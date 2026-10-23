# synth-signal-intelligence

Signal Intelligence dashboard over a synthetic copy of the data model (`SYNTH_SIGNAL_DB`).
All data is fictional; nothing here reads from or writes to `ANALYTICS_PROD`.

## Layout

```
sql/
  01_setup_schema.sql          # database, 2 schemas, 10 tables
  02_seed_synthetic_data.sql   # deterministic synthetic data (re-runnable)
signal_dashboard/              # Streamlit in Snowflake app (Workspace, container runtime)
  streamlit_app.py             # UI only: header, KPIs, five tabs
  signal_lib/                  # reusable library, no Streamlit dependency
    data.py                    # parameterised queries; take run(sql, params) -> DataFrame
    metrics.py                 # lift vs baseline, quarterly share, momentum, KPIs, filters
    charts.py                  # Altair chart builders
    theme.py                   # palette and chart styling
  snowflake.yml  pyproject.toml  .streamlit/config.toml
tests/test_metrics.py          # pure-pandas tests for metrics
```

## Setup

1. Run `sql/01_setup_schema.sql`, then `sql/02_seed_synthetic_data.sql`, with a role that can create a database.
2. Open `signal_dashboard/streamlit_app.py` in the Workspace and click **Run**
   (warehouse `DEFAULT_WH`, compute pool `SYSTEM_COMPUTE_POOL_CPU`, set in `snowflake.yml`).

## Dashboard

| Tab | Shows |
|---|---|
| Theme radar | Lift vs the AI-agents baseline against enterprise reach; ranked lift bars; full theme table |
| Trends | Quarterly share of enterprise activity (quarters under 200 activities dropped), YoY momentum, live monthly share, FDE panel |
| Network | Portco x theme heatmap, expert call coverage and examples |
| Action list | CRM accounts mentioning the focus theme that are unowned or untouched 90+ days (CSV export); external scan by Salesforce status |
| Live excerpts | Most recent CRM notes for the focus theme |

Lift = a theme's monthly rate ratio divided by the baseline ratio from the same scan.

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
