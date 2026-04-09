import streamlit as st

import db
from ui.components import inject_styles, render_hero, render_sidebar
from views.document_management_view import render as render_document_management
from views.knowledge_explorer_view import render as render_knowledge_explorer


# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="Knowledge Assistant", layout="wide")


# =========================
# SHARED THEME + SIDEBAR
# =========================
inject_styles()
db.init_db()

docs_count, chunks_count = db.get_kb_stats()
recent_docs = db.get_recent_documents(limit=5)

active_menu = st.session_state.get("single_active_menu", "app")
selected_menu = render_sidebar(
    active_page=active_menu,
    total_docs=docs_count,
    total_chunks=chunks_count,
    recent_documents=recent_docs,
    key_prefix="single",
    navigation_mode="single_page",
)
st.session_state.single_active_menu = selected_menu


# =========================
# MAIN CONTENT (SINGLE PAGE SWITCH)
# =========================
if selected_menu == "app":
    render_hero(docs_count=docs_count, chunks_count=chunks_count)
elif selected_menu == "Knowledge Explorer":
    render_knowledge_explorer()
elif selected_menu == "Document Management":
    render_document_management()


# =========================
# CHAT INPUT (UI ONLY)
# =========================
if selected_menu == "app":
    question = st.chat_input("Tanya sesuatu...")
    if question:
        st.chat_message("user").markdown(question)
        st.chat_message("assistant").markdown("UI demo: jawaban backend RAG belum diaktifkan.")
