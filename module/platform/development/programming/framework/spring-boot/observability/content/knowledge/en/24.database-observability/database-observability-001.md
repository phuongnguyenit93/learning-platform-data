# JDBC observability in Spring Boot

A Spring Boot API can return slow responses even when the controller and HTTP client have no issues. Time may be spent waiting to acquire a connection from the pool, executing SQL, waiting on a database lock, or transferring data over JDBC. If you only observe HTTP request duration, operations teams know the request is slow, but not whether the time was spent in application code, the connection pool, or the database. **JDBC observability** adds that visibility through DataSource/pool metrics, JDBC operation details, and traces that correlate database calls with the request that triggered them.

Within the **SPRING_BOOT_OBSERVABILITY** module, JDBC observability is part of the observability setup for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. This lesson belongs to the **Database observability** chapter and focuses on **JDBC observability**: observing the connection pool and JDBC queries, distinguishing connection wait time from execution time, integrating metrics/tracing, handling SQL metadata safely, controlling cardinality, testing, and troubleshooting production incidents.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish DataSource/pool metrics, JDBC query metrics, and database server metrics.
2. Monitor active/idle/pending connections, acquisition time, and usage time.
3. Understand how Spring Boot/Micrometer instruments DataSource and JDBC operations.
4. Distinguish JDBC Observation, tracing spans, and SQL logging.
5. Correlate database spans with an HTTP request using trace context.
6. Identify pool saturation, slow queries, lock waits, and connection leaks.
7. Restrict SQL attributes, query cardinality, and sensitive data.
8. Test metrics, tracing, and pool behavior using a test database.
9. Investigate missing JDBC metrics/traces or excessive telemetry overhead.

## 1. What is JDBC observability?

JDBC (Java Database Connectivity) is the Java API that allows applications to work with relational databases. In Spring Boot, code typically accesses JDBC via `JdbcTemplate`, Spring Data JDBC/JPA, Hibernate, or other data access libraries. Underneath those abstractions, the application typically uses a `DataSource` to acquire a `Connection` and a JDBC driver to execute statements.

JDBC observability monitors key points in the database access lifecycle:

- acquiring a connection from a DataSource or connection pool;
- how long a connection is held;
- executing a `PreparedStatement`/`Statement`;
- count and duration of database operations;
- exceptions and SQL error categories;
- transaction boundaries;
- trace context linking the operation to a request;
- pool state such as active, idle, pending, and timeouts.

### 1.1. Layers to observe

| Layer | Question | Example data |
| --- | --- | --- |
| Application | Which code is calling the database? | Service/operation name |
| DataSource/pool | Is a connection available? | Active, idle, pending |
| JDBC client | How long did the statement take? | Query duration, operation type |
| Database server | What is the DB doing? | Lock wait, execution plan, CPU |
| Trace | Which request does this DB call belong to? | Trace ID, span ID, parent |
| Logs | What error occurred? | SQLState, exception category |

An application-side metric does not replace database-native monitoring. For example, rising pool pending counts indicate the application is waiting for connections; database CPU/lock metrics help determine whether the database engine is overloaded or experiencing contention.

### 1.2. DataSource, connection pool, and JDBC driver

~~~mermaid
flowchart TD
    App["Spring service / repository"] --> SpringJDBC["JdbcTemplate / ORM"]
    SpringJDBC --> DataSource["DataSource"]
    DataSource --> Pool["Connection pool"]
    Pool --> Driver["JDBC driver"]
    Driver --> Database["Database server"]
    Pool -. "Pool metrics" .-> Metrics["MeterRegistry"]
    SpringJDBC -. "JDBC Observation / tracing" .-> Telemetry["Metrics / traces"]
    Database -. "DB-native monitoring" .-> DBMetrics["DB metrics / query statistics"]
~~~

Spring Boot typically configures HikariCP as the default connection pool when the appropriate dependencies are present. Applications may also use another pool or an organization-provided DataSource. Metric names and instrumentation capabilities depend on the implementation and version.

## 2. Connection pool metrics

A connection pool maintains a set of reusable connections. Pooling avoids opening and closing a physical database connection for every operation, but the pool has a finite limit. When all connections are busy, incoming requests must wait or time out.

### 2.1. Important pool measurements

| Measurement | Meaning | Interpretation |
| --- | --- | --- |
| Active connections | Connections currently borrowed by the application | Staying near max for a long time may indicate saturation |
| Idle connections | Connections ready to be borrowed | Zero is not always an error; check pending |
| Pending/waiting threads | Number of threads waiting for a connection | Sustained growth signals pool pressure |
| Max connections | Pool upper limit | Needs to be balanced with DB capacity |
| Min idle | Target number of idle connections | Affects warm-up and resource usage |
| Connection acquisition time | Time spent waiting to get a connection | High values often suggest pool pressure or DB/connectivity issues |
| Connection usage time | Time a connection is held | High values may be due to slow queries or holding connections too long |
| Timeout count | Number of times a connection could not be acquired in time | Clear signal of pool exhaustion |

Meter names can differ between HikariCP and other pools. With HikariCP, Micrometer can provide meters under the `hikaricp.connections` group and related measurements; verify against the actual registry.

### 2.2. Why high active connections alone is inconclusive

High active connections can be normal when traffic increases. You should read them together with:
- active versus max;
- idle;
- pending threads;
- acquisition latency;
- usage duration;
- request rate and DB latency.

If active is near max while pending is 0 and acquisition latency is low, the pool may simply be well utilized. If active is near max, pending is rising, and acquisition latency stays elevated, the pool is under pressure.

### 2.3. Connection acquisition time and usage time

Acquisition time is how long the application waits for the pool to supply a connection. Usage time is how long the connection is held after being borrowed. These two metrics help distinguish:

- High acquisition, normal usage: insufficient pool capacity, connections held by other requests, or slow connection creation.
- Normal acquisition, high usage: slow SQL, lock waits, large result sets, long-running transactions, or code holding connections too long.
- Both high: possible overall overload or a database/pool incident.

Do not immediately increase max pool size when seeing pending threads. Databases have connection limits, and increasing pool size can expose the database to higher concurrency, making latency worse.

## 3. Spring Boot and Actuator for DataSource metrics

With Spring Boot Actuator and Micrometer, DataSources can be automatically instrumented when the DataSource/pool is recognized and a meter registry is present.

Gradle example for a Spring Boot JDBC application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'com.h2database:h2'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

In production, replace H2 with the real JDBC driver/database. Keep dependency versions aligned with the Spring Boot BOM.

### 3.1. Enabling metrics endpoints

Example Actuator configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: never
~~~

Expose only the required endpoints and protect them with network/security policies. Do not expose metrics endpoints to the public internet without proper access control.

### 3.2. Checking meters via Actuator

Supported endpoints can list meter names and meter details. Example checks:

~~~text
GET /actuator/metrics
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.idle
GET /actuator/metrics/hikaricp.connections.pending
~~~

Exact names depend on the pool and Spring Boot/Micrometer version. Before building dashboards, inspect the actual list of meters in the running environment.

### 3.3. HikariCP metrics

When using HikariCP, Micrometer can bind pool metrics through Hikari metrics integration. Spring Boot auto-configuration usually handles this when conditions match. If a DataSource is manually created or wrapped, verify that `HikariDataSource` is recognized and bound properly.

Do not register a binder for the same pool multiple times; this can cause duplicate meter registrations or inconsistent metrics.

## 4. JDBC operations and Micrometer Observation

Pool metrics describe pool state; they do not necessarily tell you which specific SQL operation is slow. To observe JDBC operations, the application needs instrumentation at the JDBC/ORM layer or a custom Observation wrapping business operations.

Micrometer Observation provides a unified lifecycle: start, event/error, and stop. Observation handlers can produce metrics and tracing spans when configured.

### 4.1. JDBC Observation is not an SQL logger

| Mechanism | Role | Content |
| --- | --- | --- |
| DataSource pool metrics | Pool health | Active/idle/pending/timeouts |
| JDBC Observation | Operation lifecycle | Operation name, duration, outcome/context |
| JDBC tracing span | Link operation in trace | Parent, timing, selected attributes |
| SQL logging | Statement debugging | SQL text/parameters if configured |
| Database query statistics | Engine perspective | Execution stats, locks, plans |

Do not enable full SQL logging just to get query metrics. SQL text and bind parameters can contain PII, secrets, or payment data.

### 4.2. Custom Observation around business operations

If specific JDBC instrumentation is not yet present, you can add a business Observation around repository operations:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry observationRegistry;

    public OrderRepository(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry observationRegistry
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.observationRegistry = observationRegistry;
    }

    public Integer countOpenOrders() {
        return Observation.createNotStarted(
                        "orders.repository.count-open",
                        observationRegistry)
                .lowCardinalityKeyValue("db.operation", "SELECT")
                .observe(() -> jdbcTemplate.queryForObject(
                        "select count(*) from orders where status = ?",
                        Integer.class,
                        "OPEN"
                ));
    }
}
~~~

This Observation describes the business operation and wraps the `JdbcTemplate` call. If a framework or agent already instruments the underlying JDBC call, you may see an outer business span and an inner JDBC span; that is an intentional hierarchy as long as names and roles are clear. Do not create duplicate spans for the same operation at the same layer.

### 4.3. Low-cardinality and high-cardinality metadata

Metadata suitable for metrics typically includes:
- `db.system`: postgresql, mysql;
- `db.operation.name`: SELECT, INSERT, UPDATE;
- stable repository/operation name;
- outcome/error category with a bounded set of values.

Values that should not become metric tags:
- raw SQL;
- SQL bind values;
- customer ID/order ID;
- table name if dynamic and unbounded;
- free-form exception messages;
- connection URLs containing credentials.

High-cardinality attributes in traces still need size, privacy, and indexing cost controls.

## 5. JDBC tracing and distributed traces

An HTTP request may invoke a service, execute JDBC calls, and return a response. If tracing instrumentation wraps the JDBC call, the database span can be a child of the current server span or business span.

~~~mermaid
sequenceDiagram
    participant Client
    participant App as Spring Boot
    participant JDBC as JDBC instrumentation
    participant DB as Database
    participant Exporter as OTLP Collector
    Client->>App: POST /orders
    Note over App: HTTP server span
    App->>JDBC: INSERT order
    Note over JDBC: JDBC client span
    JDBC->>DB: SQL execution
    DB-->>JDBC: Result
    JDBC-->>App: Update count
    App-->>Client: HTTP 201
    App->>Exporter: Export server/business spans
    JDBC->>Exporter: Export JDBC span
~~~

A trace backend can show:
- an HTTP server span for total request duration;
- a business span for `orders.create`;
- a JDBC span for the DB operation;
- dependency spans if the request calls other services.

If the HTTP span takes 800 ms and the JDBC span takes 650 ms, the database operation may account for most of the request latency. However, JDBC span duration does not always equal pure database execution time; it can include driver/client overhead, network latency, result processing, or instrumentation boundaries.

### 5.1. Not every JDBC driver creates spans automatically

The JDBC API does not guarantee spans by itself. A suitable integration is required, such as an instrumentation agent, framework integration, or specific datasource/JDBC instrumentation. Having a Micrometer Tracing bridge and OTLP exporter is not enough to conclude that every JDBC statement is instrumented.

Verify actual spans in tests and in the trace backend; do not assume JDBC spans exist just because pool metrics appear.

### 5.2. Parent context and async database work

If a database operation runs in an async worker, context must be propagated to the worker using an appropriate mechanism. Otherwise, the JDBC span may become a separate root span or lack the expected parent. For reactive database stacks such as R2DBC, that is a different API/instrumentation model and does not fall under JDBC.

## 6. Query duration, slow queries, and database locks

JDBC client timing is useful for finding slow operations, but it does not explain what happened inside the database. When query duration increases, combine:
- JDBC span/Observation duration;
- pool acquisition/usage time;
- database-native query statistics;
- lock/wait events;
- CPU, IO, buffer/cache;
- transaction duration;
- query plans and index usage.

### 6.1. Distinguishing pool wait from database wait

| Symptom | Likely cause | Investigation direction |
| --- | --- | --- |
| High acquisition, short JDBC span | Waiting for connection before execution | Pool capacity, connection leak, concurrency |
| Low acquisition, high JDBC span | DB/driver/network/result processing | Slow query, lock, network, result size |
| High pool usage, fast DB query | Connection held outside query | Transaction scope, application processing while holding connection |
| High DB lock waits, high JDBC duration | Contention inside DB | Transaction isolation, lock order, queries |
| High pending, active=max | Pool saturation | Traffic, concurrency, query duration, pool config |

Do not blame all database latency on SQL execution. Connection acquisition and transaction scope can also be sources of delay.

### 6.2. Long-running transactions

Connections are typically held for the duration of a transaction. If code performs remote HTTP calls or heavy processing inside a transaction, the connection may be held for a long time even when SQL statements are fast. Avoid overly broad transaction scopes; do not make network dependency calls while holding a transaction/connection unless necessary.

### 6.3. N+1 queries

A single request can emit hundreds of short JDBC spans due to an ORM executing queries in a loop. Each individual query may be fast, but total duration and database load become high. Tracing helps reveal the span count; ORM/database statistics help locate N+1 issues. Metrics should aggregate query count/duration by operation without attaching entity IDs as tags.

## 7. SQL metadata and data protection

SQL statements can contain literals or sensitive data. Do not put raw SQL or bind parameters into metrics. For traces, collect only normalized statement metadata in accordance with organizational policy.

| Metadata | Recommendation |
| --- | --- |
| db.system | Safe to use, normalized values |
| db.operation.name | Safe to use, SELECT/INSERT/UPDATE/DELETE |
| db.namespace/database name | Consider carefully, avoid credentials |
| Server address/port | Consider based on topology/privacy |
| SQL query text | Not by default; requires sanitization and policy |
| Bind parameter values | Do not collect by default |
| Customer/order identifiers | Do not use as metric tags |
| Exception message | Redact; prefer SQLState/category |

### 7.1. SQL statement sanitization

If query text is needed for traces, prefer parameterized and sanitized statements so literal values are not retained. For example:

~~~sql
SELECT * FROM orders WHERE customer_id = ?
~~~

Do not export statements where literals are replaced with actual data:

~~~sql
SELECT * FROM orders WHERE customer_id = 'customer-938274'
~~~

Even sanitized queries can reveal schema or business logic; enable only when needed and restrict access.

### 7.2. Database URLs and credentials

Do not write JDBC URLs containing username/password into logs, spans, or Resource attributes. Use secret management and configure redaction. Connection pool names can be used to distinguish pools, but should not contain dynamic tenant/customer identifiers.

## 8. Connection leaks and pool exhaustion

A connection that is borrowed and never returned causes active connections to climb over time. Once the pool is exhausted, new requests wait and eventually time out.

Symptoms:
- active connections stay at max;
- idle equals 0;
- pending threads increase;
- acquisition timeouts increase;
- request latency rises;
- in-use connections do not drop after traffic subsides.

### 8.1. Common causes

1. Manually managed Connection/Statement/ResultSet not closed.
2. Transaction fails to complete due to an exception or incorrect lifecycle.
3. Code holds a connection while calling a remote service.
4. Long-running queries or locks hold connections for a long time.
5. Pool max is too low for reasonable concurrency.
6. Slow DB or network causes operations to hold connections longer.

Prefer try-with-resources when managing JDBC resources manually:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "select id from orders where status = ?")) {
    statement.setString(1, "OPEN");
    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Process a row.
        }
    }
}
~~~

With Spring `JdbcTemplate`/JPA, the framework normally manages resource lifecycles; do not manually close connections managed by the transaction manager.

### 8.2. Leak detection threshold

HikariCP provides a leak detection threshold to log connections held for too long. This is a diagnostic tool, not an automatic connection reclamation mechanism. Too low a threshold causes false positives; too high may delay early detection. Use it temporarily during investigations, monitor logs, and disable or tune it once the root cause is understood.

## 9. Transaction observability

A transaction wraps a group of database operations. Observing transaction duration and outcome helps detect:
- overly long transactions;
- increasing rollback rates;
- lock contention;
- exceptions causing rollbacks;
- connections held across multiple operations.

### 9.1. Transaction span or business Observation?

Not every transaction needs a dedicated span. If HTTP server spans and JDBC spans already describe the lifecycle adequately, adding a business Observation can highlight key operations like `orders.checkout`. Keep names stable and avoid colliding with JDBC operation names.

### 9.2. Rollbacks and exceptions

A transaction rollback can result from business validation, deadlocks, timeouts, or connection failures. Log SQLState/error categories and trace redacted exceptions. Do not log full bind parameters to explain rollbacks.

## 10. Testing JDBC observability

Tests should separate pool metrics, JDBC operations, and tracing export because each test proves a different layer.

| Test | Objective | Does not prove |
| --- | --- | --- |
| DataSource binder test | Pool meters are registered | DB query instrumentation |
| JdbcTemplate integration test | SQL operation runs properly | OTLP export |
| Observation test | Custom Observation lifecycle/tags | Automatic JDBC driver instrumentation |
| Tracing test | Span context/parent relationship | Database server execution plan |
| Pool saturation test | Pending/acquisition behavior | Absolute production capacity |
| DB integration test | SQL/transaction behavior | Identical behavior across all DB engines |

### 10.1. Testing with H2 and JdbcTemplate

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class JdbcRepositoryIntegrationTest {
    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void executesQuery() {
        Integer result = jdbcTemplate.queryForObject(
                "select 1",
                Integer.class
        );

        assertThat(result).isEqualTo(1);
    }
}
~~~

This test verifies that `JdbcTemplate` connects and executes a query within the test context. It does not prove that Hikari pool metrics or JDBC spans are exported.

### 10.2. Testing pool metrics

You can inject `MeterRegistry`, borrow and return a connection, and verify that the corresponding meters are registered. Exact meter names and measurement lookups depend on the pool implementation. Avoid asserting exact active values in multi-threaded tests because state can change between reads.

### 10.3. Testing tracing context

When JDBC tracing integration is configured, run an operation inside a parent span and verify:
- the JDBC span shares the same Trace ID;
- the span has the proper parent relationship;
- operation names/attributes are normalized;
- JDBC errors follow conventions;
- no SQL bind values or credentials appear in exported attributes.

If you only have a custom Observation around the repository, the test verifies that business span; do not conclude the driver creates spans on its own.

### 10.4. Controlled pool pressure testing

Use a small pool in tests and an operation that intentionally holds a connection. Observe active, pending, and acquisition time; release the connection in a `finally` block. Never run saturation tests against a shared or production database. This tests behavior, not final production pool sizing.

## 11. Troubleshooting JDBC observability

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| No Hikari metrics | DataSource not bound or using another pool | Check DataSource type, registry, and binders |
| Active always equals max | Pool saturation or connection leak | Inspect pending, acquisition, usage, and transactions |
| Pending increasing | No connections freed quickly enough | Investigate query latency, concurrency, and pool limit |
| High acquisition time | Waiting on pool or slow connection creation | Check active/max, idle, DB connectivity |
| High usage time | Query/transaction holding connection too long | Check JDBC spans, DB locks, and transaction scope |
| Slow HTTP request with no JDBC span | JDBC not instrumented | Verify agent/framework integration |
| Pool metrics exist but no query metrics | Pool binder only measures pool | Add appropriate JDBC instrumentation or custom Observation |
| Trace missing parent | Context not propagated to worker | Check async context propagation |
| SQL appears in logs/traces | Overly verbose SQL logging/instrumentation | Sanitize, allowlist, and disable bind values |
| Meter count grows with customer ID | ID/query value used as tag | Remove dynamic tags |
| Connection timeout | Pool exhausted or DB/connectivity error | Check pending, DB health, and timeouts |
| N+1 queries | ORM issuing many small queries | Use traces/query statistics and optimize fetching |
| Deadlock/lock wait | Transaction contention | Check DB-native locks and transaction order |
| Span duration differs from DB execution time | Span includes driver/network/result processing | Cross-check with DB-native query timing |

### 11.1. Investigation workflow for slow database requests

1. Find the HTTP request with high latency in metrics.
2. Open the corresponding trace and locate business/JDBC spans.
3. Compare durations across the server span, JDBC spans, and dependency spans.
4. Check pool active/idle/pending and acquisition time at the same timestamp.
5. If the JDBC span is long, check DB-native query statistics, locks, and execution plans.
6. Check transaction scope and connection usage duration.
7. Check exceptions/SQLState, timeouts, and retries.
8. Verify telemetry contains no SQL literals, credentials, or business identifiers.

## 12. Production checklist

| Criterion | Required evidence |
| --- | --- |
| DataSource/pool recognized | Pool metrics appear in the registry |
| Pool saturation monitored | Active/max, idle, pending, acquisition, and timeouts |
| JDBC operations instrumented | Spans/Observations present if required by goals |
| Correct parent context | JDBC spans linked to the request trace |
| Safe query metadata | No bind values, PII, or credentials |
| Reasonable transaction duration | Metrics/traces or DB-native evidence |
| Low cardinality | No dynamic SQL/IDs as metric tags |
| Complementary DB-native monitoring | Locks, query stats, CPU/IO can be correlated |
| Proper connection lifecycle | Resources returned to pool |
| Intentional leak detection | Threshold tuned to avoid noise |
| Export pipeline monitored | Export errors/dropped spans tracked |
| Tests isolate layers properly | Pool, JDBC, Observation, tracing, DB integration |

## 13. Hands-on exercise: investigating pool saturation and slow JDBC

**Scenario:** `order-service` uses Spring Boot, HikariCP, and PostgreSQL. Under increased traffic, HTTP p95 latency rises, pool active connections hit max, and pending threads appear. The operations team needs to determine whether time is lost in the pool, SQL, or transactions.

**Tasks:**

1. Enable Actuator and verify Hikari pool metrics.
2. Build a dashboard for active/max, idle, pending, acquisition time, usage time, and timeouts.
3. Send controlled load to the order creation endpoint and record HTTP request latency.
4. Enable appropriate tracing integration to see database operations in request traces.
5. Add a custom business Observation if needed to distinguish `orders.create` from JDBC operations.
6. Simulate a slow query and compare acquisition time with JDBC span duration.
7. Simulate holding a connection too long; observe pending threads and timeouts.
8. Check whether the transaction scope makes HTTP dependency calls while holding a connection.
9. Verify SQL telemetry contains no bind values, tokens, or PII.
10. Run a test with a small pool and prove connections are returned in `finally`.
11. Use DB-native query statistics/lock views to correlate a slow JDBC span.
12. Write a runbook distinguishing pool saturation, connection leaks, slow queries, and database locks.

**Expected outcomes:** pool metrics dashboard, traces showing database operations if instrumentation is configured, JDBC/pool tests, safe metadata examples, and a latency investigation runbook.

## 14. Key takeaways

**JDBC observability** requires visibility into both the pool and database operations. Pool metrics report connection availability, pending threads, acquisition, and usage; JDBC Observation/tracing describes operations and links them to requests; database-native monitoring explains execution plans, locks, CPU, and IO. These layers complement rather than replace each other.

Do not conclude a database query is slow solely from HTTP duration or active connections. Compare acquisition time, connection usage, JDBC spans, and DB-native statistics. Use stable Observation names and low-cardinality tags; never put raw SQL, bind parameters, credentials, or customer IDs into metrics or traces. Test each layer separately, monitor pool pressure, and keep transaction/resource lifecycles short and explicit.

**References:**
- [Spring Boot — JDBC Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Micrometer — JVM and DataSource Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [OpenTelemetry — Database Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/db/)
- [JDBC — Java Documentation](https://docs.oracle.com/javase/8/docs/technotes/guides/jdbc/)
