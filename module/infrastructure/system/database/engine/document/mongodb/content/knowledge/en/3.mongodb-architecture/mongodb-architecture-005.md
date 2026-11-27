# Journal, Checkpoints, and Crash Recovery in MongoDB

## 1. The Core Problem: Where Is Data When MongoDB Stops Unexpectedly?

When an application calls **insert**, **update**, or **delete**, MongoDB needs to process changes quickly while protecting data against scenarios such as an abrupt **mongod** process termination, an OS failure, or a power outage. If every single change forced flushing all modified data pages to disk before replying to the application, I/O cost would be high. Conversely, if changes were kept only in RAM, data could vanish on power loss.

MongoDB uses the **WiredTiger storage engine** with two complementary mechanisms:

- **Journal (write-ahead log, WAL):** records changes into a durable on-disk log so they can be replayed after a server crash.
- **Checkpoint:** writes a **consistent** data state from memory to data files and establishes a new recovery point.

These two mechanisms form the foundation for **crash recovery** on a single MongoDB instance. They do not replace replica sets, backups, or disaster recovery plans.

~~~text
                Java Application / mongosh
                          |
                          | insert / update / delete
                          v
                    MongoDB mongod
                          |
                  WiredTiger engine
                 /                 \
                v                   v
       Memory/cache            Journal buffer
       (modified pages)             |
                |                   | flush/sync
                |                   v
                |              Journal on disk
                |
                | periodic checkpoint
                v
          Data files on disk
          (consistent checkpoint)

       If mongod crashes: checkpoint + journal => recovery
~~~

The diagram above illustrates the **logical roles** of the components; internal execution order inside the storage engine can involve multiple write and sync steps. The central idea of a WAL is that recoverable changes are written to the journal under durability rules before a new checkpoint is treated as the safe data source.

### 1.1. Distinguishing Three Easily Confused Goals

| Goal | Question to Answer | Related Mechanisms |
|---|---|---|
| **Durability** | Once the system has acknowledged a write as successful, can the change withstand the required failure class? | Journal, checkpoints, write concern, durable storage. |
| **High availability** | When one node stops, does the system continue serving on another node? | Replica set, election/failover; with sharding, also depends on cluster components. |
| **Recoverability** | Can data and service be restored to an appropriate state after an incident? | Crash recovery, backup/restore, replication, recovery operations. |

For example: a standalone MongoDB instance with a journal can **recover data on the same disk after a process crash**, yet the application still experiences downtime while the server restarts. If the disk fails completely and loses both the journal and data files, the journal alone cannot save the system.

## 2. WiredTiger and the Storage Layers to Understand

WiredTiger is the default storage engine in modern MongoDB versions. It uses **Multi-Version Concurrency Control (MVCC)** together with a cache to support concurrent query processing, retain necessary data versions, and create consistent snapshots.

### 2.1. Cache and Dirty Pages

When a document is updated, related data/index structures can change in memory. Pages that have been modified but not yet written in their corresponding form to data files are called **dirty pages**.

You cannot conclude that:

> API returns success = every data page has immediately appeared in the collection file on disk.

Write responses also depend on **write concern**. WiredTiger does not need to immediately flush all dirty pages as a checkpoint for every request. The journal handles recording information to recover durability-guaranteed changes between checkpoints.

### 2.2. Data Files and the Journal Are Different

| Component | Primary Role | Characteristics |
|---|---|---|
| **WiredTiger cache** | Holds active pages and data, supporting efficient reads/writes. | RAM is volatile memory lost when powered off. |
| **Data files** | Store data/indexes maintained by the storage engine on disk. | Have a consistent state defined by a valid checkpoint. |
| **Journal files** | Store change records required for recovery. | WiredTiger's internal binary log, written/synced by the journaling mechanism. |
| **Checkpoint metadata** | Points to the latest valid data checkpoint. | Updated in a way that preserves the consistent milestone while a new checkpoint is being created. |

In typical configurations, journal files reside in the **journal** directory under **dbPath**, with names like **WiredTigerLog.0000000001**. MongoDB automatically manages, creates, and cleans up old journal files when they are no longer needed for recovery. **Do not delete or manually edit WiredTigerLog files** to free disk space.

### 2.3. The MongoDB Journal Is Not the Application Log or the Oplog

Three kinds of logs have distinct purposes:

| Type | Where Used | What Does It Do? |
|---|---|---|
| **WiredTiger journal** | Storage engine on each instance. | Replays local changes after a crash between checkpoints. |
| **Replication oplog** | **local.oplog.rs** collection on replica set members. | Provides an ordered operation stream for members to sync data and serves as a basis for some backup/PITR forms. |
| **MongoDB server log** | Log file/console output of **mongod**. | Records operational events, notices, warnings, and errors. |

You cannot use the regular server log to replay data, nor treat the journal as a business changelog for auditing. The journal has an internal format and lifecycle controlled by MongoDB.

## 3. How Does the Journal (Write-Ahead Logging) Work?

### 3.1. The Write-Ahead Log Concept

**Write-ahead logging** allows the storage engine to work efficiently in RAM while maintaining a reliable recovery path. For an operation updating a document and its indexes, WiredTiger creates journal records representing the necessary changes. Records may initially reside in a **journal buffer**, then be written/synced to the on-disk journal.

Conceptual model:

~~~text
T0: Application requests an update
           |
           v
T1: WiredTiger processes change; creates record in journal buffer
           |
           +------> Dirty data/pages may reside in cache
           |
           v
T2: Journal record is flushed/synced to disk
           |
           +------> Sufficient basis to recover journaled changes
           |
           v
T3: Subsequent checkpoint writes consistent snapshot to data files
           |
           +------> New checkpoint can become the recovery milestone
~~~

Crucially, **the moment the client receives acknowledgment is not fixed to T2 or T3**. It is governed by write concern and runtime conditions. A write that does not request journal acknowledgment can be acknowledged before its record is durable on disk.

### 3.2. When Is the Journal Synced?

With WiredTiger, MongoDB uses a periodic journal sync mechanism. According to MongoDB documentation, the default interval of **storage.journal.commitIntervalMs** is around **100 ms**; certain conditions can trigger an earlier sync, notably an operation requesting **write concern j: true**. On secondaries, oplog batch application mechanisms also influence journal syncing.

This leads to a key rule:

**A write still only in memory/journal buffer can be lost on a hard shutdown; a write already synced to the journal can be recovered as long as data files and the journal remain intact.**

100 ms is **the default flush interval configuration**, not an SLA promising every operation is durable within exactly 100 ms, nor a maximum recovery time. Actual sync latency also depends on I/O load and hardware.

### 3.3. What Does Each Journal Record Contain?

A client write operation can modify not only a document but also indexes. WiredTiger journal records include the internal changes associated with that operation. As a result, recovery can restore both data and indexes to a consistent state rather than merely replaying a high-level update expression.

For example:

~~~javascript
db.customers.createIndex({ email: 1 }, { unique: true })

db.customers.insertOne({
  _id: "C-101",
  email: "lan@example.test",
  status: "ACTIVE"
})
~~~

This insert affects both the collection data and the **email** index. WiredTiger journaling binds the necessary storage changes for the operation so recovery reproduces them consistently.

### 3.4. The Journal Is Not Kept Forever

As checkpoints advance, changes prior to the checkpoint milestone no longer need to be kept indefinitely in the journal for recovery from the new milestone. MongoDB manages rotation and cleanup of log segments that are no longer needed. You cannot rely on the journal to recover an arbitrary data state from days ago.

**The journal is not long-term version history and is not a backup.**

## 4. Checkpoint: Consistent Data State on Disk

### 4.1. What Problem Does a Checkpoint Solve?

If there were only a journal without a consistent data milestone, every restart could require replaying a very long history. A **checkpoint** writes a consistent data snapshot to data files to shorten recovery scope and establish a reliable starting point.

MongoDB configures WiredTiger to create checkpoints at an interval of roughly **60 seconds**. This is the default cadence for creating checkpoints; it does not mean the entire database is backed up to a separate file every 60 seconds, nor that every write waits up to 60 seconds to become durable.

### 4.2. Snapshots and Consistency

WiredTiger uses MVCC to view data at a given logical point in time. When a checkpoint finishes, the on-disk state must be consistent with that snapshot. This differs from arbitrarily copying mutable files while the database is running: files copied at different instants may not belong to the same consistent state.

~~~text
Checkpoint A (valid)
      |
      |    WiredTiger writes pages of checkpoint B
      |         [in progress]
      |                X  crash
      v
Recovery can still start from checkpoint A
and replay the appropriate journal entries.

Checkpoint A (valid)
      |
      |   Checkpoint B write completes
      |   Metadata switches to B atomically
      v
Checkpoint B (new valid checkpoint)
~~~

While a new checkpoint is being written, the previous checkpoint remains valid. Once data and metadata for the new checkpoint have been written successfully, WiredTiger updates metadata to point to the new milestone. If a crash occurs while building a checkpoint, this mechanism avoids relying on an incomplete new checkpoint.

### 4.3. A Checkpoint Does Not Mean Data After That Milestone Disappears

Example:

~~~text
09:00:00   Checkpoint C0 completes
09:00:15   Update order #A -> PAID, journal synced
09:00:40   Insert order #B, journal synced
09:00:48   mongod crashes
09:01:10   mongod restarts
~~~

If the data files and journal remain intact, MongoDB can start from C0 and **replay the records after C0 that were durably journaled**. There is no rule that all operations from 09:00:00 to 09:00:48 are lost simply because the next checkpoint had not run yet.

Conversely, if an operation was acknowledged to the application but **not yet durably synced to the journal** under the write concern used, a crash can still lose that operation. You must distinguish **acknowledgment time** from **journal sync time**.

### 4.4. Checkpoints Differ from Backup Snapshots

A checkpoint is an **internal storage engine mechanism**, residing within the live data system. A backup snapshot is an **independently managed data copy** intended for recovery after loss or corruption of the original environment. You cannot treat a checkpoint as a backup to restore on another system without following a MongoDB-supported backup method.

## 5. Crash Recovery: How Does MongoDB Recover?

**Crash recovery** is the automatic process of reconstructing a valid storage state when MongoDB restarts after an abnormal shutdown. With WiredTiger, the core logic is:

1. Read metadata/data files to identify the **latest valid checkpoint**.
2. Locate the journal record position corresponding to that checkpoint.
3. **Replay** the changes recorded in the journal that must be applied since the checkpoint.
4. Return the storage engine to a consistent state so MongoDB can resume serving.

~~~mermaid
flowchart TD
    A["mongod starts after crash"] --> B["Identify last valid checkpoint"]
    B --> C["Locate corresponding journal record"]
    C --> D["Replay needed changes after checkpoint"]
    D --> E["Restore consistent storage state"]
    E --> F["MongoDB completes startup to serve requests"]
~~~

The above describes local storage recovery. In a **replica set**, the node also undergoes replication state recovery, role determination, synchronization, and potentially other actions depending on the replica set's state. Therefore, `mongod` starting and completing journal replay successfully **does not mean that node immediately becomes primary**.

### 5.1. Typical Scenarios

| State When Failure Occurs | Recovery Behavior / Expectation |
|---|---|
| Dirty data only in RAM; journal record not synced. | Unpersisted changes may be lost after a hard crash. |
| Change synced to journal but not yet in a checkpoint. | Recovery can replay records to restore the change. |
| Crash while a new checkpoint is being written. | Uses the previous valid checkpoint, then replays appropriate journal entries. |
| New checkpoint written and metadata updated successfully. | New checkpoint milestone is used; changes after that milestone are replayed. |
| Normal shutdown (graceful shutdown). | Server has a chance to complete safe shutdown tasks; next startup is normally smoother than after a crash. |
| Loss/corruption of both data files and journal, or severe storage error. | Crash recovery cannot guarantee recovery; another healthy replica and/or valid backup is needed. |

The outcomes above assume the storage device, OS, and sync calls provide expected durability properties. Hardware failure, total disk loss, misdirected writes, or data corruption can exceed the scope of a WAL.

### 5.2. "Crash Recovery" Does Not Mean "Zero Lost Operations"

How many operations can be lost cannot be inferred solely from the checkpoint interval. To determine the guarantee for a specific write, check:

- Under which write concern was that write **acknowledged**?
- Was **j: true** requested?
- Did only one node crash, or did the entire replica set experience an outage?
- Are the disk and journal still intact?
- Did an **election/rollback** happen after the node restarted?

"MongoDB enables journaling by default" is different from "every request is acknowledged only after durable journal sync." The acknowledgment policy determines what the application is entitled to assume.

## 6. Write Concern Determines When the Client Is Told Success

MongoDB provides **write concern** so applications can specify the desired level of write acknowledgment. Two key factors are:

- **w:** the number/members of the replica set that must acknowledge the operation, or the **majority** rule.
- **j:** whether to require waiting for acknowledgment of durable persistence to the **on-disk journal**.

### 6.1. Common Guarantee Levels

| Write Concern | Intent | Notes |
|---|---|---|
| **{ w: 1 }** | Primary acknowledges the write per its mechanism. | Without requesting journal acknowledgment, an acknowledged write may not yet be synced to the journal; also risks rollback upon primary change. |
| **{ w: 1, j: true }** | Waits for durable journal write on the acknowledging node. | Better protection against a **local crash on that node**; does not protect against disk loss or rollback due to replica set election. |
| **{ w: "majority" }** | Waits for the majority rule in the replica set. | Default journaling behavior depends on **writeConcernMajorityJournalDefault**; typically **true**, making majority acknowledgment wait for appropriate journal durability. |
| **{ w: "majority", j: true }** | Explicitly requires both majority and journal durability. | Suitable when business logic needs stronger protection against failover; may increase latency or time out if insufficient nodes are up or disks are slow. |

**Two different questions:** **w** answers "how many nodes must acknowledge?", whereas **j** answers "has it been durably persisted to the journal?". Setting **j: true** on one primary alone does not guarantee majority replication; having multiple replicas alone also does not automatically assert every ACK is journaled on all nodes.

### 6.2. Example Insert with Journaling Acknowledgment

On a standalone MongoDB instance or suitable node, test an insert via `mongosh`:

~~~javascript
use journal_lab

db.orders.insertOne(
  {
    _id: "ORD-J-001",
    customerId: "CUS-100",
    status: "CREATED",
    amount: 450000
  },
  {
    writeConcern: {
      w: 1,
      j: true,
      wtimeout: 5000
    }
  }
)
~~~

In this example, **j: true** requests acknowledgment after the write has been durably synced to the journal per MongoDB's rules. This demonstrates **local durability**, not a promise of high availability. If a service must survive primary failure and is connected to a replica set, it can explicitly request majority:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-J-001" },
  { $set: { status: "PAID" } },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
)
~~~

**wtimeout** bounds how long to wait for write concern. If the client encounters a **writeConcernError** or timeout, do not infer the server definitely did not apply the operation: the change may have already been applied without yet meeting acknowledgment conditions. When retrying, business logic needs unique constraints, an idempotency key, or an appropriate status-verification flow.

### 6.3. Configuration in the URI

For a self-managed replica set, an application can supply parameters in the URI:

~~~text
mongodb://db1.example.test:27017,db2.example.test:27017,db3.example.test:27017/orders?replicaSet=rs0&w=majority&journal=true&retryWrites=true
~~~

The address above is **illustrative only**. In Spring Boot, you can place the actual URI into an environment variable used by application configuration:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Do not hardcode usernames/passwords into the repository. Spring Boot/MongoDB driver versions and configuration mechanisms may differ; verify against the target system. **journal=true** in the URI relates to write concern, not a toggle to turn storage-engine journaling on/off.

### 6.4. Distinguishing Write Concern from Read Concern

**Read concern** determines the consistency level seen by a read query, such as **local** or **majority** in supported cases. It does not replace the journal requirement of write operations. If an application must read back the data it just wrote across a failover, you must evaluate write concern, read concern, read preference, and session semantics together.

## 7. Journal, Oplog, and Recovery in a Replica Set

This is an important point in multi-node MongoDB architecture:

~~~text
Application
   |
   v
Primary mongod
   |          \
   |           +--> PRIMARY's WiredTiger journal
   |
   +--> replication oplog
             |
             v
      Secondary mongod
             |
             +--> SECONDARY's WiredTiger journal
~~~

**Each member** has its own storage engine, journal, and checkpoints. The **oplog** is the replication mechanism for secondaries to copy operations from the primary; the oplog is not synonymous with the journal. A replica set can keep serving when a node fails via election/failover, while the journal helps each individual node recover itself after a local crash.

### 7.1. Two Cases That Must Not Be Equated

**Case A — primary crashes and restarts, topology remains largely unchanged:** the node's storage engine uses checkpoints/journal to recover local data, then the node resumes participating in the replica set according to its state.

**Case B — primary loses connectivity, a secondary is elected as the new primary:** writes that existed only on the old primary and were not replicated to a majority can be **rolled back** when the old primary rejoins. Even if that write was already in the old primary's **local journal**, the replica set can still discard it to sync with the accepted history branch.

~~~text
T0: Node A is PRIMARY
T1: Client writes X; A journals it, but X has not reached majority
T2: A loses network connectivity
T3: Node B is elected new PRIMARY
T4: A returns, syncing with the replica set's valid history

=> X may be rolled back even though A's local journal holds it.
~~~

From this comes a design rule: **j: true cannot replace w: "majority" when data must be protected across failovers**. At the same time, w: "majority" with configured journaling still does not replace backups against user error or widespread storage failure.

### 7.2. Why "Having Three Nodes" Is Not Enough to Conclude Zero Data Loss

A replica set with three data-bearing members typically allows electing a new primary when one node fails, but the safety of a specific write depends on when the write reaches majority, journaling, and the nature of the failure. Adding replicas improves survivability and availability; what durability level an API-accepted write has is still governed by write concern.

## 8. Journal and Checkpoints in a Sharded Cluster

In a sharded cluster, each shard is usually a multi-node replica set. Thus, **every mongod belonging to each shard still has its own journal/checkpoints**. The config server replica set also has storage and recovery mechanisms on its members.

~~~text
                       mongos
                    /     |     \
                   v      v      v
                Shard A Shard B Shard C
                  |       |       |
               Replica Replica Replica
                 Set     Set     Set
                  |       |       |
          Each mongod has WiredTiger journal/checkpoints
~~~

When a mongod on a shard crashes, that node can perform WiredTiger recovery. However, if an entire shard becomes unavailable, queries needing that shard can still fail even while other shards remain operational. **The journal does not re-route data and does not replace replication inside each shard.**

Additionally, a multi-shard operation may require MongoDB's transaction coordination mechanisms. Do not infer that "each shard has a valid checkpoint" means copies taken at different times can be stitched together into a **cluster-wide consistent backup**. Sharded cluster backup and restore require tools/procedures that support distributed state.

## 9. When Is Crash Recovery Enough, and When Is a Backup Needed?

Automatic crash recovery helps for process/OS failures when hardware and storage files remain intact. Other incidents require dedicated recovery strategies:

| Incident | Journal + Checkpoint | What Must Be Added |
|---|---|---|
| **mongod crash**, disk intact | Normally supports automatic recovery on restart. | Error monitoring, restart automation, application verification. |
| **Power loss**, disk and journal still consistent | Can recover up to guaranteed write concern level. | Reliable storage infrastructure, proper shutdown/restart, testing. |
| **One replica set node fails** | Supports local recovery if node recovers. | Majority/quorum, failover, replacement, and resync. |
| **Disk holding data and journal fails/is lost** | Cannot guarantee recovery from lost data alone. | Healthy replica and/or restorable backup. |
| **Accidental delete, buggy update logic** | May durably persist that exact erroneous change. | Backup/PITR, access controls, confirmation for dangerous ops. |
| **Malware/ransomware, environment-wide corruption** | Cannot address destruction outside the engine. | Isolated backups, DR in another region/infra, restore drills. |
| **Need to roll back to a past point in time** | The journal is not a long-term historical store. | Backup + appropriate point-in-time recovery mechanism. |

### 9.1. Backups and Point-in-Time Recovery

A **backup** is an independently restorable copy of live data. **Point-in-time recovery (PITR)** is the ability to restore close to a specific timestamp, usually relying on a base backup and an appropriate change history such as the oplog in replica set backup workflows. This is a completely different problem from journal replay when `mongod` restarts.

For example: a staff member accidentally deletes orders at 15:00, and the mistake is only noticed at 15:10. The journal is not meant to "undo" a valid delete operation; once durably persisted, the delete will be recovered just like any other write. Only a backup/PITR plan serves the need to restore data **prior to 15:00**.

### 9.2. RPO and RTO

- **RPO — Recovery Point Objective:** the maximum amount of data or time window of changes a business can afford to lose.
- **RTO — Recovery Time Objective:** the maximum duration a service is allowed to remain unrestored to a usable state.

These two metrics drive investment in replication, backup frequency, off-site copies, PITR, and recovery drills. You cannot claim RPO = 0 or RTO = a few seconds merely based on the 100 ms journal default and 60-second checkpoint default.

### 9.3. Do Not Arbitrarily Copy a Running dbPath Directory

A copy of data files made while `mongod` is mutating them may capture files at inconsistent states. **Do not use a file copy of a live `dbPath` directory as a standard backup method** without a MongoDB-supported snapshot/backup mechanism and required locking/quiesce/coordination steps.

With MongoDB Atlas, different deployment tiers and service plans provide different backup, restore, and PITR capabilities; verify the actual capabilities of your configured tier. For self-managed deployments, pick a MongoDB-supported backup tool and procedure, then **test restores** to verify backups are valid.

## 10. Observing Journal and Checkpoints with MongoDB Tools

### 10.1. Inspecting serverStatus

On a WiredTiger instance with appropriate privileges, run in `mongosh`:

~~~javascript
const stats = db.serverStatus()

printjson(stats.storageEngine)
printjson(stats.wiredTiger?.log)
printjson(stats.wiredTiger?.transaction)
~~~

The **wiredTiger.log** object contains statistics related to journaling/logging; **wiredTiger.transaction** may contain statistics related to transactions/checkpoints. **Exact field names and availability depend on the MongoDB version**, so inspect the full object rather than hardcoding an unverified field.

You can check server startup configuration:

~~~javascript
db.adminCommand({ getCmdLineOpts: 1 })
~~~

Output reflects configuration options received by the process at startup, though you should not assume all defaults are printed. In production, metrics should also be combined with monitoring systems, system logs, and I/O health.

### 10.2. Signals to Monitor

| Signal | Meaning and How to Read It |
|---|---|
| **Journal sync / log write activity** | Journaling volume and log write cost; anomalies can relate to workload or I/O. |
| **Checkpoint duration / checkpoint activity** | Prolonged checkpoints may warrant investigating storage throughput, dirty cache, and overall load. |
| **WiredTiger cache / dirty bytes** | Cache pressure and amount of modified data waiting to be written to data files. |
| **Disk latency and IOPS** | Impacts journal sync, checkpoints, and write concern acknowledgment times. |
| **Disk free space** | Both journal and data files need space; running out of disk can halt the service. |
| **Replication lag, majority write latency** | Supplements latency visibility and write acknowledgment health in replica sets. |
| **Startup/recovery logs** | Help determine whether the server is running crash recovery, initializing storage, or hitting critical errors. |

Do not look only at a single journal log size number to conclude the system is healthy. Journal footprint varies with write rate, checkpoint timing, compression, and recovery operations.

### 10.3. Configuration and Performance

MongoDB allows configuring **storage.journal.commitIntervalMs** under supported conditions. Lowering the commit interval can increase I/O frequency; raising it can widen the window of writes not yet journal-synced if the application does not request **j: true**. Changing this parameter must be guided by workload, durability requirements, and version documentation.

**Version note:** starting in **MongoDB 6.1**, journaling is always enabled in applicable configurations; the **storage.journal.enabled** option as well as the **--journal** and **--nojournal** flags were removed. Do not follow outdated guides instructing you to "enable journaling with --journal" on modern releases.

## 11. Safe Practical Examples

The lab below only inspects data and statistics of a **local mongod**; there is no need to force an actual crash on a running environment.

### 11.1. Starting a Dedicated Lab Instance

Example on Linux/macOS (requires MongoDB Server and `mongosh` installed):

~~~bash
mkdir -p ./mongo-journal-lab
mongod --dbpath ./mongo-journal-lab --port 27019 --bind_ip 127.0.0.1
~~~

Open another terminal:

~~~bash
mongosh "mongodb://127.0.0.1:27019"
~~~

On Windows, create an equivalent data directory and run `mongod` with the appropriate path. **127.0.0.1** in the example restricts access from other machines; this lab does not represent a production security configuration.

### 11.2. Writing Data with Journal Acknowledgment

~~~javascript
use journal_lab

db.events.insertOne(
  {
    _id: "EVT-001",
    type: "PAYMENT_RECEIVED",
    amount: 200000,
    createdAt: new Date()
  },
  { writeConcern: { w: 1, j: true, wtimeout: 5000 } }
)

db.events.findOne({ _id: "EVT-001" })

db.serverStatus().wiredTiger.log
~~~

The insert requests acknowledgment tied to the local journal. Observing the log statistics helps verify WiredTiger is maintaining journaling, though **it does not prove a specific operation will survive every failure mode**.

### 11.3. Reading Back After a Graceful Shutdown

Stop **mongod** via a graceful shutdown appropriate for your environment, then restart the instance on the **same dbPath directory**. Reconnect:

~~~javascript
db.getSiblingDB("journal_lab").events.findOne({ _id: "EVT-001" })
~~~

The document should still exist if the operation completed properly and no subsequent modification/deletion occurred. This is only a basic post-restart check; **a graceful shutdown is not a crash recovery test**.

If you want to study recovery after a kill/process crash, do so only in a **completely isolated test environment** with disposable data, snapshots/backups, and process control permissions; never force-kill a real server.

### 11.4. Testing Write Concern Variations to Understand Semantics

Compare semantics without trying to benchmark latency from a single request:

~~~javascript
const database = db.getSiblingDB("journal_lab")

database.events.insertOne(
  { _id: "EVT-W1", type: "NORMAL" },
  { writeConcern: { w: 1 } }
)

database.events.insertOne(
  { _id: "EVT-J", type: "JOURNALED" },
  { writeConcern: { w: 1, j: true } }
)
~~~

Both writes can succeed. The difference is the **acknowledgment condition**, not the document format. Do not assert that a write with **w: 1** is guaranteed to be lost on a crash; it **might** not yet have been journal-synced at the exact instant of failure.

## 12. Real-World Failure Analysis Scenarios

### 12.1. A Write Returned Success but Is Missing After Reboot

Analysis steps:

1. Check the operation's write concern: whether **w: 1** or **j** was requested.
2. Verify whether `mongod` experienced a local crash, power loss, or primary switchover.
3. If the replica set had an election, check whether the write reached **majority** or could have been rolled back.
4. Verify whether the client is reading from a lagging secondary or a different environment/cluster.
5. Analyze logs, replication status, and application evidence; do not conclude "the journal is broken" solely from a query missing data.

### 12.2. Server Restarts Take Longer Than Expected

During startup, recovery may need to process the journal, restore storage metadata, and reconcile replication state. Duration is affected by un-checkpointed write volume, I/O speed, workload, and data/disk health. Check startup logs, disk health, driver timeouts, and node status instead of guessing from the default checkpoint interval.

### 12.3. Journal Files Occupy Significant Disk Space

MongoDB creates and cleans up journal files as needed. Log growth can be linked to high write rates, checkpoints, and recovery processes. **Do not delete files directly**, as doing so can break recovery capability. First check free disk space, WiredTiger activity, checkpoints, I/O errors, and appropriate operational guidance.

### 12.4. Both Primary and Secondaries Sync an Accidental Delete

The replica set and journal functioned exactly as designed when persisting and replicating the operation. To recover data from before the deletion, you need a backup or PITR. This is why backup policies must be designed independently from replication.

## 13. Key Operational Principles

1. **Do not disable journaling to "speed things up" based on outdated docs.** In MongoDB 6.1+, journaling is always enabled in applicable configurations; optimize indexes, queries, schemas, and storage first.
2. **Choose write concern based on business requirements.** Critical writes in a replica set usually require considering **w: "majority"** and corresponding journal durability.
3. **Do not rely on a single node for HA.** A journal helps a single node recover itself; it cannot create a standby node.
4. **Use restorable backups and test restores.** Journaling and replication do not fully protect against disk loss, accidental deletes, or site-wide failures.
5. **Provision adequate disk space and I/O.** Journal sync and checkpoints both rely on stable storage; running out of space can bring down `mongod`.
6. **Monitor latency, checkpoints, and replication.** Do not watch CPU/RAM alone; durability bottlenecks often show up in storage and write conditions.
7. **Design retries with idempotency.** On timeouts, operation outcome may be uncertain; blind retries easily lead to duplicate orders, duplicate transactions, or double updates.
8. **Test against RPO/RTO.** Recovery capability only matters when measured in a realistic environment.

## 14. Common Misconceptions

**"A 60-second checkpoint means MongoDB can lose 60 seconds of data."** Incorrect. Checkpoints establish data file milestones; the journal can protect changes after a checkpoint. Actual data loss depends on which operations were durably journaled and the write concern used.

**"The journal runs every 100 ms, meaning every write is acknowledged after 100 ms."** Incorrect. 100 ms is the default sync cadence, not an ACK rule for all writes or a fixed response time.

**"Having a journal means backups aren't needed."** Wrong. The journal serves local recovery from a checkpoint, not restoring accidentally deleted data or recovering from total storage device loss.

**"A write with j: true can never roll back during a primary election."** Wrong. The journal only establishes local durability of the write; a replica set can still roll back a write not acknowledged by an appropriate majority.

**"The oplog is the journal."** Wrong. The oplog serves replication, whereas the WiredTiger journal serves crash recovery on each individual node.

**"Crashing while a checkpoint is being written corrupts the whole database."** Not expected behavior. WiredTiger preserves the previous checkpoint until the new checkpoint finishes and metadata is validly updated.

**"With multiple shards, you can just back up each shard at any random time."** Wrong. Cluster-wide backups require data and metadata to be temporally consistent; sharding makes distributed backup more complex.

## 15. Thought Exercises and Self-Check Questions

**Exercise 1 — Crash timing:** checkpoint at 10:00:00, write A at 10:00:20 synced to journal, write B at 10:00:21 processed only in memory, `mongod` crashes at 10:00:22. Explain why A can be replayed while B may be lost.

**Exercise 2 — Order transactions:** an order-creation API must prevent data loss on primary failure and handle application retries. Propose a write concern, a unique business identifier, and how to handle ambiguous timeout states.

**Exercise 3 — User error recovery:** an operator runs a bad update changing prices on 10,000 products. Explain why checkpoints/journal do not revert prices back and how backup/PITR should be used.

**Exercise 4 — Operational metrics:** when write latency rises, which metrics do you inspect to distinguish bottlenecks in journal sync, checkpoints, majority replication, and the client connection pool?

**Exercise 5 — Tool selection:** for each incident—**mongod crash**, **loss of a primary**, **total disk failure**, and **accidental delete 2 hours ago**—identify the role of the journal, checkpoints, replica sets, and backups.

## 16. Summary Mental Model

~~~text
             Application WRITE
                     |
               WiredTiger cache
                     |
              Journal record
                     |
       j: true requests journal durability
                     |
                     v
               Journal on disk
                     |
         Periodic checkpoint ~60s
                     |
                     v
          Data files at new
           consistent state

CRASH:
  last valid checkpoint + journal replay => local recovery

FAILOVER:
  replica set + majority semantics       => maintain service/protect writes

DATA/REGION LOSS:
  backup + restore/PITR                  => independent recovery
~~~

The **journal** protects durably persisted changes between checkpoints; **checkpoints** provide consistent data milestones for recovery to start from. Together, these two mechanisms enable WiredTiger to recover after crashes, yet what guarantees an application receives still depends on **write concern**, topology, storage hardware, and the type of failure.

### Official MongoDB Documentation for Further Reading

- [Journaling](https://www.mongodb.com/docs/manual/core/journaling/) — how the journal works, sync timing, and journal file lifecycle.
- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — MVCC, snapshots, checkpoints, and journal.
- [Configure Journaling for Self-Managed Deployments](https://www.mongodb.com/docs/manual/tutorial/manage-journaling/) — configuration and durability.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgment levels, `j`, and majority.
- [Write Operation Performance](https://www.mongodb.com/docs/manual/core/write-performance/) — relationship between journaling, I/O, and write performance.

When applying to production systems, always cross-reference the documentation for your **running MongoDB version**, replica set/sharding configuration, and your environment's specific backup capabilities.
