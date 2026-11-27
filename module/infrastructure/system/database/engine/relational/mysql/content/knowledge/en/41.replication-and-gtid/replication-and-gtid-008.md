# Consistent snapshots, Clone plugin, and replica initialization

A new replica must start from a dataset consistent with the source. If the initial copy is missing transactions, contains data from different points in time, or has a mismatched GTID history, replication may fail or silently produce divergent data. Therefore, a crucial step before running a replica is taking a proper snapshot, restoring the snapshot, and configuring the replication starting point.

MySQL offers two common approaches to supply initial data: creating a logical dump using `mysqldump` or copying data physically using the Clone plugin. A logical dump is flexible, portable, and lets you inspect SQL contents; the Clone plugin is usually faster for large InnoDB datasets because it copies physical data. Once the data is in place, the replica must configure replication using GTID auto-position or binary log file/position.

This lesson uses the modern replication syntax from MySQL 8.0.23 onward and MySQL 8.4. Legacy command names such as `CHANGE MASTER TO`, `START SLAVE`, and `SHOW SLAVE STATUS` have been replaced with `SOURCE`/`REPLICA` syntax in newer releases. The `mysqldump --source-data` option was introduced in MySQL 8.0.26; on older versions, use `--master-data` instead. When operating another version, cross-check the documentation for your exact version.

## Objectives

After this lesson, you will be able to:

- Explain consistent snapshots and the limitations of `--single-transaction`.
- Create a logical dump with appropriate binlog/GTID metadata to initialize a replica.
- Install the Clone plugin, grant donor/recipient privileges, and run a remote clone.
- Choose GTID auto-position or file/position when connecting a replica to a source.
- Verify a replica after initialization and troubleshoot common errors.
- Avoid mistakes that lose GTID history, lack binary logs, or produce inconsistent data.

## 1. Why does a replica need a consistent snapshot?

Replication transfers changes from source to replica. The replica must have a starting point representing the data state at a well-defined point in time. Suppose the source has tables `customers`, `orders`, and `order_items`. If a backup reads `customers` before a transaction but reads `orders` after that transaction, the restored data will not reflect a single consistent logical state.

A consistent snapshot ensures that reads during backup observe the same data image via the storage engine's snapshot mechanism. For InnoDB, consistent read inside a `REPEATABLE READ` transaction allows `mysqldump --single-transaction` to read data from the same snapshot throughout the dump.

The data snapshot must be paired with metadata identifying where to resume replication:

- For file/position replication: the binary log file name and byte position on the source at the moment of the snapshot.
- For GTID replication: the GTID set executed and reflected in the snapshot.

If you only have an SQL file or a copy of the data directory without metadata on the starting point, determining which transaction to apply first becomes error-prone and can lead to skipped or re-applied transactions.

## 2. Creating a logical snapshot with mysqldump

### 2.1. Consistent snapshot with InnoDB

Example creating a full-database dump on a MySQL 8.0.26+ source:

```bash
mysqldump \
  --all-databases \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --source-data=2 \
  --set-gtid-purged=ON \
  --user=backup_user \
  --password \
  > seed.sql
```

Meaning of the options:

| Option | Effect |
|---|---|
| `--all-databases` | Dumps all databases the account has permission to read. |
| `--single-transaction` | Creates a consistent snapshot for transactional tables such as InnoDB. |
| `--quick` | Reads and writes rows incrementally to reduce memory usage. |
| `--routines` | Includes stored procedures and functions. |
| `--events` | Includes Event Scheduler events. |
| `--triggers` | Includes triggers; typically enabled by default, but explicit specification improves readability. |
| `--source-data=2` | Writes the source's binary log file/position as a commented statement in the dump. |
| `--set-gtid-purged=ON` | Writes the source's GTID set into the dump so GTID history can be established on the target machine. |

`--source-data` was renamed from `--master-data` in newer MySQL releases. The value `2` writes the `CHANGE REPLICATION SOURCE TO` statement containing file/position as a comment for the operator to inspect and choose. When combining `--source-data` with `--single-transaction`, `mysqldump` needs a brief global read lock at the start of the process to capture log coordinates synchronized with the snapshot; subsequent data reads proceed on the consistent snapshot.

The dump account needs sufficient privileges on the exported objects. `--source-data` requires binary logging enabled, `REPLICATION CLIENT` to read binary log status, and `RELOAD`; when `gtid_mode=ON` and the dump uses `--set-gtid-purged=ON|AUTO` together with `--single-transaction`, the server also requires `RELOAD` or `FLUSH_TABLES`. Grant only the required privileges to the backup account instead of using a full-privilege administrative account.

`--set-gtid-purged=ON` is appropriate when building a replica in a GTID topology and the target server is prepared to receive the GTID set from the source. If not using GTID, omit this option and use file/position. On a target machine that already has GTID history, do not blindly apply a dump containing `GTID_PURGED`: the GTID set may conflict or overlap with the existing state.

With GTID enabled, the dump also includes `SET @@SESSION.sql_log_bin=0` so data-loading statements do not generate new GTIDs on the target server; instead, the target records the original GTIDs from the source via `GTID_PURGED`. The restore account needs appropriate privileges to disable binary logging at the session scope. This ensures the replica's GTID history accurately reflects the transactions already present in the snapshot.

### 2.2. Limitations of --single-transaction

`--single-transaction` creates a consistent snapshot for InnoDB. It does not guarantee a consistent snapshot for tables using non-transactional storage engines such as MyISAM or MEMORY. If the database contains such tables, use an appropriate backup method, such as locking writes for the necessary duration or using a physical backup solution supporting those storage engines.

While the dump is running, avoid DDL operations on dumped tables such as `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE`. DDL can cause the dump to fail or prevent the result from reflecting a consistent snapshot. Furthermore, `--single-transaction` does not by itself block applications from altering schemas.

A full-database dump may contain sensitive data, user accounts, and system configuration details. Store the file in a location with restricted access, encrypt at rest, and check disk space before starting.

### 2.3. Restoring the dump onto a new replica

Before loading the dump, prepare a clean MySQL instance or a target server whose GTID state has been verified. For GTID, enable the required configuration before setting up replication:

```ini
[mysqld]
server_id=102
log_bin=replica-bin
gtid_mode=ON
enforce_gtid_consistency=ON
```

`server_id` must be unique within the topology. Both source and replica must have `gtid_mode=ON` and `enforce_gtid_consistency=ON` enabled to use GTID auto-position. If the replica will serve as a source for downstream replicas, also enable `log_replica_updates=ON` to record transactions received from upstream into the local binary log.

Restore the dump:

```bash
mysql --user=restore_user --password < seed.sql
```

When the dump contains `SET @@GLOBAL.GTID_PURGED`, the target server must meet the conditions required to assign that GTID set. The safest and most predictable approach is to use a new instance with GTID enabled and no conflicting transaction history. If loading a dump into a server that already has data or GTID history, inspect `@@GLOBAL.gtid_executed` and `@@GLOBAL.gtid_purged` before deciding how to reconcile; never wipe GTID history just to make the import command succeed.

## 3. Clone plugin: physical copying from a donor

The Clone plugin physically copies data from a MySQL donor to a recipient. This approach is well suited when you need to quickly supply initial data to a replica with a large InnoDB dataset. Unlike a logical dump, cloning transfers data and metadata at the server/storage engine level; it does not produce an SQL file for statement-by-statement editing.

The Clone plugin was introduced in MySQL 8.0.17. The plugin must be installed on both the donor and recipient. Example on Linux:

```sql
INSTALL PLUGIN clone SONAME 'mysql_clone.so';
```

On Windows, the plugin library name may be `mysql_clone.dll`. If the plugin is already configured to load at startup, there is no need to install it again. Check status:

```sql
SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'clone';
```

Remote cloning requires the donor and recipient to belong to the same MySQL server series and run on the same operating system/platform. For example, you cannot clone directly between MySQL 8.0 and 8.4, though you can clone between releases within the same 8.4 series. Check version, architecture, InnoDB configuration, and storage capacity requirements in the documentation for your exact version before executing.

### 3.1. Privileges on donor and recipient

The account used by the recipient to connect to the donor requires `BACKUP_ADMIN` on the donor. The user executing `CLONE INSTANCE` on the recipient requires `CLONE_ADMIN`.

On the donor, create an account allowing connections only from the recipient:

```sql
CREATE USER 'clone_user'@'replica.example.internal'
IDENTIFIED BY 'replace_with_secret';

GRANT BACKUP_ADMIN ON *.*
TO 'clone_user'@'replica.example.internal';
```

On the recipient, grant clone execution privileges to an appropriate administrative account:

```sql
GRANT CLONE_ADMIN ON *.*
TO 'replica_admin'@'localhost';
```

Replace the host with the actual address the donor sees from the recipient. Do not use `%` if you can restrict to a specific host. Protect passwords and prefer TLS when transferring data over the network.

### 3.2. Allowing the donor and running the clone

On the recipient, add the donor to the allowed list:

```sql
SET GLOBAL clone_valid_donor_list = 'donor.example.internal:3306';
```

Then run remote clone on the recipient:

```sql
CLONE INSTANCE FROM
  'clone_user'@'donor.example.internal':3306
IDENTIFIED BY 'replace_with_secret'
REQUIRE SSL;
```

`clone_valid_donor_list` is the list of hosts and ports the recipient accepts as donors for remote cloning. The donor must be in this list. Use `REQUIRE SSL` when connecting to the donor over a network with TLS properly configured.

Cloning replaces the recipient's data with data from the donor, and the recipient restarts when the operation finishes. With a default remote clone, existing user data and binary logs on the recipient are removed before donor data is copied. Therefore, only run this on an instance dedicated to becoming a new replica; existing data on the recipient will be overwritten. Ensure adequate disk space, a stable network connection, `max_allowed_packet` of at least 2 MB on both servers, and sufficient donor resources to serve the copy. The Clone plugin only copies InnoDB data; MyISAM and CSV tables are created as empty tables on the recipient, while data in other storage engines must be handled separately. The plugin also does not copy server configuration files or binary/relay log files; the recipient retains its own configuration.

In a replication workflow, the donor must be a source or replica belonging to the topology the recipient will join. The Clone plugin extracts and transfers both the binary log file/position and the `gtid_executed` set from the donor to the recipient to establish the continuation point. Binary log and relay log files themselves are not copied. By default, replication metadata tables are copied along with the data; thus, the donor's channels may appear on the recipient. Inspect channels before starting replication to decide whether to resume an existing channel or reconfigure.

### 3.3. Monitoring the clone

You can monitor status and progress via Performance Schema:

```sql
SELECT * FROM performance_schema.clone_status\G

SELECT * FROM performance_schema.clone_progress;
```

`clone_status` reports the status of the most recent clone operation, while `clone_progress` shows progress per stage. When a clone fails, inspect the error code and error message here along with the server error log. Do not immediately retry without diagnosing the cause, as the operation may have already altered the recipient's data state.

After cloning, you can check the coordinates transferred from the donor:

```sql
SELECT BINLOG_FILE, BINLOG_POSITION
FROM performance_schema.clone_status;

SELECT @@GLOBAL.gtid_executed;
```

If using file/position, use those exact `BINLOG_FILE` and `BINLOG_POSITION` values to configure the new channel. If using GTID auto-position, inspect `gtid_executed` and ensure GTID mode matches on both sides. The source must retain the binary logs needed for the replica to catch up from the clone point until replication connects; if the logs have already been purged, re-provision from a fresh snapshot or archived log source.

## 4. Choosing logical dump vs. Clone plugin

| Criterion | Logical dump (`mysqldump`) | Clone plugin |
|---|---|---|
| Copy method | Reads data and exports SQL statements | Physically copies InnoDB data |
| Flexibility | Can filter databases/tables, inspect or edit dump | Clones instance within plugin-supported scope |
| Speed on large datasets | Usually slower due to SQL export and reload | Usually faster due to physical copy |
| Storage engines | Can dump data from multiple engines supported by mysqldump | Clone plugin focuses on InnoDB; other engines require separate handling |
| Replication metadata | Can record file/position and GTID in the dump | Must verify GTID history and metadata after clone |
| Version/platform | Easier to migrate across SQL-compatible environments | Stricter version and platform compatibility requirements |
| Best suited for | Flexible migrations, small/medium databases, selective data | Fast provisioning of replicas with large InnoDB datasets |

No single choice is optimal for every system. Base your decision on data size, storage engines, downtime requirements, version compatibility, security policies, and snapshot verification needs.

## 5. Configuring replication with GTID auto-position

GTID (Global Transaction Identifier) assigns a unique identifier to every committed transaction written to the binary log on the source. When a replica uses `SOURCE_AUTO_POSITION=1`, it sends its executed GTID set to the source; the source sends only the transactions the replica is missing. Consequently, you do not need to manually pick file/position once the replica has accurate GTID history.

### 5.1. Preparing the source

On the source, verify binary logging and GTID are enabled. Create a replication account:

```sql
CREATE USER 'repl'@'replica.example.internal'
IDENTIFIED BY 'replace_with_secret';

GRANT REPLICATION SLAVE ON *.*
TO 'repl'@'replica.example.internal';
```

The `REPLICATION SLAVE` privilege name is still used in MySQL 8.0/8.4 for accounts reading binary logs for replication, even though management commands have transitioned to `SOURCE` and `REPLICA` terminology. Restrict the account's host, use a dedicated password, and enable TLS for the replication connection per security requirements.

### 5.2. Connecting the replica to the source

Once initial data is loaded and GTID history is accurate, configure the default channel on the replica:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl',
  SOURCE_PASSWORD = 'replace_with_secret',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

In production environments, consider configuring SSL for the channel and storing credentials through your system's secret management process. If the replica has an old channel configuration, stop it and check status before making changes. `RESET REPLICA ALL` removes channel connection metadata and relay logs; use it only when intentionally removing old configuration. This command is not a way to clear GTID execution history.

### 5.3. GTID history determines which transactions are sent

When `SOURCE_AUTO_POSITION=1`, the source compares its own GTID set against the `gtid_executed` reported by the replica. GTIDs already executed on the replica will not be resent. Therefore, the snapshot must accurately reflect both the data and the matching GTID set at the exact same point in time.

If the target server has out-of-band GTIDs (errant transactions), or `GTID_PURGED` was set incorrectly, auto-position may skip required transactions, throw errors, or create an incompatible state. Never run `RESET MASTER` or commands that delete binary log/GTID history arbitrarily as a fix. Before modifying GTID sets, determine which transactions have been applied and reconcile against actual data.

## 6. Configuring replication with file/position

If the topology does not use GTID, or needs to resume from coordinates recorded in a dump, you can configure replication using binary log file and position:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl',
  SOURCE_PASSWORD = 'replace_with_secret',
  SOURCE_LOG_FILE = 'binlog.000123',
  SOURCE_LOG_POS = 456789;

START REPLICA;
```

`SOURCE_LOG_FILE` and `SOURCE_LOG_POS` must be the coordinates recorded at the exact moment the snapshot was taken. Do not take the source's current position after the dump completes, because the source may have generated additional transactions during the dump. With `mysqldump --source-data=2`, the coordinates are written in the comment section of the dump file; read and use those exact values.

File/position is straightforward to understand but requires precise coordinate management during recovery or source switches. If the source purges the log file containing the position the replica needs to read, the replica will not be able to catch up from that coordinate; you must take a fresh snapshot or recover from another archived log source.

## 7. Finalizing and verifying the replica

After `START REPLICA`, check status:

```sql
SHOW REPLICA STATUS\G
```

Fields to inspect:

| Field | How to interpret |
|---|---|
| `Source_Host` | Source the replica is connected to. |
| `Replica_IO_Running` | Binary log receiver thread from the source; typically must be `Yes`. |
| `Replica_SQL_Running` | Relay log applier thread; typically must be `Yes`. |
| `Auto_Position` | `1` when the channel uses GTID auto-position. |
| `Retrieved_Gtid_Set` | GTIDs received from the source. |
| `Executed_Gtid_Set` | GTIDs executed on the replica. |
| `Last_IO_Error` / `Last_SQL_Error` | Most recent error on the receiver or applier thread. |
| `Seconds_Behind_Source` | Estimated lag; `NULL` may appear when the SQL thread is not running or information is unavailable. |

Both I/O and SQL threads running does not mean the data has fully caught up. Check errors, GTID sets, lag, worker count, and business data. `Seconds_Behind_Source=0` at a single point in time is also not standalone proof that the replica is always in sync.

You can also inspect worker status in Performance Schema:

```sql
SELECT *
FROM performance_schema.replication_applier_status_by_worker;

SELECT *
FROM performance_schema.replication_connection_status;
```

Compare a few read-only queries between the source and replica, such as row counts over a time range or per-table checksums. Choose checks that do not impose excessive load and account for replication lag during comparison.

After verifying, set the replica to read-only to reduce the risk of accidental direct writes:

```sql
SET PERSIST read_only = ON;
SET PERSIST super_read_only = ON;
```

`super_read_only` blocks writes even from accounts holding `SUPER` (or equivalent privileges in your specific version), while the replication applier can still apply transactions from the source. Enable it only when the instance's role is a read replica; administrative or failover tooling may require a clear procedure for toggling this mode.

## 8. Common errors when initializing a replica

| Symptom | Possible cause | Remediation |
|---|---|---|
| Replica reports missing binary log | Source already purged required logs | Create a fresh snapshot or fetch logs from archive; review retention. |
| `SOURCE_AUTO_POSITION=1` raises GTID error | GTID mode not enabled, conflicting GTID sets, or missing required transactions | Check `gtid_mode`, `enforce_gtid_consistency`, `gtid_executed`, and `gtid_purged` on both sides. |
| Replica fails to connect to source | Wrong host, port, password, privileges, or TLS | Check replication account, host match, firewall, and certificates. |
| Dump fails while running | DDL altered tables during snapshot or insufficient backup privileges | Check error log, control DDL during dump window, and review privileges. |
| Source and replica data differ | Inconsistent snapshot, omitted tables/engines, or direct writes on replica | Check snapshot timing, storage engines, GTID history, and application logs. |
| Clone plugin will not run | Plugin not installed, donor not allowlisted, or missing privileges | Check `INFORMATION_SCHEMA.PLUGINS`, `clone_valid_donor_list`, `CLONE_ADMIN`, and `BACKUP_ADMIN`. |
| Clone fails due to environment | Incompatible version/platform or insufficient disk space | Check clone prerequisites, disk space, network, and `performance_schema.clone_status`. |
| Replica SQL thread stops | Failing transaction, schema mismatch, or locally modified data | Read `Last_SQL_Error`, inspect worker status, and fix root cause before restarting. |

Do not skip a failing transaction by advancing GTIDs or bumping file/position just to keep the replica running. First determine whether the transaction can be safely skipped, what data will be lost, and how to resynchronize if divergence has occurred.

## 9. Hands-on workflow: creating a new replica

Suppose you have source `db-source` and target server `db-replica`. Choose one of the two initial data provisioning methods, then follow the shared replication setup workflow.

### Option A: logical dump

1. Verify `log_bin`, GTID mode, and binary log retention on the source.
2. Stop or control DDL during the dump window; verify tables to be copied use InnoDB if choosing `--single-transaction`.
3. Run `mysqldump` with `--single-transaction`, `--source-data=2`, and `--set-gtid-purged=ON` if the topology uses GTID.
4. Prepare the new replica instance with a unique `server_id` and matching GTID configuration.
5. Restore the dump, verify `gtid_executed` and binlog metadata in the dump file.
6. Configure `CHANGE REPLICATION SOURCE TO` using `SOURCE_AUTO_POSITION=1` or file/position coordinates.
7. Run `START REPLICA`, verify both threads, and reconcile data.

### Option B: Clone plugin

1. Confirm the donor holds consistent InnoDB data and GTID history matching the intended source.
2. Install the Clone plugin on both donor and recipient; create a donor user with `BACKUP_ADMIN` and a recipient user with `CLONE_ADMIN`.
3. Add the donor to `clone_valid_donor_list` on the recipient and verify TLS.
4. Run `CLONE INSTANCE` on the recipient; monitor `clone_status` and `clone_progress`.
5. Wait for the recipient to restart; check `server_id`, `server_uuid`, plugins, data, and GTID history.
6. Inspect channels copied from the donor; a GTID auto-position channel may continue if the donor is a replica in the same topology and settings remain valid. If a different channel is needed, stop and reconfigure intentionally.
7. If creating a new channel, use `@@GLOBAL.gtid_executed` for GTID auto-position or `BINLOG_FILE`/`BINLOG_POSITION` from `performance_schema.clone_status` for file/position.
8. Run `START REPLICA` and verify the receiver thread, applier thread, and business data.

In both options, the source must retain binary logs long enough for the new replica to catch up. If snapshot creation, data transfer, and initialization take longer than log retention, the source may purge transactions the replica needs to receive. Factor the provisioning window into your `binlog_expire_logs_seconds` policy and binary log archiving.

## 10. Safe operational principles

1. **Lock down the snapshot point and replication coordinates together.** Data and GTID/file-position metadata must describe the exact same source state.
2. **Know storage engine limits.** `--single-transaction` suits InnoDB; the Clone plugin copies InnoDB data. Handle tables on other engines separately.
3. **Control DDL during dumps.** A snapshot transaction does not protect the dump from every schema modification.
4. **Retain binary logs long enough.** Retention must cover snapshot creation, transfer, restoration, and replica catch-up.
5. **Do not mix GTID histories.** Avoid loading dumps onto servers with their own transactions or wiping GTID sets arbitrarily to clear errors.
6. **Use dedicated accounts and least privilege.** Separate backup/clone privileges from application accounts and restrict connection hosts.
7. **Verify version and platform.** Especially critical when using the Clone plugin.
8. **Verify after startup.** Check I/O, SQL, GTIDs, worker errors, and business data.
9. **Restrict writes on replicas.** Use `read_only` and `super_read_only` when appropriate for the server's role.

## 11. Self-check exercises

1. Why does `mysqldump --single-transaction` not guarantee a consistent snapshot for MyISAM tables?
2. What two different types of metadata do `--source-data=2` and `--set-gtid-purged=ON` provide?
3. In the Clone plugin, which machine's account holds `BACKUP_ADMIN` and which machine's account holds `CLONE_ADMIN`?
4. Why must you check `gtid_executed` on the replica before enabling `SOURCE_AUTO_POSITION=1`?
5. If `Replica_IO_Running=Yes` but `Replica_SQL_Running=No`, which fields should you inspect first?
6. Why should you not use `RESET REPLICA ALL` to clear GTID history?

**Answer hints:** (1) MyISAM does not support transactional consistent snapshots; write locking or another backup method is required. (2) `--source-data=2` records binary log file/position; `--set-gtid-purged=ON` records the executed GTID set. (3) The donor grants `BACKUP_ADMIN` to the account the recipient uses to connect; the recipient grants `CLONE_ADMIN` to the user executing the clone command. (4) The GTID set determines which transactions the source will send; an incorrect GTID set can skip transactions or cause errors. (5) `Last_SQL_Error` and status in `replication_applier_status_by_worker`. (6) `RESET REPLICA ALL` removes channel/relay log metadata, not executed GTID history.

## References

- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual: Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [MySQL 8.4 Reference Manual: Clone Plugin](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin.html)
- [MySQL 8.4 Reference Manual: Remote Cloning](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin-remote.html)
- [MySQL 8.4 Reference Manual: Cloning for Replication](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin-replication.html)
- [MySQL 8.4 Reference Manual: Clone Plugin Limitations](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin-limitations.html)
- [MySQL 8.4 Reference Manual: Setting Up Replication with Existing Data](https://dev.mysql.com/doc/refman/8.4/en/replication-setup-replicas.html)
- [MySQL 8.4 Reference Manual: Replication with Global Transaction Identifiers](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids.html)
- [MySQL 8.4 Reference Manual: CHANGE REPLICATION SOURCE TO](https://dev.mysql.com/doc/refman/8.4/en/change-replication-source-to.html)
