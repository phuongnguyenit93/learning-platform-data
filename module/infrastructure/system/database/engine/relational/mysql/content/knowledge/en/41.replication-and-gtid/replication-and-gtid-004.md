# Setting up replication using file/position or GTID

This lesson belongs to the **DATABASE_MYSQL** module. In the journey to mastering MySQL, replication helps maintain one or more data copies to support availability, read scaling, and server switching when needed. To operate replication safely, you must configure the binary log, server identities, replication accounts, an initial data seed, and a synchronization starting point. MySQL supports specifying the starting point either with a **binlog file/position** pair or with **GTID (Global Transaction Identifier)**.

Default MySQL replication is asynchronous: the source writes transactions to the binary log; the replica fetches events from the source, saves them to the relay log, and then applies them to its own data. Therefore, a replica can lag behind the source. Replication improves availability and helps scale certain read workloads, but it does not replace independent backups or PITR recovery procedures.

## 1. Basic replication architecture

In the source/replica model:

1. The application sends write operations to the **source**.
2. The MySQL source writes eligible changes to the binary log.
3. The receiver thread on the **replica** connects to the source using a replication account and reads new events.
4. The replica stores the events in the relay log.
5. The applier thread reads the relay log and executes the changes on the replica.

The two threads on the replica have different responsibilities:

- **Receiver (I/O thread):** connects to the source, fetches binary log events, and writes them to the relay log.
- **Applier (SQL thread or worker threads):** reads the relay log and applies transactions to the replica's data.

High-level diagram:

```text
Write application
    |
    v
+------------------+
| Source MySQL     |
| Binary log       |
+------------------+
    |
    |  replication connection
    v
+------------------+
| Replica MySQL    |
| Receiver / I/O   |
| Relay log        |
| Applier / SQL    |
+------------------+
    |
    v
Read application (if designed appropriately)
```

In newer MySQL documentation, the terms `SOURCE` and `REPLICA` replace `MASTER` and `SLAVE`. Modern statements are `CHANGE REPLICATION SOURCE TO`, `START REPLICA`, `STOP REPLICA`, and `SHOW REPLICA STATUS`. Some older versions use the legacy naming syntax; choose commands compatible with the version you are running. The examples below prefer MySQL 8.0.23 and later syntax.

## 2. Preparing the source and replica

Before establishing the connection, configure server identities and binary logging on the servers.

### 2.1. Configuring the source

Example configuration in the MySQL configuration file:

```ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
binlog_format=ROW
binlog_expire_logs_seconds=604800
```

- `server_id` is the numeric identifier of a server in the replication topology. Every server must have a unique, non-zero ID.
- `log_bin` enables binary logging and sets the base name for binlog files.
- `binlog_format=ROW` is the commonly recommended choice for replication because it logs actual row changes. Format behavior and configurability depend on the MySQL version.
- `binlog_expire_logs_seconds` sets automatic binlog retention in seconds. Retention must be long enough for a disconnected replica to have time to catch up and for PITR procedures to still have the required logs.

After changing startup configuration, restart MySQL if the variables require it. Verify:

```sql
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
```

### 2.2. Configuring the replica

The replica also needs its own unique `server_id`. If the replica will serve binlogs to downstream replicas or may be promoted to source, enable logging of transactions received from upstream:

```ini
[mysqld]
server_id=102
relay_log=/var/lib/mysql/mysql-relay-bin
log_bin=/var/lib/mysql/mysql-bin
log_replica_updates=ON
read_only=ON
super_read_only=ON
```

`log_replica_updates=ON` ensures that transactions applied from the source are also written to the local binary log, which is useful for multi-tier replication and certain role-switching procedures. `read_only` and `super_read_only` help restrict direct writes from applications or regular users on the replica; high-privilege administrative accounts still need tight control. The replication stream can apply changes via MySQL's internal mechanisms.

Not every replica needs `log_bin` enabled if it only serves reads and does not require downstream replication or promotion. Determine its intended role upfront and design the configuration accordingly. After restarting, verify `server_id` and the configured variables.

### 2.3. Network and version preparation

- The source must allow TCP connections from the replica to the MySQL port, typically `3306`, per firewall and network policy.
- Both servers must have compatible versions and configurations. Check the upgrade/replication documentation for your specific versions, especially if the source and replica are on different release branches.
- Synchronizing system clocks makes logs, monitoring, and incident investigation easier. Wall-clock time does not replace transaction ordering in the binlog.
- Use TLS to encrypt replication connections over untrusted networks.
- The replication account should only be allowed to connect from the replica's address and hold only the necessary privileges.

## 3. Creating the replication account

On the source, create a dedicated account for the replica. Replace the illustrative IP address and password with your real environment's values:

```sql
CREATE USER 'repl'@'192.0.2.20'
  IDENTIFIED BY 'replace-with-a-strong-secret'
  REQUIRE SSL;

GRANT REPLICATION SLAVE
  ON *.* TO 'repl'@'192.0.2.20';
```

The `REPLICATION SLAVE` privilege allows the replica to read the source's binary log. This privilege name still appears in many MySQL versions and docs; check supported privilege syntax if using a newer release or different distribution. Do not grant `ALL PRIVILEGES` to the replication account.

Verify the account and privileges:

```sql
SHOW GRANTS FOR 'repl'@'192.0.2.20';
```

The password in the example is only a placeholder. Never write real passwords into source code, shell history, or shared documents. When running `CHANGE REPLICATION SOURCE TO`, connection details are stored in replication metadata; restrict access to the server and any tools that can read this metadata.

## 4. Initializing data on the replica

Replication only transmits changes generated after the configured starting point. It does not automatically copy all existing data prior to that point. Therefore, before starting replication, the replica must have a consistent baseline data copy corresponding to the starting point.

You can initialize via logical backup, physical backup, or the MySQL Clone Plugin depending on scale and version. Whichever tool you choose, preserve the metadata indicating the exact binlog position or GTID set included in the baseline data copy.

Example logical dump on the source with InnoDB:

```bash
mysqldump \
  --host=source.example.net \
  --user=backup_user \
  --password \
  --single-transaction \
  --source-data=2 \
  --routines \
  --events \
  --all-databases \
  > initial-backup.sql
```

`--single-transaction` creates a consistent snapshot for transactional tables such as InnoDB. `--source-data=2` writes binary log file/position information into the dump as a comment so the operator can obtain the replication starting point. This option and its new name depend on the version; older versions may use `--master-data=2`. Check `mysqldump --help` and version-specific documentation before running.

With non-transactional tables, DDL changes during the dump, or complex write workloads, the snapshot may not be as consistent as expected. Schedule a maintenance window, apply appropriate write locks, or use a backup tool with a consistent snapshot mechanism. The backup account must also have sufficient privileges for the dump scope.

After the dump completes, transfer the file to the replica over a secure channel and restore it onto the prepared replica. Before importing, ensure the replica does not already hold conflicting data or incompatible GTIDs. Verify schemas, objects, key row counts, and backup metadata before configuring the replication stream.

## 5. Setting up replication using file/position

The file/position method specifies the binary log file and byte offset where the replica starts reading events. This is the traditional positioning approach, easy to inspect and useful when the system has not enabled GTID.

### 5.1. Obtaining the file and position from the backup

For a dump created with `--source-data=2`, open the top of the file and locate the comment line containing the `CHANGE REPLICATION SOURCE TO` statement or equivalent syntax for your version. Illustrative example:

```sql
-- CHANGE REPLICATION SOURCE TO
--   SOURCE_LOG_FILE='mysql-bin.000145',
--   SOURCE_LOG_POS=782;
```

The two values above are examples only. Use the exact file name and position recorded in the backup being restored. If using a physical backup, obtain the coordinates from the metadata generated by the backup tool. Never run `SHOW BINARY LOG STATUS` at an arbitrary time and combine that position with a snapshot created at a different time; the two points must correspond to the exact same data state.

### 5.2. Configuring the source on the replica

After restoring the baseline data, run on the replica:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='source.example.net',
  SOURCE_PORT=3306,
  SOURCE_USER='repl',
  SOURCE_PASSWORD='replace-with-a-strong-secret',
  SOURCE_LOG_FILE='mysql-bin.000145',
  SOURCE_LOG_POS=782,
  SOURCE_CONNECT_RETRY=10,
  SOURCE_SSL=1;

START REPLICA;
```

Replace the host, credentials, file, and position with actual values. Configure TLS according to your environment's certificates; `SOURCE_SSL=1` requires an SSL/TLS connection, and production systems should also verify the CA, server certificate, and appropriate peer identity verification policy. Avoid disabling certificate verification just to make the connection work.

In older MySQL versions, attributes may use the `MASTER_` prefix and the `CHANGE MASTER TO` statement; newer versions prefer `SOURCE_`. Do not mix old and new syntax in the same statement.

### 5.3. Checking replication

On the replica:

```sql
SHOW REPLICA STATUS\G
```

Important fields:

| Field | Meaning |
|---|---|
| `Replica_IO_Running` | Whether the receiver thread is running |
| `Replica_SQL_Running` | Whether the applier thread is running |
| `Source_Host` | Source the replica is connecting to |
| `Source_Log_File` | Source binlog file the receiver is reading |
| `Read_Source_Log_Pos` | Position read from the source |
| `Relay_Source_Log_File` | Source file corresponding to the relay log currently being applied |
| `Exec_Source_Log_Pos` | Source position executed up to by the applier |
| `Seconds_Behind_Source` | Estimated lag based on replication status, not a complete measure for all scenarios |
| `Last_IO_Error` | Most recent receiver error |
| `Last_SQL_Error` | Most recent applier error |

Normally, both threads should show `Yes` with no recent errors. `Seconds_Behind_Source` equal to 0 does not by itself prove the data is completely reconciled; `NULL` can also appear when a thread is not running or lag cannot be determined. Combine thread status, log positions, lag metrics, and application data checks.

## 6. Setting up replication using GTID

**GTID** identifies a transaction with a unique identifier, typically formatted as `server_uuid:transaction_number`. Instead of configuring a replica to read from a specific file/position pair, GTID auto-position lets the replica advertise the set of transactions it has executed. The source sends the missing transactions that it still retains in its binary logs.

GTID reduces manual position management when switching sources, provisioning new replicas, or organizing multi-server topologies. However, it requires servers in the topology to have consistent GTID configuration and baseline data carrying accurate GTID metadata.

### 6.1. Enabling GTID on a new topology

For a new topology, you can configure the following on the source and all replicas:

```ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
gtid_mode=ON
enforce_gtid_consistency=ON
binlog_format=ROW
```

On each replica, set a distinct `server_id` and add options required for the replica role, such as `log_replica_updates=ON` if transactions received from the source must be logged locally. `gtid_mode=ON` requires transactions in the topology to satisfy GTID rules; `enforce_gtid_consistency=ON` prevents GTID-incompatible operations from executing per configuration.

After starting up, verify on each server:

```sql
SHOW VARIABLES LIKE 'gtid_mode';
SHOW VARIABLES LIKE 'enforce_gtid_consistency';
SELECT @@GLOBAL.server_uuid, @@GLOBAL.gtid_executed;
```

Do not reuse the same `server_uuid` across multiple instances. When copying a physical data directory to create a replica, follow your tool's instructions so the new instance receives an appropriate identity; do not clone the source's identity verbatim.

### 6.2. Migrating a running system to GTID

On an active topology, never switch `gtid_mode=ON` abruptly. MySQL provides an online transition procedure through permissive states so the system has time to drain older transactions. Perform this on every server in the topology in the exact order and per your version's documentation:

1. Enable `enforce_gtid_consistency=ON` after verifying the workload does not use incompatible statements.
2. Transition `gtid_mode` from `OFF` to `OFF_PERMISSIVE` on all servers.
3. Transition all servers to `ON_PERMISSIVE`.
4. Wait for already-started anonymous transactions to finish; check `ONGOING_ANONYMOUS_TRANSACTION_COUNT` on each server.
5. Only when the count of ongoing anonymous transactions is 0 across the entire topology, transition all servers to `ON`.

Example status check:

```sql
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL STATUS LIKE 'ONGOING_ANONYMOUS_TRANSACTION_COUNT';
```

Dynamic transition steps can be executed with `SET GLOBAL` where version and privileges permit, while also updating persistent configuration so the state is not lost on restart. If there are multiple sources/replicas or complex channels, plan the transition according to official documentation and test first in an equivalent environment.

### 6.3. Preparing baseline data with GTID

When using a logical dump, you can run `mysqldump` with `--set-gtid-purged=ON` to include executed GTID information in the dump:

```bash
mysqldump \
  --host=source.example.net \
  --user=backup_user \
  --password \
  --single-transaction \
  --set-gtid-purged=ON \
  --routines \
  --events \
  --all-databases \
  > gtid-seed.sql
```

This option can emit statements setting `GTID_PURGED` into the dump. Only restore this kind of dump onto an appropriately prepared instance, usually a fresh instance without a conflicting GTID set. Never reload GTID-setting statements onto an active replica or an instance with its own transaction history without analyzing its state first. For physical backups, use the GTID metadata recorded by the backup tool.

### 6.4. Configuring auto-position

After restoring the baseline data and verifying GTIDs, run on the replica:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='source.example.net',
  SOURCE_PORT=3306,
  SOURCE_USER='repl',
  SOURCE_PASSWORD='replace-with-a-strong-secret',
  SOURCE_AUTO_POSITION=1,
  SOURCE_CONNECT_RETRY=10,
  SOURCE_SSL=1;

START REPLICA;
```

When `SOURCE_AUTO_POSITION=1`, do not also specify `SOURCE_LOG_FILE` or `SOURCE_LOG_POS` in the same connection configuration. The replica sends its executed GTID set; the source computes which GTIDs the replica is missing and sends the corresponding transactions if the necessary binlogs remain available.

Verify:

```sql
SHOW REPLICA STATUS\G
```

Inspect `Auto_Position`, `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, the status of both threads, and the error fields. Exact field names may vary by version. Both the retrieved and executed GTID sets should advance in line with the source's write load.

## 7. Comparing file/position and GTID

| Criterion | File/position | GTID auto-position |
|---|---|---|
| Starting point | Binlog file name and byte position | Set of executed GTID transactions |
| Replica configuration | `SOURCE_LOG_FILE`, `SOURCE_LOG_POS` | `SOURCE_AUTO_POSITION=1` |
| Metadata to preserve | Exact binlog coordinates at snapshot | GTID set at snapshot and matching baseline data |
| When switching sources | Must recalculate matching file/position on the new source | Can automatically request missing GTIDs if topology and logs satisfy requirements |
| Complexity | Easy to understand in small topologies, but manual coordinate management | More convenient for failover and managing many transactions |
| Prerequisites | Continuous binlog from the starting position | GTID enabled and consistent across participating servers; logs still contain needed GTIDs |

GTID is generally preferred for new topologies and environments requiring controlled failover. File/position remains useful for compatibility with legacy systems or when manually configuring a specific read point. Both approaches require a consistent baseline data copy and adequate binlog retention.

## 8. Operating and monitoring a replica

Once replication is running, monitor continuously:

- Receiver and applier status; alert whenever either thread stops.
- Connection, authentication, TLS, privilege, and binlog read errors.
- Transaction apply lag, relay log generation rate, and disk space.
- The gap between read and applied positions; with GTID, track retrieved and executed GTID sets.
- Catch-up capability after a replica disconnects, especially when the source has short retention.
- Data consistency using verification queries or appropriate reconciliation tools.

You can enable read-only mode on the replica to prevent accidental application writes:

```sql
SET PERSIST read_only = ON;
SET PERSIST super_read_only = ON;
```

`SET PERSIST` depends on the MySQL version. If unsupported, place the variables in the configuration file and restart per procedure. High-privilege administrators can still modify data if this mode is turned off; therefore DBA privileges must be controlled.

Do not run `RESET REPLICA` or `RESET REPLICA ALL` merely as an attempt to fix errors. Reset commands can delete relay logs or connection metadata; understand their impact and record the current configuration before running them. Likewise, do not purge binlogs on the source while replicas still need those files.

## 9. Troubleshooting common errors

| Symptom | Possible cause | Remediation |
|---|---|---|
| `Replica_IO_Running: Connecting` or `No` | Wrong host/port, firewall, DNS, password, TLS, or missing replication privilege | Check connectivity from replica, account, `Last_IO_Error`, and source error log |
| Receiver reports binlog not found | Source purged the file the replica needs to read | Check retention and position; if logs are missing, rebuild the replica from a newer backup with matching coordinates/GTID |
| `Replica_SQL_Running: No` | Applied transaction hit an error, lock conflict, or schema mismatch | Read `Last_SQL_Error`, inspect data/schema, and identify the failing transaction before fixing |
| Duplicate key when applier runs | Replica had local writes, wrong seed data, or transaction applied from the wrong point | Stop unintended writes, find the source of divergence, and consider reseeding from a consistent snapshot |
| GTID auto-position cannot catch up | Required GTIDs are no longer in source binlogs or GTID sets are incompatible | Compare `gtid_executed`, binlog retention, and backup metadata; reseeding is usually required if transactions are missing |
| Replica lag is increasing | High write load, slow applied queries, or insufficient I/O or CPU | Monitor workers, relay log, resources, and long transactions; optimize the root cause |

Never skip a failing transaction by incrementing a skip counter or guessing GTID adjustments. Skipping an event can permanently diverge replica data from the source. Before intervening, identify the transaction, evaluate business impact, and have a backup/snapshot to fall back on if needed.

## 10. Role switching and limits of replication

When the source fails, a replica can be selected as the new source if its data has caught up and the failover procedure permits it. Before promoting:

1. Prevent clients from continuing to write to the old source or isolate the old source to avoid split-brain.
2. Verify that the replica has received and applied all transactions required by the RPO target.
3. Designate a single new source, configure write permissions, and update application endpoints.
4. If using GTID, verify GTID sets and configure auto-position for the remaining replicas.
5. Monitor errors, lag, and data after the switch; plan how to rebuild or reintroduce the old source into the topology.

Asynchronous replication can lose transactions not yet transmitted or applied when the source crashes suddenly. If near-zero RPO is required, evaluate complementary mechanisms such as semi-synchronous replication, quorum/failover design, and appropriate storage infrastructure. Never assume asynchronous replication guarantees zero data loss.

An accidental deletion or data corruption can be written to the binlog and propagated to replicas. Therefore, full backups, off-server binlog retention, and PITR drills remain essential. A replica is a component of an availability architecture, not an independent historical backup.

## 11. Deployment checklist

- [ ] Verified MySQL version and compatible replication syntax.
- [ ] Each source/replica has a unique `server_id`.
- [ ] Source has binary logging enabled with sufficient retention.
- [ ] Dedicated replication account, host-restricted, using TLS.
- [ ] Replica initialized from a consistent snapshot.
- [ ] File/position or GTID metadata matches the snapshot.
- [ ] Configured exactly one positioning method: file/position or GTID auto-position.
- [ ] `START REPLICA` succeeded; both receiver and applier are running.
- [ ] No unhandled `Last_IO_Error` or `Last_SQL_Error`.
- [ ] Appropriate read-only mode configured, with lag/relay log space monitored.
- [ ] Tested restoring or rebuilding a replica from backup to validate the runbook.

## 12. Self-check

1. What are the responsibilities of the receiver and applier on a replica? Where does the relay log sit in the data flow?
2. Why must baseline data be restored before starting replication?
3. Where must `SOURCE_LOG_FILE` and `SOURCE_LOG_POS` be obtained from, and why must coordinates not be taken at a different time from the snapshot?
4. How does `SOURCE_AUTO_POSITION=1` use GTIDs to locate missing transactions?
5. Why does GTID not eliminate the requirement to retain binary logs?
6. When migrating a running topology to GTID, why must you pass through the permissive states?
7. How is `log_replica_updates` useful in a multi-tier topology?
8. If the receiver is running but the applier has stopped, which status fields and errors should you inspect?
9. Why should you not skip a failing replication transaction without first identifying the root cause?
10. Describe how to provision a new replica using file/position and how to do the same using GTID auto-position.

When designing, start from the baseline backup and its metadata, then choose the positioning method suited to your topology. After starting replication, verify both the receive and apply streams, monitor lag, and test the rebuild procedure. A setup can be considered operationally sound only when it can maintain synchronization, detect errors, and recover replicas within the defined RPO/RTO bounds.
