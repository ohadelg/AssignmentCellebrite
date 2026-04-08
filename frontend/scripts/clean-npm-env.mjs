#!/usr/bin/env node
/**
 * Drops npm_config_devdir / NPM_CONFIG_DEVDIR before spawning the real command.
 * Some tools set these; recent npm warns "Unknown env config devdir".
 */
import { spawnSync } from 'node:child_process'

delete process.env.npm_config_devdir
delete process.env.NPM_CONFIG_DEVDIR

const [cmd, ...args] = process.argv.slice(2)
if (!cmd) {
  console.error('usage: clean-npm-env.mjs <command> [...args]')
  process.exit(1)
}

const r = spawnSync(cmd, args, {
  stdio: 'inherit',
  env: process.env,
  shell: process.platform === 'win32',
})

process.exit(r.status === null ? 1 : r.status)
