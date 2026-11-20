# -*- coding: utf-8 -*-
"""
Crisis Fusion — Operations Intelligence  (Streamlit dashboard, single file)

Converted from the 8-page HTML dashboard:
Overview · Dataset Upload · Data Quality · Exploratory Analysis · Visualizations
· AI Insights · Data Explorer · Export Reports

Run in VS Code terminal
-----------------------
    pip install streamlit pandas numpy matplotlib seaborn openpyxl
    streamlit run crisis_fusion_app.py

Optional (fully dark native widgets): create  .streamlit/config.toml  next to this file:
    [theme]
    base = "dark"
    primaryColor = "#a92f50"
    backgroundColor = "#0e0b0c"
    secondaryBackgroundColor = "#181214"
    textColor = "#fffaf8"

Expected columns in an uploaded file (names are matched flexibly):
    Incident ID, Type, Location, Severity, Status, Response Time   (+ optional Timestamp)
"""
from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from html import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st
from matplotlib.colors import LinearSegmentedColormap

st.set_page_config(page_title="Crisis Fusion — Operations Intelligence", page_icon="📊", layout="wide")

# ══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
BG, PANEL, TEXT, SECONDARY, MUTED = "#0e0b0c", "#181214", "#fffaf8", "#eadfdd", "#b6a5a2"
BURGUNDY, GREEN, ORANGE, RED, PURPLE = "#a92f50", "#72d6a5", "#f2ba6b", "#ff8c91", "#d291b0"

PAGES = {  # id: (sidebar label, page title)
    "overview": ("🏠  Overview", "Incident command center"),
    "dataset-upload": ("⬆️  Dataset Upload", "Dataset management & ingestion"),
    "data-quality": ("✅  Data Quality", "Data quality & audit certification"),
    "exploratory-analysis": ("📈  Exploratory Analysis", "Exploratory incident analysis"),
    "visualizations": ("📊  Visualizations", "Visual analytics & chart suite"),
    "ai-insights": ("🧠  AI Insights", "AI intelligence & predictive signals"),
    "data-explorer": ("🗂️  Data Explorer", "Incident data explorer"),
    "export-reports": ("📤  Export Reports", "Export reports & dispatches"),
}
HUB = {  # overview shortcut cards: page -> (badge, description)
    "dataset-upload": ("Ingestion", "Upload CSV/JSON/XLSX files, inspect schemas, parse records, and manage active datasets."),
    "data-quality": ("Audit", "Run automated integrity audits, completeness checks, and column validation scoring."),
    "exploratory-analysis": ("Statistics", "Analyze response times, district variance, shift patterns, and volume metrics."),
    "visualizations": ("Interactive", "Incident classification bars, severity mix donut, and daily trend curves."),
    "ai-insights": ("Signals", "Data-driven findings, risk clustering, and an interactive query assistant."),
    "data-explorer": ("Interactive Table", "Search, filter, sort, and inspect granular incident records with pagination."),
    "export-reports": ("Export Center", "Export filtered incident slices, printable briefings, and JSON dossiers."),
}

REQUIRED = ["Incident ID", "Type", "Location", "Severity", "Status", "Response Time"]
TEXT_COLS = ["Incident ID", "Type", "Location", "Severity", "Status"]
SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]
SEV_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
SEV_COLORS = {"Low": BURGUNDY, "Medium": ORANGE, "High": RED, "Critical": PURPLE, "Unknown": "#6f6361"}
STATUS_COLORS = {"Open": ORANGE, "Resolved": GREEN, "Unknown": "#6f6361"}
TYPE_COLORS = {"Medical": BURGUNDY, "Traffic": PURPLE, "Fire": ORANGE, "Security": GREEN, "Other": RED}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Reference values the dataset has no columns for (kept from the original dashboard)
RESOURCES = {"Ambulance": 92, "Fire response": 78, "Police units": 96, "Specialist": 61}
COVERAGE_THRESHOLD = 70   # % operating threshold
SLA_MINUTES = 30          # municipal response SLA

DISTRICT_MEAN = {  # used only by the built-in sample-data generator
    "North District": 22, "Central Avenue": 11, "Harbor Quarter": 24,
    "Industrial Park": 16, "West End": 31, "East Junction": 9,
}

SEV_MAP = {"crit": "Critical", "critical": "Critical", "severe": "Critical", "high": "High",
           "med": "Medium", "medium": "Medium", "moderate": "Medium", "low": "Low", "minor": "Low"}
STATUS_MAP = {"open": "Open", "opened": "Open", "pending": "Open", "active": "Open", "unresolved": "Open",
              "resolved": "Resolved", "closed": "Resolved", "done": "Resolved", "complete": "Resolved",
              "completed": "Resolved"}
ALIASES = {
    "Incident ID": {"incidentid", "id", "incident", "incidentnumber", "incno", "caseid"},
    "Type": {"type", "incidenttype", "category", "incidentcategory"},
    "Location": {"location", "district", "area", "zone", "sector"},
    "Severity": {"severity", "priority", "level", "severitylevel"},
    "Status": {"status", "state", "resolution", "resolutionstatus"},
    "Response Time": {"responsetime", "responsemin", "responseminutes", "responsetimemin",
                      "responsetimeminutes", "responsetimemins", "response"},
    "Timestamp": {"timestamp", "datetime", "date", "time", "reportedat", "createdat", "reportedtime", "incidentdate"},
}

# ══════════════════════════════════════════════════════════════════════════════
# 2. STYLING (dark burgundy theme, same palette as the HTML dashboard)
# ══════════════════════════════════════════════════════════════════════════════
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;600;700&display=swap');
html, body, .stApp { font-family: 'Fira Sans', system-ui, sans-serif; }
.stApp { background: radial-gradient(circle at 78% -8%, rgba(169,47,80,.22), transparent 34%), #0e0b0c; color:#fffaf8; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background:#120d0f; border-right:1px solid rgba(255,255,255,.09); }
.block-container { padding-top: 1.4rem; max-width: 1400px; }
h1,h2,h3,h4,h5 { color:#fffaf8 !important; letter-spacing:-.01em; }
.stApp p, .stApp li, .stApp label, [data-testid="stWidgetLabel"] *, [data-testid="stCaptionContainer"] * { color:#eadfdd; }
[data-testid="stAlert"] { background: rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.16); }
[data-testid="stAlert"] * { color:#fffaf8 !important; }
.stButton>button, .stDownloadButton>button { background:rgba(255,255,255,.07); color:#fffaf8; border:1px solid rgba(255,255,255,.16); border-radius:8px; }
.stButton>button:hover, .stDownloadButton>button:hover { border-color:#a92f50; color:#fffaf8; background:rgba(169,47,80,.22); }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: rgba(255,255,255,.12) !important; border-radius:16px; background:rgba(255,255,255,.03); }
.glass { background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.16); border-radius:16px; padding:18px 20px; }
.eyebrow { color:#b6a5a2; font-size:11px; letter-spacing:.08em; text-transform:uppercase; }
.topbar-title { margin:2px 0 0; font-size:22px; font-weight:600; color:#fffaf8; }
.dataset-state { display:inline-flex; align-items:center; gap:9px; padding:7px 12px; border:1px solid rgba(255,255,255,.16); border-radius:8px; background:rgba(255,255,255,.07); color:#eadfdd; white-space:nowrap; }
.dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#72d6a5; box-shadow:0 0 0 4px rgba(114,214,165,.1); margin-right:6px; }
.dot.orange { background:#f2ba6b; box-shadow:0 0 0 4px rgba(242,186,107,.12); }
.dot.red { background:#ff8c91; box-shadow:0 0 0 4px rgba(255,140,145,.12); }
.page-intro { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin:6px 0 18px; }
.page-intro h2 { margin:0; font-size:24px; } .page-intro p { margin:2px 0 0; color:#b6a5a2; font-size:13px; }
.timestamp { font-family:'Fira Code',monospace; font-size:11px; color:#b6a5a2; }
.section-heading h3 { margin:22px 0 2px; font-size:17px; } .section-heading p { margin:0 0 10px; color:#b6a5a2; font-size:12px; }
.stat { min-height:118px; }
.stat-label { color:#b6a5a2; font-size:12px; } .stat-value { font-size:28px; font-weight:600; margin:6px 0 2px; color:#fffaf8; }
.stat-meta { color:#b6a5a2; font-size:12px; }
.badge { display:inline-block; padding:2px 9px; border-radius:6px; font-size:11px; font-weight:500; background:rgba(255,255,255,.1); color:#eadfdd; }
.badge.critical { background:rgba(210,145,176,.2); color:#d291b0; } .badge.high { background:rgba(255,140,145,.16); color:#ff8c91; }
.badge.medium, .badge.warning, .badge.open { background:rgba(242,186,107,.16); color:#f2ba6b; }
.badge.low, .badge.info { background:rgba(169,47,80,.28); color:#f2d8d8; } .badge.resolved, .badge.success { background:rgba(114,214,165,.16); color:#72d6a5; }
.hub-card { min-height:128px; transition:.2s; } .hub-card:hover { border-color:rgba(169,47,80,.55); }
.hub-card h3 { margin:6px 0 4px; font-size:16px; } .hub-card p { margin:0; color:#b6a5a2; font-size:12px; line-height:1.5; }
.district-card h4 { margin:0 0 4px; font-size:14px; display:flex; justify-content:space-between; align-items:center; color:#fffaf8; }
.district-metric { font-size:24px; font-weight:600; margin:6px 0 2px; color:#fffaf8; } .district-metric small { font-size:12px; color:#b6a5a2; font-weight:400; }
.score-banner { display:flex; align-items:center; justify-content:space-between; gap:24px; padding:24px 28px; margin-bottom:18px; background:linear-gradient(100deg, rgba(114,214,165,.1), rgba(255,255,255,.03)); border-color:rgba(114,214,165,.3); }
.score-visual { display:flex; align-items:center; gap:20px; }
.score-circle { width:76px; height:76px; border-radius:50%; display:grid; place-items:center; position:relative; flex:0 0 auto; }
.score-circle::after { content:""; position:absolute; inset:8px; border-radius:50%; background:#181214; }
.score-number { position:relative; z-index:1; font-size:19px; font-weight:700; }
.check-item { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 14px; border-radius:8px; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.09); margin-bottom:10px; font-size:13px; color:#fffaf8; }
.insight h3 { margin:0 0 8px; font-size:15px; } .insight ul { margin:0; padding-left:18px; } .insight li { margin-bottom:7px; font-size:13px; color:#eadfdd; }
.insight.risk { border-color:rgba(255,140,145,.3); } .insight.recommend { border-color:rgba(114,214,165,.3); }
.ai-response { margin-top:12px; padding:16px 18px; border-radius:10px; background:rgba(0,0,0,.35); border:1px solid rgba(210,145,176,.35); font-size:13px; line-height:1.6; color:#fffaf8; }
.export-card h3 { margin:6px 0 4px; font-size:16px; } .export-card p { margin:0 0 8px; color:#eadfdd; font-size:12px; }
.export-meta { display:flex; gap:14px; font-size:11px; color:#b6a5a2; flex-wrap:wrap; }
.brand { display:flex; align-items:center; gap:11px; padding:4px 4px 14px; } .brand strong { font-size:16px; color:#fffaf8; } .brand span { display:block; color:#b6a5a2; font-size:11px; }
.brand-mark { width:32px; height:32px; display:grid; place-items:center; border:1px solid rgba(169,47,80,.5); border-radius:10px; background:linear-gradient(145deg, rgba(169,47,80,.7), rgba(125,24,56,.42)); }
</style>
"""


def setup_plot_style() -> None:
    sns.set_theme(style="darkgrid", rc={
        "figure.facecolor": PANEL, "axes.facecolor": PANEL, "savefig.facecolor": PANEL,
        "axes.edgecolor": "#3a2f32", "axes.labelcolor": MUTED, "text.color": TEXT,
        "xtick.color": MUTED, "ytick.color": MUTED, "grid.color": "#2c2326",
        "axes.titlecolor": TEXT, "axes.titleweight": "semibold", "axes.titlesize": 12,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "legend.facecolor": PANEL, "legend.edgecolor": "#3a2f32", "legend.labelcolor": SECONDARY,
    })


# ── small HTML helpers ──────────────────────────────────────────────────────────
def md_html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def badge(text: str, kind: str = "info") -> str:
    return f'<span class="badge {kind}">{text}</span>'


def stat_card(label: str, value: str, meta: str = "", accent: str | None = None) -> str:
    style = f' style="color:{accent}"' if accent else ""
    return (f'<div class="stat glass"><div class="stat-label">{label}</div>'
            f'<div class="stat-value"{style}>{value}</div><div class="stat-meta">{meta}</div></div>')


def page_intro(title: str, sub: str, right: str = "") -> None:
    md_html(f'<div class="page-intro"><div><h2>{title}</h2><p>{sub}</p></div><div>{right}</div></div>')


def section(title: str, sub: str = "") -> None:
    md_html(f'<div class="section-heading"><h3>{title}</h3><p>{sub}</p></div>')


def goto(page: str) -> None:
    st.session_state["page"] = page


def render_fig(fig) -> None:
    st.pyplot(fig)
    plt.close(fig)


def fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# 3. DATA: SAMPLE GENERATOR, INGESTION, CLEANING
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def make_sample_data(n: int = 12480, seed: int = 42, dirty: bool = True) -> pd.DataFrame:
    """Synthetic incident log whose shape follows the original dashboard (6 districts,
    5 incident types, 42/23/17/18 % severity mix, Friday +18 %, 18:00-21:00 evening peak).
    With dirty=True a little realistic noise is injected so the cleaning step has work to do."""
    rng = np.random.default_rng(seed)
    districts = np.array(list(DISTRICT_MEAN))
    vol = np.array([3914, 2764, 2184, 1604, 1014, 1000], dtype=float)
    loc = rng.choice(districts, n, p=vol / vol.sum())
    tw = np.array([3914, 2764, 2184, 1604, 1014], dtype=float)
    typ = rng.choice(["Medical", "Traffic", "Fire", "Security", "Other"], n, p=tw / tw.sum())
    sev = rng.choice(SEVERITY_ORDER, n, p=[0.42, 0.23, 0.17, 0.18])

    end = pd.Timestamp("2024-09-23")
    days = pd.date_range(end - pd.Timedelta(days=89), end, freq="D")
    day_w = np.linspace(0.85, 1.2, len(days)) * np.where(days.dayofweek == 4, 1.18, 1.0)
    day_idx = rng.choice(len(days), n, p=day_w / day_w.sum())
    hour_w = np.ones(24)
    hour_w[18:21] = 2.2
    hour_w[0:6] = 0.5
    hour = rng.choice(24, n, p=hour_w / hour_w.sum())
    ts = days[day_idx] + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(rng.integers(0, 3600, n), unit="s")

    df = pd.DataFrame({"ts": ts, "Type": typ, "Location": loc, "Severity": sev})
    df = df.sort_values("ts").reset_index(drop=True)
    seq = df.groupby(df["ts"].dt.date).cumcount() + 1
    df.insert(0, "Incident ID", [f"INC-{t:%y%m%d}-{s:04d}" for t, s in zip(df["ts"], seq)])

    mean = df["Location"].map(DISTRICT_MEAN).to_numpy(dtype=float)
    mean = mean * np.where(df["ts"].dt.hour.between(18, 20), 1.15, 1.0) * np.where(df["Severity"] == "Critical", 0.92, 1.0)
    resp = np.clip(np.round(rng.gamma(shape=8, scale=mean / 8)), 2, 180)
    age_days = (end + pd.Timedelta(days=1) - df["ts"]).dt.total_seconds().to_numpy() / 86400
    p_open = 0.03 + 0.45 * np.exp(-age_days / 1.5)

    out = pd.DataFrame({
        "Incident ID": df["Incident ID"], "Type": df["Type"], "Location": df["Location"], "Severity": df["Severity"],
        "Status": np.where(rng.random(n) < p_open, "Open", "Resolved"),
        "Response Time": [f"{int(x)} min" for x in resp],
        "Timestamp": df["ts"].dt.strftime("%Y-%m-%d %H:%M:%S"),
    })
    if dirty:
        def pick(frac):
            return rng.random(n) < frac
        m = pick(.012); out.loc[m, "Type"] = out.loc[m, "Type"].str.lower()
        m = pick(.012); out.loc[m, "Location"] = "  " + out.loc[m, "Location"] + " "
        m = pick(.008); out.loc[m, "Severity"] = out.loc[m, "Severity"].replace(
            {"Critical": "CRITICAL", "Medium": "med", "High": "high", "Low": "LOW"})
        m = pick(.010); out.loc[m, "Status"] = out.loc[m, "Status"].replace({"Resolved": "closed", "Open": "OPEN"})
        m = pick(.004); out.loc[m, "Response Time"] = np.nan
        m = pick(.002); out.loc[m, "Response Time"] = "N/A"
        m = pick(.002); out.loc[m, "Location"] = np.nan
        m = pick(.001); out.loc[m, "Timestamp"] = "unknown"
        out = pd.concat([out, out.sample(frac=0.003, random_state=7)], ignore_index=True)  # duplicate rows
    return out


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map flexible header names (e.g. 'incident_id', 'District', 'Priority') to the canonical schema."""
    mapping: dict[str, str] = {}
    for col in df.columns:
        key = re.sub(r"[^a-z0-9]", "", str(col).lower())
        for canon, names in ALIASES.items():
            if key in names and canon not in mapping.values():
                mapping[col] = canon
                break
    return df.rename(columns=mapping)


@st.cache_data(show_spinner="Parsing file…")
def parse_upload(name: str, data: bytes, delimiter: str, encoding: str, header: bool) -> pd.DataFrame:
    lower = name.lower()
    bio = io.BytesIO(data)
    if lower.endswith((".csv", ".tsv", ".txt")):
        sep = {"comma": ",", "semicolon": ";", "tab": "\t"}.get(delimiter)  # None → auto-detect
        df = pd.read_csv(bio, sep=sep, engine="python" if sep is None else "c", encoding=encoding,
                         header=0 if header else None, skipinitialspace=True)
        if not header:
            names = REQUIRED + ["Timestamp"]
            df.columns = [names[i] if i < len(names) else f"extra_{i}" for i in range(df.shape[1])]
        return df
    if lower.endswith(".json"):
        try:
            return pd.read_json(bio)
        except ValueError:
            bio.seek(0)
            return pd.read_json(bio, lines=True)
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(bio)
    raise ValueError("Unsupported file type. Use .csv, .json or .xlsx")


def parse_minutes(series: pd.Series) -> pd.Series:
    """'18 min' → 18, '1h 5m' → 65, '22' → 22, 'N/A' → NaN."""
    s = series.map(lambda v: "" if pd.isna(v) else str(v)).str.lower()
    hours = pd.to_numeric(s.str.extract(r"(\d+(?:\.\d+)?)\s*h")[0], errors="coerce")
    mins = pd.to_numeric(s.str.extract(r"(\d+(?:\.\d+)?)\s*m")[0], errors="coerce")
    plain = pd.to_numeric(s.str.extract(r"(\d+(?:\.\d+)?)")[0], errors="coerce")
    total = hours.fillna(0) * 60 + mins.fillna(0)
    return total.where(hours.notna() | mins.notna(), plain)


def _to_datetime(s: pd.Series) -> pd.Series:
    try:
        ts = pd.to_datetime(s, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        ts = pd.to_datetime(s, errors="coerce")
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    return ts


@st.cache_data(show_spinner="Cleaning data…")
def clean_data(raw: pd.DataFrame, strip_ws: bool = True):
    """Raw frame → (clean frame, cleaning log). Steps:
    1 header mapping · 2 whitespace/blank handling · 3 drop missing/duplicate IDs · 4 standardise categories
    5 parse response time to numeric minutes + impute invalid values (district median)
    6 parse timestamps and derive Date / Hour / Weekday."""
    df = normalize_columns(raw.copy())
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    has_ts = "Timestamp" in df.columns
    df = df[REQUIRED + (["Timestamp"] if has_ts else [])].copy()
    log: dict = {"rows_raw": len(df)}

    # 2 · whitespace + blanks
    ws_fixed = 0
    for c in TEXT_COLS:
        s = df[c].map(lambda v: np.nan if pd.isna(v) else str(v)).astype(object)
        if strip_ws:
            t = s.str.strip().str.replace(r"\s+", " ", regex=True)
            ws_fixed += int((s.fillna("") != t.fillna("")).sum())
            s = t
        df[c] = s.where(s.fillna("x") != "", np.nan)
    resp_blank = df["Response Time"].map(lambda v: pd.isna(v) or str(v).strip() == "")
    df.loc[resp_blank, "Response Time"] = np.nan

    miss_by_col = {c: int(df[c].isna().sum()) for c in REQUIRED}
    log["missing_by_col"] = miss_by_col
    log["missing_cells"] = int(sum(miss_by_col.values()))
    log["cells_total"] = len(df) * len(REQUIRED)
    log["whitespace_fixed"] = ws_fixed

    # 3 · IDs
    no_id = df["Incident ID"].isna()
    log["missing_id"] = int(no_id.sum())
    df = df[~no_id]
    dup = df["Incident ID"].duplicated(keep="first")
    log["duplicates"] = int(dup.sum())
    df = df[~dup].copy()

    # 4 · categories
    cat_fixed = 0
    for c in ["Type", "Location"]:
        t = df[c].str.title()
        cat_fixed += int((df[c].fillna("") != t.fillna("")).sum())
        df[c] = t.fillna("Unknown")
    for c, mp in (("Severity", SEV_MAP), ("Status", STATUS_MAP)):
        mapped = df[c].str.lower().map(mp)
        log[f"invalid_{c.lower()}"] = int((df[c].notna() & mapped.isna()).sum())
        cat_fixed += int((df[c].notna() & mapped.notna() & (df[c] != mapped)).sum())
        df[c] = mapped.fillna("Unknown")
    log["category_fixed"] = cat_fixed

    # 5 · response time → minutes
    resp = parse_minutes(df["Response Time"])
    bad = resp.isna() | (resp <= 0) | (resp > 1440)
    resp = resp.mask(bad)
    med_loc = resp.groupby(df["Location"]).transform("median")
    df["Response Min"] = resp.fillna(med_loc).fillna(resp.median()).astype(float)
    df["Response Imputed"] = bad.to_numpy()
    log["imputed"] = int(bad.sum())
    df = df.drop(columns=["Response Time"])

    # 6 · timestamps
    if has_ts:
        ts = _to_datetime(df["Timestamp"])
        log["bad_timestamps"] = int(ts.isna().sum())
        log["future_timestamps"] = int((ts > pd.Timestamp.now()).sum())
        df["Timestamp"] = ts
        df["Date"] = ts.dt.normalize()
        df["Hour"] = ts.dt.hour
        df["Weekday"] = ts.dt.day_name()
        df = df.sort_values("Timestamp", ascending=False, kind="stable")
    else:
        df = df.sort_values("Incident ID", ascending=False, kind="stable")
    df = df.reset_index(drop=True)
    log["rows_clean"] = len(df)
    return df, log


def has_time(df: pd.DataFrame) -> bool:
    return "Timestamp" in df.columns and df["Timestamp"].notna().any()


def grade_for(score: float) -> tuple[str, str]:
    if score >= 95:
        return "A", GREEN
    if score >= 85:
        return "B", GREEN
    if score >= 70:
        return "C", ORANGE
    return "D", RED


def quality_metrics(df: pd.DataFrame, log: dict, outlier_min: int) -> dict:
    n = max(len(df), 1)
    completeness = 100 * (1 - log["missing_cells"] / max(log["cells_total"], 1))
    uniqueness = 100 * (1 - log["duplicates"] / max(log["rows_raw"] - log["missing_id"], 1))
    valid = ((df["Severity"] != "Unknown") & (df["Status"] != "Unknown")
             & (~df["Response Imputed"]) & (df["Response Min"] <= outlier_min))
    validity = 100 * float(valid.mean()) if len(df) else 0.0
    timeliness = None
    if "bad_timestamps" in log:
        timeliness = 100 * (1 - (log["bad_timestamps"] + log["future_timestamps"]) / n)
    dims = [completeness, uniqueness, validity] + ([timeliness] if timeliness is not None else [])
    overall = float(np.mean(dims))
    return {"completeness": completeness, "uniqueness": uniqueness, "validity": validity,
            "timeliness": timeliness, "overall": overall, "grade": grade_for(overall)[0],
            "outliers": int((df["Response Min"] > outlier_min).sum()), "outlier_min": outlier_min}


# ══════════════════════════════════════════════════════════════════════════════
# 4. ANALYTICS HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def peak_window(d: pd.DataFrame, width: int = 3):
    h = d["Hour"].dropna().astype(int).to_numpy() if "Hour" in d.columns else np.array([], dtype=int)
    if h.size == 0:
        return None
    hc = np.bincount(h, minlength=24)
    win = np.array([hc[(s + np.arange(width)) % 24].sum() for s in range(24)])
    s = int(win.argmax())
    base = hc.sum() / (24 / width)
    return f"{s:02d}:00 – {(s + width) % 24:02d}:00", (win[s] / base - 1) * 100 if base else 0.0, s


def period_counts(d: pd.DataFrame, days: int = 30):
    if not has_time(d):
        return None
    end = d["Timestamp"].max()
    cur = int((d["Timestamp"] > end - pd.Timedelta(days=days)).sum())
    prev = int(((d["Timestamp"] <= end - pd.Timedelta(days=days)) & (d["Timestamp"] > end - pd.Timedelta(days=2 * days))).sum())
    return cur, prev


def delta_meta(cur: int, prev: int, bad_up: bool = False, label: str = "vs previous 30 days") -> str:
    if prev == 0:
        return label
    p = (cur - prev) / prev * 100
    good = p <= 0 if bad_up else p >= 0
    return f'<strong style="color:{GREEN if good else RED}">{p:+.1f}%</strong> {label}'


def filter_range(d: pd.DataFrame, days: int | None) -> pd.DataFrame:
    if days is None or not has_time(d):
        return d
    return d[d["Timestamp"] >= d["Timestamp"].max() - pd.Timedelta(days=days)]


def district_stats(d: pd.DataFrame) -> pd.DataFrame:
    g = d[d["Location"] != "Unknown"].groupby("Location").agg(
        incidents=("Incident ID", "count"), avg_resp=("Response Min", "mean"),
        p90=("Response Min", lambda s: float(np.percentile(s, 90)))).sort_values("incidents", ascending=False)
    g["share"] = g["incidents"] / max(len(d), 1) * 100
    return g


def build_findings(df: pd.DataFrame) -> dict:
    out = {"key": [], "risk": [], "actions": [], "meta": {}}
    n = max(len(df), 1)
    tc = df["Type"].value_counts()
    out["key"].append(f"{tc.index[0]} incidents are the largest category at {tc.iloc[0] / n * 100:.1f}% of total volume.")
    peak_day, pw = None, None
    if has_time(df):
        daily = df.dropna(subset=["Date"]).groupby("Date").size()
        by_dow = daily.groupby(daily.index.day_name()).mean()
        peak_day = by_dow.idxmax()
        out["key"].append(f"{peak_day} response demand is {(by_dow.max() / by_dow.mean() - 1) * 100:.0f}% above the weekly average.")
        pw = peak_window(df)
        if pw:
            out["key"].append(f"Peak incident window is {pw[0]}, {pw[1]:+.0f}% versus a uniform daily baseline.")
    med, p90 = df["Response Min"].median(), float(np.percentile(df["Response Min"], 90))
    out["key"].append(f"Median response time is {med:.0f} min (P90: {p90:.0f} min).")
    by_loc = df[df["Location"] != "Unknown"].groupby("Location")["Response Min"].mean().sort_values()
    fast = slow = None
    if len(by_loc):
        fast, slow = by_loc.index[0], by_loc.index[-1]
        out["key"].append(f"{fast} has the fastest average response at {by_loc.iloc[0]:.0f} min.")

    crit = df[df["Severity"] == "Critical"]
    top_loc = None
    if len(crit):
        lc = crit["Location"].value_counts()
        top_loc = lc.index[0]
        msg = f"{top_loc} accounts for {lc.iloc[0] / len(crit) * 100:.0f}% of the {len(crit):,} critical incidents"
        if has_time(df):
            sub = crit[crit["Location"] == top_loc]
            msg += f", {(sub['Hour'] >= 18).mean() * 100:.0f}% of them reported after 18:00"
        out["risk"].append(msg + ".")
    low_cov = [f"{k} ({v}%)" for k, v in RESOURCES.items() if v < COVERAGE_THRESHOLD]
    if low_cov:
        out["risk"].append(f"Coverage below the {COVERAGE_THRESHOLD}% operating threshold: {', '.join(low_cov)}.")
    opened = df[df["Status"] == "Open"]
    overdue = 0
    if has_time(df):
        overdue = int((opened["Timestamp"] < df["Timestamp"].max() - pd.Timedelta(hours=24)).sum())
        out["risk"].append(f"{overdue:,} open cases have exceeded the 24-hour response target ({len(opened):,} open in total).")
    else:
        out["risk"].append(f"{len(opened):,} cases are still open.")
    if slow is not None:
        if by_loc.iloc[-1] > SLA_MINUTES:
            out["risk"].append(f"{slow} average latency ({by_loc.iloc[-1]:.0f} min) exceeds the {SLA_MINUTES}-minute SLA target.")
        else:
            out["risk"].append(f"All districts are within the {SLA_MINUTES}-minute SLA (slowest: {slow}, {by_loc.iloc[-1]:.0f} min).")

    when = f"{peak_day} evenings" + (f" ({pw[0]})" if pw else "") if peak_day else "the busiest shift"
    out["actions"].append(f"Stage one additional specialist team for {when}.")
    if top_loc:
        out["actions"].append(f"Review {top_loc} handoff procedures with dispatch supervisors.")
    out["actions"].append(f"Prioritize the {overdue:,} overdue cases in the upcoming shift briefing." if overdue
                          else "Keep monitoring open cases in the upcoming shift briefing.")
    if fast and slow and fast != slow:
        out["actions"].append(f"Reallocate idle secondary units from {fast} to {slow}.")
    out["meta"] = {"median_response_min": float(med), "p90_response_min": p90, "open_cases": int(len(opened)),
                   "critical_incidents": int(len(crit)), "overdue_open_cases": overdue}
    return out


def answer_query(q: str, df: pd.DataFrame) -> str:
    """Rule-based assistant: every answer is computed from the active cleaned dataset."""
    ql = q.lower()
    locs = [x for x in sorted(df["Location"].unique()) if x != "Unknown"]
    for loc in locs:
        if re.search(rf"\b{re.escape(loc.split()[0].lower())}\b", ql):
            d = df[df["Location"] == loc]
            city = df["Response Min"].mean()
            diff = (d["Response Min"].mean() / city - 1) * 100
            text = (f"{loc} handled {len(d):,} incidents ({len(d) / len(df) * 100:.1f}% of volume) with a mean response of "
                    f"{d['Response Min'].mean():.1f} min — {abs(diff):.0f}% {'slower' if diff > 0 else 'faster'} than the "
                    f"city-wide mean of {city:.1f} min (P90: {np.percentile(d['Response Min'], 90):.0f} min).")
            if has_time(d):
                pw = peak_window(d)
                ev = d[d["Hour"].between(18, 20)]
                rest = d[~d["Hour"].between(18, 20)]
                text += f" Demand peaks {pw[0]} ({pw[1]:+.0f}% vs its uniform baseline)."
                if len(ev) > 10 and len(rest) > 10:
                    text += (f" Evening (18:00–21:00) responses average {ev['Response Min'].mean():.1f} min versus "
                             f"{rest['Response Min'].mean():.1f} min for the rest of the day.")
            return text
    day = next((w for w in WEEKDAYS if w.lower() in ql), None)
    if day or any(k in ql for k in ("predict", "forecast", "expect", "tomorrow", "next week")):
        day = day or "Friday"
        if not has_time(df):
            return "Forecasting needs a Timestamp column in the dataset."
        daily = df.dropna(subset=["Date"]).groupby("Date").size()
        sel = daily[daily.index.day_name() == day]
        if len(sel) < 2:
            return f"Not enough {day} history in the dataset to forecast."
        sub = df[df["Weekday"] == day]
        mix = ", ".join(f"{k} ({v * 100:.0f}%)" for k, v in sub["Type"].value_counts(normalize=True).head(2).items())
        pw = peak_window(sub)
        return (f"Based on {len(sel)} historical {day}s, expect ≈{sel.mean():,.0f} ± {np.std(sel, ddof=1):,.0f} incidents "
                f"(last four {day}s average {sel.tail(4).mean():,.0f}). Mix is led by {mix}. "
                f"Demand peaks {pw[0]}, so pre-stage units ahead of that window.")
    if any(k in ql for k in ("specialist", "coverage", "readiness", "ambulance", "unit", "resource")):
        low = [(k, v) for k, v in RESOURCES.items() if v < COVERAGE_THRESHOLD]
        base = "Reference coverage: " + ", ".join(f"{k} {v}%" for k, v in RESOURCES.items()) + ". "
        if low:
            return base + (f"{', '.join(k for k, _ in low)} sits below the {COVERAGE_THRESHOLD}% threshold — "
                           "consider secondary hazard certifications to close the gap.")
        return base + f"All unit types meet the {COVERAGE_THRESHOLD}% threshold."
    if any(k in ql for k in ("slow", "delay", "latency", "response", "bottleneck")):
        st_ = district_stats(df)
        worst = st_["avg_resp"].idxmax()
        return (f"{worst} is the slowest district at {st_.loc[worst, 'avg_resp']:.1f} min average "
                f"(P90 {st_.loc[worst, 'p90']:.0f} min) against an SLA of {SLA_MINUTES} min.")
    crit_share = (df["Severity"] == "Critical").mean() * 100
    return (f"Dataset summary: {len(df):,} incidents, mean response {df['Response Min'].mean():.1f} min, "
            f"{crit_share:.1f}% critical. Try asking about a district, a weekday forecast, or unit coverage.")


# ══════════════════════════════════════════════════════════════════════════════
# 5. CHARTS (seaborn + matplotlib)
# ══════════════════════════════════════════════════════════════════════════════
def fig_type_bars(d: pd.DataFrame):
    counts = d["Type"].value_counts()
    pal = {t: TYPE_COLORS.get(t, "#8a7a77") for t in counts.index}
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    sns.barplot(x=counts.index, y=counts.values, hue=counts.index, palette=pal, dodge=False, legend=False, ax=ax)
    for i, v in enumerate(counts.values):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom", color=TEXT, fontsize=9)
    ax.set(xlabel="", ylabel="Incidents", title="Incidents by type")
    return fig


def fig_severity_donut(d: pd.DataFrame):
    counts = d["Severity"].value_counts()
    order = [s for s in SEVERITY_ORDER + ["Unknown"] if s in counts.index]
    vals = counts.reindex(order)
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.pie(vals, colors=[SEV_COLORS[s] for s in order], startangle=90, counterclock=False,
           wedgeprops=dict(width=0.38, edgecolor=PANEL, linewidth=2))
    ax.text(0, 0.05, f"{len(d) / 1000:.1f}k", ha="center", fontsize=18, fontweight="bold", color=TEXT)
    ax.text(0, -0.2, "incidents", ha="center", fontsize=9, color=MUTED)
    ax.legend([f"{s} — {v / vals.sum() * 100:.0f}%" for s, v in vals.items()], loc="center left",
              bbox_to_anchor=(1.0, 0.5), frameon=False)
    ax.set_title("Severity mix")
    ax.grid(False)
    return fig


def fig_trend(d: pd.DataFrame):
    if not has_time(d):
        return None
    daily = d.dropna(subset=["Timestamp"]).set_index("Timestamp").resample("D")["Incident ID"].count()
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    sns.lineplot(x=daily.index, y=daily.values, color=BURGUNDY, alpha=.55, linewidth=1.2, label="Daily volume", ax=ax)
    ax.fill_between(daily.index, daily.values, color=BURGUNDY, alpha=.12)
    sns.lineplot(x=daily.index, y=daily.rolling(7, min_periods=1).mean().values, color=GREEN, linewidth=2.4,
                 label="7-day average", ax=ax)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.set(xlabel="", ylabel="Incidents / day", title="Incident volume trend")
    ax.legend(frameon=False)
    return fig


def fig_resources():
    names, vals = list(RESOURCES), list(RESOURCES.values())
    pal = {n: (GREEN if v >= 90 else ORANGE if v >= COVERAGE_THRESHOLD else PURPLE) for n, v in RESOURCES.items()}
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.barh(names, [100] * len(names), color="#2c2326", height=0.55)
    sns.barplot(x=vals, y=names, hue=names, palette=pal, dodge=False, legend=False, orient="h", width=0.55, ax=ax)
    for i, v in enumerate(vals):
        ax.text(v + 1, i, f"{v}%", va="center", color=TEXT, fontsize=9)
    ax.axvline(COVERAGE_THRESHOLD, color=RED, linestyle="--", linewidth=1)
    ax.set(xlim=(0, 108), xlabel="Dispatched / requested (%)", ylabel="", title="Requested vs dispatched resources")
    return fig


def fig_response_hist(d: pd.DataFrame):
    r = d["Response Min"]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    sns.histplot(r, bins=40, kde=True, color=BURGUNDY, edgecolor=PANEL, ax=ax)
    for val, col, lab, ls in ((r.mean(), ORANGE, f"Mean {r.mean():.1f}", "-"), (r.median(), GREEN, f"Median {r.median():.1f}", "-"),
                              (np.percentile(r, 95), RED, f"P95 {np.percentile(r, 95):.0f}", "--")):
        ax.axvline(val, color=col, linestyle=ls, linewidth=1.6, label=lab)
    ax.set(xlabel="Response time (min)", ylabel="Incidents", title="Response-time distribution")
    ax.legend(frameon=False)
    return fig


def fig_box_by_district(d: pd.DataFrame):
    d = d[d["Location"] != "Unknown"]
    order = d.groupby("Location")["Response Min"].median().sort_values().index.tolist()
    cols = [BURGUNDY, PURPLE, ORANGE, GREEN, RED, "#f2d8d8"] * 3
    pal = {loc: cols[i] for i, loc in enumerate(order)}
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    sns.boxplot(data=d, y="Location", x="Response Min", hue="Location", order=order, palette=pal, legend=False,
                fliersize=2, linewidth=1, flierprops=dict(markerfacecolor=MUTED, markeredgecolor=MUTED), ax=ax)
    ax.set(xlabel="Response time (min)", ylabel="", title="Response time by district")
    return fig


def fig_heatmap(d: pd.DataFrame):
    if not has_time(d):
        return None
    ct = pd.crosstab(d["Weekday"], d["Hour"].astype("Int64")).reindex(index=WEEKDAYS, columns=range(24), fill_value=0)
    cmap = LinearSegmentedColormap.from_list("cf", [PANEL, "#7d1838", BURGUNDY, ORANGE])
    fig, ax = plt.subplots(figsize=(12, 3.8))
    sns.heatmap(ct, cmap=cmap, linewidths=.4, linecolor=PANEL, cbar_kws={"label": "Incidents"}, ax=ax)
    ax.set(xlabel="Hour of day", ylabel="", title="Incident demand: weekday × hour")
    ax.grid(False)
    return fig


def fig_missing(miss: dict, rows: int):
    s = pd.Series(miss).sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    sns.barplot(x=s.values, y=s.index, hue=s.index, palette=[ORANGE] * len(s), legend=False, orient="h", ax=ax)
    ax.set(xlabel=f"Missing values (of {rows:,} rows)", ylabel="", title="Missing values per column (raw data)")
    return fig


def build_figures(d: pd.DataFrame) -> dict:
    figs = {"Incidents by type": fig_type_bars(d), "Severity mix": fig_severity_donut(d)}
    trend = fig_trend(d)
    if trend is not None:
        figs["Incident volume trend"] = trend
    figs["Requested vs dispatched resources"] = fig_resources()
    return figs


# ══════════════════════════════════════════════════════════════════════════════
# 6. EXPORT BUILDERS
# ══════════════════════════════════════════════════════════════════════════════
def export_cols(d: pd.DataFrame) -> list[str]:
    return [c for c in ["Incident ID", "Timestamp", "Type", "Location", "Severity", "Status", "Response Min"] if c in d.columns]


def build_dossier(slice_df, df, q, name, findings) -> str:
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "schema": "CrisisFusion v2.4", "dataset": name,
        "recordsCount": int(len(df)), "qualityScore": f"{q['overall']:.1f}%",
        "quality": {k: (None if v is None else round(float(v), 2)) for k, v in q.items() if k in
                    ("completeness", "uniqueness", "validity", "timeliness")},
        "metrics": findings["meta"], "keyFindings": findings["key"], "riskSignals": findings["risk"],
        "recommendations": findings["actions"],
        "records": json.loads(slice_df[export_cols(slice_df)].to_json(orient="records", date_format="iso")),
    }
    return json.dumps(payload, indent=2)


def build_certificate(df, q, name) -> str:
    return "\n".join([
        "CRISIS FUSION — DATA QUALITY AUDIT CERTIFICATE",
        f"Generated: {datetime.now(timezone.utc):%a, %d %b %Y %H:%M:%S} UTC",
        f"Dataset: {name}",
        f"Quality Score: {q['overall']:.1f}% (Grade {q['grade']})",
        f"Total Records: {len(df):,}",
        f"Completeness: {q['completeness']:.1f}%",
        f"Uniqueness: {q['uniqueness']:.1f}%",
        f"Validity: {q['validity']:.1f}% (response-time threshold {q['outlier_min']} min)",
        "Timeliness: " + ("n/a (no Timestamp column)" if q["timeliness"] is None else f"{q['timeliness']:.1f}%"),
        "Status: " + ("CERTIFIED FOR OPERATIONAL DISPATCH" if q["overall"] >= 95 else "REVIEW RECOMMENDED"),
    ])


def build_briefing_html(df, q, findings, pngs: dict, name: str) -> str:
    li = lambda items: "".join(f"<li>{escape(i)}</li>" for i in items)
    imgs = "".join(f'<h3>{escape(k)}</h3><img alt="{escape(k)}" src="data:image/png;base64,{base64.b64encode(v).decode()}">'
                   for k, v in pngs.items())
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Crisis Fusion — Incident Briefing</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#0e0b0c;color:#fffaf8;max-width:900px;margin:30px auto;padding:0 20px;
-webkit-print-color-adjust:exact;print-color-adjust:exact}}h1{{margin-bottom:4px}}h3{{margin-top:26px;color:#f2d8d8}}
img{{max-width:100%;border-radius:10px}}li{{margin:6px 0}}.m{{display:flex;gap:14px;flex-wrap:wrap}}
.c{{border:1px solid #3a2f32;border-radius:10px;padding:10px 16px;background:#181214}}.c b{{display:block;font-size:22px}}</style></head><body>
<h1>Incident Briefing</h1><div>{escape(name)} · generated {datetime.now():%Y-%m-%d %H:%M} · print with Ctrl+P → Save as PDF</div>
<div class="m" style="margin-top:18px"><div class="c">Records<b>{len(df):,}</b></div><div class="c">Quality<b>{q['overall']:.1f}%</b></div>
<div class="c">Median response<b>{df['Response Min'].median():.0f} min</b></div><div class="c">Open cases<b>{int((df['Status'] == 'Open').sum()):,}</b></div></div>
<h3>Key operational findings</h3><ul>{li(findings['key'])}</ul><h3>Risk analysis</h3><ul>{li(findings['risk'])}</ul>
<h3>Recommended actions</h3><ul>{li(findings['actions'])}</ul>{imgs}</body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
# 7. PAGES
# ══════════════════════════════════════════════════════════════════════════════
def page_overview(df, q):
    ss = st.session_state
    right = f'<span class="timestamp">SYS: LIVE · DATA THROUGH {df["Timestamp"].max():%d %b %Y}</span>' if has_time(df) else ""
    page_intro("Operations Overview", "Executive intelligence summary, real-time posture, and operational module shortcuts", right)
    crit, opened = df[df["Severity"] == "Critical"], df[df["Status"] == "Open"]
    pt, pc = period_counts(df), period_counts(crit)
    cards = [
        stat_card("Total records", f"{len(df):,}", delta_meta(*pt) if pt else "rows in active dataset"),
        stat_card("Critical incidents", f"{len(crit):,}", delta_meta(*pc, bad_up=True) if pc else "requires review", RED),
        stat_card("Unresolved incidents", f"{len(opened):,}",
                  f'<strong style="color:{ORANGE}">{len(opened) / max(len(df), 1) * 100:.1f}%</strong> of all incidents', ORANGE),
        stat_card("Mean response time", f"{df['Response Min'].mean():.1f} min",
                  f'<strong style="color:{GREEN}">P90 {np.percentile(df["Response Min"], 90):.0f} min</strong> · median {df["Response Min"].median():.0f}', GREEN),
    ]
    for col, c in zip(st.columns(4), cards):
        col.markdown(c, unsafe_allow_html=True)

    section("Operations Modules", "Direct navigation to dedicated module pages")
    ids = list(HUB)
    for r in range(0, len(ids), 3):
        for col, pid in zip(st.columns(3), ids[r:r + 3]):
            b, desc = HUB[pid]
            if pid == "data-quality":
                b = f"Audit: {q['overall']:.1f}%"
            label = PAGES[pid][0].split("  ")[-1]
            with col:
                md_html(f'<div class="hub-card glass">{badge(b)}<h3>{label}</h3><p>{desc}</p></div>')
                st.button(f"Open {label} →", key=f"hub_{pid}", on_click=goto, args=(pid,))


def page_upload(df, log):
    ss = st.session_state
    page_intro("Dataset Upload & Ingestion", "Upload operational telemetry, configure parsing rules, and review schema detections")
    active, dropc, details = st.container(), st.container(), st.container()

    with details:
        left, right = st.columns([1.4, 1])
        with right:
            st.markdown("##### Ingestion Configuration")
            delim_label = st.selectbox("Delimiter", ["Auto-detect", "Comma (,)", "Semicolon (;)", "Tab (\\t)"])
            enc_label = st.selectbox("Character encoding", ["UTF-8 (Standard)", "ISO-8859-1 (Latin1)", "ASCII"])
            header = st.checkbox("First line contains column headers", value=True)
            strip = st.checkbox("Automatically strip whitespace", value=True)
        delim = {"Comma (,)": "comma", "Semicolon (;)": "semicolon", "Tab (\\t)": "tab"}.get(delim_label, "auto")
        enc = {"UTF-8 (Standard)": "utf-8", "ISO-8859-1 (Latin1)": "latin-1", "ASCII": "ascii"}[enc_label]

    with dropc:
        st.button("↺ Load Sample Data", on_click=reset_sample)
        up = st.file_uploader("Drag & drop your dataset file here (CSV · JSON · XLSX)", type=["csv", "json", "xlsx"],
                              key=f"uploader_{ss.uploader_key}")
        if up is not None:
            sig = (up.name, up.size, delim, enc, header, strip)
            if ss.get("upload_sig") != sig:
                try:
                    parsed = parse_upload(up.name, up.getvalue(), delim, enc, header)
                    absent = [c for c in REQUIRED if c not in normalize_columns(parsed).columns]
                    if absent:
                        st.error("Missing required column(s): " + ", ".join(absent) +
                                 ". Expected: " + ", ".join(REQUIRED) + " (+ optional Timestamp).")
                    else:
                        ss.raw, ss.dataset_name, ss.strip_ws, ss.upload_sig = parsed, up.name, strip, sig
                        st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not parse file: {exc}")

    with active:
        md_html(f'<div class="glass" style="margin-bottom:14px"><h3 style="margin:0 0 4px;font-size:15px">Active Dataset: {escape(ss.dataset_name)}</h3>'
                f'<span style="color:#eadfdd;font-size:12px">{len(df):,} rows · {len(df.columns)} fields parsed · '
                f'{log["rows_raw"]:,} raw rows ingested · Status: {badge("Ready for Analysis", "resolved")}</span></div>')

    with left:
        st.markdown("##### Detected Schema & Fields")
        rawn = normalize_columns(ss.raw)
        kinds = {"Incident ID": "String (PK)", "Type": "Categorical", "Location": "String", "Severity": "Enum (4 ranks)",
                 "Status": "Enum (Resolved/Open)", "Response Time": "Duration (min)", "Timestamp": "Datetime"}
        rows = []
        for col, kind in kinds.items():
            present = col in rawn.columns
            cc = "Response Min" if col == "Response Time" else col
            sample = "—"
            if present and cc in df.columns and len(df):
                v = df[cc].iloc[0]
                sample = f"{v:.0f} min" if cc == "Response Min" else str(v)
            nulls = log["missing_by_col"].get(col) if col != "Timestamp" else log.get("bad_timestamps")
            rows.append({"Column": col, "Data Type": kind, "Sample Value": sample,
                         "Null %": "—" if nulls is None else f"{nulls / max(log['rows_raw'], 1) * 100:.1f}%",
                         "Status": "✔ Valid" if present else "Optional (not found)" if col == "Timestamp" else "✖ Missing"})
        st.dataframe(pd.DataFrame(rows), hide_index=True)


def reset_sample():
    ss = st.session_state
    ss.raw, ss.dataset_name, ss.strip_ws, ss.upload_sig = make_sample_data(), "incident_log_q3.csv", True, None
    ss.uploader_key += 1


def page_quality(df, log, q):
    ss = st.session_state
    c1, c2 = st.columns([4, 1.4])
    with c1:
        page_intro("Data Quality & Integrity", "Automated validation against operational schemas, completeness thresholds, and anomaly indicators")
    with c2:
        st.write("")
        if st.button("⟳ Run Quality Audit"):
            st.toast(f"Quality audit completed: Grade {q['grade']} · {q['overall']:.1f}%")
    ss.outlier_min = st.slider("Response-time outlier threshold (minutes)", 15, 120, int(ss.get("outlier_min", 45)))
    q = quality_metrics(df, log, ss.outlier_min)

    grade, colour = grade_for(q["overall"])
    sc = q["overall"]
    md_html(f'<div class="glass score-banner"><div class="score-visual"><div class="score-circle" style="background:conic-gradient({colour} 0 {sc}%, rgba(255,255,255,.1) {sc}% 100%)">'
            f'<div class="score-number" style="color:{colour}">{sc:.0f}%</div></div><div><h3 style="margin:0 0 4px;font-size:18px">Overall Data Health: '
            f'<span style="color:{colour}">Grade {grade}</span></h3><p style="margin:0;font-size:13px">{len(df):,} rows evaluated '
            f'({log["rows_raw"]:,} ingested) against {4 if q["timeliness"] is not None else 3} integrity dimensions.</p></div></div>'
            f'{badge("Certification Passed", "resolved") if sc >= 95 else badge("Review Recommended", "warning")}</div>')

    tl = q["timeliness"]
    cards = [
        stat_card("Completeness", f"{q['completeness']:.1f}%", f"{log['missing_cells']:,} empty required cells", GREEN),
        stat_card("Uniqueness", f"{q['uniqueness']:.1f}%", f"{log['duplicates']:,} duplicate incident IDs removed", GREEN),
        stat_card("Validity", f"{q['validity']:.1f}%", f"{q['outliers']:,} response times &gt; {q['outlier_min']}m flagged", ORANGE),
        stat_card("Timeliness", "n/a" if tl is None else f"{tl:.1f}%",
                  "no Timestamp column" if tl is None else f"{log['bad_timestamps']:,} invalid timestamps", GREEN),
    ]
    for col, c in zip(st.columns(4), cards):
        col.markdown(c, unsafe_allow_html=True)

    def item(ok, title, text):
        return (f'<div class="check-item"><div><i class="dot{"" if ok else " orange"}"></i>{title}</div>'
                f'{badge(text, "resolved" if ok else "open")}</div>')
    inv = log["invalid_severity"] + log["invalid_status"]
    checks = [
        item(log["duplicates"] == 0 and log["missing_id"] == 0, "Primary Key Integrity: unique, non-null incident IDs",
             "Passed" if log["duplicates"] + log["missing_id"] == 0 else f"{log['duplicates']:,} duplicates · {log['missing_id']:,} missing IDs removed"),
        item(inv == 0, "Taxonomy Alignment: Severity / Status match the dispatch taxonomy",
             f"{log['category_fixed']:,} values standardised" + ("" if inv == 0 else f" · {inv:,} set to Unknown")),
        item(q["outliers"] == 0, f"Response Time Bounds: latencies above {q['outlier_min']} minutes",
             "No outliers" if q["outliers"] == 0 else f"{q['outliers']:,} outliers · {log['imputed']:,} invalid values imputed"),
    ]
    if tl is not None:
        checks.append(item(log["bad_timestamps"] + log["future_timestamps"] == 0, "Timestamp Validity: parseable, not in the future",
                           "Valid" if log["bad_timestamps"] + log["future_timestamps"] == 0 else f"{log['bad_timestamps'] + log['future_timestamps']:,} invalid"))
    section("Quality Verification Checklist")
    md_html("".join(checks))

    a, b = st.columns(2)
    with a:
        section("Cleaning Log", "What the pipeline changed between raw and cleaned data")
        steps = [("Rows ingested", log["rows_raw"]), ("Whitespace fixes", log["whitespace_fixed"]),
                 ("Category values standardised", log["category_fixed"]), ("Duplicate incident IDs removed", log["duplicates"]),
                 ("Rows without incident ID dropped", log["missing_id"]), ("Response times parsed / imputed", log["imputed"]),
                 ("Rows after cleaning", log["rows_clean"])]
        st.dataframe(pd.DataFrame(steps, columns=["Step", "Rows / values"]), hide_index=True)
    with b:
        section("Missing Values", "Empty required cells before cleaning")
        if log["missing_cells"]:
            render_fig(fig_missing(log["missing_by_col"], log["rows_raw"]))
        else:
            st.success("No missing values detected in required columns.")


def page_exploratory(df):
    c1, c2 = st.columns([4, 1.6])
    with c1:
        page_intro("Exploratory Incident Analysis", "Statistical distribution of incident velocities, shift windows, and multi-district demand")
    with c2:
        st.write("")
        rng = st.selectbox("Analysis range", ["Last 7 days", "Last 30 days", "Last 90 days", "All data"], index=2, label_visibility="collapsed")
    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}.get(rng)
    d = filter_range(df, days)
    if not has_time(df):
        st.info("No Timestamp column found — range filter, peak window and heat-map are unavailable.")
    if d.empty:
        st.warning("No incidents in the selected range.")
        return
    ds = district_stats(d)
    pw = peak_window(d)
    fast, slow = ds["avg_resp"].idxmin(), ds["avg_resp"].idxmax()
    r = d["Response Min"]
    cards = [
        stat_card("Mean response time", f"{r.mean():.1f} <span style='font-size:15px;color:{MUTED}'>min</span>",
                  f"Median: <strong>{r.median():.1f} min</strong> · P95: {np.percentile(r, 95):.0f}"),
        stat_card("Peak incident window", pw[0] if pw else "n/a", f'<strong style="color:{ORANGE}">{pw[1]:+.0f}%</strong> vs daily baseline' if pw else "needs Timestamp", ORANGE),
        stat_card("Fastest district response", fast, f"Avg: <strong>{ds.loc[fast, 'avg_resp']:.0f} min</strong> response time", GREEN),
        stat_card("Slowest district response", slow, f'<strong style="color:{RED}">{ds.loc[slow, "avg_resp"]:.0f} min</strong> avg response', RED),
    ]
    for col, c in zip(st.columns(4), cards):
        col.markdown(c, unsafe_allow_html=True)

    section("District Operational Profiles", "Comparative volume and response statistics across operational sectors")
    top = ds["incidents"].idxmax()
    for rr in range(0, len(ds), 3):
        for col, (loc, row) in zip(st.columns(3), list(ds.iterrows())[rr:rr + 3]):
            b = badge("Latency Alert", "warning") if loc == slow else badge("High Load", "critical") if loc == top \
                else badge("Optimal", "resolved") if loc == fast else badge("Stable", "resolved")
            col.markdown(f'<div class="district-card glass" style="margin-bottom:12px"><h4>{loc} {b}</h4>'
                         f'<div class="district-metric">{int(row.incidents):,} <small>incidents</small></div>'
                         f'<span style="font-size:12px;color:{SECONDARY}">{row.share:.1f}% of total volume · Avg response: {row.avg_resp:.0f} min · P90: {row.p90:.0f} min</span></div>',
                         unsafe_allow_html=True)

    section("Distributions", "Seaborn views of response velocity and demand patterns")
    a, b = st.columns(2)
    with a:
        render_fig(fig_response_hist(d))
    with b:
        render_fig(fig_box_by_district(d))
    hm = fig_heatmap(d)
    if hm is not None:
        render_fig(hm)


def page_visuals(df):
    section_df = df
    with st.expander("Chart filters", expanded=False):
        f1, f2 = st.columns(2)
        types = f1.multiselect("Incident types", sorted(df["Type"].unique()), default=sorted(df["Type"].unique()))
        sevs = f2.multiselect("Severities", [s for s in SEVERITY_ORDER + ["Unknown"] if s in df["Severity"].unique()],
                              default=[s for s in SEVERITY_ORDER + ["Unknown"] if s in df["Severity"].unique()])
    section_df = df[df["Type"].isin(types) & df["Severity"].isin(sevs)]
    if section_df.empty:
        page_intro("Visual Analytics & Charts", "Incident distribution, severity breakdown, trends, and unit allocation")
        st.warning("No incidents match the selected chart filters.")
        return
    figs = build_figures(section_df)
    pngs = {k: fig_to_png(f) for k, f in figs.items()}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in pngs.items():
            z.writestr(re.sub(r"[^a-z0-9]+", "_", k.lower()) + ".png", v)
    c1, c2 = st.columns([4, 1.6])
    with c1:
        page_intro("Visual Analytics & Charts", "Incident distribution, severity breakdown, trends, and unit allocation curves")
    with c2:
        st.write("")
        st.download_button("⬇ Export Chart Suite", buf.getvalue(), "crisis-fusion-charts.zip", "application/zip")
    items = list(figs.items())
    for i in range(0, len(items), 2):
        for col, (name, fig) in zip(st.columns(2), items[i:i + 2]):
            with col, st.container(border=True):
                render_fig(fig)
    if "Incident volume trend" not in figs:
        st.info("The trend chart needs a Timestamp column.")
    st.caption("Resource coverage uses reference values (the incident schema has no unit columns); the dashed line is the "
               f"{COVERAGE_THRESHOLD}% operating threshold.")


def page_ai(df):
    ss = st.session_state
    page_intro("AI Intelligence & Synthesis", "Evidence-backed signals, automated risk clustering, and an interactive operations assistant",
               badge("Assistant: Online (rule-based)", "resolved"))
    findings = build_findings(df)

    def run(q_text=None):
        if q_text is not None:
            ss.ai_input = q_text
        ss.ai_answer_for = ss.ai_input.strip()

    with st.container(border=True):
        st.markdown("#### Ask AI Operations Assistant")
        st.caption("Query incident history, ask for predictive dispatch suggestions, or identify bottlenecks")
        i1, i2 = st.columns([5, 1.3])
        i1.text_input("Question", key="ai_input", placeholder="e.g. Why are North District responses delayed after 18:00?",
                      label_visibility="collapsed")
        i2.button("Analyze", on_click=run)
        chips = ["Why is North District slow?", "Specialist coverage gap", "Friday demand prediction"]
        for col, ch in zip(st.columns(len(chips) + 3)[:len(chips)], chips):
            col.button(ch, key=f"chip_{ch}", on_click=run, args=(ch,))
        if ss.get("ai_answer_for"):
            md_html(f'<div class="ai-response"><strong>AI Analysis:</strong> {escape(answer_query(ss.ai_answer_for, df))}</div>')

    def card(title, items, cls=""):
        return f'<div class="insight glass {cls}"><h3>{title}</h3><ul>{"".join(f"<li>{escape(i)}</li>" for i in items)}</ul></div>'
    a, b, c = st.columns(3)
    a.markdown(card("Key operational findings", findings["key"]), unsafe_allow_html=True)
    b.markdown(card("Risk analysis &amp; vulnerabilities", findings["risk"], "risk"), unsafe_allow_html=True)
    c.markdown(card("Recommended mitigation actions", findings["actions"], "recommend"), unsafe_allow_html=True)
    st.caption("Answers are generated with pandas/numpy statistics over the cleaned dataset. To use an LLM instead, "
               "pass `df.describe()` and the findings above into your model API inside `answer_query()`.")


SORTS = {
    "Newest first": None,
    "Response: fastest": ("Response Min", True),
    "Response: slowest": ("Response Min", False),
    "Incident ID (A→Z)": ("Incident ID", True),
    "Location (A→Z)": ("Location", True),
    "Severity: highest": "severity",
}


def explorer_filter(df, search, status, sev, typ, sort):
    d = df
    if search.strip():
        blob = (d["Incident ID"] + " " + d["Type"] + " " + d["Location"] + " " + d["Severity"] + " " + d["Status"]).str.lower()
        d = d[blob.str.contains(search.strip().lower(), regex=False)]
    if status != "All statuses":
        d = d[d["Status"] == status]
    if sev != "All severities":
        d = d[d["Severity"] == sev]
    if typ != "All types":
        d = d[d["Type"] == typ]
    rule = SORTS[sort]
    if rule == "severity":
        d = d.assign(_r=d["Severity"].map(SEV_RANK).fillna(0)).sort_values("_r", ascending=False, kind="stable").drop(columns="_r")
    elif rule:
        d = d.sort_values(rule[0], ascending=rule[1], kind="stable")
    return d


def reset_explorer():
    ss = st.session_state
    ss.exp_search, ss.exp_status, ss.exp_sev, ss.exp_type, ss.exp_sort = "", "All statuses", "All severities", "All types", "Newest first"


def page_explorer(df):
    ss = st.session_state
    ss.setdefault("exp_page", 1)
    c1, c2 = st.columns([4, 1.4])
    with c1:
        page_intro("Incident Data Explorer", "Granular record inspection, multi-attribute search, sorting, and pagination")
    r1 = st.columns([3, 1.3, 1.3, 1.3])
    search = r1[0].text_input("Search", key="exp_search", placeholder="Search incident ID, type, location…")
    status = r1[1].selectbox("Status", ["All statuses", "Resolved", "Open"], key="exp_status")
    sev = r1[2].selectbox("Severity", ["All severities"] + [s for s in SEVERITY_ORDER + ["Unknown"] if s in df["Severity"].unique()], key="exp_sev")
    typ = r1[3].selectbox("Type", ["All types"] + sorted(df["Type"].unique()), key="exp_type")
    r2 = st.columns([1.6, 1, 1, 3])
    sort = r2[0].selectbox("Sort", list(SORTS), key="exp_sort")
    size = r2[1].selectbox("Rows / page", [5, 10, 25, 50, 100], index=1, key="exp_size")
    r2[2].write("")
    r2[2].button("Reset filters", on_click=reset_explorer)

    d = explorer_filter(df, search, status, sev, typ, sort)
    ss["explorer_slice"] = d
    with c2:
        st.write("")
        st.download_button("⬇ Export Slice", d[export_cols(d)].to_csv(index=False).encode("utf-8"),
                           f"crisis-fusion-slice-{datetime.now():%Y-%m-%d}.csv", "text/csv")

    sig = (search, status, sev, typ, sort, size)
    if ss.get("exp_sig") != sig:
        ss.exp_sig, ss.exp_page = sig, 1
    pages = max(1, -(-len(d) // size))
    ss.exp_page = min(max(1, ss.exp_page), pages)
    start = (ss.exp_page - 1) * size
    view = d.iloc[start:start + size][export_cols(d)]

    if view.empty:
        st.info("No matching incidents found. Try resetting search filters.")
    else:
        def paint(s, pal):
            return [f"color:{pal.get(v, TEXT)};font-weight:600" for v in s]
        styled = (view.style.apply(paint, pal=SEV_COLORS, subset=["Severity"]).apply(paint, pal=STATUS_COLORS, subset=["Status"])
                  .format({"Response Min": "{:.0f} min"}))
        st.dataframe(styled, hide_index=True, height=38 * (len(view) + 1) + 3)
    p1, p2, p3 = st.columns([6, 1, 1])
    p1.caption(f"{len(d):,} incident{'' if len(d) == 1 else 's'} found · " +
               (f"{start + 1:,}–{min(start + size, len(d)):,} of {len(d):,} · page {ss.exp_page}/{pages}" if len(d) else "0 results"))
    p2.button("← Prev", disabled=ss.exp_page <= 1, on_click=lambda: ss.update(exp_page=ss.exp_page - 1))
    p3.button("Next →", disabled=ss.exp_page >= pages, on_click=lambda: ss.update(exp_page=ss.exp_page + 1))


def page_export(df, q):
    ss = st.session_state
    page_intro("Export Reports & Dispatches", "Generate executive summaries, compliance audits, and tabular CSV extracts", badge("Export Engine: Ready", "resolved"))
    slice_df = ss.get("explorer_slice")
    options = ["Full cleaned dataset"] + (["Current Data Explorer slice"] if slice_df is not None else [])
    scope = st.radio("Scope for CSV / JSON exports", options, horizontal=True, index=len(options) - 1)
    d = slice_df if scope.startswith("Current") and slice_df is not None else df
    findings = build_findings(df)
    stamp = f"{datetime.now():%Y-%m-%d}"

    def card(tag, kind, title, desc, meta):
        return (f'<div class="export-card glass" style="margin-bottom:8px">{badge(tag, kind)}<h3>{title}</h3><p>{desc}</p>'
                f'<div class="export-meta">{"".join(f"<span>{m}</span>" for m in meta)}</div></div>')
    a, b = st.columns(2)
    with a:
        md_html(card("Data File", "info", "Filtered Incidents (CSV)", "Download the selected slice with all active filters applied.",
                     ["Format: CSV", "Encoding: UTF-8", f"Rows: {len(d):,}"]))
        st.download_button("⬇ Download CSV File", d[export_cols(d)].to_csv(index=False).encode("utf-8"),
                           f"crisis-fusion-export-{stamp}.csv", "text/csv", key="dl_csv")
    with b:
        md_html(card("Full Dossier", "resolved", "Executive Intelligence Summary (JSON)",
                     "JSON payload with metrics, risk signals and recommendations for external integration.",
                     ["Format: JSON", "Schema: CrisisFusion v2.4"]))
        st.download_button("📄 Export JSON Summary", build_dossier(d, df, q, ss.dataset_name, findings),
                           "crisis-fusion-dossier.json", "application/json", key="dl_json")
    c, e = st.columns(2)
    with c:
        figs = build_figures(df)
        pngs = {k: fig_to_png(f) for k, f in figs.items()}
        for f in figs.values():
            plt.close(f)
        md_html(card("Printable Dossier", "warning", "Printable Incident Briefing",
                     "Self-contained HTML briefing with findings and charts — open it and press Ctrl+P to save as PDF.",
                     ["Target: Printer / PDF", "Includes: Charts & Findings"]))
        st.download_button("🖨 Download Printable Briefing", build_briefing_html(df, q, findings, pngs, ss.dataset_name),
                           f"crisis-fusion-briefing-{stamp}.html", "text/html", key="dl_html")
    with e:
        md_html(card("Compliance", "resolved", "Data Quality & Audit Certificate (TXT)",
                     f"Manifest verifying {q['overall']:.1f}% data health, uniqueness and completeness.", ["Format: Manifest TXT"]))
        st.download_button("🛡 Download Audit Manifest", build_certificate(df, q, ss.dataset_name),
                           "data-quality-audit-certificate.txt", "text/plain", key="dl_txt")


# ══════════════════════════════════════════════════════════════════════════════
# 8. APP SHELL
# ══════════════════════════════════════════════════════════════════════════════
def main():
    ss = st.session_state
    ss.setdefault("page", "overview")
    ss.setdefault("uploader_key", 0)
    ss.setdefault("outlier_min", 45)
    ss.setdefault("strip_ws", True)
    if "raw" not in ss:
        ss.raw, ss.dataset_name, ss.upload_sig = make_sample_data(), "incident_log_q3.csv", None
    md_html(CSS)
    setup_plot_style()

    try:
        df, log = clean_data(ss.raw, ss.strip_ws)
    except ValueError as exc:
        st.error(f"{exc} — falling back to the sample dataset.")
        reset_sample()
        df, log = clean_data(ss.raw, True)
    q = quality_metrics(df, log, ss.outlier_min)

    with st.sidebar:
        md_html('<div class="brand"><div class="brand-mark">📊</div><div><strong>Crisis Fusion</strong><span>Operations intelligence</span></div></div>')
        st.radio("Workspace pages", list(PAGES), format_func=lambda k: PAGES[k][0], key="page", label_visibility="collapsed")
        dot = "" if q["overall"] >= 95 else " orange" if q["overall"] >= 85 else " red"
        md_html(f'<hr style="border-color:rgba(255,255,255,.09)"><div style="font-size:12px;color:{SECONDARY}"><i class="dot{dot}"></i>'
                f'Data pipeline {"healthy" if not dot else "needs review"} · {q["overall"]:.1f}%</div>')

    page = ss.page
    t1, t2, t3, t4 = st.columns([5, 3.2, 1.7, 1.2])
    t1.markdown(f'<div class="eyebrow">Operations / {PAGES[page][0].split("  ")[-1]}</div><div class="topbar-title">{PAGES[page][1]}</div>', unsafe_allow_html=True)
    t2.markdown(f'<div class="dataset-state"><i class="dot"></i>{escape(ss.dataset_name)}<span class="eyebrow">· Active</span></div>', unsafe_allow_html=True)
    t3.button("⬆ Dataset Upload", on_click=goto, args=("dataset-upload",), key="top_upload")
    t4.button("📤 Export", on_click=goto, args=("export-reports",), key="top_export")
    st.divider()

    if page == "overview":
        page_overview(df, q)
    elif page == "dataset-upload":
        page_upload(df, log)
    elif page == "data-quality":
        page_quality(df, log, q)
    elif page == "exploratory-analysis":
        page_exploratory(df)
    elif page == "visualizations":
        page_visuals(df)
    elif page == "ai-insights":
        page_ai(df)
    elif page == "data-explorer":
        page_explorer(df)
    elif page == "export-reports":
        page_export(df, q)


if __name__ == "__main__":
    main()
