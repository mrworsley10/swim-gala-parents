import streamlit as st
import pandas as pd
import re
from datetime import datetime
from supabase import create_client, Client

# --- PAGE SETUP ---
st.set_page_config(page_title="Live Swimmer Tracker", page_icon="🏊", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM MOBILE-FIRST CSS ---
st.markdown("""
<style>
    /* Hide extra Streamlit Chrome */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Sleek background and text */
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
    }
    
    /* Login / PIN Screen */
    .pin-container {
        background: #1e293b;
        padding: 30px;
        border-radius: 15px;
        text-align: center;
        margin-top: 10vh;
        border-top: 4px solid #3b82f6;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
    }
    
    /* Swimmer Report Header */
    .swimmer-header {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #334155;
        margin-bottom: 20px;
        text-align: center;
    }
    .swimmer-name {
        font-size: 1.8rem;
        font-weight: 800;
        color: #facc15;
        margin-bottom: 5px;
        line-height: 1.2;
    }
    .swimmer-stats {
        font-size: 0.9rem;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Race Cards */
    .race-card {
        background-color: #1e293b;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 15px;
        border-left: 5px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    .race-card.completed { border-left-color: #4ade80; }
    .race-card.pending { border-left-color: #facc15; }
    
    .race-top-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
        border-bottom: 1px solid #334155;
        padding-bottom: 8px;
    }
    .race-event {
        font-weight: 700;
        font-size: 1.05rem;
        color: #f8fafc;
    }
    .race-heat-lane {
        font-size: 0.8rem;
        color: #94a3b8;
        background: #0f172a;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
    }
    
    .race-times-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin-bottom: 10px;
    }
    .time-box {
        background: #0f172a;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
    }
    .time-label {
        font-size: 0.7rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 3px;
        font-weight: 700;
    }
    .time-value {
        font-size: 1.3rem;
        font-weight: 900;
    }
    .val-entry { color: #cbd5e1; }
    .val-achieved { color: #4ade80; }
    .val-pending { color: #facc15; font-size: 1rem !important; line-height: 1.3rem; }
    
    .race-analysis {
        background: #0f172a;
        padding: 10px;
        border-radius: 8px;
        font-size: 0.85rem;
        color: #e2e8f0;
        text-align: center;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- SUPABASE CLOUD CONNECTION ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Database Connection Failed: {e}")

# --- MATH & FORMATTING FUNCTIONS ---
def safe_int(val, default=-1):
    try: return int(float(val))
    except: return default

def get_event_num(event_str):
    m = re.search(r'Event\s+(\d+)', str(event_str), re.IGNORECASE)
    return int(m.group(1)) if m else 9999

def extract_gender(event_str):
    e_lower = str(event_str).lower()
    if 'female' in e_lower or 'girl' in e_lower or 'women' in e_lower: return 'F'
    if 'male' in e_lower or 'boy' in e_lower or 'men' in e_lower or 'open' in e_lower: return 'M'
    return 'M'

def extract_standard_event(event_str):
    m = re.search(r'(\d+m\s+[A-Za-z]+(?:\s+IM)?)', str(event_str), re.IGNORECASE)
    if m:
        stroke = m.group(1).title()
        stroke = stroke.replace('Breaststroke', 'Breast').replace('Breaststrok', 'Breast')
        stroke = stroke.replace('Freestyle', 'Free')
        stroke = stroke.replace('Backstroke', 'Back')
        stroke = stroke.replace('Butterfly', 'Fly')
        stroke = stroke.replace('Ind. Medley', 'IM').replace('Ind Medley', 'IM')
        stroke = stroke.replace('M ', 'm ').replace(' Im', ' IM')
        return stroke.strip()
    return ""

def time_to_seconds(t_str):
    if not t_str or str(t_str).strip().upper() in ["N/A", "S/T", "NT", "", "-", "—", "NONE", "DQ", "DNC", "WD", "WITHDRAWN"]: return None
    t_str = str(t_str).strip()
    t_str = re.sub(r'[^\d:\.]', '', t_str)
    if not t_str: return None
    try:
        if t_str.isdigit():
            if len(t_str) >= 5: 
                m, s, ms = int(t_str[:-4]), int(t_str[-4:-2]), int(t_str[-2:])
                return m * 60 + s + (ms / 100.0)
            elif len(t_str) >= 3: 
                s, ms = int(t_str[:-2]), int(t_str[-2:])
                return s + (ms / 100.0)
            else: return float(t_str)
        parts = re.split(r'[:\.]', t_str)
        if len(parts) == 3: 
            ms_val = parts[2]
            if len(ms_val) == 1: ms_val += '0' 
            return float(parts[0]) * 60 + float(parts[1]) + float(ms_val[:2]) / 100.0
        elif len(parts) == 2:
            ms_val = parts[1]
            if len(ms_val) == 1: ms_val += '0'
            if ":" in t_str or len(parts[0]) < 3: 
                if ":" in t_str: return float(parts[0]) * 60 + float(parts[1])
                else: return float(parts[0]) + float(ms_val[:2]) / 100.0
            else:
                m, s = int(parts[0][:-2]), int(parts[0][-2:])
                return m * 60 + s + float(ms_val[:2]) / 100.0
        elif len(parts) == 1: return float(parts[0])
    except Exception: return None
    return None

def seconds_to_time(sec):
    if sec is None or sec < 0: return "N/A"
    mins = int(sec // 60)
    remainder = sec % 60
    if mins > 0: return f"{mins}:{remainder:05.2f}"
    else: return f"{remainder:05.2f}"

def calculate_variance(achieved_sec, target_sec):
    if achieved_sec is None or target_sec is None: return "N/A"
    diff = achieved_sec - target_sec
    if diff < 0: return f"✅ -{seconds_to_time(abs(diff))}" 
    elif diff > 0: return f"🔺 +{seconds_to_time(abs(diff))}" 
    else: return f"⏸️️ 0.00"

def get_target_analysis(row, target_df, has_targets):
    ach_sec = time_to_seconds(row.get('Achieved Time'))
    ent_sec = time_to_seconds(row.get('Entry Time'))
    c_sec, r_sec = None, None
    
    if has_targets:
        g = extract_gender(row.get('Event', ''))
        a = safe_int(row.get('Age'), -1)
        e = extract_standard_event(row.get('Event', ''))
        match = target_df[(target_df['Gender'] == g) & (target_df['Age'] == a) & (target_df['Event'].str.lower() == e.lower())]
        
        c_time = match.iloc[0].get('County_Time', "") if not match.empty and pd.notna(match.iloc[0].get('County_Time')) else ""
        r_time = match.iloc[0].get('Regional_Time', "") if not match.empty and pd.notna(match.iloc[0].get('Regional_Time')) else ""
        
        c_sec = time_to_seconds(c_time) if c_time else None
        r_sec = time_to_seconds(r_time) if r_time else None

    if ach_sec is not None:
        res = []
        ent_ach_var = calculate_variance(ach_sec, ent_sec) if ent_sec else ""
        if ent_ach_var and ent_ach_var != "N/A": res.append(f"PB: {ent_ach_var}")
        
        if has_targets:
            c_ach_var = calculate_variance(ach_sec, c_sec) if c_sec else ""
            r_ach_var = calculate_variance(ach_sec, r_sec) if r_sec else ""
            if c_ach_var and c_ach_var != "N/A": res.append(f"C: {c_ach_var}")
            if r_ach_var and r_ach_var != "N/A": res.append(f"R: {r_ach_var}")
            
        return " | ".join(res) if res else "Logged"
    else:
        if has_targets:
            res = []
            c_ent_var = calculate_variance(ent_sec, c_sec) if ent_sec and c_sec else ""
            r_ent_var = calculate_variance(ent_sec, r_sec) if ent_sec and r_sec else ""
            if c_ent_var and c_ent_var != "N/A": res.append(f"C: {c_ent_var}")
            if r_ent_var and r_ent_var != "N/A": res.append(f"R: {r_ent_var}")
            return " | ".join(res) if res else "No Targets Loaded"
        else:
            return "⏳ Awaiting Race"

# --- DATA FETCHING ---
def fetch_room_data(pin):
    try:
        response = supabase.table("live_gala_data").select("*").eq("room_pin", str(pin)).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            return df.rename(columns={"session": "Session", "swimmer": "Swimmer", "age": "Age", "event": "Event", "heat": "Heat", "lane": "Lane", "entry_time": "Entry Time", "achieved_time": "Achieved Time"})
    except: pass
    return pd.DataFrame()

def fetch_room_targets(pin):
    try:
        res = supabase.table("target_times").select("*").eq("room_pin", str(pin)).execute()
        if res.data:
            tdf = pd.DataFrame(res.data)
            return tdf.rename(columns={"gender": "Gender", "age": "Age", "event": "Event", "county_time": "County_Time", "regional_time": "Regional_Time"})
    except: pass
    return pd.DataFrame()

# --- STATE MANAGEMENT ---
if "parent_room" not in st.session_state:
    st.session_state["parent_room"] = None
if "gala_df" not in st.session_state:
    st.session_state["gala_df"] = pd.DataFrame()
if "target_df" not in st.session_state:
    st.session_state["target_df"] = pd.DataFrame()

# --- UI: PIN LOGIN SCREEN ---
if not st.session_state["parent_room"]:
    st.markdown("""
    <div class="pin-container">
        <h1 style="color: white; margin-bottom: 5px;">🏊 Swimmer Live Tracker</h1>
        <p style="color: #94a3b8; margin-bottom: 25px;">Enter the 4-digit PIN provided by your coach to follow live results.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        join_pin = st.text_input("Room PIN", max_chars=4, placeholder="e.g. 1234", label_visibility="collapsed")
        if st.button("Access Live Results", use_container_width=True, type="primary"):
            if join_pin:
                with st.spinner("Finding Room..."):
                    df = fetch_room_data(join_pin)
                    if not df.empty:
                        st.session_state["parent_room"] = join_pin
                        st.session_state["gala_df"] = df
                        st.session_state["target_df"] = fetch_room_targets(join_pin)
                        st.rerun()
                    else:
                        st.error("Invalid PIN or room is empty.")
    st.stop()

# --- UI: PARENT DASHBOARD ---
df = st.session_state["gala_df"]
target_df = st.session_state["target_df"]
has_targets = not target_df.empty

# Top Action Bar
colA, colB = st.columns([3, 1])
with colA:
    st.markdown(f"<span style='color: #4ade80; font-weight: bold;'>🟢 Connected (Room {st.session_state['parent_room']})</span>", unsafe_allow_html=True)
with colB:
    if st.button("🔄 Refresh", use_container_width=True):
        st.session_state["gala_df"] = fetch_room_data(st.session_state["parent_room"])
        st.session_state["target_df"] = fetch_room_targets(st.session_state["parent_room"])
        st.rerun()

st.divider()

swimmer_list = sorted(df["Swimmer"].unique())
selected_swimmer = st.selectbox("🔍 Search for a Swimmer:", [""] + swimmer_list)

if selected_swimmer:
    swim_df = df[df["Swimmer"] == selected_swimmer].copy()
    
    # Sort chronologically by Session, Event Number, Heat, Lane
    swim_df["_evt_num"] = swim_df["Event"].apply(get_event_num)
    swim_df["_sort_heat"] = pd.to_numeric(swim_df["Heat"], errors='coerce').fillna(9999)
    swim_df["_sort_lane"] = pd.to_numeric(swim_df["Lane"], errors='coerce').fillna(9999)
    swim_df = swim_df.sort_values(by=["Session", "_evt_num", "_sort_heat", "_sort_lane"])
    
    total_races = len(swim_df)
    done_races = len(swim_df[swim_df["Achieved Time"] != ""])
    swimmer_age = swim_df.iloc[0].get("Age", "N/A")
    
    # Render Profile Header
    st.markdown(f"""
    <div class="swimmer-header">
        <div class="swimmer-name">{selected_swimmer}</div>
        <div class="swimmer-stats">Age {swimmer_age} • {done_races} of {total_races} Races Completed</div>
    </div>
    """, unsafe_allow_html=True)

    # Render Individual Race Cards
    for _, row in swim_df.iterrows():
        achieved = str(row["Achieved Time"]).strip()
        is_completed = bool(achieved and achieved.lower() not in ["none", "nan"])
        
        card_class = "completed" if is_completed else "pending"
        time_display = achieved if is_completed else "WAITING"
        time_class = "val-achieved" if is_completed else "val-pending"
        
        clean_event = extract_standard_event(row["Event"]) or str(row["Event"]).split(" - ")[0]
        analysis_text = get_target_analysis(row, target_df, has_targets)
        
        st.markdown(f"""
        <div class="race-card {card_class}">
            <div class="race-top-row">
                <div class="race-event">{clean_event}</div>
                <div class="race-heat-lane">Sess {row["Session"]} | H {row["Heat"]} | L {row["Lane"]}</div>
            </div>
            <div class="race-times-grid">
                <div class="time-box">
                    <div class="time-label">Entry Time</div>
                    <div class="time-value val-entry">{row["Entry Time"]}</div>
                </div>
                <div class="time-box">
                    <div class="time-label">Achieved Time</div>
                    <div class="time-value {time_class}">{time_display}</div>
                </div>
            </div>
            <div class="race-analysis">{analysis_text}</div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("👆 Tap the search bar above to find your swimmer's live report card.")

# Bottom Exit
st.markdown("<br><br>", unsafe_allow_html=True)
if st.button("🚪 Leave Room", type="secondary"):
    st.session_state["parent_room"] = None
    st.session_state["gala_df"] = pd.DataFrame()
    st.rerun()