# Scaling Up or Down a Cluster and Controlling Data Movement in MongoDB

## 1. Operational Problem: Rapidly Growing Data and Traffic

A rental listings application initially ran on a three-member MongoDB replica set. After a year, listings and event history grew manyfold:

- The **listings** collection holds tens of millions of documents.
- The **bookingEvents** collection grows continuously from event writes.
- One large tenant drives most of the traffic, especially during peak hours.
- Search **p95/p99** response times are rising and disk I/O is high.
- Free disk space on nodes is shrinking, and maintenance and backup windows are lengthening.

The operations team asks:

> Should we add a member to the replica set, upgrade machine specs, add another shard, or change the shard key?

There is no single answer based solely on total byte volume. **Cluster scaling** can target **availability, read capacity, write throughput, storage capacity, or workload distribution**. Each objective demands a different operation.

Suppose you already run a three-shard sharded cluster and later want to shrink to two shards to reduce costs. That introduces the opposite challenge:

> How do we move data off the shard being removed without losing documents, breaking application reads, or overloading the remaining shards?

In MongoDB, separate two classes of work:

1. **Topology scaling:** changing the count of replica set members, number of shards, or their compute/storage resources.
2. **Data placement/movement:** managing how data is partitioned and migrated across shards, accounting for impacts on the balancer, network, disks, caches, and application load.

Overview diagram:

~~~text
                      Applications
                           |
                  Driver / mongos
                           |
       +-------------------+-------------------+
       |                                       |
 Replica set (unsharded)               Sharded cluster
       |                                       |
   Primary + Secondaries               Shard A  Shard B  Shard C
   (full dataset copy)                    |       |        |
       |                               Replica  Replica  Replica
 Add secondary for                       Set     Set      Set
 redundancy/read scale                    \       |        /
                                           \      |       /
                                      Balancer / range moves
~~~

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **scale up/down**, **replica-set scale out**, **shard scale out/in**, and **resharding**.
2. Explain why **adding a secondary does not automatically partition data or write load** across a replica set.
3. Understand the roles of **`mongos`, config server replica set, shard replica sets, shard keys, chunks/ranges, and the balancer**.
4. Plan adding/removing replica-set members considering **initial sync, majority, elections, and replication lag**.
5. Describe the workflow for adding a shard, preparing data, monitoring rebalancing, and verifying distribution.
6. Describe the workflow for removing/draining a shard plus tricky cases such as **unsharded collections, database primary shards, and zone constraints**.
7. Identify data skew, hot shards, poor shard keys, jumbo/unsplittable ranges, and migration overhead.
8. Define safety criteria across **latency, throughput, error rates, disk capacity, HA, and backup/RPO/RTO** before and after scaling.
9. Build a runbook with **preflight checks, monitoring, limits, stop conditions, and post-checks**.
10. Run a `mongosh` lab simulating load and data distribution **without altering a real MongoDB topology**.

> **Important scope:** Replica set and sharding admin commands in this lesson are for explanation and runbook design—**not an automated script to run blindly in production**. Some commands, helpers, and balancing algorithms have changed across MongoDB versions, and **Atlas** capabilities differ from self-managed clusters. Every real operation requires checking docs for your exact version, privileges, topology, backups, and maintenance plan. The safe lab near the end operates solely inside database **`mongo_scaling_lab_381`**.

## 2. Four Easily Confused Scaling Approaches

### 2.1. Vertical Scaling: Scale Up / Down

**Scale up** increases resources on existing nodes:

- Add RAM or increase available WiredTiger cache per configuration.
- Add CPU cores.
- Increase IOPS, throughput, or storage capacity.
- Upgrade instance class or cloud tier.

**Scale down** trims resources when load is lower while preserving headroom.

Example:

~~~text
Before: 8 vCPU, 32 GiB RAM
After:  16 vCPU, 64 GiB RAM
~~~

MongoDB does not need to move ranges across shards merely because CPU increased. However, changing machine specs or storage may require restarts, node replacements, or infrastructure migrations. In Atlas, availability and automation behavior depend on cluster tier and configuration.

**Adding disk capacity does not fix every latency problem.** If a missing index forces a query to scan 2 million documents, bigger disks will not turn that scan into an index scan.

### 2.2. Horizontal Scaling of a Replica Set

Adding a member to a replica set:

~~~text
                 Replica set

        Primary (writes)
             |
          oplog
        /     |      \
  Secondary A B       C (new member)
~~~

All **data-bearing members** in a replica set store a logical copy of the **exact same dataset**—not subsets of a collection per node.

Adding a secondary can:

- Increase data redundancy and fault tolerance by design.
- Provide additional read capacity if applications use an appropriate read preference.
- Provide a dedicated member for backups or reporting.

However, it **does not scale write throughput by splitting writes across multiple primaries**, and it does not shrink the storage footprint required on each member.

### 2.3. Horizontal Scaling via Sharding

**Sharding** distributes **shard key value ranges** (often called chunks or ranges) of a collection across multiple shards.

~~~text
Sharded collection: bookingEvents

Range R1 ---> Shard A
Range R2 ---> Shard B
Range R3 ---> Shard C
~~~

Each shard is normally deployed as its own **replica set**, providing high availability for the data slice it owns.

Adding a shard increases total capacity and can scale reads/writes when data and requests **route across shards evenly**. However, adding a shard will not fix a **hot shard key** or poorly targeted queries.

### 2.4. Resharding

**Resharding** changes how a collection is partitioned using a **different shard key** via the mechanism supported by your MongoDB version.

It may be needed when:

- The current shard key has low cardinality.
- One tenant or shard key value is excessively hot.
- Queries frequently run as scatter-gather.
- Growth patterns conflict with the current key.

Resharding differs from adding a shard. **Adding a shard** adds placement capacity; **resharding** changes the partitioning axis. Not every imbalance can be fixed by adding machines.

### 2.5. Strategy Selection Table

| Goal | Typical Approach | Limitations |
| --- | --- | --- |
| Node lacks CPU/memory | Scale up | Hardware ceiling, cost, restarts |
| Need more data redundancy | Add data-bearing replica member | Does not partition writes or dataset size |
| Need more read capacity | Add secondary + read routing | Secondaries can lag; primary still handles all writes |
| Dataset / per-shard capacity growing | Add shard | Depends on shard key and rebalancing |
| Single tenant causes a hotspot | Evaluate shard key / resharding / workload | Adding a shard may not relieve the hot shard |
| Excess shard capacity; cut cost | Remove shard + draining | Requires sufficient target headroom and safe migration |
| Overprovisioned node | Controlled vertical scale down | Risks losing headroom |

## 3. Components of a Sharded Cluster

### 3.1. mongos

**`mongos`** is the query router: it receives client requests and uses sharding metadata to route them to the right shards.

~~~text
Client/Driver
     |
     v
    mongos
   /  |  \
  A   B   C    (shard replica sets)
~~~

Never assume `mongos` stores application documents. Snapshotting a host running only `mongos` **is not a sharded cluster data backup**.

### 3.2. Config Server Replica Set (CSRS)

Config servers store **data distribution metadata, shard registry, and routing configuration**. They are essential for knowing which shard owns which range.

Never manually edit metadata collections in the **`config`** database to "force" data movement. Metadata layouts and management rules evolve across versions.

### 3.3. Shards

A shard holds a subset of sharded collections and may hold unsharded collections depending on deployment model and version.

Typically every shard is a replica set:

~~~text
Shard A: rsA(primary, secondary, secondary)
Shard B: rsB(primary, secondary, secondary)
Shard C: rsC(primary, secondary, secondary)
~~~

**HA within a shard** and **data distribution across shards** are two separate layers.

### 3.4. Shard Key

A **shard key** consists of one or more fields used to partition and route a sharded collection's documents.

Examples:

~~~javascript
{ tenantId: 1, createdAt: 1 }
~~~

or a hashed shard key where supported:

~~~javascript
{ listingId: "hashed" }
~~~

When choosing a shard key, evaluate:

- **Cardinality** (number of distinct values).
- **Frequency distribution** (which values dominate).
- **Monotonicity** (continuously increasing timestamps/keys).
- **Query targeting** (do queries include the shard key?).
- **Growth / hot tenants**.
- **Zones / data residency**.
- Index and unique constraint rules for your MongoDB version.

### 3.5. Ranges / Chunks

MongoDB tracks **shard key ranges** in metadata to manage data placement. Some docs and commands refer to these as **chunks**. Modern releases balance data/ranges using version-specific policies and heuristics.

Conceptual example:

~~~text
{ key: MinKey .. 1000 }   -> Shard A
{ key: 1000 .. 2000 }     -> Shard B
{ key: 2000 .. MaxKey }   -> Shard C
~~~

Never assume "every chunk is strictly 64 MiB" or "every shard must hold the exact same chunk count" across all versions. Range sizes and balancing heuristics vary.

### 3.6. Balancer

The **balancer** coordinates moving ranges across shards to satisfy cluster placement policies. After adding a shard, it can migrate ranges to utilize the new capacity; when removing a shard, draining migrates data off the outgoing shard.

The balancer does not automatically guarantee:

- Equal document counts on every shard.
- Equal query latency across all shards.
- Even splitting of a single hot tenant.
- Partitioning of datasets that cannot legally split.

The balancer enforces **metadata- and policy-driven placement**—it cannot fix every application bottleneck.

## 4. Inspecting Current State Before Scaling

### 4.1. Topology Inventory

Record:

- Whether the cluster is standalone, replica set, or sharded.
- MongoDB binary version and **Feature Compatibility Version (FCV)**.
- Number of shards and replica members per shard.
- CSRS and `mongos` topology.
- Member roles, votes, and priorities.
- Data, index, journal, and oplog sizes per node.
- Data ingestion and deletion rates.
- CPU, RAM, WiredTiger cache, disk IOPS, and network usage.
- Query/read/write mix, write concerns, and read preferences.
- Backup status, RPO/RTO, and latest restore drill.

### 4.2. Commands to Inspect a Replica Set

Connected to a **replica set `mongod`** with appropriate privileges:

~~~javascript
printjson(rs.status());
printjson(rs.conf());
~~~

These are **read-only inspections**. When connected to `mongos`, direct replica-set helpers do not inspect individual shards. Connect to the specific shard member/deployment per security policy.

### 4.3. Commands to Inspect a Sharded Cluster

Connected through **`mongos`**:

~~~javascript
sh.status();

printjson(
  db.getSiblingDB("admin").runCommand({
    listShards: 1
  })
);
~~~

On supporting `mongosh` versions, you can also check:

~~~javascript
printjson(sh.getBalancerState());
~~~

These helpers and commands require appropriate privileges and feature support. **`sh.status()`** output can be very large; avoid dumping sensitive metadata into public logs.

### 4.4. Reading the Symptoms Correctly

| Observation | Likely Cause | What to Verify |
| --- | --- | --- |
| High CPU across entire cluster | Overall workload, query plans, insufficient compute | Per-shard CPU, `explain`, throughput |
| High CPU on only one shard | Hot shard/tenant, skew, or routing | Shard key, query mix, per-shard ops |
| Disk nearly full on one shard | Data skew, indexes, orphan/temp data | Data/index sizes, ranges, cleanup |
| Secondary lag rising | Disk/network overload, initial sync/migration | Applied optime, oplog window |
| p99 rises while balancer runs | Migrations competing for resources | Migration progress, disk/network, slow ops |
| Scatter-gather rising | Queries missing the shard key | `explain` / shard targeting |
| App pool timeouts | Pool/network issue, not necessarily shard capacity | Driver checkout waits, server metrics |

Never decide to `addShard` solely from a cluster-wide average CPU chart.

## 5. Capacity Planning Before Adding or Removing Shards

### 5.1. Logical Data Size Alone Is Insufficient

Each shard consumes storage for:

- Collection data.
- Indexes.
- WiredTiger internal and temporary files.
- Oplog and journal.
- Migration staging and cleanup overhead.
- Backups, index builds, and maintenance overhead.

Beyond current bytes, reserve **headroom** for growth and data movement. When shrinking, outgoing shard data must fit onto surviving shards while still preserving operational headroom.

### 5.2. Adding-a-Shard Math

Suppose three shards hold **2.4 TB** total data/indexes distributed fairly evenly. Adding a fourth shard with an ideal target of **0.6 TB** per shard implies roughly **0.6 TB** moving to the new shard.

This is only an **idealized capacity estimate**:

~~~text
Before:
  Shard A: 0.8 TB
  Shard B: 0.8 TB
  Shard C: 0.8 TB

After (illustrative target):
  Shard A: 0.6 TB
  Shard B: 0.6 TB
  Shard C: 0.6 TB
  Shard D: 0.6 TB
~~~

Adding a shard does not mean the balancer guarantees an exact 0.6 TB split. Zones, shard keys, range sizes, collections, and balancing policies all affect actual placement.

### 5.3. Estimating Migration Duration

Moving roughly **600 GB** at an effective average throughput of **50 MB/s** (using decimal GB/MB units consistently):

\[
\text{Ideal time} \approx
\frac{600{,}000\ \text{MB}}{50\ \text{MB/s}}
=12{,}000\ \text{s}
\approx 3\ \text{hours}\ 20\ \text{minutes}
\]

Real elapsed time can be much longer due to:

- Ongoing application writes.
- Migration throttling and concurrency limits.
- Network latency/bandwidth between shard replica sets.
- Index, copy, catch-up, and cleanup overhead.
- Ranges that cannot split cleanly.
- Balancer windows and zones.
- CPU/disk contention from live user traffic.

Never promise SLAs based on idealized math without testing on a representative environment.

### 5.4. Removing-a-Shard Math

If four shards each hold 600 GB and you want to shrink to three shards, the remaining shards must absorb at least 600 GB of drained data plus headroom. Each surviving shard grows toward ~800 GB, excluding index, temp, and replication overhead.

If each shard currently has only 100 GB free, shrinking is **unsafe** even if total logical data looks "smaller than total nominal disk".

### 5.5. Headroom Guidelines

No single 10%, 20%, or 30% free-space rule fits every workload. Choose headroom based on:

- Data and index size plus growth rate.
- Peak write rate.
- Disk latency and storage tier.
- Migration cleanup needs.
- Backup and index-build workloads.
- Lead time to provision additional capacity.
- Internal RPO/RTO and safety margins.

### 5.6. Throughput Matters More Than Shard Count

Suppose Shard A runs at 90% CPU while Shards B and C run at 30%. If hot writes target a single shard key value on A, adding Shard D will not relieve A's CPU. Determine **whether keys and queries can actually spread** to D.

## 6. Adding a Replica-Set Member: Scaling Availability, Not Sharding

### 6.1. Logical Workflow

~~~text
Preflight:
  health + quorum + backups + oplog window
       |
Provision new mongod
       |
Network/TLS/internal auth/version/storage
       |
Add member
       |
Initial sync / data copy / oplog catch-up
       |
Member becomes eligible SECONDARY
       |
Verify replication and read routing
       |
Evaluate role/priority/votes per HA policy
~~~

### 6.2. Initial Sync

When adding a data-bearing member, the new node normally runs **initial sync** to copy data and catch up on concurrent writes. Duration depends on:

- Data size and index builds.
- Speed of sync source and target.
- Network and disk throughput.
- Replication lag and oplog window.
- Impact of current live workload.

Initial sync generates **heavy reads and network transfer**, so "just adding a secondary" still impacts cluster performance.

### 6.3. Illustrative `rs.add` Syntax

On the **PRIMARY** of a **lab replica set**, with proper administrative privileges:

~~~javascript
// ADMIN ILLUSTRATION ONLY - never run unplanned on production.
// Host must be a newly provisioned mongod with internal auth and TLS.
rs.add({
  host: "mongo-new.lab.example:27017",
  priority: 0,
  votes: 0
});
~~~

In many scenarios, adding initially as **non-voting and non-electable** bounds quorum and election impact during initial sync. After the member catches up and passes HA review, altering votes/priorities requires its own controlled step—especially near the 7-voter cap or under topology constraints.

**Never** add a member with a placeholder hostname. Verify exact syntax, votes, priorities, and configuration against your MongoDB version.

### 6.4. Monitoring the New Member

~~~javascript
const status = rs.status();
printjson(status.members.map(m => ({
  name: m.name,
  stateStr: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
~~~

Exact output fields vary by version. Never assume a member listed in configuration has **finished initial sync** and is safe for reads or HA.

### 6.5. Read Preference

To use secondaries for read scaling, applications need an appropriate **read preference** and clear awareness of trade-offs:

- The primary still processes all replica set writes.
- Secondary reads can be **stale** relative to the primary.
- Query targeting and replica topology affect latency.
- A secondary dedicated to backups may need isolation from user queries.

Adding a node while the entire application uses **`primary`** read preference will not offload any reads to the new secondary.

### 6.6. Majority and Voting

Changing the number of **voting members** alters majority quorum, election behavior, and `writeConcern: "majority"` acknowledgments. Do not merely count physical hosts. Consider:

- Which members hold votes.
- Member election eligibility.
- Failure domains.
- Network partitions.
- Write concern and journaling policies.

An **arbiter** votes without **storing data**, so it adds neither read capacity nor backup copies. Never add an arbiter to solve disk shortages or scale write throughput.

## 7. Removing a Replica-Set Member: Prioritize Quorum and Recovery

### 7.1. Scenario

A replica set has four data-bearing members, and one old node must be decommissioned during hardware replacement. Removal is safe once the replacement node has synced and HA meets policy.

### 7.2. Pre-Removal Runbook

1. Verify backups and restore paths.
2. Inspect **`rs.conf()`** and **`rs.status()`**.
3. Review votes, priority, hidden, delayed settings, and quorum impact.
4. Confirm the outgoing member no longer serves backups or read traffic.
5. Verify post-removal failure tolerance.
6. Confirm apps, monitoring, and DNS do not hardcode that node.
7. Schedule a maintenance window if required.

### 7.3. Illustrative Syntax

On the `PRIMARY`, with administrative privileges after verifying preconditions:

~~~javascript
// CALL SYNTAX ILLUSTRATION ONLY; do not run on a live cluster blindly.
rs.remove("mongo-old.lab.example:27017");
~~~

**`rs.remove()` changes replica-set membership; it does not drain a shard in a sharded cluster.** Nor does it rebalance data ranges. If the member is a shard primary or critical voter, extra preparation is required; never misuse `rs.remove()` thinking it "scales down 1 shard".

### 7.4. Post-Checks

- Replica set retains a stable `PRIMARY`.
- Majority write concern works properly.
- Secondaries remain healthy with lag within thresholds.
- Read preferences do not route to the removed node.
- Backups and monitoring remain valid.
- Overall throughput and p95/p99 meet SLOs.

### 7.5. Do Not Wipe Disks Immediately

Stopping/removing a `mongod` may be part of hardware retirement, yet old disks hold sensitive data. Follow retention and secure disposal policies—never hot-wipe or reattach an old disk to an active member. Decommission resources only after sign-off and proper data/secret sanitization.

## 8. Adding a Shard: Provisioning Plus Rebalancing

### 8.1. Prerequisites

Before adding a shard, verify:

- `mongos` routers and CSRS are healthy.
- Existing shard replica sets are stable.
- The new shard is a properly configured replica set not belonging to any other cluster.
- Version, FCV, and feature compatibility align.
- Networking, hostname resolution, TLS, internal authentication, and admin privileges work.
- Sufficient disk, index, and IOPS capacity on the new shard.
- Backups and monitoring cover the new shard.
- Zone and data placement rules are planned.
- Balancer and migrations have active monitoring.

### 8.2. Illustrative `addShard` Syntax

Execute only against `mongos` in an approved **lab sharded cluster** once the new replica set is provisioned:

~~~javascript
// Connect to mongos, never to a standalone mongod.
// Operational illustration example.
sh.addShard(
  "rsShardD/shard-d1.lab.example:27017,shard-d2.lab.example:27017,shard-d3.lab.example:27017"
);
~~~

Or via the equivalent admin command where supported:

~~~javascript
db.getSiblingDB("admin").runCommand({
  addShard:
    "rsShardD/shard-d1.lab.example:27017,shard-d2.lab.example:27017,shard-d3.lab.example:27017"
});
~~~

This is **not part of the `mongosh` data lab at the end of this lesson**. Those hosts do not exist on a learner's local machine; never run with real hostnames outside an approved change management process.

### 8.3. After `addShard` Succeeds

Adding a shard to cluster metadata does not mean data has moved yet. You must:

1. Confirm the shard appears in **`listShards` / `sh.status()`**.
2. Confirm it is healthy.
3. Monitor balancing and range migrations.
4. Inspect actual distribution per collection and shard.
5. Watch application latency, throughput, and error rates.
6. Verify backups, failover, and monitoring cover the new shard.

### 8.4. The Balancer Does Not Move Every Collection Immediately

The balancer acts based on imbalance thresholds, migration throttling, and placement rules:

- Collections may remain concentrated on older shards for hours.
- Zones restrict which shards may hold specific data.
- Shard keys can limit how cleanly certain ranges split.
- Unsharded collections follow separate placement rules.

Never see shard count rise from 3 to 4 and claim "write capacity instantly grew 33%".

## 9. How Does Range Migration Work?

### 9.1. Donor and Recipient Concepts

The **donor shard** currently owns the range; the **recipient shard** receives it.

~~~text
Shard A (donor)                     Shard D (recipient)
    |                                      |
    |  Range [K1,K2)                       |
    +--------------- copy ---------------->|
    |                                      |
    |  New writes/changes continue         |
    +--------- catch-up changes ---------->|
    |                                      |
    +----------- ownership commit -------->|
    |                                      |
    |       Metadata/routing updated       |
    |                                      |
    +--- cleanup orphaned data (when safe)
~~~

This is a conceptual model. Exact phases, critical section durations, and concurrent write/transaction handling depend on MongoDB version.

### 9.2. Why Can Migrations Be Slow?

- Large range byte volume.
- Large indexes.
- Slow disk or network on recipient.
- Heavy write rate on donor forcing continuous catch-up.
- Long-running transactions or operation conflicts.
- Balancer policies and throttling.
- Zone constraints.
- Concurrent metadata/DDL operations.
- Old data cleanup and open cursors.

Migration speed never matches raw file-copy tools because MongoDB must preserve **consistency and live routing**.

### 9.3. Routing During Migration

`mongos` and drivers use metadata to target shards. When ownership shifts, routing caches refresh and operations may hit transient/retryable errors depending on version and features.

Applications should:

- Use a compatible driver with supported retry semantics.
- Configure reasonable timeouts.
- Handle transient network/server errors cleanly.
- Enforce idempotency on write workflows where retries have unknown outcomes.
- Monitor error rates and latency during migrations.

Never disable all retries or blindly add unbounded custom write retries just because rebalancing is underway.

### 9.4. Critical Section Does Not Mean Multi-Hour Cluster Freeze

Range migration is designed to keep serving workloads, with a brief synchronized commit/ownership phase. Exact latency impact and blocked operations depend on version and workload.

**Never promise "migrations always have zero downtime and zero latency impact".** Measure on a representative environment and keep stop runbooks ready if SLOs breach.

### 9.5. Orphan Cleanup

Once range ownership transfers, the donor may temporarily retain orphaned documents until safe cleanup completes. Consequently:

- Donor disk usage **does not always drop immediately**.
- Logical data size and physical disk bytes may temporarily diverge.
- Never write ad-hoc scripts to delete "orphan documents" manually.
- Track cleanup and retention via supported tools.

### 9.6. Never Attempt to Move Data via `updateOne`

In a sharded collection, editing a business field—or even updating a shard key—is not a general method to "move chunks". Updating shard keys has strict rules and differs completely from MongoDB-managed **range migration**.

Never do this:

~~~javascript
db.listings.updateMany(
  { tenantId: "t001" },
  { $set: { shardLocation: "shardD" } }
);
~~~

and claim data moved to Shard D. A business field named **`shardLocation`** is not MongoDB routing metadata.

## 10. Balancer: Policy-Level Control

### 10.1. Checking Status

On `mongos`, with appropriate privileges:

~~~javascript
sh.status();
printjson(sh.getBalancerState());
~~~

In supporting deployments/versions, inspect detailed status via MongoDB monitoring or admin APIs. Field names and outputs can vary across versions.

### 10.2. When to Observe vs. Intervene

If the balancer moves data steadily while p95/p99, replication lag, and disk headroom remain healthy, let it run.

If a migration causes overload:

1. Gather evidence on latency, errors, disk/network load, and active migrations.
2. Confirm migrations are actually the root cause.
3. Check version-supported migration concurrency/window tuning.
4. Pause the balancer intentionally if justified.
5. Never execute unverified force commands.

### 10.3. `stopBalancer` / `startBalancer`

In supporting `mongosh` versions:

~~~javascript
// ADMIN ILLUSTRATION; never run arbitrarily.
sh.stopBalancer();

// After resolving the incident and getting approval to resume:
sh.startBalancer();
~~~

Stopping the balancer:

- **Does not revert** already-migrated data.
- Delays draining and rebalancing.
- Does not guarantee an in-progress critical migration phase aborts instantaneously.
- Can stall workflows that depend on balancing.

Before toggling balancer state, know which workflows depend on it and schedule re-enabling it.

### 10.4. Manual Chunk/Range Moves

MongoDB provides manual range/chunk move commands in supporting versions. Never run them manually "to speed things up" without understanding:

- Range boundaries.
- Current owner.
- Shard key pattern.
- Balancer and zone constraints.
- Migration conflicts.
- Target disk headroom.

This lesson intentionally **omits running `moveChunk`/`moveRange` directly against a real cluster** as a lab step. When needed operationally, consult docs for your exact MongoDB version under an approved change procedure.

### 10.5. Balancing Units Are More Than Document Counts

Two ranges with 10,000 documents each can differ drastically in bytes if one holds huge arrays and heavy indexes. Likewise, 10 GB of "cold" archive data costs far less than 10 GB hit on every request.

Track **bytes, operations, latency, and hot-key distribution** rather than document counts alone.

## 11. Shrinking a Sharded Cluster: Removing a Shard Requires Draining

### 11.1. Dangerous Mistake

Wrong:

~~~text
Cluster has 4 shards.
Pick Shard D with the least data.
Shut down Shard D's mongod processes.
Delete the VMs / cloud volumes.
~~~

If D still owns ranges or unsharded collections, `mongos` keeps routing requests to D. Powering off the hosts does not make MongoDB move data to the remaining three shards.

### 11.2. Draining

**Removing a shard** from a sharded cluster is a structured workflow that evacuates data and ownership before detaching the shard.

~~~text
Preflight capacity/quorum/backup
               |
               v
          Begin drain
               |
               v
Balancer migrates ranges to remaining shards
               |
               v
Handle unsharded collections / database primary
               |
               v
Monitor drain state and remaining objects
               |
               v
MongoDB confirms removal completed
               |
               v
Decommission hosts, volumes, monitoring, secrets
~~~

### 11.3. Illustrative `removeShard` Syntax

On **`mongos`** in an approved **sharded lab**:

~~~javascript
// NEVER run in production without an approved runbook.
const admin = db.getSiblingDB("admin");
printjson(admin.runCommand({
  removeShard: "shardD"
}));
~~~

The command reports states such as **`started` / `ongoing` / `completed`** along with progress fields depending on version. Removal can take hours or longer; never treat an initial `"started"` reply as safe removal completion.

To track progress, use your running version's monitoring APIs/commands. Some workflows poll `removeShard` per documentation, so confirm exact version semantics before automating.

### 11.4. Never Delete Hosts Before `completed`

Even if dashboards show disk usage near zero, confirm **MongoDB reports removal completed** and zero metadata/placement dependencies remain.

A shard can still hold:

- Unsharded collections.
- Primary shard ownership for a database.
- Ranges pinned by special zones.
- Pending cleanup or uncommitted migrations.
- Backup, monitoring, or application dependencies.

### 11.5. Unsharded Collections and Primary Shard

Across MongoDB versions, unsharded collections and a **database's primary shard** have dedicated placement/move rules, involving commands such as **`movePrimary`**, **`moveCollection`**, or newer version mechanisms.

Never run these from one generic recipe:

- Audit which databases and collections are unsharded.
- Check which shard serves as each database's primary.
- Identify the version-supported command to move metadata and data safely.
- Verify indexes, privileges, and application assumptions.
- Monitor progress and verify zero blockers remain.

### 11.6. Zone Constraints

If Shard D is the **only shard** assigned to Zone Z while ranges require Zone Z, the balancer has no valid destination to drain into.

Before removing:

1. Inventory zone-to-shard mappings.
2. Review zone ranges and data residency mandates.
3. Ensure surviving shards satisfy every zone policy.
4. Never strip zone constraints merely to dump data into a prohibited region.

### 11.7. Final Decommissioning

Once MongoDB confirms `completed` and post-checks for HA, backups, and SLOs pass:

- Remove shard hosts from service discovery and monitoring cleanly.
- Revoke and rotate old host credentials and certificates.
- Archive the change audit and manifest.
- Sanitize and decommission storage volumes per policy.
- Update disaster recovery topology.
- Update capacity and cost forecasts.

## 12. The Shard Key Dictates Most of Your Scaling Ceiling

### 12.1. Low Cardinality

Shard key:

~~~javascript
{ status: 1 }
~~~

where `status` only takes `active`/`inactive` has very few distinct values. Too few distinct values prevents splitting data finely and evenly across shards depending on schema and range splitting limits.

Never pick a shard key merely because a field appears often in queries.

### 12.2. Monotonically Increasing Key

Sharding on continuously increasing `createdAt` drives all new inserts into the highest-value range, creating a **hot shard** without a scatter-friendly key design.

~~~text
Timeline:
  10:00 -> 10:01 -> 10:02 -> 10:03 ...
                           ^
                     Hot insert tail
~~~

Adding shards rarely relieves a monotonic hotspot if every new write hits a single tail range.

### 12.3. Hashed Shard Key

Hashed keys distribute writes across shards when the underlying field has high cardinality. However:

- Hashing trades off efficient range queries.
- Hashing **a field holding the exact same value across all documents of a huge tenant** still hashes to one single value.
- A hot tenant stays concentrated if the shard key cannot subdivide inside the tenant.

For example, if all documents for tenant `t001` have:

~~~javascript
tenantId: "t001"
~~~

then **`{ tenantId: "hashed" }`** still maps every `t001` document to the exact same hash key. Hashing does **not** automatically split one hot tenant across shards.

### 12.4. Compound Shard Key

A compound shard key can combine tenant with a high-cardinality field to distribute data more evenly, while requiring evaluation of:

- Query targeting by key prefix.
- Read/write distribution.
- Supporting index requirements.
- Oversized tenants.
- Ranges and zones.
- Unique index rules.

Candidate design to test:

~~~javascript
{ tenantId: 1, listingId: 1 }
~~~

Never assume this is universally optimal. If `listingId` increments monotonically per tenant, a single huge tenant can still form a hot tail. Simulate realistic access patterns.

### 12.5. Scatter-Gather

A query omitting the shard key fans out across all shards:

~~~text
Client -> mongos -> A + B + C + D
                          |
                      Merge results
~~~

Adding shards spreads data yet increases scatter-gather fan-out cost for untargeted queries. Measure the **targeted vs. scatter-gather query ratio** when evaluating shard keys.

### 12.6. Resharding When Rebalancing Cannot Help

When hotspots stem from the shard key itself, adding shards and running the balancer will not fix it. Evaluate **`reshardCollection`**, refining the shard key, or remodeling data per server capabilities.

Resharding consumes heavy storage and network, generates temporary data, and must guard against write/DDL conflicts. Prepare:

- Backup and restore plan.
- Preflight capacity headroom.
- Query and index compatibility review.
- Active progress monitoring.
- Failure-handling runbook.
- Post-reshard validation.

Never treat changing a shard key as a simple one-line config tweak.

## 13. Jumbo/Unsplittable Ranges and Data Skew

### 13.1. Why Are Some Ranges Hard to Split?

If many documents share one identical shard key value, or oversized documents accumulate, a range becomes impossible or impractical to split further.

MongoDB versions use differing terms and mechanics for **jumbo** or **unsplittable** ranges; never assume every release shares the exact same marker or status field.

### 13.2. Symptoms

- Shard A holds far more data than peers.
- The balancer runs yet moves almost nothing.
- Specific migrations repeatedly fail.
- Logs report range/chunk split or move failures.
- Skew persists even after adding a new shard.

### 13.3. Analysis Steps

1. Check shard key cardinality and value frequency.
2. Inspect per-shard and per-collection distribution.
3. Inspect migration logs and balancer status.
4. Check zone constraints.
5. Inspect document sizes and hot-key distribution.
6. Verify version-specific behavior.

Never edit config metadata directly or force-move a huge range in production without a version-specific runbook.

### 13.4. Byte Balance Does Not Equal Heat Balance

~~~text
Shard A: 400 GB, 8,000 ops/s
Shard B: 400 GB, 1,000 ops/s
Shard C: 400 GB, 1,000 ops/s
~~~

Byte distribution looks balanced, yet Shard A is heavily overloaded. Investigate key/query routing, caching, per-shard network/CPU, and request distribution.

## 14. Zones and Data Residency

### 14.1. Zone-Aware Placement

An organization may mandate that data belonging to a geographic region stay strictly on shards inside that region.

~~~text
Zone VN:
  Shard A, B

Zone SG:
  Shard C, D

Data range for VN -> permitted only on shards in Zone VN
~~~

This is a conceptual diagram; zone enforcement depends on shard keys, range definitions, and actual cluster setup.

### 14.2. Adding a Shard to a Zone

Adding Shard D to the cluster does not automatically make it eligible for zoned ranges. Update zone tags and ranges per policy. Never move data across restricted regions casually.

### 14.3. Shrinking Within a Zone

Removing a shard from a zone without enough capacity on remaining shards in that zone blocks draining or creates hotspots. Always check **per-zone capacity**, not just cluster-wide totals.

### 14.4. Residency and Security

Balancing transfers data over the network between shards. Ensure:

- Encrypted connections / TLS.
- Data residency compliance.
- Proper network routes and firewalls.
- Key management.
- Audits for zone/topology edits.

## 15. Read/Write Policies While Scaling

### 15.1. Read Concern and Read Preference

When adding secondaries or shards:

- Read preference tells the driver whether to target the primary or secondaries within the right replica set.
- Read concern controls consistency/isolation visibility per configuration.
- Query targeting routes requests to the right shard(s).

Never call "reading from secondaries" a way to split writes across shards.

### 15.2. Write Concern

In a replica set, `writeConcern: { w: "majority" }` strengthens replication durability per deployment, with latency tied to member health and lag.

While scaling members or moving data:

- Never weaken write concern merely to make benchmarks look faster.
- Track write concern timeouts.
- Confirm majority still behaves as expected.
- Check availability whenever altering voting members.

### 15.3. Multi-Shard Transactions

Transactions spanning multiple shards incur higher coordination overhead than single-shard transactions. Shard key and query design determine how many shards participate.

While scaling:

- Measure transaction p95/p99.
- Watch retries and transient transaction errors.
- Avoid hot shards amplifying coordination overhead.
- Never assume more shards automatically make every transaction faster.

### 15.4. Causal Consistency and Indexing

Shard-level data migration is distinct from client read-your-writes guarantees and index freshness. Applications still need appropriate sessions, read concerns, and write concerns. Never drop causal consistency or isolation policies just because the cluster scaled.

## 16. Monitoring Migrations: Minimum Telemetry

### 16.1. Application SLIs

- RPS and successful throughput.
- Error/timeout rates by query and operation.
- p50/p95/p99 latency.
- Write concern timeouts and retries.
- Transaction latency.
- Read-after-write or consistency errors.

### 16.2. MongoDB SLIs

- Per-shard CPU and memory.
- WiredTiger cache and eviction pressure.
- Disk read/write latency, IOPS, and free space.
- Network in/out across shards.
- Connection counts and pool pressure.
- Replication lag and oplog window.
- Read/write ops per shard.
- Balancer/migration status and completed/failed migration counts.
- Distribution by shard, collection, and zone.

### 16.3. Watch Both Donor and Recipient

Watching only the recipient misses disk/network saturation or oplog lag on the donor. Range migration loads both ends, plus config servers and `mongos` for metadata and routing.

### 16.4. Disk Usage Does Not Drop Instantly

After a range moves, the donor may wait on safe cleanup, keeping disk space allocated temporarily. Meanwhile, the recipient needs room for incoming data plus temporary migration overhead.

Never push extra data onto a recipient merely because `used bytes` has not climbed much yet.

### 16.5. Do Not Count Only Completed Migrations

"100 migrations completed" does not tell you:

- Total bytes actually moved.
- How many ranges/chunks remain unbalanced per policy.
- Whether a hot shard is still overloaded.
- How long failed/retried migrations took.
- Whether app latency breached SLOs.

Put **progress + cluster health + business SLOs** on one dashboard.

## 17. Safety Guardrails During Topology Changes

### 17.1. Guardrail Examples

A hypothetical plan might enforce:

| Metric | Example Target | Action When Breached |
| --- | --- | --- |
| Search p95 | <= 180 ms | Inspect migrations and resources |
| Search p99 | <= 450 ms | Consider pausing/throttling migrations |
| 5xx / timeout | <= 0.5% | Investigate immediately |
| Replication lag | Within internal RPO/HA cap | Reduce load / wait for catch-up |
| Free disk | Above approved headroom | Halt scale-in and expand capacity |
| Oplog window | Covers catch-up + incident margin | Do not let backup/node lag persist |
| Backup age | Within policy | Restore backup coverage |

These p95/p99/error figures are **illustrative thresholds**, not MongoDB standards. Derive real guardrails from your SLOs, RPO/RTO, and workload.

### 17.2. Define Stop Conditions Before Starting

Do not wait until a node saturates to debate pausing the balancer. Preflight requires:

1. Decision owner authorized to pause or abort.
2. Clear alert thresholds.
3. Ready administrative permissions.
4. Version-appropriate steps to pause migrations safely.
5. Application traffic recovery plan.
6. Plan for partially migrated data.
7. Verification checks after pausing.

### 17.3. Rollback Is Not a Single Undo Button

Moving hundreds of ranges from A to D cannot be "instantly rolled back" simply by deleting D.

A **topology change rollback** may require:

- Stopping new migrations cleanly.
- Restoring compute/routing capacity.
- Migrating data back via supported procedures.
- Checking health and consistency.
- Keeping the new shard temporarily instead of rushing removal.

If mid-`removeShard`, changing course has version-specific semantics; never assume every version offers an instant **`cancel removeShard`** button.

### 17.4. Backups Do Not Replace a Pause Plan

Backups protect against disasters, yet restoring takes hours and incurs an RPO gap. Minor distribution skew should be managed via operational controls—not reflexive full-cluster restores.

## 18. Detailed ADD SHARD Runbook

### 18.1. Phase A — Planning

~~~text
Goal:
  Add capacity for growth and relieve hotspots

Inputs:
  topology, version/FCV
  capacity per shard
  shard key distribution
  zones
  write/read mix
  p95/p99 SLO
  backup health
~~~

Planning must answer explicitly **whether adding a shard actually removes the bottleneck**. If one tenant drives one hot shard key value, fix key design beforehand or alongside.

### 18.2. Phase B — Provision

- Provision the new shard replica set per HA policy.
- Configure hosts, networking, TLS, and internal authentication.
- Confirm compatible binary versions.
- Provision storage and IOPS headroom.
- Wire up monitoring and backups.
- Verify standalone shard health independently.

Never deploy an ad-hoc single standalone `mongod` as a production shard just to save nodes.

### 18.3. Phase C — Add

Operators run `sh.addShard` via `mongos` per deployment docs, logging result, shard ID, timestamp, and config diff in the change record.

After `addShard`, **do not mark the change complete yet**.

### 18.4. Phase D — Monitor Rebalance

Track:

~~~text
old shard distribution
      |
addShard
      |
range migrations
      |
new distribution
      |
stable workload
~~~

During execution:

- Watch application SLOs.
- Watch migration failures and retries.
- Monitor shard disk and network.
- Check remaining skewed zones/ranges.
- Verify write concerns and replication lag.

### 18.5. Phase E — Verify

Success requires:

1. New shard healthy.
2. Collections and ranges match placement policy.
3. Skew and hotspots reduced as targeted.
4. Queries return accurate results and business metrics stay consistent.
5. p95/p99 and error rates within SLO.
6. Backups, restores, and monitoring updated.
7. Zero unexplained lingering migration failures.

### 18.6. Phase F — Handover

Archive:

- Timestamp of `addShard`.
- Shard/replica set hosts.
- Bytes moved and duration.
- Before/after SLOs.
- Warnings and incidents.
- Remaining risks.
- Updated capacity forecast.

## 19. Detailed REMOVE SHARD Runbook

### 19.1. Phase A — Preflight

Never start without confirming:

- Remaining shard capacity and headroom.
- Valid zone placements.
- Inventory of collections/ranges on the outgoing shard.
- Inventory of unsharded collections and database primary assignments.
- Backup and restore readiness.
- Version-supported data movement procedures.
- SLOs and stop conditions.
- Authorizations and change owner.

### 19.2. Phase B — Begin Draining

Operators execute `removeShard` on `mongos` inside the maintenance plan, recording the response and tracking drain progress.

### 19.3. Phase C — Data Evacuation

The balancer migrates ranges to surviving shards within placement rules. Only when:

- Target capacity and zones suffice.
- No unmovable ranges block progress.
- All required metadata moves succeed.

can draining finish.

### 19.4. Phase D — Remaining Objects

Check for:

- Ranges still on the shard.
- Databases where the shard is primary.
- Unsharded collections.
- Zone or invalid-config blockers.
- Slow or failing migrations.

Never assume range count hitting 0 means zero dependencies remain.

### 19.5. Phase E — Confirm Completed

Decommission only once MongoDB/monitoring reports shard removal **`completed`** per API/version—never when the command merely returned `started`.

### 19.6. Phase F — Decommission

After `completed`:

- Stop and remove old infrastructure per runbook.
- Update inventory, alerts, and backup policies.
- Revoke host certificates and secrets.
- Wipe/sanitize storage per policy.
- Monitor cluster stability after migrations halt.

### 19.7. Phase G — Post-Change Soak

Observe long enough to cover:

- Peak traffic.
- Background batch jobs.
- Backups and replication.
- Disk growth.
- Read/write p99.
- Targeted vs. scatter-gather query ratios.

Never stop monitoring 5 minutes after `removeShard` completes.

## 20. Atlas Scaling vs. Self-Managed

### 20.1. Atlas Cluster Tiers

MongoDB Atlas supports modifying cluster tier, compute, storage, and sharding depending on deployment type, subscription, features, and version. Atlas automation handles most infrastructure work.

Still, users remain accountable for:

- Capacity planning.
- SLOs.
- Index and query design.
- Shard keys.
- Data residency.
- Access control and backup/restore policies.
- Change impact.

### 20.2. Auto-Scaling

Some Atlas tiers support compute and storage auto-scaling under specific rules. **Auto-scaling never fixes a bad shard key**, nor does it eliminate a hot tenant or scatter-gather queries.

Scaling storage **down** may be restricted or require migration/rebuilds depending on service rules; never assume storage increases reverse with one click.

### 20.3. Adding/Removing Shards in Atlas

Depending on cluster type and UI/API controls, changing shard counts differs from self-managed `mongos` operations. Follow Atlas docs for your deployment. **Never assume running `removeShard` directly from an Atlas client shell is allowed.**

### 20.4. Self-Managed

In self-managed clusters, operators manage:

- Host and volume provisioning.
- Internal authentication and TLS.
- Replica sets, `mongos`, and config servers.
- Networking and firewalls.
- Balancer and migration policies.
- Backups and restores.
- Monitoring and capacity.

High flexibility brings full operational responsibility. Never deploy an insecure handful of `mongod` processes as a makeshift production sharded cluster outside a lab.

## 21. mongosh Lab: Simulating Distribution and Hot Shards Without Changing Topology

### 21.1. Idea and Boundaries

This lab **does not require a real sharded cluster**. It runs on any standalone, replica set, or sharded MongoDB where the user can create the lab database/collection.

We seed 2,400 synthetic events with:

- One large tenant **`t001`** driving high volume and heavy traffic.
- Smaller tenants.
- **`currentBucket`** simulating poor placement: every `t001` document lands in bucket `0`.
- **`proposedBucket`** simulating even placement by event ID.
- **`approxBytes`** estimating document size to show why "counting documents" misses byte skew.
- **`trafficWeight`** modeling request heat.

**`bucket` is just an illustrative document field, not a real shard.** MongoDB **does not move documents between shards** when you vary `currentBucket`/`proposedBucket`. This lab models hypothetical distribution for capacity planning; real placement requires shard keys/resharding and the balancer in a sharded deployment.

### 21.2. Idempotently Seed 2,400 Documents

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_scaling_lab_381");
  const events = lab.getCollection("lab_events");
  const tag = "scale381-v1";
  const n = 2400;
  const batchSize = 200;
  let ops = [];

  function flush() {
    if (ops.length === 0) return;
    events.bulkWrite(ops, { ordered: false });
    ops = [];
  }

  for (let i = 0; i < n; i++) {
    const tenantId = i % 10 < 6
      ? "t001"
      : "t" + String(2 + i % 9).padStart(3, "0");
    const id = "b381-event-" + String(i).padStart(6, "0");
    const currentBucket = tenantId === "t001" ? 0 : i % 4;
    const proposedBucket = i % 4;

    const doc = {
      _id: id,
      labTag: tag,
      tenantId,
      region: ["HCM", "HN", "DN"][i % 3],
      createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
      currentBucket,
      proposedBucket,
      approxBytes: i % 20 === 0 ? 51200 : 1024 + (i % 3) * 1024,
      trafficWeight: tenantId === "t001" ? 20 : 1,
      eventType: i % 3 === 0
        ? "booking_created"
        : "listing_viewed"
    };

    ops.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });

    if (ops.length >= batchSize) flush();
  }
  flush();

  events.createIndex(
    { labTag: 1, tenantId: 1 },
    { name: "ix_381_lab_tenant" }
  );
  events.createIndex(
    { labTag: 1, currentBucket: 1 },
    { name: "ix_381_lab_current_bucket" }
  );

  printjson({
    seeded: events.countDocuments({ labTag: tag }),
    sample: events.find(
      { labTag: tag },
      {
        _id: 1,
        tenantId: 1,
        currentBucket: 1,
        proposedBucket: 1,
        trafficWeight: 1
      }
    ).sort({ _id: 1 }).limit(5).toArray()
  });
})();
~~~

Expected result: **`seeded = 2400`**. `bulkWrite` only upserts `_id` values tagged with this lab; if another document shares an `_id` without `labTag`, it throws a duplicate key error instead of overwriting. Never drop the collection as a "quick fix".

### 21.3. Count Tenant Volume and Heat

~~~javascript
const lab = db.getSiblingDB("mongo_scaling_lab_381");
const events = lab.getCollection("lab_events");

printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: "$tenantId",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        trafficWeight: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { trafficWeight: -1 } }
  ]).toArray()
);
~~~

Explanation: because **`t001`** holds many documents and high **`trafficWeight`**, any shard holding all of `t001` risks becoming hot even if peer shards hold similar disk totals.

### 21.4. Current Distribution by Bucket

~~~javascript
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: "$currentBucket",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Bucket 0 exhibits huge **`syntheticLoad`** because `t001` always maps there, while peer buckets sit lightly loaded. This simulates **placement skew** caused by tenant-level partitioning.

### 21.5. Hypothetical Distribution After Changing Strategy

~~~javascript
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: "$proposedBucket",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Because `proposedBucket` uses `i % 4`, events and weights spread evenly. However:

- `proposedBucket` **is not an actual MongoDB shard key**.
- `i % 4` is a deterministic lab formula, not MongoDB's hashed shard key function.
- Applying an equivalent design in production may require **resharding**, compound keys, index updates, and query changes.
- Spreading a single tenant's events across shards can force per-tenant queries to fan out across shards.

### 21.6. Measure Skew Spread

~~~javascript
function summarizeBuckets(fieldName) {
  const groupId = "$" + fieldName;
  return events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: groupId,
        docs: { $sum: 1 },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
}

const oldBuckets = summarizeBuckets("currentBucket");
const newBuckets = summarizeBuckets("proposedBucket");

function spread(rows) {
  const weights = rows.map(x => x.syntheticLoad);
  const max = Math.max(...weights);
  const min = Math.min(...weights);
  return { max, min, maxOverMin: min ? max / min : null };
}

printjson({
  current: { rows: oldBuckets, spread: spread(oldBuckets) },
  proposed: { rows: newBuckets, spread: spread(newBuckets) }
});
~~~

**`maxOverMin`** is a coarse comparison of synthetic load—it never replaces real request p95/p99. Also evaluate disk bytes, index sizes, and query routing before adopting a new design.

### 21.7. Calculate Data Moved in the Model

~~~javascript
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $project: {
        changedBucket: {
          $ne: ["$currentBucket", "$proposedBucket"]
        },
        approxBytes: 1
      }
    },
    {
      $group: {
        _id: "$changedBucket",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" }
      }
    }
  ]).toArray()
);
~~~

This reports how many **documents and estimated bytes** switch buckets in the model. It is a **hypothetical estimate**, omitting index overhead, journal/oplog, metadata, replication, concurrency, and balancer constraints.

### 21.8. Simulating Scale-In from Four Buckets to Three

A naive heuristic:

~~~javascript
// Read-only simulation of new destination buckets.
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $project: {
        destination: { $mod: ["$proposedBucket", 3] },
        approxBytes: 1,
        trafficWeight: 1
      }
    },
    {
      $group: {
        _id: "$destination",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Because bucket 3 remaps onto bucket 0, this simple mapping **skews heavily**. Takeaway: scale-in demands explicit capacity modeling and placement policies, not naive modulo arithmetic.

### 21.9. Never Use This Lab to Benchmark Real Migration Throughput

Aggregating 2,400 records inside one database does not reflect:

- Network copying between shard replica sets.
- Balancer coordination.
- Replication lag.
- Index and storage footprint.
- Chunk/range metadata.
- Real user p99 latency.

To benchmark migrations, use an **authorized sharded staging cluster**, representative data/workloads, and full monitoring. This lab teaches **distribution and capacity analysis**.

## 22. Read-Only Diagnostics on a Sharded Staging Cluster

If you have an authorized sharded staging cluster with status privileges, inspect via `mongos`:

~~~javascript
// Connect to mongos, never standalone mongod.
sh.status();

const admin = db.getSiblingDB("admin");
printjson(admin.runCommand({ listShards: 1 }));
~~~

For a specific sharded collection, supporting `mongosh` versions offer:

~~~javascript
// Replace with your actual sharded namespace in staging.
db.getSiblingDB("rental_staging")
  .getCollection("listings")
  .getShardDistribution();
~~~

Helper availability and output vary by version. If unsupported, rely on MongoDB admin or Atlas monitoring APIs instead of editing or inferring from internal config metadata.

Never run **`sh.addShard`**, **`removeShard`**, **`reshardCollection`**, **`sh.stopBalancer`**, or **`rs.reconfig`** as part of this read-only inspection lab.

## 23. When Is Resharding Needed Instead of Just Adding Shards?

### 23.1. Strong Indicators

- One shard absorbs nearly all writes.
- A single shard key value accounts for too much data.
- Adding shards fails to reduce load on the hot shard.
- Ranges/chunks cannot split due to poor key design.
- Scatter-gather routing dominates queries.
- Zones or tenant isolation demand a different distribution axis.

### 23.2. Distinguishing Refine from Reshard

**Refine shard key** and **reshard collection** differ in prerequisites and impact:

- Refine extends the existing shard key pattern per MongoDB rules (typically appending fields to the current key).
- Reshard rebuilds data placement under an entirely different shard key.

Never treat the two terms as interchangeable APIs. Check server-version support, limits, index prerequisites, and business impact.

### 23.3. Prerequisites for Success

Before resharding:

1. Validate the new shard key's measured distribution.
2. Confirm queries can target it efficiently.
3. Verify unique constraints remain satisfiable.
4. Provision enough storage for temporary data and indexes.
5. Account for network and write amplification.
6. Ensure backups/restores and version-compatible procedures are ready.
7. Define SLOs and pause/error handling.
8. Plan post-change validation.

### 23.4. Not Reversible in One Second

Once resharding completes, returning to the old key is a **brand-new data movement operation**, not flipping a boolean. Design rollback/forward-fix plans around real cluster state rather than promising instant reversal.

## 24. Managing Risk During Migrations

### 24.1. Conflicting Operations

During migrations or rebalancing, avoid unnecessary concurrent changes:

- Concurrent resharding and major schema migrations.
- Index builds across multiple collections.
- Massive bulk imports.
- Disk/network-heavy maintenance jobs.
- Aggressive backups/snapshots throttling storage.
- Continuous routing or zone policy edits.

Not every combination is strictly forbidden by MongoDB, yet overlapping heavy changes complicate diagnostics, block rollbacks, and risk SLO breaches.

### 24.2. Long-Running Transactions

Long transactions or operations complicate migration commit and cleanup phases. Track transaction duration, retries, write conflicts, and concurrent DDL.

### 24.3. Migration Throttling Has Trade-Offs

Throttling migrations protects p99 latency while prolonging data skew and capacity pressure. Speeding up migrations shortens drain time while raising disk and network contention.

Balance the trade-off explicitly:

~~~text
Migration speed
       vs
Application SLO
       vs
Disk/IOPS headroom
       vs
Operation window
~~~

### 24.4. Backups and Restores

Follow backup policies before any topology change, ensuring backups stay topology-consistent. In a sharded cluster, full recovery requires coordinated shards and config servers—never treat independent host snapshots as cluster-consistent merely because all files exist.

### 24.5. Security

Adding a shard adds hosts, volumes, network paths, and secrets. Every new component requires:

- TLS and internal authentication.
- Proper network ACLs.
- Host hardening.
- Secret/certificate rotation.
- Monitoring and audit access.
- Backup encryption.

Scaling in requires revoking old host credentials so orphaned access paths never remain.

## 25. Typical Incidents and Responses

| Symptom | Likely Cause | Response |
| --- | --- | --- |
| Shard added yet data does not move | Balancer, zones, key/placement rules | Inspect status and placement policies |
| One shard stays hot | Hot key, hot tenant, scatter-gather | Analyze shard key and query mix |
| Secondary initial sync very slow | Network/disk/source load | Monitor lag, IOPS, and oplog window |
| Adding member destabilizes majority | Poorly planned votes/quorum/elections | Review `rs.conf()` and HA plan |
| Migration causes high p99 | Copy/catch-up/I/O contention | Monitor donor/recipient; throttle safely |
| Disk stays full after move | Orphan cleanup / index / filesystem behavior | Monitor cleanup; never delete manually |
| Range refuses to move | Jumbo/unsplittable or zone constraints | Inspect keys and logs per version |
| `removeShard` stuck `ongoing` | Incomplete drain, unsharded/primary deps | Inspect blockers and progress |
| `removeShard` hits low capacity | Surviving shards lack headroom | Pause shrink and add capacity |
| Zone's only shard being removed | No valid destination remains | Adjust zone capacity per policy |
| Stale reads rise after adding secondary | Read preference / replication lag | Tune consistency and routing |
| Write p99 rises after adding member | Replication/quorum/I/O pressure | Check majority and initial sync load |
| Backups cover only old shards | New shard omitted from backup config | Update backup coverage |
| Sharded queries slow post-add | Scatter-gather or network fan-out | Measure targeting and query plans |
| Cluster CPU low yet API times out | Pool wait, network, or one slow shard | Check driver + per-shard metrics |
| Primary lost during rolling maintenance | Lost quorum or shared failure domain | Halt changes and restore HA |
| Changing shard key did not help | Query mismatch or residual skew | Compare against baseline post-reshard |
| Balancer stopped and forgotten | Cluster stops rebalancing/draining | Add alerts, ownership, and runbook |
| Premature decommissioning | Missing ranges or metadata dependency | Always wait for MongoDB `completed` |
| Instance scaled down too small | Cache/I/O pressure, slow failovers | Capacity test and roll back |

## 26. Case Study: Oversized Tenant Overloading One Shard

### 26.1. Current State

~~~text
Shard A: 70% requests, 60% data
Shard B: 15% requests, 20% data
Shard C: 15% requests, 20% data

SLO:
  Search p99 <= 400 ms

Actual:
  Search p99 = 850 ms at peak
~~~

### 26.2. Proposal A: Add Shard D

Upside: adds aggregate capacity. However, if the shard key is **`tenantId` hashed** and tenant `t001` generates 70% of requests, all `t001` writes still hit a single hash value/range.

Result: adding D helps peer data while failing to cool down Shard A.

### 26.3. Proposal B: Vertically Scale Shard A

Relieves immediate saturation, yet creates **asymmetric infrastructure** and hits hardware limits if `t001` keeps growing.

### 26.4. Proposal C: Redesign the Shard Key

Split `t001` events using an additional high-cardinality field, while evaluating:

- How many shards per-`tenantId` queries will touch.
- Index changes needed.
- Unique constraint impact.
- Zone and data residency rules.
- Volume of data requiring migration.
- RPO/RTO and backup readiness.

### 26.5. Making the Right Decision

Benchmark candidates against concrete targets:

- Lower p99 at offered peak.
- Higher real throughput.
- No abnormal spike in errors or retries.
- Acceptable cost.
- Preserved HA and backups.

Never choose an option merely because shard boxes look "even" on a diagram.

## 27. Case Study: Shrinking from Four Shards to Three

### 27.1. Current State

~~~text
4 shards, ~600 GB data/indexes each
Total ~2.4 TB
Each shard capacity: 900 GB
~~~

After removing one shard, idealized placement is:

~~~text
3 shards, ~800 GB each
~~~

On paper, 100 GB remains per shard. Yet with a 20% headroom policy, temporary migration overhead plus 3 months of growth make the plan unsafe.

### 27.2. Mistake

The team shuts down Shard D because it has "the fewest requests" without checking zones, unsharded collections, or database primaries. Cluster state breaks and apps fail.

### 27.3. Right Approach

1. Capacity planning across data, indexes, IOPS, and growth.
2. Check zones.
3. Inventory database primaries and unsharded collections.
4. Verify backups and restore readiness.
5. Initiate `removeShard` via supported API.
6. Monitor draining, migrations, and latency.
7. Clear blockers.
8. Wait for `completed`.
9. Decommission after sign-off.
10. Run post-change soak monitoring.

### 27.4. Case Takeaway

Scale-in combines **data movement + reduced headroom + topology change**—not merely saving one VM's bill. If risk and restore costs outweigh savings, defer shrinking.

## 28. Pre-Change Operational Checklist

### 28.1. Data

- Inventory of collections and shard keys.
- Data/index distribution per shard.
- Hot tenant and key distribution.
- Zone and range placement rules.
- Assessment of jumbo/unsplittable ranges.
- Query targeting analysis.

### 28.2. Infrastructure

- Disk, IOPS, network, and CPU/RAM headroom.
- Healthy replica set majorities and quorum.
- Sufficient oplog window.
- Healthy `mongos` and CSRS.
- Compatible versions and FCV.
- Valid TLS, auth, and secrets.

### 28.3. Backups and SLOs

- Latest backup usable.
- Restore drill verified.
- Approved RPO/RTO.
- Baseline p95/p99 latency and error rates.
- Explicit stop conditions.
- Staffed on-call incident responder.

### 28.4. Plan

- Assigned change owner and maintenance window.
- Version- and deployment-accurate commands.
- Phased execution order with per-phase verification.
- Rollback / forward-fix strategy.
- Dashboards and alerts ready.
- Stakeholder communication sent to app owners.

## 29. Post-Change Verification Checklist

### 29.1. Topology

- Shard and member counts match plan.
- All replica sets healthy.
- Primaries, elections, and quorum stable.
- No unintended legacy hosts left in routing or monitoring.

### 29.2. Data Placement

- Ranges and collections satisfy zone policies.
- Data skew matches targets.
- No unresolved migration failures.
- `removeShard` confirmed `completed` if scaling in.
- No lingering unsharded or database primary blockers.

### 29.3. Business Functionality

- Search, booking, write, and transaction smoke tests pass.
- Tenant and regional data remain properly accessible.
- Application p95/p99, error rates, and throughput meet SLOs.
- Read/write consistency policies remain intact.

### 29.4. Operations

- Backup/restore coverage updated.
- Monitoring and alerts cover any new shards.
- Secrets/certificates of retired shards revoked.
- Cost and capacity forecasts updated.
- Change record archives bytes moved, duration, issues, and lessons learned.

## 30. Hands-On Exercises

### Exercise 1 — Distinguishing Scaling Methods

A three-member replica set is running out of disk on every data-bearing node. Will adding a secondary reduce how much data each node stores? Compare with vertical storage scaling and sharding.

### Exercise 2 — Write Scaling

Two secondaries are added to a replica set. Do application writes automatically split across three primaries? Describe the impact on HA and read capacity.

### Exercise 3 — Inventory

Draft a checklist of metrics and topology details to capture before adding a shard: FCV, roles, zones, shard key, disk, network, backups, p99, and replication.

### Exercise 4 — Majority

Explain why changing voting member count alters majority quorum and elections. Does a non-voting secondary count toward majority votes?

### Exercise 5 — Initial Sync

A replica set holds 1.2 TB of data and you add a new secondary. Which factors prolong initial sync and stress the sync source?

### Exercise 6 — Read Scaling

An app always uses `primary` read preference. Will adding a secondary reduce read load on the primary? If switched to `secondaryPreferred`, what consistency trade-offs arise?

### Exercise 7 — Add Shard

List preconditions required before calling `addShard`: networking, TLS/internal auth, replica set health, storage, backups, monitoring, zones, and SLOs.

### Exercise 8 — Balancer

Shard D was added, yet 24 hours later most data still sits on A/B/C. What root causes would you investigate before attempting any manual move?

### Exercise 9 — Moving 600 GB

Calculate the ideal transfer time for 600 GB at 50 MB/s effective throughput (decimal units). Why does real migration take longer?

### Exercise 10 — Donor and Recipient

Describe the main conceptual phases of a range migration. Why can temporary data remain on the donor after ownership transfers?

### Exercise 11 — Data vs. Heat Balance

Three shards each hold 400 GB, yet Shard A receives 80% of write traffic. Can the cluster be called balanced? Which metrics should you add?

### Exercise 12 — Hot Tenant

Tenant `t001` drives 70% of writes; the shard key is hashed `tenantId`. Why won't adding a shard split `t001`'s traffic?

### Exercise 13 — Monotonic Shard Key

Events are sharded by increasing `createdAt`. Where do new writes create a hotspot, and how would you re-evaluate key design?

### Exercise 14 — Scatter-Gather

Adding shards increases shard count, yet queries omit the shard key. Why can performance actually worsen?

### Exercise 15 — Jumbo / Unsplittable

The balancer repeatedly fails to migrate one huge range. Describe how to inspect shard key cardinality, zones, and logs without manually editing metadata.

### Exercise 16 — Zone Policy

Zone VN contains only Shard A, and the team wants to remove A. What changes to zone capacity and data residency rules are required before draining?

### Exercise 17 — Remove Shard

Why can't you simply shut down Shard D when shrinking from four shards to three? Describe the draining state.

### Exercise 18 — Unsharded Data

A shard serves as a database primary and holds unsharded collections. Why aren't sharded range migrations enough to remove that shard?

### Exercise 19 — Capacity Shrink

A cluster has 4 × 600 GB of data/indexes, with 900 GB capacity per shard. Target is three shards. Calculate ideal distribution and evaluate headroom and risk.

### Exercise 20 — Scale-Down Triage

After scaling in, p99 latency spikes, free disk is tight, and replication lag grows. What priority actions should you take? Should you delete the old shard immediately?

### Exercise 21 — `fsync` / Backups

Why must backups and restores be verified before topology changes? If each shard is backed up at a different timestamp, is that a consistent sharded cluster backup?

### Exercise 22 — SLOs

Set guardrails for p95, p99, errors, disk headroom, and replication lag for a multi-hour migration. When should you pause?

### Exercise 23 — Stop Balancer

An operator ran `stopBalancer` and forgot to turn it back on. How does this affect rebalancing and draining?

### Exercise 24 — Rollback

200 ranges moved to a new shard before network issues surfaced. Why can't you call `removeShard` expecting an instant "zero-cost rollback"?

### Exercise 25 — Lab Seed

Run the Section 21 lab with 2,400 documents. Inspect tenant distribution, `currentBucket`/`proposedBucket`, and `trafficWeight`.

### Exercise 26 — Current Skew

Run the aggregation grouped by `currentBucket`. Which bucket is hottest? Why is document count insufficient to measure true load?

### Exercise 27 — Proposed Placement

Run the aggregation grouped by `proposedBucket`. Does synthetic load distribute more evenly? Which query-targeting trade-offs are not modeled?

### Exercise 28 — Data Movement Estimate

Count documents and `approxBytes` where `currentBucket` differs from `proposedBucket`. Why isn't this the true physical migration byte count?

### Exercise 29 — Scale-In Simulation

Simulate shrinking four buckets to three with `proposedBucket % 3`. Why does Bucket 0 overload? Propose a better balancing heuristic.

### Exercise 30 — Shard Diagnostics

On an authorized sharded staging cluster, use `sh.status`/`listShards` and monitoring to document topology, distribution, and migrations. Why must you never manually edit `config.chunks`?

### Exercise 31 — Resharding

Compare refining a shard key with `reshardCollection`. List constraints around indexes, query routing, uniqueness, disk space, versions, and migration risk.

### Exercise 32 — Node Decommissioning

Once MongoDB reports `removeShard` `completed`, what must be cleaned up across disks, credentials, certificates, monitoring, costs, and backup catalogs?

### Exercise 33 — Atlas vs. Self-Managed

List questions to verify before changing shard counts in MongoDB Atlas. Why won't compute auto-scaling fix a hot shard key?

### Exercise 34 — End-to-End Runbook

A four-shard system holds 5 TB, 30% traffic comes from one tenant, search p99 is 700 ms against a 400 ms SLO, and the team wants to add a shard. Write the full plan: root cause, key distribution, capacity, `addShard`, rebalancing, monitoring, error thresholds, backups, stop conditions, and post-change validation.

### Exercise 35 — Safe Cluster Scale-In

After query optimization, the team wants to shrink from five shards to four. Draft a 6-month capacity forecast, zone placement checks, `removeShard` draining runbook, unsharded collection moves, SLO thresholds, and decommission checks.

## 31. MongoDB References

- MongoDB Manual — [Sharding Overview](https://www.mongodb.com/docs/manual/sharding/).
- MongoDB Manual — [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/).
- MongoDB Manual — [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/).
- MongoDB Manual — [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/).
- MongoDB Manual — [Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/).
- MongoDB Manual — [Add Shards to a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/add-shards-to-shard-cluster/).
- MongoDB Manual — [Remove Shards from a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/remove-shards-from-cluster/).
- MongoDB Manual — [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/).
- MongoDB Manual — [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/).
- MongoDB Manual — [Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/).
- MongoDB Manual — [Add Members to a Replica Set](https://www.mongodb.com/docs/manual/tutorial/expand-replica-set/).
- MongoDB Manual — [Remove Members from Replica Set](https://www.mongodb.com/docs/manual/tutorial/remove-replica-set-member/).
- MongoDB Manual — [Initial Sync](https://www.mongodb.com/docs/manual/core/initial-sync/).
- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Backup Methods](https://www.mongodb.com/docs/manual/core/backups/).
- MongoDB Atlas — [Modify a Cluster](https://www.mongodb.com/docs/atlas/scale-cluster/).
- MongoDB Atlas — [Auto-Scaling](https://www.mongodb.com/docs/atlas/cluster-autoscaling/).

**Conclusion:** **Scaling up or down a MongoDB cluster is more than adding or removing machines.** Adding a **replica-set member** increases redundancy and can assist reads, yet never splits write load or dataset storage within a replica set. Adding a **shard** expands data distribution capacity, yet effectiveness depends on **shard keys, query targeting, zones, and the balancer**; **range migrations** consume network and disk I/O and require monitoring p95/p99, replication, and application errors. When **removing a shard**, you must **drain** all data and move unsharded collections/database primaries per version, waiting for MongoDB to confirm `completed` before decommissioning. If a hot key cannot split, **resharding** may be needed instead of adding shards. Every topology change demands **capacity planning, backups, stop conditions, monitoring, privilege checks, and post-change verification**; the ultimate goal is **valid data placement, adequate headroom, and services meeting SLOs both during and after data movement**.
