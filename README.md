# synth-signal-intelligence

Signal Intelligence dashboard over a synthetic copy of the data model (`SYNTH_SIGNAL_DB`).
All data is fictional; nothing here reads from or writes to `ANALYTICS_PROD`.

## Layout

```
sql/
  01_setup_schema.sql          # database, 2 schemas, 10 tables
  02_seed_synthetic_data.sql   # deterministic synthetic data (re-runnable)
  03_evidence_views.sql        # EVIDENCE schema: unified evidence + attribution views
  04_company_profiles.sql      # theme definitions, sector profiles, company descriptions
  05_crm_on_profile.sql        # rewrites CRM note text so ~75% of mentions follow profiles
  06_derived_signals.sql       # DERIVED schema: theme/quarterly/FDE signals from CRM
  07_company_theme_fit.sql     # Cortex AI_EMBED fit + COMPANY_THEME_RELEVANCE view
  08_seed_emerging_topics.sql  # ~640 AI-written seed notes = answer key for topic detection
  09_emerging_embeddings.sql   # EMERGING schema: record feed + one embedding per distinct text
  10_emerging_clustering.sql   # CONFIG + CLUSTER_RECORDS() online clustering (Snowpark/numpy)
  11_emerging_signals.sql      # CLUSTER_MEMBERS, CLUSTER_SIGNALS (velocity, spread, status)
  12_emerging_naming_and_review.sql  # NAME_CLUSTERS(), PROMOTE_CLUSTER(), REVIEW_CLUSTER()
  13_emerging_schedule.sql     # stream + hourly task REFRESH_EMERGING (created suspended)
signal_dashboard/              # Streamlit in Snowflake app (Workspace, container runtime)
  streamlit_app.py             # UI only: header, KPIs, eight tabs
  emerging_view.py             # Emerging topics tab (map, ranked list, topic card, review)
  evidence_view.py             # Evidence explorer tab (drill-down UI)
  companies_view.py            # Company fit tab (profile fit vs mentions drill-down)
  signal_lib/                  # reusable library, no Streamlit dependency
    data.py                    # parameterised queries; take run(sql, params) -> DataFrame
    evidence.py                # evidence/attribution queries + pure helpers
    companies.py               # company profile / theme relevance queries + helpers
    emerging.py                # emerging-topic queries, promote/review actions, helpers
    metrics.py                 # lift vs baseline, quarterly share, momentum, KPIs, filters
    charts.py                  # Altair chart builders
    theme.py                   # palette and chart styling
  snowflake.yml  pyproject.toml  .streamlit/config.toml
tests/                         # pure-pandas tests for metrics, evidence, companies, emerging
```

## Setup

1. Run the `sql/` scripts in order (01 → 13) with a role that can create a database.
   07 calls Cortex `AI_EMBED` once (~130k input tokens). 05 keeps the original CRM
   table as `ANALYTICS.FACT_CRM_EVENTS_V1`; it rebuilds CRM from that backup, so re-run
   08 after 05. 08 calls `AI_COMPLETE` once (~74k input tokens + output) and stores the text.
2. Open `signal_dashboard/streamlit_app.py` in the Workspace and click **Run**
   (warehouse `DEFAULT_WH`, compute pool `SYSTEM_COMPUTE_POOL_CPU`, set in `snowflake.yml`).

## Dashboard

| Tab | Shows |
|---|---|
| Theme radar | Lift vs the AI-agents baseline against enterprise reach; ranked lift bars; full theme table |
| Emerging topics | Clusters discovered from embeddings: uniqueness vs velocity map, ranked list with weekly trend, topic card (definition, weekly additions by source, companies, closest records), Promote / Merge / Dismiss |
| Evidence explorer | Attribution by source per theme, corroboration, and drill-down Theme › Source › Company › evidence |
| Company fit | Cortex profile fit vs CRM mentions per company; Confirmed / Latent fit / Off-profile; company card with evidence; latent-fit outreach CSV |
| Trends | Quarterly share of enterprise activity (quarters under 200 activities dropped), YoY momentum, live monthly share, FDE panel |
| Network | Portco x theme heatmap, expert call coverage and examples |
| Action list | CRM accounts mentioning the focus theme that are unowned or untouched 90+ days (CSV export); external scan by Salesforce status |
| Live excerpts | Most recent CRM notes for the focus theme |

Lift = a theme's monthly rate ratio divided by the baseline ratio from the same scan.

## Emerging topics

1. **Embed every record.** `EMERGING.SOURCE_RECORDS` unions CRM notes, portco intros, expert
   calls and the external scan. `EMBED_NEW_TEXTS()` embeds each distinct cleaned text once.
2. **Cluster as records arrive.** `CLUSTER_RECORDS()` replays records week by week:
   - records with a tracked theme phrase belong to that theme;
   - identical text repeated 20+ times is treated as boilerplate and skipped;
   - other records join the nearest discovered cluster (cosine >= `JOIN_SIMILARITY`) or wait
     in a pool;
   - each week, pool records with >= `MIN_RECORDS` neighbours at >= `FORM_SIMILARITY` form
     a new cluster.

   Thresholds live in `EMERGING.CONFIG`. They were tuned on the seeded answer key:
   join 0.70, form 0.62, minimum 6 records.
3. **Score.** `CLUSTER_SIGNALS` adds the following, then labels each cluster New topic,
   Emerging sub-topic, Watch or Noise:
   - velocity (last 8 weeks against the 8 before);
   - spread (companies, reps, sources, industries);
   - share from the top company (over 50% means noise);
   - uniqueness (1 − similarity to the nearest theme);
   - an emergence score.
4. **Name.** `NAME_CLUSTERS()` makes two structured `AI_COMPLETE` calls per new or grown
   cluster: one for name and definition, one for whether a tracked theme covers the topic.
5. **Automate.** The task `REFRESH_EMERGING` runs hourly when the CRM stream has new rows.
   Resume it with `ALTER TASK SYNTH_SIGNAL_DB.EMERGING.REFRESH_EMERGING RESUME`.
6. **Review.**
   - `PROMOTE_CLUSTER` adds a theme definition, phrase and embedding.
   - `REVIEW_CLUSTER` marks a cluster Merged, Dismissed or Reopened.

Answer key (`EMERGING.SEED_TOPICS` plus a later pickup test): all 6 groups come out as expected.
- *New topic:* MCP, agentic checkout, inference sovereignty, and freight negotiation (added later).
- *Emerging sub-topic:* voice agents for claims, under Voice AI.
- *Noise:* the single-account decoy.

The original data alone produces no clusters. Seed rows have `EVENT_ID` prefix `EVS`, and the
pickup test rows have prefix `EVT_PICKUP_`.

## Data lineage

Theme, quarterly and FDE numbers come from `SYNTH_SIGNAL_DB.DERIVED`, computed from
`ANALYTICS.FACT_CRM_EVENTS`. Expert calls, portco links and the external scan come from
`SIGNAL_SAVED_FILES` because they have no underlying records in the database (FDE expert
document counts too). The original hand-written theme, quarterly and FDE tables are kept
in `SIGNAL_SAVED_FILES` for comparison but are no longer read by the dashboard.

## Company fit

`ANALYTICS.DIM_COMPANY_PROFILES` gives every account an industry, firmographics, stated
priorities (from `DIM_SECTOR_PROFILES`) and a description. `COMPANY_THEME_FIT` holds the
cosine similarity between each description and each theme definition (Cortex `AI_EMBED`,
`snowflake-arctic-embed-l-v2.0`). In `EVIDENCE.COMPANY_THEME_RELEVANCE` a theme is a
profile fit when it ranks in the company's top 4 of 21, and the relationship label is
Confirmed (fit + mentioned), Latent fit (fit, no mentions), Talking, off-profile
(mentioned, not a fit) or Unrelated.

## Evidence and attribution

`SYNTH_SIGNAL_DB.EVIDENCE.EVIDENCE_ITEMS` puts every source in one shape
(theme, source, company, date, snippet, link, and the source table and key it came from):

| Source | From | Notes |
|---|---|---|
| CRM note | `FACT_CRM_EVENTS` | direct call / meeting / email mentioning the theme |
| Portco intro | `FACT_CRM_EVENTS` | CRM note whose text says it came via a portfolio company |
| Portco network | `ENTERPRISE_PORTCOS` | one row per enterprise named alongside a portco |
| Expert call | `EXPERT_EXAMPLES` | call title, date and link |
| External scan | `EXTERNAL_SCAN` | company, stage and Salesforce status |

`THEME_ATTRIBUTION` gives each source's count and share per theme. `THEME_CORROBORATION`
counts independent source families (CRM, portco network, expert call, external scan) and
labels themes *Strongly corroborated* (3+), *Corroborated* (2) or *Single-source* (1).
Company names in the saved files link to CRM accounts by exact name match.

In the dashboard, click a theme's bar, select a company row, filter sources or search the
text. Each evidence card shows the record it came from, and the current list exports to CSV.

## Using the library elsewhere

```python
# e.g. in a notebook, with signal_dashboard/ on sys.path
from signal_lib import data, metrics

def run(sql, params=None):
    return session.sql(sql, params=params).to_pandas()   # Snowpark binds ? placeholders

lifted = metrics.theme_lift(data.enterprise_themes(run))
accounts = data.theme_accounts(run, "Voice AI")
```
Any callable `run(sql, params)` that executes qmark-bound SQL and returns a DataFrame works,
for example `st.connection("snowflake").query` or a `snowflake.connector` cursor wrapper.

## Tests

```
pip install pandas altair pytest
python -m pytest tests
```
