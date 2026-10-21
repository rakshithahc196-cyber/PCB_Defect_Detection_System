import { useCallback, useEffect, useRef, useState } from 'react'
import ControlPanel from './ControlPanel.jsx'
import ManualControl from './ManualControl.jsx'
import { createConveyorCycle } from './conveyorCycle.js'
import { captureTwoSides } from './twoSideCapture.js'
import { DEFAULT_TIMING, loadActiveTiming, sendDirection } from './firebaseControl.js'
import { captureStillFrame } from './stillFrame.js'
import TimingSettings from './TimingSettings.jsx'
import { classifyScan, isGoodBoardLabel } from './scanOutcome.js'
import './App.css'

const glyphs = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  camera: <><path d="M14 4h-4L8 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-4l-2-3Z"/><circle cx="12" cy="13" r="3"/></>,
  layers: <><path d="m12 2 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 17l9 5 9-5"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  activity: <path d="M2 12h4l3-7 5 14 3-7h5"/>,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
  plus: <path d="M12 5v14M5 12h14"/>,
  upload: <path d="M12 16V3m-5 5 5-5 5 5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>,
  play: <path d="m8 5 11 7-11 7V5Z"/>,
  stop: <rect x="5" y="5" width="14" height="14" rx="2"/>,
  scan: <path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m13-5v3a2 2 0 0 1-2 2h-3M3 12h18"/>,
  check: <path d="m5 12 4 4L19 6"/>,
  alert: <path d="M12 3 2 21h20L12 3ZM12 9v5m0 3h.01"/>,
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6m4-6v6"/>,
  edit: <path d="M12 20h9M4 17.5V21h3.5L19 9.5 14.5 5 4 15.5v2zM13 6.5l4.5 4.5"/>,
  download: <path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>,
  refresh: <path d="M20 11a8 8 0 0 0-14-5L3 9m0-5v5h5M4 13a8 8 0 0 0 14 5l3-3m0 5v-5h-5"/>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  close: <path d="M5 5l14 14M19 5 5 19"/>,
  sliders: <path d="M4 6h10m4 0h2M4 12h4m4 0h8M4 18h12m4 0h0M16 4v4M10 10v4M18 16v4"/>,
  image: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1"/><path d="m3 17 5-5 4 4 3-3 6 6"/></>,
}

function Icon({ name, size = 19 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{glyphs[name]}</svg>
}

async function api(path, options) {
  let response
  try { response = await fetch(`/api${path}`, options) }
  catch { throw new Error('API offline. Start the Python server on port 8000.') }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || 'Request failed')
  return data
}

const dateLabel = value => value ? new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
const unresolvedLabel = scan => scan.region_source === 'none' ? (scan.localization_warning || 'No green PCB in the frame') : scan.pcb_detected === true ? 'PCB found, no confident result' : scan.pcb_detected === false ? 'No confident detections' : 'No PCB confirmed'

function BoardArt() {
  return <svg className="board-art" viewBox="0 0 430 255" fill="none" aria-hidden="true"><defs><pattern id="dots" width="19" height="19" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#6ec99b" opacity=".28"/></pattern><linearGradient id="board" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#174e42"/><stop offset="1" stopColor="#0b302d"/></linearGradient></defs><rect x="20" y="14" width="390" height="225" rx="16" fill="url(#board)" stroke="#449d78" strokeWidth="2"/><rect x="20" y="14" width="390" height="225" rx="16" fill="url(#dots)"/><g stroke="#3fa87b" strokeWidth="2" opacity=".8"><path d="M61 48h90l25 25h58M62 76h65l22 22h52M43 134h92l26-26h51M52 204h98l26-26h53M256 69h48l24-24h54M265 112h54l24 24h52M260 167h45l31 31h54M66 170h47l19-19h78"/></g><g fill="#75d6a2"><circle cx="61" cy="48" r="4"/><circle cx="62" cy="76" r="4"/><circle cx="43" cy="134" r="4"/><circle cx="52" cy="204" r="4"/><circle cx="382" cy="45" r="4"/><circle cx="395" cy="136" r="4"/><circle cx="390" cy="198" r="4"/></g><rect x="198" y="63" width="82" height="112" rx="7" fill="#102827" stroke="#83cfa7" strokeWidth="2"/><rect x="209" y="75" width="60" height="88" rx="3" fill="#173d35" stroke="#316f57"/><path d="M221 103h36m-36 8h25m-25 8h31" stroke="#9be5b4" opacity=".65" strokeWidth="2"/><g fill="#d3bb70"><rect x="190" y="72" width="8" height="8"/><rect x="190" y="91" width="8" height="8"/><rect x="190" y="110" width="8" height="8"/><rect x="190" y="129" width="8" height="8"/><rect x="190" y="148" width="8" height="8"/><rect x="280" y="72" width="8" height="8"/><rect x="280" y="91" width="8" height="8"/><rect x="280" y="110" width="8" height="8"/><rect x="280" y="129" width="8" height="8"/><rect x="280" y="148" width="8" height="8"/></g><rect x="78" y="112" width="49" height="31" rx="3" fill="#0c2b2a" stroke="#66ad88"/><rect x="316" y="77" width="43" height="24" rx="3" fill="#0c2b2a" stroke="#66ad88"/><rect x="309" y="160" width="45" height="27" rx="3" fill="#0c2b2a" stroke="#66ad88"/><rect x="169" y="49" width="132" height="145" rx="13" stroke="#e1b25e" strokeWidth="2" strokeDasharray="7 5"/></svg>
}

const navigation = [{ id: 'overview', label: 'Overview', icon: 'grid' }, { id: 'inspect', label: 'Live inspection', icon: 'scan' }, { id: 'control', label: 'Conveyor control', icon: 'activity' }, { id: 'manual', label: 'Manual control', icon: 'sliders' }, { id: 'training', label: 'Training studio', icon: 'layers' }, { id: 'history', label: 'Scan history', icon: 'clock' }]

function SampleExpansion({ item, onSave, onError }) {
  const [target, setTarget] = useState(String(Math.max(item.training_count, item.count)))
  const [saving, setSaving] = useState(false)
  const desired = Number(target)
  const valid = Number.isInteger(desired) && desired >= item.count && desired <= 500

  if (item.count < 5) {
    return <div className="expansion-hint">Collect {5 - item.count} more original image{5 - item.count === 1 ? '' : 's'} to enable sample expansion.</div>
  }

  const submit = async event => {
    event.preventDefault()
    if (!valid) return
    setSaving(true)
    try { await onSave(item.id, desired) }
    catch (err) { onError(err.message) }
    finally { setSaving(false) }
  }

  return <form className="expansion-card" onSubmit={submit}>
    <div className="expansion-heading"><strong>Expand collected samples</strong><span>{item.count} originals</span></div>
    <p>Set the total image count for this defect. Variations are created from the training originals when you train.</p>
    <div className="expansion-controls"><label htmlFor="expansion-target">Target count</label><input id="expansion-target" type="number" min={item.count} max="500" step="1" value={target} onChange={event => setTarget(event.target.value)}/><button className="secondary-button" type="submit" disabled={!valid || saving}>{saving ? 'Saving…' : 'Set count'}</button></div>
    <small>{valid ? `${item.count} original + ${desired - item.count} generated = ${desired} total images` : `Enter a whole number from ${item.count} to 500.`} Validation images stay original.</small>
  </form>
}

function PcbAreaPicker({ src, area, onChange }) {
  const frameRef = useRef(null)
  const imageRef = useRef(null)
  const startRef = useRef(null)
  const [size, setSize] = useState({ width: 0, height: 0, naturalWidth: 0, naturalHeight: 0 })
  const measure = useCallback(() => {
    const frame = frameRef.current
    const image = imageRef.current
    if (frame) setSize({ width: frame.clientWidth, height: frame.clientHeight, naturalWidth: image?.naturalWidth || 0, naturalHeight: image?.naturalHeight || 0 })
  }, [])
  useEffect(() => {
    const observer = new ResizeObserver(measure)
    if (frameRef.current) observer.observe(frameRef.current)
    measure()
    return () => observer.disconnect()
  }, [measure])
  const scale = size.naturalWidth && size.naturalHeight
    ? Math.min(size.width / size.naturalWidth, size.height / size.naturalHeight) : 0
  const pixels = {
    width: size.naturalWidth * scale || 0,
    height: size.naturalHeight * scale || 0,
  }
  pixels.left = (size.width - pixels.width) / 2
  pixels.top = (size.height - pixels.height) / 2
  const point = event => {
    const rect = frameRef.current.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left - pixels.left) / pixels.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top - pixels.top) / pixels.height)),
    }
  }
  const start = event => {
    if (!pixels.width || !pixels.height) return
    event.currentTarget.setPointerCapture(event.pointerId)
    startRef.current = point(event)
    onChange(null)
  }
  const move = event => {
    if (!startRef.current) return
    const end = point(event)
    onChange({ x: Math.min(startRef.current.x, end.x), y: Math.min(startRef.current.y, end.y), w: Math.abs(startRef.current.x - end.x), h: Math.abs(startRef.current.y - end.y) })
  }
  const finish = event => { move(event); startRef.current = null }
  const selection = area && pixels.width ? {
    left: pixels.left + area.x * pixels.width,
    top: pixels.top + area.y * pixels.height,
    width: area.w * pixels.width,
    height: area.h * pixels.height,
  } : null
  return <div ref={frameRef} className="pcb-area-picker" onPointerDown={start} onPointerMove={move} onPointerUp={finish} onPointerCancel={() => { startRef.current = null }}>
    <img ref={imageRef} src={src} alt="Select the PCB area to inspect" draggable="false" onLoad={measure}/>
    {selection && <div className="pcb-area-selection" style={selection}><span>PCB area</span></div>}
  </div>
}

const sideName = { front: 'Front', back: 'Back' }
const outcomeChip = outcome => outcome === 'defect' ? 'defect' : outcome === 'good' ? 'clear' : 'unknown'
const outcomeText = { defect: 'Defects found', good: 'Good PCB', unknown: 'Not confirmed' }

function ScanImage({ scan }) {
  const detections = scan.detections || scan.findings
  return <div className="result-image-wrap"><img src={scan.image_url} alt={`${sideName[scan.side] || 'PCB'} side scan`}/>{detections.map((finding, index) => <div key={index} className={`detection-box ${isGoodBoardLabel(finding.name) ? 'good' : ''}`} style={{ left: `${finding.box.x * 100}%`, top: `${finding.box.y * 100}%`, width: `${finding.box.w * 100}%`, height: `${finding.box.h * 100}%` }}><span>{finding.name} · {(finding.confidence * 100).toFixed(0)}%</span></div>)}</div>
}

function SideShots({ shots, cameraOn, busy, modelReady, onCapture, onUpload, onClear, onAnalyze }) {
  return <div className="side-shots">{['front', 'back'].map(side => <div key={side} className={`side-shot ${shots[side] ? 'filled' : ''}`}><div className="side-shot-preview">{shots[side] ? <img src={shots[side].preview} alt={`${sideName[side]} side`}/> : <Icon name="image" size={24}/>}</div><div className="side-shot-body"><strong>{sideName[side]} side</strong><small>{shots[side] ? 'Ready to analyze' : 'Not added yet'}</small><div><button className="secondary-button" onClick={() => onCapture(side)} disabled={busy || !cameraOn}><Icon name="camera" size={15}/> Capture</button><label className={`secondary-button ${busy ? 'is-disabled' : ''}`}><Icon name="upload" size={15}/> Upload<input type="file" accept="image/*" hidden disabled={busy} onChange={event => { onUpload(side, event.target.files?.[0]); event.target.value = '' }}/></label></div></div></div>)}<div className="side-shot-actions"><button className="text-button" onClick={onClear} disabled={busy || (!shots.front && !shots.back)}>Clear</button><button className="primary-button" onClick={onAnalyze} disabled={busy || !modelReady || !shots.front || !shots.back}><Icon name="scan" size={17}/>{busy ? 'Analyzing…' : 'Analyze both sides'}</button></div></div>
}

function PairFindings({ pair }) {
  if (!pair) return <div className="analysis-empty"><div><Icon name="target" size={34}/></div><strong>Two-side inspection</strong><p>Add a front and a back image, then analyze both sides to compare them.</p></div>
  const { overall, sides, rows } = pair.comparison
  const total = sides.front.defect_count + sides.back.defect_count
  return <><div className={`analysis-banner ${outcomeChip(overall)}`}><span><Icon name={overall === 'good' ? 'check' : 'alert'} size={22}/></span><div><strong>{overall === 'defect' ? 'Defects found on this board' : overall === 'good' ? 'Both sides are good' : 'Board not confirmed'}</strong><small>{total} defect{total === 1 ? '' : 's'} across both sides</small></div></div>{['front', 'back'].map(side => <div key={side} className="analysis-meta"><span>{sideName[side]} side</span><strong>{sides[side].defect_count ? `${sides[side].defect_count} defect${sides[side].defect_count === 1 ? '' : 's'}` : outcomeText[sides[side].outcome]}</strong></div>)}<div className="analysis-meta"><span>Scanned at</span><strong>{dateLabel(pair.created_at)}</strong></div><div className="findings-list">{rows.map((row, index) => <div key={row.name} className="finding-row"><span className="finding-number">{String(index + 1).padStart(2, '0')}</span><div><strong>{row.name}</strong><small>{row.where === 'both' ? 'Front and back' : `${sideName[row.where]} only`}</small></div><span className="confidence">{(Math.max(row.front?.confidence ?? 0, row.back?.confidence ?? 0) * 100).toFixed(1)}%</span></div>)}</div></>
}

function PairComparison({ pair }) {
  const { rows, differences } = pair.comparison
  const cell = entry => entry ? `${entry.count} found · ${(entry.confidence * 100).toFixed(1)}%` : '—'
  return <section className="panel pair-panel"><div className="section-title"><div><span className="overline">TWO-SIDE COMPARISON</span><h3>Front vs back</h3></div><span className="samples-pill"><Icon name="clock" size={16}/>{dateLabel(pair.created_at)}</span></div><div className="pair-images">{['front', 'back'].map(side => <figure key={side}><figcaption><strong>{sideName[side]} side</strong><span className={`result-chip ${outcomeChip(pair.comparison.sides[side].outcome)}`}>{outcomeText[pair.comparison.sides[side].outcome]}</span></figcaption><div className="pair-image-stage"><ScanImage scan={pair[side]}/></div></figure>)}</div><div className="pair-columns"><div><h4>Differences</h4><ul className="pair-differences">{differences.map(text => <li key={text}>{text}</li>)}</ul></div><div><h4>What to change</h4>{rows.length ? <ol className="pair-fixes">{rows.map(row => <li key={row.name}><strong>{row.name}</strong> <em>({row.where === 'both' ? 'both sides' : `${row.where} side`})</em><span>{row.fix}</span></li>)}</ol> : <p className="pair-none">Nothing to change. Both sides passed.</p>}</div></div>{rows.length > 0 && <div className="pair-table-wrap"><table className="pair-table"><thead><tr><th>Defect type</th><th>Front</th><th>Back</th><th>Found on</th></tr></thead><tbody>{rows.map(row => <tr key={row.name}><td>{row.name}</td><td>{cell(row.front)}</td><td>{cell(row.back)}</td><td>{row.where === 'both' ? 'Both sides' : `${sideName[row.where]} only`}</td></tr>)}</tbody></table></div>}</section>
}

function App() {
  const [page, setPage] = useState('overview')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [health, setHealth] = useState(null)
  const [classes, setClasses] = useState([])
  const [samples, setSamples] = useState([])
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cameraDevices, setCameraDevices] = useState([])
  const [deviceId, setDeviceId] = useState(() => { try { return localStorage.getItem('pcb.cameraId') || '' } catch { return '' } })
  const [cameraOn, setCameraOn] = useState(false)
  const [ipCamera, setIpCamera] = useState(null)
  const [ipAddress, setIpAddress] = useState(() => { try { return localStorage.getItem('pcb.ipCameraAddress') || '' } catch { return '' } })
  const [showIpForm, setShowIpForm] = useState(false)
  const [ipConnecting, setIpConnecting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [cycle] = useState(() => createConveyorCycle(sendDirection))
  const [cyclePhase, setCyclePhase] = useState('')
  const [timing, setTiming] = useState(DEFAULT_TIMING)
  const timingRef = useRef(DEFAULT_TIMING)
  const changeTiming = useCallback(next => { timingRef.current = next; setTiming(next) }, [])
  useEffect(() => { loadActiveTiming().then(changeTiming).catch(err => setError(`Conveyor timings unavailable, using defaults: ${err.message}`)) }, [changeTiming])
  const stopConveyor = async () => {
    try { await cycle.stop(); setCyclePhase('Conveyor stopped') }
    catch (err) { setError(err.message); throw err }
  }
  const [lastScan, setLastScan] = useState(null)
  const [pendingScan, setPendingScan] = useState(null)
  const [inspectionArea, setInspectionArea] = useState(null)
  const [cameraArea, setCameraArea] = useState(null)
  const [sideMode, setSideMode] = useState(() => { try { return localStorage.getItem('pcb.sideMode') === 'two' ? 'two' : 'one' } catch { return 'one' } })
  const [turnRemaining, setTurnRemaining] = useState(null)
  const [sideShots, setSideShots] = useState({ front: null, back: null })
  const [lastPair, setLastPair] = useState(null)
  const [pairs, setPairs] = useState([])
  const [newClass, setNewClass] = useState('')
  const [selectedClass, setSelectedClass] = useState('')
  const [sampleFile, setSampleFile] = useState(null)
  const [editingSample, setEditingSample] = useState(null)
  const [samplePreview, setSamplePreview] = useState('')
  const [box, setBox] = useState(null)
  const [savingSample, setSavingSample] = useState(false)
  const [startingTraining, setStartingTraining] = useState(false)
  const [reviewOversized, setReviewOversized] = useState(false)
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const ipCameraRef = useRef(null)
  const imageRef = useRef(null)
  const dragRef = useRef(null)
  const scanBusyRef = useRef(false)
  const sampleInputRef = useRef(null)
  const inspectInputRef = useRef(null)
  const manualInspectInputRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const [status, dataset, scans] = await Promise.all([api('/health'), api('/classes'), api('/history')])
      setHealth(status); setClasses(dataset.classes); setSamples(dataset.samples); setHistory(scans.items.map(classifyScan)); setPairs(scans.pairs || []); setError(previous => previous.startsWith('API offline') ? '' : previous)
    } catch (err) { setHealth(null); setError(err.message) }
  }, [])
  useEffect(() => { const initial = window.setTimeout(refresh, 0); const timer = window.setInterval(refresh, 4000); return () => { window.clearTimeout(initial); window.clearInterval(timer) } }, [refresh])
  useEffect(() => () => { streamRef.current?.getTracks().forEach(track => track.stop()) }, [])
  const loadCameras = useCallback(async (askPermission = false) => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    try {
      // Browsers hide camera names until camera access is allowed once, so a refresh can ask for it.
      if (askPermission) (await navigator.mediaDevices.getUserMedia({ audio: false, video: true })).getTracks().forEach(track => track.stop())
      setCameraDevices((await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput'))
    } catch (err) { setError(`Camera unavailable: ${err.message}`) }
  }, [])
  useEffect(() => {
    const initial = window.setTimeout(loadCameras, 0)
    const onChange = () => loadCameras()
    navigator.mediaDevices?.addEventListener?.('devicechange', onChange)
    return () => { window.clearTimeout(initial); navigator.mediaDevices?.removeEventListener?.('devicechange', onChange) }
  }, [loadCameras])
  useEffect(() => () => { if (samplePreview?.startsWith('blob:')) URL.revokeObjectURL(samplePreview) }, [samplePreview])
  useEffect(() => () => { if (pendingScan?.preview) URL.revokeObjectURL(pendingScan.preview) }, [pendingScan])
  useEffect(() => { if (videoRef.current && streamRef.current) videoRef.current.srcObject = streamRef.current }, [page, cameraOn, lastScan, pendingScan])

  const go = id => { setPage(id); setSidebarOpen(false); setError(''); setNotice('') }
  const releaseIpCamera = () => {
    if (!ipCameraRef.current) return
    ipCameraRef.current = null; setIpCamera(null)
    api('/ipcam/disconnect', { method: 'POST' }).catch(() => {})
  }
  const connectIpCamera = async event => {
    event.preventDefault()
    const address = ipAddress.trim()
    if (!address) return
    setError(''); setIpConnecting(true)
    try {
      const status = await api('/ipcam/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ address }) })
      streamRef.current?.getTracks().forEach(track => track.stop()); streamRef.current = null
      setCameraArea(null); setPendingScan(null); setInspectionArea(null); setLastScan(null)
      const camera = { ...status, connectedAt: Date.now() }
      ipCameraRef.current = camera; setIpCamera(camera); setCameraOn(true); setShowIpForm(false)
      setNotice(`IP camera connected · ${status.source}`)
      try { localStorage.setItem('pcb.ipCameraAddress', address) } catch { /* remembering the address is optional */ }
    } catch (err) { setError(`IP camera unavailable: ${err.message}`) }
    finally { setIpConnecting(false) }
  }
  const startCamera = async (requestedId = deviceId) => {
    setError('')
    try {
      setCameraArea(null); setPendingScan(null); setInspectionArea(null)
      releaseIpCamera()
      streamRef.current?.getTracks().forEach(track => track.stop())
      const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: requestedId ? { deviceId: { exact: requestedId }, width: { ideal: 1280 }, height: { ideal: 720 } } : { width: { ideal: 1280 }, height: { ideal: 720 } } })
      streamRef.current = stream; setCameraOn(true)
      if (videoRef.current) videoRef.current.srcObject = stream
      const devices = await navigator.mediaDevices.enumerateDevices()
      setCameraDevices(devices.filter(device => device.kind === 'videoinput'))
      const startedId = stream.getVideoTracks()[0]?.getSettings().deviceId || ''
      setDeviceId(startedId)
      try { localStorage.setItem('pcb.cameraId', startedId) } catch { /* remembering the camera is optional */ }
    } catch (err) {
      // A remembered camera may have been unplugged; fall back to the default one.
      if (requestedId && ['OverconstrainedError', 'NotFoundError'].includes(err.name)) return startCamera('')
      setCameraOn(false); setError(`Camera unavailable: ${err.message}`)
    }
  }
  const chooseCamera = id => {
    setDeviceId(id)
    try { localStorage.setItem('pcb.cameraId', id) } catch { /* remembering the camera is optional */ }
    if (cameraOn && !ipCamera) startCamera(id)
  }
  const namedCameras = cameraDevices.filter(device => device.deviceId)
  const stopCamera = () => { stopConveyor().catch(() => {}); releaseIpCamera(); streamRef.current?.getTracks().forEach(track => track.stop()); streamRef.current = null; setCameraOn(false); setCameraArea(null); setPendingScan(null); setInspectionArea(null) }
  const capture = async () => {
    if (ipCameraRef.current) {
      let response
      try { response = await fetch('/api/ipcam/frame', { cache: 'no-store' }) }
      catch { throw new Error('API offline. Start the Python server on port 8000.') }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'IP camera is not sending frames')
      return response.blob()
    }
    let video = videoRef.current
    if (!video?.videoWidth && streamRef.current) {
      video = document.createElement('video')
      video.srcObject = streamRef.current
      video.muted = true
      await video.play()
    }
    if (!video?.videoWidth) throw new Error('Camera is still starting. Try again in a moment.')
    const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Camera capture failed')), 'image/jpeg', .9))
  }
  const runScan = useCallback(async (source, filename = 'pcb-frame.jpg', roi = null, feed = false) => {
    if (scanBusyRef.current) return null
    scanBusyRef.current = true; setBusy(true); setError('')
    try {
      return await cycle.run({ feed, timing: timingRef.current, onPhase: setCyclePhase, inspect: async () => {
        const blob = typeof source === 'function' ? await source() : source
        const form = new FormData(); form.append('file', blob, filename)
        if (roi) form.append('roi', JSON.stringify(roi))
        if (typeof source === 'function') form.append('full_view', 'true')  // live camera frame: the whole board must be in view
        const result = classifyScan(await api('/detect', { method: 'POST', body: form }))
        setLastScan(result); setHistory(items => [result, ...items].slice(0, 100))
        return result
      } })
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
      return null
    } finally { scanBusyRef.current = false; setBusy(false) }
  }, [cycle])
  const startConveyor = async () => {
    if (!cameraOn || !health?.model_ready) { setError('Connect a camera and load best.pt before starting the conveyor.'); return }
    if (sideMode === 'two') { await analyzeSides(true); return }
    setPendingScan(null)
    const captureStill = async () => {
      setCyclePhase('Conveyor stopped: waiting for a still camera frame')
      const { frame, still } = await captureStillFrame(capture, { onWaiting: () => setCyclePhase('PCB still moving: waiting before capture') })
      setCyclePhase(still ? 'PCB still: captured frame, detecting' : 'Camera never fully settled: using the latest frame')
      return frame
    }
    await runScan(captureStill, 'pcb-frame.jpg', cameraArea, true)
  }
  const chooseInspectionImage = (file, source) => {
    if (!file.type.startsWith('image/')) { setError('Choose an image file'); return }
    setPendingScan({ file, source, preview: URL.createObjectURL(file) })
    setInspectionArea(null); setError('')
  }
  const selectCameraArea = async () => {
    try {
      const frame = await capture()
      chooseInspectionImage(new File([frame], 'pcb-frame.jpg', { type: 'image/jpeg' }), 'camera')
    } catch (err) { setError(err.message) }
  }
  const inspectSelectedArea = async () => {
    if (!pendingScan || !inspectionArea || inspectionArea.w < .05 || inspectionArea.h < .05) return
    if (await runScan(pendingScan.file, pendingScan.file.name, inspectionArea)) {
      if (pendingScan.source === 'camera') setCameraArea(inspectionArea)
      setPendingScan(null); setInspectionArea(null)
    }
  }
  const switchSideMode = mode => { setSideMode(mode); setPendingScan(null); setInspectionArea(null); setLastScan(null); setError('') }
  const setSideShot = (side, file) => {
    if (sideShots[side]) URL.revokeObjectURL(sideShots[side].preview)
    const shot = file ? { file, preview: URL.createObjectURL(file) } : null
    setSideShots(shots => ({ ...shots, [side]: shot }))
  }
  const captureSide = async side => { try { setSideShot(side, new File([await capture()], `pcb-${side}.jpg`, { type: 'image/jpeg' })) } catch (err) { setError(err.message) } }
  const uploadSide = (side, file) => { if (!file) return; if (!file.type.startsWith('image/')) { setError('Choose an image file'); return }; setSideShot(side, file) }
  const clearSides = () => { setSideShot('front', null); setSideShot('back', null) }
  const saveDashboardSetup = () => {
    try {
      localStorage.setItem('pcb.sideMode', sideMode)
      setNotice(`Dashboard setup saved: ${sideMode === 'two' ? 'Two sides' : 'One side'}. Save and choose a named timing below to reuse your cycle times.`)
    } catch { setError('Could not save dashboard setup in this browser.') }
  }
  const analyzeSides = async (automatic = false) => {
    if (scanBusyRef.current || (!automatic && (!sideShots.front || !sideShots.back))) return
    if (automatic && (!cameraOn || !health?.model_ready)) { setError('Connect a camera and load best.pt before starting.'); return }
    scanBusyRef.current = true; setBusy(true); setError(''); setLastPair(null)
    const activeTiming = { ...DEFAULT_TIMING, ...timingRef.current }
    if (automatic) clearSides()
    try {
      await cycle.run({ feed: automatic, timing: { ...activeTiming, feedSeconds: activeTiming.twoSideFeedSeconds }, onPhase: setCyclePhase, inspect: async ({ wait, check, move }) => {
        let files = { front: sideShots.front?.file, back: sideShots.back?.file }
        if (automatic) {
          const captures = await captureTwoSides({ capture, wait, check, move, feedSeconds: activeTiming.twoSideFeedSeconds, turnSeconds: activeTiming.turnSeconds,
            onFront: blob => setSideShot('front', new File([blob], 'pcb-front.jpg', { type: 'image/jpeg' })),
            onTurn: setTurnRemaining, onPhase: setCyclePhase })
          files = Object.fromEntries(Object.entries(captures).map(([side, blob]) => [side, new File([blob], `pcb-${side}.jpg`, { type: 'image/jpeg' })]))
          setSideShot('back', files.back)
        }
        check()
        setCyclePhase('Inspecting both sides and saving results')
        const form = new FormData()
        for (const side of ['front', 'back']) form.append(side, files[side], files[side].name)
        const raw = await api('/detect-pair', { method: 'POST', body: form })
        check()
        const pair = { ...raw, front: classifyScan(raw.front), back: classifyScan(raw.back) }
        setLastPair(pair); setHistory(items => [pair.back, pair.front, ...items].slice(0, 100)); setPairs(items => [raw, ...items])
        setNotice('Front and back inspection saved. Open Scan history to review the results or export a PDF.')
        return { outcome: pair.comparison.overall, model_stale: pair.front.model_stale || pair.back.model_stale }
      } })
    } catch (err) { if (err.name !== 'AbortError') setError(err.message) }
    finally { setTurnRemaining(null); scanBusyRef.current = false; setBusy(false) }
  }
  const openScan = item => {
    const pair = item.pair_id && pairs.find(entry => entry.id === item.pair_id)
    const front = pair && history.find(scan => scan.id === pair.front_id)
    const back = pair && history.find(scan => scan.id === pair.back_id)
    if (front && back) { setSideMode('two'); setLastPair({ ...pair, front, back }); setLastScan(null) }
    else { setSideMode('one'); setLastScan(item) }
    go('inspect')
  }

  const chooseSample = file => { if (!file) return; if (!file.type.startsWith('image/')) { setError('Choose an image file'); return }; setEditingSample(null); setSampleFile(file); setSamplePreview(URL.createObjectURL(file)); setBox(null); setError('') }
  const editSample = sample => { setEditingSample(sample); setSelectedClass(sample.class_id); setSampleFile(null); setSamplePreview(sample.image_url); setBox(sample.box); setError(''); document.querySelector('.annotation-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  const cancelSampleEdit = () => { setEditingSample(null); setSampleFile(null); setSamplePreview(''); setBox(null) }
  const sampleFromCamera = async () => { try { chooseSample(new File([await capture()], `pcb-sample-${Date.now()}.jpg`, { type: 'image/jpeg' })); setPage('training') } catch (err) { setError(err.message) } }
  const relativePoint = event => { const rect = imageRef.current.getBoundingClientRect(); return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) } }
  const onBoxStart = event => { if (!imageRef.current || selectedClass === 'normal') return; event.currentTarget.setPointerCapture(event.pointerId); dragRef.current = relativePoint(event); setBox(null) }
  const onBoxMove = event => { if (!dragRef.current) return; const point = relativePoint(event); setBox({ x: Math.min(point.x, dragRef.current.x), y: Math.min(point.y, dragRef.current.y), w: Math.abs(point.x - dragRef.current.x), h: Math.abs(point.y - dragRef.current.y) }) }

  const addClass = async event => { event.preventDefault(); try { const item = await api('/classes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newClass }) }); setSelectedClass(item.id); setNewClass(''); setNotice(`Added ${item.name}. Upload 5 labeled images to train it.`); await refresh() } catch (err) { setError(err.message) } }
  const saveSample = async () => {
    if (!selectedClass || (!sampleFile && !editingSample) || (selectedClass !== 'normal' && (!box || box.w < .005 || box.h < .005))) { setError('Select a class and image, then draw a box for a defect sample.'); return }
    setSavingSample(true)
    try { if (editingSample) { await api(`/samples/${editingSample.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ box }) }) } else { const form = new FormData(); form.append('class_id', selectedClass); form.append('box', JSON.stringify(box)); form.append('file', sampleFile); await api('/samples', { method: 'POST', body: form }) }; cancelSampleEdit(); setNotice(editingSample ? 'Defect box updated. Retrain to use the corrected label.' : 'Labeled sample saved'); await refresh() } catch (err) { setError(err.message) } finally { setSavingSample(false) }
  }
  const removeSample = async id => { try { await api(`/samples/${id}`, { method: 'DELETE' }); await refresh() } catch (err) { setError(err.message) } }
  const saveExpansion = async (classId, targetCount) => { await api(`/classes/${classId}/target`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_count: targetCount }) }); setNotice(`Training dataset target set to ${targetCount} images`); await refresh() }
  const startTraining = async () => { setStartingTraining(true); try { await api('/train', { method: 'POST' }); setNotice('Training started. This can take a while.'); await refresh() } catch (err) { setError(err.message) } finally { setStartingTraining(false) } }
  const inspectUpload = async event => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) { setError('Choose an image file'); return }
    await runScan(file, file.name)
  }
  const inspectManualUpload = event => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) chooseInspectionImage(file, 'upload')
  }

  const totalDetections = history.reduce((sum, item) => sum + item.findings.length, 0)
  const modelReady = !!health?.model_ready
  const allReady = classes.length > 0 && classes.every(item => item.count >= 5)
  const oversizedSamples = samples.filter(sample => {
    const name = classes.find(item => item.id === sample.class_id)?.name
    return name && !isGoodBoardLabel(name) && sample.box?.w * sample.box?.h > .75
  })
  const currentClass = classes.find(item => item.id === selectedClass)
  const pageTitle = navigation.find(item => item.id === page)?.label || 'Overview'

  return <div className="app-shell">
    {turnRemaining !== null && <div className="turn-overlay"><section className="turn-dialog" role="alertdialog" aria-modal="true" aria-labelledby="turn-title" aria-describedby="turn-description" tabIndex={-1} ref={element => element?.focus()}>
      <Icon name="refresh" size={36}/><h2 id="turn-title">Turn your PCB</h2><p id="turn-description">Front side captured. Flip the PCB so the back faces the camera. The conveyor stays stopped.</p><strong role="timer">Forward starts in {Math.ceil(turnRemaining)} seconds</strong><p>After the countdown, the conveyor moves forward, stops and captures the back. Both sides are saved automatically.</p><button className="secondary-button" onClick={() => stopConveyor().catch(() => {})}>Cancel and stop conveyor</button>
    </section></div>}
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}><div className="brand"><div className="brand-mark"><span/><span/><span/><span/></div><div><strong>PCB<span>VISION</span></strong><small>INSPECTION SYSTEM</small></div></div><div className="side-group-label">WORKSPACE</div><nav className="side-nav" aria-label="Main navigation">{navigation.map(item => <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => go(item.id)}><Icon name={item.icon} size={18}/><span>{item.label}</span>{page === item.id && <i/>}</button>)}</nav><div className="sidebar-bottom"><div className="system-card"><div className="system-card-icon"><Icon name="activity" size={18}/></div><div><strong>System status</strong><span>{health ? 'API connected' : 'Waiting for API'}</span></div><i className={health ? 'online' : ''}/></div><div className="sidebar-footer">PCB Vision <span>v1.0</span></div></div></aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle menu"><Icon name={sidebarOpen ? 'close' : 'menu'}/></button><span className="breadcrumb">Workspace <span>/</span> <strong>{pageTitle}</strong></span></div><div className="topbar-right"><span className={`connection-pill ${health ? 'connected' : ''}`}><i/>{health ? 'System online' : 'API offline'}</span><div className="top-avatar">PV</div></div></header><main className="content">
      {error && <div className="message error"><Icon name="alert" size={17}/><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss"><Icon name="close" size={16}/></button></div>}
      {notice && <div className="message success"><Icon name="check" size={17}/><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss"><Icon name="close" size={16}/></button></div>}

      {page === 'overview' && <><div className="page-heading"><div><div className="eyebrow">DASHBOARD OVERVIEW</div><h1>Good to see you.</h1><p>Monitor board quality and keep your inspection workflow moving.</p></div><button className="primary-button" onClick={() => go('inspect')}><Icon name="scan" size={17}/> Start inspection <Icon name="arrow" size={17}/></button></div><div className="hero-panel"><div className="hero-copy"><span className="hero-label"><i/> AI-POWERED QUALITY CONTROL</span><h2>See every detail.<br/><em>Spot hidden defects.</em></h2><p>Inspect PCB images from your camera, train defect classes, and review every scan in one place.</p><button onClick={() => go('inspect')}>{modelReady ? 'Open inspection' : 'Check model'} <Icon name="arrow" size={18}/></button></div><BoardArt/></div><div className="stat-grid"><div className="stat-card"><span className="stat-icon green"><Icon name="scan"/></span><span className="stat-label">Total scans</span><strong>{health?.scan_count ?? '—'}</strong><small>Images inspected</small></div><div className="stat-card"><span className="stat-icon amber"><Icon name="target"/></span><span className="stat-label">Defects found</span><strong>{totalDetections}</strong><small>Saved inspection history</small></div><div className="stat-card"><span className="stat-icon blue"><Icon name="layers"/></span><span className="stat-label">Model classes</span><strong>{health?.model_classes?.length ?? 0}</strong><small>{health?.sample_count ?? 0} labeled samples</small></div><div className="stat-card"><span className="stat-icon violet"><Icon name="activity"/></span><span className="stat-label">Model status</span><strong className="stat-text">{modelReady ? 'Ready' : 'Unavailable'}</strong><small>{health?.metrics?.map50 != null ? `Val mAP@50 ${(health.metrics.map50 * 100).toFixed(1)}%` : 'best.pt'}</small></div></div><section className="panel camera-choice"><div className="section-title"><div><span className="overline">CAMERA</span><h3>Inspection camera</h3></div><button className="text-button" onClick={() => loadCameras(true)}><Icon name="refresh" size={16}/> Refresh list</button></div><div className="camera-choice-row"><div className="camera-select-wrap"><Icon name="camera" size={17}/><select aria-label="Choose inspection camera" value={namedCameras.some(device => device.deviceId === deviceId) ? deviceId : ''} onChange={event => chooseCamera(event.target.value)}><option value="">Default camera</option>{namedCameras.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}</select></div><button className="primary-button" onClick={() => { go('inspect'); startCamera(deviceId) }}><Icon name="camera" size={17}/> {cameraOn && !ipCamera ? 'Open inspection' : 'Start this camera'}</button></div><small>{!cameraDevices.length ? 'No webcams found. Plug one in or click Refresh list.' : cameraDevices.some(device => !device.label) ? `${cameraDevices.length} camera${cameraDevices.length === 1 ? '' : 's'} found. Click Refresh list and allow camera access to see their names.` : `${cameraDevices.length} camera${cameraDevices.length === 1 ? '' : 's'} available. Your choice is remembered.`}</small></section><div className="overview-grid"><section className="panel recent-panel"><div className="section-title"><div><span className="overline">ACTIVITY</span><h3>Recent inspections</h3></div><button className="text-button" onClick={() => go('history')}>View all <Icon name="arrow" size={16}/></button></div>{history.length ? <div className="activity-list">{history.slice(0, 4).map(item => <button key={item.id} className="activity-row" onClick={() => openScan(item)}><span className={`activity-icon ${item.outcome === 'defect' ? 'warn' : ''}`}><Icon name={item.outcome === 'good' ? 'check' : 'alert'} size={18}/></span><span className="activity-main"><strong>{item.outcome === 'defect' ? `${item.findings.length} defects detected` : item.outcome === 'good' ? 'Good PCB confirmed' : unresolvedLabel(item)}</strong><small>{dateLabel(item.created_at)}</small></span><span className={`result-chip ${item.outcome === 'defect' ? 'defect' : item.outcome === 'good' ? 'clear' : 'unknown'}`}>{item.outcome === 'defect' ? 'Review' : item.outcome === 'good' ? 'Good' : 'Stopped'}</span></button>)}</div> : <div className="empty-inline"><Icon name="image" size={26}/><strong>No inspections yet</strong><span>Run your first scan to see activity here.</span></div>}</section><section className="panel setup-panel"><div className="section-title"><div><span className="overline">GETTING STARTED</span><h3>Inspection setup</h3></div></div>{[[classes.length, 'Create defect classes', 'Name the defects you want to detect.', 'plus'], [allReady, 'Label 5+ samples per class', 'Draw a box around each defect.', 'upload'], [modelReady, 'Train your YOLO model', 'Check validation metrics before use.', 'activity']].map(([done, title, subtitle, icon]) => <div className="setup-step" key={title}><span className={done ? 'done' : ''}><Icon name={done ? 'check' : icon} size={17}/></span><div><strong>{title}</strong><small>{subtitle}</small></div></div>)}<button className="secondary-button setup-action" onClick={() => go('training')}>Go to training studio <Icon name="arrow" size={16}/></button></section></div></>}

      {page === 'inspect' && <><div className="page-heading"><div><div className="eyebrow">LIVE INSPECTION</div><h1>Inspect a PCB board</h1><p>Use a built-in or external webcam, or upload a board image.</p></div><div className="heading-actions"><div className="side-toggle" role="group" aria-label="Sides to inspect"><button className={sideMode === 'one' ? 'active' : ''} onClick={() => switchSideMode('one')} disabled={busy}>One side</button><button className={sideMode === 'two' ? 'active' : ''} onClick={() => switchSideMode('two')} disabled={busy}>Two sides</button></div><button className="secondary-button" onClick={saveDashboardSetup} disabled={busy}>Save dashboard setup</button><span className={`model-pill ${modelReady ? 'ready' : ''}`}><i/>{health?.model_stale ? 'Retrain model' : modelReady ? 'Model ready' : 'Model not trained'}</span></div></div><div className="inspection-grid"><section className="panel camera-panel"><div className="panel-top"><div><span className="overline">CAMERA FEED</span><h3>Live workspace</h3></div><span className={`live-pill ${cameraOn ? 'on' : ''}`}><i/>{cameraOn ? 'LIVE' : 'OFFLINE'}</span></div><div className="camera-stage">{pendingScan ? <PcbAreaPicker src={pendingScan.preview} area={inspectionArea} onChange={setInspectionArea}/> : lastScan ? <div className="result-image-wrap"><img src={lastScan.image_url} alt="Last inspected PCB"/>{(lastScan.detections || lastScan.findings).map((finding, index) => <div key={index} className={`detection-box ${isGoodBoardLabel(finding.name) ? 'good' : ''}`} style={{ left: `${finding.box.x * 100}%`, top: `${finding.box.y * 100}%`, width: `${finding.box.w * 100}%`, height: `${finding.box.h * 100}%` }}><span>{finding.name} · {(finding.confidence * 100).toFixed(0)}%</span></div>)}</div> : cameraOn ? ipCamera ? <img key={ipCamera.connectedAt} className="ip-feed" src={`/api/ipcam/stream?session=${ipCamera.connectedAt}`} alt="IP camera live feed"/> : <video ref={videoRef} autoPlay playsInline muted/> : <div className="camera-empty"><div className="camera-empty-icon"><Icon name="camera" size={31}/></div><strong>Camera is not connected</strong><span>Connect a webcam to start inspecting PCB boards.</span><div className="camera-empty-actions"><button className="secondary-button" onClick={() => startCamera()}><Icon name="camera" size={17}/> Connect camera</button><button className="secondary-button" onClick={() => setShowIpForm(true)}>Use IP camera</button></div></div>}{cameraOn && !ipCamera && (lastScan || pendingScan) && <video ref={videoRef} className="hidden-video" autoPlay playsInline muted/>}<div className="stage-corners"><i/><i/><i/><i/></div></div>{pendingScan && <div className="pcb-area-controls"><span>Drag a box around the PCB only. The saved scan will contain just this area.</span><div><button className="secondary-button" onClick={() => { setPendingScan(null); setInspectionArea(null) }} disabled={busy}>Cancel</button><button className="primary-button" onClick={inspectSelectedArea} disabled={busy || !inspectionArea || inspectionArea.w < .05 || inspectionArea.h < .05}>Inspect selected PCB</button></div></div>}<div className="camera-controls"><div className="camera-select-wrap"><Icon name="camera" size={17}/><select aria-label="Select camera" value={ipCamera ? 'ip' : deviceId} onChange={event => event.target.value === 'ip' ? setShowIpForm(true) : startCamera(event.target.value)}><option value="">Default camera</option>{namedCameras.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}<option value="ip">{ipCamera ? `IP camera · ${ipCamera.address}` : 'IP camera…'}</option></select></div><div className="camera-actions">{cameraOn && <button className="icon-button" onClick={stopCamera} title="Stop camera"><Icon name="stop" size={18}/></button>}{cameraOn && lastScan && !pendingScan && <button className="icon-button" onClick={() => setLastScan(null)} title="Show live feed"><Icon name="refresh" size={18}/></button>}<button className="primary-button" onClick={cameraOn ? startConveyor : () => startCamera()} disabled={busy || !!pendingScan || (cameraOn && !modelReady)}><Icon name={cameraOn ? 'scan' : 'camera'} size={17}/>{busy ? 'Scanning…' : cameraOn ? sideMode === 'two' ? 'Start two-side conveyor' : 'Start conveyor' : 'Connect camera'}</button>{cameraOn && sideMode === 'one' && <button className="secondary-button" onClick={selectCameraArea} disabled={busy || !!pendingScan}>Select area manually</button>}</div></div>{showIpForm && <form className="ip-camera-form" onSubmit={connectIpCamera}><label htmlFor="ip-camera-address">IP camera address</label><div><input id="ip-camera-address" value={ipAddress} onChange={event => setIpAddress(event.target.value)} placeholder="192.168.1.20 or 192.168.1.20:8080" inputMode="decimal" autoComplete="off" spellCheck="false" autoFocus/><button className="primary-button" type="submit" disabled={ipConnecting || !ipAddress.trim()}>{ipConnecting ? 'Connecting…' : 'Connect'}</button><button className="secondary-button" type="button" onClick={() => setShowIpForm(false)} disabled={ipConnecting}>Cancel</button></div><small>Enter only the IP address. Phone camera apps, ESP32-CAM, MJPEG, snapshot and RTSP cameras on the same network are found automatically.</small></form>}{cameraOn && cameraArea && !pendingScan && <button className="text-button pcb-area-reset" onClick={() => { setCameraArea(null); setLastScan(null) }}>Use full-image detection</button>}{sideMode === 'one' && <div className="camera-toolbar"><span>{cameraArea ? 'Start conveyor captures the selected area' : 'Start conveyor captures one frame after the PCB is fed'}</span><button className="text-button" onClick={() => inspectInputRef.current?.click()} disabled={busy || !modelReady || !!pendingScan}><Icon name="upload" size={16}/> Upload and auto scan</button><button className="text-button" onClick={() => manualInspectInputRef.current?.click()} disabled={busy || !modelReady || !!pendingScan}>Upload with manual area</button><input ref={manualInspectInputRef} type="file" accept="image/*" hidden onChange={inspectManualUpload}/><input ref={inspectInputRef} type="file" accept="image/*" hidden onChange={inspectUpload}/></div>}{sideMode === 'two' && <SideShots shots={sideShots} cameraOn={cameraOn} busy={busy} modelReady={modelReady} onCapture={captureSide} onUpload={uploadSide} onClear={clearSides} onAnalyze={() => analyzeSides()}/>}</section><section className="panel findings-panel"><div className="panel-top"><div><span className="overline">ANALYSIS</span><h3>Detection results</h3></div><Icon name="target" size={20}/></div>{sideMode === 'two' ? <PairFindings pair={lastPair}/> : lastScan ? <><div className={`analysis-banner ${lastScan.outcome === 'defect' ? 'defect' : lastScan.outcome === 'good' ? 'clear' : 'unknown'}`}><span><Icon name={lastScan.outcome === 'good' ? 'check' : 'alert'} size={22}/></span><div><strong>{lastScan.outcome === 'defect' ? 'Defects detected' : lastScan.outcome === 'good' ? 'Good PCB confirmed' : unresolvedLabel(lastScan)}</strong><small>{lastScan.outcome === 'defect' ? `${lastScan.findings.length} regions need attention` : lastScan.outcome === 'good' ? lastScan.model_stale ? 'Previous model result; conveyor stopped' : 'Forward command sent to Firebase' : 'Conveyor remains stopped'}</small></div></div><div className="analysis-meta"><span>Scanned at</span><strong>{dateLabel(lastScan.created_at)}</strong></div><div className="analysis-meta"><span>PCB region</span><strong>{lastScan.region_source !== 'none' && lastScan.region_source !== 'green' && lastScan.pcb_detected === false ? 'No confident detections' : lastScan.region_source === 'green' ? `Green board crop${lastScan.pcb_region?.angle ? ` · straightened ${lastScan.pcb_region.angle}°` : ''}` : lastScan.region_source === 'none' ? 'No green board found' : lastScan.region_source === 'model' ? 'best.pt / full image' : lastScan.region_source === 'manual' ? 'Manual selection' : 'Saved scan'}</strong></div>{lastScan.model_stale && <div className="locator-note">These results use the previous model. Retrain after correcting labels; automatic conveyor movement is stopped.</div>}<div className="findings-list">{lastScan.findings.map((finding, index) => <div key={index} className="finding-row"><span className="finding-number">{String(index + 1).padStart(2, '0')}</span><div><strong>{finding.name}</strong><small>Defect region</small></div><span className="confidence">{(finding.confidence * 100).toFixed(1)}%</span></div>)}</div></> : <div className="analysis-empty"><div><Icon name="target" size={34}/></div><strong>Ready when you are</strong><p>Run a scan to see detected defect regions and confidence scores here.</p></div>}<div className="locator-note">{health?.model_error || `Model classes: ${(health?.model_classes || []).map(item => item.name).join(', ')}`}</div><div className="analysis-footer"><span>MODEL</span><strong>{health?.model_stale ? 'Previous YOLO model' : modelReady ? 'best.pt' : 'Model unavailable'}</strong></div></section></div>{sideMode === 'two' && lastPair && <PairComparison pair={lastPair}/>}{page === 'training' && health?.oversized_defect_labels > 0 && <div className="label-quality-warning"><Icon name="alert" size={18}/><span>{health.oversized_defect_labels} defect training boxes are too large. Results may be unreliable until those boxes are corrected and the model is retrained.</span><button className="text-button" onClick={() => { setReviewOversized(true); go('training') }}>Review labels</button></div>}{!modelReady && <div className="callout"><span><Icon name="layers" size={21}/></span><div><strong>Load best.pt to enable detection</strong><p>Place your YOLO detection checkpoint at best.pt in the project root.</p></div></div>}<ControlPanel scanId={lastScan?.id} scanning={busy} onStart={startConveyor} onStop={stopConveyor} canStart={cameraOn && modelReady && !pendingScan} phase={cyclePhase} timing={timing} twoSides={sideMode === 'two'}/>{sideMode === 'two' && <TimingSettings activeTiming={timing} onActiveChange={changeTiming} locked={busy}/>}</>}

      {page === 'control' && <><div className="page-heading"><div><div className="eyebrow">CONVEYOR CONTROL</div><h1>Control the PCB conveyor</h1><p>Start a timed PCB inspection cycle. Connect a camera in Live inspection first.</p></div><div className="heading-actions"><div className="side-toggle" role="group" aria-label="Conveyor inspection mode"><button className={sideMode === 'one' ? 'active' : ''} onClick={() => switchSideMode('one')} disabled={busy}>One side</button><button className={sideMode === 'two' ? 'active' : ''} onClick={() => switchSideMode('two')} disabled={busy}>Two sides</button></div><button className="secondary-button" onClick={saveDashboardSetup} disabled={busy}>Save dashboard setup</button></div></div><ControlPanel scanId={lastScan?.id} scanning={busy} onStart={startConveyor} onStop={stopConveyor} canStart={cameraOn && modelReady && !pendingScan} phase={cyclePhase} timing={timing} twoSides={sideMode === 'two'}/><TimingSettings activeTiming={timing} onActiveChange={changeTiming} locked={busy}/></>}
      {page === 'manual' && <><div className="page-heading"><div><div className="eyebrow">MANUAL CONTROL</div><h1>Move the conveyor by hand</h1><p>Send forward, stop or backward directly to the belt.</p></div></div><ManualControl cycleRunning={busy} onStopCycle={stopConveyor}/></>}

      {page === 'training' && <><div className="page-heading"><div><div className="eyebrow">TRAINING STUDIO</div><h1>Teach the model what to find</h1><p>Create defect types, label sample images, and fine-tune YOLO.</p></div><span className="samples-pill"><Icon name="image" size={16}/>{samples.length} samples collected</span></div><div className="training-grid"><section className="panel classes-panel"><div className="section-title"><div><span className="overline">STEP 01</span><h3>Defect classes</h3></div><span className="count-pill">{classes.length} classes</span></div><p className="panel-description">Give each type of defect a clear name. Every class needs at least 5 original labeled examples.</p><form className="class-form" onSubmit={addClass}><input value={newClass} onChange={event => setNewClass(event.target.value)} placeholder="e.g. Missing component" maxLength={50} aria-label="Defect name"/><button type="submit" aria-label="Add defect class"><Icon name="plus" size={20}/></button></form><div className="class-list">{classes.length ? classes.map(item => <button key={item.id} className={`class-row ${selectedClass === item.id ? 'selected' : ''}`} onClick={() => setSelectedClass(item.id)}><span className="class-symbol"><Icon name="target" size={18}/></span><span className="class-name"><strong>{item.name}</strong><small>{item.count} originals / {item.training_count} total</small></span><span className={`class-progress ${item.count >= 5 ? 'complete' : ''}`}>{item.count >= 5 ? <Icon name="check" size={15}/> : `${Math.min(item.count * 20, 100)}%`}</span></button>) : <div className="mini-empty">No defect classes yet. Add your first one above.</div>}</div>{currentClass && <SampleExpansion key={`${currentClass.id}:${currentClass.count}:${currentClass.target_count || 0}`} item={currentClass} onSave={saveExpansion} onError={setError}/>}</section><section className="panel annotation-panel"><div className="section-title"><div><span className="overline">STEP 02</span><h3>Label a sample</h3></div><span className="count-pill">Bounding box</span></div><p className="panel-description">Choose an image and draw a tight defect box. You can also add normal boards without a box.</p><div className="annotate-form"><label>DEFECT CLASS<select value={selectedClass} disabled={!!editingSample} onChange={event => { setSelectedClass(event.target.value); setBox(null) }}><option value="">Select a defect class</option><option value="normal">Normal board (no defect)</option>{classes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="annotate-tools"><button className="secondary-button" onClick={() => sampleInputRef.current?.click()}><Icon name="upload" size={17}/> Choose image</button><button className="secondary-button" onClick={sampleFromCamera} disabled={!cameraOn}><Icon name="camera" size={17}/> Capture camera</button><input ref={sampleInputRef} type="file" accept="image/*" hidden onChange={event => { chooseSample(event.target.files?.[0]); event.target.value = '' }}/></div></div>{samplePreview ? <div className="annotation-image" onPointerDown={onBoxStart} onPointerMove={onBoxMove} onPointerUp={() => { dragRef.current = null }} onPointerCancel={() => { dragRef.current = null }}><img ref={imageRef} src={samplePreview} alt="PCB sample to annotate" draggable="false"/>{box && <div className="sample-box" style={{ left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.w * 100}%`, height: `${box.h * 100}%` }}><span>{currentClass?.name || 'Defect'}</span></div>}</div> : <button className="annotation-placeholder" onClick={() => sampleInputRef.current?.click()}><Icon name="image" size={31}/><strong>Choose a training image</strong><span>Then drag over the defect to draw its box.</span></button>}<div className="annotate-bottom"><span>{samplePreview ? selectedClass === 'normal' ? 'Normal board. Save without a box.' : editingSample ? 'Redraw a tight box around the defect, then save.' : box ? 'Box drawn. Save this labeled sample.' : 'Drag over the image to mark the defect.' : 'JPG, PNG, or WEBP · max 12 MB'}</span>{editingSample && <button className="secondary-button" onClick={cancelSampleEdit}>Cancel edit</button>}<button className="primary-button" onClick={saveSample} disabled={savingSample || (!sampleFile && !editingSample) || !selectedClass || (selectedClass !== 'normal' && !box)}><Icon name={editingSample ? "edit" : "plus"} size={17}/>{savingSample ? 'Saving…' : editingSample ? 'Save corrected box' : 'Add sample'}</button></div></section></div><div className="training-bottom-grid"><section className="panel samples-panel"><div className="section-title"><div><span className="overline">DATASET</span><h3>{reviewOversized ? 'Large defect boxes' : 'Recent samples'}</h3></div><div className="sample-list-actions">{(reviewOversized || oversizedSamples.length > 0) && <button className="text-button" onClick={() => setReviewOversized(!reviewOversized)}>{reviewOversized ? 'Show recent' : `Review ${oversizedSamples.length} large boxes`}</button>}<span className="count-pill">{reviewOversized ? oversizedSamples.length : samples.length} total</span></div></div>{(reviewOversized ? oversizedSamples.length : samples.length) ? <div className="sample-grid">{(reviewOversized ? oversizedSamples : samples.slice().reverse().slice(0, 8)).map(sample => <div className="sample-tile" key={sample.id}><img src={sample.image_url} alt="Labeled PCB sample"/><span>{classes.find(item => item.id === sample.class_id)?.name || 'Normal board'}{reviewOversized ? ' - large box' : ''}</span>{sample.box && !isGoodBoardLabel(classes.find(item => item.id === sample.class_id)?.name || '') && <button className="edit-sample" onClick={() => editSample(sample)} aria-label="Edit defect box" title="Edit defect box"><Icon name="edit" size={14}/></button>}<button className="delete-sample" onClick={() => removeSample(sample.id)} aria-label="Delete sample" title="Delete sample"><Icon name="trash" size={14}/></button></div>)}</div> : <div className="empty-inline"><Icon name="image" size={26}/><strong>{reviewOversized ? 'No large boxes remain' : 'No samples yet'}</strong><span>{reviewOversized ? 'Add correctly labeled images before retraining.' : 'Your labeled images will appear here.'}</span></div>}</section><section className="panel train-panel"><div className="section-title"><div><span className="overline">STEP 03</span><h3>Train your model</h3></div><span className="train-icon"><Icon name="activity" size={20}/></span></div><p className="panel-description">The model uses 80% of each class for training and 20% for validation. Review its measured mAP before deployment.</p>{page === 'training' && health?.oversized_defect_labels > 0 && <div className="label-quality-warning"><Icon name="alert" size={18}/><span>{health.oversized_defect_labels} defect label{health.oversized_defect_labels === 1 ? '' : 's'} cover over 75% of the image. Edit those samples, redraw tight boxes around the defects, and retrain. The current model may mistake background for a defect.</span></div>}<div className="train-readiness"><div><span>Dataset readiness</span><strong>{classes.length ? `${classes.filter(item => item.count >= 5).length} / ${classes.length} classes ready` : 'No classes yet'}</strong></div><div className="progress-track"><span style={{ width: `${classes.length ? classes.filter(item => item.count >= 5).length / classes.length * 100 : 0}%` }}/></div></div>{health?.training.status === 'running' && <div className="training-status"><span className="spinner"/>{health.training.message}</div>}{health?.training.status === 'failed' && <div className="training-failure">Training failed: {health.training.message}</div>}{health?.metrics?.map50 != null && <div className="metric-results"><div><strong>{(health.metrics.map50 * 100).toFixed(1)}%</strong><span>Val mAP@50</span></div><div><strong>{(health.metrics.precision * 100).toFixed(1)}%</strong><span>Precision</span></div><div><strong>{(health.metrics.recall * 100).toFixed(1)}%</strong><span>Recall</span></div></div>}<button className="primary-button train-button" onClick={startTraining} disabled={!allReady || health?.oversized_defect_labels > 0 || startingTraining || health?.training.status === 'running'}><Icon name="play" size={17}/>{health?.training.status === 'running' ? 'Training in progress' : health?.trained_at ? 'Retrain YOLO model' : 'Train YOLO model'}<Icon name="arrow" size={17}/></button><small className="train-note">Training saves backend/data/model.pt; inspection continues using the root best.pt. 5 original images per class is a starting minimum. Accuracy depends on image quality, variety, and an independent test set.</small></section></div></>}

      {page === 'history' && <><div className="page-heading"><div><div className="eyebrow">SCAN HISTORY</div><h1>Inspection records</h1><p>Review previously analyzed boards and their detected defects.</p></div><div className="heading-actions"><a className="secondary-button" href="/api/report.pdf" download><Icon name="download" size={16}/> Export PDF</a><span className="samples-pill"><Icon name="clock" size={16}/>{history.length} inspections</span></div></div><section className="panel history-panel">{history.length ? <div className="history-list">{history.map(item => <button className="history-row" key={item.id} onClick={() => openScan(item)}><img src={item.image_url} alt="PCB scan thumbnail"/><div className="history-main"><strong>{item.outcome === 'defect' ? `${item.findings.length} defects found` : item.outcome === 'good' ? 'Good PCB confirmed' : unresolvedLabel(item)}</strong><span>{item.side ? `${sideName[item.side]} side · ` : ''}{dateLabel(item.created_at)} · {item.findings.map(finding => finding.name).join(', ') || (item.outcome === 'good' ? 'Good PCB' : unresolvedLabel(item))}</span></div><span className={`result-chip ${item.outcome === 'defect' ? 'defect' : item.outcome === 'good' ? 'clear' : 'unknown'}`}>{item.outcome === 'defect' ? 'Review' : item.outcome === 'good' ? 'Good' : 'Stopped'}</span><Icon name="arrow" size={17}/></button>)}</div> : <div className="history-empty"><Icon name="clock" size={32}/><h3>No scan history yet</h3><p>Completed inspections will be saved here for review.</p><button className="primary-button" onClick={() => go('inspect')}>Open inspection <Icon name="arrow" size={16}/></button></div>}</section></>}
    </main></div>
  </div>
}

export default App
