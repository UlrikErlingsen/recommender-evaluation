"""Shared visual shell for the Signal suite."""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st


def _mark_uri(mark_path: Path) -> str:
    if not mark_path.exists():
        return ""
    return "data:image/svg+xml;base64," + base64.b64encode(mark_path.read_bytes()).decode("ascii")


def apply_suite_theme() -> None:
    """Apply the mature Signal palette, spacing, focus, sidebar, and component shell."""

    st.markdown(
        """
        <style>
        :root {
            --ss-ink:#17322e; --ss-deep:#102c2a; --ss-teal:#173c3a;
            --ss-coral:#d95b40; --ss-mint:#83d2b4; --ss-gold:#f2c66d;
            --ss-paper:#f8f5ed; --ss-muted:#59716c; --ss-line:rgba(23,50,46,.14);
        }
        [data-testid="stAppViewContainer"] {
            background:radial-gradient(circle at 94% 2%,rgba(131,210,180,.17),transparent 28rem),
                       radial-gradient(circle at 3% 93%,rgba(242,198,109,.12),transparent 25rem),
                       linear-gradient(180deg,#fbf9f3 0%,var(--ss-paper) 100%);
        }
        [data-testid="stHeader"] { background:rgba(248,245,237,.78); }
        [data-testid="stSidebar"] { background:linear-gradient(165deg,#173c3a 0%,#102c2a 65%,#0c2422 100%); }
        [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span { color:#f8f5ed; }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#b9cbc5; }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
            background:rgba(255,255,255,.06); border-color:rgba(242,198,109,.32);
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small span { color:#b9cbc5 !important; }
        [data-testid="stSidebar"] button {
            background:rgba(255,255,255,.08); color:#f8f5ed !important; border-color:rgba(255,255,255,.23);
        }
        [data-testid="stSidebar"] button:hover { background:rgba(242,198,109,.14); border-color:rgba(242,198,109,.48); }
        [data-testid="stSidebar"] button * { color:#f8f5ed !important; }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
            background:#f8f5ed; color:#17322e !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button * { color:#17322e !important; }
        .block-container { max-width:1240px; padding-top:4.4rem; padding-bottom:4rem; }
        h1,h2,h3 { color:var(--ss-ink); letter-spacing:-.025em; }
        a { color:#9b3e2b; }
        [data-testid="stMetric"] {
            background:rgba(255,255,255,.75); border:1px solid var(--ss-line); border-radius:16px;
            padding:1rem 1.05rem; box-shadow:0 8px 28px rgba(23,50,46,.045);
        }
        [data-testid="stMetricValue"] { color:var(--ss-ink); font-size:clamp(1.35rem,2.3vw,1.9rem); }
        [data-testid="stDataFrame"] { border:1px solid var(--ss-line); border-radius:12px; overflow:hidden; }
        .stButton > button[kind="primary"] {
            background:linear-gradient(135deg,#e26748,#c94c34); color:white; border:0;
            box-shadow:0 8px 20px rgba(217,91,64,.22); font-weight:750;
        }
        .stButton > button[kind="primary"]:hover { background:linear-gradient(135deg,#c94c34,#b63f2b); color:white; }
        button:focus-visible,a:focus-visible,input:focus-visible { outline:3px solid #f2c66d !important; outline-offset:2px; }
        [data-testid="stExpander"],[data-testid="stAlert"],[data-testid="stVerticalBlockBorderWrapper"] { border-radius:14px; }
        .ss-lockup { display:flex; align-items:center; gap:.65rem; }
        .ss-mark { width:38px; height:38px; }
        .ss-name { color:white; font-size:1.28rem; line-height:1; font-weight:850; letter-spacing:-.04em; }
        .ss-name span { color:#f2c66d !important; }
        .ss-tag { margin:.55rem 0 0 !important; color:#b9cbc5 !important; font-size:.77rem; line-height:1.4; }
        .ss-masthead {
            display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.72rem 1rem .72rem .78rem;
            margin-bottom:1.35rem; background:rgba(255,255,255,.65); border:1px solid var(--ss-line);
            border-radius:18px; box-shadow:0 10px 36px rgba(23,50,46,.05);
        }
        .ss-masthead .ss-mark { width:48px; height:48px; }
        .ss-wordmark { color:var(--ss-ink); font-weight:850; letter-spacing:-.045em; font-size:1.55rem; line-height:1; }
        .ss-wordmark span { color:var(--ss-coral); }
        .ss-kicker { margin-top:.32rem; color:var(--ss-muted); font-size:.67rem; font-weight:800; letter-spacing:.13em; }
        .ss-promise { color:#47645e; font-size:.78rem; font-weight:700; white-space:nowrap; }
        .ss-promise span { color:var(--ss-coral); padding:0 .3rem; }
        .ss-hero {
            position:relative; overflow:hidden; padding:clamp(1.7rem,4vw,3.4rem); margin-bottom:1.3rem;
            background:linear-gradient(135deg,#173c3a 0%,#102c2a 75%); border-radius:26px;
            box-shadow:0 18px 50px rgba(23,50,46,.17);
        }
        .ss-hero:after {
            content:""; position:absolute; width:330px; height:330px; right:-105px; top:-148px;
            border-radius:50%; border:56px solid rgba(131,210,180,.12);
        }
        .ss-eyebrow { color:var(--ss-mint); font-size:.72rem; font-weight:850; letter-spacing:.16em; }
        .ss-hero h1 { color:white; font-size:clamp(2.25rem,5vw,4.7rem); line-height:.97; margin:.75rem 0 1rem; max-width:960px; }
        .ss-hero h1 em { color:var(--ss-gold); font-style:normal; }
        .ss-hero p { color:#d7e3df; font-size:1.06rem; line-height:1.6; max-width:850px; }
        .ss-pills { display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1.15rem; }
        .ss-pill {
            padding:.4rem .72rem; border:1px solid rgba(255,255,255,.16); border-radius:999px;
            color:#f8f5ed; font-size:.78rem; font-weight:700; background:rgba(255,255,255,.055);
        }
        .ss-footer { margin-top:3.2rem; padding-top:1rem; border-top:1px solid var(--ss-line); color:#617670; font-size:.76rem; text-align:center; }
        .ss-footer span { color:var(--ss-coral); padding:0 .38rem; }
        .boundary { background:rgba(131,210,180,.13) !important; border-left-color:var(--ss-mint) !important; }
        .name-box { background:rgba(242,198,109,.15) !important; border-left-color:var(--ss-gold) !important; }
        @media (max-width:760px) {
            .ss-promise{display:none}.ss-hero{border-radius:20px}.block-container{padding-top:3.5rem}
        }
        @media (prefers-reduced-motion:reduce) { * { scroll-behavior:auto !important; transition:none !important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand(product: str, tagline: str, mark_path: Path) -> None:
    uri = _mark_uri(mark_path)
    stem = escape(product.removesuffix("Signal"))
    mark = f'<img class="ss-mark" src="{uri}" alt="">' if uri else ""
    st.sidebar.markdown(
        f'<div class="ss-lockup">{mark}<div class="ss-name">{stem}<span>Signal</span></div></div>'
        f'<p class="ss-tag">{escape(tagline)}</p>',
        unsafe_allow_html=True,
    )


def masthead(product: str, kicker: str, mark_path: Path) -> None:
    uri = _mark_uri(mark_path)
    stem = escape(product.removesuffix("Signal"))
    mark = f'<img class="ss-mark" src="{uri}" alt="">' if uri else ""
    st.markdown(
        f"""
        <div class="ss-masthead">
          <div class="ss-lockup">{mark}<div><div class="ss-wordmark">{stem}<span>Signal</span></div>
          <div class="ss-kicker">{escape(kicker.upper())}</div></div></div>
          <div class="ss-promise">Local-first <span>◆</span> Named methods <span>◆</span> Portable evidence</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero(eyebrow: str, title: str, emphasis: str, body: str, pills: tuple[str, ...]) -> None:
    safe_title = escape(title)
    if emphasis and emphasis in title:
        safe_title = safe_title.replace(escape(emphasis), f"<em>{escape(emphasis)}</em>", 1)
    pill_html = "".join(f'<span class="ss-pill">{escape(pill)}</span>' for pill in pills)
    st.markdown(
        f"""
        <div class="ss-hero">
          <div class="ss-eyebrow">{escape(eyebrow.upper())}</div>
          <h1>{safe_title}</h1>
          <p>{escape(body)}</p>
          <div class="ss-pills">{pill_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def footer(product: str, version: str, boundary: str) -> None:
    st.markdown(
        f'<div class="ss-footer">{escape(product)} v{escape(version)} <span>◆</span> '
        f'{escape(boundary)} <span>◆</span> Part of the Signal suite <span>◆</span> AGPL-3.0-or-later</div>',
        unsafe_allow_html=True,
    )
