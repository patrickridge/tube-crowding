"""The TfL client shared by both pages, using the key from Streamlit secrets or .env."""

import streamlit as st

from tube.client import TflClient
from tube.config import KEY_NAME, app_key_from_env


def app_key() -> str | None:
    try:
        if KEY_NAME in st.secrets:  # Streamlit Cloud
            return st.secrets[KEY_NAME]
    except FileNotFoundError:  # no secrets.toml locally; fall through to .env
        pass
    return app_key_from_env()


@st.cache_resource
def get_client() -> TflClient:
    return TflClient(app_key=app_key())
