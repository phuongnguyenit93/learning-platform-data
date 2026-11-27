# Data Dictionary, System Tables, and Data Directory Compatibility

MySQL must store metadata to know which tables exist in a database, what columns and indexes each table has, which accounts are allowed access, and how objects depend on one another. This metadata is managed by the **data dictionary**, alongside system tables and system schemas used for administration, monitoring, and operations.

The metadata architecture changed significantly across MySQL generations. MySQL 5.7 and earlier versions relied heavily on metadata files such as `.frm` and legacy-format system tables. Starting in MySQL 8.0, the data dictionary moved to InnoDB-based transactional metadata. As a result, a data directory from one version cannot be treated as an independent set of files to be opened arbitrarily by binaries of another version.

When upgrading, migrating, or recovering MySQL, you must understand where metadata resides, what kind of information each system schema holds, which tools serve as supported administrative interfaces, and which attributes must match between source and target. This lesson focuses on MySQL 8.0 and principles for upgrading from earlier versions.

## Learning Objectives

After completing this lesson, you will be able to:

- Explain the role of the data dictionary and metadata architectural changes in MySQL 8.0.
- Distinguish `INFORMATION_SCHEMA`, `mysql`, `performance_schema`, and `sys`.
- Query metadata using `SHOW` and supported system views.
- Understand why you must never directly edit system tables or manually mix data directory files across versions.
- Identify factors affecting data directory and tablespace compatibility.
- Design a backup, verification, upgrade, validation, and recovery workflow.

## 1. What Is the Data Dictionary?

The data dictionary is where MySQL manages metadata describing database objects and their relationships. Metadata includes information such as:

- Databases, tables, views, and column definitions.
- Indexes, primary keys, unique keys, foreign keys, and constraints.
- Stored procedures, functions, triggers, and events.
- Tablespaces, partitions, and storage attributes.
- Object details required by the server to parse SQL, verify privileges, and execute operations.

When running `SELECT * FROM app.orders`, MySQL needs to know that table `orders` exists, what columns it contains, their data types, indexes, constraints, and the current account's privileges. The data dictionary provides this metadata so the server can perform those steps.

Metadata differs from business data. Business data consists of the rows inside `orders`, `customers`, or `payments`; metadata describes the structure and properties of those objects. Backups and upgrades must preserve both types of information.

## 2. Metadata Architecture Changes from MySQL 5.7 to 8.0

### 2.1. How Metadata Was Stored Before MySQL 8.0

In MySQL 5.7 and earlier versions, table metadata was stored partially in separate files like `.frm`; partitions, triggers, and certain other objects could use separate metadata files. System tables in the `mysql` schema stored accounts, privileges, and administrative metadata. This approach scattered metadata across multiple formats, and certain operations lacked the transactional properties of InnoDB data.

For example, a `.frm` file described the table definition, while InnoDB data could reside in a separate `.ibd` tablespace or the system tablespace. Copying only the `.ibd` file without bringing its metadata and performing a supported tablespace import procedure is insufficient to restore a complete table.

### 2.2. The Transactional Data Dictionary in MySQL 8.0

Starting in MySQL 8.0, metadata is managed by a transactional data dictionary backed by InnoDB. Internal data dictionary tables reside in the `mysql` system schema and are managed by the server. These internal tables are not a public SQL interface for applications to read or modify directly; users access metadata through `INFORMATION_SCHEMA`, `SHOW`, and interfaces supported by MySQL documentation.

Moving to a transactional data dictionary brings several benefits:

- Metadata is managed under InnoDB's transactional engine.
- Metadata and DDL operations share a more consistent crash recovery model.
- No longer relies on `.frm` files for table definition metadata as in earlier versions.
- The server can manage metadata across many object types in a unified architecture.

This also creates an upgrade requirement: when opening an old data directory with MySQL 8.0, the server must convert legacy metadata into the new architecture. That conversion is part of the upgrade process, not something that can be done by renaming or copying files manually.

### 2.3. Do Not Edit the Data Dictionary Directly

Do not run `INSERT`, `UPDATE`, or `DELETE` directly against internal data dictionary tables. Do not create, delete, or replace metadata files in the data directory to force the server to recognize a different table structure.

Modify objects using supported SQL statements:

```sql
CREATE TABLE app.orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  KEY idx_orders_customer (customer_id)
) ENGINE = InnoDB;

ALTER TABLE app.orders
  ADD COLUMN source_channel VARCHAR(30) NULL;

DROP TABLE app.temporary_import;
```

DDL statements update metadata through MySQL-managed workflows, including locking, dependency checks, and crash recovery. If metadata appears corrupt after a failure, use logs, verification tools, and supported recovery procedures rather than editing system tables.

## 3. System Schemas in MySQL

MySQL provides several schemas dedicated to metadata, accounts, monitoring, and operational utilities. They serve different purposes.

| Schema | Role | Usage |
|---|---|---|
| `mysql` | System tables, accounts, privileges, roles, and administrative metadata | Use account/privilege management statements; read only documented tables or views |
| `INFORMATION_SCHEMA` | Views exposing metadata on databases, tables, columns, indexes, constraints, and routines | Query structure with SQL; do not treat it as a physical directory of files |
| `performance_schema` | Instrumentation and runtime metrics on statements, waits, locks, threads, and server activity | Investigate performance and operations; data primarily reflects runtime state |
| `sys` | Convenience views and procedures built on `performance_schema` and `INFORMATION_SCHEMA` | Use summary views for diagnostics and observability |

`INFORMATION_SCHEMA`, `performance_schema`, and `sys` are not three copies of the data dictionary. They provide distinct perspectives: object metadata, runtime instrumentation, and convenient summary queries.

### 3.1. Querying Metadata via INFORMATION_SCHEMA

List business tables and storage engines:

```sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  ENGINE,
  ROW_FORMAT,
  TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'app'
ORDER BY TABLE_NAME;
```

Inspect column definitions in order:

```sql
SELECT
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  EXTRA,
  ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

List indexes:

```sql
SELECT
  INDEX_NAME,
  NON_UNIQUE,
  SEQ_IN_INDEX,
  COLUMN_NAME,
  INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Look up foreign keys:

```sql
SELECT
  CONSTRAINT_NAME,
  COLUMN_NAME,
  REFERENCED_TABLE_SCHEMA,
  REFERENCED_TABLE_NAME,
  REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'orders'
  AND REFERENCED_TABLE_NAME IS NOT NULL;
```

These views allow migration tools, schema audits, and automated verification scripts to read metadata without parsing MySQL's internal files.

### 3.2. Using SHOW for Exact Definitions

When inspecting a table definition to save in a migration or compare across two environments, `SHOW CREATE TABLE` is often more useful than summary queries:

```sql
SHOW CREATE TABLE app.orders\G
SHOW CREATE VIEW app.active_orders\G
SHOW CREATE PROCEDURE app.rebuild_summary\G
```

`SHOW CREATE TABLE` returns the table definition, including columns, indexes, constraints, engine, charset/collation, and related options. Save the output along with the MySQL version and timestamp so you can compare after upgrading.

Not all metadata appears in a single `SHOW` statement. For a comprehensive audit, combine appropriate `INFORMATION_SCHEMA` views, `SHOW` commands, and documentation for the object under inspection.

### 3.3. Role of the mysql System Schema

The `mysql` schema holds system tables and views used by the server to manage accounts, privileges, roles, time zone info, components/plugins, and certain operational metadata.

In MySQL 8.0, `mysql.user` is a compatibility view for reading account metadata; account privilege data is stored in new internal structures, including `mysql.global_priv`. Do not rely on the physical structure of these tables or edit them directly. System schema layouts can change between releases.

Create accounts and grant privileges using supported interfaces:

```sql
CREATE USER 'report_reader'@'10.20.5.12'
  IDENTIFIED BY '<password-from-secret-manager>';

GRANT SELECT
  ON app.reporting_view
  TO 'report_reader'@'10.20.5.12';

SHOW GRANTS FOR 'report_reader'@'10.20.5.12';
```

When migrating accounts to a new instance, export or recreate account definitions, authentication plugins, roles, and grants using supported SQL statements. Never copy raw system schema files or tables from another version into the new server's `mysql` directory.

### 3.4. Performance Schema and the sys Schema

`performance_schema` records runtime activity such as statements, waits, locks, file I/O, and threads. It is valuable when investigating slow queries or blocked migrations, but it does not replace table-definition metadata and is not a long-term business data store.

`sys` provides aggregated views for easier reading. For example:

```sql
SELECT *
FROM sys.schema_table_statistics
WHERE table_schema = 'app'
ORDER BY rows_fetched + rows_inserted + rows_updated + rows_deleted DESC;
```

Exact views and columns can differ across versions. Inspect `SHOW CREATE VIEW` or accompanying documentation before depending on a view in automation.

## 4. What Does the Data Directory Contain?

The data directory is the directory MySQL uses to store data and much of the state required for the server to operate. Its actual path is configured per environment and can be checked with:

```sql
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'innodb_data_home_dir';
SHOW GLOBAL VARIABLES LIKE 'innodb_file_per_table';
```

Depending on configuration, the data directory can contain:

- Database directories and data tablespaces.
- InnoDB system tablespace and undo tablespaces.
- InnoDB redo logs.
- Data dictionary and system schemas.
- Server identity files such as `auto.cnf`.
- Binary logs and relay logs if configured inside the data directory.
- Temporary files, status files, or feature-specific metadata.

Not every component must live inside `datadir`; configuration variables can place redo logs, binary logs, relay logs, or tablespaces elsewhere. When planning backups or migrations, inventory all actual paths rather than copying one folder and assuming it is complete.

### 4.1. The Data Directory Is an Interdependent Unit

Data files, metadata, and logs work together. For instance, InnoDB needs metadata to map tablespaces to tables; redo logs to recover uncheckpointed changes; undo logs for transactions and rollbacks; and binary logs for replication and PITR.

Taking an `.ibd` file from one point in time and pairing it with a data dictionary or redo log from another point in time can prevent the server from opening tablespaces or cause inconsistent data. Likewise, copying a running MySQL data directory without a consistent backup mechanism can produce an unsynchronized set of files.

### 4.2. Checking Critical Storage Settings

Before migrating or upgrading, record relevant variables:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'datadir',
  'innodb_data_home_dir',
  'innodb_data_file_path',
  'innodb_file_per_table',
  'innodb_page_size',
  'lower_case_table_names',
  'character_set_server',
  'collation_server',
  'log_bin',
  'log_bin_basename',
  'relay_log_basename'
);
```

Not all variables can be changed on an already-initialized instance. Certain attributes, such as `innodb_page_size` and `lower_case_table_names`, are tied to how the instance was initialized and cannot be altered arbitrarily later. When creating a new target for physical recovery or migration, confirm these attributes are compatible with the source and backup.

## 5. Data Directory Compatibility

### 5.1. Do Not Open a Newer Data Directory with Old Binaries

Once a newer MySQL version upgrades the data dictionary or storage format, do not restart with older binaries against the same data directory as a rollback method. The older version may not understand metadata or file formats updated by the newer version, leading to startup failures or risk of data corruption.

Safe operational rules:

- Never share one data directory between two MySQL instances of different versions.
- Never copy internal files from a newer version's data directory into an older version.
- Never restore a physical backup onto a version outside the backup tool's compatibility matrix.
- Never assume a data directory can be downgraded simply by installing old binaries.

If you need to return to an older version, use an explicitly supported downgrade path for that exact version pair, or provision a new instance on the older version and restore from a logical dump with compatible schemas and data. Logical restores must also verify data types, collations, reserved words, and features absent in the older version.

### 5.2. Differences Between MySQL 5.7 and 8.0

When moving from 5.7 to 8.0, the server must convert legacy metadata into the new data dictionary and upgrade system schemas. `.frm` files are no longer the source of table definition metadata. Therefore:

- Do not delete `.frm` files or manually recreate metadata files to fix errors.
- Do not copy the entire `mysql` directory from 5.7 into an already-initialized 8.0 instance.
- Do not run custom scripts that alter system tables to match 5.7 layout on an 8.0 server.
- Use the official upgrade procedure so the server converts metadata and system schemas.

Starting in MySQL 8.0.16, the server automatically executes the upgrade tasks previously handled by `mysql_upgrade` when starting with a data directory requiring upgrade. `mysql_upgrade` has been deprecated; do not build new procedures around running that utility as a mandatory step after every startup. Read the release notes for the target version for specific upgrade changes.

### 5.3. Attributes Requiring Compatibility

| Attribute | Why It Matters |
|---|---|
| MySQL version and data dictionary format | The server must understand the data directory's metadata format and upgrade procedure |
| `innodb_page_size` | Page size is tied to tablespace structure; cannot be arbitrarily changed when reusing physical data |
| `lower_case_table_names` | Affects how database/table names are stored and compared; must be chosen correctly at target initialization and match the source |
| `innodb_data_file_path` and system tablespace | Defines layout and sizing of system data files |
| File-per-table tablespaces | `.ibd` files require matching metadata and a supported tablespace import procedure |
| Character set and collation | Can alter string comparisons, indexes, sorting, and query results |
| Plugins/components and authentication plugins | New server may lack legacy plugins or matching authentication settings |
| Binary log/redo/undo formats | Must be compatible with the server version and recovery/replication tools |
| `server_uuid` and `server_id` | Requires unique identities in a replication topology after clone or restore |

In particular, `lower_case_table_names` must be configured properly when initializing the data directory. Never change this variable on an existing data directory with data in an attempt to work around case-sensitivity differences between Windows, Linux, and other operating systems.

## 6. Physical Migration vs. Logical Migration

There are two common ways to move data to another instance. Choosing between them depends on downtime requirements, data size, versions, and compatibility.

### 6.1. Physical Backup/Restore

A physical backup preserves data files in their physical format. This approach usually fits when fast recovery is needed or when moving a large instance whose backup tool supports the corresponding versions and settings.

Items to verify:

- The backup must be consistent per the tool's mechanism; never copy files manually while the server is running.
- Both the MySQL version and backup tool version must fall within the compatibility matrix.
- Tablespaces, redo/undo logs, data dictionary, and related configs must be handled together.
- The target must have compatible settings, filesystem permissions, and sufficient disk space.
- If cloning into a new replication node, verify `server_uuid` and `server_id` do not collide.

Physical backups are usually not suitable for jumping directly across arbitrary major versions. When tools do not support a version pair, follow a supported upgrade path or use logical migration.

### 6.2. Logical Dump/Restore

Logical migration exports structures and data as SQL statements or logical dump formats, then loads them into a new instance. Example with `mysqldump`:

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  --databases app \
  > app_dump.sql
```

`--single-transaction` produces a consistent snapshot for transactional tables like InnoDB under suitable conditions; it does not guarantee a consistent snapshot for non-transactional tables and does not prevent concurrent DDL from interfering with the dump. For very large datasets, MySQL Shell dump/load utilities can provide parallelism and chunking; choose tools suited to the source/target versions.

Logical migration lets the new server rebuild metadata under the target version's data dictionary rather than carrying over source internal files. However, you must check incompatible SQL objects and features, accounts, roles, events, routines, charsets, collations, and dependency creation order.

### 6.3. Do Not Dump/Restore System Schemas Like Business Databases

Do not dump the entire `mysql` schema from one version and load it verbatim into another version. System tables change structure and management across releases. Accounts, roles, and privileges should be exported/recreated using supported SQL interfaces, while internal metadata must be managed by the target server.

For applications, dump business schemas along with required routines, triggers, events, and views. For accounts, recreate accounts and grants per security policy. For server configuration, manage config files separately and review every variable against the target version.

## 7. Safe Upgrade Workflow

Upgrading MySQL changes binaries, system schemas, the data dictionary, and sometimes data formats. Prepare thoroughly beforehand and verify after the new server starts.

### 7.1. Before the Upgrade

1. Record the current version, edition, plugins/components, engines, configuration, and replication topology.
2. Confirm MySQL supports the upgrade path from the exact source version to the target version.
3. Run an appropriate compatibility checker, such as MySQL Shell Upgrade Checker, and resolve warnings on syntax, data types, collations, reserved words, plugins, or system tables.
4. Check free space in the data directory, redo/undo, binary logs, temporary directory, and filesystems.
5. Create a full backup and verify restore in an independent environment.
6. Save schema definitions, accounts/roles/grants, server configurations, and required replication metadata.
7. Rehearse the full procedure on a clone with production-like data and workload.
8. Prepare the write-stop window, traffic switching method, accountable owners, and rollback criteria.

Do not begin a production upgrade solely because the new server package installs cleanly. Confirm compatibility across applications, drivers, connectors, backup tools, monitoring, and operational workflows.

### 7.2. During the Upgrade

- Halt or coordinate writes per plan; avoid concurrent schema migrations.
- Create a final backup or verified checkpoint.
- Stop MySQL cleanly if required by the upgrade path.
- Install new binaries and preserve the data directory per official upgrade guidance.
- Start the new server with compatible configuration so the server upgrades metadata/system schemas.
- Monitor the error log throughout the entire upgrade phase; never restart with old binaries once metadata conversion has occurred.
- Open traffic only after the server finishes upgrading and system checks pass.

Do not delete backups, logs, or old installation packages until system stability is confirmed and retention policies permit.

### 7.3. After the Upgrade

Verify version and data directory paths:

```sql
SELECT VERSION();
SHOW GLOBAL VARIABLES LIKE 'datadir';
SHOW GLOBAL VARIABLES LIKE 'lower_case_table_names';
```

Continue verifying:

- Error log shows zero upgrade errors or tablespace opening errors.
- Databases, tables, views, routines, triggers, events, and indexes exist intact.
- Accounts, authentication plugins, roles, and grants work.
- Character sets, collations, SQL modes, and system variables hold expected values.
- Replication, GTID, binary logs, and backups continue functioning.
- Critical queries return accurate results and execution plans show no unexpected regressions.
- Applications, connectors, monitoring, and background jobs connect successfully.
- A fresh post-upgrade backup succeeds and restore has been tested per procedure.

Do not treat a successful `mysqld` startup as sufficient proof that all objects and workloads are compatible.

## 8. Investigating Data Dictionary or System Table Errors

Signs indicating metadata or data directory compatibility issues:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Server reports incompatible data dictionary version | Mismatched binaries for the data directory or incomplete upgrade | Use the exact version per the upgrade workflow; read error logs and avoid trying old binaries arbitrarily |
| Table fails to open after copying files | Missing metadata, unsynchronized tablespace, or inconsistent copy | Restore from a consistent backup or use the supported tablespace import procedure |
| Missing system tables/columns after upgrade | System schema upgrade incomplete or failed | Inspect error logs and release upgrade procedure; never add columns to system tables manually |
| Account cannot log in | Authentication plugin, hash, role, or grant differences across versions | Check `SHOW CREATE USER`, `SHOW GRANTS`, available plugins, and authentication policies |
| Table names differ across operating systems | Different `lower_case_table_names` or filesystem rules | Verify initialization configuration and plan an explicit table-renaming migration |
| Cannot import `.ibd` tablespace | Incompatible page size, schema, tablespace metadata, or version | Use the official transportable tablespace workflow or logical restore |

### 8.1. Importing a Tablespace Is Not Arbitrary File Copying

InnoDB supports transportable tablespaces under specific conditions. The workflow generally involves preparing a matching table on the target, exporting the tablespace on the source with `FLUSH TABLES ... FOR EXPORT`, copying files per documentation, and running `ALTER TABLE ... DISCARD TABLESPACE` and `IMPORT TABLESPACE` on the target. Exact details depend on table definition, version, encryption, page size, and tablespace attributes.

Illustrative partial workflow example:

```sql
-- On source: prepare the table for export
FLUSH TABLES app.orders FOR EXPORT;

-- After copying files per instructions and ending export state:
UNLOCK TABLES;

-- On target: table has been created with a compatible definition
ALTER TABLE app.orders DISCARD TABLESPACE;
-- Copy tablespace files to the exact location per MySQL documentation
ALTER TABLE app.orders IMPORT TABLESPACE;
```

This is a conceptual outline only, not a complete copy-paste procedure. Exporting can generate auxiliary metadata files and requires copying while the table remains in export state. Follow the transportable tablespace documentation for your exact version, verify checksums, and validate constraints/indexes after import.

## 9. Things You Must Not Do

- **Do not edit system tables directly:** use `CREATE USER`, `ALTER USER`, `GRANT`, `REVOKE`, and supported DDL.
- **Do not manually delete `.frm` or old metadata files:** let the upgrade workflow and server manage metadata.
- **Do not copy the `mysql` directory across major versions:** system schemas have release-specific layouts.
- **Do not open a newer data directory with old binaries:** this is not a safe downgrade strategy.
- **Do not copy a running data directory with a file manager:** use a consistent physical backup or supported snapshot mechanism.
- **Do not treat `INFORMATION_SCHEMA` as a physical file folder:** it is a metadata query interface.
- **Do not use `performance_schema` as long-term metadata storage:** it reflects runtime instrumentation.
- **Do not assume `.ibd` files are independent of the data dictionary:** matching metadata and tablespace procedures are required.
- **Do not initialize a target with mismatched `lower_case_table_names` or `innodb_page_size`:** those properties govern physical data reuse.
- **Do not delete backups immediately after upgrading:** clean up only after verifying applications, data, replication, and recoverability.

## 10. Practical Exercise

A system runs MySQL 5.7 on Linux using InnoDB file-per-table with multiple business databases. The operations team needs to migrate to MySQL 8.0 on a new server. The system includes stored procedures, triggers, events, dedicated application accounts, and several replicas.

Create an upgrade plan and answer:

1. How does MySQL 5.7's data dictionary differ from MySQL 8.0's transactional data dictionary architecture?
2. Why can you not simply copy `.ibd` files and the `mysql` directory to the new server and start it?
3. How will you use `INFORMATION_SCHEMA`, `SHOW CREATE TABLE`, and other tools to collect metadata before upgrading?
4. Which properties such as `lower_case_table_names`, `innodb_page_size`, charset/collation, and plugins must be verified on the target?
5. When should you choose physical backup/restore versus logical dump/restore? State the compatibility requirements of each.
6. Why should you not dump the entire system schema from 5.7 and load it verbatim into 8.0?
7. How do MySQL 8.0.16 and later handle the tasks previously performed by `mysql_upgrade`?
8. Describe backup, restore testing, upgrade execution, error log inspection, and post-upgrade application verification.
9. If rolling back to 5.7 is needed after the data dictionary has already been upgraded, how will you recover?
10. If only a single InnoDB table needs to move to another instance, when are transportable tablespaces appropriate and why can `.ibd` files not be copied arbitrarily?

A solid plan must specify exact source/target versions, the supported upgrade path, backup type, target initialization settings, compatibility check steps, traffic-opening criteria, and a rehearsed recovery procedure.

## Conclusion

The data dictionary is the core metadata source allowing MySQL to understand object structures and relationships. MySQL 8.0 moved metadata into an InnoDB-backed transactional architecture; `INFORMATION_SCHEMA`, `SHOW`, `mysql`, `performance_schema`, and `sys` expose interfaces with distinct purposes. A data directory contains tightly coupled data files, metadata, and logs, so it cannot be mixed or opened arbitrarily across versions. Use official upgrade procedures, restorable backups, pre-upgrade compatibility checks, and post-upgrade verification across schemas, accounts, replication, and applications.
