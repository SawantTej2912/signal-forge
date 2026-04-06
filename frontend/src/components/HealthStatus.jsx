import { useEffect, useState } from 'react'
import { fetchHealth } from '@/api'

export default function HealthStatus() {
  const [status, setStatus] = useState('checking')

  useEffect(() => {
    fetchHealth()
      .then(() => setStatus('ok'))
      .catch(() => setStatus('down'))

    const id = setInterval(() => {
      fetchHealth()
        .then(() => setStatus('ok'))
        .catch(() => setStatus('down'))
    }, 30000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="flex items-center gap-2 text-sm">
      <span
        className={`h-2 w-2 rounded-full ${
          status === 'ok' ? 'bg-green-500' : status === 'down' ? 'bg-red-500' : 'bg-yellow-400'
        }`}
      />
      <span className="text-muted-foreground">
        API {status === 'ok' ? 'online' : status === 'down' ? 'offline' : 'checking…'}
      </span>
    </div>
  )
}
