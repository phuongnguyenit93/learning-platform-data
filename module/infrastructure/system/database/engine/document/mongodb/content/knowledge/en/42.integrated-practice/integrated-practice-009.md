# Testing Sharding in an Isolated Environment and Measuring Data Distribution in MongoDB

## 1. Scenario: Having Two Shards Does Not Mean Data Splits Evenly by Itself

An application ingests order events at a steadily growing rate. When data outgrows the storage and processing capacity of a single MongoDB replica set, the engineering team wants to test **sharding** to distribute data and load across multiple shards.

They build a two-shard cluster, write 20,000 documents, and observe:

~~~text
shard A: 19.800 documents
shard B:    200 documents
~~~

Sharding may be enabled, yet the shard key is unsuitable, chunks have not been distributed, or the system does not yet have enough data for the balancer to make changes. Having two shards does **not** prove that data, queries, or writes are distributed evenly.

This lesson belongs to the **Database Engine Document MongoDB** module, **Integrated Practice** chapter, with the topic **Testing Sharding in an Isolated Environment and Measuring Data Distribution**.

### 1.1. Expected Outcomes

After completing this lab, you will be able to:

1. Explain the roles of `mongos`, the config server replica set (CSRS), shard replica sets, chunks/ranges, and the balancer.
2. Stand up a sharded cluster **isolated from production**, without exposing public database ports.
3. Initialize the config server, two shard replica sets, and add shards through `mongos`.
4. Create two comparable collections: one with a **hashed shard key**, and one with a **ranged shard key**.
5. Generate the same data workload with a fixed document count and payload.
6. Measure **owned documents, owned data size, chunk count, and orphan documents** per shard.
7. Calculate distribution skew and distinguish chunk balance from storage/load balance.
8. Use `sh.status()`, `sh.getShardedDataDistribution()`, `getShardDistribution()`, and `config.chunks` metadata strictly for observation.
9. Observe the balancer, and split and move ranges in the **lab** under controlled conditions.
10. Compare query targeting: queries containing the shard key versus scatter-gather queries.
11. Analyze hot shards, low-cardinality shard keys, jumbo ranges, and hashed/ranged trade-offs.
12. Measure latency/throughput with the same workload without over-extrapolating from a laptop.
13. Produce a reproducible experiment report explaining variance and limitations.
14. Clean up the lab without affecting any other deployment.

**Safety rule:** All examples below are intended solely for a **local Docker Compose environment or approved staging**. Never run `sh.addShard()`, `sh.moveChunk()`, `rs.initiate()`, `dropDatabase()`, or alter the balancer in production to "experiment".

## 2. What Sharding Is and What It Is Not

MongoDB sharding distributes a **sharded collection** across shards based on **shard key** values.

~~~text
Application / mongosh
          |
          v
       mongos
    (query router)
          |
          +---------- Config Server Replica Set
          |             - collection metadata
          |             - chunk/range ownership
          |
          +---------- Shard A Replica Set
          |             - owned ranges/documents
          |
          +---------- Shard B Replica Set
                        - owned ranges/documents
~~~

- **mongos**: receives commands from applications, routes them to the required shards, and merges results.
- **Config server replica set**: stores metadata about cluster topology, sharded namespaces, and range ownership.
- **Shard**: typically a replica set holding a subset of the data.
- **Shard key**: one or more fields used to determine where data lives.
- **Chunk/range**: a contiguous range of shard key values owned by a single shard.
- **Balancer**: monitors range/chunk distribution and migrates them when needed.

### 2.1. Sharding Differs from Replication

| Characteristic | Replica set | Sharded cluster |
|---|---|---|
| Primary goal | High availability and durability | Horizontal data distribution/scale |
| Data per node | Members replicate the same shard dataset | Each shard stores a subset, replicated within the shard |
| Failover | Primary election within the replica set | Replica set election within each shard + CSRS |
| Query routing | Driver topology discovery | `mongos` routes using metadata |
| Configuration | Replica set members | CSRS, mongos, and multiple shards |

### 2.2. Not Every Collection Is Sharded

A database inside a sharded cluster can contain unsharded collections. They may still reside on a primary shard rather than being distributed by a shard key.

### 2.3. Do Not Equate a Shard with a Physical Server

In the lab, two shards may be two containers running on **the same laptop**. They have separate sharding logic, yet still share CPU, RAM, disk, and the Docker bridge. Never use these results to assume double the speed in production.

## 3. Define Data Distribution Metrics Before Measuring

Measure at least four metrics:

| Metric | Meaning | Can Be Misinterpreted When |
|---|---|---|
| Owned documents | Number of documents belonging to a shard by routing ownership | Many chunks but few documents |
| Owned size bytes | Uncompressed size of documents owned by the shard | Confused with disk usage/WiredTiger |
| Chunk/range count | Number of shard-key ranges owned by the shard | Chunks have unequal sizes |
| Orphan documents | Temporary copies left after range migration awaiting deletion | Adding orphans into the logical dataset |
| Query targeting | How many shards a query touches | Data is balanced, yet queries scatter |
| Read/write utilization | CPU, I/O, ops/s, and latency per shard | One shard serves a hot key |

### 3.1. Example: "Balanced Chunks, Skewed Data"

~~~text
Shard A:  4 chunks, 90.000 documents, 300 MB owned
Shard B:  4 chunks, 10.000 documents,  40 MB owned
~~~

The chunk counts are equal, yet document counts and bytes differ dramatically.

### 3.2. Example: "Balanced Documents, Skewed Load"

~~~text
Shard A: 50.000 docs, 500 read ops/s
Shard B: 50.000 docs, 9.000 read ops/s
~~~

A hot tenant/key can overload shard B even when data distribution is perfectly balanced.

### 3.3. Define Your Own Acceptance Criteria

A two-shard lab can set a reference target such as `maxDocumentShare ≤ 60%`, but that is a **self-defined acceptance threshold for the experiment**, not a MongoDB guarantee. On a real cluster, bytes, query distribution, zones, and workload determine what balance is actually useful.

## 4. Why an Isolated Environment Is Necessary

Sharding commands can:

- Create additional metadata and indexes.
- Migrate ranges, causing I/O, network, and replication traffic.
- Alter query routing.
- Trigger chunk migrations and range deletion.
- Generate load or lock contention.
- Impact availability if misconfigured.

### 4.1. Plan for This Lab

We use a Docker Compose project named **mongo-sharding-lab** consisting of:

~~~text
Host machine
  |
  +-- 127.0.0.1:27027 -> mongos:27017
  |
  +-- Docker private bridge (do not publish these ports)
         |
         +-- cfg:27019       CSRS, 1 voting member
         +-- shard-a:27018   rsShardA, 1 voting member
         +-- shard-b:27018   rsShardB, 1 voting member
         +-- mongos:27017    router
~~~

### 4.2. Why Only One Member per Replica Set?

The MongoDB Manual permits a single member for the config server replica set and each shard replica set **for testing purposes**. Production requires multiple members across separate failure domains, typically at least three members with an appropriate voting quorum.

A single-member lab **does not test real failover, durability under node loss, or network partitions**. It is only sufficient for studying shard-key distribution and routing.

### 4.3. Lab Security

For simplicity, this example does not enable authorization or internal TLS and uses `--bind_ip_all` **strictly inside the container network**. Therefore:

- Do not map config/shard ports to the host.
- Only publish the router on `127.0.0.1`.
- Do not run the lab on a shared host or untrusted network.
- Do not connect production apps to the lab router.
- Do not use real credentials or real data.
- Do not apply this configuration to cloud or public IPs.

Production strictly requires safeguards such as RBAC, TLS/internal authentication, firewall/network segregation, and observability.

## 5. Prerequisites

You need:

- Docker Engine and Docker Compose v2.
- A running Docker daemon.
- A machine with enough RAM/CPU for four MongoDB processes and several GB of disk space.
- `mongosh` via the container image; host installation is optional.
- A Bash, PowerShell, or equivalent terminal.
- Port `127.0.0.1:27027` free and not used by another application.
- A MongoDB image version pinned by policy; for example, `mongo:8.0` for this lab. For CI, pin an approved digest for exact reproducibility.

**Version note:** Some `mongosh` commands and output formats change across MongoDB 6.x–9.x. This lesson standardizes the concepts and examples for **MongoDB 8.0**; consult the docs for your server and `mongosh` versions when comparing.

### 5.1. Do Not Stand Up the Lab in a Production Compose Directory

Place the file in a new directory, such as `mongo-sharding-lab/compose.yaml`. Run all commands in that exact directory with project name `mongo-sharding-lab`.

### 5.2. Resources Still Share the Host

Do not run heavy stress tests while the machine is serving critical workloads. Docker Compose provides logical/network isolation, not guaranteed CPU/disk isolation unless limits are configured.

## 6. Docker Compose File

Create `compose.yaml` in the lab directory:

~~~yaml
services:
  cfg:
    image: mongo:8.0
    command:
      - mongod
      - --configsvr
      - --replSet
      - cfgRS
      - --port
      - "27019"
      - --bind_ip_all
    networks: [sharding_lab_net]
    volumes:
      - cfg_data:/data/db

  shard-a:
    image: mongo:8.0
    command:
      - mongod
      - --shardsvr
      - --replSet
      - rsShardA
      - --port
      - "27018"
      - --bind_ip_all
    networks: [sharding_lab_net]
    volumes:
      - shard_a_data:/data/db

  shard-b:
    image: mongo:8.0
    command:
      - mongod
      - --shardsvr
      - --replSet
      - rsShardB
      - --port
      - "27018"
      - --bind_ip_all
    networks: [sharding_lab_net]
    volumes:
      - shard_b_data:/data/db

  mongos:
    image: mongo:8.0
    command:
      - mongos
      - --configdb
      - cfgRS/cfg:27019
      - --port
      - "27017"
      - --bind_ip_all
    depends_on:
      - cfg
      - shard-a
      - shard-b
    ports:
      - "127.0.0.1:27027:27017"
    networks: [sharding_lab_net]

networks:
  sharding_lab_net:
    driver: bridge

volumes:
  cfg_data:
  shard_a_data:
  shard_b_data:
~~~

### 6.1. Why Not Publish Shard Ports?

Normal sharded-cluster applications must connect through `mongos`, not send CRUD directly to individual shards. MongoDB 8.0 also adds restrictions on certain direct operations on shards and introduces a special maintenance role `directShardOperations`; do not use that role in a standard lab.

### 6.2. Named Volumes Persist Data Across Restarts

Standard `docker compose down` does not remove named volumes. `down -v` **deletes lab data**—only use it when you want a full reset and have verified the project and directory.

### 6.3. depends_on Does Not Guarantee Replica Set Initialization

Compose starts processes according to dependencies, yet if `cfgRS` is not initialized, `mongos` may not become ready. We initialize the config server and shards first, then start the router.

### 6.4. Hostname Warning

MongoDB replica set members advertise hostnames `cfg`, `shard-a`, and `shard-b`. These hostnames must resolve inside the Docker network. Do not configure members using `localhost` or ephemeral container IPs when members need inter-container communication.

## 7. Start the Config Server and Shard Processes

In the terminal inside the directory containing `compose.yaml`:

~~~bash
docker compose -p mongo-sharding-lab up -d cfg shard-a shard-b
~~~

Check status:

~~~bash
docker compose -p mongo-sharding-lab ps
~~~

All containers must be running before calling `rs.initiate()`.

### 7.1. If Containers Exit

~~~bash
docker compose -p mongo-sharding-lab logs --tail=80 cfg
docker compose -p mongo-sharding-lab logs --tail=80 shard-a
docker compose -p mongo-sharding-lab logs --tail=80 shard-b
~~~

Do not proceed if ports or volumes report errors.

### 7.2. Do Not Use localhost Hostnames in the rs Config

Use service DNS names such as `cfg:27019`. Addresses configured for a replica set must match how internal members and the router reach it.

## 8. Initialize the CSRS

Run **once**:

~~~bash
docker compose -p mongo-sharding-lab exec -T cfg mongosh \
  --quiet --port 27019 \
  --eval 'rs.initiate({_id:"cfgRS",configsvr:true,members:[{_id:0,host:"cfg:27019"}]})'
~~~

A valid result normally returns `ok:1`. Do not run `rs.initiate()` repeatedly once the replica set is configured.

### 8.1. Verify Elected Primary

~~~bash
docker compose -p mongo-sharding-lab exec -T cfg mongosh \
  --quiet --port 27019 \
  --eval 'printjson(db.hello())'
~~~

Wait until `isWritablePrimary:true` appears. You can inspect `rs.status()` if needed.

### 8.2. Why configsvr:true?

`cfgRS` is a config server replica set, not a shard holding business data, following the **dedicated config server** design of this lab.

### 8.3. Difference from Newer Config Shards

Modern MongoDB supports config shards, but this lab uses a dedicated CSRS to keep topology observation straightforward. Do not confuse the two models when reading 8.x/9.x documentation.

## 9. Initialize the Two Shard Replica Sets

Initialize shard A:

~~~bash
docker compose -p mongo-sharding-lab exec -T shard-a mongosh \
  --quiet --port 27018 \
  --eval 'rs.initiate({_id:"rsShardA",members:[{_id:0,host:"shard-a:27018"}]})'
~~~

Initialize shard B:

~~~bash
docker compose -p mongo-sharding-lab exec -T shard-b mongosh \
  --quiet --port 27018 \
  --eval 'rs.initiate({_id:"rsShardB",members:[{_id:0,host:"shard-b:27018"}]})'
~~~

### 9.1. Check Each Shard's Status

~~~bash
docker compose -p mongo-sharding-lab exec -T shard-a mongosh \
  --quiet --port 27018 \
  --eval 'printjson(db.hello())'

docker compose -p mongo-sharding-lab exec -T shard-b mongosh \
  --quiet --port 27018 \
  --eval 'printjson(db.hello())'
~~~

Wait until each replica set elects a primary. Do not run `sh.addShard` before the shards can serve requests.

### 9.2. A Single-Node Configuration Cannot Elect Another Node

If the `shard-a` container dies, there is no secondary in `rsShardA` to take over as primary. This distribution lab does **not** represent an HA/failover test.

## 10. Start the mongos Router

~~~bash
docker compose -p mongo-sharding-lab up -d mongos
~~~

Check logs:

~~~bash
docker compose -p mongo-sharding-lab logs --tail=80 mongos
~~~

Connect to the router from inside its container:

~~~bash
docker compose -p mongo-sharding-lab exec -T mongos mongosh \
  --quiet --port 27017 \
  --eval 'printjson(db.hello())'
~~~

Output from `mongos` normally includes `msg:"isdbgrid"`.

### 10.1. Connecting from the Host

If `mongosh` is installed locally:

~~~bash
mongosh "mongodb://127.0.0.1:27027"
~~~

All subsequent sharding administration commands must be executed through **mongos**.

### 10.2. If mongos Fails to Start After Config Initialization

Inspect logs and hostnames, verify `cfgRS` has elected a primary, and restart just the router service if needed:

~~~bash
docker compose -p mongo-sharding-lab restart mongos
~~~

Do not delete volumes to fix topology issues without understanding the root cause.

## 11. Add Shard Replica Sets to the Cluster

Connect `mongosh` via the router:

~~~bash
docker compose -p mongo-sharding-lab exec mongos mongosh \
  --port 27017
~~~

Inside the shell connected to `mongos`:

~~~javascript
sh.addShard("rsShardA/shard-a:27018");
sh.addShard("rsShardB/shard-b:27018");

sh.status();
~~~

### 11.1. Check listShards

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Expect two shard identities corresponding to `rsShardA` and `rsShardB` (the exact shard names returned by the server are the source of truth).

### 11.2. Note That sh.addShard Modifies Metadata

This is an administrative operation that changes cluster topology; in the lab we only add the initialized shard replica sets. Never run this ad hoc on production Atlas.

### 11.3. Record the Baseline

Before sharding collections, record:

- Server version: `db.version()`.
- Mongosh version: `version()` / `mongosh --version` depending on shell.
- Shard list.
- Balancer state.
- RAM, Docker CPU, host disk.
- UTC timestamp and Git revision of the experiment notes.

## 12. Define Two Shard-Key Strategies to Compare

We use two independent collections with the same document count:

| Collection | Shard key | Prediction |
|---|---|---|
| `shard_lab.events_hash` | `{ eventId:"hashed" }` | Distinct `eventId`s yield distributed hashes |
| `shard_lab.events_range` | `{ sequence:1 }` | Monotonically increasing `sequence` risks concentrating in one range |

Both `eventId` and `sequence` in the lab have high cardinality. The key difference is whether MongoDB partitions by **hashed values** or **original values in ranges**.

### 12.1. Hashed Keys Distribute Well Without Guaranteeing an Exact Split

Hashing yields relatively even distribution for diverse keys; however, shard ownership of hash ranges, data skew, migrations, jumbo ranges, and workload all affect the outcome.

### 12.2. Range Keys Suit Ordered Queries but Risk Hotspots

A query like `sequence BETWEEN 10000 AND 15000` can target one or a few shards. However, when all inserts hit the "tail" of an increasing sequence, a hotspot forms on the newest range.

### 12.3. Do Not Claim These Are Ideal Production Shard Keys

These examples are illustrative only. Multi-tenant applications with diverse access patterns often require compound shard keys, zones, or hashed prefixes alongside dedicated benchmarks.

## 13. Create the Database and Collections

In the router `mongosh`:

~~~javascript
sh.enableSharding("shard_lab");

const labDb = db.getSiblingDB("shard_lab");

labDb.createCollection("events_hash");
labDb.createCollection("events_range");
~~~

Since MongoDB 6.0, `sh.enableSharding()` is no longer strictly required before sharding a collection; it is included here for clarity.

### 13.1. Supporting Shard-Key Indexes

~~~javascript
labDb.events_hash.createIndex({ eventId: "hashed" });
labDb.events_range.createIndex({ sequence: 1 });
~~~

For a populated collection, a supporting index must exist before sharding. For an empty collection, MongoDB can create the index if needed.

### 13.2. Verify Both Collections Are Still Empty

Check:

~~~javascript
labDb.events_hash.countDocuments({});
labDb.events_range.countDocuments({});
~~~

Both must be `0` before continuing if you want a deterministic single-load comparison. If data remains from a previous run, **never drop production data**: use a new lab project or intentionally reinitialize the lab.

## 14. Shard the Collections While Empty

~~~javascript
sh.shardCollection(
  "shard_lab.events_hash",
  { eventId: "hashed" }
);

sh.shardCollection(
  "shard_lab.events_range",
  { sequence: 1 }
);
~~~

### 14.1. MongoDB 8.0: Different Initial Chunks

On an empty collection with a single-field hashed shard key and no zones, MongoDB 8.0 creates **one initial chunk per shard** by default and distributes them across the cluster (behavior may differ across releases).

With a ranged shard key on an empty collection without zones, sharding typically initializes **a single chunk spanning the entire key space**.

### 14.2. Measure Immediately After Sharding

~~~javascript
sh.status(true);

labDb.events_hash.getShardDistribution();
labDb.events_range.getShardDistribution();
~~~

At this stage document counts are 0, so data distribution cannot yet be evaluated, even though chunk ownership exists.

### 14.3. Do Not Use unique:true with Hashed Indexes

MongoDB does not support unique hashed indexes. If you need the database to enforce `eventId` uniqueness, design differently (a regular unique index honoring the shard-key prefix, or uniqueness enforced at the application/external system level).

### 14.4. Note on _id in Sharded Collections

If `_id` is not the shard key, cluster-wide uniqueness of `_id` may not be enforced by MongoDB in all sharded configurations. In the lab, the producer supplies stable unique IDs; do not assume every collection automatically enforces global uniqueness across shards.

## 15. Generate Two Comparable Datasets

We ingest **20,000 documents per collection** with a fixed ~1 KiB payload—large enough to observe basic distribution without placing heavy stress on a laptop.

In router `mongosh`:

~~~javascript
const d = db.getSiblingDB("shard_lab");
const N = 20000;
const BATCH = 500;
const pad = "x".repeat(1024);
const baseTime = new Date("2026-11-14T00:00:00.000Z");

if (d.events_hash.countDocuments({}) !== 0 ||
    d.events_range.countDocuments({}) !== 0) {
  throw new Error("Lab collections must be empty before seeding.");
}

let insertedHash = 0;
let insertedRange = 0;

for (let start = 0; start < N; start += BATCH) {
  const hashBatch = [];
  const rangeBatch = [];

  for (let i = start; i < Math.min(start + BATCH, N); i++) {
    const id = String(i).padStart(8, "0");
    const tenant = "tenant-" + String(i % 16).padStart(2, "0");
    const timestamp = new Date(baseTime.getTime() + i * 1000);

    hashBatch.push({
      _id: "h-" + id,
      eventId: "evt-" + id,
      tenantId: tenant,
      sequence: i,
      createdAt: timestamp,
      payload: pad
    });

    rangeBatch.push({
      _id: "r-" + id,
      eventId: "evt-" + id,
      tenantId: tenant,
      sequence: i,
      createdAt: timestamp,
      payload: pad
    });
  }

  d.events_hash.insertMany(hashBatch, { ordered: false });
  d.events_range.insertMany(rangeBatch, { ordered: false });

  insertedHash += hashBatch.length;
  insertedRange += rangeBatch.length;
}

printjson({ insertedHash, insertedRange });
~~~

### 15.1. Why Pad the Payload?

Storing only a few tiny fields across 20,000 documents yields a data size too small to resemble realistic storage/balancer conditions. A fixed payload reduces experiment variance, though it still does not fully simulate a production workload.

### 15.2. Why 16 Tenants?

This allows testing tenant-specific queries and illustrates why hashing by `eventId` spreads events belonging to the same tenant across multiple shards.

### 15.3. Why Not 1 Million Documents Immediately?

A small lab makes mechanics observable and completes quickly. Once verified, you can scale `N` or payload within host limits and record measurements. Avoid changing `N` at the same time as index or shard-key changes if you want valid comparisons.

### 15.4. insertMany Retry and Error Semantics

If ingestion is interrupted mid-run, only some batches may have committed. Use `countDocuments` and unique IDs or seed markers to verify actual ingested input; never assume `N` documents were written if the terminal disconnected.

## 16. Verify Total Logical Documents

~~~javascript
printjson({
  hashedCount: d.events_hash.countDocuments({}),
  rangedCount: d.events_range.countDocuments({})
});
~~~

After a successful run on empty collections, both counts must be `20000`.

### 16.1. What Does Count Answer?

This is the logical count queried via `mongos`. It does not tell you how many documents each shard owns.

### 16.2. Do Not Read Shards Directly and Sum Them Up

Range migrations can leave behind orphan documents awaiting cleanup. Reading directly from a shard as if it were a standalone database can double-count records and risks routing issues; use supported `mongos` helpers and cluster metrics instead.

### 16.3. Ensuring Comparable Datasets

One collection may have different indexes than another (hashed vs. ascending index), so differences in disk/index sizes are normal. The primary comparison goal here is **logical document distribution** and query routing, not exact disk bytes.

## 17. Measurement Tool 1: getShardDistribution()

On the router:

~~~javascript
d.events_hash.getShardDistribution();
d.events_range.getShardDistribution();
~~~

`mongosh` prints per-shard statistics:

~~~text
Shard rsShardA:
  docs: ...
  data: ...
  chunks: ...

Shard rsShardB:
  docs: ...
  data: ...
  chunks: ...

Totals:
  docs: ...
  data: ...
  chunks: ...
  % data / % docs per shard
~~~

This is merely an **output structure template**, not measured numbers from an actual lab run.

### 17.1. Reading "docs" Correctly

The `docs` field helps estimate distribution, though behavior regarding orphan documents varies by `mongosh` version. Starting with `mongosh` 2.3.3, the helper excludes orphans from regular sharded data; older versions could include orphans awaiting deletion.

### 17.2. Reading "data" Correctly

The data size figure is not exact disk usage. Differences in BSON sizes, compression, indexes, and WiredTiger storage make disk bytes differ from logical document bytes.

### 17.3. Do Not Compare Chunks in Isolation

If each shard owns 1 chunk yet shard A holds 99% of documents, document distribution is unbalanced. Chunks are key ranges, not fixed-size buckets.

## 18. Measurement Tool 2: sh.getShardedDataDistribution()

Supported in MongoDB 6.0.3+:

~~~javascript
const distribution = sh.getShardedDataDistribution();

printjson(
  distribution.filter(item =>
    item.ns === "shard_lab.events_hash" ||
    item.ns === "shard_lab.events_range"
  )
);
~~~

Output for each namespace includes shard records with these fields:

~~~javascript
{
  ns: "shard_lab.events_hash",
  shards: [
    {
      shardName: "rsShardA",
      numOrphanedDocs: 0,
      numOwnedDocuments: 10100,
      ownedSizeBytes: 12000000,
      orphanedSizeBytes: 0
    },
    {
      shardName: "rsShardB",
      numOrphanedDocs: 0,
      numOwnedDocuments: 9900,
      ownedSizeBytes: 11800000,
      orphanedSizeBytes: 0
    }
  ]
}
~~~

**The numbers above are illustrative only.** Actual lab runs may differ, and orphan data may temporarily appear while migrations finish.

### 18.1. Owned vs. Orphan

- `numOwnedDocuments`: documents owned by the shard.
- `ownedSizeBytes`: size of owned documents measured in **uncompressed bytes**.
- `numOrphanedDocs`: number of orphan documents awaiting cleanup.
- `orphanedSizeBytes`: size of orphan documents.

### 18.2. Run at mongos

This helper must be run from `mongosh` connected to `mongos`. It does not work on standalone instances or direct shard connections, and is unsupported on certain Atlas free/flex tiers.

### 18.3. Why 20,000 Will Not Necessarily Split 10,000/10,000

Hash distribution exhibits statistical variance, and initial ranges are assigned to shards in metadata. An exact 50/50 split is not guaranteed.

## 19. Calculate Data Share per Shard Manually

In `mongosh`, you can compute percentages from `sh.getShardedDataDistribution()`:

~~~javascript
(() => {
  const ns = "shard_lab.events_hash";
  const doc = sh.getShardedDataDistribution()
    .find(item => item.ns === ns);

  if (!doc) {
    throw new Error("No sharded distribution for " + ns);
  }

  const rows = doc.shards.map(s => ({
    shard: s.shardName,
    docs: s.numOwnedDocuments,
    bytes: s.ownedSizeBytes,
    orphans: s.numOrphanedDocs
  }));

  const totalDocs = rows.reduce((x, r) => x + r.docs, 0);
  const totalBytes = rows.reduce((x, r) => x + r.bytes, 0);

  const result = rows.map(r => ({
    shard: r.shard,
    docs: r.docs,
    docsPct: totalDocs === 0 ? 0 : 100 * r.docs / totalDocs,
    bytes: r.bytes,
    bytesPct: totalBytes === 0 ? 0 : 100 * r.bytes / totalBytes,
    orphans: r.orphans
  }));

  printjson({ ns, totalDocs, totalBytes, result });
})();
~~~

### 19.1. Formula

For shard `s`:

\[
p_s = \frac{\text{ownedDocs}_s}{\sum_i \text{ownedDocs}_i} \times 100\%.
\]

For two shards:

\[
\text{gap}_{pp} = |p_A - p_B|.
\]

`gap_pp` is the difference in **percentage points**, not percentage growth.

### 19.2. Sample Evaluation

If A=10,200 docs and B=9,800 docs:

- A = 51%.
- B = 49%.
- Gap = 2 percentage points.
- Max/min count ratio ≈ 1.04.

If A=19,000 and B=1,000, the gap is 90 points; data is heavily skewed even though both shards own chunks.

### 19.3. Distinguish Expected from Measured

Never write 10,000/10,000 into a report simply because it is the ideal target. Record actual output, measurement timestamps, versions, and balancer state.

## 20. Measure Multiple Times Instead of Taking a Single Snapshot

Data migration and orphan cleanup run asynchronously. Measure at:

- T0: immediately after sharding, before inserts.
- T1: immediately after inserts complete.
- T2: after observing balancer activity.
- T3: after a stabilization period with no ongoing migrations.
- T4: after applying experimental split/move operations on the ranged collection.

### 20.1. Do Not Use T1 Numbers as the Final Conclusion

Right after bulk ingestion, the balancer may not have finished. One shard temporarily holding more data does not prove the shard key is broken.

### 20.2. Conditions for "Settled"

Rather than blindly sleeping 30 seconds, verify:

- `sh.balancerCollectionStatus(namespace)`.
- `sh.status()` for active migrations or failed rounds.
- Owned docs/bytes stop changing materially across repeated checks.
- Orphan docs stop increasing from migrations.
- Cluster nodes are healthy.

Do not expect every counter to reach absolute zero if background processes remain active.

## 21. Measure Chunks from Config Metadata (Read-Only)

When inspecting chunk ownership from metadata:

~~~javascript
const cfgDb = db.getSiblingDB("config");

const c = cfgDb.collections.findOne({
  _id: "shard_lab.events_hash"
});

if (!c) {
  throw new Error("Sharded collection metadata missing");
}

printjson({
  namespace: c._id,
  uuid: c.uuid,
  shardKey: c.key
});

printjson(
  cfgDb.chunks.aggregate([
    { $match: { uuid: c.uuid } },
    {
      $group: {
        _id: "$shard",
        chunks: { $sum: 1 }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

### 21.1. Why Use UUID Instead of ns?

In modern MongoDB versions (MongoDB 5.0+), `config.chunks` uses `uuid` to reference collections. Older examples querying `{ns:"db.collection"}` may no longer apply.

### 21.2. Config Metadata Is an Implementation Detail

The schema of the `config` database can change across MongoDB versions. Use official helpers whenever possible, and never write, modify, or delete `config.chunks` metadata directly.

### 21.3. Chunk Boundaries

Each chunk document typically contains `min` and `max` representing the interval `[min,max)`, along with the shard owner. For hashed keys, bounds are **hash ranges**, not original `eventId` strings.

### 21.4. Do Not Confuse Chunk Count with "Documents per Shard"

Four chunks can hold a tiny amount of data while a single other chunk holds most records if key distribution is skewed.

## 22. Is the Balancer Enabled or Actively Migrating Data?

On `mongos`:

~~~javascript
sh.getBalancerState();
sh.isBalancerRunning();

sh.balancerCollectionStatus(
  "shard_lab.events_hash"
);
~~~

### 22.1. Enabled vs. Active

`sh.getBalancerState()` indicates whether the balancer is **permitted to run**. It does not prove a chunk migration is currently in progress.

`sh.isBalancerRunning()` and `sh.status()` provide balancer activity signals depending on the MongoDB/`mongosh` version.

### 22.2. Collection Balancer Status

`sh.balancerCollectionStatus(namespace)` reports whether the collection satisfies distribution/balance requirements or still needs migrations due to range imbalance, zone violations, or a draining shard.

Never treat a single boolean as proof that business workload is balanced.

### 22.3. Balancer Decisions Follow Policy and Ranges

The balancer will not necessarily migrate chunks for a difference of a few hundred documents, especially when the dataset is smaller than chunk size or no split is needed.

### 22.4. Do Not Toggle the Balancer in Production to Experiment

`sh.stopBalancer()`/`sh.startBalancer()` affect the entire cluster. If a test requires changing state, do it only in a resettable lab; record prior state and restore it afterward.

## 23. Hashed Shard-Key Experiment: Interpreting Results Correctly

On MongoDB 8.0, sharding an empty collection with a single-field hashed key typically creates distributed initial chunks, so ingesting 20,000 diverse `eventId`s generally places data on **both shards**.

### 23.1. Directional Expectation, Not a Fixed Number

~~~text
rsShardA: ~50% owned docs
rsShardB: ~50% owned docs

Exact result depends on hash ranges and data.
~~~

This is a hypothesis to measure. If only one shard holds documents, check:

- Is the collection actually sharded?
- Were hashed initial ranges distributed?
- Has `mongos` metadata refreshed?
- Are the balancer and migrations running?
- Is the measurement querying the right namespace?
- Is the sample too small or heavily duplicated in key values?

### 23.2. Shard Count Does Not Equal Throughput Gain

A hashed key can distribute inserts better than a monotonic range key, yet writes still depend on journaling, network, replication, index maintenance, and shared host CPU.

### 23.3. Point Lookup by eventId

~~~javascript
d.events_hash.find({
  eventId: "evt-00000100"
}).explain("executionStats");
~~~

Because the filter includes equality on the full hashed shard key, `mongos` can route directly to the shard owning that hash. Inspect `winningPlan` and shard execution stats; do not assume fixed stage names across versions.

### 23.4. Range Lookup on Unhashed sequence

~~~javascript
d.events_hash.find({
  sequence: { $gte: 10000, $lt: 11000 }
}).explain("executionStats");
~~~

Because `sequence` is not the shard key of this collection, `mongos` can scatter-gather across multiple shards even when an index supports the filter.

## 24. Ranged Shard-Key Experiment: Skew Behavior

With `{sequence:1}`, an empty collection typically starts with **one range covering the entire key space**. After ingesting 20,000 ~1 KiB records, the dataset may be too small to trigger automatic splitting by size or balancer thresholds.

Possible outcome:

~~~text
rsShardA: 20.000 docs
rsShardB:      0 docs
~~~

This is an **illustrative possibility**, not a MongoDB default guarantee or a measured lab result.

### 24.1. Ranged Sharding Is Not Broken Simply Because Initial Distribution Is Uneven

If data volume is small and queries typically filter by time/sequence ranges, one shard may serve the workload reasonably well. Evaluate against capacity and traffic, not solely a 50/50 target.

### 24.2. Monotonic Inserts Still Risk Hotspots

If every new insert carries a higher `sequence` than earlier keys, all writes hit the uppermost range. One shard absorbs almost all concurrent writes even if historical ranges are spread evenly.

### 24.3. Measure Before Intervening

~~~javascript
d.events_range.getShardDistribution();

sh.balancerCollectionStatus(
  "shard_lab.events_range"
);
~~~

Save the T1 snapshot. The manual split/move steps below are strictly for **lab** observation.

## 25. Manual Range Split Experiment in the Lab

**Warning:** MongoDB generally recommends letting the system manage chunk splitting and balancing automatically. `sh.splitAt()` is used here solely to demonstrate mechanics on a test cluster.

Split the collection at boundary `sequence=10000`:

~~~javascript
sh.splitAt(
  "shard_lab.events_range",
  { sequence: 10000 }
);
~~~

After the split, the two logical ranges are:

~~~text
[MinKey, 10000)
[10000, MaxKey)
~~~

### 25.1. splitAt Does Not Move Data

The command only splits one chunk into two chunks. **Both chunks can still live on the same shard.** This is the difference between a *split* and a *migration*.

### 25.2. Choosing a Split Point Based on Test Data

In the lab, keys span 0..19999, so 10000 divides the set roughly 50/50 by document count. In production, splitting at the midpoint of key values **does not guarantee** an even split by bytes if payload sizes vary.

### 25.3. AutoMerger and the Balancer Can Affect Observations

Modern MongoDB versions include AutoMerger and the balancer. If a newly split range is merged back before observation or metadata changes, inspect cluster state and adjust lab policy appropriately. Never disable AutoMerger in production just to observe a split.

## 26. Move the Split Chunk/Range to Shard B

In the lab only, identify shard IDs via:

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Assuming the target shard has ID `rsShardB`, you can run:

~~~javascript
sh.moveChunk(
  "shard_lab.events_range",
  { sequence: 15000 },
  "rsShardB"
);
~~~

`sh.moveChunk(namespace,query,destination)` locates the chunk containing the specified shard key value and migrates it to the target shard.

### 26.1. Expectation

If range `[10000,MaxKey)` is moved to B:

~~~text
rsShardA: keys 0..9999      -> ~10.000 docs
rsShardB: keys 10000..19999 -> ~10.000 docs
~~~

**This is the expected logical outcome**; actual numbers must be read from the cluster. Migrations or range deletion might still be in flight at the exact moment of measurement.

### 26.2. Do Not Blindly Use moveChunk with Hashed Keys

MongoDB docs note that the `sh.moveChunk()` helper cannot be used with hashed shard keys using the `find` form; moving a hashed range requires specifying explicit bounds. This lesson uses the helper only on the **ranged collection**.

### 26.3. Why Never Run This Ad Hoc in Production?

Manual moves generate network I/O, increase latency, and interfere with the balancer, zone constraints, and replication. Let the cluster self-balance unless executing an approved maintenance plan.

### 26.4. Remeasure

~~~javascript
d.events_range.getShardDistribution();

sh.balancerCollectionStatus(
  "shard_lab.events_range"
);
~~~

Compare against the pre-split/move T1 snapshot.

## 27. Range Queries: Which Shards Does mongos Target?

After splitting data at `sequence=10000`:

~~~javascript
d.events_range.find({
  sequence: { $gte: 5000, $lt: 6000 }
}).explain("executionStats");
~~~

A query whose shard key range falls completely inside one chunk/range (assuming unchanged metadata) can target **a single shard**.

Try a query crossing the boundary:

~~~javascript
d.events_range.find({
  sequence: { $gte: 9000, $lt: 11000 }
}).explain("executionStats");
~~~

It can target **two shards** if ranges are divided as expected.

### 27.1. Hashed vs. Range Targeting

| Query shape | Hashed `eventId` | Ranged `sequence` |
|---|---|---|
| Equality `eventId` | Usually targeted | Scatter if lacking shard key |
| Equality `sequence` | Scatter if lacking shard key | Targeted |
| Range `sequence` | Scatter | Can target subset |
| Range `eventId` | Not optimized for hash-range routing | Scatter if lacking shard key |
| All tenant events | Scatter when `tenantId` is not shard key | Scatter when `tenantId` is not shard key |

### 27.2. Explain After Warmup

Run `explain` once metadata has stabilized, then measure query latency separately under the same workload. `explain` carries instrumentation overhead, so never treat `explain` timing as an API-equivalent latency benchmark.

### 27.3. Do Not Hardcode Plan Tree Paths

MongoDB explain formats and stage names can vary across the classic engine, SBE, and query routers. Read `winningPlan`, `executionStages`, and shard execution sections according to your version; never write a parser tied to a single sample output.

## 28. Measure Scatter-Gather Rather Than Data Balance Alone

A collection balanced 50/50 can still force every query to hit both shards:

~~~text
Client query has tenantId only
             |
             v
          mongos
           /   \
          v     v
       shard A shard B
          \     /
           merge
~~~

If 95% of workload queries filter by `tenantId`, a hashed `eventId` shard key may spread inserts evenly while causing read fan-out.

### 28.1. Define Realistic Workload Queries

Collect a representative sample:

~~~text
70% find events by tenantId + time window
20% find by eventId
10% aggregate by eventType/time
~~~

Use this sample to evaluate the shard key. Never pick a key from a documents-per-shard chart alone.

### 28.2. Classify Target Count

- **Single-shard query**: `mongos` routes to one shard.
- **Multi-shard targeted**: a subset of shards holding relevant ranges.
- **Scatter-gather**: many or all shards participate.

### 28.3. Query Indexes Still Matter

Even a targeted single-shard query is slow if indexes do not support the filter and sort; sharding does not replace indexing.

## 29. Use analyzeShardKey When Supported by Your Version

MongoDB 7.0+ provides `analyzeShardKey` to evaluate shard key characteristics and (when query sampling is enabled) read/write distribution.

Example on an indexed collection:

~~~javascript
d.events_range.analyzeShardKey(
  { sequence: 1 },
  {
    keyCharacteristics: true,
    readWriteDistribution: false
  }
);
~~~

Results can include:

- Total documents and sampled count.
- Cardinality/distinct values.
- Most common values/frequency.
- Monotonicity.
- Uniqueness signals based on key properties.

### 29.1. Query Sampling for Read/Write Distribution

If `configureQueryAnalyzer` has not been configured and workload queries sampled, read/write distribution metrics may return 0. **Do not** interpret 0 as "zero scatter-gather".

### 29.2. Do Not Run Directly on Shards

In a sharded cluster, `analyzeShardKey` must be executed through `mongos`, not via a direct connection to a shard replica set.

### 29.3. Evaluating Cardinality

If a shard key has only two values `status={"NEW","DONE"}`, distinct keys are far too few to split granularly, risking jumbo/indivisible ranges.

### 29.4. Evaluating Frequency

A key where one value accounts for 90% of records can still create a hot key even if total distinct values are high.

### 29.5. Evaluating Monotonicity

Steadily increasing sequences and timestamps risk append hotspots with ranged shard keys.

## 30. Testing a Low-Cardinality Shard Key

Consider an **illustrative** dataset:

~~~javascript
{
  tenantId: "tenant-A",
  status: "NEW",
  payload: "..."
}
~~~

If the shard key is `{ status:1 }`, only a handful of key values exist, meaning the cluster cannot split data arbitrarily along `status`. MongoDB chunk ranges cannot split a single identical shard key value across two different ranges on the same collection.

### 30.1. From Data Skew to Jumbo Chunks

When large numbers of documents share the same shard key value and exceed size limits, the system can encounter jumbo/unsplittable chunks or severe imbalance.

### 30.2. Ways to Improve

- Increase cardinality with a compound key including a selective field.
- Consider a hashed key suited to the workload.
- Isolate hot tenants/entities by data model or zone.
- Evaluate `refineCollectionShardKey`/`reshardCollection` with a migration plan.

### 30.3. Do Not Change Production Shard Keys Ad Hoc

Resharding incurs cost, requires storage headroom, and carries operational risk. It requires benchmarking, backups, FCV/version checks, and rollout controls.

## 31. What Happens to Orphan Data After Migration?

When moving a range:

~~~text
Source shard:
  owns range R
     |
     | copy to destination
     v
Destination shard:
  receives range R
     |
  ownership metadata switches
     |
Source:
  old copies become orphaned
  range deleter eventually removes them
~~~

### 31.1. Measure Owned, Do Not Add Orphans

`sh.getShardedDataDistribution()` separates `numOwnedDocuments` and `numOrphanedDocs`. Adding them together double-counts logical data after migration.

### 31.2. Orphans May Persist Temporarily

Range deletion runs asynchronously. Seeing high bytes on the source shard does not mean migration failed if ownership metadata has already switched.

### 31.3. Never Delete Data Directly on a Shard

Never connect to a shard to `deleteMany` documents that "look like duplicates". Doing so can corrupt the cluster. Rely on MongoDB's built-in range cleanup and diagnostics.

## 32. Balanced Distribution Does Not Equal Balanced Disk Usage

Suppose one shard stores 10,000 very large documents while the other stores 10,000 small documents:

~~~text
Shard A: 10.000 docs, 80 MB logical
Shard B: 10.000 docs, 20 MB logical
~~~

Documents are 50/50, yet bytes are 80/20. Measure both.

### 32.1. WiredTiger Compression

`ownedSizeBytes` reports **uncompressed** size. Disk usage can be lower due to compression, or higher due to indexes, oplog, metadata, and fragmentation.

### 32.2. Cache and Working Set

A shard with smaller data size can still experience higher CPU/I/O if query traffic concentrates there. Per-shard performance monitoring is essential, not just data size.

### 32.3. Measurement Timing

Avoid comparing source disk bytes before orphan cleanup finishes against destination logical owned data—those are different quantities.

## 33. Measure Latency Without Turning the Lab into a Production Benchmark

A latency scenario can include:

1. Several warmup runs for collection/index caches.
2. Point lookups by `eventId` on `events_hash`.
3. Point/range lookups by `sequence` on `events_range`.
4. `tenantId`-only queries on both collections.
5. Recording p50/p95/p99 from the same client with equal request counts.
6. Comparing shards targeted and documents examined.

### 33.1. Never Rely on a Single Run

Run 1 may hit cold pages; run 2 benefits from warm cache. Execute multiple iterations, randomize order, and separate cold/warm cache runs in reports.

### 33.2. Measure from the Client/Driver

Use driver command monitoring and application latency metrics. `explain("executionStats")` is for plan analysis, not a substitute for end-to-end benchmarking.

### 33.3. Same-Laptop Bias

Four MongoDB processes share CPU, RAM, and disk. If hashed inserts appear slower than ranged inserts in the lab, it may stem from background migrations, resource contention, or index overhead—it does not prove hashed shard keys perform worse in production.

### 33.4. Overall Throughput and Tail Latency

Reporting only average latency hides tail spikes during balancer migrations. Report p95/p99 and error rates.

## 34. Sample Ingest Throughput Measurement

In `mongosh`, you can record elapsed time for a small batch:

~~~javascript
(() => {
  const dbLab = db.getSiblingDB("shard_lab");
  const coll = dbLab.getCollection("events_hash");
  const marker = "throughput-lab-" + Date.now();
  const docs = [];

  for (let i = 0; i < 1000; i++) {
    docs.push({
      _id: marker + "-" + i,
      eventId: marker + "-" + i,
      tenantId: "benchmark",
      sequence: i,
      createdAt: new Date(),
      payload: "y".repeat(128)
    });
  }

  const startMs = Date.now();
  const result = coll.insertMany(docs);
  const elapsedMs = Date.now() - startMs;

  printjson({
    acknowledgedCount: result.insertedIds
      ? Object.keys(result.insertedIds).length
      : null,
    elapsedMs,
    approximateOpsPerSecond:
      elapsedMs > 0 ? 1000 * docs.length / elapsedMs : null
  });
})();
~~~

### 34.1. This Is a Micro-Experiment

Never treat `opsPerSecond` here as production capacity. It only reflects the current host under immediate conditions.

### 34.2. Seed Data vs. Measured Data

This batch **changes the document count** of `events_hash`. For a fair distribution comparison across both collections, use a separate benchmark collection or run it after saving your baseline, and note the change in `N`.

### 34.3. Write Concern and Durability

`insertMany` defaults to the URI/client write concern. Comparing two workloads with different write concerns produces invalid results. In production, never weaken durability solely to inflate benchmark numbers.

## 35. Running the Java Sync Driver Through mongos

Java applications should only connect to **mongos** (on the lab host `127.0.0.1:27027`):

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ShardingLabClient {

    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGO_SHARDING_LAB_URI",
            "mongodb://127.0.0.1:27027"
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("shard_lab");
            MongoCollection<Document> events =
                database.getCollection("events_hash");

            Document event = events.find(
                new Document("eventId", "evt-00000100")
            ).first();

            System.out.println("Found=" + (event != null));
        }
    }
}
~~~

### 35.1. Do Not Connect Directly to a Shard to Read App Data

The router uses shard keys and metadata to route queries. A direct-shard client bypasses `mongos` routing and can return incomplete/incorrect results or have operations rejected by the server.

### 35.2. MongoClient Should Be a Singleton

The Java driver's `MongoClient` reuses connection pools. Never create a new client per query in a benchmark, as DNS/TCP/TLS overhead will skew measurements.

### 35.3. With Spring Boot

MongoDB URI configuration varies by version:

- Spring Boot 3.5: `spring.data.mongodb.uri`.
- Spring Boot 4.x: `spring.mongodb.uri`.

In the lab, the URI points to `mongos`; production requires TLS, authentication, a secret manager, and proper topology settings.

## 36. Java Benchmark: Bounded Measurement

A simple measurement helper:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class QuerySample {

    public static List<Long> sampleMillis(
            MongoCollection<Document> collection,
            List<String> eventIds) {

        List<Long> samples = new ArrayList<>();

        for (String id : eventIds) {
            long started = System.nanoTime();

            collection.find(new Document("eventId", id)).first();

            long elapsed = System.nanoTime() - started;
            samples.add(elapsed);
        }

        Collections.sort(samples);
        return samples;
    }
}
~~~

### 36.1. sampleMillis Is an Unconverted Illustrative Name

This method returns nanoseconds because `elapsed` is not divided by 1,000,000; in production code, name it `sampleNanos` or convert explicitly to milliseconds. This highlights a very common measurement unit bug.

### 36.2. Warmup and P95

Send warmup queries before timing. Then use the sorted list to compute median/p95 with proper indexing. Separate network, server selection, and `mongos`/shard execution time when tracing is available.

### 36.3. Do Not Draw Conclusions from a Single Sample

Run multiple iterations with identical cardinality, indexes, concurrency, and Docker resources, and log the number of targeted shards.

## 37. Shard Key Design: Trade-Offs to Document in Results

| Criterion | Hashed `eventId` | Ranged `sequence` |
|---|---|---|
| Distribution on monotonically increasing keys | Usually spreads well | Risks hot upper range |
| Equality lookup on key | Targeted | Targeted |
| Range query on original shard key | Poor locality under hash | Can route to subset |
| Query on non-shard-key `tenantId` | Scatter | Scatter |
| Global uniqueness on hashed field | No unique hashed index | Unique constraints follow rules |
| Initial chunk distribution on empty MongoDB 8.0 | Can distribute early | Can start with one chunk |
| Manual `moveChunk` helper | Not usable via `find` on hashed key | Usable in lab |
| Changing shard key later | Resharding requires planning | Resharding requires planning |

### 37.1. No Single Key Fits Every Use Case

If the primary access pattern is `tenantId+aggregateId+time`, a compound key tailored to the workload may outperform both single-field keys tested here.

### 37.2. Hashing Does Not Automatically Fix Low-Cardinality Business Grouping

If many events share one `tenantId` and the shard key is `{tenantId:"hashed"}`, all events for that tenant hash identically and land on the same shard. Hashing **never splits a single key value across multiple shards**.

## 38. When Are Zones Needed?

Zone sharding pins specific shard-key ranges to a subset of shards, such as for:

- Region/data residency.
- Tiers of service.
- Tenant group isolation.
- Hot/cold data policies.

### 38.1. Zones Do Not Mean Equal Document Counts

If a zone contains only one shard or one massive tenant, distribution will be skewed even while the balancer strictly satisfies zone constraints.

### 38.2. Do Not Add Zones to the Basic Lab Ad Hoc

Adding zones alters expected distribution because the balancer must balance data while respecting placement rules. Run zones as a separate experiment with its own baseline.

### 38.3. Legal and Regulatory Limits

Never move chunks across regions "to test" if data is subject to residency requirements. The lab uses synthetic data on a single Docker host.

## 39. Resharding and shardAndDistributeCollection

Starting in MongoDB 8.0, `sh.shardAndDistributeCollection()` can shard and redistribute data faster under appropriate conditions and resources, rather than waiting for sequential balancer migrations. It combines sharding and resharding logic toward the target key.

### 39.1. Not Required for This Lab

This lesson uses `sh.shardCollection()` to clearly observe initial distribution and balancer behavior. Switching to `shardAndDistributeCollection` changes the goal of the experiment.

### 39.2. Changing an Existing Shard Key

`reshardCollection`/`refineCollectionShardKey` carry version, index, namespace, storage, write-availability, and operational requirements. Never trigger them solely because a distribution chart looks uneven.

### 39.3. When to Consider Resharding

- Real workload evidence shows a persistent hot shard.
- Chunks cannot split due to low cardinality.
- Query targeting is poor.
- Data placement misses SLOs.
- Sufficient free disk, network, and CPU capacity exist to reshard.

## 40. Sharding Pitfalls Across MongoDB Versions

### 40.1. MongoDB 5.0+ config.chunks

Use `uuid` instead of assuming `ns` is always present in chunk metadata.

### 40.2. MongoDB 6.0+

`sh.enableSharding()` is no longer mandatory before sharding a collection.

### 40.3. MongoDB 6.0.3+

`sh.getShardedDataDistribution()` is available for retrieving owned/orphan counts.

### 40.4. MongoDB 7.0+

`analyzeShardKey` helps inspect key characteristics. Read/write distribution requires configuring query sampling.

### 40.5. MongoDB 7.2+ / 8.0

Default initial chunk count for empty hashed collections changed across releases; MongoDB 8.0 creates one initial chunk per shard in standard setups.

### 40.6. MongoDB 8.0+

Includes `sh.shardAndDistributeCollection()` and restrictions around `directShardOperations`. Do not copy MongoDB 4.x admin commands into 8.x without checking current docs.

### 40.7. MongoDB 9.x

Certain APIs, commands, and sharded deployment styles continue to evolve. If changing versions, record the exact version and verify helper output before comparing against this lesson.

## 41. Distinguishing a Failed Test from a Conclusion About the Shard Key

Example:

~~~text
Experiment: events_hash 100% data on rsShardA
~~~

Before concluding "hashed sharding is bad", verify:

- Does `sh.status()` show the expected namespace as sharded?
- Does `db.events_hash.getIndexes()` show the hashed index?
- Was `sh.getShardedDataDistribution()` executed from `mongos`?
- Does the dataset actually contain many distinct `eventId` values?
- Are both shards present in `listShards` and reachable?
- Are chunks owned by both shards?
- Do balancer/migrations report errors?
- Are there journal, disk-full, or network issues?
- Did the measurement query the wrong namespace?
- Are manual zones or placement constraints configured?
- Is initial distribution still pending?

### 41.1. Setup Failure

If the config server is uninitialized or the router is unreachable, that is an infrastructure setup error—it does not prove the sharding strategy failed.

### 41.2. Measurement Error

If counting directly on a shard includes orphans after migration, that is a measurement bug. Always use owned statistics.

### 41.3. Statistical Variance

A 20-document test provides no solid evidence of long-term balance. Increase sample size and run controlled repetitions.

## 42. Runbook: All Data Lands on One Shard

1. Confirm the collection is sharded and verify the actual shard key in `sh.status()`.
2. Confirm the cluster has two healthy shards.
3. Inspect key cardinality and frequency.
4. Check chunk counts and ownership.
5. Determine whether data was inserted recently or existed before sharding.
6. Check balancer state and collection balance status.
7. Check for oversized/jumbo chunks or zone constraints.
8. Wait for background migrations if currently active.
9. If the dataset is small, document "insufficient data to trigger auto-split".
10. In the lab, test manual split/move range; in production, use a change request.
11. Remeasure owned docs/bytes and query targeting.
12. Evaluate whether resharding or key refinement is warranted.

### 42.1. Do Not Try to Fix This by Changing Primary

A primary election inside a shard replica set does not redistribute chunks to another shard. It only switches which node serves writes within the **same shard**.

### 42.2. Do Not Fix This by Blindly Increasing Pool Size

Increasing the Java `MongoClient` pool raises concurrency without altering shard key placement; the hotspot remains.

## 43. Runbook: Balancer Is Not Moving Chunks

Possible causes:

- Imbalance does not exceed policy thresholds.
- Data/ranges do not yet require migration.
- Balancer is disabled or outside its maintenance window.
- Collection contains jumbo/indivisible ranges.
- Target shard disk/resource constraints.
- Chunks restricted by zone placement rules.
- Migrations pending or failing.
- Config server or shard health issues.

### 43.1. Checks

~~~javascript
sh.getBalancerState();
sh.isBalancerRunning();

sh.balancerCollectionStatus(
  "shard_lab.events_range"
);

sh.status();
~~~

### 43.2. Do Not Reflexively Call sh.startBalancer

First determine whether the balancer is actually disabled. Enabling an already unnecessary cycle will not create chunks or fix a low-cardinality key.

### 43.3. Capture Error Details

Record the last balancer error, failed rounds, namespace, ranges, server versions, and timestamp. Never manually edit the `config` database.

## 44. Runbook: Queries Remain Slow After Data Balances

1. Measure p95/p99 latency and throughput per operation.
2. Use `explain("executionStats")` to identify targeted shards.
3. Check compound indexes on every shard.
4. Inspect scatter-gather fan-out and merge costs.
5. Check hot tenant or `eventType` skew.
6. Measure shard CPU, cache, disk I/O, and connections.
7. Check for ongoing balancer migrations.
8. Check for sort or aggregation disk spilling.
9. Re-evaluate query shapes and the shard key.
10. Only then consider adding capacity or resharding.

### 44.1. Even Data Distribution Does Not Guarantee SLOs

Read load can skew independently of document counts. Optimize targeted queries and indexes before scaling out.

## 45. Experiment Results Recording Table

Enter **actually measured** numbers, never estimates.

| Milestone | Collection | Shard | Owned docs | Owned bytes | Chunks | Orphans | Balancer state |
|---|---|---|---:|---:|---:|---:|---|
| T0 | events_hash | rsShardA | ... | ... | ... | ... | ... |
| T0 | events_hash | rsShardB | ... | ... | ... | ... | ... |
| T1 | events_hash | rsShardA | ... | ... | ... | ... | ... |
| T1 | events_hash | rsShardB | ... | ... | ... | ... | ... |
| T1 | events_range | rsShardA | ... | ... | ... | ... | ... |
| T1 | events_range | rsShardB | ... | ... | ... | ... | ... |
| T4 | events_range | rsShardA | ... | ... | ... | ... | ... |
| T4 | events_range | rsShardB | ... | ... | ... | ... | ... |

### 45.1. Record Metadata Alongside the Table

~~~yaml
experimentId: shard-distribution-lab
environment: isolated-docker-compose
mongoVersion: "8.0.x"
mongoshVersion: "record-actual-version"
routerEndpoint: "127.0.0.1:27027"
shards: 2
configServerMembers: 1
membersPerShard: 1
workload:
  documentsPerCollection: 20000
  payloadBytesApprox: 1024
measurement:
  source: sh.getShardedDataDistribution
  includesOrphans: false
notes: "Numbers are observed results, not predetermined"
~~~

This is a report template, not a MongoDB config file, and does not replace actual measurements.

### 45.2. Report Targeted Queries Too

| Query | Collection | Expected routing | Observed shards | p95 | Docs examined |
|---|---|---|---|---|---|
| eventId equality | events_hash | typically 1 shard | ... | ... | ... |
| sequence equality | events_range | typically 1 shard | ... | ... | ... |
| sequence range crossing split | events_range | potentially 2 shards | ... | ... | ... |
| tenantId only | both | scatter | ... | ... | ... |

## 46. How to Evaluate Final Results

Evaluate across multiple dimensions:

- **Correctness:** Total logical count matches with no data loss or duplication.
- **Ownership:** Owned docs and bytes are distributed as designed.
- **Balance:** Skew ratio and orphan/migration state are explainable.
- **Routing:** Queries target expected shards without unintended scatter.
- **Performance:** p95/p99 and throughput under identical workloads.
- **Operations:** Balancer, error counters, CPU, and I/O remain stable.
- **Repeatability:** Version, scripts, N, elapsed time, and clean-slate policy documented.
- **Security:** Lab cluster is not exposed externally and contains no real data.

### 46.1. PASS Does Not Always Mean 50/50

If workload queries primarily hit one tenant pinned to a zone, a 60/40 data split may be appropriate. Every experiment needs predefined acceptance criteria before running.

### 46.2. Explain Deviations

If T1 shows hash skew that improves by T3, initial chunk migration or balancer activity may explain it. Record evidence rather than only the final numbers.

### 46.3. Do Not Treat the Lab as a Production SLA

A single-host laptop does not reflect multi-AZ networking, replication factors, high concurrency, backups, maintenance windows, or cloud storage behavior.

## 47. Safety When Testing on Staging

If replacing the Docker lab with a real staging cluster:

- Only use approved accounts and staging datasets.
- Never use live customer PII.
- Cap throughput, query windows, and test duration.
- Coordinate with the DBA/owner and maintenance boundaries.
- Never execute direct-shard writes.
- Never modify config metadata.
- Never run manual `moveChunk` or `reshard` without an approved change.
- Prepare a rollback/recovery plan.
- Record audit logs and resource metrics.
- Ensure test traffic does not impact other environments.

### 47.1. Avoid "Testing" Permissions with Production Root

Sharding admin commands require privileges; a local lab can use an internal demo admin. In staging/production, enforce least privilege and never expose real root credentials in unprotected terminals.

### 47.2. Query Analyzer Carries Overhead

If enabling query sampling on staging, configure an approved `sampleRate` and duration, and record overhead. Never assume profiling tools are free.

## 48. Safe Lab Cleanup

**Before deleting anything**, confirm your terminal is in the exact directory containing the lab's `compose.yaml` and targeting the intended project name.

List containers:

~~~bash
docker compose -p mongo-sharding-lab ps
~~~

To stop only:

~~~bash
docker compose -p mongo-sharding-lab stop
~~~

To stop and remove containers while preserving named volumes:

~~~bash
docker compose -p mongo-sharding-lab down
~~~

To delete **all lab data** after verifying the exact project:

~~~bash
docker compose -p mongo-sharding-lab down -v --remove-orphans
~~~

### 48.1. down -v Is Destructive

The last command deletes named volumes belonging to the Compose project. Never run it if the project holds data you need or before verifying the project name.

### 48.2. Do Not Run Cluster-Wide Docker Prune Commands

Never run `docker system prune --all --volumes` as part of this lab. It can wipe data, images, and volumes from unrelated projects.

### 48.3. Do Not Run dropDatabase from the Wrong Connection

If cleaning up with `db.dropDatabase()`, first verify the URI points to `127.0.0.1:27027` and database `shard_lab`. Isolated Compose teardown is generally safer for demos.

## 49. Self-Practice Questions

### Exercise 1 — Component Roles

Explain `mongos`, the config server replica set, and shard replica sets.

### Exercise 2 — Replication vs. Sharding

Why does adding a secondary to a replica set not automatically partition data?

### Exercise 3 — Isolation

Why do we only map `127.0.0.1:27027` and avoid publishing shard ports?

### Exercise 4 — Hostnames

Why does `rs.initiate` use `cfg:27019` instead of temporary container IPs?

### Exercise 5 — Quorum

Can a single-member replica set test electing a new primary when a node is lost?

### Exercise 6 — mongos Connection

What can go wrong if a Java app connects directly to `shard-a` to read all data?

### Exercise 7 — enableSharding

Starting in MongoDB 6.0, is calling `sh.enableSharding()` required before `sh.shardCollection()`?

### Exercise 8 — Shard Key

Propose two shard keys for an event stream and explain hashed/ranged trade-offs.

### Exercise 9 — Initial Chunks

Why do an empty hashed collection and an empty ranged collection have different initial chunk distributions?

### Exercise 10 — Dataset

Generate 20,000 documents with a 1 KiB payload and stable IDs; why use batching?

### Exercise 11 — Logical Count

How do you check the total document count through `mongos`?

### Exercise 12 — Owned vs. Orphan

Why must you use `numOwnedDocuments` instead of summing raw records read directly from shards?

### Exercise 13 — getShardDistribution

Read docs, data, chunks, and per-shard percentages from this helper.

### Exercise 14 — getShardedDataDistribution

Retrieve `ownedSizeBytes`/`numOrphanedDocs` for a namespace.

### Exercise 15 — Data Skew

Given 12,000/8,000 docs, compute per-shard percentages and `gap_pp`.

### Exercise 16 — Byte Skew

Two shards hold 10,000 docs each, yet bytes are 80 MB/20 MB. Is data size balanced?

### Exercise 17 — Chunk Count

Why does an equal number of chunks not prove documents are balanced?

### Exercise 18 — Config Metadata

Write a query against `config.collections` and `config.chunks` using UUID.

### Exercise 19 — Balancer

Distinguish `sh.getBalancerState()` from the balancer actively migrating chunks.

### Exercise 20 — Collection Balance Status

What question does `sh.balancerCollectionStatus` help answer?

### Exercise 21 — Ranged Split

With 20,000 events (`sequence` 0..19999), splitting at 10000 creates which ranges?

### Exercise 22 — Split vs. Move

Right after `sh.splitAt`, is data guaranteed to reside on both shards?

### Exercise 23 — Manual Migration

Explain `sh.moveChunk(namespace,query,destination)`; why should it only be run in a lab?

### Exercise 24 — Hashed Move

Why should the `sh.moveChunk()` helper not be used the same way with a hashed shard key?

### Exercise 25 — AutoMerger

A newly created split disappears from metadata. Explain why automatic merging could be a possible cause.

### Exercise 26 — Query Targeting

Compare `eventId` equality on the hashed collection with `sequence` equality on the ranged collection.

### Exercise 27 — Scatter-Gather

Why can a query filtering by `tenantId` touch both shards under both schemas in this lesson?

### Exercise 28 — Explain

List the fields to inspect to determine shards targeted and documents examined.

### Exercise 29 — Cardinality

If a shard key has only two `status` values, what is the risk?

### Exercise 30 — Frequency

If `tenantId=tenant-A` accounts for 90% of events, will hashing `tenantId` split `tenant-A` across multiple shards?

### Exercise 31 — Monotonicity

Why does a monotonically increasing `sequence` create a write hotspot under range sharding?

### Exercise 32 — analyzeShardKey

Starting in MongoDB 7.0, which tool helps evaluate cardinality and monotonicity?

### Exercise 33 — Query Sampling

Why can read/write distribution return 0 when no queries have been sampled?

### Exercise 34 — Orphans

After a migration, why can source shard disk bytes remain high even after ownership switched?

### Exercise 35 — Low-Volume Lab

Why might 20 MB of data not trigger automatic splits or migrations?

### Exercise 36 — Performance

To compare two shard keys fairly, which variables must remain fixed?

### Exercise 37 — p95

Why can average latency hide occasional very slow queries caused by migrations?

### Exercise 38 — Unique Index

When sharding, how must unique indexes obey the shard-key prefix rule?

### Exercise 39 — _id Uniqueness

Why might `_id` not be globally enforced when `_id` is not part of the shard key?

### Exercise 40 — Zones

When zone constraints restrict region A data to a single shard, is 50/50 still a reasonable criterion?

### Exercise 41 — Resharding

What is the difference between refining a shard key and `reshardCollection`?

### Exercise 42 — MongoDB 8.0

What is the purpose of `sh.shardAndDistributeCollection`, and why does this lesson not use it by default?

### Exercise 43 — Same-Host Bias

Why does benchmarking four containers on a laptop fail to accurately predict multi-node production performance?

### Exercise 44 — Cleanup

Compare `docker compose down` and `down -v`. Which command deletes lab data?

### Exercise 45 — Runbook

If 100% of data resides on shard A, list at least eight investigation steps before considering resharding.

### Exercise 46 — Results Report

Create a T0/T1/T3/T4 table for the hashed and ranged collections showing owned docs, bytes, chunks, orphans, balancer state, and query targeting.

### Exercise 47 — Production Design

Suppose a multi-tenant app writes 50 million events/month. Select a shard key accounting for:
- Queries by `tenant+aggregate`.
- Queries by `eventId`.
- Batch reports over time ranges.
- Hot tenants and uneven traffic.
- Global uniqueness requirements.
- Regional data residency.
- Retention, indexes, backups, and reshard migration.
- SLOs and observability.

### Exercise 48 — Final Verification

An experiment shows a 52/48 document split on the hashed collection, yet p95 query latency worsens due to `tenantId` scatter. Is concluding "hashed is better than ranged" valid? List the missing metrics.

## 50. Integrated Practice Checklist

### Preparation

- [ ] Dedicated Docker Compose project, separate from other deployments.
- [ ] Router port bound only to localhost.
- [ ] No real data or real credentials.
- [ ] MongoDB version/image pinned.
- [ ] Config server and shards healthy.
- [ ] Router returns `msg:"isdbgrid"`.
- [ ] `listShards` lists two shards.
- [ ] No direct-shard application traffic.

### Data and Schema

- [ ] Both collections empty before sharding.
- [ ] Supporting indexes exist for shard keys.
- [ ] Hashed/ranged keys documented clearly.
- [ ] Workload uses stable IDs and high cardinality.
- [ ] Total `countDocuments` matches expected `N`.
- [ ] Global uniqueness not confused with per-shard local `_id`.
- [ ] Payload size, event fields, and indexes recorded.

### Measurement

- [ ] T0/T1/T2/T3 recorded with UTC timestamps.
- [ ] Owned documents measured.
- [ ] Owned uncompressed bytes measured.
- [ ] Chunk counts/ownership measured.
- [ ] Orphan documents measured after migrations.
- [ ] Balancer enabled/active/collection status measured.
- [ ] Per-shard percentages and skew calculated.
- [ ] `explain` inspected for targeted and scatter queries.
- [ ] Query p95/p99 measured under representative workloads.
- [ ] Logical data bytes not compared directly to disk bytes without explanation.

### Conclusion and Cleanup

- [ ] Performance not extrapolated from a single run.
- [ ] Root causes of skew explained.
- [ ] Initial state distinguished from settled state.
- [ ] Cardinality/monotonicity/hot keys evaluated.
- [ ] Index, query, and write trade-offs documented.
- [ ] No balancer/migration tampering in production.
- [ ] Only the verified Compose project cleaned up.
- [ ] Redacted measurements, tracing, and logs archived.

## 51. Summary

Sharding experiments deliver value when they turn a complex architecture into **explainable and reproducible measurements**:

1. **Build the right topology:** `mongos`, CSRS, and shard replica sets in an isolated environment. Single-member replica sets suffice for data-distribution labs, not failover/HA tests.
2. **Choose keys to test hypotheses:** a high-cardinality hashed key generally spreads writes; a monotonic ranged key can exhibit initial concentration and hot upper ranges.
3. **Measure the right quantities:** owned documents/bytes, chunks, orphan docs, and migration states are distinct numbers. Equal chunks do not imply equal data or equal load.
4. **Compare across multiple points in time:** sharding and balancing occur asynchronously. Results right after ingestion differ from the settled state.
5. **Verify routing:** point lookups on a full shard key can target one shard; queries omitting the shard key can scatter-gather even when data is evenly distributed.
6. **Maintain safety:** no direct-shard CRUD, no metadata edits, no manual moves/reshards in production for testing, and never expose an insecure lab on public networks.
7. **Report with discipline:** record versions, workload, shard states, owned counts, chunk counts, skew, targeted shards, and SLOs. Never replace measurements with a hoped-for "50/50".

**Key takeaway:** *Sharding partitions data by shard key—it does not magically split everything evenly. Measuring distribution is only step one; query routing, hotspots, and workload determine whether a design truly works.*

## Official MongoDB Documentation

- [Deploy a Self-Managed Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/deploy-shard-cluster/)
- [Sharding Architecture](https://www.mongodb.com/docs/manual/sharding/)
- [Sharding Overview and Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/)
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [Range-based Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/)
- [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/)
- [sh.shardCollection()](https://www.mongodb.com/docs/manual/reference/method/sh.shardcollection/)
- [sh.getShardedDataDistribution()](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/)
- [db.collection.getShardDistribution()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsharddistribution/)
- [sh.status()](https://www.mongodb.com/docs/manual/reference/method/sh.status/)
- [sh.balancerCollectionStatus()](https://www.mongodb.com/docs/manual/reference/method/sh.balancercollectionstatus/)
- [Manage Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/)
- [sh.splitAt()](https://www.mongodb.com/docs/manual/reference/method/sh.splitat/)
- [sh.moveChunk()](https://www.mongodb.com/docs/manual/reference/method/sh.moveChunk/)
- [Analyze Shard Key](https://www.mongodb.com/docs/manual/reference/command/analyzeshardkey/)
- [Sharded Collection and Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [sh.shardAndDistributeCollection()](https://www.mongodb.com/docs/manual/reference/method/sh.shardanddistributecollection/)
- [MongoDB Java Sync Driver — Connect to MongoDB](https://www.mongodb.com/docs/drivers/java/sync/current/connection/)
- [Security Checklist for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/security-checklist/)
