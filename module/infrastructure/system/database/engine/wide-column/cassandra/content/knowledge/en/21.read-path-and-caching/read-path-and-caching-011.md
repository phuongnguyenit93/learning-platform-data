# Token-Range Reads vs. Single-Partition Queries

## 1. Two Read Patterns, Two Very Different Workloads

In **Apache Cassandra**, two CQL statements may both return rows from a wide-column table, yet their execution paths and costs differ dramatically:

- **Single-partition read:** knowing the **full partition key**, Cassandra computes the partition's token, locates the responsible replica set, and reads rows belonging to that partition. This is the preferred read path for most user-facing APIs.
- **Token-range read (partition-range scan):** queries partitions whose tokens fall within a range on the token ring, typically spanning **many partitions** across **multiple replica sets**. Useful for batch scans, data migration, or auditing, it is not automatically efficient for interactive user requests.

In Cassandra's data model, the **partition key determines where data lives**, while **clustering columns govern ordering and row slicing inside a partition**. Picking the right read path depends on your application's question and query-driven table design, not just `SELECT` syntax.

**Lesson objectives:** distinguish routing between the two query types, understand how they use memtables/SSTables and caches, write valid `token(...)` CQL, choose consistency levels, apply Java Driver practices, and avoid pitfalls when scanning large datasets.

**Scope:** examples use `Murmur3Partitioner`, standard full replicas, and Apache Cassandra/CQL; caching details and read optimizations vary by version, configuration, and workload.

## 2. Foundations: From Partition Key to Token and Replicas

Consider a table storing readings by sensor and day:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_sensor_day (
    sensor_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Primary key semantics:**

| Component | Role | Query Consequence |
| --- | --- | --- |
| `(sensor_id, event_day)` | **Composite partition key** | Together, both values identify **one partition** and its token. |
| `event_time` | First clustering column, descending order | Supports time-range queries **inside a known partition**. |
| `event_id` | Second clustering column | Disambiguates rows sharing the same timestamp. |
| `reading` | Regular column | Data payload; cannot route partition lookups without a separate query table/path. |

For instance, `('sensor-9', '2026-11-21')` is **one** partition; `('sensor-9', '2026-11-22')` is a **different** partition even for the same sensor. Cassandra computes the token from **both partition key components in exact order**; with `Murmur3Partitioner`, tokens span a signed 64-bit integer range.

Using the replication strategy, token, and DC/rack topology, Cassandra knows which **replicas** hold that partition. RF = 3 in `dc1` targets three distinct replica nodes for the partition, provided the cluster has enough nodes. The node receiving the request acts as **coordinator** for that request; it may be a replica or simply coordinate reads to replicas.

~~~mermaid
flowchart TD
    PK["Partition key: (sensor-9, 2026-11-21)"] --> H["Partitioner computes one token"]
    H --> T["Token identifies position on ring"]
    T --> R["Replication strategy + topology select replicas"]
    R --> P["Read single partition from that replica set"]
    T --> S["Token-range query spans many ring segments"]
    S --> M["Many partitions, potentially many replica sets"]
~~~

**Do not confuse three types of ranges:** a **clustering key** range (time within one partition), a **token** range (many scattered partitions), and a **business value** range (e.g., days 1–30). They are not equivalent.

## 3. Single-Partition Queries: The Primary Application Read Path

### 3.1. CQL Targeting One Exact Partition

To fetch readings for `sensor-9` on November 21:

~~~sql
SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Both partition key components use equality predicates; Cassandra computes **one token** and resolves **one replica set**. `LIMIT 50` caps returned rows without changing where the partition lives.

To query a **time interval inside that exact partition**:

~~~sql
SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

This is a **clustering-range read within one partition**, not a token-range scan. Cassandra exploits clustering-key ordering to narrow scanned rows. Making `(sensor_id, event_day)` a composite partition key is a form of **bucketing** that prevents dumping every event for a sensor into an unbounded partition.

### 3.2. Logical Steps of the Read Path

1. **Driver selects a coordinator.** With a prepared statement binding the full partition key, the Java Driver can compute the routing key/token to **prefer an owning replica** in the local datacenter (*token-aware routing*), depending on policy and topology.
2. **Coordinator resolves replicas and consistency level.** For example, at RF = 3, `LOCAL_QUORUM` requires two eligible replica responses in the local DC; `LOCAL_ONE` requires one.
3. **Replica accesses local data.** It inspects the memtable and candidate SSTables using lookup structures and caches where applicable.
4. **Coordinator reconciles results.** The read path may use full-data and digest responses, reconcile versions, and perform read repair if configured/needed per version.
5. **Returns matching rows.** Clustering order applies **within the partition**; manage paging if results are large.

Reading a single partition involves far less routing and scanning than multi-partition scans. Still, an **oversized partition** can make even a single-partition read slow or overloaded; "knowing the partition key" does not guarantee every query is cheap.

## 4. Caches and Lookup Layers Assisting Partition Reads

Cassandra persists data primarily in immutable **SSTables**, while recent writes may still live in the **memtable**. On read, a replica combines current logical state across sources; SSTables can hold stale versions, tombstones, or expired TTLs.

| Component | Role on the Read Path | During Single-Partition Read | During Token-Range Scan |
| --- | --- | --- | --- |
| **Memtable** | Supplies recent unflushed writes | Checks matching rows of the partition | May traverse many partitions within the scanned range |
| **Per-SSTable Bloom filter** | Probabilistic filter quickly rejecting SSTables **guaranteed not to hold** a partition key; can false-positive | Helpful when checking one partition across many SSTables | Sequential scanning across many partitions gains little from single-key exclusion |
| **Partition index / index summary** | Helps locate partition offsets in SSTables | Quickly locates target partition | Aids seeking/iterating the range, yet many partitions still must be read |
| **Key cache** | Caches lookup offsets/metadata for frequently read partitions | Benefits repeated hot-partition reads when eligible | Hit rate drops when each partition is read only once |
| **Row cache** (if enabled) | Retains partition/row data per version config | Useful for small, repeatedly read partition sets | Broad scans dilute effectiveness or evict hot entries |
| **Chunk / compressed block cache** (version-dependent) | Reduces repeated reads/decompression | Helpful for frequently accessed blocks | Low payoff when reading many blocks once |
| **OS / filesystem page cache** | Keeps recently read file pages in RAM | Repeated reads benefit | Broad scans exert memory pressure and disk I/O |

**Bloom filters never cache `SELECT` results**, and key cache is not a full copy of partition data. Never assume "cache hit = skip replica checks" or "enabling caches makes token scans cheap." Reads remain bound by the coordinator's consistency level.

Simplified diagram of a **replica read**:

~~~mermaid
flowchart TD
    R["Read request arrives at replica"] --> M["Check memtable"]
    R --> C{"Eligible to serve from cache?"}
    C -->|"Valid cache hit"| P["Data source fetched faster"]
    C -->|"Cache miss / needs merge"| B["SSTables: Bloom filter and partition index"]
    B --> S["Read relevant data / tombstones"]
    M --> X["Reconcile by timestamp/tombstone/TTL"]
    P --> X
    S --> X
    X --> A["Return data or digest to coordinator"]
~~~

This diagram shows lookup concepts; Cassandra optimizes read execution differently by query type, cache config, version, and SSTable count. **Compaction** can cut the number of SSTables checked, yet never turns `COUNT(*)` or token scans into constant-time operations. **Repair** fixes cross-replica divergence, not read-cache misses.

## 5. What Is a Token-Range Read?

Instead of specifying exact `sensor_id` and `event_day`, you ask Cassandra to read **all partitions whose tokens fall within a range**. This is especially useful for **batch scan workflows**: exports, backfills, reconciliation, recomputation, or migrations.

With the composite partition key above, the `token(...)` expression must list **both columns in exact schema order**:

~~~sql
-- Illustrative token range when using Murmur3Partitioner.
-- Can return multiple partitions, not just one sensor/day.
SELECT sensor_id, event_day, event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE token(sensor_id, event_day) > -4611686018427387904
  AND token(sensor_id, event_day) <= 0
LIMIT 100;
~~~

**Key syntax and semantic rules:**

- `token(sensor_id, event_day)` applies to the **entire partition key**. `token(sensor_id)` cannot substitute when the schema has a composite partition key.
- `>`, `>=`, `<`, `<=` compare **hashed token values**, not lexicographical `sensor_id` or chronological `event_day`.
- The example interval is **one segment** of the `Murmur3Partitioner` token space, not a specific date range or `sensor_id` range.
- `LIMIT 100` caps this query's sample to at most 100 rows; **never treat it as having processed the entire token range**.
- One partition may hold many rows; scanning a token range returns matching rows from **many partitions** depending on predicates.

### 5.1. Token Ranges Are Not Time Ranges

A common misconception:

~~~sql
-- Wrong idea: assuming comparing tokens between two dates filters dates.
-- The two tokens below do not form a "Nov 01..30 date range".
SELECT *
FROM telemetry_lab.readings_by_sensor_day
WHERE token(sensor_id, event_day) >
      token('sensor-9', '2026-11-01')
  AND token(sensor_id, event_day) <=
      token('sensor-9', '2026-11-30');
~~~

Hashed tokens **do not preserve chronological order** or sensor-name order. Between those two tokens lie partitions for countless unrelated sensors and dates. To read days 1–30 for one sensor, query the **known daily partitions** (or use a monthly bucket) and merge results in the application.

Within a single day, `event_time >= ... AND event_time < ...` in Section 3 is a **clustering-column range filter** made possible because the partition key is known.

### 5.2. Why Are Token-Range Reads More Resource-Intensive?

In a single-partition read, the coordinator knows the exact replica set for that partition. In a token-range query, the range can intersect **multiple assigned token subranges and multiple replica sets**, forcing the coordinator to orchestrate reads from multiple sources. Replicas must also read across many partitions and SSTables within that range.

~~~mermaid
flowchart LR
    C["Client requests tokens in (A, B]"] --> K["Coordinator"]
    K --> R1["Range 1: replica set X"]
    K --> R2["Range 2: replica set Y"]
    K --> R3["Range 3: replica set Z"]
    R1 --> OUT["Rows across many partitions"]
    R2 --> OUT
    R3 --> OUT
    OUT --> C
~~~

This diagram illustrates the **logical path**; subrange splitting, merging, and optimizations vary by version. Crucially, a token-range read **lacks a single partition key**, preventing the Java Driver from using single-key token-aware routing as it does for point reads.

Never use a token-range scan as a lazy substitute when your application already knows the partition key.

## 6. Direct Comparison of Both Read Paths

| Criterion | **Single-Partition** Query | **Token-Range** Query |
| --- | --- | --- |
| Routing predicates | Full partition key known; optional clustering bounds | `token(...)` constrained by token-range boundaries |
| Data scope | One partition and selected rows inside it | Many partitions within one or more token ranges |
| Replica sets involved | Typically one partition replica set | Potentially multiple replica sets across the token ring |
| Token-aware driver routing | Can usually pick an owning replica from partition key | No single routing key/replica to target directly |
| Cache effectiveness | Typically stronger on hot partitions and repeated queries | Scanning many partitions once yields lower cache reuse in most workloads |
| Main cost drivers | Rows in partition, tombstones, SSTables, CL, page size | Total partitions/rows, multiple SSTables/replicas, network, paging, scan duration |
| Data ordering | Clustering order **within the partition** | Not globally sorted by date/sensor; token order is not business order |
| Best-fit use cases | APIs querying by customer, sensor, account, or time bucket | Batch export, backfill, reindexing, token-range data audits |
| Consistency | Per-request CL; concurrent writes still apply | CL applies to read slices, **not a table-wide consistent snapshot** |

**A single partition can still be huge.** If one partition holds millions of rows or dense tombstones, even a full-key query can be slow. Design partition keys/buckets, clustering bounds, TTLs, and paging for real workloads.

## 7. Hands-On CQL on the Same Table

### 7.1. Prepare Sample Data

Assume the keyspace/table from Section 2 exists and the cluster has at least three nodes in DC `dc1`. Sample data:

~~~sql
INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T08:15:00Z',
     123e4567-e89b-42d3-a456-426614174001, 21.70);

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T09:15:00Z',
     123e4567-e89b-42d3-a456-426614174002, 21.85);

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-22', '2026-11-22T08:15:00Z',
     123e4567-e89b-42d3-a456-426614174003, 22.10);

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-10', '2026-11-21', '2026-11-21T08:15:00Z',
     123e4567-e89b-42d3-a456-426614174004, 19.90);
~~~

The three partitions here are:

1. `('sensor-9', '2026-11-21')` containing **two** rows.
2. `('sensor-9', '2026-11-22')` containing **one** row.
3. `('sensor-10', '2026-11-21')` containing **one** row.

You cannot guess which partitions fall in a given token range from sensor names or dates alone; compute the partitioner token to know.

### 7.2. Read One Partition and Inspect the Trace

In `cqlsh`:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21';

TRACING OFF;
~~~

Expect **two rows** in the same partition. Tracing reveals the coordinator, participating replicas, request timestamps, and read-path events (depending on version). With RF = 3 in `dc1`, `LOCAL_QUORUM` requires two valid replica responses in the local DC.

### 7.3. Scan a Token Range and Compare

~~~sql
CONSISTENCY LOCAL_ONE;
TRACING ON;

SELECT sensor_id, event_day, event_time, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE token(sensor_id, event_day) > -4611686018427387904
  AND token(sensor_id, event_day) <= 0
LIMIT 100;

TRACING OFF;
~~~

**Do not expect a fixed four-row output**: only partitions whose tokens fall inside the interval above are returned. Run on a small lab dataset, note which partitions appear, and compare the trace and latency against Section 7.2. On a real cluster, results and internal request counts depend on topology, token ownership, and CL.

To inspect node/range distribution:

~~~bash
nodetool status
nodetool ring
~~~

`nodetool ring` shows tokens/ranges owned by nodes—it **never implies a token range equals a date range**. `CONSISTENCY` and `TRACING` are **`cqlsh` shell commands**, not CQL clauses sent verbatim from Java.

## 8. Reading Large Datasets: Range Splitting, Paging, and Checkpointing

Full token scans typically serve batch jobs and require explicit lifecycle management. Never fire a single full-ring query and buffer everything in RAM.

### 8.1. Split into Non-Overlapping Ranges

For example, split a segment of token space into two intervals:

~~~text
(A, M]   and   (M, B]
~~~

Half-open `(start, end]` intervals avoid double-counting a token equal to `M`. With `Murmur3Partitioner`, tokens are signed 64-bit integers; plan carefully to cover **every part of the ring**, including negative/positive spans, boundaries, and **ring wraparound** if scanning all partitions. Never use naive date-style `start < end` intuition to assume full-ring coverage.

Splitting work using `nodetool ring` or driver token-map metadata merely **partitions scan responsibility**—it does not group by business key. Adding/removing nodes, shifting token ownership, or running repairs mid-scan can change observed data; batch jobs need checkpointing and retryability.

**Avoiding missed or duplicate rows on resume:** multiple partition keys can share the exact same token (rare hash collisions), and one token/partition can contain many rows. Saving only the **last row's token** and resuming with `>` can skip remaining rows or colliding partitions at that token. Use protocol paging state and job-level checkpoints paired with idempotent/deduplicated writes downstream.

### 8.2. Using Paging Properly

- **Page size** bounds how much data the driver requests per round trip, keeping response latency and memory controlled. It **does not reduce total rows** scanned across the full range.
- **Paging state** is a protocol/driver cursor for resuming the exact same statement and bound values. Never decode paging state as a token or reuse it on a different query.
- **`LIMIT`** caps total rows returned by a statement, making it great for sampling but unsuitable for exhaustive scans.
- **Bound concurrency:** scanning too many ranges or pages in parallel can saturate disks, network, CPU, and coordinators, causing timeouts for live API traffic.
- **Concurrent mutations during scans:** Cassandra does not provide MVCC-style table snapshots. Batch jobs must tolerate concurrent updates/deletes or use appropriate snapshot/pipeline strategies.

### 8.3. Metrics and Symptoms to Watch

| Metric / Symptom | Question to Answer |
| --- | --- |
| Read latency, timeouts, unavailable | Are too many ranges/reads running concurrently, or does CL exceed live replicas? |
| Cache hit ratio, OS page-cache pressure | Are scans evicting hot API partitions from caches? |
| SSTables per read and tombstone scans | Do compaction, TTLs, buckets, or table schemas need tuning? |
| CPU, disk IOPS, network, pending read tasks | Are range scans starving live API queries? |
| Paging throughput and resume failures | Are job checkpoints and retry handlers reliable? |
| Replica health, repair, topology changes | Were any ranges out of sync or shifting ownership mid-scan? |

Benchmark specific thresholds in lab/staging for your Cassandra version. **Never use `ALLOW FILTERING` to "speed up" a token scan**: it cannot turn a range scan into a single-partition read.

## 9. Java Driver 4.x Example: Single-Partition Routing vs. Range Scan

This example shows **two prepared statements** against the same table. The scan samples a small range with `LIMIT 100` and page size 50 to avoid an unbounded export loop:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public class CassandraReadPaths {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            // 1) Full partition key known: API-serving query.
            PreparedStatement onePartition = session.prepare(
                    "SELECT event_time, event_id, reading " +
                    "FROM telemetry_lab.readings_by_sensor_day " +
                    "WHERE sensor_id = ? AND event_day = ? LIMIT 50");

            BoundStatement pointRead = onePartition.bind(
                            "sensor-9", LocalDate.of(2026, 11, 21))
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(pointRead)) {
                System.out.println("point: " + row.getInstant("event_time")
                        + " = " + row.getBigDecimal("reading"));
            }

            // 2) No single partition key:
            //    sample scan of partitions by token; do not use as an API point read.
            PreparedStatement tokenScan = session.prepare(
                    "SELECT sensor_id, event_day, event_time, reading " +
                    "FROM telemetry_lab.readings_by_sensor_day " +
                    "WHERE token(sensor_id, event_day) > ? " +
                    "AND token(sensor_id, event_day) <= ? LIMIT 100");

            BoundStatement sampleRange = tokenScan.bind(
                            -4611686018427387904L, 0L)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
                    .setPageSize(50);

            for (Row row : session.execute(sampleRange)) {
                System.out.println("range: " + row.getString("sensor_id")
                        + " / " + row.getLocalDate("event_day")
                        + " = " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**How to read this example:**

1. `onePartition.bind(sensor_id, event_day)` gives the driver full partition key values for token-aware routing where supported.
2. `tokenScan.bind(startToken, endToken)` binds only **bigint token boundaries**; it does not identify a target partition key.
3. `LOCAL_QUORUM` and `LOCAL_ONE` are **illustrative choices** showing CL applies to both read paths; production must choose CL per consistency rules rather than defaulting scans to weaker CL.
4. `setPageSize(50)` streams results in pages, yet you still must bound the whole job if removing `LIMIT`. Synchronous driver iteration fetches subsequent pages automatically.
5. `127.0.0.1`, `dc1`, and token bounds are lab values. Real configs need production contact points, local DC, auth/TLS, and timeout policies.

For **production backfills**, track range/page checkpoints, cap worker concurrency, make retries idempotent, and reconcile counts at the sink. This sample is **not** a complete production scanner.

## 10. Common Reasoning Errors

| Claim | Verdict | Explanation |
| --- | --- | --- |
| "`WHERE token(pk) BETWEEN ...` is a single-partition query." | **False** | A token range can span many partitions, each with many rows. |
| "Tokens increase with `event_day`, so a token range equals a date range." | **False** | Tokens come from partitioner hashing; business-key order is not preserved. |
| "Once a partition is known, reading it is always fast." | **False** | Large partitions, many SSTables, and tombstones can make reads slow. |
| "Bloom filters definitively confirm a partition is in an SSTable." | **False** | Bloom filters can false-positive; only negative answers are definitive exclusions. |
| "Row cache / key cache replaces consistency levels." | **False** | Replicas still must be read/reconciled per the request's CL. |
| "`LIMIT 100` means the whole range was scanned after 100 rows." | **False** | It only caps rows returned by that statement. |
| "Page size 50 means the whole job reads only 50 rows." | **False** | The driver keeps fetching subsequent pages. |
| "`LOCAL_QUORUM` gives a consistent multi-partition snapshot." | **False** | CL does not create table-wide snapshot transactions. |
| "Saving the last token always resumes safely." | **False** | Remaining rows in the partition or token collisions can be skipped; use paging/checkpoints and deduplication. |

## 11. Practice Exercises with Answers

**Exercise 1.** A table has `PRIMARY KEY ((sensor_id, event_day), event_time, event_id)`. To read `sensor-9` measurements on Nov 21 from 08:00 to 09:00, choose a token scan or a single-partition read?

**Answer:** Choose a **single-partition read** because both `sensor_id` and `event_day` are known; use `event_time >= ... AND event_time < ...` to bound the **clustering range**.

**Exercise 2.** Why is `token(sensor_id)` invalid for token filtering on the example table?

**Answer:** The partition key has **two** components, `sensor_id` and `event_day`. You must write `token(sensor_id, event_day)` with all partition key columns in schema order.

**Exercise 3.** An app wants all November events across all sensors sorted by `event_time`. Should it query a token range assuming results come back time-ordered?

**Answer:** **No.** Token ranges group by partition-key hashes, not time. Use a query-driven monthly/bucket table, gather buckets and sort/aggregate, or use an analytics engine for cross-partition scans.

**Exercise 4.** A scan job raises `setPageSize` from 100 to 1,000. Does that reduce the total number of rows read?

**Answer:** **No.** It only changes rows fetched per page and the round-trip/memory trade-off. Measure latency, memory, and stability while capping concurrency.

**Exercise 5.** If a token range contains 20,000 partitions and each is read once, why are key cache and row cache less valuable than for an API hammering 10 hot partitions?

**Answer:** Caches pay off on repeated access to the same data/metadata. One-pass wide scans see little reuse and can evict hot entries; scan cost is dominated by I/O, multi-partition processing, and replica coordination.

**Exercise 6.** RF = 3 in `dc1`. Does a token-range read at `LOCAL_QUORUM` guarantee the whole result is an instant point-in-time snapshot?

**Answer:** **No.** For each read slice, the coordinator satisfies CL, yet different partitions are read at different instants; concurrent writes and deletes change state while the scan runs.

## 12. Choosing the Read Path from the Business Question

~~~mermaid
flowchart TD
    A["Need to read Cassandra data"] --> B{"Full partition key known?"}
    B -->|Yes| C{"Clustering column predicates?"}
    C -->|Yes| D["Single-partition read + clustering range"]
    C -->|No| E["Single-partition read by key"]
    B -->|No| F{"Goal is batch scan / backfill?"}
    F -->|Yes| G["Split token ranges + paging + checkpoints"]
    F -->|No| H["Redesign table around query / bucket / analytics"]
    D --> I["Measure latency, tombstones, and cache hits"]
    E --> I
    G --> J["Cap concurrency, safe retries, reconcile sink"]
~~~

**Key takeaway:** knowing the **full partition key** is the shortest path for Cassandra to locate replicas and look up a partition. Using `token(...)` **iterates across many partitions on the distribution ring**, fitting batch jobs rather than normal API reads. Both still pass through coordinator/replicas and face consistency levels, SSTables, tombstones, and cache costs; the decisive difference lies in **how much data scope is scanned** and **whether routing pinpoints a single partition**.
