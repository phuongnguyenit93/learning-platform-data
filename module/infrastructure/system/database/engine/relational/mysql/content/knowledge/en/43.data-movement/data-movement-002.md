# Exporting and Importing with mysqldump and Controlling Object Order

## Objectives

After this lesson, you will be able to:

- Choose the right dump scope: a single database, multiple databases, selected tables, schema only, or data only.
- Create a consistent dump for InnoDB workloads and understand the limitations of `--single-transaction`.
- Export tables, views, triggers, stored procedures, functions, and events completely.
- Restore a dump into the right target database with proper permissions and object dependency order.
- Handle foreign keys, `DEFINER`, character sets, GTIDs, and binary log metadata during data migration.
- Verify import results using structure, data, privileges, and business queries.

## 1. The Role of mysqldump

`mysqldump` is a MySQL command-line utility for exporting databases into a logical SQL file. This file typically contains statements to create schemas, create tables, insert data, and recreate selected database objects. During restoration, the MySQL client reads the SQL file and executes those statements on the target server.

Logical dumps are useful when:

- Moving databases between servers or environments.
- Copying a small or medium schema for testing.
- Exporting selected tables for inspection, exchange, or archival.
- Producing a readable, editable dump for selective recovery.
- Migrating between MySQL versions with appropriate SQL compatibility.

A logical dump differs from a physical backup in several ways. It recreates data via SQL, making it flexible, but for large databases export/import times can be long because MySQL must read every row, rebuild indexes, and execute `INSERT` statements. A successful dump also does not prove it can be restored cleanly; you must test the import on the target environment.

`mysqldump` is a client program. It connects to MySQL Server using a privileged account, reads metadata and data, and writes output to stdout or a file. A dump file does not automatically include everything on a server: server configuration, plugins, config files, encryption keys, OS accounts, binary logs, and infrastructure components must be managed separately.

## 2. Defining Scope Before Dumping

Before running the command, determine precisely what needs to be moved:

- Required databases/schemas and tables.
- Views and view dependency order.
- Triggers attached to tables.
- Stored procedures and stored functions.
- Event Scheduler status and defined events.
- Accounts, roles, privileges, and `DEFINER` objects.
- Relevant character sets, collations, SQL mode, and timezones.
- GTID or binary log coordinates if building a replica or continuing PITR.

Do not assume dumping a database automatically includes every object the application uses. `mysqldump` has dedicated options for routines and events; triggers are exported by default in modern versions, though specifying `--triggers` makes the intent explicit.

### 2.1. Objects and Options

| Object | How It Is Exported |
|---|---|
| Table definition | Exported by default |
| Table data | Exported by default |
| View | Exported as view definitions in the dump |
| Trigger | Exported by default; can specify `--triggers` explicitly |
| Stored procedure/function | Requires `--routines` |
| Event | Requires `--events` |
| Tablespace metadata | Can be omitted with `--no-tablespaces` if unnecessary or lacking privileges to read tablespace metadata |
| Accounts and privileges | Do not treat a regular application dump as a complete backup of the account system; maintain a separate user/role/grant migration process |

For an application database, a typical command is:

```bash
mysqldump \
  --host=db-source.example.internal \
  --user=backup_user \
  --password \
  --default-character-set=utf8mb4 \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  --databases sales_app \
  --result-file=sales_app.sql
```

`--password` without a value prompts interactively for the password. Never place passwords directly on the command line, in committed scripts, or in shell history. Use a secret manager or an organization-approved authentication mechanism when automating.

`--databases sales_app` causes the dump to include database selection/creation statements, allowing restoration without specifying a database at the end of the `mysql` command. If `--databases` is omitted, the dump normally contains only the objects and data of the selected schema; during import you must specify the target database.

### 2.2. Dumping All Databases or Selected Tables

Export all databases readable by the account:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --routines --events --triggers \
  --all-databases \
  --result-file=all-databases.sql
```

`--all-databases` may include system schemas. Do not use this command as a way to migrate accounts or replace full-server backup/restore procedures without evaluating versions, privileges, and system schemas. For application migrations, explicitly select business databases instead.

Export selected tables in a database:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction \
  sales_app \
  orders order_items customers \
  --result-file=sales-core.sql
```

When specifying a database using the syntax `mysqldump db_name table_name ...`, do not add `--databases`: that option makes all arguments be interpreted as database names. A table-selective dump does not create the target database; prepare the target schema and import into the chosen database.

### 2.3. Exporting Structure Only or Data Only

Export structure only:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --no-data --routines --events --triggers \
  --databases sales_app \
  --result-file=sales-schema.sql
```

Export data only, without creating tables:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --no-create-info --skip-triggers \
  --single-transaction --quick \
  sales_app \
  --result-file=sales-data.sql
```

A data-only dump is appropriate when the target schema has already been created and verified compatible. Do not run a data-only dump into a database with a different structure without checking column names, column order, data types, constraints, and keys.

## 3. Consistency During Export

### 3.1. `--single-transaction` with InnoDB

For InnoDB tables, `--single-transaction` instructs `mysqldump` to start a transaction at an appropriate isolation level to read a consistent snapshot. Changes committed after the snapshot point do not appear in that dump. As a result, applications can continue reading and writing during the export without locking entire tables for the whole dump duration.

Example:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --quick \
  --databases sales_app \
  --result-file=sales_app.sql
```

Important conditions:

- Snapshot consistency applies to transactional tables such as InnoDB.
- Do not execute concurrent DDL during the dump. `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE`, `RENAME TABLE`, or `TRUNCATE TABLE` statements can cause the dump to fail or no longer reflect a consistent schema.
- Tables using MyISAM or non-transactional engines are not protected by the InnoDB snapshot; data may change during the dump.
- Long-running snapshots can retain old row versions in undo logs, increasing storage pressure and affecting purge.

Therefore, coordinate dump schedules with schema migration processes and inspect the storage engines of critical tables.

### 3.2. `--lock-tables` and `--lock-all-tables`

`mysqldump` provides locking mechanisms to keep data stable during export. The `--lock-tables` option locks tables in each database before dumping that database. This mechanism does not create a consistent snapshot across multiple databases.

`--lock-all-tables` requests a global read lock for the duration of the dump, preventing write operations that could modify data during export. This can severely impact applications if the dump takes a long time.

`--single-transaction` and `--lock-tables` should not be combined as active mechanisms; when `--single-transaction` is used, table locking is disabled. Choose the strategy based on storage engine, dump duration, and tolerance for write disruption.

### 3.3. Why Use `--quick`?

`--quick` instructs the client to retrieve rows one at a time from the server and write them immediately, instead of buffering the entire result set of a table in client memory. It is suitable for large tables and is enabled by default via the `--opt` option group in modern `mysqldump` versions.

If using `--skip-opt`, evaluate re-enabling necessary options such as `--quick`, `--extended-insert`, `--lock-tables`, or `--disable-keys` according to your objective. Do not disable the default option group without understanding its associated behaviors.

## 4. Controlling Object Order in Dumps

A database contains more than tables and data. Objects can depend on one another:

- Foreign keys between tables.
- Views referencing tables or other views.
- Triggers attached to tables and calling stored functions.
- Stored procedures/functions referencing tables, views, or other routines.
- Events calling stored procedures or updating tables.
- Objects with a `DEFINER` requiring the corresponding account and appropriate privileges.

During restoration, object creation order must align with the dependency graph. A clear process typically breaks down into phases:

1. Create databases, character sets, and collations.
2. Create base tables and constraints.
3. Load table data.
4. Create views in dependency order.
5. Create required routines.
6. Create triggers after referenced tables and routines are ready.
7. Create events after procedures, tables, and `DEFINER` accounts are prepared.
8. Verify privileges, Event Scheduler state, and the application.

This is a controlled deployment order, not a guarantee that every `mysqldump` file is ordered strictly according to this list across all versions. Inspect the actual dump structure. `mysqldump` has its own handling logic for views, triggers, and related objects; statement order in the file can differ from a manual procedure.

### 4.1. Base Tables and Foreign Keys

Foreign keys can reference tables created later in the dump. Dumps generated by `mysqldump` typically include statements to disable foreign key checks during import and re-enable them at the end of the file. This mechanism supports loading tables with dependency chains or circular references.

Example of two related tables:

```sql
CREATE TABLE customers (
  customer_id BIGINT PRIMARY KEY,
  name VARCHAR(200) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY,
  customer_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers(customer_id)
) ENGINE=InnoDB;
```

In this model, `orders` depends on `customers`. When creating schemas manually, create referenced tables first. When importing a dump, inspect how the file handles `FOREIGN_KEY_CHECKS`.

Important note: `SET FOREIGN_KEY_CHECKS=1` does not rescan previously loaded data to validate prior relationships. If you import with foreign key checks disabled and the data contains orphan rows, re-enabling checks will not automatically fix or detect past violations. Verify data integrity after import using anti-join queries or business checks.

Example to find orders without matching customers:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
```

### 4.2. Views and Inter-View Dependencies

Views require the tables or views they reference to exist both when the definition is created and when queries run. If `v_order_summary` uses `v_order_base`, the underlying view must be created before the dependent view.

Example:

```sql
CREATE VIEW v_order_base AS
SELECT order_id, customer_id, created_at
FROM orders;

CREATE VIEW v_order_summary AS
SELECT customer_id, COUNT(*) AS order_count
FROM v_order_base
GROUP BY customer_id;
```

If a view is created with `SQL SECURITY DEFINER`, the `DEFINER` account must exist and have appropriate privileges. If the original definer cannot be kept, evaluate whether it can be switched to `SQL SECURITY INVOKER` or whether the account and corresponding grants must be recreated. Do not strip `DEFINER` in bulk without understanding the security semantics change.

### 4.3. Triggers and Stored Routines

A trigger is attached to a specific table, so the table must exist before creating the trigger. Triggers can call stored functions; those routines must exist with appropriate privileges. When loading data, creating triggers after data avoids firing triggers on every `INSERT` during restore.

`mysqldump` exports triggers by default after a table's data section in standard dump layouts. Routines and events require the `--routines` and `--events` options. Check the end of the dump file to confirm these sections are present.

Routines can retain the SQL mode, character set, and collation active when they were created. When migrating to a server with a different SQL mode or collation, verify routine definitions and behavior rather than merely checking that `CREATE PROCEDURE` succeeded.

### 4.4. Event Scheduler

Events can run automatically on schedule when the Event Scheduler is enabled. During restoration, imported events may be in the `ENABLED` state and begin executing once the scheduler is active. This can cause unexpected data writes if events run on the target database before verification is complete.

During migration, consider keeping `event_scheduler=OFF` on the target server while importing. Enable the scheduler according to plan only after verifying events, `DEFINER`, schedules, and business impact.

Check:

```sql
SHOW VARIABLES LIKE 'event_scheduler';

SELECT EVENT_SCHEMA, EVENT_NAME, STATUS, DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'sales_app';
```

## 5. Exporting and Importing Routines, Triggers, and Events

A dump command that includes full application objects commonly looks like:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --hex-blob \
  --databases sales_app \
  --result-file=sales_app_full.sql
```

When inspecting contents, look for statements such as:

- `CREATE TABLE` — table structures.
- `INSERT INTO` or `REPLACE INTO` — data.
- `CREATE VIEW` — views.
- `CREATE TRIGGER` — triggers.
- `CREATE PROCEDURE` / `CREATE FUNCTION` — routines.
- `CREATE EVENT` — events.

Dumps may contain `DELIMITER` so the MySQL client can parse routine or trigger definitions containing multiple semicolons. `DELIMITER` is a client command, not a standard server SQL statement. Use the MySQL client to import the dump file intact; do not split the file naively on `;`, as that will break routines and triggers.

## 6. Restoring the Dump to the Target Server

### 6.1. Importing a Dump with `--databases`

If the dump was created with `--databases sales_app`, the file contains database selection/creation statements. Import with:

```bash
mysql --host=db-target.example.internal \
  --user=restore_user --password \
  < sales_app_full.sql
```

The restore account needs privileges to create databases/schemas, tables, views, triggers, routines, events, and write the corresponding data. If `DEFINER` clauses are present, the account may need appropriate administrative privileges depending on version and security configuration.

### 6.2. Importing a Dump Without `--databases`

If the dump does not contain database creation/selection statements, create the target database first:

```sql
CREATE DATABASE sales_app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Then import into the chosen schema:

```bash
mysql --host=db-target.example.internal \
  --user=restore_user --password \
  sales_app < sales_app.sql
```

Specify a character set and collation matching the source or the tested migration target. Do not change the collation arbitrarily during import if the application depends on comparison, sorting, or unique key rules.

### 6.3. Importing from the Interactive MySQL Client

Inside the MySQL client:

```sql
CREATE DATABASE sales_app;
USE sales_app;
SOURCE /backup/sales_app.sql;
```

`SOURCE` is a client command, so it only works inside the interactive MySQL command-line client. For large files or automated pipelines, invoking `mysql < file.sql` generally makes exit code and log capture easier.

### 6.4. Compressing Dumps

You can compress dump files to save storage space:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases sales_app \
  | gzip > sales_app.sql.gz
```

Import:

```bash
gzip -dc sales_app.sql.gz \
  | mysql --host=db-target.example.internal \
          --user=restore_user --password
```

With pipelines, check the exit codes of `mysqldump`, `gzip`, and `mysql`. In shells supporting `pipefail`, enable it so failures upstream in the pipeline are not masked by the final command. Never treat the mere creation of a `.gz` file as proof that the dump completed successfully.

## 7. Privileges, DEFINER, and Security During Migration

### 7.1. Dump Account Privileges

Depending on scope and MySQL version, `mysqldump` may require privileges to read data, read metadata, inspect views/triggers/routines/events, and retrieve tablespace or binary log information. Options such as `--single-transaction`, `--lock-all-tables`, and `--source-data` have different privilege requirements.

Operational principles:

- Use a dedicated dump account granted only the privileges required for the exported schemas and objects.
- Check the documentation for your client/server versions to grant exact privileges; do not grant `SUPER` or broad admin privileges out of habit.
- If tablespace metadata is not needed, consider `--no-tablespaces` to avoid needing `PROCESS` privilege in some environments.
- The import account needs privileges to create and load the actual objects present in the dump.
- Protect dump files because they may contain personal data, application secrets, or sensitive business information.

### 7.2. `DEFINER` for Views, Routines, Triggers, and Events

Stored objects can be created with a `DEFINER` account. Example:

```sql
CREATE DEFINER='report_user'@'%' VIEW v_sales_report AS
SELECT order_id, customer_id, total_amount
FROM orders;
```

If the target server lacks the `report_user`@`%` account, object creation or execution may trigger permission errors depending on version and object type. Even when creation succeeds, an overly privileged definer introduces security risk.

Before migration:

1. List the `DEFINER` of all views, routines, triggers, and events.
2. Determine whether the corresponding accounts exist on the target.
3. Create accounts with least-privilege grants, or redesign objects to use `SQL SECURITY INVOKER` if appropriate.
4. Verify the definer's privileges on relevant schemas and tables.
5. Test executing objects with the actual application account.

Do not replace every `DEFINER` with `root` or the import account. Doing so can cause routines to execute with higher privileges than intended.

### 7.3. User Accounts and Privileges

Dumping an application schema does not mean system accounts and access privileges have been migrated. Manage accounts and roles via a dedicated process—for example, saving `SHOW CREATE USER` and `SHOW GRANTS` for each user/role to migrate, then reviewing and applying them on the target environment.

Do not blindly copy the entire `mysql` schema between different versions. System structures and the data dictionary may change; use MySQL-supported upgrade and account management procedures.

## 8. GTID and Binary Log Metadata

If the goal is solely to migrate a standalone database, GTID history does not necessarily need to be included in the dump. If the goal is to build a replica or continue PITR, plan separately for GTIDs and binary logs.

### 8.1. `--set-gtid-purged`

`mysqldump` provides `--set-gtid-purged` to control writing `GTID_PURGED`-related statements into the dump. Common modes are `OFF`, `ON`, `AUTO`, and `COMMENTED`; default behavior depends on the client version.

- `OFF`: do not write statements setting `GTID_PURGED` into the dump.
- `ON`: write the executed GTID set according to the option's behavior; during import this can alter the target server's GTID history and requires appropriate prerequisites.
- `AUTO`: let the client decide based on the source server's GTID state; when GTID is enabled, the statement may carry the entire server's GTID set rather than just transactions belonging to the dumped database.
- `COMMENTED`: output the statement as a comment for reference without executing it automatically on import.

Do not use `--set-gtid-purged=ON` mechanically when importing into a server that already has GTID history. The exported GTID set may include transactions outside the dumped database scope depending on version and option usage. Inspect the dump contents, GTID sets on source and target, and replica provisioning procedures before importing.

### 8.2. `--source-data` and Binary Log Coordinates

If you need to record the binary log file/position at dump time to configure file/position-based replication, use `--source-data`. The older option name `--master-data` has been replaced by `source` terminology in newer versions; use the option name matching your client.

Example:

```bash
mysqldump --host=db-source.example.internal \
  --user=backup_user --password \
  --single-transaction \
  --source-data=2 \
  --databases sales_app \
  --result-file=sales_app_with_position.sql
```

`--source-data=2` writes the coordinate statement as a comment so operators can inspect and use it in a controlled manner. This option may require a brief global read lock to capture coordinates synchronized with the snapshot; check privilege requirements and locking impact for your client version. When using GTID auto-position, replica configuration differs and generally does not require entering file/position manually.

Do not treat a coordinate line in a dump as sufficient by itself to build a replica. You also need a replication account, network/TLS, valid GTID history or file/position, retained binlogs, and a replica startup procedure.

## 9. Version Differences and Compatibility

When dumping from MySQL 8.4 and importing into an older version, syntax, collations, data types, metadata, or features may not be supported. Conversely, dumping from an older version to a newer one can hit changes in reserved keywords, default values, SQL modes, and system behaviors.

Before migration:

- Record the source server version, `mysqldump` client version, and target server version.
- Use a client compatible with the source server; avoid using a very old binary to dump a newer server.
- Check collations such as `utf8mb4_0900_ai_ci`, which may not exist on older MySQL versions.
- Check data types, generated columns, invisible indexes, expression defaults, check constraints, and version-specific features.
- Test importing into a target server running the planned version and configuration.
- Read all errors and warnings from the MySQL client; do not ignore errors just because most tables were created.

If the migration requires changing storage engines, collations, or schema structure, separate those changes into a dedicated plan and verify data after conversion.

## 10. Verifying the Dump and Import Results

### 10.1. Checking the Dump After Export

After running `mysqldump`, verify:

- The command exit code is 0.
- The file exists, has a reasonable size, and is not truncated.
- The file header contains appropriate version info, SQL mode, and session setup statements.
- All required `CREATE TABLE` statements, data, and requested objects are present.
- Databases/tables match the intended scope, with no missing tables or unintended system schemas.
- If using GTID or `source-data`, inspect the corresponding lines and verify valid values.
- Store a checksum alongside a manifest to detect file changes after creation.

Example quick checks on Linux:

```bash
test -s sales_app_full.sql
grep -E 'CREATE TABLE|CREATE VIEW|CREATE TRIGGER|CREATE PROCEDURE|CREATE FUNCTION|CREATE EVENT' \
  sales_app_full.sql | head -n 40
sha256sum sales_app_full.sql > sales_app_full.sql.sha256
```

Checking with `grep` is only a preliminary sanity check. Routines and triggers can contain delimiters or comments; do not use `grep` as an SQL parser or conclusive proof that all objects were exported.

### 10.2. Checking After Import

On the target server:

```sql
SHOW DATABASES LIKE 'sales_app';

SELECT TABLE_NAME, TABLE_TYPE, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'sales_app'
ORDER BY TABLE_TYPE, TABLE_NAME;

SELECT ROUTINE_NAME, ROUTINE_TYPE, DEFINER
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'sales_app';

SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, DEFINER
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'sales_app';

SELECT EVENT_NAME, STATUS, DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'sales_app';
```

Reconcile:

- Counts of tables, views, and routine/trigger/event objects against the source.
- Engines, charsets, collations, indexes, primary keys, foreign keys, and partitions if present.
- Row counts or business aggregates for critical tables.
- Validity of foreign keys and referenced data.
- Application account privileges, `DEFINER`, and `SQL SECURITY`.
- Critical queries, test write transactions, and integration flows.

Do not compare `COUNT(*)` alone. A table with the same row count can still contain different values, missing indexes, or broken relationships. For critical tables, compare keyed checksums/aggregates or run business reconciliation.

## 11. Troubleshooting Common Import Errors

| Error or Symptom | Possible Cause | Resolution |
|---|---|---|
| `Unknown collation` | Target server does not support a collation in the dump | Choose a compatible target version or plan a tested collation conversion |
| `Access denied` when creating views/routines/triggers | Import account lacks privileges or `DEFINER` is invalid | Check users, grants, definers, and version privilege requirements |
| `Table doesn't exist` when creating views/triggers | Dependent object not yet created or dump is missing tables/routines | Check dependencies and import order; verify dump scope |
| Duplicate key | Data already exists, repeated import, or unclean target schema | Check target data and import strategy; do not use `--replace`/`--force` to mask errors |
| Foreign key constraint fails | Missing referenced data, wrong load order, or orphan rows on source | Check FKs, parent/child rows, and data before re-enabling checks |
| `DEFINER` does not exist or lacks privileges | Referenced account was not created on target | Create the account with minimal privileges or review security context |
| `max_allowed_packet` or large packet error | A large INSERT/BLOB row exceeds client/server limits | Adjust limits appropriately on both client and server, or dump/import accordingly |
| Import stops partway through | SQL error, connection drop, disk full, or interrupted process | Check exit code/logs, identify the last successful statement, and restart cleanly or resume in a controlled way |
| Event executes unexpectedly | Event Scheduler enabled during or immediately after import | Disable scheduler during recovery, review events, then re-enable in a controlled manner |

Avoid using `mysql --force` as a default measure when importing production dumps. This option continues past SQL errors, potentially leaving a partially restored database that operators mistake for a success.

## 12. Sample Migration Workflow

An application database migration can be organized into the following steps:

1. **Survey source:** record MySQL version, databases, engines, sizes, object counts, charsets/collations, accounts, definers, events, and GTIDs.
2. **Prepare target:** install a supported version, configure charset/collation, capacity, import account, application accounts, and required privileges.
3. **Test compatibility:** run a trial dump, import into staging, review syntax errors, collations, routines, triggers, events, and definers.
4. **Stabilize data:** choose `--single-transaction` for InnoDB or an appropriate locking plan; prevent DDL during the dump window.
5. **Export:** run the dump with all required objects, capture logs and exit code, checksum the file, secure it, and transfer it to safe storage.
6. **Import:** disable Event Scheduler if needed, create schemas, and import via the MySQL client; monitor logs and disk usage.
7. **Verify:** compare structure, data, FKs, objects, privileges, queries, and application flows.
8. **Sync final delta:** if the system continues receiving writes during the dump, establish a clear cutover strategy such as a brief write pause, replication, or CDC. A snapshot dump does not automatically carry changes made after the snapshot point.
9. **Cutover:** switch endpoints, verify connectivity, monitor errors, and keep a rollback plan based on actual write state.
10. **Finalize:** verify backups, retention, new backup schedules, and recovery runbooks for the target server.

Do not shift write traffic to the target before completing synchronization of post-snapshot data changes. If the source continues accepting transactions, the target can miss recent changes even though the initial dump was valid.

## 13. Practical Scenario

An e-commerce application has schema `sales_app` containing tables `customers`, `orders`, `order_items`, several reporting views, an audit-updating trigger, a revenue aggregation procedure, and an event closing expired orders. The source runs MySQL 8.0; the target is a new server on the same version. The application continues processing transactions during business hours.

Plan the migration:

1. Inventory tables, engines, foreign keys, views, triggers, routines, events, and `DEFINER` accounts.
2. Choose `--single-transaction --quick` if all business tables are InnoDB; agree not to run DDL during the export window.
3. Dump with `--routines --events --triggers --hex-blob` and explicitly specify the database.
4. Verify the dump includes all objects, save a checksum, and secure the file.
5. Prepare `DEFINER` accounts and privileges on the target; keep the Event Scheduler off during import.
6. Import into the target schema and verify counts of tables, views, routines, triggers, and events.
7. Reconcile order counts, daily revenue totals, foreign keys, and audit data.
8. Design a way to sync transactions occurring after the snapshot, then briefly pause writes to finish the tail and cut over.
9. Enable the Event Scheduler after confirming events will not run redundantly or cause unintended side effects.
10. Test the application with real accounts, monitor logs, and verify backups on the target.

**Self-Check Questions:**

1. Which engines does `--single-transaction` guarantee consistency for? Why is concurrent DDL still a risk?
2. Which objects do `--routines` and `--events` add to a dump?
3. Why are triggers typically created after table data has been loaded?
4. Does disabling and re-enabling `FOREIGN_KEY_CHECKS` re-verify previously loaded rows?
5. How does `DEFINER` affect the security of views and routines?
6. Why should the Event Scheduler be kept disabled during some restore procedures?
7. When a dump includes `--databases`, how does importing differ from a dump with only table/schema names?
8. Why can a consistent dump still leave the target missing transactions if the source continues receiving writes?

## Conclusion

`mysqldump` exports databases into flexible logical SQL for migration and recovery. A reliable workflow selects the proper scope and object options, takes a snapshot suited to the storage engine, controls DDL and dependencies, handles `DEFINER`/privileges/events, and verifies data after import. For systems that continue receiving writes, you must include a step to synchronize post-snapshot changes before cutover.

## References

- [MySQL 8.4 Reference Manual — mysqldump: A Database Backup Program](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual — mysqldump Options](https://dev.mysql.com/doc/refman/8.4/en/mysqldump-options.html)
- [MySQL 8.4 Reference Manual — mysqldump and Transactional Tables](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html#mysqldump-transactional-tables)
- [MySQL 8.4 Reference Manual — Stored Objects](https://dev.mysql.com/doc/refman/8.4/en/stored-objects.html)
