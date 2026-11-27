# Designing Clustering Keys for Range or Ordering Conditions

> **Chapter:** Query Tuning  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, a distributed wide-column database; core topics include partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, failure handling, and Java application integration.

When users ask to "fetch the 50 latest events for a device" or "find transactions between time A and time B," the most critical decision usually lies in the **table's primary key**, especially the **clustering key**. In Apache Cassandra, the partition key identifies the partition and the replicas storing the data; clustering columns define the ordering **within each partition** and determine which range conditions Cassandra can process efficiently.

A table with many columns, indexes, or loaded data still may not support `WHERE event_time >= ...` or `ORDER BY event_time DESC` as expected. Cassandra is not a relational database that generates arbitrary sort or join plans; the standard practice is **designing tables for the queries they serve**.

This lesson walks through choosing **clustering column order**, using equality prefixes, placing the range-filtered column next, managing ascending/descending order, pagination, and verifying with execution data.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Distinguish partition keys, clustering keys, and regular columns in a Cassandra `PRIMARY KEY`.
2. Choose clustering column order for queries using `=`, `>`, `>=`, `<`, `<=`, and `ORDER BY`.
3. Explain why a range condition on a clustering column generally requires **preceding clustering columns to be constrained by equality**.
4. Predict which queries can read a contiguous slice within a partition and which require a different table model or costly filtering.
5. Choose appropriate `CLUSTERING ORDER BY`, time buckets, and tie-breakers to avoid oversized partitions and non-deterministic result ordering.
6. Practice CQL, inspect tracing/metrics, and consume paginated results from the Java Driver.

## 2. Two Parts of PRIMARY KEY Serving Two Roles

Consider a device events table:

~~~sql
CREATE TABLE events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

In the declaration `PRIMARY KEY ((device_id, event_day), event_time, event_id)`:

| Component | Role | Query impact |
|---|---|---|
| `(device_id, event_day)` | **Composite partition key** | Identifies a specific partition and token/replicas; should appear in full in queries needing direct access |
| `event_time` | **First clustering column** | Orders timestamps within a partition; supports scanning a time range once the partition is known |
| `event_id` | **Second clustering column** | Distinguishes events sharing the same timestamp and stabilizes ordering within same-timestamp groups |
| `event_type, payload` | Regular data columns | Do not automatically create an access order or enable efficient filtering without additional design |

**Do not confuse:** parentheses in `PRIMARY KEY` carry meaning. In `PRIMARY KEY ((device_id, event_day), event_time, event_id)`, the first two columns form a **composite partition key**, while the last two form the **clustering key**. That differs from `PRIMARY KEY (device_id, event_day, event_time, event_id)`, where only `device_id` is the partition key.

Rows sharing `device_id` and `event_day` reside in the same partition and are retrieved in clustering key order. SSTables, memtables, and multiple data versions may span different files; understand "sorted" as **logical order within the partition**, not a guarantee that all records sit contiguously in a single physical file.

~~~mermaid
flowchart TB
    Q["WHERE device_id = X AND event_day = D"] --> P["Partition (X, D)"]
    P --> A["event_time 09:05 — event_id 0a..."]
    A --> B["event_time 09:05 — event_id 9b..."]
    B --> C["event_time 08:42 — event_id 14..."]
    C --> D["event_time 08:01 — event_id 3e..."]
~~~

This is the default read direction produced by `WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)`: newest timestamps first, and ascending `event_id` for identical timestamps.

## 3. Equality Prefix and Range Rule: Column Order Matters

### 3.1. A Practical Design Rule

For a multi-column clustering key `(c1, c2, c3)`, the most natural query shape is:

~~~text
Partition key: full exact values
Clustering:    c1 = ... AND c2 = ... AND c3 >= lower AND c3 < upper
                              ^^^^^^^^^^^^^^^       ^^^^^^^^^^^^^^^
                              equality prefix        first range column
~~~

Cassandra can seek to the start of the clustering slice using the prefix `c1, c2`, then scan the segment matching the range condition on `c3`. If you skip `c1` to range-filter `c2`, rows for `c2` are scattered across many `c1` groups and no longer form a contiguous slice for this access path.

**Practical rule:** place columns commonly constrained by `=` at the start of the clustering key; place the range-filtered or ordering column immediately after that prefix. After a range condition, do not assume you can arbitrarily filter or sort on trailing clustering columns as in a relational SQL query. CQL supports certain tuple comparisons or version-specific restrictions, so verify validity and utility for each specific query.

### 3.2. Example with (event_time, event_id)

Suppose a query needs device X, day D, and the 08:00–09:00 hour:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
ORDER BY event_time DESC, event_id ASC
LIMIT 50;
~~~

This query has three noteworthy properties:

1. `WHERE` supplies both partition key columns so Cassandra knows exactly which partition to read.
2. `event_time` is the first clustering column; the two bounds define a **contiguous slice** in clustering order inside the partition.
3. `ORDER BY` matches the declared clustering order, so the engine returns rows in clustering order without an arbitrary full-set sort.

Using a **half-open** interval `[start, end)` (inclusive lower bound, exclusive upper bound) lets you chain consecutive windows without double-counting boundary events. For example, 08:00–09:00 uses `>= 08:00` and `< 09:00`; 09:00–10:00 starts at `>= 09:00`.

When multiple events share the same `event_time`, `event_id` acts as a tie-breaker. If `event_time` alone were the clustering key, multiple writes with the same partition and timestamp would map to the **same logical row** (update/upsert), silently overwriting distinct events. Adding `event_id` to the clustering key preserves each event individually.

### 3.3. Two Clustering Orders Are Not Equivalent

Suppose you have these queries:

- **Q1:** "Return all events for device X on day D, newest first."
- **Q2:** "Return `ERROR` events for device X on day D, ordered by time."

Model A:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

Model B:

~~~sql
PRIMARY KEY ((device_id, event_day), event_type, event_time, event_id)
~~~

Comparison:

| Query | Model A: `(event_time, event_id)` | Model B: `(event_type, event_time, event_id)` |
|---|---|---|
| Q1: all types, time scan | **Good fit:** time is the leading clustering column | **Not a direct fit:** rows are grouped by `event_type` before time |
| Q2: `ERROR` only + time | Filtering `event_type` requires another mechanism or reading/scanning rows and filtering client-side | **Good fit:** `event_type = 'ERROR'`, then range on `event_time` |
| Partition-wide chronological order | Present within each partition | Absent across the whole partition because primary grouping is `event_type` |

In Cassandra, if both Q1 and Q2 are critical at high volume, the usual solution is **two query-driven tables**, such as `events_by_device_day` and `events_by_device_type_day`. The application writes the same logical event to both; the trade-off is extra storage, write amplification, data lifecycle management, and retry/idempotency rules.

## 4. CLUSTERING ORDER BY: Read Direction Within a Partition

### 4.1. Default ASC; Declare DESC When Commonly Needed

Without `WITH CLUSTERING ORDER BY`, clustering columns default to ascending (`ASC`). For an event feed where the UI usually fetches the newest records, declaring:

~~~sql
WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
~~~

aligns reading from the head of the partition in **newest → oldest** order with the requirement. When reading oldest → newest, Cassandra can traverse the matching reverse order:

~~~sql
SELECT event_time, event_id, payload
FROM events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
ORDER BY event_time ASC, event_id DESC;
~~~

These two orders represent the **declared order** and the **exact inverse of the entire clustering sequence**, not an arbitrary per-column choice of `ASC`/`DESC`. For a table with mixed directions `(DESC, ASC)`, the valid inverse is `(ASC, DESC)`. Reverse-order reads can have different performance characteristics depending on workload and SSTable layout; measure on representative data.

### 4.2. Limits of ORDER BY in Cassandra

Fundamental rules:

- Standard `ORDER BY` applies only to **clustering columns** within a partition where the **full partition key is restricted**.
- Sort order is bound to the declared clustering key and its valid full reversal; it does **not** allow arbitrary `ORDER BY payload` when `payload` is a regular column.
- Partitioning by `device_id + event_day` guarantees ordering **only within that single day**. It does not produce a globally sorted result across multiple days, devices, or nodes.
- Secondary indexes/SAI can assist certain lookups, but do not turn Cassandra into a general cross-partition sorting engine.
- `ALLOW FILTERING` enables certain filter-heavy queries; it does **not** fix clustering order modeling and is rarely appropriate as a long-term performance solution.

The following example is **not** a valid query pattern for the current table:

~~~sql
-- Illustrates a requirement needing a different model; do not run as a valid lab query.
SELECT event_time, payload
FROM events_by_device_day
ORDER BY event_time DESC;
~~~

Without a `WHERE` clause bounding the partition key, Cassandra cannot deliver a global chronological order across all partitions with a single `ORDER BY` like a relational database.

### 4.3. LIMIT Is Not Sorting

`LIMIT 50` only caps the number of rows returned. If the clustering order does not correspond to "the 50 newest records," adding `LIMIT 50` **will not fix it**. Neither an index nor server-side filtering turns `LIMIT 50` into a business-accurate "top 50" without the right ordering mechanism.

Example:

| Clustering key | What does `LIMIT 50` return? |
|---|---|
| `(event_time DESC, event_id ASC)` | The first 50 newest events in the partition |
| `(event_type ASC, event_time DESC)` without `event_type = ?` | The first 50 rows of whichever type groups come first; **not** the 50 newest events across all types |
| No partition restriction | No global top-50 guarantee via standard `ORDER BY` alone |

## 5. Designing Clustering Columns with Multiple Filter Conditions

### 5.1. Equality Prefix Followed by Range

When a feature requires "`ERROR` events for tenant T on day D from 08:00 to 09:00," you can choose:

~~~sql
CREATE TABLE events_by_tenant_type_day (
    tenant_id uuid,
    event_day date,
    event_type text,
    event_time timestamp,
    event_id uuid,
    message text,
    PRIMARY KEY ((tenant_id, event_day), event_type, event_time, event_id)
) WITH CLUSTERING ORDER BY (
    event_type ASC,
    event_time DESC,
    event_id ASC
);
~~~

Well-aligned query:

~~~sql
SELECT event_time, event_id, message
FROM events_by_tenant_type_day
WHERE tenant_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_type = 'ERROR'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

Because `event_type` precedes `event_time` in the clustering key and is fixed by equality, `ERROR` events within that hour form a contiguous slice that can be scanned efficiently in the declared time order.

Query that is **not directly suitable**:

~~~sql
-- Anti-pattern illustration; may be rejected by Cassandra.
SELECT event_time, event_id, message
FROM events_by_tenant_type_day
WHERE tenant_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z';
~~~

Here, the equality constraint on the preceding clustering column `event_type` is missing. The engine cannot treat the partition as globally sorted by `event_time`. Never use `ALLOW FILTERING` to paper over a schema designed against the primary query.

### 5.2. Ordering Columns Based on Comparison Type

| Requirement | Design suggestion | Reason |
|---|---|---|
| History of one device in one day | Partition `(device_id, day)`; clustering `(event_time, event_id)` | Direct time range and ordering |
| History by **type** and time | Partition `(device_id, day)`; clustering `(event_type, event_time, event_id)` | Equality on type, range on time |
| History by **status** and time | Consider partition `(tenant_id, status, bucket)`; clustering `(updated_at, row_id)` | Status is the primary filter, grouped in the partition key |
| Latest events across **all** devices | Requires scoped table/aggregates (group, day, shard) plus merging | A device-partitioned table cannot provide global ordering alone |
| Lookup any event by `event_id` | Lookup table keyed by `event_id` or suitable access path | `event_id` as second clustering column does not support cluster-wide direct lookup |

High-cardinality columns do not automatically go first, nor do low-cardinality columns always go last. Order depends on the **`WHERE` pattern**: stable equality predicates precede range predicates, balanced against partition size and key mutability.

### 5.3. Mutable Clustering Columns Are a Risky Choice

Suppose you use `updated_at` as a clustering column for a ticket row and every ticket edit updates `updated_at`. In Cassandra, the **clustering key is part of the row's identity**. Changing a clustering value does not move the existing row in place: the application typically has to **DELETE the old key and INSERT the new key**.

That generates tombstones, extra writes, and transient inconsistency during dual-writes. For **append-only** event data, `event_time` is a natural fit; for mutable entities like tickets, consider separating an ID-keyed source-of-truth table from a latest-updated read model with proper synchronization and idempotency.

## 6. Choosing Partition Keys and Time Buckets Before Tuning Ranges

A clustering key cannot fix an oversized or hot partition. If you define:

~~~sql
PRIMARY KEY ((device_id), event_time, event_id)
~~~

then a device's entire lifetime history piles into one partition. Time-range queries are syntactically valid CQL, yet across millions or billions of events, the partition grows huge; writes for that device hit the same replica set, creating hot partitions, heavy compaction/tombstone overhead, and read amplification.

Adding a day bucket:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

bounds each partition's lifecycle and volume by day, while requiring clients to **supply the day** in queries. If a user asks for "the 50 latest events, possibly spanning multiple days," the application must:

1. Query today's partition in `event_time DESC` order with an appropriate `LIMIT`.
2. If fewer than 50 rows return, query the previous day's partition, continuing up to a bounded query limit.
3. If spanning multiple devices/shards, merge the sorted streams using the same time and tie-breaker comparator in the application/aggregator.
4. Bound fan-out, request concurrency, timeouts, and pagination tokens; do not scan thousands of buckets on every screen load when a dedicated read model would serve better.

### 6.1. Choosing Bucket Width from Measurements

| Bucket | Advantages | Costs |
|---|---|---|
| Monthly | Few partitions; long-range queries need fewer requests | Larger partitions; higher hot-key risk |
| Daily | Balanced for many time-series workloads | Multi-day queries need coordination |
| Hourly | Spreads data for high-frequency devices | Many partitions; many requests for wide spans |
| Hourly + shard | Splits load of an extremely hot device | Must query multiple shards and merge in order |

For example, 3,600 events/hour with a 500-byte average payload equals **roughly 1.8 MB of payload/hour** before metadata, index, compression, and replica overhead; 30-day SSTable disk footprint cannot be predicted accurately from this simple product alone. Measure actual partition sizes using `nodetool tablehistograms`, per-table metrics, and the p95/p99 distribution of per-device write rates.

### 6.2. Queries Spanning Two Days Are Not One Contiguous Clustering Slice

For example, "from 23:50 on day 20 to 00:10 on day 21" with partition key `(device_id, event_day)`:

~~~text
Day 20 partition: event_time >= 23:50 and < 24:00
Day 21 partition: event_time >= 00:00 and < 00:10
Application merges the two sets already sorted by event_time
~~~

Each partition maintains its own order. Cassandra **does not provide a global ORDER BY** across those two partitions; simply appending `ORDER BY event_time DESC` to a multi-partition query does not guarantee the desired global sort.

## 7. CQL Lab: Creating Tables, Loading Data, and Verifying Ranges/Ordering

### 7.1. Setup

Practice on Cassandra 4.x–5.x in a **lab cluster** with `cqlsh` and `nodetool`. The example below assumes an actual datacenter named `dc1` with at least three nodes; verify with `nodetool status` and adjust RF/DC accordingly before running:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_query_tuning
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_query_tuning.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Note:** `IF NOT EXISTS` does not alter the schema of an existing keyspace or table; run `DESCRIBE TABLE lab_query_tuning.events_by_device_day` to verify the actual keys and clustering order. Do not configure RF higher than available nodes and draw latency or availability conclusions from the lab.

### 7.2. Inserting Data Including a Duplicate-Timestamp Pair

~~~sql
INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T07:45:00Z',
    49dc0401-2d82-48ae-96cb-c397150639ce,
    'INFO',
    'boot'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    080d0004-4dd6-49e4-8759-28e8365c4101,
    'WARN',
    'voltage-low'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    ed2c3c12-e91a-47de-8c30-c58353014a2b,
    'ERROR',
    'sensor-timeout'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:42:00Z',
    6db5b4cc-e3d7-4ab0-a5f4-2350d4d6b24c,
    'INFO',
    'recovered'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T09:15:00Z',
    38444992-e82b-4adb-97a6-7546cc5fb03c,
    'INFO',
    'periodic-sample'
);
~~~

All five rows belong to the same partition. The two events at `08:05` have distinct `event_id` values so they **do not overwrite each other**.

### 7.3. Testing Three SELECT Patterns

**A — Latest in the day:**

~~~sql
SELECT event_time, event_id, event_type, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
LIMIT 3;
~~~

With the default `DESC, ASC` order, expected output includes `09:15`, `08:42`, and one of the two `08:05` events in ascending `event_id` order. To include both same-timestamp events, use `LIMIT 4`. This demonstrates the **tie-breaker** and the exact semantics of `LIMIT`.

**B — Range [08:00, 09:00):**

~~~sql
SELECT event_time, event_id, event_type, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
ORDER BY event_time DESC, event_id ASC;
~~~

Expected output: `08:42` followed by **two rows** at `08:05`; `07:45` and `09:15` are excluded. Same partition and predicate structure, where changing only the bounds alters the scanned slice.

**C — Reverse read direction:**

~~~sql
SELECT event_time, event_id, event_type
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
ORDER BY event_time ASC, event_id DESC;
~~~

Results run chronologically from `07:45` to `09:15`; for rows sharing a timestamp, `event_id` is ordered descending. Verify by checking both timestamp order and `event_id` tie-breaking, not just row count.

### 7.4. Testing "Invalid or Costly Queries"

Read these two queries as **analytical cases**, not production workloads:

~~~sql
-- Missing event_day from the composite partition key:
SELECT event_time, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_time >= '2026-11-21T08:00:00Z';

-- event_type is a regular column, not a clustering prefix:
SELECT event_time, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_type = 'ERROR';
~~~

Cassandra normally rejects these without an appropriate index or filtering allowance. Even if `ALLOW FILTERING` lets you run them in a lab, the risk of scanning extensive data remains. Sound design proposals should stem from actual queries: supply the full partition key, build a table keyed by type/day, or evaluate indexes when workload-appropriate and measured.

### 7.5. Tracing and Metrics to Confirm Gains

In `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
TRACING ON
~~~

Run each valid query A/B/C, record its trace, then turn tracing off:

~~~text
TRACING OFF
~~~

`CONSISTENCY` and `TRACING` are **cqlsh commands**, not CQL DDL. `LOCAL_QUORUM` is only valid when the lab keyspace/driver/DC is configured properly; keep CL consistent across variants when measuring.

On a Cassandra node:

~~~bash
nodetool tablehistograms lab_query_tuning events_by_device_day
nodetool tablestats lab_query_tuning.events_by_device_day
nodetool tpstats
~~~

| Observation source | Metrics/details to record | What you can infer |
|---|---|---|
| Tracing | Participating replicas, read steps, and per-phase timings | Actual execution path of the request |
| Java client | End-to-end p50/p95/p99, timeouts, row and page counts | User experience under load |
| `tablehistograms` | Partition sizes, SSTables per read, local latencies | Oversized partitions or read amplification |
| `tablestats` | SSTables, read/write latency, table statistics | Storage footprint and read path cost |
| `tpstats` | Pending/blocked/completed per thread pool stage | Queueing or node-level bottlenecks |

You cannot prove a design is "faster" because two queries returned quickly on five rows. Load multiple partitions with representative sizes and distributions, compare at identical RF/CL and rows read, and measure p95/p99 under production-like load. Tracing adds overhead; sample individual requests rather than enabling it broadly during load tests.

## 8. Pagination: Preserving Order as Data Grows

### 8.1. LIMIT and Fetch Size Are Not the Same

In the Java Driver, `LIMIT 50` caps the **total rows returned by the CQL query**, whereas `page size = 20` guides how the driver fetches **each page** while iterating. One query can return 50 rows across multiple pages; timing only until the first page arrives underestimates actual latency.

On large partitions, avoid SQL-style `OFFSET 100000` pagination: Cassandra does not support efficient random-offset jumping across pages like a B-tree index. Typically, use the driver's **paging state** (with matching query/parameter invariants) or a **clustering-key cursor** strategy designed and tested for the application.

### 8.2. Java Driver 4.x: Partition/Range Query with Paging

The example assumes an initialized `CqlSession session` whose local datacenter matches the keyspace:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, event_type, payload " +
    "FROM lab_query_tuning.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? " +
    "ORDER BY event_time DESC, event_id ASC LIMIT ?");

UUID deviceId =
    UUID.fromString("0f94e3b9-0b36-4930-91f2-606b44b5231b");
BoundStatement statement = prepared.bind(
        deviceId,
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T08:00:00Z"),
        Instant.parse("2026-11-21T09:00:00Z"),
        50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(20);

ResultSet result = session.execute(statement);
int count = 0;
for (Row row : result) {
    UUID id = row.getUuid("event_id");
    Instant eventTime = row.getInstant("event_time");
    // Process id/eventTime and fields actually required by business logic.
    count++;
}
// If multiple pages exist, iterating ResultSet fetches subsequent pages as needed.
~~~

Measure **total duration and actual pages consumed**, not just the `execute()` call returning the first page. Paging state is a cursor tied to a specific query, bind values, and driver/protocol; do not reuse it across arbitrary queries. When rows are inserted or deleted between page fetches, results can shift; standard Cassandra paging is **not a transactional snapshot**.

### 8.3. Avoiding Page Drift When New Data Arrives

In a "newest-first" feed, new events keep arriving at the head of the partition while a user scrolls. Options include:

- Establishing a **high-watermark** on the first request—for example, pinning `event_time < cutoff` for subsequent pages (with clear boundary and tie-breaker rules).
- Passing the paging state returned by the initial query while keeping filters/cutoffs constant, accepting that concurrent mutations can still affect results.
- Where strict accuracy is needed, building a cursor over the full clustering key that handles equal timestamps via `event_id` (verifying CQL/tuple comparison syntax for your version) rather than `WHERE event_time < last_time` alone, which can skip events sharing a timestamp.

Avoid simulating `OFFSET` by fetching all preceding rows and discarding them client-side on large datasets: network, memory, and time costs grow linearly with page depth.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| Keeping `event_time` as a regular column and expecting `ORDER BY event_time` | CQL does not support arbitrary sorting on regular columns | Put time in the clustering key of the query-serving table |
| Choosing `(event_type, event_time)` for a screen listing **all types** newest-first | Rows are grouped by type first, not globally by time within the partition | Use a table led by time or a dedicated read model |
| Omitting part of a composite partition key | Cannot locate a single partition via standard queries | Supply the full partition key or design a new table |
| Ranging on the second clustering column without constraining the first | No contiguous scan slice in the current key order | Provide an equality prefix or reorder clustering columns |
| Using only `event_time` as clustering key when timestamps can collide | Same-timestamp events collapse into one logical row | Add `event_id` for uniqueness and tie-breaking |
| Dumping entire history into a single partition | Hot partitions, heavy reads/compactions/tombstones | Use time buckets or purposeful sharding |
| Assuming `ORDER BY` sorts across the whole cluster | Incorrect when spanning multiple partitions | Query per partition and merge, or build a read model |
| Assuming `LIMIT 50` always means the 50 newest records | Returns rows in whatever clustering order exists | Choose the right clustering order and lock down semantics |
| Using `ALLOW FILTERING` to "fix" queries | May scan huge numbers of rows before returning results | Model tables per query; benchmark indexes if needed |
| Putting a frequently changing `updated_at` in the primary key | Every update must move the row; increases tombstones/dual-writes | Separate an identity table from a read model if needed |
| Measuring only the initial request time | Hides pagination, tail latency, and disk cost | Measure end-to-end across multiple requests and partitions |

## 10. Design Exercises and Self-Check

### Exercise 1 — Choosing a Clustering Key

A table must serve:

> "List orders for customer C in month M where `status = 'PAID'`, sorted by newest `created_at` and filtered from date A to B."

Choose the partition key and clustering key; describe what happens when a new screen asks to list **all statuses** chronologically.

**Hint:** for the `PAID`-only query, you can partition by `(customer_id, month_bucket)` and cluster by `(status, created_at, order_id)`, putting `status = 'PAID'` before the `created_at` range. However, to view **all statuses** by time, this table does not provide partition-wide time order; consider a second table clustered by `(created_at, order_id)`.

### Exercise 2 — Explaining a Missing-Prefix Condition

Given:

~~~sql
PRIMARY KEY ((tenant_id, event_day), event_type, event_time, event_id)
~~~

What is wrong with `WHERE tenant_id = ? AND event_day = ? AND event_time >= ?`?

**Answer:** it lacks an equality constraint on `event_type`, which precedes `event_time`. Inside the partition, rows are grouped by type before timestamp. Add `event_type = ?` or use a table with time as the leading clustering column for all-type scans.

### Exercise 3 — Reverse Order

If `CLUSTERING ORDER BY (event_time DESC, event_id ASC)`, what is the valid reverse order along the same clustering sequence? Can `ORDER BY event_id DESC` alone sort the entire partition by `event_id`?

**Answer:** the valid reverse order is `(event_time ASC, event_id DESC)`. `event_id` is the second clustering column; it cannot act as an independent partition-wide sort key while `event_time` precedes it.

### Exercise 4 — Bucketing and Global Top N

A device emits 100,000 events/day. A screen needs "the 20 latest events from the past seven days" with low p99. Should you design daily or weekly buckets? Which tests help decide?

**Hint:** evaluate daily buckets as a candidate, reading the newest day first and stepping backward only until 20 rows are gathered. Compare against weekly buckets on partition size, request count, fan-out, p99, write hotspots, and compaction. There is no single right answer without measuring actual load distribution and event rates.

### Exercise 5 — Reading Lab Results

Given the five sample rows at 07:45, 08:05 (two events), 08:42, and 09:15, how many rows does range `[08:00, 09:00)` return? Which timestamps does `LIMIT 3` in the default order return?

**Answer:** the range query returns **three rows**: 08:42 and both 08:05 rows. `LIMIT 3` returns 09:15, 08:42, and one 08:05 row (by `event_id ASC`).

### Completion Checklist

- [ ] Distinguish composite partition keys from clustering columns.
- [ ] Explain equality-prefix-then-range ordering and spot queries missing a prefix.
- [ ] Pick `CLUSTERING ORDER BY` and tie-breakers matching newest/oldest requirements.
- [ ] Avoid confusing intra-partition `ORDER BY` with global cross-partition sorting.
- [ ] Size buckets small enough for real traffic/partition limits while bounding multi-day fan-out.
- [ ] Run the CQL lab and verify row counts and order, including duplicate timestamps.
- [ ] Distinguish `LIMIT`, fetch size, paging state, and cursors.
- [ ] Use tracing, `nodetool`, and Java latency measurements to compare designs under realistic load.

## 11. References

1. Apache Cassandra Documentation — [CQL Data Definition: PRIMARY KEY and CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
2. Apache Cassandra Documentation — [CQL Data Manipulation: SELECT, WHERE, ORDER BY, and LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
3. Apache Cassandra Documentation — [Storage Engine and SSTable Ordering](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html).
4. Apache Cassandra Documentation — [cqlsh: Tracing and Consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html).
5. Apache Cassandra Documentation — [Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).
