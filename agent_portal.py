"""
Sparta Dashboard - updated with editable Projected Live Sales column
and an Agent filter for the Monthly KPI Breakdown table.

- New dropdown "Select Agent (Monthly table)" appears in the Monthly KPI section.
- Default: "All Agents" (entire team). Selecting an agent filters the monthly table
  to that agent's rows (both application and portal data, when available from the merged master dataset).
- No other behavior changed.
"""

import logging
import re
import time
from datetime import datetime
from html import escape
from typing import List

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import gspread
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

# ==========================================================
# HYBRID DATA SOURCE CONFIGURATION
# ==========================================================
# Historical / legacy (Excel-backed) data is authoritative through
# 17-Sep-2026 inclusive. CRM is authoritative from 18-Sep-2026 onward.
SOURCE_CUTOFF_DATE = pd.Timestamp("2026-09-17")
CRM_START_DATE = pd.Timestamp("2026-09-18")

CRM_MIRROR_WORKSHEET_GID = int(
    st.secrets.get("CRM_MIRROR_WORKSHEET_GID", "1647226826")
)

# Daily attendance source used for SPD calculations.
ATTENDANCE_WORKSHEET_GID = int(
    st.secrets.get("ATTENDANCE_WORKSHEET_GID", "1036958145")
)

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

NEW_ADVISORS = ["Aryan", "Shivam"]
CUSTOMER_SERVICE_ADVISORS = ["Aman", "Ravi Inbound", "Santosh Joshi", "Vijender", "Laxmi Narayan","Alex"]
LEFT_ADVISORS = [
    "Gaurav", "Guru", "Niki", "Shaheen", "Manmeet", "Gungun", "Rani", "Archana", "Deepali", "Sushanshu",
    "Supreme", "Tokivi", "Sangeeta", "Vijay", "Khushbu", "Kushal", "Nishant", "Pawan", "Mehak", "Khushboo", "Ashima",
    "Aarti", "Abhay", "Diwakar", "Manshay", "Khusboo", "Manmet", "Lakshay", "Sneha", "Swarali", "Monica", "Paras",
    "Veer", "Yash", "Sudhanshu", "Rishabh", "Krrish", "Anshu", "Edwin", "Sravan", "Seema"
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


@st.cache_resource
def get_crm_gspread_client():
    """Cached gspread client for the dedicated CRM mirror worksheet."""
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError("Missing gcp_service_account in Streamlit secrets.")
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(credentials)

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
    pending_mask = s_norm.isin(["", "(blank)", "nan", "none"]) | s_norm.str.contains(r"pending|follow|paperwork|wrong|ring", na=False)
    done_mask = s_norm.str.contains("done", na=False)
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


# ---------------------------------------------------------------------------
# CRM-SPECIFIC STATUS SEMANTICS
# ---------------------------------------------------------------------------
# The CRM mirror uses different terminology from the legacy Excel / Sparta
# sheets. The legacy categorisers above are intentionally left untouched.


def categorize_crm_quality_status_series(s: pd.Series) -> pd.Series:
    """Map CRM Quality Status values to the executive dashboard taxonomy."""
    s_norm = s.fillna("").astype(str).str.strip().str.lower()

    # CRM-specific: QA-Pending must remain in QA Pending, not QA Cancelled.
    pending_mask = s_norm.str.contains(r"^qa[- ]?pending$|^pending$", na=False)
    approved_mask = s_norm.str.contains(r"qa[- ]?approved|approved", na=False)
    rework_mask = s_norm.str.contains(r"rework", na=False)
    cancelled_mask = s_norm.str.contains(
        r"qa[- ]?reject|reject|cancel|hold|duplicate|inbound|n/a|rec in accessible",
        na=False,
    )

    return pd.Series(
        np.select(
            [pending_mask, approved_mask, rework_mask, cancelled_mask],
            ["Pending", "Approved", "Rework", "Cancelled"],
            default="Cancelled",
        ),
        index=s.index,
    )


def categorize_crm_welcome_status_series(s: pd.Series) -> pd.Series:
    """Map CRM Welcome Call Status values to Done / Cancelled / Pending.

    CRM blanks are intentionally left uncategorized: a blank Welcome status is
    NOT counted as Welcome Pending.
    """
    s_norm = s.fillna("").astype(str).str.strip().str.lower()

    blank_mask = s_norm.isin(["", "(blank)", "nan", "none"])
    pending_mask = (~blank_mask) & s_norm.str.contains(
        r"pending|follow[- ]?up|paperwork|wrong|ring|chasing|think",
        na=False,
    )
    done_mask = s_norm.str.contains(r"approved|done|complete", na=False)
    cancelled_mask = s_norm.str.contains(
        r"reject|cancel|declin|change of mind|hold",
        na=False,
    )

    return pd.Series(
        np.select(
            [blank_mask, pending_mask, done_mask, cancelled_mask],
            ["", "Pending", "Done", "Cancelled"],
            default="",
        ),
        index=s.index,
    )


def derive_crm_portal_status(row: pd.Series) -> str:
    """
    Derive the executive dashboard Live / Committed / Cancelled taxonomy from
    CRM's downstream provisioning, onboarding, dispatch and confirmation data.

    A blank downstream section is NOT automatically "Committed" in CRM because
    the CRM sheet contains the complete application population, unlike Sparta2.
    """
    onboarding = clean_reason_text(
        row.get("Committed (Live) Status (Onboarding Status)", "")
    ).lower()
    provisioning = clean_reason_text(row.get("Provisioning Status", "")).lower()
    dispatch = clean_reason_text(row.get("LetterStatus (Dispatch Status)", "")).lower()
    confirmation = clean_reason_text(row.get("Confirmation Status", "")).lower()

    prov_cancel_reason = clean_reason_text(
        row.get("Cancellation/Rejection Reason - Provisioning", "")
    ).lower()
    dispatch_cancel_reason = clean_reason_text(
        row.get("Cancellation/Rejection Reason - Dispatch", "")
    ).lower()
    confirmation_cancel_reason = clean_reason_text(
        row.get("Cancellation/Rejection Reason - Confirmation", "")
    ).lower()
    onboarding_cancel_reason = clean_reason_text(
        row.get("Cancellation/Rejection Reason - Onboarding", "")
    ).lower()

    # CRM-specific confirmation semantics:
    # - Confirmation Approved / Followup / Pending -> Committed
    # - Confirmation To Be Cancelled -> Live Cancelled
    confirmation_is_cancelled = bool(
        re.search(
            r"to\s*be\s*cancelled|\bcancelled\b|\bcancel\b|reject(?:ed)?|rejection",
            confirmation,
            re.IGNORECASE,
        )
    )

    # Explicit cancellation/rejection wins over all other downstream signals.
    cancelled_text = " | ".join(
        [
            provisioning,
            dispatch,
            confirmation,
            onboarding,
            prov_cancel_reason,
            dispatch_cancel_reason,
            confirmation_cancel_reason,
            onboarding_cancel_reason,
        ]
    )
    if confirmation_is_cancelled or re.search(
        r"order\s*cancelled|to\s*be\s*cancelled|cancelled|cancellation|reject(?:ed)?|rejection",
        cancelled_text,
        re.IGNORECASE,
    ):
        return "Cancelled"

    # CRM Onboarding Pending / Approved corresponds to the executive
    # dashboard's Live bucket.
    if re.search(
        r"onboarding\s+(?:approved|pending)|\blive\b|\bactive\b|\bcompleted\b",
        onboarding,
        re.IGNORECASE,
    ):
        return "Live"

    # CRM confirmation is a direct Committed-pipeline signal. These three
    # statuses must all be counted under COMMITTED REM.
    if re.search(
        r"confirmation\s+(?:approved|follow[- ]?up|pending)",
        confirmation,
        re.IGNORECASE,
    ):
        return "Committed"

    # Other genuine downstream order/provisioning signals that are not
    # cancelled and not yet onboarding-live remain in the Committed pipeline.
    committed_text = " | ".join([provisioning, dispatch, confirmation, onboarding])
    if re.search(
        r"connectivity:\s*committed|\bcommitted\b|processed|re[ -]?processed|in\s+progress|send\s+for\s+rework|dispatch\s+approved",
        committed_text,
        re.IGNORECASE,
    ):
        return "Committed"

    # No downstream pipeline state yet (for example a potential opportunity
    # or a welcome-only record): do not include it in Live/Committed KPIs.
    return ""


def build_crm_portal_frame(api: pd.DataFrame) -> pd.DataFrame:
    """Build the CRM equivalent of the legacy Sparta2 frame."""
    if api.empty:
        return pd.DataFrame()

    portal = pd.DataFrame(index=api.index)
    portal["Sale Date"] = api["Sale Date Clean"].dt.strftime("%d/%m/%Y")
    portal["Sale Date Clean"] = api["Sale Date Clean"]
    portal["Telephone No."] = api["Telephone No."]
    portal["Live Date"] = ""
    # CRM-specific display column: preserve the exact Onboarding Status value.
    portal["Final Status"] = api[
        "Committed (Live) Status (Onboarding Status)"
    ].fillna("").astype(str).str.strip()
    portal["Portal Status"] = portal["Final Status"]
    portal["Letter Status"] = api[
        "LetterStatus (Dispatch Status)"
    ].fillna("").astype(str).str.strip()
    portal["Call Status"] = api[
        "Confirmation Status"
    ].fillna("").astype(str).str.strip()
    # CRM-specific source field used by the Monthly KPI Breakdown.
    portal["Confirmation Status"] = api[
        "Confirmation Status"
    ].fillna("").astype(str).str.strip()
    portal["Comments"] = api["Confirmation Comment"].apply(clean_reason_text)
    portal["Voice of Customer"] = ""
    portal["Portal Cancellation"] = api.apply(
        combine_crm_cancellation_reasons, axis=1
    )
    portal["Provisioning Status"] = api[
        "Provisioning Status"
    ].fillna("").astype(str).str.strip()
    portal["Provisioning Remarks"] = api[
        "Provisioning Remarks (Provisioning Comments)"
    ].apply(clean_reason_text)
    portal["Dashboard Month"] = api["Sale Date Clean"].dt.strftime("%B %Y")
    portal["Standardized Date"] = portal["Sale Date"]
    portal["Portal Status Clean"] = api.apply(derive_crm_portal_status, axis=1)
    portal["Advisor"] = api["Advisor"]
    portal["Source"] = "CRM"
    portal["_RecordKey"] = api["_RecordKey"]

    # Unlike Sparta2, CRM contains the entire application population. Only
    # rows with an actual downstream pipeline state become portal rows.
    portal = portal[portal["Portal Status Clean"] != ""].copy()
    return portal.reset_index(drop=True)


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
# DATA LOADING
# ==========================================================

@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def load_sparta() -> pd.DataFrame:
    """Load the legacy / Excel-backed application history from Sparta."""
    df = load_sheet_cached(APPLICATION_SHEET)
    if df.empty:
        return df

    rename_map = {
        "Advisor": "Advisor",
        "Quality Officer": "Quality Officer",
        "Welcome Call By": "Welcome Call By",
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

    return df


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def load_sparta2() -> pd.DataFrame:
    """Load the legacy / Excel-backed portal history from Sparta2."""
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

    return df


def clean_reason_text(value) -> str:
    if pd.isna(value):
        return ""
    value = str(value).replace("<br>", " | ").replace("<br/>", " | ")
    value = re.sub(r"\s+", " ", value).strip()
    if value.lower() in {"nan", "none", "null", "nat"}:
        return ""
    return value


def normalized_phone_value(value) -> str:
    """Normalize CRM phone values consistently within the CRM source."""
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if not value or value.lower() in {"nan", "none", "null", "nat"}:
        return ""
    value = re.sub(r"\.0+$", "", value)
    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""
    if digits.startswith("44") and len(digits) in {11, 12}:
        digits = "0" + digits[2:]
    return digits


def canonicalize_crm_advisor(raw_name) -> str:
    """Map CRM usernames to dashboard advisor names where there is a safe match."""
    raw = str(raw_name).strip()
    if not raw or raw.lower() in {"nan", "none", "null", "nat"}:
        return ""

    aliases = {
        "subhodeeproy": "Subhodeep",
        "priyanshurathee": "Priyanshu",
        "kunalupreti": "Kunal",
    }

    compact = re.sub(r"[^a-z0-9]", "", raw.lower())
    if compact in aliases:
        return aliases[compact]

    known_names = list(dict.fromkeys(
        NEW_ADVISORS + CUSTOMER_SERVICE_ADVISORS + LEFT_ADVISORS
    ))

    for name in known_names:
        if compact == re.sub(r"[^a-z0-9]", "", name.lower()):
            return name

    prefix_matches = []
    for name in known_names:
        name_compact = re.sub(r"[^a-z0-9]", "", name.lower())
        if len(name_compact) >= 5 and len(compact) >= len(name_compact):
            if compact.startswith(name_compact):
                prefix_matches.append(name)

    if len(prefix_matches) == 1:
        return prefix_matches[0]

    return raw.title()


def get_first_existing_column(df: pd.DataFrame, candidates: List[str]) -> str:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return ""


def combine_crm_cancellation_reasons(row: pd.Series) -> str:
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
    for label, column in fields:
        if column in row.index:
            value = clean_reason_text(row[column])
            if value:
                parts.append(f"{label}: {value}")
    return " | ".join(parts)


def make_source_record_key(date_value, phone_value) -> str:
    parsed = parse_mixed_dates_value(date_value)
    phone = normalized_phone_value(phone_value)
    if pd.isna(parsed) or not phone:
        return ""
    return f"{pd.Timestamp(parsed).strftime('%Y-%m-%d')}|{phone}"


def fetch_crm_mirror():
    """Read the CRM Excel mirror from the dedicated Google worksheet."""
    try:
        client = get_crm_gspread_client()
        crm_ws = client.open_by_key(SPREADSHEET_ID).get_worksheet_by_id(
            CRM_MIRROR_WORKSHEET_GID
        )
        values = crm_ws.get_all_records()
        crm_df = pd.DataFrame(values)
        fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if crm_df.empty:
            return crm_df, fetched_at, "CRM mirror sheet is empty"

        crm_df.columns = [
            str(c).replace("\ufeff", "").strip()
            for c in crm_df.columns
        ]

        missing = [c for c in API_REQUIRED_COLUMNS if c not in crm_df.columns]
        if missing:
            return (
                pd.DataFrame(),
                fetched_at,
                "CRM mirror is missing required columns: " + ", ".join(missing),
            )

        return crm_df, fetched_at, ""
    except Exception as exc:
        logger.exception("CRM mirror load failed: %s", exc)
        return pd.DataFrame(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(exc)


def normalize_crm_records(crm_df: pd.DataFrame):
    """Convert CRM mirror rows into the executive dashboard's two frames."""
    if crm_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    api = crm_df.copy()

    for col in API_REQUIRED_COLUMNS:
        if col not in api.columns:
            api[col] = ""

    # CRM source becomes authoritative from 18-Sep-2026 onward.
    api["Sale Date Clean"] = api["Sale Date"].apply(parse_mixed_dates_value)
    api = api[api["Sale Date Clean"] >= CRM_START_DATE].copy()

    if api.empty:
        return pd.DataFrame(), pd.DataFrame()

    api["Advisor"] = api["Advisor (Created Username)"].apply(canonicalize_crm_advisor)
    api["Customer Name"] = api["Customer Name"].fillna("").astype(str).str.strip()
    api["Telephone No."] = api["Phone Number"].apply(normalized_phone_value)
    api["_RecordKey"] = [
        make_source_record_key(d, p)
        for d, p in zip(api["Sale Date Clean"], api["Telephone No."])
    ]

    # Stable Sale Date + Phone key is required for downstream reconciliation.
    api = api[api["_RecordKey"] != ""].copy()
    api = api.drop_duplicates(subset=["_RecordKey"], keep="last").reset_index(drop=True)

    quality_owner_col = get_first_existing_column(
        api,
        [
            "Quality Officer",
            "Quality Officer (Username)",
            "Quality Officer (Created Username)",
            "Quality Officer Username",
        ],
    )
    welcome_owner_col = get_first_existing_column(
        api,
        [
            "Welcome Call By",
            "Welcome Call By (Username)",
            "Welcome Caller",
            "Welcome Call Username",
        ],
    )

    if quality_owner_col:
        quality_owner = api[quality_owner_col].fillna("").astype(str).str.strip()
    else:
        quality_owner = pd.Series([""] * len(api), index=api.index)

    if welcome_owner_col:
        welcome_owner = api[welcome_owner_col].fillna("").astype(str).str.strip()
    else:
        welcome_owner = pd.Series([""] * len(api), index=api.index)

    # --------------------------- APPLICATION FRAME -------------------------
    app = pd.DataFrame(index=api.index)
    app["Advisor"] = api["Advisor"]
    app["Quality Officer"] = quality_owner
    app["Welcome Call By"] = welcome_owner
    app["Sale Date"] = api["Sale Date Clean"].dt.strftime("%d/%m/%Y")
    app["Sale Date Clean"] = api["Sale Date Clean"]
    app["Customer Name"] = api["Customer Name"]
    app["Telephone No."] = api["Telephone No."]
    app["Quality Status"] = api["Quality Status"].fillna("").astype(str).str.strip()
    app["Quality Remarks"] = api[
        "Quality Remarks (Quality Comments)"
    ].apply(clean_reason_text)
    app["Welcome Status"] = api["Welcome Call Status"].fillna("").astype(str).str.strip()
    app["Welcome Remarks"] = api[
        "Welcome Call Remarks (Welcome Comments)"
    ].apply(clean_reason_text)
    app["Welcome Cancellation"] = ""
    app["Provisioning Status"] = api[
        "Provisioning Status"
    ].fillna("").astype(str).str.strip()
    app["Provisioning Date"] = ""
    app["Quality Date"] = ""
    app["Welcome Date"] = ""
    app["Current Provider"] = ""
    app["Package"] = ""
    app["Dashboard Month"] = api["Sale Date Clean"].dt.strftime("%B %Y")
    app["Standardized Date"] = app["Sale Date"]
    # CRM-only source field: exact onboarding/final status from CRM.
    app["Final Status"] = api[
        "Committed (Live) Status (Onboarding Status)"
    ].fillna("").astype(str).str.strip()

    # CRM terminology is normalized explicitly here.
    app["Quality Status Clean"] = categorize_crm_quality_status_series(
        app["Quality Status"]
    )
    app["Welcome Status Clean"] = categorize_crm_welcome_status_series(
        app["Welcome Status"]
    )
    app["Source"] = "CRM"
    app["_RecordKey"] = api["_RecordKey"]

    # ----------------------------- PORTAL FRAME ----------------------------
    portal = build_crm_portal_frame(api)

    return app.reset_index(drop=True), portal.reset_index(drop=True)


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def load_hybrid_data():
    """
    Load the two sources independently and enforce the explicit date boundary.

    Legacy / Excel-backed source: Sale Date <= 17-Sep-2026
    CRM source: Sale Date >= 18-Sep-2026
    """
    # ------------------------- LEGACY / EXCEL -------------------------
    legacy_app = load_sparta()
    legacy_portal = load_sparta2()

    if "Sale Date Clean" in legacy_app.columns:
        legacy_app = legacy_app[
            legacy_app["Sale Date Clean"].notna()
            & (legacy_app["Sale Date Clean"] <= SOURCE_CUTOFF_DATE)
        ].copy()
    else:
        legacy_app = legacy_app.iloc[0:0].copy()

    if "Sale Date Clean" in legacy_portal.columns:
        legacy_portal = legacy_portal[
            legacy_portal["Sale Date Clean"].notna()
            & (legacy_portal["Sale Date Clean"] <= SOURCE_CUTOFF_DATE)
        ].copy()
    else:
        legacy_portal = legacy_portal.iloc[0:0].copy()

    legacy_app["Source"] = "Excel / Legacy"
    legacy_portal["Source"] = "Excel / Legacy"

    # ------------------------------- CRM -------------------------------
    crm_raw, crm_fetched_at, crm_error = fetch_crm_mirror()
    crm_app, crm_portal = normalize_crm_records(crm_raw)

    app_df = pd.concat([legacy_app, crm_app], ignore_index=True, sort=False)
    portal_df = pd.concat([legacy_portal, crm_portal], ignore_index=True, sort=False)

    if "Sale Date Clean" in app_df.columns:
        app_df["Sale Date Clean"] = pd.to_datetime(
            app_df["Sale Date Clean"], errors="coerce"
        )
    if "Sale Date Clean" in portal_df.columns:
        portal_df["Sale Date Clean"] = pd.to_datetime(
            portal_df["Sale Date Clean"], errors="coerce"
        )

    if "Telephone No." in app_df.columns:
        app_df["Telephone No."] = (
            app_df["Telephone No."].fillna("").astype(str).str.strip()
        )
    if "Telephone No." in portal_df.columns:
        portal_df["Telephone No."] = (
            portal_df["Telephone No."].fillna("").astype(str).str.strip()
        )

    source_status = {
        "cutoff": "17 Sep 2026",
        "crm_start": "18 Sep 2026",
        "legacy_app_rows": int(len(legacy_app)),
        "legacy_portal_rows": int(len(legacy_portal)),
        "crm_app_rows": int(len(crm_app)),
        "crm_portal_rows": int(len(crm_portal)),
        "crm_mirror_rows": int(len(crm_raw)),
        "crm_fetched_at": crm_fetched_at,
        "crm_error": crm_error,
    }

    return app_df.reset_index(drop=True), portal_df.reset_index(drop=True), source_status



# ==========================================================
# ATTENDANCE / SPD DATA
# ==========================================================

def normalize_person_key(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def normalize_attendance_value(value) -> float:
    """Map 0, 0.5, 1 and UL into FTE-days; UL is treated as 0."""
    if pd.isna(value):
        return 0.0
    text = str(value).strip().lower()
    if text in {"", "nan", "none", "null", "nat", "ul", "unauthorised leave"}:
        return 0.0
    try:
        numeric = float(text)
    except Exception:
        return 0.0
    if numeric <= 0:
        return 0.0
    if numeric >= 1:
        return 1.0
    return 0.5


def build_attendance_agent_mapping(attendance_names, dashboard_agents):
    """Match attendance names to dashboard Advisor names."""
    attendance_names = [
        str(x).strip() for x in attendance_names
        if str(x).strip() and str(x).strip().lower() not in {"nan", "none"}
    ]
    dashboard_agents = [
        str(x).strip() for x in dashboard_agents
        if str(x).strip() and str(x).strip().lower() not in {"nan", "none", "unassigned"}
    ]

    explicit_aliases = {
        "frogh": "Frogh Hassani",
        "krrish": "Krrish Sadana",
        "animesh": "Animesh Mishra",
    }

    att_by_key = {normalize_person_key(x): x for x in attendance_names if normalize_person_key(x)}
    mapping = {}

    for advisor in dashboard_agents:
        adv_key = normalize_person_key(advisor)
        if not adv_key:
            continue

        alias_target = explicit_aliases.get(adv_key)
        if alias_target:
            alias_key = normalize_person_key(alias_target)
            if alias_key in att_by_key:
                mapping[advisor] = att_by_key[alias_key]
                continue

        if adv_key in att_by_key:
            mapping[advisor] = att_by_key[adv_key]
            continue

        candidates = []
        for attendance_name in attendance_names:
            att_key = normalize_person_key(attendance_name)
            if att_key and (att_key.startswith(adv_key) or adv_key.startswith(att_key)):
                candidates.append(attendance_name)

        if len(candidates) == 1:
            mapping[advisor] = candidates[0]

    return mapping


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def load_attendance_data():
    """
    Load attendance from worksheet GID 1036958145.

    Attendance values:
        0   = absent
        0.5 = half-day
        1   = present
        UL  = 0 for SPD calculations
    """
    try:
        client = get_crm_gspread_client()
        worksheet = client.open_by_key(SPREADSHEET_ID).get_worksheet_by_id(
            ATTENDANCE_WORKSHEET_GID
        )
        values = worksheet.get_all_records()
        attendance = pd.DataFrame(values)

        if attendance.empty:
            return pd.DataFrame()

        attendance.columns = [
            str(c).replace("\ufeff", "").strip()
            for c in attendance.columns
        ]

        required = {"Name", "Date", "Attendance"}
        missing = sorted(required.difference(attendance.columns))
        if missing:
            logger.warning(
                "Attendance sheet is missing required columns: %s",
                ", ".join(missing),
            )
            return pd.DataFrame()

        if "Working Days" not in attendance.columns:
            attendance["Working Days"] = np.nan

        attendance["Date Clean"] = attendance["Date"].apply(parse_mixed_dates_value)
        attendance["Attendance Value"] = attendance["Attendance"].apply(
            normalize_attendance_value
        )
        attendance["Name"] = attendance["Name"].fillna("").astype(str).str.strip()
        attendance["Agent Key"] = attendance["Name"].apply(normalize_person_key)
        attendance["Month Period"] = attendance["Date Clean"].dt.to_period("M")
        attendance["Working Days"] = pd.to_numeric(
            attendance["Working Days"], errors="coerce"
        )
        attendance = attendance.dropna(subset=["Date Clean"]).copy()

        # Prevent duplicate rows for the same agent/date from inflating SPD.
        attendance = (
            attendance.sort_values(["Agent Key", "Date Clean"])
            .groupby(["Agent Key", "Date Clean"], as_index=False)
            .agg(
                Name=("Name", "last"),
                Attendance_Value=("Attendance Value", "max"),
                Month_Period=("Month Period", "last"),
                Working_Days=("Working Days", "max"),
            )
            .rename(columns={
                "Attendance_Value": "Attendance Value",
                "Month_Period": "Month Period",
                "Working_Days": "Working Days",
            })
        )

        # Keep the exact attendance schema expected by the SPD helpers.
        if "Working Days" not in attendance.columns:
            attendance["Working Days"] = np.nan

        return attendance.reset_index(drop=True)

    except Exception as exc:
        logger.exception("Attendance sheet load failed: %s", exc)
        return pd.DataFrame()


def get_month_working_days(attendance_df: pd.DataFrame, period) -> int:
    if attendance_df.empty or period is None:
        return 0
    month_df = attendance_df[attendance_df["Month Period"] == period].copy()
    if month_df.empty:
        return 0
    working_col = "Working Days" if "Working Days" in month_df.columns else (
        "Working_Days" if "Working_Days" in month_df.columns else ""
    )
    if working_col:
        wd = pd.to_numeric(month_df[working_col], errors="coerce").dropna()
        if not wd.empty:
            return int(round(float(wd.max())))
    # Robust fallback: count distinct attendance dates for the month.
    return int(month_df["Date Clean"].dt.normalize().nunique())


def attach_attendance_advisors(attendance_df: pd.DataFrame, master_df: pd.DataFrame):
    if attendance_df.empty or master_df.empty or "Advisor" not in master_df.columns:
        return attendance_df.copy(), {}

    dashboard_agents = (
        master_df["Advisor"]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", np.nan)
        .dropna()
        .unique()
        .tolist()
    )

    advisor_to_attendance = build_attendance_agent_mapping(
        attendance_df["Name"].dropna().unique().tolist(),
        dashboard_agents,
    )

    reverse_mapping = {
        normalize_person_key(attendance_name): advisor
        for advisor, attendance_name in advisor_to_attendance.items()
    }

    out = attendance_df.copy()
    out["Dashboard Advisor"] = out["Agent Key"].map(reverse_mapping).fillna("")
    return out, advisor_to_attendance


def get_team_month_spd(
    attendance_df: pd.DataFrame,
    period,
    applications: int,
    selected_agent: str = "All Agents",
):
    """Return (SPD, working-days capacity, present-days) for one month.

    Team view:
        SPD = Applications / total present FTE-days in the month.
        Working Days = matched agents * calendar working days.

    Selected-agent view:
        SPD = Applications / that agent's present FTE-days.
        Working Days = calendar working days in the month.
    """
    if attendance_df.empty or period is None:
        return 0.0, 0.0, 0.0

    month_att = attendance_df[attendance_df["Month Period"] == period].copy()
    if month_att.empty:
        return 0.0, 0.0, 0.0

    eligible = month_att[
        month_att["Dashboard Advisor"].fillna("").astype(str).str.strip() != ""
    ].copy()
    working_days_calendar = float(get_month_working_days(month_att, period))

    if selected_agent != "All Agents":
        selected_key = normalize_person_key(selected_agent)
        matched = eligible[
            eligible["Dashboard Advisor"].apply(normalize_person_key) == selected_key
        ]
        present_days = float(matched["Attendance Value"].sum())
        working_days_capacity = working_days_calendar if not matched.empty else 0.0
    else:
        present_days = float(eligible["Attendance Value"].sum())
        total_agents = int(eligible["Dashboard Advisor"].nunique())
        working_days_capacity = float(total_agents * working_days_calendar)

    spd = applications / present_days if applications > 0 and present_days > 0 else 0.0
    return spd, working_days_capacity, present_days


def get_daily_spd(
    attendance_df: pd.DataFrame,
    day,
    applications: int,
    selected_agent: str = "All Agents",
):
    """Return (SPD, working-days capacity, present-days) for one date.

    Team view:
        Working Days = number of mapped agents scheduled on that date.
        Present Days = sum of 0 / 0.5 / 1 attendance values.

    Selected-agent view:
        Working Days = 1 when the date is a scheduled attendance date.
        Present Days = that agent's attendance value.
    """
    if attendance_df.empty or pd.isna(day):
        return 0.0, 0.0, 0.0

    day_ts = pd.Timestamp(day).normalize()
    day_att = attendance_df[
        attendance_df["Date Clean"].dt.normalize() == day_ts
    ].copy()
    if day_att.empty:
        return 0.0, 0.0, 0.0

    eligible = day_att[
        day_att["Dashboard Advisor"].fillna("").astype(str).str.strip() != ""
    ].copy()

    if selected_agent != "All Agents":
        selected_key = normalize_person_key(selected_agent)
        matched = eligible[
            eligible["Dashboard Advisor"].apply(normalize_person_key) == selected_key
        ]
        working_days_capacity = 1.0 if not matched.empty else 0.0
        present_days = float(matched["Attendance Value"].sum())
    else:
        working_days_capacity = float(eligible["Dashboard Advisor"].nunique())
        present_days = float(eligible["Attendance Value"].sum())

    spd = applications / present_days if applications > 0 and present_days > 0 else 0.0
    return spd, working_days_capacity, present_days


with st.spinner("Loading historical + CRM data..."):
    try:
        sparta_df, sparta2_df, source_status = load_hybrid_data()
    except Exception as e:
        st.error("Failed to load the dashboard data. See logs for details.")
        logger.exception("Failed to load hybrid dashboard data: %s", e)
        st.stop()


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def build_master_dataframe(app_df: pd.DataFrame, portal_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge application and portal records on Sale Date + Telephone No.

    This prevents a later sale using the same phone number from receiving the
    downstream portal status of an earlier sale.
    """
    apps = app_df.copy()
    portal = portal_df.copy()

    if "_RecordKey" not in apps.columns:
        apps["_RecordKey"] = [
            make_source_record_key(d, p)
            for d, p in zip(
                apps.get(
                    "Sale Date Clean",
                    pd.Series(index=apps.index, dtype="datetime64[ns]"),
                ),
                apps.get(
                    "Telephone No.",
                    pd.Series([""] * len(apps), index=apps.index),
                ),
            )
        ]

    if "_RecordKey" not in portal.columns:
        portal["_RecordKey"] = [
            make_source_record_key(d, p)
            for d, p in zip(
                portal.get(
                    "Sale Date Clean",
                    pd.Series(index=portal.index, dtype="datetime64[ns]"),
                ),
                portal.get(
                    "Telephone No.",
                    pd.Series([""] * len(portal), index=portal.index),
                ),
            )
        ]

    portal_valid = portal[
        portal["_RecordKey"].fillna("").astype(str).str.strip() != ""
    ].copy()

    if not portal_valid.empty:
        portal_valid = (
            portal_valid.sort_values("Sale Date Clean")
            .drop_duplicates(subset="_RecordKey", keep="last")
        )

    if not portal_valid.empty:
        merged = apps.merge(
            portal_valid,
            on="_RecordKey",
            how="left",
            suffixes=("", "_portal"),
        )
    else:
        merged = apps.copy()

    return merged


master_raw_df = build_master_dataframe(sparta_df, sparta2_df)

with st.spinner("Loading attendance data..."):
    attendance_df = load_attendance_data()

if not attendance_df.empty:
    attendance_df, attendance_agent_mapping = attach_attendance_advisors(
        attendance_df, master_raw_df
    )
else:
    attendance_agent_mapping = {}

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

source_status_text = (
    f"Source boundary: Excel / legacy through 17 Sep 2026 · "
    f"{source_status['legacy_app_rows']:,} application rows | "
    f"CRM from 18 Sep 2026 · {source_status['crm_app_rows']:,} application rows"
)
st.caption(source_status_text)

if attendance_df.empty:
    st.warning(
        "Attendance source unavailable. SPD will display '-' until the attendance sheet is available."
    )
else:
    st.caption(
        f"Attendance source connected · {attendance_df['Name'].nunique():,} people · "
        f"{attendance_df['Date Clean'].min().strftime('%d %b %Y')} to "
        f"{attendance_df['Date Clean'].max().strftime('%d %b %Y')}"
    )

if source_status["crm_error"]:
    st.warning(
        "CRM source warning: "
        + str(source_status["crm_error"])
        + " Historical Excel / legacy data is still available."
    )

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
# Projection weights (editable by user)
# ==========================================================
st.markdown("##### Projection weights (editable)")
proj_col1, proj_col2, proj_col3, proj_col4 = st.columns([1, 1, 1, 2])
with proj_col1:
    committed_pct_input = st.number_input("Committed weight %", min_value=0, max_value=100, value=60, step=1, help="Percent of committed expected to convert to Live")
with proj_col2:
    welcome_pending_pct_input = st.number_input("Welcome Pending weight %", min_value=0, max_value=100, value=35, step=1, help="Percent of Welcome Pending expected to convert to Live")
with proj_col3:
    quality_pending_pct_input = st.number_input("Quality Pending weight %", min_value=0, max_value=100, value=25, step=1, help="Percent of Quality Pending expected to convert to Live")
with proj_col4:
    st.markdown(
        f"""
        **Applied formula** (per row):  
        Projected Live = Live + ({committed_pct_input}% × Committed) + ({welcome_pending_pct_input}% × Welcome Pending) + ({quality_pending_pct_input}% × QA Pending)
        """
    )

committed_frac = committed_pct_input / 100.0
welcome_pending_frac = welcome_pending_pct_input / 100.0
quality_pending_frac = quality_pending_pct_input / 100.0

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

# ==========================================================
# MONTHLY KPI BREAKDOWN (SELECTABLE YEAR)
# with per-month + / - expandable daily breakdown
# ==========================================================
st.divider()
st.subheader("📅 Monthly KPI Breakdown")

current_year = datetime.now().year
years = list(range(2022, current_year + 1))
selected_year = st.selectbox("Select year for monthly breakdown", options=years, index=len(years) - 1)

# --- Agent dropdown for monthly table (default = All Agents)
agent_list = []
if "Advisor" in master_raw_df.columns:
    agent_list = sorted(master_raw_df["Advisor"].dropna().astype(str).unique(), key=lambda s: s.lower())
agent_options = ["All Agents"] + agent_list
selected_agent = st.selectbox("Select Agent (Monthly table)", options=agent_options, index=0)

# Build monthly application and portal frames for the selected year
monthly_app_df = master_raw_df.dropna(subset=["Period_Sort"]).copy()
monthly_app_df = monthly_app_df[monthly_app_df["Period_Sort"].dt.year == int(selected_year)]

monthly_portal_df = sparta2_df.dropna(subset=["Period_Sort"]).copy()
monthly_portal_df = monthly_portal_df[monthly_portal_df["Period_Sort"].dt.year == int(selected_year)]

# If an agent is selected, filter monthly_app_df by Agent and derive portal rows for that agent from master_raw_df (merged)
if selected_agent != "All Agents":
    agent_norm = selected_agent.strip().lower()

    if "Advisor" in monthly_app_df.columns:
        monthly_app_df = monthly_app_df[
            monthly_app_df["Advisor"].fillna("").astype(str).str.strip().str.lower() == agent_norm
        ].copy()
    else:
        monthly_app_df = monthly_app_df.iloc[0:0].copy()

    portal_from_master = master_raw_df.copy()
    if "Advisor" in portal_from_master.columns:
        portal_from_master = portal_from_master[
            portal_from_master["Advisor"].fillna("").astype(str).str.strip().str.lower() == agent_norm
        ].copy()
        portal_from_master = portal_from_master.dropna(subset=["Period_Sort"])
        portal_from_master = portal_from_master[portal_from_master["Period_Sort"].dt.year == int(selected_year)].copy()
        monthly_portal_df = portal_from_master
    else:
        monthly_portal_df = monthly_portal_df.iloc[0:0].copy()

# Periods represented by either applications or portal data
all_periods = sorted(
    list(set(monthly_app_df["Period_Sort"]).union(set(monthly_portal_df["Period_Sort"]))),
    reverse=True,
)

if not all_periods:
    st.info(f"No {selected_year} monthly data available for the KPI summary table.")
else:
    def build_kpi_row(display_label, m_app, m_portal, period_key, is_daily=False):
        """Build one monthly/daily KPI row using the same KPI definitions as the original table."""
        m_total_apps = len(m_app)

        if is_daily:
            if "Sale Date Clean" in m_app.columns and not m_app["Sale Date Clean"].dropna().empty:
                spd_day = m_app["Sale Date Clean"].dropna().iloc[0]
            else:
                spd_day = pd.to_datetime(display_label, errors="coerce", dayfirst=True)

            m_spd, m_working_days, m_present_days = get_daily_spd(
                attendance_df,
                spd_day,
                m_total_apps,
                selected_agent=selected_agent,
            )
        else:
            try:
                period_for_spd = pd.Period(str(period_key)[:6], freq="M")
            except Exception:
                period_for_spd = None

            m_spd, m_working_days, m_present_days = get_team_month_spd(
                attendance_df,
                period_for_spd,
                m_total_apps,
                selected_agent=selected_agent,
            )

        m_qa_approved = count_status(m_app, "Quality Status Clean", "Approved")
        m_qa_rework = count_status(m_app, "Quality Status Clean", "Rework")
        m_qa_cancelled = count_status(m_app, "Quality Status Clean", "Cancelled")
        m_qa_pending = count_status(m_app, "Quality Status Clean", "Pending")

        m_wc_done = count_status(m_app, "Welcome Status Clean", "Done")
        m_wc_cancelled = count_status(m_app, "Welcome Status Clean", "Cancelled")
        m_wc_pending = count_status(m_app, "Welcome Status Clean", "Pending")

        m_p_live = count_status(m_portal, "Portal Status Clean", "Live")

        # CRM-only committed semantics for the Monthly KPI Breakdown:
        # use Confirmation Status and ignore blanks. Legacy/Excel rows retain
        # their original Sparta2 Portal Status semantics.
        source_series = m_portal.get(
            "Source",
            pd.Series(index=m_portal.index, dtype=object),
        ).fillna("").astype(str).str.strip()
        legacy_portal = m_portal[source_series != "CRM"].copy()
        crm_portal = m_portal[source_series == "CRM"].copy()

        m_p_committed_legacy = count_status(
            legacy_portal, "Portal Status Clean", "Committed"
        )

        crm_confirmation_norm = pd.Series(index=crm_portal.index, dtype="string")
        if "Confirmation Status" in crm_portal.columns:
            crm_confirmation = (
                crm_portal["Confirmation Status"]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            crm_confirmation_norm = (
                crm_confirmation.str.lower()
                .str.replace(r"\s+", " ", regex=True)
                .str.strip()
            )
            m_p_committed_crm = int(
                crm_confirmation_norm.isin({
                    "confirmation approved",
                    "confirmation followup",
                    "confirmation follow-up",
                    "confirmation pending",
                }).sum()
            )
            m_p_committed_cancelled = int(
                (crm_confirmation_norm == "to be cancelled").sum()
            )
        else:
            m_p_committed_crm = 0
            m_p_committed_cancelled = 0

        m_p_committed = m_p_committed_legacy + m_p_committed_crm
        # Existing Live Cancelled remains based on the dashboard portal taxonomy.
        m_p_cancelled = count_status(m_portal, "Portal Status Clean", "Cancelled")

        qa_approved_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Approved")
        qa_rework_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Rework")
        qa_cancelled_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Cancelled")
        qa_pending_raw = format_raw_breakdown(m_app, "Quality Status", "Quality Status Clean", "Pending")

        welcome_done_raw = format_raw_breakdown(m_app, "Welcome Status", "Welcome Status Clean", "Done")
        welcome_cancelled_raw = format_raw_breakdown(m_app, "Welcome Status", "Welcome Status Clean", "Cancelled")
        welcome_pending_raw = format_raw_breakdown(m_app, "Welcome Status", "Welcome Status Clean", "Pending")

        legacy_committed_raw = format_raw_breakdown(
            legacy_portal, "Portal Status", "Portal Status Clean", "Committed"
        )
        crm_committed_raw = ""
        crm_committed_cancelled_raw = ""

        if "Confirmation Status" in crm_portal.columns:
            crm_conf_display = (
                crm_portal["Confirmation Status"]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            committed_mask = crm_confirmation_norm.isin({
                "confirmation approved",
                "confirmation followup",
                "confirmation follow-up",
                "confirmation pending",
            })
            committed_counts = crm_conf_display[committed_mask].value_counts()
            if not committed_counts.empty:
                lines = [f"{raw}: {count}" for raw, count in committed_counts.items()]
                crm_committed_raw = (
                    "CRM Confirmation Status Breakdown\n"
                    + "\n".join(lines)
                    + f"\nTotal: {int(committed_counts.sum())}"
                )

            cancelled_counts = crm_conf_display[
                crm_confirmation_norm == "to be cancelled"
            ].value_counts()
            if not cancelled_counts.empty:
                lines = [f"{raw}: {count}" for raw, count in cancelled_counts.items()]
                crm_committed_cancelled_raw = (
                    "CRM Confirmation Status Breakdown\n"
                    + "\n".join(lines)
                    + f"\nTotal: {int(cancelled_counts.sum())}"
                )

        raw_parts = [x for x in [legacy_committed_raw, crm_committed_raw] if x]
        committed_raw = "\n\n".join(raw_parts)

        live_raw = format_raw_breakdown(m_portal, "Portal Status", "Portal Status Clean", "Live")
        live_cancelled_raw = format_raw_breakdown(m_portal, "Portal Status", "Portal Status Clean", "Cancelled")

        m_projected = (
            m_p_live
            + (m_p_committed * committed_frac)
            + (m_wc_pending * welcome_pending_frac)
            + (m_qa_pending * quality_pending_frac)
        )

        projected_tooltip = (
            f"Formula: Live + ({committed_pct_input}% × Committed) + "
            f"({welcome_pending_pct_input}% × Welcome Pending) + ({quality_pending_pct_input}% × QA Pending)\n"
            f"Components:\nLive: {m_p_live}\nCommitted: {m_p_committed}\n"
            f"Welcome Pending: {m_wc_pending}\nQA Pending: {m_qa_pending}\n"
            f"Projected (rounded): {int(round(m_projected))}"
        )

        return {
            "MONTH": display_label,
            "PERIOD_KEY": period_key,
            "APPLICATIONS": m_total_apps,
            "WORKING DAYS": m_working_days,
            "PRESENT DAYS": m_present_days,
            "SPD": m_spd,
            "_SPD_DENOMINATOR": m_present_days,
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
            "COMMITTED CANCELLED": m_p_committed_cancelled,
            "COMMITTED CANCELLED RAW": crm_committed_cancelled_raw,
            "LIVE": m_p_live,
            "LIVE RAW": live_raw,
            "Live Conversion % Val": (m_p_live / m_total_apps * 100) if m_total_apps > 0 else 0.0,
            "LIVE CANCELLED": m_p_cancelled,
            "LIVE CANCELLED RAW": live_cancelled_raw,
            "PROJECTED LIVE": int(round(m_projected)),
            "PROJECTED LIVE RAW": projected_tooltip,
            "Projected Live % Val": (m_projected / m_total_apps * 100) if m_total_apps > 0 else 0.0,
        }

    # ----------------------------------------------------------
    # Build monthly rows AND daily rows for every calendar day.
    # Daily rows are stored separately and rendered hidden by default.
    # ----------------------------------------------------------
    monthly_rows = []
    daily_rows_by_period = {}

    for period in all_periods:
        month_start = period.to_timestamp()
        next_month = (period + 1).to_timestamp()
        month_app = monthly_app_df[monthly_app_df["Period_Sort"] == period].copy()
        month_portal = monthly_portal_df[monthly_portal_df["Period_Sort"] == period].copy()

        period_key = int(period.year) * 100 + int(period.month)
        monthly_rows.append(
            build_kpi_row(
                period.strftime("%B %Y"),
                month_app,
                month_portal,
                period_key,
            )
        )

        # Use the actual sale date as the day key. Include every calendar day in the month,
        # including zero-activity days, so the expanded month always shows a complete calendar.
        day_rows = []
        day = month_start
        while day < next_month:
            day_end = day + pd.Timedelta(days=1)
            day_app = month_app[
                (month_app["Sale Date Clean"] >= day) &
                (month_app["Sale Date Clean"] < day_end)
            ].copy() if "Sale Date Clean" in month_app.columns else month_app.iloc[0:0].copy()

            day_portal = month_portal[
                (month_portal["Sale Date Clean"] >= day) &
                (month_portal["Sale Date Clean"] < day_end)
            ].copy() if "Sale Date Clean" in month_portal.columns else month_portal.iloc[0:0].copy()

            day_key = int(day.strftime("%Y%m%d"))
            day_rows.append(
                build_kpi_row(
                    day.strftime("%d %b %Y"),
                    day_app,
                    day_portal,
                    day_key,
                    is_daily=True,
                )
            )
            day += pd.Timedelta(days=1)

        daily_rows_by_period[period_key] = day_rows

    monthly_summary_df = pd.DataFrame(monthly_rows)

    # ----------------------------------------------------------
    # Totals row — kept exactly on the monthly view and always
    # rendered at the bottom.
    # ----------------------------------------------------------
    if not monthly_summary_df.empty:
        tot_apps = monthly_summary_df["APPLICATIONS"].sum()
        totals_row = {
            "MONTH": "Total",
            "PERIOD_KEY": 999999,
            "APPLICATIONS": tot_apps,
            "WORKING DAYS": monthly_summary_df["WORKING DAYS"].sum(),
            "PRESENT DAYS": monthly_summary_df["PRESENT DAYS"].sum(),
            "SPD": (
                tot_apps / monthly_summary_df["PRESENT DAYS"].sum()
                if monthly_summary_df["PRESENT DAYS"].sum() > 0
                else 0.0
            ),
            "_SPD_DENOMINATOR": monthly_summary_df["PRESENT DAYS"].sum(),
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
            "COMMITTED RAW": "Aggregate committed breakdown shown in the monthly rows",
            "COMMITTED CANCELLED": monthly_summary_df["COMMITTED CANCELLED"].sum(),
            "COMMITTED CANCELLED RAW": "CRM Confirmation Status = To Be Cancelled",
            "LIVE": monthly_summary_df["LIVE"].sum(),
            "LIVE RAW": format_raw_breakdown(monthly_portal_df, "Portal Status", "Portal Status Clean", "Live"),
            "Live Conversion % Val": (monthly_summary_df["LIVE"].sum() / tot_apps * 100) if tot_apps > 0 else 0.0,
            "LIVE CANCELLED": monthly_summary_df["LIVE CANCELLED"].sum(),
            "LIVE CANCELLED RAW": format_raw_breakdown(monthly_portal_df, "Portal Status", "Portal Status Clean", "Cancelled"),
            "PROJECTED LIVE": int(round(
                monthly_summary_df["LIVE"].sum()
                + monthly_summary_df["COMMITTED REM."].sum() * committed_frac
                + monthly_summary_df["WELCOME PENDING"].sum() * welcome_pending_frac
                + monthly_summary_df["QA PENDING"].sum() * quality_pending_frac
            )),
            "PROJECTED LIVE RAW": (
                f"Aggregate projection using weights: {committed_pct_input}% committed, "
                f"{welcome_pending_pct_input}% welcome pending, {quality_pending_pct_input}% quality pending"
            ),
            "Projected Live % Val": ((
                monthly_summary_df["LIVE"].sum()
                + monthly_summary_df["COMMITTED REM."].sum() * committed_frac
                + monthly_summary_df["WELCOME PENDING"].sum() * welcome_pending_frac
                + monthly_summary_df["QA PENDING"].sum() * quality_pending_frac
            ) / tot_apps * 100) if tot_apps > 0 else 0.0,
        }
        monthly_summary_df = pd.concat(
            [monthly_summary_df, pd.DataFrame([totals_row])],
            ignore_index=True,
        )

    def render_pill(val_float: float, thresholds: List[float], good_bg: str = "#d1fae5"):
        val_str = f"{val_float:.1f}%"
        high, med = thresholds
        if val_float >= high:
            bg, color, border = "#d1fae5", "#047857", "#a7f3d0"
        elif val_float >= med:
            bg, color, border = "#fef3c7", "#b45309", "#fde68a"
        else:
            bg, color, border = "#ffe4e6", "#be123c", "#fecdd3"
        return (
            f'<span data-sort="{val_float:.6f}" style="background-color: {bg}; '
            f'color: {color}; border: 1px solid {border}; border-radius: 8px; '
            f'padding: 2px 8px; font-weight:700;">{val_str}</span>'
        )

    display_columns = [
        "MONTH", "APPLICATIONS", "WORKING DAYS", "PRESENT DAYS", "SPD", "QA APPROVED", "QA Pass Rate %",
        "QA REWORK", "QA CANCELLED", "QA PENDING", "WELCOME DONE",
        "Welcome Done %", "WELCOME CANCELLED", "WELCOME PENDING",
        "COMMITTED REM.", "COMMITTED CANCELLED", "LIVE", "Live Conversion %", "PROJECTED LIVE", "Projected Live %", "LIVE CANCELLED",
    ]

    m_header_styles = {
        "MONTH": "background-color: #f1f5f9; color: #334155;",
        "APPLICATIONS": "background-color: #eff6ff; color: #1e40af;",
        "WORKING DAYS": "background-color: #f8fafc; color: #475569;",
        "PRESENT DAYS": "background-color: #f0fdfa; color: #0f766e;",
        "SPD": "background-color: #e0f2fe; color: #0369a1;",
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
        "COMMITTED CANCELLED": "background-color: #fef2f2; color: #b91c1c;",
        "LIVE": "background-color: #f0fdfa; color: #0f766e;",
        "Live Conversion %": "background-color: #f0fdfa; color: #0f766e;",
        "PROJECTED LIVE": "background-color: #eef2ff; color: #3730a3;",
        "Projected Live %": "background-color: #eef2ff; color: #3730a3;",
        "LIVE CANCELLED": "background-color: #fef2f2; color: #b91c1c;",
    }

    monthly_tooltip_map = {
        "QA APPROVED": "QA APPROVED RAW",
        "QA REWORK": "QA REWORK RAW",
        "QA CANCELLED": "QA CANCELLED RAW",
        "QA PENDING": "QA PENDING RAW",
        "WELCOME DONE": "WELCOME DONE RAW",
        "WELCOME CANCELLED": "WELCOME CANCELLED RAW",
        "WELCOME PENDING": "WELCOME PENDING RAW",
        "COMMITTED REM.": "COMMITTED RAW",
        "COMMITTED CANCELLED": "COMMITTED CANCELLED RAW",
        "LIVE": "LIVE RAW",
        "LIVE CANCELLED": "LIVE CANCELLED RAW",
        "PROJECTED LIVE": "PROJECTED LIVE RAW",
    }

    # ----------------------------------------------------------
    # HTML table renderer helpers
    # ----------------------------------------------------------
    def render_monthly_data_cell(row, col_name, daily=False):
        """Render one data cell. Kept consistent with the original table."""
        if col_name == "MONTH":
            period_key = int(row.get("PERIOD_KEY", 0)) if pd.notna(row.get("PERIOD_KEY", None)) else 0
            cell_text = escape(str(row["MONTH"]))
            return f'<td data-sort="{period_key}">{cell_text}</td>'

        if col_name in {"WORKING DAYS", "PRESENT DAYS"}:
            val = float(row.get(col_name, 0.0) or 0.0)
            formatted = "-" if val <= 0 else (f"{val:.1f}" if abs(val - round(val)) > 1e-9 else f"{int(round(val)):,}")
            return f'<td data-sort="{val:.6f}">{formatted}</td>'

        if col_name == "SPD":
            val = float(row.get("SPD", 0.0) or 0.0)
            formatted = "-" if val <= 0 else f"{val:.2f}"
            return f'<td data-sort="{val:.6f}">{formatted}</td>'

        if col_name == "QA Pass Rate %":
            val = float(row["QA Pass Rate % Val"])
            return f'<td data-sort="{val:.6f}">{render_pill(val, thresholds=[75.0, 51.0])}</td>'

        if col_name == "Welcome Done %":
            val = float(row["Welcome Done % Val"])
            return f'<td data-sort="{val:.6f}">{render_pill(val, thresholds=[61.0, 51.0])}</td>'

        if col_name == "Live Conversion %":
            val = float(row["Live Conversion % Val"])
            return f'<td data-sort="{val:.6f}">{render_pill(val, thresholds=[41.0, 21.0])}</td>'

        if col_name == "PROJECTED LIVE":
            val = int(row.get("PROJECTED LIVE", 0))
            raw_text = row.get("PROJECTED LIVE RAW", "")
            if raw_text and val != 0:
                tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                return f'<td data-sort="{val}" title="{tooltip_html}" style="cursor:help;">{val:,}</td>'
            return f'<td data-sort="{val}">{val:,}</td>'

        if col_name == "Projected Live %":
            val = float(row.get("Projected Live % Val", 0.0))
            raw_text = row.get("PROJECTED LIVE RAW", "")
            pill_html = render_pill(val, thresholds=[41.0, 21.0])
            if raw_text and val != 0:
                tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                return f'<td data-sort="{val:.6f}" title="{tooltip_html}" style="cursor:help;">{pill_html}</td>'
            return f'<td data-sort="{val:.6f}">{pill_html}</td>'

        val = row.get(col_name, 0)
        raw_column = monthly_tooltip_map.get(col_name)
        raw_text = row.get(raw_column, "") if raw_column else ""

        if isinstance(val, (int, np.integer)):
            formatted_val = "-" if int(val) == 0 else f"{int(val):,}"
            if raw_text and int(val) != 0:
                tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                return f'<td data-sort="{int(val)}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
            return f'<td data-sort="{int(val)}">{formatted_val}</td>'

        formatted_val = "-" if (val == 0 or pd.isna(val)) else escape(str(val))
        if isinstance(val, float):
            if raw_text and val != 0:
                tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
                return f'<td data-sort="{val}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
            return f'<td data-sort="{val}">{formatted_val}</td>'

        if raw_text and str(val) not in ("0", "-", ""):
            tooltip_html = escape(str(raw_text)).replace("\n", "&#10;")
            return f'<td data-sort="{escape(str(val))}" title="{tooltip_html}" style="cursor:help;">{formatted_val}</td>'
        return f'<td data-sort="{escape(str(val))}">{formatted_val}</td>'

    # ----------------------------------------------------------
    # Build table HTML.
    # A month is a sortable group containing its monthly row + its
    # hidden daily rows. Clicking + toggles only that group.
    # ----------------------------------------------------------
    monthly_table_id = "monthly-kpi-table"
    table_height = min(700, max(200, 95 + (len(monthly_summary_df) * 45)))

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
        .monthly-kpi-table th.expand-head {{
            width: 48px;
            min-width: 48px;
            max-width: 48px;
            cursor: default;
            padding: 10px 6px;
        }}
        .monthly-kpi-table th:first-of-type + th {{
            text-align: left;
        }}
        .monthly-kpi-table td {{
            padding: 10px 14px;
            text-align: center;
            border-bottom: 1px solid #f1f5f9;
            border-right: 1px solid #f8fafc;
            color: #1e293b;
        }}
        .monthly-kpi-table td.month-label {{
            text-align: left;
            font-weight: 700;
            color: #0f172a;
            white-space: nowrap;
        }}
        .monthly-kpi-table tr.month-row {{
            background-color: #ffffff;
        }}
        .monthly-kpi-table tr.month-row:hover {{
            background-color: #f8fafc;
        }}
        .monthly-kpi-table tr.daily-row {{
            background-color: #f8fafc;
            display: none;
        }}
        .monthly-kpi-table tr.daily-row td {{
            padding-top: 8px;
            padding-bottom: 8px;
            font-size: 0.84rem;
        }}
        .monthly-kpi-table tr.daily-row td.month-label {{
            padding-left: 42px;
            font-weight: 600;
            color: #475569;
        }}
        .monthly-kpi-table tr.daily-row.shown {{
            display: table-row;
        }}
        .expand-button {{
            width: 26px;
            height: 26px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
            color: #334155;
            border-radius: 6px;
            font-size: 16px;
            line-height: 22px;
            font-weight: 700;
            cursor: pointer;
            padding: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }}
        .expand-button:hover {{
            background: #f1f5f9;
            border-color: #94a3b8;
        }}
        .daily-indent {{
            display: inline-block;
            width: 7px;
            border-left: 2px solid #cbd5e1;
            height: 14px;
            margin-right: 8px;
            vertical-align: -2px;
        }}
        .monthly-kpi-table tr.totals-row {{
            font-weight: 800;
            background-color: #f8fafc;
            border-top: 2px solid #cbd5e1;
        }}
        .monthly-kpi-table tr.totals-row td {{
            position: sticky;
            bottom: 0;
            background-color: #f8fafc;
            z-index: 4;
        }}
    </style>
    <div class="monthly-kpi-table-container">
      <div class="monthly-kpi-inner">
        <table id="{monthly_table_id}" class="monthly-kpi-table">
            <thead>
                <tr>
                    <th class="expand-head"></th>
    """

    for col_name in display_columns:
        th_style = m_header_styles.get(col_name, "background-color: #f8fafc; color: #475569;")
        m_html += f'<th style="{th_style}">{col_name}</th>'
    m_html += "</tr></thead><tbody>"

    for _, row in monthly_summary_df.iterrows():
        is_total = str(row.get("MONTH", "")).strip().lower() == "total"
        if is_total:
            m_html += '<tr class="totals-row">'
            m_html += '<td class="expand-cell"></td>'
            for col_name in display_columns:
                m_html += render_monthly_data_cell(row, col_name)
            m_html += "</tr>"
            continue

        period_key = int(row.get("PERIOD_KEY", 0))
        group_id = f"month-{period_key}"
        m_html += f'<tr class="month-row" data-group="{group_id}" data-month-sort="{period_key}">'
        m_html += (
            f'<td class="expand-cell">'
            f'<button type="button" class="expand-button" aria-expanded="false" '
            f'onclick="toggleMonth(\'{group_id}\', this)" title="Expand daily breakdown">+</button>'
            f'</td>'
        )

        for col_name in display_columns:
            cell_html = render_monthly_data_cell(row, col_name)
            if col_name == "MONTH":
                cell_html = cell_html.replace('<td ', '<td class="month-label" ', 1)
            m_html += cell_html
        m_html += "</tr>"

        # Daily rows are rendered immediately after their month row and are hidden by default.
        for daily_row in daily_rows_by_period.get(period_key, []):
            m_html += f'<tr class="daily-row" data-parent="{group_id}">'
            m_html += '<td class="expand-cell"></td>'
            for col_name in display_columns:
                cell_html = render_monthly_data_cell(daily_row, col_name, daily=True)
                if col_name == "MONTH":
                    # Visual indentation for daily rows.
                    label = escape(str(daily_row["MONTH"]))
                    cell_html = f'<td class="month-label"><span class="daily-indent"></span>{label}</td>'
                m_html += cell_html
            m_html += "</tr>"

    m_html += "</tbody></table></div></div>"

    # ----------------------------------------------------------
    # JS: per-month expansion + sortable month groups.
    # Sorting affects the monthly rows while keeping each month's
    # daily rows attached to that month. Totals remain at the bottom.
    # ----------------------------------------------------------
    m_html += f"""
    <script>
    (function() {{
        const table = document.getElementById("{monthly_table_id}");
        if (!table) return;
        const tbody = table.tBodies[0];

        window.toggleMonth = function(groupId, button) {{
            const rows = Array.from(tbody.querySelectorAll('tr.daily-row[data-parent="' + groupId + '"]'));
            const isExpanded = button.getAttribute('aria-expanded') === 'true';
            const willExpand = !isExpanded;

            rows.forEach(row => {{
                row.classList.toggle('shown', willExpand);
            }});

            button.setAttribute('aria-expanded', willExpand ? 'true' : 'false');
            button.textContent = willExpand ? '−' : '+';
            button.title = willExpand ? 'Collapse daily breakdown' : 'Expand daily breakdown';
        }};

        function sortValue(cell) {{
            if (!cell) return '';
            return cell.getAttribute('data-sort') || cell.innerText || '';
        }}

        function compareValues(aVal, bVal, order) {{
            const aNum = parseFloat(aVal.toString().replace(/,/g, ''));
            const bNum = parseFloat(bVal.toString().replace(/,/g, ''));
            if (!isNaN(aNum) && !isNaN(bNum)) {{
                return order === 'asc' ? aNum - bNum : bNum - aNum;
            }}
            return order === 'asc'
                ? aVal.toString().localeCompare(bVal.toString())
                : bVal.toString().localeCompare(aVal.toString());
        }}

        const headers = table.querySelectorAll('thead th');
        headers.forEach((th, headerIndex) => {{
            // First column is the expand/collapse control and is not sortable.
            if (headerIndex === 0) return;

            th.addEventListener('click', () => {{
                const current = th.getAttribute('data-order') || 'desc';
                const newOrder = current === 'asc' ? 'desc' : 'asc';
                headers.forEach(h => h.removeAttribute('data-order'));
                th.setAttribute('data-order', newOrder);

                const monthRows = Array.from(tbody.querySelectorAll('tr.month-row'));
                const totals = tbody.querySelector('tr.totals-row');

                monthRows.sort((a, b) => {{
                    // headerIndex is offset by one because of the expand column.
                    const aCell = a.children[headerIndex];
                    const bCell = b.children[headerIndex];
                    return compareValues(sortValue(aCell), sortValue(bCell), newOrder);
                }});

                monthRows.forEach(monthRow => {{
                    tbody.appendChild(monthRow);
                    const groupId = monthRow.getAttribute('data-group');
                    const children = Array.from(tbody.querySelectorAll('tr.daily-row[data-parent="' + groupId + '"]'));
                    children.forEach(child => tbody.appendChild(child));
                }});

                if (totals) tbody.appendChild(totals);
            }});
        }});
    }})();
    </script>
    """

    components.html(m_html, height=table_height, scrolling=False)

# ==========================================================
# PERFORMANCE TABLE SELECTOR
# Only one performance table is displayed at a time.
# ==========================================================
st.divider()
st.subheader("📊 Performance Breakdown")

performance_table_options = [
    "👥 Sales Executive Performance Breakdown",
    "🧪 Quality Officer Performance",
    "📞 Welcome Caller Performance",
]
selected_performance_table = st.radio(
    "Select performance table",
    options=performance_table_options,
    index=0,
    horizontal=True,
)

# ==========================================================
# ADVISOR PERFORMANCE MATRIX (with per-advisor tooltips, totals row, sticky header & sorting)
# Add PROJECTED LIVE and Projected Live % to advisor summary
# ==========================================================
if selected_performance_table == "👥 Sales Executive Performance Breakdown":
    st.divider()
    st.subheader("👥 Sales Executive Performance Breakdown")

if selected_performance_table == "👥 Sales Executive Performance Breakdown" and "Advisor" in master_df.columns and not master_df.empty:
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
        if not attendance_df.empty:
            perf_att = attendance_df[
                (attendance_df["Date Clean"].dt.date >= start_date)
                & (attendance_df["Date Clean"].dt.date <= end_date)
            ].copy()

            if selected_month != "All Months":
                perf_att = perf_att[
                    perf_att["Date Clean"].dt.strftime("%B %Y") == selected_month
                ]

            mapped_att = perf_att[
                perf_att["Dashboard Advisor"].fillna("").astype(str).str.strip() != ""
            ].copy()

            working_days_count = int(mapped_att["Date Clean"].dt.normalize().nunique()) if not mapped_att.empty else 0
            present_days_by_agent = (
                mapped_att.groupby("Dashboard Advisor")["Attendance Value"].sum()
                if not mapped_att.empty else pd.Series(dtype=float)
            )

            advisor_summary["WORKING DAYS"] = float(working_days_count)
            advisor_summary["PRESENT DAYS"] = (
                advisor_summary["Advisor"]
                .map(present_days_by_agent)
                .fillna(0.0)
            )
        else:
            advisor_summary["WORKING DAYS"] = 0.0
            advisor_summary["PRESENT DAYS"] = 0.0

        advisor_summary["SPD"] = np.where(
            advisor_summary["PRESENT DAYS"] > 0,
            advisor_summary["Applications"] / advisor_summary["PRESENT DAYS"],
            0.0,
        )

        advisor_summary["QA Pass Rate % Val"] = ((advisor_summary["QA_Approved"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Welcome Done % Val"] = ((advisor_summary["Welcome_Done"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Live Conversion % Val"] = ((advisor_summary["Live"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)

        advisor_summary["PROJECTED LIVE"] = (
            advisor_summary["Live"]
            + advisor_summary["Committed"] * committed_frac
            + advisor_summary["Welcome_Pending"] * welcome_pending_frac
            + advisor_summary["QA_Pending"] * quality_pending_frac
        ).round().astype(int)

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
            # Add projection tooltip for this advisor
            adv_proj_tooltip = (
                f"Formula: Live + ({committed_pct_input}% × Committed) + "
                f"({welcome_pending_pct_input}% × Welcome Pending) + ({quality_pending_pct_input}% × QA Pending)\n"
                f"Components:\nLive: {int(r.get('LIVE',0))}\nCommitted: {int(r.get('COMMITTED REM.',0))}\n"
                f"Welcome Pending: {int(r.get('WELCOME PENDING',0))}\nQA Pending: {int(r.get('QA PENDING',0))}\n"
                f"Projected (rounded): {int(r.get('PROJECTED LIVE',0))}"
            )
            adv_tooltips["PROJECTED LIVE"] = adv_proj_tooltip
            raw_tooltips[adv_display] = adv_tooltips
        # drop the helper column
        master_df.drop(columns=["_advisor_norm"], inplace=True, errors=True)

        numeric_cols = {
            "APPLICATIONS", "WORKING DAYS", "PRESENT DAYS", "SPD", "QA APPROVED", "QA REWORK", "QA CANCELLED", "QA PENDING",
            "WELCOME DONE", "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.", "LIVE", "LIVE CANCELLED", "PROJECTED LIVE"
        }

        base_col_order = [
            "SALES EXECUTIVE", "APPLICATIONS", "WORKING DAYS", "PRESENT DAYS", "SPD", "QA APPROVED", "QA Pass Rate %",
            "QA REWORK", "QA CANCELLED", "QA PENDING", "WELCOME DONE", "Welcome Done %",
            "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.",
            "LIVE", "Live Conversion %", "PROJECTED LIVE", "Projected Live %", "LIVE CANCELLED"
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
            "WORKING DAYS": "background-color:#f8fafc;color:#475569;",
            "PRESENT DAYS": "background-color:#f0fdfa;color:#0f766e;",
            "SPD": "background-color:#e0f2fe;color:#0369a1;",
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
            "PROJECTED LIVE": "background-color:#eef2ff;color:#3730a3;",
            "Projected Live %": "background-color:#eef2ff;color:#3730a3;",
            "Live Conversion %": "background-color:#f0fdfa;color:#0f766e;",
        }

        # Compute totals across visible advisors for numeric columns
        totals_series = advisor_summary[[c for c in advisor_summary.columns if c in numeric_cols]].sum(numeric_only=True)
        total_apps = int(totals_series.get("APPLICATIONS", 0))
        total_working_days = float(
            advisor_summary["WORKING DAYS"].sum()
            if "WORKING DAYS" in advisor_summary.columns
            else 0.0
        )
        total_present_days = float(
            advisor_summary["PRESENT DAYS"].sum()
            if "PRESENT DAYS" in advisor_summary.columns
            else 0.0
        )
        total_spd = (
            total_apps / total_present_days
            if total_present_days > 0
            else 0.0
        )
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
                elif c in {"WORKING DAYS", "PRESENT DAYS"}:
                    val = float(r.get(c, 0.0) or 0.0)
                    formatted = "-" if val <= 0 else (f"{val:.1f}" if abs(val - round(val)) > 1e-9 else f"{int(round(val)):,}")
                    adv_html += f'<td data-sort="{val:.6f}">{formatted}</td>'
                elif c == "SPD":
                    val = float(r.get("SPD", 0.0) or 0.0)
                    formatted = "-" if val <= 0 else f"{val:.2f}"
                    adv_html += f'<td data-sort="{val:.6f}">{formatted}</td>'
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
            elif c == "WORKING DAYS":
                formatted = "-" if total_working_days <= 0 else (f"{total_working_days:.1f}" if abs(total_working_days - round(total_working_days)) > 1e-9 else f"{int(round(total_working_days)):,}")
                adv_html += f'<td data-sort="{total_working_days:.6f}">{formatted}</td>'
            elif c == "PRESENT DAYS":
                formatted = "-" if total_present_days <= 0 else (f"{total_present_days:.1f}" if abs(total_present_days - round(total_present_days)) > 1e-9 else f"{int(round(total_present_days)):,}")
                adv_html += f'<td data-sort="{total_present_days:.6f}">{formatted}</td>'
            elif c == "SPD":
                formatted = "-" if total_spd <= 0 else f"{total_spd:.2f}"
                adv_html += f'<td data-sort="{total_spd:.6f}">{formatted}</td>'
            elif c == "QA Pass Rate %":
                adv_html += f'<td data-sort="{total_qa_pass_pct:.6f}">' + f'{render_qa_pill(total_qa_pass_pct)}</td>'
            elif c == "Welcome Done %":
                adv_html += f'<td data-sort="{total_welcome_pct:.6f}">' + f'{render_welcome_pill(total_welcome_pct)}</td>'
            elif c == "Live Conversion %":
                adv_html += f'<td data-sort="{total_live_pct:.6f}">' + f'{render_live_pill(total_live_pct)}</td>'
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
                tot_proj_pct = ( (advisor_summary["PROJECTED LIVE"].sum() / totals_series.get("APPLICATIONS", 1)) * 100 ) if totals_series.get("APPLICATIONS",0) > 0 else 0.0
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
elif selected_performance_table == "👥 Sales Executive Performance Breakdown":
    st.info("No sales records available for the selected date or month filter.")


# ==========================================================
# 🧪 QUALITY OFFICER PERFORMANCE (same performance layout and KPI calculations)
# Add PROJECTED LIVE and Projected Live % to performance summary
# ==========================================================
if selected_performance_table == "🧪 Quality Officer Performance":
    st.divider()
    st.subheader("🧪 Quality Officer Performance")

if selected_performance_table == "🧪 Quality Officer Performance" and "Quality Officer" in master_df.columns and not master_df.empty:
    advisor_summary = (
        master_df.groupby("Quality Officer", dropna=False)
            .agg(
                Applications=("Quality Officer", "count"),
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

    if advisor_summary.empty:
        st.info("No sales records match the selected tag filters.")
    else:
        advisor_summary["QA Pass Rate % Val"] = ((advisor_summary["QA_Approved"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Welcome Done % Val"] = ((advisor_summary["Welcome_Done"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Live Conversion % Val"] = ((advisor_summary["Live"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)

        advisor_summary["PROJECTED LIVE"] = (
            advisor_summary["Live"]
            + advisor_summary["Committed"] * committed_frac
            + advisor_summary["Welcome_Pending"] * welcome_pending_frac
            + advisor_summary["QA_Pending"] * quality_pending_frac
        ).round().astype(int)

        advisor_summary["Projected Live % Val"] = (
            (advisor_summary["PROJECTED LIVE"] / advisor_summary["Applications"].replace(0, np.nan)) * 100
        ).fillna(0.0)

        # 4. Rename columns to match display standards
        advisor_summary = advisor_summary.rename(columns={
            "Quality Officer": "Quality Officer",
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

        advisor_summary["Quality Officer"] = advisor_summary["Quality Officer"].replace("", "Unassigned").fillna("Unassigned")
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
        master_df["_advisor_norm"] = master_df["Quality Officer"].fillna("").astype(str).str.strip().str.lower()
        for _, r in advisor_summary.iterrows():
            adv_display = str(r["Quality Officer"])
            adv_norm = adv_display.strip().lower()
            subset = master_df[master_df["_advisor_norm"] == adv_norm]
            adv_tooltips = {}
            for k, (raw_col, clean_col, target_val) in advisor_tooltip_mapping.items():
                adv_tooltips[k] = format_raw_breakdown(subset, raw_col, clean_col, target_val)
            # Add projection tooltip for this advisor
            adv_proj_tooltip = (
                f"Formula: Live + ({committed_pct_input}% × Committed) + "
                f"({welcome_pending_pct_input}% × Welcome Pending) + ({quality_pending_pct_input}% × QA Pending)\n"
                f"Components:\nLive: {int(r.get('LIVE',0))}\nCommitted: {int(r.get('COMMITTED REM.',0))}\n"
                f"Welcome Pending: {int(r.get('WELCOME PENDING',0))}\nQA Pending: {int(r.get('QA PENDING',0))}\n"
                f"Projected (rounded): {int(r.get('PROJECTED LIVE',0))}"
            )
            adv_tooltips["PROJECTED LIVE"] = adv_proj_tooltip
            raw_tooltips[adv_display] = adv_tooltips
        # drop the helper column
        master_df.drop(columns=["_advisor_norm"], inplace=True, errors=True)

        numeric_cols = {
            "APPLICATIONS", "QA APPROVED", "QA REWORK", "QA CANCELLED", "QA PENDING",
            "WELCOME DONE", "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.", "LIVE", "LIVE CANCELLED", "PROJECTED LIVE"
        }

        base_col_order = [
            "Quality Officer", "APPLICATIONS", "QA APPROVED", "QA Pass Rate %",
            "QA REWORK", "QA CANCELLED", "QA PENDING", "WELCOME DONE", "Welcome Done %",
            "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.",
            "LIVE", "Live Conversion %", "PROJECTED LIVE", "Projected Live %", "LIVE CANCELLED"
        ]

        visible_cols = ["Quality Officer"]
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
            "Quality Officer": "background-color:#f1f5f9;color:#334155;",
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
            "PROJECTED LIVE": "background-color:#eef2ff;color:#3730a3;",
            "Projected Live %": "background-color:#eef2ff;color:#3730a3;",
            "Live Conversion %": "background-color:#f0fdfa;color:#0f766e;",
        }

        # Compute totals across visible advisors for numeric columns
        totals_series = advisor_summary[[c for c in advisor_summary.columns if c in numeric_cols]].sum(numeric_only=True)
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
        advisor_table_id = "quality-officer-perf-table"
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
            adv_display = str(r["Quality Officer"])
            adv_tooltips_local = raw_tooltips.get(adv_display, {})
            adv_html += "<tr>"
            for c in visible_cols:
                if c == "Quality Officer":
                    name = escape(str(r[c]))
                    lname = name.strip().lower()
                    tags_html = ""
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
            if c == "Quality Officer":
                adv_html += "<td data-sort='Total'>Total</td>"
            elif c == "QA Pass Rate %":
                adv_html += f'<td data-sort="{total_qa_pass_pct:.6f}">' + f'{render_qa_pill(total_qa_pass_pct)}</td>'
            elif c == "Welcome Done %":
                adv_html += f'<td data-sort="{total_welcome_pct:.6f}">' + f'{render_welcome_pill(total_welcome_pct)}</td>'
            elif c == "Live Conversion %":
                adv_html += f'<td data-sort="{total_live_pct:.6f}">' + f'{render_live_pill(total_live_pct)}</td>'
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
                tot_proj_pct = ( (advisor_summary["PROJECTED LIVE"].sum() / totals_series.get("APPLICATIONS", 1)) * 100 ) if totals_series.get("APPLICATIONS",0) > 0 else 0.0
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
elif selected_performance_table == "🧪 Quality Officer Performance":
    st.info("No sales records available for the selected date or month filter.")


# ==========================================================
# 📞 WELCOME CALLER PERFORMANCE (same performance layout and KPI calculations)
# Add PROJECTED LIVE and Projected Live % to performance summary
# ==========================================================
if selected_performance_table == "📞 Welcome Caller Performance":
    st.divider()
    st.subheader("📞 Welcome Caller Performance")

if selected_performance_table == "📞 Welcome Caller Performance" and "Welcome Call By" in master_df.columns and not master_df.empty:
    advisor_summary = (
        master_df.groupby("Welcome Call By", dropna=False)
            .agg(
                Applications=("Welcome Call By", "count"),
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

    if advisor_summary.empty:
        st.info("No sales records match the selected tag filters.")
    else:
        advisor_summary["QA Pass Rate % Val"] = ((advisor_summary["QA_Approved"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Welcome Done % Val"] = ((advisor_summary["Welcome_Done"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)
        advisor_summary["Live Conversion % Val"] = ((advisor_summary["Live"] / advisor_summary["Applications"].replace(0, np.nan)) * 100).fillna(0.0)

        advisor_summary["PROJECTED LIVE"] = (
            advisor_summary["Live"]
            + advisor_summary["Committed"] * committed_frac
            + advisor_summary["Welcome_Pending"] * welcome_pending_frac
            + advisor_summary["QA_Pending"] * quality_pending_frac
        ).round().astype(int)

        advisor_summary["Projected Live % Val"] = (
            (advisor_summary["PROJECTED LIVE"] / advisor_summary["Applications"].replace(0, np.nan)) * 100
        ).fillna(0.0)

        # 4. Rename columns to match display standards
        advisor_summary = advisor_summary.rename(columns={
            "Welcome Call By": "Welcome Call By",
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

        advisor_summary["Welcome Call By"] = advisor_summary["Welcome Call By"].replace("", "Unassigned").fillna("Unassigned")
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
        master_df["_advisor_norm"] = master_df["Welcome Call By"].fillna("").astype(str).str.strip().str.lower()
        for _, r in advisor_summary.iterrows():
            adv_display = str(r["Welcome Call By"])
            adv_norm = adv_display.strip().lower()
            subset = master_df[master_df["_advisor_norm"] == adv_norm]
            adv_tooltips = {}
            for k, (raw_col, clean_col, target_val) in advisor_tooltip_mapping.items():
                adv_tooltips[k] = format_raw_breakdown(subset, raw_col, clean_col, target_val)
            # Add projection tooltip for this advisor
            adv_proj_tooltip = (
                f"Formula: Live + ({committed_pct_input}% × Committed) + "
                f"({welcome_pending_pct_input}% × Welcome Pending) + ({quality_pending_pct_input}% × QA Pending)\n"
                f"Components:\nLive: {int(r.get('LIVE',0))}\nCommitted: {int(r.get('COMMITTED REM.',0))}\n"
                f"Welcome Pending: {int(r.get('WELCOME PENDING',0))}\nQA Pending: {int(r.get('QA PENDING',0))}\n"
                f"Projected (rounded): {int(r.get('PROJECTED LIVE',0))}"
            )
            adv_tooltips["PROJECTED LIVE"] = adv_proj_tooltip
            raw_tooltips[adv_display] = adv_tooltips
        # drop the helper column
        master_df.drop(columns=["_advisor_norm"], inplace=True, errors=True)

        numeric_cols = {
            "APPLICATIONS", "QA APPROVED", "QA REWORK", "QA CANCELLED", "QA PENDING",
            "WELCOME DONE", "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.", "LIVE", "LIVE CANCELLED", "PROJECTED LIVE"
        }

        base_col_order = [
            "Welcome Call By", "APPLICATIONS", "QA APPROVED", "QA Pass Rate %",
            "QA REWORK", "QA CANCELLED", "QA PENDING", "WELCOME DONE", "Welcome Done %",
            "WELCOME CANCELLED", "WELCOME PENDING", "COMMITTED REM.",
            "LIVE", "Live Conversion %", "PROJECTED LIVE", "Projected Live %", "LIVE CANCELLED"
        ]

        visible_cols = ["Welcome Call By"]
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
            "Welcome Call By": "background-color:#f1f5f9;color:#334155;",
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
            "PROJECTED LIVE": "background-color:#eef2ff;color:#3730a3;",
            "Projected Live %": "background-color:#eef2ff;color:#3730a3;",
            "Live Conversion %": "background-color:#f0fdfa;color:#0f766e;",
        }

        # Compute totals across visible advisors for numeric columns
        totals_series = advisor_summary[[c for c in advisor_summary.columns if c in numeric_cols]].sum(numeric_only=True)
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
        advisor_table_id = "welcome-caller-perf-table"
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
            adv_display = str(r["Welcome Call By"])
            adv_tooltips_local = raw_tooltips.get(adv_display, {})
            adv_html += "<tr>"
            for c in visible_cols:
                if c == "Welcome Call By":
                    name = escape(str(r[c]))
                    lname = name.strip().lower()
                    tags_html = ""
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
            if c == "Welcome Call By":
                adv_html += "<td data-sort='Total'>Total</td>"
            elif c == "QA Pass Rate %":
                adv_html += f'<td data-sort="{total_qa_pass_pct:.6f}">' + f'{render_qa_pill(total_qa_pass_pct)}</td>'
            elif c == "Welcome Done %":
                adv_html += f'<td data-sort="{total_welcome_pct:.6f}">' + f'{render_welcome_pill(total_welcome_pct)}</td>'
            elif c == "Live Conversion %":
                adv_html += f'<td data-sort="{total_live_pct:.6f}">' + f'{render_live_pill(total_live_pct)}</td>'
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
                tot_proj_pct = ( (advisor_summary["PROJECTED LIVE"].sum() / totals_series.get("APPLICATIONS", 1)) * 100 ) if totals_series.get("APPLICATIONS",0) > 0 else 0.0
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
elif selected_performance_table == "📞 Welcome Caller Performance":
    st.info("No sales records available for the selected date or month filter.")


# ==========================================================
# FOOTER
# ==========================================================
st.divider()
st.success("✅ Data loaded successfully")
st.caption(f"Dashboard refreshed at {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
