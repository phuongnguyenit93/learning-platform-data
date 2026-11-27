# Database error metrics

A Spring Boot API may return 500 when a database connection is refused, 503 when the connection pool is exhausted, or 409 when business logic detects conflicting data. If a dashboard only shows a single `database.errors` counter, operations teams struggle to tell whether failures stem from connectivity, query timeouts, transactions, or business constraints. Database error metrics need enough classification to guide investigation, while keeping dimensions stable so metrics aggregate and alert reliably.

This **Database error metrics** lesson belongs to the **Database observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in real environments.

> **Principle:** Metrics answer how often DB errors happen, on which operations, and in which category. Logs/traces provide details of an individual failure. Never use exception messages, SQL text, parameters, dynamic schemas/tables, user IDs, or connection strings as metric tags. Distinguish real DB failures from business rejections mapped to HTTP 4xx; both can fail a request but carry very different operational meaning.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain database error metrics and their role in observability.
2. Distinguish connectivity, pool exhaustion, query timeout, transaction, constraint, and business errors.
3. Recognize exceptions from JDBC, Spring Data/JPA, and R2DBC.
4. Use SQLState classes and vendor error codes to classify errors.
5. Design Counters/Timers for database operations and failures.
6. Choose low-cardinality dimensions such as `db.system`, `operation`, `error.type`, and `outcome`.
7. Avoid SQL text, exception messages, parameters, and dynamic IDs in metric tags.
8. Combine metrics with Observation, traces, and structured logs.
9. Design alerts around error rate, latency, pool saturation, and dependency availability.
10. Test error recording without leaking sensitive data or double-counting.

## 2. What are database error metrics?

Database error metrics are aggregated measurements of failures occurring when an application interacts with a database. They can be produced by JDBC operations and Spring JDBC exception translation, JPA/Hibernate repository operations, R2DBC reactive database operations, the connection pool, the transaction manager, and custom instrumentation.

Operational questions:
- What is the ratio of failed queries to total queries?
- On which database system or operation are errors concentrated?
- Are connection timeouts rising alongside pool pending counts?
- Which deployment preceded a surge in query timeouts?
- Are constraint errors invalid user input or a sign of regression?
- Is the DB dependency driving up API latency and error rates?

Metrics are aggregated signals. They do not replace logs/traces containing sanitized SQL operations, exception classes, and request context.

## 3. Classifying database failures

| Category | Examples | Operational impact |
|---|---|---|
| Connection acquisition | Pool exhausted, acquisition timeout | Unable to acquire a connection |
| Connection establishment | Connection refused, network unreachable | Unable to connect to the database |
| Authentication/authorization | Invalid credentials, permission denied | Misconfiguration or broken permissions |
| Query timeout/cancel | Statement timeout, query canceled | Query exceeded deadline or was canceled |
| Transaction | Deadlock, serialization failure, rollback | Transaction failed to complete |
| Constraint/data integrity | Unique violation, foreign key violation | Data violated constraints |
| Resource exhaustion | Too many connections, disk full | Database/infrastructure out of resources |
| Protocol/driver | Connection reset, protocol error | Driver/network/server issue |
| Business rejection | Order exists, insufficient balance | Business outcome, not necessarily a DB failure |

Business rejections may even be detected before sending SQL. A unique constraint violation might represent a business conflict, yet its origin and API semantics still need distinction. Do not label every 409/400 as a database failure.

### 3.1 Connectivity and pool errors

A pool acquisition timeout usually means the application could not borrow a connection within the allowed wait time. Causes include all connections being busy, queries/transactions holding connections too long, connection leaks, pool size too small for concurrency, or a slow database.

Connection refused, DNS failures, or network timeouts occur during connection establishment; they differ from pool acquisition timeouts. Separate metrics are needed if you want to pinpoint which infrastructure layer is failing.

### 3.2 Query and transaction errors

Query timeouts can stem from execution plans, lock contention, database overload, or overly aggressive timeout settings. Deadlocks/serialization failures usually require reviewing transaction isolation, access ordering, and retry policies. Constraint violations may indicate invalid input or race conditions.

Do not parse exception messages with ad-hoc regexes to infer a taxonomy. Prefer exception types, SQLState, and vendor codes for known databases/drivers.

## 4. Exception translation and SQLState

Spring JDBC translates `SQLException` into the `DataAccessException` hierarchy, such as `DataIntegrityViolationException`, `DuplicateKeyException`, `QueryTimeoutException`, `TransientDataAccessResourceException`, and `CannotGetJdbcConnectionException`. JPA/Hibernate may wrap driver errors in `PersistenceException`, `HibernateException`, or Spring's `DataAccessException`. R2DBC uses its own exception types and driver mappings. Always inspect the cause chain rather than only the outermost exception.

### 4.1 SQLState classes

SQLState is a standard classification code for SQL errors. Common classes include:

| SQLState class | General meaning | Suggested metric category |
|---|---|---|
| 08 | Connection exception | `connection` |
| 22 | Data exception | `data` |
| 23 | Integrity constraint violation | `constraint` |
| 25 | Invalid transaction state | `transaction` |
| 40 | Transaction rollback, including serialization/deadlock by subcode | `transaction` |
| 42 | Syntax/access rule violation | `query_or_permission` |
| 53 | Insufficient resources | `resource` |
| 57 | Operator intervention/system error | `database_unavailable_or_cancelled` |
| 28 | Invalid authorization specification | `authentication` |

This is a general classification; exact meanings of SQLState subcodes and vendor codes depend on the database. Do not lump all class 42 errors under syntax bugs if the database uses subcodes for access permissions.

### 4.2 Vendor error codes

Some databases expose vendor codes that distinguish deadlocks, duplicate keys, or connection failures. Mappings should live in an adapter scoped to your database/driver version, tested, and versioned. Never emit raw vendor messages or arbitrary codes as tags if the value space is unbounded.

If SQLState/vendor codes are unrecognized, assign a bounded `unknown` group instead of creating tags from free-form strings.

## 5. Designing metric dimensions

Metric dimensions must be stable and low-cardinality:

| Dimension | Appropriate values | Avoid |
|---|---|---|
| `db.system` | `postgresql`, `mysql`, `oracle` | Full JDBC URL |
| `db.operation.name` | `SELECT`, `INSERT`, `UPDATE`, `DELETE` | Verbatim SQL |
| `error.type` | `timeout`, `connection`, `constraint`, `transaction`, `unknown` | Exception message |
| `outcome` | `success`, `error` | Free-form response content |
| `pool.name` | `primary`, `reporting` | Pool names containing dynamic tenant/customer |
| `service.name` | `order-service` | Instance/request ID |
| `environment` | `production`, `staging` | Request-supplied values |

Never add SQL query text/bind parameters, database passwords/connection strings, user ID/order ID/email/account numbers, raw exception messages/stack traces, dynamic table names, or trace ID/request ID as metric labels.

When investigating specific queries, use trace spans or scrubbed log records with strict access control and retention.

## 6. Choosing metrics: counters, timers, and pool gauges

| Metric | Type | Meaning |
|---|---|---|
| `db.client.operations` | Counter | Completed operations |
| `db.client.errors` | Counter | Failed operations |
| `db.client.operation.duration` | Timer/Histogram | Operation latency |
| `db.client.timeouts` | Counter | Timeout count |
| `db.pool.active` | Gauge | Connections currently in use |
| `db.pool.idle` | Gauge | Idle connections |
| `db.pool.pending` | Gauge | Requests waiting for a connection |
| `db.pool.max` | Gauge | Pool maximum limit |
| `db.pool.acquire.duration` | Timer | Time to acquire a connection if provided by instrumentation |

Exact metric names depend on Micrometer binders, Spring Boot version, JDBC/R2DBC instrumentation, and semantic conventions. Do not create custom meters that duplicate meters already provided automatically by the registry.

### 6.1 Error count and error rate

A counter only increments when an operation fails. To compute error rate, you need total operations as the denominator:

~~~text
error_rate = failed_operations / total_operations
~~~

Looking solely at error count can mislead when traffic surges without changing the failure rate. Dashboards should show both rates and absolute counts.

### 6.2 Timers and failures

Timers can record both successful and failed operations so latency distributions reflect all attempts. Recording only successful calls can make dashboards look artificially healthy while slow requests time out and drop out of the distribution.

Timers can be segmented by `outcome` when instrumentation supports bounded tags. Ensure you never register a new timer per exception message.

### 6.3 Pool gauges

Pool metrics help distinguish a slow database from an under-provisioned pool:
- Active near max and pending rising: the application is waiting for connections.
- Low active yet rising connect errors: likely network/auth/database unavailability.
- Sustained high active and rising query duration: queries/transactions may be holding connections too long.
- Idle equals 0 during peak: the pool may be saturated.

Do not simply raise pool size; databases also have connection limits, and increasing concurrency can overload the database further.

## 7. Micrometer Observation for database operations

Micrometer Observation measures operations through a unified abstraction. With appropriate handlers, observations can generate both metrics and tracing spans. Spring/JDBC/Hibernate/R2DBC instrumentation may provide observations automatically depending on your stack and dependencies.

Example custom repository operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
class InventoryRepositoryMetrics {

    private final ObservationRegistry observationRegistry;

    InventoryRepositoryMetrics(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    Inventory load(String sku) {
        return Observation.createNotStarted(
                        "inventory.repository.load",
                        observationRegistry)
                .lowCardinalityKeyValue("db.operation.name", "SELECT")
                .observe(() -> performQuery(sku));
    }

    private Inventory performQuery(String sku) {
        // Invoke actual repository/JDBC call.
        return null;
    }
}
~~~

This illustrates a custom operation; in real code, avoid wrapping queries already instrumented automatically if doing so creates duplicate metrics/traces. When adding custom business observations, choose distinct names describing the logical operation clearly.

### 7.1 Recording errors in Observation

Observation captures exceptions thrown out of its callback; error/tracing handlers can convert that into span events/status or metric tags per conventions. If an exception is caught and converted into a normal return value inside the callback, handlers may not recognize that the operation failed.

~~~java
return Observation.createNotStarted("inventory.repository.load", observationRegistry)
        .lowCardinalityKeyValue("db.operation.name", "SELECT")
        .observe(() -> repository.findBySku(sku)
                .orElseThrow(() -> new InventoryNotFoundException(sku)));
~~~

If not-found is a normal business outcome, do not necessarily count it as a database error. Distinguish a query that succeeded with zero rows from a failed database query.

## 8. Safe custom error counter example

If the application needs a custom metric, classify exceptions into a bounded `error.type` set:

~~~java
enum DbErrorType {
    CONNECTION,
    TIMEOUT,
    CONSTRAINT,
    TRANSACTION,
    PERMISSION,
    UNKNOWN
}
~~~

The classifier should walk the cause chain/SQLState using tested mappings:

~~~java
DbErrorType classify(DataAccessException ex) {
    if (hasSqlStateClass(ex, "08")) {
        return DbErrorType.CONNECTION;
    }
    if (hasSqlStateClass(ex, "23")) {
        return DbErrorType.CONSTRAINT;
    }
    if (hasSqlStateClass(ex, "40")) {
        return DbErrorType.TRANSACTION;
    }
    if (isQueryTimeout(ex)) {
        return DbErrorType.TIMEOUT;
    }
    if (isPermissionFailure(ex)) {
        return DbErrorType.PERMISSION;
    }
    return DbErrorType.UNKNOWN;
}
~~~

Helper methods here are pseudocode because extracting `SQLException`, SQLState, and vendor codes depends on the exception hierarchy and driver. Do not copy as a complete implementation without inspecting your application's cause chains and exception wrappers.

After classifying, increment the `Counter`:

~~~java
Counter.builder("app.database.errors")
        .tag("db.system", "postgresql")
        .tag("operation", "SELECT")
        .tag("error.type", errorType.name().toLowerCase(Locale.ROOT))
        .register(meterRegistry)
        .increment();
~~~

Never use request-supplied database/table names. Use normalized `db.system` and `operation`; if there are multiple logical databases, assign fixed aliases like `primary` or `reporting`.

### 8.1 Counting errors exactly once

If driver instrumentation, Spring exception translation, and a custom catch block all increment error counters for the same failure, metrics will double-count. Choose one layer to own error counting:
- Standard instrumentation for database client operations.
- Custom metrics only for unmeasured business-level failures.
- Never increment in a repository catch block and increment again in the service/controller for the same operation.

## 9. JDBC, JPA, and R2DBC

### 9.1 JDBC/Spring JDBC

Spring JDBC provides exception translation so applications handle `DataAccessException` rather than coupling directly to driver exceptions. Keep the cause for deeper log/trace investigation, but never put sensitive messages into metric tags.

JDBC instrumentation can measure query execution, connection usage, and errors depending on integration. Check dependencies/versions and avoid adding redundant custom Timers.

### 9.2 JPA/Hibernate

A repository call may not execute SQL immediately; Hibernate can defer flushing until transaction end. Constraint violations can surface at flush/commit rather than on the `save()` line. When measuring, understand transaction boundaries and when the database actually receives statements.

A repository method returning before commit does not prove the transaction committed cleanly. If a business metric must reflect commit outcomes, instrument transaction completion or the appropriate boundary.

### 9.3 R2DBC

R2DBC is reactive and errors can arise asynchronously within publisher subscriptions. Do not measure by wrapping `Mono`/`Flux` creation in a `Timer`; instrument from subscribe to terminal signal (`complete`/`error`/`cancel`) or use built-in Observation integration.

Reactive cancellation is not necessarily a database error. Distinguish client disconnects/deadlines from database query failures.

## 10. Transactions, rollbacks, and business errors

A transaction can fail due to deadlocks, serialization conflicts, constraint violations, or connectivity errors. Metrics should reflect operation/transaction outcomes without counting the same error across statement, transaction manager, and business service.

Distinguish:
- Query failed and transaction rolled back.
- Query succeeded but transaction commit failed.
- Transaction rolled back intentionally by business rules.
- Business validation failed before any SQL ran.
- Optimistic locking conflict from concurrent data modification.

A rollback can be an expected outcome. You can emit a separate `transaction.outcome=rollback` metric and use `error.type` to distinguish technical failures from business cancellations.

## 11. Correlating metrics with traces and logs

Metrics reveal rising error rates or latency. Traces show which request contained the DB operation and how long it took. Logs provide the exception class, scrubbed SQLState, and necessary context.

~~~mermaid
flowchart LR
    A["Database error metrics"] --> B["Detect rising error rate"]
    B --> C["Trace of affected request"]
    C --> D["DB client span"]
    D --> E["Structured log"]
    E --> F["Exception type / SQLState / safe context"]
    F --> G["Investigate pool, query, lock, or database"]
~~~

Logs can include `service.name`, `environment`, operation name/repository method, exception class, normalized SQLState class, database alias, `traceId`/`spanId`, and elapsed time.

Never log SQL bind values, credentials, raw customer data, or unscrubbed exception messages.

## 12. Alerting on error metrics

Good alerts combine error rate, latency, and saturation:

| Alert | Suggested condition | Meaning |
|---|---|---|
| DB operation error rate | Error ratio exceeds threshold over consecutive windows | Real DB error impact |
| DB connection errors | Connection failures spike | Network/auth/DB availability |
| Query timeout rate | Timeout counter/rate exceeds baseline | Query or DB latency |
| Pool saturation | Active near max and pending rising | Application lacks connection capacity |
| Transaction rollbacks | Technical rollbacks rise above baseline | Deadlocks/serialization/commit failures |
| DB latency SLO | p95/p99 exceeds budget | Slow queries/dependency |

Do not alert on raw error counts when traffic fluctuates sharply. Use ratios, minimum request volume thresholds, sustained duration windows, and route/business impact. Separate expected constraint/business conflicts from availability alerts.

### 12.1 Conceptual PromQL example

~~~promql
sum(rate(app_database_errors_total[5m]))
/
clamp_min(sum(rate(app_database_operations_total[5m])), 1)
~~~

Illustrative query; actual metric names may be normalized by the Prometheus registry and require matching labels. In production, group by `db.system` and `error.type` once cardinality is controlled.

## 13. Cardinality and sensitive data

A metric with tags `db.system`, `operation`, `error.type`, and `outcome` has a small series count. Adding SQL statements, exception messages, tenant IDs, or user IDs causes unbounded series growth.

~~~text
Safe:
db.system=postgresql
operation=SELECT
error.type=timeout
outcome=error

Unsafe:
sql="select * from orders where customer_id=..."
exception.message="password authentication failed for user ..."
customer.id=customer-83921
jdbc.url=jdbc:postgresql://db.internal/orders?password=...
~~~

Hashing SQL or user IDs does not automatically solve cardinality and privacy either. Hashing queries with literal values still generates a distinct series per request. Use normalized query fingerprints when supported by instrumentation/backends and permitted by policy; never emit dynamic hashes as metric labels.

## 14. Testing database error metrics

Use a test database instance/container or mock at the right boundary. Tests should verify the classifier, counters, and Observation behavior.

Scenarios:
1. Successful query: operation counter increments, error counter does not.
2. Query timeout: `error.type=timeout`.
3. Connection unavailable: `error.type=connection`.
4. Unique constraint violation: `error.type=constraint`.
5. Deadlock/serialization failure: `error.type=transaction`.
6. Business not-found without SQL error: does not increment database error counter.
7. R2DBC cancellation: distinguished from DB failure.
8. Exception containing a synthetic secret: metric labels contain no message/SQL/credentials.

Test classifiers using known SQLState fixtures for your database/driver; do not assume all databases map vendor codes identically.

### 14.1 Counter verification example

~~~java
@Test
void incrementsDatabaseErrorCounterForTimeout() {
    meterRegistry.clear();

    service.executeQueryThatTimesOut();

    Counter counter = meterRegistry.find("app.database.errors")
            .tag("db.system", "postgresql")
            .tag("operation", "SELECT")
            .tag("error.type", "timeout")
            .counter();

    assertThat(counter).isNotNull();
    assertThat(counter.count()).isEqualTo(1.0);
}
~~~

This is an illustrative test; real tests require appropriate DB/driver fixtures or classifier mocks. Ensure the test does not accidentally create extra meters with different tag sets under the same name.

## 15. Troubleshooting

| Symptom | Possible cause | Remediation |
|---|---|---|
| DB error counter rises while API returns 2xx | Background task/retry failure or handled fallback | Correlate by service/operation/trace |
| API 4xx rises while DB errors stay flat | Business validation or not-found | Do not force into DB errors |
| Pool timeouts rise, connection errors low | Unable to borrow connection from pool | Check active/idle/pending, leaks, and transaction duration |
| Connection errors rise | DNS/network/auth/database availability | Inspect SQLState class 08 and infrastructure |
| Query timeouts rise | Slow queries, locks, DB saturation, or low timeout | Inspect DB spans, query plans, and lock metrics |
| Constraint errors spike after deploy | Schema/data migration or write behavior change | Check unique/FK constraints and rollout |
| Error counter double-counts | Multiple layers instrumenting the same failure | Pick one owner for database error counting |
| JPA `save` succeeds yet transaction rolls back | SQL flush/commit occurs after method return | Observe transaction completion |
| R2DBC records no duration | Timer stops at publisher creation instead of terminal signal | Instrument subscription/terminal signal |
| Metric cardinality spikes | Dynamic SQL/message/ID used as tags | Normalize to bounded dimensions |
| Cannot classify exception | Driver wraps exception or SQLState not extracted from cause | Walk cause chain and add tested mapping |
| Error logs lack trace ID | Context propagation/log correlation unconfigured | Check tracing bridge and MDC integration |

## 16. Playbook: database error rate spikes after deployment

**Scenario:** After releasing Order Service, the database error rate jumps from a low baseline to elevated levels.

1. Filter metrics by `service`, `db.system`, `operation`, and `error.type`.
2. Identify which error group rose: `connection`, `timeout`, `constraint`, or `transaction`.
3. Compare error rate against total operation rate to rule out a pure traffic spike.
4. Inspect pool active/idle/pending and connection acquisition timeouts.
5. Open traces of affected requests and check DB span durations and parent operations.
6. Read scrubbed logs for exception classes, SQLState classes, and database aliases.
7. Compare versions/deployments before and after release; check schema migrations, queries, or transaction changes.
8. If deadlocks/serialization conflicts rose, review transaction access ordering/isolation and retry policies.
9. If timeouts rose, inspect query latency, lock waits, pool health, and DB resource saturation.
10. Confirm after fixing: error ratio, latency, and pool pending return to baseline with no duplicate counting.

Do not just raise pool size or timeouts to mask symptoms. Identify whether the failure lies in the pool, network, query, transaction, or data integrity before changing configuration.

## 17. Self-check exercises

**Exercise 1 — Error classification.** A query hits a unique constraint violation. Which `error.type` should it map to? When is this a business conflict rather than a database availability failure?

**Exercise 2 — SQLState.** What error groups do SQLState classes `08` and `23` typically represent? Why inspect subcodes/vendor codes?

**Exercise 3 — Metric dimensions.** Why should you avoid using exception messages or SQL statements as tags on `app.database.errors`?

**Exercise 4 — Error rate.** Why does a rising error count not automatically mean reduced reliability? Which denominator is needed?

**Exercise 5 — Pool saturation.** Active connections equal max and pending is rising, yet connect timeouts are not rising. Which stage do you suspect?

**Exercise 6 — JPA commit.** Repository `save` returns successfully, yet the transaction fails to commit. Why can a metric wrapping only `save` miss this error?

**Exercise 7 — R2DBC.** Why should you not stop a `Timer` immediately after creating a `Mono`? Which terminal signals should be considered?

**Exercise 8 — Double counting.** Driver instrumentation, repository catch block, and service catch block all increment counters. Propose how to choose an instrumentation owner.

### Suggested answers

1. `constraint`. If the client sent conflicting data and the API contract treats it as 409, it is a business conflict; if it spikes unexpectedly, investigate races/schema changes.
2. `08` is connection exception; `23` is integrity constraint violation. Subcodes/vendor codes pinpoint the specific condition per database.
3. They have very high variability and can contain PII/secrets; metric labels must stay bounded.
4. Traffic may have increased; use total database operations as the denominator to compute a ratio.
5. Pool acquisition/waiting; inspect pending, active, idle, leaks, and transaction duration.
6. JPA may flush/commit after the method returns; measure at the transaction completion boundary.
7. Publishers have not executed when `Mono` is created. Measure from subscribe to `complete`/`error`/`cancel` and classify cancellation separately.
8. Let standard instrumentation measure DB operations; reserve custom counters for unmeasured business events, avoiding incrementing the same failure across multiple layers.

## 18. Official references

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics, data source/pool metrics, and customization.
- [Spring Framework — Data Access](https://docs.spring.io/spring-framework/reference/data-access.html): exception translation and data access abstractions.
- [Spring JDBC — Data Access Exceptions](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JDBC support and exception translation.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, handlers, and conventions.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP): pool metrics, active/idle/pending connections, and configuration.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLState classes and error codes.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): database activity and monitoring views.
- [OpenTelemetry Semantic Conventions — Database](https://opentelemetry.io/docs/specs/semconv/db/): database operation attributes and telemetry conventions.
- [R2DBC SPI](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/): reactive database API and error signals.

**Key takeaway:** Database error metrics must distinguish connection/pool, query, transaction, constraint, and business outcomes. Use tested SQLState/exception classification to keep `error.type` bounded; pair error counters with total operations, latency, and pool gauges. Observation connects metrics to DB spans, logs, and trace context. Never place SQL, exception messages, bind values, or dynamic IDs in metric tags. When errors rise, pinpoint the exact stage and layer before changing pool sizes, timeouts, or retry policies.
