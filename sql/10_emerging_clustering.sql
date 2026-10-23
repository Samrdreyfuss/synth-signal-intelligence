-- ============================================================================
-- 10_emerging_clustering.sql
-- Online clustering of record embeddings to surface new topics.
-- Records are replayed in date order, week by week:
--   * a record containing a known theme phrase belongs to that theme;
--   * boilerplate (identical text repeated >= BOILERPLATE_REPEATS times) is skipped;
--   * otherwise it joins the nearest discovered cluster if cosine >= JOIN_SIMILARITY,
--     or waits in a holding pool;
--   * each week, pool records within POOL_DAYS that have >= MIN_RECORDS neighbours at
--     >= FORM_SIMILARITY form a new cluster.
-- Thresholds were tuned on the seeded answer key (08_seed_emerging_topics.sql).
-- A full replay is cheap (numpy, no Cortex) and makes results reproducible.
-- ============================================================================
CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.EMERGING.CONFIG (KEY VARCHAR, VALUE FLOAT, NOTE VARCHAR) AS
SELECT * FROM VALUES
  ('JOIN_SIMILARITY', 0.70, 'cosine needed to join an existing discovered cluster'),
  ('FORM_SIMILARITY', 0.62, 'cosine between pool records to count as neighbours'),
  ('MIN_RECORDS', 6, 'neighbours needed to form a new cluster'),
  ('POOL_DAYS', 60, 'how long an unassigned record waits in the pool'),
  ('BOILERPLATE_REPEATS', 20, 'identical texts repeated this often are treated as boilerplate'),
  ('RECENT_DAYS', 56, 'recent window for velocity'),
  ('NEW_TOPIC_MAX_AGE_DAYS', 180, 'clusters created within this many days count as new'),
  ('MIN_ACCOUNTS', 5, 'fewer distinct companies than this = noise'),
  ('MAX_TOP_ACCOUNT_SHARE', 0.5, 'one company providing more than this share = noise')
AS v(KEY, VALUE, NOTE);

CREATE OR REPLACE PROCEDURE SYNTH_SIGNAL_DB.EMERGING.CLUSTER_RECORDS()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'numpy', 'pandas', 'pyarrow')
HANDLER = 'run'
AS
$$
import json
import numpy as np
import pandas as pd


def _unit(m):
    return m / np.linalg.norm(m, axis=-1, keepdims=True)


def run(session):
    cfg = {r["KEY"]: r["VALUE"] for r in session.table("SYNTH_SIGNAL_DB.EMERGING.CONFIG").collect()}
    join, form = cfg["JOIN_SIMILARITY"], cfg["FORM_SIMILARITY"]
    min_records, pool_days = int(cfg["MIN_RECORDS"]), int(cfg["POOL_DAYS"])
    boiler = int(cfg["BOILERPLATE_REPEATS"])

    rec = session.sql("""
        SELECT RECORD_ID, SOURCE, ACCOUNT_ID, RECORD_DATE, TEXT, TEXT_HASH
        FROM SYNTH_SIGNAL_DB.EMERGING.SOURCE_RECORDS
    """).to_pandas()
    emb_rows = session.sql(
        "SELECT TEXT_HASH, EMBEDDING::ARRAY AS E FROM SYNTH_SIGNAL_DB.EMERGING.TEXT_EMBEDDINGS").collect()
    vec = {r["TEXT_HASH"]: np.asarray(json.loads(r["E"]), dtype=np.float32) for r in emb_rows}
    rec = rec[rec["TEXT_HASH"].isin(vec)].reset_index(drop=True)
    phrases = session.sql(
        "SELECT THEME, PHRASE FROM SYNTH_SIGNAL_DB.ANALYTICS.DIM_THEME_DEFINITIONS").to_pandas()

    rec["RECORD_DATE"] = pd.to_datetime(rec["RECORD_DATE"])
    low = rec["TEXT"].str.lower()
    rec["ASSIGNMENT"] = None
    for theme, phrase in zip(phrases["THEME"], phrases["PHRASE"]):
        hit = rec["ASSIGNMENT"].isna() & low.str.contains(phrase, regex=False)
        rec.loc[hit, "ASSIGNMENT"] = "THEME:" + theme
    repeats = rec["TEXT_HASH"].map(rec["TEXT_HASH"].value_counts())
    rec.loc[rec["ASSIGNMENT"].isna() & (repeats >= boiler), "ASSIGNMENT"] = "BOILERPLATE"

    E = _unit(np.stack([vec[h] for h in rec["TEXT_HASH"]]))
    rec["WEEK"] = rec["RECORD_DATE"].dt.to_period("W").dt.start_time
    cents, counts, created = {}, {}, {}
    pool, next_id = [], 0
    todo = rec[rec["ASSIGNMENT"].isna()].sort_values(["RECORD_DATE", "RECORD_ID"])
    for week, idx in todo.groupby("WEEK").groups.items():
        for i in idx:
            if cents:
                keys = list(cents)
                sims = np.stack([cents[k] for k in keys]) @ E[i]
                j = int(sims.argmax())
                if sims[j] >= join:
                    k = keys[j]
                    rec.at[i, "ASSIGNMENT"] = k
                    counts[k] += 1
                    cents[k] = _unit(cents[k] + (E[i] - cents[k]) / counts[k])
                    continue
            pool.append(i)
        pool = [i for i in pool
                if rec.at[i, "ASSIGNMENT"] is None and (week - rec.at[i, "RECORD_DATE"]).days <= pool_days]
        while len(pool) >= min_records:
            P = E[pool]
            S = P @ P.T
            neighbours = (S >= form).sum(axis=1)
            j = int(neighbours.argmax())
            if neighbours[j] < min_records:
                break
            members = [pool[x] for x in np.where(S[j] >= form)[0]]
            next_id += 1
            k = f"C{next_id:03d}"
            cents[k] = _unit(E[members].mean(axis=0))
            counts[k], created[k] = len(members), week
            rec.loc[members, "ASSIGNMENT"] = k
            taken = set(members)
            pool = [i for i in pool if i not in taken]

    rec["ASSIGNMENT"] = rec["ASSIGNMENT"].fillna("UNASSIGNED")
    out = rec[["RECORD_ID", "ASSIGNMENT"]].rename(columns={"ASSIGNMENT": "CLUSTER_ID"})
    session.write_pandas(out, "RECORD_CLUSTERS", database="SYNTH_SIGNAL_DB", schema="EMERGING",
                         auto_create_table=True, overwrite=True)

    clusters = pd.DataFrame([
        {"CLUSTER_ID": k, "CREATED_WEEK": created[k].date().isoformat(), "MEMBERS": counts[k],
         "CENTROID": json.dumps([round(float(x), 6) for x in cents[k]])}
        for k in cents
    ], columns=["CLUSTER_ID", "CREATED_WEEK", "MEMBERS", "CENTROID"])
    session.write_pandas(clusters, "CLUSTERS_RAW", database="SYNTH_SIGNAL_DB", schema="EMERGING",
                         auto_create_table=True, overwrite=True)
    session.sql("""
        CREATE OR REPLACE TABLE SYNTH_SIGNAL_DB.EMERGING.CLUSTERS AS
        SELECT CLUSTER_ID, TO_DATE(CREATED_WEEK) AS CREATED_WEEK, MEMBERS,
               PARSE_JSON(CENTROID)::VECTOR(FLOAT, 1024) AS CENTROID
        FROM SYNTH_SIGNAL_DB.EMERGING.CLUSTERS_RAW
    """).collect()
    session.sql("DROP TABLE IF EXISTS SYNTH_SIGNAL_DB.EMERGING.CLUSTERS_RAW").collect()
    assigned = int((~rec["ASSIGNMENT"].isin(["UNASSIGNED", "BOILERPLATE"])
                    & ~rec["ASSIGNMENT"].str.startswith("THEME:")).sum())
    return f"{len(cents)} discovered clusters, {assigned} records assigned to them, {len(rec)} records scanned"
$$;

CALL SYNTH_SIGNAL_DB.EMERGING.CLUSTER_RECORDS();
