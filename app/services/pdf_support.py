"""Runtime detection for whether the weekly PDF path can actually run here.

ReportLab, which lays out the PDF itself, is pure Python and always available.
The one host-dependent piece is Chrome: the report embeds its Plotly charts as
rasterized PNGs, and kaleido drives a real Chrome/Chromium binary to produce
them (see `_ensure_chrome` in pdf_report). Streamlit Community Cloud's base
image ships no browser, and the apt route for adding one (packages.txt) is
unusable there as of 2026-09, so on that deployment the PDF path has to be off
and the reports page has to offer something else in its place.

Detection is a filesystem probe only — it never downloads a browser and never
launches one, so it's cheap enough to call on every Streamlit rerun. That also
means it can be wrong in one direction: a binary can be present but unable to
start (a downloaded Chrome with no libnss3/libatk on the host is exactly the
case packages.txt's `chromium` used to cover). Callers must still guard the
actual render, which is why `pdf_unavailable_note` exists for that path too.

`PDF_EXPORT_ENABLED` overrides the probe in both directions.
"""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Optional

# Only genuine Chrome/Chromium. Edge is Chromium-based but kaleido's browser
# launcher looks for Chrome/Chromium specifically, so accepting msedge here
# would turn a working "no, fall back" into a false yes followed by a failed
# render — worse than the fallback it replaced.
_BINARY_NAMES = (
    "chromium",
    "chromium-browser",
    "chrome",
    "google-chrome",
    "google-chrome-stable",
)

_TRUTHY = {"1", "true", "yes", "on", "enabled"}
_FALSY = {"0", "false", "no", "off", "disabled"}


def _wellknown_paths() -> tuple[str, ...]:
    system = platform.system()
    if system == "Windows":
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        return tuple(
            str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
            for base in (program_files, program_files_x86, local_app_data)
            if base
        )
    if system == "Darwin":
        return (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        )
    return (
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/lib/chromium/chromium",
        "/usr/lib/chromium-browser/chromium-browser",
        "/snap/bin/chromium",
    )


def _managed_chrome() -> Optional[str]:
    """A Chrome that kaleido/choreographer already downloaded on a previous run.

    Cache layout is an implementation detail of those libraries and has moved
    between versions, so this globs a few plausible roots rather than importing
    a private helper that may not exist. Best-effort by design: missing it only
    costs us a fallback we'd have offered anyway.
    """
    home = Path.home()
    roots = [
        home / ".cache" / "choreographer",
        home / ".cache" / "kaleido",
        home / "AppData" / "Local" / "choreographer",
        home / "AppData" / "Local" / "kaleido",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for name in ("chrome", "chrome.exe", "chromium", "headless_shell", "headless_shell.exe"):
            try:
                found = next(root.rglob(name), None)
            except OSError:
                continue
            if found is not None and found.is_file():
                return str(found)
    return None


def _probe_chrome() -> Optional[str]:
    # An explicit path wins — it's also the escape hatch for a host that keeps
    # its browser somewhere none of the probes below would think to look.
    for env_var in ("CHROME_PATH", "BROWSER_PATH", "CHROMIUM_PATH"):
        candidate = os.environ.get(env_var, "").strip()
        if candidate and Path(candidate).is_file():
            return candidate

    for name in _BINARY_NAMES:
        found = shutil.which(name)
        if found:
            return found

    for candidate in _wellknown_paths():
        if Path(candidate).is_file():
            return candidate

    return _managed_chrome()


# Sentinel distinct from None, which is itself a meaningful cached answer
# ("probed, found nothing").
_UNPROBED = object()
_cached_chrome: object = _UNPROBED


def find_chrome() -> Optional[str]:
    """Path to a usable-looking Chrome/Chromium, or None. No side effects.

    Cached for the life of the process: Streamlit reruns the reports page on
    every interaction, and the last-resort branch walks a cache directory, so
    an uncached probe would mean a filesystem crawl per keystroke. A browser
    doesn't appear or vanish mid-session — and the one thing that could install
    one (kaleido downloading it) only happens on a host where the probe already
    said yes.
    """
    global _cached_chrome
    if _cached_chrome is _UNPROBED:
        _cached_chrome = _probe_chrome()
    return _cached_chrome  # type: ignore[return-value]


def pdf_export_enabled() -> bool:
    """Whether the reports page should offer the PDF at all.

    Order matters: an explicit `PDF_EXPORT_ENABLED` is honoured before the
    probe, so a host where the probe guesses wrong can be corrected without a
    code change. Everything else defers to whether a browser is actually here
    — on this machine that means PDF on locally, off on Streamlit Cloud, with
    nothing hardcoded about either.
    """
    override = os.environ.get("PDF_EXPORT_ENABLED", "").strip().lower()
    if override in _TRUTHY:
        return True
    if override in _FALSY:
        return False
    return find_chrome() is not None


def pdf_unavailable_note() -> str:
    """One short line for the UI explaining why the PDF isn't on offer."""
    override = os.environ.get("PDF_EXPORT_ENABLED", "").strip().lower()
    if override in _FALSY:
        return (
            "PDF export is switched off for this deployment "
            "(`PDF_EXPORT_ENABLED` is set to off)."
        )
    return (
        "PDF export needs a Chrome/Chromium binary to render the report's charts, "
        "and this deployment doesn't have one. Every figure below is the same as "
        "the PDF's — only the file format differs."
    )
