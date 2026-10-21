const goodNames = new Set(['goodpcb', 'goodboard', 'normalpcb', 'normalboard', 'nodefect', 'defectfree'])

export function isGoodBoardLabel(name) {
  return goodNames.has(String(name || '').toLowerCase().replace(/[^a-z0-9]/g, ''))
}

export function classifyScan(scan) {
  const detections = Array.isArray(scan.detections) ? scan.detections : Array.isArray(scan.findings) ? scan.findings : []
  const defects = detections.filter(finding => !isGoodBoardLabel(finding.name))
  const goodBoardFound = detections.some(finding => isGoodBoardLabel(finding.name))
  const outcome = defects.length ? 'defect' : goodBoardFound && !scan.model_stale ? 'good' : 'unknown'
  return { ...scan, detections, findings: defects, outcome }
}
