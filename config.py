# config.py
import os

# Clave API de Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6LtLaz0rbECuSZsuiEorU2ipcGRWZgyqs_dj_QrEVhYcA")

# Configuración de Supabase
SUPABASE_URL = "https://iazvlueqgvlqbjyygcbh.supabase.co"
SUPABASE_KEY = "sb_publishable_gcXzhrpMdaNmIezv4l6gUw_wmT1i46s"

# Parámetros de Trading
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT"
]
TIMEFRAME = "1h"
INITIAL_BALANCE = 1000.0   # Saldo simulado USDT
RISK_PER_TRADE_PCT = 1.0  # 1% de riesgo por operación
REWARD_RATIO = 2.0        # Ratio Riesgo:Beneficio 1:2

# Indicadores
EMA_PERIOD = 200
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
VOLUME_MULTIPLIER = 1.15  # 115% de la media móvil de volumen