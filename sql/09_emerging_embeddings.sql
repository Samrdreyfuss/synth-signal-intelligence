-- ============================================================================
-- 09_emerging_embeddings.sql
-- Unified record feed across sources + one embedding per distinct cleaned text.
-- Incremental: a stream on FACT_CRM_EVENTS and a task embed only new texts.
-- Portco-network rows are excluded: their text is a template ("named alongside portco X")
-- with no topic content, so they would cluster by template, not meaning.
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING;

CREATE OR REPLACE VIEW SYNTH_SIGNAL_DB.EMERGING.SOURCE_RECORDS
  COMMENT = 'Every text record from CRM notes, portco intros, expert calls and the external scan'
AS
WITH crm AS (
  SELECT 'CRM:' || e.EVENT_ID AS RECORD_ID,
         IFF(CONTAINS(LOWER(e.DESCRIPTION), 'via portfolio company'), 'Portco intro', 'CRM note') AS SOURCE,
         e.ACCOUNT_ID, c.ACCOUNT_NAME AS ENTITY_NAME, e.PERFORMED_BY_ID AS RECORDED_BY_ID,
         TO_DATE(e.PERFORMED_DATE) AS RECORD_DATE,
         TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(e.DESCRIPTION, '<[^>]+>', ''),
              '^\\s*Description:\\s*', ''), '^Intro via portfolio company;\\s*', '')) AS TEXT
  FROM SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS e
  JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES c ON c.ACCOUNT_ID = e.ACCOUNT_ID
  WHERE TO_DATE(e.PERFORMED_DATE) >= '2024-07-01'
    AND NOT REGEXP_LIKE(LOWER(c.ACCOUNT_NAME), '.*(stealth|insight partners|new co|newco).*')
    AND c.ACCOUNT_NAME NOT LIKE '%(%' AND c.ACCOUNT_NAME NOT LIKE '% / %'
),
expert AS (
  SELECT 'EXP:' || SHA1(x.THEME || '|' || x.TITLE || '|' || x.DATE), 'Expert call', NULL, 'Expert network',
         NULL, x.DATE, x.TITLE
  FROM SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_EXAMPLES x
),
scan AS (
  SELECT 'EXT:' || s.DOMAIN, 'External scan', NULL, s.COMPANY, NULL,
         COALESCE(s.SALESFORCE_LAST_ACTIVITY, '2026-10-01'::DATE), s.DESCRIPTION
  FROM SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXTERNAL_SCAN s
)
SELECT r.*, SHA1(LOWER(r.TEXT)) AS TEXT_HASH
FROM (SELECT * FROM crm UNION ALL SELECT * FROM expert UNION ALL SELECT * FROM scan) r
WHERE r.TEXT IS NOT NULL AND LENGTH(r.TEXT) > 0;

CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING.TEXT_EMBEDDINGS (
  TEXT_HASH VARCHAR NOT NULL,
  TEXT VARCHAR,
  EMBEDDING VECTOR(FLOAT, 1024),
  EMBEDDED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'AI_EMBED(snowflake-arctic-embed-l-v2.0) of each distinct cleaned record text';

-- Embeds any distinct text not yet embedded. Called by the task and safe to call by hand.
CREATE OR REPLACE PROCEDURE SYNTH_SIGNAL_DB.EMERGING.EMBED_NEW_TEXTS()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  n INTEGER;
BEGIN
  INSERT INTO SYNTH_SIGNAL_DB.EMERGING.TEXT_EMBEDDINGS (TEXT_HASH, TEXT, EMBEDDING)
  SELECT TEXT_HASH, TEXT, AI_EMBED('snowflake-arctic-embed-l-v2.0', TEXT)
  FROM (SELECT TEXT_HASH, ANY_VALUE(TEXT) AS TEXT
        FROM SYNTH_SIGNAL_DB.EMERGING.SOURCE_RECORDS
        WHERE TEXT_HASH NOT IN (SELECT TEXT_HASH FROM SYNTH_SIGNAL_DB.EMERGING.TEXT_EMBEDDINGS)
        GROUP BY TEXT_HASH);
  n := SQLROWCOUNT;
  RETURN 'embedded ' || n || ' new texts';
END;
$$;

CALL SYNTH_SIGNAL_DB.EMERGING.EMBED_NEW_TEXTS();
