# Hibernate Statistics, SQL Monitoring Tools, and Operational Metrics

## Objectives

Optimizing Spring Data JPA performance requires evidence across multiple layers. Hibernate can report how many JDBC statements were prepared, how many queries ran, which entities/collections were loaded or fetched, and per-query statistics. SQL logs reveal the actual statements and bound parameters. Spring Boot Actuator and Micrometer provide request, connection pool, and application resource metrics. Database execution plans explain why an SQL query runs fast or slow.

No single number describes performance completely. Combine:

- **Hibernate Statistics:** query/statement counts, entity loads/fetches, collection fetches, cache, and transaction counters.
- **SQL logging:** SQL statements, bound parameters, timing, and execution frequency.
- **Application metrics:** p50/p95/p99 latency, throughput, error rate, and request timeouts.
- **Connection pool metrics:** active/idle/pending connections, wait time, and timeout counts.
- **Database metrics and execution plans:** CPU, I/O, locks, indexes, estimated/actual rows, and execution time.

This lesson explains how to enable and read Hibernate Statistics, detect N+1, monitor SQL safely, integrate Actuator/Micrometer, and inspect execution plans. A Java 17+ example with Spring Boot, Hibernate, and H2 measures JDBC statement counts for an N+1 query and compares it against `JOIN FETCH`.

## 1. Building a Performance Observation Workflow

When an endpoint is slow, trace through the layers in order:

1. Measure endpoint latency and throughput to see which requests are affected and how often.
2. Measure service/repository timings to isolate the data access portion.
3. Inspect SQL statement counts and per-query durations; look for N+1, repeated queries, overly broad queries, or unexpected flushes.
4. Retrieve the execution plan of slow SQL to inspect scans, joins, sorts, indexes, and actual row counts.
5. Correlate connection pools, lock waits, database CPU/I/O, and caches to pinpoint the bottleneck.
6. Change one factor, re-run the same workload, and compare using the same metric set.

For example, a 900 ms request does not mean a single SQL query took 900 ms. The request might run 40 queries at 10 ms each, wait 300 ms on the connection pool, or serialize a huge response. Measure the right layer before optimizing.

## 2. Enabling Hibernate Statistics

Hibernate exposes `org.hibernate.stat.Statistics` through `SessionFactory`. In Spring Boot, statistics can be enabled via property:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Or via API:

```java
SessionFactory sessionFactory = entityManagerFactory.unwrap(SessionFactory.class);
sessionFactory.getStatistics().setStatisticsEnabled(true);
```

With Spring Boot 3 and Hibernate 6, import APIs from `org.hibernate.stat.Statistics` and `org.hibernate.SessionFactory`.

### Obtaining Statistics from EntityManagerFactory

```java
@Component
public class HibernateDiagnostics {
    private final Statistics statistics;

    public HibernateDiagnostics(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public Statistics statistics() {
        return statistics;
    }
}
```

`Statistics` belongs to the `SessionFactory`/persistence unit and is shared across requests in the application. Counters typically accumulate from startup or since the most recent `clear()` call.

### Be Careful When Calling clear()

`statistics.clear()` resets global SessionFactory statistics. This is useful in a demo program or single-threaded test, but should not be called per request in production: one request would wipe out metrics being observed by other requests or dashboards.

In production, normally let counters accumulate and scrape periodically; if per-request numbers are needed, use request-scoped tracing, timers, or datasource instrumentation instead of resetting global Statistics.

## 3. Important Counters

The `Statistics` API offers many counters. Commonly used ones include:

| Counter | Meaning | Used to investigate |
| --- | --- | --- |
| `getPrepareStatementCount()` | Number of JDBC statements Hibernate prepared | Estimating statements generated within a measurement window. |
| `getQueryExecutionCount()` | Number of HQL/JPQL queries tracked as executed by Hibernate | Detecting repeated queries. |
| `getEntityLoadCount()` | Number of entities loaded into the persistence context | Identifying heavy entity loading. |
| `getEntityFetchCount()` | Number of entities fetched outside the initial load | Finding lazy fetches / N+1. |
| `getCollectionLoadCount()` | Number of collections loaded | Detecting heavy collection loading. |
| `getCollectionFetchCount()` | Number of collections fetched | Finding N+1 on to-many relationships. |
| `getFlushCount()` | Number of Session flushes | Finding frequent or unexpected flushes. |
| `getConnectCount()` | Number of times Hibernate acquired a JDBC connection | Observing connection activity at the Hibernate layer. |
| `getTransactionCount()` | Number of tracked transactions | Understanding transaction cadence. |
| `getOptimisticFailureCount()` | Number of optimistic locking failures | Monitoring update contention. |
| `getSecondLevelCacheHitCount()` | Second-level cache hit count | Evaluating entity/collection caching if enabled. |
| `getQueryCacheHitCount()` | Query cache hit count | Evaluating query caching if configured. |

Counters alone do not tell which query is slow. For example, high `getPrepareStatementCount()` might stem from N+1, a request calling many repository methods, or a batch job processing many rows. Cross-reference with request traces and SQL logs.

`entityLoadCount` and `entityFetchCount` have distinct meanings; do not add them together and treat the sum as database rows returned. They are ORM activity counters, not physical database row reads.

## 4. Per-Query Statistics

Besides global counters, Hibernate provides `QueryStatistics` to track specific query strings:

```java
Statistics statistics = sessionFactory.getStatistics();
QueryStatistics queryStats = statistics.getQueryStatistics(
        "select p from Product p where p.category = :category");

long executions = queryStats.getExecutionCount();
long averageMillis = queryStats.getExecutionAvgTime();
long maxMillis = queryStats.getExecutionMaxTime();
long totalMillis = queryStats.getExecutionTotalTime();
```

The query key must match the query string Hibernate tracks. Derived queries, JPQL, and native SQL may be keyed differently; check keys in the actual runtime environment.

`QueryStatistics` typically provides execution count, average/total/min/max duration, and some cache details. Tracked query time does not necessarily equal endpoint latency: it excludes full HTTP processing, JSON serialization, and service logic.

### Enabling Statistics and Slow Query Logging

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Hibernate can log Session/SessionFactory statistics through its logger. Choose an appropriate log level to avoid excessive log volume under high load. Query-level statistics can also help spot queries that run very frequently even if each execution is brief.

### Reading Counters Over an Interval

Since counters are cumulative, take snapshots at two points and compute the delta:

```java
long before = statistics.getPrepareStatementCount();
// Run a measured workload.
long after = statistics.getPrepareStatementCount();
long statementsInWorkload = after - before;
```

This yields accurate per-workload counts only when no other concurrent requests increment the counter. In concurrent production environments, do not use global deltas to attribute statement counts to an individual request.

## 5. Monitoring SQL via Logging

With Hibernate 6, you can enable SQL and bind parameter logging:

```properties
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.highlight_sql=true
spring.jpa.properties.hibernate.use_sql_comments=true

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

- `org.hibernate.SQL=DEBUG` displays SQL sent by Hibernate to JDBC.
- `org.hibernate.orm.jdbc.bind=TRACE` displays bound parameter values.
- `format_sql` formats SQL for readability.
- `highlight_sql` colorizes SQL in supporting console terminals.
- `use_sql_comments` adds comments helping correlate SQL to queries/call paths in some cases.

In Hibernate 5, the bind parameter logger has a different name; do not copy Hibernate 5 configs into a Hibernate 6 project without checking the version.

### Example Generated SQL

JPQL:

```java
@Query("select p from Product p where p.category = :category")
List<Product> findByCategory(@Param("category") String category);
```

Generated SQL might resemble:

```sql
select p.id, p.name, p.category, p.supplier_id
from products p
where p.category = ?
```

Bind logs may display `BOOK` bound to `?`. Exact SQL depends on dialect, mapping, naming strategy, and Hibernate version.

### Risks of Bind Logging

Bind parameters can contain emails, phone numbers, tokens, addresses, payment details, or personal information. TRACE can produce huge logs and leak sensitive data.

Only enable bind logging locally/in dev or during a controlled investigation window. In production, limit duration, mask data, restrict log access, and avoid logging sensitive payloads. Never use raw SQL parameters or individual user IDs as metric tags because they cause high cardinality.

### show-sql vs. Logging Framework

`spring.jpa.show-sql=true` can also print SQL to the console, but is generally less flexible than standard loggers: harder to filter by category, harder to route into log pipelines, and lacks logger-level control over bind parameters. For systems needing observability, prefer the logging framework.

## 6. Detecting N+1 Using Statistics and SQL Logs

N+1 happens when an initial query fetches N entities and the application issues an extra query per entity to load a lazy association or collection.

Example:

```java
List<Product> products = repository.findByCategory("BOOK");
for (Product product : products) {
    System.out.println(product.getSupplier().getName());
}
```

If there are 20 products across 20 distinct suppliers, SQL may include:

1. One query loading the list of products.
2. Twenty queries loading the supplier for each product.

Statistics show prepared statement counts rising sharply relative to repository calls. SQL logs display numerous identically structured `select ... from suppliers where id = ?` statements.

### Fixes by Use Case

- Use `JOIN FETCH` if the endpoint always needs that association.
- Use `@EntityGraph` to declare fetch plans per repository method.
- Use projections/DTOs if only a few fields across multiple tables are needed.
- Use batch fetching when keeping lazy loading while grouping multiple IDs into one `IN` query.
- For large collections, consider separate queries or pagination instead of fetch-joining multiple collections at once.

Do not add `EAGER` to every relationship to cure N+1. EAGER can turn the problem into huge queries, redundant joins, or over-fetching. Choose fetch plans per use case.

### Limits of JOIN FETCH

Fetch-joining to-one associations is usually predictable. Fetch-joining collections alongside pagination can force Hibernate to read many rows, log warnings, or paginate in memory depending on version/settings. Avoid fetching multiple to-many collections in a single query because it can create Cartesian products and duplicate data.

## 7. Tracking Query Duration and Slow Queries

Counting queries is only the first step. A request with one query scanning millions of rows can still be slow.

Track:

- Duration per query or query group.
- Query p50/p95/p99 and max, not just averages.
- Number of times a query runs within a single request.
- Rows returned and rows examined when exposed by the database.
- Lock waits, deadlocks, and timeouts.
- Whether query plans degrade as data grows or after deployments.

Slow-query logging can happen at the database, JDBC proxy, or instrumentation layer. Hibernate can also log queries above a threshold in supported versions. Pick a slow-query source that correlates SQL, timestamps, and trace IDs; avoid leaving all loggers on TRACE long term.

## 8. Spring Boot Actuator and Micrometer

Hibernate Statistics describes ORM activity. Actuator/Micrometer adds application and connection pool visibility.

Add the Actuator dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Configure exposure of needed endpoints:

```properties
management.endpoints.web.exposure.include=health,info,metrics
```

Locally, you can inspect:

```text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.pending
```

Metric names depend on the registry, connection pool, and instrumentation setup. Check `/actuator/metrics` to see which metrics are actually registered; do not assume every application exposes the exact same list.

### Metrics to Watch

| Group | Metrics | Signals to investigate |
| --- | --- | --- |
| HTTP | Request count, p95/p99 latency, error rate | Endpoint slowdown or rising errors after deployment. |
| HikariCP | Active, idle, pending, max, timeout | Rising pending or pool exhaustion shows requests waiting for connections. |
| JDBC | Connection active/usage if instrumented | Long connection hold times. |
| Hibernate | Statement/query/entity/collection counters | Repeated queries, excessive fetches, or unusual flushes. |
| Database | CPU, I/O, locks, cache, slow queries | Bottleneck lies in the engine or data access layer. |

Not every Hibernate Statistics counter appears automatically as a Micrometer metric. To put them on dashboards, register a version-compatible binder or write a custom `MeterBinder`; keep metric tags low-cardinality.

### Example MeterBinder for Hibernate Counters

```java
@Bean
MeterBinder hibernateStatisticsBinder(EntityManagerFactory emf) {
    return registry -> {
        Statistics stats = emf.unwrap(SessionFactory.class).getStatistics();

        Gauge.builder("app.hibernate.prepared.statements",
                stats, Statistics::getPrepareStatementCount).register(registry);

        Gauge.builder("app.hibernate.entities.loaded",
                stats, Statistics::getEntityLoadCount).register(registry);

        Gauge.builder("app.hibernate.entities.fetched",
                stats, Statistics::getEntityFetchCount).register(registry);

        Gauge.builder("app.hibernate.queries.executed",
                stats, Statistics::getQueryExecutionCount).register(registry);
    };
}
```

These are gauges over cumulative SessionFactory-wide counters. Do not call `stats.clear()` while the binder is being scraped by dashboards. If rates over time are needed, your metrics backend can compute rates/deltas from counters; do not attach raw SQL or individual user IDs as tags.

### Prometheus

If using Prometheus, add `micrometer-registry-prometheus` at the Spring Boot-managed version and expose the `prometheus` endpoint according to your system's security policy. Dashboards can display rates, histograms, and percentiles from instrumented metrics.

## 9. Monitoring the Connection Pool

Spring Boot typically uses HikariCP as the default connection pool when JDBC/JPA is present. Important metrics:

- `active`: connections currently borrowed.
- `idle`: connections ready in the pool.
- `pending`: threads waiting for a connection.
- `max`: pool connection limit.
- `connection timeout`: failures to obtain a connection within the timeout.

If `pending` rises while database CPU is low, requests may be holding connections too long or opening overly broad transactions. If the pool stays active near max and database CPU/I/O is high, the database may be the bottleneck. Raising pool size does not always boost throughput; too many connections can heighten resource contention on the database.

Check transaction boundaries, slow queries, unclosed streams, connection leaks, and non-database work inside transactions. Avoid holding transactions open during external API calls unless necessary.

## 10. Database Execution Plans

Hibernate shows what SQL was sent; the database execution plan shows how the engine executes it.

With PostgreSQL, you can use:

```sql
EXPLAIN
SELECT id, name FROM products WHERE category = 'BOOK';
```

To measure actual execution:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name FROM products WHERE category = 'BOOK';
```

`EXPLAIN` normally produces an estimated plan; `EXPLAIN ANALYZE` actually runs the statement and reports real timings/rows alongside buffer info. Never run `EXPLAIN ANALYZE` casually on production UPDATE/DELETE statements since it executes the data modification. Use staging or a controlled rollback transaction when appropriate.

When reading plans, examine:

- Sequential/table scan vs. index scan.
- Estimated rows vs. actual rows.
- Join algorithm and join order.
- Sorts, aggregates, and temporary disk spills.
- Buffer hits/reads and I/O.
- How many rows filters discard after reading.
- Whether indexes align with filters, sorts, and real selectivity.

Do not create an index for every column in WHERE. Indexes increase storage and INSERT/UPDATE/DELETE cost. Base single or composite indexes on workload and execution plans.

## 11. Distinguishing Observation Layers

| Tool | Observes well | Cannot replace |
| --- | --- | --- |
| Hibernate Statistics | ORM activity, query/statement/entity/cache counters | Execution plans and physical database resources. |
| Hibernate SQL logger | SQL and bound values at the ORM layer | End-to-end latency, pool waits, and CPU/I/O. |
| JDBC proxy/P6Spy/datasource-proxy | SQL passing through JDBC, timing, and sometimes bound parameters | ORM internals like entity loads/fetches. |
| Actuator/Micrometer | Request, JVM, pool, and application metrics | Per-SQL execution plan details. |
| Database monitoring | CPU, I/O, locks, buffers, slow queries, and plans | Entity mapping, N+1 in code, and service logic. |

These tools complement one another. You do not need to enable all of them simultaneously in production; pick the observability level suited to the question under investigation.

## 12. Runnable Example with Java 17+, Spring Boot 3.4.5, Hibernate, and H2

This example creates three suppliers and three products. `Product.supplier` is LAZY. A service runs two approaches:

- First query fetches products and accesses each row's supplier, triggering N+1.
- Second query uses `JOIN FETCH` to load products and suppliers in one SQL statement.

Hibernate Statistics measures the `prepareStatementCount` delta for each block. Since this demo runs standalone, global deltas work; do not use this reset/delta technique for per-request measurements in multi-threaded production.

### Project Structure

```text
hibernate-observability/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/observability/
        │   ├── ObservabilityApplication.java
        │   ├── Supplier.java
        │   ├── Product.java
        │   ├── SupplierRepository.java
        │   ├── ProductRepository.java
        │   └── CatalogDiagnosticsService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>hibernate-observability</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:observability;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.use_sql_comments=true
logging.level.org.hibernate.SQL=DEBUG
management.endpoints.web.exposure.include=health,info,metrics
```

Bind parameter TRACE is off by default in the example to avoid logging input values. For local debugging, you can add:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

### `Supplier.java`

```java
package com.example.observability;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "suppliers")
public class Supplier {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Supplier() {
    }

    public Supplier(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

### `Product.java`

```java
package com.example.observability;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String category;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "supplier_id", nullable = false)
    private Supplier supplier;

    protected Product() {
    }

    public Product(String name, String category, Supplier supplier) {
        this.name = name;
        this.category = category;
        this.supplier = supplier;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Supplier getSupplier() {
        return supplier;
    }
}
```

### `SupplierRepository.java`

```java
package com.example.observability;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SupplierRepository extends JpaRepository<Supplier, Long> {
}
```

### `ProductRepository.java`

```java
package com.example.observability;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByCategory(String category);

    @Query("select p from Product p join fetch p.supplier "
         + "where p.category = :category")
    List<Product> findByCategoryWithSupplier(@Param("category") String category);
}
```

### `CatalogDiagnosticsService.java`

```java
package com.example.observability;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.List;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogDiagnosticsService {
    private final ProductRepository productRepository;
    private final EntityManager entityManager;
    private final Statistics statistics;

    public CatalogDiagnosticsService(
            ProductRepository productRepository,
            EntityManager entityManager,
            EntityManagerFactory entityManagerFactory) {
        this.productRepository = productRepository;
        this.entityManager = entityManager;
        this.statistics = entityManagerFactory
                .unwrap(SessionFactory.class)
                .getStatistics();
    }

    @Transactional(readOnly = true)
    public void compareFetchPlans() {
        long beforeNPlusOne = statistics.getPrepareStatementCount();
        List<Product> products = productRepository.findByCategory("BOOK");
        products.forEach(product ->
                System.out.println(product.getName()
                        + " -> " + product.getSupplier().getName()));
        long nPlusOneStatements =
                statistics.getPrepareStatementCount() - beforeNPlusOne;

        // Detach prior entities so the next measurement must fetch its own data.
        entityManager.clear();

        long beforeJoinFetch = statistics.getPrepareStatementCount();
        List<Product> fetched =
                productRepository.findByCategoryWithSupplier("BOOK");
        fetched.forEach(product ->
                System.out.println(product.getName()
                        + " -> " + product.getSupplier().getName()));
        long joinFetchStatements =
                statistics.getPrepareStatementCount() - beforeJoinFetch;

        System.out.println("N+1 JDBC statements: " + nPlusOneStatements);
        System.out.println("JOIN FETCH JDBC statements: " + joinFetchStatements);
        System.out.println("Hibernate entity loads: " + statistics.getEntityLoadCount());
        System.out.println("Hibernate entity fetches: " + statistics.getEntityFetchCount());
    }
}
```

The service uses `@Transactional` so lazy associations are accessed while the persistence context is open. `entityManager.clear()` between the two measurements ensures the second query does not reuse suppliers already loaded in the first-level cache. In applications with concurrent requests, global counters can be altered by other requests; this measurement snippet is intended only for a single-threaded demo.

### `ObservabilityApplication.java`

```java
package com.example.observability;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ObservabilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ObservabilityApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            SupplierRepository supplierRepository,
            ProductRepository productRepository,
            CatalogDiagnosticsService diagnostics) {
        return args -> {
            Supplier one = supplierRepository.saveAndFlush(new Supplier("Supplier One"));
            Supplier two = supplierRepository.saveAndFlush(new Supplier("Supplier Two"));
            Supplier three = supplierRepository.saveAndFlush(new Supplier("Supplier Three"));

            productRepository.saveAllAndFlush(List.of(
                    new Product("JPA Basics", "BOOK", one),
                    new Product("Spring Data JPA", "BOOK", two),
                    new Product("Hibernate Guide", "BOOK", three)
            ));

            diagnostics.compareFetchPlans();
        };
    }
}
```

### Running the Program

```bash
mvn spring-boot:run
```

With three products and three distinct suppliers, the expected SQL statement count output is:

```text
N+1 JDBC statements: 4
JOIN FETCH JDBC statements: 1
```

This reflects one SELECT for products plus three lazy SELECTs for suppliers in the first case; the second query fetches products together with suppliers via one JOIN FETCH. Overall entity load/fetch counts depend on SessionFactory state and prior initialization; do not hardcode a fixed number for those lines.

In the logs, you can observe one SELECT on `products` followed by three similar SELECTs on `suppliers`. After switching to `JOIN FETCH`, a single SQL statement queries both tables.

### Viewing Actuator Metrics

While the application is running:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/http.server.requests
```

Connection pool metrics appear if the pool is instrumented and the metric binder is active. The metrics endpoint lists only metric names actually registered in the application.

## 13. Bringing Observability Safely into Production

### Choosing Logging Levels by Environment

- Local/dev: can enable SQL DEBUG and bind TRACE during active debugging.
- Test/CI: enable SQL logging when verifying fetch plans or diagnosing slow tests.
- Production: prefer metrics, traces, and thresholded slow-query logs; restrict bind values and verbose logging duration.

### Correlation ID and Tracing

Attach a trace ID or request ID to logs to tie endpoint, service, and SQL logs together for a single execution. With distributed tracing, instrument HTTP, JDBC, and downstream calls to see where time is spent.

Never use raw SQL, emails, account IDs, or request IDs as metric labels. Those values create massive cardinality and can overwhelm metrics backends. Use stable, controlled metric tags such as operation, repository area, or query category.

### Overhead of Statistics and Logging

Statistics and SQL logging incur CPU, memory, and log I/O costs. Bind TRACE is especially bulky. Enable within tight bounds, measure overhead, and disable verbose levels once investigation finishes.

### Securing Actuator

Do not expose all Actuator endpoints to the public internet. Expose only required endpoints, protect them with authentication/network policies, and restrict access to metrics/logs that could reveal system internals.

## 14. Which Metrics Belong on a Dashboard?

An operational dashboard for a JPA application can be organized as follows:

| Group | Metrics/view | Question to answer |
| --- | --- | --- |
| Endpoint | Request rate, p95/p99 latency, 5xx | Which endpoints are impacting users? |
| Persistence | Query/statement count, entity fetch, collection fetch | Is a single request generating too much SQL? |
| Database | Slow queries, CPU, I/O, lock waits, deadlocks | Is the database the bottleneck? |
| Pool | Active/idle/pending connections, timeouts | Are requests waiting for connections? |
| JVM | Heap, GC pauses, thread count | Is the application under memory or thread pressure? |
| Cache | Hit/miss/put if caching enabled | Is caching actually reducing load or just adding complexity? |

Set alerts based on system baselines and SLOs rather than arbitrary thresholds. For instance, p99 rising alongside pool pending counts and database lock waits signals something very different from p99 rising while SQL latency stays normal.

## 15. Common Pitfalls

1. **Enabling only SQL logs and drawing performance conclusions:** you need latency, query counts, pool metrics, and execution plans.
2. **Looking at averages while ignoring p95/p99:** tail latency can be terrible even when the average looks low.
3. **Confusing entity load with entity fetch:** these are distinct ORM counters, not physical row counts.
4. **Resetting Statistics on every request:** SessionFactory-wide counters get wiped or skewed by concurrent requests.
5. **Using global statement deltas under concurrency:** you cannot accurately attribute statements to a single request when others run concurrently.
6. **Leaving bind TRACE enabled long term:** logs bloat and may leak PII/secrets.
7. **Assuming a slow query is Hibernate's fault:** inspect execution plans, locks, I/O, and network.
8. **Using `show-sql` instead of a logging pipeline:** hard to filter, correlate traces, and sanitize data.
9. **Enlarging the connection pool to fix slow queries:** can overload the database further.
10. **Setting EAGER on every relationship to cure N+1:** can cause unnecessary joins and over-fetching.
11. **Fetch-joining multiple collections during pagination:** can multiply rows, spike memory, or break efficient pagination.
12. **Adding indexes by guesswork:** validate with execution plans and realistic workloads.
13. **Running `EXPLAIN ANALYZE` casually on production DML:** it executes the statement.
14. **Exposing Actuator without protection:** metrics/env/config endpoints can leak operational details.
15. **Using metric tags with raw SQL or dynamic IDs:** causes uncontrolled cardinality explosion.

## 16. Checklist for Investigating a Slow JPA Endpoint

- [ ] Record the endpoint, trace ID, request size, and p50/p95/p99 latency.
- [ ] Break down time across service, repository, JDBC, and serialization.
- [ ] Measure prepared statement/query counts under a controlled workload.
- [ ] Check for N+1 on both to-one and to-many associations.
- [ ] Inspect actual SQL and bound parameters in a safe environment.
- [ ] Obtain execution plans for slow queries on production-like data.
- [ ] Compare estimated vs. actual rows, scans, joins, sorts, and buffers.
- [ ] Check Hikari active/pending/idle counts and connection wait times.
- [ ] Check lock waits, deadlocks, database CPU/I/O, and caches.
- [ ] Change one fetch plan/index/query and re-run the same workload.
- [ ] Compare latency, statement count, rows, pool, and database load together.
- [ ] Disable bind TRACE and diagnostic logging once investigation ends.

## 17. Practical Rules

- Enable Hibernate Statistics when measuring ORM behavior and remember counters are global.
- Use query-level statistics to find high-frequency or high-max-latency queries.
- Use SQL loggers to verify actual statements; enable bind TRACE only under strict control.
- Combine Actuator/Micrometer with HikariCP metrics to watch endpoints and pools.
- Use trace IDs to connect requests with logs and SQL.
- Use database execution plans to inspect scans, joins, indexes, rows, and buffers.
- Use statistics deltas only in isolated workloads; never reset global counters per request.
- Detect N+1 via statement counts and repeated SQL, then pick fetch joins, EntityGraph, projections, or batch fetching per use case.
- Do not increase pool size or add indexes without evidence from metrics and plans.
- Secure Actuator, mask sensitive data, and avoid high-cardinality metric tags.

Core takeaway: **Hibernate Statistics shows how much work the ORM is doing; SQL logging shows exact statements and bound values; Actuator/Micrometer shows requests and connection pools; execution plans show how the database executes queries. Combining these sources lets you pinpoint bottlenecks, measure the impact of changes, and keep production observability safe.**