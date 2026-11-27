# Designing Alerts for Errors, Pool Exhaustion, and Slow Queries

In a Spring Data Relational R2DBC application, a slow or failing request can originate in any of several layers: WebFlux, the reactive pipeline, the R2DBC connection pool, the driver, the database, or downstream services. If you monitor only CPU and HTTP 5xx counts, operations teams often discover incidents late and struggle to tell whether the connection pool is exhausted, which query is slow, or which error category is climbing.

An effective alerting system ties directly to user behavior and application serving capability. For R2DBC, monitor at least three core signal groups: **errors**, **connection pool state**, and **query latency**. Combine these signals with HTTP latency/error rates, transaction duration, structured logs, and distributed traces. Alerts should convey impact, scope, and the first investigation step; overly noisy or hypersensitive alerts will be ignored.

## 1. Goals of Observability in R2DBC

Observability helps answer three questions:

- **Metrics:** how is the system behaving and how are trends shifting over time?
- **Logs:** what specific event occurred, and in what context?
- **Traces:** which components did a request traverse, and where was time spent?

With Spring Data Relational R2DBC, correlate signals using consistent operation names, service names, environments, and trace/correlation IDs. When HTTP latency rises, you can check whether the added time sits in pool acquire, SQL execution, result mapping, or downstream processing.

A basic signal flow:

```text
HTTP request / WebFlux
        |
        +---- request rate, error rate, latency
        |
        v
Service / reactive pipeline
        |
        +---- operation outcome, retries, cancellations
        |
        v
R2DBC connection pool
        |
        +---- acquired, idle, pending, acquire latency/timeouts
        |
        v
R2DBC driver / database
        |
        +---- query duration, SQL errors, lock waits, slow statements
        |
        v
Metrics + structured logs + traces + database telemetry
        |
        v
Dashboards, alerts and runbooks
```

You do not need to collect everything at maximum granularity at every layer. Start with signals that answer operational questions and add detail where needed.

## 2. Design Alerts Around Impact, Not Just Technical Thresholds

A single metric crossing a threshold does not automatically mean users are impacted. For example, active connections hitting 90% of the pool for a few seconds can be a normal traffic peak if zero requests are waiting and latency stays steady. Conversely, even a few persistent pending acquires can cause timeouts on critical endpoints despite low CPU and database load.

Every alert should specify:

1. **Signal:** which metric or event triggers it?
2. **Scope:** which service, environment, database, pool, or operation?
3. **Time condition:** how long must it exceed the threshold, and is a minimum traffic floor required?
4. **Impact:** are users seeing errors, slowdowns, timeouts, or just resource risk?
5. **Severity:** does it require immediate action or just tracking?
6. **Action:** which dashboard, query, or runbook should be opened first?

For example, an alert saying "R2DBC pool at 95%" is far less actionable than "customer-db pool saturated for 5 minutes with requests waiting for connections and rising acquire timeouts." The second shows both resource pressure and user impact.

### 2.1. Distinguishing Symptom Alerts from Cause Alerts

- **Symptoms:** rising HTTP 5xx, rising request latency, rising timeouts.
- **Potential causes:** rising pool pending, rising query duration, rising database lock waits, connection creation failures.

Symptoms show users are affected. Cause metrics help isolate the bottleneck. Include both layers, while avoiding separate paging alerts for every correlated metric in the same incident.

### 2.2. Choosing Severity Levels

A practical classification:

| Level | Meaning | Example |
|---|---|---|
| Critical / Page | Core service losing availability or SLO severely impacted | 5xx surge, exhausted pool with widespread acquire timeouts |
| Warning / Ticket | Degrading trend or risk without broad user impact yet | Sustained high pool utilization without pending acquires yet |
| Informational | Operational context to review on dashboards | Slight uptick in retries after a deployment |

Exact severity names and routing channels depend on your organization's on-call workflows. What matters is that every level carries a clear response expectation.

## 3. Foundational Metric Frameworks: RED and USE

Two metric organization patterns are consistently useful:

- **RED** for requests/services: Rate, Errors, Duration.
- **USE** for resources: Utilization, Saturation, Errors.

Applied to an R2DBC application:

| Group | Question | Example Metrics |
|---|---|---|
| Rate | How many requests/queries per second? | HTTP requests, DB operations, statements |
| Errors | How many operations failed? | HTTP 5xx, R2DBC exceptions, acquire timeouts |
| Duration | How long did they take? | HTTP latency, pool acquire latency, query duration |
| Utilization | How much of the resource is in use? | Acquired/max connections |
| Saturation | Is work queued waiting for the resource? | Pending acquire, queue wait, DB lock waits |
| Resource errors | Is the resource itself failing? | Connection creation/validation failures |

Watching utilization alone is insufficient. A pool at 100% utilization with zero pending requests can be an acceptable brief burst; a pool at 75% utilization with steadily rising pending acquires can be alarming due to long connection holds or burst inability.

## 4. Tracking Application and Database Errors

Never lump all errors into a single counter. Categorizing errors clarifies the appropriate response.

Categories to track:

- Connection errors: inability to open connections, connection resets, network failures.
- Pool errors: acquire timeouts, closed pool, validation failures.
- Timeouts: statement timeouts, Reactor timeouts, transaction timeouts.
- Data integrity errors: unique, foreign key, `NOT NULL`, `CHECK`.
- Transaction errors: deadlocks, serialization failures, rollbacks.
- SQL/mapping errors: syntax errors, column/type mismatches, conversion errors.
- Cancellation/disconnect errors: caller aborted request or publisher cancelled.

Not all errors deserve a paging alert. Duplicate keys may be normal business conflicts; alert only on abnormal spikes. Connection failures and acquire timeouts warrant greater urgency because they can affect many operations at once.

### 4.1. Measure Error Rate Instead of Raw Error Counts Alone

An error counter jumping by 100 is major for an endpoint serving 200 requests, yet negligible for a service processing millions of requests. Compute the ratio:

\[
\text{Error rate} =
\frac{\text{Failed operations}}{\text{Total operations}}\times 100\%
\]

Dashboards can show total requests, total errors, and error ratio per operation. Include a minimum traffic floor or handle small denominators so a single failed request during a low-traffic window does not trigger false alarms.

### 4.2. Categorize Errors Using Structured Metadata

With R2DBC, use exception type, SQLSTATE, and vendor error codes for classification. For instance, PostgreSQL uses SQLSTATE `23505` for unique violations; SQLSTATE class `08` typically maps to connection exceptions, class `23` to integrity constraints, and class `40` to transaction rollbacks.

Do not parse `exception.getMessage()` as your primary classifier. Messages change across drivers, database versions, and locales, and may expose SQL or sensitive data.

An internal enum keeps metrics stable:

```java
public enum DatabaseErrorCategory {
    CONNECTION,
    POOL_ACQUIRE,
    TIMEOUT,
    DATA_INTEGRITY,
    TRANSACTION,
    SQL_OR_MAPPING,
    CANCELLED,
    UNKNOWN
}
```

A service or exception translator can map errors to this category and increment counters. Never use raw exception messages as metric tags.

### 4.3. Alerting on Errors by Operation

If all database errors are aggregated together, a low-priority endpoint can hide failures in a payment endpoint. Attach stable operation names such as:

- `customer.find-by-id`
- `order.create`
- `payment.capture`
- `report.export-page`

Operation names must belong to a finite code-defined set. Never use full URLs with path parameters, customer IDs, SQL statements, or bind values as labels.

## 5. Observing the R2DBC Connection Pool

A pool is a finite resource between the application and the database. Key metrics typically include:

| Metric | Meaning |
|---|---|
| Acquired/active | Connections currently held by the application |
| Idle | Idle connections in the pool |
| Allocated/total | Total connections created by the pool |
| Max size | Configured maximum connection limit |
| Pending acquire | Requests waiting for a connection |
| Acquire duration | Time from requesting to receiving a connection |
| Acquire timeout | Number of waits that timed out without getting a connection |
| Creation/validation failure | Failures to create or validate connections |
| Release/close | Connections returned or closed |

Exact metric names depend on `r2dbc-pool`, Micrometer, Spring Boot, and your active versions. Verify the actual metrics exported in your runtime environment rather than copying metric names unverified from another version.

### 5.1. Pool Utilization

A simple ratio:

\[
\text{Pool utilization} =
\frac{\text{Acquired connections}}{\text{Max pool size}}
\]

For example, with a 40-connection max pool and 32 acquired, utilization is 80%. This is a signal to watch, though you should not automatically page just because utilization stays high for a few seconds.

Combine utilization with:

- Is pending acquire rising?
- Is acquire latency rising?
- Are acquire timeouts occurring?
- Is HTTP latency/error rate degrading?
- Is the database overloaded or waiting on locks?

### 5.2. Pending Acquire Is a Key Saturation Signal

`pending acquire` shows requests actively waiting for a connection. When it remains greater than 0 persistently, the pool cannot immediately satisfy demand at measurement time.

A pool saturation alert should combine conditions such as:

- Acquired near max over a sufficiently long window.
- Pending acquire greater than 0 or rising acquire duration.
- Acquire timeouts present or rising HTTP latency.

Exact thresholds must be tuned to normal load and SLAs. No single utilization number fits every application.

### 5.3. Acquire Timeouts

Acquire timeouts are a stronger signal than utilization alone because an operation genuinely failed to get a connection within the configured deadline. Monitor:

- Timeout counts by pool/database.
- Timeout ratio over total acquire attempts.
- Duration over which timeouts persist.
- Which operations drive high connection demand.

When acquire timeouts rise, investigate long-held connections, slow queries, long transactions, pool size, database `max_connections`, and competing workloads sharing the database.

## 6. Do Not Increase Pool Size Blindly

When a pool saturates, increasing `maxSize` may shrink queues briefly, yet simultaneously sends more concurrent queries to the database. If the database is already overloaded, enlarging the pool worsens lock contention, CPU, memory, and I/O pressure.

Before changing pool size, identify the cause:

- Are queries slow due to missing indexes or bad execution plans?
- Are transactions holding connections while waiting on HTTP calls or CPU work?
- Are large `Flux` streams feeding slow clients?
- Are `collectList`, buffers, or prefetch holding resources longer?
- Is a retry storm occurring after transient failures?
- Are operations missing cleanup or leaking connections?
- Does total pool size across all application instances exceed the database connection budget?

### 6.1. Calculating the System-Wide Connection Budget

Pool size must be evaluated across total instances, not one pod:

\[
\text{Max total connections} =
\text{Instance count} \times
\text{Max pool size per instance}
\]

For example, 8 instances each configured with a 30-connection max pool can open up to 240 connections for a single service. Adding workers, migration jobs, dashboards, and other services sharing the database pushes total demand even higher.

Reserve capacity for DBA/admin work, replication, migrations, and other workloads. Databases have their own connection limits; do not size pools based solely on application thread or CPU counts.

### 6.2. Pool Size and Concurrency Must Work Together

High `flatMap` concurrency, concurrent exports, or unbounded retries can spike connection demand. Appropriate pool sizing must pair with application-layer concurrency limits, bulkheads on heavy endpoints, and quotas on background jobs.

## 7. Monitoring Slow Queries

No single query latency metric captures the entire breakdown of an R2DBC operation. Separate:

- Pool acquire time: time waiting for a connection.
- Statement execution time: time for the database/driver to execute the statement.
- Result consumption time: time to read the entire result.
- Mapping time: time to convert rows into objects.
- Downstream time: time to process, serialize, and send data.
- End-to-end operation time: full service operation duration.

If you only measure from repository call to `Flux` completion, the metric may include downstream consumption time. It is not purely SQL execution time inside the database.

### 7.1. Histograms and Percentiles

Latency distributions are usually skewed: most queries are fast, while a few are very slow. Averages hide tail latency.

Monitor percentiles such as:

- p50: median latency.
- p90/p95: common tail latency benchmarks.
- p99: tail latency of the slowest requests.

Dashboards can chart p50/p95/p99 for `order.find-by-id` over time. Histograms allow computing aggregated percentiles across multiple instances; exact export and query syntax depend on your metrics backend.

Avoid judging p99 alone under very low traffic because percentiles become noisy with tiny sample counts. View sample counts alongside latencies of actual requests.

### 7.2. Slow Query Thresholds

Slow query thresholds should reflect operation types and SLAs. A primary-key lookup needs a different threshold than an aggregate report or page export. You can define thresholds by category:

| Operation Group | Design Target Example |
|---|---|
| Interactive lookup | Query by primary/unique key |
| Transactional write | Short-lived `INSERT`/`UPDATE` |
| Search/list | Filtered query with bounded page size |
| Aggregate/report | `GROUP BY`, `SUM`, multi-table joins, or large datasets |
| Export page | Page query allowed longer duration within bounds |

Dashboard thresholds are internal policies, not default R2DBC limits. Measure baselines first, then alert against SLOs.

## 8. Using Database Telemetry to Confirm Truly Slow Queries

Application metrics show which operation is slow; database telemetry reveals the SQL, execution plan, and server-side root cause.

For PostgreSQL, common sources include:

- `pg_stat_activity`: active sessions, running queries, and wait states.
- `pg_stat_statements`: aggregated statistics per normalized query if the extension is enabled.
- `EXPLAIN (ANALYZE, BUFFERS)`: execution plans and buffer usage for selected queries.
- Database logs: statement durations, deadlocks, lock timeouts, and connection events per configuration.
- Lock/wait views: which session is waiting and which holds the lock.

Never enable logging of all statements with bind values in production without evaluating sensitive data and log cost. Prefer normalized query fingerprints or operation names whenever possible.

### 8.1. Distinguishing Slow Queries from Lock Waits

A statement can report high elapsed time due to:

- CPU/I/O-heavy query plans.
- Missing or suboptimal indexes.
- Scanning too many rows.
- Lock waits or another transaction holding locks.
- Overloaded database or insufficient I/O capacity.
- Slow network, driver, or result consumption.

`pg_stat_activity` and lock telemetry distinguish actively executing queries from blocked queries. A "high query duration" alert should lead to inspecting wait events and execution plans, not blindly assuming missing indexes.

### 8.2. pg_stat_statements

PostgreSQL's `pg_stat_statements` extension aggregates execution statistics for statements, typically including call counts and total/mean/min/max execution times. Proper extension setup and database permissions are required.

Use it to spot query groups with high total time or abnormal mean/max durations. Statistics can be reset and track a capped number of statements; account for reset times when comparing dashboards.

Never put raw query text into metric labels. Query text can contain literals, schema details, or sensitive data if SQL string concatenation was misused.

## 9. Naming Operations for R2DBC Queries

To analyze by use case, attach operation names at service or repository boundaries:

```java
public Mono<Order> findOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .name("order.find-by-id")
        .tag("component", "r2dbc");
}
```

The `name` and `tag` operators are Reactor metadata consumed by compatible instrumentation. Whether they appear as metric/trace tags depends on your Micrometer/Reactor instrumentation configuration. Never assume calling `.name()` alone exports metrics automatically.

Alternatively, instrument at the service boundary using Observation/Micrometer per your Spring Boot version's conventions. Either way, operation names must be stable and low-cardinality.

### 9.1. Never Put Dynamic IDs in Tags

Avoid:

```java
// Avoid: each orderId creates a separate time series.
Timer.builder("r2dbc.operation.duration")
    .tag("orderId", orderId.toString())
    .register(registry);
```

Time-series counts can scale with orders, spiking memory and query costs. Use finite tag sets such as operation, database, outcome, error category, or deployment environment.

Never use emails, usernames, tenant IDs, SQL text, bind parameters, request IDs, or trace IDs as metric labels. Those belong in controlled logs/traces subject to data policies.

## 10. Metrics with Micrometer and Spring Boot

Spring Boot Actuator/Micrometer can provide HTTP, JVM, connection pool, and observation metrics depending on dependencies, configuration, and versions. For R2DBC, verify that your pool exports instrumented metrics and binds them to the registry.

Implementation steps:

1. Add Actuator and the Micrometer registry matching your metrics platform.
2. Enable metrics endpoints according to security policy.
3. Verify pool metrics appear after creating and using connections.
4. Add custom timers/counters for business operations if default instrumentation is insufficient.
5. Attach finite tags such as `operation`, `database`, `outcome`, and `error_category`.
6. Forward metrics to Prometheus or your corresponding backend.
7. Build dashboards and alert rules anchored to SLOs/baselines.

Meter names, binders, and configuration properties change across Spring Boot, Micrometer, and R2DBC Pool versions. Consult documentation for your exact project versions and verify `/actuator/metrics` or scrape outputs in test environments rather than copying legacy properties blindly.

### 10.1. Counter for Errors by Category

Example using `MeterRegistry` to increment a counter:

```java
public void recordDatabaseFailure(
        MeterRegistry registry,
        String operation,
        DatabaseErrorCategory category) {

    registry.counter(
        "app.database.operations",
        "operation", operation,
        "outcome", "error",
        "error_category", category.name()
    ).increment();
}
```

This illustrates manual instrumentation. Ensure `operation` and `category` come from internal enums/constants with finite value sets. When every error increments the counter with the same tag set, the backend can compute error rates over time.

### 10.2. Timer for Operations

```java
public Mono<Customer> findCustomer(Long id) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return customerRepository.findById(id)
            .doFinally(signal -> sample.stop(
                Timer.builder("app.database.operation.duration")
                    .tag("operation", "customer.find-by-id")
                    .tag("signal", signal.name().toLowerCase(Locale.ROOT))
                    .register(meterRegistry)
            ));
    });
}
```

This timer measures from subscription until the publisher completes, errors, or is cancelled. For `Mono`, that is typically end-to-end operation duration. For `Flux`, the timer may include downstream consumption time rather than strictly SQL execution. Name the metric and document its semantics accurately.

To measure acquire or statement duration separately, instrument the pool/driver/Observation layer directly. Never label an end-to-end timer "SQL duration" if it includes mapping or HTTP streaming.

## 11. Designing Pool Exhaustion Alerts

A useful pool alert combines multiple signals instead of a single threshold:

**Warning:** sustained high utilization with pending acquires starting to appear, without significant acquire timeouts yet.

**Critical:** sustained pending acquires, acquire latency exceeding budget or rising acquire timeouts, paired with HTTP errors/latency showing user impact.

Pseudo-rule, independent of specific metric names:

```text
IF acquired_connections / max_connections > 0.90
AND pending_acquire > 0
FOR 5 minutes
THEN alert = R2DBC_POOL_SATURATED
```

Another rule can watch acquire timeout rates:

```text
IF rate(pool_acquire_timeouts[5m]) > 0
AND request_rate > minimum_traffic
FOR 2 minutes
THEN alert = R2DBC_POOL_ACQUIRE_TIMEOUTS
```

Thresholds like 90%, 5 minutes, and 2 minutes are illustrative examples. Tune them to your pool size, burst patterns, SLAs, traffic, and database scaling headroom.

### 11.1. Why Not Alert on High Utilization Alone?

A pool can run efficiently at high utilization without queuing. Alerting solely on utilization causes false positives during peak hours. Pending acquire, acquire duration, and timeouts show when work is actually waiting.

### 11.2. Alerting Per Pool / Database

If an application has multiple `ConnectionFactory` beans or pools, give each pool a stable identity. Attach `pool` or `database` labels from internal configuration, such as `primary` or `reporting`. Never put connection URLs or hostnames containing secrets into public labels.

## 12. Designing Slow Query Alerts

A slow query alert can evaluate p95/p99 or slow query counts over thresholds:

```text
IF p95(operation_duration{operation="order.find-by-id"}) > 300ms
AND operation_count > minimum_sample_count
FOR 10 minutes
THEN alert = ORDER_LOOKUP_SLOW
```

This is an illustrative rule. If the timer wraps the entire publisher, metrics can include downstream processing. For `Flux` queries, completion time depends on row count and consumption speed. Prefer operation-specific latencies and separate query execution from result consumption when possible.

### 12.1. Alerting on Slow Query Counts

Alongside percentiles, count queries exceeding a threshold:

```text
slow_query_count = count(query_duration > threshold)
```

Absolute counts catch rare but severely slow queries. The ratio of slow queries to total queries normalizes across shifting traffic.

### 12.2. Do Not Page on Every Single Slow Query

A reporting query can legitimately take longer than a transactional lookup. Categorize by operation and SLO. Alerts should fire when problems repeat or affect users, while logs and traces help inspect individual outliers.

## 13. Error Rate and SLO Alerts

When a service has availability or latency SLOs, design alerts around error budget burn rate rather than fixed error thresholds alone.

Example availability SLI:

\[
\text{Availability} =
1 - \frac{\text{Eligible failed requests}}{\text{Eligible requests}}
\]

Define "eligible failed request" clearly: does it exclude client 4xx validation errors, upstream timeouts, or client-initiated cancellations? Do not treat every error as a server failure if it does not reflect service quality.

With a 99.9% SLO, the error budget over a compliance window is the 0.1% of requests allowed to fail per the SLI definition. Burn rate measures how fast that budget is consumed relative to an even pace across the window.

Multi-window/multi-burn-rate alerts detect both:

- Severe incidents burning through the error budget rapidly in a short window.
- Smaller, persistent incidents that would exhaust the budget over the full period.

Do not force complex alert math if the service lacks well-defined SLOs. Start with operation-level error ratios and latencies, then adopt error budgets once SLIs/SLOs are agreed upon.

## 14. Correlating HTTP Errors with R2DBC Errors

One request can fail across multiple layers. For instance, HTTP 503 may stem from a pool acquire timeout; HTTP 500 may stem from SQL syntax/mapping errors; HTTP 409 may reflect a business unique constraint conflict.

Maintain these analysis dimensions:

- HTTP route template and status class.
- Service operation.
- Database/pool name.
- Error category.
- Trace ID or correlation ID in logs/traces.
- Deployment version.

Never use concrete paths containing IDs as metric labels. Use route templates such as `/orders/{id}` to keep cardinality low.

With traces, you can inspect spans such as:

```text
HTTP POST /orders
  └── order.create
       ├── r2dbc.pool.acquire
       ├── db INSERT orders
       └── db INSERT order_lines
```

Span names and automatic creation depend on Micrometer Observation/Tracing and your driver. The diagram illustrates structure, not default span names for every stack.

## 15. Structured Logs Supporting Alerts

Metrics reveal trends; logs inspect specific failures. A well-structured log event might look like:

```text
event=database.operation.failed
service=order-service
operation=order.create
database=primary
error_category=CONNECTION
exception_type=R2dbcTransientResourceException
correlation_id=...
deployment_version=...
```

These fields are examples. Keep `operation`, `database`, and `category` to finite sets. Correlation IDs enable trace lookups, but never belong in metric labels.

### 15.1. Never Log Raw SQL or Bind Values

SQL and bind values can contain emails, tokens, payment data, or user content. Never leave driver/statement TRACE logging enabled by default in production. For diagnostics, use query fingerprints or operation names and approved metadata.

### 15.2. Preserve Causes While Controlling Log Output

Preserve exception causes inside the reactive pipeline and log safe error types/categories at boundaries. You do not always need to pass the entire `Throwable` to loggers if messages or stack traces could leak SQL or sensitive data. When stack traces are required, route them only to access-controlled sinks with proper redaction and retention policies.

## 16. Distributed Tracing for Slow Queries

Traces separate time across layers:

- Waiting for the connection pool.
- Sending statements and waiting on the database.
- Reading results.
- Mapping data.
- Calling external services.
- Serializing/writing HTTP responses.

If a trace contains only a single coarse database span, you can see the operation is slow but cannot easily separate pool wait from SQL execution. Add pool/driver instrumentation or dedicated events/timers when needed.

### 16.1. Sampling

Tracing every request increases storage and infrastructure cost. Use proportional sampling while optionally retaining error or high-latency traces via tail-based sampling in your collector. Ensure policies do not drop all traces for rare yet critical operations.

Never use trace IDs as metric tags because cardinality is nearly one value per request. Trace IDs belong in log/trace contexts.

## 17. Cardinality and Metrics Cost

A common mistake is creating metric tags from dynamic data:

- `customerId`, `orderId`, `email`.
- Raw SQL or query parameters.
- Request IDs, trace IDs.
- URLs with path variables.
- Exception messages.

Every unique tag combination creates a separate time series. High cardinality inflates memory, storage, scrape/ingestion costs, and slows dashboards.

Prefer bounded tags:

- `operation`: enum/constant.
- `database`: logical pool name.
- `outcome`: `success`, `error`, `cancelled`.
- `error_category`: enum.
- `environment`: `prod`, `staging`.
- `status_class`: `2xx`, `4xx`, `5xx`.

To inspect a specific order, use controlled logs/traces instead of metric labels.

## 18. Alerting on Retry Storms and Connection Creation

Retries can amplify database load right when the database is struggling. Track:

- Retry attempts by operation and error category.
- Retry success/failure rates.
- Average attempts per operation.
- Backoff durations.
- Connection creation rates and creation failures.
- Pending acquire and query rates during retries.

If many instances retry simultaneously without backoff/jitter, the database can be overwhelmed as it recovers. Retry storm alerts should combine rapidly rising retry rates with error rates or pool saturation.

Never retry validation errors, duplicate key errors, or SQL syntax errors. Only retry explicitly identified transient errors, bounded by retry limits, overall deadlines, and idempotency for writes.

## 19. What Should an Operational Dashboard Include?

An R2DBC dashboard can be organized into sections:

### 19.1. Request Health

- Request rate by route template/operation.
- Error rate and status class.
- p50/p95/p99 HTTP latency.
- Request timeouts/cancellations.
- Deployment version and rollout markers.

### 19.2. Connection Pool

- Acquired, idle, allocated, and max size.
- Pending acquire.
- Acquire latency p95/p99.
- Acquire timeouts and connection creation failures.
- Utilization per logical pool.

### 19.3. Database Operations

- Query/operation counts.
- Error rate by error category.
- p50/p95/p99 duration per operation.
- Slow query count above threshold.
- Retry attempts.
- Transaction duration/rollbacks if instrumented.

### 19.4. Database Server

- Active sessions and connection limits.
- CPU, memory, I/O, and storage latency.
- Lock waits/deadlocks.
- Cache hits/physical reads if provided by the DBMS.
- Top normalized statements by total time/call count.
- Replication lag if replicas are used.

### 19.5. JVM

- Heap used/after GC.
- Allocation rate and GC pauses.
- Thread/scheduler utilization.
- Direct buffer/native memory if available.
- Container memory and restarts/OOMs.

Dashboards should allow filtering by service, environment, database/pool, and operation. Avoid dumping every metric onto one screen without a clear troubleshooting hierarchy.

## 20. Illustrative PromQL Examples

Actual metric names depend on binders and configuration. The expressions below use placeholder names to illustrate the logic; replace them with verified metric names in your environment.

### 20.1. Operation Error Rate

```promql
sum(rate(app_database_operations_total{outcome="error"}[5m]))
/
clamp_min(sum(rate(app_database_operations_total[5m])), 1)
```

Group by `operation` or `database` when tag cardinality is low. `clamp_min` avoids division by zero; you still need low-traffic handling to prevent noisy alerts.

### 20.2. Pool Utilization

```promql
app_r2dbc_pool_acquired
/
clamp_min(app_r2dbc_pool_max, 1)
```

When multiple pools exist, group by logical pool name. Alert only when high utilization coincides with pending acquires or rising acquire latency.

### 20.3. Pending Acquire

```promql
max_over_time(app_r2dbc_pool_pending[5m]) > 0
```

Production rules should consider persistence duration, pending magnitude, and request impact. A brief spike may not warrant a page.

### 20.4. p95 Operation Duration

For histogram metrics with buckets:

```promql
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(app_database_operation_duration_seconds_bucket[5m])
  )
)
```

Exact `_bucket` names and units depend on the live metric. If a timer does not export histogram buckets, percentiles cannot be computed this way; enable histograms in Micrometer/backend config.

### 20.5. Acquire Timeout Rate

```promql
sum by (pool) (
  rate(app_r2dbc_pool_acquire_timeouts_total[5m])
)
```

Alert when the rate climbs over a sustained window with active traffic. For low-traffic systems, combine absolute timeout counts with persistence windows.

## 21. Example Alerts and Recommended Actions

| Alert | Suggested Signal | First Action |
|---|---|---|
| Rising HTTP error rate | 5xx ratio breaches SLO | Open error traces, check deployments and error categories |
| R2DBC pool saturation | Acquired near max + pending acquire | Check acquire duration and queries/transactions holding connections |
| Pool acquire timeouts | Timeout counter rising | Check pool metrics, connection leaks, and DB `max_connections` |
| Rising query latency | Operation p95/p99 above baseline | Check normalized queries, execution plans, and lock/wait telemetry |
| Database connection failures | Creation/validation failures rising | Check network, credential rotation, DB availability, and connection limits |
| Retry storm | Attempts surging per operation | Check root error, backoff/jitter, retry filters, and idempotency |
| Overly long transactions | Transaction duration p95/p99 rising | Look for network/CPU work inside transactions and long streams |
| Abnormal cancellations | Cancel count rising by endpoint | Check client disconnects, gateway timeouts, and response latency |

Every alert should link directly to the relevant dashboard and runbook. Never emit bare "threshold exceeded" notifications without operation, pool, or environment context.

## 22. Runbook for Investigating Pool Exhaustion

Upon receiving a pool saturation or acquire timeout alert:

1. Confirm scope: a single pool or the entire database; one instance or all instances.
2. Check acquired/max, idle, pending acquire, and acquire latency.
3. Check HTTP request rate, 5xx, and latency over the same window.
4. Identify operations with rising query duration or request duration.
5. Inspect for long transactions, large streams, and slow clients.
6. Check database active sessions, lock waits, CPU/I/O, and connection limits.
7. Check retry rates and connection creation failures.
8. To shed load if needed, cap concurrency/exports or pause background workloads per procedure.
9. Increase pool size only if the database has spare capacity and the pool is verified as the true bottleneck.
10. After mitigation, verify pending acquire returns to 0, acquire latency normalizes, and HTTP SLOs recover.

Never kill database sessions or modify database settings in production without evaluating impact and following approved operational procedures. Runbooks should state who is authorized to perform those actions.

## 23. Runbook for Investigating Slow Queries

When p95/p99 or slow query counts rise:

1. Identify the affected operation and start timestamp.
2. Compare query duration against pool acquire and end-to-end duration.
3. Inspect the matching query fingerprint/normalized statement.
4. Check `pg_stat_activity`, wait events, and lock chains if using PostgreSQL.
5. Check `pg_stat_statements` for shifts in call counts or mean/total times.
6. Run `EXPLAIN` or `EXPLAIN ANALYZE` in an appropriate environment with representative data.
7. Check indexes, rows scanned, joins, sorts, filters, and parameter selectivity.
8. Check recent schema changes, statistics, data volume shifts, and deployments.
9. Validate the impact of any query fix using latency, pool utilization, and database load.

`EXPLAIN ANALYZE` actually executes the query. For writes or heavy queries, choose a safe environment and transaction rather than running arbitrarily in production.

## 24. Avoiding Alert Fatigue

A good alerting system not only detects incidents but guides responders on what to do next. Common causes of alert fatigue:

- Alerting on multi-second spikes with zero user impact.
- Firing separate ungrouped alerts from multiple metrics for the same incident.
- Static thresholds ignoring traffic levels or baselines.
- Alerts lacking owners or runbooks.
- Sending informational warnings to critical paging channels.
- High metric cardinality slowing down dashboards and alert evaluations.
- Lacking mute/maintenance windows during deployments or scheduled maintenance.

Review alerts after every incident and periodically:

- Did alerts detect the issue before users reported it?
- Were there false positives?
- Were multiple alerts redundant?
- Could the on-call engineer act directly from the alert content?
- Do thresholds still fit after traffic growth?
- Which unused alerts can be retired?

## 25. Testing Alerts Before Production

Alerts are part of operational software and must be tested.

### 25.1. Testing Instrumentation

- Trigger a controlled database error in a test environment.
- Verify the error counter increments with the expected operation and category.
- Verify the success counter does not increment erroneously.
- Verify cancellations are classified separately if configured.
- Verify tags contain no IDs or sensitive data.

### 25.2. Testing Pool Saturation

In a test environment, configure a small pool, e.g., `maxSize = 1`, hold one connection intentionally, and request a second connection. Verify pending/acquire metrics rise as expected and timeouts are recorded. After releasing the first connection, verify the pool recovers.

Never perform this test in production. Clean up test pools and database fixtures afterward.

### 25.3. Testing Slow Query Alerts

- Trigger a slow query in a test database (e.g., PostgreSQL `pg_sleep` if using PostgreSQL).
- Verify timers/traces record duration per expected semantics.
- Verify the alert rule fires when conditions and time windows are satisfied.
- Verify normal fast queries do not fire the alert.

### 25.4. Testing Retries and Retry Storms

- Simulate transient failures.
- Verify retry counts and backoff behavior.
- Simulate duplicate/validation errors and verify no retries occur.
- Cancel the publisher during backoff and verify no further attempts run.
- Verify attempt metrics use bounded tags.

### 25.5. Testing Alert Routing and Runbooks

- Verify critical and warning alerts route to the right channels.
- Verify related alerts group per incident instead of flooding notifications.
- Verify dashboard/runbook links open the right environment.
- Verify alerts include owners and operation/pool context.
- Run tabletop exercises so responders practice following runbooks.

## 26. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Alerting only on CPU or HTTP 5xx | Misses pool saturation and slow queries | Combine RED/USE, pool, and DB telemetry |
| Alerting on brief high utilization | False positives at peak hours | Combine pending acquire, latency, and sustained windows |
| Watching only average query latency | Tail latency hidden | Track histograms/p95/p99 and sample counts |
| Calling end-to-end `Flux` duration "SQL duration" | Confuses slow downstream with slow DB | Separate acquire, statement, result, and response timings |
| Lumping all errors into one counter | Cannot tell connection errors from integrity errors | Classify by exception type/SQLSTATE/category |
| Parsing exception messages to classify | Brittle rules across drivers/versions | Use structured metadata |
| Raising max pool size as soon as pending rises | Can overload the database further | Investigate queries, transactions, and concurrency first |
| Inspecting only one instance's pool | Combined pools across instances exceed DB limit | Calculate system-wide connection budget |
| Not measuring pending acquire | Blind to queued requests | Export pending, acquire duration, and timeouts |
| Putting `orderId`/email/SQL in metric tags | Cardinality explosion and data leaks | Use bounded operation/category tags |
| Logging all SQL bind values | Leaks PII/secrets and bloats log volume | Use query fingerprints, redaction, and allowlists |
| Alerts without runbooks | Responders waste time hunting for next steps | Attach dashboards, owners, and investigation steps |
| Paging on every duplicate error | Alert noise from normal business conflicts | Categorize and alert on abnormal rates/trends |
| Unbounded retries | Retry storms amplify database load | Use backoff, jitter, retry filters, and deadlines |
| Never testing alert rules | Alerts fail silently or fire incorrectly | Test metrics, thresholds, routing, and runbooks |

## 27. Workflow for Implementing Observability and Alerting

Follow this rollout sequence:

1. **Define SLOs:** availability, latency, and critical operations.
2. **List signals:** HTTP RED, R2DBC pool USE, DB queries/locks, retries, and transactions.
3. **Enable instrumentation:** Actuator/Micrometer, pool metrics, tracing, and database telemetry.
4. **Standardize operations and error categories:** stable, low-cardinality enums/constants.
5. **Build dashboards:** requests, pools, operations, database server, and JVM.
6. **Design alerts:** error ratios, pool saturation, acquire timeouts, query tail latency, and retry storms.
7. **Set windows and minimum traffic floors:** filter out brief spikes and tiny denominators.
8. **Write runbooks:** investigation steps, dashboards, queries, and owners.
9. **Test:** simulate errors, pool exhaustion, slow queries, retries, and alert routing.
10. **Tune:** review false positives/negatives after deployments and after every incident.

## 28. Principles to Remember

- Monitor errors, pools, and queries alongside HTTP latency to see both impact and cause.
- Use RED for requests/services and USE for pool/database resources.
- Classify errors by exception type, SQLSTATE, or vendor code; avoid parsing messages.
- Error rates are more meaningful than raw counts when traffic varies; handle small denominators.
- Pair pool utilization with pending acquire, acquire latency, and timeouts.
- Pending acquire and acquire timeouts are more direct saturation signals than utilization alone.
- Sum maximum connections across all instances/pools and compare against the database budget.
- Never raise pool size blindly; inspect slow queries, long transactions, streams, retries, and concurrency.
- Measure p50/p95/p99 via histograms and sample counts; never rely on averages alone.
- Separate acquire time, statement time, result consumption, and end-to-end operation time.
- Use database telemetry such as `pg_stat_activity`, `pg_stat_statements`, wait events, and execution plans where appropriate.
- Assign stable operation names; never put IDs, SQL text, bind values, emails, or trace IDs into metric labels.
- Structured logs need allowlists and must omit raw SQL/bind values and secrets.
- Tracing connects HTTP, services, pools, and the database, requiring appropriate sampling and cardinality controls.
- Alerts should include persistence conditions, severity, owners, dashboards, and runbooks.
- Alert on impact/SLOs and error budgets when defined; avoid paging on every small spike.
- Track retry rates to catch retry storms; retry only bounded transient errors with backoff.
- Test instrumentation, pool saturation, slow queries, alert routing, and runbooks before production.

Designing alerts for Spring Data Relational R2DBC connects request quality to resource state and database behavior. HTTP errors and latency show user impact; pool acquired, pending, and acquire timeouts show whether the application can obtain connections; query duration and database wait telemetry pinpoint which statement or lock is causing slowdowns. When signals are classified consistently, tagged with low-cardinality operation names, thresholded against SLOs, and backed by runbooks, alerts help operations detect incidents early and fix root causes instead of merely reacting to threshold breaches.
