# Identifying Pool Exhaustion, Connection Leaks, and Long-Holding Queries

A connection pool helps an R2DBC application reuse database connections instead of opening a new physical connection for each operation. The pool is bounded: when every connection is in use, new requests must wait for a connection to be returned or wait until the acquire timeout expires.

Pool exhaustion typically shows up as slow requests, growing acquire queues, and connection acquisition timeouts. However, **pool exhaustion is a symptom, not the root cause**. It can stem from slow queries, long transactions, slow reactive stream consumption, excessive concurrency, an overloaded database, or connections held without being released.

To diagnose accurately, measure connection acquisition time, SQL execution time, and total connection hold time. Those three intervals help separate an undersized pool from slow queries or connection leaks.

## 1. Lifecycle of a Connection in R2DBC

A data operation generally goes through the following steps:

1. The application subscribes to a publisher from a repository or `DatabaseClient`.
2. R2DBC infrastructure requests a connection from `ConnectionFactory` or the pool.
3. The pool issues an idle connection or creates a new one if within limits.
4. The driver sends SQL to the database and receives results.
5. Results are mapped into entities or data needed by the application.
6. When the operation completes, fails, or is cancelled, infrastructure releases the connection back to the pool.

For a pooled connection, calling `Connection.close()` usually means returning the connection to the pool for reuse; it does not necessarily close the physical database connection right away.

Repositories and `DatabaseClient` manage connection lifecycles for routine operations. Applications need extra care when calling `ConnectionFactory.create()` directly, opening transactions manually, or holding long-lived publishers.

### 1.1. How Long Is a Connection Held?

SQL execution time and connection hold time can differ. For instance, a `SELECT` may execute in 20 ms, yet the connection remains held much longer if:

- Results stream incrementally and the subscriber processes each item very slowly.
- The pipeline contains additional steps inside the same transaction.
- The application calls an external HTTP service before the transaction finishes.
- Manual code fails to close the connection after reading data.
- The publisher neither completes nor gets cancelled.

Therefore, fast query execution does not guarantee connections return promptly to the pool.

### 1.2. Key Terms to Distinguish

| Term | Meaning |
| --- | --- |
| Allocated connection | Connection created or managed by the pool, including both idle and borrowed connections |
| Acquired connection | Connection currently borrowed by the application to perform work |
| Idle connection | Connection sitting in the pool available to serve a new request |
| Pending acquire | Request waiting for the pool to issue a connection |
| Acquire time | Wait time from requesting a connection until receiving it |
| Hold time | Total duration a connection remains in the borrowed state |
| Query time | Time the database takes to execute or return query results, depending on measurement method |

These metrics may appear under different names depending on the R2DBC Pool version and metrics system. When analyzing, compare metric definitions rather than relying solely on display names.

## 2. Recognizing Pool Exhaustion

Common signs include:

- Database requests slow down even though incoming request counts have not risen noticeably.
- Connection acquire time increases and waiting queues appear.
- The pool frequently has zero idle connections.
- Acquired connections stay near `max-size` over extended periods.
- Timeouts while waiting for a connection or failures to obtain a new connection.
- API latency rises with load while throughput plateaus even as incoming requests keep rising.

A single snapshot showing `acquired = max-size` does not prove a leak. Under peak load, all connections may be legitimately busy. Observe trends over time, connection hold durations, and pending acquire counts.

### 2.1. Pool Metrics to Monitor

If your metrics system exposes R2DBC Pool data, monitor at least:

| Metric | What to Observe |
| --- | --- |
| `allocatedSize` | Total connections managed by the pool compared against the maximum limit |
| `acquiredSize` | Connections currently borrowed; steady growth or hovering near the limit signals investigation |
| `idleSize` | Idle connections; staying at 0 under load suggests pool pressure |
| `pendingAcquireSize` | Waiting requests; sustained growth indicates demand exceeds immediate connection supply |

Pool metrics can be exposed via Micrometer or the application's observability stack. Enabling them and exact metric names depend on Spring Boot, R2DBC Pool versions, and metrics configuration. Consult documentation for your active version.

Do not look solely at open connections on the database side. A pool can hold idle connections ready, so a high database session count does not mean every session is actively serving a request.

### 2.2. Reading a Sample Scenario

Suppose a pool has `max-size = 20` and metrics show:

| Metric | Observed Value |
| --- | ---: |
| Allocated | 20 |
| Acquired | 20 |
| Idle | 0 |
| Pending acquire | 35 |

This shows all 20 connections are borrowed and 35 requests are waiting. It does not yet tell whether the cause is slow queries, long transactions, or a leak. The next step is measuring connection hold duration and correlating with database activity.

If `acquired` drops quickly once traffic subsides and pending clears, the pool likely experienced a load spike. If `acquired` stays high after requests finish or does not drop for a long time, investigate connection release paths and open transactions.

## 3. Distinguishing Pool Exhaustion, Leaks, and Long Queries

These three issues produce similar surface symptoms yet require different remedies.

| Signal | Undersized Pool Under Load | Held / Leaked Connections | Long Queries or Transactions |
| --- | --- | --- | --- |
| Acquired | Rises with load and drops when load subsides | May climb steadily and fail to return to baseline | Rises while queries or transactions run |
| Pending acquire | Rises during peak hours | Can climb even under modest request traffic | Rises when multiple queries wait on connections |
| Query duration | Usually stable if the database responds well | May show no active query matching held connections | High, or database waiting on locks/I/O |
| Hold time | Matches normal processing duration | Abnormally long or never ends | Long matching the query, transaction, or stream |
| When load drops | Pool typically recovers | Acquired connections may remain stuck | Recovers once queries/transactions complete or time out |
| Remediation | Measure load, cap concurrency, review sizing | Fix acquire/release lifecycle and cancellation | Optimize SQL, locks, transactions, and result consumption |

Not every case separates cleanly from one chart alone. A slow query can exhaust a pool; in that case pool exhaustion is the consequence of long connection hold times.

## 4. Connection Leaks in R2DBC Applications

A connection leak occurs when an application borrows a connection and fails to return it to the pool after work finishes. As leaked connections accumulate, the pool runs out of connections for new requests.

### 4.1. Manual Acquisition Without Release

A frequent mistake is calling `ConnectionFactory.create()` directly and handling only the success path, forgetting cleanup on exception or cancellation.

Example illustrating safe manual management with Reactor `usingWhen`:

```java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

public Mono<Integer> selectOne(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> Mono.from(connection.createStatement("SELECT 1").execute())
                    .flatMap(result -> Mono.from(result.map(
                            (row, metadata) -> row.get(0, Integer.class)))),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` registers cleanup handlers when the publisher completes, errors, or is cancelled. In production code, add necessary imports and handle types according to your query.

For routine CRUD operations, prefer repositories or `DatabaseClient` so Spring manages acquiring and releasing connections. Drop down to low-level connection APIs only when direct control is genuinely needed.

### 4.2. Cleaning Up Only on Success

An error-prone pattern calls `close()` only in the normal completion branch. If the query throws an error, mapping fails, or the subscriber cancels, the cleanup branch may never execute.

When managing asynchronous resources manually, handle all three paths:

- Normal completion.
- Error termination.
- Cancellation before completion.

Reactor's `usingWhen` fits resources with asynchronous cleanup like R2DBC connections. Avoid using `doFinally` to invoke `close()` and discard the cleanup publisher, because `doFinally` does not wait for asynchronous cleanup to complete.

### 4.3. Storing Connections in Fields or Sharing Across Requests

Do not borrow a connection and store it in a singleton service field to reuse across requests. A borrowed connection belongs to a specific operation or transaction. Concurrent sharing causes transaction corruption, state races, and prevents timely return to the pool.

Inject `ConnectionFactory`, repositories, or `DatabaseClient`, and let each operation acquire a connection scoped to its publisher lifecycle.

### 4.4. Unconsumed or Non-Terminating Publishers

Reactive publishers are lazy: calling a repository typically builds a task description; execution starts on subscription. Once subscribed and a connection is acquired, the publisher must reach completion, error, or cancellation for resources to be released.

A long-running stream or stalled subscriber can keep a connection held indefinitely. Technically this is prolonged holding rather than forgetting a manual `close()`, yet the effect on the pool is identical.

Ensure every subscription has clear ownership. Avoid fire-and-forget subscriptions lacking cancellation, timeout, or lifecycle management.

### 4.5. Verifying Cancellation and Timeouts

When a client disconnects or a pipeline times out, cancellation must propagate down reactive operators so the driver and framework can clean up resources. If custom code or adapters swallow cancel signals, release can be delayed or missed.

When investigating, test these scenarios:

- Client closes the HTTP connection mid-query.
- Request times out before the database responds.
- Publisher errors while reading multiple rows.
- An inner `flatMap` cancels when the outer pipeline cancels.

Check whether acquired connections return to baseline after each scenario.

## 5. Queries Holding Connections Too Long

A slow query holds a connection for the entire time the database operation needs it. If many such queries run concurrently, the pool can exhaust even with zero leaks.

### 5.1. Slow SQL Queries

Common causes:

- Missing indexes or indexes mismatched with filter and sort clauses.
- Scanning excessive rows or joining large datasets.
- N+1 queries issuing many round trips to the database.
- Database starved of CPU, memory, I/O, or connections.
- Queries blocked waiting on locks held by other transactions.
- Execution plan regressions after data or statistics shifts.

Measure query duration on the database and inspect execution plans using database tools. Do not conclude the pool is too small before checking whether SQL runs efficiently.

### 5.2. Transactions Kept Open Too Long

In reactive transactions, connections are usually held until the transactional publisher completes. If a transaction wraps unrelated steps, the connection remains occupied throughout that time.

Design pattern to avoid:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> inventoryClient.reserve(saved.getId())
                    .thenReturn(saved));
}
```

In this example, the transaction can stay open while the application waits on an HTTP call to the inventory service. If that service is slow, the database connection stays held far longer than needed.

Scope transactions strictly to database operations requiring atomicity. Separate persistence and external calls into distinct steps:

```java
@Service
class OrderWriter {

    private final OrderRepository repository;

    OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Order> save(Order order) {
        return repository.save(order);
    }
}

@Service
class OrderService {

    private final OrderWriter writer;
    private final InventoryClient inventoryClient;

    OrderService(OrderWriter writer, InventoryClient inventoryClient) {
        this.writer = writer;
        this.inventoryClient = inventoryClient;
    }

    public Mono<Order> createOrder(Order order) {
        return writer.save(order)
                .flatMap(saved -> inventoryClient.reserve(saved.getId())
                        .thenReturn(saved));
    }
}
```

In this structure, `OrderWriter` is a separate bean so calls go through the Spring proxy and apply the transaction. The publisher from `save()` finishes the transaction before the outer `flatMap` calls inventory. When business requirements demand consistency between the database and an external service, use an outbox, saga, or compensation mechanism; splitting transactions alone does not solve distributed consistency.

### 5.3. Subscribers Processing Results Too Slowly

With a query returning `Flux<T>`, results can be consumed incrementally. If each item goes through heavy CPU work, external calls, or waits on a slow client, the connection can stay open for the entire lifetime of the stream.

For example, an API streaming millions of rows directly to a slow client can hold a connection for a very long time. Consider:

- Keyset or cursor pagination completing each small query independently.
- Capping returned rows and stream lifetime.
- Moving exports to background jobs that write files to object storage for later download.
- Moving CPU work or external service calls outside database transactions.

Do not blindly call `collectList()` on massive datasets just to avoid long-lived streams if doing so spikes memory consumption. Choose a reading strategy matching data size and business needs.

### 5.4. Excessive Pipeline Concurrency

The `flatMap` operator can subscribe to many inner publishers simultaneously. If each inner publisher runs an R2DBC query, one request can consume multiple connections or create higher acquire pressure than expected.

Example:

```java
Flux.fromIterable(customerIds)
        .flatMap(customerRepository::findById);
```

For large lists, bound concurrency:

```java
Flux.fromIterable(customerIds)
        .flatMap(customerRepository::findById, 8);
```

The value `8` is illustrative only. Pick concurrency based on pool size, concurrent request counts, database capacity, and other queries running in the application. Bounding concurrency in one pipeline does not globally cap concurrency across the whole application.

## 6. Investigation Workflow for Pool Exhaustion

When a pool exhaustion alert fires, investigate step by step to isolate which phase holds connections.

### Step 1: Confirm the Pool Is Actually Bottlenecked

Collect aligned metrics over the same time window:

- `acquiredSize`, `allocatedSize`, `idleSize`, and `pendingAcquireSize`.
- Request rate, throughput, and p50/p95/p99 latency.
- Connection acquisition timeout error counts.
- Application instance counts and per-instance `max-size` settings.

If acquired hits the limit, idle is 0, and pending climbs, the pool lacks available connections at that moment. Record start and end timestamps to correlate with application and database logs.

### Step 2: Separate Acquire, Query, and Hold Durations

Measure three distinct intervals:

1. **Acquire latency:** time spent waiting for a connection from the pool.
2. **Query latency:** time sending SQL and receiving results from the database.
3. **Hold duration:** time from acquiring to releasing the connection.

Common interpretations:

- Acquire rises while query and hold stay normal: concurrent demand exceeds instantaneous capacity or pool is too small for concurrency.
- Query and hold rise together: investigate SQL, database, locks, and network.
- Query is short while hold is long: investigate transactions, streams, slow subscribers, or code holding connections outside SQL.
- Requests finish yet acquired does not drop: check cleanup, cancellation, and open transactions.

Ensure measurements share consistent definitions. Some tools measure query time until metadata arrives, whereas others measure until all rows are consumed.

### Step 3: Check What the Database Is Doing

The database shows which sessions are running queries, waiting on locks, or sitting in open transactions. How you inspect this depends on the database and granted privileges.

For example, in PostgreSQL you can inspect active sessions in the current database:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY query_start;
```

States like `active` or `idle in transaction` should be read alongside `wait_event`, transaction age, and application logs. An `idle in transaction` session can mean a transaction is open while the app waits on a subsequent step or failed to close the transaction.

To find blockers in PostgreSQL, inspect `pg_blocking_pids(pid)` for lock-waiting sessions. Monitoring queries require suitable privileges, and this syntax applies only to PostgreSQL; MySQL, SQL Server, and Oracle provide their own diagnostic views.

### Step 4: Correlate Traces and Application Logs

Locate requests or trace IDs matching the congestion window. Note:

- Which repository method or SQL statement ran.
- When the transaction started and ended.
- Whether HTTP calls, message broker calls, or CPU work occurred between those timestamps.
- Whether the publisher completed, errored, or was cancelled.
- Whether code manually acquired connections anywhere.

Never log passwords, sensitive data, or full SQL payloads containing personal information. When enabling SQL or bind-parameter logging, restrict scope by environment and duration.

### Step 5: Test Error and Cancellation Paths

Try reproducing with timeouts, client disconnects, mapping errors, and concurrent load. After each case, verify acquired connections drop back to baseline. If the issue happens only when publishers cancel, review resource-management code and reactive adapters.

### Step 6: Tune the Pool Only After Identifying the Root Cause

Only after ruling out leaks, slow SQL, and long transactions should you reassess `max-size`, concurrency levels, and instance counts. Enlarging the pool without checking the database can merely shift the queue from the application down into the database.

## 7. Pool and Timeout Configuration

Spring Boot can configure R2DBC Pool via `spring.r2dbc.pool.*` properties when the appropriate pool dependency is present and pooling is enabled for your version.

Example:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-acquire-time: 2s
      max-create-connection-time: 5s
      max-idle-time: 30m
      max-life-time: 2h
```

This is an illustrative configuration, not a universal recommendation. Property names, duration formats, enabling conditions, and required dependencies can vary by Spring Boot version. Check your project's configuration metadata and documentation before applying.

### 7.1. Meaning of Common Properties

| Property | Purpose | Notes |
| --- | --- | --- |
| `initial-size` | Initial connections created at startup | High values increase startup connection bursts |
| `max-size` | Maximum connections managed by the pool | Must account for all app instances and database limits |
| `max-acquire-time` | Maximum time waiting to obtain a connection | Fails requests within bounds when congested; does not fix congestion |
| `max-create-connection-time` | Maximum time to create a new connection | Helps when the database or network is unresponsive |
| `max-idle-time` | Idle duration before eviction under pool policy | Account for database or network idle timeouts |
| `max-life-time` | Maximum lifespan of a connection in the pool | Helps rotate aging connections; does not fix leaks |

### 7.2. Choosing `max-size` From Data

An initial estimate can use Little's Law:

\[
N_{avg} \approx \lambda \times T_{hold}
\]

Where:

- \(N_{avg}\) is the average number of borrowed connections.
- \(\lambda\) is database operations per second.
- \(T_{hold}\) is average connection hold time in seconds.

For example, if the app executes 80 database operations per second and each holds a connection for 0.05 seconds on average:

\[
N_{avg} \approx 80 \times 0.05 = 4
\]

The value 4 is only an estimated average. For production pool sizing, add headroom for bursts, p95/p99 latencies, long transactions, concurrent operations per request, and other workloads. Measure real traffic before finalizing.

Notably, `max-size` applies per instance. With 6 replicas each configured at `max-size = 20`, the service can request up to 120 connections. Add background workers, migration tools, other apps, and administrative connections before comparing against the database limit.

### 7.3. Setting Timeouts Based on Request Budgets

`max-acquire-time` should match the overall request timeout. If a request is only allowed 2 seconds yet acquire waits 30 seconds, the app holds resources and builds useless queues.

Budget timeouts across layers: pool wait, SQL execution, external calls, and total request. Avoid aggressive retries during pool congestion, as retries increase connection demand further.

Raising `max-acquire-time` can reduce visible timeout errors in the short term while making requests wait longer. Raising `max-size` helps if the pool is genuinely undersized, yet can overload the database. Base both changes on metrics and database limits.

## 8. Ways to Reduce Connection Hold Time

Several practices deliver clear improvements:

1. Optimize SQL, indexes, joins, and execution plans to cut query duration.
2. Keep transactions short, wrapping only operations requiring atomicity.
3. Never call HTTP services, send messages, or run slow CPU tasks inside database transactions.
4. Bound concurrency in pipelines spawning many inner queries.
5. Paginate or limit result sets when data volumes are large.
6. Ensure stream subscribers enforce clear timeouts and cancellation.
7. Use repositories or `DatabaseClient` for standard operations so the framework manages connections.
8. Use `usingWhen` whenever acquiring resources manually with asynchronous cleanup.
9. Monitor the connection pool and database together to catch issues before mass timeouts occur.

## 9. Testing Load Tolerance and Leaks

Do not wait until production to discover pool exhaustion. Design controlled load and failure tests.

### 9.1. Concurrent Load Testing

Gradually ramp concurrent requests and record:

- Throughput and p50/p95/p99 latency.
- Acquire latency and pending acquire counts.
- Acquired, idle, and allocated connections.
- Query duration, lock waits, and database CPU.
- Timeout errors and request success rate.

Load tests should mirror production behavior: similar data sizes, query patterns, transactions, and read/write ratios. A benchmark running only `SELECT 1` fails to reflect realistic workloads.

### 9.2. Failure and Cancellation Testing

Intentionally trigger edge cases in a test environment:

- Cancel an HTTP request mid-query.
- Inject an exception during result mapping.
- Slow down an external service inside a transactional flow to observe hold time.
- Stream large datasets via `Flux` with a slow subscriber.
- Send request bursts exceeding `max-size` to observe pending acquire and timeouts.

After each run, wait for operations to settle and confirm acquired connections drop back to baseline. If acquired stays elevated with zero active requests, inspect cleanup paths and open transactions.

### 9.3. Integration Tests With a Real Database

Testing against a real database or Testcontainers reveals differences in drivers, locking, data types, and transaction behavior. Use a compatible R2DBC driver and small pool limits in selected tests to make acquire/release behavior easy to observe.

Do not mock repositories exclusively when the goal is verifying connection lifecycles. Mocks skip real connection acquisition and cannot catch pool leaks.

## 10. Responding When the Pool Exhausts in Production

When the pool runs dry and requests time out, restore service while preserving evidence for root-cause analysis.

1. Confirm current acquired, idle, pending acquire, and acquire times.
2. Check the database for long-running queries, lock waits, or long idle-in-transaction sessions.
3. Identify which endpoint, query, or background job accounts for most borrowed connections.
4. If possible, throttle concurrency or pause heavy background jobs so the pool can recover.
5. If a specific runaway query is confirmed, follow database operations procedures to terminate or remediate it; avoid bulk-killing sessions without understanding transaction impact.
6. Verify pending acquire and acquired counts drop after load throttling.
7. Once stable, save metrics, traces, and logs to fix the root cause.

Restarting the application may free that process's connections, yet it destroys diagnostic evidence and can trigger a fresh connection storm against the database. Treat restarts solely as a controlled recovery step when necessary—never as a fix for a leak.

## 11. Examples of Reading Signals and Choosing Actions

| Observation | Likely Causes to Check First | Action |
| --- | --- | --- |
| Acquired hits max, query latency spikes | Slow SQL, overloaded database, or locks | Inspect execution plans, wait events, indexes, and locks |
| Acquired hits max, queries fast yet hold time long | Open transactions/streams, slow subscribers | Shorten transactions, cap streams, move non-DB work out |
| Acquired creeps up each batch and never drops | Leak in manual acquire or missing cleanup | Check `ConnectionFactory.create()`, `usingWhen`, cancel and error paths |
| Pending rises only at peak hours, then drops | Concurrency burst or undersized pool | Bound concurrency, measure workload, resize pool |
| Idle connections exist yet acquire is slow | Validation, connection creation, internal locks, or metric skew | Check pool logs, validation settings, and version-specific metric definitions |
| Database shows many `idle in transaction` sessions | Transactions open while app waits or never finishes | Audit `@Transactional` boundaries and inner waiting steps |

## 12. Investigation Checklist

- [ ] Verified `acquiredSize`, `idleSize`, `allocatedSize`, and `pendingAcquireSize` over time.
- [ ] Measured acquire latency, query latency, and connection hold duration separately.
- [ ] Correlated application traces with database sessions, queries, and locks.
- [ ] Audited manual `ConnectionFactory.create()` calls and verified cleanup on complete, error, and cancel.
- [ ] Checked whether transactions wrap HTTP calls, messaging, or slow processing.
- [ ] Checked large `Flux` streams, slow subscribers, and `flatMap` concurrency.
- [ ] Summed `max-size` across all replicas plus all other database clients.
- [ ] Re-tested after fixes and confirmed pool recovery under load, timeouts, and cancellation.

## 13. Conclusion

Pool exhaustion occurs when connection demand exceeds available connections at a given time. Connection leaks, prolonged transactions, slow queries, slowly consumed streams, and excessive concurrency can all lead to this state.

Monitor acquired, idle, pending acquire, acquire latency, query duration, and hold duration together. When queries are slow, optimize the database; when transactions or streams hold connections too long, shorten lifecycles; when manual acquisition misses release, fix cleanup across completion, error, and cancellation paths. Adjust pool size only after understanding actual load and database connection limits.
