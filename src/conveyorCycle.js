import { COMMANDS, DEFAULT_TIMING } from './firebaseControl.js'

const wait = (milliseconds, signal) => new Promise(resolve => {
  const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve() }
  const timer = setTimeout(finish, milliseconds)
  signal.addEventListener('abort', finish, { once: true })
  if (signal.aborted) finish()
})

export function createConveyorCycle(send, delay = wait) {
  let active = null
  const confirmStop = async () => {
    try { await send(COMMANDS.STOP) }
    catch (error) { throw new Error(`Stop command failed: ${error.message}. Conveyor stop is not confirmed.`, { cause: error }) }
  }
  return {
    async stop() {
      active?.abort()
      await send(COMMANDS.STOP)
    },
    async run({ feed = false, inspect, onPhase = () => {}, timing = DEFAULT_TIMING }) {
      const { feedSeconds, settleSeconds, goodSeconds, defectSeconds } = { ...DEFAULT_TIMING, ...timing }
      if (active) throw new Error('A conveyor cycle is already running')
      const controller = new AbortController()
      active = controller
      const check = () => {
        if (controller.signal.aborted) throw new DOMException('Cycle stopped', 'AbortError')
      }
      try {
        await send(COMMANDS.STOP)
        check()
        if (feed) {
          onPhase(`Feeding PCB: forward for ${feedSeconds} seconds`)
          await send(COMMANDS.FORWARD)
          check()
          await delay(feedSeconds * 1000, controller.signal)
          check()
          await send(COMMANDS.STOP)
          check()
          onPhase(`Conveyor stopped: letting the PCB settle for ${settleSeconds} seconds`)
          await delay(settleSeconds * 1000, controller.signal)
          check()
        }
        onPhase('Conveyor stopped: inspecting PCB')
        const result = await inspect({ signal: controller.signal, check, move: async (command, seconds) => {
          check()
          await send(command)
          check()
          await delay(seconds * 1000, controller.signal)
          check()
          await send(COMMANDS.STOP)
          check()
        }, wait: async milliseconds => {
          await delay(milliseconds, controller.signal)
          check()
        } })
        check()
        const outcome = result.model_stale ? 'unknown' : result.outcome
        if (outcome === 'good' || outcome === 'defect') {
          onPhase(outcome === 'good' ? `Good PCB: forward for ${goodSeconds} seconds` : `Defective PCB: backward for ${defectSeconds} seconds`)
          await send(outcome === 'good' ? COMMANDS.FORWARD : COMMANDS.BACKWARD)
          check()
          await delay((outcome === 'good' ? goodSeconds : defectSeconds) * 1000, controller.signal)
          check()
        }
        onPhase(outcome === 'unknown' ? 'No PCB confirmed: staying stopped' : 'Cycle complete: stopping conveyor')
        return result
      } finally {
        try { await confirmStop() }
        finally { active = null }
      }
    },
  }
}
