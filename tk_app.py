#!/usr/bin/env python3
"""
Tkinter-based modern UI for File Organizer
- Uses `organizer_core.Organizer` for core logic
- Provides Start / Pause / Stop, Add Source, Choose Dest, Export from Photos
- Logs actions to a scrolled text area using a thread-safe queue
"""
import threading
import queue
import time
import logging
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from organizer_core import Organizer

LOG_POLL_INTERVAL_MS = 200

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Worker(threading.Thread):
    def __init__(self, organizer: Organizer, log_q: queue.Queue):
        super().__init__(daemon=True)
        self.organizer = organizer
        self.log_q = log_q
        self._running = threading.Event()
        self._paused = threading.Event()
        self._running.clear()
        self._paused.clear()

    def run(self):
        self._running.set()
        cfg = self.organizer.config
        detect = cfg.get('DETECTION_DELAY_SECONDS', 10)
        cooldown = cfg.get('COOLDOWN_SECONDS', 30)

        while self._running.is_set():
            if self._paused.is_set():
                time.sleep(0.2)
                continue

            self.log_q.put('Scanning sources...')
            files = self.organizer.scan_all_sources()
            total = self.organizer.count_total_files(files)
            if total == 0:
                time.sleep(1.0)
                continue

            self.log_q.put(f'Detected {total} files, waiting {detect}s')
            time.sleep(detect)

            files_rescan = self.organizer.scan_all_sources()
            total_rescan = self.organizer.count_total_files(files_rescan)
            if total_rescan != total:
                self.log_q.put('File count changed, skipping this round')
                continue

            batch = self.organizer.create_batch_folder()
            self.log_q.put(f'Creating batch: {batch.name}')
            moved, attempted = self.organizer.move_all_files(files_rescan, batch)
            self.log_q.put(f'Moved {moved}/{attempted} files')

            if self.organizer.config.get('AUTO_CLEANUP_EMPTY_DIRS', False):
                self.log_q.put('Cleaning up empty source directories...')
                try:
                    self.organizer.cleanup_all_sources()
                except Exception as e:
                    self.log_q.put(f'Cleanup error: {e}')

            time.sleep(cooldown)

        self.log_q.put('Worker stopped')

    def stop(self, timeout: float = 2.0):
        self._running.clear()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root)
        self.root = root
        self.root.title('File Organizer (Tk)')
        self.pack(fill='both', expand=True)

        # Tk style
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        # simple modern colors
        style.configure('TButton', font=('Segoe UI', 11))
        style.configure('TLabel', font=('Segoe UI', 11))
        style.configure('TEntry', font=('Segoe UI', 10))

        # Internal state
        self.log_q = queue.Queue()
        self.worker = None

        # Default organizer config
        default_dest = str(Path.home() / 'Desktop' / 'Organized')
        self.organizer = Organizer({
            'SOURCE_FOLDERS': [],
            'DEST_BASE_FOLDER': default_dest,
            'BATCH_FOLDER_PREFIX': 'Session',
            'DETECTION_DELAY_SECONDS': 10,
            'COOLDOWN_SECONDS': 30,
            'ALLOWED_EXTENSIONS': ['.jpg', '.jpeg', '.png', '.raw', '.dng', '.tiff', '.gif', '.bmp', '.mp4', '.mov', '.avi', '.psd', '.ai'],
            'SKIP_HIDDEN_FILES': True,
            'RECURSIVE_SCAN': True,
            'AUTO_CLEANUP_EMPTY_DIRS': True,
            'STATE_FILE': '.file_organizer_state.json'
        })

        self._build_ui()

        # Start polling log queue
        self.root.after(LOG_POLL_INTERVAL_MS, self._poll_log)

    def _build_ui(self):
        pad = 8
        # Top frame: source list and add button
        top = ttk.Frame(self)
        top.pack(fill='x', padx=pad, pady=(pad, 0))

        ttk.Label(top, text='Source Folders:').pack(side='left')
        self.src_var = tk.StringVar(value=', '.join(self.organizer.config['SOURCE_FOLDERS']))
        self.src_entry = ttk.Entry(top, textvariable=self.src_var, state='readonly', width=80)
        self.src_entry.pack(side='left', padx=(6, 6))
        ttk.Button(top, text='Add Source', command=self.add_source).pack(side='left')

        # Destination
        mid = ttk.Frame(self)
        mid.pack(fill='x', padx=pad, pady=(6, 0))
        ttk.Label(mid, text='Destination:').pack(side='left')
        self.dest_var = tk.StringVar(value=self.organizer.config['DEST_BASE_FOLDER'])
        self.dest_entry = ttk.Entry(mid, textvariable=self.dest_var, state='readonly', width=80)
        self.dest_entry.pack(side='left', padx=(6, 6))
        ttk.Button(mid, text='Choose Dest', command=self.choose_dest).pack(side='left')

        # Controls
        ctl = ttk.Frame(self)
        ctl.pack(fill='x', padx=pad, pady=(10, 0))
        ttk.Button(ctl, text='Start', command=self.start_worker).pack(side='left', padx=4)
        ttk.Button(ctl, text='Pause/Resume', command=self.toggle_pause).pack(side='left', padx=4)
        ttk.Button(ctl, text='Stop', command=self.stop_worker).pack(side='left', padx=4)
        ttk.Button(ctl, text='Export', command=self.export_photos).pack(side='left', padx=8)

        # Log area
        log_frame = ttk.Frame(self)
        log_frame.pack(fill='both', expand=True, padx=pad, pady=(10, pad))
        self.log_view = ScrolledText(log_frame, wrap='word', height=20, state='disabled')
        self.log_view.pack(fill='both', expand=True)

    # UI actions
    def add_source(self):
        path = filedialog.askdirectory()
        if path:
            self.organizer.config['SOURCE_FOLDERS'].append(path)
            self.src_var.set(', '.join(self.organizer.config['SOURCE_FOLDERS']))
            self._log(f'Added source: {path}')

    def choose_dest(self):
        path = filedialog.askdirectory()
        if path:
            self.organizer.config['DEST_BASE_FOLDER'] = path
            self.dest_var.set(path)
            self._log(f'Set destination: {path}')

    def start_worker(self):
        if self.worker and self.worker.is_alive():
            self._log('Worker already running')
            return
        if not self.organizer.startup_checks():
            self._log('Startup checks failed')
            messagebox.showerror('Startup Failed', 'Check source and destination folders in config and retry.')
            return
        self.worker = Worker(self.organizer, self.log_q)
        self.worker.start()
        self._log('Worker started')

    def toggle_pause(self):
        if not self.worker:
            self._log('Worker not running')
            return
        if getattr(self.worker, '_paused', None) and self.worker._paused.is_set():
            self.worker.resume()
            self._log('Resumed')
        else:
            self.worker.pause()
            self._log('Paused')

    def stop_worker(self):
        if not self.worker:
            self._log('Worker not running')
            return
        self.worker.stop()
        self.worker.join(timeout=2.0)
        self.worker = None
        self._log('Stopped')

    def export_photos(self):
        """Manual export: move files from configured source folders to destination."""
        try:
            if not self.organizer.startup_checks():
                self._log('Startup checks failed')
                messagebox.showerror('Export Failed', 'Startup checks failed. Verify folders and retry.')
                return

            files = self.organizer.scan_all_sources()
            total = self.organizer.count_total_files(files)
            if total == 0:
                self._log('No files to export')
                messagebox.showinfo('Export', 'No files found in configured source folders.')
                return

            batch = self.organizer.create_batch_folder()
            self._log(f'Exporting {total} files to {batch}')
            moved, attempted = self.organizer.move_all_files(files, batch)
            self._log(f'Moved {moved}/{attempted} files to {batch}')

            if self.organizer.config.get('AUTO_CLEANUP_EMPTY_DIRS', False):
                self._log('Cleaning up empty source directories...')
                try:
                    self.organizer.cleanup_all_sources()
                except Exception as e:
                    self._log(f'Cleanup error: {e}')

            messagebox.showinfo('Export Complete', f'Moved {moved}/{attempted} files to {batch}')

        except Exception as e:
            self._log(f'Export failed: {e}')
            messagebox.showerror('Export Failed', str(e))

    def _log(self, msg: str):
        self.log_q.put(msg)

    def _poll_log(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        finally:
            self.root.after(LOG_POLL_INTERVAL_MS, self._poll_log)

    def _append_log(self, msg: str):
        self.log_view.configure(state='normal')
        self.log_view.insert('end', msg + '\n')
        self.log_view.see('end')
        self.log_view.configure(state='disabled')


def main():
    root = tk.Tk()
    app = App(root)
    root.geometry('1000x700')
    root.mainloop()


if __name__ == '__main__':
    main()
