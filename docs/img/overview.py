"""Generates overview.svg (the README diagram). Run: python3 docs/img/overview.py"""
from pathlib import Path
# kind: dir | native | hook | listed | none
rows = [
  ("~/work/", "", "dir", ""),
  ("├── ", "CLAUDE.md", "hook", "workspace level, above the Git root"),
  ("└── ", "acme-api/", "dir", ".git: Codex project root"),
  ("    ├── ", "CLAUDE.md", "native", "via project_doc_fallback_filenames"),
  ("    ├── ", "CLAUDE.local.md", "hook", "personal, git-ignored"),
  ("    └── ", ".claude/", "dir", ""),
  ("        ├── ", "CLAUDE.md", "hook", ""),
  ("        └── ", "rules/", "dir", ""),
  ("            ├── ", "style.md", "hook", "always-on rule"),
  ("            └── ", "db.md", "listed", "paths: src/db/**"),
  ("~/.claude/projects/-home-you-work-acme-api/memory/", "", "dir", ""),
  ("└── ", "MEMORY.md", "hook", "Claude's auto-memory index"),
]
C = {
  "native": ("#eaeef2", "#8c959f", "#24292f"),
  "hook":   ("#dafbe1", "#1a7f37", "#0f3d1f"),
  "listed": ("#fff8c5", "#bf8700", "#4d3800"),
}
CW = 8.4   # mono char width at 14px
FS = 14
X0, Y0, RH = 36, 78, 30
W, H = 960, Y0 + RH*len(rows) + 70
out = []
a = out.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif">')
a('<title>codex-context-bridge overview</title>')
a(f'<rect width="{W}" height="{H}" rx="12" fill="#ffffff"/>')
a('<defs><marker id="ag" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#1a7f37"/></marker>'
  '<marker id="ay" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#8c959f"/></marker></defs>')
# panel
PW = 560
a(f'<rect x="16" y="16" width="{PW}" height="{H-32}" rx="10" fill="#f6f8fa" stroke="#d0d7de"/>')
a(f'<text x="{X0}" y="48" font-size="15" font-weight="600" fill="#24292f">Example tree, Codex started in ~/work/acme-api</text>')
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
hook_ys = []
native_y = listed_y = None
for i, (prefix, name, kind, note) in enumerate(rows):
    y = Y0 + i*RH
    cy = y + RH/2
    tx = X0 + len(prefix)*CW if name else X0
    label = name or prefix
    if name:
        a(f'<text x="{X0}" y="{cy+5}" font-family="{MONO}" font-size="{FS}" fill="#8c959f" xml:space="preserve">{prefix}</text>')
    if kind in C:
        fill, stroke, fc = C[kind]
        dash = ' stroke-dasharray="4 3"' if kind == "listed" else ''
        a(f'<rect x="{tx-6}" y="{y+3}" width="{len(label)*CW+12}" height="{RH-6}" rx="5" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>')
        a(f'<text x="{tx}" y="{cy+5}" font-family="{MONO}" font-size="{FS}" font-weight="600" fill="{fc}">{label}</text>')
        if kind == "hook":
            hook_ys.append(cy)
        elif kind == "native":
            native_y = cy
        elif kind == "listed":
            listed_y = cy
    else:
        a(f'<text x="{tx}" y="{cy+5}" font-family="{MONO}" font-size="{FS}" fill="#57606a">{label}</text>')
    if note:
        nx = tx + len(label)*CW + 20
        a(f'<text x="{nx}" y="{cy+5}" font-size="12.5" fill="#57606a">{note}</text>')
# right side boxes
hx, hw, hh = 620, 150, 74
hy = (min(hook_ys)+max(hook_ys))/2 + 20 - hh/2
cx, cw, ch = 814, 130, 74
cyb = hy
a(f'<rect x="{hx}" y="{hy}" width="{hw}" height="{hh}" rx="10" fill="#1a7f37"/>')
a(f'<text x="{hx+hw/2}" y="{hy+30}" text-anchor="middle" font-size="14.5" font-weight="700" fill="#ffffff">codex-context-</text>')
a(f'<text x="{hx+hw/2}" y="{hy+48}" text-anchor="middle" font-size="14.5" font-weight="700" fill="#ffffff">bridge</text>')
a(f'<text x="{hx+hw/2}" y="{hy+65}" text-anchor="middle" font-size="11.5" fill="#dafbe1">SessionStart hook</text>')
a(f'<rect x="{cx}" y="{cyb}" width="{cw}" height="{ch}" rx="10" fill="#24292f"/>')
a(f'<text x="{cx+cw/2}" y="{cyb+42}" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">Codex session</text>')
# edges from hook rows: curves from panel edge into hook box left side
ex = PW + 16
tgt_y = hy + hh/2
for y in hook_ys + [listed_y]:
    col = "#bf8700" if y == listed_y else "#1a7f37"
    dash = ' stroke-dasharray="5 4"' if y == listed_y else ''
    a(f'<path d="M{ex-6},{y} C{ex+30},{y} {hx-40},{tgt_y} {hx-2},{tgt_y}" fill="none" stroke="{col}" stroke-width="1.8" opacity="0.85"{dash}/>')
    a(f'<circle cx="{ex-6}" cy="{y}" r="3" fill="{col}"/>')
a(f'<line x1="{hx+hw}" y1="{tgt_y}" x2="{cx-3}" y2="{tgt_y}" stroke="#1a7f37" stroke-width="3" marker-end="url(#ag)"/>')
a(f'<text x="{(hx+hw+cx)/2}" y="{tgt_y-14}" text-anchor="middle" font-size="12" fill="#1a7f37" font-weight="600">injects</text>')
# native edge: from native row, over the hook, into codex top
ny = native_y
a(f'<path d="M{ex-6},{ny} L{cx+cw/2-12},{ny} Q{cx+cw/2},{ny} {cx+cw/2},{ny+12} L{cx+cw/2},{cyb-3}" fill="none" stroke="#8c959f" stroke-width="2" marker-end="url(#ay)"/>')
a(f'<circle cx="{ex-6}" cy="{ny}" r="3" fill="#8c959f"/>')
a(f'<text x="{(ex+cx+cw/2)/2+20}" y="{ny-8}" text-anchor="middle" font-size="12" fill="#57606a">Codex reads natively</text>')
# legend
ly = H - 34
lx = 36
for kind, text in [("native", "Codex reads it natively"), ("hook", "hook injects the content"), ("listed", "hook lists path + pattern only")]:
    fill, stroke, _ = C[kind]
    dash = ' stroke-dasharray="4 3"' if kind == "listed" else ''
    a(f'<rect x="{lx}" y="{ly-12}" width="22" height="16" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>')
    a(f'<text x="{lx+30}" y="{ly+1}" font-size="12.5" fill="#24292f">{text}</text>')
    lx += 30 + len(text)*7 + 28
a('</svg>')
Path(__file__).with_name("overview.svg").write_text("\n".join(out) + "\n")
