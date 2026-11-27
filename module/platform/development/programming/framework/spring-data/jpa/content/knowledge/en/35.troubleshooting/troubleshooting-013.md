# Reading Cause Chains, SQLState, and Logging Without Exposing Sensitive Data

When Spring Data JPA encounters an error, the exception visible at the service layer is often only the outermost wrapper of multiple layers. The root cause may lie in Spring exception translation, JPA, Hibernate, JDBC, or the database management system itself. Accurate diagnosis requires walking the cause chain, locating the associated SQLException, interpreting SQLState alongside vendor error codes, and correlating logs with sufficient context.

Diagnostic logs can also expose customer data, credentials, query parameter values, or business payloads. Therefore, separate essential technical metadata from sensitive data, use correlation IDs to link logs across a single request, and enable SQL/bind parameter logging only in controlled environments.

## 1. Why Do Exceptions Have Multiple Layers?

A repository operation can traverse multiple layers:

1. Service calls a Spring Data repository.
2. Spring Data invokes EntityManager and the JPA provider.
3. Hibernate generates SQL and calls JDBC.
4. JDBC driver sends the statement to the database.
5. Database returns an error; the driver creates an SQLException.
6. Hibernate/JPA may wrap the error into a provider exception or PersistenceException.
7. Spring may translate the error at the repository boundary into an appropriate DataAccessException.

Consequently, the exception at the service layer may be `DataIntegrityViolationException`, while a deeper SQLException holds the SQLState and vendor code. A commit error may surface as `TransactionSystemException` or another exception depending on the transaction manager and provider.

Some commonly seen exception types:

| Exception | Common meaning |
|---|---|
| `DataAccessException` | Spring's general unchecked base class for data access errors |
| `DataIntegrityViolationException` | Constraint violation such as NOT NULL, foreign key, or unique |
| `DuplicateKeyException` | Duplicate key error, typically unique/primary key |
| `BadSqlGrammarException` | Invalid SQL or database rejected syntax |
| `CannotAcquireLockException` | Failed to acquire a required lock |
| `QueryTimeoutException` | Query exceeded allowed time |
| `OptimisticLockingFailureException` | Update failed due to version/optimistic lock conflict |
| `PersistenceException` | JPA-layer error |
| `TransactionSystemException` | Error finalizing a transaction, often seen on commit/rollback |

Exact names and translation behavior depend on Spring, the JPA provider, JDBC driver, and database. Not every error is translated into the exact same exception class. When diagnosing, preserve both the outermost exception and inner causes.

## 2. Reading the Cause Chain Properly

`Throwable.getCause()` returns the direct cause of the current exception. You can traverse this chain to find the deepest cause:

```java
static Throwable deepestCause(Throwable error) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());

    Throwable current = error;

    while (current != null
            && current.getCause() != null
            && visited.add(current)) {
        current = current.getCause();
    }

    return current;
}
```

Import `java.util.Collections`, `java.util.IdentityHashMap`, and `java.util.Set`.

However, the deepest cause does not always hold all useful details. Some JDBC drivers chain sequential SQL errors via `SQLException.getNextException()` instead of `getCause()` alone. Exceptions can also hold suppressed exceptions. Thus, when inspecting database errors, check the cause chain, SQL exception chain, and suppressed exceptions.

An illustrative chain might look like:

```text
DataIntegrityViolationException
  -> ConstraintViolationException (Hibernate)
      -> SQLException
          SQLState: 23505
          Vendor code: 0 or driver-specific code
```

This is an illustrative example of a unique constraint error; actual exception names and vendor codes vary by database and driver.

Do not log only `error.getMessage()` and ignore the cause chain. The outer message may simply say "could not execute statement", while deeper exceptions reveal the constraint or SQLState.

## 3. SQLState and Vendor Error Codes

`SQLException` provides two important fields:

- `getSQLState()`: SQL status code supplied by the driver/database, typically a five-character string following SQLState classification.
- `getErrorCode()`: vendor-specific error code from the database or driver. Its value and meaning depend on the database engine.

SQLState helps categorize errors into groups. Common class codes:

| SQLState class | Error category |
|---|---|
| `08` | Connection error |
| `22` | Data exception, e.g., conversion or invalid value |
| `23` | Integrity constraint violation |
| `40` | Transaction rollback |
| `42` | SQL syntax error or access rule violation |

For example, `23505` typically indicates a unique violation in PostgreSQL. MySQL may return SQLState `23000` with vendor error code `1062` for a duplicate entry. These are database-specific examples; never treat a vendor code as having universal meaning across all database engines.

When reading error codes:

1. Check the SQLState class to identify the error category.
2. Look up the vendor code in documentation for the exact database and driver version.
3. Cross-check constraints, tables/columns, and the associated SQL statement.
4. Check the root cause and when the error occurred.
5. Do not draw conclusions from a single code without transaction or schema context.

SQLState may be `null`, vendor code may be `0`, and an SQLException chain can contain multiple errors. Applications must handle missing codes gracefully.

## 4. Finding SQLException Inside Spring/JPA Exceptions

You can traverse the cause chain, suppressed exceptions, and `SQLException.getNextException()` to extract SQL codes without logging messages:

```java
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

record SqlFailure(String sqlState, int vendorCode) {
}

static SqlFailure findSqlFailure(Throwable error) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
    Deque<Throwable> pending = new ArrayDeque<>();

    if (error != null) {
        pending.add(error);
    }

    while (!pending.isEmpty()) {
        Throwable current = pending.removeFirst();

        if (!visited.add(current)) {
            continue;
        }

        if (current instanceof SQLException sql) {
            String state = sql.getSQLState();
            int code = sql.getErrorCode();

            if (state != null || code != 0) {
                return new SqlFailure(state, code);
            }

            SQLException next = sql.getNextException();
            if (next != null) {
                pending.addLast(next);
            }
        }

        Throwable cause = current.getCause();
        if (cause != null) {
            pending.addLast(cause);
        }

        for (Throwable suppressed : current.getSuppressed()) {
            if (suppressed != null) {
                pending.addLast(suppressed);
            }
        }
    }

    return null;
}
```

This snippet uses an identity set to avoid infinite loops if the exception graph contains cycles. It returns the first SQLException found with a non-null SQLState or non-zero vendor code. If the application needs to inspect multiple errors from a batch, adapt it to collect all SQLException entries rather than stopping at the first.

With Spring's `DataAccessException`, `getMostSpecificCause()` retrieves the deepest cause along the standard cause chain. However, it does not replace traversing `SQLException.getNextException()`.

## 5. Do Not Confuse Save Errors with Flush or Commit Errors

JPA can defer sending SQL to the database. Therefore:

- `save()` may only persist/merge the entity into the persistence context.
- SQL may be sent during auto-flush before a query, when `flush()` is called, or at transaction commit.
- Constraint violations may only surface at flush/commit, even though the earlier `save()` line threw no error.
- A transactional method may finish its body yet the transaction proxy still fails on commit after the method returns.

Example:

```java
@Transactional
public void createCustomer(Customer customer) {
    customerRepository.save(customer);

    // SQL INSERT may not have been executed here yet.
    // Constraint error may surface at flush or commit.
}
```

When you need to force write validation within the method scope, use `saveAndFlush()` or `EntityManager.flush()`:

```java
@Transactional
public void createCustomer(Customer customer) {
    customerRepository.save(customer);
    entityManager.flush();
}
```

Flush sends pending changes to the database without committing the transaction. The transaction can still roll back afterward. To catch commit errors, observe the call from outside the transactional proxy boundary; a try/catch inside the method cannot catch errors raised after the method body returns while the proxy commits.

Avoid adding flush to every operation solely for diagnostics, as it changes SQL execution timing and affects performance.

## 6. Safe Logging: What to Log and What to Avoid

Useful diagnostic logs typically include:

- Business operation or repository operation name.
- Entity/repository type name, without dumping the entire entity.
- Correlation ID or trace ID to link related logs.
- Application-layer exception class.
- SQLState and vendor code if available.
- Timestamp, environment, application version, and transaction/job name where appropriate.
- A stable internal error code for searchability.

Avoid logging directly:

- Passwords, access tokens, refresh tokens, API keys, cookies, or session secrets.
- Card numbers, bank accounts, payment details.
- Emails, phone numbers, addresses, or personal identifiers when unnecessary.
- Request/response bodies, entity `toString()`, or entire DTOs holding customer data.
- Query bind parameter values when they hold real user data.
- Full exception messages if the driver embeds data values in messages.
- SQL constructed with sensitive literals.

Specifically, never turn on bind parameter logging in production just to chase one bug. SQL statements usually show only query structure, whereas bind logs can print actual parameter values. An exception message or stack trace can also expose table/column names, rejected values, or driver-embedded data.

Prefer an allowlist of permitted log fields rather than trying to scrub every sensitive string with a handful of regexes. When identifying records, use appropriate internal IDs or pseudonymized identifiers; never put personal data inside a correlation ID.

## 7. Structured Logging Preserving Useful Information

The example below logs the error type and database codes without emitting messages, SQL, or parameters into standard logs:

```java
private static final Logger log =
        LoggerFactory.getLogger(CustomerService.class);

void logPersistenceFailure(
        String operation,
        String correlationId,
        RuntimeException error) {

    Throwable root = deepestCause(error);
    SqlFailure sql = findSqlFailure(error);

    log.error(
        "Persistence operation failed: operation={}, correlationId={}, " +
        "exceptionType={}, rootCauseType={}, sqlState={}, vendorCode={}",
        operation,
        correlationId,
        error.getClass().getSimpleName(),
        root == null ? "unknown" : root.getClass().getSimpleName(),
        sql == null ? null : sql.sqlState(),
        sql == null ? null : sql.vendorCode()
    );
}
```

Import SLF4J `Logger` and `LoggerFactory`, and place the two helper methods from earlier in the same class or a suitable utility. The example intentionally avoids passing the exception object as the final argument so the logger does not automatically print the full stack trace and message. If your organization requires full stack traces, route them to a restricted-access log store with clear retention policies and verified sensitive-data scrubbing.

Do not swallow the exception after logging. Convert it into an appropriate response or rethrow it so the transaction is handled properly. Catching an exception and continuing inside a rollback-only transaction can still fail on commit.

## 8. Using Correlation IDs to Link Logs

A single request can span controllers, services, repositories, transaction listeners, and background jobs. A correlation ID connects log lines belonging to the same flow without logging user data.

Example with SLF4J MDC:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
        MDC.putCloseable("correlationId", correlationId)) {
    customerService.updateCustomer(command);
}
```

Configure the logging framework pattern to include `correlationId` in each log line. With Spring Boot Actuator/Micrometer Tracing, built-in trace ID/span ID can be used if tracing is configured.

MDC is typically thread-local based. When handing work off to `@Async`, executors, or thread pools, MDC does not automatically propagate to other threads. If correlation IDs are needed in background tasks, configure a `TaskDecorator` or appropriate context propagation to copy and restore MDC; never leave stale context on pool threads after a task finishes.

Correlation IDs must be generated or validated at a trusted boundary. Never take an arbitrary client header directly as a value that could carry sensitive content or control characters; bound length and sanitize values before logging.

## 9. Controlled SQL Logging

When you need to inspect SQL generated by Hibernate, enable loggers via a diagnostic profile. Example for Hibernate 6:

```yaml
# application-diagnostics.yml
logging:
  level:
    org.hibernate.SQL: DEBUG
```

If bind parameters are needed, Hibernate 6 uses the category:

```yaml
logging:
  level:
    org.hibernate.orm.jdbc.bind: TRACE
```

On Hibernate 5, the typical bind category is:

```yaml
logging:
  level:
    org.hibernate.type.descriptor.sql.BasicBinder: TRACE
```

Bind logging can leak real data. Enable it only in development or test environments with synthetic data, for short windows, and under appropriate access controls. Never enable these TRACE categories in production for routine troubleshooting. SQL statements themselves can also contain sensitive literals or schema details if native SQL is constructed unsafely.

Prefer loggers toggleable via profiles and centralized log collection. Avoid leaving `spring.jpa.show-sql` enabled permanently because printing SQL directly to stdout bypasses uniform application logging policies. After reproducing the bug, turn off verbose log levels and confirm production configurations no longer enable bind logging.

## 10. Reading Logs by Error Group

| Symptom | Investigation direction |
|---|---|
| SQLState class `23` or `DataIntegrityViolationException` | Check NOT NULL, unique, foreign key, column length, and input data |
| SQLState class `08` | Check connectivity, network, database availability, pool timeout, and driver |
| SQLState class `22` | Check data types, conversions, precision/scale, and out-of-range values |
| SQLState class `40` | Check deadlocks, serialization failures, transaction retries, and lock ordering |
| SQLState class `42` | Check table/column names, schema, syntax, permissions, and generated query |
| `OptimisticLockingFailureException` | Check `@Version`, concurrent updates, and retry handling |
| `QueryTimeoutException` or lock timeout | Check query plan, indexes, held locks, and transaction duration |
| `TransactionSystemException` on method completion | Check cause chain, flush/commit, and transaction manager |

This is an orientation map, not an automatic diagnosis. A single SQLState or exception class can have multiple underlying causes. Verify against the active database's documentation, schema, SQL shape, and transaction context.

## 11. Workflow for Diagnosing a Production Error

1. Retrieve correlation ID, timestamp, operation, and application version from safe logs.
2. Identify the outermost exception and the Spring/JPA exception type received by the service.
3. Walk the cause chain, suppressed exceptions, and `SQLException.getNextException()`.
4. Extract SQLState and vendor code; look them up in documentation for the exact database/driver.
5. Determine whether the error occurred during query, flush, or commit; check `@Transactional` boundaries.
6. Cross-check schema, constraints, entity mapping, indexes, connection health, and lock contention.
7. If detailed SQL is needed, reproduce with synthetic data in a controlled environment and enable loggers briefly.
8. Record SQL shape and parameter positions; do not record sensitive bind parameter values.
9. Fix the root cause, add regression tests, and turn off verbose diagnostic logging once complete.

When sharing logs with teammates or pasting into tickets, strip tokens, personal info, parameter values, connection strings, and business payloads. Keep only the stack trace structure or SQLState needed for the recipient to reproduce the issue with anonymized data.

## 12. Common Mistakes During Diagnosis

**Reading only the outermost exception.** Its message can be overly generic. Always traverse the cause chain and SQLException chain.

**Assuming the root cause is always the first SQLException.** A deeper exception may be the root cause, while `getNextException()` holds additional errors. Keep the full error structure when analyzing.

**Assuming save() succeeding means commit succeeded.** JPA can defer SQL until flush/commit. Check errors at the transaction boundary.

**Relying on vendor codes without knowing the database.** Vendor codes do not share uniform meanings across engines. Record the database type and driver version alongside the code.

**Enabling TRACE bind parameters in production.** Parameter values can contain PII or secrets. Use synthetic data and controlled environments.

**Logging entire entities or request bodies.** `toString()` may expose passwords, tokens, emails, or other sensitive fields. Log only allowlisted fields.

**Logging without correlation IDs.** Linking logs across layers or threads becomes hard. Propagate trace/correlation context safely, especially with async work.

**Catching and ignoring exceptions.** This hides bugs and leaves transactions in a rollback-only state. Handle errors deliberately and ensure callers receive accurate outcomes.

## Conclusion

Troubleshooting Spring Data JPA requires combining the outermost exception, cause chain, SQLException chain, SQLState, and vendor error code. SQLState classifies the category, while vendor codes must be interpreted against the exact database and driver. When logging, use correlation IDs and allowlisted technical fields; avoid messages, entities, request bodies, and bind parameters containing real data. Enable SQL/bind logging only in controlled environments and turn it off after reproducing the bug. This preserves the diagnostic signal needed to find root causes without turning your logging system into a store of sensitive data.
