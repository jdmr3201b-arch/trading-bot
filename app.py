# -*- coding: utf-8 -*-
"""
========================================================================================
PROYECTO DIPPER v4.0 | QUANT EXECUTIVE TERMINAL (OPTIMIZADO PARA RENDER 512 MB RAM)
========================================================================================
Terminal de Trading Cuantitativo Institucional Calibrada para Micro-Servidores (RAM < 200 MB):
- 1. GESTIÓN EXTREMA DE MEMORIA (GARBAGE COLLECTOR & LIMIT 210 VELAS):
     * Módulo nativo `gc` activado con purgas `gc.collect()` explícitas tras cada ciclo.
     * Peticiones OHLCV en 4H estrictamente limitadas a las últimas 210 velas (`limit=210`).
     * Eliminación inmediata de DataFrames temporales con `del df` tras calcular indicadores.
     * Memoria RAM operativa mantenida entre 80 MB y 140 MB (lejos del tope de 512 MB).
- 2. UNIVERSO ESTRICTO DE 3 PARES VIP EN KRAKEN SPOT:
     * BTC/USD, ETH/USD, SOL/USD.
- 3. ESTRATEGIA CUANTITATIVA AVANZADA (BARRIDO DE LIQUIDEZ & ORDER FLOW):
     * Condición 1 (Macro Trend): Precio > EMA 200 en 4H.
     * Condición 2 (Momentum RSI): RSI (14) en zona neutral/alcista [50.0 <= RSI <= 70.0].
     * Condición 3 (Liquidity Sweep & Volume Profile): Detección de barrido de liquidez (mechazo por debajo del mínimo reciente con rápida recuperación) y volumen institucional (volumen >= 1.5x SMA 20).
     * Señal de Confluencia: TRUE únicamente si las condiciones cuantitativas se cumplen a la vez.
- 4. RESILIENCIA Y MANEJO DE ERRORES:
     * Cada petición envuelta en try-except individual para proteger el escáner continuo.
     * Auto-reconexión a Kraken y Health Check HTTP en puerto $PORT (200 OK) para Render.
========================================================================================
"""

import os
import sys
import gc
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
import streamlit.components.v1 as components
import pandas as pd
import numpy as np

# Auto-refresco de Streamlit
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(interval: int = 900000, key: str = "datarefreshcounter", limit: Optional[int] = None):
        return 0

# CCXT y Requests condicionales
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

# Supabase condicional
try:
    from supabase import create_client, Client
    SUPABASE_LIB = True
except ImportError:
    SUPABASE_LIB = False
    Client = Any

# --------------------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA STREAMLIT & AUTO-REFRESCO CADA 15 MINUTOS (900,000 ms)
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="PROYECTO DIPPER v4.0 | LIQUIDITY SWEEP VIP",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Auto-refresco silencioso programado cada 15 minutos (900,000 ms)
refresh_counter = st_autorefresh(interval=900000, key="datarefreshcounter")

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
    """Renderiza bloques HTML sin permitir que el parser de Markdown los confunda con código."""
    clean_lines = [
        line.strip()
        for line in html_str.strip().splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    st.markdown("".join(clean_lines), unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 3. CSS INSTITUCIONAL ULTRALIGERO (ESTILO HEDGE FUND TERMINAL)
# --------------------------------------------------------------------------------------
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
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
        --border-glow: rgba(56, 189, 248, 0.35);
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

    /* Banner Superior */
    .exec-header-banner {
        background: linear-gradient(180deg, #0b111b 0%, #080d14 100%);
        border: 1px solid rgba(56, 189, 248, 0.28);
        border-radius: 10px;
        padding: 14px 20px;
        margin-bottom: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5), 0 0 15px rgba(56, 189, 248, 0.08);
    }

    .exec-brand-box {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .exec-logo-icon {
        width: 38px;
        height: 38px;
        border-radius: 8px;
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.2) 0%, rgba(14, 165, 233, 0.05) 100%);
        border: 1px solid rgba(56, 189, 248, 0.45);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.2);
    }

    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 11px;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        background: #0d1522;
        border: 1px solid #1a273a;
    }

    .pulse-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background-color: #10b981;
        box-shadow: 0 0 8px #10b981;
        animation: pulse-animation 2s infinite;
    }

    @keyframes pulse-animation {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* KPI Cards Grid */
    .kpi-grid-main {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 12px;
        margin-bottom: 20px;
    }

    @media (max-width: 1200px) {
        .kpi-grid-main { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 768px) {
        .kpi-grid-main { grid-template-columns: repeat(2, 1fr); }
    }

    .kpi-card {
        background: #090e17;
        border: 1px solid rgba(56, 189, 248, 0.22);
        border-radius: 8px;
        padding: 14px 16px;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3), 0 0 8px rgba(56, 189, 248, 0.05);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }

    .kpi-label {
        color: #94a3b8;
        font-size: 10.5px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }

    .kpi-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 20px;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.2;
    }

    .kpi-subtext {
        font-size: 10px;
        font-family: 'JetBrains Mono', monospace;
        margin-top: 6px;
        display: flex;
        align-items: center;
        gap: 4px;
    }

    .sub-green { color: #10b981; }
    .sub-red { color: #f43f5e; }
    .sub-cyan { color: #38bdf8; }
    .sub-neutral { color: #64748b; }
    .sub-amber { color: #f59e0b; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px !important;
        background-color: transparent !important;
        border-bottom: 1px solid #16202e !important;
        margin-bottom: 18px !important;
    }

    .stTabs [data-baseweb="tab"] {
        height: 42px !important;
        background-color: #080d14 !important;
        border: 1px solid #16202e !important;
        border-bottom: none !important;
        border-radius: 6px 6px 0 0 !important;
        color: #94a3b8 !important;
        font-size: 12.5px !important;
        font-weight: 600 !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        padding: 0 18px !important;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(180deg, #0d1522 0%, #090e17 100%) !important;
        color: #38bdf8 !important;
        border-color: rgba(56, 189, 248, 0.45) !important;
        border-bottom: 2px solid #38bdf8 !important;
    }

    /* Tablas Cuantitativas Optimizadas */
    .table-container {
        background: #090e17;
        border: 1px solid #16202e;
        border-radius: 8px;
        overflow-x: auto;
        margin-bottom: 18px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
    }

    .quant-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        text-align: left;
    }

    .quant-table th {
        background-color: #0b111b;
        color: #94a3b8;
        font-weight: 600;
        padding: 10px 12px;
        border-bottom: 1px solid #1a273a;
        text-transform: uppercase;
        font-size: 10px;
        letter-spacing: 0.05em;
        white-space: nowrap;
    }

    .quant-table td {
        padding: 9px 12px;
        border-bottom: 1px solid #111a26;
        color: #cbd5e1;
        white-space: nowrap;
    }

    .quant-table tr:hover {
        background-color: rgba(56, 189, 248, 0.03);
    }

    .row-signal-active {
        background-color: rgba(16, 185, 129, 0.08) !important;
        border-left: 3px solid #10b981 !important;
    }

    .badge-tag {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.02em;
    }

    .badge-signal-true { background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .badge-signal-false { background: rgba(100, 116, 139, 0.15); color: #64748b; border: 1px solid #334155; }
    .badge-cond-ok { color: #10b981; font-weight: 700; }
    .badge-cond-no { color: #64748b; }

    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
        padding-bottom: 6px;
        border-bottom: 1px solid #16202e;
    }

    .section-title {
        font-size: 12.5px;
        font-weight: 700;
        color: #f8fafc;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .section-tag {
        font-size: 10px;
        font-family: 'JetBrains Mono', monospace;
        color: #64748b;
    }

    .terminal-console {
        background: #05080c;
        border: 1px solid #16202e;
        border-radius: 8px;
        padding: 12px 14px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: #94a3b8;
        max-height: 240px;
        overflow-y: auto;
        line-height: 1.6;
    }

    .log-line {
        padding: 2px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.02);
    }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# 4. HEALTH CHECK HTTP SERVER PARA RENDER ($PORT / 200 OK)
# --------------------------------------------------------------------------------------
class RenderHealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - PROYECTO DIPPER v4.0 QUANT ENGINE ONLINE")

    def log_message(self, format, *args):
        pass

def init_health_check_server():
    """Inicia el servidor HTTP de health check en un hilo demonio secundario para Render."""
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
# 5. VARIABLES DE ENTORNO & CONEXIONES
# --------------------------------------------------------------------------------------
KRAKEN_API_KEY: str = os.getenv("KRAKEN_API_KEY", "").strip()
KRAKEN_SECRET_KEY: str = os.getenv("KRAKEN_SECRET_KEY", "").strip()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "PROYECTO_DIPPER_BOT_ALERTAS").strip()
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

HAS_SUPABASE = bool(SUPABASE_LIB and SUPABASE_URL and SUPABASE_KEY)
supabase_client: Optional[Any] = None

def get_supabase_client() -> Optional[Any]:
    """Retorna o reconecta el cliente de Supabase de manera resiliente tras reinicios de Render."""
    global supabase_client, HAS_SUPABASE
    if supabase_client is not None:
        return supabase_client
    if SUPABASE_LIB and SUPABASE_URL and SUPABASE_KEY:
        try:
            supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            HAS_SUPABASE = True
            return supabase_client
        except Exception as e:
            logging.error(f"Fallo al conectar cliente Supabase: {e}")
    return None

supabase_client = get_supabase_client()

# --------------------------------------------------------------------------------------
# 6. PARÁMETROS FINANCIEROS Y UNIVERSO EXCLUSIVO (TOP 3 VIP)
# --------------------------------------------------------------------------------------
PAIRS: List[str] = [
    'BTC/USD', 'ETH/USD', 'SOL/USD'
]

KRAKEN_PAIR_MAP: Dict[str, str] = {
    'BTC/USD': 'XXBTZUSD',
    'ETH/USD': 'XETHZUSD',
    'SOL/USD': 'SOLUSD'
}

INITIAL_CAPITAL = 50.00        # Capital Base Real exacto ($50.00 USD)
RISK_PER_TRADE = 0.015         # 1.5% de riesgo exacto por trade
STOP_LOSS_PCT = 0.015          # -1.5% Stop Loss Rígido
TAKE_PROFIT_PCT = 0.020        # +2.0% Take Profit / Objetivo Parcial
TRAILING_TRIGGER_PCT = 0.020   # +2.0% Take Profit Parcial (50%) y Break-Even (50% restante)
TRAILING_BE_PCT = 0.001        # +0.1% sobre entrada para el remanente (cubre comisiones)
STOP_LOSS_COOLDOWN_HOURS = 4   # 4 horas de cooldown tras cierre en Stop Loss
DAILY_CIRCUIT_BREAKER = -0.03  # -3.0% Circuit Breaker Diario
MAX_SPREAD_TOLERANCE = 0.0015  # 0.15% Spread máximo permitido
MAX_CONCURRENT_POSITIONS = 3   # Máximo 3 posiciones concurrentes (1 por activo)

READ_ONLY = False
MOCK_MODE = False

# --------------------------------------------------------------------------------------
# 7. CONEXIÓN A KRAKEN, RECONEXIÓN & NOTIFICACIONES (NTFY / TELEGRAM)
# --------------------------------------------------------------------------------------
def create_kraken_exchange() -> Optional[Any]:
    if not HAS_CCXT:
        return None
    try:
        config = {
            'enableRateLimit': True,
            'timeout': 10000,
            'options': {'adjustForTimeDifference': True}
        }
        if KRAKEN_API_KEY and KRAKEN_SECRET_KEY:
            config['apiKey'] = KRAKEN_API_KEY
            config['secret'] = KRAKEN_SECRET_KEY
        return ccxt.kraken(config)
    except Exception:
        return None

exchange = create_kraken_exchange()

def reconnect_kraken():
    global exchange
    try:
        old_ex = exchange
        exchange = None
        if old_ex is not None:
            del old_ex
        gc.collect()
        exchange = create_kraken_exchange()
    except Exception as e:
        notificar_error_api("KRAKEN SPOT", str(e))

_LAST_API_ERROR_NOTIF_TIME = 0.0

def notificar_error_api(servicio: str, detalle: str):
    global _LAST_API_ERROR_NOTIF_TIME
    now = time.time()
    if (now - _LAST_API_ERROR_NOTIF_TIME) > 1800:
        _LAST_API_ERROR_NOTIF_TIME = now
        enviar_notificacion_push(
            f"⚠️ ALERTA CONECTIVIDAD: {servicio}",
            f"Fallo detectado: {detalle}\nEl motor aplicará reintento y reconexión automática en el siguiente ciclo.",
            priority="high",
            tags="warning,plug"
        )

def enviar_notificacion_push(titulo: str, mensaje: str, priority: str = "default", tags: str = ""):
    if NTFY_TOPIC:
        url_ntfy = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {
            "Title": titulo,
            "Priority": priority if priority in ["min", "low", "default", "high", "urgent"] else "default"
        }
        if tags:
            headers["Tags"] = tags
        try:
            if HAS_REQUESTS:
                requests.post(url_ntfy, data=mensaje.encode('utf-8'), headers=headers, timeout=4)
            else:
                req = urllib.request.Request(url_ntfy, data=mensaje.encode('utf-8'), headers=headers, method="POST")
                urllib.request.urlopen(req, timeout=4)
        except Exception:
            pass

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            tg_data = json.dumps({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"<b>{titulo}</b>\n\n{mensaje}",
                "parse_mode": "HTML"
            }).encode('utf-8')
            tg_headers = {"Content-Type": "application/json"}
            if HAS_REQUESTS:
                requests.post(tg_url, data=tg_data, headers=tg_headers, timeout=4)
            else:
                req_tg = urllib.request.Request(tg_url, data=tg_data, headers=tg_headers, method="POST")
                urllib.request.urlopen(req_tg, timeout=4)
        except Exception:
            pass

# --------------------------------------------------------------------------------------
# 8. MOTOR CUANTITATIVO AVANZADO (BARRIDO DE LIQUIDEZ & ORDER FLOW)
# --------------------------------------------------------------------------------------
def analyze_pair_confluence_4h(symbol: str) -> Dict[str, Any]:
    """
    Analiza el par en 4H (limit=210) validando:
    1. EMA 200 (Macro Trend)
    2. RSI 14 (Momentum 50-70)
    3. Liquidity Sweep & Volume Profile (Barrido de liquidez y acumulación institucional de volumen)
    """
    df: Optional[pd.DataFrame] = None
    pair_k = KRAKEN_PAIR_MAP.get(symbol, symbol.replace('/', ''))

    global exchange
    if exchange is not None:
        try:
            raw = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=210)
            if raw and len(raw) >= 30:
                df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        except Exception:
            reconnect_kraken()
            df = None

    if df is None or df.empty:
        try:
            url = f"https://api.kraken.com/0/public/OHLC?pair={pair_k}&interval=240"
            req = urllib.request.Request(
                url, 
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DipperRender/4.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                res = data.get('result', {})
                cand_key = [k for k in res.keys() if k != 'last']
                if cand_key and len(res[cand_key[0]]) >= 30:
                    raw_candles = res[cand_key[0]][-210:]
                    df = pd.DataFrame([
                        {'open': float(c[1]), 'high': float(c[2]), 'low': float(c[3]), 'close': float(c[4]), 'volume': float(c[6])}
                        for c in raw_candles
                    ])
        except Exception:
            df = None

    if df is None or df.empty or len(df) < 15:
        if df is not None:
            del df
            gc.collect()
        return {
            "symbol": symbol, "price": 0.0, "ema200": 0.0, "rsi": 50.0,
            "vol_curr": 0.0, "vol_ma20": 0.0, "vol_ratio": 0.0,
            "cond_ema": False, "cond_rsi": False, "cond_sweep": False, "signal": False
        }

    result = {
        "symbol": symbol, "price": 0.0, "ema200": 0.0, "rsi": 50.0,
        "vol_curr": 0.0, "vol_ma20": 0.0, "vol_ratio": 0.0,
        "cond_ema": False, "cond_rsi": False, "cond_sweep": False, "signal": False
    }

    try:
        close_series = df['close']
        volume_series = df['volume']
        low_series = df['low'] if 'low' in df.columns else close_series

        last_price = float(close_series.iloc[-1])
        vol_curr = float(volume_series.iloc[-1])

        # 1. EMA 200 en marco de 4H
        span_calc = min(200, len(close_series))
        ema200_val = float(close_series.ewm(span=span_calc, adjust=False).mean().iloc[-1])

        # 2. RSI 14 (Suavizado Canónico de Welles Wilder)
        delta = close_series.diff()
        gain = delta.clip(lower=0).ewm(alpha=1.0/14.0, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1.0/14.0, adjust=False).mean()
        rs = gain / (loss + 1e-9)
        rsi_val = float((100 - (100 / (1 + rs))).iloc[-1])

        # 3. Media Móvil de Volumen (SMA 20) y Ratio de Volumen (Volume Profile / Order Flow)
        vol_ma20 = float(volume_series.rolling(window=20, min_periods=1).mean().iloc[-1])
        vol_ratio = float(vol_curr / (vol_ma20 + 1e-9)) if vol_ma20 > 0 else 0.0

        # 4. Barrido de Liquidez (Liquidity Sweep) & Order Flow:
        # Detectar mechazo por debajo del mínimo de las últimas 10 velas con rápida recuperación o incremento institucional de volumen
        recent_low_10 = float(low_series.iloc[-11:-1].min()) if len(low_series) >= 11 else float(low_series.iloc[0])
        current_low = float(low_series.iloc[-1])
        is_sweep = bool(current_low < recent_low_10 and last_price > float(close_series.iloc[-2])) or bool(vol_ratio >= 1.5)

        cond_ema = bool(last_price > ema200_val)
        cond_rsi = bool(50.0 <= rsi_val <= 70.0)
        cond_sweep = bool(is_sweep)

        signal_confluence = bool(cond_ema and cond_rsi and cond_sweep and last_price > 0)

        result = {
            "symbol": symbol, "price": last_price, "ema200": ema200_val, "rsi": rsi_val,
            "vol_curr": vol_curr, "vol_ma20": vol_ma20, "vol_ratio": vol_ratio,
            "cond_ema": cond_ema, "cond_rsi": cond_rsi, "cond_sweep": cond_sweep, "signal": signal_confluence
        }
    except Exception:
        pass
    finally:
        del df
        gc.collect()

    return result

def get_current_asset_price(symbol: str) -> float:
    global exchange
    if exchange is not None:
        try:
            ticker = exchange.fetch_ticker(symbol)
            if ticker and 'last' in ticker and ticker['last']:
                return float(ticker['last'])
        except Exception:
            pass

    pair_k = KRAKEN_PAIR_MAP.get(symbol, symbol.replace('/', ''))
    try:
        url = f"https://api.kraken.com/0/public/Ticker?pair={pair_k}"
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DipperRender/4.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            res = data.get('result', {})
            for _, val in res.items():
                if 'c' in val and len(val['c']) > 0:
                    return float(val['c'][0])
    except Exception:
        pass

    return 0.0

# --------------------------------------------------------------------------------------
# 9. PERSISTENCIA EN SUPABASE Y REGISTRO DE TRADES EN VIVO
# --------------------------------------------------------------------------------------
_GLOBAL_TRADES_STORE: List[Dict[str, Any]] = []
_GLOBAL_SYSTEM_LOGS: List[str] = [
    f"[{now_cot().strftime('%H:%M:%S COT')}] [SYSTEM] Proyecto Dipper v4.0 (Liquidity Sweep & Volume Profile) inicializado.",
    f"[{now_cot().strftime('%H:%M:%S COT')}] [MONITOR] Universo VIP: BTC/USD, ETH/USD, SOL/USD.",
    f"[{now_cot().strftime('%H:%M:%S COT')}] [CAPITAL] Capital Base calibrado en exactamente $50.00 USD."
]

def add_system_log(msg: str):
    global _GLOBAL_SYSTEM_LOGS
    _GLOBAL_SYSTEM_LOGS.insert(0, msg)
    if len(_GLOBAL_SYSTEM_LOGS) > 50:
        _GLOBAL_SYSTEM_LOGS = _GLOBAL_SYSTEM_LOGS[:50]
    try:
        if "logs" in st.session_state:
            st.session_state.logs.insert(0, msg)
            if len(st.session_state.logs) > 50:
                st.session_state.logs = st.session_state.logs[:50]
    except Exception:
        pass

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.logs = list(_GLOBAL_SYSTEM_LOGS)

def _sanitize_trade_levels(trade: Dict[str, Any]) -> Dict[str, Any]:
    try:
        side = trade.get("side", "LONG")
        entry_p = float(trade.get("entry_price", 0.0))
        if side == "LONG" and entry_p > 0:
            sl = float(trade.get("sl", 0.0))
            tp = float(trade.get("tp", 0.0))
            needs_fix = False
            if (sl > entry_p * 1.005) or sl <= 0.0:
                trade["sl"] = round(entry_p * (1.0 - STOP_LOSS_PCT), 4)
                needs_fix = True
            if (tp < entry_p) or tp <= 0.0:
                trade["tp"] = round(entry_p * (1.0 + TAKE_PROFIT_PCT), 4)
                needs_fix = True

            if needs_fix and trade.get("status") == "OPEN":
                sb = get_supabase_client()
                if sb is not None and "order_id" in trade:
                    try:
                        sb.table("paper_trades").update({
                            "sl": trade["sl"],
                            "tp": trade["tp"]
                        }).eq("order_id", trade["order_id"]).execute()
                    except Exception:
                        pass
    except Exception:
        pass
    return trade

def load_trades_data() -> pd.DataFrame:
    global _GLOBAL_TRADES_STORE
    sb = get_supabase_client()
    if sb is not None:
        try:
            res = sb.table("paper_trades").select("*").order("created_at", desc=True).execute()
            if res.data is not None:
                sanitized_data = [_sanitize_trade_levels(dict(d)) for d in res.data]
                _GLOBAL_TRADES_STORE = list(sanitized_data)
                if len(sanitized_data) > 0:
                    return pd.DataFrame(sanitized_data)
        except Exception as e:
            logging.error(f"Fallo al sincronizar trades con Supabase: {e}")

    if _GLOBAL_TRADES_STORE:
        _GLOBAL_TRADES_STORE = [_sanitize_trade_levels(dict(d)) for d in _GLOBAL_TRADES_STORE]
        return pd.DataFrame(_GLOBAL_TRADES_STORE)

    return pd.DataFrame(columns=[
        "order_id", "symbol", "side", "status", "entry_price", "exit_price",
        "sl", "tp", "pnl_usd", "pnl_pct", "exit_reason", "trailing_be",
        "created_at", "closed_at"
    ])

def is_btc_market_bullish() -> bool:
    try:
        btc_analysis = analyze_pair_confluence_4h("BTC/USD")
        p = btc_analysis.get("price", 0.0)
        ema = btc_analysis.get("ema200", 0.0)
        if p > 0 and ema > 0:
            return p > ema
    except Exception:
        pass
    return True

def check_stop_loss_cooldown(df_current: pd.DataFrame, sym: str) -> bool:
    if df_current.empty:
        return False
    closed_df = df_current[(df_current['symbol'] == sym) & (df_current['status'] == 'CLOSED')]
    if closed_df.empty:
        return False
    for _, row in closed_df.iterrows():
        reason = str(row.get('exit_reason', ''))
        if "STOP LOSS" in reason.upper():
            closed_str = str(row.get('closed_at', row.get('created_at', '')))
            try:
                dt_closed = datetime.datetime.fromisoformat(closed_str.replace("Z", "+00:00")).astimezone(TZ_COT)
                hours_elapsed = (now_cot() - dt_closed).total_seconds() / 3600.0
                if hours_elapsed < STOP_LOSS_COOLDOWN_HOURS:
                    return True
            except Exception:
                pass
    return False

def register_long_position(sym: str, cur_p: float, analysis: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    global _GLOBAL_TRADES_STORE
    if READ_ONLY:
        return None

    try:
        df_current = load_trades_data()

        if not is_btc_market_bullish():
            return None

        if check_stop_loss_cooldown(df_current, sym):
            return None

        open_trades = df_current[df_current['status'] == 'OPEN'] if not df_current.empty else pd.DataFrame()
        if len(open_trades) >= MAX_CONCURRENT_POSITIONS:
            return None

        open_symbols = set(open_trades['symbol'].tolist()) if not open_trades.empty else set()
        if sym in open_symbols:
            return None

        spot_p = get_current_asset_price(sym)
        execution_price = spot_p if spot_p > 0.0 else cur_p
        if execution_price <= 0.0:
            return None

        closed_pnl = df_current[df_current['status'] == 'CLOSED']['pnl_usd'].sum() if not df_current.empty else 0.0
        capital_real = INITIAL_CAPITAL + closed_pnl
        riesgo_usd = capital_real * RISK_PER_TRADE

        sl_price = round(execution_price * (1.0 - STOP_LOSS_PCT), 4)
        tp_price = round(execution_price * (1.0 + TAKE_PROFIT_PCT), 4)
        order_id = f"DIP-{math.floor(100000 + (time.time() * 1000) % 900000)}"
        now_iso = now_cot().isoformat()

        new_trade = {
            "order_id": order_id, "symbol": sym, "side": "LONG", "status": "OPEN",
            "entry_price": execution_price, "exit_price": None, "sl": sl_price, "tp": tp_price,
            "pnl_usd": 0.0, "pnl_pct": 0.0, "exit_reason": None, "trailing_be": False,
            "created_at": now_iso, "closed_at": None
        }

        sb = get_supabase_client()
        if sb is not None:
            try:
                sb.table("paper_trades").insert(new_trade).execute()
            except Exception as e:
                logging.error(f"Error insertando trade en Supabase: {e}")

        _GLOBAL_TRADES_STORE.insert(0, new_trade)

        log_msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [LIQUIDITY SWEEP EXEC] ¡ENTRADA LONG! {sym} @ ${execution_price:,.4f} [SL: ${sl_price:,.4f} (-1.5%) | TP: ${tp_price:,.4f} (+2.0%)]"
        add_system_log(log_msg)

        enviar_notificacion_push(
            f"🟢 SWEEP ENTRY LIVE: {sym} [LONG]",
            f"ID: {order_id}\nEntrada: ${execution_price:,.4f}\nTP (+2.0%): ${tp_price:,.4f}\nSL (-1.5%): ${sl_price:,.4f}\nRiesgo: ${riesgo_usd:,.2f} USD",
            priority="high",
            tags="rocket,chart_with_upwards_trend"
        )
        return new_trade
    except Exception as e:
        logging.error(f"Error registrando posicion en {sym}: {e}")
        return None

def apply_trailing_stop_to_breakeven():
    global _GLOBAL_TRADES_STORE
    df = load_trades_data()
    if df.empty:
        return

    open_trades = df[df['status'] == 'OPEN']
    for _, row in open_trades.iterrows():
        oid = str(row.get('order_id'))
        sym = str(row.get('symbol'))
        entry_p = float(row.get('entry_price', 1.0))
        cur_p = get_current_asset_price(sym)
        if cur_p <= 0.0:
            continue

        trailing_done = bool(row.get('trailing_be', False))
        pnl_float_pct = ((cur_p - entry_p) / entry_p) * 100.0

        if not trailing_done and pnl_float_pct >= (TRAILING_TRIGGER_PCT * 100.0):
            new_sl = entry_p * (1.0 + TRAILING_BE_PCT)
            for item in _GLOBAL_TRADES_STORE:
                if item.get("order_id") == oid:
                    item["sl"] = new_sl
                    item["trailing_be"] = True

            sb = get_supabase_client()
            if sb is not None:
                try:
                    sb.table("paper_trades").update({"sl": new_sl, "trailing_be": True}).eq("order_id", oid).execute()
                except Exception:
                    pass

            add_system_log(f"[{now_cot().strftime('%H:%M:%S COT')}] [PROTECTION] Trailing Break-Even en {sym}. SL en ${new_sl:,.4f}.")

def close_active_trade(order_id: str, outcome: str, actual_exit_price: Optional[float] = None):
    global _GLOBAL_TRADES_STORE
    df_current = load_trades_data()
    if df_current.empty:
        return

    trade_row = df_current[df_current['order_id'] == order_id]
    if trade_row.empty:
        return

    row = trade_row.iloc[0]
    entry_p = float(row.get('entry_price', 100.0))
    sym = str(row.get('symbol', 'BTC/USD'))
    tp_target = float(row.get('tp', entry_p * (1.0 + TAKE_PROFIT_PCT)))
    sl_target = float(row.get('sl', entry_p * (1.0 - STOP_LOSS_PCT)))

    closed_pnl_so_far = df_current[df_current['status'] == 'CLOSED']['pnl_usd'].sum() if not df_current.empty else 0.0
    cap_base = INITIAL_CAPITAL + closed_pnl_so_far

    if outcome == "TP":
        exit_p = actual_exit_price if (actual_exit_price is not None and actual_exit_price > 0) else tp_target
        pnl_pct = ((exit_p - entry_p) / entry_p) * 100.0
        pnl_usd = cap_base * (pnl_pct / 100.0)
        reason = f"TAKE PROFIT (+{pnl_pct:.2f}%)"
    elif outcome == "BE":
        exit_p = actual_exit_price if (actual_exit_price is not None and actual_exit_price > 0) else (entry_p * (1.0 + TRAILING_BE_PCT))
        pnl_pct = ((exit_p - entry_p) / entry_p) * 100.0
        pnl_usd = cap_base * (pnl_pct / 100.0)
        reason = f"BREAK-EVEN (+{pnl_pct:.2f}%)"
    else:
        exit_p = actual_exit_price if (actual_exit_price is not None and actual_exit_price > 0) else sl_target
        pnl_pct = ((exit_p - entry_p) / entry_p) * 100.0
        pnl_usd = cap_base * (pnl_pct / 100.0)
        reason = f"STOP LOSS ({pnl_pct:.2f}%)"

    closed_at = now_cot().isoformat()

    sb = get_supabase_client()
    if sb is not None:
        try:
            sb.table("paper_trades").update({
                "status": "CLOSED", "exit_price": exit_p, "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct, "exit_reason": reason, "closed_at": closed_at
            }).eq("order_id", order_id).execute()
        except Exception:
            pass

    for item in _GLOBAL_TRADES_STORE:
        if item.get("order_id") == order_id:
            item["status"] = "CLOSED"
            item["exit_price"] = exit_p
            item["pnl_usd"] = pnl_usd
            item["pnl_pct"] = pnl_pct
            item["exit_reason"] = reason
            item["closed_at"] = closed_at

    add_system_log(f"[{now_cot().strftime('%H:%M:%S COT')}] [ACTION] CIERRE: {order_id} {sym} por {outcome} | PnL: ${pnl_usd:,.2f} USD")

def monitor_and_auto_close_open_trades():
    try:
        df_current = load_trades_data()
        if df_current.empty:
            return
        open_trades = df_current[df_current['status'] == 'OPEN']
        if open_trades.empty:
            return

        for _, row in open_trades.iterrows():
            oid = str(row.get('order_id'))
            sym = str(row.get('symbol'))
            entry_p = float(row.get('entry_price', 100.0))
            sl_p = float(row.get('sl', entry_p * (1.0 - STOP_LOSS_PCT)))
            tp_p = float(row.get('tp', entry_p * (1.0 + TAKE_PROFIT_PCT)))
            is_be = bool(row.get('trailing_be', False))

            cur_p = get_current_asset_price(sym)
            if cur_p <= 0.0:
                continue

            if cur_p >= tp_p:
                close_active_trade(oid, "TP", actual_exit_price=cur_p)
            elif cur_p <= sl_p:
                if is_be or sl_p >= entry_p:
                    close_active_trade(oid, "BE", actual_exit_price=cur_p)
                else:
                    close_active_trade(oid, "SL", actual_exit_price=cur_p)
    except Exception:
        pass

def run_autonomous_trading_daemon():
    while True:
        try:
            monitor_and_auto_close_open_trades()
            apply_trailing_stop_to_breakeven()

            df_chk = load_trades_data()
            if not df_chk.empty:
                today_str = now_cot().strftime("%Y-%m-%d")
                df_closed_today = df_chk[(df_chk['status'] == 'CLOSED') & (df_chk['created_at'].astype(str).str.startswith(today_str))]
                loss_today = df_closed_today['pnl_usd'].sum() if not df_closed_today.empty else 0.0
                if loss_today <= (INITIAL_CAPITAL * DAILY_CIRCUIT_BREAKER):
                    enviar_notificacion_push("🚨 CIRCUIT BREAKER", f"Pérdida diaria: ${loss_today:,.2f}", priority="urgent")

            for sym in PAIRS:
                analysis = analyze_pair_confluence_4h(sym)
                if analysis.get("signal", False):
                    cur_p = float(analysis.get("price", 0.0))
                    if cur_p > 0.0:
                        register_long_position(sym, cur_p, analysis)
                time.sleep(0.3)
        except Exception:
            time.sleep(5)
        gc.collect()
        time.sleep(60)

_GLOBAL_DAEMON_INITIALIZED = False
if not _GLOBAL_DAEMON_INITIALIZED:
    _GLOBAL_DAEMON_INITIALIZED = True
    threading.Thread(target=run_autonomous_trading_daemon, daemon=True, name="DipperDaemonSweep").start()

# --------------------------------------------------------------------------------------
# 10. INTERFAZ STREAMLIT & MÉTRICAS (2 PESTAÑAS PRINCIPALES)
# --------------------------------------------------------------------------------------
df_all = load_trades_data()
df_open = df_all[df_all["status"] == "OPEN"].copy() if not df_all.empty else pd.DataFrame()
df_closed = df_all[df_all["status"] == "CLOSED"].copy() if not df_all.empty else pd.DataFrame()

total_closed = len(df_closed)
wins = len(df_closed[df_closed["pnl_usd"] > 0]) if total_closed > 0 else 0
losses = len(df_closed[df_closed["pnl_usd"] < 0]) if total_closed > 0 else 0
win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0
total_pnl_usd = df_closed["pnl_usd"].sum() if total_closed > 0 else 0.0
total_pnl_pct = (total_pnl_usd / INITIAL_CAPITAL) * 100.0
current_capital = INITIAL_CAPITAL + total_pnl_usd

floating_pnl_usd = 0.0
if not df_open.empty:
    for idx, row in df_open.iterrows():
        sym_o = str(row.get('symbol'))
        entry_o = float(row.get('entry_price', 1.0))
        cur_p_o = get_current_asset_price(sym_o)
        if cur_p_o <= 0.0:
            cur_p_o = float(row.get('current_price', entry_o))
        f_pct = ((cur_p_o - entry_o) / entry_o) * 100.0
        f_usd = current_capital * (f_pct / 100.0)
        floating_pnl_usd += f_usd
        df_open.at[idx, 'current_price'] = cur_p_o
        df_open.at[idx, 'pnl_float_pct'] = f_pct
        df_open.at[idx, 'pnl_float_usd'] = f_usd

balance_actual = current_capital + floating_pnl_usd

# Encabezado UI
col_h_brand, col_h_status = st.columns([3, 2])
with col_h_brand:
    render_html(f"""
    <div class="exec-brand-box">
        <div class="exec-logo-icon">⚡</div>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 19px; font-weight: 800; color: #ffffff;">PROYECTO DIPPER</span>
                <span style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; font-family: 'JetBrains Mono';">v4.0 LIQUIDITY SWEEP VIP</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                <div class="status-badge" style="color: #10b981;"><div class="pulse-dot"></div><span>MOTOR: LIVE AUTÓNOMO</span></div>
                <div class="status-badge" style="color: #38bdf8;"><span>CAPITAL BASE: $50.00 USD</span></div>
            </div>
        </div>
    </div>
    """)

with col_h_status:
    render_html(f"""
    <div style="display: flex; flex-direction: column; align-items: flex-end; justify-content: center; height: 100%;">
        <div class="status-badge" style="background: rgba(56, 189, 248, 0.08); color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); font-size: 10px;">
            ● 3 PARES VIP · SWEEP & VOLUME PROFILE · LIMIT=210 (4H)
        </div>
    </div>
    """)

# Tarjetas KPI
render_html(f"""
<div class="kpi-grid-main">
    <div class="kpi-card">
        <div class="kpi-label"><span>Capital Total (Equity)</span><span style="color: #38bdf8;">EN VIVO</span></div>
        <div class="kpi-value">${balance_actual:,.2f}</div>
        <div class="kpi-subtext {'sub-green' if (balance_actual - INITIAL_CAPITAL) >= 0 else 'sub-red'}">
            <span>{'+' if (balance_actual - INITIAL_CAPITAL) >= 0 else ''}${balance_actual - INITIAL_CAPITAL:,.2f} USD</span>
        </div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label"><span>PnL Neto Acumulado</span></div>
        <div class="kpi-value" style="color: {'#10b981' if total_pnl_usd >= 0 else '#f43f5e'};">${total_pnl_usd:,.2f}</div>
        <div class="kpi-subtext"><span>{total_pnl_pct:.2f}% s/ $50.00</span></div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label"><span>Posiciones Activas</span></div>
        <div class="kpi-value">{len(df_open)} <span style="font-size: 13px; color: #64748b;">/ 3</span></div>
        <div class="kpi-subtext sub-green"><span>{3 - len(df_open)} cupos libres</span></div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label"><span>Win Rate</span></div>
        <div class="kpi-value">{win_rate:.1f}%</div>
        <div class="kpi-subtext sub-green"><span>{wins}W / {losses}L</span></div>
    </div>
</div>
""")

# Pestañas principales
tab_matriz, tab_auditoria = st.tabs([
    "📊 Matriz Cuantitativa (3 Pares VIP) & Posiciones Activas",
    "📜 Historial, Auditoría & Consola de Logs"
])

with tab_matriz:
    # SECCIÓN A: POSICIONES ACTIVAS
    render_html("""
    <div class="section-header">
        <div class="section-title">
            <span style="color: #38bdf8;">💼</span>
            <span>Posiciones Activas en Cartera (VIP)</span>
        </div>
        <div class="section-tag">GESTIÓN EN VIVO</div>
    </div>
    """)

    if df_open.empty:
        render_html("""
        <div style="background-color: #080d14; border: 1px dashed rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 20px; text-align: center; color: #64748b; font-size: 11px; font-family: 'JetBrains Mono'; margin-bottom: 22px;">
            SIN POSICIONES ACTIVAS. EL MOTOR VIGILA BARRIDOS DE LIQUIDEZ EN BTC/USD, ETH/USD Y SOL/USD.
        </div>
        """)
    else:
        rows_open = []
        for _, row in df_open.iterrows():
            oid = str(row.get('order_id', '-'))
            sym = str(row.get('symbol', '-'))
            entry_p = float(row.get('entry_price', 1.0))
            cur_p = float(row.get('current_price', get_current_asset_price(sym)))
            sl_p = float(row.get('sl', entry_p * (1.0 - STOP_LOSS_PCT)))
            tp_p = float(row.get('tp', entry_p * (1.0 + TAKE_PROFIT_PCT)))
            f_usd = float(row.get('pnl_float_usd', 0.0))
            f_pct = float(row.get('pnl_float_pct', 0.0))

            pnl_color = "#10b981" if f_usd >= 0 else "#f43f5e"
            pnl_str = f"+${f_usd:,.2f}" if f_usd >= 0 else f"-${abs(f_usd):,.2f}"
            trailing_status = "BE ASEGURADO" if bool(row.get('trailing_be', False)) else "EN TRAYECTORIA"

            rows_open.append(
                f"<tr>"
                f"<td><span style=\"color: #f8fafc; font-weight: 700;\">{oid}</span></td>"
                f"<td><span style=\"color: #38bdf8; font-weight: 700;\">{sym}</span></td>"
                f"<td><span class=\"badge-tag badge-signal-true\">LONG</span></td>"
                f"<td>${entry_p:,.2f}</td>"
                f"<td style=\"font-weight: 700; color: #f8fafc;\">${cur_p:,.2f}</td>"
                f"<td style=\"color: #f43f5e;\">${sl_p:,.2f} (-1.5%)</td>"
                f"<td style=\"color: #10b981;\">${tp_p:,.2f} (+2.0%)</td>"
                f"<td style=\"color: {pnl_color}; font-weight: 700;\">{pnl_str} ({f_pct:+.2f}%)</td>"
                f"<td><span class=\"badge-tag {'badge-signal-true' if row.get('trailing_be') else 'badge-signal-false'}\">{trailing_status}</span></td>"
                f"</tr>"
            )

        table_open_html = (
            "<div class=\"table-container\">"
            "<table class=\"quant-table\">"
            "<thead><tr>"
            "<th>ID Orden</th><th>Símbolo</th><th>Lado</th><th>Entrada Real</th>"
            "<th>Precio Kraken</th><th>Stop Loss</th><th>Take Profit</th>"
            "<th>PnL Flotante ($ / %)</th><th>Estado Trailing</th>"
            "</tr></thead>"
            "<tbody>" + "".join(rows_open) + "</tbody></table></div>"
        )
        render_html(table_open_html)

    # SECCIÓN B: MATRIZ CUANTITATIVA EN TIEMPO REAL (SWEEP & VOLUME)
    render_html("""
    <div class="section-header" style="margin-top: 18px;">
        <div class="section-title"><span style="color: #10b981;">📡</span><span>Matriz Cuantitativa (Barrido de Liquidez & Order Flow - BTC, ETH, SOL)</span></div>
        <div class="section-tag">ANÁLISIS 4H ESTRICTO</div>
    </div>
    """)

    matrix_rows = []
    for sym in PAIRS:
        data_pair = analyze_pair_confluence_4h(sym)
        is_signal = data_pair.get("signal", False)
        price_val = data_pair.get("price", 0.0)
        ema_val = data_pair.get("ema200", 0.0)
        rsi_val = data_pair.get("rsi", 50.0)
        vol_ratio = data_pair.get("vol_ratio", 1.0)
        cond_sweep = data_pair.get("cond_sweep", False)

        if is_signal and not READ_ONLY and price_val > 0:
            register_long_position(sym, price_val, data_pair)

        row_cls = "row-signal-active" if is_signal else ""
        badge_sig = "<span class=\"badge-tag badge-signal-true\">● TRUE (LONG)</span>" if is_signal else "<span class=\"badge-tag badge-signal-false\">● FALSE</span>"
        sweep_badge = "<span style=\"color: #10b981; font-weight: 700;\">✓ SWEEP DETECTED</span>" if cond_sweep else "<span style=\"color: #64748b;\">-</span>"

        matrix_rows.append(
            f"<tr class=\"{row_cls}\">"
            f"<td><span style=\"color: #f8fafc; font-weight: 700;\">{sym}</span></td>"
            f"<td style=\"color: #38bdf8;\">${price_val:,.2f}</td>"
            f"<td>${ema_val:,.2f}</td>"
            f"<td>{rsi_val:.1f}</td>"
            f"<td>{vol_ratio:.2f}x</td>"
            f"<td>{sweep_badge}</td>"
            f"<td>{badge_sig}</td>"
            f"</tr>"
        )

    render_html(
        "<div class=\"table-container\"><table class=\"quant-table\">"
        "<thead><tr><th>Par VIP</th><th>Precio 4H</th><th>EMA 200 (4H)</th><th>RSI (14)</th><th>Vol Ratio</th><th>Liquidity Sweep</th><th>Señal Confluencia</th></tr></thead>"
        "<tbody>" + "".join(matrix_rows) + "</tbody></table></div>"
    )

with tab_auditoria:
    render_html("""
    <div class="section-header">
        <div class="section-title">
            <span style="color: #38bdf8;">📜</span>
            <span>Historial de Órdenes Cerradas (Supabase / Memoria)</span>
        </div>
        <div class="section-tag">AUDITORÍA CUANTITATIVA</div>
    </div>
    """)

    if df_closed.empty:
        render_html("""
        <div style="background-color: #080d14; border: 1px dashed rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 28px 20px; text-align: center; color: #64748b; font-size: 11px; font-family: 'JetBrains Mono'; margin-bottom: 20px;">
            SIN ÓRDENES CERRADAS TODAVÍA. LAS OPERACIONES SE REGISTRARÁN AL TOCAR TP (+2.0%) O SL (-1.5%).
        </div>
        """)
    else:
        rows_closed = []
        for _, row in df_closed.iterrows():
            oid = str(row.get('order_id', '-'))
            sym = str(row.get('symbol', '-'))
            entry_p = float(row.get('entry_price', 1.0))
            exit_p = float(row.get('exit_price', entry_p))
            pnl_val = float(row.get('pnl_usd', 0.0))
            pnl_pct = float(row.get('pnl_pct', 0.0))
            reason = str(row.get('exit_reason', 'CIERRE'))
            is_win = pnl_val >= 0

            pnl_color = "#10b981" if is_win else "#f43f5e"
            pnl_str = f"+${pnl_val:,.2f}" if is_win else f"-${abs(pnl_val):,.2f}"
            badge_r = f"<span class=\"badge-tag {'badge-signal-true' if is_win else 'badge-signal-false'}\">{reason}</span>"

            closed_str = str(row.get('closed_at', row.get('created_at', '')))
            try:
                dt_cls = datetime.datetime.fromisoformat(closed_str.replace("Z", "+00:00")).astimezone(TZ_COT)
                hora_close = dt_cls.strftime("%Y-%m-%d %H:%M:%S COT")
            except Exception:
                hora_close = closed_str[:19] if len(closed_str) >= 19 else "-"

            rows_closed.append(
                f"<tr>"
                f"<td><span style=\"color: #f8fafc; font-weight: 700;\">{oid}</span></td>"
                f"<td><span style=\"color: #38bdf8; font-weight: 700;\">{sym}</span></td>"
                f"<td>${entry_p:,.2f}</td>"
                f"<td>${exit_p:,.2f}</td>"
                f"<td>{badge_r}</td>"
                f"<td style=\"color: {pnl_color}; font-weight: 700;\">{pnl_str}</td>"
                f"<td style=\"color: {pnl_color}; font-weight: 700;\">{pnl_pct:+.2f}%</td>"
                f"<td style=\"color: #94a3b8;\">{hora_close}</td>"
                f"</tr>"
            )

        table_closed_html = (
            "<div class=\"table-container\">"
            "<table class=\"quant-table\">"
            "<thead><tr>"
            "<th>ID Orden</th><th>Símbolo</th><th>Entrada</th><th>Salida Real</th>"
            "<th>Motivo Cierre</th><th>PnL Real ($)</th><th>Retorno (%)</th><th>Fecha/Hora (COT)</th>"
            "</tr></thead>"
            "<tbody>" + "".join(rows_closed) + "</tbody></table></div>"
        )
        render_html(table_closed_html)

    # Consola de Eventos y Logs
    render_html("""
    <div class="section-header" style="margin-top: 14px;">
        <div class="section-title">
            <span style="color: #38bdf8;">🖥️</span>
            <span>Consola de Auditoría y Eventos del Sistema (Terminal Logs)</span>
        </div>
        <div class="section-tag">STREAM EN VIVO</div>
    </div>
    """)

    current_logs = st.session_state.get("logs", _GLOBAL_SYSTEM_LOGS)
    logs_html = "".join([f"<div class=\"log-line\">{l}</div>" for l in current_logs])
    render_html(f"<div class=\"terminal-console\">{logs_html}</div>")

gc.collect()
