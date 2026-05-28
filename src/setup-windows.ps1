# ============================================================
# setup-windows.ps1 - Windows native dotfiles installer
#
# Usage:
#   .\src\setup-windows.ps1 clone                 # clone repo to %USERPROFILE%\projects\dotfiles
#   .\src\setup-windows.ps1 install               # install dotfiles
#   .\src\setup-windows.ps1 uninstall             # remove dotfiles
#   .\src\setup-windows.ps1 uninstall -All        # remove dotfiles + binaries
#
# Prerequisites: Git.Git must be pre-installed (it provides Git Bash).
#   winget install Git.Git
#
# All other tools (Neovim, Starship, ripgrep, fzf, zig, delta, Python 3.12)
# are installed automatically via winget by the 'install' command when missing.
#
# Dotfiles are read from src/ - the same tree used by Linux/WSL.
# ============================================================

param(
    [Parameter(Position = 0)]
    [ValidateSet('clone', 'install', 'uninstall')]
    [string]$Command = '',
    [switch]$All,
    # install: starship template to use (skips interactive prompt)
    # options: powerline | pills | nerd-font | dracula | seeker | moir | sanmue | sepan
    [string]$StarshipTemplate = ''
)

if (-not $Command) {
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  .\src\setup-windows.ps1 clone                              # clone repo"
    Write-Host "  .\src\setup-windows.ps1 install                            # install (interactive template selection)"
    Write-Host "  .\src\setup-windows.ps1 install -StarshipTemplate pills     # install with specific template"
    Write-Host "  .\src\setup-windows.ps1 uninstall"
    Write-Host "  .\src\setup-windows.ps1 uninstall -All"
    Write-Host ""
    Write-Host "Templates: powerline | pills | nerd-font | dracula | seeker | moir | sanmue | sepan" -ForegroundColor Gray
    exit 0
}

# ── Clone ──────────────────────────────────────────────────────
if ($Command -eq 'clone') {
    $RepoUrl  = 'https://github.com/AVRC26/dotfiles.git'
    $CloneDir = "$env:USERPROFILE\projects\dotfiles"

    if (Test-Path $CloneDir) {
        Write-Warning "Directory already exists: $CloneDir"
        Write-Warning "Remove it first or pull manually: git -C $CloneDir pull"
        exit 1
    }

    New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\projects" | Out-Null
    Write-Host "Cloning $RepoUrl -> $CloneDir ..." -ForegroundColor Cyan
    git clone --depth 1 $RepoUrl $CloneDir
    Write-Host "`nDone. Next:" -ForegroundColor Green
    Write-Host "  & `"$CloneDir\src\setup-windows.ps1`" install"
    exit 0
}

$ErrorActionPreference = "Stop"
$RepoRoot      = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$CommonSrc     = Join-Path $RepoRoot "src"
$UserConfigDir = "$env:USERPROFILE\.config"
$NvimConfigDir = "$env:LOCALAPPDATA\nvim"
$NvimDataDir   = "$env:LOCALAPPDATA\nvim-data"

# Available starship templates
$StarshipTemplates = @{
    '1' = 'powerline'
    '2' = 'pills'
    '3' = 'nerd-font'
    '4' = 'dracula'
    '5' = 'seeker'
    '6' = 'moir'
    '7' = 'sanmue'
    '8' = 'sepan'
}

# ── Uninstall ──────────────────────────────────────────────────
if ($Command -eq 'uninstall') {
    Write-Host "=== Uninstalling dotfiles ===" -ForegroundColor Yellow

    # Neovim config + all plugin/cache data
    foreach ($dir in @($NvimConfigDir, $NvimDataDir)) {
        if (Test-Path $dir) {
            Remove-Item $dir -Recurse -Force
            Write-Host "  Removed: $dir" -ForegroundColor Gray
        }
    }

    # Theme, prompt, shell, git config files
    foreach ($f in @(
        "$UserConfigDir\starship.toml",
        "$UserConfigDir\dotfiles-starship-template",
        "$UserConfigDir\dircolors-template",
        "$UserConfigDir\gitcolors-template",
        "$UserConfigDir\roles.json",
        "$UserConfigDir\palettes.json",
        "$UserConfigDir\render-theme.py",
        "$UserConfigDir\set-theme.ps1",
        "$UserConfigDir\git\theme.conf",
        "$env:USERPROFILE\.dircolors",
        "$env:USERPROFILE\.bashrc",
        "$env:USERPROFILE\.gitconfig",
        "$env:USERPROFILE\.minttyrc"
    )) {
        if (Test-Path $f) {
            Remove-Item $f -Force
            Write-Host "  Removed: $f" -ForegroundColor Gray
        }
    }

    # Remove dirs left behind by the install
    foreach ($dir in @(
        "$UserConfigDir\starship",
        "$UserConfigDir\__pycache__",
        "$UserConfigDir\git",
        "$env:APPDATA\starship"
    )) {
        if (Test-Path $dir) {
            Remove-Item $dir -Recurse -Force
            Write-Host "  Removed: $dir" -ForegroundColor Gray
        }
    }

    # Remove dotfiles lines from PowerShell profile
    $psProfile = $PROFILE
    if (Test-Path $psProfile) {
        $kept = Get-Content $psProfile | Where-Object {
            $_ -notlike '*Invoke-Expression (&starship init powershell)*' -and
            $_ -notlike '*set-theme.ps1*' -and
            $_ -notlike '*_starshipPrompt*'
        }
        if ($kept) {
            Set-Content $psProfile ($kept -join "`n") -Encoding UTF8
        } else {
            Remove-Item $psProfile -Force
        }
        Write-Host "  Cleaned PowerShell profile" -ForegroundColor Gray
    }

    # Remove git theme include
    $ErrorActionPreference = "SilentlyContinue"
    git config --global --unset include.path
    $ErrorActionPreference = "Stop"
    Write-Host "  Cleared git include.path" -ForegroundColor Gray

    if ($All) {
        Write-Host "`nUninstalling binaries ..." -ForegroundColor Yellow
        # Neovim was installed as a zip to user dir — remove it directly
        $nvimBinDir = "$env:USERPROFILE\bin\nvim"
        if (Test-Path $nvimBinDir) {
            Remove-Item $nvimBinDir -Recurse -Force
            Write-Host "  Removed: $nvimBinDir" -ForegroundColor Gray
        }

        foreach ($pkg in @("Starship.Starship", "BurntSushi.ripgrep.MSVC", "junegunn.fzf", "zig.zig", "dandavison.delta")) {
            winget uninstall --id $pkg --scope user --silent --force
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  Uninstalled: $pkg" -ForegroundColor Gray
            } else {
                Write-Warning "  Could not uninstall $pkg (exit $LASTEXITCODE) - remove manually via winget uninstall --id $pkg"
            }
        }
    }

    Write-Host "`n=== Uninstall complete ===" -ForegroundColor Cyan
    exit 0
}

# ── Install — prerequisites (auto-install via winget if missing) ───────────────
Write-Host "=== Checking / installing prerequisites ===" -ForegroundColor Cyan

# ── Neovim — zip install to user dir (no admin required) ──────
$NvimBinDir = "$env:USERPROFILE\bin\nvim"
if (Get-Command nvim -ErrorAction SilentlyContinue) {
    Write-Host "  Neovim: already present" -ForegroundColor Gray
} else {
    Write-Host "  Installing Neovim (latest, no admin) ..." -ForegroundColor Cyan
    $nvimRelease = (Invoke-RestMethod "https://api.github.com/repos/neovim/neovim/releases/latest")
    $nvimAsset   = $nvimRelease.assets | Where-Object { $_.name -eq "nvim-win64.zip" } | Select-Object -First 1
    if (-not $nvimAsset) {
        Write-Warning "  Could not find nvim-win64.zip in latest release - install manually from https://github.com/neovim/neovim/releases/latest"
    } else {
        $nvimZip = "$env:TEMP\nvim-win64.zip"
        Invoke-WebRequest -Uri $nvimAsset.browser_download_url -OutFile $nvimZip
        New-Item -ItemType Directory -Force -Path $NvimBinDir | Out-Null
        Expand-Archive -Path $nvimZip -DestinationPath $NvimBinDir -Force
        # The zip extracts into a versioned subfolder e.g. nvim-win64/; find nvim.exe
        $nvimExe = Get-ChildItem -Path $NvimBinDir -Recurse -Filter "nvim.exe" | Select-Object -First 1
        $nvimExeDir = $nvimExe.DirectoryName
        # Add to user PATH if not already there
        $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
        if ($userPath -notlike "*$nvimExeDir*") {
            [System.Environment]::SetEnvironmentVariable('Path', "$userPath;$nvimExeDir", 'User')
            $env:Path += ";$nvimExeDir"
        }
        Remove-Item $nvimZip -Force
        Write-Host "  Neovim installed -> $nvimExeDir" -ForegroundColor Green
        $_anyInstalled = $true
    }
}

# ── Other tools — winget with user scope, fallback to machine ──
$_tools = @(
    @{ Cmd = "starship"; Id = "Starship.Starship";        Label = "Starship" },
    @{ Cmd = "rg";       Id = "BurntSushi.ripgrep.MSVC"; Label = "ripgrep"  },
    @{ Cmd = "fzf";      Id = "junegunn.fzf";            Label = "fzf"      },
    @{ Cmd = "zig";      Id = "zig.zig";                  Label = "zig"      },
    @{ Cmd = "delta";    Id = "dandavison.delta";         Label = "delta"    }
)

$_anyInstalled = $false
foreach ($t in $_tools) {
    if (Get-Command $t.Cmd -ErrorAction SilentlyContinue) {
        Write-Host "  $($t.Label): already present" -ForegroundColor Gray
    } else {
        Write-Host "  Installing $($t.Label) ($($t.Id)) ..." -ForegroundColor Cyan
        winget install --id $t.Id --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
            $_anyInstalled = $true
        } else {
            Write-Host "  --scope user not supported for $($t.Label), retrying without scope ..." -ForegroundColor Gray
            winget install --id $t.Id --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -eq 0) {
                $_anyInstalled = $true
            } else {
                Write-Warning "  $($t.Label) install failed (exit $LASTEXITCODE) - install manually: winget install $($t.Id)"
            }
        }
    }
}

if ($_anyInstalled) {
    Write-Host '  Refreshing PATH after winget installs ...' -ForegroundColor Gray
    $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath    = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path    = $machinePath + ';' + $userPath
}

# ── Fonts — FiraCode Nerd Font + Nerd Fonts Symbols Only (user install, no admin) ──
$UserFontsDir = "$env:LOCALAPPDATA\Microsoft\Windows\Fonts"
New-Item -ItemType Directory -Force -Path $UserFontsDir | Out-Null

function Install-NerdFontFromGitHub {
    param([string]$RepoAssetName, [string]$Label, [string]$FontPattern)

    if (Get-ChildItem -Path $UserFontsDir -Filter $FontPattern -ErrorAction SilentlyContinue) {
        Write-Host "  $($Label) fonts: already installed" -ForegroundColor Gray
        return
    }

    Write-Host "  Installing $Label fonts ..." -ForegroundColor Cyan
    $release  = Invoke-RestMethod "https://api.github.com/repos/ryanoasis/nerd-fonts/releases/latest"
    $asset    = $release.assets | Where-Object { $_.name -eq $RepoAssetName } | Select-Object -First 1
    if (-not $asset) {
        Write-Warning "  Could not find $RepoAssetName in nerd-fonts latest release"
        return
    }

    $zipPath = "$env:TEMP\$RepoAssetName"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
    $extractDir = "$env:TEMP\$($RepoAssetName -replace '\.zip$', '')"
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $installed = 0
    $shellApp  = New-Object -ComObject Shell.Application
    $fontShell = $shellApp.Namespace(0x14)  # 0x14 = CSIDL_FONTS (user fonts folder)
    Get-ChildItem -Path $extractDir -Filter "*.ttf" -Recurse | ForEach-Object {
        # CopyHere with flag 0x10 (overwrite silently) installs via Shell API —
        # this is the only reliable way to register user fonts without admin.
        $fontShell.CopyHere($_.FullName, 0x10)
        $installed++
    }

    Remove-Item $zipPath -Force
    Remove-Item $extractDir -Recurse -Force
    Write-Host "  $($Label): $installed font files installed -> $UserFontsDir" -ForegroundColor Green
}

Install-NerdFontFromGitHub -RepoAssetName "FiraCode.zip"         -Label "FiraCode Nerd Font"        -FontPattern "FiraCode*"
Install-NerdFontFromGitHub -RepoAssetName "NerdFontsSymbolsOnly.zip" -Label "Nerd Fonts Symbols Only" -FontPattern "SymbolsNerdFont*"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warning "  python not found - theme rendering will be skipped. Install manually: winget install Python.Python.3.12"
}

Write-Host "=== Windows dotfiles setup ===" -ForegroundColor Cyan
Write-Host "Source: $CommonSrc" -ForegroundColor Gray

# ── Starship template selection ────────────────────────────────
$ValidTemplates = @('powerline', 'pills', 'nerd-font', 'dracula', 'seeker', 'moir', 'sanmue', 'sepan')
if ($StarshipTemplate -and ($StarshipTemplate -in $ValidTemplates)) {
    $SelectedTemplate = $StarshipTemplate
} else {
    $SelectedTemplate = 'pills'
}
Write-Host "`nStarship template: $SelectedTemplate" -ForegroundColor Green

# ── Neovim config ─────────────────────────────────────────────
Write-Host "`nSetting up Neovim config at $NvimConfigDir ..."
New-Item -ItemType Directory -Force -Path $NvimConfigDir | Out-Null
Copy-Item "$CommonSrc\.config\nvim\init.lua" "$NvimConfigDir\init.lua" -Force
Write-Host "  init.lua" -ForegroundColor Green

# ── Theme templates + renderer ────────────────────────────────
Write-Host "Copying theme templates to $UserConfigDir ..."
New-Item -ItemType Directory -Force -Path $UserConfigDir | Out-Null

# Copy starship templates directory
$StarshipDir = "$UserConfigDir\starship"
New-Item -ItemType Directory -Force -Path $StarshipDir | Out-Null
foreach ($tmpl in @('powerline', 'pills', 'nerd-font', 'dracula', 'seeker', 'moir', 'sanmue', 'sepan')) {
    Copy-Item "$CommonSrc\.config\starship\$tmpl.toml" "$StarshipDir\$tmpl.toml" -Force
}
Write-Host "  Starship templates -> $StarshipDir" -ForegroundColor Green

# Write active template name
Set-Content "$UserConfigDir\dotfiles-starship-template" $SelectedTemplate -Encoding UTF8 -NoNewline
Add-Content "$UserConfigDir\dotfiles-starship-template" ""   # add trailing newline
Write-Host "  Active template: $SelectedTemplate" -ForegroundColor Green

# Copy remaining config files
foreach ($tf in @(
    "dircolors-template",
    "gitcolors-template",
    "roles.json",
    "palettes.json",
    "render-theme.py"
)) {
    Copy-Item "$CommonSrc\.config\$tf" "$UserConfigDir\$tf" -Force
}
Write-Host "  Theme templates + render-theme.py copied" -ForegroundColor Green

# ── Write Set-Theme PowerShell helper ─────────────────────────
$setThemeScript = @'
# dotfiles Set-Theme helper - generated by setup-windows.ps1, do not edit.
function Set-Theme {
    param(
        [Parameter(Position=0)][string]$Theme            = '',
        [Parameter(Position=1)][string]$Flavor           = '',
        [Parameter(Position=2)][string]$StarshipTemplate = ''
    )
    $cfg      = "$env:USERPROFILE\.config"
    $renderer = "$cfg\render-theme.py"
    $pal      = "$cfg\palettes.json"
    $tmplFile = "$cfg\dotfiles-starship-template"

    if (-not (Test-Path $renderer)) {
        Write-Error "Set-Theme: render-theme.py not found - re-run setup-windows.ps1"
        return
    }

    if (-not $Theme -or $Theme -eq '-h' -or $Theme -eq '--help') {
        if (Test-Path $pal) { python $renderer help --palette $pal }
        else { Write-Host 'Usage: Set-Theme -Theme NAME [-Flavor NAME] [-StarshipTemplate NAME]' }
        return
    }

    # Resolve active template
    if (-not $StarshipTemplate) {
        if (Test-Path $tmplFile) { $StarshipTemplate = (Get-Content $tmplFile -Raw).Trim() }
        if (-not $StarshipTemplate) { $StarshipTemplate = 'pills' }
    }
    $tmplPath = "$cfg\starship\$StarshipTemplate.toml"
    if (-not (Test-Path $tmplPath)) {
        Write-Warning "Template '$StarshipTemplate' not found - falling back to pills."
        $StarshipTemplate = 'pills'
        $tmplPath = "$cfg\starship\pills.toml"
    }

    $sep    = [char]0xE0B0
    $pyArgs = @(
        $renderer, 'set-theme',
        '--palette',            $pal,
        '--theme',              $Theme,
        '--sep',                "$sep",
        '--starship-template',  $tmplPath,
        '--starship-output',    "$cfg\starship.toml",
        '--dircolors-template', "$cfg\dircolors-template",
        '--dircolors-output',   "$env:USERPROFILE\.dircolors",
        '--git-template',       "$cfg\gitcolors-template",
        '--git-output',         "$cfg\git\theme.conf",
        '--nvim',               "$env:LOCALAPPDATA\nvim\theme.lua"
    )
    if ($Flavor) { $pyArgs += '--flavor'; $pyArgs += $Flavor }

    python @pyArgs
    if ($LASTEXITCODE -eq 0) {
        # Save active template for future Set-Theme calls
        Set-Content $tmplFile $StarshipTemplate -Encoding UTF8 -NoNewline
        Add-Content $tmplFile ""
        $gc = "$env:USERPROFILE\.gitconfig"
        if (-not (Select-String -Path $gc -Pattern 'theme\.conf' -Quiet -ErrorAction SilentlyContinue)) {
            git config --global include.path "$cfg\git\theme.conf" 2>$null | Out-Null
        }
        $themeLabel = if ($Flavor) { "$Theme/$Flavor" } else { $Theme }
        Write-Host "Theme: $themeLabel  template: $StarshipTemplate. Restart nvim to reload." -ForegroundColor Green
    }
}

function Get-Theme {
    $themeLua = "$env:LOCALAPPDATA\nvim\theme.lua"
    $tmplFile = "$env:USERPROFILE\.config\dotfiles-starship-template"

    if (-not (Test-Path $themeLua)) {
        Write-Error "Get-Theme: theme.lua not found - run Set-Theme first"
        return
    }

    $content  = Get-Content $themeLua
    $theme    = ($content | Where-Object { $_ -match 'active_theme' }) -replace '.*"(.+)".*', '$1'
    $flavor   = ($content | Where-Object { $_ -notmatch 'active_theme' -and $_ -match 'vim\.g\.' }) -replace '.*"(.+)".*', '$1'
    $template = if (Test-Path $tmplFile) { (Get-Content $tmplFile -Raw).Trim() } else { 'unknown' }
    if (-not $flavor) { $flavor = '-' }

    Write-Host "Theme:    $theme"    -ForegroundColor Cyan
    Write-Host "Flavor:   $flavor"   -ForegroundColor Cyan
    Write-Host "Template: $template" -ForegroundColor Cyan
}
'@
Set-Content "$UserConfigDir\set-theme.ps1" $setThemeScript -Encoding UTF8
Write-Host "  set-theme.ps1 written" -ForegroundColor Green

# ── Apply default theme (catppuccin/macchiato) ────────────────
if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Applying default theme (catppuccin/macchiato) ..."
    $gitConfigDir = "$UserConfigDir\git"
    New-Item -ItemType Directory -Force -Path $gitConfigDir | Out-Null
    $sep      = [char]0xE0B0
    $tmplPath = "$UserConfigDir\starship\$SelectedTemplate.toml"
    python "$UserConfigDir\render-theme.py" set-theme `
        --palette            "$UserConfigDir\palettes.json" `
        --theme              catppuccin `
        --flavor             macchiato `
        --sep                "$sep" `
        --starship-template  "$tmplPath" `
        --starship-output    "$UserConfigDir\starship.toml" `
        --dircolors-template "$UserConfigDir\dircolors-template" `
        --dircolors-output   "$env:USERPROFILE\.dircolors" `
        --git-template       "$UserConfigDir\gitcolors-template" `
        --git-output         "$gitConfigDir\theme.conf" `
        --nvim               "$NvimConfigDir\theme.lua"
    if ($LASTEXITCODE -eq 0) {
        git config --global include.path "$gitConfigDir\theme.conf"
        Write-Host "  Default theme applied (catppuccin/macchiato, template: $SelectedTemplate)" -ForegroundColor Green
    } else {
        Write-Warning "render-theme.py exited with code $LASTEXITCODE - theme may not be fully applied."
    }
} else {
    Write-Warning "python not found - skipping theme render."
    Write-Warning "Install it with: winget install Python.Python.3.12  then run: Set-Theme catppuccin macchiato"
}

# ── Shell configs ─────────────────────────────────────────────
Write-Host "Copying .bashrc and .gitconfig ..."
Copy-Item "$CommonSrc\.bashrc"    "$env:USERPROFILE\.bashrc"    -Force
Copy-Item "$CommonSrc\.gitconfig" "$env:USERPROFILE\.gitconfig" -Force
Write-Host "  .bashrc, .gitconfig" -ForegroundColor Green

# ── minttyrc (mintty terminal config) ─────────────────────────
if (Test-Path "$CommonSrc\.minttyrc") {
    Copy-Item "$CommonSrc\.minttyrc" "$env:USERPROFILE\.minttyrc" -Force
    Write-Host "  .minttyrc" -ForegroundColor Green
}

# ── Neovim plugins ────────────────────────────────────────────
Write-Host "Installing Neovim plugins via lazy.nvim ..."
& nvim --headless "+Lazy! sync" +qa
Write-Host "  Plugins installed" -ForegroundColor Green

Write-Host "Compiling tree-sitter parsers (this may take a few minutes) ..."
& nvim --headless +qa
Write-Host "  Tree-sitter parsers compiled" -ForegroundColor Green

# ── PowerShell profile (starship + Set-Theme) ─────────────────
$psProfile = $PROFILE
Write-Host "Configuring PowerShell profile at $psProfile ..."
if (-not (Test-Path $psProfile)) {
    New-Item -ItemType File -Force -Path $psProfile | Out-Null
}
$starshipLine   = 'Invoke-Expression (&starship init powershell)'
$setThemeLine   = '. "$env:USERPROFILE\.config\set-theme.ps1"'
$profileContent = Get-Content $psProfile -ErrorAction SilentlyContinue

if (-not ($profileContent | Select-String -SimpleMatch $starshipLine)) {
    Add-Content $psProfile "`n$starshipLine"
    Write-Host "  Starship init added to PowerShell profile" -ForegroundColor Green
} else {
    Write-Host "  Starship already in PowerShell profile" -ForegroundColor Yellow
}
if (-not ($profileContent | Select-String -SimpleMatch 'set-theme.ps1')) {
    Add-Content $psProfile "`n$setThemeLine"
    Write-Host "  Set-Theme added to PowerShell profile" -ForegroundColor Green
} else {
    Write-Host "  Set-Theme already in PowerShell profile" -ForegroundColor Yellow
}

# BCE fix — must come after Starship init so $function:prompt is already Starship's.
# Windows Terminal: emit \e[?117h (DECECM off) before each render — disables BCE so new
# scroll lines use the default background, not the prompt's last segment color.
# Append \e[?117l at the END of the prompt string to re-enable BCE immediately after the
# prompt is drawn — this allows apps (nvim, less, etc.) that rely on BCE for background
# fills to work correctly when launched from the prompt.
# VS Code (xterm.js): mode 117 unsupported; instead inject \e[49m\e[2K after each \n in
# the prompt string — resets bg then erases the freshly-scrolled line before line 2 draws.
# See: https://github.com/microsoft/terminal/discussions/19747
$bceFix = @'

$script:_starshipPrompt = $function:prompt
if ($env:WT_SESSION) {
    function prompt {
        $esc = [char]27
        [Console]::Write("${esc}[?117h")
        return (& $script:_starshipPrompt) + "${esc}[?117l"
    }
} elseif ($env:TERM_PROGRAM -eq 'vscode') {
    function prompt {
        $esc = [char]27
        return (& $script:_starshipPrompt) -replace "`r?`n", "${esc}[K`n${esc}[49m${esc}[2K"
    }
}
'@
if (-not ($profileContent | Select-String -SimpleMatch '_starshipPrompt')) {
    Add-Content $psProfile $bceFix
    Write-Host "  BCE fix (WT background streak) added to PowerShell profile" -ForegroundColor Green
} else {
    Write-Host "  BCE fix already in PowerShell profile" -ForegroundColor Yellow
}

Write-Host "`n=== Setup complete! ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Restart your terminal"
Write-Host "  2. Open nvim - plugins install on first launch (zig compiles tree-sitter parsers)"
Write-Host '  3. Switch themes:    Set-Theme catppuccin macchiato'
Write-Host '  4. Change template:  Set-Theme catppuccin macchiato powerline'
Write-Host '  5. List themes:      Set-Theme --help'
