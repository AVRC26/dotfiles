"""Unit tests for preview-themes.py."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

_SRC = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("preview_themes", _SRC / "preview-themes.py")
assert spec is not None
assert spec.loader is not None
pt: Any = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)


# ── Fixtures ───────────────────────────────────────────────────────────────────

MINIMAL_PAL_DATA: dict[str, Any] = {
    "monokai": {
        "_default_flavor": "spectrum",
        "_nvim": {"theme": "monokai-pro"},
        "_roles": {
            "SEG": ["accent1"],
            "FG": "base",
        },
        "spectrum": {
            "accent1": "#fc618d",
            "base": "#f7f1ff",
        },
        "nvimonly": {
            "_nvim": {"theme": "monokai-pro"},
        },
        "with-fallback": {
            "_terminal_fallback": "spectrum",
            "_nvim": {"theme": "monokai-pro"},
        },
    },
    "catppuccin": {
        "_default_flavor": "mocha",
        "_nvim": {"theme": "catppuccin"},
        "_roles": {
            "SEG": ["mauve"],
            "FG": "text",
        },
        "mocha": {
            "mauve": "#cba6f7",
            "text": "#cdd6f4",
        },
    },
}


# ── _sep ───────────────────────────────────────────────────────────────────────


class TestSep(unittest.TestCase):
    def test_returns_string(self) -> None:
        # _sep() returns a Unicode separator glyph (U+E0B0 powerline right-arrow).
        # Assert it is a str; length may be 0 on consoles that strip the codepoint.
        result = pt._sep()
        self.assertIsInstance(result, str)


# ── _active_starship_template ─────────────────────────────────────────────────


class TestActiveStarshipTemplate(unittest.TestCase):
    def test_returns_powerline_when_no_file(self) -> None:
        fake_home = Path(tempfile.mkdtemp())
        with patch.object(Path, "home", return_value=fake_home):
            result = pt._active_starship_template()
        self.assertEqual(result, "powerline")

    def test_returns_file_content_when_exists(self) -> None:
        fake_home = Path(tempfile.mkdtemp())
        tmpl_file = fake_home / ".config" / "dotfiles-starship-template"
        tmpl_file.parent.mkdir(parents=True, exist_ok=True)
        tmpl_file.write_text("pills\n", encoding="utf-8")
        with patch.object(Path, "home", return_value=fake_home):
            result = pt._active_starship_template()
        self.assertEqual(result, "pills")

    def test_empty_file_returns_powerline(self) -> None:
        fake_home = Path(tempfile.mkdtemp())
        tmpl_file = fake_home / ".config" / "dotfiles-starship-template"
        tmpl_file.parent.mkdir(parents=True, exist_ok=True)
        tmpl_file.write_text("   \n", encoding="utf-8")
        with patch.object(Path, "home", return_value=fake_home):
            result = pt._active_starship_template()
        self.assertEqual(result, "powerline")


# ── _find_cfg ──────────────────────────────────────────────────────────────────


class TestFindCfg(unittest.TestCase):
    def test_exits_when_not_found(self) -> None:
        fake_home = Path(tempfile.mkdtemp())
        fake_here = Path(tempfile.mkdtemp())
        # Patch __file__ on the loaded module object and Path.home()
        with (
            patch.object(pt, "__file__", str(fake_here / "preview-themes.py")),
            patch.object(Path, "home", return_value=fake_home),
            self.assertRaises(SystemExit),
        ):
            pt._find_cfg()

    def test_returns_path_when_palettes_exist(self) -> None:
        fake_cfg = Path(tempfile.mkdtemp()) / ".config"
        fake_cfg.mkdir(parents=True, exist_ok=True)
        (fake_cfg / "palettes.json").write_text("{}", encoding="utf-8")
        fake_home = fake_cfg.parent
        fake_here = Path(tempfile.mkdtemp())
        # Patch __file__ so the module doesn't find the real repo .config first
        with (
            patch.object(pt, "__file__", str(fake_here / "preview-themes.py")),
            patch.object(Path, "home", return_value=fake_home),
        ):
            result = pt._find_cfg()
        self.assertEqual(result, fake_home / ".config")


# ── _build_combos ──────────────────────────────────────────────────────────────


class TestBuildCombos(unittest.TestCase):
    def test_returns_all_non_nvimonly(self) -> None:
        combos = pt._build_combos(MINIMAL_PAL_DATA)
        # spectrum has colors, nvimonly has none and no fallback, mocha has colors
        self.assertIn(("monokai", "spectrum"), combos)
        self.assertIn(("catppuccin", "mocha"), combos)
        self.assertNotIn(("monokai", "nvimonly"), combos)

    def test_includes_flavor_with_terminal_fallback(self) -> None:
        combos = pt._build_combos(MINIMAL_PAL_DATA)
        # with-fallback has no colors but declares _terminal_fallback — must be included
        self.assertIn(("monokai", "with-fallback"), combos)

    def test_filter_theme(self) -> None:
        combos = pt._build_combos(MINIMAL_PAL_DATA, filter_theme="catppuccin")
        themes = [t for t, _ in combos]
        self.assertTrue(all(t == "catppuccin" for t in themes))

    def test_filter_flavor(self) -> None:
        combos = pt._build_combos(MINIMAL_PAL_DATA, filter_flavor="mocha")
        flavors = [f for _, f in combos]
        self.assertTrue(all(f == "mocha" for f in flavors))

    def test_skips_underscore_themes(self) -> None:
        data: dict[str, Any] = {
            "_meta": {"_default_flavor": "x", "x": {"color": "#123456"}},
            "realtheme": {"_default_flavor": "dark", "dark": {"color": "#abcdef"}},
        }
        combos = pt._build_combos(data)
        themes = [t for t, _ in combos]
        self.assertNotIn("_meta", themes)
        self.assertIn("realtheme", themes)

    def test_sorted_output(self) -> None:
        combos = pt._build_combos(MINIMAL_PAL_DATA)
        self.assertEqual(combos, sorted(combos))

    def test_empty_palette_data_returns_empty(self) -> None:
        combos = pt._build_combos({})
        self.assertEqual(combos, [])


# ── main() integration ─────────────────────────────────────────────────────────


def _make_palettes_json(tmp: str, data: dict[str, Any]) -> Path:
    p = Path(tmp) / "palettes.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestMain(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)

        # Minimal palettes.json
        self.pal_data: dict[str, Any] = {
            "monokai": {
                "_default_flavor": "spectrum",
                "_nvim": {"theme": "monokai-pro"},
                "_roles": {"SEG": ["accent1"], "FG": "base"},
                "spectrum": {"accent1": "#fc618d", "base": "#f7f1ff"},
                "nvimonly": {"_nvim": {"theme": "monokai-pro"}},
                "with-fallback": {
                    "_terminal_fallback": "spectrum",
                    "_nvim": {"theme": "monokai-pro"},
                },
            },
        }
        self.pal_path = _make_palettes_json(self.tmp, self.pal_data)

        # Minimal starship template
        starship_dir = self.tmp_path / "starship"
        starship_dir.mkdir()
        (starship_dir / "powerline.toml").write_text("[character]\n", encoding="utf-8")

    def _run_main(self, extra_args: list[str] | None = None) -> None:
        """Run main() with the temp config, fully mocked subprocess and PTY."""
        argv = ["preview-themes.py"] + (extra_args or [])
        cfg = self.tmp_path

        def fake_find_cfg() -> Path:
            return cfg

        completed: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess([], 0)

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", side_effect=fake_find_cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            patch.object(pt, "_starship_via_pty", return_value=None),
            patch.object(pt, "_show_git_diff", return_value=None),
            patch.object(pt, "_show_git_status", return_value=None),
            patch.object(pt, "_show_dir_colors", return_value=None),
            patch.object(pt, "_show_nvim_theme", return_value=None),
            patch("subprocess.run", return_value=completed),
            patch.object(pt, "_HAS_PTY", False),
        ):
            pt.main()

    def test_main_runs_without_error(self) -> None:
        self._run_main()

    def test_main_forwards_conditional_module_flags_to_pty(self) -> None:
        """Hardcoded status/cmd_duration/jobs/shlvl values should reach _starship_via_pty."""
        argv = ["preview-themes.py"]
        cfg = self.tmp_path
        completed: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess([], 0)

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            patch.object(pt, "_starship_via_pty", return_value=None) as mock_pty,
            patch.object(pt, "_show_git_diff", return_value=None),
            patch.object(pt, "_show_git_status", return_value=None),
            patch.object(pt, "_show_dir_colors", return_value=None),
            patch.object(pt, "_show_nvim_theme", return_value=None),
            patch("subprocess.run", return_value=completed),
            patch.object(pt, "_HAS_PTY", True),
        ):
            pt.main()

        self.assertGreater(mock_pty.call_count, 0)
        _, kwargs = mock_pty.call_args
        self.assertEqual(
            kwargs["extra_args"],
            ["--status", "1", "--cmd-duration", "2500", "--jobs", "2", "--shlvl", "5"],
        )

    def test_main_forwards_conditional_module_flags_to_subprocess_fallback(self) -> None:
        """Same hardcoded values should reach the non-PTY subprocess.run fallback path."""
        argv = ["preview-themes.py"]
        cfg = self.tmp_path
        completed: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess([], 0)

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            patch.object(pt, "_show_git_diff", return_value=None),
            patch.object(pt, "_show_git_status", return_value=None),
            patch.object(pt, "_show_dir_colors", return_value=None),
            patch.object(pt, "_show_nvim_theme", return_value=None),
            patch("subprocess.run", return_value=completed) as mock_run,
            patch.object(pt, "_HAS_PTY", False),
        ):
            pt.main()

        starship_calls = [
            call.args[0] for call in mock_run.call_args_list if call.args[0][0] == "starship"
        ]
        self.assertTrue(starship_calls)
        self.assertIn("--status", starship_calls[0])
        self.assertIn("--jobs", starship_calls[0])

    def test_main_exits_when_template_not_found(self) -> None:
        """main() should exit if the starship template file does not exist."""
        argv = ["preview-themes.py", "--starship-template", "nonexistent"]
        cfg = self.tmp_path

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="nonexistent"),
            self.assertRaises(SystemExit),
        ):
            pt.main()

    def test_main_exits_when_no_combos(self) -> None:
        """main() should exit when filter matches no theme/flavor combinations."""
        argv = ["preview-themes.py", "--theme", "nonexistenttheme"]
        cfg = self.tmp_path

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            self.assertRaises(SystemExit),
        ):
            pt.main()

    def test_main_nvimonly_flavor_message(self) -> None:
        """Requesting an nvim-only flavor should mention 'nvim-only' in the exit message."""
        argv = ["preview-themes.py", "--theme", "monokai", "--flavor", "nvimonly"]
        cfg = self.tmp_path

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            self.assertRaises(SystemExit) as ctx,
        ):
            pt.main()
        self.assertIn("nvim-only", str(ctx.exception))

    def test_main_unknown_theme_message(self) -> None:
        """Requesting an unknown theme should list available themes in the exit message."""
        argv = ["preview-themes.py", "--theme", "nosuchtheme", "--flavor", "dark"]
        cfg = self.tmp_path

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            self.assertRaises(SystemExit) as ctx,
        ):
            pt.main()
        self.assertIn("monokai", str(ctx.exception))

    def test_main_unknown_flavor_message(self) -> None:
        """Requesting an unknown flavor should list available flavors in the exit message."""
        argv = ["preview-themes.py", "--theme", "monokai", "--flavor", "nosuchflavor"]
        cfg = self.tmp_path

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            self.assertRaises(SystemExit) as ctx,
        ):
            pt.main()
        self.assertIn("spectrum", str(ctx.exception))

    def test_main_skips_nvimonly_flavors(self) -> None:
        """nvimonly flavor (no terminal fallback) should be absent from combos."""
        combos = pt._build_combos(self.pal_data)
        flavor_names = [f for _, f in combos]
        self.assertNotIn("nvimonly", flavor_names)

    def test_main_includes_flavor_with_terminal_fallback(self) -> None:
        """A flavor with _terminal_fallback should appear in combos and not cause an exit."""
        combos = pt._build_combos(self.pal_data)
        flavor_names = [f for _, f in combos]
        self.assertIn("with-fallback", flavor_names)

    def test_main_handles_render_failure_gracefully(self) -> None:
        """When subprocess.run returns non-zero, main should print [render failed] and continue."""
        from io import StringIO

        argv = ["preview-themes.py"]
        cfg = self.tmp_path
        failed: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess([], 1)

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            patch.object(pt, "_starship_via_pty", return_value=None),
            patch("subprocess.run", return_value=failed),
            patch.object(pt, "_HAS_PTY", False),
            patch("sys.stdout", new_callable=StringIO) as mock_out,
        ):
            pt.main()

        self.assertIn("render failed", mock_out.getvalue())

    def test_main_handles_keyboard_interrupt(self) -> None:
        """KeyboardInterrupt during the loop should cause sys.exit(0)."""
        argv = ["preview-themes.py"]
        cfg = self.tmp_path

        with (
            patch.object(sys, "argv", argv),
            patch.object(pt, "_find_cfg", return_value=cfg),
            patch.object(pt, "_active_starship_template", return_value="powerline"),
            patch.object(pt, "_starship_via_pty", side_effect=KeyboardInterrupt),
            patch.object(pt, "_show_git_diff", return_value=None),
            patch.object(pt, "_show_git_status", return_value=None),
            patch.object(pt, "_show_dir_colors", return_value=None),
            patch.object(pt, "_show_nvim_theme", return_value=None),
            patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)),
            patch.object(pt, "_HAS_PTY", True),
            self.assertRaises(SystemExit) as ctx,
        ):
            pt.main()
        self.assertEqual(ctx.exception.code, 0)


# ── _find_nvim_init ───────────────────────────────────────────────────────────


def _nvim_init_in(base: Path) -> Path:
    """Return where _find_nvim_init expects init.lua given a fake config base."""
    if os.name == "nt":
        return base / "nvim" / "init.lua"  # LOCALAPPDATA/nvim/init.lua
    return base / ".config" / "nvim" / "init.lua"


def _patch_nvim_home(fake_dir: Path):  # type: ignore[return]
    """Return a context manager that redirects _find_nvim_init to fake_dir."""
    if os.name == "nt":
        return patch.dict(os.environ, {"LOCALAPPDATA": str(fake_dir)})
    return patch.object(Path, "home", return_value=fake_dir)


class TestFindNvimInit(unittest.TestCase):
    def test_returns_none_when_not_found(self) -> None:
        fake_base = Path(tempfile.mkdtemp())
        with _patch_nvim_home(fake_base):
            result = pt._find_nvim_init()
        self.assertIsNone(result)

    def test_returns_path_when_init_lua_exists(self) -> None:
        fake_base = Path(tempfile.mkdtemp())
        init = _nvim_init_in(fake_base)
        init.parent.mkdir(parents=True, exist_ok=True)
        init.write_text("-- init\n", encoding="utf-8")
        with _patch_nvim_home(fake_base):
            result = pt._find_nvim_init()
        self.assertEqual(result, init)


# ── _write_nvim_theme_lua ─────────────────────────────────────────────────────


class TestWriteNvimThemeLua(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_writes_active_theme(self) -> None:
        out = self.tmp / "theme.lua"
        pt._write_nvim_theme_lua(
            {"_nvim": {"theme": "catppuccin", "variant_key": "catppuccin_flavour"}},
            "mocha",
            out,
        )
        content = out.read_text(encoding="utf-8")
        self.assertIn('vim.g.active_theme = "catppuccin"', content)
        self.assertIn('vim.g.catppuccin_flavour = "mocha"', content)

    def test_no_variant_key_omits_variant_line(self) -> None:
        out = self.tmp / "theme.lua"
        pt._write_nvim_theme_lua({"_nvim": {"theme": "gruvbox"}}, "dark", out)
        content = out.read_text(encoding="utf-8")
        self.assertIn('vim.g.active_theme = "gruvbox"', content)
        self.assertEqual(content.count("vim.g."), 1)

    def test_empty_flavor_omits_variant_line(self) -> None:
        out = self.tmp / "theme.lua"
        pt._write_nvim_theme_lua(
            {"_nvim": {"theme": "monokai", "variant_key": "monokai_filter"}}, "", out
        )
        content = out.read_text(encoding="utf-8")
        self.assertEqual(content.count("vim.g."), 1)


if __name__ == "__main__":
    unittest.main()
