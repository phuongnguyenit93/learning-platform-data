# Choosing Concurrency Levels to Protect the Connection Pool

A Spring Data R2DBC application can issue many database queries simultaneously thanks to reactive APIs and non-blocking I/O. However, the number of connections to the database is always finite. If a processing flow generates too many concurrent queries, those queries will contend for connections in the pool, increasing wait times, causing timeouts, and potentially slowing down the entire application.

Therefore, reactive design must control *concurrency* at both the processing flow and connection layers. Reactor operators like `flatMap` allow limiting the number of active inner publishers; the connection pool limits the number of physical connections borrowed simultaneously; and application-wide limits prevent many independent requests from accumulating into a load that exceeds database capacity.

The goal is not to generate as many queries as possible. The goal is to keep the number of active database operations within the bounds of the pool and the database's processing capacity, while preserving backpressure, predictable response times, and predictable resource utilization.

## 1. Why limit concurrency?

Suppose a request needs to fetch information for 100 customers. A simple way to write this is to iterate over the list of IDs and call the repository for each ID:

```java
return Flux.fromIterable(customerIds)
        .flatMap(customerRepository::findById);
```

`flatMap` can subscribe to many inner publishers simultaneously. Without a concurrency limit, the number of pending or running queries can grow with the list size and the number of concurrent requests in the application.

Suppose 40 requests execute the flow above concurrently, each containing 100 IDs. The system could generate thousands of read operations in a short period. If the pool only has 30 connections, operations exceeding the available connections must wait to acquire one. Wait times rise, the pool queue lengthens, and requests can time out before the queries even execute.

Concurrency must be limited because:

- **The pool has a finite size:** a connection can only be borrowed for one operation scope at a time under normal usage.
- **The database has finite resources:** too many concurrent queries can increase CPU, I/O, lock contention, and memory usage.
- **The application serves multiple requests concurrently:** a limit within one pipeline does not equal a system-wide limit.
- **Backpressure must be maintained end-to-end:** you should not create swarms of tasks only for them to queue up waiting for connections.
- **Timeouts can accumulate:** a request waiting on the pool, waiting on the query, and waiting on other services can exceed the HTTP request deadline.

## 2. Three layers of concurrency control

To manage resources properly, distinguish three layers:

```text
Incoming requests
       |
       v
Application admission / bulkhead
(application-wide database work limit)
       |
       v
Reactive pipeline
(flatMap concurrency, concatMap, batching)
       |
       v
R2DBC Connection Pool
(max-size, acquire timeout, pending borrowers)
       |
       v
Database
(CPU, I/O, locks, max connections)
```

| Layer | Mechanism | Scope of control |
|---|---|---|
| Reactive flow | `flatMap` with concurrency, `concatMap`, batching | Number of active inner publishers within a single subscription |
| Application | Bulkhead or admission limit per workload type | Total work allowed into a group of queries on a single application instance |
| Connection pool | `max-size`, acquire wait timeout | Number of concurrent connections borrowed from a pool |
| Database | Connection limit, workload, query plan | Overall capacity of the database management system |

No single layer completely replaces the others. The pool is the final guardrail for connections, but if every request creates hundreds of publishers and lets them queue at the pool, the application still wastes memory and increases latency. Conversely, limiting `flatMap` within one request cannot control the total number of queries across all running requests.

## 3. Limiting active publishers with Reactor

### 3.1. Unbounded and bounded `flatMap`

`flatMap` turns each source element into an inner publisher and merges the results. You can pass `concurrency` to limit the number of inner publishers subscribed to concurrently:

```java
Flux<Customer> findCustomers(List<Long> ids) {
    return Flux.fromIterable(ids)
            .flatMap(customerRepository::findById, 8);
}
```

In this example, a single subscription allows at most 8 `findById` operations to be active concurrently through `flatMap` at this point. Only when an inner publisher completes does `flatMap` subscribe to the next element.

You can also specify `prefetch`:

```java
return Flux.fromIterable(ids)
        .flatMap(customerRepository::findById, 8, 1);
```

- `concurrency = 8`: maximum number of inner publishers subscribed to concurrently.
- `prefetch = 1`: number of elements pre-requested from each inner publisher in this configuration.

For database publishers that typically emit one result via `Mono`, prefetch is not a connection limit. The concurrency parameter is what directly caps the number of active inner operations at that `flatMap` call site.

### 3.2. `concatMap` when sequential execution is needed

If operations must run one after another or do not need concurrency, use `concatMap`:

```java
return Flux.fromIterable(customerIds)
        .concatMap(customerRepository::findById);
```

`concatMap` subscribes to the next inner publisher only after the current one completes. This keeps the number of active inner operations at one and preserves emission order matching input order.

Use it when:

- Steps depend on the result of the previous step.
- Tight load control is required.
- Operations are inside a transaction sharing a connection.
- Execution order is part of the business logic.

In exchange, sequential processing can reduce throughput if the operations are independent and the database still has headroom for parallel execution.

### 3.3. `flatMapSequential` when output order must be preserved

`flatMapSequential` allows inner publishers to run concurrently while emitting results in the order of the source elements:

```java
return Flux.fromIterable(customerIds)
        .flatMapSequential(customerRepository::findById, 8, 1);
```

This operator is useful when output order matters but the queries are independent. However, if an earlier inner publisher finishes slowly, results from later publishers must wait in a buffer. Consequently, preserving order can increase the amount of data temporarily held in memory.

### 3.4. Comparing the operators

| Operator | Concurrent inner publishers | Output order | Suitable cases |
|---|---:|---|---|
| `flatMap(mapper)` | Per default subscription/prefetch behavior, not an explicit business limit | Can interleave | Only when default concurrency is appropriate and the source is already bounded |
| `flatMap(mapper, concurrency)` | Up to `concurrency` | Can interleave | Independent queries needing load limits |
| `concatMap(mapper)` | 1 | Preserves order | Sequential operations or when tight control is needed |
| `flatMapSequential(mapper, concurrency)` | Up to `concurrency` | Preserves source order | Concurrent processing while requiring ordered output |

Do not rely on operator defaults to protect the database. Set concurrency explicitly wherever fan-out to a repository occurs.

## 4. Per-request concurrency limits are not application-wide limits

This is a critical point when designing systems with many concurrent requests.

Suppose each request uses:

```java
.flatMap(repository::findById, 8)
```

The limit of 8 applies only to one subscription. If 20 requests run simultaneously, each request can have up to 8 active inner publishers at that point. The total number of active inner publishers can reach around 160, while the pool may only have 30 connections.

```text
Request A: up to 8 database operations --+
Request B: up to 8 database operations --+
Request C: up to 8 database operations --+--> Pool max-size = 30
...                                      --+
Request T: up to 8 database operations --+
```

The pool still enforces the physical connection limit, so the remaining operations wait. If incoming load continues to grow, the queue and wait times will grow accordingly.

Therefore, combine:

- Limiting fan-out inside each pipeline.
- Limiting total database work for a given use-case type when needed.
- Configuring the pool to fit the database's connection budget.
- Rate-limiting incoming requests or returning overload errors when the system reaches its threshold.

An application-level bulkhead can limit how many tasks of the same type are allowed to run on a single instance. Libraries like Resilience4j provide reactive bulkhead integration; if used, configure appropriate limits and rejection/waiting policies. Do not mistake a per-instance bulkhead for a cluster-wide limit: with multiple instances, total concurrency is still the sum across all instances.

## 5. Configuring the R2DBC connection pool

The R2DBC connection pool manages creating, allocating, and reusing connections. With Spring Boot, when the pool dependency and matching auto-configuration are present, you can configure the pool via `spring.r2dbc.pool.*` properties.

Illustrative configuration example:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:store}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 30
      max-idle-time: 20m
      max-life-time: 30m
      max-acquire-time: 2s
      max-create-connection-time: 3s
```

Properties may vary across Spring Boot and R2DBC Pool versions. Check your project version's configuration metadata/documentation before copying settings into production.

Meaning of common properties:

| Property | Purpose |
|---|---|
| `enabled` | Enable/disable the pool when supported by auto-configuration |
| `initial-size` | Initial number of connections created |
| `max-size` | Maximum number of connections in the pool |
| `max-idle-time` | Duration a connection can remain idle before being evicted per pool policy |
| `max-life-time` | Maximum lifetime of a connection |
| `max-acquire-time` | Maximum time to wait to borrow a connection |
| `max-create-connection-time` | Maximum time allowed to create a new connection |

Some versions also provide options for validation, acquire retries, or other limits. Only enable and tune them when you understand the behavior of your driver, database, and library version.

### 5.1. `max-size` is a connection limit, not a request limit

If `max-size` is 30, the pool only allows up to 30 connections to be allocated simultaneously from that pool. It does not mean the application only accepts 30 requests or has only 30 publishers. Many requests may be waiting to acquire a connection while only a subset of operations currently hold connections to run.

### 5.2. Acquire wait time

`max-acquire-time` limits how long an operation waits to obtain a connection. If the time expires without the pool providing a connection, the publisher emits an error. Too high a value leaves requests hanging when the pool is saturated; too low a value may reject traffic spikes that the system could have handled after a brief wait.

Choose acquire time based on the request deadline and target latency. The sum of pool wait time, query execution time, and response processing must fit within the request's time budget.

### 5.3. `initial-size` and `max-size`

`initial-size` affects how many connections are created initially, while `max-size` is the pool cap. You do not need to set `initial-size` equal to `max-size` in every environment. An oversized pool can tie up database connections even during low load; an undersized pool can force operations to wait during peak hours.

### 5.4. Do not raise pool size just to clear a queue

If the pool is saturated, increasing `max-size` may help in the short term, but it can also subject the database to more concurrent queries than it can handle well. Before increasing it, inspect query latency, CPU, I/O, lock waits, actual connection count, and active running queries. Optimizing queries or reducing fan-out is usually more effective than simply adding connections.

## 6. Calculating the system-wide connection budget

The pool must be sized according to the total number of application instances and other components sharing the database.

Example:

- The database allows a maximum of 200 connections.
- 40 connections must be reserved for administration, migrations, monitoring, and other services.
- There are 4 application instances.
- Each instance has one R2DBC pool.

The maximum budget for the application is 160 connections. If split evenly, each instance could have a `max-size` of around 40. This is purely an arithmetic example; in practice, leave extra headroom for failover, temporary scaling, background workers, and other pools.

```text
Database connection budget = 200

Reserved for other clients  = 40
Application budget          = 160

4 app instances
160 / 4 = 40 connections per instance (upper budget)
```

Reference formula:

\[
\text{Max total connections}
= \sum_{i=1}^{N} \text{poolMaxSize}_i
+ \text{other clients' connections}
\]

This total must remain below the database limit and include a safety margin. If autoscaling can grow instances from 4 to 10, calculate based on the maximum possible number of running instances, not just the current count.

### 6.1. Reserve headroom for other work

Do not allocate every connection to HTTP requests. The database may need connections for:

- Migrations or administrative tasks.
- Monitoring, backups, and maintenance.
- Background workers, schedulers, or consumers.
- Another service sharing the same database.
- Spare connections during rollouts or autoscaling.

A single application's pool cannot see connections held by other clients. Budget coordination must be calculated at the system level.

## 7. Estimating concurrency from connection hold time

An initial estimation technique uses Little's Law for active work:

\[
L = \lambda \times W
\]

Where:

- (L) is the average number of operations currently being served.
- (λ) is the completion rate of operations per second.
- (W) is the average time an operation holds the resource—here, how long a connection is borrowed.

For example, if the system needs to complete an average of 300 queries/second and each query holds a connection for an average of 40 ms (0.04 seconds), the average number of connections needed for that load is roughly:

\[
L = 300 \times 0.04 = 12
\]

This is an average estimate, not the optimal pool size. You need extra headroom for peak load, latency variance, slow queries, long transactions, and other workloads. If a connection is held for 200 ms instead of 40 ms, the same throughput requires significantly higher average concurrency.

The key metric to measure is how long the connection is actually borrowed, not just Java CPU time. Queries waiting on locks, transactions waiting on external operations, or long result streams can hold connections for a long time.

## 8. Choosing concurrency for each flow type

Do not use a single concurrency value for every query. Different use cases have different characteristics:

| Work type | Typically suitable control approach |
|---|---|
| Read one record by ID | A single repository call; no fan-out needed |
| Read multiple independent IDs in one request | `flatMap(..., concurrency)` or batched `IN` queries |
| Write interdependent records | `concatMap` or sequential chaining |
| Large batch processing | Chunk into batches, `concatMap` or bounded `flatMap` |
| Queries inside the same reactive transaction | Prefer sequential if sharing a connection; check driver capability before running concurrently |
| Potentially long-running background tasks | Separate bulkhead/worker concurrency; do not share an unbounded budget with HTTP |
| CPU work after reading data | Separate CPU processing from database operations; pick the right scheduler and do not hold connections long |

### 8.1. Prefer grouped queries over per-ID fan-out

If you need to fetch records for multiple IDs, a `WHERE id IN (...)` query is usually better than calling the repository once per ID:

```java
return customerRepository.findByIdIn(customerIds);
```

This reduces connection acquisitions and SQL statements. For large ID sets, split into batches to avoid bind-parameter limits and oversized statements.

### 8.2. Limiting concurrency for batches

```java
return Flux.fromIterable(customerIds)
        .buffer(200)
        .concatMap(customerRepository::findByIdIn);
```

This example splits IDs into batches of 200 and queries sequentially. If parallel processing is needed, you can use:

```java
return Flux.fromIterable(customerIds)
        .buffer(200)
        .flatMap(customerRepository::findByIdIn, 3);
```

Within a single subscription, at most 3 batch queries are active concurrently. The numbers 200 and 3 are only examples; pick values based on parameter limits, result sizes, and pool budget.

### 8.3. Writing data in order

If multiple write operations depend on order, use `concatMap`:

```java
return Flux.fromIterable(events)
        .concatMap(event -> repository.save(toEntity(event)));
```

If write operations are independent, `flatMap` with bounded concurrency can be used, but consider unique constraints, transactions, event emission order, and retryability. Do not raise write concurrency just to go faster if the database is experiencing lock contention.

## 9. Reactive transactions and the connection pool

A reactive transaction typically binds one connection to the Reactor Context for the duration of the transaction. This means multiple repository calls within the same transaction usually share the same connection, rather than each inner publisher borrowing an independent connection.

### 9.1. Do not assume parallel queries inside a transaction

Example:

```java
@Transactional
public Flux<OrderLineEntity> loadAndProcess(List<Long> orderIds) {
    return Flux.fromIterable(orderIds)
            .flatMap(orderLineRepository::findByOrderId, 8);
}
```

The code specifies a fan-out concurrency of 8, but the operations may share the single connection bound to the transaction. Many R2DBC drivers do not support executing multiple statements concurrently on the same connection in the way `flatMap` triggers them. The result can be driver errors, internal queuing, or unexpected behavior.

Inside a transaction sharing a connection, if operations need to execute sequentially, use:

```java
@Transactional
public Flux<OrderLineEntity> loadAndProcess(List<Long> orderIds) {
    return Flux.fromIterable(orderIds)
            .concatMap(orderLineRepository::findByOrderId);
}
```

If parallel execution is needed, consider a single grouped query or splitting the work into independent transactions with explicit limits. Do not open multiple separate subscriptions inside a transaction to bypass connection limits.

### 9.2. Keep transactions short

A connection is normally held for the entire duration of the transaction. Avoid:

- Calling external HTTP services while a database transaction is open.
- Waiting on user input or waiting for messages inside a transaction.
- Performing long CPU computations before committing.
- Keeping a transaction open while streaming unbounded data to a client.

Execute required database operations in a short transaction, then handle independent processing outside the transaction when consistency rules permit.

### 9.3. A pipeline with multiple independent transactions

If batches are processed in separate transactions, each batch can borrow a different connection. In that case, `flatMap` concurrency must fit within the pool budget and the task's bulkhead. Clarify atomicity requirements: if the third batch fails after the first two commit, can the system tolerate a partial processing state or does it require a single larger transaction?

## 10. Backpressure, prefetch, and non-interchangeable operators

Backpressure lets a subscriber regulate how much data it requests from a publisher. However, not every demand-throttling operator directly limits the number of active database queries.

### 10.1. `limitRate`

`limitRate` adjusts how a subscriber requests data from upstream in chunks. It is helpful for regulating demand, but it does not replace `flatMap` concurrency when each source element produces a query publisher.

Example:

```java
Flux.fromIterable(ids)
        .limitRate(32)
        .flatMap(repository::findById);
```

`limitRate(32)` should not be read as guaranteeing at most 32 concurrent running queries. Place an explicit limit on `flatMap`:

```java
Flux.fromIterable(ids)
        .flatMap(repository::findById, 8);
```

### 10.2. `publishOn` and `subscribeOn`

`publishOn` and `subscribeOn` control which scheduler executes part of a pipeline or initializes a subscription. They are not mechanisms for limiting database connections. Moving a pipeline to another scheduler does not give the pool more connections and does not make slow queries disappear.

R2DBC drivers perform I/O reactively; you do not need to move every repository call onto `boundedElastic` like you typically do to isolate blocking JDBC. If a blocking library is present, isolate only that blocking section and do not hold a database connection while waiting.

### 10.3. `parallel()` is not a pool limit

`parallel(n)` splits a stream into rails for parallel processing, typically paired with `runOn`. It is better suited for certain CPU-bound tasks. Using `parallel()` to call the database does not automatically manage the connection budget; if each rail calls a repository, you still need explicit concurrency limits and budgeting.

## 11. Handling pool saturation and timeouts

When the pool runs out of available connections, new operations wait to acquire one. If they wait longer than allowed, the publisher emits an acquire timeout error. This is a signal to observe and adjust load, not something to retry infinitely.

### 11.1. Distinguishing types of time spent

A request can experience:

1. Time waiting for permission to start work (admission/bulkhead).
2. Time waiting for a connection from the pool.
3. Time the database spends executing the query.
4. Time the application spends mapping results and building the response.

If you only set a query timeout without bounding acquire time, a request can still wait too long on the pool before the query even begins. Configure both an overall deadline and appropriate component timeouts.

### 11.2. Do not retry acquire timeouts infinitely

Retries can worsen overload because each failed request generates yet another acquire attempt. If retries are used, cap the retry count, use backoff with jitter, distinguish transient errors from configuration errors, and ensure operations can be safely retried.

### 11.3. Shed load when limits are exceeded

A bulkhead can reject new work once allowed concurrency is reached instead of letting every request queue up. The API layer can map overload to an appropriate response such as `503 Service Unavailable` or a contract-defined resource-limit error. Choose between queuing and rejecting based on the latency budget and workload type.

## 12. Monitoring connection pool usage

To choose concurrency with evidence, monitor the following metrics:

| Metric | What to observe |
|---|---|
| Allocated/active connections | Number of connections currently borrowed |
| Idle connections | Number of connections ready for reuse |
| Pending acquire | Number of operations waiting for a connection |
| Acquire latency | Time from request until a connection is received |
| Acquire timeout count | Number of times a connection could not be obtained before the deadline |
| Connection creation time | Time taken to establish a new connection |
| Query latency | Execution time per query group |
| Transaction duration | How long connections are held within transactions |
| Database CPU/lock/I/O | Processing capacity and bottlenecks on the database side |

Exact metrics and metric names depend on your R2DBC Pool, Spring Boot, and Micrometer versions. Observability setup must be verified in a real running environment.

### 12.1. Signs concurrency needs to be lowered

- Pending acquires climb steadily.
- Acquire latency increases even though query latency has not increased proportionally.
- Acquire timeouts appear during peak hours.
- Active connections stay pinned near `max-size`.
- Database CPU or lock waits increase when concurrent query count increases.
- Throughput stops growing despite higher concurrency, while latency rises.

### 12.2. Signs concurrency can be raised

- The pool has plenty of idle connections.
- Pending acquires are near zero.
- The database still has spare CPU/I/O headroom.
- Queries are independent, connection hold times are short, and latency is stable.
- Load testing shows raising concurrency increases throughput without significantly hurting tail latency.

Do not tune the pool based on a single metric. Combine application, pool, and database metrics to identify where the bottleneck lies.

## 13. Example choosing concurrency from a pool budget

Suppose one instance has a pool `max-size = 30`. The application also runs other flows such as health checks, single-item reads, background workers, and admin tasks. Batch processing should not by default consume all 30 connections.

An illustrative allocation:

| Workload group | Illustrative concurrency budget |
|---|---:|
| Regular requests | 12 |
| Grouped batch reads | 8 |
| Background workers | 4 |
| Headroom/load spikes | 6 |
| **Total** | **30** |

This is not a universal optimal configuration. It merely illustrates that different flows share the pool and need budgets. If 10 batch requests run at once, each using concurrency 8, the batch group can generate demand for 80 operations; a per-request limit of 8 does not guarantee total batch demand stays at 8 connections.

If batches are a heavy workload, use a bulkhead limiting total concurrent batches per instance—for example, at most 2 concurrent batches with at most 4 concurrent queries each. Leave the rest of the pool for regular traffic. Actual numbers must be tuned using load tests and metrics.

## 14. Testing concurrency and the pool

Unit tests can verify that a pipeline uses the desired operators and limits, but they are not sufficient to conclude the pool behaves properly under load. Run integration/load tests against a database and driver close to production.

### 14.1. Checking concurrency in a pipeline

You can use mock publishers with an active-inner-publisher counter to verify `flatMap` does not exceed the configured concurrency. This test verifies Reactor behavior, not connection pool behavior.

### 14.2. Testing pool saturation

With a small pool size in a test environment, run multiple controlled slow operations to verify:

- Active connections never exceed `max-size`.
- Excess operations wait to acquire.
- Acquire timeout triggers when exceeding the configured limit.
- Connections return to the pool when a publisher completes or errors.
- Cancelling a subscription does not leave connections held unintentionally.

Do not generate excessive load on a shared or production database just for experimentation. Use a dedicated test database/container with explicit limits.

### 14.3. Load testing concurrent requests

Simulate many requests concurrently executing a fan-out flow. Measure throughput, p50/p95/p99 latency, active/idle/pending connections, acquire timeouts, and database CPU/I/O. Adjust one parameter at a time: per-request concurrency, bulkhead, pool `max-size`, or batch size.

### 14.4. Testing transactions

If the flow uses `@Transactional`, verify that repository calls share the transaction context as intended. Check whether the driver supports concurrent operations on the same connection; if not, use `concatMap` or a single grouped query. Verify rollback when a step emits an error.

## 15. Common mistakes

### Using unbounded flatMap on large lists

Each element can spawn a separate query, causing many publishers to wait on the pool simultaneously. Set concurrency explicitly or switch to an `IN`/batch query.

### Mistaking flatMap concurrency for an application-wide limit

The limit only applies to a single subscription at that operator. Multiple requests multiply total concurrency. Use a bulkhead/admission control if per-instance or per-workload totals must be capped.

### Increasing max-size to fix every queue

A larger pool can overload the database. Check query latency, CPU, lock waits, and the connection budget before raising it.

### Using limitRate instead of flatMap concurrency

`limitRate` throttles upstream demand, not directly the number of active inner database query publishers. Set concurrency on `flatMap`.

### Using parallel() to speed up queries

Parallel rails are not a pool management mechanism. Use I/O-appropriate operators and bound the number of active queries.

### Running multiple concurrent queries inside the same transaction

Operations may share one connection bound to the transaction context. The driver may not support concurrent statements on that connection. Prefer sequential execution or verify driver capabilities explicitly.

### Holding a transaction while calling external services

The connection is held longer, reducing available connections for other requests. Keep transactions short and move independent processing outside when business rules allow.

### Retrying infinitely on acquire timeout

Unbounded retries add load and can worsen pool saturation. Use deadlines, bounded retries, and controlled backoff.

### Monitoring only active connection count

High active connections can be normal if queries are fast and throughput is healthy. Also inspect pending acquires, acquire latency, query latency, and database load.

## 16. Process for choosing concurrency levels

1. Determine how many queries each request generates and how long on average a query holds a connection.
2. Locate fan-out points in the pipeline, especially `flatMap` calling a Repository or `DatabaseClient`.
3. Choose `concatMap` if sequential execution is required; use `flatMap`/`flatMapSequential` with finite concurrency for independent queries.
4. Prefer a grouped or batch query instead of hitting the database per ID.
5. Determine pool `max-size` and connection budget across total instances and other clients.
6. Reserve headroom for regular requests, background workers, admin tasks, and load spikes.
7. Use a bulkhead if you need to cap total work for a workload on each instance.
8. Configure acquire timeouts and deadlines within the latency budget.
9. With reactive transactions, verify connection sharing and avoid concurrent statements if the driver does not support them.
10. Monitor active/idle/pending connections, acquire latency, timeouts, query latency, and database resources.
11. Load test with multiple concurrent requests, changing one parameter at a time.
12. Pick the concurrency level where throughput remains strong while latency and pool pending counts stay within acceptable thresholds.

## 17. Takeaways checklist

- [ ] Every `flatMap` fanning out to the database has an appropriate concurrency limit.
- [ ] `concatMap` is used when operations must be sequential or share a transaction connection.
- [ ] `flatMapSequential` is used when concurrent execution is desired while preserving result order.
- [ ] Concurrency within a single subscription is not treated as an application-wide limit.
- [ ] Bulkhead/admission control is used for workloads requiring per-instance total limits.
- [ ] Pool `max-size` fits within the system-wide connection budget.
- [ ] Budgeting accounts for maximum instance count and other database clients.
- [ ] Acquire timeout aligns with the request deadline.
- [ ] Pool size is not raised merely to mask slow queries or excessive fan-out.
- [ ] Grouped/batch queries are preferred where suitable.
- [ ] `limitRate`, `publishOn`, `subscribeOn`, or `parallel()` are not used as substitutes for query concurrency limits.
- [ ] Reactive transactions are kept short and do not issue concurrent statements beyond driver capabilities.
- [ ] Metrics exist for active, idle, pending connections, acquire latency, and timeouts.
- [ ] Load tests have been run with concurrent requests while monitoring database resources.

Concurrency in Spring Data R2DBC must be tuned from inside the pipeline out to the connection pool and database. Limiting `flatMap` keeps one flow from spawning too many inner operations; bulkheads control total workload pressure per instance; `max-size` caps connections; and metrics plus load tests show where the system reaches equilibrium. When these limits are planned together, the application can benefit from reactive I/O without turning the connection pool into an overloaded queue.
