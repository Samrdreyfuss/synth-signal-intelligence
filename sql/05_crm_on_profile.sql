-- ============================================================================
-- 05_crm_on_profile.sql
-- Rewrites FACT_CRM_EVENTS descriptions so theme mentions follow each company's
-- stated priorities (DIM_COMPANY_PROFILES): ~75% on-profile, ~25% any theme.
-- Event ids, types, accounts, users and dates are unchanged. The six "hot" themes
-- still rise after 2026-04-01. Run after 04. Keeps the original as FACT_CRM_EVENTS_V1.
-- ============================================================================

CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS_V1
  CLONE SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS;

-- INSERT OVERWRITE keeps the table definition and column comments from 01_setup_schema.sql.
INSERT OVERWRITE INTO SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS
  (EVENT_ID, EVENT_TYPE, DESCRIPTION, ACCOUNT_ID, PERFORMED_BY_ID, PERFORMED_DATE)
WITH themes AS (
  SELECT ARRAY_AGG(PHRASE) WITHIN GROUP (ORDER BY THEME) AS ALL_PHRASES
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS
),
prof AS (
  SELECT p.ACCOUNT_ID,
         ARRAY_AGG(d.PHRASE) WITHIN GROUP (ORDER BY f.INDEX) AS PRIORITY_PHRASES
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_COMPANY_PROFILES p,
       LATERAL FLATTEN(p.STATED_PRIORITIES) f,
       SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS d
  WHERE d.THEME = f.value::STRING
  GROUP BY p.ACCOUNT_ID
),
b AS (
  SELECT v.*,
         TO_NUMBER(SUBSTR(v.EVENT_ID, 4)) - 1 AS N,
         IFF(ABS(HASH(v.EVENT_ID, 'on')) % 100 < 75,
             pr.PRIORITY_PHRASES[ABS(HASH(v.EVENT_ID, 'pick')) % ARRAY_SIZE(pr.PRIORITY_PHRASES)]::STRING,
             t.ALL_PHRASES[ABS(HASH(v.EVENT_ID, 'any')) % ARRAY_SIZE(t.ALL_PHRASES)]::STRING) AS PHRASE
  FROM SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS_V1 v
  JOIN prof pr ON pr.ACCOUNT_ID = v.ACCOUNT_ID
  CROSS JOIN themes t
),
s AS (
  SELECT b.*,
         ABS(HASH(N, 5)) % 100 AS RM,
         ABS(HASH(N, 6)) % 100 AS RH,
         TO_DATE(PERFORMED_DATE) >= '2026-04-01' AS IS_CURRENT,
         -- Hot themes accelerate after 2026-04-01. The AI agents baseline is deliberately not
         -- hot: it is the reference rate other themes are compared against.
         PHRASE IN ('forward deployed engineering', 'llm observability',
                    'retrieval augmented generation', 'voice ai', 'ai red teaming') AS IS_HOT
  FROM b
)
SELECT
  EVENT_ID,
  EVENT_TYPE,
  CASE WHEN RM < (CASE WHEN IS_CURRENT AND IS_HOT THEN 70 WHEN IS_CURRENT THEN 45 ELSE 30 END)
    THEN IFF(RH < 25, '<p>Description: ', '') ||
         ARRAY_CONSTRUCT('Call with CTO about ', 'Intro via portfolio company; discussed ',
                         'Met the team, strong interest in ', 'Follow-up email re: ',
                         'Enterprise buyer said their top priority is ')[N % 5]::STRING ||
         PHRASE ||
         ARRAY_CONSTRUCT('. Budget approved for next year.', '. Evaluating three vendors.',
                         '. Wants a pilot in Q1.', ', pain is integration with existing stack.')[N % 4]::STRING ||
         IFF(RH < 25, '</p>', '')
    ELSE ARRAY_CONSTRUCT('Quarterly check-in, no major updates.', 'Sent deck and follow-up materials.',
                         'Rescheduled meeting to next week.', 'Discussed hiring plans and runway.',
                         'Intro to founders, will reconnect.')[N % 5]::STRING
  END AS DESCRIPTION,
  ACCOUNT_ID,
  PERFORMED_BY_ID,
  PERFORMED_DATE
FROM s;
