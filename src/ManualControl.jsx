import { useCallback, useEffect, useState } from 'react'
import { COMMANDS, readDirection, sendDirection } from './firebaseControl.js'

const labels = { 0: 'STOP', 1: 'FORWARD', 2: 'BACKWARD' }
const buttons = [
  { value: COMMANDS.FORWARD, className: 'forward', icon: '▶', title: 'Forward', hint: 'Run the belt forward until stopped' },
  { value: COMMANDS.STOP, className: 'stop', icon: '■', title: 'Stop', hint: 'Stop the belt now' },
  { value: COMMANDS.BACKWARD, className: 'backward', icon: '◀', title: 'Backward', hint: 'Run the belt backward until stopped' },
]

// Direct belt commands. Moving is blocked while an inspection cycle runs; Stop always works and cancels the cycle.
export default function ManualControl({ cycleRunning, onStopCycle }) {
  const [direction, setDirection] = useState(null)
  const [sending, setSending] = useState(null)
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    try { setDirection(await readDirection()); setError('') }
    catch (caught) { setError(caught.message) }
  }, [])
  useEffect(() => {
    const initial = window.setTimeout(refresh, 0)
    const timer = window.setInterval(refresh, 1000)
    return () => { window.clearTimeout(initial); window.clearInterval(timer) }
  }, [refresh])
  const send = async value => {
    setSending(value); setError('')
    try {
      if (value === COMMANDS.STOP) await onStopCycle()
      else await sendDirection(value)
      setDirection(value)
    } catch (caught) { setError(caught.message) }
    finally { setSending(null) }
  }
  return <section className="panel control-panel">
    <div className="control-header"><div><span className="overline">MANUAL CONTROL</span><h3>Drive the conveyor</h3><p>Each command stays active until you press another one.</p></div><span className={`control-status ${error ? 'fault' : 'online'}`}><i/>{error ? 'Connection error' : cycleRunning ? 'Cycle running' : 'Ready'}</span></div>
    <div className="control-current"><span>Current command</span><strong className={`direction-value direction-${direction ?? 'unknown'}`}>{direction === null ? 'Checking' : labels[direction]}</strong></div>
    <div className="direction-buttons">
      {buttons.map(button => <button key={button.value} className={`direction-button ${button.className} ${direction === button.value ? 'selected' : ''}`} disabled={sending !== null || (cycleRunning && button.value !== COMMANDS.STOP)} onClick={() => send(button.value)}>
        <span className="direction-icon" aria-hidden="true">{button.icon}</span><strong>{sending === button.value ? 'Sending…' : button.title}</strong><small>{button.hint}</small>
      </button>)}
    </div>
    {cycleRunning && <p role="status">An inspection cycle is running. Press Stop to cancel it before moving the belt by hand.</p>}
    {error && <div className="control-error" role="alert">{error}</div>}
    <div className="control-logic"><strong>Firebase command</strong><span>Writes 1 (forward), 0 (stop) or 2 (backward) to ks5791/Direction.</span><small>The belt keeps moving until Stop is pressed. Leaving this page does not stop it.</small></div>
  </section>
}
