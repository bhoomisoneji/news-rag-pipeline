from __future__ import annotations

import streamlit as st

from src.ui import handle_question


st.set_page_config(page_title="News RAG Pipeline", layout="centered")
st.title("News RAG Pipeline")
st.caption("Ask questions over the local Inc42 article collection. Answers are extractive or structured from stored records.")

question = st.text_input("Question", placeholder="What are the main stories about AI in this collection?")
submitted = st.button("Submit", type="primary")

if submitted:
    result = handle_question(question)
    if result["error"]:
        st.warning(result["error"])
    else:
        if result["mode_label"]:
            st.caption(f"Query mode: {result['mode_label']}")
        st.subheader("Answer")
        st.write(result["answer"])
        st.subheader("Sources")
        if result["sources"]:
            for url in result["sources"]:
                st.markdown(f"- [{url}]({url})")
        else:
            st.write("none")
else:
    st.info("Enter a question and click Submit. The index in data/chroma and records in data/records must already exist.")
