#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MC Mod Manager v4.0
Minecraft Mod Manager - CLI Edition
"""

import os, sys, json, time, shutil, hashlib, zipfile, re, platform
from pathlib import Path
from datetime import datetime

# ── Auto-install dependencies ──────────────────────────────────────────────────
def _install(pkg, mirror=False):
    import subprocess
    index = " --index-url https://mirror-pypi.runflare.com/simple/" if mirror else ""
    cmd = f"{sys.executable} -m pip install {pkg}{index} --quiet"
    return subprocess.run(cmd, shell=True).returncode == 0

for _pkg in ["requests", "packaging"]:
    try:
        __import__(_pkg)
    except ImportError:
        print(f"  Installing {_pkg}...")
        if not _install(_pkg):
            print(f"  Retrying with mirror...")
            if not _install(_pkg, mirror=True):
                print(f"  ERROR: Could not install {_pkg}. Please run: pip install {_pkg}")
                sys.exit(1)

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from packaging.version import Version

# ── Constants ──────────────────────────────────────────────────────────────────
APP_VER  = "4.0.0"
MODRINTH = "https://api.modrinth.com/v2"
LOADERS  = ["Fabric", "Forge", "NeoForge", "Quilt"]

# ── Terminal helpers ───────────────────────────────────────────────────────────

def clr():
    os.system("cls" if platform.system() == "Windows" else "clear")

def banner(subtitle=""):
    w = 66
    title = f"MC Mod Manager v{APP_VER}"
    print("+" + "-" * w + "+")
    pad = (w - len(title)) // 2
    print("|" + " " * pad + title + " " * (w - pad - len(title)) + "|")
    if subtitle:
        sub = subtitle[:w]
        pad2 = (w - len(sub)) // 2
        print("|" + " " * pad2 + sub + " " * (w - pad2 - len(sub)) + "|")
    print("+" + "-" * w + "+")

def sep(char="-", w=68):
    print(char * w)

def info(msg):  print(f"  [i] {msg}")
def ok(msg):    print(f"  [+] {msg}")
def warn(msg):  print(f"  [!] {msg}")
def err(msg):   print(f"  [x] {msg}")

def prompt(text):
    try:
        return input(f"\n  > {text}").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)

def pause():
    try:
        input("\n  Press Enter to continue...")
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)

def get_default_mc():
    s = platform.system()
    if s == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), ".minecraft")
    elif s == "Darwin":
        return os.path.expanduser("~/Library/Application Support/minecraft")
    return os.path.expanduser("~/.minecraft")

def make_session():
    s = requests.Session()
    r = Retry(total=4, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
    a = HTTPAdapter(max_retries=r)
    s.mount("http://", a)
    s.mount("https://", a)
    s.headers["User-Agent"] = f"MCModManager/{APP_VER}"
    return s

def compute_sha512(path):
    h = hashlib.sha512()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
    except:
        pass
    return h.hexdigest()

def fmt_size(b):
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}TB"

# ── Mod metadata scanner ───────────────────────────────────────────────────────

class Mod:
    __slots__ = ("filename", "path", "name", "mod_id", "version", "mc_versions",
                 "loader", "desc", "sha512", "project_id", "new_version",
                 "new_url", "status")

    def __init__(self):
        for s in self.__slots__:
            setattr(self, s, "")
        self.mc_versions = []
        self.status = "pending"

def _stem_clean(filename):
    s = Path(filename).stem
    s = re.sub(r"[-_](fabric|forge|neoforge|quilt|mc[\d.]+|[\d.+]+)$", "", s, flags=re.I)
    return s.replace("-", " ").replace("_", " ").strip().title()

def parse_jar(path):
    m = Mod()
    m.path = path
    m.filename = Path(path).name
    m.sha512 = compute_sha512(path)
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()

            # Fabric
            if "fabric.mod.json" in names:
                d = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"))
                m.mod_id  = d.get("id", "")
                m.name    = d.get("name", m.mod_id)
                m.version = str(d.get("version", ""))
                m.loader  = "Fabric"
                m.desc    = d.get("description", "")
                mc = d.get("depends", {}).get("minecraft", "")
                m.mc_versions = [mc] if isinstance(mc, str) and mc else (mc if isinstance(mc, list) else [])

            # NeoForge
            elif "META-INF/neoforge.mods.toml" in names:
                m.loader = "NeoForge"
                _parse_toml(z, "META-INF/neoforge.mods.toml", m)

            # Forge
            elif "META-INF/mods.toml" in names:
                m.loader = "Forge"
                _parse_toml(z, "META-INF/mods.toml", m)

            # Quilt
            elif "quilt.mod.json" in names:
                d = json.loads(z.read("quilt.mod.json").decode("utf-8", "replace"))
                ql = d.get("quilt_loader", {})
                m.mod_id  = ql.get("id", "")
                m.name    = ql.get("metadata", {}).get("name", m.mod_id)
                m.version = str(ql.get("version", ""))
                m.loader  = "Quilt"
                m.desc    = ql.get("metadata", {}).get("description", "")

            # Manifest fallback
            if not m.version and "META-INF/MANIFEST.MF" in names:
                for line in z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace").splitlines():
                    if line.startswith("Implementation-Version:"):
                        m.version = line.split(":", 1)[1].strip()
                        break

    except (zipfile.BadZipFile, Exception):
        pass

    if not m.name:   m.name   = _stem_clean(m.filename)
    if not m.mod_id: m.mod_id = m.name.lower().replace(" ", "-")
    return m

def _parse_toml(zf, fname, m):
    try:
        raw = zf.read(fname).decode("utf-8", "replace")
        for line in raw.splitlines():
            line = line.strip()
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"\'')
            if k == "modId"      and not m.mod_id:  m.mod_id  = v
            elif k == "version"  and not m.version:  m.version = v.replace("${file.jarVersion}", "").strip()
            elif k == "displayName" and not m.name:  m.name    = v
    except:
        pass

def scan_mods(folder):
    mods = []
    mods_dir = os.path.join(folder, "mods")
    scan_path = mods_dir if os.path.isdir(mods_dir) else folder
    if not os.path.isdir(scan_path):
        return mods
    for f in sorted(os.listdir(scan_path)):
        if f.lower().endswith(".jar"):
            mods.append(parse_jar(os.path.join(scan_path, f)))
    return mods

# ── Modrinth API ───────────────────────────────────────────────────────────────

class Modrinth:
    def __init__(self, sess):
        self.s = sess

    def mc_versions(self):
        try:
            r = self.s.get(f"{MODRINTH}/tag/game_version", timeout=12)
            if r.ok:
                return [v["version"] for v in r.json() if v.get("version_type") == "release"]
        except:
            pass
        return ["1.21.4", "1.21.3", "1.21.1", "1.21", "1.20.6", "1.20.4",
                "1.20.1", "1.20", "1.19.4", "1.19.2", "1.19", "1.18.2",
                "1.18", "1.17.1", "1.16.5", "1.15.2", "1.14.4", "1.12.2", "1.8.9"]

    def by_hash(self, sha512):
        try:
            r = self.s.get(f"{MODRINTH}/version_file/{sha512}",
                           params={"algorithm": "sha512"}, timeout=10)
            return r.json() if r.ok else None
        except:
            return None

    def latest(self, pid, game_ver, loader):
        try:
            p = {"game_versions": json.dumps([game_ver])}
            if loader:
                p["loaders"] = json.dumps([loader.lower()])
            r = self.s.get(f"{MODRINTH}/project/{pid}/version", params=p, timeout=10)
            if r.ok and r.json():
                return r.json()[0]
        except:
            pass
        return None

    def search(self, query, loader, game_ver):
        try:
            facets = [["project_type:mod"]]
            if loader:
                facets.append([f"categories:{loader.lower()}"])
            if game_ver:
                facets.append([f"versions:{game_ver}"])
            r = self.s.get(f"{MODRINTH}/search",
                           params={"query": query, "limit": 5, "facets": json.dumps(facets)},
                           timeout=10)
            hits = r.json().get("hits", []) if r.ok else []
            return hits[0] if hits else None
        except:
            return None

    def resolve(self, mod, game_ver, loader):
        pid = None

        fv = self.by_hash(mod.sha512)
        if fv:
            pid = fv.get("project_id", "")

        if not pid and mod.project_id:
            pid = mod.project_id

        if not pid:
            h = self.search(mod.mod_id, loader, game_ver)
            if h:
                pid = h.get("project_id", "")

        if not pid and mod.name != mod.mod_id:
            h = self.search(mod.name, loader, game_ver)
            if h:
                pid = h.get("project_id", "")

        if not pid:
            return None

        mod.project_id = pid
        return self.latest(pid, game_ver, loader)

# ── Download ───────────────────────────────────────────────────────────────────

def download_file(sess, url, dest):
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        r = sess.get(url, stream=True, timeout=90)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done  = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done / total * 100
                        filled = int(pct / 2)
                        bar = "#" * filled + "-" * (50 - filled)
                        print(f"\r     [{bar}] {pct:5.1f}%  {fmt_size(done)}/{fmt_size(total)}", end="", flush=True)
        print()
        return True
    except Exception as e:
        print()
        return str(e)

# ── Logger ─────────────────────────────────────────────────────────────────────

class Logger:
    def __init__(self):
        self._lines = []
        self._path  = None

    def log(self, msg, level="INFO"):
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}][{level}] {msg}"
        self._lines.append(line)

    def set_path(self, path):
        self._path = path

    def save(self):
        if not self._path:
            return
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(f"MC Mod Manager v{APP_VER}\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n")
                f.write("\n".join(self._lines))
        except:
            pass

# ══════════════════════════════════════════════════════════════════════════════
# Main App  -  Linear wizard flow
# ══════════════════════════════════════════════════════════════════════════════

class App:
    def __init__(self):
        self.folder = ""
        self.ver    = ""
        self.loader = ""
        self.mods   = []
        self.sess   = make_session()
        self.mr     = Modrinth(self.sess)
        self.log    = Logger()

    # ── Entry point ───────────────────────────────────────────────────────────
    def run(self):
        clr()
        banner("Minecraft Mod Manager")
        print()
        print("  This tool scans your mods folder, checks Modrinth for the")
        print("  latest versions, and downloads them into a clean output folder.")
        print()
        sep()

        self._step_folder()
        self._step_version()
        self._step_loader()
        self._step_scan()
        self._step_confirm()
        self._step_download()

    # ── Step 1: Folder ────────────────────────────────────────────────────────
    def _step_folder(self):
        clr()
        banner("Step 1 of 4 -- Select Minecraft Folder")
        default = get_default_mc()
        print()
        print(f"  Default folder: {default}")
        print()
        print("  [1]  Use default folder")
        print("  [2]  Enter a custom path")
        sep()

        while True:
            ch = prompt("Enter choice [1/2]:")
            if ch == "1":
                if os.path.isdir(default):
                    self.folder = default
                    ok(f"Using: {self.folder}")
                    break
                else:
                    warn(f"Default folder not found: {default}")
                    warn("Please enter a custom path.")
                    ch = "2"

            if ch == "2":
                p = prompt("Enter folder path:")
                p = os.path.expanduser(p)
                if os.path.isdir(p):
                    self.folder = p
                    ok(f"Using: {self.folder}")
                    break
                else:
                    err(f"Folder not found: {p}")
            else:
                warn("Please enter 1 or 2.")

        pause()

    # ── Step 2: MC Version ────────────────────────────────────────────────────
    def _step_version(self):
        clr()
        banner("Step 2 of 4 -- Select Target Minecraft Version")
        print()
        info("Fetching version list from Modrinth...")
        ver_list = self.mr.mc_versions()
        print()

        # Show top 20 common versions
        top = ver_list[:20]
        for i, v in enumerate(top, 1):
            print(f"  [{i:>2}]  {v}")
        print()
        print("  Or type any version manually (e.g. 1.21.4)")
        sep()

        while True:
            ch = prompt("Enter number or version string:")
            # Try as list index
            try:
                idx = int(ch) - 1
                if 0 <= idx < len(top):
                    self.ver = top[idx]
                    ok(f"Target version: {self.ver}")
                    break
            except ValueError:
                pass
            # Try as version string
            if re.match(r"^\d+\.\d+", ch):
                self.ver = ch
                ok(f"Target version: {self.ver}")
                break
            warn("Invalid input. Enter a number from the list or a version like 1.21.4")

        pause()

    # ── Step 3: Loader ────────────────────────────────────────────────────────
    def _step_loader(self):
        clr()
        banner("Step 3 of 4 -- Select Mod Loader")
        print()
        for i, l in enumerate(LOADERS, 1):
            print(f"  [{i}]  {l}")
        sep()

        while True:
            ch = prompt("Enter choice [1-4]:")
            try:
                idx = int(ch) - 1
                if 0 <= idx < len(LOADERS):
                    self.loader = LOADERS[idx]
                    ok(f"Loader: {self.loader}")
                    break
            except ValueError:
                pass
            warn("Please enter a number between 1 and 4.")

        pause()

    # ── Step 4: Scan ──────────────────────────────────────────────────────────
    def _step_scan(self):
        clr()
        banner("Step 4 of 4 -- Scanning Mods Folder")
        print()
        info(f"Scanning: {self.folder}")
        print()

        self.mods = scan_mods(self.folder)

        if not self.mods:
            warn("No .jar files found in the mods folder.")
            warn("Make sure the folder contains a 'mods' subdirectory with .jar files.")
            pause()
            sys.exit(0)

        ok(f"Found {len(self.mods)} mod(s).")
        self.log.log(f"Scanned: {len(self.mods)} mods")
        print()

        # Check for updates
        info(f"Checking Modrinth for {self.ver} / {self.loader} versions...")
        print()

        total  = len(self.mods)
        avail  = 0
        uptodt = 0
        notfnd = 0

        for i, m in enumerate(self.mods, 1):
            label = f"[{i}/{total}] {m.name or m.filename}"
            print(f"  {label:<50}", end="", flush=True)

            ver_data = self.mr.resolve(m, self.ver, self.loader)
            if ver_data:
                files = ver_data.get("files", [])
                prim  = next((f for f in files if f.get("primary")), files[0] if files else None)
                m.new_version = ver_data.get("version_number", "")
                m.new_url     = prim["url"] if prim else ""
                if m.new_version == m.version:
                    m.status = "up_to_date"
                    uptodt += 1
                    print(f"  up-to-date ({m.version})")
                else:
                    m.status = "available"
                    avail += 1
                    print(f"  update available -> {m.new_version}")
            else:
                m.status = "not_found"
                notfnd += 1
                print("  not found on Modrinth")

            self.log.log(f"Check [{m.status}] {m.name} -> {m.new_version or 'N/A'}")

        sep()
        print()
        ok(f"Results: {avail} update(s) available, {uptodt} up-to-date, {notfnd} not found.")
        print()
        pause()

    # ── Step 5: Confirm ───────────────────────────────────────────────────────
    def _step_confirm(self):
        clr()
        banner("Confirm Download")
        print()

        # Print summary table
        col_n = 35
        col_v = 20
        col_s = 14
        header = f"  {'Mod':<{col_n}} {'Current':<{col_v}} {'Status':<{col_s}} New Version"
        print(header)
        sep("-", len(header) + 14)

        downloadable = 0
        for m in self.mods:
            name   = (m.name or m.filename)[:col_n - 1]
            cur    = (m.version or "?")[:col_v - 1]
            if m.status == "available":
                status = "UPDATE"
                downloadable += 1
            elif m.status == "up_to_date":
                status = "up-to-date"
                downloadable += 1
            else:
                status = "not found"
            new_v = m.new_version or ""
            print(f"  {name:<{col_n}} {cur:<{col_v}} {status:<{col_s}} {new_v}")

        sep()
        print()

        out_folder = os.path.join(self.folder, f"MC_{self.ver}_{self.loader}")
        info(f"Output folder: {out_folder}")
        info(f"Total to download/copy: {downloadable} mod(s)")
        print()

        ch = prompt("Proceed with download? [y/n]:")
        if ch.lower() not in ("y", "yes"):
            print()
            warn("Aborted.")
            sys.exit(0)

    # ── Step 6: Download ──────────────────────────────────────────────────────
    def _step_download(self):
        clr()
        banner("Downloading Mods")
        print()

        out_folder = os.path.join(self.folder, f"MC_{self.ver}_{self.loader}")
        mods_out   = os.path.join(out_folder, "mods")
        os.makedirs(mods_out, exist_ok=True)

        log_path = os.path.join(out_folder, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        self.log.set_path(log_path)
        self.log.log(f"Output: {out_folder}")

        ok(f"Output folder created: {out_folder}")
        print()
        sep()

        total   = len(self.mods)
        success = 0
        skipped = 0

        for i, m in enumerate(self.mods, 1):
            name = m.name or m.filename
            print()
            print(f"  [{i}/{total}] {name}")

            if m.status == "not_found" or not m.new_url:
                if m.status == "up_to_date" and not m.new_url:
                    # Copy existing file unchanged
                    if os.path.isfile(m.path):
                        shutil.copy2(m.path, os.path.join(mods_out, m.filename))
                        info(f"Copied (already up-to-date): {m.filename}")
                        success += 1
                        self.log.log(f"Copied: {m.filename}")
                    continue
                warn(f"Skipping: not found on Modrinth for {self.ver} / {self.loader}")
                skipped += 1
                self.log.log(f"Skipped: {name}", "WARN")
                continue

            if m.status == "up_to_date":
                # Download the confirmed-same version to keep the output folder self-contained
                info(f"Already up-to-date ({m.version}), downloading to output folder...")
            else:
                info(f"Downloading version {m.new_version}...")

            self.log.log(f"Downloading: {name} -> {m.new_version}")
            fname  = m.new_url.split("/")[-1].split("?")[0]
            dest   = os.path.join(mods_out, fname)
            result = download_file(self.sess, m.new_url, dest)

            if result is True:
                ok(f"Done: {fname}")
                success += 1
                self.log.log(f"OK: {name} v{m.new_version}")
            else:
                err(f"Failed: {result}")
                self.log.log(f"Error: {name}: {result}", "ERROR")

        print()
        sep()
        print()
        ok(f"Finished: {success}/{total} mods downloaded successfully. {skipped} skipped.")
        ok(f"Output folder: {out_folder}")
        self.log.save()
        ok(f"Log saved: {log_path}")
        print()
        pause()


# ── Entry ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        App().run()
    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(0)
