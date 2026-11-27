# Monitoring Shards, the Balancer, and Data Distribution Skew in MongoDB

## 1. Problem: The Cluster Has Three Shards, Yet One Shard Remains Overloaded

Suppose an e-commerce platform moves its **commerce.orders** collection to a sharded cluster to store hundreds of millions of orders. After scaling from two to three shards, the dashboard shows:

| Shard | Estimated physical storage | Peak CPU | Write operations/sec |
|---|---:|---:|---:|
| **shard01** | 900 GiB | 92% | 7,500 |
| **shard02** | 320 GiB | 38% | 1,900 |
| **shard03** | 290 GiB | 32% | 1,600 |

Operators need to answer:

- Has MongoDB **recognized all three shards**?
- Is the balancer enabled, paused, or repeatedly failing migrations?
- How are **ranges/chunks** distributed?
- If chunk counts are roughly equal, why are disk and CPU still skewed?
- Is the **shard key** funneling new writes into a single contiguous value range?
- Are **zones** intentionally constraining where data is placed?
- Are there **jumbo/oversized ranges**, orphaned documents, or a migration backlog?
- After adding a shard, how long will it take for data distribution and workload to improve?
- Which dashboards and runbooks are needed to diagnose safely without accidentally causing an outage?

This is an **observability** problem: measure the right signals, interpret them in the context of cluster metadata and workload, and only then make operational decisions.

### Lesson Objectives

After this lesson, you will be able to:

1. Describe **`mongos`, config server replica set, shards, and the balancer**.
2. Distinguish **chunk-count skew**, **owned-data skew**, **disk skew**, and **workload skew**.
3. Use **`sh.status()`, `listShards`, `balancerStatus`, `getShardDistribution`**, and relevant metrics.
4. Understand **range migrations**, placement constraints, zone sharding, and cases where balancing takes time.
5. Recognize hot shards caused by shard keys or workloads instead of always blaming the balancer.
6. Monitor **migration failures, jumbo ranges, orphan cleanup**, and operational data impact.
7. Design dashboards, alert thresholds, and safe investigation runbooks.
8. Observe the cluster via `mongosh`, Java, and metrics systems.

**Principle:** *Equal chunks do not mean equal bytes; equal bytes do not mean equal CPU and latency; and zone-based placement can be intentionally uneven.*

## 2. Sharded Cluster Architecture to Observe

~~~text
                    Client applications
                            |
                       MongoDB driver
                            |
                 +----------v----------+
                 | mongos routers      |
                 | query targeting     |
                 +----------+----------+
                            |
             +--------------+--------------+
             |              |              |
       +-----v-----+  +-----v-----+  +-----v-----+
       | shard01   |  | shard02   |  | shard03   |
       | replica   |  | replica   |  | replica   |
       | set       |  | set       |  | set       |
       +-----------+  +-----------+  +-----------+
                            ^
                            |
               +------------+-----------+
               | Config server replica  |
               | set (CSRS): metadata   |
               +------------------------+
                     balancer / migrations
~~~

### 2.1. `mongos`: Entry Point and Routing

**`mongos`** receives requests from drivers, determines which shards/ranges to access, and merges results for distributed queries. Monitor connections, query latency, throughput, errors, targeted vs. scatter-gather ratios, and latency from `mongos` to shards and config servers.

Do not connect directly to a shard primary as a substitute for `mongos` for normal application queries against a sharded collection: you risk reading only partial data and bypassing routing metadata.

### 2.2. Config Servers: Partition Metadata

The Config Server Replica Set (**CSRS**) stores metadata about shards, sharded collections, chunks/ranges, and zones. Metadata maps each range to its owning shard, supporting routing, placement, and migrations.

The CSRS also has a primary, secondaries, replication lag, and member health that must be monitored. An unhealthy CSRS can disrupt metadata operations even while some data queries continue to succeed.

**Never manually modify documents in the `config` database** to force ownership or alter boundaries. Use only supported administrative commands.

### 2.3. Shards Are Replica Sets

Each shard is typically a replica set holding a portion of a sharded collection's data.

Monitor at two levels:

- **Shard-level:** assigned data/ranges, CPU, throughput, cache, disk.
- **Replica-set-level:** primary elections, member health, replication lag, oplog, and read preference.

Three members in one replica set still constitute **one logical shard**, not three independent data-distributing shards.

### 2.4. What Does the Balancer Do?

The balancer helps the cluster adjust **range/chunk distribution** while honoring placement constraints:

1. Reads metadata and size/distribution information.
2. Identifies ranges eligible or worthwhile to move.
3. Coordinates **range migrations** from donor to recipient shard.
4. Updates ownership metadata when a migration commits.
5. Continues or pauses according to cluster state, configuration, and version.

The balancer does **not** guarantee equal CPU, QPS, or latency across all shards. It primarily manages data placement; performance also depends on the shard key, indexes, query targeting, and hardware.

### 2.5. Why Multi-Layer Observability Is Necessary

~~~text
User-facing latency
       ^
       |
     mongos                    -> routing/targeting
       ^
       |
  shard primary/secondary      -> CPU, disk, cache, lag
       ^
       |
  ranges/chunks and shard key  -> placement, hot ranges
       ^
       |
  CSRS metadata + balancer     -> migrations, zones
~~~

A single "disk used per shard" chart cannot explain this causal chain.

## 3. Ranges/Chunks and What Chunk Counts Mean

MongoDB partitions a sharded collection's keyspace into **ranges** (commonly called **chunks** in many tools and docs), bounded by shard key values:

~~~text
Shard key space:

-infinity |-----------|-----------|-----------| +infinity
          A           B           C           D

Range R1: [-infinity, A)
Range R2: [A, B)
Range R3: [B, C)
Range R4: [C, D)
Range R5: [D, +infinity)
~~~

Each range has an **owner shard**. `mongos` uses the shard key and routing metadata to route operations.

### 3.1. Chunk Count Is Not Data Size

| Shard | Range count | Owned data size |
|---|---:|---:|
| shard01 | 100 | 900 GiB |
| shard02 | 100 | 110 GiB |
| shard03 | 100 | 105 GiB |

Range counts are identical, yet owned bytes are uneven. Some ranges may be huge or have different document densities.

Conversely:

| Shard | Range count | Owned data size |
|---|---:|---:|
| shard01 | 300 | 300 GiB |
| shard02 | 150 | 300 GiB |
| shard03 | 75 | 300 GiB |

Range counts differ while owned bytes are equal. Modern balancing mechanisms consider data size and placement rather than solely equalizing chunk counts.

### 3.2. Splits, Migrations, and Merges Differ

- **Split:** divides one range into smaller ranges.
- **Migration:** transfers ownership of a range between a donor and a recipient shard.
- **Merge:** under supported conditions, combines adjacent ranges with the same owner.

Split, merge, and range management behavior varies by MongoDB version. **Splitting alone does not reduce bytes on a shard** until ownership moves.

### 3.3. Migration Does Not Shrink Disk Immediately

~~~text
Logical ownership after move:
  shard01 no longer owns R9
  shard02 owns R9

Physical storage:
  shard01 may still contain orphan copies awaiting cleanup
  shard02 has received R9 data
~~~

Disk usage may not drop right away—or may temporarily rise during migration. Distinguish **owned bytes** from **physical storage bytes**.

### 3.4. Disk Storage Includes Multiple Components

~~~text
Disk usage per shard may reflect:
  collection data
  indexes
  oplog/replication overhead
  storage-engine free space / fragmentation
  temporary migration effects
  other collections on the shard
~~~

These are conceptual components, not a rigid arithmetic formula: MongoDB storage metrics sometimes include other overhead.

### 3.5. Compare Using the Same Point in Time

If one measurement is taken at 10:00 and another at 10:02 mid-migration, the numbers reflect different states. Dashboards should record timestamps, namespaces, and active migration status when computing skew.

## 4. Four Types of Imbalance to Distinguish

### 4.1. Skew by Chunks/Ranges

~~~text
shard01: 500 ranges
shard02: 120 ranges
shard03: 110 ranges
~~~

This is **chunk-count skew**, which does not yet prove `shard01` holds most of the bytes.

### 4.2. Skew by Owned Data

~~~text
shard01: 720 GiB owned
shard02: 300 GiB owned
shard03: 280 GiB owned
~~~

This is **logical data skew**. Check whether the metric excludes orphaned documents and indexes and whether multiple collections are combined.

### 4.3. Skew by Physical Disk

~~~text
shard01: 88% disk full
shard02: 60% disk full
shard03: 58% disk full
~~~

Disk skew can stem from owned data, indexes, orphan cleanup, fragmentation, oplog, unsharded collections, or differing hardware capacities. Do not declare the balancer broken solely because disk fill percentages differ.

### 4.4. Skew by Workload

~~~text
shard01: write QPS=8000, CPU=90%
shard02: write QPS=1000, CPU=35%
shard03: write QPS=1000, CPU=32%
~~~

This is a **hot shard**. Even with balanced owned bytes, active customers or devices may concentrate writes onto a single shard key range.

**The balancer moves ranges; it cannot split a single hot shard-key value** under the existing partition design. You may need a better shard key, added distribution entropy, or resharding.

### 4.5. Zone-Induced Skew Can Be Intentional

~~~text
zone: EU    -> shard01, shard02
zone: APAC  -> shard03
~~~

If APAC data exceeds EU data, `shard03` will legitimately hold more bytes. The balancer enforces zone placement, so measure **balance within each zone or eligible shard set** rather than forcing all shards equal.

## 5. Observability Data Sources and Access Control

During an investigation, always know which component you are connected to:

| Source | How to access | Primary observations |
|---|---|---|
| **`mongos`** | `mongosh` connected to router URI | Sharding overview, shard list, balancer status, collection distribution. |
| **Config server** | Supported admin tools, monitoring | Placement metadata, CSRS member health, migration logs. |
| **Shard primary** | Controlled connection to each shard replica set | CPU, cache, disk, opcounters, write latency, replication status. |
| **Shard secondary** | Per-member monitoring | Replication lag, disk, cache, read workload if used. |
| **Application** | Traces, logs, service metrics | Read/write latency, error rates, query patterns, and tenant hot spots. |
| **Infrastructure** | Atlas monitoring, Prometheus/exporters, OS metrics | Disk capacity, IOPS, memory, network, CPU throttling. |

Do not merge metrics from different components into one number without understanding their roles.

### 5.1. Connection Requirements and Privileges

Sharding commands usually require connecting through **`mongos`** with an account authorized to read cluster state. Sensitive metrics, config metadata, and operational commands may require higher privileges such as **`clusterMonitor`**, equivalent admin roles, or an organization-defined monitoring role.

Example connection:

~~~bash
mongosh "mongodb://router1.example:27017,router2.example:27017/admin?authSource=admin" \
  --username monitoring-user
~~~

Applications and drivers may require TLS and password/secret managers. Never embed secrets in shell history or dashboard configs.

### 5.2. Principle of Least Privilege

An **observability account** should read metrics, status, and necessary metadata without privileges to alter shard placement, stop the balancer, delete metadata, or change a collection's shard key.

Separate roles:

~~~text
monitoring account:
  observe status, metrics, logs

operations account:
  approved balancer/cluster administration

application account:
  normal CRUD through mongos
~~~

Avoid using one root account for every dashboard service.

### 5.3. Prefer Supported Interfaces First, Raw Config Metadata Last

Recommended priority order for information sources:

1. **Atlas/Cluster Monitoring** or provider-supported metrics.
2. **`sh.status()`, `balancerStatus`, `listShards`**, and documented administrative commands/helpers.
3. **`getShardDistribution()`, `$collStats`**, controlled collection-level statistics.
4. **Read-only `config` database/changelog** when deep troubleshooting requires it and schema version nuances are understood.

Internal metadata schemas can change between MongoDB versions. Do not build a multi-year production dependency on directly parsing `config.chunks` when official tools suffice.

## 6. Inspecting Shards with `mongosh`

Examples in this section use **read-only status commands** on an authorized cluster. They do not create, delete, or migrate data.

### 6.1. Connecting Through `mongos`

~~~javascript
db.adminCommand({ hello: 1 });
~~~

The response identifies the connected component. When connected to `mongos`, output normally includes a router identifier such as **`msg: "isdbgrid"`**. Never run replica-set-primary-only commands against `mongos`, or vice versa.

### 6.2. Listing Shards

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Typical output provides shard IDs, hosts/replica set connection strings, and other version-dependent details:

~~~javascript
{
  shards: [
    { _id: "shard01", host: "rsShard01/s01a:27017,s01b:27017,s01c:27017" },
    { _id: "shard02", host: "rsShard02/s02a:27017,s02b:27017,s02c:27017" },
    { _id: "shard03", host: "rsShard03/s03a:27017,s03b:27017,s03c:27017" }
  ],
  ok: 1
}
~~~

**This example illustrates structure only**, not verified output from a live cluster. In production, shard host lists may be sensitive infrastructure metadata; restrict storage and logging.

Observe:

- Does the actual shard count differ from expected?
- Was a shard recently added or is one draining/being removed?
- Do replica set names and hostnames match inventory?
- Are network, TLS, or DNS errors affecting a shard?

### 6.3. Partitioning Overview with `sh.status()`

~~~javascript
sh.status();
~~~

Versions of `mongosh` support verbose levels:

~~~javascript
sh.status(true);
~~~

Results can show:

- Shards and host mappings.
- Sharded collections.
- Each collection's shard key.
- Which shards hold which ranges/chunks.
- Zones/tags and balancer state depending on version.
- Summaries of migrations or chunk distribution when available.

**Do not treat every field and format of `sh.status()` as stable across MongoDB versions.** If a collection has many ranges, verbose output can be huge; never dump full output unbounded into logs or CI artifacts.

### 6.4. Exact Namespace and Shard Key

Suppose you need to inspect collection **commerce.orders**:

~~~javascript
use commerce
sh.status();
~~~

Verify:

1. Is the collection actually sharded?
2. Is the shard key **`{customerId:"hashed"}`**, **`{createdAt:1}`**, or a compound key?
3. How are chunks distributed?
4. Are there zone ranges or shard-specific constraints?
5. Is a resharding/repartitioning operation currently running?

You cannot infer migration behavior from the database name alone; always inspect the exact **fully qualified namespace**.

### 6.5. `getShardDistribution()` for a Specific Collection

In supported `mongosh` versions, the helper:

~~~javascript
db.getSiblingDB("commerce")
  .orders
  .getShardDistribution();
~~~

summarizes estimated data distribution and chunks per shard. Output fields, estimation methods, and formatting can vary by version and how stats are gathered.

Questions to answer:

- Is one shard holding most of the collection's data?
- Do chunk counts align with data size?
- Has a newly added shard started receiving data?
- Is there a mismatch between logical ownership and physical storage?

Do not treat sample output as exact real-time numbers while migrations are actively running.

### 6.6. Collection-Level Statistics via `$collStats`

MongoDB supports the **`$collStats`** aggregation stage in appropriate versions to inspect collection counts and storage stats.

~~~javascript
db.getSiblingDB("commerce").orders.aggregate([
  {
    $collStats: {
      storageStats: {
        scale: 1048576
      },
      count: {}
    }
  }
]);
~~~

**`scale=1048576`** displays scaled sizes in MiB for applicable fields. Output fields and per-shard vs. aggregate formatting depend on version and configuration; verify each metric's meaning before computing ratios.

**`$collStats` must appear in its required position, typically the very first stage**; do not place `$match` ahead of it to filter documents like a normal aggregation.

If your cluster version does not support an option or returns a different format, use the collection metrics recommended for that MongoDB version. Never substitute total database size and attribute it to the collection under investigation.

### 6.7. Checking Shard Replica Set Health

If authorized and permitted to connect directly to each shard replica set for monitoring:

~~~javascript
rs.status();
~~~

Check the members:

- Is the primary stable?
- Are secondaries healthy?
- How high is replication lag?
- Are oplog retention and networking keeping up with writes and migrations?

Never run `rs.status()` on `mongos` and conclude a shard replica set is healthy; `mongos` is not a shard replica set member.

### 6.8. Distinguish Shard Listing from Reachability and Health

**`listShards` returning a shard in metadata** does not mean all of its members are healthy or have sufficient disk space.

Combine:

~~~text
listShards
    +
replica set/member health
    +
CPU/disk/network metrics
    +
query latency and errors
~~~

A listed shard undergoing a primary election or nearing disk exhaustion can slow down or block migrations.

## 7. Checking the Balancer: Enabled Does Not Mean Actively Moving Data

The balancer can be **enabled** yet waiting on conditions, having no ranges to move, or blocked from migrating. Distinguish:

~~~text
Balancer configured / enabled?
          |
          v
Currently in a balancer round?
          |
          v
Migration selected / started?
          |
          v
Migration progressing / committed / failed?
          |
          v
Distribution changed toward desired placement?
~~~

### 7.1. `balancerStatus`

Connect to `mongos` with appropriate privileges:

~~~javascript
db.adminCommand({ balancerStatus: 1 });
~~~

Illustrative output (fields depend on server version):

~~~javascript
{
  mode: "full",
  inBalancerRound: false,
  numBalancerRounds: 12,
  ok: 1
}
~~~

- **`mode`** describes the balancer's operating mode per server version.
- **`inBalancerRound`** indicates whether a balancing round is active at observation time, when provided.
- **`numBalancerRounds`** tracks rounds executed, **not successful migrations**.
- **`ok:1`** means the command succeeded, **not that the collection is balanced**.

### 7.2. Enabled State

In `mongosh` on a supported cluster:

~~~javascript
sh.getBalancerState();
~~~

This reflects whether the balancer is configured as enabled, distinct from "migrating right now."

~~~text
Balancer enabled: true
In balancer round: false
~~~

This can be completely normal when no migrations are needed or between balancing rounds.

### 7.3. Collection-Level Balancer Status

Some MongoDB versions support:

~~~javascript
db.adminCommand({
  balancerCollectionStatus: "commerce.orders"
});
~~~

Output can indicate **placement compliance** or why a collection is not yet compliant, depending on version. Consult your running server's documentation before building alerts on specific fields.

### 7.4. Balancer Windows and Maintenance

Clusters can configure a **balancer window**. Outside that window, being enabled without migrating is expected.

Track:

1. Global balancer enabled/disabled state.
2. Balancing window timezone.
3. Whether current time is inside the window.
4. Any maintenance, resharding, or conflicting operations.
5. Collection-specific placement constraints.

Never manually open balancing outside approved windows just to make a dashboard look "more even."

### 7.5. Eligible Yet Needing No Migrations

The balancer may legitimately take no action when:

- Owned data is already balanced within thresholds/policy.
- Ranges sit on zone-eligible shards.
- No eligible range meets size/placement move criteria.
- The cluster is outside its balancing window.
- The collection is excluded from balancing under current mode.

**Zero migrations does not automatically mean an error.**

### 7.6. Never Restart the Balancer Without Evidence

APIs that toggle the balancer alter cluster behavior and can impact user-facing latency. Perform them only with change approval, version awareness, rollback plans, and monitoring.

Restarting the balancer will not fix low shard-key cardinality or a zone with only one eligible shard.

## 8. Range Migrations: What to Observe

~~~text
                       Balancer
                          |
                 Select eligible range
                          |
                          v
           +------------------------------+
           | Donor shard (source)         |
           | currently owns range R1      |
           +------------------------------+
                          |
                Transfer/clone data
                          |
                          v
           +------------------------------+
           | Recipient shard (target)     |
           | receives range contents      |
           +------------------------------+
                          |
                Catch up concurrent writes
                          |
                Commit placement metadata
                          |
             New owner = recipient shard
                          |
              Orphan cleanup on donor
~~~

Exact phases, RPCs, and commit conditions vary by MongoDB version. The diagram illustrates the roles.

### 8.1. Donor and Recipient

- **Donor** owns the range before migration.
- **Recipient** receives the data and ownership upon commit.
- **Config metadata** updates when ownership transfers.
- **`mongos`** uses the updated metadata for routing.

The recipient starting to receive copied bytes does not mean the migration has committed.

### 8.2. Why Can Migrations Be Slow?

- Reading data and indexes on the donor.
- Writing data and indexes on the recipient.
- Transferring over the network.
- Catching up on concurrent writes during cloning.
- Waiting on replication and durability conditions.
- Committing metadata and performing cleanup.

Duration depends on range size, write churn, disk IOPS, network, replication lag, topology, and application load.

### 8.3. Commit Does Not Always Shrink Donor Disk Immediately

~~~text
Logical range owner: recipient
Donor may still have orphaned copies
Recipient has copied data
~~~

Monitor both **owned bytes** and **physical storage**, plus orphan cleanup progress.

### 8.4. Repeated Migration Failures

Common causes to investigate:

- Donor or recipient disk overload or insufficient free space.
- Primary elections, replication lag, or network/TLS/DNS errors.
- Oversized/jumbo range or inability to split as expected.
- Incompatible zone placement constraints.
- Unhealthy CSRS blocking metadata operations.
- Balancing window too short.
- Active resharding, maintenance, or conflicting operations.

Only tune migration speed after identifying the bottleneck; increasing migration load can worsen application latency.

### 8.5. Newly Added Shard

~~~text
Before adding shard03:
  shard01: 500 GiB
  shard02: 500 GiB

Immediately after:
  shard01: 500 GiB
  shard02: 500 GiB
  shard03: ~0 GiB
~~~

An empty new shard for the first few minutes is normal. If it still receives no data after several rounds, check `listShards`, the shard key, zones, balancer state/window, eligible ranges, disk/network, and migration logs.

### 8.6. Impact on the Application

During balancing you may observe:

~~~text
network bytes/sec increases
disk read/write IOPS increases
cache pressure increases
replication lag increases
application p95 latency rises temporarily
~~~

Therefore **place the migrations dashboard right next to the application latency dashboard** rather than watching bytes moved while ignoring SLAs.

## 9. Reading Migration History and Placement Metadata

### 9.1. The `config` Database Is Sensitive Internal State

MongoDB stores cluster metadata and some administrative logs in the sharded cluster's **`config`** database.

When deep investigation is required:

~~~javascript
const configDb = db.getSiblingDB("config");
~~~

Inspect metadata with proper privileges and strictly **read-only**. Never run `updateMany`, `deleteMany`, or `insert` to "fix" `config.chunks`, `config.collections`, or `config.shards`. Unsupported writes can corrupt routing and placement.

### 9.2. Migration Event History

On versions providing **`config.changelog`**:

~~~javascript
db.getSiblingDB("config").changelog.find(
  {
    what: { $regex: "^moveChunk" }
  },
  {
    _id: 0,
    time: 1,
    what: 1,
    ns: 1,
    details: 1
  }
).sort({ time: -1 }).limit(30);
~~~

Event names, document fields, log retention, and semantics vary across versions. Patterns like **`moveChunk.*`** are conventions found in certain releases; an empty query result does not prove "no migrations occurred."

Cross-reference with:

- Balancer status and rounds.
- Time-correlated MongoDB server logs.
- Atlas/Ops Manager metrics.
- Before/after placement and size measurements.

### 9.3. Event Types Must Be Interpreted by Phase

An event history containing:

~~~text
moveChunk.start
moveChunk.commit
moveChunk.error
~~~

cannot be interpreted from a single isolated event:

- **`start`** does not guarantee completion.
- **`commit`** is the stronger signal of ownership transfer.
- **`error`/`abort`** requires checking the reason and subsequent retries.

Exact names vary by version. Never write brittle alerts hardcoded to one legacy event string.

### 9.4. Inspecting Collection Metadata and Shard Key

In some versions, collection metadata stores the namespace in **`config.collections._id`**:

~~~javascript
db.getSiblingDB("config").collections.findOne(
  { _id: "commerce.orders" }
);
~~~

You may see fields like **`key`** (shard key), **`uuid`**, and other metadata. These are internal/administrative representations and must not be edited directly.

Do not equate a collection's presence in `config.collections` with the steady state of every range while resharding or migration is active.

### 9.5. Inspecting Per-Shard Range Counts for a Collection

Use only for **read-only inspection** on versions with compatible metadata schemas; prefer official helpers where available:

~~~javascript
const cdb = db.getSiblingDB("config");
const ns = "commerce.orders";
const collMeta = cdb.collections.findOne({ _id: ns });

if (!collMeta) {
  print("Collection metadata not found");
} else {
  const selector = collMeta.uuid
    ? { uuid: collMeta.uuid }
    : { ns: ns };

  cdb.chunks.aggregate([
    { $match: selector },
    {
      $group: {
        _id: "$shard",
        rangeCount: { $sum: 1 }
      }
    },
    { $sort: { rangeCount: -1 } }
  ]).forEach(printjson);
}
~~~

**Warning:** whether chunk metadata keys on **`uuid`** or **`ns`**, as well as field names, indexes, and representations, varies by server version. This snippet shows illustrative branching, not a guarantee across all deployments; use it to understand metadata reading rather than as an immutable production parser.

Per-shard range counts **do not equal** total bytes or QPS. On clusters with very large range counts, metadata aggregations must also be bounded or throttled during monitoring.

### 9.6. Inspecting Zone Metadata

Zones/tags and shard key partitions may appear in metadata collections such as **`config.tags`** or **`sh.status()`** output, depending on version.

~~~javascript
db.getSiblingDB("config").tags.find().limit(20);
~~~

Key facts to verify:

1. Which zones are assigned to which shards?
2. Which key ranges carry zone constraints?
3. Is any range in a zone with no eligible shard?
4. Are there geographic, data residency, or hardware-tier restrictions?

Never remove zone tags just to make the balancer "even out" when those tags enforce data residency requirements.

### 9.7. Monitoring Ongoing Operations

When a migration runs unusually long, combine cluster metrics, server logs, and the current-operations tools supported by your MongoDB version. Never build an always-on dashboard around heavy `currentOp` polls that return huge payloads or sensitive details.

If using:

~~~javascript
db.adminCommand({ currentOp: 1 });
~~~

keep in mind:

- Required privileges can be high.
- Output can be large and contain query text, namespaces, and host details.
- Short-lived operations can finish between samples.
- Migration operation names and fields are not stable across versions.

For long-term metric pipelines, rely on official metrics sources and normalized logs.

## 10. Measuring Data Distribution Skew Meaningfully

Do not just glance at a chart; define **units, scope, timestamp, and denominator** for every metric.

### 10.1. Data Share per Shard

Suppose three shards hold owned data bytes:

~~~text
shard01 = 600 GiB
shard02 = 300 GiB
shard03 = 300 GiB
total   = 1200 GiB
~~~

Compute:

~~~text
dataShare(shard01) = 600 / 1200 * 100% = 50%
dataShare(shard02) = 300 / 1200 * 100% = 25%
dataShare(shard03) = 300 / 1200 * 100% = 25%
~~~

This measures byte distribution for a **specific scope**. If total bytes cover the entire database while the chart is labeled with a single collection name, conclusions will be wrong.

### 10.2. Max-to-Average Skew Ratio

For N shards:

~~~text
averageOwnedBytes = sum(ownedBytes[i]) / N

maxToAverageSkew = max(ownedBytes[i]) / averageOwnedBytes
~~~

In the example:

~~~text
averageOwnedBytes = (600+300+300)/3 = 400 GiB
maxToAverageSkew  = 600/400 = 1.5
~~~

Interpretation: the largest shard holds **1.5x the average** owned bytes.

### 10.3. Max-to-Min Ratio

~~~text
maxToMinSkew = max(ownedBytes[i]) / min(ownedBytes[i])
~~~

Example:

~~~text
600 / 300 = 2
~~~

However, when a new shard has **0 bytes**, the denominator is 0, making this ratio undefined or useless. Never plot infinity and declare the cluster "broken"; use max-to-average, absolute bytes, and time since the shard was added.

### 10.4. Percent Deviation from Mean

~~~text
relativeDeviation(i) =
  (ownedBytes[i] - averageOwnedBytes) / averageOwnedBytes * 100%
~~~

Example:

~~~text
shard01: (600-400)/400 = +50%
shard02: (300-400)/400 = -25%
shard03: (300-400)/400 = -25%
~~~

This metric is intuitive, though it still assumes all shards are equally eligible and sized.

### 10.5. Coefficient of Variation (CV)

Sometimes you want a single dispersion summary:

~~~text
mean = sum(x[i]) / N
stdDevPopulation = sqrt(sum((x[i]-mean)^2) / N)
CV = stdDevPopulation / mean
~~~

A CV near 0 indicates nearly uniform distribution for the measured metric. **CV does not explain root causes**, and should be avoided when the mean is near 0 or when zones restrict placement.

### 10.6. Data Distribution Differs from Capacity Distribution

If shards have unequal hardware:

| Shard | Owned bytes | Disk capacity | Owned/capacity ratio |
|---|---:|---:|---:|
| shard01 | 600 GiB | 2,000 GiB | 30% |
| shard02 | 300 GiB | 500 GiB | 60% |
| shard03 | 300 GiB | 500 GiB | 60% |

Forcing equal owned bytes pushes smaller shards closer to full than the large shard. Balancing strategies do not always auto-scale proportionally to heterogeneous hardware as businesses might expect; plan topology and capacity explicitly.

**Compare percent disk used, free bytes, absolute bytes, and eligible placement**, not just data share.

### 10.7. Per-Collection Skew vs. Cluster-Wide Skew

Suppose:

~~~text
commerce.orders:
  shard01 90%, shard02 5%, shard03 5%

analytics.events:
  shard01 5%, shard02 47.5%, shard03 47.5%
~~~

Total disk across shards may look balanced because two collections offset each other, yet **`commerce.orders`** remains heavily skewed. To diagnose write hot spots, track metrics **per collection, shard key, and workload**, not just cluster-wide GB totals.

### 10.8. Track Skew as a Trend, Not a Single Point

Collect periodically every few minutes:

~~~text
time, namespace, shardId, ownedBytes, chunkCount,
qps, cpuPct, diskUsedBytes, diskFreeBytes,
balancerEnabled, migrationsStarted, migrationsFailed
~~~

Monitor after:

- Adding a shard.
- Changing workloads.
- Toggling balancing windows per policy.
- Resharding a collection.
- Updating zone tags.
- Onboarding or migrating a large tenant.

Mild, stable skew may be acceptable; **continuously growing skew** warrants priority investigation.

### 10.9. Be Careful with Estimated Metrics

Some document counts, data sizes, or chunk figures on sharded collections are **estimates or pulled from snapshots/metadata**. During migrations, orphan cleanup, or post-restore, these numbers may temporarily diverge from exact counts of owned data.

Do not fire corruption alarms over a few percent difference between two metrics with distinct definitions.

## 11. Shard Keys and Root Causes of Hot Shards

The balancer primarily adjusts **range placement**. If most application operations hit the same range or shard-key value, moving other ranges will not directly fix the bottleneck.

### 11.1. Monotonically Increasing Range-Based Shard Key

Suppose an `events` collection uses shard key:

~~~javascript
{ createdAt: 1 }
~~~

With high-rate writes carrying advancing current timestamps:

~~~text
Shard key range:
  old timestamps          latest timestamps
  |-----------|-----------|-----------|
                                ^
                                |
                          all new writes
~~~

Inserts with new `createdAt` values continuously target the trailing range at the edge of the keyspace, creating a **write hot spot**.

The balancer can migrate older ranges away, yet all new writes keep hitting the range holding current timestamps. **Balanced data does not guarantee balanced writes.**

### 11.2. Hashed Shard Key

Another choice:

~~~javascript
{ customerId: "hashed" }
~~~

A hashed shard key scatters values across the hash space to prevent monotonic sequential clustering.

However:

- If one single **`customerId`** drives 80% of writes, the shard holding that hashed value still runs hot.
- Hashed sharding does not preserve natural locality for range queries on `customerId`.
- Equality queries on `customerId` can be targeted, but queries omitting the shard key risk scatter-gather.
- Hashed distribution does not replace analyzing cardinality, frequency, and query patterns.

### 11.3. Cardinality and Frequency

Evaluate a shard key by:

1. **Cardinality:** how many distinct values exist?
2. **Frequency:** does a single value dominate records or operations?
3. **Monotonicity:** do new values increase or decrease monotonically?
4. **Query targeting:** do most queries include the required shard key predicate?
5. **Index/sharding constraints:** are field types, uniqueness, and collation valid?
6. **Growth:** as tenants or devices grow, how will skew evolve?

Never pick a shard key merely because the field exists in every document.

### 11.4. Compound Shard Key

Example:

~~~javascript
{ tenantId: 1, orderId: "hashed" }
~~~

A compound key can add entropy across orders within the same tenant (per compound hashed shard key rules and server version), though you must examine query targeting, index requirements, zone sharding, and access patterns.

Ask:

- How many tenants exist?
- Can one tenant exceed a single shard's capacity?
- Do queries filter mostly by `tenantId`, `orderId`, or both?
- Are there tenant-level zone or data residency requirements?
- Are range queries on `orderId` needed?

Do not assume every compound hashed key achieves both perfect locality and perfect load balance.

### 11.5. High Cardinality Can Still Run Hot

Suppose 10 million customer IDs exist, yet **C-00001** generates 45% of writes:

~~~text
Total IDs:     10,000,000
Hot ID:        C-00001
Hot write share: 45%
~~~

High cardinality alone does not prevent a hot key. Analyze **top shard-key values by read/write QPS**, not just distinct value counts.

### 11.6. Query Targeting

A collection is sharded on `customerId`, yet the application frequently runs:

~~~javascript
db.orders.find({ status: "PENDING" });
~~~

Without a shard-key predicate, the query can trigger scatter-gather across shards. The balancer cannot fix this query pattern.

A targeted query:

~~~javascript
db.orders.find({
  customerId: "C-00001",
  status: "PENDING"
});
~~~

Exact targeting depends on the shard-key pattern, indexes, collation, and query planner/version. Verify with **`explain`** rather than guessing from field names.

### 11.7. `explain` Through `mongos`

~~~javascript
db.getSiblingDB("commerce")
  .orders
  .find({ customerId: "C-00001" })
  .explain("executionStats");
~~~

Inspect shard stages, targeted shards, keys/docs examined, and latency per version output. Avoid running `explain("executionStats")` on full-collection-scan queries in peak production without controlling cost.

### 11.8. Cause-Specific Actions

| Cause | Direction to explore |
|---|---|
| Monotonic timestamp inserts | Shard key/hash/compound pattern, partitioning strategy. |
| Single oversized tenant | Add entropy, resharding, or application-level partitioning. |
| Queries missing shard key | Query patterns, indexes, API design. |
| One shard has weak hardware | Capacity planning, not just range moves. |
| Movable hot range | Moving only relocates the hotspot rather than splitting load. |
| Zone has only one eligible shard | Expand eligible capacity if policy permits. |

**Resharding carries cost and risk**; it is never the first diagnostic step.

## 12. Zone Sharding: Balancing Within Allowed Boundaries

Zone sharding pins ranges to shards belonging to matching zones for data residency, workload isolation, or storage tiering.

### 12.1. Zone Partitioning Example

~~~text
Zone "EU"   -> shard01, shard02
Zone "APAC" -> shard03

Tenant key ranges:
  EU tenants   -> EU zone
  APAC tenants -> APAC zone
~~~

If APAC holds 70% of data and only `shard03` is eligible, `shard03` holding more bytes is **not necessarily a balancer bug**.

### 12.2. Zone Compliance Differs from Global Evenness

| Zone | Eligible shards | Data |
|---|---|---:|
| EU | shard01, shard02 | 600 GiB |
| APAC | shard03 | 900 GiB |

Valid target state:

~~~text
EU: shard01 300 GiB, shard02 300 GiB
APAC: shard03 900 GiB
~~~

The balancer cannot move APAC data onto `shard01` when `shard01` is not eligible for that zone.

### 12.3. Diagnosing Zone Skew

1. Identify the namespace and shard key.
2. Read zone key ranges and shard-zone associations.
3. Verify eligible shard count and capacity in each zone.
4. Measure owned bytes and CPU **within each zone**.
5. Check placement compliance and stuck migrations.
6. Confirm data residency requirements before making any changes.

### 12.4. Zone Constraints Causing Migration Failures

A range cannot move if no eligible recipient exists, recipients lack disk space, the range is oversized, or metadata changes mid-operation.

Adding a shard **outside the zone** will not balance that zone's data. Never alter zone tags just to "even out" charts if those tags enforce legal or contractual residency rules.

## 13. Jumbo and Oversized Ranges

A range that grows too large or lacks a valid split point can resist migration, especially when many documents share the exact same shard-key value.

### 13.1. You Cannot Arbitrarily Split a Single Shard-Key Value

~~~text
Shard key:
  customerId = C-00001

Millions of documents with identical shard-key value.
~~~

Without a distinct boundary, you cannot "cut in half" an identical shard-key value to split writes across two shards while preserving shard-key semantics.

### 13.2. Jumbo Markers and Version Limits

MongoDB versions differ in jumbo markers, range sizing, and migration behavior. Do not assume:

~~~text
one range > target chunk size
  -> every migration necessarily impossible
~~~

An oversized range may be moved or rejected depending on server version, size limits, and flags. Read the specific error message and consult version-matched docs.

### 13.3. Diagnosing Jumbo Ranges

Inspect:

- Namespace, shard key, and range boundaries.
- Owned bytes and record count in the range.
- Distribution of distinct shard-key values.
- Migration error logs and reasons.
- Zone placement and recipient eligibility.
- Whether a single hot key is growing continuously.

### 13.4. Never Force-Move Arbitrarily

Forcing a migration can spike disk/network load, degrade latency, violate placement policy, or still fail to split a hot key. Force migration is an approved operational intervention, not dashboard automation logic.

If low entropy is the root cause, revisit the shard key, compound key, or resharding; **adding shards cannot split a single key value**.

## 14. Monitoring Each Shard Replica Set's Health

When distribution is skewed, do not ask only "Which range lives where?"—also verify "Can that shard handle migrations and workload?"

### 14.1. Every Shard Is a Replica Set with Primary and Secondaries

Monitor:

| Metric group | Signals |
|---|---|
| **Replica-set health** | Current primary, available members, elections, health status. |
| **Replication** | Replication lag, oplog window, catch-up rate. |
| **Operations** | Read/write ops/s, queues/concurrency, latency. |
| **WiredTiger cache** | Cache pressure, dirty data, eviction activity. |
| **Storage** | Free space, IOPS, read/write throughput, latency, index sizes. |
| **Network** | Transfer bytes/s, retransmits, donor↔recipient latency. |
| **Resource limits** | CPU saturation, memory pressure, disk throttling. |

Each group spans multiple members. Never compare `shard01`'s primary CPU against `shard02`'s secondary CPU and conclude primary loads are skewed.

### 14.2. Per-`mongod` `serverStatus`

Connect with appropriate privileges to each member:

~~~javascript
const status = db.adminCommand({ serverStatus: 1 });

printjson({
  host: status.host,
  uptime: status.uptime,
  opcounters: status.opcounters,
  connections: status.connections,
  network: status.network,
  opLatencies: status.opLatencies
});
~~~

Output exposes counters and gauges depending on version; some fields may be absent on certain nodes or editions. **Never log raw `serverStatus` publicly**, as it contains sensitive infrastructure details.

### 14.3. Counters Must Be Converted to Rates

A cumulative counter such as total operations since process startup:

~~~text
readsCounter(t0) = 1,000,000
readsCounter(t1) = 1,060,000
deltaTime        = 60 seconds

readRate = (1,060,000 - 1,000,000) / 60
         = 1,000 ops/sec
~~~

Never plot raw cumulative counter values directly as "QPS."

Handle:

- Counter resets on `mongod` restarts or elections.
- Missing samples.
- Metric schema differences across versions.
- Consistent sampling cadence and member roles.

### 14.4. WiredTiger Cache

When cache is under pressure, balancer migrations and application queries compete for I/O and CPU. Monitor cache usage, eviction, and dirty bytes via supported metrics such as fields under **`serverStatus.wiredTiger.cache`** when present.

Never assume "95% cache used" is always an error: database caches aim to utilize memory. Watch **eviction pressure, latency, and disk I/O trends**.

### 14.5. Oplog and Replication Lag

Migration cloning and heavy writes increase replication load. If secondaries fall behind, the cluster can face:

- Durability/replication-related waits.
- Shrinking oplog windows.
- Staler secondary reads.
- Disruptive primary changes or elections.

Monitor **replication lag** and **oplog window** on every shard replica set, plus the CSRS whenever metadata issues appear.

### 14.6. Network and Disk During Migrations

Large range migrations drive heavy network throughput between donor and recipient and increase disk reads/writes. Ask:

- Is network bandwidth approaching link capacity?
- Are disk IOPS or latencies spiking abnormally?
- Is high CPU driven by queries or migration cloning?
- Is client p95 latency climbing simultaneously?

Looking only at CPU makes it easy to mistake migration traffic for hot-key writes.

### 14.7. Free Disk Space and Capacity Runway

A shard receiving data needs **sufficient free space for migrations plus overhead**. Track:

~~~text
diskUsedBytes
diskFreeBytes
diskCapacityBytes
writeGrowthBytesPerDay
migrationIncomingBytesPerDay
estimatedDaysToCapacity
~~~

Under roughly steady growth:

~~~text
daysToCapacity ≈ usableFreeBytes / netGrowthBytesPerDay
~~~

This is a capacity-planning estimate, not a guarantee. The balancer can move data in and out concurrently, while compression and cleanup alter growth rates.

## 15. Choosing Dashboard Metrics to See Both Distribution and Performance

A sharded cluster dashboard needs **four layers**, not just a single "Balancer: ON" badge.

### 15.1. Layer A — Cluster Overview

| Metric | Scope | Question |
|---|---|---|
| `shardCount` | Cluster | Are all shards present? |
| `routerCount`/health | Cluster | Are `mongos` routers up and serving requests? |
| CSRS health | Config replica set | Are metadata and coordination stable? |
| `balancerEnabled` | Cluster | Is balancing allowed to run? |
| `inBalancerRound` | Cluster | Is a balancer round currently executing? |
| `recentMigrationSuccess`/`Failure` | Cluster/namespace | Are migrations making progress? |
| global p95 latency | Application/cluster | Are users impacted? |

### 15.2. Layer B — Per Collection and Shard

| Metric | Minimum labels | Unit |
|---|---|---|
| `ownedDataBytes` | namespace, shard | Bytes |
| `chunkCount` / `rangeCount` | namespace, shard | Ranges |
| `ownedDocumentCount` (if available) | namespace, shard | Documents / estimate |
| `maxToAverageOwnedBytes` | namespace | Ratio |
| `zonePlacementViolations` (if available) | namespace, zone | Count |
| `jumbo`/`oversizedRangeCandidates` | namespace, shard | Ranges |

**Owned bytes** differ from **`storageStats.storageSize`**, because the latter can reflect compression, indexes, orphans, or snapshot factors depending on the metric.

### 15.3. Layer C — Shard/Node Performance

| Metric | Labels | Unit |
|---|---|---|
| read/write QPS | shard, member role | Operations/sec |
| CPU | shard, member | % |
| `diskUsed`/`diskFree` | shard, member/volume | Bytes or % |
| network RX/TX | shard, member | Bytes/sec |
| disk latency | shard, volume | Milliseconds |
| cache eviction pressure | shard, member | Rate/value |
| replication lag | shard, member | Seconds |
| client error/timeout rate | app, endpoint, namespace if available | Requests/sec |

### 15.4. Layer D — Migration/Placement Diagnostics

| Metric | Meaning |
|---|---|
| Balancer rounds started/completed | Is placement evaluation running? |
| Migrations started/committed/failed | Are moves succeeding? |
| Migration duration | Are copy/commit phases slow? |
| Bytes moved per time unit | Rebalancing progress. |
| Orphan cleanup backlog | Disk may not reclaim space yet despite ownership change. |
| Zone compliance | Are ranges on eligible shards? |
| Oversized/jumbo candidates | Are ranges hard or impossible to move? |

Metric names in these tables are **dashboard concepts**, not literal official fields in `serverStatus`. Your exporter, Atlas API, and server version determine exact series names.

### 15.5. Example Dashboard Layout

~~~text
+----------------------------------------------------+
| SHARDED CLUSTER OVERVIEW                           |
| Shards: 3 | Routers: 2 | Balancer: enabled         |
| CSRS: healthy | Migration failures: 0 (last 1h)  |
+----------------------------------------------------+
| OWNED DATA BY SHARD       | WRITE QPS BY SHARD    |
| shard01: 600 GiB          | shard01: 8,000 ops/s  |
| shard02: 300 GiB          | shard02: 1,000 ops/s  |
| shard03: 300 GiB          | shard03: 1,000 ops/s  |
+----------------------------------------------------+
| MIGRATION TREND           | APPLICATION LATENCY   |
| bytes moved / hour        | p50 / p95 / p99       |
| success / failure         | read / write          |
+----------------------------------------------------+
| DISK / CACHE / NETWORK    | ZONES & RANGES        |
| per primary + secondary   | collection selection  |
+----------------------------------------------------+
~~~

The key is placing **owned bytes**, **write QPS**, **migration throughput**, and **latency** side by side so you can distinguish data skew from workload skew.

### 15.6. Avoid High-Cardinality Labels

In Prometheus or a metrics backend:

~~~text
cluster
shard
replica_set
member_role
namespace
environment
zone
~~~

are manageable label dimensions.

Never create a metric label for **every `orderId` or `customerId`** across millions of values: cardinality explosion makes monitoring prohibitively expensive and unstable.

Analyze specific hot keys through **sampling, analytics, or sanitized logs**, not by attaching millions of key values to time-series labels.

### 15.7. Sampling Intervals

Signals change at different speeds:

- CPU/QPS/latency: every few tens of seconds or aligned with SLOs.
- Balancer rounds/migration logs: event-driven or periodic scrape.
- Owned data/skew/chunk counts: every few minutes or slower if queries are heavy.
- Zone metadata: on config changes and periodic audits.

Never run heavy scans over `config.chunks` every 1 second just to render a dashboard.

## 16. Context-Aware Alerting

### 16.1. Owned-Data Skew Alert

Illustrative rule:

~~~text
IF maxToAverageOwnedBytes > 1.5 for 60 minutes
AND collection is expected to balance across these shards
AND no known zone exception
THEN warn: investigate placement
~~~

**1.5 and 60 minutes are examples only**, not MongoDB-mandated thresholds. A cluster with a newly added shard needs time to migrate; small collections with few ranges can naturally look skewed; zone sharding can intentionally concentrate data.

### 16.2. Stalled Balancer

Do not alert solely on:

~~~text
Balancer enabled AND inBalancerRound=false
~~~

That state can be completely normal.

Instead combine conditions:

~~~text
Sustained placement violation
AND balancer allowed to run now
AND repeated rounds show no progress
AND a migration/placement blocker is observed
~~~

Include namespace, zone, donor/recipient, error reason, and a runbook link. Never treat one round with zero migrations as an incident.

### 16.3. Free Disk Space

Track **% used**, **absolute free bytes**, days-to-capacity, and incoming migration volume. 8% free on a 10 TiB volume differs vastly from 8% free on a 100 GiB volume; calibrate against workload, growth, and migration buffer needs.

### 16.4. Migration Failures

~~~text
IF migration errors repeat within 15 minutes
AND matching placement violation persists
THEN alert with namespace, range, donor, recipient and reason
~~~

A transient error that succeeds on retry has different severity from repeated failures due to an oversized range or no eligible recipient.

### 16.5. Workload Hot Spot

Combine:

~~~text
max(writeQPS per primary) / avg(writeQPS per primary)
max(CPU per primary)
application p95 latency
~~~

If owned bytes are balanced yet write QPS ratio and latency climb, suspect the shard key or workload. Never manually move chunks based on CPU without checking hot keys first.

### 16.6. Replication and Zone Health

Alert on replication lag, primary elections, and CSRS health per SLO. For zones, alert on **placement violations or missing eligible shards**, not because APAC legitimately holds more bytes than EU.

### 16.7. Annotate Changes on Dashboards

When adding shards, resharding, changing zones, or running maintenance, add change annotations to charts. Never silence all alerts; keep critical disk, availability, and security alerts active while suppressing only expected notifications during controlled windows.

### 16.8. Suggested Alert Table

| Signal | Illustrative severity | First check |
|---|---|---|
| Newly added shard missing | High | `listShards`, routers, metadata. |
| Sustained placement skew | Warning | `balancerStatus`, compliance, zones. |
| Repeated migration failures | High | logs, recipient health, jumbo ranges. |
| Free disk below minimum headroom | Critical | growth, migration volume, capacity. |
| Repeated primary elections | Critical | replica set/network/disk. |
| One shard high CPU while bytes balanced | Warning/High | hot queries, shard key, `explain`. |
| CSRS unavailable | Critical | CSRS health, cluster impact. |
| Range placed in wrong mandatory zone | High | residency/placement diagnosis. |

Thresholds and severities must be governed by your organization's SLOs, data residency rules, and business requirements.

## 17. Diagnostic Runbooks: From Symptom to Root Cause

### 17.1. Case A — One Shard at 80% Disk

~~~text
shard01 disk used: 80%
shard02 disk used: 35%
shard03 disk used: 32%
~~~

1. Compare disk capacities and free bytes across equivalent member/volume types.
2. Check owned bytes for **each sharded collection**.
3. Compare data, indexes, oplog, storage overhead, orphan cleanup, and fragmentation.
4. Check unsharded collections or local workloads on `shard01`.
5. Verify zones, placement compliance, and migration history.
6. If owned bytes are balanced while physical disk differs, do not blame the balancer.

### 17.2. Case B — Balancer Enabled, Data Unchanged

~~~text
Balancer enabled: yes
Owned bytes:
  shard01 700 GiB
  shard02 200 GiB
  shard03 100 GiB
No movement for hours
~~~

1. Check balancer mode, rounds, and balancing window.
2. Check collection-level compliance: does data actually need to move?
3. Verify eligible recipients in zones.
4. Check recipient free disk space.
5. Check oversized/jumbo candidates.
6. Read migration attempt/error logs.
7. Check CSRS, shard replication, and concurrent resharding/maintenance.

If no eligible recipient exists due to zone rules, restarting the balancer will not help.

### 17.3. Case C — Newly Added Shard Has No Data

~~~text
shard03 added
shard03 owned bytes = 0 after hours
~~~

Verify `shard03` appears in `listShards`, the collection is truly sharded, the balancer is allowed to run, zones permit `shard03`, enough ranges exist to move, and no migration errors occur. Small collections with few ranges may not trigger large moves under current thresholds.

### 17.4. Case D — Bytes Balanced, Yet `shard01` CPU at 95%

~~~text
Owned bytes: 400 / 410 / 390 GiB
CPU:         95% / 35% / 34%
~~~

1. Compare write/read QPS and latency on primaries.
2. Analyze top queries and targeted vs. scatter-gather ratios.
3. Check for hot tenants/values by shard key (protecting PII).
4. Check for ranges holding latest timestamps or single-key hotspots.
5. Inspect indexes, slow query samples, cache, and migration traffic.
6. Only then consider shard key redesign or resharding.

The balancer may already have balanced bytes properly; the problem is **operation distribution**.

### 17.5. Case E — Balancing Drives Up Latency

~~~text
Balancer starts migrations
Network and disk I/O increase
Application p95 latency doubles
~~~

Identify donor and recipient migrations; compare network, IOPS, cache, and replication lag before/after; cross-check against SLOs and maintenance windows. Intervene only via approved incident/change processes—do not auto-disable the balancer whenever CPU rises.

### 17.6. Case F — Donor Disk Does Not Drop After Migration

~~~text
Committed migrations: yes
Owned data on donor: down
Physical disk usage: unchanged
~~~

Causes include pending orphan cleanup, storage engines not returning physical blocks to the OS immediately, fragmentation, oplog/indexes, or ongoing new writes. Check metadata ownership and storage metrics before running costly defragmentation or `compact`.

### 17.7. Case G — Jumbo Range / Hot Single-Key Value

~~~text
Migration fails for same range
Many documents share one shard key value
~~~

Check range bounds, error messages, server version, distinct key values, and zone constraints. Evaluate supported split/move options; consider resharding or a compound key if low shard-key entropy is the root cause. Never force-migrate recklessly in production.

### 17.8. Case H — APAC Zone Concentrated on One Shard

~~~text
APAC: only shard03 eligible
APAC data: 900 GiB
EU data: 600 GiB on shard01 and shard02
~~~

Verify residency rules; forecast `shard03` capacity; evaluate adding eligible shards in APAC. Never move APAC data to EU shards just to make charts look balanced.

### 17.9. Case I — Unstable CSRS Primary

Check the CSRS replica set, network/disk/replication health, metadata/balancer errors, and `mongos` failures. Never manually edit the `config` database; follow topology incident response procedures.

### 17.10. Standard Investigation Order

~~~text
1. Scope: cluster, namespace, version, time window
2. mongos / listShards / CSRS health
3. balancer mode, rounds, collection compliance
4. owned bytes / chunks / disk and trends
5. zones and oversized ranges
6. migration logs and donor/recipient health
7. QPS / CPU / cache / replication / latency
8. query targeting and shard key design
9. operational decision with approval
10. verify impact and document outcome
~~~

Never skip establishing **scope**: a figure like "70%" could refer to node-wide disk, collection owned bytes, chunk count, or write QPS.

## 18. Monitoring When Adding a Shard or Changing the Shard Key

### 18.1. Adding a Shard Is a Capacity Change, Not Instant Rebalancing

When scaling out:

~~~text
Before:
  shard01: 500 GiB
  shard02: 500 GiB

After adding shard03:
  shard01: 500 GiB
  shard02: 500 GiB
  shard03:   0 GiB

After successful eligible migrations:
  shard01: approximately 330 GiB
  shard02: approximately 340 GiB
  shard03: approximately 330 GiB
~~~

These numbers are **desired illustrative examples**, not SLAs or balancing speed guarantees. Zones, range sizes, version, resource limits, and workloads can yield different outcomes.

### 18.2. Pre-Change Baseline

Record:

1. Current shards, `mongos` routers, and CSRS members.
2. Balancer status and configuration.
3. Owned bytes/chunks by collection and shard.
4. Free disk/capacity and peak IOPS/network.
5. Read/write QPS, application p50/p95/p99, error rates.
6. Replica set health and replication lag.
7. Zone constraints and shard-key design.
8. SLOs, RPO/RTO, and maintenance/change windows.

You cannot prove scale-out improved latency without a pre-change baseline.

### 18.3. During Rebalancing

Track over time windows:

~~~text
timestamp
rangeCount and ownedBytes by shard
migrations attempted/committed/failed
balancer enabled and round status
diskFreeBytes by member
network throughput and disk IOPS
replication lag
application p95 latency / error rate
~~~

A single successful migration is not enough; confirm data is moving in **the right collection/zone** with the desired effect.

### 18.4. Post-Rebalance Review

Assess:

- Did owned bytes approach expected placement?
- Do all shards still have sufficient disk headroom for growth?
- Did app latency and throughput improve?
- Did query targeting improve, or are queries still scatter-gather?
- Did workload simply shift from `shard01` to a new hot shard?
- Has orphan cleanup stabilized?
- Are any jumbo/oversized ranges left unresolved?

If bytes are balanced while QPS remains skewed, further shard key or query optimization may be needed.

### 18.5. Resharding and Observation

Resharding changes **a collection's shard key** using the mechanism supported by your MongoDB version. Because it copies and reorganizes large volumes of data, monitor:

- Progress and phases of the resharding operation via official tools.
- Storage/capacity overhead on participating shards.
- Write throughput, replication, disk, and network.
- User-facing latency and error rates.
- Placement compliance after cutover.
- Query targeting behavior with the new key.

**Resharding must never be triggered solely by a disk skew alert.** Analyze the new shard key's properties, application queries, online/downtime behavior, and rollback strategy.

### 18.6. Balancing Across Unequal Capacities

Example:

~~~text
shard01 capacity 4 TiB
shard02 capacity 1 TiB
shard03 capacity 1 TiB
~~~

When workloads or capacities differ significantly, design explicit placement and monitor ratios against free space rather than expecting MongoDB to equalize arbitrary capacity proportions automatically.

### 18.7. Shard Removal / Draining

When removing a shard via supported procedures, the cluster must drain data off the target shard. Monitor:

- Draining status via administrative commands.
- Remaining ranges/bytes on the shard.
- Unsharded collections or unsplittable placement blockers.
- Zone constraints and eligible destination shards.
- Network, disk, and latency during draining migrations.

Never assume a shard "no longer taking writes" is ready to power off; wait for the removal workflow to finish and verify completion.

## 19. Java Sync Driver: Collecting Cluster Information

In Java, **`sh.status()` is a `mongosh` helper**, not a method on `MongoCollection`. The driver can execute supported administrative commands.

### 19.1. Java Sample Reading `listShards` and `balancerStatus`

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ShardingObserver {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI is required"
            );
        }

        // URI must connect to a mongos/router of the sharded cluster.
        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase admin = client.getDatabase("admin");

            Document shards = admin.runCommand(
                    new Document("listShards", 1)
            );
            System.out.println("Shards:");
            System.out.println(shards.toJson());

            Document balancer = admin.runCommand(
                    new Document("balancerStatus", 1)
            );
            System.out.println("Balancer:");
            System.out.println(balancer.toJson());
        }
    }
}
~~~

Notes:

- Use a long-lived, shared **`MongoClient`** in real services.
- Keep URIs and credentials in protected secret stores; never hardcode passwords.
- The monitoring account only needs cluster read privileges appropriate to these commands.
- Balancer/status fields are not immutable across MongoDB versions.
- Log selected summaries rather than dumping raw shard hostnames and metadata.

### 19.2. Collecting Collection-Level Storage Statistics

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public final class CollectionStorageObserver {

    private final MongoClient client;

    public CollectionStorageObserver(MongoClient client) {
        this.client = client;
    }

    public void inspectOrders() {
        MongoCollection<Document> orders =
                client.getDatabase("commerce")
                        .getCollection("orders");

        Bson collStats = new Document(
                "$collStats",
                new Document(
                        "storageStats",
                        new Document("scale", 1048576)
                ).append(
                        "count",
                        new Document()
                )
        );

        orders.aggregate(List.of(collStats))
                .forEach(document -> {
                    // In production, parse schema according to server version.
                    // Do not send entire sensitive documents to logs.
                    System.out.println(document.toJson());
                });
    }
}
~~~

This snippet illustrates querying **`$collStats`**. Verify field meanings and per-shard semantics on your server and driver version. Never grab an arbitrary byte field and rename it "ownedBytes" if it actually measures storage size or compressed size.

### 19.3. Computing Skew in Java from Validated Samples

Once you have a consistent map of **ownedBytes per shard** from a reliable stats source:

~~~java
import java.util.Map;

public final class SkewCalculator {

    public static double maxToAverage(
            Map<String, Long> ownedBytesByShard) {

        if (ownedBytesByShard.isEmpty()) {
            throw new IllegalArgumentException(
                    "No shard samples"
            );
        }

        double total = 0.0;
        double max = 0.0;

        for (long bytes : ownedBytesByShard.values()) {
            if (bytes < 0) {
                throw new IllegalArgumentException(
                        "Negative bytes"
                );
            }

            total += bytes;
            max = Math.max(max, bytes);
        }

        double mean = total / ownedBytesByShard.size();
        return mean == 0.0 ? 0.0 : max / mean;
    }
}
~~~

Example:

~~~java
double skew = SkewCalculator.maxToAverage(
        Map.of(
                "shard01", 600L,
                "shard02", 300L,
                "shard03", 300L
        )
);

// skew = 1.5
~~~

This only handles **computation from normalized input metrics**; it does not read `ownedBytes` uniformly across every MongoDB version by itself.

### 19.4. Do Not Turn the Monitoring Collector into a Heavy Load Generator

If a collector runs across 100 `mongos` instances:

~~~text
100 collectors
    x 1 aggregate over all config.chunks each second
    = 100 expensive metadata queries/sec
~~~

Instead:

- Elect a single collector/leader for cluster-wide metadata queries.
- Cache and scrape results at reasonable intervals.
- Never write to the `config` database or trigger migrations.
- Enforce timeouts, backoff, and rate limiting.
- Keep metric labels low-cardinality.
- Use native Atlas, Ops Manager, or exporter metrics where sufficient.

### 19.5. Do Not Put Cluster Admin Monitoring on the Application HTTP Request Path

An HTTP API doing:

~~~text
GET /orders
  -> listShards
  -> balancerStatus
  -> $collStats
  -> find orders
~~~

is poor design. Run diagnostic commands **asynchronously in a dedicated monitoring/ops service** with separate permissions and cadence; business APIs should simply query data using appropriate shard keys.

## 20. Spring Data MongoDB and Infrastructure Observability

### 20.1. `MongoTemplate.executeCommand`

In Spring Data MongoDB, admin commands can run via **`MongoTemplate`** when configured with the right database, connection, and privileges:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ShardingStatusService {

    private final MongoTemplate mongoTemplate;

    public ShardingStatusService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document balancerStatus() {
        return mongoTemplate.executeCommand(
                new Document("balancerStatus", 1)
        );
    }
}
~~~

**Ensure `MongoTemplate` connects through `mongos` with an authorized account**, and confirm the command targets the intended database (`admin`). In production, use a dedicated monitoring client if the runtime application user lacks `clusterMonitor` privileges.

### 20.2. What to Separate in Spring Boot

~~~text
Business request path:
  repository -> MongoDB through mongos

Monitoring path:
  scheduled collector -> supported read-only stats
                     -> Micrometer/metrics backend
~~~

Never invoke `balancerStatus` or config metadata queries on every API request.

### 20.3. Micrometer-Style Metrics

If an application collects normalized metrics, it can export:

~~~text
mongo_shard_owned_bytes{cluster="prod",namespace="commerce.orders",shard="shard01"} 644245094400
mongo_shard_owned_bytes{cluster="prod",namespace="commerce.orders",shard="shard02"} 322122547200
mongo_shard_owned_bytes{cluster="prod",namespace="commerce.orders",shard="shard03"} 322122547200

mongo_shard_data_skew_max_mean{cluster="prod",namespace="commerce.orders"} 1.5
~~~

These metric names are **chosen by the collector designer**, not built-in defaults from MongoDB or Spring Boot. Illustrative values convert 600/300/300 GiB into binary bytes.

### 20.4. Production Exporter Rules

1. Document **metric semantics** and bytes/GiB units clearly.
2. Record observation timestamps.
3. Mark failed/missing measurements instead of holding stale values forever.
4. Never sum shard samples taken from widely separated epochs.
5. Never export millions of `tenantId`/`orderId` values as Prometheus labels.
6. Avoid exposing raw config metadata with hostnames/keys on public endpoints.
7. Protect metrics endpoints with network policies and authentication.
8. Separate cluster-wide scrape frequency from node CPU sampling.

## 21. Factors That Make Distribution Charts "Confusing"

### 21.1. Unsharded Collections Living on a Database's Primary Shard

In a sharded cluster, each database has a **primary shard** storing unsharded collections and related data depending on MongoDB version. If a massive unsharded collection sits on `shard01`:

~~~text
commerce.orders (sharded):
  shard01: 300 GiB
  shard02: 300 GiB
  shard03: 300 GiB

commerce.audit_archive (unsharded):
  shard01: 800 GiB
  shard02:   0 GiB
  shard03:   0 GiB
~~~

Physical disk on `shard01` will be much larger even though **`orders`** is perfectly balanced.

The range balancer does not automatically split an unsharded collection across shards just because the cluster has multiple shards. Mechanisms to move unsharded collections or shard them vary by MongoDB version; consult official docs before acting.

### 21.2. Replica Set Members vs. Logical Shard Size

If `shard01` has three replica set members each storing 300 GiB:

~~~text
Logical shard01 data: ~300 GiB
Physical copies across three members: ~900 GiB
~~~

Never sum all three replica members and report **900 GiB owned data on `shard01`** while counting only the primary on another shard.

Clarify whether your dashboard tracks:

- Logical owned data.
- Physical bytes on a single member.
- Total physical bytes across all replicas.

Each serves a distinct purpose.

### 21.3. Compression Differences

Two shards with identical logical document bytes can compress differently based on data content:

~~~text
shard01 contains highly repetitive documents
shard02 contains random or already-compressed blobs
~~~

Physical `storageSize` can differ despite equal logical data size. Index cardinality and key patterns also affect index bytes.

### 21.4. One Shard Receiving Heavy Secondary Reads

If the application routes reads to secondaries, one shard's secondaries may show high CPU even when primary writes are evenly balanced. Monitor **read distribution by member role** and query targeting, not just primary write rate.

### 21.5. Bytes Are Balanced, Yet One Node Has Poor Disk IOPS

Two shards hold 500 GiB each, yet one runs on a slower disk or suffers noisy neighbors. Differing latency does not mean placement is skewed.

Check disk latency, throttling, CPU steal, and network alongside sharding metrics.

### 21.6. One Shard Holds Extra Index Overhead

Normally a sharded collection's indexes are built uniformly, yet manual actions, migration issues, or mixed collections can create differing index/storage overhead across shards.

Compare index sizes and query plans in addition to document data. Never drop indexes on a single shard directly outside proper sharded collection management procedures.

### 21.7. Orphan Cleanup and Fragmentation

After a range migration:

~~~text
ownedDataBytes(shard01) decreases
storageSize(shard01) might not fall immediately
diskAllocatedBytes might remain high
~~~

This does not prove migration failed. Monitor orphan cleanup and storage-engine behavior; do not use `diskUsed` as the sole proxy for logical ownership.

### 21.8. Balancer Working Properly, Yet Zone Placement Looks Globally Uneven

Some shards are ineligible for a zone's data. Compute skew across the **eligible shard set** or annotate zone constraints clearly. Avoid feeding a single-shard zone into a "make all shards equal" calculation without context.

### 21.9. Small Collections or Sparse Data

A collection with only a few ranges or a few MiB of data may show uneven range/byte ratios with zero SLO impact. Firing high max/min alerts on tiny datasets generates noise.

Enforce a **minimum data size/traffic threshold** before treating skew as actionable.

### 21.10. Measurements Captured at Different Times

If `shard01` just received a migration while `shard02` just finished orphan cleanup, unsynchronized counters can create the illusion that data appeared or vanished. Align timestamps/measurement windows and log active migrations.

### 21.11. Node Restart Resetting Rate Counters

When `serverStatus` counters reset:

~~~text
ops counter at t0: 9,000,000
node restarts
ops counter at t1: 10,000
~~~

Direct subtraction yields a nonsensical negative rate. The monitoring backend must detect counter resets/restarts, handle rate calculation safely, and flag missing samples.

### 21.12. Time-Varying Query Workloads

A batch import at 01:00 can heat up `shard01` for a few hours while daytime traffic stays balanced. Compare charts across **the same time of day/week** and business events before deciding to reshard.

## 22. Daily and Pre-Change Operational Checklists

### 22.1. Periodic Checks

- [ ] `mongos` routers are reachable; app error rates are within SLO.
- [ ] `listShards` returns the expected inventory.
- [ ] Config server replica set is healthy.
- [ ] Shard replica set primaries and secondaries are healthy with acceptable replication lag.
- [ ] `balancerStatus` reflects the expected mode.
- [ ] Collection placement/skew is within zone/policy bounds.
- [ ] Migration error trends are reviewed.
- [ ] Owned bytes and physical disk are measured separately.
- [ ] Disk headroom covers expected growth and migrations.
- [ ] Application p95/p99 latency shows no anomalous spikes.
- [ ] Critical queries are well-targeted by shard key.
- [ ] Monitoring alerts contain no credentials, PII, or raw config secrets.

### 22.2. Before Adding a Shard

- [ ] Prove whether the bottleneck is capacity/placement or workload/hot key.
- [ ] Size replica set config, network, and storage capacity appropriately.
- [ ] Define zones and shard eligibility.
- [ ] Capture baseline owned bytes, QPS, latency, and replication metrics.
- [ ] Confirm balancing window and change approval.
- [ ] Estimate data volume to migrate and disk headroom.
- [ ] Verify backups/DR and current monitoring are operational.
- [ ] Define success criteria and rollback/incident plan.

### 22.3. When the Balancer Makes No Progress

- [ ] Distinguish enabled vs. currently running.
- [ ] Check collection-level placement compliance.
- [ ] Confirm current time is inside the balancing window.
- [ ] Check zones and recipient eligibility.
- [ ] Check free disk space, network, and primary elections.
- [ ] Check for jumbo/oversized ranges.
- [ ] Correlate migration logs along the timeline.
- [ ] Never edit the `config` database directly.
- [ ] Never force migrations without approval.

### 22.4. When CPU/QPS Is Skewed

- [ ] Measure per-shard write QPS and per-member read QPS.
- [ ] Inspect hot shard-key values via controlled telemetry/logs.
- [ ] Check shard key cardinality and monotonicity.
- [ ] Check targeted vs. scatter-gather query distribution.
- [ ] Inspect indexes and latency/slow query patterns.
- [ ] Rule out migration or backup traffic.
- [ ] Consider resharding only after gathering evidence.

### 22.5. After Scaling Out / Resharding

- [ ] Did owned bytes/ranges shift as expected for the target namespace?
- [ ] Is zone compliance still intact?
- [ ] Have migrations completed, or is any blocker clearly understood?
- [ ] Did any new hot shard emerge?
- [ ] Are application p95/p99 and errors acceptable?
- [ ] Is free disk space still adequate?
- [ ] Is orphan cleanup progressing without capacity risk?
- [ ] Are monitoring baselines and thresholds updated for the new topology?
- [ ] Are postmortem/change records documented if needed?

## 23. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating balancer enabled as actively migrating | Misleading status reporting. | Distinguish enabled, mode, round, and migration outcomes. |
| Equal chunk counts mean equal data | Hides vastly different range sizes. | Measure owned bytes per collection. |
| Equal disk means equal CPU | Misses hot keys and query patterns. | Measure QPS, CPU, and latency. |
| Unequal disk means broken balancer | Confuses indexes, oplog, orphans, unsharded data. | Separate logical and physical metrics. |
| Auto-restarting balancer when no migrations run | Causes unnecessary operational churn. | Check compliance, window, and zones first. |
| Adding shards to split a single hot key | Bottleneck persists unchanged. | Address shard key entropy and resharding. |
| Comparing bytes across shards in different zones | False alarms under residency rules. | Compare eligible shards within each zone. |
| Ignoring free disk on recipient shards | Migrations fail or stall. | Capacity planning and headroom checks. |
| Reading `config.chunks` and editing it directly | Risk of corrupting routing metadata. | Keep read-only; use supported admin commands. |
| Hardcoding a rigid `config.chunks` parser | Breaks when `uuid`/`ns` schema changes. | Stay version-aware; prefer official helpers. |
| Treating `numBalancerRounds` as chunks moved | Wrong metric definition. | Track migration commits and owned-byte deltas. |
| Counting orphan copies as new logical data | Inflates owned byte counts. | Track owned vs. physical separately. |
| Expecting the balancer to fix queries missing shard keys | Scatter-gather persists. | Fix query targeting. |
| Querying a shard primary directly instead of `mongos` | Risks partial reads. | Route sharded collection queries via `mongos`. |
| Counting 3 replica members as 3 shards | Overstates logical shard count. | Distinguish RS member vs. shard ID. |
| Calling monitoring commands on every API request | Adds needless load. | Use a dedicated scheduled collector. |
| Putting millions of `tenantId` values in metric labels | Explodes time-series cardinality. | Bound label cardinality; analyze hot keys separately. |
| Firing high skew ratio alerts on tiny datasets | Noisy false alarms. | Enforce minimum bytes/QPS/time windows. |
| Diagnosing 95% CPU without checking I/O and migrations | Misidentifies root cause. | Correlate latency, I/O, cache, and QPS. |
| Resharding immediately upon seeing skew | High risk without proven benefit. | Baseline, `explain`, design review, and canary plan. |
| Treating `config.changelog` as permanent full audit | Misses history due to retention/version. | Maintain dedicated log and metrics pipelines. |
| Omitting metric timestamps | Compares data from mismatched epochs. | Record timestamps and consistency windows. |
| Dividing raw counter by 60 without taking delta | Wrong rate. | Compute rate from two samples and handle resets. |

## 24. Hands-On Exercises

### Exercise 1 — Drawing a Sharded Cluster Diagram

Draw a diagram with **two `mongos` routers, one config server replica set, and three shard replica sets**. Label which component receives queries, which stores routing metadata, and which stores documents.

### Exercise 2 — Counting Shards Accurately

A cluster has three shards, each a three-member replica set, plus a three-member config server replica set. How many **logical shards** exist? Why does replica member count not equal shard count?

### Exercise 3 — `listShards`

Connect to `mongos` and run:

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

List the fields you need to verify shard inventory and host mappings. Explain why command success does not prove every replica set member is healthy.

### Exercise 4 — `sh.status`

Run `sh.status()` in `mongosh` and identify:

1. Sharded collections.
2. Each collection's shard key.
3. Distribution/placement info shown in that version's output.
4. Whether any zone constraints exist.

Do not overwrite or alter config metadata.

### Exercise 5 — Four Types of Skew

A cluster shows:

~~~text
Chunks:       100 / 100 / 100
Owned bytes:  900 / 100 / 100 GiB
CPU:          90 / 30 / 25 %
Disk used:    75 / 35 / 34 %
~~~

Classify chunk-count, owned-byte, workload, and physical-storage skew. Why can't you assume every metric reflects the same root cause?

### Exercise 6 — Data Share

Given 600/300/300 GiB owned bytes, calculate each shard's share of the total. What percentage does the largest shard hold?

### Exercise 7 — Max-to-Average Skew

Using the same 600/300/300 GiB numbers, compute `averageOwnedBytes` and `maxToAverageSkew`.

### Exercise 8 — New Empty Shard

A cluster has owned bytes 500/500/0 GiB. Why is max-to-min ratio unhelpful? Compute the max-to-average ratio and propose an additional metric to track during rebalancing.

### Exercise 9 — Charts with Zones

Shards 1–2 belong to zone EU, and shard 3 belongs to zone APAC. APAC holds 70% of data. Propose how to evaluate placement compliance without forcing all 3 shards to equal owned bytes.

### Exercise 10 — Balancer Enabled vs. Running

Suppose:

~~~javascript
{
  mode: "full",
  inBalancerRound: false,
  ok: 1
}
~~~

Can you conclude the balancer is broken? Which conditions must you check first?

### Exercise 11 — `balancerCollectionStatus`

Run the command if supported by your server version:

~~~javascript
db.adminCommand({
  balancerCollectionStatus: "commerce.orders"
});
~~~

Explain why a collection-level compliance signal is more informative than looking only at cluster-wide status.

### Exercise 12 — Migration Donor and Recipient

Trace a range moving from `shard01` to `shard02`, including data cloning, catch-up, ownership commit, and orphan cleanup. Why can the recipient hold bytes before metadata commit yet not be the owner?

### Exercise 13 — Donor Disk Does Not Shrink

After 30 successful migrations, owned bytes on `shard01` dropped by 100 GiB, yet physical disk barely moved. List four hypotheses to check.

### Exercise 14 — Slow Migrations

A migration runs for hours. Donor disk IOPS is near saturation, replication lag on the recipient rises, and application p95 latency increases. Propose evidence-gathering steps and a decision aligned with change/SLO processes.

### Exercise 15 — Faulty Alert

Current alert:

~~~text
If balancerEnabled=true and inBalancerRound=false
then Critical
~~~

Why is this alert wrong? Rewrite it using collection compliance and progress/failure signals.

### Exercise 16 — Hashed vs. Ranged Shard Key

Compare:

~~~javascript
{ createdAt: 1 }
~~~

with:

~~~javascript
{ customerId: "hashed" }
~~~

Which one concentrates timestamp inserts onto a trailing edge range? When does a hashed key make range queries on `customerId` less natural?

### Exercise 17 — Hot Tenant

One tenant drives 60% of write QPS while the collection's owned bytes are balanced. How will you analyze cardinality, top shard-key values, primary CPU, and query patterns?

### Exercise 18 — Query Targeting

For a collection sharded by `customerId`, compare:

~~~javascript
db.orders.find({ status: "PENDING" });

db.orders.find({
  customerId: "C-100",
  status: "PENDING"
});
~~~

Which query has a better chance of being targeted? How do you verify with `explain`?

### Exercise 19 — Metadata Query Reading Chunks

Write a read-only query against `config.chunks` to group `rangeCount` by shard for a collection, choosing between `uuid` and `ns` per schema version. Why should you never update `config.chunks` directly?

### Exercise 20 — Unsharded Collection Skewing Disk

Collection `orders` is sharded evenly at 300 GiB per shard. Unsharded collection `audit_archive` holds 800 GiB on the database's primary shard. What will the total-disk dashboard show? Why won't the range balancer for `orders` fix it?

### Exercise 21 — Counters to QPS

A counter rises from 1,000,000 to 1,060,000 over 60 seconds. Calculate ops/sec. If the node restarts between the two samples, what must the collector do?

### Exercise 22 — Replication Lag

A shard has 2 secondaries, and one lags by 120 seconds. Which additional metrics should you inspect: oplog window, disk throughput, network, read preference, and migration effects?

### Exercise 23 — Jumbo Range

A large range holds millions of documents sharing the same `customerId`. Explain why a split point may not exist. Propose two architectural solutions and one safety principle before considering a forced migration.

### Exercise 24 — Scale-Out

A cluster adds `shard03`. Design a before/during/after migration dashboard covering owned bytes, migrations attempted/committed/failed, free disk, CPU, and application p95.

### Exercise 25 — Zone Placement

EU zone has two shards and APAC has one shard. If APAC data grows rapidly, which capacity expansion options preserve residency policy?

### Exercise 26 — Prometheus Cardinality

An exporter plans to emit:

~~~text
mongo_hot_customer_qps{customerId="..."}
~~~

across ten million `customerId` values. What is the risk? Propose a lower-cardinality label set.

### Exercise 27 — `$collStats`

Write an aggregation pipeline using **`$collStats`** to fetch `storageStats` and `count` for `orders`. Explain why output storage bytes do not automatically equal logical owned bytes of a sharded collection.

### Exercise 28 — Java Sync Driver

Write a Java monitoring utility running:

~~~javascript
db.adminCommand({ listShards: 1 });
db.adminCommand({ balancerStatus: 1 });
~~~

using `MongoDatabase.runCommand` and `Document`. Explain the requirement to route the URI through `mongos` and account permissions.

### Exercise 29 — Computing Skew in Java

Write a function taking `Map<String,Long> ownedBytesByShard` and returning the max/mean ratio. Handle empty maps, negative values, and `total bytes = 0`.

### Exercise 30 — Spring Data MongoDB

Write a scheduled collector using `MongoTemplate` or a dedicated monitoring `MongoClient`. Why shouldn't `balancerStatus` run inside every HTTP request?

### Exercise 31 — Disk Exhaustion Forecast

A shard has 300 GiB free and grows at a net 20 GiB/day. Estimate preliminary runway in days. If the balancer is about to migrate an extra 150 GiB onto this shard, why must the initial estimate be updated?

### Exercise 32 — Comparing Capacities

`shard01` holds 600 GiB owned on a 2 TiB disk; `shard02` and `shard03` each hold 300 GiB owned on 500 GiB disks. Compute owned/capacity percentages. Should you force owned bytes equal if doing so pushes the two smaller shards near full?

### Exercise 33 — Config Changelog

Run a read-only query for migration events in `config.changelog` if available. If no results return, can you conclude the cluster has never migrated chunks? Why or why not?

### Exercise 34 — Migration Throughput vs. Availability

Migrations run at 100 GiB/hour, yet API p95 latency doubles. Which SLOs—not just bytes moved—must define "success"?

### Exercise 35 — Writing a Production Runbook

A dashboard alert fires:

~~~text
Collection commerce.orders:
  max-to-average owned data skew = 1.8
  3 hours persistent
  balancer enabled
  50 migration errors in 1 hour
  shard03 disk free < 10 GiB
~~~

Outline the investigation order, data to inspect, and actions that **must not** be taken without approval.

## 25. Review Questions

1. What is the role of `mongos` in a sharded cluster?
2. Which metadata does the CSRS store?
3. Why is a shard replica set different from a single replica set member?
4. Which resource does the balancer manage?
5. What is a range/chunk?
6. How does a range migration differ from a split?
7. Why does splitting a range not mean data moved to another shard?
8. Why does chunk-count balance not guarantee owned-bytes balance?
9. Why does owned-bytes balance not guarantee disk balance?
10. Why does disk balance not guarantee workload balance?
11. By what mechanism does a monotonically increasing shard key create a hotspot?
12. What does a hashed shard key solve, and what does it not solve?
13. Can high cardinality still suffer from a hot key?
14. What risk do queries missing the shard key carry?
15. How can `explain` identify targeted shards?
16. How does zone sharding constrain balancing?
17. When a zone has only one eligible shard, can global skew be valid?
18. What causes jumbo/oversized ranges?
19. Why shouldn't you force-migrate a huge range without investigating?
20. What does `listShards` return?
21. What information can `sh.status` reveal?
22. How does `balancerStatus` differ from `sh.getBalancerState`?
23. Why does `inBalancerRound=false` not prove the balancer is broken?
24. Why is `numBalancerRounds` not the count of successful migrations?
25. How do you distinguish migration commit from orphan cleanup?
26. How do data share, max-to-average skew, and max-to-min skew differ?
27. Why is max-to-min ratio hard to use when a new shard is empty?
28. Which node-level metric groups should you check when migrations are slow?
29. Why must you compute rates from cumulative counters?
30. How do orphaned documents affect physical disk usage?
31. How do unsharded collections skew overall disk dashboards?
32. Why is CSRS health a critical part of observability?
33. Why must you never edit `config.chunks` directly?
34. How can config metadata schemas change across server versions?
35. Why must hostnames and cluster details be filtered/protected in monitoring logs?
36. Why shouldn't you place `customerId` with millions of values into metric labels?
37. Which alerts should combine zone compliance with balancer status?
38. When adding a shard, what must be measured before and after?
39. Which extra resources can resharding require?
40. Why must a good dashboard also include application latency?

## 26. Summary: Viewing Data Distribution Alongside Health and Workload

A MongoDB sharded cluster has multiple layers, each offering a distinct perspective on system health:

~~~text
                    User-facing SLO
                  latency, errors, QPS
                          |
                          v
                    mongos routing
                targeted vs scatter-gather
                          |
                          v
              shard primaries/secondaries
           CPU, cache, disk, replication lag
                          |
                          v
             owned ranges/data per shard
              chunk count, bytes, zones
                          |
                          v
           balancer, migrations, CSRS state
              rounds, errors, compliance
~~~

### 26.1. A Fast Evidence-Based Decision Flow

~~~text
Observed skew?
     |
     +-- Chunk counts unequal only
     |       |
     |       v
     |   Compare owned bytes and placement compliance.
     |
     +-- Owned bytes unequal
     |       |
     |       v
     |   Check zones, balancer, range sizes and migrations.
     |
     +-- Physical disk unequal
     |       |
     |       v
     |   Check indexes, oplog, orphan cleanup and unsharded data.
     |
     +-- CPU / QPS unequal
             |
             v
         Check hot key, shard key, query targeting,
         indexes, read preference and infrastructure.
~~~

Never choose a remediation before knowing which type of skew you are observing.

### 26.2. Five Key Commands and Investigation Sources

| Tool | What it answers |
|---|---|
| **`sh.status()`** | Cluster sharding overview, collections, and placements per version. |
| **`listShards`** | List of shards configured in the cluster. |
| **`balancerStatus`** | Cluster-level balancer operational status. |
| **`getShardDistribution()`** | Distribution of a sharded collection per helper/version. |
| **`$collStats`, `serverStatus`, `rs.status`, and metrics dashboards** | Data/storage stats and health of individual nodes and replica sets. |

When deeper insight is needed, consult **`balancerCollectionStatus`**, migration logs, read-only config metadata, and query `explain`. Never write directly to the `config` database as a "quick fix."

### 26.3. Signs That Classify Root Causes

**If owned bytes are skewed and migrations repeatedly fail**: inspect the balancer, zones, recipient disk, oversized ranges, and CSRS/replication health.

**If bytes are balanced yet CPU is skewed**: focus on hot shard-key values, query targeting, indexes, read preference, or hardware. The balancer may already be doing its job properly.

**If disk does not shrink after migrations**: check orphan cleanup, indexes, storage-engine behavior, and counters; transferred ownership does not mean immediate space reclamation to the OS.

**If zones put more data on one shard**: balancing must honor eligible placement; data residency can outweigh cluster-wide uniformity.

**If a shard was just added**: allow balancing policies/thresholds to operate and track progress rather than expecting the new shard to hold an equal share immediately.

### 26.4. Key Principles

1. **Shard count and replica set member count are two different quantities.**
2. **Balancer enabled does not mean migrations are currently running or needed.**
3. **Chunk count, owned bytes, physical disk, and workload QPS/CPU are four distinct metric groups.**
4. **Migrations have multiple phases; ownership commit and orphan cleanup do not happen simultaneously in disk metrics.**
5. **Zone compliance can outweigh global evenness.**
6. **Shard key cardinality, frequency, monotonicity, and query targeting govern hot shards.**
7. **Jumbo/oversized ranges must be diagnosed by version, never force-moved blindly.**
8. **Replication lag, network, cache, and disk I/O can block or slow balancing.**
9. **Every skew measurement requires unit, namespace, shard, timestamp, and capacity context.**
10. **Measure success via application latency, throughput, availability, and SLOs—not solely bytes moved.**
11. **Use official read commands and metric sources; never edit config metadata manually.**
12. **Any production change to balancer, shard key, zones, or migration policy requires evidence and approval.**

### Official MongoDB Documentation

- [Sharding — Overview](https://www.mongodb.com/docs/manual/sharding/) — sharded cluster architecture.
- [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/) — shards, `mongos`, and config servers.
- [Sharding Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — balancing, range migrations, and administration.
- [Manage the Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — balancer states and commands.
- [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/) — cluster sharding overview.
- [listShards Command](https://www.mongodb.com/docs/manual/reference/command/listShards/) — listing shards.
- [balancerStatus Command](https://www.mongodb.com/docs/manual/reference/command/balancerStatus/) — checking balancer status.
- [balancerCollectionStatus Command](https://www.mongodb.com/docs/manual/reference/command/balancerCollectionStatus/) — collection placement status (where supported).
- [getShardDistribution()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getShardDistribution/) — collection distribution details.
- [$collStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/collStats/) — collection storage statistics.
- [serverStatus Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — node-level server metrics.
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/) — placement constraints and zones.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency, and query patterns.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — changing shard keys and considerations.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — `MongoClient`, `runCommand`, and aggregation.
- [Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/) — `MongoTemplate` and framework integration.

Helpers, collection metadata fields, balancer behavior, and metrics vary across MongoDB versions and deployments. Before implementing—especially before placement changes—verify against documentation for your exact **server version, `mongosh`, driver, and cluster type**.

**Conclusion:** reliable shard observability must answer three questions at once: **Where does the data live? What can the balancer do and what is it doing? Are users affected by that distribution?** Only by connecting all three layers with timestamped, well-scoped measurements can you tell a properly balanced cluster apart from one with genuine skew that needs action.
