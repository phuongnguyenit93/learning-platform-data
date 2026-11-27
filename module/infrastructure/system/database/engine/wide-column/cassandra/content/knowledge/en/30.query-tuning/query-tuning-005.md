# Reducing Projections, Result Size, and Network Round-Trips

## Lesson Objectives

When tuning Apache Cassandra queries, many teams only look at whether the `WHERE` clause uses a **partition key**. That is necessary, but insufficient: a query that targets the exact right partition can still be slow if it returns too many **columns**, too many **rows**, transfers many **result pages**, or gets called repeatedly by the Java application in an **N+1 query** loop.

In the **Query Tuning** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson focuses on three related—yet distinct—levers:

1. **Reducing projection:** `SELECT` only the columns actually needed by the screen or API.
2. **Reducing result size:** bound clustering ranges, row counts, individual value sizes, and pages read.
3. **Reducing network round-trips:** avoid issuing sequential CQL statements when a bounded read path or query-specific table can satisfy the request; manage paging, concurrency, and round-trips in the Java Driver.

After this lesson, you will be able to:

- Distinguish the volume of data **Cassandra must process**, the volume **the server sends to the client**, and the number of **network requests/responses**.
- Write CQL selecting only needed columns with full partition keys, clustering ranges, and sensible `LIMIT`s.
- Explain why `SELECT *`, large JSON/blobs, overly small pages, or per-row detail fetching inflate p95/p99 latency.
- Design two complementary table layouts for **compact lists** and **on-demand details**.
- Use **prepared statements, page size, asynchronous paging**, and total row caps with Cassandra Java Driver 4.x.
- Build controlled experiments comparing bytes, page counts, total round-trips, CPU/GC, duration, and application latency.
- Connect query tuning to RF, consistency levels, replication, compaction, tombstones, and multi-datacenter operations.

## 1. A Query Can Incur Cost at Three Layers

Suppose an API displays a customer's **20 latest orders**. Each order carries status, amount, and a receipt blob of several hundred KiB. With `SELECT *`, the API fetches every blob only to discard it when serializing the list JSON.

~~~mermaid
flowchart LR
    A["HTTP GET /orders"] --> B["Java service"]
    B --> C["Cassandra coordinator"]
    C --> D["Replica: read partition / SSTables"]
    D --> C
    C -->|"CQL response: selected columns + rows"| B
    B -->|"JSON to client"| A
~~~

Distinguish clearly:

| Layer | Cost source | Primary optimization |
| --- | --- | --- |
| **Replica / storage** | Locating partitions, reading memtables/SSTables, decoding, tombstones, reconciliation | Pick the right partition key/clustering range; avoid wide scans and oversized partitions |
| **Cassandra protocol / network** | Serializing returned values, coordinator ↔ client transfer (possibly over WAN) | Narrow column projection, bound rows and pages, colocate clients with local DC |
| **Java / HTTP application** | Decoding `Row`s, memory allocation, building DTO/JSON, issuing multiple CQL calls | Trim DTOs, lazy-load details, standardize paging, eliminate N+1, enforce backpressure |

**Narrowing projection typically shrinks response size and decoding work**, especially when dropping large text/blob columns. However, Cassandra is **not** a columnar OLAP engine, so physical SSTable disk reads do not shrink linearly with returned column count. Cutting a `SELECT` from 10 columns to 4 **does not guarantee** a 60% drop in disk I/O.

Similarly, reducing **client-side CQL calls** does not mean coordinator-to-replica messages equal client CQL calls. One `LOCAL_QUORUM` read can trigger data/digest requests and read repair; CL, RF, and speculative execution further determine cluster-internal traffic.

## 2. Projection: SELECT Exactly What the API Needs

### 2.1. Sample Schema: One Row Containing Both List and Detail Data

Suppose an application stores orders by **tenant + customer + month**, ordered by creation time:

~~~sql
-- Run in lab only. Replace datacenter1 with your actual DC name.
CREATE KEYSPACE IF NOT EXISTS query_tuning_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS query_tuning_lab.orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_minor bigint,
    details_json text,
    receipt_blob blob,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

Notes:

- `(tenant_id, customer_id, month_bucket)` is a **composite partition key**. A screen supplying all three components queries **one exact partition**.
- `created_at` and `order_id` are descending clustering columns. `order_id` disambiguates orders sharing a timestamp.
- `status` and `total_minor` suffice for the list view; `details_json` and `receipt_blob` are only needed when opening an order's details.
- Currency uses minor units in `bigint` to avoid floating-point errors; `month_bucket` is `YYYY-MM` normalized by the app to a consistent timezone.
- This single table demonstrates projection impact. When details are very large or access patterns diverge sharply, Section 6 splits them into **query-driven tables**.

Insert a sample row:

~~~sql
INSERT INTO query_tuning_lab.orders_by_customer_month
    (tenant_id, customer_id, month_bucket, created_at, order_id,
     status, total_minor, details_json, receipt_blob)
VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21T09:30:00Z',
    22222222-2222-4222-8222-222222222222,
    'PAID', 20500,
    '{"shipping":"standard","notes":"sample"}',
    0x01020304
);
~~~

`receipt_blob` is just 4 bytes here for CQL practice. In real systems, large blobs require evaluation: many architectures store binary objects in object storage and keep only metadata/URI/access control in Cassandra, depending on security and lifecycle rules.

### 2.2. Avoid SELECT *

~~~sql
-- Valid CQL, but unsuitable if the API only renders a summary list:
SELECT *
FROM query_tuning_lab.orders_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

`SELECT *` returns every column for the matched rows, including `details_json` and `receipt_blob`. Adding a new column to the table later silently bloats this API's payload without any client code change.

Replace with an explicit projection:

~~~sql
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

The caller already knows `tenant_id`, `customer_id`, and `month_bucket` from the request, so there is no need to echo them on every row unless specifically required. Default `ORDER BY` already follows the table's clustering order; within a single partition you may write `ORDER BY created_at DESC, order_id DESC` to make intent explicit, though never to sort arbitrarily across partitions.

**Rule:** projections mirror the API's **data contract**, not just the storage schema. Across multiple screens, define separate `SELECT` statements instead of one "mega-DTO" pulling every column.

### 2.3. Do Not Confuse Projection with Filtering

`SELECT order_id, status` alters only **returned columns**. It does not shrink **rows** examined when `WHERE` remains overly broad.

Do not mistake this for optimized just because it selects two columns:

~~~sql
-- Example of a query without proper key alignment:
SELECT order_id, status
FROM query_tuning_lab.orders_by_customer_month
WHERE status = 'PAID'
ALLOW FILTERING;
~~~

Depending on version and schema, this may be rejected or allowed with wide-scan risk; `ALLOW FILTERING` creates no partition key and guarantees no I/O reduction. Model a dedicated table for **querying orders by status** if that lookup is frequent.

## 3. Reducing Row Counts and Data Scope

### 3.1. Narrow the Partition and Clustering Range

With a monthly bucket, a single customer may have many orders. If viewing only one day:

~~~sql
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at >= '2026-11-21T00:00:00Z'
  AND created_at <  '2026-11-22T00:00:00Z'
LIMIT 20;
~~~

When the query provides the partition key and a clustering range, Cassandra bounds the read far more efficiently than a time filter lacking key alignment. With `DESC` clustering, newer rows appear first by default.

Do not omit `month_bucket` expecting `created_at` to act as a partition key. If a requirement spans multiple months, the app must enumerate a **bounded list of buckets** and merge results cleanly—or use a table modeled for that screen.

### 3.2. LIMIT Helps, but Is Not an Absolute Byte or I/O Cap

`LIMIT 20` caps **output rows**, not "20 KiB" or "at most 20 SSTable entries."

- Twenty rows carrying large `receipt_blob`s can still produce a multi-MiB payload under `SELECT *`.
- Dense tombstones or TTL-expired rows can force the server to inspect far more than 20 live rows.
- A query missing the partition key yet bearing `LIMIT` can still be prohibitively expensive.
- `LIMIT` does not stop a partition from becoming hot or oversized.

Enforce **API-level bounds** too: max `pageSize`, max date span, max buckets, and max total items returned. Never let a caller demand hundreds of thousands of rows via `?limit=999999`.

### 3.3. Do Not Paginate Like SQL OFFSET

Relational SQL supports `LIMIT 20 OFFSET 100000`, whereas Cassandra CQL does not offer arbitrary `OFFSET` jumping as a full-set scan/sort engine. Even in engines supporting `OFFSET`, skipping huge numbers of preceding rows burns resources.

In Cassandra, use:

1. **Driver/server paging state** to fetch the next page of the **exact same query**.
2. **Clustering-key cursors** once you have explicitly designed and tested ordering, boundary conditions, duplicate timestamps, and behavior under concurrent writes.

**Paging state is an opaque token**, not a page number and not an immutable snapshot contract across calls. If the API exposes a paging token to clients, bind it to tenant/user authorization, query shape, parameters, and expiration, with tamper protection; never treat an arbitrary client token as trusted state.

## 4. Estimating Result Size Instead of Only Counting Rows

Suppose one order row contains:

| Component | *Illustrative* size |
| --- | ---: |
| `order_id`, timestamp, status, total, and overhead | 200 bytes |
| `details_json` | 4 KiB |
| `receipt_blob` | 256 KiB |

For 50 rows:

- List projection: roughly `50 × 200 = 10,000 bytes`, before framing/compression and other overhead.
- `SELECT *` including details: roughly `50 × (200 + 4,096 + 262,144) ≈ 13.3 MB` of raw cell values.

These are **illustrative estimates**, not a Cassandra benchmark. Actual wire size depends on data, nulls, column types, encoding, protocol framing, wire compression, metadata, and driver representation. The point: **50 rows is not automatically "small."**

A budgeting template:

~~~text
estimated_response_bytes
    ≈ rows_returned × average_selected_cell_bytes
      + CQL_protocol_overhead

estimated_pages
    ≈ ceil(rows_returned / effective_page_size)
      (estimate only; the server may return shorter pages)
~~~

If an API has an 80 ms p95 SLO and a 13 MB payload, shaving a few milliseconds in Java code will not offset payload serialization and network transfer. Measure directly; never translate byte estimates into fixed latency via formula.

## 5. Paging: Lower Memory Without Excessive Round-Trips

Cassandra paginates results to avoid buffering and transmitting an entire result set at once. Java Driver 4.x lets you set `pageSize`, hinting the target rows per server response page.

| Setting | Benefit | Risk / trade-off |
| --- | --- | --- |
| Very small pages, e.g., 5 rows | Tiny per-response footprint; fast first few rows | Reading 100 rows triggers many fetch-next-page round-trips |
| Medium pages, e.g., 25–100 rows | Balanced payload and fetch count for lists | Still monitor individual row byte sizes |
| Very large pages, e.g., 5,000 rows | Fewer round-trips if truly reading bulk data | Heavy payloads, heap/GC pressure, network spikes, p99 risk, weak API bounds |

**Page size does not cap total rows.** `setPageSize(25)` can still yield dozens of 25-row pages if the driver or app keeps iterating; it is not equivalent to `LIMIT 25`. Combine:

- `LIMIT` or clustering range for a **hard output row ceiling**.
- `setPageSize` to tune **rows per fetch chunk**.
- **Application caps** on pages, rows, and acceptable total bytes.

### Every Page Fetch Is Another Network Exchange

~~~mermaid
sequenceDiagram
    participant UI as UI/API
    participant Java as Java Driver
    participant C as Cassandra coordinator
    UI->>Java: List first 25 orders
    Java->>C: SELECT ... LIMIT 100 (page size 25)
    C-->>Java: Page 1 + paging state
    Java-->>UI: First 25 orders
    Note over UI: User requests next page
    UI->>Java: Next page
    Java->>C: Fetch page 2 (same query)
    C-->>Java: Page 2 + next state
    Java-->>UI: Next 25 orders
~~~

**Do not prefetch every page unconditionally** if users usually view only page one. Conversely, if a bounded report genuinely consumes the full range with work between fetches, tiny pages inflate total runtime. Pick `pageSize` by benchmarking realistic data and traffic, not a universal "magic number."

Queries can return fewer rows than `pageSize` due to server limits, partition/tombstone boundaries, or query conditions. **Rely solely on the driver's `hasMorePages`/paging state**, never assuming "fewer than 25 rows means end of results."

## 6. List/Detail Table Design to Avoid Shipping Heavy Data on Every Request

When lists are read often and details rarely opened, split into **query-driven tables**:

~~~sql
CREATE TABLE IF NOT EXISTS query_tuning_lab.orders_list_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_minor bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

CREATE TABLE IF NOT EXISTS query_tuning_lab.order_details_by_id (
    tenant_id text,
    order_id uuid,
    details_json text,
    receipt_blob blob,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

`orders_list_by_customer_month` stores only list columns. `order_details_by_id` looks up details directly via the **partition key `(tenant_id, order_id)`**, avoiding scanning all customer orders.

CQL flow:

~~~sql
-- List of 20 most recent orders:
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_list_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;

-- Only when the user opens a specific order:
SELECT details_json, receipt_blob
FROM query_tuning_lab.order_details_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 22222222-2222-4222-8222-222222222222;
~~~

**Trade-off:** Cassandra thrives on **denormalization and query-specific tables**, yet writes now span multiple tables; never assume writes across **two partitions/tables** form a single atomic transaction. When recording an order, enforce idempotent retries, event/outbox patterns, or reconciliation so list and detail views do not drift. Conversely, if the list screen always displays `details_json`, splitting tables can force extra requests and hurt performance.

### Why Not Partition the Detail Table Solely by Tenant?

If `order_details_by_id` used `PRIMARY KEY ((tenant_id), order_id)`, a massive tenant would accumulate a gigantic partition. `PRIMARY KEY ((tenant_id, order_id))` gives **one partition per tenant + order**, enabling direct point reads with two known values while preventing unbounded partition growth.

To serve both "customer's orders in a month" and "one order by ID," **two tables with distinct keys** is far cleaner than forcing a mismatched query through `ALLOW FILTERING`.

## 7. Network Round-Trips and the N+1 Problem in Java

Suppose a list API returns 20 orders and a developer writes:

~~~text
1 CQL query: SELECT 20 order_ids for the month.
20 follow-up CQL queries: for each order_id, SELECT details_json/receipt_blob.

Total: 21 client-side CQL calls for one HTTP request.
~~~

Even if every point query hits a single partition and runs fast in a lab, total RPCs and connection contention scale linearly with item count. Each call traverses the network, coordinator, replicas, and result allocation separately.

**Choose based on UI needs:**

- If the **screen only shows status/total**: one CQL projection on the list table suffices; skip details.
- If the **user clicks into one order**: issue a single detail query on demand.
- If the **screen always renders 20 detail summaries**: model a dedicated summary table/projection containing the needed fields rather than firing 20 ad hoc queries.
- If spanning multiple partitions: enforce a **bounded fan-out** and controlled concurrency; a giant `IN` clause or a loop of thousands of calls is not an optimization.

**CQL `BATCH` is not a `SELECT` batch.** `BEGIN BATCH ... APPLY BATCH` groups write mutations; it does not combine 20 `SELECT`s into one read. Never use a logged batch to "optimize N+1 reads"—it only adds write and batchlog overhead.

### Physical Round-Trips Are Not Just 21 vs. 1

Client-side CQL call count is useful, yet a single `LOCAL_QUORUM` read contacts multiple replicas, and retries/speculative executions add extra physical messages. In multi-DC setups, misrouting a client to a remote DC adds WAN latency even for a single CQL call.

Measure:

- **Client CQL requests per HTTP request**, retries, and speculative executions.
- **Server pages fetched per request**, row counts, and response sizes.
- **p95/p99** CQL time, total HTTP time, and serialization/deserialization time.
- **Bytes sent/received**, network bandwidth, pool saturation, GC, and timeouts.

Combining queries into one massive multi-tens-of-MiB response can perform **worse** than bounded smaller requests; validate empirically.

## 8. Java Driver 4.x: Projections, Async Paging, and Bounds

### 8.1. Clean, Bounded List Query

This example uses **Cassandra Java Driver 4.x**, Java 17, and `orders_list_by_customer_month`. It reuses `CqlSession`, prepares the statement once, uses `LOCAL_QUORUM`, and reads at most **two pages** with a target of **25 rows** per page. The CQL itself enforces `LIMIT 100` to prevent runaway execution.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class OrderListReader {
    private static final int PAGE_SIZE = 25;
    private static final int MAX_PAGES = 2;
    private static final int MAX_ROWS = 50;

    public record OrderSummary(
        Instant createdAt, UUID orderId, String status, long totalMinor) {}

    private final CqlSession session;
    private final PreparedStatement readList;

    public OrderListReader(CqlSession session) {
        this.session = session;
        this.readList = session.prepare(
            "SELECT created_at, order_id, status, total_minor " +
            "FROM query_tuning_lab.orders_list_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? " +
            "AND month_bucket = ? LIMIT 100");
    }

    public CompletionStage<List<OrderSummary>> readBounded(
            String tenantId, UUID customerId, String monthBucket) {
        if (tenantId == null || tenantId.isBlank()
                || customerId == null
                || monthBucket == null
                || !monthBucket.matches("\\d{4}-\\d{2}")) {
            throw new IllegalArgumentException("Invalid read key");
        }

        BoundStatement statement = readList.bind(
                tenantId, customerId, monthBucket)
            .setPageSize(PAGE_SIZE)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);

        return session.executeAsync(statement)
            .thenCompose(first -> collect(first, new ArrayList<>(), 1));
    }

    private CompletionStage<List<OrderSummary>> collect(
            AsyncResultSet page, ArrayList<OrderSummary> rows, int pageNo) {
        for (Row row : page.currentPage()) {
            if (rows.size() >= MAX_ROWS) {
                return CompletableFuture.completedFuture(List.copyOf(rows));
            }
            rows.add(new OrderSummary(
                row.getInstant("created_at"),
                row.getUuid("order_id"),
                row.getString("status"),
                row.getLong("total_minor")));
        }

        if (pageNo >= MAX_PAGES || !page.hasMorePages()) {
            return CompletableFuture.completedFuture(List.copyOf(rows));
        }
        return page.fetchNextPage()
            .thenCompose(next -> collect(next, rows, pageNo + 1));
    }
}
~~~

**Key takeaways:**

- The `SELECT` **projects only four columns** required for `OrderSummary`, omitting `details_json` and `receipt_blob`.
- `WHERE` provides all three partition key components. CQL caps total rows at `LIMIT 100`, while the method enforces an **application cap of 2 pages / 50 rows**.
- `setPageSize(25)` controls server page size, **not** `LIMIT 25`. `currentPage()` iterates only the rows already buffered in the current page.
- `fetchNextPage()` issues an additional request. The code invokes it only if a second page is needed and `hasMorePages()` is true—never unbounded.
- `CompletionStage` keeps execution non-blocking instead of calling `join()` in a loop per page. The HTTP layer still needs outer concurrency, backpressure, and timeout bounds.
- `setIdempotence(true)` applies to pure `SELECT` reads; never copy it blindly to mutations with side effects without analysis.
- `LOCAL_QUORUM` assumes matching RF/DC setup. If a client routes to a different DC, latency and freshness change.

This demonstrates a **bounded 50-row collection pattern**. If the UI only displays page one, **stop after the first `currentPage()`** and fetch the next page only on user "Load more" action. Collecting two pages here illustrates round-trip accounting, not a recommendation to prefetch page two unconditionally.

### 8.2. Avoid "Fetch All Then subList"

An anti-pattern to avoid:

~~~java
// Anti-pattern: may fetch many pages, inflating memory and network traffic.
// DO NOT use on unbounded datasets.
List<Row> allRows = session.execute(statement).all();
List<Row> firstTwenty = allRows.subList(0, Math.min(20, allRows.size()));
~~~

`ResultSet.all()` triggers fetching all remaining pages before slicing in Java. If the caller only needs 20 rows, **bound the query with CQL `LIMIT` and server-side paging** instead of truncating after download.

### 8.3. Do Prepared Statements Reduce Round-Trips?

`PreparedStatement` lets you reuse query plans/metadata, bind parameters safely, and avoid re-sending preparation overhead on every request. However:

- The initial `prepare` still talks to the server; the driver caches it and reprepares if needed.
- Prepared statements **do not merge 20 `SELECT`s into 1**.
- Parameter binding eliminates string concatenation per call, yet primary gains still come from **keys, payload size, page size, and request count**.

## 9. Connections to Replication, Consistency, Tombstones, and Compaction

### Consistency Level and Participating Replicas

Assuming RF=3 in a DC:

| Read CL | Minimum local-DC responses needed | Expected effect |
| --- | --- | --- |
| `LOCAL_ONE` | 1 | Potentially fewer round-trips/lower latency, but may return stale replica data |
| `LOCAL_QUORUM` | 2 | Higher response quorum; may involve data/digest comparison and read repair |
| `ALL` | 3 | Sensitive to slow/down replicas; never use as default "speed tuning" |

**Narrowing projection does not reduce the ACKs/responses required by CL.** Projection shrinks returned columns; CL governs replica coordination. For freshness-sensitive workloads, never downgrade `LOCAL_QUORUM` to `LOCAL_ONE` just to flatter benchmark numbers.

### Tombstones, TTLs, and Small-Result Queries That Run Slowly

A `SELECT ... LIMIT 20` can still traverse numerous tombstones or TTL-expired rows before finding 20 live rows. Therefore:

- Measure **tombstones scanned**, SSTables touched, partition size, and read latency.
- Review TTL policies, `gc_grace_seconds`, compaction strategy, and deletion patterns.
- Never raise `LIMIT` recklessly or slash `gc_grace_seconds` blindly to hide slow queries.

### Compaction and SSTables

When a partition spans multiple SSTables, the read path checks multiple files. STCS, LCS, TWCS, and UCS (on supported versions) shift read, write, and space amplification per workload. Even after shrinking a response from 13 MB to 10 KB, **latency can remain high** if replicas inspect many SSTables/tombstones or compaction saturates disk I/O.

### Multi-Datacenter Routing

With per-DC RF and a configured driver local datacenter, `LOCAL_QUORUM` operates within the coordinator's DC. If clients accidentally route to a remote DC, even tiny requests traverse the WAN. Verify contact points, driver local DC, token-aware routing, and per-DC p95 before blaming "large payloads" for Cassandra slowness.

## 10. Benchmarking One Lever at a Time

A useful benchmark isolates **which variable changed**, rather than altering schema, data, workload, and CL simultaneously and crediting projection for all gains.

### Baseline Setup

1. Generate lab data with realistic row counts and **blob/text size distributions**. Do not exhaust disk if capacity is tight.
2. Fix partitions/buckets, order lists, and the list/detail query ratio.
3. Hold RF, CL, live nodes, Cassandra version, background read/write load, and compression constant.
4. Record p50/p95/p99, CQL request count, page count, total bytes, row counts, and timeouts/unavailables.
5. Run enough iterations to absorb cache warmup; separate idle-cluster runs from background-load runs.

### Controlled Experiments

| Run | Query / change | Hypothesis to verify |
| --- | --- | --- |
| A | `SELECT *` on one partition, `LIMIT 20` | Baseline for payload and latency |
| B | Only `created_at, order_id, status, total_minor`, same `WHERE`/`LIMIT` | Payload shrinks; p95 may drop depending on network/serialization |
| C | Projection from B + daily clustering range | Fewer bytes/rows scanned if scope actually narrows |
| D | Page size 5 vs. 25 vs. 100, same total row cap | Fetch count vs. bytes/page trade-off |
| E | N+1 list API vs. list-only + detail-on-click | Drops CQL requests on common list path |
| F | Query-driven list/detail tables | Trades slimmer list storage/reads for extra writes/reconciliation |

### Measurement Log Template

| Metric | Baseline | After tuning | Notes |
| --- | ---: | ---: | --- |
| CQL requests / API call | Fill measured | Fill measured | Note retries/speculative executions |
| Pages fetched / API call | Fill measured | Fill measured | Not identical to `SELECT` statement count |
| Rows returned | Fill measured | Fill measured | Verify functional equivalence |
| Response bytes | Fill measured | Fill measured | Measure post-encoding; note compression |
| p95 / p99 CQL | Fill measured | Fill measured | At identical load/CL |
| p95 / p99 HTTP | Fill measured | Fill measured | Includes JSON serialization and non-Cassandra network |
| CPU / heap / GC | Fill measured | Fill measured | Separate Java-side bottlenecks |
| Cassandra timeouts | Fill measured | Fill measured | Never omit errors from latency stats |

**Never measure only successful requests** while discarding timeouts: a tweak that speeds up 99 requests while timing out 1 worsens p99 and SLO compliance. Track latency bucketed by payload size and page count rather than averages alone.

## 11. Diagnosing When Tuning Has No Effect

| Symptom | Likely cause | Where to check |
| --- | --- | --- |
| Dropping blobs from `SELECT` barely moves p95 | Bottleneck is disk, tombstones, CL, or fixed network RTT | Tracing, `nodetool tablestats`, page count, server/client latency |
| `pageSize = 5` makes requests slower | Too many page fetches and round-trips | Count `fetchNextPage` calls and measure network RTT |
| `pageSize = 5,000` spikes p99/GC | Oversized page payloads | Inspect heap, row sizes, bytes/page; lower page size |
| Query returns only 20 rows yet is very slow | Wide partition, heavy tombstones, unkeyed scan | Check primary key, clustering range, TTLs, compaction |
| List API issues dozens of CQL queries | N+1 detail fetching per row | Return list projection, lazy-load details, align schema with UI |
| Read timeouts across nodes despite `LIMIT` | Wide scan/filtering, CL, slow replica, network | Partition `WHERE` clause, tracing, per-node/DC metrics |
| Prepared statements barely cut latency | Bottleneck is payload or page count, not CQL parsing | Measure requests/bytes/tracing rather than focusing solely on prepare |
| List and detail tables drift after split | Cross-partition multi-table writes are non-atomic | Idempotency, event log/outbox, reconciliation, and backfill |
| Higher throughput causes more timeouts | Excessive concurrency saturating pools/replicas | Rate limits, backpressure, timeouts, and in-flight caps |

### Using Selective Tracing

In `cqlsh`:

~~~text
TRACING ON
~~~

~~~sql
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_list_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

~~~text
TRACING OFF
~~~

Tracing exposes the coordinator, replicas, timings, and read stages. **Never enable tracing broadly in production** due to overhead and system table writes. Cross-check with metrics:

~~~bash
nodetool status
nodetool tablestats query_tuning_lab.orders_list_by_customer_month
nodetool compactionstats
~~~

`nodetool` helps inspect node and table health, whereas measuring **actual bytes returned to the client and pages fetched by Java** requires driver/proxy metrics or application instrumentation—do not infer those solely from `tablestats`.

## 12. Pre-Production Checklist

- [ ] Every request uses a partition key or a benchmarked index/query path; do not scan broadly just because `SELECT` lists few columns.
- [ ] DTOs and list projections match exact UI needs; never default to `SELECT *`.
- [ ] API bounds time spans, partition/bucket counts, total rows, and payload sizes.
- [ ] Page size is chosen via measurements; the UI does not auto-fetch unnecessary pages.
- [ ] Any exposed paging token is bound to tenant, authorization, query parameters, expiration, and integrity checks.
- [ ] Unbounded N+1 loops are eliminated; CQL requests per API call (including retries/speculation) are measured.
- [ ] Java reuses `CqlSession` and `PreparedStatement`s with bounded concurrency and backpressure.
- [ ] Optimizations do not silently weaken consistency levels; RF, local DC, and routing are verified.
- [ ] Bytes, rows, pages, p95/p99 latency, timeouts, CPU/GC, and Cassandra impact are measured.
- [ ] When denormalizing list/detail tables, idempotent writes, drift monitoring, and reconciliation are in place.
- [ ] A rollback path to the prior schema/query exists alongside functional tests on realistic data before rollout.

## 13. Hands-On Exercises

**Exercise 1 — Projection.** Create `orders_by_customer_month` and load rows with `details_json` and `receipt_blob`. Run `SELECT *` vs. a four-column `SELECT` with identical `WHERE/LIMIT`. Capture driver bytes received and latency; explain why byte savings can exceed disk I/O savings.

**Exercise 2 — LIMIT Does Not Bound Bytes.** Compare 20 rows with 256 KiB blobs vs. 20 rows without blobs and estimate raw sizes for both `SELECT`s. List real-world factors that make wire response bytes differ from simple multiplication.

**Exercise 3 — Page Size.** Populate exactly 100 rows and test page sizes 5, 25, and 100. Count actual page fetches and compare p95 under varied simulated network RTT. Why doesn't a page returning fewer rows than `pageSize` guarantee it is the last page?

**Exercise 4 — N+1.** A 50-order list API currently fires one detail `SELECT` per order. Count minimum CQL requests. Design a list-projection + detail-on-click flow and describe when that split could perform worse.

**Exercise 5 — Partition-Driven Design.** A new requirement asks for "the 30 latest orders for a customer across six months." Why is one `month_bucket` insufficient? Propose bounded fan-out/merging or a new query-driven table; never use `ALLOW FILTERING` as a schema substitute.

**Exercise 6 — Java Async Paging.** Modify `OrderListReader` to return only the first page to the UI and fetch subsequent pages on demand. Explain how to store/protect the paging token and why `ResultSet.all()` must not be used for short list endpoints.

**Exercise 7 — Consistency and Tracing.** With RF=3, compare `LOCAL_ONE` and `LOCAL_QUORUM` in terms of required replica responses. If two runs of the same 200-byte query differ in latency, can you blame projection? List the evidence needed to find the root cause.

**Exercise 8 — Multi-Table Writes.** After splitting list and detail tables, the list write succeeds while the detail write times out. Why must a timeout never be treated as "definitely not written"? Design an operation ID, idempotent retry, outbox/reconciliation flow, and drift alerting.

## Key Takeaways

**Cassandra query tuning does not stop at the partition key: you must also shrink returned payloads and network round-trips.** Use explicit projections instead of `SELECT *`, bound rows and clustering ranges, balance `LIMIT` with page size, skip unnecessary page/detail fetches, and eliminate N+1 queries. Use query-driven tables where warranted while accounting for multi-table write cost. Finally, benchmark **bytes, pages, round-trips, p95/p99, errors, and resource usage** under identical RF, CL, and workloads—a tiny response never fixes missing partition keys, dense tombstones, or slow replicas.
