# executeAsync, CompletionStage, and AsyncResultSet

## 1. An HTTP Request Needs Cassandra Data Without Holding a Waiting Thread

Suppose a Java application receives thousands of requests per second to read device history. Each request needs to fetch events from **Apache Cassandra** using a `SELECT` by partition key and time range. The initial version used `session.execute(statement)` and then iterated over `ResultSet`. As traffic grew, many application threads were held while waiting for the network and replicas to return results.

The team switched to:

~~~java
CompletionStage<AsyncResultSet> pending =
    session.executeAsync(statement);
~~~

This is the first step toward **asynchronous** processing, but it does not automatically solve everything. If the code immediately calls `pending.toCompletableFuture().join()`, the thread is still blocked; if it only iterates `currentPage()` and returns a list, the API may **miss subsequent pages**; if it dispatches 100,000 `executeAsync` calls at once without admission/backpressure, both the application and Cassandra can still become overloaded.

This lesson belongs to the **Async and Reactive** chapter in the Cassandra module. Its direct topic is **`executeAsync`, `CompletionStage`, and `AsyncResultSet`** in Apache Cassandra Java Driver 4.x. The content connects CQL, partition/clustering keys, replication, consistency levels, timeouts, error handling, and real-world operational capacity.

**After this lesson, you should be able to:**

1. Explain the execution path of an `executeAsync` call and the difference between non-blocking, concurrent, and reactive.
2. Use `CompletionStage` with `thenApply`, `thenCompose`, `whenComplete`, `exceptionally`, and `handle` with correct semantics.
3. Read the **first page** using `AsyncResultSet.currentPage()`, detect `hasMorePages()`, and call `fetchNextPage()` without blocking the callback.
4. Build a multi-page read chain with **page/row limits, deadlines, and bounded concurrency**, without holding all data in the heap.
5. Write an async write path with **admission control, stable primary keys, and handling for uncertain-outcome timeouts**.
6. Distinguish client errors, Cassandra coordinator errors, replica errors, mapping errors, and data model issues.
7. Measure p95/p99, in-flight requests, queues, page/byte counts, GC, retries, and behavior under load; identify anti-patterns.

**Version scope:** the examples use the `com.datastax.oss.driver.api.*` API of **Java Driver 4.x** and Java 17 in a lab setting. Option names, callback behavior, reactive APIs, exceptions, and policies may vary across minor versions or distributions; check the documentation for the exact driver/JDK/Cassandra combination deployed. Do not use lab code without authentication/TLS as a production configuration.

## 2. `execute` and `executeAsync`: Same CQL, Different Way Java Waits

### 2.1. Common Execution Path

~~~mermaid
sequenceDiagram
    participant API as Java HTTP handler
    participant Driver as CqlSession / Driver
    participant Coord as Cassandra coordinator
    participant Replica as Natural replicas
    API->>Driver: executeAsync(boundStatement)
    Driver-->>API: CompletionStage<AsyncResultSet> (data not yet arrived)
    Driver->>Coord: CQL request
    Coord->>Replica: Read/write by token, RF, and CL
    Replica-->>Coord: Sufficient responses or error
    Coord-->>Driver: Response / first page
    Driver-->>API: Complete stage with AsyncResultSet
    API->>API: currentPage(), process rows
    opt More pages exist and application needs them
        API->>Driver: fetchNextPage()
        Driver->>Coord: Next paging request
        Coord-->>Driver: Next page
        Driver-->>API: Complete next stage
    end
~~~

**What does not change:** the same CQL statement, partition key, clustering range, consistency level, coordinator, and replicas. Async does not turn an `ALLOW FILTERING` query into a cheap partition lookup, does not make SSTables/compaction faster, and does not shrink a quorum.

| API | Result type | Must calling thread wait for data? | Common pitfall |
| --- | --- | --- | --- |
| `session.execute(statement)` | `ResultSet` | Yes, until results arrive under sync semantics. | Iterating `ResultSet` may block while fetching subsequent pages. |
| `session.executeAsync(statement)` | `CompletionStage<AsyncResultSet>` | **No waiting needed** if only creating and composing stages. | Stage completion is usually **one page**, not the entire dataset. |
| `stage.toCompletableFuture().join()` | Completed value or exception | **Yes**, if not yet complete. | Calling it inside a request/event-loop/driver callback can cause stalls. |
| Reactive API (if supported by driver/runtime) | Publisher/stream per reactive contract | Depends on subscription and demand. | Do not equate a single `CompletionStage` with Reactive Streams. |

### 2.2. Non-blocking Does Not Automatically Create More Throughput

`executeAsync` keeps **Java threads from sitting idle waiting on I/O** while Cassandra executes. However, network connections, coordinator capacity, replicas, disk IOPS, tombstone scans, serialization, and heap are still consumed. When the backend is already saturated, increasing the number of futures can drive **latency, memory, and error rates** up together.

What is needed is **non-blocking result composition** while bounding **the amount of work permitted in flight**. The distinction between *not holding a thread waiting* and *not consuming resources* is a core point.

## 3. Lab CQL: A Partition with Multiple Pages

### 3.1. Keyspace and Table

Assume the lab cluster has DC `dc1` with at least three full replicas, schema creation privileges, and properly configured clients:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_async
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_async.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

- `(device_id, event_day)` is a **composite partition key**: Cassandra hashes the key to choose the token and natural replicas; the day bucket helps cap partition size for time-series data.
- `event_time, event_id` are **clustering columns**: rows are ordered within each partition; the ID disambiguates events with the same timestamp.
- `payload` can be large; when an API only needs a timeline, **selecting fewer columns** reduces network traffic and decoding overhead, regardless of sync vs. async.
- `NetworkTopologyStrategy` with `dc1:3` and `LOCAL_QUORUM` requires **two replica responses in dc1**; it does not mean every replica has converged at the same instant.

### 3.2. Sample Data

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'HEARTBEAT', 'ok');

INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'TEMPERATURE', '21.6');

INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:02:00Z',
   123e4567-e89b-42d3-a456-426614174003, 'ALARM', 'high_temp');
~~~

`CONSISTENCY` is a **cqlsh command**, not a statement passed directly into the Java Driver. After inserting the three rows, you can test the query:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

In Java, configuring **page size = 2** lets you observe the case where the first page does not contain all three rows (when Cassandra/the driver applies paging under the corresponding limits). Page size is a **target row count per page**, not a hard byte cap and not `LIMIT`.

## 4. Setting Up Java Driver 4.x and a Shared `CqlSession`

### 4.1. Illustrative Dependency

This Maven example uses the Core Driver 4.x artifact; **the version below is illustrative only and does not imply the latest release**:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.datastax.oss</groupId>
        <artifactId>java-driver-core</artifactId>
        <version>4.17.0</version>
    </dependency>
</dependencies>
~~~

In a real application, align the driver core version with any mapper/metrics/reactive modules used and verify **JDK, Cassandra version, security/TLS, and native protocol** against the release's support matrix.

### 4.2. Session Lives with the Service

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class AsyncSessionLifecycle {
    public static void main(String[] args) {
        // LAB: one long-lived CqlSession per logical cluster/identity.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            // Application issues many executeAsync calls through the same session.
            // Do not create a new session per HTTP request or per page.
            System.out.println("Session ready for async operations");
        }
    }
}
~~~

`CqlSession` manages connections, topology, routing, prepared statements, and driver resources. A typical application should share one session per **logical cluster/identity/configuration** for the process lifetime and close it during controlled shutdown. **Closing a session while an async request is still running** can cause in-flight work to fail; the service should stop accepting traffic, drain/complete requests within a deadline, and then close.

**Production:** enable TLS with server verification, grant a least-privilege CQL role, use a secret manager, configure proper contact points/local DC, never hardcode passwords, and do not give the application unnecessary JMX/OS privileges. The following Java snippets assume **the session has already been initialized securely**.

### 4.3. Prepare the Query Once

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class Queries {
    public static PreparedStatement prepareWindow(CqlSession session) {
        return session.prepare(
            "SELECT event_time, event_id, event_type " +
            "FROM telemetry_async.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");
    }
}
~~~

In a service, retain `PreparedStatement` and reuse it with per-request `BoundStatement` instances. For example, call `prepareWindow` at startup, **not on every request**. When benchmarking async code, separate cold-start/prepare from steady-state request latency.

## 5. `CompletionStage<T>`: A Result That Will Arrive in the Future

`CompletionStage<T>` represents a computation **that can complete normally with a value `T` or exceptionally with an error**. `session.executeAsync(statement)` returns `CompletionStage<AsyncResultSet>`, enabling you to build a downstream pipeline when a page returns without blocking the calling thread.

~~~mermaid
flowchart LR
    A["executeAsync"] --> B["CompletionStage<AsyncResultSet>"]
    B --> C{"Has stage completed?"}
    C -->|Success| D["thenApply / thenCompose"]
    C -->|Error| E["exceptionally / handle / whenComplete"]
    D --> F["CompletionStage<Output>"]
    E --> F
~~~

### 5.1. Key Methods

| Method | Role | Common pitfall |
| --- | --- | --- |
| `thenApply(x -> y)` | **Synchronously transform a value** after the stage succeeds, returning a new stage. | Calling an async query inside and returning a nested `CompletionStage<CompletionStage<T>>`. |
| `thenCompose(x -> nextStage)` | Chain **an asynchronous step that depends on the previous result**, flattening the stage. | Calling `join()` instead of composing, which blocks. |
| `thenCombine(other, (a,b) -> c)` | Combine two independent stages once both succeed. | Firing two unnecessary queries or exceeding the concurrency budget. |
| `whenComplete((value,error) -> ...)` | Observe result/error for metrics or cleanup; normally **preserves the original outcome**. | Treating it as a "catch and recover" handler or blocking in the callback. |
| `exceptionally(error -> fallback)` | Recover with **a fallback value** when the stage fails. | Returning an empty list for all errors, masking `Unavailable` as "no data". |
| `handle((value,error) -> output)` | Handle both success and failure cases. | Swallowing exceptions by unconditionally returning a success value. |
| `toCompletableFuture()` | Convert to a `CompletableFuture` when needed for operations. | Calling `join/get` in an event loop or callback blocks the thread. |

`CompletionStage` **does not mean code automatically switches to a new thread** for each `thenApply`. Callbacks without the `Async` suffix may run on the thread completing the stage or the registering thread, depending on timing/implementation. Therefore, callbacks must stay **fast and non-blocking**.

### 5.2. `thenApply` for Lightweight Value Transformation

~~~java
CompletionStage<Integer> countFirstPage =
    session.executeAsync(statement)
        .thenApply(result -> {
            int rows = 0;
            for (Row ignored : result.currentPage()) {
                rows++;
            }
            return rows;
        });
~~~

This returns **the row count of the current page**, not the query's total row count if `hasMorePages()` is `true`. The snippet belongs inside a method and assumes `CompletionStage`, `Row`, and existing `session/statement` variables are imported/defined.

### 5.3. `thenCompose` for the Next Asynchronous Step

~~~java
CompletionStage<AsyncResultSet> first =
    session.executeAsync(statement);

CompletionStage<AsyncResultSet> nextOrSame =
    first.thenCompose(page -> {
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(page);
        }
        return page.fetchNextPage();
    });
~~~

`fetchNextPage()` already returns `CompletionStage<AsyncResultSet>`; therefore, **`thenCompose`**, not `thenApply`, is the right way to chain a dependent stage. In this example, `nextOrSame` holds **the second page if present**, not all rows from the first page; to aggregate across pages, you must process and accumulate results from prior pages.

### 5.4. Stage Completion Does Not Mean the Application Has Finished All Data

~~~text
executeAsync completes
    -> receives an AsyncResultSet (first page)
    -> application iterates currentPage()
    -> if hasMorePages(), must call fetchNextPage()
    -> application processes final page/results
    -> only then is the full business workflow complete
~~~

When building an API that returns multi-page history, you need **a stage representing the entire chosen workflow**, rather than measuring p99 only up to when `executeAsync` returns the first page.

## 6. `AsyncResultSet`: Current Page and Fetching the Next Page

### 6.1. Main Components

| API | Contents | Accurate interpretation |
| --- | --- | --- |
| `currentPage()` | The `Row` instances of the **current page**. | Does not automatically fetch any subsequent pages. |
| `hasMorePages()` | Indicates whether more pages can be fetched via paging. | `false` means the end of that query's pages, not that the whole cluster is consistent. |
| `fetchNextPage()` | Initiates a query for the next page and returns `CompletionStage<AsyncResultSet>`. | Needs `thenCompose`/pipelining to continue without blocking. |
| `getExecutionInfo()` | Execution metadata for that page (coordinator, warnings, tracing ID if enabled). | Not a full log of every replica. |
| `getColumnDefinitions()` | Schema of the columns returned in the result. | Not the full table schema or entity reflection metadata. |
| `wasApplied()` | Application status for operations with appropriate conditional semantics. | For LWT, inspect `[applied]` and accompanying columns per the statement; do not use it to test whether a read returned rows. |

Do not assume `AsyncResultSet` behaves like synchronous `ResultSet`: `ResultSet` can let an iterator fetch more pages during iteration; with **async**, you explicitly process `currentPage()` and call `fetchNextPage()`.

### 6.2. Example Reading Only the First Page While Flagging More Pages

~~~java
// FirstPageRead.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.concurrent.CompletionStage;

public final class FirstPageRead {
    public static CompletionStage<String> read(
            CqlSession session, PreparedStatement query) {

        BoundStatement statement = query.bind(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                Instant.parse("2026-11-21T10:00:00Z"))
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(2);

        return session.executeAsync(statement)
            .thenApply((AsyncResultSet result) -> {
                int rows = 0;
                for (Row row : result.currentPage()) {
                    rows++;
                    // Read only lightweight metadata; do not block or write files here.
                    row.getInstant("event_time");
                    row.getString("event_type");
                }
                return "first_page_rows=" + rows
                    + " has_more=" + result.hasMorePages();
            });
    }
}
~~~

**Expected behavior on the three lab rows:** the first page typically has two rows when page size is 2 and `hasMorePages()` can be `true`; exact paging behavior depends on the server/driver and data size. The code only produces a **first-page preview**. If an API promises to return up to 100 rows and uses this result, it is **dropping data at the presentation layer**, not Cassandra losing data on disk.

### 6.3. `LIMIT` and Page Size Are Different

~~~text
SELECT ... LIMIT 100
driver page size = 20
=> if enough data exists, the result is typically split across multiple pages.

LIMIT 100       : logical row cap for the entire statement.
page size 20    : target rows/page, not bytes/page.
currentPage()   : only the rows returned in the current page.
fetchNextPage() : requires an additional round-trip with paging state.
~~~

With 100 KiB rows, a 20-row page can carry **around 2 MiB of payload** before overhead; 100 concurrent futures holding large pages can sharply increase heap/direct memory/GC pressure. `LIMIT 100` also does not guarantee a replica scans only 100 physical cells: tombstones, SSTable versions, and clustering ranges can make the number of cells inspected much higher.

## 7. Non-blocking Multi-Page Reads and Bounding Total Work

Returning an entire list of 10 million rows from one `CompletionStage` exhausts the heap even if all I/O is asynchronous. The following example **counts** rows and pages across at most five pages, without retaining a large collection, using a `thenCompose` chain. This is a safe way to understand the mechanics before designing a real streaming API.

~~~java
// LimitedPageScan.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CompletableFuture;

public final class LimitedPageScan {
    public static final class Summary {
        public final int pages;
        public final long rows;
        public final boolean stoppedWithMore;

        public Summary(int pages, long rows, boolean stoppedWithMore) {
            this.pages = pages;
            this.rows = rows;
            this.stoppedWithMore = stoppedWithMore;
        }
    }

    public static CompletionStage<Summary> countUpToFivePages(
            CqlSession session, BoundStatement statement) {
        return session.executeAsync(statement)
            .thenCompose(first -> countPages(first, 1, 0, 5));
    }

    private static CompletionStage<Summary> countPages(
            AsyncResultSet page, int pages, long rows, int maxPages) {

        long accumulated = rows;
        for (Object ignored : page.currentPage()) {
            accumulated++;
        }

        if (!page.hasMorePages() || pages >= maxPages) {
            return CompletableFuture.completedFuture(
                new Summary(pages, accumulated, page.hasMorePages()));
        }

        final long nextRows = accumulated;
        return page.fetchNextPage().thenCompose(
            next -> countPages(next, pages + 1, nextRows, maxPages));
    }
}
~~~

**Why is this code bounded?**

- It only calls `fetchNextPage()` **after finishing** the current page; it does not eagerly fetch hundreds of pages in parallel.
- It does not accumulate `List<Row>` or `List<DTO>` across the entire query, keeping only `rows/pages`.
- `maxPages = 5` creates a **stopping point**; `stoppedWithMore = true` signals it stopped due to the cap while more data remained.
- A **depth-bounded** recursive chain is easy to follow for illustration; if processing millions of pages, use a controlled state machine/publisher rather than unbounded recursion.
- A request still lacks a **total deadline** just because each page has its own driver timeout; the service must enforce an end-to-end workflow deadline.

**Important:** `countUpToFivePages` **is not an exact COUNT of the whole partition** when more pages remain, nor is it a snapshot copy. Do not use the result for full data reconciliation or true total event counts.

### 7.1. When Each Page Must Be Sent Downstream

One architectural option is to receive a page, map it to small DTOs, send it to a consumer with **ack/backpressure**, and only then call `fetchNextPage()`. However, if "sending the page" involves blocking HTTP/file I/O, **do not run it directly inside a callback on the driver I/O thread**; offload CPU-heavy or blocking work to a **separate bounded executor** and return the consumer's completion stage before fetching the next page.

~~~text
fetch page 1
  -> lightweight row processing / DTO mapping
  -> downstream processes page and ACKs
  -> fetch page 2
  -> ... until rows/bytes/deadline limit
~~~

Conversely, `fetch page 2,3,4... in unbounded parallel` to boost throughput can consume heap/connection capacity uncontrollably and fail to preserve the desired display order.

## 8. `thenCompose` vs. `thenApply`: Avoiding Nested Stages

Suppose an API first reads device metadata and then reads events. The second step **depends** on the result of the first step:

~~~java
CompletionStage<DeviceInfo> infoStage = loadDeviceInfo(deviceId);

// CORRECT: thenCompose flattens the CompletionStage returned by readEventsAsync.
CompletionStage<EventPage> pageStage =
    infoStage.thenCompose(info -> {
        if (!info.isEnabled()) {
            return CompletableFuture.completedFuture(EventPage.empty());
        }
        return readEventsAsync(info.getDeviceId(), day);
    });
~~~

In this structural example, `DeviceInfo`, `EventPage`, `loadDeviceInfo`, and `readEventsAsync` are **application-defined types/functions**. Using `thenApply(info -> readEventsAsync(...))` would produce a **stage inside a stage**, making outcome handling and pipelining awkward.

### 8.1. Two Independent Queries and `thenCombine`

If two partitions are independent and the API needs to merge their results, you can write:

~~~java
CompletionStage<EventPage> today = readEventsAsync(deviceId, todayDate);
CompletionStage<EventPage> yesterday =
    readEventsAsync(deviceId, yesterdayDate);

CompletionStage<Timeline> timeline =
    today.thenCombine(yesterday, (a, b) -> mergeByTime(a, b));
~~~

However, **registering two stages does not guarantee sufficient capacity**. If an API fans out across 1,000 days/buckets or 1,000 tenants, you must bound **concurrent queries in flight**, partition count, bytes/page, and total deadline. Results from two queries do not form a **shared atomic snapshot** across the two partitions.

### 8.2. Do Not Block Inside Callbacks

~~~java
// ANTI-PATTERN: waiting on another query right inside a callback.
return session.executeAsync(statement)
    .thenApply(page -> {
        return session.executeAsync(otherStatement)
            .toCompletableFuture()
            .join(); // Can block the thread completing the stage!
    });
~~~

Write `thenCompose(page -> session.executeAsync(otherStatement))` instead, along with validation, timeout/deadline, and concurrency limits. If you need CPU-intensive work, use `thenApplyAsync(..., boundedExecutor)` or a dedicated throttled path; the `Async` suffix **does not guarantee "free threads"**.

## 9. Errors and Outcome Transformation in an Async Pipeline

### 9.1. `whenComplete` for Observation, Not Hiding Errors

~~~java
CompletionStage<AsyncResultSet> observed =
    session.executeAsync(statement)
        .whenComplete((page, error) -> {
            if (error == null) {
                metrics.recordSuccess("read_device_events");
            } else {
                metrics.recordFailure(
                    "read_device_events",
                    error.getClass().getSimpleName());
            }
        });
~~~

`metrics` is a hypothetical application utility; the callback here only increments a lightweight counter/records an event. **Do not log raw CQL containing sensitive data or payloads**. `whenComplete` normally preserves the success/failure of the original stage, making it suitable for instrumentation without masking exceptions.

### 9.2. `exceptionally` and the "Return Empty List" Trap

~~~java
// ANTI-PATTERN: every DB error turns into 'no data'.
CompletionStage<EventPage> unsafe =
    readEventsAsync(deviceId, day)
        .exceptionally(error -> EventPage.empty());
~~~

If Cassandra lacks quorum or credentials are revoked, returning `List.of()` can cause the API to return a misleading 200/404. Only use a fallback when **explicitly defined by business semantics** and backed by metrics/traces—for example, returning a bounded-staleness cache for non-critical data; never turn missing data caused by an error into an apparently valid result.

### 9.3. Handling Error Categories Properly

| Error type | What to inspect | Should you retry? |
| --- | --- | --- |
| `Unavailable` | RF/CL, node/DC, replica health. | Do not retry indefinitely; may need recovery wait or temporary failure response. |
| `ReadTimeout` | Replicas did not respond within timeout; GC/disk/network/tombstones. | Retry only within a budget if the query is safe and deadline allows. |
| `WriteTimeout` | The mutation may have already reached some replicas. | Retry only when keys/mutations are idempotent under business semantics. |
| Driver request timeout | Client deadline, queue, network, and total work. | Do not blindly raise timeouts; measure the root cause. |
| `Unauthorized`/authentication | Role, secret, TLS, and session identity. | Do not keep retrying with bad credentials or switch to superuser. |
| Invalid query/schema | CQL or deployment/schema drift. | Fix the query/schema; do not retry the same input indefinitely. |
| Mapping/codec error | CQL type and Java mapping. | Fix code/codec; do not treat as a replica error. |

**Do not confuse `CompletionException` with the underlying root cause.** Multi-stage `CompletionStage` pipelines can wrap the root cause; unwrap carefully when logging, preserve stack traces, and avoid swallowing errors. Actual exception class names depend on the driver version.

### 9.4. Example of `handle` with Explicit Success/Failure State

~~~java
// A hypothetical Java 17 record:
record ReadOutcome(boolean success, int firstPageRows, String errorType) {}

CompletionStage<ReadOutcome> outcome =
    session.executeAsync(statement).handle((page, error) -> {
        if (error != null) {
            return new ReadOutcome(
                false, 0, error.getClass().getSimpleName());
        }
        int rows = 0;
        for (Row ignored : page.currentPage()) {
            rows++;
        }
        return new ReadOutcome(true, rows, "");
    });
~~~

`handle` **converts an error into a stateful value**; callers must actually check `success`. If the API needs the exception to propagate so the infrastructure returns an appropriate error response, keep the stage failed rather than unconditionally converting it to a success-looking object.

## 10. `executeAsync` on Writes: Success, Timeouts, and Idempotency

Async reads and async writes share the same API shape, but **write timeouts carry distinct correctness risks**. Cassandra may have already applied the mutation on some replicas before the driver or coordinator reports a timeout. Therefore:

~~~text
Async INSERT sent
  -> coordinator forwards mutation to natural replicas
  -> one or more replicas may have already written
  -> insufficient ACKs arrive before deadline
  -> stage completes exceptionally
Do not assume: "stage failed" == "no replica wrote".
~~~

### 10.1. Stable Event Keys Across Every Retry

For the lab table:

~~~sql
INSERT INTO telemetry_async.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (?, ?, ?, ?, ?, ?);
~~~

`(device_id, event_day, event_time, event_id)` is the full primary key; if the producer supplies an **immutable event ID**, resending the *exact same values* avoids creating **duplicate rows from newly generated IDs**. However:

- If payloads/updates compete, Cassandra's write timestamp determines the winner under mutation semantics, not the domain event time.
- If `USING TTL` or a default TTL is used, rewriting can **extend the time to live**.
- With `counter`, LWT, or multi-table workflows, retries have different contracts; do not label every statement idempotent.
- A request receiving `WriteTimeout` needs proper **reconciliation or durable retry**, not `exceptionally(error -> success)`.

### 10.2. Java: Admission Control Before Calling the Driver

This is a **fail-fast when out of slots** pattern for a lab event writer class. It allows at most 32 concurrent Cassandra requests **within one instance of the object**, avoids unbounded queues, and releases the slot whether the stage succeeds or fails.

~~~java
// BoundedAsyncWriter.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

public final class BoundedAsyncWriter {
    public record Event(
            String deviceId, LocalDate day, Instant time,
            UUID id, String type, String payload) {}

    private final CqlSession session;
    private final PreparedStatement insert;
    private final Semaphore permits = new Semaphore(32);

    public BoundedAsyncWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO telemetry_async.events_by_device_day " +
            "(device_id, event_day, event_time, event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)");
    }

    public CompletionStage<UUID> insertAsync(Event event) {
        // Do not block event-loop/request threads when all slots are busy.
        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new RejectedExecutionException("DB concurrency limit"));
        }

        try {
            BoundStatement statement = insert.bind(
                    event.deviceId(), event.day(), event.time(),
                    event.id(), event.type(), event.payload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            return session.executeAsync(statement)
                .thenApply(ignored -> event.id())
                .whenComplete((id, error) -> permits.release());
        } catch (RuntimeException dispatchError) {
            // Includes bind/dispatch errors occurring before a stage is created.
            permits.release();
            return CompletableFuture.failedFuture(dispatchError);
        }
    }
}
~~~

**Key points about the sample:**

1. `Semaphore.tryAcquire()` makes an immediate **accept or reject** decision; it does not place requests into an endless queue. At the API layer, `RejectedExecutionException` should map to an appropriate overload response, not 404.
2. `whenComplete` returns the slot when the stage finishes **either successfully or with an error**; the callback stays lightweight and never blocks driver I/O.
3. `PreparedStatement` is prepared once. `BoundStatement` is created per request with a caller-supplied stable key.
4. The limit of 32 is scoped to the **writer instance**; creating a writer per request defeats the limit. Keep a writer tied to the service lifecycle or a shared workload gate.
5. It does not blindly enable retries/speculative execution; retries require proven idempotency and a retry budget.
6. The example omits a durable queue, mutation checkpointing, cancellation, and global rate limiting. Production must address what happens if the process crashes after a write is sent but before an ACK is received.
7. Do not treat `MAX_IN_FLIGHT=32` as universal advice. Benchmark against actual pod count, replica count, page size, payload size, and SLOs.

### 10.3. One Stage per Statement Is Not a Workflow Transaction

~~~java
CompletionStage<?> writeA = session.executeAsync(statementA);
CompletionStage<?> writeB = session.executeAsync(statementB);
~~~

Those two writes can succeed or fail independently; `thenCombine` or `allOf` only **awaits the Java results**, without turning them into an atomic cross-table/cross-partition transaction. If an event must populate two tables serving two queries, you need a **durable mutation log, dual-write reconciliation/CDC, or an appropriate business consistency mechanism**.

## 11. Backpressure: API, Driver, and Cassandra Must Share a Budget

Overload cannot be solved by "calling async as fast as possible." To keep the system controlled, distinguish **three queueing layers**:

~~~mermaid
flowchart TD
    A["HTTP / queue consumer"] --> B{"Admission: budget available?"}
    B -->|No| X["429/503/defer per contract"]
    B -->|Yes| C["App concurrency gate"]
    C --> D["Java Driver throttler / connection pools"]
    D --> E["Coordinator request queues"]
    E --> F["Replica disk/GC/compaction"]
    F --> G["Stage success / failure"]
    G --> H["Release app permit, update metrics"]
~~~

| Layer | Typical limits | Mistake |
| --- | --- | --- |
| **Gateway/API** | Concurrent user requests, request size, deadline. | Accepting unlimited requests and letting them wait in the heap. |
| **Worker/consumer** | Poll batch size, concurrency, durable offset/ack. | ACKing messages before mutations have outcomes/durable retry paths. |
| **Java app** | Semaphore, bounded executor queue, per-tenant/query budgets. | Calling `join()` or `Thread.sleep()` inside callbacks. |
| **Driver** | Request throttler, in-flight limits, pooling, request timeout/retry. | Increasing queues/pools when replicas are already saturated. |
| **Cassandra** | Coordinator queues, CL deadlines, disk/GC, guardrails. | Loosening server timeouts to hide bad CQL/query models. |

### 11.1. In-Flight Is Not Connection Count

The Cassandra native protocol allows **multiple requests to be multiplexed over a single connection**. One `CqlSession` manages connection pools to nodes; each `executeAsync` does not open a separate connection.

If a service runs 25 pods, each allowing up to 40 in-flight statements:

~~~text
Theoretical gate ceiling: 25 × 40 = 1,000 concurrent statements

Not yet counting:
  - requests from other services
  - retries or speculative attempts
  - batch/backfill jobs
  - multi-partition fan-out per API call
~~~

This is the **number of statements awaiting completion**, not 1,000 TCP connections or 1,000 statements/s. Adding connections to the pool when disk/replicas are bottlenecked usually just pushes more load into the bottleneck.

### 11.2. Little's Law for Spotting Queue Risk

In steady state:

~~~text
L ≈ λ × W
L = average number of in-flight requests
λ = completion throughput per second
W = average residence time (seconds)

Example at 800 CQL statements/s:
  mean W = 0.05 s -> L ≈ 40
  mean W = 0.50 s -> L ≈ 400
~~~

When latency increases 10x at the same arrival rate, the number of incomplete requests can surge sharply. During overload, however, the system may not be in steady state; **do not plug p99 into the formula as if it were mean W**. Measure actual queue age, in-flight count, and completion rate.

### 11.3. A Bounded Queue Is Not the Same as Dropping All Load

Bounding queues/in-flight work does not make Cassandra faster immediately; it **protects against runaway collapse** and gives the system room to recover. If data cannot be lost, overload from Kafka/message brokers must be paired with **pausing consumption, not ACKing before durable outcomes, retry/DLQ, and offset tracking**—not simply "dropping events".

## 12. AsyncResultSet and Reactive Streams: Related, Not Identical

The chapter is titled "Async and Reactive", yet **`CompletionStage<AsyncResultSet>` is not a `Publisher<Row>`**. The two programming models differ in key ways:

| Characteristic | Async Core (`executeAsync`) | Reactive Streams / driver reactive API if supported |
| --- | --- | --- |
| Result | Stage for a single `AsyncResultSet` page. | Publisher/subscriber processing a stream of results per subscription. |
| Flow signal | `hasMorePages` + `fetchNextPage`. | `request(n)`/demand, `onNext`, `onError`, `onComplete`. |
| Backpressure | Application decides when to fetch the next page and how many workflows stay in flight. | Expressed via **demand** over the reactive protocol; still needs a concurrency policy. |
| Mapping | `thenApply`, `thenCompose`, transforming `Row`/pages. | Stream operators per compatible framework/reactive API. |
| Errors | Exceptional completion of the stage. | Terminal `onError` or publisher semantics. |
| Read boundary | Explicit page-level boundary. | Framework may hide paging; must measure actual requests/pages/bytes. |

Some versions of Java Driver 4.x provide a **reactive execution API** integrated with Reactive Streams. When using Reactor/RxJava or similar frameworks, check **version-specific methods/return types and demand behavior**. Do not write:

~~~java
// SEMANTICALLY WRONG: one stage of the first page != a stream of every row.
Mono.fromCompletionStage(session.executeAsync(statement))
    // This Mono emits a single AsyncResultSet; it does NOT automatically
    // emit every Row across all pages as a Flux<Row>.
~~~

This snippet is **a conceptual illustration, not a complete Java class**. To produce a `Flux<Row>`, you must build a pipeline that **calls `fetchNextPage` in order and according to demand**, or use the driver's verified reactive API. A `Flux` wrapped around an already-materialized huge `List` has no real end-to-end backpressure during the fetch phase.

### 12.1. Reactive Does Not Make Resources Free

If a subscriber calls `request(Long.MAX_VALUE)` or uses a `flatMap` with excessive concurrency, the backend can still receive more work than it can handle. Even with a Publisher, you must still:

- Bound concurrency, demand, and buffers by **bytes/rows**.
- Set overall timeouts/deadlines and handle cancellation.
- Be careful with `collectList()` or `block()` on an event loop.
- Keep queries bounded by partition/range and avoid rampant `ALLOW FILTERING`.
- Measure memory/GC and actual read operations on Cassandra.

**Key distinction:** async removes blocking waits from threads; reactive is a model for composing and applying demand to a **stream**. Both require overload control.

## 13. Deadlines, Timeouts, and Cancellation Across Multiple Pages

### 13.1. Multiple Clocks Exist

| Timer | Scope | Typically covers |
| --- | --- | --- |
| **API deadline** | End-to-end business operation from request entry. | Admission, multiple CQL statements, paging, mapping, and HTTP serialization. |
| **Driver request timeout** | Request/attempt per driver version semantics. | Waiting for Cassandra to respond to a single driver operation. |
| **Coordinator read/write timeout** | Cassandra request at the coordinator. | Waiting for replicas matching CL, depending on query type. |
| **Per-page latency** | Each page fetch. | Network + coordinator/replica work for that page. |
| **Downstream timeout** | Delivering pages/DTOs to another system. | Internal network/API or application I/O. |

Suppose each page takes 250 ms, and an endpoint must read **10 pages** sequentially. A 2-second driver timeout per page (depending on implementation) **does not mean the whole endpoint finishes within 2 seconds**. Even when every page succeeds, total time can exceed 2.5 seconds before counting queueing and mapping.

### 13.2. `orTimeout` Is Not a Command to Cancel Replica Work

Java 17 allows attaching a timeout to a `CompletableFuture`:

~~~java
// Illustration; TimeUnit/CompletableFuture require corresponding imports.
CompletableFuture<AsyncResultSet> firstPage =
    session.executeAsync(statement).toCompletableFuture();

firstPage.orTimeout(800, TimeUnit.MILLISECONDS);
~~~

This bounds **how the Java-side future completes/is observed** per the Java API; it **does not guarantee the coordinator/replicas immediately stop work**. Nor does it automatically create a single shared deadline for subsequent `fetchNextPage()` stages launched later. Production code should maintain a **unified deadline timestamp**, check it before dispatching each page, and release resources/admission permits on completion.

### 13.3. Cancellation in an Async Pipeline

If the HTTP client disconnects:

1. The application can **stop calling `fetchNextPage()`**; this is the most direct way to avoid dispatching unneeded work.
2. A request already sent to Cassandra **may still be running** even if the client-side future is cancelled or timed out; do not assume atomic server-side cancellation.
3. Release **app permits, timeout state, and downstream subscriptions** on completion/cancellation/error paths as appropriate.
4. For writes, cancellation **does not mean data was not written**; reconcile if the mutation outcome matters.

### 13.4. Budgets by Rows, Bytes, Pages, and Time

~~~text
API query budget (example):
  maximum buckets            = 3
  maximum rows in response   = 200
  maximum pages to fetch     = 10
  maximum serialized bytes   = 2 MiB
  total request deadline     = 700 ms
  concurrency per instance   = 40
  queue limit                = 80
~~~

These numbers are illustrative only; **row-based page size does not guarantee a byte cap**, and the deadline must include waiting time. A table with very large payloads needs limits at the data model and application layers, not just client page size.

## 14. `ExecutionInfo`, Tracing, and Per-Page Observability

`AsyncResultSet.getExecutionInfo()` can report the coordinator and warnings for the corresponding request, as well as the trace ID if tracing is enabled. When multiple pages exist, **each page can have its own execution info**, and inspecting one page does not describe the whole workflow.

~~~java
// Inside a thenApply callback for AsyncResultSet:
var info = page.getExecutionInfo();
var coordinator = info.getCoordinator();
var warnings = info.getWarnings();
var traceId = info.getTracingId();

System.out.println("coordinator="
    + (coordinator == null ? "unknown" : coordinator.getEndPoint())
    + " warnings_count=" + warnings.size()
    + " tracing_id=" + traceId);
~~~

This is an **observability example for the lab**; do not `System.out.println` every row/page in production, as logging can become a bottleneck or leak metadata. `getTracingId()` is usually unset when tracing is disabled; do not infer "null means the driver dropped data." Check exact getter names and return types against your Java Driver version.

### 14.1. Useful Metrics for Async Paging

| Metric | Why it is needed |
| --- | --- |
| API end-to-end p50/p95/p99 | Reflects the user SLO, including multiple pages and Java processing. |
| First-page latency | Shows time to first data; does not represent full-result latency. |
| Full-consume latency | Shows time to finish iterating the needed rows. |
| Pages fetched/request | Detects endpoints accidentally reading too many pages. |
| Rows/bytes decoded/request | Detects large payloads and poorly tuned page sizes. |
| In-flight stages/driver requests | Detects client-side or coordinator overload. |
| Permit wait/rejections | Measures admission/backpressure effectiveness. |
| Driver retries/errors/throttler backlog | Detects retry storms or growing client queues. |
| Java heap, allocation, GC pauses | Detects callbacks/DTOs/lists driving up memory and p99. |
| Cassandra read/write latency, `tpstats`, disk, tombstones | Distinguishes server bottlenecks from the async pipeline. |

**Do not average per-node p99s as the cluster-wide p99.** Tag metrics by `query_name`, `environment`, `local_dc`, `status`, and `profile`—never use `device_id`, `event_id`, or request UUIDs as unbounded-cardinality labels.

### 14.2. Trace Only Sample Queries

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

Tracing helps inspect coordinator/replica execution and the timing of Cassandra processing steps. It **does not directly measure** Java `thenApply` time, mapping CPU, heap allocations, or time spent waiting on an application semaphore. Enabling tracing on all traffic when a cluster is overloaded adds extra overhead.

### 14.3. `nodetool` Alongside Client Metrics

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_async.events_by_device_day
~~~

Distinguish what each shows: `status` shows membership, not whether replicas still have headroom; `tpstats` shows queues/dropped tasks, not the answer to every timeout; `compactionstats` shows only part of I/O pressure; correlate logs/metrics/traces on a **UTC timeline** against a baseline.

## 15. A Range Spanning Two Day Buckets: Composition Without an Atomic Snapshot

A daily query is a single-partition lookup, but an API sometimes needs a range from 23:45 UTC the previous day to 00:15 UTC the next day. The application must read **two partitions**:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:45:00Z'
  AND event_time < '2026-11-21T00:00:00Z';

SELECT event_time, event_id, event_type
FROM telemetry_async.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-21T00:15:00Z';
~~~

From Java, you can issue two `executeAsync` calls within your concurrency budget and use `thenCombine` to merge by `event_time` and `event_id`, bounding rows/bytes. However:

1. **Bucket correctness:** `event_day` must be derived using the same UTC convention. `LocalDate.now()` in server local timezone is not necessarily the UTC day of `event_time`.
2. **Ordering:** Cassandra only sorts within each partition; merging in Java must define a consistent tie-breaker.
3. **Consistency:** two SELECTs at two instants **are not a distributed transactional snapshot**.
4. **Deadlines:** if one branch is slow, the combined `thenCombine` waits; enforce a time budget and a clear policy for partial results vs. errors.
5. **Bounded fan-out:** for a 5-year request, do not fire 1,826 daily futures in parallel without limits. Bound the window and/or use an appropriate projection/rollup table.

**Async does not replace data modeling**: a hot or oversized partition will remain a bottleneck no matter how lightweight the Java callbacks are.

## 16. Availability and Consistency Levels for Async Requests

### 16.1. CL Is Response Count, Not "Async Consistency"

With `NetworkTopologyStrategy {'dc1': 3}`:

| Consistency level | Local DC replicas required to respond (RF=3) | Typical impact |
| --- | --- | --- |
| `LOCAL_ONE` | One full replica. | Lower latency in many cases, but visibility of recent writes depends on replication/repair. |
| `LOCAL_QUORUM` | Two full replicas in dc1. | Tolerates one unavailable full replica within the DC for appropriate operations/partitions. |
| `ALL` | All three full replicas for a dc1-only keyspace. | Sensitive to any single unavailable replica; unsuitable for many workloads. |

With multiple DCs, `ALL` requires responses across all replicas participating in the operation and can depend on remote DCs; `LOCAL_QUORUM` considers only the local DC. Behavior with transient replication/operation types/versions can vary; the table above applies specifically to the **three full replicas in one DC** example.

**Do not call `LOCAL_ONE` "asynchronous" or `LOCAL_QUORUM` "synchronous"**. `executeAsync` is **how Java waits on I/O**, whereas CL determines what level of replica acknowledgment the coordinator requires. The two axes are completely independent.

### 16.2. Retries and Speculative Execution in Async

Some driver policies may retry requests or issue speculative attempts depending on configuration and idempotence flags. This can increase the actual requests sent to Cassandra compared to the number of `executeAsync` calls in application code. Therefore:

- **Measure retries/speculative attempts** and per-node traffic; do not count only HTTP requests.
- Do not treat every `INSERT`/counter/LWT as idempotent in the same way.
- A read timeout may be retried if permitted by policy, but retrying when disk/GC is overloaded can create a **load amplification loop**.
- Do not enable speculative execution across all traffic just to shave p99 in a short benchmark.

### 16.3. Do Not Silently Downgrade CL on Errors

If a `LOCAL_QUORUM` request returns `Unavailable`, silently switching to `LOCAL_ONE` "just to return 200" **alters the consistency contract**. Only consider CL downgrade when explicitly permitted by business and policy requirements, with monitoring/auditing and assessment of stale-read risk. Raising driver timeouts cannot bring back a missing replica either.

## 17. Case Study: Reading Only the First Page and Returning Missing Events

### 17.1. Symptom

A Java API was migrated from:

~~~java
ResultSet result = session.execute(bound);
for (Row row : result) {
    // consumes across needed pages
}
~~~

to:

~~~java
session.executeAsync(bound).thenApply(result -> {
    List<EventView> values = new ArrayList<>();
    for (Row row : result.currentPage()) {
        values.add(EventView.from(row));
    }
    return values;
});
~~~

The bottom code is **a snippet inside a service, not a complete class**; `EventView` is an application DTO and `from` is a hypothetical mapping helper.

In a dev environment with three rows and page size 100, both versions returned the same result. In production, each partition has thousands of rows with page size 100. The async API **only returns up to the rows in the first page** and silently drops the rest.

### 17.2. Why Is This Bug Hard to Spot?

| Observation | Premature conclusion | Accurate explanation |
| --- | --- | --- |
| Async query succeeds with no exception. | "Cassandra returned everything." | The stage only completed for the **first page**. |
| CQL `LIMIT 500` returns 100 rows. | "The replica is missing 400 rows." | More pages remain unfetched; check `hasMorePages`. |
| `nodetool status` shows all `UN`. | "No issue remains." | Cluster membership does not fix client pagination bugs. |
| Enabling `LOCAL_QUORUM` still returns 100 rows. | "Consistency is too weak." | CL does not replace `fetchNextPage`. |
| Raising page size to 500 makes dev/prod return all rows. | "Completely fixed." | Only **masks the bug** until results exceed page size, while increasing bytes/GC. |

**Root cause:** the old code relied on the synchronous iterator's automatic paging, while the async code only iterated `currentPage()` and finished. **The fix** is to explicitly fetch subsequent pages with `thenCompose` or use a reactive API with proper demand, while defining overall limits/deadlines and testing across multiple pages.

### 17.3. Required Test Cases

1. Create lab data with **more rows than the page size**.
2. Run a `LIMIT 100` query with page size 2 and a pipeline that reads all results.
3. Verify the **set of event IDs, ordering, and row count** against the CQL query.
4. Compare the first and last pages; verify `hasMorePages` is handled.
5. Verify the API does not read endlessly when the client only requests 20 rows.
6. Measure memory/GC and request counts as page size decreases or payload size grows.

## 18. Integrated Lab: Reading All Three Rows While Blocking Only at the CLI Boundary

The example below uses `CompletionStage` to read all pages of a **lab query with LIMIT 10**. It collects `UUID` values into a list solely because the result set is tiny and tightly bounded. In a CLI test or experimental runner, **waiting at the `main` boundary** is acceptable so the program does not close `CqlSession` before the stage completes. Never put this kind of `get()` inside callbacks, request handlers, or event loops.

~~~java
// AsyncPagingLab.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public final class AsyncPagingLab {
    private static CompletionStage<List<UUID>> collect(
            AsyncResultSet page, List<UUID> eventIds) {
        for (Row row : page.currentPage()) {
            eventIds.add(row.getUuid("event_id"));
        }
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(eventIds);
        }
        return page.fetchNextPage().thenCompose(
            next -> collect(next, eventIds));
    }

    public static void main(String[] args) throws Exception {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_id FROM telemetry_async.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? LIMIT 10");

            BoundStatement query = prepared.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(2);

            CompletionStage<List<UUID>> pipeline =
                session.executeAsync(query)
                    .thenCompose(first -> collect(first, new ArrayList<>()));

            // ONLY at the main/test boundary: wait for a bounded async workflow.
            List<UUID> actual = pipeline.toCompletableFuture()
                .get(10, TimeUnit.SECONDS);

            if (actual.size() != 3) {
                throw new IllegalStateException(
                    "Expected 3 sample rows, got " + actual.size());
            }
            System.out.println("ASYNC_PAGING_OK rows=" + actual.size());
        }
    }
}
~~~

**Scope of the example:** it assumes the lab table holds only **three rows in that day's partition** inserted in section 3; if other test data exists, `actual.size() == 3` is no longer the right expectation. `get(10, TimeUnit.SECONDS)` only limits the CLI wait time; on timeout, you must still understand **cancellation and driver resources** for your implementation rather than assuming the server stops immediately.

### 18.1. Why Not Use This `collect()` in Production for Unbounded Queries?

- It retains every `UUID` in an `ArrayList`; across millions of rows this can exhaust the heap.
- The recursion has no separate page cap beyond the query's `LIMIT 10`; do not copy this pattern for unbounded `SELECT` statements.
- It lacks per-page logging/metrics, a global deadline, admission/backpressure, and API cancellation.
- Multi-page snapshot immutability **is not guaranteed** under concurrent writes/deletes.

To process large results, use the **bounded page processor/consumer** from section 7, holding one reasonably sized page at a time and fetching the next page only after downstream finishes processing. If you need cluster-scale data export, use an appropriate batch/token-range/backup architecture rather than scanning all partitions from a single API query.

## 19. Case Study: Converting Everything to `executeAsync` and Running Out of Heap

**Simulated context:** 16 Java instances, each receiving 400 API requests/s. Each API call generates three `SELECT` queries by day bucket, fires `executeAsync` immediately, and collects all rows into a `List`. Some queries fetch 100 KiB `payload` columns; Cassandra is running compaction, causing latency to rise.

| Milestone | Observation | Interpretation |
| --- | --- | --- |
| Before change | Sync requests held many threads; p99 was high, but in-flight request count was naturally capped by the thread pool. | There was a thread-waiting/resource issue needing improvement. |
| After change | Waiting threads dropped, while in-flight futures surged. | Removed an implicit bound without replacing it with admission control. |
| During compaction | Mean DB latency increased, so requests lived longer. | In-flight count grew at the same arrival rate. |
| As pages returned | Hundreds of large-payload pages were held in `List` instances simultaneously. | Severe heap/GC pressure. |
| After retries | Driver/gateway issued extra attempts. | Risked creating a retry storm against congested replicas. |
| Incident | OOM or multi-fold p99 spike. | "Async" alone was not the culprit; **unbounded work** was the design flaw. |

### 19.1. Wrong Reaction

**Increasing heap, raising connection counts, raising timeouts, and lowering CL** without measuring, while still accepting unlimited requests and buffering all rows. This may delay the OOM slightly, but degrades the backend and SLOs further.

### 19.2. Evidence-Based Response

1. **Shed/throttle incoming traffic** and pause batch/backfill jobs if needed so the cluster can recover.
2. Measure `in_flight`, admission queue, rejected requests, retry count, pages/request, and response bytes.
3. Correlate client p99 with `nodetool tpstats`, compaction, disk await, GC, and server timeouts.
4. Fix the code to **bound concurrent statements**, stop buffering unbounded `List` collections, and fetch the next page only when downstream is ready.
5. Check that `SELECT` specifies the full partition key, time bucket, and column projection; drop unneeded `payload`/bytes.
6. Set an overall deadline, retry budget, and clear error contract: overload is a temporary failure, not an empty result.
7. Load test on staging with realistic data shapes/peaks and chaos scenarios, then canary a few instances with rollback ready.

**Takeaway:** async changes the thread-holding model, not **work/byte/replica limits**. When migrating from sync to async removes a thread pool's implicit concurrency cap, you must replace it with **explicit admission/backpressure**.

## 20. Configuration, Testing, and Rollout for Async Applications

### 20.1. Driver Options to Consider

This HOCON example is illustrative for Java Driver 4.x, **not a recommended set of production defaults**:

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }
  advanced.connection.pool {
    local.size = 1
  }
  advanced.request-throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 200
    max-queue-size = 400
  }
}
~~~

**Read this carefully:** the driver's request throttler does not replace **app-level admission**; `local.size` is a pool parameter rather than the in-flight statement count; the request timeout is a client-side deadline within driver scope, not a substitute for server read/write timeouts. Option names, class availability, and reload behavior must be verified for your exact version. If a config file is not loaded or a class does not exist, **do not assume the system is rate-limited** just because those lines are in the file.

### 20.2. Environment Separation

| Aspect | Dev | Staging | Production |
| --- | --- | --- | --- |
| Cluster/DC | Dedicated lab with DC matching snitch. | Mirrors RF/CL and failure modes close to production during tests. | Real DC/rack/seeds/routing, strict network policy. |
| Credentials | Least-privilege lab identity. | Separate staging identity. | Dedicated service identity, secret manager, and rotation. |
| TLS | Test with proper certificates/CA. | Full TLS/hostname verification and failover tests. | Peer-verified TLS, auditing, isolated JMX/OS protection. |
| Page/concurrency | Small, easy to trigger multi-page flows. | Load test with real or simulated row sizes/tombstones. | SLO/capacity-driven, global budget and dashboards. |
| Timeout/retry | Easy to debug, no error masking. | Test GC/disk/replica down and cancellation. | Monitored deadline/retry budgets and controlled rollout. |

**Never share production secrets or production contact points with dev/staging.** A `CqlSession` built from the wrong environment config can query the wrong cluster even with valid CQL; verify **cluster identity, keyspace, local DC, auth role, and TLS** before serving traffic.

### 20.3. Essential Test Matrix

| Test | Input | Expected outcome |
| --- | --- | --- |
| First page | Three rows, page size 2. | May receive fewer than total; do not conclude data is missing. |
| Multi-page | Enough rows to exceed page size. | Uses `fetchNextPage`, matching key set and order. |
| Zero rows | Partition with no live rows. | Stage succeeds with empty result; distinct from exceptions. |
| Partial final page | Row count not divisible by page size. | Does not fetch endlessly; `hasMorePages` stops cleanly. |
| Driver timeout | Controlled slow response in lab. | Future fails, does not report 404, slot is released. |
| Replica down | RF/CL satisfied or violated depending on scenario. | Distinguishes `Unavailable`/timeout and observes retries. |
| Write timeout | Uncertain outcome after send. | Does not generate a new `eventId` on retry; has reconciliation. |
| Callback error | Mapper/parser throws an exception. | Downstream stage fails; permit is not leaked. |
| Overload | Exceeds 32-request gate. | Requests over budget are rejected; no unbounded queue. |
| Client disconnect | Read cancelled before next page. | Stops fetching further pages if unneeded; does not assume server stops immediately. |
| Large pages | Large row payloads, high concurrency. | Heap/GC bounded, bytes/page metrics and deadlines reasonable. |
| Paging during mutations | Updates/deletes between pages. | Does not claim snapshot consistency. |
| Bad auth/TLS | Expired credentials/CA, role lacks SELECT. | Clear error; no infinite retries or trust-all. |

### 20.4. Controlled Tuning Workflow

~~~mermaid
flowchart TD
    A["Prepare sync-to-async migration"] --> B["Finalize API deadline, rows/bytes, CL/RF, and SLO"]
    B --> C["Design admit/queue/in-flight and error contract"]
    C --> D["Test multi-page, timeout, cancel, and uncertain writes"]
    D --> E["Staging load test: CPU/GC/driver/server metrics"]
    E --> F{"Correctness and p99 met?"}
    F -->|No| G["Fix CQL/paging/backpressure, retest"]
    G --> D
    F -->|Yes| H["Canary a small pod group with rollback flag"]
    H --> I["Monitor retries, pages, queues, disk, p99"]
    I --> J{"Any regression?"}
    J -->|Yes| K["Shed load / controlled rollback"]
    J -->|No| L["Expand rollout, record post-check"]
~~~

## 21. Anti-Patterns to Avoid

| Anti-pattern | Why it is wrong | What to do instead |
| --- | --- | --- |
| `executeAsync(...).toCompletableFuture().join()` in a reactive HTTP handler. | **Blocks the thread**, losing async benefits; can stall the event loop. | Return the stage/publisher and compose into the response. |
| `thenApply(page -> fetchNextPage())` without flattening. | Nested stage and improper result handling. | Use `thenCompose`, processing the current page before the next. |
| Iterating only `currentPage()` and claiming all rows were read. | Skips remaining pages when `hasMorePages` is true. | Fetch remaining pages or explicitly promise a preview API. |
| `collectList()` over a multi-TB table. | OOM/GC, destroying end-to-end backpressure. | Bound scope, pages, consumer rate, and bytes. |
| Calling `executeAsync` without limits because "it doesn't block". | App futures, driver queues, and replicas still overload. | Admission control + bounded concurrency + global budget. |
| Blocking file/HTTP/heavy CPU inside driver callbacks. | Holds completion threads, hurting other requests. | Bounded separate executor or async downstream. |
| Catching all errors with `exceptionally(e -> emptyList)`. | Timeouts/Unauthorized become false empty data. | Propagate errors and map per API contract. |
| Retrying write timeouts with a new random event ID. | Can create logical duplicates. | Stable keys, idempotency, and reconciliation. |
| Only raising driver timeouts when p99 rises. | Fails to fix tombstones/disk/GC/down replicas. | Measure driver/client/server and fix the root cause. |
| Silently downgrading `LOCAL_QUORUM` to `LOCAL_ONE`. | Breaks the consistency contract. | Only if business-approved, explicitly audited, and observed. |
| Assuming future cancellation cancels an `INSERT` on the server. | Client cancellation does not guarantee the mutation was not applied. | Handle unknown outcomes and reconcile. |
| Assuming `CompletionStage` provides Reactive Streams backpressure. | A stage has no `request(n)` semantics. | Use page-level gating or an appropriate reactive Publisher. |
| Creating a new `CqlSession` per future. | Connection churn, TLS/auth/metadata overhead. | Reuse session and prepared statements. |
| Using `ALLOW FILTERING` and cranking up concurrency. | Turns one expensive scan into many parallel expensive scans. | Design partitions/projections for the query. |
| Measuring only first-page latency. | Hides multi-page fetch and mapping costs. | Measure full-consume/API latency, pages, and bytes. |

## 22. Exercises with Answers

**Exercise 1.** What type does `executeAsync` return in Java Driver 4.x? Why should you avoid calling `join()` immediately in an HTTP event loop?

**Answer:** It returns `CompletionStage<AsyncResultSet>`. `join()` blocks the thread if the stage is not yet complete; use composition/continuations and let the framework await completion asynchronously.

**Exercise 2.** With three lab rows and page size 2, `currentPage()` returns two rows. Did Cassandra lose the third row?

**Answer:** **No.** The first page is not the whole query. Check `hasMorePages()` and call `fetchNextPage()` to retrieve the rest.

**Exercise 3.** Why is `thenCompose(page -> page.fetchNextPage())` better than `thenApply(...)`?

**Answer:** Because `fetchNextPage()` itself returns `CompletionStage<AsyncResultSet>`; `thenCompose` flattens the dependent stage and returns the stage type of the next page, avoiding nested stages.

**Exercise 4.** How does `whenComplete` differ from `exceptionally`?

**Answer:** `whenComplete` mainly observes the outcome for logging/metrics/cleanup and normally preserves the original error; `exceptionally` **replaces an error with a fallback value** and can mask failures if it blindly returns empty results.

**Exercise 5.** An API handles 100 requests, each returning 20 pages. The code only times the initial `executeAsync`. Has it measured full API latency?

**Answer:** **No.** It only measured up to the first page; you must measure all 19 subsequent fetches, mapping, downstream delivery, and response serialization.

**Exercise 6.** A service has 20 pods, each allowing up to 50 in-flight statements. What is the theoretical service-wide ceiling?

**Answer:** `20 × 50 = 1,000` concurrent statements, excluding retries/speculative attempts and other services; it is **not** 1,000 TCP connections.

**Exercise 7.** With RF = 3 in dc1, how many replicas must respond for `LOCAL_QUORUM`?

**Answer:** **Two** full replicas in dc1. Switching from `execute` to `executeAsync` does not change the replica count required by CL.

**Exercise 8.** An async `INSERT` returns `WriteTimeout`. Can you safely generate a new `eventId` and retry without risking duplicates?

**Answer:** **No.** The earlier mutation may have already been applied by some replicas; retrying with a new ID can create a duplicate. Use stable keys and an appropriate idempotency/reconciliation policy.

**Exercise 9.** A reactive consumer uses `collectList()` to buffer 10 million rows before returning a response. Has it leveraged full-stream backpressure?

**Answer:** **Not at output memory level** if it retains all the data. Publisher demand cannot bound heap usage if the consumer itself accumulates everything. Apply scope/byte/page caps and consume incrementally.

**Exercise 10.** Does `CompletableFuture.orTimeout(800ms)` guarantee replicas stop running the query at 800ms?

**Answer:** **No.** It affects the Java-side future; work on the coordinator/replicas may continue per server semantics. The application must stop requesting more pages and handle uncertain state for writes.

**Exercise 11.** If a query runs `SELECT ... LIMIT 100` with page size 20, will every page always contain exactly 20 rows and 20 KiB?

**Answer:** **No.** Page size targets **row count**, not bytes; the final page can have fewer rows, row sizes vary, and the server/driver have their own limits.

**Exercise 12.** Two `executeAsync` statements write to two tables, followed by `thenCombine` waiting for both. Is this an atomic transaction?

**Answer:** **No.** `thenCombine` only combines the Java outcomes. The two mutations can succeed or fail independently; use durable retry/reconciliation or another business consistency mechanism.

**Exercise 13.** A `thenApply` callback parses 10 MB of JSON and writes a file synchronously inside the callback. What is the risk?

**Answer:** The callback may run on the thread completing the driver stage; blocking CPU/I/O there slows down other requests. Offload heavy work to a bounded executor/async downstream and maintain demand/page budgets.

**Exercise 14.** A query `WHERE event_type='ALARM' ALLOW FILTERING` without a partition key is slow. Will switching to `executeAsync` make Cassandra scan fewer SSTables?

**Answer:** **No.** The CQL/query model stays the same. Build an appropriate table/projection/index or move to an analytics path and bound the scope.

**Exercise 15.** A stage completes successfully with the first page and `hasMorePages()=true`. The API expects up to 100 rows but returns only the first page. Is the bug in Cassandra replicas or Java pagination?

**Answer:** It is a **Java pagination/workflow bug** for not calling `fetchNextPage()` and processing all required pages. A successful stage does not prove the entire query was consumed.

**Exercise 16.** Why shouldn't you compare sync vs. async throughput while async holds 5,000 requests in flight and sync holds only 100?

**Answer:** The differing **concurrency budget** makes the comparison unfair and can push async into overload and worse p99. Keep workload, data, CL, and timeouts consistent and measure in-flight, queues, CPU/GC, and server capacity.

## 23. Checklist and Decision Flow Before Using Async in Production

~~~text
CQL / DATA MODEL
[ ] Query uses full partition key, clustering range, and sensible LIMIT.
[ ] Bucket size, hot partitions, tombstone scans, and payload/row size are benchmarked.
[ ] RF/CL/local DC match availability and correctness goals.

JAVA DRIVER / LIFECYCLE
[ ] Long-lived CqlSession and reused prepared statements.
[ ] Team understands executeAsync returns CompletionStage<AsyncResultSet>, not List<Row>.
[ ] currentPage/hasMorePages/fetchNextPage handled fully per API contract.
[ ] No join/get inside HTTP event loops or driver callbacks.
[ ] thenCompose used whenever the next step returns a CompletionStage.
[ ] Callbacks kept fast; CPU/blocking work offloaded to a bounded executor.

BOUNDING / ERROR SEMANTICS
[ ] Input admission, queues, in-flight count, and fleet-wide fan-out bounded.
[ ] Caps on rows/bytes/pages and an overall request deadline enforced.
[ ] Retry budget, idempotency, and write timeout handling clearly defined.
[ ] Stage failures not converted into invalid empty results.
[ ] Cancellation not treated as server-side mutation rollback.
[ ] CompletionStage not equated with a backpressured Publisher.

SECURITY / OBSERVABILITY
[ ] Peer-verified TLS, per-service credentials, and least-privilege CQL roles.
[ ] Dev/staging/prod clusters/DCs/secrets isolated; no blind fallback.
[ ] Logs redacted; no device/event IDs as metric labels.
[ ] Measure first-page/full-consume p95/p99, pages/request, bytes, and retries.
[ ] Monitor client queues/GC alongside server tpstats/disk/tombstones/compaction.

VALIDATION / ROLLOUT
[ ] Test page size smaller than row count, final page, zero rows, and large payloads.
[ ] Test callback exceptions, timeouts, cancellation, and replica failures.
[ ] Test overload when permits exhaust and ensure permits release on all outcomes.
[ ] Load test sufficiently and canary with stop criteria and config/code rollback.
~~~

~~~mermaid
flowchart TD
    A["Need Cassandra query without holding waiting threads"] --> B["Design CQL bounded by partition/range"]
    B --> C["Use one CqlSession + prepared statement"]
    C --> D["executeAsync -> CompletionStage<AsyncResultSet>"]
    D --> E["Process currentPage lightly"]
    E --> F{"Need and allowed to read more?"}
    F -->|Yes, budget left| G["thenCompose(fetchNextPage)"]
    G --> E
    F -->|No| H["Finish workflow with clear result/status"]
    H --> I["Release permits, metrics, deadline/cancellation cleanup"]
    I --> J{"Correctness, p99, memory, replica health met?"}
    J -->|No| K["Fix query, page/byte budget, concurrency, or retry"]
    K --> B
    J -->|Yes| L["Canary rollout and monitor"]
~~~

**Summary:** `executeAsync` is a way to **send CQL and receive a `CompletionStage<AsyncResultSet>` without blocking a Java thread while waiting for I/O**. `CompletionStage` lets you chain steps via `thenApply`, `thenCompose`, and explicit error/metrics handling; `AsyncResultSet` lets you read **`currentPage()`** and explicitly continue with **`hasMorePages()`/`fetchNextPage()`**. Switching to async **does not make CQL cheaper, does not create transactions/snapshots, and does not grant infinite backpressure**. A stable system requires **proper partition keys, row/byte/page limits, bounded admission and in-flight work, overall deadlines, safe retries, accurate cancellation semantics, and observability across both client and replicas**. A successful stage for the first page **does not mean the whole business workflow is complete**.
