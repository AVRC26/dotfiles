# TODO

- [Terminal: Alacritty](#terminal-alacritty)
- [Terminal: Gogh color scheme integration](#terminal-gogh-color-scheme-integration)
- [Windows Setup Improvements](#windows-setup-improvements)
- [Neovim: Key Map](#neovim-key-map)
- [Neovim: Extras](#neovim-extras)
- [Neovim: Plugins](#neovim-plugins)
- [Git: Delta syntax-theme](#git-delta-syntax-theme)
- [Process Monitor](#process-monitor)
- [Dep reduction: zig + curl fonts + bash theme fallback](#dep-reduction-zig--curl-fonts--bash-theme-fallback)
- [Starship: Ensure All Templates Have These Modules](#starship-ensure-all-templates-have-these-modules)

---

## Terminal: Alacritty
- Evaluate and integrate Alacritty as the default terminal: https://github.com/alacritty/alacritty
- Cross-platform (Linux, macOS, Windows), GPU-accelerated, minimal, configured via YAML/TOML
- Wire `set-theme` to render an `alacritty.toml` color scheme from the active palette

## Terminal: Gogh color scheme integration
- Integrate Gogh terminal color scheme collection: https://github.com/Gogh-Co/Gogh
- Use as a source for mapping our theme palettes to terminal emulator profiles (GNOME Terminal, iTerm2, etc.)
- Evaluate generating Gogh-compatible output from `render-theme.py`

## Windows Setup Improvements
- Review and apply recommendations from https://takken.io/blog/a-modern-terminal-for-windows

## Neovim: Key Map
- Add which-key.nvim for keybinding help popup: https://github.com/folke/which-key.nvim

## Neovim: Extras
- Evaluate snacks.nvim: https://github.com/folke/snacks.nvim

## Neovim: Plugins
- **lualine.nvim** — https://github.com/nvim-lualine/lualine.nvim
  - Use the bubbles preset
  - Read README, identify all options not currently enabled, decide which to enable
- **bufferline.nvim** — https://github.com/akinsho/bufferline.nvim
  - Read README, identify all options not currently enabled, decide which to enable
- Remove vim-fugitive (likely redundant)
- Update credits section to list all used components

## Git: Delta syntax-theme

Delta diff colors are split across two systems. Our palette owns the structural layer (added/removed line backgrounds via blended `GC_NEW`/`GC_OLD`, line numbers via `GC_NEW`/`GC_OLD`/`GC_META`/`GC_FRAG`, file names and hunk headers via `GC_BRANCH`/`GC_META`/`GC_FRAG`). The code text *inside* each hunk is syntax-highlighted via `syntax-theme`, which uses bat's theme system — there is no way to feed our hex palette into per-token coloring directly.

### Current state

`_delta.syntax_theme` in `roles.json`/`palettes.json` maps each theme/flavor to its closest bat equivalent:

| Theme | bat theme used |
|-------|---------------|
| catppuccin frappe/latte/macchiato/mocha | `Catppuccin Frappe` / `Catppuccin Latte` / `Catppuccin Macchiato` / `Catppuccin Mocha` |
| gruvbox dark / light | `gruvbox-dark` / `gruvbox-light` (bat built-ins) |
| kanagawa wave/dragon/lotus | `kanagawa-wave` / `kanagawa-dragon` / `kanagawa-lotus` |
| monokai (all flavors) | `Monokai Extended` (bat built-in) |
| tokyonight storm/night/moon/day | `tokyonight_storm` / `tokyonight_night` / `tokyonight_moon` / `tokyonight_day` |
| bearded (all flavors) | `""` — auto-selects `TwoDark` (dark BG) or `GitHub` (light BG) via luminance check |
| flexoki dark / light | `flexoki-dark` / `flexoki-light` |

Catppuccin, kanagawa, tokyonight, and flexoki bat themes are **not built into bat/delta** — they require the user to install them separately (e.g. `catppuccin/bat`, `helix-editor/tokyonight`). If the named theme is missing, delta silently falls back to its default (`Monokai Extended`). Built-in themes (gruvbox, Monokai Extended) work out of the box.

### Options to decide

1. **Keep current mapping** — best readability when the bat theme is installed; degrades gracefully to Monokai Extended otherwise. Requires per-theme maintenance as new themes are added.

2. **Drop `syntax-theme` entirely** — delta always uses `Monokai Extended`. No per-theme mapping needed, no install requirement. Diff structure (backgrounds, line numbers, headers) is still ours; only code text coloring regresses.

3. **Switch to `syntax-theme = ansi`** — delta uses the terminal's 16 ANSI colors for code text. This would be "our colors" end-to-end *only if* we also theme the terminal ANSI color slots (colors 0–15) per theme. We currently do not do this. Prerequisite: add ANSI color role mappings (`ANSI_0`–`ANSI_15`) to `roles.json`, add a terminal profile template (e.g. Windows Terminal `colorScheme` JSON, minttyrc color entries), and wire them through `render-theme.py`. This is the most integrated path but also the largest scope.

### Decision needed

If going with option 3 (ansi): scope out the Windows Terminal JSON color scheme template and minttyrc integration first — that unlocks consistent 16-color theming across all tools (delta, fzf, bat, any ANSI-aware CLI) without per-tool theme name maintenance.

## Process Monitor
- Add btop for process/system monitoring: https://github.com/aristocratos/btop

## Dep reduction: zig + curl fonts + bash theme fallback
Plan: [src/plans/bash-fallback-zig-fonts.md](plans/bash-fallback-zig-fonts.md)

- [x] WS1 — `install_zig()` in `init-dotfiles.sh`; add `compilers={"zig"}` to `nvim/init.lua`; remove gcc prereq
- [ ] WS2 — Rewrite `install_nerd_font()` to curl individual `.ttf` files; remove unzip prereq
- [ ] WS3 — Add `generate-sh` subcommand to `render-theme.py`; generate and commit `palettes.sh`
- [ ] WS4 — Write `render-theme.sh` bash fallback
- [ ] WS5 — Wire python-first / bash-fallback in `apply_dotfiles()` and `set-theme` wrapper
- [ ] WS6 — Update `README.md`, `src/README.md`, `src/THEMES.md`

## Starship: Ensure All Templates Have These Modules
Review every template under `.config/starship/` and confirm the following modules are present
(location/order within the template doesn't matter):

### Identity
- OS
- Username
- Hostname

### Directory
- Directory (`truncate_to_repo = false`)

### Version Control
- Git Branch
- Git Status (`disabled = false`, `format = '([\[$all_status$ahead_behind$\]]($style) )'`)
- Git Metrics

### Languages / Runtimes / Tools
- AWS
- C
- CPP
- CMake
- Container
- Docker Context
- Kubernetes
- Helm
- Java
- Lua
- Maven
- Node.js
- OpenStack
- Package Version
- PHP
- Python
- Shell
- SHLVL
- Terraform
- Zig

### System / Shell
- Jobs
- Memory Usage
- Character
- Time
- Command Duration
- Status
