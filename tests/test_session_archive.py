#!/usr/bin/env python3
"""Tests for bin/session-archive against a fake ~/.claude/projects tree in a temp folder."""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "session-archive")

S_MAIN = "11111111-1111-4111-8111-111111111111"
S_SMALL = "22222222-2222-4222-8222-222222222222"
S_SUB = "33333333-3333-4333-8333-333333333333"
S_LIVE = "44444444-4444-4444-8444-444444444444"
S_TMP = "55555555-5555-4555-8555-555555555555"


def line(typ, text=None, ts="2026-03-04T10:00:00Z", sidechain=False, content=None, **extra):
    msg = {"role": typ, "content": content if content is not None else text}
    d = {"type": typ, "timestamp": ts, "cwd": "/work/demo", "sessionId": "x", "isSidechain": sidechain,
         "message": msg}
    d.update(extra)
    return json.dumps(d)


def conversation(turns, pad=0, sidechain=False, first="Refactor the parser module please"):
    out = [json.dumps({"type": "custom-title", "customTitle": "Parser refactor"})] if not sidechain else []
    for i in range(turns):
        out.append(line("user", first if i == 0 else f"Next step {i}. " + "x" * pad, sidechain=sidechain))
        out.append(line("assistant", content=[{"type": "text", "text": f"Done with step {i}."},
                                              {"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {}}],
                        sidechain=sidechain))
        out.append(line("user", content=[{"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}],
                        sidechain=sidechain))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.projects = os.path.join(self.home, ".claude", "projects")
        self.out = os.path.join(self.tmp, "archive")
        # XDG_CONFIG_HOME is dropped too: the first run creates the config file, and it must land in the temp HOME
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("SESSION_ARCHIVE") and k not in ("CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME")}
        self.env.update({"HOME": self.home, "USERPROFILE": self.home, "SESSION_ARCHIVE_DIR": self.out,
                         "PYTHONIOENCODING": "utf-8"})
        os.makedirs(self.projects)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_session(self, sid, lines, project="-work-demo", age=600):
        d = os.path.join(self.projects, project)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, sid + ".jsonl")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        t = time.time() - age
        os.utime(p, (t, t))
        return p

    def cli(self, *args, ok=True):
        r = subprocess.run([sys.executable, CLI, *args], env=self.env, capture_output=True, text=True,
                           encoding="utf-8")
        if ok and r.returncode != 0:
            self.fail(f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        return r

    def run_json(self, *args):
        return json.loads(self.cli("run", "--json", *args).stdout)

    def pairs(self):
        return sorted(f for f in os.listdir(self.out) if f.endswith(".digest.md")) if os.path.isdir(self.out) else []


class TestArchive(Base):
    def fixture(self):
        self.main = self.write_session(S_MAIN, conversation(12, pad=5000))
        self.write_session(S_SMALL, conversation(3))
        self.write_session(S_SUB, conversation(12, pad=5000, sidechain=True))
        self.write_session(S_LIVE, conversation(12, pad=5000), age=10)
        self.write_session(S_TMP, conversation(12, pad=5000), project="-private-tmp-scratch")

    def test_run_archives_and_skips_with_reasons(self):
        self.fixture()
        rep = self.run_json()
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(len(rep["written"]), 1)
        reasons = {s["session"]: s["reason"] for s in rep["skipped"]}
        self.assertEqual(reasons, {S_SMALL: "trivial", S_SUB: "subagent", S_LIVE: "live"})
        self.assertNotIn(S_TMP, json.dumps(rep), "temp-folder projects are excluded")

        base = rep["written"][0]
        self.assertEqual(base, "2026-03-04_parser-refactor")
        with gzip.open(os.path.join(self.out, base + ".jsonl.gz"), "rb") as f:
            raw = f.read()
        with open(self.main, "rb") as f:
            self.assertEqual(raw, f.read(), "the .gz holds the transcript byte for byte")
        with open(os.path.join(self.out, base + ".digest.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn(f"**Session:** `{S_MAIN}`", md)
        self.assertIn("**Lines:** 1-37", md)
        self.assertIn("**User turns:** 12", md)
        self.assertIn("<!-- TLDR: not written yet -->", md)
        self.assertIn("**[USER]**\n\nRefactor the parser module please", md)
        self.assertIn("**[CLAUDE]**\n\nDone with step 0.", md)
        self.assertIn("tool call(s) and result(s) omitted", md)
        self.assertNotIn('"tool_result"', md)
        with open(os.path.join(self.out, "INDEX.md"), encoding="utf-8") as f:
            self.assertIn(f"[{base}]({base}.digest.md)", f.read())
        with open(os.path.join(self.out, "log.md"), encoding="utf-8") as f:
            self.assertIn("archived 1 pair(s)", f.read())

    def test_idempotent_second_run_writes_nothing(self):
        self.fixture()
        self.run_json()
        before = sorted(os.listdir(self.out))
        rep = self.run_json()
        self.assertEqual(rep["written"], [])
        self.assertEqual({s["reason"] for s in rep["skipped"]}, {"live"},
                         "trivial and subagent sessions are remembered and not re-checked while unchanged")
        self.assertEqual(sorted(os.listdir(self.out)), before)

    def test_continuation_holds_only_new_lines(self):
        self.fixture()
        self.run_json()
        extra = [line("user", "One more question about the parser"), line("assistant", "Here is the answer.")]
        with open(self.main, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(extra) + "\n")
        t = time.time() - 600
        os.utime(self.main, (t, t))
        rep = self.run_json()
        self.assertEqual(rep["written"], ["2026-03-04_parser-refactor-cont-1"])
        gz = os.path.join(self.out, "2026-03-04_parser-refactor-cont-1.jsonl.gz")
        with gzip.open(gz, "rb") as f:
            self.assertEqual(f.read().decode().splitlines(), extra)
        with open(gz[:-len(".jsonl.gz")] + ".digest.md", encoding="utf-8") as f:
            md = f.read()
        self.assertIn("**Lines:** 38-39", md)
        self.assertIn("**Continues:** 2026-03-04_parser-refactor.digest.md", md)
        self.assertIn("One more question about the parser", md)
        self.assertNotIn("Refactor the parser module please", md)
        self.assertEqual(self.run_json()["written"], [], "after the continuation nothing is pending")
        self.assertEqual(self.cli("verify").returncode, 0)

    def test_broken_copy_is_reported_and_rearchived(self):
        self.fixture()
        base = self.run_json()["written"][0]
        with open(os.path.join(self.out, base + ".jsonl.gz"), "wb") as f:
            f.write(b"not gzip")
        r = self.cli("verify", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("corrupt gzip", r.stdout)
        rep = self.run_json()
        self.assertEqual(rep["written"], [base + "-2"], "the session goes back to the queue under a new name")

    def test_trivial_session_that_grows_is_rechecked(self):
        p = self.write_session(S_SMALL, conversation(3))
        self.assertEqual(self.run_json()["written"], [])
        self.write_session(S_SMALL, conversation(12, pad=5000))
        self.assertEqual(len(self.run_json()["written"]), 1)
        self.assertTrue(os.path.exists(p))

    def test_limit_dry_run_and_thresholds(self):
        for i in range(3):
            sid = f"6666666{i}-6666-4666-8666-666666666666"
            self.write_session(sid, conversation(12, pad=5000, first=f"Task number {i} about widgets"),
                               age=600 + 100 * (3 - i))
        r = self.cli("run", "--dry-run")
        self.assertIn("dry run: would write 3 pair(s)", r.stdout)
        self.assertEqual(self.pairs(), [])
        rep = self.run_json("--limit", "2")
        self.assertEqual(rep["status"], "partial")
        self.assertEqual(rep["left"], 1)
        self.assertEqual(len(rep["written"]), 2)
        rep = self.run_json()
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(len(self.pairs()), 3)

    def test_min_turns_flag_and_config_file(self):
        self.write_session(S_SMALL, conversation(3))
        self.assertEqual(len(self.run_json("--min-turns", "2", "--min-kb", "0")["written"]), 1)
        # config file sets a different output folder
        other = os.path.join(self.tmp, "other-archive")
        cfg = os.path.join(self.tmp, "config.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"out_dir": other, "min_turns": 1, "min_kb": 0}, f)
        del self.env["SESSION_ARCHIVE_DIR"]
        self.env["SESSION_ARCHIVE_CONFIG"] = cfg
        rep = self.run_json()
        self.assertEqual(rep["out"], other)
        self.assertEqual(len(rep["written"]), 1)

    def test_default_out_dir_is_in_home(self):
        del self.env["SESSION_ARCHIVE_DIR"]
        self.write_session(S_MAIN, conversation(12, pad=5000))
        rep = self.run_json()
        self.assertEqual(rep["out"], os.path.join(self.home, "claude-session-archive"))

    def test_plan_writes_nothing(self):
        self.fixture()
        r = self.cli("plan")
        self.assertIn("new: 1", r.stdout)
        self.assertIn("trivial", r.stdout)
        self.assertFalse(os.path.exists(self.out))

    def test_status_gap_warning(self):
        self.fixture()
        r = self.cli("status")
        self.assertIn("no successful run yet", r.stdout)
        self.run_json()
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        with open(os.path.join(self.home, ".claude", "settings.json"), "w") as f:
            json.dump({"cleanupPeriodDays": 30}, f)
        runs = os.path.join(self.out, ".state", "runs.jsonl")
        with open(runs, "w") as f:
            f.write(json.dumps({"at": "2020-01-01T00:00:00Z", "status": "ok"}) + "\n")
        r = self.cli("status")
        self.assertIn("GAP RISK", r.stdout)

    def test_lock_blocks_a_second_run(self):
        os.makedirs(os.path.join(self.out, ".state"))
        open(os.path.join(self.out, ".state", "lock"), "w").close()
        r = self.cli("run", ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn("another run", r.stderr)

    def test_no_projects_folder(self):
        shutil.rmtree(self.projects)
        rep = self.run_json()
        self.assertEqual(rep["written"], [])


class TestConfigOptions(Base):
    """Every option added for archives that already exist in another format or share files with other tools."""

    def config(self, **cfg):
        path = os.path.join(self.tmp, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        self.env["SESSION_ARCHIVE_CONFIG"] = path

    def read(self, name):
        with open(os.path.join(self.out, name), encoding="utf-8") as f:
            return f.read()

    def existing_pair(self, sid, base, lines_field=None, session_line=None, n=None):
        """A pair written by some other tool, in another label format."""
        os.makedirs(self.out, exist_ok=True)
        src = os.path.join(self.projects, "-work-demo", sid + ".jsonl")
        with open(src, "rb") as f:
            raw = f.readlines()
        n = n or len(raw)
        with gzip.open(os.path.join(self.out, base + ".jsonl.gz"), "wb") as f:
            f.write(b"".join(raw[:n]))
        head = ["# " + base, "", "- **Datum:** 2026-03-04", session_line or f"- **Sitzung:** {sid}"]
        if lines_field:
            head.append(lines_field)
        with open(os.path.join(self.out, base + ".digest.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(head) + "\n")

    def test_read_labels_recognize_an_existing_archive(self):
        self.main = self.write_session(S_MAIN, conversation(12, pad=5000))
        self.existing_pair(S_MAIN, "2026-03-04_old")
        # default labels do not know "Sitzung": the session looks new
        self.assertIn("new: 1", self.cli("plan").stdout)
        self.config(digest={"labels": {"session": ["Sitzung", "Session"], "lines": ["Zeilen", "Lines"]}})
        r = self.cli("plan")
        self.assertIn("already archived sessions: 1", r.stdout)
        self.assertIn("new: 0", r.stdout)

    def test_lines_label_with_bullet_and_en_dash_drives_continuations(self):
        self.main = self.write_session(S_MAIN, conversation(12, pad=5000))
        self.existing_pair(S_MAIN, "2026-03-04_old", lines_field="- **Zeilen:** 1–20", n=20)
        self.config(digest={"labels": {"session": "Sitzung", "lines": "Zeilen"}})
        p = json.loads(self.cli("plan", "--json").stdout)
        self.assertEqual([(x["from"], x["to"]) for x in p["continued"]], [(21, 37)])

    def test_write_labels_order_prefix_headings_and_speakers(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(digest={
            "labels": {"date": "Datum", "session": ["Sitzung", "Session"], "project": None, "lines": "Zeilen",
                       "user_turns": None, "archived": None, "compactions": "Kompaktierung"},
            "fields": ["date", "session", "lines", "source", "compactions"],
            "field_prefix": "- ", "session_format": "{id}", "range_separator": "–", "none": "(keine)",
            "headings": {"conversation": "Gespraech"}, "speakers": {"user": "ICH"}, "speaker_inline": True})
        base = self.run_json()["written"][0]
        md = self.read(base + ".digest.md")
        head = md.split("\n\n## ")[0].splitlines()[2:]
        self.assertEqual([h.split(":**")[0] for h in head],
                         ["- **Datum", "- **Sitzung", "- **Zeilen", "- **Source", "- **Kompaktierung"])
        self.assertIn(f"- **Sitzung:** {S_MAIN}\n", md)
        self.assertIn("- **Zeilen:** 1–37\n", md)
        self.assertIn("- **Kompaktierung:** (keine)", md)
        self.assertNotIn("Project", md)
        self.assertIn("## Gespraech", md)
        self.assertIn("**[ICH]** Refactor the parser module please", md)
        self.assertIn("**[CLAUDE]** Done with step 0.", md)
        self.assertEqual(self.run_json()["written"], [], "what it wrote, it reads back")
        self.assertEqual(self.cli("verify").returncode, 0)

    def test_empty_session_label_and_unknown_keys_are_rejected(self):
        self.config(digest={"labels": {"session": None}})
        r = self.cli("plan", ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("digest.labels.session", r.stderr)
        self.config(digest={"labels": {"sesion": "x"}})
        self.assertIn("unknown digest.labels", self.cli("plan", ok=False).stderr)

    def test_state_dir_and_shared_skipped_file_with_short_hashes(self):
        self.write_session(S_SMALL, conversation(3))
        state = os.path.join(self.tmp, "state")
        shared = os.path.join(self.tmp, "ledger", "skipped.jsonl")
        self.config(state_dir=state, skipped_file=shared, skipped_hash_chars=16)
        self.run_json()
        with open(shared, encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual(len(rec["sha256"]), 16)
        self.assertTrue(os.path.exists(os.path.join(state, "runs.jsonl")))
        self.assertFalse(os.path.exists(os.path.join(self.out, ".state")))
        # a record from another tool: short hash, no mtime -> still recognized as unchanged
        with open(shared, "w", encoding="utf-8") as f:
            f.write(json.dumps({"session": S_SMALL, "reason": "trivial", "size": rec["size"],
                                "sha256": rec["sha256"]}) + "\n")
        self.assertEqual(self.run_json()["skipped"], [])

    def test_exclude_prefix_pattern(self):
        self.write_session(S_MAIN, conversation(12, pad=5000), project="-var-folders-x-T-tmp-abc")
        self.write_session(S_TMP, conversation(12, pad=5000), project="-tmp-thing")
        self.config(exclude=["^-tmp-"])
        rep = self.run_json()
        self.assertEqual(len(rep["written"]), 1, "'-tmp-' in the middle is kept, at the start it is excluded")
        self.assertNotIn(S_TMP, json.dumps(rep))

    def test_index_and_log_files_templates_and_position(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        log = os.path.join(self.tmp, "wiki", "log.md")
        os.makedirs(os.path.dirname(log))
        with open(log, "w", encoding="utf-8") as f:
            f.write("# Log\n\n## older entry\n")
        self.env["RUN_TAG"] = "r42"
        self.config(index_file="catalog.md", index_header="", index_heading="## Run {today} {env[RUN_TAG]}",
                    index_line="* `{base}` ({user_turns}){continuation_note}", log_file=log,
                    log_position="top", log_heading="## [{today}] {count} new={new} cont={continued}",
                    log_item="  - {base}")
        base = self.run_json()["written"][0]
        idx = self.read("catalog.md")
        self.assertIn(" r42\n", idx)
        self.assertIn(f"* `{base}` (12)\n", idx)
        self.assertFalse(os.path.exists(os.path.join(self.out, "INDEX.md")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "log.md")))
        with open(log, encoding="utf-8") as f:
            body = f.read()
        self.assertTrue(body.startswith("# Log\n\n## ["), body)
        self.assertIn("1 new=1 cont=0\n\n  - " + base, body)
        self.assertTrue(body.rstrip().endswith("## older entry"))

    def test_index_and_log_can_be_turned_off(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(index_file=None, log_file="")
        self.assertEqual(len(self.run_json()["written"]), 1)
        self.assertEqual(sorted(f for f in os.listdir(self.out) if f.endswith(".md") and ".digest" not in f), [])

    def test_bad_template_is_reported(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(index_line="- {nope}")
        r = self.cli("run", ok=False)
        self.assertIn("index_line template", r.stderr)

    def test_pre_command_failure_stops_the_run(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(pre_command=[sys.executable, "-c", "import sys; sys.exit(3)"])
        r = self.cli("run", ok=False)
        self.assertEqual(r.returncode, 4)
        self.assertIn("pre_command exited 3", r.stderr)
        self.assertEqual(self.pairs(), [])

    def test_post_command_gets_the_report(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        seen = os.path.join(self.tmp, "seen.json")
        code = ("import json, os; json.dump({k: v for k, v in os.environ.items() "
                "if k.startswith('SESSION_ARCHIVE_')}, open(%r, 'w'))" % seen)
        self.config(pre_command=[sys.executable, "-c", "pass"], post_command=[sys.executable, "-c", code])
        self.run_json()
        with open(seen, encoding="utf-8") as f:
            env = json.load(f)
        self.assertEqual((env["SESSION_ARCHIVE_STATUS"], env["SESSION_ARCHIVE_WRITTEN"],
                          env["SESSION_ARCHIVE_NEW"], env["SESSION_ARCHIVE_LEFT"]), ("ok", "1", "1", "0"))
        with open(env["SESSION_ARCHIVE_REPORT"], encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["written"]), 1)

    def test_post_command_failure_is_an_error_exit(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(post_command=[sys.executable, "-c", "import sys; sys.exit(2)"])
        r = self.cli("run", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("post_command exited 2", r.stderr)
        self.assertEqual(len(self.pairs()), 1, "the pairs are kept; only the hook failed")

    def test_shell_string_hook(self):
        if os.name == "nt":
            self.skipTest("a string hook runs through cmd.exe on Windows; the list form is tested everywhere")
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(post_command='echo "$SESSION_ARCHIVE_STATUS" > hook.txt')
        r = subprocess.run([sys.executable, CLI, "run"], env=self.env, cwd=self.tmp, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.tmp, "hook.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "ok")


class TestReviewFixes(TestConfigOptions):
    """Regression tests for the review of the config options."""

    def no_files(self):
        return not os.path.isdir(self.out) or not [f for f in os.listdir(self.out) if f.endswith((".md", ".gz"))]

    def test_custom_range_separator_is_read_back(self):
        self.main = self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(digest={"range_separator": " to "})
        self.run_json()
        with open(self.main, "a", encoding="utf-8", newline="\n") as f:
            f.write(line("user", "One more question") + "\n" + line("assistant", "Answer.") + "\n")
        t = time.time() - 600
        os.utime(self.main, (t, t))
        self.assertEqual(self.run_json()["written"], ["2026-03-04_parser-refactor-cont-1"])
        self.assertIn("**Lines:** 38 to 39", self.read("2026-03-04_parser-refactor-cont-1.digest.md"))
        self.assertEqual(self.run_json()["written"], [], "the continuation's range is read back")

    def test_unreadable_digest_format_is_refused_before_writing(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(digest={"session_format": "id={id}"})
        r = self.cli("plan", ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("read back", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotEqual(self.cli("run", ok=False).returncode, 0)
        self.assertTrue(self.no_files(), "no orphan pair")

    def test_label_clash_that_misreads_lines_is_refused(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.config(digest={"labels": {"date": "Lines"}})  # "Lines: 2026-03-04" would read as range 2026-3
        r = self.cli("run", ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("read back", r.stderr)
        self.assertTrue(self.no_files())

    def test_post_write_check_removes_the_pair(self):
        import importlib.machinery
        import types
        self.write_session(S_MAIN, conversation(12, pad=5000))
        os.makedirs(self.out)
        old = dict(os.environ)
        os.environ.update(self.env)
        try:
            sa = types.ModuleType("sa")
            importlib.machinery.SourceFileLoader("sa", CLI).exec_module(sa)
            c = sa.load_config(types.SimpleNamespace(out=None, projects=None, min_turns=None, min_kb=None,
                                                     live_minutes=None))
            c["digest"]["write"]["date"] = "Lines"  # break it after the load-time check
            item = sa.plan(c)["new"][0]
            with self.assertRaises(RuntimeError):
                sa.write_pair(c, item)
        finally:
            os.environ.clear()
            os.environ.update(old)
        self.assertTrue(self.no_files(), "both files of a pair that fails the read-back are removed")

    def test_templates_are_checked_before_writing(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        for key, tpl in (("index_line", "- {nope}"), ("log_item", "{base.upper}x{date.x}"),
                         ("log_heading", "{0}"), ("index_heading", "{env.x}")):
            self.config(**{key: tpl})
            r = self.cli("plan", ok=False)
            self.assertNotEqual(r.returncode, 0, key)
            self.assertIn(key, r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertNotEqual(self.cli("run", ok=False).returncode, 0)
            self.assertTrue(self.no_files(), key)

    def test_wrong_types_are_clear_errors(self):
        cases = [{"skipped_hash_chars": -1}, {"skipped_hash_chars": "abc"}, {"skipped_hash_chars": 0},
                 {"exclude": "tmp"}, {"exclude": [3]}, {"exclude": ["^"]}, {"index_line": 5},
                 {"state_dir": 5}, {"min_turns": "x"}, {"pre_command": 5}, {"post_command": {"a": 1}},
                 {"post_command": []}, {"log_position": 1}, {"digest": {"speaker_inline": "yes"}},
                 {"digest": {"labels": {"session": 5}}}, {"digest": {"range_separator": ""}},
                 {"digest": {"fields": "date"}}]
        for cfg in cases:
            self.config(**cfg)
            r = self.cli("plan", ok=False)
            self.assertNotEqual(r.returncode, 0, cfg)
            self.assertNotIn("Traceback", r.stderr, cfg)
            key = list(cfg)[0] if list(cfg)[0] != "digest" else "digest"
            self.assertIn(key, r.stderr, cfg)

    def test_post_command_runs_after_the_lock_is_released(self):
        self.write_session(S_MAIN, conversation(12, pad=5000))
        code = ("import os, sys; sys.exit(1 if os.path.exists("
                "os.path.join(os.environ['SESSION_ARCHIVE_STATE'], 'lock')) else 0)")
        self.config(post_command=[sys.executable, "-c", code])
        r = self.cli("run", ok=False)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestSeed(Base):
    """First run: the config file is created with every default, never overwritten, and behaves like none."""

    def default_cfg(self):
        return os.path.join(self.home, ".config", "session-archive", "config.json")

    def read_bytes(self, path):
        with open(path, "rb") as f:
            return f.read()

    def test_seed_creates_the_starter_silently(self):
        r = self.cli("seed", "--quiet")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        with open(os.path.join(ROOT, "config.example.json"), "rb") as f:
            example = f.read().replace(b"\r\n", b"\n")
        self.assertEqual(self.read_bytes(self.default_cfg()), example,
                         "the seeded file is config.example.json, byte for byte")

    def test_starter_holds_every_key_at_its_default(self):
        self.cli("seed", "--quiet")
        with open(self.default_cfg(), encoding="utf-8") as f:
            cfg = json.load(f)
        keys = set(cfg) - {"_doc"}
        self.assertEqual(keys, set(cfg["_doc"]) - {"about"}, "every key has a note")
        self.assertEqual(cfg["min_turns"], 10)
        self.assertEqual(cfg["exclude"], ["-private-tmp-", "-tmp-", "scratchpad"])
        self.assertIsNone(cfg["out_dir"])

    def test_existing_file_is_byte_identical(self):
        path = self.default_cfg()
        os.makedirs(os.path.dirname(path))
        mine = b'{"min_turns": 3, "min_kb": 0}\n'
        with open(path, "wb") as f:
            f.write(mine)
        self.assertEqual(self.cli("seed").stdout.strip(), f"kept {path}")
        self.write_session(S_MAIN, conversation(4))
        rep = self.run_json()
        self.assertEqual(len(rep["written"]), 1, "the user's min_turns still applies")
        self.cli("status")
        self.assertEqual(self.read_bytes(path), mine)

    def test_first_run_creates_it_and_plan_or_dry_run_do_not(self):
        self.cli("plan")
        self.cli("run", "--dry-run")
        self.assertFalse(os.path.exists(self.default_cfg()))
        self.cli("run")
        self.assertTrue(os.path.isfile(self.default_cfg()))

    def test_env_overrides_are_respected(self):
        self.env["XDG_CONFIG_HOME"] = os.path.join(self.tmp, "xdg")
        self.cli("seed", "--quiet")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "xdg", "session-archive", "config.json")))
        self.env["SESSION_ARCHIVE_CONFIG"] = os.path.join(self.tmp, "mine", "sa.json")
        self.cli("seed", "--quiet")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "mine", "sa.json")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config")))

    def test_unwritable_location_never_crashes(self):
        with open(os.path.join(self.tmp, "afile"), "w") as f:
            f.write("x")
        self.env["SESSION_ARCHIVE_CONFIG"] = os.path.join(self.tmp, "afile", "config.json")
        r = self.cli("seed", "--quiet")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        r = self.cli("seed", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("could not create", r.stderr)
        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.assertEqual(len(self.run_json()["written"]), 1, "run still works without a config file")

    def test_relative_config_path_is_not_seeded(self):
        self.env["SESSION_ARCHIVE_CONFIG"] = os.path.join("rel", "config.json")
        cwd = os.path.join(self.tmp, "cwd")
        os.makedirs(cwd)
        r = subprocess.run([sys.executable, CLI, "seed", "--quiet"], env=self.env, cwd=cwd, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(os.listdir(cwd), [], "nothing written into the current folder")

    def test_read_only_folder_never_crashes(self):
        ro = os.path.join(self.tmp, "ro")
        os.makedirs(ro)
        os.chmod(ro, 0o555)
        try:
            if os.name == "nt" or os.access(ro, os.W_OK):
                self.skipTest("this user can write to a read-only folder (Windows or root)")
            self.env["XDG_CONFIG_HOME"] = ro
            r = self.cli("seed", "--quiet")
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
            self.assertFalse(os.path.exists(os.path.join(ro, "session-archive")))
            self.cli("status")
        finally:
            os.chmod(ro, 0o755)

    def test_seeded_config_behaves_like_no_config(self):
        """Same sessions archived twice, once with no config file at all and once with the seeded one: the
        plan, the run report and every file written are the same."""
        import re

        def archive(label, seeded):
            out = os.path.join(self.tmp, label)
            self.env["SESSION_ARCHIVE_DIR"] = out
            if seeded:
                self.env["SESSION_ARCHIVE_CONFIG"] = os.path.join(self.tmp, label + "-config.json")
                self.cli("seed", "--quiet")
                self.assertTrue(os.path.isfile(self.env["SESSION_ARCHIVE_CONFIG"]))
            else:  # a config path that can never exist
                with open(os.path.join(self.tmp, "nofile"), "w") as f:
                    f.write("x")
                self.env["SESSION_ARCHIVE_CONFIG"] = os.path.join(self.tmp, "nofile", "config.json")

            def norm(t):
                for form in (json.dumps(out)[1:-1], out, out.replace(os.sep, "/")):
                    t = t.replace(form, "<out>")
                return re.sub(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d(:\d\d)?(\.\d+)?(Z|[+-]\d\d:\d\d)?", "<time>", t)

            result = [norm(self.cli("plan", "--json").stdout), norm(self.cli("run", "--json").stdout)]
            for root, _, files in os.walk(out):
                for name in sorted(files):
                    p = os.path.join(root, name)
                    rel = os.path.relpath(p, out)
                    if name.endswith(".gz"):
                        with gzip.open(p, "rb") as f:
                            result.append((rel, f.read()))
                    elif not rel.startswith(".state"):
                        with open(p, encoding="utf-8") as f:
                            result.append((rel, norm(f.read())))
            return sorted(result, key=str)

        self.write_session(S_MAIN, conversation(12, pad=5000))
        self.write_session(S_SMALL, conversation(3))
        self.write_session(S_TMP, conversation(12, pad=5000), project="-private-tmp-scratch")
        none, seeded = archive("none", False), archive("seeded", True)
        self.assertGreater(len(none), 4)
        self.assertEqual(none, seeded)

    def test_a_failed_write_leaves_no_config_behind(self):
        """The starter is written elsewhere first: an error mid-write never leaves a broken config.json."""
        code = ("import importlib.machinery, importlib.util, sys\n"
                "ld = importlib.machinery.SourceFileLoader('sa', sys.argv[1])\n"
                "m = importlib.util.module_from_spec(importlib.util.spec_from_loader('sa', ld))\n"
                "ld.exec_module(m)\n"
                "m.starter_text = lambda: '{\"min_turns\": 10, \"bad\": \"' + chr(0xD800) + '\"}'\n"
                "print(m.seed_config()[0])\n")
        r = subprocess.run([sys.executable, "-c", code, CLI], env=self.env, capture_output=True, text=True,
                           encoding="utf-8")
        self.assertEqual(r.stdout.strip(), "failed", r.stderr)
        folder = os.path.dirname(self.default_cfg())
        self.assertEqual(os.listdir(folder) if os.path.isdir(folder) else [], [], "no config, no temp file")
        self.assertEqual(self.cli("seed").stdout.strip(), f"created {self.default_cfg()}", "the next seed works")

    def test_tilde_in_config_path_and_seed_json(self):
        self.env["SESSION_ARCHIVE_CONFIG"] = "~/dotfiles/sa.json"
        r = self.cli("seed", "--json")
        made = os.path.join(self.home, "dotfiles", "sa.json")
        self.assertEqual(json.loads(r.stdout), {"state": "created", "path": made, "error": None})
        with open(made, "w", encoding="utf-8") as f:
            json.dump({"min_turns": 3, "min_kb": 0}, f)
        self.write_session(S_MAIN, conversation(4))
        self.assertEqual(len(self.run_json()["written"]), 1, "the file named with ~ is the one read")

    def test_hook_runs_the_seed(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            hook = json.load(f)["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/bin/session-archive" seed --quiet', hook["command"])
        self.assertTrue(hook["command"].rstrip().endswith("exit 0"), "never a failing exit code at session start")
        self.assertIn("seed --quiet || python ", hook["command"], "python only when python3 fails, not every time")


class TestInstall(Base):
    def sh(self, *args):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not found")
        env = dict(self.env)
        env["PATH"] = os.path.join(self.tmp, "fakebin") + os.pathsep + env.get("PATH", "")
        os.makedirs(os.path.join(self.tmp, "fakebin"), exist_ok=True)
        log = os.path.join(self.tmp, "launchctl.log")
        with open(os.path.join(self.tmp, "fakebin", "launchctl"), "w", newline="\n") as f:
            f.write(f'#!/bin/sh\necho "$@" >> "{log.replace(os.sep, "/")}"\n')
        os.chmod(os.path.join(self.tmp, "fakebin", "launchctl"), 0o755)
        return subprocess.run([bash, os.path.join(ROOT, "install.sh"), *args], env=env, capture_output=True,
                              text=True, encoding="utf-8")

    def test_install_dry_run_writes_nothing(self):
        r = self.sh("--dry-run", "--schedule", "--os", "macos")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("com.claude-tools.session-archive", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local")))
        self.assertFalse(os.path.exists(os.path.join(self.home, "Library")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config")))

    def test_install_schedule_macos_and_uninstall(self):
        r = self.sh("--schedule", "--os", "macos", "--no-load")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.home, ".local", "bin", "session-archive")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".config", "session-archive", "config.json")),
                        "install also seeds the config file")
        plist = os.path.join(self.home, "Library", "LaunchAgents", "com.claude-tools.session-archive.plist")
        with open(plist, encoding="utf-8") as f:
            body = f.read()
        self.assertIn(self.out, body)
        self.assertIn("<string>run</string>", body)
        r = self.sh("--uninstall", "--os", "macos", "--no-load")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(plist))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local", "bin", "session-archive")))

    def test_install_linux_prints_cron_line(self):
        r = self.sh("--schedule", "--os", "linux")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("crontab", r.stdout)
        self.assertIn("session-archive run", r.stdout)


if __name__ == "__main__":
    unittest.main()
