#!/usr/bin/env python3

import argparse
import atexit
import json
import logging
import os
import re
import shutil
import signal
import sys
import time

from sh import rsync
from sh import uptime

# initialize logging
logging.basicConfig(
  name='rsync',
  format='%(message)s',

  # TODO: bump this down by default
  level=logging.INFO,
)

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

  parser = argparse.ArgumentParser('backup', description='''
      Make an incremental system backup to a directory. The destination
      directory is filled with a sequence of folders that maintains an
      incremental history of all backups made.
  ''')

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
  If the directory was locked before system boot, the directory is re-locked for
  this run, since the prior process couldn't still be running after a shutdown!

  Returns a function that removes the lock directory when called.
  '''

  # attempt to make a lock directory
  lock_dir = os.path.join(dest, name)
  info_path = os.path.join(lock_dir, 'info')

  # see if a lock already exists by trying to read the file for it
  try:
    logging.debug('Looking for existing lock directory...')

    data = None
    with open(info_path, 'r') as info_file:
      data = json.load(info_file)

    # figure out when the system booted and when the directory was locked
    boot_time = time.mktime(
        time.strptime(uptime(since=True).strip(), '%Y-%m-%d %H:%M:%S'))
    lock_time = time.mktime(time.strptime(data['start_time'], TIME_FORMAT))

    # remove the lock directory if it was created before the system booted,
    # since that process couldn't possibly still be running.
    if boot_time > lock_time:
      logging.info('Removing old lock directory (locked on %s, booted on %s)...',
          time.strftime(TIME_FORMAT, time.localtime(lock_time)),
          time.strftime(TIME_FORMAT, time.localtime(boot_time)))

      shutil.rmtree(lock_dir)
    else:
      logging.debug('Lock file exists and is still valid (locked on %s)',
          time.strftime(TIME_FORMAT, time.localtime(lock_time)))

  except FileNotFoundError:
    # do nothing since there was presumably no existing lock directory
    logging.debug('No old lock directory found')
    pass

  try:
    os.mkdir(lock_dir)

    # write some useful info to our file, so others can see our status while
    # we're running and so this program can determine if the lock has "expired",
    # i.e. the system rebooted while the directory was still locked.
    with open(info_path, 'w') as info_file:
      json.dump({
        'pid': os.getpid(),
        'start_time': time.strftime(TIME_FORMAT),
      }, info_file, indent='  ', sort_keys=True)
  except FileExistsError as e:
    raise IOError("Could not acquire lock in '" + dest + "'")

  # return a function that will remove the lock directory when called
  # TODO: there's probably a race condition in here somewhere... fix it!
  return lambda: (
    os.path.exists(info_path) and
    os.path.exists(lock_dir) and
    shutil.rmtree(lock_dir)
  )

def parse_backup_time(path):
  '''
  Parse the timestamp from a backup directory path. Returns the parsed Unix
  timestamp or None if none could be parsed.
  '''

  try:
    return time.mktime(time.strptime(path[-TIME_FORMAT_LENGTH:], TIME_FORMAT))
  except ValueError:
    # fail if we couldn't parse a timestamp
    return None

def remove_old_backups(dest, timestamp):
  '''
  Remove backup folders from `dest` that are older than `timestamp`, a Unix
  timestamp.
  '''

  logging.info("Removing backups older than %s...",
      time.strftime(TIME_FORMAT, time.localtime(timestamp)))

  # keep track of how many we've removed for logging purposes
  removed = 0
  for path in os.listdir(dest):
    # normalize the path
    path = os.path.abspath(os.path.normpath(os.path.join(dest, path)))
    fname = os.path.basename(path)

    logging.debug("  Checking '%s'", path)

    # only consider backup directories
    if os.path.isdir(path) and fname.startswith(BACKUP_PREFIX):
      logging.debug("  '%s' was a dir and started with '%s'",
          fname, BACKUP_PREFIX)

      backup_timestamp = parse_backup_time(path)
      logging.debug("  Parsed timestamp %d", backup_timestamp)

      # remove the backup folder if we got a timestamp and it's too old
      if backup_timestamp is None:
        logging.error("  Failed to parse backup timestamp from '%s'", fname)
      elif backup_timestamp - timestamp <= 0:
        logging.info("  Removing '%s'", fname)
        shutil.rmtree(path)
        removed += 1
      else:
        logging.debug("  Skipping '%s'", fname)

      logging.debug('')

  logging.info('Removed %d old backup%s.', removed, '' if removed == 1 else 's')

def prune_incomplete_backups(dest):
  '''
  Removes incomplete backup folders from the given directory if a complete
  backup exists that is newer than they are.
  '''

  newest_timestamp = None
  files = [os.path.abspath(os.path.join(dest, p)) for p in os.listdir(dest)]

  logging.info('Pruning incomplete backups...')

  logging.debug('  Finding newest backup directory...')
  for path in files:
    fname = os.path.basename(path)

    logging.debug("    Checking '%s'", path)

    # find the newest backup directory
    if os.path.isdir(path) and fname.startswith(BACKUP_PREFIX):
      fname = os.path.basename(path)

      logging.debug("    '%s' was a dir and started with '%s'",
          fname, BACKUP_PREFIX)

      backup_timestamp = parse_backup_time(path)
      if newest_timestamp is None:
        logging.debug("    Setting initial newest directory to '%s'", fname)
        newest_timestamp = backup_timestamp
      elif backup_timestamp is None:
        logging.error("    Failed to parse backup timestamp from '%s'", fname)
      elif backup_timestamp > newest_timestamp:
        logging.debug("    Found newer backup directory '%s'", fname)
        newest_timestamp = backup_timestamp
    else:
      logging.debug("    Skipping '%s'", fname)

    logging.debug("")

  logging.info("  Newest backup directory time is %s",
      time.strftime(TIME_FORMAT, time.localtime(newest_timestamp)))

  logging.debug("")

  # if we found the newest backup, remove older incomplete backups
  incomplete = 0
  pruned = 0
  if newest_timestamp is not None:
    logging.info("  Searching fo old incomplete backups...")

    for path in files:
      fname = os.path.basename(path)

      logging.debug("    Checking '%s'", path)

      if os.path.isdir(path) and fname.startswith(INCOMPLETE_PREFIX):
        # track that we found an incomplete backup
        incomplete += 1

        logging.debug("    '%s' was a dir and started with '%s'",
            fname, INCOMPLETE_PREFIX)

        # remove the incomplete folder if it's older than the newest backup
        incomplete_timestamp = parse_backup_time(path)
        logging.debug("    Parsed timestamp %d", incomplete_timestamp)

        if incomplete_timestamp is None:
          logging.error("    Failed to parse backup timestamp from '%s'", fname)
        elif incomplete_timestamp - newest_timestamp < 0:
          logging.info("    Removing '%s'", fname)
          pruned += 1
          shutil.rmtree(path)
      else:
        logging.debug("    Skipping '%s'", fname)

      logging.debug('')
  else:
    # this shouldn't happen, as we should have at least the current backup
    logging.error('  No backup directories found!')

  logging.info('  Found %d incomplete backup%s',
      incomplete, '' if incomplete == 1 else 's')

  logging.info('Pruned %d incomplete backup%s',
      pruned, '' if pruned == 1 else 's')

def main():
  config = get_config()
  dest = config.destination
  src = config.source

  # ensure the destination directory exists
  os.makedirs(dest, exist_ok=True)

  # lock it so only we can use it
  unlock_dest = None
  try:
    unlock_dest = lock_dest(dest)
  except IOError as e:
    logging.info('Backup already in progress, exiting.')
    return 0

  # remove the lock when exiting under normal circumstances
  atexit.register(unlock_dest)

  # make sure we remove the lock on exit, now that we've acquired it. we catch
  # these signals explicitly since it virtually guarantees that we'll remove the
  # lock on exit, unless something catastrophic happens. we have to wrap the
  # function since handler functions must take two arguments, otherwise they
  # error.
  unlock_dest_handler = lambda a, b: unlock_dest()
  signal.signal(signal.SIGABRT, unlock_dest_handler)
  signal.signal(signal.SIGINT, unlock_dest_handler)
  signal.signal(signal.SIGSEGV, unlock_dest_handler)
  signal.signal(signal.SIGTERM, unlock_dest_handler)

  # get a timestamp for the backup directory
  backup_timestamp = time.strftime(TIME_FORMAT)

  # get names for our backup directories
  incomplete_backup_dir = os.path.join(dest,
      INCOMPLETE_PREFIX + BACKUP_PREFIX + backup_timestamp)
  complete_backup_dir = os.path.join(dest, BACKUP_PREFIX + backup_timestamp)
  current_link = os.path.join(dest, CURRENT_LINK_NAME)

  logging.info("Backing up '%s' to '%s'...", src, dest)

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

    # prettify output a bit
    itemize_changes=True,
    human_readable=True,

    # look through all subdirectories of the given one
    recursive=True,

    # include all file types and duplicate all permissions
    links=True,
    perms=True,
    times=True,
    group=True,
    owner=True,
    devices=True,
    specials=True,
    executability=True,

    # log all rsync output through our logger
    _out=logging.info,
    _err=logging.error,
  )

  # bail if the backup didn't succeed
  if rsync_result.exit_code != 0:
    logging.error('rsync process exited with code %d, backup failed!',
        rsync_result.exit_code)
    return rsync_result.exit_code
  else:
    logging.info('Backup was successful')

  # mark the backup as 'complete'
  logging.info('Marking the backup as complete...')
  os.rename(incomplete_backup_dir, complete_backup_dir)

  # remove any existing symlink and create a new one
  logging.info('Updating link to point at the current backup...')
  current_link_path = os.path.join(dest, CURRENT_LINK_NAME)
  if os.path.lexists(current_link_path):
    logging.debug("Removing existing link at '%s'", current_link_path)
    os.unlink(current_link_path)

  # makes sure the link is relative, so we can move the backup folder without
  # breaking the link.
  os.symlink(os.path.basename(complete_backup_dir), current_link_path)

  # remove old backup folders
  keep_duration_seconds = 60 * 60 * 24 * config.days_to_keep
  remove_old_backups(dest, time.time() - keep_duration_seconds)

  # prune incomplete backup folders once a newer backup exists
  prune_incomplete_backups(dest)

  return 0

if __name__ == '__main__':
  # exit with whatever code main returns, defaulting to success
  sys.exit(main())
