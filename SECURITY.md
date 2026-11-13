# Security

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Open the repository's
[Security tab](https://github.com/lucas-saldanha-werneck/session-archive/security) and choose
"Report a vulnerability" (GitHub private vulnerability reporting).

## Supported versions

Only the latest release is supported. Fixes land there.

## What this plugin accesses

- Files: it reads session transcripts under `~/.claude/projects` (or `$CLAUDE_CONFIG_DIR`) and `cleanupPeriodDays` from `~/.claude/settings.json`, and writes copies, digests, an index, a log and run history to the archive folder, `~/claude-session-archive` by default. A folder it creates gets mode 0700 (an existing one is left as it is); archive files are created with mode 0600. It never deletes or changes the originals; replaced archive pairs are moved to `.state/superseded`, not deleted.
- Config: at every session start the plugin creates `~/.config/session-archive/config.json` if it is missing (never overwritten).
- Sensitive data: a transcript holds everything typed or pasted in the session, including anything secret, and the archive keeps it as plain, readable files. Archive file names are built from each session's title or first message. When the skill runs, Claude reads the new digests to write their summaries, so that text enters the session. Protect the archive folder like the transcripts themselves.
- Commands you configure: `pre_command` and `post_command` in the config file run through the shell on every `run`.
- Install and schedule: `install.sh` copies the command to `~/.local/bin`. With `--schedule` on macOS it writes `~/Library/LaunchAgents/<prefix>.session-archive.plist`, loads it with `launchctl` (daily run, output to `~/Library/Logs/session-archive.log`); on Linux it only prints a crontab line. Both are opt-in.
- Network: the plugin's own code makes no network requests.
