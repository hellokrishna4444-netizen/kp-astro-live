import os
import json
import time
import datetime
import urllib.request
import pytz
import swisseph as swe
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. CONFIGURATION & QUOTA-SAFE CONNECTION
# ==========================================
DAYS_BACK = 30
DAYS_AHEAD = 18
LIVE_LOOP_MINUTES = 14  # Runs every 60s for 14 mins per GitHub cycle

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["GCP_SA_KEY"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

raw_id = os.environ["SHEET_ID"].strip()
if "/d/" in raw_id:
    raw_id = raw_id.split("/d/")[1].split("/")[0]
sheet = client.open_by_key(raw_id)

# Exchanges Configuration (25-column wide quadrants)
CITIES = {
    "Mumbai_NSE": {"lat": 19.0760, "lon": 72.8777, "tz": "Asia/Kolkata",     "row": 1,  "col": 1,  "janma_nak": 12},
    "Tokyo_TSE":  {"lat": 35.6762, "lon": 139.6503,"tz": "Asia/Tokyo",       "row": 1,  "col": 27, "janma_nak": 3},
    "London_LSE": {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London",    "row": 64, "col": 1,  "janma_nak": 9},
    "New_York":   {"lat": 40.7128, "lon": -74.0060,"tz": "America/New_York", "row": 64, "col": 27, "janma_nak": 21}
}

# Active Session Windows (Local Exchange Time)
# Tokyo extended to 17:30 Tokyo (02:00 PM IST) so Tokyo Close + London Open overlap is also captured!
SESSION_WINDOWS_LOCAL = {
    "Mumbai_NSE": (datetime.time(9, 10), datetime.time(15, 35)),
    "Tokyo_TSE":  (datetime.time(8, 55), datetime.time(17, 30)),
    "London_LSE": (datetime.time(7, 55), datetime.time(16, 35)),
    "New_York":   (datetime.time(9, 25), datetime.time(16, 5))
}

IST_TZ = pytz.timezone("Asia/Kolkata")
SENT_ALERTS_CACHE = set()

# ==========================================
# 2. SHASTRA TABLES & CONSTANTS
# ==========================================
DASHA_LORDS = ["Ke", "Ve", "Su", "Mo", "Ma", "Ra", "Ju", "Sa", "Me"]
DASHA_YEARS = [7, 20, 6, 10, 7, 18, 16, 19, 17]
HORA_SEQUENCE = ["Su", "Ve", "Me", "Mo", "Sa", "Ju", "Ma"]
WEEKDAY_LORDS = {6: "Su", 0: "Mo", 1: "Ma", 2: "Me", 3: "Ju", 4: "Ve", 5: "Sa"}
RASHIS = ["Ar", "Ta", "Ge", "Cn", "Le", "Vi", "Li", "Sc", "Sg", "Cp", "Aq", "Pi"]
RASHI_LORDS = ["Ma", "Ve", "Me", "Mo", "Su", "Me", "Ve", "Ma", "Ju", "Sa", "Sa", "Ju"]
TATTVA_MAP = {
    "Ar": "Fiery (Agni)", "Le": "Fiery (Agni)", "Sg": "Fiery (Agni)",
    "Ta": "Earthy (Prithvi)", "Vi": "Earthy (Prithvi)", "Cp": "Earthy (Prithvi)",
    "Ge": "Airy (Vayu)", "Li": "Airy (Vayu)", "Aq": "Airy (Vayu)",
    "Cn": "Watery (Jal)", "Sc": "Watery (Jal)", "Pi": "Watery (Jal)"
}

TITHI_LORDS_SEQ = ["Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra"]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

YOGAS = [
    ("Vishkambha", "Ashubha"), ("Priti", "Shubha"), ("Ayushman", "Shubha"), ("Saubhagya", "Shubha"),
    ("Shobhana", "Shubha"), ("Atiganda", "Ashubha"), ("Sukarma", "Shubha"), ("Dhriti", "Shubha"),
    ("Shula", "Ashubha"), ("Ganda", "Ashubha"), ("Vriddhi", "Shubha"), ("Dhruva", "Shubha"),
    ("Vyaghata", "Ashubha"), ("Harshana", "Shubha"), ("Vajra", "Ashubha"), ("Siddhi", "Shubha"),
    ("Vyatipata", "Ghor Ashubha"), ("Variyan", "Shubha"), ("Parigha", "Ashubha"), ("Shiva", "Shubha"),
    ("Siddha", "Shubha"), ("Sadhya", "Shubha"), ("Shubha", "Shubha"), ("Shukla", "Shubha"),
    ("Brahma", "Shubha"), ("Indra", "Shubha"), ("Vaidhriti", "Ghor Ashubha")
]

CHARA_KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti (Bhadra)"]
TARA_NAMES = [
    ("1-Janma", "Sensitive"), ("2-Sampat", "Param Shubha"), ("3-Vipat", "Ashubha Trap"),
    ("4-Kshema", "Shubha Safe"), ("5-Pratyak", "Obstacle"), ("6-Sadhaka", "Shubha Hit"),
    ("7-Vadha", "Ghor Ashubha"), ("8-Mitra", "Shubha"), ("9-Parama Mitra", "Param Shubha")
]

MAITRI = {
    "Su": {"friends": ["Mo", "Ma", "Ju"], "enemies": ["Ve", "Sa"], "neutral": ["Me"]},
    "Mo": {"friends": ["Su", "Me"], "enemies": [], "neutral": ["Ma", "Ju", "Ve", "Sa"]},
    "Ma": {"friends": ["Su", "Mo", "Ju"], "enemies": ["Me"], "neutral": ["Ve", "Sa"]},
    "Me": {"friends": ["Su", "Ve"], "enemies": ["Mo"], "neutral": ["Ma", "Ju", "Sa"]},
    "Ju": {"friends": ["Su", "Mo", "Ma"], "enemies": ["Me", "Ve"], "neutral": ["Sa"]},
    "Ve": {"friends": ["Me", "Sa"], "enemies": ["Su", "Mo"], "neutral": ["Ma", "Ju"]},
    "Sa": {"friends": ["Me", "Ve"], "enemies": ["Su", "Mo", "Ma"], "neutral": ["Ju"]},
    "Ra": {"friends": ["Me", "Ve", "Sa"], "enemies": ["Su", "Mo", "Ma"], "neutral": ["Ju"]}
}

PLANETS = {
    "Su": swe.SUN, "Mo": swe.MOON, "Ma": swe.MARS, "Me": swe.MERCURY,
    "Ju": swe.JUPITER, "Ve": swe.VENUS, "Sa": swe.SATURN,
    "Ra": swe.TRUE_NODE, "Ur": swe.URANUS, "Ne": swe.NEPTUNE, "Pl": swe.PLUTO
}

EXALT_SIGNS = {"Su": "Ar", "Mo": "Ta", "Ma": "Cp", "Me": "Vi", "Ju": "Cn", "Ve": "Pi", "Sa": "Li", "Ra": "Ta", "Ke": "Sc"}
DEBIL_SIGNS = {"Su": "Li", "Mo": "Sc", "Ma": "Cn", "Me": "Pi", "Ju": "Cp", "Ve": "Vi", "Sa": "Ar", "Ra": "Sc", "Ke": "Ta"}
PARAM_UCHHA_DEG = {"Su": 10.0, "Mo": 33.0, "Ma": 298.0, "Me": 165.0, "Ju": 95.0, "Ve": 357.0, "Sa": 200.0}
SHADBALA_REQ = {"Su": 6.5, "Mo": 6.0, "Ma": 5.0, "Me": 7.0, "Ju": 6.5, "Ve": 5.5, "Sa": 5.0}
NAISARGIKA_BALA = {"Su": 60.0, "Mo": 51.4, "Ve": 42.8, "Ju": 34.3, "Me": 25.7, "Ma": 17.1, "Sa": 8.6}
COMBUST_ORBS = {"Mo": 12.0, "Ma": 17.0, "Me": 14.0, "Ju": 11.0, "Ve": 10.0, "Sa": 15.0}

BAV_RULES = {
    "Su": {"Su":[1,2,4,7,8,9,10,11], "Mo":[3,6,10,11], "Ma":[1,2,4,7,8,9,10,11], "Me":[3,5,6,9,10,11,12], "Ju":[5,6,9,11], "Ve":[6,7,12], "Sa":[1,2,4,7,8,9,10,11], "As":[3,4,6,10,11,12]},
    "Mo": {"Su":[3,6,7,8,10,11], "Mo":[1,3,6,7,10,11], "Ma":[2,3,5,6,9,10,11], "Me":[1,3,4,5,7,8,10,11], "Ju":[1,4,7,8,10,11,12], "Ve":[3,4,5,7,9,10,11], "Sa":[3,5,6,11], "As":[3,6,10,11]},
    "Ma": {"Su":[3,5,6,10,11], "Mo":[3,6,11], "Ma":[1,2,4,7,8,10,11], "Me":[3,5,6,11], "Ju":[6,10,11,12], "Ve":[6,8,11,12], "Sa":[1,4,7,8,9,10,11], "As":[1,3,6,10,11]},
    "Me": {"Su":[5,6,9,11,12], "Mo":[2,4,6,8,10,11], "Ma":[1,2,4,7,8,9,10,11], "Me":[1,3,5,6,9,10,11,12], "Ju":[6,8,11,12], "Ve":[1,2,3,4,5,8,9,11], "Sa":[1,2,4,7,8,9,10,11], "As":[1,2,4,6,8,10,11]},
    "Ju": {"Su":[1,2,3,4,7,8,9,10,11], "Mo":[2,5,7,9,11], "Ma":[1,2,4,7,8,10,11], "Me":[1,2,4,5,6,9,10,11], "Ju":[1,2,3,4,7,8,10,11], "Ve":[2,5,6,9,10,11], "Sa":[3,5,6,12], "As":[1,2,4,5,6,7,9,10,11]},
    "Ve": {"Su":[8,11,12], "Mo":[1,2,3,4,5,8,9,11,12], "Ma":[3,5,6,9,11,12], "Me":[3,5,6,9,11], "Ju":[5,8,9,10,11], "Ve":[1,2,3,4,5,8,9,10,11], "Sa":[3,4,5,8,9,10,11], "As":[1,2,3,4,5,8,9,11]},
    "Sa": {"Su":[1,2,4,7,8,10,11], "Mo":[3,6,11], "Ma":[3,5,6,10,11,12], "Me":[6,8,9,10,11,12], "Ju":[5,6,11,12], "Ve":[6,11,12], "Sa":[3,5,6,11], "As":[1,3,4,6,10,11]}
}

RAHU_PART = {6: 7, 0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2}
GULIKA_PART = {6: 6, 0: 5, 1: 4, 2: 3, 3: 2, 4: 1, 5: 0}

swe.set_sid_mode(swe.SIDM_KRISHNAMURTI, 0, 0)

# ==========================================
# 3. SHASTRA & EXACT TIMING ENGINES
# ==========================================
def fmt_local_ist(dt_local, fmt="%I:%M %p"):
    ist_str = dt_local.astimezone(IST_TZ).strftime(fmt)
    loc_str = dt_local.strftime(fmt)
    if dt_local.tzinfo.zone == "Asia/Kolkata":
        return f"{loc_str} IST"
    return f"{loc_str} ({ist_str} IST)"

def deg_to_dms(deg):
    d = int(deg)
    m = int((deg - d) * 60)
    s = int((((deg - d) * 60) - m) * 60)
    return f"{d:02d}°{m:02d}'{s:02d}"

def get_relationship(day_lord, hora_lord):
    if day_lord == hora_lord:
        return "Swastha (Self)", "Anchor / High Volatility"
    rel = MAITRI.get(day_lord, {})
    if hora_lord in rel.get("friends", []):
        return "Mitra (Friend)", "Trend Continuation (BOS)"
    elif hora_lord in rel.get("enemies", []):
        return "Ghor Shatru (Enemy)", "Trap / Mean-Reversion Only"
    return "Sam (Neutral)", "Range Scalp / Mixed"

def get_varesh_summary(day_lord):
    rel = MAITRI[day_lord]
    return f"Mitra:[{','.join(rel['friends'])}] | Shatru:[{','.join(rel['enemies']) or 'None'}] | Sam:[{','.join(rel['neutral'])}]"

def get_baladi_avastha(rashi_num, deg_in_rashi):
    idx = int(deg_in_rashi // 6.0)
    if rashi_num % 2 == 0: idx = 4 - idx
    return ["Baal(25%)", "Kumar(50%)", "Yuva(100%)", "Vriddha(20%)", "Mrit(0%)"][max(0, min(4, idx))]

def compute_shadbala_rupas(p_name, lon, speed, h_d1, is_day, su_lon, mo_lon):
    if p_name not in SHADBALA_REQ:
        return "N/A", False
    uchha_pt = PARAM_UCHHA_DEG[p_name]
    neech_pt = (uchha_pt + 180.0) % 360.0
    dist_neech = min(abs(lon - neech_pt), 360.0 - abs(lon - neech_pt))
    uchha_bala = dist_neech / 3.0
    kendra_bala = 60.0 if h_d1 in [1, 4, 7, 10] else (30.0 if h_d1 in [2, 5, 8, 11] else 15.0)
    
    dig_targets = {"Me": 1, "Ju": 1, "Mo": 4, "Ve": 4, "Sa": 7, "Su": 10, "Ma": 10}
    diff_h = abs(h_d1 - dig_targets[p_name])
    if diff_h > 6: diff_h = 12 - diff_h
    dig_bala = (6 - diff_h) * 10.0
    
    day_strong = p_name in ["Su", "Ju", "Ve"]
    kaala_bala = 45.0 if (is_day == day_strong or p_name == "Me") else 15.0
    if p_name == "Mo":
        elong = (mo_lon - su_lon) % 360.0
        kaala_bala += (elong / 3.0) if elong <= 180 else ((360.0 - elong) / 3.0)
        
    cheshta_bala = 60.0 if speed < 0 else 30.0
    nais_bala = NAISARGIKA_BALA[p_name]
    total_rupas = (uchha_bala + kendra_bala + dig_bala + kaala_bala + cheshta_bala + nais_bala + 45.0) / 60.0
    is_strong = (total_rupas / SHADBALA_REQ[p_name]) >= 1.0
    return f"{total_rupas:.2f}R({'STRONG' if is_strong else 'WEAK'})", is_strong

def compute_sav_points(rashi_signs_dict):
    sav = [0] * 12
    for target_p, rules in BAV_RULES.items():
        for source_p, houses in rules.items():
            if source_p in rashi_signs_dict:
                src_idx = rashi_signs_dict[source_p]
                for h in houses:
                    sav[(src_idx + h - 1) % 12] += 1
    return sav

def evaluate_trinity_alignment(day_lord, tithi_lord, hora_lord):
    f_tithi = (tithi_lord == day_lord) or (tithi_lord in MAITRI.get(day_lord, {}).get("friends", []))
    f_hora = (hora_lord == day_lord) or (hora_lord in MAITRI.get(day_lord, {}).get("friends", []))
    if f_tithi and f_hora:
        return f"🔥 TRINITY ALIGNED ({day_lord}+{tithi_lord}+{hora_lord}): Grade A+ Trend Expansion"
    elif not f_tithi and not f_hora:
        return f"⚠️ TRINITY CLASH ({day_lord} vs {tithi_lord}/{hora_lord}): Trap / Mean-Reversion Only"
    return f"⚖️ PARTIAL ALIGNMENT ({day_lord}/{tithi_lord}/{hora_lord}): Standard Technical Confluence"

def get_kp_full(deg):
    """Calculates Rashi, Navamsha, Nakshatra, NL, SL, and 3rd-level SSL (Sub-Sub-Lord)."""
    deg = deg % 360.0
    rashi_idx = int(deg // 30.0)
    rashi = RASHIS[rashi_idx]
    deg_in_rashi = deg % 30.0
    nav_idx = int(deg_in_rashi // (30.0 / 9.0))
    d9_rashi = RASHIS[(rashi_idx * 9 + nav_idx) % 12]
    
    nak_span = 360.0 / 27.0
    nak_idx = int(deg // nak_span)
    nak_name = NAKSHATRAS[nak_idx]
    nl_idx = nak_idx % 9
    nl = DASHA_LORDS[nl_idx]
    rem_nak = deg - (nak_idx * nak_span)
    pada = int(rem_nak // (nak_span / 4.0)) + 1
    
    curr, sl, sl_idx, sl_start, sl_span = 0.0, nl, nl_idx, 0.0, nak_span
    for i in range(9):
        idx = (nl_idx + i) % 9
        span = (DASHA_YEARS[idx] / 120.0) * nak_span
        if curr <= rem_nak < (curr + span):
            sl = DASHA_LORDS[idx]
            sl_idx = idx
            sl_start = curr
            sl_span = span
            break
        curr += span

    # 3rd Level Sub-Sub-Lord (SSL) for ultra-precise intraday scalp timing
    rem_sl = rem_nak - sl_start
    curr_ssl, ssl = 0.0, sl
    for j in range(9):
        idx2 = (sl_idx + j) % 9
        span2 = (DASHA_YEARS[idx2] / 120.0) * sl_span
        if curr_ssl <= rem_sl < (curr_ssl + span2):
            ssl = DASHA_LORDS[idx2]
            break
        curr_ssl += span2
        
    return {
        "rashi": rashi, "rashi_idx": rashi_idx, "rashi_num": rashi_idx + 1, "rashi_lord": RASHI_LORDS[rashi_idx],
        "tattva": TATTVA_MAP[rashi], "deg_in_rashi": deg_in_rashi,
        "is_sandhi": (deg_in_rashi >= 29.0 or deg_in_rashi <= 1.0),
        "d9": d9_rashi, "nak": nak_name, "nak_idx": nak_idx, "pada": pada, "nl": nl, "sl": sl, "ssl": ssl
    }

def calculate_planet_next_change(p_name, deg_in_rashi, speed, dt_local):
    if abs(speed) < 0.0001:
        return "Stationary (0 spd)", "Stationary (0 spd)"
    rem_deg = (30.0 - deg_in_rashi) if speed > 0 else deg_in_rashi
    days_left = rem_deg / abs(speed)
    
    label_type = "Rashi"
    if days_left > 45.0:
        pada_span = 30.0 / 9.0
        rem_pada = (pada_span - (deg_in_rashi % pada_span)) if speed > 0 else (deg_in_rashi % pada_span)
        days_left = rem_pada / abs(speed)
        label_type = "Pada"
        
    change_dt_loc = dt_local + datetime.timedelta(days=days_left)
    change_dt_ist = change_dt_loc.astimezone(IST_TZ)
    
    if days_left < 2.0:
        loc_s = f"{label_type}: {change_dt_loc.strftime('%d-%b %I:%M %p')}"
        ist_s = f"{change_dt_ist.strftime('%d-%b %I:%M %p')} IST"
    else:
        loc_s = f"{label_type}: {change_dt_loc.strftime('%d-%b-%y %H:%M')}"
        ist_s = f"{change_dt_ist.strftime('%d-%b-%y %H:%M')} IST"
    return loc_s, ist_s

def build_planet_trading_summary(p_name, kp, flags, avastha, is_strong, sav_val):
    reasons = []
    if "SANDHI" in flags:
        reasons.append("Rashi Sandhi (29°-1°): Extreme Whipsaw & Stop-Hunt Risk")
    if "NEECH" in flags:
        reasons.append(f"Neech in {kp['rashi']}: False Breakouts, Fade Extremes")
    elif "UCHHA" in flags:
        reasons.append(f"Uchha in {kp['rashi']}: High-Conviction Directional Momentum")
    if "VAKRI(R)" in flags and p_name not in ["Ra", "Ke"]:
        reasons.append("Vakri(R): Retests Old Gaps/FVG & Reverses")
    if "ASTA" in flags:
        reasons.append("Asta (Combust): Suppressed Follow-Through")
    if "Yuva" in avastha:
        reasons.append("Yuva(100%): Full Institutional Execution Power")
    elif "Mrit" in avastha or "Baal" in avastha:
        reasons.append(f"{avastha}: Weak Follow-Through, Scalp Only")
    if sav_val > 30:
        reasons.append(f"SAV:{sav_val}(Strong Support/Res)")
    elif sav_val < 24:
        reasons.append(f"SAV:{sav_val}(Fragile Zone)")
        
    if not reasons:
        return f"Normal ({kp['tattva']}): Standard Technical Confluence via {kp['nl']}/{kp['sl']}"
    return " | ".join(reasons[:2])

def get_next_aspect_timing(planet_lons, planet_speeds, dt_local):
    mo_lon = planet_lons["Mo"]
    mo_spd = planet_speeds["Mo"]
    targets = [0, 60, 90, 120, 180]
    best_hours = 999.0
    best_desc = ""
    
    for p_name, p_lon in planet_lons.items():
        if p_name == "Mo": continue
        rel_spd = mo_spd - planet_speeds.get(p_name, 0.0)
        if rel_spd <= 0.5: continue
        curr_diff = (mo_lon - p_lon) % 360.0
        for t in targets:
            for ang in ([t] if t in [0, 180] else [t, 360 - t]):
                rem = (ang - curr_diff) % 360.0
                hrs = (rem / rel_spd) * 24.0
                if 0.02 <= hrs < best_hours:
                    best_hours = hrs
                    best_desc = f"Mo-{t}°-{p_name}"
                    
    if best_hours < 48.0:
        hit_loc = dt_local + datetime.timedelta(hours=best_hours)
        mins_left = int(best_hours * 60)
        return f"Next Exact Aspect: {best_desc} in {mins_left}m at {fmt_local_ist(hit_loc)}"
    return "Aspect Matrix updates live every 1m (Moon moves ~0.5°/hr)"

def get_sunrise_sunset(target_date, lat, lon, tz):
    dt_mid = tz.localize(datetime.datetime.combine(target_date, datetime.time(0, 0, 0)))
    u = dt_mid.astimezone(pytz.UTC)
    jd_start = swe.julday(u.year, u.month, u.day, 0.0)
    geopos = (lon, lat, 0.0)
    _, tret_sr = swe.rise_trans(jd_start, swe.SUN, swe.CALC_RISE | swe.BIT_DISC_CENTER, geopos)
    _, tret_ss = swe.rise_trans(tret_sr[0], swe.SUN, swe.CALC_SET | swe.BIT_DISC_CENTER, geopos)
    _, tret_nsr = swe.rise_trans(tret_ss[0], swe.SUN, swe.CALC_RISE | swe.BIT_DISC_CENTER, geopos)
    
    def to_loc(j):
        y, m, d, h = swe.revjul(j)
        return (datetime.datetime(y, m, d, tzinfo=pytz.UTC) + datetime.timedelta(hours=h)).astimezone(tz)
    return to_loc(tret_sr[0]), to_loc(tret_ss[0]), to_loc(tret_nsr[0])

def get_nakshatra_end_time(dt_local):
    u = dt_local.astimezone(pytz.UTC)
    jd = swe.julday(u.year, u.month, u.day, u.hour + u.minute/60.0 + u.second/3600.0)
    res, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SIDEREAL | swe.FLG_SPEED)
    lon, speed = res[0] % 360.0, res[3]
    rem_deg = (360.0 / 27.0) - (lon % (360.0 / 27.0))
    hours_left = (rem_deg / speed) * 24.0 if speed > 0 else 12.0
    return dt_local + datetime.timedelta(hours=hours_left)

def get_current_lagna_window(dt_local, lat, lon):
    def asc_sign(d_obj):
        u = d_obj.astimezone(pytz.UTC)
        j = swe.julday(u.year, u.month, u.day, u.hour + u.minute/60.0 + u.second/3600.0)
        _, ascmc = swe.houses_ex(j, lat, lon, b'P', swe.FLG_SIDEREAL)
        return int((ascmc[0] % 360.0) // 30.0)
    curr_sign = asc_sign(dt_local)
    st, et = dt_local, dt_local
    while asc_sign(st - datetime.timedelta(minutes=1)) == curr_sign:
        st -= datetime.timedelta(minutes=1)
    while asc_sign(et + datetime.timedelta(minutes=1)) == curr_sign:
        et += datetime.timedelta(minutes=1)
    next_rashi = RASHIS[(curr_sign + 1) % 12]
    return st, et, next_rashi, TATTVA_MAP[next_rashi]

def to_sbc_index(lon):
    if 276.6667 <= lon <= 280.8889: return 21
    nak_27 = int((lon % 360.0) // (360.0 / 27.0))
    return nak_27 if nak_27 < 21 else nak_27 + 1

def evaluate_sarvatobhadra_vedha(planet_lons, planet_speeds, exchange_janma_nak_27, moon_nak_27):
    malefics, benefics = {"Sa", "Ma", "Ra", "Ke", "Su"}, {"Ju", "Ve", "Me"}
    exch_sbc = exchange_janma_nak_27 if exchange_janma_nak_27 < 21 else exchange_janma_nak_27 + 1
    moon_sbc = moon_nak_27 if moon_nak_27 < 21 else moon_nak_27 + 1
    mal_hits, ben_hits = [], []
    
    for p_name, lon in planet_lons.items():
        if p_name in ["Ur", "Ne", "Pl", "Mo"]: continue
        p_sbc = to_sbc_index(lon)
        spd = planet_speeds.get(p_name, 1.0)
        for off in [0, 6, 8, 14, 20, 22]:
            target = (p_sbc + off) % 28
            if target == exch_sbc or target == moon_sbc:
                ht = "Exch" if target == exch_sbc else "Moon"
                vt = "Front" if off in [0, 14] else ("Right" if off in [6, 8] else "Left")
                lbl = f"{p_name}{'(R)' if spd < 0 else ''}->{ht}[{vt}]"
                if p_name in malefics: mal_hits.append(lbl)
                else: ben_hits.append(lbl)
                
    if len(mal_hits) >= 2 and not ben_hits:
        return f"🔴 PAAP VEDHA ({', '.join(mal_hits[:2])}): Sudden Selloff / Trap Risk!"
    elif mal_hits and ben_hits:
        return f"🟡 MIXED VEDHA ({mal_hits[0]} vs {ben_hits[0]}): Two-Way Whipsaw."
    elif ben_hits:
        return f"🟢 SHUBHA VEDHA ({', '.join(ben_hits[:2])}): Strong Support & Clean Trend."
    return "🟢 VEDHA-FREE SKY: Technical Levels & Hora Hold Precision."

def get_karana_and_bhadra(tithi_deg, moon_rashi):
    k_idx = int(tithi_deg // 6.0)
    if k_idx == 0: k_name = "Kintughna"
    elif k_idx >= 57: k_name = ["Shakuni", "Chatushpada", "Naga"][k_idx - 57]
    else: k_name = CHARA_KARANAS[(k_idx - 1) % 7]
    
    bhadra_vaas = "Bhadra-Free"
    if "Vishti" in k_name:
        if moon_rashi in ["Cn", "Le", "Aq", "Pi"]: bhadra_vaas = "🔴 MRITYU LOK BHADRA"
        elif moon_rashi in ["Ar", "Ta", "Ge", "Sc"]: bhadra_vaas = "🟢 Swarga Bhadra"
        else: bhadra_vaas = "🟡 Patala Bhadra"
    return k_name, bhadra_vaas

def get_guru_bot_extras(dt_local, lat, lon, day_lord, mo_kp, asc_kp, planet_speeds):
    """Guru-level extra calculations for Telegram Bot: KP Ruling Planets, 3rd-level SSL & Out-of-Bounds Declination."""
    u = dt_local.astimezone(pytz.UTC)
    jd = swe.julday(u.year, u.month, u.day, u.hour + u.minute/60.0 + u.second/3600.0)
    
    # 1. KP Ruling Planets (5 Pillars)
    rps = [
        ("DayLord", day_lord),
        ("MoonSignLord", mo_kp["rashi_lord"]),
        ("MoonStarLord(NL)", mo_kp["nl"]),
        ("LagnaSignLord", asc_kp["rashi_lord"]),
        ("LagnaStarLord(NL)", asc_kp["nl"])
    ]
    retro_rps = [f"{role}:{p}" for role, p in rps if planet_speeds.get(p, 1.0) < 0 and p not in ["Ra", "Ke"]]
    rp_summary = ", ".join([f"{r}={p}" for r, p in rps])
    rp_warning = f"⚠️ VAKRI RPs ({len(retro_rps)}/5): {', '.join(retro_rps)} -> High Fakeout/Retest Risk!" if len(retro_rps) >= 2 else "✅ RPs Direct/Stable"

    # 2. Out-of-Bounds (OOB) Declination check (> 23.45 deg -> Commodity Spike Trigger)
    oob_list = []
    for p_name, p_id in [("Mo", swe.MOON), ("Ma", swe.MARS), ("Me", swe.MERCURY), ("Ju", swe.JUPITER), ("Ve", swe.VENUS), ("Sa", swe.SATURN)]:
        res_eq, _ = swe.calc_ut(jd, p_id, swe.FLG_EQUATORIAL)
        decl = abs(res_eq[1])
        if decl > 23.45:
            oob_list.append(f"{p_name}(Decl:{decl:.2f}° OOB!)")
    oob_str = ", ".join(oob_list) if oob_list else "None (All planets within 23.45°)"

    return (
        f"KP RULING PLANETS: {rp_summary} | {rp_warning}\n"
        f"3RD-LEVEL KP SSL: Moon SSL = {mo_kp['ssl']} | Lagna SSL = {asc_kp['ssl']}\n"
        f"OUT-OF-BOUNDS (OOB) COMMODITY SPIKE CHECK: {oob_str}"
    )

# ==========================================
# 4. MASTER QUADRANT MATRIX BUILDER (25 COLS)
# ==========================================
def build_city_matrix(target_date, city_name, cfg, is_live=False):
    tz = pytz.timezone(cfg["tz"])
    dt_local = datetime.datetime.now(tz) if is_live else tz.localize(datetime.datetime.combine(target_date, datetime.time(9, 15, 0)))
    dt_utc = dt_local.astimezone(pytz.UTC)
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0)
    
    M = [["" for _ in range(25)] for _ in range(60)]
    day_lord = WEEKDAY_LORDS[target_date.weekday()]
    
    sr_dt, ss_dt, nsr_dt = get_sunrise_sunset(target_date, cfg["lat"], cfg["lon"], tz)
    is_day = (sr_dt <= dt_local <= ss_dt)
    dinmaan_mins = (ss_dt - sr_dt).total_seconds() / 60.0
    part_dur = (ss_dt - sr_dt) / 8.0
    
    rk_idx = RAHU_PART[target_date.weekday()]
    rk_start, rk_end = sr_dt + (part_dur * rk_idx), sr_dt + (part_dur * (rk_idx + 1))
    gk_idx = GULIKA_PART[target_date.weekday()]
    gk_start, gk_end = sr_dt + (part_dur * gk_idx), sr_dt + (part_dur * (gk_idx + 1))
    
    in_rahu = (rk_start <= dt_local <= rk_end)
    in_gulika = (gk_start <= dt_local <= gk_end)

    # --- 24 HORA WITH SEPARATE LOCAL & IST START/END COLUMNS (Cols 17 to 24) ---
    start_idx = HORA_SEQUENCE.index(day_lord)
    day_dur = (ss_dt - sr_dt) / 12.0
    night_dur = (nsr_dt - ss_dt) / 12.0
    active_hora_lord = day_lord
    in_sandhi_kaal = False
    
    for i in range(24):
        h_lord = HORA_SEQUENCE[(start_idx + i) % 7]
        st = (sr_dt + day_dur * i) if i < 12 else (ss_dt + night_dur * (i - 12))
        et = (sr_dt + day_dur * (i + 1)) if i < 12 else (ss_dt + night_dur * (i - 11))
        rel_str, rule_str = get_relationship(day_lord, h_lord)
        
        is_curr = (st <= dt_local <= et)
        if is_curr:
            active_hora_lord = h_lord
            if is_live and ((dt_local - st).total_seconds()/60.0 <= 5.0 or (et - dt_local).total_seconds()/60.0 <= 5.0):
                in_sandhi_kaal = True
                
        mark = "👉 " if (is_curr and is_live) else ""
        M[2 + i][17] = f"{mark}{i + 1}"
        M[2 + i][18] = st.strftime("%I:%M %p")
        M[2 + i][19] = et.strftime("%I:%M %p")
        M[2 + i][20] = st.astimezone(IST_TZ).strftime("%I:%M %p")
        M[2 + i][21] = et.astimezone(IST_TZ).strftime("%I:%M %p")
        M[2 + i][22] = h_lord
        M[2 + i][23] = rel_str
        M[2 + i][24] = rule_str

    # --- TOP EXCHANGE HEADER ---
    M[0][0] = f"🌐 {city_name} ({cfg['tz']})"
    M[0][4] = f"LIVE: {fmt_local_ist(dt_local, '%d-%b %H:%M:%S')}"
    M[0][10] = f"Dinmaan: {dinmaan_mins:.1f}m | 1 Hora: {dinmaan_mins/12.0:.1f}m"
    M[0][17] = "24 Hora & Shastra Execution Matrix (Local & IST)"
    M[1][17], M[1][18], M[1][19], M[1][20], M[1][21], M[1][22], M[1][23], M[1][24] = (
        "H#", "Start(Loc)", "End(Loc)", "Start(IST)", "End(IST)", "Lord", "Varesh Relation", "Action Signal"
    )
    
    M[1][0] = "☀️ Sunrise:"
    M[1][1] = fmt_local_ist(sr_dt)
    M[1][4] = "🌇 Sunset:"
    M[1][5] = fmt_local_ist(ss_dt)
    M[1][8] = f"Varesh: {day_lord}"
    M[1][10] = get_varesh_summary(day_lord)

    # --- PLANETS, ASCENDANT (~2 HR LAGNA WINDOW), SHADBALA & SAV ---
    _, ascmc = swe.houses_ex(jd, cfg["lat"], cfg["lon"], b'P', swe.FLG_SIDEREAL)
    asc_deg = ascmc[0] % 360.0
    asc_kp = get_kp_full(asc_deg)
    lagna_st, lagna_et, next_lagna_rashi, next_lagna_tattva = get_current_lagna_window(dt_local, cfg["lat"], cfg["lon"])
    
    d1_houses = {i: [f"AS {int(asc_kp['deg_in_rashi'])}°"] if i == 1 else [] for i in range(1, 13)}
    d9_houses = {i: ["AS"] if i == 1 else [] for i in range(1, 13)}
    asc_r_idx = asc_kp["rashi_idx"]
    d9_asc_idx = RASHIS.index(asc_kp["d9"])
    
    planet_lons, planet_speeds = {}, {}
    rashi_signs_dict = {"As": asc_r_idx}
    
    su_res, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SIDEREAL | swe.FLG_SPEED)
    mo_res, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SIDEREAL | swe.FLG_SPEED)
    su_lon, mo_lon = su_res[0] % 360.0, mo_res[0] % 360.0
    
    raw_bodies = []
    for p_name, p_id in list(PLANETS.items()) + [("Ke", -1)]:
        if p_name == "Ke":
            ra_res, _ = swe.calc_ut(jd, swe.TRUE_NODE, swe.FLG_SIDEREAL | swe.FLG_SPEED)
            lon, speed = (ra_res[0] + 180.0) % 360.0, ra_res[3]
        else:
            res, _ = swe.calc_ut(jd, p_id, swe.FLG_SIDEREAL | swe.FLG_SPEED)
            lon, speed = res[0] % 360.0, res[3]
        planet_lons[p_name], planet_speeds[p_name] = lon, speed
        kp = get_kp_full(lon)
        rashi_signs_dict[p_name] = kp["rashi_idx"]
        raw_bodies.append((p_name, lon, speed, kp))

    sav_points = compute_sav_points(rashi_signs_dict)
    
    planet_rows = [[
        "As", deg_to_dms(asc_deg), asc_kp["rashi"], asc_kp["tattva"], asc_kp["nak"],
        asc_kp["nl"], asc_kp["sl"], "0.00", f"SAV:{sav_points[asc_r_idx]}", "Lagna (~2h)", "Active Horizon",
        f"Next {next_lagna_rashi}: {lagna_et.strftime('%I:%M %p')}",
        f"{lagna_et.astimezone(IST_TZ).strftime('%I:%M %p')} IST",
        f"{asc_kp['rashi']} [{asc_kp['tattva']}] active till {lagna_et.strftime('%I:%M %p')}; then {next_lagna_rashi} [{next_lagna_tattva}]"
    ]]
    
    for p_name, lon, speed, kp in raw_bodies:
        is_retro = (speed < 0) or (p_name in ["Ra", "Ke"])
        flags = []
        if EXALT_SIGNS.get(p_name) == kp["rashi"]: flags.append("UCHHA")
        elif DEBIL_SIGNS.get(p_name) == kp["rashi"]: flags.append("NEECH")
        elif kp["rashi_lord"] == p_name: flags.append("Swakshetra")
        if is_retro and p_name not in ["Ra", "Ke"]: flags.append("VAKRI(R)")
        if kp["is_sandhi"]: flags.append("SANDHI")
        if p_name in COMBUST_ORBS:
            if min(abs(lon - su_lon), 360.0 - abs(lon - su_lon)) <= COMBUST_ORBS[p_name]:
                flags.append("ASTA")
                
        h_d1 = ((kp["rashi_idx"] - asc_r_idx) % 12) + 1
        h_d9 = ((RASHIS.index(kp["d9"]) - d9_asc_idx) % 12) + 1
        deg_int = int(kp["deg_in_rashi"])
        d1_houses[h_d1].append(f"{p_name}{'R' if is_retro else ''} {deg_int}°")
        d9_houses[h_d9].append(f"{p_name}{'R' if is_retro else ''}")
        
        shadbala_str, is_strong = compute_shadbala_rupas(p_name, lon, speed, h_d1, is_day, su_lon, mo_lon)
        sav_val = sav_points[kp["rashi_idx"]]
        sav_tag = f"SAV:{sav_val}{'(Strong)' if sav_val>30 else ('(Weak)' if sav_val<24 else '')}"
        avastha_str = get_baladi_avastha(kp["rashi_num"], kp["deg_in_rashi"])
        next_loc, next_ist = calculate_planet_next_change(p_name, kp["deg_in_rashi"], speed, dt_local)
        summary_str = build_planet_trading_summary(p_name, kp, flags, avastha_str, is_strong, sav_val)
        
        planet_rows.append([
            p_name, deg_to_dms(lon), kp["rashi"], kp["tattva"], f"{kp['nak']}({kp['pada']})",
            kp["nl"], kp["sl"], f"{speed:.2f}", f"{shadbala_str} | {sav_tag}",
            avastha_str, " | ".join(flags) if flags else "Normal",
            next_loc, next_ist, summary_str
        ])

    mo_kp = get_kp_full(mo_lon)
    nak_end_dt = get_nakshatra_end_time(dt_local)
    tara_idx = ((mo_kp["nak_idx"] - cfg["janma_nak"]) % 27) % 9
    tara_name, tara_nat = TARA_NAMES[tara_idx]
    sbc_conclusion = evaluate_sarvatobhadra_vedha(planet_lons, planet_speeds, cfg["janma_nak"], mo_kp["nak_idx"])
    
    tithi_deg = (mo_lon - su_lon) % 360.0
    tithi_num = int(tithi_deg // 12.0) + 1
    paksha = "Shukla" if tithi_num <= 15 else "Krishna"
    tithi_lord = TITHI_LORDS_SEQ[(tithi_num - 1) % 8]
    trinity_verdict = evaluate_trinity_alignment(day_lord, tithi_lord, active_hora_lord)

    M[2][0] = "🌙 Moon Nakshatra:"
    M[2][1] = f"{mo_kp['nak']} (Ends: {fmt_local_ist(nak_end_dt)})"
    M[2][5] = "⭐ Tara Bala:"
    M[2][6] = f"{tara_name} ({tara_nat})"
    M[2][9] = "🧭 Live Lagna (~2h):"
    M[2][10] = f"{asc_kp['rashi']} [{asc_kp['tattva']}] ({fmt_local_ist(lagna_st)} - {fmt_local_ist(lagna_et)}) -> Next: {next_lagna_rashi}"

    M[3][0] = "🔮 SARVATOBHADRA (SBC):"
    M[3][2] = sbc_conclusion
    M[3][9] = "👑 TRINITY ALIGNMENT:"
    M[3][11] = trinity_verdict

    # --- D1 & D9 KUNDLI CHARTS ---
    M[13][2] = f"D1 Rashi Kundli (Lagna: {asc_kp['rashi']} | SAV: {sav_points[asc_r_idx]})"
    M[13][10] = "D9 Navamsha Kundli"
    diamond_map = {
        1: (6, 3), 2: (5, 1), 3: (7, 0), 4: (9, 1), 5: (11, 0), 6: (12, 1),
        7: (11, 3), 8: (12, 5), 9: (11, 6), 10: (9, 5), 11: (7, 6), 12: (5, 5)
    }
    for h, (r_o, c_o) in diamond_map.items():
        r_idx_h = (asc_r_idx + h - 1) % 12
        r_name_h = RASHIS[r_idx_h]
        r9_idx = (d9_asc_idx + h - 1) % 12
        M[r_o][c_o] = f"[{r_idx_h+1}-{r_name_h}|SAV:{sav_points[r_idx_h]}]\n{' '.join(d1_houses[h])}"
        M[r_o][c_o + 8] = f"[{r9_idx+1}-{RASHIS[r9_idx]}]\n{' '.join(d9_houses[h])}"

    # --- MACRO PANCHANG & SAFETY FILTERS ---
    yog_idx = int(((su_lon + mo_lon) % 360.0) // (360.0 / 27.0))
    yog_name, yog_nat = YOGAS[yog_idx]
    karana_name, bhadra_vaas = get_karana_and_bhadra(tithi_deg, mo_kp["rashi"])
    is_panchak = "YES (5x Swing)" if mo_kp["rashi"] in ["Aq", "Pi"] else "No"

    dangers = []
    if in_sandhi_kaal: dangers.append("⏸️ HORA SANDHI FREEZE (First/Last 5m)")
    if in_rahu: dangers.append("RAHU KAAL")
    if in_gulika: dangers.append("GULIKA KAAL")
    if "MRITYU" in bhadra_vaas: dangers.append("MRITYU BHADRA")
    if "Ghor Ashubha" in yog_nat: dangers.append(f"YOGA:{yog_name}")
    if "Ghor Ashubha" in tara_nat: dangers.append(f"TARA:{tara_name}")
    
    M[15][0], M[15][1] = "SAFETY FILTER:", (f"🔴 AVOID BREAKOUTS ({', '.join(dangers)})" if dangers else "🟢 SAFE EXECUTION WINDOW")
    M[16][0], M[16][1], M[16][2], M[16][3] = "Tithi (Lord)", "Karana & Bhadra", "Nitya Yoga", "Panchak"
    M[17][0] = f"{tithi_num} {paksha} ({tithi_lord})"
    M[17][1] = f"{karana_name} | {bhadra_vaas}"
    M[17][2] = f"{yog_name} ({yog_nat})"
    M[17][3] = is_panchak
    M[18][0], M[18][1] = "Rahu Kaal:", f"{fmt_local_ist(rk_start)} - {fmt_local_ist(rk_end)}"
    M[18][2], M[18][3] = "Gulika Kaal:", f"{fmt_local_ist(gk_start)} - {fmt_local_ist(gk_end)}"

    # --- 12x12 ASPECT MATRIX + EXACT NEXT ASPECT TIMING ---
    p_keys = list(planet_lons.keys())
    M[19][0] = "⏱️ ASPECT TIMING:"
    M[19][2] = get_next_aspect_timing(planet_lons, planet_speeds, dt_local)
    M[20][0] = "Aspect"
    for idx, pk in enumerate(p_keys):
        M[20][idx + 1] = pk
        M[21 + idx][0] = pk
        for jdx, pk2 in enumerate(p_keys):
            diff = min(abs(planet_lons[pk] - planet_lons[pk2]), 360.0 - abs(planet_lons[pk] - planet_lons[pk2]))
            M[21 + idx][jdx + 1] = f"{diff:.1f}"

    # --- PLANETARY SHASTRA TABLE ---
    p_headers = [
        "Body", "Longitude", "Rasi", "Tattva", "Nakshatra(P)", "NL", "SL", "Speed",
        "Shadbala & SAV", "Baladi Avastha", "Dignity & Flags",
        "Next Change (Local)", "Next Change (IST)", "Clear Trading Summary (With Reason)"
    ]
    for ci, ht in enumerate(p_headers):
        M[34][ci] = ht
    for ri, pr in enumerate(planet_rows):
        for ci, val in enumerate(pr):
            M[35 + ri][ci] = val

    guru_extras = get_guru_bot_extras(dt_local, cfg["lat"], cfg["lon"], day_lord, mo_kp, asc_kp, planet_speeds)
    return M, guru_extras

# ==========================================
# 5. DEEP INSTITUTIONAL TELEGRAM + GEMINI AI BOT
# ==========================================
def send_telegram_alert(message_text):
    """Sends deep astro-trading analysis to all authorized Chat IDs (comma-separated in Secrets)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    raw_chats = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not raw_chats:
        return
    chat_ids = [cid.strip() for cid in raw_chats.split(",") if cid.strip()]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Split message if > 4000 chars so Telegram never truncates deep analysis
    chunks = [message_text[i:i+3900] for i in range(0, len(message_text), 3900)]
    for cid in chat_ids:
        for chunk in chunks:
            payload = json.dumps({"chat_id": cid, "text": chunk}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=15)
            except Exception as e:
                print(f"Telegram send error for {cid}:", e)

def extract_city_snapshot(city_name, matrix, guru_extras):
    header = f"{matrix[0][0]} | {matrix[0][4]} | {matrix[0][10]}"
    varesh = f"{matrix[1][8]} ({matrix[1][10]})"
    lagna = f"{matrix[2][10]} | {matrix[2][6]}"
    sbc_trinity = f"SBC: {matrix[3][2]} | Trinity: {matrix[3][11]}"
    safety = f"Safety: {matrix[15][1]} | Rahu: {matrix[18][1]} | Gulika: {matrix[18][3]} | Aspect: {matrix[19][2]}"
    
    curr_hora, next_hora = "N/A", "N/A"
    for r in range(2, 26):
        if "👉" in str(matrix[r][17]):
            curr_hora = f"H#{matrix[r][17]} | Loc: {matrix[r][18]}-{matrix[r][19]} | IST: {matrix[r][20]}-{matrix[r][21]} | Lord: {matrix[r][22]} ({matrix[r][23]}) -> {matrix[r][24]}"
            if r + 1 < 26:
                next_hora = f"H#{matrix[r+1][17]} | Loc: {matrix[r+1][18]}-{matrix[r+1][19]} | IST: {matrix[r+1][20]}-{matrix[r+1][21]} | Lord: {matrix[r+1][22]} ({matrix[r+1][23]}) -> {matrix[r+1][24]}"
            break

    planets = [" | ".join([c for c in matrix[r][0:14] if c]) for r in range(35, 48)]
    return f"""
====================
EXCHANGE: {city_name}
====================
{header}
{varesh} | {lagna}
{sbc_trinity}
{safety}
{guru_extras}
CURRENT HORA: {curr_hora}
UPCOMING HORA: {next_hora}
PLANETARY TRANSIT TABLE:
{chr(10).join(planets)}
"""

def call_gemini_analyst(prompt_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt_text}]}]}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print("Gemini error:", e)
        return None

def check_and_send_session_alerts(target_date):
    """Triggers ONLY during active Session hours & merges overlapping sessions (Tokyo+London & London+NY)."""
    active_snapshots = {}
    trigger_reasons = {}

    for city, cfg in CITIES.items():
        tz = pytz.timezone(cfg["tz"])
        now_loc = datetime.datetime.now(tz)
        open_t, close_t = SESSION_WINDOWS_LOCAL[city]
        
        if not (open_t <= now_loc.time() <= close_t):
            continue
            
        matrix, guru_extras = build_city_matrix(target_date, city, cfg, is_live=True)
        active_snapshots[city] = extract_city_snapshot(city, matrix, guru_extras)
        reasons = []
        
        # Trigger A: Session Open Bell (at exact open minute)
        mins_since_open = (now_loc.hour * 60 + now_loc.minute) - (open_t.hour * 60 + open_t.minute)
        if 4 <= mins_since_open <= 5:
            reasons.append("🔔 SESSION OPEN BELL")
            
        # Trigger B: Upcoming Hora Shift (4 to 5.5 mins before current Hora ends)
        for r in range(2, 26):
            if "👉" in str(matrix[r][17]):
                end_dt = tz.localize(datetime.datetime.combine(
                    now_loc.date(), datetime.datetime.strptime(matrix[r][19], "%I:%M %p").time()
                ))
                if end_dt < now_loc:
                    end_dt += datetime.timedelta(days=1)
                mins_left = (end_dt - now_loc).total_seconds() / 60.0
                if 4.0 <= mins_left <= 5.5:
                    reasons.append(f"⏰ UPCOMING HORA SHIFT (in ~5m at {matrix[r][21]} IST)")
                break

        # Trigger C: ~2-Hour Lagna Shift (4 to 5.5 mins before current Lagna ends)
        _, lagna_et, next_lagna_rashi, next_lagna_tattva = get_current_lagna_window(now_loc, cfg["lat"], cfg["lon"])
        lagna_mins_left = (lagna_et - now_loc).total_seconds() / 60.0
        if 4.0 <= lagna_mins_left <= 5.5:
            reasons.append(f"🧭 LAGNA SHIFT (in ~5m -> {next_lagna_rashi} [{next_lagna_tattva}] at {lagna_et.astimezone(IST_TZ).strftime('%I:%M %p')} IST)")

        if reasons:
            alert_key = f"{city}_{now_loc.strftime('%Y-%m-%d_%H:%M')}"
            if alert_key not in SENT_ALERTS_CACHE:
                SENT_ALERTS_CACHE.add(alert_key)
                trigger_reasons[city] = " + ".join(reasons)

    if not trigger_reasons:
        return

    # 1. OVERLAP FUSION CHECK: London + New York OR Tokyo + London
    overlap_pairs = [("London_LSE", "New_York"), ("Tokyo_TSE", "London_LSE")]
    for ex1, ex2 in overlap_pairs:
        if ex1 in active_snapshots and ex2 in active_snapshots:
            if ex1 in trigger_reasons or ex2 in trigger_reasons:
                trig_combined = f"{ex1}: {trigger_reasons.get(ex1, 'Active')} | {ex2}: {trigger_reasons.get(ex2, 'Active')}"
                prompt = f"""
                You are a Grandmaster KP & Vedic Financial Astrologer writing a DEEP, STRICT, AND CLEAR institutional trading briefing in Hinglish (Hindi + English trading terms).
                TWO GLOBAL EXCHANGES ARE OVERLAPPING RIGHT NOW: {ex1} AND {ex2}!
                TRIGGER EVENT: {trig_combined}

                {active_snapshots[ex1]}
                {active_snapshots[ex2]}

                Provide a thorough, crystal-clear, deep explanation covering:
                1. 🔥 OVERLAP & TIMING FUSION ({ex1} + {ex2} in Local & IST): How both exchanges' Hora Lords, Dinmaan, and ~2-Hr Lagna Tattvas interact (Synergy vs Clash).
                2. 🧬 3-LAYER KP CHAIN & RULING PLANETS: Deep breakdown of Upcoming Hora Lord -> NL -> SL -> 3rd-level SSL, Shadbala/SAV strength, Baladi Avastha, and KP Ruling Planets (Vakri/Sandhi check).
                3. 🥇 GOLD (XAUUSD) DEEP VERDICT: Exact directional bias (Trend vs Trap/Reversal), liquidity sweep expectation, and planetary reasoning (Sun/Jupiter + Sub-Lords + OOB check).
                4. 🥈 SILVER (XAGUSD) DEEP VERDICT: Expected volatility, spike risk, and exact planetary reasoning (Moon/Venus + Sub-Lords).
                5. 🛑 STRICT TRAP & SAFETY FILTER: Exact IST & Local times for Hora Sandhi Freeze (first/last 5m), Rahu/Gulika Kaal, SBC Vedha, and exact Aspect Hit times.
                """
                verdict = call_gemini_analyst(prompt)
                if verdict:
                    send_telegram_alert(verdict)
                trigger_reasons.pop(ex1, None)
                trigger_reasons.pop(ex2, None)

    # 2. SINGLE ACTIVE SESSION ALERTS (Mumbai NSE Index/Stocks OR Standalone Tokyo / London / NY)
    for city, trig_label in trigger_reasons.items():
        asset_focus = (
            "3. 📈 NIFTY / BANKNIFTY / NSE INDEX DEEP VERDICT: Exact directional bias, institutional flow, and planetary reasoning (Sun/Mercury/Jupiter + Sub-Lords)."
            if city == "Mumbai_NSE" else
            "3. 🥇 GOLD (XAUUSD) & 🥈 SILVER (XAGUSD) SEPARATE DEEP VERDICTS: Give separate, detailed move predictions and exact astrological reasons for BOTH Gold (Sun/Ju) and Silver (Moon/Ve)."
        )
        prompt = f"""
        You are a Grandmaster KP & Vedic Financial Astrologer writing a DEEP, STRICT, AND CLEAR institutional trading briefing in Hinglish (Hindi + English trading terms).
        EXCHANGE: {city}
        TRIGGER EVENT: {trig_label}

        {active_snapshots[city]}

        Provide a thorough, crystal-clear, deep explanation covering:
        1. ⏰ EXACT TIMING, DINMAAN & LAGNA SHIFT (Local & IST): Explain the upcoming Hora & ~2-Hr Lagna Tattva impact on market speed.
        2. 🧬 3-LAYER KP CHAIN & RULING PLANETS: Deep breakdown of Hora Lord -> NL -> SL -> 3rd-level SSL, Shadbala/SAV, Baladi Avastha, Dignity/Flags, and KP Ruling Planets.
        {asset_focus}
        4. ⚠️ STRICT EXECUTION & TRAP CHECKLIST: Exact IST & Local times for Hora Sandhi Freeze (first/last 5m), Rahu/Gulika Kaal, SBC Vedha, and exact Aspect Hit times.
        """
        verdict = call_gemini_analyst(prompt)
        if verdict:
            send_telegram_alert(verdict)

# ==========================================
# 6. PROFESSIONAL STYLING, BORDERS & QUOTA-SAFE LOOP
# ==========================================
def safe_api_call(func, *args, **kwargs):
    for attempt in range(4):
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            if "429" in str(e):
                print("Quota limit hit (429), pausing 65s to reset...")
                time.sleep(65)
            else:
                raise e

def apply_professional_styling(ws):
    sheet_id = ws.id
    requests = [
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 130, "startColumnIndex": 0, "endColumnIndex": 55},
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"fontFamily": "Roboto", "fontSize": 9},
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(textFormat,verticalAlignment)"
            }
        }
    ]

    quadrants = [(0, 0), (0, 26), (63, 0), (63, 26)]
    header_colors = [
        {"red": 0.11, "green": 0.27, "blue": 0.53},
        {"red": 0.45, "green": 0.11, "blue": 0.35},
        {"red": 0.08, "green": 0.38, "blue": 0.25},
        {"red": 0.18, "green": 0.20, "blue": 0.25}
    ]
    solid_border = {"style": "SOLID_MEDIUM", "color": {"red": 0.25, "green": 0.25, "blue": 0.30}}
    thin_border = {"style": "SOLID", "color": {"red": 0.70, "green": 0.72, "blue": 0.78}}

    col_widths = [
        (0, 75), (1, 95), (2, 65), (3, 110), (4, 125), (5, 55), (6, 55), (7, 65),
        (8, 165), (9, 105), (10, 150), (11, 175), (12, 175), (13, 340), (14, 45),
        (15, 45), (16, 25), (17, 55), (18, 85), (19, 85), (20, 85), (21, 85),
        (22, 55), (23, 135), (24, 195)
    ]

    for idx, (r0, c0) in enumerate(quadrants):
        bg_col = header_colors[idx]
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r0 + 1, "startColumnIndex": c0, "endColumnIndex": c0 + 25},
                "cell": {"userEnteredFormat": {"backgroundColor": bg_col, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 10}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": r0 + 1, "endRowIndex": r0 + 2, "startColumnIndex": c0, "endColumnIndex": c0 + 25},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.90, "green": 0.93, "blue": 0.98}, "textFormat": {"bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"
            }
        })
        for chart_c in [c0, c0 + 8]:
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r0 + 5, "endRowIndex": r0 + 13, "startColumnIndex": chart_c, "endColumnIndex": chart_c + 7},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1.0, "green": 0.98, "blue": 0.90}, "textFormat": {"bold": True, "fontSize": 8}, "horizontalAlignment": "CENTER", "wrapStrategy": "WRAP"}},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,wrapStrategy)"
                }
            })
            requests.append({
                "updateBorders": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r0 + 5, "endRowIndex": r0 + 13, "startColumnIndex": chart_c, "endColumnIndex": chart_c + 7},
                    "top": solid_border, "bottom": solid_border, "left": solid_border, "right": solid_border,
                    "innerHorizontal": thin_border, "innerVertical": thin_border
                }
            })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": r0 + 34, "endRowIndex": r0 + 35, "startColumnIndex": c0, "endColumnIndex": c0 + 14},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.20, "green": 0.25, "blue": 0.33}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}, "wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat(backgroundColor,textFormat,wrapStrategy)"
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": r0 + 35, "endRowIndex": r0 + 48, "startColumnIndex": c0, "endColumnIndex": c0 + 14},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"
            }
        })
        requests.append({
            "updateBorders": {
                "range": {"sheetId": sheet_id, "startRowIndex": r0 + 34, "endRowIndex": r0 + 48, "startColumnIndex": c0, "endColumnIndex": c0 + 14},
                "top": solid_border, "bottom": solid_border, "left": solid_border, "right": solid_border,
                "innerHorizontal": thin_border, "innerVertical": thin_border
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": r0 + 1, "endRowIndex": r0 + 26, "startColumnIndex": c0 + 17, "endColumnIndex": c0 + 25},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"
            }
        })
        requests.append({
            "updateBorders": {
                "range": {"sheetId": sheet_id, "startRowIndex": r0 + 1, "endRowIndex": r0 + 26, "startColumnIndex": c0 + 17, "endColumnIndex": c0 + 25},
                "top": solid_border, "bottom": solid_border, "left": solid_border, "right": solid_border,
                "innerHorizontal": thin_border, "innerVertical": thin_border
            }
        })
        if r0 == 0:
            for offset_col, px_width in col_widths:
                requests.append({
                    "updateDimensionProperties": {
                        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": c0 + offset_col, "endIndex": c0 + offset_col + 1},
                        "properties": {"pixelSize": px_width},
                        "fields": "pixelSize"
                    }
                })

    cond_rules = [
        ("🟢", {"red": 0.85, "green": 0.96, "blue": 0.87}, {"red": 0.05, "green": 0.40, "blue": 0.15}),
        ("Mitra", {"red": 0.85, "green": 0.96, "blue": 0.87}, {"red": 0.05, "green": 0.40, "blue": 0.15}),
        ("UCHHA", {"red": 0.85, "green": 0.96, "blue": 0.87}, {"red": 0.05, "green": 0.40, "blue": 0.15}),
        ("TRINITY ALIGNED", {"red": 0.85, "green": 0.96, "blue": 0.87}, {"red": 0.05, "green": 0.40, "blue": 0.15}),
        ("🔴", {"red": 0.99, "green": 0.86, "blue": 0.86}, {"red": 0.65, "green": 0.05, "blue": 0.05}),
        ("Shatru", {"red": 0.99, "green": 0.86, "blue": 0.86}, {"red": 0.65, "green": 0.05, "blue": 0.05}),
        ("NEECH", {"red": 0.99, "green": 0.86, "blue": 0.86}, {"red": 0.65, "green": 0.05, "blue": 0.05}),
        ("👉", {"red": 1.0, "green": 0.94, "blue": 0.70}, {"red": 0.45, "green": 0.25, "blue": 0.0})
    ]
    for keyword, bg, fg in cond_rules:
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 130, "startColumnIndex": 0, "endColumnIndex": 55}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": keyword}]},
                        "format": {"backgroundColor": bg, "textFormat": {"foregroundColor": fg, "bold": True}}
                    }
                },
                "index": 0
            }
        })
    safe_api_call(sheet.batch_update, {"requests": requests})

def update_single_sheet(d, ws, is_live):
    title = d.strftime("%Y-%m-%d")
    if ws.col_count < 55 or ws.row_count < 130:
        safe_api_call(ws.resize, rows=130, cols=55)
    batch_updates = []
    for city, cfg in CITIES.items():
        matrix, _ = build_city_matrix(d, city, cfg, is_live=is_live)
        start_a1 = gspread.utils.rowcol_to_a1(cfg["row"], cfg["col"])
        end_a1 = gspread.utils.rowcol_to_a1(cfg["row"] + len(matrix) - 1, cfg["col"] + len(matrix[0]) - 1)
        batch_updates.append({"range": f"{start_a1}:{end_a1}", "values": matrix})
    safe_api_call(ws.batch_update, batch_updates, value_input_option="USER_ENTERED")
    print(f"[{datetime.datetime.now(IST_TZ).strftime('%H:%M:%S')}] Updated {'LIVE' if is_live else 'STATIC'}: {title}")

def run_live_engine():
    today_ist = datetime.datetime.now(IST_TZ).date()
    valid_dates = [today_ist + datetime.timedelta(days=i) for i in range(-DAYS_BACK, DAYS_AHEAD + 1)]
    valid_titles = {d.strftime("%Y-%m-%d") for d in valid_dates}
    existing_sheets = {ws.title: ws for ws in safe_api_call(sheet.worksheets)}
    
    # 1. Cleanup expired sheets
    for title, ws in existing_sheets.items():
        if title not in valid_titles and len(existing_sheets) > 1:
            safe_api_call(sheet.del_worksheet, ws)
            time.sleep(1.5)
            
    # 2. Create missing OR upgrade ANY sheet lacking the new IST + Colourful layout
    today_ws = None
    for d in valid_dates:
        title = d.strftime("%Y-%m-%d")
        is_today = (d == today_ist)
        if title not in existing_sheets:
            ws = safe_api_call(sheet.add_worksheet, title=title, rows=130, cols=55)
            update_single_sheet(d, ws, is_live=is_today)
            apply_professional_styling(ws)
            time.sleep(3.5)
        else:
            ws = existing_sheets[title]
            u2_val = safe_api_call(ws.acell, "U2").value
            if u2_val != "Start(IST)":
                update_single_sheet(d, ws, is_live=is_today)
                apply_professional_styling(ws)
                time.sleep(3.5)
        if is_today:
            today_ws = ws

    apply_professional_styling(today_ws)

    # 3. Every 1-Minute Live Loop for Today's Sheet + Session-Only Deep AI Telegram Bot
    for minute_tick in range(LIVE_LOOP_MINUTES):
        update_single_sheet(today_ist, today_ws, is_live=True)
        check_and_send_session_alerts(today_ist)
        if minute_tick < LIVE_LOOP_MINUTES - 1:
            time.sleep(60)

if __name__ == "__main__":
    run_live_engine()
