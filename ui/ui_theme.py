import streamlit as st


def apply_base_theme():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&family=Source+Serif+4:wght@400;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', sans-serif;
            color: #e5e7eb;
        }

        .app-title {
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.2rem;
            color: #f9fafb;
        }

        .subtitle {
            color: #cbd5f5;
            font-size: 1rem;
        }

        .section-title {
            font-size: 1.2rem;
            font-weight: 700;
            margin: 0.6rem 0 0.3rem 0;
        }

        .soft-card {
            background: rgba(17, 24, 39, 0.85);
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 14px;
            padding: 1rem 1.2rem;
            box-shadow: 0 12px 30px rgba(2, 6, 23, 0.45);
        }

        .pill {
            display: inline-block;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .pill-ready { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.5); }
        .pill-running { background: rgba(59, 130, 246, 0.2); color: #93c5fd; border: 1px solid rgba(147, 197, 253, 0.5); }
        .pill-queued { background: rgba(249, 115, 22, 0.2); color: #fdba74; border: 1px solid rgba(253, 186, 116, 0.5); }
        .pill-failed { background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid rgba(252, 165, 165, 0.5); }
        .pill-muted { background: rgba(148, 163, 184, 0.2); color: #cbd5f5; border: 1px solid rgba(148, 163, 184, 0.45); }

        .stApp {
            background: radial-gradient(circle at top, #0f172a 0%, #0b1220 45%, #070b12 100%);
        }

        .stButton > button {
            border-radius: 10px;
            border: 1px solid #38bdf8;
            background: linear-gradient(135deg, #0ea5e9, #2563eb);
            color: #f8fafc;
            font-weight: 600;
            padding: 0.35rem 0.9rem;
        }
        .stButton > button:hover {
            background: linear-gradient(135deg, #38bdf8, #3b82f6);
            border-color: #7dd3fc;
        }

        .stTextInput input, .stTextArea textarea {
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.7);
            color: #e2e8f0;
            border: 1px solid rgba(148, 163, 184, 0.35);
        }

        .stSelectbox div[data-baseweb="select"] {
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.7);
            color: #e2e8f0;
            border: 1px solid rgba(148, 163, 184, 0.35);
        }

        .stMarkdown, .stCaption, .stText, .stAlert {
            color: #e2e8f0;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def status_pill(status: str) -> str:
    s = (status or "").strip().lower()
    if s in {"ready", "complete", "completed"}:
        cls = "pill-ready"
    elif s in {"parsing", "chunking", "indexing", "running", "pending", "processing"}:
        cls = "pill-running"
    elif s in {"queued", "awaiting_options"}:
        cls = "pill-queued"
    elif s in {"failed", "error"}:
        cls = "pill-failed"
    else:
        cls = "pill-muted"
    return f'<span class="pill {cls}">{status or "unknown"}</span>'
