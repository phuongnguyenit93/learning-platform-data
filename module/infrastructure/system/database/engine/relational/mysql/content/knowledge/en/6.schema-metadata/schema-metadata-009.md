# Data Dictionary and Differences from Legacy Metadata Files

MySQL needs to store descriptive information about databases to understand the structure of tables, columns, indexes, views, triggers, routines, and other objects. This information is called **metadata**. The way MySQL stores and manages metadata changed dramatically starting in MySQL 8.0.

In older versions, metadata was scattered across files in the data directory, system tables, and each storage engine's private dictionary. For example, `.frm` files held table definitions at the server layer, while InnoDB maintained its own internal information about tables and tablespaces. Starting in MySQL 8.0, MySQL uses a centralized **transactional data dictionary**, storing metadata in dictionary tables managed by the server and backed by InnoDB.

This change affects how metadata is read, backed up, restored, upgraded, and troubleshot. In particular, you can no longer treat `.frm` files as the source of table definitions or manually copy/delete metadata files as was done in some older systems.

This lesson belongs to `DATABASE_MYSQL`: understand metadata architecture to design, query, administer, and operate relational databases safely; know how to use supported SQL interfaces to inspect schemas rather than depending on internal file layouts.

## 1. Metadata and Data Dictionary

### 1.1. What is metadata?

Metadata is data that describes objects in a database, not the business data stored in individual rows. For example, for the table:

~~~sql
CREATE TABLE sales.orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id)
) ENGINE = InnoDB;
~~~

The rows containing order IDs, customers, totals, and creation timestamps are business data. Metadata describes:

- The `sales` database and the `orders` table.
- The name, ordinal position, and data type of each column.
- `NOT NULL`, `AUTO_INCREMENT`, and default value attributes.
- The primary key and secondary indexes.
- The InnoDB storage engine.
- Charset, collation, partitions, and other attributes if present.

Metadata also includes definitions of views, triggers, stored procedures, functions, events, tablespaces, partitions, and other database objects.

### 1.2. What is the data dictionary?

The **data dictionary** is the component that manages metadata for database objects. The server uses the dictionary to look up definitions, resolve names, validate relationships between objects, prepare statements, and execute DDL.

A conceptual flow:

~~~text
SQL statement
    |
    v
Parse syntax and resolve names
    |
    v
Look up metadata / data dictionary
    |
    +--> Metadata object already in cache
    |
    +--> Read dictionary when needed
    |
    v
Check privileges and prepare object
    |
    v
Execute statement and interact with storage engine
~~~

This is a conceptual diagram. The actual internal flow has more steps and varies by statement type, storage engine, and version.

The data dictionary is not an application schema that users can create or update themselves. It is an internal component of MySQL Server with supported metadata-reading interfaces such as `SHOW`, `INFORMATION_SCHEMA`, and diagnostic tools.

## 2. Metadata Architecture Before MySQL 8.0

In older versions, metadata did not reside in one unified repository. Depending on object type and storage engine, information could be stored in:

1. Metadata files inside the database subdirectories of the data directory.
2. System tables in the `mysql` schema.
3. A storage engine's own data dictionary, such as InnoDB's internal dictionary.
4. Data files, index files, or tablespaces holding physical data and some engine-specific details.

Consequently, server-layer metadata files and storage-engine internal dictionaries could describe related aspects of the same table. They had to stay consistent with each other.

### 2.1. The .frm file

In MySQL versions prior to 8.0, each table typically had a `.frm` file containing server-layer table definition information, such as:

- Column names and structure.
- Data types, attributes, and column order.
- Index information and server-level table definition options.
- Details required for the server to open and process the table.

Views also had `.frm` files in versions using this mechanism.

A `.frm` file did not contain the table's data rows. Physical data and indexes depended on the storage engine. For example:

- MyISAM typically used `.MYD` for data and `.MYI` for indexes.
- InnoDB could store tables in the shared system tablespace `ibdata*` or file-per-table `.ibd` files, depending on configuration.

Therefore, never confuse `.frm` with `.ibd`, `.MYD` data files, or `.MYI` index files.

### 2.2. Other legacy metadata files

Beyond `.frm`, older versions also used files with specific roles:

| File | Role in legacy architecture | Where did the info move in MySQL 8.0? |
|---|---|---|
| `.frm` | Server-layer table and view definitions | Data dictionary tables |
| `.TRG` | Trigger definition/parameter details | Data dictionary tables |
| `.TRN` | Trigger namespace/names | Data dictionary tables |
| `.par` | Partition definition details where still used | Data dictionary tables; InnoDB already had native partitioning since MySQL 5.7 |
| `db.opt` | Default database charset and collation | Data dictionary tables |
| `.isl` | Path to an InnoDB file-per-table tablespace placed outside the data directory | Tablespace info in the data dictionary |
| `ddl_log.log` | Logged metadata operations produced by certain DDL statements | New DDL mechanism and dictionary |

This table describes the general roles of the removed files. Not every version or storage engine created all of these file types. For example, InnoDB stopped using `.par` partition files once it supported native partitioning in MySQL 5.7.

### 2.3. Metadata in system tables and storage engines

Some legacy system information was stored in tables within the `mysql` schema. For example, older versions stored stored routine and event definitions in system tables such as `proc` and `event`. Those tables were not synonymous with `.frm` files.

InnoDB also maintained an internal dictionary to manage tables, indexes, tablespaces, and engine-level objects. In the legacy architecture, server-level metadata and InnoDB's internal dictionary served different roles yet had to describe the same object consistently.

This made metadata management more complex: a single DDL operation might have to update multiple places. After crashes or improper file operations, the state of metadata files, system tables, and engine dictionaries could fall out of sync.

### 2.4. Why the file-based architecture caused difficulties

Limitations of distributed metadata storage included:

- The server had to manage and read many definition files.
- Scanning files and looking up metadata could be costly.
- Server-level metadata and storage-engine metadata had to be kept synchronized.
- Filesystem errors, missing files, or file corruption could prevent the server from opening tables.
- Crash recovery, replication, and DDL handling were more complex.
- Extending metadata for new object types or features was difficult.
- Backup and restore tools had to understand all relevant metadata files.

For example, if a `.frm` file went missing while the InnoDB data file remained, the server could fail to open the table normally even though the physical data was not necessarily lost. If the definition in the file and InnoDB's internal dictionary disagreed, upgrades or opening the table could fail.

Do not manually edit files to match a dictionary or fabricate replacement files by renaming. Always determine the exact version, storage engine, and supported recovery procedure.

## 3. The Transactional Data Dictionary Since MySQL 8.0

MySQL 8.0 replaced the distributed metadata architecture with a centrally managed transactional data dictionary.

### 3.1. Metadata stored in InnoDB

Internal dictionary tables belong to the `mysql` system schema and use InnoDB. These tables are protected; users cannot query or modify them directly in the normal way.

MySQL provides more stable interfaces for viewing metadata:

- `INFORMATION_SCHEMA`: information about schemas, tables, columns, indexes, routines, triggers, partitions, and many other objects.
- `SHOW`: statements such as `SHOW CREATE TABLE`, `SHOW COLUMNS`, `SHOW INDEX`, `SHOW TRIGGERS`.
- `Performance Schema`: observability information on server activity, locks, and events.
- `sys`: diagnostic helper views built atop Performance Schema and other sources.

These interfaces abstract away the internal storage layout. Applications should rely on them rather than depending on internal dictionary table names.

### 3.2. Benefits of the transactional data dictionary

Compared to the legacy architecture, the new data dictionary provides:

- **Centralized management:** object metadata is managed within a unified dictionary schema.
- **Transactional and crash-safe:** metadata changes are stored via InnoDB mechanisms, supporting consistent recovery after crashes.
- **Atomic DDL:** supported DDL operations can execute atomically, including dictionary updates and related changes.
- **Unified metadata cache:** dictionary objects are cached in memory and can be reused.
- **INFORMATION_SCHEMA integration:** many metadata views query the data dictionary directly, allowing the optimizer to use underlying indexes.
- **Extensibility:** adding new attributes and object types is cleaner than relying on rigid file formats.

### 3.3. Atomic DDL is not rolling back DDL inside user transactions

Atomic DDL ensures that the server completes a supported DDL operation entirely or recovers cleanly upon error/crash. It does not mean every DDL statement can be undone with `ROLLBACK` inside an application transaction.

For instance, many `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE` statements still trigger an implicit commit. Separate the two concepts:

- Atomic DDL: guarantees server-level consistency while executing a supported DDL operation.
- DML transactions: manage row data changes using `START TRANSACTION`, `COMMIT`, and `ROLLBACK`.

## 4. Comparing Old and New Architectures

| Criterion | Before MySQL 8.0 | MySQL 8.0 and later |
|---|---|---|
| Metadata source | Metadata files, system tables, and per-engine dictionaries | Centralized transactional data dictionary |
| Table definitions | Server-layer `.frm` files | Dictionary tables |
| Triggers | `.TRG`, `.TRN` files | Dictionary tables |
| Partition definitions | Possible `.par` files depending on engine/version | Dictionary tables |
| Default database charset/collation | `db.opt` file | Dictionary tables |
| Dictionary storage | Distributed, including non-transactional components | InnoDB |
| Metadata crash safety | Complex due to multiple storage sources | Transactional, crash-safe |
| DDL | Had to synchronize multiple metadata sources | Atomic DDL for supported operations |
| Metadata queries | Some interfaces had to aggregate from multiple sources | `INFORMATION_SCHEMA` integrated with data dictionary |
| Caching | Multiple per-layer caching mechanisms | Centralized Dictionary Object Cache |
| Manual file management | Some legacy procedures depended on metadata files | Table definitions no longer managed via `.frm` files |

Important point: MySQL 8.0 did not eliminate all files in the data directory. It eliminated **the files used to store metadata under the legacy architecture**. Data files and tablespaces still exist per storage engine.

## 5. Files That Still Exist After Removing .frm

A common misconception is that MySQL 8.0 no longer has physical files for tables. In reality, the data dictionary and data files serve distinct roles.

| File or file type | Role | Still used in MySQL 8.0+? |
|---|---|---|
| `.ibd` | InnoDB file-per-table or general tablespace | Yes |
| `ibdata*` | InnoDB system tablespace, which may contain system data and InnoDB structures | Yes |
| `.MYD` | MyISAM table data | Yes, if MyISAM is used |
| `.MYI` | MyISAM table indexes | Yes, if MyISAM is used |
| Redo log | Logs changes for InnoDB recovery | Yes |
| Undo tablespace/log | Supports MVCC and rollback | Yes |
| `.frm` | Server-layer table definition metadata | No longer used since MySQL 8.0 |
| `.TRG`, `.TRN` | Legacy trigger metadata | No longer used since MySQL 8.0 |
| `db.opt` | Legacy default database charset/collation metadata | No longer used since MySQL 8.0 |

An `.ibd` file can contain data, indexes, and serialized dictionary information (SDI). It is not a new kind of `.frm` file; its structure, purpose, and usage are different.

## 6. Serialized Dictionary Information (SDI)

Starting in MySQL 8.0.3, MySQL also stores metadata in serialized dictionary information, abbreviated **SDI**.

SDI is a JSON-serialized representation of metadata. Its role is to provide an auxiliary metadata representation inside tablespaces, supporting operations such as transportable tablespaces and recovering object information in certain scenarios.

### 6.1. Where is SDI stored?

- InnoDB stores SDI inside tablespace files, such as file-per-table `.ibd`, general tablespaces, the system tablespace, and the dictionary tablespace `mysql.ibd`.
- NDB stores SDI in the NDB dictionary.
- Other storage engines may store SDI as `.sdi` files inside database directories.
- For MyISAM, `.sdi` files play a role in `IMPORT TABLE` operations.

SDI inside an InnoDB tablespace describes only the tables and tablespace objects belonging to that tablespace. It is not a full copy of the entire server's data dictionary.

### 6.2. Extracting SDI with ibd2sdi

MySQL provides the `ibd2sdi` utility to extract SDI from InnoDB tablespace files.

Example:

~~~bash
ibd2sdi /var/lib/mysql/sales/orders.ibd
~~~

Save SDI to a JSON file:

~~~bash
ibd2sdi --dump-file=orders-sdi.json /var/lib/mysql/sales/orders.ibd
~~~

The output contains JSON records with identifiers, object types, and metadata values. The tool can read tablespace files while the server is running or offline, though at certain moments involving DDL, rollbacks, or undo purging, reading SDI can temporarily fail.

Keep these limitations in mind:

- `ibd2sdi` only extracts SDI metadata; it does not recover data rows.
- SDI describes only objects belonging to the tablespace being read.
- It does not replace full backups, redo/undo recovery, or restore procedures.
- Do not modify `.ibd` files or JSON SDI and place them back into `datadir` as a way to alter schemas.
- Importing tablespaces must follow supported InnoDB procedures and compatibility requirements.

SDI is an important distinction: MySQL 8.0 does not use `.frm`, yet can still store a metadata representation inside tablespaces for specific technical purposes.

## 7. Reading Metadata Properly in MySQL 8.0+

Instead of reading internal files, use supported SQL interfaces.

### 7.1. Viewing table definitions

~~~sql
SHOW CREATE TABLE sales.orders\G
~~~

This returns DDL you can use to inspect columns, indexes, constraints, engine, charset, and table options.

### 7.2. Viewing table list and storage engines

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE,
    TABLE_COLLATION
FROM information_schema.tables
WHERE TABLE_SCHEMA = 'sales'
ORDER BY TABLE_NAME;
~~~

### 7.3. Viewing column metadata

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

### 7.4. Viewing indexes

~~~sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

### 7.5. Viewing triggers

~~~sql
SHOW TRIGGERS FROM sales;
~~~

Or:

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_STATEMENT
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = 'sales'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;
~~~

### 7.6. Viewing views, routines, and events

~~~sql
SHOW CREATE VIEW sales.active_orders\G
SHOW CREATE PROCEDURE sales.recalculate_order_total\G
SHOW EVENTS FROM sales;
~~~

When taking logical backups, remember that routines and events must be included in dumps using the appropriate options such as `--routines` and `--events`. Do not assume that a full database dump always includes every object type automatically in the exact same way across versions.

## 8. Operational Differences When Upgrading from Older Versions

Moving from MySQL 5.7 to MySQL 8.0 is not simply swapping binaries. The server must migrate metadata from the legacy architecture to the transactional data dictionary.

### 8.1. Controlled upgrade process

Before upgrading:

1. Read the official upgrade guide for both the source and target versions.
2. Check the version, OS, configuration, plugins, storage engines, and applications.
3. Check compatibility of schemas, triggers, routines, events, and data types.
4. Check for orphaned `.frm` files and metadata errors detected by upgrade tools.
5. Take a consistent backup and test restoring it into an isolated environment.
6. Dry-run the upgrade process on a copy closely matching production.
7. Plan downtime, monitoring, and contingency actions if the upgrade fails.

For example, the MySQL 8.4 documentation provides an upgrade check command:

~~~bash
mysqlcheck -u root -p --all-databases --check-upgrade
~~~

This command requires an appropriate account and must be used following the target version's instructions. It helps catch certain compatibility issues, but does not replace a full readiness validation process.

### 8.2. What happens when the server starts on the new version?

In a supported upgrade process, MySQL Server checks the data dictionary version. If an upgrade is needed, the server creates/updates dictionary tables, migrates stored metadata to the new definitions, and reinitializes the dictionary.

Once complete, legacy metadata files are removed as part of the upgrade process. For instance, after a successful upgrade, you no longer see `.frm` files alongside tables as in MySQL 5.7.

Do not manually delete metadata files before the server performs the upgrade. Do not copy `.frm` files from an old server into a MySQL 8.0 `datadir`. Do not start a new server with a `datadir` cobbled together manually from inconsistent sources.

### 8.3. Can you downgrade by starting the old binary?

Once the data dictionary has been upgraded, you cannot by default restart using the old version's binary. Dictionary formats and structures may have changed; arbitrary in-place downgrades are not supported.

If you need to revert to an older version, have a tested plan—typically based on a pre-upgrade backup or compatible logical dump/restore. Do not treat retaining `.frm` files or copying the old `datadir` haphazardly as a rollback plan.

### 8.4. Backups are no longer copying individual metadata files

With MySQL 8.0+, backups must preserve the data dictionary alongside data and related engine structures. Use supported backup tools:

- Logical backups such as `mysqldump` or MySQL Shell dump utilities.
- Physical backups compatible with the server version and configuration.
- Snapshots supported by managed database providers, under documented consistency conditions.

With `mysqldump`, specify the proper options to include stored routines and events, such as `--routines` and `--events`. After backing up, test restoring into an isolated environment and verify schemas, data, triggers, routines, events, privileges, and applications.

## 9. Investigation Example: A Table Has an .ibd File Without .frm

Suppose you receive a copy of a MySQL 8.0 data directory and see:

~~~text
/var/lib/mysql/sales/
    orders.ibd
~~~

You do not see `orders.frm` and conclude that the metadata file is missing.

That conclusion is wrong if the server is actually running MySQL 8.0 or later. MySQL no longer uses `.frm` files to store table definitions. Primary metadata is managed in the transactional data dictionary. With InnoDB, the `.ibd` file also contains the table's and tablespace's SDI.

Correct investigation steps:

1. Determine the exact server version and which version the data directory belongs to.
2. If the server is running, use `SHOW CREATE TABLE sales.orders` and `INFORMATION_SCHEMA.TABLES` to inspect the table.
3. If the server is offline and you need to inspect metadata inside the tablespace, run `ibd2sdi` on an appropriate copy of the `.ibd` file.
4. Determine whether it is a valid file-per-table tablespace with all necessary files and structures.
5. If the goal is restoring the table, follow supported backup/restore or transportable tablespace procedures for the exact version.
6. Never fabricate a `.frm` file, rename files, or drop files into `datadir` to try to make the server recognize the table.

If it is a MySQL 5.7 `datadir`, a missing `.frm` has a very different meaning and may indicate lost metadata. Always identify the version before drawing conclusions.

## 10. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| `.frm` files contain all table data | `.frm` held server-layer metadata definitions; data and indexes resided per storage engine |
| MySQL 8.0 has no physical files for tables | Data and tablespace files such as `.ibd`, `ibdata*`, `.MYD`, and `.MYI` still exist |
| All legacy metadata lived only in `.frm` | Metadata was split across files, system tables, and per-engine dictionaries |
| InnoDB before 8.0 had no own dictionary | InnoDB had an internal data dictionary alongside server-layer metadata |
| You can copy `.frm` to MySQL 8.0 to recover a table | MySQL 8.0 does not use `.frm`; use backup/restore or supported tablespace workflows |
| You can directly edit dictionary tables in the `mysql` schema | Dictionary tables are protected; use `SHOW` and `INFORMATION_SCHEMA` |
| SDI is the new `.frm` file | SDI is JSON metadata stored inside tablespaces or `.sdi` files depending on the engine |
| `ibd2sdi` can recover an entire table | `ibd2sdi` only extracts SDI metadata; it does not recover data rows |
| Atomic DDL means every DDL can be rolled back | Atomic DDL is a server-level atomicity mechanism for supported operations |
| Copying a database directory while the server is running is a valid backup | You must use consistent, supported backup methods |

## 11. Checklist When Working with Schema Metadata

- [ ] Confirmed the MySQL version before inspecting metadata files.
- [ ] Understood the historical roles of `.frm`, `.TRG`, `.TRN`, `.par`, and `db.opt`.
- [ ] Distinguished metadata files from data/index files such as `.ibd`, `.MYD`, and `.MYI`.
- [ ] Understood that legacy metadata was distributed across the server, system tables, and storage engines.
- [ ] Aware that the transactional data dictionary arrived in MySQL 8.0.
- [ ] Never read or modify internal dictionary tables directly.
- [ ] Use `SHOW` and `INFORMATION_SCHEMA` to inspect schemas.
- [ ] Understand the role of SDI and the limitations of `ibd2sdi`.
- [ ] Have a consistent backup before upgrading.
- [ ] Checked for orphaned `.frm` files and compatibility prerequisites when upgrading from older versions.
- [ ] Tested restoring and verified routines, triggers, events, privileges, and data.
- [ ] Have a rollback plan based on a tested backup.

## 12. Hands-On Exercises

### Exercise 1: Survey a table's metadata

Choose a table in a practice database and run:

~~~sql
SHOW CREATE TABLE sales.orders\G

SELECT *
FROM information_schema.columns
WHERE table_schema = 'sales'
  AND table_name = 'orders'
ORDER BY ordinal_position;

SELECT *
FROM information_schema.statistics
WHERE table_schema = 'sales'
  AND table_name = 'orders'
ORDER BY index_name, seq_in_index;
~~~

Record the columns, data types, indexes, engine, and charset. Explain how metadata differs from row data.

### Exercise 2: Compare old and new architectures

Based on MySQL 5.7 and MySQL 8.4 documentation, build a comparison table for the roles of:

- `.frm`
- `.TRG` and `.TRN`
- `db.opt`
- InnoDB's internal dictionary
- Transactional data dictionary

Explain why `.frm` files are gone in MySQL 8.0 while `.ibd` files remain.

### Exercise 3: Inspect SDI

On a MySQL 8.0+ machine with access to tablespace files, use `ibd2sdi` to export an InnoDB table's metadata to JSON. Read the table name, column, index, and tablespace properties.

Perform this only in a lab environment or on an appropriate copy. Never modify tablespace files.

### Exercise 4: Prepare an upgrade checklist

Simulate a plan to migrate a MySQL 5.7 instance to 8.0. List:

- Backup and test restore.
- Checking for orphaned `.frm` files.
- Checking triggers, routines, events, and engines.
- Checking application and connector versions.
- Timing window to run the upgrade.
- Verifying metadata and data post-upgrade.
- A fallback plan using backups if needed.

## 13. Conclusion

Before MySQL 8.0, metadata was scattered across files such as `.frm`, `.TRG`, `.TRN`, `.par`, `db.opt`, system tables, and storage-engine dictionaries. This layout forced the server to maintain consistency across multiple storage sources.

MySQL 8.0 moved to a centralized transactional data dictionary backed by InnoDB, supporting crash-safe metadata, atomic DDL, and unified metadata interfaces. Legacy metadata files were removed, while data and tablespace files remain. SDI provides an auxiliary serialized metadata representation inside tablespaces, aiding specific technical operations and investigations.

In administration, always confirm the exact version and storage engine, use `SHOW` and `INFORMATION_SCHEMA` to read metadata, use proper tools for backup/restore, and follow upgrade procedures. Never manipulate internal metadata files by hand or mistake the absence of `.frm` for an error on MySQL 8.0+.

## Official References

- [MySQL 8.4 Reference Manual – MySQL Data Dictionary](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary.html)
- [MySQL 8.4 Reference Manual – Removal of File-based Metadata Storage](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-file-removal.html)
- [MySQL 8.4 Reference Manual – Transactional Storage of Dictionary Data](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-transactional-storage.html)
- [MySQL 8.4 Reference Manual – Data Dictionary Schema](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-schema.html)
- [MySQL 8.4 Reference Manual – Serialized Dictionary Information (SDI)](https://dev.mysql.com/doc/refman/8.4/en/serialized-dictionary-information.html)
- [MySQL 8.4 Reference Manual – ibd2sdi utility](https://dev.mysql.com/doc/refman/8.4/en/ibd2sdi.html)
- [MySQL 8.4 Reference Manual – Data Dictionary Usage Differences](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-usage-differences.html)
- [MySQL 8.4 Reference Manual – Preparing Your Installation for Upgrade](https://dev.mysql.com/doc/refman/8.4/en/upgrade-prerequisites.html)
- [MySQL 8.4 Reference Manual – Upgrade Troubleshooting](https://dev.mysql.com/doc/refman/8.4/en/upgrade-troubleshooting.html)
- [MySQL 5.7 Reference Manual – File Locations](https://dev.mysql.com/doc/refman/5.7/en/data-directory.html)
