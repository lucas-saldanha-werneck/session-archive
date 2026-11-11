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
- **Moved project folders.** Moving a project folder can leave the same session in two folders. A run keeps one
  copy per session id: the biggest one, and waits while any copy is still being written.
- **Broken copies come back.** A missing or corrupt `.gz` is reported by `verify`, and the next `run`
  archives that session again under a new name.
- **Skips have reasons.** `live` (written in the last 2 minutes, picked up next run), `trivial` (fewer than
  10 user turns or under 50 KB), `subagent` (mostly sidechain lines). Trivial and subagent skips are
  remembered and only checked again when the transcript changes.
- **Gap warning.** `status` warns when the last successful run is within 3 days of Claude Code's retention.
- Every pair is read back from disk before it counts. A lock file stops two runs at once.

## Install

```
/plugin marketplace add lucas-saldanha-werneck/claude-plugins
/plugin install session-archive@lucas-plugins
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

## Use

```
session-archive plan                 # what a run would do; writes nothing
session-archive run                  # archive (oldest first, 40 pairs per run; --limit N, --dry-run)
session-archive verify               # check every pair
session-archive status               # archive folder, last run, retention warning
session-archive seed                 # create the config file with every default, if missing (--print shows it)
```

Add `--json` to any command for machine-readable output.

## Settings

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

### Config file

The config file is `~/.config/session-archive/config.json` (or `$XDG_CONFIG_HOME/session-archive/config.json`,
or the file in `$SESSION_ARCHIVE_CONFIG`). The plugin creates it by itself the first time it runs (a
`SessionStart` hook; outside the plugin, the first `session-archive run`, or `session-archive seed`), with every
key set to `null` and a short note per key under `_doc` that shows its current default: the same content as
[`config.example.json`](config.example.json). `null` means "use the built-in default", so that file behaves
exactly like having no config, and a later version that changes a default reaches you too. Replace a `null` to
change that setting. It lives outside
the plugin folder, so `/plugin update` never touches it, and the tool never overwrites or changes a config file
that is already there. The scheduled run from `install.sh` reads the same file.

### More config keys (config file only)

Paths may start with `~`; a relative path is taken from the archive folder (`out_dir` and `projects_dir`: from the
folder the command runs in). Any key set to `null` is the same as leaving it out: the built-in default. `""`
turns `index_file`, `log_file`, `index_header` and `index_heading` off. Inside `digest.labels`, `null` still means
"leave this field out".

| Key | What it does | Default |
|---|---|---|
| `exclude` | Project folder names to skip. A plain entry matches anywhere in the name; `"^x"` matches names that start with `x` | `["-private-tmp-", "-tmp-", "scratchpad"]` |
| `state_dir` | Where run history, the lock and `last-run.json` go | `<archive>/.state` |
| `skipped_file` | The list of sessions skipped on purpose (JSON lines). Point it at a file another tool also keeps | `<state_dir>/skipped.jsonl` |
| `skipped_hash_chars` | How many hex characters of the transcript's sha256 to record. Reading always compares the prefix, so records with shorter hashes from another tool are understood | `64` |
| `index_file` | One line per pair | `INDEX.md` |
| `index_header` | Written once when the index file is created | `# Archived Claude Code sessions` |
| `index_heading` | Template written before each run's lines (empty = none) | `""` |
| `index_line` | Template for each pair's line | `- {date} [{base}]({base}.digest.md) - {project} - {user_turns} user turns{continuation_note}` |
| `index_continuation_note` | What `{continuation_note}` becomes for a continuation pair | `" (continuation)"` |
| `log_file` | One entry per run | `log.md` |
| `log_position` | `end` appends; `top` puts the newest entry first, under the file's `# ` title line | `end` |
| `log_heading` | Template for each run's heading | `## [{now}] archived {count} pair(s)` |
| `log_item` | Template for each pair under the heading | `- {base}` |
| `pre_command` | Runs before `run` archives anything. A string goes through the shell (`/bin/sh`; `cmd.exe` on Windows); a list runs as is. A non-zero exit stops the run (exit code 4) with nothing written | none |
| `post_command` | Runs after `run` has released its lock, with the result in its environment (below). A non-zero exit makes `run` exit 1; the pairs stay | none |
| `digest` | Field labels, order and wording of the digests (below) | English labels |

Template placeholders: `{now}` (local `YYYY-MM-DD HH:MM`), `{today}`, `{count}`, `{new}`, `{continued}`, and
`{env[NAME]}` (an environment variable; empty when unset). Per-pair templates also get `{base}`, `{date}`,
`{project}`, `{user_turns}`, `{lines}`, `{session}`.

Environment of `pre_command` and `post_command`: `SESSION_ARCHIVE_OUT`, `SESSION_ARCHIVE_STATE`; and for
`post_command` also `SESSION_ARCHIVE_STATUS` (`ok`, `partial`, `fail`), `SESSION_ARCHIVE_WRITTEN`,
`SESSION_ARCHIVE_NEW`, `SESSION_ARCHIVE_CONTINUED`, `SESSION_ARCHIVE_LEFT` and `SESSION_ARCHIVE_REPORT` (path of
a JSON file with the run report). Use them to record the run in another tool's ledger, or to refuse to start
while something else is writing to the same folder.

### Digest format (`digest`)

The digest fields are read back to know what is already archived, so an archive written earlier in a
different format (another language, a bullet list, another dash) can be adopted by telling the tool its
labels. Each label can be a string or a list: the first is written, all of them are accepted when reading.

| Key | What it does | Default |
|---|---|---|
| `labels` | Label per field: `date`, `session`, `project`, `source`, `raw_copy`, `lines`, `continues`, `user_turns`, `compactions`, `archived`. `null` leaves a field out. `session` and `lines` cannot be empty | English (`Date`, `Session`, `Lines`, ...) |
| `fields` | Order of the fields in the header (`session` and `lines` are added if missing) | the order above |
| `field_prefix` | Put before each field, such as `"- "` for a bullet list | `""` |
| `session_format` | How the session id is written; `{id}` is the id | `` "`{id}`" `` |
| `range_separator` | Between the two numbers of `lines` (read back as well as written) | `"-"` |
| `none` | Written when there were no compactions | `"(none)"` |
| `headings` | `tldr` and `conversation` section titles | `TL;DR`, `Conversation (text only, tool calls omitted)` |
| `speakers` | `user` and `assistant` names in `**[NAME]**` | `USER`, `CLAUDE` |
| `speaker_inline` | `true` puts the text on the same line as the name | `false` |

Reading is lenient whatever the labels: a field may start with a bullet (`- `, `* `), the id may or may not
be in backticks, and the range may use `-`, `–`, `—` or your `range_separator`.

The config is checked before anything is written: every key's type, every template (formatted with sample
values), and the digest format, by writing a sample header and reading it back. A format whose session id
or line range would not read back (a label used for two fields, an id format the reader cannot find) is
refused with a message saying what read back wrong. Each pair is read back again after it is written; if
that fails, both of its files are removed and the run reports the session as failed.

Example: adopt an archive whose digests look like `- **Sitzung:** <id>` and `- **Zeilen:** 1–40`:

```json
{
  "out_dir": "~/notes/sessions",
  "digest": {
    "labels": { "session": ["Sitzung", "Session"], "lines": ["Zeilen", "Lines"] },
    "field_prefix": "- ", "session_format": "{id}", "range_separator": "–"
  }
}
```

Run `session-archive plan` after changing labels: it writes nothing, and `already archived sessions` should
match the number of sessions your archive already holds.

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
continuations, broken-copy recovery, the run limit, config precedence, the lock, the gap warning, every
config key above (labels read and written, shared skip list, index and log templates, hooks), the first-run
config file (created when missing, an existing file byte-identical, `XDG_CONFIG_HOME` and
`SESSION_ARCHIVE_CONFIG` respected, no crash on a read-only folder, the seeded file giving the same plan, report
and archive as no file), and `install.sh` with a fake `launchctl`.

## Uninstall

```
/plugin uninstall session-archive@lucas-plugins
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
