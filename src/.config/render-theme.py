#!/usr/bin/env python3
"""
render-theme.py — Apply dotfiles color themes from palettes.json.

Subcommands:
  apply       Render starship, dircolors, and git color templates
  set-theme   Validate theme/flavor, write nvim config, then apply templates
  help        List available themes and flavors

Usage:
  render-theme.py apply --palette FILE --theme THEME --flavor FLAVOR --sep CHAR \\
                        --starship-template FILE --starship-output FILE \\
                        --dircolors-template FILE --dircolors-output FILE \\
                        --git-template FILE --git-output FILE [--nvim FILE]

  render-theme.py set-theme --palette FILE --theme THEME [--flavor FLAVOR] \\
                            --sep CHAR (same file flags) [--nvim FILE]

  render-theme.py help --palette FILE
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
import tempfile
from typing import Any, cast

logger = logging.getLogger("render-theme")


# ── Logging ────────────────────────────────────────────────────────────────────


class _ColorFormatter(logging.Formatter):
    _COLORS: dict[int, str] = {
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


# ── Palette loading ────────────────────────────────────────────────────────────


def _load_palette(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data: Any = json.load(f)
    except FileNotFoundError:
        logger.error(f"palettes.json not found: {path}")
        sys.exit(2)
    except json.JSONDecodeError as e:
        logger.error(f"palettes.json is not valid JSON: {e}")
        sys.exit(2)
    if not isinstance(data, dict):
        logger.error("palettes.json must be a JSON object at the top level")
        sys.exit(2)
    return cast(dict[str, Any], data)


def _resolve_theme_flavor(
    data: dict[str, Any], theme: str, flavor: str
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Return (theme_dict, flavor_dict, resolved_flavor). Exits on error."""
    t: Any = data.get(theme)
    if not t:
        avail = " ".join(sorted(k for k in data if not k.startswith("_")))
        logger.error(f"Unknown theme '{theme}'. Available: {avail}")
        sys.exit(1)

    if not flavor:
        flavor = t.get("_default_flavor", "")

    valid: list[str] = [k for k in t if not k.startswith("_")]
    if flavor not in valid:
        logger.error(f"Unknown flavor '{flavor}' for {theme}. Available: {' '.join(sorted(valid))}")
        sys.exit(1)

    return t, t[flavor], flavor


# ── Color helpers ──────────────────────────────────────────────────────────────


def _validate_hex(value: object) -> bool:
    """Return True if value is a valid #rrggbb color string."""
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def _hex_to_rgb_escape(hex_color: str) -> str:
    """Convert #rrggbb to dircolors 38;2;R;G;B escape sequence."""
    if not _validate_hex(hex_color):
        return "38;2;128;128;128"
    h = hex_color[1:]
    return f"38;2;{int(h[0:2], 16)};{int(h[2:4], 16)};{int(h[4:6], 16)}"


def _blend_hex(fg: str, bg: str, alpha: float) -> str:
    """Blend fg over bg at alpha opacity, return #rrggbb."""
    if not (_validate_hex(fg) and _validate_hex(bg)):
        return bg if _validate_hex(bg) else "#808080"
    fr, fg_, fb = int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16)
    br, bg_g, bb = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    r = int(fr * alpha + br * (1 - alpha))
    g = int(fg_ * alpha + bg_g * (1 - alpha))
    b = int(fb * alpha + bb * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


def _is_dark(hex_color: str) -> bool:
    """Return True if the hex color has low perceived luminance."""
    if not _validate_hex(hex_color):
        return True
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return (r * 299 + g * 587 + b * 114) // 1000 < 128


# ── File I/O ───────────────────────────────────────────────────────────────────


def _atomic_write(path: str, content: str) -> None:
    """Write content to path atomically (temp file + rename) to avoid partial writes."""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target_dir, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _render_template(template_path: str, output_path: str, substitutions: dict[str, str]) -> None:
    """Read a template file, substitute {{KEY}} placeholders, write output atomically."""
    try:
        with open(template_path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"Template not found: {template_path}")
        sys.exit(2)
    except OSError as e:
        logger.error(f"Cannot read template {template_path}: {e}")
        sys.exit(2)

    for key, value in substitutions.items():
        content = content.replace("{{" + key + "}}", value)

    try:
        _atomic_write(output_path, content)
    except OSError as e:
        logger.error(f"Cannot write {output_path}: {e}")
        sys.exit(2)
    logger.debug(f"Wrote {output_path}")


# ── Theme application ──────────────────────────────────────────────────────────


def _apply_templates(
    theme_dict: dict[str, Any],
    flavor_dict: dict[str, Any],
    sep: str,
    args: argparse.Namespace,
) -> None:
    """Render starship, dircolors, and git color templates from role mappings."""
    palette: dict[str, str] = {k: v for k, v in flavor_dict.items() if not k.startswith("_")}

    if not palette:
        fallback_name: str = flavor_dict.get("_terminal_fallback", "")
        if fallback_name and fallback_name in theme_dict:
            logger.warning(
                f"No terminal colors for this flavor — using '{fallback_name}' for terminal rendering."
            )
            original_delta: dict[str, Any] | None = flavor_dict.get("_delta")
            flavor_dict = dict(theme_dict[fallback_name])
            if original_delta is not None:
                flavor_dict["_delta"] = original_delta
            palette = {k: v for k, v in flavor_dict.items() if not k.startswith("_")}
        else:
            logger.warning(
                "No palette colors for this flavor — skipping starship/dircolors/git templates (nvim-only mode)."
            )
            return

    roles: dict[str, Any] = flavor_dict.get("_roles") or theme_dict.get("_roles", {})

    def color(role_name: str) -> str:
        val = palette.get(role_name, "")
        if val and not _validate_hex(val):
            logger.warning(f"Invalid hex in palette for '{role_name}': {val!r}")
            return ""
        return val

    # Starship prompt colors
    starship_subs: dict[str, str] = {
        "SEP_TRANS": sep,
    }
    for i, name in enumerate(roles.get("SEG", [])):
        starship_subs[f"COLOR_SEG{i}"] = color(name)
    for role in ("FG", "OK", "ERR", "WARN", "BG", "TEXT"):
        starship_subs[f"COLOR_{role}"] = color(roles.get(role, ""))
    _render_template(args.starship_template, args.starship_output, starship_subs)

    # Dircolors: hex → 38;2;R;G;B
    dc_subs: dict[str, str] = {
        k: _hex_to_rgb_escape(color(v)) for k, v in roles.items() if k.startswith("DC_")
    }
    if dc_subs:
        _render_template(args.dircolors_template, args.dircolors_output, dc_subs)

    # Git diff colors: raw hex
    gc_subs: dict[str, str] = {k: color(v) for k, v in roles.items() if k.startswith("GC_")}
    if gc_subs:
        bg_hex = color(roles.get("BG", ""))
        new_hex = gc_subs.get("GC_NEW", "")
        old_hex = gc_subs.get("GC_OLD", "")
        gc_subs["GC_PLUS_BG"] = _blend_hex(new_hex, bg_hex, 0.15)
        gc_subs["GC_MINUS_BG"] = _blend_hex(old_hex, bg_hex, 0.15)
        gc_subs["GC_PLUS_EMPH_BG"] = _blend_hex(new_hex, bg_hex, 0.30)
        gc_subs["GC_MINUS_EMPH_BG"] = _blend_hex(old_hex, bg_hex, 0.30)
        delta: dict[str, Any] = flavor_dict.get("_delta") or theme_dict.get("_delta") or {}
        syntax_theme: str = delta.get("syntax_theme", "")
        if not syntax_theme:
            syntax_theme = "TwoDark" if _is_dark(bg_hex) else "GitHub"
        gc_subs["DELTA_SYNTAX_THEME"] = syntax_theme
        _render_template(args.git_template, args.git_output, gc_subs)


def _write_nvim_theme(theme_dict: dict[str, Any], flavor: str, nvim_path: str) -> None:
    """Write Neovim theme.lua with the active colorscheme and variant."""
    nv: dict[str, str] = theme_dict.get("_nvim", {})
    theme_name = nv.get("theme", "")
    variant_key = nv.get("variant_key", "")
    lines = [f'vim.g.active_theme = "{theme_name}"\n']
    if variant_key and flavor:
        lines.append(f'vim.g.{variant_key} = "{flavor}"\n')
    try:
        _atomic_write(nvim_path, "".join(lines))
    except OSError as e:
        logger.error(f"Cannot write nvim theme: {e}")
        sys.exit(2)
    logger.debug(f"Wrote nvim theme: {nvim_path}")


# ── Subcommands ────────────────────────────────────────────────────────────────


def cmd_apply(args: argparse.Namespace) -> None:
    """Render templates from palettes.json without any validation side-effects."""
    data = _load_palette(args.palette)
    theme_dict, flavor_dict, flavor = _resolve_theme_flavor(data, args.theme, args.flavor)
    _apply_templates(theme_dict, flavor_dict, args.sep, args)
    if args.nvim:
        _write_nvim_theme(theme_dict, flavor, args.nvim)


def cmd_set_theme(args: argparse.Namespace) -> None:
    """Validate theme/flavor, write nvim config, then apply all templates."""
    data = _load_palette(args.palette)
    theme_dict, flavor_dict, flavor = _resolve_theme_flavor(data, args.theme, args.flavor)
    if args.nvim:
        _write_nvim_theme(theme_dict, flavor, args.nvim)
    _apply_templates(theme_dict, flavor_dict, args.sep, args)
    logger.info(f"Applied: {args.theme}/{flavor}")


def cmd_help(args: argparse.Namespace) -> None:
    """Print available themes and their flavors."""
    data = _load_palette(args.palette)
    print("Usage: set-theme --theme THEME [--flavor FLAVOR] [--starship-template TEMPLATE]")
    print()
    for theme in sorted(data):
        if theme.startswith("_"):
            continue
        t = data[theme]
        default_flavor: str = t.get("_default_flavor", "")
        flavors = sorted(k for k in t if not k.startswith("_"))
        print(f"  {theme:<12} [{' | '.join(flavors)}]  (default: {default_flavor})")


# ── Argument parser ────────────────────────────────────────────────────────────


def _add_render_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--palette", required=True, metavar="FILE", help="Path to palettes.json")
    parser.add_argument(
        "--theme", required=True, metavar="THEME", help="Theme name (e.g. monokai, catppuccin)"
    )
    parser.add_argument(
        "--flavor",
        default="",
        metavar="FLAVOR",
        help="Flavor/variant — omit to use the theme default",
    )
    parser.add_argument(
        "--sep",
        required=True,
        metavar="CHAR",
        help="Separator glyph (U+E0B0 angular or U+E0B4 rounded)",
    )
    parser.add_argument(
        "--starship-template", required=True, metavar="FILE", help="Starship prompt template path"
    )
    parser.add_argument(
        "--starship-output",
        required=True,
        metavar="FILE",
        help="Rendered starship.toml output path",
    )
    parser.add_argument(
        "--dircolors-template", required=True, metavar="FILE", help="Dircolors template path"
    )
    parser.add_argument(
        "--dircolors-output", required=True, metavar="FILE", help="Rendered .dircolors output path"
    )
    parser.add_argument(
        "--git-template", required=True, metavar="FILE", help="Git colors template path"
    )
    parser.add_argument(
        "--git-output", required=True, metavar="FILE", help="Rendered git/theme.conf output path"
    )
    parser.add_argument("--nvim", metavar="FILE", help="Write nvim/theme.lua (optional)")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="render-theme.py",
        description="Apply dotfiles color themes from palettes.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    p_apply = subs.add_parser("apply", help="Render templates (no nvim/validation side-effects)")
    _add_render_args(p_apply)
    p_apply.set_defaults(func=cmd_apply)

    p_set = subs.add_parser("set-theme", help="Validate, write nvim/theme.lua, and apply templates")
    _add_render_args(p_set)
    p_set.set_defaults(func=cmd_set_theme)

    p_help = subs.add_parser("help", help="List available themes and flavors")
    p_help.add_argument("--palette", required=True, metavar="FILE", help="Path to palettes.json")
    p_help.set_defaults(func=cmd_help)

    args = parser.parse_args()
    _setup_logging(getattr(args, "verbose", False))
    args.func(args)


if __name__ == "__main__":
    main()
