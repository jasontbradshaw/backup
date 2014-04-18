#!/usr/bin/env bash
RDIFF=rdiff-backup

# first two arguments are source and destintation
SOURCE=${1}
DEST=${2}

# configuration options
VERBOSITY=5
KEEP_FOR=3M

echo "Backing up '${SOURCE}' to '${DEST}'..."
${RDIFF} \
  --exclude '/tmp/*' \
  --exclude '/proc/*' \
  --exclude '/sys/*' \
  --exclude '/mnt/*/*' \
  --exclude-special-files \
  --exclude-other-filesystems \
  --verbosity "${VERBOSITY}" \
  "${SOURCE}" "${DEST}"

echo "Purging old backups in '${DEST}'..."
${RDIFF} \
  --remove-older-than "${KEEP_FOR}" \
  --force \
  --verbosity "${VERBOSITY}" \
  "${DEST}"
