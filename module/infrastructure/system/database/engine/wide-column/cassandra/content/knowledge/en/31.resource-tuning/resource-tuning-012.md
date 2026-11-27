# Mutation, Batch, Collection, and Partition Sizes

> **Chapter:** Resource Tuning  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. Read and write performance depends on partition keys, query-driven table design, replication, consistency levels, memtables, the commit log, SSTables, compaction, repair, and how Java applications send CQL.

## 1. Objective: Recognizing Four Different Kinds of "Big"

A common design mistake is assuming "Cassandra handles heavy writes well, so we can send huge batches, stuff thousands of elements into collections, and keep all of a customer's data in one partition forever". Cassandra optimizes distributed writes by key very well, yet each request and each partition still consumes finite RAM, CPU, network, commit log, disk, and compaction/repair resources.

This lesson distinguishes **four independent sizes**:

| Entity | What Does It Measure? | Problems When Too Large |
|---|---|---|
| **Mutation** | Unit of data change sent and applied to one partition; size depends on encoded data/cells/tombstones | Consumes buffers, CPU, network, commit log; can exceed mutation limits or time out |
| **Batch** | Group of CQL write statements sent in one request; may affect one or multiple partitions | Coordinator must handle many ops; batchlog and fan-out consume resources; triggers warn/fail thresholds |
| **Collection** | A **list/set/map** column value in one row holding multiple elements | Reading/updating too many elements, tombstones, and compaction cost; hard to paginate element-by-element |
| **Partition** | All rows sharing the **same partition key** in a table | Hotspots, expensive reads/repairs/streaming, heavy SSTables and compaction; erratic latency |

**A small batch does not guarantee small mutations; small mutations do not guarantee a small partition; and small collections do not necessarily prevent hotspots.** Each layer needs its own constraints and monitoring metrics.

After this lesson, you should be able to:

1. Distinguish mutations, batches, collections, and partitions along with their resource impacts.
2. Choose properly when to use **LOGGED**, **UNLOGGED**, or no CQL batch at all.
3. Design bounded collections and convert unbounded data into clustered rows.
4. Estimate partition sizes and select buckets/shards from queries and write load.
5. Practice CQL and the Java driver, inspect size warnings, and diagnose incidents.

## 2. Looking at the Cassandra Write Path

When a Java app executes an **INSERT** or **UPDATE**, the request reaches a coordinator. The coordinator determines replicas from the partition key, replication strategy, and topology, then forwards the write to replicas. Each replica writes to its commit log and updates its memtable; later, the memtable flushes to SSTables. Compaction merges on-disk data according to the configured strategy.

~~~mermaid
flowchart LR
    A["Java application / CQL write"] --> C["Coordinator"]
    C --> P["Resolve partition and replicas"]
    P --> R["Replica"]
    R --> L["Commit log"]
    R --> M["Memtable"]
    M --> F["Flush to SSTable"]
    F --> K["Compaction, reads, and repair later"]
~~~

Request size applies pressure at **multiple points along the path**:

- **Client/driver:** builds and encodes bound values; thousands of statements or huge payloads can consume Java app heap.
- **Network/coordinator:** transfers bytes, schedules work, processes batches, and fans out to replicas.
- **Replica/commit log:** writes data, allocates buffers, and checks mutation size limits.
- **Memtable and flush:** large changes occupy memory and can trigger flushes/backpressure.
- **SSTables/compaction/repair:** data and tombstones keep generating cost well after the request is ACKed.

**Consistency levels** like **ONE** or **LOCAL_QUORUM** govern how many replicas must respond before returning success. They do not shrink mutations and do not turn multi-partition batches into ACID transactions.

## 3. Mutation: The Unit of Writing, Not CQL Row Count

### 3.1. What Is a Mutation?

At the implementation level, Cassandra represents changes to one partition as a **mutation**, holding updates to one or more rows/cells or tombstones within that partition. One CQL write can create a mutation; multiple operations in a batch targeting the same partition can merge into a larger mutation. Never equate **"one INSERT" = "one fixed-size mutation"**.

Example of a small row:

~~~sql
INSERT INTO app.events_by_tenant_hour
  (tenant_id, bucket_hour, happened_at, event_id, event_type, attributes)
VALUES
  (11111111-1111-4111-8111-111111111111,
   '2026-11-21T03:00:00Z',
   '2026-11-21T03:05:00Z',
   22222222-2222-4222-8222-222222222222,
   'login',
   {'device': 'web'});
~~~

If **attributes** is replaced by a massive collection or a multi-MiB blob, the statement still touches one row yet creates a huge mutation. Conversely, 10,000 tiny **INSERT**s in a batch spanning many partitions create many small mutations while making the **batch request** itself huge and expensive to coordinate.

### 3.2. Why Does Cassandra Cap Mutation Size?

- Mutations are serialized and shipped over the network; replicas must be able to receive, parse, and write them.
- The commit log is segmented; mutation sizes interact with commit log write/format constraints and version limits.
- Large mutations spike memory usage, processing latency, and the blast radius of retries.
- Slow replicas or timeouts can make the driver retry. If an operation is **non-idempotent**, extra care is required to prevent unintended updates.

Cassandra provides configs/guardrails on mutation size, such as **max_mutation_size_in_kb** in some versions. Defaults, parameter names, units, and interactions with **commitlog_segment_size_in_mb** differ across versions; inspect the **effective configuration** and error logs of your running cluster. Never copy a number from another version's docs and assume it is universal.

> **Never treat a config limit as a "target size".** A mutation below the rejection cap can still be prohibitively expensive for real latency, heap/native memory, and network bandwidth.

### 3.3. Shrinking Mutations via Data Modeling

Instead of stuffing a giant document into one cell:

- Split independently readable pieces into **multiple small rows**.
- If large objects must stay intact, consider storing objects in an object store while keeping metadata and reference keys in Cassandra.
- Do not blindly split an object by raw bytes across columns if queries still have to fetch all parts and create hotspots; design lifecycle, integrity, and read strategies properly.
- Enforce input payload, element-count, and field-length limits at the API layer; test using actual **CQL-encoded sizes**, not just pre-send JSON sizes.

## 4. CQL Batches: When Helpful, When Harmful?

**BATCH** groups multiple writes into one CQL request. It is frequently mistaken for a generic bulk-insert accelerator. In Cassandra, batching across many partitions to "save network round trips" usually loads down coordinators, the batchlog, and replicas.

### 4.1. Batch Types

| Usage | Key Semantics | When to Consider |
|---|---|---|
| **BEGIN LOGGED BATCH** (default for normal batches) | Uses the **batchlog** to help ensure multi-partition mutations complete across partial failures; does not provide multi-partition SQL transaction isolation/rollback | Business requirement mandates a multi-partition write group complete together per Cassandra batch semantics |
| **BEGIN UNLOGGED BATCH** | Skips writing a batchlog; for **single-partition** ops avoids unnecessary batchlog overhead; multi-partition can partially apply on failure | A handful of single-partition operations needing to be sent together; know the limits |
| **BEGIN COUNTER BATCH** | Exclusively for counter updates per counter semantics | Counter workloads; never mix counter and non-counter statements |

**BATCH is not a general bulk-loading tool.** For independent INSERTs across hundreds of partitions, **prepared statements + async requests with bounded concurrency/backpressure** generally outperform a big batch.

For a **single-partition batch**, updates may be coalesced into one partition mutation, giving partition-scoped atomicity/isolation per Cassandra semantics. For **multi-partition logged batches**, the batchlog supports replay/completion after certain failures, yet applications do not automatically observe an atomic cross-partition snapshot. Writing **BEGIN BATCH** provides **no rollback, no unique constraints, and no SQL multi-table transactions**.

### 4.2. Multi-Partition Batch Cost Flow

~~~mermaid
flowchart TD
    B["A BATCH with N INSERTs"] --> C["Coordinator"]
    C --> S{"How many partitions?"}
    S -->|One partition| M["Can coalesce into a single-partition mutation"]
    S -->|Many partitions| L["Logged batch may require batchlog"]
    L --> P["Distribute mutations to multiple replica sets"]
    M --> R["Replicas write commit log / memtable"]
    P --> R
    R --> X["Flush, compaction, and repair later"]
~~~

Statement count alone doesn't tell the full cost: **2 statements with 20 MiB blobs** can be far worse than **20 tiny statements**; meanwhile **20 tiny statements across 20 partitions** carry totally different fan-out costs from **20 statements in one partition**.

### 4.3. Batch Warnings and Limits

Many Cassandra versions enforce batch size warn/fail limits via parameters like **batch_size_warn_threshold** / **batch_size_fail_threshold** (or older **_in_kb**-suffixed names). Server-checked sizes reflect batch data/statements; exact enforcement rules and defaults must be checked per version.

When seeing **batch too large** warnings:

1. Record **statement count**, **distinct partition keys**, payload size, and batch type.
2. If statements are independent across many partitions, **split into throttled individual requests**.
3. If single-partition yet overly numerous, **break up the work**, cap mutation size, and bound partition growth; never default to batches for loading millions of rows.
4. Raise thresholds only with evidence from hardware, data model, and latency behavior; **raising limits never reduces resource pressure**.

### 4.4. Two Contrasting Examples

**Suitable case:** writing two small events for the same customer and hourly bucket. Both rows share **one partition key**.

~~~sql
BEGIN UNLOGGED BATCH
  INSERT INTO app.events_by_tenant_hour
    (tenant_id, bucket_hour, happened_at, event_id, event_type, attributes)
  VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-21T03:00:00Z', '2026-11-21T03:05:00Z',
     22222222-2222-4222-8222-222222222222,
     'login', {'device': 'web'});

  INSERT INTO app.events_by_tenant_hour
    (tenant_id, bucket_hour, happened_at, event_id, event_type, attributes)
  VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-21T03:00:00Z', '2026-11-21T03:06:00Z',
     33333333-3333-4333-8333-333333333333,
     'logout', {'device': 'web'});
APPLY BATCH;
~~~

**Case to avoid:** building a LOGGED BATCH of 5,000 events for 5,000 different customers hoping it runs faster. Those events span many partitions and replica groups; the coordinator bears heavy fan-out, batchlog writes, and result tracking. For independent writes, send individual requests with bounded in-flight concurrency and monitor timeouts/retries.

**Retry note:** A timed-out batch does not mean no replica applied the writes. For idempotent operations like an **INSERT** with the same primary key and deterministic business values/timestamp, retries are safer to manage than **counter increments** or logic generating a fresh ID on each attempt. Handle idempotency at the app layer and verify real consistency semantics.

## 5. Collections: Lists, Sets, and Maps Should Stay Small and Bounded

Cassandra supports collection columns:

| Type | Example | Characteristics |
|---|---|---|
| **set<text>** | Fixed product tags | Unique elements; no business ordering guarantee |
| **list<text>** | Short ordered step list | Ordered; index updates/prepends and concurrent edits can be costly |
| **map<text, text>** | Small set of event attributes | Key lookup/update; avoid unbounded key growth |
| **frozen<collection>** | Small value read/written atomically | Stored and updated as one blob; partial edits rewrite the whole value |

Collections suit a **small, bounded set of elements belonging to one row**. They do not replace a multi-row table when data keeps growing over time.

### 5.1. What Costs Do Large Collections Cause?

- **Reads:** fetching a collection column usually returns the whole collection; you cannot paginate element-by-element like clustering rows.
- **Writes:** replacing or updating many elements creates large mutations.
- **Tombstones:** deleting elements, overwriting non-frozen collections, or expiring element TTLs leaves deletion markers that must be read and cleaned via compaction.
- **Compaction/repair:** many cells and tombstones raise CPU, disk I/O, streaming, and read costs.
- **Limits:** element counts and encoded byte sizes can trip version or app guardrails/caps.

On a **non-frozen map**, individual keys can be updated:

~~~sql
UPDATE app.events_by_tenant_hour
SET attributes['device'] = 'mobile'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND bucket_hour = '2026-11-21T03:00:00Z'
  AND happened_at = '2026-11-21T03:05:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

This modifies only one map entry, yet **a map with tens of thousands of keys still signals a flawed data model**. When map keys are deleted repeatedly, tombstones also demand close monitoring.

### 5.2. When to Convert a Collection into a Table

Suppose an account generates unbounded notifications. Never store them all in:

~~~sql
-- Modeling anti-pattern: unbounded growing list.
CREATE TABLE app.bad_notifications (
    tenant_id uuid PRIMARY KEY,
    messages list<text>
);
~~~

For daily growing lists, a better model is **one notification = one row**, partitioned by tenant and time bucket:

~~~sql
CREATE TABLE app.notifications_by_tenant_day (
    tenant_id uuid,
    bucket_day date,
    created_at timestamp,
    notification_id uuid,
    message text,
    PRIMARY KEY ((tenant_id, bucket_day), created_at, notification_id)
) WITH CLUSTERING ORDER BY (created_at DESC, notification_id ASC);
~~~

Now the application can query **by partition key**, cap row counts, and paginate cleanly. You must still budget partition size per **bucket_day**; switching to rows does not automatically make partitions bounded if the partition key remains just `tenant_id`.

**Rule of thumb:** collections describe **small attributes of a single entity**; datasets with their own lifecycle, independent queries, or unbounded growth belong in rows/tables modeled for the access pattern.

## 6. Partition: Unit of Data Distribution and Source of Hotspots

In the wide-column model, the **partition key** determines the token and replica set owning a logical partition. **Clustering columns** order multiple rows inside that partition.

Example:

~~~sql
CREATE KEYSPACE IF NOT EXISTS app
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS app.events_by_tenant_hour (
    tenant_id uuid,
    bucket_hour timestamp,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    attributes map<text, text>,
    PRIMARY KEY ((tenant_id, bucket_hour), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

Here **(tenant_id, bucket_hour)** is the **composite partition key**; all events for the same tenant within one UTC hour live in the same partition (assuming consistent bucket calculation).

~~~mermaid
flowchart TB
    A["tenant_id + bucket_hour"] --> T["Partition key → token"]
    T --> R["Replicas chosen per replication"]
    R --> P["Partition holds multiple rows"]
    P --> C1["happened_at DESC, event_id"]
    P --> C2["happened_at DESC, event_id"]
    P --> C3["... within size budget"]
~~~

**Replication factor (RF)** controls logical copy count—it does not split one partition into pieces across RF. For instance, RF = 3 means **each owning replica holds a copy of the partition**, not one-third of that partition.

### 6.1. Why Do Large Partitions Cause Trouble?

- **Read amplification:** scanning many rows, tombstones, multiple SSTables, or overly wide ranges drives up read work.
- **Hot partitions:** if one partition takes a huge share of writes/reads, its replica group bottlenecks; adding nodes does not automatically split one hot partition.
- **Compaction:** huge partitions with frequent updates/deletes create heavy background load; tombstones make read latency erratic.
- **Repair/streaming:** transferring or reconciling oversized partitions drags out and consumes heavy I/O and network.
- **Memory/GC:** queries, iterators, buffers, and read/write structures suffer pressure; **`LIMIT 20` does not turn a 10 GiB partition into a small partition**.
- **Availability:** losing one replica group heavily impacts ultra-hot partitions.

There is **no single optimal partition-size limit for every Cassandra cluster**. Benchmarks like "tens of MiB" or "100 MiB" are **operational heuristics**, not universal caps—and certainly not targets to fill up to. Pick budgets from query shapes, row counts, row widths, tombstones, storage, replication, consistency levels, and real measurements.

### 6.2. Estimating to Design Buckets

Suppose a tenant writes an average of **10 events/second**, each with **512 bytes of useful payload**, uniformly distributed.

~~~text
Events per day = 10 × 86,400 = 864,000
Payload/day = 864,000 × 512 B = 442,368,000 B ≈ 421.9 MiB

Events per hour = 10 × 3,600 = 36,000
Payload/hour = 36,000 × 512 B = 18,432,000 B ≈ 17.6 MiB
~~~

Using **(tenant_id, day)** yields roughly **422 MiB/partition/day** in payload alone. Switching to **(tenant_id, hour)** drops payload to ~**17.6 MiB/partition/hour**.

These are **initial estimates**, not exact SSTable size predictions. Account for primary keys, timestamps, cell metadata, tombstones, storage format, compression, TTLs, and traffic bursts. A tenant spiking 20x above average can still blow up an **hourly partition**.

Useful formulas:

~~~text
expected_payload_per_partition
  ≈ events_per_second × seconds_per_bucket × average_payload_bytes

min_buckets_by_capacity
  ≈ ceil(payload_in_window / payload_budget_per_bucket)
~~~

**Never size buckets on bytes alone**: also bound **requests/second per partition**, row count, query shape, and the cost of merging results across multiple buckets.

### 6.3. Choosing Buckets Around Access Patterns

| Design Option | Advantages | Trade-Offs |
|---|---|---|
| **tenant_id** as sole partition key | Simple queries over a tenant's entire history | Easily becomes an unbounded partition / hotspot |
| **(tenant_id, day)** | Easy daily queries, smaller partitions | Very active tenants still build large partitions |
| **(tenant_id, hour)** | Smaller partitions, well-suited to time-ordered data | Multi-day queries touch and merge many partitions |
| **(tenant_id, day, shard)** with deterministic sharding | Spreads write load of ultra-hot tenants | Reads must fan out across shards and merge in time order; higher complexity |

Compute **bucket_hour** from timestamps in a canonical timezone such as **UTC**, applying the exact same rule on writes and reads. Querying from 02:30 to 04:15 UTC requires querying buckets 02:00, 03:00, and 04:00 and merging by timestamp if global ordering is required.

Never use **random buckets** if the application cannot tell which shard holds data. When sharding is mandatory to spread a hot tenant, encode a deterministic shard rule or explicit shard list to read, while bounding fan-out.

## 7. CQL by Partition Key: Bounded on Both Reads and Writes

For **events_by_tenant_hour**, a typical query is:

~~~sql
SELECT happened_at, event_id, event_type, attributes
FROM app.events_by_tenant_hour
WHERE tenant_id = ?
  AND bucket_hour = ?
LIMIT ?;
~~~

Both partition key components are bound, enabling the driver to compute routing keys/tokens when metadata is available and route efficiently to replicas. Clustering columns fetch the newest events inside the bucket.

Reading a slice within **one partition**:

~~~sql
SELECT happened_at, event_id, event_type
FROM app.events_by_tenant_hour
WHERE tenant_id = ?
  AND bucket_hour = ?
  AND happened_at >= ?
  AND happened_at < ?
LIMIT ?;
~~~

The range filter targets **happened_at**, a clustering column. Its cost differs completely from reading every event across all hours for a tenant or filtering on a non-key column. **Prepared statements and bindings** optimize CQL reuse, type safety, and token-aware routing; they **do not fix oversized partitions or multi-partition batches**.

## 8. Java Driver 4.x: Prepare Once, Write Small Groups

The example below writes two events for the same tenant/bucket inside a small **UNLOGGED BATCH** using a **prepared statement** and proper types. The environment requires Cassandra and a compatible 4.x **java-driver-core** dependency.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class SmallPartitionBatchDemo {
    public static void main(String[] args) {
        UUID tenantId =
            UUID.fromString("11111111-1111-4111-8111-111111111111");
        Instant t1 = Instant.parse("2026-11-21T03:05:00Z");
        Instant t2 = Instant.parse("2026-11-21T03:06:00Z");
        Instant bucketHour = t1.truncatedTo(ChronoUnit.HOURS);

        // Replace address and dc1 to match your actual cluster.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO app.events_by_tenant_hour " +
                "(tenant_id, bucket_hour, happened_at, event_id, " +
                "event_type, attributes) VALUES (?, ?, ?, ?, ?, ?)");

            // Both statements share the same composite partition key.
            BoundStatement first = insert.bind(
                tenantId, bucketHour, t1, UUID.randomUUID(),
                "login", Map.of("device", "web"));

            BoundStatement second = insert.bind(
                tenantId, bucketHour, t2, UUID.randomUUID(),
                "logout", Map.of("device", "web"));

            BatchStatement batch =
                BatchStatement.builder(DefaultBatchType.UNLOGGED)
                    .addStatement(first)
                    .addStatement(second)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM)
                    .build();

            session.execute(batch);
        }
    }
}
~~~

**Conditions and limits:**

- Keyspace/table exist as in Section 6 and the datacenter is actually named **dc1**, or replaced accordingly.
- With RF = 3, **LOCAL_QUORUM** requires enough local-DC replicas to meet quorum; never treat a single-node setup as proof this config is production-ready.
- **bucketHour** is derived from `t1` truncated in UTC; `t2` must be verified to fall in the same hour. When batching multiple timestamps, the app must **check every timestamp** before grouping.
- **Map.of** requires Java 9+; attribute maps should have input size validation.
- The example generates random UUIDs in **main**. Production apps with retries should **preserve the same `event_id`** for a given event to avoid writing duplicate rows on retry.
- Reuse **CqlSession** and **PreparedStatement** long-term in the app. Never create a new session or re-prepare on every request.
- **Batch size = 2** merely illustrates usage. It is not a universal optimum; often two separate async requests are simpler and sufficient.

### 8.1. What If Events Span Many Partitions?

For independent events across many tenants or buckets, send **individual `BoundStatement`s** through the driver using async APIs where appropriate and enforcing **in-flight limits**. Track timeouts, queues, retries, backpressure, and replica load. Never pack thousands of statements into a `LOGGED BATCH` as a substitute for concurrency control.

Implementation pseudocode:

~~~text
prepare INSERT once
for each event:
    validate payload/collection size
    calculate tenant_id + bucket_hour
    build bound statement with stable event_id
    submit within in-flight request budget
    on completion: update outcome / handle safe retries
~~~

This pseudocode does not prescribe a fixed concurrency number. Proper caps depend on topology, connection pools, payloads, consistency, replica speed, and target latency.

## 9. Diagnosis: Match the Right Metric to the Right Problem

| Symptom | Hypothesis to Test | Priority Action |
|---|---|---|
| Server logs **mutation too large** | A single row/blob/collection or coalesced partition mutation is huge | Shrink write units; split data across rows/design, verify version limits |
| Server warns **batch too large** | Too many statements/payload bytes or batch spans many partitions | Count partitions per batch, split requests, cap statements and bytes |
| Writes time out during multi-tenant batches | Coordinator fan-out, batchlog, slow/overloaded replicas | Switch to bounded-concurrency individual requests; check retries, compaction, nodes |
| Read p99 climbs as one tenant grows | Huge partition, many SSTables/tombstones/hotspot | Bucket/shard for access patterns, inspect partition histograms |
| Heavy collection deletes/updates slow reads | Many cells/tombstones, compaction lagging | Replace unbounded collections with rows, curb unnecessary updates/deletes |
| Compaction/repair drags out | SSTables, tombstones, huge partitions, I/O or replica divergence | Inspect compaction/repair metrics, partition design, and maintenance schedule |
| JVM heap/native pressure rises under write load | Oversized payloads/concurrent requests overloading coordinators/buffers | Shrink payloads and in-flight counts; measure GC/RSS/queues—don't just raise heap |
| Java app OOMs during bulk import | Buffering too much data and batches/BoundStatements in RAM | Stream in small batches, throttle requests, avoid holding full input in memory |

### 9.1. Operational Tools

On supporting Cassandra versions, use these observation commands:

~~~bash
# Table and partition stats: max/mean sizes,
# estimated partition counts, SSTables, and tombstone metrics.
nodetool tablestats app.events_by_tenant_hour

# Histograms of partition size/row count per version.
nodetool tablehistograms app events_by_tenant_hour

# Queues or active tasks.
nodetool tpstats

# Background compaction pressure.
nodetool compactionstats

# Single-node overview.
nodetool info
~~~

Field names, flags, and units vary by version. Correlate table metrics, JMX/Prometheus, server logs, and **Java driver** metrics over the exact same window. For instance, a small **mean partition size** can hide a few **giant partitions**; check distributions/maxima and workload-driven hot partitions.

### 9.2. Measurements to Collect

1. **Per write request:** serialized payload size, statement count, distinct partition keys, batch type, p50/p95/p99 latency, timeouts.
2. **Per table:** partition size distribution, rows per partition, tombstones, SSTable counts, read/write latency.
3. **Per node:** heap/GC, native memory, network, disk I/O, pending tasks, compaction/flushes/repair.
4. **Per client:** in-flight requests, retries, timeouts, request queues, error rates.
5. **Over time:** changes across ingest, TTL expirations, compaction, and repair runs; never conclude from one snapshot.

**Query tracing** in `cqlsh` helps dissect a single query, yet adds overhead. Enable it selectively in appropriate environments—never across all production requests.

## 10. Connecting to Replication, Consistency, Compaction, and Repair

### Replication and Consistency Levels

A partition replicates across nodes per the replication strategy. More replicas improve availability and consistency options, yet multiply storage and maintenance work. With **LOCAL_QUORUM** and RF = 3 in one DC, the coordinator normally waits for at least **2 replicas** in that DC; if replicas saturate from a hot partition or giant mutations, requests still time out.

**Token-aware routing** helps pick favorable coordinators when CQL binds the full partition key. It does not split a hot partition, bypass mutation size limits, or automatically strengthen consistency.

### Compaction and Tombstones

Cassandra uses an LSM storage engine. Deletes and expired TTLs write **tombstones** per Cassandra semantics; SSTables must compact/reconcile safely before eligible tombstones are purged. Frequent collection edits/deletes or giant partitions drive up read amplification, I/O, and compaction backlogs.

**A short TTL** does not mean expired data disappears immediately from all SSTables upon expiration. Compaction cycles and deletion safety rules still govern disk usage and read performance.

### Repair and Streaming

Repair reconciles data across replicas, while streaming transfers required ranges. Oversized partitions, dense tombstones, or skewed data on a subset of replicas lengthen maintenance runs and resource consumption. Bucket designs must be tested against **both query workloads and repair/streaming**, not just INSERT throughput.

## 11. Practical Sizing Workflow

No universal threshold fits every Cassandra/JDK/hardware stack. Start from **application budgets and empirical measurement**, then compare against configured guardrails:

1. **Set input limits:** max event bytes, max map keys, string length caps, and per-tenant write rates.
2. **Define access patterns:** reads by tenant/hour, result pages, retention periods; partition design must serve queries.
3. **Estimate partition size:** from peak events/s, encoded payload size, and seconds per bucket; reserve margin for row overhead, tombstones, compression, and skew.
4. **Bound batches:** group only when semantics require; budget **statement count, distinct partitions, and bytes**—not statement count alone.
5. **Measure on representative data:** p95/p99, throughput, timeouts, GC, disk I/O, partition histograms, compaction, and repair at peak load.
6. **Test failure modes:** slow replicas, coordinator restarts, retries, timeouts, replays/repairs. Check for duplicate writes, load amplification, or availability drops.
7. **Set operational thresholds and alerts:** tune input caps, buckets, concurrency, and configs from metrics; keep a rollback path if changes worsen latency or error handling.

For example, a team might set an **application target budget of 16–32 MiB/partition** for a short-lookup workload while capping event payload sizes at the API. That is solely an **illustrative application-driven budget**; another system may need smaller bounds or safely handle larger ones after measurement. Never assume Cassandra guardrails share that exact value.

## 12. Scenario Exercises

### Exercise 1 — Identifying Mutations and Batches

An app needs to send 2,000 events of 1 KiB each across 2,000 distinct tenants. A developer proposes **one LOGGED BATCH** for "a single network round trip".

**Questions:**

1. At least how many independent partitions are touched in this scenario?
2. Why can a ~2 MiB total batch cause problems even though each event is tiny?
3. What approach is far better when writes do not belong to one logical group needing batch semantics?

**Hints:** Up to 2,000 distinct partitions; coordinator and batchlog suffer huge fan-out, tripping limits/timeouts. Use a prepared statement and individual async requests with bounded in-flight concurrency, idempotent retries, and per-request error tracking.

### Exercise 2 — Collection or Multiple Rows?

A table holds a **list<text>** column recording a user's entire action history. After several months, some rows hold hundreds of thousands of elements; the app only needs the latest 50 actions.

**Question:** Why is a collection unsuitable? Propose a new primary key.

**Hints:** Collections offer no element-level pagination like clustering rows, and unbounded growth causes huge mutations and tombstones. Switch to **((user_id, bucket_day), happened_at, event_id)** with descending clustering order; use smaller buckets if daily volume exceeds budgets.

### Exercise 3 — Estimating Partition Size

One tenant produces **50 events/second** with an average **1 KiB** payload.

~~~text
In one day:
50 × 86,400 × 1,024 B = 4,423,680,000 B ≈ 4.12 GiB

In one hour:
50 × 3,600 × 1,024 B = 184,320,000 B ≈ 175.8 MiB

In 5 minutes:
50 × 300 × 1,024 B = 15,360,000 B ≈ 14.6 MiB
~~~

If operations set a **target budget of 32 MiB payload per partition**, is a **day**, **hour**, or **5-minute** bucket more likely to fit? Must peak load and row overhead also be counted? What must a full-day read do?

**Hints:** 5 minutes fits on average, yet you must check peak bursts and real overhead; full-day reads will have to query and merge many buckets, raising fan-out. Balance partition size against read requirements.

### Exercise 4 — Timeouts and Retries

A Java client runs **BEGIN BATCH** with multiple updates and times out after sending the request. The developer assumes "timeout = no writes applied" and generates a fresh `event_id` on retry.

**Questions:** What is the risk? What changes make retries safe?

**Hints:** Some or all writes may have applied; the batchlog may also complete writes after failure for logged batches. Keep `event_id` deterministic, use idempotent operations where possible, check outcomes, and implement application-level deduplication.

## 13. Self-Check Questions

1. **If an INSERT carries a 40 MiB blob, is a batch size of one statement guaranteed safe?**  
   No. Oversized mutations/values still risk tripping limits, straining resources, or timing out.

2. **Why doesn't adding replicas completely solve a hot partition?**  
   All copies of a partition still reside on a finite replica set; raising RF does not split a partition into shards automatically.

3. **Is a multi-partition LOGGED BATCH equivalent to an RDBMS ACID transaction?**  
   No. Cassandra uses a batchlog to help finish grouped writes after certain failures, yet provides no SQL-style multi-partition isolation/rollback.

4. **Why doesn't `LIMIT 20` let you ignore oversized partitions?**  
   `LIMIT` caps returned rows, while the cost of scanning SSTables, tombstones, and hotspots still depends on storage layout.

5. **When are collections appropriate?**  
   When element counts are small, bounded, and accessed as attributes of one row; unbounded growing data belongs in multiple rows.

6. **Where should choosing a bucket size start?**  
   From access patterns, peak event rate, payload sizes and skew, latency SLAs, and empirical testing.

## 14. Summary

**Mutation, batch, collection, and partition are four distinct size scopes.** Mutations affect a single partition's write path; batches group operations and can trigger fan-out/batchlog cost; collections hold multiple values inside one row's column and must stay bounded; partitions route data to replicas and dictate where read/write load concentrates.

To tune Cassandra sustainably, cap input sizes, keep collections small, avoid arbitrary multi-partition batches, design partition keys/buckets around queries, and measure peak loads. Prepared statements with complete key bindings help Java apps send steady requests, while replication/consistency, compaction, and repair govern the real resources required to run the cluster. **Never raise configuration limits just to mask a data model growing without bounds.**
