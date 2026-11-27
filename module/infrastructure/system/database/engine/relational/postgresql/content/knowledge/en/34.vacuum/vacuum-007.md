# Long Transactions, Replication Slots, and the Cleanup Horizon in PostgreSQL

PostgreSQL uses **MVCC (Multi-Version Concurrency Control)** to let multiple transactions read and write concurrently. When a transaction updates or deletes a row, PostgreSQL typically creates a new row version and retains the old version until it is certain no remaining snapshot needs to see it.

**VACUUM** reclaims row versions that are no longer needed, updates visibility/free-space metadata, and protects against transaction ID wraparound. Yet VACUUM cannot delete every dead tuple the instant it sees it. It must respect a safety boundary known as the **cleanup horizon**.

A transaction holding an old snapshot, an unconsumed logical replication slot, or a standby sending feedback for an old snapshot can pin the horizon in the past. When that happens:

- Dead tuples stay in the heap.
- Old TOAST data may also remain unreclaimed.
- Autovacuum runs without being able to clean up versions still needed by snapshots/consumers.
- Tables and indexes bloat.
- Replication slots can retain WAL, growing filesystem usage.
- If prolonged, the database can face transaction ID wraparound pressure.

This lesson, **"Long Transactions, Replication Slots, and the Cleanup Horizon"**, belongs to the **VACUUM** chapter of the **Database Engine Relational PostgreSQL** module. It explains the relationship between MVCC snapshots, XID/XMIN, the cleanup horizon, long-running transactions, logical/physical replication slots, hot standby feedback, VACUUM, freezing, and diagnostic/remediation tools.

> **Core principle:** VACUUM may only reclaim row versions that every protected snapshot and retention mechanism can safely discard. Before treating bloat, first locate whatever is pinning the cleanup horizon in the past.

---

## 1. Why Can't VACUUM Delete Old Tuples Immediately?

Suppose a table holds a row:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(14,2) NOT NULL
);

INSERT INTO accounts VALUES (1, 1000.00);
~~~

Transaction A starts a snapshot and reads the balance:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE account_id = 1;
~~~

Transaction B updates it:

~~~sql
UPDATE accounts
SET balance = 900.00
WHERE account_id = 1;

COMMIT;
~~~

PostgreSQL cannot simply overwrite 1000 with 900 while transaction A still needs to see the old state. To A's snapshot, the old row remains valid; the new version is visible to newer appropriate snapshots.

Thus the heap temporarily holds:

~~~text
account_id = 1
  |
  +-- old row version: balance = 1000
  |
  +-- new row version: balance = 900
~~~

Only when no remaining snapshot needs the old version can VACUUM reclaim it.

## 2. MVCC and Transaction IDs

Every PostgreSQL tuple carries MVCC metadata, including identifiers for the transaction that created the version and the transaction that ended its validity.

The key internal fields are commonly called:

- `xmin`: transaction ID that created the tuple version.
- `xmax`: transaction ID that deleted, updated, or locked the tuple depending on context.

These are implementation fields in the tuple header, not user-declared business columns.

### 2.1. Tuple xmin Is Not the Same as backend_xmin

The name `xmin` appears in several contexts:

- Tuple header `xmin`: XID that created the row version.
- `pg_stat_activity.backend_xmin`: snapshot horizon held by a backend.
- `pg_replication_slots.xmin`: XID horizon a replication slot requires retaining.
- `pg_replication_slots.catalog_xmin`: horizon retaining catalog tuples for logical decoding.

Do not confuse these fields. They belong to the same MVCC ecosystem yet represent distinct things.

## 3. What Is the Cleanup Horizon?

The **cleanup horizon** is the transaction ID boundary PostgreSQL uses to decide which old row versions are no longer needed by any protected snapshot or consumer.

Conceptually:

~~~text
Old Transaction IDs --------------------------> New
       |
       |       Cleanup horizon
       v             |
  Versions eligible  |      Versions a snapshot
  for cleanup        |      might still need
                     v
~~~

If a tuple was deleted by a committed transaction whose transaction ID is not yet old enough relative to the horizon, VACUUM must keep it.

Internal names and exact horizon calculation details vary by version; operators should inspect the sources pinning the horizon rather than relying on a single internal variable.

### 3.1. The Horizon Is Not Wall-Clock Time

The cleanup horizon does not mean "delete rows older than 24 hours". It is based on transaction IDs and snapshot visibility. A transaction lasting only a few minutes can hold very old versions if it keeps an old snapshot open, or if another snapshot keeps pinning the horizon.

## 4. Dead Tuples vs. Removable Tuples

A tuple may no longer be visible to new queries yet still be unsafe to delete.

Distinguish:

- **Live tuple:** version still visible to appropriate snapshots.
- **Dead tuple:** version no longer current under transaction state.
- **Removable tuple:** version older than the cleanup horizon and no longer needed by any snapshot/consumer; VACUUM can reclaim it.

Therefore, dead tuple statistics do not mean all dead tuples are immediately removable.

When running `VACUUM VERBOSE`, PostgreSQL can report dead tuples that are not yet removable. This is a valuable clue when investigating long transactions or replication retention.

## 5. Long-Running Transactions Holding Snapshots

A transaction holding an old snapshot prevents VACUUM from reclaiming row versions needed by that snapshot.

Example:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT *
FROM accounts
WHERE account_id = 1;

-- Application holds the transaction open for a long time.
~~~

Meanwhile, other transactions keep updating and deleting rows.

Consequence: old versions keep piling up until transaction A commits or rolls back.

### 5.1. A Long Transaction Does Not Need to Run Queries Continuously

A transaction might be:

- Waiting on user input.
- Waiting on an external HTTP call.
- Waiting on a message broker.
- Waiting on a lock.
- Holding a cursor or snapshot.
- Sitting `idle in transaction`.

What matters is not just whether a query is actively executing, but **whether the backend still holds a snapshot/XID that restricts cleanup**.

## 6. READ COMMITTED vs. REPEATABLE READ

At the default isolation level `READ COMMITTED`, each statement normally takes a fresh snapshot. Once a statement finishes, its snapshot is not necessarily held until the end of the transaction.

At `REPEATABLE READ`, a transaction uses one consistent snapshot throughout the transaction; that old snapshot is held until the transaction ends.

`SERIALIZABLE` also has its own snapshot semantics and retains state needed for serialization checks.

Consequently, a long-lived `REPEATABLE READ`/`SERIALIZABLE` transaction can hold back the cleanup horizon far longer than a `READ COMMITTED` transaction sitting idle between statements.

**Do not conclude purely from `state='idle in transaction'`.** Check `backend_xmin`, `backend_xid`, isolation level, and transaction duration to confirm whether the backend actually pins a snapshot/horizon.

## 7. Idle in Transaction

An application can open a transaction:

~~~sql
BEGIN;

SELECT *
FROM orders
WHERE order_id = 100;

-- Waits 30 minutes for user confirmation.
~~~

If the connection fails to COMMIT or ROLLBACK, the transaction stays open. With a snapshot held, VACUUM may have to retain old versions.

Common causes:

- Opening a transaction before calling an external API.
- Overly broad ORM transaction scopes.
- Exception paths missing a rollback.
- Returning a connection to a pool before ending the transaction.
- Workflows waiting on human interaction inside a transaction.
- Workers opening a transaction and waiting on a queue message.

### 7.1. Not Every Idle Transaction Has the Same Impact

Under `READ COMMITTED`, a finished `SELECT`'s snapshot may no longer be pinned while idle. Still, the transaction can hold locks or an allocated XID and cause other problems.

Inspect `backend_xmin` and `backend_xid` rather than looking solely at `state`.

## 8. Exported Snapshots

PostgreSQL lets a transaction export its snapshot using:

~~~sql
SELECT pg_export_snapshot();
~~~

Another transaction can import that snapshot under matching transaction isolation rules.

An exported snapshot lives only while the exporting transaction remains open. If an exporter stays open long so workers can import its snapshot, it also holds back an old horizon and delays cleanup.

This special case often appears in parallel dump and consistent-read workflows.

### 8.1. Do Not Keep Exporter Transactions Open Longer Than Necessary

Design the lifetime of exported snapshots cleanly. Once all importers have established their snapshots as required, end the exporter transaction promptly.

## 9. Prepared Transactions and Two-Phase Commit

A transaction prepared with `PREPARE TRANSACTION` to await COMMIT/ROLLBACK in two-phase commit can persist indefinitely and retain XIDs and locks.

Inspect:

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Abandoned prepared transactions block maintenance, hold locks, and keep transaction state alive. Never leave orphaned prepared transactions dangling.

Before running `COMMIT PREPARED` or `ROLLBACK PREPARED`, verify the state of the coordinator/distributed transaction; the wrong decision can desynchronize participating systems.

## 10. What Is a Replication Slot?

A **replication slot** retains resources that a replication or decoding consumer might still need.

Examples:

- A logical decoding consumer reading WAL for row changes.
- A physical standby needing WAL for replay.
- A CDC pipeline consuming changes asynchronously.

Slots prevent PostgreSQL from discarding needed WAL before the consumer confirms progress.

However, a slot can persist even when the consumer **is no longer connected**. An inactive slot can still hold WAL or a transaction horizon.

## 11. Two Types of Replication Slots

| Type | Primary Purpose | Resources It Can Retain |
|---|---|---|
| Physical slot | Retain WAL for a physical replication consumer | WAL from `restart_lsn`; may interact with feedback horizon depending on config |
| Logical slot | Track logical decoding/CDC progress | WAL, transaction `xmin`, and `catalog_xmin` per slot state |

Physical and logical slots do not serve the same purpose.

### 11.1. A Slot Is Not a Replication Connection

A replication connection can disconnect while the slot remains. A slot is persistent server-side state kept so the consumer can reconnect later.

### 11.2. Inactive Slots Do Not Auto-Delete

Having no online consumer does not mean a slot has no impact. An old slot can retain WAL indefinitely.

## 12. Key Columns of pg_replication_slots

The `pg_replication_slots` view exposes slot details.

| Column | Meaning |
|---|---|
| `slot_name` | Name of the slot |
| `slot_type` | `physical` or `logical` |
| `database` | Associated database if database-scoped |
| `active` | Whether the slot is currently in use |
| `active_pid` | PID of the process currently using the slot, if active |
| `xmin` | XID horizon the slot requires keeping for tuple visibility |
| `catalog_xmin` | Horizon retaining catalog tuples for logical decoding |
| `restart_lsn` | Oldest WAL LSN the slot might still need |
| `confirmed_flush_lsn` | Confirmed flush progress of a logical slot per slot semantics |

Not every column is populated for every slot type or at every moment.

### 12.1. xmin and catalog_xmin

`xmin` can prevent VACUUM from reclaiming tuple versions a consumer still needs.

`catalog_xmin` protects catalog tuples needed for logical decoding, such as schema/type/relation metadata per decoder snapshots.

A logical slot can cause both:

- **Heap/table bloat** via `xmin`.
- **Catalog bloat** via `catalog_xmin`.

### 12.2. restart_lsn Is the WAL Dimension

`restart_lsn` retains WAL segments needed by the slot. This is **WAL retention**, not the same thing as the heap cleanup horizon.

A slot can grow `pg_wal` disk usage even without pinning heap `xmin`, or pin `xmin`/`catalog_xmin` and cause bloat even when WAL retention is bounded elsewhere.

## 13. Logical Replication Slots and the Cleanup Horizon

Logical decoding reads changes from WAL and may require matching row/catalog versions.

A slot maintains `xmin` and `catalog_xmin` as needed for decoding. VACUUM must respect these horizons so it never deletes data logical decoding might still need.

A slow or abandoned consumer can cause:

~~~text
Inactive logical slot
       |
       +--> old restart_lsn
       |       |
       |       +--> WAL keeps accumulating
       |
       +--> old xmin
       |       |
       |       +--> dead tuples cannot be reclaimed
       |
       +--> old catalog_xmin
               |
               +--> catalog versions retained
~~~

This is why **inactive logical slots** must be monitored, not just active replication connections.

## 14. Physical Slots and hot_standby_feedback

Physical replication slots primarily ensure standbys have needed WAL to replay. A separate mechanism is `hot_standby_feedback`.

On the standby:

~~~sql
SHOW hot_standby_feedback;
~~~

When enabled, the standby sends its snapshot horizon to the primary so the primary avoids removing row versions still needed by standby queries, reducing recovery conflicts.

In exchange, feedback can pin the primary's cleanup horizon in the past and cause bloat.

### 14.1. Feedback Differs from a Replication Slot

- A replication slot retains resources based on slot state.
- Hot standby feedback sends `xmin` from standby to primary.
- Both can coexist.
- Do not treat the existence of a physical slot as the sole proof of a pinned horizon.

On the primary, check `pg_stat_replication.backend_xmin` to see the `xmin` reported by standby feedback, if any.

## 15. Trade-Offs of hot_standby_feedback

When feedback is off, the primary can clean up old versions, yet standby queries can be canceled by recovery conflicts if they need those versions.

When feedback is on:

- Standby queries suffer fewer cleanup-conflict cancellations.
- The primary may retain dead tuples longer.
- Primary bloat can grow if standby queries run long.
- An old standby transaction can affect VACUUM on the primary.

Never toggle it based on a single metric. Weigh standby query SLAs, storage capacity, vacuum health, and replication topology.

## 16. max_slot_wal_keep_size Does Not Solve Every Horizon

PostgreSQL provides `max_slot_wal_keep_size` to cap the WAL retained by replication slots across checkpoints per server policy.

~~~sql
SHOW max_slot_wal_keep_size;
~~~

This parameter governs **WAL retention**, not a switch to make VACUUM ignore `xmin` or `catalog_xmin`.

If a slot exceeds the WAL cap, the slot can be invalidated because needed WAL was removed. The consumer may then have to recreate the slot and resynchronize from another source.

### 16.1. Do Not Confuse WAL Retention with Tuple Retention

| Issue | Related Fields/Settings |
|---|---|
| Retained WAL segments | `restart_lsn`, `wal_keep_size`, `max_slot_wal_keep_size` |
| Retained heap tuples | `xmin`, active snapshots, standby feedback |
| Retained catalog tuples | `catalog_xmin` |
| Logical consumer progress | `confirmed_flush_lsn` |

Capping WAL does not replace monitoring `xmin` and `catalog_xmin`.

## 17. wal_keep_size and Replication Slots

`wal_keep_size` configures a minimum amount of WAL to retain for standbys.

Replication slots retain WAL based on each slot's required position. The two mechanisms have related goals yet work differently.

If WAL is retained too long:

- `pg_wal` can grow.
- The filesystem can fill up.
- Checkpoints and archiving can face pressure.
- Replication slots can be invalidated if slot limits apply.

Never solve this by manually deleting WAL files in the data directory.

## 18. Inactive Replication Slots Are a Risk

A slot can become inactive because:

- A CDC consumer stopped.
- A connector was deleted without cleaning up the slot.
- A deployment renamed a slot.
- A prolonged network outage occurred.
- A consumer choked on a schema change.
- A test slot was forgotten.
- A failover left a consumer pointing at the wrong primary.

Inactive does not mean safe to drop. Before dropping, confirm whether any consumer still needs data from that slot.

## 19. Inspecting Replication Slots

Basic query:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

`age(xmin)` reports XID age under PostgreSQL's transaction age semantics. NULL in `xmin`/`catalog_xmin` can be a normal state.

### 19.1. Version-Dependent Columns

Newer PostgreSQL versions may add columns such as `wal_status`, `safe_wal_size`, `inactive_since`, and `invalidation_reason`. Only query these columns when supported by your server version.

Inspect the view schema for your actual version in `psql`:

~~~text
\d+ pg_replication_slots
~~~

## 20. Inspecting Standby Feedback on the Primary

~~~sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
~~~

`backend_xmin` reveals the horizon sent by the standby to the primary when hot standby feedback is active.

NULL is not necessarily an error; it can simply mean the standby is not currently reporting a snapshot `xmin` to hold.

## 21. Finding Backends Holding Old Snapshots

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xid,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Columns to watch:

- `xact_start`: when the transaction began.
- `backend_xid`: XID of the backend's transaction if assigned.
- `backend_xmin`: snapshot horizon held by the backend, if any.
- `state`: `active`, `idle`, `idle in transaction`, and other states.
- `wait_event`: what the backend is waiting on.

### 21.1. Do Not Sort Solely by xact_age

A long active query reading data is not always the sole blocker. An idle session can pin a critical snapshot. Combine age, `backend_xmin`, and `state`.

### 21.2. application_name Helps Identify Owners

Set distinct `application_name` values per service, worker, and connector so DBAs know which session holds a transaction. Do not reuse one generic name across the whole system if you need to distinguish workloads.

## 22. Finding Old Prepared Transactions

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    now() - prepared AS prepared_age,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Prepared transactions should not linger indefinitely. Check the coordinator and transaction manager before deciding between `COMMIT PREPARED` and `ROLLBACK PREPARED`.

## 23. Monitoring Dead Tuples and Vacuum Activity

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

`n_dead_tup` is a **statistical estimate**, not an exact count of tuples immediately reclaimable.

Cross-check with:

- `VACUUM VERBOSE` output.
- Long transactions and snapshots.
- Replication slots.
- Standby feedback.
- Table/TOAST relation sizes.
- Autovacuum logs.

## 24. Monitoring VACUUM Progress

In PostgreSQL versions supporting `pg_stat_progress_vacuum`:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum;
~~~

This view shows the phase and progress of running VACUUMs. Active progress does not guarantee all dead tuples are being cleaned; the horizon still limits what can be reclaimed.

## 25. Checking Transaction ID Age

Database-level:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Table-level:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 30;
~~~

High XID age signals the need to check vacuuming and freezing. Never wait until right up against the wraparound limit to act.

## 26. Cleanup Horizon and Transaction ID Wraparound

PostgreSQL uses finite XID space. If transaction IDs wrap around before old tuples are safely frozen, the database risks misinterpreting transaction age.

VACUUM is responsible for **freezing** sufficiently old tuples and updating frozen-XID metadata so the database stays safe across wraparound.

Long-running snapshots and replication horizons can prevent VACUUM from advancing as far as desired. This is not just a disk bloat issue—it threatens the database's ability to keep accepting writes.

### 26.1. Anti-Wraparound Autovacuum

PostgreSQL automatically triggers anti-wraparound vacuums when XID age approaches configured limits. These processes are vital and must never be blocked or disabled carelessly.

If wraparound warnings appear, resolve whatever holds the horizon, let vacuum finish, and re-verify XID ages.

## 27. Freeze Horizon vs. Dead-Tuple Cleanup

VACUUM performs multiple tasks:

- Reclaims dead tuples when safe.
- Freezes sufficiently old tuple XIDs.
- Updates visibility map and free space metadata.
- Refreshes statistics when invoked with `ANALYZE`.

A pinned cleanup horizon can prevent reclaiming certain versions. Freeze horizons and anti-wraparound are related maintenance dimensions, distinct from returning heap file space to the operating system.

Never judge vacuum health solely by `n_dead_tup` or file size.

## 28. Why Does Bloat Grow Even While VACUUM Runs?

Possible scenarios:

1. VACUUM can only reclaim tuples older than the cleanup horizon.
2. A long transaction holds an old snapshot.
3. A logical slot pins `xmin`/`catalog_xmin`.
4. Standby feedback sends an old `backend_xmin`.
5. A prepared transaction holds old state.
6. A long-held exported snapshot blocks advancement.
7. Autovacuum cannot keep up with UPDATE/DELETE rates.
8. Index cleanup and heap cleanup face heavy load/locks.
9. VACUUM creates reusable internal space without shrinking the file on the filesystem.

### 28.1. VACUUM Cannot Safely Bypass the Horizon

Running VACUUM repeatedly will not fix the root cause while a transaction or slot still pins the horizon. Find the blocker first.

## 29. Lab: Proving a Long Snapshot Retains Row Versions

Run in a lab database.

Create table:

~~~sql
CREATE SCHEMA vacuum_lab;

CREATE TABLE vacuum_lab.items (
    item_id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

INSERT INTO vacuum_lab.items
VALUES (1, 'original value');
~~~

**Session A — hold a snapshot:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT payload
FROM vacuum_lab.items
WHERE item_id = 1;
~~~

The result is `original value`. Keep transaction A open.

**Session B — update and vacuum:**

~~~sql
UPDATE vacuum_lab.items
SET payload = 'updated value'
WHERE item_id = 1;

VACUUM (VERBOSE, ANALYZE) vacuum_lab.items;
~~~

VACUUM is not permitted to remove the old version while snapshot A still needs it.

Back in Session A:

~~~sql
SELECT payload
FROM vacuum_lab.items
WHERE item_id = 1;
~~~

A still sees `original value` under its `REPEATABLE READ` snapshot.

### 29.1. End the Snapshot and Vacuum Again

Session A:

~~~sql
COMMIT;
~~~

Session B:

~~~sql
VACUUM (VERBOSE, ANALYZE) vacuum_lab.items;
~~~

Once the old snapshot ends, the old version becomes removable if no other blocker remains.

Exact tuple counts depend on vacuum timing and environment; the lab goal is observing the contrast between an open snapshot and a closed one.

## 30. Lab: Observing backend_xmin

While Session A holds its transaction open, run from an observer session:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    age(backend_xmin) AS xmin_age,
    application_name
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Locate Session A's PID.

`backend_xmin` reveals the snapshot horizon held by the session. If NULL, do not assume the session has zero impact; check isolation level, transaction ID, and locks.

## 31. Lab: Inspecting Replication Slots Safely

Start with a read-only query:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;
~~~

Look for slots that are:

- Long-inactive.
- Holding old `xmin`/`catalog_xmin`.
- Far behind the current WAL position on `restart_lsn`.
- Missing a clear consumer owner.

**Never drop a slot just because `active=false`.** First verify whether the consumer still needs to resume CDC/replication from that position.

## 32. Creating a Logical Slot in the Lab (Optional)

Only in an isolated lab database, if the server is configured for logical decoding:

- `wal_level` must support `logical`.
- `max_replication_slots` must have available capacity.
- An output plugin must be installed.
- The role must hold appropriate replication privileges.

Example with the `test_decoding` plugin if installed:

~~~sql
SELECT *
FROM pg_create_logical_replication_slot(
    'vacuum_lab_slot',
    'test_decoding'
);
~~~

Creating a slot starts retaining WAL and transaction/catalog horizons. **Never run this casually on production.**

After finishing the lab, if the slot is inactive and you are certain no consumer needs it:

~~~sql
SELECT pg_drop_replication_slot('vacuum_lab_slot');
~~~

If a slot is active, stop/disconnect the consumer cleanly first. Dropping a slot can make downstream unable to resume from its old checkpoint.

## 33. Do Not Neglect Inactive Logical Slots

An inactive slot can:

- Retain WAL via `restart_lsn`.
- Pin `xmin`, causing heap bloat.
- Pin `catalog_xmin`, causing catalog bloat.
- Grow `pg_wal` until the filesystem runs out of space.

Review slot inventories regularly, assign an owner/service to every slot, track last activity, and alert on slots without active consumers.

## 34. max_slot_wal_keep_size and Slot Invalidation

When a slot WAL retention cap is configured, PostgreSQL can mark a slot unusable if required WAL has been discarded.

This protects the filesystem from an abandoned slot holding WAL forever, but may force the consumer to **reinitialize/resnapshot**.

Never treat slot invalidation as "data is already synced". Consumers must have a full data-recovery procedure.

### 34.1. Never Delete pg_wal Files Manually

Deleting WAL files with filesystem commands can corrupt the cluster. Always manage slots, archiving, and WAL configuration through PostgreSQL.

## 35. Hot Standby Feedback: Diagnosing Across Two Nodes

On the standby:

~~~sql
SHOW hot_standby_feedback;
~~~

On the primary:

~~~sql
SELECT
    application_name,
    state,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    replay_lsn,
    reply_time
FROM pg_stat_replication;
~~~

If feedback is enabled and the standby holds an old snapshot, the primary must retain row versions to avoid recovery conflicts.

### 35.1. Trade-Offs of Disabling Feedback

Disabling feedback can reduce primary bloat, yet long-running queries on the standby can be canceled when recovery needs to clean up those old versions.

Weigh read-replica workloads, query durations, replication lag, and storage capacity before changing it.

## 36. Why Can Replication Slots and Standby Feedback Compound?

A standby can use both a physical replication slot and `hot_standby_feedback` at the same time.

In that setup:

- The slot retains WAL via `restart_lsn`.
- Feedback can pin the cleanup horizon via `xmin`.
- Long queries on the standby prolong how long feedback pins the horizon.

Monitor each dimension separately. Never look at `restart_lsn` and assume heap cleanup is unblocked.

## 37. Remediation: Find the Blocker Before Acting

Diagnostic workflow:

~~~text
Bloat / dead tuples rising
          |
          v
Check VACUUM/autovacuum
          |
          v
VACUUM unable to reclaim tuples?
          |
          v
Find oldest backend_xmin
          |
          v
Find replication slot xmin/catalog_xmin
          |
          v
Check standby backend_xmin/feedback
          |
          v
Check prepared transactions/exported snapshots
          |
          v
Identify owner and purpose of the blocker
          |
          v
Release the exact horizon blocker
          |
          v
Re-run VACUUM and monitor
~~~

Never start with `VACUUM FULL` or dropping slots.

## 38. Ending Long Transactions

If the application still actively uses the transaction, the right fix is normally letting the application COMMIT or ROLLBACK per business logic.

If a transaction was abandoned:

- Identify the service/`application_name` and owner.
- Check whether it is waiting on a user or external service.
- Inspect held locks and the backend query.
- Have the application close the transaction properly.
- If DBA intervention is required, assess rollback impact before terminating.

`pg_cancel_backend(pid)` cancels the active query if possible; it **does not guarantee ending the transaction or session**. `pg_terminate_backend(pid)` terminates the session and rolls back any uncommitted transaction, which can impact business operations.

Never terminate purely because age is high without evaluating the consequences.

## 39. Handling Abandoned Replication Slots

Before dropping:

1. Identify slot type, database, plugin, and owner.
2. Check whether the connector/consumer still exists.
3. Determine the last processed checkpoint/LSN.
4. Confirm downstream can resnapshot if needed.
5. Check whether the slot is active.
6. Stop the consumer cleanly.
7. Drop only after accepting the loss of resume capability from that slot.

The command:

~~~sql
SELECT pg_drop_replication_slot('slot_name');
~~~

has serious consequences for consumers. Never run it with placeholders or on production slots without verification.

## 40. Advancing a Logical Slot Can Skip Changes

PostgreSQL provides slot-management functions such as `pg_replication_slot_advance` in supported versions.

Advancing a slot moves its position forward; changes prior to the new position can no longer be read by the consumer from that slot.

This is **not a vacuum button**. Only advance when downstream has already synced via another mechanism or the owner accepts skipping that WAL range.

Afterward, verify slot state and consumer checkpoints. Never use advance to mask an uninvestigated CDC failure.

## 41. Autovacuum Cannot Fix a Permanently Pinned Horizon

Autovacuum can run frequently, yet if the horizon never advances:

- Tuples remain non-removable.
- VACUUM scans without reclaiming held versions.
- Table bloat continues climbing.
- Autovacuum runs more often, burning extra I/O and CPU.
- XID freeze progress can come under pressure.

Adding autovacuum workers or lowering scale factors will not fix the root cause while the blocker remains.

## 42. Manual VACUUM After Releasing the Horizon

Once the transaction/slot/feedback blocker ends, you can let autovacuum handle it or run:

~~~sql
VACUUM (VERBOSE, ANALYZE) schema_name.table_name;
~~~

VACUUM:

- Reclaims versions old enough to remove.
- Updates free space and visibility metadata.
- `ANALYZE` updates planner statistics if requested.

Never run inside an explicit transaction block.

### 42.1. Standard VACUUM Does Not Return File Size Immediately

Reclaimed space usually becomes internal free space reusable by new rows in the relation. The filesystem file may not shrink.

If physical shrinking is required, evaluate a rewrite/`pg_repack` or `VACUUM FULL` with appropriate lock, downtime, and temporary space planning.

## 43. VACUUM FULL Is Not a Horizon Fix

`VACUUM FULL` rewrites the relation and takes a strong lock. It is not a safe way to bypass a snapshot or replication slot that still needs old data.

If the cleanup horizon has not advanced, a rewrite can be blocked, fail to fix the cause, or add heavy operational cost. Release the blocker first, then evaluate whether file compaction is genuinely needed.

## 44. Anti-Wraparound and Failsafe

Monitor:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

PostgreSQL enforces freeze/anti-wraparound autovacuum thresholds and version-specific failsafe mechanisms. When XID age warnings rise:

- Find long transactions and slots.
- Ensure autovacuum can run.
- Check disk space and WAL headroom.
- Never disable anti-wraparound vacuum.
- Schedule any needed maintenance.
- Verify age advances after blockers are cleared.

If transaction age gets too close to the safety limit, PostgreSQL can restrict writes to prevent wraparound corruption. Treat this as an emergency.

## 45. Parameters to Know

| Setting | Meaning |
|---|---|
| `autovacuum` | Enables/disables autovacuum at configured scope |
| `autovacuum_freeze_max_age` | XID age triggering anti-wraparound freeze vacuum |
| `vacuum_freeze_table_age` | Relation age deciding aggressive vacuum/freeze |
| `vacuum_freeze_min_age` | Minimum age for freezing tuples per policy |
| `max_replication_slots` | Maximum number of replication slots |
| `max_slot_wal_keep_size` | WAL cap retained by replication slots |
| `wal_keep_size` | Configured minimum retained WAL |
| `hot_standby_feedback` | Standby sends `xmin` feedback to primary |
| `idle_in_transaction_session_timeout` | Timeout for sessions idle inside a transaction |
| `statement_timeout` | Statement duration limit |
| `lock_timeout` | Lock wait duration limit |

Parameter changes must fit PostgreSQL version, workload, topology, and SLAs. Never apply one blanket setting across every database.

## 46. idle_in_transaction_session_timeout

Can be configured to terminate sessions sitting idle inside a transaction too long:

~~~sql
SHOW idle_in_transaction_session_timeout;
~~~

Example database/role/session setting to review:

~~~sql
ALTER ROLE app_runtime
SET idle_in_transaction_session_timeout = '5min';
~~~

This is an illustrative value only. Timeouts terminate sessions, roll back transactions, and fail application requests. Fix application transaction scopes first rather than relying solely on timeouts as a safety net.

### 46.1. Does Not Replace Monitoring

Timeouts do not catch long-running active queries or replication slots. You still need to monitor `backend_xmin`, transaction age, and slot horizons.

## 47. Consolidated Monitoring Queries

Read-only diagnostic queries:

**Backend snapshots:**

~~~sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    age(backend_xmin) AS xmin_age,
    backend_xid,
    backend_xmin
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY age(backend_xmin) DESC NULLS LAST;
~~~

**Replication slots:**

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    age(xmin) AS xmin_age,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn
FROM pg_replication_slots
ORDER BY age(xmin) DESC NULLS LAST;
~~~

**Dead tuple estimates:**

~~~sql
SELECT
    schemaname,
    relname,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

**Database XID age:**

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

These queries must be interpreted together. A single old `backend_xmin`, old slot `xmin`, or dead tuple estimate in isolation rarely tells the whole bloat story.

## 48. Real-World Scenario: Stopped CDC Consumer

Symptoms:

- The CDC connector was removed from deployment.
- Its replication slot still exists.
- `active=false`.
- `restart_lsn` is not advancing.
- `xmin`/`catalog_xmin` remain pinned at old ages.
- WAL directory and/or tables grow in size.

Handling:

1. Identify the slot owner.
2. Confirm the connector has been decommissioned.
3. Confirm whether downstream needs resnapshot.
4. Assess WAL/disk pressure.
5. Stop the consumer if still connected.
6. Drop the slot once approved.
7. Watch the horizon advance and run vacuum as needed.
8. Add inactive-slot alerting to monitoring.

Never drop a slot just to make metrics look clean if the pipeline still needs to resume.

## 49. Scenario: Standby Query Causing Primary Bloat

Symptoms:

- Dead tuples rise on the primary.
- Autovacuum runs yet cannot clean certain versions.
- Standby runs a long `REPEATABLE READ` query.
- `hot_standby_feedback` is enabled.
- `pg_stat_replication.backend_xmin` is old.

Considerations:

- Shorten queries/snapshots on the standby.
- Route long reports to an appropriate snapshot/replica.
- Adjust feedback after weighing recovery conflicts.
- Monitor primary bloat and standby query cancellations.

Never disable feedback without understanding its impact on standby queries.

## 50. Scenario: idle in transaction from an Application Pool

Symptoms:

- `pg_stat_activity.state = 'idle in transaction'`.
- `xact_start` is very old.
- `backend_xmin` holds an old value.
- The app request finished, yet the connection never committed/rolled back.

Root fix:

- Narrow transaction scopes.
- Never wait on HTTP/network/user input inside a transaction.
- Ensure exception paths always roll back.
- Use transaction managers with proper lifecycle management.
- Set an appropriate `idle_in_transaction_session_timeout`.
- Set `application_name` to trace back to the service.

If you must terminate sessions, check rollback side effects first.

## 51. Monitoring and Alerting

Useful metrics:

- Oldest `backend_xmin` age.
- Oldest slot `xmin` and `catalog_xmin` ages.
- Slot inactive duration.
- WAL distance between `restart_lsn` and current WAL position.
- WAL directory size and free disk space.
- `age(datfrozenxid)`.
- `n_dead_tup` and relation growth.
- Autovacuum duration and count.
- Count of `idle in transaction` sessions.
- Prepared transaction age.
- Standby `backend_xmin` and replication lag.

### 51.1. Alert on Trends

A large value for a few seconds can be normal for a workload. A horizon stuck for hours or days alongside growing WAL and bloat is what deserves priority. Tune alert thresholds to match SLAs and cluster capacity.

## 52. Non-Destructive Remediation

A safe sequence is typically:

1. **Observe:** gather backend, slot, standby, and vacuum metrics.
2. **Attribute:** map PIDs/slots to application or consumer owners.
3. **Verify need:** is the transaction or slot still needed?
4. **Coordinate:** let the application commit/roll back or let the consumer resume.
5. **Controlled intervention:** terminate/drop/advance only after impact assessment.
6. **Vacuum:** let autovacuum or run manual VACUUM once the horizon advances.
7. **Re-measure:** dead tuples, relation size, WAL, and XID age.
8. **Prevent recurrence:** transaction timeouts, slot inventory, alerting, and ownership.

Never manually delete heap, TOAST, or WAL files.

## 53. Common Mistakes

### 53.1. Looking Only at n_dead_tup

It is an estimate and does not say which tuples are removable.

### 53.2. Thinking VACUUM Deletes Every Dead Tuple

VACUUM must respect the cleanup horizon.

### 53.3. Assuming idle in transaction Always Holds the Same Snapshot

Impact depends on isolation level and actual snapshot; check `backend_xmin`.

### 53.4. Neglecting Inactive Logical Slots

Inactive slots can still hold WAL, `xmin`, and `catalog_xmin`.

### 53.5. Checking Only restart_lsn

WAL retention differs from heap/catalog cleanup horizons.

### 53.6. Thinking max_slot_wal_keep_size Resolves xmin

It caps WAL retention; it does not replace checking tuple/catalog horizons.

### 53.7. Enabling hot_standby_feedback Without Tracking Bloat

Standby queries suffer fewer cancellations, yet the primary may retain versions longer.

### 53.8. Dropping a Slot Just Because active=false

The consumer may need the slot to resume CDC.

### 53.9. Advancing a Slot to "Unblock Vacuum"

Advancing can cause downstream to miss changes; it is not a vacuum command.

### 53.10. Reaching for VACUUM FULL First

It does not fix a pinned snapshot/slot horizon and carries high lock and disk costs.

### 53.11. Killing Backends Without Knowing Owners

Can roll back critical business transactions.

### 53.12. Disabling Anti-Wraparound Autovacuum

Creates the risk of the database becoming unable to accept writes safely.

### 53.13. Deleting WAL Files Manually

Can break recovery and replication.

### 53.14. Using Sequence IDs as Cleanup Checkpoints

Sequence allocation order does not equal commit order.

## 54. Checklist for DBAs

- Is any transaction holding an old `backend_xmin`?
- Are any `REPEATABLE READ`/`SERIALIZABLE` transactions lingering?
- Are any exported snapshots still open?
- Are there old prepared transactions?
- Are any replication slots inactive?
- Are slot `xmin`/`catalog_xmin` ages high?
- Is `restart_lsn` holding WAL too far back?
- Is standby feedback reporting an old `backend_xmin`?
- Is autovacuum running and advancing?
- Are database/table XID ages safe?
- Is disk/WAL/archive space sufficient?
- Are owners known for every slot and application session?
- Is there a consumer recovery plan before dropping/advancing a slot?
- Are metrics verified after releasing the horizon?

## 55. Practice Exercises

### Exercise 1 — MVCC

Why does PostgreSQL retain old row versions after an UPDATE?

**Hint:** older snapshots may need to read that version.

### Exercise 2 — Tuple xmin

What does `xmin` in the tuple header represent?

**Hint:** the XID that created that tuple version.

### Exercise 3 — backend_xmin

What does `pg_stat_activity.backend_xmin` represent?

**Hint:** the snapshot horizon held by the backend.

### Exercise 4 — Cleanup Horizon

Why can a dead tuple not yet be removable?

**Hint:** it is not older than the horizon required by snapshots/consumers.

### Exercise 5 — READ COMMITTED

At what scope is a snapshot typically taken in `READ COMMITTED`?

**Hint:** per statement.

### Exercise 6 — REPEATABLE READ

Why can a long `REPEATABLE READ` transaction pin the cleanup horizon?

**Hint:** one consistent snapshot across the entire transaction.

### Exercise 7 — Idle Transaction

Does `idle in transaction` always mean an old `backend_xmin`?

**Hint:** no; check isolation level and `backend_xmin`.

### Exercise 8 — Exported Snapshot

How long does an exported snapshot remain valid?

**Hint:** until the exporting transaction finishes.

### Exercise 9 — Prepared Transactions

Which view lists prepared transactions?

**Hint:** `pg_prepared_xacts`.

### Exercise 10 — VACUUM

Why does running VACUUM repeatedly not fix a pinned horizon?

**Hint:** it cannot delete versions that are still needed.

### Exercise 11 — Logical Slot

Which horizons can a logical slot hold?

**Hint:** `xmin` and `catalog_xmin`.

### Exercise 12 — restart_lsn

Which resource does `restart_lsn` relate to?

**Hint:** WAL retention.

### Exercise 13 — confirmed_flush_lsn

What does this field represent on a logical slot?

**Hint:** confirmed flush progress.

### Exercise 14 — Inactive Slot

Can an inactive slot still retain resources?

**Hint:** yes.

### Exercise 15 — catalog_xmin

Why is `catalog_xmin` important?

**Hint:** retains catalog versions needed for logical decoding.

### Exercise 16 — Physical Slot

What is the primary purpose of a physical slot?

**Hint:** retaining WAL for a physical standby.

### Exercise 17 — Hot Standby Feedback

What information does feedback send back to the primary?

**Hint:** `xmin` snapshot horizon.

### Exercise 18 — Trade-Off

Enabling `hot_standby_feedback` lowers which risk and raises which risk?

**Hint:** lowers standby query cancellations, raises primary bloat.

### Exercise 19 — pg_replication_slots

Write a query to inspect `slot_name`, `active`, `xmin`, and `restart_lsn`.

**Hint:** `pg_replication_slots`.

### Exercise 20 — pg_stat_replication

Which column lets you observe standby feedback `xmin`?

**Hint:** `backend_xmin`.

### Exercise 21 — Backend Diagnostics

Name three important columns in `pg_stat_activity`.

**Hint:** `xact_start`, `backend_xid`, `backend_xmin`.

### Exercise 22 — Dead Tuples

Is `n_dead_tup` an exact count of removable tuples?

**Hint:** no, it is an estimate.

### Exercise 23 — Vacuum Progress

Which view shows VACUUM phases and blocks?

**Hint:** `pg_stat_progress_vacuum`.

### Exercise 24 — XID Age

Write a query to check database `age(datfrozenxid)`.

**Hint:** `pg_database`.

### Exercise 25 — Wraparound

Why is vacuum freeze important?

**Hint:** prevents transaction ID wraparound.

### Exercise 26 — max_slot_wal_keep_size

Does this parameter cap WAL retention or cleanup `xmin`?

**Hint:** WAL retention.

### Exercise 27 — wal_keep_size

Distinguish `wal_keep_size` from a replication slot's `restart_lsn`.

**Hint:** minimum WAL retention setting vs. per-slot required position.

### Exercise 28 — Dropping a Slot

Why not drop a slot just because `active=false`?

**Hint:** the consumer may need to resume from the slot.

### Exercise 29 — Advancing a Slot

What consequence can advancing a logical slot cause?

**Hint:** downstream skips changes prior to the new position.

### Exercise 30 — Long Transaction Remediation

Should you ask the app to commit/roll back or terminate immediately?

**Hint:** identify owner/impact and prefer proper transaction lifecycle.

### Exercise 31 — Cancel vs. Terminate

Distinguish `pg_cancel_backend` from `pg_terminate_backend`.

**Hint:** cancels current query vs. terminates session/rolls back.

### Exercise 32 — VACUUM FULL

Why is it not the first remedy for a horizon blocker?

**Hint:** does not fix the root cause and requires heavy locks/rewrite.

### Exercise 33 — WAL Disk Growth

What issue can an inactive slot with an old `restart_lsn` cause?

**Hint:** retains WAL and grows `pg_wal`.

### Exercise 34 — Catalog Bloat

What can a slot with an old `catalog_xmin` retain?

**Hint:** catalog tuple versions.

### Exercise 35 — Replica Conflict

How can disabling `hot_standby_feedback` affect standby queries?

**Hint:** recovery conflicts can cancel queries.

### Exercise 36 — Monitoring

Name five metrics to track the vacuum horizon.

**Hint:** backend `xmin` age, slot `xmin`, `catalog_xmin`, `restart_lsn`, XID age, dead tuples.

### Exercise 37 — Transaction Snapshot Lab

Write a two-session experiment proving `REPEATABLE READ` sees the old row version.

**Hint:** A `BEGIN REPEATABLE READ`, B `UPDATE`, A re-runs `SELECT`.

### Exercise 38 — Consumer Outage

List the steps before dropping the slot of a stopped CDC connector.

**Hint:** verify owner/checkpoint/resnapshot/stop consumer.

### Exercise 39 — Anti-Wraparound

Should you disable autovacuum when XID age climbs high?

**Hint:** no.

### Exercise 40 — Root Cause

Bloat grows even though VACUUM runs regularly. List at least four sources that hold back the horizon.

**Hint:** long snapshot, logical slot, standby feedback, prepared xact, exported snapshot.

## 56. Frequently Asked Questions

### Is the cleanup horizon a timestamp?

No. It is a transaction visibility/XID boundary, not data age in days.

### Are dead tuples always deleted by VACUUM?

No. A tuple is removable only when no snapshot or consumer needs it and it is safe relative to the cleanup horizon.

### Why can a transaction not actively running queries still cause bloat?

If it holds an old snapshot (e.g., `REPEATABLE READ`) or relevant transaction state, VACUUM must retain needed versions. Check `backend_xmin` instead of looking only at `state`.

### Does READ COMMITTED hold a snapshot until the end of the transaction?

Normally snapshots are acquired per statement. Exact behavior also depends on cursors/statements/session context; do not infer solely from transaction age.

### Are inactive replication slots dangerous?

They can be. An inactive slot can still retain WAL as well as `xmin`/`catalog_xmin` horizons.

### Is restart_lsn the same as xmin?

No. `restart_lsn` is a WAL position; `xmin` is a transaction horizon for tuple retention.

### What is catalog_xmin used for?

Retaining catalog tuple versions needed for logical decoding.

### Does max_slot_wal_keep_size prevent heap bloat?

Not directly. It limits WAL retention; monitor `xmin` and `catalog_xmin` separately.

### Is hot_standby_feedback good or bad?

It is a trade-off. It reduces recovery conflicts and canceled standby queries, but can retain dead tuples longer on the primary.

### Can you drop every inactive slot?

No. Verify the consumer, checkpoint, and resnapshot capability first.

### Does pg_cancel_backend release a transaction?

It cancels the running query if possible; the transaction can remain open. Terminating the session ends the session and rolls back the transaction.

### Does VACUUM FULL advance the horizon?

It is not a fix for a transaction/slot holding an old snapshot. Clear the blocker first.

### Why doesn't the disk file shrink after VACUUM?

Standard VACUUM makes space reusable inside the relation. Shrinking the filesystem file requires a rewrite, such as `VACUUM FULL`, with its own lock and resource costs.

### Why monitor XID age?

To detect wraparound risk early before PostgreSQL restricts writes or forces emergency intervention.

## 57. Summary

Views and fields to remember:

~~~sql
-- Backend transactions and snapshots.
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    age(backend_xmin)
FROM pg_stat_activity
WHERE datname = current_database();

-- Replication slots and retention horizons.
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    age(xmin),
    catalog_xmin,
    age(catalog_xmin),
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;

-- Standby feedback on the primary.
SELECT
    application_name,
    backend_xmin,
    age(backend_xmin),
    replay_lsn
FROM pg_stat_replication;

-- Prepared transactions.
SELECT *
FROM pg_prepared_xacts;

-- Dead tuple estimates.
SELECT
    schemaname,
    relname,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;

-- XID age per database.
SELECT datname, age(datfrozenxid)
FROM pg_database
ORDER BY age(datfrozenxid) DESC;

-- Notification/replication is not directly relevant here;
-- use pg_stat_progress_vacuum to monitor running VACUUM.
SELECT * FROM pg_stat_progress_vacuum;
~~~

Key principles:

1. **VACUUM respects the cleanup horizon**; dead does not automatically mean removable.
2. **Long-running snapshots** can retain old row versions.
3. `backend_xmin` identifies the snapshot horizon; `backend_xid` is the backend transaction's XID.
4. `REPEATABLE READ`/`SERIALIZABLE` and exported snapshots can hold snapshots for long periods.
5. `idle in transaction` should be investigated by isolation level and actual snapshot, not `state` alone.
6. Abandoned prepared transactions hold locks/XIDs and block maintenance.
7. Logical replication slots can retain `xmin` and `catalog_xmin`.
8. `restart_lsn` retains WAL, distinct from the heap cleanup horizon.
9. Inactive slots can still retain resources.
10. `hot_standby_feedback` reduces standby recovery conflicts, yet can cause bloat on the primary.
11. `max_slot_wal_keep_size` caps WAL retention and does not replace monitoring `xmin`/`catalog_xmin`.
12. VACUUM can run without being able to clean up still-needed tuples.
13. Standard VACUUM does not shrink files; `VACUUM FULL` is a separate rewrite/lock operation.
14. XID age and freeze progress must be tracked to prevent wraparound.
15. Never drop/advance slots or terminate backends before verifying owner and impact.
16. After releasing the horizon, run or let VACUUM complete and re-measure.
17. Use transaction timeouts, `application_name`, slot inventories, and alerts to prevent recurrence.

Diagnostic flow:

~~~text
Dead tuples / storage / WAL growing
              |
              v
     Inspect VACUUM progress
              |
              v
   Old backend snapshot xmin?
        /           \
      Yes            No
      |               |
Find long         Check slots
transactions /    xmin/catalog_xmin
exported              |
snapshots /           v
prepared xacts   Standby feedback?
      |               |
      +-------+-------+
              |
              v
      Identify blocker owner
              |
              v
      Release under control
              |
              v
      VACUUM and monitor again
              |
              v
     Verify bloat and XID age
~~~

**Conclusion:** Long transactions, replication slots, and standby feedback can all pin PostgreSQL to an old cleanup horizon, leaving VACUUM unable to reclaim tuple versions the system must still protect. Accurate diagnosis inspects **`backend_xmin`, slot `xmin`/`catalog_xmin`, `restart_lsn`, standby feedback, prepared transactions, and XID age** together. Once you pinpoint what holds the horizon back, release it cleanly per application/replication lifecycle so VACUUM can safely reclaim space.
