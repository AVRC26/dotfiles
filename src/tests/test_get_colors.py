"""Unit tests for get-colors.py."""

from __future__ import annotations

import argparse
import colorsys
import importlib.util
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

_SRC = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("get_colors", _SRC / "get-colors.py")
assert spec is not None
assert spec.loader is not None
gc: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc)


# ── Helpers ────────────────────────────────────────────────────────────────────


def lua_file(tmp: str, name: str, content: str) -> str:
    path = os.path.join(tmp, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return path


CATPPUCCIN_LUA = """\
local M = {}
M.frappe = {
  rosewater = "#f2d5cf",
  flamingo  = "#eebebe",
  pink      = "#f4b8e4",
}
return M
"""

GRUVBOX_LUA = """\
local colors = {
  -- dark section
  dark0 = "#282828",
  dark1 = "#3c3836",
  -- light section
  light0 = "#fbf1c7",
  light1 = "#ebdbb2",
  -- neutral (shared)
  neutral_red = "#cc241d",
}
"""

BEARDED_LUA = """\
local palettes = {
  ["arc"] = {
    red   = "#ec6e83",
    green = "#74dfc4",
    blue  = "#58a3ff",
  },
  ["milkshake"] = {
    red   = "#fa7a61",
    green = "#8bd49c",
  },
}
return palettes
"""

FLEXOKI_LUA = (
    "local base_colors = {\n"
    "\t['tx'] = '#100f0f',\n"
    "\t['bg'] = '#fffcf0',\n"
    "}\n"
    "local M = {}\n"
    "M.dark = {\n"
    "\t['tx-1'] = base_colors['tx'],\n"
    "\t['bg-1'] = base_colors['bg'],\n"
    "\t}\n"
    "return M\n"
)

TOKYONIGHT_STORM_LUA = """\
local colors = {
  bg        = "#24283b",
  fg        = "#c0caf5",
  blue      = "#7aa2f7",
}
"""

TOKYONIGHT_NIGHT_LUA = """\
local colors = {
  bg  = "#1a1b26",
  fg  = "#c0caf5",
}
"""

MINIMAL_PALETTES: dict[str, Any] = {
    "monokai": {
        "_default_flavor": "spectrum",
        "_nvim": {"theme": "monokai-pro"},
        "_roles": {
            "SEG": ["accent1"],
            "FG": "base",
            "OK": "accent4",
            "ERR": "accent1",
            "WARN": "accent2",
            "DC_DIR": "accent5",
            "GC_ADDED": "accent4",
        },
        "spectrum": {
            "accent1": "#fc618d",
            "accent2": "#fd9353",
            "accent4": "#7bd88f",
            "accent5": "#5ad4e6",
            "base": "#f7f1ff",
        },
    },
}

# Extended palette with two themes and two flavors — used for filter tests.
MULTI_PALETTES: dict[str, Any] = {
    **MINIMAL_PALETTES,
    "gruvbox": {
        "_default_flavor": "dark",
        "_nvim": {"theme": "gruvbox"},
        "_roles": {
            "SEG": ["neutral_red"],
            "FG": "dark0",
            "OK": "neutral_green",
            "ERR": "neutral_red",
            "WARN": "neutral_yellow",
            "DC_DIR": "neutral_blue",
            "GC_ADDED": "neutral_green",
        },
        "dark": {
            "neutral_red": "#cc241d",
            "dark0": "#282828",
            "neutral_green": "#98971a",
            "neutral_yellow": "#d79921",
            "neutral_blue": "#458588",
        },
        "light": {
            "neutral_red": "#9d0006",
            "dark0": "#fbf1c7",
            "neutral_green": "#79740e",
            "neutral_yellow": "#b57614",
            "neutral_blue": "#076678",
        },
    },
}


# ── _read_file ─────────────────────────────────────────────────────────────────


class TestReadFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_existing(self) -> None:
        path = os.path.join(self.tmp, "f.txt")
        Path(path).write_text("hello")
        self.assertEqual(gc._read_file(path), "hello")

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(gc._read_file("/no/such/file.txt"))

    def test_oserror_returns_none(self) -> None:
        with patch("builtins.open", side_effect=OSError("permission denied")):
            result = gc._read_file("/some/path.txt")
        self.assertIsNone(result)


# ── _pal_pairs ─────────────────────────────────────────────────────────────────


class TestPalPairs(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_basic_extraction(self) -> None:
        path = lua_file(self.tmp, "t.lua", CATPPUCCIN_LUA)
        pairs = gc._pal_pairs(path)
        names = [n for n, _ in pairs]
        self.assertIn("flamingo", names)
        self.assertIn("pink", names)

    def test_prefix_filter(self) -> None:
        path = lua_file(self.tmp, "g.lua", GRUVBOX_LUA)
        pairs = gc._pal_pairs(path, prefix="dark")
        names = [n for n, _ in pairs]
        self.assertIn("dark0", names)
        self.assertNotIn("light0", names)
        self.assertNotIn("neutral_red", names)

    def test_strip_prefix(self) -> None:
        path = lua_file(self.tmp, "g.lua", GRUVBOX_LUA)
        pairs = gc._pal_pairs(path, prefix="dark", strip="dark_")
        names = [n for n, _ in pairs]
        # dark0 has prefix "dark" but NOT "dark_", so strip doesn't apply
        self.assertIn("dark0", names)

    def test_skips_comment_lines(self) -> None:
        # The "-- dark section" comment line is before dark0, not on the same line
        path = lua_file(self.tmp, "g.lua", GRUVBOX_LUA)
        pairs = gc._pal_pairs(path)
        names = [n for n, _ in pairs]
        self.assertIn("dark0", names)

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(gc._pal_pairs("/no/such/file.lua"), [])

    def test_sorted_output(self) -> None:
        path = lua_file(self.tmp, "t.lua", CATPPUCCIN_LUA)
        pairs = gc._pal_pairs(path)
        names = [n for n, _ in pairs]
        self.assertEqual(names, sorted(names))

    def test_skips_inline_comment(self) -> None:
        # Color on the same line as a comment should be skipped
        lua = 'local c = {\n  -- red = "#ff0000",\n  blue = "#0000ff",\n}\n'
        path = lua_file(self.tmp, "inline.lua", lua)
        pairs = gc._pal_pairs(path)
        names = [n for n, _ in pairs]
        self.assertNotIn("red", names)
        self.assertIn("blue", names)

    def test_strip_prefix_applies(self) -> None:
        lua = 'local c = {\n  dark_red = "#ff0000",\n}\n'
        path = lua_file(self.tmp, "dark.lua", lua)
        pairs = gc._pal_pairs(path, prefix="dark", strip="dark_")
        names = [n for n, _ in pairs]
        # dark_red has prefix "dark" and strip "dark_" → displays as "red"
        self.assertIn("red", names)


# ── _pal_pairs_exclude ─────────────────────────────────────────────────────────


class TestPalPairsExclude(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_excludes_prefixes(self) -> None:
        path = lua_file(self.tmp, "g.lua", GRUVBOX_LUA)
        pairs = gc._pal_pairs_exclude(path, "dark", "light")
        names = [n for n, _ in pairs]
        self.assertNotIn("dark0", names)
        self.assertNotIn("light0", names)
        self.assertIn("neutral_red", names)

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(gc._pal_pairs_exclude("/no/such/file.lua", "x"), [])

    def test_skips_inline_comment(self) -> None:
        lua = 'local c = {\n  -- neutral_red = "#ff0000",\n  neutral_blue = "#0000ff",\n}\n'
        path = lua_file(self.tmp, "excl.lua", lua)
        pairs = gc._pal_pairs_exclude(path, "dark", "light")
        names = [n for n, _ in pairs]
        # neutral_red is on a comment line, neutral_blue is not excluded
        self.assertNotIn("neutral_red", names)
        self.assertIn("neutral_blue", names)


BAMBOO_LUA = """\
local palette = {
  vulgaris = {
    bg0 = "#1b1e28",
    fg  = "#d5d5d5",
    red = "#e05f74",
  },
  multiplex = {
    bg0   = "#1b1e28",
    green = "#8fcda4",
  },
}
return palette
"""

OASIS_LUA = """\
local colors = {
  rose = {
    [500] = "#d95b85",
  },
  sky = {
    [500] = "#5badcf",
  },
  theme = {
    [500] = "#000000",
  },
}
local theme = {
  moonlight = {
    bg = { core = "#1a1a2e" },
    fg = { core = "#c0c0d0" },
  },
}
"""

ONEDARKPRO_LUA = """\
local M = {}
local default_colors = {
  bg  = "#282c34",
  fg  = "#abb2bf",
  red = "#e06c75",
}
return M
"""


# ── _extract_bearded_flavor ────────────────────────────────────────────────────


class TestExtractBeardedFlavor(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.bfile = os.path.join(self.tmp, "bearded/lua/bearded/palettes/generated.lua")
        os.makedirs(os.path.dirname(self.bfile), exist_ok=True)
        Path(self.bfile).write_text(BEARDED_LUA)

    def test_extracts_arc(self) -> None:
        pairs = gc._extract_bearded_flavor(self.tmp, "arc")
        d = dict(pairs)
        self.assertEqual(d["red"], "#ec6e83")
        self.assertEqual(d["green"], "#74dfc4")
        self.assertEqual(d["blue"], "#58a3ff")

    def test_extracts_milkshake(self) -> None:
        pairs = gc._extract_bearded_flavor(self.tmp, "milkshake")
        d = dict(pairs)
        self.assertIn("red", d)
        self.assertNotIn("blue", d)

    def test_unknown_flavor_returns_empty(self) -> None:
        self.assertEqual(gc._extract_bearded_flavor(self.tmp, "ghost"), [])

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(gc._extract_bearded_flavor("/no/dir", "arc"), [])


# ── _extract_tokyonight_night ──────────────────────────────────────────────────


class TestExtractTokyonightNight(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        tn = os.path.join(self.tmp, "tokyonight.nvim/lua/tokyonight/colors")
        os.makedirs(tn, exist_ok=True)
        Path(tn, "storm.lua").write_text(TOKYONIGHT_STORM_LUA)
        Path(tn, "night.lua").write_text(TOKYONIGHT_NIGHT_LUA)

    def test_merges_storm_and_night(self) -> None:
        pairs = gc._extract_tokyonight_night(self.tmp)
        d = dict(pairs)
        # bg is overridden by night
        self.assertEqual(d["bg"], "#1a1b26")
        # fg is the same in both
        self.assertEqual(d["fg"], "#c0caf5")
        # blue is only in storm
        self.assertEqual(d["blue"], "#7aa2f7")

    def test_missing_storm_still_works(self) -> None:
        # Remove storm file — should fall back to night only
        tn = os.path.join(self.tmp, "tokyonight.nvim/lua/tokyonight/colors")
        os.remove(os.path.join(tn, "storm.lua"))
        pairs = gc._extract_tokyonight_night(self.tmp)
        d = dict(pairs)
        self.assertIn("bg", d)


# ── _extract_flexoki_variant ───────────────────────────────────────────────────


class TestExtractFlexokiVariant(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        fp = os.path.join(self.tmp, "flexoki/lua/flexoki/palette.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(FLEXOKI_LUA)

    def test_dark_variant(self) -> None:
        pairs = gc._extract_flexoki_variant(self.tmp, "dark")
        d = dict(pairs)
        self.assertIn("tx-1", d)
        self.assertEqual(d["tx-1"], "#100f0f")

    def test_nonexistent_variant_returns_empty(self) -> None:
        pairs = gc._extract_flexoki_variant(self.tmp, "light")
        self.assertEqual(pairs, [])

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(gc._extract_flexoki_variant("/no/dir", "dark"), [])


# ── _extract_bamboo_flavor ────────────────────────────────────────────────────


class TestExtractBambooFlavor(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "bamboo.nvim/lua/bamboo/palette.lua")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(BAMBOO_LUA)

    def test_extracts_vulgaris(self) -> None:
        pairs = gc._extract_bamboo_flavor(self.tmp, "vulgaris")
        d = dict(pairs)
        self.assertEqual(d["red"], "#e05f74")
        self.assertEqual(d["bg0"], "#1b1e28")

    def test_extracts_multiplex(self) -> None:
        pairs = gc._extract_bamboo_flavor(self.tmp, "multiplex")
        d = dict(pairs)
        self.assertIn("green", d)
        self.assertNotIn("red", d)

    def test_unknown_flavor_returns_empty(self) -> None:
        self.assertEqual(gc._extract_bamboo_flavor(self.tmp, "nonexistent"), [])

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(gc._extract_bamboo_flavor("/no/dir", "vulgaris"), [])


# ── _extract_oasis_flavor ──────────────────────────────────────────────────────


class TestExtractOasisFlavor(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "oasis.nvim/lua/oasis/palette.lua")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(OASIS_LUA)

    def test_extracts_bg_fg_from_theme_section(self) -> None:
        pairs = gc._extract_oasis_flavor(self.tmp, "moonlight")
        d = dict(pairs)
        self.assertEqual(d["bg"], "#1a1a2e")
        self.assertEqual(d["fg"], "#c0c0d0")

    def test_extracts_500_level_colors(self) -> None:
        pairs = gc._extract_oasis_flavor(self.tmp, "moonlight")
        d = dict(pairs)
        self.assertEqual(d["rose"], "#d95b85")
        self.assertEqual(d["sky"], "#5badcf")

    def test_skips_theme_key_in_colors_section(self) -> None:
        # "theme" is in _OASIS_SKIP — its [500] entry must not appear as a color key
        pairs = gc._extract_oasis_flavor(self.tmp, "moonlight")
        d = dict(pairs)
        self.assertNotIn("theme", d)

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(gc._extract_oasis_flavor("/no/dir", "moonlight"), [])


# ── _extract_onedarkpro_style ──────────────────────────────────────────────────


class TestExtractOnedarkproStyle(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "onedarkpro.nvim/lua/onedarkpro/themes/onedark.lua")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(ONEDARKPRO_LUA)

    def test_extracts_colors(self) -> None:
        pairs = gc._extract_onedarkpro_style(self.tmp, "onedark")
        d = dict(pairs)
        self.assertEqual(d["bg"], "#282c34")
        self.assertEqual(d["red"], "#e06c75")

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(gc._extract_onedarkpro_style(self.tmp, "onelight"), [])

    def test_no_default_colors_block_returns_empty(self) -> None:
        path = os.path.join(self.tmp, "onedarkpro.nvim/lua/onedarkpro/themes/nodefs.lua")
        Path(path).write_text('local M = { bg = "#000000" }\nreturn M\n')
        self.assertEqual(gc._extract_onedarkpro_style(self.tmp, "nodefs"), [])


# ── extract_palette (routing) ──────────────────────────────────────────────────


class TestExtractPalette(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def _make_catppuccin(self) -> None:
        fp = os.path.join(self.tmp, "catppuccin/lua/catppuccin/palettes/frappe.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(CATPPUCCIN_LUA)

    def test_catppuccin(self) -> None:
        self._make_catppuccin()
        pairs = gc.extract_palette(self.tmp, "catppuccin", "frappe")
        names = [n for n, _ in pairs]
        self.assertIn("flamingo", names)

    def test_unknown_theme_exits(self) -> None:
        with self.assertRaises(SystemExit):
            gc.extract_palette(self.tmp, "unknown_theme", "dark")


# ── cmd_matrix ─────────────────────────────────────────────────────────────────


class TestCmdMatrix(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.pal_path = os.path.join(self.tmp, "palettes.json")
        with open(self.pal_path, "w") as f:
            json.dump(MINIMAL_PALETTES, f)

    def _run_matrix(
        self,
        prompt: bool = False,
        colors: bool = False,
        theme: str | None = None,
        flavor: str = "",
        pal_path: str | None = None,
    ) -> str:
        args = argparse.Namespace(
            palettes=pal_path or self.pal_path,
            prompt=prompt,
            colors=colors,
            theme=theme,
            flavor=flavor,
            themes_dir=self.tmp,
            verbose=False,
        )
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.cmd_matrix(args)
        return out.getvalue()

    def test_prompt_submode(self) -> None:
        output = self._run_matrix(prompt=True, colors=False)
        self.assertIn("PROMPT ROLES", output)
        self.assertNotIn("DIRCOLORS", output)

    def test_colors_submode(self) -> None:
        output = self._run_matrix(prompt=False, colors=True)
        self.assertIn("DIRCOLORS", output)
        self.assertNotIn("PROMPT ROLES", output)

    def test_no_submode_prints_both(self) -> None:
        output = self._run_matrix(prompt=False, colors=False)
        self.assertIn("PROMPT ROLES", output)
        self.assertIn("DIRCOLORS", output)

    def test_missing_palette_exits(self) -> None:
        empty_dir = tempfile.mkdtemp()
        args = argparse.Namespace(
            palettes=os.path.join(empty_dir, "nonexistent.json"),
            prompt=False,
            colors=False,
            theme=None,
            flavor="",
            themes_dir=empty_dir,
            verbose=False,
        )
        with self.assertRaises(SystemExit):
            gc.cmd_matrix(args)

    def test_empty_palette_no_rows_skips_table(self) -> None:
        # Empty palette → rows=[] → print_table returns early without printing
        empty_pal_path = os.path.join(self.tmp, "empty.json")
        with open(empty_pal_path, "w") as f:
            json.dump({}, f)
        args = argparse.Namespace(
            palettes=empty_pal_path,
            prompt=False,
            colors=False,
            theme=None,
            flavor="",
            themes_dir=self.tmp,
            verbose=False,
        )
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.cmd_matrix(args)
        # With no rows, no table headers are printed
        self.assertNotIn("theme/flavor", out.getvalue())

    def test_matrix_autodetect_no_palettes_exits(self) -> None:
        # When palettes=None and no file on disk, should exit
        import unittest.mock as um

        args = argparse.Namespace(
            palettes=None,
            prompt=False,
            colors=False,
            theme=None,
            flavor="",
            themes_dir=self.tmp,
            verbose=False,
        )
        # Patch os.path.exists to always return False so auto-detect fails
        with um.patch("os.path.exists", return_value=False), self.assertRaises(SystemExit):
            gc.cmd_matrix(args)

    # ── theme / flavor filter tests ───────────────────────────────────────────

    def _multi_pal_path(self) -> str:
        p = os.path.join(self.tmp, "multi.json")
        with open(p, "w") as f:
            json.dump(MULTI_PALETTES, f)
        return p

    def test_theme_filter_includes_only_matching_theme(self) -> None:
        out = self._run_matrix(pal_path=self._multi_pal_path(), theme="gruvbox")
        self.assertIn("gruvbox", out)
        self.assertNotIn("monokai", out)

    def test_theme_filter_no_match_produces_empty_table(self) -> None:
        out = self._run_matrix(pal_path=self._multi_pal_path(), theme="catppuccin")
        self.assertNotIn("theme/flavor", out)

    def test_flavor_filter_includes_only_matching_flavor(self) -> None:
        out = self._run_matrix(pal_path=self._multi_pal_path(), flavor="dark")
        self.assertIn("gruvbox/dark", out)
        self.assertNotIn("gruvbox/light", out)
        self.assertNotIn("monokai/spectrum", out)

    def test_theme_and_flavor_filter_single_row(self) -> None:
        out = self._run_matrix(pal_path=self._multi_pal_path(), theme="gruvbox", flavor="light")
        self.assertIn("gruvbox/light", out)
        self.assertNotIn("gruvbox/dark", out)
        self.assertNotIn("monokai", out)

    def test_no_filter_includes_all_themes(self) -> None:
        out = self._run_matrix(pal_path=self._multi_pal_path())
        self.assertIn("monokai/spectrum", out)
        self.assertIn("gruvbox/dark", out)
        self.assertIn("gruvbox/light", out)


# ── _default_themes_dir ────────────────────────────────────────────────────────


class TestDefaultThemesDir(unittest.TestCase):
    def test_env_override_takes_precedence(self) -> None:
        with patch.dict(os.environ, {"SHOW_COLORS_THEMES_DIR": "/custom/path"}):
            self.assertEqual(gc._default_themes_dir(), "/custom/path")

    def test_windows_uses_localappdata(self) -> None:
        with (
            patch.dict(
                os.environ, {"LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local"}, clear=False
            ),
            patch("os.name", "nt"),
            patch.dict(os.environ, {"SHOW_COLORS_THEMES_DIR": ""}, clear=False),
        ):
            # Remove env override so path logic runs
            env = {k: v for k, v in os.environ.items() if k != "SHOW_COLORS_THEMES_DIR"}
            with patch.dict(os.environ, env, clear=True):
                result = gc._default_themes_dir()
        self.assertIn("nvim-data", result)
        self.assertIn("lazy", result)

    def test_linux_uses_home_local_share(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "SHOW_COLORS_THEMES_DIR"}
        with patch.dict(os.environ, env, clear=True), patch("os.name", "posix"):
            result = gc._default_themes_dir()
        self.assertIn(".local", result)
        self.assertIn("nvim", result)
        self.assertIn("lazy", result)

    def test_windows_falls_back_to_home_when_no_localappdata(self) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("SHOW_COLORS_THEMES_DIR", "LOCALAPPDATA")
        }
        with patch.dict(os.environ, env, clear=True), patch("os.name", "nt"):
            result = gc._default_themes_dir()
        self.assertIn("nvim-data", result)
        self.assertIn("lazy", result)


# ── cmd_palette ────────────────────────────────────────────────────────────────


class TestCmdPalette(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        fp = os.path.join(self.tmp, "catppuccin/lua/catppuccin/palettes/frappe.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(CATPPUCCIN_LUA)

    def test_outputs_name_hex_pairs(self) -> None:
        args = argparse.Namespace(
            themes_dir=self.tmp,
            theme="catppuccin",
            flavor="frappe",
            verbose=False,
        )
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.cmd_palette(args)
        lines = out.getvalue().strip().splitlines()
        self.assertTrue(all(len(ln.split()) == 2 for ln in lines if ln))
        self.assertTrue(all(ln.split()[1].startswith("#") for ln in lines if ln))

    def test_no_theme_exits(self) -> None:
        args = argparse.Namespace(themes_dir=self.tmp, theme=None, flavor="dark", verbose=False)
        with self.assertRaises(SystemExit):
            gc.cmd_palette(args)

    def test_no_flavor_exits(self) -> None:
        args = argparse.Namespace(themes_dir=self.tmp, theme="catppuccin", flavor="", verbose=False)
        with self.assertRaises(SystemExit):
            gc.cmd_palette(args)


# ── display helpers ────────────────────────────────────────────────────────────


class TestDisplayHelpers(unittest.TestCase):
    def test_show_swatch_valid(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc._show_swatch("mycolor", "#fc618d")
        self.assertIn("mycolor", out.getvalue())
        self.assertIn("#fc618d", out.getvalue())

    def test_show_swatch_invalid_skips(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc._show_swatch("bad", "not-a-color")
        self.assertEqual(out.getvalue(), "")

    def test_section(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc._section("TEST SECTION")
        self.assertIn("TEST SECTION", out.getvalue())

    def test_flavor_header(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc._flavor_header("DARK")
        self.assertIn("DARK", out.getvalue())

    def test_print_header(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc._print_header()
        self.assertIn("NEOVIM THEME", out.getvalue())


# ── show_theme ─────────────────────────────────────────────────────────────────


class TestShowTheme(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def _make_catppuccin(self) -> None:
        for flavor in ["frappe", "latte", "macchiato", "mocha"]:
            fp = os.path.join(self.tmp, f"catppuccin/lua/catppuccin/palettes/{flavor}.lua")
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            Path(fp).write_text(CATPPUCCIN_LUA)

    def test_catppuccin_all_flavors(self) -> None:
        self._make_catppuccin()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "catppuccin")
        self.assertIn("CATPPUCCIN", out.getvalue())

    def test_catppuccin_one_flavor(self) -> None:
        self._make_catppuccin()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "catppuccin", "frappe")
        output = out.getvalue()
        self.assertIn("FRAPPE", output)

    def test_gruvbox_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "gruvbox")
        self.assertIn("❌", out.getvalue())

    def _make_gruvbox(self) -> None:
        fp = os.path.join(self.tmp, "gruvbox.nvim/lua/gruvbox.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(GRUVBOX_LUA)

    def test_gruvbox_renders(self) -> None:
        self._make_gruvbox()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "gruvbox")
        self.assertIn("GRUVBOX", out.getvalue())

    def test_kanagawa_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "kanagawa")
        self.assertIn("❌", out.getvalue())

    KANAGAWA_LUA = """\
local colors = {
  dragon_black0 = "#0d0c0c",
  dragon_blue = "#658594",
  lotus_white0 = "#d5cea3",
}
"""

    def _make_kanagawa(self) -> None:
        kp = os.path.join(self.tmp, "kanagawa.nvim/lua/kanagawa/colors.lua")
        os.makedirs(os.path.dirname(kp), exist_ok=True)
        Path(kp).write_text(self.KANAGAWA_LUA)

    def test_kanagawa_wave_renders(self) -> None:
        self._make_kanagawa()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "kanagawa", "wave")
        self.assertIn("KANAGAWA", out.getvalue())

    def test_kanagawa_dragon_renders(self) -> None:
        self._make_kanagawa()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "kanagawa", "dragon")
        self.assertIn("KANAGAWA", out.getvalue())

    def test_tokyonight_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "tokyonight")
        self.assertIn("❌", out.getvalue())

    def test_tokyonight_storm_renders(self) -> None:
        self._make_tokyonight()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "tokyonight", "storm")
        self.assertIn("TOKYO NIGHT", out.getvalue())

    def test_tokyonight_night_renders(self) -> None:
        self._make_tokyonight()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "tokyonight", "night")
        self.assertIn("NIGHT", out.getvalue())

    def test_tokyonight_moon_renders(self) -> None:
        self._make_tokyonight()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "tokyonight", "moon")
        self.assertIn("MOON", out.getvalue())

    def _make_tokyonight(self) -> None:
        tn = os.path.join(self.tmp, "tokyonight.nvim/lua/tokyonight/colors")
        os.makedirs(tn, exist_ok=True)
        Path(tn, "storm.lua").write_text(TOKYONIGHT_STORM_LUA)
        Path(tn, "night.lua").write_text(TOKYONIGHT_NIGHT_LUA)
        Path(tn, "moon.lua").write_text(TOKYONIGHT_STORM_LUA)

    def test_tokyonight_day_shows_note(self) -> None:
        self._make_tokyonight()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "tokyonight", "day")
        self.assertIn("runtime", out.getvalue())

    def test_flexoki_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "flexoki")
        self.assertIn("❌", out.getvalue())

    def test_flexoki_base_colors(self) -> None:
        fp = os.path.join(self.tmp, "flexoki/lua/flexoki/palette.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(FLEXOKI_LUA)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "flexoki", "base")
        self.assertIn("BASE", out.getvalue())

    def test_bearded_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "bearded")
        self.assertIn("❌", out.getvalue())

    def test_bearded_renders(self) -> None:
        bp = os.path.join(self.tmp, "bearded/lua/bearded/palettes/generated.lua")
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        Path(bp).write_text(BEARDED_LUA)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "bearded")
        self.assertIn("BEARDED", out.getvalue())

    def test_monokai_renders(self) -> None:
        fp = os.path.join(self.tmp, "monokai-pro.nvim/lua/monokai-pro/palette/spectrum.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(CATPPUCCIN_LUA)  # any valid lua with hex colors works
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "monokai", "spectrum")
        self.assertIn("MONOKAI", out.getvalue())

    def test_gruvbox_accents_flavor(self) -> None:
        self._make_gruvbox()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "gruvbox", "accents")
        self.assertIn("SHARED ACCENTS", out.getvalue())

    def test_gruvbox_shared_flavor(self) -> None:
        self._make_gruvbox()
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "gruvbox", "shared")
        self.assertIn("SHARED ACCENTS", out.getvalue())

    def test_bearded_specific_flavor(self) -> None:
        bp = os.path.join(self.tmp, "bearded/lua/bearded/palettes/generated.lua")
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        Path(bp).write_text(BEARDED_LUA)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "bearded", "arc")
        output = out.getvalue()
        self.assertIn("ARC", output)
        self.assertNotIn("MILKSHAKE", output)

    def test_flexoki_dark_variant(self) -> None:
        fp = os.path.join(self.tmp, "flexoki/lua/flexoki/palette.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(FLEXOKI_LUA)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "flexoki", "dark")
        self.assertIn("DARK", out.getvalue())

    def test_bamboo_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "bamboo")
        self.assertIn("❌", out.getvalue())

    def test_bamboo_renders(self) -> None:
        bp = os.path.join(self.tmp, "bamboo.nvim/lua/bamboo/palette.lua")
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        Path(bp).write_text(BAMBOO_LUA)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "bamboo", "vulgaris")
        self.assertIn("BAMBOO", out.getvalue())

    def test_oasis_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "oasis")
        self.assertIn("❌", out.getvalue())

    def test_oasis_renders(self) -> None:
        op = os.path.join(self.tmp, "oasis.nvim/lua/oasis/palette.lua")
        os.makedirs(os.path.dirname(op), exist_ok=True)
        Path(op).write_text(OASIS_LUA)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "oasis", "moonlight")
        self.assertIn("OASIS", out.getvalue())

    def test_onedarkpro_missing(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "onedarkpro")
        self.assertIn("❌", out.getvalue())

    def test_onedarkpro_renders(self) -> None:
        path = os.path.join(self.tmp, "onedarkpro.nvim/lua/onedarkpro/themes/onedark.lua")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(ONEDARKPRO_LUA)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.show_theme(self.tmp, "onedarkpro", "onedark")
        self.assertIn("ONEDARKPRO", out.getvalue())


# ── cmd_show ───────────────────────────────────────────────────────────────────


class TestCmdShow(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_show_all_empty_plugins(self) -> None:
        args = argparse.Namespace(themes_dir=self.tmp, theme=None, flavor="", verbose=False)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.cmd_show(args)
        self.assertIn("Done!", out.getvalue())

    def test_show_specific_theme(self) -> None:
        args = argparse.Namespace(themes_dir=self.tmp, theme="gruvbox", flavor="", verbose=False)
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.cmd_show(args)
        self.assertIn("GRUVBOX", out.getvalue())


# ── cmd_export ─────────────────────────────────────────────────────────────────


class TestCmdExport(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.roles_path = os.path.join(self.tmp, ".config/roles.json")
        os.makedirs(os.path.dirname(self.roles_path), exist_ok=True)
        # Minimal roles.json
        roles: dict[str, Any] = {
            "catppuccin": {
                "_default_flavor": "frappe",
                "_nvim": {"theme": "catppuccin"},
                "_roles": {
                    "SEG": ["rosewater"],
                    "FG": "flamingo",
                    "OK": "pink",
                    "ERR": "rosewater",
                    "WARN": "flamingo",
                },
            }
        }
        with open(self.roles_path, "w") as f:
            json.dump(roles, f)

    def _make_catppuccin(self) -> None:
        fp = os.path.join(self.tmp, "catppuccin/lua/catppuccin/palettes/frappe.lua")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(CATPPUCCIN_LUA)

    def test_export_writes_palettes(self) -> None:
        self._make_catppuccin()
        out_path = os.path.join(self.tmp, "out_palettes.json")
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=self.roles_path,
            output=out_path,
            verbose=False,
        )
        gc.cmd_export(args)
        self.assertTrue(os.path.exists(out_path))
        data = json.loads(Path(out_path).read_text())
        self.assertIn("catppuccin", data)

    def test_export_missing_roles_exits(self) -> None:
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles="/nonexistent/roles.json",
            output=None,
            verbose=False,
        )
        with self.assertRaises(SystemExit):
            gc.cmd_export(args)

    def test_export_with_bearded_plugin(self) -> None:
        """Exercise the bearded auto-detect branch in cmd_export."""
        bp = os.path.join(self.tmp, "bearded/lua/bearded/palettes/generated.lua")
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        Path(bp).write_text(BEARDED_LUA)
        out_path = os.path.join(self.tmp, "out2.json")
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=self.roles_path,
            output=out_path,
            verbose=False,
        )
        gc.cmd_export(args)
        self.assertTrue(os.path.exists(out_path))

    def test_export_autodetect_no_roles_exits(self) -> None:
        """When roles=None and no roles.json on disk, should exit."""
        import unittest.mock as um

        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=None,
            output=None,
            verbose=False,
        )
        with um.patch("os.path.exists", return_value=False), self.assertRaises(SystemExit):
            gc.cmd_export(args)

    def test_export_autodetect_finds_roles(self) -> None:
        """When roles=None and roles.json exists next to the script, it is found."""
        out_path = os.path.join(self.tmp, "autodet.json")
        self._make_catppuccin()
        # The module auto-detects src/.config/roles.json (committed to repo). That
        # real roles.json also drives _write_colors_md's destination path, so it
        # must be patched away here — otherwise this test overwrites the repo's
        # real src/COLORS.md with empty tables (themes_dir is a fake temp dir with
        # no plugins installed, so every theme in the real roles.json fails
        # extraction).
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=None,
            output=out_path,
            verbose=False,
        )
        with patch.object(gc, "_write_colors_md", return_value=None):
            gc.cmd_export(args)
        self.assertTrue(os.path.exists(out_path))

    def test_export_write_failure_exits(self) -> None:
        """If writing the temp file fails, cmd_export should exit with code 2."""
        self._make_catppuccin()
        out_path = os.path.join(self.tmp, "fail.json")
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=self.roles_path,
            output=out_path,
            verbose=False,
        )
        with (
            patch("json.dump", side_effect=OSError("disk full")),
            self.assertRaises(SystemExit) as cm,
        ):
            gc.cmd_export(args)
        self.assertEqual(cm.exception.code, 2)

    def test_export_exits_on_seg_drift(self) -> None:
        """cmd_export must hard-fail when a sibling flavor's SEG array reorders a shared color name."""
        drift_roles: dict[str, Any] = {
            "onedarkpro": {
                "_default_flavor": "onedark",
                "onedark": {
                    "_roles": {"SEG": ["red", "orange", "yellow", "green", "cyan", "purple"]}
                },
                "onedark_vivid": {
                    "_roles": {"SEG": ["red", "purple", "yellow", "green", "blue", "cyan"]}
                },
            }
        }
        roles_path = os.path.join(self.tmp, "drift_roles.json")
        with open(roles_path, "w") as f:
            json.dump(drift_roles, f)
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=roles_path,
            output=os.path.join(self.tmp, "should_not_be_written.json"),
            verbose=False,
        )
        with self.assertRaises(SystemExit) as cm:
            gc.cmd_export(args)
        self.assertEqual(cm.exception.code, 1)
        self.assertFalse(os.path.exists(args.output))

    def test_export_passes_with_seg_substitution_only(self) -> None:
        """cmd_export must NOT fail when sibling flavors only substitute a color name at the same SEG slot."""
        consistent_roles: dict[str, Any] = {
            "onedarkpro": {
                "_default_flavor": "onedark",
                "onedark": {
                    "_roles": {"SEG": ["red", "orange", "yellow", "green", "cyan", "purple"]}
                },
                "onedark_dark": {
                    "_roles": {"SEG": ["red", "orange", "yellow", "green", "blue", "purple"]}
                },
            }
        }
        roles_path = os.path.join(self.tmp, "consistent_roles.json")
        with open(roles_path, "w") as f:
            json.dump(consistent_roles, f)
        out_path = os.path.join(self.tmp, "consistent_out.json")
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=roles_path,
            output=out_path,
            verbose=False,
        )
        gc.cmd_export(args)
        self.assertTrue(os.path.exists(out_path))

    def test_export_blend_differentiates_flavors(self) -> None:
        """--blend should give affected flavors distinct SEG0 hex, DC_EXEC untouched."""
        blend_roles: dict[str, Any] = {
            "blendtheme": {
                "_default_flavor": "a",
                "_roles": {
                    "BG": "bg",
                    "TEXT": "bg",
                    "SEG": ["red", "orange", "yellow", "green", "cyan", "purple"],
                    "OK": "green",
                    "ERR": "red",
                    "WARN": "yellow",
                    "DC_EXEC": "green",
                },
                "a": {
                    "red": "#ff0000",
                    "orange": "#ff8800",
                    "yellow": "#ffff00",
                    "green": "#00ff00",
                    "cyan": "#00ffff",
                    "purple": "#8800ff",
                    # Distinct *lightness* between a/b — the mechanism ranks
                    # by BG lightness relative to the theme's flavors, hue is
                    # irrelevant now.
                    "bg": "#000000",
                },
                "b": {
                    "red": "#ff0000",
                    "orange": "#ff8800",
                    "yellow": "#ffff00",
                    "green": "#00ff00",
                    "cyan": "#00ffff",
                    "purple": "#8800ff",
                    "bg": "#ffffff",
                },
            }
        }
        roles_path = os.path.join(self.tmp, "blend_roles.json")
        with open(roles_path, "w") as f:
            json.dump(blend_roles, f)
        out_path = os.path.join(self.tmp, "blend_out.json")
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=roles_path,
            output=out_path,
            verbose=False,
            blend=True,
        )
        gc.cmd_export(args)
        data = json.loads(Path(out_path).read_text())
        theme = data["blendtheme"]
        # "a" is the first (sorted-order) holder of the shared color, so it
        # stays canonical/untouched — only "b" (the duplicate) gets reshaded.
        self.assertNotIn("_roles", theme["a"])
        seg0_b = theme["b"]["_roles"]["SEG"][0]
        self.assertNotEqual(theme["a"]["red"], theme["b"][seg0_b])
        # The original color name must be untouched (DC_EXEC shares "green" with OK).
        self.assertEqual(theme["a"]["green"], "#00ff00")
        self.assertEqual(theme["b"]["green"], "#00ff00")

    def test_export_no_blend_flag_leaves_values_unchanged(self) -> None:
        """Without --blend, an affected theme's flavors keep identical accent values."""
        blend_roles: dict[str, Any] = {
            "blendtheme": {
                "_default_flavor": "a",
                "_roles": {
                    "BG": "bg",
                    "TEXT": "bg",
                    "SEG": ["red1", "red2", "red3", "red4", "red5", "red6"],
                    "OK": "green",
                    "ERR": "red1",
                    "WARN": "red1",
                },
                "a": {
                    "red1": "#ff0000",
                    "red2": "#ff0000",
                    "red3": "#ff0000",
                    "red4": "#ff0000",
                    "red5": "#ff0000",
                    "red6": "#ff0000",
                    "green": "#00ff00",
                    "bg": "#000000",
                },
                "b": {
                    "red1": "#ff0000",
                    "red2": "#ff0000",
                    "red3": "#ff0000",
                    "red4": "#ff0000",
                    "red5": "#ff0000",
                    "red6": "#ff0000",
                    "green": "#00ff00",
                    "bg": "#ffffff",
                },
            }
        }
        roles_path = os.path.join(self.tmp, "blend_roles2.json")
        with open(roles_path, "w") as f:
            json.dump(blend_roles, f)
        out_path = os.path.join(self.tmp, "blend_out2.json")
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=roles_path,
            output=out_path,
            verbose=False,
            blend=False,
        )
        gc.cmd_export(args)
        data = json.loads(Path(out_path).read_text())
        theme = data["blendtheme"]
        self.assertNotIn("_roles", theme["a"])
        self.assertNotIn("_roles", theme["b"])
        self.assertEqual(theme["a"]["red1"], theme["b"]["red1"])

    def test_export_warns_when_affected_and_no_blend(self) -> None:
        """Without --blend, cmd_export logs a warning naming the affected theme."""
        blend_roles: dict[str, Any] = {
            "blendtheme": {
                "_default_flavor": "a",
                "_roles": {
                    "BG": "bg",
                    "TEXT": "bg",
                    "SEG": ["red1", "red2", "red3", "red4", "red5", "red6"],
                    "OK": "green",
                    "ERR": "red1",
                    "WARN": "red1",
                },
                "a": {
                    "red1": "#ff0000",
                    "red2": "#ff0000",
                    "red3": "#ff0000",
                    "red4": "#ff0000",
                    "red5": "#ff0000",
                    "red6": "#ff0000",
                    "green": "#00ff00",
                    "bg": "#000000",
                },
                "b": {
                    "red1": "#ff0000",
                    "red2": "#ff0000",
                    "red3": "#ff0000",
                    "red4": "#ff0000",
                    "red5": "#ff0000",
                    "red6": "#ff0000",
                    "green": "#00ff00",
                    "bg": "#ffffff",
                },
            }
        }
        roles_path = os.path.join(self.tmp, "blend_roles3.json")
        with open(roles_path, "w") as f:
            json.dump(blend_roles, f)
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=roles_path,
            output=os.path.join(self.tmp, "blend_out3.json"),
            verbose=False,
            blend=False,
        )
        with self.assertLogs(gc.logger, level="WARNING") as cm:
            gc.cmd_export(args)
        self.assertTrue(any("blendtheme" in msg for msg in cm.output))

    def test_export_blend_unaffected_theme_untouched(self) -> None:
        """--blend must be a no-op for a theme whose flavors already differ."""
        self._make_catppuccin()
        out_path = os.path.join(self.tmp, "unaffected_out.json")
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=self.roles_path,
            output=out_path,
            verbose=False,
            blend=True,
        )
        gc.cmd_export(args)
        data = json.loads(Path(out_path).read_text())
        self.assertNotIn("_roles", data["catppuccin"].get("frappe", {}))


# ── _find_identical_accent_themes / _apply_accent_blend ────────────────────────


class TestAccentBlendDetection(unittest.TestCase):
    def _theme(self, accent_a: str, accent_b: str) -> dict[str, Any]:
        return {
            "blendtheme": {
                "_roles": {
                    "BG": "bg",
                    "TEXT": "bg",
                    "SEG": ["accent1"] * 6,
                    "OK": "accent1",
                    "ERR": "accent1",
                    "WARN": "accent1",
                },
                "a": {"accent1": accent_a, "bg": "#000000"},
                "b": {"accent1": accent_b, "bg": "#ffffff"},
            }
        }

    def test_detects_identical_accents_across_flavors(self) -> None:
        # "a" is the first (sorted-order) holder of the shared color and is
        # left as the canonical, untouched one — only "b" is the duplicate.
        data = self._theme("#ff0000", "#ff0000")
        affected = gc._find_identical_accent_themes(data)
        self.assertEqual(affected, {"blendtheme": ["b"]})

    def test_does_not_flag_theme_with_differing_accents(self) -> None:
        data = self._theme("#ff0000", "#00ff00")
        affected = gc._find_identical_accent_themes(data)
        self.assertNotIn("blendtheme", affected)

    def test_flags_theme_when_only_seg0_matches(self) -> None:
        """SEG0 matching is the trigger — SEG1+ don't need to match too."""
        data: dict[str, Any] = {
            "blendtheme": {
                "_roles": {
                    "BG": "bg",
                    "TEXT": "bg",
                    "SEG": ["red", "orange", "yellow", "green", "cyan", "purple"],
                    "OK": "green",
                    "ERR": "red",
                    "WARN": "yellow",
                },
                "a": {
                    "red": "#ff0000",
                    "orange": "#ff8800",  # differs from b below
                    "yellow": "#ffff00",
                    "green": "#00ff00",
                    "cyan": "#00ffff",
                    "purple": "#8800ff",
                    "bg": "#000000",
                },
                "b": {
                    "red": "#ff0000",  # SEG0 matches a
                    "orange": "#112233",  # SEG1 does NOT match a
                    "yellow": "#ffff00",
                    "green": "#00ff00",
                    "cyan": "#00ffff",
                    "purple": "#8800ff",
                    "bg": "#ffffff",
                },
            }
        }
        affected = gc._find_identical_accent_themes(data)
        self.assertEqual(affected, {"blendtheme": ["b"]})

    def test_does_not_flag_when_seg0_itself_differs(self) -> None:
        """Even if SEG1-5/OK/ERR/WARN all match, differing SEG0 must not trigger."""
        data: dict[str, Any] = {
            "blendtheme": {
                "_roles": {
                    "BG": "bg",
                    "TEXT": "bg",
                    "SEG": ["red", "orange", "yellow", "green", "cyan", "purple"],
                    "OK": "green",
                    "ERR": "red",
                    "WARN": "yellow",
                },
                "a": {
                    "red": "#ff0000",
                    "orange": "#ff8800",
                    "yellow": "#ffff00",
                    "green": "#00ff00",
                    "cyan": "#00ffff",
                    "purple": "#8800ff",
                    "bg": "#000000",
                },
                "b": {
                    "red": "#123456",  # SEG0 differs
                    "orange": "#ff8800",
                    "yellow": "#ffff00",
                    "green": "#00ff00",
                    "cyan": "#00ffff",
                    "purple": "#8800ff",
                    "bg": "#ffffff",
                },
            }
        }
        affected = gc._find_identical_accent_themes(data)
        self.assertNotIn("blendtheme", affected)

    def test_skips_single_flavor_theme(self) -> None:
        data = self._theme("#ff0000", "#ff0000")
        del data["blendtheme"]["b"]
        affected = gc._find_identical_accent_themes(data)
        self.assertNotIn("blendtheme", affected)

    def test_skips_theme_with_missing_accent_hex(self) -> None:
        data = self._theme("#ff0000", "#ff0000")
        del data["blendtheme"]["a"]["accent1"]
        affected = gc._find_identical_accent_themes(data)
        self.assertNotIn("blendtheme", affected)

    def test_apply_accent_blend_mutates_toward_bg(self) -> None:
        # "a" is the first (sorted-order) holder of the shared color, left
        # completely untouched. Only "b" (the duplicate) gets reshaded, at
        # the high end of _ACCENT_LIGHTNESS_RANGE since its BG is the
        # lighter of the two.
        data = self._theme("#ff0000", "#ff0000")
        data["blendtheme"]["a"]["bg"] = "#101010"  # dark
        data["blendtheme"]["b"]["bg"] = "#e0e0e0"  # light
        gc._apply_accent_blend(data)
        self.assertNotIn("_roles", data["blendtheme"]["a"])
        self.assertFalse(data["blendtheme"]["a"]["_blended"])
        self.assertTrue(data["blendtheme"]["b"]["_blended"])
        seg0_b = data["blendtheme"]["b"]["_roles"]["SEG"][0]
        lo, hi = gc._ACCENT_LIGHTNESS_RANGE
        expected_b = gc._lightness_rank_blend("#ff0000", 1.0, lo, hi)
        self.assertEqual(data["blendtheme"]["b"][seg0_b], expected_b)
        self.assertEqual(data["blendtheme"]["a"]["accent1"], "#ff0000")
        self.assertNotEqual(data["blendtheme"]["b"][seg0_b], "#ff0000")
        # Hue/saturation preserved — still pure red (hue=0, full saturation).
        r, g, b = (int(expected_b[i : i + 2], 16) / 255 for i in (1, 3, 5))
        h, _l, s = colorsys.rgb_to_hls(r, g, b)
        self.assertAlmostEqual(h, 0.0, places=2)
        self.assertAlmostEqual(s, 1.0, places=2)

    def test_apply_accent_blend_shared_color_name_not_double_blended(self) -> None:
        """Every SEG slot pointing at the same name should blend once, not per-slot."""
        # _theme()'s SEG is ["accent1"] * 6 — all six slots share one name.
        # "a" stays canonical/untouched; "b" is the duplicate that gets reshaded.
        data = self._theme("#ff0000", "#ff0000")
        data["blendtheme"]["a"]["bg"] = "#101010"
        data["blendtheme"]["b"]["bg"] = "#e0e0e0"
        gc._apply_accent_blend(data)
        roles_b = data["blendtheme"]["b"]["_roles"]
        # All six SEG entries must resolve to the same blended entry, not six
        # separately-named (or compounded) ones.
        self.assertEqual(len(set(roles_b["SEG"])), 1)
        lo, hi = gc._ACCENT_LIGHTNESS_RANGE
        expected = gc._lightness_rank_blend("#ff0000", 1.0, lo, hi)
        self.assertEqual(data["blendtheme"]["b"][roles_b["SEG"][0]], expected)

    def test_apply_accent_blend_reshades_ok_err_warn_too(self) -> None:
        """OK/ERR/WARN are reshaded like SEG — safe since only lightness moves, hue stays put."""
        data = self._theme("#ff0000", "#ff0000")
        data["blendtheme"]["a"]["bg"] = "#101010"
        data["blendtheme"]["b"]["bg"] = "#e0e0e0"
        gc._apply_accent_blend(data)
        self.assertNotIn("_roles", data["blendtheme"]["a"])
        roles_b = data["blendtheme"]["b"]["_roles"]
        # OK/ERR/WARN and every SEG slot all originally pointed at "accent1"
        # — must all resolve to the same blended entry.
        self.assertIn("OK", roles_b)
        self.assertIn("ERR", roles_b)
        self.assertIn("WARN", roles_b)
        self.assertEqual(roles_b["OK"], roles_b["SEG"][0])
        self.assertEqual(roles_b["ERR"], roles_b["SEG"][0])
        self.assertEqual(roles_b["WARN"], roles_b["SEG"][0])
        # Hue/saturation preserved — still pure red.
        hexval = data["blendtheme"]["b"][roles_b["OK"]]
        r, g, b = (int(hexval[i : i + 2], 16) / 255 for i in (1, 3, 5))
        h, _l, s = colorsys.rgb_to_hls(r, g, b)
        self.assertAlmostEqual(h, 0.0, places=2)
        self.assertAlmostEqual(s, 1.0, places=2)

    def test_apply_accent_blend_reshades_dc_gc_roles_sharing_a_blended_name(self) -> None:
        """DC_*/GC_* roles that share a name with OK/SEG must land on the same
        blended entry — mirrors monokai's OK/DC_EXEC/GC_ADDED all -> accent4."""
        data = self._theme("#ff0000", "#ff0000")
        data["blendtheme"]["_roles"]["DC_EXEC"] = "accent1"
        data["blendtheme"]["_roles"]["GC_ADDED"] = "accent1"
        data["blendtheme"]["a"]["bg"] = "#101010"
        data["blendtheme"]["b"]["bg"] = "#e0e0e0"
        gc._apply_accent_blend(data)
        self.assertNotIn("_roles", data["blendtheme"]["a"])
        roles_b = data["blendtheme"]["b"]["_roles"]
        self.assertIn("DC_EXEC", roles_b)
        self.assertIn("GC_ADDED", roles_b)
        self.assertEqual(roles_b["DC_EXEC"], roles_b["SEG"][0])
        self.assertEqual(roles_b["GC_ADDED"], roles_b["SEG"][0])
        # Original "accent1" entry itself is never mutated in place.
        self.assertEqual(data["blendtheme"]["b"]["accent1"], "#ff0000")

    def test_apply_accent_blend_reshades_dc_gc_role_with_its_own_name(self) -> None:
        """A DC_*/GC_* role backed by a color name no SEG/OK/ERR/WARN role uses
        must still get its own blended entry, not be left stale."""
        data = self._theme("#ff0000", "#ff0000")
        data["blendtheme"]["_roles"]["DC_DIR"] = "dironly"
        data["blendtheme"]["a"]["dironly"] = "#0000ff"
        data["blendtheme"]["b"]["dironly"] = "#0000ff"
        data["blendtheme"]["a"]["bg"] = "#101010"
        data["blendtheme"]["b"]["bg"] = "#e0e0e0"
        gc._apply_accent_blend(data)
        roles_b = data["blendtheme"]["b"]["_roles"]
        self.assertIn("DC_DIR", roles_b)
        dc_name = roles_b["DC_DIR"]
        self.assertNotEqual(dc_name, "dironly")
        self.assertEqual(data["blendtheme"]["b"]["dironly"], "#0000ff")  # untouched
        lo, hi = gc._ACCENT_LIGHTNESS_RANGE
        expected = gc._lightness_rank_blend("#0000ff", 1.0, lo, hi)
        self.assertEqual(data["blendtheme"]["b"][dc_name], expected)

    def test_apply_accent_blend_logs_each_flavor_as_blended(self) -> None:
        """Each blended flavor gets its own log line as it happens — no
        grouped/summarized rollup line."""
        data = self._theme("#ff0000", "#ff0000")
        data["blendtheme"]["a"]["bg"] = "#101010"
        data["blendtheme"]["b"]["bg"] = "#e0e0e0"
        with self.assertLogs(gc.logger, level="INFO") as cm:
            gc._apply_accent_blend(data)
        self.assertEqual(cm.output, ["INFO:get-colors:blended: blendtheme/b"])

    def test_apply_accent_blend_catches_chain_collision(self) -> None:
        """A blend result that coincidentally matches a later flavor's original
        color must flag that later flavor too — not just the first duplicate."""
        data: dict[str, Any] = {
            "blendtheme": {
                "_roles": {
                    "BG": "bg",
                    "TEXT": "bg",
                    "SEG": ["accent1"] * 6,
                    "OK": "accent1",
                    "ERR": "accent1",
                    "WARN": "accent1",
                },
                "a": {"accent1": "#ff0000", "bg": "#000000"},
                "b": {"accent1": "#ff0000", "bg": "#e0e0e0"},
                # c's original color is engineered to equal exactly what b's
                # blend result becomes — must still get flagged/reshaded even
                # though c's raw value never collided with a's original.
                "c": {"accent1": None, "bg": "#808080"},  # placeholder, set below
            }
        }
        lo, hi = gc._ACCENT_LIGHTNESS_RANGE
        # b is the lightest bg among a/b/c so far when b is processed (only a
        # is "seen" then) — compute what b will actually become once a/b/c's
        # bg range is known, then plant that exact value on c.
        bgs = {"a": "#000000", "b": "#e0e0e0", "c": "#808080"}
        b_l, lo_bg, hi_bg = (
            gc._hex_lightness(bgs["b"]),
            min(gc._hex_lightness(v) for v in bgs.values()),
            max(gc._hex_lightness(v) for v in bgs.values()),
        )
        b_normalized = (b_l - lo_bg) / (hi_bg - lo_bg)
        planted = gc._lightness_rank_blend("#ff0000", b_normalized, lo, hi)
        data["blendtheme"]["c"]["accent1"] = planted

        blended = gc._apply_accent_blend(data)
        self.assertEqual(blended, {"blendtheme": ["b", "c"]})
        self.assertNotIn("_roles", data["blendtheme"]["a"])


# ── _make_swatch_png / _ensure_swatch_png ──────────────────────────────────────


class TestSwatchPng(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_png_has_valid_signature(self) -> None:
        """Generated bytes must start with the standard 8-byte PNG signature."""
        png = gc._make_swatch_png("#c72a3c")
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_png_contains_requested_color(self) -> None:
        """Decoding the raw IDAT scanlines should reproduce the requested RGB."""
        import zlib

        png = gc._make_swatch_png("#ff0080", width=4, height=3)
        # Locate IDAT chunk body: skip signature + IHDR chunk, then read IDAT.
        idat_start = png.index(b"IDAT") + 4
        # length is the 4 bytes right before the "IDAT" tag
        length = int.from_bytes(png[png.index(b"IDAT") - 4 : png.index(b"IDAT")], "big")
        raw = zlib.decompress(png[idat_start : idat_start + length])
        # First byte of first scanline is the filter type (0); next 3 are R,G,B.
        self.assertEqual(raw[0], 0)
        self.assertEqual(tuple(raw[1:4]), (0xFF, 0x00, 0x80))

    def test_ensure_swatch_png_writes_file_once(self) -> None:
        """A second call for the same hex should not rewrite the existing file."""
        swatch_dir = os.path.join(self.tmp, "swatches")
        name1 = gc._ensure_swatch_png("#abcdef", swatch_dir)
        path = os.path.join(swatch_dir, "abcdef.png")
        mtime1 = os.path.getmtime(path)
        name2 = gc._ensure_swatch_png("#abcdef", swatch_dir)
        self.assertEqual(name1, "abcdef.png")
        self.assertEqual(name1, name2)
        self.assertEqual(os.path.getmtime(path), mtime1)

    def test_ensure_swatch_png_rejects_invalid_hex(self) -> None:
        """Empty or malformed hex strings should return None, not raise."""
        swatch_dir = os.path.join(self.tmp, "swatches")
        self.assertIsNone(gc._ensure_swatch_png("", swatch_dir))
        self.assertIsNone(gc._ensure_swatch_png("not-a-color", swatch_dir))
        self.assertIsNone(gc._ensure_swatch_png("#fff", swatch_dir))

    def test_swatch_renders_img_tag_and_hex_text(self) -> None:
        """_swatch should embed an <img> pointing at .assets/swatches plus backtick hex,
        with the image and hex text on separate lines via <br/>."""
        swatch_dir = os.path.join(self.tmp, "swatches")
        result = gc._swatch("#112233", swatch_dir)
        self.assertIn('src=".assets/swatches/112233.png"', result)
        self.assertIn("`#112233`", result)
        self.assertIn("<br/>", result)
        self.assertTrue(result.index("<br/>") < result.index("`#112233`"))

    def test_swatch_empty_returns_em_dash(self) -> None:
        swatch_dir = os.path.join(self.tmp, "swatches")
        self.assertEqual(gc._swatch("", swatch_dir), "—")


# ── _write_colors_md ─────────────────────────────────────────────────────────────


class TestWriteColorsMd(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.out_path = os.path.join(self.tmp, "COLORS.md")
        self.data: dict[str, Any] = {
            "monokai": {
                "_roles": {
                    "SEG": ["red", "orange", "purple", "green", "cyan", "yellow"],
                    "BG": "bg0",
                    "TEXT": "fg",
                    "DC_DIR": "cyan",
                    "GC_ADDED": "green",
                },
                "spectrum": {
                    "red": "#fc618d",
                    "orange": "#fd9353",
                    "purple": "#948ae3",
                    "green": "#7bd88f",
                    "cyan": "#5ad4e6",
                    "yellow": "#fce566",
                    "bg0": "#222222",
                    "fg": "#f7f1ff",
                    "unused1": "#abcdef",
                },
            }
        }

    def test_elements_table_has_seg_columns_and_two_legend_rows(self) -> None:
        """Header is seg0..seg5 plus single-purpose bg/text/fg/ok/err/warn columns
        (each one swatch, same as seg0-5 — no combined/side-by-side cell); main-line
        and stats-line legend rows follow."""
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertIn(
            "| Flavor | seg0 | seg1 | seg2 | seg3 | seg4 | seg5 | bg | text | fg | ok | err "
            "| warn |",
            content,
        )
        self.assertIn(
            "| *(main line)* | os | dir | git | lang | tools | time | user/hostname "
            "| user/hostname | pill text | ❯ ok | ❯ err | ❯ warn |",
            content,
        )
        self.assertIn(
            "| *(stats line)* | shell<br/>sudo<br/>shlvl<br/>env_var | memory | cpu | disk "
            "| duration | battery<br/>status<br/>jobs | - | - | pill text | - | - | - |",
            content,
        )
        self.assertNotIn("*(slot)*", content)

    def test_elements_row_embeds_swatch_images(self) -> None:
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertIn('src=".assets/swatches/fc618d.png"', content)
        self.assertIn("`#fc618d`", content)
        # swatch PNGs actually written to disk next to COLORS.md
        self.assertTrue(os.path.exists(os.path.join(self.tmp, ".assets/swatches/fc618d.png")))

    def test_elements_bg_text_are_separate_single_swatch_columns(self) -> None:
        """bg and text are independent columns, each a plain single swatch
        (same shape as seg0-5) — no combined/flex-wrapped cell."""
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertNotIn("display: inline-flex", content)
        self.assertIn(
            '<img src=".assets/swatches/222222.png" width="60" height="15" alt="#222222">'
            "<br/>`#222222`",
            content,
        )
        self.assertIn(
            '<img src=".assets/swatches/f7f1ff.png" width="60" height="15" alt="#f7f1ff">'
            "<br/>`#f7f1ff`",
            content,
        )

    def test_elements_fg_ok_err_warn_columns_present(self) -> None:
        """fg/ok/err/warn each get their own Elements column; unresolved ones
        (not set in this fixture's _roles) render as em-dash, not an error."""
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertIn("| bg | text | fg | ok | err | warn |", content)
        # This fixture's _roles has no FG/OK/ERR/WARN — those columns should
        # gracefully show "—", not raise or leave the row short.
        self.assertIn("`#f7f1ff` | — | — | — | — |", content)

    def test_dircolors_and_gitcolors_are_separate_tables(self) -> None:
        """DirColors (DC_*) and GitColors (GC_*) render as two independent
        tables/sections, not one combined table."""
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertIn("### DirColors", content)
        self.assertIn("### GitColors", content)
        self.assertIn("| Flavor | DC_DIR |", content)
        self.assertIn("| Flavor | GC_ADDED |", content)
        self.assertNotIn("DC_DIR | GC_ADDED", content)  # never in the same table header
        self.assertIn('src=".assets/swatches/5ad4e6.png"', content)  # DC_DIR -> cyan
        self.assertIn('src=".assets/swatches/7bd88f.png"', content)  # GC_ADDED -> green
        self.assertIn("[DirColors](#monokai-dircolors)", content)
        self.assertIn("[GitColors](#monokai-gitcolors)", content)

    def test_accent_ranking_skipped_without_nvim_metadata(self) -> None:
        """No `_nvim` metadata on the theme (this fixture's case) — section still
        prints, with an explicit skipped note instead of a table."""
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertIn("### Accent Ranking", content)
        self.assertIn("nvim not available or no `_nvim` metadata", content)

    @patch.object(gc, "_find_nvim_init", return_value="/fake/init.lua")
    @patch.object(gc, "_capture_flavor_highlights")
    def test_accent_ranking_orders_by_rank_and_marks_used(
        self, mock_capture: Any, mock_find_init: Any
    ) -> None:
        """Colors are ranked by captured highlight-group weight; Used reflects
        whether SEG/DC_*/GC_* roles reference that color name."""
        self.data["monokai"]["_nvim"] = {"theme": "monokai-pro", "variant_key": "monokai_filter"}
        # "unused1" (a Tier 1 group) outranks "red" (a Tier 3 group) despite
        # "red" being referenced by SEG/roles — rank is purely usage-derived.
        mock_capture.return_value = {
            "Normal": {"fg": 0xABCDEF, "bg": None, "sp": None},
            "SomePluginGroup": {"fg": 0xFC618D, "bg": None, "sp": None},
        }
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertIn('<summary><span style="font-size: 1.1em', content)
        self.assertIn("Accent Ranking (1 flavors)</span></summary>", content)
        self.assertIn(
            '<details style="margin-left: 1.25rem">\n<summary><span style="font-size: 1.02em',
            content,
        )
        self.assertIn("spectrum</span></summary>", content)
        self.assertIn("<summary>Used (8 colors)</summary>", content)
        self.assertIn("<summary>Unused (1 colors)</summary>", content)
        # "unused1" (a Tier 1 group) outranks "red" (a Tier 3 group) despite
        # "red" being referenced by SEG/roles — rank is purely usage-derived,
        # but "unused1" still lands in the Unused table since roles don't
        # reference it. Used table gets the extra "Used" category column;
        # "red" is referenced only via SEG.
        # Unused table has no Blended/Original columns — a `__blend` entry only
        # exists because a role got repointed at it, so it's always Used.
        self.assertIn("| 1 | Tier 1 | unused1 | `#abcdef` |", content)
        self.assertIn("| 2 | Tier 3 | red | no | `#fc618d` |", content)
        # No blockquote markers — nesting comes from inline margin-left, not `>`.
        ranking_section = content.rsplit("Accent Ranking (1 flavors)</span></summary>", 1)[1]
        self.assertFalse(any(line.startswith(">") for line in ranking_section.splitlines()))
        self.assertIn(
            "| Rank | Group Tier | Color | Blended | Hex | Swatch | Original | Og Hex | Used |",
            content,
        )
        self.assertIn("| Rank | Group Tier | Color | Hex | Swatch |", content)
        self.assertIn("| — | SEG0 |", content)  # "red": not blended (Original "—"), via SEG0
        # Swatch column has no hex text below the image (already its own column).
        self.assertNotIn("<br/>`#fc618d`", ranking_section)
        mock_capture.assert_called_with(self.data["monokai"]["_nvim"], "spectrum", "/fake/init.lua")

    @patch.object(gc, "_find_nvim_init", return_value="/fake/init.lua")
    @patch.object(gc, "_capture_flavor_highlights")
    def test_accent_ranking_marks_blend_generated_entries(
        self, mock_capture: Any, mock_find_init: Any
    ) -> None:
        """A `{name}__blend` palette entry displays as its base name, Blended=yes,
        Hex/Swatch showing the blended value, and Original a swatch plus the
        raw "Og Hex" of the pre-blend hex (still present in palettes.json under
        the base name — `_blend_color_name` never deletes or mutates it). Since
        a role always gets repointed at the new `__blend` entry, it's Used, not
        Unused — the original "red" entry itself is what ends up Unused
        (Blended/Original/Og Hex columns don't apply there)."""
        self.data["monokai"]["_nvim"] = {"theme": "monokai-pro", "variant_key": "monokai_filter"}
        self.data["monokai"]["spectrum"]["red__blend"] = "#123456"
        # Point SEG's "red" slot at the new blended entry, mirroring what
        # _apply_accent_blend's override actually does.
        self.data["monokai"]["spectrum"]["_roles"] = {
            "SEG": ["red__blend", "orange", "purple", "green", "cyan", "yellow"]
        }
        mock_capture.return_value = {}
        gc._write_colors_md(self.data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        # Displayed as "red" (not "red__blend"), Blended=yes, Hex=blended value.
        self.assertIn("| red | yes | `#123456` |", content)
        # Original column: a swatch of the pre-blend hex (#fc618d), not its name;
        # Og Hex column: the raw pre-blend hex text, backtick-wrapped.
        self.assertIn(
            'alt="#123456"> | <img src=".assets/swatches/fc618d.png" width="60" height="15" '
            'alt="#fc618d"> | `#fc618d` |',
            content,
        )
        self.assertNotIn("red__blend", content)
        # The un-blended "red" entry itself now lands in Unused, with no
        # Blended/Original columns.
        self.assertIn("Unused (2 colors)", content)

    def test_flavor_with_no_palette_shows_no_colors_message(self) -> None:
        """An nvim-only flavor (no terminal palette) should produce the fallback message."""
        data: dict[str, Any] = {
            "nvimonly": {
                "_roles": {"SEG": ["a"], "BG": "a", "TEXT": "a"},
                "dark": {"_nvim": {"theme": "x"}},
            }
        }
        gc._write_colors_md(data, self.out_path)
        content = Path(self.out_path).read_text(encoding="utf-8")
        self.assertIn("*(no terminal colors for any flavor of this theme)*", content)

    def test_stale_swatches_removed_on_regeneration(self) -> None:
        """A swatch left over from a color no longer in use must not survive a rerun."""
        swatch_dir = os.path.join(self.tmp, ".assets", "swatches")
        os.makedirs(swatch_dir, exist_ok=True)
        stale_path = os.path.join(swatch_dir, "deadbee.png")
        Path(stale_path).write_bytes(b"stale")
        gc._write_colors_md(self.data, self.out_path)
        self.assertFalse(os.path.exists(stale_path))
        # A swatch actually referenced by self.data must still be regenerated.
        self.assertTrue(os.path.exists(os.path.join(swatch_dir, "fc618d.png")))


# ── _validate_seg_roles ─────────────────────────────────────────────────────────


class TestValidateSegRoles(unittest.TestCase):
    def test_no_error_for_single_flavor_theme(self) -> None:
        """A theme with only one flavor has nothing to compare against."""
        data = {"solo": {"only": {"_roles": {"SEG": ["red", "green"]}}}}
        self.assertEqual(gc._validate_seg_roles(data), [])

    def test_no_error_for_same_slot_substitution(self) -> None:
        """Different color name at the same index across flavors is allowed (identity anchor pattern)."""
        data = {
            "tokyonight": {
                "night": {"_roles": {"SEG": ["red", "green", "cyan"]}},
                "storm": {"_roles": {"SEG": ["red", "green", "teal"]}},
            }
        }
        self.assertEqual(gc._validate_seg_roles(data), [])

    def test_detects_moved_value_between_slots(self) -> None:
        """A shared color name appearing at a different index is flagged as drift."""
        data = {
            "onedarkpro": {
                "onedark": {"_roles": {"SEG": ["red", "orange", "cyan", "purple"]}},
                "onedark_vivid": {"_roles": {"SEG": ["red", "purple", "cyan", "orange"]}},
            }
        }
        errors = gc._validate_seg_roles(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("onedarkpro", errors[0])
        self.assertIn("onedark_vivid", errors[0])

    def test_detects_length_mismatch(self) -> None:
        """Sibling SEG arrays of different lengths are flagged rather than silently compared."""
        data = {
            "sometheme": {
                "a": {"_roles": {"SEG": ["red", "green"]}},
                "b": {"_roles": {"SEG": ["red", "green", "blue"]}},
            }
        }
        errors = gc._validate_seg_roles(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("length mismatch", errors[0])

    def test_falls_back_to_theme_level_roles(self) -> None:
        """Flavors without their own _roles inherit the theme-level _roles and are still checked."""
        data = {
            "shared": {
                "_roles": {"SEG": ["red", "green"]},
                "a": {},
                "b": {},
            }
        }
        self.assertEqual(gc._validate_seg_roles(data), [])

    def test_ignores_underscore_keys_and_non_dict_values(self) -> None:
        """Metadata keys like _default_flavor must not be treated as flavors."""
        data = {
            "theme": {
                "_default_flavor": "a",
                "a": {"_roles": {"SEG": ["red", "green"]}},
                "b": {"_roles": {"SEG": ["red", "green"]}},
            }
        }
        self.assertEqual(gc._validate_seg_roles(data), [])


# ── _merge_roles ─────────────────────────────────────────────────────────────


class TestMergeRoles(unittest.TestCase):
    def test_flavor_with_no_override_inherits_theme_defaults(self) -> None:
        """A flavor with no _roles at all (None) resolves to the theme defaults unchanged."""
        theme = {"BG": "bg", "SEG": ["red", "green"]}
        self.assertEqual(gc._merge_roles(theme, None), theme)

    def test_flavor_fully_overrides_every_key(self) -> None:
        """A flavor _roles that repeats every theme key still resolves correctly (legacy full-copy style)."""
        theme = {"BG": "bg", "SEG": ["red", "green"]}
        flavor = {"BG": "bg2", "SEG": ["blue", "yellow"]}
        self.assertEqual(gc._merge_roles(theme, flavor), flavor)

    def test_flavor_partial_override_inherits_missing_keys(self) -> None:
        """A flavor _roles with only one key still inherits every other key from the theme default."""
        theme = {"BG": "bg", "TEXT": "fg", "SEG": ["red", "green", "blue"]}
        flavor = {"SEG": ["yellow", "purple", "cyan"]}
        merged = gc._merge_roles(theme, flavor)
        self.assertEqual(merged, {"BG": "bg", "TEXT": "fg", "SEG": ["yellow", "purple", "cyan"]})

    def test_empty_theme_and_flavor_roles_yields_empty_dict(self) -> None:
        """No theme defaults and no flavor override resolves to an empty roles dict."""
        self.assertEqual(gc._merge_roles({}, None), {})

    def test_real_onedarkpro_flavor_inherits_dc_and_gc_roles_from_theme(self) -> None:
        """Regression guard: onedarkpro's per-flavor _roles only declares SEG; DC_*/GC_* must still resolve via the theme default after the de-duplication refactor."""
        roles_path = os.path.join(
            os.path.dirname(os.path.abspath(gc.__file__)), ".config", "roles.json"
        )
        with open(roles_path, encoding="utf-8") as f:
            roles = json.load(f)
        theme_roles = roles["onedarkpro"]["_roles"]
        flavor_roles = roles["onedarkpro"]["onedark"]["_roles"]
        self.assertEqual(set(flavor_roles.keys()), {"SEG"})
        merged = gc._merge_roles(theme_roles, flavor_roles)
        self.assertEqual(merged["DC_DIR"], "cyan")
        self.assertEqual(merged["GC_BRANCH"], "cyan")
        self.assertEqual(merged["SEG"], ["red", "orange", "purple", "green", "cyan", "yellow"])


# ── cmd_matrix auto-detect ─────────────────────────────────────────────────────


class TestCmdMatrixAutoDetect(unittest.TestCase):
    def test_autodetect_finds_palettes_json(self) -> None:
        """When palettes=None the function auto-detects src/.config/palettes.json."""
        args = argparse.Namespace(
            palettes=None,
            prompt=False,
            colors=False,
            theme=None,
            flavor="",
            themes_dir=tempfile.mkdtemp(),
            verbose=False,
        )
        with patch("sys.stdout", new_callable=StringIO) as out:
            gc.cmd_matrix(args)
        # The real palettes.json has themes in it — output should be non-trivial
        self.assertIn("theme/flavor", out.getvalue())


# ── _setup_logging ─────────────────────────────────────────────────────────────


class TestSetupLogging(unittest.TestCase):
    def test_no_exception_verbose(self) -> None:
        gc._setup_logging(verbose=True)

    def test_no_exception_default(self) -> None:
        gc._setup_logging(verbose=False)


# ── _ColorFormatter ────────────────────────────────────────────────────────────


class TestColorFormatter(unittest.TestCase):
    def test_formats_with_color(self) -> None:
        import logging

        fmt = gc._ColorFormatter("%(message)s")
        record = logging.LogRecord("test", logging.ERROR, "", 0, "oops", (), None)
        result = fmt.format(record)
        self.assertIn("\033[31m", result)  # red for error
        self.assertIn("\033[0m", result)

    def test_info_color(self) -> None:
        import logging

        fmt = gc._ColorFormatter("%(message)s")
        record = logging.LogRecord("test", logging.INFO, "", 0, "info", (), None)
        result = fmt.format(record)
        self.assertIn("\033[32m", result)  # green for info

    def test_unknown_level_no_color(self) -> None:
        import logging

        fmt = gc._ColorFormatter("%(message)s")
        record = logging.LogRecord("test", 99, "", 0, "x", (), None)
        result = fmt.format(record)
        self.assertNotIn("\033[", result)


# ── main() entry point ─────────────────────────────────────────────────────────


class TestMain(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_main_show_dispatches(self) -> None:
        with (
            patch("sys.argv", ["get-colors.py", "--show", "--theme", "gruvbox"]),
            patch.object(gc, "cmd_show") as mock_show,
        ):
            gc.main()
        mock_show.assert_called_once()

    def test_main_matrix_dispatches(self) -> None:
        with (
            patch("sys.argv", ["get-colors.py", "--matrix"]),
            patch.object(gc, "cmd_matrix") as mock_matrix,
        ):
            gc.main()
        mock_matrix.assert_called_once()

    def test_main_palette_dispatches(self) -> None:
        with (
            patch(
                "sys.argv", ["get-colors.py", "--palette", "--theme", "gruvbox", "--flavor", "dark"]
            ),
            patch.object(gc, "cmd_palette") as mock_pal,
        ):
            gc.main()
        mock_pal.assert_called_once()

    def test_main_export_dispatches(self) -> None:
        with (
            patch("sys.argv", ["get-colors.py", "--export"]),
            patch.object(gc, "cmd_export") as mock_exp,
        ):
            gc.main()
        mock_exp.assert_called_once()

    def test_main_no_action_exits(self) -> None:
        with patch("sys.argv", ["get-colors.py"]), self.assertRaises(SystemExit):
            gc.main()


if __name__ == "__main__":
    unittest.main()
