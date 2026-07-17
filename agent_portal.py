import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import plotly.express as px
import plotly.graph_objects as go 
import calendar
import math

st.set_page_config(page_title="Sparta Agent Portal", layout="wide")


st.markdown("""
    <style>
    .block-container { max-width: 98%; padding-top: 1.5rem; }
    h3 { margin-bottom: 0.5rem !important; font-size: 1.1rem !important; color: #1E3A8A; }
    .last-updated { font-size: 0.75rem; color: gray; text-align: right; }
    
    /* Improved Box Container - Modern & Subtle */
    .kpi-box {
        background-color: #F1F5F9; 
        padding: 15px;
        border-radius: 12px; 
        border: 1px solid #E2E8F0; 
        height: 100%;
        box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.05);
    }
    .box-label {
        font-size: 0.75rem;
        font-weight: 800;
        color: #475569;
        text-align: left;
        margin-bottom: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
        display: flex;
        align-items: center;
    }
    .box-label::before {
        content: "";
        display: inline-block;
        width: 4px;
        height: 12px;
        background: #1E3A8A;
        margin-right: 8px;
        border-radius: 2px;
    }

    /* KPI Card - Polished with Depth */
    .kpi-card {
        padding: 12px 5px;
        border-radius: 10px;
        text-align: center;
        background: white;
        border: 1px solid rgba(0,0,0,0.05);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        min-height: 85px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }

    .kpi-label { 
        font-size: 0.65rem; 
        color: #64748B; 
        font-weight: 700; 
        margin-bottom: 4px; 
        text-transform: uppercase; 
    }
    .kpi-value { 
        font-size: 1.2rem; 
        color: #0F172A; 
        font-weight: 800; 
        margin: 0; 
        line-height: 1; 
    }
    .kpi-pc { 
        font-size: 0.7rem; 
        color: #1E3A8A; 
        font-weight: 700; 
        margin-top: 4px;
        background: rgba(30, 58, 138, 0.1);
        display: inline-block;
        padding: 2px 6px;
        border-radius: 4px;
    }

    /* Insight Flags */
    .insight-container {
        display: flex;
        gap: 12px;
        overflow-x: auto;
        padding: 10px 5px 20px 5px;
    }
    .insight-card {
        background: #FFFFFF;
        border-left: 5px solid #1E3A8A;
        padding: 12px 16px;
        min-width: 220px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .insight-title { font-size: 0.7rem; font-weight: 800; color: #64748B; margin: 0; text-transform: uppercase; }
    .insight-phrase { font-size: 0.9rem; font-weight: 700; color: #1E3A8A; margin: 4px 0; }
    .insight-comment { font-size: 0.75rem; color: #475569; margin: 0; line-height: 1.3; }

    /* Tips Container styling */
    .tips-box {
        background-color: #FFFBEB;
        border-left: 6px solid #D97706;
        padding: 16px;
        border-radius: 8px;
        margin-top: 15px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .tips-title {
        font-size: 0.9rem;
        font-weight: bold;
        color: #92400E;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .tips-list {
        margin: 0;
        padding-left: 20px;
        color: #78350F;
        font-size: 0.85rem;
        line-height: 1.5;
    }
    </style>
""", unsafe_allow_html=True)

ACCESS_KEYS = st.secrets["agent_keys"]

def log_agent_login(agent_name):
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ])
        client = gspread.authorize(creds)
        ss = client.open_by_key('1R1nXJHnmsHQhisEDronG-DMo5tWeI3Ysh8TyQmKQ2fQ')
        try:
            log_sheet = ss.worksheet('Logs')
        except gspread.WorksheetNotFound:
            log_sheet = ss.add_worksheet(title="Logs", rows="1000", cols="3")
            log_sheet.append_row(["Timestamp", "Agent Name", "Action"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_sheet.append_row([timestamp, agent_name, "Login"])
    except:
        pass

def robust_date_parser(date_str):
    date_str = str(date_str).strip()
    try:
        if '/' in date_str: return pd.to_datetime(date_str, dayfirst=True)
        return pd.to_datetime(date_str)
    except: return pd.NaT

@st.cache_data(ttl=300)
def fetch_data():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=[
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ])
    client = gspread.authorize(creds)
    ss = client.open_by_key('1R1nXJHnmsHQhisEDronG-DMo5tWeI3Ysh8TyQmKQ2fQ')
    
    df1 = pd.DataFrame(ss.worksheet('Sparta').get_all_records())
    df1['Date_Parsed'] = pd.to_datetime(df1['Standardized_Date'], errors='coerce')
    df1['Advisor'] = df1['Advisor'].astype(str).str.strip().str.title()
    
    df2_raw = pd.DataFrame(ss.worksheet('Sparta2').get_all_records())
    df2_raw['Date_Parsed'] = df2_raw['Sale Date'].apply(robust_date_parser)
    df2_raw['Advisor'] = df2_raw['Agent'].astype(str).str.strip().str.title()

    try:
        meta = ss.worksheet('Meta').get_all_values()
        last_sync = meta[0][1]
    except:
        last_sync = "Unknown"
        
    return df1, df2_raw, last_sync

def map_quality(val):
    s = str(val).lower()
    if any(x in s for x in ['appr', 'pass']): return 'Approved'
    if any(x in s for x in ['rew', 'repro']): return 'Rework'
    if any(x in s for x in ['can']): return 'Cancelled'
    if any(x in s for x in ['rej']): return 'Rejected'
    return 'Others'

def map_portal(val):
    s = str(val).lower()
    if 'live' in s: return 'Live'
    if 'com' in s: return 'Committed'
    if any(x in s for x in ['can', 'rej']): return 'Cancelled'
    return 'Others'

def map_wc(val):
    s = str(val).lower().strip()
    if any(x in s for x in ['done', 'pass', 'comp']): return 'Done'
    if any(x in s for x in ['pend', 'pnd']): return 'Pending'
    if any(x in s for x in ['paper', 'ppw']): return 'Paperwork'
    if any(x in s for x in ['can', 'rej']): return 'Cancelled'
    return 'Others'

def render_kpi(label, value, total):
    lbl = label.lower()
    accent = "#94A3B8" 
    if "total" in lbl: accent = "#3B82F6"
    elif any(x in lbl for x in ["appr", "done", "live"]): accent = "#10B981"
    elif any(x in lbl for x in ["rew", "pend", "paper", "comm"]): accent = "#F59E0B"
    elif "can" in lbl or "rej" in lbl: accent = "#EF4444"
    
    percent = (value / total * 100) if total > 0 else 0
    pc_html = f'<div style="display:flex; justify-content:center;"><p class="kpi-pc">{percent:.1f}%</p></div>' if "total apps" not in lbl else ""
    
    st.markdown(f"""
        <div class="kpi-card" style="border-top: 4px solid {accent};">
            <p class="kpi-label">{label}</p>
            <p class="kpi-value">{value:,}</p>
            {pc_html}
        </div>
    """, unsafe_allow_html=True)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.agent_name = ""

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("https://raw.githubusercontent.com/dataanalystsparta-netizen/logos/refs/heads/main/sparta-telecom-squarelogo-1663578233108%20(1).jpg", width=65)
        st.title("Agent Portal")
        st.info("Please enter your access key to view your performance data.")
        user_key = st.text_input("Access Key", type="password")
        if st.button("Login", use_container_width=True):
            if user_key.upper() in ACCESS_KEYS:
                st.session_state.authenticated = True
                st.session_state.agent_name = ACCESS_KEYS[user_key.upper()]
                log_agent_login(ACCESS_KEYS[user_key.upper()])
                st.rerun()
            else:
                st.error("Invalid Access Key. Try again!")
else:
    agent = st.session_state.agent_name
    today_date = datetime.date.today()
    
    with st.sidebar:
        st.subheader(f"👤 {agent}")
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.agent_name = ""
            st.rerun()

    try:
        df1, df2_raw, last_sync = fetch_data()
        ag1 = df1[df1['Advisor'] == agent].copy()
        ag2 = df2_raw[df2_raw['Advisor'] == agent].copy()
        
        col_title, col_time = st.columns([3, 1])
        with col_title:
            t_col1, t_col2 = st.columns([0.15, 0.85])
            with t_col1:
                st.image("https://raw.githubusercontent.com/dataanalystsparta-netizen/logos/refs/heads/main/sparta-telecom-squarelogo-1663578233108%20(1).jpg", width=65)
            with t_col2:
                st.title(f"My Performance Dashboard")
                
        col_time.markdown(f"<p class='last-updated'>Data Last Synced:<br><b>{last_sync}</b></p>", unsafe_allow_html=True)

        st.write("---")
        col_a, col_b, _ = st.columns([1, 1, 3])
        start_date = col_a.date_input("Start Date", today_date.replace(day=1))
        end_date = col_b.date_input("End Date", today_date)

        ag1_filtered = ag1[(ag1['Date_Parsed'].dt.date >= start_date) & (ag1['Date_Parsed'].dt.date <= end_date)].copy()
        ag2_filtered = ag2[(ag2['Date_Parsed'].dt.date >= start_date) & (ag2['Date_Parsed'].dt.date <= end_date)].copy()
        
        ag1_filtered['Q_Status'] = ag1_filtered['Quality Status'].apply(map_quality)
        ag2_filtered['P_Status'] = ag2_filtered['Status'].apply(map_portal)
        wc_col = 'Status' if 'Status' in ag1_filtered.columns else 'Welcome call Status' if 'Welcome call Status' in ag1_filtered.columns else None
        if wc_col: ag1_filtered['WC_Clean'] = ag1_filtered[wc_col].apply(map_wc)

        # ---------------- CATEGORISED KPI BOXES ----------------
        total_apps = len(ag1_filtered)
        total_ag2 = len(ag2_filtered)
        
        group_1 = [("Total Apps", total_apps, total_apps)]
        group_2 = [
            ("Approved", len(ag1_filtered[ag1_filtered['Q_Status'] == 'Approved']), total_apps),
            ("Rework", len(ag1_filtered[ag1_filtered['Q_Status'] == 'Rework']), total_apps),
            ("Cancelled", len(ag1_filtered[ag1_filtered['Q_Status'] == 'Cancelled']), total_apps),
            ("Rejected", len(ag1_filtered[ag1_filtered['Q_Status'] == 'Rejected']), total_apps),
            ("Others", len(ag1_filtered[ag1_filtered['Q_Status'] == 'Others']), total_apps)
        ]
        group_3 = []
        if wc_col:
            group_3 = [
                ("WC Done", len(ag1_filtered[ag1_filtered['WC_Clean'] == 'Done']), total_apps),
                ("WC Pending", len(ag1_filtered[ag1_filtered['WC_Clean'] == 'Pending']), total_apps),
                ("WC Paperwork", len(ag1_filtered[ag1_filtered['WC_Clean'] == 'Paperwork']), total_apps),
                ("WC Cancelled", len(ag1_filtered[ag1_filtered['WC_Clean'] == 'Cancelled']), total_apps),
                ("WC Others", len(ag1_filtered[ag1_filtered['WC_Clean'] == 'Others']), total_apps)
            ]
        group_4 = [
            ("Live", len(ag2_filtered[ag2_filtered['P_Status'] == 'Live']), total_ag2 if total_ag2 > 0 else total_apps),
            ("Committed", len(ag2_filtered[ag2_filtered['P_Status'] == 'Committed']), total_ag2 if total_ag2 > 0 else total_apps),
            ("Cancelled", len(ag2_filtered[ag2_filtered['P_Status'] == 'Cancelled']), total_ag2 if total_ag2 > 0 else total_apps),
            ("Others", len(ag2_filtered[ag2_filtered['P_Status'] == 'Others']), total_ag2 if total_ag2 > 0 else total_apps)
        ]

        b1, b2, b3, b4 = st.columns([1.2, 2.5, 2.5, 2.2])
        with b1: 
            st.markdown('<div class="kpi-box"><p class="box-label">Overview</p>', unsafe_allow_html=True)
            render_kpi(group_1[0][0], group_1[0][1], group_1[0][2])
            st.markdown('</div>', unsafe_allow_html=True)
        with b2: 
            active_g2 = [k for k in group_2 if k[1] > 0]
            if active_g2:
                st.markdown('<div class="kpi-box"><p class="box-label">Quality Audit Status</p>', unsafe_allow_html=True)
                cols = st.columns(len(active_g2))
                for i, kpi in enumerate(active_g2):
                    with cols[i]: render_kpi(kpi[0], kpi[1], kpi[2])
                st.markdown('</div>', unsafe_allow_html=True)
        with b3: 
            active_g3_kpis = [k for k in group_3 if k[1] > 0]
            if active_g3_kpis:
                st.markdown('<div class="kpi-box"><p class="box-label">Welcome Call Status</p>', unsafe_allow_html=True)
                cols = st.columns(len(active_g3_kpis))
                for i, kpi in enumerate(active_g3_kpis):
                    with cols[i]: render_kpi(kpi[0], kpi[1], kpi[2])
                st.markdown('</div>', unsafe_allow_html=True)
        with b4: 
            active_g4 = [k for k in group_4 if k[1] > 0]
            if active_g4:
                st.markdown('<div class="kpi-box"><p class="box-label">Live Status</p>', unsafe_allow_html=True)
                cols = st.columns(len(active_g4))
                for i, kpi in enumerate(active_g4):
                    with cols[i]: render_kpi(kpi[0], kpi[1], kpi[2])
                st.markdown('</div>', unsafe_allow_html=True)

        # ---------------- INSIGHT FLAGS ----------------
        flags_html = ""
        
        if total_apps > 0:
            q_appr = len(ag1_filtered[ag1_filtered['Q_Status'] == 'Approved']) / total_apps
            q_can = len(ag1_filtered[ag1_filtered['Q_Status'] == 'Cancelled']) / total_apps
            q_rej = len(ag1_filtered[ag1_filtered['Q_Status'] == 'Rejected']) / total_apps
            q_rew = len(ag1_filtered[ag1_filtered['Q_Status'] == 'Rework']) / total_apps

            if q_appr > 0.60: flags_html += '<div class="insight-card" style="border-color:#10b981"><p class="insight-title">Quality</p><p class="insight-phrase">High Approval Rate</p><p class="insight-comment">Excellent pitch and quality compliance!</p></div>'
            elif q_appr < 0.60: flags_html += '<div class="insight-card" style="border-color:#ef4444"><p class="insight-title">Quality</p><p class="insight-phrase">Low Approval Rate</p><p class="insight-comment">Review the quality guidelines to increase quality approval!</p></div>'
            
            if q_can > 0.40: flags_html += '<div class="insight-card" style="border-color:#f59e0b"><p class="insight-title">Quality</p><p class="insight-phrase">High Cancellation</p><p class="insight-comment">High Quality Cancellations, review the quality guidelines!</p></div>'
            if q_rej > 0.20: flags_html += '<div class="insight-card" style="border-color:#ef4444"><p class="insight-title">Quality</p><p class="insight-phrase">High Rejection</p><p class="insight-comment">High Quality Rejections! Pay attention to quality guidelines!</p></div>'
            if q_rew > 0.30: flags_html += '<div class="insight-card" style="border-color:#3b82f6"><p class="insight-title">Quality</p><p class="insight-phrase">Frequent Reworks</p><p class="insight-comment">Pay closer attention to quality guidelines, to avoid large number of Quality Reworks.</p></div>'

            if wc_col:
                wc_done = len(ag1_filtered[ag1_filtered['WC_Clean'] == 'Done']) / total_apps
                wc_can = len(ag1_filtered[ag1_filtered['WC_Clean'] == 'Cancelled']) / total_apps
                if wc_done < 0.70: flags_html += '<div class="insight-card" style="border-color:#f59e0b"><p class="insight-title">Welcome Call</p><p class="insight-phrase">Low Completion</p><p class="insight-comment">Address customer requirements closely to increase Welcome call approvals!</p></div>'
                if wc_can > 0.15: flags_html += '<div class="insight-card" style="border-color:#ef4444"><p class="insight-title">Welcome Call</p><p class="insight-phrase">High WC Cancellation</p><p class="insight-comment">Address customer doubts in the sales call to avoid Welcome call cancellations!</p></div>'

        if total_ag2 > 0:
            l_live = len(ag2_filtered[ag2_filtered['P_Status'] == 'Live']) / total_ag2
            l_can = len(ag2_filtered[ag2_filtered['P_Status'] == 'Cancelled']) / total_ag2
            if l_live > 0.20: flags_html += '<div class="insight-card" style="border-color:#10b981"><p class="insight-title">Live Stage</p><p class="insight-phrase">Strong Conversion</p><p class="insight-comment">Good live rate! Great overall quality of applications!</p></div>'
            elif l_live < 0.20: flags_html += '<div class="insight-card" style="border-color:#f59e0b"><p class="insight-title">Live Stage</p><p class="insight-phrase">Low Live Rate</p><p class="insight-comment">Identify bottlenecks preventing sales from going live.</p></div>'
            if l_can > 0.65: flags_html += '<div class="insight-card" style="border-color:#ef4444"><p class="insight-title">Live Stage</p><p class="insight-phrase">High Final Loss</p><p class="insight-comment">Large drops between applications and Committed. Identify bottlenecks!</p></div>'

        if flags_html:
            st.write("")
            st.subheader("💡 Points to Look Out For")
            st.markdown(f'<div class="insight-container">{flags_html}</div>', unsafe_allow_html=True)

        st.write("---")

        st.subheader("📅 Data Breakdown")
        ag1_filtered['Date'] = ag1_filtered['Date_Parsed'].dt.date
        ag2_filtered['Date'] = ag2_filtered['Date_Parsed'].dt.date
        view_mode = st.radio("View tables by:", ["Daily", "Monthly"], horizontal=True)
        
        if view_mode == "Daily":
            ag1_filtered['Period'] = ag1_filtered['Date_Parsed'].dt.date
            ag2_filtered['Period'] = ag2_filtered['Date_Parsed'].dt.date
            chart_group_col = 'Date'
        else:
            ag1_filtered['Period'] = ag1_filtered['Date_Parsed'].dt.strftime('%Y-%m')
            ag2_filtered['Period'] = ag2_filtered['Date_Parsed'].dt.strftime('%Y-%m')
            chart_group_col = 'Period'
        
        ca, cb, cc, cd = st.columns(4)
        with ca:
            st.markdown("##### Applications")
            if not ag1_filtered.empty:
                period_apps = ag1_filtered.groupby('Period').size().to_frame('Total Apps')
                vmax_apps = max(period_apps.max().max(), 1.1)
                styled_apps = period_apps.style.format(lambda x: "-" if x == 0 else x).background_gradient(cmap='Greens', vmin=1, vmax=vmax_apps).map(lambda x: 'background-color: transparent' if x == 0 else '')
                st.dataframe(styled_apps, use_container_width=True)
        with cb:
            st.markdown("##### Quality Audit Result")
            if not ag1_filtered.empty:
                period_qual = ag1_filtered.groupby(['Period', 'Q_Status']).size().unstack(fill_value=0)
                qual_order = ['Approved', 'Rework', 'Cancelled', 'Rejected', 'Others']
                period_qual = period_qual.reindex(columns=qual_order, fill_value=0)
                period_qual = period_qual.loc[:, (period_qual != 0).any(axis=0)]
                if not period_qual.empty:
                    vmax_qual = max(period_qual.max().max(), 1.1)
                    styled_qual = period_qual.style.format(lambda x: "-" if x == 0 else x).background_gradient(cmap='Greens', subset=pd.IndexSlice[:, period_qual.columns.intersection(['Approved'])], vmin=1, vmax=vmax_qual).background_gradient(cmap='Wistia', subset=pd.IndexSlice[:, period_qual.columns.intersection(['Rework'])], vmin=1, vmax=vmax_qual).background_gradient(cmap='Reds', subset=pd.IndexSlice[:, period_qual.columns.intersection(['Cancelled', 'Rejected'])], vmin=1, vmax=vmax_qual).map(lambda x: 'background-color: transparent' if x == 0 else '')
                    st.dataframe(styled_qual, use_container_width=True)
        with cc:
            st.markdown("##### Welcome Call Status")
            if wc_col and not ag1_filtered.empty:
                period_wc = ag1_filtered.groupby(['Period', 'WC_Clean']).size().unstack(fill_value=0)
                wc_order = ['Done', 'Pending', 'Paperwork', 'Cancelled', 'Others']
                period_wc = period_wc.reindex(columns=wc_order, fill_value=0)
                period_wc = period_wc.loc[:, (period_wc != 0).any(axis=0)]
                if not period_wc.empty:
                    vmax_wc = max(period_wc.max().max(), 1.1)
                    styled_wc = period_wc.style.format(lambda x: "-" if x == 0 else x).background_gradient(cmap='Greens', subset=pd.IndexSlice[:, period_wc.columns.intersection(['Done'])], vmin=1, vmax=vmax_wc).background_gradient(cmap='Wistia', subset=pd.IndexSlice[:, period_wc.columns.intersection(['Pending', 'Paperwork'])], vmin=1, vmax=vmax_wc).background_gradient(cmap='Reds', subset=pd.IndexSlice[:, period_wc.columns.intersection(['Cancelled'])], vmin=1, vmax=vmax_wc).map(lambda x: 'background-color: transparent' if x == 0 else '')
                    st.dataframe(styled_wc, use_container_width=True)
            else: st.info("No Welcome Call data.")
        with cd:
            st.markdown("##### Live Status")
            if not ag2_filtered.empty:
                period_port = ag2_filtered.groupby(['Period', 'P_Status']).size().unstack(fill_value=0)
                port_order = ['Live', 'Committed', 'Cancelled', 'Others']
                period_port = period_port.reindex(columns=port_order, fill_value=0)
                period_port = period_port.loc[:, (period_port != 0).any(axis=0)]
                if not period_port.empty:
                    vmax_port = max(period_port.max().max(), 1.1)
                    styled_port = period_port.style.format(lambda x: "-" if x == 0 else x).background_gradient(cmap='Greens', subset=pd.IndexSlice[:, period_port.columns.intersection(['Live'])], vmin=1, vmax=vmax_port).background_gradient(cmap='Wistia', subset=pd.IndexSlice[:, period_port.columns.intersection(['Committed'])], vmin=1, vmax=vmax_port).background_gradient(cmap='Reds', subset=pd.IndexSlice[:, period_port.columns.intersection(['Cancelled'])], vmin=1, vmax=vmax_port).map(lambda x: 'background-color: transparent' if x == 0 else '')
                    st.dataframe(styled_port, use_container_width=True)

        st.write("---")

        # ---------------- TRENDS & CALENDAR WITH DISPOSITION TIPS ----------------
        col_trend, col_cal = st.columns([3, 2])
        with col_trend:
            st.subheader("📈 My Trend")
            if not ag1_filtered.empty:
                d_apps = ag1_filtered.groupby(chart_group_col).size().to_frame('Total Apps')
                d_appr = ag1_filtered[ag1_filtered['Q_Status'] == 'Approved'].groupby(chart_group_col).size().to_frame('Approved')
                d_live = ag2_filtered[ag2_filtered['P_Status'] == 'Live'].groupby(chart_group_col).size().to_frame('Live')
                i_comb = d_apps.join([d_appr, d_live], how='left').fillna(0).reset_index()
                i_comb[chart_group_col] = i_comb[chart_group_col].astype(str)
                fig = go.Figure()
                fig.add_trace(go.Bar(x=i_comb[chart_group_col], y=i_comb['Total Apps'], name="Total Applications", marker_color='#60A5FA'))
                fig.add_trace(go.Scatter(x=i_comb[chart_group_col], y=i_comb['Approved'], name="Quality Approved Applications", line=dict(color='#059669', width=3)))
                fig.add_trace(go.Scatter(x=i_comb[chart_group_col], y=i_comb['Live'], name="Live Applications", line=dict(color='#F59E0B', width=3)))
                fig.update_layout(hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0), xaxis_title="Date" if view_mode=="Daily" else "Month")
                st.plotly_chart(fig, use_container_width=True)

        with col_cal:
            st.subheader("🗓️ Sales Activity Calendar")
            
            def is_holiday(dt):
                wd = dt.weekday() # 0=Mon, 6=Sun
                if wd == 6: return True 
                if wd == 5: 
                    week_num = (dt.day - 1) // 7 + 1
                    return week_num in [1, 3, 5] 
                return False

            c_month_col, c_year_col = st.columns(2)
            sel_month = c_month_col.selectbox("Month", list(calendar.month_name)[1:], index=today_date.month-1)
            sel_year = c_year_col.selectbox("Year", [2025, 2026], index=1)
            
            m_idx = list(calendar.month_name).index(sel_month)
            num_days = calendar.monthrange(sel_year, m_idx)[1]
            dates = [datetime.date(sel_year, m_idx, day) for day in range(1, num_days+1)]
            
            daily_sales = ag1.groupby(ag1['Date_Parsed'].dt.date).size()
            cal_df = pd.DataFrame({
                'Date': dates,
                'Day': [d.day for d in dates],
                'Weekday': [d.strftime('%a') for d in dates],
                'WeekNum': [int(d.strftime('%V')) if d.strftime('%V').isdigit() else 0 for d in dates],
                'Sales': [daily_sales.get(d, 0) for d in dates],
                'Type': ['Holiday' if is_holiday(d) else 'Working' for d in dates]
            })

            cal_df['HoverText'] = cal_df.apply(lambda r: "Holiday" if r['Type'] == 'Holiday' else f"{r['Sales']}", axis=1)

            fig_cal = go.Figure()
            working_days = cal_df[cal_df['Type'] == 'Working']
            fig_cal.add_trace(go.Heatmap(
                x=working_days['Weekday'], y=working_days['WeekNum'], z=working_days['Sales'],
                text=working_days['Day'], 
                customdata=working_days['HoverText'],
                hovertemplate="%{customdata}<extra></extra>",
                texttemplate="%{text}",
                colorscale=[[0, 'white'], [0.1, '#d1fae5'], [1, '#047857']],
                showscale=False, xgap=3, ygap=3
            ))

            holidays = cal_df[cal_df['Type'] == 'Holiday']
            fig_cal.add_trace(go.Scatter(
                x=holidays['Weekday'], y=holidays['WeekNum'], mode='markers+text',
                marker=dict(symbol='square', size=35, color='#ADD8E6'),
                text=holidays['Day'], 
                customdata=holidays['HoverText'],
                hovertemplate="%{customdata}<extra></extra>",
                textfont=dict(color='#94A3B8'),
                showlegend=False
            ))

            fig_cal.update_layout(
                height=300, margin=dict(l=0, r=0, t=10, b=10),
                xaxis=dict(side="top", categoryorder='array', categoryarray=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']),
                yaxis=dict(autorange="reversed", showgrid=False, zeroline=False, showticklabels=False),
                plot_bgcolor='white'
            )
            st.plotly_chart(fig_cal, use_container_width=True)
            st.caption("🟢 Sales | ⚪ No Sales | 🔵 Holiday ")

        st.write("---")

        # ---------------- RECENT APPLICATIONS LOG WITH SECTIONS ----------------
        st.subheader("🔍 Recent Applications Log")
        if not ag1.empty:
            ag2_clean = ag2.copy()
            ag2_clean['Telephone No.'] = ag2_clean['Telephone No.'].astype(str).str.strip()
            ag2_clean = ag2_clean.rename(columns={'Status': 'Portal Status', 'Committed Date': 'Live Date'})
            ag2_unique = ag2_clean.sort_values('Date_Parsed').drop_duplicates('Telephone No.', keep='last')
            
            ag1_log_base = ag1.copy()
            ag1_log_base['CLI_Key'] = ag1_log_base['CLI'].astype(str).str.strip()
            merged_log = ag1_log_base.merge(
                ag2_unique[['Telephone No.', 'LetterStatus', 'CallStatus', 'Comments', 'Voice of Customer', 'Cancellation Reason', 'Portal Status', 'Live Date']],
                left_on='CLI_Key', 
                right_on='Telephone No.', 
                how='left'
            )

            # --- RENAME AND CLEANUP RECENT LOG DATE COLUMNS TO DD-MM-YYYY STRING ---
            merged_log['Sale Date'] = pd.to_datetime(merged_log['Standardized_Date'], errors='coerce').dt.strftime('%d-%m-%Y').fillna('')
            merged_log['Live Date'] = pd.to_datetime(merged_log['Live Date'], errors='coerce').dt.strftime('%d-%m-%Y').fillna('')

            columns_layout = [
                ('Basic Info.', 'S.No.'),
                ('Basic Info.', 'Sale Date'),
                ('Basic Info.', 'Customer Name'),
                ('Quality Audit', 'Quality Status'),
                ('Quality Audit', 'Quality Remarks'),
                ('Welcome Call', 'Status'),
                ('Welcome Call', 'Welcome call Remarks'),
                ('Live Status', 'LetterStatus'),
                ('Live Status', 'CallStatus'),
                ('Live Status', 'Portal Status'),
                ('Live Status', 'Live Date'),
                ('Live Status', 'Comments'),
                ('Live Status', 'Voice of Customer'),
                ('Live Status', 'Cancellation Reason')
            ]
            
            # --- CUSTOM DATE RANGE, ALL RECORDS & LIMIT CONTROLS ---
            log_col1, log_col2, log_col3 = st.columns([1.8, 2.2, 1])
            with log_col1:
                log_filter_type = st.radio("Log View Filter:", ["All Applications", "By Specific Date Range", "By Specific Month"], horizontal=True)
            with log_col2:
                if log_filter_type == "By Specific Date Range":
                    ld_col1, ld_col2 = st.columns(2)
                    log_start = ld_col1.date_input("Log Start Date", today_date.replace(day=1), key="log_start_date")
                    log_end = ld_col2.date_input("Log End Date", today_date, key="log_end_date")
                    recent_log = merged_log[(merged_log['Date_Parsed'].dt.date >= log_start) & (merged_log['Date_Parsed'].dt.date <= log_end)].sort_values(by='Date_Parsed', ascending=False)
                elif log_filter_type == "By Specific Month":
                    unique_months = sorted(merged_log['Date_Parsed'].dt.strftime('%Y-%m').dropna().unique(), reverse=True)
                    if unique_months:
                        selected_month = st.selectbox("Select Month for Log (YYYY-MM):", unique_months)
                        recent_log = merged_log[merged_log['Date_Parsed'].dt.strftime('%Y-%m') == selected_month].sort_values(by='Date_Parsed', ascending=False)
                    else:
                        recent_log = merged_log[0:0]
                else:
                    recent_log = merged_log.sort_values(by='Date_Parsed', ascending=False)

            recent_log['S.No.'] = range(1, len(recent_log) + 1)

            with log_col3:
                row_limit = st.selectbox("Show records per page:", [5, 10, 20, 50, 100, "All"], index=2)

            valid_layout = [item for item in columns_layout if item[1] in recent_log.columns]
            display_df = recent_log[[item[1] for item in valid_layout]].copy()
            display_df.columns = pd.MultiIndex.from_tuples(valid_layout)

            table_container = st.container()

            # --- Pagination Layout Config ---
            if "current_page" not in st.session_state:
                st.session_state.current_page = 1

            if row_limit != "All":
                limit = int(row_limit)
                total_records = len(display_df)
                total_pages = max(1, math.ceil(total_records / limit))
                
                # Safety check if records shrink from dynamic filtering
                if st.session_state.current_page > total_pages:
                    st.session_state.current_page = 1
                
                start_idx = (st.session_state.current_page - 1) * limit
                end_idx = min(start_idx + limit, total_records)
                display_df_page = display_df.iloc[start_idx:end_idx]
                
                if total_pages > 1:
                    st.write("")
                    pag_col1, pag_col2 = st.columns([1, 1])
                    with pag_col1:
                        st.markdown(f"<p style='color: #475569; font-size: 0.85rem; margin-top: 6px;'>Showing {start_idx + 1} to {end_idx} of {total_records} entries</p>", unsafe_allow_html=True)
                    with pag_col2:
                        b_col1, b_col2, b_col3 = st.columns([2, 1, 1])
                        with b_col1:
                            st.markdown(f"<p style='text-align: right; color: #475569; font-size: 0.85rem; margin-top: 6px;'>Page {st.session_state.current_page} of {total_pages}</p>", unsafe_allow_html=True)
                        with b_col2:
                            if st.button("Previous", disabled=(st.session_state.current_page == 1), use_container_width=True, key="prev_pg_action"):
                                st.session_state.current_page -= 1
                                st.rerun()
                        with b_col3:
                            if st.button("Next", disabled=(st.session_state.current_page == total_pages), use_container_width=True, key="next_pg_action"):
                                st.session_state.current_page += 1
                                st.rerun()
                else:
                    display_df_page = display_df
            else:
                display_df_page = display_df

            def style_log_row(row):
                styles = [''] * len(row)
                
                def get_val(col_name):
                    for col in row.index:
                        if col[1] == col_name: return str(row[col]).lower()
                    return ""

                DARK_GREEN = '#065F46'
                DARK_AMBER = '#92400E'
                DARK_RED = '#991B1B'

                BG_GREEN = 'rgba(16, 185, 129, 0.3)'
                BG_AMBER = 'rgba(245, 158, 11, 0.3)'
                BG_RED   = 'rgba(239, 68, 68, 0.3)'

                q_val = get_val('Quality Status')
                q_bg, q_txt = '', ''
                if any(x in q_val for x in ['appr', 'pass']):
                    q_bg, q_txt = BG_GREEN, DARK_GREEN
                elif any(x in q_val for x in ['rew', 'repro']):
                    q_bg, q_txt = BG_AMBER, DARK_AMBER
                elif any(x in q_val for x in ['can', 'rej']):
                    q_bg, q_txt = BG_RED, DARK_RED
                q_style = f'background-color: {q_bg}; color: {q_txt}; font-weight: bold;' if q_bg else ''

                wc_val = get_val('Status')
                wc_bg, wc_txt = '', ''
                if any(x in wc_val for x in ['done', 'pass', 'comp', 'live']):
                    wc_bg, wc_txt = BG_GREEN, DARK_GREEN
                elif any(x in wc_val for x in ['pend', 'pnd', 'paper', 'ppw', 'com']):
                    wc_bg, wc_txt = BG_AMBER, DARK_AMBER
                elif any(x in wc_val for x in ['can', 'rej']):
                    wc_bg, wc_txt = BG_RED, DARK_RED
                wc_style = f'background-color: {wc_bg}; color: {wc_txt}; font-weight: bold;' if wc_bg else ''

                call_val = get_val('CallStatus')
                c_bg, c_txt = '', ''
                if 'satisfied' in call_val:
                    c_bg, c_txt = BG_GREEN, DARK_GREEN
                elif any(x in call_val for x in ['pend', 'cancel']):
                    c_bg, c_txt = BG_RED, DARK_RED
                c_style = f'background-color: {c_bg}; color: {c_txt}; font-weight: bold;' if c_bg else ''
                
                portal_val = get_val('Portal Status')
                p_bg, p_txt = '', ''
                if 'live' in portal_val:
                    p_bg, p_txt = BG_GREEN, DARK_GREEN
                elif 'committed' in portal_val:
                    p_bg, p_txt = BG_AMBER, DARK_AMBER
                elif any(x in portal_val for x in ['rej', 'cancel']):
                    p_bg, p_txt = BG_RED, DARK_RED
                p_style = f'background-color: {p_bg}; color: {p_txt}; font-weight: bold;' if p_bg else ''

                quality_cols = ['S.No.', 'Sale Date', 'Customer Name', 'Quality Status', 'Quality Remarks']
                portal_group = ['Portal Status', 'Live Date', 'Comments', 'Voice of Customer', 'Cancellation Reason']
                
                for i, col_tuple in enumerate(row.index):
                    col = col_tuple[1] 
                    current_style = ""
                    
                    if col == 'LetterStatus':
                        current_style = 'background-color: rgba(59, 130, 246, 0.3);'
                    elif col == 'CallStatus':
                        current_style = c_style
                    elif col in portal_group:
                        if col == 'Portal Status':
                            current_style = p_style
                        else:
                            current_style = f'background-color: {p_bg};' if p_bg else ''
                    elif col in quality_cols:
                        if col == 'Quality Status':
                            current_style = q_style
                        else:
                            current_style = f'background-color: {q_bg};' if q_bg else ''
                    else:
                        if col == 'Status':
                            current_style = wc_style
                        else:
                            current_style = f'background-color: {wc_bg};' if wc_bg else ''
                    
                    if col == 'S.No.':
                        current_style += 'border-left: 3px solid #1E3A8A;'
                    
                    if col in ['Customer Name', 'Quality Remarks', 'Welcome call Remarks', 'Cancellation Reason']:
                        current_style += 'border-right: 3px solid #1E3A8A;'
                    
                    styles[i] = current_style
                return styles           
            
            styled_log = display_df_page.style.apply(style_log_row, axis=1)
            
            with table_container:
                st.dataframe(styled_log, use_container_width=True, hide_index=True)

        # ------------ DISPOSITION PERFORMANCE TIPS ---
        st.markdown("""
            <div class="tips-box">
                <div class="tips-title">💡 Performance Tips: Correct Call Dispositions and Data Quality</div>
                <ul class="tips-list">
                    <li><b>Answering Machines:</b> Do not dispose active customer connections as an "Answering Machine" especially if the Customer Talk Time/connectivity exceeds 30 seconds. Use it primarily when you hear a pre-recorded Answering Machine/Voicemail message.</li>
                    <li><b>Customer Hangup:</b>This disposition should be used when the customer abruptly hangsup. Should be used for active/connected customers. </li>
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
        """, unsafe_allow_html=True)
        st.write("---")

    except Exception as e: st.error(f"Error: {e}")
