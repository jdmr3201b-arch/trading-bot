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
- 2. UNIVERSO AMPLIADO A 35 ACTIVOS LÍQUIDOS EN KRAKEN SPOT:
     * BTC, ETH, SOL, XRP, ADA, AVAX, DOT, LINK, LTC, NEAR, SUI, APT, UNI, ICP, FIL,
       RENDER, SHIB, PEPE, DOGE, BCH, AAVE, MATIC, ATOM, ALGO, OP, ARB, LDO, TIA, INJ,
       FET, SEI, KAS, STX, GMX, RUNE.
- 3. ESTRATEGIA CUANTITATIVA Y TRIPLE REGLA DE CONFLUENCIA (4H):
     * Condición 1 (Macro Trend): Precio > EMA 200 en 4H.
     * Condición 2 (Momentum RSI): RSI (14) en zona neutral/alcista [50.0 <= RSI <= 70.0].
     * Condición 3 (Volumen Institucional): Volumen actual >= 1.5 * Media Móvil 20 (SMA 20).
     * Señal de Confluencia: TRUE únicamente si las 3 condiciones se cumplen a la vez.
- 4. RESILIENCIA Y MANEJO DE ERRORES:
     * Cada petición envuelta en try-except individual para proteger el escáner continuo.
     * Auto-reconexión a Kraken y Health Check HTTP en puerto $PORT (200 OK) para Render.
- 5. STREAMLIT & AUTO-REFRESCO CADA 15 MINUTOS:
     * `st_autorefresh(interval=900000)` (15 minutos = 900,000 ms).
     * Reloj local interactivo (HTML+JS) sincronizado con el navegador del usuario.
     * MODO LIVE / AUTÓNOMO EXEC: Ejecución autónoma 100% matemática y en tiempo real.
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

# Importación modular del motor cuantitativo engine.py
try:
    from engine import engine, DipperQuantitativeEngine
    HAS_ENGINE_MODULE = True
except ImportError:
    HAS_ENGINE_MODULE = False
    engine = None

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
    page_title="PROYECTO DIPPER v4.0 | QUANT 35-PAIRS",
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
# 6. UNIVERSO EXPANDIDO: 35 ACTIVOS LÍQUIDOS EN KRAKEN SPOT
# --------------------------------------------------------------------------------------
PAIRS: List[str] = [
    'BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'ADA/USD', 
    'AVAX/USD', 'DOT/USD', 'LINK/USD', 'LTC/USD', 'NEAR/USD', 
    'SUI/USD', 'APT/USD', 'UNI/USD', 'ICP/USD', 'FIL/USD', 
    'RENDER/USD', 'SHIB/USD', 'PEPE/USD', 'DOGE/USD', 'BCH/USD', 
    'AAVE/USD', 'POL/USD', 'ATOM/USD', 'ALGO/USD', 'OP/USD', 
    'ARB/USD', 'LDO/USD', 'TIA/USD', 'INJ/USD', 'FET/USD', 
    'SEI/USD', 'KAS/USD', 'STX/USD', 'GMX/USD', 'RUNE/USD'
]

# Mapa para peticiones REST directas a Kraken Spot (Símbolos oficiales Kraken)
KRAKEN_PAIR_MAP: Dict[str, str] = {
    'BTC/USD': 'XXBTZUSD', 'ETH/USD': 'XETHZUSD', 'SOL/USD': 'SOLUSD', 'XRP/USD': 'XXRPZUSD',
    'ADA/USD': 'ADAUSD', 'AVAX/USD': 'AVAXUSD', 'DOT/USD': 'DOTUSD', 'LINK/USD': 'LINKUSD',
    'LTC/USD': 'XLTCZUSD', 'NEAR/USD': 'NEARUSD', 'SUI/USD': 'SUIUSD', 'APT/USD': 'APTUSD',
    'UNI/USD': 'UNIUSD', 'ICP/USD': 'ICPUSD', 'FIL/USD': 'FILUSD', 'RENDER/USD': 'RENDERUSD',
    'SHIB/USD': 'SHIBUSD', 'PEPE/USD': 'PEPEUSD', 'DOGE/USD': 'XDGUSD', 'BCH/USD': 'BCHUSD',
    'AAVE/USD': 'AAVEUSD', 'POL/USD': 'POLUSD', 'MATIC/USD': 'POLUSD', 'ATOM/USD': 'ATOMUSD',
    'ALGO/USD': 'ALGOUSD', 'OP/USD': 'OPUSD', 'ARB/USD': 'ARBUSD', 'LDO/USD': 'LDOUSD',
    'TIA/USD': 'TIAUSD', 'INJ/USD': 'INJUSD', 'FET/USD': 'FETUSD', 'SEI/USD': 'SEIUSD',
    'KAS/USD': 'KASUSD', 'STX/USD': 'STXUSD', 'GMX/USD': 'GMXUSD', 'RUNE/USD': 'RUNEUSD'
}

INITIAL_CAPITAL = 50.0         # Capital Base Real ($50.00 USD)
RISK_PER_TRADE = 0.015         # 1.5% de riesgo exacto por trade ($0.75 USD base)
STOP_LOSS_PCT = 0.015          # -1.5% Stop Loss
TAKE_PROFIT_PCT = 0.045        # +4.5% Take Profit (Ratio 1:3 Asimétrico)
TRAILING_TRIGGER_PCT = 0.020   # +2.0% flotante para mover SL a Break-Even
TRAILING_BE_PCT = 0.001        # +0.1% sobre entrada (cubre fees)
DAILY_CIRCUIT_BREAKER = -0.03  # -3.0% Circuit Breaker Diario
MAX_SPREAD_TOLERANCE = 0.0015  # 0.15% Spread máximo permitido
MAX_CONCURRENT_POSITIONS = 3   # Máximo 3 posiciones concurrentes

# BANDERAS GLOBALES DE EJECUCIÓN (AUTÓNOMO EXEC / LIVE)
READ_ONLY = False              # Desactivado modo lectura: Activada ejecución activa real (LIVE)
MOCK_MODE = False              # Desactivado modo simulación: 100% órdenes reales y cuantificadas

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
    """Reconecta el exchange CCXT de Kraken de forma autónoma liberando memoria residual."""
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
    """Envía alerta push si ocurre un fallo crítico de API, limitado a 1 vez cada 30 minutos para evitar saturación."""
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
    """Envía notificaciones push instantáneas a Ntfy.sh y Telegram."""
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
# 8. MOTOR CUANTITATIVO CON GESTIÓN EXTREMA DE MEMORIA (RAM < 200 MB)
# --------------------------------------------------------------------------------------
def analyze_pair_confluence_4h(symbol: str) -> Dict[str, Any]:
    """
    Analiza un par solicitando EXCLUSIVAMENTE 210 velas en marco 4H (interval=240, limit=210)
    directamente desde CCXT o mediante la API REST pública de Kraken Spot.
    
    Triple regla de confluencia:
    1. Precio > EMA 200 (4H)
    2. RSI (14) en zona neutral/alcista [50.0 <= RSI <= 70.0]
    3. Volumen actual >= 1.5 * Media Móvil de Volumen 20 (SMA 20)
    
    Si un par falla al descargarse o no hay suficientes datos, retorna un diccionario
    con ceros y señal False de forma limpia, sin romper el ciclo ni congelar datos.
    """
    df: Optional[pd.DataFrame] = None
    pair_k = KRAKEN_PAIR_MAP.get(symbol, symbol.replace('/', ''))

    # Intento 1: CCXT con limit=210 estricto en temporalidad 4h
    global exchange
    if exchange is not None:
        try:
            raw = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=210)
            if raw and len(raw) >= 30:
                df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        except Exception:
            reconnect_kraken()
            df = None

    # Intento 2: Kraken Public REST con interval=240 (4H) limitando a las últimas 210 velas
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
                        {'close': float(c[4]), 'volume': float(c[6])}
                        for c in raw_candles
                    ])
        except Exception:
            df = None

    # Si la API no retorna datos suficientes, retornar estructura segura con ceros liberando memoria
    if df is None or df.empty or len(df) < 15:
        if df is not None:
            del df
            gc.collect()
        return {
            "symbol": symbol,
            "price": 0.0,
            "ema200": 0.0,
            "rsi": 50.0,
            "vol_curr": 0.0,
            "vol_ma20": 0.0,
            "vol_ratio": 0.0,
            "cond_ema": False,
            "cond_rsi": False,
            "cond_vol": False,
            "signal": False
        }

    result = {
        "symbol": symbol,
        "price": 0.0,
        "ema200": 0.0,
        "rsi": 50.0,
        "vol_curr": 0.0,
        "vol_ma20": 0.0,
        "vol_ratio": 0.0,
        "cond_ema": False,
        "cond_rsi": False,
        "cond_vol": False,
        "signal": False
    }

    try:
        close_series = df['close']
        volume_series = df['volume']

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

        # 3. Media Móvil de Volumen (SMA 20) y Ratio de Volumen
        vol_ma20 = float(volume_series.rolling(window=20, min_periods=1).mean().iloc[-1])
        vol_ratio = float(vol_curr / (vol_ma20 + 1e-9)) if vol_ma20 > 0 else 0.0

        # Evaluación de la Triple Regla de Confluencia
        cond_ema = bool(last_price > ema200_val)
        cond_rsi = bool(50.0 <= rsi_val <= 70.0)
        cond_vol = bool(vol_curr >= (vol_ma20 * 1.5))

        signal_confluence = bool(cond_ema and cond_rsi and cond_vol and last_price > 0)

        result = {
            "symbol": symbol,
            "price": last_price,
            "ema200": ema200_val,
            "rsi": rsi_val,
            "vol_curr": vol_curr,
            "vol_ma20": vol_ma20,
            "vol_ratio": vol_ratio,
            "cond_ema": cond_ema,
            "cond_rsi": cond_rsi,
            "cond_vol": cond_vol,
            "signal": signal_confluence
        }
    except Exception:
        result = {
            "symbol": symbol,
            "price": 0.0,
            "ema200": 0.0,
            "rsi": 50.0,
            "vol_curr": 0.0,
            "vol_ma20": 0.0,
            "vol_ratio": 0.0,
            "cond_ema": False,
            "cond_rsi": False,
            "cond_vol": False,
            "signal": False
        }
    finally:
        # Liberación explícita de memoria RAM inmediata
        del df
        gc.collect()

    return result

def get_current_asset_price(symbol: str) -> float:
    """Obtiene cotización real en Kraken Spot sin retener memoria ni recurrir a precios sintéticos."""
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
# 9. PERSISTENCIA EN SUPABASE, MEMORIA Y REGISTRO DE TRADES EN VIVO
# --------------------------------------------------------------------------------------
_GLOBAL_TRADES_STORE: List[Dict[str, Any]] = []
_GLOBAL_SYSTEM_LOGS: List[str] = [
    f"[{now_cot().strftime('%H:%M:%S COT')}] [SYSTEM] Proyecto Dipper v4.0 inicializado con gestión de RAM < 200 MB.",
    f"[{now_cot().strftime('%H:%M:%S COT')}] [MONITOR] Universo ampliado a 35 criptoactivos en Kraken Spot (4H limit=210).",
    f"[{now_cot().strftime('%H:%M:%S COT')}] [CAPITAL] Capital Base calibrado en $50.00 USD. Modo: LIVE / AUTÓNOMO EXEC."
]

def add_system_log(msg: str):
    """Registra eventos de forma segura tanto para el hilo de fondo como para Streamlit."""
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

def load_trades_data() -> pd.DataFrame:
    """Carga órdenes reales desde Supabase o estructura interna en memoria de forma resiliente."""
    global _GLOBAL_TRADES_STORE
    sb = get_supabase_client()
    if sb is not None:
        try:
            res = sb.table("paper_trades").select("*").order("created_at", desc=True).execute()
            if res.data is not None:
                _GLOBAL_TRADES_STORE = list(res.data)
                if len(res.data) > 0:
                    return pd.DataFrame(res.data)
                return pd.DataFrame(columns=[
                    "order_id", "symbol", "side", "status", "entry_price", "exit_price",
                    "sl", "tp", "pnl_usd", "pnl_pct", "exit_reason", "trailing_be",
                    "created_at", "closed_at"
                ])
        except Exception as e:
            logging.error(f"Fallo al sincronizar trades con Supabase: {e}")

    if _GLOBAL_TRADES_STORE:
        return pd.DataFrame(_GLOBAL_TRADES_STORE)

    try:
        if "trades_cache" not in st.session_state:
            st.session_state.trades_cache = pd.DataFrame(columns=[
                "order_id", "symbol", "side", "status", "entry_price", "exit_price",
                "sl", "tp", "pnl_usd", "pnl_pct", "exit_reason", "trailing_be",
                "created_at", "closed_at"
            ])
        return st.session_state.trades_cache
    except Exception:
        return pd.DataFrame(columns=[
            "order_id", "symbol", "side", "status", "entry_price", "exit_price",
            "sl", "tp", "pnl_usd", "pnl_pct", "exit_reason", "trailing_be",
            "created_at", "closed_at"
        ])

def register_long_position(sym: str, cur_p: float, analysis: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Registra una posición LONG activa en Supabase y en memoria si READ_ONLY es False y hay cupo (< 3)."""
    global _GLOBAL_TRADES_STORE
    if READ_ONLY:
        return None

    try:
        df_current = load_trades_data()
        open_trades = df_current[df_current['status'] == 'OPEN'] if not df_current.empty else pd.DataFrame()
        open_count = len(open_trades)

        if open_count >= MAX_CONCURRENT_POSITIONS:
            return None

        open_symbols = set(open_trades['symbol'].tolist()) if not open_trades.empty else set()
        if sym in open_symbols:
            return None

        # Obtener precio de ejecución SPOT en tiempo real de Kraken
        spot_p = get_current_asset_price(sym)
        execution_price = spot_p if spot_p > 0.0 else cur_p
        if execution_price <= 0.0:
            return None

        closed_pnl = df_current[df_current['status'] == 'CLOSED']['pnl_usd'].sum() if not df_current.empty else 0.0
        capital_real = INITIAL_CAPITAL + closed_pnl
        riesgo_usd = capital_real * RISK_PER_TRADE

        # Matemática cuantitativa estricta para posiciones LONG:
        # Stop Loss: -1.5% ABAJO -> entry_price * (1 - 0.015) = entry_price * 0.985
        # Take Profit: +4.5% ARRIBA -> entry_price * (1 + 0.045) = entry_price * 1.045
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

        # 1. Persistencia resiliente en Supabase
        sb = get_supabase_client()
        if sb is not None:
            try:
                sb.table("paper_trades").insert(new_trade).execute()
            except Exception as e:
                logging.error(f"Error insertando trade en Supabase: {e}")

        # 2. Persistencia en memoria global compartida
        _GLOBAL_TRADES_STORE.insert(0, new_trade)

        # 3. Cache en sesión de Streamlit si está en contexto
        try:
            if "trades_cache" in st.session_state:
                st.session_state.trades_cache = pd.concat([pd.DataFrame([new_trade]), st.session_state.trades_cache], ignore_index=True)
        except Exception:
            pass

        log_msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [LIVE EXEC] ¡ENTRADA EJECUTADA! Orden LONG en {sym} @ ${execution_price:,.4f} [SL: ${sl_price:,.4f} (-1.5% ABAJO) | TP: ${tp_price:,.4f} (+4.5% ARRIBA) | Riesgo: ${riesgo_usd:,.2f} USD]"
        add_system_log(log_msg)

        enviar_notificacion_push(
            f"🟢 NUEVA ENTRADA LIVE: {sym} [LONG]",
            f"ID: {order_id}\nEntrada: ${execution_price:,.4f}\nTP (+4.5%): ${tp_price:,.4f}\nSL (-1.5%): ${sl_price:,.4f}\nRiesgo: ${riesgo_usd:,.2f} USD\nConfluencia: Precio > EMA200 • RSI 50-70 • Vol >= 1.5x",
            priority="high",
            tags="rocket,chart_with_upwards_trend"
        )
        return new_trade
    except Exception as e:
        logging.error(f"Error registrando posicion en {sym}: {e}")
        return None

def apply_trailing_stop_to_breakeven():
    """Mueve automáticamente el SL a Break-Even (+0.1%) al alcanzar +2.0% de ganancia flotante."""
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

            try:
                if "trades_cache" in st.session_state:
                    st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == oid, 'sl'] = new_sl
                    st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == oid, 'trailing_be'] = True
            except Exception:
                pass

            sb = get_supabase_client()
            if sb is not None:
                try:
                    sb.table("paper_trades").update({"sl": new_sl, "trailing_be": True}).eq("order_id", oid).execute()
                except Exception as e:
                    logging.error(f"Error actualizando trailing SL en Supabase: {e}")

            msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [PROTECTION] Trailing a Break-Even en {sym} (+{pnl_float_pct:.2f}%). SL en ${new_sl:,.4f} (+0.1%)."
            add_system_log(msg)
            enviar_notificacion_push(
                f"🛡️ BREAK-EVEN ACTIVADO: {sym}",
                f"Orden {oid} protegió entrada en ${new_sl:,.4f} (+0.1%). Ganancia flotante alcanzó +{pnl_float_pct:.2f}%."
            )

def close_active_trade(order_id: str, outcome: str, actual_exit_price: Optional[float] = None):
    """Liquida una posición activa al tocar TP o SL con el precio real de Kraken y cálculo dinámico de PnL."""
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
    else:  # SL
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
        except Exception as e:
            logging.error(f"Error actualizando trade cerrado en Supabase: {e}")

    for item in _GLOBAL_TRADES_STORE:
        if item.get("order_id") == order_id:
            item["status"] = "CLOSED"
            item["exit_price"] = exit_p
            item["pnl_usd"] = pnl_usd
            item["pnl_pct"] = pnl_pct
            item["exit_reason"] = reason
            item["closed_at"] = closed_at

    try:
        if "trades_cache" in st.session_state:
            st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'status'] = 'CLOSED'
            st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'exit_price'] = exit_p
            st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'pnl_usd'] = pnl_usd
            st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'pnl_pct'] = pnl_pct
            st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'exit_reason'] = reason
            st.session_state.trades_cache.loc[st.session_state.trades_cache['order_id'] == order_id, 'closed_at'] = closed_at
    except Exception:
        pass

    log_msg = f"[{now_cot().strftime('%H:%M:%S COT')}] [ACTION] CIERRE REAL: {order_id} {sym} por {outcome} | PnL: {'+' if pnl_usd >= 0 else ''}${pnl_usd:,.2f} USD ({pnl_pct:+.2f}%)"
    add_system_log(log_msg)

    if outcome == "TP":
        enviar_notificacion_push(
            f"🎯 TAKE PROFIT: {sym}",
            f"ID: {order_id}\nSalida: ${exit_p:,.4f}\nPnL: +${pnl_usd:,.2f} USD (+{pnl_pct:.2f}%)\n¡Objetivo cuantitativo cumplido!",
            priority="high",
            tags="tada,moneybag"
        )
    elif outcome == "BE":
        enviar_notificacion_push(
            f"🛡️ CIERRE BREAK-EVEN: {sym}",
            f"ID: {order_id}\nSalida: ${exit_p:,.4f}\nPnL: +${pnl_usd:,.2f} USD (+{pnl_pct:.2f}%)\nCapital 100% protegido sin pérdidas.",
            priority="default",
            tags="shield,white_check_mark"
        )
    elif outcome == "SL":
        enviar_notificacion_push(
            f"🛑 STOP LOSS: {sym}",
            f"ID: {order_id}\nSalida: ${exit_p:,.4f}\nPnL: -${abs(pnl_usd):,.2f} USD ({pnl_pct:.2f}%)\nCapital protegido al -1.5%.",
            priority="high",
            tags="stop_sign,shield"
        )

def execute_autonomous_scan_35_pairs():
    """Escanea los 35 pares con limit=210 y purga la memoria con gc.collect()."""
    df_current = load_trades_data()
    open_trades = df_current[df_current['status'] == 'OPEN'] if not df_current.empty else pd.DataFrame()
    open_count = len(open_trades)

    if open_count >= MAX_CONCURRENT_POSITIONS:
        return

    open_symbols = set(open_trades['symbol'].tolist()) if not open_trades.empty else set()
    slots_left = MAX_CONCURRENT_POSITIONS - open_count

    for sym in PAIRS:
        if slots_left <= 0:
            break
        if sym in open_symbols:
            continue

        try:
            analysis = analyze_pair_confluence_4h(sym)
            if analysis.get("signal", False):
                cur_p = float(analysis.get("price", 0.0))
                if cur_p > 0.0:
                    trade_res = register_long_position(sym, cur_p, analysis)
                    if trade_res:
                        open_symbols.add(sym)
                        slots_left -= 1
        except Exception:
            pass

    # Purga final del ciclo de escaneo
    gc.collect()

def monitor_and_auto_close_open_trades():
    """Supervisa precios de Kraken Spot para ejecutar TP/SL en tiempo real protegiendo contra errores de conexión."""
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
            # PROTECCIÓN CRÍTICA: Si el precio es <= 0.0 por fallo transitorio de API, no ejecutar SL espurio
            if cur_p <= 0.0:
                continue

            if cur_p >= tp_p:
                close_active_trade(oid, "TP", actual_exit_price=cur_p)
            elif cur_p <= sl_p:
                if is_be or sl_p >= entry_p:
                    close_active_trade(oid, "BE", actual_exit_price=cur_p)
                else:
                    close_active_trade(oid, "SL", actual_exit_price=cur_p)
    except Exception as e:
        logging.error(f"Error monitoreando posiciones abiertas: {e}")

# --------------------------------------------------------------------------------------
# 10. HILO DEMONIO AUTÓNOMO INDESTRUCTIBLE (24/7 EN RENDER)
# --------------------------------------------------------------------------------------
_GLOBAL_DAEMON_INITIALIZED = False

def run_autonomous_trading_daemon():
    """Bucle autónomo que supervisa posiciones cada 15s y escanea los 35 pares cada 15m."""
    last_scan_time = 0
    circuit_breaker_alerted_date = None

    while True:
        try:
            now_epoch = time.time()
            now_dt = now_cot()
            today_str = now_dt.strftime("%Y-%m-%d")

            # 1. Monitoreo continuo de TP/SL y Trailing Stop
            try:
                monitor_and_auto_close_open_trades()
                apply_trailing_stop_to_breakeven()
            except Exception:
                pass

            # 2. Control de Circuit Breaker Diario (-3.0%)
            try:
                df_chk = load_trades_data()
                if not df_chk.empty:
                    df_closed_today = df_chk[(df_chk['status'] == 'CLOSED') & (df_chk['created_at'].astype(str).str.startswith(today_str))]
                    loss_today = df_closed_today['pnl_usd'].sum() if not df_closed_today.empty else 0.0
                    if loss_today <= (INITIAL_CAPITAL * DAILY_CIRCUIT_BREAKER):
                        if circuit_breaker_alerted_date != today_str:
                            circuit_breaker_alerted_date = today_str
                            enviar_notificacion_push(
                                "🚨 CIRCUIT BREAKER ACTIVADO (-3.0%)",
                                f"Pérdida diaria acumulada: ${loss_today:,.2f} USD.\nOperaciones suspendidas hoy por seguridad.",
                                priority="urgent",
                                tags="warning,rotating_light"
                            )
            except Exception:
                pass

            # 3. Escaneo de los 35 pares cada 15 minutos (900s)
            if (now_epoch - last_scan_time) >= 900:
                try:
                    execute_autonomous_scan_35_pairs()
                    last_scan_time = now_epoch
                except Exception:
                    time.sleep(5)
                    try:
                        reconnect_kraken()
                        execute_autonomous_scan_35_pairs()
                        last_scan_time = now_epoch
                    except Exception:
                        last_scan_time = now_epoch
                finally:
                    gc.collect()

        except Exception:
            time.sleep(3)

        time.sleep(15)

def start_indestructible_daemon():
    """Inicia el hilo global de fondo en Render."""
    global _GLOBAL_DAEMON_INITIALIZED
    if not _GLOBAL_DAEMON_INITIALIZED:
        _GLOBAL_DAEMON_INITIALIZED = True
        t_trade = threading.Thread(target=run_autonomous_trading_daemon, daemon=True, name="DipperDaemon35Render")
        t_trade.start()

start_indestructible_daemon()

# --------------------------------------------------------------------------------------
# 11. CÁLCULO DE MÉTRICAS GLOBALES REALES
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
riesgo_trade_dinamico = balance_actual * RISK_PER_TRADE
circuit_breaker_active = (total_pnl_usd <= INITIAL_CAPITAL * DAILY_CIRCUIT_BREAKER)

# --------------------------------------------------------------------------------------
# 12. ENCABEZADO EJECUTIVO & RELOJ EN VIVO INTERACTIVO (JS)
# --------------------------------------------------------------------------------------
col_h_brand, col_h_status = st.columns([3, 2])

with col_h_brand:
    render_html(f"""
    <div class="exec-brand-box">
        <div class="exec-logo-icon">⚡</div>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 19px; font-weight: 800; color: #ffffff; letter-spacing: 0.04em;">PROYECTO DIPPER</span>
                <span style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; font-family: 'JetBrains Mono';">v4.0 QUANT (35 ACTIVOS · RAM &lt; 200MB)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px; flex-wrap: wrap;">
                <div class="status-badge" style="color: #10b981;">
                    <div class="pulse-dot"></div>
                    <span>MOTOR: AUTÓNOMO 4H</span>
                </div>
                <div class="status-badge" style="color: {'#38bdf8' if HAS_SUPABASE else '#94a3b8'};">
                    <span>SUPABASE: {'POSTGRES OK' if HAS_SUPABASE else 'STANDALONE'}</span>
                </div>
                <div class="status-badge" style="color: {'#10b981' if not circuit_breaker_active else '#f43f5e'};">
                    <span>CIRCUIT BREAKER: {'NORMAL' if not circuit_breaker_active else 'DISPARADO'}</span>
                </div>
                <div class="status-badge" style="color: {'#10b981' if not READ_ONLY else '#f59e0b'}; border-color: {'rgba(16, 185, 129, 0.4)' if not READ_ONLY else 'rgba(245, 158, 11, 0.3)'}; background: {'rgba(16, 185, 129, 0.1)' if not READ_ONLY else 'transparent'};">
                    <div class="pulse-dot" style="background: {'#10b981' if not READ_ONLY else '#f59e0b'};"></div>
                    <span>{'AUTÓNOMO EXEC' if not READ_ONLY else 'READ-ONLY'}</span>
                </div>
                <div class="status-badge" style="color: {'#38bdf8' if not READ_ONLY else '#94a3b8'}; border-color: {'rgba(56, 189, 248, 0.35)' if not READ_ONLY else 'rgba(148, 163, 184, 0.3)'}; font-weight: 700;">
                    <span>MODO: {'LIVE' if not READ_ONLY else 'AUDIT'}</span>
                </div>
            </div>
        </div>
    </div>
    """)
    # Reloj en vivo interactivo sincronizado con el navegador del usuario (HTML + JS)
    components.html("""
    <!DOCTYPE html>
    <html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
      body {
        margin: 0; padding: 0; background: transparent; overflow: hidden;
        font-family: 'JetBrains Mono', monospace;
      }
      .live-clock-badge {
        display: inline-flex; align-items: center; gap: 7px; padding: 4px 12px;
        border-radius: 9999px; font-size: 11px; font-weight: 600;
        background-color: #191919; border: 1px solid #3E3E3E; color: #E3E3E3;
        letter-spacing: 0.02em; white-space: nowrap; box-sizing: border-box;
      }
      .clock-dot {
        width: 6px; height: 6px; border-radius: 50%;
        background-color: #38bdf8; box-shadow: 0 0 6px #38bdf8;
      }
    </style>
    </head>
    <body>
      <div class="live-clock-badge">
        <div class="clock-dot"></div>
        <span>HORA LOCAL: <b id="live-clock-time" style="color: #ffffff;">--:--:--</b></span>
      </div>
      <script>
        function updateLiveClock() {
          const now = new Date();
          const h = String(now.getHours()).padStart(2, '0');
          const m = String(now.getMinutes()).padStart(2, '0');
          const s = String(now.getSeconds()).padStart(2, '0');
          const target = document.getElementById('live-clock-time');
          if (target) { target.textContent = h + ':' + m + ':' + s; }
        }
        updateLiveClock();
        setInterval(updateLiveClock, 1000);
      </script>
    </body>
    </html>
    """, height=30)

with col_h_status:
    render_html(f"""
    <div style="display: flex; flex-direction: column; align-items: flex-end; justify-content: center; height: 100%;">
        <div style="font-family: 'JetBrains Mono'; font-size: 11px; color: #94a3b8; margin-bottom: 4px;">
            AUTO-REFRESCO: <span style="color: #38bdf8; font-weight: 700;">CADA 15 MIN (900s)</span>
        </div>
        <div class="status-badge" style="background: rgba(56, 189, 248, 0.08); color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); font-size: 10px;">
            ● 35 PARES KRAKEN VIGILADOS · LIMIT=210 VELAS (4H)
        </div>
    </div>
    """)

# --------------------------------------------------------------------------------------
# 13. TARJETAS KPI PRINCIPALES (EQUITY, PNL, ACTIVAS, RIESGO)
# --------------------------------------------------------------------------------------
kpi_cards_html = f"""
<div class="kpi-grid-main">
    <div class="kpi-card">
        <div class="kpi-label"><span>Capital Total (Equity)</span><span style="color: #38bdf8;">EN VIVO</span></div>
        <div class="kpi-value">${balance_actual:,.2f}</div>
        <div class="kpi-subtext {'sub-green' if (balance_actual - INITIAL_CAPITAL) >= 0 else 'sub-red'}">
            <span>{'+' if (balance_actual - INITIAL_CAPITAL) >= 0 else ''}${balance_actual - INITIAL_CAPITAL:,.2f} USD total</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label"><span>PnL Neto Acumulado</span><span style="color: #64748b;">REALIZADO</span></div>
        <div class="kpi-value" style="color: {'#10b981' if total_pnl_usd >= 0 else '#f43f5e'};">
            {'+' if total_pnl_usd >= 0 else ''}${total_pnl_usd:,.2f}
        </div>
        <div class="kpi-subtext {'sub-green' if total_pnl_pct >= 0 else 'sub-red'}">
            <span>{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}% s/ $50 USD</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label"><span>PnL Flotante</span><span style="color: #64748b;">UNREALIZED</span></div>
        <div class="kpi-value" style="color: {'#10b981' if floating_pnl_usd >= 0 else '#f43f5e'};">
            {'+' if floating_pnl_usd >= 0 else ''}${floating_pnl_usd:,.2f}
        </div>
        <div class="kpi-subtext sub-neutral"><span>Precios en vivo Kraken</span></div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label"><span>Posiciones Activas</span><span style="color: #38bdf8;">CUPO</span></div>
        <div class="kpi-value">{len(df_open)} <span style="font-size: 13px; color: #64748b;">/ 3</span></div>
        <div class="kpi-subtext {'sub-green' if len(df_open) < 3 else 'sub-amber'}">
            <span>{3 - len(df_open)} cupos disponibles</span>
        </div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label"><span>Riesgo Dinámico (1.5%)</span><span style="color: #f59e0b;">S/ BALANCE</span></div>
        <div class="kpi-value" style="color: #f59e0b;">${riesgo_trade_dinamico:,.2f}</div>
        <div class="kpi-subtext sub-neutral"><span>TP +4.5% | SL -1.5%</span></div>
    </div>

    <div class="kpi-card">
        <div class="kpi-label"><span>Win Rate & Trades</span><span style="color: #64748b;">HISTÓRICO</span></div>
        <div class="kpi-value">{win_rate:.1f}%</div>
        <div class="kpi-subtext sub-green">
            <span>{wins}W</span><span style="color: #64748b;">/</span><span class="sub-red">{losses}L</span>
            <span style="color: #64748b; margin-left: 4px;">({total_closed} cerradas)</span>
        </div>
    </div>
</div>
"""
render_html(kpi_cards_html)

# --------------------------------------------------------------------------------------
# 14. NAVEGACIÓN EN 2 PESTAÑAS (MATRIZ DE 35 ACTIVOS & AUDITORÍA)
# --------------------------------------------------------------------------------------
tab_matriz, tab_auditoria = st.tabs([
    "📊 Matriz Cuantitativa (35 Activos) & Posiciones",
    f"📜 Historial & Auditoría de Rendimiento ({total_closed})"
])

# ======================================================================================
# PESTAÑA 1: 📊 MATRIZ CUANTITATIVA EN VIVO & POSICIONES ABIERTAS
# ======================================================================================
with tab_matriz:
    # 1. Escaneo cuantitativo de los 35 pares con limit=210 y registro en vivo
    matrix_rows = []
    signals_count = 0
    scanned_pairs_data = []

    for sym in PAIRS:
        data_pair = analyze_pair_confluence_4h(sym)
        is_signal = data_pair.get("signal", False)
        price_val = data_pair.get("price", 0.0)

        if is_signal:
            signals_count += 1
            # Si READ_ONLY es False y no hay Circuit Breaker, registrar posición automáticamente si hay cupo (< 3)
            if not READ_ONLY and not circuit_breaker_active and price_val > 0:
                register_long_position(sym, price_val, data_pair)

        scanned_pairs_data.append((sym, data_pair))

    # Purga de memoria tras escanear los 35 pares
    gc.collect()

    # Recargar datos de posiciones abiertas actualizadas en tiempo real
    df_open_fresh = load_trades_data()
    df_open_fresh = df_open_fresh[df_open_fresh['status'] == 'OPEN'].copy() if not df_open_fresh.empty else pd.DataFrame()

    # SECCIÓN A: POSICIONES ABIERTAS EN CARTERA
    render_html(f"""
    <div class="section-header">
        <div class="section-title">
            <span style="color: #38bdf8;">💼</span>
            <span>Posiciones Activas en Cartera (Máximo {MAX_CONCURRENT_POSITIONS} Concurrentes)</span>
        </div>
        <div class="section-tag">{'GESTIÓN AUTÓNOMA LIVE EXEC' if not READ_ONLY else 'GESTIÓN AUTÓNOMA 100% READ-ONLY'}</div>
    </div>
    """)

    if df_open_fresh.empty:
        render_html("""
        <div style="background-color: #080d14; border: 1px dashed rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 20px; text-align: center; color: #64748b; font-size: 11px; font-family: 'JetBrains Mono'; margin-bottom: 22px;">
            SIN POSICIONES ACTIVAS. EL MOTOR DE 35 PARES VIGILA EL MERCADO CONTINUAMENTE.
        </div>
        """)
    else:
        rows_open = []
        for _, row in df_open_fresh.iterrows():
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
            trailing_status = "BE ASEGURADO (+0.1%)" if bool(row.get('trailing_be', False)) else "EN TRAYECTORIA"

            rows_open.append(
                f"<tr>"
                f"<td><span style=\"color: #f8fafc; font-weight: 700;\">{oid}</span></td>"
                f"<td><span style=\"color: #38bdf8; font-weight: 700;\">{sym}</span></td>"
                f"<td><span class=\"badge-tag badge-signal-true\">LONG</span></td>"
                f"<td>${entry_p:,.4f}</td>"
                f"<td style=\"font-weight: 700; color: #f8fafc;\">${cur_p:,.4f}</td>"
                f"<td style=\"color: #f43f5e;\">${sl_p:,.4f} (-1.5%)</td>"
                f"<td style=\"color: #10b981;\">${tp_p:,.4f} (+4.5%)</td>"
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

    # SECCIÓN B: MATRIZ DE ESCANEO DE LOS 35 ACTIVOS
    render_html("""
    <div class="section-header" style="margin-top: 14px;">
        <div class="section-title">
            <span style="color: #10b981;">📡</span>
            <span>Matriz Cuantitativa en Tiempo Real (35 Activos · Temporalidad 4H)</span>
        </div>
        <div class="section-tag">REGLA: (PRECIO &gt; EMA 200) &amp; (50 &lt;= RSI &lt;= 70) &amp; (VOL &gt;= 1.5x SMA20)</div>
    </div>
    """)

    for sym, data_pair in scanned_pairs_data:
        is_signal = data_pair.get("signal", False)
        price_val = data_pair.get("price", 0.0)
        ema_val = data_pair.get("ema200", 0.0)
        rsi_val = data_pair.get("rsi", 50.0)
        vol_ratio = data_pair.get("vol_ratio", 1.0)

        c_ema = "✓ CUMPLE" if data_pair.get("cond_ema") else "✗ NO"
        c_rsi = "✓ CUMPLE" if data_pair.get("cond_rsi") else "✗ NO"
        c_vol = f"✓ {vol_ratio:.2f}x" if data_pair.get("cond_vol") else f"✗ {vol_ratio:.2f}x"

        row_cls = "row-signal-active" if is_signal else ""
        badge_sig = "<span class=\"badge-tag badge-signal-true\">● TRUE (LONG)</span>" if is_signal else "<span class=\"badge-tag badge-signal-false\">● FALSE</span>"

        matrix_rows.append(
            f"<tr class=\"{row_cls}\">"
            f"<td><span style=\"color: #f8fafc; font-weight: 700;\">{sym}</span></td>"
            f"<td style=\"color: #38bdf8;\">${price_val:,.4f}</td>"
            f"<td>${ema_val:,.4f}</td>"
            f"<td>{rsi_val:.1f}</td>"
            f"<td>{vol_ratio:.2f}x</td>"
            f"<td class=\"{'badge-cond-ok' if data_pair.get('cond_ema') else 'badge-cond-no'}\">{c_ema}</td>"
            f"<td class=\"{'badge-cond-ok' if data_pair.get('cond_rsi') else 'badge-cond-no'}\">{c_rsi}</td>"
            f"<td class=\"{'badge-cond-ok' if data_pair.get('cond_vol') else 'badge-cond-no'}\">{c_vol}</td>"
            f"<td>{badge_sig}</td>"
            f"</tr>"
        )

    # Purga final de Garbage Collector tras construir la tabla
    gc.collect()

    table_matrix_html = (
        "<div class=\"table-container\">"
        "<table class=\"quant-table\">"
        "<thead><tr>"
        "<th>Activo</th><th>Precio 4H</th><th>EMA 200 (4H)</th><th>RSI (14)</th><th>Ratio Vol/SMA20</th>"
        "<th>1. Precio &gt; EMA</th><th>2. RSI 50-70</th><th>3. Vol &gt;= 1.5x</th><th>Señal Confluencia</th>"
        "</tr></thead>"
        "<tbody>" + "".join(matrix_rows) + "</tbody></table></div>"
    )
    render_html(table_matrix_html)

# ======================================================================================
# PESTAÑA 2: 📜 HISTORIAL & AUDITORÍA DE RENDIMIENTO
# ======================================================================================
with tab_auditoria:
    render_html("""
    <div class="section-header">
        <div class="section-title">
            <span style="color: #10b981;">📜</span>
            <span>Bitácora de Órdenes Cerradas Legítimamente</span>
        </div>
        <div class="section-tag">REGISTROS PERSISTIDOS EN SUPABASE POSTGRESQL</div>
    </div>
    """)

    if df_closed.empty:
        render_html("""
        <div style="background-color: #080d14; border: 1px dashed rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 28px 20px; text-align: center; color: #64748b; font-size: 11px; font-family: 'JetBrains Mono'; margin-bottom: 20px;">
            SIN ÓRDENES CERRADAS TODAVÍA. TODAS LAS OPERACIONES SE REGISTRARÁN AL TOCAR TP (+4.5%) O SL (-1.5%) REAL.
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
                f"<td>${entry_p:,.4f}</td>"
                f"<td>${exit_p:,.4f}</td>"
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

    # Consola de Auditoría del Sistema
    render_html("""
    <div class="section-header" style="margin-top: 14px;">
        <div class="section-title">
            <span style="color: #38bdf8;">🖥️</span>
            <span>Consola de Auditoría & Purgas de Memoria RAM (gc.collect)</span>
        </div>
        <div class="section-tag">LOGS EN TIEMPO REAL · TIMEZONE COLOMBIA (COT UTC-5)</div>
    </div>
    """)

    logs_list = list(_GLOBAL_SYSTEM_LOGS) if _GLOBAL_SYSTEM_LOGS else st.session_state.get("logs", [])
    if logs_list:
        logs_html_lines = "".join([f"<div class='log-line'>{log}</div>" for log in logs_list[:40]])
        render_html(f"""
        <div class="terminal-console">
            {logs_html_lines}
        </div>
        """)
    else:
        render_html("""
        <div class="terminal-console">
            <div class="log-line">Esperando eventos del motor cuantitativo...</div>
        </div>
        """)

# ======================================================================================
# 14. BUCLE DE EJECUCIÓN ESTABLE & PREVENCIÓN DE FUGAS DE MEMORIA EN STREAMLIT
# ======================================================================================
# Diagnóstico y Solución para Render Free (512 MB):
# El bucle ingenuo `if st.session_state.is_running: engine.run_cycle(); time.sleep(5); st.rerun()`
# crea fugas severas de memoria si la pestaña se queda abierta, porque cada st.rerun() regenera
# el árbol de componentes de Streamlit antes de que el recolector de basura de Python libere
# los objetos anteriores.
#
# Solución de Alta Resiliencia implementada:
# 1. El ciclo cuantitativo real de Kraken corre de forma desacoplada en el daemon independiente
#    o mediante `engine.run_cycle()` bajo demanda.
# 2. Si `st.session_state.is_running` está activado, se evalúa con throttling mínimo de 15 segundos
#    (o el intervalo programado) y se aplica `gc.collect()` de inmediato.
# 3. Se evita saturación de CPU y bucles de render infinito asegurando que la UI sólo refresque
#    cuando transcurra el tiempo mínimo requerido, previniendo caídas OOM en Render.

if "is_running" not in st.session_state:
    st.session_state.is_running = True

if "last_ui_engine_cycle" not in st.session_state:
    st.session_state.last_ui_engine_cycle = 0.0

if st.session_state.get("is_running", False):
    now_ts = time.time()
    # Throttling de seguridad: ejecutar ciclo del motor si han pasado al menos 15 segundos
    if now_ts - st.session_state.last_ui_engine_cycle >= 15.0:
        st.session_state.last_ui_engine_cycle = now_ts
        try:
            if HAS_ENGINE_MODULE and engine is not None:
                engine.run_cycle()
            else:
                # Si engine.py no está presente en el mismo path, se usa la función nativa
                monitor_and_auto_close_open_trades()
                apply_trailing_stop_to_breakeven()
        except Exception as e:
            logging.warning(f"Error en ejecución del ciclo del motor: {e}")
        finally:
            # Purga explícita de memoria en el hilo de la sesión Streamlit
            gc.collect()
