import axios from 'axios'

const api = axios.create({ baseURL: 'http://localhost:8000' })

export const fetchHealth = () => api.get('/health').then(r => r.data)
export const fetchSignal = (ticker, windowHours = 24) =>
  api.get('/signal', { params: { ticker, window_hours: windowHours } }).then(r => r.data)
export const fetchAllSignals = (windowHours = 24) =>
  api.get('/signals/all', { params: { window_hours: windowHours } }).then(r => r.data)
export const fetchBacktest = (ticker, lag, period = '90d') =>
  api.get('/backtest', { params: { ticker, lag, period } }).then(r => r.data)
