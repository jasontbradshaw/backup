backup
======

My simple system backup script. Uses the magic of `rsync`'s `--link-dest` to do
nice incremental backups.

Description
----

This script takes a single argument, a destination directory, and then runs an
incremental backup on the entire system using `rsync`. The destination directory
will contain many folders named `backup-{{DATE}}`, and a single symlink named
`current` that points to the latest backup.

When the backup is complete, the script then removes old backups on a rolling
basis.

It excludes several unimportant system directories, and all external file systems
_except_ `/home`.

It should be run as a user that has read privileges on the entire file system.

If another backup is currently running, it will refuse to run concurrently and
will instead print out information about the currently-running backup.

Usage
----

```bash
backup /mnt/backup/system-backup
```

Notes
----
This only does _correct_ incremental backups if the destination file system
supports all the same attributes as the source file system. For example, trying
to back up an `ext4` partition to an `NTFS` one will just do a full backup every
time, since permissions and groups and the like won't match correctly.
