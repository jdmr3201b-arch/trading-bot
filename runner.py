import time
from engine import AutoTradingEngine
import config

# Lista de seguimiento multi-activo (10 pares con mayor liquidez)
WATCHLIST = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "NEAR/USDT", "SUI/USDT"
]

def main():
    engine = AutoTradingEngine()
    print("🤖 Bot Autónomo Multi-Activo Iniciado...")
    print(f"Monitoreando {len(WATCHLIST)} pares en segundo plano con estrategia blindada.")

    while True:
        for symbol in WATCHLIST:
            try:
                engine.run_cycle_for_symbol(symbol)
            except Exception as e:
                print(f"Error procesando {symbol}: {e}")
            
            # Pausa breve entre llamadas para respetar límites de la API de Binance
            time.sleep(1)

        # Espera de 15 segundos antes de la siguiente vuelta completa
        time.sleep(15)

if __name__ == "__main__":
    main()