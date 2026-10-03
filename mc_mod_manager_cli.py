"""
1amir2026 GOD lol
"""

import atexit, bisect, builtins, random, os, sys, json, time, shutil, hashlib, zipfile, re, platform, struct, threading, traceback, math
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from datetime import datetime
from urllib.parse import quote


def _install(pkg, mirror=False):
    import subprocess
    index = " --index-url https://mirror-pypi.runflare.com/simple/" if mirror else ""
    cmd = f"{sys.executable} -m pip install {pkg}{index} --quiet"
    return subprocess.run(cmd, shell=True).returncode == 0

for _pkg in ["requests"]:
    try:
        __import__(_pkg)
    except ImportError:
        print(f"  Installing {_pkg}...")
        if not _install(_pkg):
            print("  Retrying with mirror...")
            if not _install(_pkg, mirror=True):
                print(f"  ERROR: Could not install {_pkg}. Please run: pip install {_pkg}")
                sys.exit(1)

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

APP_VER    = "6.0.1"
MODRINTH   = "https://api.modrinth.com/v2"
CURSEFORGE = "https://api.curseforge.com/v1"
LOADERS    = ["Fabric", "Forge", "NeoForge", "Quilt"]

CF_GAME_ID    = 432
CF_CLASS_MODS = 6
CF_LOADER_IDS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
CF_LOADER_TAG = {"forge": "Forge", "fabric": "Fabric", "quilt": "Quilt", "neoforge": "NeoForge"}

CONFIG_PATH     = Path.home() / ".mc_mod_manager.json"

# The CurseForge key is NOT stored in this file. The release build generates
# _cf_secret.py from a GitHub secret (see make_secret.py / build.yml).
try:
    from _cf_secret import _A as _CF_A, _B as _CF_B
except ImportError:
    _CF_A = _CF_B = ""


def get_curseforge_key():
    """Returns (key, origin). Origin is only ever used for logging, never the key."""
    try:
        import base64
        pad, blob = base64.b64decode(_CF_A), base64.b64decode(_CF_B)
        if pad and blob:
            key = bytes(b ^ pad[i % len(pad)] for i, b in enumerate(blob)).decode("utf-8").strip()
            if key:
                return key, "embedded"
    except Exception:
        pass
    # Developer convenience when running from source; never prompts the user.
    key = os.environ.get("CURSEFORGE_API_KEY", "").strip()
    if key:
        return key, "environment (dev)"
    return "", "none"
MATCH_THRESHOLD = 0.72
DL_ATTEMPTS     = 3
STOP_WORDS      = {"the", "a", "an", "of", "for", "and", "mod"}


class Logger:
    def __init__(self):
        self._buffer = []
        self._all = []
        self._fh = None
        self._lock = threading.Lock()
        self.path = None
        self.context = {}
        self.counts = {"DEBUG": 0, "INFO": 0, "WARN": 0, "ERROR": 0}

    def log(self, msg, level="INFO"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        lines = str(msg).splitlines() or [""]
        text = f"{ts} [{level:<5}] {lines[0]}"
        if len(lines) > 1:
            text += "\n" + "\n".join(" " * 32 + ln for ln in lines[1:])
        with self._lock:
            self.counts[level] = self.counts.get(level, 0) + 1
            self._all.append(text)
            if self._fh:
                self._write(text)

    def debug(self, msg): self.log(msg, "DEBUG")
    def info(self, msg):  self.log(msg, "INFO")
    def warn(self, msg):  self.log(msg, "WARN")
    def error(self, msg): self.log(msg, "ERROR")

    def _write(self, text):
        try:
            self._fh.write(text + "\n")
            self._fh.flush()
        except OSError:
            pass

    def set_path(self, path):
        with self._lock:
            if self._fh:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
            try:
                fh = open(path, "w", encoding="utf-8")
            except OSError:
                return False
            self._fh = fh
            self.path = path
            self._write(f"MC Mod Manager v{APP_VER}")
            self._write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._write(f"Python: {platform.python_version()} on {platform.platform()}")
            self._write(f"requests: {requests.__version__}")
            for k, v in self.context.items():
                self._write(f"{k}: {v}")
            self._write("=" * 72)
            for text in self._all:
                self._write(text)
        return True

    def section(self, title):
        self.log("", "INFO")
        self.log(f"===== {title} =====", "INFO")

    def close(self):
        with self._lock:
            if self._fh:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None


def enable_ansi():
    if platform.system() != "Windows":
        return True
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def smooth_console():
    """Best effort: UTF-8 output and a smooth TrueType console font (Consolas) on Windows.
    Windows Terminal ignores the font part and uses its own font setting."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if platform.system() != "Windows" or not sys.stdout.isatty():
        return
    try:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class FONTINFOEX(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("nFont", ctypes.c_ulong),
                        ("dwFontSize", COORD), ("FontFamily", ctypes.c_uint),
                        ("FontWeight", ctypes.c_uint), ("FaceName", ctypes.c_wchar * 32)]

        k = ctypes.windll.kernel32
        k.GetStdHandle.restype = wintypes.HANDLE
        h = k.GetStdHandle(-11)
        fi = FONTINFOEX()
        fi.cbSize = ctypes.sizeof(FONTINFOEX)
        if not k.GetCurrentConsoleFontEx(h, False, ctypes.byref(fi)):
            return
        if fi.FaceName in ("Consolas", "Cascadia Mono", "Cascadia Code", "Lucida Console"):
            return
        fi.FaceName = "Consolas"
        fi.FontFamily = 54
        fi.FontWeight = 400
        fi.dwFontSize = COORD(0, max(fi.dwFontSize.Y, 18))
        k.SetCurrentConsoleFontEx(h, False, ctypes.byref(fi))
    except Exception:
        pass


def fmt_size(b):
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}TB"

def fmt_dur(seconds):
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{sec:02d}s"
    if m:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"

def fmt_took(seconds):
    return f"{seconds:.1f}s" if seconds < 10 else fmt_dur(seconds)


class Live:
    def __init__(self):
        self.enabled = sys.stdout.isatty() and enable_ansi()
        self.active = False
        self.t0 = None
        self.progress = None
        self.drawn = 0
        self.last_draw = 0.0
        self.stopped_at = None
        self.skipped = 0.0
        self.word_order = []
        self.lock = threading.RLock()
        self.stop_evt = threading.Event()
        self.thread = None

    def width(self):
        return max(20, shutil.get_terminal_size((80, 20)).columns - 1)

    def reset(self):
        self.t0 = time.monotonic()
        self.skipped = 0.0
        self.stopped_at = None

    def elapsed(self):
        if not self.t0:
            return 0.0
        now = self.stopped_at if self.stopped_at else time.monotonic()
        return now - self.t0 - self.skipped

    def _w(self, text):
        getattr(sys.stdout, "write_plain", sys.stdout.write)(text)
        sys.stdout.flush()

    def _lines(self):
        w = self.width()
        lines = []
        if self.progress:
            lines.append(colorize(self.progress[:w]))
        lines.append(self._status_line(w))
        return lines

    def _status_line(self, w):
        head = f"  [{info_icon(self.enabled)}] "
        tail = f" [{fmt_dur(self.elapsed())}]"
        if not self.enabled:
            return colorize((head + tail.lstrip())[:w])
        if not self.word_order:
            self.word_order = random.sample(range(len(STATUS_WORDS)), len(STATUS_WORDS))
        word = STATUS_WORDS[self.word_order[int(self.elapsed() / STATUS_WORD_TIME) % len(self.word_order)]] + "\u2026"
        if len(head) + 2 + len(word) + len(tail) > w:
            return colorize((head + tail.lstrip())[:w])
        return colorize(head) + status_text(word) + colorize(tail)

    def _erase(self):
        if not self.drawn:
            return
        self._w("\r\x1b[2K" + "\x1b[1A\x1b[2K" * (self.drawn - 1) + "\r")
        self.drawn = 0

    def _draw(self, lines):
        self._w("\n".join(lines))
        self.drawn = len(lines)

    def _refresh(self):
        lines = self._lines()
        if len(lines) != self.drawn:
            self._erase()
            self._draw(lines)
            return
        buf = f"\x1b[{self.drawn - 1}A" if self.drawn > 1 else ""
        buf += "\r" + "\n".join("\x1b[2K" + ln for ln in lines)
        self._w(buf)

    def _run(self):
        while not self.stop_evt.wait(STATUS_TICK):
            with self.lock:
                if self.active and self.enabled:
                    self._refresh()

    def start(self):
        with self.lock:
            if self.t0 is None:
                self.t0 = time.monotonic()
            if self.stopped_at:
                self.skipped += time.monotonic() - self.stopped_at
                self.stopped_at = None
            self.active = True
            self.progress = None
            if self.enabled:
                self._draw(self._lines())
                self.stop_evt.clear()
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()

    def stop(self):
        with self.lock:
            if not self.active:
                return
            self.active = False
            self.progress = None
            final = self.elapsed()
            self.stopped_at = time.monotonic()
            if self.enabled:
                self._erase()
        self.stop_evt.set()
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        print(f"  [i] [{fmt_dur(final)}]", flush=True)

    def set_progress(self, text):
        with self.lock:
            self.progress = text
            if not (self.active and self.enabled):
                return
            now = time.monotonic()
            if text is None or now - self.last_draw >= 0.1:
                self.last_draw = now
                self._refresh()

    def emit(self, msg):
        with self.lock:
            if self.active and self.enabled:
                self._erase()
                print(msg, flush=True)
                self._draw(self._lines())
            else:
                print(msg, flush=True)


LOG  = Logger()
LIVE = Live()


def clr():
    with ICONS.lock:
        os.system("cls" if platform.system() == "Windows" else "clear")
        ICONS.reset()
    soft_on()

def out(msg=""):
    LIVE.emit(msg)

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
    out(char * w)

def info(msg):  out(f"  [i] {msg}")
def ok(msg):    out(f"  [+] {msg}")
def warn(msg):  out(f"  [!] {msg}")
def err(msg):   out(f"  [x] {msg}")

_COLOR = sys.stdout.isatty() and enable_ansi()

SOFT_FG   = "\033[38;5;252m"
SOFT_HINT = "\033[38;5;222m"
SOFT_ICON = "\033[38;5;153m"
RESET     = "\033[0m"

I_FRAMES     = ["i", "\u00ef", "\u0131", "\u00a1", "\u0131", "\u00ef"]
I_COLORS     = [93, 97, 97, 96, 97, 93]
I_FRAME_TIME = 0.14

ARROW_REST = " > "
ARROW_FRAMES = (
    [ARROW_REST] * 4
    + [" \u00b7 ", " \u2022 ", " \u25cf ", "(\u25cf)"]
    + ["-\u25cf-", "\\\u25cf/", "|\u25cf|", "/\u25cf\\"] * 2
    + ["(\u25cf)", " \u25cf ", " \u2022 ", " \u00b7 "]
)
ARROW_FRAME_TIME = 0.08

STATUS_WORDS = [
    "Harmonizing", "Pondering", "Cogitating", "Noodling", "Simmering", "Percolating",
    "Synthesizing", "Conjuring", "Untangling", "Marinating", "Reticulating", "Brewing",
    "Ruminating", "Tinkering", "Mulling", "Calibrating", "Weaving", "Crunching",
]
STATUS_WORD_TIME = 3.5
STATUS_TICK      = 0.09
STAR_TIME        = 0.12
STAR_TONE        = "\033[38;5;216m"
STAR_GLOW        = "\033[38;5;230m"
TAG_YELLOW       = "\033[93m"

# Brand colors for provider tags (truecolor where supported, 256-color fallback otherwise)
_TRUECOLOR        = platform.system() == "Windows" or os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
MODRINTH_GREEN    = "\033[38;2;27;217;106m" if _TRUECOLOR else "\033[38;5;41m"      # #1bd96a
CURSEFORGE_ORANGE = "\033[38;2;241;100;54m" if _TRUECOLOR else "\033[38;5;202m"     # #f16436
PROVIDER_COLORS   = {"Modrinth": MODRINTH_GREEN, "CurseForge": CURSEFORGE_ORANGE}
GRAY_FAINT        = "\033[38;5;240m"

def provider_tag(name):
    c = PROVIDER_COLORS.get(name)
    return f"{c}[{name}]{SOFT_FG}" if (_COLOR and c) else f"[{name}]"

# [+] animation: (glyph, ansi color, seconds). Edit the three phases to retune it.
#   1) slow spin  + x + x +
#   2) sudden X, spinning speeds up
#   3) circle, pulsing slows down
# The full cycle then plays forward, backward, forward... (ping-pong).
def _plus_cycle():
    fwd = [(g, 93, 0.22) for g in ("+", "\u00d7", "+", "\u00d7", "+")]
    for k, d in enumerate((0.14, 0.12, 0.10, 0.08, 0.065, 0.05, 0.04, 0.035, 0.035, 0.035)):
        fwd.append(("X" if k % 2 == 0 else "+", 97, d))
    for k, d in enumerate((0.04, 0.05, 0.07, 0.09, 0.12, 0.16, 0.22, 0.30)):
        fwd.append(("O" if k % 2 == 0 else "o", 96, d))
    return fwd + fwd[-2:0:-1]

PLUS_CYCLE = _plus_cycle()
PLUS_ENDS  = []
_t = 0.0
for _g, _c, _d in PLUS_CYCLE:
    _t += _d
    PLUS_ENDS.append(_t)
PLUS_TOTAL = _t
ICON_TICK  = 0.03

def plus_frame(now=None):
    t = (time.monotonic() if now is None else now) % PLUS_TOTAL
    return PLUS_CYCLE[min(bisect.bisect_right(PLUS_ENDS, t), len(PLUS_CYCLE) - 1)]

_FANCY_STARS = platform.system() != "Windows" or bool(os.environ.get("WT_SESSION"))
_STAR_BASE   = ["\u00b7", "\u2722", "*", "\u2736", "\u273b", "\u273d"] if _FANCY_STARS else ["\u00b7", "\u2022", "\u25cf", "*"]
STAR_FRAMES  = _STAR_BASE + _STAR_BASE[-2:0:-1]

def status_text(word):
    now = time.monotonic()
    star = STAR_FRAMES[int(now / STAR_TIME) % len(STAR_FRAMES)]
    pos = int(now / 0.09) % (len(word) + 6) - 3
    chars = []
    for j, ch in enumerate(word):
        chars.append((STAR_GLOW if abs(j - pos) <= 1 else STAR_TONE) + ch)
    return f"{STAR_TONE}{star} " + "".join(chars) + SOFT_FG

def soft_on():
    if _COLOR:
        sys.stdout.write(SOFT_FG)
        sys.stdout.flush()

def soft_off():
    if _COLOR:
        sys.stdout.write(RESET)
        sys.stdout.flush()

def info_icon(animated=True):
    if not animated:
        return "i"
    return I_FRAMES[int(time.monotonic() / I_FRAME_TIME) % len(I_FRAMES)]

def yellow(text):
    return f"{SOFT_HINT}{text}{SOFT_FG}" if _COLOR else text

class ArrowAnim:
    def __init__(self):
        self.stop_evt = threading.Event()
        self.thread = None

    def _run(self):
        i = 0
        while not self.stop_evt.is_set():
            frame = ARROW_FRAMES[i % len(ARROW_FRAMES)]
            sys.stdout.write(f"\x1b7\x1b[2G{SOFT_ICON}{frame}{SOFT_FG}\x1b8")
            sys.stdout.flush()
            i += 1
            self.stop_evt.wait(ARROW_FRAME_TIME)

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_evt.set()
        if self.thread:
            self.thread.join(timeout=1)
            self.thread = None

def prompt(text):
    animate = _COLOR and sys.stdin.isatty()
    try:
        if not animate:
            return input(colorize(f"\n  > {text}")).strip()
        sys.stdout.write(f"\n {SOFT_ICON}{ARROW_REST}{SOFT_FG} {colorize(text)}")
        sys.stdout.flush()
        anim = ArrowAnim()
        anim.start()
        line0 = ICONS.line
        ICONS.typing = True
        try:
            raw_typed = input()
        except (KeyboardInterrupt, EOFError):
            ICONS.typing = False
            anim.stop()
            sys.stdout.write(f"\x1b[2G{ARROW_REST}")
            raise
        ICONS.typing = False
        ICONS.typed(raw_typed)
        typed = raw_typed.strip()
        anim.stop()
        sys.stdout.write("\r\x1b[2K")
        tracked = isinstance(sys.stdout, OutProxy)
        width = shutil.get_terminal_size((80, 20)).columns
        rows = max(1, ICONS.line - line0) if tracked else 1
        if (tracked and rows <= ICONS.srow) or (not tracked and 1 + len(ARROW_REST) + 1 + len(text) + len(typed) + 2 < width):
            sys.stdout.write(f"\x1b[{rows}A\x1b[2G{ARROW_REST}\x1b[{rows}B\r")
        sys.stdout.flush()
        return typed
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)

_ESC_RE = re.compile(r"\x1b(?:\[([0-9;?]*)([A-Za-z])|([78])|\][^\x07\x1b]*(?:\x07|\x1b\\)|[()][0-9A-Za-z])")

class IconBoard:
    def __init__(self):
        self.raw = None
        self.lock = threading.RLock()
        self.typing = False
        self.stopped = False
        self.thread = None
        self.icons = {}
        self.shown = {}
        self.width = 80
        self.height = 24
        self.reset()

    def reset(self):
        self.line = 0
        self.col = 0
        self.srow = 0
        self.last = ""
        self.saved = (0, 0, 0)
        self.icons.clear()
        self.shown.clear()

    def _size(self):
        sz = shutil.get_terminal_size((80, 24))
        if sz.columns != self.width:
            self.icons.clear()
            self.shown.clear()
            self.width = sz.columns
        self.height = sz.lines

    def feed(self, s, register=True):
        self._size()
        pos = 0
        for m in _ESC_RE.finditer(s):
            if m.start() > pos:
                self._text(s[pos:m.start()], register)
            pos = m.end()
            self._esc(m)
        if pos < len(s):
            self._text(s[pos:], register)

    def _down(self, n):
        self.line += n
        self.srow = min(self.height - 1, self.srow + n)

    def _text(self, t, register):
        for ch in t:
            if ch == "\n":
                self._down(1)
                self.col = 0
                self.last = ""
            elif ch == "\r":
                self.col = 0
                self.last = ""
            elif ch == "\b":
                self.col = max(0, self.col - 1)
                self.last = ""
            elif ch < " ":
                continue
            else:
                if self.col >= self.width:
                    self._down(1)
                    self.col = 0
                    self.last = ""
                self.icons.pop((self.line, self.col), None)
                self.shown.pop((self.line, self.col), None)
                self.last = (self.last + ch)[-3:]
                if register and self.col >= 1 and self.last in ("[i]", "[+]"):
                    key = (self.line, self.col - 1)
                    self.icons[key] = self.last[1]
                    self.shown.pop(key, None)
                self.col += 1

    def _esc(self, m):
        if m.group(3):
            if m.group(3) == "7":
                self.saved = (self.line, self.col, self.srow)
            else:
                self.line, self.col, self.srow = self.saved
            self.last = ""
            return
        cmd = m.group(2)
        if cmd is None:
            return
        args = m.group(1) or ""
        try:
            n = int(args.split(";")[0]) if args and not args.startswith("?") else None
        except ValueError:
            n = None
        k = n if n else 1
        if cmd == "A":
            self.line -= k
            self.srow = max(0, self.srow - k)
            self.last = ""
        elif cmd == "B":
            self._down(k)
            self.last = ""
        elif cmd == "C":
            self.col = min(self.width, self.col + k)
            self.last = ""
        elif cmd == "D":
            self.col = max(0, self.col - k)
            self.last = ""
        elif cmd == "G":
            self.col = min(self.width - 1, max(0, k - 1))
            self.last = ""
        elif cmd == "K":
            mode = n or 0
            for key in list(self.icons):
                if key[0] == self.line and (mode == 2 or (mode == 0 and key[1] >= self.col) or (mode == 1 and key[1] <= self.col)):
                    del self.icons[key]
        elif cmd == "J":
            mode = n or 0
            if mode == 2:
                self.icons.clear()
            else:
                for key in list(self.icons):
                    if key[0] > self.line or (key[0] == self.line and key[1] >= self.col):
                        del self.icons[key]

    def typed(self, text):
        with self.lock:
            self.feed(text + "\n", register=False)

    def clear_screen(self):
        with self.lock:
            self.reset()

    def start(self, raw):
        self.raw = raw
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while True:
            time.sleep(ICON_TICK)
            with self.lock:
                if self.typing or self.stopped or not self.icons:
                    continue
                self._size()
                now = time.monotonic()
                idx = int(now / I_FRAME_TIME) % len(I_FRAMES)
                i_frame = (I_FRAMES[idx], I_COLORS[idx])
                p_glyph, p_color, _ = plus_frame(now)
                p_frame = (p_glyph, p_color)
                parts = []
                for key, kind in list(self.icons.items()):
                    ln, col = key
                    d = self.line - ln
                    if d < 0 or d >= self.height:
                        del self.icons[key]
                        self.shown.pop(key, None)
                        continue
                    if d > self.srow or col >= self.width:
                        continue
                    frame = p_frame if kind == "+" else i_frame
                    if self.shown.get(key) == frame:
                        continue
                    self.shown[key] = frame
                    up = f"\x1b[{d}A" if d else ""
                    down = f"\x1b[{d}B" if d else ""
                    parts.append(f"{up}\x1b[{col + 1}G\x1b[{frame[1]}m{frame[0]}{down}")
                if not parts:
                    continue
                try:
                    self.raw.write("\x1b7" + "".join(parts) + f"\x1b8{SOFT_FG}")
                    self.raw.flush()
                except Exception:
                    pass

    def restore(self):
        with self.lock:
            self.stopped = True
            if not self.icons:
                return
            self._size()
            parts = []
            for (ln, col), kind in list(self.icons.items()):
                d = self.line - ln
                if 0 <= d <= self.srow and col < self.width:
                    up = f"\x1b[{d}A" if d else ""
                    down = f"\x1b[{d}B" if d else ""
                    parts.append(f"{up}\x1b[{col + 1}G{TAG_YELLOW}{kind}{down}")
            if parts:
                try:
                    self.raw.write("\x1b7" + "".join(parts) + f"\x1b8{RESET}")
                    self.raw.flush()
                except Exception:
                    pass

ICONS = IconBoard()

class OutProxy:
    def __init__(self, raw):
        object.__setattr__(self, "_raw", raw)

    def write(self, s):
        with ICONS.lock:
            n = self._raw.write(s)
            ICONS.feed(s)
            return n

    def write_plain(self, s):
        with ICONS.lock:
            n = self._raw.write(s)
            ICONS.feed(s, register=False)
            return n

    def flush(self):
        with ICONS.lock:
            return self._raw.flush()

    def __getattr__(self, name):
        return getattr(self._raw, name)

def install_info_anim():
    if not _COLOR or isinstance(sys.stdout, OutProxy):
        return
    raw = sys.stdout
    sys.stdout = OutProxy(raw)
    ICONS.start(raw)
    atexit.register(ICONS.restore)

_BRACKET = re.compile(r"\[[^\[\]\x1b]*\]")

def colorize(text):
    """Makes every [bracketed] tag yellow (only on terminals that support colors)."""
    if not _COLOR or not isinstance(text, str) or "\x1b" in text:
        return text
    return _BRACKET.sub(lambda m: f"\x1b[93m{m.group(0)}{SOFT_FG}", text)

_builtin_print = builtins.print

def print(*args, **kwargs):
    _builtin_print(*[colorize(a) for a in args], **kwargs)

def read_key(allow_esc=True):
    """Waits for Enter or Esc without echoing. Returns 'enter' or 'esc'.
    Arrow keys and other keys are ignored. Falls back to input() if stdin is not a terminal."""
    if not sys.stdin.isatty():
        input()
        return "enter"
    if platform.system() == "Windows":
        import msvcrt
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                return "enter"
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch == "\x1b" and allow_esc:
                return "esc"
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()  # second half of an arrow/function key
    import termios, tty, select
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = os.read(fd, 1).decode("utf-8", "ignore")
            if ch in ("\r", "\n"):
                return "enter"
            if ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    while select.select([fd], [], [], 0.02)[0]:
                        os.read(fd, 1)  # arrow key sequence, ignore it
                    continue
                if allow_esc:
                    return "esc"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def pause(esc=False, text="Press Enter to continue..."):
    """Yellow 'Press Enter' line. With esc=True also offers Esc and returns True if it was pressed."""
    sys.stdout.write("\n" + yellow("  " + text + (" (Esc to edit)" if esc else "")))
    sys.stdout.flush()
    try:
        key = read_key(allow_esc=esc)
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)
    print()
    return key == "esc"

def get_default_mc():
    s = platform.system()
    if s == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), ".minecraft")
    elif s == "Darwin":
        return os.path.expanduser("~/Library/Application Support/minecraft")
    return os.path.expanduser("~/.minecraft")

def make_session():
    s = requests.Session()
    kwargs = dict(total=4, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
    try:
        r = Retry(allowed_methods=frozenset({"GET", "POST"}), **kwargs)
    except TypeError:
        r = Retry(method_whitelist=frozenset({"GET", "POST"}), **kwargs)
    a = HTTPAdapter(max_retries=r)
    s.mount("http://", a)
    s.mount("https://", a)
    s.headers["User-Agent"] = f"MCModManager/{APP_VER}"
    return s

def load_config():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError as e:
        LOG.warn(f"Could not save config {CONFIG_PATH}: {e}")
        return False
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return True

def file_hashes(path):
    h512 = hashlib.sha512()
    h1 = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h512.update(chunk)
                h1.update(chunk)
    except OSError as e:
        LOG.error(f"Could not hash {path}: {e}")
        return "", ""
    return h512.hexdigest(), h1.hexdigest()

def hash_file(path, algo):
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()

def cf_fingerprint(data):
    data = data.translate(None, b"\t\n\r ")
    n = len(data)
    m = 0x5BD1E995
    mask = 0xFFFFFFFF
    h = (1 ^ n) & mask
    words = n // 4
    for (k,) in struct.iter_unpack("<I", data[:words * 4]):
        k = (k * m) & mask
        k ^= k >> 24
        k = (k * m) & mask
        h = (h * m) & mask
        h ^= k
    tail = data[words * 4:]
    rem = n & 3
    if rem == 3:
        h ^= tail[2] << 16
    if rem >= 2:
        h ^= tail[1] << 8
    if rem >= 1:
        h ^= tail[0]
        h = (h * m) & mask
    h ^= h >> 13
    h = (h * m) & mask
    h ^= h >> 15
    return h

def safe_filename(name):
    name = Path(str(name).replace("\\", "/")).name
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "mod.jar"


class Mod:
    def __init__(self):
        self.filename = ""
        self.path = ""
        self.name = ""
        self.mod_id = ""
        self.version = ""
        self.desc = ""
        self.loader = ""
        self.sha512 = ""
        self.sha1 = ""
        self.size = 0
        self.mc_versions = []
        self.authors = []
        self.fingerprint = None
        self.hits = {}
        self.status = "pending"
        self.found = None
        self.no_build = None
        self.closest = None
        self.dl = "pending"
        self.dest = ""
        self.error = ""
        self.retryable = False
        self.attempts = 0
        self.retry_rounds = 0
        self.elapsed = 0.0


_VERSION_TAIL = re.compile(r"[-_ .]+(?:fabric|forge|neoforge|quilt|mc[\d.]+|v?\d[\w.]*)$", re.I)

def _stem_clean(filename):
    original = Path(filename).stem
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", original)
    s = re.sub(r"\+.*$", "", s).strip(" -_.")
    while True:
        n = _VERSION_TAIL.sub("", s).strip(" -_.")
        if n == s or not n:
            break
        s = n
    s = s or original
    return re.sub(r"[-_]+", " ", s).strip().title()

def _clean_name(value):
    value = str(value or "").strip()
    return "" if "${" in value else value

def _as_authors(value):
    result = []
    if isinstance(value, str):
        result = [a.strip() for a in value.split(",")]
    elif isinstance(value, list):
        for a in value:
            if isinstance(a, str):
                result.append(a.strip())
            elif isinstance(a, dict) and a.get("name"):
                result.append(str(a["name"]).strip())
    elif isinstance(value, dict):
        result = [str(k).strip() for k in value]
    return [a for a in result if a]

def parse_jar(path):
    m = Mod()
    m.path = path
    m.filename = Path(path).name
    try:
        m.size = os.path.getsize(path)
    except OSError:
        m.size = 0
    m.sha512, m.sha1 = file_hashes(path)
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()

            if "fabric.mod.json" in names:
                d = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"))
                m.mod_id  = d.get("id", "")
                m.name    = _clean_name(d.get("name", "")) or m.mod_id
                m.version = str(d.get("version", ""))
                m.loader  = "Fabric"
                m.desc    = d.get("description", "")
                m.authors = _as_authors(d.get("authors"))
                mc = d.get("depends", {}).get("minecraft", "")
                m.mc_versions = [mc] if isinstance(mc, str) and mc else (mc if isinstance(mc, list) else [])

            elif "META-INF/neoforge.mods.toml" in names:
                m.loader = "NeoForge"
                _parse_toml(z, "META-INF/neoforge.mods.toml", m)

            elif "META-INF/mods.toml" in names:
                m.loader = "Forge"
                _parse_toml(z, "META-INF/mods.toml", m)

            elif "quilt.mod.json" in names:
                d = json.loads(z.read("quilt.mod.json").decode("utf-8", "replace"))
                ql = d.get("quilt_loader", {})
                meta = ql.get("metadata", {})
                m.mod_id  = ql.get("id", "")
                m.name    = _clean_name(meta.get("name", "")) or m.mod_id
                m.version = str(ql.get("version", ""))
                m.loader  = "Quilt"
                m.desc    = meta.get("description", "")
                m.authors = _as_authors(meta.get("contributors"))

            if not m.version and "META-INF/MANIFEST.MF" in names:
                for line in z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace").splitlines():
                    if line.startswith("Implementation-Version:"):
                        m.version = line.split(":", 1)[1].strip()
                        break

    except zipfile.BadZipFile:
        LOG.warn(f"{m.filename}: not a valid zip/jar, using filename only")
    except Exception as e:
        LOG.warn(f"{m.filename}: could not read metadata ({type(e).__name__}: {e}), using filename only")

    if not m.name:   m.name   = _stem_clean(m.filename)
    if not m.mod_id: m.mod_id = m.name.lower().replace(" ", "-")
    return m

def _parse_toml(zf, fname, m):
    try:
        raw = zf.read(fname).decode("utf-8", "replace")
    except (KeyError, OSError) as e:
        LOG.warn(f"{m.filename}: cannot read {fname}: {e}")
        return
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("[[dependencies"):
            break
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"\'')
        if k == "modId"         and not m.mod_id:   m.mod_id  = v
        elif k == "version"     and not m.version:  m.version = v.replace("${file.jarVersion}", "").strip()
        elif k == "displayName" and not m.name:     m.name    = _clean_name(v)
        elif k == "authors"     and not m.authors:  m.authors = _as_authors(v)

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


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in STOP_WORDS}

def search_queries(mod):
    raw = [mod.mod_id, mod.name, _stem_clean(mod.filename),
           re.sub(r"[-_.]+", " ", mod.mod_id),
           re.sub(r"\s*[\(\[].*?[\)\]]", "", mod.name)]
    seen, result = set(), []
    for q in raw:
        q = q.strip()
        k = norm(q)
        if len(k) < 2 or k in seen:
            continue
        seen.add(k)
        result.append(q)
    return result[:4]

def slug_refs(mod):
    refs = []
    for r in (mod.mod_id.lower(), mod.mod_id.lower().replace("_", "-")):
        if re.match(r"^[\w.+\-]{3,64}$", r) and r not in refs:
            refs.append(r)
    return refs

def score_candidate(mod, c):
    mf = {norm(mod.mod_id), norm(mod.name), norm(_stem_clean(mod.filename))} - {""}
    cf = {norm(c.slug), norm(c.title)} - {""}
    if not mf or not cf:
        return 0.0
    if mf & cf:
        base = 1.0
    else:
        fuzzy = max(SequenceMatcher(None, a, b).ratio() for a in mf for b in cf)
        mts = [toks(mod.name), toks(_stem_clean(mod.filename)), toks(mod.mod_id)]
        cts = [toks(c.title), toks(c.slug)]
        jac, pair = 0.0, (set(), set())
        for a in mts:
            for b in cts:
                if a and b:
                    j = len(a & b) / len(a | b)
                    if j > jac:
                        jac, pair = j, (a, b)
        base = min(0.9, 0.7 * fuzzy + 0.3 * jac)
        if any(t.isdigit() for t in pair[0] ^ pair[1]):
            base = min(base, 0.6)
    if mod.authors and c.authors:
        wanted = {norm(a) for a in mod.authors}
        if any(norm(a) in wanted for a in c.authors):
            base += 0.08
    base += min(0.02, math.log10(max(c.downloads, 0) + 1) / 400)
    return round(min(1.0, base), 3)


class Cand:
    def __init__(self, pid, title="", slug="", authors=None, downloads=0, raw=None):
        self.pid = str(pid) if pid is not None else ""
        self.title = title or ""
        self.slug = slug or ""
        self.authors = authors or []
        self.downloads = downloads if isinstance(downloads, (int, float)) else 0
        self.raw = raw or {}
        self.score = 0.0
        self.method = ""


class Found:
    def __init__(self):
        self.provider = ""
        self.project_id = ""
        self.title = ""
        self.slug = ""
        self.version = ""
        self.filename = ""
        self.url = ""
        self.hash_value = ""
        self.hash_algo = ""
        self.size = 0
        self.file_id = ""
        self.channel = "release"
        self.site_url = ""
        self.method = ""
        self.score = 0.0
        self.same_file = False
        self.manual = False


class Http:
    def __init__(self, sess):
        self.s = sess

    def request(self, method, url, params=None, body=None, headers=None, timeout=(10, 30)):
        t = time.monotonic()
        try:
            r = self.s.request(method, url, params=params, json=body, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            ms = (time.monotonic() - t) * 1000
            LOG.error(f"{method} {url} params={params} FAILED after {ms:.0f}ms: {type(e).__name__}: {e}")
            return None
        ms = (time.monotonic() - t) * 1000
        level = "DEBUG" if (r.ok or r.status_code == 404) else "WARN"
        LOG.log(f"{method} {r.url} -> {r.status_code} ({ms:.0f}ms, {len(r.content)}B)", level)
        if not r.ok and r.status_code != 404:
            LOG.warn(f"Response body: {r.text[:300]!r}")
        remaining = r.headers.get("X-Ratelimit-Remaining", "")
        if remaining.isdigit() and int(remaining) <= 2:
            try:
                wait = min(float(r.headers.get("X-Ratelimit-Reset", "5")), 15)
            except ValueError:
                wait = 5
            LOG.warn(f"Rate limit nearly exhausted, sleeping {wait:.0f}s")
            time.sleep(wait)
        return r

    def json(self, method, url, params=None, body=None, headers=None):
        r = self.request(method, url, params=params, body=body, headers=headers)
        if r is None or not r.ok:
            return None
        try:
            return r.json()
        except ValueError:
            LOG.error(f"{method} {url}: invalid JSON in response")
            return None


class Provider:
    name = ""
    progressive = False  # True = prefetch() reports per-mod progress via its callback

    def __init__(self, http):
        self.http = http
        self.enabled = True

    def prefetch(self, mods, progress=None):
        return 0

    def hash_candidates(self, mod):
        return []

    def slug_candidates(self, mod):
        return []

    def search(self, query, ver, loader, with_version):
        return []

    def latest(self, cand, mod, ver, loader):
        return None

    def _search_all(self, mod, ver, loader, with_version):
        pool = {}
        for q in search_queries(mod):
            for c in self.search(q, ver, loader, with_version):
                if not c.pid:
                    continue
                c.score = score_candidate(mod, c)
                if c.pid not in pool or c.score > pool[c.pid].score:
                    pool[c.pid] = c
            if pool and max(c.score for c in pool.values()) >= 0.95:
                break
        ranked = sorted(pool.values(), key=lambda c: -c.score)
        mode = "with version" if with_version else "any version"
        for c in ranked[:5]:
            LOG.debug(f"[{self.name}] search ({mode}) candidate '{c.title}' slug={c.slug} score={c.score:.3f}")
        return ranked

    def resolve(self, mod, ver, loader):
        info_out = {"no_build": None, "closest": None}
        tried = set()
        stages = [
            ("hash",         lambda: self.hash_candidates(mod)),
            ("slug",         lambda: self.slug_candidates(mod)),
            ("search",       lambda: self._search_all(mod, ver, loader, True)),
            ("search-loose", lambda: self._search_all(mod, ver, loader, False)),
        ]
        for method, gather in stages:
            if not self.enabled:
                break
            if method == "search-loose" and info_out["no_build"]:
                break
            for c in gather():
                c.method = method
                if c.pid in tried:
                    continue
                if c.score < MATCH_THRESHOLD:
                    LOG.debug(f"[{self.name}] rejected '{c.title}' ({method}) score={c.score:.3f} < {MATCH_THRESHOLD}")
                    if not info_out["closest"] or c.score > info_out["closest"][1]:
                        info_out["closest"] = (c.title, c.score)
                    continue
                tried.add(c.pid)
                LOG.debug(f"[{self.name}] trying '{c.title}' ({method}) score={c.score:.3f}")
                f = self.latest(c, mod, ver, loader)
                if f:
                    f.method = method
                    f.score = c.score
                    return f, info_out
                LOG.info(f"[{self.name}] '{c.title}' matches {mod.name} but has no build for {ver}/{loader}")
                if not info_out["no_build"]:
                    info_out["no_build"] = c.title
        return None, info_out


def pick_modrinth_version(versions):
    versions = sorted(versions, key=lambda v: v.get("date_published", ""), reverse=True)
    for t in ("release", "beta", "alpha"):
        for v in versions:
            if v.get("version_type") == t:
                return v
    return versions[0]


class ModrinthProvider(Provider):
    name = "Modrinth"
    versions_live = True

    @staticmethod
    def loaders_for(loader):
        l = loader.lower()
        return ["quilt", "fabric"] if l == "quilt" else [l]

    def mc_versions(self):
        data = self.http.json("GET", f"{MODRINTH}/tag/game_version")
        if isinstance(data, list):
            vers = [v["version"] for v in data if v.get("version_type") == "release"]
            if vers:
                self.versions_live = True
                return vers
        self.versions_live = False
        LOG.warn("Using built-in Minecraft version list")
        return ["1.21.4", "1.21.3", "1.21.1", "1.21", "1.20.6", "1.20.4",
                "1.20.1", "1.20", "1.19.4", "1.19.2", "1.19", "1.18.2",
                "1.18", "1.17.1", "1.16.5", "1.15.2", "1.14.4", "1.12.2", "1.8.9"]

    progressive = True

    def prefetch(self, mods, progress=None):
        matched = 0
        for i, m in enumerate(mods):
            if m.sha512:
                v = self.http.json("GET", f"{MODRINTH}/version_file/{m.sha512}",
                                   params={"algorithm": "sha512"})
                if isinstance(v, dict) and v.get("project_id"):
                    m.hits[self.name] = {"pid": v["project_id"], "version": v.get("version_number", "")}
                    matched += 1
                    LOG.debug(f"[{self.name}] hash hit: {m.filename} -> {v['project_id']}")
                else:
                    LOG.debug(f"[{self.name}] hash miss: {m.filename}")
            if progress:
                progress(matched, mods[i + 1].filename if i + 1 < len(mods) else None)
        return matched

    def _project(self, ref):
        data = self.http.json("GET", f"{MODRINTH}/project/{quote(ref, safe='')}")
        return data if isinstance(data, dict) else None

    def hash_candidates(self, mod):
        hit = mod.hits.get(self.name)
        if not hit:
            return []
        p = self._project(hit["pid"]) or {}
        c = Cand(hit["pid"], p.get("title", ""), p.get("slug", ""), [], p.get("downloads", 0), p)
        c.score = 1.0
        return [c]

    def slug_candidates(self, mod):
        result = []
        for ref in slug_refs(mod):
            p = self._project(ref)
            if p and p.get("project_type") == "mod":
                c = Cand(p.get("id"), p.get("title", ""), p.get("slug", ""), [], p.get("downloads", 0), p)
                c.score = score_candidate(mod, c)
                result.append(c)
        return result

    def search(self, query, ver, loader, with_version):
        facets = [["project_type:mod"], [f"categories:{l}" for l in self.loaders_for(loader)]]
        if with_version and ver:
            facets.append([f"versions:{ver}"])
        data = self.http.json("GET", f"{MODRINTH}/search",
                              params={"query": query, "limit": 10, "facets": json.dumps(facets)})
        hits = data.get("hits", []) if isinstance(data, dict) else []
        return [Cand(h.get("project_id"), h.get("title", ""), h.get("slug", ""),
                     [h["author"]] if h.get("author") else [], h.get("downloads", 0), h) for h in hits]

    def latest(self, cand, mod, ver, loader):
        params = {"game_versions": json.dumps([ver]),
                  "loaders": json.dumps(self.loaders_for(loader)),
                  "include_changelog": "false"}
        data = self.http.json("GET", f"{MODRINTH}/project/{cand.pid}/version", params=params)
        if not isinstance(data, list) or not data:
            return None
        v = pick_modrinth_version(data)
        files = v.get("files", [])
        prim = (next((f for f in files if f.get("primary")), None)
                or next((f for f in files if str(f.get("filename", "")).lower().endswith(".jar")), None)
                or (files[0] if files else None))
        if not prim or not prim.get("url"):
            return None
        hashes = prim.get("hashes", {}) or {}
        f = Found()
        f.provider   = self.name
        f.project_id = cand.pid
        f.title      = cand.title
        f.slug       = cand.slug
        f.version    = v.get("version_number", "")
        f.filename   = safe_filename(prim.get("filename") or Path(prim["url"]).name)
        f.url        = prim["url"]
        f.hash_algo  = "sha512" if hashes.get("sha512") else ("sha1" if hashes.get("sha1") else "")
        f.hash_value = hashes.get(f.hash_algo, "").lower() if f.hash_algo else ""
        f.size       = prim.get("size", 0) or 0
        f.file_id    = v.get("id", "")
        f.channel    = v.get("version_type", "release")
        f.site_url   = f"https://modrinth.com/mod/{cand.slug or cand.pid}"
        f.same_file  = bool(mod.sha512) and any(
            (x.get("hashes", {}) or {}).get("sha512", "").lower() == mod.sha512 for x in files)
        return f


def pick_cf_file(files):
    files = sorted(files, key=lambda f: f.get("fileDate", ""), reverse=True)
    for t in (1, 2, 3):
        for f in files:
            if f.get("releaseType") == t:
                return f
    return files[0]


class CurseForgeProvider(Provider):
    name = "CurseForge"

    def __init__(self, http, key):
        super().__init__(http)
        self.key = key

    def _headers(self):
        return {"x-api-key": self.key, "Accept": "application/json"}

    def _call(self, method, path, params=None, body=None, auth_errors=True):
        r = self.http.request(method, CURSEFORGE + path, params=params, body=body, headers=self._headers())
        if r is None:
            return None
        if auth_errors and r.status_code in (401, 403):
            if self.enabled:
                self.enabled = False
                warn("CurseForge became unavailable during the run. CurseForge disabled.")
                LOG.error(f"CurseForge returned {r.status_code}, provider disabled")
            return None
        if not r.ok:
            return None
        try:
            return r.json()
        except ValueError:
            LOG.error(f"CurseForge {path}: invalid JSON in response")
            return None

    def check_key(self):
        r = self.http.request("GET", f"{CURSEFORGE}/games/{CF_GAME_ID}", headers=self._headers())
        if r is None:
            return "unreachable"
        if r.ok:
            return "ok"
        return "invalid" if r.status_code in (401, 403) else "error"

    def prefetch(self, mods, progress=None):
        by_fp = {}
        total = len(mods)
        for i, m in enumerate(mods, 1):
            try:
                with open(m.path, "rb") as fh:
                    m.fingerprint = cf_fingerprint(fh.read())
            except OSError as e:
                LOG.error(f"Fingerprint failed for {m.filename}: {e}")
                continue
            by_fp[m.fingerprint] = m
            print(f"\r  Fingerprinting jars {i}/{total}", end="", flush=True)
        print()
        fps = list(by_fp)
        matched = 0
        for i in range(0, len(fps), 200):
            chunk = fps[i:i + 200]
            data = self._call("POST", f"/fingerprints/{CF_GAME_ID}", body={"fingerprints": chunk})
            if not isinstance(data, dict):
                continue
            for hit in (data.get("data", {}) or {}).get("exactMatches", []) or []:
                f = hit.get("file", {}) or {}
                m = by_fp.get(f.get("fileFingerprint"))
                if m and hit.get("id"):
                    m.hits[self.name] = {"pid": hit["id"], "file_id": f.get("id")}
                    matched += 1
        return matched

    def _cands(self, items):
        result = []
        for d in items or []:
            if d.get("classId") not in (None, CF_CLASS_MODS):
                continue
            authors = [a.get("name", "") for a in (d.get("authors") or []) if isinstance(a, dict)]
            result.append(Cand(d.get("id"), d.get("name", ""), d.get("slug", ""),
                               authors, d.get("downloadCount", 0), d))
        return result

    def hash_candidates(self, mod):
        hit = mod.hits.get(self.name)
        if not hit:
            return []
        data = self._call("GET", f"/mods/{hit['pid']}")
        d = (data or {}).get("data") or {}
        cands = self._cands([d]) if d else [Cand(hit["pid"])]
        for c in cands:
            c.score = 1.0
        return cands

    def slug_candidates(self, mod):
        result = []
        for ref in slug_refs(mod):
            data = self._call("GET", "/mods/search",
                              params={"gameId": CF_GAME_ID, "classId": CF_CLASS_MODS, "slug": ref})
            for c in self._cands((data or {}).get("data")):
                c.score = score_candidate(mod, c)
                result.append(c)
        return result

    def search(self, query, ver, loader, with_version):
        params = {"gameId": CF_GAME_ID, "classId": CF_CLASS_MODS, "searchFilter": query,
                  "sortField": 2, "sortOrder": "desc", "pageSize": 20}
        if with_version and ver:
            params["gameVersion"] = ver
            if loader.lower() != "quilt":
                params["modLoaderType"] = CF_LOADER_IDS[loader.lower()]
        data = self._call("GET", "/mods/search", params=params)
        return self._cands((data or {}).get("data"))

    def _compatible(self, files, ver, ld):
        result = []
        known_tags = set(CF_LOADER_TAG.values())
        for f in files or []:
            if f.get("isAvailable") is False:
                continue
            gv = f.get("gameVersions", []) or []
            if ver not in gv:
                continue
            tags = known_tags & set(gv)
            if tags and CF_LOADER_TAG[ld] not in tags:
                continue
            result.append(f)
        return result

    def latest(self, cand, mod, ver, loader):
        l = loader.lower()
        chosen, used_loader = None, l
        for ld in ([l, "fabric"] if l == "quilt" else [l]):
            data = self._call("GET", f"/mods/{cand.pid}/files",
                              params={"gameVersion": ver, "modLoaderType": CF_LOADER_IDS[ld], "pageSize": 50})
            files = self._compatible((data or {}).get("data"), ver, ld)
            if files:
                chosen, used_loader = pick_cf_file(files), ld
                break
        if not chosen:
            return None
        fid = chosen.get("id")
        url = chosen.get("downloadUrl") or ""
        if not url:
            data = self._call("GET", f"/mods/{cand.pid}/files/{fid}/download-url", auth_errors=False)
            url = (data or {}).get("data") or ""
        sha1 = next((h.get("value", "") for h in chosen.get("hashes", []) if h.get("algo") == 1), "")
        links = cand.raw.get("links", {}) if cand.raw else {}
        site = links.get("websiteUrl", "") if isinstance(links, dict) else ""
        f = Found()
        f.provider   = self.name
        f.project_id = cand.pid
        f.title      = cand.title
        f.slug       = cand.slug
        f.version    = chosen.get("displayName") or chosen.get("fileName", "")
        f.filename   = safe_filename(chosen.get("fileName") or f"{cand.slug or cand.pid}-{fid}.jar")
        f.url        = url
        f.hash_algo  = "sha1" if sha1 else ""
        f.hash_value = sha1.lower()
        f.size       = chosen.get("fileLength", 0) or 0
        f.file_id    = str(fid)
        f.channel    = {1: "release", 2: "beta", 3: "alpha"}.get(chosen.get("releaseType"), "release")
        f.site_url   = f"{site}/files/{fid}" if site else f"https://www.curseforge.com/minecraft/mc-mods/{cand.slug}"
        f.manual     = not url
        hit = mod.hits.get(self.name) or {}
        f.same_file  = (str(hit.get("file_id", "")) == str(fid)
                        or (bool(mod.sha1) and mod.sha1 == f.hash_value)
                        or (not f.hash_value and f.filename == mod.filename))
        if used_loader != l:
            LOG.info(f"[CurseForge] no {loader} file for {cand.title}, using {used_loader} file (Quilt compatibility)")
        return f


class DownloadError(Exception):
    def __init__(self, msg, retryable=True, permanent=False):
        super().__init__(msg)
        self.retryable = retryable
        self.permanent = permanent


def describe_error(e):
    if isinstance(e, requests.exceptions.Timeout):
        return "Timed out"
    if isinstance(e, requests.exceptions.ChunkedEncodingError):
        return "Connection dropped mid-download"
    if isinstance(e, requests.exceptions.SSLError):
        return "SSL error"
    if isinstance(e, requests.exceptions.RetryError):
        return "Server kept returning errors"
    if isinstance(e, requests.exceptions.ConnectionError):
        return "Connection error"
    return type(e).__name__

BAR_FULL  = "\u2588"
BAR_EMPTY = "\u2591"

def show_progress(done, total):
    if total:
        pct = min(100.0, done / total * 100)
        width = max(10, min(40, LIVE.width() - 38))
        filled = int(pct / 100 * width)
        line = f"     [{BAR_FULL * filled}{BAR_EMPTY * (width - filled)}] {pct:5.1f}%  {fmt_size(done)}/{fmt_size(total)}"
    else:
        line = f"     {fmt_size(done)} downloaded"
    LIVE.set_progress(line)

def download_file(sess, url, dest, expected_hash="", algo="", expected_size=0):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    hasher = hashlib.new(algo) if algo in ("sha512", "sha1", "md5") else None
    done = 0
    try:
        try:
            r = sess.get(url, stream=True, timeout=(10, 60))
        except requests.RequestException as e:
            LOG.debug(f"Download request error for {url}: {e!r}")
            raise DownloadError(describe_error(e))
        with r:
            if r.status_code >= 400:
                raise DownloadError(f"HTTP {r.status_code} {r.reason or ''}".strip(),
                                    retryable=r.status_code in (408, 425, 429) or r.status_code >= 500)
            total = expected_size or int(r.headers.get("content-length") or 0)
            try:
                with open(part, "wb") as fh:
                    for chunk in r.iter_content(65536):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        done += len(chunk)
                        if hasher:
                            hasher.update(chunk)
                        show_progress(done, total)
            except requests.RequestException as e:
                LOG.debug(f"Download stream error for {url} after {done} bytes: {e!r}")
                raise DownloadError(f"{describe_error(e)} after {fmt_size(done)}")
            except OSError as e:
                raise DownloadError(f"Disk error: {e}", retryable=False)
        if expected_size and done != expected_size:
            raise DownloadError(f"Size mismatch: got {done} bytes, expected {expected_size}")
        if hasher and expected_hash and hasher.hexdigest().lower() != expected_hash.lower():
            raise DownloadError(f"Hash mismatch ({algo}), file is corrupted or incomplete")
        os.replace(part, dest)
        return done
    finally:
        LIVE.set_progress(None)
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass


class HashBoard:
    """Live 2-line block: animated '[+] Name: n/N ...' counter + faint gray '[+] Checking file.jar'."""

    def __init__(self, provider, total):
        self.provider = provider
        self.total = total
        self.live = _COLOR
        self.drawn = False

    def _counter(self, n):
        w = max(20, shutil.get_terminal_size((80, 20)).columns - 1)
        return colorize(f"  [+] {self.provider}: {n}/{self.total} jar(s) recognized by file hash."[:w])

    def update(self, n, current=None):
        if not self.live:
            return
        w = max(20, shutil.get_terminal_size((80, 20)).columns - 1)
        up = "\x1b[1A" if self.drawn else ""
        plain = getattr(sys.stdout, "write_plain", sys.stdout.write)
        sys.stdout.write(f"{up}\r\x1b[2K{self._counter(n)}{SOFT_FG}\r\n")
        plain(f"\x1b[2K{GRAY_FAINT}{f'  [+] Checking {current}'[:w] if current else ''}{SOFT_FG}")
        sys.stdout.flush()
        self.drawn = True

    def finish(self, n):
        if self.live and self.drawn:
            sys.stdout.write(f"\r\x1b[2K\x1b[1A\r\x1b[2K{self._counter(n)}{SOFT_FG}\r\n")
            sys.stdout.flush()
        else:
            ok(f"{self.provider}: {n}/{self.total} jar(s) recognized by file hash.")


class App:
    def __init__(self):
        self.folder    = ""
        self.ver       = ""
        self.loader    = ""
        self.mods      = []
        self.sess      = make_session()
        self.http      = Http(self.sess)
        self.mr        = ModrinthProvider(self.http)
        self.providers = [self.mr]
        self.t_start   = time.monotonic()
        self._ver_list = None
        LOG.info(f"Session started, app v{APP_VER}")

    def run(self):
        clr()
        banner("Minecraft Mod Manager")
        print()
        print("  This tool scans your mods folder, checks Modrinth and CurseForge")
        print("  for the latest versions, and downloads them into a clean output folder.")
        print()
        sep()

        self._setup_sources()

        # Each step returns None (go on), "edit" (Esc: redo this step) or "version" (go back to step 2).
        steps = [self._step_folder, self._step_version, self._step_loader, self._step_scan]
        i = 0
        while i < len(steps):
            result = steps[i]()
            if result == "edit":
                continue
            i = 1 if result == "version" else i + 1
        self._step_confirm()
        self._step_download()

    def _setup_sources(self):
        print()
        info("Checking CurseForge...")
        key, origin = get_curseforge_key()
        LOG.info(f"CurseForge key source: {origin}")

        if not key:
            result, reason = "missing", "No CurseForge key is available in this build."
        else:
            cf = CurseForgeProvider(self.http, key)
            result = cf.check_key()
            reason = {
                "invalid":     "CurseForge rejected the API key (HTTP 401/403).",
                "unreachable": "Could not reach api.curseforge.com (network error or timeout).",
                "error":       "CurseForge returned an unexpected error (see HTTP lines above).",
            }.get(result, "")

        if result == "ok":
            LOG.info("CurseForge enabled")
            self.providers.append(cf)
            ok("CurseForge Enabled")
            time.sleep(1)
            return

        LOG.error(f"CurseForge disabled: {reason}")
        log_path = self._startup_log_path()
        print()
        info("CurseForge Disabled:")
        out("  Full log located at:")
        out(f"  {log_path}")
        print()
        pause(text="Press Enter to skip for now...")

    def _startup_log_path(self):
        """Creates a log file right away and returns its path (or a note if it can't be written)."""
        import tempfile
        name = f"curseforge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        for base in (Path.home() / ".mc_mod_manager_logs", Path(tempfile.gettempdir()) / "mc_mod_manager_logs"):
            try:
                base.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            path = str(base / name)
            if LOG.set_path(path):
                return path
        return "(could not create a log file)"

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
            ch = prompt("Enter choice [1/2]:" if not self.folder else "Enter choice [1/2] (Enter = keep current):")
            if not ch and self.folder:
                ok(f"Using: {self.folder}")
                break
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

        LOG.context["Minecraft folder"] = self.folder
        if pause(esc=True):
            return "edit"

    def _step_version(self):
        clr()
        banner("Step 2 of 4 -- Select Target Minecraft Version")
        print()
        if self._ver_list is None:
            info("Fetching version list from Modrinth...")
            self._ver_list = self.mr.mc_versions()
        ver_list = self._ver_list
        print()

        top = ver_list[:20]
        for i, v in enumerate(top, 1):
            print(f"  [{i:>2}]  {v}")
        print()
        print("  Or type any real Minecraft release (e.g. 1.21.4)")
        if not self.mr.versions_live:
            warn("Live version list unavailable, only built-in versions are accepted.")
        if self.ver:
            print(f"  Current: {self.ver} (press Enter to keep it)")
        sep()

        while True:
            ch = prompt("Enter number or version string:")
            if not ch and self.ver:
                ok(f"Target version: {self.ver}")
                break
            if ch.isdigit():
                idx = int(ch) - 1
                if 0 <= idx < len(top):
                    self.ver = top[idx]
                    ok(f"Target version: {self.ver}")
                    break
                warn(f"Pick a number between 1 and {len(top)}, or type a version like 1.21.4")
                continue
            match = next((v for v in ver_list if v.lower() == ch.lower()), None)
            if match:
                self.ver = match
                ok(f"Target version: {self.ver}")
                break
            warn(f"'{ch}' is not a real Minecraft release version.")
            LOG.warn(f"Rejected version input: {ch!r}")
            close = get_close_matches(ch, ver_list, n=3, cutoff=0.5)
            if close:
                info("Did you mean: " + ", ".join(close) + " ?")

        LOG.context["Target version"] = self.ver
        if pause(esc=True):
            return "edit"

    def _step_loader(self):
        clr()
        banner("Step 3 of 4 -- Select Mod Loader")
        print()
        for i, l in enumerate(LOADERS, 1):
            print(f"  [{i}]  {l}")
        sep()

        while True:
            ch = prompt("Enter choice [1-4]:" if not self.loader else "Enter choice [1-4] (Enter = keep current):")
            if not ch and self.loader:
                ok(f"Loader: {self.loader}")
                break
            try:
                idx = int(ch) - 1
                if 0 <= idx < len(LOADERS):
                    self.loader = LOADERS[idx]
                    ok(f"Loader: {self.loader}")
                    break
            except ValueError:
                pass
            warn("Please enter a number between 1 and 4.")

        LOG.context["Loader"] = self.loader
        LOG.context["Sources"] = ", ".join(p.name for p in self.providers)
        if pause(esc=True):
            return "edit"

    def _step_scan(self):
        clr()
        banner("Step 4 of 4 -- Scanning Mods Folder")
        print()
        info(f"Scanning: {self.folder}")
        print()

        t_scan = time.monotonic()
        LOG.section("SCAN")
        self.mods = scan_mods(self.folder)

        if not self.mods:
            warn("No .jar files found in the mods folder.")
            warn("Make sure the folder contains a 'mods' subdirectory with .jar files.")
            LOG.warn(f"No .jar files found in {self.folder}")
            pause()
            sys.exit(0)

        ok(f"Found {len(self.mods)} mod(s).")
        LOG.info(f"Scanned {len(self.mods)} jar(s) in {self.folder}")
        for m in self.mods:
            LOG.info(f"JAR {m.filename} | {fmt_size(m.size)} | loader={m.loader or '?'} | id={m.mod_id} | "
                     f"name={m.name} | version={m.version or '?'} | authors={', '.join(m.authors) or '?'} | "
                     f"sha512={m.sha512[:16]}...")
        print()

        LOG.section("EXACT FILE LOOKUP")
        for p in self.providers:
            info(f"Looking up exact file matches on {p.name}...")
            if p.progressive:
                board = HashBoard(p.name, len(self.mods))
                board.update(0, self.mods[0].filename)
                n = p.prefetch(self.mods, progress=board.update)
                board.finish(n)
            else:
                n = p.prefetch(self.mods)
                ok(f"{p.name}: {n}/{len(self.mods)} jar(s) recognized by file hash.")
            LOG.info(f"{p.name} exact matches: {n}/{len(self.mods)}")
        print()

        info(f"Checking for {self.ver} / {self.loader} versions...")
        print()
        LOG.section(f"RESOLVE ({self.ver} / {self.loader})")

        total = len(self.mods)
        counts = {"available": 0, "up_to_date": 0, "no_build": 0, "not_found": 0}
        via = {}

        for i, m in enumerate(self.mods, 1):
            label = f"[{i}/{total}] {m.name or m.filename}"
            print(f"  {label[:46]:<46}", end="", flush=True)
            self._resolve(m)
            counts[m.status] += 1
            if m.found:
                via[m.found.provider] = via.get(m.found.provider, 0) + 1
            print(self._status_text(m))

        sep()
        print()
        ok(f"Results: {counts['available']} update(s) available, {counts['up_to_date']} up-to-date, "
           f"{counts['no_build']} no build for {self.ver}, {counts['not_found']} not found.")
        if via:
            info("Found via: " + ", ".join(f"{k} {v}" for k, v in via.items()))
        LOG.info(f"Resolve summary: {counts} via={via} in {time.monotonic() - t_scan:.1f}s")
        print()
        if pause(esc=True):
            LOG.info("User pressed Esc after scan, going back to version selection")
            return "version"

    def _resolve(self, m):
        started = time.monotonic()
        no_build = None
        closest = None
        for p in self.providers:
            if not p.enabled:
                continue
            found, inf = p.resolve(m, self.ver, self.loader)
            if found:
                m.found = found
                same = found.same_file or bool(m.version and found.version == m.version)
                m.status = "up_to_date" if same else "available"
                break
            if inf["no_build"] and not no_build:
                no_build = (p.name, inf["no_build"])
            if inf["closest"] and (not closest or inf["closest"][1] > closest[2]):
                closest = (p.name, inf["closest"][0], inf["closest"][1])
        else:
            if no_build:
                m.status = "no_build"
                m.no_build = no_build
            else:
                m.status = "not_found"
                m.closest = closest

        took = time.monotonic() - started
        f = m.found
        if f:
            LOG.info(f"RESOLVED [{m.status}] {m.name} ({m.filename}) -> {f.provider} '{f.title}' via {f.method} "
                     f"(score {f.score:.2f}) | {f.version} | {f.channel} | file={f.filename} | "
                     f"same_file={f.same_file} | manual={f.manual} | {took:.1f}s")
        elif m.status == "no_build":
            LOG.warn(f"RESOLVED [no_build] {m.name}: found '{m.no_build[1]}' on {m.no_build[0]} "
                     f"but no build for {self.ver}/{self.loader} | {took:.1f}s")
        else:
            extra = f" closest='{m.closest[1]}' on {m.closest[0]} score={m.closest[2]:.2f}" if m.closest else ""
            LOG.warn(f"RESOLVED [not_found] {m.name} ({m.filename}){extra} | {took:.1f}s")

    def _status_text(self, m):
        f = m.found
        if m.status == "up_to_date":
            return f"  up-to-date ({m.version or f.version}) {provider_tag(f.provider)}"
        if m.status == "available":
            extra = "" if f.channel == "release" else f" ({f.channel})"
            manual = " manual download only" if f.manual else ""
            return f"  update available -> {f.version}{extra} {provider_tag(f.provider)}{manual}"
        if m.status == "no_build":
            return f"  no build for {self.ver}/{self.loader} (found: {m.no_build[1]})"
        hint = f" (closest: {m.closest[1]}, {m.closest[2]:.2f})" if m.closest and m.closest[2] >= 0.45 else ""
        return f"  not found{hint}"

    def _step_confirm(self):
        clr()
        banner("Confirm Download")
        print()

        col_n = 30
        col_v = 18
        col_s = 12
        col_p = 11
        header = f"  {'Mod':<{col_n}} {'Current':<{col_v}} {'Status':<{col_s}} {'Source':<{col_p}} New Version"
        print(header)
        sep("-", len(header) + 14)

        downloadable = 0
        for m in self.mods:
            name = (m.name or m.filename)[:col_n - 1]
            cur  = (m.version or "?")[:col_v - 1]
            f = m.found
            if m.status == "available":
                status = "UPDATE"
                downloadable += 1
            elif m.status == "up_to_date":
                status = "up-to-date"
                downloadable += 1
            elif m.status == "no_build":
                status = "no build"
            else:
                status = "not found"
            source = f.provider if f else ""
            new_v = f.version if f else ""
            print(f"  {name:<{col_n}} {cur:<{col_v}} {status:<{col_s}} {source:<{col_p}} {new_v}")

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
            LOG.info("User aborted at confirmation")
            sys.exit(0)

    def _unique_name(self, name, used):
        base, ext = os.path.splitext(name)
        cand, n = name, 2
        while cand.lower() in used:
            cand = f"{base}_{n}{ext}"
            n += 1
        used.add(cand.lower())
        return cand

    def _step_download(self):
        clr()
        banner("Downloading Mods")
        print()

        out_folder = os.path.join(self.folder, f"MC_{self.ver}_{self.loader}")
        mods_out   = os.path.join(out_folder, "mods")
        os.makedirs(mods_out, exist_ok=True)

        log_path = os.path.join(out_folder, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        LOG.set_path(log_path)
        LOG.section("DOWNLOAD")
        LOG.info(f"Output: {out_folder}")

        ok(f"Output folder created: {out_folder}")
        print()
        sep()

        LIVE.reset()
        LIVE.start()
        used = set()
        total = len(self.mods)

        try:
            for i, m in enumerate(self.mods, 1):
                out()
                out(f"  [{i}/{total}] {m.name or m.filename}")
                self._process(m, mods_out, used)
            self._retry_rounds()
        finally:
            elapsed = LIVE.elapsed()

        counts = self._write_summary(elapsed)
        out()
        sep()
        out()
        ready = counts["downloaded"] + counts["copied"] + counts["present"]
        line = (f"Finished: {ready}/{total} mods ready ({counts['downloaded']} downloaded, "
                f"{counts['copied']} copied, {counts['present']} already present). "
                f"{counts['skipped']} skipped, {counts['failed']} failed.")
        (warn if counts["failed"] else ok)(line)
        ok(f"Output folder: {out_folder}")
        ok(f"Log saved: {log_path}")
        LOG.close()
        LIVE.stop()
        pause()

    def _process(self, m, mods_out, used):
        t0 = time.monotonic()
        name = m.name or m.filename
        f = m.found

        if m.status in ("not_found", "no_build") or not f:
            if m.status == "no_build":
                reason = f"found '{m.no_build[1]}' on {m.no_build[0]} but no build for {self.ver} / {self.loader}"
            else:
                reason = f"not found on {' / '.join(p.name for p in self.providers)} for {self.ver} / {self.loader}"
            warn(f"Skipping: {reason}")
            LOG.warn(f"SKIPPED {name}: {reason}")
            m.dl = "skipped"
            return

        if m.status == "up_to_date" and f.same_file and os.path.isfile(m.path):
            dest = os.path.join(mods_out, self._unique_name(m.filename, used))
            try:
                shutil.copy2(m.path, dest)
            except OSError as e:
                m.dl, m.error, m.retryable = "failed", f"Copy failed: {e}", True
                m.dest = dest
                err(m.error)
                LOG.error(f"FAILED {name}: {m.error}")
                return
            m.dl, m.dest = "copied", dest
            info(f"Copied (already up-to-date, identical file): {m.filename}")
            LOG.info(f"COPIED {name}: {m.filename} (identical to {f.provider} file {f.version})")
            return

        m.dest = os.path.join(mods_out, self._unique_name(f.filename, used))

        if f.manual or not f.url:
            m.dl, m.retryable = "failed", False
            m.error = f"Download disabled by the author, get it manually: {f.site_url}"
            err(m.error)
            LOG.error(f"FAILED {name}: {m.error}")
            return

        if f.hash_algo and os.path.isfile(m.dest) and hash_file(m.dest, f.hash_algo) == f.hash_value:
            m.dl = "present"
            info(f"Already present and verified: {os.path.basename(m.dest)}")
            LOG.info(f"PRESENT {name}: {os.path.basename(m.dest)} verified ({f.hash_algo})")
            return

        if m.status == "up_to_date":
            info(f"Already up-to-date ({m.version}), downloading to output folder...")
        self._download(m)
        m.elapsed += time.monotonic() - t0

    def _download(self, m):
        f = m.found
        name = m.name or m.filename
        fname = os.path.basename(m.dest)
        m.error = ""
        for attempt in range(1, DL_ATTEMPTS + 1):
            m.attempts += 1
            suffix = f" (attempt {attempt}/{DL_ATTEMPTS})" if attempt > 1 else ""
            info(f"Downloading {f.version} from {f.provider}{suffix}...")
            LOG.info(f"DOWNLOAD {name} -> {f.version} | {f.provider} | attempt {attempt}/{DL_ATTEMPTS} | {f.url}")
            t = time.monotonic()
            try:
                size = download_file(self.sess, f.url, m.dest, f.hash_value, f.hash_algo, f.size)
            except DownloadError as e:
                took = time.monotonic() - t
                m.error = str(e)
                LOG.error(f"DOWNLOAD FAILED {name}: {e} | attempt {attempt}/{DL_ATTEMPTS} | {took:.1f}s | {f.url}")
                if e.retryable and attempt < DL_ATTEMPTS:
                    delay = 2 * attempt
                    warn(f"Failed: {e}. Retrying in {delay}s...")
                    LOG.warn(f"Auto-retry {name} in {delay}s")
                    time.sleep(delay)
                    continue
                m.dl = "failed"
                m.retryable = not e.permanent
                err(f"Failed: {e}")
                return False
            took = time.monotonic() - t
            m.dl, m.error = "downloaded", ""
            verified = f"{f.hash_algo} verified" if f.hash_algo and f.hash_value else "not verified"
            ok(f"Done: {fname} ({fmt_size(size)}, {fmt_took(took)})")
            LOG.info(f"DOWNLOADED {name}: {fname} | {fmt_size(size)} | {took:.1f}s | {verified} | attempts={attempt}")
            return True
        return False

    def _refresh_source(self, m):
        f = m.found
        provider = next((p for p in self.providers if p.name == f.provider and p.enabled), None)
        if not provider:
            return
        cand = Cand(f.project_id, f.title, f.slug)
        fresh = provider.latest(cand, m, self.ver, self.loader)
        if fresh and not fresh.manual and fresh.url:
            fresh.method, fresh.score = f.method, f.score
            if fresh.url != f.url or fresh.file_id != f.file_id:
                LOG.info(f"Refreshed source for {m.name}: {f.version} -> {fresh.version}")
            m.found = fresh
        else:
            LOG.warn(f"Could not refresh source for {m.name}, using the previous link")

    def _retry_rounds(self):
        rnd = 0
        while True:
            failed = [m for m in self.mods if m.dl == "failed"]
            if not failed:
                return
            retryable = [m for m in failed if m.retryable]

            out()
            sep()
            warn(f"{len(failed)} mod(s) failed to download:")
            LOG.warn(f"{len(failed)} mod(s) failed to download")
            for m in failed:
                f = m.found
                note = "" if m.retryable else "  [cannot retry]"
                out(f"   • {m.name or m.filename} [{f.provider if f else '?'}] {m.error}{note}")
                LOG.warn(f"FAILED {m.name} [{f.provider if f else '?'}]: {m.error} | retryable={m.retryable} | attempts={m.attempts}")
            if not retryable:
                return

            LIVE.stop()
            ch = prompt(f"Retry {len(retryable)} failed mod(s)? [y/n]:")
            if ch.lower() not in ("y", "yes"):
                LOG.info("User declined to retry failed downloads")
                LIVE.start()
                return
            LIVE.start()

            rnd += 1
            LOG.section(f"RETRY ROUND {rnd}")
            LOG.info(f"Retrying {len(retryable)} mod(s): " + ", ".join(m.name or m.filename for m in retryable))
            out()
            info(f"Retry round {rnd}: {len(retryable)} mod(s)")
            for i, m in enumerate(retryable, 1):
                out()
                out(f"  [{i}/{len(retryable)}] {m.name or m.filename}")
                m.retry_rounds += 1
                t0 = time.monotonic()
                self._refresh_source(m)
                if m.found.manual or not m.found.url:
                    m.error = f"Download disabled by the author, get it manually: {m.found.site_url}"
                    m.retryable = False
                    err(m.error)
                    LOG.error(f"RETRY FAILED {m.name}: {m.error}")
                    continue
                success = self._download(m)
                m.elapsed += time.monotonic() - t0
                if success:
                    LOG.info(f"RECOVERED {m.name} in retry round {rnd}")
                else:
                    LOG.error(f"RETRY FAILED {m.name} in round {rnd}: {m.error}")

    def _write_summary(self, elapsed):
        counts = {"downloaded": 0, "copied": 0, "present": 0, "skipped": 0, "failed": 0}
        for m in self.mods:
            key = m.dl if m.dl in counts else None
            if key:
                counts[key] += 1
        recovered = [m for m in self.mods if m.dl in ("downloaded", "present") and m.retry_rounds]
        failed = [m for m in self.mods if m.dl == "failed"]

        LOG.section("SUMMARY")
        LOG.info(f"Target: Minecraft {self.ver} / {self.loader} | sources: {', '.join(p.name for p in self.providers)}")
        LOG.info(f"Mods: {len(self.mods)} | downloaded={counts['downloaded']} copied={counts['copied']} "
                 f"already_present={counts['present']} skipped={counts['skipped']} failed={counts['failed']} "
                 f"recovered_by_retry={len(recovered)}")
        LOG.info(f"Download time: {fmt_dur(elapsed)} | total session time: {fmt_dur(time.monotonic() - self.t_start)}")
        LOG.info(f"Log entries: {LOG.counts}")
        for m in self.mods:
            f = m.found
            LOG.info(f"RESULT [{m.dl:<10}] {m.name} | {f.provider + ' ' + f.version if f else '-'} | "
                     f"attempts={m.attempts} retry_rounds={m.retry_rounds} | {fmt_took(m.elapsed)}"
                     + (f" | error={m.error}" if m.dl == "failed" else ""))
        if recovered:
            LOG.info("RECOVERED BY RETRY: " + ", ".join(m.name or m.filename for m in recovered))
        if failed:
            LOG.error(f"STILL FAILED ({len(failed)}):")
            for m in failed:
                f = m.found
                LOG.error(f"  {m.name} | {m.filename} | {f.provider if f else '?'} | {m.error} | "
                          f"{f.url if f and f.url else (f.site_url if f else '')}")
        return counts


def main():
    smooth_console()
    install_info_anim()
    atexit.register(soft_off)
    soft_on()
    try:
        App().run()
    except KeyboardInterrupt:
        LIVE.stop()
        LOG.warn("Interrupted by user (Ctrl+C)")
        print("\n\n  Interrupted.\n")
        LOG.close()
        sys.exit(0)
    except SystemExit:
        LOG.close()
        raise
    except Exception as e:
        LIVE.stop()
        LOG.error(f"Unhandled exception: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        err(f"Unexpected error: {type(e).__name__}: {e}")
        if LOG.path:
            err(f"Details saved in: {LOG.path}")
        LOG.close()
        sys.exit(1)
    LOG.close()


if __name__ == "__main__":
    main()
