# hasMorePages/fetchNextPage and Combining Asynchronous Pages

> **Chapter:** Async and Reactive  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Apache Cassandra — distributed wide-column database, partition keys, query-driven table design, consistency levels, replication, compaction, repair, error handling, and Java application integration.

## 1. Why Is Asynchronous Paging Needed?

Suppose a Java service reads a customer's activity history by day. Each day can hold thousands of events. If the program loads every row into a single list before responding, memory usage, latency, and the number of *in-flight* requests can all surge. When many customers query concurrently, the application also puts heavy pressure on coordinators and the replicas holding those partitions.

Apache Cassandra returns data in **pages** over the native protocol. Java Driver 4.x supports asynchronous reads via **executeAsync**, returning an initial **AsyncResultSet** for the current page. Your program decides **whether to continue fetching the next page**, processes each page's data, and combines them using **CompletionStage**.

Three key API names to remember:

- **currentPage():** the set of rows in the **current page**.
- **hasMorePages():** reports whether another page remains to be fetched.
- **fetchNextPage():** initiates fetching the **next page asynchronously**, returning a stage for a **new AsyncResultSet**.

Lesson objectives:

1. Understand that one **executeAsync** call does not mean the entire result set has been loaded.
2. Traverse multiple pages with **hasMorePages/fetchNextPage** in order without blocking threads on I/O.
3. **Combine pages** into a bounded result list or a constant-memory aggregate summary.
4. Coordinate asynchronous per-row processing with requesting the next page at the right time.
5. Avoid fetching too many queries/pages that overload Cassandra, and properly handle timeouts, cancellations, and retries.
6. Distinguish async paging from **Reactive Streams**, along with the limits of paging state when data mutates.

The examples use **Java Driver 4.x** (`com.datastax.oss.driver.api` package), **CompletionStage**, and **CompletableFuture**. Code snippets are illustrative and should be tested against your exact driver/JDK/Cassandra versions; cases requiring TLS/authentication configuration are noted explicitly.

## 2. What Is a Page in Cassandra?

### 2.1. A Single Query Can Span Multiple Fetches

In Cassandra, a statement returning many rows can be split by the server into multiple pages. The page size configured on the driver or statement is a **page-size hint** for how many rows to return per fetch, **not a guarantee that every page has that exact row count**.

~~~mermaid
sequenceDiagram
    participant J as Java service
    participant D as Java Driver
    participant C as Cassandra coordinator
    J->>D: executeAsync(statement)
    D->>C: CQL request + page size
    C-->>D: Page 1 + paging state
    D-->>J: AsyncResultSet page 1
    J->>J: currentPage()
    J->>J: hasMorePages() == true
    J->>D: fetchNextPage()
    D->>C: Request next page
    C-->>D: Page 2 + paging state
    D-->>J: AsyncResultSet page 2
    J->>J: Process page 2
~~~

The **first page** arrives through the stage returned by **executeAsync**. **Subsequent pages** are only requested when application code calls **fetchNextPage** on the corresponding result set. Each stage completes when its own page is ready to process, not when the whole query finishes.

### 2.2. What You Must Not Assume

- **currentPage()** does not represent all rows of the query if **hasMorePages() = true**.
- **hasMorePages() = true** does not guarantee the next page contains `pageSize` rows; a page may be shorter or, in some query paths, empty while still having more pages to fetch.
- **fetchNextPage()** is not an in-memory operation: it performs network I/O, consumes coordinator/replica resources, and can fail.
- **page size** is not **CQL LIMIT**: page size controls how results are chunked across fetches; LIMIT caps the total number of rows the query is asked to return.
- The **next page** is not a traditional SQL offset "page 2". Cassandra uses a paging state cursor; do not build unbounded offset APIs on top of it.
- Multi-page results are **not a transactionally consistent snapshot** if data changes during traversal.

### 2.3. API Quick Reference

| API | Returns | Meaning and when to call |
|---|---|---|
| **session.executeAsync(statement)** | **CompletionStage<AsyncResultSet>** | Starts the query and retrieves the **first page** |
| **result.currentPage()** | **Iterable<Row>** | Iterates rows already received in the current page |
| **result.hasMorePages()** | **boolean** | Checks whether more pages can still be fetched |
| **result.fetchNextPage()** | **CompletionStage<AsyncResultSet>** | Fetches the next page if `hasMorePages` is true |
| **statement.setPageSize(n)** | New statement | Sets the page size for the request |
| **statement.setConsistencyLevel(CL)** | New statement | Sets the required replica acknowledgment level |
| **statement.setExecutionProfileName(name)** | New statement | Selects a profile containing default timeout/CL/page-size, etc. |

In Java Driver 4.x, statements are **immutable**: you must use the value **returned** by setters. Calling a setter and discarding its return value is a common mistake when configuring page size or consistency.

## 3. A CQL Model Suitable for Testing Paging

Design the table for the query **"list a tenant's events on a given day, newest to oldest"**:

~~~sql
-- Create in a lab environment; requires enough nodes/DCs for the RF.
CREATE KEYSPACE IF NOT EXISTS event_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS event_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

**Primary key breakdown:**

- **(tenant_id, event_day)** is a **composite partition key**. Queries should bind both components to locate the partition; the driver can compute the routing key and pick a coordinator close to the replicas owning that token.
- **happened_at, event_id** are **clustering columns**. Ordering follows the clustering order; two rows with the same timestamp remain distinct via **event_id**.
- **event_day** acts as a daily bucket, bounding history within one partition. If a tenant writes too many events per day, consider hourly buckets or extra sharding; **paging cannot rescue an oversized partition**.
- **event_type/payload** are the columns read per access pattern. Do not log sensitive payloads in example logs.

Fixture data:

~~~sql
INSERT INTO event_lab.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED',
    '{"id":"demo-1"}'
);

INSERT INTO event_lab.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:01:00Z',
    33333333-3333-4333-8333-333333333333,
    'PAYMENT_PENDING',
    '{"id":"demo-1"}'
);
~~~

To observe **multiple pages**, insert more fixture rows in your test environment and pick a small page size. There is no need to use **ALLOW FILTERING** or scan the entire table just to learn paging.

### 3.1. Prepared Query with LIMIT

~~~sql
SELECT happened_at, event_id, event_type
FROM event_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

The CQL above uses **bind markers** intended for a Java prepared statement. In `cqlsh` directly, replace markers with valid literals.

**LIMIT 300** means the query returns at most 300 rows under CQL semantics, **not** that all 300 rows arrive in one page. With **setPageSize(40)**, the driver may issue multiple page fetches before reaching the limit, though the actual page count need not equal **ceil(300/40)** exactly.

## 4. Minimal Example with hasMorePages/fetchNextPage

The snippet below fetches up to 300 events and prints row counts **for each page**. Processing is lightweight; this illustrates the flow, not how to structure a long-running service.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public class AsyncPageBasics {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // This main method calls join at the demo program BOUNDARY;
        // never call join/get inside asynchronous page processing.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM event_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement statement = query
                .bind(tenantId, day, 300)
                .setPageSize(40)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            session.executeAsync(statement)
                .thenCompose(page -> visitPages(page, 1))
                .toCompletableFuture()
                .join();
        }
    }

    private static CompletionStage<Void> visitPages(
            AsyncResultSet page, int pageNumber) {

        int rowsInPage = 0;
        for (Row row : page.currentPage()) {
            if (row.getUuid("event_id") == null) {
                throw new IllegalStateException(
                    "Event fixture missing event_id");
            }
            rowsInPage++;
        }

        System.out.println("Page " + pageNumber +
                           ": " + rowsInPage + " rows");

        if (!page.hasMorePages()) {
            return java.util.concurrent.CompletableFuture
                .completedFuture(null);
        }

        return page.fetchNextPage()
            .thenCompose(next ->
                visitPages(next, pageNumber + 1));
    }
}
~~~

**Step-by-step walkthrough:**

1. **executeAsync(statement)** returns a stage for the first page.
2. **thenCompose** receives an **AsyncResultSet** once the stage completes.
3. **currentPage()** is iterated once to process that page's rows.
4. **hasMorePages()** decides whether more I/O is needed to fetch the next page.
5. **fetchNextPage()** returns a stage for the next page; **thenCompose** continues the chain when the new page arrives.
6. The outermost stage completes only when the **final page has been processed**, or fails if any stage errors.

In the example, **join()** sits only at the end of **main** to keep the session open until the demo finishes. **Never call join/get** inside callbacks, driver I/O threads, event loops, or asynchronous HTTP handlers.

**Limitation:** `visitPages` uses asynchronous recursion for clarity. For huge page counts, avoid heavy callbacks, retaining unnecessary lists/references, or deep synchronous stack chains if stages complete immediately. Use a controlled processor/trampoline, bounded executor, or Reactive Streams for very long streams. **Do not treat a console example as a complete production orchestrator.**

## 5. Combining Pages into a Bounded List

A common requirement is an endpoint returning **at most N event IDs** for display. You can merge multiple pages into one list, provided you enforce a **memory bound**.

### 5.1. Collecting at Most N Elements

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class BoundedPageCollector {
    public static CompletionStage<List<UUID>> collect(
            CompletionStage<AsyncResultSet> firstPage,
            int maxRows) {

        if (maxRows <= 0) {
            throw new IllegalArgumentException(
                "maxRows must be positive");
        }

        return firstPage.thenCompose(page ->
            append(page, new ArrayList<>(), maxRows));
    }

    private static CompletionStage<List<UUID>> append(
            AsyncResultSet page,
            List<UUID> collected,
            int maxRows) {

        for (Row row : page.currentPage()) {
            if (collected.size() >= maxRows) {
                break;
            }
            collected.add(row.getUuid("event_id"));
        }

        if (collected.size() >= maxRows ||
                !page.hasMorePages()) {
            return CompletableFuture.completedFuture(
                java.util.Collections.unmodifiableList(
                    new ArrayList<>(collected)));
        }

        return page.fetchNextPage()
            .thenCompose(next ->
                append(next, collected, maxRows));
    }
}
~~~

Usage:

~~~java
BoundStatement statement = prepared.bind(tenantId, day, 1000)
    .setPageSize(64)
    .setIdempotent(true);

CompletionStage<List<UUID>> ids =
    BoundedPageCollector.collect(
        session.executeAsync(statement), 150);
~~~

**Important invariant:** only a single continuation branch mutates **collected**, and the next page is requested **only after** processing the current page. Running multiple branches writing concurrently into an `ArrayList` introduces race conditions and non-deterministic ordering.

In this example, the returned list holds at most **150 UUIDs**; the server may have sent a page with more rows than needed, so we **stop fetching** once the cap is hit. The cap should be enforced by the service/API layer rather than letting clients pass unbounded values.

### 5.2. Why Not Always Return a List of the Whole Dataset?

Suppose an endpoint reads 100,000 rows, each holding a 1 KiB object in the application:

~~~text
100,000 rows × 1 KiB ≈ 97.7 MiB raw data

Not yet counting:
- Java object headers / reference arrays;
- strings, UUIDs, DTOs, driver buffers;
- multiple concurrent requests;
- queues and intermediate buffers for response serialization.
~~~

When 100 requests simultaneously hold large lists, OOM risk escalates rapidly. If the use case requires processing all data, **aggregate metrics**, **stream to a backpressured sink**, or run a **bounded batch job** instead of returning an unbounded list to an HTTP request.

## 6. Folding Multiple Pages into a Summary Result

One way to avoid accumulating rows is **fold/reduce**: process each page and keep only a few summary variables—for example, counting events by type or action.

### 6.1. Minimal Version: Summing Total Rows

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

static CompletionStage<Long> countPages(
        AsyncResultSet page, long previousCount) {

    long total = previousCount;
    for (Row ignored : page.currentPage()) {
        total++;
    }

    if (!page.hasMorePages()) {
        return CompletableFuture.completedFuture(total);
    }

    final long nextTotal = total;
    return page.fetchNextPage()
        .thenCompose(next -> countPages(next, nextTotal));
}
~~~

The idea is **O(1) accumulator memory**, rather than O(rows) like a collector. However, this client-side counter still reads every row, consuming bandwidth and I/O; it is **not a replacement for dedicated metrics/counters** if the system needs frequent counts at huge scale. CQL **COUNT(*)** over large sets has similar cost considerations. Design a summary/rollup table for the access pattern if frequent counting is required.

### 6.2. Separating CPU Work from Driver Callbacks

If each page needs non-trivial computation or DTO mapping, do not run heavy work inside a callback that may execute on a driver I/O thread. Offload processing to a separate bounded **Executor**.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;

import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

static CompletionStage<Long> countWithExecutor(
        AsyncResultSet page,
        long countSoFar,
        Executor processingPool) {

    return CompletableFuture.supplyAsync(() -> {
        long total = countSoFar;
        for (Row ignored : page.currentPage()) {
            // Assume CPU-bound computation happens here as well.
            total++;
        }
        return total;
    }, processingPool).thenCompose(total -> {
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(total);
        }
        return page.fetchNextPage()
            .thenCompose(next ->
                countWithExecutor(next, total, processingPool));
    });
}
~~~

Each next page is requested **only after the current page finishes processing**. This creates a natural form of backpressure between Cassandra and downstream.

**Note:** Configure the `Executor` with **bounded threads and a bounded queue**; feeding pages into a thread pool with an unbounded queue can still cause OOM. Avoid blocking disk/HTTP calls inside driver callbacks; if downstream I/O is needed, compose downstream async stages and fetch the next page only after downstream confirms completion.

### 6.3. A Common Mistake: thenApply Instead of thenCompose

When a lambda returns a **CompletionStage**, **thenApply** produces a nested stage:

~~~java
// Result type becomes CompletionStage<CompletionStage<Long>>:
 CompletionStage<CompletionStage<Long>> nested = session.executeAsync(statement)
    .thenApply(firstPage ->
        countPages(firstPage, 0L));
~~~

Use **thenCompose** to "flatten" it:

~~~java
// Result type is CompletionStage<Long>:
CompletionStage<Long> flat = session.executeAsync(statement)
    .thenCompose(firstPage ->
        countPages(firstPage, 0L));
~~~

Rule of thumb:

- **thenApply:** transforms one value into another value, e.g., **AsyncResultSet → Integer**.
- **thenCompose:** when the transformation **returns another CompletionStage**, chaining the inner async work.

## 7. Fetch Only After Downstream Finishes Processing

Suppose each event must be sent to another service whose downstream method returns **CompletionStage<Void>** once a row is accepted. You want **sequential order** so downstream is not flooded.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.function.Function;

import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

static CompletionStage<Void> drain(
        AsyncResultSet page,
        Function<Row, CompletionStage<Void>> sink) {

    CompletionStage<Void> chain =
        CompletableFuture.completedFuture(null);

    for (Row row : page.currentPage()) {
        chain = chain.thenCompose(ignored -> sink.apply(row));
    }

    return chain.thenCompose(ignored -> {
        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(null);
        }
        return page.fetchNextPage()
            .thenCompose(next -> drain(next, sink));
    });
}
~~~

**Characteristics:**

- **sink** must provide genuine async processing; if it **blocks** or does heavy CPU work, use an appropriate executor and work bounds.
- Rows within a page enter the stage chain in iteration order. The next page is **requested only after the sink finishes every row on the current page**.
- If one row fails, the stage chain fails and **does not fetch the next page** on the normal path.
- In a real system, define a row-failure policy: abort the job, checkpoint, dead-letter, bounded retry, or business compensation. Never silently swallow exceptions.
- Building a deep stage chain per row can allocate many objects when page size is large; test memory and consider a dedicated worker/processor or reactive library for very long streams.
- Do not infer durable downstream persistence from sink success unless **the sink's contract** actually guarantees durability.

### 7.1. Internal Backpressure and Query Pacing

If downstream processes 200 rows/s while Cassandra returns a 1,000-row page, the application holds that page until it is drained. That remains a **bounded buffer** as long as page size and concurrent queries are capped.

Do not call **fetchNextPage()** the instant a page arrives and keep prefetching pages ahead while the sink lags. Unbounded prefetching piles up data on the client, raises memory usage, and puts needless load on coordinators and replicas.

## 8. Do Not Fetch Multiple Pages of One Cursor in Parallel

A paginated query is **sequentially stateful**: each page depends on the previous page's paging state. The safe pattern is:

~~~text
executeAsync()
  → process currentPage()
  → hasMorePages()?
       → fetchNextPage()
       → process currentPage() of the new AsyncResultSet
       → ...
~~~

**Do not** call **fetchNextPage()** multiple times on the same page object expecting "pages 2, 3, and 4" in parallel. This is not an offset/page-number API for parallel fetching. There is no basis to assume repeated calls on the same page yield distinct consecutive pages as desired.

If you need parallelism for higher throughput, split the work into **multiple independent queries** by partition key, bucket, or token range supported by your data model; each query manages its own page chain, and total concurrent queries must stay bounded.

### 8.1. Two Independent Partitions and thenCombine

For example, suppose an application needs up to 100 event IDs from **two different days**. Each partition can be queried independently:

~~~java
CompletionStage<List<UUID>> dayOne =
    BoundedPageCollector.collect(
        session.executeAsync(statementForDayOne), 100);

CompletionStage<List<UUID>> dayTwo =
    BoundedPageCollector.collect(
        session.executeAsync(statementForDayTwo), 100);

CompletionStage<List<UUID>> combined =
    dayOne.thenCombine(dayTwo, (left, right) -> {
        List<UUID> merged = new ArrayList<>(
            left.size() + right.size());
        merged.addAll(left);
        merged.addAll(right);
        return java.util.Collections.unmodifiableList(merged);
    });
~~~

This snippet assumes both statements bind full partition keys for the two partitions. **thenCombine** waits for both tasks to finish and then merges the two lists. However:

- **left + right** is list concatenation, **not a global timestamp sort**. If global time order is needed, fetch timestamps too, merge with an explicit comparator, and apply the row cap.
- Run only a **bounded number of parallel queries**. Never launch thousands of partition queries simultaneously without admission control.
- The two partitions may mutate at different times, so there is no atomic snapshot spanning both queries.
- If either stage fails, **combined** fails unless the application explicitly defines a partial-result policy.

## 9. Bounded Concurrency Across Multiple Queries

Reading pages sequentially **within a single query** does not cap how many queries run concurrently. For instance, 1,000 HTTP requests each holding one active page still generate 1,000 concurrent requests against Cassandra.

You can cap **active paged-query pipelines** using a semaphore:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class BoundedPagedQueries {
    private final CqlSession session;
    private final Semaphore permits;

    public BoundedPagedQueries(CqlSession session, int maxActive) {
        if (maxActive <= 0) {
            throw new IllegalArgumentException(
                "maxActive must be positive");
        }
        this.session = session;
        this.permits = new Semaphore(maxActive);
    }

    public CompletionStage<List<UUID>> query(
            BoundStatement statement,
            int maxRows) {

        if (!permits.tryAcquire()) {
            CompletableFuture<List<UUID>> failed =
                new CompletableFuture<>();
            failed.completeExceptionally(
                new RejectedExecutionException(
                    "Paged-query concurrency limit reached"));
            return failed;
        }

        try {
            return BoundedPageCollector.collect(
                    session.executeAsync(statement), maxRows)
                .whenComplete((result, error) ->
                    permits.release());
        } catch (RuntimeException error) {
            permits.release();
            throw error;
        }
    }
}
~~~

**Advantage:** the permit is held for **the entire page chain**, not just the initial request. If downstream slows down, concurrent active pipelines remain bounded.

**Known limitations:**

- This limit is **per Java process**; 20 instances × 50 permits can still produce 1,000 concurrent pipelines. Consider fleet-wide and per-tenant quotas.
- **RejectedExecutionException** comes from **client-side admission**, not Cassandra's **OverloadedException**.
- Do not leak permits if callers abandon pipelines or create stages that never complete; pair with timeouts and cancellation handling appropriate for your environment.
- **maxRows** must be enforced by the API and trusted configuration; never accept unbounded client values.
- A pipeline fetching many pages holds its permit longer; separate batch workloads and apply fair scheduling across tenant/traffic classes.
- For true I/O pacing, combine pipeline limits with timeouts, retry budgets, and well-chosen page sizes.

## 10. Failures When Fetching Page N

A paged query chain can succeed on **pages 1, 2, and 3**, and then **fail on page 4** due to a read timeout, read failure, unavailable, overloaded, or network/driver error. Consequently:

- Rows from pages 1–3 already **seen or processed** by the application do not mean the whole query succeeded.
- If the sink already triggered side effects, it cannot "automatically roll back" because page 4 failed.
- Retrying the entire query re-reads earlier rows. If the sink is not idempotent, downstream data may be processed twice.
- If Cassandra data is mutating, re-running from the start may see a different dataset than the first attempt.

### 10.1. How Does CompletionStage Propagate Errors?

~~~java
CompletionStage<List<UUID>> result =
    BoundedPageCollector.collect(
        session.executeAsync(statement), 200);

CompletionStage<List<UUID>> handled =
    result.whenComplete((ids, error) -> {
        if (error != null) {
            // Log only controlled operation, exception class, and trace ID.
            System.err.println(
                "Paged query failed: " +
                error.getClass().getSimpleName());
        } else {
            System.out.println("Collected " +
                               ids.size() + " event IDs");
        }
    });
~~~

**whenComplete** observes the terminal outcome; it does not fix errors. If you want to provide a fallback, define **clear semantics**. For example, returning a partial list after a fetch failure can trick callers into treating incomplete data as complete.

### 10.2. Handling Partial Processing

For pipelines writing elsewhere, decide upfront:

| Job type | When page N fails | Safer policy |
|---|---|---|
| HTTP endpoint needing full list | Return an error instead of silently returning partial data | Enforce deadlines, page/row caps, and valid resume tokens if designed |
| Idempotent ETL | Keep checkpoint/processed IDs | Resume from a verified checkpoint and deduplicate at the sink |
| Per-row emails/payments | Do not blindly retry from the start | Use business idempotency keys or an outbox; track per-item state |
| Summary report | Do not mark COMPLETE | Keep intermediate results marked INCOMPLETE; re-run safely |
| Distributed multi-partition batch | Do not assume branches share a snapshot | Design reconciliation and test cross-partition correctness |

A **failed CompletionStage** does not always hand back the direct cause: APIs such as **CompletableFuture.join** wrap exceptions in **CompletionException**. When logging or classifying errors, safely unwrap the cause to distinguish driver timeouts from domain errors.

### 10.3. Do Not Overuse Retries

Guidelines:

1. Retry only when the operation is **idempotent** and the error is plausibly transient, within the deadline.
2. Never retry endlessly when Cassandra returns **Overloaded/Unavailable**.
3. Use backoff/jitter and a retry budget to prevent retry storms.
4. Account for the driver's built-in retry policy: if both the driver and application retry, traffic can multiply many times over.
5. **Never downgrade LOCAL_QUORUM to ONE** as an automatic fallback if the API has a consistency contract.
6. For side-effecting sinks, distinguish a **durably committed checkpoint** from **rows seen in memory**.

## 11. Paging State and Continuation Tokens: Not OFFSET

In CQL paging, a continuation state is used by the driver and server to retrieve the next slice of results. **Paging state is opaque**: never parse its bytes as an offset, primary key, or computable position.

### 11.1. Constraints When Exposing Paging State

If an API lets users click "Next page" across separate HTTP requests, design a **continuation token** with strict constraints:

- Bind the token to the **exact CQL statement, bound values, schema, page settings, and user context**.
- Never accept a paging state from an untrusted client and pass it directly into the driver without **authentication and authorization scope checks**.
- Protect token integrity/signature, set an expiration, and invalidate tokens when queries or schemas change.
- Do not assume paging state stays valid or compatible across all driver/server versions or data model changes.
- Never log raw tokens or sensitive bound values in public telemetry.
- Rows can be inserted, updated, deleted, expired via TTL, or compacted between requests; **paging state does not provide a consistent snapshot**.

For scanning **a single partition in clustering order**, an alternative is **keyset pagination** using the last-seen clustering key, tailored to the access pattern. It must still account for concurrent inserts/deletes, but can be far more transparent than exposing raw paging states to clients.

### 11.2. LIMIT, Page Size, and Business Cutoffs

Suppose an API returns events prior to a timestamp cutoff:

~~~sql
SELECT happened_at, event_id, event_type
FROM event_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND happened_at <= ?
LIMIT ?;
~~~

The predicate **bounds the clustering range** by time within the specified partition. It pins the time window of interest, yet still does not guarantee a transactionally consistent snapshot if older rows are updated or deleted mid-query. If you need point-in-time export integrity, use an **application barrier/cutoff**, backups/CDC, or an appropriate business workflow.

## 12. Async Paging Does Not Equal Reactive Streams

Both approaches avoid blocking on Cassandra I/O, but their consumption models differ.

| Feature | AsyncResultSet + CompletionStage | Reactive Streams |
|---|---|---|
| Programming unit | Single-page stage and callbacks/continuations | Publisher/Subscriber, demand-driven requests |
| Fetching next page | Explicit **hasMorePages + fetchNextPage** | Driver/reactive adapter manages fetches per subscriber demand |
| Backpressure | Application-designed: page size, sink stage, query limits | Built into the demand contract when implemented properly |
| Async composition | **thenCompose, thenCombine, whenComplete** | Framework stream transformation and composition operators |
| Risks | Eager fetching, huge in-memory lists, blocking callbacks | Bad subscriber demand/cancellation, unbounded operator buffers |
| When to use | Java workflows using CompletableFuture, simple batches/jobs/async HTTP | Multi-stage streaming pipelines, Reactor/Rx/Reactive Streams stacks |

Java Driver 4.x includes a reactive API in supported configurations/versions; integrating Reactor or other frameworks depends on dependencies and publisher contracts. **Do not assume that naming something "reactive" automatically guarantees low memory or safe retries.** An unbounded `buffer` or `collectList` operator can still pin the entire dataset in RAM.

If a service already uses **CompletionStage**, explicit per-page handling is often sufficient for bounded queries. If you need per-row downstream throttling or integration into a larger reactive pipeline, evaluate the reactive API and test backpressure and cancellation in practice.

## 13. Cancellation, Session Lifecycle, and Timeouts

### 13.1. When the Caller Stops Waiting

An HTTP request may be cancelled before all pages are read. Application code should stop requesting **the next page** once it knows the caller no longer needs the data.

However, cancelling a **CompletableFuture** or stopping continuations **does not guarantee an already-sent request is aborted on the coordinator/replicas**. Nor does it undo mutations or server-side work already started. Distinguish:

- **Stop fetching:** prevents additional page I/O from the current pipeline.
- **Cancel a client-side stage:** changes how the client proceeds; not an automatic server rollback mechanism.
- **Driver/server timeout:** can fire while the coordinator is still working or has already succeeded.
- **Downstream cancel:** must still release permits, queues, and resources cleanly per the application lifecycle.

### 13.2. Keeping CqlSession Alive Long Enough

A common mistake:

~~~java
CompletionStage<AsyncResultSet> stage;
try (CqlSession s = buildSession()) {
    stage = s.executeAsync(statement);
}
// Session is already closed; fetching subsequent pages
// may fail even if the first stage succeeded.
~~~

**Do not close CqlSession immediately after starting an async query.** Allow the entire page chain to complete or cancel cleanly before closing the session. In web services, **CqlSession is normally a long-lived shared resource**, not created and closed per HTTP request.

### 13.3. End-to-End Deadlines

If an HTTP endpoint has a 2-second deadline while a paged scan is expected to take 10 seconds, running all pages only to discard the result wastes capacity. Budget your time:

~~~text
Caller deadline
  = queue / admission wait
  + first page request
  + subsequent page fetches
  + per-page / downstream processing
  + retries / backoff if any
  + response serialization
~~~

**Per-fetch timeouts** do not automatically combine into a sensible **end-to-end deadline**. Track the business request start time and check remaining budget before fetching the next page.

## 14. Relationship to Consistency Levels, Routing, and the Wide-Column Model

### 14.1. Page Size Does Not Change Consistency

With RF = 3 in **dc1**, a **LOCAL_QUORUM read** normally requires responses from a majority of replicas in the local DC. Setting **pageSize(32)** does not relax CL to ONE. Every page fetch remains subject to request/server conditions per query semantics.

If a replica hits a GC pause, saturated disk I/O, or network trouble, **fetchNextPage** can time out even though the prior page succeeded. That is why you must monitor **errors per page**, not only `executeAsync` success.

### 14.2. Paging Does Not Fix a Missing Partition Key

A query missing part of **(tenant_id, event_day)** may be invalid or trigger expensive scans if permitted via other mechanisms. **Paging does not turn a scan into an optimally routed lookup**.

When reading across multiple days, you can dispatch multiple queries by day bucket and combine bounded results, provided:

- Each query binds the full partition key.
- Concurrent queries are bounded.
- If global ordering is required, merge by **happened_at + event_id** after fetching appropriate slices rather than just concatenating lists.
- Never assume data across multiple partitions represents a single point-in-time snapshot.

### 14.3. Compaction, Repair, and Tombstones

Cassandra reads across memtables and SSTables; compaction and repair can contend with page fetches for I/O and CPU. Heavy tombstones, oversized partitions, or large collections can make pages unusually slow or empty and increase timeouts.

**Do not solve this by raising page size indefinitely.** Larger pages reduce round-trips, but they also increase payload size, buffering, CPU/GC pressure, and tail latency. Measure p95/p99 and actual byte sizes to pick a sensible page size.

Repair converges replicas per Cassandra's anti-entropy mechanisms; it does not create a snapshot for paging pipelines or turn processed pages into a transaction.

## 15. Choosing Page Size and Data Limits

| Situation | Selection guideline | Risks to monitor |
|---|---|---|
| HTTP API returning 20–100 rows | Moderate page size, with LIMIT and response cap | Extra round-trips if too small, RAM pressure if too large |
| Query returning very large rows | Smaller page size and monitor actual bytes | Page size counts rows, not exact bytes |
| Batch ETL with slow sink | Process pages sequentially; wait for sink before fetching | Holding pages in RAM too long, timeouts, checkpoints |
| Multi-request UI pagination | Authenticated continuation token or clustering keyset | Paging state is not an offset/snapshot |
| Scanning multiple partitions/buckets | Bound concurrency, merge with explicit ordering | Hot partitions, fan-out, total in-flight work |
| LWT or writes with side effects | Never use read-paging logic to infer atomicity | Uncertain timeout/retry outcomes |

**Do not treat 100, 500, or 5,000 as "Cassandra's standard page size."** Measure against **row size, payload, CL, network, GC, workload, and SLAs**. Start conservatively in the lab and adjust after benchmarking. Also cap the **maximum rows and maximum pages a single business request may consume** when required by SLAs.

### 15.1. Empty Page When More Pages Remain

A buggy loop may stop when **currentPage()** is empty:

~~~text
If row count in current page == 0, stop.
~~~

This is not guaranteed to work across all query paths. The condition controlling **whether more pages remain** is **hasMorePages()**, not the row count of the current page. For filtered/indexed queries or edge cases where the server returns fewer rows than expected, test **empty page with more pages remaining** instead of conflating the two signals.

## 16. Observing and Troubleshooting Paging Issues

### 16.1. Metrics from Java

For each query shape, record:

- **logical request ID** (without PII) and operation type;
- partition/bucket category rather than raw partition keys;
- **page size**, actual page count, processed rows, estimated total bytes;
- **first-page** latency and **full-page-chain** latency;
- p95/p99, timeouts, failing stage/page index, retry count;
- in-flight pipeline count, queue/permit utilization;
- downstream sink latency and failure rate.

If you only measure **first-page `executeAsync`** latency, it is easy to conclude queries are fast while users actually wait across **20 pages** for the full response.

### 16.2. Observing Cassandra

On authorized nodes, using version-compatible syntax:

~~~bash
# Health/topology: which nodes are UP/DOWN, DC/rack.
nodetool status

# Background tasks and pending queues.
nodetool tpstats
nodetool compactionstats

# Relevant table stats, depending on version support.
nodetool tablestats event_lab.events_by_tenant_day

# Partition/row size distribution, depending on version.
nodetool tablehistograms event_lab events_by_tenant_day
~~~

Correlate coordinator and replica logs/metrics, disk latency/IOPS, GC, network, and tombstone counts. A query slowing down on page N can indicate reading across many SSTables, hot partitions, active repair/compaction, or rising request load; do not just bump timeouts.

### 16.3. Eight-Step Investigation Runbook

1. Identify the exact **CQL query**, full partition key, page size, LIMIT, and CL in use.
2. Measure **first-page latency** vs. **full-result latency**, separating processing and downstream time.
3. Check page count, rows per page, and which page index typically fails.
4. Correlate concurrent load: active pipelines, retries, driver queues, client GC.
5. Inspect Cassandra nodes/DC/RF, read timeouts, overloaded/unavailable errors, compaction, and disk.
6. Inspect data shape: partition sizes, tombstones, collections, TTLs, and guardrails.
7. Tune deliberately: page size, `maxRows`, in-flight caps, query design, and sink processing.
8. Re-verify on fixtures and representative load, checking data accuracy, ordering, and completeness.

## 17. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Iterating only **currentPage()** of the first result | Missing data from subsequent pages | Check `hasMorePages` and call `fetchNextPage` |
| Calling fetch and discarding its **CompletionStage** | Unobserved success/failure of the new page | Chain with `thenCompose`/`whenComplete` |
| Calling **join/get** inside an I/O callback | Blocks thread; risks stalls or deadlock | Return stage and compose asynchronously |
| Fetching continuously ahead of a slow sink | Large buffers and extra pressure on Cassandra | Wait for sink/processor before fetching |
| Buffering all rows in an unbounded **List** | Heap/GC pressure / OOM | Collect with a cap, fold, or stream |
| Calling multiple parallel fetches on the same page | Violates paging ordering/state assumptions | One sequential fetch chain per query |
| Merging two partitions via **concat** and calling it time-sorted | Wrong global ordering | Merge with an explicit comparator |
| Stopping on an empty page | Can stop prematurely | Rely on `hasMorePages` |
| Retrying the whole query after page N fails with a non-idempotent sink | Re-processes earlier rows | Checkpointing + idempotency/reconciliation |
| Treating paging state as an eternal offset | Invalid tokens, security risks, shifting data | Signed/scoped expiring opaque tokens, or keyset when appropriate |
| Closing CqlSession before fetches finish | Subsequent page fetches fail | Tie lifecycle to the full async chain |
| Unbounded concurrent queries | Overloads coordinators and replicas | Admission/bounded concurrency and backpressure |
| Measuring only first-page latency | Hides total time to deliver final results | Measure full-result latency and per-page metrics |

## 18. Hands-on Exercises

### Exercise 1 — First Page Is Not the Entire Result

A SELECT has **LIMIT 180** and **setPageSize(40)**. **executeAsync** returns an `AsyncResultSet` whose **currentPage()** has 40 rows and **hasMorePages() = true**.

**Question:** Can you return those 40 rows immediately and report the result complete? Which API is needed to continue?

**Suggested answer:** No, if the contract requires the full result. Use **fetchNextPage()** and process the **new AsyncResultSet**, repeating until **hasMorePages() = false** or a business limit is reached.

### Exercise 2 — thenApply or thenCompose?

Given:

~~~java
CompletionStage<Long> countPages(
    AsyncResultSet page, long previous);
~~~

A developer writes:

~~~java
var output = session.executeAsync(stmt)
    .thenApply(page -> countPages(page, 0L));
~~~

**Question:** What is the type of `output`, and how should this be fixed?

**Suggested answer:** **CompletionStage<CompletionStage<Long>>**. Replace `thenApply` with **thenCompose** to get **CompletionStage<Long>** and await the full fetch chain.

### Exercise 3 — Empty Page with More Pages Remaining

A query returns an empty current page while **hasMorePages() = true**.

**Question:** Should you stop and report "no more data"?

**Suggested answer:** No. Check **hasMorePages()** to determine whether more fetches remain. Current page row count does not replace paging state.

### Exercise 4 — Memory and Concurrent Requests

100 HTTP requests are active; each collects 20,000 DTOs holding roughly 1 KiB of raw data each.

**Question:** At least how much raw data memory can be held, before Java overhead? What improvements fit?

**Suggested answer:** Around **1,953 MiB (~1.91 GiB)** of raw data. Enforce `maxRows`, process per page, bound in-flight requests, reduce concurrency, and benchmark realistic load.

### Exercise 5 — Fetching Before the Sink Finishes

Each page has 500 rows, while the sink accepts only 50 rows/s. Code keeps calling `fetchNextPage` even while the sink is still working on earlier pages.

**Question:** What are the risks and how do you fix it?

**Suggested answer:** Growing buffers/GC pressure and extra coordinator/replica load; call `fetchNextPage` only after the **CompletionStage** for the current page's sink processing completes. Also bound concurrent queries.

### Exercise 6 — Two Days, One List

A Java service runs two queries for **(tenant_id, 2026-11-20)** and **(tenant_id, 2026-11-21)**, each sorted by **happened_at DESC**. Code calls **list1.addAll(list2)** and claims the combined list is globally sorted descending.

**Question:** Is that always true?

**Suggested answer:** You cannot assume global order simply by concatenating two lists unless cross-day ordering rules are proven and enforced. To merge properly, use a comparator on **happened_at + event_id**, ensure both sources fetch enough rows within bounds, and apply the global LIMIT afterward.

### Exercise 7 — Page N Fails After Sending Notifications

A pipeline reads 10 pages, sends a notification per row, and page 7 hits a `ReadTimeout`. The job automatically retries the entire query from the start.

**Question:** What bug can this cause, and how do you fix it?

**Suggested answer:** Notifications for pages 1–6 may be sent again. Use business identifiers, an outbox/idempotent sink/durable checkpoints; retry based on error class and deadline, never treating paging state as an exactly-once guarantee.

### Exercise 8 — Does Page Size Fix a Hot Partition?

A tenant has a multi-GiB partition. Operations lowers page size from 1,000 to 50 and declares the bad schema fixed.

**Question:** What is your assessment?

**Suggested answer:** A smaller page size reduces payload per response, but **does not reduce total rows scanned**—and increases round-trips. Analyze bucketing/sharding, clustering keys, tombstones, and query patterns while measuring total latency and I/O.

### Exercise 9 — Calling join Inside a Callback

~~~java
session.executeAsync(statement)
    .thenApply(page -> page.fetchNextPage()
        .toCompletableFuture().join());
~~~

**Question:** Why is this dangerous, and what condition is missing?

**Suggested answer:** It blocks the callback thread and calls fetch **without checking hasMorePages()**; it also skips processing `currentPage` of the first page. Fix with **thenCompose**, process the current page, check `hasMorePages()`, and chain the next stage.

## 19. Production Checklist for Async Paging

- [ ] Query binds the full partition key and matches the access pattern.
- [ ] `CqlSession`/`PreparedStatement` reused; connections/TLS/auth properly configured.
- [ ] **setPageSize** configured and LIMIT/maxRows controlled per SLA.
- [ ] Processes **currentPage** and checks **hasMorePages** before calling **fetchNextPage**.
- [ ] Never stops merely because `currentPage` is empty; never assumes page size equals exact row count.
- [ ] Page chain is **composed** asynchronously; never blocks with `get`/`join` inside callbacks.
- [ ] Never fetches multiple pages of a single cursor concurrently without supporting semantics.
- [ ] Never collects unbounded rows into a `List`; uses bounded collectors, folds, or downstream sinks.
- [ ] Downstream uses backpressure/bounded queues; thread pools cannot grow without limit.
- [ ] Concurrent queries/pipelines, in-flight requests, and fleet-wide totals are bounded.
- [ ] End-to-end deadline enforced; stops fetching when the caller no longer needs results.
- [ ] Distinguishes **partial** vs. **complete** results and handles page N errors per business rules.
- [ ] Retries/backoff are bounded; idempotency and checkpoints verified for side effects.
- [ ] Paging state treated as opaque; continuation tokens authenticated, scoped, and expiring.
- [ ] Tested with concurrent INSERT/DELETE/TTL mutations during multi-page reads.
- [ ] When merging multiple partitions, global sort order and parallelism caps are explicitly enforced.
- [ ] Monitors first-page latency, full-chain latency, page counts, row counts, retries, and memory.
- [ ] When slow, inspects replicas/CL, hot partitions, tombstones, compaction, repair, and disk I/O.
- [ ] Never logs payloads, real partition keys, raw paging states, or secrets.

## 20. Summary

**AsyncResultSet** in Java Driver 4.x represents **a single ready page**, not the whole result set. Read rows via **currentPage()**, check **hasMorePages()**, and only when needed call **fetchNextPage()** and chain the next stage using **thenCompose**. When combining multiple pages, choose among **bounded collection**, **low-memory summary folding**, and **sequential backpressured downstream processing** according to your business contract.

With Cassandra, async paging still obeys the wide-column model's constraints: **partition keys must fit the query, consistency levels must match replication/topology, and large partitions, collections, tombstones, compaction, or repair can slow reads down**. Protecting Java memory and server capacity requires simultaneously controlling **page size, in-flight pipelines, deadlines, retries, and mutating data semantics across pages read at different times**. Only after measuring and validating the entire chain can you consider a paged async API correct, stable, and safe.
