import { directionPath, firebaseConfig, selectedTimingPath, timingsPath } from './firebaseConfig.js'

export const COMMANDS = Object.freeze({ STOP: 0, FORWARD: 1, BACKWARD: 2 })

const url = path => `${firebaseConfig.databaseURL}/${path}.json`
let pendingWrite = Promise.resolve()

async function request(method, value, path = directionPath) {
  const controller = new AbortController()
  const timer = globalThis.setTimeout(() => controller.abort(), 7000)
  try {
    const response = await fetch(url(path), {
      method,
      ...(value !== undefined ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) } : {}),
      cache: 'no-store',
      signal: controller.signal,
    })
    if (!response.ok) {
      let detail = ''
      try { detail = (await response.json()).error || '' } catch { /* Firebase may return an empty error body. */ }
      throw new Error(`Firebase rejected the command (${response.status})${detail ? `: ${detail}` : ''}. Check database rules.`)
    }
    return response.json()
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Firebase timed out. Check your connection.', { cause: error })
    if (error instanceof TypeError) throw new Error('Cannot reach Firebase. Check your connection and browser access.', { cause: error })
    throw error
  } finally {
    globalThis.clearTimeout(timer)
  }
}

export async function readDirection() {
  const value = await request('GET')
  return [0, 1, 2].includes(value) ? value : null
}

export function sendDirection(value) {
  if (![0, 1, 2].includes(value)) return Promise.reject(new Error('Invalid direction command'))
  const write = pendingWrite.catch(() => {}).then(() => request('PUT', value))
  pendingWrite = write
  return write.then(() => value)
}

export const DEFAULT_TIMING = Object.freeze({ name: 'Default', feedSeconds: 2, settleSeconds: 1, goodSeconds: 4, defectSeconds: 4, twoSideFeedSeconds: 3, turnSeconds: 8 })
export const TIMING_FIELDS = Object.freeze(['feedSeconds', 'settleSeconds', 'goodSeconds', 'defectSeconds', 'twoSideFeedSeconds', 'turnSeconds'])

export function validateTiming(timing) {
  const name = String(timing.name || '').trim()
  if (!name) throw new Error('Enter a name for the timing')
  const clean = { name: name.slice(0, 60) }
  for (const field of TIMING_FIELDS) {
    const value = Number(timing[field] ?? DEFAULT_TIMING[field])
    const min = field === 'settleSeconds' ? 0 : 0.1
    if (!Number.isFinite(value) || value < min || value > 60) throw new Error(`Each time must be between ${min} and 60 seconds`)
    clean[field] = Math.round(value * 10) / 10
  }
  return clean
}

export async function listTimings() {
  const data = await request('GET', undefined, timingsPath) || {}
  return Object.entries(data).map(([id, timing]) => ({ ...DEFAULT_TIMING, ...timing, id })).sort((a, b) => a.name.localeCompare(b.name))
}

export async function createTiming(timing) {
  const { name: id } = await request('POST', { ...validateTiming(timing), updatedAt: Date.now() }, timingsPath)
  return id
}

export function updateTiming(id, timing) {
  return request('PUT', { ...validateTiming(timing), updatedAt: Date.now() }, `${timingsPath}/${id}`)
}

export async function deleteTiming(id) {
  await request('DELETE', undefined, `${timingsPath}/${id}`)
  if (await readSelectedTiming() === id) await selectTiming(null)
}

export async function readSelectedTiming() {
  const id = await request('GET', undefined, selectedTimingPath)
  return typeof id === 'string' ? id : null
}

export function selectTiming(id) {
  return id ? request('PUT', id, selectedTimingPath) : request('DELETE', undefined, selectedTimingPath)
}

export const timingSummary = timing => `Feed ${timing.feedSeconds}s · Settle ${timing.settleSeconds}s · Two sides: feed ${timing.twoSideFeedSeconds ?? 3}s, turn ${timing.turnSeconds ?? 8}s · Good ${timing.goodSeconds}s forward · Defect ${timing.defectSeconds}s backward`

// The timing chosen for the conveyor cycle, or the built-in default when none is chosen.
export async function loadActiveTiming() {
  const [timings, selectedId] = await Promise.all([listTimings(), readSelectedTiming()])
  return timings.find(timing => timing.id === selectedId) || DEFAULT_TIMING
}
