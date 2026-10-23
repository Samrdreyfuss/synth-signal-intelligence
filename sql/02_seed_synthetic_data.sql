-- ============================================================================
-- 02_seed_synthetic_data.sql
-- Fills SYNTH_SIGNAL_DB with deterministic synthetic data (HASH-based, no RANDOM()),
-- so every run produces the same rows. Run 01_setup_schema.sql first.
-- Safe to re-run: every table is truncated before it is loaded.
-- All values are fictional. Links use docs.example.com and domains end in .example.
-- ============================================================================

-- ---------------------------------------------------------------- ANALYTICS

TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.ANALYTICS.DIM_USERS;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS;

-- 40 users, ids 005000000000000001..040
INSERT INTO SYNTH_SIGNAL_DB.ANALYTICS.DIM_USERS
SELECT '005' || LPAD(TO_VARCHAR(SEQ4()+1),15,'0'),
  ARRAY_CONSTRUCT('Avery','Jordan','Taylor','Morgan','Riley','Casey','Quinn','Harper','Rowan','Emerson')[SEQ4()%10]::STRING || ' ' ||
  ARRAY_CONSTRUCT('Chen','Patel','Garcia','Kim','Nguyen','Okafor','Rossi','Schmidt')[FLOOR(SEQ4()/10)*2 % 8 + SEQ4()%2]::STRING
FROM TABLE(GENERATOR(ROWCOUNT=>40));

-- 1,500 companies with ~15% portfolio, ~18% unowned, some 90+ day gaps and a few excluded names
INSERT INTO SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES
WITH g AS (SELECT SEQ4() n FROM TABLE(GENERATOR(ROWCOUNT=>1500))),
b AS (SELECT n,
  ARRAY_CONSTRUCT('Nova','Apex','Lumen','Vertex','Helio','Quanta','Cobalt','Atlas','Zenith','Orbit','Pioneer','Summit','Harbor','Cedar','Ember','Falcon','Granite','Iris','Juniper','Kestrel','Lattice','Meridian','Nimbus','Onyx','Prism')[n%25]::STRING AS p1,
  ARRAY_CONSTRUCT('Labs','Systems','AI','Data','Cloud','Analytics','Health','Financial','Logistics','Robotics','Security','Networks')[FLOOR(n/25)%12]::STRING AS p2,
  ABS(HASH(n,1))%100 r1, ABS(HASH(n,2))%100 r2, ABS(HASH(n,3))%100 r3
 FROM g)
SELECT '001' || LPAD(TO_VARCHAR(n+1),15,'0'),
  CASE WHEN n IN (7,311) THEN 'Stealth Startup ' || n
       WHEN n IN (52) THEN 'NewCo ' || n
       WHEN n IN (90) THEN 'New Co Holdings'
       WHEN n IN (133) THEN 'Insight Partners Fund ' || n
       WHEN n IN (204,777) THEN p1 || ' ' || p2 || ' (duplicate)'
       WHEN n IN (450,1201) THEN p1 || ' / ' || p2
       ELSE p1 || ' ' || p2 || CASE WHEN n>=300 THEN ' ' || CHR(65+FLOOR(n/300)%26) ELSE '' END END,
  CASE WHEN r1 < 15 THEN 'Portfolio Company' WHEN r1 < 70 THEN 'Prospect' WHEN r1 < 85 THEN 'Customer Prospect' ELSE 'Other' END,
  LOWER(p1 || p2 || n) || '.com',
  CASE WHEN r2 < 8 THEN NULL WHEN r2 < 12 THEN '' WHEN r2 < 18 THEN 'Unassigned Queue' ELSE 'PENDING' END,
  CASE WHEN r3 < 5 THEN NULL ELSE DATEADD(day, -(ABS(HASH(n,4))%400), '2026-10-17'::DATE) END,
  CASE WHEN r3 < 60 THEN NULL ELSE ARRAY_CONSTRUCT('Timing','Competitor selected','No budget','Not a fit','Went dark','Valuation mismatch')[r3%6]::STRING END,
  CASE WHEN r3 < 60 THEN NULL ELSE 'Spoke with founders; ' || ARRAY_CONSTRUCT('they raised from another firm and are not raising again for 18 months, revisit after next milestone.','product is early and the market looks crowded; keep warm and check back next quarter.','budget frozen after reorg, champion left the company in the middle of the evaluation.')[r3%3]::STRING END
FROM b;

-- Spread owned accounts across the 40 users
UPDATE SYNTH_SIGNAL_DB.ANALYTICS.DIM_SALESFORCE__COMPANIES c SET OWNER_NAME = u.USER_NAME
FROM (SELECT USER_NAME, ROW_NUMBER() OVER (ORDER BY USER_ID)-1 rn FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_USERS) u
WHERE c.OWNER_NAME = 'PENDING' AND u.rn = ABS(HASH(c.ACCOUNT_ID))%40;

-- 60,000 events Jun 2024 - Oct 17 2026; theme mentions rise after 2026-04-01 (six themes rise faster)
INSERT INTO SYNTH_SIGNAL_DB.ANALYTICS.FACT_CRM_EVENTS
WITH g AS (SELECT SEQ4() n FROM TABLE(GENERATOR(ROWCOUNT=>60000))),
b AS (SELECT n,
  DATEADD(minute, ABS(HASH(n,1))%1440, DATEADD(day, ABS(HASH(n,2))%869, '2024-06-01'::DATE)) d,
  ABS(HASH(n,3))%100 rt, ABS(HASH(n,4))%21 th, ABS(HASH(n,5))%100 rm, ABS(HASH(n,6))%100 rh
 FROM g),
t AS (SELECT ARRAY_CONSTRUCT('ai agents','forward deployed engineering','ai governance','llm observability','data security posture management','vector databases','synthetic data','ai code review','model evaluation','retrieval augmented generation','gpu cost optimization','agent identity','voice ai','document processing','small language models','ai red teaming','data contracts','semantic layer','cloud cost management','browser automation','compliance automation') a)
SELECT 'EVT' || LPAD(TO_VARCHAR(n+1),9,'0'),
  CASE WHEN rt<30 THEN 'call' WHEN rt<50 THEN 'meeting' WHEN rt<80 THEN 'email' WHEN rt<88 THEN 'other'
       WHEN rt<91 THEN 'unassign' WHEN rt<93 THEN 'unassigned' WHEN rt<97 THEN 'opportunity_created' ELSE 'opportunity_stage_change' END,
  CASE WHEN rm < (CASE WHEN d >= '2026-04-01' AND th IN (0,1,3,9,12,15) THEN 70 WHEN d >= '2026-04-01' THEN 45 ELSE 30 END)
    THEN CASE WHEN rh<25 THEN '<p>Description: ' ELSE '' END ||
         ARRAY_CONSTRUCT('Call with CTO about ','Intro via portfolio company; discussed ','Met the team, strong interest in ','Follow-up email re: ','Enterprise buyer said their top priority is ')[n%5]::STRING ||
         t.a[th]::STRING || ARRAY_CONSTRUCT('. Budget approved for next year.','. Evaluating three vendors.','. Wants a pilot in Q1.',', pain is integration with existing stack.')[n%4]::STRING ||
         CASE WHEN rh<25 THEN '</p>' ELSE '' END
    ELSE ARRAY_CONSTRUCT('Quarterly check-in, no major updates.','Sent deck and follow-up materials.','Rescheduled meeting to next week.','Discussed hiring plans and runway.','Intro to founders, will reconnect.')[n%5]::STRING END,
  '001' || LPAD(TO_VARCHAR(ABS(HASH(n,7))%1500+1),15,'0'),
  '005' || LPAD(TO_VARCHAR(ABS(HASH(n,8))%40+1),15,'0'),
  d::TIMESTAMP_TZ
FROM b, t;

-- ---------------------------------------------------------------- SIGNAL_SAVED_FILES

TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_THEMES;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_QUARTERLY;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_PORTCOS;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_THEMES;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_EXAMPLES;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXTERNAL_SCAN;
TRUNCATE TABLE IF EXISTS SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.FDE_OTHER_QUARTERLY;

-- Scan 1 (baseline_ratio 2.66) has the baseline row and 16 themes; scan 2 (2.95) has the 5 discovered themes (NULL share).
-- monthly_rate_ratio = (current/6.55 months) / (prior/12 months)
INSERT INTO SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_THEMES
SELECT theme, prior, cur, ROUND((cur/6.55)/(prior/12.0),2), ents, share, ex, bl
FROM (SELECT column1 theme, column2 prior, column3 cur, column4 ents, column5 share, column6 ex, column7 bl FROM VALUES
('AI agents (baseline)',420,610,180,0.22,'Meridian Health, Atlas Logistics, Cobalt Financial',2.66),
('Forward deployed engineering',60,150,48,0.35,'Apex Systems, Harbor Networks, Zenith Data',2.66),
('AI governance',110,190,70,0.18,'Lumen Financial, Granite Security',2.66),
('LLM observability',80,170,55,0.27,'Vertex Cloud, Nimbus Analytics, Prism AI',2.66),
('Data security posture management',95,120,46,0.12,'Onyx Security, Cedar Health',2.66),
('Vector databases',130,110,52,0.09,'Quanta Data, Orbit Cloud',2.66),
('Synthetic data',45,60,25,0.20,'Iris Health, Kestrel Robotics',2.66),
('AI code review',70,140,50,0.31,'Falcon Labs, Juniper Systems, Ember AI',2.66),
('Model evaluation',85,150,58,0.24,'Lattice AI, Summit Analytics',2.66),
('Retrieval augmented generation',150,230,90,0.16,'Pioneer Financial, Helio Data, Atlas Cloud',2.66),
('GPU cost optimization',55,90,33,0.29,'Nova Cloud, Meridian Robotics',2.66),
('Voice AI',40,110,38,0.33,'Harbor Health, Zenith Logistics',2.66),
('AI red teaming',30,80,27,0.26,'Granite Networks, Onyx Labs',2.66),
('Document processing',120,140,60,0.14,'Cobalt Logistics, Cedar Financial',2.66),
('Semantic layer',50,65,24,0.19,'Prism Analytics, Quanta Systems',2.66),
('Compliance automation',65,85,35,0.21,'Iris Financial, Helio Health',2.66),
('Agent identity',20,75,26,NULL,'Vertex Security, Nimbus Networks',2.95),
('Small language models',35,70,29,NULL,'Kestrel AI, Lumen Labs',2.95),
('Data contracts',25,45,18,NULL,'Juniper Data, Orbit Analytics',2.95),
('Cloud cost management',90,100,41,NULL,'Apex Cloud, Summit Financial',2.95),
('Browser automation',15,55,20,NULL,'Ember Systems, Falcon Robotics',2.95));

-- Full 20 x 10 grid; 2026-Q4 is partial (160 activities) so the page drops it
INSERT INTO SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_QUARTERLY
WITH q AS (SELECT column1 quarter, column2 qi, column3 tot FROM VALUES
 ('2024-Q3',0,1850),('2024-Q4',1,1920),('2025-Q1',2,2010),('2025-Q2',3,2080),('2025-Q3',4,2150),
 ('2025-Q4',5,2230),('2026-Q1',6,2300),('2026-Q2',7,2420),('2026-Q3',8,2510),('2026-Q4',9,160)),
th AS (SELECT theme FROM SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_THEMES WHERE theme <> 'AI agents (baseline)')
SELECT th.theme, q.quarter,
  GREATEST(0, ROUND(q.tot * (0.008 + (ABS(HASH(th.theme))%20)/1000.0) * (1 + q.qi*(ABS(HASH(th.theme,1))%15)/100.0) + (ABS(HASH(th.theme,q.quarter))%5) - 2)),
  q.tot
FROM th, q;

-- 16 themes; no portco is listed as its own enterprise
INSERT INTO SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.ENTERPRISE_PORTCOS VALUES
('Forward deployed engineering','Kestrel Labs',14,'Apex Systems, Harbor Networks, Zenith Data'),
('Forward deployed engineering','Onyx AI',9,'Meridian Health, Cobalt Financial'),
('AI governance','Granite Labs',11,'Lumen Financial, Cedar Health, Atlas Logistics'),
('LLM observability','Prism Labs',13,'Vertex Cloud, Nimbus Analytics'),
('LLM observability','Helio AI',6,'Summit Analytics'),
('Data security posture management','Onyx Security',8,'Cedar Health, Pioneer Financial'),
('Vector databases','Quanta Labs',7,'Orbit Cloud'),
('AI code review','Ember AI',12,'Falcon Labs, Juniper Systems'),
('Model evaluation','Lattice Labs',10,'Summit Analytics, Nova Cloud, Atlas Cloud'),
('Retrieval augmented generation','Helio Data',15,'Pioneer Financial, Atlas Cloud, Cobalt Logistics'),
('Retrieval augmented generation','Nimbus AI',7,'Meridian Robotics'),
('GPU cost optimization','Nova Labs',6,'Meridian Robotics, Vertex Cloud'),
('Voice AI','Harbor AI',9,'Zenith Logistics, Iris Health'),
('AI red teaming','Granite Security',4,'Onyx Labs'),
('Document processing','Cedar Labs',8,'Cobalt Logistics, Lumen Financial'),
('Semantic layer','Prism Analytics',5,'Quanta Systems, Orbit Analytics'),
('Agent identity','Vertex Labs',6,'Nimbus Networks, Falcon Robotics'),
('Small language models','Kestrel AI',5,'Lumen Labs'),
('Compliance automation','Iris Financial',7,'Helio Health, Summit Financial');

INSERT INTO SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_THEMES VALUES
('AI agents (baseline)','ai agents',48,112,'Yes'),
('Forward deployed engineering','forward deployed engineer',4,17,'Yes'),
('AI governance','ai governance',11,23,'Yes'),
('LLM observability','llm observability',6,15,'No'),
('Data security posture management','dspm',9,10,'No'),
('Vector databases','vector database',14,9,'No'),
('AI code review','ai code review',3,12,'Yes'),
('Model evaluation','model evaluation',8,16,'No'),
('Retrieval augmented generation','retrieval augmented generation',19,27,'Yes'),
('GPU cost optimization','gpu cost',5,9,'No'),
('Voice AI','voice ai',4,13,'Yes'),
('AI red teaming','red teaming',2,8,'No'),
('Agent identity','agent identity',NULL,6,'No'),
('Browser automation','browser automation',1,NULL,'No');

INSERT INTO SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXPERT_EXAMPLES
SELECT column1, column2, column3, 'https://docs.example.com/expert-calls/' || LOWER(REPLACE(column1,' ','-')) || '-' || TO_CHAR(column3,'YYYYMMDD')
FROM VALUES
('AI agents (baseline)','Former VP Engineering at a top-10 bank on agent rollouts','2026-08-14'::DATE),
('AI agents (baseline)','Head of Automation, global insurer: agents vs RPA','2026-09-03'::DATE),
('AI agents (baseline)','CIO of a regional health system on agent pilots','2025-08-21'::DATE),
('Forward deployed engineering','Ex-Palantir FDE lead on staffing enterprise deployments','2026-07-22'::DATE),
('Forward deployed engineering','CTO of an AI startup on services-heavy GTM','2026-09-18'::DATE),
('Forward deployed engineering','Enterprise buyer view on vendor-embedded engineers','2025-09-10'::DATE),
('AI governance','Chief Risk Officer on model inventory requirements','2026-08-02'::DATE),
('AI governance','Compliance lead on EU AI Act readiness','2026-09-25'::DATE),
('LLM observability','Platform engineer on tracing LLM applications','2026-07-30'::DATE),
('LLM observability','Director of ML on evaluation and monitoring spend','2025-07-15'::DATE),
('Data security posture management','CISO on DSPM tool consolidation','2026-08-19'::DATE),
('Vector databases','Data architect on moving vectors into the warehouse','2025-08-05'::DATE),
('AI code review','VP Engineering on AI review in CI pipelines','2026-09-09'::DATE),
('AI code review','Staff engineer on false-positive rates of AI reviewers','2026-07-11'::DATE),
('Model evaluation','Head of Applied AI on eval harnesses','2026-08-27'::DATE),
('Retrieval augmented generation','Knowledge management lead on enterprise search with RAG','2026-07-08'::DATE),
('Retrieval augmented generation','ML engineer on chunking and retrieval quality','2025-09-17'::DATE),
('GPU cost optimization','FinOps lead on GPU reservation strategy','2026-08-11'::DATE),
('Voice AI','Contact center VP on voice agent deployments','2026-09-29'::DATE),
('Voice AI','Telecom product lead on real-time speech latency','2026-07-19'::DATE),
('AI red teaming','Security researcher on red-teaming LLM apps','2026-08-23'::DATE),
('Agent identity','IAM architect on credentials for autonomous agents','2026-09-14'::DATE),
('Browser automation','QA director on browser agents for testing','2025-07-28'::DATE);

-- 7 themes; forward deployed engineering deliberately absent
INSERT INTO SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.EXTERNAL_SCAN VALUES
('AI governance','Guardrail Works','guardrailworks.example','Series A',45,'Model inventory and policy enforcement for enterprises','In Salesforce','Jordan Patel','2026-09-30'),
('AI governance','PolicyMesh','policymesh.example','Seed',12,'Automated AI Act compliance mapping','Not in Salesforce',NULL,NULL),
('AI governance','Trustline AI','trustline.example','Series B',130,'Risk scoring for deployed ML models','Possible match','Trustline Systems (trustlinesys.com)',NULL),
('LLM observability','TraceLoop Labs','traceloop.example','Series A',38,'Tracing and cost analytics for LLM apps','In Salesforce','Avery Chen','2026-06-12'),
('LLM observability','Spectra Ops','spectraops.example','Seed',9,'Prompt-level monitoring and drift alerts','Not in Salesforce',NULL,NULL),
('LLM observability','Lensbridge','lensbridge.example','Series A',NULL,'Open-source eval and observability platform','In Salesforce','Unassigned Queue','2025-11-04'),
('AI code review','Reviewly','reviewly.example','Series A',52,'AI pull-request reviewer for monorepos','In Salesforce','Casey Kim','2026-10-02'),
('AI code review','DiffPilot','diffpilot.example','Seed',7,'Security-focused AI code review','Not in Salesforce',NULL,NULL),
('Voice AI','Cadence Voice','cadencevoice.example','Series B',160,'Real-time voice agents for contact centers','In Salesforce','Morgan Nguyen','2026-08-21'),
('Voice AI','Echoform','echoform.example','Series A',40,'Low-latency speech-to-speech models','Possible match','Echo Form Inc (echoforminc.com)',NULL),
('Agent identity','KeyAgent','keyagent.example','Seed',15,'Scoped credentials and audit for AI agents','Not in Salesforce',NULL,NULL),
('Agent identity','Warden ID','wardenid.example','Series A',33,'Identity governance for non-human identities','In Salesforce','Riley Okafor','2026-05-17'),
('AI red teaming','RedShift Labs','redshiftlabs.example','Seed',11,'Automated adversarial testing of LLM apps','Not in Salesforce',NULL,NULL),
('AI red teaming','Breachpoint AI','breachpoint.example','Series A',28,'Continuous red teaming as a service','In Salesforce','Quinn Rossi','2026-01-09'),
('Browser automation','Steerhand','steerhand.example','Series A',24,'Browser agents for back-office workflows','In Salesforce','Harper Schmidt','2026-09-12'),
('Browser automation','Clickwise','clickwise.example','Pre-seed',5,'Natural-language browser testing','Not in Salesforce',NULL,NULL);

INSERT INTO SYNTH_SIGNAL_DB.SIGNAL_SAVED_FILES.FDE_OTHER_QUARTERLY VALUES
('2024-Q3',12,3),('2024-Q4',15,4),('2025-Q1',18,4),('2025-Q2',22,6),('2025-Q3',27,7),
('2025-Q4',31,9),('2026-Q1',38,11),('2026-Q2',52,15),('2026-Q3',61,19),('2026-Q4',9,4);
