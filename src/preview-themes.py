#!/usr/bin/env python3
"""
preview-themes.py — Render and display every theme/flavor.

Iterates every theme+flavor in palettes.json, renders a temporary starship.toml /
.dircolors / git/theme.conf, then shows the outputs in the terminal.

Default (no output flags): shows dircolors, git status, git diff, and starship prompt.
--include-nvim adds nvim on top of the active set (including the full default).
--nvim is selective: alone it shows only nvim; combined with others it adds nvim to those.

Usage:
  python3 /usr/local/share/dotfiles/src/preview-themes.py
  python3 /usr/local/share/dotfiles/src/preview-themes.py --theme catppuccin
  python3 /usr/local/share/dotfiles/src/preview-themes.py --starship-template pills
  python3 /usr/local/share/dotfiles/src/preview-themes.py --theme tokyonight --flavor storm

  # Restrict to one output
  python3 /usr/local/share/dotfiles/src/preview-themes.py --prompt
  python3 /usr/local/share/dotfiles/src/preview-themes.py --git-diff
  python3 /usr/local/share/dotfiles/src/preview-themes.py --git-status
  python3 /usr/local/share/dotfiles/src/preview-themes.py --dir-colors

  # --nvim: selective (shows only nvim, like --prompt shows only the prompt)
  python3 /usr/local/share/dotfiles/src/preview-themes.py --nvim
  python3 /usr/local/share/dotfiles/src/preview-themes.py --nvim --theme gruvbox --flavor light
  python3 /usr/local/share/dotfiles/src/preview-themes.py --nvim --prompt --theme catppuccin --flavor mocha

  # --include-nvim: additive (adds nvim to full default set or to selected outputs)
  python3 /usr/local/share/dotfiles/src/preview-themes.py --include-nvim
  python3 /usr/local/share/dotfiles/src/preview-themes.py --include-nvim --theme gruvbox --flavor light
  python3 /usr/local/share/dotfiles/src/preview-themes.py --include-nvim --prompt --theme catppuccin --flavor mocha

  # --prompt without --starship-template cycles ALL available templates
  python3 /usr/local/share/dotfiles/src/preview-themes.py --theme gruvbox --flavor dark --prompt
  # --prompt with --starship-template shows only that template
  python3 /usr/local/share/dotfiles/src/preview-themes.py --prompt --starship-template pills

  # Combine as needed
  python3 /usr/local/share/dotfiles/src/preview-themes.py --prompt --git-diff
  python3 /usr/local/share/dotfiles/src/preview-themes.py --theme gruvbox --git-diff --dir-colors

  # $status/$cmd_duration/$jobs/$shlvl are forced to render automatically —
  # starship only shows these when real shell state warrants it, so a bare
  # preview would never exercise them otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _check_pty() -> bool:
    try:
        import pty  # pragma: no cover

        return callable(getattr(pty, "spawn", None))  # pragma: no cover
    except ImportError:
        return False


_HAS_PTY: bool = _check_pty()


# ── PTY helper ────────────────────────────────────────────────────────────────


def _starship_via_pty(
    starship_toml: Path, width: int = 120, extra_args: list[str] | None = None
) -> None:  # pragma: no cover
    """Run starship in a PTY so it outputs ANSI colors; strip readline wrappers.

    Args:
        starship_toml: Path to the rendered starship config to preview.
        width: Terminal width to report to starship for layout purposes.
        extra_args: Additional CLI args forwarded to `starship prompt` verbatim
            (e.g. `["--status", "1"]`) — used to force conditional modules like
            `$status`/`$cmd_duration`/`$jobs`/`$shlvl` to render in the preview.
    """
    import pty as _pty  # pragma: no cover

    cmd = ["starship", "prompt", "--terminal-width", str(width), *(extra_args or [])]
    _set = {"STARSHIP_CONFIG": str(starship_toml), "COLORTERM": "truecolor"}
    _prev = {k: os.environ.get(k) for k in _set}
    os.environ.update(_set)
    try:

        def _read(fd: int) -> bytes:
            data = os.read(fd, 4096)
            data = data.replace(b"\\[", b"").replace(b"\\]", b"")
            data = data.replace(b"\r\n", b"\033[K\r\n")
            return data

        _pty.spawn(cmd, _read)  # type: ignore[attr-defined]
    except KeyboardInterrupt:
        raise
    finally:
        for k, v in _prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── Config helpers ────────────────────────────────────────────────────────────


def _find_cfg() -> Path:
    here = Path(__file__).parent
    for candidate in [here / ".config", Path.home() / ".config"]:
        if (candidate / "palettes.json").exists():
            return candidate
    sys.exit("palettes.json not found — run from the repo root or install first.")


def _active_starship_template() -> str:
    tmpl_file = Path.home() / ".config" / "dotfiles-starship-template"
    if tmpl_file.exists():
        t = tmpl_file.read_text(encoding="utf-8").strip()
        if t:
            return t
    return "powerline"


def _sep() -> str:
    return ""  # U+E0B0 powerline right-arrow


def _term_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 220


# ── Combo builder ─────────────────────────────────────────────────────────────


def _build_combos(
    pal_data: dict[str, Any],
    filter_theme: str = "",
    filter_flavor: str = "",
) -> list[tuple[str, str]]:
    """Return a sorted list of (theme, flavor) tuples to preview."""
    combos: list[tuple[str, str]] = []
    for theme, tdata in sorted(pal_data.items()):
        if theme.startswith("_") or (filter_theme and theme != filter_theme):
            continue
        for flavor in sorted(k for k in tdata if not k.startswith("_")):
            if filter_flavor and flavor != filter_flavor:
                continue
            fdata = tdata[flavor]
            if not any(not k.startswith("_") for k in fdata) and "_terminal_fallback" not in fdata:
                continue  # nvim-only, no terminal fallback
            combos.append((theme, flavor))
    return combos


# ── Section rendering ─────────────────────────────────────────────────────────


def _section_header(title: str, width: int = 40) -> None:
    sys.stdout.write(f"\033[2m{'─' * width}\033[0m\n")
    sys.stdout.write(f"\033[2m  {title}\033[0m\n")
    sys.stdout.flush()


def _combo_header(theme: str, flavor: str, width: int = 60) -> None:
    bar = "━" * width
    sys.stdout.write(f"\n\033[1;36m{bar}\033[0m\n")
    sys.stdout.write(f"\033[1;37m  {theme}  /  {flavor}\033[0m\n")
    sys.stdout.write(f"\033[1;36m{bar}\033[0m\n")
    sys.stdout.flush()


# ── git diff sample ───────────────────────────────────────────────────────────

_DIFF_BEFORE = """\
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def main() -> None:
    for i in range(10):
        print(f"fib({i}) = {fibonacci(i)}")
"""

_SAMPLE_PYTHON = """\
\"\"\"Color theme manager.\"\"\"
from __future__ import annotations

import json
import os
from typing import Optional

SUPPORTED = ["catppuccin", "gruvbox", "kanagawa", "monokai"]
VERSION = (2, 0, 0)


class ColorRole:
    \"\"\"Maps semantic names to palette hex colors.\"\"\"

    def __init__(self, name: str, hex_color: str, bold: bool = False) -> None:
        if not hex_color.startswith("#"):
            raise ValueError(f"Invalid hex: {hex_color!r}")
        self.name = name
        self.hex = hex_color
        self.bold = bold

    @property
    def rgb(self) -> tuple[int, int, int]:
        h = self.hex[1:]
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def is_dark(self) -> bool:
        r, g, b = self.rgb
        return (r * 299 + g * 587 + b * 114) // 1000 < 128


class Theme:
    \"\"\"Manages a collection of color roles.\"\"\"

    def __init__(self, name: str, flavor: str = "") -> None:
        self.name = name
        self.flavor = flavor
        self._roles: dict[str, ColorRole] = {}

    def add(self, role: str, color: str) -> None:
        self._roles[role] = ColorRole(role, color)

    def get(self, role: str) -> Optional[ColorRole]:
        return self._roles.get(role)

    @property
    def background(self) -> str:
        bg = self._roles.get("BG")
        return bg.hex if bg else "#1e1e2e"


def load_palette(path: os.PathLike) -> dict[str, "Theme"]:
    \"\"\"Load all themes from a JSON palette file.\"\"\"
    with open(path, encoding="utf-8") as f:
        data: dict = json.load(f)

    themes: dict[str, Theme] = {}
    for theme_name, tdata in data.items():
        if theme_name.startswith("_"):
            continue
        for flavor, fdata in tdata.items():
            if flavor.startswith("_"):
                continue
            t = Theme(theme_name, flavor)
            for role, val in fdata.items():
                if not role.startswith("_"):
                    t.add(role, str(val))
            themes[f"{theme_name}/{flavor}"] = t

    return themes


if __name__ == "__main__":
    import sys
    result = load_palette(sys.argv[1])
    for key, theme in sorted(result.items()):
        print(f"  {key:<30}  bg={theme.background}")
"""

# Embedded Lua script: runs inside nvim --headless, captures treesitter-highlighted
# buffer text as ANSI escape sequences, writes to NVIM_PREVIEW_OUTPUT env file.
_LUA_CAPTURE_SCRIPT = r"""
local outfile = os.getenv("NVIM_PREVIEW_OUTPUT")
if not outfile then vim.cmd("qa!") return end

local buf = vim.api.nvim_get_current_buf()
local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
local MAX = 50

vim.cmd("filetype detect")
local ft = vim.bo[buf].filetype
if ft == "" then ft = "python" end
vim.opt.termguicolors = true

local row_spans = {}
for i = 0, MAX do row_spans[i] = {} end

pcall(function()
  local parser = vim.treesitter.get_parser(buf, ft)
  local tree = parser:parse()[1]
  local root = tree:root()
  local ts_query = vim.treesitter and vim.treesitter.query
  local get_q = ts_query and (ts_query.get or ts_query.get_query)
  if not get_q then return end
  local query = get_q(ft, "highlights")
  if not query then return end

  for id, node in query:iter_captures(root, buf, 0, MAX) do
    local cap = query.captures[id]
    local r1, c1, r2, c2 = node:range()
    if r1 >= MAX then break end

    local fg, bold, italic
    for _, hname in ipairs({ "@" .. cap .. "." .. ft, "@" .. cap }) do
      local hl = vim.api.nvim_get_hl(0, { name = hname, link = false })
      if hl.fg then
        fg, bold, italic = hl.fg, hl.bold, hl.italic
        break
      end
    end
    if not fg then goto skip end

    if r1 == r2 then
      table.insert(row_spans[r1], { cs = c1, ce = c2, fg = fg, bold = bold, italic = italic })
    else
      for row = r1, math.min(r2, MAX - 1) do
        local len = #(lines[row + 1] or "")
        local cs = (row == r1) and c1 or 0
        local ce = (row == r2) and c2 or len
        table.insert(row_spans[row], { cs = cs, ce = ce, fg = fg, bold = bold, italic = italic })
      end
    end
    ::skip::
  end
end)

local norm = vim.api.nvim_get_hl(0, { name = "Normal", link = false })

local function ansi_fg(c)
  return string.format("\27[38;2;%d;%d;%dm",
    math.floor(c / 65536) % 256, math.floor(c / 256) % 256, c % 256)
end
local function ansi_bg(c)
  return string.format("\27[48;2;%d;%d;%dm",
    math.floor(c / 65536) % 256, math.floor(c / 256) % 256, c % 256)
end

local BG = norm.bg and ansi_bg(norm.bg) or ""
local FG = norm.fg and ansi_fg(norm.fg) or ""
local R  = "\27[0m"

local f = io.open(outfile, "w")
if not f then vim.cmd("qa!") return end

for row = 0, math.min(#lines - 1, MAX - 1) do
  local line = lines[row + 1]
  local spans = row_spans[row]

  table.sort(spans, function(a, b)
    if a.cs ~= b.cs then return a.cs < b.cs end
    return (a.ce - a.cs) > (b.ce - b.cs)
  end)

  local merged, pe = {}, 0
  for _, s in ipairs(spans) do
    if s.cs >= pe then merged[#merged + 1] = s; pe = s.ce end
  end

  f:write(BG .. FG)
  local col, si = 0, 1
  while col < #line do
    while si <= #merged and merged[si].ce <= col do si = si + 1 end
    local s = (si <= #merged and merged[si].cs <= col) and merged[si] or nil
    if s then
      local ec = math.min(s.ce, #line)
      local esc = ansi_fg(s.fg)
      if s.bold   then esc = esc .. "\27[1m" end
      if s.italic then esc = esc .. "\27[3m" end
      f:write(esc .. line:sub(col + 1, ec) .. R .. BG .. FG)
      col = ec
      si  = si + 1
    else
      local nxt = (#merged >= si and merged[si] and merged[si].cs < #line)
                  and merged[si].cs or #line
      f:write(line:sub(col + 1, nxt))
      col = nxt
    end
  end
  -- Fill remainder of line with theme background (BG + \e[K erases to EOL)
  if BG ~= "" then f:write(BG .. "\27[K") end
  f:write(R .. "\n")
end

f:close()
vim.cmd("qa!")
"""

_DIFF_AFTER = """\
from functools import lru_cache


@lru_cache(maxsize=None)
def fibonacci(n: int) -> int:
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def fibonacci_sequence(limit: int) -> list[int]:
    return [fibonacci(i) for i in range(limit)]


def main() -> None:
    seq = fibonacci_sequence(10)
    for i, val in enumerate(seq):
        print(f"fib({i:2d}) = {val}")
"""


def _show_git_diff(git_theme_conf: Path, tmp: Path) -> None:  # pragma: no cover
    """Create a temp git repo and show a sample Python diff via delta."""
    repo = tmp / "_diff_repo"
    gitconfig = tmp / "_gitconfig"
    cols = _term_width()
    q: dict[str, Any] = {"capture_output": True, "check": False}

    try:
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir()
        sample = repo / "sample.py"

        subprocess.run(["git", "init", "--quiet", str(repo)], **q)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "x@x.com"], **q)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "x"], **q)

        sample.write_text(_DIFF_BEFORE, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "sample.py"], **q)
        subprocess.run(["git", "-C", str(repo), "commit", "--quiet", "-m", "init"], **q)

        sample.write_text(_DIFF_AFTER, encoding="utf-8")

        gitconfig.write_text(
            "[core]\n"
            "    pager = delta\n"
            "[delta]\n"
            "    side-by-side = true\n"
            "    line-numbers = true\n"
            "    features = theme-colors\n"
            f"    width = {cols}\n"
            "[include]\n"
            f"    path = {git_theme_conf}\n",
            encoding="utf-8",
        )

        subprocess.run(
            ["git", "-C", str(repo), "diff"],
            env={**os.environ, "GIT_CONFIG_GLOBAL": str(gitconfig), "COLUMNS": str(cols)},
            check=False,
        )
    except FileNotFoundError:
        sys.stdout.write("  [git or delta not found — skipping]\n")


# ── dircolors sample ──────────────────────────────────────────────────────────

# One representative per dircolors category
_LS_FILES: list[tuple[str, int | None]] = [
    # source code
    ("main.py", None),
    ("main.go", None),
    ("main.rs", None),
    ("main.ts", None),
    ("Main.java", None),
    ("main.cpp", None),
    ("script.lua", None),
    ("app.zig", None),
    ("notebook.ipynb", None),
    # text / config
    ("README.md", None),
    ("config.yaml", None),
    ("settings.toml", None),
    (".gitignore", None),
    ("Dockerfile", None),
    # env (bold archive colour — caution signal)
    (".env", None),
    # images
    ("photo.png", None),
    ("banner.jpg", None),
    ("icon.svg", None),
    # media
    ("video.mp4", None),
    ("audio.mp3", None),
    ("podcast.flac", None),
    # archives
    ("backup.zip", None),
    ("source.tar.gz", None),
    ("package.deb", None),
    ("dist.whl", None),
    # documents
    ("report.pdf", None),
    ("slides.pptx", None),
    ("ebook.epub", None),
    # executables
    ("run.sh", 0o755),
    ("build.py", 0o755),
    # build artifacts / dimmed
    ("build.pyc", None),
    ("debug.log", None),
    ("module.so", None),
    # data
    ("data.csv", None),
    ("model.parquet", None),
    # keys / certs
    ("server.pem", None),
]


def _show_dir_colors(dircolors_file: Path, tmp: Path) -> None:  # pragma: no cover
    """Show a sample ls -lhA listing with the rendered dircolors applied."""
    ls_dir = tmp / "_ls_sample"
    try:
        if ls_dir.exists():
            shutil.rmtree(ls_dir)
        ls_dir.mkdir()

        # Subdirectories
        (ls_dir / "src").mkdir()
        (ls_dir / "tests").mkdir()
        (ls_dir / ".venv").mkdir()

        # Symlink (best-effort — requires elevated privileges on Windows)
        try:
            link = ls_dir / "link.md"
            link.symlink_to("README.md")
        except OSError:
            pass

        # Files
        for name, mode in _LS_FILES:
            p = ls_dir / name
            p.touch()
            if mode is not None:
                p.chmod(mode)

        # Resolve LS_COLORS from the rendered dircolors file
        dc_result = subprocess.run(
            ["dircolors", str(dircolors_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        ls_colors = ""
        if dc_result.returncode == 0:
            m = re.search(r"LS_COLORS='([^']*)'", dc_result.stdout)
            if m:
                ls_colors = m.group(1)

        ls_env = {**os.environ}
        if ls_colors:
            ls_env["LS_COLORS"] = ls_colors

        subprocess.run(
            ["ls", "--color=always", "-lhA", "--group-directories-first", str(ls_dir)],
            env=ls_env,
            check=False,
        )
    except FileNotFoundError:
        sys.stdout.write("  [ls or dircolors not found — skipping]\n")


# ── nvim theme preview ────────────────────────────────────────────────────────


def _find_nvim_init() -> Path | None:
    """Return path to the installed nvim init.lua, or None if not found."""
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        candidate = Path(local_app) / "nvim" / "init.lua" if local_app else None
    else:
        candidate = Path.home() / ".config" / "nvim" / "init.lua"
    return candidate if candidate and candidate.exists() else None


def _write_nvim_theme_lua(theme_data: dict[str, Any], flavor: str, out: Path) -> None:
    """Write a minimal theme.lua for nvim to pick up the right colorscheme."""
    nv: dict[str, str] = theme_data.get("_nvim", {})
    theme_name = nv.get("theme", "")
    variant_key = nv.get("variant_key", "")
    content = f'vim.g.active_theme = "{theme_name}"\n'
    if variant_key and flavor:
        content += f'vim.g.{variant_key} = "{flavor}"\n'
    out.write_text(content, encoding="utf-8")


def _show_nvim_theme(  # pragma: no cover
    flavor: str, theme_data: dict[str, Any], tmp: Path
) -> None:
    """Run nvim headlessly and print ANSI syntax-highlighted sample Python code."""
    if not shutil.which("nvim"):
        sys.stdout.write("  [nvim not found — skipping]\n")
        return

    init_lua = _find_nvim_init()
    if not init_lua:
        sys.stdout.write("  [~/.config/nvim/init.lua not found — install dotfiles first]\n")
        return

    nv_info: dict[str, str] = theme_data.get("_nvim", {})
    if not nv_info.get("theme"):
        sys.stdout.write("  [no _nvim config for this theme — skipping]\n")
        return

    # Build a temp XDG_CONFIG_HOME/nvim with our theme.lua
    # stdpath("config") inside nvim resolves via XDG_CONFIG_HOME, so the real
    # init.lua (copied here) reads the right theme.lua without touching the live one.
    nvim_cfg = tmp / "nvimxdg" / "nvim"
    nvim_cfg.mkdir(parents=True, exist_ok=True)
    shutil.copy(init_lua, nvim_cfg / "init.lua")
    _write_nvim_theme_lua(theme_data, flavor, nvim_cfg / "theme.lua")

    sample_py = tmp / "_sample.py"
    sample_py.write_text(_SAMPLE_PYTHON, encoding="utf-8")

    capture_lua = tmp / "_capture.lua"
    capture_lua.write_text(_LUA_CAPTURE_SCRIPT, encoding="utf-8")

    output_file = tmp / "_nvim_out.txt"

    env = {
        **os.environ,
        "XDG_CONFIG_HOME": str(tmp / "nvimxdg"),
        "NVIM_PREVIEW_OUTPUT": str(output_file),
        "COLORTERM": "truecolor",
    }

    try:
        subprocess.run(
            ["nvim", "--headless", str(sample_py), "-c", f"luafile {capture_lua}"],
            env=env,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        sys.stdout.write("  [nvim timed out — skipping]\n")
        return
    except FileNotFoundError:
        sys.stdout.write("  [nvim not found — skipping]\n")
        return

    if output_file.exists():
        content = output_file.read_text(encoding="utf-8", errors="replace")
        if content.strip():
            sys.stdout.write(content)
            sys.stdout.flush()
        else:
            sys.stdout.write("  [nvim: no output — theme plugin may not be installed]\n")
    else:
        sys.stdout.write("  [nvim: output file not created — check theme setup]\n")


# ── git status preview ────────────────────────────────────────────────────────


def _show_git_status(git_theme_conf: Path, tmp: Path) -> None:  # pragma: no cover
    """Create a temp git repo and show a sample themed git status."""
    repo = tmp / "_status_repo"
    gitconfig = tmp / "_status_gitconfig"

    try:
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir()

        q: dict[str, Any] = {"capture_output": True, "check": False}
        subprocess.run(["git", "init", "--quiet", str(repo)], **q)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "x@x.com"], **q)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "x"], **q)

        # Initial commit so we have a branch
        (repo / "README.md").write_text("# Project\n", encoding="utf-8")
        (repo / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
        (repo / "utils.py").write_text("def helper():\n    return None\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], **q)
        subprocess.run(["git", "-C", str(repo), "commit", "--quiet", "-m", "init"], **q)

        # Staged: new file + modified file
        (repo / "new_feature.py").write_text("class Feature:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "new_feature.py"], **q)
        (repo / "main.py").write_text("def main():\n    print('hello')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "main.py"], **q)

        # Unstaged: modified file
        (repo / "utils.py").write_text("def helper():\n    return True\n", encoding="utf-8")

        # Untracked files
        (repo / "debug.log").write_text("debug output\n", encoding="utf-8")
        (repo / ".env").write_text("SECRET=changeme\n", encoding="utf-8")

        gitconfig.write_text(
            f"[color]\n    ui = always\n[include]\n    path = {git_theme_conf}\n",
            encoding="utf-8",
        )

        subprocess.run(
            ["git", "-C", str(repo), "status"],
            env={**os.environ, "GIT_CONFIG_GLOBAL": str(gitconfig)},
            check=False,
        )
    except FileNotFoundError:
        sys.stdout.write("  [git not found — skipping]\n")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview every theme/flavor. "
            "Default (no output flags): shows starship prompt, git diff, git status, and dircolors. "
            "Pass one or more flags to restrict which outputs are shown. "
            "Use --include-nvim to also run the nvim syntax preview for every combo (opt-in, slow)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Theme / starship-template selection
    parser.add_argument(
        "--starship-template",
        "-T",
        default="",
        help="Starship template name to render (default: active saved template)",
    )
    parser.add_argument("--theme", "-t", default="", help="Limit to one theme (e.g. catppuccin)")
    parser.add_argument("--flavor", "-f", default="", help="Limit to one flavor within --theme")

    # Output selection — default (none set) means show all except nvim
    parser.add_argument("--prompt", action="store_true", help="Show starship prompt output")
    parser.add_argument("--git-diff", action="store_true", help="Show git diff output via delta")
    parser.add_argument("--git-status", action="store_true", help="Show git status output")
    parser.add_argument("--dir-colors", action="store_true", help="Show dircolors ls listing")
    parser.add_argument(
        "--nvim",
        action="store_true",
        help="Show nvim syntax preview only (selective — like --prompt shows only the prompt)",
    )
    parser.add_argument(
        "--include-nvim",
        action="store_true",
        help="Add nvim syntax preview on top of whatever is shown, including the full default set",
    )

    args = parser.parse_args()

    # Conditional-module forcing — forwarded verbatim to `starship prompt`.
    # Without these, $status/$cmd_duration/$jobs/$shlvl never render in a preview
    # since starship only shows them when real shell state (a failing command, a
    # slow command, background jobs, deep nesting) actually warrants it. Hardcoded
    # rather than exposed as flags — every preview should show them by default.
    # cmd_duration must exceed starship's default min_time (2000ms) or it's suppressed.
    prompt_extra_args: list[str] = [
        "--status",
        "1",
        "--cmd-duration",
        "2500",
        "--jobs",
        "2",
        "--shlvl",
        "5",
    ]

    # --nvim is selective (like --prompt): alone it shows only nvim.
    # --include-nvim is additive: adds nvim to whatever is active, including defaults.
    any_output_flag = (
        args.prompt or args.git_diff or args.git_status or args.dir_colors or args.nvim
    )
    show_prompt = args.prompt or not any_output_flag
    show_git_diff = args.git_diff or not any_output_flag
    show_git_status = args.git_status or not any_output_flag
    show_dir_colors = args.dir_colors or not any_output_flag
    show_nvim = args.nvim or args.include_nvim

    cfg = _find_cfg()
    renderer = cfg / "render-theme.py"
    palettes = cfg / "palettes.json"
    dircolors_tmpl = cfg / "dircolors-template"
    git_color_tmpl = cfg / "gitcolors-template"

    # When --prompt is used without --starship-template, cycle all templates.
    # Otherwise use the specified/active template only.
    cycle_templates = show_prompt and not args.starship_template
    if cycle_templates:
        starship_tmpls: list[Path] = sorted((cfg / "starship").glob("*.toml"))
        if not starship_tmpls:
            sys.exit(f"No starship templates found in {cfg / 'starship'}")
    else:
        starship_tmpl_name: str = args.starship_template or _active_starship_template()
        starship_tmpl_file = cfg / "starship" / f"{starship_tmpl_name}.toml"
        if not starship_tmpl_file.exists():
            sys.exit(f"Starship template not found: {starship_tmpl_file}")
        starship_tmpls = [starship_tmpl_file]

    with open(palettes, encoding="utf-8-sig") as f:
        pal_data: dict[str, Any] = json.load(f)

    combos = _build_combos(pal_data, args.theme, args.flavor)
    if not combos:
        msg = "No matching theme/flavor combinations found."
        if args.theme and args.flavor:
            tdata = pal_data.get(args.theme, {})
            fdata = tdata.get(args.flavor)
            if fdata is not None and not any(not k.startswith("_") for k in fdata):
                msg = (
                    f"{args.theme}/{args.flavor} exists but has no terminal colors "
                    f"(nvim-only). Use get-colors.py --show --theme {args.theme} "
                    f"--flavor {args.flavor} for details."
                )
            elif args.theme not in pal_data:
                msg = f"Unknown theme '{args.theme}'. Available: {', '.join(sorted(k for k in pal_data if not k.startswith('_')))}."
            elif fdata is None:
                available = sorted(k for k in tdata if not k.startswith("_"))
                msg = f"Unknown flavor '{args.flavor}' for theme '{args.theme}'. Available: {', '.join(available)}."
        sys.exit(msg)

    sep = _sep()
    cols = _term_width()

    if cycle_templates:
        print(f"Cycling {len(starship_tmpls)} prompt templates  ×  {len(combos)} combinations\n")
    else:
        print(f"Starship template: {starship_tmpls[0].stem}    ({len(combos)} combinations)\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        starship_out = tmp_path / "starship.toml"
        dircolors_out = tmp_path / ".dircolors"
        git_theme_out = tmp_path / "theme.conf"

        try:
            for theme, flavor in combos:
                label = f"{theme}/{flavor}"
                fdata = pal_data.get(theme, {}).get(flavor, {})
                terminal_fallback = (
                    fdata.get("_terminal_fallback", "")
                    if not any(not k.startswith("_") for k in fdata)
                    else ""
                )

                _combo_header(theme, flavor, width=min(cols, 80))
                if terminal_fallback:
                    sys.stdout.write(
                        f"\033[33m  no terminal colors — showing {theme}/{terminal_fallback}\033[0m\n\n"
                    )
                    sys.stdout.flush()

                first_render_ok = False
                for tmpl in starship_tmpls:
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(renderer),
                            "apply",
                            "--palette",
                            str(palettes),
                            "--theme",
                            theme,
                            "--flavor",
                            flavor,
                            "--sep",
                            sep,
                            "--starship-template",
                            str(tmpl),
                            "--starship-output",
                            str(starship_out),
                            "--dircolors-template",
                            str(dircolors_tmpl),
                            "--dircolors-output",
                            str(dircolors_out),
                            "--git-template",
                            str(git_color_tmpl),
                            "--git-output",
                            str(git_theme_out),
                        ],
                        capture_output=True,
                    )

                    if result.returncode != 0:
                        if not first_render_ok:
                            sys.stdout.write(f"\033[2m{label}\033[0m  [render failed]\n")
                            break
                        sys.stdout.write(f"  [{tmpl.stem}: render failed]\n")
                        continue

                    # Show dircolors / git status / git diff once per combo —
                    # they don't depend on the starship template.
                    if not first_render_ok:
                        first_render_ok = True
                        if show_dir_colors:
                            _section_header("dircolors  (ls -lhA)")
                            _show_dir_colors(dircolors_out, tmp_path)
                            sys.stdout.write("\033[0m\n")
                            sys.stdout.flush()
                        if show_git_status:
                            _section_header("git status")
                            _show_git_status(git_theme_out, tmp_path)
                            sys.stdout.write("\033[0m\n")
                            sys.stdout.flush()
                        if show_git_diff:
                            _section_header("git diff  (sample.py)")
                            _show_git_diff(git_theme_out, tmp_path)
                            sys.stdout.write("\033[0m\n")
                            sys.stdout.flush()

                    if show_prompt:
                        hdr = (
                            f"starship prompt  [{tmpl.stem}]"
                            if cycle_templates
                            else "starship prompt"
                        )
                        _section_header(hdr)
                        if _HAS_PTY:
                            _starship_via_pty(
                                starship_out, width=cols, extra_args=prompt_extra_args
                            )
                        else:
                            subprocess.run(
                                [
                                    "starship",
                                    "prompt",
                                    "--terminal-width",
                                    str(cols),
                                    *prompt_extra_args,
                                ],
                                env={
                                    **os.environ,
                                    "STARSHIP_CONFIG": str(starship_out),
                                    "COLORTERM": "truecolor",
                                },
                            )
                        sys.stdout.write("\n")
                        sys.stdout.flush()

                # nvim is template-independent — shown once at the end of each combo
                if first_render_ok and show_nvim:
                    _section_header("nvim  (treesitter highlight)")
                    _show_nvim_theme(flavor, pal_data[theme], tmp_path)
                    sys.stdout.write("\033[0m\n")
                    sys.stdout.flush()

        except KeyboardInterrupt:
            sys.stdout.write("\n\033[0mInterrupted.\n")
            sys.exit(0)

    sys.stdout.write("\033[0m")
    sys.stdout.flush()
    print()


if __name__ == "__main__":
    main()
