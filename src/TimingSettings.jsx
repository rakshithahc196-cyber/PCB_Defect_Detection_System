import { useCallback, useEffect, useState } from 'react'
import { createTiming, DEFAULT_TIMING, deleteTiming, listTimings, readSelectedTiming, selectTiming, timingSummary, updateTiming, validateTiming } from './firebaseControl.js'

const fields = [
  { key: 'feedSeconds', label: 'Feed forward', hint: 'Bring the PCB under the camera' },
  { key: 'settleSeconds', label: 'Settle', hint: 'Wait after stopping, before capture' },
  { key: 'goodSeconds', label: 'Good: forward', hint: 'Send a good PCB on' },
  { key: 'defectSeconds', label: 'Defect: backward', hint: 'Return a defective PCB' },
  { key: 'twoSideFeedSeconds', label: 'Two sides: feed forward', hint: 'Same time for initial forward, return backward and forward before back capture (default 3s)' },
  { key: 'turnSeconds', label: 'Two sides: turn PCB', hint: 'Time to flip the board before back capture (default 8s)' },
]
const emptyForm = { ...DEFAULT_TIMING, name: '' }

export default function TimingSettings({ activeTiming, onActiveChange, locked = false }) {
  const [timings, setTimings] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [editingId, setEditingId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [items, selectedId] = await Promise.all([listTimings(), readSelectedTiming()])
      setTimings(items)
      onActiveChange(items.find(timing => timing.id === selectedId) || DEFAULT_TIMING)
      setError('')
    } catch (caught) { setError(caught.message) }
    finally { setLoading(false) }
  }, [onActiveChange])
  useEffect(() => { const timer = window.setTimeout(refresh, 0); return () => window.clearTimeout(timer) }, [refresh])

  const run = async (action, message) => {
    setSaving(true); setError(''); setNotice('')
    try { await action(); await refresh(); setNotice(message) }
    catch (caught) { setError(caught.message) }
    finally { setSaving(false) }
  }
  const save = event => {
    event.preventDefault()
    let timing
    try { timing = validateTiming(form) } catch (caught) { setError(caught.message); return }
    run(async () => {
      if (editingId) await updateTiming(editingId, timing)
      else await createTiming(timing)
      setForm(emptyForm); setEditingId(null)
    }, editingId ? `Updated “${timing.name}”` : `Saved “${timing.name}”`)
  }
  const edit = timing => { setEditingId(timing.id); setForm(timing); setError(''); setNotice('') }
  const cancelEdit = () => { setEditingId(null); setForm(emptyForm) }
  const remove = timing => {
    if (!window.confirm(`Delete the timing “${timing.name}”?`)) return
    run(async () => { await deleteTiming(timing.id); if (editingId === timing.id) cancelEdit() }, `Deleted “${timing.name}”`)
  }
  const use = timing => run(() => selectTiming(timing.id || null), `Conveyor now uses “${timing.name}”`)
  const disabled = saving || locked

  const row = (timing, builtIn = false) => {
    const active = builtIn ? !activeTiming.id : activeTiming.id === timing.id
    return <div key={timing.id || 'default'} className={`timing-row ${active ? 'active' : ''}`}>
      <div><strong>{timing.name}{builtIn && <small> · built in</small>}</strong><span>{timingSummary(timing)}</span></div>
      <div className="timing-actions">
        {active ? <span className="timing-badge">In use</span> : <button className="secondary-button" onClick={() => use(timing)} disabled={disabled}>Use</button>}
        {!builtIn && <button className="text-button" onClick={() => edit(timing)} disabled={disabled}>Edit</button>}
        {!builtIn && <button className="text-button danger" onClick={() => remove(timing)} disabled={disabled}>Delete</button>}
      </div>
    </div>
  }

  return <section className="panel control-panel timing-panel">
    <div className="control-header"><div><span className="overline">CONVEYOR TIMINGS</span><h3>Cycle timings</h3><p>Saved in Firebase. Choose which timing the next cycle uses.</p></div>{locked && <span className="control-status online"><i/>Cycle running</span>}</div>
    <div className="timing-list">
      {row(DEFAULT_TIMING, true)}
      {loading ? <p className="timing-empty">Loading saved timings…</p> : timings.map(timing => row(timing))}
      {!loading && !timings.length && <p className="timing-empty">No saved timings yet. Add one below.</p>}
    </div>
    <form className="timing-form" onSubmit={save}>
      <strong>{editingId ? `Edit “${timings.find(timing => timing.id === editingId)?.name || form.name}”` : 'Add a timing'}</strong>
      <label className="timing-name">Name<input value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} placeholder="e.g. Slow belt" maxLength={60} disabled={disabled}/></label>
      <div className="timing-fields">{fields.map(field => <label key={field.key}>{field.label}<span><input type="number" min={field.key === 'settleSeconds' ? 0 : 0.1} max={60} step={0.1} value={form[field.key]} onChange={event => setForm({ ...form, [field.key]: event.target.value })} disabled={disabled}/>s</span><small>{field.hint}</small></label>)}</div>
      <div className="timing-form-actions">
        {editingId && <button type="button" className="secondary-button" onClick={cancelEdit} disabled={saving}>Cancel</button>}
        <button type="submit" className="primary-button" disabled={disabled}>{saving ? 'Saving…' : editingId ? 'Update timing' : 'Save timing'}</button>
      </div>
    </form>
    {notice && <p role="status" className="timing-notice">{notice}</p>}
    {error && <div className="control-error" role="alert">{error}</div>}
  </section>
}
