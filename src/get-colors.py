#!/usr/bin/env python3
"""
get-colors.py — Color palette viewer and palette-JSON exporter for Neovim themes.

Reads directly from installed Neovim lazy plugin sources.

Actions (exactly one required):
  --show    Visual ANSI swatches from live plugin files
  --palette Print "name hex" pairs for scripting
  --matrix  Unified role matrix from palettes.json (no plugins needed)
  --export  (Re)generate palettes.json from live plugins

Options:
  --theme THEME     Theme name (for --show and --palette)
  --flavor FLAVOR   Flavor/variant (for --show and --palette)
  --prompt          With --matrix: show prompt roles only (SEG/FG/OK/ERR/WARN)
  --colors          With --matrix: show dircolor/git roles only (DC_*/GC_*)
  --output PATH     With --export: output path (default: next to roles.json)
  --blend           With --export: reshade duplicate accents per flavor (see below)
  --palettes PATH   With --matrix: path to palettes.json (auto-detected)
  --roles PATH      With --export: path to roles.json (auto-detected)
  --themes-dir PATH Neovim lazy plugins dir (default: ~/.local/share/nvim/lazy)

Environment:
  SHOW_COLORS_THEMES_DIR   Override lazy plugins dir

Examples:
  python3 /usr/local/share/dotfiles/src/get-colors.py --show
  python3 /usr/local/share/dotfiles/src/get-colors.py --show --theme kanagawa
  python3 /usr/local/share/dotfiles/src/get-colors.py --show --theme catppuccin --flavor mocha
  python3 /usr/local/share/dotfiles/src/get-colors.py --palette --theme gruvbox --flavor dark
  python3 /usr/local/share/dotfiles/src/get-colors.py --matrix
  python3 /usr/local/share/dotfiles/src/get-colors.py --matrix --prompt
  python3 /usr/local/share/dotfiles/src/get-colors.py --matrix --colors
  python3 /usr/local/share/dotfiles/src/get-colors.py --matrix --theme catppuccin
  python3 /usr/local/share/dotfiles/src/get-colors.py --matrix --theme catppuccin --flavor mocha
  python3 /usr/local/share/dotfiles/src/get-colors.py --matrix --theme catppuccin --flavor mocha --prompt
  python3 /usr/local/share/dotfiles/src/get-colors.py --export
  python3 /usr/local/share/dotfiles/src/get-colors.py --export --blend
  python3 /usr/local/share/dotfiles/src/get-colors.py --export --output /tmp/palettes-preview.json
"""

from __future__ import annotations

import argparse
import colorsys
import contextlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from typing import Any, cast

logger = logging.getLogger("get-colors")


def _default_themes_dir() -> str:
    if env := os.environ.get("SHOW_COLORS_THEMES_DIR"):
        return env
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(local_app_data, "nvim-data", "lazy")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "nvim", "lazy")


_DEFAULT_THEMES_DIR = _default_themes_dir()

KNOWN_THEMES = [
    "catppuccin",
    "gruvbox",
    "kanagawa",
    "monokai",
    "bearded",
    "tokyonight",
    "flexoki",
    "bamboo",
    "oasis",
    "onedarkpro",
]


# ── Logging ────────────────────────────────────────────────────────────────────


class _ColorFormatter(logging.Formatter):
    _COLORS = {
        logging.DEBUG: "\033[2m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelno, "")
        return f"{color}{super().format(record)}{self._RESET}" if color else super().format(record)


def _setup_logging(verbose: bool = False) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_ColorFormatter("%(levelname)s: %(message)s"))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=[handler])


# ── Terminal display helpers ───────────────────────────────────────────────────


def _show_swatch(name: str, hex_color: str) -> None:
    h = hex_color.lstrip("#").upper()
    if len(h) != 6:
        return
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    fg = 0 if (r * 299 + g * 587 + b * 114) // 1000 > 128 else 7
    print(f"\033[48;2;{r};{g};{b}m\033[3{fg}m {name:<30} \033[0m  {hex_color}")


def _section(title: str) -> None:
    bar = "━" * 68
    print(f"\n{bar}\n  \U0001f3a8  {title}\n{bar}")


def _flavor_header(title: str) -> None:
    print(f"\n  \U0001f4cc  {title}\n")


def _print_header() -> None:
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + "              NEOVIM THEME COLOR PALETTE VIEWER                    " + "║")
    print("╚" + "═" * 68 + "╝")


# ── Safe file reader ───────────────────────────────────────────────────────────


def _read_file(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        logger.warning(f"Cannot read {path}: {e}")
        return None


# ── Palette extraction helpers ─────────────────────────────────────────────────


def _pal_pairs(
    file_path: str, prefix: str | None = None, strip: str | None = None
) -> list[tuple[str, str]]:
    content = _read_file(file_path)
    if content is None:
        return []
    results: list[tuple[str, str]] = []
    for m in re.finditer(r'([a-zA-Z][a-zA-Z0-9_]+)\s*=\s*"(#[A-Fa-f0-9]{6})"', content):
        name, hex_color = m.group(1), m.group(2)
        line_start = content.rfind("\n", 0, m.start()) + 1
        if "--" in content[line_start : m.start()]:
            continue
        if prefix and not name.lower().startswith(prefix.lower()):
            continue
        display = name
        if strip and name.lower().startswith(strip.lower()):
            tail = name[len(strip) :]
            display = (tail[0].lower() + tail[1:]) if tail else tail
        results.append((display, hex_color))
    return sorted(results)


def _pal_pairs_exclude(file_path: str, *exclude_prefixes: str) -> list[tuple[str, str]]:
    content = _read_file(file_path)
    if content is None:
        return []
    results: list[tuple[str, str]] = []
    for m in re.finditer(r'([a-zA-Z][a-zA-Z0-9_]+)\s*=\s*"(#[A-Fa-f0-9]{6})"', content):
        name, hex_color = m.group(1), m.group(2)
        line_start = content.rfind("\n", 0, m.start()) + 1
        if "--" in content[line_start : m.start()]:
            continue
        if any(name.lower().startswith(ex.lower()) for ex in exclude_prefixes):
            continue
        results.append((name, hex_color))
    return sorted(results)


def _extract_tokyonight_night(themes_dir: str) -> list[tuple[str, str]]:
    tn = os.path.join(themes_dir, "tokyonight.nvim/lua/tokyonight/colors")

    def _pairs_from(path: str) -> dict[str, str]:
        content = _read_file(path) or ""
        return {
            m.group(1): m.group(2) for m in re.finditer(r'(\w+)\s*=\s*"(#[A-Fa-f0-9]{6})"', content)
        }

    base = _pairs_from(os.path.join(tn, "storm.lua"))
    base.update(_pairs_from(os.path.join(tn, "night.lua")))
    return sorted(base.items())


def _extract_flexoki_variant(themes_dir: str, variant: str) -> list[tuple[str, str]]:
    path = os.path.join(themes_dir, "flexoki/lua/flexoki/palette.lua")
    content = _read_file(path)
    if not content:
        return []
    base = {
        m.group(1): m.group(2)
        for m in re.finditer(r"\['([^']+)'\]\s*=\s*'(#[A-Fa-f0-9]{6})'", content)
    }
    vm = re.search(r"\b" + re.escape(variant) + r"\s*=\s*\{(.+?)\n\t\}", content, re.DOTALL)
    if not vm:
        return []
    return [
        (m.group(1), base[m.group(2)])
        for m in re.finditer(r"\['([^']+)'\]\s*=\s*base_colors\['([^']+)'\]", vm.group(1))
        if m.group(2) in base
    ]


def _extract_bamboo_flavor(themes_dir: str, flavor: str) -> list[tuple[str, str]]:
    path = os.path.join(themes_dir, "bamboo.nvim/lua/bamboo/palette.lua")
    content = _read_file(path)
    if not content:
        return []
    m = re.search(r"\b" + re.escape(flavor) + r"\s*=\s*\{", content)
    if not m:
        return []
    start = m.end() - 1
    depth = 0
    block = ""
    for i in range(start, len(content)):
        c = content[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                block = content[start : i + 1]
                break
    return sorted(
        (m.group(1), m.group(2))
        for m in re.finditer(r'(\w+)\s*=\s*[\'"]?(#[A-Fa-f0-9]{6})[\'"]?', block)
    )


def _extract_oasis_flavor(themes_dir: str, flavor: str) -> list[tuple[str, str]]:
    path = os.path.join(themes_dir, "oasis.nvim/lua/oasis/palette.lua")
    content = _read_file(path)
    if not content:
        return []
    results: dict[str, str] = {}

    # Extract bg.core / fg.core for this specific flavor from the theme table
    theme_start = content.find("local theme = {")
    if theme_start >= 0:
        theme_section = content[theme_start:]
        flavor_m = re.search(r"\b" + re.escape(flavor) + r"\s*=\s*\{", theme_section)
        if flavor_m:
            start = flavor_m.end() - 1
            depth = 0
            pos = start
            while pos < len(theme_section):
                if theme_section[pos] == "{":
                    depth += 1
                elif theme_section[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                pos += 1
            block = theme_section[start : pos + 1]
            bg_m = re.search(r'bg\s*=\s*\{[^}]*core\s*=\s*"(#[A-Fa-f0-9]{6})"', block)
            fg_m = re.search(r'fg\s*=\s*\{[^}]*core\s*=\s*"(#[A-Fa-f0-9]{6})"', block)
            if bg_m:
                results["bg"] = bg_m.group(1)
            if fg_m:
                results["fg"] = fg_m.group(1)

    # Extract [500] level from each named color scale in the colors section
    _OASIS_SKIP = {
        "terminal",
        "light_terminal",
        "visual",
        "diag",
        "diff",
        "git",
        "theme",
        "colors",
        "semantic_ansi_map",
    }
    colors_start = content.find("local colors = {")
    if colors_start >= 0:
        colors_section = content[colors_start:]
        for name_m in re.finditer(r"^  (\w+)\s*=\s*\{", colors_section, re.MULTILINE):
            name = name_m.group(1)
            if name in _OASIS_SKIP:
                continue
            start = name_m.end() - 1
            depth = 0
            pos = start
            while pos < len(colors_section):
                if colors_section[pos] == "{":
                    depth += 1
                elif colors_section[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                pos += 1
            block = colors_section[start : pos + 1]
            scale_m = re.search(r'\[500\]\s*=\s*"(#[A-Fa-f0-9]{6})"', block)
            if scale_m:
                results[name] = scale_m.group(1)

    return sorted(results.items())


def _extract_onedarkpro_style(themes_dir: str, style: str) -> list[tuple[str, str]]:
    path = os.path.join(themes_dir, f"onedarkpro.nvim/lua/onedarkpro/themes/{style}.lua")
    content = _read_file(path)
    if not content:
        return []
    m = re.search(r"local default_colors\s*=\s*\{", content)
    if not m:
        return []
    start = m.end() - 1
    depth = 0
    block = ""
    for i in range(start, len(content)):
        c = content[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                block = content[start : i + 1]
                break
    return sorted(
        (m.group(1), m.group(2)) for m in re.finditer(r'(\w+)\s*=\s*"(#[A-Fa-f0-9]{6})"', block)
    )


def _extract_bearded_flavor(themes_dir: str, flavor: str) -> list[tuple[str, str]]:
    path = os.path.join(themes_dir, "bearded/lua/bearded/palettes/generated.lua")
    content = _read_file(path)
    if not content:
        return []
    m = re.search(r'\["' + re.escape(flavor) + r'"\]\s*=\s*\{', content)
    if not m:
        return []
    start = m.end() - 1
    depth = 0
    block = ""
    for i in range(start, len(content)):
        c = content[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                block = content[start : i + 1]
                break
    return [
        (m.group(1), m.group(2)) for m in re.finditer(r'(\w+)\s*=\s*"(#[A-Fa-f0-9]{6})"', block)
    ]


# ── Per-theme palette extraction ───────────────────────────────────────────────


def extract_palette(themes_dir: str, theme: str, flavor: str) -> list[tuple[str, str]]:
    td = themes_dir
    if theme == "catppuccin":
        return _pal_pairs(os.path.join(td, f"catppuccin/lua/catppuccin/palettes/{flavor}.lua"))
    if theme == "gruvbox":
        # Return the full palette for all variants so roles can reference any key
        # (dark0/light0 for bg/fg, bright_*/neutral_* for accents, etc.)
        gvb = os.path.join(td, "gruvbox.nvim/lua/gruvbox.lua")
        return _pal_pairs(gvb)
    if theme == "kanagawa":
        kan = os.path.join(td, "kanagawa.nvim/lua/kanagawa/colors.lua")
        if flavor == "wave":
            return _pal_pairs_exclude(kan, "dragon", "lotus")
        return _pal_pairs(kan, prefix=flavor, strip=flavor)
    if theme == "monokai":
        return _pal_pairs(
            os.path.join(td, f"monokai-pro.nvim/lua/monokai-pro/palette/{flavor}.lua")
        )
    if theme == "bearded":
        return _extract_bearded_flavor(td, flavor)
    if theme == "tokyonight":
        if flavor == "night":
            return _extract_tokyonight_night(td)
        return _pal_pairs(os.path.join(td, f"tokyonight.nvim/lua/tokyonight/colors/{flavor}.lua"))
    if theme == "flexoki":
        return _extract_flexoki_variant(td, flavor)
    if theme == "bamboo":
        return _extract_bamboo_flavor(td, flavor)
    if theme == "oasis":
        return _extract_oasis_flavor(td, flavor)
    if theme == "onedarkpro":
        return _extract_onedarkpro_style(td, flavor)
    logger.error(f"Unknown theme: {theme}")
    sys.exit(1)


# ── Show functions ─────────────────────────────────────────────────────────────


def _show_pairs(pairs: list[tuple[str, str]]) -> None:
    for name, hex_color in pairs:
        _show_swatch(name, hex_color)


def show_theme(themes_dir: str, theme: str, want_flavor: str | None = None) -> None:
    td = themes_dir
    if theme == "catppuccin":
        _section("CATPPUCCIN   (4 flavors: latte · frappe · macchiato · mocha)")
        for f in ["frappe", "latte", "macchiato", "mocha"]:
            if want_flavor and f != want_flavor:
                continue
            fp = os.path.join(td, f"catppuccin/lua/catppuccin/palettes/{f}.lua")
            _flavor_header(f.upper())
            pairs = _pal_pairs(fp)
            _show_pairs(pairs) if pairs else print(f"  ❌ {f} not found")

    elif theme == "gruvbox":
        _section("GRUVBOX   (dark · light · shared accents)")
        gvb = os.path.join(td, "gruvbox.nvim/lua/gruvbox.lua")
        if not os.path.exists(gvb):
            print("  ❌ Gruvbox not found")
            return
        for variant in ["dark", "light"]:
            if want_flavor and want_flavor != variant:
                continue
            _flavor_header(variant.upper())
            _show_pairs(_pal_pairs(gvb, prefix=variant, strip=variant + "_"))
        if not want_flavor or want_flavor in ("accents", "shared"):
            _flavor_header("SHARED ACCENTS  (neutral · bright · faded · gray)")
            _show_pairs(_pal_pairs_exclude(gvb, "dark", "light"))

    elif theme == "kanagawa":
        _section("KANAGAWA   (wave · dragon · lotus)")
        kan = os.path.join(td, "kanagawa.nvim/lua/kanagawa/colors.lua")
        if not os.path.exists(kan):
            print("  ❌ Kanagawa not found")
            return
        for variant in ["wave", "dragon", "lotus"]:
            if want_flavor and want_flavor != variant:
                continue
            _flavor_header(variant.upper())
            if variant == "wave":
                _show_pairs(_pal_pairs_exclude(kan, "dragon", "lotus"))
            else:
                _show_pairs(_pal_pairs(kan, prefix=variant, strip=variant))

    elif theme == "monokai":
        _section("MONOKAI PRO   (7 filters)")
        for f in ["classic", "light", "machine", "octagon", "pro", "ristretto", "spectrum"]:
            if want_flavor and f != want_flavor:
                continue
            fp = os.path.join(td, f"monokai-pro.nvim/lua/monokai-pro/palette/{f}.lua")
            _flavor_header(f.upper())
            pairs = _pal_pairs(fp)
            _show_pairs(pairs) if pairs else print(f"  ❌ {f} not found")

    elif theme == "bearded":
        bfile = os.path.join(td, "bearded/lua/bearded/palettes/generated.lua")
        content = _read_file(bfile)
        if not content:
            print("  ❌ Bearded not found")
            return
        all_flavors = sorted(re.findall(r'(?<=\[")[^"]+(?="\] = \{)', content))
        _section(f"BEARDED   ({len(all_flavors)} flavors)")
        for idx, f in enumerate(all_flavors, 1):
            if want_flavor and f != want_flavor:
                continue
            _flavor_header(f"{f.upper()}   [{idx}/{len(all_flavors)}]")
            _show_pairs(_extract_bearded_flavor(td, f))

    elif theme == "tokyonight":
        _section("TOKYO NIGHT   (storm · night · moon · day)")
        tn_dir = os.path.join(td, "tokyonight.nvim/lua/tokyonight/colors")
        if not os.path.isdir(tn_dir):
            print("  ❌ Tokyo Night not found")
            return
        for variant in ["storm", "night", "moon"]:
            if want_flavor and want_flavor != variant:
                continue
            label = "NIGHT  (storm base + bg overrides)" if variant == "night" else variant.upper()
            _flavor_header(label)
            if variant == "night":
                _show_pairs(_extract_tokyonight_night(td))
            else:
                _show_pairs(_pal_pairs(os.path.join(tn_dir, f"{variant}.lua")))
        if not want_flavor or want_flavor == "day":
            _flavor_header("DAY")
            print(
                "  (palette computed at runtime from inverted night — nvim-only, no terminal colors)"
            )

    elif theme == "flexoki":
        _section("FLEXOKI   (base · dark · light)")
        fp = os.path.join(td, "flexoki/lua/flexoki/palette.lua")
        if not os.path.exists(fp):
            print("  ❌ Flexoki not found")
            return
        if not want_flavor or want_flavor == "base":
            _flavor_header("BASE COLORS  (raw named palette)")
            content = _read_file(fp) or ""
            for m in re.finditer(r"\['([^']+)'\]\s*=\s*'(#[A-Fa-f0-9]{6})'", content):
                _show_swatch(m.group(1), m.group(2))
        for variant in ["dark", "light"]:
            if want_flavor and want_flavor != variant:
                continue
            _flavor_header(variant.upper())
            _show_pairs(_extract_flexoki_variant(td, variant))

    elif theme == "bamboo":
        _section("BAMBOO   (vulgaris · multiplex · light)")
        if not os.path.exists(os.path.join(td, "bamboo.nvim/lua/bamboo/palette.lua")):
            print("  ❌ Bamboo not found")
            return
        for f in ["vulgaris", "multiplex", "light"]:
            if want_flavor and f != want_flavor:
                continue
            _flavor_header(f.upper())
            _show_pairs(_extract_bamboo_flavor(td, f))

    elif theme == "oasis":
        _OASIS_FLAVORS = [
            "abyss",
            "cactus",
            "canyon",
            "desert",
            "dune",
            "lagoon",
            "luna",
            "midnight",
            "mirage",
            "moonlight",
            "night",
            "rose",
            "scorpion",
            "sol",
            "starlight",
            "twilight",
        ]
        _section(f"OASIS   ({len(_OASIS_FLAVORS)} flavors)")
        if not os.path.exists(os.path.join(td, "oasis.nvim/lua/oasis/palette.lua")):
            print("  ❌ Oasis not found")
            return
        for f in _OASIS_FLAVORS:
            if want_flavor and f != want_flavor:
                continue
            _flavor_header(f.upper())
            _show_pairs(_extract_oasis_flavor(td, f))

    elif theme == "onedarkpro":
        _section("ONEDARKPRO   (onedark · onelight · onedark_vivid · onedark_dark)")
        if not os.path.exists(
            os.path.join(td, "onedarkpro.nvim/lua/onedarkpro/themes/onedark.lua")
        ):
            print("  ❌ OneDarkPro not found")
            return
        for f in ["onedark", "onelight", "onedark_vivid", "onedark_dark"]:
            if want_flavor and f != want_flavor:
                continue
            _flavor_header(f.upper())
            _show_pairs(_extract_onedarkpro_style(td, f))


# ── Action handlers ────────────────────────────────────────────────────────────


def cmd_show(args: argparse.Namespace) -> None:
    _print_header()
    if not args.theme:
        for theme in KNOWN_THEMES:
            show_theme(args.themes_dir, theme)
        print("\n✅  Done!")
    else:
        show_theme(args.themes_dir, args.theme, args.flavor or None)


def cmd_palette(args: argparse.Namespace) -> None:
    if not args.theme:
        logger.error("--palette requires --theme THEME")
        sys.exit(1)
    if not args.flavor:
        logger.error("--palette requires --flavor FLAVOR")
        sys.exit(1)
    pairs = extract_palette(args.themes_dir, args.theme, args.flavor)
    for name, hex_color in pairs:
        print(f"{name} {hex_color}")


def cmd_matrix(args: argparse.Namespace) -> None:
    pal_f = args.palettes
    if not pal_f:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for candidate in [
            os.path.join(script_dir, ".config/palettes.json"),
            os.path.join(os.path.expanduser("~"), ".config/palettes.json"),
        ]:
            if os.path.exists(candidate):
                pal_f = candidate
                break
    if not pal_f:
        logger.error("palettes.json not found. Use --palettes PATH to specify.")
        sys.exit(1)

    try:
        with open(pal_f, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Cannot load {pal_f}: {e}")
        sys.exit(2)

    PROMPT_ROLES = [
        "SEG0",
        "SEG1",
        "SEG2",
        "SEG3",
        "SEG4",
        "SEG5",
        "BG",
        "TEXT",
        "FG",
        "OK",
        "ERR",
        "WARN",
    ]
    DC_ROLES = [
        "DC_DIR",
        "DC_LINK",
        "DC_EXEC",
        "DC_SOURCE",
        "DC_TEXT",
        "DC_IMAGE",
        "DC_MEDIA",
        "DC_ARCHIVE",
        "DC_DOC",
        "DC_DIMMED",
    ]
    GC_ROLES = [
        "GC_ADDED",
        "GC_CHANGED",
        "GC_UNTRACKED",
        "GC_BRANCH",
        "GC_REMOTE",
        "GC_TAG",
        "GC_OLD",
        "GC_NEW",
        "GC_META",
        "GC_FRAG",
    ]
    SWATCH_VIS = 10

    def swatch(h: str) -> str:
        if not h or len(h) != 7:
            return "\033[2m──\033[0m ·······"
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        return f"\033[38;2;{r};{g};{b}m██\033[0m {h}"

    filter_theme = args.theme or None
    filter_flavor = args.flavor or None
    rows = [
        (f"{theme}/{flavor}", _resolve_roles(data[theme], flavor))
        for theme in sorted(data)
        if not theme.startswith("_")
        if not filter_theme or theme == filter_theme
        for flavor in sorted(k for k in data[theme] if not k.startswith("_"))
        if not filter_flavor or flavor == filter_flavor
    ]

    def print_table(title: str, roles: list[str]) -> None:
        if not rows:
            return
        cw = max(max(len(r) for r in roles) + 1, SWATCH_VIS + 1)
        pad = cw - SWATCH_VIS
        fw = max(len(label) for label, _ in rows) + 1
        bar = "━" * (fw + (3 + cw) * len(roles))
        print(f"\n{bar}\n  {title}\n{bar}")
        print(f"  {'theme/flavor':<{fw}}" + "".join(f" │ {r:<{cw}}" for r in roles))
        print(f"  {'─' * fw}" + ("─┼─" + "─" * cw) * len(roles))
        for label, res in rows:
            row = f"{label:<{fw}}" + "".join(
                f" │ {swatch(res.get(r, ''))}{' ' * pad}" for r in roles
            )
            print(f"  {row}")
        print()

    show_prompt = args.prompt or (not args.prompt and not args.colors)
    show_colors = args.colors or (not args.prompt and not args.colors)
    if show_prompt:
        print_table("PROMPT ROLES  —  SEG0–SEG5  FG  OK  ERR  WARN", PROMPT_ROLES)
    if show_colors:
        print_table("DIRCOLORS ROLES  —  DC_*", DC_ROLES)
        print_table("GIT COLOR ROLES  —  GC_*", GC_ROLES)


def _resolve_roles(theme_data: dict[str, Any], flavor: str) -> dict[str, str]:
    """Resolve a flavor's SEG/FG/OK/ERR/WARN/BG/TEXT/DC_*/GC_* roles to hex values.

    Args:
        theme_data: The full per-theme dict from roles.json/palettes.json
            (contains flavor sub-dicts plus theme-level "_roles").
        flavor: The flavor key to resolve within theme_data.

    Returns:
        Dict of role name -> hex string (SEG0..SEG5, FG, OK, ERR, WARN, BG,
        TEXT, plus any DC_*/GC_* roles). Missing/unresolvable roles map to "".
    """
    fdata: dict[str, Any] = theme_data.get(flavor, {})
    roles_def: dict[str, Any] = _merge_roles(theme_data.get("_roles", {}), fdata.get("_roles"))
    palette: dict[str, str] = {k: v for k, v in fdata.items() if not k.startswith("_")}
    out: dict[str, str] = {}
    for i, name in enumerate(roles_def.get("SEG", [])):
        out[f"SEG{i}"] = palette.get(str(name), "")
    for rv in ("FG", "OK", "ERR", "WARN", "BG", "TEXT"):
        out[rv] = palette.get(str(roles_def.get(rv, "")), "")
    for k, role_name in roles_def.items():
        if k.startswith("DC_") or k.startswith("GC_"):
            out[k] = palette.get(str(role_name), "")
    return out


def _merge_roles(
    theme_roles: dict[str, Any], flavor_roles: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge a flavor's role overrides on top of its theme's defaults.

    Args:
        theme_roles: The theme-level `_roles` dict (may be empty).
        flavor_roles: The flavor's own `_roles` dict, or None if it has none.
            Keys present here win; any key it omits falls back to `theme_roles`.

    Returns:
        The merged roles dict. A flavor with no `_roles` at all yields the
        theme defaults unchanged.
    """
    return {**theme_roles, **(flavor_roles or {})}


def _validate_seg_roles(data: dict[str, Any]) -> list[str]:
    """Detect SEG-role drift between sibling flavors of the same theme.

    Sibling flavors are expected to differ only by *substituting* a color
    name at a given SEG index (the documented "identity anchor" pattern).
    A color name that reappears in a sibling's SEG array at a *different*
    index indicates the array was reordered by mistake, which silently
    reassigns which prompt segment (dir/git/lang/docker/time) gets which
    color.

    Args:
        data: The merged roles/palettes dict, keyed by theme then flavor.

    Returns:
        Human-readable error strings, one per detected drift. Empty if
        every theme's flavors are internally consistent.
    """
    errors: list[str] = []
    for theme, flavors in data.items():
        if theme.startswith("_") or not isinstance(flavors, dict):
            continue
        theme_default_roles: dict[str, Any] = flavors.get("_roles", {})
        segs: dict[str, list[str]] = {}
        for flavor, fdata in flavors.items():
            if flavor.startswith("_") or not isinstance(fdata, dict):
                continue
            roles_def: dict[str, Any] = _merge_roles(theme_default_roles, fdata.get("_roles"))
            seg = roles_def.get("SEG")
            if seg:
                segs[flavor] = list(seg)

        names = list(segs.keys())
        if len(names) < 2:
            continue
        base_name, base = names[0], segs[names[0]]
        for other_name in names[1:]:
            other = segs[other_name]
            if len(other) != len(base):
                errors.append(
                    f"{theme}: SEG length mismatch — {base_name} has {len(base)} "
                    f"entries, {other_name} has {len(other)}"
                )
                continue
            moved = [
                (value, i, other.index(value))
                for i, value in enumerate(base)
                if value in other and other.index(value) != i
            ]
            if moved:
                detail = ", ".join(f"'{v}' slot {i}→{j}" for v, i, j in moved)
                errors.append(f"{theme}: SEG drift between {base_name} and {other_name} — {detail}")
    return errors


# Target lightness range accents are mapped across, ranked by each flavor's
# own BG lightness relative to the theme's other flavors (not BG's absolute
# lightness — see _apply_accent_blend for why).
_ACCENT_LIGHTNESS_RANGE: tuple[float, float] = (0.35, 0.75)


_ACCENT_TRIGGER_KEY = "SEG0"


def _find_identical_accent_themes(result: dict[str, Any]) -> dict[str, list[str]]:
    """Detect, per theme, which flavors duplicate an earlier flavor's SEG0.

    Flavors are walked in sorted order per theme. The first flavor to use a
    given `_ACCENT_TRIGGER_KEY` (`SEG0`) hex is left as the "canonical"
    holder of that color; every later flavor that resolves the exact same
    SEG0 hex is flagged as a duplicate needing a shade of its own. This
    catches partial reuse *within* a theme (e.g. bearded's 11-flavor
    "arc"/"black-&-*" cluster all sharing one SEG0, even though bearded's
    other 52 flavors don't), not just themes where literally every flavor
    shares one accent set.

    This is detection-only (no mutation) — used for the `--export` warning
    when `--blend` isn't passed. It does NOT account for a duplicate's
    *blended* result coincidentally colliding with another flavor's original
    color, since nothing is actually blended here — see `_apply_accent_blend`,
    which redoes this same walk while actually mutating, updating its "seen"
    set with each blended result too so that kind of chain collision is
    still caught once blending is real.

    Args:
        result: The full palettes dict as written to palettes.json (theme ->
            flavor -> {color_name: hex, "_roles": {...}}) — i.e. `result`
            inside `cmd_export` after the extraction loop.

    Returns:
        Dict of theme name -> sorted list of its duplicate flavor names
        (the flavors that would need blending). Empty dict if none.
    """
    affected: dict[str, list[str]] = {}
    for theme, theme_data in result.items():
        if theme.startswith("_") or not isinstance(theme_data, dict):
            continue
        flavors = sorted(k for k in theme_data if not k.startswith("_"))
        if len(flavors) < 2:
            continue
        resolved = {flavor: _resolve_roles(theme_data, flavor) for flavor in flavors}
        seen: set[str] = set()
        duplicates: list[str] = []
        for flavor in flavors:
            seg0 = resolved[flavor].get(_ACCENT_TRIGGER_KEY, "")
            if not _validate_hex(seg0):
                continue
            if seg0 in seen:
                duplicates.append(flavor)
            else:
                seen.add(seg0)
        if duplicates:
            affected[theme] = duplicates
    return affected


def _apply_accent_blend(result: dict[str, Any]) -> dict[str, list[str]]:
    """Differentiate duplicate accent colors by shading each per flavor.

    Redoes `_find_identical_accent_themes`'s sequential per-theme walk, but
    for real this time: flavors are processed in sorted order, and the first
    flavor to use a given SEG0 hex is left untouched (the "canonical" holder
    of that color). Every later flavor resolving the same SEG0 — including
    one that only now collides because an *earlier* flavor's blend result
    happened to land on it — gets `SEG0-5`/`OK`/`ERR`/`WARN` reshaded. That
    chain case is exactly why detection and blending can't stay two fully
    separate passes: the "seen" set here is updated with each flavor's
    *actual* resulting color (blended or not), so a later duplicate is never
    missed just because it didn't collide with anything at the start.

    Status colors (`OK`/`ERR`/`WARN`) are safe to reshade alongside `SEG0-5`
    specifically because this only ever touches *lightness* — a status color
    keeps its recognizable hue (red stays red), just a lighter/darker shade
    per flavor, unlike an earlier hue-rotation approach that was rejected
    for visibly drifting colors across hue families.

    Each accent's hue and saturation are left exactly as-is (never mixed
    toward BG's own hue — a theme's blues must stay blue, not drift toward
    pink or purple) — only *lightness* changes, ranked by each flavor's own
    BG lightness *relative to the theme's other flavors*, not BG's absolute
    lightness. A theme like oasis has every BG clustered in a narrow
    near-black range, so a fixed weight-toward-BG's-own-lightness barely
    moves the needle; ranking within the theme's actual min/max spread and
    mapping that onto `_ACCENT_LIGHTNESS_RANGE` guarantees visible spread
    regardless of how tightly the underlying BGs cluster.

    `DC_*`/`GC_*` (dircolors/git-diff) roles are reshaded too, whenever they
    happen to reuse a name being blended for `SEG`/`OK`/`ERR`/`WARN` — e.g.
    monokai's `_roles` has `OK`/`DC_EXEC`/`GC_ADDED` all pointing at
    `accent4`. Without this, `OK` would show the new blended shade while
    `DC_EXEC`/`GC_ADDED` kept rendering the stale, still-duplicate color —
    the same flavor showing two different shades of what's meant to be one
    consistent accent. `blended_names` is the cache that makes this safe:
    a name is only ever blended once per flavor, so every role referencing
    it — SEG slot, OK/ERR/WARN, or a DC_/GC_ role — ends up pointing at the
    exact same new entry.

    For each duplicate flavor, writes new `{name}__blend` palette entries
    (never mutates the original color name in place — that name may be
    shared with a `DC_*`/`GC_*` role, e.g. a SEG slot's color could also
    back `DC_EXEC`; mutating it would leak the shade into dircolors/git-diff
    colors too) and points the flavor's `SEG`/`OK`/`ERR`/`WARN`/`DC_*`/`GC_*`
    roles at the new entries via a per-flavor `_roles` override.

    Every flavor considered (i.e. one with a valid `BG` and `SEG0`) also gets
    a `_blended` bool written directly onto its palette dict — `true` if it
    was reshaded, `false` if it was left as the canonical/untouched holder of
    its color. This makes the outcome inspectable straight from
    `palettes.json` without recomputing which flavors collided.

    Args:
        result: The full palettes dict, mutated in place.

    Returns:
        Dict of theme name -> sorted list of the flavor names actually
        blended (for logging — mirrors `_find_identical_accent_themes`'s
        shape, but reflects what really happened, including any chain
        collisions it couldn't have predicted).
    """
    blended: dict[str, list[str]] = {}
    for theme, theme_data in result.items():
        if theme.startswith("_") or not isinstance(theme_data, dict):
            continue
        flavors = sorted(k for k in theme_data if not k.startswith("_"))
        if len(flavors) < 2:
            continue

        bg_lightness: dict[str, float] = {}
        for flavor in flavors:
            bg_hex = _resolve_roles(theme_data, flavor).get("BG", "")
            if _validate_hex(bg_hex):
                bg_lightness[flavor] = _hex_lightness(bg_hex)
        if len(bg_lightness) < 2:
            continue
        lo, hi = min(bg_lightness.values()), max(bg_lightness.values())

        seen: set[str] = set()
        theme_blended: list[str] = []
        for flavor in flavors:
            if flavor not in bg_lightness:
                continue
            fdata = theme_data.get(flavor, {})
            seg0 = _resolve_roles(theme_data, flavor).get(_ACCENT_TRIGGER_KEY, "")
            if not _validate_hex(seg0):
                continue
            if seg0 not in seen:
                seen.add(seg0)
                fdata["_blended"] = False
                continue

            roles_def = _merge_roles(theme_data.get("_roles", {}), fdata.get("_roles"))
            normalized = 0.5 if hi == lo else (bg_lightness[flavor] - lo) / (hi - lo)

            override = dict(fdata.get("_roles") or {})
            blended_names: dict[str, str] = {}

            seg_names = [str(n) for n in roles_def.get("SEG", [])]
            override["SEG"] = [
                _blend_color_name(name, fdata, normalized, blended_names) for name in seg_names
            ]
            for rv in ("OK", "ERR", "WARN"):
                role_name = roles_def.get(rv)
                if role_name:
                    override[rv] = _blend_color_name(
                        str(role_name), fdata, normalized, blended_names
                    )
            for k, role_name in roles_def.items():
                if k.startswith(("DC_", "GC_")) and role_name:
                    override[k] = _blend_color_name(
                        str(role_name), fdata, normalized, blended_names
                    )

            fdata["_roles"] = override
            fdata["_blended"] = True
            theme_blended.append(flavor)
            logger.info(f"blended: {theme}/{flavor}")

            new_seg0 = fdata.get(override["SEG"][0], "") if override["SEG"] else ""
            seen.add(new_seg0 if _validate_hex(new_seg0) else seg0)

        if theme_blended:
            blended[theme] = theme_blended
    return blended


def _hex_lightness(hex_color: str) -> float:
    """Return a hex color's HLS lightness (0.0-1.0)."""
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[1]


def _blend_color_name(
    color_name: str, fdata: dict[str, Any], normalized: float, blended_names: dict[str, str]
) -> str:
    """Return the name of a `{color_name}__blend` entry, creating it if needed.

    Args:
        color_name: The original palette color name to reshade.
        fdata: The flavor's palette dict, mutated in place with the new entry.
        normalized: This flavor's BG lightness rank (0.0-1.0) relative to its
            theme's min/max — see `_apply_accent_blend`.
        blended_names: Cache of color_name -> blended-entry-name already
            created for this flavor, so a name referenced by two roles (e.g.
            two SEG slots pointing at the same color) is shaded once.

    Returns:
        The new blended entry's name, or `color_name` unchanged if it has no
        valid hex to shade.
    """
    if color_name in blended_names:
        return blended_names[color_name]
    original_hex = fdata.get(color_name, "")
    if not _validate_hex(original_hex):
        return color_name
    new_name = f"{color_name}__blend"
    fdata[new_name] = _lightness_rank_blend(original_hex, normalized, *_ACCENT_LIGHTNESS_RANGE)
    blended_names[color_name] = new_name
    return new_name


# Two legend rows for the Elements table: what each color_segN slot means on the
# prompt's main line vs. its stats line (both lines reuse the same seg0-seg5 palette
# for different module clusters — see any src/.config/starship/*.toml format string).
# bg/text/fg/ok/err/warn are single-purpose roles (not dual main/stats-line like
# SEG) — see the "Color roles reference" section of THEMES.md for the full detail.
_MAIN_LINE_LEGEND = [
    "os",
    "dir",
    "git",
    "lang",
    "tools",
    "time",
    "user/hostname",
    "user/hostname",
    "pill text",
    "❯ ok",
    "❯ err",
    "❯ warn",
]
_STATS_LINE_LEGEND = [
    "shell<br/>sudo<br/>shlvl<br/>env_var",
    "memory",
    "cpu",
    "disk",
    "duration",
    "battery<br/>status<br/>jobs",
    "-",
    "-",
    "pill text",
    "-",
    "-",
    "-",
]
_SEG_COUNT = 6  # color_seg0 .. color_seg5


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_hex(value: object) -> bool:
    """Return True if value is a well-formed '#rrggbb' string."""
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def _lightness_rank_blend(accent_hex: str, normalized: float, lo_l: float, hi_l: float) -> str:
    """Reshade accent_hex's lightness, keeping its hue and saturation untouched.

    Args:
        accent_hex: The original accent color to reshade.
        normalized: 0.0-1.0 position to map onto the [lo_l, hi_l] target
            range (typically a flavor's BG-lightness rank within its theme —
            see `_apply_accent_blend`).
        lo_l: Target lightness for normalized=0.0.
        hi_l: Target lightness for normalized=1.0.

    Returns:
        The reshaded color as `#rrggbb` — same hue/saturation as
        `accent_hex`, only lightness moves — or a grey fallback if
        `accent_hex` isn't a valid hex color.
    """
    if not _validate_hex(accent_hex):
        return "#808080"
    ar, ag, ab = (int(accent_hex[i : i + 2], 16) / 255 for i in (1, 3, 5))
    a_h, _a_l, a_s = colorsys.rgb_to_hls(ar, ag, ab)
    new_l = lo_l + normalized * (hi_l - lo_l)
    r, g, b = colorsys.hls_to_rgb(a_h, max(0.0, min(1.0, new_l)), a_s)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


_SWATCH_WIDTH = 60
_SWATCH_HEIGHT = 15


def _make_swatch_png(
    hex_color: str, width: int = _SWATCH_WIDTH, height: int = _SWATCH_HEIGHT
) -> bytes:
    """Render a solid-color rectangle as PNG bytes, using only the stdlib.

    Args:
        hex_color: A validated `#rrggbb` color string.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        Raw PNG file bytes (8-bit truecolor, no alpha).
    """
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + tag
            + body
            + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit depth, RGB
    row = bytes([r, g, b]) * width
    raw = b"".join(b"\x00" + row for _ in range(height))  # filter-type 0 per scanline
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _ensure_swatch_png(hex_color: str, swatch_dir: str) -> str | None:
    """Write a swatch PNG for `hex_color` under `swatch_dir` if not already present.

    Args:
        hex_color: A `#rrggbb` color string (case-insensitive), or empty/invalid.
        swatch_dir: Directory (created if missing) to hold `{hex}.png` files.

    Returns:
        The swatch's filename (e.g. `"c72a3c.png"`), or None if `hex_color` isn't
        a valid 6-digit hex color.
    """
    if not hex_color or not _HEX_RE.match(hex_color):
        return None
    name = hex_color[1:].lower() + ".png"
    path = os.path.join(swatch_dir, name)
    if not os.path.exists(path):
        os.makedirs(swatch_dir, exist_ok=True)
        with open(path, "wb") as f:
            f.write(_make_swatch_png(hex_color))
    return name


def _swatch(hex_color: str, swatch_dir: str, show_hex: bool = True) -> str:
    """Render a hex color as an inline PNG swatch image, optionally with its hex text.

    GitHub's backtick color-dot annotation only works in issues/PRs/discussions,
    never in repository Markdown files, so a self-generated image is the only way
    to show real color in COLORS.md.

    Args:
        hex_color: A `#rrggbb` color string, or empty if unresolved.
        swatch_dir: Directory holding (or to receive) the generated PNG files.
        show_hex: Append a `<br/>` and backtick-hex Markdown below the image.
            False when the hex is already shown in its own table column.

    Returns:
        `<img>`, plus a `<br/>` and backtick-hex Markdown if `show_hex`, or an
        em dash if no color was resolved.
    """
    name = _ensure_swatch_png(hex_color, swatch_dir)
    if not name:
        return "—"
    rel = f".assets/swatches/{name}"
    img = f'<img src="{rel}" width="{_SWATCH_WIDTH}" height="{_SWATCH_HEIGHT}" alt="{hex_color}">'
    return f"{img}<br/>`{hex_color}`" if show_hex else img


def _flavor_names(theme_body: dict[str, Any]) -> list[str]:
    """List a theme's flavor keys, sorted, excluding metadata (`_`-prefixed) keys."""
    return sorted(
        f for f in theme_body if not f.startswith("_") and isinstance(theme_body[f], dict)
    )


# ── Accent ranking (real Neovim highlight-group usage) ─────────────────────────

# Hand-classified once, reused for every theme — not derived from any single
# theme's own opinion. Modern Lua colorschemes set every highlight group's
# colors directly (`nvim_set_hl`) rather than via `:hi link`, so there is no
# link-chain signal to build tiers from (confirmed empirically: 0 linked
# groups across monokai and tokyonight). Tier 1 is the small set of always-
# present, visually-dominant groups (base UI + the classic ~18 legacy syntax
# groups); Tier 2 is diagnostics/search/selection/statusline chrome plus any
# Treesitter capture (`@...`) group; everything else defaults to Tier 3.
_TIER1_GROUPS: frozenset[str] = frozenset(
    {
        "Normal",
        "Error",
        "ErrorMsg",
        "String",
        "Comment",
        "Function",
        "Type",
        "Statement",
        "Identifier",
        "Constant",
        "Special",
        "Keyword",
        "Number",
        "Boolean",
        "PreProc",
        "Todo",
        "Underlined",
        "Title",
        "Directory",
    }
)
_TIER2_GROUPS: frozenset[str] = frozenset(
    {
        "DiagnosticError",
        "DiagnosticWarn",
        "DiagnosticInfo",
        "DiagnosticHint",
        "Search",
        "IncSearch",
        "Visual",
        "VisualNOS",
        "StatusLine",
        "StatusLineNC",
        "Pmenu",
        "PmenuSel",
        "CursorLine",
        "CursorLineNr",
        "LineNr",
        "MatchParen",
        "NonText",
        "SpecialKey",
        "WinSeparator",
        "TabLine",
        "TabLineSel",
        "Folded",
        "SignColumn",
        "DiffAdd",
        "DiffChange",
        "DiffDelete",
        "DiffText",
        "GitSignsAdd",
        "GitSignsChange",
        "GitSignsDelete",
    }
)


def _group_tier_weight(group_name: str) -> int:
    """Return a highlight group's importance weight: 5 (tier 1), 3 (tier 2), or 1 (tier 3)."""
    if group_name in _TIER1_GROUPS:
        return 5
    if group_name in _TIER2_GROUPS or group_name.startswith("@"):
        return 3
    return 1


def _group_tier_number(group_name: str) -> int:
    """Return a highlight group's tier as 1 (most important), 2, or 3 (least)."""
    if group_name in _TIER1_GROUPS:
        return 1
    if group_name in _TIER2_GROUPS or group_name.startswith("@"):
        return 2
    return 3


_HIGHLIGHT_CAPTURE_LUA = r"""
local resolved = vim.api.nvim_get_hl(0, {})
local out = {}
for name, spec in pairs(resolved) do
  out[name] = { fg = spec.fg, bg = spec.bg, sp = spec.sp }
end
local f = io.open(os.getenv("OUT"), "w")
f:write(vim.json.encode(out))
f:close()
"""


def _find_nvim_init() -> str | None:
    """Return path to the installed nvim init.lua, or None if not found."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        candidate = os.path.join(local_app_data, "nvim", "init.lua")
    else:
        candidate = os.path.join(os.path.expanduser("~"), ".config", "nvim", "init.lua")
    return candidate if os.path.isfile(candidate) else None


def _capture_flavor_highlights(
    nv: dict[str, str], flavor: str, nvim_init: str
) -> dict[str, dict[str, int | None]] | None:
    """Load a theme/flavor in headless Neovim and dump every highlight group's resolved colors.

    Args:
        nv: The theme's `_nvim` metadata from roles.json (`theme`, `variant_key`).
        flavor: The flavor to load.
        nvim_init: Path to the user's real `init.lua` (reused so plugin wiring
            and the `vim.g.active_theme`/`vim.g.{variant_key}` dispatch logic
            match exactly what a real session would load).

    Returns:
        Dict of highlight group name -> {"fg"/"bg"/"sp": int|None} (decimal
        RGB, as Neovim returns them). None if nvim/the plugin isn't available,
        the theme has no `_nvim` metadata, or the capture failed/timed out.
    """
    theme_name = nv.get("theme", "")
    if not theme_name or not shutil.which("nvim"):
        return None

    tmp = tempfile.mkdtemp(prefix="get-colors-hl-")
    try:
        nvim_cfg = os.path.join(tmp, "nvimxdg", "nvim")
        os.makedirs(nvim_cfg, exist_ok=True)
        shutil.copy(nvim_init, os.path.join(nvim_cfg, "init.lua"))

        variant_key = nv.get("variant_key", "")
        theme_lua = f'vim.g.active_theme = "{theme_name}"\n'
        if variant_key:
            theme_lua += f'vim.g.{variant_key} = "{flavor}"\n'
        with open(os.path.join(nvim_cfg, "theme.lua"), "w", encoding="utf-8") as f:
            f.write(theme_lua)

        capture_lua = os.path.join(tmp, "capture.lua")
        with open(capture_lua, "w", encoding="utf-8") as f:
            f.write(_HIGHLIGHT_CAPTURE_LUA)

        out_path = os.path.join(tmp, "out.json")
        env = {**os.environ, "XDG_CONFIG_HOME": os.path.join(tmp, "nvimxdg"), "OUT": out_path}
        try:
            subprocess.run(
                ["nvim", "--headless", "-c", f"luafile {capture_lua}", "-c", "qa"],
                env=env,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        if not os.path.isfile(out_path):
            return None
        with open(out_path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return None
        return cast(dict[str, dict[str, "int | None"]], raw)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _rank_flavor_accents(
    highlights: dict[str, dict[str, int | None]], palette: dict[str, str]
) -> dict[str, tuple[int, int]]:
    """Score each palette color by the highlight groups that actually render it.

    Args:
        highlights: Captured highlight groups from `_capture_flavor_highlights`
            (group name -> {"fg"/"bg"/"sp": int|None}).
        palette: The flavor's own `{color_name: hex}` palette.

    Returns:
        Dict of color name -> (summed tier weight, best/lowest tier number
        reached by any contributing group — 1 is most important). Colors
        never rendered by any group are omitted (implicitly rank at the bottom).
    """
    hex_to_names: dict[str, list[str]] = {}
    for name, hex_color in palette.items():
        hex_to_names.setdefault(hex_color.lower(), []).append(name)

    scores: dict[str, int] = {}
    best_tier: dict[str, int] = {}
    for group_name, spec in highlights.items():
        if not isinstance(spec, dict):
            continue  # Lua encodes an empty table ({}) as a JSON [] — no fg/bg/sp set
        weight = _group_tier_weight(group_name)
        tier = _group_tier_number(group_name)
        matched_names: set[str] = set()
        for channel in ("fg", "bg", "sp"):
            value = spec.get(channel)
            if not isinstance(value, int):
                continue
            hex_color = f"#{value:06x}"
            matched_names.update(hex_to_names.get(hex_color, []))
        for name in matched_names:
            scores[name] = scores.get(name, 0) + weight
            best_tier[name] = min(tier, best_tier.get(name, tier))
    return {name: (scores[name], best_tier[name]) for name in scores}


def _role_categories(roles: dict[str, Any]) -> dict[str, set[str]]:
    """Map each role-referenced color name to the exact role key(s) using it.

    Args:
        roles: A merged theme+flavor `_roles` dict.

    Returns:
        Dict of color name -> set of exact role key names, e.g. `{"SEG0",
        "DC_EXEC", "GC_ADDED"}` — every individual role key that resolves to
        that color, not a collapsed category.
    """
    categories: dict[str, set[str]] = {}
    for i, name in enumerate(roles.get("SEG", [])):
        categories.setdefault(str(name), set()).add(f"SEG{i}")
    for key in ("BG", "FG", "TEXT", "OK", "ERR", "WARN"):
        value = roles.get(key)
        if value:
            categories.setdefault(str(value), set()).add(key)
    for key, value in roles.items():
        if not value or isinstance(value, list):
            continue
        if key.startswith(("DC_", "GC_")):
            categories.setdefault(str(value), set()).add(key)
    return categories


def _write_colors_md(data: dict[str, Any], out_path: str) -> None:
    """Generate COLORS.md: per-theme Elements, DirColors/GitColors, and Accent Ranking tables.

    Colors are shown as self-generated PNG swatches (`.assets/swatches/{hex}.png`,
    written alongside `out_path`) plus their hex text — GitHub's backtick color-dot
    annotation only works in issues/PRs/discussions, never in repository Markdown
    files, so an image is the only way to show real color here.

    Accent Ranking requires headless Neovim (via `_capture_flavor_highlights`) to
    load each real theme/flavor and read back actual highlight-group usage; the
    section is skipped per-theme if Neovim or the theme's `_nvim` metadata isn't
    available, so this function still succeeds (with a smaller Accent Ranking
    section) in environments without the plugins installed.

    Args:
        data: The full exported palette dict (theme -> flavor -> {color_name: hex}),
            with each theme/flavor carrying its resolved `_roles`.
        out_path: File path to write the Markdown to (overwritten each run).
    """
    swatch_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)), ".assets", "swatches")
    # Wipe and regenerate every run — otherwise a color renamed/removed since
    # the last export (e.g. a `{name}__blend` entry whose source color moved)
    # leaves a dead, never-referenced PNG behind indefinitely.
    shutil.rmtree(swatch_dir, ignore_errors=True)

    themes_with_content = [
        theme
        for theme in sorted(data)
        if not theme.startswith("_")
        and isinstance(data[theme], dict)
        and _flavor_names(data[theme])
    ]

    toc_lines: list[str] = []
    lines: list[str] = []

    seg_cols = [f"seg{i}" for i in range(_SEG_COUNT)]

    nvim_init = _find_nvim_init()

    for theme in themes_with_content:
        theme_body = data[theme]
        theme_roles = theme_body.get("_roles", {})
        theme_nv = theme_body.get("_nvim", {})
        flavors = _flavor_names(theme_body)

        toc_lines.append(f"- [{theme}](#{theme})")
        toc_lines.append(f"  - [Elements](#{theme}-elements)")

        lines.append(f"## {theme}")
        lines.append("")

        # --- Elements table ---
        lines.append(f'<a id="{theme}-elements"></a>')
        lines.append("### Elements")
        lines.append("")
        header = ["Flavor"] + seg_cols + ["bg", "text", "fg", "ok", "err", "warn"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        lines.append("| *(main line)* | " + " | ".join(_MAIN_LINE_LEGEND) + " |")
        lines.append("| *(stats line)* | " + " | ".join(_STATS_LINE_LEGEND) + " |")

        any_elements = False
        for flavor in flavors:
            fdata = theme_body[flavor]
            palette = {k: v for k, v in fdata.items() if not k.startswith("_")}
            if not palette:
                continue  # nvim-only flavor, no terminal colors to show
            roles = _merge_roles(theme_roles, fdata.get("_roles"))
            seg = roles.get("SEG", [])
            row = [flavor]
            for i in range(_SEG_COUNT):
                name = seg[i] if i < len(seg) else ""
                row.append(_swatch(palette.get(name, ""), swatch_dir))
            for role_key in ("BG", "TEXT", "FG", "OK", "ERR", "WARN"):
                row.append(_swatch(palette.get(roles.get(role_key, ""), ""), swatch_dir))
            lines.append("| " + " | ".join(row) + " |")
            any_elements = True
        if not any_elements:
            lines.pop()  # drop the now-orphaned legend-only table
            lines.pop()
            lines.pop()
            lines.pop()
            lines.append("*(no terminal colors for any flavor of this theme)*")
        lines.append("")

        # --- DirColors / GitColors tables (separate) ---
        all_role_keys = {k for k in theme_roles if k.startswith(("DC_", "GC_"))} | {
            k
            for flavor in flavors
            for k in (theme_body[flavor].get("_roles") or {})
            if k.startswith(("DC_", "GC_"))
        }
        for section, prefix, anchor_slug in (
            ("DirColors", "DC_", "dircolors"),
            ("GitColors", "GC_", "gitcolors"),
        ):
            role_keys = sorted(k for k in all_role_keys if k.startswith(prefix))
            if not role_keys:
                continue
            toc_lines.append(f"  - [{section}](#{theme}-{anchor_slug})")
            lines.append(f'<a id="{theme}-{anchor_slug}"></a>')
            lines.append(f"### {section}")
            lines.append("")
            lines.append("| Flavor | " + " | ".join(role_keys) + " |")
            lines.append("|---|" + "---|" * len(role_keys))
            for flavor in flavors:
                fdata = theme_body[flavor]
                palette = {k: v for k, v in fdata.items() if not k.startswith("_")}
                if not palette:
                    continue
                roles = _merge_roles(theme_roles, fdata.get("_roles"))
                row = [flavor] + [
                    _swatch(palette.get(roles.get(k, ""), ""), swatch_dir) for k in role_keys
                ]
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        # --- Accent ranking table ---
        toc_lines.append(f"  - [Accent Ranking](#{theme}-accent-ranking)")
        lines.append(f'<a id="{theme}-accent-ranking"></a>')
        if nvim_init is None or not theme_nv.get("theme"):
            lines.append("### Accent Ranking")
            lines.append("")
            lines.append("*(nvim not available or no `_nvim` metadata for this theme — skipped)*")
            lines.append("")
        else:
            lines.append("<details>")
            lines.append(
                '<summary><span style="font-size: 1.1em; font-weight: 600;">'
                f"Accent Ranking ({len(flavors)} flavors)</span></summary>"
            )
            lines.append("")
            lines.append(
                "Rank = how important the highlight groups actually rendering that color "
                "are in real Neovim usage (captured via headless Neovim, weighted by group "
                "tier — see `_group_tier_weight` in `get-colors.py`). Split into **Used** "
                "(referenced by this repo's own SEG/DC_\\*/GC_\\* roles) and **Unused**. "
                "`Blended`/`Original` mark `--blend`-generated `{name}__blend` entries and "
                "the color they were reshaded from."
            )
            lines.append("")
            for flavor in flavors:
                fdata = theme_body[flavor]
                palette = {k: v for k, v in fdata.items() if not k.startswith("_")}
                if not palette:
                    continue
                roles = _merge_roles(theme_roles, fdata.get("_roles"))
                categories = _role_categories(roles)
                referenced = set(categories)

                flavor_lines: list[str] = [
                    '<details style="margin-left: 1.25rem">',
                    (
                        '<summary><span style="font-size: 1.02em; font-weight: 600;">'
                        f"{flavor}</span></summary>"
                    ),
                    "",
                ]

                highlights = _capture_flavor_highlights(theme_nv, flavor, nvim_init)
                if highlights is None:
                    flavor_lines += ["*(capture failed/timed out)*", ""]
                    flavor_lines.append("</details>")
                    lines += flavor_lines
                    lines.append("")
                    continue

                ranks = _rank_flavor_accents(highlights, palette)
                ranked = sorted(palette, key=lambda name: (-ranks.get(name, (0, 3))[0], name))
                rank_of = {name: i for i, name in enumerate(ranked, start=1)}

                for label, names in (
                    ("Used", [n for n in ranked if n in referenced]),
                    ("Unused", [n for n in ranked if n not in referenced]),
                ):
                    table_lines = [
                        '<details style="margin-left: 1.25rem">',
                        f"<summary>{label} ({len(names)} colors)</summary>",
                        "",
                    ]
                    header = ["Rank", "Group Tier", "Color", "Hex", "Swatch"]
                    if label == "Used":
                        # A `{name}__blend` entry only exists because a role got
                        # repointed at it, so it's always Used — never Unused.
                        header[3:3] = ["Blended"]
                        header.append("Original")
                        header.append("Og Hex")
                        header.append("Used")
                    table_lines.append("| " + " | ".join(header) + " |")
                    table_lines.append("|" + "---|" * len(header))
                    for name in names:
                        tier = ranks.get(name)
                        tier_label = f"Tier {tier[1]}" if tier else "—"
                        is_blended = name.endswith("__blend")
                        display_name = name[: -len("__blend")] if is_blended else name
                        row = [str(rank_of[name]), tier_label, display_name]
                        if label == "Used":
                            row.append("yes" if is_blended else "no")
                        row.append(f"`{palette[name]}`")
                        row.append(_swatch(palette[name], swatch_dir, show_hex=False))
                        if label == "Used":
                            original_hex = palette.get(display_name, "") if is_blended else ""
                            original_swatch = (
                                _swatch(original_hex, swatch_dir, show_hex=False)
                                if original_hex
                                else "—"
                            )
                            row.append(original_swatch)
                            row.append(f"`{original_hex}`" if original_hex else "—")
                            row.append(", ".join(sorted(categories.get(name, set()))))
                        table_lines.append("| " + " | ".join(row) + " |")
                    table_lines += ["", "</details>", ""]
                    flavor_lines += table_lines

                flavor_lines.append("</details>")
                lines += flavor_lines
                lines.append("")
            lines.append("</details>")
            lines.append("")

    header_lines = [
        "# Theme colors",
        "",
        "Generated by `get-colors.py --export` — do not edit by hand.",
        "",
        "## Contents",
        "",
        *toc_lines,
        "",
    ]
    content = "\n".join(header_lines + lines).rstrip() + "\n"
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".tmp-colors-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, out_path)
    except Exception as e:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        logger.error(f"COLORS.md write failed: {e}")
        sys.exit(2)


def cmd_export(args: argparse.Namespace) -> None:
    td = args.themes_dir
    roles_f = args.roles
    if not roles_f:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for candidate in [
            os.path.join(script_dir, ".config/roles.json"),
            os.path.join(os.path.expanduser("~"), ".config/roles.json"),
        ]:
            if os.path.exists(candidate):
                roles_f = candidate
                break
    if not roles_f:
        logger.error("roles.json not found. Use --roles PATH to specify.")
        sys.exit(1)

    out_f = args.output or os.path.join(os.path.dirname(os.path.abspath(roles_f)), "palettes.json")
    logger.info(f"Roles    : {roles_f}")
    logger.info(f"Output   : {out_f}")
    logger.info(f"Lazy dir : {td}")

    try:
        with open(roles_f, encoding="utf-8") as f:
            result = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Cannot load roles.json: {e}")
        sys.exit(2)

    bfile = os.path.join(td, "bearded/lua/bearded/palettes/generated.lua")
    bearded_flavors: list[str] = []
    if os.path.exists(bfile):
        content = _read_file(bfile) or ""
        bearded_flavors = [str(f) for f in re.findall(r'(?<=\[")[^"]+(?="\] = \{)', content)]
    else:
        logger.warning("bearded plugin not found — skipping")

    all_themes: dict[str, list[str]] = {
        "monokai": ["classic", "light", "machine", "octagon", "pro", "ristretto", "spectrum"],
        "catppuccin": ["frappe", "latte", "macchiato", "mocha"],
        "kanagawa": ["wave", "dragon", "lotus"],
        "gruvbox": ["dark", "dark-hard", "dark-soft", "light"],
        "tokyonight": ["storm", "night", "moon"],
        "flexoki": ["dark", "light"],
        "bearded": bearded_flavors,
        "bamboo": ["vulgaris", "multiplex", "light"],
        "oasis": [
            "abyss",
            "cactus",
            "canyon",
            "desert",
            "dune",
            "lagoon",
            "luna",
            "midnight",
            "mirage",
            "moonlight",
            "night",
            "rose",
            "scorpion",
            "sol",
            "starlight",
            "twilight",
        ],
        "onedarkpro": ["onedark", "onelight", "onedark_vivid", "onedark_dark"],
    }

    ok = err = 0
    for theme, flavors in all_themes.items():
        result.setdefault(theme, {})
        for flavor in flavors:
            pairs = extract_palette(td, theme, flavor)
            if pairs:
                existing = result[theme].get(flavor, {})
                existing.update(dict(pairs))
                result[theme][flavor] = existing
                ok += 1
                logger.debug(f"ok: {theme}/{flavor} ({len(pairs)} colors)")
            else:
                logger.warning(f"no palette: {theme}/{flavor}")
                err += 1

    use_blend = getattr(args, "blend", False)
    if use_blend:
        _apply_accent_blend(result)
    else:
        affected = _find_identical_accent_themes(result)
        if affected:
            summary = ", ".join(f"{t} ({', '.join(fs)})" for t, fs in sorted(affected.items()))
            logger.warning(
                f"Identical accent colors across all flavors detected for: {summary} "
                "— pass --blend to differentiate, or leave as-is."
            )

    seg_errors = _validate_seg_roles(result)
    if seg_errors:
        for msg in seg_errors:
            logger.error(msg)
        sys.exit(1)

    out_dir = os.path.dirname(os.path.abspath(out_f))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".tmp-palettes-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
        os.replace(tmp, out_f)
    except Exception as e:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        logger.error(f"Write failed: {e}")
        sys.exit(2)

    colors_md = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(roles_f))), "COLORS.md"
    )
    _write_colors_md(result, colors_md)
    logger.info(f"Written : {colors_md}")

    total = sum(
        sum(1 for k in cast(dict[str, Any], v) if not k.startswith("_"))
        for v in result.values()
        if isinstance(v, dict)
    )
    logger.info(f"Written : {out_f}")
    logger.info(f"Flavors : {total} extracted ({ok} ok, {err} missing)")


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="get-colors.py",
        description="Color palette viewer and exporter for Neovim themes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--themes-dir",
        default=_DEFAULT_THEMES_DIR,
        metavar="PATH",
        help=f"Neovim lazy plugins dir (default: {_DEFAULT_THEMES_DIR})",
    )

    # ── Action flags ───────────────────────────────────────────────────────────
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--show", action="store_true", help="Display ANSI color swatches from live plugin files"
    )
    actions.add_argument(
        "--palette",
        action="store_true",
        help='Print "name hex" pairs for scripting (requires --theme --flavor)',
    )
    actions.add_argument(
        "--matrix", action="store_true", help="Print unified role matrix from palettes.json"
    )
    actions.add_argument(
        "--export", action="store_true", help="(Re)generate palettes.json from live plugins"
    )

    # ── --show / --palette args ────────────────────────────────────────────────
    parser.add_argument(
        "--theme",
        choices=KNOWN_THEMES,
        metavar="THEME",
        help=f"Filter by theme (--show, --palette, --matrix). One of: {', '.join(KNOWN_THEMES)}",
    )
    parser.add_argument(
        "--flavor",
        default="",
        metavar="FLAVOR",
        help="Filter by flavor/variant (--show, --palette, --matrix)",
    )

    # ── --matrix args ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--prompt",
        action="store_true",
        help="With --matrix: show prompt roles only (SEG0–SEG5, FG, OK, ERR, WARN)",
    )
    parser.add_argument(
        "--colors",
        action="store_true",
        help="With --matrix: show dircolor/git roles only (DC_*/GC_*)",
    )
    parser.add_argument(
        "--palettes",
        metavar="PATH",
        help="With --matrix: path to palettes.json (auto-detected if omitted)",
    )

    # ── --export args ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--roles",
        metavar="PATH",
        help="With --export: path to roles.json (auto-detected if omitted)",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        help="With --export: output path (default: same dir as roles.json)",
    )
    parser.add_argument(
        "--blend",
        action="store_true",
        help=(
            "With --export: reshade a flavor's accent roles "
            "(SEG0-5/OK/ERR/WARN/DC_*/GC_*) when they duplicate an earlier "
            "flavor's SEG0, ranked by that flavor's own BG lightness"
        ),
    )

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.blend and not args.export:
        parser.error("--blend is only valid with --export")

    if args.show:
        cmd_show(args)
    elif args.palette:
        cmd_palette(args)
    elif args.matrix:
        cmd_matrix(args)
    elif args.export:
        cmd_export(args)


if __name__ == "__main__":
    main()
