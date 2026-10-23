-- ============================================================================
-- 14_market_universe.sql
-- Sourcing: companies we have NOT spoken with (no CRM account), matched to themes.
--   ANALYTICS.DIM_MARKET_COMPANIES   600 synthetic companies, deterministic (HASH-based),
--                                    described with the same sector + priority templates as 04
--   ANALYTICS.MARKET_SIGNALS         where they surface in other sources (expert calls,
--                                    portfolio-company notes, external scan), with dates
--   ANALYTICS.MARKET_EMBEDDINGS      AI_EMBED of each description (~50k input tokens, once)
--   ANALYTICS.MARKET_THEME_FIT       cosine similarity to every theme definition, ranked
--   EVIDENCE.SOURCING_TARGETS        company x theme: fit, signals, recency, sourcing score
-- Needs 04 and 07 (THEME_EMBEDDINGS). Re-running reproduces the same companies.
-- ============================================================================

CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.ANALYTICS.DIM_MARKET_COMPANIES
  COMMENT = 'Synthetic companies with no CRM relationship, for sourcing (deterministic)'
AS
WITH n AS (
  SELECT SEQ4() AS I FROM TABLE(GENERATOR(ROWCOUNT => 900))
),
words AS (
  SELECT
    ARRAY_CONSTRUCT('Arbor','Kestrel','Quill','Tessel','Ondine','Brightwater','Corvid','Halcyon','Juniper','Lattice',
                    'Meridian','Northwind','Obsidian','Paragon','Quartz','Riverbend','Sable','Tidal','Umbra','Vellum',
                    'Wren','Yarrow','Zephyr','Alder','Basalt','Cinder','Drift','Ember','Fathom','Gossamer') AS A,
    ARRAY_CONSTRUCT('Works','Stack','Signal','Forge','Loop','Grid','Path','Layer','Bridge','Harbor',
                    'Mint','Scale','Pilot','Shift','Sense','Vector','Field','Labs.io','Kit','Flow') AS B
),
sectors AS (
  SELECT SECTOR, INDUSTRY, SUB_INDUSTRIES, OFFERING, BUYERS, AFFINITY_THEMES,
         ROW_NUMBER() OVER (ORDER BY SECTOR) - 1 AS SI
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_SECTOR_PROFILES
),
named AS (
  SELECT n.I, ABS(HASH(n.I, 'mkt')) AS H,
         w.A[n.I % 30]::STRING || ' ' || w.B[FLOOR(n.I / 30) % 20]::STRING AS COMPANY_NAME
  FROM n CROSS JOIN words w
),
-- distinct names that do not collide with a CRM account; keep 600
c AS (
  SELECT * FROM named
  WHERE COMPANY_NAME NOT IN (SELECT ACCOUNT_NAME FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY COMPANY_NAME ORDER BY I) = 1
  ORDER BY I LIMIT 600
),
hot AS (
  SELECT ARRAY_CONSTRUCT('Forward deployed engineering','LLM observability','Retrieval augmented generation',
                         'Voice AI','AI red teaming') AS ARR
),
p AS (
  SELECT c.I, c.H, c.COMPANY_NAME, s.SECTOR, s.INDUSTRY, s.OFFERING, s.BUYERS,
         s.SUB_INDUSTRIES[c.H % ARRAY_SIZE(s.SUB_INDUSTRIES)]::STRING AS SUB_INDUSTRY,
         ARRAY_CONSTRUCT('Pre-seed','Seed','Series A','Series B','Series C','Growth')[
           ARRAY_CONSTRUCT(0,1,1,1,2,2,2,3,3,4,5)[FLOOR(c.H / 3) % 11]::INT]::STRING AS STAGE,
         -- 2 sector priorities; 2 in 5 companies (younger, faster-moving) add a hot theme
         ARRAY_DISTINCT(ARRAY_CAT(
           ARRAY_CONSTRUCT(s.AFFINITY_THEMES[c.H % 5]::STRING,
                           s.AFFINITY_THEMES[(c.H + 2) % 5]::STRING),
           IFF(c.H % 5 < 2, ARRAY_CONSTRUCT(h.ARR[FLOOR(c.H / 13) % 5]::STRING), ARRAY_CONSTRUCT())))
           AS STATED_PRIORITIES
  FROM c
  JOIN sectors s ON s.SI = c.H % 12
  CROSS JOIN hot h
),
flat AS (
  SELECT p.I, f.INDEX AS POS, f.value::STRING AS THEME
  FROM p, LATERAL FLATTEN(p.STATED_PRIORITIES) f
),
phrases AS (
  SELECT fl.I, LISTAGG(d.PRIORITY_PHRASE, '; ') WITHIN GROUP (ORDER BY fl.POS) AS PRIORITY_TEXT
  FROM flat fl JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS d ON d.THEME = fl.THEME
  GROUP BY fl.I
)
SELECT
  'MKT' || LPAD(p.I + 1, 4, '0') AS COMPANY_ID,
  p.COMPANY_NAME,
  LOWER(REGEXP_REPLACE(p.COMPANY_NAME, '[^A-Za-z]', '')) || '.com' AS DOMAIN,
  p.SECTOR, p.INDUSTRY, p.SUB_INDUSTRY, p.STAGE,
  CASE p.STAGE WHEN 'Pre-seed' THEN 3 + p.H % 8 WHEN 'Seed' THEN 8 + p.H % 25
               WHEN 'Series A' THEN 25 + p.H % 70 WHEN 'Series B' THEN 80 + p.H % 170
               WHEN 'Series C' THEN 200 + p.H % 400 ELSE 500 + p.H % 2000 END AS HEADCOUNT,
  ARRAY_CONSTRUCT('North America','Europe','APAC','LATAM')[FLOOR(p.H / 7) % 4]::STRING AS HQ_REGION,
  CASE p.STAGE WHEN 'Pre-seed' THEN 2025 WHEN 'Seed' THEN 2023 WHEN 'Series A' THEN 2021
               WHEN 'Series B' THEN 2019 WHEN 'Series C' THEN 2016 ELSE 2010 END + p.H % 3 AS FOUNDED_YEAR,
  p.STATED_PRIORITIES,
  p.COMPANY_NAME || ' provides ' || p.OFFERING || ' for ' || p.SUB_INDUSTRY || ' organisations, selling mainly to ' ||
    p.BUYERS || '. This year the company is focused on ' || ph.PRIORITY_TEXT || '.' AS DESCRIPTION
FROM p JOIN phrases ph USING (I);

-- Where each company surfaces outside CRM. About 1 in 3 companies has no signal at all
-- (found by profile fit only); companies with a hot-theme priority surface more, and more recently.
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.ANALYTICS.MARKET_SIGNALS
  COMMENT = 'Synthetic mentions of market companies in expert calls, portco notes and the external scan'
AS
WITH hot AS (
  SELECT ARRAY_CONSTRUCT('Forward deployed engineering','LLM observability','Retrieval augmented generation',
                         'Voice AI','AI red teaming') AS ARR
),
m AS (
  SELECT c.COMPANY_ID, c.COMPANY_NAME, c.STATED_PRIORITIES,
         ABS(HASH(c.COMPANY_ID, 'sig')) AS H,
         ARRAYS_OVERLAP(c.STATED_PRIORITIES, h.ARR) AS IS_HOT
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_MARKET_COMPANIES c CROSS JOIN hot h
),
k AS (
  SELECT m.*, IFF(m.H % 3 = 0, 0, 1 + m.H % IFF(m.IS_HOT, 6, 3)) AS N_SIGNALS FROM m
),
rows_ AS (
  SELECT k.*, g.INDEX AS J, ABS(HASH(k.COMPANY_ID, g.INDEX, 'row')) AS R
  FROM k, LATERAL FLATTEN(ARRAY_GENERATE_RANGE(0, k.N_SIGNALS)) g
),
portcos AS (
  SELECT ARRAY_AGG(DISTINCT PORTCO) WITHIN GROUP (ORDER BY PORTCO) AS ARR
  FROM SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_PORTCOS
),
s1 AS (
  SELECT rows_.COMPANY_ID, rows_.COMPANY_NAME, rows_.J, rows_.R,
         ARRAY_CONSTRUCT('Expert call','Expert call','Portco network','Portco network','External scan')[rows_.R % 5]::STRING AS SOURCE,
         rows_.STATED_PRIORITIES[rows_.R % ARRAY_SIZE(rows_.STATED_PRIORITIES)]::STRING AS THEME,
         DATEADD(day, -IFF(rows_.IS_HOT, rows_.R % 180, rows_.R % 540), '2026-10-17'::DATE) AS SIGNAL_DATE,
         p.ARR[rows_.R % ARRAY_SIZE(p.ARR)]::STRING AS PORTCO
  FROM rows_ CROSS JOIN portcos p
)
SELECT
  'MSG' || LPAD(ROW_NUMBER() OVER (ORDER BY s1.COMPANY_ID, s1.J), 5, '0') AS SIGNAL_ID,
  s1.COMPANY_ID, s1.SOURCE, s1.THEME, s1.SIGNAL_DATE,
  IFF(s1.SOURCE = 'Portco network', s1.PORTCO, NULL) AS PORTCO,
  CASE s1.R % 5
    WHEN 0 THEN 'Expert call: ' || s1.COMPANY_NAME || ' came up as a vendor customers are piloting for ' || LOWER(d.PHRASE) || '.'
    WHEN 1 THEN 'Expert call: a former buyer named ' || s1.COMPANY_NAME || ' as the most credible new entrant in ' || LOWER(d.PHRASE) || '.'
    WHEN 2 THEN 'Portco note: ' || s1.PORTCO || ' is evaluating ' || s1.COMPANY_NAME || ' for ' || LOWER(d.PHRASE) || '.'
    WHEN 3 THEN 'Portco note: ' || s1.PORTCO || ' was introduced to ' || s1.COMPANY_NAME || ' by a mutual customer; strong on ' || LOWER(d.PHRASE) || '.'
    ELSE 'External scan: ' || s1.COMPANY_NAME || ' surfaced in the market scan for ' || LOWER(d.PHRASE) || '.'
  END AS SNIPPET
FROM s1 JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS d ON d.THEME = s1.THEME;

CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.ANALYTICS.MARKET_EMBEDDINGS
  COMMENT = 'AI_EMBED(snowflake-arctic-embed-l-v2.0) of DIM_MARKET_COMPANIES.DESCRIPTION'
AS
SELECT COMPANY_ID, AI_EMBED('snowflake-arctic-embed-l-v2.0', DESCRIPTION) AS EMBEDDING
FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_MARKET_COMPANIES;

CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.ANALYTICS.MARKET_THEME_FIT
  COMMENT = 'Cortex embedding similarity between market company descriptions and theme definitions'
AS
WITH s AS (
  SELECT m.COMPANY_ID, t.THEME, VECTOR_COSINE_SIMILARITY(m.EMBEDDING, t.EMBEDDING) AS SIMILARITY
  FROM SYNTH_SIGNAL_DB.ANALYTICS.MARKET_EMBEDDINGS m
  CROSS JOIN SYNTH_SIGNAL_DB.ANALYTICS.THEME_EMBEDDINGS t
)
SELECT COMPANY_ID, THEME, SIMILARITY,
       RANK() OVER (PARTITION BY COMPANY_ID ORDER BY SIMILARITY DESC) AS FIT_RANK
FROM s;

-- Company x theme sourcing targets. A company is a target for a theme when the theme is in
-- its top 4 by Cortex fit, or it has been seen on that theme in another source.
-- SOURCING_SCORE (0-1) = 0.5 fit (similarity scaled across all targets of the theme)
--                      + 0.3 signal strength (theme signals, capped at 3)
--                      + 0.2 recency (signal in the last 90 days = 1, last 180 = 0.5)
CREATE OR REPLACE VIEW SYNTH_SIGNAL_DB.EVIDENCE.SOURCING_TARGETS
  COMMENT = 'Companies with no CRM relationship, ranked per theme for sourcing'
AS
WITH sig AS (
  SELECT COMPANY_ID, THEME, COUNT(*) AS THEME_SIGNALS, MAX(SIGNAL_DATE) AS LAST_SIGNAL,
         ARRAY_TO_STRING(ARRAY_AGG(DISTINCT SOURCE) WITHIN GROUP (ORDER BY SOURCE), ', ') AS SIGNAL_SOURCES,
         ARRAY_TO_STRING(ARRAY_AGG(DISTINCT PORTCO) WITHIN GROUP (ORDER BY PORTCO), ', ') AS PORTCOS
  FROM SYNTH_SIGNAL_DB.ANALYTICS.MARKET_SIGNALS GROUP BY 1, 2
),
allsig AS (
  SELECT COMPANY_ID, COUNT(*) AS ALL_SIGNALS FROM SYNTH_SIGNAL_DB.ANALYTICS.MARKET_SIGNALS GROUP BY 1
),
t AS (
  SELECT f.COMPANY_ID, f.THEME, f.SIMILARITY, f.FIT_RANK,
         COALESCE(s.THEME_SIGNALS, 0) AS THEME_SIGNALS, s.LAST_SIGNAL, s.SIGNAL_SOURCES, s.PORTCOS,
         COALESCE(a.ALL_SIGNALS, 0) AS ALL_SIGNALS
  FROM SYNTH_SIGNAL_DB.ANALYTICS.MARKET_THEME_FIT f
  LEFT JOIN sig s ON s.COMPANY_ID = f.COMPANY_ID AND s.THEME = f.THEME
  LEFT JOIN allsig a ON a.COMPANY_ID = f.COMPANY_ID
  WHERE f.FIT_RANK <= 4 OR s.THEME_SIGNALS > 0
),
scored AS (
  SELECT t.*,
         (t.SIMILARITY - MIN(t.SIMILARITY) OVER (PARTITION BY t.THEME))
           / NULLIF(MAX(t.SIMILARITY) OVER (PARTITION BY t.THEME) - MIN(t.SIMILARITY) OVER (PARTITION BY t.THEME), 0)
           AS FIT_SCORE,
         LEAST(t.THEME_SIGNALS, 3) / 3 AS SIGNAL_SCORE,
         CASE WHEN t.LAST_SIGNAL >= DATEADD(day, -90, '2026-10-17'::DATE) THEN 1
              WHEN t.LAST_SIGNAL >= DATEADD(day, -180, '2026-10-17'::DATE) THEN 0.5 ELSE 0 END AS RECENCY_SCORE
  FROM t
)
SELECT
  sc.THEME, sc.COMPANY_ID, c.COMPANY_NAME, c.DOMAIN, c.INDUSTRY, c.SUB_INDUSTRY, c.STAGE, c.HEADCOUNT,
  c.HQ_REGION, c.FOUNDED_YEAR, c.DESCRIPTION,
  ROUND(sc.SIMILARITY, 4) AS SIMILARITY, sc.FIT_RANK, sc.FIT_RANK <= 4 AS PROFILE_FIT,
  ARRAY_CONTAINS(sc.THEME::VARIANT, c.STATED_PRIORITIES) AS STATED_PRIORITY,
  sc.THEME_SIGNALS, sc.ALL_SIGNALS, sc.LAST_SIGNAL, sc.SIGNAL_SOURCES, sc.PORTCOS,
  ROUND(0.5 * COALESCE(sc.FIT_SCORE, 0) + 0.3 * sc.SIGNAL_SCORE + 0.2 * sc.RECENCY_SCORE, 3) AS SOURCING_SCORE,
  CASE WHEN sc.THEME_SIGNALS > 0 AND sc.FIT_RANK <= 4 THEN 'Fit + signal'
       WHEN sc.THEME_SIGNALS > 0 THEN 'Signal only'
       ELSE 'Fit only' END AS BASIS
FROM scored sc
JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_MARKET_COMPANIES c USING (COMPANY_ID);
