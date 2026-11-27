# Pre-Change Backups, Recovery Rehearsals, and Downgrade Limitations

In the **DATABASE_MYSQL** module, schema changes, version upgrades, or server replacements can impact data and the operational stability of the entire system. A DDL statement might complete yet still break applications because dependent views, triggers, routines, or data have changed. An upgrade can alter the data dictionary, metadata, or storage format in ways that older versions can no longer read.

Therefore, before any critical change, you need a restorable backup, a point-in-time recovery plan, and a rehearsal in an isolated environment. This lesson presents how to select a backup method, preserve binary logs, recover to a point in time, verify results, and evaluate limitations when attempting to return to an older MySQL version.

Within `DATABASE_MYSQL`, this topic connects with table design, data types, keys, SQL queries, indexes, transactions, and concurrency control. Recovery rehearsals also rely on reading execution plans, query tuning, access control, backups, and handling relational database operational issues.

## 1. Objectives and Principles

After completing this lesson, you will be able to:

- Identify data, configuration, and objects requiring protection before schema changes or upgrades.
- Distinguish logical backups, physical backups, storage snapshots, and binary logs.
- Create backups containing the metadata needed for point-in-time recovery (PITR).
- Restore a backup onto an isolated server and replay binary logs up to a chosen point.
- Rehearse failure scenarios, measure RPO/RTO, and verify data post-restore.
- Explain why application rollback and server downgrade are two distinct operations.
- Select a safe recovery approach when a new version cannot be downgraded in place.

A backup has operational value only when it can be restored. An existing file, large file size, or valid checksum does not prove that MySQL can open the data, applications can access it, and business constraints still hold.

Before executing a change, answer four questions:

1. If the operation fails, to what point in time must data be recovered?
2. What is the maximum acceptable data loss?
3. How long does it take to recover and bring the service back online?
4. Can the old MySQL version read data after the change, or must a separate pre-change backup be restored?

## 2. RPO, RTO, and Recovery Scope

**RPO (Recovery Point Objective)** is the maximum amount of data loss tolerable, measured in time or transaction point. If RPO is 5 minutes, the system must be able to recover data to a point no older than 5 minutes before the incident.

**RTO (Recovery Time Objective)** is the maximum duration to restore the service to an operational state. RTO must account for provisioning the server, restoring the backup, replaying binary logs, validating data, switching endpoints, and reopening traffic.

| Objective | Question to Answer | Common Measures |
|---|---|---|
| RPO | How many transactions at most can be lost? | Periodic full backups, continuous binary log archiving, PITR |
| RTO | How long until the service operates again? | Backups with suitable restore speed, standby resources, rehearsed runbooks |
| Scope | Recover the entire instance, a schema, a table, or specific records? | Appropriate backups and a dedicated restore environment |
| Consistency | Does data preserve transaction boundaries and business relationships? | Consistent snapshots, ordered log replay, invariant checks |

Do not pick backup schedules based solely on disk capacity or storage cost. The schedule must match RPO, data generation rate, and restore duration. If binary logs are retained for only 24 hours while an incident may not be noticed for 2 days, PITR will fail to meet its goal.

## 3. What Needs to Be Backed Up Before a Change

### 3.1. Data and Structure

Before changing schemas or upgrading, inventory:

- Databases, tables, partitions, indexes, constraints, and tablespaces.
- Views, triggers, stored procedures, functions, and events.
- Business data, reference data, and audit/ledger tables.
- Charsets, collations, SQL modes, time zones, and critical configuration variables.
- Users, roles, grants, authentication plugins, and privilege definitions.
- Replication settings, GTIDs, binary logs, and cluster state.
- Required plugins, components, keyrings, TLS certificates, and encryption keys.
- Server configuration files, startup parameters, services, and operational scripts.

The MySQL 8.4 upgrade guide requires pre-upgrade backups to include the **mysql** system schema, which stores the data dictionary and system tables. This is crucial when restoring an entire instance back to the pre-upgrade version. However, when logically migrating data to a different version, do not blindly import raw system tables from the source version; use compatible procedures to recreate users and privileges.

Not all of the items above reside inside a data dump. For instance, configuration files, certificates, encryption keys, secrets, external plugins, and keyring keys must be protected through dedicated procedures.

### 3.2. Users, Roles, and Privileges

MySQL accounts are part of application recoverability. If data is restored but connection accounts, roles, or privileges are missing, the service still cannot run.

Inspect accounts and privileges using:

~~~sql
SHOW CREATE USER 'app_user'@'%';
SHOW GRANTS FOR 'app_user'@'%';
~~~

Save user, role, grant, and authentication policy definitions using a method appropriate for your version. Do not manually copy `mysql` schema system tables across incompatible versions. When restoring to a different version, recreate accounts using SQL statements supported by the target version or a compatible user-export tool.

### 3.3. Configuration and Encryption Keys

If data uses tablespace encryption, a keyring, or backup encryption, protect both the keys and the metadata required for decryption. A backup containing encrypted data without its keyring may be unrecoverable.

Store separately under access control:

- MySQL configuration files and startup arguments.
- Keyrings and encryption keys following security procedures.
- CA certificates, server certificates, and private keys for TLS connections.
- Plugins or components required to open data.
- Backup tool version information and checksums.

Never store secrets or private keys in repositories, shared documents, or backup job logs. Test key recovery procedures in a dedicated rehearsal.

## 4. Choosing a Backup Method

Three common categories exist. They can be combined to meet RPO/RTO goals.

| Method | Description | Advantages | Limitations to Note |
|---|---|---|---|
| Logical backup | Exports DDL and data as SQL statements or dump files | Flexible, easy to move data between compatible servers | Restores can be slow for large datasets; requires schema compatibility checks |
| Physical backup | Copies physical data files and required metadata using a backup tool | Restores are usually faster for large datasets | Depends on version, platform, tool, and prepare/restore steps |
| Storage snapshot | Snapshots the volume or filesystem holding data | Can be fast to create, convenient for large storage | Must ensure snapshot consistency; raw snapshots may only be crash-consistent |
| Binary log archive | Preserves changes after the baseline backup | Supports PITR and recovery to a transaction point | Does not replace full backups; requires an unbroken, ordered log chain |

### 4.1. Logical Backup with mysqldump

Example dumping an InnoDB schema before a change:

~~~bash
mysqldump --login-path=backup \
  --single-transaction --quick \
  --source-data=2 \
  --routines --events --triggers --hex-blob \
  --databases appdb \
  > appdb-before-change.sql
~~~

Meaning of the options:

- **--single-transaction** creates a consistent snapshot for transactional tables such as InnoDB.
- **--quick** streams rows rather than buffering entire tables into client memory.
- **--source-data=2** writes the corresponding binary log coordinates into the dump as a comment, useful for PITR or file/position replication.
- **--routines**, **--events**, **--triggers** include the corresponding objects in the dump.
- **--hex-blob** exports binary data in a SQL-safe hexadecimal format.

**--single-transaction** does not guarantee a consistent snapshot for non-transactional tables. During the dump, avoid running DDL such as `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE` on involved tables; concurrent DDL can make the dump inconsistent or cause it to fail.

When using **--source-data**, binary logging must be enabled and the account needs appropriate privileges to read log status. The tool may acquire a brief global read lock to capture consistent coordinates. Check the command exit code, dump file header, and tool logs before treating the backup as complete.

This example dumps only the `appdb` schema; it does not protect server-wide configs, encryption keys, option files, or all system accounts. For a full-instance pre-upgrade backup, choose a method that includes the `mysql` system schema and business databases.

### 4.2. Logical Backup with MySQL Shell

For large datasets, MySQL Shell provides dump/load utilities capable of chunking and multi-threaded workers:

~~~javascript
util.dumpSchemas(
  ['appdb'],
  '/backup/appdb-before-change',
  {
    threads: 8,
    bytesPerChunk: '128M',
    consistent: true,
    checksum: true
  }
);
~~~

You can dump the entire instance with **util.dumpInstance()** when backup scope needs multiple schemas and instance-level objects. Select user and metadata scope according to the documentation for your MySQL Shell version.

Items to verify:

- Is the snapshot consistent across all storage engines in use?
- Does the dump include GTID metadata and matching binary log coordinates?
- Were all chunks and metadata files created completely?
- Are checksums verified during dump and load?
- Does the dump account follow least privilege while retaining required rights?
- Does the backup destination have sufficient space and get moved to independent storage?

Tune worker threads and chunk size according to CPU, I/O, network, and production load. Increasing workers too high can overload the source or slow down business queries.

### 4.3. Physical Backups and Storage Snapshots

For large datasets, physical backup tools can shorten restore times. Use a tool supported for the exact MySQL version, operating system, and storage engine—for example, MySQL Enterprise Backup or a compatible tool such as Percona XtraBackup per vendor support matrices.

A typical physical backup workflow includes:

1. Run an initial full backup.
2. Run scheduled incremental backups if supported by the tool.
3. Record metadata for version, GTID, and binary log coordinates.
4. Run the prepare/apply-log step as required by the tool.
5. Transfer the backup to independent storage.
6. Perform a test restore on a compatible server.

Never directly copy the data directory of a running MySQL Server and treat it as a consistent backup. Storage snapshots must be coordinated with flush/quiesce mechanisms or system snapshot-aware tools to guarantee consistency. A crash-consistent-only snapshot still requires testing with a real recovery procedure.

Never open a newer version's physical backup using an older version unless MySQL and tool documentation confirm that downgrade path is supported.

## 5. Binary Logs and Point-in-Time Recovery

### 5.1. Why Do Backups Need Binary Logs?

A full backup captures data state at a single point in time. Transactions after that point are recorded in binary logs. By combining a base backup with an unbroken sequence of binary logs, you can replay changes to recover to a specific moment.

Check configuration and status:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOG STATUS;
SHOW BINARY LOGS;
~~~

Notes:

- **log_bin** must be enabled if binary logging is needed.
- File/position coordinates or the GTID set must be recorded alongside the backup.
- All contiguous log files from the backup point to the recovery point must be preserved.
- Do not let purge policies delete logs before the backup's PITR window expires.
- Copy binary logs to independent storage to protect against host loss.

GTIDs identify transactions and track the executed transaction set. File/position identifies an event's exact offset within a specific binary log file. Choose a consistent recovery-point tracking method and record metadata immediately upon backup completion.

### 5.2. Replaying Logs to a Target Point

Suppose a backup was taken at recorded coordinates, and later an accidental `DROP TABLE` ran at 14:35. The goal is to restore state immediately before that event.

You can use **mysqlbinlog** to read log files in order and bound the replay window:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 14:34:59" \
  /backup/mysql-bin.000123 \
  /backup/mysql-bin.000124 \
  > /restore/replay-before-error.sql
~~~

This example illustrates generating a replay script; substitute actual coordinates, timestamps, filenames, and timezones from your metadata. For high-precision incidents, pinpoint exact event positions and transaction boundaries rather than relying solely on timestamps.

Before executing:

- Verify log files are contiguous and properly ordered.
- Identify the offending event and exact stop point prior to it.
- Check GTIDs, `BEGIN`, `COMMIT`/`Xid`, and `end_log_pos`.
- Inspect the output file to ensure no out-of-scope transactions are replayed.
- Test on an isolated restore before applying to the primary recovery environment.

After verification, replay onto the recovery server:

~~~bash
mysql --login-path=recovery < /restore/replay-before-error.sql
~~~

Never replay directly against production without knowing exact contents and stop boundaries. DDL commonly triggers an implicit commit; you cannot rely on `ROLLBACK` to undo a committed `DROP TABLE`.

### 5.3. Preserving the Log Chain

A binary log chain missing a file or transaction segment prevents PITR from reaching the desired point. Establish a process to:

- Archive log files off the source server.
- Maintain a manifest of filenames, sizes, checksums, and sequence order.
- Monitor retention windows and archive storage capacity.
- Verify log files are readable with `mysqlbinlog`.
- Restrict access because binary logs can contain sensitive data.
- Never purge logs based solely on file age if replicas or PITR workflows still need them.

## 6. Backing Up Before Schema Changes or Upgrades

### 6.1. Establishing a Pre-Change Checkpoint

Before risky changes such as `DROP COLUMN`, data type changes, partition alterations, table rebuilds, or version upgrades:

1. Assess impact scope and what data could be lost or transformed.
2. Choose an appropriate full logical or physical backup.
3. Record the GTID set or binary log coordinates.
4. Save configurations, accounts, privileges, keys, and required plugins.
5. Verify backups and binary logs reside on independent storage.
6. Record the MySQL version, tool versions, and backup timestamp.
7. Run a restore rehearsal in an isolated environment.

Do not merely take a backup right before running DDL. Leave time to test restoring it before starting the change. If the test restore fails, fix the backup process before performing irreversible operations.

### 6.2. Rehearsing Migrations on a Clone

Use a clone or staging environment closely matching production structure and scale:

- Restore the base backup.
- Replay binary logs up to the test checkpoint.
- Execute the schema migration or version upgrade.
- Run application smoke tests and critical queries.
- Verify data, constraints, indexes, views, triggers, and routines.
- Measure DDL duration, restore time, and resource impact.
- Test recovery steps when a migration fails mid-way.

A migration succeeding on a tiny test database does not prove it will finish within an acceptable production window. Data size, fragmentation, indexes, metadata locks, and concurrent load can drastically alter execution time.

### 6.3. DDL Cannot Always Be Rolled Back

Many DDL statements in MySQL trigger an implicit commit. Atomic DDL in supported versions protects certain operations better against crashes, but it does not mean users can issue `ROLLBACK` to undo a DDL statement once it completes.

Example:

~~~sql
ALTER TABLE appdb.orders
  DROP COLUMN legacy_code;
~~~

If the statement finishes and the application discovers it still needs `legacy_code` data, `ROLLBACK` cannot restore the dropped column and values. You must restore a backup or reconstruct data from another source, then reconcile transactions that occurred since the backup point.

For irreversible changes, treat backups and restore capability as part of the deployment plan, not an afterthought once an incident happens.

## 7. Rehearsing Recovery in an Isolated Environment

### 7.1. Preparing the Restore Environment

The rehearsal environment needs:

- A MySQL server compatible with the backup version and restore tool.
- Sufficient disk space for data, temporary files, relay/binlogs, and backup archives.
- Network isolation or firewall rules preventing production apps from connecting accidentally.
- Dedicated recovery credentials, avoiding unnecessary production credentials.
- Keyrings, plugins, certificates, and settings needed to open the data.
- Distinct endpoints and DNS clearly marked as a test environment.
- Storage for logs and verification results.

Never overwrite a production server just to test a backup. Rehearsals must be repeatable without risking live data.

### 7.2. Restore Sequence

A general runbook:

1. Provision the recovery server and install the target MySQL version.
2. Apply compatible configurations, plugins, keyrings, and filesystem permissions.
3. Restore the full backup using the appropriate tool.
4. For physical backups, perform the prepare/restore step per tool documentation.
5. Verify MySQL starts and opens every tablespace.
6. Verify required databases, tables, indexes, views, triggers, routines, and users.
7. Replay binary logs from the backup coordinates up to the recovery target.
8. Run data checks and business invariant validations.
9. Run smoke tests using a test application account.
10. Record timings for each step, encountered errors, and final outcomes.

When restoring logical backups, inspect client exit codes and logs; a SQL file may load partially before failing. When restoring physical backups, inspect prepare logs, server logs, and tablespace status after startup.

### 7.3. Verifying Data After Restore

Verify across multiple layers:

**Structure**

- All schemas, tables, partitions, indexes, and constraints are present.
- Column definitions, charsets, collations, and engines match.
- Required views, triggers, routines, and events function.
- Users, roles, and grants have the right scope.

**Data**

- Row counts for critical tables.
- Monetary totals, balances, order counts, or business quantities.
- Min/max values and date/time ranges.
- Orphan foreign-key records or duplicate unique keys.
- Checksums or chunked data comparisons where tools support them.

**Business Logic**

- Sample records can be read and updated by the application.
- Order statuses, payments, and audit logs reconcile.
- Background jobs, events, and consumers operate properly.
- Zero records missing due to skipped logs or duplicated due to replayed transactions.

Example count and total verification:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount,
       MIN(created_at) AS first_order,
       MAX(created_at) AS last_order
FROM appdb.orders;
~~~

Compare against the source or reference report at the same data point. If comparing two servers at different times while the source continues accepting writes, differences may simply reflect sampling skew. Compare at the same snapshot/GTID point or in a write-frozen environment.

### 7.4. Measuring Actual RTO/RPO

Record timings:

| Phase | Start/End Time | Duration |
|---|---|---|
| Provision recovery host | Per rehearsal log | Actual measurement |
| Restore backup | Per tool log | Actual measurement |
| Apply binary logs | Per PITR target | Actual measurement |
| Verify data | Per checklist | Actual measurement |
| Smoke tests and reopen service | Per runbook | Actual measurement |

Actual RTO is the total elapsed time required to return the service to an operational state, not just how long the restore command runs. Actual RPO is determined by the latest recoverable data point and data loss observed in the test scenario.

If restore time exceeds RTO, adjust tools, full/incremental backup schedules, compute resources, standby architecture, or verification scope. Never mark RTO as met merely because backups are fast to create.

## 8. Limitations of MySQL Downgrades

### 8.1. Downgrade Differs from Application Rollback

Application rollback reverts code or configuration to a prior release while the database retains a compatible schema. A MySQL downgrade moves the server or data format back to an older version. The two operations carry different risks and requirements.

An older application version might fail against a new schema, but that does not mean you must downgrade MySQL. You may instead need a backward-compatible schema migration, an intermediate application build, or data recovery on a separate host.

### 8.2. Do Not Assume In-Place Downgrades Are Possible

Never assume MySQL can open a newer version's data directory using older server binaries. Across versions, the data dictionary, redo/undo logs, metadata, system schemas, and storage formats can change.

Downgrades must be verified against the exact release series, source/target versions, and documented supported methods. For MySQL 8.4, the downgrade documentation clearly distinguishes cases:

| Downgrade Path | Methods Listed in 8.4 Docs | Notable Conditions |
|---|---|---|
| Within the same 8.4.y LTS series to 8.4.x | In-place, logical dump/load, Clone, or replication | Must check the downgrade threshold and exact patch release pair |
| From 8.4.x LTS to 8.0.y | Logical dump/load or replication | Only for rollback if data has not used new server functionality |
| From 8.4.x LTS to 8.3.0 Innovation | Logical dump/load or replication | Only for rollback if data has not used new server functionality |
| To MySQL 5.7 or earlier | Unsupported | Do not perform downgrade |

The methods and conditions above reflect MySQL 8.4 documentation; do not apply them verbatim to other MySQL versions. For a patch pair within the same LTS series, check the downgrade threshold enforced by the server; a release may refuse to revert to an overly old patch. Whenever version documentation or downgrade validation does not confirm the path, use the pre-upgrade backup restore approach.

Note that the **Before You Begin** page of the same MySQL 8.4 documentation carries a stricter caution against downgrading from 8.4 to 8.3 or an earlier 8.4 release, whereas the table in the **Downgrading MySQL** chapter lists supported methods by release series. When documentation pages phrase things differently, do not infer that a specific version pair permits an in-place downgrade. Check release notes, downgrade validation, and support policy for the exact build; if unconfirmed, rely on the pre-upgrade backup as your fallback.

### 8.3. Changes That Can Block a Downgrade

Factors to review:

- Data dictionary or metadata format changes across versions.
- New data types, column attributes, or DDL syntax unknown to the older version.
- New collations, charsets, or comparison rules.
- Functional indexes, invisible indexes, generated columns, or expression defaults.
- New plugins, components, authentication plugins, or account formats.
- InnoDB redo/undo, tablespace, or metadata formats.
- System tables, roles, grants, and `mysql` schema structure.
- Version-dependent replication features, GTIDs, or binlog metadata.

This list represents risk categories to inspect, not a claim that every feature automatically blocks every downgrade. Consult official documentation for your exact versions and test on a representative clone.

### 8.4. Approaches for Returning to an Older Version

If the new version hits an incident and in-place downgrade is unsupported, standard options include:

**Restore the pre-upgrade backup.** Provision a server with the matching old version, restore the full pre-upgrade backup, and replay binary logs up to an acceptable point if the log chain and format are compatible. This is the direct way to return to the pre-upgrade state.

**Logical export/import.** If you must move data from the newer version back to an older server, export schema and data logically, adjust incompatible DDL/types/features, and import into the older server. Carefully inspect features unsupported by the older version. This is a data migration, not a physical downgrade.

**Run in parallel and switch endpoints.** Initialize the older server from backup, synchronize data via a tested method, and switch applications after reconciliation. If the newer server already accepted writes, reverse replication or CDC/reconciliation is required to avoid losing transactions committed after the backup point.

Never copy a data directory from a newer server to an older server, never edit system tables directly to force startup, and never ignore upgrade/downgrade errors. Such actions can corrupt data and make recovery far harder.

## 9. Pre- and Post-Upgrade Plan

### 9.1. Pre-Upgrade

1. Record the MySQL version, operating system, configuration, plugins, and replication topology.
2. Run a pre-upgrade compatibility checker suited to the target version, such as MySQL Shell Upgrade Checker where supported.
3. Resolve warnings regarding syntax, data types, reserved words, system variables, and removed features.
4. Create a full backup including required system schemas and preserve binary logs from the backup point.
5. Save user/role/grant definitions, configuration files, keyrings, and certificates.
6. Test-restore the backup in an isolated environment.
7. Rehearse the upgrade and recovery plan on a representative clone.
8. Confirm RPO/RTO and maintenance duration with system owners.

Upgrade Checker identifies many compatibility issues; it does not replace backups, restore rehearsals, or application testing.

### 9.2. During Upgrade

- Put applications into maintenance mode or restrict writes per the runbook.
- Confirm backups and binary logs are ready.
- Stop or handle jobs that could write to the database during the upgrade.
- Execute the upgrade along the exact supported version path.
- Monitor error logs, upgrade progress, and disk space.
- Do not open application traffic until server and schema checks complete.

### 9.3. Post-Upgrade

- Confirm server version and service status.
- Verify schemas, indexes, views, triggers, routines, and events.
- Verify users, roles, grants, plugins, TLS, and keyrings.
- Verify replication/cluster health and binary log status.
- Run critical queries, smoke tests, and data reconciliation.
- Monitor execution plans, latency, deadlocks, and system load.
- Retain pre-upgrade backups and binary logs throughout the approved rollback window.

If you must revert to the old version after the new system has accepted transactions, determine how to synchronize those new transactions before switching endpoints. Pointing applications back to the old server without transferring writes created on the new server risks losing transactions or creating split data histories.

## 10. Common Incidents and Remediation

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Backup files exist, but restore fails | Missing or corrupt files, incompatible tool, or incomplete metadata | Check checksums, backup logs, and tool version; take a new backup if needed |
| MySQL cannot open tablespaces after restore | Missing data files, keyring, plugin, or prepare step | Check logs, encryption keys, filesystem permissions, and restore procedure |
| PITR stops due to missing binary logs | Retention too short or incomplete archive | Recover from an earlier backup with an intact log chain; adjust retention policy |
| Restore finishes, but applications cannot connect | Missing users/grants, authentication plugin, or TLS | Recreate accounts using compatible methods and verify privileges |
| Data differs from source | Wrong log boundary, skipped events, inconsistent restore, or duplicate replay | Verify coordinates/GTIDs, log sequence, and business invariants |
| DDL fails due to metadata lock | Long-running transaction or query holding metadata lock | Identify blocker, drain transactions, and retry in a suitable window |
| Old version fails to start with new data directory | In-place downgrade unsupported or past downgrade threshold | Provision the old version separately and restore the pre-upgrade backup |
| Logical import reports syntax errors | DDL or new features unsupported by the older version | Transform schemas and data in a controlled manner before importing |
| Recovery takes too long | Suboptimal backup/restore method or insufficient resources | Use suitable physical backups, add resources, and re-rehearse |
| Reverting to old server loses transactions | New server accepted writes after the backup point | Perform reverse sync or data reconciliation before switching endpoints |

Never ignore restore, applier, or upgrade errors just to reach a Running service state. A server that starts can still be missing tables, missing transactions, or misconfigured on privileges.

## 11. Checklist Before Critical Changes

### Backup

- [ ] Defined RPO/RTO and required recovery scope.
- [ ] Selected logical/physical backup suited to size and version.
- [ ] Recorded backup GTID set or binary log coordinates.
- [ ] Archived binary logs continuously with sufficient retention.
- [ ] Protected configs, users/roles/grants, plugins, keyrings, and certificates.
- [ ] Encrypted backups and restricted access permissions.
- [ ] Verified checksums and tool logs.
- [ ] Stored backups off the source host.

### Recovery Rehearsal

- [ ] Restored in an isolated environment.
- [ ] Used the exact compatible version and tools.
- [ ] Replayed binary logs to the target point.
- [ ] Verified schemas, objects, users, and privileges.
- [ ] Reconciled row counts, checksums, and business invariants.
- [ ] Ran application smoke tests.
- [ ] Measured restore time and time to restore service.
- [ ] Documented failures and updated the runbook.

### Downgrade/Rollback

- [ ] Checked whether documentation supports a downgrade path for the exact versions.
- [ ] Checked downgrade threshold if downgrading within the same LTS series.
- [ ] Did not assume the new data directory is compatible with the old server.
- [ ] Kept pre-upgrade backups and required binary logs.
- [ ] Defined how to transfer transactions committed after the new version accepted writes.
- [ ] Prepared a separate old-version server if restore is needed.
- [ ] Tested logical export/import if used as a fallback option.
- [ ] Assigned approvers and endpoint-switching criteria.

## 12. Self-Check

**Scenario 1:** A DBA creates a `mysqldump` file but has never tested restoring it. Can the system be considered to have a reliable backup plan?

**Hint:** No. File existence does not prove restorability. You must restore into an isolated environment and verify structure, data, and applications.

**Scenario 2:** An InnoDB table is dumped with `--single-transaction`, and during the dump someone executes `ALTER TABLE` on that same table. Can you assume the dump remains consistent?

**Hint:** No. `--single-transaction` does not protect the dump from concurrent DDL. Freeze DDL on involved objects during the snapshot window.

**Scenario 3:** A `DROP TABLE` statement was executed by mistake and completed. Can `ROLLBACK` be used to bring the table back?

**Hint:** No. DDL causes an implicit commit. Restore a backup into a recovery environment and replay binary logs up to just before the `DROP` event, then verify the data.

**Scenario 4:** After an upgrade, the application fails and the team wants to run the old MySQL binaries over the current data directory. Is this a safe downgrade plan?

**Hint:** Never assume so. Check official downgrade paths and downgrade thresholds. If unsupported, provision a separate old-version server and restore the pre-upgrade backup or perform a compatibility-checked logical export/import.

**Scenario 5:** A backup was created at 01:00, an incident occurred at 09:00, and binary logs exist only up to 06:00. What actual RPO can be achieved?

**Hint:** Transactions after the last available log cannot be recovered. Maximum recovery is bounded by the backup plus the contiguous binary log chain; RPO cannot exceed the preserved log data.

## 13. Key Takeaways

- A backup is trustworthy only after restoring and verifying it in an isolated environment.
- Choose backups based on RPO/RTO and recovery scope; logical, physical, snapshot, and binary log mechanisms serve different roles.
- Consistent snapshots require proper coordination with storage engines and DDL; `--single-transaction` guarantees a transactional snapshot only for InnoDB tables.
- Record GTID or binlog coordinates alongside backups and maintain an unbroken binary log chain to support PITR.
- Protect users, roles, grants, configurations, plugins, keyrings, and certificates needed to open the data.
- DDL triggers an implicit commit; atomic DDL does not mean `ROLLBACK` is possible after the operation finishes.
- Recovery rehearsals must verify structure, data, business logic, security, and recovery duration.
- In-place downgrades depend on LTS/Innovation branches, version pairs, and downgrade thresholds; never apply a single rule across all versions.
- When returning to an older version, prefer restoring a pre-upgrade backup onto a compatible host or performing a tested logical export/import.
- If the new version has accepted writes, synchronize new transactions before switching applications back to the old server.

## References

- [MySQL 8.4 Reference Manual: Backup and Recovery](https://dev.mysql.com/doc/refman/8.4/en/backup-and-recovery.html) — backup and restore methods.
- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html) — logical backups, snapshots, and binary log coordinates.
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html) — recovery using binary logs.
- [MySQL 8.4 Reference Manual: Upgrade Paths](https://dev.mysql.com/doc/refman/8.4/en/upgrade-paths.html) — supported upgrade paths.
- [MySQL 8.4 Reference Manual: Downgrading MySQL](https://dev.mysql.com/doc/refman/8.4/en/downgrading.html) — downgrade methods and conditions by version.
- [MySQL 8.4 Reference Manual: Before You Begin an Upgrade](https://dev.mysql.com/doc/refman/8.4/en/upgrade-before-you-begin.html) — pre-upgrade backup requirements, including the `mysql` system schema.
- [MySQL Shell 8.4 Reference: Upgrade Checker Utility](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-shell-utilities-upgrade.html) — pre-upgrade compatibility checks.
