"""
Sparta Sales Dashboard - historical performance based Live forecast.

Existing features retained:
- Google Sheets loading with caching/retries.
- Existing Google Sheet history remains authoritative for records already present.
- CRM API Excel ingestion adds only records not already represented by Sale Date + normalized Phone Number.
- Date/month filters and advisor tag visibility filters.
- Top KPI cards.
- Monthly KPI Breakdown with sticky header, sorting, raw-status tooltips and totals row.
- Sales Executive Performance Breakdown with tags, sorting, raw-status tooltips and totals row.
- Editable manual projection weights remain available as an optional scenario mode.

New forecast features:
- Historical Performance projection mode is the default.
- Historical rates are calculated from mature historical sales only (configurable maturity period).
- Pending applications are forecast from their current funnel stage rather than independently adding
  QA Pending + Welcome Pending + Committed, preventing double-counting.
- QA Pending applications are first allocated into forecast QA outcomes using historical QA outcome rates.
- Welcome Pending applications use historical QA-approved -> Welcome Done progression and downstream Live conversion.
- Committed applications use historical Committed -> Live conversion.
- "FORECAST ADDL LIVE" and "Projected Live %" show the incremental Lives expected from the current pipeline.
- Historical rates used by the forecast are shown in the dashboard and in projection tooltips.
"""

import logging
import re
import time
from datetime import datetime
from html import escape
from io import BytesIO
from typing import List, Tuple

import requests

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ----------------------------------------------------------
# Basic logging
# ----------------------------------------------------------
logger = logging.getLogger("sparta_dash")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ==========================================================
# PAGE CONFIG
# ==========================================================
st.set_page_config(
    page_title="Sparta Sales Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Small base CSS
st.markdown(
    """
<style>
[data-testid="stMetric"] { border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 4px !important; box-shadow: 0 1px 3px rgba(0,0,0,0.04); text-align: center !important; }
[data-testid="stMetricLabel"] { font-size: 0.58rem !important; font-weight:700 !important; color:#475569; text-transform:uppercase; }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================================
# CONFIG / CONSTANTS
# ==========================================================
SPREADSHEET_ID: str = st.secrets.get("SPREADSHEET_ID", "1R1nXJHnmsHQhisEDronG-DMo5tWeI3Ysh8TyQmKQ2fQ")
APPLICATION_SHEET: str = st.secrets.get("APPLICATION_SHEET", "Sparta")
LIVE_SHEET: str = st.secrets.get("LIVE_SHEET", "Sparta2")
SCOPES: List[str] = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# ----------------------------------------------------------
# New CRM API source
#
# IMPORTANT:
# - Keep the token in Streamlit Secrets.
# - The API returns an XLSX workbook, not JSON.
# - The API is reconciled against the existing Google Sheets
#   data using Sale Date + normalized Phone Number.
# ----------------------------------------------------------
SPARTA_API_URL: str = st.secrets.get(
    "SPARTA_API_URL",
    "https://spartacrm.fastranking.cloud/api/dashboard/dashboard-data",
)
SPARTA_API_TOKEN: str = st.secrets.get("SPARTA_API_TOKEN", "")
SPARTA_API_TIMEOUT_SECONDS: int = int(st.secrets.get("SPARTA_API_TIMEOUT_SECONDS", 60))
SPARTA_API_MAX_RETRIES: int = int(st.secrets.get("SPARTA_API_MAX_RETRIES", 3))
DATA_CACHE_TTL_SECONDS: int = int(st.secrets.get("DATA_CACHE_TTL_SECONDS", 300))

PRIMARY_KEY_COLUMNS: Tuple[str, str] = ("Sale Date", "Telephone No.")

NEW_ADVISORS = ["Subhodeep", "Ravikant", "Priyanshu", "Kajal", "Vishal", "Aryan", "Shivam"]
CUSTOMER_SERVICE_ADVISORS = ["Aman", "Ravi Inbound", "Santosh Joshi", "Vijender", "Laxmi Narayan"]
LEFT_ADVISORS = [
    "Gaurav", "Guru", "Niki", "Shaheen", "Manmeet", "Gungun", "Rani", "Archana", "Deepali", "Sushanshu",
    "Supreme", "Tokivi", "Sangeeta", "Vijay", "Khushbu", "Kushal", "Nishant", "Pawan", "Mehak", "Khushboo", "Ashima",
    "Aarti", "Abhay", "Diwakar", "Manshay", "Khusboo", "Manmet", "Lakshay", "Sneha", "Swarali", "Monica", "Paras",
    "Veer", "Yash", "Sudhanshu", "Rishabh", "Krrish", "Anshu", "Edwin", "Sravan"
]

NEW_ADVISORS_SET = {a.strip().lower() for a in NEW_ADVISORS}
CS_ADVISORS_SET = {a.strip().lower() for a in CUSTOMER_SERVICE_ADVISORS}
LEFT_ADVISORS_SET = {a.strip().lower() for a in LEFT_ADVISORS}

# ==========================================================
# Google Sheets client (cached resource)
# ==========================================================
@st.cache_resource
def get_google_service():
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError("Missing gcp_service_account in Streamlit secrets.")
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    logger.info("Google Sheets client created")
    return service

def load_sheet(sheet_name: str, max_retries: int = 3, backoff: float = 1.0) -> pd.DataFrame:
    service = get_google_service()
    for attempt in range(1, max_retries + 1):
        try:
            result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=sheet_name).execute()
            values = result.get("values", [])
            if not values:
                return pd.DataFrame()
            headers, rows = values[0], values[1:]
            max_cols = len(headers)
            cleaned_rows = [
                r + [""] * (max_cols - len(r)) if len(r) < max_cols else r[:max_cols]
                for r in rows
            ]
            df = pd.DataFrame(cleaned_rows, columns=headers)
            logger.info("Loaded sheet '%s' with %d rows", sheet_name, len(df))
            return df
        except HttpError as e:
            logger.warning("HttpError reading sheet %s (attempt %d/%d): %s", sheet_name, attempt, max_retries, e)
        except Exception as e:
            logger.exception("Unexpected error reading sheet %s (attempt %d/%d): %s", sheet_name, attempt, max_retries, e)
        if attempt < max_retries:
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise RuntimeError(f"Failed to load sheet {sheet_name} after {max_retries} attempts")

@st.cache_data(ttl=300, show_spinner=False)
def load_sheet_cached(sheet_name: str) -> pd.DataFrame:
    return load_sheet(sheet_name)

# ==========================================================
# DATA CLEANING & VECTORIZED CATEGORIZATION
# ==========================================================
PHONE_RE = re.compile(r"\D")

def clean_phone(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(PHONE_RE, "", regex=True).str.lstrip("0").str.strip()

def parse_mixed_dates_value(val) -> pd.Timestamp:
    if pd.isna(val) or str(val).strip().lower() in {"", "(blank)", "nan", "none"}:
        return pd.NaT
    val_str = str(val).strip()
    iso_match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", val_str)
    if iso_match:
        year, month, day = iso_match.groups()
        try:
            return pd.Timestamp(year=int(year), month=int(month), day=int(day))
        except ValueError:
            pass
    uk_match = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", val_str)
    if uk_match:
        day, month, year = uk_match.groups()
        try:
            return pd.Timestamp(year=int(year), month=int(month), day=int(day))
        except ValueError:
            pass
    return pd.to_datetime(val_str, errors="coerce", dayfirst=True)

def parse_date_series(series: pd.Series) -> pd.Series:
    return series.apply(parse_mixed_dates_value)

def make_record_key(
    df: pd.DataFrame,
    sale_date_clean_col: str = "Sale Date Clean",
    phone_col: str = "Telephone No.",
) -> pd.Series:
    """Build the dashboard's primary record key: Sale Date + normalized phone.

    Invalid/incomplete keys are returned as an empty string so they are never
    incorrectly treated as a duplicate of another incomplete record.
    """
    if df.empty:
        return pd.Series(index=df.index, dtype="object")

    if phone_col in df.columns:
        phone = clean_phone(df[phone_col])
    else:
        phone = pd.Series("", index=df.index, dtype="object")

    if sale_date_clean_col in df.columns:
        sale_date = pd.to_datetime(df[sale_date_clean_col], errors="coerce")
    elif "Sale Date" in df.columns:
        sale_date = parse_date_series(df["Sale Date"])
    else:
        sale_date = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

    date_key = sale_date.dt.strftime("%Y-%m-%d").fillna("")
    phone_key = phone.fillna("").astype(str).str.strip()

    valid = date_key.ne("") & phone_key.ne("")
    keys = date_key + "|" + phone_key
    return keys.where(valid, "")

def attach_record_key(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["_Record Key"] = make_record_key(result)
    return result

def unique_valid_keys(frames: List[pd.DataFrame]) -> set:
    keys = set()
    for frame in frames:
        if frame is None or frame.empty:
            continue
        if "_Record Key" not in frame.columns:
            frame = attach_record_key(frame)
        vals = frame.loc[frame["_Record Key"].astype(str).str.len() > 0, "_Record Key"]
        keys.update(vals.astype(str).tolist())
    return keys

def format_date_ddmmyyyy(series: pd.Series) -> pd.Series:
    parsed = parse_date_series(series)
    return parsed.dt.strftime("%d/%m/%Y").fillna("")

def categorize_quality_status_series(s: pd.Series) -> pd.Series:
    s_norm = s.fillna("").astype(str).str.strip().str.lower()
    pending_mask = s_norm.isin(["", "(blank)", "nan", "none"])
    approved_mask = s_norm.str.contains("appr", na=False)
    rework_mask = s_norm.str.contains("rework", na=False)
    cancelled_mask = s_norm.str.contains(r"cancel|reject|hold|duplicat|inbound|n/a|rec in accessible", na=False)
    return pd.Series(
        np.select(
            [pending_mask, approved_mask, rework_mask, cancelled_mask],
            ["Pending", "Approved", "Rework", "Cancelled"],
            default="Cancelled"
        ),
        index=s.index,
    )

def categorize_welcome_status_series(s: pd.Series) -> pd.Series:
    s_norm = s.fillna("").astype(str).str.strip().str.lower()
    pending_mask = (
        s_norm.isin(["", "(blank)", "nan", "none"])
        | s_norm.str.contains(r"pending|follow|paperwork|wrong|ring|other work|assign", na=False)
    )
    done_mask = s_norm.str.contains(r"done|approved|complete", na=False)
    cancelled_mask = s_norm.str.contains(r"cancel|reject|hold", na=False)
    return pd.Series(
        np.select([pending_mask, done_mask, cancelled_mask], ["Pending", "Done", "Cancelled"], default="Pending"),
        index=s.index,
    )

def categorize_portal_status_series(s: pd.Series) -> pd.Series:
    s_norm = s.fillna("").astype(str).str.strip().str.lower()
    committed_mask = s_norm.isin(["", "(blank)", "nan", "none"]) | s_norm.str.contains(r"commit|in progress|processing", na=False)
    cancelled_mask = s_norm.str.contains(r"cancel|reject", na=False)
    live_mask = s_norm.str.contains(r"live|pending|active|completed", na=False)
    return pd.Series(
        np.select([cancelled_mask, live_mask, committed_mask], ["Cancelled", "Live", "Committed"], default="Committed"),
        index=s.index,
    )

def get_raw_breakdown(df: pd.DataFrame, raw_col: str, clean_col: str, target_val: str):
    if raw_col not in df.columns or clean_col not in df.columns:
        return []
    mask = df[clean_col] == target_val
    raw_values = df.loc[mask, raw_col].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")
    if raw_values.empty:
        return []
    counts = raw_values.value_counts()
    return [(str(rv), int(cnt)) for rv, cnt in counts.items()]

def format_raw_breakdown(df: pd.DataFrame, raw_col: str, clean_col: str, target_val: str) -> str:
    breakdown = get_raw_breakdown(df, raw_col, clean_col, target_val)
    if not breakdown:
        return ""
    lines = [f"{raw}: {count}" for raw, count in breakdown]
    total = sum(count for _, count in breakdown)
    return "Raw Status Breakdown\n" + "\n".join(lines) + f"\nTotal: {total}"


# ==========================================================
# HISTORICAL FORECAST ENGINE
# ==========================================================

def calculate_historical_forecast_rates(
    df: pd.DataFrame,
    maturity_days: int = 90,
    lookback_months: int = 0,
) -> dict:
    """Calculate funnel progression rates from sufficiently mature historical sales.

    The model deliberately uses outcome/progression rates rather than treating each pending
    bucket as an independent probability. This prevents double-counting the same application.
    """
    rates = {
        "history_start": None,
        "history_end": None,
        "mature_records": 0,
        "qa_approved_rate": 0.0,
        "qa_rework_rate": 0.0,
        "qa_cancelled_rate": 0.0,
        "welcome_done_given_qa_approved": 0.0,
        "committed_given_welcome_done": 0.0,
        "live_given_committed": 0.0,
    }

    if df.empty or "Sale Date Clean" not in df.columns:
        return rates

    hist = df.copy()
    valid_dates = hist["Sale Date Clean"].dropna()
    if valid_dates.empty:
        return rates

    today = pd.Timestamp(datetime.today().date())
    cutoff = today - pd.Timedelta(days=int(maturity_days))
    hist = hist[hist["Sale Date Clean"].notna() & (hist["Sale Date Clean"] <= cutoff)].copy()

    if lookback_months and lookback_months > 0:
        start_cutoff = (today - pd.DateOffset(months=int(lookback_months)))
        hist = hist[hist["Sale Date Clean"] >= start_cutoff].copy()

    if hist.empty:
        return rates

    rates["history_start"] = hist["Sale Date Clean"].min()
    rates["history_end"] = hist["Sale Date Clean"].max()
    rates["mature_records"] = int(len(hist))

    # QA outcome distribution: use the mature application base, exactly as requested.
    # Missing/unrecognised values are not forced into Approved/Rework/Cancelled.
    if "Quality Status Clean" in hist.columns:
        total = len(hist)
        if total:
            rates["qa_approved_rate"] = float((hist["Quality Status Clean"] == "Approved").sum() / total)
            rates["qa_rework_rate"] = float((hist["Quality Status Clean"] == "Rework").sum() / total)
            rates["qa_cancelled_rate"] = float((hist["Quality Status Clean"] == "Cancelled").sum() / total)

    # QA Approved -> Welcome Done. Keep the denominator as all mature QA-approved sales,
    # so unresolved Welcome activity is conservatively reflected rather than silently ignored.
    if "Quality Status Clean" in hist.columns and "Welcome Status Clean" in hist.columns:
        qa_approved = hist[hist["Quality Status Clean"] == "Approved"]
        if len(qa_approved) > 0:
            rates["welcome_done_given_qa_approved"] = float(
                (qa_approved["Welcome Status Clean"] == "Done").sum() / len(qa_approved)
            )

    # Welcome Done -> Committed/Live. Live sales have already passed the committed stage,
    # so they count as successful progression from Welcome Done as well.
    if "Welcome Status Clean" in hist.columns and "Portal Status Clean" in hist.columns:
        welcome_done = hist[hist["Welcome Status Clean"] == "Done"]
        if len(welcome_done) > 0:
            progressed = welcome_done["Portal Status Clean"].isin(["Committed", "Live"]).sum()
            rates["committed_given_welcome_done"] = float(progressed / len(welcome_done))

    # Committed -> Live. Use resolved committed outcomes only (Live vs Cancelled),
    # excluding currently-unresolved Committed records from this rate.
    if "Portal Status Clean" in hist.columns:
        resolved_committed = hist[hist["Portal Status Clean"].isin(["Live", "Cancelled"])]
        if len(resolved_committed) > 0:
            rates["live_given_committed"] = float(
                (resolved_committed["Portal Status Clean"] == "Live").sum() / len(resolved_committed)
            )

    return rates


def forecast_additional_live_for_dataframe(
    df: pd.DataFrame,
    rates: dict,
    committed_frac: float,
    welcome_pending_frac: float,
    quality_pending_frac: float,
    projection_method: str,
) -> dict:
    """Return row-level aggregate forecast metrics for a dataframe.

    Historical mode assigns each currently uncertain application to its latest/earliest
    unresolved funnel stage so the same sale cannot be counted more than once.
    Manual mode retains the legacy weighted formula for backward compatibility.
    """
    result = {
        "actual_live": 0,
        "forecast_additional_live": 0.0,
        "projected_live": 0,
        "qa_pending_count": 0,
        "qa_pending_projected_approved": 0.0,
        "qa_pending_projected_rework": 0.0,
        "qa_pending_projected_cancelled": 0.0,
        "welcome_pending_count": 0,
        "committed_count": 0,
        "projection_notes": "",
    }

    if df.empty:
        return result

    portal_series = df.get("Portal Status Clean", pd.Series(index=df.index, dtype=object))
    welcome_series = df.get("Welcome Status Clean", pd.Series(index=df.index, dtype=object))
    qa_series = df.get("Quality Status Clean", pd.Series(index=df.index, dtype=object))

    actual_live = int((portal_series == "Live").sum())
    result["actual_live"] = actual_live

    if projection_method == "Manual Scenario Weights":
        committed = int((portal_series == "Committed").sum())
        welcome_pending = int((welcome_series == "Pending").sum())
        qa_pending = int((qa_series == "Pending").sum())
        additional = (
            committed * committed_frac
            + welcome_pending * welcome_pending_frac
            + qa_pending * quality_pending_frac
        )
        result.update({
            "forecast_additional_live": float(additional),
            "projected_live": int(round(actual_live + additional)),
            "qa_pending_count": qa_pending,
            "welcome_pending_count": welcome_pending,
            "committed_count": committed,
            "projection_notes": (
                f"Manual scenario: {committed_frac:.1%} × Committed + "
                f"{welcome_pending_frac:.1%} × Welcome Pending + "
                f"{quality_pending_frac:.1%} × QA Pending"
            ),
        })
        return result

    # Historical Performance mode.
    qa_pending_mask = qa_series == "Pending"
    welcome_pending_mask = (~qa_pending_mask) & (welcome_series == "Pending")
    committed_mask = (
        (~qa_pending_mask)
        & (~welcome_pending_mask)
        & (portal_series == "Committed")
    )

    qa_pending_count = int(qa_pending_mask.sum())
    welcome_pending_count = int(welcome_pending_mask.sum())
    committed_count = int(committed_mask.sum())

    p_qa_approved = float(rates.get("qa_approved_rate", 0.0))
    p_qa_rework = float(rates.get("qa_rework_rate", 0.0))
    p_qa_cancelled = float(rates.get("qa_cancelled_rate", 0.0))
    p_welcome_done = float(rates.get("welcome_done_given_qa_approved", 0.0))
    p_committed = float(rates.get("committed_given_welcome_done", 0.0))
    p_live = float(rates.get("live_given_committed", 0.0))

    # QA pending -> forecast QA bucket. Only the portion forecast as Approved moves
    # further down the funnel toward a possible Live outcome.
    qa_projected_approved = qa_pending_count * p_qa_approved
    qa_projected_rework = qa_pending_count * p_qa_rework
    qa_projected_cancelled = qa_pending_count * p_qa_cancelled
    qa_to_live = qa_projected_approved * p_welcome_done * p_committed * p_live

    # Welcome pending -> forecast Welcome Done, then downstream progression.
    welcome_to_live = welcome_pending_count * p_welcome_done * p_committed * p_live

    # Committed -> Live directly.
    committed_to_live = committed_count * p_live

    additional = qa_to_live + welcome_to_live + committed_to_live
    projected = int(round(actual_live + additional))

    result.update({
        "forecast_additional_live": float(additional),
        "projected_live": projected,
        "qa_pending_count": qa_pending_count,
        "qa_pending_projected_approved": float(qa_projected_approved),
        "qa_pending_projected_rework": float(qa_projected_rework),
        "qa_pending_projected_cancelled": float(qa_projected_cancelled),
        "welcome_pending_count": welcome_pending_count,
        "committed_count": committed_count,
        "projection_notes": (
            "Historical funnel: QA Pending → forecast QA outcome; "
            "Welcome Pending → forecast Welcome Done; Committed → historical Live rate. "
            "Each application is counted from one current unresolved stage only."
        ),
    })
    return result


def make_projection_tooltip(summary: dict, rates: dict, projection_method: str, committed_pct_input: int, welcome_pending_pct_input: int, quality_pending_pct_input: int) -> str:
    if projection_method == "Manual Scenario Weights":
        return (
            f"Manual scenario formula: Live + ({committed_pct_input}% × Committed) + "
            f"({welcome_pending_pct_input}% × Welcome Pending) + ({quality_pending_pct_input}% × QA Pending)\n"
            f"Live: {summary.get('actual_live', 0)}\n"
            f"Committed: {summary.get('committed_count', 0)}\n"
            f"Welcome Pending: {summary.get('welcome_pending_count', 0)}\n"
            f"QA Pending: {summary.get('qa_pending_count', 0)}\n"
            f"Additional Live (weighted): {summary.get('forecast_additional_live', 0.0):.2f}\n"
            f"Projected Live (rounded): {summary.get('projected_live', 0)}"
        )

    def pct(v):
        return f"{float(v) * 100:.1f}%"

    return (
        "Historical-performance forecast\n"
        f"QA Approved baseline: {pct(rates.get('qa_approved_rate', 0))}\n"
        f"QA Rework baseline: {pct(rates.get('qa_rework_rate', 0))}\n"
        f"QA Cancelled baseline: {pct(rates.get('qa_cancelled_rate', 0))}\n"
        f"QA Approved → Welcome Done: {pct(rates.get('welcome_done_given_qa_approved', 0))}\n"
        f"Welcome Done → Committed/Live: {pct(rates.get('committed_given_welcome_done', 0))}\n"
        f"Committed → Live: {pct(rates.get('live_given_committed', 0))}\n"
        f"QA Pending: {summary.get('qa_pending_count', 0)} → "
        f"Approved≈{summary.get('qa_pending_projected_approved', 0.0):.1f}, "
        f"Rework≈{summary.get('qa_pending_projected_rework', 0.0):.1f}, "
        f"Cancelled≈{summary.get('qa_pending_projected_cancelled', 0.0):.1f}\n"
        f"Welcome Pending: {summary.get('welcome_pending_count', 0)}\n"
        f"Committed: {summary.get('committed_count', 0)}\n"
        f"Forecast Additional Live: {summary.get('forecast_additional_live', 0.0):.2f}\n"
        f"Projected Live (rounded): {summary.get('projected_live', 0)}"
    )

# ==========================================================
# API DATA LOADING / NORMALISATION
# ==========================================================

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

API_APPLICATION_COLUMNS = [
    "Sale Date",
    "Advisor",
    "Customer Name",
    "Telephone No.",
    "Quality Status",
    "Quality Remarks",
    "Welcome Status",
    "Welcome Remarks",
    "Welcome Cancellation",
    "Provisioning Status",
    "API Cancellation Reasons",
    "Sale Date Clean",
    "_Record Key",
    "_Data Source",
]

API_PORTAL_COLUMNS = [
    "Sale Date",
    "Telephone No.",
    "Portal Status",
    "Portal Status Clean",
    "Letter Status",
    "Call Status",
    "Comments",
    "Voice of Customer",
    "Portal Cancellation",
    "Live Date",
    "Sale Date Clean",
    "_Record Key",
    "_Data Source",
]

def _combine_nonblank_text(row: pd.Series, columns: List[str]) -> str:
    parts = []
    for col in columns:
        value = row.get(col, "")
        if pd.isna(value):
            continue
        value = str(value).strip()
        if not value or value.lower() in {"nan", "none", "(blank)"}:
            continue
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
        parts.append(value)
    return " | ".join(dict.fromkeys(parts))

def _normalise_api_raw_text(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in result.columns:
        if result[col].dtype == object:
            result[col] = result[col].apply(
                lambda x: "" if pd.isna(x) else str(x).replace("\x00", "").strip()
            )
    return result

@st.cache_data(ttl=DATA_CACHE_TTL_SECONDS, show_spinner=False)
def load_api_raw() -> pd.DataFrame:
    """Download the CRM's current XLSX export.

    The API source is intentionally independent from Google Sheets.
    Any API error raises a source-specific exception so the caller can
    continue using Google data when possible.
    """
    if not SPARTA_API_TOKEN:
        raise RuntimeError(
            "Missing SPARTA_API_TOKEN in Streamlit secrets. "
            "Add the CRM API bearer token before enabling API ingestion."
        )

    headers = {
        "Authorization": f"Bearer {SPARTA_API_TOKEN}",
        "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/octet-stream",
    }

    response = None
    last_error = None

    for attempt in range(1, SPARTA_API_MAX_RETRIES + 1):
        try:
            response = requests.get(
                SPARTA_API_URL,
                headers=headers,
                timeout=SPARTA_API_TIMEOUT_SECONDS,
            )

            # Do not waste retries on normal authentication/schema errors.
            if 400 <= response.status_code < 500 and response.status_code not in {408, 429}:
                response.raise_for_status()

            response.raise_for_status()
            break

        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "CRM API request failed (attempt %d/%d): %s",
                attempt,
                SPARTA_API_MAX_RETRIES,
                exc,
            )
            if attempt < SPARTA_API_MAX_RETRIES:
                time.sleep(1.5 * (2 ** (attempt - 1)))

    if response is None:
        raise RuntimeError(f"CRM API request failed: {last_error}")

    content = response.content
    if not content:
        raise RuntimeError("CRM API returned an empty response.")

    # XLSX files are ZIP containers and normally begin with PK.
    if not content.startswith(b"PK"):
        content_type = response.headers.get("Content-Type", "unknown")
        preview = content[:120].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"CRM API did not return an XLSX file. Content-Type={content_type}. "
            f"Response preview={preview!r}"
        )

    try:
        raw = pd.read_excel(BytesIO(content), engine="openpyxl")
    except Exception as exc:
        raise RuntimeError(f"Unable to parse CRM API Excel response: {exc}") from exc

    raw = _normalise_api_raw_text(raw)

    missing = [c for c in API_REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise RuntimeError(
            "CRM API Excel schema is missing required columns: "
            + ", ".join(missing)
        )

    logger.info("CRM API returned %d rows and %d columns", len(raw), len(raw.columns))
    return raw

@st.cache_data(ttl=DATA_CACHE_TTL_SECONDS, show_spinner=False)
def normalise_api_records(raw_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Convert the consolidated CRM API export into the dashboard's two logical views.

    The dashboard still thinks in terms of Applications + Portal/Live data,
    but API records are derived from one consolidated API row.
    """
    if raw_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = raw_df.copy()

    # Standard application fields
    app = pd.DataFrame(index=df.index)
    app["Sale Date"] = df["Sale Date"]
    app["Advisor"] = df["Advisor (Created Username)"]
    app["Customer Name"] = df["Customer Name"]
    app["Telephone No."] = clean_phone(df["Phone Number"])
    app["Quality Status"] = df["Quality Status"]
    app["Quality Remarks"] = df["Quality Remarks (Quality Comments)"]
    app["Welcome Status"] = df["Welcome Call Status"]
    app["Welcome Remarks"] = df["Welcome Call Remarks (Welcome Comments)"]
    app["Welcome Cancellation"] = df["Cancellation Reason - welcome"]
    app["Provisioning Status"] = df["Provisioning Status"]
    app["API Cancellation Reasons"] = df.apply(
        lambda row: _combine_nonblank_text(
            row,
            [
                "Cancellation Reason - quality",
                "Cancellation Reason - welcome",
                "Cancellation/Rejection Reason - Provisioning",
                "Cancellation/Rejection Reason - Dispatch",
                "Cancellation/Rejection Reason - Confirmation",
                "Cancellation/Rejection Reason - Onboarding",
                "Cancellation/Rejection Reason - Potential Opportunity",
            ],
        ),
        axis=1,
    )

    app["Sale Date Clean"] = parse_date_series(app["Sale Date"])
    app["Sale Date"] = app["Sale Date Clean"].dt.strftime("%d/%m/%Y").fillna("")
    app["Quality Status Clean"] = categorize_quality_status_series(app["Quality Status"])
    app["Welcome Status Clean"] = categorize_welcome_status_series(app["Welcome Status"])
    app["_Data Source"] = "API"
    app = attach_record_key(app)

    # Standard portal/live fields
    portal = pd.DataFrame(index=df.index)
    portal["Sale Date"] = df["Sale Date"]
    portal["Telephone No."] = clean_phone(df["Phone Number"])
    portal["Portal Status"] = df["Committed (Live) Status (Onboarding Status)"]
    portal["Portal Status Clean"] = categorize_portal_status_series(portal["Portal Status"])
    portal["Letter Status"] = df["LetterStatus (Dispatch Status)"]
    portal["Call Status"] = df["Confirmation Status"]
    portal["Comments"] = df["Confirmation Comment"]
    portal["Voice of Customer"] = ""
    portal["Portal Cancellation"] = df.apply(
        lambda row: _combine_nonblank_text(
            row,
            [
                "Cancellation/Rejection Reason - Dispatch",
                "Cancellation/Rejection Reason - Confirmation",
                "Cancellation/Rejection Reason - Onboarding",
                "Cancellation Reason - welcome",
                "Cancellation Reason - quality",
            ],
        ),
        axis=1,
    )
    portal["Live Date"] = ""
    portal["Sale Date Clean"] = parse_date_series(portal["Sale Date"])
    portal["Sale Date"] = portal["Sale Date Clean"].dt.strftime("%d/%m/%Y").fillna("")
    portal["_Data Source"] = "API"
    portal = attach_record_key(portal)

    # Keep only the dashboard-standard fields from each logical view.
    app_columns = [c for c in API_APPLICATION_COLUMNS + ["Quality Status Clean", "Welcome Status Clean"] if c in app.columns]
    portal_columns = [c for c in API_PORTAL_COLUMNS if c in portal.columns]

    return app[app_columns].copy(), portal[portal_columns].copy()

def reconcile_api_with_google(
    google_app_df: pd.DataFrame,
    google_portal_df: pd.DataFrame,
    api_app_df: pd.DataFrame,
    api_portal_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Keep Google history intact and add only API records not already present.

    Primary key:
        Sale Date + normalized Telephone No.

    This is deliberately two-sided:
      - Google records are never removed.
      - API duplicates already represented in either Google sheet are skipped.
      - Duplicate valid API keys inside the API export are reduced to one row.
      - Records with incomplete keys are retained but surfaced as a warning.
    """
    google_app = attach_record_key(google_app_df.copy()) if not google_app_df.empty else google_app_df.copy()
    google_portal = attach_record_key(google_portal_df.copy()) if not google_portal_df.empty else google_portal_df.copy()
    api_app = attach_record_key(api_app_df.copy()) if not api_app_df.empty else api_app_df.copy()
    api_portal = attach_record_key(api_portal_df.copy()) if not api_portal_df.empty else api_portal_df.copy()

    existing_keys = unique_valid_keys([google_app, google_portal])

    stats = {
        "google_application_rows": int(len(google_app)),
        "google_portal_rows": int(len(google_portal)),
        "api_rows_received": int(len(api_app)),
        "api_rows_with_valid_key": 0,
        "api_rows_without_valid_key": 0,
        "api_duplicate_rows_removed": 0,
        "api_rows_already_in_google": 0,
        "api_new_rows_added": 0,
    }

    if api_app.empty:
        return google_app, google_portal, stats

    valid_api = api_app["_Record Key"].astype(str).str.len() > 0
    stats["api_rows_with_valid_key"] = int(valid_api.sum())
    stats["api_rows_without_valid_key"] = int((~valid_api).sum())

    # Deduplicate API itself by the agreed primary key. Keep the last row returned.
    duplicate_mask = valid_api & api_app["_Record Key"].duplicated(keep="last")
    duplicate_count = int(duplicate_mask.sum())
    stats["api_duplicate_rows_removed"] = duplicate_count

    api_keep = ~duplicate_mask
    api_app = api_app.loc[api_keep].copy()
    api_portal = api_portal.loc[api_keep].copy()

    already_in_google = (
        api_app["_Record Key"].astype(str).isin(existing_keys)
        & api_app["_Record Key"].astype(str).ne("")
    )
    stats["api_rows_already_in_google"] = int(already_in_google.sum())

    # Incomplete-key records cannot be safely reconciled, so retain them rather than drop them.
    new_mask = (~already_in_google) | api_app["_Record Key"].astype(str).eq("")
    new_api_app = api_app.loc[new_mask].copy()
    new_api_portal = api_portal.loc[new_mask].copy()

    stats["api_new_rows_added"] = int(len(new_api_app))

    combined_app = pd.concat([google_app, new_api_app], ignore_index=True, sort=False)
    combined_portal = pd.concat([google_portal, new_api_portal], ignore_index=True, sort=False)

    return combined_app, combined_portal, stats

# ==========================================================
# DATA LOADING
# ==========================================================
@st.cache_data(ttl=300, show_spinner=False)
def load_sparta() -> pd.DataFrame:
    df = load_sheet_cached(APPLICATION_SHEET)
    if df.empty:
        return df
    rename_map = {
        "Advisor": "Advisor",
        "Sale Date": "Sale Date",
        "Customer Name": "Customer Name",
        "CLI": "Telephone No.",
        "Quality Date": "Quality Date",
        "Quality Status": "Quality Status",
        "Quality Remarks": "Quality Remarks",
        "Welcome call Remarks": "Welcome Remarks",
        "Status": "Welcome Status",
        "Cancellation Sub-text": "Welcome Cancellation",
        "WCD date": "Welcome Date",
        "Provisioning": "Provisioning Status",
        "Prov Date": "Provisioning Date",
        "Current Provider": "Current Provider",
        "Packageoffered": "Package",
        "Dashboard_Month": "Dashboard Month",
        "Standardized_Date": "Standardized Date",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    keep_columns = [c for c in rename_map.values() if c in df.columns]
    df = df[keep_columns].copy()
    if "Telephone No." in df.columns:
        df["Telephone No."] = clean_phone(df["Telephone No."])
    if "Sale Date" in df.columns:
        df["Sale Date Clean"] = parse_date_series(df["Sale Date"])
        df["Sale Date"] = format_date_ddmmyyyy(df["Sale Date"])
    for col in ["Quality Date", "Welcome Date", "Provisioning Date", "Standardized Date"]:
        if col in df.columns:
            df[col] = format_date_ddmmyyyy(df[col])
    if "Quality Status" in df.columns:
        df["Quality Status Clean"] = categorize_quality_status_series(df["Quality Status"])
    if "Welcome Status" in df.columns:
        df["Welcome Status Clean"] = categorize_welcome_status_series(df["Welcome Status"])
    df["_Data Source"] = "Google Sheets"
    df = attach_record_key(df)
    return df

@st.cache_data(ttl=300, show_spinner=False)
def load_sparta2() -> pd.DataFrame:
    df = load_sheet_cached(LIVE_SHEET)
    if df.empty:
        return df
    rename_map = {
        "Sale Date": "Sale Date",
        "Telephone No.": "Telephone No.",
        "Committed Date": "Live Date",
        "Status": "Portal Status",
        "LetterStatus": "Letter Status",
        "CallStatus": "Call Status",
        "Comments": "Comments",
        "Voice of Customer": "Voice of Customer",
        "Cancellation Reason": "Portal Cancellation",
        "Dashboard_Month": "Dashboard Month",
        "Standardized_Date": "Standardized Date",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    keep_columns = [c for c in rename_map.values() if c in df.columns]
    df = df[keep_columns].copy()
    if "Telephone No." in df.columns:
        df["Telephone No."] = clean_phone(df["Telephone No."])
    if "Sale Date" in df.columns:
        df["Sale Date Clean"] = parse_date_series(df["Sale Date"])
        df["Sale Date"] = format_date_ddmmyyyy(df["Sale Date"])
    for date_col in ["Live Date", "Standardized Date"]:
        if date_col in df.columns:
            df[date_col] = format_date_ddmmyyyy(df[date_col])
    if "Portal Status" in df.columns:
        df["Portal Status Clean"] = categorize_portal_status_series(df["Portal Status"])
    df["_Data Source"] = "Google Sheets"
    df = attach_record_key(df)
    return df

# --------------------------------------------------------------------------
# Load the two sources independently.
#
# Google Sheets is the legacy/history source and is never replaced by the API.
# The API is allowed to fail without taking down the existing dashboard.
# --------------------------------------------------------------------------
with st.spinner("Loading Google Sheets and CRM API..."):
    google_error = None
    api_error = None

    try:
        google_sparta_df = load_sparta()
        google_sparta2_df = load_sparta2()
    except Exception as e:
        google_error = str(e)
        google_sparta_df = pd.DataFrame()
        google_sparta2_df = pd.DataFrame()
        logger.exception("Google Sheets source failed: %s", e)

    try:
        api_raw_df = load_api_raw()
        api_sparta_df, api_sparta2_df = normalise_api_records(api_raw_df)
    except Exception as e:
        api_error = str(e)
        api_raw_df = pd.DataFrame()
        api_sparta_df = pd.DataFrame()
        api_sparta2_df = pd.DataFrame()
        logger.exception("CRM API source failed: %s", e)

    if google_error and api_error:
        st.error(
            "Both Sparta data sources failed.\n\n"
            f"Google Sheets: {google_error}\n\n"
            f"CRM API: {api_error}"
        )
        st.stop()

    # Reconcile only after both independent loads have completed.
    reconciliation_stats = {}
    if api_error:
        sparta_df = google_sparta_df
        sparta2_df = google_sparta2_df
        st.warning(
            "CRM API is currently unavailable, so the dashboard is showing the existing "
            "Google Sheets data only. The Google Sheets source was not modified."
        )
        st.caption(f"API error: {api_error}")
    elif google_error:
        # API-only fallback is allowed so a transient Google outage does not blank the app.
        sparta_df = api_sparta_df
        sparta2_df = api_sparta2_df
        st.warning(
            "Google Sheets is currently unavailable, so the dashboard is showing API data only "
            "for this refresh. Historical Google records are not deleted or changed."
        )
        st.caption(f"Google Sheets error: {google_error}")
        reconciliation_stats = {
            "google_application_rows": 0,
            "google_portal_rows": 0,
            "api_rows_received": int(len(api_sparta_df)),
            "api_rows_with_valid_key": int((api_sparta_df["_Record Key"].astype(str).str.len() > 0).sum()) if not api_sparta_df.empty else 0,
            "api_rows_without_valid_key": int((api_sparta_df["_Record Key"].astype(str).str.len() == 0).sum()) if not api_sparta_df.empty else 0,
            "api_duplicate_rows_removed": 0,
            "api_rows_already_in_google": 0,
            "api_new_rows_added": int(len(api_sparta_df)),
        }
    else:
        sparta_df, sparta2_df, reconciliation_stats = reconcile_api_with_google(
            google_sparta_df,
            google_sparta2_df,
            api_sparta_df,
            api_sparta2_df,
        )

# Source diagnostics — intentionally compact so the existing dashboard UI is unchanged.
if not reconciliation_stats:
    reconciliation_stats = {
        "google_application_rows": int(len(sparta_df)),
        "google_portal_rows": int(len(sparta2_df)),
        "api_rows_received": 0,
        "api_rows_with_valid_key": 0,
        "api_rows_without_valid_key": 0,
        "api_duplicate_rows_removed": 0,
        "api_rows_already_in_google": 0,
        "api_new_rows_added": 0,
    }

diag_col1, diag_col2, diag_col3, diag_col4 = st.columns(4)
with diag_col1:
    st.caption(f"📚 Google history: **{reconciliation_stats.get('google_application_rows', len(sparta_df)):,}**")
with diag_col2:
    st.caption(f"🔌 API rows received: **{reconciliation_stats.get('api_rows_received', 0):,}**")
with diag_col3:
    st.caption(f"➕ New API rows added: **{reconciliation_stats.get('api_new_rows_added', 0):,}**")
with diag_col4:
    st.caption(f"🔑 Primary key: **Sale Date + Phone**")

invalid_key_count = int(reconciliation_stats.get("api_rows_without_valid_key", 0))
duplicate_api_count = int(reconciliation_stats.get("api_duplicate_rows_removed", 0))
already_google_count = int(reconciliation_stats.get("api_rows_already_in_google", 0))

if invalid_key_count > 0:
    st.warning(
        f"API contains {invalid_key_count:,} row(s) without a usable Sale Date + Phone key. "
        "These rows are retained for visibility but cannot be safely matched against Google history."
    )

if duplicate_api_count > 0 or already_google_count > 0:
    st.caption(
        f"Reconciliation: {already_google_count:,} API row(s) already in Google; "
        f"{duplicate_api_count:,} duplicate API key row(s) removed."
    )

@st.cache_data(ttl=300, show_spinner=False)
def build_master_dataframe(app_df: pd.DataFrame, portal_df: pd.DataFrame) -> pd.DataFrame:
    """Merge application and portal views without cross-date status leakage.

    Primary match:
        Sale Date + Telephone No.

    Legacy fallback:
        For an application with no exact portal match, use the latest portal
        record for the same phone number. This preserves the old dashboard's
        phone-based behaviour where exact sale-date matching is unavailable,
        while preventing a new API record from overwriting a historical sale
        on the same phone when an exact key exists.
    """
    apps = attach_record_key(app_df.copy())
    portal = attach_record_key(portal_df.copy())

    if apps.empty:
        return apps

    if portal.empty or "Telephone No." not in portal.columns:
        return apps

    portal = portal.copy()
    portal["Telephone No."] = clean_phone(portal["Telephone No."])
    portal = portal[portal["Telephone No."] != ""].copy()

    if portal.empty:
        return apps

    # The logical portal fields used by the existing dashboard.
    portal_fields = [
        c for c in [
            "Portal Status",
            "Portal Status Clean",
            "Letter Status",
            "Call Status",
            "Comments",
            "Voice of Customer",
            "Portal Cancellation",
            "Live Date",
        ] if c in portal.columns
    ]

    if not portal_fields:
        return apps

    # Exact primary-key match.
    valid_exact_portal = portal[portal["_Record Key"].astype(str).str.len() > 0].copy()
    exact_portal = valid_exact_portal.drop_duplicates(
        subset="_Record Key",
        keep="last",
    )[["_Record Key"] + portal_fields].copy()
    merged = apps.merge(
        exact_portal,
        on="_Record Key",
        how="left",
        suffixes=("", "_exact"),
    )

    # Phone-only fallback using the latest portal row per phone, matching legacy behaviour.
    portal_sorted = portal.copy()
    if "Sale Date Clean" in portal_sorted.columns:
        portal_sorted = portal_sorted.sort_values(
            ["Telephone No.", "Sale Date Clean", "_Record Key"],
            kind="stable",
        )
    fallback_portal = portal_sorted.drop_duplicates(
        subset="Telephone No.",
        keep="last",
    )[["Telephone No."] + portal_fields].copy()

    fallback_rename = {c: f"{c}_phonefallback" for c in portal_fields}
    fallback_portal = fallback_portal.rename(columns=fallback_rename)

    merged = merged.merge(
        fallback_portal,
        on="Telephone No.",
        how="left",
    )

    for col in portal_fields:
        exact_col = col
        fallback_col = f"{col}_phonefallback"
        if fallback_col not in merged.columns:
            continue

        if exact_col not in merged.columns:
            merged[exact_col] = merged[fallback_col]
        else:
            exact_values = merged[exact_col].fillna("").astype(str).str.strip()
            fallback_values = merged[fallback_col].fillna("").astype(str).str.strip()
            use_fallback = exact_values.eq("") & fallback_values.ne("")
            merged.loc[use_fallback, exact_col] = merged.loc[use_fallback, fallback_col]

        merged.drop(columns=[fallback_col], inplace=True, errors="ignore")

    return merged

master_raw_df = build_master_dataframe(sparta_df, sparta2_df)

def assign_periods(df: pd.DataFrame, date_col: str = "Sale Date Clean", default_period: str = "2026-01"):
    if date_col in df.columns and not df[date_col].dropna().empty:
        df["Month_Year"] = df[date_col].dt.strftime("%B %Y")
        df["Period_Sort"] = df[date_col].dt.to_period("M")
    else:
        df["Month_Year"] = "Unknown"
        df["Period_Sort"] = pd.Period(default_period, freq="M")
    return df

master_raw_df = assign_periods(master_raw_df)
sparta2_df = assign_periods(sparta2_df)

# ==========================================================
# FILTERS SECTION
# ==========================================================
st.subheader("📅 Filters")

if "Sale Date Clean" in master_raw_df.columns and not master_raw_df["Sale Date Clean"].dropna().empty:
    available_months = ["All Months"] + list(
        master_raw_df["Sale Date Clean"].dt.to_period("M").drop_duplicates().sort_values(ascending=False).dt.strftime("%B %Y")
    )
else:
    available_months = ["All Months"]

valid_dates = master_raw_df["Sale Date Clean"].dropna() if "Sale Date Clean" in master_raw_df.columns else pd.Series(dtype="datetime64[ns]")
min_date = valid_dates.min().date() if not valid_dates.empty else datetime.today().date()
max_date = valid_dates.max().date() if not valid_dates.empty else datetime.today().date()

filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
with filter_col1:
    selected_month = st.selectbox("Select Month", options=available_months, index=0)
with filter_col2:
    start_date = st.date_input("Start Date", value=min_date, min_value=min_date, max_value=max_date, format="DD/MM/YYYY")
with filter_col3:
    end_date = st.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date, format="DD/MM/YYYY")

st.markdown("##### Tag Visibility Filters")
tag_col1, tag_col2, tag_col3, tag_col4 = st.columns([1, 1, 1, 1])
with tag_col1:
    include_new = st.checkbox("Include 'New' Agents", value=True)
with tag_col2:
    include_cs = st.checkbox("Include 'Customer Service' Agents", value=True)
with tag_col3:
    include_left = st.checkbox("Include 'Left' Agents", value=False)
with tag_col4:
    include_untagged = st.checkbox("Include Untagged Names", value=True)

# ==========================================================
# Projection model controls
# ==========================================================
st.markdown("##### Projection model")
projection_method = st.selectbox(
    "Projection method",
    options=["Historical Performance", "Manual Scenario Weights"],
    index=0,
    help="Historical Performance uses mature historical funnel behaviour. Manual Scenario Weights retains the original editable-weight model.",
)

hist_col1, hist_col2 = st.columns([1, 1])
with hist_col1:
    historical_maturity_days = st.number_input(
        "Historical maturity (days)",
        min_value=30,
        max_value=365,
        value=90,
        step=15,
        help="Only sales at least this many days old are used to establish historical performance rates.",
    )
with hist_col2:
    historical_lookback_months = st.number_input(
        "Historical lookback (months)",
        min_value=0,
        max_value=60,
        value=0,
        step=3,
        help="0 = use all mature history; otherwise limit the historical baseline to the selected number of months.",
    )

st.markdown("##### Manual scenario weights (retained from previous dashboard)")
proj_col1, proj_col2, proj_col3, proj_col4 = st.columns([1, 1, 1, 2])
with proj_col1:
    committed_pct_input = st.number_input("Committed weight %", min_value=0, max_value=100, value=60, step=1, help="Legacy/manual scenario: percent of committed expected to convert to Live")
with proj_col2:
    welcome_pending_pct_input = st.number_input("Welcome Pending weight %", min_value=0, max_value=100, value=35, step=1, help="Legacy/manual scenario: percent of Welcome Pending expected to convert to Live")
with proj_col3:
    quality_pending_pct_input = st.number_input("Quality Pending weight %", min_value=0, max_value=100, value=25, step=1, help="Legacy/manual scenario: percent of Quality Pending expected to convert to Live")
with proj_col4:
    if projection_method == "Historical Performance":
        st.markdown("**Applied model:** historical funnel rates from mature sales; pending stages are forecast once only.")
    else:
        st.markdown(
            f"**Applied formula** (legacy/manual):  \nProjected Live = Live + ({committed_pct_input}% × Committed) + ({welcome_pending_pct_input}% × Welcome Pending) + ({quality_pending_pct_input}% × QA Pending)"
        )

# Convert manual weights to fractional multipliers
committed_frac = committed_pct_input / 100.0
welcome_pending_frac = welcome_pending_pct_input / 100.0
quality_pending_frac = quality_pending_pct_input / 100.0

# Historical baseline is intentionally independent from the active date/month filter.
historical_rates = calculate_historical_forecast_rates(
    master_raw_df,
    maturity_days=int(historical_maturity_days),
    lookback_months=int(historical_lookback_months),
)

if historical_rates.get("mature_records", 0) > 0:
    hist_start = pd.Timestamp(historical_rates["history_start"]).strftime("%d/%m/%Y")
    hist_end = pd.Timestamp(historical_rates["history_end"]).strftime("%d/%m/%Y")
    st.caption(
        f"Historical baseline: {historical_rates['mature_records']:,} mature sales from {hist_start} to {hist_end}. "
        f"QA Approved {historical_rates['qa_approved_rate']*100:.1f}% | "
        f"QA Approved→Welcome Done {historical_rates['welcome_done_given_qa_approved']*100:.1f}% | "
        f"Welcome Done→Committed/Live {historical_rates['committed_given_welcome_done']*100:.1f}% | "
        f"Committed→Live {historical_rates['live_given_committed']*100:.1f}%"
    )
else:
    st.warning("No sufficiently mature historical sales were available for the selected maturity/lookback settings. Historical projection will therefore be 0 until enough history is available.")

if start_date > end_date:
    st.error("Error: Start Date must be earlier than or equal to End Date.")
    master_df = master_raw_df.copy()
    filtered_portal_df = sparta2_df.copy()
else:
    if "Sale Date Clean" in master_raw_df.columns:
        date_mask = (master_raw_df["Sale Date Clean"].dt.date >= start_date) & (master_raw_df["Sale Date Clean"].dt.date <= end_date)
        if selected_month != "All Months":
            date_mask &= master_raw_df["Month_Year"] == selected_month
        master_df = master_raw_df[date_mask].copy()
    else:
        master_df = master_raw_df.copy()

    if "Sale Date Clean" in sparta2_df.columns:
        portal_date_mask = (sparta2_df["Sale Date Clean"].dt.date >= start_date) & (sparta2_df["Sale Date Clean"].dt.date <= end_date)
        if selected_month != "All Months":
            portal_date_mask &= sparta2_df["Month_Year"] == selected_month
        filtered_portal_df = sparta2_df[portal_date_mask].copy()
    else:
        filtered_portal_df = sparta2_df.copy()

# ==========================================================
# TOP KPI SECTION
# ==========================================================
st.subheader("📌 Key Performance Indicators")

def count_status(df: pd.DataFrame, column: str, target_val: str) -> int:
    return int((df[column] == target_val).sum()) if column in df.columns else 0

def get_pct(part: int, total: int) -> str:
    return "0.0%" if total == 0 else f"{(part / total * 100):.1f}%"

total_applications = len(master_df)
portal_total = len(filtered_portal_df)

q_approved = count_status(master_df, "Quality Status Clean", "Approved")
q_rework = count_status(master_df, "Quality Status Clean", "Rework")
q_cancelled = count_status(master_df, "Quality Status Clean", "Cancelled")
q_pending = count_status(master_df, "Quality Status Clean", "Pending")

wc_done = count_status(master_df, "Welcome Status Clean", "Done")
wc_cancelled = count_status(master_df, "Welcome Status Clean", "Cancelled")
wc_pending = count_status(master_df, "Welcome Status Clean", "Pending")

portal_live = count_status(filtered_portal_df, "Portal Status Clean", "Live")
portal_committed = count_status(filtered_portal_df, "Portal Status Clean", "Committed")
portal_cancelled = count_status(filtered_portal_df, "Portal Status Clean", "Cancelled")

current_projection_summary = forecast_additional_live_for_dataframe(
    master_df,
    historical_rates,
    committed_frac,
    welcome_pending_frac,
    quality_pending_frac,
    projection_method,
)
current_projection_summary["actual_live"] = portal_live
current_projection_summary["projected_live"] = int(round(
    portal_live + current_projection_summary["forecast_additional_live"]
))

all_kpis = [
    ("Applications", total_applications, "100% Base", "#3b82f6", "#eff6ff", "#1d4ed8"),
    ("Quality Approved", q_approved, f"{get_pct(q_approved, total_applications)} Qualified", "#10b981", "#f0fdf4", "#15803d"),
    ("Quality Rework", q_rework, f"{get_pct(q_rework, total_applications)} In Rework", "#f59e0b", "#fefce8", "#b45309"),
    ("Quality Cancelled", q_cancelled, f"{get_pct(q_cancelled, total_applications)} Rejected", "#ef4444", "#fef2f2", "#b91c1c"),
    ("Quality Pending", q_pending, f"{get_pct(q_pending, total_applications)} Pending", "#f97316", "#fff7ed", "#c2410c"),
    ("Welcome Done", wc_done, f"{get_pct(wc_done, total_applications)} Completed", "#10b981", "#f0fdf4", "#15803d"),
    ("Welcome Cancelled", wc_cancelled, f"{get_pct(wc_cancelled, total_applications)} Cancelled", "#ef4444", "#fef2f2", "#b91c1c"),
    ("Welcome Pending", wc_pending, f"{get_pct(wc_pending, total_applications)} Pending", "#f59e0b", "#fefce8", "#b45309"),
    ("Live Status: Live", portal_live, f"{get_pct(portal_live, portal_total)} Live/Pend.", "#14b8a6", "#f0fdfa", "#0f766e"),
    ("Live Status: Comm.", portal_committed, f"{get_pct(portal_committed, portal_total)} Pipeline", "#f59e0b", "#fefce8", "#b45309"),
    ("Live Status: Canc.", portal_cancelled, f"{get_pct(portal_cancelled, portal_total)} Churned", "#ef4444", "#fef2f2", "#b91c1c"),
]

visible_kpis = [k for k in all_kpis if k[1] > 0]

if visible_kpis:
    cols = st.columns(len(visible_kpis))
    for col, (label, val, delta_sub, border_col, bg_col, delta_col) in zip(cols, visible_kpis):
        with col:
            st.markdown(
                f"""
                <div style="border:1px solid #e2e8f0;border-top:4px solid {border_col};background-color:{bg_col};border-radius:8px;padding:8px 4px; text-align:center;">
                    <div style="font-size:0.58rem;font-weight:700;color:#475569;text-transform:uppercase;">{label}</div>
                    <div style="font-size:1.3rem;font-weight:800;color:#0f172a;margin-top:6px;">{val:,}</div>
                    <div style="font-size:0.62rem;font-weight:700;color:{delta_col};margin-top:4px;">{delta_sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
else:
    st.info("No active KPIs for the selected filters.")

# Historical forecast headline for current filters
forecast_kpi_col1, forecast_kpi_col2, forecast_kpi_col3 = st.columns([1, 1, 1])
with forecast_kpi_col1:
    st.metric("Actual Live", f"{current_projection_summary['actual_live']:,}")
with forecast_kpi_col2:
    st.metric("Forecast Additional Live", f"{current_projection_summary['forecast_additional_live']:.1f}")
with forecast_kpi_col3:
    st.metric("Projected Live", f"{current_projection_summary['projected_live']:,}")

# ==========================================================
# MONTHLY KPI BREAKDOWN (SELECTABLE YEAR) - with sticky header & sorting (month sorts by PERIOD_KEY)
# PROJECTED LIVE is now historical-performance based by default; manual weights remain available as a scenario mode
# ==========================================================
st.divider()
st.subheader("📅 Monthly KPI Breakdown")

current_year = datetime.now().year
years = list(range(2022, current_year + 1))
selected_year = st.selectbox("Select year for monthly breakdown", options=years, index=len(years) - 1)

monthly_app_df = master_raw_df.dropna(subset=["Period_Sort"]).copy()
monthly_app_df = monthly_app_df[monthly_app_df["Period_Sort"].dt.year == int(selected_year)]

monthly_portal_df = sparta2_df.dropna(subset=["Period_Sort"]).copy()
monthly_portal_df = monthly_portal_df[monthly_portal_df["Period_Sort"].dt.year == int(selected_year)]

all_periods = sorted(list(set(monthly_app_df["Period_Sort"]).union(set(monthly_portal_df["Period_Sort"]))), reverse=True)

if not all_periods:
    st.info(f"No {selected_year} monthly data available for the KPI summary table.")
else:
    def build_monthly_summary(month_periods):
        rows = []
        for period in month_periods:
            m_str = period.strftime("%B %Y")
            period_key = int(period.year) * 100 + int(period.month)  # e.g., 202601
            m_app = monthly_app_df[monthly_app_df["Period_Sort"] == period]
            m_portal = monthly_portal_df[monthly_portal_df["Period_Sort"] == period]
            m_total_apps = len(m_app)
            m_qa_approved = count_status(m_app, "Quality Status Clean", "Approved")
            m_qa_rework = count_status(m_app, "Quality Status Clean", "Rework")
            m_qa_cancelled = count_status(m_app, "Quality Status Clean", "Cancelled")
            m_qa_pending = count_status(m_app, "Quality Status Clean", "Pending")
            m_wc_done = count_status(m_app, "Welcome Status Clean", "Done")
            m_wc_cancelled = count_status(m_app, "Welcome Status Clean", "Cancelled")
            m_wc_pending = count_status(m_app, "Welcome Status Clean", "Pending")
            m_p_live = count_status(m_portal, "Portal Status Clean", "Live")
            m_p_committed = count_status(m_portal, "Portal Status Clean", "Committed")
            m_p_cancelled = count_status(m_portal, "Portal Status Clean", "Cancelled")

            qa_approved_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Approved")
            qa_rework_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Rework")
            qa_cancelled_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Cancelled")
            qa_pending_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Pending")

            welcome_done_raw = format_raw_breakdown(m_app, "Welcome Status", "Welcome Status Clean", "Done")
            welcome_cancelled_raw = format_raw_breakdown(m_app, "Welcome Status", "Welcome Status Clean", "Cancelled")
            welcome_pending_raw = format_raw_breakdown(m_app, "Welcome Status", "Welcome Status Clean", "Pending")

            committed_raw = format_raw_breakdown(m_portal, "Portal Status", "Portal Status Clean", "Committed")
            live_raw = format_raw_breakdown(m_portal, "Portal Status", "Portal Status Clean", "Live")
            live_cancelled_raw = format_raw_breakdown(m_portal, "Portal Status", "Portal Status Clean", "Cancelled")

            # Build a compact monthly projection from the current funnel counts.
            # Use the merged application/portal dataframe for historical mode so that the
            # stage precedence is preserved and QA/Welcome Pending records cannot also be
            # counted as Committed simply because their portal status is blank/defaulted.
            if projection_method == "Historical Performance":
                monthly_projection = forecast_additional_live_for_dataframe(
                    m_app,
                    historical_rates,
                    committed_frac,
                    welcome_pending_frac,
                    quality_pending_frac,
                    projection_method,
                )
                # Keep the displayed actual Live count aligned with the existing portal table.
                monthly_projection["actual_live"] = m_p_live
                monthly_projection["projected_live"] = int(round(
                    m_p_live + monthly_projection["forecast_additional_live"]
                ))
            else:
                # Preserve the original manual-weight behaviour as an optional scenario mode.
                manual_additional = (
                    m_p_committed * committed_frac
                    + m_wc_pending * welcome_pending_frac
                    + m_qa_pending * quality_pending_frac
                )
                monthly_projection = {
                    "actual_live": m_p_live,
                    "forecast_additional_live": float(manual_additional),
                    "projected_live": int(round(m_p_live + manual_additional)),
                    "qa_pending_count": m_qa_pending,
                    "qa_pending_projected_approved": 0.0,
                    "qa_pending_projected_rework": 0.0,
                    "qa_pending_projected_cancelled": 0.0,
                    "welcome_pending_count": m_wc_pending,
                    "committed_count": m_p_committed,
                }

            projected_tooltip = make_projection_tooltip(
                monthly_projection,
                historical_rates,
                projection_method,
                committed_pct_input,
                welcome_pending_pct_input,
                quality_pending_pct_input,
            )

            rows.append({
                "MONTH": m_str,
                "PERIOD_KEY": period_key,
                "APPLICATIONS": m_total_apps,
                "QA APPROVED": m_qa_approved,
                "QA APPROVED RAW": qa_approved_raw,
                "QA Pass Rate % Val": (m_qa_approved / m_total_apps * 100) if m_total_apps > 0 else 0.0,
                "QA REWORK": m_qa_rework,
                "QA REWORK RAW": qa_rework_raw,
                "QA CANCELLED": m_qa_cancelled,
                "QA CANCELLED RAW": qa_cancelled_raw,
                "QA PENDING": m_qa_pending,
                "QA PENDING RAW": qa_pending_raw,
                "WELCOME DONE": m_wc_done,
                "WELCOME DONE RAW": welcome_done_raw,
                "Welcome Done % Val": (m_wc_done / m_total_apps * 100) if m_total_apps > 0 else 0.0,
                "WELCOME CANCELLED": m_wc_cancelled,
                "WELCOME CANCELLED RAW": welcome_cancelled_raw,
                "WELCOME PENDING": m_wc_pending,
                "WELCOME PENDING RAW": welcome_pending_raw,
                "COMMITTED REM.": m_p_committed,
                "COMMITTED RAW": committed_raw,
                "LIVE": m_p_live,
                "LIVE RAW": live_raw,
                "Live Conversion % Val": (m_p_live / m_total_apps * 100) if m_total_apps > 0 else 0.0,
                "LIVE CANCELLED": m_p_cancelled,
                "LIVE CANCELLED RAW": live_cancelled_raw,
                # Projection fields
                "FORECAST ADDL LIVE": float(monthly_projection["forecast_additional_live"]),
                "FORECAST ADDL LIVE RAW": projected_tooltip,
                "PROJECTED LIVE": int(monthly_projection["projected_live"]),
                "PROJECTED LIVE RAW": projected_tooltip,
                "Projected Live % Val": (monthly_projection["projected_live"] / m_total_apps * 100) if m_total_apps > 0 else 0.0,
            })
        return pd.DataFrame(rows)

    monthly_summary_df = build_monthly_summary(all_periods)

    if not monthly_summary_df.empty:
        tot_apps = monthly_summary_df["APPLICATIONS"].sum()
        totals_row = {
            "MONTH": "Total",
            "PERIOD_KEY": 999999,
            "APPLICATIONS": tot_apps,
            "QA APPROVED": monthly_summary_df["QA APPROVED"].sum(),
            "QA APPROVED RAW": format_raw_breakdown(monthly_app_df, "Quality Status", "Quality Status Clean", "Approved"),
            "QA Pass Rate % Val": (monthly_summary_df["QA APPROVED"].sum() / tot_apps * 100) if tot_apps > 0 else 0.0,
            "QA REWORK": monthly_summary_df["QA REWORK"].sum(),
            "QA REWORK RAW": format_raw_breakdown(monthly_app_df, "Quality Status", "Quality Status Clean", "Rework"),
            "QA CANCELLED": monthly_summary_df["QA CANCELLED"].sum(),
            "QA CANCELLED RAW": format_raw_breakdown(monthly_app_df, "Quality Status", "Quality Status Clean", "Cancelled"),
            "QA PENDING": monthly_summary_df["QA PENDING"].sum(),
            "QA PENDING RAW": format_raw_breakdown(monthly_app_df, "Quality Status", "Quality Status Clean", "Pending"),
            "WELCOME DONE": monthly_summary_df["WELCOME DONE"].sum(),
            "WELCOME DONE RAW": format_raw_breakdown(monthly_app_df, "Welcome Status", "Welcome Status Clean", "Done"),
            "Welcome Done % Val": (monthly_summary_df["WELCOME DONE"].sum() / tot_apps * 100) if tot_apps > 0 else 0.0,
            "WELCOME CANCELLED": monthly_summary_df["WELCOME CANCELLED"].sum(),
            "WELCOME CANCELLED RAW": format_raw_breakdown(monthly_app_df, "Welcome Status", "Welcome Status Clean", "Cancelled"),
            "WELCOME PENDING": monthly_summary_df["WELCOME PENDING"].sum(),
            "WELCOME PENDING RAW": format_raw_breakdown(monthly_app_df, "Welcome Status", "Welcome Status Clean", "Pending"),
            "COMMITTED REM.": monthly_summary_df["COMMITTED REM."].sum(),
            "COMMITTED RAW": format_raw_breakdown(monthly_portal_df, "Portal Status", "Portal Status Clean", "Committed"),
            "LIVE": monthly_summary_df["LIVE"].sum(),
            "LIVE RAW": format_raw_breakdown(monthly_portal_df, "Portal Status", "Portal Status Clean", "Live"),
            "Live Conversion % Val": (monthly_summary_df["LIVE"].sum() / tot_apps * 100) if tot_apps > 0 else 0.0,
            "LIVE CANCELLED": monthly_summary_df["LIVE CANCELLED"].sum(),
            "LIVE CANCELLED RAW": format_raw_breakdown(monthly_portal_df, "Portal Status", "Portal Status Clean", "Cancelled"),
            # Totals for projections
            "FORECAST ADDL LIVE": float(monthly_summary_df["FORECAST ADDL LIVE"].sum()),
            "FORECAST ADDL LIVE RAW": "Aggregate forecast additional Live across the displayed months.",
            "PROJECTED LIVE": int(round(
                monthly_summary_df["LIVE"].sum()
                + monthly_summary_df["FORECAST ADDL LIVE"].sum()
            )),
            "PROJECTED LIVE RAW": (
                f"Aggregate {projection_method} projection using the configured historical baseline/settings."
            ),
            "Projected Live % Val": ((
                monthly_summary_df["LIVE"].sum()
                + monthly_summary_df["FORECAST ADDL LIVE"].sum()
            ) / tot_apps * 100) if tot_apps > 0 else 0.0,
        }
        monthly_summary_df = pd.concat([monthly_summary_df, pd.DataFrame([totals_row])], ignore_index=True)

    def render_pill(val_float: float, thresholds: List[float], good_bg: str = "#d1fae5"):
        val_str = f"{val_float:.1f}%"
        high, med = thresholds
        if val_float >= high:
            bg, color, border = "#d1fae5", "#047857", "#a7f3d0"
        elif val_float >= med:
            bg, color, border = "#fef3c7", "#b45309", "#fde68a"
        else:
            bg, color, border = "#ffe4e6", "#be123c", "#fecdd3"
        return f'<span data-sort="{val_float:.6f}" style="background-color: {bg}; color: {color}; border: 1px solid {border}; border-radius: 8px; padding: 2px 8px; font-weight:700;">{val_str}</span>'

    display_columns = [
        "MONTH", "APPLICATIONS", "QA APPROVED", "QA Pass Rate %",
        "QA REWORK", "QA CANCELLED", "QA PENDING", "WELCOME DONE",
        "Welcome Done %", "WELCOME CANCELLED", "WELCOME PENDING",
        "COMMITTED REM.", "LIVE", "Live Conversion %", "FORECAST ADDL LIVE", "PROJECTED LIVE", "Projected Live %", "LIVE CANCELLED",
    ]

    # Add header styles for new columns
    m_header_styles = {
        "MONTH": "background-color: #f1f5f9; color: #334155;",
        "APPLICATIONS": "background-color: #eff6ff; color: #1e40af;",
        "QA APPROVED": "background-color: #f0fdf4; color: #15803d;",
        "QA Pass Rate %": "background-color: #f0fdf4; color: #15803d;",
        "QA REWORK": "background-color: #fefce8; color: #a16207;",
        "QA CANCELLED": "background-color: #fef2f2; color: #b91c1c;",
        "QA PENDING": "background-color: #fff7ed; color: #c2410c;",
        "WELCOME DONE": "background-color: #f0fdf4; color: #15803d;",
        "Welcome Done %": "background-color: #f0fdf4; color: #15803d;",
        "WELCOME CANCELLED": "background-color: #fef2f2; color: #b91c1c;",
        "WELCOME PENDING": "background-color: #fefce8; color: #a16207;",
        "COMMITTED REM.": "background-color: #fff7ed; color: #c2410c;",
        "LIVE": "background-color: #f0fdfa; color: #0f766e;",
        "Live Conversion %": "background-color: #f0fdfa; color: #0f766e;",
        "FORECAST ADDL LIVE": "background-color: #eef2ff; color: #3730a3;",
        "PROJECTED LIVE": "background-color: #eef2ff; color: #3730a3;",
        "Projected Live %": "background-color: #eef2ff; color: #3730a3;",
        "LIVE CANCELLED": "background-color: #fef2f2; color: #b91c1c;",
    }

    # Tooltip mapping for monthly table columns -> RAW column name
    monthly_tooltip_map = {
        "QA APPROVED": "QA APPROVED RAW",
        "QA REWORK": "QA REWORK RAW",
        "QA CANCELLED": "QA CANCELLED RAW",
        "QA PENDING": "QA PENDING RAW",
        "WELCOME DONE": "WELCOME DONE RAW",
        "WELCOME CANCELLED": "WELCOME CANCELLED RAW",
        "WELCOME PENDING": "WELCOME PENDING RAW",
        "COMMITTED REM.": "COMMITTED RAW",
        "LIVE": "LIVE RAW",
        "LIVE CANCELLED": "LIVE CANCELLED RAW",
        "FORECAST ADDL LIVE": "FORECAST ADDL LIVE RAW",
        "PROJECTED LIVE": "PROJECTED LIVE RAW",
    }

    # Build monthly table HTML with sticky header, scrollable body, and sorting JS
    table_height = max(150, 95 + (len(monthly_summary_df) * 45))
    monthly_table_id = "monthly-kpi-table"
    m_html = f"""
    <style>
        .monthly-kpi-table-container {{
            width: 100%;
            overflow-x: auto;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
            margin-bottom: 20px;
            max-height: {table_height}px;
        }}
        .monthly-kpi-inner {{
            max-height: {table_height}px;
            overflow: auto;
        }}
        .monthly-kpi-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 0.88rem;
            background-color: #ffffff;
        }}
        .monthly-kpi-table th {{
            padding: 12px 14px;
            font-weight: 800;
            font-size: 0.78rem;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            text-align: center;
            border-bottom: 2px solid #e2e8f0;
            border-right: 1px solid #f1f5f9;
            position: sticky;
            top: 0;
            z-index: 5;
            background: #ffffff;
            cursor: pointer;
        }}
        .monthly-kpi-table th:first-child {{
            text-align: left;
        }}
        .monthly-kpi-table td {{
            padding: 10px 14px;
            text-align: center;
            border-bottom: 1px solid #f1f5f9;
            border-right: 1px solid #f8fafc;
            color: #1e293b;
        }}
        .monthly-kpi-table td:first-child {{
            text-align: left;
            font-weight: 700;
            color: #0f172a;
        }}
        .monthly-kpi-table tr.totals-row {{
            font-weight: 800;
            background-color: #f8fafc;
            border-top: 2px solid #cbd5e1;
        }}
        .monthly-kpi-table tr:hover:not(.totals-row) {{
            background-color: #f8fafc;
        }}
    </style>
    <div class="monthly-kpi-table-container">
      <div class="monthly-kpi-inner">
        <table id="{monthly_table_id}" class="monthly-kpi-table">
            <thead>
                <tr>
    """
    for col_name in display_columns:
        th_style = m_header_styles.get(col_name, "background-color: #f8fafc; color: #475569;")
        m_html += f'<th style="{th_style}">{col_name}</th>'
    m_html += "</tr></thead><tbody>"

    # Render rows, marking totals row with class="totals-row"
    for _, row in monthly_summary_df.iterrows():
        is_total = str(row.get("MONTH", "")).strip().lower() == "total"
        if is_total:
            m_html += '<tr class="totals-row">'
        else:
            m_html += "<tr>"

        for col_name in display_columns:
            if col_name == "MONTH":
                period_key = int(row.get("PERIOD_KEY", 0)) if pd.notna(row.get("PERIOD_KEY", None)) else 0
                cell_text = escape(str(row["MONTH"]))
                m_html += f'<td data-sort="{period_key}">{cell_text}</td>'
            elif col_name == "QA Pass Rate %":
                val = float(row["QA Pass Rate % Val"])
                m_html += f'<td data-sort="{val:.6f}">{render_pill(val, thresholds=[75.0, 51.0])}</td>'
            elif col_name == "Welcome Done %":
                val = float(row["Welcome Done % Val"])
                m_html += f'<td data-sort="{val:.6f}">{render_pill(val, thresholds=[61.0, 51.0])}</td>'
            elif col_name == "Live Conversion %":
                val = float(row["Live Conversion % Val"])
                m_html += f'<td data-sort="{val:.6f}">{render_pill(val, thresholds=[41.0, 21.0])}</td>'
            elif col_name == "FORECAST ADDL LIVE":
                val = float(row.get("FORECAST ADDL LIVE", 0.0))
                raw_text = row.get("FORECAST ADDL LIVE RAW", "")
                formatted_val = "-" if val == 0 else f"{val:.1f}"
                if raw_text and val != 0:
                    tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                    m_html += f'<td data-sort="{val}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
                else:
                    m_html += f'<td data-sort="{val}">{formatted_val}</td>'
            elif col_name == "PROJECTED LIVE":
                val = int(row.get("PROJECTED LIVE", 0))
                raw_text = row.get("PROJECTED LIVE RAW", "")
                if raw_text and val != 0:
                    tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                    m_html += f'<td data-sort="{val}" title="{tooltip_html}" style="cursor:help;">{val:,}</td>'
                else:
                    m_html += f'<td data-sort="{val}">{val:,}</td>'
            elif col_name == "Projected Live %":
                val = float(row.get("Projected Live % Val", 0.0))
                # reuse render_pill for percent display, attach tooltip
                raw_text = row.get("PROJECTED LIVE RAW", "")
                pill_html = render_pill(val, thresholds=[41.0, 21.0])
                if raw_text and val != 0:
                    tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                    m_html += f'<td data-sort="{val:.6f}" title="{tooltip_html}" style="cursor:help;">{pill_html}</td>'
                else:
                    m_html += f'<td data-sort="{val:.6f}">{pill_html}</td>'
            else:
                val = row.get(col_name, 0)
                raw_column = monthly_tooltip_map.get(col_name)
                raw_text = row.get(raw_column, "") if raw_column else ""
                if isinstance(val, (int, np.integer)):
                    formatted_val = "-" if int(val) == 0 else f"{int(val):,}"
                    if raw_text and int(val) != 0:
                        tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                        m_html += f'<td data-sort="{int(val)}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
                    else:
                        m_html += f'<td data-sort="{int(val)}">{formatted_val}</td>'
                else:
                    formatted_val = "-" if (val == 0 or pd.isna(val)) else escape(str(val))
                    if isinstance(val, float):
                        if raw_text and val != 0:
                            tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                            m_html += f'<td data-sort="{val}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
                        else:
                            m_html += f'<td data-sort="{val}">{formatted_val}</td>'
                    else:
                        if raw_text and str(val) not in ("0", "-", ""):
                            tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                            m_html += f'<td data-sort="{escape(str(val))}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
                        else:
                            m_html += f'<td data-sort="{escape(str(val))}">{formatted_val}</td>'
        m_html += "</tr>"

    m_html += "</tbody></table></div></div>"

    # Sorting JS for monthly table - uses data-sort (numeric) and keeps totals-row at bottom
    m_html += f"""
    <script>
    (function() {{
      function makeSortable(tableId) {{
        const table = document.getElementById(tableId);
        if(!table) return;
        const tbody = table.tBodies[0];
        const headers = table.querySelectorAll('th');
        headers.forEach((th, index) => {{
          th.addEventListener('click', () => {{
            const current = th.getAttribute('data-order') || 'desc';
            const newOrder = current === 'asc' ? 'desc' : 'asc';
            headers.forEach(h => h.removeAttribute('data-order'));
            th.setAttribute('data-order', newOrder);
            const rows = Array.from(tbody.querySelectorAll('tr')).filter(r => !r.classList.contains('totals-row'));
            rows.sort((a,b) => {{
              const aCell = a.children[index];
              const bCell = b.children[index];
              const aVal = aCell ? aCell.getAttribute('data-sort') || aCell.innerText : '';
              const bVal = bCell ? bCell.getAttribute('data-sort') || bCell.innerText : '';
              const aNum = parseFloat(aVal.toString().replace(/,/g,'')); 
              const bNum = parseFloat(bVal.toString().replace(/,/g,''));
              if(!isNaN(aNum) && !isNaN(bNum)) {{
                return newOrder === 'asc' ? aNum - bNum : bNum - aNum;
              }}
              return newOrder === 'asc' ? aVal.toString().localeCompare(bVal.toString()) : bVal.toString().localeCompare(aVal.toString());
            }});
            rows.forEach(r => tbody.appendChild(r));
            const totals = tbody.querySelector('tr.totals-row');
            if(totals) tbody.appendChild(totals);
          }});
        }});
      }}
      makeSortable("{monthly_table_id}");
    }})();
    </script>
    """

    components.html(m_html, height=table_height, scrolling=False)

# ==========================================================
# ADVISOR PERFORMANCE MATRIX (with per-advisor tooltips, totals row, sticky header & sorting)
# Add historical FORECAST ADDL LIVE, PROJECTED LIVE and Projected Live %
# ==========================================================
st.divider()
st.subheader("👥 Sales Executive Performance Breakdown")

if "Advisor" in master_df.columns and not master_df.empty:
    advisor_summary = (
        master_df.groupby("Advisor", dropna=False)
            .agg(
                Applications=("Advisor", "count"),
                QA_Approved=("Quality Status Clean", lambda x: (x == "Approved").sum()),
                QA_Rework=("Quality Status Clean", lambda x: (x == "Rework").sum()),
                QA_Cancelled=("Quality Status Clean", lambda x: (x == "Cancelled").sum()),
                QA_Pending=("Quality Status Clean", lambda x: (x == "Pending").sum()),
                Welcome_Done=("Welcome Status Clean", lambda x: (x == "Done").sum()),
                Welcome_Cancelled=("Welcome Status Clean", lambda x: (x == "Cancelled").sum()),
                Welcome_Pending=("Welcome Status Clean", lambda x: (x == "Pending").sum()),
                Committed=("Portal Status Clean", lambda x: (x == "Committed").sum()),
                Live=("Portal Status Clean", lambda x: (x == "Live").sum()),
                Live_Cancelled=("Portal Status Clean", lambda x: (x == "Cancelled").sum()),
            )
            .reset_index()
    )

    def filter_tagged_rows(row):
        name = (str(row["Advisor"]) or "").strip().lower()
        is_new = name in NEW_ADVISORS_SET
        is_cs = name in CS_ADVISORS_SET
        is_left = name in LEFT_ADVISORS_SET
        is_tagged = is_new or is_cs or is_left
        if is_new and not include_new:
            return False
        if is_cs and not include_cs:
            return False
        if is_left and not include_left:
            return False
        if not is_tagged and not include_untagged:
            return False
        return True

    advisor_summary = advisor_summary[advisor_summary.apply(filter_tagged_rows, axis=1)].copy()

    if advisor_summary.empty:
        st.info("No sales records match the selected tag filters.")
    else:
        advisor_summary["QA Pass Rate % Val"] = ((advisor_summary["QA_Approved"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Welcome Done % Val"] = ((advisor_summary["Welcome_Done"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Live Conversion % Val"] = ((advisor_summary["Live"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)

        # Row-level stage-aware forecast per advisor to avoid double-counting.
        advisor_lookup = {}
        for advisor_name, advisor_rows in master_df.groupby("Advisor", dropna=False):
            lookup_name = "Unassigned" if pd.isna(advisor_name) or str(advisor_name).strip() == "" else str(advisor_name).strip()
            advisor_lookup[lookup_name] = forecast_additional_live_for_dataframe(
                advisor_rows,
                historical_rates,
                committed_frac,
                welcome_pending_frac,
                quality_pending_frac,
                projection_method,
            )

        advisor_summary["FORECAST ADDL LIVE"] = advisor_summary["Advisor"].map(
            lambda a: float(advisor_lookup.get(
                "Unassigned" if pd.isna(a) or str(a).strip() == "" else str(a).strip(),
                {},
            ).get("forecast_additional_live", 0.0))
        )
        advisor_summary["PROJECTED LIVE"] = advisor_summary["Advisor"].map(
            lambda a: int(advisor_lookup.get(
                "Unassigned" if pd.isna(a) or str(a).strip() == "" else str(a).strip(),
                {},
            ).get("projected_live", 0))
        )
        advisor_summary["FORECAST ADDL LIVE RAW"] = advisor_summary["Advisor"].map(
            lambda a: make_projection_tooltip(
                advisor_lookup.get(
                    "Unassigned" if pd.isna(a) or str(a).strip() == "" else str(a).strip(),
                    {},
                ),
                historical_rates,
                projection_method,
                committed_pct_input,
                welcome_pending_pct_input,
                quality_pending_pct_input,
            )
        )
        advisor_summary["PROJECTED LIVE RAW"] = advisor_summary["FORECAST ADDL LIVE RAW"]

        advisor_summary["Projected Live % Val"] = (
            (advisor_summary["PROJECTED LIVE"] / advisor_summary["Applications"].replace(0, np.nan)) * 100
        ).fillna(0.0)

        # 4. Rename columns to match display standards
        advisor_summary = advisor_summary.rename(columns={
            "Advisor": "SALES EXECUTIVE",
            "Applications": "APPLICATIONS",
            "QA_Approved": "QA APPROVED",
            "QA_Rework": "QA REWORK",
            "QA_Cancelled": "QA CANCELLED",
            "QA_Pending": "QA PENDING",
            "Welcome_Done": "WELCOME DONE",
            "Welcome_Cancelled": "WELCOME CANCELLED",
            "Welcome_Pending": "WELCOME PENDING",
            "Committed": "COMMITTED REM.",
            "Live": "LIVE",
            "Live_Cancelled": "LIVE CANCELLED",
        })

        advisor_summary["SALES EXECUTIVE"] = advisor_summary["SALES EXECUTIVE"].replace("", "Unassigned").fillna("Unassigned")
        advisor_summary = advisor_summary.sort_values(by="APPLICATIONS", ascending=False)

        # Build per-advisor raw breakdown tooltips once (use master_df as source)
        advisor_tooltip_mapping = {
            "QA APPROVED": ("Quality Status", "Quality Status Clean", "Approved"),
            "QA REWORK": ("Quality Status", "Quality Status Clean", "Rework"),
            "QA CANCELLED": ("Quality Status", "Quality Status Clean", "Cancelled"),
            "QA PENDING": ("Quality Status", "Quality Status Clean", "Pending"),
            "WELCOME DONE": ("Welcome Status", "Welcome Status Clean", "Done"),
            "WELCOME CANCELLED": ("Welcome Status", "Welcome Status Clean", "Cancelled"),
            "WELCOME PENDING": ("Welcome Status", "Welcome Status Clean", "Pending"),
            "COMMITTED REM.": ("Portal Status", "Portal Status Clean", "Committed"),
            "LIVE": ("Portal Status", "Portal Status Clean", "Live"),
            "LIVE CANCELLED": ("Portal Status", "Portal Status Clean", "Cancelled"),
        }

        raw_tooltips = {}
        # Pre-normalize advisor column in master_df for matching
        master_df["_advisor_norm"] = master_df["Advisor"].fillna("").astype(str).str.strip().str.lower()
        for _, r in advisor_summary.iterrows():
            adv_display = str(r["SALES EXECUTIVE"])
            adv_norm = adv_display.strip().lower()
            subset = master_df[master_df["_advisor_norm"] == adv_norm]
            adv_tooltips = {}
            for k, (raw_col, clean_col, target_val) in advisor_tooltip_mapping.items():
                adv_tooltips[k] = format_raw_breakdown(subset, raw_col, clean_col, target_val)
            # Projection tooltip for this advisor
            adv_projection_summary = advisor_lookup.get(adv_display, {})
            adv_proj_tooltip = make_projection_tooltip(
                adv_projection_summary,
                historical_rates,
                projection_method,
                committed_pct_input,
                welcome_pending_pct_input,
                quality_pending_pct_input,
            )
            adv_tooltips["FORECAST ADDL LIVE"] = adv_proj_tooltip
            adv_tooltips["PROJECTED LIVE"] = adv_proj_tooltip
            raw_tooltips[adv_display] = adv_tooltips
        # drop the helper column
        master_df.drop(columns=["_advisor_norm"], inplace=True, errors=True)

        numeric_cols = {
            "APPLICATIONS", "QA APPROVED", "QA REWORK", "QA CANCELLED", "QA PENDING",
            "WELCOME DONE", "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.", "LIVE", "LIVE CANCELLED", "FORECAST ADDL LIVE", "PROJECTED LIVE"
        }

        base_col_order = [
            "SALES EXECUTIVE", "APPLICATIONS", "QA APPROVED", "QA Pass Rate %",
            "QA REWORK", "QA CANCELLED", "QA PENDING", "WELCOME DONE", "Welcome Done %",
            "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.",
            "LIVE", "Live Conversion %", "FORECAST ADDL LIVE", "PROJECTED LIVE", "Projected Live %", "LIVE CANCELLED"
        ]

        visible_cols = ["SALES EXECUTIVE"]
        for col in base_col_order[1:]:
            if col in numeric_cols:
                if (advisor_summary.get(col, pd.Series(dtype=int)) > 0).any():
                    visible_cols.append(col)
            elif col == "QA Pass Rate %":
                if "QA APPROVED" in visible_cols:
                    visible_cols.append(col)
            elif col == "Welcome Done %":
                if "WELCOME DONE" in visible_cols:
                    visible_cols.append(col)
            elif col == "Live Conversion %":
                if "LIVE" in visible_cols:
                    visible_cols.append(col)
            elif col == "Projected Live %":
                if "PROJECTED LIVE" in visible_cols:
                    visible_cols.append(col)

        def render_qa_pill(v):
            if v >= 75.0:
                return f'<span data-sort="{v:.6f}" style="background-color:#d1fae5; color:#047857; border:1px solid #a7f3d0; border-radius:8px; padding:3px 12px; font-weight:700;">{v:.1f}%</span>'
            if v >= 51.0:
                return f'<span data-sort="{v:.6f}" style="background-color:#fef3c7;color:#b45309;border:1px solid #fde68a;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'
            return f'<span data-sort="{v:.6f}" style="background-color:#ffe4e6;color:#be123c;border:1px solid #fecdd3;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'

        def render_welcome_pill(v):
            if v >= 61.0:
                return f'<span data-sort="{v:.6f}" style="background-color:#d1fae5;color:#047857;border:1px solid #a7f3d0;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'
            if v >= 51.0:
                return f'<span data-sort="{v:.6f}" style="background-color:#fef3c7;color:#b45309;border:1px solid #fde68a;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'
            return f'<span data-sort="{v:.6f}" style="background-color:#ffe4e6;color:#be123c;border:1px solid #fecdd3;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'

        def render_live_pill(v):
            if v >= 41.0:
                return f'<span data-sort="{v:.6f}" style="background-color:#d1fae5;color:#047857;border:1px solid #a7f3d0;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'
            if v >= 21.0:
                return f'<span data-sort="{v:.6f}" style="background-color:#fef3c7;color:#b45309;border:1px solid #fde68a;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'
            return f'<span data-sort="{v:.6f}" style="background-color:#ffe4e6;color:#be123c;border:1px solid #fecdd3;border-radius:8px;padding:3px 12px;font-weight:700;">{v:.1f}%</span>'

        header_styles = {
            "SALES EXECUTIVE": "background-color:#f1f5f9;color:#334155;",
            "APPLICATIONS": "background-color:#eff6ff;color:#1e40af;",
            "QA APPROVED": "background-color:#f0fdf4;color:#15803d;",
            "QA Pass Rate %": "background-color:#f0fdf4;color:#15803d;",
            "QA REWORK": "background-color:#fefce8;color:#a16207;",
            "QA CANCELLED": "background-color:#fef2f2;color:#b91c1c;",
            "QA PENDING": "background-color:#fff7ed;color:#c2410c;",
            "WELCOME DONE": "background-color:#f0fdf4;color:#15803d;",
            "Welcome Done %": "background-color:#f0fdf4;color:#15803d;",
            "WELCOME CANCELLED": "background-color:#fef2f2;color:#b91c1c;",
            "WELCOME PENDING": "background-color:#fefce8;color:#a16207;",
            "COMMITTED REM.": "background-color:#fff7ed;color:#c2410c;",
            "LIVE": "background-color:#f0fdfa;color:#0f766e;",
            "LIVE CANCELLED": "background-color:#fef2f2;color:#b91c1c;",
            "FORECAST ADDL LIVE": "background-color:#eef2ff;color:#3730a3;",
            "PROJECTED LIVE": "background-color:#eef2ff;color:#3730a3;",
            "Projected Live %": "background-color:#eef2ff;color:#3730a3;",
            "Live Conversion %": "background-color:#f0fdfa;color:#0f766e;",
        }

        # Compute totals across visible advisors for numeric columns
        totals_series = advisor_summary[[c for c in advisor_summary.columns if isinstance(c, str) and c in numeric_cols]].sum(numeric_only=True)
        total_apps = int(totals_series.get("APPLICATIONS", 0))
        total_qa_approved = int(totals_series.get("QA APPROVED", 0))
        total_welcome_done = int(totals_series.get("WELCOME DONE", 0))
        total_live = int(totals_series.get("LIVE", 0))

        # totals percentages (overall)
        total_qa_pass_pct = (total_qa_approved / total_apps * 100) if total_apps > 0 else 0.0
        total_welcome_pct = (total_welcome_done / total_apps * 100) if total_apps > 0 else 0.0
        total_live_pct = (total_live / total_apps * 100) if total_apps > 0 else 0.0

        # totals tooltips using filtered master_df
        totals_tooltips = {}
        for k, (raw_col, clean_col, target_val) in advisor_tooltip_mapping.items():
            totals_tooltips[k] = format_raw_breakdown(master_df, raw_col, clean_col, target_val)
        # totals projection tooltip
        totals_tooltips["PROJECTED LIVE"] = (
            f"Aggregate projection using weights: {committed_pct_input}% committed, "
            f"{welcome_pending_pct_input}% welcome pending, {quality_pending_pct_input}% quality pending"
        )

        # Build advisor HTML table (use components.html to allow JS)
        advisor_table_id = "advisor-perf-table"
        advisor_table_height = min(900, max(240, 90 + len(advisor_summary) * 45))
        adv_html = f'''
        <style>
          .perf-table-container {{
            width:100%;
            border:1px solid #e2e8f0;
            border-radius:8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
            margin-bottom:16px;
            max-height:{advisor_table_height}px;
            overflow:auto;
          }}
          table.perf-table {{
            width:100%;
            border-collapse:collapse;
            font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial;
            font-size:0.88rem;
            background:#fff;
          }}
          table.perf-table th {{
            padding:10px 12px;
            font-weight:800;
            font-size:0.78rem;
            text-transform:uppercase;
            border-bottom:2px solid #e2e8f0;
            position:sticky;
            top:0;
            z-index:5;
            background:#fff;
            cursor:pointer;
          }}
          table.perf-table td {{
            padding:8px 12px;
            border-bottom:1px solid #f1f5f9;
          }}
          table.perf-table td:first-child {{
            text-align:left;
            font-weight:700;
            color:#0f172a;
          }}
          .tag{{padding:2px 6px;border-radius:6px;font-weight:700;margin-left:6px;font-size:0.68rem;display:inline-block;vertical-align:middle;}}
          .new{{background:#ede9fe;color:#6d28d9;}} .cs{{background:#e0f2fe;color:#0369a1;}} .left{{background:#fee2e2;color:#991b1b;}}
          .totals-row{{font-weight:800;background-color:#f8fafc;}}
        </style>
        <div class="perf-table-container">
          <table id="{advisor_table_id}" class="perf-table">
            <thead><tr>
        '''
        for c in visible_cols:
            style = header_styles.get(c, "background-color:#f8fafc;color:#475569;")
            adv_html += f'<th style="{style}">{c}</th>'
        adv_html += '</tr></thead><tbody>'

        for _, r in advisor_summary.iterrows():
            adv_display = str(r["SALES EXECUTIVE"])
            adv_tooltips_local = raw_tooltips.get(adv_display, {})
            adv_html += "<tr>"
            for c in visible_cols:
                if c == "SALES EXECUTIVE":
                    name = escape(str(r[c]))
                    lname = name.strip().lower()
                    tags_html = ""
                    if lname in NEW_ADVISORS_SET:
                        tags_html += '<span class="tag new">New</span>'
                    if lname in CS_ADVISORS_SET:
                        tags_html += '<span class="tag cs">Customer Service</span>'
                    if lname in LEFT_ADVISORS_SET:
                        tags_html += '<span class="tag left">Left</span>'
                    adv_html += f"<td data-sort=\"{escape(name)}\">{name}{tags_html}</td>"
                elif c == "QA Pass Rate %":
                    val = float(r["QA Pass Rate % Val"])
                    raw_text = adv_tooltips_local.get("QA APPROVED", "")
                    if raw_text and val != 0:
                        tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                        adv_html += f'<td data-sort="{val:.6f}" title="{tooltip_html}" style="cursor:help;">{render_qa_pill(val)}</td>'
                    else:
                        adv_html += f'<td data-sort="{val:.6f}">{render_qa_pill(val)}</td>'
                elif c == "Welcome Done %":
                    val = float(r["Welcome Done % Val"])
                    raw_text = adv_tooltips_local.get("WELCOME DONE", "")
                    if raw_text and val != 0:
                        tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                        adv_html += f'<td data-sort="{val:.6f}" title="{tooltip_html}" style="cursor:help;">{render_welcome_pill(val)}</td>'
                    else:
                        adv_html += f'<td data-sort="{val:.6f}">{render_welcome_pill(val)}</td>'
                elif c == "Live Conversion %":
                    val = float(r["Live Conversion % Val"])
                    raw_text = adv_tooltips_local.get("LIVE", "")
                    if raw_text and val != 0:
                        tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                        adv_html += f'<td data-sort="{val:.6f}" title="{tooltip_html}" style="cursor:help;">{render_live_pill(val)}</td>'
                    else:
                        adv_html += f'<td data-sort="{val:.6f}">{render_live_pill(val)}</td>'
                elif c == "FORECAST ADDL LIVE":
                    val = float(r.get("FORECAST ADDL LIVE", 0.0))
                    raw_text = adv_tooltips_local.get("FORECAST ADDL LIVE", "")
                    formatted_val = "-" if val == 0 else f"{val:.1f}"
                    if raw_text and val != 0:
                        tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                        adv_html += f'<td data-sort="{val}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
                    else:
                        adv_html += f'<td data-sort="{val}">{formatted_val}</td>'
                elif c == "PROJECTED LIVE":
                    val = int(r.get("PROJECTED LIVE", 0))
                    raw_text = adv_tooltips_local.get("PROJECTED LIVE", "")
                    if raw_text and val != 0:
                        tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                        adv_html += f'<td data-sort="{val}" title="{tooltip_html}" style="cursor:help;">{val:,}</td>'
                    else:
                        adv_html += f'<td data-sort="{val}">{val:,}</td>'
                elif c == "Projected Live %":
                    val = float(r.get("Projected Live % Val", 0.0))
                    raw_text = adv_tooltips_local.get("PROJECTED LIVE", "")
                    pill_html = render_live_pill(val)
                    if raw_text and val != 0:
                        tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                        adv_html += f'<td data-sort="{val:.6f}" title="{tooltip_html}" style="cursor:help;">{pill_html}</td>'
                    else:
                        adv_html += f'<td data-sort="{val:.6f}">{pill_html}</td>'
                else:
                    val = r.get(c)
                    raw_text = adv_tooltips_local.get(c, "")
                    if isinstance(val, (int, np.integer)):
                        formatted_val = "-" if int(val) == 0 else f"{int(val):,}"
                        if raw_text and int(val) != 0:
                            tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                            adv_html += f'<td data-sort="{int(val)}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
                        else:
                            adv_html += f'<td data-sort="{int(val)}">{formatted_val}</td>'
                    else:
                        formatted_val = "-" if (val == 0 or pd.isna(val)) else escape(str(val))
                        if raw_text and str(val) not in ("0", "-", ""):
                            tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                            adv_html += f'<td data-sort="{escape(str(val))}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
                        else:
                            adv_html += f'<td data-sort="{escape(str(val))}">{formatted_val}</td>'
            adv_html += "</tr>"

        # totals row
        adv_html += '<tr class="totals-row">'
        for c in visible_cols:
            if c == "SALES EXECUTIVE":
                adv_html += "<td data-sort='Total'>Total</td>"
            elif c == "QA Pass Rate %":
                adv_html += f'<td data-sort="{total_qa_pass_pct:.6f}">' + f'{render_qa_pill(total_qa_pass_pct)}</td>'
            elif c == "Welcome Done %":
                adv_html += f'<td data-sort="{total_welcome_pct:.6f}">' + f'{render_welcome_pill(total_welcome_pct)}</td>'
            elif c == "Live Conversion %":
                adv_html += f'<td data-sort="{total_live_pct:.6f}">' + f'{render_live_pill(total_live_pct)}</td>'
            elif c == "FORECAST ADDL LIVE":
                tot_additional = float(advisor_summary["FORECAST ADDL LIVE"].sum())
                tooltip_text = "Aggregate historical forecast additional Live across visible advisors."
                if tooltip_text and tot_additional != 0:
                    tooltip_html = escape(str(tooltip_text)).replace("\n", "&#10;")
                    adv_html += f'<td data-sort="{tot_additional}" title="{tooltip_html}" style="cursor:help;">{tot_additional:.1f}</td>'
                else:
                    adv_html += f'<td data-sort="{tot_additional}">{"-" if tot_additional == 0 else f"{tot_additional:.1f}"}</td>'
            elif c == "PROJECTED LIVE":
                tot_proj = int(round(
                    advisor_summary["PROJECTED LIVE"].sum()
                ))
                tooltip_text = totals_tooltips.get("PROJECTED LIVE", "")
                if tooltip_text and tot_proj != 0:
                    tooltip_html = escape(str(tooltip_text)).replace("\n", "&#10;")
                    adv_html += f'<td data-sort="{tot_proj}" title="{tooltip_html}" style="cursor:help;">{tot_proj:,}</td>'
                else:
                    adv_html += f'<td data-sort="{tot_proj}">{tot_proj:,}</td>'
            elif c == "Projected Live %":
                tot_proj_pct = ((advisor_summary["PROJECTED LIVE"].sum() / totals_series.get("APPLICATIONS", 1)) * 100) if totals_series.get("APPLICATIONS",0) > 0 else 0.0
                adv_html += f'<td data-sort="{tot_proj_pct:.6f}">'+f'{render_live_pill(tot_proj_pct)}</td>'
            else:
                if c in numeric_cols:
                    tot_val = int(totals_series.get(c, 0))
                    formatted = "-" if tot_val == 0 else f"{tot_val:,}"
                    tooltip_text = totals_tooltips.get(c, "")
                    if tooltip_text and tot_val != 0:
                        tooltip_html = escape(str(tooltip_text)).replace("\n", "&#10;")
                        adv_html += f'<td data-sort="{tot_val}" title="{tooltip_html}" style="cursor:help;">{formatted}</td>'
                    else:
                        adv_html += f'<td data-sort="{tot_val}">{formatted}</td>'
                else:
                    adv_html += "<td data-sort='-'>-</td>"
        adv_html += "</tr>"

        adv_html += "</tbody></table></div>"

        # Sorting JS for advisor table; keeps totals-row at bottom
        adv_html += f"""
        <script>
        (function() {{
          function makeSortable(tableId) {{
            const table = document.getElementById(tableId);
            if(!table) return;
            const tbody = table.tBodies[0];
            const headers = table.querySelectorAll('th');
            headers.forEach((th, index) => {{
              th.addEventListener('click', () => {{
                const current = th.getAttribute('data-order') || 'desc';
                const newOrder = current === 'asc' ? 'desc' : 'asc';
                headers.forEach(h => h.removeAttribute('data-order'));
                th.setAttribute('data-order', newOrder);
                const rows = Array.from(tbody.querySelectorAll('tr')).filter(r => !r.classList.contains('totals-row'));
                rows.sort((a,b) => {{
                  const aCell = a.children[index];
                  const bCell = b.children[index];
                  const aVal = aCell ? (aCell.getAttribute('data-sort') || aCell.innerText) : '';
                  const bVal = bCell ? (bCell.getAttribute('data-sort') || bCell.innerText) : '';
                  const aNum = parseFloat(aVal.toString().replace(/,/g,'')); 
                  const bNum = parseFloat(bVal.toString().replace(/,/g,''));
                  if(!isNaN(aNum) && !isNaN(bNum)) {{
                    return newOrder === 'asc' ? aNum - bNum : bNum - aNum;
                  }}
                  return newOrder === 'asc' ? aVal.toString().localeCompare(bVal.toString()) : bVal.toString().localeCompare(aVal.toString());
                }});
                rows.forEach(r => tbody.appendChild(r));
                const totals = tbody.querySelector('tr.totals-row');
                if(totals) tbody.appendChild(totals);
              }});
            }});
          }}
          makeSortable("{advisor_table_id}");
        }})();
        </script>
        """
        components.html(adv_html, height=advisor_table_height, scrolling=False)
else:
    st.info("No sales records available for the selected date or month filter.")

# ==========================================================
# FOOTER
# ==========================================================
st.divider()
st.success("✅ Data loaded successfully")
st.caption(f"Dashboard refreshed at {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
