# fsync, synchronous_commit, and Durability Trade-Offs in PostgreSQL

When PostgreSQL replies to an application that a transaction has **COMMITted successfully**, the application usually assumes the data has been persisted durably. However, that guarantee depends on how WAL is written, how the operating system and storage device handle flushes, and whether the system waits for a synchronous replica.

Two settings are frequently confused: **`fsync`** and **`synchronous_commit`**:

- `fsync` determines whether PostgreSQL asks the operating system to synchronize changes to storage at critical points to guarantee crash recoverability.
- `synchronous_commit` determines how far a transaction must wait before PostgreSQL confirms COMMIT: waiting for WAL to flush on the primary, waiting for a standby to write/flush WAL, or waiting for a standby to replay WAL; or returning without waiting for a local flush.

A third critical concept is the **checkpoint**. A checkpoint writes dirty data pages down to data files and establishes a redo point for crash recovery. However, a checkpoint is not a prerequisite for a transaction to be confirmed durable: PostgreSQL can confirm a commit once the WAL commit record is flushed, even while the corresponding data pages have not yet been written to data files. Upon a crash, PostgreSQL replays WAL to recover those pages.

```text
Application sends COMMIT
        |
        v
PostgreSQL creates WAL commit record
        |
        v
WAL written and flushed per durability policy
        |
        +---- synchronous_commit=off
        |       may reply before local WAL flush
        |
        +---- synchronous_commit=on
        |       waits for local WAL flush
        |       and standby flush if sync replication is configured
        |
        +---- remote_apply
                waits for synchronous standby to replay WAL
        |
        v
COMMIT confirmed to client
        |
        v
Data pages written to data files by checkpoint
        (may happen later)
```

This lesson belongs to the **WAL and checkpoints** chapter of the *Database Engine Relational PostgreSQL* module. The goal is to understand the boundary between "written," "flushed," "received by standby," and "applied by standby," so you can choose settings aligned with data-loss tolerance, latency, and availability requirements.

After this lesson, you will be able to:

1. Explain how WAL write, WAL flush, fsync, and data-page write differ.
2. Distinguish commit acknowledgement from checkpoints and crash recovery.
3. State the effects of `fsync`, `wal_sync_method`, and `full_page_writes`.
4. Compare `synchronous_commit` levels: `off`, `local`, `remote_write`, `on`, and `remote_apply`.
5. Understand the relationship between `synchronous_commit` and `synchronous_standby_names`.
6. Analyze cases where an acknowledged transaction can still be lost on a primary crash.
7. Understand group commit and why commit durability does not require flushing each transaction separately.
8. Select transaction-level overrides for reproducible data versus data that must never be lost.
9. Monitor WAL, checkpoints, replication lag, and wait events.
10. Plan testing, backups, failover, and storage hardening without blindly compromising durability.

> **Practice scope:** Commands that alter `fsync`, `synchronous_commit`, synchronous standby configuration, or simulate crashes are for lab environments only. Never turn off `fsync` on a production database holding data you need to preserve. Killing a process, resetting a VM, and losing power are different failure modes; testing must be designed deliberately.

---

## 1. What Does Durability Mean in ACID?

### 1.1. The Four ACID Properties

| Property | Meaning |
|---|---|
| Atomicity | A transaction is either applied completely or rolled back |
| Consistency | A valid transaction moves the database from one valid state to another valid state |
| Isolation | Concurrent transactions are coordinated according to isolation semantics |
| Durability | Once a commit is confirmed per the durability contract, its outcome is preserved across failures within that contract's scope |

Durability does not mean every data page is written to table files the instant an application receives COMMIT. PostgreSQL uses **Write-Ahead Logging (WAL)** so it can confirm a transaction once the required log is durably stored, and write data pages out at an appropriate time later.

### 1.2. Durability Must Specify a Failure Model

A system can claim durability under different assumptions:

- A PostgreSQL backend process crashes while the OS and storage keep running.
- The OS/kernel crashes or the host reboots unexpectedly.
- A power loss wipes out volatile write caches.
- A storage device or controller fails.
- The primary is lost completely and the system must promote a standby.
- An entire storage zone or availability zone is lost.

`fsync` and `synchronous_commit` primarily govern WAL synchronization on the primary and standbys. They do not replace backups, replication architecture, storage redundancy, or disaster recovery plans.

### 1.3. An Acknowledgement Is a Promise

When a client receives COMMIT success, the client typically does not know whether WAL flushed locally, whether a standby flushed it, or whether a standby replayed it. Applications must rely on PostgreSQL configuration and replication topology to understand that guarantee.

Never treat an application log saying "COMMIT successful" as independent proof that data reached durable hardware. It only shows the server returned success according to the active durability settings when the transaction ended.

---

## 2. WAL Write, WAL Flush, and Data-Page Write

### 2.1. What Is WAL?

WAL records the changes needed for PostgreSQL to recover the database after a crash. Instead of immediately writing every modified data page to data files before committing, PostgreSQL writes WAL records sequentially and ensures the corresponding WAL is persisted before the related data page is written.

That is the **write-ahead** principle:

> WAL describing a change must be durably persisted before the data page containing that change is written to storage.

### 2.2. Three Concepts

**WAL write**: WAL data is transferred from PostgreSQL WAL buffers to WAL files via OS write calls. This does not yet guarantee the data is safe across a power loss.

**WAL flush**: PostgreSQL asks the operating system to synchronize WAL up to a given LSN to storage via the selected sync method. When `fsync` is enabled and the OS/storage honors the contract, WAL up to that point is considered durable.

**Data-page write**: table/index pages are written out to data files. These pages can be written by backends, the background writer, or checkpoints after the transaction has already committed.

### 2.3. Illustration

```text
Transaction T updates account balance
                 |
                 v
          WAL records generated
                 |
                 v
          WAL buffer / WAL file
                 |
                 v
            WAL FLUSH
                 |
          COMMIT ACKNOWLEDGED
                 |
                 v
       Data page may still be dirty
                 |
                 v
       Checkpoint / background write
                 |
                 v
       Data file updated
```

If the server crashes after commit acknowledgement but before the data page is written, crash recovery reads WAL and replays the required changes. This is why PostgreSQL does not need to flush all data files on every COMMIT.

### 2.4. LSN

An LSN (Log Sequence Number) represents a position in the WAL stream. It tracks where WAL has been written, flushed, received, or replayed.

On the primary, you can view WAL positions:

```sql
SELECT
    pg_current_wal_lsn()        AS current_wal_lsn,
    pg_current_wal_insert_lsn() AS current_insert_lsn,
    pg_current_wal_flush_lsn()  AS current_flush_lsn;
```

These functions have distinct meanings:

- `pg_current_wal_insert_lsn()`: WAL position inserted so far.
- `pg_current_wal_lsn()`: current written WAL position per function semantics.
- `pg_current_wal_flush_lsn()`: WAL position flushed on the primary.

Do not compare LSNs like timestamps; to measure byte distance, use `pg_wal_lsn_diff(lsn1, lsn2)`.

### 2.5. Why Is WAL Flush Enough for Commit Durability?

WAL contains the information to recover changes. Once the commit record and needed WAL records are flushed, PostgreSQL can restore the transaction's state after a crash by replaying WAL, even if data files did not reflect that transaction yet.

This relies on `fsync` and the storage stack honoring flush requests. If hardware reports a flush succeeded while data actually sits in an unprotected volatile cache, durability guarantees can break underneath PostgreSQL.

---

## 3. A Checkpoint Is Not a Commit Flush

### 3.1. What Does a Checkpoint Do?

A checkpoint is a milestone in the WAL/recovery lifecycle. PostgreSQL writes eligible dirty buffers to data files and writes a checkpoint record so crash recovery knows where to start redoing.

Checkpoints help:

- Bound the amount of WAL needing replay after a crash.
- Allow older WAL segments to be recycled or handled per retention/archiving rules.
- Flush data pages to storage in batches.
- Pace write workload to avoid piling up heavy writes at the end of a checkpoint.

### 3.2. Must a Commit Wait for a Checkpoint?

Normally **no**. Under standard durability, a transaction only needs WAL flushed through its commit record per policy. Data pages are written to storage later.

Waiting for a checkpoint on every COMMIT would introduce massive write amplification and latency. WAL decouples transaction confirmation from flushing all data pages.

### 3.3. Crash Recovery

After a crash:

1. PostgreSQL locates the latest valid checkpoint.
2. Reads WAL from the required redo point.
3. Replays WAL records to bring data pages to a consistent state.
4. Finishes recovery before accepting normal connections.

Transactions with a durable commit record are recovered as committed; transactions without a valid commit record are handled as uncommitted under recovery rules.

### 3.4. Frequent Checkpoints and Full-Page Writes

Overly frequent checkpoints can increase the number of full-page images written into WAL when `full_page_writes` is enabled. This increases WAL volume and I/O. Overly infrequent checkpoints can lengthen crash recovery and retain more WAL.

This is a trade-off among:

- WAL generation.
- Checkpoint write load.
- Recovery time objective.
- Storage throughput.

### 3.5. Common Checkpoint Parameters

| Parameter | Role |
|---|---|
| `checkpoint_timeout` | Maximum time interval between scheduled checkpoints |
| `max_wal_size` | Soft WAL threshold that can trigger an early checkpoint |
| `min_wal_size` | Minimum WAL volume kept/recycled by segment management |
| `checkpoint_completion_target` | Target for spreading checkpoint writes across the checkpoint interval |
| `checkpoint_flush_after` | Coordinates flushing data files after a certain write volume |
| `full_page_writes` | Logs a full-page image on the first modification of a page after checkpoint, aiding torn-page recovery |

`max_wal_size` is not an absolute hard cap on WAL size in every scenario; archive lag, replication slots, or workload spikes can retain more WAL.

---

## 4. fsync: Protecting WAL and Data Files Against Crashes

### 4.1. What Is fsync?

`fsync` is an OS mechanism asking the system to sync written file data to storage. PostgreSQL uses appropriate sync methods to ensure WAL and critical files persist in the proper durability order.

In PostgreSQL:

```sql
SHOW fsync;
```

The default is `on`. For any database needing data preservation, keeping `fsync = on` is a fundamental rule.

### 4.2. fsync = on

With `fsync` enabled, PostgreSQL performs required file synchronization operations. Combined with the WAL protocol and storage honoring flush semantics, it protects the database against OS or host crashes.

`fsync` does not mean every row update invokes a separate fsync. PostgreSQL can batch WAL across multiple transactions using **group commit** to share flush cost.

### 4.3. fsync = off

With `fsync` disabled, PostgreSQL may skip requesting storage synchronization where needed. After an OS crash or power loss, the database can suffer **corruption unrecoverable by normal WAL alone**.

The risk is not merely "losing the last few transactions." Data files and WAL files can become mutually inconsistent, requiring a full cluster restore from backup.

### 4.4. synchronous_commit = on Cannot Save fsync = off

`synchronous_commit` controls whether transactions wait for flushes; `fsync` controls whether PostgreSQL actually issues the required sync calls.

If `fsync = off`, waiting under `synchronous_commit = on` yields no real durability guarantee. The server may acknowledge after writing to the OS cache while data still vanishes on a sudden power loss.

### 4.5. When Might fsync=off Appear?

PostgreSQL documentation notes certain workloads may consider disabling fsync when **recreating an entire cluster from a trusted data source** where the cluster can be discarded on failure—for example, loading a temporary benchmark database.

This is justified only when:

- Data is 100% reproducible.
- The cluster holds no unique authoritative data.
- Operators accept that the cluster may corrupt and require rebuilding.
- No other workload depends on that cluster.
- There is a plan to re-enable fsync and perform proper checkpointing/flushing before keeping data long-term.

Never treat `fsync=off` as a routine tuning option to speed up production.

### 4.6. fsync Cannot Fix Lying Hardware

PostgreSQL trusts the OS and storage devices to honor sync requests. If a storage controller or hypervisor reports flush success while data sits in volatile cache without battery or flash protection, durability can be lost.

Verify:

- Whether write caches have battery-backed or flash-backed protection.
- What durability semantics cloud block storage guarantees.
- Whether the hypervisor/virtual disk passes flushes/barriers properly.
- Whether RAID controllers and filesystems are configured safely.
- UPS and host power-loss behavior.

### 4.7. Privileges to Change

`fsync` is a server-level setting changeable only by a superuser. Never grant superuser to an application role allowing applications to alter durability arbitrarily.

---

## 5. wal_sync_method: How Does PostgreSQL Sync WAL?

### 5.1. Role

`wal_sync_method` selects the method PostgreSQL uses to ask the OS to sync WAL files. Options depend on OS and build:

- `fdatasync`.
- `fsync`.
- `fsync_writethrough` on some platforms.
- `open_datasync`.
- `open_sync` on some platforms.

Check current value:

```sql
SHOW wal_sync_method;
```

### 5.2. fdatasync and fsync

Conceptually:

- `fdatasync` requests syncing file data plus only the metadata required to read that data.
- `fsync` requests syncing data along with file metadata per OS semantics.

Performance and behavior differences depend on OS, filesystem, storage, and how PostgreSQL writes WAL. No single method is best on all hardware.

### 5.3. open_datasync / open_sync

Some operating systems allow opening files with sync flags so write calls carry synchronous semantics. Cost and effectiveness depend on implementation.

### 5.4. Do Not Guess by Name

`wal_sync_method` is not a "fastest" toggle. Use the `pg_test_fsync` tool shipped with PostgreSQL to measure sync methods on your specific filesystem and storage, then validate under a real workload.

### 5.5. Testing on the Host

In the PostgreSQL host shell:

```bash
pg_test_fsync --help
pg_test_fsync -f /path/to/test-file
```

This is an example of running the system utility; the test file path should point to a lab directory with adequate space and permissions. Never run heavy disk write tests on production during peak hours without planning.

### 5.6. pg_test_fsync Does Not Prove Full Durability

The tool benchmarks sync methods on a single file. It does not verify:

- That hardware will not fail.
- That a controller does not fake flushes.
- That replication/failover works properly.
- That backup restores succeed.
- That application workloads lack logic bugs.

It provides benchmark data for choosing a sync method, not a certification of end-to-end durability.

---

## 6. full_page_writes and Torn-Page Protection

### 6.1. What Is a Torn Page?

A PostgreSQL data page is often larger than the atomic write unit guaranteed by storage. If power fails during a page write, the file can end up with part old content and part new content: a **torn page**.

### 6.2. full_page_writes

When `full_page_writes` is enabled, PostgreSQL writes a full-page image into WAL the first time a page is modified after a checkpoint. If the data page gets torn during a write, recovery can use the full-page image to restore the page before replaying subsequent changes.

```sql
SHOW full_page_writes;
```

The default is typically `on`.

### 6.3. Does Not Replace fsync

`full_page_writes` and `fsync` address related yet distinct problems:

- `full_page_writes` lets recovery repair torn data pages.
- `fsync` ensures required file/WAL writes are requested to sync to storage.

Turning off fsync does not become safe merely because full_page_writes is on.

### 6.4. WAL Volume

Full-page images can substantially increase WAL volume after checkpoints, especially in workloads touching many pages. That is part of the cost paid for torn-page recoverability.

### 6.5. Data Checksums

Data checksums help detect page corruption when reading pages. They are a detection mechanism—they do not self-repair all damage and do not replace WAL, fsync, backups, or full-page writes.

---

## 7. What Does synchronous_commit Control?

### 7.1. Concept

`synchronous_commit` specifies how far PostgreSQL must wait before confirming a transaction commit succeeded.

Current value:

```sql
SHOW synchronous_commit;
```

The default is typically `on`.

### 7.2. Five Levels

| Value | Wait for local WAL flush? | Wait for synchronous standby? | Remote condition |
|---|---|---|---|
| `off` | Does not wait per commit | No | WAL will be flushed later by WAL writer or other transactions |
| `local` | Yes | No | Does not wait for standbys |
| `remote_write` | Yes | Yes | Waits for standby to write WAL to OS, not necessarily durable on storage |
| `on` | Yes | Yes | Waits for standby to flush WAL to durable storage |
| `remote_apply` | Yes | Yes | Waits for standby to replay/apply WAL so changes are readable on the standby |

Remote levels apply only when synchronous replication is appropriately configured. Without a configured synchronous standby, remote wait levels do not create a standby out of thin air; commits still follow local durability behavior.

### 7.3. off

`synchronous_commit = off` allows PostgreSQL to return COMMIT success before the transaction's WAL records are flushed to storage.

Consequences:

- Can reduce commit latency.
- Can increase throughput in workloads with many small transactions.
- If the OS/server crashes right after ACK, some recent transactions may be lost.
- The database still recovers to a consistent state via WAL; the main risk is **losing recently acknowledged transactions**, not ending up with a half-committed transaction logically because of async commit.

Per PostgreSQL documentation, the maximum delay between commit and guaranteed safety is bounded by the WAL writer cycle, roughly up to three times `wal_writer_delay`, and may be shorter under heavy load. This is a mechanism bound, not a rigid SLA across all setups and storage.

### 7.4. local

`synchronous_commit = local` waits for WAL flush on the primary, without waiting for synchronous standbys.

Useful when transactions must be durable on the primary before ACK, while avoiding tying latency or availability to synchronous replicas.

If the primary is lost completely before WAL replicates to a standby, the transaction may be missing on the promoted standby. Local durability does not equal HA durability.

### 7.5. remote_write

`remote_write` waits for the primary to flush WAL locally and for the synchronous standby to receive WAL and write it to the standby's OS. It does not wait for the standby to flush to durable storage.

If the standby OS crashes or loses power, WAL sitting only in volatile OS cache can be lost. Thus `remote_write` is stronger than mere network receipt, yet weaker than remote flush.

### 7.6. on

`synchronous_commit = on` is the default level:

- Primary waits for local WAL flush.
- If synchronous replication is configured, primary waits for flush acknowledgement from synchronous standbys per policy.
- If no synchronous standby is configured, it waits for local flush.

This is the common choice for commit durability on the primary paired with configured synchronous replication.

### 7.7. remote_apply

`remote_apply` waits for the synchronous standby to replay WAL records, not merely receive or flush them. Once commit is confirmed, the transaction has already been applied on that standby per replication semantics.

This is useful when applications read immediately after write from a synchronous standby and must ensure the transaction has been replayed there. It typically raises latency because the standby must receive, flush, and apply WAL.

### 7.8. Do Not Confuse remote_write with remote_apply

`remote_write` waits only for WAL to be written to the standby's OS; `remote_apply` waits for WAL to be replayed into database changes on the standby. For read-after-write on a standby, `remote_write` is not enough.

---

## 8. Choosing synchronous_commit by Requirement

| Requirement | Commonly Considered Level | Trade-Off |
|---|---|---|
| Acknowledged financial/order transactions must not be lost on primary crash | `on`; pair with sync replication if zero/low RPO failover is required | Latency and commit availability depend on sync standby |
| Only local primary durability needed; replication lag acceptable | `local`, or `on` without sync standbys configured | Failover to an async standby can lose unreplicated WAL |
| Need standby to have received and written to OS, without standby durable flush | `remote_write` | Weaker protection against standby crash/power loss |
| Need immediate reads from synchronous standby right after commit | `remote_apply` | Waiting for replay adds latency |
| Reproducible telemetry, caches, or staging | Consider `off` for specific transactions | Recently acknowledged commits can be lost on crash |
| Unique authoritative data that cannot be reconstructed | Never use `off`; keep fsync and proper policies | Pay in latency/throughput for durability |

This is a selection guide, not a substitute for analyzing RPO/RTO, replication topology, storage durability, and backups.

---

## 9. Synchronous Replication and synchronous_standby_names

### 9.1. Synchronous Commit Requires Designated Standbys

`synchronous_commit` does not automatically discover another server to replicate to. Synchronous replication requires configuring the primary to specify which standbys can confirm commits, typically via `synchronous_standby_names` and standby configuration.

### 9.2. FIRST Configuration Example

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

The primary waits for acknowledgement from one standby selected by priority order in the list. If the top-priority standby is unavailable, PostgreSQL can select the next eligible standby per the rules.

### 9.3. ANY Quorum Example

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

The primary waits for acknowledgements from any two synchronous standbys in the group. Quorum mode adds flexibility compared to pinning a single standby, though enough standbys must still respond.

### 9.4. sync_state Values

`pg_stat_replication` displays `sync_state`. Possible values include:

- `async`: asynchronous standby.
- `potential`: standby eligible to become synchronous per configuration/order.
- `sync`: standby currently acting as synchronous in FIRST mode.
- `quorum`: standby participating in a quorum group.

Never assume a row appearing in `pg_stat_replication` means that standby satisfies your synchronous commit policy.

### 9.5. What If the Synchronous Standby Disconnects?

If policy requires standby acknowledgement and no eligible standby is connected, transactions whose `synchronous_commit` waits for remote will **block at COMMIT** until a matching standby returns or configuration/operational action changes.

This is the availability trade-off:

- Waiting for a standby improves durability across failover.
- Waiting for a standby can stall write traffic when no eligible replica responds.

### 9.6. synchronous_commit=local

If transactions should still commit after local flush during a temporary sync standby outage, `local` skips the remote wait. However, failing over to an async standby that has not received the WAL can lose acknowledged transactions.

### 9.7. synchronous_commit=off

`off` skips waiting for local flush and skips waiting for synchronous standbys for that transaction. It can reduce latency, yet is weaker than `local` on durability.

### 9.8. remote_apply and Read Routing

`remote_apply` ensures the transaction has been replayed on the synchronous standby used to confirm the commit. However, the application must still route reads to the exact standby/replica covered by that synchronous policy; reading from a separate asynchronous replica can still observe stale data.

---

## 10. Group Commit: Multiple Transactions Sharing One Flush

### 10.1. Not Every COMMIT Triggers a Separate fsync

When multiple transactions commit close together, PostgreSQL can batch their WAL records and flush once for the group. This is **group commit**.

```text
Transaction A ---\
Transaction B ----+--> WAL flush to LSN X
Transaction C ---/          |
                            v
                    A, B, C acknowledged
```

This preserves durability without requiring a separate flush syscall per transaction.

### 10.2. WAL Flush Is the Synchronization Point

With `synchronous_commit = on`, a backend waits until the WAL flush position covers its transaction's commit record. If another transaction triggers a flush to a higher LSN, multiple commits can be confirmed together.

### 10.3. commit_delay and commit_siblings

`commit_delay` and `commit_siblings` add a short wait before WAL flush to create an opportunity to group more commits in certain workloads.

Do not tune them blindly:

- Too large a delay raises commit latency.
- Without enough concurrency, no group commit benefit occurs.
- Actual storage and workload dictate the payoff.

### 10.4. WAL Writer

The WAL writer background process writes and flushes WAL on a schedule, offloading backends in some cases. `wal_writer_delay` and `wal_writer_flush_after` tune related behavior.

For async commits, the WAL writer plays a central role in flushing WAL records that were not synced on individual commits.

### 10.5. Optimize at the Right Layer

If commit latency is high, identify the cause:

- Slow local WAL sync?
- Storage queue/latency?
- Synchronous replication lag?
- Slow standby apply?
- Network latency?
- Excessive WAL generation?
- Checkpoint I/O bursts?
- Transaction concurrency and lock contention?

Flipping `synchronous_commit=off` just to cut latency without understanding the bottleneck weakens durability without solving the real issue.

---

## 11. Overriding synchronous_commit per Transaction

### 11.1. SET LOCAL

`synchronous_commit` can be adjusted for the scope of a single transaction:

```sql
BEGIN;

SET LOCAL synchronous_commit = off;

INSERT INTO telemetry.events(event_type, payload)
VALUES ('page_view', '{"page":"home"}');

COMMIT;
```

This transaction does not wait for the usual WAL flush before returning commit acknowledgement. Once the transaction ends, the LOCAL value reverts.

### 11.2. Apply Only to Reproducible Data

Applications may consider async commit for:

- Telemetry or metrics where losing a small recent slice is acceptable.
- Rebuildable cache metadata.
- Staging rows backed by an external source of truth.
- Temporary analytics data that is not authoritative.

Do not apply it to:

- Account balances.
- Ledger/financial transactions.
- Confirmed payments.
- Customer-committed orders.
- State machines or workflows where an ACK triggers irreversible actions.

These are examples; decide based on business impact if an acknowledged transaction disappears after a crash.

### 11.3. SET LOCAL Must Be Inside a Transaction

Do not write:

```sql
SET LOCAL synchronous_commit = off;
INSERT INTO telemetry.events ...;
```

in autocommit mode expecting the setting to apply to the next INSERT. Always use an explicit `BEGIN`.

### 11.4. Session-Level SET

```sql
SET synchronous_commit = off;
```

sets the value for the session until changed, reset, or closed. With connection pooling, the setting can persist on a pooled physical connection and affect subsequent requests unless reset.

### 11.5. ALTER ROLE / ALTER DATABASE

You can set defaults:

```sql
ALTER ROLE telemetry_writer
SET synchronous_commit = off;
```

or:

```sql
ALTER DATABASE telemetry_db
SET synchronous_commit = off;
```

These set defaults for new sessions matching that scope; they do not modify already-open sessions. Review role memberships, database overrides, and connection pools before applying.

### 11.6. Critical Transactions Under an Async-Default Role

If a role or database defaults to `off` for telemetry yet occasionally runs a critical transaction, override it inside that transaction:

```sql
BEGIN;

SET LOCAL synchronous_commit = on;

INSERT INTO business.critical_events(event_id, payload)
VALUES (9001, '{"kind":"payment_confirmed"}');

COMMIT;
```

Never rely on application conventions without verifying the active value inside the transaction.

### 11.7. Do Not Mix Durability Policies Within One Business Unit

If a business operation spans multiple tables or transactions, decide durability at the business-unit level. If one part commits asynchronously while another commits durably, a crash can leave partial state the application never expected.

---

## 12. Failure Scenarios: Which Transactions Can Be Lost?

### 12.1. fsync=on, synchronous_commit=on, No Sync Standby

1. Transaction writes WAL.
2. PostgreSQL flushes WAL locally.
3. Server returns COMMIT success.
4. Host crashes.
5. Recovery replays flushed WAL.

Assuming storage honors flushes, acknowledged transactions are preserved on the primary.

### 12.2. fsync=on, synchronous_commit=off

1. Transaction writes WAL.
2. PostgreSQL returns COMMIT success before the transaction's WAL flushes.
3. Host loses power before the next flush.
4. Some recently acknowledged transactions may disappear after recovery.
5. The database still recovers to a consistent state from durable WAL.

This is **asynchronous commit**: it allows recent loss, not intentionally writing half-committed transactions.

### 12.3. fsync=off, synchronous_commit=on

1. Backend writes WAL to the OS.
2. Server may return COMMIT without true durable flush guarantees.
3. OS crash/power loss can cause lost or inconsistent files.
4. Data files/WAL can suffer corruption; recovery may be unable to repair it.

`synchronous_commit=on` cannot compensate for `fsync=off`.

### 12.4. Synchronous Replication with on

1. Primary generates WAL and sends it to the synchronous standby.
2. Primary flushes WAL locally.
3. Standby receives and flushes WAL as required.
4. Primary receives acknowledgement.
5. COMMIT returns to client.

If the primary fails after ACK, the confirming standby holds WAL through that transaction, reducing data loss risk on failover. Promotion timing and failover procedures must still ensure the right standby meeting policy is chosen.

### 12.5. remote_write

The standby wrote WAL to its OS without necessarily flushing durably. If the standby also loses power before data hits storage, the transaction may be missing on the standby despite being ACKed on the primary.

### 12.6. remote_apply

The standby has replayed WAL through the transaction. This lets queries read the transaction on that standby per replication semantics, yet does not replace backups or protect against replicated logical mistakes (like an accidental DELETE).

### 12.7. Asynchronous Replicas and Failover

With async replication, the primary can ACK a transaction before the standby receives WAL. If the primary is lost completely and the standby is promoted, acknowledged but unreplicated transactions can be lost.

`synchronous_commit=on` on the primary **does not automatically turn asynchronous replication into synchronous replication**.

---

## 13. Durability, Availability, and RPO/RTO

### 13.1. RPO

Recovery Point Objective (RPO) is the maximum data loss an organization tolerates during an incident.

Examples:

- Near-zero RPO for acknowledged transactions: requires sync replication/standby and matching storage guarantees for the failure model.
- RPO of a few seconds: async replication or async commit might be considered if the business accepts it.
- Larger RPO: periodic backups/archiving may suffice for reproducible data.

### 13.2. RTO

Recovery Time Objective (RTO) is the target time to restore service. Checkpoints, WAL volume, backup/restore speed, and failover orchestration drive RTO.

### 13.3. Local Durability Differs from Failover Durability

`fsync=on` and `synchronous_commit=on` without a synchronous standby protect transactions across a primary crash on the same storage, but do not preserve transactions if primary storage is destroyed and failover promotes an async replica.

### 13.4. Availability Trade-Off

Synchronous replication can block COMMITs if no synchronous standby responds. That strengthens durability for acknowledged transactions in the designed topology, while coupling write availability to replicas and network.

### 13.5. Backups Remain Essential

Replication copies logical mistakes and many forms of database/application-level corruption. Independent backups, WAL archiving, restore testing, and retention allow recovery from:

- Accidental data deletion.
- Ransomware or compromised credentials.
- Cluster or storage failure.
- Migration bugs.
- Replicated corruption.

---

## 14. synchronous_commit and synchronous_standby_names: Configuration Examples

### 14.1. Check Current Standbys

On the primary:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

If no rows return, no WAL sender connections currently appear in the view. That alone does not prove whether replication is configured properly or broken; check server/standby logs and configs.

### 14.2. Check Synchronous Standby Configuration

```sql
SHOW synchronous_standby_names;
SHOW synchronous_commit;
SHOW fsync;
```

### 14.3. FIRST 1

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

The primary waits for one eligible standby chosen by priority. Verify that each standby's `application_name` matches the configured names.

### 14.4. ANY Quorum

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

The primary waits for two acknowledgements from the quorum group. Quorum improves flexibility over pinning one standby, yet still requires enough standbys to respond.

### 14.5. synchronous_commit per Transaction

Even when synchronous standbys are configured, a transaction running:

```sql
SET LOCAL synchronous_commit = local;
```

waits only for local flush, skipping remote waits. Other transactions keeping `on` still wait per the synchronous replication policy.

### 14.6. Be Careful Changing Replication Configuration

Modifying `synchronous_standby_names` alters which standbys must acknowledge commits, impacting availability and commit latency. Follow operational procedures and verify `pg_stat_replication`, logs, and failover policies. Never change it in production just to "unblock hung queries" without understanding why SyncRep is waiting.

---

## 15. Checkpoints and Durability: Commonly Misattributed Parameters

### 15.1. checkpoint_timeout

Caps the maximum interval between scheduled checkpoints. Checkpoints can also be triggered by WAL volume or other conditions.

### 15.2. max_wal_size

Soft threshold for WAL volume before requesting an early checkpoint. It is not an "absolute maximum WAL size"; replication slots and archive backlogs can retain much more WAL.

### 15.3. checkpoint_completion_target

Controls the target spread of checkpoint writes across the checkpoint interval to avoid I/O bursts at the end. Too low concentrates writes; too high must be evaluated against checkpoint spacing and storage speed.

### 15.4. checkpoint_flush_after

Can prompt the OS to flush dirty pages incrementally rather than letting huge dirty buffers accumulate. Impact depends on OS, filesystem, and workload.

### 15.5. Do Not Use Checkpoints to Substitute for synchronous_commit

Raising checkpoint frequency does not make `synchronous_commit=off` durable-at-ack. Lowering checkpoint frequency does not strip `synchronous_commit=on` of its local WAL flush guarantee when fsync and storage work properly.

The two mechanisms serve different purposes:

- `synchronous_commit`: transaction ACK timing.
- Checkpoint: dirty data pages and redo/recovery boundary.

---

## 16. WAL Writer, commit_delay, and Performance

### 16.1. wal_writer_delay

`wal_writer_delay` sets the cycle interval at which the WAL writer wakes to write/flush WAL on schedule. It relates to the safety window of async commits, though it is not a fixed latency guarantee.

### 16.2. wal_writer_flush_after

Controls how much WAL the WAL writer writes before triggering a threshold flush. This affects I/O behavior and should be benchmarked in a real environment.

### 16.3. commit_delay

`commit_delay` introduces a brief microsecond pause before flushing WAL to increase group commit opportunities. An ill-suited value simply slows COMMITs down.

### 16.4. commit_siblings

`commit_siblings` sets the minimum number of concurrent active transactions required before `commit_delay` engages.

### 16.5. Never Optimize a Single Metric

Measure:

- Commit p50/p95/p99.
- WAL sync count/time.
- WAL write count/time.
- WAL bytes per transaction.
- Replication flush/replay lag.
- Checkpoint duration and buffers written.
- Storage latency/queue depth.
- Transaction throughput and error rate.

A configuration that lowers median latency while hurting tail latency or losing data on failover is a worse configuration.

---

## 17. Monitoring WAL and Flushes

### 17.1. pg_stat_wal

```sql
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
```

This view gives instance-wide WAL statistics. If `track_wal_io_timing` is off or the platform does not support timing, timing columns may not capture latency accurately.

### 17.2. Timing Counters

`wal_write_time` and `wal_sync_time` accumulate duration when appropriate tracking is enabled. To compute averages, take deltas between two snapshots over an interval rather than looking only at cumulative totals since stats reset.

### 17.3. pg_stat_replication

```sql
SELECT
    application_name,
    state,
    sync_state,
    pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn)
        AS bytes_not_written_on_standby,
    pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn)
        AS bytes_not_flushed_on_standby,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)
        AS bytes_not_replayed_on_standby
FROM pg_stat_replication;
```

These subtractions estimate LSN distances relative to current primary WAL. Under continuous writes, values shift mid-query; interpret alongside sample time and state.

### 17.4. Wait Events

Inspect waiting sessions:

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE wait_event IN ('WALWrite', 'WALSync', 'SyncRep')
ORDER BY query_start;
```

General meanings:

- `WALWrite`: waiting on WAL write operation.
- `WALSync`: waiting on WAL sync/flush.
- `SyncRep`: waiting on synchronous replication acknowledgement.

Wait event names and details can change across PostgreSQL versions. Check docs for your running version.

### 17.5. Checkpoint Statistics

Checkpoint info appears in statistics views whose names and structures differ across major versions. On newer versions, check `pg_stat_checkpointer`; on older versions, some checkpoint counters reside in `pg_stat_bgwriter`.

Never copy a monitoring query from another version without verifying the view schema.

### 17.6. Do Not Conclude from a Single Snapshot

A single reading of `wal_sync_time` or `flush_lag` is not enough to diagnose performance. Always:

1. Capture a baseline before changes.
2. Measure deltas under equivalent workloads.
3. Separate primary flush latency from standby flush/replay latency.
4. Correlate commit p95/p99 with storage/network metrics.
5. Record configuration and stats reset times.

---

## 18. Controlled Durability Experiments

### 18.1. Create the Lab Table

```sql
CREATE SCHEMA durability_lab;

CREATE TABLE durability_lab.commit_probe (
    probe_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

### 18.2. Inspect Current Configuration

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'fsync',
    'synchronous_commit',
    'wal_sync_method',
    'full_page_writes',
    'wal_writer_delay',
    'wal_writer_flush_after',
    'checkpoint_timeout',
    'max_wal_size',
    'checkpoint_completion_target'
)
ORDER BY name;
```

`pg_settings` shows the active setting, context, and source. Do not alter settings merely because a lab environment shows different results.

### 18.3. Transaction with synchronous_commit on

```sql
BEGIN;

SET LOCAL synchronous_commit = on;

INSERT INTO durability_lab.commit_probe(label)
VALUES ('durable-policy-example');

COMMIT;
```

With `fsync=on` and honest storage flushes, COMMIT waits for local WAL flush. If synchronous replication is configured, it also waits for synchronous standbys per policy.

### 18.4. Transaction with synchronous_commit off

```sql
BEGIN;

SET LOCAL synchronous_commit = off;

INSERT INTO durability_lab.commit_probe(label)
VALUES ('async-commit-example');

COMMIT;
```

The transaction can be acknowledged before its WAL is flushed. Never deliberately power off a database holding important data to test this; run failure injection only in disposable VMs/labs with backups and recovery plans.

### 18.5. Read Back the Data

```sql
SELECT probe_id, label, created_at
FROM durability_lab.commit_probe
ORDER BY probe_id;
```

Reading immediately after commit proves the transaction is present in the live database; it does not prove the transaction would survive all failure modes.

### 18.6. Durability Cannot Be Proven by SELECT Alone

A query immediately after COMMIT cannot verify:

- Whether WAL truly flushed to physical storage.
- Whether a controller hides an unprotected volatile cache.
- Whether an async replica received the WAL.
- Which standby failover will pick.
- Whether backup restores actually work.

Durability is a property of the entire stack and failure model.

---

## 19. Testing Storage and the System

### 19.1. pg_test_fsync

`pg_test_fsync` measures sync methods on a test file. Use it to compare relative costs on a specific filesystem.

### 19.2. Realistic Workload Benchmarks

A benchmark should approximate:

- Realistic WAL record sizes.
- Transactions per second.
- Commit/rollback ratios.
- Concurrent client counts.
- Sync replication topology.
- Storage latency and cache behavior.

A microbenchmark writing a single file does not fully represent production.

### 19.3. Crash Recovery Tests

Testing should distinguish:

- Backend process termination.
- Unclean PostgreSQL server shutdown.
- OS crash / VM reset.
- Storage fault / power-loss simulation.
- Primary failover to a standby.

Never `kill -9` a single backend and claim you tested power loss; a backend crash does not reproduce OS or storage failures.

### 19.4. Restore Tests

Backups are trustworthy only once restores are tested:

- Restore a base backup.
- Replay archived WAL to a target point.
- Verify consistency and application reads.
- Measure recovery time.

### 19.5. Failover Tests

With synchronous replication:

- Verify which standby is active as synchronous.
- Commit a marker on the primary.
- Wait for acknowledgement.
- Simulate primary failure in a lab environment.
- Promote the standby per procedure.
- Verify the marker and transaction ordering.

Do not assume from `synchronous_standby_names` that failover automation automatically promotes the right node; the failover manager and operator policies are also part of the system.

---

## 20. Operating fsync and Configuration Changes

### 20.1. Check Before Changing

Record:

- `SHOW fsync`.
- `SHOW synchronous_commit`.
- `SHOW wal_sync_method`.
- `SHOW synchronous_standby_names`.
- `SHOW full_page_writes`.
- PostgreSQL major version.
- Storage class, filesystem, and controller semantics.
- Backup/WAL archive status.
- Replication topology and failover policy.

### 20.2. Never Use SET LOCAL to Disable fsync

`fsync` is a server-level setting, not a transaction-level toggle like `synchronous_commit`. You cannot safely toggle fsync per request as an optimization.

### 20.3. Vary synchronous_commit by Workload

When async commit is needed for a specific workload, prefer transaction-level `SET LOCAL` after verifying the data is safe to lose. Restrict role/database-level defaults to avoid unintended side effects.

### 20.4. When Changing synchronous_standby_names

This alters durability topology. Verify:

- `application_name` values on standbys.
- Enough standbys available for FIRST/ANY rules.
- Replication state and lag.
- Behavior if standbys disconnect.
- Failover and promotion procedures.

### 20.5. When Changing wal_sync_method

Change it only after measuring with `pg_test_fsync` and realistic workload benchmarks. Keep the default unless clear evidence shows another method performs better without sacrificing safety.

---

## 21. Application Scenarios Requiring Durability Decisions

### 21.1. Payment Authorization

A system that returns "payment succeeded" to a customer generally requires acknowledged transactions to survive. `synchronous_commit=off` could let the app report success only for the transaction to vanish after a crash.

Design must define:

- When to return success responses.
- When to call external payment gateways/partners.
- Whether idempotency keys are present.
- How recovery/failover handles primary crashes right after commit.
- Whether replication is synchronous.

### 21.2. Telemetry and Metrics

Losing a few recent metric points may not cause business inaccuracy. This is where transaction-level async commit can be considered, provided downstream consumers accept data loss and metrics are not a source of truth.

### 21.3. Job Queues

If a transaction inserts a job and the app acknowledges enqueueing to a caller, losing the job on crash can mean work never runs. Choose matching durability or implement producer retries/reconciliation.

### 21.4. Cache Metadata

If caches can be rebuilt from a source of truth, async commit may fit. However, if a cache holds unique state or governs authorization, it is no longer disposable rebuildable cache.

### 21.5. Audit Logs

Audit logs may serve as compliance or forensic evidence. Never classify them as "safe to lose" just because they are logs. Verify retention, regulatory requirements, and failure contracts before selecting `off`.

---

## 22. Common Misconceptions

**1. "COMMIT success means all data pages were written to data files."** False. Flushing WAL suffices for commit durability; checkpoints write data pages later.

**2. "Checkpoints are when transactions become durable."** False. Checkpoints and commit acknowledgements are two separate mechanisms.

**3. "fsync=on calls fsync once per transaction."** Not necessarily. Group commit batches multiple transactions into a single flush.

**4. "synchronous_commit=on automatically guarantees zero data loss on failover."** Not without an eligible synchronous standby; otherwise it still guarantees only local flush.

**5. "fsync=off only loses the last few transactions."** False. It can cause corruption requiring a full cluster restore.

**6. "synchronous_commit=on compensates for fsync=off."** False. Without proper sync requests, waiting at commit gives no true durability.

**7. "synchronous_commit=off makes transactions non-atomic."** False. It relaxes durability at acknowledgement time; transactions remain atomic under transaction semantics.

**8. "off can wipe out all data in the database."** Not in normal async commit semantics; the risk is losing recent unflushed transactions. The database still recovers consistently, assuming fsync stays on.

**9. "local is identical to on."** Not when synchronous replication is active; `local` skips waiting for remote standbys.

**10. "remote_write means the standby flushed durably to storage."** False. It waits for writing to the standby's OS, not durable storage flush.

**11. "on means the standby has replayed the transaction."** False. `on` waits for standby flush; `remote_apply` waits for replay.

**12. "remote_apply makes every replica able to read the transaction."** False. It applies to the selected synchronous standby(s); other async replicas may still lag.

**13. "Setting synchronous_standby_names forces all commits to wait for replicas."** It still depends on each transaction's `synchronous_commit` value.

**14. "Without a synchronous standby, setting remote_apply makes PostgreSQL find a replica automatically."** False. Synchronous replication and matching standbys must be configured.

**15. "Synchronous replication always improves availability."** False. If no eligible standby responds, commits can block.

**16. "Async replication plus synchronous_commit=on gives RPO=0."** False. Without a synchronous standby, `on` only waits for local WAL flush.

**17. "remote_write is safe against standby power loss."** Not necessarily; volatile OS cache can be lost.

**18. "remote_apply replaces backups."** False. It also replicates logical mistakes and accidental deletes.

**19. "full_page_writes replaces fsync."** False.

**20. "Data checksums automatically repair corruption."** False; they detect page corruption.

**21. "Whichever wal_sync_method has fsync in its name is best."** False. It depends on OS, filesystem, and storage.

**22. "pg_test_fsync proves storage cannot lose data."** False. It measures sync cost, not hardware durability guarantees.

**23. "Increasing checkpoint frequency makes commits safer."** Not directly; commit durability relies on the WAL flush policy.

**24. "Lowering max_wal_size always reduces write latency."** False; checkpoint frequency and write pressure may shift unfavorably.

**25. "WAL writer delay is the exact data-loss window."** False; it is one part of the mechanism, and workload or other flushes can shorten the window.

**26. "SET LOCAL synchronous_commit outside a transaction applies to the next statement."** False.

**27. "ALTER ROLE SET immediately alters open sessions."** False; it sets defaults for new sessions following configuration precedence.

**28. "A locally durable COMMIT ACK is guaranteed to exist on async standbys."** False.

**29. "A standby listed in pg_stat_replication is definitely synchronous."** False; check `sync_state` and policy.

**30. "sync_state=sync guarantees the failover manager always promotes the right node."** False; failover orchestration must be verified independently.

**31. "Killing a backend tests power loss."** False. OS/storage failures differ from backend process crashes.

**32. "Having backups means fsync can be disabled."** False. Backups do not prevent live cluster corruption or guarantee fast recovery.

---

## 23. Practice Exercises and Answers

### Exercise 1 — Distinguishing WAL and Data Pages

**Question:** Why can PostgreSQL return COMMIT before data pages are written to data files?

**Answer:** If WAL through the commit record has been flushed per durability policy, crash recovery can replay WAL to restore the data pages after a crash.

### Exercise 2 — Checkpoint

**Question:** Is a checkpoint a prerequisite for every COMMIT to be acknowledged?

**Answer:** No. Checkpoints write dirty data pages and set a redo point; normal commit durability relies on WAL flushing.

### Exercise 3 — fsync

**Question:** What does `fsync=on` protect?

**Answer:** It requests that the OS synchronize required file changes to storage to support crash recovery under durability assumptions.

### Exercise 4 — fsync=off

**Question:** Why can `fsync=off` cause corruption instead of just losing a few commits?

**Answer:** WAL and data files may not sync in the required order/guarantees; after an OS crash or power loss, the cluster can become inconsistent and unrecoverable via WAL.

### Exercise 5 — synchronous_commit=off

**Question:** What can happen after an `off` transaction is acknowledged and power fails immediately?

**Answer:** Some recent unflushed transactions may be lost after recovery, though the database still recovers consistently if fsync and storage work properly.

### Exercise 6 — local

**Question:** What does `local` wait for?

**Answer:** Local WAL flush on the primary, without waiting for synchronous standbys.

### Exercise 7 — remote_write

**Question:** Does `remote_write` mean the standby is durable on storage?

**Answer:** No. It waits for the standby to write WAL to its OS, not necessarily flush to durable media.

### Exercise 8 — on

**Question:** With a synchronous standby configured, what does `on` wait for?

**Answer:** Local WAL flush and flush acknowledgement from synchronous standbys per replication policy.

### Exercise 9 — remote_apply

**Question:** How does `remote_apply` differ from `on`?

**Answer:** It waits for the standby to replay/apply WAL, not merely flush it.

### Exercise 10 — No Standby

**Question:** Does `synchronous_commit=on` provide remote durability when no synchronous standby exists?

**Answer:** No. It waits for local flush.

### Exercise 11 — Sync Standby Disconnected

**Question:** If policy requires a synchronous standby and none responds, what happens to commits?

**Answer:** Transactions block at commit until an eligible standby returns or policy/config changes.

### Exercise 12 — Quorum

**Task:** Write a configuration waiting for two out of three standbys.

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

### Exercise 13 — FIRST

**Task:** Write a configuration selecting one standby by priority.

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

### Exercise 14 — SET LOCAL

**Task:** Run a telemetry transaction using async commit.

```sql
BEGIN;
SET LOCAL synchronous_commit = off;
INSERT INTO telemetry.events(event_type) VALUES ('view');
COMMIT;
```

### Exercise 15 — SET LOCAL Outside a Transaction

**Question:** Why is `BEGIN` required?

**Answer:** `SET LOCAL` is transaction-scoped; if run in autocommit, its scope ends right after that single statement.

### Exercise 16 — full_page_writes

**Question:** What does `full_page_writes` protect against?

**Answer:** Assists recovery of torn data pages via full-page images in WAL on the first page modification after a checkpoint.

### Exercise 17 — full_page_writes and fsync

**Question:** Can `fsync` be disabled if `full_page_writes=on`?

**Answer:** No. The two mechanisms serve different roles.

### Exercise 18 — Group Commit

**Question:** Why can multiple commits share a single WAL flush?

**Answer:** PostgreSQL flushes WAL up to an LSN covering commit records of multiple transactions; waiting backends can be woken together.

### Exercise 19 — wal_sync_method

**Question:** Which tool measures WAL sync methods on storage?

**Answer:** `pg_test_fsync`, followed by realistic workload benchmarking.

### Exercise 20 — LSN

**Task:** View current and flush LSNs.

```sql
SELECT pg_current_wal_lsn(), pg_current_wal_flush_lsn();
```

### Exercise 21 — pg_stat_wal

**Task:** View WAL writes/syncs.

```sql
SELECT wal_write, wal_sync, wal_write_time, wal_sync_time
FROM pg_stat_wal;
```

### Exercise 22 — Replication Lag

**Task:** View sync state and replay lag.

```sql
SELECT application_name, state, sync_state, replay_lag
FROM pg_stat_replication;
```

### Exercise 23 — Wait Events

**Question:** What does the `SyncRep` wait event typically indicate?

**Answer:** A backend is waiting on synchronous replication acknowledgement.

### Exercise 24 — Checkpoint Parameters

**Question:** Is `max_wal_size` an absolute hard cap on the WAL directory?

**Answer:** No. Replication slots, archive backlogs, and other conditions can retain more WAL.

### Exercise 25 — RPO

**Question:** What does RPO measure?

**Answer:** The maximum data loss an organization tolerates in an incident.

### Exercise 26 — RTO

**Question:** What does RTO measure?

**Answer:** Target duration to restore the service/database.

### Exercise 27 — Async Replica

**Question:** Does `synchronous_commit=on` on the primary guarantee an async standby holds an acknowledged transaction?

**Answer:** No. `on` waits remotely only if synchronous replication is configured for that standby.

### Exercise 28 — remote_apply and Read-After-Write

**Question:** Why is `remote_apply` helpful when reading from a synchronous standby?

**Answer:** Because commit is acknowledged only after that standby replays the transaction per policy, so the changes are already applied there.

### Exercise 29 — Backups

**Question:** Does synchronous replication replace backups?

**Answer:** No. Replication propagates logical mistakes and accidental deletes; backups and restore tests are required.

### Exercise 30 — Failure Testing

**Question:** Does killing a PostgreSQL backend prove durability against power loss?

**Answer:** No. Backend process failure does not simulate OS crashes, controller caches, or power loss.

---

## 24. Checklist for Selecting and Operating a Durability Policy

### Business Requirements

1. Define which transactions must never be lost after ACK.
2. Define RPO/RTO for primary failures and site failures.
3. Classify source-of-truth data, reproducible data, and telemetry.
4. Determine when the application sends responses or calls external systems.
5. Define idempotency/retry semantics for ambiguous commit outcomes.

### PostgreSQL

6. Keep `fsync=on` for databases needing data preservation.
7. Verify active `synchronous_commit` at session/transaction level.
8. Do not confuse local durability with synchronous replication durability.
9. Understand how `remote_write`, `on`, and `remote_apply` differ.
10. Keep `full_page_writes` at its recommended default unless backed by clear technical grounds.
11. Understand `wal_sync_method` and benchmark before changing.
12. Understand checkpoints are not per-commit ACK prerequisites.

### Replication and Storage

13. Verify `synchronous_standby_names` and `application_name`.
14. Monitor `sync_state` and write/flush/replay LSNs.
15. Know system behavior when standbys are unavailable.
16. Verify storage cache and flush semantics.
17. Audit filesystem, controller, hypervisor, and cloud storage layers.
18. Maintain independent backups and WAL archives.
19. Execute restore and failover drills.

### Performance and Monitoring

20. Monitor `pg_stat_wal`.
21. Monitor replication lag and `SyncRep` waits.
22. Monitor checkpoint stats matching your PostgreSQL version.
23. Measure commit p95/p99, not just averages.
24. Benchmark with realistic workloads and concurrency.
25. Adjust group commit or WAL writer settings only after capturing a baseline.

### Async Commit

26. Use `synchronous_commit=off` only for data tolerant of recent loss.
27. Prefer transaction-scoped `SET LOCAL`.
28. Never set `off` at role/database default without evaluating all callers.
29. Ensure business transactions do not mix critical data and async commits inconsistently.
30. Document the policy, approver, and failure contract.

---

## 25. Summary

PostgreSQL durability relies on WAL and file synchronization mechanisms. **WAL flush** lets PostgreSQL confirm commits before data pages are written to data files; **checkpoints** write dirty pages and set recovery boundaries. These two activities are closely linked yet are not the same event.

Key points to remember:

- `fsync=on` is fundamental for requesting OS synchronization of WAL and data files per durability protocol. Disabling it risks corruption after an OS crash or power loss.
- `synchronous_commit` controls ACK timing: `off` skips local flush waits; `local` waits for local flush; `remote_write` waits for standby OS write; `on` waits for standby flush if sync replication is configured; `remote_apply` waits for standby replay.
- `synchronous_commit=on` does not create HA durability without a synchronous standby.
- Synchronous replication improves transaction survival across failovers per policy, yet can block commits when no standby responds.
- Group commit lets multiple transactions share one WAL flush, so durability does not mean one fsync syscall per COMMIT.
- `full_page_writes` aids torn-page recovery; it does not replace `fsync`.
- Async commit suits reproducible or recent-loss-tolerant data per business approval; confine it via `SET LOCAL`.
- Backups, WAL archives, restore tests, storage guarantees, and failover drills remain indispensable.

**Self-check question:** If an API returns "payment succeeded" after COMMIT, what must hold true so that the transaction is not lost if the primary crashes? You must verify local WAL flush, `fsync`, synchronous standby policy, standby flush/replay state, and storage failure behavior. Seeing COMMIT success or a recent checkpoint alone is not enough to prove the full guarantee.

### Official PostgreSQL Documentation

- [WAL Configuration — fsync, synchronous_commit, wal_sync_method, full_page_writes](https://www.postgresql.org/docs/current/runtime-config-wal.html).
- [WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html).
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html).
- [WAL — Write-Ahead Logging](https://www.postgresql.org/docs/current/wal.html).
- [WAL Configuration — Checkpoints](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-CHECKPOINTS).
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION).
- [Replication Configuration — synchronous_standby_names](https://www.postgresql.org/docs/current/runtime-config-replication.html).
- [Monitoring Statistics — pg_stat_wal and replication views](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [pg_test_fsync](https://www.postgresql.org/docs/current/pgtestfsync.html).
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html).
