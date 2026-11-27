# Snapshot Prerequisites and Whole-Data Consistency in PostgreSQL

A backup is useful only when the data inside forms a recoverable and meaningful state. If a copy holds the orders table as of time A, the payments table as of time B, and file attachments as of time C, the application might restore each piece yet end up with a business-inconsistent system.

PostgreSQL provides **MVCC snapshots** so a transaction reads one consistent data state inside a database. Tools like `pg_dump` use snapshots to export logical data without halting writes. For physical backups or storage snapshots, requirements differ: you need a copy of data files that can be brought to a consistent state via WAL recovery, while properly coordinating volumes, tablespaces, and WAL.

Therefore, when designing backups, you must answer two questions:

1. **What data does the snapshot see?** Which transactions are considered committed as of the snapshot point?
2. **Which components does the snapshot cover?** Do all tables, databases, tablespaces, WAL, Large Objects, sequence states, external files, and related systems share one consistency point?

These two questions determine whether a snapshot suits logical dumps, physical backups, storage snapshots, PITR, or test clones.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain MVCC snapshots and visibility rules in PostgreSQL.
2. Distinguish per-statement snapshots from fixed transaction snapshots.
3. Describe how `pg_dump` uses snapshots to produce consistent logical backups.
4. Explain parallel dumps and exported snapshots across multiple connections.
5. State the prerequisites and limitations of `pg_export_snapshot`/`SET TRANSACTION SNAPSHOT`.
6. Distinguish logical consistency from physical/crash consistency.
7. Use `pg_backup_start`/`pg_backup_stop` or `pg_basebackup` appropriately.
8. Determine how to coordinate snapshots across multiple volumes, tablespaces, and WAL.
9. Understand snapshot limitations across multiple databases or systems external to PostgreSQL.
10. Identify sequence states, Large Objects, roles/tablespaces, and configs not automatically covered by a single-table snapshot.
11. Define consistency points, RPO/RTO, backup retention, and restore validation.
12. Design labs to verify snapshots and recovery.

## 2. What Is an MVCC Snapshot?

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. When a transaction runs `UPDATE` or `DELETE` on a row, PostgreSQL creates a new row version or marks the old version; readers continue seeing versions matching their snapshot without blocking writers in most scenarios.

A snapshot is the information PostgreSQL uses to decide which transactions are committed, in flight, or not yet visible as completed at a logical point in time.

### 2.1. Snapshots Determine Row Visibility

A row version carries internal transaction metadata (e.g., `xmin`/`xmax`) so PostgreSQL determines whether it is visible to a snapshot. Applications should not build business logic directly around reading these system columns; understand them as the foundation of MVCC.

Example:

```text
Initially:
  account 1 balance = 100

Transaction A:
  UPDATE balance = 150
  COMMIT

Transaction B starts snapshot:
  sees balance = 150

Transaction C started before A committed:
  C's snapshot may not see version 150
  and continues seeing the old version = 100
```

A snapshot does not "freeze the database" or copy all pages into RAM. It determines which row versions are considered visible when queries read data.

### 2.2. `READ COMMITTED`: Fresh Snapshot per Statement

Under the default `READ COMMITTED` isolation level, each statement generally sees a fresh snapshot taken when that statement starts. Two consecutive `SELECT`s inside one transaction can see commits that occurred between the two statements.

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM bank.accounts
WHERE account_id = 1;

-- Another transaction can UPDATE and COMMIT here.

SELECT balance
FROM bank.accounts
WHERE account_id = 1;

COMMIT;
```

The second `SELECT` can see the new value. Hence, multiple `SELECT` statements under `READ COMMITTED` do not automatically form one fixed snapshot across the transaction.

### 2.3. `REPEATABLE READ`: Fixed Snapshot for the Transaction

Under `REPEATABLE READ`, the transaction uses one consistent snapshot established on its first read (or when a snapshot is imported). Subsequent `SELECT`s keep seeing that exact MVCC state, even as other transactions commit changes.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM sales.orders;
SELECT sum(total_amount) FROM sales.orders;

COMMIT;
```

Both `SELECT`s share the same snapshot, so they never see half of a prior state and half of a state after concurrent commits.

### 2.4. `SERIALIZABLE`

`SERIALIZABLE` adds enforcement so committed transactions behave equivalently to some serial execution order. It may abort a transaction with a serialization failure if non-serializable conflicts occur.

For read-only reporting/backups, `SERIALIZABLE READ ONLY DEFERRABLE` can be used when a safe snapshot is needed and waiting before starting is acceptable. It is not a mandatory default for every backup.

### 2.5. Snapshots Exclude Uncommitted Data

If a transaction has inserted a row without committing when a snapshot is taken, the snapshot does not treat that row as committed data for backup. Even if that transaction commits afterward, a dump using the earlier snapshot does not see the new row.

This is desirable: a backup must never capture half a transaction or treat unconfirmed writes as committed.

### 2.6. Snapshots Do Not Block Ongoing Writes

MVCC lets backups read a consistent state while applications keep issuing `INSERT`/`UPDATE`/`DELETE`. Writers do not have to wait for the entire dump to finish merely because a reader holds a snapshot.

However, long-lived snapshots carry a cost: PostgreSQL must retain old row versions so the backup transaction can still see them. This can prevent `VACUUM` from reclaiming dead tuples and increase table/index bloat.

## 3. Statement Snapshots vs. Transaction Snapshots

Distinguishing these two scopes is essential when building multi-statement backups.

### 3.1. Two `SELECT`s Under `READ COMMITTED` Can See Two States

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT count(*) FROM app.orders;

-- Another session INSERTs and COMMITs a new order.

SELECT count(*) FROM app.orders;
COMMIT;
```

If the second transaction commits between the two `SELECT`s, counts differ. A custom backup running multiple independent `SELECT`s under this default can mix points in time.

### 3.2. One `REPEATABLE READ` Transaction Uses One Snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM app.orders;

-- Another session INSERTs and COMMITs a new order.

SELECT count(*) FROM app.orders;
COMMIT;
```

Both `SELECT`s see the same snapshot. Rows committed after the snapshot appear in neither result.

### 3.3. When Does the Snapshot Start?

In `REPEATABLE READ`, the snapshot is normally established when the transaction executes its first statement needing a snapshot, not necessarily at `BEGIN`. To share a snapshot with another exporter, import the snapshot before the consumer transaction's first statement.

### 3.4. Read-Only Transactions

Declaring `READ ONLY` signals that the transaction only reads and lets PostgreSQL apply relevant optimizations/checks. It does not persist snapshots across restarts, export backup files, or stop other sessions from writing.

### 3.5. A Snapshot Is Not a Whole-Database Lock

A `REPEATABLE READ READ ONLY` transaction does not lock all tables to freeze data. It relies on MVCC visibility. DDL still takes locks and can conflict with other operations; locks acquired by `pg_dump` prevent structural changes that would cause inconsistencies during the dump.

## 4. `pg_dump` and Consistent Logical Backups

`pg_dump` creates logical backups by reading schemas and data and writing SQL or an archive format. It is designed to yield a consistent dump while the database remains concurrently usable.

### 4.1. `pg_dump`'s Snapshot

`pg_dump` opens a transaction with an appropriate snapshot so dumped tables reflect one consistent MVCC state of the database. Data committed after the snapshot will not appear in that dump.

Example:

```bash
pg_dump -Fc -f app.dump appdb
```

`-Fc` creates a custom archive; it does not mean the snapshot is a filesystem image. On restore, `pg_restore` recreates logical objects.

### 4.2. Concurrent DML

While `pg_dump` runs:

- Application sessions can `INSERT`/`UPDATE`/`DELETE`.
- `pg_dump` reads row versions visible to its snapshot.
- Transactions committed after the snapshot are excluded from the dump.
- Old row versions may need to be retained until the dump finishes.

Hence, long dumps can raise bloat under continuous write workloads while snapshots stay open.

### 4.3. Concurrent DDL

`pg_dump` takes appropriate locks on objects so schemas do not change mid-read. Some DDL may wait or cause the dump to fail on lock conflicts. Coordinate migrations/DDL with backup windows and check `pg_dump` errors rather than assuming all DDL runs harmlessly alongside dumps.

### 4.4. Single-Database Snapshot

`pg_dump` operates on **one database** at a time. It does not take a cluster-wide MVCC snapshot spanning every database at one point in time.

If an application uses database A for orders and database B for billing, running two sequential `pg_dump` commands does not guarantee both dumps represent the exact same consistency point. Design dedicated coordination or adjust data boundaries.

### 4.5. Global Objects

Dumping one database with `pg_dump` does not dump cluster-wide objects like roles and tablespaces. Use `pg_dumpall --globals-only` or a dedicated globals workflow:

```bash
pg_dumpall --globals-only > globals.sql
```

Dumping globals is a separate action without a shared MVCC snapshot across all databases. Manage role/tablespace changes during backup windows when consistent cluster configs/permissions are needed.

### 4.6. Sequences Are an Important Exception

Sequence values do not obey MVCC transactional semantics like table rows. `nextval` takes effect immediately and does not roll back with transactions. While a dump runs, applications can keep calling `nextval`; dumped sequence values do not necessarily form a strict MVCC snapshot aligned with rows.

To ensure post-restore sequence states do not collide with exported keys, coordinate writers/sequence usage or inspect/reconcile sequence values after restore. Never assume `REPEATABLE READ` freezes sequences.

### 4.7. Large Objects

`pg_dump` can dump Large Objects when configured/formatted appropriately; do not merely dump OIDs in metadata tables assuming LO payloads are automatically present. For selective dumps, check `--large-objects` options and inspect the archive.

### 4.8. Extensions and External Dependencies

`pg_dump` saves extension definitions via extension metadata, without bundling binaries/packages/OS dependencies required on the target server. Similarly, external files, secrets, certificates, configs, and object storage are not automatically included in dumps.

### 4.10. Serializable Deferrable

`pg_dump` provides `--serializable-deferrable` to use a `SERIALIZABLE`, `READ ONLY`, `DEFERRABLE` transaction. The transaction may wait until a safe snapshot is obtained instead of starting immediately; this helps specific consistency requirements at the cost of potentially delaying dump start.

There is no need to enable this option for every backup. It does not create cross-database snapshots, freeze sequences, or replace application-level consistency protocols.

### 4.9. Restoring Differs from Running Dump SQL in Production

A logical dump is a set of statements/objects to rebuild a database. On restore, matching roles, tablespaces, extensions, encoding/collation, owners, and privileges may be needed. Test restores on an independent target database.

## 5. Parallel `pg_dump` and Exported Snapshots

Parallel dumps improve throughput for large databases. For multiple worker connections to read the same state, they must share a snapshot.

### 5.1. Why Must Parallel Dumps Share a Snapshot?

If each worker took its own snapshot:

- Worker A could dump `orders` before a new transaction.
- Worker B could dump `order_items` after that transaction committed.
- The dump could hold an `order_item` whose parent order is missing from that logical state.

A shared snapshot gives workers the exact same visibility point, preserving cross-table consistency.

### 5.2. `pg_dump -j`

```bash
pg_dump -Fd -j 4 -f app_directory_dump appdb
```

Parallel dump requires directory format `-Fd` and multiple connections. `pg_dump` coordinates snapshots across workers internally; you do not manually create a snapshot per worker.

### 5.3. Exporting a Snapshot in PostgreSQL

A session can export a snapshot using `pg_export_snapshot()` inside a suitable transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

PostgreSQL returns a text snapshot identifier. The exporter session must keep its transaction open while other sessions import that snapshot.

### 5.4. Importing a Snapshot

In a consumer session:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

-- Run SELECTs that require the same snapshot.
SELECT count(*) FROM app.orders;
SELECT count(*) FROM app.order_items;

COMMIT;
```

Replace the snapshot identifier with the actual value returned by the exporter. `SET TRANSACTION SNAPSHOT` must be called before the consumer transaction's first query (aside from permitted transaction-setting commands), and the isolation level must be `REPEATABLE READ` or `SERIALIZABLE`.

### 5.5. The Exporter Must Stay Open

A snapshot identifier is not a file or permanent token. The exporter transaction must stay open while consumers import. Once the exporter ends, that snapshot can no longer be imported by new consumers.

A consumer that already imported the snapshot can continue using it in its own transaction after the exporter finishes, per PostgreSQL semantics; however, no new consumer can import the old identifier after the exporter closes.

### 5.6. Snapshots Are Scoped to One Database

Snapshot export/import applies to connections to the same database. You cannot use one snapshot ID to synchronize visibility across multiple databases in a cluster.

### 5.7. `pg_dump --snapshot`

`pg_dump` supports `--snapshot=snapshot_id` to adopt a snapshot exported by another session. This helps coordinate `pg_dump` with other tools, provided the exporter keeps its transaction open until `pg_dump` imports the snapshot.

### 5.8. Snapshots and Connection Pools

Never let an exporter transaction be returned to a pool or committed/rolled back before consumers finish importing. Connection pools can reuse sessions for other requests; holding an exporter snapshot requires explicit ownership and timeouts to avoid lingering idle transactions.

### 5.9. Exported Snapshots Are Not Durable Backups

A snapshot ID describes visibility among live transactions. It contains no data bytes, cannot rebuild a database after a restart, and does not replace dumps/base backups/WAL archives.

## 6. Logical Snapshots Are Not Physical Snapshots

Both backup methods use the word "snapshot" yet provide different guarantees.

### 6.1. Logical Snapshots

Logical backups read rows and schemas via MVCC visibility. For example, `pg_dump` outputs `CREATE TABLE`, `INSERT`/`COPY` data, indexes, constraints, functions, and supported objects.

Characteristics:

- Can restore into a new database or different compatible PostgreSQL version.
- Can select schemas/tables/database objects.
- Uses a snapshot so tables inside one database reflect one logical state.
- Restore rebuilds objects and loads rows, often taking time on large databases.
- Does not automatically include all global objects, configs, and external dependencies.

### 6.2. Physical Snapshots/Backups

Physical backups copy data files, required WAL, and cluster components. They do not scan rows under an MVCC snapshot like `pg_dump`. Instead, the backup must hold enough data for PostgreSQL to **crash-recover** the data files to a consistent state via WAL.

Characteristics:

- Covers the physical cluster, including all databases in the cluster.
- Often restores faster than logical dumps for large databases since it copies data files.
- Tied to architecture/major version, platform, tablespaces, and cluster configuration.
- Requires continuous WAL from the backup start/redo point to finish recovery.
- Not suited as a logical export to cherry-pick a few tables.

### 6.3. Crash-Consistent Storage Snapshots

Storage snapshots capture block devices at a point in time. When the server is running, the snapshot resembles a post-crash disk image: data pages may have been written at varying instants, yet WAL recovery can bring them to consistency if all required files/WAL were captured and preserved properly.

A storage snapshot is not automatically application-consistent. Cloud providers may snapshot individual volumes at slightly different timestamps; if `PGDATA`, tablespaces, and `pg_wal` span multiple volumes, you need consistent snapshot groups or backup API coordination.

### 6.4. Application-Consistent Snapshots

Application-consistent means the application/database is coordinated so the snapshot reflects a business-meaningful state. With PostgreSQL, you can:

- Use `pg_dump`/`pg_basebackup` and corresponding WAL mechanisms.
- Pause writes or set an application barrier for the required window.
- Use the backup API when taking online filesystem/storage snapshots.
- Synchronize external systems around the transaction/barrier.

Quiescing the application alone does not replace the PostgreSQL backup protocol; data files and WAL must still be valid.

### 6.5. Consistency Has Multiple Layers

| Layer | Question |
| --- | --- |
| Page/physical | Can pages and WAL crash-recover cleanly? |
| Database/MVCC | Are rows read from the same logical snapshot? |
| Cluster | Are all databases, roles, tablespaces, and shared catalogs included? |
| Application | Do related tables reflect one complete business operation? |
| Distributed | Do databases/services/files outside PostgreSQL share the consistency point? |
| Restore | Can the backup actually restore and serve the application? |

Never use the single word "consistent" to claim all layers are solved.

## 7. Online Physical Backups and the Backup API

PostgreSQL allows taking physical backups while the server is running. To copy data files safely, follow the backup protocol and retain required WAL.

### 7.1. `pg_backup_start` and `pg_backup_stop`

On modern PostgreSQL, SQL functions `pg_backup_start` and `pg_backup_stop` bracket a backup window:

```sql
SELECT pg_backup_start(
    'nightly-backup-2026-11-14',
    false
);

-- Copy/snapshot data files per backup procedure.

SELECT *
FROM pg_backup_stop(true);
```

These functions are building blocks for **physical backups**. They do not copy the data directory or create a complete archive themselves; backup tooling must capture the files, metadata, and required WAL.

### 7.2. The `fast` Parameter

The `fast` argument to `pg_backup_start(label, fast)` controls whether the requested checkpoint executes as quickly as possible or spreads out per checkpoint I/O policy:

- `false`: typical default; the checkpoint spreads writes to reduce I/O bursts.
- `true`: requests a faster checkpoint, which can cause higher I/O load.

Choose based on backup window and storage capacity; do not turn `fast` on for every backup without measuring.

### 7.3. Backup Start Point and WAL

Backup start records the required WAL point and puts the cluster into backup mode. During the backup, PostgreSQL ensures WAL holds enough information to recover the copied data files to an appropriate consistency point.

### 7.4. Snapshotting/Copying Data Files Inside the Backup Window

A conceptual filesystem snapshot workflow:

1. Call `pg_backup_start`.
2. Snapshot **all** relevant data files/tablespaces at one consistency point.
3. Call `pg_backup_stop`.
4. Save the backup label/tablespace map metadata returned by the API per version requirements.
5. Ensure WAL from backup start to backup stop is archived/included and retrievable on restore.

Do not copy only the `base` folder and consider it a complete backup; global catalogs, WAL, tablespaces, and metadata are also required.

### 7.5. Backup Label and Tablespace Map

The backup procedure may require `backup_label` at the backup root and `tablespace_map` when tablespaces exist. With the modern non-exclusive API, `pg_backup_stop` returns metadata contents for backup tooling to write in the proper locations. `pg_basebackup` handles this automatically.

Never fabricate `backup_label` by guessing LSNs/timestamps; use the exact content returned by PostgreSQL.

### 7.6. Ensuring Continuous WAL

Copied data files may contain pages from differing moments. WAL from backup start to backup stop enables redo to restore consistency. If a mandatory segment is missing, the physical backup may fail to boot.

WAL can be gathered via archiving or streaming as supported by backup tooling. Keeping only a snapshot of data files without needed WAL is insufficient.

### 7.7. Older Versions

Backup function names and semantics evolved across PostgreSQL majors. Older versions used `pg_start_backup`/`pg_stop_backup` (with exclusive/non-exclusive variants depending on version); modern PostgreSQL uses `pg_backup_start`/`pg_backup_stop`. Always follow documentation for your exact major version rather than mixing procedures.

### 7.8. Never Leave Backup Mode Open Indefinitely

If backup start is called without properly calling stop, backup state can linger, retaining WAL and inflating disk usage. Use backup management tooling with cleanup/error handling and alerts for abnormally long backup windows.

## 8. `pg_basebackup` Creates Consistent Physical Backups

`pg_basebackup` is the standard tool for taking a base backup from a PostgreSQL server. It uses the replication and backup protocols rather than ad-hoc user file copying.

### 8.1. Example Creating a Directory-Format Backup

```bash
pg_basebackup \
  -h db-primary.example.net \
  -p 5432 \
  -U replication_backup \
  -D /backup/pg/base-2026-11-14 \
  -F plain \
  -X stream \
  -P
```

This requires a role with replication privileges and matching connection settings. Protect passwords via passfiles/secret managers—never place passwords directly on command lines or in shell history.

### 8.2. WAL Methods

`pg_basebackup` offers WAL options:

- `-X stream`: streams required WAL concurrently with the backup over a second replication connection.
- `-X fetch`: fetches required WAL after data copying completes; segments must remain available until fetch finishes.
- `-X none`: excludes WAL from the backup; another mechanism (archive/source) must supply required WAL.

For self-contained recoverable backups, `-X stream` is usually simplest; choose based on capacity/network and actual archive architecture.

### 8.3. Format

- `-F plain`: writes a data directory tree.
- `-F tar`: writes tar archives.

Depending on format, tablespaces may be placed differently; inspect relevant options and backup metadata.

### 8.4. Backup Manifest and Checksums

Modern PostgreSQL majors support backup manifests listing files and checksums. Run `pg_verifybackup` to check manifest/checksum integrity and supported backup conditions:

```bash
pg_verifybackup /backup/pg/base-2026-11-14
```

Verification does not replace restore tests. A backup with a valid manifest can still fail to start due to missing WAL archives, configs, extension binaries, or external dependencies.

### 8.5. Backing Up from a Standby

`pg_basebackup` can back up from a standby in supported configurations. Check major-version limits, standby state, WAL receiver, and WAL availability. Some statistics/backup labels may differ from primary backups; test restores.

### 8.6. Never Run `pg_basebackup` into an Active `PGDATA`

`-D` must point to a dedicated destination directory. Never target a live server's data directory or overwrite an active backup. Keep source and destination strictly separate.

### 8.7. Checking Results

After backup:

- Check exit code and logs.
- Check the backup manifest if present.
- Verify all tablespaces are included.
- Verify WAL is included/available.
- Run `pg_verifybackup` when applicable.
- Test restoring into an independent cluster.

### 8.8. Backup Is Not Restore

`pg_basebackup` succeeding proves the copy protocol completed; it does not prove the target server boots, apps have permissions, the WAL archive is complete, or RTO meets targets. Only a restore drill confirms that.

## 9. Storage Snapshots Across Multiple Volumes and Tablespaces

A PostgreSQL cluster can store data files across several locations:

- `PGDATA` holds control files, system catalogs, and most database files.
- Tablespaces may reside on separate filesystems/volumes.
- `pg_wal` may be relocated via symlink.
- Configuration/log files may sit outside `PGDATA`.

A storage snapshot covering just one volume does not automatically capture the entire cluster.

### 9.1. What Is a Tablespace?

Tablespaces let database objects reside on storage locations outside the default data directory. Catalog `pg_tablespace` tracks tablespace metadata; `pg_tblspc` inside `PGDATA` holds symlinks to physical paths.

```sql
SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
```

For a complete physical backup, all tablespace directories must be copied/snapshotted with the backup set and restored to matching paths or remapped via tooling.

### 9.2. Multiple Volumes Must Share a Consistency Point

Suppose:

```text
Volume A: PGDATA/base
Volume B: tablespace holding indexes
Volume C: pg_wal

Snapshot A at 10:00:00.000
Snapshot B at 10:00:00.300
Snapshot C at 10:00:00.700

Snapshots are not at the same logical instant.
```

If the storage provider lacks atomic consistency groups, these volumes reflect differing states. PostgreSQL's backup protocol and WAL can aid recovery, yet procedures must be designed and tested around how volumes are snapshotted; never assume independent per-volume snapshots equal one cluster-wide snapshot.

### 9.3. Coordinating Online Filesystem Snapshots

Conceptual workflow:

1. Identify `PGDATA`, all tablespace paths, and WAL locations.
2. Call `pg_backup_start` on the primary.
3. Instruct the storage provider to take a **consistent group snapshot** across all volumes holding related data/tablespaces/WAL.
4. Confirm snapshots completed and can be mounted/cloned.
5. Call `pg_backup_stop` and save `backup_label`/`tablespace_map` per version.
6. Ensure required WAL from backup start to backup stop is archived/retained.
7. Record backup metadata: LSNs, timeline, snapshot IDs, tablespace mappings, PostgreSQL version, and timestamps.

Detailed sequencing must follow documentation for your PostgreSQL major version and storage provider. If the snapshot tool only gives crash-consistent snapshots without group consistency, add coordination/freeze mechanisms or use standard backup tools.

### 9.4. Snapshotting `pg_wal` Separately

If `pg_wal` sits on a separate volume, understand how it interacts with data volumes and archiving. A data-only snapshot is insufficient if the backup procedure needs local WAL; WAL may instead be supplied via archive/streaming, provided required start/end segments exist continuously.

Never copy a few arbitrary WAL files into a backup and call it a complete chain. Record start LSN, stop LSN, timeline, and check the archive.

### 9.5. Tablespace Mapping on Restore

If tablespace paths differ on the target server, use appropriate mapping options in your restore/backup tool. Never manually create symlinks pointing to empty volumes. Verify PostgreSQL OS user permissions and mount order before starting the server.

### 9.6. External Configuration

Configuration files may reside outside `PGDATA` (e.g., `postgresql.conf`, `pg_hba.conf`, SSL certificates, include files). A physical backup of the data directory does not necessarily capture all of them. Manage configs via configuration management and back them up separately, tracking versions and secrets securely.

### 9.7. Restores Must Preserve Volume Boundaries

Before starting the restored cluster:

- Mount all volumes at expected paths.
- Ensure tablespace directories exist with correct ownership/permissions.
- Ensure symlinks do not point back to old data directories.
- Ensure WAL/archive paths are accessible.
- Ensure configs and extension libraries are compatible.
- Ensure no other PostgreSQL process is using the same data directory.

## 10. Whole-Data Consistency Within One Database

An MVCC snapshot guarantees table reads inside a single database see one visibility point. However, business consistency also depends on how the application writes data.

### 10.1. Atomic Transactions Create Multi-Table Consistency

Suppose an order creates rows in `orders` and `order_items`:

```sql
BEGIN;

INSERT INTO app.orders(order_id, customer_id, total_amount)
VALUES (1001, 7, 250.00);

INSERT INTO app.order_items(order_id, product_id, quantity)
VALUES
    (1001, 21, 1),
    (1001, 22, 2);

COMMIT;
```

Snapshots before `COMMIT` see neither change; snapshots after `COMMIT` see the entire transaction. A snapshot will never see only the `orders` row while missing `order_items` from the same transaction.

### 10.2. Snapshots Cannot Fix Multi-Transaction Business Workflows

If the application creates an order in transaction A and only records payment seconds later in transaction B, a snapshot taken between those transactions sees the order unpaid. That may be valid if the workflow defines pending payments, or it may need coordination if backups require only completed orders.

MVCC guarantees atomicity per transaction, not across separate independent transactions as one business workflow.

### 10.3. Snapshot Boundaries and Business Barriers

If backups must occur only after workflows finish a stage:

1. Application signals start of backup window.
2. Stop accepting new operations of that type or queue them.
3. Wait for in-flight transactions/workflows to reach a safe state.
4. Record a barrier/epoch ID in the database.
5. Take the snapshot/backup and save the barrier ID in backup metadata.
6. Resume accepting operations.

Barriers must prevent writers from bypassing unmarked; sleeping for a few seconds creates no consistency guarantee.

### 10.4. Snapshots and Foreign Keys

An MVCC snapshot reads versions per visibility. Once a transaction commits FK-constrained changes, snapshots see the transaction as a unit. However, if FKs were disabled, data was loaded out of transaction, or application logic skips constraints, snapshots will not fix pre-existing business violations.

### 10.5. Deferred Constraints

`DEFERRABLE` constraints may be checked at `COMMIT`. Snapshots never see uncommitted transactions, so they never expose intermediate states where a transaction temporarily violates a deferred constraint. This is another reason transaction boundaries matter for logical backups.

### 10.6. Materialized Views

Materialized views store materialized data. Logical dumps can include definitions and contents per dump options; physical backups copy their data files. If a materialized view was stale before backup, a consistent snapshot still holds stale data. Backup consistency does not equal cache/reporting freshness.

### 10.7. Unlogged Tables

Unlogged tables do not write WAL like logged tables, and their contents are truncated after crash/recovery; nor do they replicate to standbys like normal logged tables. If data in an unlogged table needs durable recovery, convert it to a logged table or plan to rebuild it from another source.

## 11. Multiple Databases and External Systems

PostgreSQL snapshot export/import is scoped to a single database. A cluster physical backup covers all databases in the cluster at one physical consistency point, whereas separate logical dumps lack a shared cross-database MVCC snapshot.

### 11.1. Multiple Databases in One Cluster

A PostgreSQL connection targets one specific database. You cannot export an MVCC snapshot from database A and import it into a connection on database B.

If you run:

```bash
pg_dump -Fc -f orders.dump orders_db
pg_dump -Fc -f billing.dump billing_db
```

the two dumps may occur at different points in time. If application logic cross-references them, they may not correspond to the exact same business state.

### 11.2. Physical Backups Cover the Cluster

A cluster physical base backup covers database files in the cluster, shared catalogs, and WAL needed to recover physical state. This fits when one cluster-wide physical consistency point is needed, provided all tablespaces/WAL are included.

### 11.3. Cross-Database Business Transactions

An application connecting to databases A and B and issuing two independent commits has no shared atomic transaction merely because both reside in the same PostgreSQL cluster. If atomicity is required, use an appropriate architecture (such as distributed transactions/2PC with matching operations and recovery) or saga/outbox patterns with durable state.

### 11.4. Microservices and Multiple Clusters

A PostgreSQL snapshot cannot automatically synchronize:

- Another service's database.
- Kafka/Pulsar offsets.
- Redis/caches.
- Object storage.
- Filesystems or document stores.
- Payment/email providers.

Establish a **global consistency point** using barriers, event offsets, CDC positions, coordinated checkpoints, or quiesce workflows. Logging each backup's wall-clock timestamp does not prove they share one state.

### 11.5. Event Streams and Database Snapshots

If the database is updated from an event stream, backup metadata can record:

- Database snapshot/backup LSN.
- Consumer group offsets.
- Source partition offsets.
- CDC replication slot/consistent point.
- Application epoch/barrier ID.

On restore, you must know which offset to resume replaying events from so events are neither skipped nor double-applied relative to materialized database state.

### 11.6. External Object Storage/Files

If a database row stores an object key, a DB snapshot preserves only the key and metadata; it does not snapshot bytes inside the bucket. If the object is overwritten or deleted after the snapshot, the restored database points to a missing or altered object.

Solutions can include:

- Object versioning while storing the version ID in the DB.
- Backing up buckets under a matching retention window.
- Uploading to staging then publishing immutable object keys.
- Snapshotting/manifesting object lists and checksums at the consistency point.
- Pruning only after all DB backups referencing old objects expire.

### 11.7. Two-Phase Commit Does Not Automatically Back Up External Resources

2PC can coordinate commits among resource managers supporting the protocol, but cannot turn an object store or ordinary HTTP API into a transactional participant. For non-2PC systems, use outbox/saga patterns and backup barriers.

## 12. Sequence State and Snapshot Exceptions

Sequences are a common surprise when aiming for a "whole-data" snapshot.

### 12.1. `nextval` Does Not Roll Back

`nextval` issues sequence values immediately; transaction rollbacks do not return issued values. This avoids locking and ensures fast allocation, though sequences lack MVCC row visibility.

### 12.2. Sequences Can Advance During `pg_dump`

Applications can keep calling `nextval` while `pg_dump` runs. Dumped table rows and dumped sequence state do not necessarily form a synchronized MVCC snapshot. After restore, sequences may need reconciliation so future values exceed existing keys.

### 12.3. Checking Sequences After Restore

Example for a table with serial/identity:

```sql
SELECT max(id) AS max_id
FROM app.orders;

SELECT last_value, is_called
FROM app.orders_id_seq;
```

Actual sequence names may vary. Run `setval` only inside a maintenance window after confirming the exact sequence, ownership, and concurrency; never reset sequences while writers are actively drawing new values.

### 12.4. Reconciling Sequences

A post-restore pattern (after stopping writers and verifying the right sequence):

```sql
SELECT setval(
    'app.orders_id_seq',
    COALESCE((SELECT max(id) FROM app.orders), 1),
    EXISTS (SELECT 1 FROM app.orders)
);
```

When the table is empty, `is_called=false` makes the next `nextval` return the start value per sequence semantics. For sequences with custom increments/starts/minvalues, check carefully before applying this pattern.

### 12.5. Identity Columns

Identity columns also rely on sequences under the hood. Never assume `GENERATED ALWAYS AS IDENTITY` makes sequence state transactional or perfectly synchronized with concurrent dumps.

### 12.6. Large Objects and External References

Large Objects store separate payloads and must be included in dumps/backups properly; an OID column inside a row does not contain the file itself. If applications store OIDs inside JSON/text/custom columns, dump/cleanup tools may not recognize references the way native `oid` columns do.

## 13. Components Not Automatically Covered by a Snapshot

| Component | Logical `pg_dump` Database | Physical Base Backup |
| --- | --- | --- |
| Table rows/schemas in database | Yes, per dump options/snapshot. | Yes, in data files. |
| Indexes/constraints/functions | Per dumped objects. | Yes, in data files/catalogs. |
| Large Objects | Yes when included via options/format. | Yes, in physical data files. |
| Roles/global privileges | No; dump globals separately. | Shared catalogs in cluster, though environment configs/identities still need management. |
| Tablespace definitions/data | Tablespace definitions/globals must be managed separately; dumps do not copy physical data directories. | Tablespace data must be backed up completely. |
| Sequence state | Dumps sequence state, though not a pure MVCC snapshot. | Yes, in data files/WAL recovery. |
| PostgreSQL config files | No. | Not necessarily if outside `PGDATA`. |
| Extension binaries/OS packages | No. | Not necessarily; compatible builds needed on host. |
| Object storage/file shares | No. | No. |
| Kafka/CDC offsets | Not automatically. | Not automatically. |
| Other databases in cluster | No in a single-database `pg_dump`. | Yes in a physical cluster backup. |
| Other PostgreSQL clusters | No. | No. |
| Secrets/certificates | No. | Not necessarily; manage separately. |
| Temporary tables/sessions | Not persistent data needing restore. | Not recovered like normal persistent objects. |

This table is a summary; options, PostgreSQL major versions, extensions, and backup tools can alter exact coverage. Always inspect backup manifests and test real restores.

## 14. Long-Lived Snapshots, `VACUUM`, and System Impact

A backup holding a snapshot for an extended time affects dead-tuple reclamation.

### 14.1. Why Must `VACUUM` Track the Oldest Snapshot?

MVCC must keep old row versions if any live transaction can still see them. A long `REPEATABLE READ` backup transaction holds back the `xmin` horizon, preventing `VACUUM` from removing dead tuples.

Consequences:

- Heap/index bloat grows.
- Disk usage climbs.
- Autovacuum faces heavier catch-up work once the snapshot closes.
- Some tables can approach transaction ID wraparound if vacuum is blocked too long.

### 14.2. Observing Transactions Holding Snapshots

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    backend_xmin,
    age(backend_xid) AS xid_age,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

`backend_xmin` reveals which backends pin the snapshot horizon. Visibility of queries/metadata depends on roles and configuration. Never kill a transaction solely for being long-running; verify whether it is a backup, report, logical replication, or business transaction.

### 14.3. `idle in transaction`

A session starting `REPEATABLE READ`, exporting a snapshot, and waiting on slow file copies/networks can sit in `idle in transaction`. This is risky because it pins snapshot/transaction resources.

Solutions:

- Keep the exporter transaction open only long enough for consumers to import the snapshot.
- Never use a DB transaction to wait on manual uploads/downloads.
- Enforce timeouts/monitoring on backup orchestration.
- Ensure cleanup/rollback of the exporter if a consumer fails.

### 14.4. Exported Snapshots and Exporter Lifecycle

If the exporter closes too early, lagging consumers cannot import the snapshot. If the exporter stays open too long, `VACUUM` is held back. Balance both needs via orchestrated deadlines and explicit worker import acknowledgements.

### 14.5. Backups on a Hot Standby

Logical dumps on a standby can hit recovery conflicts when WAL replay needs to remove row versions still read by the backup query. Queries may be canceled according to hot standby conflict settings.

`hot_standby_feedback` can reduce cancellations by sending xmin feedback to the primary to retain needed dead tuples, at the trade-off of primary bloat. Never enable it without measuring impact.

### 14.6. Snapshots Cannot Run Indefinitely

Backups must have SLAs, timeouts, and alerts. A snapshot lingering for hours/days creates retention pressure and degrades system health even if the dump eventually finishes.

## 15. Designing Application-Wide Consistency Points

When data lives in one database and key business work commits in single transactions, MVCC snapshots usually suffice. When data spans multiple transactions, databases, or external systems, a coordination protocol is needed.

### 15.1. Recording Backup Epochs/Barriers

Applications can store an epoch ID:

```sql
CREATE TABLE ops.backup_epochs (
    epoch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status text NOT NULL,
    barrier_created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    snapshot_lsn pg_lsn,
    notes text
);
```

Barriers only mean something if all writers obey the protocol. One barrier row does not stop uncoordinated transactions from writing.

### 15.2. Application Quiesce

A quiesce workflow can:

1. Switch APIs to maintenance/read-only or queue writes.
2. Wait for in-flight transactions to finish.
3. Wait for multi-step workflows to reach a business checkpoint.
4. Write a barrier/epoch into the DB.
5. Take the snapshot/backup.
6. Record LSN/snapshot metadata and reopen writes.

Quiesce duration must fit within RTO/RPO/availability budgets.

### 15.3. Queues and Event Offsets

If workers consume messages and update the DB, DB snapshots must align with offsets:

```text
Message partition P:
  offset 1000 -> DB transaction committed
  offset 1001 -> in progress
  offset 1002 -> not yet received

Backup consistency point:
  DB state includes offset 1000
  consumer offset saved/synchronized accordingly
  after restore, resume from offset 1001
```

If the offset commits ahead of DB state or vice versa, events get skipped or duplicated. Store offsets inside the DB transaction or use inbox/outbox protocols.

### 15.4. CDC and Replication Slots

When using logical decoding/CDC, snapshot consistency points must coordinate with replication slots/consistent LSNs. Pipelines normally need an initial snapshot plus a WAL stream starting at the matching LSN so nothing is lost between snapshot and streaming.

Never record merely "dump started at 10:00" and assume CDC from 10:00 has no gaps. LSNs are far more exact than timestamps; still follow the connector's protocol to bridge snapshot and WAL.

### 15.5. Cross-Database Snapshots

PostgreSQL does not offer one exported MVCC snapshot importable simultaneously across independent databases. Options:

- Use a physical cluster backup if a single physical cluster point suffices.
- Consolidate data needing atomicity into the same database/transaction boundary.
- Pause writers at a shared barrier and dump each database.
- Use application-level epochs and post-restore reconciliation.

### 15.6. External Object Stores

A safe protocol for files:

1. Upload objects under immutable/staging keys.
2. Compute checksums and sizes, verifying object existence.
3. Commit DB metadata pointing to the exact object version.
4. Back up DB alongside the bucket's manifest/version inventory.
5. Never delete old objects until all DB backups referencing them pass retention.

Object version IDs matter far more than mutable keys that can be overwritten post-backup.

### 15.7. Sagas and Business Consistency

If cross-service workflows use sagas, a snapshot may catch a saga mid-flight. That is not necessarily wrong if the state machine is durably persisted and can resume or compensate after restore. If backups require only terminal sagas, place a barrier and check pending workflows.

## 16. Backup Metadata and Consistency Manifests

A solid backup needs a manifest describing its state and scope.

### 16.1. Recommended Metadata Fields

| Field | Meaning |
| --- | --- |
| `backup_id` | Unique ID of the backup set. |
| `backup_type` | logical dump, physical base backup, storage snapshot, PITR anchor. |
| `started_at`/`finished_at` | Timestamps in a standard timezone. |
| `server_version` | PostgreSQL major/minor and tool versions. |
| `system_identifier` | Cluster identifier for physical backups. |
| `timeline` | Timeline of the WAL stream. |
| `start_lsn`/`stop_lsn` | Associated WAL range when provided by backup type. |
| `database_list` | Covered databases. |
| `tablespace_map` | Tablespace paths/IDs. |
| `snapshot_ids` | Storage provider snapshot IDs/consistency group. |
| `wal_archive_range` | Segments/LSNs needed for recovery. |
| `globals_backup` | Whether roles/tablespaces/global configs were backed up. |
| `app_epoch` | Business barrier ID if present. |
| `external_manifest` | Object versions/event offsets/other system checkpoints. |
| `checksum`/`manifest` | Integrity data for backup artifacts. |
| `retention_until` | Earliest permitted purge timestamp. |
| `restore_test_id` | Result of the latest restore drill. |

### 16.2. Do Not Rely on Timestamps Alone

Timestamps cannot prove two backups share a consistency point. Clock skew, timezones, transaction latency, and asynchronous replication prevent wall-clock time from substituting for LSNs/snapshot IDs/epochs.

### 16.3. LSN Is Not a Global Transaction ID

An LSN marks a WAL position inside one timeline/cluster. It does not compare directly against LSNs from another cluster after cloning/reseeding/timeline forks. Manifests need `system_identifier` and `timeline` to interpret LSNs in context.

### 16.4. Checking Completeness

A manifest should answer:

- Which databases were backed up?
- Which tablespaces were copied?
- Which WAL range is required?
- Which storage snapshots were created together?
- Which roles/extensions/configs must be restored?
- Which external objects/offsets are linked?
- Did the latest test restore pass?

## 17. Sample Backup and Restore Workflows

### 17.1. Logical Backup of One Database

```bash
pg_dump -Fc -f appdb-2026-11-14.dump appdb
pg_dumpall --globals-only > globals-2026-11-14.sql
```

These two commands have distinct scopes. The first dumps one database; the second dumps global objects. If consistency across multiple databases is needed, do not assume these two steps share one snapshot.

### 17.2. Parallel Logical Backup

```bash
pg_dump -Fd -j 4 -f appdb-directory appdb
```

Parallel dump requires directory format. `pg_dump` coordinates the snapshot across workers.

### 17.3. Using an Exported Snapshot with `pg_dump`

Session A:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot();
```

Keep the transaction open and copy the returned snapshot ID. In a shell, run:

```bash
pg_dump --snapshot='00000003-0000001B-1' -Fc \
  -f appdb-consistent.dump appdb
```

Once `pg_dump` has imported the snapshot and finished its work, close Session A:

```sql
COMMIT;
```

The snapshot ID is an example; substitute the real ID. Never commit the exporter before `pg_dump` imports the snapshot. Check version/tool options if combining with parallel dumps or multiple workers.

### 17.4. Physical Backup with `pg_basebackup`

```bash
pg_basebackup \
  -h db-primary.example.net \
  -U replication_backup \
  -D /backup/pg/base-current \
  -F plain \
  -X stream \
  -P
```

Save outputs/logs and the backup manifest. If PITR is needed, configure continuous WAL archiving beyond the base backup.

### 17.5. Verifying Backups

```bash
pg_verifybackup /backup/pg/base-current
```

Run only when the backup format/version has a manifest and tool support. For logical dumps, inspect the archive list:

```bash
pg_restore --list appdb-2026-11-14.dump
```

This checks artifacts; it does not replace a restore drill.

### 17.6. Restoring a Logical Dump

```bash
createdb restored_appdb
pg_restore -d restored_appdb appdb-2026-11-14.dump
```

Create roles/globals and extension dependencies in proper order. Check owners/privileges and data consistency.

### 17.7. Restoring a Physical Backup

Physical restore steps depend on format and PostgreSQL major version:

1. Prepare host/data directory and tablespace paths.
2. Restore the base backup.
3. Configure archive/restore command and recovery target if needed.
4. Supply required WAL and timeline history.
5. Start PostgreSQL into crash/archive recovery.
6. Wait for recovery to complete or pause at target.
7. Verify database and application before opening traffic.

Never start two servers simultaneously pointing at the same physical data directory.

### 17.8. Restores Missing WAL

An online physical backup needs WAL from backup start to backup stop. Without that WAL, the backup may fail recovery. Never delete WAL archives thinking "we already have the base backup"; retention policies must keep the WAL chain continuous.

## 18. Snapshots, PITR, and Consistency Points

Point-in-Time Recovery (PITR) is not restoring an exported MVCC snapshot. PITR uses a base backup and WAL to reconstruct database state at a target.

### 18.1. Base Backups as Anchors

The base backup yields consistent data files after recovery. Continuous WAL afterward lets replay advance to a target time/LSN. Older base backups increase WAL replay volume and restore duration.

### 18.2. Backup Labels and Start/Stop LSNs

Backup metadata tells recovery which WAL range is required. Record exact start/stop LSNs, timeline, and labels. Never replace these LSNs solely with timestamps.

### 18.3. WAL Archive Continuity

For PITR to succeed, every needed WAL segment from the base backup to the recovery target (along the right timeline/history) must exist. One missing middle segment stops recovery even if newer segments exist in the archive.

### 18.4. Recovery Targets

PostgreSQL can halt recovery by time, LSN, transaction ID, or named restore point depending on version:

```conf
restore_command = 'cp /archive/%f %p'
recovery_target_time = '2026-11-14 10:15:00+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

This is illustrative configuration. Archive paths, timezones, timelines, and targets must be verified in a test restore. Never copy blindly into production.

### 18.5. Snapshots Do Not Replace WAL Archives

A point-in-time storage snapshot gives one data volume state. Recovering to a point after the snapshot or before a logical bug requires a matching WAL/backup chain. Snapshots do not capture every state between two snapshot runs.

### 18.6. Restoring to a Point Before a Logical Error

For instance, a user accidentally drops a table at 10:20. To PITR to 10:19:59:

1. Select a base backup taken before 10:20.
2. Verify continuous WAL archive up to the target.
3. Restore into an isolated cluster.
4. Set the recovery target before the DROP operation.
5. Start recovery and pause/promote per runbook.
6. Verify data, then extract/reintroduce the needed data back into the system.

Never overwrite the current primary before verifying the restore.

### 18.7. Timelines and Failover

After promotion/failover, a new timeline branches from the old timeline. The archive must store history files and WAL on the right branch. A target time alone is insufficient if the wrong timeline is selected; record timelines in backup manifests.

## 19. RPO, RTO, and Consistency Requirements

### 19.1. RPO

**Recovery Point Objective** is the maximum data loss accepted after an incident, usually expressed in time. A 5-minute RPO means backup/replication must allow recovering to a point no older than roughly 5 minutes before the incident (per organizational definition).

RPO depends on:

- WAL flush/durability settings.
- WAL archive frequency and archive success.
- Base backup age.
- Synchronous/asynchronous replication and failover policy.
- External object/event/offset consistency.

MVCC snapshots alone do not determine RPO.

### 19.2. RTO

**Recovery Time Objective** is the maximum allowed duration to restore service after an incident. RTO includes:

```text
Incident detection
  + restore/failover decision
  + host/storage provisioning
  + base backup restore or standby promotion
  + WAL replay
  + database/application validation
  + opening traffic
```

A backup created fast is not guaranteed to restore fast. Measure the entire end-to-end flow.

### 19.3. Consistency Point Differs from Backup Timestamp

A backup starting at 01:00 and finishing at 01:20 does not mean the logical snapshot represents 01:10. With `pg_dump`, snapshot visibility is fixed when the transaction acquires its snapshot. With physical backups, start/stop LSNs and WAL define recovery semantics. With storage group snapshots, snapshot IDs and creation points must coordinate with the backup API.

### 19.4. Multi-System RPO

If the DB commits order 1000 and Kafka reaches offset 1000, yet DB backups and offset snapshots are unsynchronized, restores can replay already-applied events or skip unapplied ones. Distributed-system RPO must encompass all systems and offsets, not just PostgreSQL.

### 19.5. Logical vs. Physical Restore RTO

Logical dumps rebuild schemas, indexes, and load rows; they can be slow on large databases yet flexible. Physical backups copy/restore data files faster, though WAL replay, version/platform compatibility, and startup remain. Choose based on empirically tested RTO goals.

### 19.6. Backup Frequency Is Not Snapshot Consistency

Backing up every 5 minutes does not guarantee a 5-minute RPO if archives fail or backups cannot restore. Conversely, continuous WAL archiving can deliver fine-grained PITR between base backups if the archive chain stays complete.

## 20. Verifying Consistency After Backup/Restore

A backup job exiting 0 is necessary yet insufficient. Verify contents and usability.

### 20.1. Integrity Checks

- Verify backup manifests/checksums if supported by tooling.
- Check file counts/sizes and WAL segments.
- Cross-check checksums of external objects.
- Verify tablespace maps, system identifiers, and timelines.
- Archive logs/exit codes for every step.

### 20.2. Database Consistency Checks

After restore, run business checks:

```sql
-- Example: no orphan order items.
SELECT count(*) AS orphan_items
FROM app.order_items i
LEFT JOIN app.orders o USING (order_id)
WHERE o.order_id IS NULL;

-- Example: order totals match line items.
SELECT o.order_id
FROM app.orders o
JOIN (
    SELECT order_id, sum(quantity * unit_price) AS item_total
    FROM app.order_items
    GROUP BY order_id
) i USING (order_id)
WHERE o.total_amount <> i.item_total;
```

These queries are examples; real business invariants must be defined and handle nulls/rounding/discounts/taxes accurately.

### 20.3. Sequence Validation

Verify the next `nextval` will not collide with existing keys post-restore. If `setval` is needed, stop writers and use exact sequence names and values.

### 20.4. Large Objects and External Files

Verify OIDs open cleanly with matching sizes/checksums; confirm object storage keys/version IDs exist and are readable. A metadata row existing in the DB does not prove the binary payload was backed up.

### 20.5. Roles and Privileges

Test using actual application roles, not just superuser. Check:

- Login/authentication.
- Schema/table/sequence privileges.
- RLS policies and tenant contexts.
- Extension permissions.
- Tablespace access.
- Certificates/secrets/configs.

### 20.6. Application Smoke Tests

After restore, run a controlled end-to-end flow: read users, query orders, download attachments, write a test record if the test environment allows, publish/consume events, and verify. Open live traffic only once critical paths pass.

### 20.7. Restore Drills

A backup is trustworthy when operators can restore it under production-like conditions within RTO/RPO. Test schedules should cover:

- Logical restores.
- Physical restores.
- PITR to targets.
- Standby failover.
- Restoring roles/configs/tablespaces.
- External object/event offset recovery.

## 21. Common Snapshot/Backup Design Mistakes

### 21.1. Using `READ COMMITTED` for Custom Multi-Statement Dumps

Each statement can see a different snapshot, exporting tables from inconsistent points. Use one `REPEATABLE READ` transaction or backup tools that manage snapshots.

### 21.2. Giving Each Worker Its Own Snapshot

Workers can see differing committed changes. Use `pg_dump` parallel mode or shared exported snapshots.

### 21.3. Exporting a Snapshot and Closing the Exporter Immediately

Consumers that haven't imported yet cannot use the snapshot ID. Keep the exporter transaction open until all consumers import.

### 21.4. Holding an Exporter Transaction Open for Hours

Old snapshots pin dead tuples and cause bloat. Keep exporters open only as long as orchestration needs, monitoring `backend_xmin` and timeouts.

### 21.5. Assuming MVCC Snapshots Freeze Sequences

Sequence `nextval` is non-transactional. Reconcile sequence values after restore when needed.

### 21.6. Dumping Two Databases and Treating Them as One Consistency Point

`pg_dump` snapshots per database. Use physical cluster backups or application barriers to coordinate.

### 21.7. Copying Only `PGDATA`

Tablespaces/WAL can sit outside `PGDATA`. Inventory and back up all locations.

### 21.8. Snapshotting Individual Volumes at Different Times

This creates an out-of-sync backup set. Use consistency groups or backup protocols properly, and test restores.

### 21.9. Storage Snapshots Missing Required WAL

Data files may need WAL for crash recovery. Ensure backup start/stop WAL ranges or archives/streams cover them.

### 21.10. Calling `pg_backup_start` and Forgetting `pg_backup_stop`

Extended backup mode pins WAL and grows storage. Use orchestration with cleanup/error handling.

### 21.11. Dumping Only OIDs While Omitting Large Objects

Metadata rows survive while payloads vanish. Use appropriate LO backup options and test reading objects post-restore.

### 21.12. Forgetting Roles/Tablespaces

Single-database `pg_dump` omits cluster-wide globals. Dump/back up globals separately and restore in order.

### 21.13. Assuming `pg_dump` Bundles Extension Binaries/Configs

Dumps may contain `CREATE EXTENSION` without installing packages/libraries on the target host. Prepare dependencies and configs separately.

### 21.14. Treating a DB Snapshot as an Object Storage Snapshot

Database keys survive while object versions get deleted/overwritten. Use versioning/manifests and aligned retention.

### 21.15. Ignoring Event Offsets

Restoring a DB without aligned consumer offsets replays duplicates or drops events. Store offsets/barriers within the consistency protocol.

### 21.16. Mistaking Physical Backups for MVCC Images

Physical backups rely on WAL recovery, not a single snapshot `SELECT`. Follow the physical backup protocol.

### 21.17. Mistaking Checkpoints for Backups

Checkpoints create internal recovery points, not independent copies or PITR archives.

### 21.18. Assuming `pg_verifybackup` Proves Application Functionality

Manifest checks do not test application permissions, external files, restore environments, or RTO. Run restore drills.

### 21.19. Not Retaining WAL Long Enough

Having base backups whose WAL archive was purged prematurely breaks PITR targets. Retention must track backup age and WAL chains.

### 21.20. Skipping Periodic Restore Tests

Backups can be corrupted, miss tablespaces, mismatch versions, or lack WAL. Restore tests confirm recoverability.

### 21.21. Using Timestamps as Global Barriers

Clock skew and commit latency prevent timestamps from synchronizing transaction state. Use LSNs, snapshot IDs, event offsets, and application epochs.

### 21.22. Pausing Writes While Ignoring In-Flight Workflows

Multi-transaction workflows can be mid-step. Waiting for DB transactions alone is insufficient; wait for business workflows to reach safe/terminal barriers.

### 21.23. Checking Only Row Counts

Matching row counts do not guarantee relationships, checksums, sequences, Large Objects, or external references. Verify business invariants and end-to-end reads.

### 21.24. Restoring into a Running Data Directory

Can corrupt or overwrite the live cluster. Restore into an isolated data directory/host; verify processes and mounts first.

### 21.25. Failing to Record Timelines/System Identifiers

Risks mixing WAL or backups from the wrong cluster/timeline. Record identities, timelines, and LSNs in manifests.

## 22. Lab 1: Observing `READ COMMITTED` vs. `REPEATABLE READ`

Goal: observe how a transaction can see two different snapshots under `READ COMMITTED` yet keep one snapshot under `REPEATABLE READ`.

### 22.1. Preparing Data

Setup session:

```sql
CREATE SCHEMA IF NOT EXISTS snapshot_lab;

DROP TABLE IF EXISTS snapshot_lab.accounts;
CREATE TABLE snapshot_lab.accounts (
    account_id integer PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO snapshot_lab.accounts
VALUES (1, 100.00), (2, 200.00);
```

### 22.2. Testing `READ COMMITTED`

Session A:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT sum(balance)
FROM snapshot_lab.accounts;
```

Initial result is 300.

Session B:

```sql
BEGIN;
UPDATE snapshot_lab.accounts
SET balance = balance + 50
WHERE account_id = 1;
COMMIT;
```

Back in Session A:

```sql
SELECT sum(balance)
FROM snapshot_lab.accounts;

COMMIT;
```

The second result is 350 because the new statement took a fresh snapshot after Session B committed.

### 22.3. Testing `REPEATABLE READ`

Session A:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT sum(balance)
FROM snapshot_lab.accounts;
```

Session B executes the `UPDATE` and `COMMIT` as above. Session A runs again:

```sql
SELECT sum(balance)
FROM snapshot_lab.accounts;

COMMIT;
```

Session A still sees the total from its initial snapshot. After `COMMIT`, a new transaction sees the updated value.

### 22.4. Takeaway for Backups

If a custom backup script runs multiple `SELECT`s under `READ COMMITTED`, it can mix states. `pg_dump` uses a snapshot transaction so tables within one database are dumped consistently.

## 23. Lab 2: Exporting and Importing Snapshots

Goal: multiple sessions read the exact same snapshot.

### 23.1. Exporter Session

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

Copy the actual snapshot ID returned. Keep this transaction open.

### 23.2. Consumer Session A

Replace the snapshot ID with the exporter's value:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT count(*) FROM snapshot_lab.accounts;
```

### 23.3. Consumer Session B

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT sum(balance) FROM snapshot_lab.accounts;
```

Both consumers share the same visibility point even across separate connections in the same database.

### 23.4. Testing Concurrent Modifications

In a third session, `UPDATE`/`INSERT` and `COMMIT`. Both consumers still see the imported snapshot without subsequent commits.

### 23.5. Finishing Up

`COMMIT` consumer transactions. Once all consumers have imported the snapshot and finished, `COMMIT` the exporter. Try opening a new consumer after the exporter closes: the old snapshot ID can no longer be imported.

### 23.6. Limitations

Snapshot identifiers live only for the exporter transaction's lifetime; they do not cross databases, survive restarts, or replace backup files.

## 24. Lab 3: `pg_dump` While Applications Write Data

Goal: create a logical dump during concurrent DML and verify the dump represents one consistent state.

### 24.1. Create Lab Table

```sql
DROP TABLE IF EXISTS snapshot_lab.events;
CREATE TABLE snapshot_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO snapshot_lab.events(event_name)
SELECT 'initial-' || g
FROM generate_series(1, 1000) AS g;
```

### 24.2. Run `pg_dump`

```bash
pg_dump -Fc -f snapshot-lab.dump snapshot_lab_db
```

Substitute your actual lab database name. To test parallel dump, use directory format and `-j`.

### 24.3. Concurrent Writer

While `pg_dump` runs, another session inserts more rows:

```sql
INSERT INTO snapshot_lab.events(event_name)
SELECT 'during-dump-' || g
FROM generate_series(1, 10000) AS g;
```

The dump reflects `pg_dump`'s snapshot; rows committed after that snapshot are omitted from that dump.

### 24.4. Restore into a New Database

```bash
createdb snapshot_lab_restore
pg_restore -d snapshot_lab_restore snapshot-lab.dump
```

Compare dumped data against the snapshot state using a recorded marker/transaction. Never compare naively against the live table after writers committed thousands more rows.

### 24.5. Inspect Dump Artifact

```bash
pg_restore --list snapshot-lab.dump
```

Inspect archive contents, then query the restored database. Listing contents does not prove data correctness; query/restore checks verify it.

## 25. Lab 4: Physical Base Backup and Verification

Goal: verify that a physical backup contains data files and required WAL.

### 25.1. Prerequisites

- An isolated PostgreSQL lab server.
- A replication/backup role with appropriate least-privilege rights.
- `pg_hba.conf` allowing replication connections from the backup host.
- Destination storage with ample space outside current `PGDATA`.
- PostgreSQL client tools of matching major or compatible version.

### 25.2. Run `pg_basebackup`

```bash
pg_basebackup \
  -h 127.0.0.1 \
  -p 5432 \
  -U replication_backup \
  -D /backup/lab-base \
  -F plain \
  -X stream \
  -P
```

Adjust host, port, and path to your lab. Never put passwords directly in commands; use passfiles/secret management.

### 25.3. Verify Manifest

```bash
pg_verifybackup /backup/lab-base
```

If a backup manifest exists and is supported by your version, the tool checks file checksums/manifest consistency. Log output and exit code.

### 25.4. Restore into a Separate Cluster

Use a new data directory, tablespace mapping, and separate port. Configure WAL archiving if recovery needs it. Start the restored server per matching major-version docs, never sharing the source data directory.

### 25.5. Verify Data

Run business queries and compare against the backup point. Record server-ready and app-ready times to build an RTO baseline.

## 26. Lab 5: Simulating a Consistency Barrier

Goal: recognize that MVCC snapshots do not automatically bundle multiple transactions into one workflow.

### 26.1. Create Order/Payment Tables

```sql
CREATE TABLE snapshot_lab.orders (
    order_id bigint PRIMARY KEY,
    status text NOT NULL
);

CREATE TABLE snapshot_lab.payments (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES snapshot_lab.orders(order_id),
    status text NOT NULL
);
```

### 26.2. Create a Two-Step Workflow State

Transaction A:

```sql
BEGIN;
INSERT INTO snapshot_lab.orders VALUES (9001, 'pending_payment');
COMMIT;
```

Pause before creating the payment.

### 26.3. Snapshot Mid-Workflow

A `REPEATABLE READ` transaction can see order 9001 as pending without a payment yet. This snapshot is still **MVCC-consistent** because transaction A committed and the payment transaction has not run yet.

### 26.4. Completing the Workflow

```sql
BEGIN;
INSERT INTO snapshot_lab.payments(order_id, status)
VALUES (9001, 'captured');
UPDATE snapshot_lab.orders
SET status = 'paid'
WHERE order_id = 9001;
COMMIT;
```

Snapshots before this transaction see neither the payment nor `paid` status; snapshots afterward see both changes together.

### 26.5. Barrier Takeaway

If backups must accept only paid orders, you need a barrier/workflow query checking pending orders and waiting for completion or recording recoverable state. MVCC does not automatically wait for multi-transaction sagas.

## 27. Case Studies

### 27.1. Case A: Long-Running `pg_dump` During Peak Hours

**Context:** Large database, dump runs 90 minutes while the application writes continuously.

**Symptoms:** Dump is consistent, yet table bloat increases, autovacuum cannot reclaim certain dead tuples, and disk usage climbs.

**Analysis:** The long-lived snapshot retains old row versions needed by `pg_dump`. MVCC allows writers to proceed, though not for free.

**Action:** Monitor `backend_xmin`, dump duration, dead tuples, and autovacuum; use parallel dumps where appropriate, boost I/O/backup host capacity, or choose another backup strategy. Do not kill an exporter mid-run expecting workers to import a fresh snapshot.

### 27.2. Case B: Two Separate `pg_dump`s for `orders_db` and `billing_db`

**Context:** Application stores orders in database A and billing in database B. Two dump jobs run 15 minutes apart.

**Risk:** An order commits between the two dumps, leaving restored databases at different consistency points.

**Action:** If whole-cluster physical state is needed, use physical backups. If separate logical dumps are needed, create an application barrier/maintenance window pausing related writes and recording a shared epoch before dumping; test cross-database reconciliation.

### 27.3. Case C: Storage Snapshots of Three Volumes Not Taken Simultaneously

**Context:** `PGDATA`, tablespace, and WAL reside on three cloud disks; provider snapshots each disk individually.

**Risk:** Each volume reflects a different timestamp. The backup set may fail to recover if WAL/data states mismatch.

**Action:** Use consistency groups/atomic multi-volume snapshots or backup tools supporting the PostgreSQL backup protocol. Record snapshot IDs, start/stop LSNs, tablespace maps, and test restores.

### 27.4. Case D: Sequences Falling Behind After Logical Restore

**Context:** During `pg_dump`, the application keeps drawing IDs from sequences. After restore, `nextval` returns values lower than existing keys.

**Risk:** New `INSERT`s violate PK/`UNIQUE` constraints.

**Action:** Stop writers during reconciliation; compare sequence states against max keys and run `setval` on the right sequences. Handle multiple sequences/custom increments individually per actual metadata.

### 27.5. Case E: DB Snapshot Retained After Object Storage Lifecycle Deletion

**Context:** Database backup preserves rows with `object_key`, yet bucket lifecycle deletes objects after 30 days while DB backups stay for 90 days.

**Risk:** Restored DB points to deleted objects.

**Action:** Enable object versioning/backup buckets with retention at least matching DB backup retention; manifests link DB backup IDs to object versions/checksums.

### 27.6. Case F: Initial Logical Replication Snapshot and CDC

**Context:** Pipeline takes an initial snapshot and starts streaming WAL changes. If the snapshot point and CDC start LSN do not align, changes are dropped or duplicated.

**Action:** Use the logical decoding connector's consistent snapshot/LSN mechanism; persist slot, snapshot metadata, and offsets; test crashes between snapshot and streaming.

### 27.7. Case G: Backup from a Hot Standby Canceled

**Context:** `pg_dump` runs on a standby, yet WAL replay needs to clean up row versions still read by the backup query.

**Symptoms:** Query canceled due to recovery conflict.

**Action:** Inspect hot standby conflict logs and backup durations; consider dumping from primary, adjusting schedule/volume, or enabling `hot_standby_feedback` with clear understanding of bloat impact. Never raise timeouts blindly.

### 27.8. Case H: `pg_basebackup` Succeeds Yet Restore Fails to Boot

**Context:** Backup command returns exit 0, but the target server lacks a tablespace mount or needed WAL.

**Risk:** Unusable backup artifact.

**Action:** Verify manifests, tablespace paths, WAL methods, system identifiers, versions, and logs; run periodic restore drills on an isolated host.

### 27.9. Case I: MVCC-Valid Backup With Pending Business State

**Context:** Order transaction committed first; payment transaction had not run when the snapshot was taken.

**Risk:** Backup holds a `pending_payment` order. Database-consistent, yet fails a requirement to "back up only completed orders."

**Action:** Define a business barrier and drain pending workflows before snapshotting, or ensure saga state is complete enough to resume post-restore.

### 27.10. Case J: Database Backup Missing Roles

**Context:** Single-database `pg_dump` is restored onto a new server, yet roles/owners do not exist.

**Symptoms:** Restore throws owner/privilege errors or apps cannot access data.

**Action:** Dump/restore globals separately, prepare role mappings, and test under application roles. Never use superuser to mask permission errors.

## 28. Practice Exercises

Exercises use the lab database and `snapshot_lab` schema created earlier. Questions on storage/cloud snapshots require design descriptions; never take snapshots or stop production clusters.

### Exercise 1. MVCC

What is a snapshot in PostgreSQL? What does it help decide when reading row versions?

### Exercise 2. `READ COMMITTED`

Why can two `SELECT`s inside a `READ COMMITTED` transaction observe two different states?

### Exercise 3. `REPEATABLE READ`

Why is `REPEATABLE READ` better suited for a backup script running multiple `SELECT`s?

### Exercise 4. Uncommitted Data

A transaction inserts a row without committing when the snapshot starts. Does that row appear in the snapshot?

### Exercise 5. Snapshots and Writers

Must an MVCC snapshot block all writers throughout a backup? Name one operational cost of long-lived snapshots.

### Exercise 6. `pg_dump`

What scope does `pg_dump` create a consistent snapshot for? Does it automatically create one snapshot across all databases?

### Exercise 7. Parallel Dump

Why must parallel `pg_dump` workers share a snapshot? Which option enables parallel dump and which format is required?

### Exercise 8. Export Snapshot

Write SQL to begin a `REPEATABLE READ READ ONLY` transaction and export its snapshot.

### Exercise 9. Import Snapshot

State the isolation level requirement and when to call `SET TRANSACTION SNAPSHOT` in a consumer transaction.

### Exercise 10. Exporter Lifetime

Why must the exporter transaction stay open when a consumer imports a snapshot? Can a snapshot ID be used after a restart?

### Exercise 11. `pg_dump --snapshot`

What does this option do? When can the exporter session `COMMIT`?

### Exercise 12. Sequences

Why is sequence state not frozen by an MVCC snapshot? Describe how to check post-restore.

### Exercise 13. Globals

Does `pg_dump` of a single database include cluster-wide roles and tablespaces? Which tool dumps globals?

### Exercise 14. Logical vs. Physical

Distinguish logical snapshots from physical backups by copied data and recovery mechanism.

### Exercise 15. Crash Consistency

A storage snapshot of running PostgreSQL resembles a post-crash disk image. What role does WAL play on restore?

### Exercise 16. `pg_backup_start`/`stop`

List the ordered steps for an online filesystem snapshot using the backup API.

### Exercise 17. Backup Label

What roles do `backup_label` and `tablespace_map` play? Why must you never fabricate them by guessing LSNs?

### Exercise 18. Multi-Volume

`PGDATA`, tablespace, and `pg_wal` sit on three volumes. Why is a consistency group or backup protocol coordination required?

### Exercise 19. `pg_basebackup`

Explain the differences between `-X stream`, `-X fetch`, and `-X none`.

### Exercise 20. Verify

What does `pg_verifybackup` check? Why does it not replace restore drills?

### Exercise 21. Cross-Database

How can two `pg_dump`s run at different times yield an inconsistent state? Propose two solutions.

### Exercise 22. Business Workflow

An order and payment are recorded in two separate transactions. What might a snapshot between them see? Is that an MVCC bug?

### Exercise 23. External Objects

A database backup stores an object key, yet the object is overwritten later. Propose how to keep object versions consistent with DB backups.

### Exercise 24. Event Offsets

Why can restoring a database without synchronized Kafka consumer offsets lose or duplicate events?

### Exercise 25. Snapshot Retention

A `pg_dump` holds a snapshot for 4 hours on a write-heavy workload. State the impact on `VACUUM` and how to monitor it.

### Exercise 26. Standby Backup

Why can `pg_dump` on a standby be canceled due to a recovery conflict? What trade-off does `hot_standby_feedback` carry?

### Exercise 27. Unlogged Tables

Is unlogged table data guaranteed like logged tables after crash/standby recovery?

### Exercise 28. RPO/RTO

Do checkpoints determine RPO? Which factors affect RPO and RTO?

### Exercise 29. Consistency Manifest

Propose at least eight metadata fields to store alongside a backup to prove scope and recoverability.

### Exercise 30. Comprehensive Design

A system uses `orders_db`, `billing_db`, Kafka, and object storage. Design a system-wide consistent backup workflow and describe restore/offset reconciliation.

## 29. Suggested Exercise Solutions

### Answer 1. MVCC

A snapshot is transaction visibility information at a logical point in time used to decide which row versions are visible. It is not a physical copy of the entire database.

### Answer 2. `READ COMMITTED`

`READ COMMITTED` takes a fresh snapshot for every statement. Another transaction committing between two `SELECT`s causes the second `SELECT` to see newly committed rows/versions.

### Answer 3. `REPEATABLE READ`

It holds the same snapshot across statements in the transaction, so multiple `SELECT`s exporting data observe the exact same visibility point. This underlies consistent logical dumps.

### Answer 4. Uncommitted Data

No. Snapshots do not treat uncommitted transactions as committed; even if that transaction commits afterward, the older snapshot still excludes that row.

### Answer 5. Writers

No. MVCC allows readers and writers to run concurrently in most scenarios. Long-lived snapshots retain dead tuples, delaying `VACUUM` and raising bloat/disk usage.

### Answer 6. `pg_dump`

`pg_dump` takes a logical snapshot within **one database**. It does not create a single shared exported MVCC snapshot across all databases in a cluster.

### Answer 7. Parallel Dump

If workers used different snapshots, parent/child tables could reflect different timestamps. Use `pg_dump -j N`; parallel dump requires directory format `-Fd`.

### Answer 8. Export Snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot();
```

Keep the exporter transaction open for consumers to import.

### Answer 9. Import Snapshot

Consumers must use `REPEATABLE READ` or `SERIALIZABLE`. Call `SET TRANSACTION SNAPSHOT 'snapshot_id'` before the transaction's first query (aside from allowed transaction-setting commands).

### Answer 10. Exporter Lifetime

Snapshot IDs can only be imported while the exporter transaction is alive. Once the exporter finishes, the identifier cannot be used by new consumers; it is not a durable object and does not survive restarts.

### Answer 11. `pg_dump --snapshot`

Option telling `pg_dump` to adopt a snapshot exported by another session. The exporter can `COMMIT` once `pg_dump` has successfully imported the snapshot and no other consumers remain; in practice, wait until the tool confirms snapshot setup.

### Answer 12. Sequences

`nextval` is non-transactional and never rolls back, so sequences can advance during a dump. Post-restore, compare `last_value`/`is_called` against the table's max key; stop writers and use `setval` to reconcile if needed.

### Answer 13. Globals

No. Single-database `pg_dump` omits cluster-wide roles/tablespaces. Use `pg_dumpall --globals-only` or a dedicated globals workflow.

### Answer 14. Logical vs. Physical

Logical backups read schemas/rows via an MVCC snapshot and rebuild objects on restore. Physical backups copy data files and required WAL; crash recovery replays WAL to bring pages to consistency.

### Answer 15. Crash Consistency

Block-device snapshots can contain pages written at differing moments. WAL supplies redo records to restore consistency, provided the backup includes complete data files/tablespaces and required WAL range.

### Answer 16. Backup API

1. Inventory `PGDATA`/tablespaces/WAL volumes.
2. Call `pg_backup_start`.
3. Snapshot/copy all relevant volumes at a shared consistency point.
4. Call `pg_backup_stop`.
5. Save `backup_label`/`tablespace_map` returned by the API per version.
6. Ensure WAL from start to stop is archived/retained.
7. Write manifest and test restore.

### Answer 17. Backup Label

`backup_label` stores backup start/checkpoint/redo info needed for recovery; `tablespace_map` describes tablespace mappings inside the backup. They must match the exact backup run; guessing LSNs/timestamps causes recovery to read wrong WAL or fail to recognize the backup.

### Answer 18. Multi-Volume

Snapshotting volumes at different times yields incompatible data/tablespace/WAL states. Synchronized consistency groups or backup API coordination with WAL guarantees a recoverable physical backup.

### Answer 19. WAL Methods

- `-X stream`: fetches WAL concurrently with data copy.
- `-X fetch`: fetches WAL after copy; segments must remain available.
- `-X none`: omits WAL from backup; an external archive/retention source must supply required WAL.

### Answer 20. Verify

`pg_verifybackup` validates the backup manifest, file presence/checksums, and supported backup checks. It does not start the server, verify application behavior, external objects, permissions, or RTO; restore drills are required.

### Answer 21. Cross-Database

Dumping orders at time A and billing at time B can capture unsynchronized business states. Solutions: physical cluster backups; or an application barrier/maintenance window pausing related writes before dumping each database and recording a shared epoch.

### Answer 22. Business Workflow

A snapshot between two transactions sees an order in `pending_payment` without a payment. This is MVCC-consistent because the order transaction committed and payment had not; it is not an MVCC bug. If business rules require only terminal states, use a barrier.

### Answer 23. External Objects

Use immutable object keys/version IDs, store version IDs and checksums in the DB, back up bucket/version inventories with retention at least matching DB backups, and never delete objects still referenced by active backups.

### Answer 24. Event Offsets

If the DB snapshot already applied offset N while restored consumer offsets sit at N-1, event N is reprocessed. If consumer offsets sit at N+1 while the DB snapshot lacks N, event N is lost. Commit offsets alongside DB state/inboxes or store coordinated barriers/CDC LSNs.

### Answer 25. Snapshot Retention

A 4-hour snapshot pins an old xmin, blocking `VACUUM` from removing dead tuples, raising bloat and wraparound pressure. Monitor `pg_stat_activity.backend_xmin`, `xact_start`, dead tuples, table sizes, and autovacuum; shorten dump duration/parallelize/adjust backup strategy.

### Answer 26. Standby Backup

WAL replay on the standby may need to clean up row versions still read by the dump query, triggering recovery conflicts and canceling the query. `hot_standby_feedback` asks the primary to retain dead tuples longer, reducing cancellations while increasing primary bloat.

### Answer 27. Unlogged Tables

No. Unlogged tables do not WAL-log data like logged tables; contents are truncated after crash recovery and do not replicate to standbys. Do not store data requiring durable backup/replication in them without a rebuild source.

### Answer 28. RPO/RTO

Checkpoints do not determine RPO. RPO depends on WAL flushes, `synchronous_commit`, replication mode, archive continuity, and external systems. RTO depends on detection, restore/standby promotion, WAL replay, storage, app validation, and opening traffic.

### Answer 29. Consistency Manifest

Examples: `backup_id`, `backup_type`, PostgreSQL version, `system_identifier`, `timeline`, `start_lsn`, `stop_lsn`, `database_list`, `tablespace_map`, storage snapshot IDs, WAL archive range, app epoch, object version manifest, checksum, `retention_until`, `restore_test_id`.

### Answer 30. Comprehensive Design

One approach:

1. Establish an application barrier/epoch; pause or queue relevant new writes.
2. Wait for in-flight order/payment workflows to reach a safe state and record the barrier.
3. Checkpoint Kafka partition offsets matching DB commits; persist offsets/barrier in DB or manifest per protocol.
4. Ensure object storage uses immutable version IDs and take a bucket inventory/checksum at the barrier.
5. Take a physical cluster backup if `orders_db`/`billing_db` share a cluster needing one physical consistency point; if dumping logically separately, hold the barrier across both dumps.
6. Continuously archive WAL and record start/stop LSNs and timeline.
7. Write a manifest linking DB backup ID, app epoch, Kafka offsets, object versions, and checksums.
8. Restore DB into an isolated environment, PITR to target, restore object versions, and restore aligned consumer offsets.
9. Reconcile inbox/outbox/pending transactions to prevent duplicate or lost events.
10. Run business invariants and end-to-end smoke tests before opening traffic.

If writes cannot pause, implement coordinated snapshot/CDC protocols and durable saga state; snapshotting DBs and buckets independently never guarantees system-wide consistency.

## 30. Backup Snapshot Design Checklist

### 30.1. Snapshot Scope

1. Is the snapshot MVCC logical, physical base backup, or storage snapshot?
2. Does the snapshot cover one database, the whole cluster, or multiple systems?
3. Do multiple tables/workers require the exact same snapshot?
4. Is consistency required across multiple databases or services?
5. Do multi-transaction application workflows require a barrier?
6. Are sequence states, Large Objects, unlogged tables, or foreign data accounted for?

### 30.2. MVCC and `pg_dump`

7. Do multi-`SELECT` scripts use `REPEATABLE READ` or a shared snapshot?
8. Does parallel dump use proper snapshot synchronization?
9. Does the exporter transaction stay open just long enough for consumers to import, then close promptly?
10. Is snapshot duration measured and bounded?
11. Are `backend_xmin`/`VACUUM` impacts monitored?
12. Are DDL/migrations coordinated with dumps?
13. Are globals (roles/tablespaces) dumped separately?
14. Are sequence values reconciled after restore?
15. Are Large Objects included and verified?

### 30.3. Physical/Storage Backups

16. Is `pg_basebackup` or the major-appropriate backup API used?
17. Does the backup contain required WAL from start to stop?
18. Are all tablespaces and external volumes inventoried?
19. Do multi-volume storage snapshots use atomic consistency groups?
20. Are `backup_label`/`tablespace_map` preserved properly?
21. Is a separate `pg_wal` coordinated properly?
22. Are config files/certificates/extensions backed up separately?
23. Are backup manifests/checksums verified?

### 30.4. Distributed Systems

24. Does external object storage use versioning/immutable keys?
25. Do Kafka/CDC offsets share a consistency point tied to DB backups?
26. Is there a shared app epoch/barrier?
27. Do backups wait for pending sagas/in-flight workflows?
28. Is 2PC or outbox/saga handled appropriately for external systems?

### 30.5. Restore and Operations

29. Are restore drills run for logical, physical, and PITR?
30. Are tests run using application roles/RLS?
31. Are business invariants, sequences, LOs, and external objects checked?
32. Are RPO/RTO measured from incident to app-ready?
33. Does WAL archive retention cover the base backup window?
34. Are timelines/system identifiers/LSNs checked in manifests?
35. Are alerts configured for stale/failed backups, archive lag, and overdue restore tests?

## 31. Runbook When Snapshots/Backups Are Inconsistent

### Step 1. Identify Backup Type

First determine whether the artifact is a `pg_dump`, `pg_basebackup`, filesystem snapshot, storage snapshot, or multi-system backup set. Each has a different consistency model and recovery path.

### Step 2. Identify Consistency Point

For logical dumps: find the snapshot/transaction boundary and database name.

For physical backups: find backup start/stop LSNs, `backup_label`, timeline, system identifier, and WAL range.

For storage snapshots: find snapshot IDs, consistency group, volume list, and backup API window.

For distributed backups: find application epoch, Kafka offsets, CDC LSNs, and object versions.

### Step 3. Check Completeness

Check database lists, tablespaces, WAL, roles/globals, LOs, configs/extensions, external objects, and event offsets. Never infer completeness simply from a dump file existing.

### Step 4. Investigate Long Snapshot Issues

If `pg_dump` runs too long or vacuum is blocked, inspect `pg_stat_activity.backend_xmin`, transaction age, autovacuum, and table bloat. Stop backup transactions strictly per runbook after checking consumer/exporter progress.

### Step 5. Verify Artifacts

Run `pg_verifybackup` when applicable, `pg_restore --list` for custom archives, and check checksums/manifests and file lists. Note explicitly that this is artifact verification, not restore validation.

### Step 6. Restore into an Isolated Environment

Never overwrite production to test. Restore with matching PostgreSQL major version, tablespace maps, WAL chains, and dependencies. Confirm server startup and recovery completion.

### Step 7. Check Business Consistency

Run invariants: orphan rows, totals, sequence values, attachment checksums, object versions, consumer offsets, and saga states. Test using application roles.

### Step 8. Decide on Opening Traffic

Open traffic only after confirming the consistency point, RPO, data integrity, authorization, external dependencies, and smoke tests. If data is missing, keep the restored cluster isolated and plan reconciliation.

### Step 9. Fix Root Cause

Examples:

- Multi-statement `READ COMMITTED` → use a transaction snapshot.
- Cross-database dumps → add barriers or physical cluster backups.
- Missing WAL → fix archive retention/backup procedures.
- Missing tablespaces → update volume inventory/consistency groups.
- Missing external objects → enable object versioning/manifests/aligned retention.
- Sequence collisions → post-restore reconciliation.
- Long snapshots → optimize duration and backup concurrency.

### Step 10. Update Manifests and Re-Drill

Record root cause, consistency point, artifact IDs, restore duration, and corrective actions. Re-run drills to verify the fix holds.

## 32. Summary

**A snapshot defines the data state visible at a consistency point; a backup is an artifact that must hold every component needed to reconstruct that state.** PostgreSQL MVCC lets logical readers view consistent row versions, whereas physical backups rely on WAL recovery to bring data files to consistency.

Core takeaways:

- `READ COMMITTED` takes a fresh snapshot per statement; `REPEATABLE READ` holds one consistent snapshot within the transaction.
- `pg_dump` uses a snapshot for one database; parallel workers must share a snapshot to avoid mixing states across tables.
- `pg_export_snapshot`/`SET TRANSACTION SNAPSHOT` coordinates connections within one database; the exporter must stay open while consumers import.
- Long-lived snapshots retain dead tuples and can cause bloat/`VACUUM` pressure.
- Sequence values do not obey MVCC snapshots like table rows; check/reconcile after restore.
- Single-database `pg_dump` omits roles/global objects and provides no consistency point across multiple databases.
- Physical backups require data files, tablespaces, backup metadata, and continuous WAL; `pg_basebackup`/backup API handle the protocol.
- Multi-volume storage snapshots require consistency groups or backup API coordination.
- Crash consistency, database MVCC consistency, and business/distributed consistency are distinct layers.
- DB snapshots do not capture object storage, Kafka offsets, filesystems, or external services.
- Checkpoints are not backups; PITR needs base backups and continuous WAL archives.
- Backup manifests should record system identifiers, timelines, LSNs, databases, tablespaces, snapshot IDs, app epochs, and external versions.
- A backup is trustworthy only after restoring/testing with the application and measuring RTO/RPO.

Practical rule:

> **Choose the right consistency point for the backup type, coordinate all components within your data boundary, and prove recoverability through restore drills.**

## 33. References

Official PostgreSQL documentation; select the exact major version you operate:

- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`, and MVCC snapshots.
- [Snapshot Synchronization Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION): `pg_export_snapshot` and snapshot importing.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical dumps, snapshots, parallel jobs, globals, and large objects.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html): dumping multiple databases and global objects.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archives, and PITR.
- [Backup Control Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-BACKUP): `pg_backup_start` and `pg_backup_stop`.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): creating physical base backups, WAL methods, and tablespaces.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): verifying backup manifests/checksums.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html): data locations and tablespace management.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `backend_xmin`, and statistics views.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): MVCC dead tuples, `VACUUM`, and transaction horizons.
- [Sequence Manipulation Functions](https://www.postgresql.org/docs/current/functions-sequence.html): `nextval`/`setval` and sequence semantics.
- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): standby recovery, hot standby conflicts, and feedback.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publication/subscription, initial copy, and replication behavior.





