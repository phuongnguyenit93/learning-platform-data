# Managing Timeouts, Query Cancellation, and Connection Resources

## 1. Why can a reactive query still bottleneck a system?

A Spring Boot WebFlux service handles order lookup requests, queries PostgreSQL via R2DBC, and calls a partner HTTP API. During peak traffic, the API returns `504` or `503` after a few seconds while active database connections hit the pool ceiling. Several clients cancel requests, yet SQL queries continue running on the server. After enabling retries, the system degrades even faster because expensive queries execute repeatedly.

This cluster of failures stems from **time budgets, cancellation signals, and resource lifecycle management**. Using `Mono`/`Flux` does not automatically solve them. Reactive I/O avoids pinning a Java thread per operation, yet database connections remain finite; heavy SQL still consumes database capacity; and cancelling a subscription does not always mean the database halted the statement or rolled back every side effect.

Within `SPRING_BOOT_INTEGRATION`, flows frequently combine HTTP clients, databases, caches, and brokers. You must enforce deadlines across adapters, ensure resources release cleanly on completion/error/cancellation, and carefully constrain retries on side-effecting operations.

This lesson primarily uses **Spring Boot 3.x, Reactor, Spring Data R2DBC, and PostgreSQL**. Many concepts carry over to reactive MongoDB and other reactive clients, though exact `cancel`, transaction, and timeout behavior varies by driver, wire protocol, and database version.

## 2. Distinguishing timeouts at each boundary

A slow API might be waiting for a pooled connection, executing SQL, streaming results, blocked on another transaction's lock, or waiting on downstream HTTP. Slapping on a single `timeout(2s)` without knowing which phase stalled makes diagnosis guesswork.

| Boundary | Resource awaited | Control mechanism | On expiration |
| --- | --- | --- | --- |
| **Request deadline** | Entire business operation | Overall HTTP/request/caller deadline; Reactor `timeout` at the right pipeline boundary | Cancels upstream and returns contract error; never auto-rolls back external systems |
| **Pool acquisition** | Borrowing a connection from pool | `spring.r2dbc.pool.max-acquire-time` when supported pool is active | Fails to acquire connection within budget |
| **Connection creation** | DNS, TCP, TLS, DB handshake | Driver options; R2DBC pool `max-create-connection-time` | Fails connection creation; classify error |
| **SQL execution** | Server processing query, table/row locks | Database statement timeout, driver-specific options | Server cancels statement or errors per engine |
| **Reading result stream** | Bytes streaming server -> client | Backpressure, row limits, per-phase timeouts | Partial results may already have arrived |
| **Transaction** | Transaction-bound resources | Reactive transaction manager, server lock/idle/statement timeouts | Requires rollback or reconciliation if commit outcome is ambiguous |

**Never conflate these three statements:**

1. **“The request timed out”**: a component stopped waiting.
2. **“The subscription was cancelled”**: Reactor propagated a cancel signal to its subscribed source.
3. **“SQL stopped on the database”**: the server received and honored cancellation, or hit a server-side deadline.

These events are related but **not identical**. Drivers generally attempt to translate cancellation into aborting active work, yet guarantees, latency, and protocol handling depend on the driver and server. Specifically for writes: a client timeout never proves the transaction did not commit.

### Timeline illustration

~~~mermaid
sequenceDiagram
    participant U as HTTP client
    participant A as Spring WebFlux
    participant P as R2DBC pool
    participant D as Database
    U->>A: GET /orders/{id}
    A->>P: Acquire connection
    P-->>A: Connection
    A->>D: Execute SELECT
    Note over A: Client deadline expires
    A-->>U: Timeout / error response
    A-->>D: Cancel propagated (best effort)
    Note over D: SQL may take time to stop
    A->>P: Cleanup / return connection
~~~

If timeout hits **before acquiring a connection**, no acquire request should remain pending after cancellation. If timeout hits mid-query, connection cleanup must finish before the driver/pool safely reuses that connection—never lend out a connection with an in-flight unfinished statement.

## 3. Reactor subscribe, cancel, and doFinally mechanics

Reactive publishers are typically **lazy**: assembling a `Mono` or `Flux` does not run queries until a subscriber attaches, such as WebFlux subscribing to a controller's return value.

~~~java
Mono<OrderView> result = repository.findOrder(orderId);
// Only assembled the Publisher; database has not run any query yet.

return result;
// WebFlux subscribes to serve the HTTP request.
~~~

When `timeout` detects a missed deadline, it emits `TimeoutException` downstream and **cancels the upstream subscription**. Similarly, if an HTTP client disconnects and WebFlux cleans up the request, cancellation propagates down the reactive chain. By contrast, calling `subscribe()` manually inside a service spawns an orphaned subscription detached from the incoming request's lifecycle.

### Key signals

| Signal / operator | How to interpret | Notes |
| --- | --- | --- |
| `onComplete` | Publisher finished normally | Does not prove side effects succeeded if detached via `subscribe()` |
| `onError` | Publisher failed | Downstream timeouts often arrive as `onError` |
| `cancel` | Subscriber needs no more items | Not a Reactor error sent upstream via `onError` |
| `doOnCancel` | Callback on upstream cancellation | Useful for telemetry; not meant for manual async cleanup |
| `doFinally(SignalType)` | Callback on complete, error, or cancel | Emits `ON_COMPLETE`, `ON_ERROR`, or `CANCEL` for metrics/tracking |
| `timeout(Duration)` | Operator-level publisher timeout | On `Flux`, usually checks time **between elements**, not total stream duration |
| `onErrorResume(...)` | Maps errors to fallback | Does not catch upstream cancellation where no error flows downstream |

**Common pitfall:** `Flux.timeout(Duration.ofSeconds(2))` does not guarantee an entire stream finishes in two seconds. A `Flux` emitting one item per second can run for minutes without timing out because inter-item gaps stay short. To cap total execution time, enforce an overall **request/flow deadline** rather than only inter-item timeouts, and never mistake a truncated stream for complete output.

**Another pitfall:** calling `block()` inside a WebFlux event-loop handler stalls the I/O thread and triggers cascading timeouts. Since R2DBC is reactive, return `Mono`/`Flux` straight out. If you must invoke a **blocking** library (like legacy JDBC), isolate it in a dedicated adapter with a blocking scheduler and load bounds rather than mixing blocking I/O directly onto event-loop threads.

## 4. Configuring a bounded R2DBC connection pool

### 4.1. Why are pools still needed in reactive stacks?

Reactive does not mean infinite connections. Long transactions, unconsumed result streams, and slow queries still pin connections. When traffic outpaces database capacity, a pool must bound active connections and acquisition waits rather than letting thousands of requests pile up endlessly.

Spring Boot 3.x dependency example (Gradle Kotlin DSL):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Basic configuration:

~~~yaml
# application.yml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal.example:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 16
      max-idle-time: 10m
      max-acquire-time: 2s
      max-create-connection-time: 5s
~~~

`${DB_PASSWORD}` is a Spring placeholder injecting the `DB_PASSWORD` environment variable. Manage credentials with a secret manager and enable PostgreSQL/driver TLS per environment policy. Values like `16` connections, `2s` acquire, and `5s` create are illustrative only; size them against database `max_connections`, instance counts, concurrent queries, and measured load.

Pool property names depend on Spring Boot and R2DBC Pool versions; verify properties bind properly rather than assuming from YAML alone. If a pooling library is absent or you declare a custom `ConnectionFactory`, `spring.r2dbc.pool.*` properties may not govern the live factory.

**Never size connections from a single instance in isolation.** Across 20 pods, `max-size=16` means hundreds of potential connections—on top of migrations, admin access, workers, and sibling services. Budget pool sizes **cluster-wide**, then apply backpressure, concurrency caps, and admission control to stay within DB capacity.

### 4.2. What happens when connections are not returned?

~~~text
HTTP requests
    |
    v
Reactive service
    |
    v
R2DBC Pool (max-size=16)
  [borrowed: 16] [idle: 0] [pending: rising]
    |
    v
PostgreSQL
  Slow query / lock / open stream
~~~

When `borrowed` pins at `max-size`, `pending acquire` counts and wait times climb, causing new requests to fail on acquire timeout even while DB connectivity is technically up. Investigate root causes: missing indexes, bloated transactions, unconsumed streams, raw manually-opened connections never closed, or excessive concurrency.

Never "solve" pool exhaustion purely by raising `max-size`. Over-provisioning connections forces PostgreSQL to juggle more concurrent queries, worsening latency. Inspect query plans, transaction hold times, concurrency limits, and pool acquire metrics.

## 5. Timeouts in Reactor pipelines and API error responses

### 5.1. Setting observable timeouts in an adapter

A Spring Data R2DBC adapter using `DatabaseClient`:

~~~java
// OrderReadAdapter.java — Spring Boot 3.x / Spring R2DBC
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class OrderReadAdapter {
    private static final Logger log =
            LoggerFactory.getLogger(OrderReadAdapter.class);
    private static final Duration QUERY_BUDGET = Duration.ofSeconds(3);

    private final DatabaseClient db;

    public OrderReadAdapter(DatabaseClient db) {
        this.db = db;
    }

    public Mono<OrderView> find(String tenantId, UUID orderId) {
        Mono<OrderView> query = db.sql("""
            SELECT id, status
            FROM orders
            WHERE tenant_id = :tenant AND id = :id
            """)
                .bind("tenant", tenantId)
                .bind("id", orderId)
                .map((row, metadata) ->
                        new OrderView(
                                row.get("id", UUID.class),
                                row.get("status", String.class)))
                .one()
                .doFinally(signal ->
                        log.debug("R2DBC source finished: {}", signal));

        return query
                .timeout(QUERY_BUDGET)
                .doOnError(TimeoutException.class,
                        error -> log.warn("Order read deadline exceeded"));
    }
}

record OrderView(UUID id, String status) {}
~~~

`.one()` returns a `Mono`; `.timeout(3s)` spans from subscription until item emission or completion, including pool acquire wait time. Upon timeout, Reactor emits `TimeoutException` downstream and cancels `query` upstream. `doFinally` placed **before** `timeout` observes `CANCEL` on the aborted source, whereas a callback after `timeout` observes `ON_ERROR`. This confirms the pipeline aborted due to timeout, not necessarily that the DB stopped SQL immediately.

`tenantId` here is illustrative; in multi-tenant APIs, extract it from authenticated security context and enforce authorization. `.bind(...)` keeps values separate from SQL syntax to prevent SQL injection.

**Adapter-level timeouts alone are insufficient:** a request may also await `WebClient`, caches, or brokers. Enforce an **overall deadline** at the use-case boundary and budget sub-steps so stacked adapter timeouts do not blow the SLA.

### 5.2. How API layers should translate timeouts

Mapping exceptions to HTTP status codes is an API contract choice, not an intrinsic R2DBC rule:

- Reads failing due to an overloaded database often return `503 Service Unavailable` with a stable error code and optional `Retry-After` if backed by real policy.
- Gateway-style APIs waiting on dependencies may return `504 Gateway Timeout` per operational contracts.
- Timeouts are never `404 Not Found`; `404` applies only after a completed query confirms no authorized data exists.
- Never leak SQL text, connection strings, database hostnames, or stack traces to clients. Log internally with trace IDs and error categories.

Using `.onErrorResume(TimeoutException.class, ...)` at the **API or service boundary** is reasonable for mapping responses, but never turn timeouts into `Mono.empty()`. Doing so hides dependency outages and tricks callers into thinking an order does not exist.

If the HTTP client already disconnected, the server cannot send a timeout response anyway; upstream chains should cancel and release resources. Never spawn "fire and forget" subscriptions in controllers just to avoid cancel errors—that leaks queries consuming connections with nobody left waiting for the result.

## 6. Client-side query cancellation vs. database-side timeouts

### 6.1. Why cancelling the subscription is not enough

When a subscriber cancels, Reactor sends cancel upstream to the driver if the chain is unbroken. The driver may send a protocol cancel packet or tear down/clean the connection, subject to driver details:

- The database may have finished executing the query before the cancel arrived.
- SQL blocked on locks or heavy work on the server takes time to abort.
- For `UPDATE`/`INSERT`, the server may already have committed; client timeout proves nothing about rollback.
- Pools must never lend out a connection whose protocol/transaction state is still dirty.

For expensive queries or strict server protection, combine **Reactor timeouts** with **database-enforced execution limits** wherever supported by driver and engine.

### 6.2. PostgreSQL statement_timeout

PostgreSQL provides `statement_timeout` to abort long queries on the server. Inside a transaction, use `SET LOCAL` so the setting never leaks onto a pooled session reused later:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '2500ms';
SELECT id, status
FROM orders
WHERE tenant_id = 'tenant-42' AND id = '00000000-0000-0000-0000-000000000001';
COMMIT;
~~~

`SET LOCAL` applies strictly to the current transaction and must not be run standalone outside a transaction expecting it to govern a separate later query. PostgreSQL timeouts raise a `query_canceled` SQLSTATE (typically `57014`). After an error inside a PostgreSQL transaction, the transaction enters an aborted state and must roll back before reusing the connection.

In a Spring R2DBC service, combine `TransactionalOperator` so both statements run inside one Reactor Context-bound transaction:

~~~java
// PostgresTimedReadService.java
import java.time.Duration;
import java.util.UUID;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class PostgresTimedReadService {
    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public PostgresTimedReadService(
            DatabaseClient db, TransactionalOperator tx) {
        this.db = db;
        this.tx = tx;
    }

    public Mono<OrderView> find(String tenantId, UUID orderId) {
        Mono<OrderView> work =
                db.sql("SET LOCAL statement_timeout = '2500ms'")
                  .then()
                  .then(db.sql("""
                      SELECT id, status FROM orders
                      WHERE tenant_id = :tenant AND id = :id
                      """)
                          .bind("tenant", tenantId)
                          .bind("id", orderId)
                          .map((row, metadata) ->
                                  new OrderView(
                                          row.get("id", UUID.class),
                                          row.get("status", String.class)))
                          .one());

        return tx.transactional(work)
                .timeout(Duration.ofSeconds(4));
    }
}
~~~

`TransactionalOperator` must be backed by a matching **reactive** transaction manager such as `R2dbcTransactionManager`, registered as a bean if needed:

~~~java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

When adding that `@Bean` method, import `org.springframework.context.annotation.Bean`, `org.springframework.transaction.ReactiveTransactionManager`, and `org.springframework.transaction.reactive.TransactionalOperator` inside an application `@Configuration` class.

This layers a **2.5-second per-statement budget** inside PostgreSQL beneath a **4-second publisher budget** covering pool wait, transaction begin, SQL execution, and cleanup. These are illustrative **layered deadlines**, not a guarantee both fire at exact timestamps. If pool acquisition stalls, the Reactor timeout may fire before SQL even starts.

Never run un-scoped session-level `SET statement_timeout = ...` on pooled connections because settings bleed into subsequent requests. For permanent role/database defaults, let DBAs configure vetted limits. On MySQL, MongoDB, or other engines, timeout syntax and behavior differ—**never assume `SET LOCAL statement_timeout` works across engines**.

### 6.3. Cancellation and transactions

Reactive transactions bind to **Reactor Context**, not a fixed `ThreadLocal`. When downstream cancels an open transactional publisher, Spring's operator triggers cleanup and rollback along the subscription lifecycle. Still, if commit already ran or failed ambiguously during a network drop, **never assume the entire business operation rolled back**.

Never break out via `subscribe()` or `block()` inside a transactional method expecting child work to inherit the connection/transaction. With reactive `@Transactional`, return `Mono`/`Flux` so the interceptor manages subscription. For cross-system flows, an `R2dbcTransactionManager` `@Transactional` never wraps HTTP, brokers, or another database into an atomic commit.

## 7. Releasing connections across all three paths: complete, error, cancel

### 7.1. Prefer Spring templates and transaction managers

Using `R2dbcEntityTemplate`, `DatabaseClient`, or Spring reactive repositories lets Spring manage acquiring and releasing connections around publisher and transaction lifecycles. Inside transactions, Spring keeps the connection bound rather than closing after each statement. Never manually call `close()` on a Spring-managed connection or store a connection in a singleton service field.

When hitting `ConnectionFactory` directly, you are responsible for cleanup **even when subscribers cancel**. Synchronous `try/finally` blocks cannot cover asynchronous resource lifetimes once a method returns a `Publisher`.

### 7.2. Mono.usingWhen for manual connection management

Example counting open orders using the raw R2DBC SPI without `DatabaseClient`:

~~~java
// RawOrderCounter.java — manual connection management example
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class RawOrderCounter {
    private final ConnectionFactory factory;

    public RawOrderCounter(ConnectionFactory factory) {
        this.factory = factory;
    }

    public Mono<Long> countOpen() {
        return Mono.usingWhen(
                Mono.from(factory.create()),
                connection -> Mono.from(
                        connection.createStatement("""
                            SELECT COUNT(*) FROM orders WHERE status = $1
                            """)
                                .bind(0, "OPEN")
                                .execute())
                        .flatMap(result -> Mono.from(
                                result.map((row, metadata) ->
                                        row.get(0, Long.class)))),
                connection -> Mono.from(connection.close()),
                (connection, error) -> Mono.from(connection.close()),
                connection -> Mono.from(connection.close()));
    }
}
~~~

`usingWhen` wires resource acquisition, async usage, completion cleanup, error cleanup, and cancellation cleanup. On pooled connections, `close()` normally returns the connection to the pool per pool contract rather than closing the underlying TCP socket. Never touch a connection reference after cleanup.

Notice the **PostgreSQL-specific `$1` parameter marker** and assumption that `COUNT(*)` maps to `Long`. Other drivers use different markers and numeric types. This snippet exists purely to teach resource lifecycles; for everyday queries, prefer `DatabaseClient` to avoid manual connection plumbing.

Never use `doFinally(signal -> connection.close().subscribe())` as routine cleanup. Detached subscriptions execute out of order, go unawaited, and swallow cleanup errors. Use `usingWhen` or Spring abstractions so cleanup stays inside the publisher lifecycle.

### 7.3. Streams can pin results and connections

A `Flux` streaming hundreds of thousands of rows pins its connection until completion or cancellation. Calling `collectList()` buffers everything onto the JVM heap; `take(100)` cancels upstream after 100 rows yet does not replace an SQL `LIMIT 100` on the database server. Prefer bounded queries, keyset pagination, or controlled batch sizes.

Example:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenant
  AND (created_at, id) > (:last_created_at, :last_id)
ORDER BY created_at, id
LIMIT 200;
~~~

This illustrates **keyset pagination** given a valid cursor and matching index, fetching small pages instead of holding long streaming queries open. Cursors must scope by tenant, exact types, and deterministic ordering; the initial page uses a cursor-free predicate rather than tuple comparison.

## 8. Controlling concurrency and backpressure

### 8.1. Unbounded flatMap can starve the pool

In integration flows reading a batch of IDs from Kafka or HTTP and enriching them from the DB, an uncapped `flatMap` launches too many concurrent query subscriptions. While the pool caps physical connections, the acquire backlog still swells and delays higher-priority requests.

~~~java
// enrichment: look up each order ID
Flux<OrderView> enrich(Flux<UUID> ids, String tenantId,
                       OrderReadAdapter adapter) {
    return ids.flatMap(
            id -> adapter.find(tenantId, id),
            8); // at most 8 concurrent inner publishers in this operator
}
~~~

`flatMap(..., 8)` caps concurrency within **this single pipeline**, not across the whole JVM. With 100 concurrent requests, each launching 8 queries still hits 800 concurrent acquires. Coordinate pool sizing, HTTP/broker concurrency, rate limits, and workload caps holistically.

| Operator / strategy | Preserves output order? | Tradeoff |
| --- | --- | --- |
| `flatMap(mapper, concurrency)` | Not guaranteed | Runs inner publishers concurrently; emits as each finishes |
| `concatMap(mapper)` | Yes | Sequential execution; strict ordering, lower concurrency |
| `flatMapSequential(mapper, concurrency)` | Yes (matches source order) | Concurrent execution, but buffers early results |
| SQL `LIMIT` + keyset pagination | Ordered by SQL `ORDER BY` | Bounds payload size and connection hold time per read |

When events update the same entity, `flatMap` can reorder writes. Enforce ordering by business key and versions/CAS rather than assuming message arrival order. For heavy workloads, **active query count**, **pending acquires**, and **connection hold duration** matter far more than Java thread count.

### 8.2. Backpressure is not free

Publishers and subscribers negotiate item counts via `request(n)`, yet not all database drivers translate downstream demand directly into strict row-by-row server fetches—drivers may prefetch or buffer internally. An unbounded `Flux` paired with a slow consumer still pins a connection and clogs the pool. Prefer bounded queries, pagination, and appropriately sized batches.

Never try to speed up slow queries with `publishOn(Schedulers.boundedElastic())`: R2DBC is already non-blocking, so switching schedulers neither accelerates SQL nor frees the DB connection. Reserve `boundedElastic` for isolating unavoidable blocking calls under strict load caps.

## 9. Retries, idempotency, and timeouts on writes

### 9.1. A timeout may mean the database already committed

Suppose a consumer processes `PaymentCaptured(eventId=pay-813)` to debit a wallet in PostgreSQL. If the client times out right as SQL finishes or `COMMIT` reaches the server, you cannot assume the update failed. Unconditional retries would debit the wallet twice.

Instead, enforce a **durable idempotency key and unique constraint**, recording the marker in the same transaction as the domain update:

~~~sql
CREATE TABLE consumed_payment_event (
    event_id TEXT PRIMARY KEY
);

-- Executed inside the business transaction.
WITH inserted AS (
    INSERT INTO consumed_payment_event(event_id)
    VALUES (:event_id)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
)
UPDATE wallet
SET balance = balance - :amount
WHERE wallet_id = :wallet_id
  AND balance >= :amount
  AND EXISTS (SELECT 1 FROM inserted);
~~~

Real transactional code must inspect `rowsUpdated()`: when zero, distinguish an already-processed event from a missing wallet or insufficient balance. For genuine business errors, **roll back** the inserted marker too—never commit a "processed" marker when the debit never occurred. Enforce balances, permissions, event IDs, and concurrency per business contract.

### 9.2. Retry only classified transient and safe errors

| Scenario | Auto-retry? | Notes |
| --- | --- | --- |
| Read-only `SELECT` with clear transient driver error | Yes, with bounded backoff | Stay within **overall deadline** and avoid retry storms |
| Pool acquire timeout when pool is overloaded | Very sparingly | Immediate retries worsen the pending queue |
| Bad SQL syntax, missing table, permission denied | No | Configuration/contract bug requiring a fix |
| Statement timeout on chronically slow query | Usually no | Fix indexes, query plans, and locks first |
| `INSERT`/`UPDATE` with ambiguous commit outcome | Never blindly retry | Look up idempotency key and reconcile |
| Broker redelivery of same consumer event | Must be replay-safe | Unique inbox key inside the same business transaction |

When using `retryWhen(Retry.backoff(...))`, keep retries **within the request's overall deadline**. Every retry resubscribes, potentially executing fresh SQL. Never stack multiple independent retry layers that multiply attempts exponentially. Because `TimeoutException` and cancellations take different paths, base retry rules on exact error sources and outcomes.

### 9.3. Coordinating HTTP/brokers with databases

Suppose Spring Boot consumes a Kafka event, updates an order projection via R2DBC, and commits the Kafka offset. If DB commit succeeds and the consumer crashes before offset commit, Kafka redelivers. Protect with an `eventId` inbox in the DB and ack/commit broker offsets **only after DB commit**. If a timeout hits around commit, the Kafka offset does not prove DB rolled back.

For outbound HTTP via `WebClient`, `TransactionalOperator` covers only the R2DBC transaction. It **cannot roll back accepted HTTP requests** or Kafka/RabbitMQ publishes. Preserve multi-system integrity with outbox/sagas, idempotency, and compensation policies.

## 10. Production observability and debugging

### 10.1. Monitoring each phase

Key signals to watch (exact metric names vary by instrumentation version):

| Category | Signals to track | What they reveal |
| --- | --- | --- |
| **API** | Request latency p95/p99, timeout counts, client disconnects/cancels | Separates caller deadlines from slow databases |
| **R2DBC pool** | Acquired/idle/pending counts, acquire wait time, acquire timeouts | Detects pool saturation or held connections |
| **SQL** | Query latency, statement timeouts, SQLSTATE codes, slow plans | Heavy queries, missing indexes, lock contention |
| **Transactions** | Transaction duration, rollbacks, commit failures, lock waits | Long resource holds or ambiguous commits |
| **Reactive pipeline** | Complete/error/cancel counts by adapter and trace ID | Separates upstream cancellations from source errors |
| **External systems** | `WebClient` timeouts, broker lag, retries, idempotency conflicts | Pinpoints external bottlenecks or replays |

Include correlation IDs, operation names, durations, error categories, and safe SQLSTATEs in error logs. Never log passwords, secret-bearing connection URLs, sensitive payloads, or SQL filled with private data.

In PostgreSQL, inspect active or waiting sessions:

~~~sql
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS query_age
FROM pg_stat_activity
WHERE application_name = 'orders-integration'
  AND state <> 'idle';
~~~

Operators need appropriate privileges to view full details. `pg_stat_activity` captures a point-in-time snapshot, not definitive proof of whether a client sent a cancel. Across layered timeouts, correlate timestamps and traces rather than blaming the pool or database blindly.

### 10.2. Quick diagnostic table

| Symptom | Likely causes to check | Action |
| --- | --- | --- |
| `PoolAcquireTimeoutException` or equivalent | Pool exhausted, connections held too long, slow queries | Inspect acquired/pending metrics, bound concurrency, audit transactions and query plans |
| API times out yet `pg_stat_activity` still shows query | Driver cancellation incomplete or server timeout unset | Check driver behavior, DB `statement_timeout`, locks, and cancellation |
| Idle connections stay low after requests finish | Missing cleanup on cancel; detached work | Audit manual `subscribe()`, `usingWhen`, and transaction boundaries |
| `Flux` runs forever without timing out | `Flux.timeout` only checks gaps between items | Enforce total deadline and pagination |
| Raising `max-size` worsens p99 | Too many concurrent queries overloading DB | Reduce concurrency, tune indexes, rebalance cluster pools |
| Client gets `503` despite fast SQL | Slow pool acquire, downstream HTTP, or queue wait | Measure duration per phase instead of SQL time alone |
| Retrying a timed-out write duplicates data | Ambiguous commit without idempotency | Add unique event IDs, transactions, reconciliation, and safe retry rules |
| `@Transactional` seems not to roll back | Detached `subscribe()`, wrong manager, or already committed | Keep work in one reactive chain; verify context and commit boundaries |

## 11. Testing cancellation and connection cleanup

Test against a **production-equivalent database** (e.g., PostgreSQL via Testcontainers) with a small pool in an isolated environment. Mocked unit tests only check Reactor signals; they prove nothing about server SQL cancellation or pool connection return.

| Test case | How to reproduce | What to verify |
| --- | --- | --- |
| Timeout before pool acquire | `max-size=1`; hold connection in one transaction, fire second request | Second request hits acquire timeout; no pending acquire lingers after cancel |
| Timeout mid-query | `SELECT pg_sleep(5)` with shorter client timeout | Downstream gets timeout; inspect cancellation/transaction and pool recovery |
| Server-side timeout | `SET LOCAL statement_timeout` shorter than query duration | PostgreSQL aborts statement; transaction rolls back and cleans up |
| Client disconnect | Cancel subscription mid-stream | `doFinally` sees `CANCEL`; connection returns cleanly to pool |
| In-transaction error | Force constraint violation | Full rollback with zero partial writes |
| Timeout right at write/commit | Induce network/DB lag creating ambiguous outcome | No blind retry duplicating data; reconciles via idempotency key |
| High concurrency spike | Concurrent `flatMap` requests | Pool never exceeds cap; latency and queueing remain bounded |
| Driver upgrade | Run full suite against new R2DBC driver | Timeout, cancellation, and pool lifecycle remain intact |

Reactor Test snippet verifying downstream timeout signaling:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.test.StepVerifier;

void shouldTimeoutSlowQuery(DatabaseClient db) {
    StepVerifier.create(
            db.sql("SELECT pg_sleep(5)")
              .then()
              .timeout(Duration.ofMillis(250)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(3));
}
~~~

This assumes `reactor-test` on the test classpath and a live PostgreSQL test instance; it validates **downstream** timeout signals, not that `pg_sleep` stopped on the server. Afterward, verify no connections leaked from the pool, fresh queries succeed, and PostgreSQL holds no orphaned queries or transactions.

**Never rely on virtual time to verify real network resource cleanup.** `StepVerifier.withVirtualTime` suits pure Reactor timer/backoff logic; driver, pool, PostgreSQL, and network cancellation require integration tests.

## 12. Comprehensive scenarios and self-check questions

**Scenario A — “API times out yet the pool still leaks connections”.** A handler returns a `Mono` from `DatabaseClient`, while a service branch calls `subscribe()` manually for auditing without managing that subscription. When the HTTP client disconnects, the main publisher cancels yet the audit query keeps running. Fix by composing auditing into the managed flow or persisting an outbox row for a monitored worker, measuring acquired/pending counts before and after cancellation.

**Scenario B — “Two-second timeout yet the stream runs for a minute”.** An API uses `Flux.timeout(2s)` while emitting one row per second. Because gaps stay under 2 seconds, the operator never trips. Fix with a total request deadline, result caps/pagination, and server-side query timeouts.

**Scenario C — “Retry after timeout debits twice”.** An R2DBC update commits right as the response drops; the handler retries `UPDATE balance = balance - amount`. Fix with a unique business event ID, transactional idempotency guards, and state reconciliation before retrying ambiguous outcomes.

### Self-check

1. **Does `Mono.timeout` guarantee PostgreSQL halts SQL immediately?** No. Reactor cancels upstream, while server cancellation depends on driver/DB support and may lag.
2. **Does `Flux.timeout(2s)` cap the entire stream to two seconds?** No; it normally caps idle gaps between emissions.
3. **Why do you need `max-acquire-time` in addition to query timeouts?** Because waiting for a free connection can stall requests even when SQL itself is fast.
4. **Why must `SET LOCAL statement_timeout` run inside a transaction?** So it applies only to that transaction without leaking onto pooled sessions reused later.
5. **How does `usingWhen` differ from `doFinally(... close().subscribe())`?** `usingWhen` binds async cleanup cleanly into complete/error/cancel lifecycles instead of spawning unawaited detached subscriptions.
6. **Does increasing pool size always reduce timeouts?** No; extra concurrent queries can overload the database.
7. **Does a write timeout prove no commit happened?** No; treat commit outcomes as potentially ambiguous and rely on idempotency/reconciliation.
8. **Does R2DBC `@Transactional` manage Kafka or HTTP?** No, only resources owned by its transaction manager.
9. **How do you prove connections return to the pool after cancellation?** Run integration tests, observe acquired/idle/pending metrics, and execute subsequent queries after cleanup.

In reactive Spring Boot data flows, sound configuration pairs **overall deadlines**, **per-phase timeouts**, **observable cancellation**, **cleanup across complete/error/cancel**, **bounded pools and concurrency**, and **idempotent writes**. Each layer protects a distinct boundary, and real driver/database tests prove how the system behaves under timeouts, cancellations, and upgrades.
