backup
======

My simple backup script. Uses the magic of `rsync`'s `--link-dest` to do nice
incremental backups.

Description
----

This script takes a two arguments: a source directory, and a destination
directory. It then runs an incremental backup of the source using `rsync`. The
destination directory will contain many folders named `backup-{{DATE}}`, and a
single symlink named `current` that points to the latest backup.

When the backup is complete, the script then removes old backups on a rolling
basis, defaulting to 365 days.

It excludes several unimportant system directories, and all external file
systems _except_ `/home`, by default. This allows its simple use as a system
backup script without further configuration.

If another backup is happening to the same destination, it will refuse to run
concurrently and will exit.

Usage
----

```bash
backup / /mnt/backup-drive/system-backups
```

Notes
----
This only does _correct_ incremental backups if the destination file system
supports all the same attributes as the source file system. For example, trying
to back up an `ext4` partition to an `NTFS` one will just do a full backup every
time, since permissions and groups and the like won't match correctly.
