"""Start the local bilingual reconciliation workspace with Streamlit."""

import streamlit as st

from ui import services
from ui.pages import VIEWS, run_financial
from ui.text import LANGUAGES, PAGES, text


def main() -> None:
    st.set_page_config(page_title="AI Financial Reconciliation Agent", layout="wide")
    state = st.session_state
    if "samples" not in state:
        state.update(source_mode="sample", uploads={}, upload_errors={}, upload_generation=0)
        try:
            state["samples"] = services.sample_files()
            run_financial(state["samples"])
        except services.AppInputError as error:
            state["samples"] = {}
            state["finance_error"] = error.args

    lang = st.sidebar.selectbox(text("en", "language"), list(LANGUAGES), format_func=LANGUAGES.__getitem__, key="ui_language")
    st.sidebar.title(text(lang, "product"))
    page = st.sidebar.radio(text(lang, "navigation"), PAGES, format_func=lambda item: text(lang, item), key="ui_page")
    st.sidebar.divider()
    mode = st.sidebar.radio(text(lang, "provider"), ("mock", "live"), format_func=lambda item: text(lang, item), key="ui_mode")
    st.sidebar.caption(f"{text(lang, 'data_source')} · {text(lang, state['source_mode'])}")
    st.title(text(lang, page))
    st.caption(text(lang, "prototype"))
    if page in ("anomalies", "assistant") and mode == "mock":
        st.info(text(lang, "mock_notice"))
    VIEWS[page](lang, mode)


if __name__ == "__main__":
    main()
