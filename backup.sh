#!/usr/bin/env bash
RDIFF=rdiff-backup

# our only argument is the destination
DEST="${1}"

# configuration options
SOURCE='/'
VERBOSITY=5
KEEP_FOR=3M

# the file used to notify that a system backup is happening
lockdir="/tmp/backup.lock"

# information files for the current backup process
pid_file="${lockdir}/pid"
start_date_file="${lockdir}/start-date"

# exit if we can't grab our lock
if ! mkdir "${lockdir}" &> /dev/null; then
  echo "Backup already in progress:"
  echo "  Started: $(cat ${start_date_file})"
  echo "      PID: $(cat ${pid_file})"
  echo "Exiting."
  exit 1
fi

# store useful info about this backup in the the lock directory
echo "$BASHPID" > "${pid_file}"
echo "$(date)" > "${start_date_file}"

# always remove the lock directory we're about to create on exit, no matter
# what. however, make sure we only do this once we know we have the lock!
trap "rm -rf ${lockdir}" INT QUIT TERM EXIT

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

echo
echo 'Backup complete!'
