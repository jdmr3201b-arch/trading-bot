import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { MetricsHeader } from './components/MetricsHeader';
import { ConfluenceCard } from './components/ConfluenceCard';
import { CandlestickChart } from './components/CandlestickChart';
import { RiskSidebar } from './components/RiskSidebar';
import { BacktestEngine } from './components/BacktestEngine';
import { AuditLogTable } from './components/AuditLogTable';
import { StreamlitCodeModal } from './components/StreamlitCodeModal';
import { STREAMLIT_APP_CODE } from './streamlitCode';
import { MarketPair, Timeframe, Candle, RiskConfig, AuditTrade } from './types';
import { fetchLiveCandles } from './utils/marketData';
import { RefreshCw, PlayCircle, ExternalLink } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'live' | 'backtest' | 'audit' | 'code'>('live');
  const [pair, setPair] = useState<MarketPair>('BTC/USDT');
  const [timeframe, setTimeframe] = useState<Timeframe>('15m');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [dataSource, setDataSource] = useState<string>('KRAKEN REST API');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [utcTime, setUtcTime] = useState<string>('');
  const [macroBlocked, setMacroBlocked] = useState<boolean>(false);

  // Risk configuration state
  const [risk, setRisk] = useState<RiskConfig>({
    capital: 1000,
    riskPct: 1.0,
    maxDailyDrawdown: 3.0,
    tpPct: 3.0,
    slPct: 1.5,
    leverage: 1.0,
  });

  // Audit trades ledger
  const [trades, setTrades] = useState<AuditTrade[]>([
    {
      id: '#DIP-8941',
      timestamp: '2026-10-05 05:48:12',
      pair: 'BTC/USDT',
      side: 'LONG',
      entryPrice: 93420.0,
      exitPrice: 96222.6,
      stopLoss: 92018.7,
      takeProfit: 96222.6,
      status: 'CLOSED_TP',
      pnlUsd: 30.0,
      pnlPct: 3.0,
      confluenceScore: 90,
      notes: 'EMA 200 Golden Breakout + Low ATR Compression',
    },
    {
      id: '#DIP-8938',
      timestamp: '2026-10-05 00:32:45',
      pair: 'ETH/USDT',
      side: 'LONG',
      entryPrice: 3410.5,
      exitPrice: 3359.34,
      stopLoss: 3359.34,
      takeProfit: 3512.8,
      status: 'CLOSED_SL',
      pnlUsd: -15.0,
      pnlPct: -1.5,
      confluenceScore: 75,
      notes: 'EMA 200 Retest wick stop out',
    },
    {
      id: '#DIP-8932',
      timestamp: '2026-10-04 17:15:20',
      pair: 'SOL/USDT',
      side: 'LONG',
      entryPrice: 184.2,
      exitPrice: 189.72,
      stopLoss: 181.43,
      takeProfit: 189.72,
      status: 'CLOSED_TP',
      pnlUsd: 30.0,
      pnlPct: 3.0,
      confluenceScore: 85,
      notes: 'Momentum reversal over 200 EMA with volume spike',
    },
    {
      id: '#DIP-8929',
      timestamp: '2026-10-04 06:10:00',
      pair: 'BTC/USDT',
      side: 'LONG',
      entryPrice: 91150.0,
      exitPrice: 93884.5,
      stopLoss: 89782.75,
      takeProfit: 93884.5,
      status: 'CLOSED_TP',
      pnlUsd: 30.0,
      pnlPct: 3.0,
      confluenceScore: 80,
      notes: 'Trend continuation confirmation',
    },
  ]);

  // Live UTC Clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(now.toISOString().slice(11, 19));
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch market candles
  const loadMarketData = useCallback(async () => {
    setIsLoading(true);
    const { candles: loadedCandles, source } = await fetchLiveCandles(pair, timeframe, 120);
    setCandles(loadedCandles);
    setDataSource(source);
    setIsLoading(false);
  }, [pair, timeframe]);

  useEffect(() => {
    loadMarketData();
  }, [loadMarketData]);

  // Periodic polling every 35s
  useEffect(() => {
    const interval = setInterval(() => {
      loadMarketData();
    }, 35000);
    return () => clearInterval(interval);
  }, [loadMarketData]);

  // Current price and EMA values
  const lastCandle = candles[candles.length - 1];
  const currentPrice = lastCandle ? lastCandle.close : 94200;
  const ema200 = lastCandle?.ema200 || currentPrice * 0.985;
  const atr14 = lastCandle?.atr || currentPrice * 0.012;

  // Calculate algorithmic confluence score
  let score = 50;
  if (currentPrice > ema200) {
    score += 25;
  } else {
    score -= 25;
  }
  // Short term momentum from 10 candles ago
  if (candles.length > 10) {
    const prevClose = candles[candles.length - 10].close;
    if (currentPrice > prevClose) score += 15;
    else score -= 15;
  }
  score = Math.max(10, Math.min(95, score));

  // Simulated order placement
  const handleExecuteSimulatedTrade = (side: 'LONG' | 'SHORT') => {
    const newId = `#DIP-${Math.floor(1000 + Math.random() * 9000)}`;
    const nowStr = new Date().toISOString().slice(0, 19).replace('T', ' ');
    const tpPrice = currentPrice * (1 + risk.tpPct / 100);
    const slPrice = currentPrice * (1 - risk.slPct / 100);

    const newTrade: AuditTrade = {
      id: newId,
      timestamp: nowStr,
      pair,
      side,
      entryPrice: currentPrice,
      exitPrice: currentPrice,
      stopLoss: slPrice,
      takeProfit: tpPrice,
      status: 'ACTIVE',
      pnlUsd: 0.0,
      pnlPct: 0.0,
      confluenceScore: score,
      notes: `Ejecución manual de prueba en señal cuantitativa (${score}%)`,
    };

    setTrades((prev) => [newTrade, ...prev]);
  };

  const activeRiskUsd = risk.capital * (risk.riskPct / 100);
  const macroMessage = macroBlocked
    ? "🛑 PAUSA PREVENTIVA: 'US Core CPI / FOMC' en ventana crítica (28 min)."
    : '🟢 FILTRO MACRO OK: Sin eventos de alto impacto en la ventana actual (±30m).';

  return (
    <div className="min-h-screen bg-[#070A13] text-[#E2E8F0] flex flex-col">
      {/* Institutional Top Bar */}
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        utcTime={utcTime}
        sourceStatus={dataSource}
        macroPaused={macroBlocked}
        onOpenCode={() => setActiveTab('code')}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-[1560px] w-full mx-auto px-4 lg:px-8 py-5">
        {/* Top Quantitative KPIs */}
        <MetricsHeader
          macroActive={macroBlocked}
          macroMessage={macroMessage}
          maxDrawdown={risk.maxDailyDrawdown}
          capital={risk.capital}
          pnlDaily={2.14}
          activeRiskUsd={activeRiskUsd}
        />

        {/* Tab 1: Live Monitor & Execution */}
        {activeTab === 'live' && (
          <div className="flex flex-col lg:flex-row gap-5">
            {/* Left/Main Column: Chart & Signals */}
            <div className="flex-1 flex flex-col gap-5">
              {/* Asset & Timeframe Selector Bar */}
              <div className="bg-[#0F172A] border border-[#1E293B] rounded-xl px-4 py-3 flex flex-wrap items-center justify-between gap-3 shadow-md">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">
                    Activo:
                  </span>
                  <div className="flex items-center gap-1.5 bg-[#070A13] p-1 rounded-lg border border-[#1E293B]">
                    {(['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT'] as MarketPair[]).map((p) => (
                      <button
                        key={p}
                        onClick={() => setPair(p)}
                        className={`px-3 py-1 text-xs font-mono font-bold rounded transition-all ${
                          pair === p
                            ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">
                    Temporalidad:
                  </span>
                  <div className="flex items-center gap-1 bg-[#070A13] p-1 rounded-lg border border-[#1E293B]">
                    {(['15m', '1h', '4h'] as Timeframe[]).map((tf) => (
                      <button
                        key={tf}
                        onClick={() => setTimeframe(tf)}
                        className={`px-2.5 py-1 text-xs font-mono font-medium rounded transition-all ${
                          timeframe === tf
                            ? 'bg-[#1E293B] text-cyan-300 border border-cyan-500/30 font-bold'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {tf}
                      </button>
                    ))}
                  </div>

                  <button
                    onClick={loadMarketData}
                    disabled={isLoading}
                    title="Actualizar datos de mercado"
                    className="p-1.5 rounded-lg bg-[#070A13] border border-[#1E293B] hover:border-slate-600 text-slate-300 transition-colors"
                  >
                    <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
                  </button>
                </div>
              </div>

              {/* Confluence Card */}
              <ConfluenceCard
                pair={pair}
                score={score}
                currentPrice={currentPrice}
                ema200={ema200}
                atr14={atr14}
                tpPct={risk.tpPct}
                slPct={risk.slPct}
                macroBlocked={macroBlocked}
                onExecuteSimulatedTrade={handleExecuteSimulatedTrade}
              />

              {/* Candlestick & Volume Chart */}
              <CandlestickChart
                candles={candles}
                pair={pair}
                timeframe={timeframe}
                tpPrice={currentPrice * (1 + risk.tpPct / 100)}
                slPrice={currentPrice * (1 - risk.slPct / 100)}
                currentPrice={currentPrice}
              />

              {/* Mini Trade Log (Below Chart on Live Tab as requested) */}
              <AuditLogTable trades={trades} />
            </div>

            {/* Right Column: Risk Management Matrix */}
            <div className="shrink-0">
              <RiskSidebar
                risk={risk}
                onRiskChange={setRisk}
                macroBlocked={macroBlocked}
                onToggleMacroBlocked={() => setMacroBlocked((prev) => !prev)}
                currentPrice={currentPrice}
              />
            </div>
          </div>
        )}

        {/* Tab 2: Historical Backtesting */}
        {activeTab === 'backtest' && <BacktestEngine risk={risk} />}

        {/* Tab 3: Order History & Audit Log */}
        {activeTab === 'audit' && <AuditLogTable trades={trades} />}

        {/* Tab 4: Streamlit Python Code Viewer */}
        {activeTab === 'code' && <StreamlitCodeModal code={STREAMLIT_APP_CODE} />}
      </main>

      {/* Institutional Terminal Footer */}
      <footer className="border-t border-[#1E293B] bg-[#070A13] px-4 lg:px-8 py-3 mt-8">
        <div className="max-w-[1560px] mx-auto flex flex-col sm:flex-row items-center justify-between text-xs font-mono text-slate-500 gap-2">
          <div className="flex items-center gap-3">
            <span>PROYECTO DIPPER · QUANT TRADING TERMINAL</span>
            <span>·</span>
            <span className="text-slate-400">INSTITUTIONAL GRADE UI/UX</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-cyan-400">KRAKEN SPOT REST FEED</span>
            <span>·</span>
            <span>MACRO SHIELD ACTIVE</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
