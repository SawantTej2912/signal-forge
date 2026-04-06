import { useCallback, useEffect, useState } from 'react'
import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { fetchCandles } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function CandleTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  const sigColor = d.signal === 'BUY' ? '#22c55e' : d.signal === 'SELL' ? '#ef4444' : '#888'
  return (
    <div className="rounded-md border bg-background/90 backdrop-blur px-3 py-2 text-xs shadow-md">
      <p className="font-semibold mb-1">{d.date}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-muted-foreground">
        <span>O</span><span className="text-foreground">{d.open}</span>
        <span>H</span><span className="text-foreground">{d.high}</span>
        <span>L</span><span className="text-foreground">{d.low}</span>
        <span>C</span><span className="text-foreground">{d.close}</span>
      </div>
      <p className="mt-1 font-bold" style={{ color: sigColor }}>{d.signal}</p>
    </div>
  )
}

export default function CandlestickChart({ ticker }) {
  const [candles, setCandles] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    fetchCandles(ticker, '90d')
      .then(setCandles)
      .catch(() => setCandles([]))
      .finally(() => setLoading(false))
  }, [ticker])

  const yMin = candles.length ? Math.min(...candles.map(c => c.low))  * 0.995 : 0
  const yMax = candles.length ? Math.max(...candles.map(c => c.high)) * 1.005 : 1

  // Bar custom shape — captures yMin/yMax from closure for pixel mapping
  const CandleShape = useCallback((props) => {
    const { x, width, background, open, high, low, close, signal } = props
    if (!background || background.height <= 0) return null

    const { y: bgY, height: bgH } = background
    const range = yMax - yMin
    const toY = (val) => bgY + bgH * (1 - (val - yMin) / range)

    const cx    = x + width / 2
    const yH    = toY(high)
    const yL    = toY(low)
    const yO    = toY(open)
    const yC    = toY(close)

    const isBullish = close >= open
    const color     = isBullish ? '#22c55e' : '#ef4444'
    const bodyTop   = Math.min(yO, yC)
    const bodyH     = Math.max(Math.abs(yC - yO), 1)
    const bodyW     = Math.max(width * 0.6, 3)

    return (
      <g>
        {/* Wick */}
        <line x1={cx} x2={cx} y1={yH} y2={yL} stroke={color} strokeWidth={1} />
        {/* Body */}
        <rect
          x={cx - bodyW / 2} y={bodyTop}
          width={bodyW} height={bodyH}
          fill={color} stroke={color}
        />
        {/* Signal markers */}
        {signal === 'BUY'  && <text x={cx} y={yL + 12} textAnchor="middle" fontSize={9} fill="#22c55e">▲</text>}
        {signal === 'SELL' && <text x={cx} y={yH - 5}  textAnchor="middle" fontSize={9} fill="#ef4444">▼</text>}
      </g>
    )
  }, [yMin, yMax])

  const tickEvery = Math.ceil(candles.length / 8)
  const xTicks = candles
    .filter((_, i) => i % tickEvery === 0)
    .map(c => c.date)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{ticker} — Price (90d)</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground py-12 text-center">Loading…</p>
        ) : candles.length === 0 ? (
          <p className="text-sm text-muted-foreground py-12 text-center">No price data</p>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart
              data={candles}
              margin={{ top: 8, right: 8, bottom: 0, left: -10 }}
            >
              <XAxis
                dataKey="date"
                ticks={xTicks}
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={d => d.slice(5)}
              />
              <YAxis
                domain={[yMin, yMax]}
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => v.toFixed(0)}
                width={45}
              />
              <Tooltip content={<CandleTooltip />} />
              <Bar
                dataKey="close"
                shape={CandleShape}
                isAnimationActive={false}
                fill="transparent"
                stroke="none"
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}

        {candles.length > 0 && (
          <div className="flex gap-4 mt-2 text-xs text-muted-foreground justify-end">
            <span className="text-green-500">▲ BUY</span>
            <span className="text-red-500">▼ SELL</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
