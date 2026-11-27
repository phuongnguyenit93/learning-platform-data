# Connectivity Checks, Error Observability, and Recovery from Database Incidents

## 1. Objectives and Scope

Spring Data JPA typically accesses a database through a chain of components: service → repository/EntityManager → Hibernate → JDBC driver → connection pool → DBMS. When the database loses connectivity or responds slowly, errors can surface at any point along this chain.

A well-operated system must accomplish four things:

1. **Check connectivity** to verify whether the application can acquire a connection and whether the database responds.
2. **Observe health** through health checks, metrics, logs, and traces to catch failures before users report them.
3. **Classify incidents** to distinguish database outages, pool exhaustion, network failures, slow queries, locks, or misconfiguration.
4. **Recover safely** by shedding/limiting load, restoring connectivity, applying bounded retries, and verifying data consistency.

No single health check guarantees the next request will succeed. A health check result reflects only the state at the moment of inspection; a connection can break immediately afterward. Therefore, combine lightweight checks with metrics, logs, and per-operation exception handling.

## 2. Checking Connectivity from the Application

### 2.1 Checking DataSource and JDBC connections

The most direct approach is borrowing a connection from the DataSource and calling JDBC `isValid()`:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public class DatabaseConnectionProbe {

    private final DataSource dataSource;

    public DatabaseConnectionProbe(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean isDatabaseReachable() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2);
        }
    }
}
```

`isValid(2)` asks the driver to validate the connection within a maximum timeout of roughly 2 seconds per the JDBC contract. Exact behavior and implementation depend on the driver. `getConnection()` may also block waiting on the pool; if the pool is exhausted, an error can occur before `isValid()` is even called.

Never open raw connections via `DriverManager` inside business code to probe the database. Check the actual DataSource Spring uses so the probe reflects the application's real configuration, credentials, pool, and driver.

If you need to inspect the DBMS and version, read metadata:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    String product = metadata.getDatabaseProductName();
    String version = metadata.getDatabaseProductVersion();

    log.info("Connected database: product={}, version={}", product, version);
}
```

Never log URLs that could contain credentials or sensitive internal details. Product and version are useful metadata for comparing test and production environments.

### 2.2 Distinguishing timeout types

Timeouts serve different purposes and should not be used interchangeably:

| Timeout | What It Limits | Configuration Example |
|---|---|---|
| Pool connection timeout | Time waiting to acquire a connection from the pool | Hikari `connectionTimeout` |
| Connection validation timeout | Time allowed to validate a connection | Hikari `validationTimeout` |
| Socket/network timeout | Time waiting on network I/O from the database | JDBC driver or network |
| Query timeout | SQL statement execution time | JPA query hint/JDBC |
| Transaction timeout | Maximum transaction duration per transaction manager/provider | `@Transactional(timeout = ...)` |
| Lock timeout | Time waiting for a database lock | DBMS or query/transaction setting |

For example, an expired Hikari `connectionTimeout` usually means the application could not borrow a connection from the pool within the configured limit. It does not prove the database server is down. The pool can run out of connections due to slow queries, long-lived transactions holding connections, or concurrency exceeding capacity.

Conversely, a query timeout happens after a connection has already been acquired and SQL has been sent. When diagnosing, identify which stage timed out.

### 2.3 Intentional HikariCP configuration

Spring Boot typically uses HikariCP when the matching dependency is present. An example configuration:

```yaml
spring:
  datasource:
    hikari:
      pool-name: application-db-pool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1740000
      keepalive-time: 120000
```

Duration values in this Hikari example are in milliseconds. These are illustrative numbers, not universal defaults for every system. Tune them based on database connection limits, application instance count, concurrency, query durations, and proxy/load balancer timeouts:

- `maximum-pool-size`: caps concurrent connections per instance. Total connections across all instances, jobs, and admin tools must fit within the DBMS budget.
- `minimum-idle`: number of idle connections the pool attempts to keep ready.
- `connection-timeout`: wait time for a connection from the pool; must align with request latency and SLAs.
- `validation-timeout`: maximum time to validate a connection; must be smaller than `connection-timeout`.
- `max-lifetime`: maximum lifetime of a connection in the pool. Set comfortably below database/proxy/network connection age limits so the pool proactively replaces connections.
- `keepalive-time`: interval to test/keep alive idle connections; must be smaller than `max-lifetime` and applies only while connections are idle.

With JDBC 4 drivers supporting `Connection.isValid()`, Hikari generally does not need `connectionTestQuery`. Use a test query only for older drivers lacking JDBC 4 support or for a specific reason confirmed in driver documentation.

Never increase `maximum-pool-size` merely because requests wait for connections. A larger pool can overload the database and worsen lock contention. First inspect slow queries, long transactions, connection leaks, concurrency, and DBMS connection limits.

## 3. Health Checks with Spring Boot Actuator

Spring Boot Actuator provides health endpoints and health indicators. When a DataSource exists, the database health indicator (typically `DataSourceHealthIndicator`) checks database reachability via the DataSource.

Add the Actuator dependency matching your Spring Boot version, then enable health probes:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
      show-details: never
```

Common endpoints in orchestrated environments:

- `/actuator/health`: overall health summary.
- `/actuator/health/liveness`: whether the application is alive and can keep running.
- `/actuator/health/readiness`: whether the application is ready to accept traffic.

**Liveness and readiness serve different purposes:**

- Liveness should reflect whether the application is deadlocked or in an unrecoverable state. Do not blindly include the database in liveness. If the DB pauses briefly and liveness goes DOWN too, Kubernetes may restart pods en masse, adding extra load on the database just as it recovers.
- Readiness can include the database if the application cannot serve primary requests when the DB is unreachable. When readiness is DOWN, the orchestrator stops routing new traffic to that instance while keeping the process alive to recover.

Including `db` in readiness is an architectural choice. An application might still serve read-only cached endpoints or status pages during a DB outage; in that case, identify which endpoint groups genuinely depend on the database. Default health groups and configuration syntax can vary across Spring Boot versions; verify against your project version.

Health checks must not run heavy queries or run excessively often. They consume pool connections and can themselves contribute to pool exhaustion. Configure reasonable timeouts, protect endpoints via network policies/authentication, and never expose internal details such as hostnames, schemas, or exceptions to external callers.

### 3.1 Readiness is not a guarantee of transaction success

A single `/actuator/health/readiness` returning UP proves only that the indicator check succeeded at that instant. The very next request can still encounter a failover, network reset, pool timeout, or deadlock.

Therefore:

- Use health checks to gate traffic routing.
- Use metrics to track trends and spot bottlenecks.
- Use logs/traces to pinpoint where a specific request failed.
- Use exception handling and transaction boundaries to handle requests already inside the application.

## 4. Observing Connection Pools and Databases

### 4.1 Key metrics

When using Actuator/Micrometer and HikariCP, monitor pool metrics typically prefixed with `hikaricp.connections`:

| Metric | Meaning | Warning Sign |
|---|---|---|
| `hikaricp.connections.active` | Connections currently in use | Climbing steadily without dropping |
| `hikaricp.connections.idle` | Idle connections | Staying at 0 under load may indicate pool undersizing |
| `hikaricp.connections.pending` | Threads waiting for a connection | Sustained elevation signals a bottleneck |
| `hikaricp.connections.max` | Pool connection limit | Compare against active/pending |
| `hikaricp.connections.min` | Configured minimum idle level | Compare against actual load |

Exact metric names and export formats depend on Boot/Micrometer versions. Inspect available metrics via `/actuator/metrics` or your Prometheus scrape endpoint.

Patterns to analyze:

- **Active hits max, pending rises**: pool is saturated. Look for slow queries, transactions holding connections, connection leaks, or traffic spikes.
- **Sustained high active, rising query latency**: database may be slowing down, heavily locked, or resource-constrained.
- **Idle at 0 while pending stays low**: pool is operating near capacity without yet causing significant queuing.
- **Active drops while pending keeps rising**: check whether the pool cannot open new connections, the database hit connection limits, or the network failed.
- **Pool timeouts rising alongside DB latency**: likely a shared symptom of a database or query issue rather than too small a pool size.

Also monitor DBMS connection counts, active/idle sessions, slow queries, lock waits, deadlocks, CPU, memory, disk I/O, transaction age, replication lag, and failover events. Application metrics alone cannot explain what the database is experiencing.

### 4.2 Query latency and transaction duration

Measure at least:

- Connection acquisition time.
- Query execution time.
- Transaction duration from begin to commit/rollback.
- Rows read/written where safely measurable.
- Error rates broken down by exception type and SQLState.
- Retry counts and total retry wait time.

Long-running transactions hold connections and locks longer than necessary. Never call external APIs, send emails, or wait on user input inside a long database transaction when those actions can be separated from the transaction.

For multi-step writes, place transaction boundaries at the service layer around the work requiring atomicity. Ensure transactions finish promptly once database work completes.

## 5. Logs and Traces for Failure Observability

### 5.1 Log sufficient context without leaking data

A useful incident log should include:

- Clear timestamp and timezone.
- Correlation ID/trace ID to tie together logs from one request.
- Operation/service name and relevant repository or use case.
- DBMS, pool name, and instance/pod if needed.
- Exception type, root cause, SQLState, and vendor error code.
- Connection acquisition, query, or transaction duration if available.
- Retry attempts and final outcome.

Never log passwords, access tokens, connection strings with credentials, payment data, PII, or raw bind parameters indiscriminately. If query identification is needed, prefer query names or sanitized SQL fingerprints stripped of sensitive values.

Never log only `exception.getMessage()` while discarding the stack trace and cause chain. Retain the root cause in access-controlled internal logs. Never return stack traces, internal SQL, or database hostnames to clients.

### 5.2 Enabling SQL logs in appropriate environments

In development/test environments, you can enable:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.springframework.orm.jpa: DEBUG
    org.springframework.transaction: DEBUG
```

Bind parameter logger names vary across Hibernate versions. TRACE can expose real data and generate huge log volumes; do not enable it broadly in production without data masking and log access controls. Enable only briefly, on a single instance or controlled subset of requests while investigating.

### 5.3 Tracing across layers

Distributed tracing connects requests from HTTP controllers through services, JDBC, and the database when supported by instrumentation. When analyzing traces:

- Find the span with the longest latency.
- Separate connection wait time from query execution time.
- Check whether the request retried multiple times.
- Correlate trace IDs with application logs and database logs.
- Check for repeated queries (N+1) or transactions held open too long.

Traces do not always include full SQL; avoid capturing raw SQL and sensitive parameters unless necessary.

## 6. Classifying Connectivity and Database Incidents

| Symptom | Cause Category | First Checks |
|---|---|---|
| Connection refused | Database not listening, wrong host/port, service down | DB status, DNS, network, endpoint |
| Connection timed out | Firewall, network partition, routing, or overloaded DB | Network path, latency, server load |
| Authentication failed | Wrong credentials/secret, locked or expired user | Secret version, account status, grants |
| Pool connection timeout | Failed to borrow connection within wait time | Active/idle/pending, query duration, leaks |
| Connection is closed/broken | Connection closed by DB/proxy, failover, or network reset | DB events, pool lifecycle, driver logs |
| Query timeout | Long query, lock wait, or slow server | Execution plan, wait events, indexes, locks |
| Deadlock | Transactions locking resources in conflicting orders | DB deadlock report, transaction flow |
| Too many connections | Total connections exceed DBMS limit | Sum of pools across instances, jobs, and clients |
| SQL syntax/object missing | Broken migration, schema, or query | DDL, migration history, DB version |
| Data integrity violation | Invalid data or constraint breach | Constraint name, input, and related data |

Distinguish transient errors from configuration errors:

- Network resets, failovers, server restarts, deadlocks, or serialization conflicts may be transient depending on the DBMS and operation.
- Wrong passwords, missing privileges, missing tables/columns, SQL syntax errors, and mapping mismatches will generally not resolve on retry.
- Pool exhaustion may be a downstream effect of slow queries or connection leaks; retrying more requests can make matters worse.

Never lump every SQLException under "database down." Use SQLState, vendor codes, health indicators, and DB monitoring to pinpoint the cause.

## 7. Responding When the Database Is Temporarily Unreachable

A practical incident response workflow:

1. **Detect**: alert when readiness goes DOWN, connection timeouts rise, error rates spike, or pool pending remains elevated.
2. **Isolate**: determine whether one instance or the whole system is affected; inspect DNS/network, DB endpoints, credentials, DB processes, and failover events.
3. **Shed load**: stop accepting DB-dependent requests via readiness, apply rate limiting/backpressure, and avoid unbounded request queues.
4. **Protect data**: let failing transactions roll back along their boundaries; never return success when commit outcome is unknown.
5. **Restore service**: wait for DB readiness, verify primary endpoint/role, privileges, schema, and fresh connectivity.
6. **Verify application**: confirm the pool can open new connections, health indicators stabilize, and verification reads/writes succeed.
7. **Re-admit traffic**: bring instances back to readiness UP once dependencies qualify; monitor error rates, latency, and backlogs.
8. **Reconcile**: handle requests with uncertain outcomes, check for duplicate/missing data, and run reconciliation if needed.

If the database fails over to a different node/endpoint, ensure the JDBC URL, DNS, driver, and connection topology fit. Some drivers support failover/cluster URLs; configuration varies by vendor. Never assume all open connections automatically migrate to the new primary.

## 8. Recovering the Connection Pool After an Outage

HikariCP manages connection lifecycles. When a connection is detected as broken or invalid, the pool can evict that connection and open new connections once the database recovers and accepts connections. Requests actively using a connection when a network failure hits may still throw exceptions; those requests are not automatically turned into successes just because the database comes back online.

How to handle it:

- Verify the database accepts new connections at the right endpoint.
- Monitor active/idle/pending metrics and connection creation failures.
- Let the pool replace broken connections through its built-in lifecycle management.
- Do not restart the entire application or manually construct a new DataSource merely because a few connections failed.
- Only consider manual pool management actions when there is evidence the pool is not self-recovering and impact on live requests has been evaluated.
- If credentials/secrets changed, verify the datasource/pool refresh mechanism; never assume a running pool automatically re-reads rotated secrets.

`maxLifetime` and `keepaliveTime` reduce the chance that idle connections are silently dropped by infrastructure without the pool knowing. They do not replace recovery after network partitions or database failovers.

## 9. Safe Retries in Spring Data JPA

### 9.1 Retry only transient errors and keep retries bounded

Retries make sense when failures are likely to clear, such as certain brief network glitches, failovers, or deadlocks. Never blindly retry:

- Invalid SQL, missing tables/columns, or broken mappings.
- Wrong credentials or missing privileges.
- Input validation/constraint violations.
- Business errors that cannot succeed when repeated.
- Connection pool exhaustion caused by sustained overload before load is reduced.

Use bounded attempt counts, exponential backoff, and jitter. Set an overall operation timeout so retries do not breach SLAs. Do not let thousands of requests retry simultaneously; jitter helps prevent retry storms.

### 9.2 Each retry attempt needs a fresh transaction

Once a transaction has rolled back or been marked rollback-only, never reuse that transaction to retry. Retries should wrap a call passing through a Spring proxy that starts a fresh transaction for each attempt.

Example with Spring Retry: `OrderRetryFacade` has no `@Transactional`; it delegates to `TransactionalOrderWriter`, a separate bean. The worker uses `REQUIRES_NEW` so every attempt gets an independent transaction, even when the facade is called from an outer transaction:

```java
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderRetryFacade {

    private final RetryTemplate retryTemplate;
    private final TransactionalOrderWriter writer;

    public OrderRetryFacade(
            RetryTemplate retryTemplate,
            TransactionalOrderWriter writer) {
        this.retryTemplate = retryTemplate;
        this.writer = writer;
    }

    public Long save(OrderCommand command) {
        return retryTemplate.execute(
                context -> writer.saveOnce(command)
        );
    }
}

@Service
public class TransactionalOrderWriter {

    private final OrderRepository repository;

    public TransactionalOrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Long saveOnce(OrderCommand command) {
        Order order = new Order(command.idempotencyKey(), command.amount());
        return repository.save(order).getId();
    }
}
```

Illustrative RetryTemplate configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class DatabaseRetryConfig {

    @Bean
    RetryTemplate databaseRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(TransientDataAccessException.class)
                .build();
    }
}
```

This example requires a Spring Retry dependency compatible with your Spring version, the Order repository/entity, and the OrderCommand record. `RetryTemplate` retries only the specified exception types; exception classification must be verified against your real JDBC driver and DBMS. Because the worker uses `REQUIRES_NEW`, each attempt's write transaction commits/rolls back independently of the caller's transaction. Use this pattern only when the business logic permits that independence. If the operation must be atomic with the caller's transaction, place the retry outside the entire use case and start a new transaction for the whole use case on each attempt.

If using `@Retryable` instead of RetryTemplate, check advisor/proxy ordering so retry wraps outside the transaction and each attempt gets a new transaction. Separating a facade from a transactional worker makes that boundary explicit.

### 9.3 Retries can create duplicate data

A dangerous scenario: the database commits, but the network drops before the application receives acknowledgment. The client sees an error and retries, even though the first attempt actually succeeded. Therefore, write operations need an idempotency key or database-level deduplication.

For example:

- The client sends a unique `request_id`.
- The database enforces a UNIQUE constraint on request_id.
- Every retry reuses the exact same request_id.
- The application returns the previously persisted result if request_id already exists instead of creating a duplicate record.

Never generate a new idempotency key on each attempt; doing so defeats duplicate protection.

For external side effects outside the database—such as sending emails, calling payment gateways, or publishing messages—never re-execute them blindly inside a transaction retry loop. Consider a transactional outbox, idempotent consumers, and reconciliation workflows.

## 10. When Should You Use Caching or Graceful Degradation?

When the DB is temporarily unavailable, you can keep certain non-DB-dependent capabilities running:

- Serve public content or valid cached data that has not expired.
- Return a temporary service-unavailable response for write operations.
- Fail fast on DB-dependent requests instead of letting them block waiting for connections.
- Enqueue work into a durable queue if supported by the architecture and paired with deduplication policies.
- Return HTTP 503 with Retry-After when appropriate.

Never use an unbounded in-memory queue to hold requests during a DB outage; the application can run out of memory if the outage lasts. Use caches only when stale data is acceptable and invalidation rules are clear. Never serve cached data as if it were live latest state when the domain requires immediate consistency.

## 11. Recovering from Data Loss or Severe Incidents

When an incident involves data loss, corruption, or backup restoration, this is a database operations procedure requiring DBA/DevOps coordination:

1. Determine impact scope, start time, and operations that may have committed.
2. Select backups/snapshots and recovery logs aligned with RPO/RTO policies.
3. Restore into an isolated environment first to verify.
4. Inspect schemas, migration versions, sequences/identities, indexes, constraints, grants, and extensions.
5. Check cross-table consistency, outbox tables, messages, and external systems.
6. Route traffic only after verifying the database has the right role, endpoint, and data.
7. Run reconciliation for transactions with uncertain outcomes.

Never automatically run DDL repairs or restore backups from application startup. Never delete migration history or recreate schemas simply to let the application start. Those actions can destroy data or leave migration state out of sync with the real database.

## 12. Testing Resilience

Integration tests and chaos/fault-injection tests can verify how the application behaves when the database fails. Run them in isolated, controlled environments:

| Scenario | What to Verify |
|---|---|
| Database stopped before request | Readiness flips DOWN, requests fail cleanly |
| Network reset mid-query | Exception is classified properly, transaction rolls back cleanly |
| Database recovers | Pool creates fresh connections, readiness returns UP |
| Pool exhausted | Requests time out as configured, pending metrics rise, alerts fire |
| Query/lock timeout | Transaction terminates, connection returns to pool |
| Deadlock | One transaction fails; bounded retry runs if operation is safe |
| Commit acknowledgment lost | Idempotency prevents duplicate writes |
| Failover to new primary | New connections point to right endpoint/role with valid privileges |
| Backup restore | Data, schema, migrations, and constraints are verified |

Never test stopping a production database without an approved game-day plan. Simulate failures using Testcontainers, fault-injecting network proxies, or an equivalent staging environment.

## 13. Operations Checklist

**Connections and pool**

- [ ] Application uses the right DataSource, JDBC driver, and endpoint.
- [ ] Pool limits fit total instance counts and DBMS connection budgets.
- [ ] Connection, query, transaction, and lock timeouts are configured separately.
- [ ] maxLifetime/keepaliveTime match database/proxy timeouts.
- [ ] Active, idle, pending, max, and connection creation failure metrics are collected.

**Health and observability**

- [ ] Actuator health is enabled and endpoints are secured.
- [ ] Liveness does not blindly depend on the database.
- [ ] Readiness accurately reflects ability to serve DB-dependent requests.
- [ ] Alerts cover error rates, latency, pool pending, DB connections, locks, and replication lag.
- [ ] Logs include correlation IDs, exception causes, SQLState, and vendor codes without leaking credentials/PII.
- [ ] Traces connect requests to key persistence operations.

**Recovery and correctness**

- [ ] Runbooks exist for DB outages, failovers, pool exhaustion, and restores.
- [ ] Retries apply only to transient errors, with bounds and backoff.
- [ ] Every retry runs in a fresh transaction.
- [ ] Writes include idempotency keys or deduplication.
- [ ] External side effects are never retried blindly.
- [ ] Database outage and recovery tests run in suitable environments.
- [ ] Backups, RPO/RTO targets, and reconciliation workflows are verified.

## 14. Key Takeaways

- Probe connectivity using the application's actual DataSource and driver.
- Distinguish pool timeouts, network timeouts, query timeouts, transaction timeouts, and lock timeouts.
- Actuator readiness stops routing new traffic when the database is unavailable; liveness should not depend on the database by default.
- Monitor Hikari active/idle/pending, query latency, transaction duration, and database-side metrics.
- Read the cause chain, SQLState, and vendor code; do not treat every SQLException as "database down."
- Once the database recovers, in-flight requests may already have failed; the pool opening new connections does not automatically repair business outcomes.
- Retries must be bounded, restricted to transient errors, executed in a fresh transaction, and protected by idempotency.
- Data recovery requires checking consistency, migrations, privileges, and related side effects.

## 15. References

- [Spring Boot Actuator — Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [Spring Framework — Data Access and Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/dao.html)
- [Spring Retry — Reference](https://github.com/spring-projects/spring-retry)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)