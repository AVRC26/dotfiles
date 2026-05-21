#!/bin/bash
set -e

# ════════════════════════════════════════════════════════════════
#  dotfiles-bootstrap.sh
#
#  One-shot entry point.  Download this file, run it once, and
#  it will clone the dotfiles repo then hand off to the master
#  installer inside the cloned tree.
#
#  Install for yourself — auto-detects root vs. user (recommended):
#    curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
#        | sudo bash -s -- --install-self   # with sudo
#    curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
#        | bash -s -- --install-self        # without sudo
#
#  System install (sudo required — installs to /usr/local/*):
#    curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
#        | sudo bash
#
#  User-local install (no sudo — installs under $HOME):
#    curl -fsSL https://raw.githubusercontent.com/AVRC26/dotfiles/master/dotfiles-bootstrap.sh \
#        | bash -s -- --user-local
#
#  Flags:
#    --user-local   Install under $HOME only; no root required
#    --install-self Also apply dotfiles to the invoking user (detects root automatically)
# ════════════════════════════════════════════════════════════════

# ── Colour logging ───────────────────────────────────────────────
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

# ── Usage ────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage:
  System (sudo):      sudo bash dotfiles-bootstrap.sh [--install-self]
  User-local:               bash dotfiles-bootstrap.sh --user-local
  Auto-detect:              bash dotfiles-bootstrap.sh --install-self

Flags:
  --user-local    Install under \$HOME only (no sudo required)
  --install-self  Apply dotfiles to the invoking user after bootstrap.
                  With sudo: binaries → /usr/local/bin, dotfiles → \$SUDO_USER's home.
                  Without sudo: auto-switches to --user-local; checks PATH for existing
                  binaries before downloading to ~/.local/bin.
EOF
    exit 1
}

# ── Argument parsing ─────────────────────────────────────────────
USER_LOCAL=false
INSTALL_SELF=false

for arg in "$@"; do
    case "$arg" in
        --user-local)   USER_LOCAL=true    ;;
        --install-self) INSTALL_SELF=true  ;;
        -h|--help)      usage ;;
        *) log_warn "Ignoring unknown flag: $arg" ;;
    esac
done

# --install-self without root implies --user-local
if [ "$INSTALL_SELF" = true ] && [ "$USER_LOCAL" = false ] && [ "${EUID:-$(id -u)}" -ne 0 ]; then
    log_info "--install-self: not running as root — switching to --user-local mode."
    USER_LOCAL=true
fi

# ── Privilege check ──────────────────────────────────────────────
if [ "$USER_LOCAL" = false ] && [ "${EUID:-$(id -u)}" -ne 0 ]; then
    log_error "System install requires root (sudo)."
    log_error "For a no-sudo install, add --user-local or --install-self:"
    log_error "  bash dotfiles-bootstrap.sh --user-local"
    log_error "  bash dotfiles-bootstrap.sh --install-self"
    exit 1
fi

# ── Prerequisite checks ──────────────────────────────────────────
# Auto-install missing prerequisites when running as root and a known
# package manager is available.  Otherwise print clear instructions
# and exit.  Supports apt-get, dnf, yum, pacman, apk, zypper.
log_section "Prerequisite checks"

_pkg_install() {
    local pkg="$1"
    if command -v apt-get &>/dev/null; then
        apt-get update -y >/dev/null 2>&1 || true
        apt-get install -y "$pkg"
    elif command -v dnf &>/dev/null; then
        dnf install -y "$pkg"
    elif command -v yum &>/dev/null; then
        yum install -y "$pkg"
    elif command -v pacman &>/dev/null; then
        pacman -Sy --noconfirm "$pkg"
    elif command -v apk &>/dev/null; then
        apk add --no-cache "$pkg"
    elif command -v zypper &>/dev/null; then
        zypper install -y "$pkg"
    else
        return 1
    fi
}

_ensure_prereq() {
    local cmd="$1" pkg="${2:-$1}"
    if command -v "$cmd" &>/dev/null; then
        log_ok "$cmd: $($cmd --version 2>&1 | head -1)"
        return 0
    fi
    if [ "${EUID:-$(id -u)}" -eq 0 ]; then
        log_info "$cmd not found — installing $pkg..."
        if _pkg_install "$pkg"; then
            log_ok "$cmd installed: $($cmd --version 2>&1 | head -1)"
            return 0
        fi
        log_error "Failed to install $pkg automatically."
        log_error "Install it manually, then re-run this script."
        exit 1
    fi
    log_error "$cmd not found and not running as root."
    log_error "Install it first: sudo apt install $pkg   (or dnf/yum/pacman/apk/zypper equivalent)"
    exit 1
}

# Same as _ensure_prereq but does NOT exit on failure.  Used for
# optional system packages whose absence only degrades a feature
# (e.g. gcc → no tree-sitter parsers; unzip → no Nerd Font).
_ensure_prereq_optional() {
    local cmd="$1" pkg="${2:-$1}"
    if command -v "$cmd" &>/dev/null; then
        log_ok "$cmd: $($cmd --version 2>&1 | head -1)"
        return 0
    fi
    if [ "${EUID:-$(id -u)}" -eq 0 ]; then
        log_info "$cmd not found — installing $pkg..."
        if _pkg_install "$pkg"; then
            log_ok "$cmd installed: $($cmd --version 2>&1 | head -1)"
            return 0
        fi
        log_warn "Failed to install $pkg — related features will be skipped."
        return 0
    fi
    log_warn "$cmd not found — install with: sudo apt install $pkg"
    log_warn "  (without $cmd, related features will be skipped)"
    return 0
}

# Required to clone the repo
_ensure_prereq git
_ensure_prereq curl

# Required later by init-dotfiles.sh:
#   unzip → FiraCode Nerd Font extraction (optional — skipped if absent)
_ensure_prereq_optional unzip

# ── Determine repo destination ───────────────────────────────────
GIT_URL="https://github.com/AVRC26/dotfiles.git"

if [ "$USER_LOCAL" = true ]; then
    REPO_DEST="${HOME}/.local/share/dotfiles"
    log_section "User-local bootstrap"
    log_info "Repo → $REPO_DEST"
else
    REPO_DEST="/usr/local/share/dotfiles"
    log_section "System bootstrap"
    log_info "Repo → $REPO_DEST"
fi

# ── Clone or update repo ─────────────────────────────────────────
log_section "Repository"

if [ -d "$REPO_DEST/.git" ]; then
    log_info "Repo already present — updating..."
    if git -C "$REPO_DEST" diff --quiet && git -C "$REPO_DEST" diff --cached --quiet 2>/dev/null; then
        git -C "$REPO_DEST" pull --depth 1
        log_ok "Updated: $REPO_DEST"
    else
        log_warn "Local changes detected in $REPO_DEST — skipping pull."
    fi
else
    log_info "Cloning dotfiles repo..."
    mkdir -p "$(dirname "$REPO_DEST")"
    git clone --depth 1 --single-branch --no-tags "$GIT_URL" "$REPO_DEST"
    log_ok "Cloned to: $REPO_DEST"
fi

chmod -R a+rX "$REPO_DEST" 2>/dev/null || true

# ── Hand off to init-dotfiles.sh ────────────────────────────────
INIT_SCRIPT="$REPO_DEST/src/init-dotfiles.sh"

if [ ! -f "$INIT_SCRIPT" ]; then
    log_error "init-dotfiles.sh not found in cloned repo ($INIT_SCRIPT)."
    log_error "The repo may be on an unexpected branch. Check: $REPO_DEST"
    exit 1
fi

chmod +x "$INIT_SCRIPT"

log_section "Handing off to init-dotfiles.sh"

if [ "$USER_LOCAL" = true ]; then
    log_info "Running: $INIT_SCRIPT install --user-local"
    exec "$INIT_SCRIPT" install --user-local
else
    if [ "$INSTALL_SELF" = true ]; then
        # Determine the real user: person who invoked sudo (or root itself).
        REAL_USER="${SUDO_USER:-$(id -un)}"

        log_info "Running: $INIT_SCRIPT bootstrap"
        "$INIT_SCRIPT" bootstrap

        log_section "Applying dotfiles for $REAL_USER"
        if [ "$REAL_USER" = "root" ]; then
            log_info "Running: $INIT_SCRIPT install root"
            exec "$INIT_SCRIPT" install root
        else
            log_info "Running: $INIT_SCRIPT install user $REAL_USER"
            exec "$INIT_SCRIPT" install user "$REAL_USER"
        fi
    else
        log_info "Running: $INIT_SCRIPT bootstrap"
        exec "$INIT_SCRIPT" bootstrap

        # (exec replaces the process; lines below are informational only)
        log_section "Bootstrap complete"
        log_ok "Shared tools installed. Repo: $REPO_DEST"
        log_ok "Next steps:"
        log_ok "  sudo $INIT_SCRIPT install root"
        log_ok "  sudo $INIT_SCRIPT install user <username>"
    fi
fi
