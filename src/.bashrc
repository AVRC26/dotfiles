# ~/.bashrc: executed by bash(1) for non-login shells.

case $- in
    *i*) ;;
      *) return;;
esac

# ── History ──────────────────────────────────────────────
HISTCONTROL=ignoreboth
shopt -s histappend
HISTSIZE=5000
HISTFILESIZE=10000

# ── Shell options ────────────────────────────────────────
shopt -s checkwinsize

# ── PATH ─────────────────────────────────────────────────
export PATH="$HOME/.local/bin:$PATH"

# ── Debian chroot label ──────────────────────────────────
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# ── Dircolors (rendered by set-theme into ~/.dircolors) ──────
if [ -x /usr/bin/dircolors ]; then
    if [ -f "$HOME/.dircolors" ]; then
        eval "$(dircolors "$HOME/.dircolors")"
    else
        eval "$(dircolors -b)"
    fi

    alias ls='ls --color=auto'
    alias dir='dir --color=auto'
    alias vdir='vdir --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# ── General aliases ──────────────────────────────────────
alias l='ls -l'
alias ll='ls -lart'
alias vi='nvim'

# ── Git aliases ──────────────────────────────────────────
alias gs='git status'
alias gd='git diff'
alias gvd='git d'
alias ga='git add'
alias gc='git commit -m'
alias gk='git checkout'

# ── Tech stack aliases ───────────────────────────────────
alias k='kubectl'
alias tf='terraform'
alias dc='docker compose'
alias activate='source .venv/bin/activate'

# ── Theme switcher ───────────────────────────────────────
# Python logic lives in render-theme.py in the dotfiles repo.
# Shell-side effects (dircolors eval, git config include) must stay in bash.

DOTFILES_DIR="/usr/local/share/dotfiles"

set-theme() {
    local theme='' flavor='' template=''
    local pal="$HOME/.config/palettes.json"
    local renderer="$DOTFILES_DIR/src/.config/render-theme.py"
    local tmpl_file="$HOME/.config/dotfiles-starship-template"
    local tmpl sep

    # Named args; positional fallback for backwards compat
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --theme|-t)             theme="$2";    shift 2 ;;
            --flavor|-f)            flavor="$2";   shift 2 ;;
            --starship-template|-T) template="$2"; shift 2 ;;
            --help|-h)              theme='--help'; shift ;;
            --*)  echo "set-theme: unknown option '$1'" >&2; return 1 ;;
            *)  [[ -z "$theme" ]]  && { theme="$1";  shift; continue; }
                [[ -z "$flavor" ]] && { flavor="$1"; shift; continue; }
                echo "set-theme: unexpected argument '$1'" >&2; return 1 ;;
        esac
    done

    [[ -f "$renderer" ]] || { echo "set-theme: render-theme.py not found — re-run init-dotfiles.sh" >&2; return 1; }

    if [[ -z "$theme" || "$theme" == "--help" ]]; then
        [[ -f "$pal" ]] && python3 "$renderer" help --palette "$pal" \
                        || echo "Usage: set-theme --theme NAME [--flavor NAME] [--starship-template NAME]"
        return 0
    fi

    [[ -f "$pal" ]] || { echo "set-theme: palettes.json not found — re-run init-dotfiles.sh" >&2; return 1; }

    # Resolve active template (arg > saved > default)
    if [[ -n "$template" ]]; then
        tmpl="$template"
        echo "$tmpl" > "$tmpl_file"
    else
        tmpl=$(cat "$tmpl_file" 2>/dev/null || echo "moir")
    fi

    sep=$''   # U+E0B0 powerline right-arrow

    python3 "$renderer" set-theme \
        --palette            "$pal" \
        --theme              "$theme" \
        --flavor             "$flavor" \
        --sep                "$sep" \
        --starship-template  "$HOME/.config/starship/${tmpl}.toml" \
        --starship-output    "$HOME/.config/starship.toml" \
        --dircolors-template "$HOME/.config/dircolors-template" \
        --dircolors-output   "$HOME/.dircolors" \
        --git-template       "$HOME/.config/gitcolors-template" \
        --git-output         "$HOME/.config/git/theme.conf" \
        --nvim               "$HOME/.config/nvim/theme.lua" || return 1

    [[ -f "$HOME/.dircolors" ]] && eval "$(dircolors "$HOME/.dircolors")"
    if ! grep -qF 'theme.conf' "$HOME/.gitconfig" 2>/dev/null; then
        git config --global include.path '~/.config/git/theme.conf' 2>/dev/null || true
    fi
}

get-theme() {
    local theme_lua="$HOME/.config/nvim/theme.lua"
    local tmpl_file="$HOME/.config/dotfiles-starship-template"

    if [[ ! -f "$theme_lua" ]]; then
        echo "get-theme: theme.lua not found — run set-theme first" >&2
        return 1
    fi

    local theme flavor template
    theme=$(grep 'active_theme'   "$theme_lua" | sed 's/.*"\(.*\)".*/\1/')
    flavor=$(grep -v 'active_theme' "$theme_lua" | grep 'vim\.g\.' | sed 's/.*"\(.*\)".*/\1/')
    template=$(cat "$tmpl_file" 2>/dev/null || echo "unknown")

    printf "Theme:    %s\nFlavor:   %s\nTemplate: %s\n" \
        "$theme" "${flavor:--}" "$template"
}

# ── Bash completion ──────────────────────────────────────
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# ── fzf key bindings (Ctrl+R history, Ctrl+T file picker) ────
if command -v fzf &>/dev/null; then
    if fzf_init=$(fzf --bash 2>/dev/null); then
        eval "$fzf_init"
    elif [ -f /usr/share/doc/fzf/examples/key-bindings.bash ]; then
        source /usr/share/doc/fzf/examples/key-bindings.bash
    fi
fi

# ── Starship prompt ──────────────────────────────────────
if command -v starship &>/dev/null; then
    eval "$(starship init bash)"
fi

# ── Windows Terminal: disable BCE to prevent background streak on scroll ─
# WT_SESSION is set by Windows Terminal in all shells (including WSL).
# \e[?117h disables Background Color Erase (DECECM off) so that new lines
# created during scroll use the default background, not the prompt's last
# active segment color. See: https://github.com/microsoft/terminal/discussions/19747
if [[ -n "$WT_SESSION" ]]; then
    PROMPT_COMMAND="printf '\e[?117h'; ${PROMPT_COMMAND:-}"
    PS0=$'\033[?117l'
fi

# ── Prompt background streak fix (overflow + scroll) ─────────────────────
# Injects \e[K] before each \n in PS1 (erases overflow bg at end of line 1)
# and \e[49m\e[2K] after (resets bg and clears BCE-colored new line).
# \001..\002 wrap non-printing chars so bash doesn't miscalculate prompt width.
# Runs after Starship sets PS1 via PROMPT_COMMAND, so appended not prepended.
_fix_prompt_streak() {
    local rs=$'\001' re=$'\002' nl=$'\n' esc=$'\e'
    PS1="${PS1//$nl/${rs}${esc}[K${re}${nl}${rs}${esc}[49m${esc}[2K${re}}"
}
PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }_fix_prompt_streak"

# ── Cursor style: blinking beam for user, blinking underline for root ────
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    printf '\e[3 q'   # blinking underline for root
else
    printf '\e[5 q'   # blinking beam for user
fi
