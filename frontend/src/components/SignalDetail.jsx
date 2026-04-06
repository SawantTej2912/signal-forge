import { useEffect, useState } from 'react'
import { fetchSignal } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import SignalBadge from './SignalBadge'

export default function SignalDetail({ ticker }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!ticker) return
    setData(null)
    fetchSignal(ticker).then(setData)

    const id = setInterval(() => fetchSignal(ticker).then(setData), 60000)
    return () => clearInterval(id)
  }, [ticker])

  if (!ticker) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{ticker} — Current Signal</CardTitle>
      </CardHeader>
      <CardContent>
        {!data ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="flex flex-col gap-3">
            <SignalBadge signal={data.signal} large />
            <div className="grid grid-cols-3 gap-4 text-center mt-2">
              <Stat label="Score" value={data.sentiment_score.toFixed(4)} />
              <Stat label="Samples" value={data.sample_size} />
              <Stat label="Window" value={`${data.window_hours}h`} />
            </div>
            <p className="text-xs text-muted-foreground text-right">
              {new Date(data.generated_at).toLocaleTimeString()}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  )
}
