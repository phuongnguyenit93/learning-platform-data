# Data Source Metrics in Spring Boot: Observing Connection Pools and Database Queries

In the **Spring Boot metrics** chapter of the **SPRING_BOOT_OBSERVABILITY** module, *data source metrics* describe the usage state of database connection pools managed by the application. For Spring Boot applications using JDBC and a connection pool such as HikariCP, metrics help answer: how many connections are busy or idle, does the pool still have capacity to hand out connections, are threads waiting, and are connection acquisition timeouts rising?

This is one piece of observability alongside **Micrometer Observation, metrics, logs, and distributed tracing** to investigate errors, latency, and application behavior in production. However, **pool metrics alone do not tell you which SQL statement is slow**. To confirm root cause, cross-check them against business operation durations, queries and transactions, logs, distributed traces, and database server metrics.

## 1. What are DataSource and connection pool metrics measuring?

In JDBC, `javax.sql.DataSource` is the interface supplying database connections. Many Spring Boot applications use a **connection pool** implementation (typically HikariCP) to reuse connections rather than opening a new physical connection for every request.

```text
HTTP request -> Service -> Repository / JdbcTemplate / JPA
                              |
                              v
                          DataSource
                              |
                              v
                     HikariCP connection pool
                       |            |
                 idle connections  busy connections
                       \            /
                            Database

Pool metrics: active, idle, max, min, pending, acquire, timeout...
Other-layer signals: HTTP latency, business observation, SQL duration,
                     transaction duration, DB locks/CPU/I/O...
```

A request can take 2 seconds even if its SQL query runs in 20 ms if it had to wait 1.8 seconds just to borrow a connection. Conversely, the pool may have plenty of idle connections while a SQL query is slow due to a missing index or lock wait. The two situations require completely different fixes.

| Observation layer | Questions it can answer | What cannot be concluded from this layer alone |
| --- | --- | --- |
| Data source/pool metrics | How many connections are busy/idle/waiting, is the pool exhausted? | Which SQL is slow and why |
| HTTP server metrics | Which endpoint is slow/failing, when did load rise? | Whether latency comes from borrowing connections or running SQL |
| Database client spans/metrics (if instrumented) | At which step in the trace DB calls occurred and how long they took | All database-side CPU, I/O, or lock causes |
| Database server metrics | Sessions, locks, CPU, I/O, slow queries | Specific business requests without correlation |
| Logs and exceptions | Timeouts, connection leak warnings, network/auth errors | Latency distributions and error rates across all requests |

Note: applications using **R2DBC** do not necessarily emit JDBC `DataSource` metrics. Reactive connection pools have their own instrumentation and metric names per driver/library; do not apply JDBC/HikariCP examples verbatim to every database technology.

## 2. How does Spring Boot collect data source metrics?

Spring Boot Actuator provides auto-configuration for Spring-managed `DataSource` beans. When a supported implementation and metadata provider are present, connection pool data is fed into the Micrometer `MeterRegistry`. HikariCP is normally the default pool when using a matching JDBC starter without configuring another pool.

```text
Spring Boot DataSource bean
      |
      +--> DataSource pool metadata
      |          |
      |          +--> jdbc.connections.* --> MeterRegistry
      |                                      |
      |                                      +--> /actuator/metrics
      |                                      +--> Prometheus / OTLP exporter
      |
      +--> HikariCP instrumentation (if present)
                 |
                 +--> hikaricp.* --> MeterRegistry
                                        |
                                        +--> Backend / dashboard / alert
```

Two common naming groups:

- **`jdbc.connections.*`:** generic pool measurements such as `active`, `idle`, `max`, and `min` when Boot can read pool metadata.
- **`hikaricp.*`:** detailed HikariCP metrics such as pending threads, acquire/usage durations, timeouts, or creation time when Hikari metrics are configured.

Not every Spring Boot version, custom `DataSource`, or pool setup automatically generates both metric groups. A proxied `DataSource`, unsupported pool, custom replaced registry, or missing dependency can cause meters to be absent. **Inspect live metrics on your running version** before designing alerts.

Names in `/actuator/metrics` are **Micrometer logical names**. With Prometheus, dots usually convert to underscores; counters, timers, and histograms can produce series with suffixes such as `_total`, `_seconds_count`, `_seconds_sum`, and `_bucket`. Never assume Actuator names and PromQL names are identical.

## 3. Example setup with Spring Boot, Actuator, and HikariCP

A Spring Boot project using JDBC/PostgreSQL can declare the following Maven dependencies. This example assumes Spring Boot parent/BOM version management:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

If the project already uses the JPA starter, you do not need to add the JDBC starter just to get metrics. Illustrative `application.yml` configuration:

```yaml
spring:
  application:
    name: orders-service
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 16
      minimum-idle: 4
      connection-timeout: 30000 # milliseconds

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
```

Explanation:

1. Environment variables supply username/password; never hardcode credentials in real files or logs. The `localhost` URL is for local testing only.
2. `pool-name` identifies the pool in Hikari labels; the exact label key may be `pool` or `name` depending on the meter/implementation. Verify in the endpoint.
3. `maximum-pool-size: 16` and `minimum-idle: 4` are **example numbers**, not universal optimal values. Size them based on replica count, DB connection limits, load, and connection hold times.
4. `connection-timeout: 30000` is the maximum wait time to borrow a connection in Hikari configuration (30 seconds), **not the SQL query timeout**.
5. Metrics/Prometheus endpoints should be exposed only within management networks or with proper access protection. Never expose all Actuator endpoints to the public Internet.

In the configuration above, `${DB_USER}` and `${DB_PASSWORD}` are placeholders resolved by Spring from the environment; `${spring.application.name}` references the application name setting. Never write real credentials into documentation or telemetry.

## 4. Key indicators and how to interpret them

### 4.1. JDBC pool metadata group

Common Micrometer logical names when Spring Boot reads pool metadata:

| Meter | Typical type | Meaning |
| --- | --- | --- |
| `jdbc.connections.active` | Gauge | Number of connections currently borrowed/in use in the pool |
| `jdbc.connections.idle` | Gauge | Number of idle connections available to hand out |
| `jdbc.connections.max` | Gauge | Upper connection bound configured/reported by the pool |
| `jdbc.connections.min` | Gauge | Lower connection bound configured/reported by the pool |

Some metadata providers do not supply every value, or use sentinel values when bounds are unknown. Do not compute utilization ratios when `max` is invalid.

**High active connections alone do not mean the pool is bottlenecked.** A pool might use 12/16 connections and still hand out connections immediately. Stronger signals to investigate are `active` pinned near `max`, low `idle`, sustained `pending`, and rising timeouts or acquire durations.

### 4.2. HikariCP group

When Hikari metrics are active, common meters prefixed with `hikaricp.connections` include:

| Common meter | Type | Operational meaning |
| --- | --- | --- |
| `hikaricp.connections.active` | Gauge | Connections currently borrowed |
| `hikaricp.connections.idle` | Gauge | Idle connections |
| `hikaricp.connections.pending` | Gauge | Threads currently waiting for a connection from the pool |
| `hikaricp.connections.max` / `min` | Gauge | Configured pool limits |
| `hikaricp.connections.acquire` | Timer | Time spent **waiting until a connection is acquired** |
| `hikaricp.connections.usage` | Timer | Time the application **holds a connection** |
| `hikaricp.connections.creation` | Timer | Time to create a new physical connection |
| `hikaricp.connections.timeout` | Counter | Count of failures to acquire a connection before timeout |

Exact names, units, types, and backend labels depend on Hikari version, Micrometer registry, and exporter; this table is a conceptual map—verify against live runtime data.

**Acquire is not query latency.** Long acquire waits can stem from an exhausted pool or slow physical connection creation. **Usage is not SQL duration either:** a connection can be held open across a transaction while waiting on application logic, network calls, or other work between queries.

An illustrative bottleneck chain: long-running transaction → `usage` rises → `active` hits `max` → `pending` rises → `acquire` rises → `timeout` rises. This is a hypothesis to verify via traces, DB sessions/locks, and logs—not a certainty from metrics alone.

## 5. Inspecting metrics via Actuator and exporters

After starting the application, test the permitted endpoints:

```bash
# List metric names known to Actuator:
curl -s http://localhost:8080/actuator/metrics

# Inspect a logical metric, if present:
curl -s http://localhost:8080/actuator/metrics/jdbc.connections.active

# Inspect Hikari pending, if instrumentation is available:
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.pending

# Inspect exported names after conversion for Prometheus:
curl -s http://localhost:8080/actuator/prometheus
```

`/actuator/metrics/<meter-name>` normally returns JSON with `measurements` and `availableTags`. **Structural illustration** (actual numbers and tags may vary):

```json
{
  "name": "jdbc.connections.active",
  "description": "Active connections",
  "measurements": [
    { "statistic": "VALUE", "value": 11.0 }
  ],
  "availableTags": [
    { "tag": "name", "values": ["orders"] }
  ]
}
```

Prometheus series might look like:

```text
jdbc_connections_active{application="orders-service",name="orders"} 11.0
jdbc_connections_max{application="orders-service",name="orders"} 16.0
```

The `name="orders"` tag is only an example. Hikari may use a `pool` tag in its own metrics. **Always inspect the actual label set** so dashboards do not break across multiple pools or replicas.

If the endpoint is unreachable, check dependencies, exposure configuration, port, and security. If the endpoint works yet the meter is missing, check the `DataSource` bean, pool type, metadata resolution, registry, and `MeterFilter`s before manually adding custom metrics.

## 6. Dashboards and PromQL queries

Once you confirm Prometheus exports the expected names and labels, you can build the following panels.

### Connection pool utilization ratio

```promql
jdbc_connections_active / clamp_min(jdbc_connections_max, 1)
```

This expression divides **series with matching labels**; multiply by 100 for percentages. If `active` and `max` carry different labels, adjust vector matching. Pools without a reliable `max` value must be excluded from this ratio alert. Never average percentages across two pools of different sizes and treat the result as system-wide utilization.

### Peak waiting threads over 5 minutes

```promql
max_over_time(hikaricp_connections_pending[5m])
```

Brief pending spikes during load surges differ from sustained pending over several minutes. Tune alert thresholds to load, scrape interval, and real impact on HTTP latency/errors.

### Connection acquisition timeout rate

```promql
rate(hikaricp_connections_timeout_total[5m])
```

This example assumes the exporter converts the `hikaricp.connections.timeout` counter into a `_total`-suffixed series. Exported names vary across stacks; verify at `/actuator/prometheus` before applying.

### Acquire p95 when histogram buckets exist

```promql
histogram_quantile(
  0.95,
  sum by (le, pool) (
    rate(hikaricp_connections_acquire_seconds_bucket[5m])
  )
)
```

This query is **illustrative only**: real histogram buckets, the `pool` label, and the `..._seconds_bucket` name must actually exist as assumed. You cannot compute accurate aggregated p95 from `count` and `sum` alone when histograms are not configured. Enabling histograms also impacts time series count and cost.

A minimal dashboard should place HTTP RPS/p95/error rate alongside pool active/idle/max/pending, timeout rate, acquire/usage latency where available, JVM CPU/threads/heap, and database server health.

## 7. Analyzing incident patterns

| Symptom | Hypothesis | Further verification |
| --- | --- | --- |
| `active ≈ max`, high pending, rising timeouts | Pool exhausted or connections held too long | HTTP latency, acquire/usage, DB sessions, transactions, thread dumps |
| Acquire rises while usage stays flat | Waiting for connections or slow new connection creation | Creation time, idle, pending, network/database connectivity |
| Usage spikes sharply, active high | Long transactions, slow queries, or lock waits | Slow query logs, DB locks, JDBC spans, transaction boundaries |
| High idle, HTTP latency rises | Bottleneck likely outside the pool | CPU/GC, business code, remote APIs, distributed traces |
| Timeouts paired with "connection is not available" | Timed out waiting to borrow a connection | Connection timeout config, queues, DB status |
| Connection creation spikes, pool shrinks suddenly | DB failover, connections closed/recreated | Network, DB restarts, validation, idle timeout |
| `jdbc.connections` missing despite active DB queries | Meter unbound or dropped by filter/exporter | Pool metadata, `DataSource` proxy, Actuator dependencies |

`active + idle` typically approximates current total connections, though it fluctuates as the pool opens/closes connections; never treat that identity as a strict invariant across every implementation.

### Scenario: pool too small for load

As traffic rises, `active` hits `max`, `pending` grows, and acquire p95 climbs while the database still has spare capacity. Increasing pool size **may** help if the database can handle the extra connections and connections are not being held abnormally. Still account for replica count and total database connection budget.

### Scenario: overly broad transaction

A `@Transactional` method calling an external API while a transaction stays open can hold onto a connection for a long time, depending on how JDBC/JPA acquires and releases connections. Merely raising `maximum-pool-size` can shift the bottleneck and overload the database. Inspect transaction boundaries, locks, slow queries, and move non-transactional work outside the transaction.

### Scenario: suspected connection leak

When JDBC code borrows a connection and forgets to release it, `active` can stay high even after traffic drops. HikariCP can log leak detection warnings when a connection is held beyond a threshold, though that warning **does not prove a leak**—a legitimate slow transaction can trigger it too. Inspect code, resource lifecycles, thread dumps, and database state.

## 8. Correlating data source metrics with tracing and logs

Pool metrics represent the state of **a pool/instance over time**. Distributed tracing shows **the execution path of a sampled request**.

```text
HTTP: POST /checkout
  ├─ business: inventory.reserve
  │    └─ JDBC/database client span (if instrumented)
  └─ business: payment.authorize
       └─ HTTP client payment provider

Concurrently: pool active=16, idle=0, pending=8, timeouts rising
```

To investigate a slow request:

1. Identify the time window when HTTP p95 or errors spiked.
2. Check pool active/idle/pending, acquire/usage, and timeouts on the **exact same instance/pool**.
3. Open traces from the same timeframe; inspect business spans and DB client spans if tracing integration is enabled.
4. Use `traceId`/`spanId` in logs if log correlation and MDC are configured. Never use request IDs as metric labels.
5. Cross-check database sessions, lock waits, slow queries, and database CPU/I/O.

When work crosses executors, queues, or other services, ensure proper **context propagation**. Opening an observation scope on an HTTP thread does not automatically propagate trace context to every worker thread. Sampling may also omit certain traces while pool metrics continue recording.

### Example: custom Observation for a `JdbcTemplate` operation

When you want to measure the duration of a **business step** separately, add an observation with semantics distinct from pool metrics:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry observationRegistry;

    public OrderLookupService(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry observationRegistry) {
        this.jdbcTemplate = jdbcTemplate;
        this.observationRegistry = observationRegistry;
    }

    public long countPendingOrders() {
        Long count = Observation
                .createNotStarted("orders.pending_count.lookup",
                        observationRegistry)
                .lowCardinalityKeyValue("operation", "count_pending")
                .observe(() -> jdbcTemplate.queryForObject(
                        "SELECT COUNT(*) FROM orders WHERE status = ?",
                        Long.class,
                        "PENDING"));

        return count == null ? 0L : count;
    }
}
```

This example uses a stable observation name and a parameterized query. When a metrics handler is active, the observation records invocation count and **operation duration**; the `count` value returned by SQL **does not automatically become a pending-orders Gauge**. Never put order IDs, emails, parameterized SQL strings, or DB passwords into low-cardinality tags.

If database client tracing is already active, a custom observation is useful only when it marks a **business boundary**; avoid creating two timers with identical scope and meaning. When you need pending order counts as a Gauge, pick a lightweight data source rather than running an expensive `COUNT(*)` on **every scrape**, which can make observability itself overload the database.

## 9. Multiple `DataSource`s, tags, and cardinality

A service may have a read pool and a write pool, or multiple `DataSource`s pointing to different databases. Each pool should have a **stable, bounded-value** identifying tag, such as `pool=orders-read` and `pool=orders-write`. For `jdbc.connections.*`, the identifier label may follow the `DataSource` bean name; for Hikari-specific metrics, it may follow the pool name. Always verify live output.

| Design | Assessment | Reason |
| --- | --- | --- |
| Stably named read pool and write pool | Suitable when architecture requires it | Analyze capacity, latency, and timeouts per pool |
| Creating a pool per request named with request ID | Avoid | Wastes connections and explodes cardinality |
| Unbounded tenant ID in pool tag | Avoid on metric labels | Many per-tenant series, high cost |
| Managed-value tags `application`, `environment`, `pool` | Suitable | Enables dashboard filtering and clear ownership |
| Raw JDBC URL, username/password as tags | Avoid | Leaks sensitive info, unstable length and cardinality |

When a pool is wrapped by a proxy, the metadata provider may fail to recognize the underlying pool. Do not rush to define a custom `Gauge` with the same name as auto-configured metrics: that can cause meter collisions or duplicate conflicting measurements.

Naming and tag conventions are part of your **telemetry schema**. Changing `name=orders` to `pool=orders-pool` can break dashboards, alerts, and PromQL queries relying on the old tag. Manage such changes like an API contract.

## 10. Sizing the connection pool from metrics

`maximum-pool-size`, `minimum-idle`, and `connection-timeout` have no universal optimal values for every system. Consider:

- **Replica count:** 10 replicas × 20 max connections can reach 200 DB connections, before counting other services and admin connections.
- **Database capacity:** allowed sessions, CPU, I/O, memory, lock contention, and proxy limits.
- **Connection hold time:** longer transactions require more concurrently active connections for the same throughput.
- **Bursts and concurrency:** clustered arrivals can cause temporary pending spikes; distinguish short bursts from sustained saturation.
- **Retry policies:** concurrent retries after timeouts can worsen queueing.

A Little's Law approximation: **average active connections ≈ connection borrows per second × average connection hold time (seconds)**, assuming a relatively steady system and consistent measurement scope.

For example, 100 borrows/second with an average usage of 0.08 seconds corresponds to about **8 average busy connections**. That **does not mean** a pool size of 8 is always enough: p95/p99 usage, bursts, instance count, DB capacity, and safety headroom all matter. An oversized pool can slow down the database instead of helping.

When tuning pool size, compare before/after HTTP RPS/p95/errors, pool active/idle/pending, acquire/usage/timeouts, and DB metrics. Never tune off a single gauge alone.

## 11. Common interpretation mistakes

**Confusing `active` with SQL concurrency.** A borrowed connection may be waiting or idle inside an open transaction without running SQL. `active` is not the number of queries currently executing on the DB server.

**Confusing `acquire` with query latency.** Acquire measures waiting to borrow a connection, not SQL execution time directly.

**Declaring a leak solely from high `active`.** Long transactions, traffic spikes, and slow queries look similar; inspect logs, thread dumps, and DB sessions.

**Treating a gauge as a counter.** `jdbc.connections.active` is an instantaneous snapshot at read/scrape time, not the cumulative total of connections borrowed since startup.

**Aggregating multiple pools without labels.** Active/max ratios must compare within the same pool and instance; merging differently sized pools can mask an exhausted pool.

**Attaching high-cardinality tags.** Never use order IDs, user IDs, raw URLs/query strings, exception messages, or trace IDs as metric labels. Use access-controlled logs/traces to investigate individual transactions.

**Registering overlapping metrics.** Actuator, Hikari instrumentation, and custom code can accidentally measure the same quantity. Inventory existing meter names/types/tags before adding new meters.

**Confusing a missing meter with missing export data.** A meter existing inside the JVM does not mean the exporter sent it, the scraper collected it, or the backend stored it. Check each stage.

## 12. Verification workflow

Before trusting dashboards or tuning settings, verify step by step:

1. **Instrumentation:** Is `DataSource` a Spring bean, what pool type is used, and are Actuator and registry dependencies present?
2. **Metric names:** Which `jdbc.connections.*` and `hikaricp.*` meters appear in `/actuator/metrics`? What tag key identifies the pool?
3. **Baseline behavior:** Under low load, do active/idle/pending plausibly reflect actual pool state?
4. **Controlled load behavior:** As concurrent requests rise, do active/pending/acquire respond as expected?
5. **Error path:** When connection acquisition times out, do timeout metrics, exceptions, and logs correlate?
6. **Exporter:** Are post-conversion names, label sets, and scrape/publish intervals correct?
7. **Correlations:** Do traces and logs link to slow HTTP requests, and does context propagation survive async/service hops?
8. **Alerts:** Do thresholds/windows reflect user impact, separate pools/instances, and avoid false positives on brief bursts?

| Scenario | Expected pool signals | Off-pool verification |
| --- | --- | --- |
| Low traffic | Low active, idle near minimum idle | DB reachable, app ready |
| Short query burst | Active rises then drops | HTTP latency normal |
| Pool exhausted | Active near max, pending climbs if metered | Acquire and HTTP latency climb |
| Connection timeout | Timeout counter increments if present | Matching exceptions/logs |
| SQL waiting on locks | Usage/active may climb | DB lock waits, query tracing |
| Trace sampled out | Pool metrics still record | Don't confuse sampling with missing meters |
| After Hikari/Micrometer upgrade | Names/labels may shift | Re-verify exporter and dashboards |
| Adding a `DataSource` | Additional per-pool series if supported | Cardinality and no name collisions |

Never generate heavy synthetic load in production solely to observe behavior; use a proper test environment with controlled load and permissions.

## 13. Practice exercise: why is checkout slow?

Suppose a Spring Boot service has a HikariCP pool capped at **16 connections**. Under rising load, the dashboard shows:

```text
HTTP checkout p95:              2.4 s  (previously: 0.3 s)
jdbc.connections.active:        16
jdbc.connections.idle:           0
jdbc.connections.max:           16
hikaricp.connections.pending:    9
Connection acquire p95:         1.7 s
Connection usage p95:           0.45 s
Connection timeout:             rising
```

*These figures are hypothetical for analysis practice; verify exact names, units, and labels against your live registry.*

**Question:** Is there enough evidence to conclude "SQL is slow, raise `maximum-pool-size` to 64"?

**Analysis:** Not yet. There is clear evidence the pool is under connection acquisition pressure: `active` equals `max`, `idle` is 0, `pending` is high, and acquire p95 climbed. However, root causes could be overly broad transactions, slow SQL/locks, unreleased connections, an overloaded database, or a pool genuinely too small for concurrency.

**Recommended investigation:**

1. Compare checkout business traces against query/transaction durations and timeout logs.
2. Inspect DB sessions, slow queries, locks, and transaction boundaries.
3. Compare total connections across all replicas against the database connection budget.
4. If the DB still has headroom and the pool is truly the bottleneck, raise it carefully under observation and compare before/after metrics.
5. If the DB is overloaded, prioritize optimizing SQL, indexes, transaction scope, or concurrency limits; raising pool size can worsen the incident.

**Key takeaway:** Data source metrics reveal **connection allocation and usage health**; business observations, SQL diagnostics, logs, and distributed traces identify **what work is holding connections and why requests are slow**. Combine all these signals, maintain context propagation, and govern tags/cardinality/exporters to make evidence-based operational decisions.
