#!/usr/bin/env bash
RDIFF=rdiff-backup

# always backup the root system
SOURCE='/'

# only argument is the destination
DEST=${1}

# configuration options
VERBOSITY=5
KEEP_FOR=3M

echo "Backing up '${SOURCE}' to '${DEST}'..."
echo

${RDIFF} \
  --exclude '/home/*/.cache' \
  --include '/home' \
  --exclude '/tmp/*' \
  --exclude '/var/tmp/*' \
  --exclude '/proc/*' \
  --exclude '/sys/*' \
  --exclude '/mnt/*/*' \
  --exclude-special-files \
  --exclude-other-filesystems \
  --verbosity "${VERBOSITY}" \
  "${SOURCE}" "${DEST}"

echo
echo "Purging old backups in '${DEST}'..."
echo

${RDIFF} \
  --remove-older-than "${KEEP_FOR}" \
  --force \
  --verbosity "${VERBOSITY}" \
  "${DEST}"
