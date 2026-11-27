# `mysqldump`: Database/Table Scope and Included Objects

`mysqldump` is MySQL's command-line utility for exporting schemas and data as SQL statements. The export scope is determined by the database names, table names, and accompanying options. Choosing the right scope produces a backup sufficient for recovery objectives, reduces unnecessary data, and avoids missing objects such as stored procedures, events, or triggers.

This lesson belongs to the **Backup and Recovery** chapter of the `DATABASE_MYSQL` module. The module spans from table design, querying, and tuning to transactions, privilege management, backup, and relational database operations. This lesson focuses on defining what `mysqldump` exports, how to select databases/tables, how to handle related objects, and how to verify results. Examples use MySQL 8.0 syntax; check `mysqldump --help` and the documentation for your exact client/server version before applying in production.

After this lesson, you will be able to:

- Choose between dumping an entire server, one or more databases, and a set of tables.
- Distinguish exporting schema only, data only, and both.
- Explicitly include views, triggers, stored routines, and events in a dump.
- Use options to filter tables or rows when clearly required.
- Select a snapshot approach suited to the storage engine and level of concurrent writes.
- Inspect dump files and perform test restores to confirm actual scope.

## 1. How `mysqldump` Determines Scope

The general syntax has three main forms:

```bash
# One database, optionally selecting one or more tables
mysqldump [options] db_name [table_name ...]

# One or more databases
mysqldump [options] --databases db_name [db_name ...]

# All databases that the command can dump
mysqldump [options] --all-databases
```

The key point to remember is that argument positions and interpretation change based on the option:

- When invoking `mysqldump db_name`, the first name is the database. Any following names, if present, are tables in that database.
- When using `--databases`, all following names are interpreted as database names. Do not append table names after a list of databases expecting them to be treated as tables.
- When using `--all-databases`, the utility selects the database scope automatically; do not pass database names.

For example, the following command exports all tables in the `sales` database:

```bash
mysqldump -u backup_user -p sales > sales.sql
```

The command below exports only the two specified tables:

```bash
mysqldump -u backup_user -p sales orders order_items > sales-orders.sql
```

To export multiple databases:

```bash
mysqldump -u backup_user -p --databases sales inventory > business-databases.sql
```

And to export server-wide scope:

```bash
mysqldump -u backup_user -p --all-databases > instance.sql
```

Database and table names in the examples are illustrative. The dump account needs privileges to read metadata and the data to be exported, plus additional privileges depending on the options and MySQL version.

### 1.1. Dumping a Single Database

This is a common choice when an application owns a dedicated database:

```bash
mysqldump --user=backup_user --password sales > sales.sql
```

The client will prompt for the password interactively. Do not write passwords directly on the command line, in shared scripts, or in shell history. In automated environments, use an appropriate credential storage mechanism, such as a login path or a configuration file with restricted read permissions.

When passing only `sales`, `mysqldump` exports the objects belonging to that database according to the active options. The command does not mean the entire server was backed up: other databases, server configuration, and resources outside the database may not be in the file.

If you need the dump file to contain database creation statements for recovery, use `--databases`:

```bash
mysqldump --user=backup_user --password --databases sales > sales-with-database.sql
```

`--databases` adds database creation/selection statements such as `CREATE DATABASE` and `USE` to the output. This is helpful when restoring to another server or when the target database does not yet exist. If you only dump a single database without `--databases`, prepare the target database before importing.

### 1.2. Dumping Multiple Databases

```bash
mysqldump --user=backup_user --password \
  --databases sales inventory reporting \
  > selected-databases.sql
```

Each database is included in the file according to the selected scope. During restore, the database creation and selection statements in the file control where objects are created. Check the database names inside the file before importing into an environment with existing data.

### 1.3. Dumping the Entire Server

```bash
mysqldump --user=backup_user --password \
  --all-databases \
  > full-instance.sql
```

`--all-databases` is suitable when the goal is to export a broad database scope across a MySQL instance. However, do not assume an `--all-databases` file is a complete backup of every server component. Special system schemas such as `performance_schema` and `information_schema` are handled specially; external server configs, configuration files, keyrings, plugins, TLS certificates, binary logs, and other infrastructure components must be handled according to recovery goals.

For accounts and privileges, clearly define operational requirements. If user identities and privileges need to be recreated, verify the exact system database contents included in the dump and the restore workflow for your version; you may need to separately save the output of `SHOW CREATE USER` and `SHOW GRANTS` for critical accounts. Never treat an application data dump as proof that users, roles, and access policies were preserved.

## 2. Selecting Specific Databases and Tables

### 2.1. Dumping Only Specific Tables

When only a subset of data is needed, list table names after the database name:

```bash
mysqldump --user=backup_user --password \
  sales orders order_items customers \
  > sales-core-tables.sql
```

This command selects three tables in the `sales` database. It is useful for moving a group of tables, creating test data copies, or performing partial recovery. Check dependencies: a table may reference a foreign key on another table, a view may read multiple tables, and routines may use tables outside the dump scope.

A table dump does not automatically become a standalone recovery package. For example, if `order_items` has a foreign key referencing `orders`, restoring `order_items` alone may fail or produce data violating constraints if the parent table and corresponding rows do not yet exist.

### 2.2. Excluding a Table

`--ignore-table` excludes a specific table from the dump scope. The value must include both the database and table:

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --ignore-table=sales.audit_log \
  --ignore-table=sales.request_cache \
  > sales-without-logs.sql
```

You can repeat the option to ignore multiple tables. Double-check the full `database.table` name; ignoring the wrong table can leave the restore missing business data or objects that views/routines depend on.

Excluding a table from a dump can omit both its definition and its data. If the goal is to keep the structure without exporting data rows, consider `--no-data` for the whole scope or a per-table data-skip feature if supported by your client version. Options to skip data per table may vary across versions; verify with `mysqldump --help` before putting them into scripts.

### 2.3. Filtering Rows with WHERE

`--where` lets you export only rows matching an SQL condition for a dumped table. For example, exporting orders created from a certain date onward:

```bash
mysqldump --user=backup_user --password \
  sales orders \
  --where="created_at >= '2026-01-01'" \
  > recent-orders.sql
```

The condition is sent to MySQL, so you must use valid SQL syntax and quote it properly for the shell in use. Test a `SELECT` query with the same condition before dumping to know the exact number of rows that will be exported.

Dumping with `WHERE` is typically used for a single table and a selected subset of data. It does not automatically apply a consistent business filter across related tables. For example, filtering orders by date while dumping all of `order_items` can create mismatched datasets. If you need a consistent sample across multiple tables, intentionally design the target ID set and related extraction steps.

Do not use `--where` as a data-masking mechanism in place of proper authorization. The dump may still contain metadata, object definitions, or other tables; inspect the file and protect permissions on the output file.

## 3. Choosing Schema, Data, or Both

Two foundational options control file contents:

| Option | Main Content | Common Purpose |
|---|---|---|
| Default | Schema and data of selected tables | Back up database for full table-scope recovery. |
| `--no-data` | Schema only, no data rows exported | Create schemas for new environments, review DDL, or prepare an empty database. |
| `--no-create-info` | Data only, no table creation statements | Load data into an existing, compatible schema. |

### 3.1. Exporting Schema Only

```bash
mysqldump --user=backup_user --password \
  --no-data --databases sales \
  > sales-schema.sql
```

This file is useful when standing up schemas in test environments or comparing table definitions. However, schema-only does not mean only `CREATE TABLE`: related objects may be exported depending on other options and client defaults. If you want to control routines, events, or triggers, specify the corresponding options explicitly.

### 3.2. Exporting Data Only

```bash
mysqldump --user=backup_user --password \
  --no-create-info --databases sales \
  > sales-data.sql
```

A data-only file requires a compatible target schema. Column count, column order, data types, charsets, collations, keys, and constraints must match how the data was exported. If the schema changed between dump time and restore time, importing may fail or insert data into the wrong columns. Only use this approach when the target schema is managed and verified separately.

### 3.3. Controlling DROP Statements

The `--add-drop-table` option adds `DROP TABLE` before table creation statements. This option is commonly enabled via `mysqldump`'s default `--opt` group. During restore, a target table with the same name can be dropped and recreated.

```bash
mysqldump --user=backup_user --password \
  --skip-add-drop-table --databases sales \
  > sales-no-drop.sql
```

`--skip-add-drop-table` prevents the output from proactively adding drop-table statements. Read the dump file before restoring; other options, deployment scripts, or customized content can still affect target data. For databases with existing data, always test restoring in an isolated environment first.

## 4. Objects Accompanying Tables and Databases

Backing up is not just copying rows in tables. An application may depend on views, triggers, stored procedures, functions, and the event scheduler. Each object group has its own export behavior.

| Object | `mysqldump` Behavior | Options to Know |
|---|---|---|
| Tables and data | Exported according to selected database/table scope | Default; adjust with `--no-data` or `--no-create-info`. |
| Views | Exported within matching database/table scope as view definitions | Check views that depend on other tables or views. |
| Triggers | Dumped by default for selected tables in current versions | `--skip-triggers` disables trigger export. |
| Stored procedures and functions | Not exported by default in many configurations | `--routines` enables exporting stored routines. |
| Events | Not exported by default | `--events` enables exporting scheduled events. |

### 4.1. Views

A view stores a query definition based on one or more tables or other views. When dumping a database, views in that scope are normally included in the output. However, if dumping only specific tables, do not assume every dependent view will be exported as expected. Inspect the view list and dependencies before selecting a table scope.

Example of checking views in a database:

```sql
SELECT TABLE_NAME, VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'sales';
```

Permission to view a view definition may depend on account privileges and version. For critical views, additionally inspect `SHOW CREATE VIEW sales.order_summary`.

### 4.2. Triggers

Triggers are attached to tables and execute automatically on events such as `INSERT`, `UPDATE`, or `DELETE`. `mysqldump` exports triggers for dumped tables by default; `--skip-triggers` disables this.

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --triggers \
  > sales-with-triggers.sql
```

`--triggers` is enabled by default in current MySQL versions, but writing it explicitly in scripts clarifies intent and aids review. Triggers can depend on other tables, routines, or `DEFINER` privileges. If dumping only a single table, check which objects its triggers call or update.

### 4.3. Stored Procedures and Functions

Stored procedures and stored functions are not exported by default in many configurations. Use `--routines` when they must be preserved:

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --routines \
  > sales-with-routines.sql
```

If schema, data, routines, and events are all needed, combine them:

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --routines --events --triggers \
  > sales-application-backup.sql
```

When restoring routines, pay attention to `DEFINER`, `SQL SECURITY`, the privileges of the owning account, and the objects accessed by the routine. A routine can dump cleanly yet fail after restore if the `DEFINER` account does not exist, its privileges changed, or dependencies have not been restored.

### 4.4. Events

Events are scheduled tasks executed by the MySQL Event Scheduler. Use `--events` to export event definitions:

```bash
mysqldump --user=backup_user --password \
  --databases reporting \
  --events \
  > reporting-with-events.sql
```

After restoring, check the Event Scheduler status on the target server and the status of each event. Do not enable automated schedules unchecked when restoring production into staging or test environments; events might send notifications, purge data, or run periodic jobs unexpectedly.

### 4.5. Summary Command for an Application Backup

A commonly used command when dumping an application database together with routines, events, and triggers:

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases sales \
  > sales-backup.sql
```

This command selects the `sales` database, exports schema and data by default, and requests routines, events, and triggers. `--single-transaction` and `--quick` affect how data is read; they do not expand database scope.

## 5. Choosing Options Based on Dump Goals

The options below are commonly used when writing backup scripts. Read `mysqldump --help` on the exact host running the backup to confirm available options.

| Option | Effect | Notes |
|---|---|---|
| `--databases` | Selects one or more databases and includes database creation/selection statements in output | Subsequent arguments are database names. |
| `--all-databases` | Selects instance-wide database scope | Does not replace backing up configuration and non-database components. |
| `--ignore-table=db.table` | Excludes the specified table from the dump | Repeatable; document reasons for exclusion. |
| `--where='condition'` | Filters table rows using an SQL condition | Verify the condition and consistency with related data. |
| `--no-data` | Exports schema only | Useful for schema-only dumps. |
| `--no-create-info` | Omits table creation statements | Only suitable when the target schema already exists and is compatible. |
| `--routines` | Exports stored procedures and functions | Verify `DEFINER` and privileges on restore. |
| `--events` | Exports scheduled events | Check Event Scheduler on the target server. |
| `--triggers` | Exports triggers for tables in scope | Typically on by default; `--skip-triggers` disables it. |
| `--single-transaction` | Creates a consistent snapshot for transactional data like InnoDB | Does not guarantee snapshots for non-transactional tables; avoid concurrent DDL. |
| `--quick` | Streams rows one by one instead of buffering the entire result set in client memory | Usually enabled in the default `--opt` option group. |
| `--hex-blob` | Exports binary data in hexadecimal format | Useful for `BINARY`, `VARBINARY`, `BLOB`, and binary data. |
| `--default-character-set=utf8mb4` | Specifies connection charset during dump | Charset must be compatible with data and environment. |
| `--no-tablespaces` | Omits tablespace/logfile group statements from output | Use when recreating those definitions is unnecessary or to avoid related privilege requirements. |

Do not copy a single option set across every system. Determine recovery objectives, storage engines, data sizes, backup account privileges, and client capabilities before finalizing the command.

## 6. Dump Consistency

Selecting the right databases and tables is not enough. The dump must also reflect a coherent data state at a single point in time.

### 6.1. InnoDB and `--single-transaction`

For InnoDB tables, `--single-transaction` tells `mysqldump` to open a transaction to read a consistent snapshot. Normal writes can continue during the dump, and the dump reflects data as of the transaction snapshot.

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  --databases sales \
  > sales-consistent.sql
```

For meaningful results, keep in mind:

- This snapshot applies to transactional engines such as InnoDB.
- MyISAM tables or other non-transactional engines are not protected by the transactional snapshot; data can change during the dump.
- Avoid concurrent DDL operations such as `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE` on objects being dumped. DDL can cause the dump to fail or leave results no longer reflecting the desired state.
- `--single-transaction` does not replace a locking strategy if the scope includes non-transactional tables.

`--quick` makes the client stream rows, reducing the need to buffer entire query results in memory. It is helpful for large tables and is normally enabled by default via `--opt`.

### 6.2. When Non-Transactional Tables Are Present

If consistency is required for non-transactional tables, you may need an appropriate read-locking mechanism, such as `--lock-all-tables`. This option acquires a global read lock during the dump and can block writes, directly impacting production operations.

```bash
mysqldump --user=backup_user --password \
  --lock-all-tables --quick \
  --databases legacy_app \
  > legacy-app-locked.sql
```

Only choose a locking approach after assessing dump duration, data size, write load, and outage tolerance. Never enable server-wide locking habitually for every database. If a system uses multiple storage engines, classify tables before picking a strategy.

### 6.3. DDL and Schema Changes During a Dump

A data snapshot does not automatically protect against concurrent structural changes. During the backup window, coordinate with migration workflows to avoid modifying or renaming objects being dumped. In continuous deployment environments, establish clear conventions around migration, backup, and restore-test timing.

## 7. Privileges and Credentials Required for `mysqldump`

The backup account needs sufficient privileges to read data and metadata within the chosen scope. Options like dumping routines, events, tablespaces, or replication info may require additional privileges depending on server version and configuration.

Create a dedicated account and grant privileges matching the backup scope. Illustrative example for a single database:

```sql
CREATE USER 'backup_user'@'10.20.%'
  IDENTIFIED BY 'replace-with-a-unique-secret';

GRANT SELECT, SHOW VIEW, TRIGGER, EVENT
ON sales.*
TO 'backup_user'@'10.20.%';
```

This is only a basic privilege example for certain dump needs; it is not a complete privilege set for every version and option. Check the documentation for your running version, test the command using the actual backup account, and add the minimum required privileges if specific errors occur. Some operations may require global or dynamic privileges.

Do not use the `root` account merely to avoid managing privileges. Store credentials using an appropriate mechanism, restrict read permissions on configuration files, protect the dump file since it may contain sensitive data, and never place passwords on the command line or in logs.

## 8. Restoring a Dump File

Files generated by `mysqldump` are typically SQL statements. Use the `mysql` client to execute the file.

If the file was created with `--databases`:

```bash
mysql --user=restore_user --password < sales-with-database.sql
```

The `CREATE DATABASE` and `USE` statements inside the file determine the target database. If the file was created with just `mysqldump sales` and lacks database creation statements, create the database first and then import:

```sql
CREATE DATABASE sales;
```

```bash
mysql --user=restore_user --password sales < sales.sql
```

For dumps containing only a few tables, prepare dependent tables and the target schema before importing. For dumps with `--no-create-info`, you must verify the schema already exists and is compatible. For dumps containing routines or events, check that the restore account has privileges to create those objects and that `DEFINER` is valid on the target server.

Before restoring into production, verify whether the file contains `DROP` statements, whether the target database shares the same name as the source database, and how existing data will be overwritten. Use an isolated environment to test the entire workflow.

## 9. Verifying Dump Scope and Quality

A command finishing with a zero exit code is not enough to prove a backup is usable. Inspect the file, its contents, and its restorability.

### 9.1. Checking Command Execution and Output File

Record client versions:

```bash
mysqldump --version
mysql --version
```

In automated scripts, check the exit code of `mysqldump` before marking a job successful. When using shell redirection `>`, the shell can create an empty file even if the dump command fails; verify file size, modification timestamp, and error logs. Log `stderr` separately in scripts for investigation.

### 9.2. Checking Present Objects

Open the dump file with a text viewer and confirm expected sections exist:

- `CREATE DATABASE` and `USE` if `--databases` was selected.
- `CREATE TABLE` along with insert statements if both schema and data were dumped.
- `CREATE VIEW` for views in scope.
- `CREATE TRIGGER` for triggers requiring recovery.
- `CREATE PROCEDURE` or `CREATE FUNCTION` when `--routines` was used.
- Event definitions when `--events` was used.

You can search strings with `grep` or an equivalent tool, though string searching is only a quick sanity check. Syntax, `DEFINER` conditions, and dependencies must be verified via an actual restore.

### 9.3. Performing a Test Restore

Restore into a test instance or database of a compatible version. Then:

1. Check the counts of created databases, tables, views, and routines.
2. Compare row counts of critical tables against figures from backup time or appropriate control reports.
3. Run representative business queries and verify foreign key constraints.
4. Check triggers, stored routines, and events; prevent staging events from accidentally running production tasks.
5. Inspect restore logs for warnings, charset errors, missing `DEFINER`s, or missing privileges.

A backup is only considered reliable when it can be restored within times and conditions meeting operational requirements. Schedule periodic restore tests rather than waiting for an incident to check.

## 10. Sample Scenarios

### Scenario A: Backing Up a Sales Database for Full Recovery

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases sales \
  > sales-full.sql
```

Scope: `sales` database, table schemas and data, routines, events, and triggers. Consistent snapshot applies to InnoDB tables; coordinate to avoid concurrent DDL. The file contains database creation/selection statements due to `--databases`.

### Scenario B: Backing Up Only Reporting Tables

```bash
mysqldump --user=backup_user --password \
  --single-transaction --quick \
  reporting daily_sales monthly_sales \
  > reporting-tables.sql
```

Scope: two selected tables in the `reporting` database. Check dependent views, routines, or tables if reports need them to function after restore.

### Scenario C: Creating an Empty Schema for a Test Environment

```bash
mysqldump --user=backup_user --password \
  --no-data --databases sales \
  > sales-empty-schema.sql
```

Scope: selected database and table structures, without data rows. Additionally verify whether views, triggers, routines, and events are included as required.

### Scenario D: Exporting a Subset of Orders for Analysis

```bash
mysqldump --user=backup_user --password \
  sales orders \
  --where="created_at >= '2026-01-01' AND status = 'completed'" \
  > completed-orders-sample.sql
```

Scope: rows in `sales.orders` matching the condition. If detail rows from `order_items` are needed, design an additional extraction step based on the selected `order_id` list; do not assume `mysqldump` infers data relationships automatically.

### Scenario E: Excluding Log Tables from a Dump

```bash
mysqldump --user=backup_user --password \
  --databases sales \
  --ignore-table=sales.audit_log \
  --ignore-table=sales.api_request_log \
  > sales-without-logs.sql
```

Scope: `sales` database excluding the two log tables. Before adopting, confirm these tables are truly recreatable or unnecessary for recovery goals. Document exceptions in backup documentation so recovery operators understand what data was excluded.

## 11. Common Scope Design Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Using `--databases sales orders` intending to dump table `orders` | `orders` is interpreted as a second database name | Use `mysqldump sales orders` to dump a table inside one database. |
| Dumping a few tables while forgetting foreign keys or dependent tables | Restore fails or data lacks referential integrity | List dependencies before selecting tables. |
| Omitting `--routines` | Procedures and functions are missing | Determine whether the application calls stored routines; enable `--routines` when needed. |
| Forgetting `--events` | Scheduled tasks are not recovered | Inventory events and include `--events` in scripts if needed. |
| Using `--skip-triggers` unintentionally | Automated table-attached logic is lost | Keep triggers in dumps or explicitly document reasons for removal. |
| Using `--no-create-info` with a different target schema version | Data mismatches structure or import fails | Check target DDL and perform a test restore. |
| Using `--single-transaction` with MyISAM and assuming all tables are consistent | Non-transactional tables may reflect different points in time | Classify storage engines and choose an appropriate locking strategy. |
| Running DDL during a dump | Dump may fail or not reflect the intended schema state | Coordinate migrations and backups within clear windows. |
| Only checking whether the file exists | May retain an empty file or a dump missing objects | Check exit code, contents, and restore tests. |

## 12. Process for Selecting and Verifying `mysqldump`

Before writing a backup command, answer these questions in order:

1. **What is the recovery goal?** Full instance recovery, one database, a set of tables, or sample data only?
2. **Which objects must be present?** List tables, views, triggers, stored procedures, functions, and events needed by the application.
3. **Are schema and data needed, or only a subset?** Choose default, `--no-data`, `--no-create-info`, `--where`, or `--ignore-table` according to the goal.
4. **Can data change during the dump?** Identify storage engines and choose `--single-transaction` or a suitable locking strategy.
5. **Is the backup account scoped narrowly enough?** Test with the exact job account and add minimal required privileges based on actual errors.
6. **Where can it be restored?** Prepare a test environment, compatible version, and restore account.
7. **Has the file been verified?** Check exit code, size, contents, objects, and restore results.

### Operational Checklist

- [ ] Command selects the right scope: `db_name`, `--databases`, or `--all-databases`.
- [ ] List of included or excluded tables has been reviewed.
- [ ] Schema and data are exported according to the goal.
- [ ] Views, triggers, routines, and events have been verified.
- [ ] Snapshot strategy fits InnoDB and any other engines in use.
- [ ] No conflicting DDL migrations occur during the dump window.
- [ ] Credentials are protected and the backup account has least-privilege access.
- [ ] Output file is verified for size, logs, and exit code.
- [ ] Test restore completed and critical business operations verified.
- [ ] Components outside the SQL file such as configuration, keyrings, plugins, and binary logs are handled by a separate recovery plan.

`mysqldump` is only useful when export scope matches recovery scope. Identify databases and tables first, inventory dependent objects, pick snapshot options per storage engine, and prove the dump can restore through a controlled test.
