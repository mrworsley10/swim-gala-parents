import streamlit as st
import pandas as pd
from supabase import create_client, Client
import re
import urllib.parse
import html
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from zoneinfo import ZoneInfo

# --- PAGE SETUP ---
st.set_page_config(page_title="Live Gala Tracker", page_icon="🏊", layout="centered")

# --- AUTO REFRESH ---
st_autorefresh(interval=30000, limit=None, key="gala_refresh")

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
    .gap-amber { color: #fbbf24; font-weight: bold; }
    
    .whatsapp-btn { display: block; margin-top: 12px; background-color: #25D366; color: white !important; text-align: center; padding: 8px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 0.9rem; transition: background-color 0.2s; }
    .whatsapp-btn:hover { background-color: #1ebc5a; }
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
    e_lower = str(row.get("Event", "")).lower()
    gender = "F" if ("female" in e_lower or "girl" in e_lower or "women" in e_lower) else "M"
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
                diff_str = f"{diff:.2f}s" if diff < 60 else seconds_to_time(diff)
                return f"<span class='gap-amber'>{diff_str} off County time - getting closer!</span>"
    return ""

# --- APP UI & LOGIC ---

st.markdown("""
<div class="header-box">
    <div class="header-title">📲 Parent Live Gala Tracker</div>
</div>
""", unsafe_allow_html=True)

# 1. Load Targets (the coaches' app saves these in Supabase, one set per gala room)
@st.cache_data(ttl=300)
def load_room_targets(pin):
    try:
        t_res = supabase.table("target_times").select("*").eq("room_pin", str(pin)).execute()
        t_df = pd.DataFrame(t_res.data or [])
    except Exception:
        return pd.DataFrame()
    if t_df.empty or "event" not in t_df.columns or "gender" not in t_df.columns or "age" not in t_df.columns:
        return pd.DataFrame()
    t_df["event"] = t_df["event"].apply(extract_standard_event)
    t_df["gender"] = t_df["gender"].astype(str).str.strip().str.upper().str[:1].map(lambda g: "F" if g in ("F", "G", "W") else "M")
    t_df["age"] = pd.to_numeric(t_df["age"], errors="coerce")
    return t_df

# --- FETCH URL PARAMETERS ---
url_pin = st.query_params.get("pin", "")
url_swimmer = st.query_params.get("swimmer", "-- Select --")

# 2. Login / PIN (Now uses URL pin as default)
room_pin = st.text_input("Enter Gala PIN provided by Team Manager:", value=url_pin, type="password")

if room_pin:
    # Update the URL automatically when a PIN is entered
    st.query_params["pin"] = room_pin

    # 3. Fetch Live Data
    res = supabase.table("live_gala_data").select("*").eq("room_pin", str(room_pin)).execute()
        
    if not res.data:
        st.warning("No data found for this PIN. Check with your Team Manager.")
        st.stop()

# --- FETCH LIVE ANNOUNCEMENTS ---
    announce_res = supabase.table("gala_settings").select("announcement").eq("room_pin", str(room_pin)).execute()
    
    if announce_res.data and announce_res.data[0].get("announcement"):
        active_msg = announce_res.data[0]["announcement"].strip()
        if active_msg:
            st.markdown(f"""
            <div style="background: linear-gradient(90deg, #f59e0b 0%, #fbbf24 100%); color: #0f172a; padding: 16px; border-radius: 12px; margin-bottom: 24px; font-weight: 900; text-align: center; border-left: 8px solid #d97706; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-size: 1.1rem;">
                🚨 GALA UPDATE: {html.escape(active_msg)}
            </div>
            """, unsafe_allow_html=True)
        
    live_df = pd.DataFrame(res.data)
    target_df = load_room_targets(room_pin)
    has_targets = not target_df.empty
    
    col_mapping = {
        "event": "Event", "session": "Session", "heat": "Heat", 
        "lane": "Lane", "swimmer": "Swimmer", "entry_time": "Entry Time", 
        "achieved_time": "Achieved Time", "official_placement": "Placement",
        "age": "Age", "gender": "Gender"
    }
    live_df.rename(columns={k: v for k, v in col_mapping.items() if k in live_df.columns}, inplace=True)
    
    # 4. Select Swimmer
    swimmers = sorted(live_df["Swimmer"].dropna().unique().tolist())
    
    # Calculate the correct dropdown index based on the URL
    default_index = 0
    if url_swimmer in swimmers:
        default_index = swimmers.index(url_swimmer) + 1
        
    selected_swimmer = st.selectbox("Select Swimmer", ["-- Select --"] + swimmers, index=default_index)
    
    if selected_swimmer != "-- Select --":
        # Update the URL automatically when a swimmer is chosen
        st.query_params["swimmer"] = selected_swimmer
        
        swim_df = live_df[live_df["Swimmer"] == selected_swimmer].copy()
        
        def get_event_num(e_str):
            m = re.search(r'\d+', str(e_str))
            return int(m.group()) if m else 999
            
        swim_df["_event_num"] = swim_df["Event"].apply(get_event_num)
        swim_df = swim_df.sort_values(by=["Session", "_event_num", "Heat", "Lane"])

        st.markdown(f"### Live Races for {selected_swimmer}")
        st.caption(f"Last updated {datetime.now(ZoneInfo('Europe/London')):%H:%M:%S} · updates every 30 seconds")

# --- DAILY TALLY DASHBOARD ---
        total_races = len(swim_df)
        completed_races = 0
        pb_count = 0
        top3_count = 0

        for _, row in swim_df.iterrows():
            entry_str = str(row.get("Entry Time", "NT")).strip()
            achieved_str = str(row.get("Achieved Time", "")).strip()
            placement_str = str(row.get("Placement", "")).strip()

            is_completed = bool(achieved_str and achieved_str.lower() not in ["none", "nan", ""])

            if is_completed:
                completed_races += 1
                
                # Check PB
                entry_sec = time_to_seconds(entry_str)
                achieved_sec = time_to_seconds(achieved_str)
                if entry_sec and achieved_sec and achieved_sec < entry_sec:
                    pb_count += 1
                    
                # Check Top 3
                if re.sub(r'\D', '', placement_str.split('.')[0]) in ["1", "2", "3"]:
                    top3_count += 1

        st.markdown(f"""
        <div style="display: flex; justify-content: space-around; background-color: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid #334155;">
            <div style="text-align: center;"><div style="font-size: 1.5rem;">🏁</div><div style="font-size: 0.8rem; font-weight: bold; color: #94a3b8; margin-top: 4px;">{completed_races} / {total_races} RACES</div></div>
            <div style="text-align: center;"><div style="font-size: 1.5rem;">🌟</div><div style="font-size: 0.8rem; font-weight: bold; color: #4ade80; margin-top: 4px;">{pb_count} PBs</div></div>
            <div style="text-align: center;"><div style="font-size: 1.5rem;">🥇</div><div style="font-size: 0.8rem; font-weight: bold; color: #facc15; margin-top: 4px;">{top3_count} TOP 3</div></div>
        </div>
        """, unsafe_allow_html=True)

        # --- NEXT RACE BOX ---
        _waiting = swim_df[swim_df["Achieved Time"].fillna("").astype(str).str.strip().str.lower().isin(["", "none", "nan"])]
        if not _waiting.empty:
            nr = _waiting.iloc[0]
            _in_marshalling = str(nr.get("in_marshalling", "")).strip().lower() == "true"
            _status = "🚶‍♂️ In marshalling now" if _in_marshalling else "⏳ Not called to marshalling yet"
            st.markdown(f"""
<div style="background: #1e3a8a; border: 2px solid #facc15; border-radius: 12px; padding: 14px 16px; margin-bottom: 20px; text-align: center;">
<div style="font-size: 0.75rem; font-weight: 800; color: #facc15; letter-spacing: 1px;">NEXT RACE</div>
<div style="font-size: 1.3rem; font-weight: 900; color: #ffffff; margin: 4px 0;">{html.escape(extract_standard_event(nr.get("Event", "")))}</div>
<div style="font-size: 0.95rem; color: #cbd5e1; font-weight: 600;">Session {nr.get("Session", "-")} · Heat {nr.get("Heat", "-")} · Lane {nr.get("Lane", "-")}</div>
<div style="font-size: 0.9rem; color: #fb923c; font-weight: 700; margin-top: 6px;">{_status}</div>
</div>
            """, unsafe_allow_html=True)
        elif total_races:
            st.success("🎉 All races finished - well done!")
        
        # --- TOGGLE FILTER ---
        filter_choice = st.radio("Filter Races:", ["All", "Upcoming", "Completed"], horizontal=True)
        st.caption("🟢 Finished · 🟠 Still to swim · 🌟 PB = faster than entry time · Unofficial = time logged by our coaches, Official = placing from the results")
        
        # 5. Render the Dashboard Cards
        for _, row in swim_df.iterrows():
            entry_str = str(row.get("Entry Time", "NT")).strip()
            achieved_str = str(row.get("Achieved Time", "")).strip()
            is_completed = bool(achieved_str and achieved_str.lower() not in ["none", "nan", ""])
            clean_evt = extract_standard_event(row.get("Event", ""))
            
            # Apply Filter
            if filter_choice == "Upcoming" and is_completed:
                continue
            if filter_choice == "Completed" and not is_completed:
                continue
            
            is_marshalled = row.get("in_marshalling", False) 
            
            placement_str = str(row.get("Placement", "")).strip()
            has_official_placement = bool(placement_str and placement_str.lower() not in ["none", "nan", ""])
            
            pb_badge_html = ""
            verification_tag = ""
            whatsapp_html = ""
            
            if is_completed:
                display_time = achieved_str
                time_class = "val-achieved"
                
                if has_official_placement:
                    verification_tag = "<div class='tag-official'>✓ OFFICIAL</div>"
                else:
                    verification_tag = "<div class='tag-unofficial'>UNOFFICIAL</div>"
                
                entry_sec = time_to_seconds(entry_str)
                achieved_sec = time_to_seconds(achieved_str)
                is_pb = False
                
                if entry_sec and achieved_sec and achieved_sec < entry_sec:
                    drop = entry_sec - achieved_sec
                    drop_str = f"-{drop:.2f}s" if drop < 60 else f"-{seconds_to_time(drop)}"
                    pb_badge_html = f"<div class='pb-pill'>🌟 PB ({drop_str})</div>"
                    is_pb = True
                
                # Build WhatsApp Share Link
                share_text = f"🌟 {selected_swimmer} just swam a PB in the {clean_evt} with a time of {achieved_str}! 🏊‍♂️🚀" if is_pb else f"🏊‍♂️ {selected_swimmer} just finished the {clean_evt} with a time of {achieved_str}!"
                encoded_text = urllib.parse.quote(share_text)
                whatsapp_url = f"https://wa.me/?text={encoded_text}"
                whatsapp_html = f"<a href='{whatsapp_url}' target='_blank' class='whatsapp-btn'>📱 Share to WhatsApp</a>"
                    
            elif is_marshalled:
                display_time = "🚶‍♂️ MARSHALLING"
                time_class = "val-pending"
            else:
                display_time = "WAITING"
                time_class = "val-entry"

            badge_html = f"<span style='font-weight: 800; font-size: 1.1rem; color: #facc15;'>{html.escape(placement_str)}</span>" if has_official_placement else ""

            st.markdown(f"""
<div class="race-card {'completed' if is_completed else 'pending'}">
<div class="race-top-row">
<div class="race-event-title-group"><span class="race-event">{html.escape(clean_evt)}</span>{badge_html}</div>
<div class="race-heat-lane">Sess {row.get("Session", "-")} | H {row.get("Heat", "-")} | L {row.get("Lane", "-")}</div>
</div>
<div class="race-times-grid">
<div class="time-box"><div class="time-label">Entry Time</div><div class="time-value val-entry">{html.escape(entry_str)}</div></div>
<div class="time-box"><div class="time-label">Achieved Time</div><div class="time-value {time_class}">{html.escape(display_time)}</div>{verification_tag}{pb_badge_html}</div>
</div>
<div class="race-analysis">{get_target_analysis(row, target_df, has_targets)}</div>
{whatsapp_html}
</div>
            """, unsafe_allow_html=True)
            
        if st.button("🔄 Force Refresh"):
            st.rerun()