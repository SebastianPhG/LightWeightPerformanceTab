"""
System overlay for Windows: CPU, GPU, VRAM, RAM. Works with any GPU vendor.

Install:  pip install psutil pywin32
Run:      python overlay_any_gpu.py
Quit:     Ctrl+C in the terminal (the overlay is click-through).
"""
import tkinter as tk
from collections import defaultdict

import psutil
import win32pdh

UPDATE_MS = 1000
POS = "+20+20"  # screen position of the overlay


class GpuReader:
    """Reads GPU load and VRAM usage via Windows performance counters
    (the same source Task Manager uses)."""

    def __init__(self):
        self.query = win32pdh.OpenQuery()
        # AddEnglishCounter works regardless of Windows display language.
        self.util = win32pdh.AddEnglishCounter(
            self.query, r"\GPU Engine(*)\Utilization Percentage")
        self.mem = win32pdh.AddEnglishCounter(
            self.query, r"\GPU Adapter Memory(*)\Dedicated Usage")
        win32pdh.CollectQueryData(self.query)  # first sample primes the rates

    def read(self):
        """Returns (gpu_percent or None, vram_bytes or None)."""
        try:
            win32pdh.CollectQueryData(self.query)
            util = win32pdh.GetFormattedCounterArray(self.util, win32pdh.PDH_FMT_DOUBLE)
            mem = win32pdh.GetFormattedCounterArray(self.mem, win32pdh.PDH_FMT_DOUBLE)
        except Exception:
            return None, None

        # Instance names look like:
        #   pid_1234_luid_0x00000000_0x0000ABCD_phys_0_eng_0_engtype_3D
        # Sum across processes per (adapter, engine type), then take the
        # busiest engine -- this is how Task Manager computes GPU %.
        totals = defaultdict(float)
        for name, value in util.items():
            try:
                luid = name.split("luid_")[1].split("_phys")[0]
                engtype = name.split("engtype_")[1]
            except IndexError:
                continue
            totals[(luid, engtype)] += value
        gpu = min(max(totals.values()), 100.0) if totals else None

        # Dedicated VRAM per adapter; show the adapter using the most
        # (normally the discrete GPU on laptops with iGPU + dGPU).
        vram = max(mem.values()) if mem else None
        return gpu, vram


def read_stats(gpu_reader):
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    gpu, vram = gpu_reader.read()

    lines = [f"CPU  {cpu:5.1f} %"]
    lines.append(f"GPU  {gpu:5.1f} %" if gpu is not None else "GPU     n/a")
    if vram is not None:
        lines.append(f"VRAM {vram / 2**30:5.1f} GB")
    lines.append(f"RAM  {ram.percent:5.1f} %  {ram.used / 2**30:.1f}/{ram.total / 2**30:.0f} GB")
    return "\n".join(lines)


def make_click_through(root):
    import ctypes
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)


def main():
    gpu_reader = GpuReader()
    psutil.cpu_percent()  # prime CPU counter

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", "black")
    root.configure(bg="black")
    root.geometry(POS)

    label = tk.Label(root, text="", font=("Consolas", 14, "bold"),
                     fg="#00ff88", bg="black", justify="left")
    label.pack()

    def tick():
        # Quit shortcut: hold Ctrl + Shift and press Q (works even in a game)
        import ctypes
        key = ctypes.windll.user32.GetAsyncKeyState
        if key(0x11) & 0x8000 and key(0x10) & 0x8000 and key(0x51) & 0x8000:
            root.destroy()
            return
        label.config(text=read_stats(gpu_reader))
        root.after(UPDATE_MS, tick)

    tick()
    root.update_idletasks()
    try:
        make_click_through(root)
    except Exception:
        pass
    root.mainloop()


if __name__ == "__main__":
    main()
