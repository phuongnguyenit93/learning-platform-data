# Connection Pool, Cache, and Database Metrics

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects HTTP clients, databases, caches, message brokers, and Spring Integration adapters into real-world integration flows. A single request might call the Catalog API, read Redis, borrow a JDBC connection from HikariCP, query PostgreSQL, and publish an outbox event to a broker.

When the system slows down, asking "is the database up?" is not enough. You must distinguish:

- **Pool waiting for connections** because all connections are busy.
- **Slow SQL** caused by missing indexes, lock contention, or long-running transactions.
- **Increased cache misses** causing a sudden spike in database queries.
- **Stale cache** serving outdated data despite a high cache hit ratio.
- **Increasing consumer backlog** even when individual queries are fast, because business throughput cannot keep up with load.

Spring Boot Actuator combines with **Micrometer** to collect metrics across multiple layers. This lesson belongs to the **Integration Observability** chapter and focuses on **connection pool, cache, and database metrics**, along with how to interpret those signals for performance and reliability.

After this lesson, you will be able to:

1. Set up Actuator, `MeterRegistry`, and a metrics export registry.
2. Distinguish gauge, counter, timer, histogram, and observation.
3. Read `jdbc.connections.*` and `hikaricp.*` metrics and recognize pool saturation.
4. Collect cache metrics for Caffeine/Redis and know when cache statistics are unavailable or disabled.
5. Distinguish JDBC pool metrics, Spring Data repository metrics, Hibernate metrics, and **individual SQL operation** timing.
6. Create custom observations/metrics for integration adapters without creating high-cardinality labels.
7. Design dashboards, alerts, tests, and data-driven diagnostic procedures.

> **Core distinction:** Pool metrics show **connection allocation status**; repository/Hibernate metrics reflect part of data-access work; to know **which query is slow and why**, you may need additional instrumentation, controlled SQL logs, query plans, database monitoring, and tracing.

## 1. Where Metrics Fit in an Integration Flow

Example order-intake flow:

~~~mermaid
flowchart LR
    A["HTTP / broker receive"] --> B["Order service"]
    B --> C["Cache lookup"]
    C -->|"Miss"| D["JDBC / JPA"]
    D --> E["Hikari connection pool"]
    E --> F["Database"]
    B --> G["Outbox writer"]
    G --> D
    G --> H["Outbox relay → broker"]
    C -. "cache metrics" .-> I["MeterRegistry"]
    E -. "pool metrics" .-> I
    D -. "repository / operation metrics" .-> I
    H -. "business metrics" .-> I
    I --> J["Prometheus / OTLP / monitoring"]
~~~

Within the same request, Hikari might show the pool is **not exhausted**, yet a query is still slow due to database lock waits. A 95% cache hit ratio may be great for product reads while doing nothing for a sync job that must always write to the database. Combine multiple indicators rather than drawing conclusions from a single metric.

Three layers commonly observed:

| Layer | Question | Signals |
| --- | --- | --- |
| **Connection pool** | Are connections available to serve work or are callers waiting? | Active, idle, pending, max, acquire time, timeout |
| **Cache** | Is the cache reducing load, holding valid data, or failing? | Hits/misses, evictions, size, load time, backend errors |
| **Database operations** | Are repositories/SQL/transactions fast and succeeding? | Operation timer, repository invocations, Hibernate statistics, query/lock indicators |

Aggregated metrics reveal trends and drive alerts. **Traces** follow individual calls, while **logs/audit** help investigate specific errors and business events. Never turn metric labels into storage for `orderId`, `eventId`, or raw SQL.

## 2. Micrometer and Measurement Types

Micrometer is a metrics facade supporting core meter types:

| Meter | Suitable for measuring | How to interpret |
| --- | --- | --- |
| **Gauge** | Active connection count, cache size, queue depth | Value at the **moment of sampling** |
| **Counter** | Timeouts, cache misses, retries, duplicates | Monotonically increasing; dashboards use rate/increase |
| **Timer** | Connection acquire time, query time, business operation duration | Count, total time, max, and optional histogram |
| **DistributionSummary** | Batch sizes, payload sizes, items per run | Distribution of values, not necessarily time |
| **LongTaskTimer** | Long-running tasks in flight and elapsed duration | Useful for long reconciliation/backfill jobs |
| **Observation** | An activity with lifecycle and context | Can emit timers/spans via corresponding handlers |

Two common pitfalls:

1. A gauge reading `active=4` does not say whether **10,000 requests waited** during the previous minute; scraping can miss short spikes. Combine gauges with timeout counters and acquire timers.
2. Cumulative counters from process start should not be plotted as "errors per minute" without applying `rate(...)` or `increase(...)`.

`Micrometer Observation` and `MeterRegistry` serve different roles. Observation describes an activity's start/stop/error lifecycle and can generate metrics when a meter handler is configured. `MeterRegistry` stores/exposes meters, after which a registry/exporter ships data to Prometheus, OTLP, or another system.

## 3. Setting Up Actuator and Exporting Metrics

### 3.1. Dependencies

Example Gradle Groovy DSL for Spring Boot integrating JDBC, JPA, or cache:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Used when the application needs JDBC:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    // Only needed when choosing Caffeine cache:
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'

    // Only needed when exporting metrics to Prometheus:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

If the app uses Spring Data JPA, the JPA starter already brings in the required JDBC infrastructure. For PostgreSQL/MySQL you still must add the vendor-specific **JDBC driver** at runtime, e.g., `org.postgresql:postgresql`. The snippet above illustrates options and does not require adding all dependencies simultaneously.

Spring Boot typically provides `MeterRegistry` and meter binders when Actuator, Micrometer, and corresponding implementations are on the classpath. **Seeing an Actuator endpoint does not prove all metric types will exist**: the actual beans/pools/caches and instrumentation support must be present.

### 3.2. Basic Configuration

~~~yaml
spring:
  application:
    name: order-integration
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/orders_db}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      connection-timeout: 3s

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-integration
~~~

URLs and usernames are illustrative only; never commit real secrets in source code. `/actuator/prometheus` is only available when a Prometheus registry is present and the endpoint is exposed. In production, **protect management endpoints** via network policies, authentication/authorization, ingress, or a dedicated management port.

How to inspect:

~~~text
GET /actuator/metrics
GET /actuator/metrics/jdbc.connections.active
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/cache.gets
GET /actuator/prometheus
~~~

The `/actuator/metrics/{name}` paths use the **Micrometer meter name**, not the backend-normalized name. For example, Micrometer `hikaricp.connections.active` may be exported by Prometheus as `hikaricp_connections_active`.

If the endpoint returns 404 or lacks a meter name:

- Check endpoint exposure and access permissions.
- Check dependencies and relevant `DataSource`/`CacheManager`/repository beans.
- Check whether metrics are filtered out by `management.metrics.enable.*` or registry configuration.
- Check whether caches are created at startup and provider statistics are enabled.
- Check whether actual activity occurred to trigger timers/counters (some meters only appear after the first measurement).

### 3.3. Micrometer Naming and Tags

Names and labels should stay stable per operation type:

| Recommended tag | Example | Why |
| --- | --- | --- |
| `application` | `order-integration` | Stable service identifier |
| `pool` | `orders-pool` | Finite set of pools |
| `cache` | `productById` | Finite set of caches |
| `cacheManager` | `cacheManager` | Distinguishes managers |
| `operation` | `outbox.fetch`, `order.save` | Categorizes work |
| `outcome` | `success`, `error` | Compares error rates |
| `db.system` | `postgresql` | Database family, when supported by instrumentation |

Never put `customerId`, `userEmail`, `orderId`, `eventId`, full SQL containing literal data, or URLs with query parameters into metric tags. A tag with millions of values inflates time-series counts and drives high costs.

## 4. DataSource Metrics: `jdbc.connections.*`

Spring Boot Actuator can automatically instrument `DataSource` beans that have supported pool metadata. Meters typically carry the `jdbc.connections` prefix and are tagged by datasource bean name.

| Common meter | Type | Interpretation |
| --- | --- | --- |
| `jdbc.connections.active` | Gauge | Connections currently borrowed/in use |
| `jdbc.connections.idle` | Gauge | Idle connections in the pool |
| `jdbc.connections.max` | Gauge | Maximum connections allowed in the pool |
| `jdbc.connections.min` | Gauge | Minimum/idle limit per pool metadata |
| Other `jdbc.connections.*` | Depends on provider/version | Check actual app list |

**Remember:** `active` is not the number of SQL statements currently running. A transaction may borrow a connection and sit idle without executing SQL for a period. Conversely, one connection may execute many consecutive statements.

Useful numbers:

~~~text
Pool limit: 12
Active:      11
Idle:         1
Pending:      0  (typically from Hikari-specific metrics)
~~~

Seeing `active/max = 11/12` may suggest the pool is near capacity, yet if acquire time remains low and pending is 0 under normal traffic, there may be no incident. Examine trends, load, and latency together.

### 4.1. Multiple DataSources

When an application has `ordersDataSource` and `reportingDataSource`, Boot can bind two metric groups with distinct identifying tags. Do not sum `active` across both and compare against the `max` of a single pool.

Measure each source separately:

- `ordersDataSource`: serves HTTP commands, JPA transactions, and outbox.
- `reportingDataSource`: serves export/reporting jobs.
- `quartzDataSource` (if present): dedicated to Quartz JDBC JobStore.

If you declare a custom `DataSource` using an implementation without supported metadata, some `jdbc.connections.*` metrics may be missing. A compatible `DataSourcePoolMetadataProvider` or custom instrumentation may be needed; do not assume every `DataSource` behaves like Hikari.

## 5. HikariCP: `hikaricp.*` Is More Detailed Than `jdbc.connections.*`

Spring Boot typically uses HikariCP when JDBC/JPA starters bring Hikari onto the classpath. Hikari provides detailed metrics on **acquire, connection usage, creation, timeouts, and pending threads**.

| Common metric | Type | Operational question |
| --- | --- | --- |
| `hikaricp.connections.active` | Gauge | How many connections are currently borrowed? |
| `hikaricp.connections.idle` | Gauge | Are idle connections available? |
| `hikaricp.connections.pending` | Gauge | How many threads are waiting for a connection? |
| `hikaricp.connections.max` | Gauge | What is the pool's max connection limit? |
| `hikaricp.connections.min` | Gauge | What is the pool's minimum idle setting? |
| `hikaricp.connections.timeout` | Counter | How many connection waits timed out? |
| `hikaricp.connections.acquire` | Timer | How long does acquiring a connection take? |
| `hikaricp.connections.usage` | Timer | How long are connections held? |
| `hikaricp.connections.creation` | Timer | How long does creating a new connection take? |

Exact names may be normalized differently by registries and some meters depend on version; check `/actuator/metrics` to confirm. Hikari-specific metrics are usually tagged by **pool name**, e.g., `orders-pool`. Set a stable name via `spring.datasource.hikari.pool-name` rather than letting auto-generated names change across deployments.

### 5.1. Reading the Metrics Correctly

~~~mermaid
flowchart TD
    A["Order service needs a connection"] --> B{"Free connection in pool?"}
    B -->|"Yes"| C["Acquire connection quickly"]
    B -->|"No"| D["Wait in pending queue"]
    D --> E{"Connection returned before timeout?"}
    E -->|"Yes"| C
    E -->|"No"| F["Connection acquisition timeout"]
    C --> G["SQL / transaction"]
    G --> H["Return connection to pool"]
~~~

Three metrics commonly read together:

- `pending`: Is anyone waiting for a connection **right now**?
- `acquire`: Over a time window, is connection-acquisition latency rising?
- `timeout`: Have threads failed to acquire a connection within the allowed time?

If `active` is near `max` while acquire time stays low, the pool may be operating normally under high load. If `pending` stays elevated, acquire p95 rises, and timeouts appear, that signals pool saturation worth investigating.

### 5.2. Why Do Connection Pools Exhaust?

Common causes:

1. Slow SQL or database lock waits causing each request to hold connections longer.
2. Overly broad transactions wrapping outbound HTTP calls or non-SQL work.
3. Manual JDBC code failing to close connections, causing connection leaks.
4. Incoming HTTP requests or broker consumers exceeding database capacity.
5. `maximum-pool-size` set too low for needed concurrency while the DB still has headroom.
6. Database/server connection-creation issues preventing the pool from replenishing connections.
7. Multiple replicas opening maximum connections that exceed server limits.

**Do not increase pool size as a knee-jerk first reaction.** Raising `maximum-pool-size` from 10 to 30 across 10 replicas increases max connection demand from 100 to 300; the database may actually slow down further due to excessive transaction contention.

### 5.3. Timeouts Differ Across Layers

| Timeout | What it measures | Do not confuse with |
| --- | --- | --- |
| Hikari `connection-timeout` | Time waiting to **borrow** a connection from the pool | SQL query timeout |
| JDBC driver connect/socket timeout | Network connect/read wait time | Pool wait time |
| Query timeout | Allowed execution time for a SQL statement | Total transaction duration |
| Spring transaction timeout | Transaction bound enforced by manager/execution mechanism | External HTTP/broker timeouts |
| HTTP client timeout | External Catalog/Payment calls | JDBC connection timeout |

Example configuration:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      connection-timeout: 3s
      max-lifetime: 30m
~~~

Values are illustrative. `max-lifetime` must account for database, proxy/load-balancer timeouts, and connection-recreation overhead; there is no universal set of values for every system.

## 6. Cache Metrics: Hits, Misses, Evictions, and Size

Caches are often the first layer suspected when database load shifts. Spring Boot Actuator can bind supported caches (Caffeine, Redis, Hazelcast, JCache, and other providers depending on version) with meters prefixed by `cache`.

Common signals:

| Metric or concept | Interpretation | Interpretation trap |
| --- | --- | --- |
| `cache.gets` with hit/miss result when supported | Lookup hit/miss counts | Requires provider statistics enabled |
| `cache.puts` | Number of cache writes | Does not equal business write count |
| `cache.evictions` | Number of evicted entries | Size-based eviction is not always the same as TTL expiration |
| `cache.size` | Current or estimated entry count | Provider-dependent; not byte size |
| Cache load duration/failures | Cost of loading data on miss | May not exist on every implementation |
| Redis roundtrip errors/latency | Redis transport health | Distinct from Spring Cache hit/miss |

**Do not assume every cache type exposes every metric.** Boot can instrument Spring's `Cache`, but specific metrics depend on the statistics API supported by the cache provider and how the cache is configured.

### 6.1. Enabling Caffeine Statistics Properly

Caffeine provides a `recordStats` option. Configure caches created at startup:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names:
      - productById
      - integrationSettings
    caffeine:
      spec: maximumSize=10000,expireAfterWrite=10m,recordStats
~~~

The cache names `productById` and `integrationSettings` are **cache region names**, fixed in count. Never create a separate cache name per customer or order.

To use caching with Spring Cache annotations, enable caching in configuration:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
}
~~~

Illustrative service:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final ProductCatalogPort catalog;

    public ProductLookupService(ProductCatalogPort catalog) {
        this.catalog = catalog;
    }

    @Cacheable(cacheNames = "productById", key = "#productId")
    public ProductDto findById(String productId) {
        return catalog.fetchFromDatabase(productId);
    }
}
~~~

`ProductCatalogPort` and `ProductDto` here are assumed application contracts. Calling `findById("P-100")` through the Spring proxy may miss and hit the DB, and the next call hits the cache if key/TTL remain valid.

**Important:** `@Cacheable` alone does not guarantee hit/miss metrics exist. The cache provider must support and enable statistics, and the cache must be bound to `MeterRegistry`. With Caffeine's `recordStats`, these indicators have data to observe.

### 6.2. Caches Created After Startup

Per Boot documentation, **caches present at startup** are automatically bound when supported. A cache created dynamically in code after startup may not automatically register metrics.

Anti-pattern example:

~~~java
// Do not create cache names per request/customer:
cacheManager.getCache("customer-" + customerId);
~~~

Even if the cache manager returns or creates caches dynamically, this produces massive numbers of caches and metric series and may bypass auto-binding. Define a finite set of cache names and store the customer ID in the **cache key** rather than the **cache name**.

If runtime cache creation is truly necessary, Spring Boot provides `CacheMetricsRegistrar` in supported versions to bind explicitly; verify the API for your Boot release and ensure you avoid double-binding. `CacheMetricsRegistrar` does not give hit/miss statistics to a cache implementation that does not support them.

### 6.3. How Does Redis Cache Differ from Caffeine?

| Aspect | Caffeine local cache | Redis-backed Spring Cache |
| --- | --- | --- |
| Data location | Usually inside each instance's JVM | On Redis server/cluster |
| Hit/miss | Caffeine `recordStats` per instance | `RedisCacheManager` has configurable stats |
| Cache size | Provider can report local entry count | Counting global keys has limits/cost |
| Operational issues | JVM memory/eviction, stale local state | Network RTT, timeouts, Redis memory and availability |
| Multi-replica scaling | Each node has its own cache | Nodes share Redis, yet client stats may still be local |

Per Spring Data Redis, `RedisCache` statistics are **disabled by default**. You can enable them when building `RedisCacheManager` via the `enableStatistics()` builder method. `RedisCache#getStatistics()` reflects activity **local to that cache instance/client**, not necessarily total cluster-wide hits/misses across Redis.

Illustrative manual manager setup (solely to demonstrate the mechanism):

~~~java
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public RedisCacheManager buildRedisCacheManager(
        RedisConnectionFactory connectionFactory) {

    return RedisCacheManager.builder(connectionFactory)
            .enableStatistics()
            .build();
}
~~~

This is an illustrative factory method, **not a required `@Bean`**. Registering your own `RedisCacheManager` bean may cause Boot auto-configuration to back off; you must preserve serialization, TTL, cache names, key prefixes, null handling, and transaction awareness as needed. Do not replace the production manager just to turn on metrics if a builder customizer or less invasive configuration is supported by your Boot version.

**Distinguish the metric sets:**

- Redis `INFO stats` and Redis server monitoring: server-level numbers.
- Spring Data `RedisCache` statistics: application/cache-instance metrics when enabled.
- Micrometer Redis/client instrumentation: network command latency/pool metrics depending on driver and configuration.
- `cache.gets`: Spring cache abstraction metric when supported by the provider binding.

Do not directly compare a single node's cache hit ratio against the entire Redis cluster's keyspace hit rate and conclude there is a bug.

## 7. Interpreting Cache Hit Ratio in Context

A common formula:

~~~text
hit ratio = hits / (hits + misses)
~~~

For example, in a 5-minute window with 9,000 hits and 1,000 misses: hit ratio = 90%. However:

1. If each miss triggers a very heavy query, 10% misses can still overload the database.
2. If the cache serves stale data, a high hit ratio **does not prove data correctness**.
3. When a cache holds multiple tenants/data categories, an overall ratio can hide one group missing continuously.
4. Right after service restart, cache warm-up causes a miss spike; compare against warm-up state and baseline.
5. If caching has bypasses, local computation, or fallbacks, `cache.gets` may not cover every business request.

Useful complementary metrics:

- Business lookup duration for hit vs. miss paths.
- Database query rate and response time.
- Count of cache fallbacks to DB.
- Cache invalidation/eviction counts.
- Redis timeouts and error rates.
- End-to-end latency or data lag when using event-driven cache updates.

If using Redis as a cache in an integration flow, ensure update/evict events are not dropped; performance metrics **do not replace a consistency strategy** between SQL and cache.

## 8. Database Metrics: Multiple Distinct Observation Levels

Do not use a vague "DB metrics" label for everything.

| Measurement level | Source | What it tells you | What it cannot prove |
| --- | --- | --- | --- |
| **DataSource/pool** | `jdbc.connections.*` / `hikaricp.*` | Connection usage, pending, acquire time | Which SQL statement is slow |
| **Spring Data repository** | `spring.data.repository.invocations` | Repository method call count, duration, state | Duration of an individual SQL query inside the method |
| **Hibernate ORM** | `hibernate.*` when statistics enabled | Supported session/entity/query/cache statistics | Query plan and all database waits |
| **Custom DB operation** | Observation/Timer around code | Latency of a selected business operation | All SQL calls if not fully instrumented |
| **SQL/JDBC/R2DBC instrumentation** | Separate agent/proxy/instrumentation | SQL spans and timing, when configured | Exact business commit if span scope is narrower |
| **Database server** | PostgreSQL/MySQL/DB-native monitoring | Slow queries, locks, CPU, I/O, connections | Business meaning without correlation |

**Example:** `JdbcTemplate.query(...)` may borrow a connection from Hikari, execute SQL, and map results. A timer wrapping the call includes **connection wait time + SQL execution + result mapping** (plus some overhead). It does not automatically break down those three parts. Separating them requires query tracing, pool acquire timers, and server-side metrics.

### 8.1. Spring Data Repository Metrics

Spring Boot can instrument Spring Data `Repository` invocations under the default meter:

~~~text
spring.data.repository.invocations
~~~

Common tags include `repository`, `method`, `state`, and `exception`. Conditions: Spring Data repositories, Actuator/Micrometer, version-appropriate instrumentation enabled, and at least one invocation.

Example:

~~~java
public interface OrderRepository
        extends org.springframework.data.jpa.repository.JpaRepository<
                OrderEntity, String> {

    java.util.List<OrderEntity> findByStatus(String status);
}
~~~

With matching auto-instrumentation, `findByStatus(...)` invocations are measured at the repository method level. This is **not** a per-SQL-statement timer for statements generated by Hibernate. One repository method may execute multiple queries, especially with lazy loading or N+1 issues.

Configurable via:

~~~yaml
management:
  metrics:
    data:
      repository:
        autotime:
          enabled: true
~~~

To measure only selected methods, disable autotime and use `@Timed` as supported by your Spring Data/Boot version. Avoid arbitrarily renaming meters across releases, as dashboards and alerts rely on stable names.

### 8.2. Hibernate Metrics and `generate_statistics`

With JPA/Hibernate, having `spring-boot-starter-data-jpa` **does not mean full Hibernate statistics are enabled**. Per Boot guidance, you need `hibernate-micrometer` on the classpath and `hibernate.generate_statistics` enabled for the relevant `EntityManagerFactory`.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.hibernate.orm:hibernate-micrometer'
}
~~~

~~~yaml
spring:
  jpa:
    properties:
      "[hibernate.generate_statistics]": true
~~~

When conditions are met, Hibernate metrics generally carry the `hibernate` prefix and are tagged by `EntityManagerFactory` name. They can expose entity/session activity, second-level cache stats, or other ORM statistics depending on version.

**Cost:** statistics add overhead and increase telemetry volume. Measure overhead vs. value on staging before enabling broadly in production. They do not replace database monitoring, query explain plans, or lock analysis.

### 8.3. Beware of N+1 Queries

A repository method may have high latency because it fetches 100 entities and then accesses a lazy association, generating 101 SQL queries. `spring.data.repository.invocations` only reflects the measured repository call; if lazy access occurs **after the method returns** in another layer, the repository timer may not even include the late SQL queries.

When suspecting N+1:

- Compare repository/business latency with statement counts from Hibernate statistics or SQL tracing.
- Use bounded SQL logging in test environments without printing sensitive data.
- Check fetch joins, entity graphs, batch fetching, and pagination.
- Use query plans and database monitoring to verify the true bottleneck.

Never assume increasing the Hikari pool size will fix N+1.

## 9. Creating Custom Metrics for a Business-Significant JDBC Operation

Suppose an outbox relay polls a batch of unpublished events every few seconds. You need to measure **batch-fetch latency**, independent of pool metrics.

First define a DTO:

~~~java
import java.util.UUID;

public record OutboxRow(UUID id, String eventType) {
}
~~~

A Spring JDBC adapter:

~~~java
// OutboxBatchReader.java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxBatchReader {

    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry registry;

    public OutboxBatchReader(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry registry) {
        this.jdbcTemplate = jdbcTemplate;
        this.registry = registry;
    }

    public List<OutboxRow> findPending(int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 500));

        return Observation.createNotStarted(
                        "integration.outbox.load", registry)
                .lowCardinalityKeyValue(
                        "operation", "pending_batch")
                .observe(() ->
                        jdbcTemplate.query(
                                """
                                SELECT id, event_type
                                FROM outbox_events
                                WHERE published_at IS NULL
                                ORDER BY created_at, id
                                LIMIT ?
                                """,
                                (rs, rowNum) -> new OutboxRow(
                                        rs.getObject("id",
                                                java.util.UUID.class),
                                        rs.getString("event_type")),
                                safeLimit));
    }
}
~~~

This SQL illustrates **PostgreSQL**. The `outbox_events` table and appropriate indexes must be created via migrations beforehand. If multiple relay workers run, a plain read query **does not claim** rows and may return the same records to multiple workers; atomic claiming, transactions, and idempotency must be designed separately. This lesson uses the query purely to illustrate measurement timing.

When `ObservationRegistry` has a meter observation handler (as configured appropriately by Boot Actuator), the completed observation can produce a timer named `integration.outbox.load`.

Key points:

- The timer measures the **synchronous `jdbcTemplate.query` call**, including borrowing a connection and mapping rows.
- Exceptions thrown out of `observe(...)` are recorded according to the observation lifecycle.
- The `operation=pending_batch` tag is finite and does not include `outboxId`.
- If the database transaction commits **after the method returns**, this timer does not include commit time; place the observation scope outside the transaction boundary if commit latency is the target.
- Even though Observation can create spans, without a matching tracer/exporter there is no distributed trace.

### 9.1. When to Use a Manual Timer?

If traces/Observation are not required, a direct Micrometer `Timer` is also appropriate:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public void recordBatch(
        MeterRegistry registry, Runnable action) {

    Timer timer = Timer.builder("integration.batch.apply")
            .description("Time spent applying a batch")
            .tag("operation", "apply")
            .register(registry);

    timer.record(action);
}
~~~

`Runnable` only covers **synchronous** work. If `action` merely builds a `Mono` or submits an async task and returns immediately, the timer stops before I/O completes. For reactive code, tie measurements to subscription/terminal signals and proper context propagation, or leverage built-in WebClient/R2DBC instrumentation.

Avoid double-measuring the same operation with `@Observed`, manual Timers, and default instrumentation under similar names without knowing how they relate.

## 10. Measuring the Right Transaction and Pipeline Boundaries

An integration flow that consumes a message and writes SQL + outbox has several boundaries:

~~~mermaid
sequenceDiagram
    participant M as Broker Consumer
    participant S as Order Service
    participant P as Hikari Pool
    participant D as SQL Database
    participant O as Outbox Relay
    M->>S: OrderPaid event
    S->>P: Borrow connection
    P-->>S: Connection granted
    S->>D: Insert inbox + update order + outbox
    D-->>S: SQL results
    S->>D: COMMIT
    D-->>S: Commit outcome
    S-->>M: Processing success/ack
    O->>D: Fetch pending outbox
    D-->>O: Batch
~~~

In this flow:

- `hikaricp.connections.acquire` measures time spent borrowing a connection from the pool.
- `hikaricp.connections.usage` reflects how long the connection was borrowed.
- `spring.data.repository.invocations` measures applicable repository calls.
- `integration.outbox.load` measures an application-defined query operation.
- A separate business timer must measure **from event receipt to transaction commit**, if that is the business SLA.
- Broker acknowledgment and outbox publishing are **different** boundaries; DB metrics alone do not prove events reached the broker.

If an HTTP timeout occurs after DB commit and the consumer receives a redelivery, the application may see duplicates. Metrics should separate `duplicate_detected` from `business_apply_success` rather than interpreting every message delivery as a new record.

**Observability does not replace transactions:** `Observation` does not provide atomic commits across databases, Redis, or brokers; it reveals where latency or failures occur for investigation.

## 11. Calculating SLOs and Detecting Saturation

### 11.1. Useful Formulas

**Approximate pool utilization:**

~~~text
utilization = active connections / maximum pool connections
~~~

Only apply this formula when both gauges belong to the **same pool** and max is non-zero. This is a point-in-time indicator, not standalone proof of pool health or exhaustion.

**Cache hit ratio over a time window:**

~~~text
hit ratio = hits_delta / (hits_delta + misses_delta)
~~~

Use hit/miss deltas **over the same time window**, without mixing cumulative counters across different windows. With very small sample sizes, percentages fluctuate noisily.

**Connection acquisition error rate:**

~~~text
pool timeout rate = timeouts_delta / observation_window
~~~

Combine with traffic/load: one timeout in several million requests differs vastly from 100 timeouts in one minute.

**Business-to-index lag:**

~~~text
lag = time_search_projection_visible - time_business_commit
~~~

This metric cannot be inferred from Hikari or cache hit ratios. Calculating it requires instrumenting and storing controlled timestamps/correlation metadata across stages.

### 11.2. Example Prometheus Queries

These are **examples** assuming the Prometheus registry actually exports these exact names/labels. Check `/actuator/prometheus` before using.

Pool usage:

~~~promql
hikaricp_connections_active{pool="orders-pool"}
/
clamp_min(hikaricp_connections_max{pool="orders-pool"}, 1)
~~~

Pending waiters:

~~~promql
hikaricp_connections_pending{pool="orders-pool"}
~~~

Timeout rate:

~~~promql
rate(hikaricp_connections_timeout_total{pool="orders-pool"}[5m])
~~~

Hit ratio when cache provider/binder emits `cache.gets` with `result=hit/miss`:

~~~promql
sum(rate(cache_gets_total{cache="productById",result="hit"}[5m]))
/
clamp_min(
  sum(rate(cache_gets_total{cache="productById"}[5m])),
  1
)
~~~

Dividing by `clamp_min(...,1)` prevents division by zero during very low traffic; when there is no data, results may be empty and **should not be interpreted as 0% hit**. Check how your provider classifies results and handles missing result tags.

Timer p95 for `integration.outbox.load` requires exporting **histogram buckets**:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        integration.outbox.load: true
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(integration_outbox_load_seconds_bucket[5m])
  )
)
~~~

Prometheus metric names, the `_seconds_bucket` suffix, and histogram availability depend on registry/configuration. Do not run `histogram_quantile` on a timer without buckets enabled; verify exported series and the cost of bucket/tag counts.

## 12. Combining Pool, Cache, and Database on a Dashboard

An operationally useful dashboard is typically organized into sections:

| Section | Metrics to group together | Purpose |
| --- | --- | --- |
| **Request/consumer load** | Throughput, error rate, p95, broker lag | Understand incoming load and SLO |
| **DB pool** | Active/max, idle, pending, acquire p95, timeouts | Detect connection-level saturation |
| **SQL/ORM** | Repository latency, custom DB operation p95, DB lock/slow query | Distinguish slow SQL from pool wait |
| **Cache** | Hits/misses, ratio, evictions, size, Redis errors | Assess cache effectiveness and risk |
| **Data consistency** | Cache invalidation lag, outbox oldest age, duplicate count | Detect stale/duplicate data |
| **Infrastructure** | DB CPU/I/O/connections, Redis memory, app JVM/GC | Investigate root causes |

**When request latency rises**, check whether cache misses increased **before** Hikari pending climbed or vice versa. If the timeline shows:

~~~text
Cache miss ↑ → DB QPS ↑ → Pool active/max ↑ → Pending ↑ → API p95 ↑
~~~

then cache effectiveness is a strong hypothesis to investigate. Still, temporal correlation does not prove causation: the same deployment might have changed both query patterns and cache keys, or the DB may have hit lock contention.

### 12.1. Alert on Behavior, Not Arbitrary Absolute Numbers

Examples of actionable operational signals:

- `hikaricp.connections.pending` stays elevated **while** acquire latency rises.
- `hikaricp.connections.timeout` occurs frequently alongside rising HTTP/consumer error rates.
- Cache misses spike unusually compared to baseline, accompanied by higher DB QPS and degraded response latency.
- Repository p95 increases while the pool is not saturated: inspect query plans, locks, and DB I/O.
- Hibernate second-level cache misses jump after a deploy: inspect cache invalidation and cache regions.
- Outbox oldest age or consumer lag breaches SLO despite fast individual queries: processing throughput is insufficient.

Do not apply a blanket rule like "active > 80% is always an error" to every pool. A pool with high utilization but low acquire latency and zero timeouts may be operating normally. Thresholds must come from baselines, traffic patterns, instance counts, and error budgets.

## 13. Testing Metrics with Micrometer

### 13.1. Unit Testing a Custom-Instrumented Operation

`SimpleMeterRegistry` enables testing without Prometheus or a collector. Observation test example:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OutboxObservationTest {

    @Test
    void recordsOneCompletedOperation() {
        var meterRegistry = new SimpleMeterRegistry();
        var observationRegistry = ObservationRegistry.create();

        observationRegistry.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(meterRegistry));

        Observation.createNotStarted(
                        "integration.outbox.load",
                        observationRegistry)
                .lowCardinalityKeyValue(
                        "operation", "pending_batch")
                .observe(() -> {
                    // Synchronous task simulating batch fetch.
                });

        assertEquals(
                1L,
                meterRegistry.get("integration.outbox.load")
                        .tag("operation", "pending_batch")
                        .timer()
                        .count());
    }
}
~~~

This test proves **Observation + meter handler** produces a completed timer. It does not test real Actuator configuration, Hikari pool binding, or Prometheus export.

### 13.2. Spring Boot Integration Test for Pool Metrics

In a `@SpringBootTest` with a real Hikari DataSource, inject `MeterRegistry` and execute a query via repository/JdbcTemplate. Then verify the meter exists:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class DataSourceMetricsTest {

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void bindsDataSourcePoolMetrics() {
        assertNotNull(
                meterRegistry.find("jdbc.connections.active").gauge());
    }
}
~~~

Test conditions: an Actuator-supported `DataSource`, active meter binder, and created pool. With multiple datasources, filter by actual datasource tags. If the test uses a non-pooling `DataSource`, this assertion may not apply; never alter tests just to "force metrics to exist".

### 13.3. Testing Cache Metrics

A cache integration test should:

1. Enable `@EnableCaching` and a provider with statistics, such as Caffeine `recordStats`.
2. Create the `productById` cache at startup.
3. Call the method through the **Spring proxy** twice with the same key.
4. Verify the business port was invoked only once.
5. Verify the cache meter is bound and records hit/miss per provider.
6. Change the key or evict the cache and verify counters/size change as expected.

If called internally from another method in the same object (`self-invocation`), proxy-based `@Cacheable` will not trigger; the test will fail caching assertions even if the business method returns the right value.

With Redis, tests must confirm metrics come from local `RedisCache` statistics when enabled, and **never** assume cluster-wide counts when running multiple replicas.

### 13.4. Load and Failure-Mode Testing

Unit tests do not reproduce pool saturation. Test in an isolated environment:

- Send concurrent requests exceeding pool max; measure pending/acquire/timeouts.
- Inject slow SQL queries or lock contention; observe pool usage.
- Temporarily disable cache; observe DB load and fallbacks.
- Restart the service; observe the warm-up miss spike.
- Simulate Redis timeouts; verify fallback policies do not overload the database.
- Stop database/network; measure timeouts, error rates, and recovery.
- Under job retries or broker redeliveries, verify business idempotency and duplicate metric counts.

Never run stress tests against a production database or intentionally hold connections to exhaust pools without authorization and safeguards.

## 14. Diagnosing Issues from Metrics

| Symptom | Accompanying signals | Investigation direction |
| --- | --- | --- |
| Pool active near max, pending rising | Acquire p95/timeouts rising | Long transactions, leaks, DB locks, concurrency |
| Pool active low yet API is slow | HTTP client p95 or cache/backend latency rising | Downstream other than DB |
| Repository latency high, pool acquisition low | DB CPU/I/O, slow queries, lock waits rising | Query plan/index/N+1 |
| Cache hit ratio drops after deploy | Cache name/key/TTL changed, DB QPS rising | Key generation, invalidation, warm-up |
| Cache hit ratio high yet data is stale | Business version/invalidation lag | Consistency, outbox replay, TTL |
| High Caffeine evictions | Cache size near max, churn | Keyspace/TTL/max size, memory pressure |
| Redis cache metrics missing | Stats disabled or cache not bound at startup | RedisCacheManager settings/registrar |
| Hibernate metrics missing | Missing `hibernate-micrometer` or statistics off | Dependency + `generate_statistics` |
| Repository metrics missing | No repository invocation or auto-instrumentation off | Actuator, Spring Data, autotime |
| `jdbc.connections.*` exists but SQL timers missing | Pool bound, query instrumentation absent | Add operation timing/SQL instrumentation |
| Prometheus does not show meter | Missing Prometheus registry/exposure/scrape, name changed | Check `/actuator/metrics` and `/actuator/prometheus` |
| Metric series jump suddenly | Tags contain IDs/users/dynamic cache names | Block high-cardinality sources |

### 14.1. A Practical Investigation Workflow

Suppose an outbox consumer is processing slowly:

1. Check **broker lag** and `outbox oldest age`: is the pipeline truly lagging?
2. Check `hikaricp.connections.pending` and acquire timer: is it waiting on the pool?
3. Check repository/custom DB operation timers: did query time increase?
4. Check database locks/slow query plans: is the issue in SQL or transactions?
5. Check cache misses/Redis latency: did cache failures add DB load?
6. Check active jobs/concurrency: are Quartz or Spring Integration pollers piling up?
7. Check release timeline: were migrations, new indexes, cache configs, or pool configs changed?
8. Apply a fix targeting the real bottleneck, then monitor metrics to confirm improvement.

Avoid reacting with "increase the pool", "lengthen cache TTL", or "add more retries" before understanding the bottleneck: those changes can worsen lock contention, stale data, or duplicate side effects.

## 15. Operational Architecture and Telemetry Security

Metrics are also part of production systems:

- **Collector/scraping:** Prometheus pull endpoints or OTLP push pipelines need proper network routes, retry/buffering, and access controls.
- **Retention:** store raw/high-resolution metrics within budget; aggregate/downsample as needed.
- **High cardinality:** enforce finite tag allowlists; avoid per-customer cache/pool names, event IDs, or dynamic SQL.
- **Secrets and PII:** never put JDBC URLs containing passwords, sensitive cache keys, payloads, or SQL literals into labels/logs.
- **Multi-instance:** dashboards must filter by instance and aggregate properly rather than treating one instance as representative of the whole cluster.
- **Multiple pools:** sum active/max across pools only when they serve the same capacity boundary; never merge production and staging.
- **Sampling:** trace sampling differs from metric aggregation; low trace sampling does not sample gauges/counters the same way.
- **Overhead:** Hibernate statistics, detailed SQL instrumentation, and histograms add cost; enable selectively and benchmark on staging.
- **Health vs. performance:** health `UP` does not prove DB queries are fast or cache projections are accurate.
- **Incident review:** retain dashboards, SLOs, and linked query/trace/log views for root-cause analysis.

### 15.1. Consistency-Related Alerts

Cache metrics and pool metrics **do not measure correctness**. In a flow that updates an Order and then evicts Redis cache:

~~~text
SQL COMMIT succeeded
    |
    +-- Redis evict failed
           |
           +-- Cache continues returning stale state
~~~

Hikari and JDBC may both look "green" and cache hit ratio remains high. Detecting divergence requires additional signals for **cache invalidation failures**, **projection lag**, **reconciliation mismatches**, and business commit boundaries. For DB→broker updates, transactional outbox preserves event emission intent; consumers still must be idempotent upon replay.

## 16. Metrics Implementation Checklist

- [ ] Added Actuator, appropriate registry/exporter, and verified metrics endpoints are secured.
- [ ] Distinguished gauge/counter/timer/Observation; cumulative counters are not plotted as instantaneous rates.
- [ ] Verified `jdbc.connections.*` and `hikaricp.*` match the intended datasource/pool.
- [ ] Dashboards cover active/max, pending, acquire p95, timeouts, and replica count.
- [ ] Statistics enabled for cache providers where needed; Caffeine has `recordStats`.
- [ ] Cache names are declared/bound at startup; dynamic caches have an explicit registration policy.
- [ ] Understand that `RedisCache` statistics are local and may be disabled by default.
- [ ] Distinguished pool metrics from repository, Hibernate, and SQL operation metrics.
- [ ] If using Hibernate metrics, verified `hibernate-micrometer` dependency and `hibernate.generate_statistics`.
- [ ] Dedicated operation timers/observations exist for key business steps (outbox, inbox, cache invalidation).
- [ ] Metric labels are low-cardinality and free of secrets/PII/IDs.
- [ ] Alerts follow baselines/SLOs, combining incoming load, latency, errors, and backlog.
- [ ] Unit/integration/load tests verify instrumentation and behavior under overload.
- [ ] Observability covers retries, duplicates, transaction commits, and projection lag—not just pool/cache hit ratios.

**Remember:** Spring Boot Actuator and Micrometer provide automatic metrics for many pools, caches, and Spring Data components. However, **metrics for one layer do not substitute for another layer**. Hikari shows how connections are allocated; cache statistics show lookup efficiency; repository/Hibernate/SQL instrumentation shows data-access timing and behavior at distinct levels. Operating integration flows reliably requires combining them with **business outcomes, transactions, retries, idempotency, testing, and observability**.

## References

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): DataSource, HikariCP, Cache, Hibernate, Spring Data repositories, and Micrometer.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): cross-reference for Boot 3.x.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): `ObservationRegistry`, handlers, and context propagation.
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): auto-configuration, cache providers, and Caffeine.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, statistics, and limitations.
- [Caffeine — Statistics](https://github.com/ben-manes/caffeine/wiki/Statistics): `recordStats`, hit rate, eviction, and load penalties.
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meters, tags, and registries.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): timer buckets, percentiles, and SLOs.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase`, `histogram_quantile`.
