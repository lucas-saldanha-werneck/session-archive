# Changelog

Versions are the `version` in `.claude-plugin/plugin.json`. Newest first.

## 0.2.7 (2026-11-13)

- Skill schema and score: add version and tags, a Purpose section, Prerequisites, Limitations and Troubleshooting; third-person description; add SkillEvaluator badges.

## 0.2.6 (2026-11-13)

- Add author metadata, Instructions and Examples sections to skills.

## 0.2.5 (2026-11-12)

- Audit round 2 fixes.

## 0.2.4 (2026-11-11)

- Point to the catalog repo's new name, lucas-tools.

## 0.2.3 (2026-11-11)

- Rename the marketplace to lucas-tools.

## 0.2.2 (2026-11-11)

- Archive a session once when its project folder moved.

## 0.2.1 (2026-11-09)

- Polish: short description, catalog install, settings headings.

## 0.2.0 (2026-11-08)

- Config options for existing archives: digest labels (read and write), state and skip-list paths, index/log templates, pre/post commands.
- Review fixes: range separator read back; digest format and templates checked at load; post-write check requires this session and range and removes a failed pair; type checks with clear errors; exclude "^" refused; post_command runs after the lock is released; counts computed once; distill takes the digest config.
- Create your config file on first run: SessionStart hook and the first run seed config.json with every default (session-archive seed).
- Review: never seed a relative override path (it would land in the current project folder).

## 0.1.0 (2026-11-08)

- Archive Claude Code sessions as digest + gzipped transcript, idempotent.
- Make install.sh executable.

