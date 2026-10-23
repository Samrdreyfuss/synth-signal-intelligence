-- ============================================================================
-- 01_setup_schema.sql
-- Signal Intelligence synthetic copy: creates database SYNTH_SIGNAL_DB with 10 empty tables.
-- Dialect: Snowflake. Schema only, no data. Safe to re-run (IF NOT EXISTS everywhere).
--
-- Every object is fully qualified with SYNTH_SIGNAL_DB, so nothing here touches any other
-- database. The real source warehouse is ANALYTICS_PROD; do not run this against it
-- and do not point the synthetic data at it.
--
-- Needs a role that can CREATE DATABASE. To use another database name, find and
-- replace SYNTH_SIGNAL_DB in this file and in queries/*.sql.
--
-- Schema ANALYTICS : 3 tables the dashboard's 6 live queries read
-- (only the columns those queries use; real tables are wider)
-- Schema SIGNAL_SAVED_FILES : 7 tables for the dashboard's saved JSON files
-- ============================================================================
CREATE DATABASE IF NOT EXISTS SYNTH_SIGNAL_DB;
CREATE SCHEMA IF NOT EXISTS SYNTH_SIGNAL_DB.ANALYTICS;
CREATE SCHEMA IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES;

-- ---------------------------------------------------------------- ANALYTICS

-- FACT_CRM_EVENTS: one row per CRM event (calls, meetings, emails, ownership changes, opportunity events and so on).
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS (
  EVENT_ID TEXT COMMENT 'Event identifier. Used as a tiebreaker when ordering events and returned in the excerpts result.',
  EVENT_TYPE TEXT COMMENT 'Lower-case event type. The dashboard compares UPPER(event_type) and reads CALL, MEETING, EMAIL, OTHER, UNASSIGN, UNASSIGNED, OPPORTUNITY (underscores replaced by spaces for matching).',
  DESCRIPTION TEXT COMMENT 'Free-text note body (can be long, may contain HTML and a ''Description:'' marker). All theme matching is a regex over LOWER(description).',
  ACCOUNT_ID VARCHAR(18) COMMENT 'Salesforce account id of the company the event belongs to.',
  PERFORMED_BY_ID VARCHAR(18) COMMENT 'Salesforce user id of whoever performed the event.',
  PERFORMED_DATE TIMESTAMP_TZ COMMENT 'When the event happened. Cast with TO_DATE(); queries filter from 2024-07-01.'
);

-- DIM_SALESFORCE__COMPANIES: one row per Salesforce account (company).
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES (
  ACCOUNT_ID VARCHAR(18) COMMENT 'Salesforce account id. Join key from FACT_CRM_EVENTS.',
  ACCOUNT_NAME VARCHAR(765) COMMENT 'Company name. Rows are excluded when the name matches stealth, insight partners, new co, newco, contains ''('' or contains '' / ''.',
  ACCOUNT_TYPE VARCHAR(240) COMMENT 'Account type. ILIKE ''portfolio%'' marks a portfolio company, everything else is treated as a prospect.',
  WEBSITE_CLEANED TEXT COMMENT 'Normalised website, returned as WEBSITE in the actions result.',
  OWNER_NAME VARCHAR(363) COMMENT 'Name of the account owner. NULL, empty string or a value starting with ''unassigned'' means unowned.',
  DATE_OF_LAST_ACTIVITY DATE COMMENT 'Date of the last activity. More than 90 days ago (or NULL) means ''No touch in 90+ days''.',
  LAST_LOSS_DROP_REASON VARCHAR(765) COMMENT 'Most recent loss or drop reason (pick-list style text).',
  LAST_LOSS_DROP_NOTES VARCHAR(98304) COMMENT 'Free-text notes that go with the last loss or drop reason. Truncated to 160 characters in the result.'
);

-- DIM_USERS: one row per Salesforce user.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.ANALYTICS.DIM_USERS (
  USER_ID VARCHAR(18) COMMENT 'Salesforce user id. Join key from FACT_CRM_EVENTS.PERFORMED_BY_ID.',
  USER_NAME VARCHAR(363) COMMENT 'Display name of the user. Returned as LAST_EVENT_BY and LAST_CONVO_BY.'
);

-- Logical joins used by the queries (not enforced):
-- FACT_CRM_EVENTS.ACCOUNT_ID -> DIM_SALESFORCE__COMPANIES.ACCOUNT_ID
-- FACT_CRM_EVENTS.PERFORMED_BY_ID -> DIM_USERS.USER_ID

-- ---------------------------------------------------------------- SIGNAL_SAVED_FILES

-- enterprise_themes. Two scans share this file; baseline_ratio holds the AI-agents baseline of the scan each theme came from (two distinct values). The 5 discovered themes have no share_from_portco_intros key. Must contain the row 'AI agents (baseline)' or the overlap calc throws.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_THEMES (
  theme VARCHAR NOT NULL COMMENT 'Theme name or ''AI agents (baseline)''.',
  prior_mentions INTEGER NOT NULL COMMENT 'Mentions Apr 2025 to Mar 2026.',
  current_mentions INTEGER NOT NULL COMMENT 'Mentions Apr 1 to Oct 17, 2026.',
  monthly_rate_ratio FLOAT NOT NULL COMMENT 'Current monthly mention rate divided by prior monthly rate.',
  current_enterprises INTEGER NOT NULL COMMENT 'Distinct enterprises mentioning the theme in the current window.',
  share_from_portco_intros FLOAT COMMENT 'Share of current mentions that came from portfolio-company introductions. Key absent for the 5 discovered themes.',
  example_enterprises VARCHAR NOT NULL COMMENT 'Up to a few enterprise names, comma separated.',
  baseline_ratio FLOAT NOT NULL COMMENT 'monthly_rate_ratio of the AI-agents baseline in the same scan.'
);

-- enterprise_quarterly. Complete grid of 20 themes x 10 quarters (2024-Q3 to 2026-Q4). total_activities is constant within a quarter. The page drops quarters with fewer than 200 activities.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_QUARTERLY (
  theme VARCHAR NOT NULL COMMENT 'Theme name (20 themes, no baseline row).',
  quarter VARCHAR(7) NOT NULL COMMENT 'Quarter label such as 2024-Q3.',
  mentions INTEGER NOT NULL COMMENT 'Enterprise activities matching the theme.',
  total_activities INTEGER NOT NULL COMMENT 'All enterprise activities in the quarter.'
);

-- enterprise_portcos. Covers 16 of the themes. Rows where the portco was the enterprise itself were removed. Some rows list only one enterprise.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_PORTCOS (
  theme VARCHAR NOT NULL COMMENT 'Theme name.',
  portco VARCHAR NOT NULL COMMENT 'Portfolio company name.',
  activities INTEGER NOT NULL COMMENT 'Matching enterprise activities that named the portco.',
  enterprises VARCHAR NOT NULL COMMENT 'Up to three enterprise names, comma separated.'
);

-- expert_themes. The dataset document points at two uploads: a top-level url (this file, 14 rows) and an earlier source.url (asset abf60f20559a1928dac5df8d63ebf430, 9 rows). Both have the same columns. Must contain the row 'AI agents (baseline)'.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_THEMES (
  theme VARCHAR NOT NULL COMMENT 'Theme name or ''AI agents (baseline)''.',
  search_phrase VARCHAR NOT NULL COMMENT 'The one exact phrase searched for the theme.',
  q3_2025_docs INTEGER COMMENT 'Matching expert call documents in Q3 2025.',
  q3_2026_docs INTEGER COMMENT 'Matching expert call documents in Q3 2026.',
  active_project_oct_2026 VARCHAR(3) NOT NULL COMMENT 'Whether an expert call project on the theme was active in October 2026.'
);

-- expert_examples. Marked fixed in the dataset document. Same two-upload pattern as expert_themes (earlier source.url asset d5cb5c91b8ff20e8a90d4d8f61f5b3ab, 11 rows, same columns).
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_EXAMPLES (
  theme VARCHAR NOT NULL COMMENT 'Theme name.',
  title VARCHAR NOT NULL COMMENT 'Title of the expert call document.',
  date DATE NOT NULL COMMENT 'Call date, YYYY-MM-DD.',
  url VARCHAR NOT NULL COMMENT 'Link to the document in the firm''s document platform.'
);

-- external_scan. Covers 7 themes only. Forward deployed engineering is deliberately not scanned.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXTERNAL_SCAN (
  theme VARCHAR NOT NULL COMMENT 'One of 7 scanned themes.',
  company VARCHAR NOT NULL COMMENT 'Company name.',
  domain VARCHAR NOT NULL COMMENT 'Company website domain.',
  stage VARCHAR NOT NULL COMMENT 'Funding stage.',
  headcount INTEGER COMMENT 'Employee count.',
  description VARCHAR NOT NULL COMMENT 'One-line company description.',
  salesforce_status VARCHAR NOT NULL COMMENT 'Result of the Salesforce check by exact website and by name.',
  salesforce_owner_or_match VARCHAR COMMENT 'Owner name when found; ''Name (website)'' of the possible match when status is ''Possible match''; null when not in Salesforce.',
  salesforce_last_activity DATE COMMENT 'Last activity date, YYYY-MM-DD. Null for not-in-Salesforce and possible-match rows.'
);

-- fde_other_quarterly. One row per quarter, 2024-Q3 to 2026-Q4.
CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.FDE_OTHER_QUARTERLY (
  quarter VARCHAR(7) NOT NULL COMMENT 'Quarter label such as 2024-Q3.',
  enterprise_fde_activities INTEGER NOT NULL COMMENT 'Enterprise activities mentioning forward deployed engineering.',
  expert_fde_docs INTEGER NOT NULL COMMENT 'Expert call documents mentioning forward deployed engineering.'
);
