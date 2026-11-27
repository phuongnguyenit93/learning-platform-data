# Snapshot Backups and Storage Engine Coordination Requirements in MongoDB

## 1. The Problem: Backing Up an Actively Writing System

A housing rental platform uses MongoDB to store:

- **listings**: hundreds of thousands of property listings.
- **bookings**: viewing appointments and rental requests.
- **payments**: payment states and reconciliation records.
- **auditEvents**: change history.

The database runs continuously. Every few seconds there are inserts, updates, and transactions. The operations team wants a backup fast enough to avoid pausing the API for hours and reliable enough to recover from disk failure.

They consider taking a **volume snapshot** of the disk hosting MongoDB:

~~~text
MongoDB mongod
      |
      v
WiredTiger storage engine
      |
      +--> Data files / indexes / metadata
      +--> Checkpoints
      +--> Journal
      |
      v
Filesystem / block device / cloud volume
      |
      v
     SNAPSHOT
      |
      v
 Backup storage / restore volume
~~~

The catch is that a storage-level snapshot command can succeed while the resulting backup remains unusable if:

1. Critical MongoDB files sit across **multiple volumes** snapshotted at different times.
2. Files are copied one by one from the data directory **while `mongod` is actively writing**, without a consistent snapshot.
3. The **journal, metadata, or files needed for WiredTiger recovery** are missing.
4. A **secondary** with replication lag is snapshotted while the team assumes its data is as current as the primary.
5. Shards and the config server are backed up **without coordination**, yet assumed to represent one consistent point across the sharded cluster.
6. Only the data volume is saved while **encryption keys, configuration, certificates, and the backup manifest** are forgotten.
7. Snapshots exist, yet nobody has ever tested a **restore**.

A valid snapshot must answer two questions simultaneously:

> **Can the storage layer recover the MongoDB files into a consistent state?**

> **Does this backup meet the entire system's recovery targets, including data point in time, topology, and dependencies?**

### Learning Objectives

After this lesson, you can:

1. Distinguish **filesystem/block-volume snapshots**, **database-consistent backups**, and **point-in-time recovery (PITR)**.
2. Understand the roles of **WiredTiger**, **checkpoints**, the **journal**, and **crash recovery**.
3. Explain why a snapshot must guarantee an **atomic point-in-time** across all relevant files/volumes.
4. Compare **cold snapshots**, **`fsyncLock` + storage snapshots**, **secondary snapshots**, and **MongoDB-managed backups**.
5. Build a runbook using **`fsyncLock`/`fsyncUnlock`** with time limits and an error recovery path.
6. Analyze **replication lag, oplog window, majority-acknowledged writes, and RPO/RTO**.
7. Understand why **sharded cluster backups** require coordination across multiple components.
8. Design backup storage, encryption/KMS, access control, and retention.
9. Build a **restore drill** procedure: isolating the environment, verifying data, integrity, and workload behavior.
10. Spot common errors: live file copies, multi-volume skew, missing journals, mixed snapshot generations, and restoring into an incompatible version.

> **Scope and Safety:** This material belongs to **Database Engine Document MongoDB → Backup and Recovery**. Locking writes, stopping `mongod`, snapshotting volumes, and restoring can affect data/availability. Run illustrative procedures only in authorized lab environments. This lesson requires no production cluster modifications. Exact syntax and capabilities of snapshot APIs, backup cursors, Ops Manager/Atlas, `fsyncLock`, and storage engines depend on version and deployment; always consult documentation for your exact environment.

## 2. Defining Snapshots in a Database Context

### 2.1. Volume Snapshot

A **volume snapshot** captures the state of a block device/volume at a logical point. Many storage systems implement this via copy-on-write, redirect-on-write, or proprietary mechanisms. Creating the snapshot point can be faster than copying every byte; data is then replicated/transferred to backup storage per provider policy.

~~~text
Volume at time T0
    [A][B][C][D]
          |
       Snapshot T0
          |
App continues writing B' at T1
          |
Current volume: [A][B'][C][D]
Snapshot T0:    [A][B ][C][D]
~~~

What matters is not just how fast the snapshot is triggered, but **which blocks are captured at the same point in time** and whether that block set suffices for storage engine recovery.

### 2.2. A Snapshot Is Not File-by-File Copying

Compare:

~~~text
Copying individual files from dbPath while mongod writes:
  File A copied at 10:00:00
  File B copied at 10:00:08
  File C copied at 10:00:25

Atomic volume snapshot:
  Blocks of the same volume referenced
  at a single consistent logical point T0
~~~

Copying files sequentially can assemble versions that **never existed together** in any valid storage state. Even if every file copy completes without an I/O error, MongoDB may still fail to start from that set of files.

An **atomic snapshot of a single volume** differs from snapshots taken **sequentially across multiple volumes**. Multi-volume setups require a **consistency group/synchronized** mechanism or a coordinated procedure satisfying storage engine requirements.

### 2.3. Crash-Consistent

A **crash-consistent** snapshot resembles storage state after an abrupt power loss at a single instant:

- Some data pages have been flushed to disk.
- Some newer changes may still reside in the journal.
- Operations acknowledged for durability under the system's guarantees must be evaluated within configuration boundaries.
- The storage engine must run **crash recovery** when opening the data files.

Crash-consistent **does not mean every file is in a "clean shutdown" state**. It means the blocks form an image equivalent to a crash at a single instant, allowing recovery via checkpoints/journal.

### 2.4. Application-Consistent

An **application-consistent** backup coordinates with the application/storage engine to guarantee the desired data state—for example via flushing/write-locking or an integrated backup mechanism.

It can:

- Narrow the gap between data files and journal at snapshot time.
- Make the write-freeze boundary explicit.
- Increase reliability when data components span multiple volumes.
- Require extra steps and potentially impact latency/availability.

**Not every crash-consistent snapshot is broken**, since WiredTiger is designed to recover from crashes. Conversely, **do not call a set of skewed multi-volume snapshots "crash-consistent"** merely because each individual volume snapshot succeeded.

### 2.5. Snapshots, Full Backups, and Incremental Backups

A **full backup** is a self-contained dataset capable of restoring without prior backup generations, aside from specified metadata/keys. An **incremental backup** stores only changes since a baseline and depends on a chain to restore.

Volume snapshots can be:

- A logical full view at each timestamp.
- Internally incremental/deduplicated physical storage inside the provider.
- Captures usable only while dependent snapshots/blocks still exist.

Do not assume "the provider only bills for changed blocks" means an independent restore file requires no underlying chain or metadata.

### 2.6. Snapshot Backups vs. MongoDB Read Concern Snapshot

The term **snapshot** also appears in **`readConcern: "snapshot"`** or transaction snapshot isolation. That controls how a transaction/query observes a logically consistent view of data.

It is **not** a filesystem physical backup API. A MongoDB transaction using snapshot read concern does not save `dbPath`, the journal, configuration, or tooling to restore an entire database.

## 3. RPO, RTO, and Backup Timing

### 3.1. Recovery Point Objective (RPO)

**RPO** is the maximum data loss a business tolerates, usually measured in time.

Example:

~~~text
Latest snapshot:   10:00
Incident:          10:37
Restorable to:     10:00

Unrecoverable data gap:
  nearly 37 minutes
~~~

Without PITR/oplog archiving or external replay sources, hourly snapshots can result in losing nearly an hour of data.

### 3.2. Recovery Time Objective (RTO)

**RTO** is the acceptable duration to restore service:

~~~text
Incident detection
 + restore decision
 + fetching snapshot
 + provisioning storage/compute
 + starting MongoDB and recovery
 + validation
 + cutting application over to new system
 = Recovery Time
~~~

A snapshot created in seconds **does not mean restoration takes only seconds**. Restoring multi-terabyte volumes, rebuilding sharded topologies, and running business checks can take hours.

### 3.3. RPO and RTO Are Not Decided by a Single Command

| Component | Impact on RPO | Impact on RTO |
| --- | --- | --- |
| Snapshot frequency | Higher frequency shrinks the gap between backup points | Can increase backup overhead |
| Secondary replication lag | A secondary snapshot can lag behind the primary | Requires verifying the effective recovery point |
| Oplog/PITR archive | Can bring the recovery point closer to the incident | Replaying logs takes time |
| Data size | Does not directly define the recovery point | Impacts copy/restore duration |
| Key/KMS/secrets availability | Does not alter data point | Can stall restoration completely |
| Restore drills | Does not alter snapshot data | Cuts time spent debugging errors/broken runbooks |
| Sharded cluster coordination | Determines cluster-wide consistency | Multi-component restoration is complex |

### 3.4. Backup Policy Selection Example

Suppose:

~~~text
Target RPO:   <= 5 minutes
Target RTO:   <= 45 minutes
Dataset:      2 TiB
Replica set:  3 members
~~~

An hourly snapshot **cannot guarantee a 5-minute RPO** without log/PITR backups or alternative recovery sources. At the same time, restoring 2 TiB and validating within 45 minutes must be **proven via drills** or achieved with a faster recovery architecture.

## 4. WiredTiger Is the Storage Engine—Why Coordinate With It?

### 4.1. What Does the Storage Engine Do?

**WiredTiger** is the standard/default storage engine in modern MongoDB. It manages storage internals including:

- Organizing data files/indexes.
- Caching and flushing data to disk.
- Managing checkpoints.
- Journaling/durability.
- Crash recovery.
- Internal structures required for transactions, data history, and metadata.

Applications see documents and collections; the storage engine must maintain a **consistent set of interrelated physical files**.

### 4.2. In-Memory Writes Differ From Durable State

When a client runs:

~~~javascript
db.bookings.updateOne(
  { _id: "booking-1" },
  { $set: { status: "confirmed" } }
);
~~~

MongoDB processes changes through cache, journal, and checkpoints per WiredTiger mechanics. When the client receives an ACK and what durability holds also depend on **write concern** and deployment configuration.

Never infer:

~~~text
updateOne returns OK
=> every data file on the filesystem immediately holds
   the full new value inside a completed checkpoint.
~~~

### 4.3. Checkpoints

A **checkpoint** is a consistent storage state that WiredTiger writes to disk per its internal schedule. Checkpoints:

- Provide a known clean point from which the engine can start up.
- Bound the amount of journal/recovery work needed.
- Maintain a crash-recoverable file structure.

Checkpoints **are not standalone backups**. They live on the same storage volume and can be lost alongside a failed disk, encrypted by ransomware, or deleted by an authorized user.

### 4.4. Journal

The **journal** enables WiredTiger to recover changes committed since the last checkpoint per durability guarantees. High-level concept:

~~~text
Checkpoint C0
    |
    +--> Transaction T1 written to journal
    +--> Transaction T2 written to journal
    +--> Crash at C1 before next checkpoint finishes
    |
    v
Restart:
  Use valid checkpoint + journal recovery
  to reconstruct a consistent data state
~~~

Exact details of journal flushing, commits, and recovery depend on MongoDB/WiredTiger version, journaling/write concern settings, and topology. The diagram above is an intuitive model, not a fixed I/O sequence for every release.

### 4.5. Snapshots Must Contain Every Engine-Required File

A physical snapshot backup must include **all files belonging to the same physical backup**:

- Data and index files.
- WiredTiger metadata and related internal files.
- The journal, wherever configured.
- All files in **`dbPath`** required for startup and recovery.
- Additional volumes if storage engine configuration spans them.

Never cherry-pick a few files with recognizable collection names while omitting system-named files. Physical file layouts vary across versions and are not a contract for manual file selection.

### 4.6. Crash Recovery Does Not Fix an Invalid Snapshot

WiredTiger can recover from a valid **crash-consistent volume image**. However, it cannot be expected to repair:

~~~text
File A taken at 10:00
File B taken at 10:07
Journal taken at 10:12
Metadata taken at 10:03
~~~

because those files never formed a crash-consistent state. Mixing components from different snapshots can cause metadata mismatches, missing data, or storage corruption.

### 4.7. Durable Does Not Mean "Everything Is Backed Up"

Write concern, journaling, majority acknowledgement, and backup points are **distinct layers of assurance**:

~~~text
Write concern:
  At what durability/replication level is a write acknowledged?

Snapshot point:
  Which bytes and database state exist
  in the image captured at backup time?

Restore:
  Can the engine recover that image
  into a consistent database?
~~~

A write majority-acknowledged on the primary might not yet exist on a **lagging secondary used for snapshotting**. Never treat the backup creation timestamp as a promise that it holds every write primary-acknowledged up to that same wall-clock time.

## 5. Atomic Snapshots: One Point in Time for All Files

### 5.1. Atomic Point-in-Time on a Single Volume

When **`dbPath`** and all required components reside on the same volume, a storage snapshot with atomic/crash-consistent semantics freezes the image of the entire volume at one instant.

~~~text
Volume V contains:
  /data/db/
      WiredTiger...
      collection...
      index...
      journal/...

Snapshot(V, T0) -> all blocks of V at T0
~~~

Afterward, the system can keep writing to the live volume. Exporting/copying data **from the created snapshot** can take a long time without keeping `mongod` frozen throughout the copy, provided the storage provider guarantees the snapshot point is fixed.

### 5.2. Multi-Volume: A Hazardous Scenario

Suppose:

~~~text
Volume V1: /data/db/data
Volume V2: /data/db/journal

Snapshot(V1) at T0 = 10:00:00
Snapshot(V2) at T1 = 10:00:18
~~~

These two snapshots **are not automatically a crash-consistent MongoDB image**. An 18-second skew can span numerous writes and checkpoints.

**Solution:** use a storage-supported **consistency group / multi-volume atomic snapshot**, or a write-stop/lock procedure coordinated with the storage engine that you have verified meets requirements.

### 5.3. Not Every Cloud Snapshot API Is a Consistency Group

A provider might offer:

- Single-volume snapshots.
- Multi-volume snapshots attached to the same instance.
- Integration-specific application-consistent snapshots.
- Snapshot groups sharing a common consistency point.

Do not assume that merely because an API accepts multiple volume IDs, **every volume is captured at the exact same application-consistent instant**. Check the API contract and storage provider behavior for your exact product/version.

### 5.4. Filesystem Freeze Differs From Database Freeze

A filesystem may offer **freeze/thaw** to stabilize metadata/I/O at snapshot time. However, filesystem freeze **does not understand** WiredTiger transactions, checkpoints, or journal semantics.

When an application-consistent backup is needed, combine properly:

~~~text
MongoDB write coordination
      +
Filesystem/storage coordination
      +
Atomic snapshot mechanism
      +
Restore validation
~~~

Never treat any arbitrary filesystem operation as proof of a MongoDB-consistent backup.

## 6. Four Common Snapshot Strategies

| Strategy | Mechanism | Strengths | Limitations |
| --- | --- | --- | --- |
| **Cold backup** | Cleanly stop `mongod`, then snapshot/copy | Easy to reason about file consistency | Downtime on the stopped node |
| **`fsyncLock` + snapshot** | Coordinate `mongod` flush/write-lock, then take storage snapshot | Can shorten the write-lock window | Delays/queues writes; requires guaranteed unlock |
| **Secondary snapshot** | Use a replica set member not serving primary app writes | Reduces impact on primary | Must monitor replication lag and member health |
| **Integrated backup platform** | Atlas/Ops Manager/Cloud Manager/supported tooling | Built-in metadata, scheduling, PITR/coordination per features | Eligibility constraints, cost, retention/restore verification |

Options can be combined—for example, **`fsyncLock` on a secondary followed by an atomic volume snapshot**. Yet any combination requires a runbook and an assessment of replication impact.

### 6.1. Cold Backup

Procedure:

~~~text
Select an eligible node to stop
      |
      v
Cleanly shut down mongod
      |
      v
Confirm process has stopped
      |
      v
Create volume snapshot / full data copy
      |
      v
Restart the node
      |
      v
Verify health and replication
~~~

The advantage is zero concurrent MongoDB writes during copying. However, a **cold backup of one member** is only a copy of that node; it does not automatically produce a globally consistent point-in-time backup of a sharded cluster.

### 6.2. Hot Snapshot Coordinated With `fsyncLock`

MongoDB provides **`fsyncLock`/`fsyncUnlock`** in supported environments/versions to coordinate flushing and block writes during filesystem backup creation.

Operation pattern:

~~~text
Verify node can safely lock writes
      |
      v
fsyncLock
      |
      v
Atomic storage snapshot
      |
      v
fsyncUnlock
      |
      v
Verify node resumes accepting/applying writes
~~~

**Hold the lock only until storage fixes the snapshot point**, not throughout the entire duration the provider takes to copy backup data to long-term storage, provided the provider guarantees the snapshot point is immutable.

### 6.3. Snapshot on a Secondary

A replica set can dedicate a secondary for backup tasks:

~~~text
                  Replica set

Primary --------------------------> App writes
  |
  +--> Secondary A ----------------> HA/read traffic
  |
  +--> Secondary B ----------------> Backup snapshot
                                      |
                                      v
                              Backup storage
~~~

Using a backup secondary reduces impact on the primary. Still, you must know:

- How much **replication lag** does Secondary B have?
- Is this member healthy enough to recover?
- Is it currently in rollback or initial sync?
- During `fsyncLock`, is **oplog application paused**, and is the oplog window large enough?
- Could this node be elected primary during backup? Configure topology policies appropriately.

### 6.4. Managed Backups

An integrated MongoDB backup service can manage snapshots, replica set/shard states, oplogs, backup catalogs, and restore workflows according to product capabilities.

Do not try to reinvent an equivalent system with a few cron scripts if the business needs **PITR, sharded-cluster-wide consistent backups, and strict restore SLAs**.

## 7. `fsyncLock` and `fsyncUnlock`: Meaning and Impact

### 7.1. Commands in `mongosh`

On an authenticated **lab `mongod`** with proper privileges:

~~~javascript
const admin = db.getSiblingDB("admin");

// Begin backup coordination window.
printjson(admin.fsyncLock());

// Here: administrator/storage API must take
// the snapshot following the verified procedure.

// End coordination window as soon as the snapshot point is fixed.
printjson(admin.fsyncUnlock());
~~~

**The snippet above does not take a snapshot itself.** It only shows where MongoDB operations sit in a runbook. Never copy-paste `fsyncLock` onto a production server without an unlock procedure, proper authorization, and impact monitoring.

### 7.2. `fsyncLock` Is More Than a Plain Read Lock

The purpose of `fsyncLock` during backup is coordinating file/storage engine state and **blocking further writes** during the operation window. Depending on version and topology, write operations may queue or stall while locked.

Consequences:

- Write latency can spike sharply.
- Clients may time out.
- Replication application on a secondary may stall.
- Write-dependent jobs may be disrupted.
- Impact can cascade to availability if the wrong member is locked or locked too long.

Hence **`fsyncLock` is a controlled operational action**, not a harmless routine command.

### 7.3. `fsyncLock` Must Be Paired With Guaranteed Unlock

A runbook must never be just:

~~~text
1. fsyncLock
2. Run snapshot script
3. fsyncUnlock
~~~

because if step 2 fails, step 3 may never execute. At minimum, include:

- **`try/finally`** or equivalent trap cleanup.
- A watchdog/timeout on the lock window.
- A check to confirm whether the node is still locked.
- A **manual unlock** path executable by authorized operators.
- Alerts when lock duration exceeds SLA.
- Handling if the lock-controlling connection drops or the orchestrator restarts.

### 7.4. Safer Orchestration Pseudocode

This is **pseudocode**, not a production-ready backup tool:

~~~javascript
async function snapshotWithCoordinatedLock(
  adminDb,
  storageProvider,
  volumeGroup
) {
  let locked = false;
  let snapshot;

  try {
    await adminDb.command({ fsync: 1, lock: true });
    locked = true;

    // Provided by the storage layer;
    // must guarantee a unified snapshot point across all volumes.
    snapshot = await storageProvider
      .createConsistentGroupSnapshot(volumeGroup);

    // Success requires confirming the snapshot point
    // is established, not merely receiving a request ID.
    if (!snapshot || !snapshot.pointInTimeEstablished) {
      throw new Error(
        "Could not verify snapshot consistency point"
      );
    }

    return snapshot;
  } finally {
    if (locked) {
      try {
        await adminDb.command({ fsyncUnlock: 1 });
      } catch (unlockError) {
        // Must raise an alert and trigger the manual unlock runbook.
        // Never assume the node was unlocked.
        throw unlockError;
      }
    }
  }
}
~~~

**Note:** `storageProvider` and `pointInTimeEstablished` are **custom illustrative interfaces**, not MongoDB APIs or cloud provider properties. Production code must also handle timeouts, cancellation, credential expiry, node/lock state checks, and manifest recording.

In some runtimes, **throwing an unlock error inside `finally`** can mask the original snapshot error; real orchestration must log both errors and prioritize safe state recovery. Never treat pseudocode as a certified backup implementation.

### 7.5. Never Forget the Unlock Step

If the snapshot API establishes the point image quickly while uploading takes 45 minutes, you generally **do not need to hold the write lock for 45 minutes** if storage snapshot semantics guarantee blocks at T0 remain unchanged during upload. Holding the lock unnecessarily queues writes, causes client timeouts, and builds replication lag.

### 7.6. Higher Risk on the Primary

Running `fsyncLock` on the primary can block most application writes. Unless there is a specific reason, prefer backing up from a dedicated secondary or a supported backup service. Even a secondary is not risk-free: it still participates in replication and can lag or fail to catch up with the oplog.

## 8. Coordinating With Filesystems and Cloud Volumes

### 8.1. Inventory Every Path

Before designing snapshots, inventory:

~~~text
mongod process
  storage.dbPath
  journal path
  filesystem mount points
  volumes/block devices
  encryption layer
  backup agent path
  logging/config/certs needed for restore
~~~

Do not guess from directory names. In default deployments, WiredTiger files and the journal usually sit under **`dbPath`**, yet storage topology, symlinks, separate mounts, and host-level configuration can differ.

### 8.2. Single-Volume Example

~~~text
Volume /dev/volumeA
   |
   +-- /var/lib/mongodb/
         WiredTiger metadata
         data/index files
         journal/

Snapshot /dev/volumeA at T0
~~~

If the snapshot provider guarantees atomic/crash-consistent captures and all needed files reside here, this is a sound foundation for physical recovery.

### 8.3. Multiple-Volume Example

~~~text
Volume A: /var/lib/mongodb/data
Volume B: /var/lib/mongodb/journal
Volume C: auxiliary WiredTiger files or dependencies
~~~

You must guarantee a **consistent group snapshot** or coordinate so components do not diverge between snapshot points per engine rules. Snapshotting A at 10:00 and B at 10:05 cannot be treated as equivalent to snapshotting A+B together.

### 8.4. Local Filesystem Snapshots Differ From Remote Replicated Storage

Some storage systems provide:

- RAID.
- Replicated block storage.
- Object storage snapshots.
- Cross-region copies.
- Immutable snapshots.

Not every feature guarantees **application consistency**. RAID/replication improves availability or hardware fault tolerance, but **does not replace backups**: accidental deletions or ransomware encryption replicate immediately to replicas.

### 8.5. Illustrative LVM Snapshot

In a Linux lab configured with LVM, an administrator might snapshot a logical volume using a command like:

~~~bash
# Illustrative only on a configured LVM lab.
# /dev/vg_lab/mongo_data is an example, not a universal volume name.
sudo lvcreate \
  --snapshot \
  --name mongo_snap_lab_343 \
  --size 4G \
  /dev/vg_lab/mongo_data
~~~

**Never run this command without knowing the exact volume and COW/snapshot space allocation.** LVM snapshots have strict capacity rules; if the COW area fills up, the snapshot becomes invalid. This also snapshots only **one logical volume**, not coordinating across multiple LVs.

### 8.6. AWS/EBS or Cloud Snapshots

Cloud providers offer volume snapshot APIs, sometimes with **multi-volume snapshots** or application quiescing depending on the product. Proper workflow:

1. Identify exact volume IDs belonging to MongoDB.
2. Verify the API's consistency guarantee.
3. Coordinate `mongod` if required.
4. Trigger the snapshot.
5. Unlock only after confirming the **snapshot point** is established.
6. Monitor snapshot/upload to completion.
7. Verify the manifest and execute restore drills.

Never rely solely on **request accepted** status to treat a backup as ready to restore. Providers may need time to finalize the snapshot or replicate it to another region.

## 9. Snapshots on a Replica Set: Which Member to Choose?

### 9.1. Why Back Up a Secondary?

A replica set provides high availability. Backing up a **secondary** generally avoids locking a primary actively serving application writes.

~~~text
Client writes
     |
     v
  Primary -------- oplog --------> Secondary A
                               \
                                \--> Secondary B
                                       |
                                       v
                               Snapshot backup
~~~

Secondary B can be a topology-designated backup member. This offloads read/copy I/O from the primary while still requiring protection of replica set availability.

### 9.2. Choose a Healthy Member

Before snapshotting, verify:

- Member is a valid **SECONDARY**, not in initial sync or abnormal recovery.
- Replication lag is within RPO limits.
- Disk, IOPS, memory, and CPU suffice for backup load.
- No rollback is underway.
- The oplog window covers any pause and catch-up period.
- Membership/election/voting policies prevent locking or cold shutdown from losing majority.

### 9.3. Replication Lag

Example:

~~~text
Primary optime:   10:30:00
Secondary optime: 10:27:40
Secondary snapshot created at 10:30:05
~~~

Although the snapshot carries a wall-clock timestamp of **10:30:05**, its data reflects the secondary's state around **10:27:40**, depending on member state and backup rules. If the business requires a 1-minute RPO, 2 minutes 20 seconds of lag already breaches the target.

**Snapshot creation timestamp is not the timestamp of the latest recovered write.**

### 9.4. Inspecting the Replica Set

On a properly authorized connection:

~~~javascript
printjson(rs.status());
~~~

Output includes member states and optime markers depending on version. Never hardcode positional fields as an immutable contract across versions; identify the backup member and read its actual replication metrics.

Cluster time / last applied optime can also be queried via supported commands/monitoring APIs. **`rs.status()` does not mean a snapshot backup exists**; it simply informs member and timing selection.

### 9.5. `fsyncLock` on a Secondary Affects Replication

When a secondary is write-locked, applying replicated changes can slow or pause depending on feature/version. If locked too long:

~~~text
Primary keeps writing
Backup secondary falls behind applying oplog
Replication lag grows
Primary oplog keeps wrapping
~~~

If the oplog window is too small for the secondary to catch up after unlocking, the member may require a resync or manual intervention. Enforce **lock duration limits**, monitor lag and oplog window, and automate cancellation/unlock.

### 9.6. Hidden/Dedicated Backup Member

You can configure a dedicated backup secondary with appropriate properties (e.g., hidden/non-electable per replica set configuration) to reduce the chance of serving read traffic or becoming primary during backup.

However, a member can still affect majority/voting and storage footprint depending on config. Never alter priority, votes, or hidden flags in production without assessing availability and quorum.

### 9.7. Snapshotting One Member Differs From Snapshotting the Whole Replica Set

For an unsharded replica set, a valid physical snapshot of **one member** typically serves as the base to recover that member or seed a replica set via proper procedures.

However, never:

- Take data files from member A and journal files from member B.
- Mix snapshots from different members at different timestamps into one `dbPath`.
- Overwrite a live replica set member's directory with an old snapshot without following recovery procedures.
- Assume an old snapshot can rejoin an active replica set cleanly without evaluating rollback/resync/oplog constraints.

Recovering a single member and recovering an **entire replica set** are distinct operational tasks.

## 10. Snapshots and Majority Write Concern

### 10.1. Meaning of Majority Acknowledgement

In a replica set, **`writeConcern: { w: "majority" }`** requires acknowledgement from the configured replica set majority of members. Durability/journaling settings and server version govern exact ACK guarantees.

Application example:

~~~javascript
db.getSiblingDB("mongo_backup_lab_343")
  .getCollection("events")
  .insertOne(
    {
      _id: "event-majority-001",
      kind: "booking_confirmed",
      createdAt: new Date()
    },
    { writeConcern: { w: "majority" } }
  );
~~~

This illustrates requesting majority acknowledgement on a replica set. On standalone or special configs, verify actual deployment semantics.

### 10.2. Majority Does Not Force Every Secondary to Have the Write

In a 3-member replica set, a majority-acknowledged write may exist on the primary and Secondary A while **Secondary B is lagging** and has not applied it yet.

If you snapshot Secondary B at that moment, B's snapshot will not contain that write even though the primary returned a majority ACK.

That is why backup members must track applied optime and data timestamps instead of inferring recency from application majority write concern.

### 10.3. Non-Durable Writes

If a workload uses weak write concerns or settings that reduce durability, a crash can cause some writes near snapshot time to vanish on recovery. Never promise "the snapshot holds every operation a client saw acknowledged" without checking write concern, journaling, and storage semantics.

### 10.4. Backup Consistency Differs From Business Consistency Outside MongoDB

Suppose a MongoDB transaction updates a booking and appends an audit event, and the service then calls an external payment gateway. A valid MongoDB snapshot **does not synchronously roll back** the external payment system.

If MongoDB restores to before the external payment completed, you need reconciliation, idempotency, saga/outbox patterns, or operational procedures to realign state across systems.

## 11. What Else Does Point-in-Time Recovery (PITR) Require?

### 11.1. Base Snapshot and Continuous Logs

A snapshot at T0 provides one recovery point. Restoring to T1 > T0 generally requires a **continuous change stream/log** and a compatible replay mechanism, such as oplog archival in a supported MongoDB backup solution.

~~~text
T0                                       T1
|----------------------------------------|
Base snapshot                     Failure / target
   \------ oplog/change archive --------/
           must have zero gaps
~~~

A PITR workflow must prove:

- A valid **base backup** exists.
- Required log segments are present and contiguous.
- Valid checkpoints/restore tokens/timestamps exist.
- Tooling applies logs in exact order and semantics.
- The target timestamp lies within the supported PITR window.

### 11.2. Do Not Treat the Oplog Inside a Snapshot as Full PITR

A secondary's physical snapshot may contain the local oplog as of backup time. Yet that oplog does not inherently hold **writes after the snapshot** or continuous history for arbitrary future restore targets.

You cannot simply restore a snapshot and run ad-hoc copy scripts on **`local.oplog.rs`** to build a safe production PITR solution.

### 11.3. Oplog Window

The oplog is a bounded collection with retention limits. If the backup/archive pipeline stalls, older entries may roll off before being archived.

Example:

~~~text
Oplog window: 8 hours
Backup job fails to collect logs for: 10 hours

=> Risk of a PITR history gap.
~~~

With managed backups, monitor **backup freshness/PITR availability**, not just volume snapshot status.

### 11.4. Target Timestamp

When choosing to restore to "14:25", clarify:

- Which timezone is the timestamp in?
- Should writes right on the boundary be included or excluded?
- How are multi-collection transactions handled?
- To what point must external systems (message bus/payments) reconcile?

Never read a timestamp off a UI without checking timezone and claim you restored to the exact business instant.

### 11.5. Do Not Mechanically Apply `mongorestore --oplogReplay`

**`mongodump`/`mongorestore`** are logical backup/restore tools with oplog flags for supported workflows. They are **not an arbitrary PITR mechanism to bolt onto a physical WiredTiger snapshot**.

If you want PITR from volume snapshots, use a product-supported and drilled backup/restore workflow. Never chain mismatched tool types assuming "both contain MongoDB data so replay will work."

## 12. Sharded Clusters: Snapshotting Each Shard Is Not a Consistent Backup

### 12.1. Components of a Sharded Cluster

A typical sharded cluster:

~~~text
                 Applications
                      |
                    mongos
                      |
            +---------+---------+
            |                   |
        Config Server         Shards
        Replica Set        +----+----+
                           |         |
                         Shard A   Shard B
                           RS        RS
~~~

Data spans multiple shards. **Config servers** store routing and chunk metadata essential for cluster operation.

### 12.2. Skewed Snapshot Times Have Consequences

Suppose a chunk migrates from Shard A to Shard B:

~~~text
10:00  Snapshot Shard A
10:02  Chunk migration A -> B
10:05  Snapshot Shard B
10:08  Snapshot Config Server
~~~

Captures taken at three separate timestamps do not guarantee a consistent cluster state. Depending on migrations/configuration, restoring can hit desynchronized data and metadata.

### 12.3. Cluster-Wide Coordination Is Mandatory

For a sharded cluster, you need:

- Backups of all relevant shards and config server components.
- A strategy guaranteeing a **consistent recovery point**.
- Coordination of **balancer/chunk migrations** per runbook and version where needed.
- Management of oplogs/PITR and multi-shard transaction semantics.
- Backup manifests tying captures together into one generation.
- Sharded-specific restore procedures.

Do not treat stopping the balancer **by itself** as sufficient for a consistent backup, because application writes and distributed transactions continue running.

### 12.4. Do Not Back Up Only `mongos`

**`mongos`** is a query router; it does not store full data and catalog state like a shard replica set or config server. Snapshotting a `mongos` host does not back up sharded cluster data.

### 12.5. When to Use Managed Backups

If a sharded cluster has many shards, transactional workloads, and tight RPOs, a MongoDB-supported backup platform (such as Atlas/Cloud Manager/Ops Manager depending on deployment) is usually far better suited than simple custom snapshot scripts.

Capabilities like full snapshots, continuous backup/PITR, cross-region copies, and retention **depend on tier, version, and policy**; verify in official product docs.

## 13. Differences Between Atlas, Ops Manager, and Self-Managed

### 13.1. MongoDB Atlas

Atlas offers backup/snapshot and PITR features depending on cluster type/tier, config, and subscription. Operators must verify:

- Is **backup enabled** on the cluster?
- Snapshot schedule and retention policy.
- Is PITR active, or only periodic snapshots?
- Which new clusters/targets can receive restores?
- Are cross-region/cross-project restores or copies enabled?
- What encryption/KMS access is needed at the restore target?
- Backup completion duration and backup health.

Do not assume Atlas free/shared tiers offer the same capabilities as dedicated clusters.

### 13.2. Ops Manager/Cloud Manager

MongoDB management platforms provide backup integration, automation, and restore workflows. They require version-specific agent, storage, privilege, and policy setup.

A manual `fsyncLock` command **does not replace** a full backup catalog and recovery orchestration platform.

### 13.3. Self-Managed

In self-managed setups, the operations team owns the entire stack:

~~~text
Snapshot API + consistency group
    |
Backup catalogs/manifest
    |
Offsite encrypted storage
    |
Retention & immutability
    |
Periodic restore drills
    |
Monitoring / incident response
~~~

The benefit is high control; the trade-off is requiring deep expertise in storage engines, filesystems, cloud/KMS, replica sets/sharding, and security.

## 14. Encryption, Access Control, and Backup Retention

### 14.1. Backups Hold Sensitive Data

Physical snapshots can contain customer data, users, bookings, financial states, and authentication metadata. **Backups must be protected at least as strictly as production data**.

Principles:

- Encryption at rest for snapshots/backup objects.
- Encryption in transit when transferring data.
- Identities granted only necessary backup/restore privileges.
- Auditing for downloads, deletions, and restores.
- Never expose public bucket/object URLs.
- Separate backup operator and application operator permissions.

### 14.2. Encryption Keys and KMS

A snapshot of an encrypted volume may be **unrestorable** if the key or decryption permission is lost.

Plan for:

- Key ownership and rotation.
- Key accessibility at the restore target.
- KMS key policies and cross-region/cross-account permissions.
- Backing up/recovering required key material per product guidance.
- Never storing plaintext keys alongside the snapshot.

**A snapshot file is useless without the key to decrypt it.**

### 14.3. TLS Certificates and Application Secrets

`dbPath` is not the entire system. Post-restore recovery may also require:

- Matching `mongod` configuration.
- TLS certificates, CA chains, and internal authentication material.
- Service secrets.
- DNS/connection strings/network policies.
- Backup agent configuration state.
- Monitoring/audit integrations.

Store these separately in configuration management/secret vaults. **Never** embed plaintext secrets in backup manifests.

### 14.4. Immutable/Offsite Copies

If ransomware or a compromised cloud root user can delete both production volumes and all snapshots, backups cease to be an independent line of defense.

Mitigations:

- Offsite/cross-account backups where appropriate.
- Immutable/object-lock policies.
- Separation of backup deletion privileges.
- Retention aligned with RPO, regulations, and cost.
- Testing restores from offsite locations, not only the same availability zone.

### 14.5. Retention Policy

Example:

~~~text
Hourly snapshots:  keep 48 hours
Daily snapshots:   keep 30 days
Weekly snapshots:  keep 12 weeks
Monthly snapshots: keep 12 months
~~~

This is a policy example, not a MongoDB standard. Actual retention must fit compliance rules, data lifecycle, storage budgets, and delayed-incident investigation windows.

### 14.6. Data Deletion and Privacy

When an application deletes a document for privacy compliance, that data may persist inside older snapshots under retention. Define backup deletion/access-restriction policies aligned with laws and company rules; never assume `deleteOne` in production instantly erases bytes from every historical backup.

## 15. Backup Manifests: Knowing Exactly What Was Captured

### 15.1. Why Is a Manifest Needed?

Three months later, a folder named:

~~~text
mongo-backup-final-v2/
~~~

does not tell you which replica set it came from, which MongoDB version, whether the journal is present, which oplog position, which encryption key, or whether it passed a restore test.

A **backup manifest** binds the backup artifact to the metadata needed for controlled recovery.

### 15.2. Logical Manifest Example

~~~yaml
backupId: "mongo-343-2026-01-15T10:00Z"
backupKind: "volume-snapshot"
environment: "lab"
mongodb:
  deploymentKind: "replica-set"
  replicaSetName: "rsLab"
  sourceMember: "mongo-secondary-b.lab:27017"
  serverVersion: "RECORD_ACTUAL_VERSION"
  fcv: "RECORD_ACTUAL_FCV"
  storageEngine: "wiredTiger"
snapshot:
  requestedAtUtc: "2026-01-15T10:00:00Z"
  pointEstablishedAtUtc: "RECORD_ACTUAL_TIME"
  consistencyMode: "coordinated-snapshot"
  volumeGroupId: "RECORD_ACTUAL_GROUP"
  volumeSnapshotIds:
    - "RECORD_REAL_SNAPSHOT_ID"
  completionState: "RECORD_ACTUAL_STATE"
replication:
  sourceAppliedOptime: "RECORD_ACTUAL_OPTIMETIME"
  sourceMajorityCommittedOptime: "IF_AVAILABLE"
security:
  encryptionKeyReference: "KMS_KEY_REFERENCE_NOT_SECRET"
  backupAccessPolicy: "backup-restore-team"
validation:
  restoreDrillPassed: false
  restoreDrillTimestampUtc: null
~~~

These fields are an **illustrative operator-defined schema**, not a mandatory manifest format from MongoDB or any cloud provider.

### 15.3. Information to Record

| Group | Details |
| --- | --- |
| Identity | Backup ID, owner, environment, ticket/job ID |
| Topology | Standalone/replica set/sharded, member/shard/config |
| Engine | WiredTiger, MongoDB version, FCV |
| Storage | `dbPath`, volume IDs, mount points, snapshot IDs |
| Consistency | Snapshot mode, lock/stop coordination, group checkpoint |
| Replication | Source optime/lag, oplog continuity if applicable |
| Security | Encryption type and key reference (never the secret) |
| Lifecycle | Created/completed time, retention, immutable flag |
| Validation | Integrity checks, restore drill history, outcome |

### 15.4. Hashes/Checksums

If a backup is exported as archive/object files, checksums verify transfer integrity. For provider-managed block snapshots, rely on integrity checks and metadata exposed by the provider.

**A matching checksum only proves data did not change relative to the hashed source**; it does not prove the captured source was a MongoDB-consistent image. Restore drills are still required.

## 16. Restore: Thinking Properly Before Touching `dbPath`

### 16.1. Never Restore Over Running Production

A procedure should begin by:

1. Identifying an **isolated** restore target.
2. Identifying the backup ID and desired data point.
3. Confirming topology, MongoDB version/FCV, and encryption keys.
4. Retrieving all snapshots/volume groups of the **exact same generation**.
5. Ensuring target `mongod` is **stopped** before replacing physical files.
6. Restoring/mounting the entire filesystem per policy.
7. Verifying file ownership, permissions, and paths.
8. Starting MongoDB with compatible configuration for engine recovery.
9. Validating data and deciding whether to promote it as the recovery system.

**Never copy WiredTiger files from a snapshot into the `dbPath` of a running `mongod`.** Data files are actively open and written by the engine; partial replacement causes severe corruption.

### 16.2. Never Mix Backup Generations

Wrong:

~~~text
data files  -> Snapshot 2026-01-15 10:00
journal     -> Snapshot 2026-01-15 11:00
metadata    -> Snapshot 2026-01-14 10:00
~~~

Right:

~~~text
All files/volumes
  from a single consistency point
  per verified manifest and provider procedure
~~~

### 16.3. Journal Recovery When Opening a Snapshot

If a snapshot is crash-consistent, WiredTiger performs checkpoint/journal recovery. Startup can take longer than after a clean shutdown and will log recovery activity.

Never delete the journal just to start faster, and never ignore consistency mismatch errors. If recovery fails, **preserve the original backup**, record logs, and retry on a separate target copy once the root cause is understood.

### 16.4. Version and FCV

Physical backups are tied to storage files of a specific MongoDB version and Feature Compatibility context. Never assume old data files can be dropped into any newer or older `mongod` binary.

Before restoring:

- Record the source binary version.
- Record the **Feature Compatibility Version (FCV)**.
- Check supported upgrade/downgrade/restore paths.
- Restore into a supported version first, then execute upgrades if required.

A valid backup lacking compatible runtime binaries or KMS keys can still be **slow or impossible to recover**.

### 16.5. Replica Set Restore Differs From Standalone Restore

A physical data directory from a replica set carries member metadata and local state. Mounting it directly into an active cluster without proper procedures causes identity conflicts, oplog timeline mismatches, or rollbacks.

To **test a backup**, restore into an **isolated** environment using topology-appropriate official procedures. To **recover production**, establish a cluster-wide rollback/rebuild/member-seeding strategy and execute the exact runbook.

Never hand-edit **`local`** or **`config`** collections to "force" a member into a replica set.

### 16.6. Sharded Cluster Restore

Restore shards and config server metadata from a **coordinated backup generation** using supported restore workflows. Never restore only Shard A, restart `mongos`, and hope Shard B/config reconcile the missing pieces.

### 16.7. Restoring to Another Region or Account

Non-MongoDB blockers can include:

- Snapshot replication not finished yet.
- Missing KMS permissions in the target region.
- Incompatible disk types/sizes.
- Missing security groups/firewall routes.
- Hostname/TLS certificate mismatches.
- Missing secret manager access.
- Missing backup catalog metadata.

RTO must budget time to resolve these dependencies.

## 17. Restore Drills: A Backup Is Only Trustworthy Once Restored

### 17.1. Purpose

A **restore drill** is an exercise rebuilding the service from backups in a safe environment to prove:

- Snapshots exist and are readable.
- Required files are complete and consistent.
- WiredTiger starts up and recovers cleanly.
- Required collections, indexes, and users restore within scope.
- Data at the restore point matches expectations.
- The application can run critical queries.
- Restoration duration meets RTO targets.

### 17.2. Checklist After `mongod` Starts

| Check | Question |
| --- | --- |
| Process readiness | Does `mongod` open the storage engine without errors? |
| Logs | Did WiredTiger recovery complete cleanly? |
| Collections | Are all key namespaces present? |
| Counts | Do document counts match the restore point? |
| Indexes | Are key index definitions intact? |
| Sample documents | Are representative business events accurate? |
| Transactions | Are there any abnormal half-committed transaction states? |
| DB auth | Do database users/roles and related secrets work? |
| Application smoke tests | Do critical APIs succeed? |
| Performance | Are post-restore latency and storage acceptable? |
| Timing | Are actual RPO/RTO recorded? |

### 17.3. Example `mongosh` Smoke Checks

After restoring **in an isolated lab**, run with an appropriately authorized user:

~~~javascript
const restored = db.getSiblingDB("mongo_backup_lab_343");

printjson({
  collections: restored.getCollectionNames(),
  eventCount: restored.getCollection("events").countDocuments({}),
  latestEvents: restored.getCollection("events")
    .find({}, { _id: 1, kind: 1, createdAt: 1 })
    .sort({ createdAt: -1 })
    .limit(5)
    .toArray(),
  indexes: restored.getCollection("events").getIndexes()
});
~~~

Listing collections/indexes requires appropriate metadata privileges. If a restricted reader cannot run `getIndexes`, use an **auditor/restore-validation identity** provisioned per policy rather than granting `root` to an API.

### 17.4. Validating a Collection

In a **lab restore**, consider running the **`validate`** command:

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");

printjson(lab.runCommand({
  validate: "events"
}));
~~~

This command is resource-intensive and requires specific privileges; never run `validate` across an entire large production cluster as a casual post-snapshot check. Nor does it replace business logic, transaction, and RPO verification.

### 17.5. Calculating Actual RPO

Example:

~~~text
Latest known committed business event: 10:45:30
Latest event found after restore:      10:40:00

Actual observed data gap:
  approximately 5 minutes 30 seconds
~~~

Accurate measurement requires a reliable **business watermark/optime**, not merely `max(createdAt)` if application clocks drift or events arrive late.

### 17.6. Calculating Actual RTO

~~~text
10:50:00 failover/restore decision starts
11:08:00 volumes ready
11:14:00 mongod recovered
11:21:00 smoke checks passed
11:25:00 API serving traffic

Actual recovery service duration:
  35 minutes
~~~

Depending on internal definitions, the RTO clock starts at detection or disaster declaration, but must be **defined consistently prior to measurement**.

## 18. Logic Lab: Sample Data and Snapshot Boundary

### 18.1. Note on the Nature of This Lab

The lab below builds a **controlled `mongosh` dataset** so learners can simulate data points. It **does not create a physical MongoDB snapshot**. Actually testing storage snapshots requires LVM/cloud volumes/a backup platform configured in a dedicated environment.

The objective is understanding:

- A backup has a **restore point**.
- Writes arriving after the restore point **are absent from the snapshot**.
- Checkpoints/journal and PITR play distinct roles.
- Restore validation must know what data is expected as of that point.

### 18.2. Seeding the Lab Database

Run in `mongosh`; do not drop databases:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_backup_lab_343");
  const events = lab.getCollection("events");

  const base = [
    {
      _id: "b343-e001",
      labTag: "snapshot343-v1",
      kind: "booking_created",
      bookingId: "booking-100",
      amountCents: 1200000,
      createdAt: ISODate("2026-01-15T10:00:00Z"),
      phase: "before-snapshot"
    },
    {
      _id: "b343-e002",
      labTag: "snapshot343-v1",
      kind: "payment_pending",
      bookingId: "booking-100",
      amountCents: 1200000,
      createdAt: ISODate("2026-01-15T10:01:00Z"),
      phase: "before-snapshot"
    },
    {
      _id: "b343-e003",
      labTag: "snapshot343-v1",
      kind: "payment_confirmed",
      bookingId: "booking-100",
      amountCents: 1200000,
      createdAt: ISODate("2026-01-15T10:02:00Z"),
      phase: "before-snapshot"
    }
  ];

  for (const doc of base) {
    events.replaceOne(
      { _id: doc._id },
      doc,
      { upsert: true }
    );
  }

  events.createIndex(
    { labTag: 1, createdAt: 1 },
    { name: "ix_snapshot343_lab_time" }
  );

  printjson({
    baselineCount: events.countDocuments({
      labTag: "snapshot343-v1",
      phase: "before-snapshot"
    }),
    firstThree: events.find({
      _id: { $in: base.map(d => d._id) }
    }).sort({ createdAt: 1 }).toArray()
  });
})();
~~~

Baseline output: **3 events** timestamped 10:00, 10:01, and 10:02 UTC. Using fixed IDs and `replaceOne` makes the script idempotent on the dedicated lab collection. Creating an index with the same name is valid only if it does not already exist with a different key pattern.

### 18.3. Simulated Snapshot Point

Suppose a snapshot was taken at the logical point:

~~~text
T_snapshot = 2026-01-15T10:02:30Z

Inside snapshot:
  b343-e001
  b343-e002
  b343-e003
~~~

This is purely a **simulation exercise**; the query below does not prove a filesystem snapshot exists.

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");
const events = lab.getCollection("events");
const snapshotBoundary = ISODate("2026-01-15T10:02:30Z");

printjson(
  events.find({
    labTag: "snapshot343-v1",
    createdAt: { $lt: snapshotBoundary }
  })
  .sort({ createdAt: 1 })
  .toArray()
);
~~~

Expected result returns the three baseline events (before learners mutate the dataset).

### 18.4. Writing Data After the Boundary

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");
const events = lab.getCollection("events");

events.replaceOne(
  { _id: "b343-e004" },
  {
    _id: "b343-e004",
    labTag: "snapshot343-v1",
    kind: "booking_cancelled",
    bookingId: "booking-100",
    createdAt: ISODate("2026-01-15T10:04:00Z"),
    phase: "after-snapshot"
  },
  { upsert: true }
);

events.replaceOne(
  { _id: "b343-e005" },
  {
    _id: "b343-e005",
    labTag: "snapshot343-v1",
    kind: "refund_requested",
    bookingId: "booking-100",
    createdAt: ISODate("2026-01-15T10:05:00Z"),
    phase: "after-snapshot"
  },
  { upsert: true }
);

printjson({
  allLabEvents: events.countDocuments({
    labTag: "snapshot343-v1"
  }),
  beforeBoundary: events.countDocuments({
    labTag: "snapshot343-v1",
    createdAt: {
      $lt: ISODate("2026-01-15T10:02:30Z")
    }
  }),
  afterBoundary: events.countDocuments({
    labTag: "snapshot343-v1",
    createdAt: {
      $gte: ISODate("2026-01-15T10:02:30Z")
    }
  })
});
~~~

Expected output: **`allLabEvents` = 5**, **`beforeBoundary` = 3**, **`afterBoundary` = 2**.

### 18.5. Meaning for Restore

If a real physical snapshot was captured **before e004/e005 were written**, restoring that snapshot **will not contain e004/e005**. Recovering post-snapshot events requires **PITR** or business replay from an external source.

**Important warning:** Querying `createdAt` on a live collection **is not snapshot restoration**. It merely models pre/post sets using a business timestamp field. With late-arriving writes, an event carrying an older `createdAt` can be written after the snapshot; filtering by `createdAt` then **does not accurately reflect** byte-level snapshot membership.

### 18.6. Simulating a Late-Arriving Event

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");
const events = lab.getCollection("events");

events.replaceOne(
  { _id: "b343-late" },
  {
    _id: "b343-late",
    labTag: "snapshot343-v1",
    kind: "late_external_notification",
    bookingId: "booking-100",
    createdAt: ISODate("2026-01-15T10:01:30Z"),
    ingestedAt: ISODate("2026-01-15T10:06:00Z"),
    phase: "after-snapshot"
  },
  { upsert: true }
);
~~~

The event was **written after the snapshot** yet has a **`createdAt` before the boundary**. Therefore:

~~~javascript
events.find({
  createdAt: {
    $lt: ISODate("2026-01-15T10:02:30Z")
  }
});
~~~

returns `b343-late` on the **live database**, even though that event **did not exist in the older physical snapshot**. Lesson: to determine the **true restore point**, never rely solely on application timestamps.

## 19. Pre-Snapshot Preparation Runbook

### 19.1. Confirm Backup Target

1. Identify deployment: standalone, replica set, or sharded cluster.
2. Identify the backup member and rationale for choosing it.
3. Confirm RPO/RTO/SLA for the backup job.
4. Confirm snapshot tooling/provider support and verification.
5. Assign an accountable owner with KMS/storage access.

### 19.2. Confirm Health

1. Verify `mongod` is healthy.
2. Check disk/free space and snapshot COW capacity if applicable.
3. Check replication lag, oplog window, and member state.
4. Confirm no initial sync, rollback, or abnormal maintenance is active.
5. Confirm the snapshot/copy destination has enough capacity and quota.

### 19.3. Confirm Consistency

1. Inventory `dbPath`, journal, and data/index/metadata dependencies.
2. Map paths to **volumes and mount points**.
3. Verify atomic snapshot or consistency group support.
4. Decide between clean shutdown or `fsyncLock`.
5. Define when the snapshot point is considered established.
6. Build unlock/unfreeze handling across every failure branch.

### 19.4. Confirm Security

1. Backup identity is separate from application root credentials.
2. Snapshots are encrypted.
3. Key/KMS permissions are available at restore time.
4. Retention and offsite policies are in place.
5. Manifest contains no plaintext secrets.

### 19.5. Confirm Restore Readiness

1. Isolated restore target is identified.
2. Compatible MongoDB version is available.
3. Topology recovery runbook exists.
4. Smoke queries and expected outcomes are defined.
5. Last/next restore drill dates are scheduled.

## 20. Snapshot Runbook Coordinated With WiredTiger

### 20.1. Phase A — Prepare

~~~text
Collect:
  deployment + member identity
  MongoDB version + FCV
  storageEngine
  dbPath + journal volumes
  rs/shard status
  source applied optime
  backup credentials + permissions
  encryption key references
~~~

If volume mapping information is missing, **halt** instead of blindly snapshotting a volume with a plausible name.

### 20.2. Phase B — Quiesce per Runbook

For cold backups: cleanly stop `mongod` on an authorized node.

For hot snapshots: run `fsyncLock` where supported, monitor lock duration, and keep an independent unlock path ready.

For integrated backup platforms: follow the product's coordination steps—**never inject manual `fsyncLock`** if the tool manages its own mechanism and adding a lock would interfere.

### 20.3. Phase C — Create Consistent Snapshot Point

Request the provider to create a snapshot point across all required volumes. Success statuses must follow the provider contract:

~~~text
SUCCESS FOR COORDINATION
  = snapshot point established

SUCCESS FOR RETENTION/RESTORE
  = data stored, verified, and
    usable for recovery
~~~

These two states can occur at different times. Once the snapshot point is fixed, you may release the lock per runbook, while the job continues tracking snapshot export/replication until completion.

### 20.4. Phase D — Unlock and Verify Source

After establishing the storage snapshot point:

- Run `fsyncUnlock`/thaw or restart the member per procedure.
- Verify writes resume normally.
- Verify replication lag shrinks.
- Check member health.
- Review post-backup metrics/alerts.

**If unlocking fails, treat it as an immediate operational incident**, even if snapshot upload continues.

### 20.5. Phase E — Commit Backup Manifest

Mark a backup **usable** only when:

- Snapshot state is valid.
- Consistency group/volume IDs are complete.
- No errors were reported by the provider.
- Key references/permissions are verified.
- Manifest records restore point and topology.
- Backup catalog/retention policy is updated.

Then schedule a restore drill or appropriate integrity verification.

### 20.6. Phase F — Monitor

Track:

~~~text
backup start -> coordination -> snapshot point
             -> transfer complete -> catalog ready
             -> restore validation
~~~

Do not alert only when a job fails to start; alert whenever there is **no usable successful backup** within the configured RPO/retention window.

## 21. Failure Scenarios and Actions

| Scenario | Consequence | Appropriate Action |
| --- | --- | --- |
| Snapshot includes data volume only, missing journal | Recovery may fail or lose data | Complete path inventory; use consistency group |
| Data/journal snapshotted at different times | Not crash-consistent | Atomic group or proper write coordination |
| `cp`/`rsync` on live `dbPath` | Mixed file versions | Never treat as a valid physical backup |
| `fsyncLock` run and unlock forgotten | Writes/replication stall | Emergency unlock runbook, lock monitoring |
| Lock held during hours-long upload | Severe latency/lag | Unlock as soon as snapshot point is fixed |
| Secondary snapshot taken with 15-minute lag | RPO worse than wall-clock expectation | Record source optime; choose healthy member |
| Backup member in initial sync | Data incomplete/invalid | Wait for healthy `SECONDARY` state |
| Gap in oplog archive | Discontinuous PITR | Alert and take fresh base backup/repair chain |
| Shards snapshotted sequentially uncoordinated | Cross-shard state inconsistency | Coordinated sharded backup |
| Backed up only `mongos` | No database data captured | Back up all shards + config servers |
| Volume snapshot created but export fails | Backup unusable for restore | Track full completion before marking usable |
| Snapshot lacks manifest | Unknown source/version/keys | Generate manifest and catalog entry |
| Lost KMS key | Unable to decrypt for restore | Maintain DR key access plan |
| Backups in same account as production | Can be deleted together in incident | Offsite/immutable storage and access separation |
| Restoring into a running `mongod` | Severe corruption risk | Stop target and restore in isolation |
| Mixing snapshot generations | Metadata/journal mismatch | Use one consistent snapshot point |
| Restoring into incompatible MongoDB version | Engine rejects data files | Record version/FCV; follow supported paths |
| Mounting replica snapshot directly into active RS | Oplog/member state conflicts | Follow official RS recovery procedures |
| Data restored yet API errors | Missing config/secrets/network/indexes | Run end-to-end restore drills |
| RPO calculated from wall-clock snapshot time | Wrong when secondary lags | Use optime/restore watermark |
| "PITR" is only an old `local.oplog.rs` file | Missing post-snapshot logs | Use continuous archival and supported backup tools |
| Testing via `createdAt` timestamps | Misses late-arriving writes | Use restore point metadata |
| Checking only checksum | Does not prove database consistency | Boot `mongod` and validate restore |

## 22. Design Scenarios: Three Systems With Different Needs

### 22.1. System A — Standalone for Non-Critical Data

~~~text
Data: 15 GiB
RPO: 24 hours
RTO: 4 hours
Downtime: 10 minutes overnight acceptable
~~~

A **clean shutdown + full volume snapshot** during the maintenance window works, followed by restart and restore drills. Simple, though incurring downtime; backups still require encryption and offsite storage.

### 22.2. System B — Continuously Scheduled Replica Set

~~~text
Data: 600 GiB
RPO: 30 minutes
RTO: 90 minutes
Primary: high write load
Dedicated secondary: available
~~~

Consider **snapshotting the secondary** with a storage consistency group and `fsync` coordination if needed. Monitor lag/oplog closely, finish backups within budget, and benchmark restore throughput. If snapshots run every 30 minutes while secondary lag is 20 minutes, effective RPO is already worse than planned.

### 22.3. System C — Sharded Transactional Platform

~~~text
Data: 10 TiB
RPO: 1 minute
RTO: 60 minutes
Multiple shards + config server RS
Distributed transactions
~~~

This cannot be solved by **an uncoordinated snapshot cron job on every host**. You need a solution supporting cluster-wide consistent backups and continuous logs/PITR, strict restore testing, standby recovery infrastructure, and a traffic cutover strategy.

### 22.4. Same Storage Engine, Different Backup Requirements

WiredTiger is the storage engine across all three systems. What differs is:

- Tolerable impact on availability.
- Data scale and topology.
- RPO/RTO targets.
- Required coordination level.
- External system dependencies.

No single snapshot command fits every system without adaptation.

## 23. Frequently Asked Questions

### 23.1. Can I copy `/var/lib/mongodb` while `mongod` is running?

**Never treat an ordinary file copy of a running server as a consistent physical backup.** Files can be copied at different instants while WiredTiger mutates them. Use a supported backup tool, a clean shutdown, or a properly coordinated atomic storage snapshot.

### 23.2. If I have the journal, will any snapshot work?

**No.** The journal enables crash recovery when files belong to a consistent storage state. It cannot repair a dataset stitched from inconsistent timestamps.

### 23.3. Can I just run `fsyncLock` and `rsync` for as long as needed?

Holding a lock through a long `rsync` causes write outages and replication lag. With storage snapshots, the goal is establishing a **fast atomic snapshot point** and unlocking once the provider guarantees that point is fixed. Copying under lock or cold copying requires careful downtime and semantic analysis, usually unsuitable for heavy-write systems.

### 23.4. Does snapshotting a secondary affect the primary?

It does not directly lock primary writes, yet still indirectly impacts HA/quorum, replication lag, oplog window, and shared resources. An unhealthy or overly locked backup member remains an operational risk.

### 23.5. Does having snapshots mean I have PITR?

**Not yet.** A snapshot provides a single point. Restoring between snapshots requires continuous log/backup capture and a formal gap-free replay mechanism.

### 23.6. Can WiredTiger data files from an old version be restored into any newer version?

Do not assume so. Physical storage formats, FCV, and upgrade/downgrade paths carry constraints. Verify supported restore paths and test in isolation.

### 23.7. Can one shard's backup restore the whole cluster?

No. A sharded cluster comprises multiple shards and config server metadata; full recovery must coordinate all components from a matching generation.

### 23.8. For cloud backups, do I need to save keys myself?

You need a **process ensuring KMS/key access at restore time**, without copying plaintext keys alongside backups. Use proper secret/key management and test cross-region/account access.

### 23.9. Checksum matches, yet `mongod` refuses to start?

A checksum only proves bytes did not change relative to a reference source. If the source was an inconsistent live-file copy, the hash will still match. Inspect restore logs, storage consistency, version, FCV, journal, and encryption.

### 23.10. With replication already running, why do we still need backups?

Replication provides availability, yet **accidental deletions, bad updates, corrupted data, and certain compromises replicate immediately to secondaries**. Backups preserve independent historical points, requiring retention and restoration outside the live replica set.

## 24. Practice Exercises

### Exercise 1 — Concepts

Explain the differences between a volume snapshot, crash-consistent backup, application-consistent backup, and MongoDB `readConcern: "snapshot"`. Which can serve as database recovery material?

### Exercise 2 — WiredTiger

Describe the roles of checkpoints and the journal in crash recovery. Why should a checkpoint file never be treated as a standalone backup?

### Exercise 3 — Copying Live Files

A script copies file A at 10:00, file B at 10:15, and the journal at 10:20 while `mongod` writes. Analyze why zero copy errors still fail to prove a valid backup.

### Exercise 4 — Single Volume

MongoDB `dbPath` and journal share one volume. The storage provider offers atomic crash-consistent volume snapshots. What conditions must you verify before adopting them as backups?

### Exercise 5 — Multiple Volumes

`dbPath` spans volume A and the journal sits on volume B. A is snapshotted at 12:00:00 and B at 12:00:10. Why can these two snapshots not be called a single consistency point? Propose a fix.

### Exercise 6 — `fsyncLock`

What is the role of `fsyncLock` in a snapshot runbook? Why shouldn't the lock stay held until the entire backup uploads to object storage?

### Exercise 7 — Unlock Failure

The snapshot API times out after `fsyncLock`. Design the cleanup/alert/manual-unlock path. Which metrics/health checks should you inspect afterward?

### Exercise 8 — Cold Backup

Draft a cold backup procedure for a lab `mongod`: prep, shutdown, snapshot, restart, validation. What drawbacks make this hard to run on a production primary?

### Exercise 9 — Secondary Lag

Primary optime is 10:30, backup secondary optime is 10:25, and wall-clock snapshot time is 10:31. How does actual RPO differ from snapshot creation time?

### Exercise 10 — Majority Write

A write is majority-acknowledged on a 3-member replica set, yet Secondary B has not applied it. Is Secondary B's snapshot guaranteed to contain that write? Explain.

### Exercise 11 — Oplog Window

A backup secondary is write-locked for 30 minutes and then must catch up. The primary's oplog window is only 20 minutes. What risks arise?

### Exercise 12 — Choosing a Member

In a 3-member replica set, pick a backup source member and list the health, replication, and quorum conditions to check.

### Exercise 13 — Snapshot Point vs. Completion

The provider returns job accepted at 10:00, establishes the snapshot point at 10:00:05, and finishes uploading at 10:18. When can you unlock? When can you mark the backup usable?

### Exercise 14 — RPO

Backups run hourly, an outage hits at 10:59, and the latest snapshot is from 10:00. No PITR exists. Calculate potential data loss and propose policy changes for a 10-minute RPO.

### Exercise 15 — RTO

Volume restore takes 35 minutes, `mongod` recovery 8 minutes, data verification 12 minutes, and cutover 10 minutes. What is the minimum actual RTO if steps run sequentially?

### Exercise 16 — PITR

A system has a base snapshot at 08:00, continuous oplog capture through 12:00, and an incident at 11:59. To restore to 11:55, what conditions on log continuity, restore engine, and timestamps are needed?

### Exercise 17 — PITR Gap

Oplog archival suffers a 45-minute gap while scheduled snapshots still run. Why can you not claim PITR to every timestamp inside that window?

### Exercise 18 — Sharded Cluster

A chunk migrates from A to B between two snapshots. Explain the metadata and data risks without cluster-wide coordination.

### Exercise 19 — Config Server

Why are shard snapshots without config server metadata insufficient to restore a sharded cluster?

### Exercise 20 — Balancer

Does stopping the balancer alone guarantee a consistent sharded-cluster snapshot? What issues remain with application writes, transactions, and oplogs?

### Exercise 21 — Atlas

Draft a checklist of questions before trusting Atlas backups: tier, snapshot schedule, retention, PITR, restore target, key policy, and latest successful backup.

### Exercise 22 — Encryption

An encrypted snapshot is intact, yet the organization lost the KMS key. What happens on restore? Design cross-account/region key-access testing.

### Exercise 23 — Immutable Backups

Why does intra-cluster replication not replace immutable/offsite backups? Analyze ransomware or an admin accidentally dropping a whole collection.

### Exercise 24 — Manifest

Propose a backup manifest containing version, FCV, storage engine, `dbPath`, volumes, snapshot IDs, applied optime, consistency point, encryption key reference, and restore drill results.

### Exercise 25 — Version Compatibility

A WiredTiger snapshot was taken on MongoDB version X, while the target only has binary version Y. List checks needed before booting `mongod` with those data files.

### Exercise 26 — Restore Drill

Design an isolated restore drill: mount volumes, boot `mongod`, inspect logs, collections, indexes, business samples, and calculate actual RPO/RTO.

### Exercise 27 — Lab Seed

Run the seed in Section 18. Verify the three pre-snapshot events. After adding `e004`/`e005`, explain why a physical snapshot at 10:02:30 does not contain those two later events.

### Exercise 28 — Late-Arriving Event

Event `b343-late` is written at 10:06 with `createdAt=10:01:30`. Why does filtering `createdAt < 10:02:30` on the live DB not prove the event existed in the older snapshot?

### Exercise 29 — Business Reconciliation

MongoDB restores to 10:00 while the payment provider already charged at 10:15. What workflow prevents double-charging or losing payment records?

### Exercise 30 — Runbook Review

Team A proposes `fsyncLock`, `rsync` of live `dbPath` for 3 hours, then unlock. Team B proposes a healthy secondary, an atomic volume snapshot in seconds, unlock, and copying from the snapshot. Compare risks, prerequisites, and required checks.

### Exercise 31 — Backup Monitoring

Design a dashboard tracking backup age, latest usable backup, snapshot completion, oplog archival gaps, replication lag, `fsyncLock` duration, storage capacity, KMS access, and restore drill age.

### Exercise 32 — Role Separation

Who should hold privileges to create/delete snapshots, restore MongoDB, read backup manifests, manage KMS, and read restored data? Why shouldn't one production API credential do all of these?

### Exercise 33 — Storage Provider Contract

A cloud API supports snapshotting three volumes in one request without specifying consistency groups. What must you verify before certifying the MongoDB snapshot as valid?

### Exercise 34 — Designing RPO/RTO

A 3 TiB, 3-member replica set with RPO = 15 minutes and RTO = 90 minutes. Propose a snapshot schedule, PITR policy, backup member, offsite storage, encryption, restore infrastructure, and drill verification plan.

## 25. References

- MongoDB Manual — [Backup Methods](https://www.mongodb.com/docs/manual/core/backups/).
- MongoDB Manual — [Back Up and Restore with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/).
- MongoDB Manual — [Back Up and Restore a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/).
- MongoDB Manual — [db.fsyncLock()](https://www.mongodb.com/docs/manual/reference/method/db.fsyncLock/).
- MongoDB Manual — [db.fsyncUnlock()](https://www.mongodb.com/docs/manual/reference/method/db.fsyncUnlock/).
- MongoDB Manual — [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/).
- MongoDB Manual — [Journaling](https://www.mongodb.com/docs/manual/core/journaling/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Replication Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Manual — [Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/).
- MongoDB Atlas — [Backup Overview](https://www.mongodb.com/docs/atlas/backup-restore-cluster/).
- MongoDB Atlas — [Point-in-Time Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/#point-in-time-restore).
- MongoDB Ops Manager — [Backup and Restore](https://www.mongodb.com/docs/ops-manager/current/backup/).
- MongoDB Database Tools — [mongodump](https://www.mongodb.com/docs/database-tools/mongodump/).
- MongoDB Database Tools — [mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/).

**Conclusion:** A **snapshot** is a storage capture at a point in time, not magic that automatically makes any set of MongoDB files consistent. With **WiredTiger**, you must understand **checkpoints, the journal, `dbPath`, and crash recovery**; treat a physical backup as trustworthy only when all required components are captured in **one atomic/consistent state**, especially across multiple volumes. You can coordinate via **clean shutdown**, **`fsyncLock`/`fsyncUnlock`**, or a **supported backup platform**, favoring an eligible secondary to reduce primary impact while still verifying **replication lag, oplog window, and RPO/RTO**. For **sharded clusters**, snapshots must be coordinated across shards and config servers; independent per-host snapshots are insufficient. Finally, backups must be **encrypted, stored independently, tracked via manifests, paired with supported restore paths, and proven via periodic restore drills**. A snapshot is truly valuable only when you **can boot MongoDB from it, validate the data, and restore service within targets**.
