# -*- coding: utf-8 -*-
"""
========================================================================================
PROYECTO DIPPER | SISTEMA CUANTITATIVO DE TRADING ALGORÍTMICO (KRAKEN & SUPABASE)
========================================================================================
Arquitectura: Cuantitativa y Modular con CCXT, Kraken Spot REST, Supabase (PostgreSQL), Ntfy
Monitoreo: 24/7 Execution Engine para despliegue en la nube (Render Worker / Background)
Gestión de Riesgo:
  - Filtro Macro Institucional en 4H (EMA 200)
  - Gestión Dinámica de Posición e Interés Compuesto Exponencial (1.5% riesgo por trade)
  - Distancia de Stop Loss: 1.5% | Distancia de Take Profit: 3.0% (Ratio R:R 1:2)
  - Fusible de Seguridad (Circuit Breaker Diario de -3.0% acumulado con Supabase)
  - Validación de Volumen Mínimo de Kraken ($10.0 USD de margen de seguridad)
  - Alertas HTTP Push en Tiempo Real mediante Ntfy.sh
========================================================================================
"""

# ======================================================================================
# SECCIÓN 1: IMPORTACIONES Y CONFIGURACIÓN DE LOGS/ENTORNO
# ======================================================================================
import os
import sys
import time
import math
import logging
import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any, Tuple, List

import requests
import ccxt
import pandas as pd
import numpy as np

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    Client = Any  # type: ignore

try:
    import zoneinfo
    try:
        TZ_COT = zoneinfo.ZoneInfo("America/Bogota")
    except Exception:
        TZ_COT = datetime.timezone(datetime.timedelta(hours=-5))
except ImportError:
    TZ_COT = datetime.timezone(datetime.timedelta(hours=-5))

# Configuración del Logger de Nivel Producción
logger = logging.getLogger("ProyectoDipper")
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter(
    fmt="[%(asctime)s COT] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# Sobrescribir el formateador de tiempo para reportar consistentemente en hora Colombia (COT)
def cot_time_converter(*args):
    return datetime.datetime.now(TZ_COT).timetuple()

log_formatter.converter = cot_time_converter

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
if not logger.handlers:
    logger.addHandler(stream_handler)

# Carga Estricta de Variables de Entorno usando os.getenv
KRAKEN_API_KEY: str = os.getenv("KRAKEN_API_KEY", "").strip()
KRAKEN_SECRET_KEY: str = os.getenv("KRAKEN_SECRET_KEY", "").strip()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "PROYECTO_DIPPER_BOT_ALERTAS").strip()

# Parámetros Cuantitativos e Institucionales de Riesgo
RISK_PER_TRADE: float = 0.015         # 1.5% de riesgo sobre balance disponible
STOP_LOSS_PCT: float = 0.015          # -1.5% distancia de Stop Loss
TAKE_PROFIT_PCT: float = 0.030        # +3.0% distancia de Take Profit
DAILY_CIRCUIT_BREAKER: float = -0.03  # -3.0% fusible de seguridad diario
MIN_ORDER_USD: float = 10.0           # Margen de seguridad mínimo de Kraken ($10.0 USD)
MAX_CONCURRENT_POSITIONS: int = 3     # Límite de 3 posiciones simultáneas
CYCLE_SLEEP_SECONDS: int = 900        # Ciclo de velas de 15 minutos (900 segundos)

# Universo de Trading: 18 Pares Kraken Spot Nativos en USD
WATCHLIST_SYMBOLS: List[str] = [
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD",
    "XRP/USD", "DOT/USD", "AVAX/USD", "LINK/USD",
    "LTC/USD", "BCH/USD", "NEAR/USD", "SUI/USD",
    "APT/USD", "FET/USD", "ARB/USD", "PEPE/USD",
    "DOGE/USD", "SHIB/USD"
]

logger.info("==================================================================")
logger.info("SECCIÓN 1 CARGADA: Entorno, logs y constantes de riesgo inicializados.")
logger.info(f"NTFY Topic: {NTFY_TOPIC} | Universo de Monitoreo: {len(WATCHLIST_SYMBOLS)} activos")
logger.info(f"Riesgo/Trade: {RISK_PER_TRADE*100}% | SL: {STOP_LOSS_PCT*100}% | TP: {TAKE_PROFIT_PCT*100}% | Circuit Breaker: {DAILY_CIRCUIT_BREAKER*100}%")
logger.info("==================================================================")


# ======================================================================================
# SECCIÓN 2: CONEXIONES API (KRAKEN, SUPABASE Y ALERTAS NTFY)
# ======================================================================================
def init_kraken_exchange() -> ccxt.kraken:
    """
    Inicializa la instancia de CCXT Kraken con autenticación segura y rate-limiting activado.
    Permite operar en modo autenticado o de lectura de mercado si no hay API keys configuradas.
    """
    exchange_config: Dict[str, Any] = {
        'enableRateLimit': True,
        'timeout': 30000,
        'options': {
            'adjustForTimeDifference': True,
        }
    }
    if KRAKEN_API_KEY and KRAKEN_SECRET_KEY:
        exchange_config['apiKey'] = KRAKEN_API_KEY
        exchange_config['secret'] = KRAKEN_SECRET_KEY
        logger.info("Kraken API: Credenciales privadas cargadas para trading real.")
    else:
        logger.warning("Kraken API: Claves de API no detectadas. Operando en modo público/paper trading.")

    exchange = ccxt.kraken(exchange_config)
    try:
        exchange.load_markets()
        logger.info(f"Kraken API: Mercados cargados exitosamente ({len(exchange.markets)} pares disponibles).")
    except Exception as e:
        logger.error(f"Kraken API: Error cargando mercados en inicialización: {e}")
    return exchange

# Instancia global del exchange
exchange: ccxt.kraken = init_kraken_exchange()

def init_supabase_client() -> Optional[Client]:
    """
    Inicializa el cliente de Supabase para persistencia relacional en PostgreSQL.
    """
    if not HAS_SUPABASE:
        logger.error("Supabase: La librería 'supabase' no está instalada en el entorno.")
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase: SUPABASE_URL o SUPABASE_KEY no configuradas en variables de entorno.")
        return None
    try:
        client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase: Conexión establecida con éxito hacia PostgreSQL.")
        return client
    except Exception as e:
        logger.error(f"Supabase: Error al conectar con el servidor: {e}")
        return None

# Instancia global de Supabase
supabase_client: Optional[Client] = init_supabase_client()

def send_ntfy_alert(message: str, title: str = "PROYECTO DIPPER | ALERTA", priority: str = "default") -> bool:
    """
    Envía una notificación Push en tiempo real a través de Ntfy.sh mediante HTTP POST.
    Resistente a fallos: cualquier error de conexión o HTTP nunca interrumpe el ciclo del bot.
    """
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    try:
        safe_title = title.encode('latin-1', 'ignore').decode('latin-1').strip()
        if not safe_title:
            safe_title = "PROYECTO DIPPER | ALERTA"

        headers = {
            "Title": safe_title,
            "Priority": priority,
            "Tags": "chart_with_upwards_trend,robot"
        }
        response = requests.post(
            url,
            data=message.encode('utf-8'),
            headers=headers,
            timeout=8
        )
        if response.status_code == 200:
            logger.info(f"Ntfy Push enviada exitosamente: '{title}'")
            return True
        else:
            logger.warning(f"Ntfy Push retornó código de estado {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ntfy Push: Excepción de red silenciada (sin interrumpir el bot): {e}")
        return False

def resolve_kraken_pair(ex: ccxt.kraken, symbol: str) -> str:
    """
    Resuelve el símbolo estándar (ej. 'BTC/USD') al par interno compatible con Kraken Spot.
    """
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


# ======================================================================================
# SECCIÓN 3: ANÁLISIS TÉCNICO & FILTRO MACRO (4H)
# ======================================================================================
def check_macro_trend_4h(symbol: str) -> str:
    """
    Descarga velas de 4 Horas (timeframe='4h') y calcula la EMA de 200 periodos.
    
    Regla Estricta Cuantitativa:
      - Si precio_actual > EMA_200 (4H) ➔ 'BULLISH'
      - Si precio_actual < EMA_200 (4H) ➔ 'BEARISH'
      - Si falta data o precio está dentro del margen neutral ➔ 'NEUTRAL'
      
    Regla de Ejecución:
      - En 15m, el bot solo abre posiciones LONG si el macro es 'BULLISH',
      - O posiciones SHORT si el macro es 'BEARISH'.
      - Entradas en contra de la tendencia macro quedan estrictamente descartadas.
    """
    try:
        target_pair = resolve_kraken_pair(exchange, symbol)
        ohlcv = exchange.fetch_ohlcv(target_pair, timeframe='4h', limit=250)
        
        if not ohlcv or len(ohlcv) < 50:
            logger.warning(f"Macro 4H: Insuficientes velas descargadas para {symbol} (recibidas: {len(ohlcv) if ohlcv else 0}).")
            return 'NEUTRAL'
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        current_price = float(df['close'].iloc[-1])
        
        # Cálculo de la EMA de 200 periodos en 4H
        span_period = 200 if len(df) >= 200 else len(df)
        df['ema200'] = df['close'].ewm(span=span_period, adjust=False).mean()
        ema_200_val = float(df['ema200'].iloc[-1])
        
        if ema_200_val <= 0:
            return 'NEUTRAL'
            
        ratio_diff = (current_price - ema_200_val) / ema_200_val
        
        # Filtro de zona muerta mínima (+/- 0.05% alrededor de la EMA)
        if ratio_diff > 0.0005:
            trend = 'BULLISH'
        elif ratio_diff < -0.0005:
            trend = 'BEARISH'
        else:
            trend = 'NEUTRAL'
            
        logger.info(
            f"Filtro Macro 4H [{symbol}]: Precio=${current_price:,.4f} | "
            f"EMA200(4H)=${ema_200_val:,.4f} | Dif={ratio_diff*100:+.2f}% ➔ Tendencia: {trend}"
        )
        return trend

    except ccxt.NetworkError as ne:
        logger.error(f"Filtro Macro 4H [{symbol}]: Error de red al consultar velas 4H: {ne}")
        return 'NEUTRAL'
    except ccxt.ExchangeError as ee:
        logger.error(f"Filtro Macro 4H [{symbol}]: Error de API Kraken: {ee}")
        return 'NEUTRAL'
    except Exception as e:
        logger.error(f"Filtro Macro 4H [{symbol}]: Excepción no controlada: {e}")
        return 'NEUTRAL'

def analyze_entry_signal_15m(symbol: str, macro_trend: str) -> Optional[Dict[str, Any]]:
    """
    Analiza la temporalidad menor (15m) combinando EMA 200, ATR(14) y RSI(14).
    Filtro Estricto:
      - Solo permite LONG si macro_trend == 'BULLISH'
      - Solo permite SHORT si macro_trend == 'BEARISH'
      - Desecha cualquier señal que contradiga la tendencia mayor.
    """
    try:
        target_pair = resolve_kraken_pair(exchange, symbol)
        ohlcv = exchange.fetch_ohlcv(target_pair, timeframe='15m', limit=70)
        
        if not ohlcv or len(ohlcv) < 30:
            return None
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        current_price = float(df['close'].iloc[-1])
        
        # EMA 200 en 15m
        span_15m = 200 if len(df) >= 200 else len(df)
        df['ema200'] = df['close'].ewm(span=span_15m, adjust=False).mean()
        ema_val = float(df['ema200'].iloc[-1])
        
        # RSI 14
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs))
        rsi_val = float(df['rsi'].fillna(50.0).iloc[-1])
        
        # ATR 14
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_val = float(tr.rolling(14).mean().bfill().iloc[-1])
        
        signal_side = "NEUTRAL"
        signal_score = 0
        
        # Lógica Cuantitativa de Gatillo 15m
        if current_price > ema_val and rsi_val > 50.0:
            signal_side = "LONG"
            signal_score = int(min(95, 60 + (rsi_val - 50) * 1.2 + 15))
        elif current_price < ema_val and rsi_val < 50.0:
            signal_side = "SHORT"
            signal_score = int(min(95, 60 + (50 - rsi_val) * 1.2 + 15))
            
        # FILTRO MACRO ESTRICTO
        if signal_side == "LONG" and macro_trend != "BULLISH":
            logger.info(f"Gatillo descartado [{symbol}]: Señal 15m LONG bloqueada por Macro 4H {macro_trend}.")
            return None
        if signal_side == "SHORT" and macro_trend != "BEARISH":
            logger.info(f"Gatillo descartado [{symbol}]: Señal 15m SHORT bloqueada por Macro 4H {macro_trend}.")
            return None
            
        if signal_score >= 70 and signal_side in ["LONG", "SHORT"]:
            return {
                "symbol": symbol,
                "side": signal_side,
                "score": signal_score,
                "price": current_price,
                "ema200": ema_val,
                "rsi": rsi_val,
                "atr": atr_val,
                "macro_trend": macro_trend
            }
        return None

    except Exception as e:
        logger.error(f"Error analizando señal 15m para {symbol}: {e}")
        return None


# ======================================================================================
# SECCIÓN 4: GESTIÓN DINÁMICA DE POSICIÓN (INTERÉS COMPUESTO EXPONENCIAL)
# ======================================================================================
def get_realtime_free_balance() -> float:
    """
    Consulta en tiempo real el balance libre disponible en USD o USDT en Kraken
    mediante exchange.fetch_balance(). Si está en modo paper sin API keys,
    retorna un balance operativo base de $1,000.0 USD.
    """
    if not (KRAKEN_API_KEY and KRAKEN_SECRET_KEY):
        return 1000.0

    try:
        balance_data = exchange.fetch_balance()
        free_balances = balance_data.get('free', {})
        
        # Buscar en activos fiat y stablecoins soportados por Kraken
        usd_free = float(free_balances.get('USD', 0.0) or 0.0)
        usdt_free = float(free_balances.get('USDT', 0.0) or 0.0)
        zusd_free = float(free_balances.get('ZUSD', 0.0) or 0.0)
        
        total_liquid = usd_free + usdt_free + zusd_free
        if total_liquid > 0:
            logger.info(f"Kraken Balance Libre Disponible: ${total_liquid:,.2f} USD (USD={usd_free}, USDT={usdt_free}, ZUSD={zusd_free})")
            return total_liquid
        else:
            logger.warning("Kraken Balance: Fondos libres en USD/USDT resultaron en $0.00.")
            return 0.0

    except ccxt.AuthenticationError as ae:
        logger.error(f"Kraken Auth Error consultando balance: {ae}")
        return 1000.0
    except ccxt.NetworkError as ne:
        logger.error(f"Kraken Network Error consultando balance: {ne}")
        return 1000.0
    except Exception as e:
        logger.error(f"Error inesperado consultando balance: {e}")
        return 1000.0

def calculate_dynamic_position_size(symbol: str, current_price: float, side: str) -> Optional[Dict[str, Any]]:
    """
    Aplica el modelo de Interés Compuesto Exponencial:
      1. Consulta el balance libre real actualizado.
      2. Calcula el riesgo del 1.5% (RISK_PER_TRADE = 0.015) sobre el saldo libre.
      3. Distancia de Stop Loss: 1.5% (STOP_LOSS_PCT = 0.015).
      4. Distancia de Take Profit: 3.0% (TAKE_PROFIT_PCT = 0.030).
      5. Fórmula de tamaño:
         - Riesgo en $ USD = free_balance * RISK_PER_TRADE
         - Tamaño de la Posición ($ USD) = Riesgo_USD / STOP_LOSS_PCT = free_balance
         - Volumen en Cripto = Tamaño_USD / current_price
      6. Validación Mínima de Exchange:
         - El volumen total en USD debe superar el mínimo de Kraken ($10.0 USD de margen de seguridad).
         - Si no alcanza, se ajusta al mínimo de $10.0 o se descarta con log explícito.
    """
    free_balance = get_realtime_free_balance()
    if free_balance <= 0:
        logger.warning(f"Gestión de Posición [{symbol}]: Saldo libre insuficiente (${free_balance:,.2f} USD).")
        return None

    # Riesgo absoluto en $ USD para el trade actual
    risk_amount_usd = free_balance * RISK_PER_TRADE
    
    # Capital total a asignar a la posición (en spot 1:1, arriesgar 1.5% con SL de 1.5% = posición de 100% de la base asignada o 1/3 del portafolio)
    # Para respetar el límite de 3 posiciones concurrentes, asignamos max 1/3 del balance por orden
    target_position_usd = (free_balance / float(MAX_CONCURRENT_POSITIONS))
    
    # Precios objetivo de Take Profit y Stop Loss
    if side == "LONG":
        tp_price = current_price * (1.0 + TAKE_PROFIT_PCT)
        sl_price = current_price * (1.0 - STOP_LOSS_PCT)
    else:  # SHORT
        tp_price = current_price * (1.0 - TAKE_PROFIT_PCT)
        sl_price = current_price * (1.0 + STOP_LOSS_PCT)
        
    # Validación del Margen Mínimo de Kraken ($10.0 USD)
    if target_position_usd < MIN_ORDER_USD:
        logger.warning(
            f"Validación Mínima Kraken [{symbol}]: Posición calculada (${target_position_usd:.2f} USD) "
            f"es inferior al mínimo de seguridad (${MIN_ORDER_USD:.2f} USD). Ajustando al mínimo de $10.0 USD."
        )
        if free_balance >= MIN_ORDER_USD:
            target_position_usd = MIN_ORDER_USD
        else:
            logger.error(f"Orden descartada [{symbol}]: Saldo disponible total (${free_balance:.2f}) no cubre el mínimo de $10.0 USD.")
            return None

    # Cálculo del volumen exacto en criptoactivo
    volume_crypto = target_position_usd / current_price
    
    # Formateo y redondeo de precisión
    crypto_volume_rounded = float(round(volume_crypto, 6 if current_price < 1.0 else 4))
    if crypto_volume_rounded <= 0:
        crypto_volume_rounded = volume_crypto

    logger.info(
        f"Gestión Dinámica de Posición [{symbol} - {side}]: "
        f"Balance Libre=${free_balance:,.2f} USD | Capital Posición=${target_position_usd:,.2f} USD | "
        f"Volumen={crypto_volume_rounded} unidades | Precio Entrada=${current_price:,.4f} | "
        f"TP (+3.0%)=${tp_price:,.4f} | SL (-1.5%)=${sl_price:,.4f}"
    )

    return {
        "symbol": symbol,
        "side": side,
        "entry_price": current_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "target_position_usd": target_position_usd,
        "risk_amount_usd": risk_amount_usd,
        "volume_crypto": crypto_volume_rounded
    }


# ======================================================================================
# SECCIÓN 5: SINCRONIZACIÓN Y FUSIBLE DE SEGURIDAD (CIRCUIT BREAKER CON SUPABASE)
# ======================================================================================
def get_today_utc_date_str() -> str:
    """Retorna la fecha actual en formato ISO YYYY-MM-DD en UTC."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

def is_circuit_breaker_active() -> bool:
    """
    Consulta en Supabase la tabla 'daily_metrics' filtrando por la fecha actual (CURRENT_DATE).
    Si la pérdida acumulada del día alcanza o supera el -3.0% (DAILY_CIRCUIT_BREAKER = -0.03),
    retorna True para congelar la apertura de nuevas órdenes durante 24 horas y emite alerta crítica.
    """
    today_str = get_today_utc_date_str()
    
    if not supabase_client:
        logger.warning("Circuit Breaker: Sin cliente Supabase activo; omitiendo bloqueo por DB.")
        return False
        
    try:
        response = supabase_client.table("daily_metrics").select("*").eq("metric_date", today_str).execute()
        rows = response.data if response else []
        
        if rows and len(rows) > 0:
            metric = rows[0]
            daily_pnl_pct = float(metric.get("daily_pnl_pct", 0.0) or 0.0)
            is_locked = bool(metric.get("is_circuit_breaker_triggered", False))
            
            # Verificar condición de disparo
            if daily_pnl_pct <= (DAILY_CIRCUIT_BREAKER * 100.0) or is_locked:
                logger.critical(
                    f"🚨 FUSIBLE DE SEGURIDAD ACTIVADO: Pérdida diaria acumulada = {daily_pnl_pct:+.2f}% "
                    f"(Umbral: {DAILY_CIRCUIT_BREAKER*100}%). Apertura de nuevas órdenes CONGELADA."
                )
                return True
                
        return False

    except Exception as e:
        logger.error(f"Error consultando 'daily_metrics' en Supabase para Circuit Breaker: {e}")
        return False

def sync_daily_pnl_supabase(trade_pnl_usd: float, trade_pnl_pct: float) -> bool:
    """
    Sincroniza el resultado de un trade cerrado con la tabla 'daily_metrics' en Supabase.
    Si la pérdida acumulada traspasa el umbral de -3.0%, actualiza 'is_circuit_breaker_triggered = True'
    y dispara una alerta urgente de alta prioridad vía Ntfy.
    """
    today_str = get_today_utc_date_str()
    
    if not supabase_client:
        logger.warning("Sync Daily PnL: Supabase no disponible. Operación en memoria.")
        return False
        
    try:
        # Consultar métrica existente del día
        res = supabase_client.table("daily_metrics").select("*").eq("metric_date", today_str).execute()
        rows = res.data if res else []
        
        if rows and len(rows) > 0:
            existing = rows[0]
            row_id = existing.get("id")
            current_usd = float(existing.get("daily_pnl_usd", 0.0) or 0.0)
            current_pct = float(existing.get("daily_pnl_pct", 0.0) or 0.0)
            total_trades = int(existing.get("trades_count", 0) or 0)
            
            new_pnl_usd = round(current_usd + trade_pnl_usd, 2)
            new_pnl_pct = round(current_pct + trade_pnl_pct, 2)
            new_trades_count = total_trades + 1
            
            trigger_breaker = new_pnl_pct <= (DAILY_CIRCUIT_BREAKER * 100.0)
            
            update_data = {
                "daily_pnl_usd": new_pnl_usd,
                "daily_pnl_pct": new_pnl_pct,
                "trades_count": new_trades_count,
                "is_circuit_breaker_triggered": trigger_breaker,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            supabase_client.table("daily_metrics").update(update_data).eq("id", row_id).execute()
            logger.info(f"Supabase daily_metrics actualizado: PnL Diario=${new_pnl_usd:+.2f} USD ({new_pnl_pct:+.2f}%)")
            
            if trigger_breaker:
                send_ntfy_alert(
                    message=(
                        f"🚨 BLOQUEO CRÍTICO DE SEGURIDAD 🚨\n"
                        f"El Circuit Breaker Diario se ha ACTIVADO.\n"
                        f"Pérdida acumulada: {new_pnl_pct:+.2f}% (${new_pnl_usd:+.2f} USD)\n"
                        f"Umbral límite: {DAILY_CIRCUIT_BREAKER*100}%\n"
                        f"Acción: Apertura de nuevas posiciones congelada por 24 horas."
                    ),
                    title="🚨 CIRCUIT BREAKER DIARIO ACTIVADO (-3.0%)",
                    priority="urgent"
                )
        else:
            trigger_breaker = trade_pnl_pct <= (DAILY_CIRCUIT_BREAKER * 100.0)
            insert_data = {
                "metric_date": today_str,
                "daily_pnl_usd": round(trade_pnl_usd, 2),
                "daily_pnl_pct": round(trade_pnl_pct, 2),
                "trades_count": 1,
                "is_circuit_breaker_triggered": trigger_breaker,
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            supabase_client.table("daily_metrics").insert(insert_data).execute()
            logger.info(f"Supabase daily_metrics creado para hoy: PnL=${trade_pnl_usd:+.2f} USD ({trade_pnl_pct:+.2f}%)")
            
            if trigger_breaker:
                send_ntfy_alert(
                    message=f"🚨 CIRCUIT BREAKER ACTIVADO en primera orden: {trade_pnl_pct:+.2f}%. Nuevas órdenes suspendidas.",
                    title="🚨 CIRCUIT BREAKER DIARIO ACTIVADO",
                    priority="urgent"
                )
                
        return True

    except Exception as e:
        logger.error(f"Error sincronizando daily PnL en Supabase: {e}")
        return False

def get_open_positions_count() -> int:
    """Consulta cuántas posiciones activas ('OPEN') existen en Supabase."""
    if not supabase_client:
        return 0
    try:
        res = supabase_client.table("paper_trades").select("id").eq("status", "OPEN").execute()
        count = len(res.data) if res and res.data else 0
        return count
    except Exception as e:
        logger.error(f"Error consultando posiciones abiertas en Supabase: {e}")
        return 0

def check_open_position_for_symbol(symbol: str) -> bool:
    """Verifica si ya existe una posición abierta para el par indicado (máximo 1 por par)."""
    if not supabase_client:
        return False
    try:
        res = supabase_client.table("paper_trades").select("id").eq("symbol", symbol).eq("status", "OPEN").execute()
        return bool(res.data and len(res.data) > 0)
    except Exception as e:
        logger.error(f"Error verificando posición abierta para {symbol}: {e}")
        return False


# ======================================================================================
# SECCIÓN 6: BUCLE PRINCIPAL (EXECUTION ENGINE 24/7)
# ======================================================================================
def monitor_and_close_positions():
    """
    Monitorea todas las posiciones abiertas en Supabase contra el precio actual de mercado de Kraken.
    Ejecuta el cierre inmediato si se alcanza el Take Profit (+3.0%) o Stop Loss (-1.5%).
    Calcula PnL estricto en $ USD y notifica vía Ntfy.
    """
    if not supabase_client:
        return
        
    try:
        res = supabase_client.table("paper_trades").select("*").eq("status", "OPEN").execute()
        open_trades = res.data if res and res.data else []
        
        if not open_trades:
            return
            
        logger.info(f"Monitoreando {len(open_trades)} posición(es) abierta(s)...")
        
        for trade in open_trades:
            order_id = trade.get("order_id")
            trade_id = trade.get("id")
            sym = trade.get("symbol")
            side = trade.get("side", "LONG")
            entry_price = float(trade.get("entry_price", 0.0))
            tp = float(trade.get("tp", 0.0))
            sl = float(trade.get("sl", 0.0))
            pos_capital = float(trade.get("target_position_usd", 0.0) or 1000.0 / MAX_CONCURRENT_POSITIONS)
            
            # Obtener precio actual de Kraken
            try:
                target_pair = resolve_kraken_pair(exchange, sym)
                ticker = exchange.fetch_ticker(target_pair)
                current_price = float(ticker.get('last') or ticker.get('close') or entry_price)
            except Exception as e_tick:
                logger.warning(f"No se pudo obtener ticker para {sym}: {e_tick}")
                continue
                
            closed = False
            close_status = ""
            pnl_pct = 0.0
            pnl_usd = 0.0
            
            # Evaluación estricta de salida por Take Profit o Stop Loss
            if side == "LONG":
                if current_price >= tp:
                    closed = True
                    close_status = "CERRADO (TP)"
                    pnl_pct = 3.0
                    pnl_usd = pos_capital * TAKE_PROFIT_PCT
                elif current_price <= sl:
                    closed = True
                    close_status = "CERRADO (SL)"
                    pnl_pct = -1.5
                    pnl_usd = -1.0 * (pos_capital * STOP_LOSS_PCT)
            elif side == "SHORT":
                if current_price <= tp:
                    closed = True
                    close_status = "CERRADO (TP)"
                    pnl_pct = 3.0
                    pnl_usd = pos_capital * TAKE_PROFIT_PCT
                elif current_price >= sl:
                    closed = True
                    close_status = "CERRADO (SL)"
                    pnl_pct = -1.5
                    pnl_usd = -1.0 * (pos_capital * STOP_LOSS_PCT)
                    
            if closed:
                # Asegurar signos matemáticos correctos
                if "SL" in close_status:
                    pnl_pct = -abs(pnl_pct)
                    pnl_usd = -abs(pnl_usd)
                elif "TP" in close_status:
                    pnl_pct = abs(pnl_pct)
                    pnl_usd = abs(pnl_usd)
                    
                update_payload = {
                    "status": close_status,
                    "exit_price": round(current_price, 4),
                    "pnl_usd": round(pnl_usd, 2),
                    "pnl_pct": round(pnl_pct, 2)
                }
                
                # Actualizar registro en Supabase
                try:
                    supabase_client.table("paper_trades").update(update_payload).eq("id", trade_id).execute()
                except Exception as e_up:
                    logger.error(f"Error actualizando orden {order_id} en Supabase: {e_up}")
                    
                # Sincronizar métricas diarias y verificar fusible
                sync_daily_pnl_supabase(pnl_usd, pnl_pct)
                
                logger.info(
                    f"POSICIÓN CERRADA: {order_id} ({side}) {sym} a ${current_price:,.4f} | "
                    f"{close_status} | PnL: ${pnl_usd:+.2f} USD ({pnl_pct:+.2f}%)"
                )
                
                # Disparador de Alerta Push Ntfy por Cierre
                icon = "🎯" if "TP" in close_status else "🛑"
                title_alert = f"{icon} POSICIÓN CERRADA: {sym} [{side}] - {close_status}"
                sign_str = "+" if pnl_usd > 0 else "-"
                msg_alert = (
                    f"📊 Par: {sym}\n"
                    f"📈 Tipo: {side}\n"
                    f"🚪 Motivo de Cierre: {close_status}\n"
                    f"💵 Precio Cierre: ${current_price:,.4f}\n"
                    f"📊 PnL (%): {pnl_pct:+.2f}%\n"
                    f"💰 PnL ($ USD): {sign_str}${abs(pnl_usd):,.2f} USD\n"
                    f"⚡ ID Orden: {order_id}"
                )
                send_ntfy_alert(msg_alert, title_alert, priority="default")

    except Exception as e:
        logger.error(f"Error en monitor_and_close_positions: {e}")

def execute_trading_cycle():
    """
    Ejecuta un ciclo completo de evaluación cuantitativa sobre el universo de 18 pares:
      1. Monitorea y cierra posiciones activas existentes.
      2. Verifica el fusible de seguridad (Circuit Breaker Diario de -3.0%).
      3. Verifica el límite de concurrencia (máximo 3 posiciones abiertas).
      4. Itera cada par de la WATCHLIST evaluando:
         - Filtro Macro Institucional en 4H (EMA 200).
         - Gatillo en 15m alineado estrictamente con el Macro.
         - Cálculo de tamaño con Interés Compuesto Exponencial y validación de Kraken.
         - Apertura y persistencia de orden en Supabase.
         - Notificación Push inmediata en Ntfy.
    """
    logger.info("------------------------------------------------------------------")
    logger.info("INICIO DE CICLO CUANTITATIVO DE EVALUACIÓN")
    logger.info("------------------------------------------------------------------")
    
    # 1. Monitoreo de salidas de posiciones abiertas
    monitor_and_close_positions()
    
    # 2. Verificación del Circuit Breaker
    if is_circuit_breaker_active():
        logger.warning("CIRCUIT BREAKER ACTIVO: Ciclo de apertura omitido por seguridad.")
        return
        
    # 3. Verificación de límite de posiciones concurrentes
    open_count = get_open_positions_count()
    if open_count >= MAX_CONCURRENT_POSITIONS:
        logger.info(f"Límite de posiciones alcanzado ({open_count}/{MAX_CONCURRENT_POSITIONS} activas). No se abrirán nuevas órdenes.")
        return
        
    slots_available = MAX_CONCURRENT_POSITIONS - open_count
    logger.info(f"Slots disponibles para nuevas posiciones: {slots_available}")

    # 4. Escaneo de los 18 pares de la lista
    for symbol in WATCHLIST_SYMBOLS:
        if slots_available <= 0:
            break
            
        # Verificar si ya existe posición en este par
        if check_open_position_for_symbol(symbol):
            logger.info(f"Activo {symbol}: Ya tiene una posición abierta activa. Omitiendo.")
            continue
            
        try:
            # Sección 3: Filtro Macro 4H
            macro_trend = check_macro_trend_4h(symbol)
            if macro_trend == "NEUTRAL":
                continue
                
            # Análisis en 15m (Alineado con Macro)
            signal_15m = analyze_entry_signal_15m(symbol, macro_trend)
            if not signal_15m:
                continue
                
            side = signal_15m["side"]
            current_price = signal_15m["price"]
            
            # Sección 4: Gestión Dinámica de Posición
            pos_data = calculate_dynamic_position_size(symbol, current_price, side)
            if not pos_data:
                continue
                
            # Generar ID de orden único
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            order_id = f"DIP-{now_utc.strftime('%m%d')}-{int(time.time()) % 10000:04d}"
            
            # Registrar posición abierta en Supabase
            if supabase_client:
                insert_payload = {
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "entry_price": round(pos_data["entry_price"], 4),
                    "exit_price": None,
                    "sl": round(pos_data["sl_price"], 4),
                    "tp": round(pos_data["tp_price"], 4),
                    "target_position_usd": round(pos_data["target_position_usd"], 2),
                    "volume_crypto": pos_data["volume_crypto"],
                    "status": "OPEN",
                    "pnl_usd": 0.0,
                    "pnl_pct": 0.0,
                    "timestamp": now_utc.isoformat(),
                    "reason": f"Macro 4H {macro_trend} + 15m Signal Score {signal_15m['score']}"
                }
                try:
                    supabase_client.table("paper_trades").insert(insert_payload).execute()
                    logger.info(f"NUEVA POSICIÓN REGISTRADA EN SUPABASE: {order_id} | {symbol} [{side}]")
                except Exception as e_ins:
                    logger.error(f"Error insertando orden en Supabase: {e_ins}")
                    
            # Enviar Alerta Push por Apertura vía Ntfy
            alert_title = f"🚀 NUEVA POSICIÓN: {symbol} [{side}]"
            alert_msg = (
                f"📊 Par: {symbol}\n"
                f"📈 Tipo: {side}\n"
                f"💵 Entrada: ${pos_data['entry_price']:,.4f}\n"
                f"🎯 TP (+3.0%): ${pos_data['tp_price']:,.4f}\n"
                f"🛑 SL (-1.5%): ${pos_data['sl_price']:,.4f}\n"
                f"💰 Asignación: ${pos_data['target_position_usd']:,.2f} USD\n"
                f"📦 Volumen: {pos_data['volume_crypto']} unid.\n"
                f"⚡ ID Orden: {order_id}"
            )
            send_ntfy_alert(alert_msg, alert_title, priority="high")
            
            slots_available -= 1
            
        except ccxt.InsufficientFunds as ife:
            logger.error(f"Fondos insuficientes en Kraken operando {symbol}: {ife}")
        except ccxt.NetworkError as ne:
            logger.error(f"Excepción de red en escaneo de {symbol}: {ne}")
        except ccxt.ExchangeError as ee:
            logger.error(f"Excepción de exchange en {symbol}: {ee}")
        except Exception as e:
            logger.error(f"Error general procesando {symbol}: {e}")

# ======================================================================================
# SECCIÓN 7: SERVIDOR HTTP AUXILIAR PARA HEALTH CHECK (PORT BINDING EN RENDER)
# ======================================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    """
    Manejador HTTP ligero para responder al health check de Render (Status 200 OK en /).
    Evita timeouts por falta de Port Binding sin interferir con el bucle de trading.
    """
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"PROYECTO DIPPER: Bot de Trading Algoritmico Online - 200 OK\n")

    def log_message(self, format, *args):
        # Suprimir logs ruidosos de polling de health check para mantener limpio el log principal
        return

def start_health_check_server():
    """
    Inicia el servidor HTTP en un hilo daemon secundario (background thread)
    usando el puerto especificado en la variable de entorno PORT (o 10000 por defecto).
    """
    port_str = os.getenv("PORT", "10000").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 10000

    def run_server():
        try:
            server_address = ("0.0.0.0", port)
            httpd = HTTPServer(server_address, HealthCheckHandler)
            logger.info(f"🌐 Servidor HTTP de Health Check activo en 0.0.0.0:{port} (Port Binding Render OK)")
            httpd.serve_forever()
        except Exception as e:
            logger.error(f"Error iniciando servidor HTTP en puerto {port}: {e}")

    server_thread = threading.Thread(target=run_server, daemon=True, name="RenderHealthCheckServer")
    server_thread.start()


def run_execution_engine():
    """
    Bucle principal de ejecución 24/7 (Execution Engine para Render).
    Itera indefinidamente en intervalos de 15 minutos (900s),
    capturando todas las excepciones de red y de API sin detener el proceso.
    """
    logger.info("==================================================================")
    logger.info("PROYECTO DIPPER: EXECUTION ENGINE 24/7 INICIADO")
    logger.info(f"Intervalo de Ciclo: {CYCLE_SLEEP_SECONDS} segundos (15m)")
    logger.info("==================================================================")
    
    # Iniciar servidor HTTP en segundo plano para cumplir con el port binding de Render
    start_health_check_server()

    # Enviar alerta de encendido del motor
    send_ntfy_alert(
        message="🟢 El Execution Engine 24/7 de Proyecto Dipper ha iniciado operaciones en la nube con Port Binding activo.",
        title="PROYECTO DIPPER | BOT ONLINE",
        priority="default"
    )

    while True:
        try:
            execute_trading_cycle()
        except ccxt.NetworkError as ne:
            logger.error(f"CCXT NetworkError en ciclo principal (reintentando en próximo ciclo): {ne}")
        except ccxt.ExchangeError as ee:
            logger.error(f"CCXT ExchangeError en ciclo principal: {ee}")
        except ccxt.InsufficientFunds as ife:
            logger.error(f"CCXT InsufficientFunds en ciclo principal: {ife}")
        except Exception as e:
            logger.critical(f"Excepción general no capturada en bucle principal: {e}", exc_info=True)
            
        logger.info(f"Ciclo finalizado. En reposo durante {CYCLE_SLEEP_SECONDS} segundos hasta la próxima vela...")
        time.sleep(CYCLE_SLEEP_SECONDS)

# ======================================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ======================================================================================
if __name__ == "__main__":
    try:
        run_execution_engine()
    except KeyboardInterrupt:
        logger.info("Ejecución detenida manualmente por el operador.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Falla fatal en punto de entrada: {e}")
        sys.exit(1)
