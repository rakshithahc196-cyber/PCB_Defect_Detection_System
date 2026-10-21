import { useCallback, useEffect, useState } from 'react'
import { readDirection, timingSummary } from './firebaseControl.js'

const labels = { 0: 'STOP', 1: 'FORWARD', 2: 'BACKWARD' }

export default function ControlPanel({ scanId, onStart, onStop, canStart, phase, timing, scanning = false, twoSides = false }) {
  const [direction, setDirection] = useState(null)
  const [error, setError] = useState('')
  const [stopping, setStopping] = useState(false)
  const refresh = useCallback(async () => {
    try { setDirection(await readDirection()); setError('') }
    catch (caught) { setError(caught.message) }
  }, [])
  useEffect(() => {
    const initial = window.setTimeout(refresh, 0)
    const timer = window.setInterval(refresh, 1000)
    return () => { window.clearTimeout(initial); window.clearInterval(timer) }
  }, [refresh, scanId])
  const stop = async () => {
    setStopping(true)
    try { await onStop(); setDirection(0) }
    catch (caught) { setError(caught.message) }
    finally { setStopping(false) }
  }
  return <section className="panel control-panel">
    <div className="control-header"><div><span className="overline">CONVEYOR CONTROL</span><h3>PCB inspection cycle</h3><p>Start once for each board.</p></div><span className={`control-status ${error ? 'fault' : 'online'}`}><i/>{error ? 'Connection error' : scanning ? 'Cycle running' : 'Ready'}</span></div>
    <div className="control-current"><span>Current command</span><strong className={`direction-value direction-${direction ?? 'unknown'}`}>{direction === null ? 'Checking' : labels[direction]}</strong></div>
    <div className="direction-buttons">
      <button className="direction-button stop" disabled={stopping} onClick={stop}><strong>{stopping ? 'Stopping…' : 'Stop conveyor'}</strong><small>Cancel cycle and stop</small></button>
      <button className="direction-button forward" disabled={scanning || stopping || !canStart} onClick={onStart}><strong>{twoSides ? 'Start two-side conveyor' : 'Start conveyor'}</strong><small>{twoSides ? 'Feed, capture front, turn and capture back' : 'Feed, inspect and sort PCB'}</small></button>
    </div>
    {!canStart && !scanning && <p>Connect a camera in Live inspection and load best.pt to start.</p>}
    {phase && <p role="status">{phase}</p>}
    {error && <div className="control-error" role="alert">{error}</div>}
    <div className="control-logic"><strong>Timing in use: {timing.name}</strong><span>{timingSummary(timing)}</span><small>No PCB or an uncertain result stays stopped. Stop cancels any pending movement.</small></div>
  </section>
}
