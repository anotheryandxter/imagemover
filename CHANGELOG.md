# Changelog

## Version 1.0.0 (2024)

### Initial Release 🎉

#### Features
- ✅ Native macOS GUI application (Apple Silicon + Intel compatible)
- ✅ Automatic file organization from source to destination
- ✅ Photos app integration with export functionality
- ✅ Option to delete from Photos after successful export
- ✅ Real-time file monitoring (watchdog)
- ✅ Background processing with pause/resume support
- ✅ Comprehensive logging to ~/Library/Logs/FileOrganizer.log

#### Technical
- Built with PyObjC (native macOS AppKit)
- Packaged with py2app (universal binary)
- Includes osxphotos for Photos integration
- File-based logging with exception handling
- Supports macOS 11.0+ (Big Sur and later)

#### Distribution
- DMG installer (34MB compressed)
- Drag-and-drop installation
- No additional dependencies required

#### Known Requirements
- macOS Photos access permission
- Full Disk Access for Photos database (if needed)
- Grant permissions when prompted on first run
