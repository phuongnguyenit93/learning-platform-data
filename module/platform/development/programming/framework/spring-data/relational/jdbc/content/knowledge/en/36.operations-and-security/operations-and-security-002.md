# Observing Connection Pools, Slow Queries, and Database Errors

In production, a Spring Data JDBC application can run into various issues: connection pool exhaustion, slow queries, database overload, long-held locks, or spikes in constraint errors. Looking only at application logs or merely checking whether the database is up makes it hard for operations teams to pinpoint the root cause and impact.

Effective observability requires combining three data sources:

- **Metrics:** quantitative trends such as active/pending connections, connection acquisition time, query latency, and error rates.
- **Logs:** specific event details, exceptions, SQL fingerprints, and contextual information.
- **Traces:** the path of a request across services, repositories, JDBC, and dependent components.

With Spring Data JDBC, you must observe the connection pool, JDBC operations, and the database engine. This lesson covers setting up dashboards, detecting slow queries, classifying database errors, configuring alerts, and building a safe diagnostic workflow.

## 1. The Three Layers to Observe

A request can pass through multiple layers before returning a result:

```text
Client request
    |
    v
Application service
    |
    v
Spring Data JDBC repository
    |
    v
DataSource / HikariCP
    |
    v
JDBC driver
    |
    v
Database engine
```

Each layer answers a different set of questions:

| Layer | Operational questions |
| --- | --- |
| Application | Which requests are slow? What is the error rate? |
| Repository/JDBC | Which operations emit the most SQL? Which statements are slow? |
| Connection pool | Are idle connections available? Are requests waiting on the pool? |
| Database | What are the query plans, locks, I/O, CPU, and connection utilization? |

Do not conclude the database is slow just because an endpoint is slow. The endpoint may be spending time mapping large data, waiting on the pool, calling external services, or serializing the response.

Similarly, database health reporting UP does not mean queries are running fast or that the pool still has capacity.

## 2. Observing the HikariCP Connection Pool

Spring Boot typically uses HikariCP as the connection pool for a JDBC DataSource. The pool holds a set of physical connections and lends them out to database operations, avoiding the cost of creating a new connection for every statement.

Metrics commonly provided when HikariCP is integrated with Micrometer:

| Metric | Meaning |
| --- | --- |
| `hikaricp.connections.active` | Number of connections currently borrowed by the application. |
| `hikaricp.connections.idle` | Number of idle connections in the pool. |
| `hikaricp.connections.pending` | Number of threads waiting for a connection. |
| `hikaricp.connections.max` | Maximum connection limit. |
| `hikaricp.connections.min` | Configured minimum idle count. |
| `hikaricp.connections.acquire` | Time spent waiting to acquire a connection. |
| `hikaricp.connections.usage` | Time a connection is held before being returned to the pool. |
| `hikaricp.connections.creation` | Time spent creating a physical connection. |
| `hikaricp.connections.timeout` | Number of acquisition timeouts. |

Metric names and tags may vary by HikariCP/Micrometer version and registry configuration. Verify the actual metric list from Actuator or the registry in use.

### 2.1. Understanding Active, Idle, and Pending

The three most important metrics when investigating a pool:

- **High active:** many requests are holding connections.
- **Low idle:** few connections remain ready in the pool.
- **Pending greater than 0:** threads are waiting for connections to be returned.

A single point-in-time snapshot is not enough to conclude the pool is exhausted. Observe trends over time and correlate them with request throughput and latency.

Example:

```text
maximum connections = 20
active connections  = 20
idle connections    = 0
pending borrowers   = 12
acquire p95         = 850 ms
```

If this state persists while request latency increases, the pool may be a bottleneck. Next, find why connections are held for so long: long transactions, slow queries, lock waits, or code not returning connections.

### 2.2. Pool Configuration and Timeouts

Example configuration:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
```

These are illustrative values, not a universal configuration for every system. Choose them based on database capacity, application instance count, concurrency, and connection hold time.

`connection-timeout` limits how long a thread waits for the pool to hand out a connection. When the timeout expires, Hikari throws an acquisition timeout error. Increasing the timeout can make requests wait longer without solving a connection shortage.

### 2.3. Total Pool Size Across Multiple Instances

If a service runs multiple replicas, the maximum total connections can be approximated as:

```text
total possible connections
    = maximumPoolSize per instance
      × number of application instances
```

For example, 6 instances each with a maximum pool size of 20 can open up to 120 connections to the database. You must also account for connections from jobs, migrations, admin tools, and other services.

Do not look only at a single instance's pool size. Compare total demand against database limits and reserve capacity for administration and replication.

### 2.4. Leak Detection and Connection Usage

HikariCP provides `leakDetectionThreshold` to log when a connection is borrowed longer than a configured threshold. Example:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 60000
```

The 60-second threshold is only an example. If set too low, valid but long transactions or queries can trigger false alarms. Leak detection helps find where connections are held for a long time; it does not by itself prove a connection is permanently leaked.

When you see a warning, inspect the stack trace where the connection was borrowed, transaction duration, query latency, and whether resources are closed/returned across all exception branches.

## 3. Exposing Metrics with Spring Boot Actuator

Spring Boot Actuator provides health and metrics endpoints. With an appropriate Micrometer registry, the application can export metrics to Prometheus or other monitoring backends.

Example configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
```

Expose only the endpoints that are genuinely needed. Management endpoints can reveal details about the environment, beans, configuration, or internal state. Restrict them using authentication, authorization, and network policies.

### 3.1. Checking Health

The `/actuator/health` endpoint provides overall status. When the database health indicator is enabled, the health response can indicate whether the datasource is reachable.

Health checks are useful for readiness/availability, but do not replace performance dashboards. A database can respond quickly to a health check while a specific business query is very slow.

In systems with liveness/readiness probes, distinguish:

- **Liveness:** whether the process is still alive and able to continue running.
- **Readiness:** whether the instance is ready to receive traffic.
- **Dependency health:** whether the database or dependent service is available.

Do not fail liveness merely because the database temporarily loses connectivity if repeated restarts will not help recover and could cause a restart storm. Readiness policies should match the architecture and how the system handles dependency outages.

### 3.2. Inspecting Specific Metrics

Once Actuator is configured and the endpoint is exposed, you can query a metric by name, for example:

```text
/actuator/metrics/hikaricp.connections.active
/actuator/metrics/hikaricp.connections.pending
/actuator/metrics/jdbc.connections.active
```

Available metric names depend on the DataSource pool and registry. The metrics endpoint is handy for checks in administrative environments; production dashboards normally pull data from Prometheus/OTLP or an equivalent backend rather than polling individual metrics manually.

### 3.3. Metrics for Application Services

Add Timers/Counters at use-case boundaries to see which operations generate database load:

```java
@Service
public class OrderQueryService {

    private final OrderRepository orders;
    private final Timer timer;

    public OrderQueryService(
            OrderRepository orders,
            MeterRegistry registry) {
        this.orders = orders;
        this.timer = registry.timer("app.orders.search");
    }

    public List<Order> findPending() {
        return timer.record(
            () -> orders.findByStatus(OrderStatus.PENDING)
        );
    }
}
```

You can add counters for errors grouped by exception category, but tags must have low cardinality. Never place order IDs, emails, full SQL, or exception messages in metric labels.

## 4. Observing Slow Queries

Slow queries can stem from several causes:

- Missing indexes or an index not chosen by the optimizer.
- A query scanning too many rows.
- Expensive joins, sorts, or aggregations.
- Lock waits or other transactions holding locks.
- Insufficient database CPU, memory, or I/O capacity.
- Parameter distribution leading to a suboptimal query plan.
- Large result sets taking time for the driver and application to read/materialize.

Combine statement timing in the application with database query statistics to find the true cause.

### 4.1. Measuring Query Duration at the JDBC Boundary

You can use datasource-proxy or P6Spy to observe statement duration:

```java
public class QueryTimingListener implements QueryExecutionListener {

    private final MeterRegistry registry;

    public QueryTimingListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {
    }

    @Override
    public void afterQuery(
            ExecutionInfo executionInfo,
            List<QueryInfo> queryInfoList) {

        Timer.builder("app.jdbc.statement")
            .tag("outcome",
                executionInfo.isSuccess() ? "success" : "error")
            .register(registry)
            .record(
                executionInfo.getElapsedTime(),
                TimeUnit.MILLISECONDS
            );
    }
}
```

This is a simplified listener example; it requires the datasource-proxy dependency and wrapper DataSource configuration so repositories use the wrapped DataSource. Add operation/query fingerprint classification in a dedicated collector if you need statistics grouped by SQL category.

Proxy timing measured at the JDBC boundary can include some driver/network overhead. It does not replace internal database execution time. To know whether the database spends time on scans, joins, sorts, or locks, check telemetry/plans from the database itself.

### 4.2. Using Query Fingerprints Instead of Raw SQL as Metric Tags

Queries may differ only by parameter values:

```sql
SELECT * FROM purchase_orders WHERE id = 101;
SELECT * FROM purchase_orders WHERE id = 102;
SELECT * FROM purchase_orders WHERE id = 103;
```

Putting full SQL into metric tags can create a separate time series per parameter value. Instead, use a query fingerprint/normalized SQL or a stable operation group.

Never put sensitive parameters into fingerprints, logs, or traces. When you need to debug a specific query, use protected logs/tracing with appropriate retention and access controls.
## 5. Using Database Telemetry to Find Resource-Heavy Queries

JDBC timing shows how long the application waited on a statement. Database telemetry shows what resources the query consumed and why it was slow.

Tools by database:

| Database | Observation tools |
| --- | --- |
| PostgreSQL | `pg_stat_statements`, slow query log, `EXPLAIN (ANALYZE, BUFFERS)`. |
| MySQL | Performance Schema, statement digest summary, slow query log, EXPLAIN. |
| SQL Server | Query Store, actual execution plan, wait statistics. |
| Oracle | AWR/ASH and SQL monitoring depending on configuration/license. |

For example, in PostgreSQL, `pg_stat_statements` aggregates queries in normalized form and provides call counts, execution times, row counts, and I/O statistics. It helps find queries with high total time or high mean latency.

Do not rank solely by the single slowest query. A query taking 200 ms once can have less impact than a query taking 20 ms executed tens of thousands of times.

### 5.1. Distinguishing Mean Latency from Total Time

Track all of the following:

- Calls: how many times the query is invoked.
- Mean execution time: average duration per call.
- Total execution time: cumulative duration.
- Rows: number of rows returned or affected.
- Shared block reads/hits or equivalent I/O.
- Lock/wait time if provided by the database.

A query with low mean latency but very high call count often suggests an N+1 pattern or repeated round-trips. A query with low call count but high total time may be a heavy report or a poor query plan.

### 5.2. Using EXPLAIN to Inspect Query Plans

Once a slow query is identified, take a representative query and inspect its execution plan. For PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, total_amount
FROM purchase_orders
WHERE customer_id = 42
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;
```

Inspect these aspects:

- Scan type: sequential scan vs. index scan.
- Estimated rows vs. actual rows.
- Join strategy and join order.
- Whether sorts/hashes spill to disk.
- Buffer hits/reads and I/O.
- Which predicate filters fewer rows than expected.

`EXPLAIN ANALYZE` actually executes the query to measure real timing. Run it only on safe queries in appropriate environments; for write statements or very heavy queries, evaluate side effects and load beforehand.

## 6. Observing Database Errors

Not every exception is an infrastructure failure. Classify errors according to Spring Data exception groups to know what action to take.

| Group | Examples | Operational meaning |
| --- | --- | --- |
| Integrity violation | `DuplicateKeyException`, `DataIntegrityViolationException` | Invalid data or constraint conflict; could be a business error or bug. |
| SQL/schema | `BadSqlGrammarException` | Incompatible query or schema; requires code/migration fix. |
| Concurrency | `OptimisticLockingFailureException`, lock exceptions | Update competition or lock contention. |
| Timeout | `QueryTimeoutException` | Query or lock wait exceeded threshold. |
| Resource failure | `DataAccessResourceFailureException` | Database/connection/resource unavailable. |
| Unknown JDBC | `UncategorizedSQLException` | Unclassified by translator; inspect cause, SQLState, and vendor code. |

Maintain counters by exception class or stable error category:

```text
app.database.errors{category="integrity"}
app.database.errors{category="timeout"}
app.database.errors{category="resource"}
app.database.errors{category="concurrency"}
app.database.errors{category="sql"}
```

Do not use the exception message as a tag because messages can contain SQL, parameters, or constantly changing data. If vendor codes need analysis, record them in redacted logs/traces instead of creating thousands of metric labels.

### 6.1. Tracking Error Rates, Not Just Counts

100 errors per minute can be severe for a service receiving only 200 requests per minute, yet far less alarming for a system handling millions of requests per minute.

Track error rate as a ratio:

```text
database error rate
    = failed database operations
      / total database operations
```

Combine error rates with request throughput, latency, and pool state. For example, rising resource failures alongside acquisition timeouts can point to a database outage or the pool being unable to open connections.

### 6.2. Preserving the Cause Chain and SQLState in Logs

When logging exceptions, preserve the stack trace and cause. If the cause is an SQLException, you can log SQLState/vendor code according to policy:

```java
Throwable cause = ex;

while (cause != null && !(cause instanceof SQLException)) {
    cause = cause.getCause();
}

if (cause instanceof SQLException sqlException) {
    log.warn(
        "Database operation failed: sqlState={}, vendorCode={}",
        sqlException.getSQLState(),
        sqlException.getErrorCode(),
        ex
    );
}
```

This snippet illustrates finding SQLException in the cause chain; in practice, an SQLException can also chain additional exceptions via `getNextException()`. Do not log raw parameters or messages containing personal information unless filtered.

## 7. Designing Dashboards and Alerts

An operational dashboard should combine application, pool, and database metrics.

### 7.1. Connection Pool Dashboard

Display:

- Active/idle/max connections.
- Pending borrowers.
- Connection acquisition p50/p95/p99.
- Connection usage duration.
- Acquisition timeout count.
- Physical connection creation rate.

### 7.2. SQL Dashboard

Display:

- Statement counts by SELECT/INSERT/UPDATE/DELETE.
- Query latency p50/p95/p99.
- Top query fingerprints by total execution time.
- Top queries by calls.
- Slow query count.
- Rows returned/affected if supported by instrumentation.

### 7.3. Error Dashboard

Display:

- Database error rate.
- Exception counts by category.
- Deadlock/lock timeout counts if provided by the database.
- Optimistic locking conflict rate.
- Connection acquisition failures.
- Database health and connection utilization.

### 7.4. Alerting Principles

There is no single threshold that fits every system. Alerts should be based on the service's SLOs and baseline.

Examples of conditions to consider:

| Signal | When to alert |
| --- | --- |
| Pending connections | Steadily increasing over multiple windows while acquisition latency rises. |
| Active/max ratio | Sustained near 100% while request latency degrades. |
| Acquisition timeout | New timeouts appear or rate exceeds operational threshold. |
| Query p95/p99 | Exceeds SLO or spikes abnormally compared to baseline. |
| Slow query volume | Sudden surge in queries exceeding the slow threshold. |
| Database error rate | Error rate exceeds threshold and impacts requests. |
| Database availability | Prolonged health check failures or multiple instances losing connectivity together. |

Use sustained alert durations (for duration) to avoid paging on brief spikes. Severe failures such as database unavailability may need faster alerting than pool utilization alerts.

## 8. Diagnosing Pool Exhaustion Step by Step

When pending connections and acquisition times rise:

1. Confirm whether the issue affects one instance or all instances.
2. Inspect active, idle, pending, and acquisition timeouts.
3. Check connection usage duration and transaction duration.
4. Look for slow queries or lock waits holding connections.
5. Check whether code makes HTTP calls, publishes messages, or performs heavy CPU work inside transactions.
6. Compare database connection limits against total connections across all services.
7. Check connection leak warnings and stack traces.
8. Only adjust pool size after confirming the database has spare capacity and the root cause is not long-held transactions/queries.

Example:

- Active is constantly equal to max.
- Pending increases.
- Query latency also increases.
- Database CPU/lock waits are high.

Increasing pool size in this situation can push more concurrent work onto the database and worsen overload. Investigate query plans, locks, and transaction durations first.

Another case:

- Active equals max.
- Query latency is low.
- Usage duration is very high.
- Logs show the service calling an external API inside a transaction.

Here, connections are held while waiting on the network. Shorten the transaction and move side effects after commit.

## 9. Diagnosing Slow Queries Step by Step

When query p95/p99 rises:

1. Identify the query fingerprint/use case experiencing higher latency.
2. Compare calls, total time, rows, and error rate.
3. Check acquisition time to rule out pool waiting.
4. Obtain a representative SQL/parameter sample via protected traces or logs.
5. Inspect query statistics and execution plan in the database.
6. Examine indexes, row estimates, joins, sorts, locks, and I/O.
7. Check result set size and mapping/serialization time.
8. Modify the query/index/projection/pagination based on evidence.
9. Re-run the same workload and compare percentiles, throughput, pool, and database resources.

Do not optimize a query just because it looks long. A complex SQL statement can have a great plan; a simple query can scan millions of rows if an index is missing.

## 10. Integrating Tracing and Logs

Distributed tracing links a request to the JDBC operations inside it. With proper instrumentation, a trace can show:

```text
HTTP POST /orders                 420 ms
  service.placeOrder              395 ms
    repository.save               120 ms
      JDBC INSERT purchase_orders  35 ms
      JDBC INSERT order_lines      48 ms
      JDBC UPDATE inventory        22 ms
    outbox.insert                  18 ms
```

The example above only illustrates span structure. Actual span names and detail levels depend on the tracing instrumentation used.

Key principles:

- Include trace ID/span ID in logs to correlate events.
- Keep metric tag cardinality low; traces are a better place for per-request detail.
- Do not record sensitive SQL parameters in span attributes.
- Sampling must balance overhead with the ability to investigate rare errors.
- Retain traces for failed or slow requests according to policy if your system supports tail sampling.

Metrics show trends, logs show event details, and traces show timing relationships across steps. These three sources should complement one another.

## 11. Protecting Operational Telemetry

Database telemetry can contain sensitive information. Enforce controls:

- Actuator endpoints accessible only from authorized networks/permissions.
- Expose health/metrics/prometheus only if genuinely needed.
- Do not publicly expose endpoints containing environment/configuration or bean details.
- Redact SQL parameters, tokens, emails, and personal data.
- Restrict read access to slow query logs and database performance schemas.
- Configure retention and access permissions for logs/traces.
- Do not put raw SQL, user IDs, or query parameters in metric labels.

Health details can reveal hosts, database names, or dependency states. Display them only to authorized callers.

## 12. Testing Instrumentation and Alerts

To ensure observability works:

- Integration tests verify Hikari/DataSource metrics appear in the registry.
- Tests verify the query proxy counts SELECT/INSERT and records elapsed time.
- Error-path tests confirm DataAccessException is counted in the right category.
- Tests verify dashboard queries use stable tags and do not create labels per ID/SQL.
- Validate alert rules using simulated data or staging environments.
- Verify health endpoints do not leak details to unauthorized callers.

Do not rely on unit tests to prove a real database is healthy. Health and pool behavior require integration/operational verification against a real datasource.

## 13. Common Operational Pitfalls

| Symptom | Possible cause | Action |
| --- | --- | --- |
| Pending connections rising | Busy pool or connections held too long. | Inspect usage time, query latency, and transaction duration. |
| Active always equals max | Too much concurrent work or long transactions. | Investigate workload and database capacity before growing the pool. |
| Acquisition timeout | Pool cannot hand out a connection before timeout. | Check pending count, database availability, and connection leaks. |
| Query p99 rising while pool is normal | Database query plan, locks, or result size. | Check query statistics and EXPLAIN. |
| Health UP yet endpoints slow | Health check only verifies basic connectivity. | Inspect latency, query stats, and pool metrics. |
| Slow query log surging | Query plan regression, missing index, or higher load. | Group by fingerprint and inspect calls/total time. |
| Database error rate spiking | Constraints, timeouts, outage, or schema-deploy mismatch. | Classify DataAccessException and correlate with migrations/deploys. |
| Leak detection warning | Connection held too long or not returned properly. | Inspect stack trace and transaction scope. |
| Metrics backend overloaded | High tag cardinality or exporting too much SQL detail. | Normalize tags and move details to controlled logs/traces. |
| Flappy alerts | Thresholds too sensitive or no hold duration. | Use baselines, SLOs, and appropriate alert durations. |

## 14. Routine Operational Workflow

A practical workflow may include:

1. Monitor dashboards for pool, query latency, database error rates, and request SLOs.
2. Periodically review top queries by total time and call count.
3. Configure alerts for pending/acquisition timeouts, slow queries, and database availability.
4. When an alert fires, use trace IDs to locate affected requests.
5. Correlate JDBC statement timing with database execution statistics.
6. Check connection usage, transaction duration, and lock waits.
7. Document root cause, blast radius, and changes made.
8. Re-run workloads after tuning to confirm improvement.
9. Periodically review telemetry access permissions, retention, and redaction.

> **Production observability requires combining pool metrics, query statistics, exception rates, logs, and traces.** Pending/active indicates connection pressure; JDBC timing reveals which statements are slow; database telemetry explains query plans, locks, and I/O; DataAccessException identifies error types. Health checks reflect only basic availability, while alerts must be grounded in service baselines and SLOs.

### References

- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics, Micrometer, and datasource instrumentation.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposing and securing management endpoints.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): connection pool settings, timeouts, and leak detection.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): latency timers and percentiles/histograms.
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): tracing and JDBC instrumentation.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query statistics by fingerprint.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): execution plan analysis.
- [MySQL — Performance Schema](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html): observing SQL activity and database resources.
- [Spring Data JDBC — Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repositories and persistence behavior.
