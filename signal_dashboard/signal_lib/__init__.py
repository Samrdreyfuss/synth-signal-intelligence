"""signal_lib: data access, metrics and charts for the Signal Intelligence dashboard.

The package has no Streamlit dependency. Data functions take a ``run`` callable
``run(sql: str, params: list | None) -> pandas.DataFrame`` so the same code works
from Streamlit (``st.connection(...).query``), a notebook, or tests.
"""

from . import charts, companies, data, evidence, metrics, theme

__all__ = ["charts", "companies", "data", "evidence", "metrics", "theme"]
