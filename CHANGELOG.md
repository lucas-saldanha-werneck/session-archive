# Changelog

Versions are the `version` in `.claude-plugin/plugin.json`. Newest first.

## 0.2.7 (2026-11-13)

- Skill: add version and tags, a Purpose section, Prerequisites, Limitations and Troubleshooting; third-person description; SkillEvaluator badges in the README.
- README: demo GIF and badges; add SECURITY.md and this CHANGELOG.

## 0.2.6 (2026-11-13)

- Skill: add author metadata, Instructions and Examples sections (docs only).

## 0.2.5 (2026-11-12)

- Archive files are private (0600, folders 0700) and written atomically.
- A bad text block or a transcript that fails to parse no longer stops the whole run.
- A rewritten transcript is detected and its old pair moved to `.state/superseded`; `verify` reports a .gz without digest and a digest without Session.
- `run --dry-run` creates no folder and takes no lock; an old lock is removed only when its PID is gone.

## 0.2.4 (2026-11-11)

- Point to the catalog repo's new name, `lucas-tools`.

## 0.2.3 (2026-11-11)

- Catalog renamed to `lucas-tools`.

## 0.2.2 (2026-11-11)

- Archive a session once when its project folder moved.

## 0.2.1 (2026-11-09)

- Short description, catalog install steps, settings headings in the README.

## 0.2.0 (2026-11-08)

- Config options for existing archives: digest labels (read and write), state and skip-list paths, index/log templates, pre/post commands.
- Create your config file on the first run (SessionStart hook or first run seeds `config.json`); never seed a relative override path.
- Review fixes: range separator read back; digest format and templates checked at load; post-write check removes a failed pair; `post_command` runs after the lock is released.
- `SESSION_ARCHIVE_CONFIG`: accepts `~` and normalizes the path.
- Make install.sh executable.

## 0.1.0 (2026-11-08)

- Archive Claude Code sessions as digest + gzipped transcript, idempotent.
