# Reducing Large Collections, Large Partitions, and Tombstone Ratios

> **Chapter:** Query Tuning  
> **Scope:** Apache Cassandra, a distributed *wide-column* database, focusing on query-driven table design and reducing *read amplification*. Hands-on examples include CQL, `nodetool`, and Cassandra Java Driver 4.x.
>
> **Learning Objectives:** Recognize three causes of slow queries—**oversized collections**, **wide partitions**, and **heavy tombstone scans**—then redesign partition/clustering keys, TTLs, update/delete patterns, and read paths. Distinguish data that "no longer appears" from data that has been physically reclaimed.

## 1. Scenario: `LIMIT 20` Yet Still Slow

An API reads a customer's 20 latest events:

```cql
SELECT event_time, event_id, payload
FROM lab.customer_events_unbounded
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
LIMIT 20;
```

The query provides the full partition key and returns very few rows, yet p99 climbs into hundreds of milliseconds. Inside the table:

- A customer can accumulate years of events inside **one single partition**.
- Each event holds a `set<text>` with thousands of tags, an ever-growing `map<text,text>`, and a `list<text>` recording action history.
- The system uses short TTLs on certain cells, frequently deletes older rows, and updates collections repeatedly.
- SSTables hold live data interleaved with tombstones; compaction either lags behind or cannot yet purge them.

**`LIMIT 20` caps only output row count**; it does not promise Cassandra only inspects 20 physical rows or cells. Replicas may consult many SSTables, skip thousands of deleted/TTL-expired entries, or traverse a huge partition before assembling enough live rows.

Address this across three layers:

1. **Change the data model** so collections and partitions have bounded growth.
2. **Reduce unnecessary tombstone creation** and avoid scanning dead data.
3. **Measure before/after** using client latency, tombstones scanned, partition sizes, SSTable counts, and compaction/repair load.

Cassandra tuning typically starts from the **business query path**, not by cranking up heap or timeouts.

## 2. Understanding the Three Distinct Problems

| Issue | Growth unit | Common symptoms | Preferred optimization direction |
| --- | --- | --- | --- |
| **Large collection** | Element count or byte size inside a collection column | Heavy collection mutations/reads/updates; deletes/replacements can emit tombstones | Use collections only when small and bounded; move unbounded items into a query-driven table |
| **Large partition** | Rows/cells and total bytes under one partition key | Reads touch many SSTables/cells; hotspots; slow compaction/streaming/repair | Bucket by time/group/shard and query the exact partition |
| **Heavy tombstones** | Cell, row, range, or partition deletion markers inspected | Scanning dead data to find live rows; p99/timeouts climb | Reduce churn/deletes and mixed TTLs; align retention, bucketing, and compaction |

These three issues compound each other: an unbounded partition holds huge collections; frequent collection replacements generate tombstones; new reads must reconcile multiple SSTables and dead entries.

### There Is No Universal "Magic Threshold" for Every Cluster

You cannot declare a 100-element collection safe and 101 elements dangerous, nor is there one ideal partition size for all workloads. Consider:

- Average and **upper-percentile** element/row sizes.
- Whether reads pull the whole collection or just a slice.
- Update/delete rates, TTLs, and hot/cold key skew.
- SSTable count, I/O capacity, RF, network, and latency SLOs.
- Whether queries hit one partition or fan out per request.

The goal is **bounded growth and predictable query cost** over time.

## 3. Collections in Cassandra: Suitable When Small and Bounded

CQL supports `list`, `set`, and `map` to represent value groups. They work well when the element set is small and tightly bound in lifecycle and access pattern to a single row.

Example small metadata table with bounded flags and attributes:

```cql
CREATE TABLE IF NOT EXISTS lab.event_small_metadata (
    event_id uuid PRIMARY KEY,
    flags set<text>,
    attributes map<text, text>
);
```

Element-level updates on **non-frozen collections** where syntax and types permit:

```cql
UPDATE lab.event_small_metadata
SET flags = flags + {'important'},
    attributes['source'] = 'mobile'
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

For small, fixed-cardinality structures, a collection is simpler than an auxiliary table. Once elements grow alongside customer tenure, however, the collection turns into an unmanageable bottleneck.

### Comparing the Three Types

| Type | Characteristics | When to consider | Risks if unbounded |
| --- | --- | --- | --- |
| `set<text>` | Unique elements, no business ordering guarantee | **Very few, bounded** flags, roles, or tags | Huge sets, heavy deletes/replacements, and full-collection reads |
| `map<text,text>` | Key → value; individual entries updatable when non-frozen | Flexible attributes with controlled key count | Map turns into an unbounded KV store reading thousands of entries |
| `list<text>` | Ordered list with collection-representation-dependent updates | Small lists where order truly matters | Infinite append history, element updates/deletes, complex concurrency conflicts |

**Never use a `list` to store an event history inside one row.** If the business needs recent-item queries, pagination, time filtering, or millions of events, a table with clustering keys fits far better.

## 4. Non-Frozen vs. Frozen: Different Update Mechanics, Not Size Magic

Cassandra supports **non-frozen** and **frozen** collections in allowed type/syntax contexts. Exact implementation details and limits vary by version.

### Non-Frozen Collections

Conceptually, collection elements are stored as individual cells with metadata, enabling partial updates.

```cql
CREATE TABLE lab.event_metadata_mutable (
    event_id uuid PRIMARY KEY,
    attributes map<text, text>
);
```

Updating a single key:

```cql
UPDATE lab.event_metadata_mutable
SET attributes['priority'] = 'high'
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

This is usually cleaner than rewriting the **entire map** to change one key. Still, unbounded element growth drives read cost plus stale versions/tombstones on overwrites and deletes.

### Frozen Collections

```cql
CREATE TABLE lab.event_metadata_frozen (
    event_id uuid PRIMARY KEY,
    attributes frozen<map<text, text>>
);
```

A frozen collection is treated as a single cell-level value: individual elements cannot be updated like non-frozen collections; changing it requires rewriting the entire collection. This suits small, stable values replaced as a unit.

**Do not use `frozen` to "fix" a giant collection.** A frozen massive collection remains a huge value to serialize, transmit, decode, and rewrite on every change—it only changes storage/update semantics.

### When Do Collections Emit Tombstones?

- Deleting an element from a `set`/`map` or deleting the entire collection.
- Replacing a whole collection and shadowing prior elements/versions where applicable.
- Writing `null` to a column per CQL/driver deletion semantics.
- Cell/element TTL expiration or updates rendering older elements obsolete.

**Not every element addition emits an explicit tombstone.** Actual tombstone counts depend on write operations, timestamps, collection types, and Cassandra version; verify with metrics/tracing when uncertain.

## 5. When Should a Collection Become Its Own Table?

Extract a collection into a table if one or more of these hold:

1. Element count **can grow unboundedly** with user activity.
2. You need to **paginate**, slice by time, or read a subset instead of the whole collection.
3. Elements have distinct lifecycles, TTLs, or access controls.
4. Elements are updated or deleted individually and frequently.
5. The collection lives inside an already wide row or partition.
6. You need to query by element: "find events with tag X" or "list newest attributes."

Example replacing a large `set<text> tags` with a table:

```cql
CREATE TABLE lab.event_tags_by_event (
    event_id uuid,
    tag text,
    PRIMARY KEY ((event_id), tag)
);
```

Adding a tag:

```cql
INSERT INTO lab.event_tags_by_event (event_id, tag)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'important'
);
```

Reading an event's tags:

```cql
SELECT tag
FROM lab.event_tags_by_event
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

This works well when tags **per event stay bounded by business rules**. If a single event could acquire millions of tags, partitioning by `event_id` creates a large partition anyway. Splitting into a table **does not automatically guarantee small partitions**; you must still choose partition/buckets based on cardinality and queries.

### What If the Query Is "Find Events by Tag"?

`event_tags_by_event` only serves event → tags lookups. For tag → events, add a query-specific projection:

```cql
CREATE TABLE lab.events_by_tag_day (
    tag text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    customer_id uuid,
    PRIMARY KEY ((tag, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Query:

```cql
SELECT event_time, event_id, customer_id
FROM lab.events_by_tag_day
WHERE tag = 'important' AND event_day = '2026-11-21'
LIMIT 50;
```

This lets Cassandra look up by partition key, while the app maintains both representations. Writing additional projections **does not automatically provide multi-table/multi-partition atomic transactions**; design for consistency, idempotent retries, reconciliation, and aligned retention.

If one ultra-popular tag receives millions of events/day, split further by hour/shard or rethink the query strategy. Extracting a collection does not solve **load distribution** on its own.

## 6. Large Partitions: Why Does Cassandra Struggle with Them?

A partition is the set of rows sharing the **same partition key**, ordered inside by clustering columns. One partition's data can span multiple immutable SSTables, versions, and tombstones.

Consider an initial design:

```cql
CREATE TABLE lab.customer_events_unbounded (
    customer_id uuid,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    tags set<text>,
    attributes map<text, text>,
    notes list<text>,
    PRIMARY KEY ((customer_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

The partition key is `customer_id` alone. If one customer generates millions of events/year, **every event for that customer** lands in the exact same partition forever.

This drives up:

- Partition data size and read metadata overhead.
- Clustering range/scan times when reading history.
- Compaction cost from merging multiple SSTables/versions of the same partition.
- Load skew: hyper-active customers create *hot partitions*.
- Streaming, repair, snapshot, and recovery overhead on oversized partitions.
- Tombstone pressure when old records are purged row-by-row or via TTL.

Note that **a large partition does not mean all its data sits in one SSTable**. One partition can be scattered across many SSTables due to flushes, while one SSTable holds many partitions.

### Averages Easily Hide the Tail

Suppose you have 1 million customers:

- 999,000 customers have a few hundred events each.
- 1,000 enterprise customers have tens of millions of events each.

The **average** partition size may look unremarkable while those hot/large partitions drive most cluster I/O and p99. Measure **partition-size distributions**, histograms, and outlier partitions—not total disk divided by partition count.

## 7. Splitting Partitions with Time Buckets

When queries ask for "events in a day/hour" or "20 latest events," add a bucket to the partition key:

```cql
CREATE TABLE lab.customer_events_by_day (
    customer_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((customer_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Now each customer gets **one partition per active day** instead of one partition for all history. Query:

```cql
SELECT event_time, event_id, event_type, payload
FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
LIMIT 20;
```

### Why Does Bucketing Work?

- Bounds rows/bytes per **partition to a time window** when ingest rates are predictable.
- Lets the app narrow read scope instead of traversing a customer's entire history.
- Reduces oversized-partition pain during flush, compaction, repair, and streaming.
- Supports retention pruning when combined with uniform TTLs/time windows and immutable historical data.

In return:

- Multi-day queries must read **multiple partitions**, coordinated and merged by the application.
- Overly tiny windows create too many partitions and round-trips.
- Daily buckets can still grow too large for extreme hot customers.
- Writers and readers must agree on deriving `event_day` from `event_time`, timezone (typically UTC), and late-arriving events.

**Cassandra does not stitch partitions into one timeline** just because they share `customer_id`. That coordination belongs to the read-path design.

### Day, Hour, or Sharding?

Rough sizing example:

```text
Large customer: 200 events/second
Each event:     ~1 KiB logical data

By day:
  200 × 86,400 ≈ 17,280,000 events/day
  ≈ 16.5 GiB/day (hypothetical payload only)

By hour:
  200 × 3,600 = 720,000 events/hour
  ≈ 703 MiB/hour

By hour + 16 evenly distributed shards:
  ≈ 44 MiB/partition in one hour
```

These are **logical data estimates**, not exact SSTable disk-byte forecasts. Compression, metadata, wide columns, replicas, compaction, and shard distribution change physical sizes. Nor are these numbers **official Cassandra thresholds**.

If hourly partitions are still too big, `(customer_id, event_hour, shard)` fits, though "20 newest events" must read/merge shards and sort by `event_time`. Adding shards trades **read complexity** for **better load distribution and smaller partitions**.

### Sharded Design Pattern (When Truly Needed)

```cql
CREATE TABLE lab.customer_events_by_hour_shard (
    customer_id uuid,
    event_hour timestamp,
    shard smallint,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((customer_id, event_hour, shard), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

The app can compute `shard` deterministically via a hash of `event_id` modulo shard count, keeping the algorithm and shard count identical across all writers and readers. **Never change modulo 16 to 32 mid-stream** without versioning/migration, or readers will lose where historical events live.

To read recent events, query the shards for the target hour and merge chronologically. Bound both fan-out and rows fetched per shard.

## 8. Measure Partition Size Before Changing Schema

A disciplined approach measures all three:

1. **Partition size distribution:** median, p95/p99, max; watch for hotspot partitions.
2. **Row/cell count per partition:** a partition of small rows with huge row counts can still be slow.
3. **Query cost:** read latency, tombstones scanned, SSTables read, and actual rows returned.

On an authorized lab node:

```bash
nodetool tablestats lab.customer_events_unbounded
nodetool tablehistograms lab.customer_events_unbounded
```

Depending on Cassandra version, `tablestats` reports table-level metrics such as SSTable count, disk space, memtables, read/write latencies, tombstones scanned, and partition stats; `tablehistograms` reports histograms for partition sizes, cell counts, and latencies.

Do not treat one version's column names or output layout as an immutable contract across releases. For deep file-level inspection, `sstablemetadata` and related SSTable tools help **in labs or per runbooks**; never manually open, edit, or delete SSTables on a live serving node.

### Signals Table to Watch

| Signal | If rising, suspect | Cross-check |
| --- | --- | --- |
| Max/p99 partition size | Hot customers, unbucketed key | Key distribution, events/day |
| SSTable count / read amplification | Frequent flushes, compaction backlog | Pending compactions, disk I/O |
| Read p99 | Heavy read path or slow replica | GC, CPU, disk, coordinator, CL |
| Few rows returned, high tombstones scanned | Scanning dead data | TTL/delete patterns, tombstone age |
| Compaction backlog | Overlapping/stale data, resource contention | Disk headroom, flush rate, repair |
| Slow streaming/repair | Oversized partitions/ranges or overloaded nodes | Token ranges, disk/network throughput |

A table with many tiny partitions and a few massive outliers usually needs **partition-key optimization**, not necessarily a compaction strategy change.

## 9. Where Do Tombstones Come From?

In Cassandra, `DELETE` writes a **deletion marker (tombstone)** rather than seeking and erasing data inside immutable SSTables. Tombstones must shadow older versions across SSTables and peer replicas until it is safe to purge them.

Common sources:

| Source | Example | Why it matters for tuning |
| --- | --- | --- |
| Column delete | `DELETE payload FROM ...` | Writes a cell tombstone inside the partition |
| Row delete | `DELETE FROM ... WHERE full_primary_key = ...` | Row tombstone must be reconciled on reads |
| Clustering range delete | Deleting a time range via valid CQL | Range tombstones can affect wide slice scans |
| Partition delete | Deleting by partition key where allowed | Partition tombstone shadows all older rows in the partition |
| TTL expiration | `INSERT ... USING TTL 3600` | Logically expired cell; expiration metadata awaits GC |
| Writing `null` with delete semantics | App binds `null` instead of omitting column | Easily creates unintended tombstones |
| Collection update/delete | Replacing/removing map, set, list, or elements | Can emit element/collection tombstones |
| Repeated overwrites | Same cell updated with deletes interspersed | Increases reconciliation work until compacted |

**Do not equate every update with an explicit tombstone.** Value overwrites create shadowed older versions; deletes, TTLs, and certain collection operations directly involve tombstones. Nevertheless, both obsolete versions and tombstones add compaction work.

### Logical Reads vs. Physical Data

After `DELETE` or TTL expiration, `SELECT` may return no rows or cells. Yet older SSTables still retain data/metadata that must be reconciled; a tombstone cannot be discarded merely because a query stops seeing the row.

`gc_grace_seconds` is one condition governing tombstone age; compaction also checks whether older data could still reside in other SSTables. Cluster-wide, repair ensures replicas do not miss deletes before tombstones are purged, preventing *zombie* data resurrection.

## 10. How Should "Tombstone Ratio" Be Measured?

Cassandra has no single metric named **tombstone ratio** with a uniform definition across all versions, queries, and monitoring stacks. In tuning, keep these separate:

- **Tombstones scanned per query/read:** deletion markers inspected to serve a read.
- **Live cells/rows scanned:** live entries actually examined, where tools expose it.
- **Rows returned:** rows shipped to the client, **not equal to** live cells read.
- **SSTable tombstone/expired share:** dead data ratio on disk; can differ drastically from per-query tombstone scans.

When a tool reports both tombstones scanned and live cells scanned over the exact same scope and definition, you can compute a **reference ratio**:

```text
Tombstone ratio among scanned cells
= tombstone_scanned / (tombstone_scanned + live_cells_scanned)
```

For example (**hypothetical**), 4,000 tombstones and 100 live cells in one read give roughly 97.6%. However, if tooling only reports "20 rows returned," never plug 20 in as `live_cells_scanned` to claim a 99.5% ratio: one row holds multiple cells and scans can touch more rows than returned.

### Practical Metrics That Help

- `nodetool tablestats`: e.g., **average/max tombstones per slice (last five minutes)** or release equivalents.
- Read latency and tombstone-scanned histograms/JMX metrics where exported.
- CQL tracing on **sampled expensive queries** to inspect the read path.
- Compaction, SSTable, and expired/TTL stats where supported.
- Client p95/p99, timeouts, rows returned, and concurrency.

A query returning 20 rows while scanning tens of thousands of tombstones signals a need to inspect **query patterns and data modeling**. Conversely, large total tombstones on disk will not slow down queries whose partitions/slices never touch them.

### Warning and Failure Thresholds

Many Cassandra versions expose warning and failure thresholds for tombstone scans, such as `tombstone_warn_threshold` and `tombstone_failure_threshold`. Exact names, defaults, and behavior vary by version and distribution.

When warnings appear:

1. Identify the query, partition/range, and tombstones scanned.
2. Check TTLs, delete/collection patterns, and SSTable counts.
3. Inspect deadlines, consistency levels, slow replicas, and query p99.
4. Fix the query/retention design before touching thresholds.

**Raising thresholds does not remove tombstones.** It merely hides symptoms or allows heavier queries to starve peer requests of queues and disk I/O.

## 11. CQL Practice: How TTL and DELETE Create Dead Data

The following examples target an **existing `lab` keyspace in a learning environment**; never test deletes or TTL changes directly on production.

### Step A — Create a Day-Bucketed Table

```cql
CREATE TABLE IF NOT EXISTS lab.customer_events_by_day (
    customer_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((customer_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

### Step B — Write an Event with a Short TTL

```cql
INSERT INTO lab.customer_events_by_day
  (customer_id, event_day, event_time, event_id, event_type, payload)
VALUES
  (aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
   '2026-11-21',
   '2026-11-21T03:00:00Z',
   11111111-1111-4111-8111-111111111111,
   'detail',
   'expires after 1 day')
USING TTL 86400;
```

`event_day` and `event_time` are event columns; Cassandra calculates TTL from when the mutation is written, **not from the `event_time` column**. Once expired, the record disappears logically yet contributes dead data in SSTables until GC/compaction reclaims it.

### Step C — Write a Longer-Lived Row

```cql
INSERT INTO lab.customer_events_by_day
  (customer_id, event_day, event_time, event_id, event_type, payload)
VALUES
  (aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
   '2026-11-21',
   '2026-11-21T03:01:00Z',
   22222222-2222-4222-8222-222222222222,
   'audit',
   'retain for 30 days')
USING TTL 2592000;
```

Two rows in the same day partition carry different TTLs. They may land in the same SSTable, preventing whole-SSTable drops: after 1 day the first event expires, yet the second event remains live. Separating retention classes or aligning TTLs per table/window improves reclamation on matching workloads.

### Step D — Check Remaining TTL and Perform a Controlled Delete

```cql
SELECT event_time, event_id, payload, TTL(payload)
FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
LIMIT 20;
```

Then delete **one specific row** in the lab:

```cql
DELETE FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T03:00:00Z'
  AND event_id = 11111111-1111-4111-8111-111111111111;
```

Data disappearing from `SELECT` does not prove SSTables were reclaimed. Never force compaction or set `gc_grace_seconds` to 0 to "erase immediately"—doing so risks zombie data if any replica missed the delete.

## 12. Reducing Tombstones Through Retention Design

### Approach A — Avoid Bulk Row-by-Row Deletes When Possible

If millions of events arrive daily and a weekend job deletes old rows individually to keep 7 days, the cluster continuously accumulates row tombstones.

Where business rules allow, write events with `USING TTL` from the start. Note that **TTL is not tombstone-free**; it embeds expiration into the mutation and can streamline retention management.

Analyze whether TTLs are uniform, whether compaction can drop expired SSTables, and exactly when data must vanish from reads.

### Approach B — Separate Different TTL Cohorts

Avoid mixing 1-day and 90-day TTL data in the same storage layer when you can separate by query and retention. A `recent_events` table with 1-day TTL and an `audit_events` table with 90-day TTL give SSTables uniform lifecycles.

In exchange, if an API needs all events over a span, the app must read/merge across tables—a classic **query-driven data modeling trade-off**.

### Approach C — TWCS for Append-Only Time-Series Workloads

**TimeWindowCompactionStrategy (TWCS)** groups compactions into time windows, excelling for mostly append-only time-series data with uniform TTLs and minimal updates/deletes to older records.

Once all data in an SSTable expires past GC/safety requirements, Cassandra can drop **entire files** instead of rewriting live cells. However:

- **Never** assume TWCS eliminates every tombstone.
- Backfills, late writes, updates to old rows, and mixed TTLs break window assumptions.
- `gc_grace_seconds`, SSTable overlap, repairs, and replica state still govern safe reclamation.
- Compaction backlogs also keep dead data and tombstones around longer.

### Approach D — Consider Delete Granularity

If retention requires deleting "an entire month of one customer's data," deleting millions of rows individually generates massive tombstones. Design **retention-aligned buckets** so deletes align with partition/range boundaries. Still, a partition tombstone shadows vast history and must persist safely—it never waives repair or GC rules.

If uniform TTL expiration fits instead, test whether it cuts write/delete overhead and helps compaction. Always measure tombstones scanned on **actual queries**.

## 13. A Good Read Path Takes More Than `LIMIT`

Combine these optimizations together:

1. **Right partition key:** avoid unnecessary cross-token scans.
2. **Narrow clustering range:** read only the needed day/hour/event slice.
3. **Required column projection:** avoid `SELECT *` with large collections, blobs, or unused columns.
4. **Page size:** driver `fetch size/page size` bounds per-page delivery, without erasing tombstone scan cost.
5. **Bounded fan-out:** reading three daily partitions may be fine; reading thousands to aggregate needs a different model.
6. **Avoid unkeyed filters:** `ALLOW FILTERING` never substitutes for proper modeling; evaluate secondary indexes/SAI against Cassandra's constraints.
7. **Do not measure only p50:** large partitions, tombstones, and slow replicas show up in p95/p99.

Two-way query examples:

| Requirement | Sound design | Avoid |
| --- | --- | --- |
| 20 newest events for customer today | `(customer_id, event_day)` + clustering time DESC | One `customer_id` partition holding 5 years of history |
| Tags on one event (few, bounded) | Small `set` or `event_tags_by_event` | A set growing with account age |
| Find events by tag and day | `events_by_tag_day` or query projection | Scanning all events and filtering collections client-side |
| View last 7 days | Query at most 7 day buckets and merge boundedly | Full-table scan or huge `IN` list |
| Retain events 24h and audit 90d | Separate retention tables where feasible | Mixing both TTLs in every SSTable of one workload |

Sometimes a larger partition remains workable if an access pattern demands it and size stays bounded; the real hazard is **unbounded partition growth** forcing scans far wider than returned results.

## 14. Java Driver 4.x: Bucketed Reads with Result Limits

Java applications should construct explicit buckets, use prepared statements, set consistency levels, and bound results. Example reading events for **one day**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class CustomerEventReader {
    private final CqlSession session;
    private final PreparedStatement selectByDay;

    public CustomerEventReader(CqlSession session) {
        this.session = session;
        this.selectByDay = session.prepare(
            "SELECT event_time, event_id, event_type, payload " +
            "FROM lab.customer_events_by_day " +
            "WHERE customer_id = ? AND event_day = ? LIMIT ?"
        );
    }

    public List<UUID> recentEventIds(
            UUID customerId, LocalDate eventDay, int maxRows) {

        if (maxRows < 1 || maxRows > 100) {
            throw new IllegalArgumentException("maxRows must be between 1 and 100");
        }

        BoundStatement statement = selectByDay.bind(
                customerId, eventDay, maxRows)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(maxRows, 50))
            .setIdempotent(true);

        ResultSet result = session.execute(statement);
        List<UUID> ids = new ArrayList<>();

        for (Row row : result) {
            ids.add(row.getUuid("event_id"));
        }
        return ids;
    }
}
```

Assumes `CqlSession` is connected, `lab` holds the table above, and RF/DC support `LOCAL_QUORUM`. `LocalDate` represents the normalized business day bucket. Java Driver 4.x uses matching codecs for `date`/`timestamp`; never pass a `String` instead of `LocalDate` when prepared for `date`.

`setPageSize` bounds rows per page while `LIMIT` caps total query rows. **Neither guarantees low tombstone scans** if Cassandra must traverse extensive dead data to find live rows.

### What If You Need the 20 Newest Events Across 7 Days?

With day-bucketed tables, the app can read the newest days in descending order, capping at 20 rows/day and stopping once 20 rows are gathered. Ensure:

- Consistent derivation of `event_day` from `event_time` and timezone (e.g., UTC).
- Intra-partition ordering via the clustering key.
- Clean handling of empty days and late-arriving events.
- Bounded bucket count and overall API deadlines.
- When sharding is part of the partition key, query every shard and merge globally by `event_time`/`event_id`; never concatenate shards blindly.

The snippet above reads **one day** only and does not pretend to solve multi-day or multi-shard merging automatically.

## 15. Measuring Impact Under Identical Workload and Conditions

A valid experiment controls:

- Query shapes, partition keys, and hot/cold customer distributions.
- Realistic data volume, TTLs, and update/delete rates.
- RF, consistency level, datacenter, and coordinator routing.
- Concurrent read/write load, compaction, repair, and cache state.
- Duration long enough to capture p99 and background compaction.

### Before/After Metric Set

| Metric | Before (unbucketed, illustrative) | After (bucketed, illustrative) |
| --- | ---: | ---: |
| Max partition size | 1.8 GiB | 28 MiB |
| Tombstones scanned p95/query | 8,000 | 150 |
| Read p99 | 480 ms | 85 ms |
| SSTables read/query | High, volatile | Lower |
| Fan-out queries | One giant partition | Multiple buckets on cross-day reads |
| Extra writes | Minimal projections | Higher if adding tag/query tables |

These are **hypothetical numbers**, not universal Cassandra benchmark results. Measure write amplification, disk/CPU, cache misses, and app-side merge cost too—never cherry-pick a single improved p99 row.

### Pitfalls When Testing

- A brand-new table has tiny data so queries look fast; that proves nothing once populated.
- The second run hits warm OS page cache; compare under equivalent cache states.
- Testing only an average customer while skipping hot customers.
- Checking small returned row counts without measuring tombstones scanned.
- Forcing compaction in baseline but not treatment, or vice versa.
- Watching only successful latency while ignoring timeouts/error rates.
- Switching CL from `QUORUM` to `ONE` alongside a schema change and crediting bucketing for all gains.

## 16. Observation and Troubleshooting

Run observation commands in authorized environments:

```bash
nodetool tablestats lab.customer_events_by_day
nodetool tablehistograms lab.customer_events_by_day
nodetool compactionstats
nodetool tpstats
nodetool gcstats
```

To inspect the execution path of **one query**:

```cql
TRACING ON;

SELECT event_time, event_id, event_type, payload
FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Tracing adds overhead; use selectively in labs or via controlled sampling. A single trace never represents the entire p99 distribution; pair it with histograms, JMX, and OS metrics.

### Scenario A — Partition Size Dropped, Yet p99 Did Not Improve

**Check:** Does the query read more buckets than before? Is the driver fanning out too widely? Is a node/replica lagging from GC or I/O? Are queries still scanning many tombstones inside each bucket?

**Direction:** Align bucket granularity with access patterns, cap bucket count, confirm date derivation, and inspect caching/compaction.

### Scenario B — Collection Extracted, Yet Write Cost Spiked

**Check:** How many projection writes does one business mutation emit? Are retries duplicating writes? Are unused projections maintained? Does a hot tag create a hot partition?

**Direction:** Maintain projections only for active queries, enforce idempotency and reconciliation, and bucket/shard popular tags.

### Scenario C — High Tombstones Scanned Long After TTL Expired

**Check:** `gc_grace_seconds`, SSTable overlap, compaction strategy, repair history, snapshots, and mixed short/long TTLs. An expired tombstone past grace is not instantly purged.

**Direction:** Fix retention and query modeling first; evaluate compaction fit—never slash grace or delete SSTables manually.

### Scenario D — Small-LIMIT Query Triggers Tombstone Warnings

**Check:** Does the partition/range hold many expired rows, does the clustering filter scan history, or do collection updates emit tombstones? Inspect traces and table metrics.

**Direction:** Separate hot/cold data, align buckets and TTLs, and query only needed time ranges. Do not merely raise `tombstone_failure_threshold`.

### Scenario E — One Customer Slows the Entire Cluster

**Check:** Token hotspots, that customer's read/write rate, partition size distribution, owning replicas, compaction, and thread queues.

**Direction:** If daily buckets are insufficient, add hourly/shard buckets with a planned merge path; rate-limit requests and review capacity. Adding nodes **does not split a single hot partition** across tokens if its partition key stays unchanged.

## 17. Optimization Design Checklist

Before deploying a new Cassandra table, answer:

| Question | Required evidence |
| --- | --- |
| Which query is the primary read path? | `WHERE`, `ORDER BY`, `LIMIT`, time window, and request rate |
| Does the partition key have bounded growth? | Events/sec, bytes/row, day/hour/shard bucket, p99 skew |
| Are collection element counts bounded? | Max cardinality, byte size, and update pattern |
| How do TTLs/deletes generate dead data? | Mutation rate, retention groups, `gc_grace_seconds`, and repair |
| Do we need element → event lookups? | Dedicated table/projection and maintenance cost |
| Must queries scan multiple buckets? | Bounded fan-out, merge logic, paging, latency budget |
| Is historical data updated or backfilled? | TWCS impact, late events, consistency |
| Are tombstones scanned measured? | Per-query metrics/tracing, p95/p99, and histograms |
| Are multi-table write failures handled? | Idempotency, retries, reconciliation, source of truth |
| Were hot keys and realistic data volumes tested? | Real benchmark, replica load, GC/I/O/compaction |

Do not roll out a new schema solely because "large collections are bad": measure **growth rate, query shape, write cost, and business impact**.

## 18. Common Misconceptions

**"`LIMIT 20` means Cassandra only inspects 20 rows."** False. SSTable and tombstone scans can be vastly larger.

**"Collections are always bad."** False. Small, well-bounded collections accessed cleanly as a whole or per element remain practical.

**"Switching to `frozen<map>` fixes any large collection."** False. Data stays large and usually requires rewriting the entire collection on edits.

**"Extracting a collection into its own table prevents large partitions."** False. If the new table's partition key still gathers millions of elements, the same problem persists.

**"Adding a clustering key makes partitions smaller."** False. Clustering keys sort rows **inside a partition**; only the partition key controls token distribution.

**"Adding shards is always better."** False. Sharding spreads writes yet complicates fan-out reads and merging, potentially raising request counts.

**"TTL removes data from SSTables the instant it expires."** False. Data expires logically first; physical reclamation awaits compaction/GC.

**"Every `UPDATE` creates a tombstone just like `DELETE`."** False. Distinguish overwritten versions from deletion markers; collections and TTLs have specific mechanics.

**"Raising tombstone thresholds optimizes the query."** False. It does not reduce read amplification.

**"Tombstones scanned / rows returned is always the true tombstone ratio."** False. Rows returned does not equal live cells scanned.

**"Running repair automatically erases tombstones."** False. Repair synchronizes replicas; compaction/GC reclaims SSTable data once safety conditions hold.

**"Lower `gc_grace_seconds` as much as possible to reclaim disk."** False. Replicas that missed deletes can resurrect zombie data.

**"Adding more nodes automatically splits a hot partition."** False. A partition's token comes from its partition key; you must change bucketing or sharding to split load.

## 19. Questions and Exercises

1. Why can `SELECT ... LIMIT 20` scan thousands of tombstones even when returning only 20 rows?
2. A customer has 20 million events in one partition. Does adding clustering column `event_type` shrink the partition? How should the partition key change?
3. Give one scenario where a small `map<text,text>` makes sense and one where it should become a separate table.
4. Compare updating one entry of a non-frozen `map` vs. replacing a `frozen<map>`.
5. An event has 5,000 tags and the app needs tag pagination. Does `event_tags_by_event` fit? What if tag count reaches millions?
6. At 200 events/sec and ~1 KiB/event, compute daily bytes and explain why daily buckets are insufficient if targeting small partitions.
7. If sharding across 16 shards per hour, what must the app do to return the 20 globally newest events?
8. A table mixes 1-day and 30-day TTL writes. Why can't SSTables be dropped whole after two days?
9. Why doesn't an old event timestamp mean its Cassandra TTL counts from that timestamp?
10. Explain how `gc_grace_seconds` and repair relate to zombie-data risk.
11. Which tools help analyze partition sizes, tombstones scanned, and compaction? Why isn't one `nodetool` snapshot enough?
12. You observe 4,000 tombstones and 100 live cells scanned in the same measurement. What is the reference ratio? If you only know 20 rows were returned, can you compute the same ratio?
13. Daily bucketing is in place, yet one customer still causes a hotspot; propose two design options with trade-offs.
14. If p99 drops from 400 ms to 80 ms after a schema change while write throughput drops 40%, is it a success? What else must be measured?
15. Why doesn't Java Driver `setPageSize(50)` solve a query scanning excessive tombstones?
16. When splitting one table into two query-driven tables, why are idempotency and reconciliation required?

## 20. Decision Summary

```text
Slow Cassandra query / timeout / tombstone warning
                    |
                    v
      Identify query, partition key, CL, replicas
                    |
           +--------+----------+
           |                   |
    Large collection?     Oversized partition?
           |                   |
    Unbounded growth?     Bucket / time key?
           |                   |
    Move to query-driven  Split day/hour/shard
    table when needed     and bound fan-out
           |                   |
           +--------+----------+
                    |
              Many tombstones?
                    |
        Inspect DELETE, TTL, nulls,
        collection updates, stale data
                    |
        Tune retention + query range
        + matching compaction + safe repair
                    |
                    v
        Measure p95/p99 + tombstones scanned
        + partition size + write/disk cost
```

**Takeaway:** Keep collections **small and bounded**, design partition keys to keep **rows/bytes within predictable limits**, and manage tombstones across **data modeling, TTL/delete patterns, and compaction/repair**. To cut p99, optimize the cells and SSTables actually scanned—**not merely returned row counts**. Always balance lower read amplification against fan-out, write amplification, and Java application complexity for maintaining auxiliary tables.
