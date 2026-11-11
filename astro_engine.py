import os
import json
import datetime
import pytz
import swisseph as swe
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Google Sheets Connection
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["GCP_SA_KEY"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SHEET_ID"])

# 2. Cities Configuration (Top-Left, Top-Right, Bottom-Left, Bottom-Right)
CITIES = {
    "Mumbai":   {"lat": 19.0760, "lon": 72.8777, "tz": "Asia/Kolkata",     "row": 1,  "col": 1},
    "Tokyo":    {"lat": 35.6762, "lon": 139.6503,"tz": "Asia/Tokyo",       "row": 1,  "col": 22},
    "London":   {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London",    "row": 45, "col": 1},
    "New_York": {"lat": 40.7128, "lon": -74.0060,"tz": "America/New_York", "row": 45, "col": 22}
}

# KP Nakshatra & Sub-Lord Lords Sequence (Vimshottari)
DASHA_LORDS = ["Ke", "Ve", "Su", "Mo", "Ma", "Ra", "Ju", "Sa", "Me"]
DASHA_YEARS = [7, 20, 6, 10, 7, 18, 16, 19, 17]
RASHIS = ["Ar", "Ta", "Ge", "Cn", "Le", "Vi", "Li", "Sc", "Sg", "Cp", "Aq", "Pi"]
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

PLANETS = {
    "Su": swe.SUN, "Mo": swe.MOON, "Ma": swe.MARS, "Me": swe.MERCURY,
    "Ju": swe.JUPITER, "Ve": swe.VENUS, "Sa": swe.SATURN,
    "Ra": swe.TRUE_NODE, "Ur": swe.URANUS, "Ne": swe.NEPTUNE, "Pl": swe.PLUTO
}

# Set KP Ayanamsha
swe.set_sid_mode(swe.SIDM_KRISHNAMURTI, 0, 0)

def get_kp_details(deg):
    """Calculates Rashi, Nakshatra, Pada, Nakshatra Lord, and Sub-Lord."""
    deg = deg % 360
    rashi_idx = int(deg // 30)
    rashi = RASHIS[rashi_idx]
    
    nak_span = 360.0 / 27.0  # 13°20'
    nak_idx = int(deg // nak_span)
    nak_name = NAKSHATRAS[nak_idx]
    nak_lord = DASHA_LORDS[nak_idx % 9]
    
    rem_in_nak = deg - (nak_idx * nak_span)
    pada = int(rem_in_nak // (nak_span / 4.0)) + 1
    
    # Sub-Lord Calculation
    start_lord_idx = nak_idx % 9
    curr_pos = 0.0
    sub_lord = nak_lord
    for i in range(9):
        idx = (start_lord_idx + i) % 9
        span = (DASHA_YEARS[idx] / 120.0) * nak_span
        if curr_pos <= rem_in_nak < (curr_pos + span):
            sub_lord = DASHA_LORDS[idx]
            break
        curr_pos += span
        
    return rashi, nak_name, pada, nak_lord, sub_lord

def calculate_city_block(target_date, city_name, cfg, is_live=False):
    """Generates the grid matrix for a specific city and date."""
    tz = pytz.timezone(cfg["tz"])
    if is_live:
        dt_local = datetime.datetime.now(tz)
    else:
        # Default Market Open / Reference Time (09:15 AM Local)
        dt_local = tz.localize(datetime.datetime.combine(target_date, datetime.time(9, 15, 0)))
        
    dt_utc = dt_local.astimezone(pytz.UTC)
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                    dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0)
    
    # Header Block
    grid = [
        [f"Transit ({city_name})", dt_local.strftime("%d-%m-%Y"), dt_local.strftime("%H:%M:%S"), "", "Gifted with True Friendship", "", "", "Hora Timing"],
        ["Planet", "Deg.(Lon.)", "Rashi", "Nakshatra", "Pada", "N Lord", "Sub L", "Speed", "Status"]
    ]
    
    # Ascendant Calculation
    cusps, ascmc = swe.houses_ex(jd, cfg["lat"], cfg["lon"], b'P', swe.FLG_SIDEREAL)
    asc_deg = ascmc[0]
    rashi, nak, pada, nl, sl = get_kp_details(asc_deg)
    grid.append(["As", f"{asc_deg:.4f}", rashi, nak, pada, nl, sl, "0.0000", "Ascendant"])
    
    # Planets Calculation
    for p_name, p_id in PLANETS.items():
        res, _ = swe.calc_ut(jd, p_id, swe.FLG_SIDEREAL | swe.FLG_SPEED)
        lon, speed = res[0], res[3]
        rashi, nak, pada, nl, sl = get_kp_details(lon)
        status = "Retrograde (R)" if speed < 0 and p_name not in ["Ra", "Ke"] else "Direct"
        grid.append([p_name, f"{lon:.4f}", rashi, nak, pada, nl, sl, f"{speed:.4f}", status])
        
    # Ketu (180 degrees opposite Rahu)
    ra_res, _ = swe.calc_ut(jd, swe.TRUE_NODE, swe.FLG_SIDEREAL | swe.FLG_SPEED)
    ke_lon = (ra_res[0] + 180.0) % 360.0
    rashi, nak, pada, nl, sl = get_kp_details(ke_lon)
    grid.append(["Ke", f"{ke_lon:.4f}", rashi, nak, pada, nl, sl, f"{ra_res[3]:.4f}", "Retrograde (R)"])
    
    return grid

def sync_rolling_sheets():
    today_ist = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).date()
    
    # Rolling Window: Past 30 days + Today + Next 18 days = 49 days
    valid_dates = [today_ist + datetime.timedelta(days=i) for i in range(-30, 19)]
    valid_titles = {d.strftime("%Y-%m-%d") for d in valid_dates}
    
    existing_sheets = {ws.title: ws for ws in sheet.worksheets()}
    
    # 1. Delete old sheets (older than 30 days)
    for title, ws in existing_sheets.items():
        if title not in valid_titles and len(existing_sheets) > 1:
            sheet.del_worksheet(ws)
            print(f"Deleted expired sheet: {title}")
            
    # 2. Create missing sheets & Update Live Today sheet
    for d in valid_dates:
        title = d.strftime("%Y-%m-%d")
        is_today = (d == today_ist)
        
        if title not in existing_sheets:
            ws = sheet.add_worksheet(title=title, rows=95, cols=45)
            needs_populate = True
        else:
            ws = existing_sheets[title]
            needs_populate = is_today  # Always recalculate Today for LIVE updates
            
        if needs_populate:
            for city, cfg in CITIES.items():
                block_data = calculate_city_block(d, city, cfg, is_live=is_today)
                start_cell = gspread.utils.rowcol_to_a1(cfg["row"], cfg["col"])
                ws.update(range_name=start_cell, values=block_data)
            print(f"Updated {'LIVE' if is_today else 'STATIC'} sheet: {title}")

if __name__ == "__main__":
    sync_rolling_sheets()
