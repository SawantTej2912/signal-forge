import { useEffect, useState } from 'react'
import { fetchAllSignals } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import SignalBadge from './SignalBadge'

export default function Watchlist({ onSelect, selectedTicker }) {
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    fetchAllSignals()
      .then(setSignals)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Watchlist</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <p className="px-4 py-3 text-sm text-muted-foreground">Loading…</p>
        ) : (
          <ul>
            {signals.map(s => (
              <li
                key={s.ticker}
                onClick={() => onSelect(s.ticker)}
                className={`flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-accent transition-colors ${
                  selectedTicker === s.ticker ? 'bg-accent' : ''
                }`}
              >
                <div>
                  <span className="font-semibold text-sm">{s.ticker}</span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {s.sentiment_score > 0 ? '+' : ''}{s.sentiment_score.toFixed(3)}
                  </span>
                </div>
                <SignalBadge signal={s.signal} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
