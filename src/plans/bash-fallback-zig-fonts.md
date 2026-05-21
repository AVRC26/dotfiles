# Plan: bash fallback renderer, zig for treesitter, curl font install

## Context
Three goals driven by the need to reduce mandatory system-package deps in user-local
mode (no root / no sudo):
1. **gcc** for nvim-treesitter → replace with zig (static binary, user-installable)
2. **unzip** for fonts → replace with direct curl of individual .ttf files
3. **python3** for theme rendering → keep as primary; add bash fallback when absent

## Overview — 5 workstreams

| # | What | Files |
|---|------|-------|
| 1 | Zig binary installer + nvim treesitter compiler | `init-dotfiles.sh`, `nvim/init.lua` |
| 2 | Font install via curl (drop unzip dep) | `init-dotfiles.sh` |
| 3 | `palettes.sh` companion + `generate-sh` Python subcommand | `render-theme.py`, new `palettes.sh` |
| 4 | `render-theme.sh` bash fallback | new `src/.config/render-theme.sh` |
| 5 | Python-first / bash-fallback wiring + docs | `init-dotfiles.sh`, `setup-windows.ps1`, READMEs |

---

## ~~Workstream 1 — Zig + treesitter~~ ✓ DONE

### `src/.config/nvim/init.lua`
Added `compilers = { "zig" }` to `configs.setup()` (line ~400).

### `src/init-dotfiles.sh`
- **No permanent zig install** — zig is only needed while treesitter compiles parsers,
  so instead of a permanent binary install we fetch it to a `mktemp -d`, inject it
  onto PATH for the `nvim --headless Lazy sync`, then `rm -rf` it immediately after.
- `ARCH_ZIG` added to the arch detection block (`x86_64` / `aarch64`).
- `_install_zig_temp()` — resolves latest stable from `ziglang.org/download/index.json`,
  downloads `zig-linux-ARCH-VERSION.tar.xz`, sets `ZIG_TEMP_DIR` / `ZIG_TEMP_BIN`.
- `_cleanup_zig_temp()` — `rm -rf $ZIG_TEMP_DIR`; no-op if nothing was installed.
- Nvim headless sync block updated: if `zig` not in PATH, calls `_install_zig_temp`
  and prepends `ZIG_TEMP_BIN` to `_path`; calls `_cleanup_zig_temp` after sync.
- `check_prereq gcc` removed from both `cmd_bootstrap` and `cmd_install_user_local`.

### `dotfiles-bootstrap.sh`
`_ensure_prereq_optional gcc` and its comment removed.

---

## Workstream 2 — Font install via curl (drop unzip)

### `src/init-dotfiles.sh` — rewrite `install_nerd_font()`
Replace zip download + unzip with direct curl of individual .ttf files.

**Files to download** (Nerd Fonts v3, raw GitHub HEAD):
```
FiraCode (Mono variants — single-width, correct for terminals):
  patched-fonts/FiraCode/Regular/FiraCodeNerdFontMono-Regular.ttf
  patched-fonts/FiraCode/Bold/FiraCodeNerdFontMono-Bold.ttf
  patched-fonts/FiraCode/Light/FiraCodeNerdFontMono-Light.ttf
  patched-fonts/FiraCode/Medium/FiraCodeNerdFontMono-Medium.ttf
  patched-fonts/FiraCode/Retina/FiraCodeNerdFontMono-Retina.ttf
  patched-fonts/FiraCode/SemiBold/FiraCodeNerdFontMono-SemiBold.ttf

NerdFontsSymbolsOnly:
  patched-fonts/NerdFontsSymbolsOnly/Regular/SymbolsNerdFontMono-Regular.ttf
  patched-fonts/NerdFontsSymbolsOnly/Regular/SymbolsNerdFont-Regular.ttf
```
Base URL: `https://github.com/ryanoasis/nerd-fonts/raw/HEAD/`

NOTE: Verify exact paths with `curl -I` before implementing — Nerd Fonts reorganised
between v2 and v3.

No `unzip` required. Remove `_ensure_prereq_optional unzip` from `dotfiles-bootstrap.sh`.

---

## Workstream 3 — `palettes.sh` companion format

### Why a companion file
The bash fallback needs palettes data without jq or python3.
Solution: pre-generated bash-sourceable `palettes.sh` committed alongside
`palettes.json`. Python generates/regenerates it; bash just sources it.

### Variable naming convention
```bash
MONOKAI_DEFAULT_FLAVOR="spectrum"
MONOKAI_NVIM_THEME="monokai-pro"
MONOKAI_NVIM_VARIANT_KEY="monokai_filter"
MONOKAI_DELTA_SYNTAX_THEME="TwoDark"

MONOKAI_SPECTRUM_BG="#2d2a2e"
MONOKAI_SPECTRUM_FG="#fcfcfa"
# ... all non-underscore color keys per flavor

MONOKAI_SPECTRUM_DELTA_SYNTAX_THEME="TwoDark"   # flavor-level override if present

MONOKAI_SPECTRUM_ROLE_BG="bg"
MONOKAI_SPECTRUM_ROLE_FG="fg"
MONOKAI_SPECTRUM_ROLE_SEG="bg text ok err warn dimmed"  # space-separated
MONOKAI_SPECTRUM_ROLE_DC_DIR="bg"
MONOKAI_SPECTRUM_ROLE_GC_NEW="ok"
MONOKAI_SPECTRUM_TERMINAL_FALLBACK=""
```

### `render-theme.py` — add `generate-sh` subcommand
`generate-sh --palette palettes.json --output palettes.sh`
Run by developers after editing palettes.json; output committed to repo.

---

## Workstream 4 — `render-theme.sh` bash fallback

### New file: `src/.config/render-theme.sh`
Same CLI as render-theme.py `set-theme` / `apply` subcommands.

Color math (pure bash, no deps):
- `_hex_to_dec`, `_hex_to_rgb_escape`, `_blend_hex` (integer alpha*100), `_is_dark`

Template substitution: bash `${content//{{KEY}}/val}` pattern + `mktemp`/`mv` for
atomic writes.

Palette resolution via indirect expansion:
```bash
source "$palette_sh"
_color() { local v="${THEME^^}_${FLAVOR^^}_ROLE_${1}"; local c="${!v}";
           local cv="${THEME^^}_${FLAVOR^^}_${c^^}"; echo "${!cv}"; }
```

---

## Workstream 5 — Python-first / bash-fallback wiring

### `src/init-dotfiles.sh` — `apply_dotfiles()`
```bash
if command -v python3 &>/dev/null; then
    python3 "$render_py" set-theme --palette "$pal_json" ...
elif [ -x "$render_sh" ]; then
    bash   "$render_sh" set-theme --palette "$pal_sh"   ...
else
    log_warn "No theme renderer found — skipping."
fi
```
Copy both `palettes.json` and `palettes.sh` during install.

### `check_prereq` changes
- Remove `check_prereq gcc` — zig replaces it
- Remove `check_prereq unzip` — no longer needed
- Keep `check_prereq python3` as optional warn-only

### `set-theme` wrapper heredoc
Update to use same python-first / bash-fallback logic.

---

## Critical files

| File | Change |
|------|--------|
| `src/.config/nvim/init.lua` | add `compilers = {"zig"}` |
| `src/init-dotfiles.sh` | `install_zig`, rewrite `install_nerd_font`, fallback wiring |
| `dotfiles-bootstrap.sh` | remove gcc/unzip optional prereqs |
| `src/.config/render-theme.py` | add `generate-sh` subcommand |
| `src/.config/render-theme.sh` | **NEW** bash fallback renderer |
| `src/.config/palettes.sh` | **NEW** generated bash-sourceable palette data |
| `README.md`, `src/README.md`, `src/THEMES.md` | docs update |

---

## Verification

1. `install_zig` + treesitter: no gcc, `:TSInstall lua` compiles via zig
2. Font install: no unzip, `.ttf` files present, `fc-list | grep Fira` works
3. Python path: render-theme.py called when python3 present
4. Bash fallback: python3 absent → render-theme.sh produces identical output
5. `palettes.sh` round-trip: `generate-sh` output matches committed file
6. Uninstall: zig removed cleanly
