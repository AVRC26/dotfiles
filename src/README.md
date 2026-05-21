# dotfiles — full reference

This document is the comprehensive reference for everything in `src/`. For the quick-start guide see the [top-level README](../README.md).

---

## Contents

- [State files](#state-files)
- [Profiles](#profiles)
- [Theme system](#theme-system)
- [Development — linting and tests](#development--linting-and-tests)
- [Terminal font (Nerd Font)](#terminal-font-nerd-font)
- [Neovim key bindings](#neovim-key-bindings)
- [Neovim plugins](#neovim-plugins)
- [Shell extras](#shell-extras)
- [LSP (optional)](#lsp-optional)
- [Troubleshooting](#troubleshooting)

---

## State files

Every file deployed by the installer is recorded so uninstall is deterministic.

**System state: `/var/lib/dotfiles/`**

```
/var/lib/dotfiles/
  platform          ← "linux" or "win"
  mode              ← "system"
  binary_dir        ← "/usr/local/bin"
  opt_dir           ← "/opt"
  repo_base         ← "/usr/local/share/dotfiles"
  bootstrapped_at   ← ISO-8601 timestamp
  binaries/
    rg              ← installed version
    fzf             ← installed version
    nvim            ← installed version
    nvim_pkg        ← e.g. "nvim-linux-x86_64"
    starship        ← installed version
  users/
    root/
      installed_at
      home          ← "/root"
      files         ← one absolute path per line
    alice/
      installed_at
      home          ← "/home/alice"
      files         ← one absolute path per line
```

**User-local state: `~/.local/state/dotfiles/`** — same layout, `mode = user-local`.

Before removing shared tools `uninstall --all` checks `users/` and exits with an error if any consumers are still registered. Uninstall each consumer first, or use `--force` to skip the check and remove everything in one go.

---

## Profiles

All Linux installs (bare metal, VM, or WSL) use `src/` as the single dotfile source. The role only controls the default theme and whether `.minttyrc` is deployed (root skips it).

| File | Contents |
|------|---------|
| `.bashrc` | History, PATH, aliases, theme switcher, fzf bindings, starship init |
| `.gitconfig` | Git colours via include, aliases, `editor = nvim` — no `[user]` block (prompted at install time) |
| `.config/nvim/init.lua` | Neovim — lazy.nvim, all themes, all plugins |
| `.config/nvim/lazy-lock.json` | Pinned plugin commit SHAs — run `:Lazy restore` to reproduce exact versions |
| `.config/starship/` (6 templates) + `dircolors-template` + `gitcolors-template` + `roles.json` | Theme templates and role definitions |
| `.config/palettes.json` | Pre-generated color palette cache (all themes/flavors) |
| `.minttyrc` | mintty terminal config (non-root only) |

| Role | Default theme | Notes |
|------|--------------|-------|
| `install root` | Gruvbox (dark) | Warm earthy tones; visually distinct from user shells |
| `install user` / `--user-local` | Monokai Pro **Spectrum** | |

Override the default with `--theme` / `--flavor` on first install (ignored on re-install to preserve the user's active theme):

```bash
sudo ./init-dotfiles.sh install root  --theme catppuccin --flavor frappe
sudo ./init-dotfiles.sh install user alice --theme kanagawa --flavor wave
./init-dotfiles.sh install --user-local --theme gruvbox --flavor dark
```

If `--theme` is given without `--flavor`, the theme's own default flavor from `palettes.json` is used — the role default (`spectrum` for user, `light` for root) only applies when the theme is also at its role default. For example, `--theme flexoki` resolves to `flexoki/dark` without requiring an explicit `--flavor dark`.

`theme.lua` is written at install time and read by both Neovim and `.bashrc` on every startup. `set-theme` updates it immediately.

---

## Theme system

`set-theme` switches the Neovim colorscheme, Starship prompt, `ls` colors, and `git diff`/`git status` colors together. Theme color data is pre-generated and committed to the repo — no Neovim plugins are needed at switch time.

**Full reference** → **[THEMES.md](THEMES.md)** covers:
- How to use `set-theme` with every theme and flavor
- Architecture: `palettes.json`, `roles.json`, and the three templates
- The complete color role reference (Starship, dircolors, git)
- How to regenerate `palettes.json` (`python3 src/get-colors.py --export`)
- Step-by-step guide for adding a new theme (including Neovim plugin, roles.json entry, and testing all three outputs)

### Preview all themes

`src/preview-themes.py` renders every theme/flavor combination and displays the results — nothing in your active config is modified.

```bash
python3 /usr/local/share/dotfiles/src/preview-themes.py [--theme T] [--flavor F] [--starship-template N] [--prompt] [--git-diff] [--dir-colors]
```

**What it shows** — pass one or more output flags to restrict; omit all three to show everything:

| Flag | Shows |
|------|-------|
| *(none)* | starship prompt + git diff + dircolors |
| `--prompt` | starship prompt |
| `--git-diff` | git diff via delta |
| `--dir-colors` | `ls -lhA` with theme colors |

**Filtering**:

```bash
# All themes, all outputs
python3 preview-themes.py

# One theme (all its flavors)
python3 preview-themes.py --theme catppuccin

# One specific combination
python3 preview-themes.py --theme gruvbox --flavor dark-hard
```

**Prompt template options**:

```bash
# Cycle ALL prompt templates for a given theme/flavor (most useful)
python3 preview-themes.py --theme gruvbox --flavor dark --prompt

# Use one specific template
python3 preview-themes.py --prompt --starship-template pills

# No --starship-template + no --prompt: uses your currently active template
python3 preview-themes.py --theme gruvbox
```

**Available templates:** `powerline` · `pills` · `nerd-font` · `dracula` · `seeker` · `moir` · `sanmue` · `sepan`

**Requirements:** `starship` on `PATH` for `--prompt`; `git` + `delta` for `--git-diff`; `ls` + `dircolors` for `--dir-colors`. nvim-only flavors (e.g. `tokyonight day`) are skipped automatically.

---

## Development — linting and tests

All Python source lives in `src/`. Tools are configured in `src/pyproject.toml`.

### Prerequisites

```bash
pip install ruff mypy pytest pytest-cov
```

### Linting

```bash
cd src

# Style + static analysis (E/F/W/I/UP/B/SIM rules, line-length 100)
python -m ruff check .

# Type checking (non-strict, check_untyped_defs = true)
python -m mypy get-colors.py render-theme.py preview-themes.py
```

Both must be clean before committing. The `pyproject.toml` target is Python 3.11.

### Tests

```bash
cd src

# Run all tests
python -m pytest tests/ -v

# With coverage report (fails if overall < 90 %)
python -m pytest tests/ --cov=. --cov-report=term-missing

# Run only one test file
python -m pytest tests/test_get_colors.py -v
python -m pytest tests/test_preview_themes.py -v
python -m pytest tests/test_render_theme.py -v
```

**Test files:**

| File | What it covers |
|------|---------------|
| `tests/test_get_colors.py` | Palette extraction (catppuccin, gruvbox, kanagawa, monokai, bearded, tokyonight, flexoki, bamboo, oasis, onedarkpro), `cmd_show`, `cmd_palette`, `cmd_matrix` (including filter flags), `cmd_export`, `_default_themes_dir`, display helpers |
| `tests/test_preview_themes.py` | `_build_combos`, `_find_cfg`, `_active_starship_template`, `_find_nvim_init`, `_write_nvim_theme_lua`, main() integration (render failure, keyboard interrupt, flag variants) |
| `tests/test_render_theme.py` | `_load_palette`, `_resolve_theme_flavor`, `_validate_hex`, `_blend_hex`, `_is_dark`, `_render_template`, `_write_nvim_theme`, `cmd_apply`, `cmd_set_theme`, `cmd_help` |

### Quick one-liner

```bash
cd src && python -m ruff check . && python -m mypy get-colors.py render-theme.py preview-themes.py && python -m pytest tests/ -q
```

---

## Terminal font (Nerd Font)

The bootstrap installs two fonts automatically on Linux (including WSL):

| Font | Role |
|------|------|
| **FiraCode Nerd Font** | Primary coding font — all text and most glyphs |
| **Symbols Nerd Font Mono** | Glyphs-only fallback — the OS uses this for any codepoint missing from FiraCode |

Installed to: system → `/usr/local/share/fonts/NerdFonts`, user-local → `~/.local/share/fonts/NerdFonts`.

For macOS, install **both fonts** on the host OS yourself, then point your terminal at FiraCode.

Without a Nerd Font, file/folder/git glyphs in `nvim-tree`, `bufferline`, and `lualine` render as `□` boxes.

### Linux desktop terminals (gnome-terminal, kitty, alacritty, wezterm)

The bootstrap automatically installs both fonts. Set the font in your terminal preferences to **`FiraCode Nerd Font Mono`** (or `FiraCodeNL Nerd Font Mono`). Open a new tab to apply.

### Windows Terminal (WSL)

1. Install **Windows Terminal** from the Microsoft Store.
2. Settings (`Ctrl+,`) → your Ubuntu/WSL profile → **Appearance** → Font face → `FiraCode NFM` → Font size `12` → Save.
3. To make WSL your default: Settings → Startup → Default profile → pick your distro.

> **Note:** Fonts are installed into the WSL filesystem (`~/.local/share/fonts` or `/usr/local/share/fonts`). Windows Terminal reads fonts from the Windows font store, so you also need to install both `FiraCode.zip` and `NerdFontsSymbolsOnly.zip` **on the Windows host** ([Nerd Fonts releases](https://github.com/ryanoasis/nerd-fonts/releases/latest)) for them to appear in Windows Terminal's font picker.

### MobaXterm (Windows)

Both fonts must be installed **for all users** on Windows *and* FiraCode must be set in two places in MobaXterm.

**1. Install both fonts system-wide on Windows:**

From the [Nerd Fonts releases page](https://github.com/ryanoasis/nerd-fonts/releases/latest):

1. Download **`FiraCode.zip`** → extract → select all `.ttf` files → right-click → **Install for all users**.
2. Download **`NerdFontsSymbolsOnly.zip`** → same steps.

**2. Set MobaXterm to use it (both locations required):**

- **Global default:** `Settings` → `Configuration` → `Terminal` tab → "Default font" → pick **`FiraCode NFM`** → OK.
- **Per-session:** right-click your session → `Edit session` → `Terminal settings` tab → "Font" → pick **`FiraCode NFM`** → OK.

Use the `NFM` variant (Nerd Font Mono). Close all open tabs and reopen.

### macOS

```bash
brew install --cask font-fira-code-nerd-font
brew install --cask font-symbols-only-nerd-font
```

Or manually: download `FiraCode.zip` and `NerdFontsSymbolsOnly.zip` from the [release page](https://github.com/ryanoasis/nerd-fonts/releases/latest), extract, double-click every `.ttf` → "Install Font".

- **Terminal.app:** `Terminal` → `Settings…` → profile → `Text` tab → Change… → pick **`FiraCode Nerd Font Mono`**.
- **iTerm2:** `Profiles` → profile → `Text` → font → pick **`FiraCode Nerd Font Mono`**.

### Verify

Inside nvim:

```
:lua print(require'nvim-web-devicons'.get_icon('init.lua', 'lua'))
```

Should print a Lua glyph. For a full visual check:

```
:NvimWebDeviconsHiTest
```

---

## Neovim key bindings

Leader key is `,`.

| Key | Action |
|-----|--------|
| `Ctrl+P` | Telescope: find files |
| `,f` | Telescope: live grep (ripgrep) |
| `,b` | Telescope: open buffers |
| `,t` | Telescope: grep word under cursor |
| `Ctrl+N` | Toggle file tree (nvim-tree) |
| `Shift+N` / `Shift+P` | Next / previous buffer |
| `Shift+T` / `Shift+X` | New buffer / close buffer |
| `Shift+V` / `Shift+H` | Vertical / horizontal split |
| `Space` | Toggle fold (all levels) |
| `Ctrl+X` | Toggle fold (one level) |
| `Ctrl+N Ctrl+N` | Toggle line numbers |
| `w!!` *(command mode)* | Write with sudo |

---

## Neovim plugins

All plugins are managed by lazy.nvim and defined in `src/.config/nvim/init.lua`. They install on first `nvim` launch, or via `:Lazy sync`.

**Version pinning:** `src/.config/nvim/lazy-lock.json` is committed to this repo. Run `:Lazy restore` inside Neovim to install the exact pinned commit of every plugin. Run `:Lazy update` to upgrade and write a new lockfile, then commit it.

> **Tree-sitter:** parsers are compiled using `zig`, which the installer fetches automatically. No `gcc` required.

### lazy.nvim

**[folke/lazy.nvim](https://github.com/folke/lazy.nvim)** — plugin manager.

| Command | Effect |
|---------|--------|
| `:Lazy` | Open UI |
| `:Lazy sync` | Install missing, update existing, remove unused |
| `:Lazy update` | Update all plugins |
| `:Lazy clean` | Remove unused plugins |
| `:Lazy health` | Run health checks |
| `:Lazy profile` | Show startup time per plugin |

Inside `:Lazy`: `Enter` expand, `u` update, `x` clean, `q` close, `?` help.

#### Theme plugins

All theme plugins load on startup (`lazy = false`); only the active theme fires its `colorscheme` call.

**[Catppuccin](https://github.com/catppuccin/nvim)** — `catppuccin/nvim` — **user default** (Mocha).

| Flavour | Style |
|---------|-------|
| `mocha` | Darkest — **user default** |
| `macchiato` | Dark |
| `frappe` | Medium dark |
| `latte` | Light |

**[Gruvbox](https://github.com/ellisonleao/gruvbox.nvim)** — `ellisonleao/gruvbox.nvim` — **root default** (dark).

**[Monokai Pro](https://github.com/loctvl842/monokai-pro.nvim)** — `loctvl842/monokai-pro.nvim`. Filters: `spectrum` (default), `classic`, `octagon`, `pro`, `machine`, `ristretto`.

**[Kanagawa](https://github.com/rebelot/kanagawa.nvim)** — `rebelot/kanagawa.nvim`. Variants: `wave` (default), `dragon`, `lotus`.

**[Bearded](https://github.com/Ferouk/bearded-nvim)** — `Ferouk/bearded-nvim`. 60+ flavors. Default: `arc`. Change live in Neovim: `:BeardedReload <slug>`.

**[Flexoki](https://github.com/kepano/flexoki-neovim)** — `kepano/flexoki-neovim`. Styles: `dark` (default), `light`.

**[Tokyo Night](https://github.com/folke/tokyonight.nvim)** — `folke/tokyonight.nvim`. Styles: `night` (default), `storm`, `moon`, `day`.

### Tree-sitter

**[nvim-treesitter/nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter)** — accurate syntax highlighting.

Parsers installed automatically: `python`, `hcl`, `javascript`, `typescript`, `tsx`, `css`, `json`, `jsonc`, `bash`, `lua`, `markdown`.

Add a parser: `:TSInstall <lang>`. List all: `:TSInstallInfo`.

### Telescope

**[nvim-telescope/telescope.nvim](https://github.com/nvim-telescope/telescope.nvim)** — fuzzy finder. Requires ripgrep for live grep.

Inside a picker: `Ctrl+N`/`↓` down · `Ctrl+P`/`↑` up · `Enter` open · `Ctrl+V` vsplit · `Ctrl+X` split · `Esc` close · `?` all mappings.

### nvim-tree

**[nvim-tree/nvim-tree.lua](https://github.com/nvim-tree/nvim-tree.lua)** — file explorer. Toggle: `Ctrl+N`

| Key | Action |
|-----|--------|
| `Enter` / `o` | Open / expand-collapse |
| `a` | New file or dir (end with `/` for dir) |
| `d` / `r` | Delete / rename |
| `x` / `c` / `p` | Cut / copy / paste |
| `y` / `Y` / `gy` | Filename / relative path / absolute path |
| `R` | Refresh |
| `H` / `I` | Toggle dotfiles / gitignored |
| `g?` | All key mappings |

### bufferline.nvim

**[akinsho/bufferline.nvim](https://github.com/akinsho/bufferline.nvim)** — open buffers as a tab bar.

`Shift+N`/`Shift+P` next/prev · `Shift+T`/`Shift+X` new/close.

Commands: `:BufferLinePick` · `:BufferLinePickClose` · `:BufferLineSortByDirectory`

### lualine.nvim

**[nvim-lualine/lualine.nvim](https://github.com/nvim-lualine/lualine.nvim)** — status bar. Uses `theme = "auto"` — picks up the active colorscheme automatically.

### indent-blankline.nvim

**[lukas-reineke/indent-blankline.nvim](https://github.com/lukas-reineke/indent-blankline.nvim)** — vertical indent guides.

Commands: `:IBLToggle` · `:IBLToggleScope`

### gitsigns.nvim

**[lewis6991/gitsigns.nvim](https://github.com/lewis6991/gitsigns.nvim)** — gutter signs for added (`│` green), changed (`│` yellow), deleted (`_`/`‾` red).

```lua
local gs = require("gitsigns")
vim.keymap.set("n", "]c", gs.next_hunk)
vim.keymap.set("n", "[c", gs.prev_hunk)
vim.keymap.set("n", "<leader>hs", gs.stage_hunk)
vim.keymap.set("n", "<leader>hr", gs.reset_hunk)
vim.keymap.set("n", "<leader>hp", gs.preview_hunk)
vim.keymap.set("n", "<leader>hb", function() gs.blame_line({ full = true }) end)
vim.keymap.set("n", "<leader>hd", gs.diffthis)
```

---

## Shell extras

Defined in `.bashrc`:

| Alias | Expands to |
|-------|-----------|
| `gs` | `git status` |
| `gd` | `git diff` |
| `ga` | `git add` |
| `gc` | `git commit -m` |
| `gk` | `git checkout` |
| `l` / `ll` | `ls -l` / `ls -lart` |
| `vi` | `nvim` |
| `k` | `kubectl` |
| `tf` | `terraform` |
| `dc` | `docker compose` |
| `activate` | `source .venv/bin/activate` |
| `Ctrl+R` | fzf shell history search |
| `Ctrl+T` | fzf file picker |

---

## LSP (optional)

The config ships minimal — themes, navigation, git, UI. Extend `~/.config/nvim/init.lua` to add LSP.

**Suggested lazy.nvim additions:**

```lua
{ "williamboman/mason.nvim" },
{ "williamboman/mason-lspconfig.nvim" },
{ "neovim/nvim-lspconfig" },
{ "saghen/blink.cmp" },   -- fast Rust completion
```

**Common language servers (`:MasonInstall <name>`):**

| Server | Language |
|--------|----------|
| `pyright` | Python |
| `ts_ls` | TypeScript / JS |
| `tailwindcss` | Tailwind |
| `bashls` | Bash |
| `html` / `cssls` / `jsonls` / `yamlls` | Web / config |
| `dockerls` | Dockerfile |

---

## Troubleshooting

**`nvim` not found during Lazy sync** — run `bootstrap` first, then verify:

```bash
ls -la /usr/local/bin/nvim && /usr/local/bin/nvim --version
```

**Fonts look wrong (missing icons / `□` boxes)** — your terminal isn't using a Nerd Font, or it isn't set in all required places. For MobaXterm specifically, both fonts must be installed **for all users** on Windows *and* FiraCode must be set in both the global MobaXterm configuration and the per-session settings.

**Uninstall fails — consumers still registered:**

`uninstall --all` blocks if users still have dotfiles installed. Either uninstall each consumer first:

```bash
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall user alice
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall root
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall --all
```

Or skip the check and remove everything at once:

```bash
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall --all --force
```

**Inspect state:**

```bash
ls /var/lib/dotfiles/users/
cat /var/lib/dotfiles/users/alice/files
```

**WSL clipboard not working as root** (`'powershell.exe' is not executable`) — root's PATH omits Windows interop directories. The config resolves `powershell.exe` and `clip.exe` via their full Windows paths (`/mnt/c/Windows/System32/…`) automatically, so this should not appear. If it still does, verify WSL interop is enabled:

```bash
cat /proc/sys/fs/binfmt_misc/WSLInterop   # should print "enabled"
# or check /etc/wsl.conf:
grep interop /etc/wsl.conf
```

If interop is disabled, add to `/etc/wsl.conf`:

```ini
[interop]
enabled = true
appendWindowsPath = false
```

Then restart the WSL instance (`wsl --shutdown` from PowerShell).

**Git colors not showing** — verify the include is registered:

```bash
git config --global --list | grep include
cat ~/.config/git/theme.conf
```

If missing: `git config --global include.path ~/.config/git/theme.conf`

**Repo out of date after bootstrap:**

```bash
sudo git -C /usr/local/share/dotfiles pull --depth 1
```
