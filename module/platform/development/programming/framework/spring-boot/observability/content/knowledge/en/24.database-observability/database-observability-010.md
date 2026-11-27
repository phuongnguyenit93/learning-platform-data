# Tracing database calls in Spring Boot

When an HTTP request accesses a database, processing time can be spent across several stages: waiting for a connection from the pool, sending SQL through the JDBC driver, waiting for database execution, reading the result set, and mapping data. An HTTP server span reveals total request duration, but does not by itself pinpoint which database call consumed the time. **Tracing database calls** adds spans for database operations, places them properly within the trace, links them to their parent request, and helps compare time spent in the application, JDBC client, and database.

Within the **SPRING_BOOT_OBSERVABILITY** module, database tracing complements Micrometer Observation, metrics, logs, and distributed tracing. This lesson belongs to the **Database observability** chapter and focuses on **tracing database calls**: span modeling for database operations, instrumenting JDBC, distinguishing agent/framework/proxy/custom Observation approaches, handling SQL metadata safely, linking transactions and parent contexts, testing, and troubleshooting missing or broken database spans.

## Learning Objectives

After this lesson, you will be able to:
1. Explain the place of database spans in a distributed trace.
2. Distinguish JDBC client spans, business Observations, and pool metrics.
3. Identify options for instrumenting database calls in Spring Boot.
4. Read trace hierarchy, duration, status, and database attributes.
5. Understand parent context in transactions, async work, and nested database calls.
6. Control SQL text, bind values, cardinality, and sensitive data.
7. Test database spans using a test exporter and test database.
8. Investigate slow queries, missing spans, duplicate spans, and propagation failures.

## 1. What is tracing a database call?

A database span represents a database operation within a trace. A span typically carries an operation name, start/end timestamps, status, attributes describing the database system/operation, and a parent relationship to the active span.

~~~text
Trace ID: 4bf92f...

HTTP server span: POST /orders
  └─ Business span: orders.create
       ├─ JDBC span: INSERT orders
       ├─ JDBC span: SELECT inventory
       └─ JDBC span: UPDATE order_status
~~~

Database spans show which operation took time and where errors occurred. They do not necessarily equal pure database engine SQL execution time; depending on the instrumentation boundary, duration can include driver overhead, network latency, connection handling, and result processing.

### 1.1. Where do database spans sit in a trace?

~~~mermaid
flowchart TD
    Request["Incoming HTTP request"] --> Server["HTTP server span"]
    Server --> Business["Business Observation / span"]
    Business --> JdbcA["JDBC client span: SELECT"]
    Business --> JdbcB["JDBC client span: INSERT"]
    JdbcB --> Database["Database server"]
    Server --> Logs["Logs with traceId/spanId"]
    JdbcA --> Export["Tracing exporter"]
    JdbcB --> Export
    Server --> Export
    Export --> Backend["Trace backend"]
~~~

In a trace viewer, database spans normally sit beneath a server span or business span depending on active context. If code invokes multiple repository methods, each instrumented call can create its own span. Avoid collapsing all database activity into a single span if individual operations need investigation.

### 1.2. Database spans and HTTP spans

An HTTP server span encompasses request handling. A JDBC span wraps only a database operation. If a server span takes 900 ms and JDBC spans total 500 ms, the remaining time may come from controller/service logic, pool waits excluded from JDBC spans, remote calls, or other work. Do not sum all child span durations and expect them to equal the server span: spans can be nested or execute concurrently.

## 2. Ways to instrument database calls

The JDBC API does not automatically guarantee tracing spans. A suitable instrumentation mechanism is required.

| Approach | Instrumentation point | Pros | Caveats |
| --- | --- | --- | --- |
| Java agent | JDBC calls via bytecode hooks | Broad library coverage with minimal code changes | Verify agent/module compatibility and overhead |
| Framework-native instrumentation | Spring/Micrometer/ORM integration | Integrated with framework lifecycle and Observation | Coverage depends on framework/version |
| DataSource proxy/wrapper | Connection/Statement operations | Adds instrumentation at the DataSource | Easily overlaps with agent/native instrumentation |
| Custom Observation | Business/repository boundary | Business-meaningful operation names | Does not automatically describe every SQL statement |
| DB-native monitoring | Inside database engine | Query plans, locks, execution statistics | Does not replace distributed trace context |

### 2.1. Do not confuse the tracing bridge with JDBC instrumentation

A Micrometer Tracing bridge connects Micrometer Tracing to OpenTelemetry. It enables spans to be managed and exported, but does not guarantee every JDBC call is instrumented. An OTLP exporter only transports spans that have already been created; without JDBC instrumentation, the exporter cannot discover SQL statements on its own.

### 2.2. Choose one instrumentation owner

If both a Java agent and a DataSource proxy instrument the same statement, traces can contain two near-identical spans. This clutters timelines and increases telemetry volume. Designate one primary mechanism at the JDBC boundary; a service-layer business Observation can serve as a parent span when it describes a distinct operation.

### 2.3. Verify support scope

Before enabling in production, verify database vendor, JDBC driver version, Spring Boot/Spring Framework version, tracing API/SDK compatibility, agent modules, and async/transaction behavior. Do not assume a PostgreSQL setup applies unchanged to Oracle, SQL Server, or MySQL.

## 3. Trace hierarchy from request to JDBC

~~~mermaid
sequenceDiagram
    participant Client
    participant App as Spring Boot
    participant Repo as Repository/JdbcTemplate
    participant Driver as JDBC driver
    participant DB as Database
    participant Collector
    Client->>App: POST /orders + traceparent
    Note over App: HTTP server span
    App->>Repo: createOrder()
    Note over App,Repo: Business span orders.create
    Repo->>Driver: PreparedStatement.execute()
    Note over Repo,Driver: JDBC client span
    Driver->>DB: SQL operation
    DB-->>Driver: Result
    Driver-->>Repo: Update count / rows
    Repo-->>App: Return
    App-->>Client: HTTP response
    App->>Collector: Export spans
~~~

The Trace ID is shared across the entire trace; each span gets its own Span ID. A JDBC span should have the active span at the start of the database call as its parent. When invoked from an HTTP request, the parent chain can flow from server span through business span to JDBC span.

### 3.1. Parent-child and nested spans

Example:
- server span: `POST /orders`;
- business span: `orders.create`;
- JDBC span: `INSERT orders`;
- JDBC span: `SELECT inventory`.

JDBC spans are children of the business span if it is active at invocation time. Without a business span, they can be direct children of the server span. Do not fake parent spans manually by copying Trace ID/Span ID into MDC; use tracing context/scope APIs so the SDK manages relationships.

### 3.2. Concurrent JDBC calls

A business operation may execute multiple database calls on an executor. Context must be propagated to worker threads. Otherwise, spans can become detached root traces or lack expected parents. When running in parallel, child spans can overlap; summed durations will not equal wall-clock request duration.

## 4. Database attributes and semantic conventions

A database span needs just enough metadata to identify the system and operation type. OpenTelemetry semantic conventions may use attributes such as `db.system.name`, `db.operation.name`, `db.namespace`, `server.address`, and `server.port`, depending on convention version and instrumentation.

| Attribute | Meaning | Example |
| --- | --- | --- |
| `db.system.name` | Database engine | `postgresql` |
| `db.operation.name` | Primary operation | `SELECT`, `INSERT` |
| `db.namespace` | Database/schema namespace | `commerce` |
| `server.address` | DB host | `postgres.internal` |
| `server.port` | DB port | `5432` |
| `db.collection.name` | Table/collection if convention applies | `orders` |
| `db.query.text` | Query text if permitted | `SELECT ... WHERE id = ?` |
| `error.type` | Error category | `SQLTransientConnectionException` |

Attribute names and semantic convention requirements can change across versions. Check which instrumentation version and convention are emitted; do not rename keys arbitrarily if dashboards/backends are not aligned.

### 4.1. Operation name and query text

Operation names should describe stable operations, such as `SELECT` or `INSERT`. Never put customer ID/order ID into span names. Query text can help identify SQL statements, but must be sanitized/parameterized. In many systems, normalized operation names and statement summaries suffice.

### 4.2. SQL bind parameters

Do not collect bind parameter values by default. Parameters can include emails, access tokens, payment data, personal identifiers, or secrets. If an investigation requires specific values, use access-controlled database tooling and proper data governance rather than shipping bulk values into traces.

## 5. Configuring tracing in Spring Boot

Example dependencies for Spring Boot using the Micrometer Tracing OpenTelemetry bridge and OTLP exporter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Keep versions aligned with the Spring Boot BOM. These dependencies set up the tracing bridge/export path, not a guarantee that JDBC statement instrumentation is automatically enabled.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

The endpoint must point to a Collector reachable from the application. In containers/Kubernetes, use an appropriate DNS/service address rather than `localhost` if the Collector runs in another container/pod.

### 5.1. Enabling JDBC instrumentation via your chosen mechanism

If using a Java agent, configure the agent and corresponding JDBC module for your version. If using a DataSource proxy, register the wrapper as the Spring-injected DataSource and verify transaction managers and repositories use that wrapper. If your framework version includes native JDBC observation, check properties and auto-configuration conditions in your version's docs.

Do not add guessed properties or a second proxy without confirming which instrumentation is already active.

### 5.2. Custom business Observation around repositories

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InvoiceRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry registry;

    public InvoiceRepository(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry registry
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.registry = registry;
    }

    public Integer countUnpaidInvoices() {
        return Observation.createNotStarted("invoice.repository.count-unpaid", registry)
                .lowCardinalityKeyValue("db.operation", "SELECT")
                .observe(() -> jdbcTemplate.queryForObject(
                        "select count(*) from invoice where status = ?",
                        Integer.class,
                        "UNPAID"
                ));
    }
}
~~~

This Observation describes the repository operation and generates spans/metrics via configured handlers. It is not necessarily a span per individual JDBC statement. If a JDBC agent also creates an inner span, the business -> JDBC hierarchy can be helpful. Avoid adding business spans as a substitute for JDBC instrumentation when per-statement timing is needed.

## 6. Distinguishing pool wait, JDBC span, and database execution

~~~text
Application requests connection
  ├─ Wait for pool connection
  ├─ Obtain JDBC Connection
  ├─ Prepare/bind statement
  ├─ Execute over network
  ├─ Database execution / lock waits
  ├─ Transfer result
  ├─ Map rows
  └─ Return connection
~~~

Instrumentation at `JDBC Statement` may wrap only prepare/execute/result operations; it does not necessarily include time spent waiting on the DataSource pool. Pool metrics supply separate acquisition/usage measurements.

| Observation | May indicate | Cross-check |
| --- | --- | --- |
| High pool acquisition time | Waiting for a connection | Active/idle/pending/max |
| High JDBC span duration | Slow client-side operation | DB query stats, network, result size |
| High DB execution time | Slow engine execution/locks | Explain plans, locks, DB CPU/IO |
| High connection usage yet short JDBC spans | Connection held outside execute | Transaction/application code |
| High HTTP span, low JDBC spans | Time spent in another layer | Business spans, remote calls, serialization |

Do not interpret JDBC span duration as pure engine time when instrumentation does not measure directly inside the database server.

## 7. Transaction boundaries and database spans

Spring transaction management typically manages connection lifecycles through a transaction manager. Multiple JDBC operations can execute inside a single transaction.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void settleInvoice() {
        repository.markPaid();
        repository.writeAuditRecord();
    }
}
~~~

Database spans can be children within a transaction/business context, though not every transaction automatically becomes its own span. Instrumentation defines span boundaries. When measuring transaction duration, create a business Observation with a stable name around the use case and avoid duplicating spans for individual JDBC calls.

### 7.1. Rollbacks and exceptions

A database span can finish with an error status when a JDBC operation throws an exception. The transaction may subsequently roll back. Distinguish a failed SQL operation, a transaction rollback caused by a later operation, an intentional business-rule rollback, and a commit/connection failure at transaction end.

Do not blame the final SQL statement if the rollback originated from other logic. Inspect span events/status, application logs, and transaction outcomes.

### 7.2. Overly long transactions

Long transactions can hold connections while the application calls remote services or processes business logic. Individual database spans may look short while connection usage remains high. Tracing business spans alongside pool metrics helps uncover time spent outside SQL.

## 8. Cardinality, privacy, and query capture

| Data | Metrics | Traces | Policy |
| --- | --- | --- | --- |
| `db.system.name` | Possible | Yes | Normalized values |
| `db.operation.name` | Yes | Yes | Small operation set |
| database/schema name | Evaluate | Possible | Must not contain dynamic tenants |
| `server.address`/`port` | Not as default labels | Possible | Control topology exposure |
| raw SQL text | No | Not by default | Sanitize and review |
| bind parameter values | No | No | May contain secrets/PII |
| customer/order ID | No | Not by default | High cardinality |
| exception message | No | Not by default | Redact, prefer error category |
| JDBC URL credentials | No | No | Secret |

### 8.1. Never use SQL text as a metric tag

SQL text can vary by literals, whitespace, or generated queries. Using it as a tag can produce unbounded time series. Metrics should group by operation or controlled stable query names.

### 8.2. Query normalization and redaction

When identifying query shapes, use query fingerprints or normalized statement names from vetted instrumentation/backends. Fingerprints can still reveal schema structure and require policy governance. Redact before telemetry leaves the process; UI masking only hides display, while payloads may already be stored in Collectors, queues, or storage.

Never write credentials into `Resource`, span attributes, MDC, or exception messages.

## 9. Logs and database spans

Log events can carry `traceId`/`spanId` via MDC. When a database operation fails, log the exception inside the active span context so operators can locate the corresponding trace.

~~~text
ERROR traceId=4bf92f... spanId=8a31c2...
  InvoiceRepository - Database operation failed
  error.type=SQLTransientConnectionException
~~~

Do not log raw bind values or full SQL without sanitization. Use SQLState, error categories, and normalized operation names.

### 9.1. From logs to database spans

1. Find the log event by `traceId`.
2. Open the trace backend with the same Trace ID.
3. Locate the JDBC span by `spanId` if the log was emitted inside that span.
4. Read the operation, duration, status, and database attributes.
5. Inspect parent business/server spans for request context.
6. Cross-check pool metrics and database-native query stats at the same timestamp.

A log carrying a `traceId` does not guarantee a database span was created or exported. Sampling may drop the trace; JDBC instrumentation may be disabled; the exporter or Collector may drop spans. Investigate each layer separately.

## 10. Testing database tracing

| Test type | Objective | Does not prove on its own |
| --- | --- | --- |
| Repository integration test | JDBC operation executes | JDBC span exists |
| Observation test | Custom business Observation | Driver instrumentation |
| In-memory span exporter | Span name/context/attributes | OTLP network export |
| Agent integration test | Agent instruments JDBC calls | Production DB performance |
| Collector smoke test | OTLP spans are received | SQL execution plan |
| DB-native test | Query/lock behavior | Trace propagation |

### 10.1. Testing a custom Observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class InvoiceObservationTest {
    @Test
    void recordsRepositoryOperation() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        Observation.createNotStarted("invoice.repository.count-unpaid", registry)
                .lowCardinalityKeyValue("db.operation", "SELECT")
                .observe(() -> { });
        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

Assertion APIs may vary across Micrometer versions. This test only verifies the business Observation lifecycle; it does not prove the JDBC driver creates spans automatically.

### 10.2. Testing parent-child spans

With a tracing SDK test setup and an in-memory exporter:
1. Create a parent span.
2. Put the parent in scope.
3. Execute a JDBC operation through the instrumentation under test.
4. End the parent.
5. Collect spans from the exporter.
6. Assert the JDBC span shares the Trace ID and has the expected parent span ID.
7. Verify operation/attributes contain no bind values.

If using an agent, tests must run with the agent attached to the test JVM process; unit tests without the agent do not verify agent instrumentation.

### 10.3. Testing errors and transaction rollbacks

Using a test database, execute a controlled failing statement and verify the exception, span status/error conventions, transaction rollback, absence of sensitive data, and restoration of parent context after the exception. Never use a production database to intentionally induce deadlocks or connection exhaustion in tests.

## 11. Troubleshooting database spans

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Trace only has HTTP span | JDBC instrumentation disabled | Identify active agent/native/proxy mechanism |
| Pool metrics exist but no JDBC spans | Pool binder does not instrument statements | Add JDBC instrumentation |
| Two spans per statement | Agent and proxy both instrumenting | Choose one instrumentation owner |
| JDBC span becomes a root trace | Parent context inactive/not propagated | Check current span and async context |
| Span lacks `db.system` | Instrumentation missing database metadata | Check driver/semantic conventions |
| Span contains raw SQL literals | Statement capture unsanitized | Redact/disable query text |
| Short JDBC span yet slow request | Pool wait or time outside JDBC execute | Cross-check acquisition/usage and business spans |
| Long JDBC span | DB, network, driver, or result mapping | Check DB-native query stats, locks, result size |
| Span shows no error despite rollback | Rollback occurred after operation or via business rule | Track transaction outcome separately |
| Unexpectedly high span count | Duplicate instrumentation or N+1 | Inspect hierarchy and query count |
| Database span missing in async | Context not propagated | Check executor/context propagation |
| Exporter not sending spans | Sampling, queue, endpoint, or Collector | Inspect tracing pipeline |

### 11.1. Investigation workflow

1. Identify which JDBC instrumentation mechanism is running: agent, native integration, or DataSource wrapper.
2. Verify whether a test query produces a span.
3. Inspect the span's parent, Trace ID, and Span ID.
4. Check operation name and database attributes.
5. Compare JDBC span duration with pool acquisition/usage.
6. If the query is slow, cross-check DB-native execution stats, lock waits, and query plans.
7. Check for duplicate spans, N+1 patterns, and long transaction durations.
8. Verify SQL capture, bind values, credentials, and PII are filtered.
9. If spans are created locally but missing in the backend, investigate sampler/exporter/Collector.

## 12. Production checklist

| Criterion | Required evidence |
| --- | --- |
| JDBC instrumentation clearly chosen | Agent/native/proxy documented |
| No duplicate instrumentation | Single statement does not create duplicate spans |
| Correct span hierarchy | JDBC spans parented by request/business span |
| Normalized database attributes | `db.system`/operation conform to conventions |
| Safe query capture | No bind values, secrets, or PII |
| Independent pool metrics | Active/idle/pending/acquisition monitored |
| Complementary DB-native monitoring | Query stats, locks, CPU/IO correlated |
| Clear transaction outcomes | Commit/rollback/errors observed |
| Async context tested | Worker spans have proper parents |
| Low cardinality | No SQL/customer IDs as metric labels |
| Sampling/export monitored | Dropped spans and exporter errors alerted |
| Meaningful regression tests | Parent-child, errors, rollbacks, and redaction |

## 13. Hands-on exercise: tracing a database call

**Scenario:** `order-service` receives an HTTP request, creates an order in a transaction, and writes to PostgreSQL. HTTP traces currently show only the server span; the operations team wants visibility into each database operation.

**Tasks:**
1. Enable Spring Boot Actuator and a Micrometer Tracing bridge aligned with the BOM.
2. Choose one JDBC instrumentation mechanism (agent, native integration, or DataSource proxy) and record its version.
3. Use a test database to send a request flowing through a repository/`JdbcTemplate`.
4. Collect traces and verify database spans appear beneath the server/business span.
5. Inspect Trace ID, Span ID, parent relationship, and operation name.
6. Run SELECT/INSERT/UPDATE operations and compare span durations.
7. Trigger a controlled failing statement and verify span status/exception.
8. Trigger a rollback and distinguish statement errors from transaction outcomes.
9. Compare JDBC span duration against Hikari acquisition/usage metrics.
10. Verify SQL text/bind values/credentials are not exported outside policy.
11. Test with a second instrumentation enabled to recognize duplicate spans, then keep only one mechanism.
12. Write a runbook for missing JDBC spans, root spans, slow database calls, and SQL leakage.

**Expected outcomes:** traces containing database spans, clear hierarchy, safe metadata, tests proving the chosen instrumentation, and an investigation runbook.

## 14. Key takeaways

**Tracing database calls** places database operations inside distributed traces to explain which JDBC operations a request executed, how long they took, and where failures occurred. The Micrometer Tracing bridge/exporter transports spans once created; dedicated JDBC instrumentation (agent, framework integration, or DataSource wrapper) determines which statements are instrumented. Custom business Observations add business-level operation context and do not replace JDBC spans when per-statement timing is required.

Read database spans alongside HTTP/business spans, pool acquisition/usage metrics, and DB-native query statistics. Do not equate JDBC duration with pure engine execution time, and do not confuse pool metrics with query spans. Preserve parent context, avoid duplicate instrumentation, sanitize SQL, and never capture bind values, credentials, or PII. Use metrics for trends and pool health, traces to investigate individual requests, and logs to inspect redacted failures.

**References:**
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — JDBC Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [OpenTelemetry — Database Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/db/)
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [JDBC — Java Documentation](https://docs.oracle.com/javase/8/docs/technotes/guides/jdbc/)
