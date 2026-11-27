# Page Size, LIMIT, and Client/Server Memory in Apache Cassandra

## 1. Problem: A "Working" SELECT Can Still Exhaust Memory

Apache Cassandra is a distributed **wide-column** database. Data is distributed by **partition key**, tables should be modeled around queries, and every CQL request flows through the Java Driver and coordinator to replicas per the **consistency level**. A seemingly simple `SELECT` can return tens of thousands of rows, saturate the network, consume node memory, and trigger GC pauses or `OutOfMemoryError` in the Java application.

Two parameters frequently confused are CQL **`LIMIT`** and the driver's **page size / fetch size**:

- **`LIMIT`** caps the **total number of result rows** a single query execution is allowed to return.
- **Page size** sets the target **number of rows per result page**, letting the client fetch results in chunks instead of pulling everything at once.
- **Client/server memory** depends on actual per-row byte size, active pages in flight, concurrent requests, how the client accumulates results, and the read work required to assemble each page.

They are **not** equivalent. If a query specifies `LIMIT 10000` with a page size of `200`, the application may process many pages; if client code calls `all()` and holds all 10,000 rows in memory, most of paging's client-memory benefit disappears.

This lesson belongs to the **Query Tuning** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The focus is choosing `LIMIT`, page size, and result-consumption patterns for Java applications in a distributed cluster while respecting replication, compaction, consistency, and read cost.

## 2. How Do Page Size and LIMIT Differ?

### 2.1. Core Comparison Table

| Dimension | CQL `LIMIT` | Driver page size |
|---|---|---|
| Where set? | Inside the `SELECT` statement | Statement/driver property or driver configuration |
| Purpose | Caps **maximum total rows returned** | Splits results into multiple pages |
| Scope | Entire query execution | Per page fetch |
| Example | `LIMIT 500` | `setPageSize(100)` |
| If 500 rows match | At most 500 rows returned | May take roughly 5 pages, depending on sizes and server limits |
| Makes a wide filter scan efficient? | **No** | **No** |
| Guarantees RAM cap in MB? | **No**: individual rows can be huge | **No**: row count does not reflect bytes |
| Can cause client to retain all results? | Yes, if code collects everything | Yes, if code calls `all()` / collects every page |

### 2.2. Three Very Different Cases

Suppose a query targets a single partition with 20,000 matching rows.

**Case A: `LIMIT 50`, page size = 500**

The query returns at most 50 rows. Normally one page suffices because the result limit is smaller than the page size; this still does not guarantee the server read only 50 internal entries.

**Case B: `LIMIT 1000`, page size = 200**

The query returns at most 1,000 rows delivered across multiple pages. Ideally that is 5 pages of 200 rows; in practice it can vary due to byte-based page limits, row sizes, tombstone handling, and runtime conditions.

**Case C: No `LIMIT`, page size = 200**

The server keeps serving pages until the result set ends or the client stops consuming. **Page size 200 does not mean the query returns at most 200 rows total.**

### 2.3. Visualizing Paginated Data Flow

~~~mermaid
sequenceDiagram
    participant A as Java service
    participant D as Cassandra Driver
    participant C as Coordinator
    participant R as Replica
    A->>D: SELECT ... LIMIT 1000, pageSize=200
    D->>C: Request first page
    C->>R: Read matching data
    R-->>C: Read result
    C-->>D: Page 1 + paging state
    D-->>A: Rows from page 1
    Note over A: Process row by row; no need to retain all
    A->>D: Continue iterating results
    D->>C: Request page 2 with paging state
    C-->>D: Page 2 + paging state
    D-->>A: Rows from page 2
    Note over A,D: Repeat until LIMIT or end of results
~~~

This diagram shows the logical flow. The synchronous driver can **automatically fetch the next page as the iterator advances**; with the async API, the application explicitly decides when to call `fetchNextPage()`.

## 3. What Does `LIMIT` Actually Bound?

### 3.1. Bounds Output, Not Disk I/O

Telemetry table:

~~~cql
-- Assumes keyspace telemetry already exists.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

The partition key is **`(device_id, event_day)`**, and the clustering key is `event_time`. Fetching the 50 newest events in one day:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

This is a well-scoped query because it supplies the full partition key and reads in clustering order for newest events. Still, **`LIMIT 50` caps only live rows returned**, not how many on-disk entries the storage engine must inspect.

In a partition spanning multiple SSTables and tombstones, Cassandra may read and merge many older entries, skipping deleted or TTL-expired rows before collecting 50 valid rows. Hence **`LIMIT` does not cure tombstone-heavy reads**.

### 3.2. `LIMIT` Does Not Replace WHERE on Partition Key

Consider an inefficient example:

~~~cql
-- Anti-pattern illustration; do not use as a default production API.
SELECT device_id, event_day, event_time, value
FROM telemetry.events_by_device_day
WHERE value > 80
LIMIT 50
ALLOW FILTERING;
~~~

Here the server may need to scan many partitions to find 50 matching rows. A small page size and `LIMIT 50` do not eliminate the wide search.

If you need to look up by `value` or another dimension, **model a query-specific table**, consider controlled data duplication, or evaluate indexing/search options suited to your version and workload. Never use `ALLOW FILTERING` as a read-cost optimization.

### 3.3. `LIMIT` Is Not Offset Pagination

Some SQL databases support:

~~~sql
SELECT ... LIMIT 100 OFFSET 5000;
~~~

There is **no equivalent CQL pagination pattern**. Cassandra does not offer a general SQL `OFFSET` to jump arbitrarily to "page 50" of a large result set.

For Cassandra, two primary patterns apply:

- **Paging state**: resume the same query from the server/driver continuation position.
- **Keyset/range pagination** on clustering keys: the API queries rows after/before a known key marker, ideal when stable ordered navigation and explicit cursor management are needed.

Never simulate `OFFSET` by reading and discarding 5,000 rows client-side on every request: skipped rows still burn network, CPU, and I/O.

## 4. How Is Page Size Actually Applied?

### 4.1. Page Size Is Normally a Row-Count Target, Not a Byte Quota

In Java Driver 4.x, you can set:

~~~java
BoundStatement statement = prepared.bind(deviceId, eventDay)
    .setPageSize(200);
~~~

This asks the driver to fetch pages targeting 200 rows. However:

1. One row may hold large blobs/collections, so 200 rows can total megabytes.
2. Cassandra also enforces message/page size limits and guardrails, depending on version and config.
3. A page may contain **fewer** than the target rows; getting fewer than 200 rows does not mean results are exhausted.
4. When tombstones, byte boundaries, or server limits trigger, actual server work can far exceed returned bytes.

**Do not treat page size as a hard RAM quota.** Measure **bytes/page** and pages/second, not row counts alone.

### 4.2. Choosing Page Size by Row Characteristics

| Data / query profile | Risk if page is too large | Considerations |
|---|---|---|
| Small rows, few scalar columns | High row counts per page; buffers and allocations grow with concurrency | Can test relatively larger pages; measure bytes and latency |
| Rows with large blobs/collections | Single page can hold many MBs | Start with small pages and bound row sizes / data model |
| Very wide partitions | Large pages pull long slices; server scan or client memory spikes | Bound clustering ranges and consider bucketing |
| Multi-partition / range scans | Many replicas/partitions; total result size unpredictable | Bound scope and concurrency; set stop conditions |
| UI "load 20 more items" | Fetching 1,000 rows when user views 20 wastes work | Align page size with UI demand or use keyset pagination |
| Batch export | Tiny pages cause excessive round-trips; huge pages pressure memory | Benchmark multiple sizes; record results and keep streaming/bounded buffers |

No single page size is optimal for every table. No guide can replace benchmarking against your actual row sizes, network RTT, CL, concurrency, and available RAM.

### 4.3. Too Small Also Has a Cost

Reading 10,000 rows at 10 rows per page theoretically takes ~1,000 page exchanges. Each round incurs request, coordinator, network RTT, parsing, and iterator/async scheduling overhead.

Very large page sizes reduce round-trips yet can inflate bytes/message, time to first page, CPU, heap/GC, and network congestion. The goal is not **smallest possible pages**, but **balancing time to first result, total throughput, and peak memory**.

### 4.4. Page Size Does Not Change Write Batches

Page size governs **pagination of `SELECT` results**. It does not limit mutations inside `BEGIN BATCH`, split a large blob write into chunks, or make multi-partition batches cheap.

When writing millions of rows, control **sensible batching, prepared statements, concurrency, backpressure, and data modeling**—do not tweak fetch/page size expecting lower write-path memory.

## 5. Server Memory: A Page Can Cost More Than It Looks

### 5.1. Costs Present During Reads

A single read request may require:

- **Buffers** for reading SSTable data, indexes, and compressed/decompressed chunks.
- **Iterators and merge state** when a partition spans multiple SSTables.
- **Tombstone** and TTL processing; many discarded rows may be read to build one page of few live rows.
- **Memory/serialization buffers** to assemble and transmit the CQL response over the network.
- **Request concurrency**, queues, CPU, and disk bandwidth shared across parallel requests.
- Background work like **compaction, repair, and streaming** competing for CPU and I/O.

Page size limits how many rows a single response aims to ship, yet **does not guarantee server peak RAM scales strictly with row count**, nor does it stop huge partitions or large collections from straining storage.

### 5.2. Illustrative Byte Calculation

Assume each serialized row averages **4 KiB**, before other overhead.

| Page size | Estimated payload per page | 120 concurrent active pages/requests (idealized payload) |
|---:|---:|---:|
| 100 rows | 400 KiB ≈ 0.39 MiB | ≈ 46.9 MiB |
| 200 rows | 800 KiB ≈ 0.78 MiB | ≈ 93.8 MiB |
| 1,000 rows | 4,000 KiB ≈ 3.91 MiB | ≈ 468.8 MiB |
| 2,000 rows | 8,000 KiB ≈ 7.81 MiB | ≈ 937.5 MiB |

These numbers illustrate only **concurrent live payload**, not actual Cassandra or Java heap. Object headers, buffers, compression, codecs, GC, metadata, prefetched pages, request queues, and concurrency make real memory footprint differ substantially. Never assume every request holds an entire page simultaneously.

### 5.3. Concurrency and Page Size Must Be Tuned Together

An application never handles just "one read request." If 100 HTTP requests run concurrently and each pulls multiple pages, in-flight bytes scale with active requests and buffered chunks.

An approximate mental model:

~~~text
In-flight page payload (estimate)
≈ active_page_count × avg_serialized_bytes_per_page

Client retained results (estimate)
≈ retained_row_count × avg_in_memory_bytes_per_row

Peak memory is driven by both, plus driver buffers,
application objects, caches, GC, and non-Cassandra work.
~~~

**`avg_serialized_bytes_per_row` does not equal `avg_in_memory_bytes_per_row`.** Java objects add headers, references, collections, and intermediate allocations; decoded objects often consume more heap than wire bytes.

Therefore, measure simultaneously:

- In-flight requests and active pages.
- Bytes returned per request/page.
- Java heap used, GC pauses, and allocation rate.
- Cassandra heap/off-heap/disk I/O and read latency.
- Client timeouts, backpressure, and end-to-end p95/p99.

## 6. Java Memory: Automatic Paging Does Not Mean Automatic Streaming Everywhere

### 6.1. Synchronous: `ResultSet` Fetches Next Pages During Iteration

Java Driver 4.x provides `ResultSet` for synchronous reads. The driver receives the first page and fetches subsequent pages as iteration demands more rows.

**Incremental processing without retaining every row:**

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.UUID;

// session is initialized and managed outside this illustrative snippet.
PreparedStatement ps = session.prepare(
    "SELECT event_time, value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 500"
);

BoundStatement statement = ps.bind(
        UUID.fromString("11111111-1111-1111-1111-111111111111"),
        LocalDate.of(2026, 11, 21))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

ResultSet resultSet = session.execute(statement);
int count = 0;

for (Row row : resultSet) {
    // Process each row immediately instead of accumulating into a large List.
    recordMetric(row.getInstant("event_time"),
                 row.getDouble("value"));
    count++;
}

System.out.println("Processed " + count + " rows");
~~~

Here:

- `LIMIT 500` guarantees the query returns at most 500 rows.
- `setPageSize(100)` targets 100 rows per page—roughly five pages ideally.
- The loop retains only the active row plus internal driver buffers per driver behavior; **do not accumulate 500 `Row` objects in a `List` unnecessarily**.
- `recordMetric` is a placeholder handler; it must avoid retaining all data or blocking excessively.
- Iteration can trigger subsequent page fetches, so total loop duration **differs** from the initial `session.execute(statement)` call time.

### 6.2. Anti-Pattern: `all()` Turns a Paged Query into an In-RAM Collection

This pattern is dangerous without a small upper bound:

~~~java
ResultSet resultSet = session.execute(statement);

// Caution: may fetch all remaining pages and collect every row in RAM.
List<Row> allRows = resultSet.all();
~~~

When a query lacks `LIMIT` or sets a huge bound, `all()` builds a giant `List`, increasing allocations, GC pauses, and `OutOfMemoryError` risk.

**Page size still shapes network framing**, yet the client actively **materializes everything**. Nothing stops 50,000 rows across many pages from piling into the Java heap.

If business logic truly needs all rows for sorting or aggregation, ask whether the computation can:

- Be modeled by query and pre-aggregated ahead of time.
- Stream incrementally without retaining prior rows.
- Write chunks to a backpressure-aware sink.
- Run as an isolated job with bounded concurrency and memory.

### 6.3. `getAvailableWithoutFetching()` Is Not Total Row Count

`ResultSet.getAvailableWithoutFetching()` reports how many rows are buffered locally without another fetch; `isFullyFetched()` tells whether the driver has received all pages of the query.

Do not confuse these methods with **`COUNT(*)`** or total query rows. Once one page is consumed, another page may remain; having 0 locally available rows **does not mean the query is finished**.

## 7. Asynchronous: Using `AsyncResultSet` to Pace Page Fetches

In Java Driver 4.x, `executeAsync(statement)` returns `CompletionStage<AsyncResultSet>`. `AsyncResultSet.currentPage()` exposes the current page's rows; `hasMorePages()` indicates whether more pages exist; `fetchNextPage()` requests the next page.

Example **processing one page at a time** without firing hundreds of concurrent fetch requests:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class PagedEventReader {
    private final CqlSession session;
    private final PreparedStatement ps;

    public PagedEventReader(CqlSession session) {
        this.session = session;
        this.ps = session.prepare(
            "SELECT event_time, value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 500"
        );
    }

    public CompletionStage<Void> read(
            UUID deviceId, LocalDate day) {
        BoundStatement statement = ps.bind(deviceId, day)
            .setPageSize(100)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        return session.executeAsync(statement)
            .thenCompose(this::consumePage);
    }

    private CompletionStage<Void> consumePage(AsyncResultSet page) {
        for (Row row : page.currentPage()) {
            // Demo: lightweight non-blocking processing on driver callback.
            recordMetric(row.getInstant("event_time"),
                         row.getDouble("value"));
        }
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(null);
        }
        return page.fetchNextPage().thenCompose(this::consumePage);
    }

    private void recordMetric(java.time.Instant at, double value) {
        // Replace with fast logic or a backpressure-aware pipeline.
    }
}
~~~

**Limitation of this example:** `recordMetric` here is fast, synchronous, and does not block driver threads. If writing files, making HTTP calls, or performing slow work, offload to a separate executor/sink and fetch the next page only after prior processing completes. Never run heavy I/O directly on a driver callback thread.

Pages are still fetched **sequentially**, preventing prefetching every page before downstream consumes them. For large workloads, add cancellation, deadlines, concurrency limits, and `CompletionStage` error handling.

### When to Choose Synchronous vs. Asynchronous?

| Criterion | Sync `ResultSet` | Async `AsyncResultSet` |
|---|---|---|
| Code style | Simple loops | Reactive/completion-stage pipelines |
| Page fetching | Driver auto-fetches as iterator advances | Application explicitly calls `fetchNextPage()` |
| Blocking | May block application thread waiting for pages | Frees application threads while waiting |
| Backpressure | Natural during sequential row processing, but ties up a thread | Can tie directly to downstream readiness |
| Risks | `all()`, oversized thread pools, long I/O blocking | Firing too many page fetches at once, blocking callbacks, pipeline buffering |

## 8. Paging State Is a Continuation Cursor, Not a Page Number

### 8.1. Concept

When results remain, the server/driver supplies a **paging state** so the next request resumes from the matching position. This token is **opaque** protocol data: never try to parse it as a ring token, offset, or timestamp.

If an HTTP API returns 50 rows per call, it may store or pass a continuation token built from paging state. However, you must:

- Bind the token to the **same query, same bind values, and matching data context**.
- **Validate** the token before use; never trust arbitrary client-supplied bytes as valid paging state.
- Protect tokens sent outside the server (HMAC signing, encryption, or server-side storage depending on architecture).
- Enforce TTL/expiration and handle invalid or expired tokens gracefully.
- Never promise permanent token compatibility across Cassandra version upgrades, query shape edits, or topology changes.
- Never blindly pass query A's state to query B or alter page size mid-pagination without verifying driver/server support.

**Paging state is not a row primary key**, nor does it provide random access to "page 100" without traversing preceding pages.

### 8.2. Paging Does Not Create a Fixed Snapshot Across Requests

Pages may be fetched at **different points in time**. Between pages, new mutations, `DELETE`s, or TTL expirations can change the underlying data. Never assume pages form a single transactional snapshot.

Consequences can include rows appearing or shifting between pages or changing page counts, depending on clustering order, timestamps, and concurrent writes. For APIs needing stable pagination journeys:

- Query by explicit **partition key and clustering key** order.
- Consider **keyset pagination** using a business cursor (e.g., event timestamp plus unique tie-breaker) when appropriate.
- Define acceptable time/session boundaries, or use snapshots/exports in dedicated systems when strict transactional consistency is required.
- Handle deduplication if paginating over rapidly changing data.

### 8.3. Keyset Pagination via Clustering Key

On a table with `PRIMARY KEY ((device_id, event_day), event_time)` and `event_time DESC`, first call:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

The next call uses the **last returned `event_time` marker**:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 50;
~~~

`10:00:00Z` is illustrative; the app must capture the exact last clustering key from the previous page to avoid duplicates. The clustering key must capture both order and uniqueness required by the product; if two events can share a timestamp, include a tie-breaker column in the clustering key.

**Keyset pagination and server paging state solve related but distinct goals.** Keyset maps cleanly to "load items before X" UX and `WHERE` bounds; paging state resumes a CQL execution via server/driver state. Test both under concurrent writes and deletes.

## 9. Controlling Row Counts Across Multiple Partitions

### 9.1. Global LIMIT and PER PARTITION LIMIT

For queries spanning multiple partitions, global `LIMIT` caps **total returned rows**, without preventing one partition from consuming the entire quota. Where supported by Cassandra, `PER PARTITION LIMIT` caps rows **within each partition**, while `LIMIT` caps the overall result.

Syntax illustration **across multiple partitions**:

~~~cql
SELECT device_id, event_day, event_time, value
FROM telemetry.events_by_device_day
PER PARTITION LIMIT 10
LIMIT 100;
~~~

Each partition contributes at most 10 rows, capped at 100 rows total. Yet because there is **no `WHERE` restricting the partition key**, the server still performs a broad scan to locate matching partitions and rows. This illustrates semantics—**not a default production query pattern**.

`PER PARTITION LIMIT` support depends on Cassandra syntax/version; verify interactions with `IN`, `ORDER BY`, and query restrictions.

### 9.2. Do Not Use One Giant Interactive Query to Export an Entire Table

Exporting millions of partitions with an unrestricted `SELECT` plus Java auto-paging can:

- Impose heavy read I/O across the cluster.
- Contend with online traffic and compaction.
- Saturate driver, network, and sink memory.
- Produce time-skewed results as the export drags on.

For batch exports, backups, or migrations, use purpose-built tools/pipelines, split token/partition ranges safely, and keep concurrency low and monitored. **Paging never turns a full scan into a cheap query.**

## 10. Page Size and Consistency Level: Do Not Confuse Speed with Correctness

Page size primarily governs rows per fetch; consistency level governs replica response requirements.

| Setting | What does it change? | What does it NOT change? |
|---|---|---|
| `LIMIT 50` | Caps query output at 50 rows | Does not pick replicas or weaken CL |
| `setPageSize(50)` | Targets 50 rows per page | Does not cap total rows without `LIMIT` |
| `LOCAL_ONE` / `ONE` | Smaller read ACK quorum | Does not guarantee quorum freshness in all scenarios |
| `LOCAL_QUORUM` | Requires quorum in local DC | Does not turn a full scan into a point lookup |
| `QUORUM` | Quorum across keyspace RF | Does not change page size or client memory caps |

Pages of a single query travel across **separate network requests** using the configured paging state and consistency level; never treat an entire multi-page sequence as one atomic snapshot transaction.

Never downgrade CL from `LOCAL_QUORUM` to `ONE` just because page fetches are slow, unless business requirements explicitly allow relaxed read consistency. Tune page size alongside topology, RF, read latency, and fault tolerance—**never instead of them**.

## 11. Optimizing Throughput Without Hurting p99 or RAM

### 11.1. Controlled Experimentation

Pick a representative query shape with fixed dataset, CL, concurrency, and result-handling logic. Test several page sizes while measuring **time to first page**, **total consume time**, **bytes/page**, CPU/RAM, and p99.

**Hypothetical** illustrative measurements:

| Page size | Time to first page p95 | Total time to read 5,000 rows | App peak heap | Observation |
|---:|---:|---:|---:|---|
| 50 | 28 ms | 2,400 ms | 220 MiB | Many network round-trips |
| 200 | 34 ms | 900 ms | 255 MiB | Balanced for this workload |
| 1,000 | 95 ms | 680 ms | 430 MiB | Faster overall, but higher first-page latency and RAM |
| 5,000 | 320 ms | 650 ms | 900 MiB | RAM/GC may be unacceptable |

**These are synthetic numbers to illustrate the methodology**, not Cassandra or driver benchmarks. A different app, row size, or network RTT can invert these trade-offs.

Do not pick `pageSize = 5,000` just for peak throughput if an interactive API needs the first page under 100 ms or runs in tight heap. Conversely, do not force `50` on an export job where total completion time matters more than first-page latency.

### 11.2. When Does Increasing Page Size Hurt?

- Java heap/GC grows with larger page payloads and concurrent requests.
- The server takes longer to assemble huge page responses, driving up timeouts and p99.
- Single responses approach frame/message limits or cause network bursts.
- One client's burst starves bandwidth for peer queries.
- The application rarely consumes the entire first page (e.g., user views 20 rows after fetching 2,000).

### 11.3. When Does Decreasing Page Size Hurt?

- Each query requires many more fetch requests.
- High network RTT, especially across remote datacenters, multiplies round-trip cost.
- Coordinator and driver spend extra overhead handling many tiny pages.
- Total export runtime stretches even though peak memory falls.
- Downstream memory still climbs if application code `collect`s every row anyway.

Aim for a **page size matched to actual consumption**, rather than one rigid system-wide constant.

## 12. Observing and Diagnosing Cassandra When Paging Is Slow

The commands below are starting points; syntax and metric names may vary by version.

~~~bash
# Table metrics: read/write latency, SSTables, and data sizes.
nodetool tablestats telemetry.events_by_device_day

# Per-table histograms, including SSTables per read/latency on supported versions.
nodetool tablehistograms telemetry events_by_device_day

# Coordinator / proxy-path histograms.
nodetool proxyhistograms

# Compaction I/O and pending tasks.
nodetool compactionstats

# Thread pools, queues, and dropped messages.
nodetool tpstats

# Node, DC, and rack status.
nodetool status
~~~

Also inspect **Java Driver metrics**—request latency, in-flight requests, retries, timeouts, and bytes received (if instrumented)—alongside service heap/GC.

### 12.1. Signals That Commonly Appear Together

| Symptom | Hypothesis | Verification step |
|---|---|---|
| Larger page size spikes heap peak and GC | Page payload or client retention too high | Heap metrics, allocations, `all()`, concurrent requests |
| Small page size gives slow total time but fast first page | Excessive network round-trips | Pages/query, RTT, driver metrics |
| Small `LIMIT` still shows high read latency | Tombstone scans or missing partition key | CQL shape, tracing, SSTables per read |
| High client p99, low local-table p99 | Driver queue/retries, coordinator, network | Driver metrics, `proxyhistograms`, network |
| One specific partition is slow | Wide/hot partition, many SSTables/TTLs | Partition size, compaction, tombstones |
| Higher concurrency causes timeouts | Disk, CPU, heap, or connection pool saturation | In-flight count, load, dropped messages |
| Unbounded query OOMs the service | `all()` or retaining rows in RAM | Safe heap inspection, code review, result caps |
| Fewer rows returned than `pageSize` with more pages left | Byte boundary or server paging limits | Inspect paging state/`hasMorePages`, row sizes |

**Never use average read latency to declare an API healthy.** Track p50/p95/p99, timeouts/errors, and SLO good-request ratio. If the slowest requests time out and drop out of success histograms, p99 can appear artificially low.

### 12.2. Selective Tracing

~~~cql
TRACING ON;

SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
~~~

Tracing reveals coordinator/replica steps, yet carries overhead; never enable it across all production traffic just to tune page size. Always correlate traces with load levels, CL, and actual nodes.

## 13. Runbook: Raising Page Size Causes Java Service OOM

Suppose a service changes `setPageSize(200)` to `setPageSize(5000)` to speed up event exports. Soon after:

- Java heap climbs sharply with concurrent export jobs.
- Interactive endpoint p99 degrades.
- GC pauses and timeouts appear.
- Cassandra still serves requests, while the application crashes with OOM.

**Step 1 — Confirm the change and scope.** Verify release, query shape, effective page size, `LIMIT`, concurrent job count, row sizes, and when heap began climbing.

**Step 2 — Inspect consumption code.** Check for `resultSet.all()`, `collect(toList())`, multi-page accumulation, or unbounded queues. Shrinking page size while still collecting every row **may only delay the OOM** without fixing retention.

**Step 3 — Measure payload and heap.** Capture bytes/page, in-flight pages, retained object counts, allocation rate, GC pauses, and timeouts. Inspect unexpected blobs or large collections.

**Step 4 — Restore safe limits.** Following release/rollback procedures, revert to a proven stable page size; cap concurrency and isolate export workloads from interactive traffic. Never blindly inflate heap indefinitely or push uncontrolled load onto Cassandra nodes.

**Step 5 — Fix the design.** Switch to incremental page-by-page processing, eliminate `all()`, apply backpressure, and enforce stop conditions. If an API only needs a 50-row UI page, use an explicit `LIMIT` or keyset pagination rather than an unbounded `SELECT`.

**Step 6 — Verify both sides.** Measure client heap/GC, p99/timeouts, network bytes, server read latency, and compaction pressure. Declare success only when **memory stays stable and SLOs hold**, not merely because the export finishes faster.

## 14. Common Misconceptions

| Statement | True or false? | Reason |
|---|---|---|
| "Page size 100 means `SELECT` returns at most 100 rows." | **False** | Only a per-page target; the query can span many pages |
| "`LIMIT 100` always reads only 100 rows on disk." | **False** | Tombstones, SSTables, and filters can force reading far more |
| "`LIMIT 1000` with page size 200 always yields exactly 5 pages." | **False** | Byte boundaries and runtime limits can alter rows per page |
| "Using `all()` still saves heap because the driver pages." | **False** | `all()` buffers all remaining rows into a single `List` |
| "Page size is a response MB quota." | **False** | Row count differs from byte count; single rows can be huge |
| "Larger page sizes are always faster." | **False** | Involves trade-offs in latency, RAM, network, and server work |
| "The next page is a frozen snapshot." | **Not guaranteed** | Concurrent writes/TTLs between fetches can alter results |
| "You can jump directly to page 50 with `OFFSET`." | **Not standard CQL model** | Use paging state or keyset pagination instead |
| "A small `LIMIT` fixes `ALLOW FILTERING`." | **False** | Scan scope can still be huge |
| "Changing fetch size makes batch `INSERT`s lighter." | **False** | Paging applies to reading results, not splitting write batches |
| "Because the table has a partition key, page size doesn't matter." | **False** | One partition can be huge and rows can carry large payloads |
| "Increasing app heap alone is enough." | **Not necessarily** | Server I/O, network, memory, and concurrency still constrain the system |

## 15. Exercises and Self-Check

### Question 1 — Distinguishing the Two Bounds

A query specifies `LIMIT 750` and the Java Driver sets page size 150. What is the maximum number of rows, and roughly how many pages in the ideal case?

**Answer:** At most 750 rows, roughly 5 pages if each holds 150 rows. Actual page counts can vary due to byte limits, server constraints, and data layout.

### Question 2 — No LIMIT, Small Page Size

A client runs `SELECT` without `LIMIT` using page size 100, then calls `all()`. Why can Java still OOM?

**Answer:** The driver fetches all pages while `all()` retains every row in a `List`. Page size does not cap total rows or total bytes.

### Question 3 — Calculating In-Flight Payload

Each serialized row averages 4 KiB, page size is 1,000, and 120 pages are concurrently active. Roughly how many MiB is the raw payload?

**Answer:** `1000 × 4 KiB × 120 = 480,000 KiB ≈ 468.75 MiB`, excluding metadata, Java objects, buffers, and other work.

### Question 4 — Tombstones

A query supplies the full partition key and `LIMIT 20`, yet scans 8,000 tombstones before collecting enough rows. Name two areas to investigate.

**Answer:** Inspect tombstones/TTLs and stale data spread across SSTables, compaction strategy/backlog, clustering range width, and retention/bucket modeling—do not just raise page size.

### Question 5 — SELECT for a UI

A UI shows 20 events with a "Load more" button. Backend sets page size 5,000 and `SELECT` without `LIMIT`. What are the risks?

**Answer:** Fetches massive data the user has not requested, wasting RAM, network, and first-page latency; retaining all rows risks OOM. Align query limits/page size with UI demand or use controlled keyset/paging tokens.

### Question 6 — Keyset vs. Paging State

Is paging state a long-lived page number that lets you arbitrarily alter `WHERE` or switch partition keys when resuming?

**Answer:** No. It is an opaque continuation token for a matching query, not an offset. Validate, protect, and bind it strictly to its query and parameters.

### Question 7 — Synchronous vs. Asynchronous

With `AsyncResultSet`, why shouldn't you fire `fetchNextPage()` calls in bulk before processing the current page?

**Answer:** Doing so buffers multiple pages simultaneously, breaks backpressure, and inflates in-flight network and heap load. Fetch at the pace downstream can consume.

### Question 8 — Byte Size vs. Row Count

Two tables use page size 200; one has 200 B rows and the other has 100 KiB rows. Will peak memory look similar?

**Answer:** No. Idealized payloads differ by hundreds of times, before overhead. Page size must be evaluated alongside actual row sizes and concurrency.

### Question 9 — CL Configuration

A service reading at `LOCAL_QUORUM` slows down during internal network trouble. Should you immediately switch to `ONE` to cut timeouts?

**Answer:** That changes consistency guarantees, not just paging. Evaluate business correctness requirements, RF/topology, and root latency causes before changing CL.

### Question 10 — Conflicting Benchmark Results

Page size 2,000 yields faster total consume time than page size 200, yet worse p99 time-to-first-page and peak heap. Which do you pick?

**Answer:** It depends on the goal. Interactive endpoints likely favor 200 for latency and RAM; isolated batch exports with dedicated capacity and SLOs might test 2,000. Decide from metrics and resource ceilings, not throughput alone.

## 16. Summary

In Apache Cassandra:

1. **`LIMIT` caps total rows returned by a query; page size targets rows per fetched page.** The two settings serve different purposes.
2. **LIMIT and page size never replace partition-key data modeling.** Unkeyed or tombstone-heavy queries stay expensive even when returning few rows.
3. **Never treat page size as a memory cap:** row size, blobs, concurrency, and client retention determine peak heap.
4. **Both sync and async Java Driver APIs support paging**, yet `ResultSet.all()`, unbounded collectors, or aggressive prefetching defeat low-RAM streaming.
5. **Paging state is an opaque cursor**, not an `OFFSET` or durable snapshot; keyset pagination fits ordered navigation UX well.
6. **Choose page size via controlled benchmarks** measuring time to first page, total consume time, p99, bytes/page, GC, timeouts, and server load.
7. **Keep backpressure and concurrency bounded**, especially for exports, scans, and multi-page APIs.
8. **Separate performance from consistency:** tuning page size leaves RF/CL intact; lowering CL to hide slowness is a correctness decision.

The right tuning question is not simply "what page size should I set?", but **"how many bytes per page, how many pages per request, how many concurrent requests, how long does the client hold rows, and how much must the server read to build each page?"** Answering those questions tunes Cassandra queries and Java clients without sacrificing p99, memory stability, or data integrity.
