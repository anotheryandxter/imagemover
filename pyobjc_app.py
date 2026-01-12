#!/usr/bin/env python3
"""Native macOS UI using PyObjC (AppKit) that wraps the Organizer core."""
import sys
from datetime import datetime
import threading
import logging
import sys
import traceback
import threading as _threading
import signal as _signal
from pathlib import Path

from AppKit import NSApplication, NSApp, NSWindow, NSButton, NSTextField, NSTextView, NSScrollView, NSMakeRect, NSOpenPanel, NSURL
from Foundation import NSObject, NSLog

from organizer_core import Organizer

# Configure logging to a file so we capture unhandled exceptions from the packaged app
log_path = Path.home() / 'Library' / 'Logs' / 'FileOrganizer.log'
log_path.parent.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(str(log_path), encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
file_handler.setFormatter(formatter)
root_logger = logging.getLogger()
if not root_logger.handlers:
    logging.basicConfig(level=logging.INFO)
root_logger.addHandler(file_handler)
root_logger.setLevel(logging.INFO)
logger = logging.getLogger(__name__)
logger.info('pyobjc_app module imported')


# Global exception handlers to capture crashes and write tracebacks to the log file
def _report_exception(exc_type, exc_value, exc_traceback):
    try:
        if issubclass(exc_type, KeyboardInterrupt):
            # let default handler handle keyboard interrupts
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
    except Exception:
        pass
    tb = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.error('Uncaught exception:\n%s', tb)
    try:
        # Try to show a native alert if AppKit is available
        from AppKit import NSAlert
        alert = NSAlert.alloc().init()
        alert.setMessageText_('FileOrganizer: Unexpected Error')
        alert.setInformativeText_('An unexpected error occurred. See the log at: ' + str(log_path))
        alert.addButtonWithTitle_('OK')
        alert.runModal()
    except Exception:
        pass


sys.excepthook = _report_exception

# Python 3.8+ threading hook
try:
    def _thread_excepthook(args):
        _report_exception(args.exc_type, args.exc_value, args.exc_traceback)

    _threading.excepthook = _thread_excepthook
except Exception:
    pass

# Signal handlers to log termination signals
def _signal_handler(signum, frame):
    logger.warning('Received signal: %s', signum)
    try:
        tb = ''.join(traceback.format_stack(frame))
        logger.debug('Stack at signal:\n%s', tb)
    except Exception:
        pass

for _sig in ('SIGTERM', 'SIGINT', 'SIGHUP'):
    try:
        _signal.signal(getattr(_signal, _sig), _signal_handler)
    except Exception:
        pass

# Write an immediate startup marker to both the user log and /tmp to aid debugging
try:
    with open(str(log_path), 'a', encoding='utf-8') as _f:
        _f.write(f"STARTUP_MARKER: {datetime.now().isoformat()}\n")
except Exception:
    pass

try:
    with open('/tmp/FileOrganizer.log', 'a', encoding='utf-8') as _f:
        _f.write(f"STARTUP_MARKER: {datetime.now().isoformat()}\n")
except Exception:
    pass


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
        self.log_view = None

    def append_log(self, msg: str):
        logger.debug(f'append_log called: {msg}')
        # Schedule UI update on the main thread by calling `updateLog_:` there.
        if not self.log_view:
            logger.warning('log_view not yet initialized')
            return
        try:
            self.performSelectorOnMainThread_withObject_waitUntilDone_('updateLog:', msg, False)
        except Exception as e:
            logger.error(f'performSelector failed: {e}')
            # Fallback: try direct insert (may fail if called off-main-thread)
            try:
                cur = self.log_view.string() or ''
                self.log_view.setString_(cur + msg + '\n')
            except Exception as e2:
                logger.error(f'direct setString failed: {e2}')

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

    def exportSession_(self, sender):
        """Export Session: move all files from source subfolders to destination, then cleanup empty dirs"""
        try:
            if not self.organizer.config.get('SOURCE_FOLDERS'):
                self.append_log('No source folders configured')
                return
            
            self.append_log('Export Session: scanning all source folders...')
            moved, attempted, batch_folder = self.organizer.export_session()
            
            if batch_folder:
                self.append_log(f'Export Session complete: {moved}/{attempted} files moved to {batch_folder.name}')
                self.append_log('Empty subfolders cleaned up')
            else:
                self.append_log('No files found to export')
        except Exception as e:
            self.append_log(f'Export Session failed: {e}')
            logger.exception('Export session error')

    def applicationDidFinishLaunching_(self, notification):
        logger.info('applicationDidFinishLaunching_ called')
        # Create organizer and build UI here (on main thread after app finishes launching)
        self.organizer = Organizer({
            'SOURCE_FOLDERS': [],
            'DEST_BASE_FOLDER': str(Path.home() / 'Desktop' / 'Organized'),
            'BATCH_FOLDER_PREFIX': 'Session',
            'DETECTION_DELAY_SECONDS': 10,
            'COOLDOWN_SECONDS': 30,
            'ALLOWED_EXTENSIONS': ['.jpg', '.jpeg', '.png', '.raw', '.dng', '.tiff', '.gif', '.bmp', '.mp4', '.mov', '.avi', '.psd', '.ai'],
            'SKIP_HIDDEN_FILES': True,
            'RECURSIVE_SCAN': True,
            'STATE_FILE': '.file_organizer_state.json'
        })
        self.worker = None

        # Build UI
        logger.info('Building UI')
        try:
            from AppKit import NSTitledWindowMask, NSClosableWindowMask, NSMiniaturizableWindowMask, NSResizableWindowMask
            style_mask = NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSResizableWindowMask
        except:
            style_mask = 15  # fallback
            
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(100.0, 100.0, 900.0, 600.0),
            style_mask,
            2, False
        )
        self.window.setTitle_('File Organizer (PyObjC)')
        logger.info(f'Window created: {self.window}')

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
        export_btn.setTitle_('Export Photos')
        export_btn.setTarget_(self)
        export_btn.setAction_('exportPhotos:')
        content.addSubview_(export_btn)

        export_session_btn = NSButton.alloc().initWithFrame_(NSMakeRect(490, 440, 160, 32))
        export_session_btn.setTitle_('Export Session')
        export_session_btn.setTarget_(self)
        export_session_btn.setAction_('exportSession:')
        content.addSubview_(export_session_btn)

        # Log view (scrollable text area)
        scroll_view = NSScrollView.alloc().initWithFrame_(NSMakeRect(20, 20, 860, 400))
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setAutoresizingMask_(18)
        
        self.log_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 860, 400))
        self.log_view.setEditable_(False)
        scroll_view.setDocumentView_(self.log_view)
        content.addSubview_(scroll_view)

        # Show window
        logger.info('About to show window')
        self.window.center()
        self.window.setLevel_(3)  # NSFloatingWindowLevel
        self.window.orderFrontRegardless()
        self.window.makeKeyAndOrderFront_(None)
        logger.info('Window shown')
        self.append_log('File Organizer started. Configure sources and destination, then click Start.')
        
        logger.info('applicationDidFinishLaunching_ completed')


if __name__ == '__main__':
    try:
        app = NSApplication.sharedApplication()
        logger.info('Created NSApplication')
        delegate = AppDelegate.alloc().init()
        app.setDelegate_(delegate)
        try:
            app.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular
        except Exception:
            logger.debug('Could not set activation policy')
        app.activateIgnoringOtherApps_(True)
        logger.info('Starting AppKit run loop')
        app.run()
        logger.info('AppKit run loop exited')
    except Exception:
        logger.exception('Failed to start AppKit run loop')
