"""Unit tests for render-theme.py."""

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

# Load the module from its hyphenated filename
_SRC = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("render_theme", _SRC / ".config" / "render-theme.py")
assert spec is not None
assert spec.loader is not None
rt: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)


# ── Fixtures ───────────────────────────────────────────────────────────────────

MINIMAL_PALETTES: dict[str, Any] = {
    "monokai": {
        "_default_flavor": "spectrum",
        "_nvim": {"theme": "monokai-pro", "variant_key": "monokaipro_filter"},
        "_roles": {
            "SEG": ["accent1", "accent2", "accent3", "accent4", "accent5", "accent6"],
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
            "accent3": "#fce566",
            "accent4": "#7bd88f",
            "accent5": "#5ad4e6",
            "accent6": "#948ae3",
            "base": "#f7f1ff",
        },
    },
    "catppuccin": {
        "_default_flavor": "mocha",
        "_nvim": {"theme": "catppuccin"},
        "_roles": {
            "SEG": ["mauve", "blue", "green", "yellow", "peach", "red"],
            "FG": "text",
            "OK": "green",
            "ERR": "red",
            "WARN": "yellow",
        },
        "mocha": {
            "mauve": "#cba6f7",
            "blue": "#89b4fa",
            "green": "#a6e3a1",
            "yellow": "#f9e2af",
            "peach": "#fab387",
            "red": "#f38ba8",
            "text": "#cdd6f4",
        },
    },
}


def make_palettes_file(tmp: str, data: dict[str, Any] | None = None) -> str:
    path = os.path.join(tmp, "palettes.json")
    with open(path, "w") as f:
        json.dump(data or MINIMAL_PALETTES, f)
    return path


def make_template(tmp: str, name: str, content: str) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write(content)
    return path


def make_render_args(
    tmp: str, pal: str, theme: str = "monokai", flavor: str = "spectrum"
) -> argparse.Namespace:
    return argparse.Namespace(
        palette=pal,
        theme=theme,
        flavor=flavor,
        sep=">",
        starship_template=os.path.join(tmp, "starship.tmpl"),
        starship_output=os.path.join(tmp, "starship.toml"),
        dircolors_template=os.path.join(tmp, "dircolors.tmpl"),
        dircolors_output=os.path.join(tmp, "dircolors"),
        git_template=os.path.join(tmp, "git.tmpl"),
        git_output=os.path.join(tmp, "git.conf"),
        nvim=None,
    )


# ── _validate_hex ──────────────────────────────────────────────────────────────


class TestValidateHex(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertTrue(rt._validate_hex("#fc618d"))
        self.assertTrue(rt._validate_hex("#000000"))
        self.assertTrue(rt._validate_hex("#ffffff"))
        self.assertTrue(rt._validate_hex("#ABCDEF"))

    def test_invalid_format(self) -> None:
        self.assertFalse(rt._validate_hex("fc618d"))  # no #
        self.assertFalse(rt._validate_hex("#fc618"))  # too short
        self.assertFalse(rt._validate_hex("#fc618dff"))  # too long
        self.assertFalse(rt._validate_hex("#gggggg"))  # not hex
        self.assertFalse(rt._validate_hex(""))
        self.assertFalse(rt._validate_hex(None))
        self.assertFalse(rt._validate_hex(123))


# ── _hex_to_rgb_escape ─────────────────────────────────────────────────────────


class TestHexToRgb(unittest.TestCase):
    def test_black(self) -> None:
        self.assertEqual(rt._hex_to_rgb_escape("#000000"), "38;2;0;0;0")

    def test_white(self) -> None:
        self.assertEqual(rt._hex_to_rgb_escape("#ffffff"), "38;2;255;255;255")

    def test_color(self) -> None:
        self.assertEqual(rt._hex_to_rgb_escape("#fc618d"), "38;2;252;97;141")

    def test_invalid_returns_fallback(self) -> None:
        self.assertEqual(rt._hex_to_rgb_escape("bad"), "38;2;128;128;128")
        self.assertEqual(rt._hex_to_rgb_escape(""), "38;2;128;128;128")


# ── _load_palette ──────────────────────────────────────────────────────────────


class TestLoadPalette(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_valid(self) -> None:
        path = make_palettes_file(self.tmp)
        data = rt._load_palette(path)
        self.assertIn("monokai", data)

    def test_missing_file(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            rt._load_palette("/nonexistent/palettes.json")
        self.assertEqual(ctx.exception.code, 2)

    def test_invalid_json(self) -> None:
        path = os.path.join(self.tmp, "bad.json")
        with open(path, "w") as f:
            f.write("{not valid json")
        with self.assertRaises(SystemExit) as ctx:
            rt._load_palette(path)
        self.assertEqual(ctx.exception.code, 2)

    def test_non_dict_json(self) -> None:
        path = os.path.join(self.tmp, "list.json")
        with open(path, "w") as f:
            json.dump([1, 2, 3], f)
        with self.assertRaises(SystemExit) as ctx:
            rt._load_palette(path)
        self.assertEqual(ctx.exception.code, 2)


# ── _resolve_theme_flavor ──────────────────────────────────────────────────────


class TestResolveThemeFlavor(unittest.TestCase):
    def setUp(self) -> None:
        self.data = MINIMAL_PALETTES

    def test_valid_explicit_flavor(self) -> None:
        _, f, flavor = rt._resolve_theme_flavor(self.data, "monokai", "spectrum")
        self.assertEqual(flavor, "spectrum")
        self.assertIn("accent1", f)

    def test_default_flavor(self) -> None:
        _, _, flavor = rt._resolve_theme_flavor(self.data, "monokai", "")
        self.assertEqual(flavor, "spectrum")  # _default_flavor

    def test_unknown_theme_exits(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            rt._resolve_theme_flavor(self.data, "nonexistent", "")
        self.assertEqual(ctx.exception.code, 1)

    def test_unknown_flavor_exits(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            rt._resolve_theme_flavor(self.data, "monokai", "ghost")
        self.assertEqual(ctx.exception.code, 1)


# ── _atomic_write ──────────────────────────────────────────────────────────────


class TestAtomicWrite(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_creates_file(self) -> None:
        path = os.path.join(self.tmp, "out.txt")
        rt._atomic_write(path, "hello world")
        self.assertEqual(Path(path).read_text(), "hello world")

    def test_creates_nested_dirs(self) -> None:
        path = os.path.join(self.tmp, "a", "b", "c.txt")
        rt._atomic_write(path, "deep")
        self.assertTrue(os.path.exists(path))

    def test_overwrites_existing(self) -> None:
        path = os.path.join(self.tmp, "out.txt")
        rt._atomic_write(path, "v1")
        rt._atomic_write(path, "v2")
        self.assertEqual(Path(path).read_text(), "v2")


# ── _render_template ───────────────────────────────────────────────────────────


class TestRenderTemplate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_substitution(self) -> None:
        tmpl = make_template(self.tmp, "t.tmpl", "color = {{MY_COLOR}}")
        out = os.path.join(self.tmp, "out.txt")
        rt._render_template(tmpl, out, {"MY_COLOR": "#ff0000"})
        self.assertEqual(Path(out).read_text(), "color = #ff0000")

    def test_multiple_substitutions(self) -> None:
        tmpl = make_template(self.tmp, "t.tmpl", "a={{A}} b={{B}}")
        out = os.path.join(self.tmp, "out.txt")
        rt._render_template(tmpl, out, {"A": "1", "B": "2"})
        self.assertEqual(Path(out).read_text(), "a=1 b=2")

    def test_missing_template_exits(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            rt._render_template("/no/such/tmpl", "/tmp/out", {})
        self.assertEqual(ctx.exception.code, 2)


# ── _write_nvim_theme ──────────────────────────────────────────────────────────


class TestWriteNvimTheme(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_basic(self) -> None:
        t = {"_nvim": {"theme": "monokai-pro", "variant_key": "filter"}}
        path = os.path.join(self.tmp, "theme.lua")
        rt._write_nvim_theme(t, "spectrum", path)
        content = Path(path).read_text()
        self.assertIn('vim.g.active_theme = "monokai-pro"', content)
        self.assertIn('vim.g.filter = "spectrum"', content)

    def test_no_variant_key(self) -> None:
        t = {"_nvim": {"theme": "catppuccin"}}
        path = os.path.join(self.tmp, "theme.lua")
        rt._write_nvim_theme(t, "mocha", path)
        content = Path(path).read_text()
        self.assertIn('vim.g.active_theme = "catppuccin"', content)
        self.assertNotIn("vim.g.", content.replace("vim.g.active_theme", ""))

    def test_no_nvim_key(self) -> None:
        t: dict[str, Any] = {}
        path = os.path.join(self.tmp, "theme.lua")
        rt._write_nvim_theme(t, "dark", path)
        content = Path(path).read_text()
        self.assertIn("vim.g.active_theme", content)


# ── _apply_templates ───────────────────────────────────────────────────────────


class TestApplyTemplates(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.pal = make_palettes_file(self.tmp)

    def _make_args(self, theme: str = "monokai", flavor: str = "spectrum") -> argparse.Namespace:
        make_template(
            self.tmp, "starship.tmpl", "sep={{SEP_TRANS}} fg={{COLOR_FG}} seg0={{COLOR_SEG0}}"
        )
        make_template(self.tmp, "dircolors.tmpl", "dir={{DC_DIR}}")
        make_template(self.tmp, "git.tmpl", "added={{GC_ADDED}}")
        return make_render_args(self.tmp, self.pal, theme, flavor)

    def test_starship_rendered(self) -> None:
        args = self._make_args()
        data = rt._load_palette(args.palette)
        t, f, _ = rt._resolve_theme_flavor(data, "monokai", "spectrum")
        rt._apply_templates(t, f, ">", args)
        content = Path(args.starship_output).read_text()
        self.assertIn("sep=>", content)
        self.assertIn("fg=#f7f1ff", content)
        self.assertIn("seg0=#fc618d", content)

    def test_dircolors_rendered(self) -> None:
        args = self._make_args()
        data = rt._load_palette(args.palette)
        t, f, _ = rt._resolve_theme_flavor(data, "monokai", "spectrum")
        rt._apply_templates(t, f, ">", args)
        content = Path(args.dircolors_output).read_text()
        self.assertIn("38;2;", content)  # DC_DIR hex converted to RGB

    def test_terminal_fallback_renders_from_fallback(self) -> None:
        """Nvim-only flavor with _terminal_fallback should render using fallback's colors."""
        data: dict[str, Any] = {
            "monokai": {
                "_roles": {
                    "SEG": ["accent1"],
                    "FG": "base",
                    "OK": "accent1",
                    "ERR": "accent1",
                    "WARN": "accent1",
                    "DC_DIR": "accent1",
                    "GC_ADDED": "accent1",
                    "BG": "base",
                    "TEXT": "base",
                },
                "spectrum": {
                    "accent1": "#fc618d",
                    "base": "#f7f1ff",
                },
                "day": {
                    "_terminal_fallback": "spectrum",
                },
            }
        }
        args = self._make_args()
        theme_dict = data["monokai"]
        day_dict = theme_dict["day"]
        rt._apply_templates(theme_dict, day_dict, ">", args)
        content = Path(args.starship_output).read_text()
        # Should render spectrum's colors, not empty
        self.assertIn("#fc618d", content)

    def test_nvimonly_without_fallback_skips(self) -> None:
        """Nvim-only flavor with no _terminal_fallback should skip template rendering."""
        args = self._make_args()
        flavor_dict: dict[str, Any] = {"_nvim": {"theme": "monokai-pro"}}
        theme_dict: dict[str, Any] = MINIMAL_PALETTES["monokai"]
        rt._apply_templates(theme_dict, flavor_dict, ">", args)
        # starship output should not have been written
        self.assertFalse(Path(args.starship_output).exists())


# ── cmd_help ───────────────────────────────────────────────────────────────────


class TestCmdHelp(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_lists_themes(self) -> None:
        pal = make_palettes_file(self.tmp)
        args = argparse.Namespace(palette=pal)
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            rt.cmd_help(args)
        output = mock_out.getvalue()
        self.assertIn("monokai", output)
        self.assertIn("catppuccin", output)
        self.assertIn("spectrum", output)
        self.assertIn("default:", output)


# ── cmd_set_theme ──────────────────────────────────────────────────────────────


class TestCmdSetTheme(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.pal = make_palettes_file(self.tmp)
        make_template(self.tmp, "starship.tmpl", "sep={{SEP_TRANS}}")
        make_template(self.tmp, "dircolors.tmpl", "d={{DC_DIR}}")
        make_template(self.tmp, "git.tmpl", "a={{GC_ADDED}}")

    def _args(self, theme: str = "monokai", flavor: str = "spectrum") -> argparse.Namespace:
        args = make_render_args(self.tmp, self.pal, theme, flavor)
        args.nvim = os.path.join(self.tmp, "theme.lua")
        return args

    def test_applies_and_writes_nvim(self) -> None:
        args = self._args()
        rt.cmd_set_theme(args)
        self.assertTrue(os.path.exists(args.starship_output))
        self.assertTrue(os.path.exists(args.nvim))
        self.assertIn("monokai-pro", Path(args.nvim).read_text())

    def test_default_flavor_resolved(self) -> None:
        args = self._args(flavor="")  # should resolve to "spectrum"
        rt.cmd_set_theme(args)
        self.assertTrue(os.path.exists(args.nvim))

    def test_unknown_theme_exits(self) -> None:
        args = self._args(theme="ghost")
        with self.assertRaises(SystemExit):
            rt.cmd_set_theme(args)


# ── cmd_apply ──────────────────────────────────────────────────────────────────


class TestCmdApply(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.pal = make_palettes_file(self.tmp)
        make_template(self.tmp, "starship.tmpl", "x={{COLOR_FG}}")
        make_template(self.tmp, "dircolors.tmpl", "d={{DC_DIR}}")
        make_template(self.tmp, "git.tmpl", "a={{GC_ADDED}}")

    def test_renders_without_nvim(self) -> None:
        args = make_render_args(self.tmp, self.pal)
        rt.cmd_apply(args)
        self.assertTrue(os.path.exists(args.starship_output))
        self.assertIsNone(args.nvim)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "theme.lua")))

    def test_renders_with_nvim(self) -> None:
        args = make_render_args(self.tmp, self.pal)
        args.nvim = os.path.join(self.tmp, "theme.lua")
        rt.cmd_apply(args)
        self.assertTrue(os.path.exists(args.nvim))


# ── _blend_hex ─────────────────────────────────────────────────────────────────


class TestBlendHex(unittest.TestCase):
    def test_full_alpha_returns_fg(self) -> None:
        # alpha=1.0 → result equals fg
        result = rt._blend_hex("#ffffff", "#000000", 1.0)
        self.assertEqual(result, "#ffffff")

    def test_zero_alpha_returns_bg(self) -> None:
        # alpha=0.0 → result equals bg
        result = rt._blend_hex("#ffffff", "#000000", 0.0)
        self.assertEqual(result, "#000000")

    def test_half_alpha_blends(self) -> None:
        # alpha=0.5 → midpoint of white/black = #7f7f7f (int truncation)
        result = rt._blend_hex("#ffffff", "#000000", 0.5)
        # int(255*0.5 + 0*0.5) = 127 = 0x7f
        self.assertEqual(result, "#7f7f7f")

    def test_invalid_fg_returns_bg(self) -> None:
        result = rt._blend_hex("notacolor", "#aabbcc", 0.5)
        self.assertEqual(result, "#aabbcc")

    def test_both_invalid_returns_fallback(self) -> None:
        result = rt._blend_hex("bad", "alsabad", 0.5)
        self.assertEqual(result, "#808080")


# ── _is_dark ───────────────────────────────────────────────────────────────────


class TestIsDark(unittest.TestCase):
    def test_black_is_dark(self) -> None:
        self.assertTrue(rt._is_dark("#000000"))

    def test_white_is_light(self) -> None:
        self.assertFalse(rt._is_dark("#ffffff"))

    def test_dark_hex_is_dark(self) -> None:
        self.assertTrue(rt._is_dark("#1e1e2e"))  # catppuccin mocha base

    def test_invalid_defaults_to_dark(self) -> None:
        self.assertTrue(rt._is_dark("notacolor"))
        self.assertTrue(rt._is_dark(""))


# ── _apply_templates: delta computed placeholders ──────────────────────────────

DELTA_PALETTES: dict[str, Any] = {
    "testtheme": {
        "_default_flavor": "dark",
        "_nvim": {"theme": "testtheme"},
        "_roles": {
            "SEG": ["accent1"],
            "FG": "fg",
            "OK": "green",
            "ERR": "red",
            "WARN": "yellow",
            "BG": "bg",
            "GC_NEW": "green",
            "GC_OLD": "red",
        },
        "dark": {
            "accent1": "#fc618d",
            "fg": "#f7f1ff",
            "bg": "#1e1e2e",
            "green": "#7bd88f",
            "red": "#fc618d",
            "yellow": "#fd9353",
        },
    },
}


class TestApplyTemplatesDelta(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        # Write palettes.json with DELTA_PALETTES
        self.pal_path = os.path.join(self.tmp, "palettes.json")
        with open(self.pal_path, "w") as f:
            json.dump(DELTA_PALETTES, f)
        # Write templates
        make_template(self.tmp, "starship.tmpl", "fg={{COLOR_FG}}")
        make_template(self.tmp, "dircolors.tmpl", "dummy=no_dc_roles")
        make_template(
            self.tmp,
            "git.tmpl",
            (
                "plus_bg={{GC_PLUS_BG}} minus_bg={{GC_MINUS_BG}} "
                "plus_emph={{GC_PLUS_EMPH_BG}} minus_emph={{GC_MINUS_EMPH_BG}} "
                "syntax={{DELTA_SYNTAX_THEME}}"
            ),
        )

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            palette=self.pal_path,
            theme="testtheme",
            flavor="dark",
            sep=">",
            starship_template=os.path.join(self.tmp, "starship.tmpl"),
            starship_output=os.path.join(self.tmp, "starship.toml"),
            dircolors_template=os.path.join(self.tmp, "dircolors.tmpl"),
            dircolors_output=os.path.join(self.tmp, "dircolors"),
            git_template=os.path.join(self.tmp, "git.tmpl"),
            git_output=os.path.join(self.tmp, "git.conf"),
            nvim=None,
        )

    def test_delta_computed_placeholders_substituted(self) -> None:
        args = self._args()
        data = rt._load_palette(args.palette)
        t, f, _ = rt._resolve_theme_flavor(data, "testtheme", "dark")
        rt._apply_templates(t, f, ">", args)
        content = Path(args.git_output).read_text()
        # No literal {{...}} placeholders should remain
        self.assertNotIn("{{GC_PLUS_BG}}", content)
        self.assertNotIn("{{GC_MINUS_BG}}", content)
        self.assertNotIn("{{GC_PLUS_EMPH_BG}}", content)
        self.assertNotIn("{{GC_MINUS_EMPH_BG}}", content)
        self.assertNotIn("{{DELTA_SYNTAX_THEME}}", content)
        # Values should be hex colors or theme name
        self.assertIn("plus_bg=#", content)
        self.assertIn("minus_bg=#", content)
        self.assertIn("syntax=", content)

    def test_delta_syntax_theme_dark_bg(self) -> None:
        args = self._args()
        data = rt._load_palette(args.palette)
        t, f, _ = rt._resolve_theme_flavor(data, "testtheme", "dark")
        rt._apply_templates(t, f, ">", args)
        content = Path(args.git_output).read_text()
        # bg=#1e1e2e is dark → should use TwoDark
        self.assertIn("syntax=TwoDark", content)


# ── _apply_templates: nvim-only flavor (empty palette) ────────────────────────


NVIM_ONLY_PALETTES: dict[str, Any] = {
    "nvimonly": {
        "_default_flavor": "dark",
        "_nvim": {"theme": "somecolorscheme"},
        "_roles": {},
        "dark": {
            "_delta": {"syntax_theme": "Dracula"},
        },
    },
}


class TestApplyTemplatesNvimOnly(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.pal_path = os.path.join(self.tmp, "palettes.json")
        with open(self.pal_path, "w") as f:
            json.dump(NVIM_ONLY_PALETTES, f)
        make_template(self.tmp, "starship.tmpl", "fg={{COLOR_FG}}")
        make_template(self.tmp, "dircolors.tmpl", "dummy=x")
        make_template(self.tmp, "git.tmpl", "a={{GC_ADDED}}")

    def test_nvim_only_no_output_files(self) -> None:
        args = argparse.Namespace(
            palette=self.pal_path,
            theme="nvimonly",
            flavor="dark",
            sep=">",
            starship_template=os.path.join(self.tmp, "starship.tmpl"),
            starship_output=os.path.join(self.tmp, "starship.toml"),
            dircolors_template=os.path.join(self.tmp, "dircolors.tmpl"),
            dircolors_output=os.path.join(self.tmp, "dircolors"),
            git_template=os.path.join(self.tmp, "git.tmpl"),
            git_output=os.path.join(self.tmp, "git.conf"),
            nvim=None,
        )
        data = rt._load_palette(args.palette)
        t, f, _ = rt._resolve_theme_flavor(data, "nvimonly", "dark")
        rt._apply_templates(t, f, ">", args)
        # No output files should have been written
        self.assertFalse(os.path.exists(args.starship_output))
        self.assertFalse(os.path.exists(args.dircolors_output))
        self.assertFalse(os.path.exists(args.git_output))


# ── main() entry point ─────────────────────────────────────────────────────────


class TestMainEntryPoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.pal = make_palettes_file(self.tmp)
        make_template(self.tmp, "starship.tmpl", "sep={{SEP_TRANS}}")
        make_template(self.tmp, "dircolors.tmpl", "d={{DC_DIR}}")
        make_template(self.tmp, "git.tmpl", "a={{GC_ADDED}}")

    def _apply_argv(self, extra: list[str]) -> list[str]:
        return [
            "render-theme.py",
            "apply",
            "--palette",
            self.pal,
            "--theme",
            "monokai",
            "--flavor",
            "spectrum",
            "--sep",
            ">",
            "--starship-template",
            os.path.join(self.tmp, "starship.tmpl"),
            "--starship-output",
            os.path.join(self.tmp, "starship.toml"),
            "--dircolors-template",
            os.path.join(self.tmp, "dircolors.tmpl"),
            "--dircolors-output",
            os.path.join(self.tmp, "dircolors"),
            "--git-template",
            os.path.join(self.tmp, "git.tmpl"),
            "--git-output",
            os.path.join(self.tmp, "git.conf"),
        ] + extra

    def test_main_apply_subcommand(self) -> None:
        with patch("sys.argv", self._apply_argv([])):
            rt.main()
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "starship.toml")))

    def test_main_set_theme_subcommand(self) -> None:
        nvim_path = os.path.join(self.tmp, "theme.lua")
        argv = [
            "render-theme.py",
            "set-theme",
            "--palette",
            self.pal,
            "--theme",
            "monokai",
            "--flavor",
            "spectrum",
            "--sep",
            ">",
            "--starship-template",
            os.path.join(self.tmp, "starship.tmpl"),
            "--starship-output",
            os.path.join(self.tmp, "starship.toml"),
            "--dircolors-template",
            os.path.join(self.tmp, "dircolors.tmpl"),
            "--dircolors-output",
            os.path.join(self.tmp, "dircolors"),
            "--git-template",
            os.path.join(self.tmp, "git.tmpl"),
            "--git-output",
            os.path.join(self.tmp, "git.conf"),
            "--nvim",
            nvim_path,
        ]
        with patch("sys.argv", argv):
            rt.main()
        self.assertTrue(os.path.exists(nvim_path))

    def test_main_help_subcommand(self) -> None:
        with (
            patch("sys.argv", ["render-theme.py", "help", "--palette", self.pal]),
            patch("sys.stdout", new_callable=StringIO) as mock_out,
        ):
            rt.main()
        self.assertIn("monokai", mock_out.getvalue())

    def test_main_no_subcommand_exits(self) -> None:
        with patch("sys.argv", ["render-theme.py"]), self.assertRaises(SystemExit):
            rt.main()


if __name__ == "__main__":
    unittest.main()
