# Distinguishing Logical Backup, Physical Backup, Restore, and Recovery

This lesson belongs to the **DATABASE_MYSQL** module. In the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control—backup and recovery is the capability that protects data against operator errors, hardware failures, software crashes, or service disruptions. Operators also need to know how to read execution plans, tune queries, manage privileges, perform backups, and troubleshoot relational database operations. This lesson focuses on distinguishing the two common ways of creating backups and the two phases of bringing a system back into operation.

## 1. Four Concepts to Distinguish

These terms often appear together, but they describe different things:

| Concept | Meaning | Question to Answer |
|---|---|---|
| **Logical backup** | Exports structures and data into a logical representation such as SQL statements or a dump format that can be reloaded | Which databases, tables, schemas, and objects need to be saved? |
| **Physical backup** | Backs up the physical data files and the information needed to restore them, such as tablespaces and redo logs according to the tool's mechanism | Which files need to be saved to reconstruct data at the server or storage engine level? |
| **Restore** | Brings data from a backup back onto a target server or environment | How do we reload the backup? |
| **Recovery** | Brings restored data to a consistent state and desired target, potentially by applying redo logs or binary logs | Which changes need to be replayed to reach the exact point in time to recover? |

For example: the operations team takes a physical backup at 01:00. Someone accidentally deletes data at 10:15. The operations team restores the 01:00 backup onto a recovery server, then applies the binary logs up to 10:14:59. The restore brings back the baseline data; the recovery replays valid changes after the backup time to reach the state right before the incident.

**Restore is not synonymous with recovery.** A restore may only bring the system back to the time the backup was taken. Recovery may require additional redo logs, binary logs, or appropriate repair steps to achieve a consistent state or reach a specific point in time.

## 2. Logical Backup

A logical backup reads structures and data through MySQL and writes them out as logical statements or records. During a restore, MySQL executes the dump contents to recreate the databases, tables, indexes, data, and objects included in the backup.

Common tools include:

- `mysqldump`: a familiar command-line tool that produces an SQL-formatted dump.
- MySQL Shell dump utilities such as `util.dumpInstance()`, `util.dumpSchemas()`, and `util.dumpTables()`: support scoped dumps, splitting data into chunks, and parallel loading with `util.loadDump()`.
- ETL tools or specialized export tools: suitable for migrating or extracting a subset of data, though you must clearly verify whether they preserve all required structures and metadata.

### 2.1. Creating a Logical Backup with `mysqldump`

Example of dumping an InnoDB database:

~~~bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --default-character-set=utf8mb4 \
  --single-transaction \
  --routines \
  --events \
  --databases shop \
  > shop.sql
~~~

Explanation of options:

- `--password` prompts for the password interactively; avoid writing passwords directly in commands or scripts where they can be exposed in shell history and process lists.
- `--default-character-set=utf8mb4` sets the character set for the dump connection.
- `--single-transaction` creates a consistent snapshot for transactional tables such as InnoDB without needing long-held read locks across the entire dump process.
- `--routines` includes stored procedures and functions in the dump.
- `--events` includes Event Scheduler events in the dump.
- `--databases shop` dumps the database along with the appropriate database creation/selection statements for reloading.

`mysqldump` dumps triggers by default unless an option to skip triggers is used. Even so, you should inspect the dump contents and the list of objects after a restore to ensure application objects were actually carried over.

`--single-transaction` has important limitations:

1. A consistent snapshot only applies to tables that support transactions, typically InnoDB. MyISAM tables or non-transactional storage engines can change during the dump and do not have the same snapshot guarantee.
2. You should not run DDL changes such as `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE` on tables currently being dumped. Coordinate the dump schedule with schema deployments.
3. The dump account must have sufficient privileges to read the data and metadata of the requested objects. Special options or features may require additional privileges depending on the version and configuration.

For large databases, `mysqldump` can produce a huge SQL file and take a long time to restore because the server must re-execute many statements. MySQL Shell dump utilities can split data into chunks and load them in parallel, but you must verify version compatibility, privileges, and dump format before adopting them in operations.

### 2.2. Restoring a Logical Backup

For a dump created with `--databases shop`, you can reload it using the MySQL client:

~~~bash
mysql \
  --host=db-restore.example.net \
  --user=restore_user \
  --password \
  < shop.sql
~~~

If the dump only contains the contents of a single schema and does not include database creation/selection statements, you must create the target database first and specify the schema when loading:

~~~sql
CREATE DATABASE shop_restore
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

~~~bash
mysql --host=db-restore.example.net --user=restore_user \
  --password shop_restore < shop-data.sql
~~~

Do not restore directly onto production before verifying the overwrite scope. A dump may contain `DROP TABLE`, `CREATE TABLE`, `USE`, or statements that modify objects. Read the header and inspect the dump contents, test the restore in an isolated environment, and only then plan the cutover.

### 2.3. Strengths and Limitations of Logical Backup

| Strengths | Limitations |
|---|---|
| Easy to inspect because data and structure are in logical form, usually SQL | Restore can be slow for large data volumes |
| Can dump a single database, specific tables, or a subset of objects | Must ensure views, triggers, routines, events, and related metadata are all included |
| Convenient for migrating between compatible environments or versions | Does not always preserve every physical attribute, layout, or internal server state |
| Can filter or transform data during export/import | Does not automatically replace storing binary logs for point-in-time recovery |

Logical backup is suitable for small and medium databases, schema migrations, selective backups, and cases where content readability/inspection is needed. For large systems, measure actual dump and restore times to determine whether it meets the RTO.

## 3. Physical Backup

A physical backup saves data in the file format used by MySQL and its storage engines. For InnoDB, the backup set typically has to handle tablespaces, metadata, and redo logs to create a set of files that can be recovered consistently. Depending on the tool and method, a backup may cover the entire instance or a physical scope supported by the tool.

Common options:

- **MySQL Enterprise Backup**: the physical backup tool for MySQL Enterprise Edition.
- **Percona XtraBackup**: a widely used third-party tool for InnoDB physical backups; you must check the compatibility matrix with the MySQL version, Percona Server, and data format in use.
- **Cold backup**: cleanly shuts down MySQL and copies all required data files. This is a simpler file-level copy approach, but it causes downtime while being performed.

### 3.1. Hot Backup and Cold Backup

Physical backups can be performed while the server is running or after the server has stopped, depending on the tool:

- **Hot backup** takes place while MySQL continues serving queries. The tool must coordinate with the storage engine and redo logs to handle data pages that change during the copy. Arbitrarily copying the data directory while the server is running cannot be considered a valid hot backup.
- **Cold backup** requires a controlled shutdown of MySQL before copying. Once the server has completely stopped, the data files are no longer being written to by the MySQL process. Make sure all necessary files are copied and keep configuration files, keyrings, and related metadata in a safe place.

A copy of the data directory made manually while MySQL is still running may contain files from different points in time. Data pages, redo logs, and metadata can mismatch; the result may fail to start or be inconsistent. Only use an online copy process if the tool is designed to produce a consistent backup.

### 3.2. General Physical Backup Workflow

Exact command names differ between MySQL Enterprise Backup, Percona XtraBackup, and other tools. However, a physical workflow typically includes these steps:

1. Check the server version, storage engine, destination capacity, and the tool's compatibility matrix.
2. Choose the backup scope, full or incremental type, and storage location.
3. Run the backup tool in a supported mode; the tool records metadata and handles changes that occur during the copy.
4. If required by the tool, run the prepare step to apply redo logs and bring the backup set to a consistent, restorable state.
5. Check the exit code, logs, metadata, size, and integrity of the backup set.
6. Transfer the backup to storage independent of the source server and protect it with encryption and appropriate access permissions.
7. Periodically test restoring onto another server or recovery environment.

Do not use physical commands from one tool for another. For example, Percona XtraBackup's backup, prepare, and copy-back syntax differs from MySQL Enterprise Backup's restore workflow. Follow the exact documentation for the tool version deployed.

### 3.3. Restoring a Physical Backup

A typical physical restore workflow includes these steps:

1. Prepare a target server that is compatible in version, architecture, configuration, and required components.
2. Stop MySQL on the target server before replacing the data directory.
3. Place the prepared backup set into the location required by the tool; ensure file ownership and permissions match the account running MySQL.
4. Restore required auxiliary components such as keyrings or encryption keys, corresponding configuration files, and files outside the backup scope.
5. Start MySQL, monitor the error log, and let InnoDB complete crash recovery if needed.
6. Verify databases, tables, objects, privileges, and application state before shifting traffic.

Physical restore is typically well-suited when fast recovery of a large instance or dataset is needed. It can depend tightly on the MySQL version, file format, configuration, and the tool that created the backup. Restoring a single database may require standing up the backup on a temporary instance and then logically exporting the needed portion to the target system.

### 3.4. Components Easily Overlooked

The data directory does not necessarily contain everything needed to operate the system again. Inventory these separately:

- Server configuration, such as configuration files, InnoDB parameters, and data and log paths.
- Keyring or key management system if the database uses encrypted tablespaces or data. Having the data files without the corresponding keys can still render the data unreadable.
- Binary logs and metadata identifying the log position or GTID at the time of the backup.
- TLS certificates, authentication configuration, plugins, components, and items outside the data directory.
- Accounts, roles, grants, and identity information required for applications to connect.

Actual scope depends on the tool. Read the manifest and tool documentation to know exactly what was backed up; do not assume a physical backup automatically includes the entire operational configuration.

## 4. Comparing Logical Backup and Physical Backup

| Criterion | Logical Backup | Physical Backup |
|---|---|---|
| Storage unit | Logical structures and data | Data files, tablespaces, and related physical information |
| Restore method | Execute dump or load chunks | Place backup files into the appropriate location following the tool's workflow |
| Speed with large data | Usually slower due to reading/exporting and re-executing data | Usually faster as backup and restore operate at the file level |
| Selectivity | Convenient for specific schemas, tables, or objects | Usually targets an instance or physical scope supported by the tool |
| Portability | Usually more flexible across compatible environments | Depends on version, storage engine, format, and tool |
| Content inspection | Dump can be read and reviewed | Requires inspection tools, metadata, and test restores |
| Operational requirements | Requires sufficient privileges to read and load objects | Requires understanding the data directory, engine, redo logs, file permissions, and auxiliary components |

No single backup type fits every scenario. A practical strategy often combines physical backups for fast recovery of large systems, logical backups for selective recovery or data migration, and binary logs for recovering to a desired point in time.

## 5. Recovery and Point-in-Time Recovery (PITR)

A full backup only reflects the data at the moment the backup was created. If an incident occurs afterward, valid transactions that occurred between the backup time and the incident time may not yet be in the backup. The MySQL binary log (binlog) records data and structure change events according to server configuration, allowing those changes to be replayed after a restore.

**Point-in-time recovery (PITR)** is recovering data to a specific point in time, typically right before an erroneous operation. Basic workflow:

1. Select the most recent verified full backup and confirm its binary log or GTID metadata at the time of the backup.
2. Restore the full backup onto a recovery server.
3. Identify the continuous chain of binary logs starting from the position after the backup.
4. Use `mysqlbinlog` to read and replay events up to the target time or the position right before the incident.
5. Verify the data and application; only shift traffic after confirming the results.

Illustrative example of inspecting binary logs:

~~~bash
mysqlbinlog --start-datetime="2026-11-19 01:00:00" \
            --stop-datetime="2026-11-19 10:14:59" \
            binlog.000120 binlog.000121 > replay.sql
~~~

After inspecting the event scope in `replay.sql`, it can be replayed onto the recovery server:

~~~bash
mysql --host=db-restore.example.net \
      --user=recovery_user --password < replay.sql
~~~

This is an example of limiting by time. In a real workflow, you must use the exact file, start position, or GTID recorded in the backup metadata; specify all consecutive binlog files in order; and verify the time zone, incident timestamp, and timestamp precision. When high accuracy is needed, limiting by log position or GTID is usually more reliable than relying solely on timestamps.

Do not blindly replay the entire binlog. If the incident was a `DROP TABLE` statement at 10:15, identify the event boundary and stop before that operation. You can restore onto a separate instance, verify the data to keep, and then decide how to bring the data back to production.

### 5.1. Prerequisites for PITR to Work

- Binary logging must be enabled before the changes that need to be recovered occur.
- Binlogs must be retained long enough and copied to a location independent of the source server.
- You must know the backup's replay starting point, via file/position or GTID metadata.
- The log chain must be continuous, complete, and free of missing or corrupted files.
- You must precisely control the stop point so the erroneous operation is not replayed.

You can check binary logging and the log list using:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW BINARY LOGS;
~~~

Statement names and how metadata is displayed may vary by MySQL version. Use the commands supported by your server version and store log position information alongside the backup. If you only store full backups without keeping binary logs, recovery capability is generally limited to the point in time of those backups.

## 6. Designing a Backup Strategy Based on RPO and RTO

Two metrics help turn business requirements into a concrete backup schedule:

- **RPO (Recovery Point Objective)**: the maximum amount of data loss an organization accepts, usually expressed as a time interval. An RPO of 15 minutes means the goal is to lose no more than 15 minutes of data.
- **RTO (Recovery Time Objective)**: the maximum acceptable time to restore service. An RTO of 1 hour means service must be brought back within one hour.

For example, a retail application sets an RPO of 5 minutes and an RTO of 30 minutes. Taking only a nightly logical dump may fail to meet the RPO, and restoring the entire dump may exceed the RTO. You may need periodic physical full backups, incremental backups if supported by the tool, and continuous binary log shipping to an independent system. Afterward, you must run drills to measure actual restore and PITR times.

A reference schedule for a system requiring strong recoverability:

| Component | Reference Schedule | Purpose |
|---|---|---|
| Physical full backup | Daily or during an appropriate window | Create a baseline recovery point for the entire instance |
| Physical incremental backup | Periodically throughout the day, if supported by the tool | Reduce the amount of data backed up each time |
| Binary log | Collected and shipped off-site continuously | PITR and reducing the data loss window |
| Logical backup | Scheduled or before/after major changes | Selective recovery, inspection, and data migration |
| Restore drill | Periodically and after major process changes | Measure RTO, verify backups, and validate runbooks |

This schedule is only a starting point. Adjust it based on data volume, rate of data change, storage costs, maintenance windows, regulatory requirements, and drill results.

### 6.1. Backup Storage and Protection Rules

A good strategy must protect both the backups and access to them:

1. Keep multiple copies across different failure domains; do not keep the only copy on the same server or storage as the source data.
2. Use encryption in transit and at rest, manage keys separately, and control who has decryption permissions.
3. Restrict read, write, and delete permissions on backups; consider immutable storage or protection against accidental deletion.
4. Monitor backup size, completion time, exit codes, tool errors, and age of the most recent backup.
5. Set appropriate retention, ensuring the required binary logs remain available across the entire intended PITR window.
6. Back up and test restoring keyrings, configuration files, and credentials needed alongside the data workflow.

Replication increases availability and offloads reads, but it does not replace backups. An accidental delete or maliciously encrypted data can replicate to replicas; independent backups and PITR capability remain essential.

## 7. Incident Recovery Workflow

Suppose the application detects that order data was accidentally deleted at 10:15. There is a full backup from 01:00 and binary logs are stored continuously. The workflow can be carried out as follows:

1. **Contain the incident:** stop or restrict jobs that might continue writing bad data; record the detection time and the time window during which the erroneous operation could have occurred.
2. **Preserve evidence:** keep copies of binlogs, application logs, and relevant operational data; avoid overwriting files needed for investigation.
3. **Select the recovery point:** identify the most recent good backup, check metadata, and verify the binlog chain from the backup point up to before the incident.
4. **Restore into an isolated environment:** do not rush to overwrite production. Stand up a compatible recovery machine and verify that it starts cleanly.
5. **Recover to the target point:** replay logs up to right before the erroneous event, or to an already confirmed safe point.
6. **Verify data:** check orders, application-level logical foreign keys, record counts, total amounts, and related business invariants.
7. **Bring data back into service:** choose an appropriate cutover method, such as restoring the whole instance or extracting the needed tables/records from the recovery machine.
8. **Monitor post-recovery:** watch for MySQL errors, latency, connections, background jobs, and data correctness after reopening traffic.
9. **Conduct a postmortem:** document actual timings, root cause, gaps in backup coverage, and update the runbook.

Restoring partial data into a live production database can be complex due to related tables and newly arrived transactions. Clearly determine primary keys, data relationships, load order, and conflict-handling rules before merging data from the recovery machine.

## 8. Verifying That a Backup Is Usable

A "backup completed" message or a large file size does not prove it can be restored. A backup is only trustworthy once it can be restored and its results verified.

Verification checklist:

- [ ] The tool completed successfully; logs contain no unresolved errors or warnings.
- [ ] The backup has metadata, manifest, checksums, or integrity verification appropriate to the tool.
- [ ] Backup files have been transferred to independent storage and are readable.
- [ ] Binary logs, GTIDs, or log positions required for PITR are retained along with reference details.
- [ ] Required encryption keys, keyrings, configurations, and tool versions are safeguarded.
- [ ] A test restore in an isolated environment completes within the target time.
- [ ] Required databases, tables, indexes, routines, triggers, events, and privileges are present after restore.
- [ ] The application can execute critical business flows on the recovered data.
- [ ] Operators know where to retrieve backups, how to obtain keys, and how to execute each step in the runbook.

After a restore, you can perform quick checks with SQL:

~~~sql
SHOW DATABASES;

USE shop;
SHOW FULL TABLES;

SELECT COUNT(*) AS order_count
FROM orders;

SHOW TRIGGERS FROM shop;
SHOW EVENTS FROM shop;
~~~

These queries are only an initial check. Correct row counts do not guarantee correct data; you also need checksum comparisons, business aggregations, cross-table consistency checks, and application testing. A successful test restore must also be repeated periodically because configurations, versions, and operational procedures can change.

## 9. Self-Check

1. What type of backup is a `mysqldump` file containing SQL statements? Why?
2. Why should you not use copying a running data directory as a physical hot backup?
3. Does `--single-transaction` guarantee a consistent snapshot for MyISAM tables? What must you be careful of with DDL during a dump?
4. When restoring a physical backup, why must you pay attention to the MySQL version, file ownership, and keyring?
5. If you only restore a full backup from 01:00 without replaying binary logs, is data after 01:00 recovered?
6. To recover right before an accidental delete at 10:15, what information do you need about the backup and binlogs?
7. Why can a replica not replace an independent backup?
8. Propose a backup schedule that meets an RPO of 15 minutes and an RTO of 1 hour, and describe how to run a drill to prove the schedule meets the requirements.

When answering, clearly distinguish the baseline backup, the action of putting the backup back onto a server, and the log replay step to reach the recovery point. Use restore drill results along with actual timing metrics to evaluate RPO and RTO, rather than relying solely on the backup schedule.
