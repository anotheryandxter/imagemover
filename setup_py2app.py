from setuptools import setup

APP = ['pyobjc_app.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    # Include PyObjC modules and the organizer core; py2app will bundle these
    'includes': ['objc', 'AppKit', 'Foundation', 'Photos', 'organizer_core', 'osxphotos'],
    # Exclude large/optional packages that trigger benign missing-module warnings
    'excludes': [
        'IPython', 'ipykernel', 'jupyter', 'numpy', 'pandas', 'matplotlib', 'cryptography', 'sphinx',
        'tornado', 'win32com', 'pygments', 'pkg_resources', 'setuptools', 'scipy', 'torch', 'tensorflow'
    ],
    # Ensure core packages are included
    'packages': ['organizer_core', 'osxphotos'],
    # Use a generated app.icns in project root. build_app.sh will convert .ico -> .icns if needed.
    'iconfile': 'app.icns',
    'plist': {
        'CFBundleName': 'FileOrganizer',
        'CFBundleShortVersionString': '1.0',
        'CFBundleIdentifier': 'com.example.fileorganizer',
    }
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
