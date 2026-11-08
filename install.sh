#!/usr/bin/env bash
# session-archive: optional install of the command line tool, with an optional daily schedule.
# The plugin alone is enough to run the skill; this is for running the archive without Claude.
#
# Usage: ./install.sh [--schedule] [--hour H] [--label-prefix P] [--os macos|linux] [--no-load] [--dry-run]
#        ./install.sh --uninstall [--os macos|linux] [--no-load] [--dry-run]
#   --schedule      macOS: write a launchd agent that runs `session-archive run` daily and load it.
#                   Linux: print the crontab line to add (nothing is changed).
#   --hour H        hour of the daily run (default 4)
#   --label-prefix  launchd label prefix (default com.claude-tools); the label is <prefix>.session-archive
#   --no-load       write or remove the plist but do not call launchctl
# SESSION_ARCHIVE_DIR, if set when you run this, is written into the launchd agent.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SCHEDULE=0; UNINSTALL=0; DRY=0; LOAD=1; HOUR=4; PREFIX="com.claude-tools"
case "$(uname -s 2>/dev/null)" in Darwin) OS=macos;; Linux) OS=linux;; *) OS=other;; esac
while [ $# -gt 0 ]; do case "$1" in
  --schedule) SCHEDULE=1; shift;; --uninstall) UNINSTALL=1; shift;; --dry-run) DRY=1; shift;;
  --no-load) LOAD=0; shift;; --hour) HOUR="$2"; shift 2;; --label-prefix) PREFIX="$2"; shift 2;;
  --os) OS="$2"; shift 2;;
  -h|--help) sed -n '2,14p' "$0"; exit 0;;
  *) echo "unknown option: $1" >&2; exit 1;; esac; done
case "$HOUR" in ''|*[!0-9]*) echo "--hour must be a number 0-23" >&2; exit 1;; esac
LABEL="$PREFIX.session-archive"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3 || command -v python || true)"
run() { if [ $DRY = 1 ]; then echo "would run: $*"; else "$@"; fi; }

if [ $UNINSTALL = 1 ]; then
  if [ "$OS" = macos ] && [ -f "$PLIST" ]; then
    [ $LOAD = 1 ] && run launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    run rm -f "$PLIST"; echo "removed $PLIST"
  fi
  [ -f "$BIN_DIR/session-archive" ] && { run rm -f "$BIN_DIR/session-archive"; echo "removed $BIN_DIR/session-archive"; }
  [ "$OS" = linux ] && echo "if you added a crontab line for session-archive, remove it with: crontab -e"
  echo "your archive folder was not touched"
  exit 0
fi

[ -n "$PY" ] || { echo "python3 not found on PATH" >&2; exit 1; }
run mkdir -p "$BIN_DIR"
run cp "$HERE/bin/session-archive" "$BIN_DIR/session-archive"
run chmod +x "$BIN_DIR/session-archive"
echo "installed $BIN_DIR/session-archive"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "note: $BIN_DIR is not on your PATH";; esac

[ $SCHEDULE = 1 ] || exit 0
OUT_XML=""
if [ -n "${SESSION_ARCHIVE_DIR:-}" ]; then
  OUT_XML="  <key>EnvironmentVariables</key>
  <dict><key>SESSION_ARCHIVE_DIR</key><string>$SESSION_ARCHIVE_DIR</string></dict>"
fi
LOG_DIR="$HOME/Library/Logs"
case "$OS" in
  macos)
    body="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$BIN_DIR/session-archive</string><string>run</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>0</integer></dict>
$OUT_XML
  <key>StandardOutPath</key><string>$LOG_DIR/session-archive.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/session-archive.log</string>
</dict>
</plist>"
    if [ $DRY = 1 ]; then echo "would write $PLIST (label $LABEL):"; echo "$body"
    else
      mkdir -p "$(dirname "$PLIST")" "$LOG_DIR"
      printf '%s\n' "$body" > "$PLIST"
      echo "wrote $PLIST"
    fi
    if [ $LOAD = 1 ]; then
      run launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
      run launchctl bootstrap "gui/$(id -u)" "$PLIST"
      echo "loaded $LABEL: runs daily at $HOUR:00, log $LOG_DIR/session-archive.log"
    fi ;;
  linux)
    echo "add this line with crontab -e (runs daily at $HOUR:00):"
    echo "0 $HOUR * * * ${SESSION_ARCHIVE_DIR:+SESSION_ARCHIVE_DIR=$SESSION_ARCHIVE_DIR }$PY $BIN_DIR/session-archive run >> \$HOME/.cache/session-archive.log 2>&1" ;;
  *) echo "no scheduler support on this OS; run 'session-archive run' with your own task scheduler" ;;
esac
