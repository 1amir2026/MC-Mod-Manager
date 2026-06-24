# MC Mod Manager

**Minecraft Mod Manager -- CLI Edition**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![Modrinth](https://img.shields.io/badge/Powered%20by-Modrinth-green)](https://modrinth.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()

---

A command-line tool for scanning, version-checking, and downloading Minecraft mods from [Modrinth](https://modrinth.com). No GUI required.

---

## Features

| Feature | Description |
|---------|-------------|
| Guided wizard flow | Step-by-step prompts -- no menus to navigate |
| Auto-detect Minecraft folder | Finds the default `.minecraft` directory on all platforms |
| Deep mod scanning | Reads metadata from Fabric, Forge, NeoForge, and Quilt jars |
| SHA-512 hash search | Identifies mods precisely via Modrinth's hash API |
| Version and loader targeting | Checks updates for your specific MC version and loader |
| Progress bar download | Downloads each mod with a per-file percentage bar |
| Organized output folder | Creates `MC_{version}_{loader}/mods/` alongside your existing folder |
| Session log | Saves a timestamped log file in the output folder |
| Auto-install dependencies | Installs `requests` and `packaging` automatically if missing |

---

## Requirements

```
Python 3.8+
requests
packaging
```

Dependencies are installed automatically on first run. If the primary PyPI index is unreachable, the script falls back to a mirror automatically.

---

## Windows Security Warning

When running the executable for the first time, Windows SmartScreen may
display a blue warning screen ("Windows protected your PC"). This happens
because the binary is not code-signed.

To proceed:
1. Click "More info"
2. Click "Run anyway"

This is expected behavior for unsigned open-source executables.
The source code is fully available in this repository for review.

---

## Usage Guide

This guide covers two ways to use MC Mod Manager: running the prebuilt binary, or running from source with Python.

---

### Option 1 — Prebuilt Binary (Recommended)

No Python or any other software required.

**Step 1.** Go to the [Releases](https://github.com/1amir2026/MC-Mod-Manager/releases/latest) page and download the file for your platform:

| Platform | File |
|----------|------|
| Windows 64-bit | MCModManager-Windows-x64.exe |
| Linux 64-bit | MCModManager-Linux-x64 |
| macOS 64-bit | MCModManager-macOS-x64 |

**Step 2.** Run the file.

Windows:
```
Double-click MCModManager-Windows-x64.exe
```
If Windows SmartScreen shows a blue warning, click More info then Run anyway.

Linux / macOS:
```bash
chmod +x MCModManager-Linux-x64
./MCModManager-Linux-x64
```

macOS only: If Gatekeeper blocks the file, run this once:
```bash
xattr -d com.apple.quarantine ./MCModManager-macOS-x64
```

---

### Option 2 — Run from Source with Python

Requires Python 3.8 or later. Download from https://python.org.

**Step 1.** Clone the repository:
```bash
git clone https://github.com/1amir2026/MC-Mod-Manager.git
cd MC-Mod-Manager
```

**Step 2.** Install dependencies:
```bash
pip install requests packaging
```

**Step 3.** Run:
```bash
python mc_mod_manager_cli.py
```

Dependencies are also installed automatically on first run if missing.

---

### Option 3 — Build the Binary Yourself

If you want to compile your own executable from source:

```bash
pip install pyinstaller requests packaging
pyinstaller --onefile --console --name MCModManager mc_mod_manager_cli.py
```

Output will be in the `dist/` folder.

Windows only — to include a custom icon:
```bash
pyinstaller --onefile --console --name MCModManager --icon=icon1.ico mc_mod_manager_cli.py
```

---

### Workflow

Once started, the tool guides you through six steps:

```
Step 1  Select your Minecraft folder
        The default .minecraft path is detected automatically.
        You can confirm it or enter a custom path.

Step 2  Select target Minecraft version
        Choose from a list fetched from Modrinth,
        or type a version manually (e.g. 1.21.4).

Step 3  Select mod loader
        Choose from Fabric, Forge, NeoForge, or Quilt.

Step 4  Scan and check
        The tool scans your mods folder and queries Modrinth
        for each mod. Results are shown as:
          update available  -- a newer version exists for your target
          up-to-date        -- already on the latest version
          not found         -- mod is not available on Modrinth

Step 5  Confirm
        Review the full list and confirm before any files are written.

Step 6  Download
        Each mod is downloaded one by one with a progress bar.
        A new folder is created at:
        .minecraft/MC_{version}_{loader}/mods/
        Your existing mods folder is never modified.
```

---

### Output Structure

After a successful run:

```
.minecraft/
+-- MC_1.21.4_Fabric/
    +-- mods/
    |   +-- sodium-fabric-0.6.3+mc1.21.4.jar
    |   +-- lithium-fabric-0.13.0+mc1.21.4.jar
    |   +-- ...
    +-- log_20250623_183000.txt
```

---

### Troubleshooting

| Issue | Resolution |
|-------|------------|
| Mod not found | The mod may only be on CurseForge. Download it manually. |
| Windows blue screen on launch | Click More info then Run anyway. |
| macOS blocked by Gatekeeper | Run: xattr -d com.apple.quarantine ./MCModManager-macOS-x64 |
| Network error | Check your connection. The tool retries automatically. |
| Wrong version downloaded | Make sure your selected loader matches the mods in your folder. |
| pip cannot reach PyPI | The tool retries with a fallback mirror automatically. |

---

## Workflow

The tool runs as a linear wizard. Each step must be completed before moving to the next.

```
Step 1 -- Select Minecraft folder
          Choose the default detected path or enter a custom one.

Step 2 -- Select target Minecraft version
          Pick from a fetched list or type a version string (e.g. 1.21.4).

Step 3 -- Select mod loader
          Choose Fabric, Forge, NeoForge, or Quilt.

Step 4 -- Scan and check
          The tool scans your mods folder, then queries Modrinth for
          each mod and reports whether an update is available.

Step 5 -- Confirm
          Review a summary table and confirm before any files are written.

Step 6 -- Download
          Each mod is downloaded in sequence with a progress bar.
          The output folder is created in the same directory as your
          .minecraft folder.
```

---

## Output Structure

After a successful run, a new folder is created at the same level as your `.minecraft` folder (or inside it if that is what was selected):

```
.minecraft/
+-- MC_1.21.4_Fabric/
    +-- mods/
    |   +-- sodium-fabric-0.6.3+mc1.21.4.jar
    |   +-- lithium-fabric-0.13.0+mc1.21.4.jar
    |   +-- ...
    +-- log_20250623_183000.txt
```

The existing `.minecraft/mods/` folder is never modified.

---

## Supported Loaders

| Loader | Metadata file |
|--------|--------------|
| Fabric | `fabric.mod.json` |
| Forge | `META-INF/mods.toml` |
| NeoForge | `META-INF/neoforge.mods.toml` |
| Quilt | `quilt.mod.json` |

---

## Mod Search Strategy

For each mod, Modrinth is queried in this order of precision:

```
1. SHA-512 file hash  -- most accurate, matches the exact uploaded file
2. Saved project ID   -- reused from a prior hash or name lookup
3. Mod ID search      -- searches by the mod's internal identifier
4. Display name       -- fallback text search using the mod's display name
```

---

## Building a Standalone Binary

### Windows (.exe)

```bash
pip install pyinstaller
pyinstaller --onefile --console --name MCModManager mc_mod_manager_cli.py
```

Output: `dist/MCModManager.exe`

### Linux

```bash
pip install pyinstaller
pyinstaller --onefile --console --name MCModManager mc_mod_manager_cli.py
```

Output: `dist/MCModManager`

Make it executable:

```bash
chmod +x dist/MCModManager
./dist/MCModManager
```

### macOS

Same command as Linux. Output: `dist/MCModManager` (Mach-O binary).

To distribute on macOS without Gatekeeper warnings, the binary needs to be code-signed. For personal use, running `xattr -d com.apple.quarantine ./MCModManager` after download is sufficient.

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| Mod not found | The mod may only be available on CurseForge. Download it manually. |
| Network error | Check your internet connection. The script retries automatically. |
| Wrong version downloaded | Confirm that your selected loader matches the mods in your folder. |
| Hash not matched | The mod was not downloaded from Modrinth originally. A name-based search will be attempted instead. |
| `pip` cannot reach PyPI | The script will retry using a fallback mirror. If both fail, run `pip install requests packaging` manually using a working network. |

---

## Sample Log

```
MC Mod Manager v4.0.0
Date: 2025-06-23 18:30:00
============================================================
[18:30:01][INFO] Scanned: 23 mods
[18:30:05][INFO] Check [available] Sodium -> 0.6.3+mc1.21.4
[18:30:06][INFO] Check [up_to_date] Lithium -> 0.13.0+mc1.21.4
[18:30:07][INFO] Check [not_found] OldMod -> N/A
[18:30:10][INFO] Output: .minecraft/MC_1.21.4_Fabric
[18:30:11][INFO] Downloading: Sodium -> 0.6.3+mc1.21.4
[18:30:13][INFO] OK: Sodium v0.6.3+mc1.21.4
```

---

## Code Structure

```
mc_mod_manager_cli.py
+-- Auto-install deps       requests + packaging
+-- Mod (class)             Data model for a scanned mod
+-- parse_jar()             Reads .jar metadata (Fabric / Forge / NeoForge / Quilt)
+-- scan_mods()             Scans the mods/ directory
+-- Modrinth (class)        API wrapper for modrinth.com
+-- download_file()         Downloads a file with a terminal progress bar
+-- Logger (class)          Writes a timestamped log file
+-- App (class)             Wizard steps and download logic
```

---

## License

MIT License. Free to use, modify, and distribute.

---

Made for the Minecraft community.

[Modrinth](https://modrinth.com) · [Fabric](https://fabricmc.net) · [Forge](https://minecraftforge.net) · [NeoForge](https://neoforged.net)
