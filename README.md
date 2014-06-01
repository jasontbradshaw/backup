backup
======

My simple system backup script.

Descrption
----

This script takes a single argument, a destination directory, and then runs a
diffing, versioned backup on the entire system using `rdiff-backup`. When it's
done running the backup, it then removes old backups on a rolling basis.

It excludes several unimportant system directories, and all external filesystems
_except_ `/home`.

It should be run as a user that has read privledges on the entire filesystem.

If another backup is currently running, it will refuse to run concurrently and
will instead print out information about the currently-running backup.

Usage
----

```bash
backup /mnt/backup/system-backup
```

Notes
----
`rdiff-backup` isn't friendly to being killed! You should avoid killing the
process while its running, otherwise on the next backup it _will_ regress all
currently backed-up files to ensure their integrity. This can take a _long_
time, so don't do it! This includes powering the system off while its backing
up!
