---
name: session-archive
description: Archive recent Claude Code conversations before Claude Code deletes old transcripts. Use when the user says "archive my sessions", "sync sessions", "back up my Claude conversations", "save the recent conversations", "session archive status", "did the archive run?", or wants to make sure past sessions are not lost. It only archives (a digest + gzipped transcript per session); it does not summarize them into notes or a wiki.
---

# session-archive

One pair per Claude Code session in the archive folder: `YYYY-MM-DD_<slug>.digest.md` (metadata + the
conversation text, tool calls cut) and `YYYY-MM-DD_<slug>.jsonl.gz` (the raw transcript). A session that kept
going after it was archived gets a `<slug>-cont-N` pair with only the new lines. Nothing is archived twice:
the digests themselves are the watermark.

The command is `session-archive` (on the Bash tool's PATH while the plugin is enabled; full path
`python3 "${CLAUDE_PLUGIN_ROOT}/bin/session-archive"`). `session-archive --help` lists every option.

## Steps

1. **Plan.** `session-archive plan`. It lists new sessions, continuations and skips, with a reason for each
   skip: `live` (written in the last 2 minutes, usually this very session; it is picked up next time),
   `trivial` (fewer than 10 user turns or under 50 KB), `subagent` (mostly sidechain lines). Show the user
   only warnings (`WARNING broken archive ...`); the rest goes in the final report.
2. **Run.** `session-archive run` (oldest first, at most 40 pairs per run; `--limit N` to change). If it says
   sessions are left over the limit, run it again until nothing is left, or tell the user how many remain.
   Each pair is read back from disk (gzip line count and digest header) before it counts as archived.
3. **TL;DR.** Each new digest has a `<!-- TLDR: not written yet -->` line under its TL;DR heading (the
   heading text can be changed in the config). For each digest
   the run printed, read its conversation section and replace that line with up to 5 lines: what the session
   did and decided. Keep everything else in the digest as it is. If the user is in a hurry or there are many,
   say how many TL;DRs are still open instead of writing them.
4. **Report** after `session-archive verify` passes: pairs written (names), sessions skipped with reasons,
   sessions left, where the archive is (`session-archive status` shows the folder and the last run).

If `run` exits with code 3, another run holds the lock: wait, or check that no run is active and delete the
lock file it names. Exit code 4 means the user's `pre_command` refused to start (it prints why); report that
and do not work around it. A `post_command exited N` message means the pairs were written but the user's
follow-up command failed: report it.

## Settings the user may ask about

- Archive folder: `SESSION_ARCHIVE_DIR`, or `out_dir` in `~/.config/session-archive/config.json`, or `--out`.
  Default `~/claude-session-archive`.
- Thresholds: `--min-turns`, `--min-kb`, `--live-minutes` (or `min_turns`, `min_kb`, `live_minutes`,
  `exclude` in the config file).
- Digest labels, index and log files, a shared skip list, and commands to run before and after: keys in the
  same config file (`digest`, `index_file`, `log_file`, `skipped_file`, `pre_command`, `post_command`, ...;
  the plugin README lists them). The file is outside the plugin folder, so it survives plugin updates. After
  a change, `session-archive plan` shows whether existing digests are still recognized
  (`already archived sessions`).
- Retention: Claude Code deletes transcripts older than `cleanupPeriodDays` (default 30) from
  `~/.claude/settings.json`. `session-archive status` warns when the last successful run is close to that.
- A daily run without Claude: `./install.sh --schedule` from the repo (launchd on macOS, a crontab line on
  Linux).

## Out of scope

Summarizing sessions into notes or a wiki, deleting the original transcripts, editing past digests other than
filling the TL;DR.
