#!/usr/bin/env python3
"""Tests for codex-context-bridge. Run: python3 -m unittest discover -s tests"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "codex-context-bridge"


def load_module() -> types.ModuleType:
    loader = importlib.machinery.SourceFileLoader("context_bridge", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules during exec.
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


bridge = load_module()


class BridgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.claude_dir = self.root / "claude-config"
        (self.claude_dir / "projects").mkdir(parents=True)
        self.work = self.root / "work"
        self.work.mkdir()
        # Mirrors the common Codex setup: CLAUDE.md as a native fallback name.
        self.config = bridge.Config(
            trusted_roots=(self.work,),
            claude_config_dir=self.claude_dir,
            codex_fallback_filenames=("CLAUDE.md",),
        )

    def outside_dir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name).resolve()

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def seed_memory(self, directory: Path, text: str) -> Path:
        index = (
            self.claude_dir
            / "projects"
            / bridge.flatten_project_path(directory)
            / "memory"
            / "MEMORY.md"
        )
        return self.write(index, text)

    def scan(self, cwd: Path, **overrides) -> "bridge.Scan":
        return bridge.scan(cwd, replace(self.config, **overrides))

    def render(self, cwd: Path, **overrides) -> str:
        config = replace(self.config, **overrides)
        return bridge.render_context(bridge.scan(cwd, config), config.max_context_chars)


class DiscoveryTests(BridgeTestCase):
    def test_git_root_uses_native_claude_and_injects_local_overlay(self) -> None:
        root = self.work
        (root / ".git").mkdir()
        self.write(root / "CLAUDE.md", "root")
        leaf = root / "category" / "leaf"
        leaf.mkdir(parents=True)
        self.write(root / "category" / "CLAUDE.md", "category")
        self.write(leaf / "CLAUDE.local.md", "local")

        result = self.scan(leaf)

        self.assertEqual(
            list(result.native_selected),
            [root / "CLAUDE.md", root / "category" / "CLAUDE.md"],
        )
        self.assertEqual([i.source for i in result.injected], [leaf / "CLAUDE.local.md"])
        self.assertEqual(result.skipped, ())

    def test_nested_git_root_injects_broad_ancestors(self) -> None:
        root = self.work
        self.write(root / "CLAUDE.md", "root")
        category = root / "work"
        self.write(category / "CLAUDE.md", "work")
        repo = category / "repo"
        (repo / ".git").mkdir(parents=True)
        self.write(repo / "CLAUDE.md", "repo")
        leaf = repo / "src"
        leaf.mkdir()

        result = self.scan(leaf)

        self.assertEqual(result.native_root, repo)
        self.assertEqual(list(result.native_selected), [repo / "CLAUDE.md"])
        self.assertEqual(
            [i.source for i in result.injected], [root / "CLAUDE.md", category / "CLAUDE.md"]
        )

    def test_without_claude_fallback_in_codex_claude_md_below_root_is_injected(self) -> None:
        root = self.work
        (root / ".git").mkdir()
        self.write(root / "CLAUDE.md", "root")

        result = self.scan(root, codex_fallback_filenames=())

        self.assertEqual(result.native_selected, ())
        self.assertEqual([i.source for i in result.injected], [root / "CLAUDE.md"])

    def test_agents_file_stays_native_without_duplicate_claude_injection(self) -> None:
        root = self.work
        (root / ".git").mkdir()
        self.write(root / "AGENTS.md", "native")
        self.write(root / "CLAUDE.md", "shared")

        result = self.scan(root)

        self.assertEqual(list(result.native_selected), [root / "AGENTS.md"])
        self.assertEqual(result.injected, ())

    def test_project_dot_claude_file_is_injected(self) -> None:
        (self.work / ".git").mkdir()
        instruction = self.write(self.work / ".claude" / "CLAUDE.md", "hidden")

        result = self.scan(self.work)

        self.assertEqual([i.source for i in result.injected], [instruction])

    def test_toggles_disable_local_and_dot_claude(self) -> None:
        (self.work / ".git").mkdir()
        self.write(self.work / ".claude" / "CLAUDE.md", "hidden")
        self.write(self.work / "CLAUDE.local.md", "local")

        result = self.scan(self.work, include_local=False, include_dot_claude=False)

        self.assertEqual(result.injected, ())

    def test_custom_root_marker_is_respected(self) -> None:
        self.write(self.work / "CLAUDE.md", "root")
        repo = self.work / "repo"
        self.write(repo / ".hg" / "keep", "")
        result = self.scan(repo, codex_root_markers=(".hg",))
        self.assertEqual(result.native_root, repo)
        self.assertEqual([i.source for i in result.injected], [self.work / "CLAUDE.md"])

    def test_instruction_symlink_escaping_root_is_rejected(self) -> None:
        (self.work / ".git").mkdir()
        secret = self.write(self.outside_dir() / "CLAUDE.local.md", "outside")
        (self.work / "CLAUDE.local.md").symlink_to(secret)

        result = self.scan(self.work)

        self.assertEqual(result.injected, ())
        self.assertEqual(result.skipped[0]["reason"], "symlink target escapes trusted root")

    def test_worktree_git_file_is_a_native_root(self) -> None:
        self.write(self.work / "CLAUDE.md", "root")
        worktree = self.work / "worktree"
        self.write(worktree / ".git", "gitdir: elsewhere")
        self.write(worktree / "CLAUDE.md", "worktree")

        result = self.scan(worktree)

        self.assertEqual(result.native_root, worktree)
        self.assertEqual([i.source for i in result.injected], [self.work / "CLAUDE.md"])

    def test_git_root_above_trusted_root_prevents_duplicate_injection(self) -> None:
        (self.root / ".git").mkdir()
        leaf = self.work / "leaf"
        leaf.mkdir()
        self.write(self.work / "CLAUDE.md", "root")

        result = self.scan(leaf)

        self.assertEqual(result.native_root, self.root)
        self.assertEqual(list(result.native_selected), [self.work / "CLAUDE.md"])
        self.assertEqual(result.injected, ())

    def test_escaping_native_agents_does_not_change_native_selection(self) -> None:
        (self.work / ".git").mkdir()
        outside_agents = self.write(self.outside_dir() / "AGENTS.md", "native outside")
        (self.work / "AGENTS.md").symlink_to(outside_agents)
        self.write(self.work / "CLAUDE.md", "fallback")

        result = self.scan(self.work)

        self.assertEqual(list(result.native_selected), [self.work / "AGENTS.md"])
        self.assertEqual(result.injected, ())
        self.assertIn("native Codex file outside bridge trust", result.skipped[0]["reason"])

    def test_cwd_symlink_escaping_trusted_root_is_not_trusted(self) -> None:
        link = self.work / "escape"
        link.symlink_to(self.outside_dir())

        result = self.scan(link)

        self.assertIsNone(result.trusted_root)
        self.assertEqual(result.injected, ())

    def test_no_trusted_roots_injects_nothing_and_says_why(self) -> None:
        self.write(self.work / "CLAUDE.md", "root")
        result = self.scan(self.work, trusted_roots=())
        self.assertEqual(result.injected, ())
        self.assertIn("no trusted_roots configured", result.notes)


class RulesTests(BridgeTestCase):
    def test_unconditional_rules_injected_scoped_rules_listed(self) -> None:
        (self.work / ".git").mkdir()
        rules = self.work / ".claude" / "rules"
        always = self.write(rules / "style.md", "ALWAYS_RULE")
        scoped = self.write(
            rules / "tex" / "latex.md", '---\npaths:\n  - "**/*.tex"\n---\nTEX_RULE'
        )
        inline = self.write(rules / "py.md", "---\npaths: src/**/*.py\n---\nPY_RULE")

        result = self.scan(self.work)
        context = self.render(self.work)

        self.assertEqual([i.source for i in result.injected], [always])
        self.assertEqual(list(result.scoped_rules), [(inline, "src/**/*.py"), (scoped, "**/*.tex")])
        self.assertIn("ALWAYS_RULE", context)
        self.assertNotIn("TEX_RULE", context)
        self.assertIn(f"- {scoped} (paths: **/*.tex)", context)

    def test_rules_toggle(self) -> None:
        (self.work / ".git").mkdir()
        self.write(self.work / ".claude" / "rules" / "style.md", "ALWAYS_RULE")
        self.assertEqual(self.scan(self.work, include_rules=False).injected, ())


class RenderTests(BridgeTestCase):
    def test_rendered_conflict_order_is_broad_to_deep_with_precedence(self) -> None:
        self.write(self.work / "CLAUDE.md", "PARENT_VALUE")
        repo = self.work / "repo"
        (repo / ".git").mkdir(parents=True)
        self.write(repo / "CLAUDE.md", "CHILD_VALUE")
        self.write(repo / "CLAUDE.local.md", "LOCAL_CHILD_VALUE")

        context = self.render(repo)

        self.assertLess(context.index("PARENT_VALUE"), context.index("LOCAL_CHILD_VALUE"))
        self.assertNotIn("CHILD_VALUE\n", context.replace("LOCAL_CHILD_VALUE", ""))
        self.assertIn("Native Codex instructions remain authoritative", context)

    def test_safe_instruction_symlink_keeps_source_label_and_reads_resolved(self) -> None:
        (self.work / ".git").mkdir()
        target = self.write(self.work / "shared-instructions.md", "RESOLVED_INSTRUCTION")
        source = self.work / "CLAUDE.local.md"
        source.symlink_to(target)

        result = self.scan(self.work)
        context = self.render(self.work)

        self.assertEqual(result.injected[0].source, source)
        self.assertEqual(result.injected[0].resolved, target)
        self.assertIn(f"## Source: {source}", context)
        self.assertIn("RESOLVED_INSTRUCTION", context)

    def test_deepest_files_win_under_cap(self) -> None:
        self.write(self.work / "CLAUDE.md", "SHALLOW" + "x" * 3000)
        leaf = self.work / "leaf"
        self.write(leaf / "CLAUDE.md", "DEEP" + "y" * 3000)

        context = self.render(leaf, codex_fallback_filenames=(), max_context_chars=5000)

        self.assertIn("DEEP", context)
        self.assertNotIn("SHALLOW", context)
        self.assertIn(f"Omitted over context cap: {self.work / 'CLAUDE.md'}", context)


class MemoryTests(BridgeTestCase):
    def test_flatten_matches_claude_code(self) -> None:
        self.assertEqual(
            bridge.flatten_project_path(Path("/Users/a/.local/share/x_y")),
            "-Users-a--local-share-x-y",
        )

    def test_memory_index_for_cwd_is_appended_after_instructions(self) -> None:
        self.write(self.work / "CLAUDE.md", "PARENT_VALUE")
        leaf = self.work / "leaf"
        leaf.mkdir()
        index = self.seed_memory(leaf, "- [note.md](note.md) - hi")

        result = self.scan(leaf)
        context = self.render(leaf)

        self.assertEqual(result.memory_index.source, index)
        self.assertIn(f"# Claude auto-memory index for {leaf}", context)
        self.assertIn(f"linked files live in {index.parent}", context)
        self.assertLess(context.index("PARENT_VALUE"), context.index("auto-memory index"))

    def test_memory_for_dotted_path_is_found(self) -> None:
        leaf = self.work / ".hidden" / "proj"
        leaf.mkdir(parents=True)
        self.seed_memory(leaf, "DOTTED_MEMORY")
        self.assertIn("DOTTED_MEMORY", self.render(leaf))

    def test_cwd_without_memory_index_appends_nothing(self) -> None:
        self.write(self.work / "CLAUDE.md", "PARENT_VALUE")
        leaf = self.work / "leaf"
        leaf.mkdir()
        self.assertNotIn("auto-memory index", self.render(leaf))

    def test_memory_toggle(self) -> None:
        self.seed_memory(self.work, "MEM")
        self.assertIsNone(self.scan(self.work, include_memory=False).memory_index)

    def test_nearest_ancestor_memory_index_is_used(self) -> None:
        middle = self.work / "middle"
        leaf = middle / "leaf"
        leaf.mkdir(parents=True)
        self.seed_memory(self.work, "ROOT_MEMORY")
        nearest = self.seed_memory(middle, "MIDDLE_MEMORY")

        result = self.scan(leaf)
        context = self.render(leaf)

        self.assertEqual(result.memory_index.source, nearest)
        self.assertIn("MIDDLE_MEMORY", context)
        self.assertNotIn("ROOT_MEMORY", context)
        self.assertIn(f"inherited from ancestor {middle}", context)

    def test_memory_outside_trusted_roots_is_not_injected(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        self.seed_memory(outside, "OUTSIDE_MEMORY")

        result = self.scan(outside)

        self.assertIsNone(result.memory_index)
        self.assertEqual(self.render(outside), "")

    def test_memory_symlink_escaping_projects_root_is_rejected(self) -> None:
        leaf = self.work / "leaf"
        leaf.mkdir()
        index = self.seed_memory(leaf, "placeholder")
        index.unlink()
        outside_index = self.write(self.outside_dir() / "MEMORY.md", "OUTSIDE_MEMORY")
        index.symlink_to(outside_index)

        result = self.scan(leaf)

        self.assertIsNone(result.memory_index)
        self.assertNotIn("OUTSIDE_MEMORY", self.render(leaf))
        self.assertEqual(result.skipped[0]["path"], str(index))
        self.assertEqual(result.skipped[0]["reason"], "symlink target escapes trusted root")

    def test_broken_memory_symlink_is_rejected(self) -> None:
        leaf = self.work / "leaf"
        leaf.mkdir()
        index = self.seed_memory(leaf, "placeholder")
        index.unlink()
        index.symlink_to(self.root / "missing-memory-index")

        result = self.scan(leaf)

        self.assertIsNone(result.memory_index)
        self.assertEqual(result.skipped[0]["reason"], "broken symlink")

    def test_memory_omitted_marker_when_no_budget_is_left(self) -> None:
        leaf = self.work / "leaf"
        leaf.mkdir()
        self.seed_memory(leaf, "MEMORY_HEAD")

        result = self.scan(leaf)
        tight = bridge.render_memory_index(result, 120)

        self.assertNotIn("MEMORY_HEAD", tight)
        self.assertIn("auto-memory index omitted", tight)
        self.assertLessEqual(len(tight), 120)
        self.assertEqual(bridge.render_memory_index(result, 5), "")

    def test_oversized_memory_index_is_truncated_not_dropped(self) -> None:
        self.write(self.work / "CLAUDE.md", "PARENT_VALUE")
        leaf = self.work / "leaf"
        leaf.mkdir()
        self.seed_memory(leaf, "MEMORY_HEAD\n" + "x" * 40_000)

        context = self.render(leaf)

        self.assertEqual(len(context), self.config.max_context_chars)
        self.assertIn("PARENT_VALUE", context)
        self.assertIn("MEMORY_HEAD", context)
        self.assertTrue(context.endswith("[truncated]\n"))


class ConfigAndCliTests(BridgeTestCase):
    def env(self, config_text: str, codex_text: str = "") -> dict[str, str]:
        config_path = self.write(self.root / "bridge.toml", config_text)
        codex_home = self.root / "codex-home"
        self.write(codex_home / "config.toml", codex_text)
        return {
            **os.environ,
            "CODEX_CONTEXT_BRIDGE_CONFIG": str(config_path),
            "CODEX_HOME": str(codex_home),
            "CLAUDE_CONFIG_DIR": str(self.claude_dir),
        }

    def run_script(self, args: list[str], env: dict[str, str], stdin: str = "") -> str:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=stdin,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def test_config_reads_codex_fallback_and_markers(self) -> None:
        env = self.env(
            f'trusted_roots = ["{self.work}"]\n',
            'project_doc_fallback_filenames = ["CLAUDE.md"]\nproject_root_markers = [".jj"]\n',
        )
        old = dict(os.environ)
        try:
            os.environ.update(env)
            config = bridge.load_config()
        finally:
            os.environ.clear()
            os.environ.update(old)
        self.assertEqual(config.trusted_roots, (self.work,))
        self.assertEqual(config.codex_fallback_filenames, ("CLAUDE.md",))
        self.assertEqual(config.codex_root_markers, (".jj",))
        self.assertEqual(config.memory_projects_root, self.claude_dir / "projects")

    def test_hook_mode_emits_session_start_json(self) -> None:
        self.write(self.work / "CLAUDE.md", "PARENT_VALUE")
        repo = self.work / "repo"
        (repo / ".git").mkdir(parents=True)
        env = self.env(f'trusted_roots = ["{self.work}"]\n')

        out = self.run_script([], env, json.dumps({"cwd": str(repo)}))

        payload = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(payload["hookEventName"], "SessionStart")
        self.assertIn("PARENT_VALUE", payload["additionalContext"])

    def test_hook_mode_is_silent_on_bad_input(self) -> None:
        env = self.env("")
        self.assertEqual(self.run_script([], env, "not json"), "")
        self.assertEqual(self.run_script([], env, "[]"), "")

    def test_dry_run_json(self) -> None:
        self.write(self.work / "CLAUDE.md", "root")
        env = self.env("")
        out = self.run_script(
            ["--dry-run", "--trusted-root", str(self.work), "--cwd", str(self.work)], env
        )
        self.assertEqual(json.loads(out)["injected"], [str(self.work / "CLAUDE.md")])


if __name__ == "__main__":
    unittest.main()
