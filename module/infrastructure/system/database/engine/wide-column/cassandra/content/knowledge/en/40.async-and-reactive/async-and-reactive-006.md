# Bounding Concurrent Requests Instead of Uncontrolled Dispatch

> **Chapter:** Async and Reactive  
> **Scope:** Apache Cassandra with Java Driver 4.x, `CompletionStage`, `AsyncResultSet`, and Reactor integration examples. Focuses on **bounding active in-flight requests**, *backpressure*, queue control, replica load, and protecting services during traffic spikes.
>
> **Learning objectives:** Understand why `executeAsync()` does not automatically mean the system tolerates infinite requests; distinguish QPS, *in-flight concurrency*, connection pools, and queues; estimate an initial budget via Little's Law; implement **non-blocking admission control without blocking the event loop**; integrate Java Driver and Reactor; measure replica impact, coordinate retries/speculation, and implement graceful overload handling.

## 1. The Problem: "Asynchronous" Does Not Mean "Unbounded"

A Java API receives a list of one million keys to read. The code below looks appealing because it never loops waiting on each result:

```java
List<CompletionStage<AsyncResultSet>> requests = new ArrayList<>();

for (UUID orderId : orderIds) {
    requests.add(
        session.executeAsync(
            prepared.bind(tenantId, orderId)
        )
    );
}
```

**The problem:** the loop can fire hundreds of thousands of requests almost instantaneously. Calling `executeAsync` does not block like synchronous CQL, yet every call still carries cost:

- Allocates objects for statements, futures, callbacks, tracing/metrics, and timeouts.
- Enters driver queues and processing threads.
- Consumes connection pools and per-connection concurrent request limits.
- Creates coordinator work, internode messages, and SSTable/memtable reads on replicas.
- Retains buffers/heap on both the application and server.
- Raises the odds of timeouts, retries, speculative executions, and resource exhaustion.

When Cassandra slows down, incomplete requests pile up even faster. If the application keeps pumping more in, **work accumulates**, driving p99 up and eventually causing out-of-memory crashes or outages.

**Core principle of this lesson:** decide **when a request is allowed to start**, rather than only deciding "how to send it asynchronously."

## 2. Two Systems Serving One Operation

A partition-key read traverses multiple layers:

```text
HTTP / Kafka / Scheduled job
             |
             v
     Service application
             |
       Admission control
             |
     Java Driver 4.x
             |
         Coordinator
             |
       Replicas R1/R2/R3
             |
     Memtable / SSTable
             |
          Response
```

There are at least **two independent budgets**:

1. **Application budget:** heap, CPU, request threads/event loops, pending futures, and API response deadlines.
2. **Cassandra budget:** coordinator queues, CPU, GC, disk I/O, network, replica responses per consistency level, and background work like compaction/repair.

An application limit must account for **both sides**. If 20 service instances each allow 500 concurrent requests, the fleet can send **10,000 logical in-flight requests** even though each instance thinks it is "bounded."

And that counts only logical requests: retries, speculative executions, or page fetches generate even more driver/server work.

## 3. Five Numbers Never to Conflate

| Concept | Definition | Unit | Often confused with |
| --- | --- | --- | --- |
| **Arrival rate / QPS** | Logical requests arriving per second | requests/s | Concurrent requests |
| **In-flight concurrency** | Requests admitted for processing that have not completed | requests | QPS or thread count |
| **Queue depth** | Requests waiting **not yet admitted** for execution | requests | In-flight requests |
| **Service time** | Time a request spends inside the measured system | ms | Queue wait time |
| **Connection pool capacity** | Driver connection and per-host request multiplexing capacity | connections/requests | Cassandra's safe concurrency level |

Add one more layer: **resource cost per request**. Two CQL `SELECT`s both count as "one request," yet reading a tiny partition key is vastly different from scanning a giant partition full of tombstones.

Hence `maxInFlight = 100` is purely a **count** limit; it does not by itself guarantee CPU, disk, or network stays within budget.

### Thread Count Does Not Equal Request Count

In blocking apps, 100 threads can wait on 100 requests. In async apps, **a handful of event-loop threads** can juggle thousands of outstanding requests.

Switching to async **reduces thread-per-request overhead**, but does not make external requests disappear. Precisely because a single thread can launch huge numbers of requests, **admission control** becomes even more critical.

## 4. Little's Law: Relating Throughput, Latency, and Concurrency

A useful approximation when a system is relatively steady:

\[
L = \lambda \times W
\]

Where:

- \(L\): average amount of work inside the measured system.
- \(\lambda\): average completion or arrival rate of requests in steady state.
- \(W\): average time a request spends inside that system.

Hypothetical example:

```text
Steady throughput: 800 logical reads/s
Mean service time: 60 ms = 0.060 s

L = 800 x 0.060 = 48 average in-flight reads
```

**48 is not an automatically optimal limit.** It estimates average steady-state in-flight concurrency, excluding bursts, p99 tails, uneven request costs, or background work.

If mean latency triples while the arrival rate stays unchanged:

```text
800 reads/s x 0.180 s = 144 average in-flight reads
```

That explains why systems spiral: **latency rises → in-flight climbs → more pressure → latency climbs further**.

### When Is Little's Law Insufficient?

- Measurement windows are too short and the system is not in steady state.
- Multiple query types have wildly different costs.
- Requests queue or reject before dispatch.
- Workloads have heavy bursts and fan-out.
- Driver retries/speculation turn one logical request into multiple coordinator attempts.
- Hot partitions/tombstones push tail latency far above the mean.

Use the formula to form an **initial hypothesis**, then validate with benchmarks and metrics.

## 5. What Does a Properly Placed Limit Look Like?

Keep the boundary clear:

```text
            INCOMING REQUEST
                   |
                   v
         In-flight slot available?
             /           \
           Yes            No
           |               |
           v               v
    Run Cassandra    Reject / Bounded queue
           |               |
           v               v
    CompletionStage  429/503 or wait
      completes      with deadline
           |
           v
      Release slot
```

**Acquire the slot before calling `session.executeAsync`.**

If the app calls `executeAsync` first and acquires a slot afterward, the request has already entered the driver pool/queue. You only cap callback processing, **failing to stop load from hitting Cassandra**.

### Defining Slot Scope

In this lesson, one slot represents **one logical operation** from admission at the repository layer until the guarded stage completes.

This is **not** a cap on total physical RPCs:

- The driver may retry after an error.
- The driver may issue a speculative attempt on an idempotent `SELECT`.
- Subsequent page fetches create separate logical requests.
- The coordinator may contact multiple replicas.

For tighter physical bounds, combine driver metrics, retry/speculation policies, and server capacity budgets.

## 6. Three Overload Strategies

| Approach | When slots are full | Pros | Risks / costs |
| --- | --- | --- | --- |
| **Fail fast / shed load** | Return controlled error immediately | No large queues; protects Cassandra well | Clients need proper retry/backoff |
| **Bounded queue** | Wait in a small queue with a deadline | Absorbs short bursts | Adds queue latency; needs expiry and fairness |
| **Async wait-for-permit** | Return future waiting for a slot without blocking threads | Doesn't block event loop | Without a waiter cap, it is still an **unbounded queue** |

The most dangerous setup is usually:

```text
"Wait if no slot is free"
+
unbounded number of waiters
+
no deadline
+
upstream keeps sending steadily
```

That merely trades an **unbounded driver queue** for an **unbounded application queue**.

For interactive APIs, starting with **fail fast** is often easiest to operate. For batch processing, a **bounded queue or source-side demand mechanism** is usually better. No single policy fits every workload.

## 7. Never Call `Semaphore.acquire()` on an Event Loop

Java provides `Semaphore` to manage permits. Watch the critical difference:

```java
// NEVER do this on a Netty/Reactor event-loop thread.
semaphore.acquire();
return session.executeAsync(statement);
```

`acquire()` can **block the thread** until a permit frees up. If that thread is an event loop driving callbacks, networking, or request handling, you risk:

- Stalling the event loop.
- Spiking response times for unrelated requests.
- Deadlock/starvation when callbacks need the blocked thread.
- Thread pool exhaustion under load.

Async paths should use non-blocking **`tryAcquire()`** or an **async semaphore with bounded waiters**.

```java
if (!semaphore.tryAcquire()) {
    // Reject early without blocking the event loop.
}
```

To absorb bursts, do not "fix" it by dumping every request onto an unbounded thread pool. Bound **both active requests and waiting requests**.

## 8. Java 17: A Reusable Asynchronous Limiter

The example below is a **non-blocking admission gate**. It uses `Semaphore.tryAcquire()` to reserve a slot **before** creating a Cassandra request and returns a failed `CompletionStage` when overloaded.

```java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

public final class AsyncInFlightLimiter {

    public static final class BusyException extends RuntimeException {
        public BusyException(String message) {
            super(message);
        }
    }

    private final Semaphore permits;
    private final int maxInFlight;

    public AsyncInFlightLimiter(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException(
                "maxInFlight must be positive");
        }
        this.maxInFlight = maxInFlight;
        this.permits = new Semaphore(maxInFlight);
    }

    public <T> CompletionStage<T> submit(
            Supplier<? extends CompletionStage<T>> operation) {

        // Admission happens BEFORE operation creates a request.
        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new BusyException("Cassandra capacity is busy"));
        }

        final CompletionStage<T> stage;

        try {
            stage = Objects.requireNonNull(
                operation.get(), "operation must return a stage"
            );
        } catch (RuntimeException ex) {
            permits.release();
            return CompletableFuture.failedFuture(ex);
        } catch (Error fatal) {
            permits.release();
            throw fatal;
        }

        // Release on both success and failure; NEVER
        // release right after calling executeAsync.
        return stage.whenComplete(
            (value, failure) -> permits.release()
        );
    }

    public int getInFlight() {
        return maxInFlight - permits.availablePermits();
    }

    public int getAvailable() {
        return permits.availablePermits();
    }

    public int getMaxInFlight() {
        return maxInFlight;
    }
}
```

### Invariants of This Code

1. **Never exceeds `maxInFlight`** admitted slots on a limiter instance.
2. Zero blocking waits on event loops.
3. If `operation.get()` throws synchronously, the permit is returned.
4. When the async stage completes normally or exceptionally, the permit is returned.
5. When out of permits, the request is **not created**, and the backend can return a controlled overload error.
6. The code does not maintain an unbounded internal queue.

**Crucial:** `whenComplete` must attach to **the stage covering the entire guarded work**. If the returned stage only represents driver response metadata while the app goes on to read more pages or call downstream services, the permit may release too early.

### Limitations of This Example

- This `Semaphore` protects **one limiter instance in one JVM**, not the entire Cassandra cluster.
- It provides no per-tenant fairness, priorities, or weighted cost.
- It **does not cancel** an in-flight request when an HTTP caller disconnects.
- It does not prevent the driver from retrying/speculating inside one logical request.
- When releasing permits on completion, avoid heavy callbacks directly on I/O threads.
- If developers omit downstream work from the stage or lack timeouts, permits can be held too long.

This is a **verifiable baseline** for explaining admission control, not a full-featured dispatcher for every traffic class.

## 9. Never Release the Permit Right After `executeAsync`

Wrong example:

```java
semaphore.acquire();
try {
    return session.executeAsync(statement);
} finally {
    semaphore.release();
}
```

`executeAsync` returns a future almost immediately, which **does not mean the query finished**. `finally` runs right after dispatching the request, releasing the slot long before Cassandra finishes.

Right principle:

```java
if (!semaphore.tryAcquire()) {
    return CompletableFuture.failedFuture(
        new IllegalStateException("busy")
    );
}

try {
    return session.executeAsync(statement)
        .whenComplete((result, error) -> semaphore.release());
} catch (RuntimeException ex) {
    semaphore.release();
    throw ex;
}
```

This snippet illustrates permit lifetime. If you return the result for another layer to fetch more pages, **decide explicitly** whether the slot covers all page fetches or each page fetch acquires its own slot. Never confuse an `AsyncResultSet` holding **the current page** with an entire multi-page cursor.

## 10. Sample Cassandra Table: Query-First to Bound Cost

Suppose the app reads an order by tenant and order ID. Design the table for that exact query:

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    status text,
    total decimal,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

Assume keyspace `lab` already exists with replication strategy, RF/DC, and security matching your lab cluster.

Insert data (using an authorized role):

```cql
INSERT INTO lab.orders_by_id (
    tenant_id, order_id, customer_id, status, total, updated_at
) VALUES (
    'tenant-a',
    11111111-1111-4111-8111-111111111111,
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    'PAID',
    250.00,
    '2026-11-21T10:00:00Z'
);
```

Query by **full partition key**:

```cql
SELECT order_id, status, total
FROM lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-4111-8111-111111111111;
```

If a query omits `tenant_id` or filters `status='PAID'` without a partition key, tuning or bounding in-flight limits **cannot replace query-driven table design**. Even a few heavy requests on giant partitions can exhaust resources.

## 11. Integrating the Limiter into Java Driver 4.x

The repository below holds the slot until **one row** is received and mapped from `AsyncResultSet`.

```java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class AsyncOrdersRepository {

    public record OrderView(
        UUID orderId, String status, BigDecimal total) {}

    private final CqlSession session;
    private final AsyncInFlightLimiter limiter;
    private final PreparedStatement byId;

    public AsyncOrdersRepository(
            CqlSession session,
            AsyncInFlightLimiter limiter) {
        this.session = Objects.requireNonNull(session);
        this.limiter = Objects.requireNonNull(limiter);
        this.byId = session.prepare(
            "SELECT order_id, status, total " +
            "FROM lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public CompletionStage<Optional<OrderView>> find(
            String tenantId, UUID orderId) {

        if (tenantId == null || tenantId.isBlank() ||
            orderId == null) {
            throw new IllegalArgumentException(
                "tenantId and orderId are required");
        }

        // Validation and authorization occur before admission.
        // The API layer must verify tenantId from the authenticated principal.
        BoundStatement statement = byId
            .bind(tenantId, orderId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        return limiter.submit(() ->
            session.executeAsync(statement)
                .thenApply(result -> {
                    Row row = result.one();

                    if (row == null) {
                        return Optional.<OrderView>empty();
                    }

                    return Optional.of(new OrderView(
                        row.getUuid("order_id"),
                        row.getString("status"),
                        row.getBigDecimal("total")
                    ));
                })
        );
    }
}
```

### Actual Execution Flow

```text
HTTP request
    |
    +--> auth/tenant/resource check
    +--> prepare / bind statement
    |
    +--> limiter.tryAcquire()
            |
            +--> No slot -> failed stage -> 429/503
            |
            +--> Slot acquired
                   |
                   +--> session.executeAsync()
                   +--> map AsyncResultSet -> OrderView
                   +--> completion success/error
                   +--> release permit
```

**Core point:** `session.executeAsync` is called **only inside the supplier** permitted by the limiter. Calling it before `submit` already dispatches the load and renders the gate useless.

### Code Assumptions

- Java 17 for `record`; Java Driver 4.x providing `CqlSession` and `AsyncResultSet`.
- `LOCAL_QUORUM` fits only when local DC RF and available replicas suffice; single-node labs must pick an appropriate CL.
- `find` reads one partition and at most one row by primary key, so no `fetchNextPage` is needed.
- `setIdempotent(true)` fits this pure SELECT, **not as a blind default for every mutation**.
- The HTTP layer enforces user/tenant authorization rather than relying solely on the Cassandra service-account role.
- `CqlSession` and `PreparedStatement` are reused, never re-created per request.
- If mapping becomes CPU-heavy, use a dedicated executor/bulkhead and extend measurement scope to avoid blocking driver I/O threads.

## 12. Mapping Busy Rejections to Meaningful HTTP Responses

When the gate rejects a request, it is a **capacity-protection decision**, not an exception returned by Cassandra.

Conceptual mapping:

| Scenario | Possible HTTP response | Notes |
| --- | --- | --- |
| Caller exceeds tenant quota | `429 Too Many Requests` | May include a reasoned `Retry-After` |
| Service temporarily out of DB capacity | `503 Service Unavailable` | Ensure gateways don't blindly retry in lockstep |
| Unauthenticated caller | `401 Unauthorized` | Handle before DB admission |
| Caller lacks tenant access | `403 Forbidden` | Never consume a DB slot |
| Invalid input | `400 Bad Request` | Validate before admission |
| Driver timeout / replica unavailable | `503` or `504` per contract | Classify separately from admission overload |

`429`/`503` are API contract choices, not a single mandatory rule. What matters is that **clients recognize controlled overload signaling** and do not retry immediately without limits.

### Retry Signals Can Trigger a "Thundering Herd"

If 100,000 clients receive `503` and all retry after exactly 1 second, the cluster takes another spike right at that instant.

You need:

- Exponential backoff + **jitter**.
- Retry limits and **end-to-end deadlines**.
- Rate limiting at gateways/consumers.
- Never blindly retrying non-idempotent writes.
- No retries once a request's business deadline has expired.

**Admission control only works if upstream respects backpressure signals or can be rejected.**

## 13. Why `CompletableFuture.allOf` Does Not Limit Concurrency

Common mistake:

```java
List<CompletableFuture<?>> pending = new ArrayList<>();

for (UUID id : ids) {
    pending.add(
        session.executeAsync(prepared.bind(tenant, id))
            .toCompletableFuture()
    );
}

return CompletableFuture.allOf(
    pending.toArray(new CompletableFuture<?>[0])
);
```

`allOf` is a tool to **await multiple futures**. It **does not cap how many futures are created**, never pauses the launch loop, and does not hold back requests to Cassandra.

With one million items, it also allocates a huge future list on the heap.

### Two Alternatives

**Option A — Fixed batches/windows:** take at most K keys, fire at most K requests, wait for the batch to finish, then start the next batch. Simple, though utilization can dip while a slow tail request stalls the whole batch.

**Option B — Sliding window / concurrency-limited stream:** as each request finishes, admit one new item from the source. Keeps up to K items active without waiting for the slowest item in a fixed batch.

In Reactor or Reactive Streams, Option B is cleanly expressed via **`flatMap(..., concurrency)`** when the source supports real backpressure. Pair it with a **global admission gate** because an individual stream cannot see concurrent load from other HTTP requests.

## 14. Reactor: Using `flatMap` with Bounded Concurrency

Example in a multi-order read service:

```java
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveOrdersService {
    private final AsyncOrdersRepository repository;

    public ReactiveOrdersService(AsyncOrdersRepository repository) {
        this.repository = repository;
    }

    public Flux<AsyncOrdersRepository.OrderView> loadMany(
            String tenantId, List<UUID> orderIds) {

        final int maxConcurrentReadsInThisStream = 16;

        return Flux.fromIterable(orderIds)
            .flatMap(orderId ->
                Mono.defer(() ->
                    Mono.fromCompletionStage(
                        repository.find(tenantId, orderId)
                    )
                ),
                maxConcurrentReadsInThisStream
            )
            .flatMapIterable(optional ->
                optional.<List<AsyncOrdersRepository.OrderView>>
                    map(List::of)
                    .orElseGet(List::of)
            );
    }
}
```

Meaning:

- `Flux.fromIterable` emits keys as demanded by the stream.
- `flatMap(mapper, 16)` caps concurrently subscribed inner publishers within **this stream**.
- `Mono.defer` postpones calling `repository.find` until subscription/demand arrives.
- `Mono.fromCompletionStage` bridges the async result into a Publisher.
- `AsyncOrdersRepository` still enforces a **service-instance-wide limiter** when many HTTP requests or batch streams run concurrently.
- Filtering out `Optional.empty()` is illustrative for batch reads; **never use it to hide query failures**.

### Why Both the 16 Limit and a Global Limiter Are Needed

Suppose 100 concurrent HTTP requests each start a `Flux` permitting 16 reads:

```text
100 streams x 16 reads/stream = up to 1,600 concurrent logical reads
```

`flatMap(..., 16)` bounds only **one pipeline**. With a global service limit of 80, at most 80 requests enter the Cassandra layer of **that instance**, while excess requests reject early or wait in a designed bounded queue.

**Never extrapolate a local `flatMap` concurrency into an application-wide budget.**

### When Input Order Must Be Preserved

`flatMap` can emit results **out of `orderIds` order** because requests finish at different times.

When ordering is an important contract:

- Use an order-preserving operator like `flatMapSequential` with bounded concurrency, watching its buffer memory cost; or
- Tag items with an index/key and re-sort within bounded scope.

`concatMap` processes sequentially and preserves order easily, but allows only one active inner subscription at a time, which may underutilize batch I/O concurrency.

## 15. What Is Reactive Streams Backpressure?

Reactive Streams defines **demand**: downstream signals capacity for a specific number of items upstream via `request(n)`.

Conceptual diagram:

```text
Downstream consumer
   |
   | request(16)
   v
Upstream publisher
   |
   | emits only per demand and contract
   v
flatMap(concurrency = 16)
   |
   | at most 16 active inner subscriptions
   v
Async Cassandra repository
```

Distinguish three mechanisms:

1. **Publisher backpressure:** items emit according to demand.
2. **Admission control before `executeAsync`:** whether a Cassandra request is allowed to start at all.
3. **Driver/server queues:** once a request is sent, `Flux` backpressure does not retract already-dispatched work.

If the source is an unpausable callback/event stream (e.g., certain event buses), design a **bounded buffer + overflow policy** or pull/pause demand from the source.

**A reactive pipeline is not automatically safe if the source pumps unboundedly or inner work fires requests before subscription.**

## 16. Commonly Misused Reactive Operators

| Operator / technique | Proper use | Common misconception |
| --- | --- | --- |
| `flatMap(mapper, K)` | Caps concurrent inner publishers in one stream | "Whole app only has K requests" |
| `concatMap` | Need ordering and accept sequential execution | "Every workload should be sequential" |
| `flatMapSequential` | Need ordered output with concurrency | "Zero buffering cost if first item is slow" |
| `limitRate` | Tunes demand/prefetch in Reactor chains | "Caps total Cassandra in-flight across all requests" |
| `onBackpressureBuffer` | **Bounded** buffer with an overflow policy | "Unbounded buffering is safe" |
| `onBackpressureDrop` | Domain tolerates dropping items | "Okay to drop payment orders or required events" |
| `onBackpressureLatest` | Only latest state matters | "Safe for any business queue" |
| `timeout` | Deadline on reactive chain | "Server definitely stopped work upon cancel" |
| `retryWhen` | Transient error + idempotent op + budget | "Adding retries fixes overload" |

**Never sacrifice business data for throughput.** For payment commands, audit events, or mandatory mutations, `drop/latest` can be completely wrong. Use durable queues with backpressure/acknowledgements and verify sources when zero event loss is required.

## 17. Reactive Cassandra: Distinguishing One Page from the Full Result

Java Driver 4.x supports async querying, and compatible versions/distributions support Reactive Streams via the corresponding API. When using `AsyncResultSet`, remember:

- `currentPage()` iterates only the current page.
- `hasMorePages()` indicates whether another page remains.
- `fetchNextPage()` explicitly requests the next page.
- `setPageSize(50)` does not limit **total query rows**.
- One API request may require multiple protocol pages depending on design.

### Bounding In-Flight per Page Fetch

```java
CompletionStage<AsyncResultSet> first =
    limiter.submit(() -> session.executeAsync(statement));

CompletionStage<AsyncResultSet> next =
    first.thenCompose(result -> {
        if (!result.hasMorePages()) {
            return CompletableFuture.completedFuture(result);
        }

        // The next page is a new DB operation:
        // route through limiter if controlled individually.
        return limiter.submit(result::fetchNextPage);
    });
```

This snippet illustrates **two page fetches**, not collecting all rows or looping through every page. Include imports for `CompletionStage`, `CompletableFuture`, and `AsyncResultSet` as in earlier Java examples.

### Two Ways to Scope Permits

**Option 1 — One permit per page fetch.** Useful when pages span multiple HTTP requests via a cursor; the permit is held only while a page fetch runs. Other requests can interleave between pages.

**Option 2 — One permit for the full fetch + final processing chain.** Useful for small-budget batches needing an end-to-end bound. However, holding the permit while a slow downstream consumes or a user pauses scrolling risks holding slots far too long.

**Never hold a DB permit for minutes waiting for a user to click "Next page."** API cursors can have TTLs, while DB permits should guard active work.

## 18. Never Run Heavy CPU Work on Driver I/O Threads

A Java callback like:

```java
return session.executeAsync(statement)
    .thenApply(result -> expensiveJsonSerialization(result));
```

may execute on the future-completing thread depending on implementation and scheduling. Heavy CPU or blocking I/O inside it slows driver event loops and other requests' completions.

How to handle it:

- Keep simple callbacks limited to tiny, non-blocking mappings.
- Use a **separate executor with bounded queues and concurrency** for heavy CPU work when truly needed.
- Separate **Cassandra I/O limits** from **CPU/serialization limits**.
- Measure latency from request receipt through serialized response, not just driver result arrival.

### When Using `thenApplyAsync`

```java
CompletionStage<ResponseDto> response =
    session.executeAsync(statement)
        .thenApplyAsync(
            result -> toResponseDto(result),
            boundedMappingExecutor
        );
```

`boundedMappingExecutor` is an application-managed executor with **bounded threads and queues**. The snippet omits its definition; never rely on an uncontrolled default executor and assume all layers are bounded.

Decide whether DB permits release after driver completion or after mapping: if protecting **overall request service capacity**, hold through mapping; if bounding only Cassandra in-flight calls, separate per-layer metrics and permits.

## 19. Throttling QPS Differs from Limiting In-Flight Requests

An API capped at 1,000 QPS does not guarantee low concurrency. If latency rises, in-flight requests rise even at constant QPS.

Example:

| Arrival rate | Mean service time | Hypothetical mean in-flight |
| ---: | ---: | ---: |
| 100 req/s | 50 ms | 5 |
| 500 req/s | 50 ms | 25 |
| 500 req/s | 300 ms | 150 |
| 1,000 req/s | 300 ms | 300 |

Table illustrates steady-state Little's Law. Real numbers must be measured.

### Combining Multiple Layers

- **Token bucket / rate limit:** caps average ingress rate and bursts.
- **In-flight limit:** caps concurrent requests consuming resources.
- **Queue limit:** caps waiting work.
- **Deadline:** caps how long a request may hold resources.
- **Retry budget:** caps extra requests triggered by failures.
- **Circuit breaker:** reduces traffic when downstream cannot respond.

No single layer replaces the others.

## 20. Bounded Queues: How Long Should Requests Wait?

A tiny queue absorbs bursts of tens of milliseconds. A long queue causes requests to expire **before ever getting a DB slot**.

Example:

```text
Max in-flight:        80
Max waiting:          40
Max queue wait:       50 ms
End-to-end deadline:  500 ms
If active + waiting are both full -> reject immediately
```

Numbers are design illustrations only, not official Cassandra thresholds.

### Four Essential Queue Constraints

1. **Max queue length** — cannot buffer unbounded requests in RAM.
2. **Max queue wait** — stale requests waiting too long must leave the queue.
3. **Request deadline** — reject requests whose remaining time is already insufficient.
4. **Fairness / priority** — one tenant or workload cannot monopolize the queue.

If a request expires while queued, **remove it from the queue and never issue a CQL request**. Once sent to Cassandra, cancelling the client future does not guarantee the server halts immediately.

### Warning About "Async Semaphores"

An implementation using `CompletableFuture` waiters for permits without capping waiting futures is just an **unbounded queue in async clothing**.

If designing async waiters, you must handle timeout failures, cancellation cleanup, races between release and expiry, and single-release guarantees. That complexity makes well-tested libraries or a simple fail-fast gate preferable initially.

## 21. Deadlines and Cancellation: Avoiding Misconceptions

Different deadlines apply at different layers:

```text
HTTP client deadline
     |
API budget, auth/rate/queue wait
     |
Java driver request timeout
     |
Cassandra coordinator/replica timeout
```

Suppose HTTP has a 500 ms deadline and a request waited 450 ms in a queue. Even if Cassandra runs the SELECT in 100 ms, **not enough time remains** to finish the API call.

A sound design should:

- Check remaining budget **before admission**.
- Evict expired requests from queues.
- Issue requests with timeouts fitting remaining budget per API/driver version.
- Never retry after the deadline expires.
- Release permits when **the scoped work actually finishes**.
- Document that cancellation may **neither roll back nor immediately stop server-side work**.

### Do Not "Release Early" to Fake Higher Throughput

If an HTTP client cancels after 30 ms while the driver request has not completed or cancelled, immediately releasing the slot to admit another request allows **actual physical work to exceed budget**.

The conservative approach ties the slot to completion of the driver stage, paired with request timeouts and tracking for leaked/long-running operations.

**Client timeout does not mean the server stopped working.** This is especially critical for writes.

## 22. Retries and Speculative Execution Multiply Attempts

Suppose a limiter allows 100 logical requests. If driver policy triggers a speculative attempt on 15% of reads plus error retries, coordinators/replicas can still see **well over 100 physical attempts**.

```text
100 admitted logical requests
    |
    +--> 100 primary execution attempts
    +--> ~15 speculative attempts (illustrative)
    +--> retries after errors
    |
    v
>100 coordinator attempts active at once
```

Therefore:

- A service-layer limiter **does not replace** `RetryPolicy` and `SpeculativeExecutionPolicy`.
- Only set `setIdempotent(true)` after verifying repeat-safety semantics.
- Be extra cautious with counter increments, list appends, side effects, and LWTs.
- A request timeout does not prove replicas never applied the mutation.
- When multiple HTTP/message-gateway layers retry, enforce an **end-to-end retry budget**.

### Concurrency Limits Alone Cannot Stop a Retry Storm

When a cluster slows down, 100 slots stay occupied longer. Raising `maxInFlight` to "stop `BusyException`" while allowing heavy retries can make cluster overload worse.

**Rule:** when p99 and pending queues climb, inspect load sources, query shapes, retries/speculation, and downstream health first. Never raise caps as a knee-jerk reaction.

## 23. Consistency Levels Change Replica Workload

In Cassandra, the coordinator selects replicas via partition key/token and keyspace RF/DC. Consistency level dictates how many replicas must respond before the request succeeds.

Example with RF=3 in a local datacenter:

| CL | Conceptual meaning | Impact on in-flight time |
| --- | --- | --- |
| `LOCAL_ONE` | One local replica responds | Often faster, though may observe stale versions in some cases |
| `LOCAL_QUORUM` | Two local replicas respond | Latency and availability depend on at least a local quorum |
| `ALL` | Every replica per RF responds | Sensitive to any slow or offline replica |
| `QUORUM` | Overall quorum across replication | Across multi-DC, response paths can differ |
| `EACH_QUORUM` | Write quorum in every DC | Different cost and availability profile |

**Never lower CL just to "reduce in-flight count"** when the application requires stronger consistency guarantees. That alters the correctness contract, not merely performance tuning.

### Local DC Matters

A Java app running in `dc1` whose driver local DC points to `dc2` adds WAN round-trips, holds slots longer, and drives up in-flight concurrency at the same QPS.

Check:

- `withLocalDatacenter(...)` or effective driver configuration.
- Keyspace RF under `NetworkTopologyStrategy`.
- Actual coordinator/DC handling requests.
- Replication/repair/streaming health.
- Per-statement CL.

**Re-measure admission budgets whenever CL, RF, local DC, or topology changes.**

## 24. One "Request" Can Still Consume Heavy CPU and I/O

Even with only 80 concurrent SELECTs, if 10 scan a 100,000-row partition full of tombstones, the cluster can saturate.

Cost drivers include:

- Does the query include the full partition key on the right query-driven table?
- Are there hot partitions or oversized buckets?
- How many SSTables must be read, and is there compaction backlog?
- Are tombstones/expired TTLs or delete-heavy workloads present?
- How many rows/bytes are returned, and how does paging behave?
- Are SAI/secondary indexes or `ALLOW FILTERING` widening the read scope?
- Is the driver fetching many consecutive pages?
- Does the query invoke expensive UDFs/UDAs?
- What is the network latency between coordinator and replicas/DCs?

### Prioritize Workload Classification

| Request class | Example | Admission strategy |
| --- | --- | --- |
| Small PK lookup | `orders_by_id` | Global cap and tenant cap |
| Bounded paged read | `orders_by_customer_day`, 25 rows/page | Cap per page fetch, max page size |
| Batch import/write | Many events by key | Bounded producer demand/queues, dedicated cap |
| Repair / maintenance | Node/operator tasks | Bypasses Java limiter, yet shares server budget |
| Analytics / broad scan | Many partitions/token ranges | Separate bulkhead, lower concurrency |
| LWT / counter writes | Idempotency-sensitive mutations | Dedicated caps and retry policies |

A single flat cap across all query types lets a few heavy queries starve everything else. Larger systems use **weighted permits** or separate bulkheads by cost tier.

## 25. Bulkheads: Prevent One Business Flow from Consuming All Capacity

*Bulkheads* borrow from ship compartments: flooding one compartment does not sink the entire vessel.

Suppose a service handles:

- Order-status read API.
- Report sync batch.
- Order-update API.
- Background reconciliation job.

If all four share a single cap of 100 and the batch grabs all 100 slots, user-facing reads get rejected.

### Illustrative Budget Split

```text
Global Cassandra in-flight cap per instance: 100

Interactive reads:          max 50
Business writes:            max 30
Batch/reconciliation:       max 20

Each group has its own cap; overall sum governed
at a shared admission layer when needed.
```

**Do not simply create three unrelated semaphores** and assume their sum stays 100 if anything else shares capacity. Design consistent permit acquisition and release ordering (e.g., global first then category, or one unified admission controller allocating quotas).

The 50/30/20 split is illustrative; measure QPS, deadlines, and query costs before setting real budgets.

### Priority Does Not Mean Starvation

Giving user reads absolute priority can starve writes or reconciliation forever. Define **minimums and maximums** aligned with SLOs, deadlines, and operational health—never lose mandatory events solely to favor UI traffic.

## 26. Multi-Tenant: Per-Tenant and Service-Wide Caps

Suppose one tenant launches 50 jobs, each reading thousands of partitions. With only a global cap, that noisy tenant can exhaust capacity for every other tenant.

Two-tier model:

```text
Request from Tenant A
        |
        v
  Global capacity?
        |
        v
  Tenant A capacity?
        |
        v
   Cassandra query
        |
        v
 Release both slots
```

A solid design must address:

- Total cap per service instance.
- Caps per tenant/principal/job.
- Separate quotas for batch vs. interactive traffic.
- Evicting inactive tenant state so semaphore maps do not grow unboundedly.
- Never acquiring/holding permits when validation or authentication already failed.
- If the global permit succeeds and the tenant permit fails, **release the global permit immediately**.
- Preventing leaks or double-releases on cancellation, errors, or races.

### Never Trust Client-Supplied Tenant IDs

If an API accepts an unverified `tenantId` parameter, callers can spoof another tenant to bypass rate limits. Derive tenant scope from the authenticated principal or verify it via authorization.

**A tenant limiter is a resource boundary, not data-access authorization.** Both quotas and tenant-scoped CQL WHERE clauses remain mandatory.

## 27. Multiple Instances: A JVM Cap Is Not a Cluster Cap

Example:

```text
10 application instances
each instance has 80 in-flight slots

Theoretical max fleet logical in-flight:
10 x 80 = 800 requests
```

If autoscaling grows to 30 instances while keeping 80 each:

```text
30 x 80 = 2,400 logical in-flight requests
```

The Cassandra cluster does not gain capacity just because more Java pods booted. Deployment sizing must factor in **max application replicas**, QPS, retry/speculative rates, and Cassandra capacity.

### Management Options

1. **Size per-instance caps against max app replicas**, reserving headroom for scale-out.
2. **Gateway rate/concurrency limits** to bound total ingress alongside per-instance caps.
3. **Distributed quota coordinator** when strict global caps are truly required, accepting quota-store overhead and failure modes.
4. **Autoscale on backlog and downstream headroom**, not just app CPU.
5. **Per-tenant quotas** keyed consistently across instances or backed by a central quota service.

Never use one Java semaphore and claim "Cassandra sees at most 80 requests system-wide."

### Distributed Semaphores Have Their Own Failure Modes

A lease/permit store can lose connectivity or experience client crashes, requiring TTLs/leases and protection against double grants. Expiring a lock/lease **does not guarantee** the underlying Cassandra request stopped.

When the goal is protecting the server from load, **local fail-fast caps + global rate limits + observability** are often simpler, safer, and have fewer dependencies than a complex distributed semaphore.

## 28. Retries Across HTTP, Kafka, and Batch Jobs

Backpressure must span end-to-end from the event source:

### HTTP APIs

- On overload, return `429`/`503` per contract.
- Callers apply jittered backoff and deadlines.
- Prevent gateways from endlessly retrying non-idempotent `POST`s.
- Use circuit breakers/bulkheads to protect downstream layers.

### Kafka / Queue Consumers

- Tune poll batch size and handler concurrency.
- Pause/reduce demand when DB limits saturate; resume when capacity returns.
- Ack/commit offsets only after required business steps complete per design.
- Never drop critical mutations on overflow without compensation or durable retries.
- Account for rebalancing and duplicate delivery; idempotency keys and event IDs remain essential.

### Scheduled Batches

- Partition work into bounded pages/chunks.
- Keep at most K tasks active; never build a million futures at once.
- Persist checkpoints to resume after restarts.
- Enforce deadlines and "stop on overload" instead of raising concurrency.
- Track progress and rate-limit so online SLOs stay intact.

**When upstream supports real demand or pause signals, use them.** Pushing pileups into an unbounded in-app queue is not backpressure.

## 29. Graceful Shutdown and Draining

When an instance is asked to stop (deployment/restart):

1. Stop admitting new work at the admission gate.
2. Drain/reject incoming requests per gateway lifecycle.
3. Wait for valid in-flight work to finish **within the shutdown deadline**.
4. Persist or handle unacknowledged batches per contract.
5. Close `CqlSession` once work has drained within acceptable limits.
6. Log unfinished operations and trigger retry/recovery policies.

Closing the session while many futures remain active causes the app to lose outcomes while Cassandra may still apply mutations. Handle writes as **outcome unknown**, never assuming everything cancelled cleanly.

### How Should In-Flight Count Reach Zero?

In a non-queuing limiter, once new admissions stop, active counts fall as stages complete or time out. If counts hang, investigate:

- Is an operation hanging without completing its stage?
- Is I/O or a callback blocking the event loop?
- Is the driver request timeout configured and firing?
- Are futures retained after HTTP cancellation?
- Is there a permit leak or double-release bug in wrapper code?

**Never reset permit gauges to 0 artificially** while Cassandra requests remain active; dashboards look clean while admission control breaks.

## 30. Minimum Metrics for Admission Control

| Metric | Meaning | Warning sign |
| --- | --- | --- |
| Current `in_flight` | Logical requests holding slots | Pinned at max for long stretches |
| `in_flight_max` | Configured cap | Mismatched against app instance count |
| `admitted_total` | Accepted requests | Sustained QPS near capacity |
| `rejected_total{reason}` | Rejected requests | Sudden spikes or sustained rejections |
| `queue_depth` (if queued) | Waiting requests | Hitting queue limit |
| `queue_wait_ms` | Wait time before DB | p95 approaching deadline |
| `db_execution_ms` | DB/mapping stage duration | p99 climbing before rejections begin |
| `request_end_to_end_ms` | Ingress to response | SLO breached even if DB p99 looks low |
| `driver_in_flight` (if available) | Requests managed by driver | Diverges sharply from app logical count |
| `retry/speculative_count` | Request amplification | Surges when cluster slows |
| `coordinator/DC` | Where requests coordinate | Cross-DC skew, hotspots |
| `tpstats pending/dropped` | Server-side queues/stages | Rising under saturation |
| CPU/GC/disk await/network | True node resource budget | Approaching saturation before full outage |
| Compaction/repair/streaming | Background resource contention | Coincides with p99 spikes |

Never put millions of `tenant_id` values directly into metric labels; track per-tenant quotas internally while keeping dashboard labels grouped by top tiers/capacity buckets to bound cardinality.

### Do Not Alert Only on Rejections

If rejections are zero while p99 and driver in-flight climb steadily, the system is **approaching overload**.

A well-behaved cap will produce rejections during bursts; sometimes that is **expected protective behavior** when evaluated alongside SLOs and demand. Alerts should distinguish:

- Brief, controlled bursts.
- Sustained rejections due to insufficient capacity.
- Unusually slow DB holding permits too long.
- App scale-out driving higher cluster load.
- One tenant or query shape hogging all slots.

## 31. Example Capacity Budget Across Multiple App Instances

Suppose the lab cluster was tested to sustain **2,000 logical reads/s** of a small query with required headroom. Four service instances handle a mix of reads and writes.

Illustrative calculation:

```text
Observed healthy mean latency:   40 ms
Observed logical arrival rate:   1,500 req/s

Little's Law:
  Average in-flight ~ 1500 x 0.040 = 60

4 application instances:
  ~15 average in-flight per instance if balanced

Initial canary cap:
  40 per instance = 160 fleet-wide logical in-flight
```

**The cap of 40 does not come straight from the formula.** It is a canary starting point to validate under bursts, p99 targets, SLOs, max instance counts, and retry amplification. If 4 instances scale to 12, 40 per instance becomes **480 logical in-flight**—recalculate accordingly.

### How Much Headroom Should You Keep?

No universal ratio exists. With Cassandra running compaction/repair, node failures, or traffic peaks, headroom must cover worst-case events. Validate via load tests:

- CPU/heap/GC stay stable during bursts.
- Disk I/O latency does not climb uncontrollably.
- CQL p99 and error rates meet SLOs.
- No retry storms occur.
- Losing one node/rack allowed by RF/CL still carries required traffic.
- Background repair/streaming does not push latency past budget.

A threshold picked because "CPU looked low during a 1-minute test" is inadequate.

## 32. Load Testing: Find the Stable Region, Not Just Peak Numbers

### Test A — Stepped QPS Ramp

1. Start low with warmed caches.
2. Step up arrival rate keeping **query shapes**, RF/CL, and hot-key skew constant.
3. Record in-flight, rejections, queue wait, p50/p95/p99, and retries.
4. Watch CPU/GC, disk/network, `tpstats`, and compaction.
5. Find the knee where latency climbs rapidly while throughput stops scaling proportionally.
6. Set caps below the knee with headroom for bursts and failures.

### Test B — Bursts

```text
Steady: 300 req/s
5-second burst: 1,800 req/s
Post-burst: 300 req/s
```

Evaluate:

- Did the limiter actually cap started requests?
- Did rejections and queue depth stay within policy?
- Once the burst ended, did latency and in-flight **recover**?
- Did upstream trigger a retry spike after rejections?
- Did heap grow from piled-up futures?

### Test C — Slow Node

In **staging/lab**, inject controlled slowness on a replica/coordinator. Observe:

- How much longer are permits held?
- Does admission block excess requests before the driver?
- Do timeouts/retries/speculation exceed resource budgets?
- Does the API degrade gracefully or trigger a retry storm?
- When the node recovers, does queued backlog drain without causing a secondary overload?

### Test D — Noisy Tenant

Drive heavy load for Tenant A and light load for Tenant B. Verify Tenant B still meets its minimum SLO per fairness policy without Tenant A draining all permits/queues.

**Run fault injection only in authorized environments.** Never intentionally stress production Cassandra outside planned exercises.

## 33. Why Benchmark Tools Can Mislead

Load generators must model arrival rates cleanly:

- **Closed-loop:** clients send the next request only after the previous finishes. When the server slows, arrival rate drops automatically, masking saturation.
- **Open-loop:** clients maintain an arrival schedule independent of latency, exposing queue buildup under bursts.
- **Coordinated omission:** measuring only sent or successful requests omits queue wait and rejected requests, making p99 look artificially rosy.

Reports must include:

- Offered QPS alongside **admitted/completed/rejected QPS**.
- Queue wait and end-to-end latency, not just DB execution.
- Timed-out and cancelled requests.
- Extra attempts from retries/speculation.
- Row/partition sizes and key distributions.
- App instance counts and driver pool sizes.
- RF/CL, local DC, and compaction/repair state.

**Never compare throughput solely on successful requests while ignoring 30% rejected requests.**

## 34. Incident A — Firing One Million `executeAsync` Calls and Hitting OOM

**Symptom:** heap climbs, futures/callbacks fill RAM, latency rises across all requests, and the app OOMs.

**Cause:** the producer creates requests faster than downstream completes, with no admission or queue bounds.

**Remediation:**

1. Pause/throttle the producer and shield the service from bursts.
2. Switch to a demand-driven stream or sliding window of size K.
3. Place a global limiter before `executeAsync`.
4. Bound queues and enforce deadlines if queuing is used.
5. Measure heap, in-flight count, driver queues, and server load.
6. Only once stable, increase K incrementally via canary.

You cannot solve the root cause by quadrupling heap while leaving a loop firing one million requests.

## 35. Incident B — Using `Semaphore.acquire()` in WebFlux

**Symptom:** app CPU looks low, yet request handlers freeze, Reactor event-loop threads block, and p99 spikes even on endpoints that never touch Cassandra.

**Cause:** blocking waits on the event loop.

**Remediation:** switch to `tryAcquire()` + fail fast or bounded async waiters. If blocking code must run elsewhere, isolate it in an appropriate scheduler/executor while **still bounding queues and concurrency**.

Never move the entire service onto an unbounded thread pool.

## 36. Incident C — Per-Request Limit of 16, Yet DB Still Overloads

**Symptom:** every `flatMap` uses `concurrency=16`, yet Cassandra receives thousands of concurrent requests.

**Cause:** hundreds of concurrent HTTP requests/streams run simultaneously. Concurrency 16 is **per stream**, not **per JVM**.

**Remediation:** add a global admission cap at the repository/gateway sized for max app instances, add per-tenant rate controls, and enforce query-class bulkheads.

## 37. Incident D — Rejections Spike During Compaction

**Symptom:** service holds its cap steady, yet many requests return `BusyException` while disk await and compaction backlog rise.

**Cause:** Cassandra slows down, so each request holds its permit longer; arrival rate exceeds sustainable throughput.

**Remediation:**

- Do not immediately raise the cap.
- Inspect compaction schedules, disk headroom, tombstones, and query shapes.
- Throttle batch/analytics traffic; prioritize critical queries.
- Reduce upstream rate/bursts and use jittered retry backoff.
- Verify permits and p99 recover once compaction subsides.

If the cap successfully shielded Cassandra from collapse, rejections are a signal to **shed load or scale capacity properly**, not necessarily a limiter bug.

## 38. Incident E — Cancellation Leaks Extra Load

**Symptom:** users close browsers, the app releases permits right away, yet the server keeps running queries. New requests get admitted, pushing physical concurrency past budget.

**Cause:** confusing **HTTP cancellation** with **stopped Cassandra RPCs**.

**Remediation:** track driver stage completion, tie permits to actual scoped completion, configure timeouts/cancellation per driver version, and keep server-side headroom rather than treating cancellation as guaranteed instant resource reclamation.

For mutations, cancellation **is not rollback**.

## 39. Incident F — Retry Storm After `503`

**Symptom:** the gateway returns `503` for excess load, and clients retry in unison, hitting the cluster in waves.

**Cause:** multiple retry layers lacking a shared budget, jittered backoff, or max attempts.

**Remediation:** add rate limiting, exponential backoff with jitter, policy-backed `Retry-After`, fewer retry layers, and end-to-end deadlines. Never blindly retry non-idempotent writes.

## 40. Incident G — One Tenant Causes Timeouts for Everyone

**Symptom:** Tenant A's batch holds nearly all global permits; low-QPS Tenant B gets rejected.

**Cause:** missing per-tenant/per-class bulkheads or fair scheduling.

**Remediation:** enforce per-tenant quotas, global caps, priority with minimum reserved capacity, TTL cleanup for quota state, and tenant-tier monitoring. Never weaken RBAC or trust client-supplied tenant IDs for quota isolation.

## 41. Common Misconceptions

**"Async automatically provides backpressure."** False. `executeAsync` does not stop a producer from spawning unbounded futures.

**"Having 8 Netty threads means at most 8 concurrent Cassandra requests."** False. One event loop can manage many concurrent requests.

**"A `flatMap(16)` cap limits the whole system."** False. It applies only within that stream's scope.

**"`CompletableFuture.allOf` runs requests in batches."** False. It merely awaits futures that were already launched.

**"`Semaphore.acquire()` is fine because the DB is async."** False if the calling thread is an event loop.

**"Using a queue makes it safe even if unbounded."** False. Unbounded queues still exhaust memory and spike latency.

**"Releasing the permit right after `executeAsync` still limits concurrency."** False. The driver has only returned a future.

**"Client timeout cancelled all server work."** Never assume this.

**"Guarding 100 logical requests means at most 100 replica RPCs."** False. Coordinators contact multiple replicas and drivers retry/speculate.

**"Having a QPS cap eliminates the need for an in-flight cap."** False. Rising latency drives concurrency up even at constant QPS.

**"Raising in-flight until CPU hits 100% is optimal."** False. Cassandra also depends on disk/network/GC, tail latency, and fault tolerance.

**"`LOCAL_ONE` is always better because it lowers pressure."** Not purely a performance choice; changing CL alters consistency semantics.

**"Any partition-key lookup is cheap."** False. Hot partitions, large collections, and heavy tombstones can be very expensive.

**"Reading only 10 rows needs no page limit."** False if queries/drivers auto-fetch pages, or the server scans tombstones/SSTables to find live rows.

**"Doubling app instances via autoscaling doubles Cassandra capacity."** False. Total fleet in-flight load increases instead.

**"Sharing one global quota across all tenants is fair."** False if one tenant can monopolize every slot.

**"Rejections are errors to mask with infinite retries."** False. Rejections are load signals requiring controlled handling.

**"Dropping CL or turning on speculation fixes queue overload."** No guarantee, and it can worsen correctness or load.

**"Using Reactor guarantees there is no blocking code."** False. Callbacks can still call `block()`, `Thread.sleep`, or `Semaphore.acquire`.

**"Setting a 30-second timeout prevents request failures."** False. It holds permits longer and inflates queues.

**"Backpressure allows dropping any event."** False for mutations, payments, audits, or mandatory workflows.

**"Having a limiter means we don't need server observability."** False. Driver and replicas incur distinct work and costs.

## 42. Pre-Rollout Test Matrix

| Case | Input / condition | Expected |
| --- | --- | --- |
| T1 | Max=2, 2 stages incomplete | 3rd request rejected before `executeAsync` |
| T2 | One stage completes normally | Exactly one permit released |
| T3 | One stage completes exceptionally | Permit still released |
| T4 | Supplier throws synchronously | No permit leak |
| T5 | Supplier returns null stage | No permit leak; clear error |
| T6 | 1,000 concurrent requests against max=20 | At most 20 admitted in-flight on instance |
| T7 | Malformed request | Validation fails before admission |
| T8 | Unauthorized tenant | No query sent; no DB slot consumed |
| T9 | Reactor stream with concurrency 16 | At most 16 inner subscriptions in stream |
| T10 | 100 concurrent Reactor streams | Global limiter enforces fleet/instance cap |
| T11 | Multi-page fetch | No unbounded `all()`; each page passes gate appropriately |
| T12 | CPU-heavy application callback | Does not block driver I/O event loop |
| T13 | HTTP client cancels | Permit/lifecycle handled safely while DB stage runs |
| T14 | Driver timeout | Stage fails; permit released |
| T15 | Queue of 40 full | New requests rejected; queue does not grow |
| T16 | Queue wait exceeds 50 ms | Request expires before hitting DB |
| T17 | Tenant A heavy load, Tenant B light | Tenant B gets designed quota/fairness |
| T18 | 10 app instances | Total cap evaluated across deployment |
| T19 | Autoscale to 30 instances | Does not unexpectedly blow Cassandra budget |
| T20 | Retry/speculation enabled | Physical attempts measured separately from logical cap |
| T21 | One slow replica | Admission prevents runaway feedback loops |
| T22 | Background compaction/repair | p99/errors/rejections and disk headroom monitored |
| T23 | Node restart | System degrades safely; no retry storm |
| T24 | Rate limit + concurrency limit | Both policies work together without conflict |
| T25 | Graceful shutdown | Stops new admissions, drains, and closes in order |
| T26 | Empty batch | Zero Cassandra requests created |
| T27 | Batch of one million IDs | Does not allocate one million futures at once |
| T28 | Hot partition data | Separate budget or cost-based rejection when needed |
| T29 | HTTP client retries `503` | Jittered backoff, deadline, and max attempts |
| T30 | Sweep maxInFlight=20/40/80 | Chosen by SLO and resources, not throughput alone |

### Testing Real Concurrency with Test Doubles

For `AsyncInFlightLimiter`, use **incomplete `CompletableFuture`s** to occupy slots:

```java
import java.util.concurrent.CompletableFuture;

// Illustrative test setup, e.g., limiter with maxInFlight=2.
AsyncInFlightLimiter limiter =
    new AsyncInFlightLimiter(2);

CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();

var acceptedA = limiter.submit(() -> a);
var acceptedB = limiter.submit(() -> b);

// Third request fails fast because no slots remain.
var rejected = limiter.submit(
    () -> CompletableFuture.completedFuture("never started")
);

// Assert getInFlight()==2 here.
// After a.complete("ok"), one slot is released.
a.complete("ok");
```

This is a **partial test illustration**, not a complete JUnit class. In a real test, use proper assertions, inspect the rejected future, and verify the third request's supplier **never ran**.

## 43. Phased Rollout Runbook

### Phase A — Preparation

1. Inventory query shapes: PK SELECTs, paged reads, writes, LWTs, batches, analytics.
2. Confirm Cassandra release, Java Driver 4.x version, RF/DC, CL, and connection settings.
3. Baseline QPS, in-flight, p95/p99, timeouts, and retry/speculative rates.
4. Measure node headroom: CPU, GC, disk I/O, network, and compaction.
5. Estimate concurrency via Little's Law and validate against burst/peak loads.
6. Set per-instance, per-query-class, and per-tenant limits accounting for **max app replicas**.
7. Choose fail-fast vs. bounded queue, deadlines, and HTTP/Kafka signaling.
8. Ensure every `executeAsync` on the target path sits behind the admission gate.
9. Write unit/integration tests covering permit release on success/error/cancel.
10. Prepare feature flags and a safe rollback to prior settings.

### Phase B — Canary

11. Enable the limiter on a subset of traffic/instances.
12. Inspect admitted/rejected counts, in-flight, queue wait, and end-to-end p99.
13. Compare driver requests and retries/speculation against logical operations.
14. Check Cassandra `tpstats`, CPU/GC, disk await, and SSTables/compaction.
15. Test bursts, node slowness, and noisy-tenant behavior where permitted.
16. Watch upstream retries to ensure no synchronized waves after `429/503`.
17. Never raise caps if server p99, queues, or disk are degrading.
18. Observe across multiple peak-load and background-job cycles.

### Phase C — Operations

19. Re-evaluate caps whenever service replica counts change.
20. Re-evaluate after changing RF/CL, local DC, schema, page size, or driver policies.
21. Maintain separate capacity planning for foreground vs. batch jobs.
22. Perform graceful draining during rolling deployments.
23. Report successes, rejections, timeouts, and queue wait times together.
24. Keep bind values, tokens, customer IDs, and PII out of logs and metrics.
25. Assign owners for quota tuning and overload runbooks.
26. Rehearse rollbacks and recovery during heavy Cassandra compaction/repair.

## 44. Questions and Exercises

1. Why does `executeAsync()` fail to guarantee a safe number of concurrent requests?
2. Distinguish QPS, in-flight concurrency, queue depth, and connection pool capacity.
3. At 500 req/s and 100 ms mean latency, what average in-flight count does Little's Law predict?
4. Why can rising p99 increase concurrency even when QPS stays constant?
5. Why must admission happen **before** `session.executeAsync`?
6. Contrast fail-fast, bounded queues, and unbounded async waiters.
7. Why is `Semaphore.acquire()` unsuitable on a Netty/Reactor event loop?
8. What does `Semaphore.tryAcquire()` solve, and what does it leave unsolved?
9. Why must permits be released when a `CompletionStage` completes exceptionally?
10. What must happen if the supplier throws synchronously before returning a future?
11. Why is `finally {release();}` right after `executeAsync` wrong?
12. Does `CompletableFuture.allOf` bound how many requests are dispatched?
13. Compare fixed batching vs. sliding-window concurrency.
14. What scope does `flatMap(mapper, 16)` actually govern?
15. With 200 HTTP requests each running a stream of 16 reads, what is the theoretical combined load?
16. Why is a global limiter needed even with Reactor `flatMap`?
17. Does Reactive `request(n)` backpressure retract an already-sent Cassandra request?
18. Why is `onBackpressureDrop` dangerous for payment events?
19. When does `flatMapSequential` fit, and where is its buffer cost?
20. A paged SELECT spans 10 pages; should limits guard per page or the full workflow?
21. Why shouldn't you hold a DB permit while a user waits 5 minutes to open the next page?
22. Does a reactive chain `timeout` guarantee the server halted a mutation?
23. In WebFlux, why does heavy CPU mapping inside callbacks need its own executor/bulkhead?
24. How do rate limiting and in-flight limiting solve different problems?
25. If a limiter caps at 80 across 20 pods, what is the theoretical maximum logical requests?
26. Why does autoscaling Java pods not give Cassandra extra capacity?
27. Design a global + per-tenant quota without leaking permits.
28. Why is a service account with `SELECT` insufficient for tenant data access isolation?
29. One logical request triggers a retry and a speculative attempt. Will replica RPC count equal 1?
30. Why shouldn't you raise `maxInFlight` right away when p99 and queues climb?
31. How can RF=3 and `LOCAL_QUORUM` affect permit hold times?
32. Why is switching CL to `ONE` a correctness contract change?
33. Why can a PK-scoped query still be expensive if the partition is huge?
34. How should a million-row batch use demand and checkpoints?
35. When upstream Kafka cannot drop events, what should you do instead of dropping?
36. In load tests, why must `rejected QPS` be reported alongside `completed QPS`?
37. How does coordinated omission skew latency measurements?
38. Why should tests run alongside active compaction/repair?
39. On HTTP client cancellation, how must permits and driver stages be managed?
40. Design a dashboard covering in-flight, rejections, queue wait, driver attempts, and server resources.
41. Diagnose: "the limiter enforces 100, yet Cassandra sees over 100 coordinator attempts."
42. If p99 drops while write timeouts climb, should you keep raising concurrency?
43. If one tenant grabs 90% of slots, how should bulkheads and quotas be applied?
44. Describe a graceful shutdown flow that avoids losing outcomes of completed mutations.
45. Write a test double using incomplete `CompletableFuture`s to prove the cap cannot be exceeded.

## 45. Final Decision Flow

```text
         REQUEST NEEDS CASSANDRA
                    |
                    v
         Input/auth/tenant valid?
             |              |
            No              Yes
             |              |
          Reject            v
                     Enough deadline left?
                        |         |
                       No         Yes
                        |         |
                     Timeout      v
                          Global / tenant /
                          class slot free?
                             |        |
                            No        Yes
                             |        |
                      Bounded queue?  v
                        |      |   executeAsync()
                        |      |      |
                       No      Yes    v
                        |      |   CompletionStage
                     429/503  Wait    |
                           (bounded Success/Error
                           deadline)  |
                                      v
                               Release permit
                                      |
                                      v
                              Response / metrics
```

**Remember:** **The async Java Driver avoids blocking threads while waiting on Cassandra, but does not stop an application from dispatching unbounded work.** Always place **admission control before `executeAsync`**, bounding *in-flight* logical requests, queues, and wait times, and releasing permits only when the async work truly finishes. In Reactor, `flatMap(..., concurrency)` bounds a single stream, while the service and multi-instance fleet require their own budgets. Estimate with **Little's Law**, then lock in caps via **load tests, p95/p99, rejections, retries/speculation, and replica CPU/GC/disk metrics**. True protection means **keeping the system available under overload**, not forcing every request into Cassandra at any cost.
