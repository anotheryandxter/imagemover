#!/bin/bash
# Quick distribution script for FileOrganizer

echo "🚀 FileOrganizer Distribution Script"
echo "======================================"
echo ""

# Check if app is built
if [ ! -d "/Applications/FileOrganizer.app" ]; then
    echo "❌ FileOrganizer.app not found in /Applications"
    echo "   Run './build_app.sh' first"
    exit 1
fi

# Build DMG
echo "📦 Creating DMG installer..."
./create_dmg.sh

if [ -f "FileOrganizer-1.0.0.dmg" ]; then
    echo ""
    echo "✅ Distribution package ready!"
    echo ""
    echo "📊 Package Info:"
    echo "   File: FileOrganizer-1.0.0.dmg"
    echo "   Size: $(du -h FileOrganizer-1.0.0.dmg | cut -f1)"
    echo "   Location: $(pwd)/FileOrganizer-1.0.0.dmg"
    echo ""
    echo "📤 Distribution Options:"
    echo ""
    echo "1. 🌐 GitHub Release:"
    echo "   - Go to: https://github.com/anotheryandxter/imagemover/releases"
    echo "   - Create new release"
    echo "   - Upload FileOrganizer-1.0.0.dmg"
    echo ""
    echo "2. 📧 Direct Share:"
    echo "   - Upload to cloud storage (Dropbox, Google Drive, etc.)"
    echo "   - Share download link"
    echo ""
    echo "3. 🔐 Code Signing (Optional but Recommended):"
    echo "   - Get Apple Developer ID: https://developer.apple.com"
    echo "   - Sign with: codesign --deep --force --sign 'Developer ID' FileOrganizer.app"
    echo "   - Notarize: xcrun notarytool submit FileOrganizer-1.0.0.dmg"
    echo ""
    echo "📝 Don't forget to update README.md with download link!"
else
    echo "❌ DMG creation failed"
    exit 1
fi
