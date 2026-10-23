-- ============================================================================
-- 08_seed_emerging_topics.sql
-- Appends ~640 varied, AI-written CRM notes that act as an answer key for emerging-topic
-- detection. Existing events are untouched; seeded rows have EVENT_ID prefix 'EVS'.
-- Generated text is stored in EMERGING.SEED_NOTES, so re-running does not call Cortex again
-- unless that table is dropped. Remove the seed with:
--   DELETE FROM SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS WHERE EVENT_ID LIKE 'EVS%';
-- NOTE: 05_crm_on_profile.sql rebuilds FACT_CRM_EVENTS from the V1 backup and drops these
-- rows; re-run this script after 05.
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING;

-- Answer key: what each seeded group is and how it should be classified.
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.EMERGING.SEED_TOPICS (
  SEED_TOPIC VARCHAR, EXPECTED_STATUS VARCHAR, TOPIC_DESCRIPTION VARCHAR, AVOID_PHRASE VARCHAR,
  START_DATE DATE, MONTHLY_WEIGHTS ARRAY, TOTAL_NOTES INT, SECTORS ARRAY, SINGLE_ACCOUNT BOOLEAN
) AS SELECT column1, column2, column3, column4, column5::DATE, PARSE_JSON(column6), column7, PARSE_JSON(column8), column9 FROM VALUES
('agentic checkout', 'New topic',
 'AI agents that find, compare and complete purchases end to end on behalf of shoppers or procurement teams',
 'agentic checkout', '2026-05-15', '[1,3,6,9,10,5]', 130, '["Systems","Logistics","Financial","AI","Analytics","Cloud"]', FALSE),
('model context protocol', 'New topic',
 'adopting the Model Context Protocol (MCP) standard to connect AI assistants to internal tools, APIs and data sources',
 'model context protocol', '2026-05-01', '[1,2,5,8,10,6]', 120, '["AI","Cloud","Data","Systems","Security","Analytics"]', FALSE),
('inference sovereignty', 'New topic',
 'keeping AI model inference and data processing inside a specific country or region for data-residency and sovereignty rules',
 'inference sovereignty', '2026-07-15', '[2,5,9,6]', 80, '["Financial","Health","Networks","Cloud","Security"]', FALSE),
('voice agents for claims', 'Emerging sub-topic',
 'using voice AI phone agents specifically to take first notice of loss and handle insurance claims calls',
 'voice ai', '2026-06-01', '[2,4,7,8,4]', 70, '["Financial","Health"]', FALSE),
('office plant subscription', 'Noise',
 'a single customer repeatedly discussing switching its office plant-care subscription vendor',
 'plant subscription', '2026-09-01', '[6,4]', 40, '["Systems"]', TRUE),
('background on existing themes', 'Joins existing theme',
 'one of these existing topics, chosen by the theme field: ',
 '', '2024-07-01', '[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]', 200, '[]', FALSE);

-- One spec row per note: topic, date, account, rep, event type, intro flag.
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.EMERGING.SEED_NOTE_SPECS AS
WITH months AS (
  SELECT t.SEED_TOPIC, f.INDEX AS M, f.value::FLOAT AS W,
         SUM(f.value::FLOAT) OVER (PARTITION BY t.SEED_TOPIC) AS WSUM, t.TOTAL_NOTES, t.START_DATE
  FROM SYNTH_SIGNAL_DB.EMERGING.SEED_TOPICS t, LATERAL FLATTEN(t.MONTHLY_WEIGHTS) f
),
alloc AS (
  SELECT SEED_TOPIC, M, START_DATE, GREATEST(1, ROUND(TOTAL_NOTES * W / WSUM)) AS N FROM months
),
gen AS (SELECT SEQ4() AS I FROM TABLE(GENERATOR(ROWCOUNT => 40))),
rows_ AS (
  SELECT a.SEED_TOPIC, a.M, g.I,
         LEAST(DATEADD(day, ABS(HASH(a.SEED_TOPIC, a.M, g.I, 'd')) % 30, DATEADD(month, a.M, a.START_DATE)),
               '2026-10-17'::DATE) AS NOTE_DATE
  FROM alloc a JOIN gen g ON g.I < a.N
),
accts AS (
  SELECT p.ACCOUNT_ID, p.ACCOUNT_NAME, p.SECTOR, p.INDUSTRY,
         ROW_NUMBER() OVER (PARTITION BY p.SECTOR ORDER BY HASH(p.ACCOUNT_ID, 'seed')) - 1 AS RN_SECTOR,
         ROW_NUMBER() OVER (ORDER BY HASH(p.ACCOUNT_ID, 'seed')) - 1 AS RN_ALL
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_COMPANY_PROFILES p
  JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES c USING (ACCOUNT_ID)
  WHERE NOT REGEXP_LIKE(LOWER(c.ACCOUNT_NAME), '.*(stealth|insight partners|new co|newco).*')
    AND c.ACCOUNT_NAME NOT LIKE '%(%' AND c.ACCOUNT_NAME NOT LIKE '% / %'
),
picked AS (
  SELECT r.*, t.TOPIC_DESCRIPTION, t.AVOID_PHRASE, t.SINGLE_ACCOUNT, t.SECTORS, t.EXPECTED_STATUS,
         IFF(ARRAY_SIZE(t.SECTORS) > 0,
             t.SECTORS[ABS(HASH(r.SEED_TOPIC, r.M, r.I, 's')) % ARRAY_SIZE(t.SECTORS)]::STRING, NULL) AS SECTOR,
         ABS(HASH(r.SEED_TOPIC, r.M, r.I, 'a')) AS HA
  FROM rows_ r JOIN SYNTH_SIGNAL_DB.EMERGING.SEED_TOPICS t USING (SEED_TOPIC)
),
bg_theme AS (
  SELECT ARRAY_AGG(OBJECT_CONSTRUCT('theme', THEME, 'def', DEFINITION)) WITHIN GROUP (ORDER BY THEME) AS ARR
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS
),
sector_n AS (SELECT SECTOR, COUNT(*) AS N FROM accts GROUP BY 1),
all_n AS (SELECT COUNT(*) AS N FROM accts),
decoy AS (SELECT ACCOUNT_ID FROM accts WHERE SECTOR = 'Systems' AND RN_SECTOR = 0),
keyed AS (
  SELECT p.*, sn.N AS SECTOR_COUNT, an.N AS ALL_COUNT
  FROM picked p LEFT JOIN sector_n sn ON sn.SECTOR = p.SECTOR CROSS JOIN all_n an
)
SELECT
  'EVS' || LPAD(TO_VARCHAR(ROW_NUMBER() OVER (ORDER BY k.NOTE_DATE, k.SEED_TOPIC, k.I)), 9, '0') AS EVENT_ID,
  k.SEED_TOPIC, k.EXPECTED_STATUS, k.NOTE_DATE,
  -- decoy: always the same account; others: an account from the target sector (any sector for background)
  IFF(k.SINGLE_ACCOUNT, d.ACCOUNT_ID, COALESCE(xs.ACCOUNT_ID, xa.ACCOUNT_ID)) AS ACCOUNT_ID,
  IFF(k.SINGLE_ACCOUNT, '005000000000000007',
      '005' || LPAD(TO_VARCHAR(ABS(HASH(k.SEED_TOPIC, k.M, k.I, 'u')) % 40 + 1), 15, '0')) AS PERFORMED_BY_ID,
  ARRAY_CONSTRUCT('call', 'meeting', 'email', 'call', 'meeting')[ABS(HASH(k.SEED_TOPIC, k.I, 't')) % 5]::STRING AS EVENT_TYPE,
  (NOT k.SINGLE_ACCOUNT AND ABS(HASH(k.SEED_TOPIC, k.M, k.I, 'pc')) % 100 < 25) AS VIA_PORTCO,
  IFF(k.SEED_TOPIC = 'background on existing themes',
      b.ARR[ABS(HASH(k.M, k.I, 'bg')) % ARRAY_SIZE(b.ARR)]:theme::STRING, NULL) AS BACKGROUND_THEME,
  IFF(k.SEED_TOPIC = 'background on existing themes',
      b.ARR[ABS(HASH(k.M, k.I, 'bg')) % ARRAY_SIZE(b.ARR)]:def::STRING, k.TOPIC_DESCRIPTION) AS TOPIC_TEXT,
  IFF(k.SEED_TOPIC = 'background on existing themes',
      LOWER(b.ARR[ABS(HASH(k.M, k.I, 'bg')) % ARRAY_SIZE(b.ARR)]:theme::STRING), k.AVOID_PHRASE) AS AVOID_PHRASE,
  ARRAY_CONSTRUCT('the CTO', 'the CEO', 'the VP Engineering', 'the head of operations', 'the CIO',
                  'the head of product')[ABS(HASH(k.SEED_TOPIC, k.I, 'w')) % 6]::STRING AS CONTACT
FROM keyed k
CROSS JOIN bg_theme b
CROSS JOIN decoy d
LEFT JOIN accts xs ON xs.SECTOR = k.SECTOR AND xs.RN_SECTOR = k.HA % k.SECTOR_COUNT
LEFT JOIN accts xa ON xa.RN_ALL = k.HA % k.ALL_COUNT;

-- Generate note text once with Cortex (~74k input tokens + output). Kept across re-runs.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING.SEED_NOTES
  COMMENT = 'AI_COMPLETE-generated seed CRM notes (answer key for emerging-topic detection)'
AS
SELECT s.EVENT_ID,
       TRIM(REPLACE(AI_COMPLETE('llama3.1-70b',
         'Write one realistic CRM note (1-2 sentences, under 45 words) logged by a venture investor after a ' ||
         s.EVENT_TYPE || ' with ' || s.CONTACT || ' of ' || c.ACCOUNT_NAME || ', a ' || LOWER(pr.INDUSTRY) ||
         ' company. Topic of the conversation: ' || s.TOPIC_TEXT ||
         '. Include one concrete detail (a pilot, budget, vendor, timeline, blocker or metric). Use your own wording' ||
         IFF(s.AVOID_PHRASE <> '', '; do not use the exact phrase "' || s.AVOID_PHRASE || '"', '') ||
         '. Return only the note text, no quotes.'), '"', '')) AS NOTE_TEXT
FROM SYNTH_SIGNAL_DB.EMERGING.SEED_NOTE_SPECS s
JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES c USING (ACCOUNT_ID)
JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_COMPANY_PROFILES pr USING (ACCOUNT_ID);

-- Append to the CRM fact table (idempotent: replace any earlier seed rows).
DELETE FROM SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS WHERE EVENT_ID LIKE 'EVS%';
INSERT INTO SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS
  (EVENT_ID, EVENT_TYPE, DESCRIPTION, ACCOUNT_ID, PERFORMED_BY_ID, PERFORMED_DATE)
SELECT s.EVENT_ID, s.EVENT_TYPE,
       IFF(s.VIA_PORTCO, 'Intro via portfolio company; ', '') || n.NOTE_TEXT,
       s.ACCOUNT_ID, s.PERFORMED_BY_ID,
       DATEADD(minute, ABS(HASH(s.EVENT_ID)) % 600 + 480, s.NOTE_DATE::TIMESTAMP_NTZ)::TIMESTAMP_TZ
FROM SYNTH_SIGNAL_DB.EMERGING.SEED_NOTE_SPECS s
JOIN SYNTH_SIGNAL_DB.EMERGING.SEED_NOTES n USING (EVENT_ID);
