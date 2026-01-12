#!/bin/bash
set -e

APP_NAME="FileOrganizer"
VERSION="1.0.0"
DMG_NAME="${APP_NAME}-${VERSION}"
SOURCE_APP="/Applications/${APP_NAME}.app"
TEMP_DMG="temp_${DMG_NAME}.dmg"
FINAL_DMG="${DMG_NAME}.dmg"
VOLUME_NAME="${APP_NAME}"
SIZE="200m"

echo "Creating distributable DMG for ${APP_NAME}..."

# Check if app exists
if [ ! -d "$SOURCE_APP" ]; then
    echo "Error: ${SOURCE_APP} not found. Please build and install the app first."
    exit 1
fi

# Clean up old DMG
rm -f "$TEMP_DMG" "$FINAL_DMG"

# Create temporary DMG
echo "Creating temporary DMG..."
hdiutil create -size $SIZE -fs HFS+ -volname "$VOLUME_NAME" -ov "$TEMP_DMG"

# Mount the DMG
echo "Mounting DMG..."
MOUNT_DIR=$(hdiutil attach "$TEMP_DMG" | grep "/Volumes/" | awk '{print $3}')

echo "Copying app to DMG..."
cp -R "$SOURCE_APP" "$MOUNT_DIR/"

# Create Applications symlink
echo "Creating Applications symlink..."
ln -s /Applications "$MOUNT_DIR/Applications"

# Optional: Add background image and .DS_Store for custom appearance
# (Commented out - uncomment and customize if you have design assets)
# mkdir -p "$MOUNT_DIR/.background"
# cp background.png "$MOUNT_DIR/.background/"

echo "Unmounting DMG..."
hdiutil detach "$MOUNT_DIR"

# Convert to compressed read-only DMG
echo "Converting to final DMG..."
hdiutil convert "$TEMP_DMG" -format UDZO -o "$FINAL_DMG"

# Clean up temp DMG
rm -f "$TEMP_DMG"

echo "✅ DMG created successfully: $FINAL_DMG"
echo "File size: $(du -h "$FINAL_DMG" | cut -f1)"
echo ""
echo "You can now distribute this DMG file to users."
echo "Users can:"
echo "1. Double-click the DMG to mount it"
echo "2. Drag FileOrganizer.app to Applications folder"
echo "3. Eject the DMG"
echo "4. Run FileOrganizer from Applications"
