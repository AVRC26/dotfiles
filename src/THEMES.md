# Theme system — complete reference

Everything about how themes work, how to switch them, how to add new ones, and how the color data is managed.

---

## Contents

- [Quick usage — set-theme](#quick-usage--set-theme)
- [Starship prompt templates](#starship-prompt-templates)
- [How it works](#how-it-works)
- [File map](#file-map)
- [Color roles reference](#color-roles-reference)
- [Color selection philosophy](#color-selection-philosophy)
- [Managing palettes.json](#managing-palettesjson)
- [Adding a new theme — step by step](#adding-a-new-theme--step-by-step)
- [Testing a theme](#testing-a-theme)
- [preview-themes.py reference](#preview-themespy-reference)
- [get-colors.py reference](#get-colorspy-reference)

---

## Quick usage — set-theme

Switches Neovim colorscheme, Starship prompt, `ls` colors, and `git diff`/`git status` colors in one command. Takes effect immediately in the current shell.

All arguments are **named**. The positional form still works for backwards compat but named is preferred.

### Linux / WSL (bash)

```bash
# Switch theme — named args
set-theme --theme monokai
set-theme --theme monokai --flavor spectrum
set-theme --theme catppuccin --flavor latte

# Switch prompt template (saved; persists across theme switches)
set-theme --theme monokai --starship-template nerd-font

# Theme + template in one call
set-theme --theme gruvbox --flavor dark --starship-template powerline

# List all available themes and flavors
set-theme --help

# Show active theme, flavor, and Starship template
get-theme

# Short aliases
set-theme -t monokai -f classic -T pills
```

Available themes and flavors:

```bash
set-theme --theme monokai                    # Monokai Pro — spectrum (user default)
set-theme --theme monokai --flavor classic
set-theme --theme monokai --flavor octagon
set-theme --theme monokai --flavor pro
set-theme --theme monokai --flavor machine
set-theme --theme monokai --flavor ristretto

set-theme --theme catppuccin                 # Catppuccin Mocha
set-theme --theme catppuccin --flavor latte  # light
set-theme --theme catppuccin --flavor frappe
set-theme --theme catppuccin --flavor macchiato

set-theme --theme gruvbox                    # Gruvbox light (root default: gruvbox/light + sanmue)
set-theme --theme gruvbox --flavor light     # root default
set-theme --theme gruvbox --flavor dark-hard
set-theme --theme gruvbox --flavor dark-soft
set-theme --theme gruvbox --flavor dark

set-theme --theme kanagawa                   # Kanagawa Wave
set-theme --theme kanagawa --flavor dragon
set-theme --theme kanagawa --flavor lotus    # light

set-theme --theme bearded                    # Bearded Arc (default)
set-theme --theme bearded --flavor oceanic
set-theme --theme bearded --flavor milkshake-raspberry
# 63 flavors total — see: python3 src/get-colors.py --show --theme bearded

set-theme --theme flexoki                    # Flexoki Dark
set-theme --theme flexoki --flavor light

set-theme --theme tokyonight                 # Tokyo Night
set-theme --theme tokyonight --flavor storm
set-theme --theme tokyonight --flavor moon
set-theme --theme tokyonight --flavor day    # nvim-only; terminal falls back to storm

set-theme --theme bamboo                     # Bamboo Vulgaris (default)
set-theme --theme bamboo --flavor multiplex  # greener variant
set-theme --theme bamboo --flavor light      # light theme

set-theme --theme oasis                      # Oasis Moonlight (default)
set-theme --theme oasis --flavor night
set-theme --theme oasis --flavor dune
set-theme --theme oasis --flavor lagoon
set-theme --theme oasis --flavor rose
set-theme --theme oasis --flavor twilight
set-theme --theme oasis --flavor luna
set-theme --theme oasis --flavor abyss
set-theme --theme oasis --flavor cactus
set-theme --theme oasis --flavor canyon
set-theme --theme oasis --flavor desert
set-theme --theme oasis --flavor midnight
set-theme --theme oasis --flavor mirage
set-theme --theme oasis --flavor scorpion
set-theme --theme oasis --flavor sol
set-theme --theme oasis --flavor starlight
# 16 flavors total — see: python3 src/get-colors.py --show --theme oasis

set-theme --theme onedarkpro                              # One Dark
set-theme --theme onedarkpro --flavor onelight            # light
set-theme --theme onedarkpro --flavor onedark_vivid       # more saturated variant
set-theme --theme onedarkpro --flavor onedark_dark        # pure-black background
```

Windows `Set-Theme` / `Get-Theme` usage → **[README.md — Windows setup](../README.md#windows-setup)**

**Install defaults:**

| Context | Theme | Flavor | Template |
|---------|-------|--------|----------|
| Linux / WSL — user | monokai | spectrum | moir |
| Linux / WSL — root | gruvbox | light | sanmue |
| Windows | catppuccin | macchiato | pills |

Defaults only apply on first install. Override with `--theme`, `--flavor`, `--starship-template` flags.

---

## Starship prompt templates

Ten prompt layouts are available. All use the same theme color palette — only the visual structure differs. The active template is saved in `~/.config/dotfiles-starship-template` and used by every future `set-theme` call.

All templates carry a stats line (RAM, 1-min CPU load average, disk `/` usage %) above the main
prompt line — network usage is deferred, not yet shown.

| Template | Description | Best for |
|----------|-------------|----------|
| `powerline` | Classic powerline segments, NF icons, left-only, stats line on top | Linux default |
| `pills` | Pill-shaped modules, box-draw borders, three-line (stats + prompt + cursor) | Windows Terminal |
| `nerd-font` | Dense NF v3 icons, fill-separated, stats line + prompt + cursor | NF power users |
| `dracula` | Badge-style pills on a `╭`/`│`/`╰─` frame with fill separator, three-line | Decorative |
| `seeker` | Three-line with `╭─`/`├─`/`╰─` borders and right bracket | Structured |
| `moir` | Dense powerline left + full right-side module list, stats line on top | Power users |
| `sanmue` | Three-line flat-bg, fill-split right-side modules, Power10k-inspired | NF v2 users |
| `sepan` | Powerline left-to-right segments, full module coverage, three-line | Power users |

> **Note — prompt background streak:** When prompts length is greater than the width of the terminal, the promp may show a colored streak to the right of the overflow line or the second line (`╰─❯`). Two root causes, both fixed automatically:
>
> | Environment | Cause | Fix |
> |---|---|---|
> | Windows Terminal (bash) | BCE: scroll paints new lines with last SGR bg | `\e[?117h` (DECECM off) via `PROMPT_COMMAND` when `$WT_SESSION` set — see `.bashrc` |
> | Windows Terminal (PowerShell) | Same BCE cause | `$([char]27)[?117h` written before each prompt render — see `$PROFILE` |
> | VS Code (PowerShell) | Overflow: bg bleeds into wrapped line | `\e[K\n\e[49m\e[2K` injected into Starship's prompt string — see `$PROFILE` |
> | VS Code (WSL bash) | Same overflow cause | `\e[K` + `\e[49m\e[2K` injected into PS1 via `PROMPT_COMMAND` — see `.bashrc` |
>
> All fixes are wired in at install time. Upstream BCE tracking: [#19747](https://github.com/microsoft/terminal/discussions/19747), [#19736](https://github.com/microsoft/terminal/issues/19736).


### Select at install time

```bash
# Interactive prompt (when --interactive is passed)
sudo ./init-dotfiles.sh install user alice --interactive

# Non-interactive
sudo ./init-dotfiles.sh install user alice --starship-template moir
```

Windows → see [README.md — Windows setup](../README.md#windows-setup)

### Switch template after install

```bash
set-theme --theme monokai --starship-template nerd-font
```

The `--starship-template` flag re-renders the active theme with the new layout and saves the choice. Subsequent `set-theme` calls without `--starship-template` use the saved template.

---

## How it works

```
palettes.json  +  roles.json
       │                │
       │   (merged at   │
       │    install)    │
       └────────┬───────┘
                ▼
          _apply_theme
         (single Python call)
                │
    ┌───────────┼─────────────┐
    ▼           ▼             ▼
starship.toml  .dircolors  git/theme.conf
```

**`palettes.json`** — checked into the repo at `src/.config/palettes.json`. Contains the actual hex color values for every theme and flavor (`accent1: "#ff6188"`, etc.). Generated by the repo owner from live Neovim plugin Lua files using `python3 src/get-colors.py --export`. Users never need to regenerate it.

**`roles.json`** — checked into the repo at `src/.config/roles.json`. Maps semantic roles (`SEG0`, `DC_DIR`, `GC_ADDED`, …) to palette color names (`accent1`, `blue`, …) for each theme. This is the "design intent" — which color in the palette plays which visual role. Edited by hand when adding or tuning a theme.

**`set-theme`** — defined in `.bashrc`. Reads both files, resolves names→hex, and renders three output files in one Python call:

| Template | Output | Color format |
|----------|--------|--------------|
| `~/.config/starship/<active-template>.toml` | `~/.config/starship.toml` | hex `#rrggbb` |
| `~/.config/dircolors-template` | `~/.dircolors` | 24-bit ANSI `38;2;R;G;B` |
| `~/.config/gitcolors-template` | `~/.config/git/theme.conf` | quoted hex `"#rrggbb"` |

The separator glyph (`{{SEP_TRANS}}`, U+E0B0) and prompt character (`{{PROMPT_CHAR}}`, `|` for user / `_` for root) are injected automatically. The active template is read from `~/.config/dotfiles-starship-template`.

**Usage:** `set-theme --theme NAME [--flavor NAME] [--starship-template NAME]`. Validates the theme/flavor against `palettes.json`, writes `~/.config/nvim/theme.lua` (read by Neovim on startup), then renders all templates.

---

## File map

```
repo/
└── src/
    ├── get-colors.py              ← palette viewer + JSON exporter
    └── .config/
        ├── roles.json             ← role→colorname mappings (hand-edited)
        ├── palettes.json          ← all hex values (generated, committed)
        ├── starship/
        │   ├── powerline.toml     ← powerline segments (NF icons)
        │   ├── pills.toml         ← pill-shaped modules
        │   ├── nerd-font.toml     ← comprehensive NF icons, fill-separated
        │   ├── dracula.toml       ← badge-style with fill separator
        │   ├── seeker.toml        ← two-line with right border
        │   ├── moir.toml          ← dense powerline + right-side modules
        │   ├── sanmue.toml        ← two-line flat-bg, Power10k-inspired
        │   └── sepan.toml         ← powerline segments, full module coverage
        ├── dircolors-template     ← ls color template
        ├── gitcolors-template     ← git color template
        └── nvim/
            └── init.lua           ← Neovim + all theme plugins

deployed to ~/.config/
├── palettes.json                  ← copied from repo at install
├── roles.json                     ← copied from repo at install
├── dotfiles-starship-template     ← active template name (e.g. "powerline")
├── starship/                      ← copied from repo at install
│   ├── powerline.toml
│   ├── pills.toml
│   ├── nerd-font.toml
│   ├── dracula.toml
│   ├── seeker.toml
│   ├── moir.toml
│   ├── sanmue.toml
│   └── sepan.toml
├── dircolors-template             ← copied from repo at install
├── gitcolors-template             ← copied from repo at install
├── starship.toml                  ← rendered by set-theme
├── git/
│   └── theme.conf                 ← rendered by set-theme, loaded via [include]
└── nvim/
    └── theme.lua                  ← written by set-theme, read by init.lua

~/.dircolors                       ← rendered by set-theme (in $HOME, not .config)
```

---

## Color roles reference

Each role key lives under `"_roles"` in `roles.json`. `render-theme.py` resolves the role name → palette color name → hex value and substitutes it into the relevant template. There are four output targets:

| Target | Format | Template file |
|--------|--------|--------------|
| `starship.toml` | `#rrggbb` | `starship/<name>.toml` |
| `.dircolors` | `38;2;R;G;B` | `dircolors-template` |
| `git/theme.conf` | `"#rrggbb"` (quoted) | `gitcolors-template` |
| `git/theme.conf` (delta section) | computed / bat name | `gitcolors-template` |

### Starship prompt roles → `{{COLOR_*}}`

The prompt is laid out as a chain of pills:

```
[BG pill: user@host (TEXT on BG)] → [SEG1: dir (FG on SEG1)] → [SEG2: git] → [SEG3: lang] → ...
```

`SEG0` uses `BG`/`TEXT` exclusively — `SEG[0]` exists in the array for completeness but is not applied to the user/host pill.

| Role | Placeholder | What it colors |
|------|-------------|----------------|
| `BG` | `{{COLOR_BG}}` | User/host pill background — **the theme identity anchor** |
| `TEXT` | `{{COLOR_TEXT}}` | Text inside the user/host pill (contrasts with `BG`) |
| `SEG` (array of 6) | `{{COLOR_SEG0}}`–`{{COLOR_SEG5}}` | Segment backgrounds left→right: user/host · dir · git · lang · docker · time |
| `FG` | `{{COLOR_FG}}` | Foreground text on SEG1–SEG5 pills |
| `OK` | `{{COLOR_OK}}` | `❯` prompt character — last command succeeded |
| `ERR` | `{{COLOR_ERR}}` | `❯` prompt character — last command failed |
| `WARN` | `{{COLOR_WARN}}` | `❯` prompt character — vim replace/visual mode |

### Dircolors roles → `{{DC_*}}`

Hex values are converted to 24-bit ANSI `38;2;R;G;B` before substitution.

| Role | Placeholder | What it colors |
|------|-------------|----------------|
| `DC_DIR` | `{{DC_DIR}}` | Directories |
| `DC_LINK` | `{{DC_LINK}}` | Symbolic links |
| `DC_EXEC` | `{{DC_EXEC}}` | Executables (`chmod +x`) |
| `DC_SOURCE` | `{{DC_SOURCE}}` | Source code (`.py`, `.go`, `.rs`, `.ts`, …) |
| `DC_TEXT` | `{{DC_TEXT}}` | Config & text (`.yaml`, `.toml`, `.md`, `.env`, …) |
| `DC_IMAGE` | `{{DC_IMAGE}}` | Images (`.png`, `.jpg`, `.svg`, …) |
| `DC_MEDIA` | `{{DC_MEDIA}}` | Audio & video (`.mp4`, `.mp3`, `.mkv`, …) |
| `DC_ARCHIVE` | `{{DC_ARCHIVE}}` | Archives (`.zip`, `.tar.gz`, `.deb`, …) |
| `DC_DOC` | `{{DC_DOC}}` | Documents (`.pdf`, `.docx`, `.pptx`, …) |
| `DC_DIMMED` | `{{DC_DIMMED}}` | Unimportant files (`.pyc`, `.log`, `.swp`, …) |

### Git / delta roles → `{{GC_*}}`

Written as `"#rrggbb"` (quoted) into the gitconfig include file for git's own coloring, and also used as inputs to the computed delta placeholders below.

| Role | Placeholder | Where it appears |
|------|-------------|-----------------|
| `GC_ADDED` | `{{GC_ADDED}}` | `git status` added files |
| `GC_CHANGED` | `{{GC_CHANGED}}` | `git status` modified files |
| `GC_UNTRACKED` | `{{GC_UNTRACKED}}` | `git status` untracked files |
| `GC_BRANCH` | `{{GC_BRANCH}}` | Branch name; `git log` decorations; delta file headers |
| `GC_REMOTE` | `{{GC_REMOTE}}` | Remote branch names in `git log` |
| `GC_TAG` | `{{GC_TAG}}` | Tag decorations in `git log` |
| `GC_OLD` | `{{GC_OLD}}` | Removed lines in `git diff`; delta minus line numbers |
| `GC_NEW` | `{{GC_NEW}}` | Added lines in `git diff`; delta plus line numbers |
| `GC_META` | `{{GC_META}}` | File header lines in `git diff`; delta hunk headers |
| `GC_FRAG` | `{{GC_FRAG}}` | Hunk markers `@@ … @@`; delta hunk border; line-number gutter |

### Delta computed placeholders

These are **not** stored in `roles.json` — `render-theme.py` derives them automatically at render time from the GC roles above. They appear only in `gitcolors-template` under `[delta "theme-colors"]`.

| Placeholder | How it is computed | What it colors in delta |
|-------------|-------------------|------------------------|
| `{{GC_PLUS_BG}}` | `GC_NEW` blended 15% into `BG` | Added-line background (normal) |
| `{{GC_PLUS_EMPH_BG}}` | `GC_NEW` blended 30% into `BG` | Added-line background (emphasized) |
| `{{GC_MINUS_BG}}` | `GC_OLD` blended 15% into `BG` | Removed-line background (normal) |
| `{{GC_MINUS_EMPH_BG}}` | `GC_OLD` blended 30% into `BG` | Removed-line background (emphasized) |
| `{{DELTA_SYNTAX_THEME}}` | `_delta.syntax_theme` from `roles.json`; falls back to `TwoDark`/`GitHub` based on `BG` luminance | bat syntax highlighting theme for code text inside hunks |

---

## Color selection philosophy

This explains *why* colors are assigned the way they are, so future theme integrations don't start from scratch.

### The identity anchor problem

Neovim themes are visually distinct for one primary reason: their **editor background color**. You can tell catppuccin mocha from catppuccin frappe at a glance because mocha is warm purple-dark and frappe is slate blue-dark. The accent colors (red, green, blue etc.) are nearly identical between dark flavors of the same theme.

The prompt/gc/dc color system has the same problem: if you map `SEG0` to `red` for all catppuccin flavors, the user/host pill looks almost the same in mocha, frappe, and macchiato because their `red` hex values differ by only a few points.

**Solution:** `BG` maps to the editor background color. The user/host pill background *is* the editor background, so the prompt immediately reflects the theme's visual identity. `TEXT` maps to the editor body text (guaranteed by the theme to contrast with `BG`).

### How per-flavor `_roles` creates gc/dc differentiation

For themes where all accents are identical between flavors (tokyonight night vs storm share *every* accent hex value), we use **different color name choices** for the same semantic role:

- night `DC_DIR`: `cyan` (#7dcfff — light ice-blue)
- storm `DC_DIR`: `teal` (#1abc9c — saturated green-teal)

Both colors exist in both palettes with the same hexes, but by *choosing* different names per flavor, the rendered output differs in hue.

For themes where accents differ subtly (catppuccin dark flavors), we anchor each flavor to a **different color family** for the navigation/link roles:

| Flavor | DC_DIR/GC_BRANCH | DC_LINK/GC_FRAG | Identity |
|--------|-----------------|----------------|---------|
| mocha | sapphire (blue-cyan) | mauve (lavender-purple) | warm purple |
| macchiato | sky (light cyan) | lavender (blue-purple) | cool navy |
| frappe | teal (green-cyan) | blue (soft blue) | slate |
| latte | sapphire | mauve | naturally distinct (light theme) |

### When hex differences are enough

Themes where shared `_roles` gives sufficient differentiation:

- **Monokai** — 7 filters have deliberately distinct backgrounds and accent palettes (machine is electric-blue-tinted, ristretto is warm/desaturated, spectrum is near-black with vivid accents). The `BG` pill carries the identity difference automatically.
- **Bearded** — 63 flavors with very different palettes per flavor. The shared role names resolve to completely different hex values.
- **Gruvbox** — dark vs light is structurally different (even without per-flavor roles, the `BG` hex contrast is extreme: `#282828` vs `#fbf1c7`).
- **Flexoki** — dark `bg` = `#100F0F` (near-black), light `bg` = `#FFFCF0` (warm paper). Same role name, completely different hex.

### Applying this to a new theme

1. Find the nvim `Normal` bg key → that's `BG`
2. Find the nvim `Normal` fg key → that's `TEXT`
3. Set `FG` = same key as `BG` (dark text on bright accent pills works for both dark and light themes)
4. If flavors share accent hex values → use per-flavor `_roles` with different color name choices
5. If flavors have genuinely different accent palettes → shared `_roles` is fine, `BG` carries the identity

### Delta diff colors — the structural / syntax split

Delta has two separate color layers and they are owned by different systems:

**Structural colors (owned by our palette):**

| Delta option | Source |
|---|---|
| `plus-style` / `minus-style` background | 15% blend of `GC_NEW`/`GC_OLD` into `BG` |
| `plus-emph-style` / `minus-emph-style` background | 30% blend (stronger, for emphasized hunks) |
| `line-numbers-plus/minus-style` | `GC_NEW` / `GC_OLD` |
| `line-numbers-zero-style` | `GC_META` |
| `line-numbers-left/right-style` | `GC_FRAG` |
| `file-style` / `file-decoration-style` | `GC_BRANCH` |
| `hunk-header-style` / `hunk-header-decoration-style` | `GC_META` / `GC_FRAG` |

These are written into `[delta "theme-colors"]` in `git/theme.conf` by `render-theme.py` at every `set-theme` call. The backgrounds are computed (not stored in roles) by blending the relevant GC color into BG at the given alpha.

**Syntax highlighting (owned by delta/bat):**

The code text *inside* each diff hunk is syntax-highlighted by delta using a bat theme. Delta doesn't expose per-token coloring from an external source — only a theme name. This is stored in `_delta.syntax_theme` per flavor in `roles.json`/`palettes.json` and written as `syntax-theme = <name>` into `[delta "theme-colors"]`.

For flavors with no matching bat theme (bearded and flexoki), `render-theme.py` auto-selects `TwoDark` (dark BG) or `GitHub` (light BG) based on the perceived luminance of `BG`. If you install additional bat themes (e.g. catppuccin/bat, tokyonight/bat), the named `syntax-theme` values will automatically activate them without any changes needed here.

**Implication for new components:** any diff-related component you add can reuse the existing `GC_*` colors. The background blending helpers (`_blend_hex`, `_is_dark`) in `render-theme.py` are available for deriving subtle tints from any existing role.

### nvim-only flavors

Some flavors cannot provide static hex colors because their palettes are computed at runtime in Lua (e.g. tokyonight `day`, which inverts the `night` palette via `Util.invert()`). These are registered in `roles.json` and `palettes.json` with only `_delta` metadata and no color entries.

When `render-theme.py` encounters a flavor with an empty palette it:
1. Still writes `nvim/theme.lua` (so Neovim gets the correct colorscheme)
2. Checks for a `_terminal_fallback` key (see below) — if present, uses that flavor's terminal colors
3. Otherwise skips all template rendering (starship, dircolors, git/theme.conf) with a warning
4. Exits successfully — the previous terminal colors remain active (or fallback colors are applied)

This means `set-theme --theme tokyonight --flavor day` is valid and safe: Neovim switches to the day (light) colorscheme, and the Starship prompt/`ls`/`git` colors are re-rendered using the `moon` fallback.

**`_terminal_fallback`** — specify another flavor of the same theme to use for terminal rendering when the selected flavor has no static palette:

```json
"day": {
  "_delta": { "syntax_theme": "tokyonight_day" },
  "_terminal_fallback": "moon"
}
```

`render-theme.py` will render starship, dircolors, and git templates using the fallback flavor's palette, but keep the original flavor's `_delta.syntax_theme` so bat/delta uses the correct highlighting in diffs. The nvim colorscheme is still set to `day`.

To add an nvim-only flavor without a fallback, add it to `roles.json` with only `_delta` (and optionally `_nvim` overrides if needed) and no `_roles`. Do not add color data to `palettes.json` — the empty-palette guard handles the rest.

### Flavor naming conventions

Most themes use simple flavor names (`dark`, `light`, `mocha`, `storm`). Gruvbox uses a compound naming scheme to encode both background and contrast in a single flavor string: `dark`, `dark-hard`, `dark-soft`, `light`. `init.lua` parses the suffix to derive `vim.o.background` and the `contrast` value passed to `require("gruvbox").setup()`. New themes that have both a dark/light axis and a contrast/density axis should follow the same `{bg}-{contrast}` pattern rather than adding a separate `variant_key`.

### Adding a color-able component (beyond prompt/gc/dc)

If you want to colorize a new terminal component (e.g. tmux status line, fzf colors, bat theme):

1. Add new placeholder keys to the relevant template (e.g. `{{COLOR_COMPONENT_KEY}}`)
2. Add corresponding role keys to `_roles` in `roles.json` (e.g. `"COMP_KEY": "accent5"`)
3. In `render-theme.py`'s `_apply_templates`, collect your new roles and call `_render_template` with a substitution dict
4. The same `BG`/`TEXT` roles are available — reuse them for any component that should reflect the theme identity
5. For per-flavor differentiation: add your new role to each flavor's `_roles` rather than the shared one

---

## Managing palettes.json

`palettes.json` is committed to the repo. It is **not** regenerated at install time — users just get the version the repo owner committed. This guarantees consistency across all installs.

### When to regenerate

- You added a new theme or flavor to `roles.json`
- A theme plugin updated and changed its color names
- You want to pick up new bearded flavor slugs

### How to regenerate (repo owner only)

Make sure the Neovim plugins are up to date first:

```bash
nvim --headless "+Lazy! sync" +qa
```

Then run:

```bash
# From the repo root — writes to src/.config/palettes.json automatically
python3 src/get-colors.py --export

# Or to a custom path
python3 src/get-colors.py --export --output /tmp/palettes-preview.json
```

Inspect the output, then commit:

```bash
git add src/.config/palettes.json
git commit -m "chore: refresh palettes.json"
```

### Verifying extraction accuracy

Run this after any regeneration to confirm every color name referenced in `roles.json` actually resolves to a hex value in the extracted palette. Catches mismatched color names before they silently produce empty/fallback colors at theme-switch time.

```bash
# From the repo root — requires plugins installed (Lazy sync done)
python3 - << 'PYEOF'
import subprocess, json, os

REPO   = "."                                        # adjust if running from elsewhere
LAZY   = os.path.expanduser("~/.local/share/nvim/lazy")
script = f"{REPO}/src/get-colors.py"
roles  = json.load(open(f"{REPO}/src/.config/roles.json"))
pals   = json.load(open(f"{REPO}/src/.config/palettes.json"))

def run_palette(theme, flavor):
    env = {**os.environ, "SHOW_COLORS_THEMES_DIR": LAZY}
    r = subprocess.run(["python3", script, "palette", theme, flavor],
                       env=env, capture_output=True, text=True)
    return {p.split()[0]: p.split()[1]
            for p in r.stdout.splitlines()
            if len(p.split()) == 2 and p.split()[1].startswith("#")}

def needed_names(roles_def):
    names = set(roles_def.get("SEG", []))
    for k in ("FG","OK","ERR","WARN","BG","TEXT"):
        if roles_def.get(k): names.add(roles_def[k])
    for k, v in roles_def.items():
        if (k.startswith("DC_") or k.startswith("GC_")) and v:
            names.add(v)
    return names

ok = fail = 0
for theme in sorted(roles):
    if theme.startswith("_"): continue
    t = roles[theme]
    for flavor in sorted(k for k in pals.get(theme,{}) if not k.startswith("_")):
        fdata = t.get(flavor, {})
        roles_def = fdata.get("_roles") or t.get("_roles", {})
        missing = needed_names(roles_def) - set(run_palette(theme, flavor))
        if missing:
            print(f"FAIL  {theme}/{flavor}: missing {sorted(missing)}")
            fail += 1
        else:
            ok += 1

print(f"\n{'ALL OK' if not fail else 'FAILURES FOUND'}: {ok} ok, {fail} failed")
PYEOF
```

**What a FAIL means:** a color name in `roles.json` doesn't appear in the extracted palette. Fix by:
1. Running `python3 src/get-colors.py --palette --theme <theme> --flavor <flavor>` to see what names are actually available
2. Updating the role name in `roles.json` to match
3. Re-running `python3 src/get-colors.py --export` then re-verifying

Users get the update on their next `sudo init-dotfiles.sh install user <name>` or `git pull` + redeploy.

---

## Adding a new theme — step by step

After following this guide, `set-theme --theme mytheme` will update the Starship prompt, `ls` colors, `git diff`/`git status` colors, and Neovim — all at once.

### 1. Install the Neovim plugin

Add the plugin to `src/.config/nvim/init.lua` in the theme plugins block (search for `lazy = false`):

```lua
{
    "author/mytheme.nvim",
    lazy = false,
    priority = 1000,
    config = function()
        if vim.g.active_theme == "mytheme" then
            require("mytheme").setup({ style = vim.g.mytheme_style })
            vim.cmd("colorscheme mytheme")
        end
    end,
},
```

The `vim.g.active_theme` guard ensures only the active theme runs its `colorscheme` call — all others load silently. Then install:

```bash
nvim --headless "+Lazy! sync" +qa
```

### 2. Inspect the palette

```bash
# Visual swatch — see all colors at a glance
python3 src/get-colors.py --show --theme mytheme --flavor dark

# Raw name/hex pairs — the exact names you will use in roles.json
python3 src/get-colors.py --palette --theme mytheme --flavor dark
```

From the output, identify a color for each role. The mapping logic:

| Role(s) | What to pick | Typical key names |
|---------|-------------|-------------------|
| `BG` | Editor background — nvim `Normal` bg. The one color that makes a flavor instantly recognizable. | `bg`, `base`, `background`, `uibackground` |
| `TEXT` | Editor body text — nvim `Normal` fg. Must contrast with `BG`. | `fg`, `text`, `default`, `fujiWhite` |
| `FG` | Text on accent pills (SEG1–SEG5). Use a near-black/near-white, often the same key as `BG`. | same as `BG`, or a near-black/paper-white |
| `SEG` (×6) | 6 vibrant accent colors for segment backgrounds, left→right. | any 6 distinct accents |
| `OK`, `GC_ADDED`, `GC_NEW`, `DC_EXEC`, `DC_SOURCE` | Green-ish | `green`, `success`, `bright_green` |
| `ERR`, `GC_UNTRACKED`, `GC_OLD` | Red-ish | `red`, `danger`, `bright_red` |
| `WARN`, `GC_CHANGED`, `GC_ARCHIVE` | Orange or warm yellow | `orange`, `warning`, `bright_orange` |
| `GC_META`, `GC_TAG`, `DC_TEXT` | Yellow or secondary accent | `yellow`, `bright_yellow` |
| `GC_FRAG`, `DC_LINK`, `DC_MEDIA` | Purple or violet | `purple`, `mauve`, `violet` |
| `GC_BRANCH`, `DC_DIR` | Cyan or blue | `cyan`, `teal`, `sapphire`, `blue` |
| `GC_REMOTE`, `GC_CHANGED`, `DC_ARCHIVE` | Orange | `orange`, `peach` |
| `DC_IMAGE` | Pink or red | `pink`, `red`, `maroon` |
| `DC_DOC` | Blue or sky | `blue`, `sky`, `sapphire` |
| `DC_DIMMED` | Muted gray or overlay | `gray`, `overlay0`, `fujiGray` |

> **Bearded:** 60+ flavors but consistent names across all of them (`red`, `orange`, `purple`, `green`, `blue`, `turquoize`, `primary`, `success`, `danger`, `warning`, `border`, `pink`, `yellow`). One shared `_roles` covers all 60+ flavors.

> **Kanagawa:** wave/dragon/lotus use different name conventions because the extractor strips flavor prefixes. Run `--palette kanagawa wave`, `--palette kanagawa dragon`, `--palette kanagawa lotus` separately and use the stripped names you see in each output.

### 3. Add the role mapping to roles.json

**First, decide: shared `_roles` or per-flavor?**

| Situation | Use |
|-----------|-----|
| Flavors have genuinely distinct accent hex values (monokai, bearded) | Shared `_roles` at theme level — `BG` carries the identity automatically |
| Flavors share all accent hex values (tokyonight night/storm) | Per-flavor — choose *different color names* to force visible distinction |
| Flavors have subtly similar accents (catppuccin dark flavors) | Per-flavor — anchor each flavor to a different color family |
| Theme has a dark + light split | Per-flavor — `BG`/`TEXT` keys differ and must be specified separately |

**Shared `_roles` (single flavor or flavor-invariant accents):**

```json
"mytheme": {
    "_default_flavor": "dark",
    "_delta": { "syntax_theme": "Mytheme Dark" },
    "_nvim": { "theme": "mytheme", "variant_key": "mytheme_style" },
    "_roles": {
        "BG":   "bg_editor",
        "TEXT": "fg_editor",
        "SEG": ["accent_red", "accent_orange", "accent_yellow", "accent_green", "accent_cyan", "accent_purple"],
        "FG": "bg_editor",
        "OK": "accent_green",   "ERR": "accent_red",    "WARN": "accent_yellow",
        "DC_DIR":     "accent_cyan",    "DC_LINK":    "accent_purple",
        "DC_EXEC":    "accent_green",   "DC_SOURCE":  "accent_green",
        "DC_TEXT":    "accent_yellow",  "DC_IMAGE":   "accent_red",
        "DC_MEDIA":   "accent_purple",  "DC_ARCHIVE": "accent_orange",
        "DC_DOC":     "accent_cyan",    "DC_DIMMED":  "muted_gray",
        "GC_ADDED":     "accent_green",   "GC_CHANGED":   "accent_orange",
        "GC_UNTRACKED": "accent_red",     "GC_BRANCH":    "accent_cyan",
        "GC_REMOTE":    "accent_orange",  "GC_TAG":       "accent_yellow",
        "GC_OLD":       "accent_red",     "GC_NEW":       "accent_green",
        "GC_META":      "accent_yellow",  "GC_FRAG":      "accent_purple"
    }
}
```

**Per-flavor `_roles` (flavor-specific accent name choices):**

```json
"mytheme": {
    "_default_flavor": "dark",
    "_nvim": { "theme": "mytheme", "variant_key": "mytheme_style" },
    "dark": {
        "_delta": { "syntax_theme": "Mytheme Dark" },
        "_roles": {
            "BG": "bg_dark", "TEXT": "fg_dark", "FG": "bg_dark",
            "SEG": ["dark_red", "dark_orange", "dark_yellow", "dark_green", "dark_cyan", "dark_purple"],
            "DC_DIR": "dark_cyan",  "GC_BRANCH": "dark_cyan",
            "GC_FRAG": "dark_purple", "DC_LINK": "dark_purple",
            ...
        }
    },
    "light": {
        "_delta": { "syntax_theme": "Mytheme Light" },
        "_roles": {
            "BG": "bg_light", "TEXT": "fg_light", "FG": "bg_light",
            "SEG": ["light_red", "light_orange", "light_yellow", "light_green", "light_teal", "light_mauve"],
            "DC_DIR": "light_teal", "GC_BRANCH": "light_teal",
            ...
        }
    }
}
```

**`_nvim` fields:**

| Field | What to put |
|-------|-------------|
| `_nvim.theme` | The `vim.g.active_theme` value written to `theme.lua` — matches the `if` guard in `init.lua` |
| `_nvim.variant_key` | The `vim.g.<key>` variable written for the flavor — matches what `init.lua` reads (e.g. `mytheme_style`) |
| `_delta.syntax_theme` | bat/delta theme name for code syntax highlighting in diffs — set per flavor for themes with dark/light variants; use `""` to auto-select `TwoDark`/`GitHub` based on `BG` luminance |

**`init.lua` block** — add a guarded config entry to `src/.config/nvim/init.lua` alongside the other theme plugins:

```lua
{
    "author/mytheme.nvim",
    lazy = false, priority = 995,
    config = function()
        if vim.g.active_theme == "mytheme" then
            require("mytheme").setup({ style = vim.g.mytheme_style or "dark" })
            vim.cmd.colorscheme("mytheme-" .. (vim.g.mytheme_style or "dark"))
        end
    end,
},
```

### 4. Regenerate palettes.json

```bash
# Sync plugins first if you just added one
nvim --headless "+Lazy! sync" +qa

# Regenerate — writes to src/.config/palettes.json automatically
python3 src/get-colors.py --export
```

Verify the entry is present:

```bash
python3 -c "
import json
d = json.load(open('src/.config/palettes.json'))
print(list(d['mytheme'].keys()))
"
```

Expected: your flavor names plus `_default_flavor`, `_nvim`, `_delta`, `_roles`.

### 5. Deploy and test

```bash
# Deploy to the active shell
cp src/.config/roles.json    ~/.config/roles.json
cp src/.config/palettes.json ~/.config/palettes.json
source ~/.bashrc

# Apply the theme — all outputs rendered in one call
set-theme --theme mytheme
set-theme --theme mytheme --flavor dark
```

**Verify starship** — prompt updates immediately; confirm no unreplaced placeholders:

```bash
grep "color_seg" ~/.config/starship.toml    # should show hex values, not {{...}}
```

**Verify dircolors** — `ls` colors update immediately:

```bash
mkdir /tmp/dc_test && cd /tmp/dc_test
touch file.py file.go file.md image.png archive.zip doc.pdf build.pyc
chmod +x file.py
ls --color=always -la
cd - && rm -rf /tmp/dc_test
```

**Verify git colors** — in any git repo:

```bash
git status                                  # colored added/modified/untracked
git diff                                    # colored diff with hunk highlighting
git log --oneline --graph --decorate -10    # colored branch/tag/remote decorations
git config --list | grep "^color\."         # all values should be hex, not empty
```

### 6. Commit

```bash
git add src/.config/nvim/init.lua
git add src/.config/roles.json
git add src/.config/palettes.json
git commit -m "feat: add mytheme theme"
```

### 7. Commit everything

```bash
git add src/.config/nvim/init.lua
git add src/.config/roles.json
git add src/.config/palettes.json
git commit -m "feat: add mytheme theme"
```

---

## Testing a theme

Use `preview-themes.py` to see all outputs at once without switching your active theme:

```bash
# Preview a single flavor — all outputs (dircolors, git status, git diff, prompt, nvim)
python3 src/preview-themes.py --theme mytheme --flavor dark --include-nvim
```

Or test each output manually:

### Dircolors test

```bash
mkdir /tmp/dc_test && cd /tmp/dc_test

# Create one file of each major category
touch main.py main.go main.rs main.ts            # source
touch README.md config.yaml .env Makefile        # text/config
touch photo.png screenshot.jpg icon.svg          # images
touch song.mp3 video.mp4 clip.mkv               # media
touch backup.zip archive.tar.gz package.deb     # archives
touch report.pdf slides.pptx spreadsheet.xlsx   # documents
touch debug.log build.pyc .cache                 # dimmed
chmod +x main.py                                 # executable

ls --color=always -la

cd - && rm -rf /tmp/dc_test
```

### Git colors test

In any git repo with changes:

```bash
# Status colors
git status

# Diff colors (added=green, removed=red, header=yellow, hunk=purple)
git diff

# Log decoration colors (branch=cyan, tag=yellow, remote=orange)
git log --oneline --graph --decorate -10

# Verify the underlying config
git config --list --show-origin | grep "^file.*color"
```

---

## preview-themes.py reference

Renders every theme/flavor to a set of temp files and shows the live output in the terminal. Useful for comparing themes side-by-side before committing to one.

```bash
# Default — shows dircolors (ls), git status, git diff (delta), starship prompt
python3 src/preview-themes.py
python3 src/preview-themes.py --theme catppuccin
python3 src/preview-themes.py --theme gruvbox --flavor light
python3 src/preview-themes.py --theme gruvbox --flavor light --starship-template powerline

# Restrict to one or more outputs
python3 src/preview-themes.py --prompt
python3 src/preview-themes.py --git-diff
python3 src/preview-themes.py --git-status
python3 src/preview-themes.py --dir-colors
python3 src/preview-themes.py --prompt --git-diff

# Add nvim preview to the loop — opt-in, launches nvim per combo
python3 src/preview-themes.py --include-nvim
python3 src/preview-themes.py --theme gruvbox --flavor light --include-nvim
python3 src/preview-themes.py --theme monokai --flavor machine --include-nvim
python3 src/preview-themes.py --theme catppuccin --flavor mocha --include-nvim --prompt

# --prompt without --starship-template cycles ALL available templates
python3 src/preview-themes.py --theme gruvbox --flavor dark --prompt
# --prompt with --starship-template shows only that template
python3 src/preview-themes.py --prompt --starship-template pills
```

**Output flags:**

| Flag | What it shows | On by default? |
|------|--------------|----------------|
| `--dir-colors` | `ls -lhA` listing with theme dircolors applied | Yes |
| `--git-status` | Sample git repo: staged / unstaged / untracked files | Yes |
| `--git-diff` | Sample Python diff rendered by delta with theme colors | Yes |
| `--prompt` | Starship prompt rendered via PTY (or subprocess fallback) | Yes |
| `--nvim` | Sample Python file with treesitter syntax highlighting — **selective** | **No — opt-in only** |
| `--include-nvim` | Same nvim preview — **additive** (adds nvim to whatever is shown, including defaults) | **No — opt-in only** |

Both flags are opt-in because they spawn one `nvim --headless` process per combo (~2–3 s each). Use `--theme` + `--flavor` to keep it fast.

```bash
# nvim only
preview-themes.py --nvim --theme gruvbox --flavor light

# full default set + nvim
preview-themes.py --include-nvim --theme gruvbox --flavor light

# nvim + prompt only
preview-themes.py --nvim --prompt --theme gruvbox --flavor light
```

**How the nvim preview works:**
1. A temp `XDG_CONFIG_HOME/nvim/theme.lua` is written with the target colorscheme and flavor
2. The installed `~/.config/nvim/init.lua` is copied into the same temp dir (so `stdpath("config")` resolves there without touching the live config)
3. `nvim --headless sample.py -c "luafile capture.lua"` is run — the embedded Lua script uses `query:iter_captures` from the treesitter highlight query to collect per-span colors, then writes ANSI-escaped output to a temp file
4. The ANSI output is printed; each line is padded to full terminal width with the theme background using `\e[K`

Requires: nvim installed, dotfiles installed (`~/.config/nvim/init.lua` present), treesitter parser for `python` compiled.

---

## get-colors.py reference

`src/get-colors.py` reads palette data directly from installed Neovim lazy plugins (`~/.local/share/nvim/lazy/` by default). Override with `--themes-dir PATH` or `SHOW_COLORS_THEMES_DIR=/path/to/lazy`.

```bash
# Visual display — live ANSI swatches, one color block per palette entry
python3 src/get-colors.py --show                                        # all themes
python3 src/get-colors.py --show --theme catppuccin                      # one theme, all flavors
python3 src/get-colors.py --show --theme catppuccin --flavor mocha       # one specific flavor
python3 src/get-colors.py --show --theme bearded --flavor milkshake-raspberry

# Role matrix — unified table: all themes × all flavors as rows, roles as columns.
# Each cell shows a live 24-bit ANSI swatch (██) + hex value.
# Reads from palettes.json — no plugins needed.
python3 src/get-colors.py --matrix --prompt | less -R                              # all themes, prompt roles
python3 src/get-colors.py --matrix --colors | less -R                              # all themes, DC_* / GC_*
python3 src/get-colors.py --matrix          | less -R                              # all themes, all roles
python3 src/get-colors.py --matrix --theme catppuccin                              # one theme, all flavors
python3 src/get-colors.py --matrix --theme catppuccin --flavor mocha               # single flavor
python3 src/get-colors.py --matrix --theme catppuccin --flavor mocha --prompt      # single flavor, prompt only

# Scripting: output "name hex" pairs (one per line)
python3 src/get-colors.py --palette --theme monokai --flavor spectrum
python3 src/get-colors.py --palette --theme kanagawa --flavor dragon
python3 src/get-colors.py --palette --theme gruvbox --flavor dark

# Generate/refresh palettes.json from installed plugins
python3 src/get-colors.py --export                               # auto-detects output path
python3 src/get-colors.py --export --output /tmp/palettes-preview.json
```

**`matrix`** reads `palettes.json` and prints one continuous table across all 110+ flavors — no Neovim plugins needed. Each row is `theme/flavor`, each column is a role. Two submodes keep the output scannable:

| Flag | Columns | Use for |
|---------|---------|---------|
| `--matrix --prompt` | SEG0–SEG5, BG, TEXT, FG, OK, ERR, WARN | Checking prompt color identity per flavor |
| `--matrix --colors` | DC_DIR…DC_DIMMED + GC_ADDED…GC_FRAG | Checking ls + git color assignments |
| `--matrix` (no flags) | All of the above | Full overview |
| `--matrix --theme NAME` | same as above, filtered | One theme, all its flavors |
| `--matrix --theme NAME --flavor NAME` | same as above, filtered | Single flavor only |

**`--export`**:
1. Locates `roles.json` (sibling `.config/` → `~/.config/roles.json`)
2. Calls `palette <theme> <flavor>` for every known flavor (no subprocess — pure Python)
3. Merges palette hex values with the existing `_roles`/`_nvim` structure
4. Writes `palettes.json` next to `roles.json` (or the path you specify with `--output`)

| Subcommand | Needs plugins |
|------------|--------------|
| `--show`, `--palette`, `--export` | Yes — reads live Lua files from `~/.local/share/nvim/lazy/` |
| `--matrix` | No — reads committed `palettes.json` |
