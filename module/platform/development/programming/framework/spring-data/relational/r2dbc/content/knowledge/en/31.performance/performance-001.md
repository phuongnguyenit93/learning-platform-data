# Defining Latency, Throughput, and Connection Count as Measurement Targets

When optimizing Spring Data R2DBC performance, you should not start by arbitrarily increasing the connection pool size or adding replicas. First, you need to determine how many requests the system must serve, how fast it must respond, and how many database connections it will use at the expected load. The three foundational metric groups are **latency**, **throughput**, and **connections**.

These three metrics are closely related but cannot substitute for one another. A system can achieve high throughput with terrible p99 latency; a pool can have many connections without the database processing queries any faster; or latency can be low at light load but spike sharply as concurrency increases. Measurement targets must describe the realistic workload, acceptance thresholds, and test conditions so that results are reproducible.

## 1. Three Questions to Answer Before Measuring

Before running a benchmark, translate business requirements into three measurable questions:

1. **Latency:** how long is a request or database operation allowed to take, and at which percentile?
2. **Throughput:** how many requests or transactions per second must the system complete while still meeting the latency target?
3. **Connections:** how many concurrent connections does the application need, how long is the pool allowed to wait, and does the database have enough connection budget for all instances?

For example, a product-reading API might need to serve a normal load of 100 requests/second, a peak load of 250 requests/second, p95 under 200 ms, and p99 under 500 ms. These are only illustrative numbers; real targets must come from product requirements, user experience, cost, and database capacity.

Do not set a goal like “R2DBC must be 30% faster than JDBC” without specifying the same workload, database, configuration, and measurement conditions. Reactive is an I/O processing model, not an automatic guarantee of lower latency or higher throughput.

## 2. Defining SLIs, SLOs, and Test Thresholds

A clear performance target typically includes:

- **SLI (Service Level Indicator):** an observable metric, such as an endpoint's p95 latency or successful request rate.
- **SLO (Service Level Objective):** the target to meet over a time window, such as 99% of read requests completing within 300 ms.
- **Load-test acceptance criteria:** the conditions for a test run to pass, such as minimum throughput, maximum p99, and maximum error rate at a defined load.

Example target table:

| Metric | Workload | Illustrative Target |
| --- | --- | --- |
| Read latency | Product detail API | p95 ≤ 200 ms, p99 ≤ 500 ms |
| Write latency | Order creation API | p95 ≤ 400 ms, p99 ≤ 800 ms |
| Throughput | Defined read/write mix | ≥ 150 successful requests/second |
| Error rate | Same measurement window | < 0.5% unexpected errors |
| Pool acquire | Wait time to obtain a connection | p95 ≤ 20 ms |
| Pending acquire | Steady load | Does not grow continuously |
| Connection count | All application instances | Does not exceed allocated DB budget |

The values in the table are not defaults of Spring or R2DBC. Replace them with your system's requirements. A number is only meaningful when accompanied by the endpoint/query, load, measurement duration, percentile, and environment conditions.

## 3. What Is Latency?

Latency is the time from when an operation starts until the required result is ready. For an HTTP API, it can be measured from when the server receives the request until the response completes. For a database operation, it can be measured from when acquiring a connection or sending a query begins until the full result is received.

Do not lump all latency into a single number when searching for root causes. A WebFlux request may go through:

1. Routing and Controller handling.
2. Validation and Service logic.
3. Waiting for a connection from the pool.
4. Sending the query and waiting for database execution.
5. Receiving and mapping rows.
6. Calling external services, if any.
7. Serializing the response and sending it over HTTP.

Total API time can be much larger than SQL time. Measuring each stage separately helps identify whether the bottleneck is in the pool, database, network, mapping, or an external dependency.

~~~mermaid
flowchart LR
    A[HTTP received]
    B[Controller / Service]
    C[Pool acquire]
    D[Database query]
    E[Mapping]
    F[Response encoding]
    G[HTTP completed]
    A --> B --> C --> D --> E --> F --> G
~~~

If you only measure query duration and conclude the API meets its SLO, you may miss pool wait times or response serialization. Conversely, if you only measure end-to-end latency, it is hard to know which layer needs optimization.

## 4. Use Percentiles Instead of Only Averages

Latency typically has a skewed distribution: most requests are fast, while some are slow due to locks, cache misses, GC, connection waits, or large queries.

Common percentiles:

- **p50:** 50% of requests complete at or below this time; close to the median.
- **p90:** 90% of requests complete at or below this time.
- **p95:** 95% of requests complete at or below this time.
- **p99:** 99% of requests complete at or below this time.
- **p99.9:** shows the very slow tail when the sample size is large enough.

Example:

| Metric | Latency |
| --- | ---: |
| p50 | 45 ms |
| p90 | 110 ms |
| p95 | 180 ms |
| p99 | 620 ms |
| Maximum | 2.4 s |

A 45 ms median looks good, yet 1% of requests are slower than 620 ms. If users encounter those slow requests frequently at scale, the experience is still poor.

The mean (average) is useful for calculating total load and applying certain queueing models, but it does not describe tail latency well. A performance report should include at least p50, p95, p99, throughput, and error rate.

Percentiles require a sufficient sample size. A test with only a few hundred requests is not a solid basis for interpreting p99. For p99/p99.9, run the test long enough and generate enough requests in each endpoint group.

## 5. Distinguishing Request, Transaction, and Query Latency

An R2DBC system can measure multiple time layers:

| Scope | Start / End | Used to Answer |
| --- | --- | --- |
| HTTP latency | Request enters server → response completes | How long does the API caller wait? |
| Service latency | Use case starts → publisher completes | How long does the business logic take? |
| Pool acquire latency | Connection requested → connection obtained | Is there waiting in the pool? |
| Query latency | Statement sent → result received per measurement scope | How long does the database/driver take to process the query? |
| Transaction duration | Transaction starts → commit/rollback | How long are the connection and transaction held? |
| External dependency latency | HTTP/message request sent → result received | How much impact does the external service have? |

Exact names and measurement points depend on instrumentation. Clearly document how measurements are taken: does query latency include acquiring a connection, does it include mapping and consuming the entire Flux, or only until the statement returns a result?

With a large Flux, the time to first element (time to first row) differs from the time to consume the entire stream. A streaming API may start returning data quickly while still keeping the connection open for a long time to read the remainder.

## 6. What Is Throughput?

Throughput is the amount of work completed per unit of time. For APIs, requests/second (RPS) is commonly used; for databases, transactions/second (TPS), queries/second, or rows/second may be used depending on the workload.

Basic formula:

\[
\text{Throughput} =
\frac{\text{Completed operations in the measurement window}}
{\text{Measurement window duration}}
\]

For example, if 9,000 requests complete successfully in 60 seconds:

\[
9,000 / 60 = 150\ \text{requests/second}
\]

You should distinguish between:

- **Offered load:** the number of requests the client attempts to send.
- **Started requests:** the number of requests the server begins processing.
- **Completed throughput:** the number of requests that finish.
- **Successful throughput/goodput:** the number of requests that finish meeting business expectations.

If the client sends 300 requests/second but the server only completes 180 requests/second, you cannot report that the system achieves 300 RPS. You need to inspect pending requests, timeouts, and errors.

## 7. Throughput Cannot Be Separated from Latency and Error Rate

A system can increase throughput by allowing longer queues. Requests still complete, but users wait much longer. Another system can keep latency low by rejecting most requests; the remaining requests have nice latency, but goodput is low.

Therefore, targets must be a simultaneous set of conditions:

- Minimum throughput.
- Maximum p95/p99 latency.
- Maximum error rate.
- Pending queue does not grow unboundedly.
- Connection usage stays within budget.
- CPU, memory, I/O, and the database are not saturated beyond acceptable levels.

Do not pick a benchmark operating point solely because it has the highest RPS. Choose the point where the system still meets latency and reliability requirements under the expected workload.

## 8. The Relationship Between Throughput, Latency, and Concurrency

Little's Law describes the average relationship in a stable system:

\[
L = \lambda W
\]

Where:

- L: average number of work items in the system (concurrency/in-flight work).
- λ: average throughput, in work items/second.
- W: average time a work item spends in the system, in seconds.

For example, if an API completes 120 requests/second with an average latency of 250 ms (0.25 seconds):

\[
L = 120 \times 0.25 = 30
\]

On average, about 30 requests are being processed or waiting in the system.

This is a steady-state relationship using averages over the same measurement scope. Do not plug p99 into the formula and treat the result as exact concurrency. If queues are continuously growing, the system is not in a steady state and the calculation does not describe that condition.

## 9. Request Concurrency Does Not Equal Database Connection Count

A WebFlux request may:

- Execute just one very short query.
- Execute multiple queries sequentially.
- Execute several queries in parallel.
- Wait on an HTTP service without holding a DB connection.
- Wait on another publisher before acquiring a connection.

Therefore, 100 in-flight HTTP requests do not mean 100 R2DBC connections are needed.

To estimate connections in use, you can apply Little's Law at the database connection scope:

\[
\text{Average active DB connections}
\approx
\text{DB operations per second}
\times
\text{Average connection hold time}
\]

For example, if the application completes 80 transactions/second and each transaction holds a connection for an average of 40 ms (0.04 seconds):

\[
80 \times 0.04 = 3.2
\]

Average active connections are approximately 3.2 under steady-state conditions. The pool still needs headroom for bursts, variance, long transactions, and background activity; however, the example shows you should not mechanically set pool size equal to total request concurrency.

## 10. What Does Connection Count Include?

When discussing connection counts, distinguish between:

- **Active/acquired:** connections currently leased to a caller and in use.
- **Idle:** connections sitting in the pool, not currently used by any caller.
- **Allocated:** physical connections created and managed by the pool, consisting of active and idle depending on how the pool measures them.
- **Pending acquire:** requests waiting to be granted a connection.
- **Maximum allocated:** the upper limit of connections the pool can create.

Exact metric names and definitions depend on the R2DBC Pool version and instrumentation. Do not add active + allocated if allocated already includes active; doing so double-counts.

A pool can have many idle connections without load. That is not a bug if the database has an appropriate budget. Conversely, continuously rising pending acquires while database CPU is low may indicate an undersized pool, long-held connections, or a leak.

## 11. Connection Pool in R2DBC

R2DBC Pool manages a set of connections so the application can reuse them instead of opening a new connection for every query. Configuration typically includes:

- Initial size: number of connections initially created.
- Max size: maximum number of connections the pool is allowed to manage.
- Max idle time: how long a connection can remain idle before eviction under policy.
- Max life time: maximum lifetime of a connection.
- Max acquire time: maximum time a caller waits to acquire a connection.
- Validation: how to verify a connection is still usable.

Example Java configuration:

~~~java
ConnectionPoolConfiguration configuration =
        ConnectionPoolConfiguration.builder(connectionFactory)
                .initialSize(5)
                .maxSize(20)
                .maxIdleTime(Duration.ofMinutes(10))
                .maxLifeTime(Duration.ofMinutes(30))
                .maxAcquireTime(Duration.ofSeconds(2))
                .build();

ConnectionPool pool = new ConnectionPool(configuration);
~~~

This is an illustrative configuration, not a default recommendation. API names and options may vary by r2dbc-pool version. When using Spring Boot, configure the pool through the mechanism supported by your Boot version and manage the pool lifecycle as a bean, rather than creating a new pool per request.

## 12. Calculating the System-Wide Connection Budget

The database connection limit is a cluster-wide or database-instance limit, not a per-pod limit.

Suppose:

- The database allows a maximum of 200 connections.
- 30 connections must be reserved for administration, migrations, monitoring, and other services.
- There are 5 application instances.
- Each instance has one writer pool.

Maximum budget available for the application:

\[
200 - 30 = 170
\]

If divided evenly:

\[
170 / 5 = 34
\]

Arithmetically, each instance cannot exceed about 34 connections if there is only one pool and no other pools. However, in practice you must reserve extra headroom for scale-out, rolling deployments where old and new versions run simultaneously, background workers, and other services.

A budgeting formula:

\[
\text{Total possible connections}
=
\sum (\text{instances} \times \text{pool max size})
+ \text{other clients}
\]

This total must be lower than the database limit with a clear safety margin. If each instance has both a writer pool and a reader pool, both must be summed. If a deployment can scale from 5 to 10 replicas, calculate based on 10, not just the normal instance count.

## 13. A Larger Pool Size Does Not Equal Higher Throughput

Increasing max pool size can reduce connection wait times when the pool is truly the bottleneck. However, it can also:

- Increase the number of concurrent queries hitting the database.
- Saturate database CPU, I/O, or lock contention.
- Increase server-side memory and context/connection overhead.
- Increase contention between transactions.
- Worsen p95/p99 latency even though pool acquire latency decreases.

If the database is already saturated at 30 connections, increasing the pool to 100 may simply shift the queue from the pool to the database. Requests still wait, but in a harder-to-control place.

Measure pool waits, active connections, database CPU/I/O, query latency, and lock waits together before changing pool size. Increase incrementally and compare under the same workload.

## 14. Connection Hold Time and Transaction Duration

Connection hold time is how long a connection is held by an operation or transaction. It can be much longer than query execution time if a transaction runs multiple statements or executes application logic between queries.

Example to avoid:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentClient.authorize(toPaymentRequest(order))
                            .thenReturn(order)
            );
}
~~~

If the HTTP call takes 2 seconds, the transaction may hold the connection for the entire wait time. This drives up active connections and can exhaust the pool.

Measure transaction duration and connection hold time, not just SQL duration. Keep transactions short by performing external calls outside the transaction or splitting workflows into local, recoverable transactional steps.

## 15. How Does Pool Saturation Manifest?

Several warning signs:

- Active/acquired connections stay at max size for extended periods.
- Pending acquires increase.
- Acquire latency p95/p99 increases.
- Request timeouts occur before queries even begin.
- Database CPU remains low while the application waits for connections.
- Connections do not return to idle after publishers complete, possibly due to leaks or long-running transactions.

If active connections are low while query latency is high, the bottleneck may be in the database, network, or locks. If pending acquires are high and active connections are always at max, examine connection hold time and workload. If allocated connections are low yet acquire timeouts occur, check connection creation errors, validation, or configuration.

Do not simply raise max size when seeing pending acquires. First determine why connections are being held and whether the database can handle additional concurrency.

## 16. Throughput and Connection Pools Have a Saturation Point

As load increases, a system typically moves through these regions:

1. **Underloaded:** few requests; low latency, idle connections available in the pool.
2. **Efficient operating region:** throughput increases nearly linearly while latency remains stable.
3. **Knee/saturation point:** throughput growth slows while latency and queues grow rapidly.
4. **Overloaded:** pending requests/connections rise, timeouts and errors appear; goodput may drop.

~~~mermaid
flowchart LR
    A[Low load]
    B[Efficient region]
    C[Knee / saturation]
    D[Overload]
    A --> B --> C --> D
~~~

The operating target should stay below the saturation point with headroom for bursts and growth. Do not set an SLO right at the maximum load a benchmark can briefly sustain for a few seconds.

## 17. Choosing Workloads to Measure

A meaningful test must reflect realistic operation types:

| Workload Group | Example | Characteristics to Record |
| --- | --- | --- |
| Read point lookup | Find entity by ID | Small row count, usually indexed |
| Read list | List with filter/sort/page | Cardinality and page size |
| Write single row | Insert/update one entity | Constraints, generated ID |
| Multi-step transaction | Create Order and OrderLine | Query count, transaction duration |
| Join/projection | Read DTO across multiple tables | Join plan and row count |
| Bulk/streaming | Batch read or write | Row count, memory, connection hold |
| Contended update | Multiple requests updating same row | Lock waits and deadlocks |

Record the mix ratio, such as 70% reads, 25% writes, and 5% multi-query workflows. The ratio must come from telemetry or expected demand, not chosen arbitrarily just to make results look good.

## 18. Test Data Must Be Representative

A benchmark with 100 rows in a table does not accurately represent production with tens of millions of rows. Test data should reflect:

- Row counts and table sizes.
- Value distributions, duplication levels, and cardinality.
- NULL ratios and long payloads.
- Indexes, constraints, and foreign keys.
- Hot keys or frequently accessed rows.
- Cache hit/miss ratios.
- Row width and result set sizes.
- Concurrent update intensity.

If every request queries a single fixed ID, caching can make the benchmark artificially fast. If test data is too small, indexes and working sets may fit entirely in memory. Simulate realistic access distributions.

## 19. A Repeatable Load-Testing Process

A test run should include these phases:

1. **Environment preparation:** record versions of the application, JVM, driver, database, schema, pool, and infrastructure.
2. **Warm-up:** let the JVM, connection pool, JIT, and database caches stabilize.
3. **Ramp-up:** gradually increase load to observe when queueing begins.
4. **Steady state:** hold target load long enough to measure stable latency and throughput.
5. **Burst:** verify ability to absorb short traffic spikes.
6. **Soak:** run for an extended duration to uncover leaks, pool drift, memory growth, or degradation.
7. **Cool-down:** reduce load and verify resources are released.

Do not compare a build warmed up for 10 minutes against one that just started. Likewise, do not compare benchmarks when one side's database has cached the data and the other has not.

## 20. Open Workload vs. Closed Workload

Two common load-generation models:

**Closed workload**

- Has a fixed number of virtual users.
- Each user sends a request, waits for the response, and then sends the next request.
- When latency increases, the request sending rate automatically drops.
- Suitable for simulating users with think time.

**Open workload**

- Sends requests at a predetermined arrival rate, e.g., 200 requests/second.
- The sending rate does not drop just because the server slows down.
- Suitable for testing whether the system can sustain offered load and detecting growing queues.

A closed workload can mask saturation: when the server slows down, the client backs off, causing throughput to stall while offered load also drops. An open workload shows more clearly whether the system can keep up with the required arrival rate.

Choose the model based on your objective; both can be used. Always record both offered load and completed throughput.

## 21. Example Measurement Script Using k6

A skeleton script:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const failed = new Rate('failed_requests');

export const options = {
  scenarios: {
    api_load: {
      executor: 'ramping-arrival-rate',
      startRate: 20,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { target: 50, duration: '2m' },
        { target: 100, duration: '3m' },
        { target: 150, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<200', 'p(99)<500'],
    failed_requests: ['rate<0.005'],
  },
};

export default function () {
  const response = http.get(
    'http://localhost:8080/api/products/42'
  );

  const ok = check(response, {
    'status is 200': (r) => r.status === 200,
  });

  failed.add(!ok);
}
~~~

This is an example script, not recommended production thresholds. Adjust endpoints, data, authentication, read/write ratios, stages, VUs, and thresholds to match your real workload. The arrival-rate executor needs enough VUs to sustain the target sending rate; if insufficient, k6 may fail to generate the expected offered load and report dropped iterations.

Run the load generator on a separate, sufficiently powerful machine or infrastructure. If the generator's CPU saturates, results will not reflect server capacity.

## 22. Measuring API and Database Queries Separately

An HTTP test shows the external experience, but additional application and database telemetry is needed:

- HTTP request duration and request count by route.
- Service/use-case duration.
- R2DBC pool acquire latency, acquired, allocated, idle, and pending counts.
- Query/statement duration by operation type.
- Transaction duration.
- Database CPU, memory, I/O, and active sessions.
- Lock waits, deadlocks, and slow queries.
- JVM CPU, heap, GC pauses, threads, and event-loop utilization.

If HTTP p99 increases while query duration stays flat, check pool acquire, service logic, external dependencies, serialization, and the event loop. If query p99 rises alongside database CPU or lock waits, investigate the database and execution plans.

## 23. Instrumentation with Spring Boot Actuator and Micrometer

Spring Boot Actuator and Micrometer can provide metrics for the HTTP server, JVM, and supported integrations. R2DBC Pool can expose metrics when appropriate instrumentation is enabled.

Common pool metric names in the R2DBC Pool ecosystem include:

- r2dbc.pool.acquired
- r2dbc.pool.allocated
- r2dbc.pool.idle
- r2dbc.pool.pending

Exact names, tags, and registration depend on pool, Spring Boot, and registry versions. Open the application's metrics/Prometheus endpoint and verify actual metrics instead of assuming every name is always present.

Example Actuator and registry dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Example endpoint configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
~~~

Expose only metrics endpoints compliant with your security policy. Do not leave management endpoints publicly open if they expose internal details.

## 24. Measuring Latency with Histograms

To compute percentiles on a metrics backend, you typically need histograms or appropriate distribution statistics. If you only emit a mean gauge, the monitoring system cannot reliably reconstruct p95/p99.

Histograms divide latency into buckets. The backend can approximate percentiles from bucket distributions. Some registries support client-side or server-side percentile histograms; configuration depends on the Micrometer registry.

Conceptual distribution configuration example:

~~~java
Timer.builder("service.operation.duration")
        .description("Duration of a service operation")
        .publishPercentileHistogram()
        .register(meterRegistry);
~~~

You can instrument a publisher segment with Reactor:

~~~java
return serviceOperation()
        .name("product.lookup")
        .tap(Micrometer.metrics(meterRegistry));
~~~

This code illustrates Reactor Micrometer integration; exact dependencies and APIs depend on the Reactor/Micrometer version. When using Spring's Observation API, you can instrument service or repository boundaries as supported by the framework.

Do not enable too many histogram buckets on every metric if cardinality and storage costs become excessive. Choose metric counts and resolution appropriate for your SLOs.

## 25. Avoiding High-Cardinality Metric Tags

Do not use per-request changing values as tags:

- User ID.
- Order ID.
- Email.
- Request ID.
- Arbitrary SQL parameters or filter values.

Each tag value combination can create a separate time series, increasing metrics memory, storage, and query costs. Use tags with bounded value sets:

- operation = read / write / search.
- repository = product / order / customer.
- outcome = success / error / timeout.
- route = endpoint template, e.g., /api/products/{id}.

Correlation IDs belong in logs and traces, not as metric labels.

## 26. Tracing to Find Slow Stages

Distributed tracing can show how a request breaks down into spans:

~~~text
HTTP GET /api/orders/{id}              420 ms
  Controller / Service                 415 ms
    R2DBC pool acquire                   8 ms
    SELECT order                         35 ms
    SELECT order lines                   22 ms
    HTTP shipping service               330 ms
    DTO mapping                          10 ms
~~~

In this example, the database is not the primary bottleneck; the shipping service call accounts for most of the latency. Increasing pool size will not fix the root cause.

Tracing should record spans for external HTTP and database operations when supported by instrumentation. Use appropriate trace sampling in production to avoid excessive overhead. Do not attach sensitive payloads to span attributes.

## 27. Measuring Pool Acquire and Query Separately

Pool acquire latency answers: how long does the application wait to obtain a connection? Query latency answers: once a connection is obtained, how long does the statement take?

Example:

| Scenario | Acquire p95 | Query p95 | Assessment |
| --- | ---: | ---: | --- |
| A | 2 ms | 180 ms | Slowness mainly in query/database |
| B | 120 ms | 35 ms | Significant pool wait |
| C | 3 ms | 40 ms | Database path relatively healthy; look for slowness in service/HTTP |

If no direct acquire metric is available, you may need to instrument the connection factory/pool or use metrics exposed by the pool. Do not infer acquire time by subtracting two independent percentiles; percentiles of sums and individual components do not add or subtract linearly.

## 28. Measuring Transaction Duration and Lock Contention

Increased transaction duration can be caused by:

- Multiple sequential queries.
- Slow queries.
- Lock waits.
- CPU logic inside the transaction.
- Calling HTTP or awaiting another publisher while the transaction is open.
- A slow consumer on a Flux within the transaction.

Measure duration alongside queries per transaction, lock waits, and connection hold time. If a transaction holds a connection for 1 second while SQL only runs for 50 ms, the remainder is spent in application logic or other waits.

For multi-step workflows, enclose only the operations that require atomicity inside the transaction. Move HTTP calls, email sending, and broker waits outside the transaction, or use an outbox to publish after commit.

## 29. Measuring Specific Queries and Execution Plans

Aggregated query latency per repository can hide a single very slow query. Categorize queries by operation/template or statement name, then use the database slow query log and execution plans.

Elements to inspect:

- Index scan vs. full table scan.
- Estimated rows vs. actual rows.
- Join strategy.
- Sort/hash operations.
- Rows returned and bytes transferred.
- Lock waits.
- Buffer/cache hits.
- Disk reads/writes.

Use EXPLAIN or EXPLAIN ANALYZE according to your database. EXPLAIN ANALYZE executes the query, so be cautious with write statements and production workloads. Query plans depend on data and statistics; do not draw conclusions solely from a tiny local schema.

## 30. R2DBC Throughput and Queries per Request

An endpoint can generate multiple queries per HTTP request. If API throughput is 100 requests/second and each request executes an average of 4 queries:

\[
\text{DB query rate} \approx 100 \times 4 = 400\ \text{queries/second}
\]

This is an average estimate; parallel queries and conditional branches can alter the distribution. Measure the actual query count per use case.

If an endpoint triggers N+1 queries, the query rate can grow with the number of returned entities. Optimizing with JOINs or batch loading can cut round trips and connection occupancy without increasing pool size.

## 31. Comparing Pool Configurations Using the Same Methodology

When testing pool sizes 10, 20, and 30:

1. Keep the application, database, data, and workload identical.
2. Restart or reset the pool to an equivalent state.
3. Warm up for the same duration.
4. Run the same offered load and steady-state duration.
5. Collect p50/p95/p99, successful throughput, error rate, acquire waits, active/pending connections, and DB CPU.
6. Repeat runs to observe variance.
7. Compare improvements against the cost of additional connections.

Example results:

| Pool max | Goodput | API p95 | Acquire p95 | DB CPU |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 90 RPS | 420 ms | 80 ms | 45% |
| 20 | 145 RPS | 230 ms | 12 ms | 68% |
| 30 | 148 RPS | 310 ms | 2 ms | 92% |

The table illustrates an important point: pool 30 lowers acquire wait, yet throughput barely rises and API p95 worsens because the database nears saturation. Pool 20 may be the better operating point in this scenario.

Do not pick a configuration based solely on acquire latency. The goal is goodput and SLO compliance at the required load while preserving database headroom.

## 32. Identifying Load Thresholds and Headroom

After running a ramp test, identify the point where:

- Throughput starts increasing slower than offered load.
- p95/p99 begins climbing sharply.
- Pending acquires or request queues grow continuously.
- Database CPU/I/O or lock waits approach limits.
- Errors/timeouts appear.

This is the saturation/knee region. Normal operating targets should sit below this region. Headroom can be sized based on expected load growth, bursts, and the time needed to scale additional instances/replicas.

For example, if the system begins violating p99 at 220 RPS, you should not set normal target capacity to 220 RPS. Choose a lower level with margin, such as 150–170 RPS depending on variance and growth plans. This is illustrative; specific thresholds must be based on repeated measurements.

## 33. Soak Testing to Detect Issues Over Time

A 5-minute test may fail to uncover:

- Gradual connection leaks.
- Pools not returning connections after cancellation.
- Memory growth from buffers or collectList on large datasets.
- Long-running transactions or stuck jobs.
- Connections expiring en masse.
- Replication lag or accumulating queues.

Soak tests run a steady workload for longer durations, such as tens of minutes or hours depending on goals. Track active/idle/pending connections, heap, GC, DB sessions, error rates, and latency over time.

If active connections climb steadily and fail to drop under constant load or after traffic stops, investigate resource lifecycles and transaction boundaries.

## 34. Measuring Under Cancellation and Timeout

In WebFlux, clients can disconnect; Reactor can cancel subscriptions. Measure:

- Number of cancelled requests.
- Time from cancellation until the connection is returned to the pool.
- Active connections remaining after the test client stops.
- Whether queries continue running on the database after the caller cancels.
- Transaction rollback count.

Cancellation does not guarantee the database stops the statement immediately; behavior depends on the driver and database. Combine Reactor timeouts, database statement/query timeouts, and pool metrics to evaluate behavior.

A test can:

1. Send a request creating a long stream.
2. Receive part of the data and close the client.
3. Observe cancellation.
4. Check pool active/idle counts and DB sessions.
5. Verify the connection can be reused.

## 35. Setting Connection Acquire and Pool Wait Targets

Do not configure max connections alone. Define the maximum wait time to obtain a connection:

- If acquire timeout is too long, requests may wait a long time before failing.
- If it is too short, brief bursts may trigger errors even when the system is about to free connections.
- If the pending queue is unbounded, memory and latency can grow.

Base acquire timeout on the request deadline and latency budget. For instance, a request with a 1-second deadline should not allow a 5-second pool acquire wait. Leave time for queries, service logic, and response serialization.

When the pool runs out of connections, explicitly decide whether the application waits within a bound or fails fast. Never allow unbounded request queues.

## 36. Allocating a Latency Budget

An API with a 500 ms SLO can allocate an internal budget:

| Component | Illustrative Budget |
| --- | ---: |
| Routing/Controller/Service | 40 ms |
| Pool acquire | 20 ms |
| Database queries | 180 ms |
| External dependency | 150 ms |
| Mapping/serialization/network overhead | 60 ms |
| Safety margin | 50 ms |
| **Total** | **500 ms** |

This is a planning example, not exact additive percentiles. Components can run in parallel, and percentiles of individual spans do not sum to the end-to-end percentile. Use budgets to set alerting/investigation thresholds, then verify against actual traces.

## 37. Targets by Endpoint Type

Do not apply a single SLO to every endpoint:

| Endpoint Type | Latency Focus | Throughput Focus | Connection Behavior |
| --- | --- | --- | --- |
| Point read | p95/p99, cache hit | Read RPS | Short query |
| Search/list | Time to first row, total response | RPS and rows/s | Result size, streaming |
| Create/update | End-to-end commit latency | Successful writes/s | Transaction duration |
| Multi-step workflow | Total duration and per dependency | Workflow completions/s | Do not hold connection across HTTP calls |
| Bulk export | Total duration, rows/s throughput | Rows/s | Stream/batch, connection hold |
| Contended write | p99, lock wait, error rate | Goodput under contention | Active connections, deadlocks |

A list endpoint may need a page size limit; an export endpoint may need streaming; a write endpoint may prioritize correctness over peak RPS.

## 38. Event Loop and CPU Impact

R2DBC uses non-blocking I/O, yet application code can still block the event loop:

- Calling JDBC or blocking HTTP clients.
- Calling `block()` on Mono/Flux.
- Running heavy CPU processing directly on the event loop.
- Serializing very large payloads without control.

When the event loop is blocked, latency can spike across many requests even when database queries remain fast. Monitor CPU, event-loop utilization, thread dumps, and blocking detection if available.

Do not mechanically offload everything onto boundedElastic. Use appropriate schedulers for genuinely blocking work and prefer non-blocking APIs within reactive flows.

## 39. Comparing R2DBC and JDBC Fairly

If the measurement goal is evaluating R2DBC as an option, keep conditions equivalent:

- Same database instance and schema.
- Same data, indexes, and queries.
- Same transaction semantics.
- Same connection budget.
- Same number of application instances.
- Same workload mix and arrival model.
- Same warm-up and steady-state durations.
- Same percentile, error, and goodput measurement methods.

Do not compare a 50-connection JDBC pool against a 10-connection R2DBC pool and draw conclusions about the protocol. Nor should you compare blocking JDBC with R2DBC in a benchmark where thread counts or client concurrency differ significantly without documenting it.

Measure throughput, tail latency, CPU, memory, threads, connection count, and operational cost. R2DBC can be useful when handling high I/O concurrency with fewer threads, but actual gains depend on workload and driver.

## 40. Documenting Benchmarks for Reproducibility

Each measurement run should record:

- Git commit/build version.
- Java/JVM version and flags.
- Spring Boot, Spring Data Relational, Reactor, and R2DBC driver versions.
- Database engine/version and configuration.
- Schema, row counts, and indexes.
- Connection pool options.
- Instance count and CPU/memory resources.
- Workload mix, data distribution, and arrival model.
- Ramp-up, warm-up, steady-state, and soak durations.
- p50/p95/p99, goodput, and error rate.
- Active/idle/pending connections and acquire latency.
- Database CPU/I/O, locks, and slow queries.

Without this information, two benchmark results cannot be reliably compared.

## 41. Example Measurement Target Report

A report may be formatted as:

~~~text
Use case: GET /api/products/{id}
Database: PostgreSQL, recorded version
Application: 3 instances
Pool: max size 20 per instance
Workload: 90% point reads, 10% updates
Arrival rate: ramp 50 -> 150 -> 200 RPS
Warm-up: 5 minutes
Steady state: 10 minutes per stage

At 150 offered RPS:
  successful throughput: 149 RPS
  p50: 38 ms
  p95: 115 ms
  p99: 280 ms
  error rate: 0.1%
  pool acquired: peak 14 per instance
  pool pending: 0 sustained
  acquire p95: 4 ms

Database:
  CPU: 62%
  active sessions: measured separately
  lock waits: within agreed threshold
~~~

This is a report format template, not real measurement results. Replace all values with data collected from testing.

## 42. Common Mistakes When Setting Measurement Targets

1. **Using only average latency.** Tail latency can be terrible even with a low mean.
2. **Reporting offered load as throughput.** Sent requests are not guaranteed to complete successfully.
3. **Setting pool size equal to HTTP concurrency.** Requests do not hold DB connections for their entire lifecycle.
4. **Increasing the pool to fix every timeout.** The bottleneck may be the database or transaction hold time.
5. **Forgetting to sum pools across instances.** Total connections can exceed database limits during scale-out.
6. **Measuring queries while ignoring pool acquire.** Requests may wait a long time before SQL starts.
7. **Measuring HTTP without database telemetry.** Makes it hard to pinpoint the slow layer.
8. **Using an overly small dataset.** Caches and execution plans will not represent production.
9. **Running only short tests.** Misses leaks, pool drift, or gradual degradation.
10. **Using a closed workload without recording offered load.** When the server slows down, the client throttles itself.
11. **Choosing peak RPS even when p99 violates the SLO.** High goodput is insufficient if user experience fails.
12. **Adding or subtracting span percentiles.** Percentiles are not linearly additive.
13. **Enabling metric tags with user/request IDs.** Causes high cardinality and increases monitoring costs.
14. **Failing to record benchmark configuration.** Results become non-reproducible.
15. **Assuming reactive automatically increases throughput.** Databases, queries, pools, CPU, and networks still have limits.

## Process for Defining Measurement Targets

1. Select critical use cases and classify reads, writes, transactions, and streaming.
2. Define workload mix, normal offered load, peak load, and bursts.
3. Set p95/p99 latency SLOs per endpoint group.
4. Set minimum goodput and maximum error rate at target load.
5. Estimate connection demand from DB operation rate and connection hold time; cross-check with pool metrics.
6. Budget total connections across instance counts, writer/reader pools, and other clients.
7. Instrument HTTP, service, pool, query, transaction, and database layers.
8. Run warm-up, ramp, steady-state, burst, and soak tests on representative data.
9. Locate the saturation point and choose an operating target with headroom.
10. Save configurations and results to compare after every change.

Latency, throughput, and connection count are three complementary lenses for defining the serving capacity of a Spring Data R2DBC application. Measure latency using percentiles across HTTP, pool, query, and transaction layers; measure throughput by successful operations completed under a defined workload; and manage connections by active/idle/pending metrics alongside a system-wide budget. Combining Little's Law, repeatable load tests, Micrometer/R2DBC Pool telemetry, and database metrics helps locate saturation points, choose an appropriate pool size, and set operating targets with headroom rather than optimizing a single number in isolation.
