# session-archive

A Claude Code plugin that keeps your conversations. Each session becomes a pair of files in an archive
folder: a readable digest and the gzipped raw transcript. Claude Code deletes transcripts older than
`cleanupPeriodDays` (30 days by default), so whatever you did not copy is gone after that.

```
~/claude-session-archive/
  2026-03-04_parser-refactor.digest.md        metadata + the conversation text, tool calls cut
  2026-03-04_parser-refactor.jsonl.gz         the transcript, byte for byte
  2026-03-04_parser-refactor-cont-1.digest.md the same session, later: only the new lines
  2026-03-04_parser-refactor-cont-1.jsonl.gz
  INDEX.md                                    one line per pair
  log.md                                      one entry per run
  .state/                                     run history, skipped sessions, lock
```

## What a digest looks like

```
# parser-refactor

**Date:** 2026-03-04
**Session:** `11111111-1111-4111-8111-111111111111`
**Project:** /work/demo
**Source:** ~/.claude/projects/-work-demo/11111111-....jsonl
**Raw copy:** 2026-03-04_parser-refactor.jsonl.gz
**Lines:** 1-37
**User turns:** 12
**Compactions:** (none)

## TL;DR

<!-- TLDR: not written yet -->        (the skill has Claude fill this in)

## Conversation (text only, tool calls omitted)

**[USER]**

Refactor the parser module please

_[1 tool call(s) and result(s) omitted]_

**[CLAUDE]**

Done with step 0.
```

The slug comes from the session's title (the one Claude Code shows), else its first message.

## How it avoids duplicates and gaps

- **The archive is its own watermark.** Each digest records its session id and the transcript lines it holds
  (`Lines: A-B`). A run reads them back, checks each `.gz` opens and holds that many lines, and archives only
  what is missing. Running it twice writes nothing the second time.
- **Continuations.** A session you resumed after it was archived gets a `-cont-N` pair with only the new lines.
- **Broken copies come back.** A missing or corrupt `.gz` is reported by `verify`, and the next `run`
  archives that session again under a new name.
- **Skips have reasons.** `live` (written in the last 2 minutes, picked up next run), `trivial` (fewer than
  10 user turns or under 50 KB), `subagent` (mostly sidechain lines). Trivial and subagent skips are
  remembered and only checked again when the transcript changes.
- **Gap warning.** `status` warns when the last successful run is within 3 days of Claude Code's retention.
- Every pair is read back from disk before it counts. A lock file stops two runs at once.

## Install

```
/plugin marketplace add lucas-saldanha-werneck/session-archive
/plugin install session-archive@session-archive
```

Then ask Claude to "archive my sessions". The skill runs the command, then fills in each new digest's TL;DR.

To run it without Claude, on a schedule (optional):

```
git clone https://github.com/lucas-saldanha-werneck/session-archive && cd session-archive
./install.sh --schedule            # --dry-run first to see the plan
```

That copies `session-archive` to `~/.local/bin`. On macOS `--schedule` writes and loads a launchd agent
(`com.claude-tools.session-archive`, daily at 4:00; `--hour`, `--label-prefix` to change). On Linux it prints
the crontab line to add. A scheduled run leaves the TL;DR blank; the skill fills it in later.

## Usage

```
session-archive plan                 # what a run would do; writes nothing
session-archive run                  # archive (oldest first, 40 pairs per run; --limit N, --dry-run)
session-archive verify               # check every pair
session-archive status               # archive folder, last run, retention warning
```

Add `--json` to any command for machine-readable output.

## Configuration

Flags win over environment variables, which win over the config file.

| Setting | Flag | Env var | Config key | Default |
|---|---|---|---|---|
| Archive folder | `--out` | `SESSION_ARCHIVE_DIR` | `out_dir` | `~/claude-session-archive` |
| Transcripts folder | `--projects` | `SESSION_ARCHIVE_PROJECTS` | `projects_dir` | `$CLAUDE_CONFIG_DIR/projects`, else `~/.claude/projects` |
| Minimum user turns | `--min-turns` | | `min_turns` | `10` |
| Minimum size (KB) | `--min-kb` | | `min_kb` | `50` |
| "Live" window (minutes) | `--live-minutes` | | `live_minutes` | `2` |
| Project folders to skip (substrings) | | | `exclude` | temp folders (`-tmp-`, `-private-tmp-`, `scratchpad`) |

The config file is `~/.config/session-archive/config.json` (or `$SESSION_ARCHIVE_CONFIG`):

```json
{ "out_dir": "~/Documents/claude-archive", "min_turns": 5 }
```

To make the archive outlive your machine, put the folder inside something that syncs or is backed up.

## Requirements

- Python 3.9+ (standard library only).
- `bash` for `install.sh`.

## Optional requirements

| Thing | Used for | Without it |
|---|---|---|
| launchd (macOS) | daily run from `install.sh --schedule` | run it by hand, from the skill, or with any scheduler |
| cron (Linux) | daily run | same |

## Platform

The command and the skill work on macOS, Linux and Windows. The scheduler part of `install.sh` is macOS
(launchd) and Linux (prints a crontab line). Tests run on all three in CI.

## Tests

```
python3 tests/test_session_archive.py -v
```

They build a fake `~/.claude/projects` tree in a temp folder (a normal session, a short one, a subagent
transcript, a live one, a temp-folder project) and check the pairs byte for byte, skips, idempotency,
continuations, broken-copy recovery, the run limit, config precedence, the lock, the gap warning, and
`install.sh` with a fake `launchctl`.

## Uninstall

```
/plugin uninstall session-archive@session-archive
/plugin marketplace remove session-archive
```

If you ran `install.sh`: `./install.sh --uninstall` removes the command and the launchd agent. Your archive
folder is never touched.

## Limits

- Checked against real transcripts on macOS (read-only, archive written to a temp folder). Not run against
  real transcripts on Linux or Windows; the tests there use the fake tree.
- The transcript format is Claude Code's internal JSONL, which can change. The raw `.gz` is always a full
  copy, so a digest that misses something can be rebuilt from it.
- The first run over a large history parses every transcript and can take a while (about 30 seconds for
  ~2,000 transcripts in the test above). Later runs skip what they already checked.

## Credits

The idea comes from Austin Marchese's video
["How to Build A Self-Improving System with Claude"](https://www.youtube.com/watch?v=2fc0NX9vIJ8), where he
suggests a skill called "sync Claude sessions" that brings past conversation history into the project.

## License

MIT

Built with Claude Code
