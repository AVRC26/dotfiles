#!/bin/bash
set -e

# ════════════════════════════════════════════════════════════════
#  init-dotfiles.sh  —  dotfiles installer / uninstaller
#
#  SYSTEM (sudo required):
#    sudo ./init-dotfiles.sh bootstrap
#    sudo ./init-dotfiles.sh install root
#    sudo ./init-dotfiles.sh install user alice
#    sudo ./init-dotfiles.sh uninstall user alice
#    sudo ./init-dotfiles.sh uninstall root
#    sudo ./init-dotfiles.sh uninstall --all
#
#  USER-LOCAL (no sudo — everything under $HOME):
#    ./init-dotfiles.sh install --user-local
#    ./init-dotfiles.sh uninstall --user-local
#
#  State files:
#    System:     /var/lib/dotfiles/
#    User-local: ~/.local/state/dotfiles/   (respects $XDG_STATE_HOME)
# ════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════════
if [ -t 1 ]; then
    _CI='\033[0;36m' _CO='\033[0;32m' _CW='\033[0;33m' _CE='\033[0;31m' _CB='\033[1m' _CR='\033[0m'
else
    _CI='' _CO='' _CW='' _CE='' _CB='' _CR=''
fi
log_info()    { echo -e "${_CI}[info]${_CR}  $*"; }
log_ok()      { echo -e "${_CO}[ ok ]${_CR}  $*"; }
log_warn()    { echo -e "${_CW}[warn]${_CR}  $*"; }
log_error()   { echo -e "${_CE}[fail]${_CR}  $*"; }
log_section() { echo -e "\n${_CB}${_CI}══ $* ══${_CR}"; }


# ════════════════════════════════════════════════════════════════
# USAGE
# ════════════════════════════════════════════════════════════════
usage() {
    cat <<EOF

Usage (system — requires sudo):
  $0 bootstrap
  $0 install root [--theme <name>] [--flavor <flavor>] [--starship-template <name>]
  $0 install user <username> [--theme <name>] [--flavor <flavor>] [--starship-template <name>]
  $0 uninstall root
  $0 uninstall user <username>
  $0 uninstall --all

Usage (no sudo — current user only):
  $0 install --user-local [--theme <name>] [--flavor <flavor>] [--starship-template <name>]
  $0 uninstall --user-local

  In --user-local mode, binary installers check PATH first.  If rg / fzf / nvim /
  starship / delta are already accessible (e.g. installed system-wide), the download
  to ~/.local/bin is skipped and the existing binary is used instead.

Flags:
  --interactive      Prompt for git user.name / user.email and starship template during install
  --force            With uninstall --all: skip the consumer-still-installed safety check

Theme flags (first install only; ignored on re-install):
  --theme <name>            Override default theme  (root default: gruvbox,  user default: monokai)
  --flavor <name>           Override default flavor (root default: light,   user default: spectrum)
  --starship-template <name> Override default starship template (root default: sanmue, user default: moir)
                             Options: powerline  pills  nerd-font  dracula  seeker  moir  sanmue  sepan

State is recorded in:
  system:     /var/lib/dotfiles/
  user-local: \$HOME/.local/state/dotfiles/

EOF
    exit 1
}


# ════════════════════════════════════════════════════════════════
# ARCHITECTURE DETECTION
# ════════════════════════════════════════════════════════════════
case "$(uname -m)" in
    x86_64)        ARCH_FZF="amd64"  ARCH_RG="x86_64-unknown-linux-musl"     ARCH_NVIM="x86_64" ARCH_ZIG="x86_64" ;;
    aarch64|arm64) ARCH_FZF="arm64"  ARCH_RG="aarch64-unknown-linux-gnu"     ARCH_NVIM="arm64"  ARCH_ZIG="aarch64" ;;
    armv7l)        ARCH_FZF="armv7"  ARCH_RG="arm-unknown-linux-gnueabihf"   ARCH_NVIM=""       ARCH_ZIG="" ;;
    *)             ARCH_FZF=""       ARCH_RG=""                               ARCH_NVIM=""       ARCH_ZIG="" ;;
esac


# ════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════
GIT_URL="https://github.com/AVRC26/dotfiles.git"
CANON_REPO="/usr/local/share/dotfiles"
MONOKAI_FILTER_DEFAULT="spectrum"


# ════════════════════════════════════════════════════════════════
# ARGUMENT PARSING
#
# All --flags are extracted first; remaining positional args are:
#   POSITIONAL[0] = COMMAND   (bootstrap | install | uninstall)
#   POSITIONAL[1] = SUBCMD    (root | user | empty for --user-local/--all)
#   POSITIONAL[2] = USERNAME_ARG  (only when SUBCMD=user)
# ════════════════════════════════════════════════════════════════
USER_LOCAL=false
UNINSTALL_ALL=false
FORCE=false
NON_INTERACTIVE=true
THEME_ARG=""
FLAVOR_ARG=""
STARSHIP_TMPL_ARG=""
POSITIONAL=()

_prev_arg=""
for _arg in "$@"; do
    case "$_prev_arg" in
        --theme)              THEME_ARG="$_arg";        _prev_arg=""; continue ;;
        --flavor)             FLAVOR_ARG="$_arg";       _prev_arg=""; continue ;;
        --starship-template)  STARSHIP_TMPL_ARG="$_arg"; _prev_arg=""; continue ;;
    esac
    case "$_arg" in
        --user-local)         USER_LOCAL=true      ;;
        --all)                UNINSTALL_ALL=true   ;;
        --force)              FORCE=true           ;;
        --interactive)        NON_INTERACTIVE=false ;;
        --theme|--flavor|--starship-template) _prev_arg="$_arg" ;;
        -h|--help)            usage ;;
        *)                    POSITIONAL+=("$_arg") ;;
    esac
done

COMMAND="${POSITIONAL[0]:-}"
SUBCMD="${POSITIONAL[1]:-}"
USERNAME_ARG="${POSITIONAL[2]:-}"

[ -z "$COMMAND" ] && { log_error "No command specified."; usage; }

case "$COMMAND" in
    bootstrap|install|uninstall) ;;
    *) log_error "Unknown command: '$COMMAND'"; usage ;;
esac


# ════════════════════════════════════════════════════════════════
# DERIVE PATHS FROM MODE
# ════════════════════════════════════════════════════════════════
if [ "$USER_LOCAL" = true ]; then
    REPO_BASE="${HOME}/.local/share/dotfiles"
    PREFIX_BIN="${HOME}/.local/bin"
    NVIM_OPT_PARENT="${HOME}/.local/opt"
    STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/dotfiles"
else
    REPO_BASE="$CANON_REPO"
    PREFIX_BIN="/usr/local/bin"
    NVIM_OPT_PARENT="/opt"
    STATE_DIR="/var/lib/dotfiles"
fi


# ════════════════════════════════════════════════════════════════
# STATE MANAGEMENT
#
# Layout:
#   $STATE_DIR/
#     platform          — "linux" | "win"
#     mode              — "system" | "user-local"
#     binary_dir        — absolute path to bin dir
#     opt_dir           — absolute path to opt dir
#     repo_base         — absolute path to cloned repo
#     bootstrapped_at   — ISO-8601 timestamp
#     binaries/
#       rg              — installed version string
#       fzf             — installed version string
#       nvim            — installed version string
#       nvim_pkg        — nvim directory name inside opt_dir
#       starship        — installed version string
#     users/
#       <username>/
#         installed_at  — ISO-8601 timestamp
#         home          — absolute home dir path
#         files         — one installed path per line (for clean uninstall)
# ════════════════════════════════════════════════════════════════

state_init() {
    mkdir -p "$STATE_DIR/binaries" "$STATE_DIR/users"
}

state_write() {
    local key="$1" val="$2"
    mkdir -p "$(dirname "$STATE_DIR/$key")"
    printf '%s\n' "$val" > "$STATE_DIR/$key"
}

state_read() {
    local key="$1"
    [ -f "$STATE_DIR/$key" ] && cat "$STATE_DIR/$key" || echo ""
}

state_track_file() {
    local consumer="$1" filepath="$2"
    mkdir -p "$STATE_DIR/users/$consumer"
    echo "$filepath" >> "$STATE_DIR/users/$consumer/files"
}

state_add_consumer() {
    local consumer="$1" home_dir="$2"
    mkdir -p "$STATE_DIR/users/$consumer"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE_DIR/users/$consumer/installed_at"
    echo "$home_dir"             > "$STATE_DIR/users/$consumer/home"
    : >                            "$STATE_DIR/users/$consumer/files"
}

state_reset_files() {
    local consumer="$1"
    : > "$STATE_DIR/users/$consumer/files"
}

state_remove_consumer() {
    local consumer="$1"
    rm -rf "${STATE_DIR:?}/users/$consumer"
}

state_consumer_exists() {
    [ -d "$STATE_DIR/users/$1" ]
}

state_list_consumers() {
    [ -d "$STATE_DIR/users" ] && ls "$STATE_DIR/users/" 2>/dev/null || true
}

state_consumer_count() {
    state_list_consumers | wc -l
}


# ════════════════════════════════════════════════════════════════
# PRIVILEGE CHECK
# ════════════════════════════════════════════════════════════════
require_root() {
    if [ "${EUID:-$(id -u)}" -ne 0 ]; then
        log_error "This command requires root (sudo)."
        log_error "For a no-sudo install use: $0 install --user-local"
        exit 1
    fi
}


# ════════════════════════════════════════════════════════════════
# BINARY INSTALLERS
# ════════════════════════════════════════════════════════════════
_need_curl() {
    if ! command -v curl &>/dev/null; then
        log_warn "curl not found — skipping $1 install."
        return 1
    fi
    return 0
}

# Zig — downloaded to a temp dir solely for treesitter parser compilation,
# then removed immediately.  No permanent install; no state tracking needed.
_install_zig_temp() {
    ZIG_TEMP_DIR="" ZIG_TEMP_BIN=""
    _need_curl zig || return 1
    [ -z "${ARCH_ZIG:-}" ] && { log_warn "No zig build for $(uname -m) — treesitter parsers may not compile."; return 1; }

    # Pull the tarball URL directly from the index rather than constructing it.
    # Stable releases live under ziglang.org/download/; master builds are under /builds/.
    # Tarball name format: zig-<arch>-linux-<ver>.tar.xz  (arch before "linux").
    local json url ver pkg
    json=$(curl -sSfL "https://ziglang.org/download/index.json" 2>/dev/null)
    [ -z "$json" ] && { log_warn "Could not fetch zig index — treesitter parsers may not compile."; return 1; }

    url=$(printf '%s' "$json" \
        | grep -oE "https://ziglang\\.org/download/[^\"]+zig-${ARCH_ZIG}-linux-[^\"]+\\.tar\\.xz" \
        | head -1)
    [ -z "$url" ] && { log_warn "Could not find zig download URL — treesitter parsers may not compile."; return 1; }

    # Derive version and directory name from the URL
    ver=$(printf '%s' "$url" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    pkg="zig-${ARCH_ZIG}-linux-${ver}"
    local tmp_dir
    tmp_dir=$(mktemp -d)

    log_info "Fetching zig $ver for treesitter compilation (temporary)..."
    if curl -sSfL "$url" | tar -xJ -C "$tmp_dir" 2>/dev/null; then
        # Move the full package (zig needs its lib/ dir alongside the binary).
        # Install to /usr/local/lib/zig-VERSION and symlink the binary into
        # PREFIX_BIN so all users find it on PATH without extra PATH juggling.
        local zig_lib_dir
        zig_lib_dir="$(dirname "$PREFIX_BIN")/lib/zig-${ver}"
        mv "$tmp_dir/$pkg" "$zig_lib_dir"
        rm -rf "$tmp_dir"
        ln -sf "$zig_lib_dir/zig" "${PREFIX_BIN}/zig"
        ZIG_TEMP_DIR="$zig_lib_dir"
        log_ok "zig $ver ready (temporary)"
    else
        log_warn "zig download failed — treesitter parsers may not compile."
        rm -rf "$tmp_dir"
        return 1
    fi
}

_cleanup_zig_temp() {
    [ -n "${ZIG_TEMP_DIR:-}" ] && [ -d "$ZIG_TEMP_DIR" ] || return 0
    rm -rf "$ZIG_TEMP_DIR"
    rm -f "${PREFIX_BIN}/zig"
    ZIG_TEMP_DIR=""
    log_ok "zig (temporary) removed"
}

install_ripgrep() {
    local dest_bin="$1"
    _need_curl ripgrep || return 0
    [ -z "$ARCH_RG" ] && { log_warn "Unknown arch — skipping ripgrep."; return 0; }
    mkdir -p "$dest_bin"

    local current="0.0.0"
    if [ -x "${dest_bin}/rg" ]; then
        current=$("${dest_bin}/rg" --version 2>/dev/null | head -1 | grep -oP 'ripgrep \K[\d.]+' || echo "0.0.0")
    elif [ "$USER_LOCAL" = true ]; then
        local _sys_rg
        _sys_rg=$(command -v rg 2>/dev/null || true)
        if [ -n "$_sys_rg" ]; then
            local _sv
            _sv=$("$_sys_rg" --version 2>/dev/null | head -1 | grep -oP 'ripgrep \K[\d.]+' || echo "0.0.0")
            if [ "$(echo "$_sv" | cut -d. -f1)" -ge 14 ] 2>/dev/null; then
                log_ok "ripgrep $_sv found in PATH ($_sys_rg) — skipping download"
                state_write "binaries/rg" "$_sv"
                return 0
            fi
        fi
    fi

    if [ "$(echo "$current" | cut -d. -f1)" -lt 14 ] 2>/dev/null; then
        local ver
        ver=$(curl -sSfL https://api.github.com/repos/BurntSushi/ripgrep/releases/latest \
            | grep -oP '"tag_name": "\K[^"]+')
        curl -sSfL "https://github.com/BurntSushi/ripgrep/releases/download/${ver}/ripgrep-${ver}-${ARCH_RG}.tar.gz" \
            | tar -xz -C /tmp
        mv "/tmp/ripgrep-${ver}-${ARCH_RG}/rg" "$dest_bin/rg"
        chmod a+rx "$dest_bin/rg"
        rm -rf "/tmp/ripgrep-${ver}-${ARCH_RG}"
        state_write "binaries/rg" "$ver"
        log_ok "ripgrep $ver → $dest_bin/rg"
    else
        log_ok "ripgrep up-to-date ($current)"
    fi
}

install_fzf() {
    local dest_bin="$1"
    _need_curl fzf || return 0
    [ -z "$ARCH_FZF" ] && { log_warn "Unknown arch — skipping fzf."; return 0; }
    mkdir -p "$dest_bin"

    local current="0.0"
    if [ -x "${dest_bin}/fzf" ]; then
        current=$("${dest_bin}/fzf" --version 2>/dev/null | grep -oP '^\d+\.\d+' || echo "0.0")
    elif [ "$USER_LOCAL" = true ]; then
        local _sys_fzf
        _sys_fzf=$(command -v fzf 2>/dev/null || true)
        if [ -n "$_sys_fzf" ]; then
            local _sv
            _sv=$("$_sys_fzf" --version 2>/dev/null | grep -oP '^\d+\.\d+' || echo "0.0")
            if [ "$(echo "$_sv" | cut -d. -f2)" -ge 48 ] 2>/dev/null; then
                log_ok "fzf $_sv found in PATH ($_sys_fzf) — skipping download"
                state_write "binaries/fzf" "$_sv"
                return 0
            fi
        fi
    fi

    if [ "$(echo "$current" | cut -d. -f2)" -lt 48 ] 2>/dev/null; then
        local tag ver
        tag=$(curl -sSfL https://api.github.com/repos/junegunn/fzf/releases/latest \
            | grep -oP '"tag_name": "\K[^"]+')
        ver="${tag#v}"
        curl -sSfL "https://github.com/junegunn/fzf/releases/download/${tag}/fzf-${ver}-linux_${ARCH_FZF}.tar.gz" \
            | tar -xz -C "$dest_bin"
        chmod a+rx "$dest_bin/fzf" 2>/dev/null || true
        state_write "binaries/fzf" "$ver"
        log_ok "fzf $ver → $dest_bin/fzf"
    else
        log_ok "fzf up-to-date ($current)"
    fi
}

install_neovim() {
    local opt_parent="$1" dest_bin="$2"
    _need_curl neovim || return 0
    [ -z "${ARCH_NVIM:-}" ] && { log_warn "No official Neovim tarball for $(uname -m) — skipping."; return 0; }
    mkdir -p "$opt_parent" "$dest_bin"

    local pkg="nvim-linux-${ARCH_NVIM}"
    local current="0.0.0"
    if [ -x "${dest_bin}/nvim" ]; then
        current=$("${dest_bin}/nvim" --version 2>/dev/null | head -1 | grep -oP 'NVIM v\K[\d.]+' || echo "0.0.0")
    elif [ "$USER_LOCAL" = true ]; then
        local _sys_nvim
        _sys_nvim=$(command -v nvim 2>/dev/null || true)
        if [ -n "$_sys_nvim" ]; then
            local _sv _smaj _smin
            _sv=$("$_sys_nvim" --version 2>/dev/null | head -1 | grep -oP 'NVIM v\K[\d.]+' || echo "0.0.0")
            _smaj=$(echo "$_sv" | cut -d. -f1)
            _smin=$(echo "$_sv" | cut -d. -f2)
            if ! { [ "${_smaj:-0}" -eq 0 ] && [ "${_smin:-0}" -lt 10 ]; } 2>/dev/null; then
                log_ok "neovim $_sv found in PATH ($_sys_nvim) — skipping download"
                state_write "binaries/nvim" "$_sv"
                return 0
            fi
        fi
    fi

    local major minor
    major=$(echo "$current" | cut -d. -f1)
    minor=$(echo "$current" | cut -d. -f2)

    if { [ "${major:-0}" -eq 0 ] && [ "${minor:-0}" -lt 10 ]; } 2>/dev/null; then
        curl -sSfL "https://github.com/neovim/neovim/releases/latest/download/${pkg}.tar.gz" \
            -o "/tmp/${pkg}.tar.gz"
        rm -rf "${opt_parent:?}/${pkg}"
        tar -C "$opt_parent" -xzf "/tmp/${pkg}.tar.gz"
        rm -f "/tmp/${pkg}.tar.gz"
        ln -sf "${opt_parent}/${pkg}/bin/nvim" "${dest_bin}/nvim"
        chmod a+rx "${opt_parent}/${pkg}/bin/nvim" 2>/dev/null || true

        local nvim_ver
        nvim_ver=$("${dest_bin}/nvim" --version 2>/dev/null | head -1 | grep -oP 'NVIM v\K[\d.]+' || echo "?")
        state_write "binaries/nvim"     "$nvim_ver"
        state_write "binaries/nvim_pkg" "$pkg"
        log_ok "neovim $nvim_ver → $dest_bin/nvim  (tree: $opt_parent/$pkg)"
    else
        log_ok "neovim up-to-date ($current)"
    fi
}

install_starship() {
    local dest_bin="$1"
    _need_curl starship || return 0
    mkdir -p "$dest_bin"

    if [ ! -x "${dest_bin}/starship" ]; then
        if [ "$USER_LOCAL" = true ]; then
            local _sys_starship
            _sys_starship=$(command -v starship 2>/dev/null || true)
            if [ -n "$_sys_starship" ] && [ "$(dirname "$_sys_starship")" != "$dest_bin" ]; then
                local _sv
                _sv=$("$_sys_starship" --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo "?")
                log_ok "starship $_sv found in PATH ($_sys_starship) — skipping download"
                state_write "binaries/starship" "$_sv"
                return 0
            fi
        fi
        curl -sS https://starship.rs/install.sh | sh -s -- --bin-dir "$dest_bin" --yes
        chmod a+rx "${dest_bin}/starship" 2>/dev/null || true
        local ver
        ver=$("${dest_bin}/starship" --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo "?")
        state_write "binaries/starship" "$ver"
        log_ok "starship $ver → $dest_bin/starship"
    else
        log_ok "starship already present"
    fi
}

install_delta() {
    local dest_bin="$1"
    _need_curl delta || return 0
    [ -z "$ARCH_RG" ] && { log_warn "Unknown arch — skipping delta."; return 0; }
    mkdir -p "$dest_bin"

    if [ "$USER_LOCAL" = true ]; then
        local _sys_delta
        _sys_delta=$(command -v delta 2>/dev/null || true)
        if [ -n "$_sys_delta" ] && [ "$(dirname "$_sys_delta")" != "$dest_bin" ]; then
            local _sv
            _sv=$("$_sys_delta" --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo "?")
            log_ok "delta $_sv found in PATH ($_sys_delta) — skipping download"
            state_write "binaries/delta" "$_sv"
            return 0
        fi
    fi

    local latest installed
    latest=$(curl -sS "https://api.github.com/repos/dandavison/delta/releases/latest" \
        | grep -oP '"tag_name":\s*"\K[^"]+' | head -1 || echo "")
    [ -z "$latest" ] && { log_warn "Could not resolve delta version — skipping."; return 0; }

    installed=$("${dest_bin}/delta" --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo "")
    if [ "$installed" = "$latest" ]; then
        log_ok "delta up-to-date ($installed)"
        return 0
    fi

    local tarball="delta-${latest}-${ARCH_RG}.tar.gz"
    local url="https://github.com/dandavison/delta/releases/download/${latest}/${tarball}"
    local tmp_dir
    tmp_dir=$(mktemp -d)
    curl -sL "$url" -o "$tmp_dir/$tarball" || { log_warn "delta download failed — skipping."; rm -rf "$tmp_dir"; return 0; }
    tar -xz -C "$tmp_dir" -f "$tmp_dir/$tarball" --strip-components=1 2>/dev/null || true
    if [ -f "$tmp_dir/delta" ]; then
        install -m 0755 "$tmp_dir/delta" "${dest_bin}/delta"
        state_write "binaries/delta" "$latest"
        log_ok "delta $latest → ${dest_bin}/delta"
    else
        log_warn "delta binary not found in archive — skipping."
    fi
    rm -rf "$tmp_dir"
}

# System-package prereqs are managed by dotfiles-bootstrap.sh
# (which uses apt/dnf/yum/pacman/apk/zypper).  This script only
# verifies their presence and prints a hint if they're missing.
#
# Required prereqs (from bootstrap):  git, curl
# Optional prereqs (from bootstrap):  gcc, unzip
#   gcc   → tree-sitter parser compilation
#   unzip → FiraCode Nerd Font extraction
check_prereq() {
    local cmd="$1" hint="${2:-}"
    if command -v "$cmd" &>/dev/null; then
        log_ok "$cmd: $($cmd --version 2>&1 | head -1)"
        return 0
    fi
    log_warn "$cmd not found${hint:+ — $hint}."
    log_warn "Install it via dotfiles-bootstrap.sh, or: sudo apt install $cmd"
    return 1
}

# Nerd Fonts — required by nvim-web-devicons.
#
# Installs two fonts:
#   1. FiraCode Nerd Font  — primary monospaced coding font
#   2. Symbols Nerd Font Mono    — glyphs-only fallback font; the OS uses
#                                  this for any codepoint missing from the
#                                  primary font, giving complete icon coverage
#
# System install:     /usr/local/share/fonts/NerdFonts/
# User-local install: ~/.local/share/fonts/NerdFonts/
#
# NOTE: In WSL, fonts are installed to the Linux filesystem. Windows Terminal
# reads fonts from the Windows font store, so the fonts must also be installed
# on the Windows host for them to appear in Windows Terminal's font picker.
_is_wsl() { grep -qi microsoft /proc/version 2>/dev/null; }

install_nerd_font() {
    if _is_wsl; then
        log_warn "WSL detected — skipping Linux font install (fonts are not used by Windows Terminal)."
        log_warn "Install both Nerd Fonts on the Windows host instead:"
        log_warn "  https://github.com/ryanoasis/nerd-fonts/releases/latest"
        log_warn "  Extract each zip → select all .ttf → right-click → Install for all users"
        log_warn "  Then set your terminal font to 'FiraCode NFM'."
        return 0
    fi

    local font_dir
    if [ "$USER_LOCAL" = true ]; then
        font_dir="${HOME}/.local/share/fonts/NerdFonts"
    else
        font_dir="/usr/local/share/fonts/NerdFonts"
    fi

    _need_curl "Nerd Font" || return 0
    if ! command -v unzip &>/dev/null; then
        log_warn "unzip not found — skipping Nerd Font install."
        log_warn "Install it (sudo apt install unzip), then re-run."
        return 0
    fi

    mkdir -p "$font_dir"

    _install_one_font() {
        local name="$1" zipfile="$2"
        local marker="$font_dir/.installed_${name}"
        if [ -f "$marker" ]; then
            log_ok "Nerd Font already installed: $name"
            return 0
        fi
        log_info "Installing $name → $font_dir"
        local tmp_zip="/tmp/${zipfile}"
        curl -sSfL -o "$tmp_zip" \
            "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/${zipfile}"
        unzip -qo "$tmp_zip" -d "$font_dir"
        rm -f "$tmp_zip"
        touch "$marker"
        log_ok "$name installed."
    }

    _install_one_font "FiraCode"      "FiraCode.zip"
    _install_one_font "NerdFontsSymbolsOnly" "NerdFontsSymbolsOnly.zip"

    if command -v fc-cache &>/dev/null; then
        fc-cache -f "$font_dir" >/dev/null 2>&1 || true
        log_ok "Font cache refreshed."
    else
        log_warn "fc-cache not found — run: sudo apt install fontconfig && fc-cache -f"
    fi

    state_write "binaries/nerd_font_dir" "$font_dir"
    log_ok "Nerd Fonts installed: $font_dir"
    log_info "Primary : FiraCode NFM"
    log_info "Fallback: NerdFontsSymbolsOnly (fills any missing glyphs automatically)"
}


# ════════════════════════════════════════════════════════════════
# REPO SYNC
# ════════════════════════════════════════════════════════════════
sync_repo() {
    local base="$1"
    if [ -d "$base/.git" ]; then
        log_info "Repo present — pulling (shallow)..."
        if git -C "$base" diff --quiet && git -C "$base" diff --cached --quiet 2>/dev/null; then
            git -C "$base" pull --depth 1
            log_ok "Repo updated: $base"
        else
            log_warn "Local changes in $base — skipping pull."
        fi
    else
        log_info "Cloning dotfiles → $base"
        mkdir -p "$(dirname "$base")"
        git clone --depth 1 --single-branch --no-tags "$GIT_URL" "$base"
        log_ok "Repo cloned: $base"
    fi
    chmod -R a+rX "$base" 2>/dev/null || true
}


# ════════════════════════════════════════════════════════════════
# RUN AS TARGET USER
# Requires: ROLE, USERNAME, USER_LOCAL to be set.
# ════════════════════════════════════════════════════════════════
run_as_target() {
    local cmd="$1"
    if [ "$USER_LOCAL" = true ] || [ "${ROLE:-}" = "root" ]; then
        bash -c "$cmd"
    else
        runuser -l "$USERNAME" -c "$cmd"
    fi
}


# ════════════════════════════════════════════════════════════════
# APPLY DOTFILES
#
# All profiles share a single source tree: src/common/
# ROLE controls only the default theme written on first install.
#
# Requires: ROLE, USERNAME, HOME_DIR, REPO_BASE, PREFIX_BIN, USER_LOCAL
#   ROLE = "root"  → default theme: gruvbox light, template: sanmue
#   ROLE = "user"  → default theme: monokai spectrum, template: moir
# ════════════════════════════════════════════════════════════════
apply_dotfiles() {
    local src="$REPO_BASE/src"

    [ -d "$src" ] || {
        log_error "Dotfiles source missing: $src"
        log_error "Run bootstrap first, or check that the repo cloned correctly."
        exit 1
    }

    if [ "$ROLE" != "root" ] && ! id "$USERNAME" &>/dev/null 2>&1; then
        log_error "User '$USERNAME' does not exist."
        exit 1
    fi

    log_section "Dotfiles → $HOME_DIR  (role: $ROLE)"

    _cp_as_target() {
        local s="$1" d="$2"
        if [ "$ROLE" = "root" ] || [ "$USER_LOCAL" = true ]; then
            cp "$s" "$d"
        else
            runuser -l "$USERNAME" -c "cp '$s' '$d'"
        fi
    }

    _mkdir_as_target() {
        run_as_target "mkdir -p $1"
    }

    _track() { state_track_file "$USERNAME" "$1"; }

    # ── Neovim config ──────────────────────────────────────────
    log_info "Neovim config..."
    _mkdir_as_target "$HOME_DIR/.config/nvim"
    _track "$HOME_DIR/.config/nvim"
    _cp_as_target "$src/.config/nvim/init.lua" "$HOME_DIR/.config/nvim/init.lua"
    _track "$HOME_DIR/.config/nvim/init.lua"
    log_ok "init.lua"

    if [ -f "$src/.config/nvim/lazy-lock.json" ]; then
        _cp_as_target "$src/.config/nvim/lazy-lock.json" "$HOME_DIR/.config/nvim/lazy-lock.json"
        _track "$HOME_DIR/.config/nvim/lazy-lock.json"
        log_ok "lazy-lock.json  (run ':Lazy restore' in Neovim to pin exact plugin versions)"
    fi

    # ── Shell dotfiles ─────────────────────────────────────────
    log_info "Shell dotfiles..."
    _cp_as_target "$src/.bashrc"    "$HOME_DIR/.bashrc"
    _cp_as_target "$src/.gitconfig" "$HOME_DIR/.gitconfig"
    _track "$HOME_DIR/.bashrc"
    _track "$HOME_DIR/.gitconfig"
    log_ok ".bashrc, .gitconfig"
    # Patch DOTFILES_DIR in the installed .bashrc to match the actual repo location
    sed -i 's|^DOTFILES_DIR=.*|DOTFILES_DIR="'"$REPO_BASE"'"|' "$HOME_DIR/.bashrc" 2>/dev/null || true

    # ── Git identity ───────────────────────────────────────────
    # The shipped .gitconfig has no [user] block.  Prompt once so
    # each person gets their own name/email written into their copy.
    local _git_name="" _git_email=""
    if [ "$NON_INTERACTIVE" = false ] && [ -t 0 ]; then
        log_info "Git identity (leave blank to skip — set manually later):"
        read -rp "  git user.name  : " _git_name  </dev/tty || true
        read -rp "  git user.email : " _git_email </dev/tty || true
    fi
    if [ -n "$_git_name" ] || [ -n "$_git_email" ]; then
        local _gc="$HOME_DIR/.gitconfig"
        [ -n "$_git_name" ]  && run_as_target "git config --file '$_gc' user.name  '$_git_name'"
        [ -n "$_git_email" ] && run_as_target "git config --file '$_gc' user.email '$_git_email'"
        log_ok "Git identity set (name='$_git_name' email='$_git_email')"
    else
        log_warn "Git user.name/email not set — run afterwards:"
        log_warn "  git config --global user.name  'Your Name'"
        log_warn "  git config --global user.email 'you@example.com'"
    fi

    # ── Theme templates + role definitions ───────────────────
    log_info "Theme templates..."
    _mkdir_as_target "$HOME_DIR/.config/starship"
    _track "$HOME_DIR/.config/starship"
    for _sf in powerline pills nerd-font dracula seeker moir sanmue sepan; do
        _cp_as_target "$src/.config/starship/${_sf}.toml" "$HOME_DIR/.config/starship/${_sf}.toml"
        _track "$HOME_DIR/.config/starship/${_sf}.toml"
    done
    for _tf in dircolors-template gitcolors-template roles.json palettes.json; do
        _cp_as_target "$src/.config/$_tf" "$HOME_DIR/.config/$_tf"
        _track "$HOME_DIR/.config/$_tf"
    done
    log_ok "Theme templates + roles.json"

    # ── minttyrc (mintty terminal — skip for root) ─────────────
    if [ "$ROLE" != "root" ] && [ -f "$src/.minttyrc" ]; then
        log_info "minttyrc..."
        _cp_as_target "$src/.minttyrc" "$HOME_DIR/.minttyrc"
        _track "$HOME_DIR/.minttyrc"
        log_ok ".minttyrc"
    fi

    # ── Neovim plugins (lazy.nvim + tree-sitter parsers) ──────
    log_info "Neovim plugins — lazy.nvim sync + tree-sitter parser compilation..."
    log_info "(This may take a minute while tree-sitter parsers are compiled from source.)"
    local nvim_bin="${PREFIX_BIN}/nvim"
    local nvim_data_dir="$HOME_DIR/.local/share/nvim"

    if [ ! -x "$nvim_bin" ]; then
        log_warn "nvim not found at $nvim_bin — skipping Lazy sync."
    else
        local nvim_ver
        nvim_ver=$("$nvim_bin" --version 2>/dev/null | head -1 | grep -oP 'NVIM v\K[\d.]+' || echo "0.0.0")
        local nvim_minor
        nvim_minor=$(echo "$nvim_ver" | cut -d. -f2)
        if [ "$(echo "$nvim_ver" | cut -d. -f1)" -eq 0 ] && [ "${nvim_minor:-0}" -lt 10 ] 2>/dev/null; then
            log_warn "nvim $nvim_ver detected — Neovim 0.10+ is recommended."
        fi

        local _path="/usr/local/bin:/usr/bin:/bin"
        [ "$USER_LOCAL" = true ] && _path="${PREFIX_BIN}:${_path}"

        # Zig is the C compiler for treesitter parsers.  Use system zig if present;
        # otherwise install a temporary copy to PREFIX_BIN and remove after compilation.
        if ! command -v zig &>/dev/null; then
            _install_zig_temp || true
        fi

        if [ "$ROLE" = "root" ]; then
            PATH="$_path" HOME=/root "$nvim_bin" --headless "+Lazy! sync" +qa 2>&1 || true
        else
            run_as_target "PATH=${_path} HOME=$HOME_DIR $nvim_bin --headless '+Lazy! sync' +qa" 2>&1 || true
        fi

        _cleanup_zig_temp
        _track "$nvim_data_dir"
        log_ok "Plugins installed (lazy.nvim + tree-sitter parsers)"
    fi

    # palettes.json was copied in the theme templates loop above.
    local pal_out="$HOME_DIR/.config/palettes.json"
    if [ "$ROLE" != "root" ] && [ -n "$USERNAME" ]; then
        chown "$USERNAME":"$USERNAME" "$pal_out" 2>/dev/null || true
    fi


    # -- Default theme + starship template (first install only) ----
    # Skipped on re-install so the user active choices are preserved.
    _track "$HOME_DIR/.config/starship.toml"
    _track "$HOME_DIR/.config/dotfiles-starship-template"
    _track "$HOME_DIR/.config/nvim/theme.lua"
    _track "$HOME_DIR/.config/git"
    _track "$HOME_DIR/.config/git/theme.conf"

    if [ -f "$HOME_DIR/.config/nvim/theme.lua" ]; then
        local _cur_theme
        _cur_theme=$(grep -oP 'active_theme = "\K[^"]+' "$HOME_DIR/.config/nvim/theme.lua" 2>/dev/null || echo "unknown")
        log_ok "Theme already set ($_cur_theme) -- preserving user choice."
    else
        log_info "Default theme + starship template (first install)..."

        # -- Default values by role -----------------------------------------
        local _def_theme _def_flavor _def_tmpl _sep
        _sep=$(printf '\xEE\x82\xB0')
        if [ "$ROLE" = "root" ]; then
            _def_theme="gruvbox"; _def_flavor="light"; _def_tmpl="sanmue"
        else
            _def_theme="monokai"; _def_flavor="spectrum"; _def_tmpl="moir"
        fi
        [ -n "$THEME_ARG" ]         && _def_theme="$THEME_ARG"
        [ -n "$FLAVOR_ARG" ]        && _def_flavor="$FLAVOR_ARG"
        # If --theme was overridden without --flavor, clear the role default so
        # render-theme.py falls back to each theme's _default_flavor in palettes.json.
        [ -n "$THEME_ARG" ] && [ -z "$FLAVOR_ARG" ] && _def_flavor=""
        [ -n "$STARSHIP_TMPL_ARG" ] && _def_tmpl="$STARSHIP_TMPL_ARG"

        # -- Interactive starship template selection -------------------------
        if [ "$NON_INTERACTIVE" = false ] && [ -z "$STARSHIP_TMPL_ARG" ] && [ -t 0 ]; then
            log_info "Available starship templates:"
            printf '    1. powerline  (powerline segments with NF icons)\n'
            printf '    2. pills      (pill-shaped modules)\n'
            printf '    3. nerd-font  (comprehensive NF icons, fill-separated)\n'
            printf '    4. dracula    (badge-style with fill separator)\n'
            printf '    5. seeker     (two-line with right border)\n'
            printf '    6. moir       (dense powerline + right-side modules)\n'
            printf '    7. sanmue     (two-line flat bg, fill-split, Power10k-inspired)\n'
            printf '    8. sepan      (powerline segments, full module coverage, two-line)\n'
            read -rp "  Select starship template [${_def_tmpl}]: " _tmpl_choice </dev/tty || true
            if [ -n "$_tmpl_choice" ]; then
                case "$_tmpl_choice" in
                    1) _def_tmpl="powerline" ;;
                    2) _def_tmpl="pills" ;;
                    3) _def_tmpl="nerd-font" ;;
                    4) _def_tmpl="dracula" ;;
                    5) _def_tmpl="seeker" ;;
                    6) _def_tmpl="moir" ;;
                    7) _def_tmpl="sanmue" ;;
                    8) _def_tmpl="sepan" ;;
                    powerline|pills|nerd-font|dracula|seeker|moir|sanmue|sepan)
                        _def_tmpl="$_tmpl_choice" ;;
                    *) log_warn "Unknown template '$_tmpl_choice' -- using ${_def_tmpl}." ;;
                esac
            fi
        fi

        # -- Validate template file exists ----------------------------------
        local _tmpl_file="$HOME_DIR/.config/starship/${_def_tmpl}.toml"
        if [ ! -f "$_tmpl_file" ]; then
            log_warn "Template file not found: $_tmpl_file -- falling back to powerline."
            _def_tmpl="powerline"
            _tmpl_file="$HOME_DIR/.config/starship/powerline.toml"
        fi

        # -- Write active template name -------------------------------------
        if [ "$ROLE" = "root" ] || [ "$USER_LOCAL" = true ]; then
            echo "$_def_tmpl" > "$HOME_DIR/.config/dotfiles-starship-template"
        else
            runuser -l "$USERNAME" -c "echo '$_def_tmpl' > '$HOME_DIR/.config/dotfiles-starship-template'"
        fi

        _mkdir_as_target "$HOME_DIR/.config/git"

        if ! command -v python3 &>/dev/null; then
            log_warn "python3 not found -- skipping theme render."
            log_warn "Install it with: sudo apt install python3.12  then run: set-theme $_def_theme $_def_flavor"
        else
        python3 "$src/.config/render-theme.py" set-theme \
            --palette            "$pal_out"             \
            --theme              "$_def_theme"          \
            --flavor             "$_def_flavor"         \
            --sep                "$_sep"                \
            --starship-template  "$_tmpl_file"          \
            --starship-output    "$HOME_DIR/.config/starship.toml"    \
            --dircolors-template "$HOME_DIR/.config/dircolors-template" \
            --dircolors-output   "$HOME_DIR/.dircolors"               \
            --git-template       "$HOME_DIR/.config/gitcolors-template" \
            --git-output         "$HOME_DIR/.config/git/theme.conf"   \
            --nvim               "$HOME_DIR/.config/nvim/theme.lua"

        if [ "$ROLE" != "root" ] && [ -n "$USERNAME" ]; then
            for _f in \
                    "$HOME_DIR/.config/starship.toml"              \
                    "$HOME_DIR/.config/dotfiles-starship-template" \
                    "$HOME_DIR/.dircolors"                         \
                    "$HOME_DIR/.config/git/theme.conf"             \
                    "$HOME_DIR/.config/nvim/theme.lua"; do
                [ -f "$_f" ] && chown "$USERNAME":"$USERNAME" "$_f" 2>/dev/null || true
            done
            chown "$USERNAME":"$USERNAME" "$HOME_DIR/.config/git" 2>/dev/null || true
        fi

        run_as_target "git config --global include.path ~/.config/git/theme.conf" 2>/dev/null || true
        log_ok "Theme: $_def_theme ($_def_flavor)  template: $_def_tmpl"
        fi  # python3 check
    fi


    log_ok "Done — $USERNAME ($HOME_DIR)"
}

# ════════════════════════════════════════════════════════════════
# REMOVE USER DOTFILES
# Reads the tracked file list from state and deletes each entry.
# ════════════════════════════════════════════════════════════════
remove_user_dotfiles() {
    local consumer="$1"
    local files_list="$STATE_DIR/users/$consumer/files"

    if [ ! -f "$files_list" ]; then
        log_warn "No install record for '$consumer' — nothing to remove."
        return 0
    fi

    log_section "Removing dotfiles for $consumer"

    while IFS= read -r path; do
        [ -z "$path" ] && continue
        if [ -e "$path" ] || [ -L "$path" ]; then
            rm -rf "$path"
            log_ok "Removed: $path"
        else
            log_warn "Already gone: $path"
        fi
    done < "$files_list"

    # Clean up runtime caches and state dirs created by the tools
    # (not tracked in the files list since tools create them at runtime).
    local home_dir
    home_dir=$(cat "$STATE_DIR/users/$consumer/home" 2>/dev/null || echo "")
    if [ -n "$home_dir" ]; then
        for _d in \
            "$home_dir/.cache/nvim" \
            "$home_dir/.cache/starship" \
            "$home_dir/.local/state/nvim"; do
            if [ -e "$_d" ]; then
                rm -rf "$_d"
                log_ok "Removed cache: $_d"
            fi
        done
        # Remove parent dirs only if now empty (safe — rmdir fails silently on non-empty).
        rmdir "$home_dir/.cache"        2>/dev/null || true
        rmdir "$home_dir/.local/state"  2>/dev/null || true
    fi

    state_remove_consumer "$consumer"
    log_ok "State record removed for $consumer"
}


# ════════════════════════════════════════════════════════════════
# REMOVE SHARED TOOLS
# Cascades through every registered consumer, removing their tracked
# dotfiles first, then tears down shared binaries, fonts, and state.
# This guarantees no $HOME ends up with a .bashrc that references a
# binary we just deleted.
# ════════════════════════════════════════════════════════════════
remove_shared_tools() {
    local consumers
    consumers=$(state_list_consumers)

    if [ -n "$consumers" ]; then
        log_section "Cascading uninstall — removing all consumer dotfiles first"
        while IFS= read -r c; do
            [ -z "$c" ] && continue
            remove_user_dotfiles "$c"
        done <<< "$consumers"
    else
        log_info "No registered consumers."
    fi

    log_section "Removing shared tools"

    # Neovim application tree (under /opt or ~/.local/opt)
    local nvim_pkg
    nvim_pkg=$(state_read "binaries/nvim_pkg")
    if [ -n "$nvim_pkg" ] && [ -d "${NVIM_OPT_PARENT}/${nvim_pkg}" ]; then
        rm -rf "${NVIM_OPT_PARENT:?}/${nvim_pkg}"
        log_ok "Removed: ${NVIM_OPT_PARENT}/${nvim_pkg}"
    fi

    # Binary symlinks / executables
    for _b in rg fzf nvim starship delta; do
        local _bp="${PREFIX_BIN}/$_b"
        if [ -e "$_bp" ] || [ -L "$_bp" ]; then
            rm -f "$_bp"
            log_ok "Removed binary: $_bp"
        fi
    done

    # Nerd Font
    local nf_dir
    nf_dir=$(state_read "binaries/nerd_font_dir")
    if [ -n "$nf_dir" ] && [ -d "$nf_dir" ]; then
        rm -rf "$nf_dir"
        command -v fc-cache &>/dev/null && fc-cache -f >/dev/null 2>&1 || true
        log_ok "Removed Nerd Font: $nf_dir"
    fi

    # Canonical repo clone
    if [ -d "$REPO_BASE" ]; then
        rm -rf "$REPO_BASE"
        log_ok "Removed repo: $REPO_BASE"
    fi

    # State directory
    if [ -d "$STATE_DIR" ]; then
        rm -rf "$STATE_DIR"
        log_ok "Removed state: $STATE_DIR"
    fi

    log_ok "All shared tools and state removed."
}


# ════════════════════════════════════════════════════════════════
# COMMAND: bootstrap
# Installs shared tools into /usr/local/bin (or PREFIX_BIN for
# user-local) and clones the canonical repo.  Does NOT touch any
# user home directories.
# ════════════════════════════════════════════════════════════════
cmd_bootstrap() {
    require_root

    log_section "Bootstrap — shared tools + canonical repo"
    log_info "Bin dir  : $PREFIX_BIN"
    log_info "Opt dir  : $NVIM_OPT_PARENT"
    log_info "Repo     : $REPO_BASE"

    state_init
    state_write "platform"       "linux"
    state_write "mode"           "system"
    state_write "binary_dir"     "$PREFIX_BIN"
    state_write "opt_dir"        "$NVIM_OPT_PARENT"
    state_write "repo_base"      "$REPO_BASE"
    state_write "bootstrapped_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    log_section "System prereqs (managed by bootstrap)"
    check_prereq unzip  "Nerd Font cannot be extracted"
    check_prereq python3 "theme rendering will be skipped — install with: sudo apt install python3.12"

    log_section "Shared binaries"
    install_ripgrep  "$PREFIX_BIN"
    install_fzf      "$PREFIX_BIN"
    install_neovim   "$NVIM_OPT_PARENT" "$PREFIX_BIN"
    install_starship "$PREFIX_BIN"
    install_delta    "$PREFIX_BIN"
    install_nerd_font

    log_section "Canonical repository"
    sync_repo "$REPO_BASE"

    log_section "Bootstrap complete"
    log_ok "Shared tools on PATH for all users with $PREFIX_BIN."
    log_ok "Repo: $REPO_BASE"
    log_ok ""
    log_ok "Next steps — use the canonical script from now on:"
    log_ok "  sudo $REPO_BASE/src/init-dotfiles.sh install root"
    log_ok "  sudo $REPO_BASE/src/init-dotfiles.sh install user <name>"
}


# ════════════════════════════════════════════════════════════════
# COMMAND: install (system — root or named user)
# ════════════════════════════════════════════════════════════════
cmd_install_system() {
    require_root

    [ -d "$REPO_BASE/.git" ] || {
        log_error "Canonical repo not found at $REPO_BASE."
        log_error "Run bootstrap first:  sudo $0 bootstrap"
        exit 1
    }

    case "$SUBCMD" in
        root)
            [ -n "$USERNAME_ARG" ] && log_warn "Ignoring extra argument '$USERNAME_ARG' for 'install root'."
            ROLE=root; USERNAME=root; HOME_DIR=/root
            ;;
        user)
            [ -z "$USERNAME_ARG" ] && {
                log_error "Username required:  $0 install user <username>"
                exit 1
            }
            ROLE=user; USERNAME="$USERNAME_ARG"; HOME_DIR="/home/$USERNAME_ARG"
            ;;
        "")
            log_error "Subcommand required: 'install root' or 'install user <name>'."
            usage
            ;;
        *)
            log_error "Unknown subcommand '$SUBCMD'. Expected 'root' or 'user'."
            usage
            ;;
    esac

    log_section "Repository update"
    sync_repo "$REPO_BASE"

    state_init
    if state_consumer_exists "$USERNAME"; then
        log_info "Consumer '$USERNAME' already registered — re-applying dotfiles."
        state_reset_files "$USERNAME"
    else
        state_add_consumer "$USERNAME" "$HOME_DIR"
    fi

    apply_dotfiles

    log_section "Install complete"
    log_ok "Open a new terminal as $USERNAME."
    if _is_wsl; then
        log_warn "WSL: set your Windows Terminal font to 'FiraCode NFM' and install"
        log_warn "both Nerd Fonts on the Windows host if you haven't already."
        log_warn "  https://github.com/ryanoasis/nerd-fonts/releases/latest"
    fi
}


# ════════════════════════════════════════════════════════════════
# COMMAND: install --user-local
# Installs binaries and dotfiles entirely under $HOME — no sudo.
# ════════════════════════════════════════════════════════════════
cmd_install_user_local() {
    log_section "User-local install"
    log_info "User     : $(id -un)"
    log_info "Home     : $HOME"
    log_info "Bin      : $PREFIX_BIN"
    log_info "Repo     : $REPO_BASE"

    ROLE=user
    USERNAME=$(id -un)
    HOME_DIR="$HOME"

    state_init
    state_write "platform"    "linux"
    state_write "mode"        "user-local"
    state_write "binary_dir"  "$PREFIX_BIN"
    state_write "opt_dir"     "$NVIM_OPT_PARENT"
    state_write "repo_base"   "$REPO_BASE"
    state_write "installed_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    log_section "System prereqs (managed by bootstrap)"
    check_prereq unzip  "Nerd Font cannot be extracted"
    check_prereq python3 "theme rendering will be skipped — install with: sudo apt install python3.12"

    log_section "User-local binaries"
    install_ripgrep  "$PREFIX_BIN"
    install_fzf      "$PREFIX_BIN"
    install_neovim   "$NVIM_OPT_PARENT" "$PREFIX_BIN"
    install_starship "$PREFIX_BIN"
    install_delta    "$PREFIX_BIN"
    install_nerd_font

    log_section "Repository"
    sync_repo "$REPO_BASE"

    state_init
    if state_consumer_exists "$USERNAME"; then
        log_info "Re-applying dotfiles for $USERNAME."
        state_reset_files "$USERNAME"
    else
        state_add_consumer "$USERNAME" "$HOME_DIR"
    fi

    apply_dotfiles

    log_section "User-local install complete"
    log_ok "Ensure $PREFIX_BIN is on your PATH — the shipped .bashrc handles this."
    log_ok "Open a new shell."
    if _is_wsl; then
        log_warn "WSL: set your Windows Terminal font to 'FiraCode NFM' and install"
        log_warn "both Nerd Fonts on the Windows host if you haven't already."
        log_warn "  https://github.com/ryanoasis/nerd-fonts/releases/latest"
    fi
}


# ════════════════════════════════════════════════════════════════
# COMMAND: uninstall user / root  (system)
# Removes the tracked dotfiles for the named consumer and
# deregisters them.  Shared tools are NOT removed; use
# 'uninstall --all' for that (after all consumers are gone).
# ════════════════════════════════════════════════════════════════
cmd_uninstall_consumer() {
    require_root

    local consumer="$1"

    if ! state_consumer_exists "$consumer"; then
        log_error "No install record for '$consumer' in state ($STATE_DIR)."
        log_error "List registered consumers with:  ls $STATE_DIR/users/"
        exit 1
    fi

    remove_user_dotfiles "$consumer"

    local remaining
    remaining=$(state_consumer_count)

    log_section "Uninstall complete"
    log_ok "$consumer — dotfiles removed."
    log_warn "Existing shells for '$consumer' still hold starship/dircolors in"
    log_warn "memory.  Open a NEW terminal (or run 'exec bash') to refresh."

    if [ "$remaining" -gt 0 ]; then
        log_info "$remaining consumer(s) still installed; shared tools kept."
        log_info "Remaining: $(state_list_consumers | tr '\n' ' ')"
    else
        log_info "No consumers remain."
        log_info "To also remove shared tools (rg, fzf, nvim, starship, repo):"
        log_info "  sudo $0 uninstall --all"
    fi
}


# ════════════════════════════════════════════════════════════════
# COMMAND: uninstall --user-local
# Removes user-local dotfiles AND the locally installed binaries,
# opt tree, repo, and state.
# ════════════════════════════════════════════════════════════════
cmd_uninstall_user_local() {
    local consumer
    consumer=$(id -un)

    log_section "User-local uninstall"

    if state_consumer_exists "$consumer"; then
        remove_user_dotfiles "$consumer"
    else
        log_warn "No install record found — will still remove binaries and repo."
    fi

    log_info "Removing user-local binaries..."
    for _b in rg fzf nvim starship delta; do
        local _bp="${PREFIX_BIN}/$_b"
        if [ -e "$_bp" ] || [ -L "$_bp" ]; then
            rm -f "$_bp"
            log_ok "Removed: $_bp"
        fi
    done

    local nvim_pkg
    nvim_pkg=$(state_read "binaries/nvim_pkg")
    if [ -n "$nvim_pkg" ] && [ -d "${NVIM_OPT_PARENT}/${nvim_pkg}" ]; then
        rm -rf "${NVIM_OPT_PARENT:?}/${nvim_pkg}"
        log_ok "Removed: ${NVIM_OPT_PARENT}/${nvim_pkg}"
    fi

    local nf_dir
    nf_dir=$(state_read "binaries/nerd_font_dir")
    if [ -n "$nf_dir" ] && [ -d "$nf_dir" ]; then
        rm -rf "$nf_dir"
        command -v fc-cache &>/dev/null && fc-cache -f >/dev/null 2>&1 || true
        log_ok "Removed Nerd Font: $nf_dir"
    fi

    if [ -d "$REPO_BASE" ]; then
        rm -rf "$REPO_BASE"
        log_ok "Removed repo: $REPO_BASE"
    fi

    if [ -d "$STATE_DIR" ]; then
        rm -rf "$STATE_DIR"
        log_ok "Removed state: $STATE_DIR"
    fi

    log_section "User-local uninstall complete"
    log_ok "Everything under $PREFIX_BIN and $REPO_BASE removed."
    log_warn "Your current shell still holds starship/dircolors in memory."
    log_warn "Open a NEW terminal (or run 'exec bash') to refresh."
}


# ════════════════════════════════════════════════════════════════
# COMMAND: uninstall --all  (system)
# Cascades through every registered consumer (removing their tracked
# dotfiles), then removes shared tools, binaries, repo, and state.
# ════════════════════════════════════════════════════════════════
cmd_uninstall_all() {
    require_root
    log_section "Uninstall --all"

    local remaining
    remaining=$(state_consumer_count)
    if [ "$remaining" -gt 0 ]; then
        local names
        names=$(state_list_consumers | tr '\n' ' ')
        if [ "$FORCE" = true ]; then
            log_warn "$remaining consumer(s) still installed: $names"
            log_warn "--force given — removing shared tools anyway."
        else
            log_error "$remaining consumer(s) still have dotfiles installed: $names"
            log_error "Uninstall each consumer first, then re-run uninstall --all."
            log_error "  sudo $0 uninstall user <username>"
            log_error "  sudo $0 uninstall root"
            log_error "Or to remove everything without uninstalling each user first:"
            log_error "  sudo $0 uninstall --all --force"
            exit 1
        fi
    fi

    remove_shared_tools
    log_warn "Any open shells on this host still hold starship/dircolors in"
    log_warn "memory.  Open NEW terminals (or run 'exec bash') to refresh."
}


# ════════════════════════════════════════════════════════════════
# MAIN DISPATCH
# ════════════════════════════════════════════════════════════════
case "$COMMAND" in

    bootstrap)
        cmd_bootstrap
        ;;

    install)
        if [ "$USER_LOCAL" = true ]; then
            cmd_install_user_local
        else
            cmd_install_system
        fi
        ;;

    uninstall)
        if [ "$USER_LOCAL" = true ]; then
            cmd_uninstall_user_local
        elif [ "$UNINSTALL_ALL" = true ]; then
            cmd_uninstall_all
        elif [ "$SUBCMD" = "root" ]; then
            cmd_uninstall_consumer "root"
        elif [ "$SUBCMD" = "user" ]; then
            [ -z "$USERNAME_ARG" ] && {
                log_error "Username required:  $0 uninstall user <username>"
                exit 1
            }
            cmd_uninstall_consumer "$USERNAME_ARG"
        else
            log_error "Unknown uninstall target: '$SUBCMD'"
            usage
        fi
        ;;

    *)
        log_error "Unknown command: '$COMMAND'"
        usage
        ;;
esac
