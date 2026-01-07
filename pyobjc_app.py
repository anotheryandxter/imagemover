#!/usr/bin/env python3
"""Native macOS UI using PyObjC (AppKit) that wraps the Organizer core."""
import sys
import threading
import logging
from pathlib import Path

from AppKit import NSApplication, NSApp, NSWindow, NSButton, NSTextField, NSTextView, NSScrollView, NSMakeRect, NSOpenPanel, NSURL
from Foundation import NSObject, NSLog

from organizer_core import Organizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerThread(threading.Thread):
    def __init__(self, organizer: Organizer, log_cb):
        super().__init__(daemon=True)
        self.organizer = organizer
        self.log_cb = log_cb
        self._running = False
        self._paused = False

    def run(self):
        self._running = True
        cfg = self.organizer.config
        detect = cfg.get('DETECTION_DELAY_SECONDS', 10)
        cooldown = cfg.get('COOLDOWN_SECONDS', 30)

        while self._running:
            if self._paused:
                threading.Event().wait(0.2)
                continue

            self.log_cb('Scanning sources...')
            files = self.organizer.scan_all_sources()
            total = self.organizer.count_total_files(files)
            if total == 0:
                threading.Event().wait(1.0)
                continue

            self.log_cb(f'Detected {total} files, waiting {detect}s')
            threading.Event().wait(detect)

            files_rescan = self.organizer.scan_all_sources()
            total_rescan = self.organizer.count_total_files(files_rescan)
            if total_rescan != total:
                self.log_cb('File count changed, skipping this round')
                continue

            batch = self.organizer.create_batch_folder()
            self.log_cb(f'Creating batch: {batch.name}')
            moved, attempted = self.organizer.move_all_files(files_rescan, batch)
            self.log_cb(f'Moved {moved}/{attempted} files')

            # Perform optional cleanup of empty subdirectories if configured
            try:
                if self.organizer.config.get('AUTO_CLEANUP_EMPTY_DIRS', False):
                    self.log_cb('Cleaning up empty source directories...')
                    self.organizer.cleanup_all_sources()
            except Exception as e:
                self.log_cb(f'Cleanup error: {e}')

            threading.Event().wait(cooldown)

        self.log_cb('Worker stopped')

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False


class AppDelegate(NSObject):
    def __init__(self):
        super().__init__()
        # Defer creating Organizer until applicationDidFinishLaunching_
        # because PyObjC may initialize the delegate via other ObjC initializers.
        self.organizer = None
        self.worker = None
        self.window = None

    def append_log(self, msg: str):
        # Schedule UI update on the main thread by calling `updateLog_:` there.
        try:
            self.performSelectorOnMainThread_withObject_waitUntilDone_('updateLog:', msg, False)
        except Exception:
            # Fallback: try direct insert (may fail if called off-main-thread)
            try:
                cur = self.log_view.string() or ''
                self.log_view.setString_(cur + msg + '\n')
            except Exception:
                pass

    def updateLog_(self, pymsg):
        try:
            cur = self.log_view.string() or ''
        except Exception:
            cur = ''
        try:
            text = f"{cur}{pymsg}\n"
            self.log_view.setString_(text)
        except Exception:
            pass

    # Actions
    def addSource_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(True)
        panel.setCanChooseFiles_(False)
        panel.setAllowsMultipleSelection_(True)
        res = panel.runModal()
        if res == 1:
            urls = panel.URLs()
            folders = [str(u.path()) for u in urls]
            self.organizer.config['SOURCE_FOLDERS'].extend(folders)
            self.src_field.setStringValue_(', '.join(self.organizer.config['SOURCE_FOLDERS']))

    def chooseDest_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(True)
        panel.setCanChooseFiles_(False)
        panel.setAllowsMultipleSelection_(False)
        res = panel.runModal()
        if res == 1:
            url = panel.URL()
            path = str(url.path())
            self.organizer.config['DEST_BASE_FOLDER'] = path
            self.dest_field.setStringValue_(path)

    def start_(self, sender):
        if self.worker and self.worker.is_alive():
            self.append_log('Worker already running')
            return
        if not self.organizer.startup_checks():
            self.append_log('Startup checks failed')
            return
        self.worker = WorkerThread(self.organizer, self.append_log)
        self.worker.start()
        self.append_log('Worker started')

    def pause_(self, sender):
        if self.worker:
            if getattr(self.worker, '_paused', False):
                self.worker.resume()
                self.append_log('Resumed')
            else:
                self.worker.pause()
                self.append_log('Paused')

    def stop_(self, sender):
        if self.worker:
            self.worker.stop()
            self.worker.join(timeout=2.0)
            self.append_log('Stopped')

    def exportPhotos_(self, sender):
        try:
            exporter = None
            try:
                import organizer_core as _oc
                PhotosPermissionError = getattr(_oc, 'PhotosPermissionError', Exception)
                PhotosExporter = getattr(_oc, 'PhotosExporter')
                exporter = PhotosExporter()
            except Exception as e:
                self.append_log(f'PhotosExporter not available: {e}')
                return
            batch = self.organizer.create_batch_folder()
            self.append_log(f'Exporting from Photos to {batch}')
            exported = exporter.export_originals(str(batch))
            self.append_log(f'Exported {len(exported)} files')
        except PhotosPermissionError as ppe:
            # Show a native alert with guidance
            try:
                from AppKit import NSAlert
                alert = NSAlert.alloc().init()
                alert.setMessageText_('Photos Permission Required')
                alert.setInformativeText_(str(ppe))
                alert.addButtonWithTitle_('OK')
                alert.runModal()
            except Exception:
                pass
            self.append_log(f'Photos export failed: {ppe}')
        except Exception as e:
            self.append_log(f'Photos export failed: {e}')

    def applicationDidFinishLaunching_(self, notification):
        # Create organizer and build UI here (on main thread after app finishes launching)
        self.organizer = Organizer({
            'SOURCE_FOLDERS': [],
            'DEST_BASE_FOLDER': str(Path.home() / 'Desktop' / 'Organized'),
            'BATCH_FOLDER_PREFIX': 'Session',
            'DETECTION_DELAY_SECONDS': 10,
            'COOLDOWN_SECONDS': 30,
            'ALLOWED_EXTENSIONS': ['.jpg', '.jpeg', '.png', '.raw', '.dng', '.tiff', '.gif', '.bmp', '.mp4', '.mov', '.avi', '.psd', '.ai'],
            'SKIP_HIDDEN_FILES': True,
            'STATE_FILE': '.file_organizer_state.json'
        })
        self.worker = None

        # Build UI
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(100.0, 100.0, 900.0, 600.0),
            15,  # titled,closable,minimizable,resizable mask combined
            2, False
        )
        self.window.setTitle_('File Organizer (PyObjC)')

        content = self.window.contentView()

        # Source display
        self.src_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 520, 660, 24))
        self.src_field.setEditable_(False)
        content.addSubview_(self.src_field)

        add_src_btn = NSButton.alloc().initWithFrame_(NSMakeRect(700, 520, 80, 24))
        add_src_btn.setTitle_('Add Source')
        add_src_btn.setTarget_(self)
        add_src_btn.setAction_('addSource:')
        content.addSubview_(add_src_btn)

        # Destination
        self.dest_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 480, 660, 24))
        self.dest_field.setEditable_(False)
        self.dest_field.setStringValue_(self.organizer.config.get('DEST_BASE_FOLDER'))
        content.addSubview_(self.dest_field)

        dest_btn = NSButton.alloc().initWithFrame_(NSMakeRect(700, 480, 80, 24))
        dest_btn.setTitle_('Choose Dest')
        dest_btn.setTarget_(self)
        dest_btn.setAction_('chooseDest:')
        content.addSubview_(dest_btn)

        # Controls
        start_btn = NSButton.alloc().initWithFrame_(NSMakeRect(20, 440, 80, 32))
        start_btn.setTitle_('Start')
        start_btn.setTarget_(self)
        start_btn.setAction_('start:')
        content.addSubview_(start_btn)

        pause_btn = NSButton.alloc().initWithFrame_(NSMakeRect(110, 440, 80, 32))
        pause_btn.setTitle_('Pause')
        pause_btn.setTarget_(self)
        pause_btn.setAction_('pause:')
        content.addSubview_(pause_btn)

        stop_btn = NSButton.alloc().initWithFrame_(NSMakeRect(200, 440, 80, 32))
        stop_btn.setTitle_('Stop')
        stop_btn.setTarget_(self)
        stop_btn.setAction_('stop:')
        content.addSubview_(stop_btn)

            export_btn = NSButton.alloc().initWithFrame_(NSMakeRect(320, 440, 160, 32))
            export_btn.setTitle_('Export')
            export_btn.setTarget_(self)
            export_btn.setAction_('exportPhotos:')
        content.addSubview_(export_btn)

        try:
            # Manual export: scan sources, create batch, move files
            if not self.organizer.startup_checks():
                self.append_log('Startup checks failed')
                return

            files = self.organizer.scan_all_sources()
            total = self.organizer.count_total_files(files)
            if total == 0:
                self.append_log('No files to export')
                return

            batch = self.organizer.create_batch_folder()
            self.append_log(f'Exporting {total} files to {batch}')
            moved, attempted = self.organizer.move_all_files(files, batch)
            self.append_log(f'Moved {moved}/{attempted} files to {batch}')

            if self.organizer.config.get('AUTO_CLEANUP_EMPTY_DIRS', False):
                self.append_log('Cleaning up empty source directories...')
                try:
                    self.organizer.cleanup_all_sources()
                except Exception as e:
                    self.append_log(f'Cleanup error: {e}')

        except Exception as e:
            self.append_log(f'Export failed: {e}')
