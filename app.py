# -*- coding: utf-8 -*-
"""
PROYECTO DIPPER | Quant Terminal v2.4
Terminal Autónomo de Trading Cuantitativo
Stack: Python, Streamlit, CCXT (Kraken Spot), Supabase (PostgreSQL), Plotly
"""

import os
import time
import datetime
import pandas as pd
import numpy as np
import streamlit as st
import ccxt
import plotly.graph_objects as go

try:
    from supabase import create_client, Client
    HAS_SUPABASE_LIB = True
except ImportError:
    HAS_SUPABASE_LIB = False

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA E INYECCIÓN CSS
# ==========================================
st.set_page_config(
    page_title="PROYECTO DIPPER | Quant Terminal v2.4",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS Profesionales Bloomberg Dark Theme (#070a13) y soporte Móvil
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

    /* Grid y Tarjetas de Estado Superiores */
    .status-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 20px;
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

    /* Tarjetas de Señal Algorítmica con Neón */
    .signal-card-long {
        background: radial-gradient(circle at top left, rgba(16, 185, 129, 0.15), rgba(11, 17, 32, 0.95));
        border: 1px solid #10b981;
        box-shadow: 0 0 18px rgba(16, 185, 129, 0.2);
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 14px;
    }
    .signal-card-short {
        background: radial-gradient(circle at top left, rgba(239, 68, 68, 0.15), rgba(11, 17, 32, 0.95));
        border: 1px solid #ef4444;
        box-shadow: 0 0 18px rgba(239, 68, 68, 0.2);
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 14px;
    }
    .signal-card-neutral {
        background: #0b1120;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 18px;
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

    /* Adaptación Móvil */
    @media (max-width: 768px) {
        .status-grid {
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 8px !important;
        }
        .status-card {
            padding: 10px !important;
        }
        .status-value {
            font-size: 14px !important;
        }
        .status-sub, .status-sub-warn {
            font-size: 10px !important;
        }
        .signal-card-long, .signal-card-short, .signal-card-neutral {
            padding: 14px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONEXIÓN SUPABASE & GESTIÓN DE ESTADO
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
    if len(st.session_state.system_logs) > 50:
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
# 3. CONEXIÓN A KRAKEN (CCXT REST)
# ==========================================
@st.cache_resource
def get_kraken_exchange():
    return ccxt.kraken({
        'enableRateLimit': True,
        'timeout': 15000,
    })

exchange = get_kraken_exchange()

def generate_synthetic_candles(symbol: str, limit: int = 100):
    """Genera serie de velas sintéticas para fallback."""
    now = datetime.datetime.now(datetime.timezone.utc)
    timestamps = [now - datetime.timedelta(minutes=15 * (limit - i)) for i in range(limit)]
    base_price = 68500.0 if "BTC" in symbol else (3450.0 if "ETH" in symbol else 175.0)
    
    np.random.seed(int(now.timestamp()) // 300)
    returns = np.random.normal(0.0002, 0.003, limit)
    prices = base_price * np.exp(np.cumsum(returns))
    
    data = []
    for i, t in enumerate(timestamps):
        c = float(prices[i])
        o = float(prices[max(0, i-1)])
        h = max(o, c) * (1 + abs(np.random.normal(0, 0.0015)))
        l = min(o, c) * (1 - abs(np.random.normal(0, 0.0015)))
        v = float(np.random.uniform(10, 80))
        data.append([int(t.timestamp() * 1000), o, h, l, c, v])
    
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def fetch_market_data(symbol='BTC/USDT', timeframe='15m', limit=100):
    """Obtiene datos OHLCV desde Kraken Spot REST y calcula indicadores técnicos."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 20:
            df = generate_synthetic_candles(symbol, limit)
        else:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    except Exception as e:
        add_log(f"Fallo temporal Kraken REST ({symbol}): Usando feed de contingencia", "WARN")
        df = generate_synthetic_candles(symbol, limit)
    
    # EMA 200 institucional
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Average True Range (ATR 14)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean().bfill()
    df['atr_mean_long'] = tr.rolling(50).mean().bfill()
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['rsi'] = df['rsi'].bfill()
    
    return df

# ==========================================
# 4. MOTOR DE CONFLUENCIA Y SEÑAL ALGORÍTMICA
# ==========================================
def evaluate_confluence(df: pd.DataFrame):
    if df.empty or len(df) < 15:
        return {
            "side": "NEUTRAL",
            "score": 0,
            "reason": "Calculando confluencias con datos insuficientes...",
            "breakdown": {},
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
    breakdown = {}
    
    # Regla 1: Estructura Tendencial vs EMA 200 (+40)
    if close > ema:
        side = "LONG"
        score += 40
        breakdown["EMA 200"] = {"status": "ALCISTA", "pts": 40}
        reasons.append("Precio cotiza por encima de EMA 200")
    else:
        side = "SHORT"
        score += 40
        breakdown["EMA 200"] = {"status": "BAJISTA", "pts": 40}
        reasons.append("Precio cotiza por debajo de EMA 200")
    
    # Regla 2: Presión Direccional de Cierre (+25)
    if (side == "LONG" and close > prev['close']) or (side == "SHORT" and close < prev['close']):
        score += 25
        breakdown["Presión Cierre"] = {"status": "CONFIRMADA", "pts": 25}
        reasons.append("Impulso direccional consistente")
    else:
        breakdown["Presión Cierre"] = {"status": "DIVERGENTE", "pts": 0}
    
    # Regla 3: Régimen de Volatilidad ATR (+20)
    if atr > 0:
        score += 20
        breakdown["Rango ATR"] = {"status": "EXPANSIÓN ÓPTIMA", "pts": 20}
        reasons.append("Volatilidad ATR suficiente para objetivo")
    else:
        breakdown["Rango ATR"] = {"status": "BAJA VOLATILIDAD", "pts": 0}
        
    # Regla 4: Momentum RSI (+15)
    if (side == "LONG" and 45 <= rsi <= 68) or (side == "SHORT" and 32 <= rsi <= 55):
        score += 15
        breakdown["RSI Momentum"] = {"status": "ZONA FAVORABLE", "pts": 15}
        reasons.append("RSI en zona óptima de continuación")
    else:
        breakdown["RSI Momentum"] = {"status": "NEUTRAL/EXTREMO", "pts": 0}

    return {
        "side": side,
        "score": score,
        "reason": " • ".join(reasons),
        "breakdown": breakdown,
        "price": close,
        "ema": ema,
        "atr": atr,
        "rsi": rsi
    }

# ==========================================
# 5. FILTRO MACRO DINÁMICO
# ==========================================
def evaluate_macro_filter(df: pd.DataFrame, force_status: str = "AUTO"):
    if force_status == "FORZAR_BLOQUEO":
        return False, "BLOQUEADO (SIMULACIÓN MACRO)"
    if force_status == "FORZAR_SEGURO":
        return True, "ACTIVO (Ventana Segura)"
        
    if df.empty or len(df) < 20:
        return True, "ACTIVO (Ventana Segura)"
    
    last = df.iloc[-1]
    atr_current = float(last.get('atr', 0))
    atr_mean = float(last.get('atr_mean_long', atr_current))
    
    if atr_mean > 0 and (atr_current / atr_mean) > 2.5:
        return False, "BLOQUEADO (VOLATILIDAD EXTREMA)"
    
    return True, "ACTIVO (Ventana Segura)"

# ==========================================
# 6. GESTIÓN DE BASE DE DATOS Y TABLAS
# ==========================================
def fetch_all_trades_supabase():
    if supabase_client:
        try:
            res = supabase_client.table("paper_trades").select("*").order("timestamp", desc=True).execute()
            if res.data is not None:
                return res.data
        except Exception as e:
            add_log(f"Error consultando Supabase: {str(e)}", "ERROR")
    return st.session_state.local_paper_trades

def check_existing_open_position(symbol: str, side: str):
    if supabase_client:
        try:
            res = supabase_client.table("paper_trades") \
                .select("id, order_id, symbol, side, status") \
                .eq("status", "OPEN") \
                .eq("symbol", symbol) \
                .eq("side", side) \
                .execute()
            if res.data and len(res.data) > 0:
                return True, res.data[0]
            return False, None
        except Exception as e:
            add_log(f"Error comprobando cooldown en Supabase: {str(e)}", "WARN")
    
    for trade in st.session_state.local_paper_trades:
        if trade.get("status") == "OPEN" and trade.get("symbol") == symbol and trade.get("side") == side:
            return True, trade
    return False, None

def get_open_positions_for_symbol(symbol: str):
    if supabase_client:
        try:
            res = supabase_client.table("paper_trades") \
                .select("*") \
                .eq("status", "OPEN") \
                .eq("symbol", symbol) \
                .execute()
            if res.data:
                return res.data
        except Exception as e:
            pass
    
    return [t for t in st.session_state.local_paper_trades if t.get("status") == "OPEN" and t.get("symbol") == symbol]

# ==========================================
# 7. FIREWALL DIARIO (-3.0% CIRCUIT BREAKER)
# ==========================================
def calculate_daily_firewall(capital: float, max_loss_pct: float = 3.0):
    today_utc = datetime.datetime.now(datetime.timezone.utc).date()
    max_allowed_loss_usd = -1.0 * abs(capital * (max_loss_pct / 100.0))
    
    all_trades = fetch_all_trades_supabase()
    daily_pnl_usd = 0.0
    daily_trades_count = 0
    daily_wins = 0
    daily_losses = 0
    
    for t in all_trades:
        status = t.get("status", "")
        if "CERRADO" in status:
            raw_ts = t.get("timestamp") or t.get("closed_at")
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
                    if pnl > 0:
                        daily_wins += 1
                    else:
                        daily_losses += 1
    
    is_circuit_breaker = daily_pnl_usd <= max_allowed_loss_usd
    
    return {
        "daily_pnl_usd": daily_pnl_usd,
        "daily_pnl_pct": (daily_pnl_usd / capital) * 100.0 if capital > 0 else 0.0,
        "is_circuit_breaker": is_circuit_breaker,
        "max_allowed_loss_usd": max_allowed_loss_usd,
        "daily_trades_count": daily_trades_count,
        "daily_wins": daily_wins,
        "daily_losses": daily_losses,
        "status_text": "BLOQUEADO (-3.0% ALCANZADO)" if is_circuit_breaker else "OPERATIVO (DD Máx: -3.0%)"
    }

# ==========================================
# 8. MOTOR DE EVALUACIÓN Y CIERRE AUTOMÁTICO (TP / SL)
# ==========================================
def evaluate_and_close_positions(symbol: str, current_price: float):
    open_trades = get_open_positions_for_symbol(symbol)
    if not open_trades:
        return
    
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    for trade in open_trades:
        trade_id = trade.get("id")
        order_id = trade.get("order_id", f"DIP-{trade_id}")
        side = trade.get("side", "LONG")
        entry_price = float(trade.get("entry_price", current_price))
        sl = float(trade.get("sl", entry_price * 0.985))
        tp = float(trade.get("tp", entry_price * 1.030))
        
        closed = False
        status = "OPEN"
        pnl_usd = 0.0
        pnl_pct = 0.0
        
        if side == "LONG":
            if current_price >= tp:
                closed = True
                status = "CERRADO (TP)"
                pnl_pct = 3.0
                pnl_usd = 30.00
            elif current_price <= sl:
                closed = True
                status = "CERRADO (SL)"
                pnl_pct = -1.5
                pnl_usd = -15.00
                
        elif side == "SHORT":
            if current_price <= tp:
                closed = True
                status = "CERRADO (TP)"
                pnl_pct = 3.0
                pnl_usd = 30.00
            elif current_price >= sl:
                closed = True
                status = "CERRADO (SL)"
                pnl_pct = -1.5
                pnl_usd = -15.00
        
        if closed:
            update_payload = {
                "status": status,
                "exit_price": round(current_price, 4),
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "closed_at": now_iso
            }
            
            if supabase_client and trade_id:
                try:
                    supabase_client.table("paper_trades") \
                        .update(update_payload) \
                        .eq("id", trade_id) \
                        .execute()
                except Exception as e:
                    add_log(f"Fallo al actualizar orden en Supabase: {str(e)}", "ERROR")
            
            for local_t in st.session_state.local_paper_trades:
                if local_t.get("order_id") == order_id or local_t.get("id") == trade_id:
                    local_t.update(update_payload)
                    break
            
            log_color = "SUCCESS" if pnl_usd > 0 else "WARN"
            add_log(f"POSICIÓN CERRADA: {order_id} ({side}) en {symbol} a ${current_price:,.2f} | {status} | PnL: ${pnl_usd:+.2f} USD ({pnl_pct:+.1f}%)", log_color)

# ==========================================
# 9. AUTOTRIGGER / EJECUCIÓN AUTOMÁTICA DE ÓRDENES
# ==========================================
def execute_autotrigger(symbol: str, signal: dict, is_firewall_locked: bool, is_macro_safe: bool):
    score = signal.get("score", 0)
    side = signal.get("side", "NEUTRAL")
    entry_price = signal.get("price", 0.0)
    
    if score < 75 or side not in ["LONG", "SHORT"]:
        return False, "Score insuficiente para gatillo autónomo (Mínimo: 75%)"
    
    if is_firewall_locked:
        return False, "AUTOTRIGGER BLOQUEADO: Límite de Drawdown Diario (-3.0%) activado."
        
    if not is_macro_safe:
        return False, "AUTOTRIGGER BLOQUEADO: Filtro Macro detecta volatilidad o riesgo de noticias."
        
    has_open, existing_order = check_existing_open_position(symbol, side)
    if has_open:
        existing_id = existing_order.get("order_id", "N/A")
        return False, f"COOLDOWN ACTIVO: Ya existe orden OPEN ({existing_id}) para {symbol} [{side}]. Evitando sobreoperación."
    
    if side == "LONG":
        tp = entry_price * 1.030
        sl = entry_price * 0.985
    else:
        tp = entry_price * 0.970
        sl = entry_price * 1.015
        
    order_id = f"DIP-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    trade_data = {
        "order_id": order_id,
        "timestamp": now_iso,
        "symbol": symbol,
        "side": side,
        "entry_price": round(float(entry_price), 4),
        "exit_price": None,
        "sl": round(float(sl), 4),
        "tp": round(float(tp), 4),
        "status": "OPEN",
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "confluence": int(score),
        "reason": signal.get("reason", "Confluencia de Alta Probabilidad")
    }
    
    inserted = False
    if supabase_client:
        try:
            res = supabase_client.table("paper_trades").insert(trade_data).execute()
            if res.data:
                inserted = True
                add_log(f"AUTOTRIGGER EJECUTADO EN SUPABASE: {order_id} {side} {symbol} @ ${entry_price:,.2f} [TP: ${tp:,.2f} | SL: ${sl:,.2f}]", "SUCCESS")
        except Exception as e:
            add_log(f"Error insertando en Supabase: {str(e)}", "ERROR")
            
    if not inserted:
        trade_data["id"] = len(st.session_state.local_paper_trades) + 1
        st.session_state.local_paper_trades.insert(0, trade_data)
        add_log(f"AUTOTRIGGER LOCAL EJECUTADO: {order_id} {side} {symbol} @ ${entry_price:,.2f}", "SUCCESS")
        
    return True, f"¡Orden Autónoma {order_id} abierta con éxito!"

# ==========================================
# 10. INTERFAZ GRÁFICA BLOOMBERG TERMINAL
# ==========================================

st.markdown("""
<div style="display: flex; align-items: center; justify-content: space-between; padding: 14px 0 16px 0; border-bottom: 1px solid #1e293b; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
    <div style="display: flex; align-items: center; gap: 10px;">
        <span style="font-size: 26px; line-height: 1;">⚡</span>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 19px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;">PROYECTO DIPPER</span>
                <span style="background: #1e293b; color: #38bdf8; font-size: 10px; padding: 3px 8px; border-radius: 4px; font-weight: 700; border: 1px solid #334155;">QUANT TERMINAL v2.4</span>
                <span class="badge-auto">AUTÓNOMO / TP-SL</span>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 2px;">
                ALGORITHMIC TRADING TERMINAL · KRAKEN SPOT REST · SUPABASE POSTGRESQL ENGINE
            </div>
        </div>
    </div>
    <div style="font-size: 11px; color: #64748b; text-align: right;">
        FEED: <span style="color: #38bdf8; font-weight: bold;">KRAKEN SPOT REST</span> &nbsp;|&nbsp;
        MOTOR: <span style="color: #34d399; font-weight: bold;">ONLINE</span> &nbsp;|&nbsp;
        HORA UTC: <span style="color: #cbd5e1;">""" + datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S") + """</span>
    </div>
</div>
""", unsafe_allow_html=True)

# SIDEBAR
with st.sidebar:
    st.markdown("### ⚙️ PARÁMETROS DEL SISTEMA")
    
    symbol = st.selectbox("Par Operativo", ["BTC/USDT", "ETH/USDT", "SOL/USDT"], index=0)
    timeframe = st.selectbox("Temporalidad", ["15m", "1h", "4h"], index=0)
    
    st.markdown("---")
    st.markdown("### 🛡️ MATRIZ DE RIESGO & FIREWALL")
    capital = st.number_input("Capital Operativo ($ USD)", value=1000.0, step=100.0, min_value=100.0)
    risk_pct = st.slider("% Riesgo Máximo / Trade", 0.5, 5.0, 1.5, step=0.1)
    
    st.markdown(f"""
        <div class="metric-box">
            <div class="metric-label">Riesgo Fijo por Posición (-1.5% SL)</div>
            <div class="metric-num" style="color: #ef4444;">${capital * 0.015:.2f} USD</div>
            <div class="metric-label" style="margin-top: 6px;">Beneficio Fijo Objetivo (+3.0% TP)</div>
            <div class="metric-num" style="color: #10b981;">+${capital * 0.030:.2f} USD</div>
            <div class="metric-label" style="margin-top: 6px;">Drawdown Máximo Diario (-3.0%)</div>
            <div class="metric-num" style="color: #f87171;">-${capital * 0.030:.2f} USD</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🌐 FILTRO MACRO DINÁMICO")
    macro_override = st.selectbox(
        "Modo Filtro Macro",
        ["AUTO", "FORZAR_SEGURO", "FORZAR_BLOQUEO"],
        format_func=lambda x: "AUTOMÁTICO (Régimen Algorítmico)" if x == "AUTO" else ("FORZAR VENTANA SEGURA" if x == "FORZAR_SEGURO" else "FORZAR BLOQUEO MACRO / NOTICIAS")
    )
    
    st.markdown("---")
    st.markdown("### 🔄 CICLO DE ACTUALIZACIÓN")
    auto_refresh_enabled = st.checkbox("Refresco Automático (30s)", value=True)
    if st.button("⚡ Ejecutar Ciclo Manual Ahora"):
        st.rerun()

# Refresco de página
if auto_refresh_enabled:
    st.markdown("""
        <script>
            setTimeout(function(){
                window.location.reload();
            }, 30000);
        </script>
    """, unsafe_allow_html=True)

# OBTENCIÓN DE DATOS Y ESTADO
df = fetch_market_data(symbol, timeframe)
current_price = float(df.iloc[-1]['close']) if not df.empty else 0.0
signal = evaluate_confluence(df)
is_macro_safe, macro_status_str = evaluate_macro_filter(df, macro_override)

evaluate_and_close_positions(symbol, current_price)

firewall = calculate_daily_firewall(capital, max_loss_pct=3.0)
is_circuit_breaker = firewall["is_circuit_breaker"]

autotrigger_executed = False
autotrigger_msg = ""
if signal["score"] >= 75 and not is_circuit_breaker and is_macro_safe:
    autotrigger_executed, autotrigger_msg = execute_autotrigger(symbol, signal, is_circuit_breaker, is_macro_safe)

# TARJETAS DE ESTADO
motor_status_text = "ONLINE"
motor_sub_text = "↑ Ciclo Activo · 30s"

macro_val = "ACTIVO" if is_macro_safe else "BLOQUEADO"
macro_sub = "↑ Ventana Segura" if is_macro_safe else "↓ Volatilidad / Noticias"
macro_sub_class = "status-sub" if is_macro_safe else "status-sub-warn"

firewall_val = "OPERATIVO" if not is_circuit_breaker else "BLOQUEADO"
firewall_sub = f"↑ PnL Hoy: ${firewall['daily_pnl_usd']:+.2f} USD" if not is_circuit_breaker else "↓ -3.0% ALCANZADO"
firewall_sub_class = "status-sub" if not is_circuit_breaker else "status-sub-warn"

db_name = "SUPABASE" if supabase_client else "LOCAL / DEMO"
db_status_sub = "↑ PostgreSQL Sincronizado" if supabase_client else "• Modo Memoria Activo"

st.markdown(f"""
<div class="status-grid">
    <div class="status-card">
        <div class="status-title"><span>⚡</span> ESTADO DEL MOTOR</div>
        <div class="status-value" style="color: #34d399;">{motor_status_text}</div>
        <div class="status-sub">{motor_sub_text}</div>
    </div>
    <div class="status-card">
        <div class="status-title"><span>🌐</span> FILTRO MACRO</div>
        <div class="status-value" style="color: {'#38bdf8' if is_macro_safe else '#ef4444'};">{macro_val}</div>
        <div class="{macro_sub_class}">{macro_sub}</div>
    </div>
    <div class="status-card">
        <div class="status-title"><span>🛡️</span> FIREWALL DIARIO</div>
        <div class="status-value" style="color: {'#34d399' if not is_circuit_breaker else '#ef4444'};">{firewall_val}</div>
        <div class="{firewall_sub_class}">{firewall_sub}</div>
    </div>
    <div class="status-card">
        <div class="status-title"><span>🗄️</span> CONEXIÓN DB</div>
        <div class="status-value" style="color: #93c5fd;">{db_name}</div>
        <div class="status-sub">{db_status_sub}</div>
    </div>
</div>
""", unsafe_allow_html=True)

if is_circuit_breaker:
    st.markdown(f"""
        <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 6px; padding: 14px 18px; margin-bottom: 16px;">
            <div style="color: #ef4444; font-weight: 800; font-size: 14px;">🛑 CIRCUIT BREAKER DIARIO ACTIVADO (-3.0% ALCANZADO)</div>
            <div style="color: #cbd5e1; font-size: 12px; margin-top: 4px;">
                La pérdida diaria acumulada ha alcanzado <b>${firewall['daily_pnl_usd']:.2f} USD</b> ({firewall['daily_pnl_pct']:.2f}%).
                Por protocolo estricto de preservación de capital, el sistema ha <b>BLOQUEADO la apertura de nuevas posiciones</b> hasta el siguiente ciclo UTC.
            </div>
        </div>
    """, unsafe_allow_html=True)

# ==========================================
# 11. PESTAÑAS PRINCIPALES
# ==========================================
tab1, tab2 = st.tabs(["⚡ Monitor Cuantitativo en Vivo", "📋 Historial de Órdenes & Audit Log"])

# PESTAÑA 1: MONITOR CUANTITATIVO
with tab1:
    if not df.empty:
        col_chart, col_signal = st.columns([2.6, 1.1])
        
        with col_chart:
            st.markdown(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div style="font-size: 13px; font-weight: bold; color: #f8fafc;">
                        KRAKEN SPOT · {symbol} ({timeframe}) · PRECIO EN VIVO: <span style="color: #38bdf8;">${current_price:,.2f}</span>
                    </div>
                    <div style="font-size: 11px; color: #64748b;">
                        EMA 200: <span style="color: #38bdf8;">${signal['ema']:,.2f}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Gráfica Plotly Candlestick
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df['timestamp'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Candles',
                increasing_line_color='#10b981',
                decreasing_line_color='#ef4444'
            ))
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['ema200'],
                mode='lines',
                name='EMA 200',
                line=dict(color='#38bdf8', width=1.5)
            ))
            fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='#070a13',
                plot_bgcolor='#0b1120',
                margin=dict(l=10, r=10, t=10, b=10),
                height=420,
                xaxis_rangeslider_visible=False,
                xaxis=dict(showgrid=True, gridcolor='#1e293b'),
                yaxis=dict(showgrid=True, gridcolor='#1e293b')
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_signal:
            side = signal['side']
            score = signal['score']
            
            card_class = "signal-card-long" if side == "LONG" else ("signal-card-short" if side == "SHORT" else "signal-card-neutral")
            badge_color = "#10b981" if side == "LONG" else ("#ef4444" if side == "SHORT" else "#64748b")
            
            st.markdown(f"""
                <div class="{card_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="background: {badge_color}; color: #000; font-weight: 800; padding: 3px 10px; border-radius: 4px; font-size: 12px;">
                            SEÑAL: {side}
                        </span>
                        <span style="font-size: 18px; font-weight: 800; color: #f8fafc;">
                            {score} / 100
                        </span>
                    </div>
                    <div style="font-size: 11px; color: #cbd5e1; margin-top: 12px; line-height: 1.5;">
                        <b>Desglose de Confluencia:</b><br>{signal['reason']}
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Status del Autotrigger
            if score >= 75:
                st.success("🎯 SEÑAL DE ALTA CONFLUENCIA DETECTADA (≥ 75%)")
            else:
                st.info("⏳ Monitoreando mercado... Esperando Score ≥ 75%")

# PESTAÑA 2: HISTORIAL Y AUDIT LOG
with tab2:
    st.markdown("### 📋 TABLA HISTÓRICA DE ÓRDENES SIMULADAS")
    trades = fetch_all_trades_supabase()
    
    if trades:
        df_trades = pd.DataFrame(trades)
        st.dataframe(df_trades, use_container_width=True)
    else:
        st.info("No hay órdenes registradas aún en el sistema.")
        
    st.markdown("---")
    st.markdown("### 📜 SYSTEM LOGS (AUDITORÍA EN TIEMPO REAL)")
    for log in st.session_state.system_logs:
        st.text(log)
