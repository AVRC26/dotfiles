"""Unit tests for get-colors.py."""

from __future__ import annotations

import argparse
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
        # The module auto-detects src/.config/roles.json (committed to repo) —
        # pass roles=None and a real output path so the function runs end-to-end.
        args = argparse.Namespace(
            themes_dir=self.tmp,
            roles=None,
            output=out_path,
            verbose=False,
        )
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
