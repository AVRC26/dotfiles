# dotfiles

Personal shell, Neovim, and prompt configuration for **Linux**, **WSL**, and **Windows**. One `src/` tree, role-based defaults, full install/uninstall lifecycle tracking.

Full reference: [src/README.md](src/README.md)

---

## Quick install

### Linux / WSL — just install for me (recommended)

One flag installs everything for the user who runs the command.

**With sudo** — binaries go to `/usr/local/bin` (shared), dotfiles go to your home:

```bash
curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
    | sudo bash -s -- --install-self
```

**Without sudo** — everything under `~/`; existing system tools (rg, fzf, nvim, starship, delta) are reused from PATH instead of re-downloaded:

```bash
curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
    | bash -s -- --install-self
```

> `--install-self` detects whether you have root. With root it runs a full system bootstrap then applies dotfiles to `$SUDO_USER`. Without root it auto-switches to `--user-local` mode.

> **Python 3** is required for theme switching (`set-theme`). If not already installed: `sudo apt install python3.12`

---

### Linux / WSL — system install (shared machine, manual)

```bash
sudo apt install git curl

# Step 1 — bootstrap once per machine (installs shared tools + clones repo)
curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
    | sudo bash -s --
# Step 2 — apply dotfiles (use the canonical path from here on)
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh install root
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh install user alice
```

> **Python 3** is required for theme switching (`set-theme`). If not already installed: `sudo apt install python3.12`

**Uninstall:**

```bash
# Remove per-user dotfiles first, then shared tools
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall user alice
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall root
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall --all

# Or remove everything at once (skips the consumer check)
sudo /usr/local/share/dotfiles/src/init-dotfiles.sh uninstall --all --force
```

### Linux / WSL — no sudo (current user only)

```bash
curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
    | bash -s -- --user-local
```

Installs binaries to `~/.local/bin`. If rg, fzf, nvim, starship, or delta are already on your PATH (e.g. installed system-wide), those are reused and the download is skipped.

> **Python 3** is required for theme switching (`set-theme`). If not already installed: `sudo apt install python3.12`

**Uninstall:**

```bash
~/.local/share/dotfiles/src/init-dotfiles.sh uninstall --user-local```

---

## Themes — Linux / WSL

Switch Neovim colorscheme, Starship prompt, `ls` colors, and git colors in one command:

```bash
set-theme --theme monokai                         # Monokai Pro Spectrum (user default)
set-theme --theme catppuccin --flavor latte       # Catppuccin Latte (light)
set-theme --theme kanagawa --flavor dragon
set-theme --theme gruvbox --flavor light          # Gruvbox Light (root default)
set-theme --theme tokyonight --flavor storm

set-theme --help                                  # list all themes and flavors
get-theme                                         # show active theme, flavor, and template
```

Switch the prompt layout without changing the theme:

```bash
set-theme --theme monokai --starship-template moir        # user default template
set-theme --theme gruvbox --starship-template sanmue      # root default template
# templates: powerline | pills | nerd-font | dracula | seeker | moir | sanmue | sepan
```

Full reference → [src/THEMES.md](src/THEMES.md)

---

## Terminal font

A **Nerd Font** is required for file/folder icons in nvim-tree, bufferline, and lualine. The installer deploys **FiraCode Nerd Font** + **Symbols Nerd Font Mono** automatically on Linux/WSL. Set your terminal font to `FiraCode NFM`.

For **WSL with Windows Terminal**: Settings → your WSL profile → Appearance → Font face → `FiraCode NFM`.

For **MobaXterm**, **macOS**, and detailed font setup see [src/README.md — Terminal font](src/README.md#terminal-font-nerd-font).

---

## What's included

| Tool | Purpose |
|------|---------|
| **Neovim 0.10+** | Editor — lazy.nvim, Telescope, nvim-tree, lualine, bufferline, gitsigns |
| **Starship** | Cross-shell prompt — git, Python, Node, K8s context |
| **ripgrep** | Fast grep, powers Telescope live_grep |
| **fzf** | Fuzzy finder — `Ctrl+R` history, `Ctrl+T` file picker |

---

## Windows setup

### Prerequisites

**Git** must be installed first — it provides Git Bash and `git clone`:

```powershell
winget install Git.Git
```

All other tools (Neovim, Starship, ripgrep, fzf, zig, delta) are installed automatically by the setup script when missing.

> **Python** is required for theme switching (`Set-Theme`) but is not auto-installed — install it manually if needed: `winget install Python.Python.3.12`

### Clone and install

```powershell
# Clone to C:\Users\<you>\projects\dotfiles
git clone --depth 1 https://github.com/AVRC26/dotfiles.git "$env:USERPROFILE\projects\dotfiles"
& "$env:USERPROFILE\projects\dotfiles\src\setup-windows.ps1" install
```

Auto-installs any missing tools (Neovim, Starship, ripgrep, fzf, zig, delta) via winget, applies the **Catppuccin Macchiato** theme with a **pills**-style Starship prompt for PowerShell, and configures Git Bash (`.bashrc`, `.gitconfig`, dircolors, git diff colors). `Set-Theme` and `Get-Theme` commands are added to your PowerShell profile.

```powershell
# Switch theme
Set-Theme -Theme catppuccin -Flavor macchiato     # default
Set-Theme -Theme catppuccin -Flavor latte
Set-Theme -Theme gruvbox

# Show active theme, flavor, and template
Get-Theme

# Switch prompt template
Set-Theme -Theme catppuccin -StarshipTemplate powerline
# templates: powerline | pills | nerd-font | dracula | seeker | moir | sanmue | sepan

# Install with a specific template (skips the interactive prompt)
& "$env:USERPROFILE\projects\dotfiles\src\setup-windows.ps1" install -StarshipTemplate pills

# List all available themes and flavors
Set-Theme --help
```

### Uninstall

```powershell
& "$env:USERPROFILE\projects\dotfiles\src\setup-windows.ps1" uninstall        # remove dotfiles only
& "$env:USERPROFILE\projects\dotfiles\src\setup-windows.ps1" uninstall -All   # also uninstall nvim, starship, rg, fzf, zig, delta
```

> **Note:** The Starship prompt uses Nerd Font glyphs. Install [FiraCode Nerd Font](https://github.com/ryanoasis/nerd-fonts/releases/latest) on the Windows host (download `FiraCode.zip` + `NerdFontsSymbolsOnly.zip`, select all `.ttf` → right-click → Install for all users), then set your terminal font to `FiraCode NFM`.

---

## Windows utilities

### Disk usage — folder breakdown

Total size of a folder recursively (follows junctions/symlinks, includes hidden files):

```powershell
(Get-ChildItem -Recurse -File -Force C:\Users\avrc26\ | Measure-Object -Property Length -Sum).Sum / 1GB
```

Top-level folder breakdown ranked by size:

```powershell
Get-ChildItem -Force C:\Users\avrc26\ | Where-Object { $_.PSIsContainer } | ForEach-Object {
    $size = (Get-ChildItem -Recurse -File -Force $_.FullName -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    [PSCustomObject]@{ Folder = $_.Name; SizeGB = [math]::Round($size / 1GB, 2) }
} | Sort-Object SizeGB -Descending | Format-Table -AutoSize
```

> **Note:** Windows Explorer Properties may show a higher number than `Get-ChildItem` without `-Force` because it follows junction points. Always use `-Force` for accurate totals.

---

## Credits

**Themes** — [Ayu](https://github.com/Shatur/neovim-ayu) · [Bamboo](https://github.com/ribru17/bamboo.nvim) · [Bearded](https://github.com/Ferouk/bearded-nvim) · [Catppuccin](https://github.com/catppuccin/nvim) · [Flexoki](https://github.com/kepano/flexoki-neovim) · [Gruvbox](https://github.com/ellisonleao/gruvbox.nvim) · [Kanagawa](https://github.com/rebelot/kanagawa.nvim) · [Monokai Pro](https://github.com/loctvl842/monokai-pro.nvim) · [Oasis](https://github.com/uhs-robert/oasis.nvim) · [OneDarkPro](https://github.com/olimorris/onedarkpro.nvim) · [Tokyo Night](https://github.com/folke/tokyonight.nvim)

**Starship prompts** — [dracula](https://github.com/starship/starship/discussions/1107#discussioncomment-11130385) · [moir](https://github.com/starship/starship/discussions/1107#discussioncomment-11890875) · [nerd-font](https://starship.rs/presets/nerd-font) · [pills](https://github.com/TaouMou/starship-presets) · [powerline](https://starship.rs/presets/plain-text-symbols) · [sanmue](https://gist.github.com/sanmue/e04657a7ca37841c8e97e7fdf0dd6a5c) · [seeker](https://github.com/starship/starship/discussions/1107#discussioncomment-13575853) · [sepan](https://gitlab.com/sjsepan/sjsepan.powerline)

**Neovim** — [bufferline.nvim](https://github.com/akinsho/bufferline.nvim) · [gitsigns.nvim](https://github.com/lewis6991/gitsigns.nvim) · [indent-blankline.nvim](https://github.com/lukas-reineke/indent-blankline.nvim) · [lazy.nvim](https://github.com/folke/lazy.nvim) · [lualine.nvim](https://github.com/nvim-lualine/lualine.nvim) · [nvim-tree](https://github.com/nvim-tree/nvim-tree.lua) · [nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter) · [Telescope](https://github.com/nvim-telescope/telescope.nvim)

**CLI** — [delta](https://github.com/dandavison/delta) · [fzf](https://github.com/junegunn/fzf) · [Neovim](https://github.com/neovim/neovim) · [ripgrep](https://github.com/BurntSushi/ripgrep) · [Starship](https://github.com/starship/starship)

---

[Apache License 2.0](LICENSE)
