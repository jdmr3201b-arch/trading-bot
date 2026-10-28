# -*- coding: utf-8 -*-
"""
========================================================================================
PROYECTO DIPPER v4.1 | QUANT EXECUTIVE TERMINAL (REFACTOR: CONCURRENCIA, VELAS CERRADAS, SIZING)
========================================================================================
Cambios respecto a v4.0 (auditoría técnica):
- 1. CONCURRENCIA:
     * El motor vive en un singleton `DipperEngine` creado con `@st.cache_resource`:
       un único hilo demonio por proceso, sin importar cuántos reruns haga Streamlit.
     * Toda mutación de posiciones ocurre bajo `threading.RLock`. `register_long_position`
       reserva la posición en memoria de forma atómica ANTES de escribir en Supabase.
     * La UI es solo lectura: ya no abre posiciones ni consulta Kraken.
     * order_id = UUID corto (sin colisiones). Se recomienda un índice único parcial en
       Supabase (ver SQL al final del archivo) como segunda barrera.
- 2. MOTOR CUANTITATIVO:
     * Todo se calcula sobre la ÚLTIMA VELA CERRADA (equivale a `iloc[-2]`): cero repainting.
     * Barrido de liquidez estricto: ruptura del mínimo previo AND cierre de recuperación
       sobre ese mínimo AND vela alcista AND volumen >= 1.5x SMA20.
     * 720 velas 4H (máximo de Kraken) para que la EMA 200 converja.
     * Una sola entrada por vela cerrada y par (evita reentradas inmediatas tras un TP).
- 3. RIESGO:
     * Tamaño = (equity * 1.5%) / SL%, limitado por caja libre y por tope por posición.
     * Circuit breaker diario (-3%) BLOQUEA nuevas entradas (por `closed_at`, hora COT).
     * Comisiones simuladas (SIM_FEE_PER_SIDE) y filtro de spread (MAX_SPREAD_TOLERANCE).
- 4. RESILIENCIA:
     * Sin `except: pass` en llamadas críticas: todo fallo va a `add_system_log` (con
       antispam y redacción de secretos). Escrituras fallidas a Supabase se reintentan.
     * Si Supabase está configurado pero no se pudo cargar el estado, NO se abren posiciones.
- 5. CONTROL: interruptor de emergencia `operating_mode` (ACTIVO / SOLO_GESTIÓN).
========================================================================================
"""

import os
import sys
import gc
import time
import math
import json
import uuid
import logging
import datetime
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any, Tuple, List, Callable

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
    page_title="PROYECTO DIPPER v4.1 | LIQUIDITY SWEEP VIP",
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
# 4. VARIABLES DE ENTORNO, PARÁMETROS FINANCIEROS Y UNIVERSO EXCLUSIVO (TOP 3 VIP)
# --------------------------------------------------------------------------------------
KRAKEN_API_KEY: str = os.getenv("KRAKEN_API_KEY", "").strip()
KRAKEN_SECRET_KEY: str = os.getenv("KRAKEN_SECRET_KEY", "").strip()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "PROYECTO_DIPPER_BOT_ALERTAS").strip()
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

SUPABASE_CONFIGURED: bool = bool(SUPABASE_LIB and SUPABASE_URL and SUPABASE_KEY)

PAIRS: List[str] = ['BTC/USD', 'ETH/USD', 'SOL/USD']

KRAKEN_PAIR_MAP: Dict[str, str] = {
    'BTC/USD': 'XXBTZUSD',
    'ETH/USD': 'XETHZUSD',
    'SOL/USD': 'SOLUSD'
}

INITIAL_CAPITAL = 50.00        # Capital Base Real exacto ($50.00 USD)
RISK_PER_TRADE = 0.015         # 1.5% de riesgo por trade (sobre el equity realizado)
STOP_LOSS_PCT = 0.015          # -1.5% Stop Loss Rígido
TAKE_PROFIT_PCT = 0.020        # +2.0% Take Profit
TRAILING_TRIGGER_PCT = 0.020   # Umbral para mover el SL a Break-Even
TRAILING_BE_PCT = 0.001        # +0.1% sobre entrada para el SL en Break-Even
STOP_LOSS_COOLDOWN_HOURS = 4   # 4 horas de cooldown tras cierre en Stop Loss
DAILY_CIRCUIT_BREAKER = -0.03  # -3.0% Circuit Breaker Diario (bloquea nuevas entradas)
MAX_SPREAD_TOLERANCE = 0.0015  # 0.15% Spread máximo permitido para entrar
MAX_CONCURRENT_POSITIONS = 3   # Máximo 3 posiciones concurrentes (1 por activo)

# --- Sizing ---------------------------------------------------------------------------
# Exposición = (equity * RISK_PER_TRADE) / STOP_LOSS_PCT, limitada por:
#   (a) caja libre (spot sin apalancamiento) y
#   (b) un tope por posición como fracción del equity.
# NOTA: con RISK_PER_TRADE == STOP_LOSS_PCT la fórmula pura da 100% del equity por trade.
# Con el tope de 1/3 se pueden tener 3 posiciones, pero el riesgo real por trade baja a ~0.5%.
# Si prefieres arriesgar 1.5% reales, pon MAX_POSITION_PCT_OF_EQUITY=1.0 (en la práctica 1 posición).
MAX_POSITION_PCT_OF_EQUITY = float(os.getenv("MAX_POSITION_PCT_OF_EQUITY", str(1.0 / 3.0)))
MIN_POSITION_USD = float(os.getenv("MIN_POSITION_USD", "10.0"))   # Mínimo operativo aprox. (ajústalo al mínimo de orden de Kraken)
SIM_FEE_PER_SIDE = float(os.getenv("SIM_FEE_PER_SIDE", "0.0040")) # Comisión taker simulada por lado (verifica tu tier). 0.0 = sin comisiones.

# --- Motor cuantitativo ---------------------------------------------------------------
OHLCV_LIMIT = 720              # Máximo de Kraken: la EMA 200 converge sin sesgo inicial
MIN_CANDLES_FOR_EMA = 250      # Mínimo de velas cerradas para considerar válida la EMA 200
SWEEP_LOOKBACK = 10            # Mínimo previo de las últimas 10 velas
VOL_RATIO_MIN = 1.5            # Volumen >= 1.5x SMA20
CANDLE_MS = 4 * 60 * 60 * 1000

# --- Ciclos del daemon ----------------------------------------------------------------
MONITOR_INTERVAL_SEC = 30      # Chequeo de SL/TP
ANALYSIS_INTERVAL_SEC = 120    # Refresco del análisis 4H (solo cambia al cerrar vela)

# --- Modo operativo (interruptor de emergencia) ---------------------------------------
MODE_ACTIVE = "ACTIVO"                 # Abre y gestiona posiciones
MODE_MANAGE_ONLY = "SOLO_GESTIÓN"      # NO abre nuevas posiciones; sigue cerrando SL/TP
OPERATING_MODES = [MODE_ACTIVE, MODE_MANAGE_ONLY]
_env_mode = os.getenv("OPERATING_MODE", MODE_ACTIVE).strip()
DEFAULT_OPERATING_MODE = _env_mode if _env_mode in OPERATING_MODES else MODE_ACTIVE

# Columnas de la tabla `paper_trades`
BASE_COLS = [
    "order_id", "symbol", "side", "status", "entry_price", "exit_price", "sl", "tp",
    "pnl_usd", "pnl_pct", "exit_reason", "trailing_be", "created_at", "closed_at"
]
EXTRA_COLS = ["position_usd", "fees_usd"]   # Requieren migración (SQL al final del archivo)
ALL_COLS = BASE_COLS + EXTRA_COLS

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DipperRender/4.1"}


def _redact(text: str) -> str:
    """Oculta secretos en mensajes de error antes de enviarlos a logs/UI."""
    out = str(text)
    for secret in (TELEGRAM_BOT_TOKEN, KRAKEN_API_KEY, KRAKEN_SECRET_KEY, SUPABASE_KEY):
        if secret and len(secret) >= 6:
            out = out.replace(secret, "***")
    return out


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        f = float(value)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> Optional[datetime.datetime]:
    """Parsea ISO-8601 a datetime en COT. Devuelve None si no se puede."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("none", "nan", "nat"):
        return None
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_COT)
        return dt.astimezone(TZ_COT)
    except ValueError:
        return None


# --------------------------------------------------------------------------------------
# 5. MOTOR SINGLETON: UN SOLO HILO, ESTADO PROTEGIDO POR LOCK
# --------------------------------------------------------------------------------------
class DipperEngine:
    """
    Estado + lógica de trading. Se instancia UNA vez por proceso (st.cache_resource).
    - `self.trades` es la fuente de verdad en memoria; Supabase es persistencia write-through.
    - Solo el hilo del daemon toca Kraken; la UI lee cachés (precios y análisis).
    """

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

        self.trades: List[Dict[str, Any]] = []
        self.logs: List[str] = []
        self.analysis_cache: Dict[str, Dict[str, Any]] = {}
        self.price_cache: Dict[str, float] = {}
        self.last_entry_candle: Dict[str, int] = {}

        self.exchange: Optional[Any] = None
        self.supabase: Optional[Any] = None
        self.pending_writes: List[Tuple[str, Callable[[Any], None]]] = []
        self.extra_cols_ok = True
        self.hydrated = False

        self.operating_mode = DEFAULT_OPERATING_MODE
        self.last_cycle_ts = 0.0
        self.last_analysis_ts = 0.0
        self.cycle_count = 0

        self._err_last: Dict[str, float] = {}
        self._last_api_notif = 0.0
        self._last_reconnect = 0.0
        self._breaker_notified_day: Optional[str] = None
        self._breaker_blocked_logged_day: Optional[str] = None

        self.log("SYSTEM", "Proyecto Dipper v4.1 (velas cerradas · sizing por riesgo) inicializado.")
        self.log("MONITOR", "Universo VIP: BTC/USD, ETH/USD, SOL/USD.")
        self.log("CAPITAL", f"Capital Base calibrado en exactamente ${INITIAL_CAPITAL:,.2f} USD.")
        if not SUPABASE_CONFIGURED:
            self.log("WARNING", "Supabase NO configurado: el estado vive solo en memoria y se perderá al reiniciar.")
        self.exchange = self._create_exchange()

    # ------------------------------------------------------------------ logging
    def log(self, tag: str, msg: str) -> None:
        line = f"[{now_cot().strftime('%H:%M:%S COT')}] [{tag}] {msg}"
        with self.lock:
            self.logs.insert(0, line)
            if len(self.logs) > 50:
                del self.logs[50:]

    def log_error(self, ctx: str, exc: BaseException, notify: bool = False, throttle_sec: float = 600.0) -> None:
        """Registra un fallo en logs del sistema (con antispam y sin secretos)."""
        detail = _redact(f"{type(exc).__name__}: {exc}")
        key = f"{ctx}|{detail[:80]}"
        now = time.time()
        if now - self._err_last.get(key, 0.0) < throttle_sec:
            return
        self._err_last[key] = now
        if len(self._err_last) > 200:
            self._err_last.clear()
        logging.error("%s -> %s", ctx, detail)
        self.log("ERROR", f"{ctx}: {detail[:220]}")
        if notify:
            self.notify_api_error(ctx, detail)

    # ------------------------------------------------------------ notificaciones
    def notify_api_error(self, servicio: str, detalle: str) -> None:
        now = time.time()
        if now - self._last_api_notif > 1800:
            self._last_api_notif = now
            self.notify(
                f"⚠️ ALERTA CONECTIVIDAD: {servicio}",
                f"Fallo detectado: {detalle}\nEl motor reintentará en el siguiente ciclo.",
                priority="high", tags="warning,plug"
            )

    def notify(self, titulo: str, mensaje: str, priority: str = "default", tags: str = "") -> None:
        if NTFY_TOPIC:
            headers = {
                "Title": titulo.encode("latin-1", "ignore").decode("latin-1").strip() or "DIPPER",   # headers HTTP: solo latin-1 (los emojis van en Tags)
                "Priority": priority if priority in ["min", "low", "default", "high", "urgent"] else "default"
            }
            if tags:
                headers["Tags"] = tags
            try:
                url = f"https://ntfy.sh/{NTFY_TOPIC}"
                if HAS_REQUESTS:
                    requests.post(url, data=mensaje.encode("utf-8"), headers=headers, timeout=4)
                else:
                    req = urllib.request.Request(url, data=mensaje.encode("utf-8"), headers=headers, method="POST")
                    urllib.request.urlopen(req, timeout=4)
            except Exception as e:
                self.log_error("Notificación ntfy", e, throttle_sec=1800)

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            try:
                tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                tg_data = json.dumps({
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": f"<b>{titulo}</b>\n\n{mensaje}",
                    "parse_mode": "HTML"
                }).encode("utf-8")
                tg_headers = {"Content-Type": "application/json"}
                if HAS_REQUESTS:
                    requests.post(tg_url, data=tg_data, headers=tg_headers, timeout=4)
                else:
                    req = urllib.request.Request(tg_url, data=tg_data, headers=tg_headers, method="POST")
                    urllib.request.urlopen(req, timeout=4)
            except Exception as e:
                self.log_error("Notificación Telegram", e, throttle_sec=1800)

    # ------------------------------------------------------------------ conexiones
    def _create_exchange(self) -> Optional[Any]:
        if not HAS_CCXT:
            self.log("WARNING", "ccxt no está instalado: se usará solo la API pública REST de Kraken.")
            return None
        try:
            config: Dict[str, Any] = {
                'enableRateLimit': True,
                'timeout': 10000,
                'options': {'adjustForTimeDifference': True}
            }
            # Las claves se cargan por compatibilidad, pero este motor NO envía órdenes reales.
            if KRAKEN_API_KEY and KRAKEN_SECRET_KEY:
                config['apiKey'] = KRAKEN_API_KEY
                config['secret'] = KRAKEN_SECRET_KEY
            return ccxt.kraken(config)
        except Exception as e:
            self.log_error("Crear cliente ccxt Kraken", e, notify=True)
            return None

    def reconnect_kraken(self) -> None:
        now = time.time()
        if now - self._last_reconnect < 60:
            return
        self._last_reconnect = now
        try:
            self.exchange = None
            gc.collect()
            self.exchange = self._create_exchange()
            self.log("RECONNECT", "Cliente Kraken recreado tras un fallo de red.")
        except Exception as e:
            self.log_error("Reconexión Kraken", e, notify=True)

    def _get_sb(self) -> Optional[Any]:
        if self.supabase is not None:
            return self.supabase
        if SUPABASE_CONFIGURED:
            try:
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                return self.supabase
            except Exception as e:
                self.log_error("Conectar Supabase", e, notify=True)
        return None

    # ------------------------------------------------------------- persistencia
    @staticmethod
    def _is_column_error(exc: BaseException) -> bool:
        s = str(exc).lower()
        return "column" in s or "pgrst204" in s or "42703" in s

    @staticmethod
    def _is_duplicate_error(exc: BaseException) -> bool:
        s = str(exc).lower()
        return "23505" in s or "duplicate key" in s or "unique constraint" in s

    def _payload(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        cols = ALL_COLS if self.extra_cols_ok else BASE_COLS
        return {k: trade.get(k) for k in cols}

    def _db_insert(self, trade: Dict[str, Any]) -> str:
        """Devuelve 'ok' | 'duplicate' | 'queued' | 'memory'."""
        if not SUPABASE_CONFIGURED:
            return "memory"
        sb = self._get_sb()
        if sb is None:
            self._queue_write(f"insert {trade['order_id']}", self._make_insert_op(trade))
            return "queued"
        try:
            self._make_insert_op(trade)(sb)
            return "ok"
        except Exception as e:
            if self._is_duplicate_error(e):
                return "duplicate"
            self.log_error(f"Supabase insert {trade['order_id']}", e, notify=True)
            self._queue_write(f"insert {trade['order_id']}", self._make_insert_op(trade))
            return "queued"

    def _make_insert_op(self, trade: Dict[str, Any]) -> Callable[[Any], None]:
        snapshot = dict(trade)

        def op(sb: Any) -> None:
            try:
                sb.table("paper_trades").insert(self._payload(snapshot)).execute()
            except Exception as e:
                if self.extra_cols_ok and self._is_column_error(e):
                    self.extra_cols_ok = False
                    self.log("WARNING", "Tabla paper_trades sin columnas position_usd/fees_usd: ejecuta la migración SQL "
                                        "(final del archivo). Se guarda sin ellas por ahora.")
                    sb.table("paper_trades").insert(self._payload(snapshot)).execute()
                else:
                    raise
        return op

    def _db_update(self, order_id: str, fields: Dict[str, Any]) -> None:
        if not SUPABASE_CONFIGURED:
            return
        fields = dict(fields)

        def op(sb: Any) -> None:
            data = {k: v for k, v in fields.items() if (self.extra_cols_ok or k not in EXTRA_COLS)}
            try:
                sb.table("paper_trades").update(data).eq("order_id", order_id).execute()
            except Exception as e:
                if self.extra_cols_ok and self._is_column_error(e):
                    self.extra_cols_ok = False
                    data = {k: v for k, v in fields.items() if k not in EXTRA_COLS}
                    sb.table("paper_trades").update(data).eq("order_id", order_id).execute()
                else:
                    raise

        sb = self._get_sb()
        if sb is None:
            self._queue_write(f"update {order_id}", op)
            return
        try:
            op(sb)
        except Exception as e:
            self.log_error(f"Supabase update {order_id}", e, notify=True)
            self._queue_write(f"update {order_id}", op)

    def _queue_write(self, label: str, op: Callable[[Any], None]) -> None:
        with self.lock:
            if len(self.pending_writes) >= 200:
                self.pending_writes.pop(0)
                self.log("ERROR", "Cola de escrituras pendientes llena: se descartó la más antigua.")
            self.pending_writes.append((label, op))

    def flush_pending_writes(self) -> None:
        """Reintenta en orden las escrituras que fallaron (se detiene en la primera que falle)."""
        with self.lock:
            if not self.pending_writes:
                return
            batch = list(self.pending_writes)
        sb = self._get_sb()
        if sb is None:
            return
        done = 0
        for label, op in batch:
            try:
                op(sb)
                done += 1
            except Exception as e:
                if self._is_duplicate_error(e):
                    done += 1
                    continue
                self.log_error(f"Reintento Supabase ({label})", e)
                break
        if done:
            with self.lock:
                del self.pending_writes[:done]
            self.log("SYNC", f"{done} escritura(s) pendiente(s) sincronizada(s) con Supabase.")

    def _normalize_trade(self, t: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza tipos y repara niveles absurdos de SL/TP en posiciones abiertas."""
        t["entry_price"] = _to_float(t.get("entry_price"))
        t["exit_price"] = None if t.get("exit_price") is None else _to_float(t.get("exit_price"))
        t["pnl_usd"] = _to_float(t.get("pnl_usd"))
        t["pnl_pct"] = _to_float(t.get("pnl_pct"))
        t["sl"] = _to_float(t.get("sl"))
        t["tp"] = _to_float(t.get("tp"))
        t["trailing_be"] = bool(t.get("trailing_be", False))
        t["fees_usd"] = _to_float(t.get("fees_usd"))
        t["side"] = t.get("side") or "LONG"
        t["status"] = str(t.get("status") or "OPEN").upper()

        pos = _to_float(t.get("position_usd"))
        if pos <= 0:
            if t["status"] == "CLOSED" and abs(t["pnl_pct"]) > 1e-9 and t["pnl_usd"] != 0:
                pos = abs(t["pnl_usd"] / (t["pnl_pct"] / 100.0))
            else:
                pos = INITIAL_CAPITAL * MAX_POSITION_PCT_OF_EQUITY
        t["position_usd"] = pos

        entry = t["entry_price"]
        if t["status"] == "OPEN" and t["side"] == "LONG" and entry > 0:
            fixed: Dict[str, Any] = {}
            if (t["sl"] > entry * 1.005) or t["sl"] <= 0.0:
                t["sl"] = round(entry * (1.0 - STOP_LOSS_PCT), 4)
                fixed["sl"] = t["sl"]
            if (t["tp"] < entry) or t["tp"] <= 0.0:
                t["tp"] = round(entry * (1.0 + TAKE_PROFIT_PCT), 4)
                fixed["tp"] = t["tp"]
            if fixed:
                self.log("SANITIZE", f"Niveles SL/TP corregidos en {t.get('order_id')}: {fixed}")
                self._db_update(str(t.get("order_id")), fixed)
        return t

    def hydrate_from_supabase(self) -> None:
        """Carga el estado persistido una sola vez. Sin esto no se permiten nuevas entradas."""
        if not SUPABASE_CONFIGURED:
            with self.lock:
                self.hydrated = True
            return
        sb = self._get_sb()
        if sb is None:
            return
        try:
            res = sb.table("paper_trades").select("*").order("created_at", desc=True).execute()
            rows = [self._normalize_trade(dict(r)) for r in (res.data or [])]
            with self.lock:
                self.trades = rows
                self.hydrated = True
            self.log("SYNC", f"Estado cargado desde Supabase: {len(rows)} registro(s).")
        except Exception as e:
            self.log_error("Cargar estado desde Supabase", e, notify=True)

    # ------------------------------------------------------------------ datos de mercado
    def _fetch_ohlcv_df(self, symbol: str) -> Optional[pd.DataFrame]:
        pair_k = KRAKEN_PAIR_MAP.get(symbol, symbol.replace('/', ''))
        if self.exchange is not None:
            try:
                raw = self.exchange.fetch_ohlcv(symbol, timeframe='4h', limit=OHLCV_LIMIT)
                if raw and len(raw) >= 30:
                    return pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            except Exception as e:
                self.log_error(f"Kraken fetch_ohlcv {symbol}", e, notify=True)
                self.reconnect_kraken()
        try:
            url = f"https://api.kraken.com/0/public/OHLC?pair={pair_k}&interval=240"
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            res = data.get('result', {})
            keys = [k for k in res.keys() if k != 'last']
            if keys and len(res[keys[0]]) >= 30:
                rows = res[keys[0]][-OHLCV_LIMIT:]
                return pd.DataFrame([
                    {'ts': int(c[0]) * 1000, 'open': float(c[1]), 'high': float(c[2]),
                     'low': float(c[3]), 'close': float(c[4]), 'volume': float(c[6])}
                    for c in rows
                ])
        except Exception as e:
            self.log_error(f"Kraken REST OHLC {symbol}", e)
        return None

    @staticmethod
    def _empty_analysis(symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol, "price": 0.0, "ema200": 0.0, "rsi": 50.0,
            "vol_curr": 0.0, "vol_ma20": 0.0, "vol_ratio": 0.0,
            "cond_ema": False, "cond_rsi": False, "cond_sweep": False, "signal": False,
            "candle_ts": 0, "ema_ready": False
        }

    @staticmethod
    def compute_signal(df: pd.DataFrame, symbol: str, now_ms: Optional[int] = None) -> Dict[str, Any]:
        """
        Calcula la señal SOLO con velas cerradas. Si la última fila es la vela en formación,
        se descarta (equivale a usar iloc[-2] sobre el DataFrame crudo).
        Función pura: no hace red ni toca estado, por lo que es testeable.
        """
        result = DipperEngine._empty_analysis(symbol)
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)

        d = df.reset_index(drop=True)
        if len(d) and int(d['ts'].iloc[-1]) + CANDLE_MS > now_ms:
            d = d.iloc[:-1].reset_index(drop=True)          # vela en formación fuera
        if len(d) < max(SWEEP_LOOKBACK + 2, 22):
            return result

        close, open_, low, volume = d['close'], d['open'], d['low'], d['volume']
        last_close = float(close.iloc[-1])
        last_open = float(open_.iloc[-1])
        last_low = float(low.iloc[-1])
        vol_curr = float(volume.iloc[-1])

        # 1. EMA 200 (solo válida con suficiente historia cerrada)
        ema_ready = len(close) >= MIN_CANDLES_FOR_EMA
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

        # 2. RSI 14 (Wilder)
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1.0 / 14.0, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / 14.0, adjust=False).mean()
        rs = gain / (loss + 1e-9)
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])

        # 3. Volumen: SMA20 de las 20 velas ANTERIORES a la vela de señal
        vol_ma20 = float(volume.iloc[-21:-1].mean())
        vol_ratio = float(vol_curr / vol_ma20) if vol_ma20 > 0 else 0.0

        # 4. Barrido de liquidez ESTRICTO (todas las condiciones a la vez)
        recent_low = float(low.iloc[-1 - SWEEP_LOOKBACK:-1].min())
        broke_low = last_low < recent_low                          # mecha bajo el mínimo previo
        recovered = last_close > recent_low and last_close > last_open   # cierre de recuperación y vela alcista
        vol_ok = vol_ratio >= VOL_RATIO_MIN
        is_sweep = bool(broke_low and recovered and vol_ok)

        cond_ema = bool(ema_ready and last_close > ema200)
        cond_rsi = bool(50.0 <= rsi <= 70.0)
        signal = bool(cond_ema and cond_rsi and is_sweep and last_close > 0)

        result.update({
            "price": last_close, "ema200": ema200, "rsi": rsi,
            "vol_curr": vol_curr, "vol_ma20": vol_ma20, "vol_ratio": vol_ratio,
            "cond_ema": cond_ema, "cond_rsi": cond_rsi, "cond_sweep": is_sweep,
            "signal": signal, "candle_ts": int(d['ts'].iloc[-1]), "ema_ready": ema_ready
        })
        return result

    def analyze_pair_confluence_4h(self, symbol: str) -> Dict[str, Any]:
        df = self._fetch_ohlcv_df(symbol)
        if df is None or df.empty:
            return self._empty_analysis(symbol)
        try:
            return self.compute_signal(df, symbol)
        except Exception as e:
            self.log_error(f"Cálculo de indicadores {symbol}", e)
            return self._empty_analysis(symbol)
        finally:
            del df
            gc.collect()

    def get_quote(self, symbol: str) -> Dict[str, float]:
        """Devuelve {'last','bid','ask'} (0.0 si no disponible) y actualiza la caché de precios."""
        quote = {"last": 0.0, "bid": 0.0, "ask": 0.0}
        if self.exchange is not None:
            try:
                tk = self.exchange.fetch_ticker(symbol)
                if tk:
                    quote["last"] = _to_float(tk.get('last'))
                    quote["bid"] = _to_float(tk.get('bid'))
                    quote["ask"] = _to_float(tk.get('ask'))
            except Exception as e:
                self.log_error(f"Kraken fetch_ticker {symbol}", e, notify=True)
        if quote["last"] <= 0.0:
            pair_k = KRAKEN_PAIR_MAP.get(symbol, symbol.replace('/', ''))
            try:
                url = f"https://api.kraken.com/0/public/Ticker?pair={pair_k}"
                req = urllib.request.Request(url, headers=_UA)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                for _, val in data.get('result', {}).items():
                    if val.get('c'):
                        quote["last"] = _to_float(val['c'][0])
                        quote["bid"] = _to_float(val.get('b', [0])[0])
                        quote["ask"] = _to_float(val.get('a', [0])[0])
                        break
            except Exception as e:
                self.log_error(f"Kraken REST Ticker {symbol}", e)
        if quote["last"] > 0.0:
            with self.lock:
                self.price_cache[symbol] = quote["last"]
        return quote

    def get_current_asset_price(self, symbol: str) -> float:
        return self.get_quote(symbol)["last"]

    def get_cached_price(self, symbol: str) -> float:
        with self.lock:
            return self.price_cache.get(symbol, 0.0)

    # ------------------------------------------------------------------ vistas (solo lectura)
    def snapshot_trades(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [dict(t) for t in self.trades]

    def snapshot_df(self) -> pd.DataFrame:
        rows = self.snapshot_trades()
        if rows:
            return pd.DataFrame(rows)
        return pd.DataFrame(columns=ALL_COLS)

    def get_logs(self) -> List[str]:
        with self.lock:
            return list(self.logs)

    def get_analysis(self, symbol: str) -> Dict[str, Any]:
        with self.lock:
            return dict(self.analysis_cache.get(symbol) or self._empty_analysis(symbol))

    def get_mode(self) -> str:
        with self.lock:
            return self.operating_mode

    def set_mode(self, mode: str) -> None:
        if mode not in OPERATING_MODES:
            return
        with self.lock:
            changed = mode != self.operating_mode
            self.operating_mode = mode
        if changed:
            self.log("MODE", f"Modo operativo cambiado a {mode}.")
            self.notify("🔧 MODO OPERATIVO", f"Nuevo modo: {mode}", priority="high", tags="gear")

    def heartbeat_age(self) -> float:
        return (time.time() - self.last_cycle_ts) if self.last_cycle_ts else float("inf")

    # ------------------------------------------------------------------ reglas de riesgo (bajo lock)
    def _closed(self) -> List[Dict[str, Any]]:
        return [t for t in self.trades if t.get("status") == "CLOSED"]

    def _open(self) -> List[Dict[str, Any]]:
        return [t for t in self.trades if t.get("status") == "OPEN"]

    def equity_realized(self) -> float:
        with self.lock:
            return INITIAL_CAPITAL + sum(_to_float(t.get("pnl_usd")) for t in self._closed())

    def daily_realized_pnl(self) -> float:
        today = now_cot().date()
        total = 0.0
        with self.lock:
            for t in self._closed():
                dt = _parse_dt(t.get("closed_at")) or _parse_dt(t.get("created_at"))
                if dt is not None and dt.date() == today:
                    total += _to_float(t.get("pnl_usd"))
        return total

    def is_circuit_breaker_active(self) -> bool:
        return self.daily_realized_pnl() <= (INITIAL_CAPITAL * DAILY_CIRCUIT_BREAKER)

    def _in_sl_cooldown(self, sym: str) -> bool:
        now = now_cot()
        for t in self._closed():
            if t.get("symbol") != sym or "STOP LOSS" not in str(t.get("exit_reason", "")).upper():
                continue
            dt = _parse_dt(t.get("closed_at")) or _parse_dt(t.get("created_at"))
            if dt is not None and (now - dt).total_seconds() / 3600.0 < STOP_LOSS_COOLDOWN_HOURS:
                return True
        return False

    def _btc_bullish(self) -> bool:
        """Falla cerrado: si no hay análisis válido de BTC, no se abren posiciones."""
        a = self.analysis_cache.get("BTC/USD")
        if not a or not a.get("ema_ready") or a.get("price", 0.0) <= 0 or a.get("ema200", 0.0) <= 0:
            return False
        return a["price"] > a["ema200"]

    # ------------------------------------------------------------------ operaciones
    def register_long_position(self, sym: str, cur_p: float, analysis: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        # Red FUERA del lock (cotización); las decisiones y la reserva ocurren DENTRO, de forma atómica.
        quote = self.get_quote(sym)
        spot = quote["last"]
        execution_price = spot if spot > 0.0 else cur_p
        if execution_price <= 0.0:
            self.log("SKIP", f"{sym}: sin precio válido, entrada omitida.")
            return None
        if quote["bid"] > 0 and quote["ask"] > 0:
            spread = (quote["ask"] - quote["bid"]) / quote["ask"]
            if spread > MAX_SPREAD_TOLERANCE:
                self.log("SKIP", f"{sym}: spread {spread * 100:.3f}% > {MAX_SPREAD_TOLERANCE * 100:.2f}%, entrada omitida.")
                return None

        candle_ts = int((analysis or {}).get("candle_ts", 0))

        with self.lock:
            if self.operating_mode != MODE_ACTIVE:
                return None
            if not self.hydrated:
                return None
            if self.is_circuit_breaker_active():
                today = now_cot().strftime("%Y-%m-%d")
                if self._breaker_blocked_logged_day != today:
                    self._breaker_blocked_logged_day = today
                    self.log("BREAKER", "Circuit breaker diario activo: nuevas entradas BLOQUEADAS hasta mañana (COT).")
                return None
            if not self._btc_bullish():
                return None
            if candle_ts and self.last_entry_candle.get(sym) == candle_ts:
                return None                                   # ya se operó esta vela cerrada
            if self._in_sl_cooldown(sym):
                return None

            open_trades = self._open()
            if len(open_trades) >= MAX_CONCURRENT_POSITIONS:
                return None
            if any(t.get("symbol") == sym for t in open_trades):
                return None

            equity = self.equity_realized()
            risk_usd = equity * RISK_PER_TRADE
            pos_usd = risk_usd / STOP_LOSS_PCT
            pos_usd = min(pos_usd, equity * MAX_POSITION_PCT_OF_EQUITY)
            free_cash = equity - sum(_to_float(t.get("position_usd")) for t in open_trades)
            pos_usd = min(pos_usd, free_cash)
            if pos_usd < MIN_POSITION_USD:
                self.log("SKIP", f"{sym}: tamaño ${pos_usd:,.2f} < mínimo ${MIN_POSITION_USD:,.2f} (caja libre ${free_cash:,.2f}).")
                return None

            sl_price = round(execution_price * (1.0 - STOP_LOSS_PCT), 4)
            tp_price = round(execution_price * (1.0 + TAKE_PROFIT_PCT), 4)
            order_id = f"DIP-{uuid.uuid4().hex[:8].upper()}"
            real_risk = pos_usd * STOP_LOSS_PCT

            new_trade = {
                "order_id": order_id, "symbol": sym, "side": "LONG", "status": "OPEN",
                "entry_price": execution_price, "exit_price": None, "sl": sl_price, "tp": tp_price,
                "pnl_usd": 0.0, "pnl_pct": 0.0, "exit_reason": None, "trailing_be": False,
                "created_at": now_cot().isoformat(), "closed_at": None,
                "position_usd": round(pos_usd, 4), "fees_usd": 0.0
            }
            # RESERVA ATÓMICA en memoria: ningún otro hilo puede abrir este símbolo a partir de aquí.
            self.trades.insert(0, new_trade)
            if candle_ts:
                self.last_entry_candle[sym] = candle_ts

        # Persistencia fuera del lock (red lenta). Si el índice único rechaza, se revierte la reserva.
        status = self._db_insert(new_trade)
        if status == "duplicate":
            with self.lock:
                self.trades = [t for t in self.trades if t.get("order_id") != order_id]
            self.log("DUPLICATE", f"{sym}: Supabase rechazó un duplicado (índice único). Entrada revertida.")
            return None

        self.log("EXEC", f"¡ENTRADA LONG! {sym} @ ${execution_price:,.4f} · tamaño ${pos_usd:,.2f} "
                         f"(riesgo ${real_risk:,.2f}) [SL ${sl_price:,.4f} | TP ${tp_price:,.4f}] · persistencia: {status}")
        self.notify(
            f"🟢 SWEEP ENTRY: {sym} [LONG]",
            f"ID: {order_id}\nEntrada: ${execution_price:,.4f}\nTamaño: ${pos_usd:,.2f}\n"
            f"TP (+{TAKE_PROFIT_PCT * 100:.1f}%): ${tp_price:,.4f}\nSL (-{STOP_LOSS_PCT * 100:.1f}%): ${sl_price:,.4f}\n"
            f"Riesgo: ${real_risk:,.2f} USD",
            priority="high", tags="rocket,chart_with_upwards_trend"
        )
        return new_trade

    def apply_trailing_stop_to_breakeven(self) -> None:
        updates: List[Tuple[str, Dict[str, Any]]] = []
        with self.lock:
            for t in self._open():
                if t.get("trailing_be"):
                    continue
                cur_p = self.price_cache.get(str(t.get("symbol")), 0.0)
                entry = _to_float(t.get("entry_price"))
                if cur_p <= 0.0 or entry <= 0.0:
                    continue
                if (cur_p - entry) / entry >= TRAILING_TRIGGER_PCT:
                    new_sl = entry * (1.0 + TRAILING_BE_PCT)
                    t["sl"] = new_sl
                    t["trailing_be"] = True
                    updates.append((str(t["order_id"]), {"sl": new_sl, "trailing_be": True}))
                    self.log("PROTECTION", f"Trailing Break-Even en {t.get('symbol')}. SL en ${new_sl:,.4f}.")
        for oid, fields in updates:
            self._db_update(oid, fields)

    def close_active_trade(self, order_id: str, outcome: str, actual_exit_price: Optional[float] = None) -> bool:
        """Idempotente: si el trade ya está cerrado no hace nada."""
        with self.lock:
            trade = next((t for t in self.trades if t.get("order_id") == order_id and t.get("status") == "OPEN"), None)
            if trade is None:
                return False
            entry = _to_float(trade.get("entry_price"))
            if entry <= 0:
                return False
            pos = _to_float(trade.get("position_usd"))
            tp_t = _to_float(trade.get("tp"), entry * (1.0 + TAKE_PROFIT_PCT))
            sl_t = _to_float(trade.get("sl"), entry * (1.0 - STOP_LOSS_PCT))
            have_px = actual_exit_price is not None and actual_exit_price > 0

            if outcome == "TP":
                exit_p = actual_exit_price if have_px else tp_t
            elif outcome == "BE":
                exit_p = actual_exit_price if have_px else entry * (1.0 + TRAILING_BE_PCT)
            else:
                exit_p = actual_exit_price if have_px else sl_t

            gross_pct = (exit_p - entry) / entry * 100.0
            fees = pos * SIM_FEE_PER_SIDE + pos * (1.0 + gross_pct / 100.0) * SIM_FEE_PER_SIDE
            pnl_usd = pos * (gross_pct / 100.0) - fees
            pnl_pct = (pnl_usd / pos * 100.0) if pos > 0 else 0.0
            label = {"TP": "TAKE PROFIT", "BE": "BREAK-EVEN"}.get(outcome, "STOP LOSS")
            sign = "+" if gross_pct >= 0 else ""
            reason = f"{label} ({sign}{gross_pct:.2f}% bruto)"
            closed_at = now_cot().isoformat()

            trade.update({
                "status": "CLOSED", "exit_price": exit_p, "pnl_usd": pnl_usd, "pnl_pct": pnl_pct,
                "exit_reason": reason, "closed_at": closed_at, "fees_usd": fees
            })
            symbol = trade.get("symbol")

        self._db_update(order_id, {
            "status": "CLOSED", "exit_price": exit_p, "pnl_usd": pnl_usd, "pnl_pct": pnl_pct,
            "exit_reason": reason, "closed_at": closed_at, "fees_usd": fees
        })
        self.log("ACTION", f"CIERRE: {order_id} {symbol} por {outcome} | PnL neto: ${pnl_usd:,.2f} USD (comisiones ${fees:,.2f})")
        return True

    def monitor_and_auto_close_open_trades(self) -> None:
        with self.lock:
            open_trades = [dict(t) for t in self._open()]
        for t in open_trades:
            sym = str(t.get("symbol"))
            cur_p = self.get_current_asset_price(sym)          # red fuera del lock
            if cur_p <= 0.0:
                continue
            entry = _to_float(t.get("entry_price"))
            sl_p = _to_float(t.get("sl"), entry * (1.0 - STOP_LOSS_PCT))
            tp_p = _to_float(t.get("tp"), entry * (1.0 + TAKE_PROFIT_PCT))
            oid = str(t.get("order_id"))
            if cur_p >= tp_p:
                self.close_active_trade(oid, "TP", actual_exit_price=cur_p)
            elif cur_p <= sl_p:
                if bool(t.get("trailing_be")) or sl_p >= entry:
                    self.close_active_trade(oid, "BE", actual_exit_price=cur_p)
                else:
                    self.close_active_trade(oid, "SL", actual_exit_price=cur_p)

    def _check_breaker_notification(self) -> None:
        if self.is_circuit_breaker_active():
            today = now_cot().strftime("%Y-%m-%d")
            if self._breaker_notified_day != today:
                self._breaker_notified_day = today
                self.notify("🚨 CIRCUIT BREAKER",
                            f"Pérdida diaria: ${self.daily_realized_pnl():,.2f}. Nuevas entradas bloqueadas hasta mañana (COT).",
                            priority="urgent", tags="rotating_light")

    # ------------------------------------------------------------------ ciclo del daemon
    def run_cycle(self) -> None:
        self.flush_pending_writes()
        if not self.hydrated:
            self.hydrate_from_supabase()

        self.monitor_and_auto_close_open_trades()
        self.apply_trailing_stop_to_breakeven()
        self._check_breaker_notification()

        if time.time() - self.last_analysis_ts >= ANALYSIS_INTERVAL_SEC:
            fresh: Dict[str, Dict[str, Any]] = {}
            for sym in PAIRS:
                fresh[sym] = self.analyze_pair_confluence_4h(sym)
                time.sleep(0.3)
            with self.lock:
                for sym, a in fresh.items():
                    if a.get("price", 0.0) > 0:                 # no pisar un buen análisis con uno vacío
                        self.analysis_cache[sym] = a
                    elif sym not in self.analysis_cache:
                        self.analysis_cache[sym] = a
            self.last_analysis_ts = time.time()

            for sym in PAIRS:
                a = fresh[sym]
                if a.get("signal", False) and a.get("price", 0.0) > 0.0:
                    self.register_long_position(sym, float(a["price"]), a)

        self.last_cycle_ts = time.time()
        self.cycle_count += 1

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as e:
                self.log_error("Ciclo del daemon", e, notify=True)
                self.stop_event.wait(5)
            gc.collect()
            self.stop_event.wait(MONITOR_INTERVAL_SEC)

    def start(self) -> None:
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._loop, daemon=True, name="DipperDaemonSweep")
            self.thread.start()


@st.cache_resource(show_spinner=False)
def get_engine() -> DipperEngine:
    """Singleton por proceso: el hilo se crea una sola vez aunque Streamlit re-ejecute el script."""
    eng = DipperEngine()
    eng.start()
    return eng


# --------------------------------------------------------------------------------------
# 6. HEALTH CHECK HTTP PARA RENDER ($PORT / 200 OK) — también singleton
# --------------------------------------------------------------------------------------
class RenderHealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - PROYECTO DIPPER v4.1 QUANT ENGINE ONLINE")

    def log_message(self, format, *args):
        pass


@st.cache_resource(show_spinner=False)
def init_health_check_server() -> bool:
    port = int(os.getenv("PORT", "10000"))
    try:
        httpd = HTTPServer(("0.0.0.0", port), RenderHealthCheckHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True, name="DipperHealth").start()
        return True
    except OSError as e:
        # Normal en Render: Streamlit ya escucha en $PORT y responde 200 por sí mismo.
        logging.info("Health check dedicado no iniciado (puerto %s ocupado): %s", port, e)
        return False


engine = get_engine()
init_health_check_server()
# 10. INTERFAZ STREAMLIT & MÉTRICAS (2 PESTAÑAS PRINCIPALES)
# --------------------------------------------------------------------------------------
import html as _html

# La UI es SOLO LECTURA: toma una foto del estado del motor (sin red, sin abrir posiciones).
df_all = engine.snapshot_df()
df_open = df_all[df_all["status"] == "OPEN"].copy() if not df_all.empty else pd.DataFrame()
df_closed = df_all[df_all["status"] == "CLOSED"].copy() if not df_all.empty else pd.DataFrame()

total_closed = len(df_closed)
wins = len(df_closed[df_closed["pnl_usd"] > 0]) if total_closed > 0 else 0
losses = len(df_closed[df_closed["pnl_usd"] < 0]) if total_closed > 0 else 0
win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0
total_pnl_usd = float(df_closed["pnl_usd"].sum()) if total_closed > 0 else 0.0
total_pnl_pct = (total_pnl_usd / INITIAL_CAPITAL) * 100.0
current_capital = INITIAL_CAPITAL + total_pnl_usd

floating_pnl_usd = 0.0
if not df_open.empty:
    _cur_l, _pct_l, _usd_l = [], [], []
    for _, row in df_open.iterrows():
        sym_o = str(row.get('symbol'))
        entry_o = float(row.get('entry_price') or 1.0)
        cur_p_o = engine.get_cached_price(sym_o)
        if cur_p_o <= 0.0:
            cur_p_o = entry_o
        f_pct = ((cur_p_o - entry_o) / entry_o) * 100.0
        f_usd = float(row.get('position_usd') or 0.0) * (f_pct / 100.0)   # PnL sobre el tamaño REAL de la posición
        floating_pnl_usd += f_usd
        _cur_l.append(cur_p_o)
        _pct_l.append(f_pct)
        _usd_l.append(f_usd)
    df_open["current_price"] = _cur_l
    df_open["pnl_float_pct"] = _pct_l
    df_open["pnl_float_usd"] = _usd_l

balance_actual = current_capital + floating_pnl_usd

# Estado del motor (latido del hilo, modo operativo, breaker)
_hb_age = engine.heartbeat_age()
if engine.cycle_count == 0:
    motor_label, motor_color = "INICIANDO", "#f59e0b"
elif _hb_age > 180:
    motor_label, motor_color = "SIN LATIDO (REVISAR LOGS)", "#f43f5e"
elif not engine.hydrated:
    motor_label, motor_color = "SINCRONIZANDO SUPABASE · ENTRADAS BLOQUEADAS", "#f59e0b"
elif engine.get_mode() != MODE_ACTIVE:
    motor_label, motor_color = "SOLO GESTIÓN · SIN NUEVAS ENTRADAS", "#f59e0b"
elif engine.is_circuit_breaker_active():
    motor_label, motor_color = "CIRCUIT BREAKER ACTIVO · ENTRADAS BLOQUEADAS", "#f43f5e"
else:
    motor_label, motor_color = "LIVE AUTÓNOMO", "#10b981"

# Encabezado UI
col_h_brand, col_h_status = st.columns([3, 2])
with col_h_brand:
    render_html(f"""
    <div class="exec-brand-box">
        <div class="exec-logo-icon">⚡</div>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 19px; font-weight: 800; color: #ffffff;">PROYECTO DIPPER</span>
                <span style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; font-family: 'JetBrains Mono';">v4.1 LIQUIDITY SWEEP VIP</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                <div class="status-badge" style="color: {motor_color};"><div class="pulse-dot"></div><span>MOTOR: {motor_label}</span></div>
                <div class="status-badge" style="color: #38bdf8;"><span>CAPITAL BASE: $50.00 USD</span></div>
            </div>
        </div>
    </div>
    """)

with col_h_status:
    render_html(f"""
    <div style="display: flex; flex-direction: column; align-items: flex-end; justify-content: center; height: 100%;">
        <div class="status-badge" style="background: rgba(56, 189, 248, 0.08); color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); font-size: 10px;">
            ● 3 PARES VIP · SWEEP & VOLUME PROFILE · LIMIT=720 (4H · VELAS CERRADAS)
        </div>
    </div>
    """)

    def _on_mode_change():
        engine.set_mode(st.session_state["operating_mode"])

    # Sincroniza con el estado real del motor (otra pestaña pudo cambiarlo) antes de crear el widget.
    st.session_state["operating_mode"] = engine.get_mode()
    st.selectbox(
        "Modo operativo (interruptor de emergencia)",
        OPERATING_MODES,
        key="operating_mode",
        on_change=_on_mode_change,
        label_visibility="collapsed",
        help="ACTIVO: abre y gestiona posiciones. SOLO_GESTIÓN: no abre nuevas, sigue cerrando por SL/TP."
    )

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
            cur_p = float(row.get('current_price', entry_p))
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
        data_pair = engine.get_analysis(sym)
        is_signal = data_pair.get("signal", False)
        price_val = data_pair.get("price", 0.0)
        ema_val = data_pair.get("ema200", 0.0)
        rsi_val = data_pair.get("rsi", 50.0)
        vol_ratio = data_pair.get("vol_ratio", 1.0)
        cond_sweep = data_pair.get("cond_sweep", False)

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

    current_logs = engine.get_logs()
    logs_html = "".join([f"<div class=\"log-line\">{_html.escape(str(l))}</div>" for l in current_logs])
    render_html(f"<div class=\"terminal-console\">{logs_html}</div>")

gc.collect()

# ======================================================================================
# SQL RECOMENDADO EN SUPABASE (ejecutar una vez en el SQL Editor)
# ======================================================================================
# -- Columnas nuevas para el sizing real y las comisiones simuladas:
# alter table paper_trades
#   add column if not exists position_usd double precision,
#   add column if not exists fees_usd double precision default 0;
#
# -- Segunda barrera anti-duplicados: una sola posición ABIERTA por símbolo:
# create unique index if not exists one_open_position_per_symbol
#   on paper_trades (symbol) where status = 'OPEN';
#
# -- Si order_id no es único todavía:
# create unique index if not exists paper_trades_order_id_uq on paper_trades (order_id);
# ======================================================================================
