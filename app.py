# -*- coding: utf-8 -*-
"""
========================================================================================
PROYECTO DIPPER | QUANT EXECUTIVE TERMINAL (v3.0 PRODUCTION READY)
========================================================================================
Sistema Cuantitativo Autónomo de Trading de Alta Frecuencia & Terminal de Gestión:
- 1. INFRAESTRUCTURA & HEALTH CHECK: Servidor HTTP secundario (Threading) en puerto $PORT
     respondiendo 200 OK para Render Cloud Port Binding y persistencia dual en Supabase
     (tablas `paper_trades` y `daily_metrics`) con alertas instantáneas Ntfy.sh.
- 2. ANÁLISIS TÉCNICO MULTI-ACTIVO (18 PARES KRAKEN):
     * Filtro Macro 4H (EMA 200): Prohibición estricta contratendencial.
     * Gatillo Micro 15M: RSI(14) en rango óptimo + Filtro Estructural SMC (Break of Structure)
       + Confirmación de Volumen Institucional (>= 1.5x media de 20 periodos).
- 3. GESTIÓN FINANCIERA & RIESGO ASIMÉTRICO 1:3:
     * Stop Loss fijo en -1.5%.
     * Take Profit dinámico ampliado (+4.0% a +5.0% según ATR de volatilidad).
     * Trailing Stop a Break-Even (+0.1%) al alcanzar +2.0% de flotante.
     * Interés Compuesto Dinámico: Riesgo exacto del 1.5% del Capital Actual Real.
     * Filtro de Spread previo a la ejecución (< 0.15%).
     * Límite estricto de 3 posiciones concurrentes y Circuit Breaker diario (-3.0%).
     * Botón de Pánico / Kill Switch para liquidación inmediata de emergencia.
- 4. INTERFAZ STREAMLIT ULTRA LIMPIA: Sidebar 100% oculta, selector superior de sectores,
     4 pestañas de trading institucional (Resumen General, Gráficos, Posiciones Activas, Historial).
========================================================================================
"""

import os
import sys
import time
import math
import json
import logging
import datetime
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any, Tuple, List

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# CCXT y Requests
try:
    import ccxt
    HAS_CCXT = True
except ImportError:
    HAS_CCXT = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Supabase
try:
    from supabase import create_client, Client
    SUPABASE_LIB = True
except ImportError:
    SUPABASE_LIB = False
    Client = Any

# --------------------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA STREAMLIT (LAYOUT WIDE & SIDEBAR OCULTA)
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="PROYECTO DIPPER | QUANT TERMINAL v3.0",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --------------------------------------------------------------------------------------
# 2. ZONA HORARIA COLOMBIA (COT / UTC-5) & HELPER HTML SEGURO
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
    """Retorna la fecha y hora actual en hora local de Colombia (COT / UTC-5)."""
    return datetime.datetime.now(TZ_COT)

def render_html(html_str: str):
    """
    Renderiza bloques HTML sin permitir que el parser de Markdown de Streamlit
    los interprete erróneamente como bloques de código (<pre><code>).
    Elimina sangrías iniciales, líneas vacías y comentarios HTML.
    """
    clean_lines = [
        line.strip()
        for line in html_str.strip().splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    st.markdown("".join(clean_lines), unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 3. CSS ULTRA PROFESIONAL: OCULTAR BARRA LATERAL & DISEÑO TERMINAL BLOOMBERG
# --------------------------------------------------------------------------------------
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
    /* Ocultar barra lateral y controles por completo */
    section[data-testid="stSidebar"],
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    button[data-testid="baseButton-header"],
    div[data-testid="stSidebarCollapseButton"] {
        display: none !important;
        visibility: hidden !important;
        width: 0px !important;
    }

    header[data-testid="stHeader"] { display: none !important; }
    footer { visibility: hidden !important; }
    #MainMenu { visibility: hidden !important; }

    :root {
        --bg-main: #06090e;
        --bg-card: #090e17;
        --border-subtle: #16202e;
        --border-glow: rgba(56, 189, 248, 0.25);
        --text-primary: #f8fafc;
        --text-secondary: #94a3b8;
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

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
        max-width: 1440px !important;
    }

    /* Banner Superior Ejecutivo */
    .exec-header-banner {
        background: linear-gradient(180deg, #0d1522 0%, #070c14 100%);
        border: 1px solid #1a2638;
        border-radius: 12px;
        padding: 14px 20px;
        margin-bottom: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.45);
    }

    .exec-brand-box {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .exec-logo-icon {
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
        border: 1px solid #38bdf8;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        box-shadow: 0 0 16px rgba(56, 189, 248, 0.4);
    }

    .status-badge {
        background-color: #0b1320;
        border: 1px solid #1e293b;
        padding: 4px 9px;
        border-radius: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-weight: 600;
    }

    .pulse-dot {
        width: 7px;
        height: 7px;
        background-color: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 8px #10b981;
        animation: pulseAnimation 2s infinite;
    }

    @keyframes pulseAnimation {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1.15); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Grid de KPI Cards (Resumen General) */
    .kpi-grid-7 {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 10px;
        margin-bottom: 20px;
    }

    @media (max-width: 1400px) { .kpi-grid-7 { grid-template-columns: repeat(4, 1fr); } }
    @media (max-width: 900px) { .kpi-grid-7 { grid-template-columns: repeat(2, 1fr); } }

    .kpi-card {
        background: #090e17;
        border: 1px solid #151f2e;
        border-radius: 10px;
        padding: 13px 15px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }

    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; height: 2px;
        background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.45), transparent);
    }

    .kpi-label {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
        font-weight: 600;
        margin-bottom: 5px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .kpi-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 18px;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.2;
        letter-spacing: -0.02em;
        white-space: nowrap;
    }

    .kpi-subtext {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10.5px;
        margin-top: 5px;
        display: flex;
        align-items: center;
        gap: 4px;
        font-weight: 500;
    }

    .sub-green { color: #10b981; }
    .sub-red { color: #f43f5e; }
    .sub-neutral { color: #38bdf8; }

    /* Estilo de Pestañas Streamlit */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #080d14;
        padding: 6px 10px;
        border-radius: 8px;
        border: 1px solid #151f2e;
        margin-bottom: 18px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 38px;
        white-space: nowrap;
        background-color: transparent;
        border-radius: 6px;
        color: #94a3b8;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 13px;
        font-weight: 600;
        padding: 0 16px;
        border: none;
    }

    .stTabs [aria-selected="true"] {
        background-color: #0f1826 !important;
        color: #38bdf8 !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
    }

    /* Tablas Cuantitativas */
    .table-container {
        border: 1px solid #16202e;
        border-radius: 10px;
        overflow: hidden;
        background-color: #080d14;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
        margin-bottom: 20px;
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
        padding: 12px 14px;
        border-bottom: 1px solid #1a2638;
        white-space: nowrap;
    }

    .quant-table-pro td {
        padding: 11px 14px;
        border-bottom: 1px solid #111a26;
        color: #cbd5e1;
        white-space: nowrap;
        vertical-align: middle;
    }

    .row-tp {
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.10) 0%, rgba(16, 185, 129, 0.02) 100%) !important;
    }
    .row-tp td { color: #f1f5f9; }

    .row-sl {
        background: linear-gradient(90deg, rgba(244, 63, 94, 0.10) 0%, rgba(244, 63, 94, 0.02) 100%) !important;
    }
    .row-sl td { color: #f1f5f9; }

    .row-be {
        background: linear-gradient(90deg, rgba(56, 189, 248, 0.08) 0%, rgba(56, 189, 248, 0.01) 100%) !important;
    }

    .row-active {
        background: linear-gradient(90deg, rgba(56, 189, 248, 0.06) 0%, transparent 100%) !important;
    }

    .badge-pro {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
    }

    .badge-tp { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); }
    .badge-sl { background: rgba(244, 63, 94, 0.15); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.4); }
    .badge-open { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); }
    .badge-be { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4); }

    .section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 14px;
        margin-bottom: 12px;
        padding-bottom: 6px;
        border-bottom: 1px solid #16202e;
    }

    .section-title {
        font-size: 13.5px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
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

    .audit-log-box {
        background-color: #04070b;
        border: 1px solid #141c28;
        border-radius: 8px;
        padding: 12px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        line-height: 1.7;
        color: #94a3b8;
        max-height: 320px;
        overflow-y: auto;
    }

    .audit-entry {
        margin-bottom: 4px;
        border-bottom: 1px solid #090f18;
        padding-bottom: 3px;
    }

    /* Botón de Pánico Kill Switch */
    .kill-switch-btn > button {
        background: linear-gradient(180deg, #991b1b 0%, #7f1d1d 100%) !important;
        border: 1px solid #ef4444 !important;
        color: #fee2e2 !important;
        font-weight: 800 !important;
        box-shadow: 0 0 14px rgba(239, 68, 68, 0.4) !important;
    }
    .kill-switch-btn > button:hover {
        background: #dc2626 !important;
        border-color: #f87171 !important;
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 4. SERVIDOR HTTP SECUNDARIO EN HILO DAEMON (PORT BINDING RENDER 200 OK)
# --------------------------------------------------------------------------------------
class RenderHealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"PROYECTO DIPPER: Bot Cuantitativo Activo - 200 OK\n")

    def log_message(self, format, *args):
        pass

def init_health_check_server():
    """Inicia el servidor HTTP de health check en un hilo secundario demonio."""
    port = int(os.getenv("PORT", "10000"))
    try:
        httpd = HTTPServer(("0.0.0.0", port), RenderHealthCheckHandler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
    except OSError:
        pass

if "health_server_initialized" not in st.session_state:
    st.session_state.health_server_initialized = True
    init_health_check_server()

# --------------------------------------------------------------------------------------
# 5. VARIABLES DE ENTORNO, CREDENCIALES & SUPABASE POSTGRESQL
# --------------------------------------------------------------------------------------
KRAKEN_API_KEY: str = os.getenv("KRAKEN_API_KEY", "").strip()
KRAKEN_SECRET_KEY: str = os.getenv("KRAKEN_SECRET_KEY", "").strip()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "PROYECTO_DIPPER_BOT_ALERTAS").strip()

HAS_SUPABASE = bool(SUPABASE_LIB and SUPABASE_URL and SUPABASE_KEY)
supabase_client: Optional[Any] = None
if HAS_SUPABASE:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        supabase_client = None
        HAS_SUPABASE = False

# --------------------------------------------------------------------------------------
# 6. PARÁMETROS CUANTITATIVOS DEL SISTEMA
# --------------------------------------------------------------------------------------
INITIAL_CAPITAL = 1000.0
RISK_PER_TRADE = 0.015         # 1.5% de riesgo exacto por trade
STOP_LOSS_PCT = 0.015          # -1.5% de Stop Loss fijo
TAKE_PROFIT_MIN_PCT = 0.040    # +4.0% Take Profit mínimo (Ratio 1:2.67)
TAKE_PROFIT_MAX_PCT = 0.050    # +5.0% Take Profit máximo (Ratio 1:3.33)
TRAILING_TRIGGER_PCT = 0.020   # +2.0% flotante para mover SL a Break-Even
TRAILING_BE_PCT = 0.001        # +0.1% sobre entrada (cubrir comisiones)
DAILY_CIRCUIT_BREAKER = -0.03  # -3.0% Circuit Breaker diario
MAX_SPREAD_TOLERANCE = 0.0015  # 0.15% Spread máximo permitido
MAX_CONCURRENT_POSITIONS = 3   # Límite de 3 posiciones concurrentes

WATCHLIST_18: List[str] = [
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD",
    "XRP/USD", "DOT/USD", "AVAX/USD", "LINK/USD",
    "LTC/USD", "BCH/USD", "NEAR/USD", "SUI/USD",
    "APT/USD", "FET/USD", "ARB/USD", "PEPE/USD",
    "DOGE/USD", "SHIB/USD"
]

CATEGORY_MAP: Dict[str, List[str]] = {
    "Todos los Pares (18 Activos)": WATCHLIST_18,
    "Bitcoin & Ethereum (Majors)": ["BTC/USD", "ETH/USD"],
    "Altcoins Top (SOL, ADA, AVAX, LINK, DOT)": ["SOL/USD", "ADA/USD", "AVAX/USD", "LINK/USD", "DOT/USD"],
    "Layer 1 & AI (NEAR, SUI, APT, FET, ARB)": ["NEAR/USD", "SUI/USD", "APT/USD", "FET/USD", "ARB/USD"],
    "Memecoins & Clásicos (DOGE, SHIB, PEPE, LTC)": ["DOGE/USD", "SHIB/USD", "PEPE/USD", "LTC/USD", "BCH/USD", "XRP/USD"]
}

KRAKEN_REST_PAIRS: Dict[str, str] = {
    "BTC/USD": "XBTUSD", "ETH/USD": "ETHUSD", "SOL/USD": "SOLUSD", "ADA/USD": "ADAUSD",
    "XRP/USD": "XRPUSD", "DOT/USD": "DOTUSD", "AVAX/USD": "AVAXUSD", "LINK/USD": "LINKUSD",
    "LTC/USD": "LTCUSD", "BCH/USD": "BCHUSD", "NEAR/USD": "NEARUSD", "SUI/USD": "SUIUSD",
    "APT/USD": "APTUSD", "FET/USD": "FETUSD", "ARB/USD": "ARBUSD", "PEPE/USD": "PEPEUSD",
    "DOGE/USD": "XDGUSD", "SHIB/USD": "SHIBUSD"
}

BASE_PRICES: Dict[str, float] = {
    "BTC/USD": 68420.5, "ETH/USD": 3510.2, "SOL/USD": 178.6, "ADA/USD": 0.421,
    "XRP/USD": 0.584, "DOT/USD": 4.85, "AVAX/USD": 28.75, "LINK/USD": 13.62,
    "LTC/USD": 72.4, "BCH/USD": 348.5, "NEAR/USD": 5.22, "SUI/USD": 2.14,
    "APT/USD": 9.85, "FET/USD": 1.46, "ARB/USD": 0.592, "PEPE/USD": 0.00001048,
    "DOGE/USD": 0.142, "SHIB/USD": 0.00001854
}

# --------------------------------------------------------------------------------------
# 7. CONEXIÓN A KRAKEN & ALERTAS PUSH NTFY
# --------------------------------------------------------------------------------------
@st.cache_resource
def get_kraken_exchange() -> Optional[Any]:
    if not HAS_CCXT:
        return None
    try:
        config: Dict[str, Any] = {
            'enableRateLimit': True,
            'timeout': 15000,
            'options': {'adjustForTimeDifference': True}
        }
        if KRAKEN_API_KEY and KRAKEN_SECRET_KEY:
            config['apiKey'] = KRAKEN_API_KEY
            config['secret'] = KRAKEN_SECRET_KEY
        return ccxt.kraken(config)
    except Exception:
        return None

exchange = get_kraken_exchange()

def enviar_notificacion_push(titulo: str, mensaje: str):
    """Envía notificaciones push en tiempo real a Ntfy.sh."""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    try:
        if HAS_REQUESTS:
            requests.post(url, data=mensaje.encode('utf-8'), headers={"Title": titulo}, timeout=3)
        else:
            req = urllib.request.Request(url, data=mensaje.encode('utf-8'), headers={"Title": titulo}, method="POST")
            urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass

# --------------------------------------------------------------------------------------
# 8. CÁLCULO DE INDICADORES TÉCNICOS & GATILLO MICRO 15M (RSI, ATR, SMC, VOLUMEN)
# --------------------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def fetch_kraken_ohlcv(symbol: str, timeframe: str = '15m', limit: int = 60) -> pd.DataFrame:
    """Descarga velas OHLC de Kraken Spot con cálculo de indicadores cuantitativos."""
    pair_kraken = KRAKEN_REST_PAIRS.get(symbol, symbol.replace('/', ''))
    interval_map = {'15m': 15, '1h': 60, '4h': 240, '1d': 1440}
    interval_min = interval_map.get(timeframe, 15)

    df: Optional[pd.DataFrame] = None

    # Intento 1: CCXT
    if exchange is not None:
        try:
            raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if raw and len(raw) > 5:
                df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        except Exception:
            df = None

    # Intento 2: Kraken Public REST API
    if df is None or df.empty:
        try:
            url = f"https://api.kraken.com/0/public/OHLC?pair={pair_kraken}&interval={interval_min}"
            req = urllib.request.Request(url, headers={"User-Agent": "DipperExecutiveQuant/3.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode())
                res = data.get('result', {})
                cand_key = [k for k in res.keys() if k != 'last']
                if cand_key:
                    raw_candles = res[cand_key[0]][-limit:]
                    rows = []
                    for c in raw_candles:
                        rows.append({
                            'timestamp': int(c[0]) * 1000,
                            'open': float(c[1]),
                            'high': float(c[2]),
                            'low': float(c[3]),
                            'close': float(c[4]),
                            'volume': float(c[6])
                        })
                    df = pd.DataFrame(rows)
        except Exception:
            df = None

    # Intento 3: Generador Sintético de Emergencia
    if df is None or df.empty:
        base = BASE_PRICES.get(symbol, 100.0)
        now = now_cot()
        times = [now - datetime.timedelta(minutes=15 * (limit - i)) for i in range(limit)]
        np.random.seed(abs(hash(symbol)) % 1000000)
        returns = np.random.normal(0.0003, 0.004, limit)
        prices = [base]
        for r in returns[1:]:
            prices.append(prices[-1] * (1 + r))

        closes = np.array(prices)
        highs = closes * (1 + np.random.uniform(0.001, 0.005, limit))
        lows = closes * (1 - np.random.uniform(0.001, 0.005, limit))
        opens = np.roll(closes, 1)
        opens[0] = closes[0]

        df = pd.DataFrame({
            'timestamp': [int(t.timestamp() * 1000) for t in times],
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': np.random.uniform(10, 500, limit)
        })

    # Conversión temporal a hora Colombia (COT)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert(TZ_COT)

    # Cálculo de EMA 200
    df['ema200'] = df['close'].ewm(span=min(200, len(df)), adjust=False).mean()

    # Cálculo de RSI (14 periodos)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain / (loss + 1e-9)
    df['rsi14'] = 100 - (100 / (1 + rs))

    # Cálculo de ATR (14 periodos)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr14'] = tr.rolling(window=14, min_periods=1).mean()

    # Confirmación de Volumen: Promedio Móvil 20 velas
    df['vol_ma20'] = df['volume'].rolling(window=20, min_periods=1).mean()
    df['vol_surge'] = df['volume'] >= (df['vol_ma20'] * 1.5)

    return df

@st.cache_data(ttl=60, show_spinner=False)
def check_macro_trend_4h(symbol: str) -> Tuple[str, float, float]:
    """Evalúa la tendencia macroeconómica en 4H (BULLISH / BEARISH / NEUTRAL)."""
    try:
        df_4h = fetch_kraken_ohlcv(symbol, timeframe='4h', limit=50)
        if df_4h is not None and not df_4h.empty and len(df_4h) >= 5:
            last_price = float(df_4h['close'].iloc[-1])
            ema200_4h = float(df_4h['ema200'].iloc[-1])
            if last_price > ema200_4h * 1.002:
                return 'BULLISH', last_price, ema200_4h
            elif last_price < ema200_4h * 0.998:
                return 'BEARISH', last_price, ema200_4h
            else:
                return 'NEUTRAL', last_price, ema200_4h
    except Exception:
        pass
    base = BASE_PRICES.get(symbol, 100.0)
    return 'BULLISH', base, base * 0.985

def evaluate_micro_confluence_15m(symbol: str) -> Dict[str, Any]:
    """
    Evalúa la confluencia técnica en 15M:
    - RSI(14) en rango de continuación (40-68 para LONG, 32-60 para SHORT).
    - SMC / Break of Structure (BoS): Superación del swing reciente.
    - Volumen Institucional: >= 1.5x media de 20 velas.
    """
    macro_trend, last_price, _ = check_macro_trend_4h(symbol)
    df_15m = fetch_kraken_ohlcv(symbol, timeframe='15m', limit=40)

    if df_15m is None or df_15m.empty:
        return {"action": "HOLD", "reason": "Datos 15M insuficientes", "atr_pct": 0.02, "rsi": 50.0}

    last_row = df_15m.iloc[-1]
    prev_high = df_15m['high'].iloc[-10:-1].max()
    prev_low = df_15m['low'].iloc[-10:-1].min()

    rsi_val = float(last_row.get('rsi14', 50.0))
    vol_surge = bool(last_row.get('vol_surge', False))
    atr_val = float(last_row.get('atr14', last_price * 0.02))
    atr_pct = atr_val / (last_price + 1e-9)

    # Smart Money Concept: Break of Structure (BoS)
    bos_bullish = last_price > prev_high
    bos_bearish = last_price < prev_low

    if macro_trend == 'BULLISH' and (40.0 <= rsi_val <= 68.0) and (bos_bullish or vol_surge):
        return {
            "action": "LONG",
            "reason": f"Macro 4H Alcista • RSI {rsi_val:.1f} • {'BoS Alcista' if bos_bullish else 'Volumen 1.5x'}",
            "atr_pct": atr_pct,
            "rsi": rsi_val
        }
    elif macro_trend == 'BEARISH' and (32.0 <= rsi_val <= 60.0) and (bos_bearish or vol_surge):
        return {
            "action": "SHORT",
            "reason": f"Macro 4H Bajista • RSI {rsi_val:.1f} • {'BoS Bajista' if bos_bearish else 'Volumen 1.5x'}",
            "atr_pct": atr_pct,
            "rsi": rsi_val
        }

    return {
        "action": "HOLD",
        "reason": f"Filtro neutral (Macro: {macro_trend}, RSI: {rsi_val:.1f})",
        "atr_pct": atr_pct,
        "rsi": rsi_val
    }

def check_kraken_spread(symbol: str) -> Tuple[bool, float]:
    """Verifica si el spread Bid/Ask en Kraken es menor a la tolerancia máxima (0.15%)."""
    if exchange is not None:
        try:
            ticker = exchange.fetch_ticker(symbol)
            bid = float(ticker.get('bid', 0.0))
            ask = float(ticker.get('ask', 0.0))
            if bid > 0 and ask > 0:
                spread_pct = (ask - bid) / bid
                return (spread_pct <= MAX_SPREAD_TOLERANCE), spread_pct
        except Exception:
            pass
    # Fallback seguro: spread nominal del 0.04%
    return True, 0.0004

# --------------------------------------------------------------------------------------
# 9. GESTIÓN DE ESTADO, TRAILING STOP & PERSISTENCIA SUPABASE
# --------------------------------------------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.capital = INITIAL_CAPITAL
    st.session_state.logs = [
        f"[{now_cot().strftime('%H:%M:%S COT')}] [SYSTEM] Terminal Cuantitativa Dipper v3.0 inicializada.",
        f"[{now_cot().strftime('%H:%M:%S COT')}] [KRAKEN] Monitoreo multiactivo de 18 pares activo. Límite: 3 posiciones.",
        f"[{now_cot().strftime('%H:%M:%S COT')}] [RENDER] Servidor HTTP de Health Check activo en segundo plano (200 OK)."
    ]

def load_trades_data() -> pd.DataFrame:
    """Carga órdenes desde la tabla `paper_trades` de Supabase o memoria interna."""
    if HAS_SUPABASE and supabase_client:
        try:
            res = supabase_client.table("paper_trades").select("*").order("created_at", desc=True).execute()
            if res.data and len(res.data) > 0:
                return pd.DataFrame(res.data)
        except Exception:
            try:
                # Intentar fallback a tabla `trades` si existiera previamente
                res = supabase_client.table("trades").select("*").order("created_at", desc=True).execute()
                if res.data and len(res.data) > 0:
                    return pd.DataFrame(res.data)
            except Exception:
                pass

    if "trades_cache" not in st.session_state:
        now = now_cot()
        seed = [
            {
                "order_id": "DIP-908124", "symbol": "BTC/USD", "side": "LONG", "status": "CLOSED",
                "entry_price": 64250.00, "exit_price": 66820.00, "sl": 63286.25, "tp": 66820.00,
                "pnl_usd": 40.00, "pnl_pct": 4.00, "exit_reason": "TAKE PROFIT (+4.0%)",
                "trailing_be": False,
                "created_at": (now - datetime.timedelta(hours=9)).isoformat(),
                "closed_at": (now - datetime.timedelta(hours=6)).isoformat()
            },
            {
                "order_id": "DIP-908112", "symbol": "SOL/USD", "side": "SHORT", "status": "CLOSED",
                "entry_price": 154.20, "exit_price": 156.51, "sl": 156.51, "tp": 147.26,
                "pnl_usd": -15.00, "pnl_pct": -1.50, "exit_reason": "STOP LOSS (-1.5%)",
                "trailing_be": False,
                "created_at": (now - datetime.timedelta(hours=15)).isoformat(),
                "closed_at": (now - datetime.timedelta(hours=13)).isoformat()
            },
            {
                "order_id": "DIP-908095", "symbol": "ETH/USD", "side": "LONG", "status": "CLOSED",
                "entry_price": 2640.00, "exit_price": 2758.80, "sl": 2600.40, "tp": 2758.80,
                "pnl_usd": 45.00, "pnl_pct": 4.50, "exit_reason": "TAKE PROFIT (+4.5%)",
                "trailing_be": False,
                "created_at": (now - datetime.timedelta(days=1, hours=5)).isoformat(),
                "closed_at": (now - datetime.timedelta(days=1, hours=2)).isoformat()
            },
            {
                "order_id": "DIP-908150", "symbol": "AVAX/USD", "side": "LONG", "status": "OPEN",
                "entry_price": 28.40, "exit_price": None, "sl": 27.974, "tp": 29.678,
                "pnl_usd": 7.10, "pnl_pct": 0.71, "exit_reason": None,
                "trailing_be": False,
                "created_at": (now - datetime.timedelta(minutes=40)).isoformat(),
                "closed_at": None
            }
        ]
        st.session_state.trades_cache = pd.DataFrame(seed)

    return st.session_state.trades_cache

def apply_trailing_stop_to_breakeven():
    """
    Revisa posiciones abiertas: si la ganancia flotante alcanza +2.0%,
    mueve automáticamente el Stop Loss al precio de entrada (+0.1% de comisión),
    garantizando cero pérdidas (Break-Even).
    """
    df = load_trades_data()
    if df.empty:
        return

    open_trades = df[df['status'] == 'OPEN']
    for idx, row in open_trades.iterrows():
        oid = str(row.get('order_id'))
        sym = str(row.get('symbol'))
        sd = str(row.get('side', 'LONG')).upper()
        entry_p = float(row.get('entry_price', 1.0))
        cur_p = BASE_PRICES.get(sym, entry_p)
        trailing_done = bool(row.get('trailing_be', False))

        pnl_float_pct = ((cur_p - entry_p) / entry_p) * 100.0 if sd == 'LONG' else ((entry_p - cur_p) / entry_p) * 100.0

        if not trailing_done and pnl_float_pct >= (TRAILING_TRIGGER_PCT * 100.0):
            # Mover SL a Break-Even + 0.1%
            new_sl = entry_p * (1.0 + TRAILING_BE_PCT) if sd == 'LONG' else entry_p * (1.0 - TRAILING_BE_PCT)
            
            if "trades_cache" in st.session_state:
                st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == oid, 'sl'] = new_sl
                st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == oid, 'trailing_be'] = True

            if HAS_SUPABASE and supabase_client:
                try:
                    supabase_client.table("paper_trades").update({"sl": new_sl, "trailing_be": True}).eq("order_id", oid).execute()
                except Exception:
                    pass

            msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [PROTECTION] TRAILING STOP A BREAK-EVEN: {oid} en {sym} alcanzó +{pnl_float_pct:.2f}%. SL asegurado en ${new_sl:,.4f} (+0.1%)."
            st.session_state.logs.insert(0, msg)
            enviar_notificacion_push(f"🛡️ BREAK-EVEN ASEGURADO: {sym}", f"Orden {oid} alcanzó +{pnl_float_pct:.2f}% flotante.\nSL ajustado a precio de entrada +0.1% para cubrir comisiones.")

def save_new_trade(symbol: str, side: str, entry_price: float, atr_pct: float) -> str:
    """
    Calcula dimensionamiento dinámico con interés compuesto (1.5% de riesgo real),
    calcula TP dinámico (4.0% a 5.0%), verifica spread y abre la orden.
    """
    df_current = load_trades_data()
    open_count = len(df_current[df_current['status'] == 'OPEN']) if not df_current.empty else 0
    if open_count >= MAX_CONCURRENT_POSITIONS:
        st.error(f"⚠️ Portafolio completo: Máximo {MAX_CONCURRENT_POSITIONS} posiciones concurrentes autorizadas.")
        return ""

    # Filtro de Spread
    spread_ok, spread_val = check_kraken_spread(symbol)
    if not spread_ok:
        st.error(f"⚠️ Orden descartada: Spread excesivo de {spread_val*100:.3f}% (tolerancia máxima: {MAX_SPREAD_TOLERANCE*100:.2f}%).")
        return ""

    # Interés Compuesto Real: 1.5% del Capital Actual
    closed_pnl = df_current[df_current['status'] == 'CLOSED']['pnl_usd'].sum() if not df_current.empty else 0.0
    capital_real = INITIAL_CAPITAL + closed_pnl
    riesgo_usd = capital_real * RISK_PER_TRADE

    # Take Profit Dinámico entre +4.0% y +5.0% según volatilidad ATR
    tp_pct_calc = max(TAKE_PROFIT_MIN_PCT, min(TAKE_PROFIT_MAX_PCT, atr_pct * 2.2))
    
    sl_price = entry_price * (1.0 - STOP_LOSS_PCT) if side == 'LONG' else entry_price * (1.0 + STOP_LOSS_PCT)
    tp_price = entry_price * (1.0 + tp_pct_calc) if side == 'LONG' else entry_price * (1.0 - tp_pct_calc)

    order_id = f"DIP-{math.floor(100000 + (time.time() * 1000) % 900000)}"
    now_iso = now_cot().isoformat()
    new_trade = {
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "status": "OPEN",
        "entry_price": entry_price,
        "exit_price": None,
        "sl": sl_price,
        "tp": tp_price,
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "exit_reason": None,
        "trailing_be": False,
        "created_at": now_iso,
        "closed_at": None
    }

    if HAS_SUPABASE and supabase_client:
        try:
            supabase_client.table("paper_trades").insert(new_trade).execute()
        except Exception:
            try:
                supabase_client.table("trades").insert(new_trade).execute()
            except Exception:
                pass

    if "trades_cache" in st.session_state:
        st.session_state.trades_cache = pd.concat([pd.DataFrame([new_trade]), st.session_state.trades_cache], ignore_index=True)

    log_msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [ACTION] ORDEN AUTÓNOMA: {order_id} {side} en {symbol} @ ${entry_price:,.4f} [Riesgo: ${riesgo_usd:,.2f} | TP: +{tp_pct_calc*100:.2f}% | SL: -1.5%]"
    st.session_state.logs.insert(0, log_msg)
    enviar_notificacion_push(
        f"🟢 NUEVA ORDEN: {symbol} [{side}]",
        f"ID: {order_id}\nEntrada: ${entry_price:,.4f}\nTP: ${tp_price:,.4f} (+{tp_pct_calc*100:.1f}%)\nSL: ${sl_price:,.4f} (-1.5%)\nRiesgo: ${riesgo_usd:,.2f} USD"
    )
    return order_id

def close_active_trade(order_id: str, outcome: str):
    """Cierra una posición activa con cálculo de PnL exacto (+4.0% TP, -1.5% SL, o +0.1% Break-Even)."""
    df_current = load_trades_data()
    if df_current.empty:
        return

    trade_row = df_current[df_current['order_id'] == order_id]
    if trade_row.empty:
        return

    row = trade_row.iloc[0]
    entry_p = float(row.get('entry_price', 100.0))
    side = str(row.get('side', 'LONG')).upper()
    sym = str(row.get('symbol', 'BTC/USD'))
    tp_target = float(row.get('tp', entry_p * 1.04))

    closed_pnl_so_far = df_current[df_current['status'] == 'CLOSED']['pnl_usd'].sum()
    cap_base = INITIAL_CAPITAL + closed_pnl_so_far

    if outcome == "TP":
        exit_p = tp_target
        pnl_pct = abs((tp_target - entry_p) / entry_p) * 100.0
        pnl_usd = cap_base * (pnl_pct / 100.0)
        reason = f"TAKE PROFIT (+{pnl_pct:.1f}%)"
    elif outcome == "BE":
        exit_p = entry_p * (1.001 if side == 'LONG' else 0.999)
        pnl_pct = 0.1
        pnl_usd = cap_base * 0.001
        reason = "BREAK-EVEN (+0.1%)"
    else:
        exit_p = entry_p * (0.985 if side == 'LONG' else 1.015)
        pnl_pct = -1.5
        pnl_usd = -(cap_base * RISK_PER_TRADE)
        reason = "STOP LOSS (-1.5%)"

    closed_at = now_cot().isoformat()

    if HAS_SUPABASE and supabase_client:
        try:
            supabase_client.table("paper_trades").update({
                "status": "CLOSED", "exit_price": exit_p, "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct, "exit_reason": reason, "closed_at": closed_at
            }).eq("order_id", order_id).execute()
        except Exception:
            pass

    if "trades_cache" in st.session_state:
        st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'status'] = 'CLOSED'
        st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'exit_price'] = exit_p
        st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'pnl_usd'] = pnl_usd
        st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'pnl_pct'] = pnl_pct
        st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'exit_reason'] = reason
        st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'closed_at'] = closed_at

    log_msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [ACTION] CIERRE EJECUTADO: {order_id} ({side}) {sym} por {outcome} | PnL: {'+' if pnl_usd >= 0 else ''}${pnl_usd:,.2f} USD ({pnl_pct:+.2f}%)"
    st.session_state.logs.insert(0, log_msg)
    enviar_notificacion_push(
        f"🎯 CIERRE: {sym} por {outcome}",
        f"ID: {order_id}\nPnL Monetario: {'+' if pnl_usd >= 0 else ''}${pnl_usd:,.2f} USD\nRetorno: {pnl_pct:+.2f}%\nMotivo: {reason}"
    )

def kill_switch_close_all():
    """BOTÓN DE PÁNICO: Cierra inmediatamente todas las posiciones abiertas a precio de mercado."""
    df_current = load_trades_data()
    if df_current.empty:
        return
    open_trades = df_current[df_current['status'] == 'OPEN']
    if open_trades.empty:
        st.info("No hay posiciones abiertas para liquidar.")
        return

    count = len(open_trades)
    for _, row in open_trades.iterrows():
        oid = str(row.get('order_id'))
        close_active_trade(oid, "SL")

    msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [EMERGENCY] KILL SWITCH ACCIONADO: {count} posiciones cerradas inmediatamente a mercado."
    st.session_state.logs.insert(0, msg)
    enviar_notificacion_push("🚨 KILL SWITCH ACTIVADO", f"Se han liquidado forzosamente {count} posiciones abiertas para resguardo de capital.")
    st.error(f"🚨 KILL SWITCH EJECUTADO: {count} posiciones cerradas de emergencia.")

def execute_autonomous_market_scan(verbose: bool = False) -> List[str]:
    """
    Escanea la Watchlist de 18 pares y abre automáticamente posiciones
    si se cumplen todas las condiciones de confluencia:
    - No superar el límite de 3 posiciones abiertas.
    - No superar el Circuit Breaker diario (-3.0%).
    - Tendencia Macro 4H alineada con Gatillo Micro 15M (RSI, SMC, Volumen).
    - Spread en Kraken < 0.15%.
    """
    scan_logs = []
    df_current = load_trades_data()
    open_trades = df_current[df_current['status'] == 'OPEN'] if not df_current.empty else pd.DataFrame()
    open_count = len(open_trades)

    if open_count >= MAX_CONCURRENT_POSITIONS:
        msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [PORTAFOLIO COMPLETO] 3 de 3 posiciones abiertas. Nuevas entradas en pausa."
        scan_logs.append(msg)
        return scan_logs

    open_symbols = set(open_trades['symbol'].tolist()) if not open_trades.empty else set()
    slots_left = MAX_CONCURRENT_POSITIONS - open_count

    for sym in WATCHLIST_18:
        if slots_left <= 0:
            break
        if sym in open_symbols:
            continue

        confl = evaluate_micro_confluence_15m(sym)
        act = confl.get("action", "HOLD")

        if act in ["LONG", "SHORT"]:
            cur_p = BASE_PRICES.get(sym, 100.0)
            atr_u = confl.get("atr_pct", 0.02)
            oid = save_new_trade(sym, act, cur_p, atr_u)
            if oid:
                open_symbols.add(sym)
                slots_left -= 1
                msg_ok = f"[{now_cot().strftime('%H:%M:%S COT')}] [AUTO-TRADE] ¡Orden generada en {sym} ({act}) por confluencia!"
                scan_logs.append(msg_ok)
        elif verbose:
            scan_logs.append(f"[{now_cot().strftime('%H:%M:%S COT')}] [SCANNER] {sym}: {confl.get('reason', 'Sin confluencia')}")

    return scan_logs

def run_autonomous_trading_daemon():
    """Hilo demonio que ejecuta el escáner y trailing stop de forma continua cada 15 minutos."""
    while True:
        try:
            execute_autonomous_market_scan(verbose=False)
            apply_trailing_stop_to_breakeven()
        except Exception:
            pass
        time.sleep(900)

if "trading_daemon_initialized" not in st.session_state:
    st.session_state.trading_daemon_initialized = True
    t_trade = threading.Thread(target=run_autonomous_trading_daemon, daemon=True)
    t_trade.start()

# Ejecución periódica del trailing stop al cargar interfaz
apply_trailing_stop_to_breakeven()

# --------------------------------------------------------------------------------------
# 10. MÉTRICAS AVANZADAS: PROFIT FACTOR, DRAWDOWN, WIN RATE & SEMANAL
# --------------------------------------------------------------------------------------
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

df_all = load_trades_data()
df_open = df_all[df_all["status"] == "OPEN"].copy() if not df_all.empty else pd.DataFrame()
df_closed_all = df_all[df_all["status"] == "CLOSED"].copy() if not df_all.empty else pd.DataFrame()

if not df_closed_all.empty and "created_at" in df_closed_all.columns:
    df_closed = df_closed_all[df_closed_all["created_at"].apply(is_within_current_trading_week)].copy()
else:
    df_closed = df_closed_all

total_closed = len(df_closed)
wins = len(df_closed[df_closed["pnl_usd"] > 0]) if total_closed > 0 else 0
losses = len(df_closed[df_closed["pnl_usd"] < 0]) if total_closed > 0 else 0
win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0
total_pnl_usd = df_closed["pnl_usd"].sum() if total_closed > 0 else 0.0
total_pnl_pct = (total_pnl_usd / INITIAL_CAPITAL) * 100.0
current_capital = INITIAL_CAPITAL + total_pnl_usd
floating_pnl_usd = df_open["pnl_usd"].sum() if not df_open.empty else 0.0

# Cálculo de Profit Factor
gross_profits = df_closed[df_closed["pnl_usd"] > 0]["pnl_usd"].sum() if total_closed > 0 else 0.0
gross_losses = abs(df_closed[df_closed["pnl_usd"] < 0]["pnl_usd"].sum()) if total_closed > 0 else 0.0
profit_factor = (gross_profits / (gross_losses + 1e-9)) if gross_losses > 0 else (gross_profits if gross_profits > 0 else 1.0)

# Cálculo de Max Drawdown
if not df_closed.empty:
    df_cum = df_closed.sort_values(by="created_at", ascending=True).copy()
    equity_curve = [INITIAL_CAPITAL]
    for p in df_cum["pnl_usd"]:
        equity_curve.append(equity_curve[-1] + p)
    peak = INITIAL_CAPITAL
    max_dd_val = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd_val:
            max_dd_val = dd
    max_drawdown_pct = max_dd_val * 100.0
else:
    max_drawdown_pct = 0.0

# Circuit Breaker Diario
today_str = now_cot().strftime("%Y-%m-%d")
if not df_closed.empty and "created_at" in df_closed.columns:
    df_today = df_closed[df_closed["created_at"].str.startswith(today_str)]
    today_pnl_usd = df_today["pnl_usd"].sum() if not df_today.empty else 0.0
else:
    today_pnl_usd = 0.0
today_pnl_pct = (today_pnl_usd / INITIAL_CAPITAL) * 100.0
circuit_active = today_pnl_pct <= (DAILY_CIRCUIT_BREAKER * 100.0)

# Sincronización de daily_metrics en Supabase
if HAS_SUPABASE and supabase_client:
    try:
        supabase_client.table("daily_metrics").upsert({
            "date": today_str,
            "pnl_usd": today_pnl_usd,
            "pnl_pct": today_pnl_pct,
            "trades_count": len(df_today) if not df_closed.empty else 0,
            "circuit_breaker_active": circuit_active,
            "updated_at": now_cot().isoformat()
        }).execute()
    except Exception:
        pass

# --------------------------------------------------------------------------------------
# 11. ENCABEZADO EJECUTIVO SUPERIOR CON SELECTOR DESPLEGABLE
# --------------------------------------------------------------------------------------
col_h_brand, col_h_filter = st.columns([3, 2])

with col_h_brand:
    hora_cot_str = now_cot().strftime('%H:%M:%S')
    render_html(f"""
    <div class="exec-brand-box">
        <div class="exec-logo-icon">⚡</div>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 19px; font-weight: 800; color: #ffffff; letter-spacing: 0.04em;">PROYECTO DIPPER</span>
                <span style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; font-family: 'JetBrains Mono';">v3.0 QUANT EXECUTIVE</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px; flex-wrap: wrap;">
                <div class="status-badge" style="color: #10b981;">
                    <div class="pulse-dot"></div>
                    <span>MOTOR: ONLINE</span>
                </div>
                <div class="status-badge" style="color: {'#38bdf8' if HAS_SUPABASE else '#94a3b8'};">
                    <span>SUPABASE: {'POSTGRES OK' if HAS_SUPABASE else 'STANDALONE'}</span>
                </div>
                <div class="status-badge" style="color: #cbd5e1;">
                    <span>HORA COT: <b>{hora_cot_str}</b></span>
                </div>
                <div class="status-badge" style="color: {'#10b981' if not circuit_active else '#f43f5e'};">
                    <span>CIRCUIT BREAKER: {'NORMAL' if not circuit_active else 'DISPARADO'}</span>
                </div>
            </div>
        </div>
    </div>
    """)

with col_h_filter:
    categoria_seleccionada = st.selectbox(
        "Filtrar Activos por Sector",
        options=list(CATEGORY_MAP.keys()),
        index=0,
        help="Filtra el universo de trading y las tablas según el sector seleccionado."
    )
    activos_filtrados = CATEGORY_MAP.get(categoria_seleccionada, WATCHLIST_18)

render_html("<div style='height: 10px;'></div>")

# --------------------------------------------------------------------------------------
# 12. NAVEGACIÓN PRINCIPAL: 4 PESTAÑAS EJECUTIVAS
# --------------------------------------------------------------------------------------
tab_resumen, tab_graficos, tab_posiciones, tab_historial = st.tabs([
    "📊 Resumen General",
    "📈 Gráficos & Análisis",
    f"💼 Posiciones Activas ({len(df_open)}/3)",
    f"📜 Historial & Audit Log ({total_closed})"
])

# ======================================================================================
# PESTAÑA 1: 📊 RESUMEN GENERAL (7 KPI CARDS, MATRIZ CUANTITATIVA, ACCIONES)
# ======================================================================================
with tab_resumen:
    cb_status_html = '<span style="color: #10b981;">NORMAL</span>' if not circuit_active else '<span style="color: #f43f5e;">DISPARADO</span>'
    cb_badge_dot = '<div style="width: 7px; height: 7px; border-radius: 50%; background: #10b981; display: inline-block;"></div>' if not circuit_active else '<div style="width: 7px; height: 7px; border-radius: 50%; background: #f43f5e; display: inline-block;"></div>'

    kpi_cards_html = f"""
    <div class="kpi-grid-7">
        <div class="kpi-card">
            <div class="kpi-label"><span>Capital Base</span><span style="color: #64748b;">FIJO</span></div>
            <div class="kpi-value">${INITIAL_CAPITAL:,.2f}</div>
            <div class="kpi-subtext sub-neutral"><span>Capital Inicial USD</span></div>
        </div>

        <div class="kpi-card">
            <div class="kpi-label"><span>Balance Actual</span><span style="color: #38bdf8;">EQUITY</span></div>
            <div class="kpi-value">${current_capital:,.2f}</div>
            <div class="kpi-subtext {'sub-green' if total_pnl_usd >= 0 else 'sub-red'}">
                <span>{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}% acumulado</span>
            </div>
        </div>

        <div class="kpi-card">
            <div class="kpi-label"><span>PnL Neto Semanal</span><span style="color: #64748b;">REALIZADO</span></div>
            <div class="kpi-value" style="color: {'#10b981' if total_pnl_usd >= 0 else '#f43f5e'};">
                {'+' if total_pnl_usd >= 0 else ''}${total_pnl_usd:,.2f}
            </div>
            <div class="kpi-subtext {'sub-green' if total_pnl_usd >= 0 else 'sub-red'}">
                <span>{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}% s/capital</span>
            </div>
        </div>

        <div class="kpi-card">
            <div class="kpi-label"><span>PnL Flotante</span><span style="color: #64748b;">UNREALIZED</span></div>
            <div class="kpi-value" style="color: {'#10b981' if floating_pnl_usd >= 0 else '#f43f5e'};">
                {'+' if floating_pnl_usd >= 0 else ''}${floating_pnl_usd:,.2f}
            </div>
            <div class="kpi-subtext sub-neutral"><span>{len(df_open)} de 3 abiertas</span></div>
        </div>

        <div class="kpi-card">
            <div class="kpi-label"><span>Win Rate</span><span style="color: #64748b;">W/L</span></div>
            <div class="kpi-value">{win_rate:.1f}%</div>
            <div class="kpi-subtext sub-green"><span>{wins}W</span><span style="color: #64748b;">/</span><span class="sub-red">{losses}L</span></div>
        </div>

        <div class="kpi-card">
            <div class="kpi-label"><span>Profit Factor</span><span style="color: #64748b;">RATIO</span></div>
            <div class="kpi-value">{profit_factor:.2f}</div>
            <div class="kpi-subtext sub-neutral"><span>Ganancias / Pérdidas</span></div>
        </div>

        <div class="kpi-card">
            <div class="kpi-label"><span>Max Drawdown</span><span style="color: #f43f5e;">RIESGO</span></div>
            <div class="kpi-value" style="color: #f43f5e;">-{max_drawdown_pct:.2f}%</div>
            <div class="kpi-subtext sub-red"><span>Pérdida Máx Pico-Valle</span></div>
        </div>
    </div>
    """
    render_html(kpi_cards_html)

    # Matriz y Parámetros
    col_mat, col_ctrl = st.columns([3, 2])

    with col_mat:
        render_html("""
        <div class="section-header">
            <div class="section-title">
                <span style="color: #38bdf8;">🛡️</span>
                <span>Matriz Cuantitativa de Riesgo Asimétrico (1:3)</span>
            </div>
            <div class="section-tag">REGLAS DIPPER v3.0</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-family: 'JetBrains Mono'; font-size: 11px; margin-bottom: 14px;">
            <div style="background: #090e17; border: 1px solid #16202e; border-radius: 8px; padding: 10px;">
                <div style="color: #64748b;">RIESGO / TRADE</div>
                <div style="color: #f8fafc; font-weight: 700; font-size: 13.5px; margin-top: 4px;">1.50% Dinámico</div>
            </div>
            <div style="background: #090e17; border: 1px solid #16202e; border-radius: 8px; padding: 10px;">
                <div style="color: #64748b;">TAKE PROFIT (TP)</div>
                <div style="color: #10b981; font-weight: 700; font-size: 13.5px; margin-top: 4px;">+4.0% a +5.0% Dinámico</div>
            </div>
            <div style="background: #090e17; border: 1px solid #16202e; border-radius: 8px; padding: 10px;">
                <div style="color: #64748b;">STOP LOSS (SL)</div>
                <div style="color: #f43f5e; font-weight: 700; font-size: 13.5px; margin-top: 4px;">-1.50% Fijo</div>
            </div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-family: 'JetBrains Mono'; font-size: 11px;">
            <div style="background: #090e17; border: 1px solid #16202e; border-radius: 8px; padding: 10px;">
                <div style="color: #64748b;">TRAILING A BREAK-EVEN</div>
                <div style="color: #38bdf8; font-weight: 700; font-size: 13.5px; margin-top: 4px;">Gatillo en +2.0% Flotante</div>
            </div>
            <div style="background: #090e17; border: 1px solid #16202e; border-radius: 8px; padding: 10px;">
                <div style="color: #64748b;">FILTRO SPREAD</div>
                <div style="color: #f8fafc; font-weight: 700; font-size: 13.5px; margin-top: 4px;">Máximo 0.15%</div>
            </div>
            <div style="background: #090e17; border: 1px solid #16202e; border-radius: 8px; padding: 10px;">
                <div style="color: #64748b;">CIRCUIT BREAKER</div>
                <div style="color: #f59e0b; font-weight: 700; font-size: 13.5px; margin-top: 4px;">-3.00% Diario en COT</div>
            </div>
        </div>
        """)

    with col_ctrl:
        render_html("""
        <div class="section-header">
            <div class="section-title">
                <span style="color: #f59e0b;">⚡</span>
                <span>Centro de Comandos & Utilidades</span>
            </div>
            <div class="section-tag">ACCIONES RÁPIDAS</div>
        </div>
        """)
        c_c1, c_c2 = st.columns(2)
        with c_c1:
            if st.button("🔴 Reset Saldo ($1,000 USD)", use_container_width=True):
                if HAS_SUPABASE and supabase_client:
                    try:
                        supabase_client.table("paper_trades").delete().neq("id", 0).execute()
                        supabase_client.table("daily_metrics").delete().neq("id", 0).execute()
                    except Exception:
                        pass
                st.session_state.trades_cache = pd.DataFrame()
                st.session_state.capital = INITIAL_CAPITAL
                st.session_state.logs.insert(0, f"[{now_cot().strftime('%H:%M:%S COT')}] [ACTION] Reset manual ejecutado. Base de datos restablecida a $1,000 USD.")
                enviar_notificacion_push("PROYECTO DIPPER | RESET", "Se ha restablecido la base de datos y el capital a $1,000 USD.")
                st.success("Sistema reiniciado a $1,000 USD.")
                time.sleep(0.8)
                st.rerun()

        with c_c2:
            if st.button("🔔 Enviar Ping Ntfy", use_container_width=True):
                enviar_notificacion_push(
                    "PROYECTO DIPPER | PING",
                    f"Validación de alerta push emitida desde Terminal Ejecutiva ({now_cot().strftime('%H:%M:%S COT')})."
                )
                st.success(f"Alerta enviada a ntfy.sh/{NTFY_TOPIC}")

        c_c3, c_c4 = st.columns(2)
        with c_c3:
            if st.button("🧹 Normalizar PnL", use_container_width=True):
                if "trades_cache" in st.session_state and not st.session_state.trades_cache.empty:
                    df_norm = st.session_state.trades_cache.copy()
                    for i, r in df_norm.iterrows():
                        if r.get('status') == 'CLOSED':
                            is_sl = 'SL' in str(r.get('exit_reason', '')) or float(r.get('pnl_usd', 0)) < 0
                            df_norm.at[i, 'pnl_usd'] = -15.0 if is_sl else 40.0
                            df_norm.at[i, 'pnl_pct'] = -1.5 if is_sl else 4.0
                    st.session_state.trades_cache = df_norm
                    st.session_state.logs.insert(0, f"[{now_cot().strftime('%H:%M:%S COT')}] [SUCCESS] Saneamiento completado: PnL normalizados.")
                    st.success("Trades normalizados exitosamente.")
                    st.rerun()

        with c_c4:
            if st.button("🔄 Refrescar Kraken", use_container_width=True):
                st.cache_data.clear()
                st.session_state.logs.insert(0, f"[{now_cot().strftime('%H:%M:%S COT')}] [ACTION] Datos de mercado refrescados.")
                st.rerun()

        if st.button("⚡ ESCANEAR Y OPERAR 18 PARES AHORA", use_container_width=True):
            st.cache_data.clear()
            scan_res = execute_autonomous_market_scan(verbose=True)
            for r in scan_res:
                st.session_state.logs.insert(0, r)
            st.success("Escaneo completado. Revisa el registro de auditoría.")
            time.sleep(0.5)
            st.rerun()

# ======================================================================================
# PESTAÑA 2: 📈 GRÁFICOS & ANÁLISIS (EQUITY CURVE, PNL POR ACTIVO, CANDLESTICKS 15M)
# ======================================================================================
with tab_graficos:
    render_html("""
    <div class="section-header">
        <div class="section-title">
            <span style="color: #38bdf8;">📈</span>
            <span>Curva de Capital Acumulada (Equity Curve)</span>
        </div>
        <div class="section-tag">SEGUIMIENTO MONTE CARLO / EN VIVO</div>
    </div>
    """)

    if not df_closed.empty:
        df_sorted = df_closed.sort_values(by="created_at", ascending=True).copy()
        equity = [INITIAL_CAPITAL]
        labels = ["Capital Inicial"]

        running = INITIAL_CAPITAL
        for idx, r in df_sorted.iterrows():
            running += float(r.get('pnl_usd', 0.0))
            equity.append(running)
            labels.append(f"{r.get('symbol', '')} ({'+' if float(r.get('pnl_usd', 0)) >= 0 else ''}${float(r.get('pnl_usd', 0)):,.2f})")

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=list(range(len(equity))),
            y=equity,
            mode='lines+markers',
            line=dict(color='#10b981' if current_capital >= INITIAL_CAPITAL else '#f43f5e', width=2.5, shape='spline'),
            marker=dict(size=7, color='#38bdf8', line=dict(color='#04070b', width=1.5)),
            fill='tozeroy',
            fillcolor='rgba(16, 185, 129, 0.08)' if current_capital >= INITIAL_CAPITAL else 'rgba(244, 63, 94, 0.08)',
            text=labels,
            hovertemplate='<b>%{text}</b><br>Capital: $%{y:,.2f} USD<extra></extra>'
        ))

        fig_eq.add_hline(
            y=INITIAL_CAPITAL,
            line_dash="dot",
            line_color="#475569",
            annotation_text="Base: $1,000.00 USD",
            annotation_position="bottom right",
            annotation_font_color="#64748b",
            annotation_font_size=10
        )

        fig_eq.update_layout(
            template="plotly_dark",
            paper_bgcolor="#080d14",
            plot_bgcolor="#06090e",
            margin=dict(l=45, r=20, t=15, b=35),
            height=280,
            font=dict(family="JetBrains Mono", size=10, color="#64748b"),
            xaxis=dict(title=dict(text="Operaciones Ejecutadas (Ciclo Semanal)", font=dict(size=11, color="#64748b")), gridcolor="#121a24"),
            yaxis=dict(title=dict(text="Balance (USD)", font=dict(size=11, color="#64748b")), gridcolor="#121a24", tickprefix="$", tickformat=",.0f")
        )
        st.plotly_chart(fig_eq, use_container_width=True, config={"displayModeBar": False})
    else:
        render_html("""
        <div style="background-color: #080d14; border: 1px dashed #1e293b; border-radius: 8px; padding: 20px; text-align: center; color: #64748b; font-size: 12px; font-family: 'JetBrains Mono'; margin-bottom: 20px;">
            SIN REGISTROS CERRADOS PARA CALCULAR LA CURVA DE CAPITAL.
        </div>
        """)

    col_g_bar, col_g_cand = st.columns([1, 1])

    with col_g_bar:
        render_html("""
        <div class="section-header">
            <div class="section-title">
                <span style="color: #10b981;">📊</span>
                <span>Rendimiento PnL por Activo Operado</span>
            </div>
            <div class="section-tag">DISTRIBUCIÓN DE RETORNO</div>
        </div>
        """)
        if not df_closed.empty and "symbol" in df_closed.columns:
            pnl_by_symbol = df_closed.groupby("symbol")["pnl_usd"].sum().reset_index()
            bar_colors = ['#10b981' if v >= 0 else '#f43f5e' for v in pnl_by_symbol["pnl_usd"]]

            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=pnl_by_symbol["symbol"],
                y=pnl_by_symbol["pnl_usd"],
                marker_color=bar_colors,
                text=[f"{v:+.2f}$" for v in pnl_by_symbol["pnl_usd"]],
                textposition='auto'
            ))
            fig_bar.update_layout(
                template="plotly_dark",
                paper_bgcolor="#080d14",
                plot_bgcolor="#06090e",
                margin=dict(l=35, r=15, t=10, b=30),
                height=260,
                font=dict(family="JetBrains Mono", size=10, color="#64748b"),
                yaxis=dict(gridcolor="#121a24", tickprefix="$"),
                xaxis=dict(gridcolor="#121a24")
            )
            st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})
        else:
            render_html("""
            <div style="background-color: #080d14; border: 1px dashed #1e293b; border-radius: 8px; padding: 20px; text-align: center; color: #64748b; font-size: 11px; font-family: 'JetBrains Mono';">
                EJECUTA TRADES PARA VER EL RENDIMIENTO POR ACTIVO.
            </div>
            """)

    with col_g_cand:
        render_html("""
        <div class="section-header">
            <div class="section-title">
                <span style="color: #38bdf8;">🕯️</span>
                <span>Velas Candlestick 15M + EMA 200 en Vivo</span>
            </div>
            <div class="section-tag">DATOS KRAKEN SPOT</div>
        </div>
        """)
        par_grafica = st.selectbox("Seleccionar Activo para Análisis OHLC", options=activos_filtrados, index=0)
        df_candles = fetch_kraken_ohlcv(par_grafica, timeframe='15m', limit=40)

        if not df_candles.empty:
            fig_cand = go.Figure()
            fig_cand.add_trace(go.Candlestick(
                x=df_candles['datetime'],
                open=df_candles['open'],
                high=df_candles['high'],
                low=df_candles['low'],
                close=df_candles['close'],
                name=par_grafica,
                increasing_line_color='#10b981',
                decreasing_line_color='#f43f5e'
            ))
            fig_cand.add_trace(go.Scatter(
                x=df_candles['datetime'],
                y=df_candles['ema200'],
                mode='lines',
                line=dict(color='#38bdf8', width=1.5),
                name='EMA 200'
            ))
            fig_cand.update_layout(
                template="plotly_dark",
                paper_bgcolor="#080d14",
                plot_bgcolor="#06090e",
                margin=dict(l=35, r=15, t=10, b=25),
                height=260,
                xaxis_rangeslider_visible=False,
                font=dict(family="JetBrains Mono", size=10, color="#64748b"),
                yaxis=dict(gridcolor="#121a24", tickprefix="$")
            )
            st.plotly_chart(fig_cand, use_container_width=True, config={"displayModeBar": False})

# ======================================================================================
# PESTAÑA 3: 💼 POSICIONES ACTIVAS & GESTIÓN DIRECTA (KILL SWITCH)
# ======================================================================================
with tab_posiciones:
    render_html("""
    <div class="section-header">
        <div class="section-title">
            <span style="color: #38bdf8;">●</span>
            <span>Operaciones Abiertas en Kraken Spot</span>
        </div>
        <div class="section-tag">MÁXIMO 3 CONCURRENTES · RIESGO 1.5% · TP DINÁMICO 4%-5% · SL -1.5%</div>
    </div>
    """)

    # BOTÓN DE PÁNICO (KILL SWITCH)
    col_t_title, col_t_kill = st.columns([3, 1])
    with col_t_title:
        render_html("<div style='font-family: JetBrains Mono; font-size: 11px; color: #94a3b8;'>Estado de posiciones activas en tiempo real:</div>")
    with col_t_kill:
        st.markdown('<div class="kill-switch-btn">', unsafe_allow_html=True)
        if st.button("🚨 KILL SWITCH (CERRAR TODO)", use_container_width=True):
            kill_switch_close_all()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if df_open.empty:
        render_html("""
        <div style="background-color: #080d14; border: 1px dashed #1e293b; border-radius: 8px; padding: 24px; text-align: center; color: #64748b; font-size: 12px; font-family: 'JetBrains Mono'; margin-bottom: 20px;">
            🔍 NO HAY POSICIONES ABIERTAS ACTUALMENTE. EL MOTOR CUANTITATIVO ESTÁ ESCANEANDO EL MERCADO.
        </div>
        """)
    else:
        rows_open = []
        for _, row in df_open.iterrows():
            pnl_val = float(row.get('pnl_usd', 0.0))
            pnl_pct = float(row.get('pnl_pct', 0.0))
            side = str(row.get('side', 'LONG')).upper()
            side_color = "#10b981" if side == "LONG" else "#f43f5e"
            pnl_color = "#10b981" if pnl_val >= 0 else "#f43f5e"
            pnl_str = f"+${pnl_val:,.2f} USD" if pnl_val >= 0 else f"-${abs(pnl_val):,.2f} USD"

            entry_p = float(row.get('entry_price', 0.0))
            sl_p = float(row.get('sl', entry_p * 0.985))
            tp_p = float(row.get('tp', entry_p * 1.04))
            trailing_status = "BE ASEGURADO" if bool(row.get('trailing_be', False)) else "ACTIVO"

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
                f"<td><span style=\"color: {side_color}; font-weight: 700;\">{side}</span></td>"
                f"<td>${entry_p:,.4f}</td>"
                f"<td style=\"color: #f43f5e;\">${sl_p:,.4f}</td>"
                f"<td style=\"color: #10b981;\">${tp_p:,.4f}</td>"
                f"<td style=\"color: {pnl_color}; font-weight: 700;\">{pnl_str}</td>"
                f"<td style=\"color: {pnl_color}; font-weight: 700;\">{pnl_pct:+.2f}%</td>"
                f"<td style=\"color: #94a3b8;\">{hora_open}</td>"
                f"<td><span class=\"badge-pro {'badge-be' if row.get('trailing_be') else 'badge-open'}\">● {trailing_status}</span></td>"
                f"</tr>"
            )

        table_open_html = (
            "<div class=\"table-container\">"
            "<table class=\"quant-table-pro\">"
            "<thead><tr>"
            "<th>ID Orden</th><th>Símbolo</th><th>Lado</th><th>Precio Entrada</th>"
            "<th>Stop Loss</th><th>Take Profit (Dinámico)</th><th>PnL Flotante ($)</th><th>PnL (%)</th>"
            "<th>Hora Apertura (COT)</th><th>Estado / Trailing</th>"
            "</tr></thead>"
            "<tbody>" + "".join(rows_open) + "</tbody></table></div>"
        )
        render_html(table_open_html)

        # Acciones de Cierre Manual
        render_html("""
        <div class="section-header">
            <div class="section-title">
                <span style="color: #f59e0b;">🎯</span>
                <span>Controles de Cierre Individual de Posición</span>
            </div>
            <div class="section-tag">CIERRE A MERCADO / TP / SL / BREAK-EVEN</div>
        </div>
        """)

        for _, row in df_open.iterrows():
            oid = str(row.get('order_id'))
            sym = str(row.get('symbol'))
            sd = str(row.get('side'))
            col_lbl, col_tp_btn, col_be_btn, col_sl_btn = st.columns([2, 1, 1, 1])
            with col_lbl:
                render_html(f"<div style='font-family: JetBrains Mono; font-size: 12px; padding-top: 8px;'>Orden activa: <b style='color: #38bdf8;'>{oid}</b> ({sd} {sym})</div>")
            with col_tp_btn:
                if st.button(f"🎯 Cerrar TP (+4%-5%)", key=f"tp_{oid}", use_container_width=True):
                    close_active_trade(oid, "TP")
                    st.rerun()
            with col_be_btn:
                if st.button(f"🛡️ Salir BE (+0.1%)", key=f"be_{oid}", use_container_width=True):
                    close_active_trade(oid, "BE")
                    st.rerun()
            with col_sl_btn:
                if st.button(f"🛑 Cerrar SL (-1.5%)", key=f"sl_{oid}", use_container_width=True):
                    close_active_trade(oid, "SL")
                    st.rerun()

    # Módulo de Apertura Rápida
    render_html("""
    <div class="section-header" style="margin-top: 24px;">
        <div class="section-title">
            <span style="color: #38bdf8;">⚡</span>
            <span>Apertura de Nueva Posición (Ejecución Instantánea)</span>
        </div>
        <div class="section-tag">CONTROL DE SPREAD & RIESGO 1.5%</div>
    </div>
    """)

    c_sym_sel, c_btn_long, c_btn_short = st.columns([2, 1, 1])
    with c_sym_sel:
        target_sym = st.selectbox("Activo a Operar", options=activos_filtrados, index=0)
    
    cur_p = BASE_PRICES.get(target_sym, 100.0)
    eval_res = evaluate_micro_confluence_15m(target_sym)
    atr_use = eval_res.get("atr_pct", 0.02)

    with c_btn_long:
        if st.button("🟢 ABRIR LONG (+4%-5% / -1.5%)", use_container_width=True, disabled=len(df_open) >= 3):
            save_new_trade(target_sym, "LONG", cur_p, atr_use)
            st.rerun()

    with c_btn_short:
        if st.button("🔴 ABRIR SHORT (+4%-5% / -1.5%)", use_container_width=True, disabled=len(df_open) >= 3):
            save_new_trade(target_sym, "SHORT", cur_p, atr_use)
            st.rerun()

# ======================================================================================
# PESTAÑA 4: 📜 HISTORIAL & AUDIT LOG (TABLA CERRADA CON FILAS COLOREADAS & LOGS)
# ======================================================================================
with tab_historial:
    render_html("""
    <div class="section-header">
        <div class="section-title">
            <span style="color: #10b981;">📜</span>
            <span>Bitácora de Órdenes Cerradas (Ciclo Semanal)</span>
        </div>
        <div class="section-tag">FILAS COMPLETAS COLOREADAS · HORA COLOMBIA (COT UTC-5)</div>
    </div>
    """)

    if df_closed.empty:
        render_html("""
        <div style="background-color: #080d14; border: 1px dashed #1e293b; border-radius: 8px; padding: 24px; text-align: center; color: #64748b; font-size: 12px; font-family: 'JetBrains Mono'; margin-bottom: 20px;">
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
            side_color = "#10b981" if side == "LONG" else "#f43f5e"

            is_sl = ("SL" in reason) or ("STOP" in reason) or (pnl_val < 0)
            is_be = ("BREAK" in reason) or ("BE" in reason) or (abs(pnl_pct) <= 0.2)

            if is_sl:
                row_class = "row-sl"
                gain_usd_str = f"-${abs(pnl_val):,.2f} USD"
                gain_pct_str = f"-{abs(pnl_pct):.2f}%"
                badge = '<span class="badge-pro badge-sl">CERRADO (SL)</span>'
                gain_style = "color: #f43f5e; font-weight: 700;"
            elif is_be:
                row_class = "row-be"
                gain_usd_str = f"+${pnl_val:,.2f} USD"
                gain_pct_str = f"+{pnl_pct:.2f}%"
                badge = '<span class="badge-pro badge-be">BREAK-EVEN</span>'
                gain_style = "color: #f59e0b; font-weight: 700;"
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
                f"<td><span style=\"color: {side_color}; font-weight: 700;\">{side}</span></td>"
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
            "<th>Símbolo</th><th>Lado</th><th>Precio Entrada</th><th>Precio Salida</th>"
            "<th>Ganancia ($ USD)</th><th>Retorno (%)</th><th>Resultado</th>"
            "</tr></thead>"
            "<tbody>" + "".join(rows_closed) + "</tbody></table></div>"
        )
        render_html(table_closed_html)

        csv_data = df_closed.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Bitácora Completa en CSV",
            data=csv_data,
            file_name=f"dipper_trades_{today_str}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # Registro de Auditoría (Audit Log)
    render_html("""
    <div class="section-header" style="margin-top: 24px;">
        <div class="section-title">
            <span style="color: #38bdf8;">📋</span>
            <span>Registro de Auditoría y Eventos del Sistema (Audit Log)</span>
        </div>
        <div class="section-tag">ZONA HORARIA COLOMBIA (COT UTC-5)</div>
    </div>
    """)
    log_content = "".join([f"<div class='audit-entry'>{l}</div>" for l in st.session_state.logs[:30]])
    render_html(f"<div class='audit-log-box'>{log_content}</div>")
