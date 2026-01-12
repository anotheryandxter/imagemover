import os
import shutil
import time
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import subprocess

try:
    import osxphotos
    _osxphotos_import_error = None
except Exception as e:
    import logging as _logging
    osxphotos = None
    _osxphotos_import_error = e
    try:
        _logging.getLogger(__name__).exception("Failed to import osxphotos: %s", e)
    except Exception:
        # If logging isn't available yet, silently continue; we still want to record the error
        pass


    class PhotosPermissionError(Exception):
        """Raised when access to the Photos library is blocked by macOS privacy settings."""



class State:
    def __init__(self, state_file: str):
        self.state_file = state_file
        self.processed_files = set()
        self.logger = logging.getLogger(__name__)
        self.load()

    def load(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.processed_files = set(data.get('processed_files', []))
        except Exception as e:
            self.logger.warning(f"Could not load state: {e}")
            self.processed_files = set()

    def save(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump({'processed_files': list(self.processed_files), 'last_updated': datetime.now().isoformat()}, f)
        except Exception as e:
            self.logger.error(f"Could not save state: {e}")

    def mark_moved(self, file_path: str):
        self.processed_files.add(str(file_path))
        self.save()

    def is_moved(self, file_path: str) -> bool:
        return str(file_path) in self.processed_files

    def cleanup(self):
        still_exists = {f for f in self.processed_files if os.path.exists(f)}
        if len(still_exists) < len(self.processed_files):
            self.processed_files = still_exists
            self.save()


class Organizer:
    """Core organizer logic extracted from file_organizer_v1.5.py

    Consumer can instantiate with a config dict similar to the original.
    """

    def __init__(self, config: Dict):
        self.config = config.copy()
        self.logger = logging.getLogger(__name__)
        self.state = State(self.config.get('STATE_FILE', '.file_organizer_state.json'))

    def is_file_locked(self, file_path: Path, retries: int = 3) -> bool:
        for attempt in range(retries):
            try:
                with open(file_path, 'rb') as f:
                    f.read(1)
                return False
            except (IOError, OSError):
                if attempt < retries - 1:
                    time.sleep(0.3)
                else:
                    return True
        return True

    def get_eligible_files(self, source_folder: Path, recursive: bool = None) -> List[Path]:
        """
        Get eligible files in a source folder.

        If `recursive` is None, the value will be read from self.config['RECURSIVE_SCAN'].
        """
        eligible = []
        try:
            if recursive is None:
                recursive = bool(self.config.get('RECURSIVE_SCAN', False))

            if recursive:
                iterator = source_folder.rglob('*')
            else:
                iterator = source_folder.iterdir()

            for item in iterator:
                # Must be file
                if not item.is_file():
                    continue

                # Skip hidden
                if self.config.get('SKIP_HIDDEN_FILES', True) and item.name.startswith('.'):
                    continue

                # Must match extension
                if item.suffix.lower() not in self.config.get('ALLOWED_EXTENSIONS', []):
                    continue

                # Must not be already moved
                if self.state.is_moved(str(item)):
                    continue

                # Must not be locked
                if self.is_file_locked(item):
                    continue

                eligible.append(item)

        except Exception as e:
            self.logger.error(f"Error scanning {source_folder}: {e}")
        return eligible

    def scan_all_sources(self) -> Dict[str, List[Path]]:
        result = {}
        for source_folder in self.config.get('SOURCE_FOLDERS', []):
            source_path = Path(source_folder)
            if not source_path.exists():
                self.logger.warning(f"Source folder not found: {source_folder}")
                continue
            files = self.get_eligible_files(source_path, recursive=bool(self.config.get('RECURSIVE_SCAN', False)))
            result[source_folder] = files
        return result

    def cleanup_empty_directories(self, source_folder_path: Path):
        """
        Recursively remove empty subdirectories within source folder.
        """
        try:
            for dirpath, dirnames, filenames in os.walk(source_folder_path, topdown=False):
                # Skip root source folder itself
                if dirpath == str(source_folder_path):
                    continue
                try:
                    if not os.listdir(dirpath):
                        os.rmdir(dirpath)
                        self.logger.info(f"Removed empty directory: {Path(dirpath).relative_to(source_folder_path)}")
                except OSError:
                    # Not empty or permission denied; skip
                    pass
        except Exception as e:
            self.logger.error(f"Error cleaning up directories in {source_folder_path}: {e}")

    def cleanup_all_sources(self):
        if not bool(self.config.get('AUTO_CLEANUP_EMPTY_DIRS', False)):
            return
        for source_folder in self.config.get('SOURCE_FOLDERS', []):
            source_path = Path(source_folder)
            if source_path.exists():
                self.cleanup_empty_directories(source_path)

    def export_session(self) -> Tuple[int, int, Path]:
        """Export session: move all files from source subfolders to destination, then delete empty subfolders.
        
        Returns: (moved_count, total_count, batch_folder)
        """
        # Scan all sources recursively
        files_dict = self.scan_all_sources()
        total = self.count_total_files(files_dict)
        
        if total == 0:
            self.logger.info('No files to export')
            return 0, 0, None
        
        # Create batch folder
        batch_folder = self.create_batch_folder()
        self.logger.info(f'Export session: moving {total} files to {batch_folder.name}')
        
        # Move all files
        moved, attempted = self.move_all_files(files_dict, batch_folder)
        
        # Cleanup empty directories
        self.logger.info('Cleaning up empty directories...')
        for source_folder in self.config.get('SOURCE_FOLDERS', []):
            source_path = Path(source_folder)
            if source_path.exists():
                self.cleanup_empty_directories(source_path)
        
        return moved, attempted, batch_folder

    def count_total_files(self, files_dict: Dict[str, List[Path]]) -> int:
        return sum(len(files) for files in files_dict.values())

    def create_batch_folder(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{self.config.get('BATCH_FOLDER_PREFIX','Session')}_{timestamp}"
        batch_path = Path(self.config.get('DEST_BASE_FOLDER')) / folder_name
        batch_path.mkdir(parents=True, exist_ok=True)
        return batch_path

    def move_file(self, source: Path, dest_folder: Path) -> bool:
        try:
            dest_file = dest_folder / source.name
            counter = 1
            while dest_file.exists():
                stem = source.stem
                suffix = source.suffix
                dest_file = dest_folder / f"{stem}_{counter}{suffix}"
                counter += 1
            shutil.move(str(source), str(dest_file))
            if source.exists():
                self.logger.error(f"Move verification failed: {source.name} still exists")
                return False
            self.state.mark_moved(str(source))
            return True
        except Exception as e:
            self.logger.error(f"Failed to move {source.name}: {e}")
            return False

    def move_all_files(self, files_dict: Dict[str, List[Path]], batch_folder: Path) -> Tuple[int, int]:
        total = sum(len(files) for files in files_dict.values())
        moved = 0
        for source_folder, files in files_dict.items():
            for file_path in files:
                if self.move_file(file_path, batch_folder):
                    moved += 1
        return moved, total

    def startup_checks(self) -> bool:
        for folder in self.config.get('SOURCE_FOLDERS', []):
            path = Path(folder)
            if not path.exists() or not path.is_dir():
                self.logger.error(f"Source folder invalid: {folder}")
                return False
        try:
            Path(self.config.get('DEST_BASE_FOLDER')).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Cannot create destination folder: {e}")
            return False
        self.state.cleanup()
        return True


class PhotosExporter:
    """Minimal Photos integration using `osxphotos`.

    - `export_originals(dest_folder, uuids=None)` exports originals to dest_folder.
    - `delete_from_photos(uuids)` attempts to delete photos (guarded and best-effort).

    NOTE: Deleting from Photos is potentially destructive — the method will only run
    if explicitly enabled and will attempt to use osxphotos APIs; if unavailable it
    will raise an error. Users must grant Photos permissions to the app.
    """

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        if osxphotos is None:
            self.logger.warning("osxphotos not available — Photos export disabled until installed")
            try:
                # If an import error was captured at module import time, log it for debugging
                if '_osxphotos_import_error' in globals() and globals()['_osxphotos_import_error'] is not None:
                    self.logger.error('osxphotos import error: %s', globals()['_osxphotos_import_error'])
            except Exception:
                pass

    def export_originals(self, dest_folder: str, uuids: List[str] = None) -> List[str]:
        """Export originals from Photos library to dest_folder.

        Returns list of exported file paths.
        """
        if osxphotos is None:
            raise RuntimeError("osxphotos is not installed. Run: pip install osxphotos")

        export_dir = Path(dest_folder)
        export_dir.mkdir(parents=True, exist_ok=True)

        exported = []
        try:
            # Create PhotosDB; if this fails it's usually a permission issue
            try:
                db = osxphotos.PhotosDB()
            except Exception as e:
                # Detect common TCC / permission errors and provide guidance
                self.logger.error("Failed to open Photos library: %s", e)
                msg = str(e)
                if isinstance(e, (PermissionError, OSError)) and ("Operation not permitted" in msg or getattr(e, 'errno', None) == 1):
                    guidance = (
                        "Photos library access was blocked by macOS privacy settings.\n"
                        "Please grant Full Disk Access or Photos permission to the app or Terminal:\n"
                        "  1) Open System Settings → Privacy & Security.\n"
                        "  2) Under Full Disk Access, add this app (dist/FileOrganizer.app) or your Terminal app if you launch from terminal.\n"
                        "  3) Also check Photos and allow access to the Photos library for the app.\n"
                        "  4) Restart the app after granting permissions.\n"
                        "If you prefer to run from Terminal, add Terminal to Full Disk Access and re-run the packaged binary."
                    )
                    self.logger.error(guidance)
                    raise PhotosPermissionError(guidance)
                raise

            # Normalize photos_by_uuid: newer osxphotos may expose it as a callable
            photos_map = None
            try:
                raw = getattr(db, 'photos_by_uuid', None)
                if callable(raw):
                    photos_map = raw()
                else:
                    photos_map = raw
            except Exception as e:
                self.logger.warning(f"Could not obtain photos_by_uuid mapping: {e}")
                photos_map = {}

            # Resolve PhotoInfo objects for requested UUIDs
            photos_to_export = []
            if uuids:
                for u in uuids:
                    try:
                        photo = photos_map.get(u) if photos_map is not None else None
                        if photo is None:
                            self.logger.warning(f"UUID not found in Photos library: {u}")
                        else:
                            photos_to_export.append(photo)
                    except Exception as e:
                        self.logger.warning(f"Error resolving uuid {u}: {e}")
            else:
                # Export everything (be conservative: use photos_by_uuid values)
                photos_to_export = list(photos_map.values()) if photos_map is not None else []

            # Lazy import of exporter classes (avoid failing module import earlier)
            from osxphotos.photoexporter import PhotoExporter, ExportOptions

            opts = ExportOptions(
                download_missing=True,
                export_as_hardlink=False,
                overwrite=False,
                use_photos_export=False,
            )

            for photo in photos_to_export:
                try:
                    exporter = PhotoExporter(photo)
                    results = exporter.export(str(export_dir), options=opts)
                    # ExportResults.exported holds exported file paths
                    for p in getattr(results, 'exported', []):
                        exported.append(str(p))
                except Exception as e:
                    self.logger.error(f"Failed to export photo {getattr(photo, 'uuid', photo)}: {e}")

        except Exception as e:
            # Provide specific guidance for permission errors
            msg = str(e)
            if isinstance(e, (PermissionError, OSError)) and ("Operation not permitted" in msg or getattr(e, 'errno', None) == 1):
                guidance = (
                    "Photos export failed because access to the Photos library is blocked by macOS privacy settings.\n"
                    "Grant Full Disk Access or Photos permission to the app (or Terminal) and try again:\n"
                    "  System Settings → Privacy & Security → Full Disk Access → add dist/FileOrganizer.app or Terminal.\n"
                    "  System Settings → Privacy & Security → Photos → allow access for the app.\n"
                    "Then restart the app and retry the export."
                )
                self.logger.error(guidance)
                raise PhotosPermissionError(guidance)
            else:
                self.logger.error(f"Photos export failed: {e}")
            raise

        return exported

    def delete_from_photos(self, uuids: List[str]) -> bool:
        """Best-effort delete from Photos. Requires osxphotos and appropriate permissions.

        Returns True on success, False otherwise.
        """
        if osxphotos is None:
            self.logger.error("osxphotos not installed — cannot delete from Photos")
            return False

        try:
            db = osxphotos.PhotosDB()
            # osxphotos provides a delete method in newer versions; attempt to use it
            if hasattr(db, 'delete'):
                db.delete(photos=uuids)
                return True
            else:
                # Fallback: attempt AppleScript delete via osascript (best-effort)
                # This is risky and may not work for all Photos versions; warn the user.
                for uid in uuids:
                    script = f'tell application "Photos" to delete (first media item whose uuid is "{uid}")'
                    subprocess.run(['osascript', '-e', script], check=False)
                return True

        except Exception as e:
            self.logger.error(f"Failed to delete from Photos: {e}")
            return False

