import { useEffect, useState } from 'react'
import { fetchBacktest } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Slider } from '@/components/ui/slider'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

export default function BacktestPanel({ ticker }) {
  const [lag, setLag] = useState(3)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    fetchBacktest(ticker, lag, '90d')
      .then(setData)
      .finally(() => setLoading(false))
  }, [ticker, lag])

  if (!ticker) return null

  const curve = data?.equity_curve ?? []
  const returnPct = data?.total_return_pct ?? 0
  const returnColor = returnPct >= 0 ? '#22c55e' : '#ef4444'

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{ticker} — Backtest (90d)</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">

        {/* Lag slider */}
        <div>
          <div className="flex justify-between text-xs text-muted-foreground mb-2">
            <span>Signal lag</span>
            <span className="font-semibold text-foreground">{lag} day{lag !== 1 ? 's' : ''}</span>
          </div>
          <Slider
            min={1} max={14} step={1}
            value={[lag]}
            onValueChange={([v]) => setLag(v)}
          />
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>1d</span><span>14d</span>
          </div>
        </div>

        {/* Equity curve */}
        {loading ? (
          <p className="text-sm text-muted-foreground py-8 text-center">Loading…</p>
        ) : curve.length > 0 ? (
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={curve} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={returnColor} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={returnColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false}
                tickFormatter={d => d.slice(5)} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false}
                tickFormatter={v => v.toFixed(2)} />
              <Tooltip
                formatter={(v) => [v.toFixed(4), 'Equity']}
                labelFormatter={l => `Date: ${l}`}
                contentStyle={{ fontSize: 11 }}
              />
              <ReferenceLine y={1} stroke="#555" strokeDasharray="3 3" />
              <Area type="monotone" dataKey="equity" stroke={returnColor}
                fill="url(#equityGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-muted-foreground py-8 text-center">No backtest data</p>
        )}

        {/* Metric cards */}
        {data && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="Total Return" value={`${returnPct > 0 ? '+' : ''}${returnPct.toFixed(2)}%`}
              color={returnColor} />
            <Metric label="Sharpe" value={data.sharpe_ratio.toFixed(2)} />
            <Metric label="Max Drawdown" value={`${data.max_drawdown_pct.toFixed(2)}%`}
              color={data.max_drawdown_pct < 0 ? '#ef4444' : undefined} />
            <Metric label="Win Rate" value={`${data.win_rate_pct.toFixed(1)}%`} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function Metric({ label, value, color }) {
  return (
    <div className="rounded-md bg-muted/50 px-3 py-2 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-bold mt-0.5" style={color ? { color } : {}}>
        {value}
      </p>
    </div>
  )
}
