# -*- coding: utf-8 -*-
import os
import sys
import json
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

# Force UTF-8 encoding for standard output on Windows to support emojis/unicode
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add src folder to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from context_builder import assemble_context
from draft_machine import draft_reply, draft_reply_with_metadata
from triage import triage_inbox, triage_thread
from task_logger import log_action, get_action_log

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="The Desk \u2014 Inbox Copilot",
    page_icon="\U0001f58b\ufe0f",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------- INITIALIZE GMAIL CLIENT SAFELY -----------------
gmail_available = False
gmail_client = None
gmail_error = None
try:
    from gmail_client import GmailClient
    gmail_client = GmailClient()
    gmail_available = True
except Exception as e:
    gmail_error = e

@st.cache_resource
def _get_send_reply():
    if gmail_available and gmail_client:
        return gmail_client.send_reply
    return None

@st.cache_resource
def _get_calendar_engine():
    import calendar_engine
    return calendar_engine

# Helper to load/save JSON data
def load_json_data(file_name, default):
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_approved_draft(thread, draft_text, sent_via_gmail=False, gmail_message_id=None):
    t_id = thread.get("thread_id") or thread.get("id")
    st.session_state.approved[t_id] = draft_text
    try:
        approved_file = "data/approved_drafts.json"
        existing = load_json_data(approved_file, [])
        existing.append({
            "thread_id": t_id,
            "subject": thread.get("subject"),
            "recipient": thread.get("from") or thread.get("sender"),
            "approved_draft": draft_text,
            "timestamp": datetime.now().isoformat(),
            "sent_via_gmail": sent_via_gmail,
            "gmail_message_id": gmail_message_id
        })
        with open(approved_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        st.error(f"Failed saving to disk: {e}")

tone_profile = load_json_data("data/tone_profile.json", {"name": "Aaron Francis", "role": "Chief of Staff", "tone": "professional", "formality": "semi-formal", "quirks": []})
approved_drafts = load_json_data("data/approved_drafts.json", [])

# ----------------- SESSION STATE MANAGEMENT -----------------
def _init_session_state():
    defaults = {
        "threads": [],
        "selected_thread_dict": None,
        "current_draft": "",
        "status": "none",
        "edited_draft": "",
        "gmail_query": "is:unread",
        "max_results": 8,
        "inbox_source": "Live Gmail API" if gmail_available else "Triage Demo Threads",
        "source": "Live Gmail API" if gmail_available else "Triage Demo Threads",
        "approved": {},
        "show_send_confirmation": False,
        "pending_approval_draft": "",
        "pending_approval_thread": None,
        "draft_guidance": "",
        "booked": {},
        "sent_threads": set(),
        "pipeline_running": False,
        "pipeline_log": [],
        "drafts": {},
        "current_phase": "Inbox Triage"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.get("persona_name") in (None, ""):
        st.session_state.persona_name = tone_profile.get("name", "Aaron Francis")
    if st.session_state.get("persona_role") in (None, ""):
        st.session_state.persona_role = tone_profile.get("role", "Chief of Staff")
    if st.session_state.get("persona_tone") in (None, ""):
        st.session_state.persona_tone = tone_profile.get("tone", "professional")
    if st.session_state.get("persona_formality") in (None, ""):
        st.session_state.persona_formality = tone_profile.get("formality", "semi-formal")
    if st.session_state.get("persona_signoff") in (None, ""):
        st.session_state.persona_signoff = tone_profile.get("sign_off", "Best regards, Aaron Francis")
    if st.session_state.get("persona_quirks") in (None, ""):
        st.session_state.persona_quirks = "\n".join(tone_profile.get("quirks", []))

_init_session_state()

if st.session_state.get("show_save_toast"):
    st.toast("Persona details updated!", icon="💾")
    st.balloons()
    st.session_state.show_save_toast = False

# API Key handling
groq_api_key = None
try:
    groq_api_key = st.secrets.get("GROQ_API_KEY")
except Exception:
    pass
if not groq_api_key:
    groq_api_key = os.environ.get("GROQ_API_KEY")

# ----------------- DESIGN SYSTEM CSS -----------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600;8..60,700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
        --ink: #F3F4F6;
        --ink-soft: #9CA3AF;
        --paper: #0B0F19;
        --paper-raised: #111827;
        --line: #1F2937;
        --line-soft: #1E293B;
        --amber: #F59E0B;
        --amber-deep: #D97706;
        --blue: #3B82F6;
        --moss: #10B981;
        --rust: #EF4444;
        --muted: #4B5563;
    }

    /* Base Reset */
    .stApp, [data-testid="stAppViewContainer"] {
        background-color: var(--paper) !important;
        background-image: linear-gradient(var(--line-soft) 1px, transparent 1px);
        background-size: 100% 38px;
        font-family: 'Inter', sans-serif !important;
        color: var(--ink) !important;
    }

    [data-testid="stMain"], [data-testid="stAppViewBlockContainer"], .main, .block-container, .stMain {
        background: transparent !important;
    }

    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1rem !important;
        max-width: 1440px !important;
    }

    /* Hide default Streamlit header and menu */
    #MainMenu, header, footer, [data-testid="stHeader"] {
        visibility: hidden !important;
        height: 0 !important;
        opacity: 0 !important;
        display: none !important;
    }

    /* Typography */
    h1, h2, h3, h4, h5, h6 {
        color: var(--ink) !important;
        font-family: 'Source Serif 4', serif !important;
        letter-spacing: -0.01em;
    }

    .stApp p, .stApp label, .stApp li, .stApp ul, .stApp ol,
    .stApp strong, .stApp b, .stApp small, .stApp code, .stApp details, .stApp summary {
        color: var(--ink) !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* ---------- MASTHEAD ---------- */
    .stApp .masthead {
        background: var(--paper-raised) !important;
        border: 1px solid var(--ink) !important;
        border-radius: 2px !important;
        padding: 20px 30px !important;
        margin-bottom: 20px !important;
        box-shadow: 4px 4px 0 rgba(20, 17, 15, 0.06) !important;
    }
    .stApp .masthead-title {
        font-family: 'Source Serif 4', serif !important;
        font-weight: 700 !important;
        font-size: 1.8rem !important;
        margin: 0 !important;
        color: var(--ink) !important;
        display: flex !important;
        align-items: baseline !important;
        gap: 10px !important;
    }
    .stApp .masthead-rule {
        height: 2px !important;
        background: var(--ink) !important;
        margin: 8px 0 4px 0 !important;
        opacity: 0.92 !important;
    }
    .stApp .masthead-sub {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.7rem !important;
        letter-spacing: 0.09em !important;
        text-transform: uppercase !important;
        color: var(--muted) !important;
        margin: 0 !important;
    }
    .stApp .masthead-stats { 
        display: flex !important; 
        gap: 28px !important; 
        justify-content: flex-end !important; 
        flex-wrap: wrap !important; 
    }
    .stApp .mh-stat { 
        text-align: right !important; 
        min-width: 86px !important; 
    }
    .stApp .mh-stat-val {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        color: var(--ink) !important;
        line-height: 1.1 !important;
    }
    .stApp .mh-stat-val.online { color: var(--moss) !important; }
    .stApp .mh-stat-val.offline { color: var(--rust) !important; }
    .stApp .mh-stat-lbl {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.62rem !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        color: var(--muted) !important;
        margin-top: 2px !important;
    }

    /* ---------- THREE-PANE LAYOUT ---------- */
    [data-testid="column"] {
        background: var(--paper-raised) !important;
        border: 1px solid var(--line) !important;
        border-radius: 2px !important;
        padding: 20px !important;
        box-shadow: 2px 2px 0 rgba(20, 17, 15, 0.03) !important;
        margin-bottom: 0 !important;
        max-height: 82vh !important;
        overflow-y: auto !important;
    }
    [data-testid="column"] [data-testid="column"] {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        box-shadow: none !important;
        margin-bottom: 0 !important;
        max-height: none !important;
        overflow-y: visible !important;
    }

    .stApp .pane-header {
        font-family: 'Source Serif 4', serif !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        color: var(--ink) !important;
        margin: 0 0 12px 0 !important;
        padding-bottom: 10px !important;
        border-bottom: 1px solid var(--ink) !important;
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
    }
    .stApp .pane-empty {
        text-align: center !important;
        padding: 60px 18px !important;
        color: var(--muted) !important;
        font-family: 'Source Serif 4', serif !important;
        font-style: italic !important;
        font-size: 0.95rem !important;
        line-height: 1.5 !important;
    }

    /* ---------- INPUTS ---------- */
    .stApp input, .stApp textarea {
        color: var(--ink) !important;
        background-color: var(--paper-raised) !important;
        border: 1px solid var(--line) !important;
        border-radius: 2px !important;
        font-family: 'Inter', sans-serif !important;
        caret-color: var(--ink) !important;
    }
    .stApp input:focus, .stApp textarea:focus {
        border-color: var(--amber) !important;
        box-shadow: 0 0 0 1px var(--amber) !important;
    }
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input {
        color: var(--ink) !important;
        background-color: var(--paper-raised) !important;
        caret-color: var(--ink) !important;
    }
    
    /* Disabled and read-only textareas/inputs */
    .stApp textarea:disabled,
    .stApp input:disabled,
    .stApp [disabled] textarea,
    .stApp [disabled] input,
    .stApp [data-disabled="true"] textarea,
    .stApp [data-disabled="true"] input,
    .stApp [data-baseweb="textarea"] textarea:disabled,
    .stApp [data-baseweb="input"] input:disabled {
        color: var(--ink-soft) !important;
        -webkit-text-fill-color: var(--ink-soft) !important;
        background-color: var(--line-soft) !important;
    }

    [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span {
        color: var(--ink-soft) !important;
        font-weight: 600 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.7rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Selectbox */
    [data-baseweb="select"] > div {
        background-color: var(--paper-raised) !important;
        border: 1px solid var(--line) !important;
        border-radius: 2px !important;
    }
    [data-baseweb="select"] div, [data-baseweb="select"] span, [data-baseweb="select"] input {
        color: var(--ink) !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* Tabs */
    [data-baseweb="tab-list"] { gap: 12px !important; border-bottom: 1px solid var(--line) !important; }
    [data-baseweb="tab-list"] button { background-color: transparent !important; }
    .stApp [data-baseweb="tab"] p, .stApp [data-baseweb="tab"] span {
        color: var(--muted) !important;
        font-weight: 600 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
    }
    .stApp [data-baseweb="tab"][aria-selected="true"] p, .stApp [data-baseweb="tab"][aria-selected="true"] span {
        color: var(--amber-deep) !important;
    }
    [data-baseweb="tab-highlight"] { background-color: var(--amber) !important; }

    /* ---------- BUTTONS ---------- */
    .stButton button, [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {
        border-radius: 2px !important;
        transition: all 0.15s ease-in-out !important;
        font-weight: 600 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.75rem !important;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .stApp [data-testid="stBaseButton-primary"], .stApp .stButton button[kind="primary"] {
        background-color: var(--moss) !important;
        border: 1px solid var(--moss) !important;
    }
    .stApp [data-testid="stBaseButton-primary"]:hover, .stApp .stButton button[kind="primary"]:hover {
        background-color: #4A583E !important;
        border-color: #4A583E !important;
    }
    .stApp [data-testid="stBaseButton-secondary"], .stApp .stButton button[kind="secondary"] {
        background-color: var(--paper-raised) !important;
        border: 1px solid var(--line) !important;
    }
    .stApp [data-testid="stBaseButton-secondary"]:hover, .stApp .stButton button[kind="secondary"]:hover {
        background-color: var(--line-soft) !important;
        border-color: var(--ink) !important;
    }
    .stApp [data-testid="stBaseButton-primary"] * { color: var(--paper) !important; }
    .stApp [data-testid="stBaseButton-secondary"] * { color: var(--ink-soft) !important; }

    /* Fix action button texts inside nested columns so they do not wrap or truncate */
    div[data-testid="column"] div[data-testid="column"] button {
        padding: 6px 12px !important;
        min-width: 0 !important;
        width: 100% !important;
        min-height: 0 !important;
    }
    div[data-testid="column"] div[data-testid="column"] button *,
    div[data-testid="column"] div[data-testid="column"] button span,
    div[data-testid="column"] div[data-testid="column"] button p {
        white-space: nowrap !important;
        word-break: keep-all !important;
        word-wrap: normal !important;
        font-size: 0.72rem !important;
        letter-spacing: 0.01em !important;
        text-align: center !important;
    }

    /* Force download button text color */
    .stApp [data-testid="stDownloadButton"] button,
    .stApp [data-testid="stDownloadButton"] button *,
    .stApp [data-testid="stDownloadButton"] button span,
    .stApp [data-testid="stDownloadButton"] button p {
        color: var(--ink-soft) !important;
        background-color: var(--paper-raised) !important;
    }
    .stApp [data-testid="stDownloadButton"] button:hover,
    .stApp [data-testid="stDownloadButton"] button:hover *,
    .stApp [data-testid="stDownloadButton"] button:hover span,
    .stApp [data-testid="stDownloadButton"] button:hover p {
        color: var(--ink) !important;
        background-color: var(--line-soft) !important;
    }

    /* Expander Stylings - Force high contrast headers */
    [data-testid="stExpander"],
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] summary {
        background-color: var(--paper-raised) !important;
        color: var(--ink) !important;
        border-color: var(--line) !important;
    }
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span {
        color: var(--ink) !important;
        font-weight: 600 !important;
    }

    /* ---------- COLUMN 1 LEDGER CARDS ---------- */
    [data-testid="column"]:nth-of-type(1) [data-testid="stBaseButton-secondary"],
    [data-testid="column"]:nth-of-type(1) button {
        text-align: left !important;
        justify-content: flex-start !important;
        background-color: var(--paper-raised) !important;
        border: 1px solid var(--line) !important;
        border-radius: 4px !important;
        padding: 12px 14px !important;
        margin-bottom: 10px !important;
        width: 100% !important;
        color: var(--ink-soft) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        line-height: 1.45 !important;
        box-shadow: 2px 2px 4px rgba(20, 17, 15, 0.02) !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        transition: all 0.2s ease-in-out !important;
    }
    [data-testid="column"]:nth-of-type(1) [data-testid="stBaseButton-secondary"]:hover,
    [data-testid="column"]:nth-of-type(1) button:hover {
        background-color: var(--line-soft) !important;
        border-color: var(--amber) !important;
        color: var(--ink) !important;
    }
    [data-testid="column"]:nth-of-type(1) [data-testid="stBaseButton-primary"],
    [data-testid="column"]:nth-of-type(1) button[kind="primary"] {
        text-align: left !important;
        justify-content: flex-start !important;
        background-color: var(--ink) !important;
        border: 1px solid var(--ink) !important;
        border-radius: 4px !important;
        padding: 12px 14px !important;
        margin-bottom: 10px !important;
        width: 100% !important;
        color: var(--paper) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        line-height: 1.45 !important;
        box-shadow: 2px 2px 6px rgba(20, 17, 15, 0.08) !important;
        text-transform: none !important;
        letter-spacing: normal !important;
    }
    [data-testid="column"]:nth-of-type(1) [data-testid="stBaseButton-primary"]:hover,
    [data-testid="column"]:nth-of-type(1) button[kind="primary"]:hover {
        background-color: var(--amber-deep) !important;
        border-color: var(--amber-deep) !important;
        color: var(--paper) !important;
    }
    [data-testid="column"]:nth-of-type(1) button *,
    [data-testid="column"]:nth-of-type(1) button span,
    [data-testid="column"]:nth-of-type(1) button p {
        white-space: pre-line !important;
        text-align: left !important;
        word-break: break-word !important;
        font-size: 0.82rem !important;
    }
    [data-testid="column"]:nth-of-type(1) [data-testid="stBaseButton-primary"] *,
    [data-testid="column"]:nth-of-type(1) [data-testid="stBaseButton-primary"] span,
    [data-testid="column"]:nth-of-type(1) [data-testid="stBaseButton-primary"] p {
        color: var(--paper) !important;
    }

    /* ---------- CORRESPONDENCE BUBBLES ---------- */
    .thread-scroll { max-height: 520px; overflow-y: auto; padding-right: 6px; }
    .incoming-bubble {
        background: var(--paper-raised) !important;
        border: 1px solid var(--line) !important;
        border-left: 3.5px solid var(--blue) !important;
        border-radius: 2px !important;
        padding: 12px 14px !important;
        margin-bottom: 10px !important;
    }
    .outgoing-bubble {
        background: #1E293B !important;
        border: 1px solid var(--line) !important;
        border-left: 3.5px solid var(--moss) !important;
        border-radius: 2px !important;
        padding: 12px 14px !important;
        margin-bottom: 10px !important;
        margin-left: 20px;
    }
    .stApp .bubble-header {
        display: flex !important;
        justify-content: space-between !important;
        font-weight: 600 !important;
        font-size: 0.75rem !important;
        margin-bottom: 6px !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    .stApp .incoming-bubble .bubble-header, .stApp .incoming-bubble .bubble-header span { color: var(--blue) !important; }
    .stApp .outgoing-bubble .bubble-header, .stApp .outgoing-bubble .bubble-header span { color: var(--moss) !important; }
    .stApp .bubble-date { color: var(--muted) !important; font-size: 0.65rem !important; }
    .stApp .bubble-body {
        font-size: 0.88rem !important;
        line-height: 1.5 !important;
        white-space: pre-wrap !important;
        color: var(--ink-soft) !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* ---------- DRAFT / LETTERHEAD ---------- */
    .stApp .draft-letterhead {
        background: var(--paper-raised) !important;
        border: 1px solid var(--ink) !important;
        border-radius: 2px !important;
        padding: 0 !important;
        margin-bottom: 12px !important;
        box-shadow: 3px 3px 0 rgba(20, 17, 15, 0.05) !important;
        overflow: hidden;
    }
    .stApp .draft-letterhead-bar {
        background: var(--ink) !important;
        color: var(--paper) !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.62rem !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        padding: 6px 14px !important;
    }
    .stApp .draft-letterhead-body {
        padding: 16px 18px !important;
        font-size: 0.9rem !important;
        line-height: 1.6 !important;
        color: var(--ink) !important;
        white-space: pre-wrap !important;
        max-height: 300px !important;
        overflow-y: auto !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* ---------- MARGINALIA / AUDIT ---------- */
    .stApp .marginalia {
        display: flex !important;
        align-items: flex-start !important;
        justify-content: space-between !important;
        gap: 10px !important;
        padding: 8px 0 !important;
        border-bottom: 1px dashed var(--line) !important;
        font-size: 0.8rem !important;
    }
    .stApp .marginalia:last-child { border-bottom: none !important; }
    .stApp .marginalia-label { color: var(--ink-soft) !important; font-weight: 500 !important; }
    .stApp .marginalia-mark {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.7rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.04em !important;
    }

    /* ---------- STATUS STAMP ---------- */
    .stApp .stamp {
        display: inline-flex !important;
        align-items: center !important;
        gap: 6px !important;
        padding: 3px 9px !important;
        border-radius: 2px !important;
        font-size: 0.62rem !important;
        font-weight: 700 !important;
        font-family: 'JetBrains Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        border: 1px solid currentColor !important;
    }
    .stApp .stamp-approved { color: var(--moss) !important; background: rgba(91,107,79,0.08) !important; }
    .stApp .stamp-rejected { color: var(--rust) !important; background: rgba(178,58,46,0.08) !important; }
    .stApp .stamp-editing  { color: var(--amber-deep) !important; background: rgba(199,112,44,0.08) !important; }
    .stApp .stamp-none     { color: var(--muted) !important; background: rgba(140,132,117,0.08) !important; }

    /* ---------- ARCHIVE ENTRY ---------- */
    .stApp .archive-entry {
        background: var(--paper-raised) !important;
        border: 1px solid var(--line) !important;
        border-radius: 2px !important;
        padding: 10px 12px !important;
        margin-bottom: 8px !important;
    }
    .stApp .archive-entry-top {
        font-size: 0.76rem !important;
        font-weight: 600 !important;
        color: var(--amber-deep) !important;
        display: flex !important;
        justify-content: space-between !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    .stApp .archive-entry-meta { font-size: 0.65rem !important; color: var(--muted) !important; margin: 3px 0 6px 0 !important; font-family: 'JetBrains Mono', monospace !important; }
    .stApp .archive-entry-body {
        font-size: 0.78rem !important;
        font-style: italic !important;
        color: var(--ink-soft) !important;
        line-height: 1.35 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        font-family: 'Source Serif 4', serif !important;
    }

    hr { border-color: var(--line) !important; margin: 10px 0 !important; }

    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(140, 132, 117, 0.3); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(140, 132, 117, 0.5); }
</style>
""", unsafe_allow_html=True)

# Helper function to audit draft rules
def check_draft_rules(draft: str) -> dict:
    if not draft:
        return {}
    fluff_phrases = [
        "hope this email finds you well",
        "thank you for reaching out",
        "appreciate your message",
        "looking forward to hearing from you"
    ]
    detected_fluff = [p for p in fluff_phrases if p in draft.lower()]
    sentences = [s.strip() for s in draft.split('.') if s.strip()]
    sentence_count = len(sentences)
    length_ok = sentence_count <= 5
    has_signoff = "aaron francis" in draft.lower() or "best regards" in draft.lower()

    return {
        "fluff_free": len(detected_fluff) == 0,
        "fluff_list": detected_fluff,
        "length_ok": length_ok,
        "sentence_count": sentence_count,
        "has_signoff": has_signoff
    }

def format_confirmation_email(topic, start_time_str, duration_minutes, attendees, calendar_link, sign_off):
    try:
        from datetime import datetime
        naive_str = start_time_str
        if "Z" in naive_str:
            naive_str = naive_str.replace("Z", "")
        if "+" in naive_str:
            naive_str = naive_str.split("+")[0]
        dt = datetime.fromisoformat(naive_str)
        formatted_time = dt.strftime("%A, %d %B at %I:%M %p")
    except Exception:
        formatted_time = start_time_str
        
    body = (
        f"Hi,\n\n"
        f"I have scheduled our meeting \"{topic}\" on Google Calendar for {formatted_time}.\n\n"
        f"You should receive a calendar invitation shortly. You can also view it here: {calendar_link}\n\n"
        f"{sign_off}"
    )
    return body

def send_email_action(thread, draft_text):
    t_id = thread.get("thread_id") or thread.get("id")
    sent_flag = False
    sent_id = None
    
    is_demo = str(t_id).startswith("demo_") or str(t_id).startswith("thread_")
    if gmail_available and not is_demo:
        last_msg_id = None
        if thread.get("messages"):
            last_msg_id = thread["messages"][-1].get("id") or thread.get("last_message_id")
        
        with st.spinner("Delivering reply via Gmail..."):
            try:
                send_fn = _get_send_reply()
                if send_fn:
                    sent_id = send_fn(
                        thread_id=t_id,
                        message_id=last_msg_id,
                        reply_text=draft_text
                    )
                if sent_id:
                    sent_flag = True
                else:
                    st.error("Gmail client failed to send the reply. Check console logs.")
            except Exception as err:
                st.error(f"Gmail Send Error: {err}")
    elif is_demo:
        if gmail_available:
            with st.spinner("Delivering demo test email to your Gmail inbox..."):
                try:
                    profile = gmail_client.service.users().getProfile(userId='me').execute()
                    my_email = profile.get('emailAddress')
                    if my_email:
                        from email.mime.text import MIMEText
                        import base64
                        
                        test_subject = f"[Demo Reply] Re: {thread.get('subject', 'Demo Thread')}"
                        test_body = f"""--- DEMO TEST EMAIL SENT BY INBOX COPILOT ---
Original Sender: {thread.get('from') or thread.get('sender')}
Original Subject: {thread.get('subject')}

Approved Reply:
--------------------------------------------------
{draft_text}
--------------------------------------------------
"""
                        msg = MIMEText(test_body)
                        msg['to'] = my_email
                        msg['subject'] = test_subject
                        
                        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                        
                        sent = gmail_client.service.users().messages().send(
                            userId='me',
                            body={'raw': raw}
                        ).execute()
                        
                        if sent and sent.get('id'):
                            sent_flag = True
                            sent_id = sent.get('id')
                        else:
                            st.error("Failed to send demo test mail.")
                    else:
                        st.error("Could not retrieve your Gmail address for demo sending.")
                except Exception as err:
                    st.error(f"Gmail Demo Send Error: {err}")
        else:
            st.info("Demo Mode: Simulated mail delivery (Gmail offline).")
            sent_flag = True
            sent_id = "mock_send_id_123"
    else:
        st.error("Gmail Client is offline or unavailable. Cannot send email.")
        
    if sent_flag:
        result = {"id": sent_id}
        if result.get("id"):
            recipient = thread.get("from") or thread.get("sender") or "Unknown"
            log_action(
                action_type="sent",
                thread_subject=thread["subject"],
                detail=recipient,
                action_id=result["id"],
            )
        save_approved_draft(thread, draft_text, sent_via_gmail=gmail_available, gmail_message_id=sent_id)
        if "sent_threads" not in st.session_state:
            st.session_state.sent_threads = set()
        st.session_state.sent_threads.add(t_id)
        st.session_state.status = "approved"
        st.balloons()
        st.toast("Email dispatched successfully via Gmail!", icon="✉️")
        st.rerun()

def save_local_action(thread, draft_text):
    t_id = thread.get("thread_id") or thread.get("id")
    save_approved_draft(thread, draft_text, sent_via_gmail=False, gmail_message_id=None)
    if "sent_threads" not in st.session_state:
        st.session_state.sent_threads = set()
    st.session_state.sent_threads.add(t_id)
    st.session_state.status = "approved"
    st.balloons()
    st.toast("Draft approved and saved locally.", icon="💾")
    st.rerun()

# ----------------- PIPELINE FUNCTIONS -----------------
def load_sample_threads():
    if os.path.exists("data/sample_triage_threads.json"):
        try:
            with open("data/sample_triage_threads.json", "r", encoding="utf-8") as f:
                threads = json.load(f)
                for t in threads:
                    if "id" in t and "thread_id" not in t:
                        t["thread_id"] = t["id"]
                return threads
        except Exception:
            pass
    return []

def fetch_threads_via_engine():
    if not gmail_available or not gmail_client:
        raise ValueError("Gmail client is offline or unavailable.")
    max_results = st.session_state.get("max_results", 8)
    query = st.session_state.get("gmail_query", "is:unread")
    raw_threads = gmail_client.get_inbox_threads(max_results=max_results, query=query)
    threads = []
    for t in raw_threads:
        threads.append({
            "thread_id": t.get("thread_id") or t.get("id"),
            "subject": t.get("subject", "No Subject"),
            "from": t.get("from", "Unknown"),
            "snippet": t.get("snippet", ""),
            "messages": t.get("messages", []),
            "last_message_id": t.get("last_message_id")
        })
    return threads

def triage_threads(threads):
    if groq_api_key:
        return triage_inbox(threads, api_key=groq_api_key)
    else:
        # Mock classification fallbacks
        for idx, t in enumerate(threads):
            if "priority" not in t:
                t["priority"] = "urgent" if idx == 0 else ("needs-reply" if idx < 3 else "fyi")
            if "category" not in t:
                t["category"] = "admin" if idx == 0 else "meeting request"
            if "reason" not in t:
                t["reason"] = "Demo fallback classification"
        return threads

def _get_draft_reply(thread):
    if not groq_api_key:
        raise ValueError("Groq API key not found.")
    active_tone_profile = {
        "name": st.session_state.get("persona_name", "Aaron Francis"),
        "role": st.session_state.get("persona_role", "Chief of Staff"),
        "tone": st.session_state.get("persona_tone", "professional"),
        "formality": st.session_state.get("persona_formality", "semi-formal"),
        "sign_off": st.session_state.get("persona_signoff", "Best regards, Aaron Francis"),
        "quirks": [q.strip() for q in st.session_state.get("persona_quirks", "").split("\n") if q.strip()]
    }
    return draft_reply(
        thread,
        api_key=groq_api_key,
        tone_profile=active_tone_profile,
        guidance=st.session_state.get("draft_guidance", "")
    )

def run_full_pipeline():
    log = []
    try:
        # 1. Read source
        source = st.session_state.get("source", "Triage Demo Threads")
        log.append(f"Source determined: {source}")
        
        # 2. Fetch
        if source == "Live Gmail API":
            log.append("Fetching threads from Live Gmail API...")
            threads = fetch_threads_via_engine()
        else:
            log.append("Loading sample threads...")
            threads = load_sample_threads()
        log.append(f"Fetched {len(threads)} threads.")
    except Exception as e:
        log.append(f"ERROR: Fetch failed: {e}")
        return log

    try:
        # 3. Triage
        log.append("Triaging threads...")
        threads = triage_threads(threads)
        st.session_state.threads = threads
        priorities = [t.get("priority", "unknown").lower() for t in threads]
        log.append(f"Triaged: {priorities.count('urgent')} urgent, {priorities.count('needs-reply')} needs-reply, {priorities.count('fyi')} fyi, {priorities.count('ignore')} ignore.")
    except Exception as e:
        log.append(f"ERROR: Triage failed: {e}")
        return log

    # 4. Reset downstream state
    st.session_state.drafts = {}
    st.session_state.approved = {}
    st.session_state.rejected = {}
    st.session_state.sent = set()
    st.session_state.sent_threads = set()
    st.session_state.booked = {}
    st.session_state.selected_thread_dict = None
    st.session_state.current_draft = ""
    st.session_state.status = "none"
    log.append("Reset downstream session state (drafts, approved, rejected, sent, booked).")

    # 5. Draft loop
    to_draft = [t for t in threads if t.get("priority", "").lower() in ["urgent", "needs-reply"]]
    total_to_draft = len(to_draft)
    drafts_count = 0
    
    for idx, thread in enumerate(to_draft):
        t_id = thread.get("thread_id") or thread.get("id")
        subject = thread.get("subject", "No Subject")
        log.append(f"Drafting {idx+1}/{total_to_draft}: {subject}...")
        try:
            draft_text = _get_draft_reply(thread)
            st.session_state.drafts[t_id] = draft_text
            drafts_count += 1
            log.append(f"Draft {idx+1}/{total_to_draft}: {subject} ...done")
        except Exception as e:
            log.append(f"ERROR: Draft {idx+1}/{total_to_draft} failed for '{subject}': {e}")
            
    # Auto-select the first thread for approval gate if available
    if to_draft:
        st.session_state.selected_thread_dict = to_draft[0]
        st.session_state.current_draft = st.session_state.drafts.get(to_draft[0].get("thread_id") or to_draft[0].get("id"), "")

    st.session_state.current_phase = "Approval Gate"
    log.append(f"Pipeline complete! {drafts_count} drafts ready for review.")
    return log

def _render_pipeline_execution():
    pipeline_log = []
    source = st.session_state.get("source", "Triage Demo Threads")
    pipeline_log.append(f"Starting pipeline. Source: {source}")
    
    # We will use st.status
    with st.status("Running full pipeline...", expanded=True) as status:
        # Step 1: Fetch
        status.update(label="Fetching threads...", state="running")
        threads = []
        try:
            if source == "Live Gmail API":
                threads = fetch_threads_via_engine()
            else:
                threads = load_sample_threads()
            st.write(f"✔️ Fetched {len(threads)} threads.")
            pipeline_log.append(f"Fetched {len(threads)} threads.")
        except Exception as e:
            st.write(f"❌ Fetch failed: {e}")
            pipeline_log.append(f"ERROR: Fetch failed: {e}")
            status.update(label="Pipeline failed during fetch.", state="error")
            st.session_state.pipeline_running = False
            st.session_state.pipeline_log = pipeline_log
            return

        # Step 2: Triage
        status.update(label="Triaging threads...", state="running")
        try:
            threads = triage_threads(threads)
            st.session_state.threads = threads
            priorities = [t.get("priority", "unknown").lower() for t in threads]
            urgent_count = priorities.count("urgent")
            needs_reply_count = priorities.count("needs-reply")
            fyi_count = priorities.count("fyi")
            ignore_count = priorities.count("ignore")
            st.write(f"✔️ Triaged: {urgent_count} urgent, {needs_reply_count} needs-reply, {fyi_count} fyi, {ignore_count} ignore.")
            pipeline_log.append(f"Triaged: {urgent_count} urgent, {needs_reply_count} needs-reply, {fyi_count} fyi, {ignore_count} ignore.")
        except Exception as e:
            st.write(f"❌ Triage failed: {e}")
            pipeline_log.append(f"ERROR: Triage failed: {e}")
            status.update(label="Pipeline failed during triage.", state="error")
            st.session_state.pipeline_running = False
            st.session_state.pipeline_log = pipeline_log
            return

        # Reset downstream session state
        st.session_state.drafts = {}
        st.session_state.approved = {}
        st.session_state.rejected = {}
        st.session_state.sent = set()
        st.session_state.sent_threads = set()
        st.session_state.booked = {}
        st.session_state.selected_thread_dict = None
        st.session_state.current_draft = ""
        st.session_state.status = "none"
        pipeline_log.append("Reset downstream session state (drafts, approved, rejected, sent, booked).")

        # Step 3: Draft Loop
        to_draft = [t for t in threads if t.get("priority", "").lower() in ["urgent", "needs-reply"]]
        total_to_draft = len(to_draft)
        status.update(label=f"Drafting replies (0/{total_to_draft})...", state="running")
        
        drafts_count = 0
        for idx, thread in enumerate(to_draft):
            t_id = thread.get("thread_id") or thread.get("id")
            subject = thread.get("subject", "No Subject")
            status.update(label=f"Drafting replies ({idx+1}/{total_to_draft}): {subject}...", state="running")
            try:
                draft_text = _get_draft_reply(thread)
                st.session_state.drafts[t_id] = draft_text
                drafts_count += 1
                st.write(f"✔️ Drafted {idx+1}/{total_to_draft}: {subject}")
                pipeline_log.append(f"Draft {idx+1}/{total_to_draft}: {subject} ...done")
            except Exception as e:
                st.write(f"❌ Failed drafting {idx+1}/{total_to_draft} ({subject}): {e}")
                pipeline_log.append(f"ERROR: Draft {idx+1}/{total_to_draft} failed for '{subject}': {e}")
        
        # Auto-select the first thread for approval gate if available
        if to_draft:
            st.session_state.selected_thread_dict = to_draft[0]
            st.session_state.current_draft = st.session_state.drafts.get(to_draft[0].get("thread_id") or to_draft[0].get("id"), "")

        status.update(label=f"Pipeline complete! {drafts_count} drafts ready for review.", state="complete")
        pipeline_log.append(f"Pipeline complete! {drafts_count} drafts ready for review.")
        
    st.session_state.pipeline_log = pipeline_log
    st.session_state.current_phase = "Approval Gate"
    st.session_state.pipeline_running = False
    st.rerun()

def render_approval_phase(thread):
    t_id = thread.get("thread_id") or thread.get("id")
    
    if "sent_threads" not in st.session_state:
        st.session_state.sent_threads = set()
        
    is_approved = (t_id in st.session_state.approved or st.session_state.status == "approved")
    is_sent = (t_id in st.session_state.sent_threads)
    
    if not is_sent:
        for d in approved_drafts:
            if d.get("thread_id") == t_id and d.get("sent_via_gmail"):
                st.session_state.sent_threads.add(t_id)
                is_sent = True
                break

    category = (thread.get("_category") or thread.get("category") or "").lower().strip()
    is_meeting = (category == "meeting-request" or category == "meeting request" or "meeting" in category or "schedule" in category or "calendar" in category or "booking" in category)

    pipeline_log = st.session_state.get("pipeline_log", [])
    if pipeline_log:
        with st.expander("Pipeline Execution Log", expanded=False):
            for entry in pipeline_log:
                if "ERROR" in entry or "FAILED" in entry:
                    st.write(f"❌ {entry}")
                else:
                    st.write(f"✔️ {entry}")
            if st.button("Clear log", key="clear_pipeline_log_btn", use_container_width=True):
                st.session_state.pipeline_log = []
                st.rerun()
        st.divider()

    if not is_approved:
        st.markdown("<p style='font-family: \"JetBrains Mono\", monospace; font-size: 0.75rem; text-transform: uppercase; color: var(--muted); margin-bottom: 8px;'>Action Required</p>", unsafe_allow_html=True)
        
        act_row1_col1, act_row1_col2 = st.columns(2)
        with act_row1_col1:
            if st.button("Approve", use_container_width=True, type="primary"):
                st.session_state.approved[t_id] = st.session_state.current_draft
                if send_on_approve and not is_meeting:
                    st.session_state.pending_approval_draft = st.session_state.current_draft
                    st.session_state.pending_approval_thread = thread
                    st.session_state.show_send_confirmation = True
                else:
                    st.session_state.status = "approved"
                st.rerun()
        with act_row1_col2:
            if st.button("Edit", use_container_width=True):
                st.session_state.status = "editing"
                st.session_state.edited_draft = st.session_state.current_draft
                st.rerun()
                
        act_row2_col1, act_row2_col2 = st.columns(2)
        with act_row2_col1:
            if st.button("Regen", use_container_width=True):
                with st.spinner("Regenerating draft..."):
                    try:
                        active_tone_profile = {
                            "name": st.session_state.get("persona_name", "Aaron Francis"),
                            "role": st.session_state.get("persona_role", "Chief of Staff"),
                            "tone": st.session_state.get("persona_tone", "professional"),
                            "formality": st.session_state.get("persona_formality", "semi-formal"),
                            "sign_off": st.session_state.get("persona_signoff", "Best regards, Aaron Francis"),
                            "quirks": [q.strip() for q in st.session_state.get("persona_quirks", "").split("\n") if q.strip()]
                        }
                        st.session_state.current_draft = draft_reply(
                            thread,
                            api_key=groq_api_key,
                            tone_profile=active_tone_profile,
                            guidance=st.session_state.get("draft_guidance", "")
                        )
                        st.session_state.status = "none"
                        st.toast("Draft regenerated", icon="🔄")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Regen failed: {err}")
        with act_row2_col2:
            if st.button("Reject", use_container_width=True):
                st.session_state.status = "rejected"
                st.toast("Draft discarded", icon="❌")
                st.rerun()
                
    elif is_approved and not is_sent:
        if is_meeting:
            st.warning("Draft approved! Since this is a meeting request, you can book the event and/or dispatch the email.")
            
            is_booked = t_id in st.session_state.booked
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("Send Email", use_container_width=True, type="primary"):
                    send_email_action(thread, st.session_state.current_draft)
            with btn_col2:
                if is_booked:
                    event_info = st.session_state.booked[t_id]
                    html_link = event_info.get("htmlLink", "#")
                    st.markdown(f"""
                    <div style='text-align: center; padding: 6px; border: 1px solid var(--moss); background: rgba(72,202,228,0.1); border-radius: 2px;'>
                        <a href='{html_link}' target='_blank' style='color: var(--moss); text-decoration: none; font-weight: 600; font-family: "JetBrains Mono", monospace; font-size: 0.72rem;'>📅 VIEW IN GOOGLE CALENDAR</a>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    if st.button("Book Meeting", use_container_width=True):
                        try:
                            with st.spinner("Parsing meeting request details..."):
                                cal_eng = _get_calendar_engine()
                                draft_text = st.session_state.approved.get(t_id) or st.session_state.get("current_draft")
                                parsed = cal_eng.parse_meeting_request(thread, draft_text)
                                
                            if "parsing_error" in parsed:
                                st.error(f"Failed to parse meeting details: {parsed['parsing_error']}")
                            else:
                                st.info(f"**Topic:** {parsed['topic']}\n\n**Duration:** {parsed['duration_minutes']} min\n\n**Attendees:** {', '.join(parsed['attendees'])}")
                                
                                with st.spinner("Checking primary calendar availability..."):
                                    free_slot = cal_eng.find_free_slot(
                                        parsed["proposed_times"],
                                        parsed["duration_minutes"]
                                    )
                                    
                                if not free_slot:
                                    st.error("No available slots found for the proposed times.")
                                else:
                                    st.success(f"Available slot found: {free_slot}")
                                    
                                    with st.spinner("Scheduling event on Google Calendar..."):
                                        event = cal_eng.create_event(
                                            summary=parsed["topic"],
                                            start_time=free_slot,
                                            duration_minutes=parsed["duration_minutes"],
                                            attendees=parsed["attendees"],
                                            description=f"Auto-scheduled by Inbox Copilot for thread: {thread.get('subject')}"
                                        )
                                        
                                        st.session_state.booked[t_id] = event
                                        if event.get("id"):
                                            meeting_info = parsed
                                            if "title" not in meeting_info and "topic" in meeting_info:
                                                meeting_info["title"] = meeting_info["topic"]
                                            log_action(
                                                action_type="booked",
                                                thread_subject=thread["subject"],
                                                detail=meeting_info.get("title", thread["subject"]),
                                                action_id=event["id"],
                                            )
                                        st.success("Meeting booked successfully!")
                                        
                                        # Auto-send confirmation email
                                        sign_off = st.session_state.get("persona_signoff", "Best Regards, Aaron Francis")
                                        confirmation_body = format_confirmation_email(
                                            topic=parsed["topic"],
                                            start_time_str=free_slot,
                                            duration_minutes=parsed["duration_minutes"],
                                            attendees=parsed["attendees"],
                                            calendar_link=event.get("htmlLink", ""),
                                            sign_off=sign_off
                                        )
                                        
                                        send_email_action(thread, confirmation_body)
                                        st.rerun()
                        except Exception as e:
                            st.error(f"Error booking meeting: {e}")
                            
            st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
            if st.button("Archive Without Sending", use_container_width=True):
                save_local_action(thread, st.session_state.current_draft)
        else:
            st.info("Draft approved! Dispatch via Gmail or archive locally.")
            col_send1, col_send2 = st.columns(2)
            with col_send1:
                if st.button("Send via Gmail", use_container_width=True, type="primary"):
                    send_email_action(thread, st.session_state.current_draft)
            with col_send2:
                if st.button("Save Local Only", use_container_width=True):
                    save_local_action(thread, st.session_state.current_draft)
                    
    else:
        st.success("Draft approved and archived.")
        if is_meeting and t_id in st.session_state.booked:
            event_info = st.session_state.booked[t_id]
            html_link = event_info.get("htmlLink", "#")
            st.markdown(f"""
            <div style='text-align: center; padding: 10px; border: 1px solid var(--moss); background: rgba(72,202,228,0.1); border-radius: 2px; margin-bottom: 12px;'>
                <a href='{html_link}' target='_blank' style='color: var(--moss); text-decoration: none; font-weight: 600; font-family: "JetBrains Mono", monospace;'>📅 VIEW IN GOOGLE CALENDAR</a>
            </div>
            """, unsafe_allow_html=True)
            
        if st.button("Start New Reply", use_container_width=True):
            st.session_state.status = "none"
            st.session_state.current_draft = ""
            st.rerun()


send_on_approve = True

def render_sidebar():
    with st.sidebar:
        st.title("The Desk")
        st.caption("Ghostwriter's Command Console")
        st.divider()
        if not gmail_available and gmail_error:
            st.error(f"⚠️ **Gmail Connection Failed**\n\n`{gmail_error}`")
            st.markdown("""
            **Troubleshooting Steps:**
            1. Go to your Streamlit Cloud dashboard: **Settings** -> **Secrets**.
            2. Verify you have defined the `GMAIL_CREDENTIALS` key.
            3. Ensure it is a valid JSON string (matching your local `~/.gmail-mcp/credentials.json` token content).
            4. If running locally, check that `gcp-oauth.keys.json` is located in your `Gmail-MCP-Server/` folder or home directory `~/.gmail-mcp/`.
            """)
            st.divider()
        if st.button("Run Full Pipeline", type="primary", use_container_width=True):
            st.session_state.pipeline_running = True
            st.rerun()
        st.caption("Fetches, triages, and drafts -- stops at Approval Gate.")

def render_phase():
    global send_on_approve
    if st.session_state.selected_thread_dict:
        t_id = st.session_state.selected_thread_dict.get("thread_id") or st.session_state.selected_thread_dict.get("id")
        if not st.session_state.current_draft and t_id in st.session_state.get("drafts", {}):
            st.session_state.current_draft = st.session_state.drafts[t_id]
    # ----------------- MASTHEAD -----------------
    gmail_status_class = "online" if gmail_available else "offline"
    gmail_status_text = "LINKED" if gmail_available else "OFFLINE"
    total_deliverables = len(st.session_state.approved)

    st.markdown(f"""
    <div class='masthead'>
        <table style='width: 100%; border-collapse: collapse; border: none; background: transparent;'>
            <tr style='border: none; background: transparent;'>
                <td style='vertical-align: middle; width: 40%; border: none; background: transparent; padding: 0; text-align: left;'>
                    <p class='masthead-title'>\U0001f58b\ufe0f The Desk</p>
                    <div class='masthead-rule'></div>
                    <p class='masthead-sub'>Ghostwriter's Command Console &middot; Inbox Triage & Reply Automation</p>
                </td>
                <td style='vertical-align: middle; width: 60%; border: none; background: transparent; padding: 0;'>
                    <div class='masthead-stats'>
                        <div class='mh-stat'>
                            <div class='mh-stat-val {gmail_status_class}'>{gmail_status_text}</div>
                            <div class='mh-stat-lbl'>Gmail API</div>
                        </div>
                        <div class='mh-stat'>
                            <div class='mh-stat-val'>{len(st.session_state.threads):02d}</div>
                            <div class='mh-stat-lbl'>Threads</div>
                        </div>
                        <div class='mh-stat'>
                            <div class='mh-stat-val'>{total_deliverables:02d}</div>
                            <div class='mh-stat-lbl'>Deliverables</div>
                        </div>
                        <div class='mh-stat'>
                            <div class='mh-stat-val'>llama-3.3</div>
                            <div class='mh-stat-lbl'>Model \u00b7 Groq</div>
                        </div>
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

    # ----------------- MAIN THREE-PANE WORKSPACE -----------------
    col_inbox, col_thread, col_copilot = st.columns([1.2, 1.8, 1.6], gap="medium")

    # ==================== PANE 1: INBOX LEDGER ====================
    with col_inbox:
        st.markdown("<p class='pane-header'><span>\U0001f4e5 Inbox Ledger</span></p>", unsafe_allow_html=True)

        inbox_source = st.selectbox(
            "Mail Source",
            options=["Live Gmail API", "Triage Demo Threads"],
            index=0 if st.session_state.inbox_source == "Live Gmail API" else 1,
            label_visibility="collapsed"
        )
        if inbox_source != st.session_state.inbox_source:
            st.session_state.inbox_source = inbox_source
            st.session_state.source = inbox_source
            st.rerun()

        if inbox_source == "Live Gmail API":
            st.text_input("Query Filter", key="gmail_query", placeholder="e.g. is:unread")
            st.number_input("Max Results", min_value=1, max_value=25, key="max_results")
        else:
            st.info("Demo Mode: Loaded mock threads representing all priority levels.")

        # Action Buttons
        sync_col, pipe_col = st.columns(2)
        with sync_col:
            sync_clicked = st.button("Sync Inbox & Triage", use_container_width=True)
        with pipe_col:
            run_pipeline_clicked = st.button("Run Full Pipeline", type="primary", use_container_width=True)

        if run_pipeline_clicked:
            st.session_state.pipeline_running = True
            st.rerun()

        if sync_clicked:
            if inbox_source == "Live Gmail API":
                if gmail_available:
                    with st.spinner("Fetching from Gmail..."):
                        try:
                            raw_threads = gmail_client.get_inbox_threads(
                                max_results=st.session_state.max_results,
                                query=st.session_state.gmail_query
                            )
                            threads = []
                            for t in raw_threads:
                                threads.append({
                                    "thread_id": t.get("thread_id") or t.get("id"),
                                    "subject": t.get("subject", "No Subject"),
                                    "from": t.get("from", "Unknown"),
                                    "snippet": t.get("snippet", ""),
                                    "messages": t.get("messages", []),
                                    "last_message_id": t.get("last_message_id")
                                })

                            if threads:
                                if groq_api_key:
                                    with st.spinner("Classifying threads..."):
                                        threads = triage_inbox(threads, api_key=groq_api_key)
                                else:
                                    for idx, t in enumerate(threads):
                                        t["priority"] = "needs-reply"
                                        t["category"] = "other"
                                        t["reason"] = "Missing Groq API Key"

                                st.session_state.threads = threads
                                st.session_state.status = "none"
                                st.session_state.current_draft = ""
                                st.toast(f"Synced {len(st.session_state.threads)} threads", icon="\U0001f4e5")
                                st.rerun()
                            else:
                                st.warning("No threads matching the query were found.")
                        except Exception as e:
                            st.error(f"Gmail Sync Error: {e}")
                else:
                    st.error("Gmail Client offline. Please set up authentication credentials.")
            else:
                with st.spinner("Loading demo threads..."):
                    try:
                        if os.path.exists("data/sample_triage_threads.json"):
                            with open("data/sample_triage_threads.json", "r", encoding="utf-8") as f:
                                threads = json.load(f)
                        else:
                            threads = []

                        if threads:
                            for t in threads:
                                if "id" in t and "thread_id" not in t:
                                    t["thread_id"] = t["id"]

                            if groq_api_key:
                                with st.spinner("Classifying demo threads..."):
                                    threads = triage_inbox(threads, api_key=groq_api_key)
                            else:
                                # Mock classification fallbacks
                                for idx, t in enumerate(threads):
                                    if "priority" not in t:
                                        t["priority"] = "urgent" if idx == 0 else ("needs-reply" if idx < 3 else "fyi")
                                    if "category" not in t:
                                        t["category"] = "admin" if idx == 0 else "meeting request"
                                    if "reason" not in t:
                                        t["reason"] = "Demo fallback classification"

                            st.session_state.threads = threads
                            st.session_state.status = "none"
                            st.session_state.current_draft = ""
                            st.toast(f"Loaded {len(st.session_state.threads)} demo threads", icon="\U0001f4e5")
                            st.rerun()
                        else:
                            st.error("Demo file sample_triage_threads.json is missing or empty.")
                    except Exception as e:
                        st.error(f"Failed loading demo: {e}")

        st.markdown("<hr>", unsafe_allow_html=True)

        # Thread cards list
        if st.session_state.threads:
            priority_emojis = {
                "urgent": "\U0001f534",
                "needs-reply": "\U0001f7e1",
                "fyi": "\U0001f7e2",
                "ignore": "\u26aa",
                "unknown": "\u2753"
            }

            for idx, t in enumerate(st.session_state.threads):
                t_id = t.get("thread_id") or t.get("id")
                p_val = t.get("priority", "unknown").lower()
                p_icon = priority_emojis.get(p_val, "\u2753")
                category = t.get("category", "other").upper()

                sender_raw = t.get("from") or t.get("sender") or "Unknown"
                sender_clean = sender_raw.split("<")[0].strip() if "<" in sender_raw else sender_raw
                sender_clean = sender_clean[:18]

                subj = t.get("subject", "No Subject")
                subj_clean = subj[:22] + "..." if len(subj) > 25 else subj

                snippet = t.get("snippet", "")
                snippet_clean = snippet[:36] + "..." if len(snippet) > 40 else snippet

                # Formatted multiline card label
                card_label = f"{p_icon} [{category}] {sender_clean}\n{subj_clean}\n{snippet_clean}"

                # Determine selection state
                is_active = False
                if st.session_state.selected_thread_dict:
                    is_active = (st.session_state.selected_thread_dict.get("thread_id") == t_id)

                btn_type = "primary" if is_active else "secondary"

                if st.button(card_label, key=f"tcard_{t_id}_{idx}", type=btn_type, use_container_width=True):
                    st.session_state.selected_thread_dict = t
                    st.session_state.status = "none"
                    st.session_state.current_draft = st.session_state.drafts.get(t_id, "")
                    st.rerun()
        else:
            st.markdown("<p class='pane-empty'>No threads loaded.<br>Click 'Sync Inbox & Triage' to begin.</p>", unsafe_allow_html=True)

    # ==================== PANE 2: OPEN LETTER ====================
    with col_thread:
        if not st.session_state.selected_thread_dict:
            st.markdown("<p class='pane-header'><span>\U0001f4ac Open Letter</span></p>", unsafe_allow_html=True)
            st.markdown("<p class='pane-empty'>Select a thread from the ledger on the left to read correspondence logs.</p>", unsafe_allow_html=True)
        else:
            thread = st.session_state.selected_thread_dict
            st.markdown(f"<p class='pane-header'><span>\U0001f4ac {thread.get('subject', 'No Subject')}</span></p>", unsafe_allow_html=True)

            messages_html = "<div class='thread-scroll'>"
            for msg in thread.get("messages", []):
                sender = msg.get("from", "Unknown")
                date = msg.get("date", "Unknown")
                body = msg.get("body", "")

                is_you = "you" in sender.lower() or "aaron" in sender.lower()
                bubble_class = "outgoing-bubble" if is_you else "incoming-bubble"
                avatar = "YOU" if is_you else sender

                messages_html += f"""
                <div class='{bubble_class}'>
                    <div class='bubble-header'>
                        <span>{avatar}</span>
                        <span class='bubble-date'>{date}</span>
                    </div>
                    <div class='bubble-body'>{body}</div>
                </div>
                """
            messages_html += "</div>"
            st.markdown(messages_html, unsafe_allow_html=True)

    # ==================== PANE 3: DRAFTING DESK ====================
    with col_copilot:
        stamp_html = {
            "approved": "<span class='stamp stamp-approved'>Approved</span>",
            "rejected": "<span class='stamp stamp-rejected'>Rejected</span>",
            "editing": "<span class='stamp stamp-editing'>Editing</span>",
        }.get(st.session_state.status, "<span class='stamp stamp-none'>Reviewing</span>")

        st.markdown(f"""
        <p class='pane-header'>
            <span>\U0001f916 Drafting Desk</span>
            {stamp_html}
        </p>
        """, unsafe_allow_html=True)

        if not st.session_state.selected_thread_dict:
            st.markdown("<p class='pane-empty'>No draft loaded.<br>Select an inbox thread to initiate drafting.</p>", unsafe_allow_html=True)
        else:
            thread = st.session_state.selected_thread_dict
            t_id = thread.get("thread_id") or thread.get("id")

            # Custom response guidance / instructions
            guidance = st.text_area(
                "Custom Reply Guidance / Instructions (Optional)",
                key="draft_guidance",
                placeholder="e.g. Say yes but suggest Tuesday instead, or politely decline.",
                height=70
            )

            # Draft generation trigger
            generate_clicked = st.button("Draft Response Reply", use_container_width=True, type="primary")
            send_on_approve = st.toggle("Send via Gmail on approval", value=True, disabled=not gmail_available)

            st.markdown("<hr>", unsafe_allow_html=True)

            if generate_clicked:
                if not groq_api_key:
                    st.error("Groq API Key is missing. Configure in .env or secrets.")
                else:
                    with st.spinner("Drafting in your voice..."):
                        try:
                            active_tone_profile = {
                                "name": st.session_state.get("persona_name", "Aaron Francis"),
                                "role": st.session_state.get("persona_role", "Chief of Staff"),
                                "tone": st.session_state.get("persona_tone", "professional"),
                                "formality": st.session_state.get("persona_formality", "semi-formal"),
                                "sign_off": st.session_state.get("persona_signoff", "Best regards, Aaron Francis"),
                                "quirks": [q.strip() for q in st.session_state.get("persona_quirks", "").split("\n") if q.strip()]
                            }
                            result = draft_reply_with_metadata(
                                thread,
                                api_key=groq_api_key,
                                tone_profile=active_tone_profile,
                                guidance=guidance
                            )
                            st.session_state.current_draft = result["draft"]
                            st.session_state.status = "none"
                            st.toast("Draft response generated", icon="\u2728")
                        except Exception as err:
                            st.error(f"Failed drafting: {err}")

            # View, Edit or Confirm layout
            if not st.session_state.current_draft:
                st.markdown("<p class='pane-empty'>Awaiting response draft.<br>Click 'Draft Response Reply' to begin.</p>", unsafe_allow_html=True)
            else:
                if st.session_state.show_send_confirmation:
                    st.markdown("### \u2709\ufe0f Confirm Delivery")
                    st.write("Do you want to send this finalized email reply via Gmail?")

                    st.markdown(f"""
                    <div class='draft-letterhead'>
                        <div class='draft-letterhead-bar'>Final Approved Correspondence - Ready to Send</div>
                        <div class='draft-letterhead-body'>{st.session_state.pending_approval_draft}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("Yes, Send via Gmail", use_container_width=True, type="primary"):
                        thread = st.session_state.pending_approval_thread
                        draft_text = st.session_state.pending_approval_draft
                        t_id = thread.get("thread_id") or thread.get("id")

                        sent_flag = False
                        sent_id = None

                        # Only send if it is not a demo thread and Gmail is online
                        is_demo = str(t_id).startswith("demo_") or str(t_id).startswith("thread_")
                        recipient = None
                        if gmail_available and not is_demo:
                            last_msg_id = None
                            if thread.get("messages"):
                                last_msg_id = thread["messages"][-1].get("id") or thread.get("last_message_id")

                            with st.spinner("Delivering reply via Gmail..."):
                                try:
                                    sent_id = gmail_client.send_reply(
                                        thread_id=t_id,
                                        message_id=last_msg_id,
                                        reply_text=draft_text
                                    )
                                    if sent_id:
                                        sent_flag = True
                                    else:
                                        st.error("Gmail client failed to send the reply. Check console logs.")
                                except Exception as err:
                                    st.error(f"Gmail Send Error: {err}")
                        elif is_demo:
                            if gmail_available:
                                try:
                                    import email.utils
                                    from_header = thread.get('from') or thread.get('sender') or ''
                                    _, target_email = email.utils.parseaddr(from_header)
                                    
                                    demo_domains = ['company.com', 'cloudhost.com', 'cloudvendor.com', 'aiweekly.io', 'officedeals.com', 'example.com']
                                    profile = gmail_client.service.users().getProfile(userId='me').execute()
                                    my_email = profile.get('emailAddress')
                                    
                                    recipient = target_email
                                    if recipient:
                                        domain = recipient.split('@')[-1].lower()
                                        if domain in demo_domains:
                                            recipient = my_email
                                    else:
                                        recipient = my_email
                                except Exception:
                                    recipient = None

                                if recipient:
                                    with st.spinner(f"Delivering demo test email to {recipient}..."):
                                        try:
                                            from email.mime.text import MIMEText
                                            import base64

                                            test_subject = f"[Demo Reply] Re: {thread.get('subject', 'Demo Thread')}"
                                            test_body = f"""--- DEMO TEST EMAIL SENT BY INBOX COPILOT ---
    Original Sender: {thread.get('from') or thread.get('sender')}
    Original Subject: {thread.get('subject')}

    Approved Reply:
    --------------------------------------------------
    {draft_text}
    --------------------------------------------------
    """
                                            msg = MIMEText(test_body)
                                            msg['to'] = recipient
                                            msg['subject'] = test_subject

                                            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

                                            sent = gmail_client.service.users().messages().send(
                                                userId='me',
                                                body={'raw': raw}
                                            ).execute()

                                            if sent and sent.get('id'):
                                                sent_flag = True
                                                sent_id = sent.get('id')
                                            else:
                                                st.error("Failed to send demo test mail.")
                                        except Exception as err:
                                            st.error(f"Gmail Demo Send Error: {err}")
                                else:
                                    st.error("Could not determine recipient email address for demo sending.")
                            else:
                                st.info("Demo Mode: Simulated mail delivery (Gmail offline).")
                                sent_flag = True
                                sent_id = "mock_send_id_123"
                        else:
                            st.error("Gmail Client is offline or unavailable. Cannot send email.")

                        if sent_flag:
                            result = {"id": sent_id}
                            if result.get("id"):
                                if not recipient:
                                    import email.utils
                                    from_header = thread.get('from') or thread.get('sender') or ''
                                    _, target_email = email.utils.parseaddr(from_header)
                                    recipient = target_email or thread.get("from") or thread.get("sender") or "Unknown"
                                log_action(
                                    action_type="sent",
                                    thread_subject=thread["subject"],
                                    detail=recipient,
                                    action_id=result["id"],
                                )
                            save_approved_draft(thread, draft_text, sent_via_gmail=gmail_available, gmail_message_id=sent_id)
                            st.session_state.show_send_confirmation = False
                            st.session_state.pending_approval_draft = ""
                            st.session_state.pending_approval_thread = None
                            st.session_state.status = "approved"
                            st.session_state.current_draft = draft_text

                            st.balloons()
                            if is_demo:
                                if gmail_available:
                                    st.toast(f"Demo Mode: Test email sent to {recipient}!", icon="\u2709\ufe0f")
                                else:
                                    st.toast("Demo Mode: Simulated mail delivery successful!", icon="\u2709\ufe0f")
                            else:
                                st.toast("Email dispatched successfully via Gmail!", icon="\u2709\ufe0f")
                            st.rerun()

                    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
                    confirm_col1, confirm_col2 = st.columns(2)
                    with confirm_col1:
                        if st.button("No, Save Local Only", use_container_width=True):
                            thread = st.session_state.pending_approval_thread
                            draft_text = st.session_state.pending_approval_draft

                            save_approved_draft(thread, draft_text, sent_via_gmail=False, gmail_message_id=None)

                            st.session_state.show_send_confirmation = False
                            st.session_state.pending_approval_draft = ""
                            st.session_state.pending_approval_thread = None
                            st.session_state.status = "approved"
                            st.session_state.current_draft = draft_text
                            st.balloons()
                            st.toast("Draft approved and saved locally.", icon="\U0001f4be")
                            st.rerun()

                    with confirm_col2:
                        if st.button("Cancel Approval", use_container_width=True):
                            st.session_state.show_send_confirmation = False
                            st.session_state.pending_approval_draft = ""
                            st.session_state.pending_approval_thread = None
                            st.rerun()

                elif st.session_state.status == "editing":
                    edited_text = st.text_area("Inline Editor", value=st.session_state.edited_draft, label_visibility="collapsed", height=220)
                    st.session_state.edited_draft = edited_text

                    if st.button("Save & Approve", use_container_width=True, type="primary"):
                        if send_on_approve:
                            st.session_state.pending_approval_draft = st.session_state.edited_draft
                            st.session_state.pending_approval_thread = thread
                            st.session_state.show_send_confirmation = True
                            st.rerun()
                        else:
                            save_approved_draft(thread, st.session_state.edited_draft, sent_via_gmail=False)
                            st.session_state.status = "approved"
                            st.session_state.current_draft = st.session_state.edited_draft
                            st.balloons()
                            st.toast("Draft approved and saved locally.", icon="\U0001f4be")
                            st.rerun()

                    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        if st.button("Save Draft Only", use_container_width=True):
                            st.session_state.current_draft = st.session_state.edited_draft
                            st.session_state.status = "none"
                            st.balloons()
                            st.toast("Draft changes saved", icon="\U0001f4be")
                            st.rerun()
                    with edit_col2:
                        if st.button("Cancel Edit", use_container_width=True):
                            st.session_state.status = "none"
                            st.rerun()
                else:
                    # View Mode
                    st.markdown(f"""
                    <div class='draft-letterhead'>
                        <div class='draft-letterhead-bar'>Draft - awaiting review</div>
                        <div class='draft-letterhead-body'>{st.session_state.current_draft}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.session_state.status == "rejected":
                        st.error("Draft rejected and discarded.")
                        if st.button("Restore Draft", use_container_width=True):
                            st.session_state.status = "none"
                            st.rerun()
                    else:
                        render_approval_phase(thread)

                # Render Prominent Audit compliance checker directly below draft
                audit = check_draft_rules(st.session_state.current_draft)
                fluff_icon, fluff_status, fluff_color = ("\u2705", "PASS", "var(--moss)") if audit.get("fluff_free") else ("\u274c", "FAIL", "var(--rust)")
                len_icon, len_status, len_color = ("\u2705", "PASS", "var(--moss)") if audit.get("length_ok") else ("\u274c", "FAIL", "var(--rust)")
                sign_icon, sign_status, sign_color = ("\u2705", "PASS", "var(--moss)") if audit.get("has_signoff") else ("\u26a0\ufe0f", "WARN", "var(--amber-deep)")

                st.markdown(f"""
                <div style='background: var(--paper-raised); border: 1px solid var(--line); border-radius: 4px; padding: 12px 14px; margin-top: 12px; box-shadow: 2px 2px 4px rgba(20, 17, 15, 0.02);'>
                    <div style='font-family: "JetBrains Mono", monospace; font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; margin-bottom: 8px; border-bottom: 1px solid var(--line-soft); padding-bottom: 4px;'>
                        \U0001f4ca Live Compliance Audit Scan
                    </div>
                    <div style='display: flex; flex-direction: column; gap: 6px;'>
                        <div style='display: flex; justify-content: space-between; align-items: center;'>
                            <span style='font-family: "Inter", sans-serif; font-size: 0.8rem; color: var(--ink-soft);'>No Corporate Fluff</span>
                            <span style='font-family: "JetBrains Mono", monospace; font-size: 0.72rem; font-weight: 700; color: {fluff_color};'>{fluff_icon} {fluff_status}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; align-items: center;'>
                            <span style='font-family: "Inter", sans-serif; font-size: 0.8rem; color: var(--ink-soft);'>Brevity (&le; 5 sentences)</span>
                            <span style='font-family: "JetBrains Mono", monospace; font-size: 0.72rem; font-weight: 700; color: {len_color};'>{len_icon} {len_status} ({audit.get("sentence_count")} sentences)</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; align-items: center;'>
                            <span style='font-family: "Inter", sans-serif; font-size: 0.8rem; color: var(--ink-soft);'>Carries Sign-off Signature</span>
                            <span style='font-family: "JetBrains Mono", monospace; font-size: 0.72rem; font-weight: 700; color: {sign_color};'>{sign_icon} {sign_status}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<hr>", unsafe_allow_html=True)

            # Tabs at the bottom
            tab_triage, tab_persona, tab_deliverables, tab_archive = st.tabs(["TRIAGE", "PERSONA", "DELIVERABLES", "ARCHIVE"])

            with tab_triage:
                p_val = thread.get("priority", "unknown").upper()
                cat_val = thread.get("category", "other").upper()
                reason_val = thread.get("reason", "No reason provided.")

                p_colors = {
                    "URGENT": "var(--rust)",
                    "NEEDS-REPLY": "var(--amber-deep)",
                    "FYI": "var(--moss)",
                    "IGNORE": "var(--muted)",
                    "UNKNOWN": "var(--muted)"
                }
                p_color = p_colors.get(p_val, "var(--ink)")

                st.markdown(f"""
                <div class='marginalia'>
                    <span class='marginalia-label'>Priority Level</span>
                    <span class='marginalia-mark' style='color:{p_color}; font-weight:700;'>{p_val}</span>
                </div>
                <div class='marginalia'>
                    <span class='marginalia-label'>Triage Category</span>
                    <span class='marginalia-mark' style='color:var(--blue); font-weight:700;'>{cat_val}</span>
                </div>
                <div style='margin-top: 8px;'>
                    <span style='font-family: "JetBrains Mono", monospace; font-size: 0.65rem; color: var(--muted); text-transform: uppercase; font-weight: 600;'>Triage Reason</span>
                    <p style='font-size: 0.8rem; font-style: italic; margin-top: 3px; line-height: 1.4; color: var(--ink-soft);'>"{reason_val}"</p>
                </div>
                """, unsafe_allow_html=True)

                # Manual override text inputs
                st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)
                over_col1, over_col2 = st.columns(2)
                with over_col1:
                    new_p = st.text_input(
                        "Override Priority",
                        value=p_val.lower(),
                        key=f"op_{t_id}"
                    )
                with over_col2:
                    new_cat = st.text_input(
                        "Override Category",
                        value=cat_val.lower(),
                        key=f"oc_{t_id}"
                    )

                if new_p != p_val.lower() or new_cat != cat_val.lower():
                    for idx, tr in enumerate(st.session_state.threads):
                        if tr.get("thread_id") == t_id or tr.get("id") == t_id:
                            st.session_state.threads[idx]["priority"] = new_p
                            st.session_state.threads[idx]["category"] = new_cat
                            st.session_state.threads[idx]["reason"] = "Manual override by ghostwriter"
                            st.session_state.selected_thread_dict = st.session_state.threads[idx]
                    st.toast("Triage classifications updated!", icon="\U0001f504")
                    st.rerun()

                if st.button("Re-run Triage Sync", use_container_width=True, key=f"t_sync_{t_id}"):
                    with st.spinner("Recalculating classification..."):
                        try:
                            sender_val = thread.get('from') or thread.get('sender') or 'Unknown'
                            subject_val = thread.get('subject') or 'No Subject'
                            snippet_val = thread.get('snippet') or (thread.get('messages', [{}])[-1].get('body', '')[:100] if thread.get('messages') else '')

                            label = triage_thread(sender=sender_val, subject=subject_val, snippet=snippet_val, api_key=groq_api_key)

                            # update
                            for idx, tr in enumerate(st.session_state.threads):
                                if tr.get("thread_id") == t_id or tr.get("id") == t_id:
                                    st.session_state.threads[idx].update(label)
                                    st.session_state.selected_thread_dict = st.session_state.threads[idx]

                            st.toast("Triage Sync complete", icon="\U0001f916")
                            st.rerun()
                        except Exception as err:
                            st.error(f"Triage recalculation failed: {err}")

            with tab_persona:
                st.markdown(f"**Writer Persona:** &middot; {st.session_state.persona_name} ({st.session_state.persona_role})")
                st.markdown(f"**Standard Tone:** &middot; {st.session_state.persona_tone}")
                st.markdown(f"**Formality Level:** &middot; {st.session_state.persona_formality}")

                # Persona editing inputs
                with st.expander("\U0001f4dd Edit Tone Profile Details"):
                    p_name = st.text_input("Name", value=st.session_state.get("persona_name", ""))
                    p_role = st.text_input("Role Description", value=st.session_state.get("persona_role", ""))
                    p_tone = st.text_input("Tone", value=st.session_state.get("persona_tone", ""))
                    p_formality = st.text_input("Formality", value=st.session_state.get("persona_formality", ""))
                    p_signoff = st.text_input("Sign-off Signature", value=st.session_state.get("persona_signoff", ""))
                    p_quirks = st.text_area("Writing Quirks (one per line)", value=st.session_state.get("persona_quirks", ""))

                    if st.button("Save Persona Configuration", use_container_width=True):
                        tone_profile["name"] = p_name
                        tone_profile["role"] = p_role
                        tone_profile["tone"] = p_tone
                        tone_profile["formality"] = p_formality
                        tone_profile["sign_off"] = p_signoff
                        tone_profile["quirks"] = [q.strip() for q in p_quirks.split("\n") if q.strip()]

                        with open("data/tone_profile.json", "w", encoding="utf-8") as f:
                            json.dump(tone_profile, f, indent=2)

                        # Update session state values explicitly
                        st.session_state.persona_name = p_name
                        st.session_state.persona_role = p_role
                        st.session_state.persona_tone = p_tone
                        st.session_state.persona_formality = p_formality
                        st.session_state.persona_signoff = p_signoff
                        st.session_state.persona_quirks = p_quirks
                        st.session_state.show_save_toast = True
                        st.rerun()



            # Proof generation helpers
            def generate_proof_markdown() -> str:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                md = f"# The Draft Desk \u2014 Proof of Work\n"
                md += f"**Date generated:** {now_str}\n"
                md += f"**Approved Drafts:** {len(st.session_state.approved)} finalized replies\n\n"
                md += "---\n"

                for t_id, approved_draft in st.session_state.approved.items():
                    original_thread = next((t for t in st.session_state.threads if t.get("thread_id") == t_id or t.get("id") == t_id), None)
                    if original_thread:
                        messages = original_thread.get("messages", [])
                        last_msg_body = messages[-1].get("body", "") if messages else original_thread.get("snippet", "")
                        sender = original_thread.get("from") or original_thread.get("sender") or "Unknown"
                        md += f"\n\n## Thread: {original_thread.get('subject')}\n"
                        md += f"- **From:** {sender}\n"
                        md += f"### Incoming Message:\n"
                        md += f"> {last_msg_body.replace(chr(10), chr(10) + '> ')}\n\n"
                        md += f"### Approved Reply Draft:\n"
                        md += f"```\n{approved_draft}\n```\n"
                        md += "---\n"
                return md

            def generate_proof_html() -> str:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                html = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>The Draft Desk \u2014 Proof of Work</title>
    <style>
        body {{
            background-color: #1a1a2e;
            color: #f1f1f1;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 40px;
            margin: 0;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            border-bottom: 2px solid #ff7a00;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }}
        h1 {{
            margin: 0;
            color: #ff7a00;
            font-size: 2.2rem;
        }}
        .meta-details {{
            font-family: monospace;
            color: #a0a0b0;
            margin-top: 10px;
        }}
        .grid-container {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
            background: #111122;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }}
        .column {{
            padding: 25px;
        }}
        .left-column {{
            border-right: 1px dashed #333344;
            background: rgba(255, 122, 0, 0.02);
        }}
        .right-column {{
            background: rgba(0, 255, 122, 0.02);
        }}
        .thread-title {{
            grid-column: span 2;
            padding: 16px 25px;
            background: #252538;
            font-size: 1.2rem;
            font-weight: bold;
            border-bottom: 1px solid #ff7a00;
            display: flex;
            justify-content: space-between;
        }}
        .label-header {{
            text-transform: uppercase;
            font-family: monospace;
            letter-spacing: 0.1em;
            font-size: 0.72rem;
            margin-bottom: 12px;
        }}
        .label-left {{ color: #ff7a00; }}
        .label-right {{ color: #00ff7a; }}
        .message-box {{
            background: #222235;
            border-radius: 4px;
            padding: 16px;
            border-left: 3px solid #ff7a00;
            line-height: 1.5;
            white-space: pre-wrap;
            font-size: 0.9rem;
        }}
        .draft-box {{
            background: #222235;
            border-radius: 4px;
            padding: 16px;
            border-left: 3px solid #00ff7a;
            line-height: 1.5;
            white-space: pre-wrap;
            font-size: 0.9rem;
        }}
    </style>
    </head>
    <body>
    <div class="container">
        <header>
            <h1>The Draft Desk \u2014 Proof of Work</h1>
            <div class="meta-details">Date: {now_str} &middot; Total Deliverables: {len(st.session_state.approved)}</div>
        </header>
    """
                for t_id, approved_draft in st.session_state.approved.items():
                    original_thread = next((t for t in st.session_state.threads if t.get("thread_id") == t_id or t.get("id") == t_id), None)
                    if original_thread:
                        messages = original_thread.get("messages", [])
                        last_msg_body = messages[-1].get("body", "") if messages else original_thread.get("snippet", "")
                        sender = original_thread.get("from") or original_thread.get("sender") or "Unknown"
                        html += f"""
        <div class="grid-container">
            <div class="thread-title">
                <span>Subject: {original_thread.get('subject')}</span>
                <span style="color:#00ff7a; font-family:monospace; font-size:0.75rem;">APPROVED</span>
            </div>
            <div class="column left-column">
                <div class="label-header label-left">Original Correspondence Log</div>
                <div style="margin-bottom: 8px; font-size:0.8rem; color:#a0a0b0;">From: {sender}</div>
                <div class="message-box">{last_msg_body}</div>
            </div>
            <div class="column right-column">
                <div class="label-header label-right">Finalized Reply Draft</div>
                <div style="margin-bottom: 8px; font-size:0.8rem; color:#a0a0b0;">Sign-off: Aaron Francis</div>
                <div class="draft-box">{approved_draft}</div>
            </div>
        </div>
    """
                html += """
    </div>
    </body>
    </html>
    """
                return html

            with tab_deliverables:
                if st.session_state.approved:
                    st.markdown(f"**Finalized Session Deliverables ({len(st.session_state.approved)} items)**")
                    for td_id, app_text in st.session_state.approved.items():
                        orig_t = next((t for t in st.session_state.threads if t.get("thread_id") == td_id or t.get("id") == td_id), None)
                        subj_t = orig_t.get("subject", "Approved Draft") if orig_t else "Approved Draft"
                        with st.expander(f"\u2705 {subj_t}"):
                            st.text_area("Approved reply body", value=app_text, disabled=True, height=120, key=f"deliv_view_{td_id}")

                    st.subheader("Action Log")
                    actions = get_action_log()
                    if not actions:
                        st.info("No actions logged yet.")
                    else:
                        for entry in actions:
                            col1, col2, col3, col4 = st.columns(4)
                            action_type = entry.get("action_type", "")
                            icon = "📨" if action_type == "sent" else "📅"
                            col1.write(f"{icon} {action_type.upper()}")
                            col2.write(f"**{entry.get('thread_subject', '')}**")
                            col3.write(f"`{entry.get('detail', '')}`")
                            
                            ts_str = entry.get("timestamp", "")
                            try:
                                dt = datetime.fromisoformat(ts_str)
                                formatted_ts = dt.strftime("%b %d %I:%M %p")
                            except Exception:
                                formatted_ts = ts_str
                            col4.caption(formatted_ts)

                    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
                    md_proof = generate_proof_markdown()
                    html_proof = generate_proof_html()

                    col_dld1, col_dld2 = st.columns(2)
                    with col_dld1:
                        st.download_button(
                            label="\U0001f4c4 Download Proof (Markdown)",
                            data=md_proof,
                            file_name=f"proof_of_work_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                            mime="text/markdown",
                            use_container_width=True,
                            key="dl_md_btn"
                        )
                    with col_dld2:
                        st.download_button(
                            label="\U0001f310 Download Proof (HTML Social)",
                            data=html_proof,
                            file_name=f"proof_of_work_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                            mime="text/html",
                            use_container_width=True,
                            key="dl_html_btn"
                        )
                else:
                    st.caption("No drafts approved in this active session yet.")

            with tab_archive:
                if approved_drafts:
                    st.markdown("**Historical Approved Drafts (Last 5)**")
                    for d in reversed(approved_drafts[-5:]):
                        ts = d.get('timestamp', '').split('T')[0] if d.get('timestamp') else ''
                        sent_lbl = "Sent via Gmail" if d.get('sent_via_gmail') else "Saved locally"
                        st.markdown(f"""
                        <div class='archive-entry'>
                            <div class='archive-entry-top'>
                                <span>{d.get('subject', 'No Subject')[:25]}...</span>
                                <span>{ts}</span>
                            </div>
                            <div class='archive-entry-meta'>{sent_lbl}</div>
                            <div class='archive-entry-body'>{d.get('approved_draft', '')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("No historical approved drafts saved yet.")

def main():
    render_sidebar()
    if st.session_state.get("pipeline_running", False):
        _render_pipeline_execution()
    else:
        render_phase()

if __name__ == "__main__":
    main()
