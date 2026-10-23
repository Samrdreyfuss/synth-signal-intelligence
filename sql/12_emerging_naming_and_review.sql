-- ============================================================================
-- 12_emerging_naming_and_review.sql
-- Cortex naming for discovered clusters + human review actions.
-- NAME_CLUSTERS() makes two structured AI_COMPLETE calls per cluster that is new or has
-- grown by 50%+ since it was last named (a few calls per run): one for a name, definition
-- and key terms, and one narrow question - is this topic covered by a tracked theme's
-- definition? - which decides new topic vs sub-topic. Context is the 15 records closest
-- to the cluster centre.
-- Cluster ids come from a deterministic date-ordered replay, so existing ids stay
-- stable as new data arrives; new clusters get new ids.
-- ============================================================================
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.EMERGING.CLUSTER_PROFILES (
  CLUSTER_ID VARCHAR, TOPIC_NAME VARCHAR, DEFINITION VARCHAR, RELATION VARCHAR,
  RELATED_THEME VARCHAR, KEY_TERMS VARCHAR, REASON VARCHAR, EXAMPLE_IDS ARRAY, NAMED_AT_MEMBERS INT,
  NAMED_AT TIMESTAMP_LTZ
) COMMENT = 'AI_COMPLETE-written name/definition per discovered cluster; RELATION = new | sub-topic | noise';

CREATE TABLE IF NOT EXISTS SYNTH_SIGNAL_DB.EMERGING.CLUSTER_REVIEW (
  CLUSTER_ID VARCHAR, STATUS VARCHAR, THEME VARCHAR, NOTE VARCHAR,
  REVIEWED_BY VARCHAR DEFAULT CURRENT_USER(), REVIEWED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'Human decisions: Promoted, Merged, Dismissed';

CREATE OR REPLACE PROCEDURE SYNTH_SIGNAL_DB.EMERGING.NAME_CLUSTERS()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
  n INTEGER;
BEGIN
  CREATE OR REPLACE TEMPORARY TABLE SYNTH_SIGNAL_DB.EMERGING.TMP_TO_NAME AS
  WITH todo AS (
    SELECT c.CLUSTER_ID, c.MEMBERS, c.CENTROID
    FROM SYNTH_SIGNAL_DB.EMERGING.CLUSTERS c
    LEFT JOIN SYNTH_SIGNAL_DB.EMERGING.CLUSTER_PROFILES p USING (CLUSTER_ID)
    WHERE p.CLUSTER_ID IS NULL OR c.MEMBERS >= 1.5 * p.NAMED_AT_MEMBERS
  ),
  ex AS (
    SELECT t.CLUSTER_ID, m.RECORD_ID, m.TEXT,
           VECTOR_COSINE_SIMILARITY(m.EMBEDDING, t.CENTROID) AS SIM
    FROM todo t JOIN SYNTH_SIGNAL_DB.EMERGING.CLUSTER_MEMBERS m USING (CLUSTER_ID)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY t.CLUSTER_ID ORDER BY SIM DESC, m.RECORD_ID) <= 15
  ),
  themes AS (
    -- every tracked theme except the broad baseline, which is a reference rate, not a parent
    SELECT LISTAGG('- ' || THEME || ': ' || DEFINITION, '\n') WITHIN GROUP (ORDER BY THEME) AS DEFS
    FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS
    WHERE THEME <> 'AI agents (baseline)'
  ),
  ex_agg AS (
    SELECT CLUSTER_ID, ARRAY_AGG(RECORD_ID) AS EXAMPLE_IDS,
           LISTAGG('- ' || TEXT, '\n') WITHIN GROUP (ORDER BY SIM DESC) AS EXAMPLES
    FROM ex GROUP BY 1
  )
  SELECT t.CLUSTER_ID, t.MEMBERS, e.EXAMPLE_IDS,
         'CRM notes from one topic cluster:\n' || e.EXAMPLES ||
         '\n\nGive the topic a short name (2-5 words), a one-sentence definition and up to 5 comma-separated'
         || ' key terms.' AS NAME_PROMPT,
         -- A narrow, fixed-answer question: free-form "is this new or a sub-topic" judgements were
         -- unreliable (broad themes absorbed everything); this wording matched the answer key 5/5.
         'Theme definitions:\n' || h.DEFS || '\n\nCRM notes:\n' || e.EXAMPLES ||
         '\n\nQuestion: Is the specific technology or practice these notes are about the same thing a single'
         || ' theme definition above names, just applied to a particular use case? Answer covered_by = that'
         || ' theme name only if its definition names the same technology or practice (for example: voice'
         || ' agents answering insurance claims calls ARE covered by a definition about voice agents handling'
         || ' phone calls). Answer covered_by = "none" if the notes are about a different technology,'
         || ' protocol, standard, regulation or buying behaviour, even if a definition is loosely related.'
         || ' Answer is_technology_topic = false if the notes are not about a technology or market at all.'
         || ' Also give a one-sentence reason.' AS COVER_PROMPT
  FROM todo t JOIN ex_agg e USING (CLUSTER_ID) CROSS JOIN themes h;

  CREATE OR REPLACE TEMPORARY TABLE SYNTH_SIGNAL_DB.EMERGING.TMP_NAMED AS
  SELECT CLUSTER_ID, MEMBERS, EXAMPLE_IDS,
         -- structured output: Cortex enforces the schema, so results are always valid JSON
         AI_COMPLETE(model => 'llama3.3-70b', prompt => NAME_PROMPT,
                     response_format => TYPE OBJECT(name STRING, definition STRING, key_terms STRING)) AS N,
         AI_COMPLETE(model => 'llama3.3-70b', prompt => COVER_PROMPT,
                     response_format => TYPE OBJECT(covered_by STRING, is_technology_topic BOOLEAN,
                                                    reason STRING)) AS C
  FROM SYNTH_SIGNAL_DB.EMERGING.TMP_TO_NAME;

  MERGE INTO SYNTH_SIGNAL_DB.EMERGING.CLUSTER_PROFILES p
  USING (
    SELECT n.CLUSTER_ID, n.N:name::STRING AS TOPIC_NAME, n.N:definition::STRING AS DEFINITION,
           CASE WHEN n.C:is_technology_topic::BOOLEAN = FALSE THEN 'noise'
                WHEN d.THEME IS NOT NULL THEN 'sub-topic'
                ELSE 'new' END AS RELATION,
           d.THEME AS RELATED_THEME,
           n.N:key_terms::STRING AS KEY_TERMS, n.C:reason::STRING AS REASON, n.EXAMPLE_IDS, n.MEMBERS
    FROM SYNTH_SIGNAL_DB.EMERGING.TMP_NAMED n
    -- only accept a cover answer that is an actual theme name
    LEFT JOIN SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS d
      ON LOWER(d.THEME) = LOWER(TRIM(n.C:covered_by::STRING)) AND d.THEME <> 'AI agents (baseline)'
    WHERE n.N IS NOT NULL AND n.C IS NOT NULL
  ) s ON p.CLUSTER_ID = s.CLUSTER_ID
  WHEN MATCHED THEN UPDATE SET TOPIC_NAME = s.TOPIC_NAME, DEFINITION = s.DEFINITION, RELATION = s.RELATION,
    RELATED_THEME = s.RELATED_THEME, KEY_TERMS = s.KEY_TERMS, REASON = s.REASON, EXAMPLE_IDS = s.EXAMPLE_IDS,
    NAMED_AT_MEMBERS = s.MEMBERS, NAMED_AT = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN INSERT (CLUSTER_ID, TOPIC_NAME, DEFINITION, RELATION, RELATED_THEME, KEY_TERMS, REASON,
    EXAMPLE_IDS, NAMED_AT_MEMBERS, NAMED_AT)
    VALUES (s.CLUSTER_ID, s.TOPIC_NAME, s.DEFINITION, s.RELATION, s.RELATED_THEME, s.KEY_TERMS, s.REASON,
            s.EXAMPLE_IDS, s.MEMBERS, CURRENT_TIMESTAMP());
  n := SQLROWCOUNT;
  RETURN 'named ' || n || ' clusters';
END;
$$;

-- Promote a cluster to a tracked theme: adds a definition (and phrase) and its embedding,
-- so every dashboard tab picks it up. PHRASE is what CRM notes are matched on.
CREATE OR REPLACE PROCEDURE SYNTH_SIGNAL_DB.EMERGING.PROMOTE_CLUSTER(
  CLUSTER_ID VARCHAR, THEME_NAME VARCHAR, PHRASE VARCHAR, DEFINITION VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
  INSERT INTO SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS (THEME, PHRASE, DEFINITION, PRIORITY_PHRASE)
  SELECT :THEME_NAME, LOWER(:PHRASE), :DEFINITION, LOWER(:DEFINITION)
  WHERE NOT EXISTS (SELECT 1 FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS WHERE THEME = :THEME_NAME);
  INSERT INTO SYNTH_SIGNAL_DB.ANALYTICS.THEME_EMBEDDINGS (THEME, DEFINITION, EMBEDDING)
  SELECT :THEME_NAME, :DEFINITION, AI_EMBED('snowflake-arctic-embed-l-v2.0', :DEFINITION)
  WHERE NOT EXISTS (SELECT 1 FROM SYNTH_SIGNAL_DB.ANALYTICS.THEME_EMBEDDINGS WHERE THEME = :THEME_NAME);
  DELETE FROM SYNTH_SIGNAL_DB.EMERGING.CLUSTER_REVIEW WHERE CLUSTER_ID = :CLUSTER_ID;
  INSERT INTO SYNTH_SIGNAL_DB.EMERGING.CLUSTER_REVIEW (CLUSTER_ID, STATUS, THEME)
  VALUES (:CLUSTER_ID, 'Promoted', :THEME_NAME);
  RETURN 'promoted ' || :CLUSTER_ID || ' as ' || :THEME_NAME;
END;
$$;

CREATE OR REPLACE PROCEDURE SYNTH_SIGNAL_DB.EMERGING.REVIEW_CLUSTER(
  CLUSTER_ID VARCHAR, STATUS VARCHAR, THEME VARCHAR, NOTE VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
  IF (:STATUS NOT IN ('Merged', 'Dismissed', 'Reopen')) THEN
    RETURN 'status must be Merged, Dismissed or Reopen';
  END IF;
  DELETE FROM SYNTH_SIGNAL_DB.EMERGING.CLUSTER_REVIEW WHERE CLUSTER_ID = :CLUSTER_ID;
  IF (:STATUS <> 'Reopen') THEN
    INSERT INTO SYNTH_SIGNAL_DB.EMERGING.CLUSTER_REVIEW (CLUSTER_ID, STATUS, THEME, NOTE)
    VALUES (:CLUSTER_ID, :STATUS, :THEME, :NOTE);
  END IF;
  RETURN :STATUS || ' ' || :CLUSTER_ID;
END;
$$;
