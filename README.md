# synth-signal-intelligence

Signal Intelligence dashboard over a synthetic copy of the data model (`SYNTH_SIGNAL_DB`).
All data is fictional; nothing here reads from or writes to `ANALYTICS_PROD`.

## Layout

```
sql/
  01_setup_schema.sql          # database, 2 schemas, 10 tables
  02_seed_synthetic_data.sql   # deterministic synthetic data (re-runnable)
  03_evidence_views.sql        # EVIDENCE schema: unified evidence + attribution views
signal_dashboard/              # Streamlit in Snowflake app (Workspace, container runtime)
  streamlit_app.py             # UI only: header, KPIs, six tabs
  evidence_view.py             # Evidence explorer tab (drill-down UI)
  signal_lib/                  # reusable library, no Streamlit dependency
    data.py                    # parameterised queries; take run(sql, params) -> DataFrame
    evidence.py                # evidence/attribution queries + pure helpers
    metrics.py                 # lift vs baseline, quarterly share, momentum, KPIs, filters
    charts.py                  # Altair chart builders
    theme.py                   # palette and chart styling
  snowflake.yml  pyproject.toml  .streamlit/config.toml
tests/                         # pure-pandas tests for metrics and evidence
```

## Setup

1. Run `sql/01_setup_schema.sql`, `sql/02_seed_synthetic_data.sql`, then `sql/03_evidence_views.sql`, with a role that can create a database.
2. Open `signal_dashboard/streamlit_app.py` in the Workspace and click **Run**
   (warehouse `DEFAULT_WH`, compute pool `SYSTEM_COMPUTE_POOL_CPU`, set in `snowflake.yml`).

## Dashboard

| Tab | Shows |
|---|---|
| Theme radar | Lift vs the AI-agents baseline against enterprise reach; ranked lift bars; full theme table |
| Evidence explorer | Attribution by source per theme, corroboration, and drill-down Theme › Source › Company › evidence |
| Trends | Quarterly share of enterprise activity (quarters under 200 activities dropped), YoY momentum, live monthly share, FDE panel |
| Network | Portco x theme heatmap, expert call coverage and examples |
| Action list | CRM accounts mentioning the focus theme that are unowned or untouched 90+ days (CSV export); external scan by Salesforce status |
| Live excerpts | Most recent CRM notes for the focus theme |

Lift = a theme's monthly rate ratio divided by the baseline ratio from the same scan.

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
