# JDBC observation starter

Within the **Database observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, the JDBC observation starter is the starting point for observing database access over JDBC in Spring Boot applications. When DataSource and JDBC instrumentation are configured properly, query operations can emit Observation/trace spans, helping identify slow statements, connection errors, and database dependencies affecting requests.

Three kinds of signals must be distinguished: **JDBC observations/traces** describe individual SQL executions; **DataSource pool metrics** describe connection pool state; **database/server metrics** describe database health. They complement each other without replacing one another. High active connections in the pool do not prove any specific SQL query is slow; a slow JDBC span alone is not enough to conclude the database server is overloaded.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain the role of JDBC observation in Spring Boot.
2. Distinguish database spans, pool metrics, and database server metrics.
3. Identify the conditions required for JDBC operations to be instrumented.
4. Configure a tracing bridge/exporter and verify dependency compatibility.
5. Understand how DataSource instrumentation wraps connection acquisition and JDBC statements.
6. Read database spans and correlate them with HTTP/server spans.
7. Recognize limitations with ORMs, R2DBC, and custom drivers.
8. Control SQL attributes, bind values, cardinality, and sensitive data.
9. Inspect spans via the trace backend and metrics via Actuator.
10. Write integration tests and runbooks for database observability.

## 2. What is the JDBC observation starter?

Spring Boot Actuator and Micrometer Tracing provide observability infrastructure; JDBC instrumentation adds visibility for operations going through a JDBC DataSource. Depending on the Spring Boot version and tracer, the starter/bridge dependency differs. When instrumentation is enabled, JDBC calls can produce spans representing database operations, with attributes describing the database system, operation, and statement according to instrumentation policy.

A starter does not automatically turn every database access into spans if the application does not go through an instrumented JDBC path:
- JDBC through an instrumented DataSource can produce database spans.
- Hibernate executes SQL over JDBC; spans can be created at the JDBC layer, though not every ORM operation has a dedicated business span.
- R2DBC is a reactive database API, not JDBC; it requires corresponding instrumentation.
- Native driver APIs or custom clients may sit outside JDBC instrumentation.
- DataSource proxies/pools or custom wrappers can affect where instrumentation sits.

Artifact names and enabling mechanisms depend on the Spring Boot/Spring Framework/Micrometer version. Read the documentation for your exact version rather than copying similarly named dependencies from old tutorials.

## 3. Layers of database observability

| Signal | What it observes | Example |
| --- | --- | --- |
| JDBC observation/span | How long a JDBC database operation took and how it ended. | SELECT on `orders` took 420 ms. |
| DataSource pool metrics | How the connection pool is utilizing resources. | Active, idle, max, pending. |
| Database server metrics | Health and load inside the DB engine. | CPU, locks, buffer cache, replication lag. |
| Application logs | Specific business/error events. | Transaction rollback. |
| HTTP/server span | Inbound request wrapping multiple dependency calls. | `POST /orders` calls JDBC and inventory. |

~~~mermaid
flowchart TD
    HTTP["HTTP server request span"]
    HTTP --> Service["Service / repository"]
    Service --> JDBC["JDBC observation / database span"]
    JDBC --> DS["DataSource / connection pool"]
    DS --> DB["Database engine"]
    DS --> PoolMetrics["Pool metrics"]
    DB --> DBMetrics["Database server metrics"]
    JDBC --> TraceBackend["Trace backend"]
    PoolMetrics --> MetricsBackend["Metrics backend"]
    DBMetrics --> MetricsBackend
~~~

Database spans show timing observed at the application boundary. Pool metrics show connection borrowing and holding. Database server metrics show what happens inside the DB engine. Cross-referencing all three pinpoints the bottleneck.

## 4. Dependencies and version compatibility

With Spring Boot, prefer starters and dependency management provided by Boot. The tracing bridge determines the tracer implementation; JDBC instrumentation adds visibility for database calls. Do not add multiple bridges or overlapping auto-instrumentation layers at the same time.

Spring Boot 3.x commonly uses Micrometer Tracing with OpenTelemetry as follows:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
    runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

Or choose Brave instead of OpenTelemetry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
    runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

These two examples are alternatives. Do not declare both the OTel bridge and the Brave bridge. The MySQL driver is just an example; use your project's actual driver.

In newer Spring Boot major versions, tracing starters/modules may be reorganized. Do not assume an artifact named JDBC observation starter stays identical across all versions. Check the dependency tree and reference docs for your minor version. If using the OpenTelemetry Java Agent, the agent can instrument JDBC automatically; avoid adding duplicate manual instrumentation.

## 5. Enabling tracing and exporting database spans

JDBC instrumentation typically exports database spans through the configured tracing pipeline. Spring Boot 3.x example with OTLP:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Property namespaces and endpoint semantics vary across Spring Boot versions. Some newer Boot lines organize tracing export under a different namespace. Check your exact version and Collector protocol; HTTP/protobuf typically uses port 4318 with a signal path, while gRPC typically uses port 4317.

If using Zipkin/Brave, configure the Zipkin reporter and corresponding endpoint; do not put a Zipkin endpoint in an OTLP property. Sampling probability controls the ratio of traces sampled, not whether JDBC instrumentation is enabled. If a trace is head-sampled out, its database spans will not appear in the backend either.

Verify there is exactly one Micrometer Tracing bridge; `ObservationRegistry` has a tracing handler; the tracer/exporter is wired properly; JDBC instrumentation is actually active; the exporter endpoint matches the Collector receiver; and no Java agent/custom instrumentation creates duplicate spans.

## 6. Where does JDBC instrumentation operate?

JDBC instrumentation typically observes activity at the DataSource/driver boundary, where the application borrows connections and executes statements. Depending on the implementation, spans may record the database system/vendor, operation such as SELECT/INSERT/UPDATE/DELETE, allowed database name or connection metadata, statement representation, error status/exception type, and duration.

Not every implementation records every attribute. OpenTelemetry semantic conventions and Micrometer instrumentation versions can differ in attribute names and detail levels. Inspect actual span payloads.

### JDBC spans and ORM operations

A single repository call can execute multiple SQL statements: lazy loading, N+1 selects, flushes, or transaction queries. JDBC spans typically reflect each instrumented JDBC operation; they do not necessarily correspond one-to-one with repository methods.

For example, a repository method issuing 1 SELECT may create one span; an entity graph causing 12 SELECTs can create multiple spans; a transaction can span many statements; a batch update can group multiple row operations into one JDBC call. Use the trace waterfall to spot the number of database calls. If you see many repeated short spans, inspect N+1 queries, ORM fetch strategies, and batching.

## 7. DataSource and connection pool metrics

Spring Boot Actuator can instrument a DataSource and expose pool metrics when the pool implementation is supported and an appropriate registry exists. With HikariCP, metrics typically cover active/idle/max/minimum connections and pending threads waiting for a connection.

Example queries:

~~~http
GET /actuator/metrics/jdbc.connections.active
GET /actuator/metrics/jdbc.connections.idle
GET /actuator/metrics/hikaricp.connections.pending
~~~

Exact meter names depend on the pool, version, and binders. Some pool metrics live under the `hikaricp.*` namespace instead of `jdbc.*`; inspect Actuator `/actuator/metrics` to confirm.

If JDBC spans are slow while pool active connections are not high, the bottleneck may be DB execution or the network. If pending threads rise and connection acquisition is slow, the pool may be exhausted or connections are held too long. Do not mechanically increase max pool size: more connections can put heavier load on the DB server and increase contention. Tune pools based on DB capacity and application replica counts.

## 8. Correlating HTTP spans and JDBC spans

In an inbound request, tracing context is propagated from the server span through services/repositories to JDBC instrumentation. The database span is typically a child span or sits within the current request's trace tree.

~~~mermaid
sequenceDiagram
    participant Client
    participant App as order-service
    participant Repo as OrderRepository
    participant DS as Instrumented DataSource
    participant DB as Database
    participant Trace as Trace backend

    Client->>App: POST /orders
    Note over App: HTTP server span
    App->>Repo: save(order)
    Repo->>DS: execute INSERT
    Note over DS: JDBC/database span
    DS->>DB: SQL
    DB-->>DS: Result
    DS-->>Repo: Update count
    Repo-->>App: Saved
    App-->>Client: 201 Created
    DS->>Trace: Export DB span
    App->>Trace: Export server span
~~~

If a database span appears as a separate root trace, check context propagation and JDBC instrumentation. Verify spans are not dropped by sampling decisions or the exporter.

## 9. SQL statement attributes and sensitive data

SQL statements can contain literal values or sensitive schema details:

~~~sql
SELECT * FROM users WHERE email = 'alice@example.com';
UPDATE accounts SET balance = 1000000 WHERE account_id = 'A-9182';
~~~

Some instrumentations can normalize SQL or record only operation/statement summaries, but do not assume every driver/agent masks literal values automatically.

- Do not export bind parameter values if they contain PII, secrets, or payment data.
- Prefer statement summaries/normalized queries when supported by instrumentation.
- Limit the length of SQL attributes.
- Do not attach raw database URLs/connection strings containing username/password to spans.
- Check whether exception messages embed SQL or parameter values.
- Use database system, operation, and controlled query fingerprints when possible.
- Protect trace backends with RBAC and appropriate retention policies.

Database spans can have high-cardinality statement attributes. Do not use full SQL text as a metric tag. Metric dimensions should remain stable, such as datasource name, operation, and outcome.

## 10. Transactions and connection lifecycle

A transaction can last longer than a single SQL statement. Database spans typically reflect individual instrumented JDBC operations; they do not necessarily encompass the entire business transaction or the full time a connection is held.

A transaction may acquire a connection, begin the transaction, run SELECT/UPDATE statements, commit/rollback, and return the connection to the pool. A trace may contain multiple spans for statements, while pool metrics reflect the connection being held. If a transaction stays open long while SQL spans are short, check application logic between queries, lock waits, transaction propagation, and connection leaks.

Do not infer transaction duration simply by summing database span durations if processing time occurs between statements.

## 11. Sampling and database tracing cost

Each request can generate multiple JDBC spans. Estimate:

~~~text
database_spans_per_second =
    inbound_requests_per_second
    * average_jdbc_calls_per_request
    * trace_sampling_ratio
~~~

For example, 300 requests/second, averaging 6 JDBC calls/request, and 10% sampling:

~~~text
300 * 6 * 0.1 = 180 database spans/second
~~~

This is an estimate; retries, batches, async operations, and spans not tied to inbound requests can change actual volume.

Sampling reduces stored traces, but does not replace controlling statement attributes and cardinality. Use parent-based sampling to keep decisions consistent across services. If using tail sampling at the Collector, applications must send enough required spans; spans dropped by a head sampler cannot be recovered by the tail sampler.

## 12. DataSource configuration and database names

Spring Boot configures a DataSource via properties or beans. Example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/orders
    username: DB_USERNAME_FROM_SECRET
    password: DB_PASSWORD_FROM_SECRET
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3s
~~~

Do not log raw URLs/usernames/passwords. Connection strings can include host, database name, and credentials. If database names are attached to telemetry, verify policy and cardinality.

If the application has multiple DataSources, give them clear names/qualifiers, verify each pool has separate metrics, verify spans identify the appropriate DataSource/database if instrumentation supports it, and avoid using dynamic tenant database names as metric tags.

## 13. Verifying database spans and metrics

Send a request that performs JDBC operations, then look up the trace by service name. Inspect the HTTP/server span, underlying database/JDBC spans, parent-child relationships, duration/operation, error status/exception type, and absence of SQL literals/credentials/PII.

Actuator:

~~~http
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
GET /actuator/metrics/jdbc.connections.active
~~~

Pool metric names may differ. Expose only necessary endpoints and protect them with Spring Security/network policies.

The trace backend answers "which operations did this request perform and how long did they take at the application boundary?". Database monitoring answers "what load, locks, or replication lag is the database engine experiencing?". Compare query latency against DB CPU, lock waits, slow query logs, and connection pool metrics.

## 14. Testing JDBC observation

Integration tests should use a real test database or Testcontainers when verifying the JDBC path, DataSource instrumentation, and spans. H2 is convenient for simple tests, but differs in driver and SQL semantics from production databases.

Test cases:
1. A successful query produces a database span.
2. An SQL exception is recorded with the appropriate error status/type.
3. Multiple statements produce the expected number of spans.
4. Spans are attached to the current trace.
5. DataSource pool metrics are registered.
6. SQL attributes do not contain test canary PII/secrets.
7. Transaction commit/rollback preserves context.
8. Instrumentation does not create duplicate spans when an agent is present.

You can use an in-memory exporter/test exporter compatible with your tracer version to inspect spans without a real backend. End-to-end integration tests can use a test Collector/backend to verify export. Do not assert exact names of every span attribute if conventions shift across versions; verify key contracts such as span presence, trace relationships, operation, and zero data leakage.

## 15. Cases not covered by JDBC instrumentation

The JDBC observation starter is not universal database instrumentation:
- R2DBC uses a reactive protocol and needs its own instrumentation.
- MongoDB, Redis, and Elasticsearch have separate client instrumentations.
- Native driver APIs may bypass JDBC.
- Some ORM/cache operations generate no JDBC call and thus no JDBC span.
- Stored procedures/batch operations may be represented differently per driver.
- Async database calls may require separate context propagation.

If the backend shows no database spans, identify the actual API the application uses before adding JDBC dependencies. Do not instrument a DataSource that is not on the actual database access path.

## 16. Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| HTTP spans exist but no JDBC spans | JDBC instrumentation missing/disabled or queries go through another client. | Inspect DataSource path, starter/agent, and tracer setup. |
| JDBC spans are outside HTTP trace | Context propagation lost or instrumentation created a separate SDK. | Check `ObservationRegistry`, current span, and DataSource instrumentation. |
| Duplicate spans appear | OTel agent and Micrometer/JDBC instrumentation both active. | Inspect dependencies/agent extensions and disable one overlapping layer. |
| High pool active, short query spans | Connection held in application/transaction or leaked. | Check transaction lifecycle and pool usage. |
| Long query spans, pool not exhausted | DB execution, locks, network, or driver delay. | Cross-check slow query logs, DB metrics, and span timing. |
| No pool metrics | Pool binder/Actuator/registry not configured or pool unsupported. | Inspect meter list and DataSource implementation. |
| SQL text exposes literals | Instrumentation records raw statements or exceptions embed SQL. | Inspect span payload, statement sanitizer, and exporter processors. |
| Unclear DataSource name | Multiple DataSources lack names/qualifiers. | Assign stable bean identities and inspect attributes. |
| H2 tests produce spans but prod DB does not | Production driver/proxy/connection pool differs. | Test with the same database family and driver. |
| SQL errors missing from traces | Exception caught/translated or span status convention not marked. | Check error recording and exception mapping. |

## 17. Runbook for verifying JDBC observability

1. Identify whether database access uses JDBC, R2DBC, or a native client.
2. Check Spring Boot version and dependencies/tracing bridge.
3. Inspect the DataSource bean and connection pool implementation.
4. Send a request executing a simple SQL statement.
5. Locate the trace and verify the database span beneath the HTTP/server span.
6. Check operation, duration, DataSource identity, and error status.
7. Check pool metrics active/idle/pending and connection limits.
8. Trigger an SQL error and verify exception/error handling.
9. Audit statement attributes, connection strings, credentials, and PII.
10. Check sampling/exporter/Collector drops if spans do not reach the backend.
11. Compare span timing against database slow query logs and server metrics.
12. Record versions, driver, pool, instrumentation source, and test results.

## 18. Self-check exercises

### Exercise 1 — Distinguishing signals

A request has an HTTP span and a JDBC span. HikariCP also reports high active connections. What do these three pieces of data tell you?

**Answer:** The HTTP span describes the overall request; the JDBC span describes the database exchange; active connections describe pool usage. Compare durations alongside pending/idle metrics to pinpoint the bottleneck.

### Exercise 2 — Missing JDBC spans

An application uses R2DBC, yet a JDBC observation dependency was added. Why are no database spans appearing?

**Answer:** R2DBC does not go through the JDBC DataSource/driver path. You need instrumentation suited for R2DBC rather than JDBC.

### Exercise 3 — SQL cardinality

Should you use full SQL text as a metric tag to filter slow queries?

**Answer:** No. SQL literals and dynamic statements create high cardinality and can expose data. Use stable operation/query fingerprints or controlled trace attributes.

### Exercise 4 — N+1 queries

A single request creates 40 short database spans. What should you inspect?

**Answer:** N+1 queries, lazy loading, fetch strategies, ORM flushing, and repository loops. The trace waterfall shows call counts and relationships; database metrics add server load visibility.

### Exercise 5 — Pool exhaustion

Pending threads increase, active connections hit max, and JDBC spans have long durations. Should you only increase max pool size?

**Answer:** No. Inspect query/transaction durations, connection leaks, DB capacity, and replica counts. Increasing the pool can overload the database further.

### Exercise 6 — SQL exception without error status

The application catches `SQLException` and returns a business error response. The trace span has no error status. Does this necessarily mean instrumentation is broken?

**Answer:** No. A handled exception may not automatically mark the span as errored under conventions. Record errors intentionally in the observation/span context using the appropriate API/version.

## 19. Implementation checklist

- [ ] Confirm the application accesses the database via JDBC.
- [ ] Spring Boot, Micrometer Tracing bridge, and instrumentation versions are compatible.
- [ ] Exactly one tracer bridge is present with no duplicate Java agent instrumentation.
- [ ] DataSource/connection pool is properly managed and instrumented.
- [ ] Database spans appear in the current trace.
- [ ] HTTP/server spans and JDBC spans have a sensible parent-child relationship.
- [ ] Operation, duration, and error status are verified on real payloads.
- [ ] Pool metrics active/idle/pending/max are monitored.
- [ ] SQL text, bind values, credentials, and connection strings are protected.
- [ ] Full SQL or tenant IDs are not used as metric tags.
- [ ] Sampling is chosen based on volume/cost and investigation needs.
- [ ] Dashboards correlate traces, pool metrics, and database server metrics.
- [ ] Integration tests use an appropriate database and driver.
- [ ] Tests cover success, SQL exceptions, transactions, and context propagation.
- [ ] R2DBC/native clients are identified and use separate instrumentation.
- [ ] Runbooks include checks for exporter, Collector, and backend drops.

**Key takeaway:** The JDBC observation starter provides visibility into database calls going through JDBC, but it does not replace connection pool metrics or internal database monitoring. Choose dependencies matching your Spring Boot/tracer version, maintain one consistent tracing pipeline, verify database spans sit inside HTTP traces, and protect SQL attributes from literals and PII. Combine spans, pool metrics, and database server metrics to distinguish slow queries, connection waits, and database overload.
