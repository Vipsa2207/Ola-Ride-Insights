"""db.py - one shared database connection + a cached query runner."""
import certifi
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text, URL


@st.cache_resource
def get_engine():
    """Create the SQLAlchemy engine once per app (reads .streamlit/secrets.toml)."""
    cfg = st.secrets["mysql"]
    url = URL.create(
        "mysql+pymysql",
        username=cfg["user"], password=cfg["password"],
        host=cfg["host"], port=int(cfg["port"]), database=cfg["database"],
        query={"charset": "utf8mb4"},
    )
    ssl = {"ssl": {"ca": certifi.where()}} if cfg.get("ssl", False) else {}
    return create_engine(url, pool_pre_ping=True, pool_recycle=280, connect_args=ssl)


@st.cache_data(ttl=3600, show_spinner=False)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. Results are cached for 1 hour."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)