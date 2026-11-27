# Moving Data Between Shards and Monitoring Load Balancing in MongoDB

## 1. Context: when data is distributed across multiple shards

An application stores hundreds of millions of events in MongoDB. Instead of placing all documents on a single replica set, the system organizes data into a **sharded cluster** with multiple **shards**. Each shard is typically a replica set holding a portion of the data. **`mongos`** routers route queries using sharding metadata; the **config server replica set** stores configuration and range-ownership metadata.

As data grows, one shard may accumulate far more data than others, or a group of tenants/write keys may grow rapidly. MongoDB needs a way to **transfer ownership of shard key value ranges** from one shard to another to distribute data according to cluster policy.

In this lesson, we will cover:

1. How data is partitioned by **ranges/chunks**.
2. How the **balancer** decides on and executes data-range migrations.
3. How to distinguish **physical data transfer**, **ownership metadata commit**, and **orphan cleanup**.
4. Commands for observing the balancer, data distribution, and migration progress.
5. When to let **automatic balancing** run versus when to perform **manual moves**.
6. Effects of **shard keys, zones, jumbo ranges, skewed data, and hot shards**.
7. Workflows for monitoring, troubleshooting, and safe production operations.

**Distinguish right from the start:** balancing **data volume** does not automatically mean balancing **CPU, query counts, write counts, or latency**. A cluster with evenly distributed data sizes can still have one shard absorbing most of the traffic.

## 2. Components involved in data movement

### 2.1. Shards, `mongos`, and config servers

Conceptual diagram:

```text
             APPLICATION / MONGODB DRIVER
                       |
                       v
                 +-----------+
                 |  mongos   |
                 |  router   |
                 +-----------+
                    |     |
      Lookup meta   |     | Route queries
                    v     v
      +----------------+  +------------------------------+
      | Config Server  |  | Sharded Data                 |
      | Replica Set    |  |                              |
      |                |  | Shard A   Shard B   Shard C   |
      | Collection     |  |  RS A      RS B      RS C    |
      | ranges/zones/  |  |                              |
      | ownership      |  +------------------------------+
      +----------------+
```

Simplified roles:

- **`mongos`** receives requests, knows topology, and routes via metadata. Applications normally connect to `mongos` rather than picking target shards arbitrarily.
- **Shards** store documents belonging to the shard key ranges they own.
- **Config servers** store metadata on sharded collections, data ranges, current owning shards, and other configuration.
- **Balancer** is the mechanism managing range movement across shards to converge toward current policy distribution.

Task responsibilities may differ slightly across MongoDB versions. What matters is understanding that **ownership metadata** and **physical data on disk** do not always change instantaneously at the same moment.

### 2.2. The shard key governs partitioning

Suppose `shop.events` is sharded on:

```javascript
{ tenantId: 1, eventAt: 1 }
```

A document:

```javascript
{
  _id: "event-001",
  tenantId: "T01",
  eventAt: ISODate("2026-11-01T10:00:00Z"),
  type: "LOGIN"
}
```

is routed by its **shard key value**. Data is divided into **value ranges** in the shard key space, and those ranges are assigned to shards.

Never think “each tenant is a shard” or “each document is a chunk.” A shard can hold many ranges, and each range can contain millions of documents.

## 3. Ranges and chunks: the units the balancer cares about

### 3.1. Key intervals, not arbitrary record lists

With a simple key `{ customerId: 1 }`, visualize:

```text
   Ascending shard key space

MinKey |--------|-----------|-----------|---------| MaxKey
       A        K           T           Z
         R1         R2          R3         R4

Shard A: R1, R2
Shard B: R3
Shard C: R4
```

Each segment is a shard key **range**. In MongoDB docs and tooling, users also commonly encounter **chunk** to denote the managed/migrated range unit.

Simulated metadata example:

```javascript
{
  min: { customerId: "A" },
  max: { customerId: "K" },
  shard: "shardA"
}
```

Read this as: keys in the range **from `min` inclusive up to `max` exclusive** are owned by `shardA`. This is an **illustrative model**, not advice to manually create or edit documents in `config.chunks`.

### 3.2. Ranges can be empty, small, or huge

A range’s document count is not fixed. Two ranges with similar key-space spans can hold vastly different data volumes:

```text
Range A: customerId from A to K
  10 million documents

Range B: customerId from K to T
  15 thousand documents
```

Therefore, **counting ranges/chunks does not always reflect size or load**.

Modern MongoDB versions (especially from 6.0 onward) primarily use **data size imbalance** in routine balancing decisions rather than chunk counts alone. Exact field names and algorithms vary by version.

### 3.3. Compound shard keys

With:

```javascript
{ tenantId: 1, eventAt: 1 }
```

`min`/`max` are **documents with the exact key structure**, compared left-to-right. You cannot treat compound `min`/`max` bounds like a single plain integer.

A range might look like:

```javascript
{
  min: { tenantId: "T01", eventAt: MinKey() },
  max: { tenantId: "T02", eventAt: MinKey() }
}
```

This is a **logical boundary example**, not a claim that a real cluster has that exact range.

### 3.4. Logical units differ from physical disk footprint

When a range moves:

- Logical ownership transfers to the destination shard.
- The data copy on the source shard may take time to clean up.
- Observed disk usage may not drop immediately due to **range deletion, storage reuse, and storage engine file mechanics**.

Thus, after a range migrates successfully, do not jump to conclude it failed just because disk file size on the source shard has not shrunk yet.

## 4. What the balancer is and is not

The **Balancer** is the component of a MongoDB sharded cluster that maintains data-range distribution according to balancing and zone policies. It evaluates metadata/sizes, selects eligible transfers, and runs necessary migrations.

### 4.1. Primary goals

- Prevent one shard from holding vastly more data than others **when balancing is possible**.
- Distribute data when new shards join the cluster or datasets grow.
- Respect **zone constraints** defined for shard key ranges.
- Allow cluster storage capacity to scale out **incrementally**.

### 4.2. What the balancer does NOT guarantee

The balancer does **not** mean:

- Every shard always holds exactly 1/N of documents.
- Every shard always holds identical byte sizes.
- Every shard handles equal CPU and query counts.
- Every oversized range can always be split in all circumstances.
- Any arbitrary range can move to a shard outside its permitted zone.
- Source disk usage shrinks immediately post-migration.
- Zero impact on network, disk I/O, or latency.

### 4.3. When does data remain skewed even with the balancer enabled?

Examples:

1. New data concentrates in **one shard key region** not yet split into useful ranges.
2. The shard key has an **overly frequent value** that cannot split across shards.
3. **Zones** restrict where data is allowed to live.
4. A range is oversized or unsplittable; a **jumbo** condition may appear.
5. The cluster is busy with other migrations or the balancer is waiting on conditions.
6. Size skew has not crossed the threshold/criteria to trigger migration.
7. Connectivity, replica set, metadata, resource exhaustion, or migration rejection errors occur.

To diagnose, combine **balancer state, data distribution, metadata, and logs**, rather than looking at one boolean flag.

## 5. What steps does a migration go through?

When MongoDB decides to move a range from a **donor shard** (source) to a **recipient shard** (destination), the high-level model is:

```text
                        sharded cluster

    Donor shard (A)                         Recipient shard (B)
   +----------------+                      +----------------+
   | Range R data   | ------ copy ------>  | Copy of R      |
   | Currently ownsR|                      | Receiving R    |
   +----------------+                      +----------------+
            |                                      |
            |  Concurrent changes handled per      |
            |  migration protocol                  |
            |                                      |
            +------------+-------------------------+
                         |
                Sync / catch-up
                         |
             Commit ownership metadata
                         |
             R logically belongs to shard B
                         |
            Donor cleans up orphaned data
            via range deletion mechanism
```

### 5.1. Preparation phase

The balancer or admin command determines:

- The target collection namespace.
- The specific shard key range/chunk.
- Donor and recipient shards.
- Topology, zone compliance, and receiver readiness.

This is not “copying a database folder from machine A to B”; it must coordinate with metadata and sharding protocols.

### 5.2. Copy phase

The recipient receives the range’s data. While the application stays live, source data continues mutating; MongoDB tracks and applies concurrent changes so the destination qualifies to take ownership.

**Never assume migration time equals raw file copy time.** It is also affected by write workload, indexes, volume, network, and catch-up sync.

### 5.3. Catch-up and critical section

Near ownership handover, shards and metadata coordinate briefly to prevent both sides from believing they own the range simultaneously in an inconsistent way.

During brief phases, certain operations on the range may wait/pause briefly so ownership transfers cleanly. Exact mechanics and duration vary by MongoDB version and cluster state.

### 5.4. Metadata commit

Config server/cluster metadata updates so **the recipient becomes the shard owning the range**. `mongos` routers must learn the new metadata to route accurately; metadata refresh mechanics handle stale router caches.

Never alter metadata by manually editing documents in `config.chunks` or `config.collections`. Doing so corrupts topology consistency and makes data unreachable.

### 5.5. Post-move orphan cleanup

After ownership transfers, the donor retains old physical copies of the range until cleanup finishes. Copies no longer logically owned by that shard are called **orphaned documents**.

Key takeaways:

- Orphans do not mean business documents appear duplicated in queries through `mongos`.
- Physical storage on the donor may not shrink right away.
- Orphan cleanup and OS disk reclamation are asynchronous, not instant.
- Monitor range deletion status/metrics instead of manually deleting documents “suspected to be orphans.”

### 5.6. Does migration force the application to switch endpoints?

Normally the application keeps connecting to **`mongos`** via the sharded cluster URI. MongoDB updates metadata and routes to the new shard. Applications **do not** record “document O01 is on shard A” in business tables and update it after migration.

That is a major advantage of metadata-driven sharding, though operations may see brief latency shifts during migration or refreshes.

## 6. Setting up an appropriately scoped practice environment

This lesson includes **status-reading** commands and **data/placement-changing** commands. Use placement-changing commands only on a prepared **lab sharded cluster**, never on production without an approved plan.

### 6.1. Lab prerequisites

A proper environment includes:

- **Config server replica set**.
- At least **two shards** (typically separate replica sets).
- One or more **`mongos`** routers.
- Privileges to create databases/collections, shard collections, and manage the balancer when needed.
- Reliable hostnames/ports and secure authentication.

**You cannot build a range-migration lab on a standalone `mongod`.** If you only have standalone MongoDB locally, study the rest as conceptual diagrams and illustrative commands without running `sh.moveChunk()`.

### 6.2. Connecting to `mongos`

Hypothetical URI example:

```bash
mongosh "mongodb://localhost:27017"
```

Port 27017 applies only if your lab `mongos` listens there. In authenticated clusters, URIs require credentials and TLS; never embed passwords in examples or logs.

Verify the current node is `mongos`:

```javascript
db.adminCommand({ hello: 1 });
```

When connected to `mongos`, the response includes:

```javascript
{ msg: "isdbgrid" }
```

This is a **router role indicator**, not the entire response. `sh.*` helpers primarily apply in a `mongos` or supported router context.

### 6.3. Inspect actual shard names before writing commands

```javascript
db.adminCommand({ listShards: 1 });
```

Output lists shard IDs such as `shardA` and `shardB`. **Always use exact real shard names** from your cluster. Throughout this lesson, `shardA`/`shardB`/`shardC` are illustrative placeholders.

If only one shard exists, do not attempt moving ranges to a nonexistent `shardB`.

## 7. Sample dataset and shard key

We use database `sharding_lab265` and collection `events265`:

```javascript
const labDb = db.getSiblingDB("sharding_lab265");
const events = labDb.events265;
```

### 7.1. Run only on a new/empty collection

The snippet intentionally uses a dedicated collection name and checks for existing data:

```javascript
if (events.countDocuments({}) !== 0) {
  throw new Error(
    "events265 already has data; please use a new lab/collection"
  );
}
```

**Never run `drop()` on a collection holding real data** just to repeat an example. If you already used that collection earlier, pick a fresh lab database/collection.

### 7.2. Create the shard key index

Choose key:

```javascript
{ tenantId: 1, eventAt: 1 }
```

Create the supporting index:

```javascript
events.createIndex({ tenantId: 1, eventAt: 1 });
```

This is a **ranged** key by tenant then time. It clearly illustrates contiguous ranges, yet **does not guarantee even write distribution**, especially if most events come from one hot tenant with ever-increasing `eventAt`.

### 7.3. Shard the collection

Connect to `mongos` and run:

```javascript
sh.shardCollection(
  "sharding_lab265.events265",
  { tenantId: 1, eventAt: 1 }
);
```

Depending on MongoDB version/setup, enabling database sharding and collection prerequisites vary. Use the appropriate API for your deployment. Do not re-run `shardCollection` if the namespace is already sharded.

### 7.4. Insert a small sample to observe

```javascript
const rows = [];
const tenants = ["T01", "T02", "T03", "T04"];

for (let i = 0; i < 800; i++) {
  const tenantId = tenants[i % tenants.length];
  rows.push({
    _id: "evt-" + String(i).padStart(5, "0"),
    tenantId,
    eventAt: new Date(Date.UTC(2026, 10, 1 + (i % 10), i % 24)),
    type: i % 3 === 0 ? "VIEW" : "CLICK",
    payload: { source: "lab", sequence: i }
  });
}

events.insertMany(rows);
```

This dataset has **only 800 small documents**. It suffices for learning syntax, **not for guaranteeing MongoDB creates multiple ranges or triggers migrations**. If `sh.status()` shows everything on one shard, do not conclude the balancer is broken. Manual move testing depends on existing ranges.

## 8. Viewing the overall picture with `sh.status()`

### 8.1. Command

In `mongosh` connected to `mongos`:

```javascript
sh.status();
```

Depending on version, you can run:

```javascript
sh.status(true);
```

for verbose detail if supported. Output typically shows the shard list, balancer state, databases, sharded collections, shard keys, range distributions, and zones.

### 8.2. How to read it

Look for sections such as:

```text
shards
  shardA
  shardB

balancer
  enabled / running / ...

databases
  sharding_lab265
    events265
      shard key: { tenantId: 1, eventAt: 1 }
      ranges by shard: ...
```

The labels above are a **schematic**, not a verbatim copy of every MongoDB version’s exact output.

### 8.3. Mind the units in the output

If the tool reports:

```text
Shard A: 7 chunks
Shard B: 3 chunks
```

you only know **range/chunk counts**, not data volume or traffic. It might be:

```text
Shard A: 7 ranges, total 250 MB
Shard B: 3 ranges, total 300 MB
```

In modern MongoDB, that may **not be a bad distribution** by data volume.

### 8.4. Compare two measurements

When checking the balancer:

```javascript
sh.status();
// After an observation window with data changes:
sh.status();
```

Record **timestamps**, **per-shard range counts/sizes**, and **balancer state**. Seeing no change over a brief interval does not automatically prove it is stuck abnormally.

## 9. Checking whether the balancer is enabled and active

### 9.1. `sh.getBalancerState()`

```javascript
sh.getBalancerState();
```

This helper queries the **enabled/disabled state** of the balancer. It **does not tell you** whether a migration is currently active or whether balance has converged.

A balancer can be enabled yet idle because:

- There is no data imbalance exceeding thresholds to move.
- Current time is outside the configured balancing window.
- It is waiting on prerequisites or competing operations.
- Zones or unmovable ranges block transfers.

Thus, **`true` does not mean data is migrating every second**.

### 9.2. `sh.isBalancerRunning()`

On supported environments/versions:

```javascript
sh.isBalancerRunning();
```

This helper gives additional balancer activity status. Exact semantics and format vary by version, and it **does not replace** data distribution metrics or migration history.

### 9.3. Combine multiple signals

Reasoning table:

| Balancer enabled? | Signs of active run? | Data distribution | Initial interpretation |
|---|---|---|---|
| Yes | No | Already matches policy | Likely nothing to move |
| Yes | Yes | Currently skewed | Likely balancing incrementally |
| Yes | No | Currently skewed | Check thresholds, zones, window, errors |
| No | No | Currently skewed | No auto-balancing while disabled |
| Yes | Yes | Still has a hot shard | Balancer balances bytes, not query load |

Never treat these rows as absolute decision rules; confirm with real metrics.

### 9.4. Avoid changing config before knowing the cause

In most clusters, the balancer stays enabled by default as normal operations. **Do not turn off the balancer just because one migration slowed a query.** Verify whether the load shift truly came from migrations, the shard key, or another cause.

## 10. Observing per-shard document and storage distribution

### 10.1. `getShardDistribution()`

For a sharded collection in `mongosh`:

```javascript
db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

This helper prints per-shard collection distribution stats, depending on MongoDB version and metadata support, such as estimated/observed sizes and document counts.

**This is an inspection tool**, not a reason to delete “excess” data by intuition. Figures may be estimates affected by orphans or collection timing; read the version-specific output notes.

### 10.2. `sh.getShardedDataDistribution()`

On supported MongoDB versions:

```javascript
sh.getShardedDataDistribution();
```

This helper shows sharded data distribution by namespace and shard, potentially including **owned data** and **orphaned data** stats.

Sample output shape (**illustrative figures**):

```text
Namespace: sharding_lab265.events265

shardA:
  owned data: 400 MB
  orphaned data: 20 MB

shardB:
  owned data: 410 MB
  orphaned data: 0 MB
```

Key takeaways:

- **Owned** figures reflect data the shard legitimately owns per cluster tools.
- **Orphaned** figures should not be counted as live business data owned by that shard.
- Two shards with nearly equal owned data can still differ in physical disk size due to copies awaiting cleanup.

**Do not assume every version provides this helper or identical field names.** Where unavailable, use `sh.status()`, monitoring metrics, and deployment-supported admin tools.

### 10.3. Structured snapshots for tracking

Instead of screenshots:

```javascript
const observation = {
  observedAt: new Date(),
  balancerEnabled: sh.getBalancerState(),
  // Record only metrics actually supported by your current version.
};

printjson(observation);
```

Monitoring scripts can emit timestamped JSON using supported commands/metrics. In production, use an observability platform with history, alerting, and RBAC rather than ad-hoc manual commands without audit trails.

## 11. `balancerCollectionStatus`: is the collection balanced?

On supported MongoDB versions, the helper:

```javascript
sh.balancerCollectionStatus(
  "sharding_lab265.events265"
);
```

reports whether a collection **complies with balancing policies**, along with hints if it is out of compliance.

### 11.1. Do not interpret “compliant” as “zero performance issues”

A collection rated compliant with balancer policy can still suffer from:

- An extremely hot tenant.
- CPU-heavy scatter-gather queries across all shards.
- Missing indexes.
- Weaker hardware on one shard.
- Orphaned records awaiting cleanup.
- Replication lag.

Balancer compliance pertains to **policy-compliant data placement**, not an overall performance bill of health.

### 11.2. If the helper is unavailable

Do not assume:

```javascript
sh.balancerCollectionStatus(...);
```

exists on every MongoDB version. If unsupported, inspect via `sh.status()`, data distribution stats, and metrics supported by your server version.

## 12. Tracking migration history

### 12.1. Why is history needed?

A `sh.status()` snapshot only shows **right now**. To learn:

- Which ranges moved?
- From which shard to which shard?
- When did migrations start and finish?
- Were there errors, retries, or unusually long durations?

we need history and logs.

### 12.2. `config.changelog`

In certain MongoDB versions/configs, `config.changelog` records sharding admin events, including balancer/migration events.

**Read-only** query to inspect:

```javascript
const cfg = db.getSiblingDB("config");

cfg.changelog.find({
  what: /moveChunk|moveRange|balancer/i
}).sort({ time: -1 }).limit(20);
```

Caution:

- **Event names and log schemas vary** across versions.
- Not every migration emits the exact `what` patterns shown above.
- Never treat `config.changelog` as a stable API for long-term business software.
- **Never edit, delete, or insert manually** in `config`/metadata collections.

### 12.3. `config.actionlog` and server logs

Some deployments also record balancer round details in `config.actionlog` or component logs:

```javascript
cfg.actionlog.find().sort({ time: -1 }).limit(20);
```

This collection does not always exist or keep a stable schema. For deep troubleshooting, **server logs** from `mongos`, config servers, and shards are far more reliable than guessing unstable metadata fields.

### 12.4. Correlating history with infrastructure metrics

If latency spikes:

```text
10:00  Balancer starts migration
10:03  Network throughput rises
10:05  Shard A disk I/O rises
10:06  Application p99 latency rises
10:12  Migration completes
10:14  Latency drops
```

This is a **correlation to verify**, not absolute proof that migration was the root cause. Application traffic may also have spiked simultaneously. Combine read/write metrics, slow queries, indexes, replication lag, and migration status.

## 13. Moving a range manually with `sh.moveChunk()`

### 13.1. When should you even consider it?

**Normally let the balancer manage balancing.** Manual moves are useful for:

- Labs to understand ownership ranges.
- Planned operations after verifying target shard, zones, and capacity.
- Specific imbalance remediation per MongoDB version guidance.

Never treat `moveChunk` as a business API to route individual orders or pick shards per insert.

### 13.2. Helper syntax

In `mongosh` on supported versions:

```javascript
sh.moveChunk(
  "database.collection",
  { shardKeyField: someValue },
  "destinationShardName"
);
```

Example **for lab use only**, after confirming the collection has a range on a source shard and a valid target shard:

```javascript
sh.moveChunk(
  "sharding_lab265.events265",
  {
    tenantId: "T02",
    eventAt: ISODate("2026-11-02T00:00:00Z")
  },
  "shardB"
);
```

Meaning:

- Namespace identifies the sharded collection.
- The second argument is a **point in the shard key space** locating the range containing that point—not a full document.
- `"shardB"` is the **destination shard ID**, matching the cluster’s actual shard list.
- The command asks MongoDB to **move the entire range/chunk containing that shard key**, not just that single document.

### 13.3. Checks before running

1. Connected to **`mongos`**, not directly to a shard replica set by mistake.
2. Namespace is actually sharded on the expected key.
3. Destination shard exists and is healthy.
4. The selected range currently lives on a different shard from destination.
5. Zone policies **permit** the range on the destination.
6. Sufficient disk/network/replication headroom exists to receive the data.
7. Latency impact and error handling are accounted for.

If a small collection has only one range, moving that range moves **the entire small collection** to the other shard; it **does not create a 50/50 split**. Never use a single `moveChunk` as a substitute for shard key/range design.

### 13.4. Status after the command

Once the command reports migration completion:

```javascript
sh.status();

db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

Output reflects transferred range ownership. However, orphans/physical storage on the donor **may not be cleaned up yet**. Continue monitoring if needed.

### 13.5. Do not run bulk `moveChunk` loops casually

A loop calling `moveChunk` across hundreds of ranges can:

- Saturate network and disk.
- Contend with the balancer.
- Spike latency.
- Accidentally move data contrary to zones/goals.
- Be hard to undo if automation picks the wrong bounds.

For large-scale rebalancing, rely on **balancer policies and deployment workflows**, limiting manual moves to reviewed runbooks.

## 14. Moving explicit ranges and version differences

In MongoDB, both **chunk** and **range** appear in docs and operations. Some versions provide commands/helpers for **range migration** with explicit `min`/`max` bounds; interfaces evolve, expand, or restrict across versions.

Never guess a `moveRange` command from another version’s docs and run it on production. If explicit `min`/`max` control is needed:

1. Identify exact **MongoDB server and `mongosh` versions**.
2. Verify commands/helpers supported by that version.
3. Specify full `min`/`max` bounds matching the **shard key index and BSON types**.
4. Verify zone constraints.
5. Test on a production-like lab cluster.

For learning basic mechanics, `sh.moveChunk()` with a shard key point is clear; **do not view it as replacing all modern balancer functions**.

## 15. Stopping/starting the balancer: understand impact first

### 15.1. Cluster-wide control

In `mongosh` on supported clusters:

```javascript
sh.stopBalancer();
```

and:

```javascript
sh.startBalancer();
```

These are **operational state changes**, not read-only queries. Never run them in production without approval.

### 15.2. Do not equate “stopping the balancer” with “freezing all writes”

While the balancer is stopped:

- Applications still read and write normally on the shards owning data.
- New data growth can let distribution drift increasingly skewed.
- Automatic range migrations pause per control state.
- An in-flight migration may take time to finish before reaching a clean stopped state.

**Stopping the balancer does not turn the cluster into a standalone database**, nor is it a “freeze all data” switch.

### 15.3. Re-enabling after a maintenance window

If stopped per an approved runbook, re-enable and verify:

```javascript
sh.startBalancer();
sh.getBalancerState();
sh.isBalancerRunning();
sh.status();
```

A successful command return does not replace watching the cluster converge toward desired balance.

### 15.4. Balancing windows for diurnal traffic

Some deployments configure a **balancer window** restricting when balancing runs. Window sizing must fit real traffic:

- If data grows rapidly all day, too short a window builds a huge migration backlog.
- Balancing only during off-peak hours reduces direct impact on daytime workloads.
- Verify system timezone and window rules for your server version.

Never edit `config.settings` or metadata directly with manual CRUD to “schedule” balancing when the deployment provides supported APIs/procedures.

## 16. Disabling/enabling balancing for a single collection

MongoDB provides helpers on supported versions:

```javascript
sh.disableBalancing(
  "sharding_lab265.events265"
);
```

and:

```javascript
sh.enableBalancing(
  "sharding_lab265.events265"
);
```

### 16.1. Different scopes

| Operation | Scope |
|---|---|
| `sh.stopBalancer()` | Cluster-wide automatic balancing per control mechanism |
| `sh.startBalancer()` | Enables cluster-wide automatic balancing |
| `sh.disableBalancing(ns)` | Pauses automatic balancing for the specified namespace |
| `sh.enableBalancing(ns)` | Re-enables automatic balancing for the specified namespace |

**Do not treat disabling collection balancing as locking all admin operations.** It does not make data immutable, nor does it necessarily block manual moves across all versions.

### 16.2. Reasons for temporary use

- Executing a documented migration or backup runbook.
- Limiting churn on a specific collection briefly.
- Isolating a variable during performance troubleshooting.

Always **restore desired balancing state** afterward and monitor. Never leave a fast-growing collection with balancing disabled indefinitely due to a forgotten test.

## 17. Zone sharding: not every range can go to every shard

### 17.1. Zones define placement policies

**Zones** bind one or more shards to a placement group and assign shard key ranges to that zone.

Business examples:

- APAC data must stay on APAC shards.
- EU data must stay on EU shards.
- Certain tenants must live on dedicated hardware per policy.

Diagram:

```text
Range belonging to zone APAC
           |
           +-- Shard A (zone APAC)  Eligible
           |
           +-- Shard B (zone APAC)  Eligible
           |
           +-- Shard C (zone EU)    Ineligible per policy
```

A cluster with zone policies may intentionally remain uneven across **all shards** because data must obey placement rules.

### 17.2. Illustrative zone configuration example

Suppose **another** collection has shard key:

```javascript
{ region: 1, createdAt: 1 }
```

Zone admin commands (illustrative only; **do not run directly unless the collection and shards exist**):

```javascript
sh.addShardToZone("shardA", "APAC");

sh.updateZoneKeyRange(
  "geo_lab.events",
  { region: "APAC", createdAt: MinKey() },
  { region: "APAC", createdAt: MaxKey() },
  "APAC"
);
```

Note: with shard key `region` then `createdAt`, a `min`/`max` pair like above illustrates an interval **within one region**; covering all keys of a region without overlapping zones must follow exact BSON shard key ordering. In real deployments, compute bounds accurately and verify zone configuration.

### 17.3. Zones can explain storage skew

Suppose:

```text
Shard A + B: zone APAC, total 5 TB
Shard C:     zone EU,   total 1 TB
```

If policy forbids APAC data moving to C, C having plenty of free space **does not mean the balancer is broken**. It is respecting placement constraints.

### 17.4. Zones do not fix hot tenants automatically

If one tenant generates 90% of APAC traffic and the shard key fails to distribute that tenant’s data, the balancer hits limits even with many APAC shards. Fixes require **changing the shard key design, access patterns, or data model**, not adding more zone tags.

## 18. Jumbo ranges: why are some ranges hard to move?

### 18.1. Concept

A range can become **oversized or hard to split**, commonly described as **jumbo** in sharding contexts. Causes include shard key distribution, many documents sharing the exact same shard key value, or inability to pick split points.

Example:

```text
Collection sharded on { country: 1 }

95% of documents have country = "VN"
5% belong to other countries
```

If a massive number of documents share the exact key value `"VN"`, the cluster cannot split them into multiple distinct ranges **using `country` alone**. That dataset forms a huge chunk that resists balancing.

### 18.2. Consequences

- Data stays skewed despite an enabled balancer.
- Migrations may stall or fail.
- Warnings about range/chunk size or jumbo status may appear in logs/metadata.
- The shard holding the massive data or request load is not relieved as expected.

### 18.3. Do not “fix” by forcing repeated moves

Some MongoDB versions offer special options/commands for moving jumbo or oversized ranges. Misusing them triggers heavy load, long transfer times, and operational risk.

Never run forced moves simply because `sh.status()` shows one shard is larger. First check:

1. Does the shard key have enough distinct values?
2. Is the range physically huge, or merely hot in traffic?
3. Can the shard key model be changed appropriately?
4. Are zone constraints blocking moves?
5. Are disk/I/O headroom and a maintenance window available?

### 18.4. A key that “looks good on paper” may still fall short

`{ country: 1 }` has few distinct values; `{ tenantId: 1 }` skews if one tenant dominates; monotonic `{ createdAt: 1 }` funnels new writes into one end.

A suitable compound or hashed key improves distribution while **trading off** targeted queries, range queries, colocation, and zone policies. Design shard keys around **both data growth and access patterns**, not merely chunk count.

## 19. Balancer balances bytes, yet queries may still run hot

### 19.1. Equal storage yet unequal QPS

Suppose:

```text
Shard A: owned data 500 GB, 15,000 queries/s
Shard B: owned data 490 GB,    800 queries/s
Shard C: owned data 510 GB,    750 queries/s
```

The balancer views data distribution as fairly balanced, yet Shard A remains a bottleneck.

Possible causes:

- A hot tenant resides mainly on Shard A.
- Queries repeatedly target one shard key band.
- Shard A lacks an index or has divergent indexes.
- Shard A has weaker hardware.
- Scatter-gather queries or aggregations distribute work unevenly.
- Chunk placement is balanced by bytes, not by operations.

### 19.2. Monitor the workload too

Never inspect `sh.status()` alone. Track:

- CPU per shard/replica set.
- Disk IOPS, read/write latency, free space.
- Inter-shard network throughput.
- Operation counts, query latency (p95/p99).
- Replication lag and write concern waits.
- Slow queries and `explain()` for key query patterns.
- Owned/orphaned bytes per collection.
- Migration rate, failure rate, and duration.

### 19.3. Scatter-gather is a routing issue, not just byte distribution

Suppose a collection is sharded on:

```javascript
{ tenantId: 1, eventAt: 1 }
```

A query filtering by `tenantId` and an `eventAt` window can route selectively, unlike a query filtering only on `type: "CLICK"` without the shard key.

If queries routinely omit the shard key, `mongos` fans out to many shards. Moving ranges via the balancer never turns a scatter-gather query into a targeted one.

## 20. When a new shard is added, does data move immediately?

### 20.1. Adding capacity does not equal using capacity immediately

When adding `shardC` to an existing A/B cluster:

```text
Before:
  shardA: 600 GB
  shardB: 580 GB

Right after adding shardC:
  shardA: 600 GB
  shardB: 580 GB
  shardC:   0 GB
```

This is **completely normal right after adding a shard**. The balancer must evaluate and migrate eligible ranges under live conditions. It does not instantly copy 1/3 of data to the new shard the moment `addShard` returns.

### 20.2. Track progress over time

Across observation checkpoints:

```text
Time      | Owned A | Owned B | Owned C
----------+---------+---------+--------
T0        | 600 GB  | 580 GB  | 0 GB
T1        | 540 GB  | 530 GB  | 110 GB
T2        | 425 GB  | 420 GB  | 335 GB
T3        | 395 GB  | 390 GB  | 395 GB
```

Numbers are **illustrative**, not a speed prediction. Actual speed depends on data, movable range counts, zones, network, I/O, and balancer state.

### 20.3. Do not declare a “bug” from a single snapshot

If the new shard is still empty after 30 seconds, that does not prove balancing failed. Verify:

- Whether the balancer is enabled or disabled.
- Whether the collection is sharded or unsharded.
- Whether zones exclude the new shard.
- Whether enough movable ranges exist.
- Whether migration errors appear in logs.
- Whether imbalance crosses balancer thresholds.

## 21. Draining a shard and moving data off a shard

Another goal is **removing a shard**. When a shard enters MongoDB’s remove/drain workflow, the cluster must migrate all owned data to remaining shards before removal completes.

### 21.1. Draining differs from normal balancing

Normal balancing adjusts distribution. **Draining** evacuates all eligible data off the departing shard.

```text
Shard A: continues serving
Shard B: continues serving
Shard C: draining state
           |
           v
       Data migrates gradually to A/B
           |
           v
       Remove-shard preconditions satisfied
```

### 21.2. Never just shut down a shard and call it done

Shutting down a shard before data migrates cleanly and metadata updates makes that shard’s slice of data inaccessible.

When removing a shard:

- Confirm remaining cluster capacity is sufficient.
- Confirm eligible destination shards exist for all zones.
- Monitor drain progress and remaining chunks/data.
- Handle unsharded collections or special configurations per your version’s procedure.
- Decommission infrastructure only after the admin command reports completion and verification passes.

### 21.3. Never confuse cluster shrinking with backup/restore

Draining transfers data ownership between shards; it does not replace backups. Operational mistakes during draining can still cause outages. Maintain recovery plans and appropriate change windows.

## 22. Special constraints for sharded collections

### 22.1. Unsharded collections

An unsharded collection lacks multi-range chunk distribution. Sitting on one shard does not prove the balancer is broken.

Modern MongoDB versions offer separate placement controls and **`moveCollection`** for unsharded collections; that is distinct from chunk/range migrations on a **sharded collection**.

### 22.2. Hashed shard keys

If a collection is sharded on:

```javascript
{ tenantId: "hashed" }
```

ranges partition the **hash value space** of the shard key. The aim is spreading key values, not keeping alphabetical `tenantId`s together.

When performing manual moves, never guess `min`/`max` bounds from alphabetical `tenantId` strings. Use supported helpers/metadata and understand hashed key routing.

### 22.3. Compound hashed keys

Example:

```javascript
{ region: 1, tenantId: "hashed" }
```

combines a zone/range-friendly prefix field with a hashed component. However, hashed keys, unique indexes, range splitting, and targeted queries carry version-specific rules. Never modify shard keys directly in production without evaluating full impact.

### 22.4. Resharding vs. chunk migration

**Chunk/range migration** moves data between shards **while keeping the collection’s shard key unchanged**.

**Resharding** changes partitioning to **a different shard key**. It is a much heavier operation with its own mechanisms and prerequisites.

```text
Migration:
  shard key unchanged
  range R: shard A -> shard B

Resharding:
  old shard key { tenantId: 1 }
              ->
  new shard key { tenantId: 1, eventAt: 1 }
  reorganizes distribution under the new key
```

Never use `sh.moveChunk()` to “change the shard key” or alter a collection’s key structure.

## 23. Monitoring impact on users and applications

### 23.1. Metrics to correlate

| Metric group | Examples | Purpose |
|---|---|---|
| Data | Owned bytes per shard/namespace | Shows storage distribution |
| Ownership | Range/chunk counts or placement state | Confirms logical ownership changes |
| Orphans | Orphaned bytes, range deletion backlog | Separates logical move from physical cleanup |
| Migrations | Rate/sec, duration, failures | Tracks speed and errors |
| Storage | Disk used/free, write latency, IOPS | Detects overloaded donor/recipient |
| Network | Inter-shard throughput, latency | Detects slow copy/catch-up |
| Queries | p95/p99, scatter-gather, slow queries | Measures real application impact |
| Replica sets | Secondary lag, elections | Assesses data-bearing member health |
| Balancer | Enabled/rounds/compliance | Shows what automation is doing |

### 23.2. One chart alone is never enough

If Shard A’s storage chart drops, it could mean:

- Data migrated cleanly to another shard.
- TTL or deletes are purging documents.
- Compression or storage engine metrics changed.
- The collection was resharded or rewritten.

Correlate migration history, destination shard owned bytes, application activity, and operational events.

### 23.3. Trend-based alerting

Useful alerts include:

- Owned data remains heavily skewed over multiple cycles **and** the balancer makes no progress.
- Recipient free disk drops below safety headroom.
- Migration failure rate climbs.
- Orphan cleanup backlog grows continuously.
- Balancer disabled outside an approved maintenance window.
- Write p99 latency spikes during migrations.
- Replication lag exceeds system thresholds.

Never alert `critical` on “1 range difference.” Small clusters may not need balancing immediately, and range count does not reflect byte size.

## 24. Diagnostic workflow when the balancer seems stuck

### Step 1 — Verify connection and topology

```javascript
db.adminCommand({ hello: 1 });
db.adminCommand({ listShards: 1 });
```

Confirm you are on **`mongos`** with at least two healthy target shards. Verify shard replica sets have healthy primaries/secondaries with no severe incidents.

### Step 2 — Confirm the collection is sharded

```javascript
sh.status();
```

Verify namespace, shard key, and existing ranges/data. **An unsharded collection does not spread across shards via chunk balancing.**

### Step 3 — Check balancer state

```javascript
sh.getBalancerState();
sh.isBalancerRunning();
```

If disabled, check why and review runbooks; never turn it on impulsively during another team’s maintenance window.

### Step 4 — Inspect real data distribution

```javascript
db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

If supported:

```javascript
sh.getShardedDataDistribution();
```

Separate owned data from orphans and chunk counts.

### Step 5 — Check policies and zones

Verify whether ranges are permitted on other shards. An empty shard in an incompatible zone is not a valid destination.

### Step 6 — Look for jumbo or unsplittable ranges

Inspect version-appropriate metadata and logs. Evaluate shard key cardinality and concentration. If all documents share one shard key value, the balancer cannot invent distinct values.

### Step 7 — Review migration history and errors

```javascript
db.getSiblingDB("config").changelog
  .find({ what: /moveChunk|moveRange|balancer/i })
  .sort({ time: -1 })
  .limit(20);
```

Correlate with `mongos`/config server/shard logs and monitoring. Never rely solely on one event string when schemas vary across versions.

### Step 8 — Assess donor/recipient load

Check network/disk, replication lag, write concern, elections, and query latency. If the recipient lacks headroom, pushing more migrations worsens the incident.

### Step 9 — Choose a bounded remediation

Options include:

- Let the balancer continue if making steady progress.
- Provision planned capacity.
- Adjust zone placement if policy permits.
- Fix shard key/splittability through architectural changes.
- Schedule a maintenance window for special migrations.
- Following version docs, manually move a lab range or an approved production range.

**Never “fix” by editing metadata directly.**

### Step 10 — Verify post-change state

Record:

- Owned bytes and orphaned bytes.
- Ranges and ownership.
- Balancer state.
- Migration successes/failures.
- Free disk space and replication lag.
- Application p95/p99 latency.

Confirm normal application service and planned balancing state are restored.

## 25. Misconceptions to avoid

| Misconception | Reality |
|---|---|
| The balancer places each document on the least-loaded shard | The balancer moves **shard key ranges**, not arbitrary individual documents |
| An enabled balancer is always actively moving data | There may be no migrations needed |
| 10 chunks on A and 5 on B means A holds double the data | Chunks vary in size; inspect data bytes |
| Moving a chunk is like copying a data folder | Requires copying, catch-up, metadata commit, and cleanup |
| Donor disk usage must drop immediately post-migration | Orphan cleanup and storage reuse delay physical reclamation |
| Orphans mean queries return duplicate documents | Logical ownership and routing prevent duplicates |
| One range holds one document | One range can hold millions of documents |
| `moveChunk` with key X moves only document X | Moves **the entire range containing key X** |
| `moveChunk` always balances data | Moving a huge range can skew distribution the other way |
| Balanced storage bytes means balanced CPU/QPS | Hot keys, query patterns, and hardware can still skew |
| Any range can move to any shard | Zones and sharding constraints restrict destinations |
| Adding a shard evens data immediately | Balancing takes time and eligibility |
| Stopping the balancer stops application writes | No; normal reads/writes continue per ownership |
| `sh.status()` showing balancer enabled means balancing finished | Check distribution/compliance and trends |
| `config.chunks` is an admin table to edit with `updateOne` | Internal metadata; direct edits are dangerous |
| `moveChunk` is how you change a shard key | Changing shard keys requires resharding, not normal migration |
| Equal document counts are always optimal | Document sizes and traffic vary widely |
| An empty new shard means the balancer is broken | May not need moves yet or may be restricted by zones/keys |
| One snapshot metric suffices to diagnose issues | Compare trends over time, logs, and multiple metrics |
| Many orphans means data was lost | Orphans are copies awaiting cleanup; interpret properly |
| To fix skew, force-move every jumbo range | High risk; analyze root causes and follow runbooks |

## 26. Hands-on exercises

### Exercise 1 — Sketch a cluster and ownership

Suppose `orders` is sharded on `{ customerId: 1 }` across three shards:

```text
Shard A: [MinKey, "K")
Shard B: ["K", "T")
Shard C: ["T", MaxKey)
```

Answer:

1. Which shard owns an order with `customerId: "M15"`?
2. If range `["K", "T")` moves from B to C, what must change in metadata?
3. Might Shard B retain physical copies temporarily?
4. Must applications using `mongos` change their connection string?

### Exercise 2 — Counting chunks vs. comparing storage

Two shards show:

```text
Shard A: 8 chunks, owned 420 MB
Shard B: 4 chunks, owned 430 MB
```

Why can’t you conclude Shard A handles double the load? What additional metrics are needed to evaluate data balance and query balance?

### Exercise 3 — Inspecting the balancer in a lab

On a lab sharded cluster:

```javascript
sh.status();
sh.getBalancerState();
sh.isBalancerRunning();
```

Distinguish:

- Is the balancer enabled?
- Is it currently active?
- Is the collection compliant with policy?
- Is a migration actively running?

Why can’t a single boolean command answer all four questions?

### Exercise 4 — Observing collection distribution

For `sharding_lab265.events265`:

```javascript
db.getSiblingDB("sharding_lab265")
  .events265
  .getShardDistribution();
```

Record which shards hold data. If `sh.getShardedDataDistribution()` is available, compare owned vs. orphaned bytes. Explain why two measurements can differ due to migrations or fresh inserts.

### Exercise 5 — Scoping `moveChunk`

Suppose a range is:

```text
[{ tenantId:"T02", eventAt:MinKey },
 { tenantId:"T03", eventAt:MinKey })
```

If you call the helper with a point `tenantId: "T02"` inside that range, answer:

- Are you moving one document or the entire range?
- What happens to other `T02` documents in the same range?
- Why must you know the destination shard and zones?
- Why shouldn’t you call `moveChunk` in bulk loops without a runbook?

### Exercise 6 — Adding a new shard

Initially:

```text
Shard A: 900 GB
Shard B: 880 GB
```

After adding C, C holds 0 GB. Describe how the balancer transfers data, conditions that slow it down, and metrics to monitor on A/B/C.

### Exercise 7 — Balancer enabled yet skewed

A cluster shows:

```text
Shard A: 1 TB
Shard B: 150 GB
Balancer enabled: true
```

Give at least five **distinct** hypotheses explaining this state. For each, name one diagnostic source to check: zones, chunk/range sizes, migration logs, balancer window, hardware, shard key, or unsharded collections.

### Exercise 8 — Zones change what “balanced” means

Suppose:

```text
Shard A: zone APAC
Shard B: zone APAC
Shard C: zone EU
```

Total APAC data is 3 TB while EU is 500 GB. Why can’t you move an APAC range onto C just to equalize storage across all three shards? Propose how to evaluate balance **within each zone**.

### Exercise 9 — Identifying a hot shard

Three shards each hold roughly 500 GB of owned data, yet QPS is:

```text
Shard A: 20,000/s
Shard B: 1,000/s
Shard C: 1,100/s
```

Why won’t calling `sh.startBalancer()` necessarily solve this? Propose how to investigate query routing, hot tenants, indexes, the shard key, and hardware.

### Exercise 10 — Why can orphans spike temporarily?

A range just moved from Shard A to B. Metadata already names B as the new owner, yet monitoring reports:

```text
Shard A orphaned bytes: 200 MB
Shard B owned bytes increased: 200 MB
```

Explain why this is a valid intermediate state and why you must never manually delete documents by filter on A without understanding range deletion.

### Exercise 11 — Choosing a suitable shard key

Compare three keys for `events`:

```javascript
{ createdAt: 1 }
{ tenantId: 1 }
{ tenantId: "hashed" }
```

Suppose 80% of queries filter by tenant, one tenant accounts for 70% of events, and new events continually increase over time. Discuss trade-offs across range queries, targeted queries, cardinality, hotspots, and migration feasibility.

You do not need to claim one universally optimal key; state what data must be measured before deciding.

### Exercise 12 — Shard replacement workflow

A shard must be removed for hardware replacement. Write a conceptual runbook:

1. Check how much owned data the shard holds.
2. Verify remaining cluster capacity.
3. Check zone placement.
4. Start draining via your version’s supported command.
5. Monitor progress and errors.
6. Verify metadata/ownership before shutting down nodes.

Why is stopping MongoDB and deleting data directories before draining finishes dangerous?

### Exercise 13 — Distinguishing resharding from migration

For a collection currently sharded on `{ tenantId: 1 }`, the organization wants to switch to `{ tenantId: 1, eventAt: 1 }`.

Can `sh.moveChunk()` accomplish this? Compare the goals of **migration** vs. **resharding**, impact levels, and query/index verification needs.

### Exercise 14 — Designing a load-balancing dashboard

Propose a dashboard including:

- Owned GB per shard.
- Orphaned GB per shard.
- Successful/failed migrations per hour.
- Free disk space and IOPS.
- p95/p99 query latency.
- CPU/QPS per shard.
- Balancer enabled/activity.
- Observation timestamps and deployment version.

State which metrics measure **data**, which measure **workload**, and which detect migration errors.

## 27. Safe operational workflow to remember

When investigating or adjusting inter-shard data movement, follow this order:

1. **Verify connection to `mongos`** and the exact namespace.
2. **Check shard key, zones, and topology** before assuming data can spread freely.
3. **Measure owned data**, not just chunk counts or raw file sizes.
4. **Check balancer enabled/activity/compliance** using version-supported helpers.
5. **Inspect history/logs** for active or failing migrations.
6. **Evaluate donor/recipient health** across disk, network, replica sets, and app latency.
7. **Prefer the balancer** for routine automatic balancing.
8. **Use manual moves only within a scoped runbook** specifying range, destination, and rollback criteria.
9. **Never edit sharding metadata directly** and never delete orphans manually.
10. **Verify post-move state** via distribution, ownership, metrics, and app queries.

This process distinguishes a cluster balancing normally, a cluster constrained by policies/shard keys, and a cluster experiencing a real migration failure.

## 28. Summary

**MongoDB partitions sharded data by shard key ranges.** A range/chunk is the logical unit the system transfers from donor to recipient. Migration encompasses copying data, syncing ongoing changes, committing ownership metadata, and cleaning up unowned records on the source shard.

**The balancer aims for policy-compliant data distribution**, without guaranteeing equal document counts, chunk counts, CPU, or QPS. Owned storage, zone constraints, the shard key, and range splittability govern what can actually balance.

**Monitoring must combine multiple layers of signals.** `sh.status()` reveals topology; `sh.getBalancerState()` and activity helpers report balancer status; `getShardDistribution()`/`getShardedDataDistribution()` show data placement; logs and infrastructure metrics catch failed migrations or latency impacts.

**Manual move commands are impactful administrative actions.** `sh.moveChunk()` targets the entire range containing a shard key value, not a single document. Use them only when namespace, donor, recipient, zones, and resource headroom are verified; never edit `config.chunks` or delete data directly to “force balance.”

**The ultimate goal is a scalable cluster serving applications reliably**, not a pretty chunk-count chart. Once you understand range ownership, migration mechanics, and balancer signals, you will know when to wait and observe, when to adjust your distribution model, and when manual intervention is truly justified.
