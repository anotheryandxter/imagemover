#!/usr/bin/env python3
"""
File Watchdog Auto Organizer - v1.5 CLEAN REFACTOR
Monitors source folders and moves files to timestamped session folders.

Architecture (v1.5):
- CLEAN: Simplified main loop
- SIMPLE: Clear state machine
- RELIABLE: Proven logic from v1.4
- MAINTAINABLE: Easy to understand and modify

Main Loop:
1. Detect files in ALL source folders
2. Wait 10 seconds (detection delay)
3. Rescan & verify (count must match)
4. Move all files to NEW session folder
5. Wait 30 seconds (cool-down)
6. Repeat from step 1
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
import time
import logging
from typing import List, Dict, Tuple
import json

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    # Source Folders (where files come from)
    "SOURCE_FOLDERS": [
        "/Volumes/Photography/Imports/Camera",
        "/Volumes/Photography/Imports/Phone",
        "/Volumes/Photography/Imports/Scanner",
    ],
    
    # Destination (where batches go)
    "DEST_BASE_FOLDER": "/Volumes/Photography/Generated",
    "BATCH_FOLDER_PREFIX": "Session",
    
    # Timing
    "DETECTION_DELAY_SECONDS": 10,
    "COOLDOWN_SECONDS": 30,
    
    # Files
    "ALLOWED_EXTENSIONS": [
        ".jpg", ".jpeg", ".png", ".raw", ".dng",
        ".tiff", ".gif", ".bmp", ".mp4", ".mov",
        ".avi", ".psd", ".ai"
    ],
    "SKIP_HIDDEN_FILES": True,
    
    # Logging
    "LOG_FILE": "file_organizer.log",
    "STATE_FILE": ".file_organizer_state.json",
    "SILENT_MODE": True,
}

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Initialize logger"""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    log_level = logging.INFO if CONFIG["SILENT_MODE"] else logging.DEBUG
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(CONFIG["LOG_FILE"]),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ============================================================================
# STATE MANAGEMENT
# ============================================================================

class State:
    """Simple state file management"""
    
    def __init__(self, state_file: str):
        self.state_file = state_file
        self.processed_files: set = set()
        self.load()
    
    def load(self):
        """Load state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.processed_files = set(data.get('processed_files', []))
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
            self.processed_files = set()
    
    def save(self):
        """Save state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump({
                    'processed_files': list(self.processed_files),
                    'last_updated': datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Could not save state: {e}")
    
    def mark_moved(self, file_path: str):
        """Mark file as moved"""
        self.processed_files.add(str(file_path))
        self.save()
    
    def is_moved(self, file_path: str) -> bool:
        """Check if file already moved"""
        return str(file_path) in self.processed_files
    
    def cleanup(self):
        """Remove files from state if they no longer exist"""
        still_exists = {f for f in self.processed_files if os.path.exists(f)}
        if len(still_exists) < len(self.processed_files):
            self.processed_files = still_exists
            self.save()

state = State(CONFIG["STATE_FILE"])

# ============================================================================
# FILE DETECTION & VALIDATION
# ============================================================================

def is_file_locked(file_path: Path, retries: int = 3) -> bool:
    """Check if file is being written to"""
    for attempt in range(retries):
        try:
            with open(file_path, 'rb') as f:
                f.read(1)
            return False  # Can read = not locked
        except (IOError, OSError):
            if attempt < retries - 1:
                time.sleep(0.3)
            else:
                return True  # Cannot read = locked
    return True

def get_eligible_files(source_folder: Path) -> List[Path]:
    """Get files ready to move from one source folder"""
    eligible = []
    
    try:
        for item in source_folder.iterdir():
            # Skip hidden
            if CONFIG["SKIP_HIDDEN_FILES"] and item.name.startswith('.'):
                continue
            
            # Must be file
            if not item.is_file():
                continue
            
            # Must match extension
            if item.suffix.lower() not in CONFIG["ALLOWED_EXTENSIONS"]:
                continue
            
            # Must not be already moved
            if state.is_moved(str(item)):
                continue
            
            # Must not be locked
            if is_file_locked(item):
                continue
            
            eligible.append(item)
    
    except Exception as e:
        logger.error(f"Error scanning {source_folder}: {e}")
    
    return eligible

def scan_all_sources() -> Dict[str, List[Path]]:
    """Scan all source folders, return files per folder"""
    result = {}
    
    for source_folder in CONFIG["SOURCE_FOLDERS"]:
        source_path = Path(source_folder)
        if not source_path.exists():
            logger.warning(f"Source folder not found: {source_folder}")
            continue
        
        files = get_eligible_files(source_path)
        result[source_folder] = files
    
    return result

def count_total_files(files_dict: Dict[str, List[Path]]) -> int:
    """Count total files across all sources"""
    return sum(len(files) for files in files_dict.values())

# ============================================================================
# BATCH CREATION & FILE MOVING
# ============================================================================

def create_batch_folder() -> Path:
    """Create new batch folder with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{CONFIG['BATCH_FOLDER_PREFIX']}_{timestamp}"
    batch_path = Path(CONFIG["DEST_BASE_FOLDER"]) / folder_name
    
    try:
        batch_path.mkdir(parents=True, exist_ok=True)
        return batch_path
    except Exception as e:
        logger.error(f"Failed to create batch folder: {e}")
        raise

def move_file(source: Path, dest_folder: Path) -> bool:
    """Move single file to destination"""
    try:
        # Handle duplicates
        dest_file = dest_folder / source.name
        counter = 1
        while dest_file.exists():
            stem = source.stem
            suffix = source.suffix
            dest_file = dest_folder / f"{stem}_{counter}{suffix}"
            counter += 1
        
        # Move file
        shutil.move(str(source), str(dest_file))
        
        # Verify move successful
        if source.exists():
            logger.error(f"Move verification failed: {source.name} still exists")
            return False
        
        # Mark as moved
        state.mark_moved(str(source))
        return True
    
    except Exception as e:
        logger.error(f"Failed to move {source.name}: {e}")
        return False

def move_all_files(files_dict: Dict[str, List[Path]], batch_folder: Path) -> Tuple[int, int]:
    """Move all files to batch folder
    
    Returns: (moved_count, total_count)
    """
    total = sum(len(files) for files in files_dict.values())
    moved = 0
    
    for source_folder, files in files_dict.items():
        for file_path in files:
            if move_file(file_path, batch_folder):
                moved += 1
    
    return moved, total

# ============================================================================
# MAIN LOGIC - CLEAN STATE MACHINE
# ============================================================================

def main_loop():
    """
    Clean main loop - repeats until user terminates
    
    Steps:
    1. Detect files
    2. Wait 10s (detection delay)
    3. Rescan files
    4. Move to batch folder
    5. Wait 30s (cooldown)
    6. Repeat
    """
    
    while True:
        try:
            # ===== STEP 1: DETECT FILES =====
            logger.info("🔍 Scanning source folders...")
            files_dict = scan_all_sources()
            total_files = count_total_files(files_dict)
            
            if total_files == 0:
                # No files, wait a bit before scanning again
                time.sleep(5)
                continue
            
            logger.info(f"🔍 DETECTED: {total_files} files")
            
            # ===== STEP 2: WAIT (DETECTION DELAY) =====
            logger.info(f"⏳ Waiting {CONFIG['DETECTION_DELAY_SECONDS']}s before moving...")
            time.sleep(CONFIG["DETECTION_DELAY_SECONDS"])
            
            # ===== STEP 3: RESCAN & VERIFY =====
            logger.info("🔍 Rescanning to verify file count...")
            files_dict_rescan = scan_all_sources()
            total_files_rescan = count_total_files(files_dict_rescan)
            
            if total_files_rescan != total_files:
                logger.info(f"📍 File count changed ({total_files} → {total_files_rescan}), rescanning...")
                continue
            
            if total_files_rescan == 0:
                logger.warning("⚠️ No files found during rescan")
                continue
            
            logger.info(f"✓ File count verified: {total_files_rescan} files stable")
            
            # ===== STEP 4: MOVE FILES =====
            logger.info(f"📤 Creating batch folder...")
            batch_folder = create_batch_folder()
            logger.info(f"📂 Created: {batch_folder.name}")
            
            logger.info(f"📤 Moving {total_files_rescan} files...")
            moved_count, total_count = move_all_files(files_dict_rescan, batch_folder)
            
            if moved_count > 0:
                logger.info(f"✓ BATCH COMPLETE: {moved_count}/{total_count} files moved")
            else:
                logger.warning(f"⚠️ No files moved (attempted {total_count})")
            
            # ===== STEP 5: COOLDOWN WAIT =====
            logger.info(f"⏳ Cooldown: waiting {CONFIG['COOLDOWN_SECONDS']}s before next scan...")
            time.sleep(CONFIG["COOLDOWN_SECONDS"])
            
            # ===== STEP 6: LOOP BACK (repeat) =====
            logger.info("🔄 Ready for next batch")
            
        except KeyboardInterrupt:
            logger.info("✓ Stopped by user")
            print("\n✓ Watchdog stopped\n")
            sys.exit(0)
        
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(5)

# ============================================================================
# INITIALIZATION
# ============================================================================

def startup_checks():
    """Verify configuration before starting"""
    
    # Check source folders
    for folder in CONFIG["SOURCE_FOLDERS"]:
        path = Path(folder)
        if not path.exists():
            logger.error(f"Source folder missing: {folder}")
            return False
        if not path.is_dir():
            logger.error(f"Not a directory: {folder}")
            return False
    
    # Ensure destination folder exists
    try:
        Path(CONFIG["DEST_BASE_FOLDER"]).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Cannot create destination folder: {e}")
        return False
    
    # Clean up state (remove files that no longer exist)
    state.cleanup()
    
    return True

def print_header():
    """Print startup message"""
    print("\n" + "=" * 70)
    print("📁 File Watchdog Auto Organizer (v1.5 - CLEAN REFACTOR)")
    print("=" * 70)
    print(f"📍 Monitoring {len(CONFIG['SOURCE_FOLDERS'])} source folders:")
    for folder in CONFIG['SOURCE_FOLDERS']:
        print(f"   • {Path(folder).name}")
    print(f"📤 Output: {Path(CONFIG['DEST_BASE_FOLDER']).name}")
    print(f"⏱️  Detection wait: {CONFIG['DETECTION_DELAY_SECONDS']}s")
    print(f"⏱️  Cooldown wait: {CONFIG['COOLDOWN_SECONDS']}s")
    print(f"🔇 Mode: {'SILENT' if CONFIG['SILENT_MODE'] else 'VERBOSE'}")
    print("=" * 70)
    print("✓ Starting main loop (Ctrl+C to stop)")
    print("=" * 70 + "\n")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    logger.info("✓ Watchdog starting...")
    
    if not startup_checks():
        logger.error("Startup checks failed")
        sys.exit(1)
    
    print_header()
    
    try:
        main_loop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
