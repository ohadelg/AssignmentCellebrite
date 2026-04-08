#!/usr/bin/env node
/**
 * Start Vite without going through `npm run` (avoids npm's devdir env warning)
 * and strips npm_config_devdir for the child.
 */
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

delete process.env.npm_config_devdir
delete process.env.NPM_CONFIG_DEVDIR

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const viteCli = path.join(root, 'node_modules', 'vite', 'bin', 'vite.js')

const r = spawnSync(process.execPath, [viteCli, '--host', '127.0.0.1'], {
  stdio: 'inherit',
  env: process.env,
  cwd: root,
})

process.exit(r.status === null ? 1 : r.status)
