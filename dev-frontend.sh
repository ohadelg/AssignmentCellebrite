#!/usr/bin/env sh
# Start Vite without invoking `npm run` (avoids npm's "Unknown env config devdir" warning).
cd "$(dirname "$0")/frontend" || exit 1
unset npm_config_devdir 2>/dev/null
unset NPM_CONFIG_DEVDIR 2>/dev/null
exec node scripts/vite-dev.mjs
