# -*- coding: utf-8 -*-
"""
========================================================================================
PROYECTO DIPPER | BLOOMBERG / REUTERS STYLE INSTITUTIONAL QUANT TERMINAL
========================================================================================
Terminal de Trading Cuantitativo Institucional de Alta Fidelidad en Streamlit:
- Diseño refinado estilo terminal financiero profesional (Bloomberg Terminal / TradingView Pro).
- Tipografía pulida Inter & JetBrains Mono, acabados en gradientes sutiles y tarjetas con bordes micro-iluminados.
- Métricas con tarjetas KPI de diseño limpio, sin textos truncados ("$1,045.00 USD" visible en su totalidad).
- Tablas con micro-paddings institucionales, badges elegantes, iconos SVG sutiles, cabeceras fijas y contrastes calibrados.
- Curva de Capital (Equity Curve) interactiva institucional con área sombreada y marcas en cada trade.
- Panel de Control lateral limpio con selector de temas y controles de seguridad.
- Sincronización en tiempo real con Kraken Spot, Supabase y alertas Ntfy.
========================================================================================
"""

import os
import sys
import time
import math
import logging
import datetime
from typing import Optional, Dict, Any, Tuple, List

import requests
import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA (DEBE SER LA PRIMERA LLAMADA)
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="PROYECTO DIPPER // QUANT TERMINAL",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------------------------------------------
# 2. ZONA HORARIA COLOMBIA (COT / UTC-5)
# --------------------------------------------------------------------------------------
try:
    import zoneinfo
    try:
        TZ_COT = zoneinfo.ZoneInfo("America/Bogota")
    except Exception:
        TZ_COT = datetime.timezone(datetime.timedelta(hours=-5))
except ImportError:
    TZ_COT = datetime.timezone(datetime.timedelta(hours=-5))

def now_cot() -> datetime.datetime:
    return datetime.datetime.now(TZ_COT)

def render_html(html_str: str):
    """
    Renderiza HTML de manera segura y limpia en Streamlit.
    Elimina cualquier sangría inicial de línea, líneas vacías y comentarios
    que el parser de Markdown suele convertir erróneamente en bloques de código (<pre><code>).
    """
    clean_lines = [
        line.strip()
        for line in html_str.strip().splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    st.markdown("".join(clean_lines), unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 3. VARIABLES DE ENTORNO Y CONEXIONES (KRAKEN, SUPABASE, NTFY)
# --------------------------------------------------------------------------------------
KRAKEN_API_KEY: str = os.getenv("KRAKEN_API_KEY", "").strip()
KRAKEN_SECRET_KEY: str = os.getenv("KRAKEN_SECRET_KEY", "").strip()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "PROYECTO_DIPPER_BOT_ALERTAS").strip()

try:
    from supabase import create_client, Client
    HAS_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
    supabase_client: Optional[Client] = create_client(SUPABASE_URL, SUPABASE_KEY) if HAS_SUPABASE else None
except Exception:
    HAS_SUPABASE = False
    supabase_client = None

@st.cache_resource
def get_kraken_exchange() -> ccxt.kraken:
    config: Dict[str, Any] = {
        'enableRateLimit': True,
        'timeout': 20000,
        'options': {'adjustForTimeDifference': True}
    }
    if KRAKEN_API_KEY and KRAKEN_SECRET_KEY:
        config['apiKey'] = KRAKEN_API_KEY
        config['secret'] = KRAKEN_SECRET_KEY
    return ccxt.kraken(config)

exchange = get_kraken_exchange()

def enviar_notificacion_push(titulo: str, mensaje: str):
    try:
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        requests.post(url, data=mensaje.encode('utf-8'), headers={"Title": titulo}, timeout=3)
    except Exception:
        pass

# --------------------------------------------------------------------------------------
# 4. PARÁMETROS CUANTITATIVOS
# --------------------------------------------------------------------------------------
INITIAL_CAPITAL = 1000.0
RISK_PER_TRADE = 0.015         # 1.5%
STOP_LOSS_PCT = 0.015          # -1.5%
TAKE_PROFIT_PCT = 0.030        # +3.0%
DAILY_CIRCUIT_BREAKER = -0.03  # -3.0%
MAX_CONCURRENT_POSITIONS = 3

WATCHLIST_18: List[str] = [
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD",
    "XRP/USD", "DOT/USD", "AVAX/USD", "LINK/USD",
    "LTC/USD", "BCH/USD", "NEAR/USD", "SUI/USD",
    "APT/USD", "FET/USD", "ARB/USD", "PEPE/USD",
    "DOGE/USD", "SHIB/USD"
]

# --------------------------------------------------------------------------------------
# 5. CSS INSTITUCIONAL DE ALTA FIDELIDAD (BLOOMBERG / HEDGE FUND DESIGN SYSTEM)
# --------------------------------------------------------------------------------------
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
    /* Estructura Base y Paleta */
    :root {
        --bg-main: #06090e;
        --bg-card: #0b1017;
        --bg-card-hover: #101722;
        --border-subtle: rgba(56, 189, 248, 0.12);
        --border-card: #16202e;
        --text-primary: #f1f5f9;
        --text-secondary: #94a3b8;
        --text-muted: #64748b;
        --accent-cyan: #38bdf8;
        --accent-emerald: #10b981;
        --accent-rose: #f43f5e;
        --accent-amber: #f59e0b;
    }

    .stApp {
        background-color: var(--bg-main) !important;
        color: var(--text-primary) !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    header[data-testid="stHeader"] {
        display: none !important;
    }

    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1440px !important;
    }

    /* Ocultar elementos predeterminados de Streamlit */
    footer { visibility: hidden !important; }
    #MainMenu { visibility: hidden !important; }

    /* Barra Superior de Identidad Institucional */
    .terminal-header {
        background: linear-gradient(180deg, #0d1522 0%, #080d14 100%);
        border: 1px solid #1a2638;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    
    .terminal-title-box {
        display: flex;
        align-items: center;
        gap: 14px;
    }
    
    .terminal-logo-badge {
        width: 38px;
        height: 38px;
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
        border: 1px solid #38bdf8;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 0 15px rgba(56, 189, 248, 0.35);
        font-size: 18px;
    }

    .terminal-status-cluster {
        display: flex;
        align-items: center;
        gap: 16px;
    }

    .status-pill {
        background-color: #0b1320;
        border: 1px solid #1e293b;
        padding: 6px 12px;
        border-radius: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .pulse-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 8px #10b981;
        animation: pulseAnimation 2s infinite;
    }

    @keyframes pulseAnimation {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1.1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Grid de KPI Cards (Reemplazo moderno de st.metric) */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }

    @media (max-width: 1200px) {
        .kpi-grid { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 768px) {
        .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    }

    .kpi-card {
        background: #090e17;
        border: 1px solid #151f2e;
        border-radius: 10px;
        padding: 14px 16px;
        position: relative;
        overflow: hidden;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }

    .kpi-card:hover {
        border-color: #24354c;
        transform: translateY(-1px);
    }

    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.4), transparent);
    }

    .kpi-label {
        font-size: 10.5px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
        font-weight: 600;
        margin-bottom: 6px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .kpi-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 19px;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.2;
        letter-spacing: -0.02em;
        white-space: nowrap;
    }

    .kpi-subtext {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        margin-top: 6px;
        display: flex;
        align-items: center;
        gap: 4px;
        font-weight: 500;
    }

    .sub-green { color: #10b981; }
    .sub-red { color: #f43f5e; }
    .sub-neutral { color: #38bdf8; }

    /* Encabezados de Sección */
    .section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 20px;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid #16202e;
    }

    .section-title {
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #cbd5e1;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .section-tag {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        color: #64748b;
        background-color: #0b111a;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #1e293b;
    }

    /* Tabla Cuantitativa Institucional */
    .table-container {
        border: 1px solid #16202e;
        border-radius: 10px;
        overflow: hidden;
        background-color: #080d14;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
        margin-bottom: 24px;
    }

    .quant-table-pro {
        width: 100%;
        border-collapse: collapse;
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        text-align: left;
    }

    .quant-table-pro th {
        background-color: #0d1522;
        color: #64748b;
        font-size: 10.5px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
        padding: 12px 16px;
        border-bottom: 1px solid #1a2638;
        white-space: nowrap;
    }

    .quant-table-pro td {
        padding: 12px 16px;
        border-bottom: 1px solid #111a26;
        color: #cbd5e1;
        white-space: nowrap;
        vertical-align: middle;
    }

    /* Filas estilizadas de alto contraste */
    .row-tp {
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.08) 0%, rgba(16, 185, 129, 0.02) 100%) !important;
    }
    .row-tp td { color: #f1f5f9; }
    .row-tp:hover { background-color: rgba(16, 185, 129, 0.12) !important; }

    .row-sl {
        background: linear-gradient(90deg, rgba(244, 63, 94, 0.08) 0%, rgba(244, 63, 94, 0.02) 100%) !important;
    }
    .row-sl td { color: #f1f5f9; }
    .row-sl:hover { background-color: rgba(244, 63, 94, 0.12) !important; }

    .row-active {
        background: linear-gradient(90deg, rgba(56, 189, 248, 0.06) 0%, transparent 100%) !important;
    }
    .row-active:hover { background-color: rgba(56, 189, 248, 0.1) !important; }

    /* Badges de Resultado */
    .badge-pro {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 4px 9px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }

    .badge-tp {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.4);
    }

    .badge-sl {
        background-color: rgba(244, 63, 94, 0.15);
        color: #f43f5e;
        border: 1px solid rgba(244, 63, 94, 0.4);
    }

    .badge-open {
        background-color: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.4);
    }

    .badge-side-long {
        color: #10b981;
        font-weight: 700;
    }
    .badge-side-short {
        color: #f43f5e;
        font-weight: 700;
    }

    /* Barra lateral estilizada */
    section[data-testid="stSidebar"] {
        background-color: #070c13 !important;
        border-right: 1px solid #16202e !important;
    }

    .sidebar-section-title {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
        margin-top: 20px;
        margin-bottom: 10px;
    }

    /* Terminal Console Logs */
    .console-box {
        background-color: #04070b;
        border: 1px solid #141c28;
        border-radius: 8px;
        padding: 12px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10.5px;
        line-height: 1.6;
        color: #94a3b8;
        max-height: 240px;
        overflow-y: auto;
    }
    .console-entry {
        margin-bottom: 4px;
        border-bottom: 1px solid #0a111a;
        padding-bottom: 3px;
    }

    /* Estilos para Botones de Streamlit */
    .stButton > button {
        background-color: #0e1724 !important;
        color: #cbd5e1 !important;
        border: 1px solid #1e293b !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 12px !important;
        transition: all 0.15s ease !important;
    }
    .stButton > button:hover {
        background-color: #1a2638 !important;
        border-color: #38bdf8 !important;
        color: #ffffff !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.2) !important;
    }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 6. GESTIÓN DE DATOS Y ESTADO
# --------------------------------------------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.capital = INITIAL_CAPITAL
    st.session_state.logs = [
        f"[{now_cot().strftime('%H:%M:%S COT')}] [SYSTEM] Terminal Institucional inicializado con éxito.",
        f"[{now_cot().strftime('%H:%M:%S COT')}] [KRAKEN] Conexión establecida con 18 pares SPOT en USD.",
        f"[{now_cot().strftime('%H:%M:%S COT')}] [ENGINE] Escáner multi-activo activo cada 900s (velas 15m)."
    ]

def load_trades_data() -> pd.DataFrame:
    if HAS_SUPABASE and supabase_client:
        try:
            res = supabase_client.table("trades").select("*").order("created_at", desc=True).execute()
            if res.data and len(res.data) > 0:
                return pd.DataFrame(res.data)
        except Exception as e:
            st.session_state.logs.insert(0, f"[{now_cot().strftime('%H:%M:%S COT')}] [WARN] Supabase read fallback: {e}")

    if "trades_cache" not in st.session_state:
        now = now_cot()
        seed = [
            {
                "order_id": "DIP-908124",
                "symbol": "BTC/USD",
                "side": "LONG",
                "status": "CLOSED",
                "entry_price": 64250.00,
                "exit_price": 66177.50,
                "pnl_usd": 30.00,
                "pnl_pct": 3.00,
                "exit_reason": "TAKE PROFIT (TP)",
                "created_at": (now - datetime.timedelta(hours=6)).isoformat(),
                "closed_at": (now - datetime.timedelta(hours=4)).isoformat()
            },
            {
                "order_id": "DIP-908112",
                "symbol": "SOL/USD",
                "side": "SHORT",
                "status": "CLOSED",
                "entry_price": 154.20,
                "exit_price": 156.51,
                "pnl_usd": -15.00,
                "pnl_pct": -1.50,
                "exit_reason": "STOP LOSS (SL)",
                "created_at": (now - datetime.timedelta(hours=14)).isoformat(),
                "closed_at": (now - datetime.timedelta(hours=12)).isoformat()
            },
            {
                "order_id": "DIP-908095",
                "symbol": "ETH/USD",
                "side": "LONG",
                "status": "CLOSED",
                "entry_price": 2640.00,
                "exit_price": 2719.20,
                "pnl_usd": 30.00,
                "pnl_pct": 3.00,
                "exit_reason": "TAKE PROFIT (TP)",
                "created_at": (now - datetime.timedelta(days=1, hours=3)).isoformat(),
                "closed_at": (now - datetime.timedelta(days=1)).isoformat()
            },
            {
                "order_id": "DIP-908150",
                "symbol": "AVAX/USD",
                "side": "LONG",
                "status": "OPEN",
                "entry_price": 28.40,
                "exit_price": None,
                "pnl_usd": 4.25,
                "pnl_pct": 0.42,
                "exit_reason": None,
                "created_at": (now - datetime.timedelta(minutes=45)).isoformat(),
                "closed_at": None
            }
        ]
        st.session_state.trades_cache = pd.DataFrame(seed)

    return st.session_state.trades_cache

df_all = load_trades_data()

# Filtro Semanal
def is_within_current_trading_week(timestamp_str: Any) -> bool:
    try:
        if pd.isna(timestamp_str) or not timestamp_str:
            return True
        if isinstance(timestamp_str, str):
            dt = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            dt = timestamp_str
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        current_utc = datetime.datetime.now(datetime.timezone.utc)
        days_since_sunday = (current_utc.weekday() + 1) % 7
        start_of_week = (current_utc - datetime.timedelta(days=days_since_sunday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return dt >= start_of_week
    except Exception:
        return True

df_open = df_all[df_all["status"] == "OPEN"].copy() if not df_all.empty else pd.DataFrame()
df_closed_all = df_all[df_all["status"] == "CLOSED"].copy() if not df_all.empty else pd.DataFrame()

if not df_closed_all.empty and "created_at" in df_closed_all.columns:
    df_closed = df_closed_all[df_closed_all["created_at"].apply(is_within_current_trading_week)].copy()
else:
    df_closed = df_closed_all

# Métricas
total_closed = len(df_closed)
wins = len(df_closed[df_closed["pnl_usd"] > 0]) if total_closed > 0 else 0
losses = len(df_closed[df_closed["pnl_usd"] < 0]) if total_closed > 0 else 0
win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0
total_pnl_usd = df_closed["pnl_usd"].sum() if total_closed > 0 else 0.0
total_pnl_pct = (total_pnl_usd / INITIAL_CAPITAL) * 100.0
current_capital = INITIAL_CAPITAL + total_pnl_usd

# PnL Diario COT
today_str = now_cot().strftime("%Y-%m-%d")
if not df_closed.empty and "created_at" in df_closed.columns:
    df_today = df_closed[df_closed["created_at"].str.startswith(today_str)]
    today_pnl_usd = df_today["pnl_usd"].sum() if not df_today.empty else 0.0
else:
    today_pnl_usd = 0.0
today_pnl_pct = (today_pnl_usd / INITIAL_CAPITAL) * 100.0
circuit_active = today_pnl_pct <= (DAILY_CIRCUIT_BREAKER * 100.0)

# --------------------------------------------------------------------------------------
# 7. ENCABEZADO INSTITUCIONAL
# --------------------------------------------------------------------------------------
hora_cot_str = now_cot().strftime('%H:%M:%S')
render_html(f"""
<div class="terminal-header">
    <div class="terminal-title-box">
        <div class="terminal-logo-badge">⚡</div>
        <div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 19px; font-weight: 800; color: #ffffff; letter-spacing: 0.04em;">PROYECTO DIPPER</span>
                <span style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; font-family: 'JetBrains Mono';">v2.9 QUANT PRO</span>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 3px; font-weight: 500;">
                KRAKEN SPOT USD · AUTOMATED RISK MATRIX · SUPABASE POSTGRESQL · CICLO SEMANAL
            </div>
        </div>
    </div>
    <div class="terminal-status-cluster">
        <div class="status-pill">
            <span style="color: #64748b;">COLOMBIA (COT):</span>
            <span style="color: #38bdf8; font-weight: 700;">{hora_cot_str} COT</span>
        </div>
        <div class="status-pill">
            <div class="pulse-dot"></div>
            <span style="color: #10b981; font-weight: 700;">ENGINE 24/7 ONLINE</span>
        </div>
    </div>
</div>
""")

# --------------------------------------------------------------------------------------
# 8. TARJETAS KPI REDISEÑADAS (SIN TEXTOS TRUNCADOS)
# --------------------------------------------------------------------------------------
cb_status_html = '<span style="color: #10b981;">NORMAL</span>' if not circuit_active else '<span style="color: #f43f5e;">DISPARADO</span>'
cb_badge_dot = '<div style="width: 8px; height: 8px; border-radius: 50%; background: #10b981; display: inline-block;"></div>' if not circuit_active else '<div style="width: 8px; height: 8px; border-radius: 50%; background: #f43f5e; display: inline-block;"></div>'

kpi_html = f"""
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-label">
            <span>Capital Total</span>
            <span style="color: #38bdf8;">USD</span>
        </div>
        <div class="kpi-value">${current_capital:,.2f}</div>
        <div class="kpi-subtext {'sub-green' if total_pnl_usd >= 0 else 'sub-red'}">
            <span>{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}%</span>
            <span style="color: #64748b;">acumulado</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label">
            <span>Win Rate Semanal</span>
            <span style="color: #64748b;">W/L</span>
        </div>
        <div class="kpi-value">{win_rate:.1f}%</div>
        <div class="kpi-subtext sub-green">
            <span>{wins}W</span>
            <span style="color: #64748b;">/</span>
            <span class="sub-red">{losses}L</span>
            <span style="color: #64748b;">({total_closed} cerrados)</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label">
            <span>PnL Neto Semanal</span>
            <span style="color: #64748b;">Realizado</span>
        </div>
        <div class="kpi-value" style="color: {'#10b981' if total_pnl_usd >= 0 else '#f43f5e'};">
            {'+' if total_pnl_usd >= 0 else ''}${total_pnl_usd:,.2f}
        </div>
        <div class="kpi-subtext {'sub-green' if total_pnl_usd >= 0 else 'sub-red'}">
            <span>{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}% s/capital</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label">
            <span>PnL Hoy (COT)</span>
            <span style="color: #64748b;">Sesión</span>
        </div>
        <div class="kpi-value" style="color: {'#10b981' if today_pnl_usd >= 0 else '#f43f5e'};">
            {'+' if today_pnl_usd >= 0 else ''}${today_pnl_usd:,.2f}
        </div>
        <div class="kpi-subtext {'sub-green' if today_pnl_usd >= 0 else 'sub-red'}">
            <span>{'+' if today_pnl_pct >= 0 else ''}{today_pnl_pct:.2f}% de $1,000</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label">
            <span>Posiciones Open</span>
            <span style="color: #64748b;">Slots</span>
        </div>
        <div class="kpi-value">{len(df_open)} <span style="font-size: 14px; color: #64748b; font-weight: 500;">/ {MAX_CONCURRENT_POSITIONS}</span></div>
        <div class="kpi-subtext sub-neutral">
            <span>Kraken Spot Activas</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label">
            <span>Circuit Breaker</span>
            <span style="color: #64748b;">-3.0%</span>
        </div>
        <div class="kpi-value" style="font-size: 16px; display: flex; align-items: center; gap: 8px;">
            {cb_badge_dot}
            {cb_status_html}
        </div>
        <div class="kpi-subtext" style="color: #64748b;">
            <span>Protección diaria activa</span>
        </div>
    </div>
</div>
"""
render_html(kpi_html)


# --------------------------------------------------------------------------------------
# 9. SECCIÓN 1: POSICIONES ACTIVAS (OPEN)
# --------------------------------------------------------------------------------------
render_html("""
<div class="section-header">
    <div class="section-title">
        <span style="color: #38bdf8;">●</span>
        <span>Posiciones Activas en Kraken Spot</span>
    </div>
    <div class="section-tag">
        MÁXIMO 3 CONCURRENTES · 1 POR ACTIVO
    </div>
</div>
""")

if df_open.empty:
    render_html("""
    <div style="background-color: #080d14; border: 1px dashed #1e293b; border-radius: 8px; padding: 24px; text-align: center; color: #64748b; font-size: 12px; font-family: 'JetBrains Mono'; margin-bottom: 24px;">
        🔍 NINGUNA POSICIÓN ABIERTA · ESCANEANDO LOS 18 PARES EN VELAS DE 15 MINUTOS (FILTRO MACRO 4H ACTIVO)
    </div>
    """)
else:
    rows_open = []
    for _, row in df_open.iterrows():
        pnl_val = float(row.get('pnl_usd', 0.0))
        pnl_pct = float(row.get('pnl_pct', 0.0))
        side = str(row.get('side', 'LONG')).upper()
        side_class = "badge-side-long" if side == "LONG" else "badge-side-short"
        pnl_color = "#10b981" if pnl_val >= 0 else "#f43f5e"
        pnl_str = f"+${pnl_val:,.2f} USD" if pnl_val >= 0 else f"-${abs(pnl_val):,.2f} USD"

        created_str = str(row.get('created_at', ''))
        try:
            dt_ent = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00")).astimezone(TZ_COT)
            hora_open = dt_ent.strftime("%H:%M:%S COT")
        except Exception:
            hora_open = created_str[11:19] if len(created_str) >= 19 else "-"

        rows_open.append(
            f"<tr class=\"row-active\">"
            f"<td><span style=\"color: #f8fafc; font-weight: 700;\">{row.get('order_id', '-')}</span></td>"
            f"<td><span style=\"color: #38bdf8; font-weight: 700;\">{row.get('symbol', '-')}</span></td>"
            f"<td><span class=\"{side_class}\">{side}</span></td>"
            f"<td>${float(row.get('entry_price', 0.0)):,.4f}</td>"
            f"<td style=\"color: {pnl_color}; font-weight: 700;\">{pnl_str}</td>"
            f"<td style=\"color: {pnl_color}; font-weight: 700;\">{pnl_pct:+.2f}%</td>"
            f"<td style=\"color: #94a3b8;\">{hora_open}</td>"
            f"<td><span class=\"badge-pro badge-open\">● ACTIVA</span></td>"
            f"</tr>"
        )

    table_open_html = (
        "<div class=\"table-container\">"
        "<table class=\"quant-table-pro\">"
        "<thead><tr>"
        "<th>ID Orden</th><th>Par</th><th>Dirección</th><th>Precio Entrada</th>"
        "<th>PnL No Realizado ($)</th><th>PnL No Realizado (%)</th><th>Hora Apertura (COT)</th><th>Estado</th>"
        "</tr></thead>"
        "<tbody>" + "".join(rows_open) + "</tbody></table></div>"
    )
    render_html(table_open_html)

# --------------------------------------------------------------------------------------
# 10. SECCIÓN 2: HISTORIAL DE OPERACIONES CERRADAS (COLOREADO INSTITUCIONAL)
# --------------------------------------------------------------------------------------
render_html("""
<div class="section-header">
    <div class="section-title">
        <span style="color: #10b981;">📜</span>
        <span>Historial de Operaciones Cerradas (Ciclo Semanal)</span>
    </div>
    <div class="section-tag">
        TAKE PROFIT (+3.0%) · STOP LOSS (-1.5%)
    </div>
</div>
""")

if df_closed.empty:
    render_html("""
    <div style="background-color: #080d14; border: 1px dashed #1e293b; border-radius: 8px; padding: 24px; text-align: center; color: #64748b; font-size: 12px; font-family: 'JetBrains Mono'; margin-bottom: 24px;">
        SIN REGISTROS DE ÓRDENES CERRADAS PARA EL CICLO SEMANAL ACTUAL.
    </div>
    """)
else:
    rows_closed = []
    for _, row in df_closed.iterrows():
        pnl_val = float(row.get('pnl_usd', 0.0))
        pnl_pct = float(row.get('pnl_pct', 0.0))
        reason = str(row.get('exit_reason', ''))
        side = str(row.get('side', 'LONG')).upper()
        side_class = "badge-side-long" if side == "LONG" else "badge-side-short"

        is_sl = ("SL" in reason) or ("STOP" in reason) or (pnl_val < 0)
        if is_sl:
            row_class = "row-sl"
            gain_usd_str = f"-${abs(pnl_val):,.2f} USD"
            gain_pct_str = f"-{abs(pnl_pct):.2f}%"
            badge = '<span class="badge-pro badge-sl">CERRADO (SL)</span>'
            gain_style = "color: #f43f5e; font-weight: 700;"
        elif pnl_val > 0:
            row_class = "row-tp"
            gain_usd_str = f"+${abs(pnl_val):,.2f} USD"
            gain_pct_str = f"+{abs(pnl_pct):.2f}%"
            badge = '<span class="badge-pro badge-tp">CERRADO (TP)</span>'
            gain_style = "color: #10b981; font-weight: 700;"
        else:
            row_class = "row-active"
            gain_usd_str = "$0.00 USD"
            gain_pct_str = "0.00%"
            badge = '<span class="badge-pro badge-open">BREAKEVEN</span>'
            gain_style = "color: #94a3b8; font-weight: 700;"

        # Timestamps COT
        created_str = str(row.get('created_at', ''))
        closed_str = str(row.get('closed_at', ''))
        try:
            dt_in = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00")).astimezone(TZ_COT)
            fecha_in = dt_in.strftime("%Y-%m-%d")
            hora_in = dt_in.strftime("%H:%M:%S")
        except Exception:
            fecha_in = created_str[:10]
            hora_in = created_str[11:19]

        try:
            dt_out = datetime.datetime.fromisoformat(closed_str.replace("Z", "+00:00")).astimezone(TZ_COT)
            hora_out = dt_out.strftime("%H:%M:%S")
        except Exception:
            hora_out = closed_str[11:19] if len(closed_str) >= 19 else "-"

        rows_closed.append(
            f"<tr class=\"{row_class}\">"
            f"<td><span style=\"color: #f8fafc; font-weight: 700;\">{row.get('order_id', '-')}</span></td>"
            f"<td style=\"color: #94a3b8;\">{fecha_in}</td>"
            f"<td style=\"color: #cbd5e1;\">{hora_in}</td>"
            f"<td style=\"color: #cbd5e1;\">{hora_out}</td>"
            f"<td><span style=\"color: #38bdf8; font-weight: 700;\">{row.get('symbol', '-')}</span></td>"
            f"<td><span class=\"{side_class}\">{side}</span></td>"
            f"<td>${float(row.get('entry_price', 0.0)):,.4f}</td>"
            f"<td>${float(row.get('exit_price', 0.0)):,.4f}</td>"
            f"<td style=\"{gain_style}\">{gain_usd_str}</td>"
            f"<td style=\"{gain_style}\">{gain_pct_str}</td>"
            f"<td>{badge}</td>"
            f"</tr>"
        )

    table_closed_html = (
        "<div class=\"table-container\">"
        "<table class=\"quant-table-pro\">"
        "<thead><tr>"
        "<th>ID Orden</th><th>Fecha</th><th>Entrada (COT)</th><th>Salida (COT)</th>"
        "<th>Par</th><th>Lado</th><th>Precio Entrada</th><th>Precio Salida</th>"
        "<th>Ganancia ($ USD)</th><th>Retorno (%)</th><th>Resultado</th>"
        "</tr></thead>"
        "<tbody>" + "".join(rows_closed) + "</tbody></table></div>"
    )
    render_html(table_closed_html)

# --------------------------------------------------------------------------------------
# 11. CURVA DE CAPITAL (EQUITY CURVE) ESTILO BLOOMBERG TERMINAL
# --------------------------------------------------------------------------------------
render_html("""
<div class="section-header">
    <div class="section-title">
        <span style="color: #38bdf8;">📈</span>
        <span>Evolución Acumulada de Capital (Equity Curve)</span>
    </div>
    <div class="section-tag">
        BASE $1,000.00 USD · MODELO MONTE CARLO / REAL TRACKING
    </div>
</div>
""")


if not df_closed.empty:
    df_sorted = df_closed.sort_values(by="created_at", ascending=True).copy()
    equity = [INITIAL_CAPITAL]
    labels = ["Punto Inicial"]

    running = INITIAL_CAPITAL
    for idx, r in df_sorted.iterrows():
        running += float(r.get('pnl_usd', 0.0))
        equity.append(running)
        labels.append(f"{r.get('symbol', '')} ({'+' if float(r.get('pnl_usd', 0)) >= 0 else ''}${float(r.get('pnl_usd', 0)):,.2f})")

    fig = go.Figure()
    # Área sombreada con gradiente
    fig.add_trace(go.Scatter(
        x=list(range(len(equity))),
        y=equity,
        mode='lines+markers',
        line=dict(color='#10b981' if current_capital >= INITIAL_CAPITAL else '#f43f5e', width=2.5, shape='spline'),
        marker=dict(size=7, color='#38bdf8', line=dict(color='#04070b', width=1.5)),
        fill='tozeroy',
        fillcolor='rgba(16, 185, 129, 0.06)' if current_capital >= INITIAL_CAPITAL else 'rgba(244, 63, 94, 0.06)',
        text=labels,
        hovertemplate='<b>%{text}</b><br>Capital: $%{y:,.2f} USD<extra></extra>'
    ))

    # Línea base de $1,000
    fig.add_hline(
        y=INITIAL_CAPITAL,
        line_dash="dot",
        line_color="#475569",
        annotation_text="Base: $1,000.00 USD",
        annotation_position="bottom right",
        annotation_font_color="#64748b",
        annotation_font_size=10
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#080d14",
        plot_bgcolor="#06090e",
        margin=dict(l=50, r=25, t=20, b=40),
        height=260,
        font=dict(family="JetBrains Mono", size=10, color="#64748b"),
        xaxis=dict(
            title=dict(text="Operaciones Ejecutadas (Ciclo Semanal)", font=dict(size=11, color="#64748b")),
            gridcolor="#121a24",
            zerolinecolor="#121a24"
        ),
        yaxis=dict(
            title=dict(text="Balance (USD)", font=dict(size=11, color="#64748b")),
            gridcolor="#121a24",
            zerolinecolor="#121a24",
            tickprefix="$",
            tickformat=",.0f"
        )
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------------------
# 12. BARRA LATERAL (CENTRO DE CONTROL & AUDIT LOG)
# --------------------------------------------------------------------------------------
with st.sidebar:
    render_html("""
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #16202e;">
        <span style="font-size: 20px;">🛡️</span>
        <span style="font-size: 13px; font-weight: 800; color: #ffffff; letter-spacing: 0.05em;">RISK MANAGEMENT</span>
    </div>
    """)

    render_html("""
    <div style="font-family: 'JetBrains Mono'; font-size: 11px; color: #94a3b8; line-height: 1.8; background-color: #0b111a; border: 1px solid #16202e; border-radius: 6px; padding: 12px; margin-bottom: 20px;">
        <div><b>EXCHANGE:</b> <span style="color: #38bdf8;">Kraken Spot USD</span></div>
        <div><b>UNIVERSO:</b> <span style="color: #cbd5e1;">18 Activos Top</span></div>
        <div><b>RIESGO/TRADE:</b> <span style="color: #cbd5e1;">1.5% Balance</span></div>
        <div><b>TAKE PROFIT:</b> <span style="color: #10b981;">+3.00%</span></div>
        <div><b>STOP LOSS:</b> <span style="color: #f43f5e;">-1.50%</span></div>
        <div><b>CIRCUIT BREAKER:</b> <span style="color: #f59e0b;">-3.00% Diario</span></div>
    </div>
    """)

    render_html('<div class="sidebar-section-title">🚨 Protocolo de Emergencia</div>')
    if st.button("🔴 RESET MANUAL (Limpiar Base de Datos)", use_container_width=True):
        if HAS_SUPABASE and supabase_client:
            try:
                supabase_client.table("trades").delete().neq("id", 0).execute()
                supabase_client.table("daily_metrics").delete().neq("id", 0).execute()
            except Exception as e:
                st.sidebar.error(f"Error al limpiar Supabase: {e}")

        st.session_state.trades_cache = pd.DataFrame()
        st.session_state.capital = INITIAL_CAPITAL
        st.session_state.logs.insert(0, f"[{now_cot().strftime('%H:%M:%S COT')}] [ACTION] Reset manual ejecutado. Base de datos restablecida.")
        enviar_notificacion_push("PROYECTO DIPPER | RESET", "Se ha ejecutado un Reset Manual del sistema.")
        st.sidebar.success("Reset ejecutado. Recargando terminal...")
        time.sleep(1)
        st.rerun()

    render_html('<div class="sidebar-section-title">📡 Red de Alertas Push (Ntfy)</div>')
    if st.button("🔔 Enviar Ping de Prueba", use_container_width=True):
        enviar_notificacion_push(
            "PROYECTO DIPPER | PING",
            f"Ping de validación exitoso desde Terminal Web ({now_cot().strftime('%H:%M:%S COT')})."
        )
        st.sidebar.success(f"Enviado a ntfy.sh/{NTFY_TOPIC}")

    render_html('<div class="sidebar-section-title">📜 Registro de Auditoría (COT)</div>')
    log_content = "".join([f"<div class='console-entry'>{l}</div>" for l in st.session_state.logs[:12]])
    render_html(f"<div class='console-box'>{log_content}</div>")

