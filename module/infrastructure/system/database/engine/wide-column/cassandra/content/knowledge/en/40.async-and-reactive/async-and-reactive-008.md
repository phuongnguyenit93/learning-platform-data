# Reactive API, Publishers, and Driver Support Conditions When Querying Apache Cassandra

## 1. The Problem: "Non-Blocking" Does Not Automatically Mean "Reactive"

In the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, Java applications interact with CQL, **partition keys**, replication, consistency levels, compaction, and repair across distributed Apache Cassandra. When an app queries many partitions or streams data continuously over HTTP/gRPC, how results are consumed directly impacts **in-flight requests, memory, coordinator/replica load, and tail latency**.

Three execution styles are commonly discussed:

- **Synchronous:** `session.execute(statement)` returns `ResultSet`; the calling thread may wait on network I/O.
- **Asynchronous:** `session.executeAsync(statement)` returns `CompletionStage<AsyncResultSet>`; the app handles results via callbacks/futures and explicitly manages pages.
- **Reactive:** when supported by the driver's API, `session.executeReactive(statement)` exposes results as a **Reactive Streams `Publisher`**, letting the consumer drive item demand rather than materializing a huge list upfront.

**Lesson objectives** in the **Async and Reactive** chapter:

1. Explain `Publisher`, `Subscriber`, `Subscription`, and the `request(n)` signal.
2. Identify the **driver version, library, and API type prerequisites** needed to genuinely use the Reactive API.
3. Connect prepared/bound CQL statements to `Publisher` and Reactor `Flux` when that integration is available.
4. Distinguish **row-level demand** from page size, server requests, bytes, and end-to-end rate limits.
5. Understand cancellation, cold publishers, multiple subscribers, error handling, and timeouts.
6. Avoid `block()`, `collectList()`, or unbounded fan-out that defeat reactive benefits.
7. Relate reactive execution to token-aware routing, CL, tombstones, replica load, and Cassandra resources.
8. Write tests and operational runbooks for reactive workloads.

> **Reactive does not automatically make CQL faster or make a partition-key-less query valid.** It primarily changes how Java consumes results, coordinates concurrency, and expresses backpressure.

## 2. What Happens Along a Query's Execution Path?

~~~mermaid
flowchart LR
    A["HTTP/gRPC or job"] --> B["Reactive Subscriber"]
    B -->|"request(n)"| C["Java Driver Publisher"]
    C --> D["Cassandra Coordinator"]
    D --> E["Replicas by token, RF, and CL"]
    E --> D
    D -->|"CQL pages"| C
    C -->|"onNext(Row), onError, onComplete"| B
    B --> F["Bounded processing/output"]
    G["Rate limit / max concurrency / deadline"] -.-> B
    H["Disk, SSTables, compaction, repair"] -.-> E
~~~

CQL requests still flow through a coordinator and replicas. The driver may fetch one or more **pages** to serve rows while the Subscriber requests individual **rows**. You cannot assume `request(1)` maps to one network CQL request, one byte of data, or one disk read I/O.

A query scanning a wide partition can still consume heavy server resources before a single row ever reaches the client.

## 3. Four Reactive Streams Interfaces to Distinguish

Reactive Streams for the JVM uses interfaces in the `org.reactivestreams` package:

| Component | Role | Practical rule |
|---|---|---|
| `Publisher<T>` | Source capable of emitting items `T` | Emits items per subscription according to contract |
| `Subscriber<T>` | Consumer receiving signals from a source | Must receive `onSubscribe` before any `onNext` |
| `Subscription` | Link between one publisher and one subscriber | Exposes `request(long n)` and `cancel()` |
| `Processor<T,R>` | Both Subscriber and Publisher transforming a stream | Not required just to read Cassandra results |

Key signals:

1. `onSubscribe(subscription)`: Subscriber receives the `Subscription`.
2. `subscription.request(n)`: Subscriber signals **the maximum additional items it wants**; `n > 0`.
3. `onNext(item)`: Publisher emits an item within current demand.
4. `onError(error)`: signals failure, terminating the stream.
5. `onComplete()`: normal stream completion.
6. `subscription.cancel()`: consumer needs no more items.

After `onError` or `onComplete`, the stream has terminated; no further `onNext` events should occur per contract.

**`request(0)` and negative numbers are not valid pause signals**. To pause, simply **stop requesting more**; to stop permanently, call `cancel()`.

### 3.1. Backpressure Is Control Over Item Demand

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    participant D as Driver / Coordinator
    S->>P: subscribe
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P->>D: Fetch if needed
    D-->>P: One result page
    P-->>S: onNext(row1)
    P-->>S: onNext(row2)
    Note over S,P: Emits no more rows without further demand
    S->>P: request(1)
    P-->>S: onNext(row3)
    S->>P: cancel()
    Note over D,P: Cancellation does not guarantee server aborted in-flight work
~~~

Libraries like Reactor and RxJava add hundreds of operators, yet **Reactive Streams is the lower-level contract**; not every `Publisher` is a Reactor `Flux`, and Reactor is not a built-in component of the Cassandra server.

### 3.2. Reactive Streams Is Not Java `Flow.Publisher`

Java 9 introduced `java.util.concurrent.Flow.Publisher`, whereas many Java Driver 4.x APIs and Reactor use `org.reactivestreams.Publisher`. They share similar concepts, yet **are distinct Java types** and must not be cast directly to one another.

If a project uses `Flow.Publisher`, use a version-compatible adapter. Do not assume `executeReactive` returns `Flow.Publisher` merely because the project runs on JDK 17.

## 4. Support Conditions by Java Driver and Application Stack

### 4.1. Verify the API Before Writing Code

When documentation mentions "reactive Cassandra," first identify **the exact driver**:

| Case | What to verify |
|---|---|
| **Java Driver 4.x supporting Reactive API** | `CqlSession.executeReactive(...)`, reactive result types, and exact package in the artifact used |
| **Java Driver 3.x** | Lacks Driver 4.x Reactive APIs/examples by default; check major-version docs |
| **Vendor-managed distributions/drivers** | Compatibility matrix, version, and supported/licensed APIs |
| **Spring Data Cassandra reactive** | Compatibility across Spring Data, Spring Framework, driver, and Reactor; repository abstractions don't fit every driver version |
| **Apps using only `executeAsync`** | `CompletionStage` is an async API, not yet a demand-aware `Publisher` |
| **Apps using Java Flow API** | Check adapters; never cast between the two Publisher interfaces |

The examples below assume **a Driver 4.x release providing `executeReactive`**. If your IDE/compiler reports missing methods or types, verify **artifact, version, imports, and compatibility matrix** instead of adding casts or copying code from another major version.

Some driver releases/branches have changed **maintainers, Maven coordinates, and support policies**. Always take group/artifact IDs from the documentation of the exact release you use; never assume all 4.x releases share identical Maven coordinates or support identical JVM/Cassandra versions.

### 4.2. Distinguish Required vs. Optional Dependencies

- **Driver core**: provides `CqlSession` and execution APIs, including the Reactive API if supported in that release.
- **Reactive Streams interfaces**: `Publisher`, `Subscriber`, `Subscription`. Check transitive dependencies pulled by your driver version rather than dumping every "reactive" library onto the classpath.
- **Project Reactor** (`reactor-core`): **optional**, for `Flux`, `Mono`, and `StepVerifier` (`StepVerifier` lives in `reactor-test`).
- **RxJava**: an alternative if the app already uses it; must use compatible Reactive Streams adapters/versions.
- **Spring WebFlux / Spring Data**: higher-level frameworks; unnecessary for native driver examples.

Verify compatibility across **all three axes**: Java/JDK, Java Driver ↔ Cassandra server/protocol, and libraries/frameworks ↔ driver. Running Cassandra 4.x **does not automatically dictate** which Java Driver 4.x release you must pick.

### 4.3. Operational Prerequisites Beyond Dependencies

The Reactive API only helps when:

- CQL queries have proper partition keys and access patterns.
- Explicit policies exist for **page size, LIMIT, timeouts, and CL**.
- Limits govern **concurrency, retries, and concurrent subscriptions**.
- Downstream processing does not block indefinitely or collect every row into the heap.
- The app observes `onError` and cancellation instead of using fire-and-forget `subscribe()` calls that drop errors.
- Sessions are reused per lifecycle with proper local DC, auth, and TLS.

Without those safeguards, reactive code can **increase** cluster load simply because spawning subscriptions looks effortless.

## 5. Comparing Synchronous, Asynchronous, and Reactive APIs

| Property | `execute` | `executeAsync` | `executeReactive` (when supported) |
|---|---|---|---|
| Interface | `ResultSet` | `CompletionStage<AsyncResultSet>` | `Publisher` of result rows |
| Consumption | `one()` / iterator | `currentPage()` and `fetchNextPage()` | Subscriber/request or Reactor operators |
| Does calling thread wait? | May block on call/page fetch | Does not wait; uses callbacks | Driven by subscription and signals |
| Demand control | Consumer pulls rows; sync paging | App decides when to fetch next page | Demand via `request(n)` |
| Heap control | Iterate streaming instead of `all()` | Do not accumulate current pages | Backpressure; avoid `collectList()` |
| Error handling | Exception thrown | Failed future | `onError` |
| Mid-stream stop | Stop iterating; fetched effects remain | Stop fetching next pages; manage future | `cancel()` and lifecycle rules |
| Is one CQL request cheaper? | Not by default | Not by default | Not by default |
| Best fit | CLI / small services | Async workflows with clear page steps | Multi-item streams with downstream demand |

**Reactive fits best when downstream is reactive** (WebFlux, Reactor pipelines), though synchronous services need not be forced onto `Publisher`. Base the choice on concurrency, observability, readability, and operational cost.

## 6. Creating a Practice Table with a Proper Partition Key

Assume a **lab** cluster, datacenter `dc1`, and enough replicas for RF=3:

~~~cql
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Query:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

Here:

- Partition key = `(device_id, event_day)`: binding both enables driver token-aware routing.
- Clustering key = `event_time`: supports newest-first reads within the partition.
- `LIMIT` caps **total rows** for the query.
- `page size` sets the **target rows** per server response page.
- `LOCAL_QUORUM` sets replica acknowledgment requirements; it **does not make Reactor process rows faster**.

Sample rows:

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    24.6,
    'OK'
);

INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T08:31:00Z',
    24.8,
    'OK'
);
~~~

These examples are strictly for lab practice; never recreate production keyspaces or use admin credentials in HTTP endpoints.

## 7. Native Reactive API: From BoundStatement to Publisher

### 7.1. Prepare the Statement Once

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, reading_value, status " +
    "FROM telemetry_lab.readings_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT ?"
);

UUID deviceId = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");
LocalDate eventDay = LocalDate.of(2026, 11, 21);

BoundStatement statement = prepared
    .bind(deviceId, eventDay, 100)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(25);

// Use only when your driver version provides the Reactive API:
var publisher = session.executeReactive(statement);
~~~

This snippet uses `var` (Java 10+). `session` is a reused `CqlSession` already configured with contact points, local DC, and TLS/auth. Older Java versions use the explicit return type from your driver API.

`PreparedStatement` fixes the **CQL shape and typed bind markers**, and helps the driver extract partition-key routing metadata when available. The Reactive API does not replace bind parameters or prevent CQL injection if code concatenates raw input into query strings.

### 7.2. A Publisher Is Not a List

Reactive results are a **row stream** per subscription, not an already-loaded `List<Row>`. Never assume:

~~~java
// CONCEPTUALLY WRONG:
List<Row> allRows = session.executeReactive(statement);
~~~

To consume rows, **subscribe**, or adapt to a Reactive Streams library like Reactor:

~~~java
// Illustration when reactor-core is on the classpath:
Flux.from(session.executeReactive(statement))
    .subscribe(row -> {
        System.out.println(row);
    });
~~~

This is only a quick data-flow demo. In real services, standalone `subscribe` detaches errors and lifecycle from the HTTP caller; instead **return the publisher/`Flux` to the calling layer or use a managed subscriber**.

### 7.3. Do Not Treat `executeReactive` as a Continuous Server Push Stream

Cassandra still executes a **bounded CQL query**, typically delivered in pages. The Publisher lets the client consume rows on demand; the server is not a message broker streaming future inserts forever.

If you need a continuous **change stream**, look at CDC, event logs, or another architecture. A reactive `SELECT` does not automatically emit mutations inserted after the query began.

## 8. Using Subscriber to Understand `request(n)` and `cancel()`

To see demand mechanics directly, you can implement a `Subscriber` without Reactor. This example **focuses on lifecycle** and uses `Object` to avoid tying syntax to version-specific row wrapper types.

~~~java
import org.reactivestreams.Publisher;
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;

import java.util.concurrent.atomic.AtomicBoolean;

public final class DemandSubscriber implements Subscriber<Object> {
    private Subscription subscription;
    private final AtomicBoolean stopped = new AtomicBoolean();
    private long seen;

    @Override
    public void onSubscribe(Subscription s) {
        this.subscription = s;
        s.request(1); // Request only one element initially.
    }

    @Override
    public void onNext(Object row) {
        if (stopped.get()) {
            return;
        }

        try {
            processRow(row);
            seen++;
        } catch (RuntimeException error) {
            stopped.set(true);
            subscription.cancel();
            reportFailure(error);
            return;
        }

        if (seen >= 100) {
            stopped.set(true);
            subscription.cancel();
        } else {
            subscription.request(1);
        }
    }

    @Override
    public void onError(Throwable t) {
        stopped.set(true);
        reportFailure(t);
    }

    @Override
    public void onComplete() {
        stopped.set(true);
        reportSuccess(seen);
    }

    private void processRow(Object value) {
        // Demo: short logic; never block the signal thread.
        // Real code should accept the driver's ReactiveRow type.
    }

    private void reportFailure(Throwable error) {
        System.err.println(error.getClass().getSimpleName());
    }

    private void reportSuccess(long count) {
        System.out.println("completed rows=" + count);
    }
}
~~~

Subscribe to the driver's publisher when types and generic parameters align:

~~~java
// Where BoundStatement and CqlSession are already available.
// Subscriber<Object> accepts items as Object to illustrate demand.
session.executeReactive(statement)
    .subscribe(new DemandSubscriber());
~~~

**Production warning:** this code illustrates the `request(1)` contract only—it is not a production-hardened implementation for concurrency, cancellation races, metrics, or downstream error propagation. For non-trivial processing, use Reactor operators/bounded executors and avoid blocking driver I/O threads.

### 8.1. Is Requesting One Element at a Time Optimal?

Not necessarily. `request(1)` can add more signaling/callback overhead than a moderate batch demand, whereas `request(Long.MAX_VALUE)` imposes zero demand limit and risks flooding a slow downstream.

The right choice is **demand matched to processing capacity**. In Reactor, operators manage requests and prefetching indirectly; most applications never need a custom `Subscriber`.

### 8.2. Never Call `request()` After Cancellation

Once `cancel()` is called, do not expect further data. Signals already in flight or queued can still race in some implementations, so guard state transitions and avoid non-idempotent side effects.

Never treat cancellation as a **transaction rollback**: Cassandra does not undo already-executed mutations just because a Java Subscriber stopped reading rows.

## 9. Reactor `Flux`: Mapping Rows to DTOs

### 9.1. Reactive Repository Example

An implementation using Java Driver 4.x with Reactive API and Reactor:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import reactor.core.publisher.Flux;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public final class ReactiveReadingRepository {
    private final CqlSession session;
    private final PreparedStatement query;

    public ReactiveReadingRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.query = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT ?"
        );
    }

    // Assumes a JDK supporting record; replace with a DTO class if needed.
    public record ReadingDto(
        Instant eventTime, Double readingValue, String status) {}

    public Flux<ReadingDto> find(UUID deviceId,
                                 LocalDate day,
                                 int limit) {
        if (limit < 1 || limit > 200) {
            return Flux.error(
                new IllegalArgumentException("Invalid limit"));
        }

        // defer ensures statement/Publisher creation per subscription
        // happens inside the subscriber-driven lifecycle.
        return Flux.defer(() -> {
            BoundStatement stmt = query
                .bind(deviceId, day, limit)
                .setPageSize(Math.min(limit, 50))
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            return Flux.from(session.executeReactive(stmt))
                .map(row -> new ReadingDto(
                    row.getInstant("event_time"),
                    row.isNull("reading_value")
                        ? null : row.getDouble("reading_value"),
                    row.getString("status")));
        });
    }
}
~~~

This pattern highlights:

- CQL/statements prepared **once** in the repository.
- `Flux.defer` creates a publisher only upon subscription.
- Each subscription executes a **real CQL request**; never subscribe multiple times thinking results are cached.
- The mapper reads only selected columns and preserves `null` for `double` when needed.
- `LIMIT` and page size are bounded explicitly; do not assume `Flux` restricts broad source scans by itself.
- `LOCAL_QUORUM` is a data consistency policy, not backpressure.
- Neither `block()` nor `collectList()` appears on the return path.

**Version note:** this code assumes the driver's reactive row exposes CQL getters like `getInstant`/`getDouble`/`getString`. Check `ReactiveResultSet`'s signature and element type in your artifact's Javadoc before copying into production. If your version wraps rows differently, use that version's row/getter API.

### 9.2. Keeping `Flux` at the API Boundary

With Spring WebFlux (when the full stack supports it), a controller can return:

~~~java
// Illustrative snippet: full Spring imports/configuration omitted.
@GetMapping("/devices/{id}/readings")
public Flux<ReadingDto> readings(
        @PathVariable UUID id,
        @RequestParam LocalDate day) {
    return repository.find(id, day, 100);
}
~~~

If using a nested DTO like `ReactiveReadingRepository.ReadingDto`, import or qualify it properly. This is an architectural illustration, not a drop-in controller.

**Crucial point:** the HTTP boundary does not always translate demand cleanly down to Cassandra; serialization buffers, proxies, and client sockets all affect flow. Measure memory and backpressure **end-to-end**, rather than seeing a `Flux` return type and assuming the system cannot overload.

## 10. Backpressure vs. Page Size, LIMIT, and Server Quotas

### 10.1. Five Independent Limits

| Mechanism | What it controls | What it does NOT guarantee |
|---|---|---|
| `request(n)` | Demand for at most `n` more items from Publisher | Does not equal `n` CQL requests or `n` bytes |
| `setPageSize(k)` | Target rows per page | Not a hard bytes/RAM ceiling |
| CQL `LIMIT m` | Max rows in query output | Does not cap SSTables/tombstones scanned server-side |
| Max active subscriptions | Concurrent active query streams | Does not cap bytes/query if rows are wide |
| Rate/bytes budget | Job/service QPS, rows/s, or bytes/s | Does not fix a query missing its partition key |

Example:

~~~text
Statement: LIMIT 1000, pageSize = 100
Subscriber: request(5)

Meaning:
  - CQL may return up to 1,000 rows.
  - Driver may fetch results in ~100-row target pages.
  - Publisher emits at most 5 rows under current demand.
  - Server may have computed and driver may buffer the rest of that page.
~~~

**Backpressure is not a Cassandra resource quota.** If a partition holds heavy tombstones, the server may scan thousands of entries before emitting a single row. One oversized row can also consume megabytes even under `request(1)`.

### 10.2. Reactor `limitRate` Is Not CQL LIMIT

~~~java
Flux.from(session.executeReactive(statement))
    .limitRate(32)
    .doOnNext(row -> consume(row))
    .subscribe();
~~~

`limitRate(32)` tunes how Reactor requests items from upstream; it **does not rewrite CQL to `LIMIT 32`**, does not force page size to 32, and does not cap total rows returned by the query. `consume` is an illustrative handler.

### 10.3. Avoid Unbounded `onBackpressureBuffer`

~~~java
// ANTI-PATTERN without understanding buffer bounds and downstream speed.
Flux.from(session.executeReactive(statement))
    .onBackpressureBuffer()
    .subscribe(this::slowlyConsume);
~~~

An unbounded buffer piles items onto the heap whenever downstream lags. If buffering is truly needed, specify **item/byte caps, an overflow policy, and metrics** rather than picking an operator just because its name says "backpressure."

### 10.4. Memory Calculation Example

**Hypothetical** numbers:

~~~text
Average decoded row payload = 8 KiB
Page size target            = 500 rows
Concurrent subscriptions    = 100

Approximate payload:
8 KiB × 500 × 100 = 400,000 KiB ≈ 390.6 MiB

Excluding:
  driver buffers, object overhead, DTOs,
  downstream queues, network buffers, GC headroom.
~~~

Always cap **concurrency and row size**; `request(n)` is not an "OOM-proof" guarantee.

## 11. Reactive Paging and Result Semantics Over Time

### 11.1. Difference from `AsyncResultSet`

With the async API, you explicitly process `AsyncResultSet.currentPage()` and call `fetchNextPage()`. With the Reactive API, the Publisher/driver fetches pages per **subscriber demand** and that version's paging rules.

Do not invent `fetchNextPage()` calls on `ReactiveRow` where no such contract exists. Sync, async, and reactive all use CQL paging underneath, yet expose **different consumption interfaces**.

### 11.2. A Page May Contain Fewer Rows Than Target

- Servers enforce internal response-size limits.
- Large rows yield fewer rows per page than the row target.
- Tombstones and the read path add work before rows fill a page.
- Subsequent pages still incur network/coordinator/replica latency.
- `LOCAL_QUORUM` and topology still govern each underlying fetch.

### 11.3. Time to First Row Differs from Total Consumption Time

~~~text
T0: subscriber subscribe()
T1: first onNext(row)
T2: last row of first page
T3: last onNext(row)
T4: onComplete()

Time to first row:   T1 - T0
Total consume time:  T4 - T0
~~~

If a 10,000-row stream has low time-to-first-row while total time drags on, you cannot claim the query served all data quickly. Measure page count, total duration, and downstream throughput together.

### 11.4. Paging Is Not a Transactional Snapshot

Between pages, concurrent inserts, deletes, TTL expirations, and repairs can alter data. A `Publisher` does not create a table-wide ACID snapshot. For exports or cutovers requiring a consistent cut, add snapshots, CDC/event logs, or reconciliation as required.

## 12. Cancellation: Stopping Consumption Does Not Undo CQL

### 12.1. When an HTTP Client Disconnects

The reactive layer can `cancel()` the subscription. Typical desirable effects:

- The subscriber stops receiving unneeded rows.
- The driver can avoid fetching subsequent pages once demand stops.
- Requests **already sent** may keep running at the coordinator/replicas.
- Applied mutations never automatically roll back.
- Events already sent downstream are not retracted.

**Never claim `cancel()` instantaneously halts all server work.** Verify actual cancellation behavior in your driver and server versions.

### 12.2. `take(n)` Does Not Replace CQL `LIMIT`

~~~java
Flux.from(session.executeReactive(statement))
    .take(20)
    .doFinally(signal -> metrics.recordTermination(signal.toString()));
~~~

`take(20)` cancels upstream after 20 rows. Still specify **`LIMIT 20`** in CQL whenever the API only needs 20 rows so the source scans less work. `metrics` here is a hypothetical app component.

### 12.3. Cancelling a Reactive Write

When an app cancels a Publisher executing an `INSERT` or `UPDATE` due to timeout:

- No automatic transaction rollback happens.
- Some replicas may have applied the write before Java saw an ACK.
- Retries must account for idempotency and operation IDs.
- Counters, LWTs, TTLs, and DELETEs each carry their own rules.

Never mark a write "definitely did not run" just because downstream cancelled.

## 13. Cold Publishers, Multiple Subscriptions, and Retries

### 13.1. One Subscribe Can Mean One CQL Execution

In many Reactive APIs, the Publisher is **cold** or triggers execution upon subscribe—verify exact behavior for your driver version. Thus:

~~~java
Flux<ReadingDto> flux = repository.find(deviceId, day, 100);

flux.subscribe(this::sendToAudit);
flux.subscribe(this::sendToHttpClient);
~~~

**Can** trigger two CQL requests and two paging sequences rather than sharing one result. If multicasting or caching is needed, design memory bounds, cancellation, retention, and privacy explicitly—never cache tenant data unboundedly.

### 13.2. `retry` and `repeat` Re-Subscribe

~~~java
// ANTI-PATTERN: retrying many times without classifying errors.
repository.find(deviceId, day, 100)
    .retry(100)
    .subscribe();
~~~

At the Reactor layer, `retry`/`repeat` **re-subscribes to the upstream Publisher**, firing a new query. If a stream emitted half its rows before failing, retrying can **re-emit already-sent rows**. That is hazardous for HTTP streaming or side-effecting sinks.

Distinguish **driver-level request retries** from **Reactor pipeline retries** and **upstream gateway/client retries**.

### 13.3. Two Subscriptions Need Not See Identical Data

Cassandra data mutates via INSERT, DELETE, TTL, consistency repairs, and replication; a cold Publisher is not an immutable snapshot backup. If point-in-time consistency is needed, build it outside `Publisher`.

## 14. Concurrency: Thousands of Small Publishers Can Still Overload the Cluster

### 14.1. Unbounded Fan-Out Anti-Pattern

~~~java
for (UUID deviceId : deviceIds) {
    repository.find(deviceId, day, 100)
        .subscribe(row -> sendRow(row));
}
~~~

Each subscription keeps its own request/page buffers. Token-aware routing helps pick coordinators when full partition keys are present, yet **does not bound total in-flight work or protect hot partitions**.

### 14.2. Bounded Fan-Out with Reactor

~~~java
import reactor.core.publisher.Flux;

int maxConcurrentPartitions = 8;

Flux<ReactiveReadingRepository.ReadingDto> rows =
    Flux.fromIterable(deviceIds)
        .flatMap(
            deviceId -> repository.find(deviceId, day, 50),
            maxConcurrentPartitions
        );
~~~

`flatMap(..., 8)` caps active inner Publishers **within this pipeline**. Across 100 concurrent HTTP requests, total inner subscriptions **can still approach 800**. Enforce admission control and rate/byte budgets **across the service/pod/cluster**, not just inside one `Flux`.

If input element order must be preserved, consider `concatMap` or an order-preserving operator while accepting the throughput trade-off.

### 14.3. System-Wide Load Limits

- Per-tenant / per-query-template rate limiters.
- Shared semaphore / in-flight budgets.
- End-to-end deadlines.
- Backpressure down to HTTP sinks and worker queues.
- Controls on row bytes, partition widths, and page sizes.
- Load shedding / circuit breakers when Cassandra overloads.
- Monitoring the worst node, not only cluster-average QPS.

**Reactive does not know how much IOPS/CPU Cassandra has left.** Many concurrent subscriptions hitting the same partition still create a hotspot on those replicas.

## 15. Never Block Callbacks or Threads While Processing Rows

### 15.1. Anti-Pattern: Calling Blocking APIs Inside `map`

~~~java
// ANTI-PATTERN: blocking I/O can stall event-loop/callback threads.
Flux.from(session.executeReactive(statement))
    .map(row -> {
        writeToSlowExternalApi(row);
        return row;
    });
~~~

If `writeToSlowExternalApi` performs synchronous HTTP/JDBC/file I/O, running it directly in the callback delays signals and causes client timeouts or starvation. **Reactive stays non-blocking only when downstream processing is also non-blocking or properly isolated.**

### 15.2. Use a Dedicated Scheduler When Blocking Is Unavoidable

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux.from(session.executeReactive(statement))
    .flatMap(
        row -> Mono.fromCallable(() -> blockingTransform(row))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

This illustrates operator usage; `blockingTransform` must be defined. `boundedElastic` caps threads and queues, yet **does not guarantee queues never grow too large**. Still bound concurrency (8 here) and monitor execution times and capacity. Prefer true non-blocking clients whenever available.

### 15.3. Calling `block()` Defeats Reactive Benefits

~~~java
// ANTI-PATTERN on a WebFlux event loop:
ReadingDto first = repository.find(deviceId, day, 100)
    .next()
    .block();
~~~

`block()` turns waiting synchronous and can stall an event loop. If a service is synchronous and does not need streaming, calling `execute()` or `executeAsync()` directly is often cleaner than "wrapping in `Flux` and calling `block()`."

Never call `Thread.sleep()` in `onNext` to throttle pace; use demand, rate limiters, or scheduler/backpressure policies instead.

## 16. Explicit Error Handling from Publishers

### 16.1. `onError` Differs from an Empty Result

A SELECT returning **0 rows** completes normally; network failures, `DriverTimeoutException`, or `AllNodesFailedException` arrive via **`onError`** (or the framework's equivalent wrapper).

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.DriverTimeoutException;

Flux<ReadingDto> observed =
    repository.find(deviceId, day, 100)
        .doOnError(error -> {
            if (error instanceof DriverTimeoutException) {
                metrics.increment("driver_timeout");
            } else if (error instanceof AllNodesFailedException) {
                metrics.increment("all_nodes_failed");
            } else {
                metrics.increment("other_failure");
            }
        });
~~~

`metrics` is a hypothetical app component. On `AllNodesFailedException`, `getAllErrors()` helps inspect **coordinator candidates** and causes, without proving every replica is down.

### 16.2. Avoid Turning Timeouts Into "No Data"

~~~java
// ANTI-PATTERN: swallowing all Cassandra errors:
repository.find(deviceId, day, 100)
    .onErrorResume(error -> Flux.empty());
~~~

If the API returns `200 OK []` when the query timed out, callers misread an outage as zero events. Separate **business-empty** from **service failures** via clear status and error contracts.

### 16.3. Selective, Bounded Reactor Retries

~~~java
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import java.time.Duration;
import reactor.util.retry.Retry;

Flux<ReadingDto> retried =
    repository.find(deviceId, day, 100)
        .retryWhen(
            Retry.backoff(1, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(500))
                .jitter(0.5)
                .filter(e -> e instanceof DriverTimeoutException)
        );
~~~

**This shows Reactor syntax only—not a blanket recommendation to retry every `DriverTimeoutException`**. Verify the SELECT is idempotent, deadline remains, the cluster isn't overloaded, and total attempts account for driver/gateway retries. If a failure happens after emitting some rows, **re-subscribing can emit duplicate rows**; in HTTP streaming, that can violate the response contract.

### 16.4. Synchronous Errors Before Subscribe

Building a `PreparedStatement`/`BoundStatement` can throw validation or codec errors before the Publisher is subscribed. `Flux.defer` defers construction until subscription time, yet **does not make invalid CQL retryable**.

Tests must cover:

- API returning `Flux.error` on invalid `limit`.
- Server/driver failures via `onError`.
- Publisher emitting 0 rows followed by `onComplete`.
- Mapper throwing when CQL column types mismatch.
- Downstream cancelling mid-stream.

## 17. Timeouts, CL, and Correctness in Reactive Queries

### 17.1. Distinguish Three Clocks

| Clock | What it bounds | Misconception to avoid |
|---|---|---|
| Driver request timeout | Driver request/operation per version contract | Not automatically the total deadline across all pages/rows |
| Reactor `timeout(Duration)` | Wait interval between signals per operator | Not necessarily total wall-clock stream duration |
| HTTP/gRPC deadline | End-to-end request budget | Does not mean the server rolled back started work |

Example:

~~~java
repository.find(deviceId, day, 100)
    .timeout(Duration.ofSeconds(5));
~~~

The `timeout` operator cancels upstream if no signal arrives within the window. Still, cancelling in Java **does not guarantee Cassandra halted the running request**.

### 17.2. `LOCAL_QUORUM` Does Not Change Because of `Flux`

With RF=3 in `dc1`, `LOCAL_QUORUM` requires a quorum of two replicas per operation rules. Switching from `executeAsync` to `executeReactive` **never alters consistency guarantees** or turns three replicas into one.

If replicas slow down during compaction/repair, reactive streams still suffer higher latency and errors. On timeouts:

- Verify driver deadlines and query shapes.
- Check RF/CL and node states.
- Inspect `tpstats`, disks, and SSTable/tombstone read paths.
- Reduce fan-out/reactive subscriptions under overload.

### 17.3. Writes and Cancellation: Outcomes May Be Uncertain

If a reactive write times out or is cancelled:

- Some replicas may have applied the mutation.
- `INSERT` with identical PK/values may be nearly idempotent, though timestamps, TTLs, and concurrent updates matter.
- Counter increments can double-count if retried.
- LWT `IF NOT EXISTS` needs operation-identity/invariant checks when the initial outcome is unknown.
- A `DELETE` with a newer timestamp can shadow valid writes issued between attempts.
- External side effects need deduplication, outboxes, or matching mechanisms.

Reactive Streams **does not provide exactly-once transactions**. Base retry decisions on business semantics, not exception classes alone.

## 18. Observing Reactive Pipelines Alongside Cassandra Resources

### 18.1. Dashboards Should Cover Three Layers

| Layer | Metrics to measure | Risks detected |
|---|---|---|
| **HTTP / Reactive** | Subscriber count, cancellations, time to first row, total duration, `onError` rate | Slow clients, disconnects, overly long streams |
| **Driver** | Request QPS, p95/p99, timeouts, retries, coordinator, pool/in-flight | Network issues, retry storms, coordinator pressure |
| **Cluster / node** | Disk free/latency, pending compactions, SSTables per read, flushes, repairs, streaming, CPU/GC | Overloaded replicas |

Also track `rows emitted` and `bytes emitted` per query template, active streams, and completed streams. Never use raw tenant/device IDs or routing keys as high-cardinality labels.

### 18.2. Diagnostic Commands in Lab or Authorized Operations

~~~bash
# Node/DC/rack status.
nodetool status

# Pending/active/dropped per thread pool.
nodetool tpstats

# Compaction backlog and progress.
nodetool compactionstats

# Streaming during bootstrap/repair/rebuild.
nodetool netstats

# Table-level latency/size/SSTables.
nodetool tablestats telemetry_lab.readings_by_device_day
~~~

`netstats` does not show regular CQL native transport traffic. Seeing nodes `UN` in `status` **does not prove** latency or queues are healthy. `nodetool` output and flags vary by release—check `help` on your running version.

### 18.3. Tracking Rate and Memory with a Hypothetical Table

| Time | Active streams | Page size | API p99 | Worst-node disk free | Preliminary conclusion |
|---|---:|---:|---:|---:|---|
| 09:00 | 20 | 100 | 90 ms | 38% | Baseline |
| 09:15 | 100 | 500 | 380 ms | 33% | Load increased |
| 09:30 | 400 | 500 | 1,200 ms | 26% | Reduce concurrency, investigate |
| 09:35 | 50 | 100 | 220 ms | 26% | After shedding load, keep watching backlog |

**Numbers are hypothetical**, not a Cassandra benchmark. Never diagnose root cause from this table alone: correlate QPS, row bytes, compaction, GC, and network at the same timestamps.

### 18.4. Measure the Right Latency Scopes

For long streams, separate:

- **Time to first row**.
- **Time to last row / `onComplete`**.
- **Pages/bytes received**.
- **Downstream wait time** and periods where upstream had `demand=0`.
- **Timeout rate** and errors, not just latency of successful requests.
- **Cancellation rate** and client disconnect causes.

Never average per-node p99s as cluster-wide p99; merge histograms/distributions properly.

## 19. Integration Testing the Reactive API

### 19.1. A Basic Test with `StepVerifier`

When your project includes Reactor Test (`reactor-test`) and a lab cluster:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(repository.find(deviceId, day, 2))
    .assertNext(row -> {
        if (row.eventTime() == null) {
            throw new AssertionError("eventTime was null");
        }
    })
    .thenCancel()
    .verify();
~~~

This test assumes at least one matching row in the lab and a Java version supporting `record` DTOs. `thenCancel` verifies the stream supports cancellation; it **does not prove the server always stops an already-sent query immediately**.

For queries over a fixed seeded row count, use `expectNextCount` and `verifyComplete` to verify the full stream, controlling dataset/CL to avoid flakiness.

### 19.2. Testing Demand with a Custom Subscriber

A Publisher can be verified with a controlled Subscriber:

1. Subscribe without requesting any items yet.
2. Call `request(1)` and verify no more than demanded items arrive.
3. After processing the first row, request a small batch.
4. Call `cancel()` and verify no unwanted downstream side effects occur.
5. Inject input/timeout errors and verify `onError` classification.
6. Verify `onComplete` is never emitted on a failed stream.

Test races/concurrency with virtual time or proper synchronization primitives rather than `Thread.sleep` guesses.

### 19.3. Mandatory Correctness Tests

| Test case | What is verified |
|---|---|
| Query returning 0 rows | `onComplete` with zero items, not `onError` |
| Valid / invalid limits | Server-side `LIMIT` and Java validation |
| Rows with nullable fields | DTO preserves `null` rather than converting to 0 |
| Large partition | Page size, heap, total consume time, cancellation |
| Client cancels after 5 rows | Zero additional downstream side effects |
| Second subscriber | Does not assume one CQL execution is shared |
| Retry after 2 rows then error | No duplicate side effects or row IDs |
| Network / driver timeout | `onError`, never converted into an empty result |
| 100 concurrent subscriptions | In-flight/concurrency/admission caps hold |
| Schema / driver upgrade | Method/type signatures and codecs remain compatible |
| CL / local DC | Results/timeouts match RF and replica availability |
| Slow downstream | Queues/heap do not grow unboundedly |

**Never inject faults directly in production.** Use an isolated test cluster and synthetic data with low rate limits so tests do not turn into unplanned stress tests.

## 20. Architectural Choice: Reactive API or Async Paging?

Choose based on concrete requirements:

| Need | Usually appropriate choice | Control point |
|---|---|---|
| Return up to 10 rows for a sync API | `execute` or `executeAsync` | CQL `LIMIT`, timeout |
| Async workflow with explicit per-page steps | `executeAsync` / `fetchNextPage()` | Explicit fetch, app backpressure |
| Reactive HTTP streaming of rows | `executeReactive` + Reactor/WebFlux if compatible | Demand, cancellation, full pipeline |
| Large token-range backfills | Throttled async/reactive or dedicated import tool | Bytes/s, partition routing, checkpoints |
| One-off state synchronization | Prepared sync/async or reactive per stack | Idempotency/CL; reactive not mandatory |
| Continuous DB changes | Purpose-built CDC / event broker | `executeReactive(SELECT)` is not a change feed |
| Legacy driver without Reactive API | Controlled async or planned driver upgrade | Driver/JDK/server compatibility |

**Never build a `Flux.create(sink -> session.execute(...))` wrapper around blocking JDBC-style calls and call it reactive Cassandra.** Bridges may serve temporary migrations, but require meticulous management of schedulers, demand, cancellation, and blocking threads.

### 20.1. If Your Current Driver Lacks `executeReactive`

Viable options:

- Use `executeAsync` with a **bounded-demand** paging loop you implement and test.
- Upgrade the driver under a plan with a compatibility matrix, regression tests, and rollback.
- Use a reactive abstraction/framework officially supported by your stack.
- Stick to simple sync code for small workloads instead of building fragile bridges.

Never try to call `executeReactive` on 3.x merely because you saw it in Driver 4.x documentation.

### 20.2. If Already Using Spring Data Cassandra Reactive

Audit the stack:

- Does your Spring Data Cassandra version support your exact driver and server versions?
- Which driver/API does the reactive repository actually call underneath?
- Which layer configures consistency levels, paging, tracing, retries, and timeouts?
- Do `UDT/collection` codecs and mappings differ from the native driver?
- Does HTTP response backpressure propagate cleanly down to the repository?

Spring abstractions can help, yet **never replace understanding the Publisher contract** or Cassandra data modeling.

## 21. Runbook A — Code Cannot Find `executeReactive`

**Scenario:** A Java module is upgraded from Driver 3.x to 4.x; reactive examples fail to compile, or runtime throws `NoSuchMethodError` / `ClassNotFoundException`.

### Step 1 — Identify Exact Artifact and Package

Record driver major/minor/patch, vendor, dependency coordinates, JDK, and declared reactive libraries. Never conclude "Cassandra doesn't support reactive" simply because a method is missing from **one specific driver classpath**.

### Step 2 — Inspect Actual Runtime Classpath

Check whether transitive dependencies pull multiple driver versions; watch for `NoSuchMethodError` when compilation succeeds against a newer JAR while runtime loads an older JAR. Fix dependency graphs in build/CI, **never by patching JARs ad hoc in production**.

### Step 3 — Verify Against Exact Artifact API

Use your IDE/Javadoc for the exact artifact to check:

- Does `CqlSession` expose `executeReactive`?
- Does its return type implement `org.reactivestreams.Publisher`?
- What are the row type and getters?
- Which transitive dependencies does the driver require?
- Which Java/JDK, CQL protocol, and Cassandra server versions are supported?

Never force-cast between `java.util.concurrent.Flow.Publisher` and `org.reactivestreams.Publisher` without an adapter.

### Step 4 — Verify Reactor Integration

If the driver exposes `Publisher` while code cannot find `Flux` or `StepVerifier`, verify `reactor-core` / `reactor-test` are declared in the right module with compatible versions and zero classpath conflicts. **Reactor is not the driver itself**; a Reactor import error does not prove the native Reactive API is missing.

### Step 5 — Decide the Path Forward

- If your current version supports it: fix imports/dependencies and run compile/integration tests.
- If unsupported: stay on `executeAsync` with explicit paging and backpressure, or schedule a compatibility-verified upgrade.
- On runtime binary mismatches: fix dependency resolution/build artifacts rather than bypassing tests.
- Document verified version pairs and decisions to prevent regressions.

### Step 6 — Smoke Test Before Rollout

Run a partition-key SELECT in the lab, subscribe once, and test 0/1/n rows, errors, and cancellation. Measure QPS, p99, and heap under moderate load. Never ship to production just because an example compiled.

## 22. Runbook B — Reactive Service Heap and Latency Climb

**Scenario:** After migrating to Reactor, app heap/GC climbs, ~500 streams are active, Cassandra `ReadStage Pending` and p99 rise, and the code uses `collectList()` and unbounded `flatMap`.

### Step 1 — Scope the Incident

Record query templates, active subscription counts, HTTP concurrency, page size, `LIMIT`, row/response bytes, timeouts, and deployment timing. Never log raw tenant/partition IDs.

### Step 2 — Locate Buffers

Search for:

~~~text
collectList()
onBackpressureBuffer() (unbounded)
flatMap(...) (unbounded concurrency)
request(Long.MAX_VALUE) into a slow consumer
block() / Thread.sleep() / synchronous I/O in callbacks
accidental double subscribe() on the same Publisher
~~~

Not every call to these APIs is a bug, yet each must be audited against real workload and memory budgets.

### Step 3 — Measure Cassandra

- `nodetool tpstats`: are Active/Pending/Dropped rising?
- `nodetool compactionstats`: is compaction backlog competing for disk?
- Disk free, read latency, GC, network, and row sizes.
- Do queries bind full partition keys; are tombstones/SSTables excessive?
- `nodetool netstats`: is bootstrap/repair streaming competing for I/O?

### Step 4 — Throttle Load

Lower active subscriptions, `flatMap` concurrency, and page sizes to fit workload; remove unbounded buffers; add shared rate limiters/admission controls. If overloaded, pause non-essential bulk scans/backfills per runbook.

### Step 5 — Fix Semantics

Do not just swap `collectList()` for another operator that still buffers all DTOs downstream. Stream to sinks with quotas, proper cancellation, and memory limits at every layer.

### Step 6 — Verify

Monitor heap/GC, active streams, API first/total latency, timeouts, compaction, worst node, and error budgets; raise concurrency only incrementally after stability returns.

## 23. Runbook C — Duplicates After Retries or Client Disconnects

**Scenario:** A streaming API returns 30 rows, hits a network timeout, and `retryWhen` re-subscribes. The client receives the first 15 rows twice, or a side-effecting sink writes duplicates.

### Step 1 — Locate the Failure Point

Which rows had the Publisher emitted before `onError`? Did the driver retry, or Reactor? Is an API gateway also retrying the HTTP call? Logs must include **logical request IDs** while excluding sensitive data.

### Step 2 — Check the Output Contract

If HTTP streaming already flushed part of the body, the service cannot alter the status code or "retract sent rows." Clarify **whether duplicate emissions are permitted** and how clients resume.

### Step 3 — Disable Unsafe Full-Stream Retries

For user-facing streaming responses, it is usually safer to terminate with a clear error or use a contracted cursor/paging token rather than silently replaying from the beginning.

### Step 4 — Design Data Identity

Use primary/clustering keys for deduplication or consumer-side checkpoints where business rules allow. Tokens are not time cursors, and paging state never guarantees a snapshot across separate subscriptions.

### Step 5 — For Write Pipelines

Verify operation IDs, idempotency, TTL/timestamps, counters/LWTs, and side effects. Cancellation/timeouts never prove a mutation did not occur.

### Step 6 — Retest

Simulate failures mid-stream in the lab; verify actual query execution counts, downstream row counts, absence of duplicates, and that rates/heap stay within bounds.

## 24. Common Misconceptions

| Misconception | Reality |
|---|---|
| "Async and reactive are the same." | `CompletionStage` differs from `Publisher` and demand-based protocols |
| "Every Cassandra Java Driver has `executeReactive`." | Must verify exact driver/version/artifact/API |
| "Reactor is built into the Cassandra server." | Reactor is an optional JVM application library |
| "A Publisher is a pre-loaded List." | It is a subscription- and demand-driven stream |
| "`request(1)` means the server reads one row." | Server/driver use page buffers and scan tombstones/SSTables |
| "Page size 100 caps the whole query at 100 rows." | Requires CQL `LIMIT` or explicit stopping logic |
| "`limitRate(32)` equals CQL `LIMIT 32`." | `limitRate` paces Reactor demand |
| "`Flux` prevents all `OutOfMemoryError`s." | Buffers, `collectList`, wide rows, and fan-out still cause OOM |
| "`onBackpressureBuffer` always saves RAM." | Unbounded buffers grow the heap |
| "`cancel()` immediately halts the coordinator." | In-flight CQL may keep running |
| "Cancelling a reactive write = rollback." | Replicas may already have applied the mutation |
| "Subscribing twice shares one SELECT." | Typically executes the query twice |
| "`retry()` replays only the failed row." | Re-subscribes the entire Publisher, duplicating prior rows |
| "A `Flux` provides exactly-once by default." | No; idempotency and reconciliation must be designed |
| "`flatMap(...,8)` caps the whole service at 8 requests." | Caps only that single pipeline |
| "`block()` in WebFlux is still non-blocking." | `block()` can stall event loops |
| "`onErrorResume(Flux.empty())` is harmless." | Masks outages as empty data, breaking business logic |
| "Token-aware routing cures hot partitions." | The same replica set still absorbs concentrated load |
| "`LOCAL_QUORUM` doesn't matter with `Flux`." | CL still governs replica acknowledgment requirements |
| "Reactive `SELECT` streams newly inserted rows." | It is not CDC or a change feed |
| "A Publisher snapshots the entire table." | Pages can observe mutating data |
| "Nothing in `netstats` means zero CQL load." | `netstats` mainly tracks SSTable streaming |
| "Lowering `DriverTimeout` suffices when p99 rises." | Must check SLOs, API latency, and overall system load |

## 25. Exercises and Answers

### Question 1 — Core Distinction

Is `CompletionStage<AsyncResultSet>` equivalent to a `Publisher`?

**Answer:** No. `CompletionStage` represents async completion of a single computation/page; `Publisher` represents a stream of items governed by subscriptions, demand, and lifecycle signals.

### Question 2 — Driver 3.x

An app uses `com.datastax.driver.core.*` and lacks `executeReactive`. Should you add `reactor-core` and call the 4.x method directly?

**Answer:** No. Reactor does not add native methods to Driver 3.x. Use existing APIs or plan a driver upgrade against the compatibility matrix.

### Question 3 — Reactive Streams vs. Java Flow

Can you cast `org.reactivestreams.Publisher` directly to `java.util.concurrent.Flow.Publisher`?

**Answer:** Not directly. They are separate interfaces; use an adapter when bridging between them.

### Question 4 — Demand

A Subscriber calls `request(5)`. Does Cassandra read strictly five SSTable entries?

**Answer:** No. Demand controls only items emitted to the subscriber; the server/driver may read/buffer a page or scan many tombstones before returning rows.

### Question 5 — LIMIT

CQL specifies `LIMIT 500` with page size 50. Does `request(10)` change `LIMIT` to 10?

**Answer:** No. CQL can still return up to 500 rows; demand only paces items delivered to the current subscription.

### Question 6 — `request(0)`

To pause a stream, should you call `request(0)`?

**Answer:** No. Reactive Streams requires `n > 0`; to pause, stop requesting more items, and to stop permanently, call `cancel()`.

### Question 7 — Cancellation

A client cancels after 20 rows. Is the server guaranteed to have halted all CQL work?

**Answer:** No. Already-sent requests/pages may finish executing; cancellation never rolls back.

### Question 8 — Two Subscribers

A cold Publisher receives two subscriptions. Can you assume only one CQL query executes?

**Answer:** No. Each subscription can execute a fresh query; verify the contract and add intentional sharing/caching only if appropriate.

### Question 9 — Fan-Out

100 concurrent HTTP requests each run `flatMap` with concurrency=8. How high can total inner subscriptions climb?

**Answer:** Nearly 800 in the idealized case. Add a shared limiter rather than relying solely on per-request concurrency.

### Question 10 — Buffering

A pipeline uses unbounded `onBackpressureBuffer()` ahead of a slow consumer. What is the risk?

**Answer:** Heap/GC spikes and OOM even though upstream is a Publisher. Use bounded buffers with overflow policies and rate/concurrency limits.

### Question 11 — Reactive in WebFlux

A controller calls `repository.find(...).block()` on the event loop. Is it still non-blocking end-to-end?

**Answer:** No. `block()` stalls event-loop threads; return `Flux/Mono` directly or use sync APIs in a synchronous architecture.

### Question 12 — Retrying After Partial Emissions

A stream emits 10 rows then errors, and `retryWhen` re-subscribes from the start. What can go wrong?

**Answer:** The first 10 rows can be re-emitted/duplicated, especially with side-effecting sinks or HTTP streaming; use checkpoints/dedup or avoid full-stream retries.

### Question 13 — Empty Results and `onComplete`

A query succeeds with zero rows; the Publisher calls `onComplete` without `onNext`. Is this a timeout error?

**Answer:** No. That is a valid empty result; timeouts/errors arrive via `onError`.

### Question 14 — Reactive Writes

A counter mutation times out and the Publisher automatically retries. Is this safe?

**Answer:** Not by default. The first attempt may have incremented; the retry increments again. Use operation identity/deduplication or a different data model.

### Question 15 — Consistency

Switching `executeAsync` to `executeReactive` while keeping `LOCAL_QUORUM`—does that reduce RF=3 quorum to one replica?

**Answer:** No. Cassandra's CL and RF never change because of the Java API style.

### Question 16 — Slow System

Page size=500, active streams=400, p99 rises, and compaction backlog is huge. Should you just raise timeouts?

**Answer:** No. Lower concurrency/page size as needed, inspect disk, SSTables/tombstones, backpressure, and SLOs. Raising timeouts often just keeps requests alive longer.

### Question 17 — Is Reactive SELECT CDC?

Does an `executeReactive(SELECT ...)` subscription automatically emit new rows inserted later?

**Answer:** No. It consumes a finite query result; change feeds require dedicated CDC or event streams.

### Question 18 — Support Boundaries

A specific Driver 4.x release lacks a reactive type/method shown in docs you are reading. What is the right response?

**Answer:** Verify the release Javadoc, Maven coordinates, dependency conflicts, JDK, and server/driver compatibility. If unsupported, use `executeAsync` or plan a proper upgrade; never force-cast.

## 26. Implementation and Audit Checklist

### 26.1. Driver and Libraries

~~~text
[ ] Exact Java Driver version, artifact coordinates, and JDK verified.
[ ] executeReactive and Publisher types confirmed in the target API version.
[ ] org.reactivestreams / Reactor / RxJava adapters compatible.
[ ] Java Flow.Publisher not confused with Reactive Streams Publisher.
[ ] Driver ↔ Cassandra server/protocol compatibility matrix checked.
[ ] CqlSession reused; auth, TLS, and local DC properly configured.
[ ] Spring Data / WebFlux versions verified if used.
~~~

### 26.2. CQL, Backpressure, and Correctness

~~~text
[ ] Queries specify full partition keys or approved access patterns.
[ ] Prepared/bound parameters used; never concatenate raw user input into CQL.
[ ] LIMIT and page size fit row sizes and workload.
[ ] Subscriber demand handled cleanly; never request(0) or negative values.
[ ] No unbounded buffers/lists or collectList on large datasets.
[ ] Max active subscriptions, in-flight requests, rates, and bytes share a budget.
[ ] Zero blocking inside driver callbacks or WebFlux event loops.
[ ] Cancellation and timeouts never treated as rollbacks.
[ ] Retries/resubscribes enforce idempotency, deadlines, and dedup as needed.
[ ] Never silently convert onError into empty results.
[ ] Never assume paging is a snapshot or SELECT is a change stream.
[ ] RF, CL, DC, token-aware routing, and replica load properly accounted for.
~~~

### 26.3. Testing and Operations

~~~text
[ ] Unit tests verify demand, onError, onComplete, and cancel.
[ ] Integration tests seed rows and verify 0/1/n records and nullable fields.
[ ] Tested two subscriptions to verify whether queries repeat.
[ ] Tested retries after partial output and duplicate handling.
[ ] Tested slow downstream and high concurrency safely in a lab.
[ ] Metrics track active streams, first-row/total latency, rows, and bytes.
[ ] Track driver QPS/timeouts/retries alongside backend compaction/GC/disk.
[ ] Never log raw routing keys, tenant IDs, credentials, or full rows.
[ ] Runbooks exist for backpressure, dependency mismatches, and retry duplicates.
[ ] Pause / load-shed triggers defined when the worst node approaches SLO limits.
~~~

## 27. Summary

The Reactive API in the Cassandra Java Driver must be understood across **two distinct yet connected layers**:

1. **Driver/support layer:** use `executeReactive` only when your exact Java Driver version/artifact provides the method and Publisher types; verify JDK, server/protocol, and optional frameworks like Reactor or Spring.
2. **Reactive Streams layer:** `Publisher` emits signals through `Subscription`; `Subscriber` calls `request(n)` and `cancel()` to govern demand and lifecycle.
3. **Backpressure does not replace CQL `LIMIT` or page size:** row demand differs from bytes read, server paging, tombstone/SSTable scans, and resource quotas.
4. **Reactive does not guarantee bounded memory:** concurrent subscriptions, `collectList`, `onBackpressureBuffer`, and blocking callbacks can still spike heap, p99, and replica load.
5. **Each subscription or retry can re-execute CQL:** never assume results are cached, deduplicated, or snapshotted across reads.
6. **Cancellation does not roll back:** already-sent requests may continue; handle mutation timeouts/cancellations via idempotency and consistency semantics.
7. **Keep the path truly non-blocking:** never `block()` on event loops, never do blocking I/O in `onNext`, and bound fan-out with shared quotas.
8. **CQL and cluster topology still dominate cost:** partition keys, token routing, RF/CL, compaction, repair, tombstones, and network behavior do not change just because Java returns a `Flux`.
9. **Measure and test end-to-end:** time to first row, total consume time, active streams, p99, errors, retries, cancellations, disk/GC, and data correctness.

The question for designing a reactive query flow is not merely **"did we return a `Flux`?"**, but **"Does our driver version genuinely support this Publisher, can subscribers process within demand, are total subscriptions and bytes bounded system-wide, and do cancellations/retries preserve data under CL and business rules?"** Only when code, tests, and metrics answer all of those does the Reactive API make Java–Cassandra systems more resilient.
