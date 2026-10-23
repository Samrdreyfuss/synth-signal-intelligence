-- ============================================================================
-- 09_emerging_terms.sql
-- Emerging-term detection: extract 1-3 word terms from CRM notes, portco intros and
-- expert call titles, then score them on uniqueness (novelty), velocity and spread.
-- Statistical only (no Cortex). Run after 01-07 (and 08 if you want the test seed).
-- Safe to re-run. Decisions (promote / dismiss) in TERM_DECISIONS are preserved.
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING;

-- Tunable thresholds. Edit values here; the scoring view reads them at query time.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING.CONFIG (
  KEY VARCHAR NOT NULL, VALUE FLOAT NOT NULL, DESCRIPTION VARCHAR);
MERGE INTO SYNTH_SIGNAL_DB.EMERGING.CONFIG t
USING (SELECT * FROM VALUES
  ('recent_days',        60,  'Length of the recent window, ending at the as-of date'),
  ('baseline_days',      365, 'Length of the baseline window immediately before the recent window'),
  ('min_mentions',       10,  'Minimum recent mentions to be flagged'),
  ('min_companies',      5,   'Minimum distinct companies in the recent window'),
  ('max_company_share',  0.4, 'Reject terms where one company accounts for more than this share of recent mentions'),
  ('new_velocity',       5,   'Minimum velocity for status New'),
  ('accel_velocity',     3,   'Minimum velocity for status Accelerating'),
  ('accel_burst_z',      3,   'Minimum weekly burst z-score for status Accelerating'),
  ('watch_velocity',     2,   'Minimum velocity for status Watch'),
  ('watch_companies',    3,   'Minimum companies for status Watch')
) s(KEY, VALUE, DESCRIPTION) ON t.KEY = s.KEY
WHEN NOT MATCHED THEN INSERT VALUES (s.KEY, s.VALUE, s.DESCRIPTION);

-- Common words that cannot start or end a term (a term made only of these is dropped).
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.EMERGING.STOPWORDS (WORD VARCHAR NOT NULL) AS
SELECT TRIM(value::STRING) FROM TABLE(FLATTEN(SPLIT(
  'a,an,the,and,or,but,if,of,to,in,on,at,by,for,with,about,from,into,over,under,re,is,are,was,were,be,been,'
  || 'it,its,this,that,these,those,their,they,them,we,our,us,you,your,he,she,his,her,i,me,my,not,no,yes,so,'
  || 'as,than,then,there,here,what,which,who,whom,when,where,why,how,all,any,each,some,more,most,other,'
  || 'such,only,own,same,too,very,can,will,just,should,now,next,week,weeks,year,years,month,months,'
  || 'q1,q2,q3,q4,said,says,team,call,calls,email,meeting,met,follow,up,discussed,description,p,'
  || 'has,have,had,do,does,did,would,could,via,also,new,top,three,existing,stack', ',')));

-- Decisions made by a reviewer. PROMOTE_TERM / DISMISS_TERM write here.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING.TERM_DECISIONS (
  TERM VARCHAR NOT NULL, DECISION VARCHAR NOT NULL, THEME VARCHAR,
  DECIDED_BY VARCHAR DEFAULT CURRENT_USER(), DECIDED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());

-- Every text record the detector reads, one row per record.
CREATE OR REPLACE VIEW SYNTH_SIGNAL_DB.EMERGING.TEXT_RECORDS
  COMMENT = 'CRM notes, portco intros and expert call titles as cleaned text'
AS
SELECT 'CRM:' || e.EVENT_ID AS RECORD_ID,
       IFF(CONTAINS(LOWER(e.DESCRIPTION), 'via portfolio company'), 'Portco intro', 'CRM note') AS SOURCE,
       e.ACCOUNT_ID, e.PERFORMED_BY_ID AS AUTHOR_ID, TO_DATE(e.PERFORMED_DATE) AS RECORD_DATE,
       TRIM(REGEXP_REPLACE(LOWER(REGEXP_REPLACE(e.DESCRIPTION, '<[^>]+>', ' ')), '[^a-z0-9]+', ' ')) AS CLEAN_TEXT
FROM SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS e
WHERE TO_DATE(e.PERFORMED_DATE) >= '2024-07-01'
UNION ALL
SELECT 'EXP:' || SHA1(x.THEME || '|' || x.TITLE || '|' || x.DATE), 'Expert call',
       NULL, NULL, x.DATE,
       TRIM(REGEXP_REPLACE(LOWER(x.TITLE), '[^a-z0-9]+', ' '))
FROM SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_EXAMPLES x;

-- One row per (record, term). Dynamic table so new CRM rows are picked up automatically.
CREATE OR REPLACE DYNAMIC TABLE SYNTH_SIGNAL_DB.EMERGING.TERM_OCCURRENCES
  TARGET_LAG = '1 hour'
  WAREHOUSE = DEFAULT_WH
  COMMENT = '1-3 word terms per text record; refreshed automatically from TEXT_RECORDS'
AS
WITH words AS (
  SELECT r.RECORD_ID, r.SOURCE, r.ACCOUNT_ID, r.AUTHOR_ID, r.RECORD_DATE,
         w.INDEX AS POS, w.value::STRING AS WORD
  FROM SYNTH_SIGNAL_DB.EMERGING.TEXT_RECORDS r,
       LATERAL SPLIT_TO_TABLE(r.CLEAN_TEXT, ' ') w
  WHERE w.value::STRING <> ''
),
seq AS (
  SELECT words.*,
         LEAD(WORD, 1) OVER (PARTITION BY RECORD_ID ORDER BY POS) AS W2,
         LEAD(WORD, 2) OVER (PARTITION BY RECORD_ID ORDER BY POS) AS W3
  FROM words
),
grams AS (
  SELECT RECORD_ID, SOURCE, ACCOUNT_ID, AUTHOR_ID, RECORD_DATE, 1 AS N, WORD AS FIRST_WORD, WORD AS LAST_WORD, WORD AS TERM FROM seq
  UNION ALL
  SELECT RECORD_ID, SOURCE, ACCOUNT_ID, AUTHOR_ID, RECORD_DATE, 2, WORD, W2, WORD || ' ' || W2 FROM seq WHERE W2 IS NOT NULL
  UNION ALL
  SELECT RECORD_ID, SOURCE, ACCOUNT_ID, AUTHOR_ID, RECORD_DATE, 3, WORD, W3, WORD || ' ' || W2 || ' ' || W3 FROM seq WHERE W3 IS NOT NULL
)
SELECT DISTINCT g.RECORD_ID, g.SOURCE, g.ACCOUNT_ID, g.AUTHOR_ID, g.RECORD_DATE, g.N, g.TERM
FROM grams g
LEFT JOIN SYNTH_SIGNAL_DB.EMERGING.STOPWORDS s1 ON s1.WORD = g.FIRST_WORD
LEFT JOIN SYNTH_SIGNAL_DB.EMERGING.STOPWORDS s2 ON s2.WORD = g.LAST_WORD
WHERE s1.WORD IS NULL AND s2.WORD IS NULL
  AND LENGTH(g.TERM) >= 4
  AND NOT REGEXP_LIKE(g.TERM, '^[0-9 ]+$');

-- As-of date for scoring: the latest record date (so the synthetic copy scores "as of" its data).
CREATE OR REPLACE VIEW SYNTH_SIGNAL_DB.EMERGING.AS_OF AS
SELECT MAX(RECORD_DATE) AS AS_OF FROM SYNTH_SIGNAL_DB.EMERGING.TEXT_RECORDS;

-- Uniqueness, velocity and spread per term, with status. One row per term with recent mentions.
CREATE OR REPLACE VIEW SYNTH_SIGNAL_DB.EMERGING.TERM_SIGNALS
  COMMENT = 'Emerging-term scores: novelty, velocity, burst, spread, emergence score and status'
AS
WITH cfg AS (
  SELECT OBJECT_AGG(KEY, VALUE::VARIANT) AS C FROM SYNTH_SIGNAL_DB.EMERGING.CONFIG
),
win AS (
  SELECT a.AS_OF,
         DATEADD(day, -cfg.C:recent_days::INT + 1, a.AS_OF) AS RECENT_START,
         DATEADD(day, -cfg.C:recent_days::INT - cfg.C:baseline_days::INT + 1, a.AS_OF) AS BASE_START,
         cfg.C:recent_days::INT AS RECENT_DAYS, cfg.C:baseline_days::INT AS BASE_DAYS, cfg.C
  FROM SYNTH_SIGNAL_DB.EMERGING.AS_OF a CROSS JOIN cfg
),
totals AS (
  SELECT COUNT_IF(r.RECORD_DATE >= w.RECENT_START AND r.RECORD_DATE <= w.AS_OF) AS RECENT_RECORDS,
         COUNT_IF(r.RECORD_DATE >= w.BASE_START AND r.RECORD_DATE < w.RECENT_START) AS BASE_RECORDS
  FROM SYNTH_SIGNAL_DB.EMERGING.TEXT_RECORDS r CROSS JOIN win w
),
occ AS (
  SELECT o.*, a.INDUSTRY,
         o.RECORD_DATE >= w.RECENT_START AND o.RECORD_DATE <= w.AS_OF AS IN_RECENT,
         o.RECORD_DATE >= w.BASE_START AND o.RECORD_DATE < w.RECENT_START AS IN_BASE,
         o.RECORD_DATE >= DATEADD(day, -29, w.AS_OF) AND o.RECORD_DATE <= w.AS_OF AS IN_LAST30,
         o.RECORD_DATE >= DATEADD(day, -59, w.AS_OF) AND o.RECORD_DATE < DATEADD(day, -29, w.AS_OF) AS IN_PRIOR30
  FROM SYNTH_SIGNAL_DB.EMERGING.TERM_OCCURRENCES o
  CROSS JOIN win w
  LEFT JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_COMPANY_PROFILES a ON a.ACCOUNT_ID = o.ACCOUNT_ID
),
acct AS (   -- concentration: share of recent mentions from the single busiest company
  SELECT TERM, MAX(N) / NULLIF(SUM(N), 0) AS TOP_COMPANY_SHARE
  FROM (SELECT TERM, ACCOUNT_ID, COUNT(*) AS N FROM occ WHERE IN_RECENT AND ACCOUNT_ID IS NOT NULL GROUP BY 1, 2)
  GROUP BY TERM
),
weekly AS (  -- weekly counts in the baseline for the burst z-score (zero weeks included)
  SELECT t.TERM, wk.WEEK_START, COALESCE(c.N, 0) AS N
  FROM (SELECT DISTINCT TERM FROM occ WHERE IN_RECENT) t
  CROSS JOIN (
    SELECT DATEADD(week, SEQ4(), DATE_TRUNC('week', w.BASE_START)) AS WEEK_START
    FROM win w, TABLE(GENERATOR(ROWCOUNT => 60))
  ) wk
  LEFT JOIN (SELECT TERM, DATE_TRUNC('week', RECORD_DATE) AS WEEK_START, COUNT(*) AS N
             FROM occ WHERE IN_BASE GROUP BY 1, 2) c
    ON c.TERM = t.TERM AND c.WEEK_START = wk.WEEK_START
  CROSS JOIN win w
  WHERE wk.WEEK_START < DATE_TRUNC('week', w.RECENT_START)
),
burst AS (
  SELECT TERM, AVG(N) AS BASE_WEEKLY_MEAN, STDDEV_POP(N) AS BASE_WEEKLY_STD FROM weekly GROUP BY TERM
),
agg AS (
  SELECT TERM, ANY_VALUE(N) AS WORDS,
         MIN(RECORD_DATE) AS FIRST_SEEN, MAX(RECORD_DATE) AS LAST_SEEN,
         COUNT_IF(IN_RECENT) AS RECENT_MENTIONS,
         COUNT_IF(IN_BASE) AS BASE_MENTIONS,
         COUNT_IF(IN_LAST30) AS LAST30, COUNT_IF(IN_PRIOR30) AS PRIOR30,
         COUNT(DISTINCT IFF(IN_RECENT, ACCOUNT_ID, NULL)) AS COMPANIES,
         COUNT(DISTINCT IFF(IN_RECENT, AUTHOR_ID, NULL)) AS AUTHORS,
         COUNT(DISTINCT IFF(IN_RECENT, SOURCE, NULL)) AS SOURCES,
         COUNT(DISTINCT IFF(IN_RECENT, INDUSTRY, NULL)) AS INDUSTRIES,
         ARRAY_AGG(DISTINCT IFF(IN_RECENT, SOURCE, NULL)) AS SOURCE_LIST
  FROM occ GROUP BY TERM
),
themes AS (SELECT THEME, PHRASE FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS),
overlap AS (  -- terms that are, or contain, or sit inside an existing theme phrase
  SELECT a.TERM, ANY_VALUE(th.THEME) AS OVERLAPS_THEME
  FROM agg a JOIN themes th
    ON CONTAINS(' ' || a.TERM || ' ', ' ' || th.PHRASE || ' ')
    OR CONTAINS(' ' || th.PHRASE || ' ', ' ' || a.TERM || ' ')   -- whole-word containment only
  GROUP BY a.TERM
),
scored AS (
  SELECT a.*, w.AS_OF, w.RECENT_START, w.C,
         a.RECENT_MENTIONS / NULLIF(t.RECENT_RECORDS, 0) * 10000 AS RECENT_PER_10K,
         a.BASE_MENTIONS / NULLIF(t.BASE_RECORDS, 0) * 10000 AS BASE_PER_10K,
         -- smoothed rate ratio: (recent+1)/recent_records over (base+1)/base_records
         ((a.RECENT_MENTIONS + 1) / NULLIF(t.RECENT_RECORDS, 0))
           / ((a.BASE_MENTIONS + 1) / NULLIF(t.BASE_RECORDS, 0)) AS VELOCITY,
         -- novelty: share of the term's normalised rate that sits in the recent window (0..1)
         (a.RECENT_MENTIONS / NULLIF(t.RECENT_RECORDS, 0))
           / NULLIF(a.RECENT_MENTIONS / NULLIF(t.RECENT_RECORDS, 0) + a.BASE_MENTIONS / NULLIF(t.BASE_RECORDS, 0), 0) AS NOVELTY,
         (a.LAST30 + 1) / (a.PRIOR30 + 1) AS ACCELERATION,
         ((a.RECENT_MENTIONS / (w.RECENT_DAYS / 7.0)) - b.BASE_WEEKLY_MEAN) / (b.BASE_WEEKLY_STD + 0.5) AS BURST_Z,
         c.TOP_COMPANY_SHARE,
         ov.OVERLAPS_THEME
  FROM agg a CROSS JOIN win w CROSS JOIN totals t
  LEFT JOIN burst b ON b.TERM = a.TERM
  LEFT JOIN acct c ON c.TERM = a.TERM
  LEFT JOIN overlap ov ON ov.TERM = a.TERM
  WHERE a.RECENT_MENTIONS > 0
),
ranked AS (
  SELECT s.*,
         s.NOVELTY * LN(1 + s.VELOCITY) * LN(1 + s.COMPANIES) * (1 + 0.25 * (s.SOURCES - 1)) AS EMERGENCE_SCORE,
         -- passes the spread guards (enough volume, companies, not one-account noise)
         s.RECENT_MENTIONS >= s.C:min_mentions::FLOAT
           AND s.COMPANIES >= s.C:min_companies::FLOAT
           AND COALESCE(s.TOP_COMPANY_SHARE, 0) <= s.C:max_company_share::FLOAT AS PASSES_SPREAD
  FROM scored s
),
labelled AS (
  SELECT r.*,
         CASE
           WHEN d.DECISION = 'Promoted' THEN 'Promoted'
           WHEN d.DECISION = 'Dismissed' THEN 'Dismissed'
           WHEN r.OVERLAPS_THEME IS NOT NULL THEN 'Known theme'
           WHEN r.PASSES_SPREAD AND r.FIRST_SEEN >= r.RECENT_START - 30
                AND r.VELOCITY >= r.C:new_velocity::FLOAT THEN 'New'
           WHEN r.PASSES_SPREAD AND r.VELOCITY >= r.C:accel_velocity::FLOAT
                AND r.BURST_Z >= r.C:accel_burst_z::FLOAT THEN 'Accelerating'
           WHEN r.COMPANIES >= r.C:watch_companies::FLOAT AND r.VELOCITY >= r.C:watch_velocity::FLOAT
                AND COALESCE(r.TOP_COMPANY_SHARE, 0) <= r.C:max_company_share::FLOAT THEN 'Watch'
           WHEN NOT r.PASSES_SPREAD AND r.VELOCITY >= r.C:new_velocity::FLOAT THEN 'Concentrated'
           ELSE 'Background'
         END AS STATUS,
         d.THEME AS PROMOTED_THEME
  FROM ranked r
  LEFT JOIN (SELECT * FROM SYNTH_SIGNAL_DB.EMERGING.TERM_DECISIONS
             QUALIFY ROW_NUMBER() OVER (PARTITION BY TERM ORDER BY DECIDED_AT DESC) = 1) d
    ON d.TERM = r.TERM
),
-- Collapse fragments and extensions of the same phrase among flagged terms:
-- drop X if a longer flagged term contains X and carries >= 80% of X's mentions (X is a fragment),
-- or if X contains a shorter flagged term that has clearly more mentions (X is a padded extension).
flagged AS (
  SELECT TERM, RECENT_MENTIONS FROM labelled WHERE STATUS IN ('New', 'Accelerating', 'Watch')
),
dropped AS (
  SELECT DISTINCT x.TERM
  FROM flagged x JOIN flagged f ON f.TERM <> x.TERM
  WHERE (CONTAINS(' ' || f.TERM || ' ', ' ' || x.TERM || ' ') AND f.RECENT_MENTIONS >= 0.8 * x.RECENT_MENTIONS)
     OR (CONTAINS(' ' || x.TERM || ' ', ' ' || f.TERM || ' ') AND x.RECENT_MENTIONS < 0.8 * f.RECENT_MENTIONS)
)
SELECT l.TERM, l.WORDS, l.STATUS, ROUND(l.EMERGENCE_SCORE, 3) AS EMERGENCE_SCORE,
       l.FIRST_SEEN, l.LAST_SEEN, l.RECENT_MENTIONS, l.BASE_MENTIONS,
       ROUND(l.RECENT_PER_10K, 2) AS RECENT_PER_10K, ROUND(l.BASE_PER_10K, 2) AS BASE_PER_10K,
       ROUND(l.VELOCITY, 2) AS VELOCITY, ROUND(l.NOVELTY, 3) AS NOVELTY,
       ROUND(l.ACCELERATION, 2) AS ACCELERATION, ROUND(l.BURST_Z, 2) AS BURST_Z,
       l.COMPANIES, l.AUTHORS, l.SOURCES, l.INDUSTRIES,
       ARRAY_TO_STRING(ARRAY_COMPACT(l.SOURCE_LIST), ', ') AS SOURCE_LIST,
       ROUND(l.TOP_COMPANY_SHARE, 3) AS TOP_COMPANY_SHARE,
       l.OVERLAPS_THEME, l.PROMOTED_THEME, l.AS_OF
FROM labelled l
LEFT JOIN dropped d ON d.TERM = l.TERM
WHERE d.TERM IS NULL;
