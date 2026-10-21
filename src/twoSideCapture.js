import { COMMANDS } from './firebaseControl.js'

// Called while the conveyor cycle owns the belt and has stopped it after feeding.
export async function captureTwoSides({ capture, wait, check, move, feedSeconds, turnSeconds, onFront, onTurn, onPhase }) {
  onPhase('Conveyor stopped: capturing front side')
  const front = await capture()
  check()
  onFront(front)
  try {
    onPhase(`Returning PCB: backward for ${feedSeconds} seconds`)
    await move(COMMANDS.BACKWARD, feedSeconds)
    onPhase('Conveyor stopped: turn your PCB')
    let remaining = turnSeconds
    onTurn(remaining)
    while (remaining > 0) {
      const step = Math.min(1, remaining)
      await wait(step * 1000)
      remaining = Math.max(0, Math.round((remaining - step) * 10) / 10)
      onTurn(remaining)
    }
    check()
    onTurn(null)
    onPhase(`Bringing back side to camera: forward for ${feedSeconds} seconds`)
    await move(COMMANDS.FORWARD, feedSeconds)
    onPhase('Conveyor stopped: capturing back side')
    const back = await capture()
    check()
    return { front, back }
  } finally {
    onTurn(null)
  }
}
