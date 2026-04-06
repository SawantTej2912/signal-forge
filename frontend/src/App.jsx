import { useState } from 'react'
import HealthStatus from './components/HealthStatus'
import Watchlist from './components/Watchlist'
import SignalDetail from './components/SignalDetail'
import CandlestickChart from './components/CandlestickChart'
import BacktestPanel from './components/BacktestPanel'

export default function App() {
  const [selectedTicker, setSelectedTicker] = useState('TSLA')

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="border-b px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold tracking-tight">SignalForge</h1>
          <p className="text-xs text-muted-foreground">Real-time NLP trade signals</p>
        </div>
        <HealthStatus />
      </header>

      {/* Main layout */}
      <div className="flex gap-4 p-4 max-w-6xl mx-auto">

        {/* Left sidebar — watchlist */}
        <aside className="w-56 shrink-0">
          <Watchlist onSelect={setSelectedTicker} selectedTicker={selectedTicker} />
        </aside>

        {/* Right panel */}
        <main className="flex-1 flex flex-col gap-4">
          <SignalDetail ticker={selectedTicker} />
          <CandlestickChart ticker={selectedTicker} />
          <BacktestPanel ticker={selectedTicker} />
        </main>

      </div>
    </div>
  )
}
