# Subscriptions, Demand for Data, and Result Lifecycle

> **Chapter:** Async and Reactive  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra with distributed architecture, wide-column modeling, partition keys, query-driven tables, read/write consistency levels, CQL, replication, compaction, repair, troubleshooting, and Java application connectivity.

A Java application queries an events table holding millions of records. In synchronous code, a `ResultSet` loop fetches subsequent pages on the fly as it iterates. In asynchronous code, `executeAsync()` returns a `CompletionStage<AsyncResultSet>` and the app explicitly drives pagination. In **reactive** code, the app receives a **`Publisher<ReactiveRow>`**, expressed via Reactive Streams: a subscriber subscribes, requests items through `Subscription.request(n)`, receives items one by one via `onNext`, and finishes with `onComplete` or `onError`.

Returning a `Flux` does not turn Cassandra into an infinite real-time stream. A normal CQL `SELECT` remains a **finite query** subject to paging, consistency levels, timeouts, and replica capacity. Reactive Streams primarily serves to **propagate consumption demand and manage result lifecycles inside the application**, preventing upstream from pushing rows faster than the subscriber can process them.

This lesson answers four practical questions:

1. **When does the query start executing?** On `executeReactive`, on `subscribe`, or on `request(n)`?
2. **What if the subscriber only asks for two rows?** Does the driver fetch by page or issue two separate reads?
3. **What happens if the subscriber stops mid-stream?** What becomes of unread rows, in-flight requests, pool connections, and already-written mutations?
4. **Can a `ReactiveResultSet` be reused?** What happens with `cache()`, `retry()`, or two subscribers?

> **Version scope:** examples are based on **Apache Cassandra Java Driver 4.x** and official **4.19** documentation, paired with **Reactive Streams 1.0.x** and **Project Reactor 3.x**. The driver's reactive package is named `com.datastax.dse.driver.api.core.cql.reactive` for historical reasons; these APIs **work with open-source Apache Cassandra OSS**, without requiring DataStax Enterprise. When using Spring Data Cassandra Reactive, check your release train/BOM and Spring-layer behavior separately.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `Publisher`, `Subscriber`, `Subscription`, and `onSubscribe/onNext/onComplete/onError` signals.
2. Explain `request(n)` as **cumulative consumer demand**; `request(0)`/negative values are invalid and `Long.MAX_VALUE` effectively signals unbounded demand.
3. Understand that Java Driver 4.x's `ReactiveResultSet` defaults to **cold, unicast, single-subscription**, and why a second subscription fails.
4. Use `Flux.from(session.executeReactive(statement))`, distinguish one query result from a stream of queries, and handle write results that **emit zero rows**.
5. Explain how demand governs **page fetching** in Cassandra and the limits of backpressure on writes.
6. Manage `cancel`, completion/errors, timeouts, session lifecycles, and associated resources without assuming mutations rolled back.
7. Write a subscriber controlling demand in batches, a Reactor pipeline for SELECT, bounded-concurrency writes, and `StepVerifier` tests.
8. Distinguish subscriber-side bounds (`take`, `limitRate`) from server-side CQL bounds (`LIMIT`, partition key, page size).

## 2. Four Components of Reactive Streams

### 2.1. Who Produces, Who Consumes?

| Component | Typical API | Role in Cassandra Java Driver |
|---|---|---|
| **Publisher<T>** | `subscribe(Subscriber<? super T>)` | `ReactiveResultSet` emitting `ReactiveRow`s of one query |
| **Subscriber<T>** | `onSubscribe`, `onNext`, `onError`, `onComplete` | Code/framework receiving data and deciding how much it wants |
| **Subscription** | `request(long n)`, `cancel()` | Private link between one subscriber and publisher handling demand and cancellation |
| **Processor** | Both subscriber and publisher | Operators/adapters such as `map`, `filter`, `publishOn`, or complex pipelines |

**A `Publisher` does not wrap a pre-loaded `List<Row>`**. It represents a source capable of emitting items when consumed. Creating a `ReactiveResultSet` does not yet execute CQL; driver docs specify that query execution actually **triggers upon subscription**.

### 2.2. Valid Signal Sequence

~~~mermaid
sequenceDiagram
    participant S as Subscriber / Reactor
    participant P as ReactiveResultSet
    participant D as Cassandra Driver
    participant C as Coordinator / Replicas
    S->>P: subscribe(subscriber)
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P->>D: Execute / continue delivering results
    D->>C: Native protocol SELECT, fetch pages as needed
    C-->>D: Rows by page
    D-->>P: ReactiveRow, ReactiveRow
    P-->>S: onNext(row 1)
    P-->>S: onNext(row 2)
    Note over S,P: Never emit beyond remaining demand
    S->>P: request(3)
    P-->>S: onNext(row 3...5) if data remains
    P-->>S: onComplete() when results finish
~~~

This diagram is a **behavioral model**; it does not assert the driver always sends a network request at the exact instant of `request(2)`, nor that each `request(2)` corresponds to one CQL page. Query execution can start right after subscription, with rows fetched/buffered per page size, prefetching, and runtime path.

### 2.3. Observable Lifecycle of a Subscription

~~~text
NEW publisher (unsubscribed)
   |
   v
onSubscribe(subscription)   -- subscriber holds Subscription
   |
   v
ACTIVE (may await demand, receive onNext, await page/connection)
   |\
   | \----> cancel() ----> CANCELLED (no longer wants data)
   |
   +------> onComplete() -> COMPLETED (terminal)
   |
   +------> onError(e) --> FAILED (terminal)
~~~

Per Reactive Streams, **after terminal `onComplete` or `onError`, no new `onNext` may arrive**. `cancel` is a request to terminate the subscription, **not a mandatory terminal signal sent back to the subscriber**. Signals already in flight may still arrive as cancellation is observed; subscribers must handle racing states safely.

### 2.4. Demand Rules to Memorize

| Call | Semantics | Key point |
|---|---|---|
| `request(1)` | Ask for at most one new item | Can call `request(1)` repeatedly to process row by row |
| `request(5)`, then `request(3)` | Cumulative demand: up to 8 remaining rows allowed | Does NOT "replace demand 5 with 3" |
| `request(Long.MAX_VALUE)` | Effectively unbounded demand | Does not mean the entire table was just loaded into RAM |
| `request(0)` or `request(-1)` | **Invalid** | Per spec 3.9, must signal `onError(IllegalArgumentException)` if subscription is not cancelled |
| `cancel()` | Stop wanting more items | May lag behind already-emitted/in-flight `onNext`s; never rolls back server |
| No `request(n)` called | Subscriber has requested zero rows | Zero `onNext` signals; timeouts or terminal errors can still occur |

Per the Reactive Streams spec, a `Publisher` **must never emit more `onNext` signals than requested**. Yet requesting 2 rows **is not a native-protocol command instructing Cassandra to read strictly 2 rows from disk**: Cassandra's native protocol uses paging, and the driver may have already fetched/buffered a whole page of rows.

## 3. Java Driver 4.x: `CqlSession.executeReactive` Is a Cold Publisher

### 3.1. Real API and Packages

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import org.reactivestreams.Publisher;

// session created earlier with local DC and TLS/auth as needed.
ReactiveResultSet rs = session.executeReactive("SELECT ...");
Publisher<ReactiveRow> rows = rs; // ReactiveResultSet is a Publisher<ReactiveRow>.
~~~

**Never replace `com.datastax.dse...ReactiveRow` with a guessed `com.datastax.oss...ReactiveRow`.** The package name was kept for historical reasons even though the open-source Apache driver supports it. `org.reactivestreams:reactive-streams` must be on the classpath to call reactive methods; Project Reactor is an **optional** library, unnecessary if you use raw `Publisher`/`Subscriber`.

### 3.2. Lazy: Creating a Publisher Has Not Sent the Query

~~~java
ReactiveResultSet rs = session.executeReactive(
    "SELECT event_time, event_id, payload FROM stream_lab.events_by_device " +
    "WHERE device_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");

// Up to here rs is unsubscribed => query has NOT executed yet.
// Generally do not hold rs indefinitely and let CqlSession close before subscribing.
~~~

With Reactor:

~~~java
import reactor.core.publisher.Flux;

Flux<ReactiveRow> stream = Flux.from(rs);
// Still only a pipeline description; no subscriber yet.

// In a CLI/lab program, blockLast() subscribes and waits for completion.
stream.doOnNext(row -> System.out.println(row.getUuid("event_id")))
      .blockLast();
~~~

**Use `blockLast()` only in CLI/test code where blocking is permitted.** In WebFlux/reactive handlers, return `Flux` to the framework so it subscribes according to the HTTP lifecycle—never call `block()`/`subscribe()` manually and return another publisher.

### 3.3. Unicast, Single-Subscription: Not Arbitrarily Re-Subscribable

Per Java Driver 4.19, `ReactiveResultSet` is by default:

- **cold:** the query does not execute before subscription.
- **unicast:** one subscriber receives one result stream.
- **single-subscription-only:** **one subscription** per `ReactiveResultSet`; subscribing a second time to the same instance can fail with `IllegalStateException`.

~~~java
ReactiveResultSet once = session.executeReactive(
    "SELECT event_time FROM stream_lab.events_by_device " +
    "WHERE device_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");

Flux<ReactiveRow> flux = Flux.from(once);
// Conceptual demo: first subscribe consumes the source, second errors.
// flux.count().block();
// flux.count().block();  // Never rely on a second subscription working.
~~~

This applies to a **specific result set instance**, not to the session itself—one `CqlSession` executes many concurrent queries. To **run a fresh query per subscriber**, create a **new `ReactiveResultSet` per subscription**:

~~~java
import reactor.core.publisher.Flux;

Flux<ReactiveRow> rerunnable = Flux.defer(() ->
    Flux.from(session.executeReactive(
        "SELECT event_time, event_id, payload " +
        "FROM stream_lab.events_by_device " +
        "WHERE device_id = 11111111-1111-4111-8111-111111111111 " +
        "AND event_day = '2026-11-21'")));

// Each subscribe -> new ReactiveResultSet -> new query execution.
// This is intentional behavior; never reuse for unsafe mutations.
~~~

**Warning:** `Flux.defer` does not "allow re-subscribing to the old object"; it **issues a brand new query**. Two subscribers may observe different data if new writes occurred, consistency is weak, or TTLs expired between reads. On INSERT/UPDATE, a second subscription repeats side effects.

## 4. How Does Demand Flow from Subscriber to Cassandra?

### 4.1. Bounded Demand Is Backpressure

A subscriber reading in batches might:

1. Call `request(2)` in `onSubscribe`.
2. Process two `onNext` items.
3. Once that batch finishes, call `request(2)` again.
4. When enough data is read or the user cancels the HTTP request, call `cancel()`.

This prevents the publisher from emitting rows beyond unfulfilled demand. Still, it **does not automatically bound processing duration or operator buffering** downstream; with `publishOn`, `flatMap`, `buffer`, or `onBackpressureBuffer`, you must explicitly account for prefetch and memory.

### 4.2. Paging Is the Throttle Between Driver and Cassandra

Cassandra's native protocol **has no standard message saying "subscriber requested 2 more rows."** The driver schedules next-page fetches based on demand and stream state. Therefore:

- `request(2)` bounds **`onNext` emissions**, not how many rows the server scanned.
- The query still uses a `page size`; one page holds many rows, and next-page fetches fire whenever the driver needs more data.
- When downstream slows down, the driver can **pace next-page fetches**; Cassandra has still spent CPU/I/O producing pages already sent.
- Extremely slow subscribers, slow nodes, or congested paths can still trigger `DriverTimeoutException` or `ReadTimeoutException`.
- If a query scans huge partitions/tombstones or uses `ALLOW FILTERING`, reactive backpressure **never makes that query cheap**.

**Impact diagram:**

~~~mermaid
flowchart LR
    A["Subscriber demand<br/>request(n)"] --> B["Driver reactive publisher"]
    B --> C["Deliver buffered rows<br/>within demand"]
    B --> D["Pace next-page fetches<br/>by demand and buffer"]
    D --> E["Native protocol paging"]
    E --> F["Cassandra coordinator"]
    F --> G["Replicas / SSTables"]
    H["CQL LIMIT, PK, CL, page size"] -. "Determines workload" .-> E
~~~

### 4.3. Three Limits Never to Confuse

| Limit | Where it lives | What it does **NOT** guarantee |
|---|---|---|
| `Subscription.request(n)` | Reactive Streams between subscriber and publisher | Does not force Cassandra to scan strictly `n` rows/disk reads |
| `Flux.take(n)` | Subscriber-side operator; cancels upstream after `n` items | Does not mean CQL read only `n` server rows; pages may already be fetched |
| CQL `LIMIT n` | Server-side query semantics with partition/filter/clustering | Not a hard cap on SSTable bytes scanned when tombstones/filters exist |
| `Statement.setPageSize(n)` | Target size per native-protocol page | Does not cap total results or force exact `n` rows/page |
| `Flux.limitRate(n)` | Paces upstream Reactor demand | Does not change CQL `LIMIT` or page size |

If business logic only needs the 10 latest events, **design the table with matching clustering + CQL `LIMIT 10`** and add Reactor operators to pace consumption as needed. Never write `SELECT *` on a massive partition expecting `take(10)` to always save server work.

## 5. Writing a Raw Subscriber to See `request(n)` and `cancel()`

### 5.1. A Subscriber Reading in Batches of Two Rows

Pure `org.reactivestreams` example, without requiring Reactor:

~~~java
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import java.util.concurrent.atomic.AtomicInteger;

final class TwoAtATimeSubscriber implements Subscriber<ReactiveRow> {
    private Subscription subscription;
    private final AtomicInteger received = new AtomicInteger();

    @Override
    public void onSubscribe(Subscription s) {
        this.subscription = s;
        s.request(2); // Accept at most 2 items before asking for more.
    }

    @Override
    public void onNext(ReactiveRow row) {
        // Perform ONLY SHORT work; NEVER block on I/O or HTTP here.
        System.out.println("event_id=" + row.getUuid("event_id"));
        int total = received.incrementAndGet();

        if (total >= 6) {
            subscription.cancel(); // Stop after 6 rows; does not delete DB rows.
        } else if (total % 2 == 0) {
            subscription.request(2); // Cumulative demand for the next batch.
        }
    }

    @Override
    public void onError(Throwable cause) {
        System.err.println("Query error type: "
                + cause.getClass().getSimpleName());
    }

    @Override
    public void onComplete() {
        System.out.println("Query fully consumed");
    }
}
~~~

Attach the subscriber to the result:

~~~java
// rs created from session.executeReactive(preparedBoundStatement).
rs.subscribe(new TwoAtATimeSubscriber());
~~~

**Expected behavior:** If fewer than 6 rows exist, `onComplete` fires. Once 6 rows arrive, the subscriber calls `cancel()` and **must not expect `onComplete` as a required signal**. If signals were already emitted just before `cancel`, handle state races carefully; do not treat this demo as a precise distributed counter.

**Demo goal:** make `Subscription`, demand, and cancellation concrete. In production, avoid per-row `System.out.println` on driver threads, never leak customer data, and use Reactor operators or bounded queues to offload heavy work.

### 5.2. Why `request(0)` Is Not "Pause"

~~~java
// WRONG: request(0) violates Reactive Streams Specification 3.9.
// subscription.request(0);
~~~

To pause receiving rows, **simply refrain from calling `request` again** once existing demand is spent. When ready to process more, call `request(k)` with `k > 0`. For async processing, tie completion of downstream work to issuing new demand—never block `onNext` waiting on a future.

### 5.3. Never Call `request(Long.MAX_VALUE)` Without Capacity

When a subscriber calls `request(Long.MAX_VALUE)`, it declares unbounded flow-control capacity. If downstream pushes each row into an unbounded queue or calls a slow task, OOM can strike **in operators or application code** even while the driver honors Reactive Streams.

Prefer pacing demand via Reactor operators, bounded queues, or bounded batches; **never create unbounded buffering** just because "reactive is non-blocking."

## 6. Reactor Pipeline for `SELECT` and WebFlux

### 6.1. Prepared Statement and Partition-Key Mapping

Suppose data is modeled for "latest events of one device on one day":

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
~~~

The app can prepare once at startup and return a `Flux` per request:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import reactor.core.publisher.Flux;

// JDK 17+ example: record as an immutable DTO.
record EventView(Instant eventTime, UUID eventId, String payload) {}

static Flux<EventView> findEvents(
        CqlSession session, PreparedStatement select,
        UUID deviceId, LocalDate day) {

    BoundStatement statement = select.bind(deviceId, day)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(2)     // Lab: small page target to observe paging.
        .setIdempotent(true); // Read-only SELECT with no side effects.

    // defer creates a NEW ReactiveResultSet for each subscription.
    return Flux.defer(() -> Flux.from(session.executeReactive(statement)))
        .map(row -> new EventView(
            row.getInstant("event_time"),
            row.getUuid("event_id"),
            row.getString("payload")))
        .limitRate(2);
}
~~~

Prepared statement (created once and reused for the session's lifetime):

~~~java
PreparedStatement select = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM stream_lab.events_by_device " +
    "WHERE device_id = ? AND event_day = ? " +
    "LIMIT 100");
~~~

Here:

- `SELECT` specifies the full **partition key**; the driver computes the routing key/token and prefers local replicas per the load-balancing policy.
- `LOCAL_QUORUM` requires matching RF/DC; it will not work on a single-node lab configured with RF=3.
- `setPageSize(2)` is only a **target page size**, not a 2-row cap on total results.
- `LIMIT 100` is a server-side cap returning at most 100 rows; it still does not make a huge or tombstone-heavy partition cheap.
- `limitRate(2)` throttles **Reactor's upstream demand**, not a CQL page-size setting.
- `Flux.defer` lets a **repository method** return a multi-subscribable publisher by executing a fresh query each time. Do not use it if re-running the query violates business rules.

### 6.2. In WebFlux HTTP Handlers, Return the Publisher to the Framework

Example simple controller (auth/validation omitted):

~~~java
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/devices")
final class DeviceEventController {
    private final EventQueryService queryService;

    DeviceEventController(EventQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{deviceId}/days/{day}/events")
    Flux<EventView> events(@PathVariable UUID deviceId,
                           @PathVariable LocalDate day) {
        return queryService.events(deviceId, day);
        // Never call .subscribe(), .block(), or .blockLast() here.
    }
}
~~~

`EventQueryService` is a hypothetical app bean calling `findEvents(...)` above; the controller omits Spring Boot configuration, auth, and query bounds, so it is **not a standalone application**. WebFlux subscribes per HTTP response lifecycle, paces downstream writes, and propagates cancellation on client disconnect.

**Spring Data Cassandra note:** Reactive repositories / `ReactiveCqlTemplate` may build pipelines over the **driver's async API** and expose `Flux/Mono`. Do not assume every Spring Data method wraps `executeReactive`'s `ReactiveResultSet` directly. Either way, *lazy until subscribed*, demand, cancellation, and avoiding blocking remain critical at the Reactor layer.

### 6.3. Never Call `.subscribe()` to "Trigger Early" and Discard or Reuse

Anti-pattern:

~~~java
Flux<EventView> flux = findEvents(session, select, deviceId, day);

// WRONG if the HTTP framework also subscribes to this publisher:
// flux.subscribe(row -> System.out.println("side effect"));
// return flux;
~~~

With `Flux.defer`, two subscriptions trigger **two independent CQL queries**. With `Flux.from(existingReactiveResultSet)`, the second subscription **fails**. Furthermore, a manual subscription detaches from the HTTP request's timeout, cancellation, and error handling.

To log or record metrics on **the same execution**, use `doOnNext`/`doOnError`/`doFinally` inside the pipeline the framework subscribes to—never add a second subscription just to log.

## 7. Write Streams: An Empty Publisher Does Not Mean Nothing Wrote

### 7.1. Unconditional `INSERT`/`UPDATE` Normally Emits Zero Rows

A CQL `INSERT` is not a row-returning query. With `executeReactive(insertStatement)`, the publisher typically **emits 0 `ReactiveRow`s** and then signals `onComplete` when the request succeeds.

~~~mermaid
sequenceDiagram
    participant A as Reactor / Subscriber
    participant B as ReactiveResultSet
    participant C as Cassandra
    A->>B: subscribe + request(1)
    B->>C: INSERT ...
    C-->>B: Success (no rows)
    B-->>A: onComplete()
    Note over A,B: No onNext, yet the write may have succeeded
~~~

This **does not** prove data is compacted/repaired, every replica is updated, or no future failure will occur. It means the CQL statement returned a success response at its configured consistency level. On timeouts or lost ACKs, mutation outcomes remain **uncertain** even when the client sees `onError`.

### 7.2. `doOnNext` Does Not Trigger Queries; `flatMap` Subscribes Inner Publishers

**Wrong** example:

~~~java
Flux.just(insertStatementA, insertStatementB)
    .doOnNext(session::executeReactive)
    .blockLast(); // doOnNext calls the method creating a Publisher and discards it.
~~~

Here the outer pipeline has a subscriber, yet each `executeReactive` creates a **cold Publisher** and drops it. **Zero inner subscriptions occur, so zero INSERTs execute**.

Right Reactor example:

~~~java
Flux.just(insertStatementA, insertStatementB)
    .concatMap(stmt -> Flux.from(session.executeReactive(stmt)).then())
    .blockLast(); // Use .blockLast() ONLY in CLI/tests.
~~~

`concatMap` subscribes sequentially, waiting for the previous statement to finish before starting the next. That bounds write concurrency to 1, while **not turning statements into a cross-partition transaction**.

### 7.3. Counting Completed Statements, Not Emitted Rows

~~~java
import reactor.core.publisher.Flux;

Flux<BoundStatement> writes = Flux.fromIterable(writeStatements);

Flux<Integer> acknowledgements = writes.flatMap(
    stmt -> Flux.from(session.executeReactive(stmt)).thenReturn(1),
    8
);

// Counting completed write requests:
// In Reactor you can use:
// Mono<Long> completedCount = acknowledgements.count();
~~~

**Exact explanation:** `thenReturn(1)` emits `1` **after the result publisher completes normally**. It accurately counts write requests that returned a successful response; it **does not prove multi-table business atomicity**, does not replace LWTs, and does not make retries after timeouts safe.

If a statement is an LWT, never equate completion with `[applied]=true`. Read `ReactiveResultSet.wasApplied()` to check whether the condition held, and map the outcome per business rules.

### 7.4. Bounding Concurrent Writes: Cassandra Does Not Push Write Demand

Driver 4.19 notes that the native protocol **does not provide bidirectional Reactive Streams backpressure**. On writes, Cassandra **does not send `request(n)` to Java** saying how many mutations it has room for; if upstream emits faster than coordinators handle, the cluster hits `WriteTimeoutException`, `OverloadedException`, and GC/network queue pileups.

Hence Reactor must **bound concurrently subscribed inner Publishers**:

~~~java
Flux.fromIterable(writeStatements)
    .flatMap(
        stmt -> Flux.from(session.executeReactive(stmt)).thenReturn(1),
        8  // Lab: at most 8 concurrent in-flight CQL requests from this operator.
    )
    .count(); // Returns Mono<Long>; caller must subscribe.
~~~

The value `8` is **illustrative only**; tune via p95/p99, RF/CL, mutation sizes, hot partitions, driver pools, and server load. When multiple app instances write concurrently, `concurrency=8` **per instance** still creates `8×N` total load; size limits across the entire system.

**Watch out for `flatMap`:** it can complete writes **out of input order**. If operations on the same partition require preserving business order, use `concatMap` or key-grouped bounded concurrency—while remembering sequential pipelines still do not replace CAS, timestamps/conflict resolution, and retry idempotency.

## 8. Result Lifecycle on Complete, Error, and Cancel

### 8.1. State and Operational Meaning Table

| Event | What the subscriber receives | What is / is not guaranteed |
|---|---|---|
| `onSubscribe` | A `Subscription` | CQL initialized on driver side; does not prove rows arrived |
| `request(n)` | Cumulative demand | Does not guarantee the server scans only `n` rows |
| `onNext(row)` | One `ReactiveRow` | Data comes from fetched pages; not a cluster-wide snapshot |
| `onComplete()` | Normal completion, no more rows | SELECT exhausted per query; write acknowledged per CL |
| `onError(e)` | Terminal error | **Partial rows** may already have emitted; mutations may have unknown outcome |
| `cancel()` | `onComplete` not required | Subscriber stops caring; **never rolls back** Cassandra |
| `session.closeAsync()` / `close()` | Closes `CqlSession` pools/resources | Never use to "cancel one query" on a shared session |

A subscriber receives at most **one terminal event**: `onComplete` or `onError`. `cancel()` does not mandate an `onError(CancellationException)`. In Reactor, `doFinally(signalType)` reports `CANCEL` so you can observe cancellations and release **pipeline-owned** resources.

### 8.2. Cancel Does Not Guarantee Server Work Stops

Suppose a frontend views 20 rows and closes the tab:

~~~text
HTTP client disconnects
  -> WebFlux/Reactor calls upstream subscription.cancel()
  -> Driver stops emitting rows and can stop fetching new pages
  -> Pages/requests already sent to coordinator may still finish
  -> App's shared CqlSession/pool stays alive for other requests
~~~

Never assume:

- Cassandra halted all processing on replicas.
- Already-sent mutations rolled back.
- Server CPU/I/O wasn't already spent.
- Cancel acts like `DELETE`/`TRUNCATE` or removes paging state on disk.

For `SELECT`, cancellation helps **avoid consuming or fetching unneeded future pages**, though not to exact network-byte precision. For writes or LWTs, cancellation after dispatch creates an **unknown outcome** requiring idempotency or business markers before any retry.

### 8.3. Using `doFinally` Properly for Cleanup/Metrics

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger delivered = new AtomicInteger();
Flux<EventView> stream = findEvents(session, select, deviceId, day)
    .doOnNext(event -> delivered.incrementAndGet())
    .doOnError(error -> metrics.recordQueryError(error))
    .doFinally(signal -> {
        metrics.recordTermination(signal.name(), delivered.get());
        // Close per-subscription resources created outside if any.
        // NEVER close the shared session here.
    });
~~~

`metrics` is a hypothetical observability service; this snippet illustrates the pattern, not a standalone program. If a `Flux` has **multiple subscriptions** via `defer`, an `AtomicInteger` created outside the pipeline **mixes counts across subscriptions**; in production allocate per-subscription state inside `Flux.defer(() -> { AtomicInteger count = ...; return ...; })` or use Reactor Context / proper metrics operators.

### 8.4. `onError` Can Arrive After Several `onNext`s

Multi-page `SELECT` scenario:

~~~text
Page 1: onNext rows 1..100
Page 2: onNext rows 101..200
Fetch page 3: timeout / node Down
Terminal: onError(DriverTimeoutException)
~~~

Seeing 200 rows **does not mean the whole query succeeded**. If `onErrorResume(error -> Flux.empty())` turns the error into a silent completion, the app mistakes 200 rows for **the entire dataset**, producing an incomplete export.

If business rules permit partial results, **surface partial/incomplete status explicitly** via the API/protocol and checkpoints rather than swallowing errors. If retrying the whole query after partial delivery, subscribers can see **duplicate rows**; deduplicate by primary key or use tested resumable paging/checkpoints.

### 8.5. Driver Timeout vs. Full-Stream Timeout

`basic.request.timeout` / `Statement.setTimeout(Duration)` bounds driver requests per version semantics, yet a long multi-page or multi-query stream can exceed business deadlines. Enforce an **end-to-end application deadline**.

In Reactor:

~~~java
import java.time.Duration;

Flux<EventView> bounded = findEvents(session, select, deviceId, day)
    .timeout(Duration.ofSeconds(2));
~~~

`Flux.timeout(Duration)` normally limits **the idle gap between consecutive signals**, **not a strict two-second wall-clock cap for the entire stream** if rows keep trickling in. For a hard wall-clock deadline, use context/framework timeouts or a shared timer with `takeUntilOther`/verified cancellation—never reset the budget on every page.

**On timeout/cancel:** Java stops consuming, while Cassandra continues handling already-received work. Never treat timeout/cancel as a rollback guarantee.

## 9. `CqlSession` and Resource Lifecycles

### 9.1. A Session Is Not One Query Result

`CqlSession` owns connection pools, topology/schema metadata, the prepared-statement cache, and network state. `ReactiveResultSet` represents **one individual query result**. Therefore:

- Create **one long-lived session** per application/service; never create a session per subscriber, row, or HTTP request.
- `ReactiveResultSet` is **single-subscription** with its own short lifecycle.
- When `cancel()`ling a query, **never close the shared session** used by other requests.
- On app shutdown, stop admitting new requests, drain in-flight work within bounds, and then **close `CqlSession`** via the framework lifecycle.
- Closing the session while a publisher still awaits subscription or page fetches breaks queries; manage ownership and lifecycles explicitly.

### 9.2. Bean Configuration Pattern in Spring Boot

With Spring Boot:

~~~java
// Lifecycle illustration only; application/config classes and credentials
// must match your BOM and actual environment.
//
// @Bean(destroyMethod = "close")
// CqlSession cassandraSession(DriverConfigLoader config) {
//     return CqlSession.builder().withConfigLoader(config).build();
// }
~~~

In Spring Data Cassandra, auto-configuration may already manage `CqlSession`; **avoid creating extra duplicate sessions** that spawn redundant connection pools and schema listeners. Framework-managed beans close on app shutdown—never close them inside per-request `doFinally` hooks.

### 9.3. Pipeline-Scoped Resources and `doFinally` / `usingWhen`

If each request allocates a temporary file, lease, buffer, or outbound stream, release it across all three outcomes: **complete, error, and cancel**. Reactor's `doFinally` or `usingWhen` binds cleanup to subscription lifecycles. Still, cleaning up Java resources **never** implies Cassandra mutations rolled back.

Conceptual example:

~~~java
Flux<EventView> flow = findEvents(session, select, deviceId, day)
    .doFinally(signalType -> {
        // COMPLETED / ON_ERROR / CANCEL in Reactor.
        // Record metrics; release per-request resources.
    });
~~~

Never wrap `CqlSession` in `try-with-resources` inside a service method returning `Flux`, because the `try` block closes the session **before the publisher is ever subscribed to**. Manage sessions at application lifetime, or use a reactive resource scope aligned with subscriber lifetimes.

## 10. Result Metadata and LWTs in `ReactiveResultSet`

### 10.1. Two Metadata Layers

Alongside rows, `ReactiveResultSet` exposes metadata publishers:

~~~java
Publisher<? extends ColumnDefinitions> getColumnDefinitions();
Publisher<? extends ExecutionInfo> getExecutionInfos();
Publisher<Boolean> wasApplied();
~~~

Corresponding to:

- **ColumnDefinitions:** schema of result columns.
- **ExecutionInfos:** driver execution/page metadata, including coordinator and request info.
- **wasApplied:** conditional LWT outcome, or API-defined convention for non-conditional CQL.

Per Java Driver documentation, metadata publishers **cannot complete before the main query result completes**; if the main query errors, metadata publishers emit that same error. Therefore, never subscribe only to metadata and wait for it while nothing consumes the source rows.

### 10.2. Subscribe to the Result Once, Then Read Metadata

~~~java
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

ReactiveResultSet rs = session.executeReactive(selectStatement);

// Source rs is subscribed EXACTLY ONCE:
Mono<Void> rowsCompleted = Flux.from(rs).then();

Mono<Void> printInfo = rowsCompleted.thenMany(
        Flux.from(rs.getExecutionInfos()))
    .doOnNext(info ->
        System.out.println("Coordinator=" + info.getCoordinator()))
    .then();

// When caller subscribes to printInfo, it drains rows first,
// then subscribes to metadata. Use block() ONLY in CLI/tests.
// printInfo.block();
~~~

This example **intentionally discards row contents** to showcase metadata. In real apps, map and process rows inside the same pipeline before reading summary metadata. **Never subscribe `rowsCompleted` separately and then subscribe `printInfo`**: that subscribes to `rs` twice and fails.

On `ReactiveRow`, you can also inspect per-row info:

~~~java
Flux.from(session.executeReactive(selectStatement))
    .doOnNext(row -> {
        // Metadata for that row/page; never log every row under heavy load.
        var coordinator = row.getExecutionInfo().getCoordinator();
    });
~~~

`var` requires Java 10+; on Java 8 declare `Node` explicitly. Never infer from this variable which replicas the coordinator contacted; Cassandra handles CL and replication.

### 10.3. Reading `wasApplied()` for LWTs

Suppose a prepared statement runs `INSERT ... IF NOT EXISTS`:

~~~java
ReactiveResultSet rs = session.executeReactive(conditionalWrite);

Mono<Boolean> applied = Flux.from(rs)
    .then(Mono.from(rs.wasApplied()));
~~~

This pipeline consumes the primary result and then reads `wasApplied` metadata (without subscribing to the result twice). Outcomes:

- `true`: condition applied per LWT response.
- `false`: CAS condition did not hold—**not a network error**.
- `onError`: classify timeout/unavailable/unknown outcome; never assume `false`.

To inspect existing columns returned when CAS is `false`, handle `ReactiveRow`s emitted by the query and check `ColumnDefinitions`; returned columns **depend on LWT type, schema, and version**. On `UPDATE ... IF EXISTS` false, usually only `[applied]` returns; on `INSERT IF NOT EXISTS` false, existing row columns may return. Never assume every LWT returns the full entity.

**Note:** for non-LWT statements, `wasApplied` may return `true` by API convention; **never use it to prove `CREATE TABLE IF NOT EXISTS` just created a brand-new table**.

## 11. Multiple Subscribers, Caching, Sharing, and Stale Data Risks

### 11.1. Three Different Strategies

| Goal | Technique | When to use | Risk |
|---|---|---|---|
| Each subscriber **runs a new query** | `Flux.defer(() -> Flux.from(session.executeReactive(stmt)))` | Each HTTP request reads current state | Two executions, data may differ, higher load |
| Two downstream observers share **one execution** | `Flux.from(rs).publish()` with coordinated connect | Compute two aggregates simultaneously on one stream | Late subscribers can miss rows; requires coordination |
| Multiple subscribers read **cached results** | `Flux.from(rs).cache()` | Small, strictly bounded result sets | Can retain all rows in RAM and serve stale data |

**No single solution** fits all three needs. If two endpoints reuse an already-subscribed `ReactiveResultSet`, that is not caching: the second subscription fails.

### 11.2. Example Caching a Small Set

~~~java
import reactor.core.publisher.Flux;

// Sensible ONLY when the query has a small LIMIT and non-sensitive data.
Flux<String> cached = Flux.from(session.executeReactive(
        "SELECT status FROM stream_lab.device_status_by_id " +
        "WHERE device_id = 11111111-1111-4111-8111-111111111111"))
    .map(row -> row.getString("status"))
    .cache();

// Subsequent subscriptions to "cached" replay from Reactor's cache.
// The driver source gets only one subscription, avoiding unicast errors.
~~~

**Distinction:** `cache()` never refreshes Cassandra when a new subscriber arrives; results can go stale. By default `cache()` has no size bound, so using it on a million-row SELECT can trigger OOM and pin sensitive payloads in RAM longer than retention rules allow. Prefer explicit TTL/size-bounded caches at the right layer or separate queries.

### 11.3. Multicast Is Not Replay

~~~java
Flux<String> shared = Flux.from(session.executeReactive(
        "SELECT status FROM stream_lab.device_status_by_id " +
        "WHERE device_id = 11111111-1111-4111-8111-111111111111"))
    .map(row -> row.getString("status"))
    .publish()
    .autoConnect(2);
~~~

This waits for **two subscribers** before subscribing upstream, avoiding single-subscription errors. Yet it is **multicast**, not replay for latecomers; both subscribers must register in coordination. **Never call `shared.blockLast()` sequentially twice expecting it to run**: the first call blocks waiting for the second subscriber and hangs forever.

For large exports, streaming multicast cuts RAM vs. `cache()`, yet still requires policies for slow subscribers, backpressure, cancellation, and stream-wide errors. One very slow subscriber can throttle the shared stream.

### 11.4. Retrying via `defer`: Each Retry Runs a Fresh Query

~~~java
// Concept for idempotent SELECTs; do not run without a timeout policy.
Flux<EventView> retryable = Flux.defer(() ->
        Flux.from(session.executeReactive(readStatement)))
    .map(row -> new EventView(
        row.getInstant("event_time"),
        row.getUuid("event_id"),
        row.getString("payload")));

// If retryWhen is attached, it re-subscribes to "defer" and runs a new query.
// Must enforce max attempts, jittered backoff, and a business deadline.
~~~

If an error hits **after two pages already emitted**, retrying the full query re-emits older rows, **creating duplicates downstream**. For export/ETL pipelines, use primary-key resume tokens/checkpoints, verified paging states, deduplication, or transactional sinks. Never slap `retry(3)` onto a stream and call it exactly-once.

## 12. CQL and Java Lab: Observing Real Subscriptions

### 12.1. Environment Setup

Examples assume a **lab cluster** of Apache Cassandra 4.x/5.x with datacenter `dc1` and **three nodes** for RF=3 with `LOCAL_QUORUM`. On a single-node lab, adjust RF/CL to match reality. Never run fault injection on production.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

In `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS stream_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS stream_lab.events_by_device (
  device_id uuid,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS stream_lab.device_status_by_id (
  device_id uuid PRIMARY KEY,
  status text
);

INSERT INTO stream_lab.device_status_by_id (device_id, status)
VALUES (11111111-1111-4111-8111-111111111111, 'ACTIVE');
~~~

`IF NOT EXISTS` **does not alter an existing keyspace/table schema**. Before testing, check `DESCRIBE KEYSPACE stream_lab` and `DESCRIBE TABLE stream_lab.events_by_device`; the datacenter name must match your topology. Using one fixed partition makes inspection easy, but never use it as a cluster-wide performance benchmark.

### 12.2. Insert Six Events to Observe Paging and Cancellation

~~~sql
INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:00:00Z',
  22222222-2222-4222-8222-000000000001, 'sample-1');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:01:00Z',
  22222222-2222-4222-8222-000000000002, 'sample-2');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:02:00Z',
  22222222-2222-4222-8222-000000000003, 'sample-3');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:03:00Z',
  22222222-2222-4222-8222-000000000004, 'sample-4');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:04:00Z',
  22222222-2222-4222-8222-000000000005, 'sample-5');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:05:00Z',
  22222222-2222-4222-8222-000000000006, 'sample-6');

SELECT event_time, event_id, payload
FROM stream_lab.events_by_device
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Because clustering order is `event_time DESC`, `SELECT` returns newer events first. All IDs and payloads are **synthetic sample data**, representing no real users or tokens.

### 12.3. `StepVerifier` Test Starting With Demand 0

Create a Reactor test using `reactor-test` matching your Reactor version/BOM:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

UUID deviceId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111");
LocalDate day = LocalDate.of(2026, 11, 21);

Flux<EventView> stream = findEvents(session, select, deviceId, day);

StepVerifier.create(stream, 0L) // Start with zero row demand.
    .expectSubscription()
    .thenRequest(1)
    .expectNextCount(1)
    .thenRequest(2)
    .expectNextCount(2)
    .thenCancel()
    .verify();
~~~

Expected behavior:

- The subscriber receives **at most 1 row** before granting 2 more demand, honoring Reactive Streams.
- 3 rows total are observed, then the subscription is cancelled.
- **At least three rows** must exist in the lab source. If TTL/deletes removed rows or the wrong partition was queried, the test terminates early.
- Cancelling does not delete the remaining three rows in Cassandra; we simply stopped consuming that query.
- Even with `pageSize=2`, demand governs how many rows may be **emitted**, not necessarily how many rows the server scanned or returned in one page.

This test verifies the contract; to observe actual page fetches, use metrics or tracing rather than inferring from `expectNextCount(3)`.

### 12.4. Test Completion After Reading Full Results

~~~java
StepVerifier.create(
        findEvents(session, select, deviceId, day)
            .map(EventView::eventId))
    .expectNextCount(6)
    .verifyComplete();
~~~

The lab passes only if those six rows exist and no leftover rows from prior runs share that partition. Between runs, **use a fresh partition key or clean up the lab cleanly**, rather than treating 6 as a fixed truth over mutated data.

### 12.5. Testing Multiple Subscribers

~~~java
ReactiveResultSet rs = session.executeReactive(readStatement);
Flux<ReactiveRow> once = Flux.from(rs);

// In a standalone test with seeded data:
// StepVerifier.create(once).expectNextCount(6).verifyComplete();
// StepVerifier.create(once).expectError(IllegalStateException.class).verify();
~~~

The second attempt fails because **the same `ReactiveResultSet` was subscribed again**, not because Cassandra "ran out of rows." To test running a fresh query per subscription, use:

~~~java
Flux<ReactiveRow> freshEachTime =
    Flux.defer(() -> Flux.from(session.executeReactive(readStatement)));
~~~

Or cache only when the row set is **small and strictly bounded**, never turning a streaming query into a full-table cache.

### 12.6. Testing Empty Writes and Completion

~~~java
import reactor.core.publisher.Mono;

// insertStatement properly prepared/bound against lab data.
Mono<Void> completedWrite = Flux
    .from(session.executeReactive(insertStatement))
    .then();

StepVerifier.create(completedWrite)
    .verifyComplete();
~~~

Do not write `expectNextCount(1)` to verify an INSERT: unconditional mutations **do not emit a row**. For LWTs, inspect `wasApplied` separately rather than equating `onComplete` with condition success. If a write times out, expect `onError`/unknown outcome, never assuming rollback.

### 12.7. Testing Mid-Paging Failures

With an authorized lab proxy/cluster, inject a timeout while fetching the next page. Record:

1. Rows observed by the subscriber before `onError`.
2. Rows persisted/exported to the sink.
3. Did `onComplete` fire? (No, if the stream terminated with `onError`.)
4. If retried from the start, did duplicate row IDs appear?
5. Full export deadline, retry/attempt counts, and CPU/network/driver pools.

**Never** write `onErrorResume(error -> Flux.empty())` "to keep dashboards green," as that turns a partial export into a fake success. Always surface explicit partial/incomplete status or enforce idempotent checkpoint resumption.

## 13. Observability and Operational Optimization

### 13.1. Measure Consumer, Driver, and Cluster Together

| Layer | Metrics to track | Why it matters |
|---|---|---|
| **Subscriber / Reactor** | Subscription starts, rows received, request batches, cancellations, completions, errors | Reveals whether the app consumes fully or aborts early |
| **Demand / Buffers** | Pending rows, prefetch, queue depth, `limitRate`, concurrency | Spots bloated operator buffers or slow subscribers |
| **Java Driver** | Requests/s, in-flight, throttling queue/delay, `pool.available-streams`, page latencies | Proves whether DB/network is bottlenecked |
| **Cassandra** | Read/write p95/p99, dropped messages, CPU, GC, tombstones scanned, compaction backlog | Separates slow subscribers from slow queries/storage |
| **Business** | Actual exported rows, end-to-end duration, partial exports, duplicate side effects | Goes beyond "stream threw no exception" |

Java Driver metrics may be **disabled by default**; enable specific metrics per version and measure overhead. Never treat `onNext/s` and `CQL requests/s` as equivalent units: one query can produce many rows/pages, whereas a write produces zero rows.

### 13.2. Request Timeouts and Backpressure Do Not Replace SLAs

If a consumer is very slow, even though `request(n)` paces `onNext`, total export duration climbs. Causes may include:

- Starved demand because the subscriber is blocked.
- `publishOn` prefetching too much / growing queues.
- Partitions heavy with tombstones or returning very few rows per page.
- WAN/TLS/JVM GC overhead or slow coordinators.
- Too many concurrent writes with zero upstream backpressure.

Measure **end-to-end latency and page counts** before tuning page size or retries. Making `pageSize` too small adds round-trips; making it too large balloons memory and response sizes. Split across partitions/keyspaces when needed, but never change a partition key just to mask a blocking subscriber.

### 13.3. Prevent Accidental Double Subscriptions at the Framework Layer

Patterns that trigger double execution:

~~~text
ReactiveResultSet rs = session.executeReactive(statement)
  -> Flux.from(rs) returned to HTTP
  -> another service also subscribes for audit
  => second subscriber errors

Flux.defer(() -> Flux.from(session.executeReactive(statement)))
  -> HTTP subscribes
  -> audit subscribes
  => two separate CQL executions (no error, doubles load)
~~~

To audit the same request, attach a side-effect operator inside **one pipeline**, or emit a standardized event via an outbox/service with explicit semantics. **Never let a secondary subscription accidentally re-run an `INSERT` or LWT**.

## 14. Real-World Scenarios and Exercises

### Exercise 1 — Can Unsubscribed Writes Execute?

Code calls `session.executeReactive(insertStatement)` and discards the return value. Logs say "sent successfully." Is the row guaranteed written?

**Answer:** No. `ReactiveResultSet` is a cold publisher; without a subscription, the query is never triggered under the reactive API.

### Exercise 2 — Does `request(2)` Make the Server Read Only Two Rows?

A subscriber calls `request(2)`. The API author claims Cassandra scans strictly 2 rows, so server cost equals 2 rows. True?

**Answer:** False. Demand bounds `onNext` item emissions, while Cassandra's native protocol and driver operate in **pages**. One page can hold many rows, and the server may scan far more than requested.

### Exercise 3 — `request(0)` to Pause?

A subscriber calls `request(0)` when a queue fills. Why is this wrong?

**Answer:** Requested elements must be positive. Per the Reactive Streams spec, non-positive requests violate the contract and signal `onError(IllegalArgumentException)` if still active. To pause, simply stop issuing new demand while keeping queues bounded.

### Exercise 4 — Does Cancel Delete Data?

A client disconnects after 4 of 100 rows. The app calls `cancel()` and assumes Cassandra completely aborted the CQL query and immediately reclaimed cluster resources. What is accurate?

**Answer:** Cancellation stops further emissions/fetches once observed, but **does not guarantee** halting already-in-flight coordinator requests and never rolls back mutations. `CqlSession` remains a shared app resource.

### Exercise 5 — Why Did the Second Subscribe Fail?

Two components share one `ReactiveResultSet`; the second subscriber gets `IllegalStateException`. Is Cassandra down?

**Answer:** No; that is the **single-subscription** constraint. Use an intentional multicast/caching pipeline, or create a new result set per subscriber when re-querying is desired.

### Exercise 6 — Write Without `onNext`

A reactive `INSERT` signals `onComplete` with zero `onNext`s. A developer concludes the write failed. Right or wrong?

**Answer:** Wrong. Normal CQL mutations return no rows; normal completion indicates a successful response per CL. Handle `onError` and unknown outcomes separately rather than checking row count == 0.

### Exercise 7 — `flatMap` With Unbounded Concurrency

A job builds 200,000 INSERT publishers, uses unbounded `flatMap`, and the cluster reports overloaded. Does Cassandra lack reactive support?

**Answer:** No. Cassandra has no wire-level Reactive Streams write demand; you must bound in-flight writes, apply ingress backpressure, enforce retry budgets, and account for multi-instance load. Use `flatMap(..., concurrency)` or `concatMap` when order matters.

### Exercise 8 — Partial Results With Swallowed Errors

An export receives 2 pages, page 3 errors, and the pipeline uses `onErrorResume(e -> Flux.empty())` returning HTTP 200 with 200 rows. What is the risk?

**Answer:** The system reports completion despite **missing data**. Surface partial/error status explicitly, or use checkpoints and idempotent retries for completeness—never hide errors behind completion.

### Exercise 9 — Caching an Entire Table for Two Subscribers

A team adds `Flux.from(rs).cache()` to a query returning millions of rows. What goes wrong?

**Answer:** Reactor can buffer every row in RAM, causing OOM or keeping data stale too long; bound queries, use properly bounded caches, or stream multicast. If two independent executions are desired, use `Flux.defer` and budget the DB cost.

### Exercise 10 — Is Reactor Timeout a Full-Stream Deadline?

A pipeline uses `.timeout(Duration.ofSeconds(2))`, and rows trickle in every second for an hour. Will the stream stop after 2 seconds total?

**Answer:** No. This operator normally times out **gaps between consecutive signals**. Business-level deadlines require an absolute wall-clock deadline/budget rather than resetting on each row or page.

### Completion Checklist

- [ ] Can distinguish `Publisher`, `Subscriber`, `Subscription`, and `Processor`.
- [ ] Knows the `onSubscribe` → `onNext*` → `onComplete/onError` sequence; `cancel()` is not a terminal signal.
- [ ] Understands `request(n)` is cumulative, must be positive, and never exceeded.
- [ ] Knows Driver 4.x `ReactiveResultSet` defaults to cold/unicast/single-subscription-only.
- [ ] Never discards cold publishers returned by `executeReactive` when writes are required.
- [ ] Never manually subscribes in a WebFlux handler while also returning the `Flux`.
- [ ] Knows `Flux.defer` runs a **new query** per subscription; `cache/publish` shares one execution within bounds.
- [ ] Knows demand paces **page fetching** rather than forcing the server to read strictly `n` rows.
- [ ] Distinguishes `request(n)`, `take(n)`, `limitRate(n)`, CQL `LIMIT n`, and `setPageSize(n)`.
- [ ] Never treats an `INSERT` as failed simply because no `onNext` fired.
- [ ] Enforces concurrency/backpressure caps on ingress when dispatching writes.
- [ ] Knows cancellation neither rolls back mutations nor closes the shared session.
- [ ] Knows query metadata publishers complete only when the main result completes; never subscribes to main result twice.
- [ ] Handles errors/timeouts, partial results, and retries without unintended duplicates.
- [ ] Tested `StepVerifier` with initial demand 0, incremental requests, completion, and cancellation.
- [ ] Measures p95/p99, in-flight writes, memory buffers, subscriptions, cancels/errors, and actual rows processed.

## 15. References

1. Apache Cassandra Java Driver 4.19 — [Reactive Streams](https://apache.github.io/cassandra-java-driver/4.19.0/core/reactive/): cold publishers, single-subscriber limits, writing SELECT/INSERT, backpressure, caching, retries.
2. Apache Cassandra Java Driver 4.19 — [ReactiveResultSet API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveResultSet.html): `Publisher<ReactiveRow>` and `ReactiveQueryMetadata`.
3. Apache Cassandra Java Driver 4.19 — [ReactiveSession API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveSession.html): `executeReactive(String/Statement)`.
4. Apache Cassandra Java Driver 4.19 — [ReactiveRow API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveRow.html): row values and execution metadata.
5. Apache Cassandra Java Driver 4.19 — [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): page size, paging state, and page fetch paths.
6. Apache Cassandra Java Driver 4.19 — [Async Programming](https://apache.github.io/cassandra-java-driver/4.19.0/core/async/): comparing `CompletionStage`/`AsyncResultSet` with reactive consumption.
7. Reactive Streams JVM Specification — [Publisher/Subscriber/Subscription rules](https://github.com/reactive-streams/reactive-streams-jvm): `request(n)`, terminal signals, cancellation, and thread-safety.
8. Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Flux.defer`, `flatMap` concurrency, `concatMap`, `limitRate`, `cache`, `publish`, `doFinally`, `StepVerifier`.
9. Spring Data Cassandra — [Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): composition vs. execution, reactive repositories/templates, and driver integration.
10. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) and [Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): partition keys, clustering order, `LIMIT`, and consistency.
