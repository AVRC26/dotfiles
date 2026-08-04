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
  --palettes PATH   With --matrix: path to palettes.json (auto-detected)
  --roles PATH      With --export: path to roles.json (auto-detected)
  --themes-dir PATH Neovim lazy plugins dir (default: ~/.local/share/nvim/lazy)

Environment:
  SHOW_COLORS_THEMES_DIR   Override lazy plugins dir

Examples:
  get-colors.py --show
  get-colors.py --show --theme kanagawa
  get-colors.py --show --theme catppuccin --flavor mocha
  get-colors.py --palette --theme gruvbox --flavor dark
  get-colors.py --matrix
  get-colors.py --matrix --prompt
  get-colors.py --matrix --colors
  get-colors.py --matrix --theme catppuccin
  get-colors.py --matrix --theme catppuccin --flavor mocha
  get-colors.py --matrix --theme catppuccin --flavor mocha --prompt
  get-colors.py --export
  get-colors.py --export --output /tmp/palettes-preview.json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import struct
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

    def resolve(theme_data: dict[str, Any], flavor: str) -> dict[str, str]:
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

    filter_theme = args.theme or None
    filter_flavor = args.flavor or None
    rows = [
        (f"{theme}/{flavor}", resolve(data[theme], flavor))
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


# Two legend rows for the Elements table: what each color_segN slot means on the
# prompt's main line vs. its stats line (both lines reuse the same seg0-seg5 palette
# for different module clusters — see any src/.config/starship/*.toml format string).
_MAIN_LINE_LEGEND = ["os", "dir", "git", "lang", "tools", "time", "user/host"]
_STATS_LINE_LEGEND = [
    "shell<br/>sudo<br/>shlvl<br/>env_var",
    "memory",
    "cpu",
    "disk",
    "duration",
    "battery<br/>status<br/>jobs",
    "-",
]
_SEG_COUNT = 6  # color_seg0 .. color_seg5


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


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


def _swatch(hex_color: str, swatch_dir: str) -> str:
    """Render a hex color as an inline PNG swatch image plus its hex text.

    GitHub's backtick color-dot annotation only works in issues/PRs/discussions,
    never in repository Markdown files, so a self-generated image is the only way
    to show real color in COLORS.md.

    Args:
        hex_color: A `#rrggbb` color string, or empty if unresolved.
        swatch_dir: Directory holding (or to receive) the generated PNG files.

    Returns:
        `<img>`, a `<br/>`, then backtick-hex Markdown, or an em dash if no color
        was resolved.
    """
    name = _ensure_swatch_png(hex_color, swatch_dir)
    if not name:
        return "—"
    rel = f".assets/swatches/{name}"
    return (
        f'<img src="{rel}" width="{_SWATCH_WIDTH}" height="{_SWATCH_HEIGHT}" '
        f'alt="{hex_color}"><br/>`{hex_color}`'
    )


def _flavor_names(theme_body: dict[str, Any]) -> list[str]:
    """List a theme's flavor keys, sorted, excluding metadata (`_`-prefixed) keys."""
    return sorted(
        f for f in theme_body if not f.startswith("_") and isinstance(theme_body[f], dict)
    )


def _write_colors_md(data: dict[str, Any], out_path: str) -> None:
    """Generate COLORS.md: per-theme Elements, Dircolors/git, and unused-accent tables.

    Colors are shown as self-generated PNG swatches (`.assets/swatches/{hex}.png`,
    written alongside `out_path`) plus their hex text — GitHub's backtick color-dot
    annotation only works in issues/PRs/discussions, never in repository Markdown
    files, so an image is the only way to show real color here.

    Args:
        data: The full exported palette dict (theme -> flavor -> {color_name: hex}),
            with each theme/flavor carrying its resolved `_roles`.
        out_path: File path to write the Markdown to (overwritten each run).
    """
    swatch_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)), ".assets", "swatches")

    themes_with_content = [
        theme
        for theme in sorted(data)
        if not theme.startswith("_")
        and isinstance(data[theme], dict)
        and _flavor_names(data[theme])
    ]

    lines: list[str] = [
        "# Theme colors",
        "",
        "Generated by `get-colors.py --export` — do not edit by hand.",
        "",
        "## Contents",
        "",
    ]
    lines += [f"- [{theme}](#{theme})" for theme in themes_with_content]
    lines.append("")

    seg_cols = [f"seg{i}" for i in range(_SEG_COUNT)]

    for theme in themes_with_content:
        theme_body = data[theme]
        theme_roles = theme_body.get("_roles", {})
        flavors = _flavor_names(theme_body)

        lines.append(f"## {theme}")
        lines.append("")

        # --- Elements table ---
        lines.append("### Elements")
        lines.append("")
        header = ["Flavor"] + seg_cols + ["user/host"]
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
            bg_hex = palette.get(roles.get("BG", ""), "")
            text_hex = palette.get(roles.get("TEXT", ""), "")
            row.append(f"{_swatch(bg_hex, swatch_dir)}<br/>{_swatch(text_hex, swatch_dir)}")
            lines.append("| " + " | ".join(row) + " |")
            any_elements = True
        if not any_elements:
            lines.pop()  # drop the now-orphaned legend-only table
            lines.pop()
            lines.pop()
            lines.pop()
            lines.append("*(no terminal colors for any flavor of this theme)*")
        lines.append("")

        # --- Dircolors / git table ---
        dc_gc_keys: list[str] = sorted(
            {k for k in theme_roles if k.startswith(("DC_", "GC_"))}
            | {
                k
                for flavor in flavors
                for k in (theme_body[flavor].get("_roles") or {})
                if k.startswith(("DC_", "GC_"))
            }
        )
        if dc_gc_keys:
            lines.append("### Dircolors / git")
            lines.append("")
            lines.append("| Flavor | " + " | ".join(dc_gc_keys) + " |")
            lines.append("|---|" + "---|" * len(dc_gc_keys))
            for flavor in flavors:
                fdata = theme_body[flavor]
                palette = {k: v for k, v in fdata.items() if not k.startswith("_")}
                if not palette:
                    continue
                roles = _merge_roles(theme_roles, fdata.get("_roles"))
                row = [flavor] + [
                    _swatch(palette.get(roles.get(k, ""), ""), swatch_dir) for k in dc_gc_keys
                ]
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        # --- Unused accents table ---
        lines.append("### Unused accents")
        lines.append("")
        lines.append("| Flavor | Unused (not referenced by any SEG/DC_\\*/GC_\\* role) |")
        lines.append("|---|---|")
        for flavor in flavors:
            fdata = theme_body[flavor]
            palette = {k: v for k, v in fdata.items() if not k.startswith("_")}
            if not palette:
                continue
            roles = _merge_roles(theme_roles, fdata.get("_roles"))
            referenced: set[str] = set(roles.get("SEG", []))
            referenced |= {
                str(v) for k, v in roles.items() if k != "SEG" and not isinstance(v, list) and v
            }
            unused = sorted(set(palette) - referenced)
            cell = (
                ", ".join(f"{name}: {_swatch(palette[name], swatch_dir)}" for name in unused)
                if unused
                else "—"
            )
            lines.append(f"| {flavor} | {cell} |")
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
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
                logger.debug(f"  ok: {theme}/{flavor} ({len(pairs)} colors)")
            else:
                logger.warning(f"  no palette: {theme}/{flavor}")
                err += 1

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

    args = parser.parse_args()
    _setup_logging(args.verbose)

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
