import test from 'node:test'
import assert from 'node:assert/strict'
import { captureTwoSides } from './twoSideCapture.js'
import { createConveyorCycle } from './conveyorCycle.js'

test('two-side cycle feeds for 3 seconds, stops, waits 8 seconds between images, then sorts', async () => {
  const events = []
  const cycle = createConveyorCycle(async command => events.push(['command', command]), async ms => events.push(['wait', ms]))
  let frame = 0
  await cycle.run({ feed: true, timing: { feedSeconds: 3, settleSeconds: 0 }, inspect: async ({ wait, check, move }) => {
    const files = await captureTwoSides({ capture: async () => { events.push(['capture', ++frame]); return frame },
      wait, check, move, feedSeconds: 3, turnSeconds: 8, onFront: () => {}, onTurn: () => {}, onPhase: () => {} })
    assert.deepEqual(files, { front: 1, back: 2 })
    return { outcome: 'good' }
  } })
  assert.deepEqual(events.slice(0, 6), [['command', 0], ['command', 1], ['wait', 3000], ['command', 0], ['wait', 0], ['capture', 1]])
  const back = events.findIndex(event => event[0] === 'capture' && event[1] === 2)
  assert.deepEqual(events.slice(6, back), [['command', 2], ['wait', 3000], ['command', 0], ...Array.from({ length: 8 }, () => ['wait', 1000]), ['command', 1], ['wait', 3000], ['command', 0]])
  assert.deepEqual(events.slice(back + 1), [['command', 1], ['wait', 4000], ['command', 0]])
})

test('Stop during turn countdown cancels back capture and sorting and closes popup', async () => {
  const commands = []
  let releaseTurn
  let turnStarted
  const started = new Promise(resolve => { turnStarted = resolve })
  const cycle = createConveyorCycle(async command => commands.push(command), async (ms, signal) => {
    if (ms !== 1000) return
    turnStarted()
    await new Promise(resolve => { releaseTurn = resolve; signal.addEventListener('abort', resolve, { once: true }) })
  })
  let captures = 0
  let popup
  const running = cycle.run({ inspect: async ({ wait, check, move }) => {
    await captureTwoSides({ capture: async () => ++captures, wait, check, move, feedSeconds: 3, turnSeconds: 8,
      onFront: () => {}, onTurn: value => { popup = value }, onPhase: () => {} })
    return { outcome: 'good' }
  } })
  const rejected = assert.rejects(running, { name: 'AbortError' })
  await started
  await cycle.stop()
  releaseTurn()
  await rejected
  assert.equal(captures, 1)
  assert.equal(popup, null)
  assert.deepEqual(commands, [0, 2, 0, 0, 0])
})
