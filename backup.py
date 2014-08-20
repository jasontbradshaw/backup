#!/usr/bin/env python3

import argparse
import atexit
import json
import os
import re
import shutil
import time

from sh import rsync

# the format of backup directory timestamps. the time format is assumed to
# always output a string of the same length!
TIME_FORMAT = '%Y-%m-%dT%H:%M:%S'
TIME_FORMAT_LENGTH = len(time.strftime(TIME_FORMAT))

CURRENT_LINK_NAME = 'current'
BACKUP_PREFIX = 'backup-'
INCOMPLETE_PREFIX = 'incomplete-'

# NOTE: this script doesn't work as intended when backing up a Linux FS to an
# NTFS drive, thanks to permissions being incompatible. rsync detects all files
# as changed, then does a full sync every time!

def get_config():
  '''Parse and return the current command-line arguments.'''

  parser = argparse.ArgumentParser('backup',
      description='''Make an incremental system backup to a directory. The
      destination directory is filled with a sequence of folders that maintains
      an incremental history of all backups made.''')

  # standardize a path to an absolute, normalized path
  norm = lambda path: os.path.abspath(os.path.normpath(path))

  parser.add_argument('source', metavar='SOURCE', type=norm, default='/',
      help='The source directory to back up.')
  parser.add_argument('destination', metavar='DEST', type=norm,
      help='The destination directory to create the backup history in.')
  parser.add_argument('-k', '--days-to-keep', type=int, default=365,
      help='The number of days to keep old backups.')

  return parser.parse_args()

def lock_dest(dest, name='backup.lock'):
  '''
  Create a lock directory in the destination directory. Raises an IOError if the
  lock could not be acquired, i.e. the destination directory is already locked.

  Returns a function that removes the lock directory when called.
  '''

  # attempt to make a lock directory
  lock_dir = os.path.join(dest, name)
  info_path = os.path.join(lock_dir, 'info')
  try:
    os.mkdir(lock_dir)

    # write some useful info to our file, so others can see our status
    with open(info_path, 'w') as info_file:
      json.dump({
        'pid': os.getpid(),
        'start_time': int(time.time()),
      }, info_file, indent='  ', sort_keys=True)
  except FileExistsError as e:
    raise IOError("Could not acquire lock in '" + dest + "'")

  # return a function that will remove the lock directory when called
  return lambda: shutil.rmtree(lock_dir)

def parse_backup_time(path):
  '''
  Parse the timestamp from a backup directory path. Returns the parsed Unix
  timestamp or None if none could be parsed.
  '''

  try:
    return time.strptime(path[-TIME_FORMAT_LENGTH:], TIME_FORMAT)
  except ValueError:
    # fail if we couldn't parse a timestamp
    return None

def remove_old_backups(dest, timestamp):
  '''
  Remove backup folders from `dest` that are older than `timestamp`, a Unix
  timestamp.
  '''

  for path in os.listdir(dest):
    # normalize the path
    path = os.path.abspath(os.path.normpath(path))
    fname = os.path.basename(path)

    # only consider backup directories
    if os.path.isdir(path) and fname.startswith(BACKUP_PREFIX):
      backup_timestamp = parse_backup_time(path)

      # remove the backup folder if we got a timestamp and it's too old
      if backup_timestamp is not None and backup_timestamp - timestamp >= 0:
        shutil.rmtree(path)

def prune_incomplete_backups(dest):
  '''
  Removes incomplete backup folders from the given directory if a complete
  backup exists that is newer than they are.
  '''

  newest_backup = None
  files = [os.path.abspath(os.path.normpath(p)) for p in os.listdir(dest)]

  for path in files:
    fname = os.path.basename(path)

    # find the newest backup directory
    if os.path.isdir(path) and fname.startswith(BACKUP_PREFIX):
      backup_timestamp = parse_backup_time(path)

      if newest_backup is None:
        newest_backup = backup_timestamp
      elif backup_timestamp is not None and backup_timestamp > newest_backup:
        newest_backup = backup_timestamp

  # if we found the newest backup, remove older incomplete backups
  if newest_backup is not None:
    for path in files:
      fname = os.path.basename(path)

      if os.path.isdir(path) and fname.startswith(INCOMPLETE_PREFIX):
        incomplete_timestamp = parse_backup_time(path)

        # remove the incomplete folder if it's older than the newest backup
        if (incomplete_timestamp is not None and
            incomplete_timestamp - newest_backup >= 0):
          shutil.rmtree(path)

def main():
  config = get_config()
  dest = config.destination
  src = config.source

  # ensure the destination directory exists
  os.makedirs(dest, exist_ok=True)

  # lock it so only we can use it
  unlock_dest = lock_dest(dest)

  # make sure we remove the lock on exit, now that we've acquired it
  atexit.register(unlock_dest)

  # get a timestamp for the backup directory
  backup_timestamp = time.strftime(TIME_FORMAT)

  # get names for our backup directories
  incomplete_backup_dir = os.path.join(dest,
      INCOMPLETE_PREFIX + BACKUP_PREFIX + backup_timestamp)
  complete_backup_dir = os.path.join(dest, BACKUP_PREFIX + backup_timestamp)
  current_link = os.path.join(dest, CURRENT_LINK_NAME)

  # start the backup
  rsync_result = rsync(
    '--exclude', '/home/*/.cache',
    '--exclude', '/home/*/.thumbnails',
    '--exclude', '/tmp/*',
    '--exclude', '/var/tmp/*',
    '--exclude', '/var/log/journal/*',
    '--exclude', '/dev/*',
    '--exclude', '/proc/*',
    '--exclude', '/sys/*',
    '--exclude', '/mnt/*',
    '--exclude', dest,

    '--include', '/home',

    # backup from the source to our 'incomplete' directory
    src, incomplete_backup_dir,

    # this does the incremental magic
    link_dest=current_link,

    # makes rsync archive all changes
    itemize_changes=True,
    human_readable=True,
    recursive=True,
    links=True,
    perms=True,
    times=True,
    group=True,
    owner=True,
    devices=True,
    specials=True,
    executability=True,
  )

  # bail if the backup didn't succeed
  if rsync_result.exit_code != 0:
    return rsync_result.exit_code

  # mark the backup as 'complete'
  os.rename(incomplete_backup_dir, complete_backup_dir)

  # remove any existing symlink and create a new one
  if os.path.lexists(CURRENT_LINK_NAME):
    os.path.unlink(CURRENT_LINK_NAME)
  os.symlink(complete_backup_dir, CURRENT_LINK_NAME)

  # remove old backup folders
  keep_duration_seconds = 60 * 60 * 24 * config.days_to_keep
  remove_old_backups(dest, time.time() - keep_duration_seconds)

  # prune incomplete backup folders once a newer backup exists
  prune_incomplete_backups(dest)

  return 0

if __name__ == '__main__':
  import sys

  # exit with whatever code main returns, defaulting to success
  sys.exit(main() or 0)
