import streamlit as st
import pandas as pd
from supabase import create_client, Client
import re
from streamlit_autorefresh import st_autorefresh

# --- PAGE SETUP ---
st.set_page_config(page_title="Live Gala Tracker", page_icon="🏊", layout="centered")

# --- AUTO REFRESH ---
st_autorefresh(interval=15000, limit=None, key="gala_refresh")

# --- SUPABASE CONNECTION ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_connection()
except Exception as e:
    st.error("Failed to connect to the database. Check your Streamlit secrets.")
    st.stop()

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .header-box { background: linear-gradient(135deg, #3b82f6 0%, #1e293b 100%); padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-bottom: 4px solid #facc15; }
    .header-title { font-size: 1.8rem; font-weight: 900; color: #ffffff; margin: 0; }
    
    .race-card { background-color: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 16px; border-left: 5px solid #334155; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3); }
    .race-card.completed { border-left-color: #4ade80; }
    .race-card.pending { border-left-color: #fb923c; } 
    
    .race-top-row { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 12px; }
    .race-event-title-group { display: flex; align-items: center; gap: 10px; }
    .race-event { font-weight: 800; font-size: 1.1rem; color: #f8fafc; }
    .race-heat-lane { color: #94a3b8; font-size: 0.85rem; font-weight: 600; }
    
    .race-times-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .time-box { background: #0f172a; padding: 10px; border-radius: 8px; text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; }
    .time-label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; font-weight: 700; margin-bottom: 4px; }
    .time-value { font-size: 1.2rem; font-weight: 900; }
    
    .pb-pill { background-color: #166534; color: #4ade80; font-size: 0.75rem; font-weight: 800; padding: 3px 8px; border-radius: 12px; margin-top: 6px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    
    .tag-unofficial { color: #94a3b8; font-size: 0.65rem; text-transform: uppercase; margin-top: 6px; font-weight: 700; letter-spacing: 0.5px; }
    .tag-official { color: #4ade80; font-size: 0.65rem; text-transform: uppercase; margin-top: 6px; font-weight: 800; letter-spacing: 0.5px; }
    
    .val-entry { color: #94a3b8; }
    .val-achieved { color: #4ade80; } 
    .val-pending { color: #fb923c; } 
    
    .race-analysis { margin-top: 12px; padding-top: 12px; border-top: 1px dashed #334155; text-align: center; font-size: 0.9rem; }
    .gap-green { color: #4ade80; font-weight: bold; }
    .gap-red { color: #f87171; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def extract_standard_event(event_str):
    t = str(event_str).lower()
    t = t.replace('breaststroke', 'breast').replace('breaststrok', 'breast')
    t = t.replace('freestyle', 'free').replace('backstroke', 'back').replace('butterfly', 'fly')
    t = t.replace('individual medley', 'im').replace('ind medley', 'im').replace('ind. medley', 'im')
    t = t.replace('individual', 'im')
    
    m = re.search(r'(\d+)\s*m?\s*(free|back|breast|fly|im)', t)
    if m:
        dist = m.group(1)
        stroke = m.group(2).capitalize()
        if stroke.lower() == 'im': stroke = "IM"
        return f"{dist}m {stroke}"
    
    clean_fallback = str(event_str).split(" - ")[0].strip()
    clean_fallback = re.sub(r'(?i)^event\s*\d+\s*', '', clean_fallback)
    return clean_fallback.title()

def time_to_seconds(t_str):
    if not t_str or pd.isna(t_str) or str(t_str).strip().upper() in ["N/A", "NT", ""]: return None
    t_str = re.sub(r'[^\d:\.]', '', str(t_str).strip())
    if not t_str: return None
    try:
        parts = re.split(r'[:\.]', t_str)
        if len(parts) == 3: return float(parts[0]) * 60 + float(parts[1]) + float(parts[2].ljust(2,'0')[:2]) / 100.0
        elif len(parts) == 2:
            ms_val = parts[1].ljust(2,'0')[:2]
            if ":" in t_str or len(parts[0]) < 3: return float(parts[0]) * 60 + float(parts[1]) if ":" in t_str else float(parts[0]) + float(ms_val) / 100.0
            else: return int(parts[0][:-2]) * 60 + int(parts[0][-2:]) + float(ms_val) / 100.0
        elif len(parts) == 1: return float(parts[0])
    except: return None
    return None

def seconds_to_time(sec):
    return "N/A" if sec is None or sec < 0 else (f"{int(sec // 60)}:{sec % 60:05.2f}" if sec >= 60 else f"{sec % 60:05.2f}")

def get_target_analysis(row, target_df, has_targets):
    if not has_targets: return ""
    
    achieved_str = str(row.get("Achieved Time", "")).strip()
    if not achieved_str or achieved_str.lower() in ["none", "nan", ""]: return ""
    
    pb_sec = time_to_seconds(achieved_str)
    if not pb_sec: return ""
    
    evt = extract_standard_event(row.get("Event", ""))
    gender = str(row.get("Gender", "M")).upper()
    age = row.get("Age", 0)
    
    try:
        age = int(age)
    except:
        return ""

    if evt and "event" in target_df.columns:
        match = target_df[
            (target_df["gender"].str.upper() == gender) & 
            (target_df["age"] == age) & 
            (target_df["event"].str.lower() == evt.lower())
        ]
        
        if not match.empty:
            c_val = match.iloc[0].get("county_time")
            r_val = match.iloc[0].get("regional_time")
            
            c_sec = time_to_seconds(str(c_val)) if pd.notna(c_val) else None
            r_sec = time_to_seconds(str(r_val)) if pd.notna(r_val) else None
            
            if r_sec and pb_sec <= r_sec:
                return "<span class='gap-green'>🏆 Regional Time Achieved!</span>"
            elif c_sec and pb_sec <= c_sec:
                return "<span class='gap-green'>🌟 County Time Achieved!</span>"
            elif c_sec:
                diff = pb_sec - c_sec
                return f"<span class='gap-red'>Missed County by {seconds_to_time(diff)}</span>"
    return ""

# --- APP UI & LOGIC ---

st.markdown("""
<div class="header-box">
    <div class="header-title">📲 Parent Live Gala Tracker</div>
</div>
""", unsafe_allow_html=True)

# 1. Load Targets
try:
    target_df = pd.read_csv("target_times.csv")
    cols = {str(c).strip().lower(): c for c in target_df.columns}
    rename_map = {}
    for c_lower, c_orig in cols.items():
        if 'county' in c_lower: rename_map[c_orig] = 'county_time'
        elif 'region' in c_lower: rename_map[c_orig] = 'regional_time'
        elif 'event' in c_lower: rename_map[c_orig] = 'event'
        elif 'age' in c_lower: rename_map[c_orig] = 'age'
        elif 'gender' in c_lower or 'sex' in c_lower: rename_map[c_orig] = 'gender'
    target_df.rename(columns=rename_map, inplace=True)
    if "event" in target_df.columns: target_df["event"] = target_df["event"].apply(extract_standard_event)
    has_targets = True
except:
    has_targets = False
    target_df = pd.DataFrame()

# 2. Login / PIN
room_pin = st.text_input("Enter Gala PIN provided by Team Manager:", type="password")

if room_pin:
    # 3. Fetch Live Data
    res = supabase.table("live_gala_data").select("*").eq("room_pin", str(room_pin)).execute()
        
    if not res.data:
        st.warning("No data found for this PIN. Check with your Team Manager.")
        st.stop()
        
    live_df = pd.DataFrame(res.data)
    
    # Updated mapping to catch 'official_placement'
    col_mapping = {
        "event": "Event", "session": "Session", "heat": "Heat", 
        "lane": "Lane", "swimmer": "Swimmer", "entry_time": "Entry Time", 
        "achieved_time": "Achieved Time", "official_placement": "Placement",
        "age": "Age", "gender": "Gender"
    }
    live_df.rename(columns={k: v for k, v in col_mapping.items() if k in live_df.columns}, inplace=True)
    
    # 4. Select Swimmer
    swimmers = sorted(live_df["Swimmer"].dropna().unique().tolist())
    selected_swimmer = st.selectbox("Select Swimmer", ["-- Select --"] + swimmers)
    
    if selected_swimmer != "-- Select --":
        swim_df = live_df[live_df["Swimmer"] == selected_swimmer].copy()
        
        def get_event_num(e_str):
            m = re.search(r'\d+', str(e_str))
            return int(m.group()) if m else 999
            
        swim_df["_event_num"] = swim_df["Event"].apply(get_event_num)
        swim_df = swim_df.sort_values(by=["Session", "_event_num", "Heat", "Lane"])

        st.markdown(f"### Live Races for {selected_swimmer}")
        
        # 5. Render the Dashboard Cards
        for _, row in swim_df.iterrows():
            entry_str = str(row.get("Entry Time", "NT")).strip()
            achieved_str = str(row.get("Achieved Time", "")).strip()
            is_completed = bool(achieved_str and achieved_str.lower() not in ["none", "nan", ""])
            clean_evt = extract_standard_event(row.get("Event", ""))
            
            is_marshalled = row.get("in_marshalling", False) 
            
            placement_str = str(row.get("Placement", "")).strip()
            has_official_placement = bool(placement_str and placement_str.lower() not in ["none", "nan", ""])
            
            pb_badge_html = ""
            verification_tag = ""
            
            if is_completed:
                display_time = achieved_str
                time_class = "val-achieved"
                
                # Check for Official/Unofficial Status
                if has_official_placement:
                    verification_tag = "<div class='tag-official'>✓ OFFICIAL</div>"
                else:
                    verification_tag = "<div class='tag-unofficial'>UNOFFICIAL</div>"
                
                # Calculate Time Drop for PB Pill (ignores "DQ" safely)
                entry_sec = time_to_seconds(entry_str)
                achieved_sec = time_to_seconds(achieved_str)
                
                if entry_sec and achieved_sec and achieved_sec < entry_sec:
                    drop = entry_sec - achieved_sec
                    drop_str = f"-{drop:.2f}s" if drop < 60 else f"-{seconds_to_time(drop)}"
                    pb_badge_html = f"<div class='pb-pill'>🌟 PB ({drop_str})</div>"
                    
            elif is_marshalled:
                display_time = "🚶‍♂️ MARSHALLING"
                time_class = "val-pending"
            else:
                display_time = "WAITING"
                time_class = "val-entry"

            badge_html = f"<span style='font-weight: 800; font-size: 1.1rem; color: #facc15;'>{placement_str}</span>" if has_official_placement else ""

            st.markdown(f"""
<div class="race-card {'completed' if is_completed else 'pending'}">
<div class="race-top-row">
<div class="race-event-title-group"><span class="race-event">{clean_evt}</span>{badge_html}</div>
<div class="race-heat-lane">Sess {row.get("Session", "-")} | H {row.get("Heat", "-")} | L {row.get("Lane", "-")}</div>
</div>
<div class="race-times-grid">
<div class="time-box"><div class="time-label">Entry Time</div><div class="time-value val-entry">{entry_str}</div></div>
<div class="time-box"><div class="time-label">Achieved Time</div><div class="time-value {time_class}">{display_time}</div>{verification_tag}{pb_badge_html}</div>
</div>
<div class="race-analysis">{get_target_analysis(row, target_df, has_targets)}</div>
</div>
            """, unsafe_allow_html=True)
            
        if st.button("🔄 Force Refresh"):
            st.rerun()