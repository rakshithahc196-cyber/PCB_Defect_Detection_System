// Waits until the camera shows a still scene, so a PCB still coasting on the belt is not inspected blurred.

const sampleSize = { width: 64, height: 48 }

async function grayscale(blob) {
  const bitmap = await createImageBitmap(blob)
  const canvas = document.createElement('canvas')
  canvas.width = sampleSize.width; canvas.height = sampleSize.height
  const context = canvas.getContext('2d', { willReadFrequently: true })
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close?.()
  const { data } = context.getImageData(0, 0, canvas.width, canvas.height)
  const pixels = new Float32Array(canvas.width * canvas.height)
  for (let i = 0; i < pixels.length; i++) pixels[i] = data[i * 4] * .299 + data[i * 4 + 1] * .587 + data[i * 4 + 2] * .114
  return pixels
}

// Mean absolute brightness change between two frames, 0–255.
function difference(a, b) {
  let total = 0
  for (let i = 0; i < a.length; i++) total += Math.abs(a[i] - b[i])
  return total / a.length
}

const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))

export async function captureStillFrame(capture, { interval = 250, threshold = 3, stableFrames = 2, timeout = 5000, onWaiting = () => {} } = {}) {
  const deadline = Date.now() + timeout
  let frame = await capture()
  let previous = await grayscale(frame)
  let stable = 0
  while (Date.now() < deadline) {
    await pause(interval)
    frame = await capture()
    const current = await grayscale(frame)
    stable = difference(previous, current) < threshold ? stable + 1 : 0
    if (stable >= stableFrames) return { frame, still: true }
    if (!stable) onWaiting()
    previous = current
  }
  return { frame, still: false }
}
