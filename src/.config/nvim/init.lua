-- ============================================================
-- Bootstrap lazy.nvim
-- ============================================================
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git", "clone", "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable", lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

-- ============================================================
-- General settings
-- ============================================================
vim.opt.backspace   = "indent,eol,start"
-- OSC52 disabled: MobaXterm renders a garbage character (+q4D73) when it is active.
vim.g.termfeatures  = vim.tbl_extend("force", vim.g.termfeatures or {}, { osc52 = false })
-- Mouse disabled: prevents unintended selection and paste when clicking around the terminal.
vim.opt.mouse       = ""
vim.opt.cursorline  = true
vim.opt.history     = 500
vim.opt.ruler       = true
vim.opt.showmatch   = true
vim.opt.tw          = 80
vim.opt.undolevels  = 1000
vim.opt.wildmode    = "longest,list"
vim.opt.hlsearch    = true
vim.opt.incsearch   = true
vim.opt.smartcase   = true
vim.opt.expandtab   = true
vim.opt.softtabstop = 4
vim.opt.tabstop     = 4
vim.opt.shiftwidth  = 4
-- Line numbers on by default. Toggle with Ctrl+N Ctrl+N.
-- When mouse-selecting to copy, toggle numbers and indent guides off first (Ctrl+I Ctrl+I)
-- to avoid including them in the selection. Yank (v + y) never includes either.
vim.opt.number      = true
vim.opt.foldenable  = false
vim.opt.nuw         = 6
vim.opt.termguicolors = true
vim.g.mapleader     = ","

-- auto-create parent directories when saving a new file
vim.api.nvim_create_autocmd("BufWritePre", {
  callback = function()
    local dir = vim.fn.expand("<afile>:p:h")
    if vim.fn.isdirectory(dir) == 0 then
      vim.fn.mkdir(dir, "p")
    end
  end,
})

-- return to last cursor position when reopening a file
vim.api.nvim_create_autocmd("BufReadPost", {
  callback = function()
    local mark = vim.api.nvim_buf_get_mark(0, '"')
    if mark[1] > 0 and mark[1] <= vim.api.nvim_buf_line_count(0) then
      vim.api.nvim_win_set_cursor(0, mark)
    end
  end,
})

-- strip trailing whitespace on save
vim.api.nvim_create_autocmd({ "BufRead", "BufWrite" }, {
  callback = function()
    if not vim.bo.binary then
      vim.cmd([[silent! %s/\s\+$//ge]])
    end
  end,
})

-- ============================================================
-- Keymaps
-- ============================================================
local map = vim.keymap.set
map("c", "w!!", "w !sudo tee % > /dev/null")
map("n", "<C-N><C-N>", ":set invnumber<CR>")
-- Toggle indent guides (Ctrl+I Ctrl+I). Turn off before mouse-selecting to avoid
-- copying the guide characters (▎) into the clipboard.
map("n", "<C-I><C-I>", ":IBLToggle<CR>", { silent = true })
map("n", "<Space>", "zA")
map("v", "<Space>", "zA")
map("n", "<C-x>", "za")
map("v", "<C-x>", "za")
map("n", "<S-n>", ":BufferLineCycleNext<CR>", { silent = true })
map("n", "<S-p>", ":BufferLineCyclePrev<CR>", { silent = true })
map("n", "<S-t>", ":enew<CR>",               { silent = true })
map("n", "<S-x>", ":bd<CR>",                 { silent = true })
map("n", "<S-v>", ":vsplit<CR>",             { silent = true })
map("n", "<S-h>", ":split<CR>",              { silent = true })

-- ============================================================
-- Active theme
-- Written by set-theme shell function; read here on startup.
-- Defaults: root → gruvbox,  everyone else → monokai-pro (spectrum)
-- ============================================================
local theme_file = vim.fn.stdpath("config") .. "/theme.lua"
if vim.fn.filereadable(theme_file) == 1 then
  dofile(theme_file)
end
if not vim.g.active_theme then
  vim.g.active_theme = "monokai-pro"
end

-- ============================================================
-- Plugins
-- ============================================================
require("lazy").setup({

  -- ── Themes ────────────────────────────────────────────────
  {
    "loctvl842/monokai-pro.nvim",
    lazy = false, priority = 1000,
    config = function()
      if vim.g.active_theme == "monokai-pro" then
        require("monokai-pro").setup({
          transparent_background = false,
          terminal_colors        = true,
          devicons               = true,
          filter                 = vim.g.monokai_filter or "spectrum",
          inc_search             = "background",
          styles = {
            comment   = { italic = true },
            keyword   = { italic = true },
            type      = { italic = true },
            parameter = { italic = true },
          },
          background_clear = { "telescope", "toggleterm", "notify" },
          plugins = {
            treesitter = true,
            bufferline = {
              underline_selected = true,
              underline_visible  = false,
              bold               = true,
            },
            indent_blankline = {
              context_highlight       = "pro",
              context_start_underline = false,
            },
          },
        })
        local _f = vim.g.monokai_filter or "spectrum"
        vim.cmd.colorscheme(_f == "pro" and "monokai-pro" or ("monokai-pro-" .. _f))
      end
    end,
  },
  {
    "catppuccin/nvim",
    name = "catppuccin",
    lazy = false, priority = 999,
    config = function()
      if vim.g.active_theme == "catppuccin" then
        -- theme.lua may set vim.g.catppuccin_flavour; root defaults to
        -- "frappe" (visually distinct from user's "mocha").
        require("catppuccin").setup({
          flavour                = vim.g.catppuccin_flavour or "mocha",
          transparent_background = false,
          term_colors            = true,
          styles = {
            comments     = { "italic" },
            conditionals = { "italic" },
          },
          integrations = {
            cmp        = true,
            gitsigns   = true,
            nvimtree   = true,
            bufferline = true,
            telescope  = { enabled = true },
            indent_blankline = {
              enabled               = true,
              scope_color           = "lavender",
              colored_indent_levels = false,
            },
            native_lsp = {
              enabled    = true,
              underlines = {
                errors      = { "underline" },
                hints       = { "underline" },
                warnings    = { "underline" },
                information = { "underline" },
              },
            },
          },
        })
        vim.cmd.colorscheme("catppuccin")
      end
    end,
  },
  {
    "rebelot/kanagawa.nvim",
    lazy = false, priority = 998,
    config = function()
      if vim.g.active_theme == "kanagawa" then
        local variant = vim.g.kanagawa_variant or "wave"
        require("kanagawa").setup({ theme = variant })
        vim.cmd.colorscheme("kanagawa-" .. variant)
      end
    end,
  },
  {
    "Ferouk/bearded-nvim",
    name = "bearded",
    lazy = false, priority = 997,
    config = function()
      if vim.g.active_theme == "bearded" then
        require("bearded").setup({
          flavor          = vim.g.bearded_flavor or "arc",
          bold            = true,
          italic          = true,
          terminal_colors = true,
        })
        vim.cmd.colorscheme("bearded")
      end
    end,
  },
  {
    "ellisonleao/gruvbox.nvim",
    lazy = false, priority = 996,
    config = function()
      if vim.g.active_theme == "gruvbox" then
        local flavor = vim.g.gruvbox_flavor or "dark"
        vim.o.background = (flavor == "light" or flavor == "light-hard" or flavor == "light-soft") and "light" or "dark"
        local contrast = (flavor == "dark-hard" or flavor == "light-hard") and "hard"
                      or (flavor == "dark-soft" or flavor == "light-soft") and "soft"
                      or ""
        require("gruvbox").setup({
          terminal_colors = true,
          undercurl       = true,
          underline       = true,
          bold            = true,
          italic = {
            strings  = true,
            emphasis  = true,
            comments  = true,
            operators = false,
            folds     = true,
          },
          contrast = contrast,
        })
        vim.cmd.colorscheme("gruvbox")
      end
    end,
  },
  {
    "folke/tokyonight.nvim",
    lazy = false, priority = 995,
    config = function()
      if vim.g.active_theme == "tokyonight" then
        require("tokyonight").setup({
          style           = vim.g.tokyonight_style or "night",  -- night | storm | moon | day
          terminal_colors = true,
          styles = {
            comments  = { italic = true },
            keywords  = { italic = true },
          },
        })
        vim.cmd.colorscheme("tokyonight-" .. (vim.g.tokyonight_style or "night"))
      end
    end,
  },
  {
    "kepano/flexoki-neovim",
    name = "flexoki",
    lazy = false, priority = 994,
    config = function()
      if vim.g.active_theme == "flexoki" then
        local style = vim.g.flexoki_style or "dark"
        vim.cmd.colorscheme("flexoki-" .. style)
      end
    end,
  },
  {
    "uhs-robert/oasis.nvim",
    lazy = false, priority = 993,
    config = function()
      if vim.g.active_theme == "oasis" then
        require("oasis").setup({ style = vim.g.oasis_style or "moonlight" })
        vim.cmd.colorscheme("oasis-" .. (vim.g.oasis_style or "moonlight"))
      end
    end,
  },
  {
    "ribru17/bamboo.nvim",
    lazy = false, priority = 992,
    config = function()
      if vim.g.active_theme == "bamboo" then
        require("bamboo").setup({ style = vim.g.bamboo_style or "vulgaris" })
        vim.cmd.colorscheme("bamboo")
      end
    end,
  },
  {
    "olimorris/onedarkpro.nvim",
    lazy = false, priority = 991,
    config = function()
      if vim.g.active_theme == "onedarkpro" then
        require("onedarkpro").setup({
          options = {
            terminal_colors  = true,
            cursorline       = true,
          },
        })
        -- colorscheme names: onedark | onelight | onedark_vivid | onedark_dark
        vim.cmd.colorscheme(vim.g.onedarkpro_style or "onedark")
      end
    end,
  },
  {
    "Shatur/neovim-ayu",
    name = "ayu",
    lazy = false, priority = 990,
    config = function()
      if vim.g.active_theme == "ayu" then
        local flavor = vim.g.ayu_flavor or "dark"
        vim.o.background = (flavor == "light") and "light" or "dark"
        require("ayu").setup({ mirage = (flavor == "mirage"), terminal = true })
        require("ayu").colorscheme()
      end
    end,
  },

  -- ── Navigation & search ───────────────────────────────────
  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    config = function()
      require("telescope").setup({})
      local b = require("telescope.builtin")
      vim.keymap.set("n", "<C-p>",     b.find_files,  { desc = "find files" })
      vim.keymap.set("n", "<leader>f", b.live_grep,   { desc = "live grep" })
      vim.keymap.set("n", "<leader>b", b.buffers,     { desc = "buffers" })
      vim.keymap.set("n", "<leader>t", b.grep_string, { desc = "grep word under cursor" })
    end,
  },
  {
    "nvim-tree/nvim-web-devicons",
    lazy = false,
    config = function()
      require("nvim-web-devicons").setup({
        default      = true,   -- fallback glyph for unknown filetypes
        color_icons  = true,   -- per-icon highlight colours
        strict       = true,   -- filename match first, then extension
      })
    end,
  },
  {
    "nvim-tree/nvim-tree.lua",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      -- Disable netrw so nvim-tree owns directory views
      vim.g.loaded_netrw       = 1
      vim.g.loaded_netrwPlugin = 1

      -- Must be called BEFORE nvim-tree.setup() — devicons ignores any
      -- setup() call after the first one (see nvim-web-devicons known issues).
      require("nvim-web-devicons").setup({
        default     = true,
        color_icons = true,
        strict      = true,
      })

      require("nvim-tree").setup({
        renderer = {
          group_empty   = true,
          highlight_git = true,
          icons = {
            show = {
              file         = true,
              folder       = true,
              folder_arrow = true,
              git          = true,
            },
            -- No explicit glyphs block — nvim-tree uses its built-in defaults
            -- which share the same Nerd Font codepoint table as nvim-web-devicons.
            -- Override only git status with plain Unicode (renders everywhere).
            glyphs = {
              git = {
                unstaged  = "✗",
                staged    = "✓",
                unmerged  = "⚠",
                renamed   = "➜",
                untracked = "★",
                deleted   = "✘",
                ignored   = "◌",
              },
            },
          },
        },
      })
      vim.keymap.set("n", "<C-n>", ":NvimTreeToggle<CR>", { silent = true })
    end,
  },
  {
    "akinsho/bufferline.nvim",
    version = "*",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      local highlights = {}
      if vim.g.active_theme == "catppuccin" then
        local ok, cat_bl = pcall(require, "catppuccin.groups.integrations.bufferline")
        if ok then highlights = cat_bl.get() end
      end
      require("bufferline").setup({
        highlights = highlights,
        options = {
          diagnostics         = false,
          show_buffer_icons   = true,   -- file-type icons from nvim-web-devicons
          show_buffer_close_icons = false,
          show_close_icon     = false,
          offsets = {{
            filetype  = "NvimTree",
            text      = "Files",
            highlight = "Directory",
            separator = true,
          }},
        },
      })
    end,
  },

  -- ── Treesitter — syntax highlighting + smart indent ──────
  -- NOTE: pin to `master` branch.  The new default `main` branch is a
  -- rewrite with a different API (no setup(), no :TSInstall*, no configs
  -- module).  Stay on master until the ecosystem catches up.
  {
    "nvim-treesitter/nvim-treesitter",
    lazy = false,
    branch = "master",
    build = ":TSUpdate",
    config = function()
      local ok, configs = pcall(require, "nvim-treesitter.configs")
      if not ok then return end   -- plugin not yet installed; silent on first launch
      configs.setup({
        sync_install = true,   -- compile parsers synchronously (matters on first headless run)
        compilers = { "zig" }, -- zig is the C compiler; no gcc/cc required
        -- Parsers for the active stack; add more with :TSInstall <lang>
        ensure_installed = {
          -- Languages
          "python",
          "javascript",      -- JS + JSX
          "typescript",      -- TypeScript
          "tsx",             -- React TSX (Next.js components)
          "lua",
          "powershell",
          "sql",
          -- Infrastructure / config
          "hcl",             -- Terraform (.tf / .tfvars)
          "terraform",
          "dockerfile",
          "helm",
          "yaml",
          "toml",
          -- Web
          "css",
          "html",
          "htmldjango",
          "http",
          "jinja",
          "jinja_inline",
          -- Data / markup
          "json",
          "jsonc",
          "xml",
          "csv",
          "markdown",
          "markdown_inline",
          -- Tooling
          "regex",
          "jq",
          "mermaid",
        },
        highlight = {
          enable = true,
          -- Keep vim regex as fallback only for filetypes with no TS parser
          additional_vim_regex_highlighting = false,
        },
        indent = { enable = true },
      })
    end,
  },

  -- ── Git ───────────────────────────────────────────────────
  {
    "lewis6991/gitsigns.nvim",
    config = function() require("gitsigns").setup() end,
  },

  -- ── UI ────────────────────────────────────────────────────
  {
    "nvim-lualine/lualine.nvim",
    config = function()
      require("lualine").setup({
        options = {
          theme                = "auto",
          icons_enabled        = true,
          -- Classic powerline glyphs (codepoints E0B0-E0B3) are in every
          -- Nerd Font version so these render reliably across all terminals.
          section_separators   = { left = "", right = "" },
          component_separators = { left = "", right = "" },
        },
        sections = {
          lualine_a = { "mode" },
          lualine_b = {
            { "branch", icon = "" },
            { "diff",
              symbols = { added = " ", modified = " ", removed = " " },
            },
          },
          lualine_c = { { "filename", symbols = { modified = " ●", readonly = " ", unnamed = "[No Name]" } } },
          lualine_x = { { "filetype", icon_only = false } },
          lualine_y = { "progress" },
          lualine_z = { "location" },
        },
      })
    end,
  },
  {
    "lukas-reineke/indent-blankline.nvim",
    main = "ibl",
    config = function() require("ibl").setup() end,
  },

}, {
  ui = { border = "rounded" },
})
