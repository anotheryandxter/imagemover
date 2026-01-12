import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QLineEdit, QLabel, QTextEdit, QFileDialog, QSpinBox
)
from PySide6.QtWidgets import QCheckBox
from PySide6.QtCore import QThread, Signal
from organizer_core import Organizer, PhotosExporter


LOG = logging.getLogger(__name__)


class Worker(QThread):
    log_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, organizer: Organizer):
        super().__init__()
        self.organizer = organizer
        self._running = False
        self._paused = False

    def run(self):
        self._running = True
        cfg = self.organizer.config
        detect = cfg.get('DETECTION_DELAY_SECONDS', 10)
        cooldown = cfg.get('COOLDOWN_SECONDS', 30)

        while self._running:
            if self._paused:
                self.msleep(200)
                continue

            self.log_signal.emit('Scanning sources...')
            files = self.organizer.scan_all_sources()
            total = self.organizer.count_total_files(files)
            if total == 0:
                self.msleep(1000)
                continue

            self.log_signal.emit(f'Detected {total} files, waiting {detect}s')
            for _ in range(int(detect * 10)):
                if not self._running or self._paused:
                    break
                self.msleep(100)

            files_rescan = self.organizer.scan_all_sources()
            total_rescan = self.organizer.count_total_files(files_rescan)
            if total_rescan != total:
                self.log_signal.emit('File count changed, skipping this round')
                continue

            batch = self.organizer.create_batch_folder()
            self.log_signal.emit(f'Creating batch: {batch.name}')
            moved, attempted = self.organizer.move_all_files(files_rescan, batch)
            self.log_signal.emit(f'Moved {moved}/{attempted} files')

            for _ in range(int(cooldown * 10)):
                if not self._running or self._paused:
                    break
                self.msleep(100)

        self.status_signal.emit('stopped')

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False


class MainWindow(QWidget):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle('File Organizer - GUI')
        self.organizer = Organizer(config)
        self.worker = Worker(self.organizer)
        self.worker.log_signal.connect(self.append_log)
        self.worker.status_signal.connect(self.on_status)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Source folders list
        self.src_list = QListWidget()
        for s in self.organizer.config.get('SOURCE_FOLDERS', []):
            self.src_list.addItem(s)

        add_btn = QPushButton('Add Source')
        add_btn.clicked.connect(self.add_source)
        remove_btn = QPushButton('Remove Selected')
        remove_btn.clicked.connect(self.remove_source)

        src_h = QHBoxLayout()
        src_h.addWidget(add_btn)
        src_h.addWidget(remove_btn)

        # Destination
        self.dest_edit = QLineEdit(self.organizer.config.get('DEST_BASE_FOLDER', ''))
        dest_btn = QPushButton('Choose Destination')
        dest_btn.clicked.connect(self.choose_dest)

        dest_h = QHBoxLayout()
        dest_h.addWidget(QLabel('Destination:'))
        dest_h.addWidget(self.dest_edit)

        # Photos export controls
        self.photos_export_btn = QPushButton('Export from Photos')
        self.photos_export_btn.clicked.connect(self.export_from_photos)
        self.delete_photos_chk = QCheckBox('Delete from Photos after successful export')

        dest_h.addWidget(dest_btn)

        # Controls
        self.start_btn = QPushButton('Start')
        ctrl_h.addWidget(self.photos_export_btn)
        ctrl_h.addWidget(self.delete_photos_chk)
        self.start_btn.clicked.connect(self.start)
        self.pause_btn = QPushButton('Pause')
        self.pause_btn.clicked.connect(self.pause)
        self.stop_btn = QPushButton('Stop')
        self.stop_btn.clicked.connect(self.stop)

        ctrl_h = QHBoxLayout()
        ctrl_h.addWidget(self.start_btn)
        ctrl_h.addWidget(self.pause_btn)
        ctrl_h.addWidget(self.stop_btn)

        # Interval controls
        self.detect_spin = QSpinBox()
        self.detect_spin.setRange(1, 3600)
        self.detect_spin.setValue(self.organizer.config.get('DETECTION_DELAY_SECONDS', 10))
        self.detect_spin.valueChanged.connect(self.update_config)

        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 3600)
        self.cooldown_spin.setValue(self.organizer.config.get('COOLDOWN_SECONDS', 30))
        self.cooldown_spin.valueChanged.connect(self.update_config)

        ints_h = QHBoxLayout()
        ints_h.addWidget(QLabel('Detect(s):'))
        ints_h.addWidget(self.detect_spin)
        ints_h.addWidget(QLabel('Cooldown(s):'))
        ints_h.addWidget(self.cooldown_spin)

        # Log area
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        layout.addWidget(QLabel('Source Folders:'))
        layout.addWidget(self.src_list)
        layout.addLayout(src_h)
        layout.addLayout(dest_h)
        layout.addLayout(ctrl_h)
        layout.addLayout(ints_h)
        layout.addWidget(QLabel('Log:'))
        layout.addWidget(self.log)

        self.setLayout(layout)

    def append_log(self, text: str):
        self.log.append(text)

    def on_status(self, st: str):
        self.append_log(f'Status: {st}')

    def add_source(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Source Folder')
        if path:
            self.src_list.addItem(path)
            self.organizer.config['SOURCE_FOLDERS'] = [self.src_list.item(i).text() for i in range(self.src_list.count())]

    def remove_source(self):
        for item in self.src_list.selectedItems():
            self.src_list.takeItem(self.src_list.row(item))
        self.organizer.config['SOURCE_FOLDERS'] = [self.src_list.item(i).text() for i in range(self.src_list.count())]

    def choose_dest(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Destination Folder')
        if path:
            self.dest_edit.setText(path)
            self.organizer.config['DEST_BASE_FOLDER'] = path

    def update_config(self):
        self.organizer.config['DETECTION_DELAY_SECONDS'] = int(self.detect_spin.value())
        self.organizer.config['COOLDOWN_SECONDS'] = int(self.cooldown_spin.value())

    def start(self):
        # update config from UI
        self.organizer.config['SOURCE_FOLDERS'] = [self.src_list.item(i).text() for i in range(self.src_list.count())]
        self.organizer.config['DEST_BASE_FOLDER'] = self.dest_edit.text() or self.organizer.config.get('DEST_BASE_FOLDER')
        if not self.organizer.startup_checks():
            self.append_log('Startup checks failed, check folders.')
            return
        if not self.worker.isRunning():
            self.worker.start()
            self.append_log('Worker started')

    def export_from_photos(self):
        # Export originals from Photos into a new batch folder
        try:
            exporter = PhotosExporter()
            batch = self.organizer.create_batch_folder()
            self.append_log(f'Exporting originals from Photos to {batch}')
            exported = exporter.export_originals(str(batch))
            self.append_log(f'Exported {len(exported)} files')

            if self.delete_photos_chk.isChecked():
                # Ask for confirmation via log (UI prompt could be added)
                self.append_log('Delete after export requested — attempting delete (best-effort)')
                # Attempt to map exported files back to UUIDs is not trivial; try best-effort
                # Here we do NOT have UUIDs; osxphotos export could be extended to return them.
                self.append_log('WARNING: delete operation requires UUID mapping; manual verification recommended.')

        except Exception as e:
            self.append_log(f'Photos export failed: {e}')

    def pause(self):
        if self.worker._paused:
            self.worker.resume()
            self.append_log('Resumed')
        else:
            self.worker.pause()
            self.append_log('Paused')

    def stop(self):
        if self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
            self.append_log('Stopped')


def main():
    logging.basicConfig(level=logging.INFO)
    # Default config mirrors original script but user can modify from UI
    default_config = {
        'SOURCE_FOLDERS': [],
        'DEST_BASE_FOLDER': str(Path.home() / 'Desktop' / 'Organized'),
        'BATCH_FOLDER_PREFIX': 'Session',
        'DETECTION_DELAY_SECONDS': 10,
        'COOLDOWN_SECONDS': 30,
        'ALLOWED_EXTENSIONS': ['.jpg', '.jpeg', '.png', '.raw', '.dng', '.tiff', '.gif', '.bmp', '.mp4', '.mov', '.avi', '.psd', '.ai'],
        'RECURSIVE_SCAN': True,
        'SKIP_HIDDEN_FILES': True,
        'STATE_FILE': '.file_organizer_state.json'
    }

    app = QApplication(sys.argv)
    w = MainWindow(default_config)
    w.resize(800, 600)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
