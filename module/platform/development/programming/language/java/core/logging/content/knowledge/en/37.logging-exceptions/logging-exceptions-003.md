# Logging in the Repository Layer in Java — Exceptions, Transactions, SQL, and Logging Responsibilities

## 1. The Role of the Repository and the Question “Should We Log Here?”

In a layered Java application, the **repository/DAO** provides data access operations via JDBC, JPA/Hibernate, Spring Data, or a storage adapter. The repository typically sits below the application service and above the database:

```text
HTTP Controller / Message Consumer
             |
     Application Service
    (use case, transaction)
             |
       Repository / DAO
     (query, mapping, data)
             |
    JDBC / JPA / Driver / DB
```

Because it is close to the database, the repository can observe the operation type, datasource, rows read/written, technical exceptions, and latency. However, logging too much here increases I/O and CPU overhead, creates duplicates with the service/controller, and can even expose SQL parameters, passwords, or personal data.

In the **Logging and Exceptions** group, the **Repository Logging** topic emphasizes four goals: **log the right technical information**, **preserve exception and transaction semantics**, **avoid duplicate error logging**, and **do not leak sensitive data**. There is no rule that every `repository.save(...)` must log at INFO.

Consider a successful request:

```text
GET /api/orders/42
  → HTTP filter: request summary + status/duration
  → OrderService: decides to read the order
  → OrderRepository: SELECT...
  → DB: one row
  → Service: returns OrderView
  → HTTP 200
```

Once an HTTP summary is already logged, you usually **do not need** a `"find order 42"` line at the controller, service, and repository. The repository only needs diagnostic logs at DEBUG or metrics/tracing when there is a technical question to answer.

## 2. Dividing Log Ownership Across Layers

| Event | Typically appropriate owner | Level / signal |
| --- | --- | --- |
| Request start/end, status, duration | HTTP filter / Observation | INFO, timer metrics |
| Business state change | Service / domain event | INFO or audit |
| A generated SQL query | Hibernate / JDBC instrumentation | DEBUG as needed |
| Slow query / connection acquisition | Repository wrapper / metrics | Thresholded WARN, histogram |
| Cache miss, batch fetch | Repository / adapter | DEBUG or metric |
| Record not found | Service / controller decides meaning | INFO/DEBUG or no log |
| Unhandled exception | Boundary (HTTP, consumer, scheduler) | ERROR once |
| Intentional storage retry | Retry owner | WARN per attempt, final outcome |
| Durable transaction commit | Post-commit / outbox / audit infrastructure | Business event with a contract |

This rule is an **architectural guideline**, not a mandatory Java API. A repository might be the final observation point in a CLI job, library, or standalone connector; in that case, it can own WARN/ERROR logs. Regardless of where it happens, **each failure must have one owner for the summary log**, avoiding multi-layer catch–log–rethrow that adds no new information.

### 2.1. Benefits of Structured Logs

A structured event:

```text
WARN event=repository.slow_operation
     operation=find_order entity=Order datasource=primary
     duration_ms=1280.400 trace_id=<safe-trace-id>
```

Fields such as `event`, `operation`, `entity`, `datasource`, and `duration_ms` help diagnose issues faster than `"DB is slow"`. In a real application, `trace_id` must be supplied by instrumentation; do not copy placeholders into production data. You do not need to print raw query params or entity objects to diagnose duration.

## 3. Distinguishing Three Cases: FOUND, NOT_FOUND, and ERROR

`repository.findById(42L)` can:
1. Return an entity: query succeeded.
2. Return `Optional.empty()`: no record matched the criteria; this is not a database error by itself.
3. Throw an exception: **the outcome is unknown because data access failed**.

Do not conflate “does not exist” with “could not query”.

| Situation | Repository layer result | Service / boundary behavior |
| --- | --- | --- |
| Row exists | `Optional.of(entity)` | Map to DTO, return success |
| Row does not exist | `Optional.empty()` | May be HTTP 404 or a valid result |
| Database unavailable | Exception | Report infrastructure error, usually not 404 |
| Write conflict | Classified exception | Conflict / retry if business rules allow |
| Query timeout | Exception | Evaluate timeout budget and retryability |

Spring Data JPA example:

```java
Optional<OrderEntity> found = orderRepository.findById(orderId);
if (found.isEmpty()) {
    return Optional.empty();
}
return found;
```

This is an **illustrative snippet** inside a method that has `OrderEntity`, `orderRepository`, and an appropriate return type, not a standalone Java file. Do not log ERROR just because of `Optional.empty()`; the service understands the use-case semantics better than the repository.

## 4. Exceptions in the Repository: Propagate, Translate, or Recover?

When a database call fails, the repository has several options:

- **Propagate:** let the exception bubble up to the layer authorized to decide the outcome; usually the right default.
- **Translate:** convert driver/JPA exceptions into an appropriate abstraction, preserving the original cause when possible.
- **Recover:** fallback/retry according to a designed policy that accounts for idempotency.
- **Technical logging:** only if critical diagnostic facts exist solely in the repository and contain no secrets.

A common anti-pattern:

```java
try {
    repository.save(order);
} catch (RuntimeException ex) {
    log.error("Saving order failed", ex);
    throw ex;
}
```

If the service and global exception handler also log-and-rethrow, a single failure produces **three nearly identical stack traces**. That pollutes logs and can increase ingest costs. If you cannot handle the error here, usually all you need is:

```java
repository.save(order);
```

The layer capable of deciding the HTTP response, retry, dead-letter, or fallback will log **one outcome event** with the operation, error type, and correlation ID. If a layer needs to add context, it can wrap the exception while keeping `cause`, without needing to log immediately at every layer.

### 4.1. Do Not Swallow Exceptions

A risky example:

```java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    log.warn("Database write failed");
}
return successResponse;
```

The method returns a false success even though the write failed. With Spring transactions, an error may mark the transaction as rollback-only, leading to `UnexpectedRollbackException` when the transaction finishes. Only catch and continue if you have valid recovery/compensation and the business outcome is genuinely correct.

## 5. Runnable Java 17+ Example: Logging in the Repository and at the Request Boundary

This example uses **`java.util.logging` (JUL)**, requiring no Spring or real database. The in-memory repository simulates three outcomes: found, not found, and exception. The repository logs diagnostics at `FINE`; the boundary logs the outcome once. A custom in-memory `Handler` ensures deterministic stdout without depending on timestamps or machine-local logger configuration.

Save as `RepositoryLogDemo.java`:

```java
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class RepositoryLogDemo {
    private static final class Lines extends Handler {
        private final StringBuilder output = new StringBuilder();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            output.append(record.getLevel().getName())
                  .append(" ")
                  .append(record.getMessage())
                  .append("\n");
        }

        @Override public void flush() { }
        @Override public void close() { }

        String text() { return output.toString(); }
    }

    private static final class StoreUnavailable extends RuntimeException {
        StoreUnavailable() { super("simulated storage failure"); }
    }

    private static final class InMemoryOrderRepository {
        private final Logger log;
        private final Map<Long, String> rows = Map.of(42L, "PAID");

        InMemoryOrderRepository(Logger log) {
            this.log = log;
        }

        String findStatus(long id) {
            log.fine("event=repository.lookup entity=Order id=" + id);
            if (id == 9L) {
                throw new StoreUnavailable();
            }
            return rows.get(id);
        }
    }

    private static void handleRequest(long id,
                                      InMemoryOrderRepository repo,
                                      Logger requestLog) {
        try {
            String status = repo.findStatus(id);
            if (status == null) {
                requestLog.info("event=order.lookup outcome=NOT_FOUND id=" + id);
            } else {
                requestLog.info("event=order.lookup outcome=FOUND id=" + id
                        + " status=" + status);
            }
        } catch (StoreUnavailable ex) {
            requestLog.warning("event=order.lookup outcome=ERROR "
                    + "error_type=STORE_UNAVAILABLE id=" + id);
        }
    }

    public static void main(String[] args) {
        Logger repoLog = Logger.getLogger("demo.repository");
        Logger requestLog = Logger.getLogger("demo.request");
        Lines handler = new Lines();
        handler.setLevel(Level.ALL);

        repoLog.setLevel(Level.FINE);
        requestLog.setLevel(Level.INFO);
        repoLog.setUseParentHandlers(false);
        requestLog.setUseParentHandlers(false);
        repoLog.addHandler(handler);
        requestLog.addHandler(handler);

        try {
            InMemoryOrderRepository repo = new InMemoryOrderRepository(repoLog);
            handleRequest(42L, repo, requestLog);
            handleRequest(77L, repo, requestLog);
            handleRequest(9L, repo, requestLog);
            System.out.print(handler.text());
        } finally {
            repoLog.removeHandler(handler);
            requestLog.removeHandler(handler);
            handler.close();
        }
    }
}
```

Run:

```bash
javac --release 17 RepositoryLogDemo.java
java RepositoryLogDemo
```

Exact stdout:

```text
FINE event=repository.lookup entity=Order id=42
INFO event=order.lookup outcome=FOUND id=42 status=PAID
FINE event=repository.lookup entity=Order id=77
INFO event=order.lookup outcome=NOT_FOUND id=77
FINE event=repository.lookup entity=Order id=9
WARNING event=order.lookup outcome=ERROR error_type=STORE_UNAVAILABLE id=9
```

For ID 9, the repository **throws an error** without printing a stack trace; the boundary catches it and logs a single WARNING. The two differently named loggers are not in a parent-child relationship in this example, and each logger has one handler and `setUseParentHandlers(false)`, so no duplicates are created by propagation.

This is a **logging architecture demo**, not a production in-memory JDBC implementation. For real HTTP requests, the boundary must return an appropriate response status or perform retry/dead-letter according to the contract, rather than just catching and finishing like the demo. `id` is a synthetic value; user/order identifiers in a real system must be checked against privacy policies before logging.

### 5.1. Why Log at FINE/DEBUG?

DEBUG-level logging (the closest JUL equivalent is `FINE`) is usually suitable for inspecting internal operations without forcing INFO output in production. When lower levels are disabled, the application avoids part of the event-generation cost; however, string concatenations evaluated before the JUL call may still be allocated, so for expensive logs consider `logger.isLoggable(Level.FINE)` or an appropriate deferred-formatting API.

Do not log entire entities, JDBC parameters, or query results even at FINE/DEBUG: developers may temporarily enable debug in an environment containing real data.

## 6. Spring Data JPA: Responsibilities of the Repository Interface

A Spring Data JPA repository:

```java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderJpaRepository
        extends JpaRepository<OrderEntity, Long> {
}
```

`OrderEntity` is an entity in the project. This snippet requires Spring Data JPA, Jakarta Persistence, and a configured datasource; it does not compile standalone with only the JDK.

The service decides the business meaning:

```java
package com.example.orders;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {
    private final OrderJpaRepository orders;

    public OrderQueryService(OrderJpaRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderView find(long id) {
        OrderEntity entity = orders.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
        return new OrderView(entity.getId(), entity.getStatus());
    }
}
```

`OrderView`, `OrderNotFoundException`, and `OrderEntity` are project-specific types, so this class only illustrates the architecture. When not found, the service translates it into a domain exception; the HTTP boundary can map that to 404. There is no need to log an ERROR line in the repository.

### 6.1. Transaction Configuration in Spring Data JPA

According to Spring Data JPA documentation, CRUD methods **inherited** from `CrudRepository` typically use `SimpleJpaRepository`'s transaction configuration: read operations default to `readOnly=true`, and write operations use standard `@Transactional`. **User-declared query methods do not automatically share the same transaction configuration** in all cases. For use cases that call multiple repositories, the transaction boundary should usually live at the service/facade.

Do not assume a `findBy...` method always has a read-only transaction, and do not rely solely on method names to infer commit or flush conditions.

## 7. `@Repository`, Exception Translation, and `DataAccessException`

Spring provides an exception abstraction hierarchy under `org.springframework.dao.DataAccessException`. When `PersistenceExceptionTranslationPostProcessor` and an appropriate translator are present, `@Repository` beans can have persistence exceptions from JPA/Hibernate/ORM translated.

It is **incorrect** to say that the `@Repository` annotation automatically translates **every** checked `SQLException` from raw JDBC. With `JdbcTemplate`, Spring uses the appropriate `SQLExceptionTranslator` in the JDBC pipeline; hand-written raw JDBC needs an explicit exception contract.

Common types:

| Exception type | Typical meaning | Action |
| --- | --- | --- |
| `DataAccessException` | Root of Spring DAO hierarchy | Do not retry every subtype |
| `DataIntegrityViolationException` | A DB constraint was violated | Read constraint/driver cause safely |
| `DuplicateKeyException` | Unique/primary key conflict | Domain conflict when business-valid |
| `OptimisticLockingFailureException` | Version conflict on update | Conditional retry or return 409 |
| `CannotGetJdbcConnectionException` | Failed to acquire a connection | Check DB / pool / network |
| `QueryTimeoutException` | Query exceeded timeout per translator | Review timeout budget and query plan |
| `EmptyResultDataAccessException` | API expected a row but none existed | May represent a not-found result |

Exception mapping is influenced by driver, dialect, access technology, and operation; `DataIntegrityViolationException` can be a unique, foreign key, or non-null constraint. Do not map all of them to HTTP 409 just because they look like conflicts.

## 8. One Error, One Log at the Boundary

The `Repository` usually does not know whether the request will be retried, fall back, or be returned as HTTP 503. The boundary has full context to decide the final log:

```text
Driver/JPA -> CannotGetJdbcConnectionException
Repository -> propagate
Service -> propagate if unrecoverable
HTTP handler -> log ERROR once + return HTTP 503
```

Example method in a Spring MVC `@RestControllerAdvice` class:

```java
@ExceptionHandler(CannotGetJdbcConnectionException.class)
ResponseEntity<ProblemDetail> storageUnavailable(
        CannotGetJdbcConnectionException ex) {
    log.error("event=storage.unavailable "
            + "error_type={} operation={}",
            ex.getClass().getSimpleName(), "read_order");

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Storage temporarily unavailable");
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(problem);
}
```

This is an illustrative method using an SLF4J logger and Spring Web imports; it is **not standalone**. Status 503 is only appropriate for the connection-unavailable scenario in the example, not for every `DataAccessException`. The log does not print `ex.getMessage()` because that message may contain a JDBC URL, SQL parameters, or credentials.

When the service needs to convert a technical exception into a domain exception:

```java
try {
    repository.reserve(orderId);
} catch (OptimisticLockingFailureException ex) {
    throw new OrderConcurrentUpdateException(orderId, ex);
}
```

`OrderConcurrentUpdateException` is a custom type with a constructor that stores the original `cause`. There is no need to call `log.error` before throwing if the global handler already owns error logging. Preserving the cause allows diagnosing the stack trace at the exact place authorized to log it.

## 9. Transactions: `save`, Flush, and Commit Are Different

Anti-pattern:

```java
@Transactional
public void createOrder(Order order) {
    repository.save(order);
    log.info("Order committed id={}", order.getId());
}
```

In JPA, `save` may update the persistence context; SQL may be executed at flush/commit depending on the provider and ID strategy. `saveAndFlush` pushes SQL out earlier, but **does not mean the transaction has committed**. After the method returns, the transaction interceptor can still encounter an exception at commit. Therefore, logging `"committed"` beforehand can be wrong.

If you only log the action inside the transaction, use honest wording such as `"save attempted"` or `"entity staged"`; do not prematurely claim commit success.

If you need audit records or events emitted **after commit**, common approaches include:
- Spring `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` runs a callback in the corresponding phase, though an in-memory callback **does not guarantee durable delivery after a crash**.
- A transactional outbox writes the event in the same transaction as the data change so another worker can publish it later.
- An audit trail with ID/sequence, retention, and durability matching business requirements.

Do not use an INFO line from an `AsyncAppender` as definitive proof of a commit or durable storage.

### 9.1. Rollback and Checked/Unchecked Errors

In Spring, transactions roll back by default on `RuntimeException` or `Error`, whereas checked exceptions may require `rollbackFor` or explicit configuration. If a repository swallows an error and only logs a WARN, the service may think the operation succeeded or hit rollback-only at commit.

Do not retry inside an already-failed transaction without knowing whether it is still usable or marked rollback-only. For transaction retries, you need a policy that creates a new valid attempt/transaction at the appropriate layer.

### 9.2. Database Errors Sometimes Occur After the Repository Method

Lazy loading, `flush`, validation, the transaction interceptor, or DB commit can throw an exception after a repository method has already returned. Therefore, catching and logging every error in each repository method **does not cover all errors**, while still causing duplicates. Monitor both the transaction boundary and traces.

## 10. SQL Logging: Hibernate 6 and Bind Parameter Risks

With Hibernate 6, categories used for diagnostics:

```properties
# Spring Boot application.properties - enable temporarily when needed
logging.level.org.hibernate.SQL=DEBUG

# Dangerous with real data: logs JDBC binding values.
# logging.level.org.hibernate.orm.jdbc.bind=TRACE

# Can also expose data read from ResultSet.
# logging.level.org.hibernate.orm.jdbc.extract=TRACE
```

- `org.hibernate.SQL` prints generated SQL through Hibernate's logging level.
- `org.hibernate.orm.jdbc.bind` at TRACE can print **actual bound values**: emails, account numbers, tokens, password hashes.
- `org.hibernate.orm.jdbc.extract` can print read data.
- `hibernate.show_sql=true` writes SQL to the console via Hibernate's own mechanism, not quite the same as a configured logger appender; it is harder to control centrally.

Hibernate 5 categories differ in part from Hibernate 6; always check your framework version. Do not enable JDBC bind/extract TRACE in production containing sensitive data.

### 10.1. SQL Placeholders Do Not Automatically Prevent Log Leaks

Example:

```sql
SELECT id, status FROM orders WHERE customer_email = ?
```

`PreparedStatement` provides parameterization and reduces SQL injection, but driver/Hibernate TRACE can still log the **bound email**. SQL text can also contain sensitive literals if the app concatenates queries manually. Thus, the rule against printing secrets still applies even when code uses parameterized queries.

Enable SQL DEBUG in a safe environment, use synthetic data, restrict viewer access, and turn it off after investigation. Check collectors, archives, dashboards, and backups because a log line emitted once can persist for a long time in many places.

## 11. JDBC: Timing Operations Without Printing Parameters

Measure duration with `System.nanoTime()`:

```java
public Optional<String> findStatus(long id) throws SQLException {
    long started = System.nanoTime();
    boolean completed = false;
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(
                 "SELECT status FROM orders WHERE id = ?")) {

        ps.setLong(1, id);
        try (ResultSet rs = ps.executeQuery()) {
            Optional<String> result = rs.next()
                    ? Optional.ofNullable(rs.getString("status"))
                    : Optional.empty();
            completed = true;
            return result;
        }
    } finally {
        double millis = (System.nanoTime() - started) / 1_000_000.0;
        if (log.isDebugEnabled()) {
            log.debug("event=repository.operation "
                    + "operation=find_status entity=Order "
                    + "outcome={} duration_ms={}",
                    completed ? "OK" : "FAILED", millis);
        }
    }
}
```

This is an integration snippet requiring `javax.sql.DataSource`, `java.sql`, `Optional`, an SLF4J logger, and a DB table. **It does not run standalone with only the JDK**. It measures connection acquisition, prepare, execute, and reading one row—not just CPU/database execution time. Do not print `id` or bound values in the log to reduce sensitive-data risk.

Measuring elapsed time with a monotonic clock is more suitable than `System.currentTimeMillis()` because wall-clock time can jump. If you need to separate pool wait from query execution, use separate timers/spans.

The snippet declares `throws SQLException`: a checked `SQLException` is not automatically converted to `DataAccessException` just because the author adds `@Repository`. With Spring JDBC, `JdbcTemplate` is usually the right abstraction for exception translation and resource handling.

## 12. Logging Slow Repository Operations Without Spam

Example event:

```text
WARN event=repository.slow_operation
     operation=find_order entity=Order
     datasource=primary duration_ms=1280.4 trace_id=<safe-id>
```

A 1,000 ms threshold is only an example. A small lookup may need a lower threshold; a large report may be designed to run longer. Choose based on SLOs, operation classification, and context.

Design guidelines:
- Record metrics/histograms for all important operations when possible.
- Log WARN for slow requests exceeding the threshold, or sample in a controlled way.
- Include operation name, datasource, duration, outcome, and a safe trace ID.
- Do not attach emails, order IDs, raw SQL, or request IDs to high-cardinality **metric tags**.
- Check connection pool, locks, network, fetching, and mapping before concluding DB execution is slow.
- Measure formatting/appender overhead; a full async queue can block or drop logs.

A slow request might be 900 ms waiting on the pool and 10 ms querying; a total repository time of 910 ms does not prove the SQL engine took 910 ms.

## 13. Metrics, Tracing, MDC, and Privacy

| Signal | Use for | What to avoid |
| --- | --- | --- |
| Logs | Failure details / operation / error type | Dumping entities/params, duplicate stacks |
| Metrics | Query count, pool usage, p95/p99 | High-cardinality IDs / raw SQL labels |
| Traces | HTTP → service → repository → DB | Sensitive queries / credentials in spans |
| Audit | Business state changes with retention | Using repository DEBUG instead of an audit store |

Useful metrics: active/idle/pending pool counts, connection acquisition time, query duration, timeout/deadlock rates, retries, and SQL statements per HTTP request. Spring Boot with HikariCP/Micrometer may already provide some of these signals; check before building custom logging for every query.

MDC or Log4j2 `ThreadContext` helps attach `trace_id`, `request_id`, and operation to logs. SLF4J example:

```java
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("operation", "find_order")) {
    return repository.findById(id);
}
```

This is an integration snippet requiring `org.slf4j.MDC`. `try-with-resources` cleans up the context to avoid leaking across requests when a thread pool reuses threads. For async tasks, proper propagation is needed; MDC does not automatically transfer across all threads.

Do not put passwords, bearer tokens, cookies, JDBC URLs with secrets, user credentials, or SQL parameters into MDC, log messages, exceptions, or span attributes. Structured logging and `{}` placeholders **do not automatically mask data**.

## 14. Retries and Exception Logging: Distinguishing Attempts from Final Failure

A transient error can be retried when there is an idempotency policy and timeout budget. However, **do not retry all `DataAccessException`s**: constraint violations or non-idempotent writes may be invalid to retry.

An example:

```text
WARN event=storage.retry operation=reserve_order
     attempt=2 max_attempts=3 reason=TRANSIENT
ERROR event=order.reserve_failed attempts=3
      error_type=STORAGE_UNAVAILABLE
```

These are **two events with different meanings**: a retry occurred, and a failure outcome occurred after exhausting attempts. They are not duplicates if event/attempt metadata is clear. You do not need to log a stack trace on each retry when you already have the final failure, unless diagnostic requirements demand it.

If a retry needs a new transaction, the policy must wrap outside the transaction; retrying inside a rollback-only transaction may not recover. For optimistic locking, only retry when the operation can safely re-run and is allowed by the use case.

## 15. Batching and N+1: When INFO per Query Becomes a Problem

A controller can trigger an N+1 issue, such as fetching 100 orders and then loading a relation for each order one by one. If every repository method logs INFO, a single request generates hundreds of lines. Logging itself can increase latency and ingest cost while still not explaining why there are so many queries.

Appropriate tools:
- SQL/query statistics, call counts, and connection-pool metrics.
- JDBC spans/traces, being careful with attributes containing personal data.
- Temporary Hibernate SQL DEBUG in a safe environment.
- Query plans, fetch strategy, batch size, and code review.
- Load testing after fixing the query, rather than just turning off loggers to cut volume.

For batch jobs, log one summary: safe `batch_id`, total items, duration, and success/failure counts. If per-row auditing is a strict requirement, use an audit channel with designed transaction/durability/retention guarantees, not `AsyncAppender` INFO logs.

## 16. Package-Level Configuration in Spring Boot

```properties
logging.level.root=INFO
logging.level.com.example.orders.repository=DEBUG

# Enable only when investigating Hibernate 6 SQL:
logging.level.org.hibernate.SQL=DEBUG

# Do not leave enabled permanently when using real data:
# logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

`com.example.orders.repository` affects only loggers in that namespace. Hibernate SQL uses its own category; setting DEBUG on the repository package does not automatically enable SQL logging.

If you attach a separate appender to the repository, check `additivity`. Attaching the same appender to both the child logger and root can log twice; setting `additivity=false` without an appender on the child can drop logs. In many cases, package-level logger levels are all you need, without a new file appender.

## 17. Testing Checklist for Failure, Privacy, and Logging

| Case | Expectation |
| --- | --- |
| Query returns entity | No INFO spam, service receives the right result |
| Query returns empty | Not treated as a DB outage |
| DB connection failure | Exception propagates, summary logged once |
| Data integrity violation | Classified properly, no blind retries |
| Duplicate key | Conflict when valid for the use case |
| Optimistic locking | Cause preserved, retry/409 per contract |
| Query timeout | Includes error type/operation/duration, no raw params |
| Service calls save then commit fails | Does not falsely log “committed” |
| Repository catches DataAccessException | Does not swallow to return false success |
| Exception crosses 3 layers | Does not print three duplicate stack traces |
| Hibernate SQL DEBUG | Shows needed SQL, no bound values |
| Hibernate bind TRACE | Not enabled with sensitive production data |
| Raw JDBC SQLException | Does not assume annotations auto-translate |
| Retry | Attempts and final result have distinct event names |
| MDC in thread pool | No context/request ID leakage |
| N+1 / batch | Useful metrics/traces, no log spam |
| Root + child appender | No duplicates from additivity |
| Async logging | Understands full queue, block/drop, shutdown |

You can attach a test appender/Handler to assert event counts, levels, and error codes. Use synthetic canary credentials to verify that no sink prints tokens, SQL parameters, or sensitive data. Integration tests should verify transaction rollback and HTTP responses, not just log counts.

## 18. Common Mistakes

**Logging INFO on every `findById/save`:** increases volume while duplicating service/HTTP summaries.

**Catch–log–rethrow at every layer:** one exception produces multiple useless stack traces.

**Logging then swallowing errors:** transactions and responses can become inconsistent.

**Treating `Optional.empty()` as ERROR:** confuses missing data with a database failure.

**Logging “committed” after `save()`:** flush/commit may happen later.

**Enabling JDBC bind TRACE:** can expose PII, credentials, and returned data.

**Printing entity/`toString`:** may include emails, tokens, password hashes, or financial data.

**Retrying every `DataAccessException`:** some errors are non-retryable; risks duplicate side effects.

**Measuring duration with `currentTimeMillis`:** wall-clock can jump; use `nanoTime` for elapsed time.

**Using repository DEBUG as audit:** lacks proper durability and transaction guarantees.

**Adding metric labels with raw SQL/IDs:** causes cardinality explosion.

**Attaching duplicate root/child appenders:** creates duplicates due to additivity.

## 19. Practical Design Workflow

1. Identify whether the repository uses JDBC, Spring Data JPA, or another adapter.
2. Classify found / not found / expected conflict / transient / fatal error.
3. Define **the layer that owns ERROR logging** and retry/fallback responsibilities.
4. Log only truly needed repository diagnostics: operation, entity, datasource, duration, outcome.
5. Never log raw SQL bind parameters, sensitive entities, credentials, or unchecked exception messages.
6. Place transaction boundaries at the service layer and do not treat save/flush as commit.
7. Use metrics/tracing for pool latency, query duration, N+1 detection, throughput, and error rate.
8. Enable SQL DEBUG/TRACE temporarily per policy, checking your Hibernate version.
9. Verify log routing, additivity, async loss, and access permissions.
10. Test propagation, rollback, exception translation, privacy, and absence of duplicates.

**Conclusion:** the repository primarily provides **data access results and the right exception types**. Logs here should supply useful technical context without replacing business, transaction, or audit events, and without repeating full errors across other layers. Clear ownership keeps the system both easy to investigate and reliable in its logging.

## References

- [Spring Data JPA – Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html).
- [Spring Framework – PersistenceExceptionTranslationPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/annotation/PersistenceExceptionTranslationPostProcessor.html).
- [Spring Framework – DataAccessException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html).
- [Spring Framework – JdbcTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- [Hibernate ORM – Logging categories](https://docs.jboss.org/hibernate/orm/6.4/logging/logging.html).
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html).
- [SLF4J – User Manual](https://www.slf4j.org/manual.html).
- [Oracle Java – System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).
- [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).