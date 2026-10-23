"""Unbolt's small drag-and-drop window."""
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
import winreg
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from unbolt.convert import FORMATS, KIND_LABELS, convert

REPO = "https://github.com/moneymangod/Unbolt"
MENU_KEY = r"Software\Classes\SystemFileAssociations\{ext}\shell\Unbolt"
MENU_TEXT = "Convert with Unbolt"
BLUE, BLUE_DARK, PANEL, DROP, DROP_HOT, INK, MUTED = "#2f6fed", "#1f56c4", "#f6f7fb", "#eaf0ff", "#d4e2ff", "#1c2333", "#6b7385"


def set_context_menu(enable):
    """Add or remove the right-click entry for every supported extension (current user only)."""
    if enable and not getattr(sys, "frozen", False):
        raise RuntimeError("The right-click menu can only be installed from the built Unbolt.exe.")
    for ext in FORMATS:
        key = MENU_KEY.format(ext=ext)
        if enable:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
                winreg.SetValueEx(k, None, 0, winreg.REG_SZ, MENU_TEXT)
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, sys.executable)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
                winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{sys.executable}" "%1"')
        else:
            for sub in (key + r"\command", key):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except FileNotFoundError:
                    pass


def _resource(name):
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return os.path.join(base, name)


class App(TkinterDnD.Tk):
    def __init__(self, files):
        super().__init__()
        self.title("Unbolt")
        self.geometry("560x640")
        self.minsize(520, 600)
        self.configure(bg=PANEL)
        try:
            self.iconbitmap(_resource(os.path.join("assets", "icon.ico")))
        except tk.TclError:
            pass
        self.files, self.outdir, self.messages = [], None, queue.Queue()
        self.style_widgets()

        head = tk.Frame(self, bg=PANEL)
        head.pack(fill="x", padx=18, pady=(16, 8))
        tk.Label(head, text="Unbolt", font=("Segoe UI Semibold", 20), fg=INK, bg=PANEL).pack(anchor="w")
        tk.Label(head, text="Open locked file formats in the tools you already use.", font=("Segoe UI", 10),
                 fg=MUTED, bg=PANEL).pack(anchor="w")

        self.drop = tk.Label(self, text="Drop files here\nor click to browse", font=("Segoe UI", 11), fg=BLUE_DARK, bg=DROP,
                             height=4, cursor="hand2", highlightthickness=1, highlightbackground="#b9ccf5")
        self.drop.pack(fill="x", padx=18, pady=(4, 8))
        self.drop.bind("<Button-1>", lambda e: self.browse())
        for w in (self.drop, self):
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<Drop>>", self.on_drop)
        self.drop.dnd_bind("<<DropEnter>>", lambda e: self.drop.configure(bg=DROP_HOT))
        self.drop.dnd_bind("<<DropLeave>>", lambda e: self.drop.configure(bg=DROP))

        listing = tk.Frame(self, bg=PANEL)
        listing.pack(fill="x", padx=18)
        self.listbox = tk.Listbox(listing, height=5, font=("Segoe UI", 10), relief="flat", highlightthickness=1,
                                  highlightbackground="#d5d9e5", selectbackground=BLUE, activestyle="none")
        self.listbox.pack(side="left", fill="x", expand=True)
        ttk.Button(listing, text="Clear", command=self.clear).pack(side="left", padx=(8, 0), anchor="n")

        opts = tk.Frame(self, bg=PANEL)
        opts.pack(fill="x", padx=18, pady=10)
        self.choice = {}
        for row, (kind, label) in enumerate(KIND_LABELS.items()):
            exts = [e for e, (_, _, k) in FORMATS.items() if k == kind]
            tk.Label(opts, text=label, font=("Segoe UI", 10), fg=INK, bg=PANEL, width=15, anchor="w").grid(row=row, column=0, pady=3)
            box = ttk.Combobox(opts, values=[f.upper() for f in FORMATS[exts[0]][0]], state="readonly", width=8)
            box.current(0)
            box.grid(row=row, column=1, padx=8)
            tk.Label(opts, text=" ".join(exts), font=("Segoe UI", 9), fg=MUTED, bg=PANEL).grid(row=row, column=2, sticky="w")
            for e in exts:
                self.choice[e] = box
        row = len(KIND_LABELS)
        self.out_label = tk.Label(opts, text="Save next to each file", font=("Segoe UI", 10), fg=INK, bg=PANEL, anchor="w")
        self.out_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(opts, text="Change folder", command=self.pick_outdir).grid(row=row, column=2, sticky="w", pady=(8, 0))

        self.go = ttk.Button(self, text="Convert", style="Accent.TButton", command=self.run)
        self.go.pack(fill="x", padx=18, pady=(2, 6), ipady=4)
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=18)

        foot = tk.Frame(self, bg=PANEL)
        foot.pack(side="bottom", fill="x", padx=18, pady=(4, 10))
        ttk.Button(foot, text="Add right-click menu", command=lambda: self.menu(True)).pack(side="left")
        ttk.Button(foot, text="Remove it", command=lambda: self.menu(False)).pack(side="left", padx=6)
        star = tk.Label(foot, text="★ Star Unbolt on GitHub", font=("Segoe UI", 9, "underline"), fg=BLUE, bg=PANEL, cursor="hand2")
        star.pack(side="right")
        star.bind("<Button-1>", lambda e: webbrowser.open(REPO))

        self.log = tk.Text(self, height=6, state="disabled", wrap="word", font=("Consolas", 9), relief="flat",
                           highlightthickness=1, highlightbackground="#d5d9e5", fg=INK)
        self.log.pack(fill="both", expand=True, padx=18, pady=(8, 4))
        self.add(files)
        self.poll()

    def style_widgets(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 4))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 11), background=BLUE, foreground="white", borderwidth=0)
        style.map("Accent.TButton", background=[("active", BLUE_DARK), ("disabled", "#a9b8de")])
        style.configure("Horizontal.TProgressbar", troughcolor="#e1e5f0", background=BLUE, borderwidth=0)

    def say(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_drop(self, event):
        self.drop.configure(bg=DROP)
        self.add(self.tk.splitlist(event.data))

    def add(self, paths):
        for p in paths:
            if os.path.splitext(p)[1].lower() not in FORMATS:
                self.say(f"Skipped (unsupported): {os.path.basename(p)}")
            elif p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", os.path.basename(p))

    def clear(self):
        self.files.clear()
        self.listbox.delete(0, "end")

    def browse(self):
        types = " ".join(f"*{e}" for e in FORMATS)
        self.add(filedialog.askopenfilenames(filetypes=[("Locked formats", types)]))

    def pick_outdir(self):
        d = filedialog.askdirectory()
        if d:
            self.outdir = d
            self.out_label.configure(text="Save to " + os.path.basename(d))

    def menu(self, enable):
        try:
            set_context_menu(enable)
        except Exception as e:
            messagebox.showerror("Unbolt", str(e))
            return
        self.say("Right-click menu " + ("added." if enable else "removed."))

    def run(self):
        if not self.files:
            self.say("Add some files first.")
            return
        jobs = [(p, self.choice[os.path.splitext(p)[1].lower()].get().lower()) for p in self.files]
        self.go.configure(state="disabled")
        self.progress.start(12)
        threading.Thread(target=self.work, args=(jobs,), daemon=True).start()

    def work(self, jobs):
        for path, fmt in jobs:
            self.messages.put(f"Converting {os.path.basename(path)} to {fmt.upper()}...")
            try:
                outs, warns = convert(path, fmt, self.outdir or os.path.dirname(path))
                self.messages.put("  Done: " + ", ".join(os.path.basename(o) for o in outs))
                for w in dict.fromkeys(warns):
                    self.messages.put("  Note: " + w)
            except Exception as e:
                self.messages.put(f"  Failed: {e}")
        self.messages.put(None)

    def poll(self):
        while not self.messages.empty():
            msg = self.messages.get()
            if msg is None:
                self.progress.stop()
                self.go.configure(state="normal")
            else:
                self.say(msg)
        self.after(100, self.poll)


def main(files):
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    App(files).mainloop()
