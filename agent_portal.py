import streamlit as st
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

# ============================================================================
# SPARTA AGENT PORTAL — PREMIUM UI REFRESH
# Existing functionality retained:
# - Agent access-key authentication
# - Login logging to Google Sheets / Logs
# - Sparta + Sparta2 Google Sheet data
# - 5-minute data cache
# - Start/end date filtering
# - Quality / Welcome Call / Live KPIs
# - Insight flags
# - Daily / Monthly breakdowns
# - Trend chart
# - Sales activity calendar
# - Recent applications log with filters + pagination
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
        padding-top: 1.0rem;
        padding-bottom: 1.8rem;
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
        margin: 2px 0 7px 0;
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
        margin: -3px 0 9px 43px;
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
        margin-bottom: 4px;
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
        margin-top: 6px;
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
        margin: 14px 0 16px;
        padding: 12px 15px 2px;
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
        min-height: 91px;
        padding: 11px 7px 10px;
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
        margin-bottom: 4px;
        text-transform: uppercase;
        letter-spacing: .55px;
    }

    .kpi-value {
        font-size: 1.25rem;
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
        margin-top: 6px;
        background: #EAF1FF;
        display: inline-block;
        padding: 3px 7px;
        border-radius: 99px;
    }

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
        padding: 18px 19px;
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
        margin-top: 6px;
        color: #64748B;
        font-size: .70rem;
        line-height: 1.4;
        max-width: 92%;
    }

    /* --------------------------- FUNNEL --------------------------------- */
    .funnel-shell {
        padding: 16px 17px;
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
        margin: 10px 0;
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
        min-height: 84px;
        padding: 10px 12px;
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
        font-size: 1.06rem;
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
        font-size: .60rem;
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
        padding: 10px 11px;
        border-radius: 12px;
        background: rgba(255,255,255,.92);
        border: 1px solid #E2E8F0;
    }

    .mini-stat-label {
        color: #64748B;
        font-size: .60rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .65px;
    }

    .mini-stat-value {
        color: #0F172A;
        font-size: 1.06rem;
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
        padding: 12px;
        box-shadow: 0 7px 20px rgba(15,23,42,.035);
    }

    .pulse-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 9px;
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
        margin: 10px 0;
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
SPREADSHEET_ID = "1R1nXJHnmsHQhisEDronG-DMo5tWeI3Ysh8TyQmKQ2fQ"

ACCESS_KEYS = st.secrets["agent_keys"]

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


def robust_date_parser(date_str):
    date_str = str(date_str).strip()
    try:
        if "/" in date_str:
            return pd.to_datetime(date_str, dayfirst=True)
        return pd.to_datetime(date_str)
    except Exception:
        return pd.NaT


@st.cache_data(ttl=300, show_spinner=False)
def fetch_data():
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

    df1 = pd.DataFrame(ss.worksheet("Sparta").get_all_records())
    df1["Date_Parsed"] = pd.to_datetime(df1["Standardized_Date"], errors="coerce")
    df1["Advisor"] = df1["Advisor"].astype(str).str.strip().str.title()

    df2_raw = pd.DataFrame(ss.worksheet("Sparta2").get_all_records())
    df2_raw["Date_Parsed"] = df2_raw["Sale Date"].apply(robust_date_parser)
    df2_raw["Advisor"] = df2_raw["Agent"].astype(str).str.strip().str.title()

    try:
        meta = ss.worksheet("Meta").get_all_values()
        last_sync = meta[0][1]
    except Exception:
        last_sync = "Unknown"

    return df1, df2_raw, last_sync


def map_quality(val):
    s = str(val).lower()
    if any(x in s for x in ["appr", "pass"]):
        return "Approved"
    if any(x in s for x in ["rew", "repro"]):
        return "Rework"
    if any(x in s for x in ["can"]):
        return "Cancelled"
    if any(x in s for x in ["rej"]):
        return "Rejected"
    return "Others"


def map_portal(val):
    s = str(val).lower()
    if "live" in s:
        return "Live"
    if "com" in s:
        return "Committed"
    if any(x in s for x in ["can", "rej"]):
        return "Cancelled"
    return "Others"


def map_wc(val):
    s = str(val).lower().strip()
    if any(x in s for x in ["done", "pass", "comp"]):
        return "Done"
    if any(x in s for x in ["pend", "pnd"]):
        return "Pending"
    if any(x in s for x in ["paper", "ppw"]):
        return "Paperwork"
    if any(x in s for x in ["can", "rej"]):
        return "Cancelled"
    return "Others"


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


def render_kpi(label, value, total):
    lbl = str(label).lower()
    accent = "#94A3B8"

    if "total" in lbl:
        accent = "#3B82F6"
    elif any(x in lbl for x in ["appr", "done", "live"]):
        accent = "#10B981"
    elif any(x in lbl for x in ["rew", "pend", "paper", "comm"]):
        accent = "#F59E0B"
    elif "can" in lbl or "rej" in lbl:
        accent = "#EF4444"

    percent = (value / total * 100) if total > 0 else 0
    pc_html = (
        f'<div><span class="kpi-pc">{percent:.1f}%</span></div>'
        if "total apps" not in lbl
        else ""
    )

    st.html(
        f"""
        <div class="kpi-card" style="border-top:4px solid {accent};">
            <p class="kpi-label">{escape(str(label))}</p>
            <p class="kpi-value">{value:,}</p>
            {pc_html}
        </div>
        """
    )


def kpi_panel(title, kpis):
    active = [x for x in kpis if x[1] > 0]
    if not active:
        return

    with st.container(border=True):
        st.markdown(f"**{escape(title)}**")
        cols = st.columns(len(active))
        for i, kpi in enumerate(active):
            with cols[i]:
                render_kpi(kpi[0], kpi[1], kpi[2])


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
    live = len(portal_df[portal_df["P_Status"] == "Live"]) if not portal_df.empty else 0
    committed = len(portal_df[portal_df["P_Status"] == "Committed"]) if not portal_df.empty else 0

    stages = [
        ("Applications", total, "#3B82F6"),
        ("Quality", quality_approved, "#10B981"),
        ("Welcome", wc_done, "#06B6D4"),
        ("Live", live, "#047857"),
    ]

    return stages, committed


def add_date_strings(frame, source_col, output_col):
    frame = frame.copy()
    if source_col in frame.columns:
        frame[output_col] = pd.to_datetime(frame[source_col], errors="coerce").dt.strftime("%d-%m-%Y").fillna("")
    return frame


def pick_existing(frame, candidates):
    return [c for c in candidates if c in frame.columns]


def summary_for_period(base_apps, base_portal, start_date, end_date, welcome_col):
    apps = base_apps[(base_apps["Date_Parsed"].dt.date >= start_date) & (base_apps["Date_Parsed"].dt.date <= end_date)].copy()
    portal = base_portal[(base_portal["Date_Parsed"].dt.date >= start_date) & (base_portal["Date_Parsed"].dt.date <= end_date)].copy()

    if "Quality Status" in apps.columns:
        apps["Q_Status"] = apps["Quality Status"].apply(map_quality)
    else:
        apps["Q_Status"] = "Others"

    if "Status" in portal.columns:
        portal["P_Status"] = portal["Status"].apply(map_portal)
    else:
        portal["P_Status"] = "Others"

    total_apps = len(apps)
    total_portal = len(portal)
    approved = len(apps[apps["Q_Status"] == "Approved"])

    wc_done = 0
    if welcome_col and welcome_col in apps.columns:
        apps["WC_Clean"] = apps[welcome_col].apply(map_wc)
        wc_done = len(apps[apps["WC_Clean"] == "Done"])

    live = len(portal[portal["P_Status"] == "Live"])
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
    df1, df2_raw, last_sync = fetch_data()
    ag1 = df1[df1["Advisor"] == agent].copy()
    ag2 = df2_raw[df2_raw["Advisor"] == agent].copy()

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
                <div style="font-size:.82rem;font-weight:800;margin-top:3px;"><span class="live-dot"></span>Connected</div>
                <div class="hero-sync" style="text-align:left;padding-top:7px;">
                    Last synced<br><strong>{escape(str(last_sync))}</strong>
                </div>
            </div>
            """,
        )

    # ------------------------------------------------------------------------
    # GLOBAL DATE FILTER
    # ------------------------------------------------------------------------
    with st.container(border=True):
        filter_icon, date_col1, date_col2, spacer = st.columns([0.42, 1.2, 1.2, 2.1])

        with filter_icon:
            st.markdown("### 🗓️")

        with date_col1:
            st.caption("START DATE")
            start_date = st.date_input(
                "Start Date",
                today_date.replace(day=1),
                label_visibility="collapsed",
                key="main_start_date",
            )

        with date_col2:
            st.caption("END DATE")
            end_date = st.date_input(
                "End Date",
                today_date,
                label_visibility="collapsed",
                key="main_end_date",
            )


    # Protect against a reversed user-selected range without altering the source data.
    if start_date > end_date:
        st.warning("Start Date is after End Date. Please select a valid date range.")
        st.stop()

    ag1_filtered = ag1[
        (ag1["Date_Parsed"].dt.date >= start_date)
        & (ag1["Date_Parsed"].dt.date <= end_date)
    ].copy()
    ag2_filtered = ag2[
        (ag2["Date_Parsed"].dt.date >= start_date)
        & (ag2["Date_Parsed"].dt.date <= end_date)
    ].copy()

    ag1_filtered["Q_Status"] = ag1_filtered["Quality Status"].apply(map_quality)
    ag2_filtered["P_Status"] = ag2_filtered["Status"].apply(map_portal)

    wc_col = (
        "Status"
        if "Status" in ag1_filtered.columns
        else "Welcome call Status"
        if "Welcome call Status" in ag1_filtered.columns
        else None
    )
    if wc_col:
        ag1_filtered["WC_Clean"] = ag1_filtered[wc_col].apply(map_wc)

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

    live_total_denominator = total_ag2 if total_ag2 > 0 else total_apps
    group_4 = [
        ("Live", len(ag2_filtered[ag2_filtered["P_Status"] == "Live"]), live_total_denominator),
        ("Committed", len(ag2_filtered[ag2_filtered["P_Status"] == "Committed"]), live_total_denominator),
        ("Cancelled", len(ag2_filtered[ag2_filtered["P_Status"] == "Cancelled"]), live_total_denominator),
        ("Others", len(ag2_filtered[ag2_filtered["P_Status"] == "Others"]), live_total_denominator),
    ]

    render_section("Performance snapshot", "✦", "Your selected date range at a glance")

    b1, b2, b3, b4 = st.columns([1.15, 2.6, 2.6, 2.35], gap="small")
    with b1:
        with st.container(border=True):
            st.markdown("**Overview**")
            render_kpi(group_1[0][0], group_1[0][1], group_1[0][2])
    with b2:
        kpi_panel("Quality audit status", group_2)
    with b3:
        kpi_panel("Welcome call status", group_3)
    with b4:
        kpi_panel("Live status", group_4)

    # ========================================================================
    # ACTION CENTRE — CANCELLATION FIRST
    # ========================================================================
    quality_cancel_count = len(ag1_filtered[ag1_filtered["Q_Status"] == "Cancelled"])
    wc_cancel_count = 0
    if wc_col and "WC_Clean" in ag1_filtered.columns:
        wc_cancel_count = len(ag1_filtered[ag1_filtered["WC_Clean"] == "Cancelled"])
    live_cancel_count = len(ag2_filtered[ag2_filtered["P_Status"] == "Cancelled"]) if not ag2_filtered.empty else 0
    total_cancel_count = quality_cancel_count + wc_cancel_count + live_cancel_count

    st.divider()
    render_section(
        "Action centre",
        "⚡",
        "Cancellation-focused queues highlighting records that need attention in the selected period",
    )

    action_items = [
        ("Quality cancellations", quality_cancel_count, "!", "#FEF2F2", "#B91C1C", "Review cancelled applications and the associated Quality Remarks for recurring loss points."),
        ("Welcome call cancellations", wc_cancel_count, "☎", "#FFF7ED", "#C2410C", "Review Welcome Call cancellations and remarks to identify avoidable customer drop-offs."),
        ("Live-stage cancellations", live_cancel_count, "×", "#FEF2F2", "#991B1B", "Review final-stage cancellations, customer feedback and cancellation reasons."),
    ]

    action_html = []
    for title, count, icon, bg, fg, copy in action_items:
        action_html.append(
            f"""
            <div class="action-card">
                <div class="action-top">
                    <div class="action-icon" style="background:{bg};color:{fg};">{icon}</div>
                    <div class="action-label">{escape(title)}</div>
                </div>
                <div class="action-count">{count:,}</div>
                <div class="action-copy">{escape(copy)}</div>
            </div>
            """
        )
    st.html('<div class="action-wrap">' + ''.join(action_html) + '</div>')

    st.caption(f"Total cancellation records across the three tracked stages in this period: {total_cancel_count:,}")

    with st.expander("Open cancellation queues", expanded=False):
        aq1, aq2, aq3 = st.tabs(["Quality cancellations", "Welcome cancellations", "Live-stage cancellations"])

        with aq1:
            quality_cancel_df = ag1_filtered[ag1_filtered["Q_Status"] == "Cancelled"].copy()
            if not quality_cancel_df.empty:
                quality_cancel_df = add_date_strings(quality_cancel_df, "Standardized_Date", "Sale Date")
                cols = pick_existing(
                    quality_cancel_df,
                    ["Sale Date", "Customer Name", "CLI", "Quality Status", "Quality Remarks"],
                )
                st.dataframe(quality_cancel_df[cols], use_container_width=True, hide_index=True, height=260)
            else:
                st.success("No Quality Cancellation applications in the selected period.")

        with aq2:
            if wc_col:
                wc_cancel_df = ag1_filtered[ag1_filtered["WC_Clean"] == "Cancelled"].copy()
                if not wc_cancel_df.empty:
                    wc_cancel_df = add_date_strings(wc_cancel_df, "Standardized_Date", "Sale Date")
                    cols = pick_existing(
                        wc_cancel_df,
                        ["Sale Date", "Customer Name", "CLI", wc_col, "Welcome call Remarks"],
                    )
                    st.dataframe(wc_cancel_df[cols], use_container_width=True, hide_index=True, height=260)
                else:
                    st.success("No Welcome Call Cancellation applications in the selected period.")
            else:
                st.info("Welcome Call status is not available in the current source data.")

        with aq3:
            live_cancel_df = ag2_filtered[ag2_filtered["P_Status"] == "Cancelled"].copy()
            if not live_cancel_df.empty:
                live_cancel_df = add_date_strings(live_cancel_df, "Sale Date", "Sale Date")
                cols = pick_existing(
                    live_cancel_df,
                    [
                        "Sale Date",
                        "Customer Name",
                        "Telephone No.",
                        "Portal Status",
                        "Cancellation Reason",
                        "Comments",
                        "Voice of Customer",
                    ],
                )
                st.dataframe(live_cancel_df[cols], use_container_width=True, hide_index=True, height=260)
            else:
                st.success("No Live-stage Cancellation applications in the selected period.")

    # ========================================================================
    # PIPELINE SNAPSHOT + PERFORMANCE PULSE
    # ========================================================================
    st.divider()
    funnel_col, pulse_col = st.columns([1.0, 2.0], gap="medium")

    with funnel_col:
        render_section(
            "Pipeline snapshot",
            "◎",
            "Four true stages. Committed remains alongside Live and is not treated as a fifth stage.",
        )
        stages, committed_count = stage_snapshot(ag1_filtered, ag2_filtered, wc_col)
        total_for_funnel = max(total_apps, 1)
        funnel_rows = []
        for name, count, color in stages:
            width = min(max(pct(count, total_for_funnel), 0), 100)
            companion = ""
            if name == "Live":
                companion = f'<div class="funnel-companion">Committed: {committed_count:,}</div>'
            funnel_rows.append(
                f"""
                <div class="funnel-row">
                    <div class="funnel-name">
                        {escape(name)}
                        {companion}
                    </div>
                    <div class="funnel-track">
                        <div class="funnel-fill" style="width:{width:.1f}%;background:{color};"></div>
                    </div>
                    <div class="funnel-value">{count:,} · {width:.1f}%</div>
                </div>
                """
            )
        st.html(
            '<div class="funnel-shell">'
            '<div class="funnel-note">'
            'Selected-period stage snapshot: Quality = Approved, Welcome = Done, Live = Live. '
            'Committed is companion information only.'
            '</div>'
            + ''.join(funnel_rows)
            + '</div>'
        )

    with pulse_col:
        period_days = (end_date - start_date).days + 1
        prev_start = start_date - datetime.timedelta(days=period_days)
        prev_end = start_date - datetime.timedelta(days=1)

        current_summary = {
            "apps": total_apps,
            "approval_rate": pct(len(ag1_filtered[ag1_filtered["Q_Status"] == "Approved"]), total_apps),
            "wc_done_rate": pct(
                len(ag1_filtered[ag1_filtered["WC_Clean"] == "Done"])
                if wc_col and "WC_Clean" in ag1_filtered.columns else 0,
                total_apps,
            ),
            "live_rate": pct(
                len(ag2_filtered[ag2_filtered["P_Status"] == "Live"]),
                total_ag2 if total_ag2 > 0 else total_apps,
            ),
        }
        previous_summary = summary_for_period(ag1, ag2, prev_start, prev_end, wc_col)

        # Working-day / activity calculations.
        def portal_is_holiday(dt):
            wd = dt.weekday()
            if wd == 6:
                return True
            if wd == 5:
                week_num = (dt.day - 1) // 7 + 1
                return week_num in [1, 3, 5]
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
            f"""
            <div class="pulse-shell">
                <div class="pulse-head">
                    <div class="pulse-title">Performance pulse</div>
                    <div class="pulse-note">
                        Selected period: {escape(start_date.strftime('%d %b'))} – {escape(end_date.strftime('%d %b %Y'))}
                    </div>
                </div>
                <div class="pulse-subtitle"><span></span>Period momentum</div>
            </div>
            """
        )

        render_comparison_cards(
            [
                ("Applications", current_summary["apps"], previous_summary["apps"], False, f"Previous: {previous_summary['apps']:,}"),
                ("QA approval", current_summary["approval_rate"], previous_summary["approval_rate"], True, f"Previous: {previous_summary['approval_rate']:.1f}%"),
                ("WC completion", current_summary["wc_done_rate"], previous_summary["wc_done_rate"], True, f"Previous: {previous_summary['wc_done_rate']:.1f}%"),
                ("Live rate", current_summary["live_rate"], previous_summary["live_rate"], True, f"Previous: {previous_summary['live_rate']:.1f}%"),
            ]
        )

        st.html(
            """
            <div class="pulse-separator"></div>
            <div class="pulse-subtitle"><span></span>Activity consistency</div>
            """
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

        if len(working_days) > 0 and zero_sales_days > 0:
            st.caption(f"{zero_sales_days} working day(s) had no applications in the selected period.")

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
        l_live = len(ag2_filtered[ag2_filtered["P_Status"] == "Live"]) / total_ag2
        l_can = len(ag2_filtered[ag2_filtered["P_Status"] == "Cancelled"]) / total_ag2
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
    # DATA BREAKDOWN
    # ------------------------------------------------------------------------
    st.html('<div style="height:6px"></div>')
    render_section("Data breakdown", "▦", "Daily or monthly view of your application funnel")

    ag1_filtered["Date"] = ag1_filtered["Date_Parsed"].dt.date
    ag2_filtered["Date"] = ag2_filtered["Date_Parsed"].dt.date

    view_mode = st.radio(
        "View tables by:",
        ["Daily", "Monthly"],
        horizontal=True,
        label_visibility="collapsed",
        key="breakdown_view_mode",
    )

    if view_mode == "Daily":
        ag1_filtered["Period"] = ag1_filtered["Date_Parsed"].dt.date
        ag2_filtered["Period"] = ag2_filtered["Date_Parsed"].dt.date
        chart_group_col = "Date"
    else:
        ag1_filtered["Period"] = ag1_filtered["Date_Parsed"].dt.strftime("%Y-%m")
        ag2_filtered["Period"] = ag2_filtered["Date_Parsed"].dt.strftime("%Y-%m")
        chart_group_col = "Period"

    ca, cb, cc, cd = st.columns(4, gap="small")

    with ca:
        render_section("Applications", "01")
        if not ag1_filtered.empty:
            period_apps = ag1_filtered.groupby("Period").size().to_frame("Total Apps")
            vmax_apps = max(period_apps.max().max(), 1.1)
            styled_apps = (
                period_apps.style
                .format(lambda x: "-" if x == 0 else x)
                .background_gradient(cmap="Greens", vmin=1, vmax=vmax_apps)
                .map(lambda x: "background-color: transparent" if x == 0 else "")
            )
            st.dataframe(styled_apps, use_container_width=True, height=370)

    with cb:
        render_section("Quality audit", "02")
        if not ag1_filtered.empty:
            period_qual = ag1_filtered.groupby(["Period", "Q_Status"]).size().unstack(fill_value=0)
            qual_order = ["Approved", "Rework", "Cancelled", "Rejected", "Others"]
            period_qual = period_qual.reindex(columns=qual_order, fill_value=0)
            period_qual = period_qual.loc[:, (period_qual != 0).any(axis=0)]
            if not period_qual.empty:
                vmax_qual = max(period_qual.max().max(), 1.1)
                styled_qual = (
                    period_qual.style
                    .format(lambda x: "-" if x == 0 else x)
                    .background_gradient(cmap="Greens", subset=pd.IndexSlice[:, period_qual.columns.intersection(["Approved"])], vmin=1, vmax=vmax_qual)
                    .background_gradient(cmap="Wistia", subset=pd.IndexSlice[:, period_qual.columns.intersection(["Rework"])], vmin=1, vmax=vmax_qual)
                    .background_gradient(cmap="Reds", subset=pd.IndexSlice[:, period_qual.columns.intersection(["Cancelled", "Rejected"])], vmin=1, vmax=vmax_qual)
                    .map(lambda x: "background-color: transparent" if x == 0 else "")
                )
                st.dataframe(styled_qual, use_container_width=True, height=370)

    with cc:
        render_section("Welcome call", "03")
        if wc_col and not ag1_filtered.empty:
            period_wc = ag1_filtered.groupby(["Period", "WC_Clean"]).size().unstack(fill_value=0)
            wc_order = ["Done", "Pending", "Paperwork", "Cancelled", "Others"]
            period_wc = period_wc.reindex(columns=wc_order, fill_value=0)
            period_wc = period_wc.loc[:, (period_wc != 0).any(axis=0)]
            if not period_wc.empty:
                vmax_wc = max(period_wc.max().max(), 1.1)
                styled_wc = (
                    period_wc.style
                    .format(lambda x: "-" if x == 0 else x)
                    .background_gradient(cmap="Greens", subset=pd.IndexSlice[:, period_wc.columns.intersection(["Done"])], vmin=1, vmax=vmax_wc)
                    .background_gradient(cmap="Wistia", subset=pd.IndexSlice[:, period_wc.columns.intersection(["Pending", "Paperwork"])], vmin=1, vmax=vmax_wc)
                    .background_gradient(cmap="Reds", subset=pd.IndexSlice[:, period_wc.columns.intersection(["Cancelled"])], vmin=1, vmax=vmax_wc)
                    .map(lambda x: "background-color: transparent" if x == 0 else "")
                )
                st.dataframe(styled_wc, use_container_width=True, height=370)
        else:
            st.info("No Welcome Call data.")

    with cd:
        render_section("Live status", "04")
        if not ag2_filtered.empty:
            period_port = ag2_filtered.groupby(["Period", "P_Status"]).size().unstack(fill_value=0)
            port_order = ["Live", "Committed", "Cancelled", "Others"]
            period_port = period_port.reindex(columns=port_order, fill_value=0)
            period_port = period_port.loc[:, (period_port != 0).any(axis=0)]
            if not period_port.empty:
                vmax_port = max(period_port.max().max(), 1.1)
                styled_port = (
                    period_port.style
                    .format(lambda x: "-" if x == 0 else x)
                    .background_gradient(cmap="Greens", subset=pd.IndexSlice[:, period_port.columns.intersection(["Live"])], vmin=1, vmax=vmax_port)
                    .background_gradient(cmap="Wistia", subset=pd.IndexSlice[:, period_port.columns.intersection(["Committed"])], vmin=1, vmax=vmax_port)
                    .background_gradient(cmap="Reds", subset=pd.IndexSlice[:, period_port.columns.intersection(["Cancelled"])], vmin=1, vmax=vmax_port)
                    .map(lambda x: "background-color: transparent" if x == 0 else "")
                )
                st.dataframe(styled_port, use_container_width=True, height=370)

    # ------------------------------------------------------------------------
    # TREND + CALENDAR
    # ------------------------------------------------------------------------
    st.html('<div style="height:8px"></div>')
    col_trend, col_cal = st.columns([3, 2], gap="large")

    with col_trend:
        render_section("My trend", "↗", "Applications compared with Quality Approved and Live")
        if not ag1_filtered.empty:
            d_apps = ag1_filtered.groupby(chart_group_col).size().to_frame("Total Apps")
            d_appr = (
                ag1_filtered[ag1_filtered["Q_Status"] == "Approved"]
                .groupby(chart_group_col)
                .size()
                .to_frame("Approved")
            )
            d_live = (
                ag2_filtered[ag2_filtered["P_Status"] == "Live"]
                .groupby(chart_group_col)
                .size()
                .to_frame("Live")
            )

            i_comb = d_apps.join([d_appr, d_live], how="left").fillna(0).reset_index()
            i_comb[chart_group_col] = i_comb[chart_group_col].astype(str)

            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=i_comb[chart_group_col],
                    y=i_comb["Total Apps"],
                    name="Total Applications",
                    marker_color="#93C5FD",
                    marker_line_width=0,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=i_comb[chart_group_col],
                    y=i_comb["Approved"],
                    name="Quality Approved Applications",
                    mode="lines+markers",
                    line=dict(color="#10B981", width=3),
                    marker=dict(size=7),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=i_comb[chart_group_col],
                    y=i_comb["Live"],
                    name="Live Applications",
                    mode="lines+markers",
                    line=dict(color="#F59E0B", width=3),
                    marker=dict(size=7),
                )
            )
            fig.update_layout(
                height=365,
                hovermode="x unified",
                margin=dict(l=8, r=8, t=22, b=8),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(255,255,255,.72)",
                font=dict(color="#475569", size=11),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(
                    title="Date" if view_mode == "Daily" else "Month",
                    showgrid=False,
                    zeroline=False,
                    linecolor="#E2E8F0",
                ),
                yaxis=dict(
                    title="Applications",
                    gridcolor="#E7EDF5",
                    zeroline=False,
                ),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No application data for the selected date range.")

    with col_cal:
        render_section("Sales activity calendar", "▦", "Daily sales activity with working-day / holiday context")

        def is_holiday(dt):
            wd = dt.weekday()  # 0=Mon, 6=Sun
            if wd == 6:
                return True
            if wd == 5:
                week_num = (dt.day - 1) // 7 + 1
                return week_num in [1, 3, 5]
            return False

        c_month_col, c_year_col = st.columns(2)
        with c_month_col:
            sel_month = st.selectbox(
                "Month",
                list(calendar.month_name)[1:],
                index=today_date.month - 1,
                key="calendar_month",
            )
        with c_year_col:
            sel_year = st.selectbox(
                "Year",
                [2025, 2026],
                index=1,
                key="calendar_year",
            )

        m_idx = list(calendar.month_name).index(sel_month)
        num_days = calendar.monthrange(sel_year, m_idx)[1]
        dates = [datetime.date(sel_year, m_idx, day) for day in range(1, num_days + 1)]

        daily_sales = ag1.groupby(ag1["Date_Parsed"].dt.date).size()
        cal_df = pd.DataFrame(
            {
                "Date": dates,
                "Day": [d.day for d in dates],
                "Weekday": [d.strftime("%a") for d in dates],
                "WeekNum": [int(d.strftime("%V")) if d.strftime("%V").isdigit() else 0 for d in dates],
                "Sales": [daily_sales.get(d, 0) for d in dates],
                "Type": ["Holiday" if is_holiday(d) else "Working" for d in dates],
            }
        )
        cal_df["HoverText"] = cal_df.apply(
            lambda r: "Holiday" if r["Type"] == "Holiday" else f"{r['Sales']} sale(s)",
            axis=1,
        )

        fig_cal = go.Figure()
        working_days = cal_df[cal_df["Type"] == "Working"]
        fig_cal.add_trace(
            go.Heatmap(
                x=working_days["Weekday"],
                y=working_days["WeekNum"],
                z=working_days["Sales"],
                text=working_days["Day"],
                customdata=working_days["HoverText"],
                hovertemplate="%{customdata}<extra></extra>",
                texttemplate="%{text}",
                textfont=dict(color="#334155", size=11),
                colorscale=[[0, "#F8FAFC"], [0.1, "#D1FAE5"], [1, "#047857"]],
                showscale=False,
                xgap=3,
                ygap=3,
            )
        )

        holidays = cal_df[cal_df["Type"] == "Holiday"]
        fig_cal.add_trace(
            go.Scatter(
                x=holidays["Weekday"],
                y=holidays["WeekNum"],
                mode="markers+text",
                marker=dict(symbol="square", size=35, color="#DDEBFF", line=dict(color="#BFD7F7", width=1)),
                text=holidays["Day"],
                customdata=holidays["HoverText"],
                hovertemplate="%{customdata}<extra></extra>",
                textfont=dict(color="#64748B", size=11),
                showlegend=False,
            )
        )

        fig_cal.update_layout(
            height=325,
            margin=dict(l=0, r=0, t=2, b=4),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,.72)",
            xaxis=dict(
                side="top",
                categoryorder="array",
                categoryarray=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                showgrid=False,
                zeroline=False,
                fixedrange=True,
            ),
            yaxis=dict(
                autorange="reversed",
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                fixedrange=True,
            ),
        )
        st.plotly_chart(fig_cal, use_container_width=True, config={"displayModeBar": False})
        st.caption("🟢 Sales activity  •  ◻ No sales  •  🔵 Holiday")

    # ------------------------------------------------------------------------
    # RECENT APPLICATIONS LOG
    # ------------------------------------------------------------------------
    st.divider()
    render_section("Recent applications log", "⌕", "Detailed record-by-record view of your applications and downstream status")

    if not ag1.empty:
        ag2_clean = ag2.copy()
        ag2_clean["Telephone No."] = ag2_clean["Telephone No."].astype(str).str.strip()
        ag2_clean = ag2_clean.rename(columns={"Status": "Portal Status", "Committed Date": "Live Date"})
        ag2_unique = ag2_clean.sort_values("Date_Parsed").drop_duplicates("Telephone No.", keep="last")

        ag1_log_base = ag1.copy()
        ag1_log_base["CLI_Key"] = ag1_log_base["CLI"].astype(str).str.strip()
        merged_log = ag1_log_base.merge(
            ag2_unique[
                [
                    "Telephone No.",
                    "LetterStatus",
                    "CallStatus",
                    "Comments",
                    "Voice of Customer",
                    "Cancellation Reason",
                    "Portal Status",
                    "Live Date",
                ]
            ],
            left_on="CLI_Key",
            right_on="Telephone No.",
            how="left",
        )

        merged_log["Sale Date"] = (
            pd.to_datetime(merged_log["Standardized_Date"], errors="coerce")
            .dt.strftime("%d-%m-%Y")
            .fillna("")
        )
        merged_log["Live Date"] = (
            pd.to_datetime(merged_log["Live Date"], errors="coerce")
            .dt.strftime("%d-%m-%Y")
            .fillna("")
        )

        columns_layout = [
            ("Basic Info.", "S.No."),
            ("Basic Info.", "Sale Date"),
            ("Basic Info.", "Customer Name"),
            ("Quality Audit", "Quality Status"),
            ("Quality Audit", "Quality Remarks"),
            ("Welcome Call", "Status"),
            ("Welcome Call", "Welcome call Remarks"),
            ("Live Status", "LetterStatus"),
            ("Live Status", "CallStatus"),
            ("Live Status", "Portal Status"),
            ("Live Status", "Live Date"),
            ("Live Status", "Comments"),
            ("Live Status", "Voice of Customer"),
            ("Live Status", "Cancellation Reason"),
        ]

        # Custom log controls preserved from the original portal.
        log_col1, log_col2, log_col3 = st.columns([2.15, 2.45, 1])
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
                    (merged_log["Date_Parsed"].dt.date >= log_start)
                    & (merged_log["Date_Parsed"].dt.date <= log_end)
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

        # Row styling — same status meaning as the original portal, with a cleaner palette.
        def style_log_row(row):
            styles = [""] * len(row)

            def get_val(col_name):
                for col in row.index:
                    if col[1] == col_name:
                        return str(row[col]).lower()
                return ""

            DARK_GREEN = "#065F46"
            DARK_AMBER = "#92400E"
            DARK_RED = "#991B1B"

            BG_GREEN = "rgba(16, 185, 129, 0.16)"
            BG_AMBER = "rgba(245, 158, 11, 0.16)"
            BG_RED = "rgba(239, 68, 68, 0.16)"
            BG_BLUE = "rgba(59, 130, 246, 0.12)"

            q_val = get_val("Quality Status")
            q_bg, q_txt = "", ""
            if any(x in q_val for x in ["appr", "pass"]):
                q_bg, q_txt = BG_GREEN, DARK_GREEN
            elif any(x in q_val for x in ["rew", "repro"]):
                q_bg, q_txt = BG_AMBER, DARK_AMBER
            elif any(x in q_val for x in ["can", "rej"]):
                q_bg, q_txt = BG_RED, DARK_RED
            q_style = f"background-color: {q_bg}; color: {q_txt}; font-weight: 800;" if q_bg else ""

            wc_val = get_val("Status")
            wc_bg, wc_txt = "", ""
            if any(x in wc_val for x in ["done", "pass", "comp", "live"]):
                wc_bg, wc_txt = BG_GREEN, DARK_GREEN
            elif any(x in wc_val for x in ["pend", "pnd", "paper", "ppw", "com"]):
                wc_bg, wc_txt = BG_AMBER, DARK_AMBER
            elif any(x in wc_val for x in ["can", "rej"]):
                wc_bg, wc_txt = BG_RED, DARK_RED
            wc_style = f"background-color: {wc_bg}; color: {wc_txt}; font-weight: 800;" if wc_bg else ""

            call_val = get_val("CallStatus")
            c_bg, c_txt = "", ""
            if "satisfied" in call_val:
                c_bg, c_txt = BG_GREEN, DARK_GREEN
            elif any(x in call_val for x in ["pend", "cancel"]):
                c_bg, c_txt = BG_RED, DARK_RED
            c_style = f"background-color: {c_bg}; color: {c_txt}; font-weight: 800;" if c_bg else ""

            portal_val = get_val("Portal Status")
            p_bg, p_txt = "", ""
            if "live" in portal_val:
                p_bg, p_txt = BG_GREEN, DARK_GREEN
            elif "committed" in portal_val:
                p_bg, p_txt = BG_AMBER, DARK_AMBER
            elif any(x in portal_val for x in ["rej", "cancel"]):
                p_bg, p_txt = BG_RED, DARK_RED
            p_style = f"background-color: {p_bg}; color: {p_txt}; font-weight: 800;" if p_bg else ""

            quality_cols = ["S.No.", "Sale Date", "Customer Name", "Quality Status", "Quality Remarks"]
            portal_group = ["Portal Status", "Live Date", "Comments", "Voice of Customer", "Cancellation Reason"]

            for i, col_tuple in enumerate(row.index):
                col = col_tuple[1]
                current_style = ""

                if col == "LetterStatus":
                    current_style = f"background-color: {BG_BLUE};"
                elif col == "CallStatus":
                    current_style = c_style
                elif col in portal_group:
                    if col == "Portal Status":
                        current_style = p_style
                    else:
                        current_style = f"background-color: {p_bg};" if p_bg else ""
                elif col in quality_cols:
                    if col == "Quality Status":
                        current_style = q_style
                    else:
                        current_style = f"background-color: {q_bg};" if q_bg else ""
                else:
                    if col == "Status":
                        current_style = wc_style
                    else:
                        current_style = f"background-color: {wc_bg};" if wc_bg else ""

                if col == "S.No.":
                    current_style += "border-left: 3px solid #2563EB;"

                if col in ["Customer Name", "Quality Remarks", "Welcome call Remarks", "Cancellation Reason"]:
                    current_style += "border-right: 3px solid #E2E8F0;"

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
        '<div class="footer-note">Sparta Agent Portal • Your performance data is refreshed automatically from the connected reporting sheets.</div>',
    )

except Exception as e:
    st.error(f"Error: {e}")
