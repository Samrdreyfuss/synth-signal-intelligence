-- ============================================================================
-- 04_company_profiles.sql
-- Company descriptions and theme definitions, so companies can be matched to themes.
-- Deterministic (HASH-based). Run after 01 and 02. Safe to re-run.
-- Matching itself (Cortex AI_EMBED) lives in 05_company_theme_fit.sql.
-- ============================================================================

-- One row per theme: a definition used for embedding, and a business-language phrase
-- used inside company descriptions (deliberately not the theme name itself).
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS (
  THEME VARCHAR NOT NULL COMMENT 'Theme name, matches SIGNAL_SAVED_FILES.ENTERPRISE_THEMES.THEME',
  PHRASE VARCHAR NOT NULL COMMENT 'Lower-case phrase matched in CRM note text',
  DEFINITION VARCHAR NOT NULL COMMENT 'What the theme means; embedded for company matching',
  PRIORITY_PHRASE VARCHAR NOT NULL COMMENT 'How a company would describe this need in its own words'
) AS SELECT * FROM VALUES
('AI agents (baseline)','ai agents','AI agents: autonomous software agents that plan and take multi-step actions across business systems.','deploying autonomous assistants that complete multi-step back-office tasks'),
('Forward deployed engineering','forward deployed engineering','Forward deployed engineering: vendor engineers embedded with the customer to build and integrate software on site.','bringing vendor engineers on site to build custom integrations with their teams'),
('AI governance','ai governance','AI governance: policies, inventories, approvals and audit controls for how models are built and used.','putting policy, approval and audit controls around every model in production'),
('LLM observability','llm observability','LLM observability: tracing, monitoring, cost and quality analytics for large language model applications.','monitoring quality, latency and cost of their language-model features'),
('Data security posture management','data security posture management','Data security posture management: discovering sensitive data across clouds and fixing risky access.','finding sensitive data across cloud stores and locking down risky access'),
('Vector databases','vector databases','Vector databases: storing and searching embeddings for semantic retrieval and recommendations.','storing embeddings to power semantic search over their content'),
('Synthetic data','synthetic data','Synthetic data: generating artificial but realistic datasets for testing, training and privacy.','generating realistic artificial datasets so teams can test without real customer records'),
('AI code review','ai code review','AI code review: automated review of pull requests and code changes using language models.','using AI to review pull requests and catch bugs before release'),
('Model evaluation','model evaluation','Model evaluation: benchmarking and testing model accuracy, safety and regressions before release.','benchmarking model accuracy and regressions before each release'),
('Retrieval augmented generation','retrieval augmented generation','Retrieval augmented generation: grounding language model answers in company documents and knowledge bases.','grounding assistant answers in their own documents and knowledge base'),
('GPU cost optimization','gpu cost optimization','GPU cost optimization: reducing spend on GPU compute for model training and inference.','cutting the cost of GPU compute for training and inference'),
('Agent identity','agent identity','Agent identity: credentials, permissions and audit trails for non-human identities such as AI agents and bots.','issuing scoped credentials and audit trails to bots and automated agents'),
('Voice AI','voice ai','Voice AI: speech recognition and voice agents that handle phone calls and spoken interactions.','automating inbound phone calls with natural-sounding speech agents'),
('Document processing','document processing','Document processing: extracting fields and text from forms, invoices, claims and contracts.','pulling fields out of forms, invoices and contracts automatically'),
('Small language models','small language models','Small language models: compact models that run cheaply on device or at the edge.','running compact models on devices and at the edge to keep costs low'),
('AI red teaming','ai red teaming','AI red teaming: adversarial testing of AI systems for jailbreaks, data leakage and misuse.','stress-testing their AI features against jailbreaks and data leakage'),
('Data contracts','data contracts','Data contracts: agreed schemas and quality guarantees between data producers and consumers.','agreeing schemas and quality guarantees between data producers and consumers'),
('Semantic layer','semantic layer','Semantic layer: shared business metric definitions that every BI tool and AI assistant uses.','defining business metrics once so every dashboard and assistant agrees'),
('Cloud cost management','cloud cost management','Cloud cost management: visibility, allocation and optimization of cloud infrastructure spend.','getting visibility into and control over their cloud bill'),
('Browser automation','browser automation','Browser automation: software agents that operate web applications and browsers to complete tasks.','automating repetitive work inside web portals with browser bots'),
('Compliance automation','compliance automation','Compliance automation: continuously collecting evidence and mapping controls for audits and regulations.','automating audit evidence collection and regulatory control mapping')
AS v(THEME, PHRASE, DEFINITION, PRIORITY_PHRASE);

-- Sector affinities: which themes each sector tends to prioritise (first = strongest).
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.ANALYTICS.DIM_SECTOR_PROFILES (
  SECTOR VARCHAR NOT NULL,
  INDUSTRY VARCHAR NOT NULL,
  SUB_INDUSTRIES ARRAY NOT NULL,
  OFFERING VARCHAR NOT NULL,
  BUYERS VARCHAR NOT NULL,
  AFFINITY_THEMES ARRAY NOT NULL
) AS SELECT column1, column2, PARSE_JSON(column3), column4, column5, PARSE_JSON(column6) FROM VALUES
('Labs','Applied R&D','["biotech research","materials science","AI research"]','research tooling and experimental platforms','R&D and science teams','["Model evaluation","Synthetic data","GPU cost optimization","Small language models","AI red teaming"]'),
('Systems','Enterprise software','["ERP","workflow software","IT service management"]','enterprise workflow and back-office software','operations and IT leaders','["AI agents (baseline)","Browser automation","Forward deployed engineering","Agent identity","Document processing"]'),
('AI','AI software','["foundation-model apps","AI copilots","conversational AI"]','AI copilots and assistants for knowledge workers','product and engineering teams','["LLM observability","Retrieval augmented generation","Model evaluation","AI code review","AI red teaming"]'),
('Data','Data infrastructure','["data integration","data warehousing","data quality"]','data pipelines and integration platforms','data engineering teams','["Data contracts","Vector databases","Semantic layer","Synthetic data","Retrieval augmented generation"]'),
('Cloud','Cloud infrastructure','["managed hosting","developer platforms","edge compute"]','managed cloud and developer platforms','platform and infrastructure teams','["Cloud cost management","GPU cost optimization","LLM observability","Small language models","AI code review"]'),
('Analytics','Analytics & BI','["business intelligence","product analytics","forecasting"]','analytics and reporting software','finance and analytics leaders','["Semantic layer","Data contracts","Retrieval augmented generation","Vector databases","AI agents (baseline)"]'),
('Health','Healthcare','["payer","provider networks","medtech"]','care-coordination and patient engagement software','clinical operations and compliance teams','["Voice AI","Document processing","Compliance automation","AI governance","Synthetic data"]'),
('Financial','Financial services','["banking","insurance","payments"]','lending, claims and payments platforms','risk, compliance and operations teams','["AI governance","Compliance automation","Document processing","Voice AI","Data security posture management"]'),
('Logistics','Logistics & supply chain','["freight","warehousing","last-mile delivery"]','shipment tracking and warehouse management software','supply-chain operators','["Document processing","Browser automation","AI agents (baseline)","Voice AI","Forward deployed engineering"]'),
('Robotics','Robotics & industrial','["warehouse robotics","industrial automation","drones"]','robotic automation for factories and warehouses','manufacturing and plant managers','["Small language models","Forward deployed engineering","GPU cost optimization","Model evaluation","Synthetic data"]'),
('Security','Cybersecurity','["cloud security","identity security","threat detection"]','security monitoring and identity protection products','CISOs and security operations','["Data security posture management","AI red teaming","Agent identity","AI governance","Compliance automation"]'),
('Networks','Networking & telecom','["telecom carriers","network infrastructure","contact centers"]','network management and customer-contact platforms','network operations and customer-care leaders','["Voice AI","Cloud cost management","Agent identity","LLM observability","Browser automation"]');

-- One row per CRM account.
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.ANALYTICS.DIM_COMPANY_PROFILES
  COMMENT = 'Synthetic company descriptions and stated priorities (deterministic)'
AS
WITH c AS (
  SELECT ACCOUNT_ID, ACCOUNT_NAME,
         COALESCE(REGEXP_SUBSTR(ACCOUNT_NAME, '(Labs|Systems|AI|Data|Cloud|Analytics|Health|Financial|Logistics|Robotics|Security|Networks)'),
                  'Systems') AS SECTOR,
         ABS(HASH(ACCOUNT_ID, 'p')) AS H
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES
),
all_themes AS (
  SELECT ARRAY_AGG(THEME) WITHIN GROUP (ORDER BY THEME) AS ARR
  FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS
),
p AS (
  SELECT c.*, s.INDUSTRY, s.OFFERING, s.BUYERS,
         s.SUB_INDUSTRIES[c.H % ARRAY_SIZE(s.SUB_INDUSTRIES)]::STRING AS SUB_INDUSTRY,
         -- 3 priorities from the sector list (rotated by hash); 1 in 5 companies adds an off-sector one
         ARRAY_DISTINCT(ARRAY_CAT(
           ARRAY_CONSTRUCT(
             s.AFFINITY_THEMES[c.H % 5]::STRING,
             s.AFFINITY_THEMES[(c.H + 1 + (FLOOR(c.H / 5) % 2)) % 5]::STRING,
             s.AFFINITY_THEMES[(c.H + 3) % 5]::STRING),
           IFF(c.H % 5 = 0,
               ARRAY_CONSTRUCT(a.ARR[FLOOR(c.H / 11) % ARRAY_SIZE(a.ARR)]::STRING),
               ARRAY_CONSTRUCT()))) AS STATED_PRIORITIES
  FROM c
  JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_SECTOR_PROFILES s USING (SECTOR)
  CROSS JOIN all_themes a
),
flat AS (
  SELECT p.ACCOUNT_ID, f.INDEX AS POS, f.value::STRING AS THEME
  FROM p, LATERAL FLATTEN(p.STATED_PRIORITIES) f
),
phrases AS (
  SELECT fl.ACCOUNT_ID,
         LISTAGG(d.PRIORITY_PHRASE, '; ') WITHIN GROUP (ORDER BY fl.POS) AS PRIORITY_TEXT
  FROM flat fl
  JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS d ON d.THEME = fl.THEME
  GROUP BY fl.ACCOUNT_ID
)
SELECT
  p.ACCOUNT_ID,
  p.ACCOUNT_NAME,
  p.SECTOR,
  p.INDUSTRY,
  p.SUB_INDUSTRY,
  ARRAY_CONSTRUCT('1-50','51-200','201-1,000','1,001-5,000','5,000+')[p.H % 5]::STRING AS EMPLOYEE_BAND,
  ARRAY_CONSTRUCT('North America','Europe','APAC','LATAM')[FLOOR(p.H / 7) % 4]::STRING AS HQ_REGION,
  1995 + (p.H % 30) AS FOUNDED_YEAR,
  p.STATED_PRIORITIES,
  p.ACCOUNT_NAME || ' provides ' || p.OFFERING || ' for ' || p.SUB_INDUSTRY || ' organisations, selling mainly to ' ||
    p.BUYERS || '. This year the company is focused on ' || ph.PRIORITY_TEXT || '.' AS DESCRIPTION
FROM p JOIN phrases ph USING (ACCOUNT_ID);
