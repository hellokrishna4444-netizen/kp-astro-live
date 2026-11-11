import os
import json
import datetime
import pytz
import swisseph as swe
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. CONFIGURATION (LIMIT & WINDOW CONTROL)
# ==========================================
# Limit bachane ke liye yaha se din kam-zyada kar sakte hain (e.g., 15 aur 10 = 26 sheets)
DAYS_BACK = 15
DAYS_AHEAD = 10

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["GCP_SA_KEY"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SHEET_ID"])

# Exchanges with Coordinates, Timezone, and Founding Moon Nakshatra (0-26)
CITIES = {
    "Mumbai_NSE": {"lat": 19.0760, "lon": 72.8777, "tz": "Asia/Kolkata",     "row": 1,  "col": 1,  "janma_nak": 12}, # Hasta
    "Tokyo_TSE":  {"lat": 35.6762, "lon": 139.6503,"tz": "Asia/Tokyo",       "row": 1,  "col": 25, "janma_nak": 3},  # Rohini
    "London_LSE": {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London",    "row": 62, "col": 1,  "janma_nak": 9},  # Magha
    "New_York":   {"lat": 40.7128, "lon": -74.0060,"tz": "America/New_York", "row": 62, "col": 25, "janma_nak": 21}  # Shravana
}

IST_TZ = pytz.timezone("Asia/Kolkata")

# ==========================================
# 2. ASTROLOGICAL CONSTANTS & SHASTRA TABLES
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

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

# 28 Nakshatra Sequence for Sarvatobhadra Chakra (includes Abhijit between U.Ashadha & Shravana)
SBC_NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
    "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra",
    "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
    "Abhijit", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
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
    ("1-Janma", "Sensitive/Volatile"), ("2-Sampat", "Param Shubha (Wealth)"), ("3-Vipat", "Ashubha (Trap)"),
    ("4-Kshema", "Shubha (Safe)"), ("5-Pratyak", "Obstacle/Rejection"), ("6-Sadhaka", "Shubha (Target Hit)"),
    ("7-Vadha", "Ghor Ashubha (Crash)"), ("8-Mitra", "Shubha (Smooth)"), ("9-Parama Mitra", "Param Shubha (Expansion)")
]

MAITRI = {
    "Su": {"friends": ["Mo", "Ma", "Ju"], "enemies": ["Ve", "Sa"], "neutral": ["Me"]},
    "Mo": {"friends": ["Su", "Me"], "enemies": [], "neutral": ["Ma", "Ju", "Ve", "Sa"]},
    "Ma": {"friends": ["Su", "Mo", "Ju"], "enemies": ["Me"], "neutral": ["Ve", "Sa"]},
    "Me": {"friends": ["Su", "Ve"], "enemies": ["Mo"], "neutral": ["Ma", "Ju", "Sa"]},
    "Ju": {"friends": ["Su", "Mo", "Ma"], "enemies": ["Me", "Ve"], "neutral": ["Sa"]},
    "Ve": {"friends": ["Me", "Sa"], "enemies": ["Su", "Mo"], "neutral": ["Ma", "Ju"]},
    "Sa": {"friends": ["Me", "Ve"], "enemies": ["Su", "Mo", "Ma"], "neutral": ["Ju"]}
}

PLANETS = {
    "Su": swe.SUN, "Mo": swe.MOON, "Ma": swe.MARS, "Me": swe.MERCURY,
    "Ju": swe.JUPITER, "Ve": swe.VENUS, "Sa": swe.SATURN,
    "Ra": swe.TRUE_NODE, "Ur": swe.URANUS, "Ne": swe.NEPTUNE, "Pl": swe.PLUTO
}

EXALT_SIGNS = {"Su": "Ar", "Mo": "Ta", "Ma": "Cp", "Me": "Vi", "Ju": "Cn", "Ve": "Pi", "Sa": "Li", "Ra": "Ta", "Ke": "Sc"}
DEBIL_SIGNS = {"Su": "Li", "Mo": "Sc", "Ma": "Cn", "Me": "Pi", "Ju": "Cp", "Ve": "Vi", "Sa": "Ar", "Ra": "Sc", "Ke": "Ta"}
COMBUST_ORBS = {"Mo": 12.0, "Ma": 17.0, "Me": 14.0, "Ju": 11.0, "Ve": 10.0, "Sa": 15.0}

RAHU_PART = {6: 7, 0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2}
GULIKA_PART = {6: 6, 0: 5, 1: 4, 2: 3, 3: 2, 4: 1, 5: 0}

swe.set_sid_mode(swe.SIDM_KRISHNAMURTI, 0, 0)

# ==========================================
# 3. HELPER & ASTRONOMICAL FUNCTIONS
# ==========================================
def fmt_local_ist(dt_local, fmt="%I:%M %p"):
    """Formats time as '06:15 AM (02:45 AM IST)'."""
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
    f_str = ",".join(rel["friends"])
    e_str = ",".join(rel["enemies"]) if rel["enemies"] else "None"
    n_str = ",".join(rel["neutral"])
    return f"Mitra:[{f_str}] | Shatru:[{e_str}] | Sam:[{n_str}]"

def get_baladi_avastha(rashi_num, deg_in_rashi):
    idx = int(deg_in_rashi // 6.0)
    if rashi_num % 2 == 0:
        idx = 4 - idx
    return ["Baal (25%)", "Kumar (50%)", "Yuva (100%)", "Vriddha (20%)", "Mrit (0%)"][max(0, min(4, idx))]

def get_kp_full(deg):
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
    
    curr, sl, sl_idx, rem_sl, sl_span = 0.0, nl, nl_idx, 0.0, 0.0
    for i in range(9):
        idx = (nl_idx + i) % 9
        span = (DASHA_YEARS[idx] / 120.0) * nak_span
        if curr <= rem_nak < (curr + span):
            sl, sl_idx, rem_sl, sl_span = DASHA_LORDS[idx], idx, rem_nak - curr, span
            break
        curr += span
        
    curr_ssl, ssl = 0.0, sl
    for i in range(9):
        idx = (sl_idx + i) % 9
        span = (DASHA_YEARS[idx] / 120.0) * sl_span
        if curr_ssl <= rem_sl < (curr_ssl + span):
            ssl = DASHA_LORDS[idx]
            break
        curr_ssl += span
        
    return {
        "rashi": rashi, "rashi_num": rashi_idx + 1, "rashi_lord": RASHI_LORDS[rashi_idx],
        "tattva": TATTVA_MAP[rashi], "deg_in_rashi": deg_in_rashi,
        "is_sandhi": (deg_in_rashi >= 29.0 or deg_in_rashi <= 1.0),
        "d9": d9_rashi, "nak": nak_name, "nak_idx": nak_idx, "pada": pada,
        "nl": nl, "sl": sl, "ssl": ssl
    }

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

def get_nakshatra_end_time(dt_local, tz):
    """Finds exact time when current Moon Nakshatra ends."""
    u = dt_local.astimezone(pytz.UTC)
    jd = swe.julday(u.year, u.month, u.day, u.hour + u.minute/60.0 + u.second/3600.0)
    res, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SIDEREAL | swe.FLG_SPEED)
    lon, speed = res[0] % 360.0, res[3]
    nak_span = 360.0 / 27.0
    rem_deg = nak_span - (lon % nak_span)
    hours_left = (rem_deg / speed) * 24.0 if speed > 0 else 12.0
    return dt_local + datetime.timedelta(hours=hours_left)

def get_current_lagna_window(dt_local, lat, lon, tz):
    """Finds exact Start and End time of the current active Lagna."""
    def asc_sign(d_obj):
        u = d_obj.astimezone(pytz.UTC)
        j = swe.julday(u.year, u.month, u.day, u.hour + u.minute/60.0 + u.second/3600.0)
        _, ascmc = swe.houses_ex(j, lat, lon, b'P', swe.FLG_SIDEREAL)
        return int((ascmc[0] % 360.0) // 30.0)
        
    curr_sign = asc_sign(dt_local)
    st = dt_local
    while asc_sign(st - datetime.timedelta(minutes=2)) == curr_sign:
        st -= datetime.timedelta(minutes=2)
    et = dt_local
    while asc_sign(et + datetime.timedelta(minutes=2)) == curr_sign:
        et += datetime.timedelta(minutes=2)
    return st, et

def to_sbc_index(lon):
    """Maps 360° Sidereal longitude into 28-Nakshatra Sarvatobhadra Chakra index (0-27)."""
    # Abhijit spans 276°40' (Capricorn 6°40') to 280°53'20" (Capricorn 10°53'20")
    if 276.6667 <= lon <= 280.8889:
        return 21 # Abhijit
    nak_27 = int((lon % 360.0) // (360.0 / 27.0))
    return nak_27 if nak_27 < 21 else nak_27 + 1

def evaluate_sarvatobhadra_vedha(planet_lons, planet_speeds, exchange_janma_nak_27, moon_nak_27):
    """Calculates SBC Front (15th), Right (7th/9th), and Left (21st/23rd) Vedhas on Exchange & Moon."""
    malefics = {"Sa", "Ma", "Ra", "Ke", "Su"}
    benefics = {"Ju", "Ve", "Me"}
    
    # Convert 27-nak index to 28-nak SBC index
    exch_sbc = exchange_janma_nak_27 if exchange_janma_nak_27 < 21 else exchange_janma_nak_27 + 1
    moon_sbc = moon_nak_27 if moon_nak_27 < 21 else moon_nak_27 + 1
    
    malefic_hits = []
    benefic_hits = []
    
    # Standard SBC Vedha offsets on 28-Nakshatra square grid
    vedha_offsets = [0, 6, 8, 14, 20, 22] # Conjunction(0), Right(6,8), Front/Opposite(14), Left(20,22)
    
    for p_name, lon in planet_lons.items():
        if p_name in ["Ur", "Ne", "Pl", "Mo"]:
            continue
        p_sbc = to_sbc_index(lon)
        spd = planet_speeds.get(p_name, 1.0)
        # Retrograde planets cast stronger reverse/forward Vedha
        for off in vedha_offsets:
            target_sbc = (p_sbc + off) % 28
            if target_sbc == exch_sbc or target_sbc == moon_sbc:
                hit_target = "Exchange Janma" if target_sbc == exch_sbc else "Live Moon"
                v_type = "Front/Direct" if off in [0, 14] else ("Right" if off in [6, 8] else "Left")
                label = f"{p_name}{'(R)' if spd < 0 else ''}->{hit_target}[{v_type}]"
                if p_name in malefics:
                    malefic_hits.append(label)
                elif p_name in benefics:
                    benefic_hits.append(label)
                    
    if len(malefic_hits) >= 2 and not benefic_hits:
        verdict = f"🔴 SEVERE PAAP VEDHA ({', '.join(malefic_hits[:2])}): Sudden Selloff / Trap Risk!"
    elif malefic_hits and benefic_hits:
        verdict = f"🟡 MIXED VEDHA (Malefic: {malefic_hits[0]} vs Benefic: {benefic_hits[0]}): Two-Way Whipsaw."
    elif benefic_hits:
        verdict = f"🟢 SHUBHA VEDHA ({', '.join(benefic_hits[:2])}): Strong Institutional Support & Clean Trend."
    else:
        verdict = "🟢 VEDHA-FREE (Clean Sky): Technical Levels & Hora Will Hold Precision."
    return verdict

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

# ==========================================
# 4. MASTER QUADRANT MATRIX BUILDER
# ==========================================
def build_city_matrix(target_date, city_name, cfg, is_live=False):
    tz = pytz.timezone(cfg["tz"])
    dt_local = datetime.datetime.now(tz) if is_live else tz.localize(datetime.datetime.combine(target_date, datetime.time(9, 15, 0)))
    dt_utc = dt_local.astimezone(pytz.UTC)
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0)
    
    M = [["" for _ in range(23)] for _ in range(58)]
    day_lord = WEEKDAY_LORDS[target_date.weekday()]
    
    # Sunrise, Sunset, Dinmaan (Local + IST)
    sr_dt, ss_dt, nsr_dt = get_sunrise_sunset(target_date, cfg["lat"], cfg["lon"], tz)
    dinmaan_mins = (ss_dt - sr_dt).total_seconds() / 60.0
    part_dur = (ss_dt - sr_dt) / 8.0
    
    rk_idx = RAHU_PART[target_date.weekday()]
    rk_start, rk_end = sr_dt + (part_dur * rk_idx), sr_dt + (part_dur * (rk_idx + 1))
    gk_idx = GULIKA_PART[target_date.weekday()]
    gk_start, gk_end = sr_dt + (part_dur * gk_idx), sr_dt + (part_dur * (gk_idx + 1))
    
    in_rahu = (rk_start <= dt_local <= rk_end)
    in_gulika = (gk_start <= dt_local <= gk_end)

    # --- TOP EXCHANGE HEADER (Rows 0 to 4) ---
    M[0][0] = f"🌐 {city_name} ({cfg['tz']})"
    M[0][4] = f"LIVE TIME: {fmt_local_ist(dt_local, '%d-%b %H:%M:%S')}"
    M[0][10] = f"Dinmaan: {dinmaan_mins:.1f}m | 1 Hora: {dinmaan_mins/12.0:.1f}m"
    
    M[1][0] = "☀️ Sunrise:"
    M[1][1] = fmt_local_ist(sr_dt)
    M[1][4] = "🌇 Sunset:"
    M[1][5] = fmt_local_ist(ss_dt)
    M[1][8] = f"Varesh (Day Lord): {day_lord}"
    M[1][10] = get_varesh_summary(day_lord)

    # --- PLANETS & ASCENDANT ---
    _, ascmc = swe.houses_ex(jd, cfg["lat"], cfg["lon"], b'P', swe.FLG_SIDEREAL)
    asc_deg = ascmc[0] % 360.0
    asc_kp = get_kp_full(asc_deg)
    lagna_st, lagna_et = get_current_lagna_window(dt_local, cfg["lat"], cfg["lon"], tz)
    
    d1_houses = {i: ["AS"] if i == 1 else [] for i in range(1, 13)}
    d9_houses = {i: ["AS"] if i == 1 else [] for i in range(1, 13)}
    asc_r_idx = asc_kp["rashi_num"] - 1
    d9_asc_idx = RASHIS.index(asc_kp["d9"])
    
    planet_lons, planet_speeds, planet_lats, planet_rows = {}, {}, {}, []
    su_res, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SIDEREAL | swe.FLG_SPEED)
    su_lon = su_res[0] % 360.0
    
    planet_rows.append([
        "As", deg_to_dms(asc_deg), asc_kp["rashi"], asc_kp["tattva"], asc_kp["nak"],
        asc_kp["pada"], asc_kp["nl"], asc_kp["sl"], "0.00", "Lagna", "Active Horizon"
    ])
    
    for p_name, p_id in list(PLANETS.items()) + [("Ke", -1)]:
        if p_name == "Ke":
            ra_res, _ = swe.calc_ut(jd, swe.TRUE_NODE, swe.FLG_SIDEREAL | swe.FLG_SPEED)
            lon, lat_p, speed = (ra_res[0] + 180.0) % 360.0, -ra_res[1], ra_res[3]
        else:
            res, _ = swe.calc_ut(jd, p_id, swe.FLG_SIDEREAL | swe.FLG_SPEED)
            lon, lat_p, speed = res[0] % 360.0, res[1], res[3]
            
        planet_lons[p_name], planet_speeds[p_name], planet_lats[p_name] = lon, speed, lat_p
        kp = get_kp_full(lon)
        is_retro = (speed < 0) or (p_name in ["Ra", "Ke"])
        
        flags = []
        if EXALT_SIGNS.get(p_name) == kp["rashi"]: flags.append("UCHHA")
        elif DEBIL_SIGNS.get(p_name) == kp["rashi"]: flags.append("NEECH")
        elif kp["rashi_lord"] == p_name: flags.append("Swakshetra")
        if is_retro and p_name not in ["Ra", "Ke"]: flags.append("VAKRI(R)")
        if kp["is_sandhi"]: flags.append("SANDHI")
        if p_name in COMBUST_ORBS:
            diff_su = min(abs(lon - su_lon), 360.0 - abs(lon - su_lon))
            if diff_su <= COMBUST_ORBS[p_name]: flags.append("ASTA(Combust)")
            
        h_d1 = ((kp["rashi_num"] - 1 - asc_r_idx) % 12) + 1
        h_d9 = ((RASHIS.index(kp["d9"]) - d9_asc_idx) % 12) + 1
        lbl = f"{p_name}R" if is_retro else p_name
        d1_houses[h_d1].append(lbl)
        d9_houses[h_d9].append(lbl)
        
        planet_rows.append([
            p_name, deg_to_dms(lon), kp["rashi"], kp["tattva"], kp["nak"],
            kp["pada"], kp["nl"], kp["sl"], f"{speed:.3f}",
            get_baladi_avastha(kp["rashi_num"], kp["deg_in_rashi"]),
            " | ".join(flags) if flags else "Normal"
        ])

    # Moon Nakshatra, End Time, Tara Bala & SBC Conclusion
    mo_lon = planet_lons["Mo"]
    mo_kp = get_kp_full(mo_lon)
    nak_end_dt = get_nakshatra_end_time(dt_local, tz)
    tara_idx = ((mo_kp["nak_idx"] - cfg["janma_nak"]) % 27) % 9
    tara_name, tara_nat = TARA_NAMES[tara_idx]
    sbc_conclusion = evaluate_sarvatobhadra_vedha(planet_lons, planet_speeds, cfg["janma_nak"], mo_kp["nak_idx"])

    M[2][0] = "🌙 Moon Nakshatra:"
    M[2][1] = f"{mo_kp['nak']} (Ends: {fmt_local_ist(nak_end_dt)})"
    M[2][5] = "⭐ Tara Bala:"
    M[2][6] = f"{tara_name} - {tara_nat}"
    M[2][9] = "🧭 Live Lagna:"
    M[2][10] = f"{asc_kp['rashi']} [{asc_kp['tattva']}] ({fmt_local_ist(lagna_st)} - {fmt_local_ist(lagna_et)})"

    M[3][0] = "🔮 SARVATOBHADRA (SBC) CONCLUSION:"
    M[3][2] = sbc_conclusion

    # --- 24 HORA TABLE HEADER (Cols 17 to 22) ---
    M[0][17] = "24 Hora & Shastra Execution Matrix"
    M[1][17], M[1][18], M[1][19], M[1][20], M[1][21], M[1][22] = "H#", "Start (Loc)", "End (Loc)", "Lord", "Varesh Relation", "Action Signal"

    # --- D1 & D9 DIAMOND CHARTS (Rows 5 to 13) ---
    M[13][2] = "D1 Rashi Chart"
    M[13][10] = "D9 Navamsha Chart"
    diamond_map = {
        1: (6, 3), 2: (5, 1), 3: (7, 0), 4: (9, 1), 5: (11, 0), 6: (12, 1),
        7: (11, 3), 8: (12, 5), 9: (11, 6), 10: (9, 5), 11: (7, 6), 12: (5, 5)
    }
    for h, (r_o, c_o) in diamond_map.items():
        r1 = ((asc_r_idx + h - 1) % 12) + 1
        r9 = ((d9_asc_idx + h - 1) % 12) + 1
        M[r_o][c_o] = f"[{r1}] {' '.join(d1_houses[h])}"
        M[r_o][c_o + 8] = f"[{r9}] {' '.join(d9_houses[h])}"

    # --- MACRO PANCHANG & SAFETY FILTERS (Rows 15 to 19) ---
    tithi_deg = (mo_lon - su_lon) % 360.0
    tithi_num = int(tithi_deg // 12.0) + 1
    paksha = "Shukla" if tithi_num <= 15 else "Krishna"
    yog_idx = int(((su_lon + mo_lon) % 360.0) // (360.0 / 27.0))
    yog_name, yog_nat = YOGAS[yog_idx]
    karana_name, bhadra_vaas = get_karana_and_bhadra(tithi_deg, mo_kp["rashi"])
    is_panchak = "YES (5x Swing)" if mo_kp["rashi"] in ["Aq", "Pi"] else "No"

    dangers = []
    if in_rahu: dangers.append("RAHU KAAL")
    if in_gulika: dangers.append("GULIKA KAAL")
    if "MRITYU" in bhadra_vaas: dangers.append("MRITYU BHADRA")
    if "Ghor Ashubha" in yog_nat: dangers.append(f"YOGA:{yog_name}")
    if "Ghor Ashubha" in tara_nat: dangers.append(f"TARA:{tara_name}")
    
    M[15][0], M[15][1] = "SAFETY FILTER:", (f"🔴 AVOID BREAKOUTS ({', '.join(dangers)})" if dangers else "🟢 SAFE WINDOW")
    M[16][0], M[16][1], M[16][2], M[16][3] = "Tithi & Paksha", "Karana & Bhadra", "Nitya Yoga", "Panchak"
    M[17][0] = f"{tithi_num} ({paksha})"
    M[17][1] = f"{karana_name} | {bhadra_vaas}"
    M[17][2] = f"{yog_name} ({yog_nat})"
    M[17][3] = is_panchak
    M[18][0], M[18][1] = "Rahu Kaal:", f"{fmt_local_ist(rk_start)} - {fmt_local_ist(rk_end)}"
    M[18][2], M[18][3] = "Gulika Kaal:", f"{fmt_local_ist(gk_start)} - {fmt_local_ist(gk_end)}"

    # --- 12x12 ASPECT MATRIX (Rows 20 to 32) ---
    p_keys = list(planet_lons.keys())
    M[20][0] = "Aspect"
    for idx, pk in enumerate(p_keys):
        M[20][idx + 1] = pk
        M[21 + idx][0] = pk
        for jdx, pk2 in enumerate(p_keys):
            diff = min(abs(planet_lons[pk] - planet_lons[pk2]), 360.0 - abs(planet_lons[pk] - planet_lons[pk2]))
            M[21 + idx][jdx + 1] = f"{diff:.1f}"

    # --- PLANETARY SHASTRA TABLE (Rows 34 to 46) ---
    p_headers = ["Body", "Longitude", "Rasi", "Tattva", "Nakshatra", "Pada", "NL", "SL", "Speed", "Baladi Avastha", "Dignity & Flags"]
    for ci, ht in enumerate(p_headers):
        M[34][ci] = ht
    for ri, pr in enumerate(planet_rows):
        for ci, val in enumerate(pr):
            M[35 + ri][ci] = val

    # --- 24 HORA POPULATE (Rows 2 to 25, Cols 17 to 22) ---
    start_idx = HORA_SEQUENCE.index(day_lord)
    day_dur = (ss_dt - sr_dt) / 12.0
    night_dur = (nsr_dt - ss_dt) / 12.0
    for i in range(24):
        h_lord = HORA_SEQUENCE[(start_idx + i) % 7]
        st = (sr_dt + day_dur * i) if i < 12 else (ss_dt + night_dur * (i - 12))
        et = (sr_dt + day_dur * (i + 1)) if i < 12 else (ss_dt + night_dur * (i - 11))
        rel_str, rule_str = get_relationship(day_lord, h_lord)
        mark = "👉 " if (st <= dt_local <= et and is_live) else ""
        M[2 + i][17] = f"{mark}{i + 1}"
        M[2 + i][18] = st.strftime("%I:%M %p")
        M[2 + i][19] = et.strftime("%I:%M %p")
        M[2 + i][20] = h_lord
        M[2 + i][21] = rel_str
        M[2 + i][22] = rule_str

    return M

# ==========================================
# 5. ROLLING SHEET SYNC (QUOTA SAFE)
# ==========================================
def sync_rolling_sheets():
    today_ist = datetime.datetime.now(IST_TZ).date()
    valid_dates = [today_ist + datetime.timedelta(days=i) for i in range(-DAYS_BACK, DAYS_AHEAD + 1)]
    valid_titles = {d.strftime("%Y-%m-%d") for d in valid_dates}
    
    existing_sheets = {ws.title: ws for ws in sheet.worksheets()}
    
    # Delete expired sheets
    for title, ws in existing_sheets.items():
        if title not in valid_titles and len(existing_sheets) > 1:
            sheet.del_worksheet(ws)
            print(f"Deleted old sheet: {title}")
            
    # Create missing sheets & Update ONLY Today live (saves 96% API quota)
    for d in valid_dates:
        title = d.strftime("%Y-%m-%d")
        is_today = (d == today_ist)
        
        if title not in existing_sheets:
            ws = sheet.add_worksheet(title=title, rows=125, cols=50)
            needs_update = True
        else:
            ws = existing_sheets[title]
            needs_update = is_today
            
        if needs_update:
            batch_updates = []
            for city, cfg in CITIES.items():
                matrix = build_city_matrix(d, city, cfg, is_live=is_today)
                start_a1 = gspread.utils.rowcol_to_a1(cfg["row"], cfg["col"])
                end_a1 = gspread.utils.rowcol_to_a1(cfg["row"] + len(matrix) - 1, cfg["col"] + len(matrix[0]) - 1)
                batch_updates.append({"range": f"{start_a1}:{end_a1}", "values": matrix})
                
            ws.batch_update(batch_updates, value_input_option="USER_ENTERED")
            print(f"Synced {'LIVE' if is_today else 'STATIC'}: {title}")

if __name__ == "__main__":
    sync_rolling_sheets()
