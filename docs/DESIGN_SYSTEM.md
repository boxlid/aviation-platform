# Sonic Flights — Design System

Single source of truth for UI. Every page and component must use these tokens and
classes — do not introduce ad-hoc colors, inline styles for theming, or one-off
button markup. All styles live in `app/static/css/app.css`.

## Design tokens (CSS variables, `:root`)
| Token | Use |
|---|---|
| `--bg`, `--bg-2` | page backgrounds |
| `--panel`, `--panel-solid` | card / surface backgrounds |
| `--border`, `--border-bright` | borders; `-bright` = focus/active |
| `--text`, `--text-dim`, `--text-faint` | primary / secondary / tertiary text |
| `--accent` (cyan) | primary actions, links, highlights |
| `--gold` | secondary accent (Mode S hex, turboprop) |
| `--good` `--warn` `--bad` `--running` | status semantics |
| `--radius` | corner radius (14px) |
| `--mono` `--sans` | fonts; `--mono` for tails/hex/codes/logs |

**Rule:** reference colors only via `var(--token)`. Never hard-code hex in components.

## Components (class → meaning)
- **Panel**: `.panel` (surface), `.panel.pad` (with padding). All cards are panels.
- **Grid**: `.grid` + `.cols-2|3|4` (responsive; collapses < 1100px).
- **Stat card**: `.panel.stat` with `.k` (label), `.v` (value), `.sub` (caption), optional `.glow`.
- **Buttons**: `.btn` base. Variants: `.btn.primary` (cyan, main action), `.btn.ghost` (transparent), `.btn.danger` (red on hover, destructive), `.btn.sm` (compact). One primary action per view.
- **Badges**: `.badge` + `.cat-Jet|cat-Turboprop|cat-Helicopter|cat-Piston|cat-Other|cat-Unknown`. Aircraft category only — use `catBadge()` in JS.
- **Status pill**: `.status-pill.st-<status>` with a `.dot-s`. Statuses: `success|running|error|paused|idle`. Use `statusPill()` in JS.
- **Tables**: `<table>` inside a `.panel`. Sortable tables add `class="sortable"` and `th[data-key][data-type=str|num]`; wire with `SF.sortable()`. Numeric cells/headers use `.num` (right-aligned).
- **Cell styles**: `.tail` (N-number, cyan mono), `.hex` (Mode S, gold mono), `.muted`/`.dim` (de-emphasized).
- **Toolbar**: `.toolbar` row above a table; `.search` is the flexible search input.
- **Note/banner**: `.note` (info callout). **Empty state**: `.empty` (centered placeholder inside tbody).
- **Logs**: `.logs` container, `.logline` with `.t` (time) `.lv .lv-<LEVEL>` (level) + message.
- **Bar**: `.bar > i` (progress/proportion).

## Interaction rules
- **Links inside tables** are `--accent` and underline on hover. Drill-downs (operator, FSDO) are plain `<a href>` — server-rendered pages, not modals.
- **Sorting**: click a `th[data-key]` to sort; click again to reverse. Arrow (`▲/▼`) shows active column. All data tables should be sortable.
- **Notification dot**: never render statically. `SF.checkNotifications()` injects `.dot` into `#bell` only when `/api/notifications` reports `unread > 0`.
- **One toolbar search per list**, debounced 300ms (`debounce()`).

## JS render helpers (in `app/static/js/app.js`, namespace `SF` + module-level)
`fmtNum, fmtInterval, ago, dt, esc, catBadge, statusPill, debounce, getJSON, send, SF.sortable`.
Always `esc()` untrusted strings into HTML. Reuse these — do not re-implement formatting.

## Adding a new page
1. Template `app/templates/<page>.html` extends `base.html`; fill `{% block content %}` and a `{% block script %}` that calls one `SF.<page>()`.
2. Add a `SF.<page>` renderer in `app.js` using the helpers above.
3. Add the route in `app/main.py` (`page(request, "<page>.html", active="<navkey>", title="…")`).
4. Add the nav entry in `base.html` if it's top-level.
Use existing components only; if you need a new component, add it here first, then to `app.css`.
