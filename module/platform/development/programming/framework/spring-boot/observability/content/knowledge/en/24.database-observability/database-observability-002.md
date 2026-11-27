# Datasource Micrometer in Spring Boot

Within the **Database observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, Datasource Micrometer is how we observe connection pool state and behavior through metrics. In Spring Boot applications using JDBC and HikariCP, Micrometer can collect active, idle, and max connection counts, threads waiting for connections, and connection acquisition/usage durations. These metrics help detect pool saturation, insufficient capacity, or connections held too long before failures cascade into API timeouts.

Datasource metrics do not replace database monitoring. Micrometer observes the pool from the application side: how many connections the application holds, how many requests are waiting on the pool, and what connection borrowing times look like. Database server monitoring observes the server side: query execution, locks, buffer/cache, replication, and database resources. Combining both sides helps distinguish pool exhaustion caused by the application holding connections too long from a slow database preventing connections from being returned.

In the **SPRING_BOOT_OBSERVABILITY** module, datasource metrics are one signal alongside Micrometer Observation, metrics, logs, and distributed tracing. This lesson explains how Spring Boot/Micrometer instruments a DataSource, the meaning of each metric, Actuator/Prometheus configuration, reading signs of pool saturation, controlling tags/cardinality, and correlating with query traces and logs.

## 1. Where does Datasource Micrometer sit?

With a Spring Boot-managed JDBC DataSource and a pool with appropriate integration, Actuator/Micrometer can bind pool metrics into `MeterRegistry`:

```text
Incoming HTTP request
        |
        v
   Service method
        |
        v
     JDBC call
        |
        v
   HikariCP DataSource
      |       |       |
      v       v       v
   active    idle   pending
      \       |       /
       \      |      /
        Micrometer binder
               |
               v
          MeterRegistry
               |
       +-------+--------+
       |                |
       v                v
 /actuator/metrics   Prometheus scrape
       |                |
       +-------+--------+
               v
        Metrics backend
```

| Component | Role |
| --- | --- |
| JDBC DataSource | API providing connections to the application |
| HikariCP | Manages the connection pool when selected as the pool implementation |
| Micrometer binder | Reads pool state/statistics and records them into `MeterRegistry` |
| MeterRegistry | Stores measurements in the application and forwards them to registries/exporters |
| Actuator metrics endpoint | Allows inspecting metrics inside the registry |
| Prometheus registry/endpoint | Exposes metrics in scrape format when configured |
| Metrics backend | Stores history, supports queries, dashboards, and alerts |

Spring Boot usually auto-configures HikariCP when the required dependencies are present and the DataSource is created via auto-configuration. How metrics are bound depends on the Spring Boot, Micrometer, and pool implementation/version. Do not assume every custom DataSource or externally created DataSource is instrumented automatically.

## 2. Common datasource metrics

Common metric names with HikariCP/Micrometer may carry the `hikaricp` prefix or be normalized by the registry. Commonly observed metrics include:

| Metric concept | Meaning | Answers |
| --- | --- | --- |
| Active connections | Connections currently borrowed by the application | How many connections are busy? |
| Idle connections | Connections ready to be borrowed | How much free pool capacity remains? |
| Maximum connections | Upper limit of the pool | What is the current capacity ceiling? |
| Minimum idle | Configured/maintained minimum idle target | How many idle connections does the pool try to keep? |
| Pending threads | Threads waiting to acquire a connection | Are requests queuing at the pool? |
| Connection acquire time | Time spent waiting to get a connection | Is the pool struggling to issue connections? |
| Connection usage time | Time a connection is held/borrowed | Are connections being held too long? |
| Connection creation time | Time to establish a new connection | Is opening connections to the DB slow? |

Exact names and availability depend on the binder/pool/version. For example, a registry may expose:

```text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.max
hikaricp.connections.min
hikaricp.connections.pending
hikaricp.connections.acquire
hikaricp.connections.usage
hikaricp.connections.creation
```

Some registries convert dots to underscores or rename meters during scraping. Verify actual metric names at the Actuator/Prometheus endpoint.

## 3. What do active, idle, max, and pending tell you?

Pool state gauges must be read together:

- **Active:** number of connections currently borrowed by application code.
- **Idle:** number of connections available in the pool.
- **Max:** maximum connection limit.
- **Pending:** number of threads waiting for a connection to be returned or created.

A pool with active near max is not necessarily an incident if connection hold time is short and pending is zero. Conversely, low active with high pending can indicate the pool is constrained, metrics are being read from a different DataSource, or connection acquisition has an issue that needs investigation.

Example snapshot:

| Metric | Illustrative value |
| --- | ---: |
| Active | 20 |
| Idle | 0 |
| Max | 20 |
| Pending | 14 |

This snapshot shows the pool has hit max and 14 threads are waiting. If this state persists, request latency can climb due to connection wait times. However, a single snapshot is inconclusive; examine how long it persists, acquire latency, DB health, and traffic.

### Connection utilization

\[
\text{Pool utilization} =
\frac{\text{Active connections}}{\text{Maximum connections}}
\times 100\%
\]

With active = 18 and max = 20, utilization is 90%. This is a signal worth watching when sustained, not a universal error threshold for all workloads. A pool with high utilization, zero pending, and low acquire time may be operating healthily.

## 4. Acquire time, usage time, and creation time

Three timer/histogram concepts answer three distinct questions:

**Acquire time** measures how long the application waits for the pool to provide a connection. If acquire p95 rises, the pool may lack available connections, the pending queue may be growing, or connection creation may be slow.

**Usage time** measures how long a connection is held while the application uses it. If usage p95 is high, long transactions, slow queries, code holding a connection while making external HTTP calls, or unclosed connections may be the cause.

**Creation time** measures how long it takes to open a new connection. If it increases, check DNS/network to the database, TLS, authentication, database connection limits, and handshake speed.

Do not infer query duration directly from usage time. Usage time can encompass multiple operations in a transaction, processing time between queries, and application hold time. To identify which SQL statement is slow, you need database query metrics/tracing or slow query logs.

## 5. Spring Boot auto-configuration for DataSource and HikariCP

In a typical Spring Boot JDBC application, the starter dependency and DataSource configuration can create a HikariCP pool automatically:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
```

Example configuration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: `{ORDERS_DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

This is an example configuration; usernames, URLs, pool sizes, and timeouts must reflect the real environment. Never commit passwords to source control. Expose Actuator endpoints according to network/security policies, and especially avoid leaving metrics or environment details publicly accessible unnecessarily.

`pool-name` helps distinguish DataSources in metric tags when an application has multiple pools. Use a stable functional name like `orders-pool` or `reporting-pool`, not a request ID or arbitrary tenant name.

## 6. Micrometer binders and manually created DataSources

Spring Boot can automatically bind metrics for auto-configured DataSources. If a DataSource is created manually, if multiple DataSources exist, or if pool wrappers are used, verify each pool has an appropriate binder.

With HikariCP, a Micrometer binder can read Hikari metrics via DataSource/pool integration. In some setups, a binder can be registered manually:

```java
import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.db.HikariCPMetrics;

void bindPoolMetrics(
        HikariDataSource dataSource,
        MeterRegistry registry) {
    new HikariCPMetrics(dataSource, java.util.Collections.emptyList())
            .bindTo(registry);
}
```

This snippet illustrates the binder API; packages, constructors, and auto-binding mechanisms may vary across Micrometer versions. Before binding manually, check whether Actuator has already registered metrics for the pool. Binding the same DataSource twice can cause meter registration conflicts or duplicate data.

With multiple DataSources, clarify how each pool is named/tagged and whether dashboards distinguish them. Do not share a single generic tag across all pools if per-pool diagnosis is needed.

## 7. Inspecting datasource metrics via Actuator

If the Actuator metrics endpoint is exposed, you can inspect metric names:

```http
GET /actuator/metrics
```

Then query a specific metric using its actual registry name, for example:

```http
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.pending
GET /actuator/metrics/hikaricp.connections.acquire
```

The names above are common examples; the metrics endpoint returns the registry's actual measurements and available tags. If a metric is missing:

1. Confirm Actuator and a metrics registry are included in dependencies.
2. Check whether the actual DataSource is a `HikariDataSource`.
3. Determine whether the pool is auto-configured by Spring Boot or created manually.
4. Verify the binder is registered and the DataSource is active.
5. Check metric names against actual output instead of guessing prefixes.

The Actuator metrics endpoint is for diagnosing individual meters in the registry; it does not replace a Prometheus scrape endpoint or a historical metrics backend.

## 8. Prometheus and datasource dashboards

When using a Prometheus registry/exporter, the exposition endpoint provides datasource series for the scraper:

```text
GET /actuator/prometheus
```

A basic dashboard should include:

| Panel | Metric concept | How to read |
| --- | --- | --- |
| Active vs max | Active connections and max | Pool utilization |
| Idle | Idle connections | Available idle connections |
| Pending | Pending threads | Pool wait pressure |
| Acquire p95/p99 | Acquire duration histogram | Connection acquisition latency |
| Usage p95/p99 | Connection usage duration | Connection hold duration |
| Creation duration | Connection creation time | Latency to open new connections |
| Connection timeout count | Pool timeout/error metric if available | Requests failing to acquire a connection |

Not all binders/exporters provide the exact same histogram types or timeout counters. Inspect the actual series and configure appropriate distributions. Do not write queries based on guessed metric names or units.

## 9. Identifying pool saturation

Pool saturation typically manifests across several simultaneous signals:

1. Active connections approach maximum.
2. Idle connections drop to 0 for a sustained period.
3. Pending threads increase.
4. Acquire time p95/p99 increases.
5. HTTP server latency or transaction latency rises.
6. Connection acquisition timeouts occur.

```text
Normal:
active low/moderate | idle available | pending = 0 | acquire low
                         |
                         v
High load:
active rises | idle drops | pending begins rising
                         |
                         v
Pool saturation:
active = max | idle = 0 | pending high | acquire rises
                         |
                         v
API latency rises / timeouts / request failures
```

When seeing saturation signs, do not rush to increase `maximum-pool-size`. Databases have connection limits and can become overloaded if every instance increases its pool size. Identify the bottleneck first:

- Slow queries or lock contention?
- Transactions holding connections too long?
- Code calling remote HTTP services inside transactions?
- Connection leaks or unclosed resources?
- Traffic spikes or misconfigured pool sizing?
- Database max connections or network capacity already saturated?

Increasing the pool only helps when the database has spare capacity and the workload genuinely needs higher concurrency. If the database is already bottlenecked, adding connections can make things worse.

## 10. Multiple DataSources and pool naming

An application may have DataSources for OLTP, reporting, batch jobs, or read replicas. Each pool needs a clear identity:

| Pool | Purpose | Illustrative pool name |
| --- | --- | --- |
| Primary | Business transactions | `orders-primary` |
| Read replica | Read queries | `orders-read` |
| Reporting | Reporting | `orders-reporting` |
| Batch | Background jobs | `orders-batch` |

Metric tags should use stable pool names. Do not generate pool names per tenant or request because each name can spawn a separate group of time series. If a multi-tenant system shares a pool, tenant ID should not be a default datasource metric tag.

If multiple DataSources exist but the dashboard shows only one pool, check:

- Which bean is marked primary and auto-configured?
- Are the remaining DataSources bound?
- Does a pool wrapper hide Hikari metrics?
- Is the binder registered with the right registry?
- Are pool name tags distinct?

## 11. Cardinality and tags of datasource metrics

Datasource metrics typically have few dimensions such as pool name, service instance, or DataSource role. Keep them stable:

| Tag | Should use? | Reason |
| --- | --- | --- |
| Fixed pool name | Yes | Distinguishes pools in the application |
| Service name | Yes, usually a resource attribute | Identifies the service |
| Instance ID | Depends on backend/resource model | Distinguishes replicas if needed |
| Normalized database host | Possible | Diagnoses bounded DB endpoints |
| Per-request tenant ID | No | Cardinality grows with tenants |
| Verbatim SQL statement | No | Large, dynamic, and potentially sensitive |
| Query parameter values | No | Creates unbounded series |
| Connection ID | No | Nearly unique per connection |

Do not attach raw SQL or query hashes to datasource pool gauges/timers when the goal is pool health. SQL-level metrics/tracing need a separate pipeline with dedicated cardinality limits, normalization, and redaction.

## 12. Correlating datasource metrics with queries, logs, and traces

Datasource metrics show how the pool is handling load; database query tracing/logs help pinpoint the statement or transaction causing the load:

```text
HTTP request latency p95 increases
          |
          v
JDBC connection acquire p95 increases?
          |
     +----+----+
     |         |
    Yes        No
     |         |
     v         v
Pool / DB   Investigate app or
contention  other dependencies
     |
     v
Trace spans / SQL observation / DB slow query logs
     |
     v
Identify slow query, lock, or long-held connection
```

When JDBC tracing is configured, traces can show spans for database operations; capabilities and detail levels depend on the instrumentation/driver. Do not assume every JDBC call automatically produces a span just because Hikari metrics exist.

Logs can record correlation ID/trace ID alongside the operation, DataSource role, and exception type. Do not log passwords, connection URLs with credentials, sensitive raw parameters, or SQL containing user data. Use query fingerprints/normalized statements if the system has safe sanitization mechanisms.

Metrics do not need Trace ID as a tag. If the backend supports exemplars, a sample metric can be linked to a representative trace without inflating cardinality across the entire series.

## 13. Connection leaks, long transactions, and pool timeouts

| Symptom | Metric/signal | Cause to investigate |
| --- | --- | --- |
| Insufficient pool capacity | Active near max, pending rising | Sizing or high concurrency |
| Slow query | Usage time rising, DB query duration rising | Execution plan, indexes, locks |
| Slow acquire | Acquire time rising, low idle | Pool saturation or slow creation |
| Slow connection creation | Creation time rising | DNS/network/TLS/auth/database load |
| Connection leak | Active rises and stays high after workload | Unclosed resources or hung transactions |
| Long transaction | Long usage time, lock waits | Overly broad transaction scope |
| Pool timeout | Acquire exceeds `connectionTimeout` | Pool failed to issue connection before deadline |

HikariCP can support a leak detection threshold to warn when a connection is held longer than a threshold. Enable it only with an appropriate threshold because leak detection logs can create noise during legitimate long queries. Leak detection is a diagnostic aid, not a substitute for proper connection/transaction management.

Example:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 30000
```

The 30-second value is just an example; set it based on normal transaction durations and operational goals. If the threshold is lower than legitimate workloads, warning logs can be misleading.

## 14. Testing datasource metrics

An integration test should check both that metrics appear and that they change during JDBC activity:

1. Start the application context with a test DataSource.
2. Verify `MeterRegistry` contains the expected datasource/pool metrics.
3. Execute a simple query via a repository/`JdbcTemplate`.
4. Check that acquire/usage or query-related metrics increase according to binder semantics.
5. Apply controlled concurrency to observe active/pending if the test pool is small and reproducible.
6. Verify the pool name tag is accurate and no request/tenant/raw SQL tags are present.
7. Check the Actuator endpoint and Prometheus exposition if configured.

Do not write tests that depend on exact millisecond acquire timings in CI because timings fluctuate across machines. Prefer verifying meter registration, tag sets, monotonic counters/counts, or pool states under controlled test conditions.

### Investigation scenario

A service shows:

| Metric | Observed value |
| --- | --- |
| Active | 30 |
| Max | 30 |
| Idle | 0 |
| Pending | 45 |
| Acquire p95 | 1.8 seconds |
| JDBC usage p95 | 2.4 seconds |
| HTTP server p95 | 2.7 seconds |

These numbers indicate the pool is under pressure. Next steps:

- Check database query latency and lock waits.
- Open a representative request trace to see which JDBC operation holds the connection longest.
- Check whether the transaction wraps remote HTTP calls or non-database processing.
- Compare the sum of pool sizes across all app instances against the DB connection limit.
- Review connection timeout/leak warnings and workload concurrency.

Do not conclude you should simply raise max to 60. If the DB is struggling with slow queries, doubling the pool can increase contention.

## 15. Case study exercise

A Spring Boot application runs 4 replicas, each using HikariCP with a maximum pool size of 25. Dashboards show active frequently hitting 25, pending rising during peak hours, and acquire p99 climbing to 2 seconds. The database has a limit of 120 connections for this application.

**Questions:**

1. What is the total maximum number of connections under the current configuration?
2. Why could increasing each replica's pool size to 40 be dangerous?
3. Which metrics should you inspect to distinguish slow queries from insufficient pool capacity?
4. What does high usage time suggest?
5. How can pool metrics be correlated with tracing/logs?

**Analysis hints:**

- The current total pool max is 4 × 25 = 100 connections, not counting other processes/jobs that may connect to the DB.
- Raising it to 40 brings the total max to 160, exceeding the 120-connection limit even before accounting for overhead and other workloads.
- Inspect active/idle/max/pending, acquire duration, usage duration, creation duration, connection timeouts, DB query latency, and lock waits.
- High usage time may point to slow queries, long transactions, or code holding connections while doing non-DB work.
- Use datasource pool name and low-cardinality dimensions in metrics; open traces with JDBC spans and search logs by correlation/trace ID. Never put raw SQL or connection IDs into metric tags.

### Completion checklist

| Topic | Can explain/verify |
| --- | --- |
| Datasource binder | Understand how Micrometer collects pool metrics |
| Active/idle/max/pending | Read pool health state |
| Acquire/usage/creation | Distinguish different latency components |
| Spring Boot/HikariCP | Configure pool and observe DataSource |
| Actuator/Prometheus | Verify actual metric names and tags |
| Pool saturation | Identify active=max, idle=0, rising pending |
| Multi-datasource | Set stable pool names and distinguish pools |
| Cardinality | Avoid putting tenant, connection ID, or raw SQL in tags |
| Database tracing | Correlate metrics with query spans and logs |
| Capacity planning | Sum pool sizes across all replicas |
| Connection leaks | Use usage/leak detection properly |
| Testing | Verify binder, tags, and metric behavior |

**Key takeaway:** Datasource Micrometer shows how the application uses its connection pool. Active, idle, max, and pending describe state; acquire, usage, and creation durations help pinpoint bottlenecks. In Spring Boot, verify actual binders and metric names, assign stable pool names, expose Actuator/Prometheus securely, and monitor multiple signals together. When pool saturation appears, inspect query latency, locks, transaction scope, connection leaks, and total pool capacity across all replicas before increasing max pool size. Combine pool metrics with JDBC traces and structured logs to isolate root causes at the right layer.
