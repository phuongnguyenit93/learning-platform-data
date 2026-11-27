# Choosing Migration Scope: Data, Schema, Accounts, and Configuration

This lesson belongs to the **DATABASE_MYSQL** module. When migrating MySQL to a new server, upgrading versions, separating an application from a shared database, or standing up a test environment, the first step is to determine exactly what needs to be moved. A migration can include data, schema, accounts and privileges, server configuration, or the entire instance. Each group has different export, import, verification, and dependency requirements.

Choosing the wrong scope typically leads to two types of incidents: missing components that prevent the application from working after cutover, or carrying over too much legacy state that leaves the target server with unsuitable configuration, access privileges, and data. Therefore, you should inventory objects and dependencies before selecting tools.

## 1. The Four Primary Migration Scopes

| Scope | Includes | Example Use Cases | Common Approaches |
|---|---|---|---|
| **Schema** | Databases, tables, views, indexes, constraints, triggers, routines, events | Creating a new database structure or migrating to a different version | Logical schema dump, migration scripts, MySQL Shell |
| **Data** | Table rows, either in full or a selected subset | Migrating business data, loading historical data, syncing specific tables | Logical dump, `LOAD DATA`, replication, ETL tools |
| **Accounts and privileges** | Users, roles, authentication plugins, grants, default roles, account attributes | Allowing applications and operators to access the new server | `SHOW CREATE USER`, `SHOW GRANTS`, administrative scripts |
| **Configuration and operational components** | System variables, configuration files, plugins/components, TLS, keyring, paths, backup and replication schedules | Standing up a replacement server or migrating environments | Inventory and selectively apply configuration, deploy supporting components |

A full-instance migration typically requires all four scopes. Moving a single database for one service may only need the schema, data, and associated accounts. Regardless of the scope, identify dependencies outside the database such as secrets, certificates, DNS, applications, background jobs, and monitoring tools.

## 2. Surveying Source and Target Before Choosing Scope

Before exporting, collect information from both the source and target servers. Basic commands:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution,
       @@hostname AS server_name,
       @@server_id AS server_id,
       @@server_uuid AS server_uuid;

SHOW DATABASES;
SHOW ENGINES;
SHOW PLUGINS;
SHOW GLOBAL VARIABLES;
```

For each schema to migrate, list tables, views, and other objects:

```sql
SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS,
       DATA_LENGTH, INDEX_LENGTH
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_TYPE, TABLE_NAME;

SELECT ROUTINE_NAME, ROUTINE_TYPE, DEFINER, SQL_MODE
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop';

SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_TIMING,
       EVENT_MANIPULATION, DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'shop';

SELECT EVENT_NAME, STATUS, DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'shop';
```

For InnoDB, `TABLE_ROWS` is typically an estimate and should not be used as the sole proof that all data has been transferred. `information_schema` queries may also be restricted by the privileges of the inspection account.

Check compatibility points:

- MySQL version and distribution branch on source and target.
- Storage engines, charset, collation, and `sql_mode`.
- Data volume, write rate, number of tables, and dump/restore duration.
- Views, triggers, procedures, functions, events, and objects with `DEFINER`.
- Foreign keys, dependency order between tables, and tables referenced outside the scope.
- Authentication plugins, plugins/components, TLS, keyring, and encrypted data.
- Binary logs, GTIDs, replication channels, and existing backup jobs.

Not all MySQL versions can directly exchange every dump format or physical backup. Check the compatibility matrix, document differences, and test importing on an equivalent target machine before scheduling cutover.

## 3. Selecting the Migration Level

Requirements can be divided into four levels, from smallest to largest:

1. **Data only:** the target schema already exists and is compatible; only load or sync rows.
2. **Schema and data of a single database:** recreate objects and load data for one application.
3. **Multiple databases and related accounts:** migrate multiple applications, roles, and required privileges.
4. **Entire instance or entire environment:** data, configuration, accounts, plugins, keys, replication, and operational procedures.

Choose the smallest level that still satisfies the objective. If you only need one schema, avoid copying system databases or unrelated server configuration. Conversely, if the application depends on the event scheduler, routines, user-defined functions, or `DEFINER` accounts, a dump containing only tables and data is insufficient.

### 3.1. Scope Selection Matrix by Scenario

| Scenario | Scopes to Consider | Questions to Answer |
|---|---|---|
| Creating a test environment from production | Schema, anonymized data, test accounts, environment-specific config | Is there any personal data or secret to strip out? Should data volume be reduced? |
| Splitting an application out of a shared database | Schema, related tables, routines/views/triggers/events, users and grants | Are there queries or foreign keys referencing other schemas? |
| Upgrading MySQL | Schema, data, users/roles, compatible config, plugins | Have syntax, collations, auth plugins, or config variables changed? |
| Moving to a new server on the same version | Data, schema, accounts, reviewed config, TLS/keyring | Use logical or physical backup? Preserve binlog/GTID to sync subsequent changes? |
| Recovering a dropped table | Data and possibly table schema, along with related dependencies | Can you restore to a temporary instance and extract the table? |
| Building a new replica | Data snapshot, file/position or GTID metadata, replication config and user | Which exact starting point does the snapshot correspond to? |

## 4. Migrating the Schema

A schema describes the structure and behavior of a database. A complete schema may include:

- Databases and charset/collation attributes.
- Tables, columns, data types, defaults, generated columns, and indexes.
- Primary keys, unique keys, foreign keys, check constraints.
- Views and `DEFINER` definitions.
- Triggers.
- Stored procedures and functions.
- Event Scheduler events.

Do not verify only that the tables exist. Applications may depend on views, routines, triggers, or events to carry out business logic.

### 4.1. Exporting Schema with `mysqldump`

Example of exporting the structure of database `shop` without row data:

```bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --no-data \
  --routines \
  --events \
  --triggers \
  --databases shop \
  > shop-schema.sql
```

`--no-data` omits row data. The dump can still include database, table, view, and selected object definitions. Triggers are dumped by default in `mysqldump`; specifying `--triggers` explicitly clarifies intent. `--routines` and `--events` instruct it to include procedures/functions and events in the dump.

Before importing, inspect `CREATE DATABASE`, `USE`, `DEFINER`, charset, collation, and statements that could overwrite existing objects. If the target already has a schema, decide explicitly whether to create a new schema, adjust names, or apply incremental migrations.

### 4.2. Exporting Schema via Migration Scripts

For actively developed applications, schemas can be managed with versioned migration scripts instead of re-dumping the entire structure for every deployment. A migration should:

1. Have a unique version identifier or name.
2. Express a specific change, such as adding a column, index, or table.
3. Be tested on a representative copy of data.
4. Have a handling plan if the migration fails or takes too long.
5. Be recorded so you know which version has been applied to each environment.

DDL in MySQL generally causes an implicit commit, and many DDL operations cannot be rolled back like normal DML. Do not assume a sequence of `ALTER TABLE` statements can be undone with `ROLLBACK`. For large tables, evaluate lock duration, DDL algorithm, temporary space, and replication impact.

### 4.3. Handling `DEFINER`

Views, triggers, routines, and events can store a definer (`DEFINER`). If that account does not exist on the target server or lacks appropriate privileges, the object may fail during creation or execution. Inventory `DEFINER` values, create appropriate accounts/roles per policy, or modify definitions in a controlled manner. Do not replace every `DEFINER` with a single shared administrative account.

## 5. Migrating Data

Before exporting data, clearly identify which tables, rows, columns, and point-in-time consistency need to be preserved. There are three common scope patterns:

- **All data in a schema:** suitable when moving a complete database.
- **A subset of tables:** suitable when splitting out part of an application or restoring only certain tables.
- **A subset of rows or columns:** suitable when migrating historical data, anonymizing test data, or running ETL.

### 5.1. Exporting Data Without Recreating Tables

If the target schema has already been created and verified for compatibility, you can dump data for specific tables:

```bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --single-transaction \
  --no-create-info \
  --skip-triggers \
  shop customers orders order_items \
  > shop-data.sql
```

- `--no-create-info` omits table creation statements.
- `--skip-triggers` avoids exporting triggers in the data dump when triggers were already handled in the schema step.
- `--single-transaction` creates a consistent snapshot for transactional tables such as InnoDB.

The target schema must already have compatible tables and structures before loading. For data with foreign keys, understand the load order and the state of referenced tables. Prefer loading in dependency order with constraint checks enabled. If you must temporarily disable `FOREIGN_KEY_CHECKS`, verify integrity afterward because re-enabling the variable does not automatically scan and validate previously loaded rows.

### 5.2. Exporting Only a Subset of Rows

`mysqldump --where` can filter rows for a table:

```bash
mysqldump \
  --host=db01.example.net \
  --user=backup_user \
  --password \
  --no-create-info \
  --skip-triggers \
  --where="created_at >= '2026-01-01'" \
  shop orders \
  > recent-orders.sql
```

The `WHERE` condition must be carefully checked so data is neither missed nor duplicated. When migrating multiple related tables, per-table filters must preserve business relationships and foreign keys. For example, taking orders by date without taking the corresponding `order_items` rows produces incomplete data.

### 5.3. Loading Data

For SQL dumps, use the MySQL client to import into the target database:

```bash
mysql \
  --host=db02.example.net \
  --user=restore_user \
  --password \
  < shop-schema.sql

mysql \
  --host=db02.example.net \
  --user=restore_user \
  --password \
  < shop-data.sql
```

If the dump specifies a database name different from the desired target, prepare the target schema first and inspect `USE` statements in the dump. Do not bulk-edit SQL dumps with naive text replacement when the database name may appear inside views, routines, data, or quoted identifiers.

For CSV-formatted data, `LOAD DATA` can be faster than executing individual `INSERT` statements, but you must control charset, delimiters, escapes, `NULL` handling, date/time formats, column order, and file permissions. Example:

```sql
LOAD DATA LOCAL INFILE 'orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, created_at, status);
```

`LOCAL` reads the file from the client side; its use depends on client/server configuration and security policy. Enable it only when needed, restrict file sources, and do not allow untrusted clients to load arbitrary files.

### 5.4. Consistency During Export

`--single-transaction` in `mysqldump` is usually suitable for InnoDB because the dump reads from a consistent snapshot without holding a read lock for the entire duration. However:

1. It does not provide the same snapshot guarantee for MyISAM or non-transactional storage engines.
2. Do not run DDL such as `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE` on objects currently being dumped.
3. Long-running write transactions or prolonged snapshots can increase the amount of undo history that must be retained.
4. If you need to synchronize tables/objects across multiple sources or engines, you must design an appropriate lock window or snapshot mechanism.

For migrations requiring minimal downtime, you can take an initial snapshot and then track subsequent changes via replication/binlog, followed by a brief write pause to apply the tail and cut over. Save the exact binlog coordinates or GTID associated with the snapshot.

## 6. Migrating Accounts and Privileges

MySQL accounts are identified by the pair `user` and `host`. `app@localhost` and `app@192.0.2.20` are two distinct accounts that can have different authentication methods, passwords, lock states, and privileges. Therefore, migrating users is not just copying usernames.

### 6.1. Inventorying Users and Roles

An administrator can list accounts using a privileged query:

```sql
SELECT User, Host, plugin, account_locked
FROM mysql.user
ORDER BY User, Host;
```

`mysql.user` is a system table for reading account information; do not update it directly. Use MySQL-supported administrative statements to create, alter, lock, or drop accounts.

For each application or administrative account to migrate, record:

- Username and allowed connection host.
- Authentication plugin and TLS requirements.
- Lock status, password expiration, resource limits, and account attributes.
- Global/schema/table/column privileges.
- Granted roles, default roles, and nested role relationships.
- Objects with a `DEFINER` depending on the account.

Not every account on the source needs to be migrated. Internal accounts, expired personal accounts, or platform-managed accounts may not belong on the target server.

### 6.2. Exporting Definitions and Privileges

For each account to migrate, run:

```sql
SHOW CREATE USER 'app'@'192.0.2.20';
SHOW GRANTS FOR 'app'@'192.0.2.20';
```

`SHOW CREATE USER` provides the account creation statement along with authentication attributes as represented by the server. `SHOW GRANTS` provides the privilege and role grant statements. Store the output in a protected location because it may contain authentication strings or sensitive information.

The typical application order is:

1. Verify that required authentication plugins exist on the target.
2. Create roles first if users will be granted roles.
3. Create users with the appropriate host and approved authentication attributes.
4. Apply grants, role grants, and default roles.
5. Verify effective privileges with `SHOW GRANTS` and test connecting from the actual source host.

Example of creating an account and granting minimal privileges on the target server:

```sql
CREATE USER 'app'@'192.0.2.20'
  IDENTIFIED BY 'replace-with-a-new-secret'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE
  ON shop.* TO 'app'@'192.0.2.20';

SHOW GRANTS FOR 'app'@'192.0.2.20';
```

The password in the example is a placeholder. During migration, you can preserve the identity if host and plugin are compatible, or rotate it according to security policy. Do not copy password hashes manually unless you understand the plugin and authentication format.

### 6.3. Checking Host and Authentication Plugins

The source account's host may no longer be valid on the target. For example, the application previously connected from `10.0.1.15`, but after moving to a new VPC its traffic originates from `10.20.4.12`. Identify the IP address that the target MySQL server actually sees, accounting for NAT, proxies, and container gateways.

The authentication plugin must also exist and be supported on the target server. If the source uses an external authentication plugin, that plugin may require additional libraries, configuration, or external authentication services. Migrating the `CREATE USER` statement without migrating its dependencies will cause logins to fail.

Do not grant broad privileges such as `ALL PRIVILEGES ON *.*` just to avoid permission errors after migration. Determine which statements the application needs to execute and grant the narrowest appropriate privileges.

## 7. Migrating Configuration and Operational Components

MySQL configuration includes startup variables, dynamic variables, configuration files, plugins/components, and external dependencies. Avoid copying configuration files verbatim from source to target without review, because the two hosts may differ in CPU, RAM, storage, operating system, paths, and topology role.

### 7.1. Inventorying System Variables

You can export the current list of variables:

```sql
SHOW GLOBAL VARIABLES;
```

Focus on these groups:

| Group | Examples | Questions When Migrating |
|---|---|---|
| Character sets and collations | `character_set_server`, `collation_server` | Are they compatible with the data and application? |
| SQL behavior | `sql_mode`, `time_zone`, `system_time_zone` | Could they alter query results or timestamps? |
| InnoDB | `innodb_buffer_pool_size`, `innodb_flush_log_at_trx_commit`, `innodb_redo_log_capacity` | Do they fit the target's RAM, I/O, and durability requirements? |
| Connections | `max_connections`, `connect_timeout`, `wait_timeout` | Do they match connection pools and actual workload? |
| Binary log | `log_bin`, `binlog_format`, `sync_binlog`, `binlog_expire_logs_seconds` | Is the target a source, replica, or standalone server? |
| Replication | `server_id`, `gtid_mode`, `enforce_gtid_consistency`, `log_replica_updates` | Are a new identity and replication state needed? |
| Security | `require_secure_transport`, TLS variables, audit settings | Are certificates, CAs, and policies available on the target? |

The variable list is only survey input. Classify each variable as required configuration, hardware-tuned configuration, role-specific configuration, or droppable configuration. Source values are not automatically optimal for the target.

### 7.2. Configuration Files and Paths

MySQL typically reads configuration from `my.cnf` on Unix-like systems or `my.ini` on Windows, along with included files depending on the installation. When migrating, check:

- `datadir`, `tmpdir`, socket, PID, error log, slow query log, and binary log paths.
- Filesystem ownership and access permissions for the OS user running MySQL.
- RAM/CPU sizing, storage throughput, and operating system limits.
- `server_id` must be unique across the replication topology.
- `server_uuid` is generated by MySQL for an instance; do not clone an identity from source to a new instance.
- `lower_case_table_names` is constrained by the platform and data directory initialization time; do not treat it as freely changeable after data has been created.

Keep the source configuration for reference, but apply each reviewed setting individually to the target configuration. Record before/after values and how to roll back. Avoid copying paths or sockets that do not exist on the target operating system.

### 7.3. Plugins, Components, TLS, and Keyring

If the application or database relies on plugins/components, verify compatible binaries, versions, load configuration, and licenses if applicable. Plugins installed on the source are not automatically present on the target.

For data encryption, moving tablespace files alone may be insufficient. You must preserve the keyring or corresponding key management system, access permissions, master keys, and key recovery procedures. Losing keys can render encrypted data unreadable.

For TLS, migrate or issue new certificates, private keys, CA chains, and identity verification settings. Private keys must be protected as secrets. Test connections from applications and replication after installation.

### 7.4. Do Not Copy the Entire System Database

Do not dump/copy the entire `mysql` schema as a way to migrate users and privileges across different versions. System table structures and the data dictionary can change between versions; overwriting them can corrupt metadata or cause startup/upgrade failures. Migrate accounts using supported administrative statements and let MySQL manage system tables via standard installation/upgrade procedures.

## 8. Choosing Tools by Scope and Size

| Tool / Method | Suitable Scope | Strengths | Limitations to Consider |
|---|---|---|---|
| `mysqldump` | Schema, logical data, selected tables | Human-readable, easy to filter, suitable for selective migration | Restore can be slow for large datasets; requires complete object flags |
| MySQL Shell dump/load utilities | Instance, schema, or table as logical dump | Supports chunking and parallel loading; fits large datasets | Must verify version, options, and target compatibility |
| Physical backup | Entire instance or tool-supported scope | Typically fast for large volumes, preserves physical layout | Depends on version, engine, tool, configuration, and keyring |
| `LOAD DATA` | Loading file-based data such as CSV | Efficient bulk loading | Must handle charset, delimiter, NULL, permissions, and formatting |
| Replication/binlog | Syncing post-snapshot changes | Minimizes write pause at cutover | Requires continuous log retention and handling lag/GTID/start position |
| ETL or transformation apps | Selecting, transforming, or merging data | Flexible for mapping and cleansing | Must design consistency, retries, and reconciliation |

No single tool is optimal for every scope. For a few small tables, a logical dump may suffice. For terabytes with limited downtime, a physical backup combined with replication/binlog may be more suitable. Base the decision on benchmarking export, transfer, import, verification, and cutover durations.

## 9. Safe Migration Sequence

A migration plan should be broken into verifiable phases.

### 9.1. Before Migration

1. Define goals, scope, data owners, downtime window, RTO/RPO, and success criteria.
2. Inventory schemas, data, users/roles, grants, configs, plugins, certificates, keyrings, and dependent jobs.
3. Compare versions, charsets, collations, SQL modes, storage engines, and incompatible features.
4. Choose logical, physical, replication, or ETL; define how to obtain a consistent snapshot.
5. Create a restorable backup and test it in an isolated environment.
6. Provision the target server, capacity, administrative accounts, firewalls, TLS, and monitoring.
7. Rehearse the migration on representative data, measure timings, and update the runbook.

### 9.2. During Migration

1. Take a snapshot/dump at a defined point in time and save binlog/GTID metadata if syncing subsequent changes.
2. Migrate schemas and dependent objects.
3. Create users/roles and apply approved privileges.
4. Load data in dependency order; monitor errors, throughput, storage usage, and progress.
5. If using replication, configure the receiver/applier and wait for the replica to catch up.
6. Reconcile data, schema, privileges, and objects before cutover.

### 9.3. Cutover

1. Announce and open the cutover window.
2. Stop or fence new write streams to the source in a manner supported by the application.
3. Apply the final data delta or wait for replication to reach the designated sync point.
4. Verify the final transaction, GTID/binlog position, and consistency.
5. Switch endpoints, secrets, or application connection settings to the target.
6. Run smoke tests on critical business flows.
7. Re-open traffic gradually and monitor errors, latency, connections, deadlocks, and data.

Do not allow both source and target to accept independent writes during cutover unless the architecture explicitly implements multi-writer conflict resolution. Uncontrolled writes in two places cause data divergence that is very difficult to merge.

### 9.4. Post-Migration and Rollback

Keep the source available for comparison for a defined period, while preventing accidental writes to the old source. Monitor the application and compare business outcomes before closing the rollback window.

Rollback requires clear criteria: which failures trigger fallback, who makes the decision, how new writes on the target will be handled, and when the old source can accept writes again. If the target has already accepted new writes, you cannot simply point endpoints back to the source and discard those transactions; you must sync them back or execute a controlled data recovery procedure.

## 10. Verifying Migration Results

Do not declare success merely because an import command exited with code 0. Verify each scope:

| Scope | Verification |
|---|---|
| Schema | Compare `SHOW CREATE TABLE`, views, indexes, constraints, triggers, routines, and events |
| Data | Row counts, business aggregate reconciliation, batch checksums or hashes, sample checks |
| Relationships | Check orphan rows, foreign keys, parent/child table relationships, and business integrity |
| Accounts | Check `SHOW CREATE USER`, `SHOW GRANTS`, default roles, plugins, and connections from actual hosts |
| Configuration | Compare required variables, plugins, TLS, keyring, log paths, replication, and security parameters |
| Application | Run smoke tests, read/write flows, background jobs, reports, events, and critical workflows |
| Operations | Fresh backups, test restores, alerts, monitoring, rotation, and runbooks |

Example of checking row count and total order amount:

```sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS order_total
FROM shop.orders;
```

Run the same query on source and target at corresponding data states. If the source still receives writes during comparison, differences may result from snapshot timing. For large tables, reconcile by key or time range to isolate discrepancies easily.

Check logical foreign keys with an anti-join query, for example:

```sql
SELECT oi.order_id
FROM shop.order_items AS oi
LEFT JOIN shop.orders AS o
  ON o.order_id = oi.order_id
WHERE o.order_id IS NULL
LIMIT 20;
```

Evaluate results against business rules. Returning zero rows is a good sign for this relationship, though it does not prove all constraints and data are valid.

## 11. Common Mistakes When Choosing Scope

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Tables exist but app reports missing objects | Views, routines, triggers, or events were not dumped | Inventory objects and re-export the missing components |
| View/routine permission errors | `DEFINER` does not exist or lacks privileges | Create/adjust definer per policy and check grants |
| User login failures | Wrong host, missing auth plugin, different TLS or password policy | Check `SHOW CREATE USER`, plugin, actual source host, and auth logs |
| Collation errors during import | Target does not support source collation | Choose a compatibility plan, test charset/collation conversion, and verify results |
| Missing or duplicate data | Inconsistent snapshot, wrong export filter, or repeated import run | Verify snapshot point, unique keys, transactions, and retry procedures |
| Slow migration | Large SQL dump, indexes/constraints, I/O, or sequential import | Measure each phase, consider MySQL Shell, physical backup, or controlled parallel load |
| Target behaves differently from source | Different config, SQL mode, time zone, plugins, or system variables | Compare impactful settings and run application tests |
| Cannot decrypt encrypted data | Missing keyring or corresponding keys | Restore keys via approved key management procedures |
| Replica cannot catch up after snapshot | Missing binlogs, wrong position/GTID, or too-short retention | Check metadata and log sequence; take a new snapshot if required logs are gone |

## 12. Scope Selection and Cutover Checklist

- [ ] Identified databases, tables, rows, and columns to migrate.
- [ ] Inventoried views, indexes, constraints, triggers, routines, and events.
- [ ] Checked `DEFINER` values and cross-schema dependencies.
- [ ] Decided which users/roles to migrate, which hosts to adjust, and which privileges to grant.
- [ ] Checked authentication plugins, TLS, certificates, keyring, and secrets.
- [ ] Inventoried source configuration and chosen appropriate values for target hardware/role.
- [ ] Verified compatibility of versions, charsets, collations, SQL modes, and storage engines.
- [ ] Selected export/import tools appropriate for data volume and downtime.
- [ ] Obtained a consistent snapshot along with binlog/GTID metadata if syncing subsequent changes.
- [ ] Tested restore/import on an equivalent environment.
- [ ] Established reconciliation criteria for schema, data, privileges, and business logic.
- [ ] Prepared the cutover window, write fencing on source, and rollback plan.
- [ ] Verified new backups and operational procedures after cutover.

## 13. Self-Check

1. When migrating only a single database for an application, why is it still necessary to check routines, triggers, events, and `DEFINER`?
2. What is the difference between `mysqldump --no-data` and `--no-create-info`?
3. Does `--single-transaction` guarantee a consistent snapshot for every storage engine? Which operations should be avoided during the dump?
4. Why should you not copy the entire `mysql` schema to a server running a different version?
5. When migrating accounts, why must you check `user@host`, authentication plugins, roles, and grants together?
6. Why should you not copy configuration files verbatim from source to target without review?
7. What additional components must be migrated alongside data files for an encrypted database?
8. When using an initial snapshot plus replication to minimize downtime, what metadata must be saved to start syncing accurately?
9. Why must writes be stopped or controlled before cutover, and why must two servers not accept independent writes?
10. Design a migration scope for an e-commerce application containing `orders`, `order_items`, customers, application accounts, a report-sending event, and TLS configuration; describe how to verify after cutover.

A good migration plan starts with an inventory of objects and dependencies before choosing tools. Ensure each scope has clear export, import, verification, and rollback procedures so that the MySQL migration can be evaluated with concrete data and test results.
