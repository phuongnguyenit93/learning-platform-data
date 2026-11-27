# Routines, Triggers, Events, Users/Grants, and Components to Back Up

A MySQL backup is only valuable when it can restore both the data and the components that make the application work properly. Beyond tables and rows, a system often depends on stored procedures, functions, triggers, events, views, accounts, roles, access privileges, server configuration, encryption keys, and binary logs. Missing any one of these components can leave a newly restored server where the application still fails, scheduled jobs do not run, or access privileges change unexpectedly.

This lesson focuses on MySQL 8.0 and later, compatible with MySQL 8.4. Examples use `mysqldump`, administrative SQL, and logical recovery workflows. For physical backups, use a tool matching your server version and storage engine, while preserving the accompanying encryption and configuration components.

## Objectives

After this lesson, you will be able to:

- Distinguish the types of objects required in a MySQL backup.
- Choose `mysqldump` options to capture routines, triggers, and events.
- Back up account definitions, grants, roles, and default roles separately.
- Identify dependencies such as `DEFINER`, `SQL SECURITY`, the event scheduler, plugins, and keyrings.
- Establish a restore sequence, verify completeness, and prepare binary logs for point-in-time recovery.

## 1. What Must a MySQL Backup Contain?

Think of a backup as a set of interconnected layers. Each layer has a different backup and restore method.

| Group | Components to Save | Risk if Missing |
|---|---|---|
| Schema and data | Databases, tables, columns, data types, indexes, keys, constraints, partitions, data | Cannot reconstruct data state and application structure |
| Logic objects | Views, procedures, functions, triggers, events | Loss of business rules, automated jobs, or access logic |
| Identity and security | Users, hosts, authentication plugins, roles, privileges, default roles, TLS requirements, and account lock state | Users cannot log in or receive incorrect privileges |
| Recovery state | Binary logs, GTIDs, log position at backup time, replication metadata | Cannot replay changes accurately to the target recovery time |
| Server configuration | Config files, `server_id`, `event_scheduler`, binlog settings, plugins/components, charsets, and related parameters | Restored server behaves differently from source server |
| Secrets and external dependencies | Keyrings, encryption keys, TLS certificates, UDF/plugin libraries, scripts called by events | Objects exist but cannot decrypt or execute |

Not every component lives in the same dump file. A logical dump typically stores SQL structures and data; accounts, configuration, binary logs, and encryption keys must be inventoried via dedicated procedures or captured with a full-instance backup tool that supports them.

## 2. Stored Procedures and Functions

Stored procedures and stored functions hold SQL logic inside the database. They can be called directly by the application, invoked by triggers, or executed on a schedule by events. Therefore, dumping only tables and data is insufficient if the application relies on stored programs.

With `mysqldump`, enable `--routines` to export procedures and functions:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --databases sales_db \
  > sales_db.sql
```

`--routines` is not enabled by default in `mysqldump`. If omitted, the dump may contain tables and data while missing procedures/functions. When inspecting a specific routine, you can run:

```sql
SHOW CREATE PROCEDURE sales_db.recalculate_order_total;
SHOW CREATE FUNCTION sales_db.normalize_phone;
```

Besides the routine body, pay attention to attributes affecting execution:

- `DEFINER`: the account the routine uses as its defining context.
- `SQL SECURITY DEFINER` or `SQL SECURITY INVOKER`: determines the privilege context at runtime.
- `SQL_MODE`: the SQL mode stored with the routine, which can affect how statements are interpreted.
- Character set and collation of parameters, return value, and routine body.

When restoring a routine with `SQL SECURITY DEFINER`, the definer account must exist and hold the required privileges. If the definer does not exist or its privileges changed, the routine may be created yet fail at runtime, or object creation may raise warnings/errors depending on the statement and version. Therefore, inventory definers and prepare accounts before recreating stored objects.

## 3. Triggers

A trigger is attached to a table and runs automatically on `INSERT`, `UPDATE`, or `DELETE` events, at `BEFORE` or `AFTER` timing. Triggers often hold data validation rules, audit logging, or updates to related tables. Losing triggers can cause post-recovery data to stop obeying legacy rules.

`mysqldump` exports triggers by default. You can explicitly pass `--triggers` in the command to make intent clear and avoid confusion when reading backup scripts:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --databases sales_db \
  > sales_db.sql
```

If `--skip-triggers` is used, triggers are excluded from the dump. Do not use that option if triggers are part of application logic.

Inspect trigger definitions with:

```sql
SHOW CREATE TRIGGER sales_db.orders_audit_bu;

SELECT TRIGGER_SCHEMA,
       TRIGGER_NAME,
       EVENT_MANIPULATION,
       EVENT_OBJECT_TABLE,
       ACTION_TIMING,
       DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'sales_db';
```

Triggers can depend on routines, audit tables, definer accounts, or execution order relative to other triggers on the same table. During manual recovery, restore dependent tables and definer accounts first. If loading data with `INSERT` statements after triggers have already been created, triggers may fire on every row and generate extra audit records or side effects. For large data loads, determine the proper trigger-creation order and test the impact before bringing the system into service.

## 4. Events and the Event Scheduler

An event is a scheduled SQL task executed by MySQL, such as period closing, purging old data, or daily metric aggregation. An event definition includes schedule, start/end times, enabled/disabled state (`ENABLE`/`DISABLE` in DDL; `ENABLED`/`DISABLED` when viewed through `INFORMATION_SCHEMA.EVENTS`), definer, and execution statement.

`mysqldump` does not export events by default. You must add `--events`:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --databases sales_db \
  > sales_db.sql
```

Inspect events and scheduler configuration:

```sql
SHOW CREATE EVENT sales_db.purge_expired_sessions;

SELECT EVENT_SCHEMA,
       EVENT_NAME,
       STATUS,
       DEFINER,
       TIME_ZONE,
       EVENT_DEFINITION
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'sales_db';

SHOW VARIABLES LIKE 'event_scheduler';
```

There are two separate concepts:

- **Event definitions** are stored in the database and exported with `--events`.
- **Event scheduler** is the server component that decides whether enabled events actually execute. The scheduler state is a server configuration setting and is not replaced merely by dumping schemas.

When restoring or running drills on a test server, disable the scheduler before loading data and inspecting events:

```sql
SET GLOBAL event_scheduler = OFF;
```

Only after verifying definers, schedules, time zones, event statuses, and dependencies should you enable the scheduler according to environment policy:

```sql
SET GLOBAL event_scheduler = ON;
```

Changing a global variable requires appropriate administrative privileges; if the variable is set to `DISABLED` at startup, it cannot be enabled via `SET GLOBAL`. Check the configuration file and operational plan before making changes. In production, avoid having two servers simultaneously run business events after a clone or restore if doing so could send duplicate emails, issue payments, or double-process data.

## 5. Users, Roles, and Access Privileges

A database dump does not equal a complete backup of identities and access privileges. A MySQL account is identified by both user and host, for example `'app_api'@'10.%'`; `'app_api'@'localhost'` is a distinct account and may hold different privileges.

Information to inventory for each account includes:

- User name and host.
- Authentication plugin and credential attributes exported by MySQL via administrative statements.
- TLS requirements, resource limits, password expiration, and account lock state.
- Global, database, table, column, routine, and proxy privileges if any.
- Granted roles, nested roles, `WITH ADMIN OPTION`, and default roles.
- Server-wide roles such as `mandatory_roles`, along with the `activate_all_roles_on_login` setting.

### 5.1. Exporting Account Definitions

`SHOW CREATE USER` returns the account creation statement along with authentication and security attributes managed by MySQL:

```sql
SHOW CREATE USER 'app_api'@'10.%';
```

The output may contain sensitive authentication strings. Store exported files in an encrypted area, restrict read permissions, and never paste them into tickets, logs, or public source repositories.

### 5.2. Exporting Privileges and Granted Roles

`SHOW GRANTS` returns statements representing the privileges and roles granted to an account:

```sql
SHOW GRANTS FOR 'app_api'@'10.%';
```

If roles are involved, ensure those roles are also created and granted privileges before applying grants to the account. You can inspect effective privileges expanded from a specific role using `SHOW GRANTS ... USING`:

```sql
SHOW GRANTS FOR 'app_api'@'10.%'
USING 'r_app_runtime'@'%';
```

### 5.3. Saving Default Roles and Server-Wide Role Settings

Granting a role and setting default roles are two separate operations. Save each account's `SET DEFAULT ROLE` statement as well. On MySQL 8.0, you can inventory default roles via the `mysql.default_roles` system table:

```sql
SELECT USER,
       HOST,
       DEFAULT_ROLE_USER,
       DEFAULT_ROLE_HOST
FROM mysql.default_roles
ORDER BY USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST;

SHOW VARIABLES LIKE 'activate_all_roles_on_login';
SHOW VARIABLES LIKE 'mandatory_roles';
```

Tables in the `mysql` schema are internal implementation details; prefer administrative interfaces such as `SHOW CREATE USER`, `SHOW GRANTS`, and `CREATE USER`, `CREATE ROLE`, `GRANT`, and `SET DEFAULT ROLE` statements to recreate policies. Use system table queries as a controlled inventory check—do not modify grant tables directly.

A manual export workflow for an account might record the following in a secured file:

```text
SHOW CREATE USER 'app_api'@'10.%';
SHOW GRANTS FOR 'app_api'@'10.%';
SET DEFAULT ROLE 'r_app_runtime'@'%' TO 'app_api'@'10.%';
```

The two `SHOW` lines are inspection statements for the administrator to save their output. The `SET DEFAULT ROLE` line is a sample restore statement; substitute actual inventoried roles and accounts. For many accounts and roles, automate export/restore with a tested workflow or use MySQL Shell dump utilities that support exporting users, rather than copying grants by hand.

### 5.4. Restoring Accounts in Order

A safe order is typically:

1. Create required roles.
2. Create users using statements equivalent to `SHOW CREATE USER` output.
3. Grant object privileges to roles.
4. Grant roles to other roles and to users.
5. Configure default roles.
6. Verify `SHOW GRANTS`, `CURRENT_ROLE()` on a test login, and representative operations.

If objects have a `DEFINER`, create the necessary definer accounts before restoring procedures, functions, views, triggers, and events. Do not grant overly broad administrative privileges just to make a restore pass; determine the exact privileges each definer needs.

## 6. Components Outside the Schema to Back Up

### 6.1. Server Configuration

Save configuration files and key parameters such as `my.cnf` or equivalent config files, `server_id`, `log_bin`, `binlog_format`, `gtid_mode`, `event_scheduler`, TLS settings, plugins/components, and InnoDB parameters. Record the MySQL version, plugin versions, and source/replica topology so a compatible environment can be rebuilt.

Do not copy a configuration file verbatim from one server to another without reviewing identifiers and paths. For instance, `server_id`, data directory, socket, log paths, and replication settings must fit the target server.

### 6.2. Keyrings, Encryption Keys, and Certificates

If tablespace, redo log, or backup encryption is used, preserve the keyring and corresponding keys. Encrypted data files without the matching keys may be unrecoverable. TLS certificates and private keys must also be stored securely if required by applications or replication.

Encryption keys and data backup files must have independent access controls. Store a copy of keys in a separately protected location with an access-recovery procedure and periodic decryption checks. Never place keys and the sole backup in the same location sharing the same failure risk.

### 6.3. Plugins, Components, and UDFs

A routine or event may invoke a user-defined function (UDF), plugin, or component. An SQL dump only holds SQL definitions; it does not package binary libraries, configuration files, or OS dependencies. Record names, versions, installation sources, checksums, and reinstall instructions for these external components.

### 6.4. Binary Logs and Replication Metadata

Binary logs record committed changes on the server and can be replayed after a full backup to recover to a point in time. If point-in-time recovery (PITR) is needed, binary logs must be retained continuously from the backup checkpoint, alongside recording the log position or GTID corresponding to the backup.

Useful inspection commands:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'gtid_mode';
SHOW BINARY LOGS;
SELECT @@GLOBAL.gtid_executed;
```

`SHOW BINARY LOGS` requires appropriate privileges. Incorporate binary log rotation, off-host archiving, and purge policies into the backup workflow. Never purge logs before off-host copies are verified and the required PITR retention window has been met.

During recovery, use `mysqlbinlog` to read logs from the exact saved checkpoint and replay up to the target time. Cross-check GTIDs or log positions to avoid skipping or replaying unintended transactions. Never arbitrarily replay binary logs onto a server that already contains new data.

## 7. Creating a Logical Backup with `mysqldump`

The following example backs up an application database along with routines, triggers, and events:

```bash
mysqldump \
  --host=db01.example.internal \
  --user=backup_operator \
  --password \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --hex-blob \
  --databases sales_db \
  > sales_db_full.sql
```

`--password` without a value prompts interactively for the password. In automation, use a proper credential mechanism such as a login path or secret manager; avoid putting passwords directly on the command line, in scripts, or in shell history.

| Option | Effect |
|---|---|
| `--single-transaction` | Creates a consistent snapshot for transactional tables such as InnoDB without locking all tables during the dump |
| `--routines` | Exports procedures and functions |
| `--triggers` | Exports triggers; this is the default in `mysqldump`, though specifying it explicitly makes the command easier to audit |
| `--events` | Exports events; must be specified explicitly |
| `--hex-blob` | Represents binary data in hexadecimal format in the dump |
| `--databases sales_db` | Exports the specified database, including database creation/selection statements |

`--single-transaction` does not create a consistent snapshot for tables using non-transactional engines like MyISAM. Nor does it protect the dump against concurrent DDL changes such as `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE`. During the backup window, maintain a process to control schema changes. If the database contains non-transactional tables or requires a consistent snapshot across multiple engines, select an appropriate locking or backup method and evaluate downtime impact.

To dump multiple databases, use `--databases db1 db2`. `--all-databases` dumps all databases, including the `mysql` system schema. Having the `mysql` schema in a dump does not mean you should restore system tables directly into another version. Those tables are tied to the server's version and internal structure; for migrations, recreate users and grants via exported administrative statements and follow a supported upgrade/migration procedure.

## 8. Logical Backup vs. Physical Backup

| Criterion | Logical Backup | Physical Backup |
|---|---|---|
| Storage format | SQL statements and reloadable data | Data files, tablespaces, redo logs, and related files per tool |
| Example tools | `mysqldump`, MySQL Shell dump utilities | MySQL Enterprise Backup, Percona XtraBackup, or compatible tools |
| Scope | Can select databases, tables, and objects | Usually suited for backing up/restoring an entire instance or supported physical scope |
| Flexibility | Easy to move data and filter objects | Usually restores faster for large data, tightly coupled to version and format |
| Dependencies to keep | Users/grants, configuration, binary logs, and keys still handled separately | Requires keyrings, configuration, binary logs, and corresponding prepare/restore workflow |

An instance-wide physical backup typically includes system data, so it can carry the source server's grant tables. However, it should not be treated as a mechanism for migrating users across different MySQL versions. When restoring onto another server or upgrading versions, follow compatibility guidelines for the tool and target version, then verify users, roles, authentication plugins, and privileges.

MySQL Shell dump utilities are another logical backup option. When choosing a tool, verify version support, schema/instance scope, and whether user export options exist. Do not assume every dump tool automatically preserves users, grants, default roles, or server configuration files.

## 9. Recommended Restore Sequence

A controlled restore sequence helps avoid objects missing definers, events firing prematurely, or misapplied privileges:

1. **Prepare target server:** install a compatible version, configure storage, charsets, plugins/components, TLS, and keyring. Verify decryption keys before loading data.
2. **Disable automated tasks:** keep `event_scheduler` set to `OFF` in restore/drill environments; isolate the server from integrations with side effects.
3. **Restore identities:** create required users and roles, including `DEFINER` accounts. Grant the minimum privileges needed for the restore process.
4. **Restore schemas and data:** load databases, tables, views, and data per plan; confirm charsets, collations, indexes, constraints, and partitions.
5. **Restore stored objects:** verify procedures, functions, triggers, and events; ensure `DEFINER`, `SQL SECURITY`, SQL mode, and dependencies are correct.
6. **Restore privileges:** apply grants, role memberships, default roles, and server-wide security settings; test representative accounts.
7. **Point-in-time recovery:** if needed, replay binary logs from the backup checkpoint to the target time using `mysqlbinlog` per the verified plan.
8. **Pre-cutover verification:** confirm data, objects, privileges, events, logs, and application health; only enable the scheduler and route traffic once approved.

Exact ordering may vary by backup tool. For instance, a self-contained dump may create databases and objects in its own order. Read and test the actual restore procedure in an isolated environment before applying it to production.

## 10. Completeness Checklist

After creating a backup, do not merely check whether the file exists. Verify every object group:

| Check | How to Verify |
|---|---|
| Tables and data | Verify schema/table list, representative row counts, sizes, and checksums if available |
| Routines | Cross-check `information_schema.ROUTINES` or `SHOW CREATE PROCEDURE/FUNCTION` |
| Triggers | Cross-check `information_schema.TRIGGERS`, timing, event manipulation, and definer |
| Events | Cross-check `information_schema.EVENTS`, status, schedule, time zone, and definer |
| Users/grants | Cross-check user/host list, `SHOW CREATE USER`, `SHOW GRANTS`, and default roles |
| Configuration | Record version, config files, key variables, plugins, and topology |
| Keys and certificates | Confirm copies are accessible, decryptable, and protected |
| PITR | Confirm continuous binary logs from backup checkpoint and a starting position/GTID for replay |
| Recoverability | Perform a test restore on a separate host, run data checks, and test application flows |

A backup is only considered trustworthy after a test restore. Store a manifest alongside the backup containing creation timestamp, MySQL version, database list, dump options, binary log/GTID position, checksum, storage location, and results of the latest restore test. Track both RPO (maximum acceptable data loss) and RTO (maximum time to restore service).

## 11. Common Mistakes

- **Missing `--routines`:** tables and data are present, but procedures/functions vanish. Add the option and verify routine counts after restore.
- **Missing `--events`:** events are not exported, so scheduled tasks never run. Check `information_schema.EVENTS` and `event_scheduler`.
- **Disabling triggers unintentionally:** dump used `--skip-triggers`, dropping audit or validation rules. Verify actual options and trigger counts.
- **Backing up only application schemas:** users, roles, and grants are not recreated. Export identities and privileges separately, or use a tool confirmed to support user export.
- **Non-existent definer:** routines, views, triggers, or events fail at runtime. Create exact definer accounts and grants before enabling the application.
- **Events firing immediately after restore:** events may send notifications or modify data during verification. Disable the scheduler, review events, and only then re-enable it.
- **Losing keyring or certificates:** encrypted data files may be unreadable or TLS connections may fail. Test key recovery in an isolated environment.
- **Not retaining binary logs:** recovery is limited to the full backup checkpoint, unable to replay transactions up to the latest moment.
- **Trusting a dump file without a test restore:** the file could be truncated, lack read permissions, have charset issues, or miss dependencies. Schedule restore drills and measure actual timings.

## 12. Self-Check Exercises

1. A `mysqldump` command includes `--triggers` but omits `--routines` and `--events`. Which types of objects risk being missing?
2. Why should `SHOW CREATE USER` and `SHOW GRANTS` be saved alongside an application schema dump?
3. An event was dumped and restored successfully, yet it does not run. List the items you should inspect.
4. Why should `DEFINER` accounts be created before restoring procedures, triggers, or events?
5. A server uses InnoDB and needs recovery to 10:35 AM after a 02:00 AM backup. Besides the full backup, what else must be saved and what metadata must be recorded?
6. When cloning production to a test environment, why should you disable the event scheduler and review users, plugins, certificates, and external integrations?

**Answer Hints:** (1) Procedures/functions and events risk being missing; triggers are still exported because `--triggers` is present. (2) Dumping an application schema does not guarantee exporting users, authentication methods, roles, or all privileges; those two administrative statements help recreate identities and access policies. (3) Check whether the event exists and is `ENABLED`, whether the scheduler is `ON`, time/time zone settings, the definer, and the definer's privileges. (4) Stored objects may run under the definer's context; a missing account or insufficient privileges causes runtime errors. (5) Continuous binary logs from the backup checkpoint, plus GTID or log position to replay accurately up to 10:35. (6) To prevent automated tasks from causing side effects, while ensuring the target environment has the right identities, dependencies, and secrets.

## References

- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual: mysqldump and Stored Programs](https://dev.mysql.com/doc/refman/8.4/en/mysqldump-stored-programs.html)
- [MySQL 8.4 Reference Manual: SHOW CREATE USER](https://dev.mysql.com/doc/refman/8.4/en/show-create-user.html)
- [MySQL 8.4 Reference Manual: SHOW GRANTS](https://dev.mysql.com/doc/refman/8.4/en/show-grants.html)
- [MySQL 8.4 Reference Manual: Event Scheduler Configuration](https://dev.mysql.com/doc/refman/8.4/en/events-configuration.html)
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html)
- [MySQL 8.4 Reference Manual: Backup and Recovery](https://dev.mysql.com/doc/refman/8.4/en/backup-and-recovery.html)
