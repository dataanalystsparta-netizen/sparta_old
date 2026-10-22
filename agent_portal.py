import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import plotly.express as px
import plotly.graph_objects as go
import calendar
import math
from html import escape
from io import BytesIO
import re
import time
import requests
import os

# ============================================================================
# SPARTA AGENT PORTAL — PREMIUM UI REFRESH
# Existing functionality retained:
# - Agent access-key authentication
# - Login logging to Google Sheets / Logs
# - Existing Sparta + Sparta2 Google Sheet historical data
# - CRM data mirrored into Google Sheets by a separate 5-minute sync job
# - 5-minute data cache
# - Start/end date filtering
# - Quality / Welcome Call / Live KPIs
# - Insight flags
# - Main KPI cards include change versus the immediately preceding equal-length period
# - Daily / Monthly breakdowns
# - Sales activity calendar
# - Recent applications log with hierarchical filters + pagination
# - Existing disposition / performance tips
# ============================================================================

st.set_page_config(
    page_title="Sparta Agent Portal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not hasattr(st, "html"):
    st.error("This portal requires Streamlit 1.37+ for the premium UI renderer.")
    st.stop()

# ----------------------------------------------------------------------------
# Theme / UI
# ----------------------------------------------------------------------------
st.html(
    """
    <style>
    /* --------------------------- GLOBAL SHELL ---------------------------- */
    :root {
        --navy: #0B1736;
        --navy-2: #122451;
        --blue: #2563EB;
        --blue-2: #3B82F6;
        --cyan: #06B6D4;
        --green: #10B981;
        --amber: #F59E0B;
        --red: #EF4444;
        --slate-900: #0F172A;
        --slate-700: #334155;
        --slate-600: #475569;
        --slate-500: #64748B;
        --slate-400: #94A3B8;
        --slate-300: #CBD5E1;
        --slate-200: #E2E8F0;
        --slate-100: #F1F5F9;
        --surface: #FFFFFF;
        --page: #F4F7FB;
    }

    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 8% 0%, rgba(37,99,235,0.075), transparent 30%),
            radial-gradient(circle at 95% 10%, rgba(6,182,212,0.06), transparent 28%),
            var(--page);
    }

    [data-testid="stHeader"] {
        background: rgba(244,247,251,0.80);
        backdrop-filter: blur(14px);
    }

    .block-container {
        max-width: 1500px;
        padding-top: 0.55rem;
        padding-bottom: 0.8rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }

    /* ------------------------------ SIDEBAR ------------------------------ */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #09132E 0%, #0D1B3D 55%, #0A1531 100%);
        border-right: 1px solid rgba(255,255,255,0.06);
    }

    [data-testid="stSidebar"] * {
        color: #EAF0FF;
    }

    [data-testid="stSidebar"] [data-testid="stButton"] button {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.12);
        color: #FFFFFF;
        border-radius: 10px;
        transition: all .2s ease;
    }

    [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
        background: rgba(255,255,255,0.11);
        border-color: rgba(255,255,255,0.22);
        transform: translateY(-1px);
    }

    .sidebar-profile {
        margin: 0.5rem 0 1rem;
        padding: 16px;
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(255,255,255,0.085), rgba(255,255,255,0.035));
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
    }

    .sidebar-avatar {
        width: 42px;
        height: 42px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #2563EB, #06B6D4);
        font-size: 1.1rem;
        font-weight: 800;
        color: white;
        box-shadow: 0 8px 20px rgba(37,99,235,0.24);
    }

    .sidebar-role {
        font-size: .68rem;
        text-transform: uppercase;
        letter-spacing: 1.4px;
        color: #9FB3DC !important;
        font-weight: 800;
        margin-top: 10px;
    }

    .sidebar-name {
        font-size: 1.05rem;
        font-weight: 750;
        margin-top: 3px;
        color: #FFFFFF !important;
    }

    /* ---------------------------- TYPOGRAPHY ----------------------------- */
    h1, h2, h3, h4, h5, h6 {
        color: var(--slate-900) !important;
        letter-spacing: -0.025em;
    }

    .section-title {
        display: flex;
        align-items: center;
        gap: 11px;
        font-size: 1.02rem;
        font-weight: 800;
        color: var(--slate-900);
        margin: 1px 0 4px 0;
    }

    .section-title .icon {
        width: 32px;
        height: 32px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 9px;
        background: #EAF1FF;
        color: var(--blue);
        font-size: .95rem;
        box-shadow: inset 0 0 0 1px rgba(37,99,235,.08);
    }

    .section-subtitle {
        color: var(--slate-500);
        font-size: .78rem;
        margin: -2px 0 5px 43px;
    }

    /* ------------------------------ LOGIN -------------------------------- */
    .login-shell {
        max-width: 530px;
        margin: 7vh auto 0 auto;
        padding: 7px;
        border-radius: 26px;
        background: linear-gradient(135deg, rgba(37,99,235,.18), rgba(6,182,212,.16));
    }

    .login-card {
        background: rgba(255,255,255,.95);
        border: 1px solid rgba(255,255,255,.85);
        border-radius: 22px;
        padding: 34px 34px 30px;
        box-shadow: 0 24px 70px rgba(15,23,42,.14);
    }

    .login-brand {
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 18px;
    }

    .login-brand img {
        width: 56px;
        height: 56px;
        border-radius: 16px;
        object-fit: cover;
        box-shadow: 0 9px 25px rgba(15,23,42,.12);
    }

    .login-overline {
        font-size: .68rem;
        color: var(--blue);
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 1.6px;
        margin-bottom: 2px;
    }

    .login-title {
        font-size: 1.8rem;
        line-height: 1.05;
        font-weight: 850;
        color: var(--slate-900);
    }

    .login-copy {
        color: var(--slate-500);
        font-size: .86rem;
        line-height: 1.55;
        margin: 10px 0 22px;
    }

    /* ----------------------------- HERO --------------------------------- */
    .hero {
        position: relative;
        overflow: hidden;
        padding: 24px 27px;
        border-radius: 22px;
        color: white;
        background:
            radial-gradient(circle at 82% 15%, rgba(6,182,212,.24), transparent 27%),
            radial-gradient(circle at 0% 100%, rgba(59,130,246,.28), transparent 34%),
            linear-gradient(135deg, #09142F 0%, #10275A 55%, #143A70 100%);
        box-shadow: 0 18px 40px rgba(15,23,42,.13);
        border: 1px solid rgba(255,255,255,.08);
    }

    .hero::after {
        content: "";
        position: absolute;
        width: 240px;
        height: 240px;
        right: -80px;
        top: -120px;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,.08);
        box-shadow: 0 0 0 35px rgba(255,255,255,.025), 0 0 0 70px rgba(255,255,255,.018);
    }

    .hero-kicker {
        font-size: .68rem;
        text-transform: uppercase;
        letter-spacing: 1.7px;
        font-weight: 850;
        color: #8DB4FF;
        margin-bottom: 2px;
    }

    .hero-title {
        font-size: 1.75rem;
        font-weight: 850;
        letter-spacing: -.035em;
        margin: 0;
        color: white;
    }

    .hero-subtitle {
        color: #C5D4F3;
        font-size: .82rem;
        margin-top: 4px;
    }

    .hero-sync {
        text-align: right;
        font-size: .7rem;
        color: #A9BDE2;
        position: relative;
        z-index: 2;
        padding-top: 6px;
    }

    .hero-sync strong {
        display: inline-block;
        margin-top: 4px;
        font-size: .82rem;
        color: #FFFFFF;
    }

    .live-dot {
        display: inline-block;
        width: 7px;
        height: 7px;
        background: #34D399;
        border-radius: 50%;
        margin-right: 5px;
        box-shadow: 0 0 0 4px rgba(52,211,153,.10);
    }

    /* ------------------------------- FILTERS ---------------------------- */
    .filter-card {
        margin: 8px 0 10px;
        padding: 8px 12px 0;
        border-radius: 15px;
        background: rgba(255,255,255,.76);
        border: 1px solid rgba(226,232,240,.95);
        box-shadow: 0 7px 20px rgba(15,23,42,.04);
    }

    .filter-label {
        font-size: .64rem;
        color: var(--slate-500);
        font-weight: 850;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 3px;
    }

    /* ------------------------------ KPI BOXES ---------------------------- */
    .kpi-box {
        height: 100%;
        padding: 13px;
        border-radius: 16px;
        border: 1px solid var(--slate-200);
        background: rgba(255,255,255,.88);
        box-shadow: 0 8px 22px rgba(15,23,42,.045);
        backdrop-filter: blur(9px);
    }

    .box-label {
        font-size: .63rem;
        font-weight: 900;
        color: var(--slate-500);
        text-transform: uppercase;
        letter-spacing: 1.2px;
        display: flex;
        align-items: center;
        gap: 7px;
        margin: 0 0 10px;
    }

    .box-label::before {
        content: "";
        width: 4px;
        height: 12px;
        border-radius: 4px;
        background: linear-gradient(180deg, var(--blue), var(--cyan));
        display: inline-block;
    }

    .kpi-grid {
        display: grid;
        gap: 9px;
    }

    .kpi-card {
        min-height: 72px;
        padding: 8px 6px 7px;
        border-radius: 12px;
        text-align: center;
        background: linear-gradient(180deg, #FFFFFF, #F8FAFC);
        border: 1px solid #E7EDF5;
        box-shadow: 0 4px 13px rgba(15,23,42,.045);
        transition: transform .18s ease, box-shadow .18s ease;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 24px rgba(15,23,42,.08);
    }

    .kpi-label {
        font-size: .61rem;
        color: var(--slate-500);
        font-weight: 800;
        margin-bottom: 2px;
        text-transform: uppercase;
        letter-spacing: .55px;
    }

    .kpi-value {
        font-size: 1.10rem;
        color: var(--slate-900);
        font-weight: 900;
        margin: 0;
        line-height: 1;
        letter-spacing: -.03em;
    }

    .kpi-pc {
        font-size: .65rem;
        color: var(--blue);
        font-weight: 800;
        margin-top: 4px;
        background: #EAF1FF;
        display: inline-block;
        padding: 3px 7px;
        border-radius: 99px;
    }

    .kpi-trend {
        display: inline-block;
        margin-top: 5px;
        padding: 2px 6px;
        border-radius: 999px;
        font-size: .52rem;
        line-height: 1.25;
        font-weight: 850;
        white-space: nowrap;
        max-width: 100%;
    }
    .kpi-trend-good { background: #ECFDF5; color: #047857; }
    .kpi-trend-bad { background: #FEF2F2; color: #B91C1C; }
    .kpi-trend-neutral { background: #EFF6FF; color: #1D4ED8; }
    .kpi-trend-flat { background: #F1F5F9; color: #64748B; }

    /* ------------------------------ INSIGHTS ----------------------------- */
    .insight-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        padding: 5px 1px 3px;
    }

    .insight-card {
        flex: 1 1 235px;
        max-width: 330px;
        min-width: 220px;
        padding: 13px 15px;
        border-radius: 13px;
        background: rgba(255,255,255,.92);
        border: 1px solid var(--slate-200);
        border-left: 4px solid var(--blue);
        box-shadow: 0 6px 18px rgba(15,23,42,.045);
    }

    .insight-title { font-size: .61rem; font-weight: 900; color: var(--slate-500); margin: 0; text-transform: uppercase; letter-spacing: .8px; }
    .insight-phrase { font-size: .84rem; font-weight: 850; color: var(--slate-900); margin: 4px 0 2px; }
    .insight-comment { font-size: .71rem; color: var(--slate-600); margin: 0; line-height: 1.4; }

    /* ------------------------------ PANELS ------------------------------- */
    .panel-caption {
        color: var(--slate-500);
        font-size: .70rem;
        margin-top: -5px;
        margin-bottom: 8px;
    }

    .soft-divider {
        height: 1px;
        margin: 18px 0;
        background: linear-gradient(90deg, transparent, #DCE4EE 15%, #DCE4EE 85%, transparent);
    }

    /* ------------------------------ TABS --------------------------------- */
    button[data-baseweb="tab"] {
        font-weight: 750;
        color: var(--slate-500);
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--blue) !important;
    }

    [data-baseweb="tab-highlight"] {
        background-color: var(--blue) !important;
    }

    /* ------------------------------ INPUTS -------------------------------- */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    [data-testid="stDateInput"] input {
        border-radius: 10px !important;
        border-color: #D8E1ED !important;
        background: rgba(255,255,255,.92) !important;
    }

    [data-testid="stTextInput"] input {
        border-radius: 11px;
        border: 1px solid #D8E1ED;
        background: #FFFFFF;
    }

    [data-testid="stButton"] button {
        border-radius: 10px;
        font-weight: 750;
        transition: all .18s ease;
    }

    [data-testid="stButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(15,23,42,.08);
    }

    /* ----------------------------- TABLES -------------------------------- */
    [data-testid="stDataFrame"] {
        border-radius: 13px;
        overflow: hidden;
        border: 1px solid #E2E8F0;
        box-shadow: 0 5px 18px rgba(15,23,42,.035);
        background: white;
    }

    /* --------------------------- TIPS PANEL ------------------------------ */
    .tips-box {
        background: linear-gradient(135deg, #FFFDF5 0%, #FFFBEB 100%);
        border: 1px solid #FDE68A;
        border-left: 5px solid var(--amber);
        padding: 13px 15px;
        border-radius: 15px;
        margin-top: 8px;
        box-shadow: 0 7px 20px rgba(180,83,9,.05);
    }

    .tips-title {
        font-size: .76rem;
        font-weight: 900;
        color: #92400E;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: .8px;
    }

    .tips-list {
        margin: 0;
        padding-left: 20px;
        color: #78350F;
        font-size: .76rem;
        line-height: 1.55;
    }

    /* ----------------------------- FOOTER -------------------------------- */
    .footer-note {
        text-align: center;
        color: var(--slate-400);
        font-size: .66rem;
        padding: 3px 0 0;
    }

    /* ------------------------ ACTION CENTRE ------------------------------ */
    .action-wrap {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
        margin: 4px 0 8px;
    }

    .action-card {
        position: relative;
        overflow: hidden;
        min-height: 124px;
        padding: 15px 16px;
        border-radius: 15px;
        background: rgba(255,255,255,.93);
        border: 1px solid #E2E8F0;
        box-shadow: 0 8px 22px rgba(15,23,42,.045);
    }

    .action-card::after {
        content: "";
        position: absolute;
        width: 90px;
        height: 90px;
        right: -28px;
        top: -35px;
        border-radius: 999px;
        border: 1px solid rgba(37,99,235,.08);
    }

    .action-top {
        display: flex;
        align-items: center;
        gap: 9px;
    }

    .action-icon {
        width: 31px;
        height: 31px;
        border-radius: 9px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: .85rem;
        font-weight: 900;
        flex: 0 0 auto;
    }

    .action-label {
        color: #475569;
        font-size: .64rem;
        text-transform: uppercase;
        letter-spacing: .9px;
        font-weight: 900;
    }

    .action-count {
        margin-top: 8px;
        color: #0F172A;
        font-size: 1.45rem;
        line-height: 1;
        font-weight: 900;
        letter-spacing: -.04em;
    }

    .action-copy {
        margin-top: 4px;
        color: #64748B;
        font-size: .70rem;
        line-height: 1.4;
        max-width: 92%;
    }

    /* --------------------------- FUNNEL --------------------------------- */
    .funnel-shell {
        padding: 11px 13px;
        border-radius: 15px;
        background: rgba(255,255,255,.93);
        border: 1px solid #E2E8F0;
        box-shadow: 0 8px 22px rgba(15,23,42,.045);
    }

    .funnel-note {
        color: #64748B;
        font-size: .68rem;
        line-height: 1.45;
        margin-bottom: 12px;
    }

    .funnel-row {
        display: grid;
        grid-template-columns: 98px 1fr 58px;
        gap: 9px;
        align-items: center;
        margin: 7px 0;
    }

    .funnel-name {
        color: #334155;
        font-size: .69rem;
        font-weight: 800;
    }

    .funnel-companion {
        margin-top: 3px;
        color: #92400E;
        font-size: .56rem;
        font-weight: 800;
        letter-spacing: .15px;
    }

    .funnel-track {
        height: 10px;
        border-radius: 99px;
        background: #EDF2F7;
        overflow: hidden;
    }

    .funnel-fill {
        height: 100%;
        border-radius: 99px;
        min-width: 3px;
    }

    .funnel-value {
        text-align: right;
        color: #0F172A;
        font-size: .68rem;
        font-weight: 900;
    }

    /* ------------------------ COMPARISON -------------------------------- */
    .comparison-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 8px;
    }

    .comparison-card {
        min-height: 72px;
        padding: 8px 10px;
        border-radius: 13px;
        background: linear-gradient(180deg, #FFFFFF, #F8FAFC);
        border: 1px solid #E2E8F0;
        box-shadow: 0 6px 16px rgba(15,23,42,.035);
    }

    .comparison-label {
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: .65px;
        font-size: .59rem;
        font-weight: 900;
    }

    .comparison-value {
        color: #0F172A;
        font-size: .98rem;
        font-weight: 900;
        margin-top: 4px;
    }

    .comparison-base {
        color: #94A3B8;
        font-size: .63rem;
        margin-top: 2px;
    }

    .delta {
        display: inline-block;
        margin-top: 7px;
        padding: 3px 7px;
        border-radius: 99px;
        font-size: .56rem;
        font-weight: 900;
    }

    .delta-up {
        background: #ECFDF5;
        color: #047857;
    }

    .delta-down {
        background: #FEF2F2;
        color: #B91C1C;
    }

    .delta-flat {
        background: #F1F5F9;
        color: #64748B;
    }

    /* ------------------------ MINI STATS -------------------------------- */
    .mini-stat-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 8px;
    }

    .mini-stat {
        padding: 7px 9px;
        border-radius: 12px;
        background: rgba(255,255,255,.92);
        border: 1px solid #E2E8F0;
    }

    .mini-stat-label {
        color: #64748B;
        font-size: .56rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .65px;
    }

    .mini-stat-value {
        color: #0F172A;
        font-size: .98rem;
        font-weight: 900;
        margin-top: 4px;
    }

    .mini-stat-sub {
        color: #94A3B8;
        font-size: .59rem;
        margin-top: 1px;
    }

    /* ------------------------ PERFORMANCE PULSE ------------------------- */
    .pulse-shell {
        background: rgba(255,255,255,.72);
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 8px 10px;
        box-shadow: 0 7px 20px rgba(15,23,42,.035);
    }

    .pulse-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 6px;
    }

    .pulse-title {
        font-size: .88rem;
        font-weight: 900;
        color: #0F172A;
    }

    .pulse-note {
        color: #64748B;
        font-size: .62rem;
        line-height: 1.35;
        text-align: right;
    }

    .pulse-subtitle {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #475569;
        font-size: .65rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .7px;
        margin: 0 0 7px;
    }

    .pulse-subtitle span {
        width: 5px;
        height: 16px;
        border-radius: 999px;
        background: linear-gradient(180deg, #2563EB, #06B6D4);
        display: inline-block;
    }

    .pulse-separator {
        height: 1px;
        background: #E8EEF5;
        margin: 7px 0;
    }

    /* --------------------------- RESPONSIVE ------------------------------ */
    @media (max-width: 900px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        .hero-title { font-size: 1.45rem; }
        .hero-sync { text-align: left; padding-top: 12px; }
        .login-shell { margin-top: 4vh; }
    }
    </style>
    """
)

# ----------------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------------
LOGO_URL = "https://raw.githubusercontent.com/dataanalystsparta-netizen/logos/refs/heads/main/sparta-telecom-squarelogo-1663578233108%20(1).jpg"
SPREADSHEET_ID = st.secrets.get("SPREADSHEET_ID", "1R1nXJHnmsHQhisEDronG-DMo5tWeI3Ysh8TyQmKQ2fQ")
CRM_MIRROR_SHEET_URL = st.secrets.get(
    "CRM_MIRROR_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1R1nXJHnmsHQhisEDronG-DMo5tWeI3Ysh8TyQmKQ2fQ/edit?gid=1647226826#gid=1647226826",
)
CRM_MIRROR_WORKSHEET_GID = int(st.secrets.get("CRM_MIRROR_WORKSHEET_GID", "1647226826"))
# Explicit worksheet IDs supplied for the traditional source tabs. Use GIDs
# instead of worksheet titles so the portal always reads the intended tabs.
SPARTA_WORKSHEET_GID = int(st.secrets.get("SPARTA_WORKSHEET_GID", "1598890500"))
SPARTA2_WORKSHEET_GID = int(st.secrets.get("SPARTA2_WORKSHEET_GID", "1601740359"))
ATTENDANCE_WORKSHEET_GID = int(st.secrets.get("ATTENDANCE_WORKSHEET_GID", "1036958145"))
ATTENDANCE_SHEET_URL = st.secrets.get(
    "ATTENDANCE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1R1nXJHnmsHQhisEDronG-DMo5tWeI3Ysh8TyQmKQ2fQ/edit?gid=1036958145#gid=1036958145",
)

# ---------------------------------------------------------------------------
# SOURCE CUTOVER
# ---------------------------------------------------------------------------
# Legacy Sparta / Sparta2 data is used only through 17-Sep-2026 (inclusive).
# All records after 17-Sep-2026 are taken only from the CRM mirror worksheet.
LEGACY_SOURCE_CUTOFF = pd.Timestamp("2026-09-17")
CRM_SOURCE_START = LEGACY_SOURCE_CUTOFF + pd.Timedelta(days=1)

# Existing authentication remains unchanged.
ACCESS_KEYS = st.secrets["agent_keys"]

# ---------------------------------------------------------------------------
# HYBRID DATA-SOURCE CONFIGURATION
# Google Sheets remains the historical/legacy source. A dedicated CRM mirror
# worksheet supplies new CRM records, using Sale Date + Phone Number for
# reconciliation. The direct API functions below are retained for reference
# but are no longer called by the portal.
# ---------------------------------------------------------------------------
SPARTA_API_URL = st.secrets.get(
    "SPARTA_API_URL",
    "https://spartacrm.fastranking.cloud/api/dashboard/dashboard-data",
)
def resolve_api_secret():
    """Read the API token from common Streamlit-secret layouts without exposing it."""
    direct_names = [
        "SPARTA_API_TOKEN",
        "SPARTA_CRM_API_TOKEN",
        "SPARTA_API_KEY",
        "API_TOKEN",
    ]

    for name in direct_names:
        try:
            value = st.secrets.get(name, "")
        except Exception:
            value = ""
        if value:
            return str(value).strip()

    # Also support a nested [sparta_api] / [SPARTA_API] secret block.
    for section_name in ("sparta_api", "SPARTA_API", "api", "API"):
        try:
            section = st.secrets.get(section_name)
        except Exception:
            section = None
        if section:
            for key_name in ("token", "api_token", "key", "api_key"):
                try:
                    value = section.get(key_name, "")
                except Exception:
                    value = ""
                if value:
                    return str(value).strip()

    # Local development fallback only. Streamlit Cloud should use secrets.
    for env_name in ("SPARTA_API_TOKEN", "SPARTA_CRM_API_TOKEN", "SPARTA_API_KEY"):
        value = os.getenv(env_name, "")
        if value:
            return value.strip()

    return ""


SPARTA_API_TOKEN = resolve_api_secret()
SPARTA_API_AUTH_MODE = str(st.secrets.get("SPARTA_API_AUTH_MODE", "auto")).strip().lower()
SPARTA_API_TIMEOUT = int(st.secrets.get("SPARTA_API_TIMEOUT_SECONDS", 60))
SPARTA_API_MAX_RETRIES = int(st.secrets.get("SPARTA_API_MAX_RETRIES", 3))
DATA_CACHE_TTL = int(st.secrets.get("DATA_CACHE_TTL_SECONDS", 300))

API_REQUIRED_COLUMNS = [
    "Sale Date",
    "Advisor (Created Username)",
    "Customer Name",
    "Phone Number",
    "Quality Status",
    "Quality Remarks (Quality Comments)",
    "Welcome Call Status",
    "Welcome Call Remarks (Welcome Comments)",
    "Provisioning Status",
    "Provisioning Remarks (Provisioning Comments)",
    "Committed (Live) Status (Onboarding Status)",
    "LetterStatus (Dispatch Status)",
    "Confirmation Status",
    "Confirmation Comment",
    "Cancellation Reason - quality",
    "Cancellation Reason - welcome",
    "Cancellation/Rejection Reason - Provisioning",
    "Cancellation/Rejection Reason - Dispatch",
    "Cancellation/Rejection Reason - Confirmation",
    "Cancellation/Rejection Reason - Onboarding",
    "Cancellation/Rejection Reason - Potential Opportunity",
]

# ----------------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------------
def log_agent_login(agent_name):
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        client = gspread.authorize(creds)
        ss = client.open_by_key(SPREADSHEET_ID)

        try:
            log_sheet = ss.worksheet("Logs")
        except gspread.WorksheetNotFound:
            log_sheet = ss.add_worksheet(title="Logs", rows="1000", cols="3")
            log_sheet.append_row(["Timestamp", "Agent Name", "Action"])

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_sheet.append_row([timestamp, agent_name, "Login"])
    except Exception:
        # Preserve original behaviour: login should not fail because logging fails.
        pass


def robust_date_parser(date_value):
    """Parse legacy Google dates using the portal's day-first convention."""
    if pd.isna(date_value):
        return pd.NaT
    if isinstance(date_value, (pd.Timestamp, datetime.datetime, datetime.date)):
        return pd.Timestamp(date_value)

    value = str(date_value).strip()
    if not value or value.lower() in {"nan", "nat", "none", "null"}:
        return pd.NaT

    # ISO / year-first values should remain year-first.
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", value):
        try:
            return pd.to_datetime(value, errors="coerce", yearfirst=True)
        except Exception:
            return pd.NaT

    # Legacy portal data uses day-first dates for slash/dash text values.
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            parsed = pd.to_datetime(value, format=fmt, errors="coerce")
            if not pd.isna(parsed):
                return parsed
        except Exception:
            pass

    try:
        return pd.to_datetime(value, errors="coerce", dayfirst=True, format="mixed")
    except Exception:
        try:
            return pd.to_datetime(value, errors="coerce", dayfirst=True)
        except Exception:
            return pd.NaT


def parse_date_series(series):
    """Parse legacy Google dates consistently as day-first, without dtype comparison issues."""
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for idx, value in series.items():
        result.loc[idx] = robust_date_parser(value)
    return result


def parse_api_date(value):
    """Parse CRM API Sale Date, whose supplied export format is DD-MM-YYYY."""
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date)):
        return pd.Timestamp(value)

    text_value = str(value).strip()
    if not text_value or text_value.lower() in {"nan", "nat", "none", "null"}:
        return pd.NaT

    # The CRM workbook examples are explicitly DD-MM-YYYY.
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            parsed = pd.to_datetime(text_value, format=fmt, errors="coerce")
            if not pd.isna(parsed):
                return parsed
        except Exception:
            pass

    # ISO fallback for future API changes.
    try:
        return pd.to_datetime(text_value, errors="coerce", yearfirst=True, format="mixed")
    except Exception:
        return pd.to_datetime(text_value, errors="coerce", yearfirst=True)


def parse_api_date_series(series):
    """Parse every API date row using the CRM's DD-MM-YYYY contract."""
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for idx, value in series.items():
        result.loc[idx] = parse_api_date(value)
    return result

def normalized_phone(value):
    """Normalize phone numbers for the agreed Sale Date + Phone key."""
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if not value or value.lower() in {"nan", "none", "null", "nat"}:
        return ""
    value = re.sub(r"\.0+$", "", value)

    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""

    # UK-friendly normalization: +44XXXXXXXXXX -> 0XXXXXXXXXX.
    if digits.startswith("44") and len(digits) in {11, 12}:
        digits = "0" + digits[2:]

    return digits


def date_key_value(value):
    parsed = robust_date_parser(value)
    if pd.isna(parsed):
        return ""
    return pd.Timestamp(parsed).strftime("%Y-%m-%d")


def make_record_key(date_value, phone_value):
    """Primary key agreed for source reconciliation."""
    date_key = date_key_value(date_value)
    phone_key = normalized_phone(phone_value)
    if not date_key or not phone_key:
        return ""
    return f"{date_key}|{phone_key}"


def add_record_keys(frame, date_col, phone_col):
    result = frame.copy()
    if date_col in result.columns:
        date_values = result[date_col]
    else:
        date_values = pd.Series([pd.NaT] * len(result), index=result.index)
    if phone_col in result.columns:
        phone_values = result[phone_col]
    else:
        phone_values = pd.Series([""] * len(result), index=result.index)

    result["_RecordKey"] = [
        make_record_key(d, p) for d, p in zip(date_values, phone_values)
    ]
    return result


def existing_google_keys(df1, df2_raw):
    """Return keys from BOTH legacy Google tabs without modifying them."""
    keys = set()

    df1_keyed = add_record_keys(df1, "Standardized_Date", "CLI")
    keys.update(k for k in df1_keyed["_RecordKey"].tolist() if k)

    df2_keyed = add_record_keys(df2_raw, "Sale Date", "Telephone No.")
    keys.update(k for k in df2_keyed["_RecordKey"].tolist() if k)

    return keys


def canonicalize_advisor(raw_name):
    """Map CRM usernames to the portal's login/agent names where possible."""
    raw = str(raw_name).strip()
    if not raw or raw.lower() in {"nan", "none", "null", "nat"}:
        return ""

    # Known API username variants seen in the CRM export.
    aliases = {
        "subhodeeproy": "Subhodeep",
        "priyanshurathee": "Priyanshu",
        "kunalupreti": "Kunal",
    }

    compact = re.sub(r"[^a-z0-9]", "", raw.lower())
    if compact in aliases:
        return aliases[compact]

    candidates = []
    try:
        for value in ACCESS_KEYS.values():
            name = str(value).strip()
            if name:
                candidates.append(name)
    except Exception:
        candidates = []

    # Exact compact match.
    for name in candidates:
        if compact == re.sub(r"[^a-z0-9]", "", name.lower()):
            return name

    # Common CRM convention: username = agent name + surname/handle.
    # Only map when the match is unique, avoiding accidental cross-agent merges.
    prefix_matches = []
    for name in candidates:
        name_compact = re.sub(r"[^a-z0-9]", "", name.lower())
        if len(name_compact) >= 5 and len(compact) >= len(name_compact):
            if compact.startswith(name_compact):
                prefix_matches.append(name)
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    return raw.strip().title()


def clean_reason_text(value):
    if pd.isna(value):
        return ""
    text = str(value).replace("<br>", " | ").replace("<br/>", " | ")
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def combine_api_cancellation_reasons(row):
    fields = [
        ("Quality", "Cancellation Reason - quality"),
        ("Welcome", "Cancellation Reason - welcome"),
        ("Provisioning", "Cancellation/Rejection Reason - Provisioning"),
        ("Dispatch", "Cancellation/Rejection Reason - Dispatch"),
        ("Confirmation", "Cancellation/Rejection Reason - Confirmation"),
        ("Onboarding", "Cancellation/Rejection Reason - Onboarding"),
        ("Potential Opportunity", "Cancellation/Rejection Reason - Potential Opportunity"),
    ]
    parts = []
    for label, col in fields:
        if col in row.index:
            value = clean_reason_text(row[col])
            if value:
                parts.append(f"{label}: {value}")
    return " | ".join(parts)


def fetch_api_excel():
    """Fetch the CRM Excel export.

    The CRM endpoint is known to return an XLSX file.  In practice the API may
    be configured with a Bearer token, X-API-Key, or a raw Authorization token,
    so ``SPARTA_API_AUTH_MODE = "auto"`` tries those common formats only when
    the previous format is rejected with HTTP 401/403.
    """
    if not SPARTA_API_TOKEN:
        return pd.DataFrame(), "API not configured", 0, "API token missing"

    base_headers = {
        "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/octet-stream, */*",
        "User-Agent": "Sparta-Agent-Portal/1.0",
    }

    auth_mode = SPARTA_API_AUTH_MODE
    if auth_mode == "auto":
        auth_variants = [
            ("bearer", {"Authorization": f"Bearer {SPARTA_API_TOKEN}"}),
            ("x-api-key", {"X-API-Key": SPARTA_API_TOKEN}),
            ("authorization-token", {"Authorization": SPARTA_API_TOKEN}),
            ("authorization-token-prefix", {"Authorization": f"Token {SPARTA_API_TOKEN}"}),
        ]
    elif auth_mode in {"bearer", "x-api-key", "authorization-token", "authorization-token-prefix"}:
        auth_variants = []
        if auth_mode == "bearer":
            auth_variants.append((auth_mode, {"Authorization": f"Bearer {SPARTA_API_TOKEN}"}))
        elif auth_mode == "x-api-key":
            auth_variants.append((auth_mode, {"X-API-Key": SPARTA_API_TOKEN}))
        elif auth_mode == "authorization-token":
            auth_variants.append((auth_mode, {"Authorization": SPARTA_API_TOKEN}))
        else:
            auth_variants.append((auth_mode, {"Authorization": f"Token {SPARTA_API_TOKEN}"}))
    else:
        return (
            pd.DataFrame(),
            "API unavailable",
            0,
            f"Invalid SPARTA_API_AUTH_MODE: {SPARTA_API_AUTH_MODE}",
        )

    last_error = None
    last_status = None

    for auth_name, auth_headers in auth_variants:
        headers = {**base_headers, **auth_headers}

        for attempt in range(1, SPARTA_API_MAX_RETRIES + 2):
            try:
                response = requests.get(
                    SPARTA_API_URL,
                    headers=headers,
                    timeout=SPARTA_API_TIMEOUT,
                )

                last_status = response.status_code

                if response.status_code in (401, 403) and auth_mode == "auto":
                    body = (response.text or "").strip().replace("\\n", " ")
                    last_error = (
                        f"HTTP {response.status_code} using {auth_name}"
                        + (f": {body[:250]}" if body else "")
                    )
                    break

                response.raise_for_status()

                if not response.content:
                    raise ValueError("API returned an empty response body.")

                content_type = (response.headers.get("Content-Type") or "").lower()
                if "spreadsheet" not in content_type and "excel" not in content_type and not response.content.startswith(b"PK"):
                    preview = (response.text or "").strip().replace("\\n", " ")[:250]
                    raise ValueError(
                        f"API returned unexpected content type '{content_type}'"
                        + (f": {preview}" if preview else "")
                    )

                api_df = pd.read_excel(BytesIO(response.content), engine="openpyxl")
                api_df.columns = [str(c).replace("\\ufeff", "").strip() for c in api_df.columns]

                missing = [c for c in API_REQUIRED_COLUMNS if c not in api_df.columns]
                if missing:
                    raise ValueError(
                        "API Excel is missing required columns: " + ", ".join(missing)
                    )

                fetched_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return api_df, fetched_at, len(api_df), ""

            except requests.RequestException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                last_status = status or last_status
                body = ""
                try:
                    body = (exc.response.text or "").strip().replace("\\n", " ")[:250]
                except Exception:
                    pass
                last_error = str(exc) + (f" | {body}" if body else "")
                if status in (401, 403) and auth_mode == "auto":
                    break
                if attempt <= SPARTA_API_MAX_RETRIES:
                    time.sleep(min(2 ** (attempt - 1), 6))
            except Exception as exc:
                last_error = str(exc)
                if attempt <= SPARTA_API_MAX_RETRIES:
                    time.sleep(min(2 ** (attempt - 1), 6))

        # In auto mode, move to the next auth scheme after an auth rejection.
        if auth_mode != "auto":
            break

    if last_status in (401, 403) and last_error:
        return pd.DataFrame(), "API forbidden", 0, last_error

    return pd.DataFrame(), "API unavailable", 0, last_error or "Unknown API error"


def _crm_header_token(value):
    """Normalize a CRM worksheet header for case/spacing/punctuation tolerant matching."""
    value = str(value or "").replace("\ufeff", "").replace("\u00a0", " ").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def canonicalize_inbound_columns(frame):
    """Guarantee canonical Inbound Status/Remarks columns from CRM mirror headers.

    Google Sheets headers sometimes vary in capitalization, whitespace, punctuation,
    or use common equivalents such as Inbound Comments. Match those headers before
    constructing portal rows so the fields cannot silently disappear from the log.
    When more than one matching source column exists, prefer the first nonblank value.
    """
    if frame is None:
        return pd.DataFrame(columns=["Inbound Status", "Inbound Remarks"])
    result = frame.copy()
    result.columns = [
        str(col).replace("\\ufeff", "").replace("\ufeff", "").replace("\u00a0", " ").strip()
        for col in result.columns
    ]

    aliases = {
        "Inbound Status": {
            "inboundstatus", "inboundstage", "inboundcallstatus", "currentinboundstatus"
        },
        "Inbound Remarks": {
            "inboundremarks", "inboundremark", "inboundcomments", "inboundcomment",
            "inboundstatusremarks", "inboundstageremarks", "inboundcallremarks"
        },
    }
    for canonical, alias_tokens in aliases.items():
        positions = [
            idx for idx, column in enumerate(result.columns)
            if _crm_header_token(column) in alias_tokens
        ]
        if not positions:
            result[canonical] = ""
            continue

        merged_values = pd.Series("", index=result.index, dtype=object)
        for idx in positions:
            candidate = result.iloc[:, idx]
            if isinstance(candidate, pd.DataFrame):
                # This should only occur for duplicate source headers; coalesce each
                # duplicate series from left to right rather than dropping values.
                for sub_idx in range(candidate.shape[1]):
                    values = candidate.iloc[:, sub_idx]
                    values_text = values.fillna("").astype(str).str.strip()
                    usable = ~values_text.str.lower().isin({"", "nan", "none", "null", "nat"})
                    merged_values = merged_values.where(~usable, values)
            else:
                values_text = candidate.fillna("").astype(str).str.strip()
                usable = ~values_text.str.lower().isin({"", "nan", "none", "null", "nat"})
                merged_values = merged_values.where(~usable, candidate)

        # Remove matched source columns by position and then put back one canonical
        # field, avoiding duplicate labels that make pandas return a DataFrame.
        keep_positions = [idx for idx in range(result.shape[1]) if idx not in positions]
        result = result.iloc[:, keep_positions].copy()
        result[canonical] = merged_values

    return result


def normalize_api_records(api_df):
    """Convert the consolidated API export into the old portal's two logical datasets."""
    if api_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    api = canonicalize_inbound_columns(api_df.copy())
    # Explicitly guarantee the CRM mirror's exact inbound fields are present
    # and retained before any downstream mapping/joins.
    for _inbound_name in ("Inbound Status", "Inbound Remarks"):
        if _inbound_name not in api.columns:
            api[_inbound_name] = ""
        api[_inbound_name] = api[_inbound_name].fillna("").astype(str).map(str.strip)
    for col in API_REQUIRED_COLUMNS:
        if col not in api.columns:
            api[col] = ""

    # Optional CRM fields displayed in Recent Applications Log. Keep them
    # optional so older CRM mirror exports without these columns still load.
    for col in ("Verifier Name", "Agent Remarks", "Inbound Status", "Inbound Remarks"):
        if col not in api.columns:
            api[col] = ""

    api["Date_Parsed"] = parse_api_date_series(api["Sale Date"])
    api["Advisor"] = api["Advisor (Created Username)"].apply(canonicalize_advisor)
    api["Customer Name"] = api["Customer Name"].fillna("").astype(str).str.strip()
    api["Phone Number"] = api["Phone Number"].apply(normalized_phone)
    api["_RecordKey"] = [
        make_record_key(d, p)
        for d, p in zip(api["Sale Date"], api["Phone Number"])
    ]

    # A primary-key record cannot be reconciled safely if either component is missing.
    api = api[api["_RecordKey"] != ""].copy()

    # Keep the latest row when the API itself contains duplicate keys.
    api = api.drop_duplicates(subset=["_RecordKey"], keep="last").reset_index(drop=True)

    quality = api["Quality Status"].fillna("").astype(str).str.strip()
    quality_remarks = api["Quality Remarks (Quality Comments)"].apply(clean_reason_text)
    wc_status = api["Welcome Call Status"].fillna("").astype(str).str.strip()
    wc_remarks = api["Welcome Call Remarks (Welcome Comments)"].apply(clean_reason_text)

    # -----------------------------------------------------------------------
    # Application-side representation (old Sparta sheet shape used by portal)
    # -----------------------------------------------------------------------
    app = pd.DataFrame(index=api.index)
    app["Standardized_Date"] = api["Date_Parsed"]
    app["Date_Parsed"] = api["Date_Parsed"]
    app["Sale Date"] = api["Sale Date"]
    app["Advisor"] = api["Advisor"]
    app["Customer Name"] = api["Customer Name"]
    app["Verifier Name"] = api["Verifier Name"].apply(clean_reason_text)
    app["Agent Remarks"] = api["Agent Remarks"].apply(clean_reason_text)
    app["Inbound Status"] = api["Inbound Status"].apply(clean_reason_text)
    app["Inbound Remarks"] = api["Inbound Remarks"].apply(clean_reason_text)
    app["CLI"] = api["Phone Number"]
    app["Quality Status"] = quality
    app["Quality Remarks"] = quality_remarks
    app["Status"] = wc_status
    app["Welcome call Remarks"] = wc_remarks
    app["Source"] = "CRM Mirror"
    app["_RecordKey"] = api["_RecordKey"]

    # -----------------------------------------------------------------------
    # Portal-side representation (old Sparta2 shape used by portal)
    # -----------------------------------------------------------------------
    portal = pd.DataFrame(index=api.index)
    portal["Sale Date"] = api["Sale Date"]
    portal["Date_Parsed"] = api["Date_Parsed"]
    portal["Agent"] = api["Advisor"]
    portal["Advisor"] = api["Advisor"]
    portal["Customer Name"] = api["Customer Name"]
    portal["Telephone No."] = api["Phone Number"]
    portal["Status"] = api["Committed (Live) Status (Onboarding Status)"].fillna("").astype(str).str.strip()
    portal["LetterStatus"] = api["LetterStatus (Dispatch Status)"].fillna("").astype(str).str.strip()
    # Keep the API's provisioning fields under the dashboard's short internal
    # names so the Recent Applications Log can use them directly.
    portal["Provisioning Status"] = api["Provisioning Status"].fillna("").astype(str).str.strip()
    portal["Provisioning Remarks"] = api["Provisioning Remarks (Provisioning Comments)"].apply(clean_reason_text)
    portal["CallStatus"] = api["Confirmation Status"].fillna("").astype(str).str.strip()
    portal["Comments"] = api["Confirmation Comment"].apply(clean_reason_text)
    portal["Voice of Customer"] = ""
    portal["Cancellation Reason"] = api.apply(combine_api_cancellation_reasons, axis=1)
    portal["Committed Date"] = pd.NaT
    portal["Source"] = "CRM Mirror"
    portal["_RecordKey"] = api["_RecordKey"]

    return app.reset_index(drop=True), portal.reset_index(drop=True)


def fetch_crm_mirror(client):
    """Read the exact CRM mirror worksheet by its configured Google Sheets GID.

    Use get_all_values() rather than relying on gspread's record conversion so
    the literal CRM header row (including Inbound Status and Inbound Remarks)
    is preserved and mapped explicitly. This avoids those fields silently
    disappearing if record conversion/header handling differs across versions.
    """
    fetched_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        crm_ws = spreadsheet.get_worksheet_by_id(CRM_MIRROR_WORKSHEET_GID)
        raw_values = crm_ws.get_all_values()
    except Exception as exc:
        return pd.DataFrame(), fetched_at, 0, f"CRM mirror sheet unavailable: {exc}"

    if not raw_values or not any(str(v).strip() for v in raw_values[0]):
        return pd.DataFrame(), fetched_at, 0, "CRM mirror sheet is empty or has no header row"

    headers = [
        str(c).replace("\ufeff", "").replace("\u00a0", " ").strip()
        for c in raw_values[0]
    ]
    # Remove only trailing empty header cells; keep the source column order intact.
    while headers and not headers[-1]:
        headers.pop()
    body = []
    for raw_row in raw_values[1:]:
        row = list(raw_row[:len(headers)])
        if len(row) < len(headers):
            row.extend([""] * (len(headers) - len(row)))
        body.append(row)
    crm_df = pd.DataFrame(body, columns=headers)
    if crm_df.empty:
        return crm_df, fetched_at, 0, "CRM mirror sheet contains headers but no data rows"

    # Preserve the exact two requested source fields first, then canonicalise
    # aliases/spacing as a fallback for older variants of the mirror export.
    for canonical in ("Inbound Status", "Inbound Remarks"):
        exact_matches = [col for col in crm_df.columns if str(col).strip() == canonical]
        if exact_matches:
            crm_df[canonical] = crm_df[exact_matches[0]].fillna("").astype(str)
    crm_df = canonicalize_inbound_columns(crm_df)

    # Make sure these exact CRM fields survive normalization even when every
    # value is blank in the current data slice.
    for canonical in ("Inbound Status", "Inbound Remarks"):
        if canonical not in crm_df.columns:
            crm_df[canonical] = ""
        crm_df[canonical] = crm_df[canonical].fillna("").astype(str).map(str.strip)

    missing = [c for c in API_REQUIRED_COLUMNS if c not in crm_df.columns]
    if missing:
        return pd.DataFrame(), "CRM mirror invalid", 0, (
            "CRM mirror is missing required columns: " + ", ".join(missing)
        )

    return crm_df, fetched_at, len(crm_df), ""


def normalize_attendance_status(value):
    """Convert the attendance sheet's raw value to the portal display code."""
    if pd.isna(value):
        return "-"
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "nat", "-"}:
        return "-"
    if text.upper() == "UL":
        return "UL"

    try:
        number = float(text)
    except (TypeError, ValueError):
        return text.upper()

    if number == 0:
        return "Ab"
    if number == 0.5:
        return "HD"
    if number == 1:
        return "P"

    # Preserve unexpected values rather than silently hiding them.
    return str(value).strip()


def fetch_attendance_sheet(client):
    """Read the dedicated Attendance worksheet and normalize its fields."""
    try:
        ws = client.open_by_key(SPREADSHEET_ID).get_worksheet_by_id(ATTENDANCE_WORKSHEET_GID)
        values = ws.get_all_records()
        df = pd.DataFrame(values)
    except Exception as exc:
        return pd.DataFrame(), f"Attendance sheet unavailable: {exc}"

    if df.empty:
        return pd.DataFrame(), "Attendance sheet is empty"

    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    required = ["Name", "Date", "Attendance"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return pd.DataFrame(), "Attendance sheet missing columns: " + ", ".join(missing)

    df["Date_Parsed"] = parse_date_series(df["Date"])
    df["Attendance_Code"] = df["Attendance"].apply(normalize_attendance_status)
    df["Attendance_Agent"] = df["Name"].apply(canonicalize_advisor)
    df["Name"] = df["Name"].fillna("").astype(str).str.strip()

    # Keep only usable date rows. Duplicate Name/Date entries are reduced to
    # the last supplied value, matching how the sheet is maintained.
    df = df[df["Date_Parsed"].notna()].copy()
    df = df.drop_duplicates(subset=["Attendance_Agent", "Date_Parsed"], keep="last")

    return df.reset_index(drop=True), ""


def _legacy_header_key(value):
    """Normalize a legacy worksheet header for tolerant column matching."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").replace("\ufeff", "").replace("\u00a0", " ").casefold())


def normalize_legacy_sheet_columns(frame, sheet_name):
    """Resolve known legacy header variants without changing source status columns.

    The two historical tabs have had minor header variations over time.  The
    downstream app requires a small set of canonical date/advisor/phone fields
    before it applies the legacy cutoff; if one of those headers differs by a
    space, underscore, or alias, the prior loader would otherwise silently
    discard every row as undated or unattributed.
    """
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    result = frame.copy()
    if result.empty:
        return result

    if str(sheet_name).strip().casefold() == "sparta":
        specs = {
            "Standardized_Date": ["Standardized_Date", "Standardized Date", "Sale Date", "Application Date", "App Date", "Date"],
            "Advisor": ["Advisor", "Agent", "Agent Name", "Sales Agent", "Created Username", "Created By", "Username", "User Name"],
            "CLI": ["CLI", "Telephone No.", "Telephone Number", "Phone Number", "Phone", "Mobile", "Mobile Number", "Customer Phone", "Contact Number"],
        }
    else:
        specs = {
            "Sale Date": ["Sale Date", "SaleDate", "Standardized_Date", "Standardized Date", "Application Date", "App Date", "Date"],
            "Agent": ["Agent", "Advisor", "Agent Name", "Sales Agent", "Created Username", "Created By", "Username", "User Name"],
            "Telephone No.": ["Telephone No.", "Telephone Number", "Phone Number", "Phone", "CLI", "Mobile", "Mobile Number", "Customer Phone", "Contact Number"],
        }

    # Choose an exact known alias with the most nonblank values. Prefer the
    # canonical header on ties so normal worksheets are left untouched.
    columns = list(result.columns)
    for canonical, aliases in specs.items():
        alias_keys = {_legacy_header_key(alias) for alias in aliases}
        candidates = [col for col in columns if _legacy_header_key(col) in alias_keys]
        if not candidates:
            continue
        def nonblank_count(col):
            values = result[col]
            return int(values.map(lambda v: bool(str(v).strip()) and str(v).strip().casefold() not in {"nan", "none", "null", "nat"}).sum())
        candidates.sort(key=lambda col: (nonblank_count(col), _legacy_header_key(col) == _legacy_header_key(canonical)), reverse=True)
        selected = candidates[0]
        if canonical not in result.columns:
            result[canonical] = result[selected]
        elif selected != canonical:
            current_count = nonblank_count(canonical)
            selected_count = nonblank_count(selected)
            # Repair a blank placeholder canonical column if a populated alias
            # exists, but never overwrite a canonical field with less data.
            if selected_count > current_count:
                blank_mask = result[canonical].isna() | result[canonical].astype(str).str.strip().eq("")
                result.loc[blank_mask, canonical] = result.loc[blank_mask, selected]
    return result


def worksheet_to_dataframe_by_gid(spreadsheet, worksheet_gid, source_label):
    """Read a worksheet by its exact GID while preserving its literal headers.

    get_all_records() can be fragile when legacy workbook tabs contain empty
    header cells or repeated `Unnamed:` columns. This reader keeps all actual
    source columns, assigns a stable placeholder only to genuinely blank
    header cells, and ensures duplicate labels do not overwrite one another.
    """
    worksheet = spreadsheet.get_worksheet_by_id(int(worksheet_gid))
    raw_values = worksheet.get_all_values()
    if not raw_values:
        return pd.DataFrame()

    raw_headers = list(raw_values[0])
    body = list(raw_values[1:])
    width = max([len(raw_headers)] + [len(row) for row in body]) if body else len(raw_headers)
    if width == 0:
        return pd.DataFrame()
    raw_headers.extend([""] * (width - len(raw_headers)))

    headers = []
    used = set()
    for index, raw_header in enumerate(raw_headers):
        header = str(raw_header or "").replace("\ufeff", "").replace("\u00a0", " ").strip()
        if not header:
            # Use a private placeholder for an actually blank cell so a real
            # source header such as the literal text "Unnamed: 47" is preserved.
            header = f"__blank_header_{index}"
        candidate = header
        suffix = 2
        while candidate in used:
            candidate = f"{header}__{suffix}"
            suffix += 1
        used.add(candidate)
        headers.append(candidate)

    normalized_rows = []
    for row in body:
        values = list(row[:width])
        if len(values) < width:
            values.extend([""] * (width - len(values)))
        if not any(str(value).strip() for value in values):
            continue
        normalized_rows.append(values)

    frame = pd.DataFrame(normalized_rows, columns=headers)
    # Avoid treating the label as an added data column; it is useful in errors.
    return frame


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def fetch_data():
    """Load legacy history through 17-Sep-2026 and newer records from CRM mirror.

    Source rules:
      * Sparta / Sparta2 legacy tabs: Sale Date <= 17-Sep-2026 only.
      * CRM mirror worksheet: Sale Date >= 18-Sep-2026 only.

    This prevents the same post-cutover record from being sourced from the
    legacy tabs and ensures CRM is the sole source for newer records.
    """
    # =============================== GOOGLE ================================
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    client = gspread.authorize(creds)
    ss = client.open_by_key(SPREADSHEET_ID)

    # Attendance is maintained in a dedicated worksheet in the same workbook.
    attendance_df, attendance_error = fetch_attendance_sheet(client)

    # -----------------------------------------------------------------------
    # LEGACY SPARTA — inclusive through 17-Sep-2026 only
    # -----------------------------------------------------------------------
    # The worksheet IDs are explicit because the workbook has several tabs and
    # the legacy headers include blank/Unnamed columns. Preserve actual header
    # labels so the Excel summary only uses fields present in this source.
    df1 = worksheet_to_dataframe_by_gid(ss, SPARTA_WORKSHEET_GID, "Sparta")
    df1 = normalize_legacy_sheet_columns(df1, "Sparta")
    if df1.empty:
        df1 = pd.DataFrame(columns=["Standardized_Date", "Advisor", "Quality Status", "CLI", "Customer Name"])
    if "Standardized_Date" not in df1.columns:
        df1["Standardized_Date"] = pd.NaT
    if "Advisor" not in df1.columns:
        df1["Advisor"] = ""
    if "CLI" not in df1.columns:
        df1["CLI"] = ""
    df1["Date_Parsed"] = parse_date_series(df1["Standardized_Date"])
    df1["Advisor"] = df1["Advisor"].astype(str).str.strip().str.title()
    df1["Source"] = "Google - Sparta"

    legacy_sparta_total = len(df1)
    df1 = df1[
        df1["Date_Parsed"].notna()
        & (df1["Date_Parsed"] <= LEGACY_SOURCE_CUTOFF)
    ].copy()

    # -----------------------------------------------------------------------
    # LEGACY SPARTA2 — inclusive through 17-Sep-2026 only
    # -----------------------------------------------------------------------
    df2_raw = worksheet_to_dataframe_by_gid(ss, SPARTA2_WORKSHEET_GID, "Sparta2")
    df2_raw = normalize_legacy_sheet_columns(df2_raw, "Sparta2")
    if df2_raw.empty:
        df2_raw = pd.DataFrame(columns=["Sale Date", "Agent", "Status", "Telephone No."])
    if "Sale Date" not in df2_raw.columns:
        df2_raw["Sale Date"] = pd.NaT
    if "Agent" not in df2_raw.columns:
        df2_raw["Agent"] = ""
    if "Telephone No." not in df2_raw.columns:
        df2_raw["Telephone No."] = ""
    df2_raw["Date_Parsed"] = parse_date_series(df2_raw["Sale Date"])
    df2_raw["Advisor"] = df2_raw["Agent"].astype(str).str.strip().str.title()
    df2_raw["Source"] = "Google - Sparta2"

    legacy_sparta2_total = len(df2_raw)
    df2_raw = df2_raw[
        df2_raw["Date_Parsed"].notna()
        & (df2_raw["Date_Parsed"] <= LEGACY_SOURCE_CUTOFF)
    ].copy()

    try:
        meta = ss.worksheet("Meta").get_all_values()
        google_last_sync = meta[0][1] if meta and len(meta[0]) > 1 else "Unknown"
    except Exception:
        google_last_sync = "Unknown"

    # ============================ CRM MIRROR ==============================
    # The independent sync job writes the current CRM Excel export to the
    # dedicated Google worksheet. The portal reads ONLY post-cutover records
    # from this CRM mirror.
    api_df, api_fetched_at, api_row_count, api_error = fetch_crm_mirror(client)

    crm_total_before_cutover = len(api_df)
    crm_cutover_excluded = 0
    crm_invalid_dates = 0

    if not api_df.empty:
        if "Sale Date" in api_df.columns:
            crm_dates = parse_api_date_series(api_df["Sale Date"])
            crm_invalid_dates = int(crm_dates.isna().sum())
            crm_mask = crm_dates.notna() & (crm_dates >= CRM_SOURCE_START)
            crm_cutover_excluded = int((crm_dates.notna() & (crm_dates < CRM_SOURCE_START)).sum())
            api_df = api_df.loc[crm_mask].copy()
        else:
            api_df = pd.DataFrame()

    api_app, api_portal = normalize_api_records(api_df)

    # Since the legacy sources stop at 17-Sep-2026, CRM is the sole authority
    # for all records from 18-Sep-2026 onward. Still guard against duplicate
    # keys inside the CRM export itself (normalize_api_records already keeps
    # the latest row for duplicate CRM keys).
    new_api_app = api_app.copy()
    new_api_portal = api_portal.copy()

    # Concatenate the two logical datasets. No post-cutover legacy records can
    # enter because of the explicit cutoff above.
    df1_combined = pd.concat([df1, new_api_app], ignore_index=True, sort=False)
    df2_combined = pd.concat([df2_raw, new_api_portal], ignore_index=True, sort=False)

    # Final date/advisor normalization after the merge.
    df1_combined["Date_Parsed"] = parse_date_series(df1_combined["Date_Parsed"])
    df2_combined["Date_Parsed"] = parse_date_series(df2_combined["Date_Parsed"])
    df1_combined["Advisor"] = df1_combined["Advisor"].fillna("").astype(str).str.strip()
    df2_combined["Advisor"] = df2_combined["Advisor"].fillna("").astype(str).str.strip()

    # Keep the on-screen sync status useful without exposing the source token.
    status_lines = [
        f"Legacy cutoff: {LEGACY_SOURCE_CUTOFF.strftime('%d-%b-%Y')}",
        f"Legacy Sparta rows: {len(df1):,} of {legacy_sparta_total:,}",
        f"Legacy Sparta2 rows: {len(df2_raw):,} of {legacy_sparta2_total:,}",
        f"CRM mirror sync: {api_fetched_at}",
        f"CRM mirror rows: {api_row_count:,}",
        f"CRM post-cutover rows: {len(new_api_app):,}",
    ]

    if crm_cutover_excluded:
        status_lines.append(f"CRM rows before cutover ignored: {crm_cutover_excluded:,}")
    if crm_invalid_dates:
        status_lines.append(f"CRM rows with invalid Sale Date ignored: {crm_invalid_dates:,}")

    if api_error:
        status_lines.append(f"CRM mirror warning: {api_error}")
        connection_status = "Google connected • CRM mirror unavailable"
    else:
        connection_status = "Google history + CRM post-cutover connected"

    if attendance_error:
        status_lines.append(f"Attendance warning: {attendance_error}")
    else:
        status_lines.append(f"Attendance rows: {len(attendance_df):,}")

    return df1_combined, df2_combined, attendance_df, "\n".join(status_lines), connection_status


def map_quality(val):
    """Map quality-audit source values to stable reporting categories.

    QA-Cancelled remains in QA-Pending, matching the Executive Dashboard's
    quality-stage convention. Only workflow status is inspected; remarks are
    not used to infer a category.
    """
    s = normalize_workflow_status(val)
    if not s:
        return "Others"

    # Check explicit pending-stage values before generic cancellation tokens.
    if s in {"qa pending", "qa-pending", "pending", "qa cancelled", "qa-cancelled"}:
        return "QA-Pending"
    if s.startswith(("qa pending ", "qa-pending ", "qa cancelled ", "qa-cancelled ")):
        return "QA-Pending"
    if "rework" in s or "rework required" in s or s.startswith(("rew", "repro")):
        return "Rework"
    if "reject" in s or s.startswith("rej"):
        return "Rejected"
    if "cancel" in s:
        return "Cancelled"
    if "approved" in s or "approve" in s or "pass" in s:
        return "Approved"
    return "Others"


def map_wc(val):
    """Normalize Welcome Call outcomes; Welcome Rejected belongs to Cancelled."""
    try:
        if pd.isna(val):
            return "Others"
    except (TypeError, ValueError):
        pass
    s = str(val).strip().lower()
    if not s or s in {"none", "nan", "nat", "null", "-", "n/a"}:
        return "Others"
    # This check intentionally precedes positive/pending matching.
    if any(token in s for token in ("cancel", "reject", "rejected", "rej")):
        return "Cancelled"
    if any(token in s for token in ("done", "pass", "comp", "approved", "approve")):
        return "Done"
    if any(token in s for token in ("follow", "f/u", "f u")):
        return "Follow up"
    if any(token in s for token in ("pend", "pnd", "other work", "delay")):
        return "Pending"
    if any(token in s for token in ("paper", "ppw")):
        return "Paperwork"
    return "Others"


def map_wc_with_quality(welcome_value, quality_value):
    """Map Welcome Call status, treating otherwise-unknown WC as Pending when QA is pending/rework."""
    welcome_status = map_wc(welcome_value)
    quality_status = map_quality(quality_value)
    if welcome_status == "Others" and quality_status in {"QA-Pending", "Rework"}:
        return "Pending"
    return welcome_status


# ---------------------------------------------------------------------------
# CENTRAL, MUTUALLY EXCLUSIVE DOWNSTREAM CLASSIFICATION
# ---------------------------------------------------------------------------
DOWNSTREAM_CATEGORY_ORDER = [
    "Live",
    "Committed Rem.",
    "Committed Cancelled",
    "Live Cancelled",
    "Unclassified / Review",
]
# Main Live Status cards and previous-period trend cards use exactly the same
# mutually exclusive reporting categories.
LIVE_KPI_STATUS_ORDER = list(DOWNSTREAM_CATEGORY_ORDER)


def normalize_workflow_status(value):
    """Normalise a *status field* without inspecting comments/reason text."""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "none", "null", "nat", "-", "n/a"}:
        return ""
    # Harmonise visually equivalent hyphens / repeated whitespace while
    # retaining the words that distinguish business statuses.
    raw = raw.replace("\u2010", "-").replace("\u2011", "-")
    raw = raw.replace("\u2012", "-").replace("\u2013", "-").replace("\u2014", "-")
    raw = re.sub(r"\s*[-]+\s*", " ", raw)
    raw = re.sub(r"\s*:\s*", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip().lower()
    return raw


def _is_explicit_cancel_status(value):
    """Recognise explicit terminal cancellation/rejection in a status field."""
    status = normalize_workflow_status(value)
    if not status:
        return False
    exact = {
        "cancel", "cancelled", "canceled", "rejected", "reject", "rejection",
        "to be cancelled", "to be canceled", "order cancelled", "order canceled",
        "connectivity order cancelled", "connectivity order canceled",
        "onboarding cancelled", "onboarding canceled", "onboarding rejected",
        "live cancelled", "live canceled", "live rejected",
        "port cancelled", "port canceled", "port rejected",
    }
    if status in exact:
        return True
    # Status values may include a brief, structured qualifier (e.g. "Order
    # Cancelled by Provider"). Do not search free-text remarks/reasons here.
    return status.startswith((
        "cancelled ", "canceled ", "rejected ", "reject ",
        "to be cancelled ", "to be canceled ",
        "order cancelled ", "order canceled ",
        "connectivity order cancelled ", "connectivity order canceled ",
        "onboarding cancelled ", "onboarding canceled ", "onboarding rejected ",
        "live cancelled ", "live canceled ", "live rejected ",
        "port cancelled ", "port canceled ", "port rejected ",
    ))


def _is_confirmation_cancel_status(value):
    """Recognise an explicit cancellation outcome in the Confirmation field."""
    status = normalize_workflow_status(value)
    if not status:
        return False
    if status in {
        "to be cancelled", "to be canceled", "cancel", "cancelled", "canceled",
        "reject", "rejected", "rejection", "confirmation cancelled",
        "confirmation canceled", "confirmation rejected",
    }:
        return True
    return status.startswith((
        "to be cancelled ", "to be canceled ", "confirmation cancelled ",
        "confirmation canceled ", "confirmation rejected ",
    ))


def _is_confirmation_progress_status(value):
    """Known confirmation progress values; unknown values remain unknown."""
    status = normalize_workflow_status(value)
    if not status:
        return False
    prefixes = (
        "confirmation approved", "confirmation followup", "confirmation follow up",
        "confirmation pending",
    )
    if status.startswith(prefixes):
        return True
    return status in {
        # Older Sparta2 exports sometimes store the shorter status labels.
        "approved", "approve", "followup", "follow up", "pending", "pnd",
        "committed", "committed rem", "committed reminder", "committed pending",
    }


def _onboarding_state(value):
    """Return live / cancelled / committed-pending / blank / unknown."""
    status = normalize_workflow_status(value)
    if not status:
        return "blank"

    # These exact current outcomes are explicitly known to mean Live.
    # Normalisation makes Port-Pending and Port Pending equivalent.
    if status in {
        "onboarding approved", "port pending", "live", "live approved",
        "onboarding live",
    } or status.startswith("live "):
        return "live"

    # A cancellation/rejection stated in the primary onboarding outcome is a
    # downstream/live-stage cancellation, not a confirmation-stage cancellation.
    if _is_explicit_cancel_status(status):
        return "live_cancelled"

    if status in {
        "committed", "committed rem", "committed reminder", "committed pending",
        "committed live",
    } or status.startswith("committed "):
        return "committed"

    # Preserve established legacy mappings for clear pending/other-work/delay
    # status values. The primary Port Pending live outcome was handled above.
    if status in {
        "onboarding pending", "pending onboarding", "pending", "pnd",
        "other work", "other work assigned", "delayed", "delay", "in progress",
        "provisioning pending", "dispatch pending", "onboarding in progress",
    } or "pending" in status or "other work" in status or "delay" in status:
        return "pending"

    return "unknown"


def classify_downstream_record(row):
    """Return (category, review_flag) for exactly one downstream record.

    Precedence:
      1. A decisive primary onboarding Live/cancelled outcome wins; contradictory
         downstream stage values set a review flag rather than double-counting.
      2. With a known primary onboarding status, an explicit confirmation-stage
         cancellation is Committed Cancelled; confirmation approval alone never
         overrides Onboarding Pending.
      3. Known committed/pending onboarding outcomes become Committed Rem.
      4. With a blank onboarding status, decisive Confirmation status values may
         classify the record. Explicit Provisioning/Dispatch cancellation is
         Live Cancelled only if there is no contradictory later confirmation.
      5. Unknown primary statuses and genuinely inconclusive blanks remain
         Unclassified / Review. Comments/reason fields are never used as flags.
    """
    if hasattr(row, "get"):
        primary_raw = row.get("Status", "")
        confirmation_raw = row.get("CallStatus", row.get("Confirmation Status", ""))
        provisioning_raw = row.get("Provisioning Status", "")
        dispatch_raw = row.get("LetterStatus", row.get("Dispatch Status", ""))
    else:
        primary_raw = ""
        confirmation_raw = ""
        provisioning_raw = ""
        dispatch_raw = ""

    confirmation = normalize_workflow_status(confirmation_raw)
    primary_state = _onboarding_state(primary_raw)
    confirmation_cancel = _is_confirmation_cancel_status(confirmation_raw)
    confirmation_progress = _is_confirmation_progress_status(confirmation_raw)
    provisioning_cancel = _is_explicit_cancel_status(provisioning_raw)
    dispatch_cancel = _is_explicit_cancel_status(dispatch_raw)
    earlier_stage_cancel = provisioning_cancel or dispatch_cancel

    # The current primary onboarding outcome is authoritative when it is a
    # decisive terminal outcome. Contradictions are visible for investigation.
    if primary_state == "live":
        conflicts = []
        if confirmation_cancel:
            conflicts.append("Confirmation shows cancellation while onboarding shows Live")
        if earlier_stage_cancel:
            conflicts.append("Provisioning/Dispatch shows cancellation while onboarding shows Live")
        return "Live", "; ".join(conflicts)

    if primary_state == "live_cancelled":
        conflicts = []
        if confirmation_progress:
            conflicts.append("Confirmation progress conflicts with onboarding cancellation/rejection")
        if confirmation_cancel:
            conflicts.append("Confirmation cancellation may be pre-Live while onboarding indicates Live Cancelled")
        return "Live Cancelled", "; ".join(conflicts)

    # A non-empty, unknown onboarding value is not overridden by lower-stage
    # fields: keep it visible and flag for review rather than invent meaning.
    if primary_state == "unknown":
        return "Unclassified / Review", (
            f"Unrecognised onboarding status: {str(primary_raw).strip()}"
        )

    # A specific confirmation cancellation belongs to Committed Cancelled only
    # when onboarding has not already established a Live/Live Cancelled outcome.
    if confirmation_cancel:
        return "Committed Cancelled", ""

    if primary_state in {"committed", "pending"}:
        flag = ""
        if earlier_stage_cancel:
            flag = "Onboarding is committed/pending but Provisioning/Dispatch shows cancellation/rejection"
        return "Committed Rem.", flag

    # Primary onboarding status is blank. A valid confirmation stage can establish
    # a committed/reminder outcome, but not Live solely from Confirmation Approved.
    if primary_state == "blank":
        # A true legacy Live value in CallStatus is retained for historical rows;
        # CRM Confirmation Approved is deliberately handled as Committed Rem.
        if confirmation in {"live", "live approved", "onboarding approved", "port pending"}:
            flag = "Legacy Live outcome is stored in CallStatus; verify source mapping"
            if earlier_stage_cancel:
                flag += "; Provisioning/Dispatch cancellation also present"
            return "Live", flag

        if confirmation_progress:
            flag = ""
            if earlier_stage_cancel:
                flag = "Confirmation progress conflicts with Provisioning/Dispatch cancellation/rejection"
            return "Committed Rem.", flag

        # A non-empty unknown confirmation status prevents an earlier-stage
        # cancellation from being treated as a definitive terminal outcome.
        if confirmation:
            return "Unclassified / Review", f"Unrecognised confirmation status with blank onboarding status: {str(confirmation_raw).strip()}"

        if earlier_stage_cancel:
            return "Live Cancelled", "Cancellation/rejection identified from an explicit Provisioning/Dispatch status; onboarding/confirmation are blank"

        return "Unclassified / Review", "Onboarding and confirmation statuses are blank"

    return "Unclassified / Review", "Status combination requires review"


def classify_downstream_frame(frame):
    """Attach the one central category and any conflict/review flag to a copy."""
    result = frame.copy()
    if result.empty:
        result["Downstream_Category"] = pd.Series(index=result.index, dtype="object")
        result["Downstream_Review_Flag"] = pd.Series(index=result.index, dtype="object")
        result["P_Status"] = result["Downstream_Category"]
        return result
    classified = [classify_downstream_record(row) for _, row in result.iterrows()]
    result["Downstream_Category"] = [value[0] for value in classified]
    result["Downstream_Review_Flag"] = [value[1] for value in classified]
    # Compatibility alias for existing charts / insights; this is no longer a
    # separate classification rule.
    result["P_Status"] = result["Downstream_Category"]
    return result


def map_portal(val):
    """Compatibility wrapper; all downstream mapping goes through one classifier."""
    return classify_downstream_record({"Status": val})[0]


def map_live_kpi_status(primary_status, call_status="", provisioning_status="", dispatch_status=""):
    """Compatibility wrapper for the central classifier, including legacy fallback fields."""
    return classify_downstream_record({
        "Status": primary_status,
        "CallStatus": call_status,
        "Provisioning Status": provisioning_status,
        "LetterStatus": dispatch_status,
    })[0]


def build_wc_done_live_kpi_rows(apps_frame, portal_frame, welcome_status_col):
    """Return only downstream rows whose matching application is WC Done/Approved.

    Uses the same Sale Date + phone record key already used by the Recent
    Applications Log. The source dataframes are copied, so the detailed log and
    daily/monthly breakdown remain unchanged by this KPI-only eligibility rule.
    """
    if (
        apps_frame is None or portal_frame is None
        or apps_frame.empty or portal_frame.empty
        or not welcome_status_col or welcome_status_col not in apps_frame.columns
    ):
        empty = portal_frame.iloc[0:0].copy() if portal_frame is not None else pd.DataFrame()
        empty["Live_KPI_Status"] = pd.Series(dtype="object")
        return empty

    apps_done = apps_frame[apps_frame[welcome_status_col].apply(map_wc) == "Done"].copy()
    if apps_done.empty:
        empty = portal_frame.iloc[0:0].copy()
        empty["Live_KPI_Status"] = pd.Series(dtype="object")
        return empty

    if "Standardized_Date" not in apps_done.columns:
        apps_done["Standardized_Date"] = apps_done.get("Date_Parsed", pd.NaT)
    if "CLI" not in apps_done.columns:
        apps_done["CLI"] = ""
    apps_done = add_record_keys(apps_done, "Standardized_Date", "CLI")
    wc_done_keys = {
        str(key) for key in apps_done["_RecordKey"].tolist()
        if key and str(key).strip()
    }
    if not wc_done_keys:
        empty = portal_frame.iloc[0:0].copy()
        empty["Live_KPI_Status"] = pd.Series(dtype="object")
        return empty

    portal = portal_frame.copy()
    if "Sale Date" not in portal.columns:
        portal["Sale Date"] = portal.get("Date_Parsed", pd.NaT)
    if "Telephone No." not in portal.columns:
        portal["Telephone No."] = ""
    if "Status" not in portal.columns:
        portal["Status"] = ""
    if "CallStatus" not in portal.columns:
        portal["CallStatus"] = ""

    portal = add_record_keys(portal, "Sale Date", "Telephone No.")
    portal = portal[portal["_RecordKey"].astype(str).isin(wc_done_keys)].copy()
    # Classification is calculated once on the full downstream frame upstream.
    # Reuse it here so eligibility remains a separate decision from category.
    if "Downstream_Category" not in portal.columns:
        portal = classify_downstream_frame(portal)
    portal["Live_KPI_Status"] = portal["Downstream_Category"]
    if "Downstream_Review_Flag" not in portal.columns:
        portal["Downstream_Review_Flag"] = ""
    return portal


def date_range_mask(series, start_date, end_date):
    """Safe timestamp comparison for pandas datetime64[s]/datetime64[ns]/object."""
    parsed = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=True)
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    return (parsed >= start_ts) & (parsed < end_ts)

def initials(name):
    parts = [p for p in str(name).split() if p]
    if not parts:
        return "A"
    return "".join(p[0] for p in parts[:2]).upper()


def render_section(title, icon="◆", subtitle=None):
    subtitle_html = (
        f'<div class="section-subtitle">{escape(subtitle)}</div>'
        if subtitle else ""
    )
    st.html(
        f"""
        <div class="section-title">
            <span class="icon">{escape(icon)}</span>
            <span>{escape(title)}</span>
        </div>
        {subtitle_html}
        """
    )


def trend_badge_html(label, current, previous):
    """Compact count trend versus the immediately preceding equal-length period."""
    if previous is None:
        return ""

    try:
        current = int(current)
        previous = int(previous)
    except (TypeError, ValueError):
        return ""

    delta = current - previous
    if delta == 0:
        text_value = "→ unchanged"
        css_class = "flat"
    else:
        arrow = "↑" if delta > 0 else "↓"
        if previous == 0:
            text_value = f"{arrow} {abs(delta):,} vs 0"
        else:
            pct_change = abs(delta) / abs(previous) * 100
            text_value = f"{arrow} {abs(delta):,} ({pct_change:.0f}%)"

        label_lower = str(label).strip().lower()
        unfavourable_when_up = any(token in label_lower for token in (
            "rework", "cancel", "reject", "pending", "paperwork"
        ))
        favourable_when_up = any(token in label_lower for token in (
            "total apps", "approved", "done", "live", "committed"
        ))

        if unfavourable_when_up:
            css_class = "bad" if delta > 0 else "good"
        elif favourable_when_up:
            css_class = "good" if delta > 0 else "bad"
        else:
            css_class = "neutral"

    return f'<div><span class="kpi-trend kpi-trend-{css_class}" title="Change versus immediately preceding period">{escape(text_value)}</span></div>'


def render_kpi(label, value, total, previous_count=None):
    lbl = str(label).lower()
    accent = "#94A3B8"

    # Cancellation/rejection must win over terms such as "Live" or
    # "Committed" in the same category label, so terminal-loss cards are red.
    if "can" in lbl or "rej" in lbl:
        accent = "#EF4444"
    elif "total" in lbl:
        accent = "#3B82F6"
    elif any(x in lbl for x in ["appr", "done", "live"]):
        accent = "#10B981"
    elif any(x in lbl for x in ["rew", "pend", "paper", "comm"]):
        accent = "#F59E0B"

    percent = (value / total * 100) if total > 0 else 0
    pc_html = (
        f'<div><span class="kpi-pc">{percent:.1f}%</span></div>'
        if "total apps" not in lbl
        else ""
    )
    trend_html = trend_badge_html(label, value, previous_count)

    st.html(
        f"""
        <div class="kpi-card" style="border-top:4px solid {accent};">
            <p class="kpi-label">{escape(str(label))}</p>
            <p class="kpi-value">{value:,}</p>
            {pc_html}
            {trend_html}
        </div>
        """
    )


def kpi_panel(title, kpis, previous_counts=None):
    previous_counts = previous_counts or {}
    # Do not render zero-valued KPI cards, even if the previous period had
    # activity. The panel reflects only non-zero values in the selected range.
    active = [x for x in kpis if x[1] > 0]
    if not active:
        return

    with st.container(border=True):
        st.markdown(f"**{escape(title)}**")
        cols = st.columns(len(active))
        for i, kpi in enumerate(active):
            with cols[i]:
                render_kpi(
                    kpi[0], kpi[1], kpi[2],
                    previous_count=previous_counts.get(kpi[0]),
                )


def pct(value, total):
    if not total:
        return 0.0
    return (value / total) * 100


def comparison_delta(current, previous, is_rate=False):
    if is_rate:
        delta = current - previous
        if abs(delta) < 0.05:
            return "→ 0.0 pp", "flat"
        return (f"↑ {abs(delta):.1f} pp" if delta > 0 else f"↓ {abs(delta):.1f} pp"), ("up" if delta > 0 else "down")

    delta = current - previous
    if delta == 0:
        return "→ 0", "flat"
    return (f"↑ {abs(delta):,}" if delta > 0 else f"↓ {abs(delta):,}"), ("up" if delta > 0 else "down")


def render_comparison_cards(metrics):
    cards = []
    for label, current, previous, is_rate, base_text in metrics:
        value_text = f"{current:.1f}%" if is_rate else f"{int(current):,}"
        delta_text, direction = comparison_delta(current, previous, is_rate=is_rate)
        cards.append(
            f"""
            <div class="comparison-card">
                <div class="comparison-label">{escape(label)}</div>
                <div class="comparison-value">{value_text}</div>
                <div class="comparison-base">{escape(base_text)}</div>
                <span class="delta delta-{direction}">{delta_text}</span>
            </div>
            """
        )

    st.html('<div class="comparison-grid">' + ''.join(cards) + '</div>')


def stage_snapshot(apps_df, portal_df, welcome_col):
    """Return the four true funnel stages.

    Committed is intentionally NOT treated as a fifth downstream stage.
    It sits at the same level as Live, so it is returned separately only as
    companion information for the Live stage.
    """
    total = len(apps_df)
    quality_approved = len(apps_df[apps_df["Q_Status"] == "Approved"])
    wc_done = 0
    if welcome_col and "WC_Clean" in apps_df.columns:
        wc_done = len(apps_df[apps_df["WC_Clean"] == "Done"])
    live = len(portal_df[portal_df["Downstream_Category"] == "Live"]) if not portal_df.empty and "Downstream_Category" in portal_df.columns else 0
    committed = len(portal_df[portal_df["Downstream_Category"] == "Committed Rem."]) if not portal_df.empty and "Downstream_Category" in portal_df.columns else 0

    stages = [
        ("Applications", total, "#3B82F6"),
        ("Quality", quality_approved, "#10B981"),
        ("Welcome", wc_done, "#06B6D4"),
        ("Live", live, "#047857"),
    ]

    return stages, committed


def add_date_strings(frame, source_col, output_col):
    frame = frame.copy()
    if "Date_Parsed" in frame.columns:
        parsed = frame["Date_Parsed"]
    elif source_col in frame.columns:
        parsed = parse_date_series(frame[source_col])
    else:
        parsed = pd.Series(pd.NaT, index=frame.index)
    frame[output_col] = pd.to_datetime(parsed, errors="coerce").dt.strftime("%d-%m-%Y").fillna("")
    return frame


def _monthly_table_is_holiday(day_value):
    """Working-day rule: Sundays and the 1st/3rd Saturdays are holidays."""
    day = day_value.date() if isinstance(day_value, (pd.Timestamp, datetime.datetime)) else day_value
    weekday = day.weekday()
    if weekday == 6:
        return True
    if weekday == 5:
        saturday_number = (day.day - 1) // 7 + 1
        return saturday_number in {1, 3}
    return False


def build_crm_monthly_summary(apps_frame, portal_frame, attendance_frame, as_of=None):
    """Build monthly and daily CRM-only summaries for one already-filtered agent.

    Returns (monthly_summary, daily_summary). The daily summary includes every
    date within each represented CRM month, including zero-sales working days,
    so each month can be expanded in the interactive table.
    """
    as_of = as_of or datetime.date.today()
    as_of_date = as_of.date() if isinstance(as_of, datetime.datetime) else as_of

    base_columns = ["Month", "Total Attendance", "SPD", "Applications"]
    daily_base_columns = ["Date", "Attendance", "SPD", "Applications"]
    status_specs = [
        ("Inbound", "_InboundStatus"),
        ("Quality", "_QualityStatus"),
        ("Welcome", "_WelcomeStatus"),
        ("Committed", "_ConfirmationStatus"),
        ("Onboarding", "_OnboardingStatus"),
    ]
    empty_monthly = pd.DataFrame(columns=base_columns)
    empty_daily = pd.DataFrame(columns=daily_base_columns)
    if apps_frame is None or apps_frame.empty or "Source" not in apps_frame.columns:
        return empty_monthly, empty_daily

    # This report deliberately uses only rows whose source is the CRM mirror.
    crm_apps = apps_frame[
        apps_frame["Source"].fillna("").astype(str).str.strip().eq("CRM Mirror")
    ].copy()
    if crm_apps.empty:
        return empty_monthly, empty_daily

    if "Date_Parsed" not in crm_apps.columns:
        crm_apps["Date_Parsed"] = parse_date_series(
            crm_apps.get("Sale Date", pd.Series(index=crm_apps.index, dtype=object))
        )
    crm_apps["Date_Parsed"] = pd.to_datetime(crm_apps["Date_Parsed"], errors="coerce")
    crm_apps = crm_apps[
        crm_apps["Date_Parsed"].notna()
        & (crm_apps["Date_Parsed"].dt.date >= CRM_SOURCE_START.date())
        & (crm_apps["Date_Parsed"].dt.date <= as_of_date)
    ].copy()
    if crm_apps.empty:
        return empty_monthly, empty_daily

    if "_RecordKey" not in crm_apps.columns:
        crm_apps = add_record_keys(crm_apps, "Standardized_Date", "CLI")
    crm_apps["_RecordKey"] = crm_apps["_RecordKey"].fillna("").astype(str).str.strip()
    crm_apps = crm_apps[crm_apps["_RecordKey"].ne("")].copy()
    crm_apps = crm_apps.drop_duplicates(subset=["_RecordKey"], keep="last")
    if crm_apps.empty:
        return empty_monthly, empty_daily

    for col in ("Inbound Status", "Quality Status", "Status"):
        if col not in crm_apps.columns:
            crm_apps[col] = ""
    crm_apps = crm_apps.rename(columns={
        "Inbound Status": "_InboundStatus",
        "Quality Status": "_QualityStatus",
        "Status": "_WelcomeStatus",
    })
    crm_apps = crm_apps[[
        "_RecordKey", "Date_Parsed", "_InboundStatus", "_QualityStatus", "_WelcomeStatus"
    ]]

    portal_statuses = pd.DataFrame(
        columns=["_RecordKey", "_OnboardingStatus", "_ConfirmationStatus"]
    )
    if portal_frame is not None and not portal_frame.empty and "Source" in portal_frame.columns:
        crm_portal = portal_frame[
            portal_frame["Source"].fillna("").astype(str).str.strip().eq("CRM Mirror")
        ].copy()
        if "_RecordKey" not in crm_portal.columns:
            crm_portal = add_record_keys(crm_portal, "Sale Date", "Telephone No.")
        crm_portal["_RecordKey"] = crm_portal["_RecordKey"].fillna("").astype(str).str.strip()
        crm_portal = crm_portal[crm_portal["_RecordKey"].ne("")].copy()
        for col in ("Status", "CallStatus"):
            if col not in crm_portal.columns:
                crm_portal[col] = ""
        portal_statuses = crm_portal[["_RecordKey", "Status", "CallStatus"]].rename(columns={
            "Status": "_OnboardingStatus",
            "CallStatus": "_ConfirmationStatus",
        }).drop_duplicates(subset=["_RecordKey"], keep="last")

    monthly_data = crm_apps.merge(
        portal_statuses,
        on="_RecordKey",
        how="left",
        validate="one_to_one",
    )
    monthly_data["_Month"] = monthly_data["Date_Parsed"].dt.to_period("M")
    monthly_data["_SaleDay"] = monthly_data["Date_Parsed"].dt.date

    # Inbound is the highest-priority workflow classification for the monthly
    # CRM performance table. If Inbound Status is populated, count that record
    # only under Inbound and suppress all other stage status counts for it.
    monthly_data["_InboundStatus"] = monthly_data["_InboundStatus"].fillna("").astype(str).str.strip()
    has_inbound_status = monthly_data["_InboundStatus"].apply(normalize_workflow_status).ne("")
    for suppressed_status_col in (
        "_QualityStatus", "_WelcomeStatus", "_ConfirmationStatus", "_OnboardingStatus"
    ):
        if suppressed_status_col in monthly_data.columns:
            monthly_data.loc[has_inbound_status, suppressed_status_col] = ""

    status_labels = {}
    for group_name, source_col in status_specs:
        if source_col not in monthly_data.columns:
            monthly_data[source_col] = ""
        key_col = f"_StatusKey_{group_name}"
        monthly_data[key_col] = monthly_data[source_col].apply(normalize_workflow_status)
        labels_for_group = {}
        for raw_value, normalized_key in zip(
            monthly_data[source_col].tolist(), monthly_data[key_col].tolist()
        ):
            if not normalized_key:
                continue
            label = re.sub(r"\s+", " ", clean_reason_text(raw_value)).strip()
            if label:
                labels_for_group.setdefault(normalized_key, label)
        status_labels[group_name] = dict(sorted(
            labels_for_group.items(), key=lambda item: item[1].casefold()
        ))

    def monthly_attendance_code(value):
        code = str(value or "-").strip().upper()
        if code in {"P", "PRESENT"}:
            return "P"
        if code in {"HD", "HALF DAY", "HALF-DAY", "HALFDAY"}:
            return "HD"
        if code in {"AB", "A", "ABSENT", "ABSENCE"}:
            return "Ab"
        if code in {"UL", "UNPAID LEAVE", "UNPAID-LEAVE"}:
            return "UL"
        return "-" if code in {"", "NAN", "NONE", "NULL", "NAT", "-"} else code

    attendance = attendance_frame.copy() if attendance_frame is not None else pd.DataFrame()
    if not attendance.empty:
        if "Date_Parsed" not in attendance.columns:
            attendance["Date_Parsed"] = parse_date_series(
                attendance.get("Date", pd.Series(index=attendance.index, dtype=object))
            )
        attendance["Date_Parsed"] = pd.to_datetime(attendance["Date_Parsed"], errors="coerce")
        if "Attendance_Code" not in attendance.columns:
            attendance["Attendance_Code"] = attendance.get(
                "Attendance", pd.Series("-", index=attendance.index)
            ).apply(normalize_attendance_status)
        attendance = attendance[attendance["Date_Parsed"].notna()].copy()
        attendance["_AttendanceDate"] = attendance["Date_Parsed"].dt.date
        attendance = attendance.drop_duplicates(subset=["_AttendanceDate"], keep="last")

    attendance_by_date = {}
    if not attendance.empty:
        attendance_by_date = dict(zip(
            attendance["_AttendanceDate"],
            attendance["Attendance_Code"].apply(monthly_attendance_code)
        ))

    # Attendance units are counted only on scheduled working days. Leave and
    # absence both contribute zero; a half-day contributes 0.5.
    attendance_units = {"P": 1.0, "HD": 0.5, "Ab": 0.0, "UL": 0.0}

    rows = []
    daily_rows = []
    months = sorted(monthly_data["_Month"].dropna().unique())
    for month_period in months:
        month_apps = monthly_data[monthly_data["_Month"] == month_period].copy()
        month_start = max(month_period.start_time.date(), CRM_SOURCE_START.date())
        month_end = min(month_period.end_time.date(), as_of_date)
        if month_start > month_end:
            continue

        all_dates = [
            month_start + datetime.timedelta(days=offset)
            for offset in range((month_end - month_start).days + 1)
        ]
        working_dates = [day for day in all_dates if not _monthly_table_is_holiday(day)]
        present_units = sum(
            attendance_units.get(attendance_by_date.get(day, ""), 0.0)
            for day in working_dates
        )

        application_count = int(len(month_apps))
        row = {
            "Month": month_period.to_timestamp().strftime("%b-%Y"),
            "Total Attendance": f"{present_units:g}",
            "SPD": f"{application_count / present_units:.2f}" if present_units > 0 else "—",
            "Applications": application_count,
        }
        for group_name, _source_col in status_specs:
            key_col = f"_StatusKey_{group_name}"
            month_counts = month_apps[key_col].value_counts().to_dict()
            for normalized_key, display_label in status_labels[group_name].items():
                row[f"{group_name} · {display_label}"] = int(month_counts.get(normalized_key, 0))
        rows.append(row)

        # Daily rows are created for every date in the month window, including
        # dates with no sales. Holiday dates remain visible but have no working
        # day denominator; fifth Saturdays are working days under the revised rule.
        for sale_day in all_dates:
            day_apps = month_apps[month_apps["_SaleDay"] == sale_day]
            day_is_holiday = _monthly_table_is_holiday(sale_day)
            day_present_units = attendance_units.get(attendance_by_date.get(sale_day, ""), 0.0)
            day_working_denominator = 0 if day_is_holiday else 1
            app_count = int(len(day_apps))
            daily_row = {
                "Date": sale_day.strftime("%a, %d %b"),
                "_MonthKey": month_period.strftime("%Y-%m"),
                "Attendance": monthly_attendance_code(attendance_by_date.get(sale_day, "-")),
                "SPD": f"{app_count / day_present_units:.2f}" if day_present_units > 0 else "—",
                "Applications": app_count,
            }
            for group_name, _source_col in status_specs:
                key_col = f"_StatusKey_{group_name}"
                day_counts = day_apps[key_col].value_counts().to_dict()
                for normalized_key, display_label in status_labels[group_name].items():
                    daily_row[f"{group_name} · {display_label}"] = int(day_counts.get(normalized_key, 0))
            daily_rows.append(daily_row)

    if not rows:
        return empty_monthly, empty_daily

    dynamic_columns = []
    for group_name, _source_col in status_specs:
        dynamic_columns.extend(
            f"{group_name} · {label}"
            for label in status_labels[group_name].values()
        )
    result_columns = base_columns + dynamic_columns
    monthly_result = pd.DataFrame(rows).reindex(columns=result_columns, fill_value=0)
    daily_columns = daily_base_columns + dynamic_columns + ["_MonthKey"]
    daily_result = pd.DataFrame(daily_rows).reindex(columns=daily_columns, fill_value=0)
    for frame in (monthly_result, daily_result):
        for col in dynamic_columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0).astype(int)
        frame["Applications"] = pd.to_numeric(frame["Applications"], errors="coerce").fillna(0).astype(int)
    return monthly_result, daily_result


def pick_existing(frame, candidates):
    return [c for c in candidates if c in frame.columns]


def get_preset_dates(preset, today):
    if preset == "Today":
        return today, today
    if preset == "This Week":
        start = today - datetime.timedelta(days=today.weekday())
        return start, today
    if preset == "This Month":
        return today.replace(day=1), today
    if preset == "Last Month":
        first_this = today.replace(day=1)
        last_prev = first_this - datetime.timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    return st.session_state.get("main_start_date", today.replace(day=1)), st.session_state.get("main_end_date", today)


def summary_for_period(base_apps, base_portal, start_date, end_date, welcome_col):
    apps = base_apps[date_range_mask(base_apps["Date_Parsed"], start_date, end_date)].copy()
    portal = base_portal[date_range_mask(base_portal["Date_Parsed"], start_date, end_date)].copy()

    if "Quality Status" in apps.columns:
        apps["Q_Status"] = apps["Quality Status"].apply(map_quality)
    else:
        apps["Q_Status"] = "Others"

    if "Downstream_Category" not in portal.columns:
        portal = classify_downstream_frame(portal)
    portal["P_Status"] = portal["Downstream_Category"]

    total_apps = len(apps)
    total_portal = len(portal)
    approved = len(apps[apps["Q_Status"] == "Approved"])

    wc_done = 0
    if welcome_col and welcome_col in apps.columns:
        apps["WC_Clean"] = apps[welcome_col].apply(map_wc)
        wc_done = len(apps[apps["WC_Clean"] == "Done"])

    live = len(portal[portal["Downstream_Category"] == "Live"])
    live_denominator = total_portal if total_portal > 0 else total_apps

    return {
        "apps": total_apps,
        "approval_rate": pct(approved, total_apps),
        "wc_done_rate": pct(wc_done, total_apps),
        "live_rate": pct(live, live_denominator),
    }


# ----------------------------------------------------------------------------
# SESSION STATE
# ----------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.agent_name = ""

if "current_page" not in st.session_state:
    st.session_state.current_page = 1

# ----------------------------------------------------------------------------
# LOGIN
# ----------------------------------------------------------------------------
if not st.session_state.authenticated:
    left, center, right = st.columns([1, 1.4, 1])

    with center:
        with st.container(border=True):
            st.image(LOGO_URL, width=65)
            st.caption("SPARTA TELECOM • AGENT PERFORMANCE")
            st.markdown("# Agent Portal")
            st.write(
                "Secure access to your applications, quality results, welcome-call progress, "
                "live conversions and detailed sales activity."
            )

            user_key = st.text_input(
                "Access Key",
                type="password",
                placeholder="Enter your access key",
            )

            if st.button(
                "Sign in to my dashboard →",
                use_container_width=True,
                type="primary",
            ):
                if user_key.upper() in ACCESS_KEYS:
                    st.session_state.authenticated = True
                    st.session_state.agent_name = ACCESS_KEYS[user_key.upper()]
                    st.session_state.current_page = 1
                    log_agent_login(ACCESS_KEYS[user_key.upper()])
                    st.rerun()
                else:
                    st.error("Invalid Access Key. Try again!")

            st.caption(
                "Your dashboard displays only the performance data assigned to your login."
            )

    st.stop()

# ----------------------------------------------------------------------------
# AUTHENTICATED PORTAL
# ----------------------------------------------------------------------------
agent = st.session_state.agent_name
today_date = datetime.date.today()

# Sidebar
with st.sidebar:
    st.html(
        f"""
        <div class="sidebar-profile">
            <div class="sidebar-avatar">{escape(initials(agent))}</div>
            <div class="sidebar-role">Signed in as</div>
            <div class="sidebar-name">{escape(agent)}</div>
        </div>
        """,
        )
    st.html(
        '<div style="font-size:.67rem;color:#7E93BF;text-transform:uppercase;letter-spacing:1px;font-weight:800;margin:18px 0 8px;">Portal</div>',
        )
    if st.button("↪  Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.agent_name = ""
        st.rerun()

    st.html(
        '<div style="position:fixed;bottom:20px;width:220px;color:#6F86B7;font-size:.64rem;line-height:1.45;">'
        "Sparta Agent Portal<br>Performance & activity centre"
        "</div>"
    )

# ----------------------------------------------------------------------------
# DATA LOAD
# ----------------------------------------------------------------------------
try:
    df1, df2_raw, attendance_df, last_sync, connection_status = fetch_data()
    # Agent login remains the control point: each agent only sees their own data.
    agent_compact = re.sub(r"[^a-z0-9]", "", str(agent).lower())
    ag1 = df1[df1["Advisor"].apply(lambda x: re.sub(r"[^a-z0-9]", "", str(x).lower()) == agent_compact)].copy()
    ag2 = df2_raw[df2_raw["Advisor"].apply(lambda x: re.sub(r"[^a-z0-9]", "", str(x).lower()) == agent_compact)].copy()
    # One mutually exclusive category per downstream record, reused by KPIs,
    # trends, daily/monthly tables, insights, and the Recent Applications Log.
    ag2 = classify_downstream_frame(ag2)
    if not attendance_df.empty:
        ag_attendance = attendance_df[
            attendance_df["Attendance_Agent"].apply(
                lambda x: re.sub(r"[^a-z0-9]", "", str(x).lower()) == agent_compact
            )
        ].copy()
    else:
        ag_attendance = pd.DataFrame(columns=["Date_Parsed", "Attendance_Code", "Attendance_Agent", "Name"])

    # ------------------------------------------------------------------------
    # HERO
    # ------------------------------------------------------------------------
    hero_left, hero_right = st.columns([3.1, 1.15])
    with hero_left:
        st.html(
            f"""
            <div class="hero">
                <div class="hero-kicker">Sparta Telecom • Agent Performance</div>
                <div class="hero-title">Welcome back, {escape(agent)}</div>
                <div class="hero-subtitle">A clear view of applications, quality, welcome calls and live conversion.</div>
            </div>
            """,
        )
    with hero_right:
        st.html(
            f"""
            <div class="hero" style="height:100%;padding:21px 22px;">
                <div class="hero-kicker">Data status</div>
                <div style="font-size:.82rem;font-weight:800;margin-top:3px;"><span class="live-dot"></span>{escape(connection_status)}</div>
                <div class="hero-sync" style="text-align:left;padding-top:7px;">
                    Last synced<br><strong>{escape(str(last_sync))}</strong>
                </div>
            </div>
            """,
        )

    # ------------------------------------------------------------------------
    # GLOBAL DATE FILTER + QUICK PRESETS
    # ------------------------------------------------------------------------
    if "main_start_date" not in st.session_state:
        st.session_state.main_start_date = today_date.replace(day=1)
    if "main_end_date" not in st.session_state:
        st.session_state.main_end_date = today_date
    if "date_preset" not in st.session_state:
        st.session_state.date_preset = "This Month"

    def apply_date_preset():
        # Streamlit callbacks can run before the main script body is rerun.
        # Use a safe fallback so an existing/stale callback can never crash
        # when the widget key is temporarily absent from session state.
        preset = st.session_state.get("date_preset", "This Month")
        st.session_state.date_preset = preset
        if preset != "Custom":
            preset_start, preset_end = get_preset_dates(preset, today_date)
            st.session_state.main_start_date = preset_start
            st.session_state.main_end_date = preset_end

    with st.container(border=True):
        top_filter_col, preset_col, start_col, end_col = st.columns([0.55, 2.25, 1.25, 1.25], gap="small")

        with top_filter_col:
            st.markdown("### 🗓️")

        with preset_col:
            st.caption("QUICK RANGE")
            st.radio(
                "Quick Range",
                ["This Month", "Today", "This Week", "Last Month", "Custom"],
                horizontal=True,
                key="date_preset",
                on_change=apply_date_preset,
                label_visibility="collapsed",
            )

        with start_col:
            st.caption("START DATE")
            start_date = st.date_input(
                "Start Date",
                key="main_start_date",
                disabled=st.session_state.date_preset != "Custom",
                label_visibility="collapsed",
            )

        with end_col:
            st.caption("END DATE")
            end_date = st.date_input(
                "End Date",
                key="main_end_date",
                disabled=st.session_state.date_preset != "Custom",
                label_visibility="collapsed",
            )

    # Protect against a reversed user-selected range without altering the source data.
    if start_date > end_date:
        st.warning("Start Date is after End Date. Please select a valid date range.")
        st.stop()

    ag1_filtered = ag1[date_range_mask(ag1["Date_Parsed"], start_date, end_date)].copy()
    ag2_filtered = ag2[date_range_mask(ag2["Date_Parsed"], start_date, end_date)].copy()

    ag1_filtered["Q_Status"] = ag1_filtered["Quality Status"].apply(map_quality)
    ag2_filtered["P_Status"] = ag2_filtered["Downstream_Category"]

    wc_col = (
        "Status"
        if "Status" in ag1_filtered.columns
        else "Welcome call Status"
        if "Welcome call Status" in ag1_filtered.columns
        else None
    )
    if wc_col:
        ag1_filtered["WC_Clean"] = ag1_filtered.apply(
            lambda row: map_wc_with_quality(
                row.get(wc_col, ""), row.get("Quality Status", "")
            ), axis=1
        )

    # The Live Status KPI counts only downstream records whose corresponding
    # application is Welcome Done/Approved. Eligibility is separate from the
    # central downstream classification; the broader frame remains intact for
    # the log, insights, and daily/monthly breakdowns.
    live_kpi_filtered = build_wc_done_live_kpi_rows(
        ag1_filtered, ag2_filtered, wc_col
    )

    # The trend shown on each main KPI card compares the selected date range
    # with the immediately preceding period of the same number of days.
    period_days = (end_date - start_date).days + 1
    prev_start = start_date - datetime.timedelta(days=period_days)
    prev_end = start_date - datetime.timedelta(days=1)
    previous_ag1 = ag1[date_range_mask(ag1["Date_Parsed"], prev_start, prev_end)].copy()
    previous_ag2 = ag2[date_range_mask(ag2["Date_Parsed"], prev_start, prev_end)].copy()

    if "Quality Status" in previous_ag1.columns:
        previous_ag1["Q_Status"] = previous_ag1["Quality Status"].apply(map_quality)
    else:
        previous_ag1["Q_Status"] = "Others"
    if "Downstream_Category" not in previous_ag2.columns:
        previous_ag2 = classify_downstream_frame(previous_ag2)
    previous_ag2["P_Status"] = previous_ag2["Downstream_Category"]
    if wc_col and wc_col in previous_ag1.columns:
        previous_ag1["WC_Clean"] = previous_ag1.apply(
            lambda row: map_wc_with_quality(
                row.get(wc_col, ""), row.get("Quality Status", "")
            ), axis=1
        )

    previous_live_kpi = build_wc_done_live_kpi_rows(
        previous_ag1, previous_ag2, wc_col
    )

    trend_previous_counts = {"Total Apps": len(previous_ag1)}
    for label, status in [
        ("Approved", "Approved"), ("Rework", "Rework"),
        ("Cancelled", "Cancelled"), ("Rejected", "Rejected"),
        ("Others", "Others"),
    ]:
        trend_previous_counts[label] = int((previous_ag1["Q_Status"] == status).sum())

    if wc_col and "WC_Clean" in previous_ag1.columns:
        for label, status in [
            ("WC Done", "Done"), ("WC Pending", "Pending"),
            ("WC Paperwork", "Paperwork"), ("WC Cancelled", "Cancelled"),
            ("WC Others", "Others"),
        ]:
            trend_previous_counts[label] = int((previous_ag1["WC_Clean"] == status).sum())

    for label in LIVE_KPI_STATUS_ORDER:
        # These comparison counts use the same WC Done/Approved eligibility
        # and CallStatus fallback as the current Live Status KPI cards.
        key = f"Portal {label}"
        trend_previous_counts[key] = int(
            (previous_live_kpi["Live_KPI_Status"] == label).sum()
        )

    # ------------------------------------------------------------------------
    # KPI ROW
    # ------------------------------------------------------------------------
    total_apps = len(ag1_filtered)
    total_ag2 = len(ag2_filtered)

    group_1 = [("Total Apps", total_apps, total_apps)]
    group_2 = [
        ("Approved", len(ag1_filtered[ag1_filtered["Q_Status"] == "Approved"]), total_apps),
        ("Rework", len(ag1_filtered[ag1_filtered["Q_Status"] == "Rework"]), total_apps),
        ("Cancelled", len(ag1_filtered[ag1_filtered["Q_Status"] == "Cancelled"]), total_apps),
        ("Rejected", len(ag1_filtered[ag1_filtered["Q_Status"] == "Rejected"]), total_apps),
        ("QA-Pending", len(ag1_filtered[ag1_filtered["Q_Status"] == "QA-Pending"]), total_apps),
        ("Others", len(ag1_filtered[ag1_filtered["Q_Status"] == "Others"]), total_apps),
    ]

    group_3 = []
    if wc_col:
        group_3 = [
            ("WC Done", len(ag1_filtered[ag1_filtered["WC_Clean"] == "Done"]), total_apps),
            ("WC Pending", len(ag1_filtered[ag1_filtered["WC_Clean"] == "Pending"]), total_apps),
            ("WC Paperwork", len(ag1_filtered[ag1_filtered["WC_Clean"] == "Paperwork"]), total_apps),
            ("WC Cancelled", len(ag1_filtered[ag1_filtered["WC_Clean"] == "Cancelled"]), total_apps),
            ("WC Others", len(ag1_filtered[ag1_filtered["WC_Clean"] == "Others"]), total_apps),
        ]

    # Live KPI denominator is the subset with a matching Welcome Done/Approved
    # application row, not every downstream record in the selected period.
    live_total_denominator = len(live_kpi_filtered)
    group_4 = [
        (
            status_label,
            int((live_kpi_filtered["Live_KPI_Status"] == status_label).sum()),
            live_total_denominator,
        )
        for status_label in LIVE_KPI_STATUS_ORDER
    ]

    # ------------------------------------------------------------------------
    # TOP DASHBOARD: KPI AREA + ATTENDANCE / SALES HEATMAP
    # ------------------------------------------------------------------------
    top_left, top_right = st.columns([1.75, 1.0], gap="small")

    with top_left:
        render_section("Performance snapshot", "✦", "Your selected date range at a glance")

        # Four primary KPI panels in a clean 2 x 2 layout.
        # Nested status values keep their individual trends inside each panel.
        kpi_top_left, kpi_top_right = st.columns(2, gap="small")
        with kpi_top_left:
            with st.container(border=True):
                st.markdown("**Overview**")
                render_kpi(
                    group_1[0][0], group_1[0][1], group_1[0][2],
                    previous_count=trend_previous_counts.get("Total Apps"),
                )
        with kpi_top_right:
            kpi_panel("Quality audit status", group_2, trend_previous_counts)

        kpi_bottom_left, kpi_bottom_right = st.columns(2, gap="small")
        with kpi_bottom_left:
            kpi_panel("Welcome call status", group_3, trend_previous_counts)
        with kpi_bottom_right:
            kpi_panel(
                "Live status",
                group_4,
                {
                    status_label: trend_previous_counts.get(f"Portal {status_label}", 0)
                    for status_label in LIVE_KPI_STATUS_ORDER
                },
            )
            # Preserve visibility of the old CallStatus fallback detail without
            # treating confirmation-stage values as additional categories. These
            # counts are a subset of the categories above and are not additive.
            confirmation_detail_counts = {
                "Confirmation Approved": 0,
                "Confirmation Followup": 0,
                "Confirmation Pending": 0,
            }
            for _, eligible_row in live_kpi_filtered.iterrows():
                if normalize_workflow_status(eligible_row.get("Status", "")):
                    continue
                fallback_status = normalize_workflow_status(eligible_row.get("CallStatus", ""))
                if fallback_status.startswith("confirmation approved") or fallback_status == "approved":
                    confirmation_detail_counts["Confirmation Approved"] += 1
                elif fallback_status.startswith(("confirmation followup", "confirmation follow up")) or fallback_status in {"followup", "follow up"}:
                    confirmation_detail_counts["Confirmation Followup"] += 1
                elif fallback_status.startswith("confirmation pending") or fallback_status in {"pending", "pnd"}:
                    confirmation_detail_counts["Confirmation Pending"] += 1
            confirmation_details = [
                f"{label}: {count:,}"
                for label, count in confirmation_detail_counts.items()
                if count > 0
            ]
            if confirmation_details:
                st.markdown("**Confirmation fallback detail**")
                st.caption(" · ".join(confirmation_details))

        # Compact activity consistency. Period-to-period trends now live on
        # the main KPI cards, so repeated Performance Pulse comparison cards
        # are intentionally omitted.
        def portal_is_holiday(dt):
            wd = dt.weekday()
            if wd == 6:
                return True
            if wd == 5:
                week_num = (dt.day - 1) // 7 + 1
                return week_num in [1, 3]
            return False

        range_dates = [
            start_date + datetime.timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]
        working_days = [d for d in range_dates if not portal_is_holiday(d)]
        daily_activity = (
            ag1_filtered.groupby(ag1_filtered["Date_Parsed"].dt.date).size()
            if not ag1_filtered.empty
            else pd.Series(dtype="int64")
        )
        active_days = sum(1 for d in working_days if daily_activity.get(d, 0) > 0)
        zero_sales_days = sum(1 for d in working_days if daily_activity.get(d, 0) == 0)
        best_day_text = "—"
        best_day_count = 0
        if not daily_activity.empty:
            best_day = daily_activity.idxmax()
            best_day_count = int(daily_activity.max())
            best_day_text = pd.Timestamp(best_day).strftime("%d %b")
        avg_active_day = (total_apps / active_days) if active_days > 0 else 0
        avg_working_day = (total_apps / len(working_days)) if working_days else 0

        st.html(
            '<div style="display:flex;align-items:center;gap:7px;margin:7px 0 5px;'
            'font-size:.68rem;font-weight:900;letter-spacing:.65px;color:#475569;'
            'text-transform:uppercase;"><span style="width:4px;height:13px;border-radius:4px;'
            'background:linear-gradient(180deg,#2563EB,#06B6D4);display:inline-block;"></span>'
            'Activity consistency</div>'
        )

        activity_cards = [
            ("Working days", len(working_days), "in selected range"),
            ("Active days", active_days, f"of {len(working_days)} working days"),
            ("Avg apps / working day", f"{avg_working_day:.1f}", "applications"),
            ("Avg apps / active day", f"{avg_active_day:.1f}", "applications"),
            ("Best sales day", best_day_text, f"{best_day_count:,} applications" if best_day_count else "no activity"),
        ]
        activity_html = []
        for label, value, sub in activity_cards:
            activity_html.append(
                f"""
                <div class="mini-stat">
                    <div class="mini-stat-label">{escape(str(label))}</div>
                    <div class="mini-stat-value">{escape(str(value))}</div>
                    <div class="mini-stat-sub">{escape(str(sub))}</div>
                </div>
                """
            )
        st.html('<div class="mini-stat-grid">' + ''.join(activity_html) + '</div>')

    with top_right:
            render_section("Sales activity heatmap", "▦", "Attendance + daily sales intensity — working-day cells show attendance and sales")

            def is_holiday(dt):
                wd = dt.weekday()  # 0=Mon, 6=Sun
                if wd == 6:
                    return True
                if wd == 5:
                    week_num = (dt.day - 1) // 7 + 1
                    return week_num in [1, 3]
                return False

            c_month_col, c_year_col = st.columns([1.25, 1.0], gap="small")
            with c_month_col:
                st.caption("MONTH")
                sel_month = st.selectbox(
                    "Month",
                    list(calendar.month_name)[1:],
                    index=start_date.month - 1,
                    key="calendar_month",
                    label_visibility="collapsed",
                )
            with c_year_col:
                st.caption("YEAR")
                year_options = list(range(max(2025, start_date.year - 2), max(2025, today_date.year) + 1))
                if start_date.year not in year_options:
                    year_options.append(start_date.year)
                    year_options = sorted(set(year_options))
                default_year_index = year_options.index(start_date.year) if start_date.year in year_options else len(year_options) - 1
                sel_year = st.selectbox(
                    "Year",
                    year_options,
                    index=default_year_index,
                    key="calendar_year",
                    label_visibility="collapsed",
                )

            m_idx = list(calendar.month_name).index(sel_month)
            num_days = calendar.monthrange(sel_year, m_idx)[1]
            dates = [datetime.date(sel_year, m_idx, day) for day in range(1, num_days + 1)]

            daily_sales = ag1.groupby(ag1["Date_Parsed"].dt.date).size()
            calendar_max = int(daily_sales.max()) if not daily_sales.empty else 0

            # -------------------------------------------------------------------
            # ATTENDANCE + SALES CALENDAR HEATMAP — FIXED GRID
            # -------------------------------------------------------------------
            # Use a single 7-column x 5/6-row heatmap matrix built from the actual
            # month calendar.  This prevents Plotly from stacking multiple traces
            # into the same categorical coordinates, which was causing:
            #   * unequal-looking cell sizes
            #   * labels appearing in neighbouring cells
            #   * colours bleeding / appearing on the wrong date
            #
            # Each cell contains:
            #   line 1 = day of month
            #   line 2 = attendance + sales, e.g. P3 / HD1 / Ab / UL2
            #
            # Colour has BOTH meanings:
            #   P  = green family
            #   HD = amber family
            #   Ab = red family
            #   UL = indigo family
            #   -  = neutral grey when attendance is missing
            #   Holiday = light blue
            # Within each family, sales 0 / 1 / 2 / 3 / 4+ controls intensity.
            attendance_by_date = {}
            if not ag_attendance.empty:
                for _, att_row in ag_attendance.iterrows():
                    dt = pd.to_datetime(att_row.get("Date_Parsed"), errors="coerce")
                    if pd.isna(dt):
                        continue
                    attendance_by_date[dt.date()] = str(
                        att_row.get("Attendance_Code", "-")
                    ).strip() or "-"

            def display_attendance_code(value):
                code = str(value or "-").strip()
                return code if code else "-"

            def sales_bucket(sales):
                try:
                    n = int(sales)
                except (TypeError, ValueError):
                    n = 0
                return min(max(n, 0), 4)

            def cell_label(day, sales, attendance_code, is_holiday=False):
                if is_holiday:
                    return f"{int(day)}<br>Holiday"
                code = display_attendance_code(attendance_code)
                n = int(sales)
                second_line = code if n <= 0 else f"{code}{n}"
                return f"{int(day)}<br>{second_line}"

            def cell_hover(day, kind, sales, attendance_code):
                if kind == "Holiday":
                    return f"Date: {day}<br>Holiday / Non-working day<br>Sales: {int(sales)}"
                code = display_attendance_code(attendance_code)
                return (
                    f"Date: {day}<br>Attendance: {escape(code)}<br>"
                    f"Sales: {int(sales)}"
                )

            # Build the exact calendar matrix: every date belongs to one fixed
            # weekday column and one fixed calendar-week row. Padding cells are None.
            month_weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(sel_year, m_idx)
            weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

            # Discrete colour classes.  Code 0 is reserved for padding / blank;
            # code 1-5 are holidays; the remaining blocks are attendance families
            # with sales intensity 0/1/2/3/4+.
            palette_groups = {
                "Holiday": ["#EAF2FF"] * 5,
                "-": ["#F8FAFC", "#E2E8F0", "#CBD5E1", "#94A3B8", "#64748B"],
                "P": ["#ECFDF5", "#BBF7D0", "#6EE7B7", "#34D399", "#047857"],
                "HD": ["#FFFBEB", "#FEF3C7", "#FDE68A", "#FBBF24", "#B45309"],
                "Ab": ["#FEF2F2", "#FECACA", "#FCA5A5", "#F87171", "#B91C1C"],
                "UL": ["#EEF2FF", "#C7D2FE", "#A5B4FC", "#818CF8", "#4338CA"],
            }

            group_order = ["Holiday", "-", "P", "HD", "Ab", "UL"]
            # Exact integer code for each (group, sales bucket).
            code_lookup = {}
            code_to_color = {}
            next_code = 0
            for group in group_order:
                for bucket, color in enumerate(palette_groups[group]):
                    code_lookup[(group, bucket)] = next_code
                    code_to_color[next_code] = color
                    next_code += 1

            # Code zero is deliberately a real colour only for the first holiday
            # slot; padded cells are represented as None and therefore transparent.
            n_colors = next_code
            discrete_colorscale = []
            if n_colors == 1:
                discrete_colorscale = [[0.0, code_to_color[0]], [1.0, code_to_color[0]]]
            else:
                for code in range(n_colors):
                    pos = code / (n_colors - 1)
                    discrete_colorscale.append([pos, code_to_color[code]])

            z_matrix = []
            text_matrix = []
            hover_matrix = []

            for week in month_weeks:
                z_row = []
                text_row = []
                hover_row = []
                for day in week:
                    if day == 0:
                        z_row.append(None)
                        text_row.append("")
                        hover_row.append("")
                        continue

                    dt = datetime.date(sel_year, m_idx, day)
                    sales = int(daily_sales.get(dt, 0))

                    if is_holiday(dt):
                        group = "Holiday"
                        bucket = 0
                        text_value = cell_label(day, sales, "-", is_holiday=True)
                        hover_value = cell_hover(day, "Holiday", sales, "-")
                    else:
                        attendance_code = display_attendance_code(
                            attendance_by_date.get(dt, "-")
                        )
                        # Only known codes participate in the colour families.
                        if attendance_code not in {"P", "HD", "Ab", "UL"}:
                            attendance_code = "-"
                        group = attendance_code
                        bucket = sales_bucket(sales)
                        text_value = cell_label(
                            day, sales, attendance_code, is_holiday=False
                        )
                        hover_value = cell_hover(
                            day, "Working", sales, attendance_code
                        )

                    z_row.append(code_lookup[(group, bucket)])
                    text_row.append(text_value)
                    hover_row.append(hover_value)

                z_matrix.append(z_row)
                text_matrix.append(text_row)
                hover_matrix.append(hover_row)

            fig_cal = go.Figure(
                data=[
                    go.Heatmap(
                        x=list(range(7)),
                        y=list(range(len(month_weeks))),
                        z=z_matrix,
                        text=text_matrix,
                        customdata=hover_matrix,
                        hovertemplate="%{customdata}<extra></extra>",
                        texttemplate="%{text}",
                        textfont=dict(
                            color="#334155",
                            size=10,
                        ),
                        zmin=0,
                        zmax=max(n_colors - 1, 1),
                        colorscale=discrete_colorscale,
                        showscale=False,
                        xgap=4,
                        ygap=4,
                        hoverongaps=False,
                        hoverlabel=dict(
                            bgcolor="#0F172A",
                            font=dict(color="#FFFFFF", size=11),
                        ),
                    )
                ]
            )

            # Give every day cell the same geometric footprint.  Using numeric
            # coordinates rather than weekday strings avoids categorical spacing
            # differences and ensures all 7 columns are perfectly equal.
            fig_cal.update_xaxes(
                side="top",
                tickmode="array",
                tickvals=list(range(7)),
                ticktext=weekday_names,
                range=[-0.5, 6.5],
                showgrid=False,
                zeroline=False,
                fixedrange=True,
                constrain="domain",
            )
            fig_cal.update_yaxes(
                tickmode="array",
                tickvals=list(range(len(month_weeks))),
                ticktext=[f"Week {i+1}" for i in range(len(month_weeks))],
                range=[len(month_weeks) - 0.5, -0.5],
                showgrid=False,
                zeroline=False,
                fixedrange=True,
                constrain="domain",
                scaleanchor="x",
                scaleratio=1,
            )
            fig_cal.update_layout(
                height=max(290, 70 * len(month_weeks) + 48),
                margin=dict(l=34, r=4, t=8, b=3),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(255,255,255,.72)",
                showlegend=False,
            )

            st.plotly_chart(
                fig_cal,
                use_container_width=True,
                config={"displayModeBar": False},
            )

            # Compact legend: attendance determines hue, sales determine depth.
            st.html(
                """
                <div style="display:flex;flex-wrap:wrap;gap:7px 14px;align-items:center;
                            margin:2px 0 5px;font-size:.65rem;color:#475569;font-weight:750;">
                    <span style="font-weight:900;color:#334155;">Attendance + sales:</span>
                    <span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:#34D399;vertical-align:-1px;margin-right:4px;"></span>P = Present</span>
                    <span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:#FBBF24;vertical-align:-1px;margin-right:4px;"></span>HD = Half Day</span>
                    <span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:#F87171;vertical-align:-1px;margin-right:4px;"></span>Ab = Absent</span>
                    <span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:#818CF8;vertical-align:-1px;margin-right:4px;"></span>UL = Unauthorised Leave</span>
                    <span style="color:#64748B;">Darker = more sales</span>
                </div>
                """
            )
            st.caption(
                f"{calendar.month_name[m_idx]} {sel_year} · peak: {calendar_max:,} sales · "
                "format: date + attendance/sales · Sundays + 1st/3rd Saturdays are holidays"
            )


    # ------------------------------------------------------------------------
    # INSIGHT FLAGS
    # ------------------------------------------------------------------------
    flags_html = ""

    if total_apps > 0:
        q_appr = len(ag1_filtered[ag1_filtered["Q_Status"] == "Approved"]) / total_apps
        q_can = len(ag1_filtered[ag1_filtered["Q_Status"] == "Cancelled"]) / total_apps
        q_rej = len(ag1_filtered[ag1_filtered["Q_Status"] == "Rejected"]) / total_apps
        q_rew = len(ag1_filtered[ag1_filtered["Q_Status"] == "Rework"]) / total_apps

        if q_appr > 0.60:
            flags_html += '<div class="insight-card" style="border-color:#10B981"><p class="insight-title">Quality</p><p class="insight-phrase">High Approval Rate</p><p class="insight-comment">Excellent pitch and quality compliance!</p></div>'
        elif q_appr < 0.60:
            flags_html += '<div class="insight-card" style="border-color:#EF4444"><p class="insight-title">Quality</p><p class="insight-phrase">Low Approval Rate</p><p class="insight-comment">Review the quality guidelines to increase quality approval!</p></div>'

        if q_can > 0.40:
            flags_html += '<div class="insight-card" style="border-color:#F59E0B"><p class="insight-title">Quality</p><p class="insight-phrase">High Cancellation</p><p class="insight-comment">High Quality Cancellations, review the quality guidelines!</p></div>'
        if q_rej > 0.20:
            flags_html += '<div class="insight-card" style="border-color:#EF4444"><p class="insight-title">Quality</p><p class="insight-phrase">High Rejection</p><p class="insight-comment">High Quality Rejections! Pay attention to quality guidelines!</p></div>'
        if q_rew > 0.30:
            flags_html += '<div class="insight-card" style="border-color:#3B82F6"><p class="insight-title">Quality</p><p class="insight-phrase">Frequent Reworks</p><p class="insight-comment">Pay closer attention to quality guidelines, to avoid large number of Quality Reworks.</p></div>'

        if wc_col:
            wc_done = len(ag1_filtered[ag1_filtered["WC_Clean"] == "Done"]) / total_apps
            wc_can = len(ag1_filtered[ag1_filtered["WC_Clean"] == "Cancelled"]) / total_apps
            if wc_done < 0.70:
                flags_html += '<div class="insight-card" style="border-color:#F59E0B"><p class="insight-title">Welcome Call</p><p class="insight-phrase">Low Completion</p><p class="insight-comment">Address customer requirements closely to increase Welcome call approvals!</p></div>'
            if wc_can > 0.15:
                flags_html += '<div class="insight-card" style="border-color:#EF4444"><p class="insight-title">Welcome Call</p><p class="insight-phrase">High WC Cancellation</p><p class="insight-comment">Address customer doubts in the sales call to avoid Welcome call cancellations!</p></div>'

    if total_ag2 > 0:
        l_live = len(ag2_filtered[ag2_filtered["Downstream_Category"] == "Live"]) / total_ag2
        l_can = len(ag2_filtered[ag2_filtered["Downstream_Category"].isin(["Committed Cancelled", "Live Cancelled"])]) / total_ag2
        if l_live > 0.20:
            flags_html += '<div class="insight-card" style="border-color:#10B981"><p class="insight-title">Live Stage</p><p class="insight-phrase">Strong Conversion</p><p class="insight-comment">Good live rate! Great overall quality of applications!</p></div>'
        elif l_live < 0.20:
            flags_html += '<div class="insight-card" style="border-color:#F59E0B"><p class="insight-title">Live Stage</p><p class="insight-phrase">Low Live Rate</p><p class="insight-comment">Identify bottlenecks preventing sales from going live.</p></div>'
        if l_can > 0.65:
            flags_html += '<div class="insight-card" style="border-color:#EF4444"><p class="insight-title">Live Stage</p><p class="insight-phrase">High Final Loss</p><p class="insight-comment">Large drops between applications and Committed. Identify bottlenecks!</p></div>'

    if flags_html:
        st.html('<div style="height:6px"></div>')
        render_section("Points to look out for", "💡", "Automated indicators based on the same thresholds as the original portal")
        st.html(f'<div class="insight-wrap">{flags_html}</div>')

    # ------------------------------------------------------------------------
    # MONTHLY TRADITIONAL EXCEL (SPARTA / SPARTA2) SUMMARY
    # ------------------------------------------------------------------------
    # Keep this as a separate table from CRM so source-specific headers and
    # classification rules never get fused. September intentionally appears
    # in both tables: legacy covers through 17-Sep, CRM starts 18-Sep.
    st.html('<div style="height:6px"></div>')
    render_section(
        "Monthly Excel performance",
        "▦",
        "Traditional Sparta / Sparta2 sheets · legacy records through 17-Sep-2026",
    )
    st.caption(
        "This separate table reads the traditional Sparta (gid 1598890500) and Sparta2 (gid 1601740359) worksheets directly, "
        "using only legacy records through 17 September 2026. Its status columns are created only from status fields actually available in those legacy sheets; "
        "CRM-only fields such as Inbound Status and Inbound Remarks are deliberately excluded. "
        "September also appears in the CRM table below for records from 18 September onward. "
        "Attendance follows the existing working-day rule: Sundays and 1st/3rd Saturdays are excluded; "
        "P=1, HD=0.5, Ab/UL=0. SPD = applications ÷ total attendance."
    )

    # Build this table from the complete loaded frames rather than the already
    # filtered KPI/log frames (ag1/ag2). The source and agent filters are applied
    # explicitly here so a prior transformation in the main portal cannot make
    # the legacy table appear empty for every login.
    def _legacy_source_for_agent(source_frame, source_name):
        if not isinstance(source_frame, pd.DataFrame) or source_frame.empty:
            return pd.DataFrame()
        frame = source_frame.copy()
        if "Source" not in frame.columns:
            return pd.DataFrame()
        frame = frame[
            frame["Source"].fillna("").astype(str).str.strip().eq(source_name)
        ].copy()
        if frame.empty:
            return frame

        # Canonicalize usernames as well as spacing/case. This preserves the
        # per-agent access boundary while supporting the same aliases used by
        # the rest of the portal.
        if "Advisor" not in frame.columns:
            frame["Advisor"] = ""
        frame["_LegacyAdvisorKey"] = frame["Advisor"].apply(
            lambda value: re.sub(r"[^a-z0-9]", "", canonicalize_advisor(value).lower())
        )
        target_key = re.sub(r"[^a-z0-9]", "", canonicalize_advisor(agent).lower())
        frame = frame[frame["_LegacyAdvisorKey"].eq(target_key)].copy()
        return frame.drop(columns=["_LegacyAdvisorKey"], errors="ignore")

    # The fetch cache can contain frames created before a header variant was
    # normalized, so normalize once more at the table boundary as a safeguard.
    _monthly_legacy_sparta = normalize_legacy_sheet_columns(df1, "Sparta")
    _monthly_legacy_sparta2 = normalize_legacy_sheet_columns(df2_raw, "Sparta2")
    legacy_apps = _legacy_source_for_agent(_monthly_legacy_sparta, "Google - Sparta")
    legacy_portal = _legacy_source_for_agent(_monthly_legacy_sparta2, "Google - Sparta2")
    _legacy_rows_available = 0
    if "Source" in _monthly_legacy_sparta.columns:
        _legacy_rows_available += int(_monthly_legacy_sparta["Source"].fillna("").astype(str).str.strip().eq("Google - Sparta").sum())
    if "Source" in _monthly_legacy_sparta2.columns:
        _legacy_rows_available += int(_monthly_legacy_sparta2["Source"].fillna("").astype(str).str.strip().eq("Google - Sparta2").sum())
    _legacy_agent_rows = len(legacy_apps) + len(legacy_portal)

    if not legacy_apps.empty:
        if "Date_Parsed" not in legacy_apps.columns:
            legacy_apps["Date_Parsed"] = pd.NaT
        legacy_apps["Date_Parsed"] = pd.to_datetime(legacy_apps["Date_Parsed"], errors="coerce")
        if legacy_apps["Date_Parsed"].isna().all():
            for _date_col in ("Standardized_Date", "Sale Date", "Date"):
                if _date_col in legacy_apps.columns:
                    _parsed_dates = parse_date_series(legacy_apps[_date_col])
                    if _parsed_dates.notna().any():
                        legacy_apps["Date_Parsed"] = _parsed_dates
                        break
        legacy_apps = legacy_apps[
            legacy_apps["Date_Parsed"].notna()
            & (legacy_apps["Date_Parsed"].dt.date <= LEGACY_SOURCE_CUTOFF.date())
            & (legacy_apps["Date_Parsed"].dt.date <= today_date)
        ].copy()
        if not legacy_apps.empty:
            # IMPORTANT: df1 is concatenated with CRM rows before reaching this
            # table. Therefore the combined frame may already contain _RecordKey,
            # but legacy rows can have that field blank. Always rebuild the key
            # from the legacy sheet's own date + phone columns.
            legacy_apps = add_record_keys(legacy_apps, "Standardized_Date", "CLI")
            legacy_apps["_RecordKey"] = legacy_apps["_RecordKey"].fillna("").astype(str).str.strip()

            # Deduplicate only rows that have the agreed Sale Date + phone key.
            # A dated application with a missing phone must still count as an
            # application; it simply cannot be joined to a Sparta2 outcome row.
            _legacy_has_key = legacy_apps["_RecordKey"].ne("")
            _legacy_keyed = legacy_apps.loc[_legacy_has_key].drop_duplicates(
                subset=["_RecordKey"], keep="last"
            )
            _legacy_unkeyed = legacy_apps.loc[~_legacy_has_key]
            legacy_apps = pd.concat(
                [_legacy_keyed, _legacy_unkeyed], axis=0
            ).sort_index(kind="stable")

    if not legacy_portal.empty:
        if "Date_Parsed" not in legacy_portal.columns:
            legacy_portal["Date_Parsed"] = pd.NaT
        legacy_portal["Date_Parsed"] = pd.to_datetime(legacy_portal["Date_Parsed"], errors="coerce")
        if legacy_portal["Date_Parsed"].isna().all():
            for _date_col in ("Sale Date", "Standardized_Date", "Date"):
                if _date_col in legacy_portal.columns:
                    _parsed_dates = parse_date_series(legacy_portal[_date_col])
                    if _parsed_dates.notna().any():
                        legacy_portal["Date_Parsed"] = _parsed_dates
                        break
        legacy_portal = legacy_portal[
            legacy_portal["Date_Parsed"].notna()
            & (legacy_portal["Date_Parsed"].dt.date <= LEGACY_SOURCE_CUTOFF.date())
            & (legacy_portal["Date_Parsed"].dt.date <= today_date)
        ].copy()
        if not legacy_portal.empty:
            # As above, do not trust an existing combined-frame _RecordKey for
            # legacy rows: regenerate from the original Sparta2 Sale Date + phone.
            legacy_portal = add_record_keys(legacy_portal, "Sale Date", "Telephone No.")
            legacy_portal["_RecordKey"] = legacy_portal["_RecordKey"].fillna("").astype(str).str.strip()
            legacy_portal = legacy_portal[
                legacy_portal["_RecordKey"].ne("")
            ].drop_duplicates(subset=["_RecordKey"], keep="last")

    legacy_monthly = pd.DataFrame()
    legacy_daily = pd.DataFrame()
    legacy_status_specs = []
    if not legacy_apps.empty:
        # Determine the Welcome field from values actually present on legacy rows.
        # The combined frame may contain CRM-only headers, so column existence
        # alone is not enough to decide which traditional sheet field to use.
        legacy_wc_col = None
        for _candidate_wc in ("Status", "Welcome call Status"):
            if _candidate_wc in legacy_apps.columns:
                _nonblank_wc = legacy_apps[_candidate_wc].apply(clean_reason_text)
                if _nonblank_wc.astype(str).str.strip().ne("").any():
                    legacy_wc_col = _candidate_wc
                    break
        # Only use legacy sheet fields. Never add CRM-only Inbound columns here.
        legacy_field_candidates = [
            ("Quality", "Quality Status", legacy_apps),
            ("Welcome Call", legacy_wc_col, legacy_apps),
            ("Confirmation", "CallStatus_portal", legacy_portal),
            ("Portal / Live", "Status_portal", legacy_portal),
        ]
        for group_name, field_name, source_frame in legacy_field_candidates:
            source_field_name = field_name.removesuffix("_portal") if field_name else None
            if source_field_name and not source_frame.empty and source_field_name in source_frame.columns:
                raw_values = source_frame[source_field_name].apply(clean_reason_text)
                distinct = []
                seen = set()
                for raw in raw_values:
                    label = re.sub(r"\s+", " ", str(raw or "")).strip()
                    key = normalize_workflow_status(label)
                    if key and key not in seen:
                        seen.add(key)
                        distinct.append((key, label))
                if distinct:
                    legacy_status_specs.append((group_name, field_name, distinct))

        # Join Sparta2 outcomes to Sparta applications using the same Sale Date
        # + normalized phone key used by the portal log. Do not match by phone alone.
        if not legacy_portal.empty:
            portal_keep = ["_RecordKey"]
            for _group, _field, _distinct in legacy_status_specs:
                _source_field = _field.removesuffix("_portal")
                if _source_field in legacy_portal.columns and _source_field not in portal_keep:
                    portal_keep.append(_source_field)
            portal_status_frame = legacy_portal[portal_keep].drop_duplicates("_RecordKey", keep="last").rename(
                columns={"CallStatus": "CallStatus_portal", "Status": "Status_portal"}
            )
            legacy_work = legacy_apps.merge(
                portal_status_frame, on="_RecordKey", how="left", suffixes=("", "_portal"),
                validate="one_to_one",
            )
        else:
            legacy_work = legacy_apps.copy()

        legacy_work["_Month"] = legacy_work["Date_Parsed"].dt.to_period("M")
        legacy_work["_SaleDay"] = legacy_work["Date_Parsed"].dt.date

        # Attendance uses the selected agent's already-filtered attendance frame.
        legacy_attendance = ag_attendance.copy() if isinstance(ag_attendance, pd.DataFrame) else pd.DataFrame()
        if not legacy_attendance.empty:
            if "Date_Parsed" not in legacy_attendance.columns:
                legacy_attendance["Date_Parsed"] = parse_date_series(
                    legacy_attendance.get("Date", pd.Series(index=legacy_attendance.index, dtype=object))
                )
            legacy_attendance["Date_Parsed"] = pd.to_datetime(legacy_attendance["Date_Parsed"], errors="coerce")
            if "Attendance_Code" not in legacy_attendance.columns:
                legacy_attendance["Attendance_Code"] = legacy_attendance.get(
                    "Attendance", pd.Series("-", index=legacy_attendance.index)
                ).apply(normalize_attendance_status)
            legacy_attendance = legacy_attendance[legacy_attendance["Date_Parsed"].notna()].copy()
            legacy_attendance["_AttendanceDate"] = legacy_attendance["Date_Parsed"].dt.date
            legacy_attendance = legacy_attendance.drop_duplicates("_AttendanceDate", keep="last")
        legacy_attendance_by_date = (
            dict(zip(legacy_attendance["_AttendanceDate"], legacy_attendance["Attendance_Code"]))
            if not legacy_attendance.empty else {}
        )
        legacy_attendance_units = {"P": 1.0, "HD": 0.5, "Ab": 0.0, "UL": 0.0}

        legacy_month_rows, legacy_day_rows = [], []
        legacy_month_set = set(legacy_work["_Month"].dropna().tolist())
        # Preserve September in the Excel table as the legacy side of the
        # mid-month source split, even when this agent had no Sep 1–17 sale.
        if CRM_SOURCE_START.to_period("M") == LEGACY_SOURCE_CUTOFF.to_period("M"):
            overlap_period = LEGACY_SOURCE_CUTOFF.to_period("M")
            if overlap_period.start_time.date() <= today_date:
                legacy_month_set.add(overlap_period)
        for month_period in sorted(legacy_month_set):
            month_work = legacy_work[legacy_work["_Month"] == month_period]
            month_start = month_period.start_time.date()
            month_end = min(month_period.end_time.date(), LEGACY_SOURCE_CUTOFF.date(), today_date)
            if month_start > month_end:
                continue
            all_dates = [month_start + datetime.timedelta(days=i)
                         for i in range((month_end - month_start).days + 1)]
            working_dates = [d for d in all_dates if not _monthly_table_is_holiday(d)]
            attendance_total = sum(
                legacy_attendance_units.get(str(legacy_attendance_by_date.get(d, "-")).strip(), 0.0)
                for d in working_dates
            )

            def _legacy_status_counts(frame):
                result = {}
                for group_name, field_name, distinct in legacy_status_specs:
                    actual_field = field_name
                    if actual_field not in frame.columns and f"{actual_field}_portal" in frame.columns:
                        actual_field = f"{actual_field}_portal"
                    if actual_field not in frame.columns:
                        continue
                    keys = frame[actual_field].apply(lambda v: normalize_workflow_status(clean_reason_text(v)))
                    for status_key, label in distinct:
                        result[f"{group_name} · {label}"] = int((keys == status_key).sum())
                return result

            app_count = int(len(month_work))
            month_row = {
                "Month": month_period.to_timestamp().strftime("%b-%Y"),
                "Total Attendance": f"{attendance_total:g}",
                "SPD": f"{app_count / attendance_total:.2f}" if attendance_total > 0 else "—",
                "Applications": app_count,
            }
            month_row.update(_legacy_status_counts(month_work))
            legacy_month_rows.append(month_row)

            for sale_day in all_dates:
                day_work = month_work[month_work["_SaleDay"] == sale_day]
                day_attendance = str(legacy_attendance_by_date.get(sale_day, "-")).strip()
                day_units = legacy_attendance_units.get(day_attendance, 0.0)
                day_count = int(len(day_work))
                day_row = {
                    "Date": sale_day.strftime("%a, %d %b"),
                    "_MonthKey": month_period.strftime("%Y-%m"),
                    "Attendance": day_attendance if day_attendance in {"P", "HD", "Ab", "UL"} else "-",
                    "SPD": f"{day_count / day_units:.2f}" if day_units > 0 else "—",
                    "Applications": day_count,
                }
                day_row.update(_legacy_status_counts(day_work))
                legacy_day_rows.append(day_row)

        legacy_dynamic_columns = [
            f"{group_name} · {label}"
            for group_name, _field, distinct in legacy_status_specs
            for _key, label in distinct
        ]
        legacy_monthly = pd.DataFrame(legacy_month_rows)
        legacy_daily = pd.DataFrame(legacy_day_rows)
        if not legacy_monthly.empty:
            for col in legacy_dynamic_columns:
                if col not in legacy_monthly.columns:
                    legacy_monthly[col] = 0
                legacy_monthly[col] = pd.to_numeric(legacy_monthly[col], errors="coerce").fillna(0).astype(int)
            legacy_monthly = legacy_monthly.reindex(
                columns=["Month", "Total Attendance", "SPD", "Applications"] + legacy_dynamic_columns
            )
        if not legacy_daily.empty:
            for col in legacy_dynamic_columns:
                if col not in legacy_daily.columns:
                    legacy_daily[col] = 0
                legacy_daily[col] = pd.to_numeric(legacy_daily[col], errors="coerce").fillna(0).astype(int)
            legacy_daily = legacy_daily.reindex(
                columns=["Date", "_MonthKey", "Attendance", "SPD", "Applications"] + legacy_dynamic_columns
            )

    # Even if this agent has no traditional application rows, show the shared
    # cutover month as a zero-sales legacy row. This makes September visible in
    # both reports and keeps the legacy attendance window limited to 17 Sep.
    legacy_used_zero_fallback = False
    if legacy_monthly.empty and CRM_SOURCE_START.to_period("M") == LEGACY_SOURCE_CUTOFF.to_period("M"):
        overlap_period = LEGACY_SOURCE_CUTOFF.to_period("M")
        overlap_start = overlap_period.start_time.date()
        overlap_end = min(overlap_period.end_time.date(), LEGACY_SOURCE_CUTOFF.date(), today_date)
        if overlap_start <= overlap_end:
            fallback_attendance = ag_attendance.copy() if isinstance(ag_attendance, pd.DataFrame) else pd.DataFrame()
            if not fallback_attendance.empty:
                if "Date_Parsed" not in fallback_attendance.columns:
                    fallback_attendance["Date_Parsed"] = parse_date_series(
                        fallback_attendance.get("Date", pd.Series(index=fallback_attendance.index, dtype=object))
                    )
                fallback_attendance["Date_Parsed"] = pd.to_datetime(fallback_attendance["Date_Parsed"], errors="coerce")
                if "Attendance_Code" not in fallback_attendance.columns:
                    fallback_attendance["Attendance_Code"] = fallback_attendance.get(
                        "Attendance", pd.Series("-", index=fallback_attendance.index)
                    ).apply(normalize_attendance_status)
                fallback_attendance = fallback_attendance[fallback_attendance["Date_Parsed"].notna()].copy()
                fallback_attendance["_AttendanceDate"] = fallback_attendance["Date_Parsed"].dt.date
                fallback_attendance = fallback_attendance.drop_duplicates("_AttendanceDate", keep="last")
                fallback_attendance_by_date = dict(zip(
                    fallback_attendance["_AttendanceDate"], fallback_attendance["Attendance_Code"]
                ))
            else:
                fallback_attendance_by_date = {}
            fallback_units = {"P": 1.0, "HD": 0.5, "Ab": 0.0, "UL": 0.0}
            fallback_dates = [overlap_start + datetime.timedelta(days=i)
                              for i in range((overlap_end - overlap_start).days + 1)]
            fallback_working_dates = [d for d in fallback_dates if not _monthly_table_is_holiday(d)]
            fallback_total = sum(
                fallback_units.get(str(fallback_attendance_by_date.get(d, "-")).strip(), 0.0)
                for d in fallback_working_dates
            )
            legacy_monthly = pd.DataFrame([{
                "Month": overlap_period.to_timestamp().strftime("%b-%Y"),
                "Total Attendance": f"{fallback_total:g}",
                "SPD": "0.00" if fallback_total > 0 else "—",
                "Applications": 0,
            }])
            fallback_days = []
            for sale_day in fallback_dates:
                attendance_code = str(fallback_attendance_by_date.get(sale_day, "-")).strip()
                day_units = fallback_units.get(attendance_code, 0.0)
                fallback_days.append({
                    "Date": sale_day.strftime("%a, %d %b"),
                    "_MonthKey": overlap_period.strftime("%Y-%m"),
                    "Attendance": attendance_code if attendance_code in {"P", "HD", "Ab", "UL"} else "-",
                    "SPD": "0.00" if day_units > 0 else "—",
                    "Applications": 0,
                })
            legacy_daily = pd.DataFrame(fallback_days)
            legacy_dynamic_columns = []
            legacy_status_specs = []
            legacy_used_zero_fallback = True

    if legacy_used_zero_fallback:
        st.caption(
            f"Legacy source diagnostic · traditional rows available after the 17-Sep cutoff: {_legacy_rows_available:,} · "
            f"rows matched to this account: {_legacy_agent_rows:,}. "
            "A zero-sales September row is being shown because no eligible Sparta application rows matched this account. "
            "If traditional rows are available but matches are zero, check advisor names in the legacy sheets against the portal login."
        )

    if legacy_monthly.empty:
        st.info("No traditional Sparta / Sparta2 applications are available for your account through 17-Sep-2026.")
        # Actionable diagnostic: shows whether the issue is worksheet loading,
        # date filtering, or the selected account mapping without exposing rows.
        st.caption(
            f"Legacy source diagnostic · rows available after the date cutoff: {_legacy_rows_available:,} · "
            f"rows matched to this account: {_legacy_agent_rows:,}. "
            "If source rows are zero, check the worksheet date headers/values; if source rows are present but matches are zero, check the legacy advisor names against the portal login."
        )
    else:
        legacy_table_id = "excel-monthly-performance-table"
        legacy_groups = []
        for group_name, _field, distinct in legacy_status_specs:
            if any(f"{group_name} · {label}" in legacy_monthly.columns for _key, label in distinct):
                legacy_groups.append(group_name)
        legacy_group_colours = {
            "Monthly Summary": "#102451", "Quality": "#1D4ED8",
            "Welcome Call": "#0F766E", "Confirmation": "#6D28D9", "Portal / Live": "#92400E",
        }
        legacy_display_pairs = [("Monthly Summary", x) for x in ["Month", "Total Attendance", "SPD", "Applications"]]
        for col in legacy_monthly.columns:
            if " · " in col:
                group_name, label = col.split(" · ", 1)
                legacy_display_pairs.append((group_name, label))
        legacy_header_top = [
            '<th class="legacy-expand-head" rowspan="2"></th>',
            '<th class="legacy-group-header" colspan="4">Monthly Summary</th>'
        ]
        for group_name in legacy_groups:
            count = sum(1 for group, _label in legacy_display_pairs if group == group_name)
            if count:
                legacy_header_top.append(
                    f'<th class="legacy-group-header" colspan="{count}" '
                    f'style="background:{legacy_group_colours.get(group_name, "#475569")}">{escape(group_name)}</th>'
                )
        legacy_header_bottom = [
            f'<th class="legacy-sub-header">{escape(label)}</th>'
            for _group, label in legacy_display_pairs
        ]

        # Status-cell colours mirror the CRM table. Status columns are dynamic
        # because only values genuinely present in Sparta/Sparta2 are displayed.
        # Positive: green; pending/rework/SOP: amber; cancelled/rejected,
        # duplicate and missed outcomes: red; unknown values: neutral grey.
        _legacy_status_palettes = {
            "yellow": ("#FFFBEB", "#F59E0B"),
            "green": ("#ECFDF5", "#059669"),
            "red": ("#FEF2F2", "#DC2626"),
            "neutral": ("#F8FAFC", "#CBD5E1"),
        }

        def _legacy_status_family(column_name):
            if " · " in str(column_name):
                _group, _label = str(column_name).split(" · ", 1)
            else:
                _group, _label = "", str(column_name)
            _label_clean = re.sub(r"[^a-z0-9]+", " ", _label.casefold()).strip()
            _tokens = set(_label_clean.split())
            _compact = _label_clean.replace(" ", "")
            if (
                _tokens.intersection({
                    "cancel", "cancellation", "cancelled", "canceled",
                    "reject", "rejected", "duplicate", "missed",
                })
                or _compact in {"tobecancelled", "tobecanceled", "inboundcancel"}
                or "duplicate" in _compact
                or "missed" in _compact
            ):
                return "red"
            if (
                _tokens.intersection({"pending", "rework"})
                or "followup" in _compact
                or "portpending" in _compact
                or "reworkrequired" in _compact
            ):
                return "yellow"
            if _tokens.intersection({"approved", "done", "satisfied", "live"}) or _compact in {
                "rs/satisfied", "rp/satisfied", "rssatisfied", "rpsatisfied"
            }:
                return "green"
            return "neutral"

        def _legacy_blend_hex(low_hex, high_hex, ratio):
            low_rgb = tuple(int(low_hex[i:i + 2], 16) for i in (1, 3, 5))
            high_rgb = tuple(int(high_hex[i:i + 2], 16) for i in (1, 3, 5))
            rgb = tuple(round(a + (b - a) * ratio) for a, b in zip(low_rgb, high_rgb))
            return "#" + "".join(f"{component:02X}" for component in rgb)

        _legacy_status_families = {
            col: _legacy_status_family(col) for col in legacy_dynamic_columns
        }
        _legacy_status_max = {}
        for _col, _family in _legacy_status_families.items():
            _month_values = (
                pd.to_numeric(legacy_monthly[_col], errors="coerce").fillna(0)
                if _col in legacy_monthly.columns else pd.Series(dtype=float)
            )
            _day_values = (
                pd.to_numeric(legacy_daily[_col], errors="coerce").fillna(0)
                if _col in legacy_daily.columns else pd.Series(dtype=float)
            )
            _legacy_status_max[(_family, "month")] = max(
                _legacy_status_max.get((_family, "month"), 0),
                float(_month_values.max()) if not _month_values.empty else 0,
            )
            _legacy_status_max[(_family, "day")] = max(
                _legacy_status_max.get((_family, "day"), 0),
                float(_day_values.max()) if not _day_values.empty else 0,
            )

        def _legacy_status_cell_html(column_name, value, row_kind):
            try:
                count = int(value) if pd.notna(value) else 0
            except (TypeError, ValueError):
                count = 0
            family = _legacy_status_families.get(column_name, "neutral")
            low_hex, high_hex = _legacy_status_palettes[family]
            maximum = _legacy_status_max.get((family, row_kind), 0)
            # Keep zero cells subtly tinted to reveal the status category while
            # reserving stronger colour for non-zero counts.
            ratio = 0.0 if count <= 0 or maximum <= 0 else 0.16 + 0.84 * min(1.0, count / maximum)
            background = _legacy_blend_hex(low_hex, high_hex, ratio)
            foreground = "#FFFFFF" if family in {"green", "red"} and ratio >= 0.68 else "#334155"
            display_value = "—" if count <= 0 else f"{count:,}"
            return (
                f'<td class="legacy-status-number {family}" '
                f'style="background:{background};color:{foreground};font-weight:750;text-align:center;">'
                f'{display_value}</td>'
            )

        legacy_rows_html = []
        for _, row in legacy_monthly.iterrows():
            month_label = str(row["Month"])
            parsed = pd.to_datetime(month_label, format="%b-%Y", errors="coerce")
            month_key = parsed.strftime("%Y-%m") if pd.notna(parsed) else re.sub(r"[^A-Za-z0-9_-]", "", month_label)
            group_id = f"excel-month-{month_key}"
            legacy_rows_html.append(
                f'<tr class="legacy-month-row"><td class="legacy-expand-cell"><button type="button" '
                f'class="legacy-expand-button" data-group="{escape(group_id)}" aria-expanded="false" title="Expand daily breakdown">+</button></td>'
                f'<td class="legacy-month-cell">{escape(month_label)}</td>'
                f'<td class="legacy-number">{escape(str(row["Total Attendance"]))}</td>'
                f'<td class="legacy-number">{escape(str(row["SPD"]))}</td>'
                f'<td class="legacy-number legacy-apps-number">{int(row["Applications"]):,}</td>'
            )
            for col in legacy_dynamic_columns:
                legacy_rows_html.append(_legacy_status_cell_html(col, row.get(col, 0), "month"))
            legacy_rows_html.append('</tr>')
            month_daily = legacy_daily[legacy_daily["_MonthKey"].astype(str).eq(month_key)] if not legacy_daily.empty else pd.DataFrame()
            for _, day in month_daily.iterrows():
                legacy_rows_html.append(
                    f'<tr class="legacy-daily-row" data-parent="{escape(group_id)}"><td class="legacy-expand-cell"></td>'
                    f'<td class="legacy-date-cell">↳ {escape(str(day["Date"]))}</td>'
                    f'<td class="legacy-number">{escape(str(day["Attendance"]))}</td>'
                    f'<td class="legacy-number">{escape(str(day["SPD"]))}</td>'
                    f'<td class="legacy-number">{int(day["Applications"]):,}</td>'
                )
                for col in legacy_dynamic_columns:
                    legacy_rows_html.append(_legacy_status_cell_html(col, day.get(col, 0), "day"))
                legacy_rows_html.append('</tr>')
        legacy_html = f"""
        <style>
          .legacy-monthly-wrap,.legacy-monthly-wrap * {{box-sizing:border-box;}}
          .legacy-monthly-wrap {{width:100%;max-width:100%;overflow-x:auto;overflow-y:visible;border:1px solid #D9E2F0;border-radius:10px;background:#fff;font-family:Arial,sans-serif;color:#1E293B;}}
          .legacy-monthly-table {{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%;font-size:12px;}}
          .legacy-monthly-table th,.legacy-monthly-table td {{padding:6px 8px;border-right:1px solid #E2E8F0;border-bottom:1px solid #E2E8F0;white-space:nowrap;}}
          .legacy-monthly-table thead th {{position:sticky;z-index:5;text-align:center;}}
          .legacy-group-header {{top:0;background:#102451;color:#fff;font-size:11px;font-weight:850;padding:8px 7px!important;}}
          .legacy-expand-head {{min-width:34px;width:34px;background:#102451;}}
          .legacy-sub-header {{top:31px;background:#EAF0F8;color:#26364F;font-size:10px;font-weight:800;}}
          .legacy-expand-cell {{width:34px;min-width:34px;text-align:center;padding:3px 4px;background:#F8FAFC;}}
          .legacy-expand-button {{width:23px;height:23px;padding:0;border:1px solid #CBD5E1;border-radius:6px;background:#fff;color:#334155;font-size:16px;line-height:20px;font-weight:800;cursor:pointer;}}
          .legacy-month-row td {{background:#F1F5FF;font-weight:750;}}
          .legacy-month-cell {{color:#102451;}}
          .legacy-daily-row {{display:none;}}
          .legacy-daily-row.shown {{display:table-row;}}
          .legacy-daily-row td {{font-size:11px;}}
          .legacy-date-cell {{background:#F8FAFC;color:#475569;padding-left:12px;}}
          .legacy-number,.legacy-status-number {{text-align:center;font-variant-numeric:tabular-nums;}}
          .legacy-apps-number {{color:#102451;font-weight:850;}}
          .legacy-status-number {{font-weight:750;}}
          .legacy-monthly-table tbody tr:hover td {{box-shadow:inset 0 0 0 9999px rgba(219,234,254,.18);}}
        </style>
        <div class="legacy-monthly-wrap"><table id="{legacy_table_id}" class="legacy-monthly-table">
        <thead><tr>{''.join(legacy_header_top)}</tr><tr>{''.join(legacy_header_bottom)}</tr></thead>
        <tbody>{''.join(legacy_rows_html)}</tbody></table></div>
        <script>(function(){{const table=document.getElementById("{legacy_table_id}");if(!table)return;
        table.querySelectorAll('.legacy-expand-button').forEach(function(button){{button.addEventListener('click',function(){{
        const id=button.getAttribute('data-group');const rows=Array.from(table.tBodies[0].querySelectorAll('tr.legacy-daily-row[data-parent="'+id+'"]'));
        const expand=button.getAttribute('aria-expanded')!=='true';rows.forEach(function(row){{row.classList.toggle('shown',expand);}});
        button.setAttribute('aria-expanded',expand?'true':'false');button.textContent=expand?'−':'+';button.title=expand?'Collapse daily breakdown':'Expand daily breakdown';
        }});}});}})();</script>
        """
        try:
            st.html(legacy_html, unsafe_allow_javascript=True)
        except TypeError:
            legacy_html_fallback = legacy_html.replace('</script>', '</script>', 1)
            if hasattr(st, "iframe"):
                st.iframe(legacy_html_fallback, width="stretch", height="content", alt="Traditional Excel monthly performance with expandable daily rows")
            else:
                components.html(legacy_html_fallback, height=260, scrolling=False)

    # ------------------------------------------------------------------------
    # MONTHLY CRM-ONLY SUMMARY
    # ------------------------------------------------------------------------
    st.html('<div style="height:6px"></div>')
    render_section(
        "Monthly CRM performance",
        "▦",
        "CRM mirror only · status counts show raw workflow values",
    )
    st.caption(
        "This table is agent-specific and independent of the main date filter. "
        "September starts at the CRM cutover (18 Sep 2026); the current month is month-to-date. "
        "If Inbound Status is populated, that record is counted only under Inbound and excluded from other stage status counts. "
        "Monthly Total Attendance = summed attendance units on scheduled working days (P=1, HD=0.5, Ab/UL=0). "
        "Expanded daily rows show the attendance code (P, Ab, HD or UL). SPD = CRM applications ÷ total attendance. "
        "Sundays and 1st/3rd Saturdays are excluded from monthly attendance totals."
    )
    monthly_crm_summary, daily_crm_summary = build_crm_monthly_summary(
        ag1, ag2, ag_attendance, as_of=today_date
    )
    if monthly_crm_summary.empty:
        st.info("No CRM mirror applications are available for your account yet.")
    else:
        # Compact two-level headers: workflow groups on the first row and
        # individual status names on the second row. Native Streamlit controls
        # above the table toggle each month's daily rows without iframe overlap.
        workflow_groups = ["Inbound", "Quality", "Welcome", "Committed", "Onboarding"]

        def compact_status_header(group_name, label):
            text = str(label).strip()
            prefixes = {
                "Inbound": r"^Inbound[-\s]+",
                "Quality": r"^QA[-\s]+",
                "Welcome": r"^(?:Welcome|WC)[-\s]+",
                "Committed": r"^(?:Confirmation|Committed)[-\s]+",
                "Onboarding": r"^Onboarding[-\s]+",
            }
            pattern = prefixes.get(group_name)
            if pattern:
                text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
            return text or str(label).strip()

        summary_columns = ["Month", "Total Attendance", "SPD", "Applications"]
        status_columns = [
            col for col in monthly_crm_summary.columns
            if col not in set(summary_columns)
        ]
        display_pairs = [("Monthly Summary", name) for name in summary_columns]
        for col in status_columns:
            group_name, raw_label = col.split(" · ", 1)
            display_pairs.append((group_name, compact_status_header(group_name, raw_label)))

        header_colours = {
            "Monthly Summary": "#102451",
            "Inbound": "#475569",
            "Quality": "#1D4ED8",
            "Welcome": "#0F766E",
            "Committed": "#6D28D9",
            "Onboarding": "#92400E",
        }

        def status_colour_family(group_name, short_label):
            """Assign a consistent semantic colour to CRM and legacy status columns."""
            label = re.sub(r"[^a-z0-9]+", " ", str(short_label).casefold()).strip()
            tokens = set(label.split())
            compact = label.replace(" ", "")

            # Negative / terminal outcomes. Match singular as well as plural
            # forms because the traditional sheets use labels such as "Cancel"
            # and "Quality Reject", while CRM may use "Cancelled" / "Rejected".
            if (
                tokens.intersection({
                    "cancel", "cancellation", "cancelled", "canceled",
                    "reject", "rejected", "duplicate", "missed",
                })
                or compact in {"tobecancelled", "tobecanceled", "inboundcancel"}
                or "duplicate" in compact
                or "missed" in compact
            ):
                return "red"

            # Waiting / work-in-progress / follow-up states.
            if (
                tokens.intersection({"pending", "rework"})
                or "followup" in compact
                or "portpending" in compact
                or "reworkrequired" in compact
            ):
                return "yellow"

            # Positive outcomes across both sources.
            if tokens.intersection({"approved", "done", "satisfied", "live"}) or compact in {
                "rs/satisfied", "rp/satisfied", "rssatisfied", "rpsatisfied"
            }:
                return "green"
            return "neutral"

        status_palettes = {
            "yellow": ("#FFFBEB", "#F59E0B"),
            "green": ("#ECFDF5", "#059669"),
            "red": ("#FEF2F2", "#DC2626"),
            "neutral": ("#F8FAFC", "#CBD5E1"),
        }

        def blend_hex(low_hex, high_hex, ratio):
            low_rgb = tuple(int(low_hex[i:i + 2], 16) for i in (1, 3, 5))
            high_rgb = tuple(int(high_hex[i:i + 2], 16) for i in (1, 3, 5))
            rgb = tuple(round(a + (b - a) * ratio) for a, b in zip(low_rgb, high_rgb))
            return "#" + "".join(f"{component:02X}" for component in rgb)

        status_families = {}
        for group_name, short_label in display_pairs:
            if group_name != "Monthly Summary":
                matching_col = next(
                    col for col in status_columns
                    if col.split(" · ", 1)[0] == group_name
                    and compact_status_header(group_name, col.split(" · ", 1)[1]) == short_label
                )
                status_families[matching_col] = status_colour_family(group_name, short_label)

        # Scale monthly and daily shades separately so daily counts remain
        # visually meaningful instead of being washed out by monthly totals.
        shade_max = {}
        for col, family in status_families.items():
            month_values = pd.to_numeric(monthly_crm_summary[col], errors="coerce").fillna(0)
            day_values = (
                pd.to_numeric(daily_crm_summary[col], errors="coerce").fillna(0)
                if col in daily_crm_summary.columns else pd.Series(dtype=float)
            )
            shade_max[(family, "month")] = max(
                shade_max.get((family, "month"), 0),
                float(month_values.max()) if not month_values.empty else 0,
            )
            shade_max[(family, "day")] = max(
                shade_max.get((family, "day"), 0),
                float(day_values.max()) if not day_values.empty else 0,
            )

        def status_cell_html(col, value, row_kind):
            try:
                count = int(value) if pd.notna(value) else 0
            except (TypeError, ValueError):
                count = 0
            family = status_families.get(col, "neutral")
            low_hex, high_hex = status_palettes[family]
            maximum = shade_max.get((family, row_kind), 0)
            ratio = 0.0 if count <= 0 or maximum <= 0 else 0.16 + 0.84 * min(1.0, count / maximum)
            background = blend_hex(low_hex, high_hex, ratio)
            foreground = "#FFFFFF" if family in {"green", "red"} and ratio >= 0.68 else "#334155"
            display_value = "—" if count <= 0 else f"{count:,}"
            return (
                f'<td class="status-cell" style="background:{background};color:{foreground};'
                f'font-weight:750;text-align:center;">{display_value}</td>'
            )

        def basic_cell_html(value, extra_class=""):
            safe_value = escape(str(value))
            return f'<td class="{extra_class}">{safe_value}</td>'

        group_counts = {}
        for group_name, _label in display_pairs:
            group_counts[group_name] = group_counts.get(group_name, 0) + 1

        header_row_one = ['<th class="group-header summary-group" colspan="4">Monthly Summary</th>']
        for group_name in workflow_groups:
            count = sum(1 for pair in display_pairs if pair[0] == group_name)
            if count:
                header_row_one.append(
                    f'<th class="group-header" colspan="{count}" '
                    f'style="background:{header_colours[group_name]}">{escape(group_name)}</th>'
                )

        header_row_two = []
        for group_name, label in display_pairs:
            if group_name == "Monthly Summary":
                shown_label = label
            else:
                shown_label = label
            header_row_two.append(
                f'<th class="sub-header" style="border-top:3px solid '
                f'{header_colours.get(group_name, "#CBD5E1")}">{escape(shown_label)}</th>'
            )

        def monthly_summary_key(month_label):
            # Derive the key from the month label without relying on locale-sensitive parsing.
            parsed_month = pd.to_datetime(str(month_label), format="%b-%Y", errors="coerce")
            if pd.isna(parsed_month):
                return re.sub(r"[^A-Za-z0-9_-]", "", str(month_label))
            return parsed_month.strftime("%Y-%m")

        # Match the internal row expander design used by the Executive Dashboard's
        # Monthly KPI Breakdown. The iframe must follow its content height: when
        # every month is collapsed it shows only the monthly summary rows; when a
        # month is expanded the daily rows increase the iframe height naturally,
        # pushing Recent Applications Log down; collapsing removes that height.
        table_id = "crm-monthly-performance-table"

        table_rows_html = []
        for _, month_row in monthly_crm_summary.iterrows():
            month_label = str(month_row["Month"])
            month_key = monthly_summary_key(month_label)
            group_id = f"crm-month-{month_key}"
            table_rows_html.append(
                f'<tr class="month-row" data-group="{escape(group_id)}">'
                f'<td class="expand-cell"><button type="button" class="expand-button" '
                f'aria-expanded="false" data-group="{escape(group_id)}" '
                f'title="Expand daily breakdown">+</button></td>'
            )
            table_rows_html.append(
                f'<td class="month-cell"><strong>{escape(month_label)}</strong></td>'
            )
            table_rows_html.append(
                basic_cell_html(month_row["Total Attendance"], "numeric-cell attendance-total-cell")
            )
            table_rows_html.append(basic_cell_html(month_row["SPD"], "numeric-cell spd-cell"))
            table_rows_html.append(
                basic_cell_html(f'{int(month_row["Applications"]):,}', "numeric-cell applications-cell")
            )
            for col in status_columns:
                table_rows_html.append(status_cell_html(col, month_row.get(col, 0), "month"))
            table_rows_html.append("</tr>")

            month_daily = (
                daily_crm_summary[
                    daily_crm_summary["_MonthKey"].astype(str).eq(month_key)
                ]
                if not daily_crm_summary.empty
                else pd.DataFrame()
            )
            for _, day_row in month_daily.iterrows():
                table_rows_html.append(
                    f'<tr class="daily-row" data-parent="{escape(group_id)}">'
                    '<td class="expand-cell"></td>'
                )
                table_rows_html.append(
                    f'<td class="date-cell"><span class="daily-indent">↳</span>'
                    f'{escape(str(day_row["Date"]))}</td>'
                )
                table_rows_html.append(
                    basic_cell_html(day_row["Attendance"], "numeric-cell attendance-code-cell")
                )
                table_rows_html.append(basic_cell_html(day_row["SPD"], "numeric-cell spd-cell"))
                table_rows_html.append(
                    basic_cell_html(f'{int(day_row["Applications"]):,}', "numeric-cell applications-cell")
                )
                for col in status_columns:
                    table_rows_html.append(status_cell_html(col, day_row.get(col, 0), "day"))
                table_rows_html.append("</tr>")

        header_row_one = [
            '<th class="expand-head" rowspan="2" aria-label="Expand monthly details"></th>',
            '<th class="group-header summary-group" colspan="4">Monthly Summary</th>',
        ]
        for group_name in workflow_groups:
            count = sum(1 for pair in display_pairs if pair[0] == group_name)
            if count:
                header_row_one.append(
                    f'<th class="group-header" colspan="{count}" '
                    f'style="background:{header_colours[group_name]}">{escape(group_name)}</th>'
                )

        header_row_two = []
        for group_name, label in display_pairs:
            header_row_two.append(
                f'<th class="sub-header" style="border-top:3px solid '
                f'{header_colours.get(group_name, "#CBD5E1")}">{escape(label)}</th>'
            )

        table_html = f"""
        <style>
          /* Scoped to this table: the dashboard page itself is never sized or overflow-adjusted. */
          .crm-monthly-wrap, .crm-monthly-wrap * {{ box-sizing:border-box; }}
          .crm-monthly-wrap {{ display:block; width:100%; max-width:100%; height:auto; max-height:none;
            margin:0; padding:0; overflow-x:auto; overflow-y:visible; border:1px solid #D9E2F0;
            border-radius:10px; background:#fff; font-family:Arial,sans-serif; color:#1E293B;
            scrollbar-width:thin; }}
          .crm-monthly-table {{ border-collapse:separate; border-spacing:0; width:max-content; min-width:100%; font-size:12px; }}
          .crm-monthly-table th, .crm-monthly-table td {{ padding:6px 8px; border-right:1px solid #E2E8F0;
            border-bottom:1px solid #E2E8F0; white-space:nowrap; }}
          .crm-monthly-table thead th {{ position:sticky; z-index:5; text-align:center; }}
          .crm-monthly-table .group-header {{ top:0; background:#102451; color:#FFF; font-size:11px;
            font-weight:850; letter-spacing:.35px; padding:8px 7px !important; }}
          .crm-monthly-table .summary-group {{ background:#102451; }}
          .crm-monthly-table .expand-head {{ left:0; min-width:34px; width:34px; background:#102451; }}
          .crm-monthly-table .sub-header {{ top:31px; background:#EAF0F8; color:#26364F; font-size:10px; font-weight:800; }}
          .crm-monthly-table .expand-cell {{ width:34px; min-width:34px; text-align:center; padding:3px 4px; background:#F8FAFC; }}
          .crm-monthly-table .expand-button {{ width:23px; height:23px; padding:0; border:1px solid #CBD5E1;
            border-radius:6px; background:#FFF; color:#334155; font-size:16px; line-height:20px;
            font-weight:800; cursor:pointer; }}
          .crm-monthly-table .expand-button:hover {{ background:#EFF6FF; border-color:#93C5FD; }}
          .crm-monthly-table .month-row td {{ background-color:#F1F5FF; font-weight:750; }}
          .crm-monthly-table .month-row .month-cell {{ color:#102451; text-align:left; }}
          .crm-monthly-table .daily-row {{ display:none; }}
          .crm-monthly-table .daily-row.shown {{ display:table-row; }}
          .crm-monthly-table .daily-row td {{ font-size:11px; }}
          .crm-monthly-table .daily-row .date-cell {{ background:#F8FAFC; color:#475569; text-align:left; padding-left:12px; }}
          .crm-monthly-table .daily-indent {{ color:#94A3B8; margin-right:6px; }}
          .crm-monthly-table .numeric-cell {{ text-align:center; font-variant-numeric:tabular-nums; }}
          .crm-monthly-table .attendance-total-cell {{ color:#102451; font-weight:850; }}
          .crm-monthly-table .attendance-code-cell {{ color:#475569; font-weight:800; }}
          .crm-monthly-table .spd-cell {{ color:#0F766E; font-weight:750; }}
          .crm-monthly-table .applications-cell {{ color:#102451; font-weight:850; }}
          .crm-monthly-table tbody tr:hover td {{ box-shadow:inset 0 0 0 9999px rgba(219,234,254,.18); }}
        </style>
        <div class="crm-monthly-wrap">
          <table id="{table_id}" class="crm-monthly-table">
            <thead><tr>{''.join(header_row_one)}</tr><tr>{''.join(header_row_two)}</tr></thead>
            <tbody>{''.join(table_rows_html)}</tbody>
          </table>
        </div>
        <script>
          (function() {{
            const table = document.getElementById("{table_id}");
            if (!table) return;
            const tbody = table.tBodies[0];
            table.querySelectorAll('.expand-button').forEach(function(button) {{
              button.addEventListener('click', function() {{
                const groupId = button.getAttribute('data-group');
                const rows = Array.from(tbody.querySelectorAll(
                  'tr.daily-row[data-parent="' + groupId + '"]'
                ));
                const expand = button.getAttribute('aria-expanded') !== 'true';
                rows.forEach(function(row) {{ row.classList.toggle('shown', expand); }});
                button.setAttribute('aria-expanded', expand ? 'true' : 'false');
                button.textContent = expand ? '−' : '+';
                button.title = expand ? 'Collapse daily breakdown' : 'Expand daily breakdown';
              }});
            }});
            // The table is rendered directly into Streamlit's page (not in an
            // iframe). Hiding/showing rows therefore changes the page's natural
            // document flow immediately, without leaving an old iframe height behind.
          }})();
        </script>
        """
        # Render directly into the Streamlit document, rather than an iframe.
        # Native document flow automatically closes the space when rows are
        # collapsed, so the Recent Applications Log moves up immediately.
        # unsafe_allow_javascript is needed only for the table's local +/- controls.
        try:
            st.html(table_html, unsafe_allow_javascript=True)
        except TypeError:
            # Compatibility for Streamlit builds whose st.html has no JavaScript
            # flag yet. Dynamically resize the frame itself on every toggle so it
            # shrinks as well as grows (unlike a fixed-height components.html).
            frame_resize_script = r"""
              <script>
                (function() {
                  function fitMonthlyFrame() {
                    var wrap = document.querySelector('.crm-monthly-wrap');
                    if (!wrap || !window.frameElement) return;
                    var height = Math.ceil(wrap.getBoundingClientRect().height + 4);
                    window.frameElement.style.height = height + 'px';
                    window.frameElement.setAttribute('height', String(height));
                  }
                  document.querySelectorAll('.expand-button').forEach(function(button) {
                    button.addEventListener('click', function() {
                      requestAnimationFrame(function() { requestAnimationFrame(fitMonthlyFrame); });
                    });
                  });
                  if (typeof ResizeObserver !== 'undefined') {
                    new ResizeObserver(function() { requestAnimationFrame(fitMonthlyFrame); })
                      .observe(document.querySelector('.crm-monthly-wrap'));
                  }
                  window.addEventListener('load', fitMonthlyFrame);
                  requestAnimationFrame(fitMonthlyFrame);
                })();
              </script>
            """
            legacy_table_html = table_html.replace('</script>', '</script>' + frame_resize_script, 1)
            if hasattr(st, "iframe"):
                st.iframe(
                    legacy_table_html,
                    width="stretch",
                    height="content",
                    alt="Monthly CRM performance table with expandable daily rows",
                )
            else:
                components.html(legacy_table_html, height=260, scrolling=False)

    # ------------------------------------------------------------------------
    # RECENT APPLICATIONS LOG
    # ------------------------------------------------------------------------
    st.divider()
    render_section("Recent applications log", "⌕", "Detailed record-by-record view of your applications and downstream status")

    if not ag1.empty:
        ag2_clean = ag2.copy()
        # These downstream columns are optional in the legacy Sparta2 sheet and
        # may be absent entirely when the CRM mirror has no eligible rows. Add
        # blank defaults before selecting columns for the merge so the log never
        # crashes and all application rows remain visible.
        for _optional_log_col in (
            "Telephone No.", "LetterStatus", "Provisioning Status",
            "Provisioning Remarks", "CallStatus", "Comments",
            "Voice of Customer", "Cancellation Reason", "Status",
            "Committed Date", "Source",
        ):
            if _optional_log_col not in ag2_clean.columns:
                ag2_clean[_optional_log_col] = ""
        ag2_clean["Telephone No."] = ag2_clean["Telephone No."].astype(str).str.strip()
        ag2_clean = ag2_clean.rename(columns={
            "Status": "Portal Status",
            "Committed Date": "Live Date",
            "Downstream_Category": "_Internal_Downstream_Category",
            "Downstream_Review_Flag": "Classification Review",
        })

        # Use the same agreed Sale Date + Phone primary key in the detailed
        # portal log. This prevents a customer with the same number on a later
        # sale from receiving the wrong downstream status.
        ag2_clean = add_record_keys(ag2_clean, "Sale Date", "Telephone No.")
        # Never let missing/invalid keys join to one another in the log. For
        # repeated valid legacy keys, retain the existing latest-row-in-source
        # rule; CRM duplicate keys are already reduced to the latest mirror row.
        usable_log_keys = ag2_clean["_RecordKey"].fillna("").astype(str).str.strip().ne("")
        ag2_unique = (
            ag2_clean.loc[usable_log_keys]
            .sort_values("Date_Parsed")
            .drop_duplicates("_RecordKey", keep="last")
        )
        for _merge_col in (
            "_RecordKey", "Telephone No.", "LetterStatus",
            "Provisioning Status", "Provisioning Remarks", "CallStatus",
            "Comments", "Voice of Customer", "Cancellation Reason",
            "Portal Status", "_Internal_Downstream_Category",
            "Classification Review", "Live Date",
        ):
            if _merge_col not in ag2_unique.columns:
                ag2_unique[_merge_col] = ""

        ag1_log_base = ag1.copy()
        # Explicitly preserve CRM inbound fields through the record-level log merge.
        # Legacy rows have no inbound data, so they receive blank values and display "-".
        for _inbound_col in ("Inbound Status", "Inbound Remarks"):
            if _inbound_col not in ag1_log_base.columns:
                ag1_log_base[_inbound_col] = ""
            ag1_log_base[_inbound_col] = ag1_log_base[_inbound_col].apply(clean_reason_text)
        ag1_log_base = add_record_keys(ag1_log_base, "Standardized_Date", "CLI")
        merged_log = ag1_log_base.merge(
            ag2_unique[
                [
                    "_RecordKey",
                    "Telephone No.",
                    "LetterStatus",
                    "Provisioning Status",
                    "Provisioning Remarks",
                    "CallStatus",
                    "Comments",
                    "Voice of Customer",
                    "Cancellation Reason",
                    "Portal Status",
                    "_Internal_Downstream_Category",
                    "Classification Review",
                    "Live Date",
                ]
            ],
            on="_RecordKey",
            how="left",
        )

        # Guarantee the two requested columns exist in the visible log even if
        # legacy-only data is being viewed or an older record lacks these fields.
        for _inbound_col in ("Inbound Status", "Inbound Remarks"):
            if _inbound_col not in merged_log.columns:
                merged_log[_inbound_col] = ""

        # Show WC Pending in the log when the raw WC value maps to Others but
        # the quality stage is still QA-Pending or Rework.
        if "Status" in merged_log.columns:
            _wc_display = merged_log.apply(
                lambda row: map_wc_with_quality(
                    row.get("Status", ""), row.get("Quality Status", "")
                ), axis=1
            )
            _wc_override = (
                merged_log["Status"].apply(map_wc).eq("Others")
                & merged_log["Quality Status"].apply(map_quality).isin(["QA-Pending", "Rework"])
            )
            merged_log.loc[_wc_override, "Status"] = "WC Pending"

        merged_log["Sale Date"] = (
            pd.to_datetime(merged_log["Date_Parsed"], errors="coerce")
            .dt.strftime("%d-%m-%Y")
            .fillna("")
        )
        merged_log["Live Date"] = (
            parse_date_series(merged_log["Live Date"])
            .dt.strftime("%d-%m-%Y")
            .fillna("")
        )

        columns_layout = [
            ("Basic Info.", "S.No."),
            ("Basic Info.", "Sale Date"),
            ("Basic Info.", "Customer Name"),
            ("Basic Info.", "Verifier Name"),
            ("Basic Info.", "Agent Remarks"),
            ("Quality Audit", "Quality Status"),
            ("Quality Audit", "Quality Remarks"),
            ("Inbound", "Inbound Status"),
            ("Inbound", "Inbound Remarks"),
            ("Welcome Call", "Status"),
            ("Welcome Call", "Welcome call Remarks"),
            ("Live Status", "LetterStatus"),
            ("Provisioning", "Provisioning Status"),
            ("Provisioning", "Provisioning Remarks"),
            ("Live Status", "CallStatus"),
            ("Live Status", "Portal Status"),
            ("Live Status", "Classification Review"),
            ("Live Status", "Live Date"),
            ("Live Status", "Comments"),
            ("Live Status", "Voice of Customer"),
            ("Live Status", "Cancellation Reason"),
        ]

        # Smarter log controls: preserve the original date/month filters while adding
        # compact status pills and full-record search.
        log_col1, log_col2, log_col3 = st.columns([2.0, 2.55, 1.0], gap="small")

        with log_col1:
            log_filter_type = st.radio(
                "Log View Filter:",
                ["All Applications", "By Specific Date Range", "By Specific Month"],
                horizontal=True,
                key="log_filter_type",
            )

        with log_col2:
            if log_filter_type == "By Specific Date Range":
                ld_col1, ld_col2 = st.columns(2)
                with ld_col1:
                    log_start = st.date_input(
                        "Log Start Date",
                        today_date.replace(day=1),
                        key="log_start_date",
                    )
                with ld_col2:
                    log_end = st.date_input(
                        "Log End Date",
                        today_date,
                        key="log_end_date",
                    )
                recent_log = merged_log[
                    date_range_mask(merged_log["Date_Parsed"], log_start, log_end)
                ].sort_values(by="Date_Parsed", ascending=False)
            elif log_filter_type == "By Specific Month":
                unique_months = sorted(
                    merged_log["Date_Parsed"].dt.strftime("%Y-%m").dropna().unique(),
                    reverse=True,
                )
                if unique_months:
                    selected_month = st.selectbox(
                        "Select Month for Log (YYYY-MM):",
                        unique_months,
                        key="log_selected_month",
                    )
                    recent_log = merged_log[
                        merged_log["Date_Parsed"].dt.strftime("%Y-%m") == selected_month
                    ].sort_values(by="Date_Parsed", ascending=False)
                else:
                    recent_log = merged_log[0:0]
            else:
                recent_log = merged_log.sort_values(by="Date_Parsed", ascending=False)

        with log_col3:
            row_limit = st.selectbox(
                "Show records per page:",
                [5, 10, 20, 50, 100, "All"],
                index=2,
                key="log_row_limit",
            )

        # Full-record search for the application log.
        # This must be defined before the filtering logic below.
        log_search = st.text_input(
            "Search applications",
            placeholder="Search customer, phone, quality/inbound remarks, WC remark, cancellation reason…",
            key="log_search",
        )

        # --------------------------------------------------------------------
        # ADVANCED HIERARCHICAL STATUS FILTERS
        # --------------------------------------------------------------------
        # Within one stage, checked statuses are combined with OR.
        # Across selected stages, filters are combined with AND.
        # Example: Quality > Approved + Welcome Call > Done returns records
        # that are both QA Approved AND Welcome Call Done.
        log_filter_source = merged_log.copy()
        log_filter_source["Q_Filter_Status"] = log_filter_source.get(
            "Quality Status", pd.Series("", index=log_filter_source.index)
        ).apply(map_quality)

        wc_filter_source_col = wc_col if wc_col and wc_col in log_filter_source.columns else (
            "Status" if "Status" in log_filter_source.columns else None
        )
        if wc_filter_source_col:
            log_filter_source["WC_Filter_Status"] = log_filter_source.apply(
                lambda row: map_wc_with_quality(
                    row.get(wc_filter_source_col, ""), row.get("Quality Status", "")
                ), axis=1
            )
        else:
            log_filter_source["WC_Filter_Status"] = "Others"

        log_filter_source["P_Filter_Status"] = log_filter_source.get(
            "_Internal_Downstream_Category",
            pd.Series("Unclassified / Review", index=log_filter_source.index),
        ).fillna("Unclassified / Review")

        quality_options = ["Approved", "QA-Pending", "Cancelled", "Rework", "Rejected", "Others"]
        welcome_options = ["Done", "Follow up", "Pending", "Paperwork", "Cancelled", "Others"]
        live_options = list(DOWNSTREAM_CATEGORY_ORDER)

        with st.expander("☷  Advanced status filters", expanded=False):
            st.caption(
                "Select one or more statuses at each level. Multiple selections within a level are OR; "
                "selected levels are AND. Leave every box unticked to show all applications."
            )

            # Reset by rotating the widget-key namespace instead of modifying
            # instantiated checkbox state. This avoids Streamlit's
            # `st.session_state.<widget_key>` modification error.
            if "log_status_filter_version" not in st.session_state:
                st.session_state.log_status_filter_version = 0

            if st.button("Clear status filters", key="clear_log_status_filters"):
                st.session_state.log_status_filter_version += 1
                st.rerun()

            filter_version = st.session_state.log_status_filter_version
            filter_header_cols = st.columns(3)
            selected_quality = []
            selected_wc = []
            selected_live = []

            with filter_header_cols[0]:
                st.markdown("**01 · Quality Audit**")
                for status_name in quality_options:
                    widget_key = f"log_q_status_v{filter_version}_{status_name.lower().replace(' ', '_')}"
                    if st.checkbox(status_name, key=widget_key):
                        selected_quality.append(status_name)

            with filter_header_cols[1]:
                st.markdown("**02 · Welcome Call**")
                for status_name in welcome_options:
                    widget_key = f"log_wc_status_v{filter_version}_{status_name.lower().replace(' ', '_')}"
                    if st.checkbox(status_name, key=widget_key):
                        selected_wc.append(status_name)

            with filter_header_cols[2]:
                st.markdown("**03 · Live Status**")
                for status_name in live_options:
                    widget_key = f"log_live_status_v{filter_version}_{status_name.lower().replace(' ', '_')}"
                    if st.checkbox(status_name, key=widget_key):
                        selected_live.append(status_name)

        # Start from the date/month filtered log produced above.
        recent_log = recent_log.sort_values(by="Date_Parsed", ascending=False)

        # Apply the hierarchy to the currently visible rows only.
        if selected_quality or selected_wc or selected_live:
            stage_mask = pd.Series(True, index=log_filter_source.index)

            if selected_quality:
                stage_mask &= log_filter_source["Q_Filter_Status"].isin(selected_quality)
            if selected_wc:
                stage_mask &= log_filter_source["WC_Filter_Status"].isin(selected_wc)
            if selected_live:
                stage_mask &= log_filter_source["P_Filter_Status"].isin(selected_live)

            recent_log = recent_log.loc[stage_mask.loc[recent_log.index]]

        if log_search.strip():
            searchable_cols = pick_existing(
                recent_log,
                [
                    "Customer Name", "Verifier Name", "Agent Remarks", "CLI",
                    "Quality Status", "Quality Remarks", "Inbound Status", "Inbound Remarks", "Status",
                    "Welcome call Remarks", "LetterStatus",
                    "Provisioning Status", "Provisioning Remarks", "CallStatus",
                    "Portal Status", "Classification Review",
                    "Comments", "Voice of Customer", "Cancellation Reason",
                ],
            )
            if searchable_cols:
                search_blob = recent_log[searchable_cols].fillna("").astype(str).agg(" | ".join, axis=1)
                recent_log = recent_log[
                    search_blob.str.contains(
                        log_search.strip(), case=False, regex=False, na=False
                    )
                ]

        # Final display guarantee: keep both requested CRM inbound columns in the
        # filtered table even if the current selection contains legacy-only rows.
        # These are sourced from the exact headers in the CRM worksheet and passed
        # through normalize_api_records -> ag1 -> merged_log -> recent_log.
        for _required_inbound_col in ("Inbound Status", "Inbound Remarks"):
            if _required_inbound_col not in recent_log.columns:
                recent_log[_required_inbound_col] = ""
            recent_log[_required_inbound_col] = (
                recent_log[_required_inbound_col].fillna("").astype(str).map(str.strip)
            )

        # Always sort after applying the filters so the newest matching records remain first.
        recent_log = recent_log.sort_values(by="Date_Parsed", ascending=False)

        filter_summary = []
        if selected_quality:
            filter_summary.append("QA: " + ", ".join(selected_quality))
        if selected_wc:
            filter_summary.append("WC: " + ", ".join(selected_wc))
        if selected_live:
            filter_summary.append("Live: " + ", ".join(selected_live))
        if log_search.strip():
            filter_summary.append(f'Search: "{log_search.strip()}"')
        if filter_summary:
            st.caption(" • ".join(filter_summary) + f"  ·  {len(recent_log):,} matching record(s)")

        # Export the currently filtered application log without changing the table behaviour.
        export_valid_layout = [item for item in columns_layout if item[1] in recent_log.columns]
        export_cols = [item[1] for item in export_valid_layout]
        export_df = recent_log[export_cols].copy() if export_cols else recent_log.copy()
        export_csv = export_df.to_csv(index=False).encode("utf-8-sig")
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Applications")
        excel_buffer.seek(0)

        export_col1, export_col2 = st.columns([1, 1])
        with export_col1:
            st.download_button(
                "↓ CSV",
                data=export_csv,
                file_name=f"{agent}_applications.csv",
                mime="text/csv",
                use_container_width=True,
                key="export_log_csv",
            )
        with export_col2:
            st.download_button(
                "↓ Excel",
                data=excel_buffer.getvalue(),
                file_name=f"{agent}_applications.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="export_log_excel",
            )

        recent_log["S.No."] = range(1, len(recent_log) + 1)

        valid_layout = [item for item in columns_layout if item[1] in recent_log.columns]
        display_df = recent_log[[item[1] for item in valid_layout]].copy()
        display_df.columns = pd.MultiIndex.from_tuples(valid_layout)

        # Reset pagination when the visible dataset changes in size.
        if row_limit != "All":
            limit = int(row_limit)
            total_records = len(display_df)
            total_pages = max(1, math.ceil(total_records / limit))
            if st.session_state.current_page > total_pages:
                st.session_state.current_page = 1
            start_idx = (st.session_state.current_page - 1) * limit
            end_idx = min(start_idx + limit, total_records)
            display_df_page = display_df.iloc[start_idx:end_idx]
        else:
            total_records = len(display_df)
            total_pages = 1
            start_idx = 0
            end_idx = total_records
            display_df_page = display_df

        # Display cleanup: show a dash instead of missing/None-like values.
        # This is intentionally applied only to the visible table, so source
        # data and calculations remain unchanged.
        display_df_page = display_df_page.copy()
        for _col in display_df_page.columns:
            display_df_page[_col] = display_df_page[_col].apply(
                lambda _value: "-"
                if pd.isna(_value)
                or str(_value).strip().lower() in {"none", "nan", "nat", "null", ""}
                else _value
            )

        # Row/cell styling — CRM-aware status colouring.
        # Each status cell and its directly related remarks/detail cell share
        # the same colour. Other unrelated cells remain neutral.
        def style_log_row(row):
            styles = [""] * len(row)

            def get_val(col_name):
                for col in row.index:
                    if isinstance(col, tuple) and len(col) > 1 and col[1] == col_name:
                        return str(row[col]).strip().lower()
                return ""

            DARK_GREEN = "#065F46"
            DARK_AMBER = "#92400E"
            DARK_RED = "#991B1B"
            DARK_BLUE = "#1D4ED8"

            BG_GREEN = "rgba(16, 185, 129, 0.16)"
            BG_AMBER = "rgba(245, 158, 11, 0.18)"
            BG_RED = "rgba(239, 68, 68, 0.16)"
            BG_BLUE = "rgba(59, 130, 246, 0.10)"

            def status_style(value, kind):
                """Return one precise cell style for a CRM/legacy status value."""
                v = re.sub(r"\s+", " ", str(value or "").strip().lower())
                if not v:
                    return ""

                # ------------------------------ INBOUND ---------------------
                if kind == "inbound":
                    if any(x in v for x in ["cancel", "cancelled", "canceled", "reject", "rejected", "sop"]):
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"
                    if any(x in v for x in ["approved", "approve", "complete", "completed", "done", "pass"]):
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if any(x in v for x in ["pending", "followup", "follow-up", "follow up", "rework", "in progress"]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"

                # ----------------------------- QUALITY ----------------------
                if kind == "quality":
                    # Explicit CRM / legacy values requested:
                    # In-bound cancel, Quality Cancel and SOP are red.
                    if any(x in v for x in [
                        "in-bound cancel", "inbound cancel", "quality cancel",
                        "sop", "rejected", "reject", "cancelled", "canceled",
                    ]):
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"
                    if any(x in v for x in ["approved", "approve", "pass", "qa approved", "satisfied"]):
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if any(x in v for x in ["rework", "re-work", "followup", "follow up", "pending"]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"

                # ----------------------------- WELCOME ----------------------
                if kind == "welcome":
                    # Exact/common CRM values: Done = green, Cancel = red.
                    if any(x in v for x in [
                        "welcome approved", "welcome: approved", "approved", "welcome done",
                        "done", "completed", "complete", "pass", "satisfied",
                    ]):
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if any(x in v for x in [
                        "welcome followup", "welcome follow-up", "followup", "follow up",
                        "pending", "ringing", "chasing", "paperwork", "other work",
                    ]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if any(x in v for x in [
                        "welcome rejected", "rejected", "reject", "cancelled", "canceled",
                        "cancel",
                    ]):
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"

                # --------------------------- CONFIRMATION -------------------
                if kind == "confirmation":
                    if any(x in v for x in [
                        "confirmation approved", "approved", "confirmed", "satisfied",
                    ]):
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if any(x in v for x in [
                        "confirmation followup", "confirmation follow-up", "followup", "follow up",
                        "pending", "ringing", "chasing",
                    ]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if any(x in v for x in [
                        "confirmation rejected", "rejected", "reject", "cancelled", "canceled",
                        "to be cancelled", "to be canceled",
                    ]):
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"

                # -------------------------- PROVISIONING --------------------
                if kind == "provisioning":
                    # Explicit CRM values requested: Connectivity: Committed
                    # and Connectivity: Order Cancelled.
                    if "connectivity: order cancelled" in v or "connectivity: order canceled" in v:
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"
                    if "connectivity: committed" in v:
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if any(x in v for x in [
                        "provisioned", "provisioning complete", "order completed", "completed",
                        "processed", "confirmed", "connected", "live",
                    ]):
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if any(x in v for x in [
                        "pending", "followup", "follow-up", "delay", "delayed", "in progress",
                        "other work", "potential opportunity", "committed",
                    ]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if any(x in v for x in [
                        "order cancelled", "order canceled", "cancelled", "canceled", "rejected", "reject",
                    ]):
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"

                # ------------------------------ LETTER ----------------------
                if kind == "letter":
                    if any(x in v for x in ["letter sent", "mail sent", "dispatched", "dispatch approved", "sent"]):
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if any(x in v for x in ["pending", "followup", "follow-up", "re-sent", "resend"]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if any(x in v for x in ["cancelled", "canceled", "rejected", "reject"]):
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"

                # ------------------------------ LIVE ------------------------
                if kind == "portal":
                    # Missed / Delayed are operational attention statuses.
                    if any(x in v for x in ["missed", "delayed", "delay"]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if "live" in v:
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if any(x in v for x in ["committed", "pending", "followup", "follow-up"]):
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if any(x in v for x in ["rejected", "reject", "cancelled", "canceled", "to be cancelled"]):
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"

                if kind == "derived":
                    if v == "live":
                        return f"background-color:{BG_GREEN};color:{DARK_GREEN};font-weight:800;"
                    if v == "committed rem.":
                        return f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                    if v in {"committed cancelled", "live cancelled"}:
                        return f"background-color:{BG_RED};color:{DARK_RED};font-weight:800;"
                    if v == "unclassified / review":
                        return f"background-color:{BG_BLUE};color:{DARK_BLUE};font-weight:800;"

                return ""

            q_style = status_style(get_val("Quality Status"), "quality")
            inbound_style = status_style(get_val("Inbound Status"), "inbound")
            wc_style = status_style(get_val("Status"), "welcome")
            letter_style = status_style(get_val("LetterStatus"), "letter")
            prov_style = status_style(get_val("Provisioning Status"), "provisioning")
            call_style = status_style(get_val("CallStatus"), "confirmation")
            portal_style = status_style(get_val("Portal Status"), "portal")
            review_value = get_val("Classification Review")
            review_style = (
                f"background-color:{BG_AMBER};color:{DARK_AMBER};font-weight:800;"
                if review_value and review_value not in {"-", "none", "nan", "nat", "null"}
                else ""
            )

            for i, col_tuple in enumerate(row.index):
                col = col_tuple[1] if isinstance(col_tuple, tuple) and len(col_tuple) > 1 else str(col_tuple)
                current_style = ""

                # Status + its directly related detail/remarks cell use the
                # same colour, so the row's status context is immediately clear.
                # The status cell remains the primary source of the colour.
                style_by_col = {
                    "Quality Status": q_style,
                    "Quality Remarks": q_style,
                    "Inbound Status": inbound_style,
                    "Inbound Remarks": inbound_style,
                    "Status": wc_style,
                    "Welcome call Remarks": wc_style,
                    "LetterStatus": letter_style,
                    "Provisioning Status": prov_style,
                    "Provisioning Remarks": prov_style,
                    "CallStatus": call_style,
                    "Comments": call_style,
                    "Portal Status": portal_style,
                    "Classification Review": review_style,
                }
                current_style = style_by_col.get(col, "")

                # Keep the established separators/layout accents.
                if col == "S.No.":
                    current_style += "border-left:3px solid #2563EB;"
                if col in [
                    "Customer Name",
                    "Quality Remarks",
                    "Inbound Remarks",
                    "Welcome call Remarks",
                    "Provisioning Remarks",
                    "Cancellation Reason",
                ]:
                    current_style += "border-right:3px solid #E2E8F0;"

                styles[i] = current_style

            return styles

        styled_log = display_df_page.style.apply(style_log_row, axis=1)
        st.dataframe(
            styled_log,
            use_container_width=True,
            hide_index=True,
            height=545,
        )

        # Pagination controls
        if row_limit != "All" and total_pages > 1:
            st.write("")
            pag_col1, pag_col2, pag_col3 = st.columns([1.5, 1.0, 1.5])
            with pag_col1:
                st.html(
                    f'<div style="color:#64748B;font-size:.72rem;padding-top:9px;">Showing <b>{start_idx + 1}</b>–<b>{end_idx}</b> of <b>{total_records}</b> entries</div>'
                )
            with pag_col2:
                st.html(
                    f'<div style="color:#64748B;font-size:.72rem;text-align:center;padding-top:9px;">Page <b>{st.session_state.current_page}</b> of <b>{total_pages}</b></div>'
                )
            with pag_col3:
                p1, p2 = st.columns(2)
                with p1:
                    if st.button(
                        "← Prev",
                        disabled=(st.session_state.current_page == 1),
                        use_container_width=True,
                        key="prev_pg_action",
                    ):
                        st.session_state.current_page -= 1
                        st.rerun()
                with p2:
                    if st.button(
                        "Next →",
                        disabled=(st.session_state.current_page == total_pages),
                        use_container_width=True,
                        key="next_pg_action",
                    ):
                        st.session_state.current_page += 1
                        st.rerun()
    else:
        st.info("No applications are available for this agent.")

    # ------------------------------------------------------------------------
    # PERFORMANCE TIPS — ORIGINAL CONTENT RETAINED
    # ------------------------------------------------------------------------
    st.divider()
    render_section("Disposition & data quality guidance", "!", "Reference guidance for accurate call outcomes")
    st.html(
        """
        <div class="tips-box">
            <div class="tips-title">💡 Performance Tips: Correct Call Dispositions and Data Quality</div>
            <ul class="tips-list">
                <li><b>Answering Machines:</b> Do not dispose active customer connections as an "Answering Machine" especially if the Customer Talk Time/connectivity exceeds 30 seconds. Use it primarily when you hear a pre-recorded Answering Machine/Voicemail message.</li>
                <li><b>Customer Hangup:</b> This disposition should be used when the customer abruptly hangsup. Should be used for active/connected customers.</li>
                <li><b>No Answer:</b> Dispose as "No Answer" only if the customer does not pick up the call.</li>
                <li><b>Sky TV packages/Virgin:</b> Any call which indicates an error on the Talk-Talk portal, should be disposed as "Sky TV packages" or "Virgin". They must not be disposed as Answering Machines, Customer Hangup, No Answer, Not Interested etc. These dispositions would reappear in the dialler, and would dilute the quality of the data severely as the probability of the application of these customers is pretty low.</li>
                <li><b>Wrong Number:</b> Dispose them as "Wrong Number" if there is a mismatch in the data on the dialler and the data provided by the customer.</li>
                <li><b>Family Interference/POA:</b> Dispose as Family Interference/POA, if a family member or a 3rd person takes care of the customer's finances or other decisions.</li>
                <li><b>Dementia:</b> Dispose as Dementia, if the customer seems to have Dementia (seems forgetful of basic details), or seems Vulnerable.</li>
                <li><b>Over Age:</b> Dispose as Over Age if the customer is over 85 years old, or was born before 1940.</li>
                <li><b>Mobile Number:</b> Any number beginning with "7" should be disposed as a Mobile Number.</li>
                <li><b>Social Alarm VOIP:</b> If a customer has a Social Alarm/Medical Alarm/Careline/Lifeline etc, then use the disposition "Social Alarm VOIP".</li>
                <li><b>Hang up on bank details:</b> Use this disposition if the customer disconnects when hearing of or attempting any financial details.</li>
                <li><b>Busy:</b> If the customer is busy.</li>
                <br>
                <li><b>🚫 Dispositions that WILL NOT reappear in the dialler (if processed correctly):</b>
                    <ul>
                        <li>Dementia</li>
                        <li>Family Interference / POA</li>
                        <li>Sky TV Packages / Virgin</li>
                        <li>Over Age</li>
                    </ul>
                </li>
                <br>
                <li><b>🔄 Dispositions that WILL reappear frequently on the dialler:</b>
                    <ul>
                        <li>Answering Machine</li>
                        <li>Customer Hangup</li>
                        <li>Interested</li>
                        <li>Callback</li>
                    </ul>
                </li>
                <br>
                <li><u><b>Data Accuracy and Quality: The more accurate the disposition you enter, the better quality of the data would appear on the dialler for the entire team.</b></u></li>
            </ul>
        </div>
        """,
    )

    st.html(
        '<div class="footer-note">Sparta Agent Portal • Legacy records through 17-Sep-2026 remain sourced from Sparta/Sparta2; records from 18-Sep-2026 onward are sourced from the CRM mirror.</div>',
    )

except Exception as e:
    st.error(f"Error: {e}")
