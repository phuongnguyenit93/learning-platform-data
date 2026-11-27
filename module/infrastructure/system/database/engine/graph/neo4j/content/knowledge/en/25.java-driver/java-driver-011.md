# Choosing Synchronous, Asynchronous, or Reactive APIs for Neo4j Applications

## 1. The Problem: Same Cypher, Three Ways Java Processes Results

A supply-network application stores `Supplier` and `Product` nodes and `SUPPLIES` relationships in Neo4j. Users may want a list of products from one supplier, or to analyze hundreds of thousands of relationships for reporting. Both requests can use Cypher, yet **how Java receives results and manages work while waiting on Neo4j** strongly affects application resources.

Neo4j Java Driver provides three primary API styles:

1. **Synchronous (blocking):** call a method and wait for the result before continuing execution.
2. **Asynchronous:** receive a `CompletionStage` and chain follow-up steps once I/O completes.
3. **Reactive:** receive a `Publisher`, consume when subscribed, and regulate record delivery using **backpressure**.

All three still send queries to **the same Neo4j Database**, using the same nodes, relationships, indexes, constraints, and transaction engine. Picking an API **does not make Cypher run faster by itself** or increase server query capacity if the bottleneck lies in query plans, disk, locks, or server resources. The main differences lie in **threads, orchestration model, result consumption rate, and client-side concurrency**.

In the `DATABASE_ENGINE_GRAPH_NEO4J` module, your API choice should align with your Java/Spring Data Neo4j architecture, data volume, and how the application consumes Cypher results.

## 2. Quick Comparison Before Choosing an API

| Criterion | Synchronous | Asynchronous | Reactive |
| --- | --- | --- | --- |
| Session | `org.neo4j.driver.Session` | `org.neo4j.driver.async.AsyncSession` | `org.neo4j.driver.reactivestreams.ReactiveSession` or `org.neo4j.driver.reactive.ReactiveSession` |
| Operation return type | Value or `Result` directly | `CompletionStage<T>` / `CompletableFuture<T>` | `Publisher<T>`; commonly Reactor `Flux`/`Mono` |
| Calling thread | May wait on I/O during the operation | Does not hold a thread waiting on I/O; callbacks run when stages complete | Does not hold a thread waiting on I/O; subscriber pulls data on demand |
| Multi-record consumption | `Result.next()` / `list()` / `stream()` | `ResultCursor.nextAsync()` / `listAsync()` / `forEachAsync()` | `Publisher<Record>` with request/subscribe, supporting backpressure |
| Managed transactions | `executeRead` / `executeWrite` | `executeReadAsync` / `executeWriteAsync` | `executeRead` / `executeWrite` returning a Publisher |
| Session lifecycle | `try-with-resources` fits naturally | Closed via `closeAsync()` after stages finish | Tied to subscription lifecycle via `usingWhen` or equivalent resource hook |
| Complexity | Low | Medium; must manage stage chaining and errors | Higher; requires understanding subscriptions, backpressure, cancellation, and context |
| Best fit | CRUD, simple APIs, batch/CLI, imperative code | I/O fan-out, high concurrency, `CompletionStage` integration | Spring WebFlux/Reactor, large streaming pipelines needing backpressure |
| Common pitfalls | Holding threads too long, `list()` on huge sets | Forgetting to wait for `closeAsync()`, blocking I/O threads, lost exceptions | Forgetting to subscribe, calling `block()` on event loops, skipping cancel cleanup |

**Default to synchronous if the application is imperative.** With multiple independent I/O calls, choose async when the architecture already uses `CompletionStage`. For **end-to-end reactive** apps or explicit backpressure requirements, choose reactive. Neo4j documentation likewise recommends reactive primarily when the application already follows a reactive model; other cases typically use sync or async. Java 21+ with virtual threads further expands options for imperative code with heavy concurrent I/O.

## 3. Version Scope and Driver 6.x Changes

Examples in this lesson use the **Neo4j Java Driver 6.x** API. When using Driver 5.x or older codebases, consult the migration guide before copying code.

| Component | Driver 6.x | Notes |
| --- | --- | --- |
| Sync session | `driver.session(SessionConfig)` | `Session` extends `AutoCloseable` |
| Async session | `driver.session(AsyncSession.class, config)` | Do not use legacy `driver.asyncSession()` |
| Reactor reactive session | `driver.session(org.neo4j.driver.reactivestreams.ReactiveSession.class, config)` | Do not use `driver.rxSession()` |
| Java Flow reactive session | `driver.session(org.neo4j.driver.reactive.ReactiveSession.class, config)` | Returns Java 9+ `Flow.Publisher` |
| Managed transaction | `executeRead` / `executeWrite` | Legacy `readTransaction` / `writeTransaction` removed |
| Async managed transaction | `executeReadAsync` / `executeWriteAsync` | Uses `AsyncTransactionCallback` |
| Reactive transaction | `executeRead` / `executeWrite` on reactive session | Returns a publisher, executed upon subscription |

**Distinguish the two `ReactiveSession` interfaces:** one lives in `reactivestreams` for Reactive Streams/Reactor, and the other lives in `reactive` for `java.util.concurrent.Flow`. They share similar publisher concepts with different Java types, so never mix imports in the same file.

A `Driver` is normally created **once and shared across threads**; it manages the connection pool and routing. A `Session` (including async/reactive sessions) is a **short-lived work context** and must never be shared concurrently across multiple transactions. Each concurrent request or independent transaction should get its own session.

## 4. Preparing a Shared Graph and Query

Examples use a dedicated `DriverDemoUser` label to avoid colliding with real application schemas. In a test database, create a uniqueness constraint on ID:

```cypher
CREATE CONSTRAINT driver_demo_user_id IF NOT EXISTS
FOR (u:DriverDemoUser) REQUIRE u.id IS UNIQUE;
```

Create nodes:

```cypher
UNWIND [
  {id: 'u001', name: 'An', active: true},
  {id: 'u002', name: 'Bình', active: true},
  {id: 'u003', name: 'Chi', active: false},
  {id: 'x004', name: 'Dũng', active: true}
] AS row
MERGE (u:DriverDemoUser {id: row.id})
SET u.name = row.name,
    u.active = row.active;
```

Shared read example:

```cypher
MATCH (u:DriverDemoUser)
WHERE u.active = true AND u.id STARTS WITH $prefix
RETURN u.id AS id, u.name AS name
ORDER BY name
LIMIT $limit;
```

Parameters:

```json
{"prefix": "u", "limit": 100}
```

With the sample data, `u001` and `u002` are expected. Use **parameters** for `$prefix` and `$limit` instead of concatenating user input into Cypher strings; add indexes/constraints when needed to guarantee keys and optimize queries on large graphs.

In the Java snippets below, assume a `Driver driver` created via `GraphDatabase.driver(...)` already exists and is **closed on application shutdown**, never created per method call.

For simplicity, the result DTO is a record:

```java
record UserView(String id, String name) {}
```

## 5. Synchronous API: Simple, Readable, and Easy Transaction Control

### 5.1. Read Query Using a Managed Transaction

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

static List<UserView> findActiveSync(Driver driver, String prefix) {
    String cypher = """
        MATCH (u:DriverDemoUser)
        WHERE u.active = true AND u.id STARTS WITH $prefix
        RETURN u.id AS id, u.name AS name
        ORDER BY name
        LIMIT $limit
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.executeRead(tx ->
            tx.run(cypher, Map.of("prefix", prefix, "limit", 100))
              .list(record -> new UserView(
                  record.get("id").asString(),
                  record.get("name").asString()
              ))
        );
    }
}
```

How it works:

1. `driver.session(...)` creates a lightweight session and borrows a connection from the pool as needed.
2. `executeRead(...)` orchestrates a **managed read transaction**, automatically retrying eligible transient errors.
3. `tx.run(...)` sends Cypher with parameters; `list(...)` consumes all results inside the transaction.
4. `try-with-resources` closes the session on scope exit, even when exceptions occur.

Because results are **materialized into a List**, this fits queries with a small `LIMIT`. For millions of records, `list()` can exhaust the Java heap; use sequential streaming or pagination instead of buffering the whole set in memory.

### 5.2. When to Choose Synchronous

- CRUD endpoints with small result sets and linear steps.
- Spring MVC services or command-line jobs written in an imperative style.
- Multi-step update queries needing one clear transaction boundary.
- Teams prioritizing simple stack traces and straightforward testing.
- Moderate I/O load, or Java 21+ apps using virtual threads with an appropriate resource strategy.

**Blocking does not automatically mean "slow".** If Neo4j returns 5 records quickly under modest concurrency, async/reactive can add complexity without improving latency. Under heavy load, measure latency, connection pool usage, CPU cost, and thread capacity.

### 5.3. Write Queries and Transactions

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.executeWriteWithoutResult(tx ->
        tx.run(
            """
            MERGE (u:DriverDemoUser {id: $id})
            SET u.name = $name
            """,
            Map.of("id", "u005", "name", "Hà")
        ).consume()
    );
}
```

`executeWriteWithoutResult` fits when a callback does not need to return data. In managed transactions, the driver may re-invoke the callback on transient failures. Therefore avoid **sending emails, charging payments outside Neo4j, or incrementing global variables** inside the callback; external side effects can occur multiple times. Use business keys, constraints, and idempotent designs when needed.

## 6. Asynchronous API: `CompletionStage` and Proper Lifecycle Management

### 6.1. Mechanism

`AsyncSession` returns `CompletionStage<T>`. The calling thread can continue other work instead of waiting for Neo4j I/O to finish. Subsequent stages use `thenApply`, `thenCompose`, `handle`, or `whenComplete`.

- `thenApply`: transforms a **completed value** into another value.
- `thenCompose`: chains an operation that also returns a `CompletionStage`, avoiding nested stages.
- `handle`: handles both success and failure.
- `whenComplete`: observation hook for results/errors; **not an automatic mechanism to await async cleanup inside the callback**.

One critical rule: stage callbacks may run on **network I/O threads**. Never call `Thread.sleep(...)`, `join()`, `get()`, or run heavy CPU tasks inside these I/O callbacks. If heavy computation is needed, offload to `thenApplyAsync(..., executor)` with a managed executor.

### 6.2. Async Example Closing the Session After Processing

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.async.AsyncSession;

static CompletionStage<List<UserView>> findActiveAsync(
        Driver driver, String prefix) {

    String cypher = """
        MATCH (u:DriverDemoUser)
        WHERE u.active = true AND u.id STARTS WITH $prefix
        RETURN u.id AS id, u.name AS name
        ORDER BY name
        LIMIT $limit
        """;

    AsyncSession session = driver.session(
        AsyncSession.class,
        SessionConfig.forDatabase("neo4j")
    );

    CompletionStage<List<UserView>> query = session.executeReadAsync(
        tx -> tx.runAsync(
                cypher, Map.of("prefix", prefix, "limit", 100)
            )
            .thenCompose(cursor -> cursor.listAsync(
                record -> new UserView(
                    record.get("id").asString(),
                    record.get("name").asString()
                )
            ))
    );

    CompletableFuture<List<UserView>> completed =
        new CompletableFuture<>();

    query.whenComplete((users, queryError) ->
        session.closeAsync().whenComplete((ignored, closeError) -> {
            if (queryError != null) {
                completed.completeExceptionally(queryError);
            } else if (closeError != null) {
                completed.completeExceptionally(closeError);
            } else {
                completed.complete(users);
            }
        })
    );

    return completed;
}
```

Here:
- `executeReadAsync` and `runAsync` return stages; `listAsync` fetches and maps all results while still inside the transaction.
- Async sessions **do not use `try-with-resources`** because the Java lexical block can exit before async I/O finishes.
- The returned stage completes only after `closeAsync()` finishes. This avoids completing requests while sessions are still awaiting cleanup.
- The error handling above prioritizes the query error if both query and close fail. In production services, log cleanup failures too so secondary errors are not lost.
- This snippet assumes stage creation does not throw synchronously before attaching callbacks; in shared utilities, handle setup exceptions as well.

Caller usage:

```java
findActiveAsync(driver, "u")
    .thenAccept(users -> users.forEach(System.out::println))
    .exceptionally(error -> {
        System.err.println("Neo4j async query failed: " + error);
        return null;
    });
```

In real applications, ensure the runtime **retains the lifecycle** of the stage and does not close the Driver while work is still in flight. Use `join()` at the outermost layer of CLI tools only when deliberately waiting; doing so inside I/O callbacks destroys non-blocking benefits.

### 6.3. Do Not Confuse Async with Large-Result Streaming

`listAsync()` still **materializes the entire result in the Java heap**. It is only asynchronous in how it awaits I/O, not end-to-end backpressure driven by record processing demand. For large outputs:

- `nextAsync()`: requests the next record step by step.
- `forEachAsync(...)`: applies a consumer to each record; the consumer must be fast and non-blocking.
- Reactive API: better suited when the **consumer must control the pace of incoming records** under Reactive Streams.

Never run multiple concurrent queries on **the same AsyncSession** expecting each to have a safe independent transaction. One session runs at most one active transaction at a time; use separate sessions for concurrent operations.

## 7. Reactive API: Subscribers, Backpressure, and Resource Lifecycles

### 7.1. How Reactive Differs from Async

`CompletionStage` represents **a single future result**. It can still complete with a huge `List`.

`Publisher` models a **signal stream** under Reactive Streams: `onSubscribe`, `onNext`, `onError`, `onComplete`. The subscriber calls `request(n)` to demand at most `n` more items. This gives the driver a mechanism to pace records pulled from Neo4j to match consumption speed.

```text
Neo4j server
     |
     | Bolt / query results
     v
Neo4j ReactiveSession
     |
     | Publisher<Record>
     v
Subscriber (Reactor Flux/Mono)
     |
     +-- request(10) --> receive up to requested number of elements
     +-- process 10 records
     +-- request(10) --> request more when needed
```

This is a **conceptual model**; the driver, Bolt protocol, and Reactor use internal buffering/prefetching, so "request 10" does not strictly mean literally 10 network packets or 10 records in memory at every layer. Backpressure controls data flow; it **does not automatically make Neo4j's Cypher execution process fewer rows**.

### 7.2. Two Reactive Variants in Java Driver 6.x

| Package | Publisher standard | Used in |
| --- | --- | --- |
| `org.neo4j.driver.reactivestreams` | `org.reactivestreams.Publisher` | Project Reactor, Spring WebFlux, and Reactive Streams codebases |
| `org.neo4j.driver.reactive` | `java.util.concurrent.Flow.Publisher` | Apps using Java Flow API without necessarily depending on Reactor |

To use Reactor, add a `reactor-core` dependency aligned with your project's BOM and compatible with your Driver/Spring versions. Under Spring Boot, rely on the selected Boot version's BOM and dependency management instead of mixing incompatible Reactor versions.

### 7.3. Reactor Example with Subscription-Scoped Session Management

```java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.reactivestreams.ReactiveSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

static Flux<UserView> findActiveReactive(
        Driver driver, String prefix) {

    String cypher = """
        MATCH (u:DriverDemoUser)
        WHERE u.active = true AND u.id STARTS WITH $prefix
        RETURN u.id AS id, u.name AS name
        ORDER BY name
        LIMIT $limit
        """;

    return Flux.usingWhen(
        Mono.fromSupplier(() ->
            driver.session(
                ReactiveSession.class,
                SessionConfig.forDatabase("neo4j")
            )
        ),
        session -> Flux.from(session.executeRead(
            tx -> Flux.from(tx.run(
                cypher,
                Map.of("prefix", prefix, "limit", 100)
            ))
            .flatMap(result -> Flux.from(result.records()))
            .map(record -> new UserView(
                record.get("id").asString(),
                record.get("name").asString()
            ))
        )),
        ReactiveSession::close
    );
}
```

Design notes:
- `Mono.fromSupplier` opens the session **only upon subscription**, avoiding opening unused sessions.
- `executeRead` manages the transaction reactively; `tx.run(...)` returns a result publisher and `result.records()` returns a publisher of records.
- `Flux.usingWhen` closes the session via its cleanup publisher when the stream terminates; with the shared cleanup overload, Reactor handles completion, errors, and cancellation per `usingWhen` semantics.
- There is no `block()` inside the pipeline. **Never call `subscribe()` arbitrarily inside repositories/services** and lose control over lifecycles and errors. Return the `Flux` for callers to compose.
- One subscription should own one dedicated session; never keep an app-wide shared `ReactiveSession`.

Handling in a service:

```java
Flux<UserView> names = findActiveReactive(driver, "u")
    .filter(user -> user.name() != null)
    .doOnError(error -> System.err.println(error.getMessage()));
```

`names` is a **stream blueprint**. It does not query the database until an actual subscriber subscribes. In Spring WebFlux, the HTTP runtime subscribes to the publisher returned by the controller. In standalone apps, callers must subscribe intentionally and manage lifecycles.

### 7.4. Reactive Does Not Mean "Never Uses RAM"

Backpressure regulates **output**, yet:
- `collectList()` still gathers every record into a List, risking client-side OOM.
- `sort()` on a `Flux` may buffer all data before emitting anything.
- `flatMap` with excessive concurrency/prefetch can open too many queries or retain sizable buffers.
- Calling blocking libraries (JDBC, synchronous file reads, blocking HTTP clients) inside `map(...)`/`flatMap(...)` can stall the event loop. When unavoidable, offload to a dedicated scheduler per Reactor guidelines.
- Queries with `ORDER BY` or heavy aggregations may still process vast amounts of data **on the server** before emitting the first record.

Thus, reactive pays off when **the entire processing path** (driver → service → controller → client) respects non-blocking and backpressure semantics, not merely by changing return signatures to `Flux`.

## 8. Choosing the API by Application Style

| Scenario | Typical reasonable choice | Reason |
| --- | --- | --- |
| Spring MVC REST CRUD, small results | **Sync** | Simple, clear transactions, easy debugging; virtual threads are an added option on Java 21+ |
| CLI migrations or linear business batch jobs | **Sync** | Sequential flow with clear failure stopping points |
| Gateway calling Neo4j and multiple independent I/O services | **Async** | Composes `CompletionStage`s without tying up threads waiting on each I/O |
| Event-driven service using `CompletableFuture` | **Async** | Fits existing pipelines; asynchronous error handling |
| End-to-end Spring WebFlux + Reactor | **Reactive** | Fits `Flux`/`Mono`, Reactor context, and backpressure |
| Exporting/streaming huge record counts with slow consumers | **Reactive** | Regulates record demand, avoiding unbounded client buffering |
| Heavy CPU computation per record | Depends on workload; often streaming + worker pool | Never run blocking/heavy CPU work on I/O threads |
| Graph query slow due to missing indexes | **Optimize query first** | Switching APIs does not fix a bad query plan |
| Single short query needed | **Sync**, optionally `Driver.executableQuery` | Avoids unnecessary callback lifecycle complexity |

**A system does not have to use a single API style everywhere.** However, mixing styles requires clear boundaries. Avoid serving WebFlux requests while calling blocking repositories on the event loop. Avoid rewriting an entire imperative codebase to Reactor before the team has proper error and cancellation observability.

## 9. Shared Transaction Boundaries, Retries, and Consistency

### 9.1. Choosing Managed Transactions vs. Auto-Commit

| Need | API to use |
| --- | --- |
| Read/write business unit needing transactions with transient retries | Sync `executeRead/executeWrite`, async `executeReadAsync/executeWriteAsync`, reactive `executeRead/executeWrite` |
| Single auto-commit Cypher statement | Sync `session.run`, async `session.runAsync`, reactive `session.run` |
| Manual `commit`/`rollback` control | `beginTransaction` and its async/reactive counterparts |
| Cypher `CALL { ... } IN TRANSACTIONS` | **Auto-commit/implicit transaction**; do not wrap in a managed transaction |

Managed transactions are **automatically retried by the Neo4j Driver when an error is classified as transient**. Because callbacks can re-run, avoid external side effects inside callbacks. For payments, emails, or external writes, use idempotency keys/outboxes or appropriate integration patterns.

Common mistake:

```java
// WRONG for queries batching internally via CALL ... IN TRANSACTIONS:
session.executeWrite(tx ->
    tx.run("""
        LOAD CSV WITH HEADERS FROM $source AS row
        CALL (row) {
          MERGE (:DriverDemoUser {id: row.id})
        } IN TRANSACTIONS OF 1000 ROWS
        """,
        Map.of("source", csvUrl)
    ).consume()
);
```

This statement opens sub-transactions internally, so it must run in an **implicit transaction** via `session.run(...)` or its async/reactive equivalent. Also ensure the CSV file is accessible to the Neo4j server as configured.

### 9.2. Results Are Valid Only While the Transaction Is Alive

- In sync, `Result` depends on the transaction/session; map it to needed DTOs/lists inside the callback before returning.
- In async, `ResultCursor` depends on the transaction; consume it with `listAsync`/`forEachAsync`/`consumeAsync` **inside the callback's stage**. Never return the cursor outside and close the session.
- In reactive, return the publisher **within the transaction scope** and keep the session alive until the stream finishes/cancels; never retain a `ReactiveResult` after the transaction closes.

A query may be sent while results are **pulled lazily**. To be sure an auto-commit operation finished, consume the result or close/commit the transaction/session within its proper lifecycle.

### 9.3. Routing, Bookmarks, and Clusters

With a `neo4j://` URI pointing to a cluster, using `executeRead`/`executeReadAsync`/reactive `executeRead` lets the driver route reads properly, while write transactions route to the appropriate writer. This is a **routing hint**, not a security privilege; RBAC is still enforced by Neo4j.

A single session links transactions with **causal consistency**. If request A writes and request B reads across **two separate sessions**, use a bookmark manager/bookmarks per your driver version when read-your-writes across the cluster is required. Never assume every read replica updates instantaneously after a write.

### 9.4. Cancellation and Timeouts

- Timeouts at the Java HTTP or Reactor layer **do not guarantee Neo4j rolled back every task**. Handle ambiguous transaction state and verify after errors/disconnects.
- `CompletionStage.cancel(...)` should not be relied upon as a guaranteed business mechanism to abort a server-side query.
- When a reactive subscription sends `cancel`, the driver can clean up the session/transaction, yet if a write already committed, client-side cancellation **does not undo the commit**.
- When a transaction deadline is needed, pass `TransactionConfig` with `withTimeout(...)` and align gateway, pool, and server timeouts.

If a response is lost after a write, the application may not know whether the write committed. Use business keys and `MERGE`/constraints for safe retries instead of unconditional `CREATE`.

## 10. Memory, Connection Pool, Threads, and Performance

### 10.1. Shared Driver, Per-Operation Session

A `Driver` holds the connection pool. Creating a session is lightweight; **never keep one global session for all requests**. Sessions are not thread-safe and cannot run multiple independent transactions concurrently. If 1,000 requests run concurrently against a finite connection pool, some requests must **wait to acquire a connection** regardless of whether sync, async, or reactive is used.

Pool tuning should consider:
- Actual concurrency, query latency, and number of databases/server endpoints.
- `maxConnectionPoolSize`, connection acquisition timeout, and server-side limits.
- Request timeout rates, retries, and long-running transactions holding connections.
- Returned record counts, fetch size, and client heap usage.

**Never increase pool size indefinitely** hoping every request gets faster: the Neo4j server still has CPU, memory, page cache, I/O, and lock limits. A slow full-scan query often gets worse when more concurrent requests run in parallel.

### 10.2. Async/Reactive and Threads

- Sync holds a thread while waiting on I/O; traditional servlet models need enough threads, while Java virtual threads reduce thread-holding costs where applicable.
- Async returns a stage so the caller does not block, yet every callback must obey the rule **never block network I/O threads**.
- Reactive orchestrates subscribers, prefetching, and backpressure, while still needing threads for events and CPU work.
- When processing large record sets with heavy CPU work, use dedicated executors/schedulers; measure latency and queues instead of spawning unbounded threads.

### 10.3. Measure What Actually Needs Improvement

| Metric | Meaning |
| --- | --- |
| Latency p50/p95/p99 | User experience across query + driver + application completion |
| Throughput (requests/s) | Serving capacity as request rate climbs |
| Connection acquisition wait time | Whether the pool is the bottleneck |
| Active sessions/transactions | Whether operations are held open too long |
| JVM heap and GC | Whether too many records/lists are buffered |
| Event loop/worker utilization | Whether async/reactive callbacks are blocking |
| Server CPU, I/O, page cache | Whether the real bottleneck sits on Neo4j |
| Cypher `EXPLAIN` / `PROFILE` | Index seeks, fan-out, Cartesian products, high DB Hits |

Comparing the three APIs is only fair when using **the same Cypher, same parameters, same data, same pool settings, and comparable load**. `async` does not automatically reduce DB Hits or relationships traversed by Neo4j.

## 11. Spring Data Neo4j: Choose the Full Stack, Not Just the Driver API

Spring Data Neo4j (SDN) builds on top of the Neo4j Java Driver, adding entity mapping, repositories, template/client abstractions, and Spring transaction management.

### 11.1. Imperative Applications

A Spring MVC application can use:

- `Neo4jRepository<T, ID>`.
- `Neo4jClient` (imperative).
- `Neo4jTemplate` and the Spring transaction manager.
- Direct sync Java Driver calls when specialized queries are needed, provided transaction boundaries are clearly understood.

Repository example:

```java
interface UserRepository
        extends org.springframework.data.neo4j.repository.Neo4jRepository<
            DriverDemoUserEntity, String> {

    java.util.List<DriverDemoUserEntity> findByActiveTrue();
}
```

This is an **interface signature sketch**; the entity must be mapped properly for your SDN version with `@Node` and `@Id`. Standard repositories are imperative; never call them on a WebFlux event loop without intentionally offloading blocking work.

### 11.2. Reactive Applications

A WebFlux application can use:

- `ReactiveNeo4jRepository<T, ID>`.
- `ReactiveNeo4jClient`.
- `ReactiveNeo4jTemplate` and the reactive transaction manager.
- Direct reactive Java Driver APIs when explicit publisher/feature control is needed.

Repository sketch:

```java
interface ReactiveUserRepository
        extends org.springframework.data.neo4j.repository.ReactiveNeo4jRepository<
            DriverDemoUserEntity, String> {

    reactor.core.publisher.Flux<DriverDemoUserEntity> findByActiveTrue();
}
```

A method returning `Flux` **is not guaranteed non-blocking** if internal service logic calls blocking APIs. Reactive Spring transactions rely on **Reactor context**; imperative `ThreadLocal` transaction propagation does not automatically flow across async/reactive chains.

**Note:** if an application injects the `Driver` bean and calls `driver.session(...)`/`executeWrite(...)` directly, those driver transactions do not automatically participate in an active `@Transactional` managed by Spring Data Neo4j. Pick a clear transaction strategy instead of assuming operations across two layers share one atomic transaction.

### 11.3. Distinguishing "Async in Java" from "Reactive in Spring"

`CompletableFuture` does not turn a `Neo4jRepository` into a backpressure-aware async repository. Spring Data Neo4j supports imperative and reactive models; if a specific workflow needs async, you can use **Driver AsyncSession** inside a component explicitly managing its transactions without migrating the whole application to WebFlux.

## 12. Common Mistakes and How to Fix Them

| Symptom | Typical cause | Remediation |
| --- | --- | --- |
| Async API still blocks request threads | Calling `join()` / `get()` immediately on stage | Compose with `thenCompose`/`thenApply` and return the stage |
| Deadlocks / unexpected latency | Callback on I/O thread calls blocking code | Offload CPU/blocking tasks to an appropriate executor |
| `Connection acquisition timed out` | Pool slots exhausted by transactions holding connections | Inspect session hold time, query plans, and pool sizing |
| Memory spikes despite `listAsync` | Still materializing all results into a List | Use incremental cursors or reactive backpressure |
| Returning `Flux` runs no query | No subscriber | Return publisher to controller/reactive runtime or manage subscriptions explicitly |
| Query runs twice on two subscribers | Cold publisher subscribed twice | Understand per-subscription semantics and cache/share deliberately when valid |
| Reactor stalls | `block()` or blocking JDBC/HTTP inside pipeline | Never block event loops; use a dedicated scheduler if bridging is unavoidable |
| Session leak | Missing `closeAsync` or missing cancel cleanup | Chain `closeAsync`; use `usingWhen` for reactive |
| `ResultConsumedException` | Using cursor after transaction/session closes | Map/consume results inside the transaction scope |
| Duplicate writes on retry | Callback has side effects or unkeyed `CREATE` | Use constraints, `MERGE`, and idempotent logic |
| No `rxSession()` in Java Driver 6 | Legacy API removed | Use `driver.session(ReactiveSession.class, ...)` |
| `CALL ... IN TRANSACTIONS` throws transaction error | Invoked inside a managed transaction | Run as an implicit/auto-commit query |
| WebFlux + blocking SDN is slow | Imperative repository called on event loop | Use reactive repository/client or offload blocking calls carefully |
| Huge reactive stream still slow on server | Cypher sort/aggregate/full scan still consumes resources | Tune `EXPLAIN`/`PROFILE`, predicates/indexes, and projection |
| Request timed out yet data still wrote | Client timeout/cancel occurred after commit | Design safe retries and verify actual state |

## 13. Practice Exercises

1. Load the `DriverDemoUser` dataset and write a sync `executeRead` query returning `List<UserView>`. Measure total time with `LIMIT 10` and `LIMIT 1000` on a sufficiently large test dataset.
2. Rewrite Exercise 1 using `AsyncSession`, ensuring the returned stage completes only after `closeAsync`. Explain why calling `join()` right after `executeReadAsync` defeats async benefits on the calling thread.
3. Convert Exercise 1 to Reactor `Flux<UserView>`. Run with a slow-demanding subscriber and observe the differences among `flatMap`, `concatMap`, and `collectList`.
4. A Spring MVC service handles 40 req/s returning 5 nodes each; a WebFlux service serves 5,000 subscribers streaming 10,000 records each. Recommend an API for each service and how to control pool/heap usage.
5. Write a managed transaction updating `(:Supplier)-[:SUPPLIES]->(:Product)`. Explain why publishing a Kafka notification directly inside the `executeWrite` callback risks duplicate messages.
6. For an import query using `CALL { ... } IN TRANSACTIONS`, explain why it must run as auto-commit across all three APIs and why data reconciliation is required after partial batch commits.
7. Draft a Java Driver 5 → 6 smoke-test checklist: session factory, transaction callbacks, reactive imports, session lifecycle, retries, timeouts, mapping, and driver shutdown.
8. If a `Flux` is canceled after updating the graph, is the database guaranteed to roll back? Propose how to record an idempotency key and verify outcomes.
9. A pipeline uses `Flux.from(session.executeRead(...))` yet still calls `collectList()` on millions of nodes. Analyze where the heap can exhaust and design a safe consumption alternative.
10. Explain why an app with many async requests can still be slow if `PROFILE` reveals millions of `DB Hits` and no selective index.

## 14. Pre-Deployment API Selection Checklist

1. **Architecture:** is the codebase imperative, `CompletionStage`-based, or Reactor/Flow?
2. **Output shape:** returning one DTO, a few dozen rows, or streaming millions of records?
3. **Concurrency:** how many requests are actually in flight, and how many connections are available?
4. **Transactions:** read/write, managed/auto-commit, retries, and idempotency requirements?
5. **Lifecycle:** shared Driver, per-operation Session, cleanup on error/cancel?
6. **Threading:** any blocking callbacks, heavy CPU work, or `block()` on an event loop?
7. **Data & Cypher:** proper indexes/constraints, or large fan-outs and aggregations?
8. **Versions:** Driver/Neo4j/SDN/Reactor compatible; free of APIs removed in 6.x?
9. **Observability:** p95 latency, pool waits, JVM heap, retries, query logs, `EXPLAIN`/`PROFILE`?
10. **Load testing:** measured with representative data and request mix; simplest solution meeting SLOs?

## 15. Key Takeaways

- **Sync** is the clear choice for imperative CRUD and linear business flows; Java 21+ virtual threads are also worth considering for high-concurrency I/O.
- **Async** uses `AsyncSession` and `CompletionStage` when composing multiple I/O tasks without blocking threads; consume cursors and await `closeAsync` properly.
- **Reactive** uses `ReactiveSession`, `Publisher`, and backpressure for already-reactive pipelines, especially when consumers must pace record delivery.
- **Async does not equal reactive**: `listAsync()` still buffers entire results in RAM, just like `collectList()` in Reactor.
- **Shared Driver, per-operation Session.** Sessions are not thread-safe; each independent transaction needs its own context.
- **Managed transactions can retry**, so callbacks must be safe to re-execute; `CALL { ... } IN TRANSACTIONS` requires an implicit transaction.
- **Imperative and reactive Spring Data Neo4j use different transaction managers**; direct driver calls do not automatically join Spring-managed transactions.
- Choose the API based on **architecture, data volume, concurrency, and backpressure needs**; verify via profiling and load tests instead of assuming any API is universally faster.

### References

- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Neo4j Java Driver Manual — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Non-blocking asynchronous queries](https://neo4j.com/docs/java-manual/current/async/)
- [Neo4j Java Driver Manual — Control results flow with reactive streams](https://neo4j.com/docs/java-manual/current/reactive/)
- [Neo4j Java Driver Manual — Upgrade from older versions](https://neo4j.com/docs/java-manual/current/upgrade/)
- [Neo4j Java Driver API — AsyncSession](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/async/AsyncSession.html)
- [Neo4j Java Driver API — ResultCursor (Async)](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/async/ResultCursor.html)
- [Neo4j Java Driver API — ReactiveSession (Flow)](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/reactive/ReactiveSession.html)
- [Spring Data Neo4j — Building Blocks](https://docs.spring.io/spring-data/neo4j/reference/introduction-and-preface/building-blocks.html)
- [Spring Data Neo4j — Reference Documentation](https://docs.spring.io/spring-data/neo4j/reference/)
