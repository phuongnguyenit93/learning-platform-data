# Consistent Snapshots with `--single-transaction` and Limitations with DDL/Non-Transactional Tables

When backing up a database that is actively serving an application, data may continue to be inserted, updated, or deleted while the tool reads tables. If each table is read at a different point in time, the dump may contain pieces of data that do not belong to a single consistent state. MySQL addresses this for InnoDB tables through MVCC consistent reads. With `mysqldump`, the `--single-transaction` option uses one transaction and a consistent snapshot to read data without locking normal write operations for the entire dump duration.

This mechanism has important limitations: an MVCC snapshot applies to InnoDB transactional data. It does not make MyISAM or other non-transactional tables transactional, nor does it protect the dump against concurrent table structure changes (DDL). To choose the right backup strategy, you must inspect storage engines, understand when the snapshot is established, and coordinate backup schedules with schema change activity.

## Learning Objectives

After this lesson, you will be able to:

- Explain MVCC-based consistent snapshots and how `mysqldump --single-transaction` uses them.
- Predict which data is visible when the application continues writing during a dump.
- Identify the limitations of `--single-transaction` with DDL and non-transactional tables.
- Choose between transactional snapshots, read locks, and write pauses based on engine and consistency requirements.
- Inspect engines, create an appropriate dump, and verify it through a test restore workflow.

## 1. Why Does a Backup Need a Consistent Point?

Suppose a sales transaction updates two tables: `orders` and `payments`. The application writes the order status first and then records the payment within the same transaction. If the backup tool reads `orders` before the transaction commits and reads `payments` after it commits, the result can reflect two different points in time. Upon recovery, the data might represent a state the application never actually observed.

A consistent logical backup must read transactional tables from the same point of view. InnoDB provides this via **Multi-Version Concurrency Control (MVCC)**: instead of forcing every reader to wait for writers or vice versa, InnoDB retains the record versions needed so a reading transaction sees a stable snapshot of the data.

With a consistent snapshot established at time T0:

- Changes committed before T0 are visible.
- Changes uncommitted at T0 are not visible.
- Changes committed after T0 do not appear in consistent reads of that transaction.
- Subsequent reads within the same transaction continue using the same snapshot rather than advancing to the latest state per statement.

This keeps the dump from mixing data committed at different moments during the read, provided the relevant tables all use InnoDB and no DDL breaks the snapshot's assumptions.

## 2. InnoDB Consistent Snapshots

### 2.1. MVCC and Consistent Reads

InnoDB stores record version metadata and undo information needed to reconstruct the version matching a transaction's read view. When a transaction performs a consistent read, InnoDB determines which transactions had committed when the read view was created. If a row was updated by another transaction after that point, the reader can retrieve the older version from undo information.

For example, an `accounts` table holds balances for two accounts. A transfer transaction updates both rows and commits. A reading transaction whose snapshot was created before that commit continues seeing the old balances for both rows. A snapshot created after the commit sees the new balances for both rows. Thus, a reader never sees a half-finished transfer transaction.

A transaction can explicitly establish a snapshot as follows:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT * FROM accounts WHERE account_id IN (101, 202);
-- Subsequent consistent SELECTs continue using the same read view.

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` creates the read view as soon as the transaction starts under the appropriate isolation level. For InnoDB, `REPEATABLE READ` is the default isolation level and the level `mysqldump --single-transaction` uses for snapshots. Plain `SELECT` statements in the example are consistent reads; locking reads such as `SELECT ... FOR UPDATE` have different semantics and should not be used to illustrate read snapshots.

### 2.2. Data Changing During a Dump

Suppose a dump creates its snapshot at 10:00. The application continues writing data:

| Time | Application Activity | Data Seen by the 10:00 Snapshot |
|---|---|---|
| 09:58 | Transaction A updates an order and commits | Updated data is visible |
| 10:00 | `mysqldump` starts transaction and creates snapshot | Point of view is pinned here |
| 10:02 | Transaction B inserts a new order and commits | New order is not visible in snapshot |
| 10:04 | Transaction C updates order status and commits | Pre-10:00 version is still visible |
| 10:06 | `mysqldump` finishes and commits read transaction | Snapshot is released |

The application can continue performing DML on InnoDB during the dump. The dump reflects the committed state at the moment the snapshot was established, not the latest state at the moment the dump command finishes. This is the desired behavior of a point-in-time consistent backup.

## 3. Using `mysqldump --single-transaction`

`--single-transaction` instructs `mysqldump` to start a transaction before reading data and use a consistent snapshot. This option fits best when all tables to be backed up are InnoDB.

Example of backing up the `shop` database:

```bash
mysqldump \
  --login-path=backup \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --databases shop > shop.sql
```

Meaning of key options:

| Option | Meaning |
|---|---|
| `--login-path=backup` | Uses connection credentials stored via `mysql_config_editor`, avoiding passwords directly on the command line |
| `--single-transaction` | Uses a single consistent snapshot for transactional data |
| `--quick` | Streams rows one by one instead of buffering entire large table results in client memory |
| `--routines` | Includes stored procedures and stored functions |
| `--events` | Includes Event Scheduler events |
| `--triggers` | Includes triggers; this is also normal default behavior in `mysqldump`, listed explicitly for easy command review |
| `--databases shop` | Dumps the `shop` database and adds database creation/selection statements to the output |

`--login-path=backup` assumes a matching login path was created using `mysql_config_editor set --login-path=backup ...`. Do not place real passwords in script files, cron schedules, or shell history. The `--quick` option is typically already included in the default `--opt` option group, but specifying it explicitly makes streaming intent clear when reviewing backup configurations.

If you need to dump a database without adding `CREATE DATABASE`/`USE` statements, you can intentionally omit `--databases` or pass the database name directly and choose the matching restore method. Align the dump format with your recovery procedure.

### 3.1. Conditions for a Meaningful Snapshot

- Data tables requiring consistency must use InnoDB.
- The snapshot must be held within the same transaction throughout data reading.
- No DDL affects the tables being dumped while the snapshot is active.
- The backup account has sufficient privileges to read required data and metadata for dumped objects.
- The server has sufficient resources to retain needed older row versions while the long-running read transaction stays open.

`--single-transaction` does not mean the entire backup process has zero impact. Long-running read transactions can increase the amount of undo history retained, slow purge activity, and grow the undo tablespace. The larger the tables, the slower the read rate, or the longer the dump duration, the more closely this impact must be monitored.

## 4. Limitations with DDL During a Dump

InnoDB's consistent snapshot protects row-version reads under MVCC. It does not create a historical snapshot of table definitions and metadata across the entire schema. Structural changes during a dump can cause reads to fail or make the output no longer reflect a consistent schema.

While `mysqldump --single-transaction` is running, do not execute DDL operations on tables being dumped, including:

- `ALTER TABLE`: modifying columns, indexes, or table structure.
- `DROP TABLE`: dropping a table currently being read.
- `RENAME TABLE`: renaming a table.
- `TRUNCATE TABLE`: emptying a table via a DDL operation.
- `CREATE TABLE`: creating new tables in the schema being dumped, which can alter the set of objects processed by the dump.

DDL typically causes an implicit commit and requires metadata locks. It can modify the data dictionary or structures that the dump queries rely on. Therefore, an MVCC read view is not enough to keep a dump safe when schemas change concurrently. Exact impact varies by operation and timing; never rely on a previous dump happening to succeed as justification for running DDL in parallel.

### 4.1. Coordinating with Migrations

An easily controllable workflow is:

1. Schedule backups and schema migrations into coordinated windows.
2. Before dumping, confirm no migrations or DDL operations are running against tables in the backup scope.
3. For the duration of the dump, pause deployments that alter table structure, `TRUNCATE`, `RENAME`, or drop tables.
4. Only resume deferred migrations after the dump completes.
5. Record backup start/end timestamps, schema version, and job status for investigation if recovery is needed.

If the system deploys DDL continuously and cannot tolerate a pause window, choose a backup solution specifically designed to coordinate with DDL and the system's topology. Do not assume `--single-transaction` handles schema changes on its own.

## 5. Limitations with Non-Transactional Tables

MyISAM is a common example of a non-transactional storage engine. This engine does not provide MVCC consistent reads and cannot roll back DML like InnoDB. If a MyISAM table is updated while `mysqldump` is reading it, rows in the dump may reflect different points in time.

This also applies to databases containing both InnoDB and non-transactional tables. `--single-transaction` can still create a consistent snapshot for the InnoDB tables, but it cannot guarantee that MyISAM or other non-transactional tables belong to the same point in time. A mixed-engine dump therefore cannot be treated as a consistent database-wide snapshot based on this option alone.

Inspect table engines before choosing a backup strategy:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM information_schema.tables
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN (
      'mysql', 'information_schema', 'performance_schema', 'sys'
  )
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

Focus on finding tables whose `ENGINE` is other than `InnoDB`, or `NULL` if metadata indicates an undetermined engine. You can summarize table counts by engine:

```sql
SELECT
    ENGINE,
    COUNT(*) AS table_count
FROM information_schema.tables
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA = 'shop'
GROUP BY ENGINE
ORDER BY ENGINE;
```

### 5.1. Options When Non-Transactional Tables Exist

**Option A: Pause writes during the backup window.** Temporarily stop applications or jobs that can modify non-transactional tables, wait for active operations to finish, and then dump. This is straightforward to reason about, but requires operational coordination and interrupts write functionality.

**Option B: Use a global read lock.** `mysqldump --lock-all-tables` acquires a global read lock for the duration of the dump, preventing write operations from modifying server data while locked. This can preserve consistency across non-transactional tables and multiple databases, but it can block writes across the entire instance and directly impact the application.

Example:

```bash
mysqldump \
  --login-path=backup \
  --lock-all-tables \
  --quick \
  --routines \
  --events \
  --triggers \
  --databases shop > shop-locked.sql
```

`--lock-all-tables` and `--single-transaction` are two different strategies; pick the appropriate strategy rather than combining them expecting an extra snapshot layer. A global read lock is held for roughly the entire dump duration, so benchmark runtime and assess impact before applying in production.

**Option C: Use `--lock-tables` when scope fits.** This option locks the tables of each database before dumping that database. It can fit certain single-database dumps, but does not establish a shared consistency point across multiple databases because databases are processed sequentially. `--lock-tables` is also incompatible with `--single-transaction`, as locking tables can cause an implicit commit.

**Option D: Migrate tables to InnoDB.** If workload and application requirements allow, converting the engine enables tables to participate in transactions and consistent snapshots. Conversion must be evaluated separately for locking, storage footprint, indexes, data types, application behavior, and migration duration; do not convert engines with a hasty command during a backup window.

## 6. Choosing a Strategy by System State

| Data State | Typically Suitable Strategy | What to Control |
|---|---|---|
| All tables are InnoDB, no concurrent DDL | `--single-transaction --quick` | Transaction duration, undo history, and storage capacity |
| Has MyISAM/non-transactional tables, writes can pause | Controlled write pause during dump | Write pause/resume timing and confirming no active writers |
| Many non-transactional tables, instance-wide consistency needed | `--lock-all-tables` if lock impact is acceptable | Global read lock and write-blocking duration |
| Dumping one database only and per-database locking is acceptable | Consider `--lock-tables` | Locks per database; no shared point across multiple databases |
| Schema changes during backup | Coordinate migrations or use a backup solution designed to handle DDL | Do not run DDL on tables being dumped with `--single-transaction` |

No single dump option fits every topology. First classify engines, define the database scope to back up, measure dump duration, and agree on acceptable write disruption.

## 7. Controlled Backup Workflow

A practical workflow can follow these steps:

1. **Survey engines:** query `information_schema.tables` to find non-transactional tables in the backup scope.
2. **Check schema changes:** confirm no migrations, DDL, or structural maintenance tasks run inside the backup window.
3. **Select mode:** use `--single-transaction` if all tables requiring a snapshot are InnoDB; choose write pauses or read locks if non-transactional tables exist.
4. **Run dump:** record logs, start/end timestamps, exit code, and output file path. Monitor file size and server resources.
5. **Verify output:** confirm the file was created, is non-empty, the job exited cleanly, and the header/footer of the dump file are readable.
6. **Test recovery:** import into a compatible test environment and verify tables, routines, events, triggers, and key data.
7. **Store securely:** apply encryption, least-privilege access, retention policies, and off-host copies per operational requirements.

A dump command returning a success exit code is a necessary condition, not proof that the backup restores cleanly. Periodic test restores are what confirm backup usability.

## 8. Common Misconceptions

- **Assuming `--single-transaction` locks all tables:** for InnoDB, it uses a consistent snapshot so DML can proceed. It does not lock all write operations for the entire dump.
- **Assuming every storage engine supports snapshots:** MVCC consistent read is a mechanism of transactional engines like InnoDB. MyISAM tables are not protected by that snapshot.
- **Assuming DDL is also snapshotted:** a data snapshot does not freeze the data dictionary or table definitions. DDL must be coordinated separately.
- **Combining `--single-transaction` with `--lock-tables`:** the two modes have conflicting semantics; `LOCK TABLES` can implicitly commit a transaction. Pick one strategy intentionally.
- **Ignoring long-running read transactions:** prolonged snapshots hold older row versions longer, slowing purge and increasing undo storage needs.
- **Equating dump success with restore success:** an SQL file can be created yet lack necessary privileges, objects, or data. Always validate with a test restore.

## 9. Practice Exercise

An e-commerce system has a `shop` database with InnoDB tables `orders` and `order_items`, plus a MyISAM table `legacy_audit`. During business hours, the application continuously inserts orders. The development team also deploys an `ALTER TABLE orders` migration in the evening. The requirement is to create a consistent dump capable of recovering the database in an incident.

Perform the following tasks in a test environment:

1. Use `information_schema.tables` to identify the engine of all three tables and list all non-InnoDB tables.
2. Explain what `mysqldump --single-transaction` guarantees for `orders` and `order_items`, and why it cannot provide the same guarantee for `legacy_audit` while the application keeps writing.
3. Propose a coordination schedule between the backup and the `ALTER TABLE orders` migration. Specify the window where DDL must not run.
4. Compare pausing writes against `--lock-all-tables`; identify the impact on application operations.
5. Create the dump using the chosen strategy, record the exit code and file size, then restore into a test database.
6. Compare row counts and key schema objects after restore. Explain the limitation of comparing only `COUNT(*)` when data can change due to business activity.

The expected outcome is an evidence-backed backup decision: knowing which tables are protected by a consistent snapshot, when DDL or DML must be blocked, and having proof that the dump can be restored.

## Conclusion

`mysqldump --single-transaction` establishes a useful consistent snapshot for InnoDB tables thanks to MVCC and the `REPEATABLE READ` isolation level. DML can continue during the dump, but DDL on tables being backed up can invalidate structural assumptions and make output inaccurate. Non-transactional tables also do not participate in the snapshot, requiring write pauses, appropriate read locks, or storage engine changes. Inspect engines before every backup plan, coordinate migrations, and always verify with a test restore.
