# Security

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Open the repository's
[Security tab](https://github.com/lucas-saldanha-werneck/session-archive/security) and choose
"Report a vulnerability" (GitHub private vulnerability reporting).

## Supported versions

Only the latest release is supported. Fixes land there.

## What this plugin accesses

- Files: it reads session transcripts under `~/.claude/projects` (or `$CLAUDE_CONFIG_DIR`) and writes copies to the archive folder, `~/claude-session-archive` by default (folder mode 0700, files mode 0600). It only reads the originals; it removes nothing but its own temporary files.
- Sensitive data: a transcript holds everything typed or pasted in the session, including anything secret, and the archive keeps it as plain, readable files. Protect that folder like the transcripts themselves.
- Schedule: on macOS, `install.sh` can add a launchd agent that runs the archive periodically; it is opt-in.
- Network: the plugin's own code makes no network requests.

