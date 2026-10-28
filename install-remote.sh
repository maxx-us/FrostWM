#!/usr/bin/env bash
# FrostWM remote installer.
# Downloads the current main-branch source archive and invokes its user-local installer.
set -Eeuo pipefail

readonly REPO="maxx-us/FrostWM"
readonly BRANCH="main"
readonly ARCHIVE_URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

say() { printf '\n[FrostWM] %s\n' "$*"; }
die() { printf '\n[FrostWM] ERROR: %s\n' "$*" >&2; exit 1; }

for cmd in tar mktemp; do
  command -v "$cmd" >/dev/null 2>&1 || die "Required command '$cmd' was not found."
done

if command -v curl >/dev/null 2>&1; then
  downloader="curl"
elif command -v wget >/dev/null 2>&1; then
  downloader="wget"
else
  die "Install curl or wget, then run this installer again."
fi

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/frostwm-install.XXXXXXXX")"
cleanup() { rm -rf -- "$tmpdir"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

say "Downloading FrostWM from https://github.com/${REPO} ..."
if [[ "$downloader" == "curl" ]]; then
  curl --fail --location --silent --show-error "$ARCHIVE_URL" -o "$tmpdir/frostwm.tar.gz" ||
    die "Download failed. Check your connection and that the ${BRANCH} branch exists."
else
  wget --https-only -q "$ARCHIVE_URL" -O "$tmpdir/frostwm.tar.gz" ||
    die "Download failed. Check your connection and that the ${BRANCH} branch exists."
fi

tar -xzf "$tmpdir/frostwm.tar.gz" -C "$tmpdir" ||
  die "Could not extract the downloaded source archive."

project_dir="$tmpdir/FrostWM-${BRANCH}"
[[ -d "$project_dir" ]] || die "Expected source directory was not found in the archive."
for required in install.sh frostwm.py config.example.json bin/frostwm systemd/frostwm.service waybar/frostwm gnome-extension/extension.js gnome-extension/metadata.json; do
  [[ -f "$project_dir/$required" ]] || die "Repository is missing required file: $required"
done

say "Running the project installer..."
say "No sudo commands are run by this remote installer."
(
  cd "$project_dir"
  bash ./install.sh
)

say "Installation finished."
say "Start FrostWM with: frostwm start"
say "Optional login autostart: frostwm enable"
