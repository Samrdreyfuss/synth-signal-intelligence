"""signal_lib: data access, metrics and charts for the Signal Intelligence dashboard.

The package has no Streamlit dependency. Data functions take a ``run`` callable
``run(sql: str, params: list | None) -> pandas.DataFrame`` so the same code works
from Streamlit (``st.connection(...).query``), a notebook, or tests.
"""

# The app reloads these modules when this differs from its CODE_VERSION (see streamlit_app.py).
CODE_VERSION = 5

from . import charts, companies, data, emerging, evidence, metrics, theme, topics

__all__ = ["charts", "companies", "data", "emerging", "evidence", "metrics", "theme", "topics"]
