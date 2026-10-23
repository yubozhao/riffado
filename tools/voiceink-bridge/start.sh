#!/bin/sh
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
BRIDGE_HOME="${RIFFADO_VOICEINK_HOME:-$HOME/.local/share/riffado}"
if [ ! -f "$BRIDGE_HOME/voiceink.env" ]; then
    echo "Create $BRIDGE_HOME/voiceink.env with RIFFADO_VOICEINK_KEY first." >&2
    exit 1
fi
set -a
. "$BRIDGE_HOME/voiceink.env"
set +a
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -B "$SCRIPT_DIR/server.py" "$@"
