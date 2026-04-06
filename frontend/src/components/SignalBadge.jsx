import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const COLORS = {
  BUY:  'bg-green-500/15 text-green-400 border-green-500/30',
  SELL: 'bg-red-500/15 text-red-400 border-red-500/30',
  HOLD: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
}

export default function SignalBadge({ signal, large = false }) {
  if (!signal) return null
  return (
    <Badge
      variant="outline"
      className={cn(
        'font-bold tracking-widest border',
        COLORS[signal] ?? COLORS.HOLD,
        large ? 'text-2xl px-6 py-2' : 'text-xs px-2 py-0.5',
      )}
    >
      {signal}
    </Badge>
  )
}
