# Backup Consistency While the System Is Actively Writing

A MongoDB system serving orders, e-wallets, telemetry, or transactional data usually **cannot halt all requests** just to take a backup. While the backup tool reads the first collection, the application may still insert, update, delete, commit transactions, modify indexes, or run migrations. During a restore, what matters is not merely **having a backup file**, but whether that file represents a **valid data state at a well-defined point in time**.

For example, suppose an application transfers 200,000 VND from wallet A to wallet B. If the backup captures **wallet A's balance after debiting** but **wallet B's balance before crediting**, the system's total balance can be wrong after restore — even though every BSON file is readable and both collections contain all documents. This is an example of a **point-in-time inconsistent backup**.

The goal of the lesson **"Backup Consistency While the System Is Actively Writing"** in the **Backup and Recovery** chapter, *Database Engine Document MongoDB* module, is to understand:

1. What **consistency** means in backups, how it differs from "finished copying," and how it differs from **RPO/RTO**.
2. Why scanning multiple documents/collections while writes continue easily produces a dump that **does not correspond to any single point in time**.
3. When to use **`mongodump --oplog`**, **filesystem snapshots**, or **Atlas/Cloud Manager/Ops Manager managed backups**.
4. The roles of **oplog, journal, WiredTiger checkpoints, write concern, read concern, snapshot reads, and replication lag**, along with each mechanism's limitations.
5. Why a **sharded cluster** is more complex than a replica set and why per-shard dumps cannot be arbitrarily stitched together.
6. How to design **backup/restore runbooks, PITR, oplog window monitoring, and post-restore invariant checks**, along with scenario exercises.

> **Scope:** Shell examples run on a **prepared and authorized lab/DR environment**. Never run restore commands, stop the balancer, lock writes, drop data, or reset a replica set on production just to test a lesson. Syntax and limits vary by MongoDB Server, Database Tools, and Atlas versions; official documentation is linked at the end.

## 1. "Consistency" Has Multiple Layers, Not Just a Backup Flag

### 1.1. Three Concepts to Separate

| Concept | Meaning | Example |
|---|---|---|
| **File/format integrity** | The backup is readable, without truncation, missing pieces, or checksum errors. | `backup.archive` restores valid BSON. |
| **Database point-in-time consistency** | The dataset reflects a valid MongoDB state at **one shared logical timestamp**; no half-committed transactions are visible. | Wallet A and wallet B are both before or both after the transfer transaction. |
| **Application/business consistency** | Business rules hold, including data outside MongoDB if included in scope. | Payments, bookings, and Kafka events align at the same cutover. |

**A valid file does not mean consistent data.** A byte-complete dump file can still combine collection A at 10:00:03 with collection B at 10:00:40. Conversely, a consistent backup at 10:00 may still be **stale** relative to events at 10:05; that is an **RPO** issue, not a consistency bug.

### 1.2. Point-in-Time Consistency

Suppose MongoDB receives:

~~~text
10:00:00  Orders count = 100; Payments count = 100
10:00:02  Transaction T creates order + payment atomically
10:00:03  Orders count = 101; Payments count = 101
~~~

A valid **point-in-time consistent** backup may represent:

- **Before transaction T:** Orders=100 and Payments=100.
- **After transaction T:** Orders=101 and Payments=101.

However, it must never become **Orders=101, Payments=100** from sampling two different timestamps. This is a severe issue even if each individual collection looks error-free.

### 1.3. Write-Time Atomicity Does Not Automatically Protect Backups

MongoDB supports **single-document atomicity** and multi-document transactions when properly implemented. That protects live operations against the running database. However, a **sequential reader** without a consistent snapshot boundary can see the first collection after T and the second before T.

**Application transactions and backup snapshot consistency are two separate mechanisms.** You cannot conclude that "because the app uses MongoDB transactions, a plain `mongodump` is definitely consistent."

### 1.4. Distinguishing Crash-Consistent vs. Application-Consistent

| Term | Description | What Is Not Guaranteed |
|---|---|---|
| **Crash-consistent snapshot** | A data image like after an abrupt server halt, recoverable via journal/WiredTiger if all required components are captured. | Not necessarily synchronized across multiple nodes/shards or external queues. |
| **Database-consistent point-in-time backup** | Post-recovery data sits at a common logical point respecting write ordering/transaction semantics. | Does not automatically cover Kafka, object storage, or payment gateways. |
| **Application-consistent backup** | Coordinated around business invariants, potentially involving quiesce/markers/outbox and external systems. | Depends on application scope, not just a MongoDB command. |

The word "snapshot" can refer to an **OS filesystem snapshot**, **MongoDB readConcern snapshot**, **Atlas managed snapshot**, or **VM/cloud disk snapshot**. These do not inherently share the same guarantees.

## 2. Timeline Diagram: Read Anomalies While Actively Writing

### 2.1. Dumping Two Collections Sequentially

~~~text
Timeline:

             10:00        10:02          10:04       10:06
              |             |              |           |
mongodump:    [read accounts]              [read ledger]
                            |
app write:                  [commit transaction T]

Backup accounts:
  balance before T

Backup ledger:
  entry after T

Restore:
  old accounts + new ledger -> invariant mismatch.
~~~

On a replica set, without a mechanism guaranteeing a unified snapshot, a multi-collection dump is read **across different time windows**. MongoDB Database Tools documentation states clearly: **without `--oplog`, when writes occur during a dump, the output does not reflect a single point in time**.

### 2.2. Even a Single Collection Can Change Mid-Scan

Suppose a job is exporting 10 million documents:

~~~text
Dump cursor:
  reads _id 1..1000000

Writer:
  updates an already-read document
  deletes a not-yet-read document
  inserts a new document

Dump cursor:
  continues reading the remainder
~~~

Depending on scan order, queries, indexes, and engine behavior, the backup may not match any consistent snapshot. Do not infer from this example that specific mutations always appear/disappear in a fixed order; the fundamental flaw is the **lack of a single cut timestamp**.

### 2.3. "Reading with Majority" Does Not Solve It Automatically

A reader using `readConcern:"majority"` observes data that has been majority-acknowledged per server semantics. Yet if the reader scans collections across **multiple points in time**, data can still differ because new writes were majority-committed between reads.

**Majority durability does not mean all reads share a single snapshot timestamp.** Distinguish this from `readConcern:"snapshot"` in supported APIs/transactions, and from a backup agent that pins or selects a dedicated recovery point.

## 3. RPO, RTO, and Consistency Targets

Backup/restore success should be defined by three criteria:

- **Consistency:** Restores a valid state at a defined logical point.
- **Recovery Point Objective (RPO):** Maximum acceptable data loss relative to the incident timestamp.
- **Recovery Time Objective (RTO):** Maximum allowed time to restore service per SLA.

Example:

~~~text
Backup snapshot:        09:00
Incident:               09:47
Restore to snapshot:    09:00

Data after 09:00 is lost without logs/PITR.
The data-loss window can reach 47 minutes.
~~~

The 09:00 backup may be completely **consistent**, yet fail a **5-minute RPO**. Reducing RPO requires capturing changes after the snapshot (e.g., managed continuous cloud backup/PITR) and ensuring restore to a supported timestamp.

### 3.1. Practical Requirement Profiles

| Application Type | Major Challenge | Evaluation Direction |
|---|---|---|
| Demo/dev, reconstructible data | RPO can be long. | Scheduled `mongodump`, test restore. |
| Knowledge base/small API | Continuous updates, few transactions. | Replica set `mongodump --oplog` or managed snapshot. |
| Marketplace with orders/payments | Requires consistency and low RPO. | Coordinated backup/PITR, verify business invariants. |
| 20-shard SaaS | Cross-shard transactions and chunk migrations. | Managed cluster-wide backups/PITR. |
| High-throughput IoT | Oplog churn, high storage/IOPS. | Online snapshot solution, monitor oplog window. |
| Compliance-regulated system | WORM/retention/encryption/auditing. | Managed policy + immutable offsite copies + restore drills. |

**RPO is a business requirement**, not a value measured by file size. RTO must be **rehearsed via restore drills**; `mongodump` speed tells you nothing about index rebuild time, oplog replay, data validation, or DNS/connection string cutover.

## 4. MongoDB Replication, Oplog, Journal, and Checkpoints

### 4.1. Replica Sets and the Oplog

A replica set has a **primary** accepting writes and **secondaries** synchronizing operations via the **oplog** — an ordered operation log stored in `local.oplog.rs` per deployment conditions and topology.

~~~text
Client writes
     |
     v
  Primary
     |
     +-- data files / WiredTiger
     |
     +-- oplog entries ------> Secondary A applies
                        \----> Secondary B applies
~~~

The oplog powers replication and certain backup/recovery workflows. It is **not an immutable log kept forever**. When write volume exceeds its configured size/retention, older entries can be overwritten; oplog-based backups may hit a **history gap**.

### 4.2. Why Is the Oplog Needed in an Online Dump?

While `mongodump` scans data, the tool can capture **operations that occur during the dump window**. During restore, replaying those operations in the proper order reconstructs a state at a single logical point in time, instead of stitching together collections read sequentially.

This is the role of `mongodump --oplog` and `mongorestore --oplogReplay` on a **replica set**. However, those flags **do not automatically provide a global snapshot of a sharded cluster**, because each shard replica set has its own history and there is also config server metadata.

### 4.3. Oplog Window

The **oplog window** is the time span between the newest and oldest entries retained in the oplog:

~~~text
Oplog oldest:  08:00
Oplog newest:  12:00
Window:        4 hours
~~~

If a backup workflow needs to replay events from 07:30 while the oldest retained entry is 08:00, it cannot reconstruct events that were already overwritten. Depending on implementation, the dump/agent may fail or require a resync. Monitor **oplog history during peak write hours**, not just daily averages.

### 4.4. WiredTiger Journal

The **journal** records changes needed to recover data after a crash per WiredTiger durability mechanisms. A proper filesystem copy must account for **both data files and the journal**, or use a flush/lock procedure when they reside on separate volumes.

You cannot simply copy a few `.wt` files while `mongod` is writing and claim it can be restored. A sequential file-by-file copy can capture pieces from mismatched checkpoint/journal states.

### 4.5. WiredTiger Checkpoints

WiredTiger periodically creates **checkpoints** representing a stable data state. The MongoDB Manual describes checkpoints occurring after sufficient data changes or time intervals (typically around one minute), but the exact recovery point of a backup still depends on the journal, snapshot method, and node state.

**Checkpoints do not replace the oplog/PITR**: they enable crash recovery, not a service that captures every change event and restores to any arbitrary timestamp.

### 4.6. Majority Commit and Rollback

With `writeConcern:{w:"majority"}`, a write is acknowledged once it meets the majority threshold per deployment semantics, preventing a write from existing only on an old primary and being rolled back after an election.

However:

- Majority ack **does not** mean the backup already contains the write; the backup has its own recovery point.
- `w:1` may appear as "success" to the app yet still be rolled back if insufficiently replicated.
- A secondary can **lag**; a backup reading a secondary reflects that node's state, not automatically the primary's "right now" state.
- A consistent point-in-time backup can be completely valid **yet precede** the most recent writes.

## 5. Backup Methods and Guarantees While Writes Continue

| Method | Can Back Up While Writes Run? | Consistency to Understand | Recommendation |
|---|---|---|---|
| Standard `mongodump` | Technically can run. | Does **not** guarantee a single point in time under concurrent writes. | Lab/dev data, quiesced migrations; do not use for online transactional guarantees. |
| `mongodump --oplog` on **one replica set** | Yes, if conditions are met and no prohibited DDL runs. | Tool uses oplog to bring dump to a single logical point when restored with `--oplogReplay`. | Online full replica-set logical backup, medium scale, test-restored. |
| Block-level snapshot of **one node** with all data/journal on one atomic volume | Can snapshot while running per platform/Manual procedures. | **Crash-consistent** for that node; recovers via journal/checkpoint. | Self-managed replica set; requires safe storage configuration. |
| File-by-file copy via `cp`/`rsync` while `mongod` writes | Can copy bytes, no usability guarantee. | **Not** an atomic snapshot; files read at different times. | Avoid. |
| Filesystem snapshot with journal/data on **different volumes** | Requires write lock/pause per Manual unless a proven atomic multi-volume snapshot exists. | No guarantee if volumes are snapshotted at different times. | Use `fsyncLock`/quiesce or coordinated storage-level consistency. |
| Manual backup of a **sharded cluster** via dump/snapshots | Requires quiescing writes and stopping balancer/schema transformations per Manual. | No automatic cluster-wide atomicity if snapshotting shards while writes run. | Use only specialized runbooks; check version compatibility. |
| Atlas Cloud Backup coordinated snapshots | Yes, for eligible clusters/tiers. | Managed **cluster-wide consistent snapshots**, including sharded clusters per conditions. | Preferred for managed online backups. |
| Atlas Continuous Cloud Backup / PITR | Yes, with feature and retention window enabled. | Snapshot + captured oplog allows picking a recovery point within the window. | Low RPO, needing recovery prior to a bad operation. |
| Ops Manager / Cloud Manager managed backup | Yes, per product support/topology. | Backup agents coordinate snapshots/PIT and metadata, including sharded clusters per product. | Self-managed enterprise/large topologies. |

**Note:** "Online backup" has two meanings: (1) without shutting down the daemon, and (2) **users can keep writing normally**. A manual snapshot may be taken while `mongod` is running yet still require **pausing writes** — meaning (1) is true, (2) is false. State requirements explicitly when choosing a solution.

### 5.1. Backup Speed Does Not Determine Consistency

Filesystem snapshots are often fast because they create copy-on-write images rather than reading all files immediately at creation time. However:

- A snapshot is only fast during **create snapshot**; copying/transferring/archiving/restoring still requires I/O.
- A snapshot on the same storage array does not replace an **offsite copy** if the whole site loses power or burns.
- Fast snapshots per shard taken asynchronously still produce an inconsistent cluster snapshot.
- Undo/rollback/journal replay capability depends on engine version and file state.

### 5.2. Consistency and Recoverability Are Two Different Questions

A backup can be consistent yet fail to restore because:

- Journal/index/metadata files are missing or the archive is truncated.
- Target version/FCV is incompatible.
- Snapshot lacks encryption keys/remote KMS permissions.
- Restore process runs out of space and gets killed midway.
- Index builds/validations fail to complete.
- Sharded topology/config servers are incompatible.

Therefore, **archive readback/checksums** are a technical check, whereas **restore drills + data validation** prove real recoverability.

## 6. Standard `mongodump` While Writes Continue

MongoDB Database Tools `mongodump` creates a **logical backup**: BSON documents and metadata defining indexes/options. This is **not** a physical WiredTiger checkpoint image; index data is typically **rebuilt** during `mongorestore`.

Command-line example in a lab environment:

~~~bash
# Example for a lab replica set only:
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./dump-without-oplog.archive"
~~~

If the application inserts/updates while the tool scans data, the archive may contain collections/documents from **different points in time**.

### 6.1. Why Can Individual Collections Look Fine Yet Still Be Dangerous?

Suppose:

~~~javascript
// Normal collections on a lab replica set.
db.accounts.insertMany([
  { _id: "A", balanceMinor: 100000 },
  { _id: "B", balanceMinor: 100000 }
])

db.ledger.insertOne({
  _id: "TX-1",
  from: "A",
  to: "B",
  amountMinor: 20000,
  state: "COMMITTED"
})
~~~

If `accounts` is read before a transaction updates balances and `ledger` is read after the transaction, the backup can hold **old balances + new ledger entry**. Simply parsing the BSON file cleanly cannot restore the broken invariant.

### 6.2. Is Adding `--readPreference=secondary` Enough?

No. Redirecting reads to a secondary offloads the primary, but:

- A secondary continuously **receives and applies oplog entries** during the dump.
- It may lag behind the primary.
- Collections can still be read at **different points in time**.
- The backup can still include writes applied while the tool scans.

**Read preference selects the read source**, not "freeze the DB state at a single point." To achieve point-in-time consistency on a replica set with Database Tools, you need `--oplog` (subject to its requirements).

### 6.3. Is `--readConcern majority` Enough?

No. `readConcern:"majority"` ensures visibility/durability guarantees for each read operation per server semantics, yet **does not** force all cursors and collections in a standard dump onto a single snapshot timestamp.

Do not conflate two distinct concepts:

~~~text
Read only majority-committed data

                ≠

Read all collections at one identical timestamp
~~~

into a single assumption. When a consistent snapshot is needed, use a backup method that explicitly provides that guarantee.

## 7. `mongodump --oplog`: Online Logical Backup of **One Replica Set**

For a **replica set**, MongoDB Database Tools lets `mongodump --oplog` record oplog entries occurring **during the dump**. When restored with `mongorestore --oplogReplay`, the dataset can be reconstructed at **one logical point in time** even while the application keeps writing during the backup.

### 7.1. Conceptual Flow

~~~text
Replica set writes continue:

       t0           t1       t2       t3
       |            |        |        |
       +-----------------------------> time

mongodump:
       [----- read BSON collections -----]
       [----- capture oplog entries -----]

Archive:
       BSON collection dumps
       metadata/options/index definitions
       oplog.bson (or embedded oplog in archive)

mongorestore:
       Restore BSON collections
       Replay oplog entries in valid order
                   |
                   v
       Consistent recovery state
~~~

Do not read this diagram and conclude the backup can restore **to any arbitrary time after the dump**. `mongodump --oplog` captures changes **within the dump window**, unlike **continuous oplog archival** in managed PITR solutions.

### 7.2. Creating a Full Backup with `--oplog`

In a **terminal** (not `mongosh`), on a lab replica set only:

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./rsLab-2026-11-14.archive" \
  --oplog
~~~

Directory format can also be used:

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --out="./rsLab-2026-11-14" \
  --oplog
~~~

In directory mode, the oplog is written as `oplog.bson` at the **top level of the dump directory**; in archive mode, entries are embedded inside the archive. `--archive` and `--out` **cannot be used together**.

### 7.3. It Must Be a **Full Dump**

Per MongoDB Database Tools docs, `mongodump --oplog` requires a **full dump of a replica set member**. Do not combine it with the following scope-narrowing options:

~~~bash
# The following combinations are INVALID with --oplog:
mongodump --oplog --db app
mongodump --oplog --collection accounts
mongodump --oplog --query='{"status":"ACTIVE"}'
mongodump --oplog --dumpDbUsersAndRoles
~~~

These are **invalid examples, not commands to run**. Why? Because the oplog records operations across multiple namespaces, whereas a partial dump lacks the full base dataset needed to replay consistently as designed.

### 7.4. DDL and Metadata Changes Can Cause the Dump to Fail

MongoDB Database Tools documents that certain operations occurring while `--oplog` runs will cause the dump to **fail**, such as:

- `renameCollection` or `db.collection.renameCollection()`.
- Aggregation pipelines using `$out` that replace a collection.
- Similar schema transformations/renames.
- Changes to users, roles, or privileges.
- Cluster-wide settings changes such as `setDefaultRWConcern`.

Thus "online backup allows writes to continue" **does not mean every DDL/admin operation can run concurrently**. Production backup plans still need **DDL-restricted backup windows**, migration alerts, and exit-code/artifact monitoring.

### 7.5. Backing Up from a Secondary

In a replica set with a backup-dedicated secondary:

~~~text
Primary (serves writes)
   |
   +----> Secondary A (serves reads)
   |
   +----> Secondary B (backup dedicated)
                    |
                    +-- mongodump --oplog
~~~

The benefit is offloading BSON scan pressure from the primary. However:

- The secondary may **lag**; the recovery timestamp corresponds to that source's data/oplog state, not automatically the primary's latest wall-clock time.
- You must monitor replication delay, disk I/O, available oplog window, and node health.
- Configure `readPreference`/topology targeting carefully so you do not accidentally hit the primary.
- Do not assume a backup secondary is "idle" if it also serves shard replication/change streams/critical reads.
- If an election, rollback, or source disconnect occurs, the backup can fail and must be retried rather than treating the archive as complete.

### 7.6. Using `--oplog` Does Not Mean Zero-RPO

A backup finishing at 10:10 and restored with `--oplogReplay` will not include writes from 10:11, 10:12, etc., without continuous oplog segments captured afterward. For **RPOs of minutes or sub-minute**, evaluate managed continuous backup/PITR or a properly engineered archival/redo-log pipeline.

### 7.7. The Oplog Window Must Be Large Enough

Suppose a dump takes 3 hours while the oplog window during peak traffic shrinks to 45 minutes. Needed entries risk rolling off/truncating before the tool/backup agent catches up. Plan accordingly:

1. Measure p95/p99 backup duration and peak throughput.
2. Measure the smallest oplog window during peak hours.
3. Add headroom for spikes, network hiccups, and retries.
4. Alert when the oplog window approaches backup duration + lag.
5. If a history gap occurs or the backup tool fails, **never mark the dump healthy**.

The MongoDB Manual documents `oplogMinRetentionHours` and `replSetResizeOplog`, yet **increasing retention/size impacts storage/replication**; perform capacity planning rather than changing production blindly.

### 7.8. FCV/Time-Series Caveats by Tools Version

In newer MongoDB releases, there is an important exception: Database Tools warns **not to change FCV between MongoDB 8.x and 9.0 while `mongodump --oplog` runs on a deployment with time-series collections**, because the oplog could span a **time-series format conversion** that `mongorestore --oplogReplay` cannot replay directly across an FCV state boundary.

Starting in **Database Tools 100.18.0**, `mongodump` may proactively fail rather than create an unrestorable dump in this case. Therefore, backup windows should **avoid FCV/major-version format transitions** and require compatibility restore testing. See the version notes at the end.

## 8. `mongorestore --oplogReplay`: Restoring Both Data and Writes From the Dump Window

A `mongodump --oplog` backup **only fulfills its guarantee when restored properly**. Restoring the BSON files while ignoring the oplog can leave you with an inconsistent state because collections were scanned at different times.

### 8.1. Restoring to an **Isolated and Empty** Environment

In a terminal on a compatible DR/test environment:

~~~bash
# Restore the lab replica set archive to an isolated target.
# Do NOT point RESTORE_URI at a live production cluster.
mongorestore \
  --uri="mongodb://restoreuser@restore-lab:27017/" \
  --archive="./rsLab-2026-11-14.archive" \
  --oplogReplay
~~~

Or with a directory dump:

~~~bash
mongorestore \
  --uri="mongodb://restoreuser@restore-lab:27017/" \
  --dir="./rsLab-2026-11-14" \
  --oplogReplay
~~~

`--oplogReplay` replays oplog entries from `oplog.bson` (in directory mode) or the archive's oplog section after restoring BSON data. The target should be **empty or dedicated for replay**; restoring over an actively written DB causes conflicts and unpredictable state.

### 8.2. Do Not Filter to a Single Namespace When Replaying the Full Oplog

With a full replica-set dump and `--oplogReplay`, MongoDB Database Tools **does not allow** narrowing the restore with:

~~~bash
# INVALID in the context of full oplog replay:
mongorestore --oplogReplay --db app
mongorestore --oplogReplay --collection orders
mongorestore --oplogReplay --nsInclude "app.orders"
mongorestore --oplogReplay --nsExclude "app.logs"
mongorestore --oplogReplay --nsFrom "app.*" --nsTo "demo.*"
~~~

These flags fail or are incompatible because replay logic expects the full dataset. If your goal is **restoring a single collection** from a large backup, design a separate **selective restore workflow** accounting for consistency constraints, dependencies, indexes, and cross-collection relationships.

### 8.3. `--oplogLimit` Is Not "Eyeballing a Timestamp"

Database Tools provides `--oplogLimit=<seconds>:<ordinal>` to cap which entries are replayed under `--oplogReplay`. Using an incorrect timestamp can cause **inconsistency**; official docs explicitly warn against manually picking arbitrary oplog ranges.

**Do not** assume picking a timestamp from logs and passing `--oplogLimit` produces a fully consistent arbitrary point-in-time restore; transactions, metadata changes, and capture scope must all be accounted for. For minute/second-level recovery, prefer **managed PITR** with controlled restore points.

### 8.4. New Writes on the Restore Target

If an application connects to the target and inserts data while `mongorestore` is running:

- Duplicate documents, unique index errors, or a partial restore can occur.
- Oplog replay may no longer align with the target dataset.
- Indexes or migrations may block the restore.
- Target data from a previous failed restore may contaminate the run.

Therefore, **isolate the restore target**, stop writes/app traffic to it, complete restore and validation, and then execute a coordinated cutover.

### 8.5. If a Restore Fails Midway

Do not blindly re-run the same command on a **partially restored** target. MongoDB Database Tools warns that a crash during `mongorestore` can leave incomplete, inconsistent data. Safe runbook:

1. Check the tool exit code, logs, and failure phase.
2. **Keep the original backup immutable** to preserve evidence.
3. Wipe/recreate the **approved DR target** or reset the environment safely.
4. Restore from scratch.
5. Verify counts, indexes, and business invariants before declaring ready.

**Never** run `--drop` automatically on a cluster not verified as the DR target; `mongorestore --drop` deletes existing collections.

### 8.6. Recovery Can Take Longer Than Creating the Backup

A logical dump holds documents and **index definitions**, not necessarily prebuilt index data structures like a physical snapshot. During restore, indexes must be **rebuilt**, extending RTO. Total:

~~~text
Actual RTO =
  prepare target
  + fetch/copy backup over network
  + load BSON data
  + replay oplog
  + build indexes
  + validation/business checks
  + app cutover / cache warming
~~~

A backup job finishing in 20 minutes does not guarantee the service can recover in 20 minutes.

## 9. Filesystem Snapshots: Node-Level and Storage-Level Consistency

A **filesystem snapshot** captures the state of an **entire volume** at a nearly instantaneous point per storage semantics. For MongoDB/WiredTiger, the essential requirement is that the snapshot includes the **exact set of data files and journal files** with appropriate atomicity.

### 9.1. A Single Volume Can Be Snapshotted Atomically

~~~text
Linux block device / logical volume V:

  /var/lib/mongodb/
    WiredTiger
    WiredTiger.wt
    collection-*.wt
    index-*.wt
    journal/
    ...

            |
   Atomic volume snapshot
            |
            v
      Snapshot image
            |
      Copy to offsite store
~~~

If all required components live on one volume and the snapshot is properly atomic, the backup reflects a **node-level crash-consistent state**. When the target starts up, MongoDB recovery uses checkpoints/journal to bring data to a valid state.

However, **never** assume every cloud disk snapshot, RAID array, or container volume driver provides atomic snapshots across the entire dataset. Verify your specific storage platform and follow MongoDB's backup tutorial.

### 9.2. Data and Journal on Separate Volumes

Case:

~~~text
Volume A:
  collection/index WiredTiger files

Volume B:
  journal files

Snapshot A at 10:00:00
Snapshot B at 10:00:20
~~~

If writes continue during the 20 seconds between snapshots, you combine data files and journal from **two mismatched states**. The MongoDB Manual requires **locking and pausing writes** for filesystem backup procedures when WiredTiger data and journal sit on separate volumes.

"All volumes snapshotted within the same minute" is not enough — you need a verified **atomic multi-volume group snapshot**, or write locking/flushing per the documentation.

### 9.3. `db.fsyncLock()` Procedure When Required

On a lab node or backup-dedicated secondary per official guidance:

~~~javascript
// ADMIN PATTERN - DO NOT RUN ARBITRARILY ON A PRODUCTION PRIMARY.
db.fsyncLock()
~~~

Then the operator takes the snapshot/copy per runbook, and **must unlock**:

~~~javascript
db.fsyncUnlock()
~~~

**Impact:** `fsyncLock` can block writes and degrade replication/app availability depending on the node; running it on a primary impacts production directly. Do not treat it as an online backup where **writes continue normally**.

### 9.4. Always Include an Unlock/Recovery Step on Failure

The runbook must handle:

- Snapshot process timeout.
- Operator session disconnect between `fsyncLock` and `fsyncUnlock`.
- Snapshot service returning an error while the node remains locked.
- Secondary falling behind the oplog if blocked from applying for too long.

**Maintain checklists and alarms** for lock duration; never leave a node locked for hours. In automation, use `finally`/failure handling and verify lock state using the appropriate command/version.

### 9.5. Why Isn't Live `rsync` Equivalent to a Snapshot?

~~~bash
# DO NOT use as a guaranteed consistent backup while MongoDB writes:
rsync -a /var/lib/mongodb/ backup-host:/backup/mongo/
~~~

Copying `collection-1.wt` at 10:00:01, `index-1.wt` at 10:00:30, and the journal at 10:01:00 produces files from mismatched timestamps. A clean file/SSH `rsync` exit **does not** prove a crash-consistent database.

### 9.6. Storage Snapshots Are Not Offsite Backups

A copy-on-write snapshot on the **same storage pool** can be lost alongside the disk array or site. After creating the image, copy it to **offsite/immutable storage** and verify checksums, encryption, and retention. Fast snapshots help RTO, but do not replace defenses against ransomware, accidental snapshot deletion, site failure, or compromised admin credentials.

### 9.7. Should You Snapshot a Primary or a Secondary?

Usually, consider a **dedicated backup secondary** to avoid impacting the primary. However:

- The backup secondary must be healthy and not excessively lagged.
- The oplog window must suffice for the node to catch up after snapshotting/locking.
- Read traffic/hidden member topology must match design.
- Restoring from a secondary snapshot yields a recovery point that may be **stale** compared to the primary.
- If the snapshotted node underwent an election/rollback, consult stability runbooks before certifying the backup.

Do not snapshot the primary merely because it is "freshest" if the cost/write-pause breaks SLA. Nor should you treat any secondary as a globally consistent point for an entire sharded cluster.

## 10. Sharded Cluster: Why Each Shard Being Consistent Is Still Not Enough

A sharded MongoDB cluster comprises multiple **shard replica sets**, `mongos` routers, and a **config server replica set** storing metadata for shards, collections, and ranges/chunks. Transactions can write across multiple shards. Backups must preserve **cluster-wide** consistency, not just each shard individually.

### 10.1. Cross-Shard Transaction Example

~~~text
                mongos
                  |
      +-----------+-----------+
      |                       |
      v                       v
   Shard A                  Shard B
 account A                account B

Transaction T:
  A.balance -= 200
  B.balance += 200

Backup Shard A at 10:00:10
Backup Shard B at 10:00:30
~~~

If T commits at 10:00:20, backup A may reflect data **before T**, while backup B reflects data **after T**. Each individual shard snapshot is valid, yet **when restored together, transaction T is torn in half**.

This is the **cross-shard consistency problem**. It cannot be solved simply by "syncing NTP clocks": it requires a **backup method that coordinates timestamps/recovery points and transaction boundaries**, or pausing writes per runbook.

### 10.2. Config Server Metadata Can Drift From Shard Data

The config server stores **chunk/range ownership**. If the balancer migrates range R during a backup:

~~~text
10:00  Config: range R belongs to Shard A
10:01  Balancer migrates R from A -> B
10:02  Backup Shard A
10:03  Backup config metadata
10:04  Backup Shard B
~~~

Combining data/metadata from different timestamps can cause **missing data, duplicates, or metadata ownership mismatches** upon restore. Hence MongoDB documentation requires **stopping the balancer** during manual sharded cluster backups and confirming migrations have ceased.

### 10.3. Why Doesn't `mongodump --oplog` on `mongos` Solve This?

MongoDB Database Tools states clearly:

- `--oplog` operates on nodes that maintain an **oplog**, such as replica set members.
- Running `mongodump --oplog` via `mongos` to dump an entire sharded cluster **provides no global snapshot guarantee**.
- `mongodump --oplog` cannot be used as an online backup method for an entire sharded cluster with replica set semantics.
- `mongorestore --oplogReplay` **is not supported for sharded clusters** in that model.

**Do not:** dump each shard with `--oplog`, pick the "latest oplog" from each shard, stitch them arbitrarily, and claim cross-shard transaction recovery. Separate oplogs do not automatically form a global cut.

### 10.4. What Must a Manual Sharded Cluster Backup Stop?

Per MongoDB's official tutorials for self-managed sharded clusters:

1. **Stop the balancer** and wait for in-flight migrations to finish.
2. **Stop writes** to the cluster and any related schema transformations/resharding operations.
3. Execute **`fsync`/`db.fsyncLock()`** and snapshot/dump each component per the supported runbook/version.
4. Back up **config server metadata** and every shard in the prescribed order/procedure.
5. Verify artifacts and metadata, then **unlock/restart the balancer/writers** cleanly.

With manual approaches, docs warn that consistency still depends on having no half-completed operations and following the procedure strictly. **Do not interpret "stop the balancer" as sufficient**: if writes continue, cross-shard inconsistency can still occur.

### 10.5. Example of **Sensitive Administrative Commands** (Not a Production Copy-Paste Script)

On `mongos` in an authorized **sharded lab**:

~~~javascript
// STOP BALANCER: alters cluster operation.
sh.stopBalancer()

// Check state, and confirm migrations have actually stopped.
sh.getBalancerState()
~~~

In supported environments/sequences, the database dump backup documentation also describes locking the cluster from `mongos`:

~~~javascript
// ILLUSTRATIVE ONLY: follow full procedure/permissions.
db.getSiblingDB("admin").fsyncLock()

// Create the backup in the next step per the official tutorial.

// Finally unlock per the exact procedure:
db.getSiblingDB("admin").fsyncUnlock()
~~~

**Never run these commands** on production just while reading a lesson; they directly affect write availability and cluster balancing. Across MongoDB versions, locking/state verification/commands can differ; follow the **tutorial for your exact server version** without skipping preparation steps.

### 10.6. Why Is Backing Up the Config Server Crucial?

Business collections alone are not enough:

~~~text
Sharded-cluster backup set:

  config server replica set
    - collection/shard metadata
    - chunk/range ownership
    - configuration state

  shard A replica set
    - data/index definitions

  shard B replica set
    - data/index definitions

  shard C replica set
    - data/index definitions
~~~

Restoring shard data with missing or mismatched config metadata can leave `mongos` unable to locate ranges accurately. A **cluster restore** differs from importing documents into a fresh collection; never attempt to repair topology by manually inserting documents into `config.*`.

### 10.7. Topology Compatibility During Restore

Managed systems and restore tools impose constraints on:

- Shard count and config server type (dedicated/config-shard).
- Server version and FCV.
- Auth/users/roles/encryption/key management.
- Logical/physical backup format.
- Snapshot age and compatibility after adding/removing shards.

For example, **Atlas Cloud Backup** requires **source/target sharded clusters to have compatible shard counts** and matching config server topologies; in some cases an older snapshot cannot restore onto a changed topology. Check the exact tutorial and plan to **restore to a new cluster with a matching topology**.

### 10.8. Recommended Approach When True Online Backup Is Needed

If the business cannot pause writes on a sharded cluster, the operationally simpler path is using:

- **Atlas managed cluster-wide backups**.
- **Atlas Continuous Cloud Backup (PITR)** when recovery timestamps near an incident are needed.
- **MongoDB Ops Manager / Cloud Manager** with coordinated backup/restore per product terms.

These services are engineered to **coordinate shards, transactions, and metadata**; do not replace them with a cron job running parallel `mongodump --oplog` jobs lacking a verified global cut algorithm.

## 11. Atlas Cloud Backup: Managed Backups for Active Clusters

**MongoDB Atlas Cloud Backup** provides policy-driven snapshots and, when **Continuous Cloud Backup** is enabled on supported deployments, **point-in-time restore** within a configured window.

### 11.1. Managed Service Consistent Snapshots

The MongoDB Atlas Architecture Center describes **cluster-wide consistent snapshots including for sharded clusters**. Atlas coordinates timing across shards so the snapshot corresponds to the selected cluster point.

This eliminates the pitfall of operators manually snapshotting shards at different times. Still, do not assume every DDL operation, backup tier, or PITR capability behaves identically — check **cluster tier, cloud provider, region, version, backup policy, and restore target**.

### 11.2. Snapshots Can Be Taken While the Application Writes

~~~text
Applications continuously write
          |
          v
      Atlas cluster
     /     |      \
  Shard A Shard B Shard C
     \     |      /
      coordinated snapshot
              |
              v
     Backup storage + retention policy
~~~

**Managed backups** avoid building custom lock/stop-balancer workflows in many scenarios. However, backup jobs still consume storage/compute/network and may have version/feature constraints.

### 11.3. PITR: Snapshot Plus Captured Changes

~~~text
09:00     Snapshot S0
  |
  +-- 09:05 changes captured
  +-- 09:10 changes captured
  +-- 09:15 changes captured
  +-- 09:17 accidental deletion
  |
  v
09:18     Incident detected

Recovery objective:
  Restore to 09:16:59 (just before deletion),
  if that point is inside permitted PITR window.
~~~

**Exact timing** must be determined per product support and the actual operation/commit timestamp. You may aim to restore **just before** a bad delete, yet picking a wall-clock time alone does not guarantee the operation hadn't executed if clocks and cluster timestamps differ; consult oplog timestamps/audit logs when available.

### 11.4. A Snapshot Schedule Is Not Continuous Backup

If policy only retains hourly snapshots:

~~~text
09:00 snapshot
10:00 snapshot
10:49 fail
~~~

With snapshots alone (no PITR), recovery may have to return to 10:00, losing nearly 49 minutes of writes. Continuous backup stores ongoing changes to allow choosing restore points within the window. Never equate "hourly backups" with a one-minute RPO.

### 11.5. Backup Retention and Restore Window

Distinct parameters:

| Parameter | Meaning |
|---|---|
| Snapshot frequency | How often a new snapshot is created. |
| Snapshot retention | How long snapshots are kept. |
| Continuous/PITR window | History span with enough logs to restore by timestamp. |
| Backup compliance policy | Mandatory retention, immutability/regulatory rules. |
| Restore target constraints | Compatible shard count/region/tier/version/data partitioning. |
| RPO | Acceptable data loss per business rules. |
| RTO | Total time to recover usability after an incident. |

If the PITR window is only 24 hours and corruption is discovered 3 days later, you **cannot** automatically restore to just before the bug using that PITR window, even if an older snapshot remains under retention policy.

### 11.6. Fallback Snapshots Warning

Atlas documentation mentions **fallback snapshots** in certain restore scenarios, warning that they **may contain inconsistent data** and should only be used as a last resort. Do not ignore consistency warnings simply because a snapshot appears in the UI. For DR evaluation, prioritize snapshots verified to carry the required guarantees and validate application invariants.

### 11.7. Restoring to a New Cluster Reduces Risk

In many incidents, restoring to a **new/isolated cluster**, verifying data, and switching traffic is safer than overwriting the live cluster. Atlas docs note that cluster-level restores can **overwrite existing data on the target** and render it unavailable during restoration. Runbooks should distinguish:

- **In-place cluster restore**: downtime / potential loss of existing target data.
- **Restore to new cluster**: requires topology/cost/connection string/migration prep, yet enables validation before cutover.

### 11.8. Search Indexes, Secrets, and External Services

Atlas restore may restore **search index definitions** without pre-populating all index data; Search/`mongot` may need to **rebuild**, delaying search feature availability even after collections finish restoring. Additionally:

- Secrets/KMS keys and access policies may live outside backup data.
- Integrations such as Kafka, S3, payment systems, and Redis caches do not automatically share the same restore point.
- Replication/backup management logs must be retained for audits and recovery decisions.

**A cluster-consistent snapshot is only one piece of a full-system DR plan.**

## 12. Transactions and Backup Consistency: Complete Business Example

Suppose an e-wallet system has `wallets` and `transfers` in the **same replica set**. Transferring funds requires:

1. Checking that wallet A has sufficient funds.
2. Debiting A and crediting B.
3. Creating a `transfers` record with status COMMITTED.
4. All changes commit or abort together.

### 12.1. Proper Application-Layer Transaction

`mongosh` example on a lab replica set:

~~~javascript
const session = db.getMongo().startSession()
const sdb = session.getDatabase("backup342_lab")

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const debit = sdb.wallets.updateOne(
    { _id: "A", balanceMinor: { $gte: 20000 } },
    { $inc: { balanceMinor: -20000 } }
  )
  if (debit.matchedCount !== 1) {
    throw new Error("insufficient funds or missing source wallet")
  }

  const credit = sdb.wallets.updateOne(
    { _id: "B" },
    { $inc: { balanceMinor: 20000 } }
  )
  if (credit.matchedCount !== 1) {
    throw new Error("missing destination wallet")
  }

  sdb.transfers.insertOne({
    _id: "TX-20261114-001",
    from: "A",
    to: "B",
    amountMinor: 20000,
    state: "COMMITTED",
    createdAt: new Date()
  })
  session.commitTransaction()
} catch (err) {
  try { session.abortTransaction() } catch (_) {}
  throw err
} finally {
  session.endSession()
}
~~~

**Note:** This code illustrates atomicity; production requires a transaction retry policy, commit ambiguity handling, stable idempotency keys, and duplicate transfer prevention. Using a transaction avoids partial business writes in the **live database**, yet backups still require a proper recovery point.

### 12.2. What If a Backup Cuts Across a Commit?

~~~text
Transaction T timeline:

  t0: T starts, updates A/B and inserts TX
  t1: T commits successfully

Backup recovery point P:

  P < t1:
     A/B and transfer record reflect state before T

  P >= t1:
     A/B and transfer record reflect state after T
~~~

A consistent backup must respect **transaction atomicity at the recovery point**. Uncoordinated reads by plain `mongodump` do not automatically enforce that rule; `--oplog` on a replica set or managed backup/PITR is built to preserve it under supported conditions.

### 12.3. Post-Restore Invariant Check Example

~~~javascript
// Run on the restored DR database, NEVER pointing at production.
const rdb = db.getSiblingDB("backup342_lab")
const walletA = rdb.wallets.findOne({ _id: "A" })
const walletB = rdb.wallets.findOne({ _id: "B" })

if (walletA == null || walletB == null) {
  throw new Error("wallet missing after restore")
}

const total = walletA.balanceMinor + walletB.balanceMinor
printjson({
  totalMinor: total,
  transfers: rdb.transfers.countDocuments({ state: "COMMITTED" })
})
~~~

If the two wallets originally totaled 200,000 VND with no deposits/withdrawals, the sum must remain 200,000 across all internal transfers. Yet **a matching sum alone is not enough**: you still need to check individual ledger entries/transfer IDs, timestamps, and external payment reconciliation.

### 12.4. A Snapshot Can Still Capture an Intermediate Business State

If the application issues **two writes outside a transaction**:

~~~text
update A.balance
      |
      +---- backup point P
      |
update B.balance
~~~

then even a **valid database snapshot at P** will capture A debited while B is not yet credited. Backups do not replace application transactions, outbox patterns, or business atomicity.

**Database-consistent** means accurately reflecting MongoDB's state at P; **business-consistent** also requires the application not to produce invariant-violating states (or to define a compensating recovery workflow).

## 13. Read Concern and Write Concern: Real Impact on Backups

### 13.1. `w:1` vs. `w:"majority"`

~~~javascript
// Can be acknowledged by primary before reaching majority:
db.events.insertOne(
  { eventId: "E-1001", value: 42 },
  { writeConcern: { w: 1 } }
)

// Requires majority acknowledgement:
db.events.insertOne(
  { eventId: "E-1002", value: 43 },
  { writeConcern: { w: "majority" } }
)
~~~

`w:"majority"` reduces the risk of an acknowledged write being rolled back after an election. However, a backup at a recovery point prior to E-1002 still will not contain E-1002 even if it was majority-acknowledged immediately afterward. That is an **RPO/recovery point** property, not a failure of majority write concern.

### 13.2. `readConcern:"local"`

Readers may see the node's latest local data, including writes not yet majority-committed that could still be rolled back. Do not treat `local` as guaranteeing "newest and safest"; consider source node, stable timestamps, and backup methodology.

### 13.3. `readConcern:"majority"`

`majority` guarantees visibility rules per operation under server semantics, **without freezing** the entire database across thousands of cursor batches:

~~~text
10:00:00  Read accounts with majority
10:00:05  Commit transaction T with majority
10:00:10  Read transfers with majority
~~~

Both reads use majority yet observe **two different points in time**. "Dumping with readConcern majority" cannot replace `--oplog` or a managed snapshot guarantee.

### 13.4. `readConcern:"snapshot"`

Within supported operations/transactions, `snapshot` reads data as of **one snapshot timestamp**. However:

- Very long read-only transactions scanning an entire database put pressure on snapshot history/cache and can hit transaction lifetime limits.
- Sharded clusters require timestamp coordination across shards.
- A snapshot read does not persist data/journal files or continuously capture the oplog.
- `mongodump` does not become a cluster-wide consistent backup simply because an app uses snapshot read concern elsewhere.

**Use supported backup tools with verified guarantees**, rather than building giant read transactions to scan the DB.

### 13.5. Does Causal Consistency Help?

A causally consistent session preserves causal ordering for reads/writes under defined conditions; it **does not** create a global point-in-time cut across all collections and shards when an independent backup tool runs.

Do not confuse causal consistency with snapshot consistency, nor assume a user API session coordinates a `mongodump` process running elsewhere.

## 14. Other Changes During the Backup Window

It is not only `insertOne()` and `updateMany()` that affect consistency. DDL, background jobs, TTL, and cluster management can prevent a backup from representing a valid state.

### 14.1. Rename/DDL

~~~javascript
// DDL ILLUSTRATION; do not run during a backup window.
db.orders.renameCollection("orders_v2")
~~~

If `mongodump` scanned part of `orders` when the rename fired and later moved to `orders_v2`, output can suffer namespace errors or incomplete data. `mongodump --oplog` documents operations that cause a failure, including `renameCollection`, aggregation `$out`, and user/role/cluster-wide setting changes.

**Schedule backup windows away from deployment migrations and schema transformations**, not just peak web traffic.

### 14.2. TTL Deletes

The TTL monitor may delete expired documents during a backup. Plain dumps can see before-and-after states across reads; replica-set `--oplog` or managed recovery points reconstruct those deletes accurately as of the logical point.

After restore, TTL may **resume deleting** documents immediately because they are already past expiration, changing test counts. When validating restores, account for TTL policies and wall-clock time rather than assuming restored data stays frozen forever after `mongod` starts.

### 14.3. Index Builds

Index builds increase IOPS and extend backup duration. `mongodump` exports BSON documents and index definitions, whereas `mongorestore` may have to **rebuild** indexes. Consequently:

- A fast backup does not mean a fast restore.
- Free space is needed for index rebuilds.
- Post-restore checks must verify index readiness/queries, not just collection counts.
- Avoid running major index migrations alongside backups without impact analysis.

### 14.4. Compaction and Storage Transformations

Compaction or file-layout changes can impact physical snapshots/file copies. Use supported backup/storage APIs instead of custom scripts scanning `.wt` files while the engine mutates structures.

### 14.5. Chunk Migration/Resharding

On a sharded cluster:

- The balancer moves chunks/ranges.
- Resharding clones data and reassigns metadata ownership.
- Schema/FCV transformations can alter storage layout.
- Cross-shard transactions use dedicated commit protocols.

Uncoordinated manual backups can **miss or duplicate ranges** or misalign metadata and data. Stop the **balancer, writes, and schema transformations** per the tutorial, or use managed coordinated backups.

### 14.6. Atlas Search/Vector Indexes

Restoring BSON documents does not guarantee Search/Vector index segments are ready at the exact same moment. Index definitions may restore, while search index data requires **initial sync/rebuild**. DR readiness must include search endpoints, not just `findOne()` on a collection.

### 14.7. Major Versions, FCV, and Storage Formats

Do not run backups spanning FCV/major-version layout changes when tool docs warn against support. For instance, MongoDB 8.x ↔ 9.0 includes a **time-series format conversion** that prevents `mongorestore --oplogReplay` from replaying an oplog range spanning the conversion. Database Tools 100.18.0+ implements early-failure checks for affected cases.

If a DR runbook must cover an upgrade window, retain **backups proven restorable at each stage** rather than assuming unconditional backward/forward compatibility.

## 15. Data Outside MongoDB: A Consistent DB Is Not Automatically a Consistent System

An e-commerce application typically pairs MongoDB with:

- Kafka/RabbitMQ/SQS for events.
- Object storage for images, invoices, and exports.
- Redis for caches/queues.
- Payment providers and external ledger services.
- Search indexes, warehouses, or analytics projections.

A MongoDB backup can be completely valid as of 10:00 while Kafka offsets and object storage sit at 10:03. Restoring MongoDB without planning for connected systems causes duplicate events, broken references, or double processing.

### 15.1. Outbox and Already-Published Events Example

~~~text
09:59  MongoDB transaction:
         Create order O-10
         Insert outbox event E-10
       Commit.

10:00  MongoDB backup point P.

10:01  Worker sends E-10 to Kafka, marks outbox SENT.

10:05  Incident; restore MongoDB to P.
~~~

After restore:

- MongoDB has order O-10 and outbox E-10 **not yet SENT** (state at 10:00).
- Kafka already contains event E-10 sent at 10:01.
- The worker may re-publish E-10.

This is not necessarily a **backup defect**. It requires idempotent consumers and stable event IDs to handle replay safely. Full-system recovery must define cutover, queue offsets, and deduplication.

### 15.2. Do Not Delete External Objects Too Early

If MongoDB holds:

~~~javascript
{
  _id: "INVOICE-100",
  pdfUrl: "s3://billing/invoices/INVOICE-100.pdf"
}
~~~

yet object storage deleted the file at 10:03 while the DB restores to 10:00, the restored record points to a missing file. You need **coordinated retention** on object storage (versioning/soft delete/WORM per policy), not just MongoDB document backups.

### 15.3. Caches Are Not Sources of Truth

Redis caches may hold values newer than the restore point. After a MongoDB restore, invalidate/warm caches per runbook so you do not serve data from the "future" relative to the restored DB.

### 15.4. Multi-Region and External Consistency

If a MongoDB cluster spans regions and external services log in UTC vs. local time, rely on **event IDs, logical offsets, cluster timestamps, and commit markers**, not string-matching wall-clock log timestamps. NTP reduces clock skew, but **does not replace distributed transactions/coordination** across systems.

### 15.5. Designing an Application Recovery Protocol

A sound workflow:

1. Select a **MongoDB recovery point P** proven consistent.
2. Record corresponding **external offsets/checkpoints** or define idempotent replay rules.
3. Pause ingress/consumer writes during restore/cutover.
4. Restore MongoDB and verify business invariants.
5. Reset queue consumer offsets or apply replay/deduplication policies.
6. Rebuild caches/search/read models derived from MongoDB.
7. Admit canary traffic and monitor errors, duplicates, and lag.

**Never claim "the entire system was restored atomically"** unless every component actually has coordinated synchronization and verification.

## 16. Securing Backups While the System Writes

Consistency is central, yet a backup still requires protection for **confidentiality, integrity, and controlled usability**.

### 16.1. Least-Privilege Backup Accounts

Do not use a cluster-wide admin application account just to run backups. For `mongodump`, use built-in roles/privileges scoped to the needed collections/metadata; for managed backups, grant task-specific project roles. Restore accounts should also be separated and used only in authorized DR environments.

### 16.2. Encryption in Transit and at Rest

In production:

- Use TLS to MongoDB.
- Encrypt backups at rest and in transit to offsite storage.
- Protect keys via KMS/secret manager and verify key recovery.
- Never leak URI passwords in shell history, CI logs, READMEs, or repos.
- Enforce retention/immutable storage per policy to block unauthorized deletion/tampering.

Lesson command examples use placeholder hostnames/usernames; **never** place real secrets into examples or logs.

### 16.3. Checksums and File Integrity

After copying an archive to another storage tier, generate a checksum:

~~~bash
# Example on Linux/Unix in a DR environment.
sha256sum rsLab-2026-11-14.archive
~~~

Comparing source and destination checksums detects **file corruption during transfer**. However, a passing checksum only confirms identical bytes; **it does not prove consistent DB contents**. Proving consistency requires restoring and validating business invariants.

### 16.4. Restore Drills Must Not Expose Sensitive Data Carelessly

A production backup may contain PII/secrets. DR tests must run in environments with equivalent security controls, restricted access, anonymization where appropriate, and protected log artifacts. Never download customer backups onto personal laptops just to run a test.

### 16.5. Malware/Ransomware and Backup Independence

If backups reside in the same account/storage as production and can be deleted with the same credentials, losing production credentials can wipe out backups too. Enforce **privilege separation, immutable/offsite copies, audit trails, and a restore path when the primary admin plane is compromised**.

## 17. Monitoring Backups as Write Throughput Changes

A backup job that succeeded last week can fail during a flash sale due to **oplog churn, latency, index builds, I/O pressure, or insufficient disk headroom**. Continuous monitoring beats a silent cron job returning exit code 0.

### 17.1. Minimum Metrics to Track

| Metric | What to Measure | Alert When |
|---|---|---|
| **Last verified recovery point** | Latest confirmed backup/PITR timestamp. | Older than allowed RPO/SLO. |
| **Backup job success/failure** | Exit codes/managed job states, errors. | Job fails or is skipped while scheduler reports success. |
| **Backup duration** | Snapshot/dump creation and offsite copy time. | Exceeds backup window or spikes suddenly. |
| **Oplog window** | Remaining history duration. | Too close to backup duration + retry margin. |
| **Replication lag** | Lag on backup secondary and other secondaries. | Recovery point goes stale or node falls behind. |
| **Write QPS/oplog bytes/sec** | Peaks and variation over time. | Oplog window shrinks rapidly at peak. |
| **CPU/IOPS/cache pressure** | Primary, backup secondary, storage. | Backups elevate app p95/p99 latency. |
| **Backup artifact size** | Full/incremental sizes and growth. | Unusually small or unusually large. |
| **Checksum/transfer result** | Source/dest hashes, upload integrity. | Mismatch or incomplete/truncated copy. |
| **Restore-drill outcome** | Pass/fail, duration, invariants. | Overdue drill or failure. |
| **PITR window coverage** | Earliest/latest restorable timestamp. | Window shorter than retention/RPO policy. |
| **Key/KMS availability** | KMS grants, backup encryption keys. | Key revoked or inaccessible at restore time. |
| **Sharded cluster state** | Balancer/migrations, pending DDL/reshard. | Manual backup runs while topology is changing. |

### 17.2. Checking the Oplog Window on a Replica Set

In `mongosh` connected directly to a replica-set member (with authorized permissions):

~~~javascript
// Classic helper displaying oplog size/time range.
rs.printReplicationInfo()

// View replication state, member health/optimes.
rs.status()
~~~

In newer deployments, some helpers may change or be supplemented by monitoring/APIs; collect metrics from Atlas/Ops Manager where appropriate. **Never** run replica-set helpers directly through `mongos` and assume it reflects a cluster-wide oplog.

### 17.3. Oplog Window Depends on Write Rate

A rough estimate:

\[
\text{Oplog history duration}
\approx
\frac{\text{effective oplog capacity}}
{\text{average oplog write bytes/second}}
\]

Under heavy write bursts, **the window shrinks** if oplog capacity is fixed, unless minimum retention or other settings apply. This is only a rough model; reality includes entry size distributions, truncation policies, transaction operations, and retention settings.

### 17.4. Capacity Planning Illustration

~~~text
Off-peak:
  backup duration: 45 minutes
  oplog window:    5 hours

Flash sale:
  backup duration: 90 minutes
  oplog window:    55 minutes
~~~

During a flash sale, backup duration exceeds the observed window, risking the backup agent losing needed history. Do not treat 90/55 literally as universal thresholds: gather tool and workload logs, add headroom/throttling, or adopt a better-suited backup method.

### 17.5. Do Not Monitor Only Free Disk Space

A node with 2 TB of free disk that causes a 5x spike in p99 latency on every backup still violates SLOs. Treat backup workloads as **a consumer of CPU, network, I/O, and cache**; if using a backup-dedicated secondary, ensure it has enough capacity and does not lag replication excessively.

### 17.6. Alert When a Backup "Succeeds With the Wrong Scope"

For example, a job intended to back up an entire replica set has `--db=app` added to `mongodump` while `--oplog` is removed to make the command run. The job may exit 0 yet **lose its consistency guarantee**. Therefore, manifests/automation must explicitly record:

- **Full replica set** backup or partial DB/collection?
- Is `--oplog` present, and which tool version?
- Where is the recovery timestamp/point?
- Target cluster and roles?
- **Restore drill** results and business checks?

Never report "healthy" solely because an output file exists.

## 18. End-to-End Runbook: From Backup to Restore/Cutover

A runbook must be specific enough for an operator to execute **during an incident**, without having to invent architecture while production is down.

### Phase A — Define Objectives

1. Specify topology: standalone, replica set, sharded cluster, Atlas/managed.
2. Define RPO, RTO, and recovery granularity (full cluster, DB, collection).
3. List business invariants and external dependencies.
4. Choose a backup method matching **active-write requirements**.
5. Define retention, offsite/immutable storage, and compliance rules.
6. Document supported versions/FCV and backup/restore tool versions.

### Phase B — Pre-Backup Preparation

1. Verify replica set health, oplog window/replication lag/capacity.
2. Verify user credentials/roles/KMS permissions.
3. For manual sharded backups: schedule coordinated write/balancer/DDL pause.
4. For replica-set `--oplog`: prepare full dump and block prohibited DDL.
5. Choose encrypted storage destination with sufficient space.
6. Record backup ID, start time, source topology, and tool version in the manifest.

### Phase C — Collecting the Backup

~~~text
Backup job starts
   |
   +-- Check source topology/version/health
   |
   +-- Capture data with appropriate consistency method
   |
   +-- Capture oplog or coordinated snapshot metadata
   |
   +-- Copy artifact to protected storage
   |
   +-- Verify complete artifact / checksum
   |
   +-- Record recovery point and retention
   |
   v
Mark artifact "CANDIDATE FOR RESTORE"
~~~

At this point you have a **candidate backup artifact**. Not every single backup must be test-restored immediately, but you need a **scheduled restore validation** cadence and must not treat file-only checks as proven recoverability.

### Phase D — Test Restore in an Isolated Environment

1. Choose an artifact with an appropriate recovery point/retention.
2. Provision a **new/empty DR target** with compatible topology/version.
3. Block inbound application writes to DR.
4. Restore data and oplog/PITR using the prescribed method.
5. Inspect logs/exit codes and index build completion.
6. Verify database names, document counts, and schema/index definitions.
7. Run business invariants (e.g., wallet totals, orphan references).
8. Test critical queries/end-to-end APIs.
9. Record **actual** restore results and duration.

### Phase E — Production Cutover When Required

1. Declare incident and select approved recovery point P.
2. Pause/coordinate writes and message consumers before cutover.
3. Restore to an isolated target or follow an approved in-place runbook.
4. Run integrity/business checks and verify permissions/KMS.
5. Switch connection strings/DNS/routers to the target.
6. Disable/redirect producers pointing at the old cluster to prevent split brain.
7. Warm caches/rebuild search indexes/reconcile external events.
8. Monitor errors, duplicates, lag, and p95/p99.
9. Record actual data loss vs. RPO and notify stakeholders.

### Phase F — Post-Incident

- Archive artifact hashes, manifest, logs, chosen recovery point, and approvers.
- Root-cause analysis: wrong backup method, oplog gap, storage fault, DDL, permissions/KMS.
- Tune retention/monitoring/capacity and re-run drills.
- Do not delete the old cluster/artifacts prematurely before full verification and retention/forensics policies clear.

### 18.1. Backup Manifest Example

~~~json
{
  "backupId": "RS-LAB-20261114-0100",
  "sourceType": "replicaSet",
  "sourceName": "rsLab",
  "method": "mongodump --oplog",
  "databaseToolsVersion": "100.x.y",
  "serverVersion": "8.x.y",
  "fcv": "8.0",
  "startedAtUtc": "2026-11-14T01:00:00Z",
  "finishedAtUtc": "2026-11-14T01:18:00Z",
  "archive": "rsLab-2026-11-14.archive",
  "checksumSha256": "<computed-by-backup-job>",
  "restorePoint": "<recorded-from-backup-metadata>",
  "store": "encrypted-offsite",
  "restoreDrill": {
    "status": "NOT_YET_RUN",
    "lastVerifiedAtUtc": null
  }
}
~~~

**This is illustrative metadata JSON**, not a mandatory MongoDB format. `checksumSha256` must be computed on the actual file by the job; `restorePoint` must never be guessed from the scheduler's start time.

### 18.2. Crucial Lesson About the Restore Target

The DR target must never receive production writes before restoration completes. Furthermore, prevent both clusters from accepting writes after cutover. If the old cluster comes back online after the application has moved to the new cluster, enforce a **fencing/switchover policy**; otherwise you end up with two diverging "sources of truth" even if the initial backup was consistent.

## 19. Illustrative Lab: Writes Running Concurrently With Backup

The lab goal is not to break production, but to observe the difference between a **plain dump** and a **full dump with oplog** on a **test replica set**. Timings vary by machine/version; do not assume 30 writes alone will deterministically reproduce a specific inconsistency.

### 19.1. Preparing the Test Replica Set

Prerequisites:

- An initialized, healthy replica set `rsLab`.
- Appropriate backup/restore privileges.
- A dedicated **`backup342_lab`** database.
- Two terminals: one running the writer, one running `mongodump`.
- A restore target **separate from source**, empty, containing no valuable data.

**Never** use a production cluster or customer-facing Atlas deployment for the delete/restore exercises in this lesson.

### 19.2. Creating Fixtures

In `mongosh` on the lab replica set:

~~~javascript
const lab = db.getSiblingDB("backup342_lab")

lab.wallets.insertMany([
  { _id: "A", balanceMinor: 100000 },
  { _id: "B", balanceMinor: 100000 }
])

lab.transfers.insertOne({
  _id: "SEED",
  from: "system",
  to: "system",
  amountMinor: 0,
  state: "SEED"
})

lab.events.insertMany([
  { _id: 1, label: "seed", createdAt: new Date() },
  { _id: 2, label: "seed", createdAt: new Date() }
])
~~~

**Run once.** Re-running will cause duplicate `_id` errors. To reset, act only on the verified lab database; never copy drop commands into other environments.

### 19.3. Terminal A — Generating Concurrent Writes

In `mongosh`:

~~~javascript
const lab = db.getSiblingDB("backup342_lab")

for (let i = 3; i <= 50; i++) {
  lab.events.insertOne({
    _id: i,
    label: "concurrent-write",
    createdAt: new Date()
  })
  sleep(100)
}
~~~

This is a strictly bounded loop of **50 or fewer** operations, not an infinite loop or load test. Re-running after inserts will hit duplicate `_id` errors; use a different lab database or shift ID ranges when repeating.

### 19.4. Terminal B — Plain Dump

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./plain.archive"
~~~

To observe real divergence, the corpus must be large enough for the dump to span concurrent writes. On a tiny fixture, the tool may finish before writers start; **seeing no error does not prove a plain dump is consistent under concurrent writes**.

### 19.5. Terminal B — Full Dump With Oplog

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./with-oplog.archive" \
  --oplog
~~~

This is the proper way to test an **online consistent logical dump of a replica set** per MongoDB Database Tools, provided no prohibited DDL runs and the tool succeeds. `--oplog` cannot be combined with `--db=backup342_lab`; it must be a full replica-set dump.

### 19.6. Restoring and Comparing

Restore each archive to **two empty, separate DR targets**:

~~~bash
# DR Target 1: plain dump, without oplogReplay.
mongorestore \
  --uri="mongodb://restoreuser@restore-plain:27017/" \
  --archive="./plain.archive"

# DR Target 2: full dump with oplog.
mongorestore \
  --uri="mongodb://restoreuser@restore-oplog:27017/" \
  --archive="./with-oplog.archive" \
  --oplogReplay
~~~

Do not restore both to the same target; never run against the live source. Verify:

~~~javascript
const lab = db.getSiblingDB("backup342_lab")

printjson({
  events: lab.events.countDocuments({}),
  wallets: lab.wallets.countDocuments({}),
  transfers: lab.transfers.countDocuments({})
})

printjson(lab.wallets.find().sort({ _id: 1 }).toArray())
~~~

Because writers may finish before/during/after the backup, **differing event counts between snapshots do not by themselves prove a consistency failure**. An earlier backup can be valid even without newer writes. The goal is understanding the **recovery point** and confirming restoration of a valid logical state.

### 19.7. Use Transactions to Better Demonstrate Invariants

You can write a writer executing atomic transfers instead of just inserting events. After restore, check:

1. Total `A + B` remains constant across internal transfers.
2. Every committed transfer ID corresponds to matching balances.
3. No half-applied transfer exists; verify data before/after the recovery point makes sense.
4. When comparing two backups, do not use raw counts to declare one corrupt merely because it is older.

With a tiny fixture, overlapping writes are probabilistic; rigorous verification requires a controlled test harness with deterministic concurrency/timestamps rather than a lucky single run.

### 19.8. Clean Up Safely After the Lab

Delete only clearly labeled test targets after verifying **the exact DR environment**. Retain logs and sample archives if used for training under appropriate security policies. Never delete production backups just because a test restore succeeded once.

## 20. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
|---|---|---|
| "If the BSON file restores, the backup is consistent." | Each collection could come from different timestamps. | Require point-in-time guarantees and business invariant checks. |
| "A plain dump is a snapshot as of its start time." | `mongodump` does not lock the whole DB; writes happen during scan. | Use `--oplog` on a replica set or a managed backup. |
| "`--oplog` works with `--db`." | The tool requires a full replica set dump. | Do not restrict namespaces when using `--oplog`. |
| "Dumping through `mongos --oplog` yields a cluster-wide snapshot." | `mongos` does not expose a cluster-wide oplog. | Use managed coordinated backups or the manual sharded runbook. |
| "`--oplogReplay` can be used for sharded restores." | Database Tools does not support it in that model. | Use a supported cluster restore mechanism. |
| "Dumping each shard within the same minute is enough." | Transaction commits and metadata ranges still misalign. | Need a global consistent cut or quiesced writes. |
| "Stopping the balancer is enough to back up a sharded cluster." | Cross-shard writes still run. | Manual procedures require stopping writes/schema operations. |
| "Having `readConcern:majority` equals a full snapshot." | Majority reads can still span different timestamps. | Snapshot timestamp and backup method are separate concerns. |
| "Majority writes ensure the latest backup." | Backups have their own recovery points and may lag. | Majority durability is distinct from RPO. |
| "Secondaries are always in sync with the primary." | Replication is asynchronous and can lag. | Check optimes/lag and backup recovery point. |
| "A live filesystem `cp` suffices for restore." | Files are copied at different times. | Use atomic volume snapshots or lock writes per docs. |
| "Sequential snapshots of separate data/journal volumes are safe." | The two snapshots can be out of sync. | Use proven atomic group snapshots or `fsyncLock`/quiesce. |
| "`fsyncLock` has no impact on users." | It can block writes and replication. | Use a backup node/maintenance window and always unlock. |
| "The journal is the same as the oplog." | Journal serves crash recovery; oplog serves replication/redo workflows. | Pick the right mechanism for the goal. |
| "Fast snapshot creation means fast restore." | Copying, replay, index builds, validation, and cutover take time. | Measure RTO via restore drills. |
| "A consistent snapshot means zero data loss." | Writes after point P are absent from the backup. | RPO is an independent criterion. |
| "The PITR window is infinite." | Restores are bounded by the configured retention window. | Monitor earliest/latest restorable points. |
| "If backup succeeds, no restore testing is needed." | Artifacts can be incompatible or missing keys. | Run periodic restore drills. |
| "A good checksum proves the database is valid." | It only proves file bytes are intact. | Requires restoring + checking invariants. |
| "Using transactions makes plain dumps consistent." | Backups read data across different times. | Transactions and backup snapshot boundaries are independent. |
| "If the app writes non-atomically, backups will fix it." | Snapshots faithfully capture intermediate states. | Fix application transaction/outbox logic. |
| "MongoDB backups include Kafka offsets and S3 objects." | Outside DB backup scope. | Design multi-system recovery and replay. |
| "Outbox means restores cannot duplicate events." | Restores can revert to unsent states. | Use idempotent consumers and stable event IDs. |
| "A same-site physical snapshot is enough for DR." | Site/storage/credentials can all fail together. | Use offsite/immutable copies and restore drills. |
| "Having the archive means just chmod and restore." | Missing roles/KMS/FCV/version/topology can fail. | Verify prerequisites before an incident. |
| "Indexes/data are immediately complete after restore." | Logical restores rebuild indexes; Search indexes re-sync. | Measure RTO until features are ready. |
| "Backing up one collection covers multi-collection transactions." | Relationships can drift out of sync. | Define proper logical scope and consistency strategies. |
| "Any `--oplogLimit` works for PITR." | Replaying wrong partial ranges causes inconsistency. | Use managed PITR or proven specialized oplog procedures. |
| "FCV upgrades do not affect backups." | Time-series format conversions between 8.x and 9.0 cannot be replayed. | Avoid backups spanning format transitions; test restores. |
| "If restore fails, re-run over the partial data." | Target may be partial/inconsistent. | Reset the authorized DR target and restore from scratch. |
| "Restore into live production receiving writes for speed." | Causes conflicts and data loss. | Restore into an isolated target, validate, then cut over. |
| "After cutover, let the old cluster keep accepting writes." | Causes split brain and diverging data. | Fence the old primary/writers and control switchover. |

### 20.1. Separating Three Diagnostic Questions

~~~text
Is the backup file complete?
  -> checksum, file size, tool exit code, transfer logs

Is the backup point-in-time consistent?
  -> method, oplog/snapshot metadata, tool docs, restore invariants

Does the backup meet RPO/RTO?
  -> actual recovery point, restore duration, app readiness
~~~

Never use a single "backup success" status to substitute for all three evaluations.

## 21. Scenario Exercises and Solutions

The exercises below use **hypothetical** figures and systems; they are not outputs of a real backup run. When asked to pick a command, apply it only on a **replica set/sharded lab or DR target** with proper permissions—never run restore or write-locking operations on production.

### Exercise 1 — Two Collections Dumped at Different Times

**Prompt:** `mongodump` reads `wallets` at 09:00, reads `transfers` at 09:05, and a transaction commits at 09:03. Does the dump definitely reflect a single point in time?

**Answer:** No, if using a plain dump without snapshot/oplog mechanisms. `wallets` may precede T while `transfers` follows T. Use an online full replica-set dump with `--oplog` or a supported managed point-in-time backup.

### Exercise 2 — Valid BSON Yet Balances Do Not Reconcile

**Prompt:** After restore, every collection parses cleanly, yet total `wallet.balanceMinor` is short by 20,000 compared to the ledger. What should you investigate first?

**Answer:** Inspect the **backup consistency method**, recovery timestamp, transaction boundaries, and whether the restore replayed the oplog. Also inspect whether application logic uses atomic transactions on writes. Valid BSON files do not rule out timestamp skew or pre-backup business bugs.

### Exercise 3 — When to Use `--oplog`

**Prompt:** A 3-node replica set is actively serving writes; you need a full logical backup without stopping writes. Which tool/flags do you choose?

**Answer:** `mongodump --oplog` for a **full dump of a replica set member** on supported Database Tools/versions; restore with `mongorestore --oplogReplay` and validate. Avoid DDL operations that abort the dump and monitor the oplog window.

### Exercise 4 — `--oplog` Combined With `--db`

**Prompt:** A developer runs `mongodump --db app --oplog` and gets an error. Why?

**Answer:** `--oplog` requires a **full replica set dump** and cannot be combined with `--db`, `--collection`, `--query`, or other narrowing flags. To back up a single DB, use a different method and do not claim a full point-in-time guarantee.

### Exercise 5 — Restoring Without `--oplogReplay`

**Prompt:** A team has a full `--oplog` dump but restores using only `mongorestore --archive=file`. Is the intended consistency guaranteed?

**Answer:** No. Without replaying the oplog, the dumped documents may reflect multiple timestamps. You must use `--oplogReplay` per the format/conditions and inspect logs.

### Exercise 6 — Selecting One Collection During Oplog Replay

**Prompt:** Can you run `mongorestore --oplogReplay --nsInclude="app.wallets"` on a full dump?

**Answer:** No, per Database Tools limitations. Oplog replay for a full replica-set dump does not support arbitrary `--db`, `--collection`, `--nsInclude`, `--nsExclude`, `--nsFrom`, or `--nsTo`. Design a separate selective restore procedure if needed.

### Exercise 7 — Is Dumping a Secondary Automatically Consistent?

**Prompt:** Because the backup runs on a secondary, someone says `--oplog` is unnecessary. Are they right?

**Answer:** No. A secondary continuously applies oplog writes while the dump scans, and can also lag. `readPreference:secondary` reduces primary load; it **does not freeze a snapshot**. For a consistent full replica-set logical backup, evaluate `--oplog` and the recovery point.

### Exercise 8 — Majority Reads

**Prompt:** Two collections are read with `readConcern:"majority"` before and after a majority-committed transaction. Is this a single snapshot?

**Answer:** No. Each read can occur at a different timestamp, even though returned data is majority-committed. **Majority visibility ≠ global snapshot timestamp**.

### Exercise 9 — Majority Writes and RPO

**Prompt:** A write at 10:02 receives `w:"majority"` ack. The backup recovery point is 10:00. Will the restore include the 10:02 write?

**Answer:** No. The backup reflects state only up to its recovery point. Majority write concern does not retroactively alter an earlier backup's timestamp. This is an RPO question.

### Exercise 10 — `w:1` and Elections

**Prompt:** A client receives a `w:1` ACK, but the primary fails before the entry is majority-replicated. After an election, what can happen to that write?

**Answer:** It can be rolled back. If strong durability is required for business transactions, evaluate `w:"majority"` with appropriate write concern settings. Do not treat a primary ACK as proof every secondary or backup holds the write.

### Exercise 11 — Is the Journal the Oplog?

**Prompt:** An operator copies journal files and claims they can replay to any timestamp in the past week. True?

**Answer:** No. The WiredTiger journal handles **crash recovery**, while the oplog powers replication and certain log-based backup/PITR workflows. The journal is not a week-long continuous archive by default.

### Exercise 12 — Single-Volume Filesystem Snapshot

**Prompt:** Data and journal share one atomic snapshot volume on a replica set secondary. Writes continue on the primary. What can be guaranteed?

**Answer:** With storage/tooling compliant with MongoDB procedures, the snapshot can capture a **crash-consistent image of that secondary node**. However, it may be **stale** due to replication lag and does not form a global point for a sharded cluster. Test-restore and check business invariants.

### Exercise 13 — Data and Journal on Separate Volumes

**Prompt:** The data volume is snapshotted at 10:00 and the journal volume at 10:01 while writes run. Is that safe?

**Answer:** Not guaranteed. The two volume snapshots can be out of sync. Per the MongoDB filesystem snapshot tutorial, you must **lock/pause writes** when data and journal sit on separate volumes, or use a proven atomic group snapshot mechanism.

### Exercise 14 — Live `rsync` of Data Directory

**Prompt:** A cron job runs `rsync -a /var/lib/mongodb /backup` hourly while `mongod` writes. Can this be called a consistent hot backup?

**Answer:** No. `rsync` reads files sequentially without freezing the full data/journal set at one point in time. Use atomic filesystem snapshots or supported MongoDB backup methods.

### Exercise 15 — `fsyncLock` on the Primary

**Prompt:** A team runs `db.fsyncLock()` on the primary during peak hours to take a snapshot. What happens?

**Answer:** It can **block writes and degrade availability/latency**, violating the "writes keep running" requirement. Use only under an approved runbook, typically favoring a backup secondary or managed backup; **always unlock** safely.

### Exercise 16 — Insufficient Oplog Window

**Prompt:** A dump takes 2 hours, while the oplog window drops to 40 minutes during a flash sale. What should be done?

**Answer:** There is a high risk of losing needed history. Monitor errors/lag, carefully increase capacity/oplog retention, or reduce dump duration/throttle/adopt a managed solution. Never mark a backup successful if the tool reports an oplog gap.

### Exercise 17 — Shards Backed Up at Different Times

**Prompt:** Shard A is snapshotted at 12:00:00 and Shard B at 12:01:00; a cross-shard transaction commits at 12:00:30. Result?

**Answer:** Only one shard may reflect transaction T; the restored cluster is inconsistent. Use a coordinated cluster-wide backup or a manual procedure with writes quiesced.

### Exercise 18 — Backing Up via `mongos --oplog`

**Prompt:** Can you run one `mongodump --oplog` against `mongos` for an online backup of all shards?

**Answer:** No. `--oplog` on `mongos` **does not guarantee a global point-in-time snapshot**, and Database Tools does not support using it as a replica-set-style full backup for sharded clusters.

### Exercise 19 — Balancer Moving Chunks

**Prompt:** While dumping each shard, the balancer moves a range from Shard A to B. What can go wrong?

**Answer:** Data can be **duplicated or omitted** when shards are captured at mismatched points/metadata. Manual backups require stopping the balancer, waiting for migrations to complete, and pausing writes/schema transformations per the tutorial.

### Exercise 20 — Config Server Metadata

**Prompt:** An operator backs up all shard data files but skips config server state. Is that enough to restore the topology?

**Answer:** No. The config server holds chunk/range ownership and sharding metadata. Full cluster restores require compatible metadata; never hand-edit `config.*` to "patch" range mappings.

### Exercise 21 — Can Atlas Cloud Backup Run While the Cluster Writes?

**Prompt:** An Atlas sharded cluster has managed backups enabled; the business cannot stop writes. Do we need to run `fsyncLock` manually on all shards?

**Answer:** Generally **no** with **Atlas managed coordinated backup**, as Atlas provides cluster-wide snapshot coordination. Still verify tier/version/policy, backup permissions, and restore target constraints. Do not force manual filesystem-snapshot steps onto the managed service as mandatory.

### Exercise 22 — Snapshots vs. Continuous Cloud Backup

**Prompt:** Atlas only has hourly snapshots, with Continuous Cloud Backup disabled. An incident happens at 10:49, and the latest snapshot is 10:00. Maximum data loss?

**Answer:** Nearly **49 minutes of writes** after the 10:00 snapshot could be lost (in this hypothetical scenario). The snapshot may be perfectly consistent yet **fail a 5-minute RPO target**. Continuous/PITR or a policy adjustment is needed.

### Exercise 23 — PITR Prior to an Accidental Delete

**Prompt:** A bad delete commits at 09:17 and is detected at 09:18; the PITR window covers 09:16:59. What should you do?

**Answer:** Select a **verified recovery point before the delete** matching Atlas timestamps/semantics, restore to an appropriate DR target, validate data, and then cut over/reconcile. Do not blindly type an approximate clock time and assume the bad op is excluded.

### Exercise 24 — One-Day PITR Window

**Prompt:** An accidental delete occurred 3 days ago and the PITR window is only 24 hours. Can you pick a PITR point right before that delete?

**Answer:** Not if the restore point has fallen outside the history window. You may inspect older retained snapshots or external data copies, but never promise infinite arbitrary-time PITR.

### Exercise 25 — Low RPO Yet High RTO

**Prompt:** PITR loses at most 1 minute of data, but restoring 10 TB and rebuilding indexes takes 7 hours. Does the system meet a 1-hour RTO SLA?

**Answer:** No. Low RPO does not guarantee low RTO. Measure end-to-end restore/cutover, optimize topology/restore methods, evaluate hot standbys if appropriate, and plan read-model/index rebuilds.

### Exercise 26 — In-Place Restore Into a Populated Target

**Prompt:** An operator selects a cluster-level restore directly onto a live user-facing cluster. Risks?

**Answer:** Cluster-level restores can **overwrite existing target data** and cause downtime; concurrent writes during restoration are also hazardous. Prefer a new/isolated DR target, verify, and cut over if architecture permits.

### Exercise 27 — Restore Fails Midway

**Prompt:** `mongorestore --oplogReplay` is killed after loading several collections. Should you re-run the same command on the half-restored target?

**Answer:** No. Inspect logs, keep the source backup immutable, **reset/recreate the authorized DR target**, and restore from scratch; validate the full result. Never run `--drop` on an unverified cluster.

### Exercise 28 — SHA256 Matches Yet Ledger Is Off

**Prompt:** Source and destination checksums match, yet post-restore data is missing a payment record matching an order. Does the checksum rule out consistency bugs?

**Answer:** No. A checksum only ensures file bytes did not change during transit/storage. The backup may have used an inconsistent method or the app may have written non-atomically. Investigate recovery points/transactions and business checks.

### Exercise 29 — Kafka Event Sent After Backup

**Prompt:** A 10:00 MongoDB backup has outbox E1=NEW, Kafka receives E1 at 10:01, and MongoDB restores to 10:00. What will the worker see?

**Answer:** The worker will see E1 unsent and **re-send it**; consumers must enforce stable event IDs/idempotent processing to avoid double side effects. This is not necessarily a backup bug.

### Exercise 30 — Object Storage and DB Restore

**Prompt:** MongoDB restores to a point with a record pointing to an S3 file, but the file was later deleted from S3 without versioning. Is the document usable?

**Answer:** Possibly not. MongoDB backups do not contain external object bytes. Coordinate object-storage retention/backups and verify references after restoring.

### Exercise 31 — TTL Immediately After Restore

**Prompt:** Restoring a collection with a 7-day TTL from a 10-day-old snapshot causes some documents to vanish once the service starts. Is the backup definitely inconsistent?

**Answer:** Not necessarily. The TTL monitor deletes expired documents per policy after restoration. Inspect TTL indexes, logical clocks, and state at the recovery point before concluding corruption.

### Exercise 32 — Search Not READY Yet

**Prompt:** MongoDB collections are restored, yet the Atlas Search API returns sparse results or is unavailable. Why?

**Answer:** Search index data may require **rebuild/initial sync** after index definitions are restored. RTO must include search readiness, not just database CRUD.

### Exercise 33 — MongoDB 8.x → 9.0 FCV Conversion

**Prompt:** `mongodump --oplog` runs on a deployment with time-series collections while FCV transitions from 8.x to 9.0. Can the backup be assumed consistent?

**Answer:** No. Database Tools docs warn the oplog can span a **time-series format conversion** that `mongorestore --oplogReplay` cannot replay directly; Tools 100.18.0+ may fail rather than produce an unrestorable backup. Avoid version/FCV transitions during backup windows and consult exact branch docs.

### Exercise 34 — Balancer Disabled While Writes Continue

**Prompt:** A team stops the balancer and sequentially backs up the config server and shards while apps keep writing. Is there a global consistent point?

**Answer:** Not guaranteed. Stopping the balancer only halts range migrations; **cross-shard writes/transactions** can still occur between snapshots. Manual procedures require pausing writes/schema transformations, or using managed coordinated backups.

### Exercise 35 — "Taking Snapshots at the Same Wall-Clock Time"

**Prompt:** Two nodes have synced NTP and each is snapshotted at 10:00:00 ±20 ms. Can you claim cross-shard transaction atomicity?

**Answer:** No. Accurate wall-clock time does not automatically create a distributed consistent cut across committed writes/metadata, especially given transaction protocols and replication delay. You need a supported coordination/recovery protocol.

### Exercise 36 — Backup Artifacts Stored in the Same Production Account

**Prompt:** A compromised cloud admin can delete both production and backups in the same account. What should be added?

**Answer:** Separate backup accounts/permissions, immutable/offsite copies, independent encryption/KMS controls where feasible, auditing, and restore drills. Backups must survive a production-plane compromise.

### Exercise 37 — Is One Count Enough in a Restore Drill?

**Prompt:** After restore, `db.orders.countDocuments({})` matches the source at an estimated timestamp. What else should be checked?

**Answer:** Payment/order relationships, transfer ledger totals, unique IDs, indexes, permissions, query availability, restore tool logs, recovery timestamps, external events, and actual RTO. Matching counts do not prove identical data.

### Exercise 38 — Choosing a Method for Online Sharded SaaS

**Prompt:** 12 shards, 24/7 traffic, cross-shard transactions, few-minute RPO; the team proposes 12 parallel `mongodump --oplog` cron jobs. Does that make sense?

**Answer:** No. Individual oplogs do not produce a global consistency point, and config metadata plus chunk placement must align too. Prefer topology-supported managed coordinated backups/PITR or another proven solution. Never stitch 12 outputs into a supposedly consistent backup.

### Exercise 39 — Choosing a Method for a Small Replica Set

**Prompt:** A 3-node, 120 GB replica set with a backup secondary, continuous writes, needing nightly logical backups, tolerating a 24h RPO. Suggested design?

**Suggested Answer:** Full `mongodump --oplog` from a healthy secondary with sufficient oplog window and no concurrent DDL, offsite archive with checksum, restored via `--oplogReplay` to DR, with job/replication monitoring and periodic drills. If a lower RPO is needed, evaluate managed PITR or higher-frequency/appropriate methods.

### Exercise 40 — Designing a DR Plan for a Marketplace With Kafka and S3

**Prompt:** System has sharded MongoDB, Kafka payment events, S3 invoice PDFs, and Redis cache. RPO is 5 minutes and RTO is 1 hour; writes cannot stop for backups. Propose a verifiable design.

**Suggested Answer:**

1. Use **managed cluster-wide consistent backup/PITR** for sharded MongoDB on a supported tier/region/version.
2. Choose recovery point P within the PITR window using verified audit/timestamps.
3. Define Kafka offset/eventId replay and consumer idempotency; do not expect a MongoDB restore to rewind Kafka to P.
4. Configure S3 versioning/retention so restored documents never point to deleted files.
5. Invalidate/warm Redis after cutover; Redis is not a source of truth.
6. Restore to a compatible DR cluster, verifying cross-shard transaction invariants and payment/order counts.
7. Budget time for Search indexes, caches, connection cutover, and role/KMS validation.
8. Monitor actual RPO, measured RTO, and post-switch error/duplicate rates.
9. Enforce fencing so the old cluster cannot accept concurrent writes; run periodic drills proving the 1-hour RTO is achievable.
10. Alert whenever backups, PITR windows, KMS access, or DR drills fall short of policy.

No single MongoDB command makes **every** external system consistent. A sound plan defines data boundaries and application-wide replay/repair mechanisms.

## 22. Quick Decision Table by Topology and Goal

| Context | Can Writes Continue? | First Option to Consider | Pitfall to Avoid |
|---|---|---|---|
| Standalone lab, non-critical data | Quiesce or inconsistent dump acceptable where appropriate. | Test dump/restore, explicitly note guarantee level. | Calling a plain dump a consistent snapshot. |
| Replica set, full logical backup, 24/7 writes | **Yes** when conditions are met. | `mongodump --oplog` + `mongorestore --oplogReplay`. | Adding `--db`/`--collection` or skipping replay. |
| Replica set, fast physical backup, single atomic volume | Yes per supported storage procedures. | Filesystem snapshot of data+journal on one member. | Live `rsync`/`cp` or omitting the journal. |
| Replica set, journal/data on separate volumes | Requires quiesce/atomic group strategy. | `fsyncLock` and snapshot per Manual; consider secondary. | Snapshotting two volumes at different times while writing. |
| Self-managed sharded cluster, brief write pause allowed | **No** during required manual backup window. | Sharded-cluster manual backup tutorial and coordinated maintenance. | Stopping only the balancer without stopping writes. |
| Sharded cluster, cannot pause writes | Yes, via coordinated service. | Atlas/Ops Manager/Cloud Manager coordinated backups. | Stitching separate replica-set backups without a global cut. |
| Minute-level RPO requiring timestamp selection | Yes, with PITR enabled and sufficient window. | Continuous backup + point-in-time restore. | Running only hourly snapshots while promising 1-minute RPO. |
| Requirement to restore one collection selectively | Depends on method/business invariants. | Dedicated selective restore/migration plan. | Combining `--oplogReplay --nsInclude` against tool rules. |
| System includes Kafka/S3/payment service | MongoDB backup alone is insufficient. | DB PITR + external replay/versioning/idempotency. | Treating MongoDB backup as a whole-system transaction. |
| Production with large search indexes | Restoring data alone does not meet RTO. | Include index rebuild/warmup and query readiness. | Stopping the RTO clock as soon as BSON finishes restoring. |

### 22.1. Method Selection Flow

~~~text
Is the topology a single replica set?
  |
  +-- Yes:
  |     Need full logical backup while writes continue?
  |       -> mongodump --oplog (matching version/constraints)
  |       -> mongorestore --oplogReplay on restore
  |
  |     Need physical snapshot?
  |       -> atomic storage group + full data/journal
  |       -> if separate volumes: fsyncLock/quiesce per Manual
  |
  +-- No: sharded cluster?
        |
        +-- Must keep writes running?
        |     -> coordinated managed backup/PITR
        |
        +-- Have a write-pause maintenance window?
              -> manual sharded backup procedure
              -> stop balancer + writes + schema transformations

Need RPO lower than snapshot interval?
  -> PITR/continuous captured changes.

Need full application recovery?
  -> MongoDB + Kafka/S3/Redis/payment + invariants.
~~~

### 22.2. Three Pieces of "Evidence" to Retain After Every Backup

1. **Backup completion evidence:** Job ID, exit status, artifact paths, checksum, tool/server versions, backup recovery point.
2. **Consistency evidence:** Method guarantee per docs, oplog/snapshot/cluster coordination state, no DDL conflicts, restore-tested business invariants.
3. **Recoverability evidence:** Passing DR drill, real recovery duration, indexes/permissions/keys ready, recorded RPO/RTO.

Not every backup needs an immediate test restore upon creation, but you need a **periodic testing strategy** and enough history to catch when a method stops guaranteeing recovery after version/FCV changes.

## 23. Official MongoDB Documentation

Use the links below to verify syntax and limitations by **MongoDB Server version, Database Tools version, and managed cluster tier**. `/manual/` pages generally reflect the current release; if production runs an older branch, switch to the matching documentation version before running operations.

### 23.1. Logical Dump and Oplog Replay

1. [`mongodump` — Database Tools](https://www.mongodb.com/docs/database-tools/mongodump/) — `--oplog`, full replica-set dump, incompatible flags, DDL failure cases, `mongos` limitations.
2. [`mongodump` Behavior, Access and Usage](https://www.mongodb.com/docs/database-tools/mongodump/mongodump-behavior/) — BSON/index definition output, read preference, scope/exclusions.
3. [`mongorestore` — Database Tools](https://www.mongodb.com/docs/database-tools/mongorestore/) — `--oplogReplay`, full restore constraints, `--oplogLimit`, and archive/directory formats.
4. [`mongorestore` Behavior, Access and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/) — mid-restore failures, transaction/oplog restrictions, time-series FCV format conversion.
5. [MongoDB Database Tools Documentation](https://www.mongodb.com/docs/database-tools/) — comparing Database Tools and server/FCV versions.

### 23.2. Filesystem Snapshots and Sharded Clusters

6. [Back Up a Self-Managed Deployment with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/) — WiredTiger data/journal, atomic volumes, `fsyncLock` for separate volumes, restore.
7. [Back Up a Sharded Cluster with File System Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/) — stopping writes/balancer/DDL and backing up config servers + shards.
8. [Back Up a Self-Managed Sharded Cluster with a Database Dump](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-database-dumps/) — manual sharded dump workflow and server patch-level compatibility.
9. [Backup and Restore a Self-Managed Sharded Cluster](https://www.mongodb.com/docs/manual/administration/backup-sharded-clusters/) — collection of procedures and cross-shard consistency warnings.
10. [Backup Methods for Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/) — comparing RPO/RTO, dumps, physical snapshots, and managed backups.
11. [Manage Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — `sh.stopBalancer()` and checking migrations during manual backups.
12. [`db.fsyncLock()`](https://www.mongodb.com/docs/manual/reference/method/db.fsyncLock/) — flush/lock for backup support and its impact on writes.
13. [`db.fsyncUnlock()`](https://www.mongodb.com/docs/manual/reference/method/db.fsyncUnlock/) — returning a node from locked state.

### 23.3. Replica Sets, Read/Write Concern, and Transactions

14. [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog window, retention, resizing, and replication log semantics.
15. [Read Isolation, Consistency and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — differences across local/majority/snapshot/causal consistency.
16. [Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot timestamps and support conditions.
17. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — majority acknowledgement and durability.
18. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transaction atomicity and distributed transactions.
19. [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/) — writes rolling back before majority commit.

### 23.4. Atlas Cloud Backup, PITR, and Restore

20. [Atlas Cloud Backup Overview](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/) — managing backup policies and eligibility.
21. [Atlas Architecture — Guidance for Backups](https://www.mongodb.com/docs/atlas/architecture/current/backups/) — cluster-wide snapshots, continuous backups, RPO/RTO.
22. [Dedicated Cluster Backups](https://www.mongodb.com/docs/atlas/backup/cloud-backup/dedicated-cluster-backup/) — how Atlas coordinates snapshots and captured changes.
23. [Recover a Point In Time with Continuous Cloud Backup](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/) — timestamp selection and restore windows.
24. [Restore from a Snapshot](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-snapshot/) — source/target topology, fallback snapshot consistency warning.
25. [Atlas Restore Overview](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-overview/) — prerequisites and avoiding traffic on targets.
26. [Troubleshoot Backup and Restore Failures](https://www.mongodb.com/docs/manual/troubleshooting/backup-restore-failures/) — oplog gaps, backup agents, restore failures.

### 23.5. Using Documentation Safely

Before running commands in production, always answer:

1. Is the backup source a **replica set member** or a **`mongos` sharded cluster**?
2. Does the method allow **writes to continue**, or only keep the daemon running while writes are locked?
3. How is the recovery point determined and where is it recorded?
4. Are there prohibited DDL ops, chunk migrations, FCV format conversions, or admin changes?
5. Is the oplog window sufficient relative to duration/lag?
6. Are restore target/version/FCV/topology compatible?
7. Are encryption keys, credentials, index definitions, and external dependencies covered?
8. Do you have invariant tests, RPO/RTO targets, and a safe cutover path?

## 24. Conclusion

**A backup created while MongoDB actively receives writes is trustworthy only if it can restore a valid data state at a defined logical point in time.** Complete BSON files, matching checksums, or a "backup completed" screenshot are **not enough** to prove consistency.

On a **single replica set**, `mongodump --oplog` paired with `mongorestore --oplogReplay` is a sound online logical backup approach, provided you perform a **full dump, maintain an adequate oplog window, avoid prohibited DDL, and test restores**. For **filesystem snapshots**, ensure atomicity across data/journal volumes and apply `fsyncLock`/quiesce per documentation where required. For **sharded clusters**, stitching per-shard backups does not yield a globally consistent point; manual backups require coordinated pausing of writes/balancer/schema changes, while systems requiring online cluster-wide snapshots are usually better served by **Atlas/Ops Manager/Cloud Manager coordinated backups**.

Finally, consistency does not equal **zero RPO**, and a DB backup does not automatically cover Kafka/S3/Redis or downstream business services. A reliable strategy combines **recovery-point policies, oplog/PITR coverage, offsite immutable backups, restore drills, business invariants, and a cutover runbook**. What matters most is not "how many GB were backed up," but **being able to restore the exact state required, within the allowed timeframe, without breaking application data commitments**.
