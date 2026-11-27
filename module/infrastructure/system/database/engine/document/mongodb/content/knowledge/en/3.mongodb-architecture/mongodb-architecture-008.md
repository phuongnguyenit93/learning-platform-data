# Distinguishing the Journal, the Oplog, and Backup Data in MongoDB

## Lesson Objectives

In MongoDB's architecture, the **journal**, **oplog**, and **backups** all relate to written data, yet they serve three distinct purposes. Confusing them easily leads to flawed designs: assuming a replica set replaces backups, or thinking the journal can undo an accidental delete command.

After this lesson, learners will be able to:

- Explain why the **WiredTiger journal** helps MongoDB recover after a process crash or power outage, and the role of checkpoints in that process.
- Describe how the **replica set oplog** records changes for primary–secondary synchronization, and understand the **oplog window**.
- Distinguish **restorable backups** from live operational data, internal checkpoints, the journal, and the oplog.
- Connect the three mechanisms with **write concern**, **replication**, **recovery point objective (RPO)**, and **recovery time objective (RTO)**.
- Choose the appropriate response when facing a crash, a lagging secondary, accidental data deletion, or total cluster loss.
- Practice inspecting the oplog, journal statistics, and producing a consistent dump for a test replica set.

> **Remember:** The journal supports recovering **a single node's durable state**; the oplog helps **replica set nodes stay caught up with changes**; backups provide an **independent recovery point** when live data is no longer correct or no longer exists.

---

## 1. Three Questions, Three Mechanisms

Suppose an application writes an order into MongoDB at 09:00, and then an incident occurs. The question you need to answer determines which mechanism helps.

| Question | Primary Mechanism | Why |
|---|---|---|
| A node unexpectedly loses power during writes; on restart, can durable writes not yet flushed to data files be recovered? | **Journal + checkpoint** | WiredTiger uses the on-disk log to recover changes since the latest valid checkpoint |
| The primary just modified an order; how do secondaries receive and apply that change? | **Oplog + replication** | Secondaries read operations from their sync source's oplog and apply them to their own data |
| A staff member accidentally deletes thousands of orders and the delete replicated to every node; how do you return to pre-delete data? | **Backup / point-in-time recovery** | You must restore from independently stored data and, if available, replay changes up to the desired point in time |

All three mechanisms can coexist in one system:

~~~text
                             Application
                                 |
                             Write data
                                 |
                                 v
                       Replica set PRIMARY
                       +------------------+
                       | Collections      |
                       | Indexes          |
                       | WiredTiger       |
                       | Journal +        |
                       | Checkpoint       |
                       |                  |
                       | local.oplog.rs   |
                       +------------------+
                                 |
                      Sync operations via oplog
                        /                    \
                       v                      v
                SECONDARY A              SECONDARY B
              +-------------+          +-------------+
              | Data        |          | Data        |
              | Journal     |          | Journal     |
              | Own Oplog   |          | Own Oplog   |
              +-------------+          +-------------+

          Independent backup system
          = snapshots/dumps + change history per policy
          = separate storage + tested restore procedure
~~~

**Note:** The diagram above illustrates conceptual flow. The WiredTiger journal is not streamed directly as a journal feed from primary to secondary. Replication uses the oplog; each node independently maintains durability of the data it writes using its storage engine mechanism.

---

## 2. What Is the Journal?

### 2.1. Role in the Storage Engine

With the **WiredTiger** storage engine, MongoDB uses **write-ahead logging (WAL)**: writing necessary information into on-disk journal files so recovery is possible after an unexpected process termination. The journal is an internal mechanism of **each individual `mongod`**; it is not a user-queryable database.

WiredTiger manages data on disk while holding ongoing modifications in memory. Periodically, it creates a **checkpoint** — a consistent data state written to data files. If the process stops right between two checkpoints, the journal helps replay eligible changes since the last checkpoint.

One way to picture it:

~~~text
Time on a single node
--------------------------------------------------------------------->
T0                     T1                    T2                  T3
|                      |                     |                   |
Checkpoint A           Write X               Write Y             CRASH
(consistent data)      (journaled)           (journaled)

On restart:
1. Read checkpoint A from data files.
2. Locate valid journal records after checkpoint A.
3. Apply needed records to restore a consistent state.

If X or Y was not yet durable in the journal before the crash,
it may be absent from the recovered state.
~~~

Key point: **an operation that has executed in memory does not automatically mean it has been durably persisted to disk**. Write concern acknowledgment rules determine when the application receives a success response.

### 2.2. What Does the Journal Record?

The WiredTiger journal stores storage-engine-level information to recover data modifications, including internal index modifications. It differs from a business audit entry like "user A modified order B for reason C."

MongoDB technical documentation describes WiredTiger creating journal records for write operations and their associated internal changes. The journal is **not designed** for applications to read as a document change-history table, query by collection, or pick a day from last month to restore.

On a self-managed system using WiredTiger, the journal usually resides under the data directory:

~~~text
<dbPath>/
  WiredTiger...
  collection-...
  index-...
  journal/
    WiredTigerLog.0000000...
    WiredTigerLog.0000000...
~~~

These are **files managed by the storage engine**. Never open, edit, delete, move, or manually "clean up" journal files while MongoDB is running. Doing so can corrupt the database or break recovery capability.

### 2.3. A Checkpoint Is Not a Backup

A checkpoint is an **internal consistency milestone** used by the storage engine to manage data files and recovery. WiredTiger creates checkpoints periodically; MongoDB documentation describes a default interval of 60 seconds. The journal supports recovering changes after the latest checkpoint.

A checkpoint:

- Lives inside the node's active dataset.
- Can be lost along with the disk or host.
- Is not a historical copy you can arbitrarily pick at restore time.
- Does not replace a backup mechanism stored in an independent location.

Therefore, saying "MongoDB already takes checkpoints so we don't need backups" is wrong.

### 2.4. What Does the Journal Protect Against and What Does It Not?

**The journal helps when:**

- The `mongod` process crashes.
- The operating system or host reboots unexpectedly.
- Data files do not yet reflect writes after the last checkpoint, yet the durable journal remains intact.

**The journal is not a direct solution when:**

- Documents were accidentally deleted and the delete succeeded.
- A mistaken bulk update command ran.
- The entire storage device holding both data files and the journal fails.
- Data is corrupted or encrypted by malware affecting live files.
- You want to restore the database to an arbitrary timestamp days ago.

The journal protects consistency and durability of state **that was accepted for writing**, without distinguishing valid business operations from human mistakes.

### 2.5. Versions and Exceptions to Remember

With **WiredTiger**, journaling is standard. Starting in **MongoDB 6.1**, MongoDB documentation notes journaling is always enabled, and legacy options to toggle journaling on/off were removed.

Do not generalize this to every storage engine: MongoDB Enterprise has offered an **in-memory storage engine** with different durability behavior because data resides primarily in memory without the same on-disk journal model. When reviewing production configurations, confirm the exact version and storage engine.

---

## 3. What Is the Oplog?

### 3.1. Operations Log for Replica Sets

**Oplog** stands for **operations log**. In a replica set, MongoDB maintains a system collection named **local.oplog.rs** that records data-modifying operations and certain replication-related activities.

When the primary receives a modification, the corresponding change event is written to the oplog. Secondaries pull new oplog entries from their sync source and apply them to keep their data copies up to date. Each replica set member maintains **its own oplog**; it is not a raw journal file copied verbatim across machines.

~~~text
PRIMARY                            SECONDARY
-------                            ---------
insert/update/delete
        |
        v
Data + oplog entry     ----->     Read new entry
                                      |
                                      v
                                 Apply change
                                      |
                                      v
                                 Secondary data
                                 Secondary oplog
~~~

A replica set helps a system continue serving when a node fails, provided topology and election conditions are met. However, **replication does not create an independent backup history**: a valid delete command on the primary is replicated to secondaries as well.

### 3.2. What Does an Oplog Entry Look Like?

An oplog entry has a BSON structure, typically containing a timestamp and operation details. Illustrative example **to show meaning**, not a promise of exact schema across all versions:

~~~javascript
{
  ts: Timestamp({ t: 1790000000, i: 1 }),
  op: "i",
  ns: "shop.orders",
  o: {
    _id: ObjectId("68f000000000000000000001"),
    orderNo: "ORD-101",
    status: "NEW"
  }
}
~~~

Common fields:

| Field | High-Level Meaning |
|---|---|
| **ts** | Logical timestamp ordering changes in the replication stream |
| **op** | Operation type; e.g. **i** (insert), **u** (update), **d** (delete), **c** (command), **n** (no-op) |
| **ns** | Namespace, typically formatted as **database.collection** |
| **o** | Operation payload in appropriate format |
| **o2**, **ui**, other fields | Supplemental metadata depending on operation type and version |

Do not build applications coupled to the raw oplog format. For consuming real-time data changes, prefer **MongoDB Change Streams**, which is the supported API. Change streams build on replication/oplog and use resume tokens, though they are not backups either.

### 3.3. The Oplog Is a Collection with Bounded History

**local.oplog.rs** is a **capped** collection. The oplog acts as a history buffer with managed capacity: as new writes arrive, older entries can be evicted to make room.

The **oplog window** is the time span between the oldest retained entry and the newest entry. For example:

~~~text
Oplog currently holds changes from Monday 08:00 to Wednesday 08:00
=> Oplog window is approximately 48 hours

A secondary loses connectivity from Monday 12:00 to Wednesday 09:00
=> Entries it needs may have already been evicted.
=> Incremental sync from its old position may no longer be possible.
=> An appropriate initial sync/resync procedure is required.
~~~

Distinguish clearly:

- **Oplog size:** the configured capacity for the oplog.
- **Oplog window:** the retained historical time span, which fluctuates with write rate.
- **Replication lag:** how far behind its sync source a secondary currently is.
- **Minimum oplog retention:** a setting that enforces keeping entries for at least a minimum number of hours; does not turn the oplog into a long-term backup.

As write throughput rises, the same oplog size typically yields a **shorter window**. MongoDB makes an exception in the capped oplog mechanism: the oplog can exceed its configured size to avoid evicting data still needed for the majority commit point. Thus, do not divide oplog size by write rate as an absolute SLA.

### 3.4. How Does the Oplog Help Recover a Secondary?

A briefly offline secondary can resume receiving missed entries if its sync source still holds the needed history. If the outage gap exceeds the window, incremental synchronization cannot continue and the node requires an **initial sync** or recovery procedure designed for that situation.

Thus, the oplog serves two closely related operational needs:

1. **Replicating changes from primary/sync source to secondaries.**
2. **Allowing lagging nodes to catch up** without copying the entire dataset, as long as sufficient history remains.

However, if a user accidentally drops or clears a collection and the operation is recorded in the oplog, secondaries execute the matching operation. The oplog has no concept of an "accidental delete."

---

## 4. What Is Backup Data?

A **backup** is a copy of data retained under policy so it can be restored if the live system loses data, receives corrupted/erroneous writes, suffers hardware failure, or needs to revert to a historical point. To qualify as a usable backup, besides the data copy you must have a **verified restore procedure**.

A backup set may consist of:

- **Logical copy:** BSON collections/documents and metadata produced by tools like **mongodump**.
- **Physical copy/snapshot:** on-disk state of data files captured by a consistent snapshot system.
- **Continuous change history:** oplog collected/stored separately by the backup system to support **point-in-time recovery (PITR)** where configured.
- **Operational metadata:** snapshot timestamp, version, topology, encryption, storage location, retention policy, and recovery info.

### 4.1. Logical Backups with mongodump

**mongodump** reads MongoDB data and exports BSON files alongside metadata. **mongorestore** restores from that format.

Example exporting a test database:

~~~bash
mongodump \
  --uri="mongodb://USER:PASSWORD@HOST:27017/?authSource=admin" \
  --db=shop \
  --out=./backup-shop
~~~

Command illustrated in Bash-style shell syntax; replace USER, PASSWORD, and HOST with lab details, and keep secrets out of shell history in real environments. If data is actively changing during the dump, a simple dump may **not reflect a single consistent point in time**.

In a replica set, **mongodump --oplog** records operations occurring during the dump window so restore can replay them to reach a consistent point-in-time state. This approach has clear limitations, explained later.

### 4.2. Physical Backups with Filesystem Snapshots

A filesystem snapshot copies the state of storage volume blocks at a point in time. For self-managed MongoDB, snapshots can be fast, yet **not every copy of `dbPath` taken while `mongod` is running is a consistent backup**.

For WiredTiger deployments, MongoDB specifies requirements regarding journaling and placing the journal on the same logical volume as data files so snapshotting a running `mongod` stays consistent. If data spans multiple volumes, snapshots must be coordinated consistently across volumes per official guidance.

For **sharded clusters**, consistent backups also require coordinating across shards and config servers while accounting for the balancer and metadata. You cannot randomly snapshot one shard and call it a cluster-wide backup.

### 4.3. Managed Backups on Atlas or Admin Tools

Backup services/tools automate snapshots, incremental backups, isolated storage, status tracking, and restoration. In Atlas, **Cloud Backup** and **Continuous Cloud Backup** offer different capabilities; PITR support depends on cluster tier, backup policy, and service configuration.

Crucially, **having a backup service does not mean every backup allows rolling back to any arbitrary second**. Verify the restore window, tier-specific capabilities, retention period, restore permissions, and costs.

---

## 5. Direct Comparison: Journal, Oplog, and Backups

| Criterion | WiredTiger Journal | Replica Set Oplog | Backup |
|---|---|---|---|
| Primary purpose | Crash recovery for an individual node | Replication and catching up on changes | Recovering data after failures/errors, at allowed milestones |
| Responsible layer | Storage engine | Replica set mechanism | Backup system/tools |
| Storage form | Internal log files under dbPath | **local.oplog.rs** collection | Dumps, snapshots, archives, or objects in a backup store |
| Scope | One process/node and its data files | Operations in the replication stream | Data, cluster, and metadata scope per backup policy |
| Retention duration | Per recovery needs since checkpoint | Bounded rolling window | Per schedule and retention policy |
| Recovering from a single `mongod` crash | **Yes**, if journal/data remain and writes were durable | **Not the primary crash-recovery mechanism** | Can restore, though slower and unnecessary if node self-recovers |
| Helping a secondary catch up | No | **Yes**, if required history remains | Can seed/restore a node via a separate process, not normal oplog sync |
| Recovering from replicated accidental delete | No | No, the delete is replicated too | **Yes**, if a pre-delete backup exists |
| Restoring to a chosen point in time | No | Oplog alone is insufficient | Possible with **PITR** given base backup + continuous change history |
| Replaces independent backups? | **No** | **No** | Forms the core of a backup/restore plan |
| Should apps access directly? | No | No for business flows; use Change Streams if needed | Through controlled backup/restore procedures |

An easily confused point: **backups can use the oplog**. In that setup, the backup system **collects and stores a copy of oplog history in an independent location**. That stored copy, replayable during restore, is part of the backup; the live rolling **local.oplog.rs** collection on a node is still not a backup.

---

## 6. Path of a Write Command Through the Journal and Oplog

Consider a replica set with three data-bearing members:

~~~text
          Client
            |
       insertOne()
            |
            v
      PRIMARY receives write
            |
        Data + oplog
            |
       WiredTiger journal
            |
        +---+------------------------------+
        |                                  |
        v                                  v
   SECONDARY A                        SECONDARY B
   Receives oplog entry               Receives oplog entry
   Applies change                     Applies change
   Own journal                        Own journal
~~~

Each mechanism answers a different class of question:

- **Execution:** Did MongoDB process the operation?
- **Node durability:** Was the operation durably persisted via journal/checkpoint?
- **Replication:** How many members satisfied the acknowledgment rule?
- **Historical recoverability:** Which backup can restore the database to an appropriate past milestone?

You cannot collapse all four questions into a single boolean "write is safe."

### 6.1. Role of Write Concern

Write concern lets applications request the desired acknowledgment level. Two basic parameters:

- **w:** number of members required to acknowledge, or **"majority"**.
- **j:** requires durable persistence to the on-disk journal on the acknowledging members.

Example in `mongosh` on a **test replica set**:

~~~javascript
db.getSiblingDB("shop").orders.insertOne(
  {
    orderNo: "ORD-201",
    amount: 450000,
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

At a high level:

| Configuration | Key Condition | Limitations to Understand |
|---|---|---|
| **{ w: 1 }** | Primary acknowledges per node conditions | Does not guarantee majority received the write; risks rollback on failover |
| **{ w: 1, j: true }** | Requires durable journal write on acknowledging member | Primary durability does not mean data is guaranteed to survive every primary election |
| **{ w: "majority" }** | Waits for majority members per write concern rules | Default journaling behavior depends on **writeConcernMajorityJournalDefault** and replica set config |
| **{ w: "majority", j: true }** | Combines majority acknowledgment with journal durability | Does not protect against accidental deletes, logical corruption, or cluster-wide loss; backups still needed |

**Version detail:** In modern MongoDB, the default write concern on many replica sets is **w: "majority"**, though exceptions exist with arbiters and custom configurations. Normally **writeConcernMajorityJournalDefault** is **true**, so majority write concern implies journaling; do not assume default behavior without inspecting actual topology and settings.

Furthermore, starting in MongoDB 8.0, majority acknowledgment rules have specific details regarding when members durably record the oplog versus when secondaries apply changes. Therefore, **majority acknowledgment does not mean every read query on every secondary immediately sees the new data**. If an application needs read/write ordering guarantees across operations, study read concern and causally consistent sessions.

### 6.2. The Journal Does Not Prevent Rollback on Failover

Suppose an application writes with **{ w: 1, j: true }** to an old primary. The primary's journal is durable, yet secondaries have not received the write. The primary loses connectivity and a secondary is elected as the new primary. A write not acknowledged by a majority can be rolled back when the old primary rejoins.

These are two distinct risks:

- **Crash of that node itself:** the journal can preserve that node's durable writes.
- **Primary change in the replica set:** depends on how many members acknowledged and potential rollback.

If data is critical, consider **majority write concern** with appropriate durability constraints. Do not use the journal to replace replication, nor replication to replace backups.

### 6.3. Write Concern Timeout Does Not Always Mean "Not Written"

If **wtimeout** expires, the application may receive a write concern error even though the primary already executed the operation. It is not automatically rolled back. When handling retries, design **idempotency** into APIs or transactions and verify actual state.

---

## 7. Where Do the Oplog and Backups Meet?

The oplog is not a backup, yet it can serve as a **change stream source** for a backup system aiming for consistency or point-in-time recovery.

### 7.1. Consistent Dump While the System Continues Taking Writes

Suppose dumping collections takes 10 minutes:

~~~text
10:00  Start mongodump
10:02  Finish dumping collection A
10:04  App moves an order from A to B
10:08  Dump collection B
10:10  Dump finishes
~~~

Reading collections sequentially while data continuously mutates produces a dump capturing collections at **different points in time**. Logical state across collections may be inconsistent.

On an eligible replica set, the command:

~~~bash
mongodump \
  --uri="mongodb://USER:PASSWORD@RS_HOST:27017/?replicaSet=rs0&authSource=admin" \
  --oplog \
  --out=./backup-rs0
~~~

saves the dumped data along with oplog entries generated during the dump window. When writing to a directory, the tool creates **oplog.bson** at the top level of the output.

You can then restore into a **dedicated test target environment**:

~~~bash
mongorestore \
  --uri="mongodb://RESTORE_USER:RESTORE_PASSWORD@RESTORE_HOST:27017/?authSource=admin" \
  --oplogReplay \
  ./backup-rs0
~~~

The purpose of **--oplogReplay** here is to replay the captured operations from the dump to reach a consistent state. Check permissions, namespaces, versions, metadata, and `mongorestore` options in matching documentation before executing.

**Constraints to remember:**

- **--oplog** works with a **full dump of a replica set member**; do not combine it with **--db**, **--collection**, **--query**, or incompatible scope-limiting flags.
- Do not assume running **mongodump --oplog** against **mongos** in a sharded cluster automatically yields a cluster-wide consistent backup. Sharded deployments need dedicated procedures.
- Certain administrative/DDL operations occurring during the dump can cause **--oplog** dumps to fail.
- Ensure sufficient oplog history for the dump duration, enough backup space, and test restores.
- **--oplog only captures the dump window**; it does not maintain continuous multi-day change history afterward.

The example above is a conceptual lab guide, not a command to run blindly against a live production cluster.

### 7.2. Point-in-Time Recovery (PITR)

**PITR** enables restoring a database to a **valid timestamp** within the recovery window. A typical PITR system needs:

1. A consistent **base backup/snapshot** at time T0.
2. A **continuous change stream after T0**, captured and stored separately, sufficient to recover to T1.
3. A verified **replay/restore procedure** selectively applying changes up to the exact target timestamp.
4. A **retention policy** ensuring both base backups and corresponding logs are still retained.

Example:

~~~text
01:00  Consistent snapshot S0
01:01  Normal updates
...
09:29  Last known good state
09:30  App accidentally deletes 50,000 documents
09:31  Delete replicates to secondaries
09:40  Incident discovered

With S0 + continuous change history through 09:29:
    Restore S0 -> Replay changes up to 09:29
    -> Can return to just before the accidental delete.

With only S0, no change history retained:
    Restore S0 -> Only 01:00 state exists,
    -> All valid updates from 01:00 to 09:29 are lost.
~~~

Selectable timestamps and actual granularity depend on backup capabilities, topology, data types, and retention policies. **You cannot take the live journal to arbitrarily "undo" successful writes from days ago.**

In Atlas, **Continuous Cloud Backup** is an example of a system using snapshots plus oplog history stored by the service in backup storage to support PITR per configuration. Not every Atlas tier or cluster shares the same features/restore window.

### 7.3. Oplog Window vs. PITR Window

These two concepts are often confused:

| Concept | Belongs To | Meaning |
|---|---|---|
| **Oplog window** | Oplog of a running replica set member | Time span of recent operations still retained on that member |
| **PITR window** | Backup service/system | Time span selectable for restore, based on snapshots and independently retained history |

A system with a 24-hour oplog window does **not automatically** have 24-hour PITR. Conversely, a backup platform can offload oplog history to separate storage to provide PITR longer than the current oplog window on a live member.

---

## 8. Choosing the Right Mechanism by Incident Type

### Scenario A — `mongod` Crashes Between Two Checkpoints

**Symptom:** Node restarts after power loss; data volume and journal remain intact.

**Primary mechanism:** WiredTiger recovers from the checkpoint and durable journal records.

**Response:** Monitor startup/recovery, inspect logs/health, verify member status and data integrity per runbook. Do not hastily copy/delete journal files by hand.

**Limitation:** Changes not durably persisted before the crash may be lost, depending on write concern and sync timing.

### Scenario B — A Secondary Loses Network for Several Hours

**Symptom:** Secondary lags behind primary; upon reconnecting, attempts to resume sync.

**Primary mechanism:** Oplog allows the secondary to catch up on missed operations.

**Response:** Check replication lag, oplog window, node health, write rate, and network. If the sync source no longer retains needed history, use initial sync/resync procedures.

**Limitation:** The secondary's own journal cannot substitute for oplog entries it never received.

### Scenario C — Primary Is Permanently Lost While Replica Set Retains a Healthy Majority

**Symptom:** Remaining nodes elect a new primary.

**Primary mechanism:** Replica set, election, write concern, and oplog/replication state.

**Response:** Verify election, ensure applications reconnect/retry cleanly, restore redundancy, and check whether any non-majority writes were rolled back.

**Limitation:** The lost primary's journal cannot deliver unreplicated operations to other members.

### Scenario D — Accidental Data Deletion Replicated to All Nodes

**Symptom:** After a `deleteMany` missing proper filters, data disappears on both primary and secondaries.

**Primary mechanism:** A pre-delete backup and PITR if configured.

**Response:** Halt harmful writes per runbook, preserve evidence, pick the right restore point, test restoring to an isolated cluster, and verify data before cutover.

**Limitation:** The replica set replicates the delete too. The journal recovers the post-delete state rather than reverting back before the delete.

### Scenario E — All Cluster Disks Fail or Data Is Hit by Ransomware

**Symptom:** No usable data files, journal, or oplog remain on any member.

**Primary mechanism:** Backups on independent storage—ideally immutable/isolated copies—and a rehearsed recovery procedure.

**Response:** Provision clean infrastructure, rotate/verify credentials, restore from a verified backup, validate checksums/consistency, and restart applications in a controlled manner.

**Limitation:** A three-node replica set where all three sit in the same failure domain or compromised account can still lose everything simultaneously.

### Quick Selection Table

| Incident | Journal | Oplog/Replication | Backup |
|---|---|---|---|
| `mongod` crash, disk intact | **Primary** | Supports replica set re-sync after restart | Fallback if local recovery fails |
| Brief secondary disconnect | Maintains local durability | **Primary** | Usually not needed |
| Secondary falls behind oplog window | Cannot bridge missing history | Insufficient for incremental catch-up | May assist node recovery depending on system |
| Primary failover | Preserves per-node durable writes | **Primary**, along with election/write concern | Disaster fallback |
| Accidental replicated delete/update | Does not restore old version | Replicates the bad operation too | **Primary** |
| Simultaneous loss of all live copies | Nothing left on disk | No source node left | **Primary**, if stored independently |

---

## 9. Practice: Observing a Test Replica Set

The commands below target a **lab replica set** with privileges to read status info, **without performing destructive configuration actions**. A standalone instance has a journal but lacks a replica set oplog stream; check topology before running.

### 9.1. Viewing Replica Set Status

In `mongosh`:

~~~javascript
rs.status()
~~~

Observe members, primary/secondary states, and relevant timestamps. Across MongoDB versions, response structures and status fields may vary.

### 9.2. Viewing the Oplog Window

~~~javascript
rs.printReplicationInfo()
~~~

Simulated example:

~~~text
configured oplog size:   2048MB
log length start to end: 86400secs (24hrs)
oplog first event time: ...
oplog last event time:  ...
now:                    ...
~~~

Interpretation:

- **Configured oplog size:** the configured oplog capacity.
- **Log length start to end:** time span between the oldest and newest operations still in the oplog.
- **Oplog first/last event time:** timestamps of the stored history boundaries.

This value changes with workload. The oplog window observed right now is **not a fixed 24-hour guarantee** for future days.

For scripts, retrieve structured object output via:

~~~javascript
db.getReplicationInfo()
~~~

### 9.3. Inspecting a Few Oplog Entries

Using a lab account with appropriate read privileges on system collections:

~~~javascript
db.getSiblingDB("local")
  .oplog.rs
  .find(
    {},
    { ts: 1, op: 1, ns: 1, o: 1 }
  )
  .sort({ $natural: -1 })
  .limit(5);
~~~

Inspect **ts**, **op**, **ns**, and **o**, then compare them with inserts/updates/deletes just run in your test database. Actual structure may differ from the example, especially with transactions, DDL commands, and newer versions.

**Never manually modify `local.oplog.rs`.** This is system data governing replication, not an application collection.

### 9.4. Viewing Journal Statistics

On a WiredTiger member, an account with monitoring privileges can query:

~~~javascript
const status = db.serverStatus();

printjson(status.wiredTiger?.log);
~~~

The **wiredTiger.log** group shows write counts, log volume, and journaling-related status. These are **operational metrics**, not a list of documents you can manually replay.

### 9.5. Testing Two Write Concern Modes

In a lab database, run two operations with different write concerns:

~~~javascript
const orders = db.getSiblingDB("lab").orders;

orders.insertOne(
  { _id: "wc-1", type: "w1" },
  { writeConcern: { w: 1 } }
);

orders.insertOne(
  { _id: "wc-majority", type: "majority-journal" },
  { writeConcern: { w: "majority", j: true, wtimeout: 5000 } }
);
~~~

Read both documents:

~~~javascript
orders.find({ _id: { $in: ["wc-1", "wc-majority"] } });
~~~

**Takeaway:** Both operations can produce identical documents under normal operation, yet **the meaning of a success response differs**. Never induce crashes or primary elections in a shared environment just to demonstrate failure. If doing fault injection, use an isolated lab with snapshots and reset scripts.

### 9.6. Practicing Intentional Backup and Restore

With a lab replica set:

1. Create sample data and record the total document count.
2. Run **mongodump --oplog** to take a full dump while generating a small stream of writes.
3. Verify the output contains dump data, metadata, and **oplog.bson** in the expected place.
4. Restore using **mongorestore --oplogReplay** into an **empty target `mongod`/cluster** dedicated to the exercise.
5. Count documents, verify sample records, and check indexes/metadata.
6. Record backup duration, restore duration, and readability of restored data.

The goal of this exercise is to see that **backups must be test-restored**, and the oplog captured by the dump tool **only ensures consistency within that backup session**. A dump folder that has never been test-restored does not prove the system is recoverable.

---

## 10. Designing a Backup Policy: RPO, RTO, and Isolation

### 10.1. What Is RPO?

**Recovery Point Objective (RPO)** is the maximum amount of recent data a business accepts losing when recovery is required.

For example, a 15-minute RPO means the recovery solution must be able to restore data to a point within roughly 15 minutes before the incident, under verified and committed conditions. A once-daily backup **is usually insufficient** for a 15-minute RPO without continuous change capture.

The journal and replica set reduce data-loss risk for specific failure classes, yet **they do not provide historical RPO for an accidental replicated deletion**.

### 10.2. What Is RTO?

**Recovery Time Objective (RTO)** is the maximum duration allowed to restore service after an incident.

For example, having a 2 TB dump that takes 10 hours to restore fails a 1-hour RTO even if the backup is readable. Snapshots and faster restore mechanisms may be required depending on scale.

RPO and RTO are separate requirements. Low RPO does not automatically mean low RTO.

### 10.3. Backups Must Be Isolated

A sound backup design typically requires:

- **Independent storage location** separate from live data files and the journal; avoid losing both production and backups in one disk failure.
- **Separate access controls, encryption, and key management**.
- **Retention policy** aligned with business and compliance requirements.
- **Cross-fault-domain copies** or immutability/tamper protection when required by risk assessment.
- **Automated alerting for failed backup jobs** or low storage/quota conditions.
- **Periodic restore drills:** restore into an isolated environment and verify consistency, data, indexes, permissions, and application functionality.
- **Clear runbooks** for choosing restore points, obtaining approvals, and cutting traffic over to restored data.

For sharded clusters or workloads with cross-collection transactions/dependencies, verify supported backup tools to guarantee consistency across all required components.

### 10.4. Layered Defense Strategy

You can picture a production strategy like this:

~~~text
Layer 1: Write concern + WiredTiger journal
         -> Protects durable writes against a single-node crash.

Layer 2: Replica set + adequate oplog window
         -> Increases availability; keeps secondaries caught up.

Layer 3: Separately stored snapshot/dump backups
         -> Recovers from data loss or business mistakes.

Layer 4: Continuous backup/PITR when needed
         -> Reduces loss of valid data since the prior snapshot.

Layer 5: Restore drills + runbooks + access controls
         -> Turns stored copies into proven recovery capability.
~~~

Each layer addresses a distinct risk class. Never omit the backup layer just because you already have journaling and a replica set.

---

## 11. Common Misconceptions

### "The journal and oplog are both logs, so they are interchangeable."

No. The journal records storage-engine operations for crash recovery; the oplog records operations for replication. Both being logs does not make their functions equivalent.

### "The journal can be replayed to go back to yesterday."

No. The journal is not a long-term operation history for administrators to pick restore points. WiredTiger manages it relative to checkpoints and local node recovery needs.

### "We have three secondaries, so we don't need backups."

No. Accidental deletes, bad updates, malware, or incidents hitting all members can still destroy good data across every copy. Replication propagates technically valid writes even when they are business mistakes.

### "A 72-hour oplog window means we can restore to any second in the last 72 hours."

No. The oplog alone lacks a matching base backup and a replay/restore pipeline. PITR requires a complete backup system and matching retention policy.

### "`mongodump --oplog` is Continuous Backup."

No. That flag captures oplog entries generated **during the dump window** to produce a consistent point-in-time dump. Capturing continuous changes after the dump requires dedicated backup/PITR infrastructure.

### "Just copying the `dbPath` folder while `mongod` is running is enough."

Not guaranteed to be consistent. You must use a MongoDB-supported snapshot method satisfying journal, volume, and topology rules, or follow proper write-quiesce procedures.

### "Writing with `j: true` guarantees zero loss ever."

No. Requesting journaling increases durability on the acknowledging node. It does not protect against total disk loss, infrastructure zone failure, or primary-failover rollback if the write lacked majority acknowledgment.

### "A write returning a timeout definitely wasn't saved."

Not necessarily. On a write concern timeout, the primary may have accepted the operation without yet meeting acknowledgment thresholds. Verify state and design safe retries.

### "A checkpoint and a filesystem snapshot are the same."

No. A checkpoint is an **internal WiredTiger consistency milestone**, whereas a filesystem snapshot is a storage-layer copy mechanism. A snapshot can participate in a backup system when taken and stored properly.

### "Atlas has backups, so point-in-time recovery is always available by default."

No. Backup/PITR availability depends on cluster type, tier, and enabled policies. Verify your **restore window**, retention, RPO/RTO, and actual recoverability.

---

## 12. Scenario Exercises

### Exercise 1 — Identify the Right Mechanism

For each symptom below, pick **journal**, **oplog**, **backup**, or **combination** and state its limitation:

| Scenario | Answer Direction |
|---|---|
| Node A crashes after the most recent checkpoint | Journal + checkpoint on A |
| Secondary B disconnects for 30 minutes; oplog window is 8 hours | Oplog, provided required operations remain |
| Bad update overwrites all product prices and replicates | Backup/PITR with a milestone prior to the bad command |
| Primary dies after `w: 1, j: true` write before replicating | Durable journal on old primary does not ensure data exists on new primary |
| Cluster simultaneously loses all disks and journals | Independent backup |
| Need a consistent dump of a replica set taking live writes | Proper backup tool, e.g., `mongodump --oplog` within its constraints |

### Exercise 2 — Calculate Potential Data Loss

A database has:

- Daily snapshots at **00:00**.
- No oplog history offloaded to backup storage.
- An accidental delete occurs at **17:30** and is noticed at **17:45**.
- The replica set remains healthy; all secondaries applied the delete.

Answer:

1. Can the deleted documents be recovered from the journal? Why or why not?
2. Do secondaries retain the pre-delete state on their own?
3. With only the 00:00 snapshot, up to how much valid update history could be lost upon restoring the snapshot?
4. To restore to **17:29:59**, what additional mechanism must the system be designed with?

**Guidance:** The live system's journal/oplog does not replace historical backups. Restoring to right before the delete requires PITR with a base backup plus continuous change history.

### Exercise 3 — Oplog Window and Secondary Lag

A secondary was offline for 10 hours. Previously the sync source's oplog window was 12 hours, but a heavy write burst during the outage shrank the window to 7 hours.

Explain why the secondary may fail incremental sync, and propose:

- How to check the actual window at recovery time.
- Which metrics to monitor: oplog window, replication lag, write rate, and member health.
- Remediation if missing entries have already been evicted from the sync source.
- Why increasing oplog size helps yet does not replace backups.

### Exercise 4 — Designing a Backup Policy

An e-commerce system has these constraints:

- Maximum RPO of **10 minutes** for data-loss incidents.
- Maximum RTO of **2 hours**.
- Production is a three-node replica set.
- Accidental deletes might only be discovered several hours later.
- Minimum 14 days of recovery history required.

Design a solution covering: base backups, continuous change capture, storage location, retention, restore drills, how to validate restore time, and access control. Relying solely on "three-node replication" will not satisfy historical recovery requirements.

---

## 13. Review Questions

1. Which layer of MongoDB does the journal belong to? How does it work with checkpoints?
2. Why is the journal not a place to look up document update history?
3. Which database/collection holds the oplog in a replica set?
4. How does a secondary use the oplog when it falls behind?
5. What makes the oplog window shrink even when oplog size stays constant?
6. Why can't a replicated accidental collection drop be undone simply via a secondary?
7. What is the difference between **w: 1, j: true** and **w: "majority", j: true**?
8. What problem does **mongodump --oplog** solve? Does it provide long-term PITR on its own?
9. What is the difference between an internal checkpoint and a filesystem snapshot used for backups?
10. Can a system be considered to have a backup strategy if restores have never been tested? Why or why not?

## 14. Summary

- The **journal** belongs to the WiredTiger storage engine and pairs with checkpoints to recover a node after a crash, bounded by which writes were durably persisted.
- The **oplog** is the recent operations log of a **replica set**, enabling secondaries to replicate and catch up on changes, bounded by the oplog window.
- A **backup** is data stored **independently and restorably**, serving recovery after accidental deletes, data corruption, disk loss, or disasters.
- **PITR** combines a base backup with separately captured and retained change history to restore to an appropriate point in time; the live oplog on a running node is insufficient for that goal.
- **Write concern, journaling, replication, and backups are complementary protection layers**, each with its own scope and preconditions.

When designing production MongoDB systems, start by asking **"Which failure types must we recover from, how much data loss is acceptable, and how fast must we restore?"**. Those answers determine how you configure journaling/write concern, replica sets/oplog, and backup/restore policies.

## Official References

- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/)
- [MongoDB Manual — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Backup Methods for Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Atlas — Continuous Cloud Backup and Point-in-Time Recovery](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Manual — rs.printReplicationInfo](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/)
