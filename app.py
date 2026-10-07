"""Entry point. Run locally with:  streamlit run app.py"""

import logging

import streamlit as st

# The import is inside the try too, so even an import error shows a message, not a traceback.
try:
    from tube.ui import main

    main()
except Exception:
    logging.getLogger(__name__).exception("Unhandled error")
    st.error("Something went wrong loading this page. Please refresh, or try again in a minute.")
