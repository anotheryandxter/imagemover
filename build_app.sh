#!/usr/bin/env bash
set -euo pipefail

# Build standalone macOS .app using py2app
# NOTE: To produce an Apple Silicon (arm64) binary, run this on an Apple Silicon Python interpreter

VENV_DIR=.venv

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install py2app
# Ensure PyObjC packages installed for bundling
pip install pyobjc-core pyobjc-framework-Cocoa || true

ICON_SOURCE_PNG="/Users/chiio/File R/REFLECTION LOGO/Logo RF Top Only Black.png"
ICON_SOURCE_ICO="/Users/chiio/File R/REFLECTION LOGO/Logo RF Top Only Black.ico"
# Prefer PNG if available, otherwise fall back to ICO
if [ -f "$ICON_SOURCE_PNG" ]; then
	ICON_SOURCE="$ICON_SOURCE_PNG"
elif [ -f "$ICON_SOURCE_ICO" ]; then
	ICON_SOURCE="$ICON_SOURCE_ICO"
else
	ICON_SOURCE="$ICON_SOURCE_PNG" # leave as default (may not exist)
fi
ICON_TARGET="app.icns"

# Convert icon if needed
if [ -f "$ICON_SOURCE" ]; then
	echo "Found source icon: $ICON_SOURCE"
	ext="${ICON_SOURCE##*.}"
	# macOS ships with bash 3.x which doesn't support ${var,,}; use tr instead
	ext_lower="$(echo "$ext" | tr '[:upper:]' '[:lower:]')"
	if [ "$ext_lower" = "icns" ]; then
		echo "Copying .icns to project root as $ICON_TARGET"
		cp "$ICON_SOURCE" "$ICON_TARGET"
	else
		echo "Converting $ICON_SOURCE -> $ICON_TARGET"
		TMP_ICONSET="tmp.iconset"
		rm -rf "$TMP_ICONSET"
		mkdir -p "$TMP_ICONSET"

		# Preferred: ImageMagick v7 'magick' or v6 'convert'
		if command -v magick >/dev/null 2>&1; then
			echo "Using ImageMagick 'magick' to generate iconset"
			CONVERT_CMD="magick convert"
		elif command -v convert >/dev/null 2>&1; then
			echo "Using ImageMagick 'convert' to generate iconset"
			CONVERT_CMD="convert"
		else
			CONVERT_CMD=""
		fi

		if [ -n "$CONVERT_CMD" ]; then
			# generate required sizes (including @2x)
			if command -v magick >/dev/null 2>&1; then
				magick convert "$ICON_SOURCE" -resize 16x16     "$TMP_ICONSET/icon_16x16.png"
				magick convert "$ICON_SOURCE" -resize 32x32     "$TMP_ICONSET/icon_16x16@2x.png"
				magick convert "$ICON_SOURCE" -resize 32x32     "$TMP_ICONSET/icon_32x32.png"
				magick convert "$ICON_SOURCE" -resize 64x64     "$TMP_ICONSET/icon_32x32@2x.png"
				magick convert "$ICON_SOURCE" -resize 128x128   "$TMP_ICONSET/icon_128x128.png"
				magick convert "$ICON_SOURCE" -resize 256x256   "$TMP_ICONSET/icon_128x128@2x.png"
				magick convert "$ICON_SOURCE" -resize 256x256   "$TMP_ICONSET/icon_256x256.png"
				magick convert "$ICON_SOURCE" -resize 512x512   "$TMP_ICONSET/icon_256x256@2x.png"
				magick convert "$ICON_SOURCE" -resize 512x512   "$TMP_ICONSET/icon_512x512.png"
				magick convert "$ICON_SOURCE" -resize 1024x1024 "$TMP_ICONSET/icon_512x512@2x.png"
			else
				convert "$ICON_SOURCE" -resize 16x16     "$TMP_ICONSET/icon_16x16.png"
				convert "$ICON_SOURCE" -resize 32x32     "$TMP_ICONSET/icon_16x16@2x.png"
				convert "$ICON_SOURCE" -resize 32x32     "$TMP_ICONSET/icon_32x32.png"
				convert "$ICON_SOURCE" -resize 64x64     "$TMP_ICONSET/icon_32x32@2x.png"
				convert "$ICON_SOURCE" -resize 128x128   "$TMP_ICONSET/icon_128x128.png"
				convert "$ICON_SOURCE" -resize 256x256   "$TMP_ICONSET/icon_128x128@2x.png"
				convert "$ICON_SOURCE" -resize 256x256   "$TMP_ICONSET/icon_256x256.png"
				convert "$ICON_SOURCE" -resize 512x512   "$TMP_ICONSET/icon_256x256@2x.png"
				convert "$ICON_SOURCE" -resize 512x512   "$TMP_ICONSET/icon_512x512.png"
				convert "$ICON_SOURCE" -resize 1024x1024 "$TMP_ICONSET/icon_512x512@2x.png"
			fi

		# Fallback: icotool (from icoutils) to extract PNGs
		elif command -v icotool >/dev/null 2>&1; then
			echo "Using icotool to extract PNGs"
			icotool -x -o "$TMP_ICONSET" "$ICON_SOURCE" || true
			# attempt to rename extracted pngs to standard iconset names (best-effort)
			i=0
			for f in "$TMP_ICONSET"/*.png; do
				case $i in
					0) mv "$f" "$TMP_ICONSET/icon_16x16.png" ;;
					1) mv "$f" "$TMP_ICONSET/icon_16x16@2x.png" ;;
					2) mv "$f" "$TMP_ICONSET/icon_32x32.png" ;;
					3) mv "$f" "$TMP_ICONSET/icon_32x32@2x.png" ;;
					4) mv "$f" "$TMP_ICONSET/icon_128x128.png" ;;
					5) mv "$f" "$TMP_ICONSET/icon_128x128@2x.png" ;;
					6) mv "$f" "$TMP_ICONSET/icon_256x256.png" ;;
					7) mv "$f" "$TMP_ICONSET/icon_256x256@2x.png" ;;
					8) mv "$f" "$TMP_ICONSET/icon_512x512.png" ;;
					9) mv "$f" "$TMP_ICONSET/icon_512x512@2x.png" ;;
					*) rm -f "$f" ;;
				esac
				i=$((i+1))
			done
		# Fallback: macOS 'sips' to resize images
		elif command -v sips >/dev/null 2>&1; then
			echo "Using macOS 'sips' to generate iconset"
			sips -z 16 16  "$ICON_SOURCE" --out "$TMP_ICONSET/icon_16x16.png"
			sips -z 32 32  "$ICON_SOURCE" --out "$TMP_ICONSET/icon_16x16@2x.png"
			sips -z 32 32  "$ICON_SOURCE" --out "$TMP_ICONSET/icon_32x32.png"
			sips -z 64 64  "$ICON_SOURCE" --out "$TMP_ICONSET/icon_32x32@2x.png"
			sips -z 128 128 "$ICON_SOURCE" --out "$TMP_ICONSET/icon_128x128.png"
			sips -z 256 256 "$ICON_SOURCE" --out "$TMP_ICONSET/icon_128x128@2x.png"
			sips -z 256 256 "$ICON_SOURCE" --out "$TMP_ICONSET/icon_256x256.png"
			sips -z 512 512 "$ICON_SOURCE" --out "$TMP_ICONSET/icon_256x256@2x.png"
			sips -z 512 512 "$ICON_SOURCE" --out "$TMP_ICONSET/icon_512x512.png"
			sips -z 1024 1024 "$ICON_SOURCE" --out "$TMP_ICONSET/icon_512x512@2x.png"

		else
			echo "ERROR: Neither 'magick'/'convert', 'icotool', nor 'sips' found. Cannot convert .ico to .icns."
			echo "Install ImageMagick (brew install imagemagick), icoutils (brew install icoutils), or ensure 'sips' is available."
			deactivate || true
			exit 1
		fi

		# Normalize iconset: some tools create files with '-0' suffixes; select best candidate per size
		for base in "icon_16x16.png" "icon_16x16@2x.png" "icon_32x32.png" "icon_32x32@2x.png" "icon_128x128.png" "icon_128x128@2x.png" "icon_256x256.png" "icon_256x256@2x.png" "icon_512x512.png" "icon_512x512@2x.png"; do
			if [ -f "$TMP_ICONSET/$base" ]; then
				continue
			fi
			prefix="${base%.png}"
			# find candidates like prefix-*.png or prefix*.png
			candidates=("$TMP_ICONSET/${prefix}"*.png)
			# if glob didn't match, candidates will be literal; check
			if [ -e "${candidates[0]}" ]; then
				# choose largest file as best candidate
				best=""
				bestsize=0
				for c in "${candidates[@]}"; do
					if [ ! -f "$c" ]; then
						continue
					fi
					sz=$(stat -f%z "$c" 2>/dev/null || stat -c%s "$c" 2>/dev/null || echo 0)
					if [ "$sz" -gt "$bestsize" ]; then
						bestsize=$sz
						best="$c"
					fi
				done
				if [ -n "$best" ]; then
					mv "$best" "$TMP_ICONSET/$base"
				fi
			fi
		done

		# Verify required iconset files exist before calling iconutil
		REQUIRED=(
			"icon_16x16.png"
			"icon_16x16@2x.png"
			"icon_32x32.png"
			"icon_32x32@2x.png"
			"icon_128x128.png"
			"icon_128x128@2x.png"
			"icon_256x256.png"
			"icon_256x256@2x.png"
			"icon_512x512.png"
			"icon_512x512@2x.png"
		)
		MISSING=()
		for f in "${REQUIRED[@]}"; do
			if [ ! -f "$TMP_ICONSET/$f" ]; then
				MISSING+=("$f")
			fi
		done
		if [ ${#MISSING[@]} -ne 0 ]; then
			echo "ERROR: iconset missing required files:" "${MISSING[*]}"
			echo "Contents of $TMP_ICONSET:"
			ls -la "$TMP_ICONSET" || true
			echo "Cannot create .icns. Ensure conversion tool produced all required sizes."
			deactivate || true
			exit 1
		fi

		# Build .icns
		if command -v iconutil >/dev/null 2>&1; then
			echo "Running iconutil to create $ICON_TARGET"
			iconutil -c icns "$TMP_ICONSET" -o "$ICON_TARGET"
			rm -rf "$TMP_ICONSET"
		else
			echo "ERROR: iconutil not found (macOS tool). Cannot create .icns"
			echo "Ensure you're running this on macOS where 'iconutil' is available."
			deactivate || true
			exit 1
		fi
	fi
else
	echo "No icon source found at $ICON_SOURCE; proceeding without custom icon."
fi

# Remove previous builds
rm -rf build dist

# Ensure app.icns exists (py2app expects it if set)
if [ -f "app.icns" ]; then
	echo "Using icon: app.icns"
else
	echo "Warning: app.icns not found; py2app will build without a custom icon."
fi

# Run py2app to build the .app (this will produce dist/*.app)
python setup_py2app.py py2app

APP_BUNDLE="dist/FileOrganizer.app"

if [ -d "$APP_BUNDLE" ]; then
	echo "Build finished: $APP_BUNDLE"
else
	echo "Build completed but $APP_BUNDLE not found. Check py2app output for errors."
fi

# Optional code signing: set SIGN_IDENTITY to a valid macOS Developer ID Application identity
# Example: export SIGN_IDENTITY="Developer ID Application: Example Co (TEAMID)"
if [ -n "${SIGN_IDENTITY:-}" ] && [ -d "$APP_BUNDLE" ]; then
	echo "Signing app with identity: $SIGN_IDENTITY"
	ENTITLEMENTS_FILE="entitlements.plist"
	cat > "$ENTITLEMENTS_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>com.apple.security.cs.disable-library-validation</key>
	<true/>
	<key>com.apple.security.cs.allow-jit</key>
	<true/>
</dict>
</plist>
EOF

	# Sign main executable
	codesign --timestamp --options runtime --sign "$SIGN_IDENTITY" --entitlements "$ENTITLEMENTS_FILE" "$APP_BUNDLE" || true

	# Sign nested frameworks and plugins
	find "$APP_BUNDLE" -type f \( -name "*.dylib" -o -name "*.so" -o -name "*.framework" \) -print0 | while IFS= read -r -d '' f; do
		echo "Signing $f"
		codesign --timestamp --options runtime --sign "$SIGN_IDENTITY" --entitlements "$ENTITLEMENTS_FILE" "$f" || true
	done

	echo "Codesign steps completed. You may need to notarize the app for distribution."
fi

# Optional notarization: set NOTARIZE_USERNAME, NOTARIZE_PASSWORD (app-specific password), and BUNDLE_ID
# If provided, the script will zip the app and submit it for notarization with altool.
if [ -n "${NOTARIZE_USERNAME:-}" ] && [ -n "${NOTARIZE_PASSWORD:-}" ] && [ -n "${BUNDLE_ID:-}" ] && [ -d "$APP_BUNDLE" ]; then
	echo "Preparing app for notarization (requires Xcode command-line tools and valid Apple ID credentials)..."
	ZIP_NAME="${APP_BUNDLE%.app}.zip"
	ditto -c -k --keepParent "$APP_BUNDLE" "$ZIP_NAME"

	echo "Submitting $ZIP_NAME for notarization..."
	xcrun altool --notarize-app -t osx -f "$ZIP_NAME" --primary-bundle-id "$BUNDLE_ID" -u "$NOTARIZE_USERNAME" -p "$NOTARIZE_PASSWORD"

	echo "After notarization completes, staple with: xcrun stapler staple $APP_BUNDLE"
fi

echo "Done. See dist/ for the built app." 

deactivate || true
