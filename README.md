# codex-context-bridge

A Codex `SessionStart` hook that gives Codex the Claude Code context it cannot discover on its own, at session start, without generating or syncing any files.

If you run Claude Code and Codex side by side in the same trees, you probably already set `project_doc_fallback_filenames = ["CLAUDE.md"]` in Codex. That covers the easy part. This hook covers the rest.

## What Codex misses, and what the hook adds

Codex reads instruction files from its project root (the nearest `.git` by default) down to the startup directory, at most one file per directory, preferring `AGENTS.override.md`, then `AGENTS.md`, then your fallback names. Claude Code reads more. Inside directories you mark as trusted, the hook injects:

| Claude Code context | Codex natively | Hook |
| --- | --- | --- |
| `CLAUDE.md` between the Git root and cwd | yes, with the fallback setting | skipped (no duplicates) |
| `CLAUDE.md` above the Git root (e.g. a workspace `~/Projects/CLAUDE.md` over nested repos) | no | injected |
| `CLAUDE.md` below the root when CLAUDE.md is not a fallback name | no | injected |
| `CLAUDE.local.md` at any level | no | injected |
| `<project>/.claude/CLAUDE.md` | no | injected |
| `<project>/.claude/rules/**/*.md` without `paths:` frontmatter | no | injected |
| `.claude/rules` files with `paths:` frontmatter | no | listed with their patterns, not loaded |
| Claude auto-memory index (`~/.claude/projects/<flattened-path>/memory/MEMORY.md`, nearest ancestor) | no | appended as background; linked memory files are not read |

Output order is broad to deep, with a preamble telling Codex that native instructions win, deeper directories override shallower ones, and `CLAUDE.local.md` overrides `CLAUDE.md` in the same directory.

## Install

Requires Python 3.11+ (stdlib only) and a Codex version with hooks.

1. Put `codex-context-bridge` somewhere stable and make it executable.
2. Create `~/.config/codex-context-bridge/config.toml` with at least your trusted roots (see [examples/config.toml](examples/config.toml)):
   ```toml
   trusted_roots = ["~/Projects", "~/Code"]
   ```
3. Add the hook to `~/.codex/hooks.json` (see [examples/hooks.json](examples/hooks.json)), then start Codex and approve the hook under `/hooks`.
4. Check what it would inject for a directory:
   ```sh
   codex-context-bridge --dry-run --cwd ~/Code/some-repo           # decisions as JSON
   codex-context-bridge --dry-run --render --cwd ~/Code/some-repo  # the injected text
   ```

## Configuration

Config file: `$CODEX_CONTEXT_BRIDGE_CONFIG`, else `$XDG_CONFIG_HOME/codex-context-bridge/config.toml`, else `~/.config/codex-context-bridge/config.toml`. `--config PATH` overrides.

| Key | Default | Meaning |
| --- | --- | --- |
| `trusted_roots` | none | Only directories under these get anything injected. With none set the hook is a no-op. |
| `claude_config_dir` | `$CLAUDE_CONFIG_DIR` or `~/.claude` | Where Claude Code keeps `projects/*/memory/MEMORY.md`. |
| `codex_fallback_filenames` | Codex's `project_doc_fallback_filenames` | Names Codex already reads; the hook does not re-inject them. |
| `codex_root_markers` | Codex's `project_root_markers`, else `[".git"]` | How the hook finds Codex's project root. |
| `include_local`, `include_dot_claude`, `include_rules`, `include_memory` | `true` | Toggle each source. |
| `max_context_chars` | `18000` | Total budget, kept below Codex's roughly 5,000-token hook context limit. |

Codex settings are read from `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`), so the hook mirrors what your Codex actually loads.

## How it works

1. Reads the hook JSON from stdin and takes `cwd`.
2. Resolves cwd; if it is not under a trusted root, exits with no output.
3. Finds Codex's project root, then walks from the trusted root to cwd. Above the project root it injects every `CLAUDE.md`; from the root down it injects `CLAUDE.md` only where Codex loaded no file for that directory.
4. At the project root it adds `.claude/CLAUDE.md` and `.claude/rules`; at every level it adds `CLAUDE.local.md`.
5. Every file must resolve inside the trusted root (memory: inside the Claude projects dir). Symlinks that escape are skipped and reported in `--dry-run`.
6. When over budget it keeps whole files, deepest first, names the omitted ones, and truncates the memory index last.

Every failure exits 0 with a message on stderr, so a broken config never blocks a Codex session.

## Limits

- Startup only. Claude Code loads nested `CLAUDE.md` and path-scoped rules lazily as it touches files; the hook cannot, so it lists scoped rules and relies on Codex to read them.
- Rules and `.claude/CLAUDE.md` are read only at the project root, not from every ancestor.
- If a directory has both `AGENTS.md` and a `CLAUDE.md` with different content, only `AGENTS.md` reaches Codex. The hook assumes they mirror each other (the common symlink setup).
- User-level context (`~/.claude/CLAUDE.md`, `~/.claude/rules/`) is not bridged. Point `~/.codex/AGENTS.md` at it, or generate it, instead.
- `@path` imports inside `CLAUDE.md` are passed through as text, not expanded.
- Hook context is a separate message, not a native instruction file, and counts against Codex's hook context limit, not `project_doc_max_bytes`.
- Tested on macOS; should work on Linux. Not tested on Windows.

## Related tools

- AGENTS.md as the single source, with `CLAUDE.md` as a symlink or `@AGENTS.md` import: the simplest answer when you control every repo. It does not cover `CLAUDE.local.md`, `.claude/rules`, auto-memory, or a `CLAUDE.md` above a repo you do not own.
- [ruler](https://github.com/intellectronica/ruler), [rulesync](https://github.com/dyoshikawa/rulesync), [agent-sync-template](https://github.com/benthamite/agent-sync-template): generate or sync instruction files per agent. They write files into your repos; this hook writes nothing and works on trees you would rather not add files to.
- [codex-claude-memory-plugin](https://github.com/gaboe/codex-claude-memory-plugin): a Codex plugin that shares Claude's `MEMORY.md` with Codex and lets Codex write to it. Overlaps with the memory part only; use it instead if you want Codex to update Claude's memory.

## Tests

```sh
python3 -m unittest discover -s tests
```

## License

MIT
