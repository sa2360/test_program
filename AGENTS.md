# Workspace instructions

- Save every `*.ps1` file that may run under Windows PowerShell 5.1 as UTF-8 with BOM. PowerShell 5.1 misreads BOM-less UTF-8 source containing Chinese text as the active ANSI code page.
- Prefer `$PSScriptRoot`, environment variables, or ASCII-only arguments over hard-coded Chinese working-directory literals.
- After creating or editing a PowerShell script containing non-ASCII text, verify the `EF BB BF` prefix and run it in a brand-new `powershell.exe -NoProfile` child process.
