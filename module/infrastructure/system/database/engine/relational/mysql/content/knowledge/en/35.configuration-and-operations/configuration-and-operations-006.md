# Data Directory, Socket, PID File, and Filesystem Permissions

MySQL Server requires a persistent storage area for data files, a local communication mechanism between clients and the server, and a way to identify the running process. Three common configuration areas are:

- **Data directory (`datadir`)**: where MySQL stores the data dictionary, schemas, tables, tablespaces, and many server state files.
- **Socket or named pipe**: local communication endpoint between clients and the server on supported operating systems.
- **PID file (`pid_file`)**: file recording the process ID of the mysqld process, often used by service managers or operational tools to track the process.

These paths must exist at server startup and be accessible by the OS account running MySQL with appropriate permissions. Even a valid SQL configuration can fail to start if a directory does not exist, filesystem permissions are wrong, SELinux/AppArmor blocks access, a volume is unmounted, or a runtime directory is wiped on reboot.

This lesson belongs to the DATABASE_MYSQL scope: identifying runtime paths, understanding each file's role, granting least-privilege permissions, configuring sockets/PIDs on Linux and Windows, moving a data directory safely, troubleshooting startup errors, and verifying filesystem security boundaries.

## 1. Map of MySQL Paths

A MySQL instance can use several different directories. Not every file lives inside the datadir.

| Component | Role | How to Check |
|---|---|---|
| basedir | Installation directory for binaries, libraries, and utilities | `@@basedir` |
| datadir | Data directory of the instance | `@@datadir` |
| socket | Unix-domain socket on Unix-like OSes | `@@socket` |
| pid_file | Process ID file | `@@pid_file` |
| tmpdir | Server temporary file directory | `@@tmpdir` |
| log_error | Error log | `@@log_error` |
| secure_file_priv | Restricted directory for certain server-side import/export operations | `@@secure_file_priv` |
| log_bin_basename | Prefix/path of binary logs if enabled | `@@log_bin_basename` |
| relay_log_basename | Prefix/path of relay logs if replication is used | `@@relay_log_basename` |

Check multiple paths at once:

~~~sql
SELECT
    @@basedir AS basedir,
    @@datadir AS datadir,
    @@socket AS socket_path,
    @@pid_file AS pid_file,
    @@tmpdir AS tmpdir,
    @@log_error AS error_log,
    @@secure_file_priv AS secure_file_priv;
~~~

Check individual variables:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
    'basedir',
    'datadir',
    'socket',
    'pid_file',
    'tmpdir',
    'log_error',
    'secure_file_priv'
);
~~~

Actual paths depend on installation method, OS, package, service manager, and instance configuration. Do not copy defaults from a Linux installation to Windows or containers without verification.

## 2. What Does the Data Directory Contain?

The datadir is the root data directory of a MySQL instance. With InnoDB, it typically contains or relates to:

- Database schemas and metadata.
- Tablespace files as configured.
- System tablespace if configured inside the datadir.
- Undo tablespaces if placed there.
- Redo log files in the redo log directory depending on version/configuration.
- Binary logs or relay logs if their paths are set inside the datadir.
- Error log if no other path is configured.
- Internal configuration/state files such as `auto.cnf`.
- System schema directories such as `mysql`, `performance_schema`, and `sys` depending on version and installation.

Do not assume all data resides in a single directory. Some tablespaces, logs, keyrings, plugins, temporary files, or import/export files may live at different paths.

### 2.1. The Datadir Is Not a Backup Directory

The datadir is where the live server operates and writes data. A backup is a recoverable copy created through a consistent procedure.

Never copy a running datadir using regular filesystem commands and treat it as a valid backup. For InnoDB, data pages, redo logs, undo state, and metadata must be consistent at a single point in time. Use appropriate backup tools:
- Logical backups such as `mysqldump` or MySQL Shell dump utilities.
- MySQL-aware physical backups such as MySQL Enterprise Backup or a verified compatible tool.
- Storage snapshots only when the workflow guarantees consistency, such as coordinating freeze/backup locks per tool and version.

Backups must be verified by test restores. Having a backup file alone does not prove the system can recover.

### 2.2. Never Edit Data Files While mysqld Is Running

Never use an editor to directly modify InnoDB files, the data dictionary, redo logs, or system tables. Never delete files currently used by the server to "free up space."

When structural changes are needed, use SQL DDL/DML and proper backup/restore or migration workflows. When moving the datadir, shut down the server cleanly before copying physical files.

## 3. Identifying datadir, basedir, and Effective Configuration

Do not guess locations from package names. Ask the server directly:

~~~sql
SELECT
    @@version AS mysql_version,
    @@version_comment AS distribution,
    @@basedir AS basedir,
    @@datadir AS datadir,
    @@server_uuid AS server_uuid;
~~~

Some variables are readable only at GLOBAL scope. In a client, you can run:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'basedir';
SHOW GLOBAL VARIABLES LIKE 'socket';
SHOW GLOBAL VARIABLES LIKE 'pid_file';
~~~

On the server host, you can inspect how mysqld receives options:

~~~bash
mysqld --print-defaults
~~~

This command prints options read from option files parsed by mysqld. To view the list of option file paths and default values, run:

~~~bash
mysqld --verbose --help
~~~

These are shell diagnostic commands; run them using the exact binary and environment of the instance. Output can be long. Do not run multiple different mysqld binaries arbitrarily, as they may read different configuration files.

### 3.1. Configuration Order

MySQL can receive configuration from:
- Option files such as `my.cnf` or `my.ini`.
- Included files or include directories.
- Service command-line arguments.
- Runtime-modifiable variables set via SET GLOBAL.
- Compiled-in binary defaults.

An option appearing in multiple places can be overridden according to read order and option-file rules. Verify effective configuration via runtime variables and the service command line rather than reading just one configuration file.

### 3.2. Determining Which Binary the Service Runs

On Linux:

~~~bash
systemctl status mysql
systemctl cat mysql
ps -ef | grep '[m]ysqld'
~~~

The unit name may be `mysql`, `mysqld`, or a package-specific name.

On Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Service |
  Where-Object { $_.Name -match 'mysql' } |
  Select-Object Name, State, StartName, PathName
~~~

`PathName` shows the binary and service arguments; `StartName` shows the service account. Do not modify the service command line without backing up the current configuration first.

## 4. Configuring datadir in an Option File

On Unix-like OSes, server settings usually reside in the `[mysqld]` section:

~~~ini
[mysqld]
basedir=/usr
datadir=/var/lib/mysql
socket=/run/mysqld/mysqld.sock
pid-file=/run/mysqld/mysqld.pid
user=mysql
~~~

On Windows, the configuration file is typically `my.ini` and paths use Windows syntax:

~~~ini
[mysqld]
basedir=C:/Program Files/MySQL/MySQL Server 8.4
datadir=C:/ProgramData/MySQL/MySQL Server 8.4/Data
port=3306
named_pipe=ON
socket=MYSQL
~~~

These examples illustrate structure only. Packages and installers may choose different paths, service names, and IPC mechanisms.

Notes:
- `basedir` points to the installation directory, not where databases are stored.
- `datadir` must be the data directory for that exact instance.
- Never point two concurrently running mysqld instances at the same datadir.
- Changing startup paths usually requires a server restart.
- Do not relocate a datadir merely by editing the option and restarting; prepare and move the data following the proper procedure.

## 5. Initializing a Data Directory

A new datadir must be initialized using the MySQL utility matching the version.

Example on Linux after installing the package and creating the directory with proper permissions:

~~~bash
mysqld --initialize --user=mysql --datadir=/var/lib/mysql
~~~

`--initialize` creates system tables and initializes InnoDB; MySQL generates a temporary root password in the error log in supported configurations. Read the error log per package instructions and change the password immediately after first login.

Another option:

~~~bash
mysqld --initialize-insecure --user=mysql --datadir=/var/lib/mysql
~~~

`--initialize-insecure` initializes root without an initial password. Use it only in controlled environments and set a strong password immediately afterward. Never leave an instance with a passwordless administrative account on a network or shared environment.

On Windows, you may need to run from the binary directory with appropriate privileges:

~~~powershell
mysqld --initialize --console --datadir="C:/ProgramData/MySQL/MySQL Server 8.4/Data"
~~~

Initialization commands are only for a new, empty datadir belonging to the right instance. Never run `--initialize` against a datadir that already contains data. If the server reports the datadir is already initialized, stop and verify the path; do not delete its contents to force re-initialization.

### 5.1. Initialization vs. Upgrading

`--initialize` is not a command to upgrade an old datadir. When upgrading versions:
- Read the upgrade guide for the target version.
- Take a restorable backup.
- Check compatibility and data dictionary changes.
- Use a MySQL-supported upgrade workflow.
- Do not initialize anew over an existing data directory.

Do not use an older binary version to open a datadir upgraded by a newer version unless the documentation supports downgrades.

## 6. Least-Privilege Filesystem Permissions for datadir

MySQL usually runs under a dedicated OS account, such as `mysql` on Linux. This account needs appropriate read/write access on data files and traverse permission on every parent directory.

A common Linux setup:

~~~bash
chown -R mysql:mysql /var/lib/mysql
chmod 750 /var/lib/mysql
~~~

This is only an example for a new datadir or after verifying the entire directory tree belongs to that instance. Never run `chown -R` blindly on a directory containing mount points, backup files, sockets, logs, or files belonging to another instance.

Permissions to review:
- Owner of the datadir and files.
- Read/write permissions on data and log files.
- Execute permission on directories for traversal.
- File creation/deletion permissions in writable directories.
- ACLs if the environment uses ACLs.
- SELinux/AppArmor policies.
- Mount options and quotas.

### 6.1. Avoid chmod 777

Never grant read/write access to all users just to get MySQL to start.

`chmod 777` can allow untrusted accounts to read or alter database files, create symlinks, delete data, or tamper with state files. Grant proper owner/group and least-privilege permissions per package rather than opening permissions system-wide.

### 6.2. Permissions on Parent Directories

Even if the datadir has the right permissions, mysqld still cannot access it if any parent directory lacks traverse permission for the service account.

Check the path:

~~~bash
namei -l /var/lib/mysql
ls -ld /var/lib/mysql
ls -l /var/lib/mysql
~~~

`namei -l` inspects permissions on each path component. On systems without `namei`, check each parent directory with `ls`/`stat`.

### 6.3. Do Not Run mysqld as root

On Unix-like OSes, MySQL is typically configured to drop privileges to a dedicated user. Never start the server as root to bypass a permission error. Doing so expands the blast radius of any bug or vulnerability.

If the service runs as user `mysql`, grant permissions to that exact user and inspect the service configuration.

## 7. SELinux and AppArmor

Unix permissions are not the only control layer. Linux distributions may use SELinux or AppArmor to restrict which paths mysqld can access.

### 7.1. AppArmor

Some Ubuntu/Debian packages use an AppArmor profile for mysqld. The profile may allow only the default datadir and certain log/socket paths.

If you move the datadir to `/srv/mysql/data`, mysqld may be blocked even when ownership and mode are correct.

Check status and logs:

~~~bash
sudo aa-status
sudo journalctl -k --since "10 minutes ago" | grep -i apparmor
~~~

Resolution:
1. Identify the active profile for mysqld.
2. Add rules for the exact datadir, log, socket, or tmpdir required.
3. Reload the profile per your distribution's procedure.
4. Restart/test the service.
5. Confirm no denials remain.

Never disable AppArmor system-wide to fix a single misconfigured path. Keep policy updates as narrow as possible.

### 7.2. SELinux

On systems with SELinux enabled, file contexts can matter just as much as Unix permissions.

Check:

~~~bash
getenforce
ls -Zd /var/lib/mysql
ausearch -m AVC -ts recent
~~~

If the datadir moves to a custom path, assign the appropriate MySQL data file context per the distribution's policy. Common workflow example:

~~~bash
semanage fcontext -a -t mysqld_db_t "/srv/mysql/data(/.*)?"
restorecon -Rv /srv/mysql/data
~~~

Type names and policies can vary by distribution. Verify package policies before applying. Never use `setenforce 0` or disable SELinux as a permanent solution.

## 8. What Is a Socket?

On Unix-like OSes, a Unix-domain socket is a local communication endpoint between clients and mysqld. It is neither a TCP port nor a database data file, even though the filesystem shows the socket as an entry.

Some packages use a path such as:

~~~text
/run/mysqld/mysqld.sock
~~~

Clients can connect via socket:

~~~bash
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock -u app_user -p
~~~

Loopback TCP connection:

~~~bash
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u app_user -p
~~~

On Unix, host `localhost` typically selects a Unix socket per client behavior; `127.0.0.1` usually forces TCP. To avoid ambiguity during diagnostics, specify `--protocol` explicitly.

### 8.1. Socket Path Must Match Between Server and Client

The server has the `socket` variable; clients can also read a `socket` option from `[client]` or `[mysql]` sections.

Example:

~~~ini
[mysqld]
socket=/run/mysqld/mysqld.sock

[client]
socket=/run/mysqld/mysqld.sock

[mysql]
socket=/run/mysqld/mysqld.sock
~~~

If the server creates the socket at one path while the client looks at another, the client reports a socket-not-found error even though mysqld is running.

Check on the server side:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'socket';
~~~

Check on the OS side:

~~~bash
ls -l /run/mysqld/
ss -xl | grep mysql
~~~

Socket names and inspection tools depend on the distribution.

### 8.2. Permissions on the Socket and Its Parent Directory

Clients need permission to access the socket file and traverse parent directories. The socket directory is usually created by the service manager at startup.

Do not place the socket in a world-writable directory unnecessarily. Never delete the socket file while the server is running. If a socket file remains after a crash, first verify that no mysqld instance is using it; handle stale files only per the system runbook.

## 9. Runtime Directories Such as /run/mysqld

On many Linux distributions, `/run` is a runtime filesystem recreated on reboot and typically resides on tmpfs. Therefore, `/run/mysqld` may not exist after a machine reboots if the service/package does not recreate it.

The service manager can create the runtime directory and assign owner/group on start. A systemd unit may use mechanisms like `RuntimeDirectory`; packages may use `tmpfiles.d` or startup scripts.

Check:

~~~bash
systemctl cat mysql
systemd-tmpfiles --cat-config | grep -i mysqld
ls -ld /run/mysqld
~~~

Do not create a runtime directory manually once and assume it will survive reboots. Use the runtime directory initialization mechanism of the service manager/package.

If managing a systemd override yourself:
- Override only the necessary properties.
- Keep the original unit intact.
- Verify user/group permissions.
- Run `daemon-reload` when modifying units.
- Test restarts and reboots in staging.

## 10. What Is a PID File?

The PID file records the process ID of mysqld. Example:

~~~text
/run/mysqld/mysqld.pid
~~~

Some service scripts and operational tools use the PID file to identify the process. Server variable:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'pid_file';
~~~

In the shell:

~~~bash
cat /run/mysqld/mysqld.pid
ps -p "$(cat /run/mysqld/mysqld.pid)" -o pid,comm,args
~~~

A PID file is not the sole proof that the server is running. PIDs can be reused after a process terminates; verify command line, executable, and service state.

### 10.1. Stale PID Files

After a crash or unclean shutdown, an old PID file may remain. When mysqld restarts, it may refuse to start because the PID file exists, or a service script may mistakenly think the instance is already running.

Handling procedure:
1. Check service state.
2. Check all mysqld processes on the host.
3. Verify whether the PID inside the file still corresponds to the matching mysqld instance.
4. Check the datadir and socket of that exact instance.
5. Only when certain the file is stale and no server is running, handle it per runbook.
6. Read the error log and investigate why the previous stop was abnormal.

Never delete a PID file merely because the service fails to start. If mysqld is actually running, deleting the file can cause the service manager to lose track of the process.

## 11. Sockets/PIDs and Multiple MySQL Instances

A single machine can run multiple MySQL instances, provided each instance has dedicated resources and paths.

| Resource | Instance A | Instance B |
|---|---|---|
| datadir | `/srv/mysql/a/data` | `/srv/mysql/b/data` |
| socket | `/run/mysqld/a.sock` | `/run/mysqld/b.sock` |
| pid_file | `/run/mysqld/a.pid` | `/run/mysqld/b.pid` |
| port | 3306 | 3307 |
| error log | `/var/log/mysql/a.err` | `/var/log/mysql/b.err` |

Do not share:
- Datadir.
- Socket path.
- PID file path.
- TCP port.
- Error log path when operational separation is needed.
- Binary log/relay log basenames when configuration requires separation.

Configuration example:

~~~ini
[mysqld]
port=3307
datadir=/srv/mysql/b/data
socket=/run/mysqld/b.sock
pid-file=/run/mysqld/b.pid
log-error=/var/log/mysql/b.err
server-id=102
~~~

Each instance must have dedicated filesystem permissions and a clear service unit/command line. Never start two mysqld processes on the same datadir; InnoDB is not designed for two independent servers to open the same datadir concurrently.

## 12. Connections on Windows: Named Pipes and TCP

Windows does not use Unix-domain sockets the way Linux does. MySQL on Windows can use TCP/IP and, if enabled/supported, named pipes or shared memory.

Example named pipe configuration:

~~~ini
[mysqld]
named_pipe=ON
socket=MYSQL
~~~

Clients can select the pipe protocol if supported by the client/version:

~~~powershell
mysql --protocol=PIPE --socket=MYSQL -u app_user -p
~~~

TCP:

~~~powershell
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u app_user -p
~~~

Do not confuse the `socket` value on Windows with a Unix socket file path. Depending on version and configuration, it may represent the named pipe name.

### 12.1. Service Account Permissions and NTFS ACLs

The MySQL Windows service runs under an account, such as Network Service, Local System, or a dedicated account. That account needs appropriate permissions on:
- Datadir.
- Log directory.
- Temporary directory.
- Runtime directories and related files.
- Keyring or plugin directories if configured.

Check the service account:

~~~powershell
Get-CimInstance Win32_Service |
  Where-Object { $_.Name -match 'mysql' } |
  Select-Object Name, StartName, PathName
~~~

Check ACLs:

~~~powershell
icacls "C:\ProgramData\MySQL\MySQL Server 8.4\Data"
~~~

Grant permissions to the actual service account, never `Everyone Full Control`. When changing the service account, audit all paths mysqld needs to access.

## 13. Filesystem Permissions vs. SQL Privileges

MySQL has two separate permission layers:

- **SQL privilege**: controls whether an account can SELECT, INSERT, UPDATE, DELETE, EXECUTE, FILE, etc., on databases/objects.
- **Filesystem permission**: controls whether the mysqld process can read, write, create, or delete files on the operating system.

A user having SELECT privilege in MySQL does not mean they can read InnoDB files directly on the filesystem. Conversely, someone with OS read permissions on the datadir can access sensitive data outside SQL authorization.

SQL privilege example:

~~~sql
GRANT SELECT ON app_db.* TO 'report_user'@'%';
~~~

This statement does not grant filesystem permissions to `report_user`, nor does it change the owner of the datadir.

### 13.1. FILE Privilege and secure_file_priv

Certain server-side file read/write statements such as `LOAD DATA INFILE` and `SELECT ... INTO OUTFILE` require the `FILE` privilege and are further constrained by `secure_file_priv`, filesystem permissions, and OS policies.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'secure_file_priv';
SHOW GRANTS FOR CURRENT_USER();
~~~

If `secure_file_priv` points to a directory, server-side file operations are restricted accordingly. If its value is NULL, those file operations are disabled under this variable's rules; if empty, no directory restriction is imposed by this variable, though `FILE` privilege and OS permissions still apply. Check documentation for your exact version.

`LOAD DATA LOCAL INFILE` differs from server-side INFILE: data is read from the client side and sent to the server, introducing additional client/server `LOCAL` configuration factors. Do not infer permissions of one type from the other.

## 14. Moving the datadir Safely

Moving a datadir is a high-risk operational task because it involves all data in the instance. Never simply edit `datadir` in `my.cnf` and restart.

### 14.1. Preparation

Before moving:
1. Identify the exact instance and current datadir via `@@datadir`.
2. Record `basedir`, `socket`, `pid_file`, `tmpdir`, error log, binary log, relay log, and any related tablespace paths.
3. Check target filesystem capacity, inodes, mount options, and quotas.
4. Verify the target filesystem is suitable for MySQL/InnoDB and provides required durability.
5. Take a restorable backup and test recovery.
6. Schedule a maintenance window and notify applications.
7. Prepare owner/group/ACL permissions.
8. Update AppArmor/SELinux policies if needed.
9. Prepare new configuration and a rollback plan to the old path.

### 14.2. Clean Server Shutdown

Stop via the service manager:

~~~bash
sudo systemctl stop mysql
systemctl status mysql
~~~

Confirm no mysqld process for the instance is still running. Do not rely solely on the service command exit status; check processes and shutdown logs.

Never copy a live datadir with ordinary `cp` or `rsync` and treat it as a consistent physical backup. If you cannot stop the server, use a backup/clone/snapshot tool designed for MySQL.

### 14.3. Copying and Preserving Metadata

Illustrative example on Linux after the server has stopped cleanly:

~~~bash
sudo rsync -aHAX --numeric-ids /var/lib/mysql/ /srv/mysql/data/
~~~

Important metadata-preservation options may depend on the filesystem and administrative privileges. Verify the result:
- Owner/group.
- Mode.
- ACLs.
- Extended attributes.
- Symlinks.
- Total size and file count.
- Actual mount point.

Do not delete the old datadir immediately. Keep the old copy unused by mysqld until the new instance starts and is verified.

### 14.4. Updating Configuration and Policies

Edit the exact `[mysqld]` section:

~~~ini
[mysqld]
datadir=/srv/mysql/data
socket=/run/mysqld/mysqld.sock
pid-file=/run/mysqld/mysqld.pid
~~~

At the same time:
- Update AppArmor/SELinux.
- Update the service unit if it contains hardcoded paths.
- Verify the socket/PID runtime directory is still created.
- Check separate tablespace/log paths.
- Avoid unexpectedly changing the client socket path.

### 14.5. Starting Up and Verifying

~~~bash
sudo systemctl start mysql
systemctl status mysql
journalctl -u mysql -n 100 --no-pager
~~~

After connecting:

~~~sql
SELECT
    @@datadir,
    @@socket,
    @@pid_file,
    @@log_error,
    @@server_uuid;

SHOW ENGINE INNODB STATUS;
~~~

Verify:
- The server opened the new datadir.
- Important schemas and tables exist.
- Sample data and row counts match.
- Replication/binlog works if configured.
- Applications connect to the right socket/port.
- New backups run successfully.
- Error log has no permission or tablespace errors.

Only after verification and taking a fresh backup should you schedule removal of the old datadir per retention policy. Never delete it right after the first startup.

## 15. Filesystems, Mounts, and Data Durability

The datadir should reside on a durable filesystem supported for MySQL workloads. Evaluate:
- I/O latency and throughput.
- `fsync` semantics and write durability.
- Capacity and inodes.
- Quotas.
- Mount options.
- RAID/storage controller cache policies.
- Snapshot/backup integration.
- Behavior when the filesystem fills up or loses its mount.

Never place the datadir on temporary directories or runtime filesystems like `tmpfs`. Do not assume network filesystems/NFS/SMB behave identically to local block storage; verify official support and locking/`fsync` semantics before deploying.

If the datadir volume is unmounted when the service starts, mysqld might create or see an empty directory at the mountpoint on the root filesystem. This is dangerous because the server could mistakenly initialize or start on an empty directory. The service should declare proper mount dependencies, and startup should verify the volume is mounted.

### 15.1. Checking Mounts on Linux

~~~bash
findmnt /srv/mysql/data
df -h /srv/mysql/data
df -i /srv/mysql/data
mount | grep '/srv/mysql'
~~~

Inspect mount options and underlying block devices. In systemd, appropriate dependencies such as `RequiresMountsFor` can be used for custom services; check existing units and packages before adding overrides.

### 15.2. Full Filesystem

If the datadir or log filesystem fills up:
- INSERT/UPDATE statements may fail.
- InnoDB may be unable to write redo/undo or data pages.
- Binary logs may stop writing.
- The server may halt or enter an error state.
- Replication may break.

Never delete InnoDB files or binary logs with `rm` to free space. Use proper SQL/rotation/purge procedures:
- Identify which files consume space.
- Check backup and replication consumers.
- Purge binary logs with the appropriate MySQL statement.
- Expand the volume or relocate logs as planned.
- Safely recover temporary space.
- Verify InnoDB and replication after recovery.

## 16. Related Paths Distinct from datadir

Several path variables to consider when designing filesystem layouts:

| Variable/Group | Meaning |
|---|---|
| `innodb_data_home_dir` | Base location for system tablespace paths if configured |
| `innodb_data_file_path` | Defines system tablespace data files |
| `innodb_undo_directory` | Directory for undo tablespaces in configurations that use it |
| `innodb_redo_log_capacity` | Managed redo log capacity; not a path |
| `tmpdir` | Server temporary file directory |
| `log_error` | Error log |
| `log_bin_basename` | Binary log path |
| `relay_log_basename` | Relay log path |
| `secure_file_priv` | Directory restricting server-side file operations |
| `keyring_file_data` | Keyring file path if using the corresponding plugin/component |

Do not alter these variables merely because you are moving the datadir. Some variables are deprecated or vary by version. Confirm the variable exists on your server and check documentation for your exact version.

## 17. Containers and Volume Permissions

In containers, the datadir is typically mounted from a persistent volume. Restarting a container must not lose data; the volume must persist independently of the container lifecycle.

Common issues:
- UID/GID inside the image does not match volume ownership on the host.
- Volume mounted read-only.
- Incompatible SELinux labels.
- Host directory permissions prevent mysqld writes.
- Container starts even though the volume is not mounted.
- Two containers mount the same datadir simultaneously.

Procedure:
1. Identify the UID/GID of the mysqld user in the actual image.
2. Check ownership and mode on the volume.
3. Check mount mode and SELinux labeling.
4. Change owner/ACL only for the target volume and instance.
5. Ensure a datadir is opened by only one mysqld instance.
6. Use persistent volumes and independent backups.
7. Test container restarts/recreation and restores.

Never run `chmod -R 777` on a volume. Never share one datadir across multiple mysqld containers as a way to scale read replicas; use replication/clone or proper MySQL deployment mechanisms.

## 18. Diagnosing Path-Related Startup Failures

When mysqld fails to start, check in order:

1. What error did the service manager report?
2. Which binary and option files are in use?
3. Does the datadir exist and belong to the right instance?
4. Is the filesystem containing the datadir mounted?
5. Are owner/mode/ACLs correct?
6. Does the service account have traverse permissions on all parent directories?
7. Are there SELinux/AppArmor denials?
8. Do the socket/PID directories exist and allow writes?
9. Is a PID file stale or is an old process still running?
10. Is disk space or are inodes exhausted?
11. Does the error log report InnoDB, redo log, tablespace, or version compatibility errors?

On Linux:

~~~bash
systemctl status mysql
journalctl -u mysql -n 200 --no-pager
tail -n 100 /var/log/mysql/error.log
namei -l /var/lib/mysql
df -h
df -i
~~~

Error log and unit names depend on the package. Prefer the path reported by the server via `log_error` or service configuration.

On Windows:

~~~powershell
Get-Service *mysql*
Get-WinEvent -LogName Application -MaxEvents 100
icacls "C:\ProgramData\MySQL\MySQL Server 8.4\Data"
~~~

Check the specific service `PathName`, account, and error log. Do not alter ACLs or delete PID/socket/data files before identifying the root cause.

## 19. Socket and PID Error Runbook

### 19.1. Client Reports "Can't connect through socket"

Check:
- Whether mysqld is running.
- What the server socket path is.
- What the client socket path is.
- Whether the socket directory exists.
- Whether the service account can create the socket.
- Whether AppArmor/SELinux blocks it.
- Whether the client is using TCP instead of socket or vice versa.

Example:

~~~bash
mysqladmin --protocol=SOCKET \
  --socket=/run/mysqld/mysqld.sock ping
~~~

If you need to test TCP:

~~~bash
mysqladmin --protocol=TCP \
  -h 127.0.0.1 -P 3306 ping
~~~

Do not edit socket paths before verifying which endpoint the server is actually listening on.

### 19.2. Server Reports "PID file already exists"

Check processes:

~~~bash
ps -ef | grep '[m]ysqld'
cat /run/mysqld/mysqld.pid
~~~

If the process is still running, identify the instance and service unit. If no process exists and the PID file is genuinely stale, handle it per runbook after verifying the corresponding datadir/socket. Read the error log to find why the previous stop was abnormal.

### 19.3. Server Cannot Create PID/Socket

Common causes:
- `/run/mysqld` does not exist after reboot.
- Wrong owner/group.
- Service account was changed.
- Read-only filesystem.
- AppArmor/SELinux policy blocking creation.
- Mismatched paths in option files.

Fix the root cause in the service/runtime directory and policies. Do not place PID/socket files inside the datadir merely to avoid configuring the runtime directory if doing so makes configuration harder to manage.

## 20. Filesystem-Level Data Security

The datadir typically contains business data and security metadata. Protect it as a sensitive asset:

- Grant access only to the service account and administrative groups.
- Never place the datadir inside a web root or shared user directories.
- Protect backups and snapshots at an equal or higher security level.
- Use encryption at rest when required by security policy.
- Manage keyrings/key material separately with recoverable backups.
- Never leak passwords, keys, or production data into uncontrolled logs/diagnostics.
- Audit filesystem permissions.
- Use a dedicated OS account for mysqld.
- Never run the server as root.
- Do not grant broad `FILE` privileges unnecessarily.

Encryption at rest does not replace filesystem permissions. Anyone with access to both data files and keys can still read the data; protect data files, backups, and key management together.

## 21. Production Path Deployment Checklist

- [ ] Identified the exact instance, binary, and service account.
- [ ] Recorded `basedir`, `datadir`, `socket`, `pid_file`, and `tmpdir` from runtime.
- [ ] Distinguished the datadir from backup directories.
- [ ] Identified any log/tablespace/keyring paths outside the datadir.
- [ ] Placed the datadir on a durable filesystem with sufficient space and inodes.
- [ ] Ensured the volume is mounted before mysqld starts.
- [ ] Verified no two mysqld instances share one datadir.
- [ ] Granted owner/group/ACLs on a least-privilege basis.
- [ ] Verified all parent directories have traverse permissions.
- [ ] Configured SELinux/AppArmor policies to allow exact required paths.
- [ ] Ensured runtime directories for sockets/PIDs are recreated after reboot.
- [ ] Verified client socket path matches server socket path.
- [ ] Ensured the PID file is managed by the exact service instance.
- [ ] Avoided `chmod 777` and running mysqld as root.
- [ ] Controlled `FILE` privilege and `secure_file_priv`.
- [ ] Restricted initialization commands strictly to new, empty datadirs.
- [ ] Prepared restore-tested backups and a maintenance plan for datadir migrations.
- [ ] Performed physical copies only after clean shutdown or with proper backup tools.
- [ ] Verified startup, error log, SQL queries, and applications after migration.
- [ ] Tested restarts/reboots and volume permissions if running in containers.
- [ ] Maintained runbooks for socket errors, stale PIDs, full disks, and permission denials.

## 22. Hands-On Exercises

### Exercise 1: Exploring Runtime Paths

Connect to MySQL and query `basedir`, `datadir`, `socket`, `pid_file`, `tmpdir`, `log_error`, and `secure_file_priv`. Cross-check with the OS service configuration.

### Exercise 2: Distinguishing datadir and Backup

Create a logical backup in a separate directory. Compare the backup structure with the datadir. Test restoring into an independent lab instance and verify the data.

### Exercise 3: Checking Filesystem Permissions

On a Linux lab, inspect owner/mode of the datadir and every parent directory with `namei`. Test starting the service with insufficient permissions in a test environment, read the error log, and restore least-privilege permissions.

### Exercise 4: Socket vs. TCP

Connect using a Unix socket and then loopback TCP. Observe the endpoints, use `mysqladmin ping`, and explain why `localhost` can select a socket while `127.0.0.1` uses TCP.

### Exercise 5: Runtime Directory

Check `/run/mysqld` after a reboot. Identify which mechanism the package/systemd uses to create the directory. Do not rely on manual `mkdir`; test restarting the service and verify the socket/PID are recreated.

### Exercise 6: Stale PID File

In a lab VM, observe the PID file while the server is running and after a clean shutdown. Never kill a production process. Simulate a stale PID on a disposable instance and verify processes before handling it.

### Exercise 7: Windows Service Account

On a Windows lab, check `StartName` and `PathName` of the MySQL service. Use `icacls` to view datadir ACLs. Propose least-privilege permissions for the service account.

### Exercise 8: Moving the datadir

Create a lab instance with sample data. Take a backup and restore-test it. Stop the server cleanly, copy the datadir to another volume, update the option file and security policies, start it back up, and verify data and endpoints.

### Exercise 9: AppArmor/SELinux

In a lab VM with active policies, move the datadir to a custom path. Observe permission denials despite correct Unix modes. Update the policy narrowly and verify the service starts.

### Exercise 10: Multi-Instance

Create two disposable instances with separate datadirs, sockets, PIDs, ports, and error logs. Verify clients connect to the right instance and no data directory is shared.

### Exercise 11: Disk and Inodes

Observe `df -h` and `df -i` on a lab filesystem. Safely simulate low space, read logs, and draft a recovery procedure. Never delete data files to free space.

### Exercise 12: Runbook

Write short runbooks for three scenarios: missing socket, pre-existing PID file, and `mysqld` permission denied. Each scenario must include inspection commands, evidence to gather, and preconditions before making fixes.

## 23. Conclusion

The data directory, socket, PID file, and filesystem permissions are distinct components that must work together for stable MySQL operation. The datadir holds instance data; the socket or named pipe provides the local communication endpoint; the PID file helps the service manager identify the process. These paths must align with effective configuration, the service account, parent directory permissions, runtime directories, and OS security policies.

When initializing, use only a new, empty datadir. When migrating, take and restore-test a backup, shut down the server cleanly, copy while preserving metadata, update policies/configuration, and verify thoroughly before retiring the old copy. Never copy live data files with ordinary filesystem tools, never delete PID/socket files without verifying running processes, never use `chmod 777`, and never run mysqld as root.

Finally, always distinguish SQL privileges from filesystem permissions, the datadir from backups, sockets from TCP ports, and PID files from actual process state. Record runtime values, test across restarts/reboots, and maintain runbooks for path, permission, mount, and capacity failures.

## Official References

- [MySQL 8.4 Reference Manual – Data Directory](https://dev.mysql.com/doc/refman/8.4/en/data-directory.html)
- [MySQL 8.4 Reference Manual – Server Configuration Defaults](https://dev.mysql.com/doc/refman/8.4/en/server-configuration-defaults.html)
- [MySQL 8.4 Reference Manual – Option Files](https://dev.mysql.com/doc/refman/8.4/en/option-files.html)
- [MySQL 8.4 Reference Manual – Server System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual – mysqld: The MySQL Server](https://dev.mysql.com/doc/refman/8.4/en/mysqld.html)
- [MySQL 8.4 Reference Manual – Initializing the Data Directory](https://dev.mysql.com/doc/refman/8.4/en/data-directory-initialization.html)
- [MySQL 8.4 Reference Manual – Connecting to the MySQL Server Using Unix Sockets](https://dev.mysql.com/doc/refman/8.4/en/connecting.html)
- [MySQL 8.4 Reference Manual – Connecting to the MySQL Server Using Named Pipes](https://dev.mysql.com/doc/refman/8.4/en/windows-and-named-pipes.html)
- [MySQL 8.4 Reference Manual – Secure File Privileges](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_secure_file_priv)
- [MySQL 8.4 Reference Manual – mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual – InnoDB Backup and Recovery](https://dev.mysql.com/doc/refman/8.4/en/innodb-backup.html)
