# InnoDB Storage

## TRUNCATE, DROP, OPTIMIZE, and Space Reclamation Capabilities

Deleting data in MySQL does not always make data files smaller. In InnoDB, `DELETE` marks records for deletion and space is only freed after purge can remove older versions; the freed space is typically reused inside the tablespace. `TRUNCATE TABLE` removes all data via a fast DDL operation; `DROP TABLE` removes the entire table object; and `OPTIMIZE TABLE` can rebuild the table and indexes to reorganize data, while returning unused space to the OS in certain tablespace types.

The space reclamation outcome depends on where the table is stored: file-per-table, general tablespace, or system tablespace. Distinguish three outcomes: logically deleting records, returning pages to free space for InnoDB reuse, and shrinking the physical file so the operating system sees space returned. These are three distinct outcomes.

### 1. Distinguishing DELETE, TRUNCATE, DROP, and OPTIMIZE

| Statement | Primary effect | Supports `WHERE` clause? | Rollbackable via transaction? | Space goal |
| --- | --- | --- | --- | --- |
| `DELETE` | Deletes matching rows; can delete part or all of a table | Yes | Yes with InnoDB if transaction is uncommitted | Marks records for purge; empty pages are typically reused |
| `TRUNCATE TABLE` | Empties the entire table via DDL | No | No; causes implicit commit | Frees the table's data/index space to tablespace management |
| `DROP TABLE` | Drops the table object and its data/indexes | No | No; causes implicit commit | Can delete the dedicated tablespace file if the table uses file-per-table |
| `OPTIMIZE TABLE` | Reorganizes the table and indexes, updates statistics | No | No; DDL/maintenance operation | Can return unneeded space in file-per-table to the operating system |

`DELETE` is DML; `TRUNCATE`, `DROP`, and `OPTIMIZE` are DDL or maintenance operations with DDL behavior. Consequently, they have different transaction boundaries and execution privileges. Never use `TRUNCATE` or `DROP` as a shortcut for `DELETE` when the application needs rollback capability or per-row triggers.

### 2. DELETE: Removes Rows Without Necessarily Shrinking the File

`DELETE` deletes rows matching conditions and can participate in an InnoDB transaction:

```sql
START TRANSACTION;

DELETE FROM event_log
WHERE created_at < '2025-01-01';

-- Results can be checked before deciding.
ROLLBACK;
```

If rolled back before commit, InnoDB uses undo to restore the changes. If committed, deleted records are delete-marked and only physically purged once no read view needs older versions. A long-running `REPEATABLE READ` transaction can pin required undo history, slowing purge and delaying record cleanup.

After purge, pages may gain additional free space for future inserts or updates. However, the `.ibd` file usually retains its allocated size. For example, deleting 80% of rows in a file-per-table table can leave most internal pages sparse or empty, while the file size on the filesystem has not dropped proportionally.

This is often beneficial behavior if the table continues receiving data: InnoDB can reuse already allocated pages without requesting additional space from the operating system. Only when returning physical disk space to the filesystem is required should a rebuild or other DDL operation be considered.

### 3. TRUNCATE TABLE: Emptying the Entire Table

Syntax:

```sql
TRUNCATE TABLE event_log;
```

`TRUNCATE TABLE` removes all rows from a table via a DDL operation. It is usually faster than `DELETE FROM event_log` without a `WHERE` clause because it does not process rows one by one like standard DML. Key points:

- No `WHERE` clause; cannot delete only a subset of data.
- Does not generate per-row `DELETE` events and does not fire the table's `DELETE` triggers.
- Resets the `AUTO_INCREMENT` counter back to the initial value per table definition.
- Requires the `DROP` privilege on the table.
- Is DDL with an implicit commit; cannot be undone via `ROLLBACK` of an enclosing transaction.
- Can be rejected if the table is referenced by a foreign key from another table; an exception is a self-referencing foreign key under MySQL rules.

Example illustrating the `AUTO_INCREMENT` difference:

```sql
CREATE TABLE import_stage (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    payload JSON
) ENGINE = InnoDB;

INSERT INTO import_stage (payload)
VALUES ('{"batch": 1}'), ('{"batch": 2}');

TRUNCATE TABLE import_stage;

INSERT INTO import_stage (payload)
VALUES ('{"batch": 3}');
-- id is reassigned from the beginning per current AUTO_INCREMENT rules.
```

Do not rely on `AUTO_INCREMENT` numbers as a gapless counter or an identifier that is never reused. If the system needs to preserve identifier history, store historical data in another table or choose an appropriate key strategy.

`TRUNCATE` also skips business logic implemented in `DELETE` triggers. If you need per-row audit logging, domain event emission, or per-record updates to related tables, use an appropriate DML workflow instead of substituting `TRUNCATE`.

### 4. DROP TABLE: Removing the Table Object

Basic syntax:

```sql
DROP TABLE event_log;
```

`DROP TABLE` removes the table definition along with its data and indexes. With file-per-table, a successful operation typically removes the table's dedicated tablespace and corresponding `.ibd` file. With a table residing in a shared system or general tablespace, the table's space is returned to the shared storage area for reuse; the file holding the tablespace does not shrink automatically just because one table was dropped.

`DROP TABLE` is DDL with an implicit commit and cannot be rolled back via `ROLLBACK`. Before dropping a table involved in foreign key relationships, inspect dependent constraints and migration order. MySQL normally disallows dropping a table referenced by a foreign key from another table while foreign key checks are enabled. Disabling `foreign_key_checks` does not automatically remove constraint definitions on child tables; using this option requires a clear plan for integrity verification and constraint restoration.

To avoid an error when the table does not exist, you can use:

```sql
DROP TABLE IF EXISTS event_log;
```

This statement remains a non-transactional, non-rollbackable drop operation. `IF EXISTS` only alters handling when the table is missing; it does not make the command a safe rollbackable operation.

### 5. OPTIMIZE TABLE with InnoDB

Syntax:

```sql
OPTIMIZE TABLE customer_order;
```

For InnoDB, `OPTIMIZE TABLE` is normally mapped to a rebuild operation equivalent to `ALTER TABLE ... FORCE`. This process recreates the table and index structures, reorganizes pages, eliminates unneeded gaps in the rebuilt structure, and updates index statistics. It is not a command that merely trims empty bytes from a file.

Cases where `OPTIMIZE TABLE` should be considered:

- A file-per-table table has had a large volume of rows deleted and free space needs to be returned to the filesystem.
- A table exhibits fragmentation or page layouts no longer well suited to the workload after major changes.
- Indexes need rebuilding and statistics updating after a major data change, once query plans have been evaluated.

Do not run `OPTIMIZE TABLE` on a rigid periodic schedule for every table. Rebuilds consume CPU, I/O, and temporary disk space; they can increase replication lag, add backup load, and affect other transactions. If the table keeps growing, newly reclaimed space may quickly be reallocated again.

### 6. File-Per-Table vs. Shared Tablespaces Determine Whether Files Shrink

The ability to return space to the operating system depends on the tablespace type:

| InnoDB table location | After `DELETE` and purge | After `TRUNCATE TABLE` | After `OPTIMIZE TABLE` or rebuild |
| --- | --- | --- | --- |
| File-per-table (dedicated `.ibd`) | Empty pages are typically kept in the file for reuse | Table is emptied and its dedicated tablespace space can be freed/recreated | Tablespace file can be recreated smaller, returning surplus to the filesystem |
| General tablespace | Empty pages are returned to the shared area for reuse | Table space is freed within the shared tablespace | Data can be reorganized, yet the general tablespace file does not shrink per table |
| System tablespace (`ibdata`) | Space can be reused inside the system tablespace | Does not shrink `ibdata` | Rebuilding the table does not shrink an already allocated system tablespace |

Checking `innodb_file_per_table` is not enough to be certain where an existing table resides, because that variable primarily controls the default for new tables. Inspect the tablespace metadata of the table itself.

Example checking file-per-table and page size:

```sql
SHOW VARIABLES LIKE 'innodb_file_per_table';
SHOW VARIABLES LIKE 'innodb_page_size';

SELECT
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM information_schema.innodb_tablespaces
WHERE NAME LIKE CONCAT(DATABASE(), '/customer_order%');
```

Tablespace names and display formats may vary by table type and version. Cross-reference `INFORMATION_SCHEMA.INNODB_TABLES` and `INNODB_TABLESPACES` when you need to identify the exact space ID and corresponding file.

### 7. Comparing Space Reclamation Capabilities

Consider a file-per-table table initially occupying 20 GiB. After deleting most rows, pages are purged and reusable, yet the `.ibd` file remains roughly 20 GiB. If a rebuild succeeds and remaining data needs only 4 GiB, the new file can be significantly smaller; the final figure also depends on indexes, page fill factors, row formats, and metadata.

```text
Before deletion:
  customer_order.ibd  ~20 GiB

After DELETE + purge:
  customer_order.ibd  ~20 GiB
  (many empty pages, reusable)

After successful OPTIMIZE/rebuild:
  customer_order.ibd  ~4 GiB
  (illustrative size; depends on data and index structure)
```

With general or system tablespaces, a rebuild can increase free regions inside the tablespace for other tables to reuse, yet the shared file does not necessarily shrink. This is why you should define your goal before running a command: query optimization, internal space reuse, or reducing filesystem usage.

### 8. DDL, Implicit Commit, and Atomic DDL

`TRUNCATE TABLE`, `DROP TABLE`, and the rebuild operation of `OPTIMIZE TABLE` exhibit DDL behavior. Standard DDL statements cause an implicit commit before and/or after the operation per MySQL rules. Therefore, you cannot wrap them inside a transaction and expect `ROLLBACK` to restore the dropped table or removed data.

For example, `TRUNCATE` ends the active transaction before executing:

```sql
START TRANSACTION;

UPDATE account
SET status = 'review'
WHERE id = 10;

TRUNCATE TABLE import_stage;

ROLLBACK;
-- The UPDATE before TRUNCATE was implicitly committed; this ROLLBACK does not undo it.
```

MySQL 8.0 supports Atomic DDL for many supported InnoDB DDL operations. Atomic DDL makes a statement execute in a crash-safe manner: after a crash, metadata and changes from the statement do not leave a half-applied state within the engine's supported scope. However, **Atomic DDL does not mean DDL can be rolled back by the user**. A completed `TRUNCATE` or `DROP` still cannot be undone via a transaction `ROLLBACK`.

Atomic DDL does not replace backups either. Before critical delete or rebuild operations, ensure you have a restorable backup and tested restore procedures.

### 9. Locks, Temporary Space, and Operational Impact During Rebuilds

`OPTIMIZE TABLE` or a rebuild DDL may need to construct a new structure before replacing the old one. During this time, the system may require substantial temporary space—typically budgeting at least roughly the size of the data and indexes being rebuilt, plus logs and workload headroom. Actual usage depends on the DDL algorithm, version, table structure, and concurrent changes.

Risks to evaluate:

- **Disk capacity:** insufficient temporary space can cause the rebuild to fail or put pressure on the filesystem.
- **Metadata lock (MDL):** the statement must acquire an MDL; long-running transactions accessing the table can block the DDL. A waiting DDL can also queue subsequent new queries behind it.
- **Concurrent DML:** concurrent read/write capability depends on algorithm and version; never assume `OPTIMIZE TABLE` is always non-locking or always permits writes.
- **Replication:** DDL is written to the binary log per server rules and can cause load or lag on replicas.
- **Backups and I/O:** rebuilds generate heavy read/write I/O, competing with workloads and backup windows.
- **Execution time:** large tables or wide indexes can take a long time; measure in a similar environment before deploying.

Before running, check long transactions, metadata locks, filesystem space, replica lag, and maintenance windows. For critical tables, test the procedure on a data copy and prepare an abort/recovery plan.

### 10. Measuring Size Before and After the Operation

Do not use `COUNT(*)` alone to conclude a file has shrunk. Compare table metadata, tablespace metadata, and file sizes on the filesystem.

Table-level estimates:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_order';
```

Tablespace info in MySQL 8.0:

```sql
SELECT
    SPACE,
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM information_schema.innodb_tablespaces
WHERE NAME LIKE CONCAT(DATABASE(), '/customer_order%');
```

`DATA_LENGTH`, `INDEX_LENGTH`, and `DATA_FREE` are engine-reported metrics, which may be estimates or reflect shared tablespace scope. To confirm physical space was returned, inspect actual file sizes on the filesystem after the operation completes. Never read or edit binary contents of `.ibd` or `ibdata` with external tools while MySQL is using them.

Record before/after metrics from consistent points in time: row count, `DATA_LENGTH`, `INDEX_LENGTH`, `DATA_FREE`, `FILE_SIZE`, `ALLOCATED_SIZE`, filesystem free space, and replica lag. Then compare against your original goal: internal space reuse or space returned to the operating system.

### 11. Choosing the Statement by Goal

| Need | Commonly suitable choice | Notes |
| --- | --- | --- |
| Delete a subset of rows by condition with rollback support | `DELETE ... WHERE ...` in a transaction | Wait for purge; file may not shrink |
| Empty a staging table where DDL is acceptable | `TRUNCATE TABLE` | No WHERE, resets AUTO_INCREMENT, implicit commit, check FKs and triggers |
| Remove a table no longer used | `DROP TABLE` | Removes object; check dependencies/FKs and backups |
| Return file-per-table space after deleting large volumes of data | `OPTIMIZE TABLE` or planned rebuild | Requires temp space, I/O, and MDL assessment |
| Free space for other tables in a shared tablespace | `DELETE`/purge or appropriate `TRUNCATE`/rebuild | Shared tablespace files do not shrink automatically |
| Shrink the `ibdata` system tablespace | Cannot be done via `OPTIMIZE TABLE` alone | Typically requires redesign and building a new instance/data directory via migration/restore |

If the goal is pruning old time-series data in a very large table, consider partitioning from initial design. Dropping a partition can be much more efficient than deleting millions of records, though partition changes remain DDL and must account for foreign keys, indexes, binary logs, and data retention rules.

### 12. Pre-Reclamation Checklist

1. Confirm whether the goal is logical deletion, page reuse within a tablespace, or reducing filesystem usage.
2. Identify whether the table resides in file-per-table, a general tablespace, or the system tablespace.
3. Check foreign keys, triggers, `AUTO_INCREMENT`, privileges, and implicit commit impact before `TRUNCATE`/`DROP`.
4. With `DELETE`, monitor long transactions and purge to know when old records can be cleaned up.
5. With `OPTIMIZE TABLE`, plan for temporary space, I/O, metadata locks, duration, and replica lag.
6. Measure metadata metrics and file sizes before/after; never infer file shrinkage from row counts alone.
7. Have a backup and verify restore capability before non-rollbackable operations.
8. Never manipulate `.ibd`, `ibdata`, redo, or undo files directly; let InnoDB manage tablespaces.

`DELETE` frees records via transaction and purge mechanisms; `TRUNCATE` empties a table via DDL; `DROP` removes the object; `OPTIMIZE` rebuilds to reorganize structures. Only by understanding tablespace types and space goals can you choose the right operation and predict which space is reused inside InnoDB versus actually returned to the operating system.
