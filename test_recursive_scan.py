import os
import shutil
import tempfile
from pathlib import Path

from organizer_core import Organizer

# Setup temp dirs
root = Path(tempfile.mkdtemp(prefix='fo_test_'))
src = root / 'source'
dest_base = root / 'dest'
src_sub = src / 'subfolder'
src_sub.mkdir(parents=True)
src.mkdir(exist_ok=True)

# Create files
file_in_sub = src_sub / 'photo1.JPG'
file_in_root = src / 'photo2.jpg'
file_in_sub.write_text('test')
file_in_root.write_text('test')

config = {
    'SOURCE_FOLDERS': [str(src)],
    'DEST_BASE_FOLDER': str(dest_base),
    'ALLOWED_EXTENSIONS': ['.jpg', '.jpeg'],
    'RECURSIVE_SCAN': True,
    'STATE_FILE': str(root / 'state.json')
}

print('Source structure:')
for p in src.rglob('*'):
    print(' -', p)

org = Organizer(config)
if not org.startup_checks():
    print('Startup checks failed')
    raise SystemExit(1)

files = org.scan_all_sources()
print('Scanned files dict:', {k: [str(x) for x in v] for k, v in files.items()})
print('Total files:', org.count_total_files(files))

batch = org.create_batch_folder()
print('Batch folder:', batch)

moved, attempted = org.move_all_files(files, batch)
print('Moved, Attempted:', moved, attempted)

print('Destination contents:')
for p in batch.rglob('*'):
    print(' -', p)

# cleanup
shutil.rmtree(root)
print('Test completed')
