# Pool Observability: Acquired, Idle, and Pending Connections

## 1. Why Observe the R2DBC Connection Pool?

In Spring WebFlux and Spring Data Relational R2DBC applications, a connection pool manages a set of reusable connections for database access. When an operation needs the database, the application borrows a connection from the pool. When the operation finishes and the connection is released properly, the pool can return that connection to the idle state for another request to use.

A pool avoids the cost of creating a physical connection for every SQL statement and limits how many connections an application instance can open to the database. However, a pool is also a finite resource. When all connections are borrowed, new requests must wait or fail if they exceed the timeout or queue limit.

Looking only at API response time is not enough to identify where the problem lies. A slow endpoint can be caused by:

- A long-running database query.
- The connection pool running out of idle connections.
- Requests waiting in the acquire queue.
- Connections being held for a long time inside a transaction or while streaming results.
- The database refusing new connections.
- An external service being slow while an R2DBC transaction still holds a connection.
- Traffic rising beyond the pool limit or the database connection limit.

To diagnose issues, you must observe at least four core states:

- **Acquired:** the number of connections currently borrowed from the pool by the application.
- **Allocated:** the number of connections the pool has created or is managing.
- **Idle:** the number of connections currently idle and ready to be borrowed.
- **Pending:** the number of requests currently waiting to acquire a connection.

These four metrics tell you whether the pool has spare capacity, is operating normally under high load, or is saturated. This guide explains how to read these metrics, enable observability via Micrometer and Spring Boot Actuator, set up alerts, and trace root causes when the pool is exhausted.

## 2. Lifecycle of a Connection in the Pool

A pool typically manages connections through the following conceptual states:

~~~text
                Application needs database
                         |
                         v
                Request to acquire connection
                         |
              +----------+----------+
              |                     |
              v                     v
       Idle connection        No connection
         available              available
              |                     |
              v                     v
       Move to acquired       Room to create new?
                                    |
                          +---------+---------+
                          |                   |
                         Yes                  No
                          |                   |
                          v                   v
                   Create connection     Put request in
                   and lend to app       pending queue
                          |                   |
                          v                   v
                       Acquired         Wait for connection
                                        to be released or created
              |                     |
              +----------+----------+
                         |
                         v
                Database operation finishes
                         |
                         v
                 Release connection
                         |
                         v
                  Return to idle state
~~~

In real-world operations, the pool also performs validation, eviction, timeouts, and faulty connection handling. The diagram above only illustrates the primary flow.

### 2.1. Acquired: Connections Currently Borrowed

Acquired is the number of connections currently leased to consumers. They have not yet been returned to the pool.

An acquired connection may currently be:

- Executing SQL.
- Waiting for the database to return results.
- Inside an open transaction.
- Held by a callback using `Connection` directly.
- Streaming results via `Flux`.
- Waiting for another processing step within the same connection-hold scope.

Therefore, acquired does not equal the number of SQL statements actively running on the database. A connection can be acquired while no SQL statement is running at that moment, for example when a service is waiting on an external HTTP call while a transaction remains open.

Acquired increases when there are many concurrent operations or when each operation holds a connection for a long time. Look at it together with pending, idle, pool max size, and processing time before drawing conclusions.

### 2.2. Allocated: Total Connections Managed by the Pool

Allocated represents the number of connections the pool has created or allocated to manage. In a typical reading:

- A portion of allocated connections are acquired.
- The rest are idle.
- The pool can create additional connections up to the max size limit if there is demand and the database allows it.

In steady state, acquired plus idle is usually close to allocated. When the pool is creating, closing, or validating connections, the counts may be in transition and will not necessarily match strictly at every instant.

Allocated helps answer: how many connections has the pool opened, and does it still have room to open more?

Do not confuse allocated with max size. For example, if max size is 20 but allocated is only 8, the pool can still create more connections if needed and the database accepts them.

### 2.3. Idle: Connections Ready for Use

Idle is the number of connections currently in the pool and not borrowed by any consumer. This represents capacity available immediately for new requests.

Idle being 0 is not necessarily an error. Under steady load, a pool can use nearly all connections without any request having to wait. A problem arises when idle remains 0 persistently, acquired hits the limit, and pending rises.

Excessively high idle counts for long periods may indicate the pool is configured larger than needed. However, do not shrink the pool based on a short snapshot; observe peak hours, latency, and burst headroom.

### 2.4. Pending: Requests Waiting to Acquire

Pending is the number of requests that have asked for a connection but have not yet been granted one. They are waiting for a connection to be released or for the pool to create a new one.

Pending is a direct signal that the application cannot obtain a connection immediately.

- Pending equals 0: at measurement time, no acquire requests are waiting.
- Brief pending spikes: may be a short traffic burst and not necessarily an incident.
- Continuously growing pending: the pool may be saturated or creating new connections is too slow.
- Pending hitting the queue limit: new requests may be rejected depending on pool configuration.

Monitor both acquire wait time and acquire timeout counts. Even a small queue with long wait times can push API latency past SLOs.

## 3. Reading All Four Metrics Together

Do not draw conclusions from a single gauge alone. The table below illustrates several states:

| Acquired | Idle | Pending | Initial Interpretation |
|---|---|---|---|
| Low | High | 0 | Pool has spare capacity |
| High | Some remaining | 0 | High pool utilization without queuing yet |
| Near max | 0 | Rising | Signs of pool saturation |
| At max | 0 | Persistently high | Pool cannot supply enough connections for current load |
| Below max | 0 | Rising | Possible slow connection creation, creation errors, or other configured limits |
| Low | High | 0 | Pool is not an obvious cause of current latency |

Example of a pool with max size 20:

| Metric | Value | Meaning |
|---|---:|---|
| allocated | 20 | Pool has created the maximum number of connections |
| acquired | 20 | All connections are currently borrowed |
| idle | 0 | No connections available |
| pending | 35 | 35 requests are waiting |

This is a clear sign of saturation. However, immediately increasing max size might not fix the root cause. If queries are slow or transactions hold connections too long, a larger pool only shifts pressure onto the database and can overload it.

Another example:

| Metric | Value | Meaning |
|---|---:|---|
| allocated | 12 | Pool has not needed to open up to max size 30 |
| acquired | 3 | Only 3 connections are currently borrowed |
| idle | 9 | Plenty of connections available |
| pending | 0 | No requests waiting |

If the API is still slow in this situation, inspect query latency, downstream services, CPU, event loop, and network. The pool is not the first suspect.

## 4. Common R2DBC Pool Metrics

When using R2DBC Pool with a suitable Micrometer integration, common pool metrics are named:

| Metric | Meaning |
|---|---|
| r2dbc.pool.acquired | Number of connections currently borrowed |
| r2dbc.pool.allocated | Number of connections allocated by the pool |
| r2dbc.pool.idle | Number of idle connections |
| r2dbc.pool.pending | Number of requests waiting to acquire |
| r2dbc.pool.max.allocated | Maximum allocated level recorded, if provided by version |
| r2dbc.pool.max.pending | Maximum pending level recorded, if provided by version |

Exact metric names, tags, and enabling steps depend on the R2DBC Pool version, Micrometer version, and application configuration. Do not assume every version exposes all metrics in the table. Check the Actuator endpoint and documentation for the exact running version.

The acquired, allocated, idle, and pending metrics are typically gauges: they represent state at the moment of observation, not cumulative request totals since application startup.

### 4.1. How Gauges Differ from Counters

A gauge can go up or down with current state:

- Acquired increases when a connection is borrowed.
- Acquired decreases when a connection is released.
- Idle increases when a connection returns to the pool.
- Pending increases when a request must wait and decreases when granted a connection or cancelled.

A counter typically only increases, such as total requests, total errors, or total timeouts since the process/registry reset.

Do not apply `rate()` to a gauge as if it were a counter. For gauges, typically observe current value, max, window average, or sustained duration above a threshold.

### 4.2. Same Metric Name with Different Tags

When multiple pools exist, metrics must be distinguished by a pool-identifying tag. The tag may be named `name`, `pool`, or another key provided by the specific integration.

Do not assume the tag is always named `name`. Inspect `availableTags` on Actuator or labels in Prometheus to confirm the exact tag being exported.

Pool names should be stable and meaningful, such as `orders`, `audit`, or `reporting`. Do not put customer IDs, request IDs, or per-request changing values in tags because that creates very high cardinality.

## 5. Enabling Observability with Spring Boot Actuator and Micrometer

### 5.1. Common Dependencies

For a Spring Boot application, you typically need:

- Spring Boot Actuator to expose management and metric endpoints.
- A Micrometer registry matching your observability backend, e.g., Prometheus registry if using Prometheus.
- R2DBC Pool if the application uses connection pooling.
- The database's R2DBC driver.

Artifact names and versions should follow your project's Spring Boot dependency management. Do not manually mix Micrometer or R2DBC Pool major versions that differ from your Spring Boot version.

### 5.2. Exposing the Metrics Endpoint

Example `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Or using properties:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
~~~

The metrics endpoint lets you inspect a specific meter. The Prometheus endpoint exports metrics in Prometheus format if the corresponding registry is configured.

In production, protect management endpoints with security, network policies, or appropriate deployment controls. Never expose all management endpoints publicly to the Internet.

### 5.3. Checking Metrics via Actuator

You can access:

~~~http
GET /actuator/metrics
~~~

To list available meters. Then query a specific metric:

~~~http
GET /actuator/metrics/r2dbc.pool.acquired
GET /actuator/metrics/r2dbc.pool.allocated
GET /actuator/metrics/r2dbc.pool.idle
GET /actuator/metrics/r2dbc.pool.pending
~~~

Actuator's response typically includes the metric name, measurements, and `availableTags`. If the application has multiple pools, use the actual returned tag to filter for a specific pool.

Illustrative response structure:

~~~json
{
  "name": "r2dbc.pool.acquired",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 8.0
    }
  ],
  "availableTags": [
    {
      "tag": "name",
      "values": ["orders", "audit"]
    }
  ]
}
~~~

This is a structural example to illustrate how to read the response, not a fixed response across all versions. Tag names and values depend on pool and registry configuration.

Once you know the tag, you can query by tag, for example:

~~~http
GET /actuator/metrics/r2dbc.pool.acquired?tag=name:orders
~~~

Only use `name` if your application's endpoint actually publishes that tag. If the tag is `pool`, use the exact key returned.

### 5.4. The Metrics Endpoint Is Not a Historical Dashboard

The Actuator metrics endpoint typically reports the current value or snapshot of a meter in the process. It does not store long-term history and does not replace a time-series system.

To observe trends, scrape metrics periodically into Prometheus or the corresponding registry, then visualize them on dashboards and configure alerts.

## 6. Using Prometheus to Observe the Pool

If the application uses the Micrometer Prometheus registry, the endpoint is typically:

~~~http
GET /actuator/prometheus
~~~

Dotted metric names are usually converted to Prometheus-compatible names, for example:

~~~text
r2dbc_pool_acquired
r2dbc_pool_allocated
r2dbc_pool_idle
r2dbc_pool_pending
~~~

Actual names may vary by version and configuration. Inspect the endpoint output directly before writing dashboards or alerts.

### 6.1. Monitoring Pending

Conceptual PromQL example:

~~~promql
r2dbc_pool_pending
~~~

This chart shows the number of waiting requests over time, split by pool label if the metric has one.

An alert can start from a condition where pending stays greater than 0 over a period:

~~~promql
max_over_time(r2dbc_pool_pending[2m]) > 0
~~~

This is only an example. In production, add pool labels, instance labels, and a duration condition appropriate for normal load. A brief spike does not necessarily warrant waking on-call.

### 6.2. Monitoring Pool Utilization

You can track acquired against configured max size. If the `max_allocated` metric reflects the highest recorded value rather than the configured max size, use a dedicated configuration metric or dashboard variable to compute the ratio.

Conceptual formula:

~~~text
pool utilization = acquired / configured max size
~~~

For example, if max size is 20 and acquired is 18, utilization is 90%.

Do not mechanically use `allocated` as the denominator if the goal is to compare against configured max size. `allocated` might only be the currently created connections and may not have reached the limit yet.

### 6.3. Monitoring Acquire Timeouts

Some versions/integrations provide metrics or observations for acquire timeout, connection creation time, and pool errors. If no built-in metric exists, you can record errors at the service layer or connection acquisition layer using a custom Micrometer counter/timer.

Specific meter names must be confirmed from your library version. Do not build dashboards based on assumed metrics that are not actually exported.

### 6.4. Monitoring Per Pool and Per Instance

In multi-instance deployments, distinguish:

- Pool `orders` on instance A.
- Pool `orders` on instance B.
- Pool `audit` on instance A.
- Pool `audit` on instance B.

If a dashboard only aggregates everything into one total, a locally saturated instance can be missed. Retain diagnostic labels such as pool name, application, environment, and instance.

Do not add high-cardinality labels like user ID, order ID, or SQL parameters.

## 7. Pool Configuration and Its Relationship to Metrics

Metrics only make sense when you understand the pool configuration in use.

Example manual configuration with R2DBC Pool:

~~~java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(driverConnectionFactory)
        .name("orders")
        .initialSize(2)
        .maxSize(20)
        .maxPendingAcquire(100)
        .maxAcquireTime(Duration.ofSeconds(3))
        .maxCreateConnectionTime(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofMinutes(10))
        .maxLifeTime(Duration.ofMinutes(30))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
~~~

This example illustrates common properties. Verify supported builder APIs and properties against your project's R2DBC Pool version.

Meaning:

- `initialSize`: initial number of connections created.
- `maxSize`: maximum number of connections the pool can manage.
- `maxPendingAcquire`: limit on requests waiting to acquire.
- `maxAcquireTime`: maximum wait time to obtain a connection.
- `maxCreateConnectionTime`: timeout for creating a new connection.
- `maxIdleTime`: time a connection is allowed to remain idle before eviction per config.
- `maxLifeTime`: maximum lifetime of a connection in the pool.
- `name`: pool identifier name, which may be used in metric tags depending on integration.

When using Spring Boot auto-configuration for a single datasource, pool properties typically live under `spring.r2dbc.pool.*` if pooling is enabled and the right dependencies are present. With multiple custom `ConnectionFactory` beans, configure a separate pool for each datasource instead of assuming a single auto-config prefix creates all pools automatically.

### 7.1. Do Not Increase maxSize Just Because Acquired Is High

High acquired can be normal load. Check:

- Is pending increasing?
- Does acquire wait exceed SLOs?
- Is query latency increasing?
- Does the database still have capacity?
- What is the total connection count across all application instances?

If pending is 0 and the API still meets SLOs, the pool may simply be utilized efficiently.

### 7.2. maxPendingAcquire Is the Queue Limit

An overly large queue does not make the database process work faster. It may just make requests wait longer, consume more memory, and increase tail latency.

Choose a queue limit based on acceptable wait time. When the pool is saturated, the system needs backpressure or early rejection rather than accumulating unbounded requests.

### 7.3. Acquire Timeout and Query Timeout Are Different

- Acquire timeout limits how long a request waits to borrow a connection from the pool.
- Query timeout limits how long an SQL statement or database operation can execute as supported by the driver/framework.
- HTTP timeout limits how long the client waits for a response.
- Transaction timeout limits transaction duration per transaction manager capabilities.

A request can hit acquire timeout before any SQL statement starts. Do not lump all of these under a single "database query timeout" message.

## 8. Distinguishing Borrowed Connections from Running Queries

This is one of the most common misunderstandings when reading dashboards.

**Acquired is not the active query count.**

For example, consider a service doing:

~~~java
@Transactional
public Mono<Order> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            paymentClient.authorize(order)
                .flatMap(result -> {
                    order.setStatus("PAID");
                    return orderRepository.save(order);
                })
        );
}
~~~

If `paymentClient` takes 8 seconds to respond, the reactive transaction may still hold the R2DBC connection during that wait. For most of that time, no query is running, yet `acquired` stays elevated.

Other situations can also keep connections acquired:

- A `Flux` reading results is consumed slowly.
- An `inConnection` callback is waiting on a publisher to complete.
- A transaction is scoped too broadly.
- Code manually acquires a connection and forgets to release it.
- A publisher never completes or is not cancelled properly.

To understand running queries, combine pool metrics with database monitoring, query statistics, tracing, or SQL execution instrumentation. Pool metrics only report connection borrowing state.

## 9. Diagnosing Pool Saturation Patterns

### 9.1. Acquired Hits Max, Idle Is 0, Pending Increases

This is the clearest saturation pattern.

Investigation workflow:

1. Identify which pool is saturated.
2. Check when pending started increasing.
3. Compare query latency and transaction duration.
4. Check database CPU, lock waits, and session count.
5. Find requests/transactions holding connections for a long time.
6. Check whether downstream calls run inside a transaction.
7. Check whether publishers are held open by slow `Flux` consumers.
8. Check whether code manually acquires connections and lacks cleanup.

Increasing `maxSize` should only be done after confirming the database has capacity and connections are being used efficiently.

### 9.2. Acquired Below Max Yet Pending Still Rises

A pool that has not reached max size while requests still wait may be caused by:

- The pool creating new connections slowly.
- The database rejecting or throttling new connections.
- `maxCreateConnectionTime` being hit.
- Connection validation or initialization taking time.
- Another limit inside the pool or driver taking effect.
- Metrics sampled at slightly different times with observation lag.

Check connection creation error logs, connect times, DNS, network, TLS, database authentication, and server-side connection limits.

### 9.3. Allocated Hits Max Yet Acquired Is Not High

The pool may be retaining many idle connections from earlier load or min-idle settings. This is not an issue if idle connections remain available and pending is 0.

If the database has too many sessions despite low application load, review max size, min idle, max idle time, and application instance count.

### 9.4. Idle Is 0 Yet Pending Is 0

All connections may currently be in use while no requests have had to wait yet. This can be normal high load.

Monitor further:
- Acquire latency.
- Whether pending increases on the next burst.
- API latency.
- Query latency.
- Transaction duration.

A single snapshot of idle equal to 0 is not enough to conclude the pool needs to be enlarged.

### 9.5. Pending Rises Together with Query Latency

If query latency rises first and acquired and pending follow, the root cause may lie in the database or SQL query:

- Missing index.
- Lock contention.
- High database CPU or I/O.
- Execution plan regression.
- Database running vacuum/checkpoint or heavy background tasks.
- A query scanning too many rows.

Pool saturation here may be a symptom of a slow database, not the root cause.

### 9.6. Pending Rises Together with Transaction Duration

If transaction duration increases while query latency does not increase correspondingly, look for work occurring between SQL operations:

- HTTP calls or blocking SDK calls.
- Sending messages.
- File processing.
- Waiting on user input or another publisher.
- Retries with backoff waits.
- Result streaming with a slow consumer.

Narrow transactions to surround only the database operations that require atomicity.

## 10. Common Causes of Long Connection Hold Times

### 10.1. Transactions Wrapping Calls Outside the Database

Do not hold an R2DBC transaction while waiting on a payment gateway, HTTP service, or email provider unless business requirements strictly demand it.

Split into:
1. Read required data.
2. End the read transaction if one was used.
3. Call the external service.
4. Open a short write transaction, reload state, and apply updates.

If reliable coordination is needed, use outbox, saga, and idempotency patterns rather than holding a connection across the entire workflow.

### 10.2. Slowly Consumed Flux

For operations returning `Flux`, the connection may remain held while the publisher reads results.

If downstream processes each row slowly or pushes data to a slow HTTP client, the connection may stay occupied for a long time.

Consider:
- Pagination.
- Row limits.
- Mapping data to lightweight DTOs.
- Avoiding blocking work inside `Row` mapping callbacks.
- Moving non-database processing after reading finishes when possible.
- Avoiding long transactions solely to stream large datasets.

### 10.3. Failing to Release Connections When Using R2DBC SPI Directly

If the application calls `ConnectionFactory.create()` directly, it is responsible for releasing the connection on all complete, error, and cancel paths.

With publishers, `usingWhen` can manage asynchronous cleanup:

~~~java
Mono.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> executeQuery(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
~~~

If you only need access to a connection inside a callback, prefer `DatabaseClient.inConnection` or `inConnectionMany` so Spring manages the lifecycle according to its rules. Never manually close a connection managed by `DatabaseClient` or a transaction manager.

### 10.4. Non-Terminating Publishers

A publisher that never completes can hold connections and transactions open longer than expected. Check:

- Does the `Mono`/`Flux` wait on a source that never emits a signal?
- Is an infinite publisher composed into a transaction?
- Is a nested subscription created that prevents cleanup on the main flow?
- Is a callback hanging or blocking without a timeout?

Place timeouts at the appropriate layer and ensure cleanup follows the reactive lifecycle.

## 11. Observing Multiple Pools in the Same Application

An application may have multiple `ConnectionFactory` instances such as `orders`, `audit`, and `reporting`. Each pool must be observed individually.

Example:

| Pool | Max size | Role |
|---|---:|---|
| orders | 20 | Order transactions |
| audit | 8 | History logging |
| reporting | 12 | Reporting queries |

Dashboards should have a panel group for each pool:

- Acquired.
- Allocated.
- Idle.
- Pending.
- Acquire timeout/error.
- Acquire wait if instrumented.
- Pool utilization vs. max size.

Do not look only at total connections across the application. The `orders` pool may be saturated while `audit` has spare capacity. Looking only at totals can mask localized saturation.

### 11.1. Calculating the Connection Budget Across All Instances

Suppose one instance has three pools:

- `orders` max size = 20.
- `audit` max size = 8.
- `reporting` max size = 12.

One instance can open up to 40 connections. Running 5 instances gives a potential limit of 200 connections, not counting other applications, migration jobs, admin clients, and workers.

Calculate:

~~~text
Total potential connections
  = number of instances
    x sum of pool max sizes per instance
    + connections from other workloads
~~~

Compare this number against the database connection limit and operational headroom. Never configure `maxSize` in isolation while ignoring replica count.

### 11.2. Keeping Pool Names Clear

Stable pool names allow metrics to be filtered by datasource. Use short, meaningful names such as `orders`, `audit`, `reporting`.

Avoid:
- Creating new pool names per request.
- Attaching customer IDs to metric tags.
- Attaching full SQL or query parameters to tags.
- Using names that change per deployment unless necessary.

High tag cardinality increases memory and storage costs in the metrics system.

## 12. Setting Meaningful Alerts

No single threshold fits every system. Base thresholds on SLOs, pool max size, processing durations, and application baselines.

Generally useful signals:

| Signal | Meaning | Action |
|---|---|---|
| Sustained pending > 0 | Requests waiting to acquire | Check saturation and wait times |
| Acquired near max for extended period | Pool near capacity limit | Check connection hold time and DB capacity |
| Idle = 0 with rising pending | No available connections left | Investigate pool saturation |
| Acquire timeouts rising | Requests failing to obtain connections in time | Check pool, DB, and timeouts |
| Create connection failures rising | Pool cannot open new connections | Check database, network, credentials, and session limits |
| Transaction duration rising | Connections may be held too long | Find long transactions and non-DB side effects |
| API latency rising while pool has idle | Bottleneck may lie in another layer | Check queries, CPU, downstream, and event loop |

### 12.1. Alerting on Sustained Conditions

A brief pending spike may be a normal burst. Alerts should require the condition to persist over a window, e.g., pending greater than 0 continuously for 2 minutes, depending on the system.

Conceptual PromQL example:

~~~promql
max_over_time(r2dbc_pool_pending[2m]) > 0
~~~

In production dashboards, add pool and environment filters based on the exported labels. To alert per pool, group by the corresponding pool label.

### 12.2. Combining Pool Metrics with SLOs

High pool utilization is not necessarily an incident if API latency and error rate remain healthy. Conversely, small but persistent pending counts can degrade p99 latency.

A high-quality alert should combine:
- Pending or acquire timeouts.
- API latency.
- Error rate.
- Transaction duration.
- Database latency or saturation.

Do not alert solely because acquired hit 90% once. Look at persistence and user impact.

## 13. Building an Operational Dashboard

A useful pool dashboard can be organized into rows:

### Row 1: Overall Health

- API request rate.
- API p95/p99 latency.
- HTTP 5xx/error rate.
- Database availability.

### Row 2: Pool State by Datasource

- Acquired.
- Allocated.
- Idle.
- Pending.
- Configured max size.

### Row 3: Acquire Timing and Errors

- Acquire wait duration if available.
- Acquire timeout count.
- Connection creation failures.
- Validation failures.

### Row 4: Database

- Active sessions.
- Running query count.
- Query latency.
- Lock waits.
- CPU, memory, and I/O.

### Row 5: Transactions and Application

- Transaction duration.
- Slow queries.
- In-flight requests.
- Scheduler saturation if blocking workloads exist.
- Downstream latency.

When panels share the same time range, causal relationships become visible:

~~~text
Database query latency rises
          |
          v
Connections held longer
          |
          v
Acquired increases
          |
          v
Idle decreases
          |
          v
Pending increases
          |
          v
Acquire timeouts and API latency increase
~~~

This is one possible causal chain, not an invariable rule. A long transaction or blocking call outside the database can also drive up acquired before query latency changes.

## 14. Distinguishing Pool Metrics from Database Session Metrics

The two observability systems measure different perspectives:

| Perspective | What It Measures |
|---|---|
| R2DBC pool acquired | Connections leased by the pool to the application |
| R2DBC pool idle | Connections still in the pool and not borrowed |
| R2DBC pool allocated | Connections created/managed by the pool |
| R2DBC pool pending | Application requests waiting for a connection |
| Database active sessions | Connected database sessions and server-side state |
| Database running queries | SQL statements currently executing at observation time |
| Database lock wait | Transactions waiting on locks in the database |

An acquired connection may not be running a query. A database session may still exist even while idle in the pool.

When comparing connection counts:
- Sum `allocated` across all pools on all instances.
- Add connections from other services.
- Include connections from migrations, admin tools, and monitoring.
- Compare against the database's server-side session limit.

If server sessions exceed one instance's `allocated`, that is not automatically abnormal because many other connection sources exist.

## 15. Testing Pool Saturation

Testing the pool helps verify limits and timeouts work properly.

### 15.1. Generating Controlled Load

Configure a small test pool, such as max size 2 and a low max pending acquire. Then create publishers that hold connections long enough to observe acquired, idle, and pending.

Do not use `Thread.sleep` on the event loop to hold connections. Use a test publisher controlled by `Sinks` or `Mono.delay` in tests to explicitly control when completion happens.

### 15.2. Verifying Pending

Scenario:

1. The first two operations acquire two connections.
2. Both wait on a test signal so they do not release yet.
3. A third operation requests a connection.
4. Verify pending increases.
5. Signal one operation to complete.
6. Verify the waiting request receives a connection and pending decreases.

Tests need access to metrics or pool metrics APIs matching the version in use. If no direct metric API is exposed, verify behavior through acquire timings and publisher outcomes.

### 15.3. Testing Acquire Timeout and Pending Limit

Another test holds all connections and dispatches additional requests:

- Requests wait within the allowed limit.
- Once acquire timeout elapses, the publisher emits the corresponding error.
- When pending exceeds the limit, the pool rejects new requests according to the version's behavior.
- After connections are released, the pool continues serving new requests.

Do not assert overly specific exception names if driver/pool versions wrap errors differently. Check the root cause and the library's actual contract.

### 15.4. Testing Cleanup After Errors and Cancellations

Verify connections return to the pool after:
- Publisher completion.
- Publisher error.
- Subscriber cancellation.
- Query timeout.
- Direct connection callback completion.

If `acquired` does not decrease after all publishers finish, investigate cleanup logic, detached subscriptions, or connections held elsewhere.

### 15.5. Do Not Use Small Test Pools to Size Production Pools

A max pool size of 2 makes reproducing saturation easy, but does not mean production should use 2. The goal of testing is to verify semantics, timeouts, and cleanup. Production sizing must be based on traffic, database capacity, and replica count.

## 16. Common Mistakes When Reading Metrics

| Misconception | Why It Is Wrong | Correct Understanding |
|---|---|---|
| Acquired is the number of running queries | Connections may be held in a transaction without running SQL | Acquired is the number of borrowed connections |
| Idle = 0 is always an error | Pool may be fully utilized without anyone waiting | Check pending, latency, and timeouts |
| Allocated equals max size | Allocated is the created count; max size is the configured limit | Compare allocated against max size |
| Rising pending guarantees the database is slow | Connections may be held by transactions or downstream calls | Correlate query latency and transaction duration |
| Increasing maxSize always solves saturation | The database can overload when more sessions open | Check database capacity and hold times |
| Pending = 0 proves the pool is healthy | Acquire timeouts may have occurred before the snapshot or no queue existed at the moment | Check timeout/error rates and acquire latency |
| Actuator metrics store history | The endpoint primarily returns meter snapshots | Use Prometheus or a time-series backend |
| The metric tag is always named `name` | Tags vary by version and integration | Check actual `availableTags` |
| Each instance has a small maxSize so total is small | Total connections multiply by replica count and pool count | Calculate the system-wide connection budget |
| Pool allocated equals DB active sessions | Multiple connection sources and idle sessions exist | Compare the two perspectives separately |
| Increasing pending queue improves throughput | Long queues can just make requests wait longer | Limit queues according to latency budget |
| Looking only at aggregate dashboards | An individual pool can be saturated | Break down metrics per pool and instance |

## 17. Workflow for Investigating Pool Exhaustion

When receiving a pool saturation alert, follow this order:

1. Identify which datasource/pool has rising pending.
2. Check acquired, allocated, idle, and max size at the same time.
3. Inspect acquire timeouts and connection creation failures.
4. Check query latency, database CPU, lock waits, and session limits.
5. Check transaction duration and unusually long transactions.
6. Look for services making HTTP calls, blocking SDK calls, or file processing inside transactions.
7. Check large `Flux` streams or slow consumers holding connections.
8. Check code using `ConnectionFactory` directly for proper cleanup on complete/error/cancel.
9. Check replica count and total potential connections across all pools.
10. Only increase max size when the database has capacity and the workload truly needs more connections.
11. Tune acquire timeout, pending limit, and concurrency within the latency budget.
12. Re-run load tests and verify pending, timeouts, and p95/p99 latency improved.

If query latency is high, address queries/database first. If queries are fast yet acquired remains high, look for time connections are held between operations. If allocated is below max while pending rises, investigate connection creation and server-side limits.

## 18. Self-Check Exercises

### Exercise 1: Reading Pool State

A pool has max size 20, acquired 20, idle 0, pending 15. What should you conclude?

Hint: The pool is saturated at the time of measurement. Find out why connections are held long and confirm database capacity before increasing max size.

### Exercise 2: Acquired Is Not Query Count

Acquired is 12, yet the database reports only 2 running queries. Can this happen?

Hint: Yes. The remaining connections can be held in transactions, waiting on downstream calls, streaming data, or sitting idle while leased.

### Exercise 3: Idle Equals 0

A pool has acquired equal to max, idle 0, yet pending is always 0 and the API meets SLOs. Is this necessarily an incident?

Hint: No. The pool is fully utilized without requests having to wait. Continue monitoring bursts, acquire latency, and timeouts.

### Exercise 4: Pending Rising While Allocated Is Below Max

What causes should be checked?

Hint: Slow or failing connection creation, database limits, validation, network, authentication, or other pool configurations.

### Exercise 5: Long Transaction

A service calls a payment gateway inside a 10-second R2DBC transaction. What can happen to acquired?

Hint: Connections may be held while waiting on payment even without running queries, reducing idle and increasing pending.

### Exercise 6: Multiple Instances

An application runs 4 replicas; each replica has an `orders` pool with max size 20 and an `audit` pool with max size 5. What is the total potential connections from these two pools?

Hint: Each replica can open 25 connections; 4 replicas can open 100 connections total, excluding other applications.

### Exercise 7: Actuator Tag

The metrics endpoint returns `availableTags` with tag `poolName`. Should you query using tag `name`?

Hint: No. You must use the exact tag key published by the endpoint.

### Exercise 8: Timeout

A request receives an acquire timeout. Does that mean the SQL statement ran too long?

Hint: No. An acquire timeout occurs while waiting for a connection before any SQL can execute.

### Exercise 9: Pool Metrics vs. Database Sessions

The `orders` pool's allocated is 20, yet the database reports 60 sessions. Can that be normal?

Hint: There can be other instances, other services, other pools, migrations, or admin connections. Sum all connection sources.

### Exercise 10: Increasing Pool Size

Pending is rising, but query latency and database CPU are also very high. Should you increase `maxSize` immediately?

Hint: Do not decide solely from pending. The database may be the bottleneck; opening more connections can worsen load. Investigate queries, locks, and capacity first.

## 19. Takeaways

- A connection pool manages reusable connections and caps how many connections an application opens to the database.
- Acquired is the number of borrowed connections, not the number of running queries.
- Allocated is the number of connections the pool has created/managed; max size is the configured limit.
- Idle is the number of connections ready to be borrowed.
- Pending is the number of requests waiting to acquire.
- Acquired near max, idle at 0, and persistently rising pending signal pool saturation.
- Idle at 0 alone is not enough to declare an incident; check pending, latency, and timeouts.
- Common pool metrics include `r2dbc.pool.acquired`, `allocated`, `idle`, and `pending`; exact names and tags depend on version and integration.
- Spring Boot Actuator provides metrics endpoints; Prometheus or a time-series backend stores history and powers dashboards/alerts.
- Check actual `availableTags` rather than guessing tag names.
- Break out metrics by pool and instance so local saturation is not hidden.
- Calculate total connections across replicas, all pools, and other workloads before raising max size.
- Long transactions, slow `Flux` consumers, non-database blocking calls, and missing cleanup all keep acquired elevated.
- Acquire timeout differs from query timeout; pending differs from running query count.
- Combine pool metrics with query latency, transaction duration, database sessions, lock waits, and API SLOs.
- Test pool saturation with controlled barriers/publishers, not `Thread.sleep`.
- Only increase pool size after confirming the database has capacity and the root cause truly requires more connections.

When observing an R2DBC pool, read acquired, allocated, idle, and pending as a group of states. Combine them with acquire duration, transaction duration, and database health to determine whether connections are being used efficiently or held too long. Per-pool dashboards, replica-aware connection limits, and SLO-based alerts help detect connection contention early without blindly enlarging the pool.
