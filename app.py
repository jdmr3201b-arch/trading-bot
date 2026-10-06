# -*- coding: utf-8 -*-
"""
PROYECTO DIPPER | Quant Terminal v2.7 (Risk-Managed PnL & Supabase Healing Engine)
Terminal Autónomo de Trading Cuantitativo
Escaneo: 18 Criptomonedas Kraken Spot Nativas en USD
Gestión de Riesgo:
  - Límite de 3 Posiciones Concurrentes (Máx 1 por par)
  - Cálculo estricto de PnL en $ USD sobre Capital de Posición / Operativo
  - Take Profit: +3.0% (+$30.00 USD para base $1,000)
  - Stop Loss: -1.5% (-$15.00 USD para base $1,000)
  - Recalculador de Balance / Equity: Capital Inicial + SUMA(PnL_USD de trades cerrados)
  - Normalizador y Saneador de Registros Históricos de Supabase
  - Firewall Diario (-3.0% Circuit Breaker)
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
    from supabase import create_client, Client
    HAS_SUPABASE_LIB = True
except ImportError:
    HAS_SUPABASE_LIB = False

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA E INYECCIÓN CSS
# ==========================================
st.set_page_config(
    page_title="PROYECTO DIPPER | Multi-Asset Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS Profesionales Bloomberg Dark Theme (#070a13)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,600;0,700;1,400&display=swap');
    
    html, body, [class*="css"], .stMarkdown {
        font-family: 'JetBrains Mono', monospace !important;
        background-color: #070a13 !important;
        color: #93c5fd;
    }
    .stApp {
        background-color: #070a13 !important;
    }

    /* Scrollbar personalizada */
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
    .status-sub-warn {
        font-size: 11px;
        color: #f87171;
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

    /* Tarjetas de Señal Algorítmica con Neón */
    .signal-card-long {
        background: radial-gradient(circle at top left, rgba(16, 185, 129, 0.15), rgba(11, 17, 32, 0.95));
        border: 1px solid #10b981;
        box-shadow: 0 0 18px rgba(16, 185, 129, 0.2);
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 14px;
    }
    .signal-card-short {
        background: radial-gradient(circle at top left, rgba(239, 68, 68, 0.15), rgba(11, 17, 32, 0.95));
        border: 1px solid #ef4444;
        box-shadow: 0 0 18px rgba(239, 68, 68, 0.2);
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 14px;
    }
    .signal-card-neutral {
        background: #0b1120;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 14px;
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
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DEFINICIÓN DE ACTIVOS NATIVOS KRAKEN (18 PARES USD)
# ==========================================
# Kraken opera de forma nativa en USD con alta liquidez spot
WATCHLIST_18 = [
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD",
    "XRP/USD", "DOT/USD", "AVAX/USD", "LINK/USD",
    "LTC/USD", "BCH/USD", "NEAR/USD", "SUI/USD",
    "APT/USD", "FET/USD", "ARB/USD", "PEPE/USD",
    "DOGE/USD", "SHIB/USD"
]

MAX_CONCURRENT_POSITIONS = 3

# ==========================================
# 3. CONEXIÓN SUPABASE & GESTIÓN DE ESTADO
# ==========================================
ENV_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
ENV_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if "local_paper_trades" not in st.session_state:
    st.session_state.local_paper_trades = []

if "system_logs" not in st.session_state:
    st.session_state.system_logs = []

def add_log(message: str, level: str = "INFO"):
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC")
    st.session_state.system_logs.insert(0, f"[{timestamp}] [{level}] {message}")
    if len(st.session_state.system_logs) > 60:
        st.session_state.system_logs.pop()

@st.cache_resource
def get_supabase_client(url: str, key: str):
    if HAS_SUPABASE_LIB and url and key:
        try:
            client = create_client(url, key)
            return client
        except Exception as e:
            return None
    return None

supabase_client = get_supabase_client(ENV_SUPABASE_URL, ENV_SUPABASE_KEY)

# ==========================================
# 4. CONEXIÓN A KRAKEN CON RESOLUCIÓN ROBUSTA DE MERCADOS
# ==========================================
@st.cache_resource
def get_kraken_exchange():
    """
    Inicializa el cliente CCXT de Kraken y precarga los mercados (load_markets).
    Esto mapea los nombres internos (ej: XXBTZUSD -> BTC/USD, XDG/USD -> DOGE/USD).
    """
    ex = ccxt.kraken({
        'enableRateLimit': True,
        'timeout': 15000,
    })
    try:
        ex.load_markets()
    except Exception as e:
        pass
    return ex

exchange = get_kraken_exchange()

def resolve_kraken_symbol(ex, symbol: str) -> str:
    """
    Resuelve el símbolo estándar al identificador de mercado exacto reconocido por CCXT y Kraken.
    Previene el error 'kraken does not have market symbol'.
    """
    if not ex.markets:
        try:
            ex.load_markets()
        except Exception:
            return symbol

    # 1. Comprobación directa (ej. 'BTC/USD')
    if symbol in ex.markets:
        return symbol

    # 2. Alternativas conocidas de Kraken Spot
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
    """
    Obtiene las últimas 50 velas reales directamente desde Kraken Spot REST mediante CCXT.
    Aplica resolución robusta de mercados y calcula EMA 200, ATR y RSI sin advertencias repetitivas.
    """
    try:
        ex = get_kraken_exchange()
        target_symbol = resolve_kraken_symbol(ex, symbol)
        
        ohlcv = ex.fetch_ohlcv(target_symbol, timeframe=timeframe, limit=limit)
        
        if ohlcv and len(ohlcv) > 0:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['time_label'] = df['timestamp'].dt.strftime('%d/%m %H:%M')
            
            # EMA 200 calculada sobre precios reales de cierre
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
    except ccxt.BadSymbol:
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 5. MOTOR DE CONFLUENCIA Y SEÑAL ALGORÍTMICA
# ==========================================
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
    
    # Regla 1: Estructura Tendencial vs EMA 200 (+40)
    if close > ema:
        side = "LONG"
        score += 40
        reasons.append("Precio > EMA 200")
    else:
        side = "SHORT"
        score += 40
        reasons.append("Precio < EMA 200")
    
    # Regla 2: Presión Direccional de Cierre (+25)
    if (side == "LONG" and close > prev['close']) or (side == "SHORT" and close < prev['close']):
        score += 25
        reasons.append("Impulso direccional consistente")
    
    # Regla 3: Régimen de Volatilidad ATR (+20)
    if atr > 0:
        score += 20
        reasons.append("Volatilidad ATR suficiente")
        
    # Regla 4: Momentum RSI (+15)
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

# ==========================================
# 6. FILTRO MACRO DINÁMICO
# ==========================================
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
# 7. NORMALIZACIÓN, LIMPIEZA DE PNL Y GESTIÓN DE BASE DE DATOS
# =========================================================================
def normalize_trade_data(trade: dict, operational_capital: float = 1000.0) -> dict:
    """
    Normaliza y sanea los registros de trading.
    Corrige anomalías históricas donde el PnL en $ USD se calculó erróneamente sobre el
    precio unitario del par (ej. -$1,275 USD por BTC a $85,000) en lugar del capital operativo.
    Regla estricta institucional:
      - Stop Loss (-1.5%): PnL_USD = -1.0 * (capital_operativo * 0.015)  [ej. -$15.00 USD para $1000]
      - Take Profit (+3.0%): PnL_USD = capital_operativo * 0.030         [ej. +$30.00 USD para $1000]
    """
    if not isinstance(trade, dict):
        return trade
        
    t = dict(trade)
    status_str = str(t.get("status", "")).upper()
    
    # Solo procesamos órdenes cerradas
    if "CERRADO" in status_str or "CLOSED" in status_str:
        raw_pnl_usd = t.get("pnl_usd")
        raw_pnl_pct = t.get("pnl_pct")
        
        try:
            pnl_usd = float(raw_pnl_usd) if raw_pnl_usd is not None else None
        except (ValueError, TypeError):
            pnl_usd = None
            
        try:
            pnl_pct = float(raw_pnl_pct) if raw_pnl_pct is not None else None
        except (ValueError, TypeError):
            pnl_pct = None
            
        is_sl = "SL" in status_str or (pnl_pct is not None and pnl_pct < 0) or (pnl_usd is not None and pnl_usd < 0)
        is_tp = "TP" in status_str or (pnl_pct is not None and pnl_pct > 0) or (pnl_usd is not None and pnl_usd > 0)
        
        # Detección del bug del precio unitario del activo:
        # Si pnl_usd excede el 15% del capital operativo (ej. > $150 para $1000) cuando la gestión
        # fija -1.5% / +3.0%, o si es nulo / cero con status cerrado.
        needs_correction = False
        if pnl_usd is not None:
            if abs(pnl_usd) > (operational_capital * 0.15):
                needs_correction = True
        else:
            needs_correction = True
            
        if needs_correction:
            if is_sl:
                t["pnl_pct"] = -1.5
                t["pnl_usd"] = -1.0 * round(operational_capital * 0.015, 2)
            elif is_tp:
                t["pnl_pct"] = 3.0
                t["pnl_usd"] = round(operational_capital * 0.030, 2)
        else:
            if pnl_usd is not None:
                t["pnl_usd"] = round(pnl_usd, 2)
            if pnl_pct is not None:
                t["pnl_pct"] = round(pnl_pct, 2)
                
    return t

def fix_and_normalize_supabase_trades(operational_capital: float = 1000.0) -> int:
    """
    Función de utilidad activa para limpiar y normalizar en Supabase todos los registros
    con PnL erróneos de -$1200 USD generados por el bug de precio unitario.
    """
    fixed_count = 0
    # 1. Normalizar memoria de sesión
    for i, t in enumerate(st.session_state.local_paper_trades):
        cleaned = normalize_trade_data(t, operational_capital)
        if cleaned != t:
            st.session_state.local_paper_trades[i] = cleaned
            fixed_count += 1
            
    # 2. Normalizar base de datos Supabase
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
                            
                        if abs(pnl_val) > (operational_capital * 0.15) or pnl_val == 0.0:
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
            
    add_log(f"Normalización completada: {fixed_count} órdenes corregidas con riesgo institucional.", "SUCCESS")
    return fixed_count

def reset_all_trades_supabase() -> bool:
    """Resetea el historial de órdenes para reiniciar el terminal limpiamente."""
    st.session_state.local_paper_trades = []
    if supabase_client:
        try:
            supabase_client.table("paper_trades").delete().neq("id", -999999).execute()
            add_log("Base de datos de paper_trades reseteada en Supabase.", "WARN")
            return True
        except Exception as e:
            add_log(f"Error reseteando Supabase: {str(e)}", "ERROR")
            return False
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

    # Sanitizar automáticamente cada registro contra el bug de precio unitario
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
# 8. RECALCULADOR DE BALANCE / EQUITY Y RESUMEN SEMANAL DE CAPITAL
# =========================================================================
def calculate_weekly_capital_metrics(initial_capital: float = 1000.0):
    """
    Recalculador integral de Balance y Equity según especificaciones exactas:
      - Capital Actual (Equity) = Capital Inicial + SUMA(PnL_USD de trades cerrados)
      - PnL Semanal ($ y %) = Rendimiento acumulado de trades cerrados en los últimos 7 días
      - Win Rate (% de acierto) = Victorias / Total cerrados en la ventana semanal
    """
    all_trades = fetch_all_trades_supabase(operational_capital=initial_capital)
    
    # 1. Todas las operaciones cerradas históricas
    all_closed_trades = [
        t for t in all_trades 
        if "CERRADO" in str(t.get("status", "")).upper() or "CLOSED" in str(t.get("status", "")).upper()
    ]
    
    # SUMA exacta del PnL en $ USD de todos los trades cerrados legítimos
    total_closed_pnl_usd = sum(float(t.get("pnl_usd", 0.0) or 0.0) for t in all_closed_trades)
    
    # REGLA 2: Capital Actual (Equity) = Capital Inicial + SUMA(PnL_USD de trades cerrados)
    current_equity = initial_capital + total_closed_pnl_usd
    total_pnl_pct = (total_closed_pnl_usd / initial_capital * 100.0) if initial_capital > 0 else 0.0
    
    # 2. Filtrado de operaciones cerradas de los últimos 7 días
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    seven_days_ago = now_utc - datetime.timedelta(days=7)
    
    weekly_closed_trades = []
    for t in all_closed_trades:
        raw_ts = t.get("timestamp")
        trade_dt = None
        if raw_ts:
            try:
                if isinstance(raw_ts, str):
                    ts_clean = raw_ts.replace("Z", "+00:00")
                    trade_dt = datetime.datetime.fromisoformat(ts_clean)
                elif isinstance(raw_ts, (int, float)):
                    trade_dt = datetime.datetime.fromtimestamp(raw_ts, tz=datetime.timezone.utc)
            except Exception:
                trade_dt = now_utc
        else:
            trade_dt = now_utc
            
        if trade_dt:
            if trade_dt.tzinfo is None:
                trade_dt = trade_dt.replace(tzinfo=datetime.timezone.utc)
            if trade_dt >= seven_days_ago:
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
        "trades": weekly_closed_trades
    }

# ==========================================
# 9. FIREWALL DIARIO (-3.0% CIRCUIT BREAKER)
# ==========================================
def calculate_daily_firewall(capital: float, max_loss_pct: float = 3.0):
    today_utc = datetime.datetime.now(datetime.timezone.utc).date()
    max_allowed_loss_usd = -1.0 * abs(capital * (max_loss_pct / 100.0))
    
    all_trades = fetch_all_trades_supabase(operational_capital=capital)
    daily_pnl_usd = 0.0
    daily_trades_count = 0
    
    for t in all_trades:
        status = str(t.get("status", "")).upper()
        if "CERRADO" in status or "CLOSED" in status:
            raw_ts = t.get("timestamp")
            if raw_ts:
                try:
                    if isinstance(raw_ts, str):
                        ts_clean = raw_ts.replace("Z", "+00:00")
                        trade_date = datetime.datetime.fromisoformat(ts_clean).date()
                    elif isinstance(raw_ts, (int, float)):
                        trade_date = datetime.datetime.fromtimestamp(raw_ts, tz=datetime.timezone.utc).date()
                    else:
                        trade_date = today_utc
                except Exception:
                    trade_date = today_utc
                
                if trade_date == today_utc:
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
# 10. EVALUACIÓN Y CIERRE DE POSICIONES OPEN (GESTIÓN DE RIESGO ESTRICTA)
# =========================================================================
def evaluate_and_close_open_positions(operational_capital: float = 1000.0):
    """
    Monitorea de forma iterativa todas las posiciones OPEN en el portafolio.
    Consulta el precio en vivo del par EXACTO correspondiente a cada orden.
    Ejecuta salidas automáticas por Take Profit (+3.0%) o Stop Loss (-1.5%).
    REGLA ESTRICTA DE PNL:
      - Stop Loss (-1.5%): PnL_USD = -1 * (capital_operativo * 0.015) [ej. -$15.00 USD]
      - Take Profit (+3.0%): PnL_USD = capital_operativo * 0.030     [ej. +$30.00 USD]
      - NUNCA se multiplica por el precio unitario del activo (ej. $85,000 de BTC).
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
        
        # Capital asignado a la posición (por defecto el capital operativo del terminal)
        pos_capital = float(trade.get("capital") or trade.get("position_size_usd") or operational_capital)
        if pos_capital <= 0:
            pos_capital = operational_capital
            
        # Consulta de precio en vivo del par exacto de la orden
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
                # Ganancia exacta: +3.0% del capital operativo
                pnl_usd = pos_capital * 0.030
            elif current_price <= sl:
                closed = True
                status = "CERRADO (SL)"
                pnl_pct = -1.5
                # Pérdida exacta: -1.5% del capital operativo
                pnl_usd = -1.0 * (pos_capital * 0.015)
                
        elif side == "SHORT":
            if current_price <= tp:
                closed = True
                status = "CERRADO (TP)"
                pnl_pct = 3.0
                pnl_usd = pos_capital * 0.030
            elif current_price <= sl:
                closed = True
                status = "CERRADO (SL)"
                pnl_pct = -1.5
                pnl_usd = -1.0 * (pos_capital * 0.015)
        
        if closed:
            # Tipos nativos de Python para evitar fallos de serialización PostgREST
            clean_status = str(status)
            clean_exit_price = float(round(float(current_price), 4))
            clean_pnl_usd = float(round(float(pnl_usd), 2))
            clean_pnl_pct = float(round(float(pnl_pct), 2))
            
            # Payload compatible con el esquema de Supabase: columnas válidas únicamente (SIN closed_at)
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
                    break
            
            log_type = "SUCCESS" if pnl_usd > 0 else "WARN"
            add_log(f"POSICIÓN CERRADA: {order_id} ({side}) en {sym} a ${current_price:,.4f} | {status} | PnL: ${pnl_usd:+.2f} USD ({pnl_pct:+.1f}%)", log_type)

# ==========================================
# 11. MOTOR DE EJECUCIÓN AUTÓNOMO (LÍMITE 3 POSICIONES)
# ==========================================
def execute_autotrigger(symbol: str, signal: dict, is_firewall_locked: bool, is_macro_safe: bool, capital_base: float = 1000.0):
    score = signal.get("score", 0)
    side = signal.get("side", "NEUTRAL")
    entry_price = signal.get("price", 0.0)
    
    if score < 75 or side not in ["LONG", "SHORT"]:
        return False, "Score insuficiente para gatillo autónomo (Mínimo requerido: 75%)"
    
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
        
    order_id = f"DIP-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
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
        
    return True, f"¡Orden Autónoma {order_id} abierta para {symbol} [{side}]!"

# ==========================================
# 12. ESCANEO ITERATIVO DE LOS 18 PARES NATIVOS
# ==========================================
def scan_all_18_watchlist():
    """
    Escanea de forma iterativa los 18 pares nativos en USD de Kraken Spot.
    Maneja excepciones de forma individual sin detener el terminal.
    """
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

# ==========================================
# 13. ENCABEZADO Y SIDEBAR INSTITUCIONAL
# ==========================================
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px;">
    <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 26px; line-height: 1;">⚡</span>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 19px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;">PROYECTO DIPPER</span>
                <span style="background: #1e293b; color: #38bdf8; font-size: 10px; padding: 3px 8px; border-radius: 4px; font-weight: 700; border: 1px solid #334155;">QUANT TERMINAL v2.7</span>
                <span class="badge-auto">KRAKEN USD NATIVO · MÁX 3 OPEN</span>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">
                MOTOR MULTIACTIVO DE TRADING CUANTITATIVO · GESTIÓN ESTRICTA DE PNL USD · SUPABASE POSTGRESQL
            </div>
        </div>
    </div>
    <div style="font-size: 11px; color: #64748b; text-align: right;">
        HORA UTC: <span style="color: #cbd5e1; font-weight: bold;">""" + datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S") + """</span> &nbsp;|&nbsp;
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
            <div class="metric-label" style="margin-top: 6px;">Riesgo / Posición (-1.5% SL)</div>
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
    auto_refresh_enabled = st.checkbox("Refresco Automático (30s)", value=True)
    if st.button("⚡ Escanear Ahora (18 Pares USD)"):
        st.rerun()

if auto_refresh_enabled:
    st.markdown("""
        <script>
            setTimeout(function(){
                window.location.reload();
            }, 30000);
        </script>
    """, unsafe_allow_html=True)

# EJECUCIÓN DEL CICLO EN TIEMPO REAL
# 1. Monitoreo y cierre de posiciones OPEN activas con cálculo estricto de PnL sobre el capital operativo
evaluate_and_close_open_positions(operational_capital=capital)

# 2. Obtención de datos del par en inspección
df_inspected = fetch_market_data(selected_symbol, timeframe, limit=50)
signal_inspected = evaluate_confluence(df_inspected)
is_macro_safe, macro_status_str = evaluate_macro_filter(df_inspected, macro_override)

# 3. Estado de Firewall y Portafolio
firewall = calculate_daily_firewall(capital, max_loss_pct=3.0)
is_circuit_breaker = firewall["is_circuit_breaker"]
open_positions = get_all_open_positions(operational_capital=capital)
open_positions_count = len(open_positions)

# 4. Escaneo automático y posible ejecución de Autotrigger
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
        "Por protocolo institucional estricto, las nuevas entradas están BLOQUEADAS hasta el siguiente ciclo UTC."
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
# PANEL DE BALANCE Y RESUMEN SEMANAL DE CAPITAL (RECALCULADOR EXACTO)
# =========================================================================
weekly_kpis = calculate_weekly_capital_metrics(initial_capital=capital)

st.markdown("""
<div style="margin-top: 10px; margin-bottom: 8px; font-size: 13px; font-weight: 800; color: #f8fafc; letter-spacing: 0.8px; display: flex; align-items: center; justify-content: space-between;">
    <div style="display: flex; align-items: center; gap: 8px;">
        <span>💼</span> PANEL DE BALANCE Y RESUMEN DE CAPITAL (RECALCULADOR INSTITUCIONAL)
    </div>
    <div style="font-size: 11px; color: #64748b;">
        Trades Cerrados: 7D (<b style="color: #cbd5e1;">""" + str(weekly_kpis["total_closed"]) + """</b>) &nbsp;|&nbsp; Total Histórico (<b style="color: #cbd5e1;">""" + str(weekly_kpis["all_closed_count"]) + """</b>)
    </div>
</div>
""", unsafe_allow_html=True)

col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

with col_kpi1:
    st.metric(
        label="💵 Capital Inicial",
        value=f"${weekly_kpis['initial_capital']:,.2f}",
        help="Base de capital operativo asignada en la matriz de riesgo del terminal"
    )

with col_kpi2:
    equity_delta_color = "normal" if weekly_kpis["total_closed_pnl_usd"] >= 0 else "inverse"
    st.metric(
        label="💼 Capital Actual (Equity)",
        value=f"${weekly_kpis['current_equity']:,.2f}",
        delta=f"${weekly_kpis['total_closed_pnl_usd']:+,.2f} ({weekly_kpis['total_pnl_pct']:+.2f}%)",
        delta_color=equity_delta_color,
        help="Capital neto actual: Capital Inicial + SUMA(PnL_USD de trades cerrados legítimos)"
    )

with col_kpi3:
    pnl_delta_color = "normal" if weekly_kpis["weekly_pnl_usd"] >= 0 else "inverse"
    st.metric(
        label="📈 PnL Semanal (7 Días)",
        value=f"${weekly_kpis['weekly_pnl_usd']:+,.2f}",
        delta=f"{weekly_kpis['weekly_pnl_pct']:+.2f}%",
        delta_color=pnl_delta_color,
        help="Rendimiento neto acumulado de operaciones cerradas en los últimos 7 días"
    )

with col_kpi4:
    win_rate_str = f"{weekly_kpis['win_rate']:.1f}%"
    record_str = f"{weekly_kpis['winning_trades']}W / {weekly_kpis['losing_trades']}L (7D)"
    st.metric(
        label="🎯 Win Rate (% Acierto)",
        value=win_rate_str,
        delta=record_str if weekly_kpis['total_closed'] > 0 else "Sin cerradas en 7D",
        help="Porcentaje de operaciones con ganancia neta sobre el total cerrado"
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
        
        # Procesar fechas de forma segura
        parsed_dates = []
        now_ts = datetime.datetime.now(datetime.timezone.utc)
        for raw_ts in df_closed['timestamp']:
            try:
                if isinstance(raw_ts, str):
                    clean_str = raw_ts.replace("Z", "+00:00")
                    dt_val = datetime.datetime.fromisoformat(clean_str)
                elif isinstance(raw_ts, (int, float)):
                    dt_val = datetime.datetime.fromtimestamp(raw_ts, tz=datetime.timezone.utc)
                else:
                    dt_val = now_ts
            except Exception:
                dt_val = now_ts
            parsed_dates.append(dt_val)
            
        df_closed['ts'] = parsed_dates
        df_closed = df_closed.sort_values(by='ts')
        
        # Curva de capital acumulativa sobre PnL USD saneado
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
            xaxis=dict(showgrid=True, gridcolor='#1e293b', title="Tiempo UTC"),
            yaxis=dict(showgrid=True, gridcolor='#1e293b', title="Equity ($ USD)")
        )
        st.plotly_chart(fig_equity, use_container_width=True)
    else:
        fig_empty = go.Figure()
        now_time = datetime.datetime.now(datetime.timezone.utc)
        fig_empty.add_trace(go.Scatter(
            x=[now_time - datetime.timedelta(hours=2), now_time],
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
        st.caption(f"ℹ️ Curva de capital inicializada con el capital base (${capital:,.2f}). Trazará automáticamente cada operación real cerrada.")

with col_chart_perf:
    wins = weekly_kpis["winning_trades"]
    losses = weekly_kpis["losing_trades"]
    
    if wins + losses > 0:
        fig_donut = go.Figure(data=[go.Pie(
            labels=['Ganadoras (TP)', 'Perdedoras (SL)'],
            values=[wins, losses],
            hole=.6,
            marker_colors=['#10b981', '#ef4444'],
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
                <div style="font-size: 13px; font-weight: bold; color: #cbd5e1;">Sin ratio W/L todavía</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 6px;">
                    Se calculará y actualizará dinámicamente cuando el bot ejecute y cierre las primeras operaciones reales.
                </div>
            </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# 14. PESTAÑAS PRINCIPALES DEL DASHBOARD
# ==========================================
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
            
            # Gráfico Interactivo de Candlestick (Plotly)
            fig = go.Figure()
            
            # Velas reales (Open, High, Low, Close)
            fig.add_trace(go.Candlestick(
                x=df_real['time_label'],
                open=df_real['open'],
                high=df_real['high'],
                low=df_real['low'],
                close=df_real['close'],
                name=selected_symbol,
                increasing_line_color='#10b981',
                increasing_fillcolor='#10b981',
                decreasing_line_color='#ef4444',
                decreasing_fillcolor='#ef4444'
            ))
            
            # Línea de la EMA 200 real
            fig.add_trace(go.Scatter(
                x=df_real['time_label'],
                y=df_real['ema200'],
                mode='lines',
                name='EMA 200',
                line=dict(color='#38bdf8', width=1.8)
            ))
            
            # Tema oscuro plotly_dark y remoción de rangos vacíos (type='category')
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
            st.warning(f"⚠️ Sincronizando datos de {selected_symbol} desde Kraken Spot REST... Por favor reintenta en unos instantes.")

    with col_signal:
        side_ins = signal_inspected['side']
        score_ins = signal_inspected['score']
        
        card_class = "signal-card-long" if side_ins == "LONG" else ("signal-card-short" if side_ins == "SHORT" else "signal-card-neutral")
        badge_color = "#10b981" if side_ins == "LONG" else ("#ef4444" if side_ins == "SHORT" else "#64748b")
        
        st.markdown(f"""
            <div class="{card_class}">
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

# PESTAÑA 3: HISTORIAL DE ÓRDENES SIMPLIFICADO Y AUDIT LOG
with tab_history:
    st.markdown("### 📋 REGISTRO DE OPERACIONES (VISTA SIMPLIFICADA)")
    
    # Barra de herramientas de mantenimiento y saneamiento de datos
    col_clean1, col_clean2 = st.columns([1.5, 1])
    with col_clean1:
        if st.button("🧹 Normalizar y Corregir Registros en Supabase (Fix Bug -$1,200 USD)"):
            c_fixed = fix_and_normalize_supabase_trades(capital)
            st.success(f"¡Registros saneados exitosamente ({c_fixed} órdenes normalizadas al riesgo institucional)!")
            time.sleep(1)
            st.rerun()
    with col_clean2:
        if st.button("🗑️ Resetear Historial Completo (Empezar de Cero)"):
            reset_all_trades_supabase()
            st.warning("Historial de órdenes reseteado.")
            time.sleep(1)
            st.rerun()
            
    st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)
    
    trades = fetch_all_trades_supabase(operational_capital=capital)
    
    if trades and len(trades) > 0:
        df_trades = pd.DataFrame(trades)
        
        # Columnas esenciales requeridas
        essential_cols = ['order_id', 'symbol', 'side', 'entry_price', 'exit_price', 'pnl_usd', 'pnl_pct', 'status']
        for col in essential_cols:
            if col not in df_trades.columns:
                df_trades[col] = None
                
        df_display = df_trades[essential_cols].copy()
        
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "order_id": st.column_config.TextColumn("ID Orden"),
                "symbol": st.column_config.TextColumn("Par"),
                "side": st.column_config.TextColumn("Tipo (Side)"),
                "entry_price": st.column_config.NumberColumn("Precio Entrada", format="$%.4f"),
                "exit_price": st.column_config.NumberColumn("Precio Cierre", format="$%.4f"),
                "pnl_usd": st.column_config.NumberColumn("Ganancia ($ USD)", format="$%.2f"),
                "pnl_pct": st.column_config.NumberColumn("Ganancia (%)", format="%.2f%%"),
                "status": st.column_config.TextColumn("Estado")
            }
        )
    else:
        st.info("ℹ️ Sin operaciones reales registradas en la base de datos. El motor está activo esperando confluencia ≥ 75% para abrir la primera posición.")
        
    st.markdown("---")
    st.markdown("### 📜 AUDIT LOG DEL SISTEMA")
    
    if st.session_state.system_logs:
        logs_html = "".join([f"<div style='font-size: 11px; margin-bottom: 4px; color: #93c5fd;'>{log}</div>" for log in st.session_state.system_logs])
        st.markdown(f"""
            <div style="background-color: #0b1120; border: 1px solid #1e293b; padding: 12px; border-radius: 6px; max-height: 250px; overflow-y: auto;">
                {logs_html}
            </div>
        """, unsafe_allow_html=True)
    else:
        st.text("Sin registros de eventos en esta sesión.")
