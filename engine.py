import os
import time
import json
import re
import pandas as pd
import ccxt
from google import genai
import config

# Inicialización del cliente oficial de Gemini
api_key = getattr(config, 'GEMINI_API_KEY', '') or os.getenv("GEMINI_API_KEY", "")
client = genai.Client(api_key=api_key) if api_key else None

class AutoTradingEngine:
    def __init__(self, initial_balance=getattr(config, 'INITIAL_BALANCE', 1000.0)):
        self.balance = initial_balance
        self.equity = initial_balance
        self.positions = []      # Posiciones activas
        self.trade_history = []  # Historial cerrado
        self.logs = []           # Bitácora
        
        self.exchange = ccxt.kraken({
            'apiKey': getattr(config, 'EXCHANGE_API_KEY', ''),
            'secret': getattr(config, 'EXCHANGE_SECRET', ''),
            'enableRateLimit': True,
        })

    def log(self, message: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self.logs.append(entry)
        print(entry)

    def fetch_market_data(self, symbol: str) -> pd.DataFrame:
        """Descarga velas OHLCV y calcula EMA, RSI y Promedio de Volumen."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, config.TIMEFRAME, limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 1. EMA 200
            df['EMA_200'] = df['close'].ewm(span=config.EMA_PERIOD, adjust=False).mean()
            
            # 2. RSI (14)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # 3. Promedio de Volumen (últimas 20 velas)
            df['vol_sma'] = df['volume'].rolling(window=20).mean()
            
            return df
        except Exception as e:
            self.log(f"Error descargando datos para {symbol}: {str(e)}")
            return pd.DataFrame()

    def evaluate_technical_setup(self, df: pd.DataFrame) -> dict:
        """Filtro Técnico Triple: EMA 200 + RSI + Volumen Institucional."""
        if df.empty or len(df) < 20:
            return {"signal": "NEUTRAL"}
            
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Validación de Volumen (> 15% sobre la media)
        vol_confirmed = latest['volume'] > (latest['vol_sma'] * 1.15)
        
        signal = "NEUTRAL"
        # COMPRA: Cruce EMA 200 hacia arriba + RSI > 50 + Volumen
        if latest['close'] > latest['EMA_200'] and prev['close'] <= prev['EMA_200']:
            if latest['RSI'] > 50 and vol_confirmed:
                signal = "BUY"
                
        # VENTA: Cruce EMA 200 hacia abajo + RSI < 50 + Volumen
        elif latest['close'] < latest['EMA_200'] and prev['close'] >= prev['EMA_200']:
            if latest['RSI'] < 50 and vol_confirmed:
                signal = "SELL"
                
        return {
            "signal": signal,
            "close_price": latest['close'],
            "ema_200": latest['EMA_200'],
            "rsi": round(latest['RSI'], 2),
            "volume_ok": vol_confirmed
        }

    def consult_ai_filter(self, symbol: str, setup: dict, df_summary: str) -> dict:
        """Filtro Antimanipulación con Gemini 2.5 Flash."""
        if not client:
            return {"approve": False, "confidence_score": 0, "reasoning": "API Key no configurada."}

        prompt = f"""
Eres un gestor de riesgo institucional. Se ha detectado la siguiente señal técnica:

- Activo: {symbol}
- Dirección: {setup['signal']}
- Precio: {setup['close_price']:.2f} | EMA 200: {setup['ema_200']:.2f}
- RSI: {setup['rsi']} | Confirmación de Volumen: {setup['volume_ok']}

Contexto reciente del mercado:
{df_summary}

Evalúa si la estructura actual muestra un impulso limpio o si hay riesgo de manipulación (falsos rompimientos/mechas de absorción).
Responde ÚNICAMENTE en JSON estricto:
{{\"approve\": true, \"confidence_score\": 85, \"reasoning\": \"Breve análisis de máximo 2 oraciones.\"}}
"""
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {"approve": False, "confidence_score": 0, "reasoning": "Formato de respuesta inválido"}
        except Exception as e:
            self.log(f"Error en consulta Gemini: {str(e)}")
            return {"approve": False, "confidence_score": 0, "reasoning": "Error de comunicación API"}

    def execute_automatic_order(self, symbol: str, signal_type: str, price: float, reasoning: str):
        """Ejecuta orden en Paper Trading con Gestión 1:2."""
        # Evitar abrir posiciones duplicadas para el mismo activo
        if any(p['symbol'] == symbol for p in self.positions):
            self.log(f"Posición para {symbol} ya se encuentra abierta. Se omite duplicado.")
            return

        risk_amount = self.balance * (config.RISK_PER_TRADE_PCT / 100.0)
        stop_distance = price * 0.015  # 1.5% Stop Loss
        
        stop_loss = price - stop_distance if signal_type == "BUY" else price + stop_distance
        take_profit = price + (stop_distance * config.REWARD_RATIO) if signal_type == "BUY" else price - (stop_distance * config.REWARD_RATIO)
        position_size = risk_amount / stop_distance

        trade = {
            "id": len(self.positions) + len(self.trade_history) + 1,
            "symbol": symbol,
            "type": signal_type,
            "entry_price": price,
            "size": round(position_size, 4),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "status": "EXECUTED_AUTO",
            "reasoning": reasoning,
            "time": time.strftime("%H:%M:%S")
        }
        
        self.positions.append(trade)
        self.log(f"⚡ ORDEN EJECUTADA [{symbol} - {signal_type}] | Entrada: {price:.2f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f}")

    def run_cycle_for_symbol(self, symbol: str):
        """Ciclo completo de análisis por cada par."""
        df = self.fetch_market_data(symbol)
        if df.empty:
            return

        setup = self.evaluate_technical_setup(df)
        
        if setup['signal'] in ["BUY", "SELL"]:
            self.log(f"🎯 [{symbol}] Filtro Técnico Superado ({setup['signal']}). Consultando a la IA...")
            summary_str = df[['close', 'EMA_200', 'RSI', 'volume']].tail(5).to_string()
            
            ai_eval = self.consult_ai_filter(symbol, setup, summary_str)
            
            if ai_eval.get('approve') and ai_eval.get('confidence_score', 0) >= 75:
                self.log(f"✅ IA Aprobó orden en {symbol} ({ai_eval['confidence_score']}% confianza): {ai_eval['reasoning']}")
                self.execute_automatic_order(symbol, setup['signal'], setup['close_price'], ai_eval['reasoning'])
            else:
                self.log(f"❌ IA Rechazó orden en {symbol}: {ai_eval.get('reasoning')}")
