# Coordinating Timeouts, Retries, and Backpressure

> **Chapter:** Async and Reactive  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Apache Cassandra, distributed wide-column architecture, partition keys, query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, troubleshooting, and Java Driver.

## 1. The Problem: Three Good Mechanisms Combining Into an Outage

A Java service uses **executeAsync** to read Cassandra data. Normally, every query finishes in tens of milliseconds. When several replicas slow down due to compaction and disk I/O, response times climb. The application reacts by raising timeouts and retrying multiple times; meanwhile, a reactive pipeline keeps accepting more HTTP requests. Result: deep queues, surging in-flight requests, retries piling on extra load, and Cassandra reporting **Overloaded**, **ReadTimeout**, or **Unavailable**.

Three distinct controls interact in the same scenario:

- **Timeout / deadline:** how long an operation is allowed to take before the caller no longer wants the result?
- **Retry:** should we try again after a failure, how many times, and under what conditions to avoid corrupting data?
- **Backpressure / admission:** how many concurrent requests are permitted, or how many rows can downstream demand and absorb?

Tuning each knob in isolation can make an app look like it has "fewer timeouts" while actually driving **higher p99, deeper backlogs, and worse Cassandra overload**.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish timeouts across **caller, driver, Cassandra server, and individual page fetches**.
2. Design **end-to-end deadlines** and retry budgets covering queueing, backoff, and downstream processing.
3. Classify Cassandra errors so only **safe/idempotent** operations retry, avoiding retry storms under overload.
4. Use **CompletionStage**, non-blocking scheduled retries, and **in-flight** caps in Java.
5. Understand **Reactive Streams demand**, maintaining backpressure across pipelines, and how it differs from simply using an async API.
6. Integrate paging, consistency levels, partition keys, metrics, and operational runbooks for failures under load.

> **Safety rule:** A timeout in Java **does not prove a write was not applied** in Cassandra. Cancelling a future **does not automatically undo work sent to the server**. Always design idempotency and business-level reconciliation.

## 2. Three Clocks and a Load Limiter

Look at the complete path:

~~~mermaid
flowchart LR
    U["HTTP/gRPC Caller\nDeadline"] --> A["Java API\nAdmission/queue"]
    A --> D["Java Driver\nRequest timeout"]
    D --> C["Cassandra coordinator\nExecution timeout"]
    C --> R["Replica\nDisk/GC/compaction"]
    R --> C
    C --> D
    D --> A
    A --> U
    A --> B["Downstream processing\nCompletionStage / reactive demand"]
~~~

In practice there are **more than three timeouts**. Exact names vary by API/driver/version, yet they fall into clear layers:

| Layer | Start / end | Who decides? | When expired, what can happen? |
|---|---|---|---|
| **Caller deadline** | From API request receipt until caller stops waiting | HTTP/gRPC / business API | Caller leaves; Java must stop doing useless work |
| **Admission / queue wait** | From permit request until dispatched to driver | Java service | Should reject when slots are full rather than queueing endlessly |
| **Driver request timeout** | Per driver-configured request scope | Java Driver | Client sees timeout; coordinator may have finished or still run |
| **Server read/write timeout** | While Cassandra coordinates reads/writes across replicas | Cassandra coordinator/server | Reports `ReadTimeout`/`WriteTimeout`; write state uncertain |
| **Per-page fetch** | From `fetchNextPage` call until page returns or errors | Driver + Cassandra | Paging chain can halt mid-way |
| **Downstream deadline** | Sending rows to another system or CPU work | Pipeline / consumer | Slow page handling builds backlog if fetching continues |
| **Retry / backoff** | After failure and before next attempt | Driver or Java policy | Consumes remaining budget and multiplies physical requests |

**Timeout != deadline.** Suppose a request has a 1-second driver timeout, three retries, and two 300 ms backoff delays. Total duration can exceed 3 seconds plus queueing and downstream processing, even though each attempt was "only 1 second."

### 2.1. Time Budgets Must Be Allocated

Let:

~~~text
Total logical request time
  = admission wait
  + sum of Cassandra attempt durations
  + sum of backoffs
  + page & downstream processing
  + serialization / response write

Must be <= business deadline,
with margin for network and cleanup.
~~~

**Hypothetical** example:

| Component | Budget |
|---|---:|
| HTTP deadline | 2,000 ms |
| Max admission wait | 100 ms |
| CQL execution & attempts | 1,400 ms |
| Backoff if any | 200 ms |
| Result processing + HTTP response | 200 ms |
| Margin | 100 ms |

This is an **illustrative allocation**, not a default Cassandra config. Real budgets must reflect observed latency and SLOs. If one attempt already took 1,300 ms, launching another 1,400 ms retry no longer fits a 2-second deadline.

### 2.2. Measure Time Properly

- Log UTC timestamps to correlate events across app, coordinator, and replicas.
- For **durations**, use **`System.nanoTime()`** or telemetry monotonic clocks; never subtract two **`currentTimeMillis()`** values, as wall clocks can jump.
- Track **total end-to-end latency** from API ingress separately from **per-attempt latency**.
- Include permit wait and multi-page processing—never measure only up to when **`executeAsync`** returns the first page.

## 3. Classify Errors Before Deciding to Retry

In Java Driver 4.x, failures arrive via an **exceptionally completed `CompletionStage`**. Never treat every exception as a retryable network blip.

| Signal type | Key meaning | Initial handling |
|---|---|---|
| **`ReadTimeoutException`** | Insufficient read responses before server timeout | Inspect replicas, CL, partition, tombstones, load; limited retry if read is idempotent |
| **`ReadFailureException`** | Replicas reported read execution failure | Inspect server logs/read path; blind retries mask systemic bugs |
| **`WriteTimeoutException`** | Insufficient write ACKs per CL before timeout | **Outcome may be unknown**; retry only if proven safe |
| **`WriteFailureException`** | Write failed per server response | Some replicas may have written; apply business policy |
| **`UnavailableException`** | Insufficient replicas marked alive for CL | Check RF/DC/health; immediate retries rarely create new replicas |
| **`OverloadedException`** | Server lacks capacity for current workload | Slow down, backpressure/shed load; avoid immediate retries |
| **Driver-side timeout** | Driver/caller exceeded configured wait; possibly no server response | Check driver/connections/queues; never assume server did nothing |
| **Auth / TLS / Codec / CQL syntax** | Bad config, permissions, or code | Fix root cause; never retry in a loop |
| **Client admission rejection** | Java service rejected pre-send due to exhausted permits | Shed load / signal caller; do not confuse with server Overloaded |

Exact exception names and scopes depend on your driver/server versions. **`ReadFailure != ReadTimeout`** and **`WriteFailure != WriteTimeout`**; even if both appear during one incident, their diagnostics differ.

### 3.1. Uncertain Outcomes

If the client sees **`WriteTimeout`** after the coordinator dispatched the mutation, some replicas may still have applied the write. When retrying:

- An **`INSERT` with the same primary key and fixed values** is usually easier to prove idempotent.
- **`Counter` increments**, **list appends**, operations with inconsistent TTLs/timestamps, or generating a fresh event ID per attempt are **not idempotent**.
- A timed-out **LWT `IF NOT EXISTS`** may have succeeded; a retry returning **`[applied] = false`** does not prove the first attempt failed.
- Writing to Cassandra and sending an email or charging a card elsewhere does not become end-to-end exactly-once just because CQL is idempotent.

**Rule:** Establish idempotency at the **business and data levels** before enabling driver or app retries. Calling **`statement.setIdempotent(true)`** merely informs the driver—it never turns an unsafe operation into a safe one.

### 3.2. Why Overload Demands Pushing Back in Reverse

When the server reports **`Overloaded`**, immediately re-sending the same request:

1. Increases in-flight requests.
2. Slows queues, GC, disks, and compaction further.
3. Stretches latency, timing out even more requests.
4. Triggers cascading retries from other clients.
5. Escalates into **retry amplification** or a **retry storm**.

A sound policy **rejects in a controlled way**, cuts concurrency, sheds low-priority work, applies jittered backoff, or opens a circuit breaker; when capacity cannot meet the deadline, **failing fast** beats holding an unbounded queue.

## 4. No Consistency Level Substitutes for Load Management

Cassandra selects replicas from the **partition key** and replication strategy. CL dictates how many replicas must respond.

Assume keyspace RF = 3 in **`dc1`**:

| CL | General condition | Trade-off |
|---|---|---|
| **`LOCAL_ONE`** | One replica in local DC | Lighter, may read staler data |
| **`LOCAL_QUORUM`** | Majority of local replicas, typically 2/3 | More responses; requires enough healthy replicas |
| **`ALL`** | All replicas per RF | Fragile to any slow or failed replica |

Under **`LOCAL_QUORUM`**, one failed node can still be tolerated when the other two replicas are healthy. If a remaining node is overloaded, however, CL can time out. **Downgrading `LOCAL_QUORUM` to `LOCAL_ONE` to lower error rates** alters the consistency contract; never slip it into a retry policy silently.

Inspect:

- **Actual RF and topology:** are enough replicas available in the DC the driver considers local?
- **Query shape:** does the statement supply the full partition key or scan many partitions?
- **Hot partitions:** does one tenant or time bucket concentrate load onto a few replicas?
- **Compaction / repair:** are I/O, network, GC, or tombstones slowing replica responses?
- **Payloads / mutations:** huge batches, unbounded collections, or too many SSTables?

Raising timeouts, enlarging page sizes, or changing CL will never split one giant partition into many small ones. Query-driven data modeling remains foundational.

## 5. Reactive Backpressure Differs from Timeouts and Retries

**Asynchronous** means not blocking threads while waiting on I/O. It **does not automatically bound** how many requests can be launched.

**Reactive Streams** adds a contract between **`Publisher`** and **`Subscriber`**: the subscriber signals demand via **`request(n)`**, and the publisher must not emit beyond unfulfilled demand. Yet demand only helps when no stage breaks it with unbounded buffers or queues.

~~~mermaid
sequenceDiagram
    participant H as HTTP / Subscriber
    participant J as Java reactive pipeline
    participant D as Cassandra Driver
    participant C as Cassandra
    H->>J: request(1)
    J->>D: Demand for more results
    D->>C: Fetch data when needed
    C-->>D: Data / pages
    D-->>J: onNext(row)
    J-->>H: Process one row
    H->>J: next request(1) when ready
~~~

This diagram shows **the demand principle**; it does not assert every **`request(1)`** causes exactly one network round-trip to Cassandra, since the driver can fetch pages and buffer rows per its implementation.

| Mechanism | What it controls | What it CANNOT do |
|---|---|---|
| **Timeout** | How long a request/stage may wait | Does not automatically reduce source concurrency |
| **Retry** | Whether to re-try after errors | Does not fix schemas, failed replicas, or server overload |
| **Backpressure** | Data flow pace matching downstream demand | Does not alter deadlines, idempotency, or RF |
| **Admission limit** | How many logical operations can start/stay active | Does not guarantee data correctness by itself |
| **Rate limit** | Requests/bytes/work units per time window | Does not bound total memory if queues remain unbounded |
| **Circuit breaker** | Temporarily sheds calls on failing paths | Does not fix underlying server or data model bugs |

They must be **coordinated**, never picking one mechanism and ignoring the rest.

## 6. Lab CQL: Two Operation Types With Different Policies

To test both behaviors, create an events table and an orders status table. Run only in an authorized test environment:

~~~sql
-- dc1 / RF = 3 applies only when the cluster topology has enough replicas.
CREATE KEYSPACE IF NOT EXISTS async_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS async_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS async_lab.orders_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Where:

- **`events_by_tenant_day`** serves event reads within one **`(tenant_id, event_day)`** partition. Async paging works well here, provided page counts and partition sizes stay bounded.
- **`orders_by_id`** serves lookups/updates by **`(tenant_id, order_id)`**. An **`IF NOT EXISTS`** operation requires conditional outcome handling, unlike an idempotent `SELECT`.
- **`LOCAL_QUORUM`** requires enough replicas in the local DC; on a single-node cluster adjust RF/CL and note the difference from production.

A couple of fixtures:

~~~sql
INSERT INTO async_lab.events_by_tenant_day
    (tenant_id, event_day, happened_at, event_id, event_type, payload)
VALUES
    (11111111-1111-4111-8111-111111111111, '2026-11-21',
     '2026-11-21T08:00:00Z',
     22222222-2222-4222-8222-222222222222,
     'ORDER_CREATED', '{"source":"lab"}');

INSERT INTO async_lab.events_by_tenant_day
    (tenant_id, event_day, happened_at, event_id, event_type, payload)
VALUES
    (11111111-1111-4111-8111-111111111111, '2026-11-21',
     '2026-11-21T08:01:00Z',
     33333333-3333-4333-8333-333333333333,
     'ORDER_VALIDATED', '{"source":"lab"}');
~~~

Prepared `SELECT`:

~~~sql
SELECT happened_at, event_id, event_type
FROM async_lab.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT ?;
~~~

Conditional write:

~~~sql
INSERT INTO async_lab.orders_by_id
    (tenant_id, order_id, status, created_at)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

**Two different retry rules:**

- `SELECT` can be marked idempotent since it mutates no data, though retries still add read load.
- Conditional `INSERT` must handle **`[applied]`** and ambiguous timeouts via state reconciliation / idempotency keys rather than infinite retries.

## 7. Java Driver 4.x Timeouts and Execution Profiles

An illustrative HOCON configuration in **`application.conf`**:

~~~hocon
datastax-java-driver {
  basic {
    contact-points = [ "127.0.0.1:9042" ]
    load-balancing-policy.local-datacenter = dc1

    request {
      timeout = 1500 milliseconds
      consistency = LOCAL_QUORUM
      page-size = 100
    }
  }

  profiles {
    limited-read {
      basic.request.timeout = 1200 milliseconds
      basic.request.consistency = LOCAL_QUORUM
      basic.request.page-size = 64
    }

    conditional-write {
      basic.request.timeout = 2 seconds
      basic.request.consistency = LOCAL_QUORUM
    }
  }
}
~~~

These are **illustrative values**, not SLOs or defaults for every Cassandra cluster. Verify syntax and options against your driver version; **driver timeouts are not server timeouts**.

Selecting a profile on a statement:

~~~java
BoundStatement read = preparedRead.bind(tenantId, day, 200)
    .setExecutionProfileName("limited-read")
    .setIdempotent(true);

CompletionStage<AsyncResultSet> firstPage =
    session.executeAsync(read);
~~~

Driver 4.x uses **immutable** statements, so setters return a **new statement**. Explicit statement values can override profile settings. If your app overrides timeouts/consistency per request, expose the effective policy in observability.

**Do not configure retries by gut feel:** the driver has **its own retry policy**, and some failures may already have been retried before the future fails. When adding Java-service retries, account for driver attempts so load does not multiply unexpectedly.

### 7.1. Server Timeouts vs. Client Timeouts

When the server emits **`ReadTimeout`**, it reflects Cassandra's request-processing timeout. When Java hits **`driver request timeout`**, the coordinator may still be executing or already finished. If the HTTP tier also sets timeouts and proxies/gateways retry, one logical request can spawn **many physical requests**.

Track all of:

~~~text
Logical requests arriving at HTTP
Actual driver request dispatches
Driver-policy retries
Service / gateway retries
fetchNextPage calls for paged queries
Client admission rejections
~~~

Never treat **`application retry count = 0`** as proof the system did not retry; other layers may have retried.

## 8. Asynchronous Error Handling Without Blocking Threads

With **`CompletionStage`**, attach success/failure handlers via callbacks. Never call **`join/get`** on HTTP or driver I/O threads.

~~~java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class AsyncReadService {
    private final CqlSession session;
    private final PreparedStatement query;

    public AsyncReadService(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT happened_at, event_id, event_type " +
            "FROM async_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");
    }

    public CompletionStage<AsyncResultSet> readFirstPage(
            UUID tenantId, LocalDate day) {

        BoundStatement request = query.bind(tenantId, day, 100)
            .setPageSize(32)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        return session.executeAsync(request)
            .whenComplete((page, error) -> {
                if (error != null) {
                    Throwable root = unwrap(error);
                    System.err.println(
                        "Read failed: " +
                        root.getClass().getSimpleName());
                }
            });
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException &&
                error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

**Notes:**

1. **`whenComplete`** observes the outcome; it **does not fix errors** or turn failures into successes.
2. Never log raw **`BoundStatement`**s, customer IDs, tokens, or payloads. Log operation, query shape, CL, retry count, and exception class.
3. This snippet returns the first page, **not all pages**. If the API needs complete data, continue paging via **`hasMorePages/fetchNextPage`** under a full-chain time budget.
4. Reuse `CqlSession` and `PreparedStatement` across the application lifecycle.
5. The sample omits TLS/auth to focus on async flow; production must use proper authentication and encryption rather than weakening security to avoid timeouts.
6. Check for **driver-side timeouts, network, auth/TLS, and overload** separately from CQL server errors; never catch `Throwable` and blindly retry everything.

## 9. Set a Retry Budget Before Writing a Retry Loop

A safe retry policy requires **four simultaneous conditions**:

1. **Idempotent request** (or explicit unknown-outcome / business-idempotency handling).
2. **Plausibly transient failure** based on exception class and telemetry.
3. **Remaining deadline** after accounting for wait time and backoff.
4. **Available system capacity:** admission / circuit breakers are not signaling overload, and the retry budget is not spent.

Mental model:

~~~text
if !idempotent:
    do_not_retry_automatically

if overloaded || circuit_open:
    shed_load_or_fail_fast

if attempts >= max_attempts:
    fail

if remaining_deadline <= next_delay + minimal_request_budget:
    fail

retry_with_bounded_backoff_and_jitter()
~~~

**Not every `ReadTimeout` is worth retrying.** If all replicas lag from I/O saturation or one hot partition, re-sending usually adds more load. A sound retry policy also includes a **circuit/budget switch that curtails retries as error rates or load rise**, validated in staging under realistic traffic.

### 9.1. Exponential Backoff and Jitter

Example up to three attempts including the initial try:

| Attempt | Before sending | Hypothetical delay |
|---|---|---|
| 1 | Initial attempt | 0 |
| 2 | After transient error | random 0–100 ms |
| 3 | After next transient error | random 0–200 ms |

This uses **full jitter** over an exponentially growing cap, not a mandatory millisecond prescription. When Cassandra is saturated, you may need **zero retries** or longer delays per system health. Count per-attempt timeouts and queue time so the total never exceeds the caller deadline.

**Never call `Thread.sleep` inside callbacks** on driver or reactive event loops to wait out backoff. Use **`ScheduledExecutorService`**, the framework's scheduler, or a compatible non-blocking delay.

## 10. Integrated Example: Admission, Deadline, and Bounded Retries

The class below demonstrates coordinating all three mechanisms for an **idempotent `SELECT`**:

- A **`Semaphore`** caps active **logical read operations**, including backoff wait time.
- A **monotonic deadline** governs the entire attempt sequence.
- Retries up to **3 attempts**, strictly in this sample for **`ReadTimeoutException`**, with full jitter; **`Overloaded`/`Unavailable`/`ReadFailure` are not retried automatically**.

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;

public final class BoundedAsyncReadGateway implements AutoCloseable {
    private final CqlSession session;
    private final Semaphore active;
    private final ScheduledExecutorService scheduler;
    private final int maxAttempts;

    public BoundedAsyncReadGateway(
            CqlSession session, int maxActive, int maxAttempts) {
        if (maxActive <= 0 || maxAttempts <= 0) {
            throw new IllegalArgumentException("positive limits required");
        }
        this.session = session;
        this.active = new Semaphore(maxActive);
        this.maxAttempts = maxAttempts;
        this.scheduler = new ScheduledThreadPoolExecutor(1);
    }

    public CompletionStage<AsyncResultSet> executeIdempotentRead(
            BoundStatement read, Duration budget) {

        if (budget.isNegative() || budget.isZero()) {
            return failed(new IllegalArgumentException(
                "budget must be positive"));
        }
        if (!active.tryAcquire()) {
            return failed(new RejectedExecutionException(
                "logical read admission limit reached"));
        }

        CompletableFuture<AsyncResultSet> outcome =
            new CompletableFuture<>();
        long startedAtNanos = System.nanoTime();

        // Hold permit until the entire attempt sequence completes.
        attempt(read, startedAtNanos, budget.toNanos(),
                1, outcome);

        // Return dependent stage so callers don't hold the internal
        // CompletableFuture and complete it arbitrarily.
        return outcome.whenComplete((page, error) ->
            active.release());
    }

    private void attempt(
            BoundStatement read,
            long startedAtNanos,
            long budgetNanos,
            int attemptNo,
            CompletableFuture<AsyncResultSet> outcome) {

        if (outcome.isDone()) {
            return;
        }
        long elapsed = System.nanoTime() - startedAtNanos;
        if (elapsed >= budgetNanos) {
            outcome.completeExceptionally(
                new TimeoutException("logical deadline exceeded"));
            return;
        }

        CompletionStage<AsyncResultSet> request;
        try {
            request = session.executeAsync(read);
        } catch (RuntimeException error) {
            outcome.completeExceptionally(error);
            return;
        }

        request.whenComplete((page, error) -> {
            long nowElapsed = System.nanoTime() - startedAtNanos;
            if (error == null) {
                if (nowElapsed >= budgetNanos) {
                    outcome.completeExceptionally(
                        new TimeoutException("logical deadline exceeded"));
                } else {
                    outcome.complete(page);
                }
                return;
            }

            Throwable reason = unwrap(error);
            boolean retryable =
                reason instanceof ReadTimeoutException;

            if (!retryable || attemptNo >= maxAttempts) {
                outcome.completeExceptionally(reason);
                return;
            }

            long capMillis = Math.min(
                1000L, 100L << Math.min(attemptNo - 1, 10));
            long delayMillis =
                ThreadLocalRandom.current().nextLong(capMillis + 1);

            long remainingNanos =
                budgetNanos - nowElapsed;
            long requiredNanos =
                TimeUnit.MILLISECONDS.toNanos(delayMillis + 50);

            if (remainingNanos <= requiredNanos) {
                outcome.completeExceptionally(reason);
                return;
            }

            try {
                scheduler.schedule(
                    () -> attempt(read, startedAtNanos,
                            budgetNanos, attemptNo + 1, outcome),
                    delayMillis, TimeUnit.MILLISECONDS);
            } catch (RejectedExecutionException stopped) {
                outcome.completeExceptionally(stopped);
            }
        });
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException &&
                error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    private static <T> CompletionStage<T> failed(
            Throwable error) {
        CompletableFuture<T> result = new CompletableFuture<>();
        result.completeExceptionally(error);
        return result;
    }

    @Override
    public void close() {
        scheduler.shutdown();
    }
}
~~~

Using it with a prepared `SELECT`:

~~~java
BoundStatement read = preparedRead.bind(tenantId, day, 100)
    .setPageSize(32)
    .setIdempotent(true)
    .setConsistencyLevel(
        com.datastax.oss.driver.api.core
            .DefaultConsistencyLevel.LOCAL_QUORUM);

BoundedAsyncReadGateway gateway =
    new BoundedAsyncReadGateway(session, 40, 3);

CompletionStage<AsyncResultSet> firstPage =
    gateway.executeIdempotentRead(
        read, Duration.ofMillis(1800));

// Keep gateway/session alive for the service lifecycle;
// close only after stopping requests and draining work.
~~~

**Scope limits of this example — not a complete production retry framework:**

1. Use only for **verified idempotent `SELECT`s**. The class does not parse CQL to prove idempotence; the caller owns that invariant.
2. **Does not retry `Overloaded`, `Unavailable`, or `ReadFailure`** in this sample. Under fleet-wide load controls, real policies may **avoid retrying `ReadTimeout` as well**.
3. **This deadline is a cooperative check** before/after attempts and before scheduling retries—not a hard kill of in-flight Cassandra work. Configure driver timeouts appropriately so single attempts never hang forever.
4. **`Semaphore`** holds the permit until the result stage finishes, including backoff waits. When servers slow down, this prevents spinning up endless parallel retry chains.
5. **`ScheduledThreadPoolExecutor`** here has a single scheduler thread. In real systems, bound timer/job counts, stop admitting before shutdown, and monitor scheduler queues or use a framework-managed scheduler.
6. **The driver may already retry internally.** Before adding Java-layer retries, inspect the effective driver retry policy, request budget, and actual attempt counts to avoid layered retry multiplication.
7. This sample fetches only the **first page** of a paged `SELECT`. End-to-end **multi-page** deadlines must be managed separately rather than treating first-page completion as meeting the whole job deadline.
8. **TLS/auth** are omitted in the caller snippet; production must initialize `CqlSession` securely.
9. Modifying or cancelling the caller stage does not guarantee Cassandra halts in-flight work. Release resources per lifecycle and monitor outstanding operations in production.
10. `maxActive` is **per instance**, not a cluster-wide quota. Across dozens of instances, perform fleet-wide capacity budgeting.

## 11. Timeouts and Backpressure in Multi-Page Async Reads

In Java Driver 4.x, **`executeAsync(statement)`** returns **`CompletionStage<AsyncResultSet>`** for the first page; each **`AsyncResultSet`** provides:

- **`currentPage()`:** rows in the current page.
- **`hasMorePages()`:** whether more pages remain to fetch.
- **`fetchNextPage()`:** asynchronously fetches the next page as a stage.

An endpoint with a 2-second deadline reading 20 pages **cannot rely on the first page's timeout to guarantee the entire result finishes within 2 seconds**.

### 11.1. Read Flow Maintaining One Shared Deadline

~~~mermaid
flowchart TD
    A["Receive logical request, record startNanos"] --> B["Admit into bounded pipeline count"]
    B --> C["executeAsync: first page"]
    C --> D["Process currentPage / downstream"]
    D --> E{"Deadline left?"}
    E -->|No| X["Finish INCOMPLETE; stop fetching"]
    E -->|Yes| F{"hasMorePages?"}
    F -->|No| G["COMPLETE + release permit"]
    F -->|Yes| H["fetchNextPage"]
    H --> D
~~~

If downstream processes pages slowly, **wait for it to finish before calling `fetchNextPage`**. Prefetching many pages into an unbounded list defeats load control.

### 11.2. Example Counting Rows With a Full-Chain Deadline

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeoutException;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class DeadlinePagedCount {
    public static CompletionStage<Long> count(
            CqlSession session, BoundStatement statement,
            Duration budget) {

        long started = System.nanoTime();
        return session.executeAsync(statement)
            .thenCompose(first ->
                consume(first, 0L, started, budget.toNanos()));
    }

    private static CompletionStage<Long> consume(
            AsyncResultSet page, long count,
            long started, long budgetNanos) {

        long nextCount = count;
        for (Row ignored : page.currentPage()) {
            nextCount++;
        }

        if (System.nanoTime() - started >= budgetNanos) {
            CompletableFuture<Long> failed =
                new CompletableFuture<>();
            failed.completeExceptionally(
                new TimeoutException("paging deadline exceeded"));
            return failed;
        }

        if (!page.hasMorePages()) {
            return CompletableFuture.completedFuture(nextCount);
        }

        final long snapshotCount = nextCount;
        return page.fetchNextPage()
            .thenCompose(nextPage ->
                consume(nextPage, snapshotCount,
                        started, budgetNanos));
    }
}
~~~

This keeps the counter **O(1)** without buffering `Row`s. Still:

1. **There is no forced abort** of an in-flight `fetchNextPage` if the deadline expires mid-fetch; code checks only once that stage finishes.
2. Enforce real bounds via **driver request timeouts** and framework/API cancellation policies.
3. If `currentPage` is large or per-row work is heavy, check deadlines/cancellation inside processing or offload to a bounded executor.
4. Counting every row still consumes I/O; avoid using this as a routine analytics query on large partitions.
5. The sample uses async recursion via **`thenCompose`**. For very high page counts, prefer a loop/trampoline or reactive pipeline to control depth and memory.
6. This deadline governs **the entire multi-page query**, unlike the **first-page** retry attempts in section 10. In production, share **one caller deadline** across layers instead of minting fresh deadlines per layer.

### 11.3. What If Page N Fails?

Suppose a pipeline processed pages 1–5 and page 6 fails:

- The full-pipeline future must report **failed/incomplete**, not complete.
- Earlier rows may have caused side effects at the sink.
- Retrying the **entire query from the start** can resend already-processed rows.
- Paging state does not preserve a consistent snapshot across concurrent INSERT/DELETE/TTL mutations.
- ETL jobs need **durable checkpoints + idempotent sinks/reconciliation**, not just an in-RAM cursor.

If an API intentionally returns partial results, the contract must explicitly expose **`partial=true`**, verified coverage bounds, and resumption mechanics—never return truncated lists labeled as complete success.

## 12. Coordinating Reactive Demand With Asynchronous Sinks

Java Driver 4.x exposes a reactive API per version/dependency. In Reactor apps, wrap the driver's publisher with **`Flux`** to process under demand.

### 12.1. Reactor Example With an Asynchronous Downstream

Assume **`sink.persist(UUID)`** returns **`CompletionStage<Void>`** once durable per the sink's contract:

~~~java
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveEventPipeline {
    interface EventSink {
        CompletionStage<Void> persist(UUID eventId);
    }

    public static Mono<Void> consume(
            CqlSession session,
            BoundStatement statement,
            EventSink sink) {

        return Flux.from(session.executeReactive(statement))
            .limitRate(16)
            .concatMap(
                row -> Mono.fromCompletionStage(
                    sink.persist(row.getUuid("event_id"))),
                1)
            .then()
            .timeout(Duration.ofSeconds(2));
    }
}
~~~

**Characteristics and boundaries:**

- **`executeReactive`** returns a publisher per Driver 4.x reactive API. Requires compatible Reactor, Reactive Streams, and driver versions.
- **`limitRate(16)`** shapes demand in a bounded window; it does not imply one `request(1)` equals one network round-trip.
- **`concatMap(..., 1)`** preserves sink order with **prefetch = 1** when supported by your Reactor overload.
- **`then()`** completes once the source finishes and all chained sink writes complete; sink errors propagate through the pipeline.
- **`Mono.timeout(2 seconds)`** placed after **`then()`** bounds the entire pipeline converted to a completion `Mono`, unlike placing `timeout` on a `Flux` where it only bounds gaps between items.
- Java timeouts/cancellations never undo requests or side effects already triggered on Cassandra or the sink.
- Long-running ETL jobs need job-appropriate timeouts and checkpoints; 2 seconds is illustrative only.
- Verify exact **`concatMap`** and **`executeReactive`** overloads against your dependency versions before production use.
- Never log real UUIDs or payloads if sensitive.

### 12.2. Never Retry an Entire `Flux` When the Sink Is Non-Idempotent

~~~java
// Unsafe if sink has side effects without deduplication.
Flux.from(session.executeReactive(statement))
    .concatMap(row -> Mono.fromCompletionStage(
        sink.persist(row.getUuid("event_id"))))
    .retry(5);
~~~

**`retry(5)`** re-subscribes to the source from the beginning, not just the failing row. Rows that already sent emails, incremented counters, or charged accounts will be re-processed. Retry the full pipeline only when **both source and sink are replay-safe**, backed by checkpoints and verified retry/deadline bounds.

Adding **`retryWhen(backoff)`** does not solve idempotency or duplicate downstream side effects either.

### 12.3. Demand Does Not Replace Admission Control

Each reactive subscription may honor `request(n)`, yet **1,000 concurrent subscriptions** can still overwhelm the system. Simultaneously bound:

- **Active subscriptions / logical queries**.
- **Pipeline demand / prefetch / buffers**.
- **`flatMap` concurrency** and sink worker thread pools.
- **Overall deadlines**, retry budgets, and cancellation.
- **Per-tenant quotas** if one tenant can consume most capacity.

**Reactive does not mean OOM-proof.** An unbounded `collectList` or unbounded buffer still retains the entire dataset.

## 13. Admission, Rate Limiting, Load Shedding, and Circuit Breakers

### 13.1. Each Mechanism Addresses a Different Pressure

| Mechanism | Controls | Example |
|---|---|---|
| **Concurrency limit** | Active logical operations | Semaphore of 40 reads/instance |
| **Rate limit** | Requests / work units over time | Per-tenant, per-API ingest rate cap |
| **Queue bound** | Requests allowed to wait for a permit | Max 100 queued, then reject |
| **Retry budget** | Fraction of traffic allowed for retries | Retries cannot starve fresh requests |
| **Circuit breaker** | Temporarily sheds calls on failing paths | Opens during sustained overload |
| **Cost-based admission** | Distinguishes cheap reads from heavy scans | Multi-partition queries spend more tokens than point lookups |

**Concurrency** and **rate** do not replace one another. Slow requests hold permits long even at low QPS; ultra-fast requests at high QPS can still saturate disks/networks. Combine them to fit the workload.

### 13.2. Responding to Callers When Out of Capacity

When Java rejects **pre-dispatch** due to exhausted permits, that is a **client admission rejection**, not `OverloadedException` from Cassandra.

For HTTP APIs:

- **`429 Too Many Requests`** fits when a caller or tenant exceeds quota.
- **`503 Service Unavailable`** fits when the service or dependencies lack temporary capacity.
- **`Retry-After`** should be sent only when a meaningful wait window can be estimated; avoid fixed promises while the cluster remains overloaded.
- Curb automatic gateway/proxy retries unless bounded within an end-to-end budget.
- Emit non-PII reason codes and correlation IDs to distinguish client load shedding from server overload.

Exact HTTP status codes follow your API contract, not a CQL error mapping. Controlled early rejections protect p99 for admitted requests.

### 13.3. Per-Tenant Fairness

If one tenant generates 80% of traffic, a naive global semaphore starves every other tenant. Consider:

1. Quotas per tenant or endpoint group.
2. Prioritizing critical business calls over bulk jobs.
3. Separate rate limits for hot partitions and heavy query classes.
4. Different deadlines for interactive APIs vs. batch jobs.
5. Metrics grouped by query shape/tenant tier without exposing sensitive IDs.

Also evict stale per-tenant queues/counters so large tenant counts do not leak memory.

## 14. Why Must Concurrency Be Measured Alongside Latency?

A useful operational intuition is **Little's Law** in relatively steady state:

~~~text
L ≈ λ × W

L : average requests inside the system
λ : request throughput (requests/s)
W : average residence time per request (seconds)
~~~

Example at **1,000 logical requests/s**:

| Mean residence time W | Estimated in-flight L |
|---|---:|
| 0.1 s | 100 |
| 0.5 s | 500 |
| 2.0 s | 2,000 |

When Cassandra slows from 100 ms to 2 s while the app keeps sending 1,000 req/s, active requests in the system surge roughly **20x**. If every timeout also triggers retries, load climbs even higher.

This is a steady-state average relation, **not an exact forecast** during saturation, deadlines, bursts, or drops. It explains why **raising timeouts without bounding in-flight work** triggers memory pressure and p99 collapse.

### 14.1. Testing Along Two Axes

In controlled experiments, vary:

- **Concurrency:** 20, 40, 80 logical operations/instance.
- **Request rate:** 200, 500, 1,000 requests/s fleet-wide.
- Keep **row size, page size, CL, and partition distribution** measured and consistent.
- **Retry budget:** 0 or a small explicit allowance.

Measure **successful throughput**, not just offered traffic. If raising concurrency fails to raise throughput while p99 and `Overloaded` rise, the system is past saturation.

## 15. Retry Policies Should Depend on Error Class and Load

| Scenario | Idempotent read | Unproven-idempotent write | Reduce load pressure? |
|---|---|---|---|
| `ReadTimeout` | Very limited retry if budget remains and server is healthy | N/A | Possibly |
| `ReadFailure` | Inspect logs/tables/replicas; retry depends on cause | N/A | Depends on cause |
| `WriteTimeout` | N/A | **Never blind-retry**; reconcile state | Possibly |
| `WriteFailure` | N/A | Assess partial/unknown write | Possibly |
| `Overloaded` | Do not retry immediately; shed load | Do not retry immediately | **Yes** |
| `Unavailable` | Wait for replica/topology recovery; retry only if state changed | Check data/CL | Possibly |
| Driver timeout | Inspect network/queues/driver | Ambiguous outcome | Possibly |
| Auth / Codec / CQL error | Never retry; fix config/code | Never retry; fix config/code | Retrying won't help |

Choices must align with the **driver's actual retry policy and business contract**; there is no universal "retry 3 times on every ReadTimeout" rule.

### 15.1. What to Avoid

- Retrying immediately without backoff inside callbacks, creating bursts.
- Calling `Thread.sleep` on driver or reactive event-loop threads.
- Retrying both HTTP POSTs and driver requests without a shared idempotency key.
- Minting a fresh UUID on every retry when creating events or orders.
- Dropping consistency level on timeout when the API promised stronger consistency.
- Switching coordinators hoping to cure a hot partition: the same replica set still handles the token.
- Retrying when a circuit breaker is open or the caller's deadline expired.
- Ignoring LWT **`[applied]`** or treating every exception as "write didn't happen."
- Raising `maxAttempts` before identifying the source of `Overloaded`/GC/disk saturation.

### 15.2. Retries With Downstream Side Effects

In a **read Cassandra → publish to broker → update external system** pipeline, retrying after page N fails can resend earlier pages. Design:

1. A stable **`event_id`** per event.
2. Idempotent/deduplicating sinks.
3. Checkpoints advancing only after the sink confirms durable commit per contract.
4. Reconciliation to catch missing events.
5. Never treating paging state as an eternal checkpoint across schema/version changes.

**At-least-once + deduplication** is usually far more realistic than unproven end-to-end exactly-once promises.

## 16. Client Timeouts/Cancellations Are Not Rollbacks

| Event | Java side | Cassandra side |
|---|---|---|
| Caller cancels HTTP request | Can stop fetching next pages | Already-sent request may keep running |
| `CompletableFuture` timeout/cancel | Stage finishes errored/cancelled | Does not prove coordinator halted mutation |
| Server `WriteTimeout` | Client lacked enough ACKs | Some replicas may already have written |
| Reactive subscription cancel | Subscriber stops receiving items | Does not undo already-executed side effects |
| App retries after LWT timeout | May receive `[applied]=false` | First attempt may have succeeded |

**Cancellation must be cooperative**:

- Before `fetchNextPage`, verify the caller still wants results and deadline remains.
- Stop producers/sinks without reporting the database rolled back.
- Release permits cleanly per lifecycle; avoid releasing too early while server work remains active.
- For writes/LWTs, verify state via business keys.
- Align driver timeouts with caller deadlines so requests don't stay orphaned too long.

## 17. Observability and Diagnostics From Java to Cassandra

### 17.1. Metrics at Every Layer

| Layer | Signals | Question |
|---|---|---|
| **HTTP / gRPC** | Arrival rate, p95/p99, deadline exceeded, 429/503 | What does the caller experience? |
| **Admission** | Active permits, rejections, queue depth/wait, tenant quotas | Is too much work admitted? |
| **Driver** | In-flight, connection pool, timeouts, retry counts, coordinator/DC | Are retries amplifying load? |
| **Async paging** | First-page/full-result latency, page count, failing page | Which page is slow or failing? |
| **Reactive** | Demand, consumed rows, sink latency, buffers | Is downstream keeping up? |
| **Cassandra** | Read/WriteFailure, timeouts, overload, unavailable | Which replica/coordinator errors occur? |
| **Storage / JVM** | Disk latency/free, heap, native RSS, GC, compaction backlog | Where is the bottleneck? |
| **Topology** | UP/DOWN, RF/DC/rack, repair/streaming | Are enough replicas up for CL? |

**Never count only application retries.** Driver, proxy, and gateway layers can each retry independently. Distinguish **logical requests** from **physical attempts** to see true load.

### 17.2. Read-Only Diagnostic Commands

On an authorized cluster using version-compatible syntax:

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool tablestats async_lab.events_by_tenant_day
nodetool tablehistograms async_lab events_by_tenant_day
~~~

Combine server logs on **coordinators and replicas** with JMX/Prometheus metrics, disk I/O, GC, and client traffic. A node showing **`UN` (Up/Normal)** can still be overloaded or too slow for `LOCAL_QUORUM`.

Never run **repair, cleanup, `upgradesstables`**, or topology changes reflexively to "cure timeouts." Those operations generate heavy I/O and belong in deliberate runbooks. Repair converges replicas; it never undoes a mistaken business `DELETE`.

### 17.3. Redacted Structured Logging

~~~json
{
  "event": "cassandra_async_operation_failed",
  "operation": "events_by_tenant_day.read",
  "profile": "limited-read",
  "consistency": "LOCAL_QUORUM",
  "failure_class": "ReadTimeoutException",
  "logical_attempt": 2,
  "page_index": 3,
  "deadline_remaining_ms": 180,
  "active_operations": 40,
  "admission_rejected": false,
  "request_id": "req-lab-72"
}
~~~

This is an **application-defined log format**, not default driver output. Never log passwords, raw `BoundStatement`s, real customer IDs, paging states, or payloads. Query shape, operation, CL, latency, and exception class normally suffice to start investigating.

## 18. Two Real-World Coordination Scenarios

### 18.1. Retry Storm During Bulk Ingestion

**Hypothetical scenario:** 15 Java instances, each allowing 200 in-flight write requests. A bulk job starts while Cassandra runs compaction and disk utilization climbs. Driver and app both have retry policies, and the API gateway retries some errors too.

| Observation | Consequence |
|---|---|
| 15 instances × 200 requests | Up to 3,000 in-flight requests if all quotas fill |
| Cassandra reports `Overloaded` | Many requests cannot finish in time |
| Retries across multiple layers | Physical attempts surge unexpectedly |
| Disk / compaction backlog grows | Extra attempts slow storage further |
| Caller deadline expires | Server-sent requests may still keep running |

**Remediation:** Never blindly raise timeouts or `maxAttempts`. Throttle bulk ingest, cap fresh admissions, eliminate layered retries, apply jittered backoff, and shed load. Inspect disk/GC/compaction, hot partitions, and batch/mutation sizes; ramp traffic back up only behind p99/error-rate gates. Never estimate attempts simply by multiplying retry limits—measure actual **physical attempts** at each layer.

### 18.2. Reactive ETL With a Slow Sink

A job reads 500,000 rows while its sink handles only 100 rows/s, yet the pipeline uses **high `flatMap` concurrency**, unbounded buffers, and retries the entire `Flux` when one page times out.

- Buffers grow, causing heap/GC pressure.
- The driver keeps fetching pages ahead of downstream completion.
- Full-source retries re-send already-processed rows.
- Callers time out while the pipeline keeps burning resources.

**Redesign:** cap active subscriptions, demand/prefetch, and concurrency; use `concatMap` or bounded `flatMap` sized to sink throughput; add checkpoints/idempotency; halt further fetches when deadlines expire; measure **successfully processed** rows/s and full-result latency instead of first-page latency alone.

## 19. Runbook for Timeouts and Overload

~~~mermaid
flowchart TD
    A["Timeout/ReadFailure/Overloaded spikes"] --> B["Classify errors and blast radius"]
    B --> C{"Data corruption, quorum loss, or severe security error?"}
    C -->|Yes| S["STOP; protect data and run incident response"]
    C -->|No| D{"Queues/in-flight or overload rising?"}
    D -->|Yes| E["Shed load, cap concurrency, cut retries"]
    D -->|No| F["Check timeout layers, RF/CL, network"]
    E --> G["Check hot partitions, disk/GC, compaction"]
    F --> G
    G --> H{"SLOs and correctness restored?"}
    H -->|No| I["Keep diagnosing, hold tight caps"]
    H -->|Yes| J["Ramp load gradually with monitoring"]
~~~

Eight-step procedure:

1. **Pinpoint start time and scope** and halt changes that add load.
2. **Classify exceptions** across server, driver, admission, and downstream; identify which deadline expired.
3. **Check topology and CL:** RF, DC, healthy replicas, and partition routing.
4. **Check query / data model:** hot keys, large partitions, tombstones, page sizes, `LIMIT`, batches, and collections.
5. **Check resources:** GC, disk, native RSS, compaction, repair, streaming, and pending tasks.
6. **Measure load amplification:** retries at driver/app/gateway, instance counts, active subscriptions, and queues.
7. **Relieve pressure safely:** load shedding, quotas, jittered backoff, deadlines; never weaken promised consistency.
8. **Verify recovery:** p95/p99, successful throughput, errors by class, queues, and data correctness. Ramp load slowly.

If corruption or data loss is detected, cutting retries alone is not enough—preserve evidence and evaluate restore/repair based on root cause.

## 20. Staging Test Plan

### 20.1. Minimum Test Suite

1. **Normal baseline:** p50/p95/p99, throughput, first-page/full-result latency, GC, and disk.
2. **One slow replica:** simulated in lab; compare `LOCAL_ONE` vs. `LOCAL_QUORUM` per contract.
3. **One unavailable replica:** distinguish `Unavailable`, `ReadTimeout`, and Java timeouts.
4. **Bounded overload:** ramp rate/concurrency stepwise; locate the `Overloaded` knee.
5. **Retry budget:** measure physical attempts across all layers, backoff, and jitter.
6. **Caller timeout / cancel:** pipeline stops fetching new pages; zero leaked permits.
7. **Page N failure:** outcome must be `INCOMPLETE`, never silently complete.
8. **Slow sink:** demand, buffers, and concurrency remain bounded.
9. **Idempotent vs. non-idempotent writes:** timeouts with event IDs, counters, list appends, and LWTs.
10. **Soak test:** long enough to observe compaction, repair, and GC impacts.

Run fault injection and network shaping only in **isolated, authorized environments**—never deliberately disrupt production.

### 20.2. Pass / Fail Criteria

- Zero data corruption or business-invariant violations.
- Deadlines honored within clear bounds; partial results never reported complete.
- Retries stay within budget; no retry storms under `Overloaded`.
- In-flight counts, queues, and reactive buffers stay bounded and observable.
- Successful throughput/latency meets SLOs under representative load.
- Slow downstream never triggers unbounded Cassandra fetches.
- Once faults clear, the system recovers without mass restarts.
- Metrics/logs cleanly separate error layers without leaking sensitive data.

Timeout and concurrency thresholds must match your SLOs, payloads, RF/DC, and capacity—no single "standard" value fits all clusters.

## 21. Scenario Exercises

### Exercise 1 — Deadlines and Retries

HTTP deadline is **2 seconds**. A request waits **300 ms** in admission, the first Cassandra attempt runs **1.2 seconds** and times out, planned backoff is **250 ms**, and the next attempt has a **1-second** timeout.

**Question:** Should you retry?  
**Suggested answer:** No. 1.5 seconds are already gone, leaving only 0.25 seconds after backoff for both the retry attempt and response handling. Insufficient budget.

### Exercise 2 — Counter Timed Out

An increment **`counter +1`** hits `WriteTimeout`; a developer sets **`setIdempotent(true)`** and retries.

**Question:** Why is this dangerous?  
**Suggested answer:** Telling the driver it's idempotent does not make counters idempotent; the first attempt may have applied, so retrying double-increments.

### Exercise 3 — Overloaded and App Scaling

10 Java instances each allow 100 in-flight requests; when the server reports `Overloaded`, the app retries immediately three times.

**Question:** What should take priority?  
**Suggested answer:** Cut ingress rate, cap fleet-wide in-flight/retries, apply jittered backoff, shed load, and investigate disk/GC/hot partitions/compaction.

### Exercise 4 — `thenApply` vs. `thenCompose`

~~~java
CompletionStage<Void> sink(Row row);

CompletionStage<CompletionStage<Void>> nested =
    firstPage.thenApply(page -> sink(page.currentPage()
        .iterator().next()));
~~~

**Question:** What is wrong here?  
**Suggested answer:** `sink` returns a `CompletionStage`, so `thenApply` produces a nested stage; use `thenCompose`, check for empty pages, and process all needed rows rather than just the first.

### Exercise 5 — Is Non-Blocking Enough for Backpressure?

A service receives 10,000 HTTP requests; each calls **`executeAsync`** and keeps the future without calling `sleep` or `join`.

**Question:** Can it still overload?  
**Suggested answer:** Yes. Async does not cap logical operations; you still need admission control, bounded queues, rate limits, retry budgets, and paging limits.

### Exercise 6 — HTTP Cancellation and Mutations

A client hits a driver timeout after some replicas already received an `INSERT`. The caller cancels the HTTP request.

**Question:** Can you assert the DB did not change?  
**Suggested answer:** No. Cancel/timeout never rolls back; reconcile by primary key/idempotency key and keep keys stable on safe retries.

### Exercise 7 — Retrying the Whole Reactive Source

Rows from pages 1–5 already persisted; page 6 hits `ReadTimeout` and the pipeline runs `retryWhen` on the entire `Flux`.

**Question:** What is the risk?  
**Suggested answer:** Re-subscribing can re-process earlier rows as duplicates. Use checkpoints, idempotent sinks, bounded retries, incomplete states, and deadlines.

### Exercise 8 — Estimating Average In-Flight

A system handles **400 requests/s** while mean latency rises from **0.1 s** to **1 s**.

**Question:** By Little's Law, how does `L` change?  
**Suggested answer:** From roughly **40 to 400** requests—a 10x increase under steady-state assumptions.

### Exercise 9 — Hot Partitions and Retries

A table uses **`PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)`**; one tenant sends 95% of traffic to one daily partition. The team raises timeouts, page sizes, and retry counts.

**Question:** Why doesn't this fix the root cause?  
**Suggested answer:** That partition's replica set remains overloaded; fix bucketing/sharding for the access pattern, rate-limit mutations, and bound concurrency.

### Exercise 10 — Reactive Buffering

A source emits 1,000 rows/s while the sink processes 20 rows/s, and the `Flux` uses an unbounded buffer.

**Question:** Does reactive prevent OOM?  
**Suggested answer:** No. You must bound demand/prefetch, buffers, and concurrent subscriptions, and implement load shedding.

## 22. Production Readiness Checklist

- [ ] **End-to-end deadlines** cover queueing, retries, paging, and downstream steps.
- [ ] Caller, driver, server, page, and sink timeouts are clearly separated.
- [ ] Durations measured with monotonic clocks; timestamps logged in UTC.
- [ ] Errors classified across `ReadTimeout`, `ReadFailure`, `WriteTimeout`, `WriteFailure`, `Overloaded`, `Unavailable`, and network/auth/codec issues.
- [ ] Retries enabled only when **idempotency** is proven; unknown write outcomes have reconciliation.
- [ ] Never retry `Overloaded` immediately; use jittered backoff, retry budgets, and admission/circuit breakers.
- [ ] Zero uncontrolled layered retries across driver, app, and gateway.
- [ ] Never weaken consistency levels below business commitments.
- [ ] `CompletionStage`/`thenCompose` never block driver callbacks with `sleep`/`join`/`get`.
- [ ] Bounded in-flight counts, bounded queues, rate limits, and load shedding in place.
- [ ] Reactive demand maintained end-to-end; zero unbounded buffers or `collectList`.
- [ ] Paging halts on deadline expiry and never fetches ahead of slow sinks.
- [ ] Page N failures report incomplete rather than full; sinks use idempotency/checkpoints when side-effecting.
- [ ] Cancellation cleans up resources per lifecycle without treating it as a server rollback.
- [ ] `CqlSession` reused and closed only after draining.
- [ ] Queries bind full partition keys; partition sizes, batches, and collections stay bounded.
- [ ] Monitors RF/DC/CL, replicas, hot partitions, tombstones, compaction, repair, and disk/GC.
- [ ] Metrics track first-page/full-result latency, physical attempts, permits/rejections, and sink latency.
- [ ] Failure modes tested on representative staging rather than production.
- [ ] Credentials, raw bind values, and customer data never logged.

## 23. Summary

**Timeouts** bound how long a request remains useful, **retries** decide whether to re-attempt after failure, and **backpressure/admission** stop Java and Cassandra from accepting more work than capacity allows. In asynchronous or reactive apps, simply avoiding blocked threads **is not enough**: dispatching requests and fetching pages without bounds still overwhelms the system.

Resilient designs enforce **one caller-owned deadline**, retry only safe operations within budget, **shed load on `Overloaded`**, bound logical operations and reactive demand, and reconcile uncertain state after write timeouts. In Cassandra, pair these controls with **proper partition keys, query-driven tables, replication/consistency levels, bounded partition sizes, compaction, and repair**. The goal is **correct data, SLO-compliant latency, and graceful recovery under load**—not merely making exception counts look smaller.
