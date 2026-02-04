import streamlit as st


def apply_base_theme():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&family=Source+Serif+4:wght@400;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', sans-serif;
        }

        .app-title {
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.2rem;
        }

        .subtitle {
            color: #6b7280;
            font-size: 1rem;
        }

        .section-title {
            font-size: 1.2rem;
            font-weight: 700;
            margin: 0.6rem 0 0.3rem 0;
        }

        .soft-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            padding: 1rem 1.2rem;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
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
        .pill-ready { background: #ecfdf3; color: #047857; border: 1px solid #a7f3d0; }
        .pill-running { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
        .pill-queued { background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; }
        .pill-failed { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
        .pill-muted { background: #f3f4f6; color: #6b7280; border: 1px solid #e5e7eb; }

        .stApp {
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        }

        .stButton > button {
            border-radius: 10px;
            border: 1px solid #0f766e;
            background: #0f766e;
            color: #ffffff;
            font-weight: 600;
            padding: 0.35rem 0.9rem;
        }
        .stButton > button:hover {
            background: #115e59;
            border-color: #115e59;
        }

        .stTextInput input, .stTextArea textarea {
            border-radius: 10px;
        }

        .stSelectbox div[data-baseweb="select"] {
            border-radius: 10px;
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
