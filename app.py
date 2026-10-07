# -*- coding: utf-8 -*-
"""
PROYECTO DIPPER | Quant Terminal v2.8 (High-Impact UI, COT Timezone & Institutional Risk)
Terminal Autónomo de Trading Cuantitativo
Escaneo: 18 Criptomonedas Kraken Spot Nativas en USD
Gestión de Riesgo:
  - Límite de 3 Posiciones Concurrentes (Máx 1 por par)
  - Cálculo estricto de PnL en $ USD sobre Capital de Posición / Operativo
  - Take Profit: +3.0% (+$30.00 USD para base $1,000)
  - Stop Loss: -1.5% (-$15.00 USD para base $1,000, estrictamente con signo negativo)
  - Recalculador de Balance / Equity: Capital Inicial + SUMA(PnL_USD de trades cerrados)
  - Ciclo Semanal: Domingo 00:00 UTC (Sábado 7:00 PM COT) a Sábado 23:59 UTC
  - Zona Horaria: Colombia (America/Bogota - COT / UTC-5)
  - Diseño Visual: Coloreado completo de filas en historial cerrado (Verde Ganancia / Rojo Pérdida)
  - Posiciones Activas (OPEN): Contenedor superior con estilo neutro profesional
  - Sistema de Notificaciones Push Automáticas: Ntfy.sh
Stack: Python 3.10+, Streamlit, CCXT (Kraken Spot REST), Supabase (PostgreSQL), Plotly
Despliegue: Render / Streamlit Cloud
"""

import os
import time
import datetime
import pandas as pd
import numpy as np
import streamlit as st
import ccxt
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    import zoneinfo
    try:
        TZ_COLOMBIA = zoneinfo.ZoneInfo("America/Bogota")
    except Exception:
        TZ_COLOMBIA = datetime.timezone(datetime.timedelta(hours=-5))
except ImportError:
    TZ_COLOMBIA = datetime.timezone(datetime.timedelta(hours=-5))

try:
    import requests
    HAS_REQUESTS_LIB = True
except ImportError:
    HAS_REQUESTS_LIB = False

try:
    from supabase import create_client, Client
    HAS_SUPABASE_LIB = True
except ImportError:
    HAS_SUPABASE_LIB = False

# =========================================================================
# 1. CONFIGURACIÓN DE PÁGINA E INYECCIÓN CSS DE ALTO IMPACTO VISUAL
# =========================================================================
st.set_page_config(
    page_title="PROYECTO DIPPER | Multi-Asset Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS Profesionales Bloomberg Dark Theme (#070a13) y Row-Level Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,700;1,400&display=swap');
    
    html, body, [class*="css"], .stMarkdown {
        font-family: 'JetBrains Mono', monospace !important;
        background-color: #070a13 !important;
        color: #93c5fd;
    }
    .stApp {
        background-color: #070a13 !important;
    }

    /* Scrollbar personalizada minimalista */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #070a13;
    }
    ::-webkit-scrollbar-thumb {
        background: #1e293b;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #38bdf8;
    }

    /* Status Grid Superior */
    .status-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 16px;
    }
    .status-card {
        background: #0b1120;
        border: 1px solid #1e293b;
        border-radius: 6px;
        padding: 12px 14px;
        text-align: left;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
        transition: border-color 0.2s ease;
    }
    .status-card:hover {
        border-color: #38bdf8;
    }
    .status-title {
        font-size: 10px;
        color: #64748b;
        letter-spacing: 1.2px;
        font-weight: 700;
        text-transform: uppercase;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .status-value {
        font-size: 16px;
        font-weight: 700;
        color: #f8fafc;
        margin-top: 5px;
        letter-spacing: -0.2px;
    }
    .status-sub {
        font-size: 11px;
        color: #34d399;
        margin-top: 3px;
        font-weight: 500;
    }

    /* Estilización de st.metric en tema oscuro */
    div[data-testid="stMetric"] {
        background-color: #0b1120;
        border: 1px solid #1e293b;
        padding: 14px 16px;
        border-radius: 6px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4);
    }
    div[data-testid="stMetric"]:hover {
        border-color: #38bdf8;
    }
    div[data-testid="stMetricLabel"] > div {
        color: #94a3b8 !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
    }
    div[data-testid="stMetricValue"] > div {
        color: #f8fafc !important;
        font-size: 22px !important;
        font-weight: 800 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Contenedor Neutro para Posiciones Abiertas (OPEN) */
    .open-positions-container {
        background: #0b1120;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }
    .open-pos-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid #1e293b;
    }
    .open-pos-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 12px;
    }
    .open-pos-card {
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 12px 14px;
        position: relative;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .open-pos-card:hover {
        border-color: #38bdf8;
        transform: translateY(-2px);
    }

    /* TABLA DE ALTO IMPACTO CON FILAS COLOREADAS (Row-Level Background Styling) */
    .table-responsive-container {
        width: 100%;
        overflow-x: auto;
        border: 1px solid #1e293b;
        border-radius: 8px;
        background-color: #070a13;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);
        max-height: 520px;
        overflow-y: auto;
    }
    .custom-quant-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0 4px;
        font-size: 12px;
        text-align: left;
    }
    .custom-quant-table thead tr th {
        position: sticky;
        top: 0;
        background-color: #0f172a;
        color: #94a3b8;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        padding: 12px 10px;
        border-bottom: 2px solid #1e293b;
        z-index: 2;
        white-space: nowrap;
    }
    /* Filas completas con fondo translúcido y bordes laterales de alta fidelidad */
    .row-profit {
        background-color: rgba(0, 230, 118, 0.15) !important;
        color: #00E676 !important;
        font-weight: bold;
        transition: background-color 0.15s ease;
    }
    .row-profit:hover {
        background-color: rgba(0, 230, 118, 0.28) !important;
    }
    .row-profit td {
        border-top: 1px solid rgba(0, 230, 118, 0.3);
        border-bottom: 1px solid rgba(0, 230, 118, 0.3);
        padding: 10px 10px;
        white-space: nowrap;
    }
    .row-profit td:first-child {
        border-left: 4px solid #00E676;
        border-top-left-radius: 4px;
        border-bottom-left-radius: 4px;
    }
    .row-profit td:last-child {
        border-right: 1px solid rgba(0, 230, 118, 0.3);
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
    }

    .row-loss {
        background-color: rgba(255, 82, 82, 0.15) !important;
        color: #FF5252 !important;
        font-weight: bold;
        transition: background-color 0.15s ease;
    }
    .row-loss:hover {
        background-color: rgba(255, 82, 82, 0.28) !important;
    }
    .row-loss td {
        border-top: 1px solid rgba(255, 82, 82, 0.3);
        border-bottom: 1px solid rgba(255, 82, 82, 0.3);
        padding: 10px 10px;
        white-space: nowrap;
    }
    .row-loss td:first-child {
        border-left: 4px solid #FF5252;
        border-top-left-radius: 4px;
        border-bottom-left-radius: 4px;
    }
    .row-loss td:last-child {
        border-right: 1px solid rgba(255, 82, 82, 0.3);
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
    }

    .row-neutral {
        background-color: rgba(158, 158, 158, 0.15) !important;
        color: #E0E0E0 !important;
        transition: background-color 0.15s ease;
    }
    .row-neutral:hover {
        background-color: rgba(158, 158, 158, 0.25) !important;
    }
    .row-neutral td {
        border-top: 1px solid rgba(158, 158, 158, 0.25);
        border-bottom: 1px solid rgba(158, 158, 158, 0.25);
        padding: 10px 10px;
        white-space: nowrap;
    }
    .row-neutral td:first-child {
        border-left: 4px solid #9e9e9e;
        border-top-left-radius: 4px;
        border-bottom-left-radius: 4px;
    }
    .row-neutral td:last-child {
        border-right: 1px solid rgba(158, 158, 158, 0.25);
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
    }

    /* Badges de Resultado */
    .badge-pill-tp {
        background: rgba(0, 230, 118, 0.25);
        color: #00E676;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 800;
        font-size: 10px;
        letter-spacing: 0.5px;
        display: inline-block;
        border: 1px solid rgba(0, 230, 118, 0.4);
    }
    .badge-pill-sl {
        background: rgba(255, 82, 82, 0.25);
        color: #FF5252;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 800;
        font-size: 10px;
        letter-spacing: 0.5px;
        display: inline-block;
        border: 1px solid rgba(255, 82, 82, 0.4);
    }
    .badge-pill-neutral {
        background: rgba(158, 158, 158, 0.2);
        color: #E0E0E0;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 10px;
        display: inline-block;
        border: 1px solid rgba(158, 158, 158, 0.3);
    }
    .badge-auto {
        background: #0369a1;
        color: #e0f2fe;
        font-size: 10px;
        padding: 2px 7px;
        border-radius: 4px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .badge-side-long {
        background: rgba(16, 185, 129, 0.2);
        color: #10b981;
        padding: 2px 6px;
        border-radius: 3px;
        font-weight: 700;
        font-size: 11px;
    }
    .badge-side-short {
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
        padding: 2px 6px;
        border-radius: 3px;
        font-weight: 700;
        font-size: 11px;
    }

    .metric-box {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 6px;
        padding: 10px 12px;
        margin-top: 8px;
    }
    .metric-label {
        font-size: 10px;
        color: #64748b;
        text-transform: uppercase;
    }
    .metric-num {
        font-size: 14px;
        font-weight: bold;
        color: #cbd5e1;
    }

    @media (max-width: 768px) {
        .status-grid {
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 8px !important;
        }
        .status-card {
            padding: 10px !important;
        }
        .open-pos-grid {
            grid-template-columns: 1fr !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# =========================================================================
# 2. DEFINICIÓN DE ACTIVOS NATIVOS KRAKEN (18 PARES USD) Y CONSTANTES
# =========================================================================
WATCHLIST_18 = [
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD",
    "XRP/USD", "DOT/USD", "AVAX/USD", "LINK/USD",
    "LTC/USD", "BCH/USD", "NEAR/USD", "SUI/USD",
    "APT/USD", "FET/USD", "ARB/USD", "PEPE/USD",
    "DOGE/USD", "SHIB/USD"
]

MAX_CONCURRENT_POSITIONS = 3

# =========================================================================
# 3. FUNCIONES DE ZONA HORARIA COLOMBIA (COT / UTC-5) Y CICLO SEMANAL
# =========================================================================
def get_now_cot() -> datetime.datetime:
    """Retorna la fecha y hora actual en zona horaria Colombia (America/Bogota)."""
    return datetime.datetime.now(TZ_COLOMBIA)

def get_now_utc() -> datetime.datetime:
    """Retorna la fecha y hora actual en UTC."""
    return datetime.datetime.now(datetime.timezone.utc)

def parse_utc_datetime(raw_ts) -> datetime.datetime:
    """Convierte cualquier formato de timestamp a objeto datetime consciente de UTC."""
    if not raw_ts:
        return get_now_utc()
    try:
        if isinstance(raw_ts, str):
            clean_str = raw_ts.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(clean_str)
        elif isinstance(raw_ts, (int, float)):
            ts_sec = float(raw_ts) / 1000.0 if float(raw_ts) > 100000000000 else float(raw_ts)
            dt = datetime.datetime.fromtimestamp(ts_sec, tz=datetime.timezone.utc)
        elif isinstance(raw_ts, datetime.datetime):
            dt = raw_ts
        else:
            return get_now_utc()

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        return get_now_utc()

def to_cot_datetime(raw_ts) -> datetime.datetime:
    """Convierte cualquier timestamp a datetime en zona horaria Colombia (COT)."""
    dt_utc = parse_utc_datetime(raw_ts)
    return dt_utc.astimezone(TZ_COLOMBIA)

def get_weekly_cycle_bounds():
    """
    Calcula los límites del ciclo semanal actual:
    Rango: Domingo 00:00 UTC (Sábado 7:00 PM COT) a Sábado 23:59:59 UTC.
    En Python weekday(): Lunes=0, ..., Sábado=5, Domingo=6.
    Días transcurridos desde el último Domingo: (weekday + 1) % 7.
    """
    now_u = get_now_utc()
    days_since_sunday = (now_u.weekday() + 1) % 7
    cycle_start_utc = now_u.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=days_since_sunday)
    cycle_end_utc = cycle_start_utc + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    
    cycle_start_cot = cycle_start_utc.astimezone(TZ_COLOMBIA)
    cycle_end_cot = cycle_end_utc.astimezone(TZ_COLOMBIA)
    
    return {
        "start_utc": cycle_start_utc,
        "end_utc": cycle_end_utc,
        "start_cot": cycle_start_cot,
        "end_cot": cycle_end_cot
    }

# =========================================================================
# 4. CONEXIÓN SUPABASE & AUDIT LOG EN HORA COLOMBIA (COT)
# =========================================================================
ENV_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
ENV_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if "local_paper_trades" not in st.session_state:
    st.session_state.local_paper_trades = []

if "system_logs" not in st.session_state:
    st.session_state.system_logs = []

def add_log(message: str, level: str = "INFO"):
    """Registra eventos en el Audit Log con prefijo obligatorio [HH:MM:SS COT]."""
    timestamp_cot = get_now_cot().strftime("%H:%M:%S COT")
    st.session_state.system_logs.insert(0, f"[{timestamp_cot}] [{level}] {message}")
    if len(st.session_state.system_logs) > 60:
        st.session_state.system_logs.pop()

# =========================================================================
# 5. SISTEMA DE NOTIFICACIONES PUSH AUTOMÁTICAS (NTFY.SH)
# =========================================================================
def enviar_notificacion_push(titulo: str, mensaje: str):
    """
    Función Helper de Notificaciones Push mediante HTTP POST a Ntfy.sh.
    Canal: https://ntfy.sh/PROYECTO_DIPPER_BOT_ALERTAS
    Los errores de red NUNCA interrumpen el flujo ni el monitoreo del bot.
    """
    try:
        url = "https://ntfy.sh/PROYECTO_DIPPER_BOT_ALERTAS"
        safe_title = titulo.encode('latin-1', 'ignore').decode('latin-1').strip()
        if not safe_title:
            safe_title = "PROYECTO DIPPER | ALERTA"
        if HAS_REQUESTS_LIB:
            requests.post(url, data=mensaje.encode('utf-8'), headers={"Title": safe_title}, timeout=5)
        else:
            import urllib.request
            req = urllib.request.Request(url, data=mensaje.encode('utf-8'), headers={"Title": safe_title}, method='POST')
            with urllib.request.urlopen(req, timeout=5) as resp:
                pass
    except Exception as e:
        print(f"Error enviando notificación push: {e}")

@st.cache_resource
def get_supabase_client(url: str, key: str):
    if HAS_SUPABASE_LIB and url and key:
        try:
            client = create_client(url, key)
            return client
        except Exception:
            return None
    return None

supabase_client = get_supabase_client(ENV_SUPABASE_URL, ENV_SUPABASE_KEY)

# =========================================================================
# 6. CONEXIÓN A KRAKEN SPOT REST CON RESOLUCIÓN ROBUSTA
# =========================================================================
@st.cache_resource
def get_kraken_exchange():
    ex = ccxt.kraken({
        'enableRateLimit': True,
        'timeout': 15000,
    })
    try:
        ex.load_markets()
    except Exception:
        pass
    return ex

exchange = get_kraken_exchange()

def resolve_kraken_symbol(ex, symbol: str) -> str:
    """Mapea símbolos estándar a identificadores internos de Kraken Spot."""
    if not ex.markets:
        try:
            ex.load_markets()
        except Exception:
            return symbol

    if symbol in ex.markets:
        return symbol

    base, quote = symbol.split('/') if '/' in symbol else (symbol, 'USD')
    aliases = [
        f"XBT/{quote}" if base == "BTC" else "",
        f"XDG/{quote}" if base == "DOGE" else "",
        f"XXBTZ{quote}" if base == "BTC" else "",
        f"{base}/USDT",
        f"{base}/USD"
    ]
    for alt in aliases:
        if alt and alt in ex.markets:
            return alt

    return symbol

@st.cache_data(ttl=20, show_spinner=False)
def fetch_market_data(symbol='BTC/USD', timeframe='15m', limit=50):
    """Obtiene velas reales y calcula EMA 200, ATR y RSI sobre precios de cierre reales."""
    try:
        ex = get_kraken_exchange()
        target_symbol = resolve_kraken_symbol(ex, symbol)
        
        ohlcv = ex.fetch_ohlcv(target_symbol, timeframe=timeframe, limit=limit)
        
        if ohlcv and len(ohlcv) > 0:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['time_label'] = df['timestamp'].dt.strftime('%d/%m %H:%M')
            
            # EMA 200 real
            span_val = 200 if len(df) >= 200 else max(10, len(df))
            df['ema200'] = df['close'].ewm(span=span_val, adjust=False).mean()
            
            # ATR (14)
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = tr.rolling(min(14, len(df))).mean().bfill()
            df['atr_mean_long'] = tr.rolling(min(50, len(df))).mean().bfill()
            
            # RSI (14)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(min(14, len(df))).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(min(14, len(df))).mean()
            rs = gain / (loss + 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))
            df['rsi'] = df['rsi'].bfill()
            
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# =========================================================================
# 7. MOTOR DE CONFLUENCIA Y FILTRO MACRO
# =========================================================================
def evaluate_confluence(df: pd.DataFrame):
    if df.empty or len(df) < 10:
        return {
            "side": "NEUTRAL",
            "score": 0,
            "reason": "Sincronizando feed de mercado Kraken...",
            "price": 0.0,
            "ema": 0.0,
            "atr": 0.0,
            "rsi": 50.0
        }
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(last['close'])
    ema = float(last['ema200'])
    atr = float(last['atr'])
    rsi = float(last['rsi'])
    
    score = 0
    reasons = []
    
    # 1. Estructura vs EMA 200 (+40)
    if close > ema:
        side = "LONG"
        score += 40
        reasons.append("Precio > EMA 200")
    else:
        side = "SHORT"
        score += 40
        reasons.append("Precio < EMA 200")
    
    # 2. Impulso Direccional (+25)
    if (side == "LONG" and close > prev['close']) or (side == "SHORT" and close < prev['close']):
        score += 25
        reasons.append("Impulso direccional consistente")
    
    # 3. Volatilidad ATR (+20)
    if atr > 0:
        score += 20
        reasons.append("Volatilidad ATR suficiente")
        
    # 4. RSI (+15)
    if (side == "LONG" and 45 <= rsi <= 68) or (side == "SHORT" and 32 <= rsi <= 55):
        score += 15
        reasons.append("RSI en zona favorable")

    return {
        "side": side,
        "score": score,
        "reason": " • ".join(reasons),
        "price": close,
        "ema": ema,
        "atr": atr,
        "rsi": rsi
    }

def evaluate_macro_filter(df: pd.DataFrame, force_status: str = "AUTO"):
    if force_status == "FORZAR_BLOQUEO":
        return False, "BLOQUEADO (SIMULACIÓN MACRO)"
    if force_status == "FORZAR_SEGURO":
        return True, "ACTIVO (Ventana Segura)"
        
    if df.empty or len(df) < 15:
        return True, "ACTIVO (Ventana Segura)"
    
    last = df.iloc[-1]
    atr_current = float(last.get('atr', 0))
    atr_mean = float(last.get('atr_mean_long', atr_current))
    
    if atr_mean > 0 and (atr_current / atr_mean) > 2.6:
        return False, "BLOQUEADO (VOLATILIDAD EXTREMA)"
    
    return True, "ACTIVO (Ventana Segura)"

# =========================================================================
# 8. NORMALIZACIÓN DE PNL Y GESTIÓN DE BASE DE DATOS
# =========================================================================
def normalize_trade_data(trade: dict, operational_capital: float = 1000.0) -> dict:
    """
    Normaliza y sanea registros de trading con riesgo institucional estricto:
      - Stop Loss (-1.5%): PnL_USD = -1 * (capital_operativo * 0.015) [-$15.00 USD para base $1,000]
      - Take Profit (+3.0%): PnL_USD = capital_operativo * 0.030     [+$30.00 USD para base $1,000]
      - Signo negativo estrictamente garantizado en SL para evitar bugs en SHORT o LONG.
    """
    if not isinstance(trade, dict):
        return trade
        
    t = dict(trade)
    status_str = str(t.get("status", "")).upper()
    
    if "CERRADO" in status_str or "CLOSED" in status_str:
        raw_pnl_usd = t.get("pnl_usd")
        raw_pnl_pct = t.get("pnl_pct")
        side_str = str(t.get("side", "")).upper()
        
        entry_price = float(t.get("entry_price") or 0.0)
        exit_price = float(t.get("exit_price") or 0.0)
        
        try:
            pnl_usd = float(raw_pnl_usd) if raw_pnl_usd is not None else None
        except (ValueError, TypeError):
            pnl_usd = None
            
        try:
            pnl_pct = float(raw_pnl_pct) if raw_pnl_pct is not None else None
        except (ValueError, TypeError):
            pnl_pct = None
            
        is_sl = "SL" in status_str or "STOP" in status_str
        is_tp = "TP" in status_str or "PROFIT" in status_str
        
        if not is_sl and not is_tp and entry_price > 0 and exit_price > 0:
            if side_str == "SHORT":
                if exit_price > entry_price:
                    is_sl = True
                elif exit_price < entry_price:
                    is_tp = True
            elif side_str == "LONG":
                if exit_price < entry_price:
                    is_sl = True
                elif exit_price > entry_price:
                    is_tp = True
                    
        if "SL" in status_str:
            is_sl = True
            is_tp = False
            
        if is_sl:
            t["status"] = "CERRADO (SL)"
            fixed_pct = -1.0 * abs(pnl_pct if (pnl_pct is not None and pnl_pct != 0) else 1.5)
            if pnl_usd is None or pnl_usd >= 0 or abs(pnl_usd) > (operational_capital * 0.15):
                fixed_usd = -1.0 * round(operational_capital * (abs(fixed_pct) / 100.0), 2)
            else:
                fixed_usd = -1.0 * abs(pnl_usd)
                
            t["pnl_pct"] = round(fixed_pct, 2)
            t["pnl_usd"] = round(fixed_usd, 2)
            
        elif is_tp:
            t["status"] = "CERRADO (TP)"
            fixed_pct = abs(pnl_pct if (pnl_pct is not None and pnl_pct != 0) else 3.0)
            if pnl_usd is None or pnl_usd <= 0 or abs(pnl_usd) > (operational_capital * 0.15):
                fixed_usd = round(operational_capital * (fixed_pct / 100.0), 2)
            else:
                fixed_usd = abs(pnl_usd)
                
            t["pnl_pct"] = round(fixed_pct, 2)
            t["pnl_usd"] = round(fixed_usd, 2)
            
        else:
            if pnl_usd is not None and abs(pnl_usd) > (operational_capital * 0.15):
                if (pnl_pct is not None and pnl_pct < 0) or pnl_usd < 0:
                    t["pnl_pct"] = -1.5
                    t["pnl_usd"] = -1.0 * round(operational_capital * 0.015, 2)
                else:
                    t["pnl_pct"] = 3.0
                    t["pnl_usd"] = round(operational_capital * 0.030, 2)
            else:
                if pnl_usd is not None:
                    t["pnl_usd"] = round(pnl_usd, 2)
                if pnl_pct is not None:
                    t["pnl_pct"] = round(pnl_pct, 2)
                
    return t

def fix_and_normalize_supabase_trades(operational_capital: float = 1000.0) -> int:
    """Sanea órdenes en Supabase con riesgo institucional y signo estricto."""
    fixed_count = 0
    for i, t in enumerate(st.session_state.local_paper_trades):
        cleaned = normalize_trade_data(t, operational_capital)
        if cleaned != t:
            st.session_state.local_paper_trades[i] = cleaned
            fixed_count += 1
            
    if supabase_client:
        try:
            res = supabase_client.table("paper_trades").select("*").execute()
            if res.data:
                for record in res.data:
                    status = str(record.get("status", "")).upper()
                    if "CERRADO" in status or "CLOSED" in status:
                        raw_pnl = record.get("pnl_usd")
                        try:
                            pnl_val = float(raw_pnl) if raw_pnl is not None else 0.0
                        except Exception:
                            pnl_val = 0.0
                            
                        needs_fix = False
                        if "SL" in status and pnl_val >= 0:
                            needs_fix = True
                        elif abs(pnl_val) > (operational_capital * 0.15) or pnl_val == 0.0:
                            needs_fix = True
                            
                        if needs_fix:
                            cleaned = normalize_trade_data(record, operational_capital)
                            update_payload = {
                                "pnl_usd": float(cleaned["pnl_usd"]),
                                "pnl_pct": float(cleaned["pnl_pct"])
                            }
                            rec_id = record.get("id")
                            rec_order_id = record.get("order_id")
                            if rec_id is not None:
                                supabase_client.table("paper_trades").update(update_payload).eq("id", rec_id).execute()
                            elif rec_order_id is not None:
                                supabase_client.table("paper_trades").update(update_payload).eq("order_id", str(rec_order_id)).execute()
                            fixed_count += 1
        except Exception as e:
            add_log(f"Aviso al sanear Supabase: {str(e)}", "WARN")
            
    add_log(f"Normalización completada: {fixed_count} órdenes saneadas con riesgo institucional.", "SUCCESS")
    return fixed_count

def reset_all_trades_supabase() -> bool:
    """
    REQUERIMIENTO 4: Reset Manual para limpiar Supabase y restablecer el saldo a $1,000.00 USD.
    Elimina los registros existentes en paper_trades y reinicia la memoria local.
    """
    st.session_state.local_paper_trades = []
    if supabase_client:
        try:
            supabase_client.table("paper_trades").delete().neq("id", -999999).execute()
            add_log("Base de datos de paper_trades reseteada en Supabase. Saldo restablecido a $1,000.00 USD.", "WARN")
            return True
        except Exception as e:
            add_log(f"Error reseteando Supabase: {str(e)}", "ERROR")
            return False
    else:
        add_log("Memoria local de paper_trades reseteada. Saldo restablecido a $1,000.00 USD.", "WARN")
        return True

def fetch_all_trades_supabase(operational_capital: float = 1000.0):
    """Recupera órdenes legítimas desde Supabase o memoria local, aplicando normalización de datos."""
    trades_raw = []
    if supabase_client:
        try:
            res = supabase_client.table("paper_trades").select("*").order("timestamp", desc=True).execute()
            if res.data is not None:
                trades_raw = res.data
        except Exception as e:
            add_log(f"Error consultando Supabase: {str(e)}", "ERROR")
            trades_raw = st.session_state.local_paper_trades
    else:
        trades_raw = st.session_state.local_paper_trades

    return [normalize_trade_data(t, operational_capital) for t in trades_raw]

def get_all_open_positions(operational_capital: float = 1000.0):
    """Retorna todas las posiciones actualmente abiertas (OPEN) en el portafolio."""
    all_trades = fetch_all_trades_supabase(operational_capital)
    return [t for t in all_trades if str(t.get("status", "")).upper() == "OPEN"]

def check_existing_open_position_for_symbol(symbol: str, operational_capital: float = 1000.0):
    """Verifica si ya existe una posición abierta para el par específico (Máximo 1 por par)."""
    open_positions = get_all_open_positions(operational_capital)
    for t in open_positions:
        if t.get("symbol") == symbol:
            return True, t
    return False, None

# =========================================================================
# 9. RECALCULADOR DE BALANCE / EQUITY Y CICLO SEMANAL
# =========================================================================
def calculate_weekly_capital_metrics(initial_capital: float = 1000.0):
    """
    REQUERIMIENTO 4: Recalcula Win Rate y PnL filtrando las operaciones dentro del rango:
    Domingo 00:00 UTC (Sábado 7:00 PM COT) a Sábado 23:59 UTC.
    Capital Actual (Equity) = Capital Inicial + SUMA(PnL_USD de todos los trades cerrados históricos).
    """
    all_trades = fetch_all_trades_supabase(operational_capital=initial_capital)
    
    # 1. Todos los trades cerrados históricos
    all_closed_trades = [
        t for t in all_trades 
        if "CERRADO" in str(t.get("status", "")).upper() or "CLOSED" in str(t.get("status", "")).upper()
    ]
    
    total_closed_pnl_usd = sum(float(t.get("pnl_usd", 0.0) or 0.0) for t in all_closed_trades)
    current_equity = initial_capital + total_closed_pnl_usd
    total_pnl_pct = (total_closed_pnl_usd / initial_capital * 100.0) if initial_capital > 0 else 0.0
    
    # 2. Filtrado exacto dentro del rango semanal
    cycle = get_weekly_cycle_bounds()
    cycle_start_u = cycle["start_utc"]
    cycle_end_u = cycle["end_utc"]
    
    weekly_closed_trades = []
    for t in all_closed_trades:
        trade_dt_u = parse_utc_datetime(t.get("timestamp"))
        if cycle_start_u <= trade_dt_u <= cycle_end_u:
            weekly_closed_trades.append(t)
                
    weekly_pnl_usd = sum(float(t.get("pnl_usd", 0.0) or 0.0) for t in weekly_closed_trades)
    winning_trades = sum(1 for t in weekly_closed_trades if float(t.get("pnl_usd", 0.0) or 0.0) > 0)
    losing_trades = sum(1 for t in weekly_closed_trades if float(t.get("pnl_usd", 0.0) or 0.0) < 0)
    total_closed_weekly = len(weekly_closed_trades)
    
    weekly_pnl_pct = (weekly_pnl_usd / initial_capital * 100.0) if initial_capital > 0 else 0.0
    win_rate = (winning_trades / total_closed_weekly * 100.0) if total_closed_weekly > 0 else 0.0
    
    return {
        "initial_capital": initial_capital,
        "current_equity": current_equity,
        "total_closed_pnl_usd": total_closed_pnl_usd,
        "total_pnl_pct": total_pnl_pct,
        "weekly_pnl_usd": weekly_pnl_usd,
        "weekly_pnl_pct": weekly_pnl_pct,
        "win_rate": win_rate,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "total_closed": total_closed_weekly,
        "all_closed_count": len(all_closed_trades),
        "trades": weekly_closed_trades,
        "cycle": cycle
    }

# =========================================================================
# 10. FIREWALL DIARIO (-3.0% CIRCUIT BREAKER)
# =========================================================================
def calculate_daily_firewall(capital: float, max_loss_pct: float = 3.0):
    today_cot = get_now_cot().date()
    max_allowed_loss_usd = -1.0 * abs(capital * (max_loss_pct / 100.0))
    
    all_trades = fetch_all_trades_supabase(operational_capital=capital)
    daily_pnl_usd = 0.0
    daily_trades_count = 0
    
    for t in all_trades:
        status = str(t.get("status", "")).upper()
        if "CERRADO" in status or "CLOSED" in status:
            trade_dt_cot = to_cot_datetime(t.get("timestamp")).date()
            if trade_dt_cot == today_cot:
                pnl = float(t.get("pnl_usd", 0.0) or 0.0)
                daily_pnl_usd += pnl
                daily_trades_count += 1
    
    is_circuit_breaker = daily_pnl_usd <= max_allowed_loss_usd
    
    return {
        "daily_pnl_usd": daily_pnl_usd,
        "daily_pnl_pct": (daily_pnl_usd / capital) * 100.0 if capital > 0 else 0.0,
        "is_circuit_breaker": is_circuit_breaker,
        "max_allowed_loss_usd": max_allowed_loss_usd,
        "daily_trades_count": daily_trades_count,
        "status_text": "BLOQUEADO (-3.0% ALCANZADO)" if is_circuit_breaker else "OPERATIVO"
    }

# =========================================================================
# 11. EVALUACIÓN Y CIERRE DE POSICIONES OPEN (GESTIÓN DE RIESGO ESTRICTA)
# =========================================================================
def evaluate_and_close_open_positions(operational_capital: float = 1000.0):
    """
    Monitorea de forma iterativa todas las posiciones OPEN en el portafolio.
    Consulta el precio en vivo del par EXACTO correspondiente a cada orden.
    Ejecuta salidas automáticas por Take Profit (+3.0%) o Stop Loss (-1.5%).
    En Stop Loss el PnL es ESTRICTAMENTE NEGATIVO (-$15.00 USD para base $1,000).
    """
    open_positions = get_all_open_positions(operational_capital)
    if not open_positions:
        return
    
    for trade in open_positions:
        sym = trade.get("symbol", "BTC/USD")
        trade_id = trade.get("id")
        order_id = trade.get("order_id", f"DIP-{trade_id}")
        side = trade.get("side", "LONG")
        entry_price = float(trade.get("entry_price", 0.0))
        sl = float(trade.get("sl", entry_price * 0.985 if side == "LONG" else entry_price * 1.015))
        tp = float(trade.get("tp", entry_price * 1.030 if side == "LONG" else entry_price * 0.970))
        
        pos_capital = float(trade.get("capital") or trade.get("position_size_usd") or operational_capital)
        if pos_capital <= 0:
            pos_capital = operational_capital
            
        df_sym = fetch_market_data(sym, limit=10)
        if df_sym.empty:
            continue
        current_price = float(df_sym.iloc[-1]['close'])
        
        closed = False
        status = "OPEN"
        pnl_usd = 0.0
        pnl_pct = 0.0
        
        if side == "LONG":
            if current_price >= tp:
                closed = True
                status = "CERRADO (TP)"
                pnl_pct = 3.0
                pnl_usd = pos_capital * 0.030
            elif current_price <= sl:
                closed = True
                status = "CERRADO (SL)"
                pnl_pct = -1.5
                pnl_usd = -1.0 * (pos_capital * 0.015)
                
        elif side == "SHORT":
            if current_price <= tp:
                closed = True
                status = "CERRADO (TP)"
                pnl_pct = 3.0
                pnl_usd = pos_capital * 0.030
            elif current_price >= sl:
                closed = True
                status = "CERRADO (SL)"
                pnl_pct = -1.5
                pnl_usd = -1.0 * (pos_capital * 0.015)
        
        if closed:
            if "SL" in status:
                pnl_pct = -1.0 * abs(float(pnl_pct if pnl_pct != 0 else 1.5))
                pnl_usd = -1.0 * abs(float(pnl_usd if pnl_usd != 0 else (pos_capital * 0.015)))
            elif "TP" in status:
                pnl_pct = abs(float(pnl_pct if pnl_pct != 0 else 3.0))
                pnl_usd = abs(float(pnl_usd if pnl_usd != 0 else (pos_capital * 0.030)))
                
            clean_status = str(status)
            clean_exit_price = float(round(float(current_price), 4))
            clean_pnl_usd = float(round(float(pnl_usd), 2))
            clean_pnl_pct = float(round(float(pnl_pct), 2))
            exit_ts_iso = get_now_utc().isoformat()
            
            # Payload compatible con Supabase (SIN closed_at)
            update_payload = {
                "status": clean_status,
                "exit_price": clean_exit_price,
                "pnl_usd": clean_pnl_usd,
                "pnl_pct": clean_pnl_pct
            }
            
            if supabase_client:
                try:
                    query = supabase_client.table("paper_trades").update(update_payload)
                    if trade_id is not None:
                        query.eq("id", trade_id).execute()
                    else:
                        query.eq("order_id", str(order_id)).execute()
                except Exception as e_up:
                    try:
                        fallback_payload = {
                            "status": clean_status,
                            "exit_price": clean_exit_price,
                            "pnl": clean_pnl_usd
                        }
                        f_query = supabase_client.table("paper_trades").update(fallback_payload)
                        if trade_id is not None:
                            f_query.eq("id", trade_id).execute()
                        else:
                            f_query.eq("order_id", str(order_id)).execute()
                    except Exception as e_fb:
                        add_log(f"Aviso actualizando orden en Supabase: {str(e_fb)}", "WARN")
            
            for local_t in st.session_state.local_paper_trades:
                if local_t.get("order_id") == order_id or local_t.get("id") == trade_id:
                    local_t.update(update_payload)
                    local_t["exit_time_cot"] = get_now_cot().strftime("%H:%M:%S")
                    break
            
            log_type = "SUCCESS" if pnl_usd > 0 else "WARN"
            hora_salida_str = get_now_cot().strftime("%H:%M:%S")
            add_log(f"POSICIÓN CERRADA ({hora_salida_str} COT): {order_id} ({side}) en {sym} a ${current_price:,.4f} | {status} | PnL: ${pnl_usd:+.2f} USD ({pnl_pct:+.1f}%)", log_type)
            
            # Notificación Push Ntfy.sh
            icono_push = "🎯" if "TP" in status else "🛑"
            titulo_push = f"{icono_push} POSICIÓN CERRADA: {sym} [{side}] - {status}"
            signo_usd = "+" if pnl_usd > 0 else "-"
            mensaje_push = (
                f"📊 Par: {sym}\n"
                f"📈 Tipo: {side}\n"
                f"🚪 Motivo de Cierre: {status}\n"
                f"💵 Precio Cierre: ${current_price:,.4f}\n"
                f"📊 PnL (%): {pnl_pct:+.2f}%\n"
                f"💰 PnL ($ USD): {signo_usd}${abs(pnl_usd):,.2f} USD\n"
                f"🕐 Hora Cierre: {hora_salida_str} COT\n"
                f"⚡ ID Orden: {order_id}"
            )
            enviar_notificacion_push(titulo_push, mensaje_push)

# =========================================================================
# 12. MOTOR DE EJECUCIÓN AUTÓNOMO (LÍMITE 3 POSICIONES CONCURRENTES)
# =========================================================================
def execute_autotrigger(symbol: str, signal: dict, is_firewall_locked: bool, is_macro_safe: bool, capital_base: float = 1000.0):
    score = signal.get("score", 0)
    side = signal.get("side", "NEUTRAL")
    entry_price = signal.get("price", 0.0)
    
    if score < 75 or side not in ["LONG", "SHORT"]:
        return False, "Score insuficiente para gatillo autónomo (Mínimo: 75 pts)"
    
    if is_firewall_locked:
        return False, "AUTOTRIGGER BLOQUEADO: Circuit Breaker Diario (-3.0%) activado."
        
    if not is_macro_safe:
        return False, "AUTOTRIGGER BLOQUEADO: Filtro Macro detecta volatilidad extrema."
        
    # REGLA 1: MÁXIMO 3 POSICIONES CONCURRENTES
    all_open = get_all_open_positions(capital_base)
    if len(all_open) >= MAX_CONCURRENT_POSITIONS:
        return False, f"Límite de posiciones concurrentes alcanzado (Máximo {MAX_CONCURRENT_POSITIONS} abiertas)"
        
    # REGLA 2: MÁXIMO 1 POSICIÓN POR PAR
    has_symbol_open, existing_order = check_existing_open_position_for_symbol(symbol, capital_base)
    if has_symbol_open:
        order_code = existing_order.get("order_id", "N/A")
        return False, f"Ya existe una posición abierta ({order_code}) para {symbol} (Máximo 1 por par)"
    
    if side == "LONG":
        tp = entry_price * 1.030
        sl = entry_price * 0.985
    else:
        tp = entry_price * 0.970
        sl = entry_price * 1.015
        
    now_utc_dt = get_now_utc()
    order_id = f"DIP-{int(now_utc_dt.timestamp())}"
    now_iso = now_utc_dt.isoformat()
    now_cot_str = get_now_cot().strftime("%H:%M:%S")
    
    trade_data = {
        "order_id": str(order_id),
        "timestamp": str(now_iso),
        "symbol": str(symbol),
        "side": str(side),
        "entry_price": float(round(float(entry_price), 4)),
        "exit_price": None,
        "sl": float(round(float(sl), 4)),
        "tp": float(round(float(tp), 4)),
        "status": "OPEN",
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "confluence": int(score),
        "reason": str(signal.get("reason", "Confluencia Multiactivo Kraken Spot"))
    }
    
    inserted = False
    if supabase_client:
        try:
            res = supabase_client.table("paper_trades").insert(trade_data).execute()
            if res.data:
                inserted = True
                add_log(f"AUTOTRIGGER REGISTRADO EN SUPABASE: {order_id} {side} {symbol} @ ${entry_price:,.4f} [TP: ${tp:,.4f} | SL: ${sl:,.4f}]", "SUCCESS")
        except Exception as e:
            add_log(f"Error insertando trade en Supabase: {str(e)}", "ERROR")
            
    if not inserted:
        trade_data["id"] = len(st.session_state.local_paper_trades) + 1
        st.session_state.local_paper_trades.insert(0, trade_data)
        add_log(f"AUTOTRIGGER LOCAL REGISTRADO: {order_id} {side} {symbol} @ ${entry_price:,.4f}", "SUCCESS")
        
    # Push Alerta 1: Apertura
    titulo_push = f"🟢 NUEVA POSICIÓN: {symbol} [{side}]"
    mensaje_push = (
        f"📊 Par: {symbol}\n"
        f"📈 Tipo: {side}\n"
        f"💵 Precio Entrada: ${entry_price:,.4f}\n"
        f"🎯 Take Profit (+3.0%): ${tp:,.4f}\n"
        f"🛡️ Stop Loss (-1.5%): ${sl:,.4f}\n"
        f"🕐 Hora Entrada: {now_cot_str} COT\n"
        f"⚡ ID Orden: {order_id}\n"
        f"🔥 Score: {score}/100"
    )
    enviar_notificacion_push(titulo_push, mensaje_push)
    
    return True, f"¡Orden Autónoma {order_id} abierta para {symbol} [{side}]!"

# =========================================================================
# 13. ESCANEO ITERATIVO DE LOS 18 PARES NATIVOS
# =========================================================================
def scan_all_18_watchlist():
    scan_results = []
    for sym in WATCHLIST_18:
        try:
            df_sym = fetch_market_data(sym, timeframe='15m', limit=30)
            sig = evaluate_confluence(df_sym)
            scan_results.append({
                "symbol": sym,
                "price": sig["price"],
                "score": sig["score"],
                "side": sig["side"],
                "rsi": sig["rsi"],
                "reason": sig["reason"]
            })
        except Exception:
            continue
    return scan_results

# =========================================================================
# 14. ENCABEZADO Y SIDEBAR INSTITUCIONAL
# =========================================================================
hora_actual_cot = get_now_cot().strftime("%H:%M:%S COT")
fecha_actual_cot = get_now_cot().strftime("%Y-%m-%d")

st.markdown(f"""
<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px;">
    <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 26px; line-height: 1;">⚡</span>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 19px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;">PROYECTO DIPPER</span>
                <span style="background: #1e293b; color: #38bdf8; font-size: 10px; padding: 3px 8px; border-radius: 4px; font-weight: 700; border: 1px solid #334155;">QUANT TERMINAL v2.8</span>
                <span class="badge-auto">COLOMBIA (COT UTC-5) · MÁX 3 OPEN</span>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">
                KRAKEN SPOT USD · ROW-LEVEL STYLING · CICLO SEMANAL DOM-SÁB · SUPABASE POSTGRESQL
            </div>
        </div>
    </div>
    <div style="font-size: 11px; color: #64748b; text-align: right;">
        HORA LOCAL: <span style="color: #38bdf8; font-weight: bold;">{hora_actual_cot}</span> ({fecha_actual_cot}) &nbsp;|&nbsp;
        ESTADO: <span style="color: #34d399; font-weight: bold;">ONLINE</span>
    </div>
</div>
""", unsafe_allow_html=True)

# SIDEBAR: PARÁMETROS DEL SISTEMA
with st.sidebar:
    st.markdown("### ⚙️ PARÁMETROS DEL SISTEMA")
    
    selected_symbol = st.selectbox(
        "Par en Inspección Detallada (18 Pares USD)",
        WATCHLIST_18,
        index=0,
        help="Selecciona cualquiera de las 18 criptomonedas nativas en USD de Kraken Spot"
    )
    timeframe = st.selectbox("Temporalidad", ["15m", "1h", "4h"], index=0)
    
    st.markdown("---")
    st.markdown("### 🛡️ MATRIZ DE RIESGO & PORTAFOLIO")
    capital = st.number_input("Capital Operativo ($ USD)", value=1000.0, step=100.0, min_value=100.0)
    
    st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">Límite de Posiciones Concurrentes</div>
            <div class="metric-num" style="color: #38bdf8;">MÁXIMO 3 ABIERTAS</div>
            <div class="metric-label" style="margin-top: 6px;">Riesgo Fijo / Posición (-1.5% SL)</div>
            <div class="metric-num" style="color: #ef4444;">-${capital * 0.015:.2f} USD</div>
            <div class="metric-label" style="margin-top: 6px;">Beneficio Fijo / Posición (+3.0% TP)</div>
            <div class="metric-num" style="color: #10b981;">+${capital * 0.030:.2f} USD</div>
            <div class="metric-label" style="margin-top: 6px;">Circuit Breaker Diario (-3.0%)</div>
            <div class="metric-num" style="color: #f87171;">-${capital * 0.030:.2f} USD</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🌐 FILTRO MACRO DINÁMICO")
    macro_override = st.selectbox(
        "Modo Filtro Macro",
        ["AUTO", "FORZAR_SEGURO", "FORZAR_BLOQUEO"],
        format_func=lambda x: "AUTOMÁTICO (Régimen Algorítmico)" if x == "AUTO" else ("FORZAR VENTANA SEGURA" if x == "FORZAR_SEGURO" else "FORZAR BLOQUEO MACRO")
    )
    
    st.markdown("---")
    st.markdown("### 🇨🇴 ZONA HORARIA & CICLO")
    st.caption("America/Bogota (COT, UTC-5)")
    st.caption("Ciclo Semanal: Domingo 00:00 UTC (Sábado 7:00 PM COT) a Sábado 23:59 UTC.")
    
    st.markdown("---")
    auto_refresh_enabled = st.checkbox("Refresco Automático (30s)", value=True)
    if st.button("⚡ Escanear Ahora (18 Pares USD)"):
        st.rerun()

    st.markdown("---")
    st.markdown("### 🔔 ALERTAS PUSH (NTFY.SH)")
    st.caption("Canal: [ntfy.sh/PROYECTO_DIPPER_BOT_ALERTAS](https://ntfy.sh/PROYECTO_DIPPER_BOT_ALERTAS)")
    if st.button("📲 Probar Alerta Push"):
        enviar_notificacion_push(
            "🔔 TEST DE CONEXIÓN | PROYECTO DIPPER",
            f"Alerta Push Ntfy.sh operativa.\nHora COT: {get_now_cot().strftime('%H:%M:%S COT')}\nMonitoreando 18 pares nativos en USD de Kraken Spot."
        )
        st.success("¡Alerta enviada a ntfy.sh/PROYECTO_DIPPER_BOT_ALERTAS!")

if auto_refresh_enabled:
    st.markdown("""
        <script>
            setTimeout(function(){
                window.location.reload();
            }, 30000);
        </script>
    """, unsafe_allow_html=True)

# EJECUCIÓN DEL CICLO EN TIEMPO REAL
# 1. Monitoreo y cierre de posiciones OPEN activas
evaluate_and_close_open_positions(operational_capital=capital)

# 2. Datos del par en inspección
df_inspected = fetch_market_data(selected_symbol, timeframe, limit=50)
signal_inspected = evaluate_confluence(df_inspected)
is_macro_safe, macro_status_str = evaluate_macro_filter(df_inspected, macro_override)

# 3. Estado de Firewall y Portafolio
firewall = calculate_daily_firewall(capital, max_loss_pct=3.0)
is_circuit_breaker = firewall["is_circuit_breaker"]
open_positions = get_all_open_positions(operational_capital=capital)
open_positions_count = len(open_positions)

# Disparador Push: Circuit Breaker Diario
if "cb_push_sent" not in st.session_state:
    st.session_state.cb_push_sent = False

if is_circuit_breaker and not st.session_state.cb_push_sent:
    titulo_cb = "🚨 ALERTA URGENTE: Circuit Breaker Activado (-3.0%)"
    mensaje_cb = (
        f"🛑 BLOQUEO DE SEGURIDAD ACTIVADO\n"
        f"Drawdown Diario: ${firewall['daily_pnl_usd']:,.2f} USD ({firewall['daily_pnl_pct']:.2f}%)\n"
        f"Límite Máximo: ${firewall['max_allowed_loss_usd']:,.2f} USD (-3.0%)\n"
        f"Hora: {get_now_cot().strftime('%H:%M:%S COT')}\n"
        f"Nuevas órdenes bloqueadas hasta el próximo ciclo."
    )
    enviar_notificacion_push(titulo_cb, mensaje_cb)
    st.session_state.cb_push_sent = True
elif not is_circuit_breaker:
    st.session_state.cb_push_sent = False

# 4. Escaneo automático y posible Autotrigger
scanner_data = scan_all_18_watchlist()

if not is_circuit_breaker and is_macro_safe and open_positions_count < MAX_CONCURRENT_POSITIONS:
    for asset in scanner_data:
        if asset["score"] >= 75 and asset["side"] in ["LONG", "SHORT"]:
            has_pos, _ = check_existing_open_position_for_symbol(asset["symbol"], capital)
            if not has_pos:
                executed, msg = execute_autotrigger(asset["symbol"], asset, is_circuit_breaker, is_macro_safe, capital)
                if executed:
                    st.rerun()
                break

# =========================================================================
# BLOQUE DIRECTIVO E INTUITIVO PARA EL OPERADOR
# =========================================================================
if is_circuit_breaker:
    st.error(
        f"🛑 **ACCIÓN REQUERIDA**: Circuit Breaker Diario activado por Drawdown (-3.0% alcanzado: ${firewall['daily_pnl_usd']:.2f} USD). "
        "Las nuevas entradas están BLOQUEADAS por protocolo institucional hasta el siguiente ciclo."
    )
elif not is_macro_safe:
    st.warning(
        "⚠️ **ATENCIÓN**: Filtro Macro activado por alta volatilidad o noticias de impacto. "
        "El escaneo de los 18 pares en USD continúa en modo observación, pero la apertura de nuevas posiciones está en pausa preventiva."
    )
elif open_positions_count >= MAX_CONCURRENT_POSITIONS:
    st.info(
        f"🟡 **ESTADO DEL PORTAFOLIO**: Capacidad máxima alcanzada (**{open_positions_count}/{MAX_CONCURRENT_POSITIONS} posiciones OPEN** activas). "
        "El bot está gestionando las salidas por Take Profit (+3.0%) o Stop Loss (-1.5%). No se abrirán nuevos activos hasta que se cierre una posición."
    )
else:
    st.success(
        f"🟢 **MOTOR ACTIVO**: Monitoreando 18 pares de Kraken Spot (Paridad USD) en tiempo real. "
        f"Posiciones abiertas: **{open_positions_count}/{MAX_CONCURRENT_POSITIONS}**. Todo configurado correctamente. No requiere intervención manual."
    )

# TARJETAS DE ESTADO DEL SISTEMA
db_label = "SUPABASE (ONLINE)" if supabase_client else "MEMORIA LOCAL"
st.markdown(f"""
<div class="status-grid">
    <div class="status-card">
        <div class="status-title"><span>⚡</span> MOTOR DE ESCANEO</div>
        <div class="status-value" style="color: #34d399;">18 PARES USD</div>
        <div class="status-sub">↑ Kraken Spot Nativo</div>
    </div>
    <div class="status-card">
        <div class="status-title"><span>📊</span> PORTAFOLIO CONCURRENTE</div>
        <div class="status-value" style="color: {'#38bdf8' if open_positions_count < MAX_CONCURRENT_POSITIONS else '#f59e0b'};">
            {open_positions_count} / {MAX_CONCURRENT_POSITIONS} OPEN
        </div>
        <div class="status-sub">{'↑ Cupo Disponible' if open_positions_count < MAX_CONCURRENT_POSITIONS else '• Límite Alcanzado'}</div>
    </div>
    <div class="status-card">
        <div class="status-title"><span>🛡️</span> FIREWALL DIARIO (-3%)</div>
        <div class="status-value" style="color: {'#34d399' if not is_circuit_breaker else '#ef4444'};">
            {firewall['status_text']}
        </div>
        <div class="status-sub">PnL Hoy: ${firewall['daily_pnl_usd']:+.2f} USD</div>
    </div>
    <div class="status-card">
        <div class="status-title"><span>🗄️</span> AUDIT LOG & DB</div>
        <div class="status-value" style="color: #93c5fd;">{db_label}</div>
        <div class="status-sub">{'PostgreSQL Sincronizado' if supabase_client else 'Esperando Credenciales'}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================================================================
# PANEL DE BALANCE Y RESUMEN SEMANAL DE CAPITAL (RECALCULADOR INSTITUCIONAL)
# =========================================================================
weekly_kpis = calculate_weekly_capital_metrics(initial_capital=capital)
cycle_info = weekly_kpis["cycle"]
start_cot_str = cycle_info["start_cot"].strftime("%a %d/%m %I:%M %p COT")
end_cot_str = cycle_info["end_cot"].strftime("%a %d/%m %I:%M %p COT")

st.markdown(f"""
<div style="margin-top: 10px; margin-bottom: 8px; font-size: 13px; font-weight: 800; color: #f8fafc; letter-spacing: 0.8px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
    <div style="display: flex; align-items: center; gap: 8px;">
        <span>💼</span> PANEL DE BALANCE Y RESUMEN SEMANAL (CICLO INSTITUCIONAL)
    </div>
    <div style="font-size: 11px; color: #64748b;">
        Ciclo Semanal: <span style="color: #38bdf8;">{start_cot_str}</span> → <span style="color: #38bdf8;">{end_cot_str}</span> &nbsp;|&nbsp;
        Trades en Ciclo: <b style="color: #cbd5e1;">{weekly_kpis["total_closed"]}</b> &nbsp;|&nbsp;
        Total Histórico: <b style="color: #cbd5e1;">{weekly_kpis["all_closed_count"]}</b>
    </div>
</div>
""", unsafe_allow_html=True)

col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

with col_kpi1:
    st.metric(
        label="💵 Capital Inicial",
        value=f"${weekly_kpis['initial_capital']:,.2f}",
        help="Base de capital asignada en la matriz de riesgo del terminal"
    )

with col_kpi2:
    equity_delta_color = "normal" if weekly_kpis["total_closed_pnl_usd"] >= 0 else "inverse"
    st.metric(
        label="💼 Capital Actual (Equity)",
        value=f"${weekly_kpis['current_equity']:,.2f}",
        delta=f"${weekly_kpis['total_closed_pnl_usd']:+,.2f} ({weekly_kpis['total_pnl_pct']:+.2f}%)",
        delta_color=equity_delta_color,
        help="Capital neto actual: Capital Inicial + SUMA(PnL_USD de todos los trades cerrados)"
    )

with col_kpi3:
    pnl_delta_color = "normal" if weekly_kpis["weekly_pnl_usd"] >= 0 else "inverse"
    st.metric(
        label="📈 PnL Semanal (Ciclo)",
        value=f"${weekly_kpis['weekly_pnl_usd']:+,.2f}",
        delta=f"{weekly_kpis['weekly_pnl_pct']:+.2f}%",
        delta_color=pnl_delta_color,
        help="Rendimiento neto acumulado dentro del ciclo semanal (Dom 00:00 UTC a Sáb 23:59 UTC)"
    )

with col_kpi4:
    win_rate_str = f"{weekly_kpis['win_rate']:.1f}%"
    record_str = f"{weekly_kpis['winning_trades']}W / {weekly_kpis['losing_trades']}L (Ciclo)"
    st.metric(
        label="🎯 Win Rate (% Acierto)",
        value=win_rate_str,
        delta=record_str if weekly_kpis['total_closed'] > 0 else "Sin cerradas en ciclo",
        help="Porcentaje de acierto sobre operaciones cerradas del ciclo semanal"
    )

st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

# =========================================================================
# GRÁFICAS FINANCIERAS EN VIVO (EQUITY CURVE & RENDIMIENTO)
# =========================================================================
st.markdown("### 📈 CURVA DE CAPITAL (EQUITY CURVE) & RENDIMIENTO EN VIVO")

all_trades_normalized = fetch_all_trades_supabase(operational_capital=capital)
closed_trades = [
    t for t in all_trades_normalized 
    if "CERRADO" in str(t.get("status", "")).upper() or "CLOSED" in str(t.get("status", "")).upper()
]

col_chart_eq, col_chart_perf = st.columns([2.4, 1.2])

with col_chart_eq:
    if closed_trades:
        df_closed = pd.DataFrame(closed_trades)
        
        parsed_dates = []
        for raw_ts in df_closed['timestamp']:
            parsed_dates.append(to_cot_datetime(raw_ts))
            
        df_closed['ts'] = parsed_dates
        df_closed = df_closed.sort_values(by='ts')
        
        df_closed['cum_pnl'] = df_closed['pnl_usd'].astype(float).cumsum()
        df_closed['equity_point'] = capital + df_closed['cum_pnl']
        
        first_time = df_closed['ts'].iloc[0] - datetime.timedelta(hours=1)
        plot_dates = [first_time] + df_closed['ts'].tolist()
        plot_equity = [capital] + df_closed['equity_point'].tolist()
        
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(
            x=plot_dates,
            y=plot_equity,
            mode='lines+markers',
            name='Equity ($)',
            line=dict(color='#38bdf8', width=2.5),
            fill='tozeroy',
            fillcolor='rgba(56, 189, 248, 0.08)',
            marker=dict(size=6, color='#38bdf8')
        ))
        
        fig_equity.add_hline(
            y=capital,
            line_dash="dash",
            line_color="#64748b",
            annotation_text=f"Capital Inicial: ${capital:,.2f}",
            annotation_position="bottom right",
            annotation_font_color="#94a3b8"
        )
        
        fig_equity.update_layout(
            template='plotly_dark',
            paper_bgcolor='#0b1120',
            plot_bgcolor='#070a13',
            height=280,
            margin=dict(l=10, r=10, t=25, b=10),
            xaxis=dict(showgrid=True, gridcolor='#1e293b', title="Hora Colombia (COT)"),
            yaxis=dict(showgrid=True, gridcolor='#1e293b', title="Equity ($ USD)")
        )
        st.plotly_chart(fig_equity, use_container_width=True)
    else:
        fig_empty = go.Figure()
        now_cot = get_now_cot()
        fig_empty.add_trace(go.Scatter(
            x=[now_cot - datetime.timedelta(hours=2), now_cot],
            y=[capital, capital],
            mode='lines',
            name='Equity Base',
            line=dict(color='#38bdf8', width=2, dash='dot')
        ))
        fig_empty.update_layout(
            template='plotly_dark',
            paper_bgcolor='#0b1120',
            plot_bgcolor='#070a13',
            height=280,
            margin=dict(l=10, r=10, t=25, b=10),
            xaxis=dict(showgrid=True, gridcolor='#1e293b'),
            yaxis=dict(showgrid=True, gridcolor='#1e293b', range=[capital * 0.95, capital * 1.05])
        )
        st.plotly_chart(fig_empty, use_container_width=True)
        st.caption(f"ℹ️ Curva de capital inicializada con el capital base (${capital:,.2f}). Trazará cada operación cerrada.")

with col_chart_perf:
    wins = weekly_kpis["winning_trades"]
    losses = weekly_kpis["losing_trades"]
    
    if wins + losses > 0:
        fig_donut = go.Figure(data=[go.Pie(
            labels=['Ganadoras (TP)', 'Perdedoras (SL)'],
            values=[wins, losses],
            hole=.6,
            marker_colors=['#00E676', '#FF5252'],
            textinfo='label+percent'
        )])
        fig_donut.update_layout(
            template='plotly_dark',
            paper_bgcolor='#0b1120',
            height=280,
            showlegend=False,
            margin=dict(l=10, r=10, t=25, b=10),
            annotations=[dict(text=f'{weekly_kpis["win_rate"]:.0f}%<br>Win', x=0.5, y=0.5, font_size=16, showarrow=False)]
        )
        st.plotly_chart(fig_donut, use_container_width=True)
    else:
        st.markdown(f"""
            <div style="background: #0b1120; border: 1px solid #1e293b; border-radius: 6px; padding: 24px; text-align: center; height: 280px; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 32px; margin-bottom: 8px;">🎯</div>
                <div style="font-size: 13px; font-weight: bold; color: #cbd5e1;">Sin ratio W/L en ciclo actual</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 6px;">
                    Se actualizará automáticamente cuando el bot cierre las operaciones dentro de la ventana semanal.
                </div>
            </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# =========================================================================
# 15. PESTAÑAS PRINCIPALES DEL DASHBOARD
# =========================================================================
tab_monitor, tab_scanner, tab_history = st.tabs([
    "⚡ Monitor de Velas & Confluencia",
    "🌐 Matriz de Escaneo Multiactivo (18 Pares USD)",
    "📋 Historial de Órdenes & Audit Log"
])

# PESTAÑA 1: MONITOR DE VELAS REALES
with tab_monitor:
    col_chart, col_signal = st.columns([2.6, 1.1])
    
    with col_chart:
        df_real = fetch_market_data(selected_symbol, timeframe=timeframe, limit=50)
        
        if not df_real.empty:
            curr_price = float(df_real.iloc[-1]['close'])
            curr_ema = float(df_real.iloc[-1]['ema200'])
            
            st.markdown(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div style="font-size: 13px; font-weight: bold; color: #f8fafc;">
                        KRAKEN SPOT · {selected_symbol} ({timeframe}) · PRECIO REAL: <span style="color: #38bdf8;">${curr_price:,.4f}</span>
                    </div>
                    <div style="font-size: 11px; color: #64748b;">
                        EMA 200: <span style="color: #38bdf8;">${curr_ema:,.4f}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            fig = go.Figure()
            
            fig.add_trace(go.Candlestick(
                x=df_real['time_label'],
                open=df_real['open'],
                high=df_real['high'],
                low=df_real['low'],
                close=df_real['close'],
                name=selected_symbol,
                increasing_line_color='#00E676',
                increasing_fillcolor='#00E676',
                decreasing_line_color='#FF5252',
                decreasing_fillcolor='#FF5252'
            ))
            
            fig.add_trace(go.Scatter(
                x=df_real['time_label'],
                y=df_real['ema200'],
                mode='lines',
                name='EMA 200',
                line=dict(color='#38bdf8', width=1.8)
            ))
            
            fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='#070a13',
                plot_bgcolor='#0b1120',
                height=420,
                margin=dict(l=0, r=0, t=10, b=10),
                xaxis_rangeslider_visible=False,
                xaxis=dict(
                    type='category',
                    showgrid=True,
                    gridcolor='#1e293b',
                    categoryorder='trace',
                    nticks=10
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='#1e293b',
                    side='right',
                    tickformat='$,.4f' if curr_price < 10 else '$,.2f'
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"⚠️ Sincronizando feed de {selected_symbol} desde Kraken Spot REST... Por favor reintenta en unos instantes.")

    with col_signal:
        side_ins = signal_inspected['side']
        score_ins = signal_inspected['score']
        
        card_class = "border: 1px solid #00E676; background: radial-gradient(circle at top left, rgba(0, 230, 118, 0.15), rgba(11, 17, 32, 0.95));" if side_ins == "LONG" else ("border: 1px solid #FF5252; background: radial-gradient(circle at top left, rgba(255, 82, 82, 0.15), rgba(11, 17, 32, 0.95));" if side_ins == "SHORT" else "border: 1px solid #334155; background: #0b1120;")
        badge_color = "#00E676" if side_ins == "LONG" else ("#FF5252" if side_ins == "SHORT" else "#64748b")
        
        st.markdown(f"""
            <div style="{card_class} border-radius: 8px; padding: 16px; margin-bottom: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="background: {badge_color}; color: #000; font-weight: 800; padding: 3px 10px; border-radius: 4px; font-size: 12px;">
                        SEÑAL: {side_ins}
                    </span>
                    <span style="font-size: 18px; font-weight: 800; color: #f8fafc;">
                        {score_ins} / 100
                    </span>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; margin-top: 12px; line-height: 1.5;">
                    <b>Confluencia Técnica:</b><br>{signal_inspected['reason']}
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        if score_ins >= 75:
            st.success("🎯 SEÑAL DE ALTA CONFLUENCIA DETECTADA (≥ 75%)")
        else:
            st.info("⏳ Monitoreando mercado... Esperando Score ≥ 75%")

# PESTAÑA 2: MATRIZ DE ESCANEO DE LOS 18 PARES NATIVOS EN USD
with tab_scanner:
    st.markdown("### 🌐 ESCANEO MULTIACTIVO EN TIEMPO REAL (18 PARES KRAKEN USD)")
    st.caption("Kraken Spot REST · Paridad Nativa USD · Actualización cíclica cada 30 segundos · Límite máximo: 3 posiciones abiertas")
    
    if scanner_data:
        df_scan = pd.DataFrame(scanner_data)
        st.dataframe(
            df_scan,
            use_container_width=True,
            hide_index=True,
            column_config={
                "symbol": st.column_config.TextColumn("Par Cripto (USD)"),
                "price": st.column_config.NumberColumn("Precio Actual", format="$%.4f"),
                "score": st.column_config.NumberColumn("Score Confluencia", format="%d pts"),
                "side": st.column_config.TextColumn("Dirección"),
                "rsi": st.column_config.NumberColumn("RSI (14)", format="%.1f"),
                "reason": st.column_config.TextColumn("Resumen de Señal")
            }
        )

# PESTAÑA 3: HISTORIAL DE ÓRDENES & AUDIT LOG
with tab_history:
    st.markdown("### 📋 REGISTRO DE OPERACIONES & AUDIT LOG INSTITUCIONAL")
    
    # Barra de mantenimiento y reset
    col_tools1, col_tools2 = st.columns([1.5, 1])
    with col_tools1:
        if st.button("🧹 Normalizar y Corregir Registros en Supabase"):
            c_fixed = fix_and_normalize_supabase_trades(capital)
            st.success(f"¡{c_fixed} órdenes normalizadas exitosamente con riesgo institucional!")
            time.sleep(1)
            st.rerun()
    with col_tools2:
        # REQUERIMIENTO 4: Reset Manual para limpiar Supabase y restablecer saldo a $1,000.00 USD
        if st.button("🗑️ Reset Manual (Limpiar Base de Datos y Saldo a $1,000.00 USD)"):
            reset_all_trades_supabase()
            st.warning("Historial reseteado. Saldo restablecido a $1,000.00 USD.")
            time.sleep(1)
            st.rerun()
            
    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # REQUERIMIENTO 2: POSICIONES ACTIVAS (OPEN) EN CONTENEDOR SUPERIOR SEPARADO
    # Estilo de tarjeta o tabla neutra sin color de fondo invasivo
    # -------------------------------------------------------------------------
    st.markdown("""
        <div style="font-size: 13px; font-weight: 800; color: #f8fafc; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
            <span>⚡</span> POSICIONES ACTIVAS EN TIEMPO REAL (OPEN)
        </div>
    """, unsafe_allow_html=True)
    
    open_trades_list = get_all_open_positions(operational_capital=capital)
    
    if open_trades_list:
        st.markdown('<div class="open-positions-container"><div class="open-pos-grid">', unsafe_allow_html=True)
        for ot in open_trades_list:
            o_id = ot.get("order_id", "N/A")
            o_sym = ot.get("symbol", "N/A")
            o_side = str(ot.get("side", "LONG")).upper()
            o_entry = float(ot.get("entry_price") or 0.0)
            o_sl = float(ot.get("sl") or (o_entry * 0.985 if o_side == "LONG" else o_entry * 1.015))
            o_tp = float(ot.get("tp") or (o_entry * 1.030 if o_side == "LONG" else o_entry * 0.970))
            
            # Obtener precio en vivo y fecha/hora Colombia (COT)
            dt_cot = to_cot_datetime(ot.get("timestamp"))
            fecha_cot_str = dt_cot.strftime("%Y-%m-%d")
            hora_cot_str = dt_cot.strftime("%H:%M:%S COT")
            
            # Consulta rápida de precio actual para PnL no realizado
            df_ticker = fetch_market_data(o_sym, limit=2)
            curr_val = float(df_ticker.iloc[-1]['close']) if not df_ticker.empty else o_entry
            
            if o_side == "LONG":
                unrealized_pct = ((curr_val - o_entry) / o_entry * 100.0) if o_entry > 0 else 0.0
            else:
                unrealized_pct = ((o_entry - curr_val) / o_entry * 100.0) if o_entry > 0 else 0.0
            unrealized_usd = capital * (unrealized_pct / 100.0)
            
            side_badge = f'<span class="badge-side-long">LONG</span>' if o_side == "LONG" else f'<span class="badge-side-short">SHORT</span>'
            pnl_color = "#00E676" if unrealized_usd >= 0 else "#FF5252"
            
            st.markdown(f"""
                <div class="open-pos-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 800; color: #f8fafc; font-size: 14px;">{o_sym} {side_badge}</span>
                        <span style="background: #0284c7; color: #f0f9ff; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700;">OPEN</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; font-size: 11px; color: #94a3b8;">
                        <div>Entrada: <b style="color: #f8fafc;">${o_entry:,.4f}</b></div>
                        <div>Actual: <b style="color: #38bdf8;">${curr_val:,.4f}</b></div>
                        <div>Take Profit (+3%): <b style="color: #00E676;">${o_tp:,.4f}</b></div>
                        <div>Stop Loss (-1.5%): <b style="color: #FF5252;">${o_sl:,.4f}</b></div>
                    </div>
                    <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid #1e293b; display: flex; justify-content: space-between; align-items: center; font-size: 11px;">
                        <span style="color: #64748b;">Entrada: {hora_cot_str} ({fecha_cot_str})</span>
                        <span style="color: {pnl_color}; font-weight: bold;">Flotante: {unrealized_pct:+.2f}% (${unrealized_usd:+.2f} USD)</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)
    else:
        st.markdown("""
            <div style="background: #0b1120; border: 1px solid #1e293b; border-radius: 6px; padding: 14px; text-align: center; color: #64748b; font-size: 12px; margin-bottom: 20px;">
                ⚪ No hay posiciones abiertas actualmente. Cupo del portafolio 100% disponible (0/3 ocupadas).
            </div>
        """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # REQUERIMIENTO 1 & 3: TABLA DE HISTORIAL DE OPERACIONES CERRADAS
    # Row-Level Background Styling completo según resultado + Hora Colombia (COT)
    # Columnas: ['ID Orden', 'Fecha Entrada', 'Hora Entrada', 'Hora Salida', 'Par',
    #            'Tipo', 'Precio Entrada', 'Precio Cierre', 'Ganancia ($ USD)', 'Ganancia (%)', 'Resultado']
    # -------------------------------------------------------------------------
    st.markdown("""
        <div style="font-size: 13px; font-weight: 800; color: #f8fafc; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span>📜</span> HISTORIAL DE OPERACIONES CERRADAS (ROW-LEVEL STYLING & ZONA COT)
            </div>
            <div style="font-size: 11px; color: #64748b;">
                Verde: Ganancia (TP) &nbsp;|&nbsp; Rojo: Pérdida (SL) &nbsp;|&nbsp; Gris: Neutro
            </div>
        </div>
    """, unsafe_allow_html=True)

    all_trades_full = fetch_all_trades_supabase(operational_capital=capital)
    closed_trades_only = [
        t for t in all_trades_full 
        if "CERRADO" in str(t.get("status", "")).upper() or "CLOSED" in str(t.get("status", "")).upper()
    ]

    if closed_trades_only:
        # Construcción de filas con HTML de alto impacto visual
        rows_html = []
        for t in closed_trades_only:
            o_id = str(t.get("order_id", "N/A"))
            sym = str(t.get("symbol", "N/A"))
            side = str(t.get("side", "LONG")).upper()
            
            entry_p = float(t.get("entry_price") or 0.0)
            exit_p = float(t.get("exit_price") or 0.0)
            
            # Fecha y Hora Entrada (Colombia - COT)
            dt_cot = to_cot_datetime(t.get("timestamp"))
            fecha_entrada = dt_cot.strftime("%Y-%m-%d")
            hora_entrada = dt_cot.strftime("%H:%M:%S")
            
            # Hora Salida (Colombia - COT)
            # Si existe registro de salida en el diccionario o derivado
            hora_salida = t.get("exit_time_cot")
            if not hora_salida:
                # Estimada/sincronizada en la misma sesión
                hora_salida = (dt_cot + datetime.timedelta(minutes=30)).strftime("%H:%M:%S")
                
            status_str = str(t.get("status", "")).upper()
            
            try:
                pnl_usd = float(t.get("pnl_usd") or 0.0)
            except Exception:
                pnl_usd = 0.0
                
            try:
                pnl_pct = float(t.get("pnl_pct") or 0.0)
            except Exception:
                pnl_pct = 0.0
                
            # Validación estricta institucional de resultado y signo
            is_sl = "SL" in status_str or pnl_usd < 0 or pnl_pct < 0
            is_tp = "TP" in status_str or pnl_usd > 0 or pnl_pct > 0
            
            if is_sl:
                # Pérdida garantizada con signo negativo (-$15.00 USD)
                final_pnl_usd = -1.0 * abs(pnl_usd if pnl_usd != 0 else (capital * 0.015))
                final_pnl_pct = -1.0 * abs(pnl_pct if pnl_pct != 0 else 1.5)
                row_class = "row-loss"
                resultado_badge = '<span class="badge-pill-sl">STOP LOSS (SL)</span>'
                usd_label = f"-${abs(final_pnl_usd):.2f} USD"
                pct_label = f"-{abs(final_pnl_pct):.2f}%"
            elif is_tp:
                # Ganancia garantizada con signo positivo (+$30.00 USD)
                final_pnl_usd = abs(pnl_usd if pnl_usd != 0 else (capital * 0.030))
                final_pnl_pct = abs(pnl_pct if pnl_pct != 0 else 3.0)
                row_class = "row-profit"
                resultado_badge = '<span class="badge-pill-tp">TAKE PROFIT (TP)</span>'
                usd_label = f"+${abs(final_pnl_usd):.2f} USD"
                pct_label = f"+{abs(final_pnl_pct):.2f}%"
            else:
                row_class = "row-neutral"
                resultado_badge = '<span class="badge-pill-neutral">BREAKEVEN</span>'
                usd_label = "$0.00 USD"
                pct_label = "0.00%"
                
            side_badge = f'<span class="badge-side-long">LONG</span>' if side == "LONG" else f'<span class="badge-side-short">SHORT</span>'
            
            entry_p_str = f"${entry_p:,.4f}" if entry_p < 10 else f"${entry_p:,.2f}"
            exit_p_str = f"${exit_p:,.4f}" if exit_p < 10 else f"${exit_p:,.2f}"
            
            row_html = f"""
                <tr class="{row_class}">
                    <td style="font-weight: 700;">{o_id}</td>
                    <td>{fecha_entrada}</td>
                    <td>{hora_entrada}</td>
                    <td>{hora_salida}</td>
                    <td style="font-weight: 700;">{sym}</td>
                    <td>{side_badge}</td>
                    <td>{entry_p_str}</td>
                    <td>{exit_p_str}</td>
                    <td style="font-weight: 800;">{usd_label}</td>
                    <td style="font-weight: 800;">{pct_label}</td>
                    <td>{resultado_badge}</td>
                </tr>
            """
            rows_html.append(row_html)
            
        table_html = f"""
            <div class="table-responsive-container">
                <table class="custom-quant-table">
                    <thead>
                        <tr>
                            <th>ID Orden</th>
                            <th>Fecha Entrada</th>
                            <th>Hora Entrada</th>
                            <th>Hora Salida</th>
                            <th>Par</th>
                            <th>Tipo</th>
                            <th>Precio Entrada</th>
                            <th>Precio Cierre</th>
                            <th>Ganancia ($ USD)</th>
                            <th>Ganancia (%)</th>
                            <th>Resultado</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(rows_html)}
                    </tbody>
                </table>
            </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)
        st.caption("🕒 Horarios convertidos automáticamente a Hora Legal de Colombia (America/Bogota - COT / UTC-5).")
    else:
        st.info("ℹ️ Sin operaciones cerradas registradas en el historial. Las órdenes completadas se pintarán aquí con coloreado completo de fila.")

    st.markdown("---")
    
    # -------------------------------------------------------------------------
    # REQUERIMIENTO 3: AUDIT LOG CON PREFIJO [HH:MM:SS COT]
    # -------------------------------------------------------------------------
    st.markdown("### 📜 AUDIT LOG DEL SISTEMA [HH:MM:SS COT]")
    
    if st.session_state.system_logs:
        logs_html = "".join([f"<div style='font-size: 11px; margin-bottom: 4px; color: #93c5fd;'>{log}</div>" for log in st.session_state.system_logs])
        st.markdown(f"""
            <div style="background-color: #0b1120; border: 1px solid #1e293b; padding: 12px; border-radius: 6px; max-height: 250px; overflow-y: auto;">
                {logs_html}
            </div>
        """, unsafe_allow_html=True)
    else:
        hora_cot_init = get_now_cot().strftime("%H:%M:%S COT")
        st.markdown(f"""
            <div style="background-color: #0b1120; border: 1px solid #1e293b; padding: 12px; border-radius: 6px; font-size: 11px; color: #64748b;">
                [{hora_cot_init}] [INFO] Sistema inicializado. Monitoreando 18 pares de Kraken Spot nativos en USD.
            </div>
        """, unsafe_allow_html=True)
