# Walwriter, Disk Writes, and Commit Confirmation Timing in PostgreSQL

PostgreSQL uses **Write-Ahead Logging (WAL)** to protect data when the system fails. When a transaction modifies data, PostgreSQL writes descriptions of the changes to WAL before the corresponding data pages are written to the main table files.

This raises an important question: **When an application calls COMMIT and receives a success response, is the data truly safe on storage?**

The answer depends on how PostgreSQL writes and flushes WAL, the `synchronous_commit` configuration, the replication sync mode, and the honesty of the filesystem/storage layer.

Components to distinguish:

- **WAL buffers**: shared memory area holding WAL records before they are written to WAL files.
- **Backend process**: the process serving a connection, which can write/flush WAL itself when needed.
- **Walwriter**: background process that writes WAL buffers out to WAL segment files on a schedule and threshold.
- **Operating system cache**: data written to the kernel/filesystem that is not necessarily durable across a power loss.
- **fsync/fdatasync**: asks the operating system to synchronize data to the storage device per platform semantics.
- **COMMIT record**: WAL record marking transaction commit.
- **Checkpoint**: process of writing dirty data pages and establishing a recovery point; not synonymous with commit confirmation.

The lesson **“Walwriter, Disk Writes, and Commit Confirmation Timing”**, part of the **WAL and checkpoints** chapter in the **Database Engine Relational PostgreSQL** module, explains WAL insert/write/flush, the role of walwriter, synchronous_commit, group commit, checkpoints, synchronous replication, and how to observe related metrics.

> **Key takeaway:** PostgreSQL can confirm a transaction commit before data pages are written back to heap files because WAL enables crash recovery. However, under standard synchronous commit settings, the WAL containing the commit record must be flushed as required before the server returns success to the client. "Written" and "durably flushed" are two different states.

---

## 1. Why Does PostgreSQL Need WAL?

If every UPDATE had to immediately write all changes to their exact positions in heap, index, and other structures, one transaction would require many random I/O operations. Crashing mid-way could also leave data in an inconsistent state.

WAL changes the approach:

1. PostgreSQL generates WAL records describing the changes.
2. The records are placed into WAL buffers in shared memory.
3. WAL is written out to WAL segment files.
4. When durability is required, WAL is flushed to storage via a synchronous mechanism.
5. Data pages can be written later; on crash, PostgreSQL redoes WAL to recover.

~~~text
Transaction
    |
    v
Modify page in shared buffers
    |
    v
Create WAL records in WAL buffers
    |
    v
Write WAL to pg_wal
    |
    v
Flush WAL per durability policy
    |
    v
COMMIT confirmed
    |
    v
Data pages written via checkpoint/background write
~~~

WAL lets the database write sequentially to a log and recover committed changes that have not yet been completely written to data files.

## 2. The Write-Ahead Rule

The **write-ahead** rule requires that WAL records describing a change be durably written before the data page containing that change is durably written to storage.

~~~text
WAL record: page 42 modified
        |
        v
WAL must be durable first
        |
        v
Data page 42 is then allowed to be durably written
~~~

If a data page is written before its required WAL, a crash can leave PostgreSQL without enough information to recover that page.

## 3. Where Do WAL Buffers Live?

PostgreSQL has a shared memory area called **WAL buffers**, configured via `wal_buffers`.

~~~sql
SHOW wal_buffers;
~~~

WAL records are generated while a transaction runs and placed into WAL buffers. They are not necessarily written to WAL files at the exact moment an SQL statement ends.

When buffers need to be freed, a backend or the walwriter can perform the write to segment files.

### 3.1. WAL Buffers Are Not Data Buffers

| Buffer area | What it holds | Written to |
|---|---|---|
| Shared buffers | Heap/index data pages | Table/index relation files |
| WAL buffers | WAL records | WAL segment files in pg_wal |

A page in shared buffers and a WAL record describing a change to that page are two different kinds of data.

## 4. WAL Segment Files

WAL is stored in segment files inside the `pg_wal` directory of the data directory.

Filenames typically follow a hexadecimal format, for example:

~~~text
00000001000000000000000A
00000001000000000000000B
~~~

The default segment size is commonly **16 MB**, though it can be chosen at initdb with the appropriate option. Do not hardcode this size in monitoring tools.

WAL segments can be created, appended to, flushed, switched to the next segment, archived, recycled, or deleted when no longer needed per retention/replication rules.

## 5. Three WAL Positions: Insert, Write, and Flush

PostgreSQL tracks multiple LSN (Log Sequence Number) positions:

- **Insert LSN**: the latest WAL position generated/inserted into WAL buffers.
- **Write LSN**: the WAL position written out to WAL files via write operations.
- **Flush LSN**: the WAL position flushed via the durability mechanism.

Typical ordering:

~~~text
Insert LSN >= Write LSN >= Flush LSN
~~~

The positions can be equal when no WAL is waiting to be written or flushed.

### 5.1. Insert Does Not Mean Write

A WAL record created in shared memory has not necessarily been written out to pg_wal.

### 5.2. Write Does Not Mean Flush

A write operation may simply place bytes into the OS page cache. The data can still reside in kernel-managed cache and not yet be confirmed durable on storage.

### 5.3. Flush Is the Key Milestone for Durability

Flush asks the operating system to synchronize WAL data via fsync/fdatasync or the corresponding method. With `fsync=on` and storage honoring the semantics, this is the milestone PostgreSQL relies on to confirm WAL durability.

## 6. Observing Current LSNs

Useful functions:

~~~sql
SELECT
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_lsn() AS write_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
~~~

- `pg_current_wal_insert_lsn()` returns the current insert position.
- `pg_current_wal_lsn()` returns the current write position.
- `pg_current_wal_flush_lsn()` returns the current flush position.

These functions show WAL progress at query time. They are not a per-transaction commit history.

### 6.1. Older Versions

In older PostgreSQL versions, function names used the `pg_current_xlog_*` prefix. WAL replaced XLOG in newer versions. Use the functions matching your actual server version.

## 7. Calculating LSN Distance

~~~sql
SELECT pg_wal_lsn_diff(
    pg_current_wal_insert_lsn(),
    pg_current_wal_flush_lsn()
) AS unflushed_wal_bytes;
~~~

`pg_wal_lsn_diff` returns the byte distance between two LSNs.

This is a snapshot at query time. The value can change rapidly while a workload is writing WAL. Do not use a single sample to draw conclusions about commit latency.

## 8. What Is Walwriter?

**Walwriter** is a PostgreSQL background process dedicated to writing WAL buffers out to WAL files according to a configured schedule and threshold.

Goals:

- Reduce how often backends must write WAL buffers themselves.
- Write WAL periodically even when no transaction commits at that exact moment.
- Smooth out burst I/O and assist group commit.
- Keep WAL advancing steadily under load.

Walwriter does not completely replace backend WAL writes/flushes. When a backend needs durable WAL for COMMIT and WAL has not yet been flushed to the required position, the backend can write/flush it directly or wait on the appropriate sync mechanism.

### 8.1. Walwriter Does Not Write Heap Data Pages

Walwriter works exclusively with **WAL**. Table and index data pages are written by other mechanisms such as the background writer, checkpointer, and backend processes.

Do not confuse walwriter with the background writer.

## 9. Walwriter and Backends Both Participate in Writing WAL

~~~text
                 WAL buffers
                      |
            +---------+---------+
            |                   |
            v                   v
        Walwriter           Backend
       writes WAL          commit needs WAL
            |                   |
            +---------+---------+
                      |
                      v
                 WAL files
                      |
                      v
                 Flush/sync
~~~

Walwriter may have already written/flushed the required WAL before the backend commits. In that case, the backend avoids repeating all the I/O.

If not, the backend can write/flush up to the position its commit must guarantee.

## 10. wal_writer_delay

`wal_writer_delay` specifies how long walwriter waits between rounds of processing WAL buffers.

~~~sql
SHOW wal_writer_delay;
~~~

The default is commonly **200 ms** in standard PostgreSQL configurations.

A smaller value wakes walwriter up more frequently; a larger value lets WAL buffers wait longer before being written by a walwriter cycle.

Do not tune this parameter merely hoping for "faster commits." Synchronous commits can trigger a backend flush directly when needed.

## 11. wal_writer_flush_after

`wal_writer_flush_after` specifies the volume of WAL written by walwriter after which it triggers a threshold flush.

~~~sql
SHOW wal_writer_flush_after;
~~~

The default is commonly around **1 MB** in standard PostgreSQL versions/configurations. A value of `0` can disable the byte-threshold flush for walwriter.

This parameter helps control background WAL flushing. It does not change the durability semantics required by `synchronous_commit` for a transaction.

| Parameter | Controls |
|---|---|
| `wal_writer_delay` | Time between walwriter cycles |
| `wal_writer_flush_after` | WAL bytes written before walwriter flushes by threshold |

## 12. Writing to OS Cache Differs from Durable Storage

~~~text
PostgreSQL
    |
    | write()
    v
Kernel / filesystem cache
    |
    | fsync() or fdatasync()
    v
Storage device / controller
~~~

After a write, the operating system may hold data in the page cache. That does not prove the data survives power loss.

`fsync`/`fdatasync` requests synchronizing data and necessary metadata according to platform/filesystem semantics.

### 12.1. Storage Hardware Must Honor Flush Semantics

PostgreSQL can issue fsync, but if a storage controller, hypervisor, or device lies about flush completion, actual durability may fall short of expectations.

Production operations require storage with battery/capacitor-backed write cache (power-loss protection) and honest flush semantics.

## 13. fsync

~~~sql
SHOW fsync;
~~~

`fsync=on` is the recommended setting for any system requiring durability. PostgreSQL asks the operating system to sync critical changes to storage.

Disabling fsync can boost benchmark numbers, but an OS crash or power loss can cause **corruption or loss of consistency**, not just losing a few recent transactions.

Never disable fsync in production to optimize commit latency.

### 13.1. synchronous_commit Differs from fsync

| Setting | Role |
|---|---|
| `fsync` | Whether to request syncing data to storage per durability protocol |
| `synchronous_commit` | How far transaction commit waits for WAL flush / replication acknowledgement |

`synchronous_commit=off` can still be used alongside `fsync=on`; it changes when the server confirms commit, without turning off the entire fsync mechanism.

## 14. wal_sync_method

~~~sql
SHOW wal_sync_method;
~~~

This parameter chooses the method PostgreSQL uses to sync WAL on the current platform—for example, variants based on `fdatasync`, `fsync`, open_sync, or an OS-specific equivalent.

Supported values depend on platform and build. Never copy a value from Linux to Windows or vice versa without checking server support.

The `pg_test_fsync` utility can evaluate sync method performance on test storage. Never run ad-hoc I/O benchmarks against a production data directory.

## 15. COMMIT Record in WAL

When a transaction commits, PostgreSQL creates a WAL record marking the transaction as committed.

A single transaction may generate many WAL records for INSERT/UPDATE/index changes. The commit record is the marker of transaction completion in WAL.

~~~text
WAL records for changes
        |
        v
COMMIT record
        |
        v
Flush per synchronous_commit policy
        |
        v
Server returns COMMIT success
~~~

If a crash occurs after the commit record is durable but before data pages are written to the heap, recovery uses WAL to redo the committed changes.

## 16. When Does PostgreSQL Confirm COMMIT?

With the common configuration `synchronous_commit=on` and `fsync=on`:

1. PostgreSQL ensures the WAL containing the commit record has been written and flushed to storage per the durability protocol.
2. Once the required flush completes, the backend can return COMMIT success.
3. The corresponding data pages do not need to have been written to table files yet.
4. On crash, crash recovery relies on WAL.

Thus **commit durability relies on WAL**, not on waiting for a checkpoint to write all data pages.

### 16.1. Client Receiving Success Is a Clear Milestone, but Network Errors Can Create Ambiguity

If the server finishes committing and the connection drops before the response reaches the client, the application cannot tell whether the transaction committed. Non-idempotent retries can cause duplicate side effects.

Application design requires idempotency keys or a mechanism to query outcomes by business ID.

## 17. synchronous_commit

`synchronous_commit` controls how far a transaction commit waits.

~~~sql
SHOW synchronous_commit;
~~~

| Value | Local wait | Synchronous standby wait |
|---|---|---|
| `off` | Does not wait for local WAL flush before reporting success | No |
| `local` | Waits for local WAL flush | Does not wait for remote acknowledgement |
| `remote_write` | Waits for local flush | Waits for standby to write WAL to OS, not necessarily durable flush |
| `on` | Waits for local flush | If synchronous standby is configured, waits for remote flush |
| `remote_apply` | Waits for local flush | Waits for standby to apply/replay the transaction |

Remote mode details apply only when synchronous replication is configured with an eligible standby.

## 18. synchronous_commit=on

This is the standard and default choice in PostgreSQL.

~~~sql
SET synchronous_commit = on;
~~~

- Waits for local WAL flush per durability protocol.
- If a synchronous standby is configured, commit also waits for remote flush per `on` semantics.
- Does not wait for a checkpoint or for all table/index pages.

Actual protection depends on `fsync`, the filesystem, kernel, storage hardware, and replication setup.

## 19. synchronous_commit=off

~~~sql
SET synchronous_commit = off;
~~~

A transaction can be reported successful **before its WAL records are durably flushed**.

If the database or OS crashes immediately after the response, some recently acknowledged transactions may be lost during recovery.

Important points:

- The database still maintains internal consistency through WAL recovery design.
- This does not mean `fsync=off`.
- The primary risk is losing recently confirmed transactions, not allowing the database to write heap pages before WAL.
- Walwriter/background flushes still write WAL afterwards.

Consider this only for workloads that can tolerate losing a small window of recent transactions on crash and can regenerate them. Do not use it for ledgers, payments, or order confirmations where the application promises immediate durability upon returning success.

## 20. local, remote_write, and remote_apply

When synchronous replication is active:

- `local`: waits for local WAL flush, skipping waits on synchronous standbys.
- `remote_write`: waits for the standby to write WAL to its OS, without guaranteeing the standby flushed durably.
- `on`: waits for the standby to flush WAL per synchronous replication requirements.
- `remote_apply`: waits for the standby to replay/apply the transaction so queries on the standby can see the changes.

### 20.1. remote_write Is Not the Same as Remote Flush

A standby write to the OS cache may not survive a power loss on the standby. If you require a remotely flushed copy, use appropriate semantics such as `on`.

### 20.2. remote_apply Can Increase Latency

The standby must receive, flush, and replay WAL. This increases commit duration, though it can be useful for read-after-commit requirements on standbys.

## 21. synchronous_standby_names

For synchronous replication to take effect, the primary must configure which standbys count as synchronous.

~~~sql
SHOW synchronous_standby_names;
~~~

The configuration determines which standbys participate in acknowledgements, optionally using quorum or priority policies per PostgreSQL syntax.

If no synchronous standby is configured, remote levels of synchronous_commit do not conjure a standby to wait for.

Observe:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

A streaming standby is not necessarily selected as a synchronous standby for commits.

## 22. Group Commit

When multiple transactions commit closely in time, PostgreSQL can perform **group commit**: a single WAL flush can satisfy the durability requirement for multiple transactions.

~~~text
Transaction A -- COMMIT --+
Transaction B -- COMMIT --+--> WAL flush
Transaction C -- COMMIT --+       |
Transaction D -- COMMIT --+       v
                           Multiple commits confirmed
~~~

Group commit increases throughput without needing a separate fsync for each transaction.

Walwriter can write WAL buffers on schedule, saving backends from doing every write. Yet synchronous commit must still ensure WAL is flushed through the required commit position before returning success.

## 23. commit_delay and commit_siblings

~~~sql
SHOW commit_delay;
SHOW commit_siblings;
~~~

- `commit_delay`: microseconds a backend may wait before flushing WAL to create an opportunity to group more commits.
- `commit_siblings`: minimum number of concurrent open transactions required before applying commit_delay.

The default `commit_delay` is typically 0, meaning no intentional delay.

Adding a delay can raise individual transaction latency while increasing throughput in workloads with many concurrent commits. Benchmark against real traffic.

## 24. Checkpoint Differs from COMMIT

This is a very common source of confusion.

**COMMIT** confirms that a transaction is complete per the WAL durability policy.

**CHECKPOINT** writes dirty data pages and updates checkpoint information to bound the amount of WAL that must be replayed after a crash.

~~~text
COMMIT:
WAL commit record --> flush --> return success

CHECKPOINT:
WAL already durable --> write dirty data pages
                    --> checkpoint record/state
~~~

A transaction may have committed durably long ago while its data page has still not been written by the next checkpoint.

### 24.1. Commits Do Not Wait for Checkpoints

PostgreSQL does not need to flush all of a transaction's table/index pages at COMMIT. WAL allows recovering those changes after a crash.

## 25. The Write-Ahead Rule and Checkpoints

When the checkpointer writes a dirty page to a data file, the WAL associated with that page must have been flushed at least up to the required LSN.

~~~text
WAL durable through page LSN
          |
          v
Data page permitted to be written to relation file
~~~

This protects crash recovery if a page write is torn or a crash interrupts operations.

## 26. full_page_writes

~~~sql
SHOW full_page_writes;
~~~

`full_page_writes` is typically enabled. After a checkpoint, the first modification to a page can emit a full-page image in WAL so recovery can repair torn pages per PostgreSQL mechanics.

It can increase WAL volume, especially right after a checkpoint or in workloads updating many pages.

Never disable full_page_writes merely to cut WAL volume without understanding torn-page corruption risks and storage guarantees.

## 27. Checkpoint Frequency and WAL Volume

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
~~~

- `checkpoint_timeout`: maximum time interval between scheduled checkpoints.
- `max_wal_size`: WAL threshold that triggers earlier checkpoints; not an absolute hard cap for pg_wal.
- `checkpoint_completion_target`: target fraction for spreading checkpoint writes across the checkpoint interval.

Too-frequent checkpoints can increase I/O and full-page images. Too-infrequent checkpoints can increase recovery time and WAL retention.

Do not raise checkpoint_timeout expecting synchronous COMMITs to avoid flushing. Commit durability and checkpoints are two separate mechanisms.

## 28. Background Writer Differs from Walwriter

| Process | Primary Responsibility |
|---|---|
| `walwriter` | Writes WAL buffers to WAL files |
| `background writer` | Writes dirty data buffers in the background |
| `checkpointer` | Executes checkpoints, writes dirty pages |
| `backend` | Handles queries/transactions, can write data/WAL when needed |

These processes can all generate I/O concurrently, yet they operate on different memory areas and serve different goals.

## 29. wal_buffers and Commit Latency

~~~sql
SHOW wal_buffers;
~~~

Too-small WAL buffers can force backends to write WAL themselves more frequently in some workloads. However, increasing wal_buffers does not by itself reduce storage fsync latency.

Tuning requires separating WAL generation rate, buffer pressure, write throughput, flush/fsync latency, synchronous replication wait, and CPU overhead.

Do not raise shared memory settings based on a single commit latency metric.

## 30. Observing WAL Statistics

The `pg_stat_wal` view provides aggregate WAL statistics on supported versions:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time,
    stats_reset
FROM pg_stat_wal;
~~~

Common columns:

- `wal_records`: count of WAL records generated.
- `wal_fpi`: count of full-page images.
- `wal_bytes`: total WAL bytes generated.
- `wal_buffers_full`: times WAL buffers filled up and required handling.
- `wal_write`: number of write operations.
- `wal_sync`: number of sync operations.
- `wal_write_time` and `wal_sync_time`: write/sync time if corresponding tracking is enabled.
- `stats_reset`: timestamp when statistics were reset.

Exact names and columns can vary by PostgreSQL version; inspect the view schema on your actual server.

## 31. track_wal_io_timing

~~~sql
SHOW track_wal_io_timing;
~~~

When enabled, PostgreSQL collects timing for the corresponding WAL I/O operations, helping distinguish write time from sync time.

Timing metrics carry a small overhead that should still be weighed on very latency-sensitive workloads.

Do not conclude fsync is slow solely from the wal_sync count; examine total time, operation count, workload, and storage telemetry.

## 32. pg_stat_activity and WAL Wait Events

When commits are slow, inspect:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE wait_event IS NOT NULL
ORDER BY query_start;
~~~

Some wait events relate to WAL, such as waiting on WAL write/sync depending on version.

Wait event names and taxonomy can vary by version. Use `pg_wait_events` if available, or consult the reference for your server version.

Not every slow commit is caused by fsync. Other causes include lock waits, synchronous standby lag, storage queue congestion, CPU scheduling, network latency, and high WAL volume.

## 33. Observing Synchronous Replication Lag

On the primary:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

- `write_lsn`: position written by standby.
- `flush_lsn`: position flushed by standby.
- `replay_lsn`: position replayed/applied by standby.
- Lag fields reflect recent timing statistics and may be NULL when no suitable samples exist.

If `synchronous_commit=on` and the standby is synchronous but slow to flush, COMMITs can stall waiting for remote flush.

## 34. Lab: Two Sessions Checking Commit and WAL LSN

Open two psql sessions in a **lab database**.

Create the table once:

~~~sql
CREATE TABLE wal_lab (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

**Session A:**

~~~sql
SHOW synchronous_commit;

SELECT
    pg_current_wal_insert_lsn(),
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();
~~~

**Session B:**

~~~sql
BEGIN;

INSERT INTO wal_lab(value)
VALUES ('transaction one');

COMMIT;
~~~

After COMMIT returns, rerun the LSN queries in Session A.

Under concurrent workloads, insert/write/flush positions can advance past the transaction being tested. LSN is a system-wide WAL position, not a label tied to the newly inserted row.

## 35. Lab: Comparing synchronous_commit=on and off

In lab Session B:

~~~sql
BEGIN;

SET LOCAL synchronous_commit = on;

INSERT INTO wal_lab(value)
VALUES ('durability setting on');

COMMIT;
~~~

Try another transaction:

~~~sql
BEGIN;

SET LOCAL synchronous_commit = off;

INSERT INTO wal_lab(value)
VALUES ('durability setting off');

COMMIT;
~~~

`SET LOCAL` applies only within the current transaction.

Without a crash, both rows will appear. The difference is **when the server confirms COMMIT relative to when WAL becomes durable**, not that a row is guaranteed to vanish when using off.

Never simulate a crash by killing a production host or database. Durability testing requires an isolated environment and dedicated procedure.

## 36. Lab: Observing Background Processes

~~~sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    backend_start
FROM pg_stat_activity
WHERE backend_type IN (
    'walwriter',
    'background writer',
    'checkpointer'
)
ORDER BY backend_type;
~~~

View availability and backend_type values vary by version; on supported versions you can observe the corresponding process names.

These processes are managed by PostgreSQL. Never send SQL COMMIT/ROLLBACK or arbitrarily terminate them like application sessions.

## 37. Java JDBC and Commit Return Timing

In JDBC:

~~~java
connection.setAutoCommit(false);

try {
    // INSERT/UPDATE statements
    connection.commit();
} catch (Exception e) {
    connection.rollback();
    throw e;
}
~~~

When `commit()` returns normally, the server has confirmed the transaction according to the active durability settings, such as `synchronous_commit`.

JDBC itself does not know how far WAL was flushed locally or remotely; the semantics come from PostgreSQL's configuration.

### 37.1. Commit Response Lost on the Network

If the server commits successfully but the socket drops before the client receives the response, the application sees an exception and does not know whether the transaction committed.

Never retry a non-idempotent operation merely because the client saw no response. Use a business request ID, unique constraint, or idempotency key to determine the outcome.

## 38. SET LOCAL and SET SESSION synchronous_commit

You can set it per session:

~~~sql
SET synchronous_commit = off;
~~~

Or inside a transaction:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = off;
-- statements
COMMIT;
~~~

It can also be configured per role or database via ALTER ROLE/ALTER DATABASE when reviewed and justified.

Never set off globally just to reduce latency for a single batch job.

## 39. COMMIT AND CHAIN

PostgreSQL supports:

~~~sql
COMMIT AND CHAIN;
~~~

This commits the current transaction and immediately starts a new one with matching transaction characteristics. It does not change the durability semantics of the commit that just finished.

Similarly, `ROLLBACK AND CHAIN` starts a new transaction after a rollback.

## 40. Asynchronous Commit and Consistency

`synchronous_commit=off` can lose the most recent transactions reported as successful if a crash happens before WAL is flushed, yet PostgreSQL preserves internal consistency via WAL recovery. There can be a window of lost data after the application received success.

A system must not promise "permanently saved" if transactions commit in asynchronous mode.

### 40.1. Sequences and Side Effects

Even when the database recovers consistency, external side effects (emails, payment gateways, message publishing) do not automatically roll back with WAL. Use a transactional outbox and idempotency for such integrations.

## 41. Tuning WAL Writer and Commit Latency

Before changing parameters, classify the bottleneck:

| Symptom | What to Inspect |
|---|---|
| wal_buffers_full rising fast | WAL buffer pressure/generation |
| High wal_write_time | Write path/storage throughput |
| High wal_sync_time | Flush/fsync latency |
| High pg_stat_replication flush_lag | Synchronous standby/storage/network |
| High WAL bytes | Write workload, full-page images, bulk updates |
| Slow commits with low WAL sync | Locks, CPU, app/network, remote wait |
| Checkpoint writes causing I/O bursts | Checkpoint cadence/completion target/storage |

Increasing wal_writer_delay will not fix slow storage fsync or standby lag.

## 42. Checkpoint Statistics Across Versions

Across different PostgreSQL versions, checkpoint statistics are organized in different views.

PostgreSQL 17+ provides `pg_stat_checkpointer` for checkpoint counts, timings, and buffers; older versions placed part of this information in `pg_stat_bgwriter`.

Example on a server with the matching view:

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

On older versions, check:

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

Do not run queries hardcoding newer version columns against older servers. Use `\d+ pg_stat_checkpointer` or `\d+ pg_stat_bgwriter` in psql to inspect the actual schema.

## 43. WAL Archive and Commit Durability

`archive_mode` and `archive_command` archive WAL segments for PITR and backups.

Archive success is not a prerequisite for each local transaction COMMIT to be confirmed in normal setups.

Distinguish:

- Local WAL flush: transaction durability on the primary per fsync policy.
- Synchronous replication acknowledgement: remote standby acknowledgement per sync mode.
- WAL archive: storing segments for point-in-time recovery.

A committed transaction is archived afterward when its segment completes or switches per workflow.

## 44. WAL Switch and Segment Recycling

~~~sql
SELECT pg_switch_wal();
~~~

This function requests switching to a new WAL segment under appropriate conditions. It can be helpful in archiving or testing workflows, but it is not a per-transaction flush command.

Do not call it repeatedly to "make COMMITs faster"; overly frequent switches create underfilled segments and increase archive and management overhead.

## 45. synchronous_commit and Logical Replication

`synchronous_commit` local/remote semantics do not automatically mean a logical subscriber has applied all changes. Logical replication has its own slots, consumer progress, and mechanisms.

If a logical subscriber must apply before the primary returns success, design synchronous replication matching your topology and version and verify support; do not infer it merely from having a logical slot.

## 46. Durability and Backups

WAL flush keeps transactions durable on the primary per storage contract, but does not replace backups.

Backups and PITR protect against accidental deletion, application bugs writing bad data, storage failures beyond redundancy, loss of an entire cluster or site, and administrative mistakes.

A durably committed transaction can still be a wrong business transaction. You still need backups, WAL archives, restore tests, and disaster recovery.

## 47. Common Misconceptions

### 47.1. Walwriter Writes Data Pages

False. Walwriter writes WAL buffers; checkpointer and background writer handle data buffers.

### 47.2. write() Means Durable

False. Write may only place data into the OS cache; flush/fsync and storage semantics determine durability.

### 47.3. COMMIT Must Wait for a Checkpoint

False. Commits wait for WAL durability per policy, not for all data pages to be checkpointed.

### 47.4. synchronous_commit=off Means fsync=off

False. These are two different settings. Off can confirm before local WAL flush; fsync off disables sync durability requirements and is far more dangerous.

### 47.5. Walwriter Always Flushes Before Every COMMIT

False. Backends can write/flush directly when a commit requires it, and walwriter runs on its own schedule.

### 47.6. Raising wal_writer_delay Always Increases Throughput

Not guaranteed. It can increase how long WAL waits; synchronous commit backends may still have to flush themselves.

### 47.7. remote_write Equals Remote Durable

False. The standby has written to its OS, not necessarily flushed durably.

### 47.8. remote_apply Only Waits for Write

False. It waits for the standby to replay/apply the transaction.

### 47.9. Checkpoint and Commit Are the Same Milestone

False. Commit marks a transaction; checkpoint flushes dirty data pages and creates a recovery point.

### 47.10. max_wal_size Is a Hard Cap for pg_wal

False. It is a checkpoint target threshold, not an absolute cap on all WAL retention.

### 47.11. WAL Archiving Must Finish Before COMMIT

Not in normal configurations. Archiving is a separate workflow.

### 47.12. If JDBC Commit Throws an Exception, the Transaction Definitely Rolled Back

False. The response may have been lost after the server committed; the outcome can be ambiguous.

## 48. Checklist for Diagnosing Slow COMMITs

1. Identify synchronous_commit for the session/transaction.
2. Check fsync and wal_sync_method.
3. Inspect pg_stat_wal write/sync counts and timings.
4. Enable/check track_wal_io_timing if appropriate.
5. Check WALWrite/WALSync wait events per version.
6. Inspect pg_stat_replication if synchronous standbys are configured.
7. Check lock waits and query duration.
8. Measure WAL bytes/transaction and full-page images.
9. Check storage latency, queue depth, and power-loss protection.
10. Compare walwriter activity and WAL buffer pressure.
11. Inspect checkpoint statistics separately—do not conflate them with commit.
12. Benchmark concurrency and group commit using realistic workloads.
13. Never disable fsync or full_page_writes to hide a bottleneck.
14. If responses are lost, use idempotency to resolve commit ambiguity.

## 49. Practice Exercises

### Exercise 1 — WAL

Why does PostgreSQL use WAL?

**Hint:** write-ahead and crash recovery.

### Exercise 2 — WAL Buffers

Where are WAL records initially created?

**Hint:** WAL buffers in shared memory.

### Exercise 3 — Data Buffers

Distinguish between shared buffers and WAL buffers.

**Hint:** data pages vs. log records.

### Exercise 4 — Insert LSN

What does `pg_current_wal_insert_lsn` represent?

**Hint:** WAL position inserted into buffers.

### Exercise 5 — Write LSN

What does `pg_current_wal_lsn` represent?

**Hint:** WAL position written.

### Exercise 6 — Flush LSN

What does `pg_current_wal_flush_lsn` represent?

**Hint:** WAL position flushed.

### Exercise 7 — Write vs. Flush

Why is writing to the OS cache not enough to conclude data is durable?

**Hint:** fsync/fdatasync semantics are required.

### Exercise 8 — Walwriter

What is walwriter's job?

**Hint:** writing WAL buffers to WAL files.

### Exercise 9 — Backend Flush

Why can a backend flush WAL itself?

**Hint:** synchronous commit needs WAL durable through the commit record.

### Exercise 10 — wal_writer_delay

What does this parameter control?

**Hint:** time between walwriter cycles.

### Exercise 11 — wal_writer_flush_after

What does this parameter control?

**Hint:** byte threshold before walwriter flushes.

### Exercise 12 — fsync

Why does production typically keep fsync enabled?

**Hint:** durability across OS crash/power loss per storage contract.

### Exercise 13 — synchronous_commit

What does it control?

**Hint:** how far commit waits for WAL flush / remote acknowledgement.

### Exercise 14 — off

What risk does synchronous_commit=off carry?

**Hint:** losing a few recent transactions already reported successful on crash.

### Exercise 15 — fsync vs. synchronous_commit

Distinguish between the two settings.

**Hint:** storage sync mechanism vs. commit wait policy.

### Exercise 16 — remote_write

The standby has written, yet what is not guaranteed?

**Hint:** durable flush is not guaranteed.

### Exercise 17 — remote_apply

How does it differ from on?

**Hint:** waits for standby replay/apply.

### Exercise 18 — local

Does local wait for a synchronous standby?

**Hint:** no, though it waits for local flush.

### Exercise 19 — synchronous_standby_names

What is the role of this setting?

**Hint:** selecting synchronous standbys.

### Exercise 20 — Group Commit

How does group commit help?

**Hint:** a single WAL flush satisfies multiple transactions.

### Exercise 21 — commit_delay

When can it increase throughput?

**Hint:** when enough concurrent commits exist to group.

### Exercise 22 — commit_siblings

Which condition does it control?

**Hint:** minimum open transactions required for commit_delay.

### Exercise 23 — Checkpoint

What does a checkpoint do?

**Hint:** flushes dirty data pages and creates a recovery point.

### Exercise 24 — Commit vs. Checkpoint

Why does commit not wait for a checkpoint?

**Hint:** WAL is sufficient to redo after a crash.

### Exercise 25 — full_page_writes

What issue does it protect against?

**Hint:** torn pages after a checkpoint.

### Exercise 26 — Background Writer

How does it differ from walwriter?

**Hint:** data buffers vs. WAL buffers.

### Exercise 27 — wal_buffers

What data does it hold?

**Hint:** WAL records in shared memory.

### Exercise 28 — pg_stat_wal

Name four useful metrics.

**Hint:** wal_bytes, wal_records, wal_write, wal_sync, timings.

### Exercise 29 — track_wal_io_timing

What does it help observe?

**Hint:** WAL write/sync timing.

### Exercise 30 — pg_stat_replication

Which LSNs help track standby progress?

**Hint:** write_lsn, flush_lsn, replay_lsn.

### Exercise 31 — JDBC Commit

When Connection.commit returns normally, what do the semantics depend on?

**Hint:** server durability settings.

### Exercise 32 — Ambiguous Commit

Why does a client receiving an SQLException not prove the transaction rolled back?

**Hint:** the response may have been lost after the server committed.

### Exercise 33 — Idempotency

How do you handle retries after commit ambiguity?

**Hint:** unique business key / idempotency key.

### Exercise 34 — WAL Archive

Is WAL archiving required for a local COMMIT to succeed?

**Hint:** not in normal configurations.

### Exercise 35 — pg_switch_wal

Is it a per-transaction flush command?

**Hint:** no, it switches segments.

### Exercise 36 — max_wal_size

Is it a hard cap on pg_wal?

**Hint:** no.

### Exercise 37 — Storage

Why does a hardware write cache need power-loss protection and proper flush semantics?

**Hint:** fsync cannot compensate for a device falsely reporting durability.

### Exercise 38 — Commit Latency

List three causes other than fsync that can slow down COMMIT.

**Hint:** locks, synchronous standby lag, CPU/network.

### Exercise 39 — WAL Buffers Full

What does a rising wal_buffers_full metric suggest?

**Hint:** buffer pressure and WAL generation/write workload.

### Exercise 40 — Durability Choice

When can synchronous_commit=off be considered?

**Hint:** only for workloads that tolerate losing recent transactions and can regenerate them.

## 50. Frequently Asked Questions

### Is walwriter the only process that writes WAL?

No. Backend processes can also write/flush WAL when needed, especially when a commit requires WAL durable through a specific position.

### Once WAL is written, is it safe across a power loss?

Not necessarily. A write may only place data into the OS cache. Flush/fsync and storage semantics determine durability.

### Does COMMIT wait for data pages to be written to table files?

No. Commit typically waits for WAL per durability policy; data pages can be written out later by checkpoints or background writers.

### Can synchronous_commit=off lose data?

Yes, recent transactions already reported successful by the server can be lost if a crash happens before WAL flushes. The database still relies on WAL recovery to preserve consistency.

### Is disabling fsync the same as synchronous_commit=off?

No. Disabling fsync can cause corruption or loss of consistency on crash. synchronous_commit=off changes commit confirmation timing while preserving fsync for other writes.

### Does remote_write guarantee remote durability?

No. It waits for the standby to write WAL to its OS; remote flush has not necessarily finished.

### When is remote_apply used?

When commit must wait for the standby to replay/apply the transaction, such as for certain read-after-commit requirements on standbys.

### Does group commit make every transaction wait longer?

Not necessarily. It can share a single flush across multiple commits. commit_delay is a conditional wait mechanism and must be benchmarked.

### What is the impact of overly frequent checkpoints?

They can increase data I/O and full-page images / WAL volume. Balance against recovery time and WAL capacity.

### Does pg_stat_wal measure commit latency directly?

No. It provides WAL write/sync statistics. Combine it with query timings, wait events, replication metrics, and application measurements.

### If a JDBC commit times out, should you retry immediately?

Not if the operation is non-idempotent. The server may have committed while the response was lost. Look up status by business key or idempotency key.

### If WAL archiving is enabled, can you turn off fsync?

No. Archiving does not replace local durability of WAL and data files.

### Does increasing wal_writer_delay reduce commit latency?

Not guaranteed. Synchronous backends can flush themselves when needed; any change must be backed by measurements.

## 51. Summary

Key observation queries:

~~~sql
-- WAL configuration.
SHOW wal_buffers;
SHOW wal_writer_delay;
SHOW wal_writer_flush_after;
SHOW synchronous_commit;
SHOW fsync;
SHOW wal_sync_method;

-- WAL progress.
SELECT
    pg_current_wal_insert_lsn(),
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();

-- Unflushed bytes at query time.
SELECT pg_wal_lsn_diff(
    pg_current_wal_insert_lsn(),
    pg_current_wal_flush_lsn()
);

-- WAL statistics.
SELECT *
FROM pg_stat_wal;

-- Synchronous replication progress.
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- WAL wait events and session activity.
SELECT
    pid,
    wait_event_type,
    wait_event,
    state
FROM pg_stat_activity
WHERE wait_event IS NOT NULL;
~~~

Principles to remember:

1. **WAL records are generated before data pages are durably written** per the write-ahead rule.
2. WAL buffers reside in shared memory; walwriter writes them to WAL segment files.
3. Backends can write/flush WAL themselves when COMMIT requires durability.
4. **Insert, write, and flush LSNs are three distinct milestones.**
5. Writing to OS cache does not mean durable across power loss.
6. `fsync=on` is essential for production durability.
7. `synchronous_commit` determines how far a transaction waits for local/remote acknowledgement.
8. `off` can report success before local WAL flush; recent transactions can be lost after a crash.
9. `remote_write` is not the same as remote flush; `remote_apply` waits for standby replay.
10. Group commit lets multiple transactions share a single WAL flush.
11. `wal_writer_delay` and `wal_writer_flush_after` control walwriter behavior, not the durability contract.
12. **COMMIT does not need to wait for a CHECKPOINT**; WAL is durable enough for recovery.
13. Checkpoints write dirty data pages and create a recovery point.
14. The background writer handles data buffers; walwriter handles WAL buffers.
15. Monitor `pg_stat_wal`, LSN gaps, wait events, and `pg_stat_replication`.
16. A JDBC commit exception can be an ambiguous outcome if the response was lost after server commit; use idempotency.
17. WAL archives and backups do not replace fsync or disaster recovery.
18. Storage hardware must honor flush semantics.

Confirmation timing diagram:

~~~text
SQL INSERT/UPDATE
       |
       v
WAL records generated
       |
       v
WAL buffers (insert LSN)
       |
       v
Write WAL files (write LSN)
       |
       v
Flush WAL (flush LSN)
       |
       v
Commit record durable per policy?
       |
       +--> synchronous_commit=on:
       |       wait for local flush
       |       and remote flush if sync standby
       |
       +--> synchronous_commit=off:
       |       may return success before local flush
       |
       v
Server returns COMMIT success
       |
       v
Data pages written by background/checkpointer
       |
       v
Checkpoint completes per schedule/threshold
~~~

**Conclusion:** Walwriter helps PostgreSQL write WAL buffers steadily and relieves pressure on backends, yet **when COMMIT is confirmed depends on the durability policy**, specifically `synchronous_commit`, `fsync`, and synchronous replication. Distinguish write from flush, commit from checkpoint, local durability from remote acknowledgement, and verify latency using WAL/replication metrics before adjusting configuration.
