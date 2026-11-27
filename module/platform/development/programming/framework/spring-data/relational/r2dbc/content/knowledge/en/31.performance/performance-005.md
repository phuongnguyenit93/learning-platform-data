# Optimizing Concurrency Alongside Pool Sizing

## 1. Two Limits That Must Be Coordinated

In a Spring Data R2DBC application, reactive pipeline concurrency and connection pool size are closely linked, yet they are two distinct configurations.

- **Pipeline concurrency** governs how many publishers or operations are allowed to run simultaneously within a processing stream. Reactor controls this via operators such as `flatMap`, `flatMapSequential`, and `concatMap`.
- **Connection pool size** governs the maximum number of R2DBC connections that can be borrowed concurrently from a single application instance's pool.

For example, a flow using `flatMap` with concurrency 50 can attempt to run up to 50 repository operations simultaneously. If the pool only has 10 connections, some operations must wait for connections to be returned. Conversely, a pool of 50 connections does not mean every pipeline should launch 50 parallel operations.

Performance tuning requires answering three questions together:

1. How many simultaneous operations can the database handle while maintaining stable latency?
2. How many concurrent database operations can the application generate across requests, batches, and background jobs?
3. How many connections does the pool need to serve that load without exhausting the database's connection budget?

R2DBC avoids tying up a blocking thread per operation while waiting on database I/O. That does not give the database infinite capacity to process concurrent queries. The database still has CPU, I/O, lock, memory, connection, and throughput limits.

## 2. Flow from Reactor to the Connection Pool

When a repository publisher is subscribed to, an operation needing a connection borrows one from the `ConnectionFactory`. If the application uses a connection pool, the request goes to the pool:

~~~text
HTTP requests / background jobs
              |
              v
       Reactive pipelines
              |
       flatMap concurrency
              |
              v
       Repository / Template
              |
              v
       R2DBC ConnectionFactory
              |
              v
        Connection pool
         /           \
        v             v
   Connection      Acquire queue
   available       wait for release
        |
        v
    R2DBC driver
        |
        v
      Database
~~~

Several scenarios:

- If a free connection exists, the operation borrows it and proceeds.
- If the pool has reached `max-size`, new requests wait for a connection to be released or time out.
- If operations hold connections for a long time, other operations wait longer.
- If the pool is sized too large, the database may suffer excessive concurrent sessions and rising latency.
- If pipeline concurrency is too high, the pool's acquire queue can grow even though physical connection count stays constant.

Therefore, raising `flatMap` concurrency and `max-size` together does not always improve throughput. First measure whether the bottleneck sits in the application, the pool, or the database.

## 3. Reactor Concurrency Controls Active Publishers

On a `Flux`, the `flatMap` operator accepts a concurrency parameter limiting how many inner publishers are subscribed to simultaneously.

Example:

~~~java
Flux<Order> savedOrders =
        Flux.fromIterable(commands)
                .flatMap(
                        command -> orderRepository.save(toOrder(command)),
                        8
                );
~~~

In this example, Reactor allows at most 8 inner publishers from the source `Flux` to be subscribed to concurrently. If each inner publisher performs an R2DBC write, at most 8 of those operations are active concurrently within this subscription.

Concurrency is not a thread count. R2DBC uses asynchronous I/O; many operations can await database responses without dedicating a blocked thread to each one.

### 3.1. flatMap, flatMapSequential, and concatMap

| Operator | Processing Behavior | When Suitable |
|---|---|---|
| `flatMap(mapper, concurrency)` | Subscribes to multiple inner publishers concurrently; results may emit in completion order | Independent operations without output ordering requirements |
| `flatMapSequential(mapper, concurrency)` | Runs concurrently but emits results in source order | Output ordering must match input while still running in parallel |
| `concatMap(mapper)` | Waits for the current inner publisher to complete before starting the next | Operations must be serialized or side-effect ordering must be preserved |

Sequential example:

~~~java
Flux<Void> updates =
        Flux.fromIterable(commands)
                .concatMap(command ->
                        customerRepository.save(toCustomer(command))
                                .then()
                );
~~~

Bounded-parallel example:

~~~java
Flux<Customer> updates =
        Flux.fromIterable(commands)
                .flatMap(
                        command -> customerRepository.save(toCustomer(command)),
                        6
                );
~~~

Do not use high concurrency when operations depend on each other. If you must obtain the ID of a prior record to create the next record, chain them sequentially with `flatMap` or `then` instead of launching two independent operations in parallel.

### 3.2. Concurrency and Prefetch Are Different Parameters

Some operators accept both concurrency and prefetch:

~~~java
Flux<Customer> saved =
        commands.flatMap(
                command -> customerRepository.save(toCustomer(command)),
                8,
                1
        );
~~~

- `concurrency` caps how many inner publishers are subscribed to simultaneously.
- `prefetch` controls how many items are requested upfront from each inner publisher in operators supporting that parameter.

Prefetch is neither connection pool size nor thread count. Raising prefetch can increase buffered items held in the pipeline, without adding database capacity.

On `Mono`, `flatMap` typically chains a single dependent publisher and has no concurrency parameter like `Flux`. Limiting multiple independent operations is normally applied to the source `Flux`.

## 4. flatMap Concurrency Is Usually a Per-Subscription Limit

This is a frequent cause of accidental overload. The concurrency argument passed to `flatMap` applies to a single subscription of that pipeline—it does not globally cap the entire application.

Suppose each request executes:

~~~java
return Flux.fromIterable(request.items())
        .flatMap(item -> repository.save(toEntity(item)), 10)
        .then();
~~~

One request can have up to 10 active inner publishers. If 20 concurrent requests run the pipeline simultaneously, potential concurrent database operations can reach roughly 200, depending on timing and publisher lifetimes.

A simple estimation formula:

~~~text
Total active inner operations
    <= active subscriptions
       × concurrency per subscription
~~~

This is an upper bound on potential load, not a guarantee that all are always active simultaneously. The source publisher may emit slowly, requests may finish early, or some steps may not need a connection.

If you look at `flatMap(..., 10)` and assume the application executes at most 10 queries at a time, you will underestimate load when multiple requests or background jobs run concurrently.

### 4.1. The Pool Is a Final Resource Limit, Not a Complete Admission Control Policy

Pool `max-size` limits concurrent connections borrowed from the pool. When connections run out, new requests wait in the acquire queue. While this stops the pool from opening unbounded connections, an overly long queue still raises request latency and causes timeouts.

Place limits at the load-producing layer where appropriate:

- Cap concurrent items processed within a batch.
- Cap background worker concurrency.
- Bound requests or workloads using bulkheads or rate limiters.
- Set explicit deadlines and timeouts for operations.
- Apply backpressure or shed excess load according to application policy.

Do not let thousands of publishers queue against the pool for long periods and mistake that for scalability. A giant queue simply turns overload into latency and memory pressure.

## 5. Connection Pool in R2DBC

The R2DBC SPI defines `ConnectionFactory` for creating connections. A connection pool manages reusable connections to avoid repeated connection establishment costs and limit open sessions to the database.

In the R2DBC ecosystem, `r2dbc-pool` is the common pooling implementation. Spring Boot can configure pooling via properties when the pool dependency is on the classpath.

Example Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-pool'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Replace the driver dependency with the one matching your database. Manage versions compatibly with Spring Boot and the R2DBC SPI.

### 5.1. Configuring the Pool via application.yml

Example starting configuration:

~~~yaml
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
      max-idle-time: 10m
      max-life-time: 30m
~~~

Meanings of common properties:

| Property | Meaning |
|---|---|
| `enabled` | Enables connection pool configuration |
| `initial-size` | Initial connections created as supported by pool configuration |
| `max-size` | Maximum connections maintained in the pool |
| `max-acquire-time` | Maximum wait time to borrow a connection |
| `max-idle-time` | Duration a connection can stay idle before eviction per pool policy |
| `max-life-time` | Maximum lifetime of a connection per pool policy |

Exact property names and binding behavior depend on the Spring Boot and R2DBC pool versions. Check your project's dependency management and version documentation before deploying. Never copy configuration verbatim from another version without verifying property support.

Additional `r2dbc-pool` properties may cover connection creation timeout, validation depth, validation query, and eviction intervals. Enable them only for specific operational goals.

### 5.2. initial-size Is Not max-size

`initial-size` is how many connections the pool tries to create initially as configured. `max-size` is the upper cap the pool can maintain or allocate under pool semantics.

Do not set `initial-size` equal to `max-size` solely to pre-warm everything immediately. Opening too many connections upfront can cause connection storms when multiple replicas boot together. For light workloads or scale-to-zero environments, a lower `initial-size` reduces startup overhead.

### 5.3. A Pool Is Not a Query Result Cache

Connection pools reuse connections; they do not cache `SELECT` results. Every cold subscription to a repository can still execute a fresh SQL query. Pools manage connection lifecycles and establishment overhead—they do not collapse repeated queries into one.

## 6. Calculating the System-Wide Connection Budget

You cannot choose `max-size` by looking at a single application instance. The database enforces a total connection limit shared across many consumers:

- Replicas of the R2DBC application.
- Workers and background services.
- Migration tools.
- Monitoring and health checks.
- Administrative tools.
- Other applications or services sharing the database.

A budgeting formula:

~~~text
Budget for R2DBC application
    = database max_connections
      - reserved for admin
      - other services
      - migrations/monitoring
      - safety margin
~~~

Then allocate across the maximum replica count:

~~~text
max-size per instance
    <= budget for application
       / maximum number of replicas
~~~

Illustrative example:

| Component | Connections |
|---|---:|
| Database `max_connections` | 200 |
| Reserved for admin/monitoring | 15 |
| Other services | 55 |
| Migrations and operational jobs | 10 |
| Safety margin | 20 |
| Remaining for R2DBC application | 100 |

If the deployment can scale up to 5 replicas, the theoretical per-instance budget averages 20 connections. A `max-size` of 20 is then a starting point for load testing—not proof that the database handles 100 active connections gracefully.

Calculate using the maximum replica count, including rolling deployments that temporarily run both old and new versions. If autoscaling scales replicas from 5 to 10 with the same pool `max-size`, total potential connections double.

### 6.1. Do Not Allocate All of max_connections to Application Pools

Databases need spare connections for administration, monitoring, backups, migrations, and other clients. If the application consumes every slot, operational tasks or other services may fail to connect.

Reserve a safety margin. The exact reserve depends on your system and load; there is no single universal percentage for all databases.

### 6.2. Multiple Pools Within the Same Application

If an application configures multiple `ConnectionFactory` instances, each pool has its own `max-size`. Total potential connections equal the sum of `max-size` across all pools on all replicas.

For instance, suppose each instance has a `customer` pool (`max-size` 15) and an `order` pool (`max-size` 20). Across 4 replicas, total potential connections are:

~~~text
4 × (15 + 20) = 140 connections
~~~

Do not check only the primary pool in `application.yml`. Inventory every `ConnectionFactory` and pool created in application configuration.

## 7. Using Little’s Law to Estimate In-Flight Operations

Little’s Law relates throughput, time in the system, and average concurrent work in progress:

~~~text
L = λ × W
~~~

Where:

- `L`: average number of operations in the system.
- `λ`: throughput, operations per second.
- `W`: average time an operation spends in the system, in seconds.

For example, if the application runs 300 database operations per second and average connection hold time is 40 ms:

~~~text
L = 300 × 0.040 = 12
~~~

On average, roughly 12 operations are holding connections. This is a steady-state average estimate based on measured workload and duration—not a rule to set pool size to 12 in all situations.

If connections are held in a 250 ms transaction instead of 40 ms:

~~~text
L = 300 × 0.250 = 75
~~~

At the same throughput, longer transactions raise average connection demand sharply. That is why shortening connection hold time is often far more effective than simply enlarging the pool.

### 7.1. Use Actual Connection Hold Time

Query times shown in SQL logs do not always equal how long a connection is held. A connection can remain held across:

- An entire reactive transaction.
- Consuming a multi-row `Flux`.
- Callbacks or mapping inside the data-access lifecycle.
- Application steps between two queries in the same transaction.
- Waiting for a downstream publisher to complete before the transaction closes.

Measure connection acquire/release and transaction duration whenever possible. Plugging pure SQL execution time into `L` when transactions hold connections longer underestimates connection demand.

### 7.2. Little’s Law Does Not Predict Bursts or p99

The formula relies on steady-state averages. It cannot tell you how many connections a pool needs during bursts, tail latency spikes, lock contention, or sudden traffic surges.

Use it for initial sizing, then validate with load tests and metrics. Never treat steady-state averages as hard production ceilings.

## 8. Databases Do Not Automatically Run Faster with More Connections

Every concurrent connection consumes database resources:

- Backend/session memory.
- CPU for parsing, planning, and executing queries.
- Buffer/cache pressure.
- I/O and locks.
- Scheduling and context switching.
- Memory for sorts, hash joins, or transactions.
- Transaction and snapshot management overhead.

Once concurrency exceeds useful processing capacity, the database enters contention. Throughput plateaus or drops while p95/p99 latency climbs.

A larger pool merely raises how many connections can be borrowed. It does not add database CPU, IOPS, memory, or lock throughput.

Three regions can be observed:

~~~text
Throughput
   ^
   |                 _________
   |              __/
   |           __/
   |        __/
   |     __/
   |  __/
   +--------------------------------> concurrency
       useful gain    saturation / contention
~~~

Initially, higher concurrency helps utilize database capacity. Eventually throughput nears its ceiling. Beyond that point, extra concurrency mostly inflates queues and latency.

Saturation points must be measured under realistic workloads. They depend on queries, indexes, data, hardware, database version, and competing workloads sharing the database.

## 9. Choosing Concurrency per Workload Type

Not all queries have equal cost. A primary-key `SELECT` is much lighter than a multi-table join with sorting and aggregation. A batch update holds locks longer than a brief read.

Workloads can be categorized as:

| Workload | Tuning Direction |
|---|---|
| Primary-key lookup | Can permit higher concurrency after measuring |
| Heavy join/aggregate query | Lower concurrency to protect database CPU and memory |
| Bulk writes | Bounded batches; avoid many transactions modifying the same rows |
| Background polling | Limit concurrency and frequency |
| Long streaming `Flux` | Cap concurrent streams; avoid holding connections too long |
| Multi-step transactions | Match concurrent transactions to connection hold times |
| Import/export jobs | Batch with throttling and checkpoints |

Do not set one global `flatMap` concurrency across the entire application assuming all queries cost the same. Bound concurrency by workload and business priority.

## 10. Tuning Concurrency in Batches

Batch jobs processing many records commonly need explicit concurrency limits.

Example:

~~~java
public Flux<Customer> importCustomers(Flux<CustomerInput> inputs) {
    return inputs.flatMap(
            input -> customerRepository.save(toCustomer(input)),
            8
    );
}
~~~

At most 8 saves from this subscription execute concurrently. The value 8 is only an example; measure against your database, schema, and batch size.

When sequential execution is required:

~~~java
public Flux<Customer> importCustomers(Flux<CustomerInput> inputs) {
    return inputs.concatMap(input ->
            customerRepository.save(toCustomer(input))
    );
}
~~~

When grouping into batches before writing:

~~~java
public Flux<Customer> importCustomers(Flux<CustomerInput> inputs) {
    return inputs.buffer(100)
            .concatMap(batch ->
                    customerRepository.saveAll(
                            batch.stream()
                                    .map(this::toCustomer)
                                    .toList()
                    )
            );
}
~~~

`buffer(100)` groups up to 100 inputs per chunk before calling `saveAll`. This bounds how much data enters each processing step.

Note: `saveAll` does not necessarily issue a single SQL bulk insert. Repository implementations and drivers may execute individual statements. When true SQL batching is needed, inspect the generated SQL or use a database-appropriate API.

### 10.1. Tune Batch Size and Concurrency Independently

Batch size controls how many items are grouped together. Concurrency controls how many inner publishers or batches run simultaneously.

With batch size 100 and concurrency 5, the pipeline can hold multiple batches in flight simultaneously, raising both memory usage and potential database operations.

Do not raise both parameters at once without measuring. Start with a moderate batch size and low concurrency, then adjust one factor at a time while monitoring throughput, memory, pool wait, and database latency.

### 10.2. Backpressure Does Not Replace Global Limits

Reactor supports demand/backpressure so subscribers request data at their consumption pace. However, backpressure does not automatically enforce a global limit across all concurrent requests in the application.

One input `Flux` can be throttled within its subscription, yet multiple independent subscriptions can still run concurrently. Add admission limits or bulkheads at the application layer when combined workloads can overwhelm database capacity.

## 11. Transactions Change How Connections Are Used

In reactive transactions, Spring typically binds a connection to the Reactor Context for the active transaction. Participating R2DBC operations reuse that transaction-bound connection.

This has two consequences:

1. A transaction normally holds the connection from start until commit or rollback completes.
2. Concurrent operations inside the same transaction can contend for the same connection.

Not all R2DBC drivers or connections support concurrent statements on a single connection. Therefore, avoid assuming high `flatMap` concurrency inside a transaction creates multiple separate connections within the same transaction.

Sequential dependent steps in one transaction:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(saved ->
                    orderLineRepository.saveAll(toLines(saved.id(), command))
                            .thenReturn(saved)
            )
            .flatMap(saved ->
                    inventoryRepository.reserve(command.items())
                            .thenReturn(saved)
            );
}
~~~

Dependent steps are chained sequentially with `flatMap`/`then`. They can participate in the same transaction and bound connection.

### 11.1. Avoid External Service Calls Inside Long Transactions

Do not keep a transaction open while waiting on HTTP calls, emails, or user responses. Connections stay pinned even while the database executes no queries, rapidly exhausting the pool under load.

Example to avoid:

~~~java
@Transactional
public Mono<Order> placeOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentClient.authorize(order)
                            .thenReturn(order)
            )
            .flatMap(order ->
                    orderRepository.markPaid(order.id())
                            .thenReturn(order)
            );
}
~~~

If `paymentClient` takes several seconds, the transaction holds the connection and locks throughout that wait. Better designs use state machines, sagas, or an outbox depending on business requirements, keeping database transactions short.

### 11.2. Do Not Arbitrarily Parallelize Queries on One Transaction Connection

If two queries belong to the same transaction and the driver does not support concurrent statements on one connection, chain them sequentially:

~~~java
return customerRepository.findById(customerId)
        .flatMap(customer ->
                addressRepository.findByCustomerId(customer.id())
                        .collectList()
                        .map(addresses ->
                                new CustomerProfile(customer, addresses)
                        )
        );
~~~

Run queries in parallel inside one transaction only after confirming the driver, connection, and Spring transaction integration support it. If queries need separate connections, they cannot automatically share a single atomic transaction merely by running inside `flatMap`.

## 12. Streaming and Connection Hold Time

A database `Flux` can hold a connection while the driver reads the result set and the subscriber consumes items. If downstream processing is slow, the connection stays held longer than expected.

Example:

~~~java
return customerRepository.findAll()
        .map(this::toExportRow)
        .flatMap(exportService::writeRow, 4);
~~~

If `exportService` writes files or calls slow external services, the pipeline stretches out `Flux` consumption. Verify whether the connection remains pinned throughout processing for your publisher and driver.

Ways to relieve pressure:

- Use pagination or keyset pagination for large datasets.
- Split reading and processing into discrete batches.
- Avoid long-lived streaming `Flux` exports that hold connections indefinitely.
- Cap concurrent exports.
- Never make blocking calls inside `map`/`flatMap`.
- Ensure subscribers can cancel promptly when data is no longer needed.
- Measure stream duration and connection hold time.

Do not call `collectList()` on unbounded datasets simply to close the connection early. `collectList()` loads all rows into heap and causes memory pressure. Choose pagination or batching matched to data scale.

## 13. Configuring Timeouts for Pool and Queries

Timeouts at different layers address different failure modes:

| Timeout | What It Bounds |
|---|---|
| Connection acquire timeout | Wait time to borrow a connection from the pool |
| Connection creation timeout | Time to establish a new connection |
| Query/statement timeout | SQL execution time as supported by driver/database |
| Transaction timeout | Transaction duration per transaction manager |
| HTTP/request deadline | Total time a request is allowed to execute |
| Retry backoff | Wait interval before retrying |

A short acquire timeout exposes pool saturation early, though setting it too tight may reject valid requests during brief spikes when the database still has capacity.

An overly long acquire timeout leaves requests waiting and ties up upstream resources. Set it shorter than and aligned with the request deadline and business latency budget.

Do not confuse connection acquire timeout with query timeout. A request can obtain a connection fast while the query stalls on a lock. Conversely, a query can be fast while the request spent too long waiting on the pool beforehand.

## 14. Setting Pool max-size Too Low or Too High

### 14.1. Pool Too Small

Symptoms:

- Requests wait for connections even though the database has spare capacity.
- Pool pending acquires climb.
- Acquire latency increases.
- Acquire timeouts occur.
- Active database sessions stay low relative to available capacity.
- Throughput is capped by the pool.

Remediation:

- Inspect connection hold times.
- Check for long transactions or long-lived streams.
- Determine whether queries are slow or the pool simply lacks connections.
- Increase `max-size` incrementally if the database has headroom.
- Adjust workload concurrency to prevent oversized queues.

Do not enlarge the pool if the real cause is slow queries or transactions holding connections too long.

### 14.2. Pool Too Large

Symptoms:

- Too many active database sessions.
- Database CPU or I/O jumps sharply as concurrency rises.
- p95/p99 latency degrades.
- Lock waits, deadlocks, or context switching increase.
- Throughput stops climbing despite more connections.
- Other services experience connection starvation.

Remediation:

- Reduce `max-size` or workload concurrency.
- Optimize queries and indexes.
- Shorten transaction durations.
- Break large batches into smaller chunks.
- Throttle background jobs.
- Review replica counts and system-wide connection totals.

A larger pool is not a universal fix for throughput. Sometimes lowering concurrency lets the database finish each query faster, raising overall throughput.

## 15. Measure Metrics Before Making Changes

To tune with evidence, monitor both application and database layers.

### 15.1. Connection Pool Metrics

Depending on pool version and metrics system, observe:

- Allocated/created connections.
- Acquired/in-use connections.
- Idle connections.
- Pending acquire requests.
- Average and percentile acquire times.
- Acquire timeout count.
- Disposed/evicted connections.
- Connection creation time.

If pool usage continuously hugs `max-size` and pending acquires grow, the application may be pool-constrained. However, if the database is already saturated, enlarging the pool will only worsen contention.

### 15.2. Database Metrics

Monitor:

- Active sessions and connection counts.
- Query latency p50/p95/p99.
- Query/transaction throughput.
- CPU and memory.
- Disk I/O and buffer/cache hit rates.
- Lock waits and deadlocks.
- Slow queries.
- Replication lag if replicas exist.
- Transaction duration and idle-in-transaction sessions.

Correlate these metrics over the exact same time window as pool metrics. Never diagnose from a connection-count chart alone.

### 15.3. Application Metrics

Track:

- Request concurrency and request rate.
- Average database operations per request.
- Background job concurrency.
- Processing time per publisher.
- Error and timeout rates.
- Pipeline queues and backlogs.
- Memory and GC.
- Running replica count and autoscaling events.

Changing `max-size` affects a single-SELECT request differently than a request fanning out into 20 queries.

## 16. Controlled Tuning Process

A practical workflow:

1. Measure a baseline on a representative workload.
2. Record request rate, query throughput, connection usage, and p95/p99 latency.
3. Determine whether the pool is the bottleneck or the database is saturated.
4. Inspect connection hold times, transactions, and streams.
5. Choose workload-appropriate concurrency limits.
6. Choose `max-size` within the system-wide connection budget.
7. Adjust one parameter at a time.
8. Re-run the exact same workload and dataset.
9. Compare throughput, latency, pending acquires, DB CPU, and lock waits.
10. Verify behavior at maximum replica count and during rolling deployments.
11. Pick a balanced operating point rather than chasing a brief peak throughput spike.
12. Monitor post-deployment and ensure configuration can be rolled back.

Do not tune using a quick test of a few requests. Run load long enough for pools to stabilize, database statistics to reflect activity, and lock/cache patterns to emerge.

## 17. Example: Reading Load Test Results

Suppose three configurations are measured on the same database and workload:

| Pool max-size | Throughput | p95 latency | Pending acquire | DB CPU |
|---:|---:|---:|---:|---:|
| 10 | 700 ops/s | 180 ms | High | 45% |
| 20 | 1,050 ops/s | 150 ms | Low | 65% |
| 40 | 1,080 ops/s | 310 ms | Low | 95% |

These are hypothetical numbers illustrating how to interpret results.

- Raising `max-size` from 10 to 20 increases throughput and drops pending acquires.
- Raising from 20 to 40 barely increases throughput.
- p95 latency and DB CPU jump sharply at pool 40, indicating the database is likely saturating.

In this illustrative scenario, pool 20 appears better balanced than pool 40. Still inspect workload details, concurrency, replica count, other services, and tail latency before finalizing production settings.

Do not pick pool 40 just because it permits more connections. The target is stable throughput with acceptable latency and resource headroom.

## 18. Global Limits for Background Workers

A background worker may read from a job queue and write to the database. If each worker instance uses `flatMap` concurrency 20 across 10 replicas, potential concurrent operations reach 200.

Calculate potential concurrency across the whole worker fleet:

~~~text
Total potential concurrency
    = worker instances
      × active subscriptions per instance
      × concurrency per subscription
~~~

Knobs you can tune:

- Worker replica count.
- Consumers/subscriptions per instance.
- `flatMap` concurrency.
- Batch size.
- Message polling/consumption rate from the broker.
- Retry and backoff settings.
- Global rate limits or partitioning.

Do not cap only the pool while letting message queues accumulate unbounded backlogs. Enforce worker-level backpressure/admission control and monitor lag.

If messages are retried after timeouts, ensure writes are idempotent. Raising concurrency makes duplicates or conflicts more likely when multiple messages update the same entity.

## 19. Retries Can Amplify Load When Pools or Databases Are Overloaded

When acquire timeouts or query timeouts occur, immediate retries inject extra load right when the system is already saturated.

Avoid immediate retries without backoff:

~~~java
return repository.findById(id)
        .retry(5);
~~~

A retry policy should ensure:

- Only safe, transient errors are retried.
- Retry count is bounded.
- Exponential backoff with jitter is used.
- An overall deadline is enforced.
- Validation or constraint errors are never retried.
- Non-idempotent writes are not retried when commit status is uncertain.
- Retries cannot overwhelm database recovery.

Example:

~~~java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5);

return repository.findById(id)
        .retryWhen(retryPolicy);
~~~

This illustrates a policy for retryable reads. For writes, evaluate repeat semantics and idempotency before enabling retries.

When the database recovers, backoff with jitter prevents all clients from hammering it simultaneously. However, retries do not replace circuit breakers, rate limits, or bulkheads for load shedding.

## 20. Connection Pools and Mixed Workloads

If an application handles both interactive requests and background batches, batches can monopolize connections and starve critical user requests.

Options:

- Lower batch concurrency.
- Schedule batches off-peak or throttle them via rate-limited queues.
- Allocate a realistic connection budget favoring high-priority workloads.
- Use separate pools for distinct workloads if justified and accounted for in the total connection budget.
- Set deadlines on requests and jobs.
- Track pending acquires per pool when multiple pools exist.

Do not spin up extra pools merely to dodge queues without summing total sessions. Two pools with `max-size` 20 each still permit 40 connections per instance.

With separate pools, note that transactions do not automatically span across two pools. A transaction manager manages its assigned `ConnectionFactory`; operations on another pool do not automatically join the same atomic transaction.

## 21. Avoid Confusing Thread Pools with Connection Pools

R2DBC is a reactive database API. Connection pools and scheduler thread pools govern two completely different resources.

- Connection pools manage database connections.
- Reactor schedulers manage where callbacks or tasks execute.
- `flatMap` concurrency bounds active inner publishers in one pipeline.
- The database caps total query execution and session capacity.

Do not raise threads via `Schedulers.parallel()` to fix pool exhaustion. Nor should you enlarge the connection pool to solve CPU-heavy transformations.

CPU-heavy work may warrant an appropriate scheduler:

~~~java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::calculateExpensiveScore);
~~~

Moving a callback to another scheduler does not make database queries faster. Measure query time, connection wait time, and CPU processing time separately.

Do not offload R2DBC calls onto `boundedElastic` out of habit from blocking JDBC. R2DBC drivers already provide non-blocking APIs; using blocking schedulers unnecessarily adds overhead and hides pipeline design flaws.

## 22. Anti-Patterns in Concurrency and Pool Tuning

- **Setting `max-size` huge to stop acquire timeouts:** can saturate the database.
- **Raising per-request `flatMap` concurrency without counting total requests:** produces much higher load than expected.
- **Letting background workers run at maximum concurrency:** batches starve interactive traffic.
- **Holding transactions open across HTTP calls or long processing:** pins connections needlessly.
- **Running parallel statements on one transaction connection:** drivers may not support it.
- **Treating `prefetch` like connection count:** the two parameters mean different things.
- **Using `collectList()` on unbounded data:** causes memory pressure.
- **Retrying immediately on pool timeouts:** amplifies overload.
- **Monitoring only connection count:** misses latency, queues, locks, and throughput.
- **Sizing pools for a single replica:** ignores autoscaling and rolling deployments.
- **Creating multiple pools without summing `max-size`:** blows past the database budget.
- **Growing thread pools to fix connection pool issues:** targets the wrong resource.
- **Using H2 or mocks to tune production pools:** fails to reflect real drivers and engines.

## 23. Pre-Change Configuration Checklist

Before increasing concurrency or `max-size`, determine:

1. What are the actual query throughput and average queries per request?
2. What are average and p95/p99 connection hold times?
3. How many connections are acquired, idle, and pending in the pool?
4. Do acquire timeouts happen continuously or only during bursts?
5. Does the database still have CPU, memory, I/O, and connection headroom?
6. Are there lock waits, slow queries, or long-running transactions?
7. How many inner publishers and what concurrency does each request use?
8. How many requests and background subscriptions run concurrently?
9. What is the maximum replica count and number of pools per replica?
10. Does total `max-size` fit comfortably inside the database budget?
11. Do any transactions or `Flux` streams hold connections too long?
12. Are parallel operations running on a single transaction connection?
13. Do retries use backoff and are writes idempotent?
14. Were load tests run on the real database/driver with a representative workload?
15. Did p95/p99, throughput, and DB resources actually improve after the change?

## 24. Conclusion

Optimizing concurrency alongside pool sizing is a balancing act between active reactive operations, borrowable connections, and real database capacity. `flatMap` concurrency is a per-subscription limit; across many concurrent requests and workers, aggregate concurrency can far exceed the single number in one pipeline. Connection pool `max-size` caps connections per pool per instance, whereas system-wide connection totals must sum across all pools and replicas.

Start from the database connection budget, measure connection hold times and throughput, use Little’s Law to estimate average active work, and validate with load tests. Bound concurrency per workload, keep transactions short, avoid long-held streams and unthrottled batches, configure proper acquire/query/request timeouts, and monitor pending acquires alongside database latency, CPU, and locks. Enlarge pools only when the pool itself is the bottleneck and the database retains headroom. The goal is steady throughput with bounded tail latency and resource usage—not maximizing connections or active publishers.
