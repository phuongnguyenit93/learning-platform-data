# Disk Full, Memory Pressure, and Prioritizing Safe Recovery Actions in MongoDB

A MongoDB system that had been running steadily suddenly begins returning write errors, Java applications time out, and latency graphs spike sharply. The dashboard shows the filesystem hosting `dbPath` has only a few hundred MiB left; meanwhile, several MongoDB containers are restarting with `OOMKilled`. The on-call operator may feel pressured to "free space immediately," yet making the wrong choice—deleting WiredTiger files, deleting the oplog, dropping indexes, restarting the whole replica set, or running `compact` on a full disk—can turn a recoverable resource incident into **data loss or prolonged downtime**.

This lesson, **"Disk Full, Memory Pressure, and Prioritizing Safe Recovery Actions in MongoDB,"** belongs to the **Troubleshooting** chapter of the **Database Engine Document MongoDB** module. Its focus is **decision-making during a live incident**: which signals to observe first, how to isolate root causes, how to shed load safely, which actions are safe and reversible, when to expand resources, how to recover members one by one without breaking quorum, and how to validate data and applications afterward.

Objectives:

1. Distinguish **disk capacity full**, **inode/quota full**, **read-only filesystem**, **disk I/O saturation**, and **memory pressure/OOM**.
2. Quickly interpret key signals from Linux, `mongod`, Docker, Kubernetes, and MongoDB Atlas.
3. Understand why WiredTiger files, the journal, and the oplog **are not disposable junk that can be deleted manually**.
4. Follow the sequence: **stop harm → verify topology → preserve data → expand resources/shed load → recover → reconcile**.
5. Avoid "treating symptoms" with `compact`, `repair`, deleting millions of documents, or increasing replica count while data is at risk.
6. Control backpressure, retries, and idempotency on the Java/Spring Boot side so applications do not further exhaust the database.
7. Build runbooks for standalone, replica set, sharded cluster, container, and Atlas environments.
8. Establish recovery drills, growth-rate alerting, RPO/RTO alignment, and postmortems.

> **Safety principle:** command examples are primarily **read-only status checks**. Changes such as resizing volumes, adjusting cgroup limits, restarting MongoDB, stepping down a primary, halting write sources, deleting data, altering TTLs, resyncing members, or restoring backups must follow an approved runbook with topology/backup evaluation and operational authorization. Never perform data-destructive actions merely because a command appears to shrink `df` immediately.

## 1. Four Layers to Identify Before Intervening

```text
Java / API Applications
  |
  | request rate, retry storm, bulk writes
  v
MongoDB mongod / mongos
  |
  | WiredTiger cache, journal, checkpoints,
  | oplog, replication, query execution
  v
OS / container / cgroup
  |
  | RAM limit, OOM killer, page cache,
  | file descriptors, mount, inode, quota
  v
Storage backend
  |
  | capacity, IOPS, throughput, latency,
  | snapshots, attached volumes, failures
  v
Disk / managed storage
```

A fault at a lower layer can manifest at an upper layer:

- Extremely slow disk I/O → `mongod` responds slowly → driver waits longer → API timeouts → clients retry → request rate rises → disk gets even slower.
- Low memory limit → `mongod` gets OOM-killed → applications see connection resets → retries surge → recovery/checkpoints take extra load.
- Volume out of space → journal/checkpoint/writes fail → member stops serving normally → replica set loses majority → applications cannot write.
- Wrong mount path → MongoDB starts on another or empty filesystem → looks like "data loss" even though the original volume still exists.

Therefore, **never read just one Java stack trace and immediately tweak MongoDB**.

## 2. Distinguishing "Disk Full" from "Slow Database"

| Symptom | Common evidence | Do not jump to conclusions |
| --- | --- | --- |
| **Out of bytes** | `df -h` near or at 100%, `ENOSPC` | Every write failure is due to oversized documents |
| **Out of inodes** | `df -i` full, cannot create files | Many GiB free in `df -h` means it's safe |
| **Disk quota** | Filesystem has space, yet user/project quota hit limit | Simply growing the cloud volume is enough |
| **Read-only filesystem** | Mount options `ro`, kernel I/O errors | Just needs `chown`/`chmod` |
| **I/O saturation** | High latency/queue depth, IOPS or throughput capped | 40% free disk means enough performance |
| **WiredTiger cache pressure** | Rising eviction/dirty pages/disk reads | All RSS memory is cache |
| **OOM kill** | K8s `OOMKilled`/kernel logs/cgroup events | MongoDB crashed on its own due to a bug |
| **OS page cache fluctuation** | Low "free" RAM, yet "available" remains | Low free RAM always requires a restart |

Signals can occur **simultaneously**. A saturated disk slows eviction and checkpoints; scarce RAM increases disk reads; write retries grow the oplog faster. Investigations should trace the **causal chain** rather than pinning a single label.

## 3. Decision Flowchart for the First 5 Minutes

```text
Alert: write errors / p99 latency / mongod restart
                  |
                  v
           Is any data at risk?
                  |
          +-------+--------+
          |                |
         Yes            Unclear
          |                |
          v                v
   Preserve evidence   Check backups/
   and block data-     topology/RPO
   destructive steps       |
          +--------+-------+
                   |
                   v
       Is Host / PVC / Atlas storage full?
             /          \
           Yes           No
            |             |
            v             v
       bytes/inode/     OOM / cache /
       quota/RO/IOPS    CPU/I/O/network
            \            /
             \          /
              v        v
        Identify member and role
        (primary/secondary/config shard)
                  |
                  v
     Throttle error sources, protect quorum
                  |
                  v
      Least destructive action possible
                  |
                  v
      Verify data + replication + APIs
```

This is an **order of reasoning**, not a promise that every incident resolves in five minutes. Sometimes **halting non-essential writes** immediately takes priority over gathering heavy metrics.

## 4. Safety Priorities: What Goes First, What Comes Later?

| Priority | Action | Purpose | Condition |
| --- | --- | --- | --- |
| P0 | Halt improvised destructive commands | Prevent secondary data loss | Apply immediately |
| P0 | Verify member topology/quorum/role | Avoid paralyzing the cluster | Before restart/stepdown |
| P0 | Curb non-essential write bursts/retry storms | Stop the situation from worsening rapidly | Coordinate with app owner |
| P0 | Check backup/recovery options | Know how far data can be recovered | Don't wait until data is deleted |
| P1 | Measure exact bytes, inodes, mounts, quotas, I/O latency/RAM | Isolate true root cause | Use read-only commands |
| P1 | Expand volume/RAM/IOPS via supported paths | Add headroom without deleting data | Verify backend/topology |
| P1 | Clean verified safe **artifacts outside `dbPath`** | Reclaim temporary space if needed | Confirm exact file, owner, retention |
| P1 | Recover members in quorum-preserving order | Restore availability | Follow replica set runbook |
| P2 | Fix workload/indexes/retention, tune cache | Prevent recurrence | After system stabilizes |
| P2 | Right-size resources, improve alerts | Capacity/performance planning | Based on real metrics |

**Never P0:** `rm -rf /var/lib/mongodb/journal`, `rm WiredTiger*`, `db.dropDatabase()`, `rs.reconfig(..., {force:true})`, restarting all members, reflexively running `--repair`, or deleting volumes/PVCs. These carry vastly greater risk than adding capacity or throttling write sources.

## 5. Collecting Minimum Information Without Adding Load

Information to record:

```text
Incident ID:
Start time:
Cluster / environment:
MongoDB version:
Standalone / replica set / sharded:
Node role: primary / secondary / config server / mongos
Storage path / mount / PVC / volume ID:
Disk bytes free / inode free:
Disk I/O latency / queue:
Process memory RSS / cgroup memory limit:
Restart count / OOM events:
Replication health / lag / majority available:
Write error samples / app request rate:
Last verified backup:
Required RPO / RTO:
Recent deploy / migration / data import:
```

Do not paste credentials/PII, full BSON records, or internal keys into unprotected incident tickets. Logs should include correlation IDs and sanitized metrics.

### Why Record a Baseline First?

If you restart immediately, in-memory counters and evidence are lost. If you delete files or volumes, recovery artifacts disappear. However, **never delay safe load reduction** merely to collect a huge `serverStatus` dump while the system is severely jammed.

## 6. Classifying Impact Severity

A "disk at 95%" alert is not necessarily as severe as "primary cannot journal and applications cannot write." You can classify as:

| Severity | Situation | Typical action |
| --- | --- | --- |
| **Sev 1 / urgent** | Primary or majority of members cannot write/serve; data loss/quorum risk | Incident command, throttle writes, preserve data, scale capacity/recover by topology |
| **Sev 2 / high** | One secondary full and lagging heavily; primary remains healthy | Protect quorum, recover the secondary under control |
| **Sev 3 / warning** | Low free disk while service stays healthy; early fullness projection | Plan resize and address growth |
| **Sev 3 / degraded** | Memory pressure/cache eviction raises p99 without crashing | Right-size/throttle workload, watch risk |

These are illustrative classifications, not a replacement for internal severity policies. Real priority depends on **customer impact, data at risk, quorum, write availability, resource exhaustion rate, and RTO/RPO**, rather than a static percentage threshold.

## 7. Inspecting the Filesystem Hosting `dbPath` on Linux

First, determine the actual `storage.dbPath` from the **running `mongod`** config or startup arguments rather than guessing package defaults:

```bash
# Observation commands; do not modify data.
ps -eo user,pid,cmd | grep '[m]ongod'
systemctl cat mongod
```

Assuming `dbPath` is `/var/lib/mongodb`, inspect:

```bash
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt -T /var/lib/mongodb
lsblk -f
```

Meaning:

- `df -hT`: capacity and filesystem type of the volume.
- `df -i`: remaining inodes.
- `findmnt -T`: the actual mount containing the path, including mount options.
- `lsblk -f`: block devices/filesystems; in managed/container environments, inspect alongside cloud/CSI metadata.

### Warning: A Mis-Mount Is More Dangerous Than a Small Disk

A host expecting a data disk mounted at `/var/lib/mongodb` whose mount failed may leave that directory sitting on the **root filesystem**. The process may write onto the root disk or expose an empty database depending on configuration and existing directory contents.

Do not generate new data and "accept an empty database" before verifying mounts. Verify volume ID, filesystem UUID, path, and contents per runbook. Attaching an old volume to the wrong node can also trigger ownership, format, or security errors.

## 8. Out of Bytes: `ENOSPC` and Consequences

`ENOSPC` means "No space left on device." When the filesystem holding `dbPath` can no longer allocate space:

- MongoDB cannot create or extend needed files.
- Journal, checkpoint, and storage writes fail.
- Index builds, imports, initial syncs, or temporary files fail.
- Logs or diagnostics cannot be written if they share the same filesystem.
- The member may stop or become unhealthy depending on server/storage failure modes.
- Applications experience timeouts, write failures, and failovers depending on topology.

**Never assume a timed-out `insertOne()` wrote nothing.** If the client receives no acknowledgment, the outcome is ambiguous; reconcile with a business idempotency key rather than unconditionally inserting a new record.

### "MongoDB Logical Data" Does Not Grow 1:1 with Filesystem Usage

Disk consumption includes:

```text
WiredTiger data files
 + index storage
 + journal/checkpoint internals
 + replica set oplog
 + temporary/index-build files
 + log files/backup artifacts if sharing the filesystem
 + filesystem metadata / snapshots / quotas
```

Looking only at `db.stats().dataSize` misses indexes, oplog, journal, overhead, and co-located files on the same volume.

## 9. Inode and Quota Exhaustion: `df -h` Is Not Enough

A filesystem can have many GiB free yet still fail to create files because:

- **Inodes** are exhausted (especially with many small files).
- User, project, or container **quotas** hit their cap.
- Volume, thin-provisioning, or snapshot pool limits are reached.
- The filesystem switched to read-only due to I/O errors.

Check:

```bash
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt -T /var/lib/mongodb
```

If `df -h` shows free space while writes fail, inspect events, logs, quotas, and backing storage. Do not assume the issue is a bad BSON document or permissions error.

### Do Not "Test Write a File" Inside `dbPath`

During an incident, never write test files inside the WiredTiger directory to check writability. If filesystem write testing is needed, follow the runbook on a separate authorized test path with minimal size, or inspect existing diagnostics instead of filling the data volume further.

## 10. Read-Only Filesystem and I/O Errors

A filesystem can remount as `ro` when the kernel or storage layer detects errors. When that happens, `chmod`, `chown`, restarting, or refreshing credentials **will not fix the root cause**.

Observation commands:

```bash
findmnt -T /var/lib/mongodb
journalctl -k --no-pager -n 100
```

Look for signals:

- `I/O error`.
- Filesystem metadata errors.
- Device disconnects/timeouts.
- Read-only remounts.
- Storage backend unavailable.

**Do not force a filesystem back to read-write** before understanding why it went read-only. Hardware or metadata corruption may require storage/OS vendor procedures. Secure backups/snapshots and storage admin approval before any filesystem-level repair.

## 11. Disk Not Full, Yet Saturated by I/O

Disk capacity and I/O speed are separate dimensions:

| Metric | Question |
| --- | --- |
| Free bytes | Is there room left to store data? |
| IOPS | How many operations/second can the disk handle? |
| Throughput | How many MiB/second can the disk transfer? |
| I/O latency | How long does each operation wait? |
| Queue depth | How many I/O requests are queued? |
| Cloud burst credits | Have temporary burst credits been exhausted? |

A cloud SSD volume can be 50% empty while hitting its IOPS or throughput ceiling. `mongod` then suffers slow checkpoints/journals, slow index/data reads, and secondary lag.

If `sysstat` is available:

```bash
# Sample briefly; check the actual block device backing dbPath.
iostat -xz 1 5
```

In cloud/Kubernetes environments, correlate volume/CSI metrics because host or container stats may be incomplete or aggregate multiple workloads. Do not blindly increase disk GiB if the bottleneck is an IOPS policy cap; and do not blindly add vCPUs if all threads are blocked on storage.

## 12. Pinpointing What Is Driving Disk Growth

Common culprits:

1. Surging insert/ingest rate.
2. New indexes or index builds on large collections.
3. Larger oplog sizing or rapid oplog growth under current writes.
4. Backups, dumps, or exports written to **the same volume** as `dbPath`.
5. Unrotated application, system, or MongoDB logs.
6. Temporary files, staging data, or other snapshots/caches consuming space.
7. Old data not purged properly by TTL/retention rules.
8. Resync or index migrations generating heavy storage churn.
9. Cloud snapshots, thin-provisioning pools, or volume quotas with hidden caps.

### Inspect Filesystem Layout Safely

```bash
# Check capacity of relevant mounts:
df -hT /var/lib/mongodb /var/log

# Inspect log directory once the path is verified:
ls -lh /var/log/mongodb
```

A recursive scan such as `du -x -h -d 1 /var/lib/mongodb` walks heavy metadata trees, adding I/O to an already overloaded disk. **Do not reflexively run heavy recursive scans**; narrow timing and scope, and prefer existing telemetry first.

### Deleted-But-Open Files

On Linux, a deleted log file still held open by a process continues consuming disk space until its file descriptor closes. With proper privileges and only when genuinely needed:

```bash
# Can consume resources; run only when authorized and necessary.
lsof +L1
```

Never blindly restart `mongod` solely to release an open log handle; verify topology/quorum and whether safe log rotation/reopen mechanisms exist.

## 13. Why Must You Never Delete WiredTiger, Journal, or Oplog Files?

Files inside `dbPath` are **internal state** of the storage engine and server:

```text
dbPath/
  WiredTiger* ...
  collection/index data files ...
  journal/ ...
  internal metadata ...
```

File names and layouts evolve across versions; never treat them as a stable manual folder structure.

Deleting a file can cause:

- Failure of the storage engine to start.
- Inconsistent metadata or corrupted data.
- Inability to perform crash recovery properly.
- Secondaries unable to catch up or resume oplog replication.
- Longer restore times and elevated risk of data loss.

**Never try to solve disk-full incidents by deleting `journal/`, `WiredTiger.wt`, `collection-*.wt` files, or manually truncating `local.oplog.rs`.**

MongoDB manages its journal, checkpoints, storage reuse, and oplog sizing/retention internally. Use only **MongoDB-supported database commands and runbook procedures**, never direct file edits.

## 14. Load-Reduction Sequence When a Filesystem Nears Full

A sequence typically far less risky than deleting data:

1. **Halt non-essential ingestion**: batch imports, ETL jobs, data-generating analytics, and non-urgent index rebuilds.
2. **Stop application retry storms**: apply backoff, cap concurrency, and open circuit breakers per policy.
3. **Assess business-critical writes**: do not unilaterally halt payments or orders if doing so drops transactions; coordinate with product/incident leads.
4. **Project time-to-full** from the storage growth slope, not current percentage alone.
5. **Expand storage safely**, favoring non-destructive, platform-supported paths.
6. **Clean up artifacts outside `dbPath`** only after confirming they are obsolete temporary files or rotated logs allowed by retention policy.
7. **Verify MongoDB health and business data** once headroom is restored.

This does not mean "shut down every write API immediately." A financial system may need to **route requests into a durable queue** or return clear temporary errors rather than reporting success before writes are confirmed.

## 15. Expanding Volumes: Why Is It Usually Safer Than Deleting Data?

If the storage backend supports resizing, **adding capacity** lets MongoDB continue running without deleting documents, indexes, or the oplog.

Remember the multiple layers involved:

```text
Cloud block volume size
        |
        v
Partition / logical volume
        |
        v
Filesystem capacity
        |
        v
MongoDB dbPath available bytes
```

**Increasing the cloud volume size does not always expand `df -h` immediately.** Additional partition, LVM, or filesystem grow steps may be required depending on OS and backend.

### Resizing Safely

- Confirm the exact **volume ID, mount path, and filesystem**.
- Ensure snapshots/backups and a plan exist if required by the backend.
- Follow supported online/offline grow procedures for the filesystem (XFS, ext4, etc.).
- Assess replication/quorum if a restart is required.
- Avoid resizing the root disk by mistake while data resides on another PV.
- Verify quota/IOPS policies after resizing.
- Re-check `df` and live metrics afterward.

Never treat a single `resize2fs` or `xfs_growfs` command as a universal formula for every storage layout. Follow vendor/OS/filesystem procedures and approved change controls.

## 16. Should You Delete Logs to Free Space?

**Only for clearly identified logs outside `dbPath` and within retention rules.**

For instance, rotated historical logs in `/var/log/mongodb/` may be archived or deleted per policy, yet:

- Never delete a log file **still held open by a running process** assuming disk space frees immediately.
- Never delete audit logs under legal hold or active incident investigation.
- Verify logs actually reside on **the same full filesystem**.
- Cleaning logs on a separate filesystem will not fix a full `dbPath`.
- Perform log rotation/truncation through supported mechanisms preserving proper owner and permissions.

### The Goal Is Not "Find the Largest File and Delete It"

A huge file may be a **valid WiredTiger data file**. Those files must be managed via MongoDB operations, never `rm`. Even if backup archives or temporary exports sit next to data, verify whether they are the sole copy or still actively transferring.

## 17. Why Is `deleteMany()` Not an Instant Disk-Full Fix?

In MongoDB:

```javascript
db.events.deleteMany({ createdAt: { $lt: cutoff } });
```

removes logical documents, yet on WiredTiger:

- The storage engine retains pages/data files for **internal reuse**, so `df -h` does not immediately shrink by the bytes deleted.
- Deleting millions of documents also generates heavy **writes, journal traffic, and oplog entries**, slowing storage further during an incident.
- Secondaries must replicate and apply all deletes; if already lagging, this adds heavy pressure.
- Business retention and legal requirements must still be respected.

Therefore, when bytes are nearly exhausted, **never fire a massive `deleteMany` hoping to rescue disk space**. Once data genuinely expires, use planned TTL/retention or throttled batch cleanup with adequate headroom, keeping OS reclamation semantics in mind.

### TTL Is Not an Instant Delete Switch

The TTL monitor runs asynchronously; it makes no guarantee that documents disappear the instant they expire or immediately after creating a TTL index. A large backlog of TTL deletes can also spike I/O and oplog load.

## 18. Why Should `compact` Never Be Used as a Default Firefighting Tool?

MongoDB provides `compact` and version-specific storage reclamation mechanisms. However, `compact` can:

- Read and rewrite large volumes of data, consuming heavy I/O and time.
- Require free space/headroom to operate.
- Impact node availability and performance.
- Carry different semantics and limits across versions and topologies.

If a node is already disk-full or I/O-saturated, running `compact` can **make matters worse** or fail outright.

**Logical order:** restore headroom and availability first; post-incident, evaluate fragmentation, space reuse, collection/index design, and whether compaction or rebuilding is truly warranted. Never equate logical document deletion with immediate filesystem byte reduction.

## 19. Oplog: Why Must You Never Truncate It Arbitrarily?

Replica sets rely on the oplog to replicate operations. Oplog size and retention affect:

- Secondary lag and catch-up viability.
- Change stream resume windows.
- Resync safety after prolonged secondary downtime.
- Volume capacity provisioning.

When disk is full, **manually deleting or shrinking the oplog without a plan** can force secondaries into initial sync, break CDC consumer resume tokens, or plunge the cluster into lengthy recovery.

### What to Do Instead of Deleting the Oplog?

1. Measure lag and oplog window using proper metrics.
2. Identify which members carry write pressure.
3. Expand storage cleanly if the volume is undersized.
4. Curb write surges, batch loads, and retries.
5. Revisit oplog sizing and CDC retention **after the system stabilizes**.

When multiple members are already lagging, never shrink the oplog window purely to save short-term disk space.

## 20. Replica Set: A Full Secondary Differs from a Full Primary

Suppose:

```text
Replica set (3 voting data-bearing members):

node-a  PRIMARY    disk 97%
node-b  SECONDARY  disk 60%
node-c  SECONDARY  disk 65%
```

If the primary is nearly full, two secondaries remain healthy, yet that **does not permit blind restarts or stepdowns**:

- Verify secondaries are healthy and caught up on the oplog.
- Verify current majority/quorum status.
- Check write concern and application failover behavior.
- Decide whether to grow primary storage online or shift load via planned failover.
- Avoid triggering repeated elections while servers are already resource-constrained.

### Full Secondary Case

```text
node-a  PRIMARY    disk 60%
node-b  SECONDARY  disk 99%
node-c  SECONDARY  disk 60%
```

The usual priority is **rescuing `node-b` without disrupting `node-a` or `node-c`**. However, if another member is already down, stopping `node-b` could break majority. Always evaluate the **entire topology** before acting.

### Never Restart All Members Simultaneously

If a node can recover after volume expansion, process one node at a time per runbook and confirm it returns to healthy status before touching another. Restarting the whole replica set at once needlessly destroys availability and quorum.

## 21. When Multiple Members Fill Up Together: Correlated Failure Risk

A more dangerous scenario:

```text
node-a PRIMARY    99%
node-b SECONDARY  99%
node-c SECONDARY  98%
```

Because workloads and data replicate, all three members grow at nearly the same pace. "Just fail over the primary to a secondary" solves nothing if **secondaries are also nearly full**.

Priority actions:

1. Declare an incident and confirm RPO/RTO.
2. Throttle application ingestion and retry storms.
3. Keep members online if still possible; never restart all at once.
4. Determine which volume to resize first to preserve majority.
5. Ensure backing storage provides actual capacity and IOPS headroom.
6. Verify replication and health after each node's resize.
7. Watch the growth slope so disks do not fill again minutes later.

If all members depend on one shared storage failure domain, this is also an **availability architecture gap**, not just a single-node capacity shortage.

## 22. Sharded Clusters: Shards vs. Config Servers

In a sharded MongoDB cluster:

```text
App -> mongos routers
         |
         +--> Shard A replica set
         +--> Shard B replica set
         +--> Shard C replica set
         |
         +--> Config server replica set
```

Know which volume is full:

- **Shard data node**: affects collections/chunks and queries on that shard.
- **Config server node**: holds critical metadata/configuration; outages can impact the entire cluster.
- **`mongos` host**: routers generally hold no collection data like `mongod`; disk pressure there usually comes from logs/OS.

Never treat every host listening on a MongoDB port identically. Resyncing or restarting config servers requires extra caution and strict adherence to topology/version procedures.

### Chunk Migration Is Not a Universal Emergency Fix

Sharding distributes data by shard key and migration rules. Yet when disk is nearly full, chunk migrations:

- Add network and disk I/O.
- Require free capacity on the destination shard.
- Cannot quickly resolve filesystem, inode, or read-only errors.
- May be blocked by cluster state.

Never trigger mass rebalancing or `moveChunk` operations on congested disks without checking headroom and a formal plan.

## 23. Backups Before Any Action?

**Having backups does not mean you can immediately take a new local backup during a disk-full incident.** Starting `mongodump` outputting onto **the same full volume** only worsens the crisis.

Questions to answer:

1. When was the last valid backup taken?
2. What is the maximum acceptable RPO data loss?
3. Is the backup consistent and restore-tested?
4. Are snapshots or managed backups available without writing temporary files onto the full volume?
5. Does the restore target have sufficient disk space and access rights?
6. Must incident evidence be preserved before altering the filesystem or storage?

### Never Blindly Copy a Live `dbPath`

```bash
# DO NOT treat this as a consistent backup of a writing mongod:
cp -r /var/lib/mongodb /backup/mongo-copy
```

Files can be copied at inconsistent points in time out of sync with the journal and checkpoints. Use MongoDB-supported **`mongodump`/snapshot/managed backup** methods tailored to your topology and consistency needs.

### Backups Do Not Replace Headroom

Even with valid backups, protect live data whenever possible; restoring multi-TiB datasets takes time, may exceed RTO, and complicates reconciling newly arrived writes.

## 24. What Is Memory Pressure?

MongoDB and the OS share RAM across multiple consumers:

```text
Host RAM / cgroup limit
    |
    +--> MongoDB process
    |      |
    |      +--> WiredTiger internal cache
    |      +--> Query execution
    |      +--> Connections / threads / stacks
    |      +--> Metadata / allocator overhead
    |
    +--> OS filesystem page cache
    +--> Kernel allocations
    +--> Other services / agents
```

**WiredTiger cache size is not a cap on `mongod` total RAM.** Even with a 2 GiB cache, the process requires additional RAM for network buffers, aggregations, connections, and internal structures.

Memory pressure arises when working sets, cache, query buffers, and co-located consumers exceed available RAM or limits, causing:

- Elevated cache evictions and disk page reads.
- Swap thrashing or major page faults.
- High latency.
- OOM kills/crashes.
- Continuous container restarts.

### "Low Free RAM" Does Not Automatically Mean OOM

Linux uses spare RAM for filesystem page cache. Inspect `MemAvailable`, swap pressure, and OOM logs alongside workload metrics rather than reading the `free` column alone. A host with low `free` but ample `MemAvailable` and zero eviction/OOM pressure may be operating normally.

## 25. Quickly Reading Memory Metrics on Linux

Read-only commands:

```bash
free -h
vmstat 1 5
ps -eo pid,user,rss,vsz,%mem,%cpu,cmd | grep '[m]ongod'

# When authorized to read kernel logs:
journalctl -k --no-pager -n 100
```

Meaning:

- `free -h`: total, used, free, available memory, and swap.
- `vmstat`: VM activity, swap in/out, and I/O over the sample window.
- `ps`: RSS/process memory and relative CPU usage.
- Kernel logs: may show `Out of memory` or killed-process records.

**RSS is not the full system footprint.** Cgroup memory accounting can include filesystem page cache and kernel memory depending on cgroup version. For containers, examine both **container and host** metrics to avoid misreading.

### Is Swap Always Forbidden?

Swap and kernel tuning guidance depend on MongoDB version, OS, and deployment type. Heavy swapping destroys latency; yet disabling swap in tight-RAM environments can trigger earlier OOM kills. Proper sizing and production notes matter more than blanket commands across all systems.

## 26. WiredTiger Cache and Eviction Pressure

WiredTiger uses an internal cache to hold data/index pages and track dirty pages. When the working set outgrows cache or dirty content piles up:

```text
High write rate / queries
            |
            v
WiredTiger cache pressure
            |
            v
Eviction work increases
            |
            +--> More disk reads
            +--> Checkpoints/flushes compete for I/O
            +--> Application operations slow down
```

Metrics and field names depend on MongoDB version and storage engine:

```javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson(s.wiredTiger?.cache);
printjson(s.mem);
printjson(s.connections);
```

These are `mongosh` observation commands requiring appropriate monitoring roles. Do not assume every server or tier exposes identical fields or permits access to all metrics.

### Do Not Immediately Raise WiredTiger Cache When Queries Slow Down

If the constraint is a **low cgroup memory limit**, raising cache triggers OOM sooner. If the constraint is **full disk**, larger cache frees zero disk bytes. If the constraint is **missing indexes**, queries perform huge scans and thrash cache—fix queries/indexes after stabilizing.

Recommendation: inspect host/container memory limits, memory pressure, cache/evictions, process RSS, and workload before changing `storage.wiredTiger.engineConfig.cacheSizeGB`.

## 27. When `mongod` Is `OOMKilled`

In Kubernetes, a Pod may restart with:

```text
Last State: Terminated
Reason: OOMKilled
Exit Code: 137
```

Exit code 137 indicates SIGKILL, yet **137 alone does not prove OOM**; verify `Reason`, kernel/container events, and limits.

Common causes:

- Container memory limit too small for workload.
- WiredTiger cache sized improperly for the cgroup.
- Aggregation, `$sort`, or `$group` queries consuming large RAM.
- Connection or request surges.
- Co-located workloads competing for node RAM.
- Memory leaks or unexpected allocations in apps/sidecars.
- Page cache/cgroup accounting amplifying memory pressure.

### Avoid Restart Loops

Automatic restarts will not solve the root cause when the same workload and memory limit repeat. Every `mongod` restart can also trigger recovery and disk reads while storage is already strained.

Priority actions:

1. Confirm genuine `OOMKilled`.
2. Curb spike-inducing workloads.
3. Review resource requests/limits, WiredTiger cache, and host memory.
4. Expand RAM/limits cleanly or lower cache **based on analysis**, never blindly.
5. Verify the PVC is persistent and retains disk headroom.
6. Monitor recovery and query latency.

## 28. Docker: External Memory Cap vs. In-Process Memory

Inspect container configuration:

```bash
docker inspect mongo-lab
docker stats mongo-lab
docker logs --tail 100 mongo-lab
```

Check:

- Container image/version.
- `HostConfig.Memory` or equivalent cap.
- Cgroup CPU/memory policies.
- Volume mounts and actual `dbPath`.
- Exit status and OOM flags.

Setting a 2 GiB container memory limit **does not automatically guarantee** every MongoDB/runtime version selects the optimal WiredTiger cache size; defaults depend on runtime environment and server version. Never copy bare-metal "cache = X% of RAM" tuning into containers without checking cgroup awareness in your version.

### Volumes and OOM

If a container gets OOM-killed while mounted on a proper named/persistent volume, the storage engine can recover from durable state upon restart. If using an ephemeral writable layer and the container is recreated, data loss risk rises sharply. **Memory fixes never replace storage durability planning.**

## 29. Kubernetes: Observing Pods, PVCs, and Nodes

Read-only commands:

```bash
kubectl get pods -n mongodb
kubectl describe pod mongo-0 -n mongodb
kubectl logs mongo-0 -n mongodb --previous
kubectl top pod -n mongodb

kubectl get pvc -n mongodb
kubectl describe pvc mongo-data-mongo-0 -n mongodb
```

Pod and PVC names are examples; retrieve actual names from `kubectl get`. `kubectl top` requires the metrics server and only shows a point-in-time snapshot.

### Distinguishing Failure Signals

| Kubernetes signal | Likely meaning | Next check |
| --- | --- | --- |
| `OOMKilled` | Hit memory limit | cgroup, requests/limits, cache/query load |
| `Evicted` | Node pressure or eviction policy | Node conditions/events, ephemeral storage |
| `CrashLoopBackOff` | Repeated process crash | `--previous` logs + last termination state |
| PVC `Pending` | CSI, quota, storage class, or topology | `describe pvc`, cluster events |
| Volume attach error | Zone/attachment conflict | CSI, node scheduling, volume status |
| `No space left on device` | Filesystem, PVC, or ephemeral storage | Identify true path and mount |
| Pod `Ready` yet DB slow | Disk I/O, cache, or heavy queries | MongoDB metrics and app latency |

### Expanding a PVC Is Not Always Instant

PVC expansion depends on StorageClass/CSI support, filesystem resizing, and topology. Sometimes expansion completes online; other times it requires a Pod restart or explicit filesystem steps. Never patch PVC size and assume the incident is over without verifying available bytes inside the Pod.

### Never Delete a PVC to "Reset Errors"

Deleting a PVC can permanently destroy the underlying data volume depending on PV reclaim policy and StorageClass. **Never run `kubectl delete pvc` as quick cleanup** while MongoDB holds data you need to keep.

## 30. Atlas: Operators Do Not Touch Internal Node Files

In MongoDB Atlas-managed deployments, operators generally have no SSH, `chown`, or journal-deletion access on managed nodes. Proper actions include:

- Review Atlas metrics and alerts: storage usage, growth rate, CPU, memory/working set, IOPS, replication lag.
- Check cluster tier, storage size, and tier limits/features.
- Check whether storage/compute autoscaling is supported and enabled.
- Scale capacity or cluster tier via managed service controls when needed.
- Reduce ingestion, bulk migrations, heavy aggregations, or application retries.
- Review backup and restore options.
- Open a support case if platform/storage health looks abnormal or scaling lags behind demand.

Never assume Atlas autoscales storage automatically **on every tier**, or scales instantaneously past thresholds. Verify your deployment's exact configuration and limits.

### Do Not Treat Atlas Issues with `db.repairDatabase()`

Self-managed storage file edits or repair workflows do not serve as a general remedy on Atlas-managed nodes. Use managed controls and support channels.

## 31. Java Driver: What Does the Application See When Resources Run Out?

Typical symptoms:

- `MongoSocketTimeoutException`.
- `MongoTimeoutException` when server selection fails within timeout.
- `MongoWriteException` for specific write failures.
- `MongoWriteConcernException` or write concern errors.
- Command errors tied to storage/availability.
- Connection pool saturation and wait-queue timeouts.
- High latency even when APIs see no single consistent error code.

Exact exceptions vary by driver and server version, so **no single exception uniquely denotes "disk full" or "OOM."**

### Why Is a Java Stack Trace Not Enough?

An OOM-killed MongoDB server causes clients to see connection resets—a **network** symptom whose root cause is memory. Saturated disk I/O causes client timeouts; raising socket timeouts just makes threads wait longer without fixing disk latency.

During an incident, correlate:

1. Driver/server error codes and error labels.
2. Application request rate, retries, and pool utilization.
3. MongoDB server logs and metrics.
4. Host, PVC, and cloud storage metrics.
5. Replica set topology and health.

## 32. Retry Storms Worsen Incidents

A dangerous feedback loop:

```text
MongoDB write latency spikes
        |
        v
API timeouts
        |
        v
5 instances x 5 retries per request
        |
        v
Write traffic multiplies several-fold
        |
        v
Heavier pressure on journal/oplog/cache/CPU/disk
        |
        v
More timeouts
```

**Never retry infinitely** and never let all service instances retry immediately in lockstep.

Desired application behavior:

- Exponential backoff + jitter with bounded attempts and deadlines.
- Circuit breakers/load shedding for non-essential endpoints.
- Durable queues for deferrable work, checking queue capacity and retention.
- Stable idempotency keys for retryable writes.
- Never automatically retry non-idempotent side effects (payments/emails).
- Prioritize critical writes per business policy.
- Treat rate-limiting and rejections as protective signals rather than errors to "hide."

### Driver Retryable Writes Differ from Outer Retries

The Java Driver supports retryable reads/writes under qualifying conditions, yet they do not replace application-level idempotency. If services also implement outer retries, account for **total combined attempts** to avoid retry amplification.

## 33. Java Example: Reacting Safely to Ambiguous Write Outcomes

Suppose an application persists a request carrying a unique business ID:

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class RequestWriter {
    public static Document register(
            MongoCollection<Document> collection,
            String requestId,
            String payloadHash) {

        Document doc = new Document("_id", requestId)
            .append("payloadHash", payloadHash)
            .append("status", "RECEIVED");

        try {
            collection.insertOne(doc);
        } catch (MongoException ex) {
            // Do not immediately conclude the write failed to apply.
            Document existing = collection.find(
                Filters.eq("_id", requestId)).first();

            if (existing != null &&
                payloadHash.equals(
                    existing.getString("payloadHash"))) {
                return existing; // A form of idempotent replay.
            }

            // Outcome still unknown or conflicting payload.
            throw ex;
        }

        Document saved = collection.find(
            Filters.eq("_id", requestId)).first();
        if (saved == null) {
            throw new IllegalStateException(
                "Write acknowledged but record not readable");
        }
        return saved;
    }
}
```

This is a **conceptual illustration**, not a complete production error handler:

- Requires a unique `_id`/business key and an acknowledged write concern.
- The follow-up read after an error may also fail if the cluster has not recovered.
- Reading from a secondary can hit lag; choose read preference and read concern carefully.
- A duplicate key with a mismatched payload **must not be treated as success**.
- Never execute external side effects inside retryable blocks lacking idempotency.
- Production needs structured error classification, deadlines, fallbacks, and formal reconciliation workflows.

Key point: **when an outcome is ambiguous, never mint a new request ID or blindly repeat a payment**.

## 34. Temporary Load Shedding Does Not Mean Weakening Write Durability

A hasty workaround is dropping `writeConcern` from `majority` to `w:0` so apps "wait less."

That does not make the disk healthier and can:

- Deprive clients of write success/error confirmation.
- Increase uncertainty over whether writes applied.
- Violate RPO and durability contracts.
- Make business transactions appear "successful" with zero acknowledgment.

**Never lower write concern or disable journaling merely to ride out a resource crunch** without formal risk sign-off. Safe mitigation reduces non-essential throughput or expands capacity/IOPS/RAM.

### Throttling Must Respect API Contracts

When shedding load temporarily, return explicit status codes (e.g., 503/429 per contract) rather than returning 200 before writes finish. If enqueueing requests, return accepted only after the queue has **durably persisted** them with appropriate idempotency and expiry.

## 35. Do Not Restart `mongod` as Your First Reflex

A restart helps when:

- Mount, permission, or config faults have already been fixed.
- Newly added resources require a restart for the runtime to recognize them.
- A controlled restart is needed per runbook with quorum and backups verified.

However, restarting **never frees disk space on its own** and can:

- Interrupt primary availability during elections.
- Trigger crash recovery, spiking disk reads/writes.
- Wipe in-memory metrics and diagnostics.
- Trigger repeated OOM loops if memory limits remain unchanged.
- Cause the database to initialize on an unexpected path if a mount is wrong.

**Before restarting:** inspect node role, replica health, backups, data path, free disk, and root cause. In replica sets, restart one member at a time per supported procedures.

## 36. What Is `mongod --repair` and Why Is It Not an Emergency Reset Button?

`--repair` exists for specialized self-managed recovery scenarios, yet it is **never a first-line fix** for simple disk or memory exhaustion. It consumes heavy resources, has storage/version constraints, and risks data loss under severe corruption.

If logs only report `ENOSPC`, never reflexively run `--repair`. Instead:

1. Verify whether actual corruption exists vs. simple resource/mount exhaustion.
2. Collect evidence and check backups.
3. If the replica set has healthy secondaries, consider supported resync/replacement procedures.
4. Consult MongoDB documentation for your exact server version.
5. Ensure ample disk and RAM before any recovery run.

**Never manually delete files inside `dbPath` before or after repair.** Any file-level intervention demands a dedicated runbook and approval.

## 37. Procedure to Rescue a Disk-Full Secondary

Scenario:

```text
Replica set:
  node-a primary healthy
  node-b secondary disk full
  node-c secondary healthy
```

Conceptual runbook:

1. Confirm `node-a` and `node-c` remain healthy and hold majority.
2. Check lag and oplog window for `node-b`.
3. Confirm `node-b`'s data path, volume ID, permissions, and what filled its disk.
4. If possible, **expand the volume** on `node-b` without touching data files.
5. If `node-b` requires a restart, follow single-member procedures while verifying cluster state.
6. Monitor `node-b`'s recovery, replication catch-up, and log errors.
7. Confirm `node-b` returns to `SECONDARY` and lag stabilizes.
8. Verify app, quorum, and backup alerts return to normal.

If `node-b` has fallen outside the oplog window, initial sync/resync may be needed. That consumes **heavy I/O and disk and replaces local data**; never delete `dbPath` to "resync" without an approved plan and a healthy sync source.

## 38. Procedure When the Primary Is Nearly Full

More dangerous because the primary serves live writes:

1. Coordinate incident lead, app owners, and DBAs.
2. Assess majority availability, secondary lag, and critical business flows.
3. Halt non-essential ingestion and retries immediately if exhaustion is rapid.
4. Grow primary storage/IOPS online if a safe path exists.
5. If failover/stepdown is needed, do so only when healthy secondaries qualify and change control approves.
6. Avoid an **election loop** caused by repeated stepdowns or resource-starved peers.
7. Verify the new/retained primary, write concern, and application write outcomes.
8. Reconcile business requests that suffered timeouts or ambiguous results.

Never run `rs.stepDown()` out of habit without inspecting topology first. A secondary could be lagging or equally full; failing over to an unhealthy peer will not heal the cluster.

## 39. Recovery Order When Both Disk and RAM Are Exhausted

A combined crisis:

```text
Low free disk
Rising WiredTiger dirty pages / eviction
OS memory pressure
Application retry storm
```

Sensible sequence:

1. **Stop adding load**: cap non-essential ingestion and retries.
2. **Protect data integrity**: never delete files, indexes, journal, or oplog.
3. **Identify which limit is hitting hard failure**: disk bytes/inodes, read-only mount, cgroup OOM, or IOPS ceiling.
4. **Raise headroom on the hard blocker**: expand capacity/volume first if disk cannot write; expand RAM/limits when genuine OOM hits.
5. **Recover service one node at a time**, avoiding restart storms and retry surges.
6. **Confirm improvement**: disk latency, cache eviction, process RSS, replica health, API success.
7. Tune cache, indexes, queries, and retention only after stabilization.

There is no rigid rule saying "always add RAM first" or "always expand disk first." **Prioritize whichever hard ceiling threatens durability or availability right now** using the least destructive intervention.

## 40. Disk Full Because Backups/Exports Share the Filesystem

Suppose:

```text
/var/lib/mongodb          90 GiB data
/var/lib/mongodb/backups  20 GiB temporary dump
Filesystem               100 GiB
```

This is a poor layout: backup archives share the data filesystem. During an incident, never hastily delete the dump if it is the sole copy or mid-upload. Instead:

1. Identify which job owns the backup file and its completion state.
2. Verify whether a validated copy exists on another destination.
3. If it is **temporary non-data-file artifacts** eligible for deletion under policy, clean up carefully.
4. Relocate backup destinations off the data volume permanently.
5. Verify backup job configuration and disk headroom before the next run.

A directory nested **under `dbPath`** yet outside WiredTiger files is still risky if handled carelessly. Design separate backup storage paths from day one.

## 41. Incidents Triggered by Index Builds or Migrations

Deploying multiple new indexes on a large collection can:

- Spike disk consumption.
- Drive heavy CPU, RAM, and I/O load.
- Contend with normal writes and queries.
- Cause secondary lag or elevated write latency depending on workload.

### Investigation

1. Check recent schema migrations and deployments.
2. Inspect index sizes and active index build status via supported metrics/commands.
3. Check for concurrent heavy operations.
4. Pause **upcoming jobs** where possible without recklessly aborting safe active state.
5. Scale capacity/IOPS or schedule index builds in low-traffic maintenance windows.

Never blindly run `killOp` or drop indexes in production. Aborting a running index build carries version-specific semantics and side effects; coordinate with DBAs and backup/recovery plans.

## 42. Incidents Triggered by Memory-Heavy Queries/Aggregations

A query like:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$customerId", total: { $sum: "$amount" } } },
  { $sort: { total: -1 } }
]);
```

can demand substantial RAM depending on document counts, group cardinality, and indexes.

### When the Server Is Near OOM

Do not treat `allowDiskUse:true` as an automatic cure-all:

- It lets certain aggregation stages spill temporary files to disk.
- If **disk is also nearly full or I/O-saturated**, spilling to disk worsens the crisis.
- Some operators impose separate constraints and memory caps.

Priorities:

1. Identify the endpoint or batch job emitting the heavy query.
2. Pause or throttle it if non-critical.
3. Inspect query plans and indexes once the server has breathing room.
4. Consider pre-aggregation, pagination, projections, `$limit`, or data-model adjustments.
5. Measure cache, memory, disk spill, and storage headroom before enabling disk spill.

## 43. When the Java App Runs Out of RAM—Not `mongod`

A common application bug:

```text
MongoDB server healthy
    |
    v
Java service loads 3 million documents into a List
    |
    v
JVM heap OOM
    |
    v
API crash / retry / reconnect
```

This is a **client-side failure**, not WiredTiger cache exhaustion.

In Java:

- Use cursors/streaming or bounded pagination.
- Never call `into(new ArrayList<>())` on unbounded result sets.
- Use projections to shrink payload bytes and object churn.
- Size batch sizes and concurrency to your heap budget.
- Close cursors and client resources properly in lifecycle hooks.
- Monitor JVM heap/GC, thread pools, and connection pools.

Adding RAM to `mongod` will never cure a JVM heap OOM. Triage must identify **which process** ran out of memory.

## 44. Connection Pool Exhaustion and Retry Backpressure

An exhausted driver connection pool mimics a slow server:

```text
API requests surge
    |
    v
Threads block waiting for MongoDB connections
    |
    v
Wait queue timeouts
    |
    v
Retries / fan-out increase
```

Root causes may be slow MongoDB responses from disk I/O, or application-side issues like creating multiple clients, cursor leaks, fan-out storms, or oversized thread pools.

### Diagnosis

- Inspect driver pool utilization and wait-queue checkout times.
- Inspect active server operations using authorized monitoring privileges.
- Measure request rates, queue depths, and latencies.
- Distinguish **server selection timeout**, **socket timeout**, and **pool wait timeout**.
- Throttle concurrency when the server lacks throughput instead of merely raising max pool size.

Enlarging the connection pool does not give the server extra IOPS or RAM; excessive open connections consume more RAM and file descriptors.

## 45. Checking MongoDB Metrics While the Server Still Responds

With `mongosh` and an authorized monitoring role:

```javascript
const status = db.adminCommand({ serverStatus: 1 });

printjson(status.uptime);
printjson(status.connections);
printjson(status.mem);
printjson(status.wiredTiger?.cache);

const info = db.getSiblingDB("appdb").stats();
printjson({
  dataSize: info.dataSize,
  storageSize: info.storageSize,
  indexSize: info.indexSize
});
```

In a replica set:

```javascript
rs.status();
```

Or:

```javascript
db.adminCommand({ replSetGetStatus: 1 });
```

### Caution When Querying Metrics During an Incident

- Some commands do not apply on `mongos` or fail when members are unhealthy.
- Field names and availability depend on MongoDB version.
- `serverStatus` returns a huge document; extract only needed sections during incidents.
- `db.stats()` reports logical/storage figures rather than replacing `df` for free filesystem bytes.
- Read secondary lag and majority status against the right topology and timestamp.
- Never enable full profiling or launch collection scans when the server is already overloaded.

## 46. Interpreting `db.stats()` Alongside `df -h`

Suppose:

```text
db.stats().dataSize    = 50 GiB
db.stats().storageSize = 28 GiB
db.stats().indexSize   = 8 GiB
df used                = 70 GiB
```

These numbers are not contradictory:

- `dataSize` reflects logical uncompressed document size per server semantics.
- `storageSize` reflects storage allocated to collections by the engine.
- `indexSize` reflects index storage.
- The filesystem also holds the journal, oplog, logs, backups/exports, metadata, snapshots, and files outside database stats.
- Compression and internal space reuse separate logical from physical sizes.

**Never treat `dataSize + indexSize` as total host disk usage.** During disk-full root-cause analysis, filesystem/volume metrics measure actual available space, while MongoDB stats explain internal data growth.

## 47. Post-Recovery Verification: What Must You Confirm?

Seeing `mongod` running again **is never sufficient**. Verify across all layers:

| Layer | Confirmation |
| --- | --- |
| Filesystem | Bytes/inodes have healthy headroom, correct mount, not read-only |
| Disk | Latency, queue depth, and IOPS stabilized |
| Memory | No OOM loops; RSS, cache, and evictions normal |
| MongoDB process | No recurring startup/recovery errors |
| Replica set | Healthy members, primary, majority intact, lag shrinking |
| Sharding | Shards, config servers, and routers healthy; normal routing |
| Application | Business reads and writes succeeding |
| Durability | Intended write concern preserved, not silently weakened |
| Idempotency | No duplicate requests or payments generated by retries |
| Backups | Backup jobs running cleanly and restore paths valid |
| Alerts | Incident alerts genuinely cleared |

### Business Data Verification Tests

For example:

- Read an existing pre-incident order.
- Write a safe synthetic record via an authorized test workflow/fixture and confirm acknowledgment.
- Verify read-after-write consistency per contract.
- Reconcile all timed-out or unknown-outcome requests.
- Verify Change Streams/CDC consumers if present.

Never run destructive tests or leave junk test rows in live production tables without explicit policy and cleanup.

## 48. Can Acknowledged Data Be Lost?

This depends on:

- `writeConcern` (`w:1`, `majority`, `j:true` under version semantics).
- Replica set topology and majority health.
- Storage backend durability guarantees.
- Failover timing and rollback scenarios.
- Transaction and application behavior.

**Never infer from a "client timeout" that a write definitely failed to apply.** Nor infer from a `w:1` acknowledgment that a write survives every failover. During resource outages, preserve RPO/business contracts and build idempotent reconciliation for ambiguous operations.

### Retry Reconciliation

A practical business handling matrix:

| Client outcome | Safer action |
| --- | --- |
| Write acknowledged | Follow ACK/transaction semantics, advance state |
| Duplicate key matching idempotency key | Read existing record and compare payload/result |
| Timeout with unknown outcome | Look up by stable ID; never mint a new ID immediately |
| Write concern timeout | Write may already be applied; reconcile before retrying |
| Authorization/validation error | Fix permissions/schema; never retry blindly |
| Server unavailable | Cap attempts, apply backoff, enqueue/reject per policy |

## 49. Prioritize by RPO/RTO, Not Disk Percentage Alone

**RPO (Recovery Point Objective)** is the maximum acceptable data loss measured in time/state. **RTO (Recovery Time Objective)** is the target time within which service must recover.

Example:

```text
Application A:
  RPO ~ 0 for confirmed payments
  RTO 15 minutes

Application B:
  Rerunnable analytics jobs
  RPO several hours
  RTO several hours
```

When both contend for MongoDB resources, prioritize resources for A and throttle or pause B via approved procedures.

**Never sacrifice acknowledged data solely to make latency graphs look prettier.** If the incident forces pausing writes, communicate status clearly upstream and rely on durable replay mechanisms so requests are not silently lost.

## 50. Sizing Headroom from Growth Rate

Knowing disk is at 85% does not tell you how much time remains. Measure:

```text
Available capacity = A GiB
Net growth rate    = G GiB/hour

Projected time-to-full ≈ A / G
  (assuming G > 0 and steady trend)
```

Example:

```text
Volume has 80 GiB free
Net growth rate is 20 GiB/hour
=> ~4 hours under linear assumption
```

This is an **operational estimate**, not a guaranteed forecast:

- Bulk imports can spike suddenly.
- Index builds grow disk unevenly.
- Backups, compaction, and recovery need scratch headroom.
- TTL/deletes do not immediately return bytes to the OS.
- Storage autoscaling has provisioning lag and caps.

Alert on **time-to-full** compared against storage provisioning time and RTO, not just static percentage thresholds like 90%.

### Disk Performance Headroom

Even with spare GiB, leave performance headroom for failovers, backups, initial syncs, and traffic peaks. A volume hitting its IOPS/throughput cap triggers outages well before `df` hits 100%.

## 51. Recommended Alerting Signals

| Category | Signal | Purpose |
| --- | --- | --- |
| Capacity | Free bytes/inodes, projected time-to-full | Early warning before `ENOSPC` |
| Storage | I/O latency, queue depth, IOPS/throughput | Detect saturation |
| Filesystem | Read-only remount, kernel I/O errors | Spot backend corruption/failure |
| Memory | RSS, cgroup usage/limit, OOM events | Prevent crash loops |
| WiredTiger | Cache dirty/eviction/reads, checkpoint timing | Spot internal pressure |
| Process | Restart count, crash logs | Diagnose availability |
| Replica set | Member states, lag, majority, oplog window | Safeguard consistency/availability |
| Workload | Write rate, query latency, retry rate | Pinpoint pressure sources |
| App | Pool wait, timeouts, 5xx, queue depth | Measure user impact |
| Backups | Last successful backup, restore drills | Ensure recoverability |
| Change streams | Resume lag/history-loss errors | Protect CDC pipelines |
| Capacity changes | Autoscale failures, PVC resize events | Confirm scaling actually took effect |

No universal numeric threshold fits every deployment. Tune alerts to **baselines, growth rate, response lead time, topology, and criticality**.

## 52. Emergency Do's and Don'ts Table

| Symptom | Do first | Avoid |
| --- | --- | --- |
| `df` near 100% | Curb ingestion, verify mount/volume, add capacity | Deleting WiredTiger/journal files |
| `df -i` full | Check inodes/quotas, locate small-file generators | Only adding GiB blindly |
| Read-only filesystem | Check kernel/storage errors, escalate | Forcing read-write without investigation |
| High disk latency | Check IOPS/queue/cloud volume limits | Blindly adding vCPUs |
| Secondary disk full | Check quorum/lag, resize that member | Restarting the entire replica set |
| Primary disk full | Protect majority, throttle writes, resize | Blindly stepping down |
| `OOMKilled` | Check cgroup/cache/RSS/workload | Endless restart loops |
| Low free Linux RAM | Inspect `MemAvailable`/swap/evictions | Declaring OOM from `free` alone |
| Aggregation spill | Curb query load, check disk headroom | Enabling disk spill unconditionally |
| Huge TTL/delete backlog | Plan throttled batch cleanup post-stabilization | Emergency multi-million-row `deleteMany` |
| Timeout errors | Preserve idempotency keys, reconcile | Unlimited retries with new IDs |
| Atlas capacity alert | Check scaling, metrics, and support | Trying to SSH/delete node files |
| PVC nearly full | Check CSI expansion support | Deleting PVC to "reset" |
| Index build pressure | Defer upcoming jobs, plan capacity | Dropping indexes without review |

## 53. Practice Exercises with Answers

### Exercise 1. Disk Full—First Command?

Primary MongoDB reports filesystem 100% full. Someone suggests `rm -rf /var/lib/mongodb/journal` to free space. Should you do it?

**Answer:** No. The journal is internal state required for durability and crash recovery. Reduce write pressure, verify mounts/volumes, and expand storage safely.

### Exercise 2. Free Space Exists, Yet `ENOSPC` Happens

`df -h` shows 20 GiB free, yet creating new files fails. What do you check next?

**Answer:** `df -i`, filesystem quotas, read-only remounts, backing storage/pool limits, and mount paths—not bytes alone.

### Exercise 3. Large Disk, Slow Queries

A volume has 60% free space, yet I/O latency spikes sharply. Will growing capacity fix it?

**Answer:** Not necessarily. The volume may be hitting IOPS/throughput caps or deep queues; measure storage performance and cloud volume tier settings.

### Exercise 4. Wrong Mount

After a reboot, `/var/lib/mongodb` sits on the root filesystem because the data disk failed to mount. Should `mongod` keep writing?

**Answer:** No, not before verifying the data path. Restore the proper mount, verify volume ID, and assess any data mistakenly written.

### Exercise 5. Bulk Deleting Documents

A DBA runs `deleteMany()` on millions of docs to rescue a full filesystem. Why is that dangerous?

**Answer:** Deletes generate writes and oplog load without immediately returning OS bytes, worsening I/O pressure. Address headroom and planned retention instead.

### Exercise 6. TTL

Right after creating a TTL index, do all expired docs vanish immediately and drop `df` usage?

**Answer:** No. TTL runs asynchronously, and WiredTiger may retain freed space internally for reuse rather than returning it to the OS immediately.

### Exercise 7. Compact

A node sits at 99% disk with saturated I/O. Should you run `compact` to shrink files?

**Answer:** Do not use it as default emergency relief. Compaction demands extra space and I/O, making overload worse. Restore headroom first.

### Exercise 8. Oplog

A secondary lags by 20 minutes; an operator proposes shrinking the oplog drastically to save space. What is the risk?

**Answer:** Shrinking the oplog window can prevent the secondary from catching up and cause CDC consumers to lose resume history, forcing an initial sync or rebootstrap.

### Exercise 9. Quorum

In a 3-member replica set, one secondary is already offline and the primary is nearly full. Should you shut down the primary immediately to "rest" it?

**Answer:** Very dangerous if doing so breaks majority. Verify topology, shed load, and take quorum-preserving recovery steps.

### Exercise 10. Primary vs. Secondary

Three-node replica set: primary healthy, one secondary full, other secondary healthy. How should you proceed?

**Answer:** Focus on recovering the full secondary while watching lag and oplog window; never restart the whole cluster.

### Exercise 11. Atlas

An Atlas cluster fires a disk capacity alert. Should you try to SSH into nodes to delete WiredTiger files?

**Answer:** No. Use Atlas metrics, scaling controls, backups, and support while reducing workload; managed nodes are never operated via manual internal file deletion.

### Exercise 12. `OOMKilled`

Kubernetes Pod last state is `OOMKilled` with a 2 GiB memory limit. Is raising `cacheSizeGB` to 4 GiB a good fix?

**Answer:** No; it will worsen OOM failures. Review the cgroup memory cap, WiredTiger cache sizing, RSS, and workload first.

### Exercise 13. Linux Free Memory

Linux reports `free` RAM near 0 while `MemAvailable` is large, with no swap or OOM events. Is that proof of a memory incident?

**Answer:** Not by itself. Linux caches files in unused RAM; inspect memory pressure, evictions, RSS, and latency.

### Exercise 14. Restart Loop

A MongoDB container gets `OOMKilled` and restarts every minute. Will simply raising application retries help?

**Answer:** No; a retry storm worsens load. Curb traffic, fix memory/cgroup/cache sizing, and recover cleanly.

### Exercise 15. App OOM

MongoDB is healthy, yet the Java API runs `find().into(new ArrayList<>())` over millions of docs and hits JVM OOM. Root cause?

**Answer:** Unbounded client-side materialization. Use cursors, projections, and bounded pagination rather than expanding WiredTiger cache.

### Exercise 16. Aggregation

The server faces memory pressure and disk is also nearly full. Is enabling `allowDiskUse:true` across all aggregations safe?

**Answer:** No. Disk spill adds storage consumption and I/O pressure. Curb query load, tune indexes/pipelines post-stabilization, and verify disk headroom.

### Exercise 17. Timeout

A client hits a write timeout, immediately generates a fresh ID, and re-inserts the same payment request. What is the risk?

**Answer:** The first write may have succeeded, creating duplicate business operations. Reuse stable idempotency keys and reconcile.

### Exercise 18. Write Concern

To cut latency while disk is busy, a team switches `w:majority` to `w:0`. Why is that reckless?

**Answer:** It sacrifices acknowledgment and weakens RPO/durability without fixing I/O, leaving clients blind to whether operations succeeded.

### Exercise 19. Backing Up to the Same Disk

`mongodump --out` writes onto the nearly full data volume. Does that help recover safely?

**Answer:** It can fill the disk even faster; backups require a dedicated destination and consistent process that does not compound volume pressure.

### Exercise 20. Read-Only Filesystem

A filesystem remounts `ro` after I/O errors. Someone tries `chmod 777`. Right or wrong?

**Answer:** Wrong. Read-only storage/hardware faults are unrelated to file permissions. Investigate storage backend, kernel logs, and filesystem per vendor guidance.

### Exercise 21. Cloud Resize

A cloud volume was grown from 100 to 200 GiB, yet `df -h` still reads 100 GiB. Is MongoDB broken?

**Answer:** No. The partition/LVM/filesystem layer likely has not been grown yet; verify volume, partition, and supported grow procedures.

### Exercise 22. PVC

A Kubernetes StatefulSet uses PVCs. An operator suggests `kubectl delete pvc` to provision a fresh volume and stop crashes. Risk?

**Answer:** Can permanently destroy data depending on PV reclaim policy; never use PVC deletion as a reset without verified backups and recovery plans.

### Exercise 23. Performance

After adding RAM to `mongod`, queries remain slow with deep disk I/O queues. What should you inspect?

**Answer:** IOPS/throughput bottlenecks, query plans/indexes, and workload volume; adding RAM alone does not raise raw disk throughput.

### Exercise 24. Full Across the Replica Set

All three members are nearly full. Should you step down the primary since either secondary can take over?

**Answer:** Not by default. Failing over to an equally full node saves no space and risks election churn. Curb ingestion and add headroom systematically.

### Exercise 25. Time-to-Full

A volume has 40 GiB left with 10 GiB/h net growth. Linearly, how long until full?

**Answer:** Roughly 4 hours at constant growth. Leave margin for index builds, backups, and intervention lead time; treat linear estimates carefully.

### Exercise 26. p99 and OOM

Free memory is low, p99 is high, yet zero OOM events occurred and disk latency is extreme. Can you conclude RAM exhaustion?

**Answer:** Not conclusively. The root cause may be disk saturation or bad queries; check cache/evictions/RSS/OS pressure together.

### Exercise 27. Logs

A log file was removed with `rm`, yet disk usage did not drop. Why?

**Answer:** A running process still holds the deleted file descriptor open. Check for deleted-but-open files and use safe log rotation/reopen rather than blindly restarting the primary.

### Exercise 28. Incident Closure

After a restart, `ping` returns 1. Can you close the incident immediately?

**Answer:** No. Verify mounts/capacity, latency, memory, replica health, business reads/writes, and any previously timed-out requests.

### Exercise 29. Sharded Cluster

A config server member's disk is full while shard data nodes have ample room. Can you ignore it because application data lives on shards?

**Answer:** No. The config server replica set stores critical cluster metadata; an outage affects cluster operations and availability. Follow a topology-specific runbook.

### Exercise 30. Least Destructive Action

Two options: (A) expand the verified data volume at its proper mount via supported steps; (B) delete unfamiliar WiredTiger files. Which do you choose?

**Answer:** Prioritize A alongside backup/rollback checks and quorum verification. Option B risks corruption and data loss.

## 54. On-Call Operator Checklist

### Triage

- [ ] Confirm environment, server version, and topology.
- [ ] Verify member roles and majority before any restart or stepdown.
- [ ] Record incident timestamp, error samples, and recent changes.
- [ ] Verify actual `dbPath`, mount point, and PV/volume ID.
- [ ] Measure bytes, inodes, quotas, read-only state, and disk latency.
- [ ] Measure RSS/cgroup memory, OOM events, and WiredTiger cache pressure.
- [ ] Separate `mongod` OOM from JVM/application OOM.
- [ ] Check backup/recovery options and RPO/RTO targets.

### Damage Control

- [ ] Pause non-essential ingestion, index builds, and analytics jobs.
- [ ] Curb uncontrolled retries; apply backoff and jitter.
- [ ] Preserve business idempotency keys and write acknowledgment contracts.
- [ ] Never delete journal, oplog, or WiredTiger data files.
- [ ] Never reflexively delete PVCs/volumes or drop indexes/collections.
- [ ] Never run `compact` or `--repair` without clear justification.
- [ ] Never restart all MongoDB members simultaneously.

### Recovery

- [ ] Choose the least destructive way to add capacity, IOPS, or RAM.
- [ ] Clean only verified artifacts outside `dbPath` per retention policy.
- [ ] Process replica set members one at a time while preserving majority.
- [ ] Align resource limits with cgroup, StorageClass, or Atlas tier settings.
- [ ] Re-verify `df`, memory pressure, and I/O after changes.
- [ ] Confirm replica health, lag, and clean startup/recovery logs.
- [ ] Run policy-compliant business read/write checks and reconcile ambiguous outcomes.

### Post-Incident

- [ ] Monitor time-to-full and cloud autoscaling boundaries.
- [ ] Review quotas, IOPS, cache sizing, queries, indexes, and TTL retention.
- [ ] Test backup/restore drills and verify CDC oplog windows.
- [ ] Set alerts on growth slope, latency, OOM events, and replication lag.
- [ ] Analyze retry amplification and failover capacity headroom.
- [ ] Write a postmortem covering root causes, decisions, and safeguards.

## 55. Postmortem: Improving to Prevent Recurrence

A good postmortem never stops at **"disk filled up, we expanded disk."** It answers:

1. **Why** did storage grow faster than projected?
2. Was any new ingestion job, backfill, or index build deployed beforehand?
3. Did alerts fire early enough relative to storage provisioning lead time?
4. Why did autoscaling or quotas fail to prevent it?
5. Why did failover/quorum succeed or fail to preserve availability?
6. Did applications trigger a retry storm or return success on unknown write outcomes?
7. Did data loss or duplicate business operations occur requiring reconciliation?
8. Did backups/restores satisfy RPO/RTO?
9. Were any hazardous emergency commands proposed, and what guardrails stopped them?
10. What changes are needed across deployments, capacity budgets, monitoring, ownership, and runbooks?

### Layered Prevention Actions

| Layer | Improvements |
| --- | --- |
| Product/app | Rate limits, queue budgets, idempotency, retry budgets |
| MongoDB query | Proper indexes, bounded aggregations, avoid full scans |
| Data lifecycle | Controlled TTL/retention, partitioning/archival policies |
| Storage | Capacity/IOPS headroom, autoscale ceilings, multi-zone failure domains |
| Memory | Runtime-aware cache sizing, cgroup requests/limits, connection budgets |
| Replica | Lag/oplog windows, staged recovery, tested failovers |
| Observability | Free bytes + time-to-full + latency + OOM + user impact |
| Operations | Change reviews, verified backups, restore drills, safe incident actions |

## 56. Summary

When MongoDB hits **full disk**, **memory pressure**, or **I/O saturation**, the top priority is not finding whichever command turns a red chart green fastest. The priority is **preserving acknowledged data, protecting replica sets and quorum, throttling load sources that worsen the outage, and restoring the specific constrained resource layer**.

Distinguish byte exhaustion, inode/quota exhaustion, read-only filesystems, and high disk latency. On the memory side, distinguish WiredTiger cache pressure, JVM OOM, MongoDB OOM/cgroup limits, and OS page cache. Never delete WiredTiger/journal/oplog files or PVCs, and never reflexively run `compact`, `--repair`, or cluster-wide restarts. Generally, curb non-essential ingestion and retries, verify mounts and volumes, and scale capacity, IOPS, or RAM via supported channels before deep tuning.

Once headroom returns, **a running process does not mean the incident is finished**. Verify replication health, write concern compliance, latency, business reads/writes, and any operations left ambiguous by timeouts. Over the long run, **time-to-full** alerting, memory/OOM telemetry, I/O latency tracking, retry-rate visibility, and tested backups catch resource exhaustion before it escalates into a data incident.

### Version-Specific Official References

- [MongoDB Manual — Production Notes](https://www.mongodb.com/docs/manual/administration/production-notes/)
- [MongoDB Manual — Configuration Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/)
- [MongoDB Manual — Replica Set Operations](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — db.stats()](https://www.mongodb.com/docs/manual/reference/method/db.stats/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — compact](https://www.mongodb.com/docs/manual/reference/command/compact/)
- [MongoDB Atlas — Monitor Clusters](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/)
- [Kubernetes Documentation — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes Documentation — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
