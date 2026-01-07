import threading
import time
from organizer_core import Organizer


class SimpleWorker(threading.Thread):
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
                time.sleep(0.2)
                continue
            self.log_cb('Scanning sources...')
            files = self.organizer.scan_all_sources()
            total = self.organizer.count_total_files(files)
            if total == 0:
                time.sleep(1.0)
                continue

            self.log_cb(f'Detected {total} files, waiting {detect}s')
            time.sleep(detect)

            files_rescan = self.organizer.scan_all_sources()
            total_rescan = self.organizer.count_total_files(files_rescan)
            if total_rescan != total:
                self.log_cb('File count changed, skipping this round')
                continue

            batch = self.organizer.create_batch_folder()
            self.log_cb(f'Creating batch: {batch.name}')
            moved, attempted = self.organizer.move_all_files(files_rescan, batch)
            self.log_cb(f'Moved {moved}/{attempted} files')

            time.sleep(cooldown)

        self.log_cb('Worker stopped')

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False
