# Resource Errors, Locks, Concurrency, and Retryability in Spring Data Access

When accessing a database through `JdbcTemplate` or Spring's data access layers, an operation can fail due to **connection/resource issues**, **lock contention**, **concurrent update conflicts**, or **data/SQL errors that cannot be resolved by retrying**. These errors require different handling. In particular, **it is not safe to simply catch `DataAccessException` and re-run the SQL statement**.

For example, two transactions updating the same row can trigger a lock timeout or deadlock; two users editing the same record can cause an optimistic conflict; a database disconnect after a money transfer command can leave the application **not knowing whether the command committed or not**. In each case, you must classify accurately, understand transaction boundaries, choose a safe action, and retry only with justification.

This lesson focuses on Spring Framework's `org.springframework.dao` exception hierarchy, recognizing resource/lock/concurrency failures, deciding retryability, keeping data consistent, and Java 17+ examples using Spring JDBC.

## 1. What Does Spring Do When JDBC Raises an Error?

In plain JDBC, you frequently encounter `SQLException`, `SQLTransientException`, `SQLIntegrityConstraintViolationException`, `SQLTransactionRollbackException`, and database-specific `SQLState` or error codes. If every business layer merely catches generic `SQLException`, application code becomes directly coupled to the driver and vendor.

`JdbcTemplate` typically **translates `SQLException`s** into Spring's unified runtime exception hierarchy:

```text
Driver / database
  -> SQLException (+ SQLState, vendor error code, subtype)
  -> Spring JDBC SQLExceptionTranslator
  -> Appropriate DataAccessException
  -> Service layer decides rollback, error reporting, or retry
```

`DataAccessException` is an **unchecked** exception (extending `RuntimeException`). Spring uses `SQLExceptionTranslator` to map JDBC errors. In Spring Framework 6.x, the default translator is `SQLExceptionSubclassTranslator` with fallback to `SQLStateSQLExceptionTranslator`; `SQLErrorCodeSQLExceptionTranslator` can use vendor error codes when appropriately configured.

**There is no guarantee** that a given SQLState always produces the exact same Spring exception class across all driver/vendor versions. When analyzing real incidents, inspect the Spring exception class, `getMostSpecificCause()` or `getRootCause()`, SQLState, vendor code, and transaction state together.

## 2. Important Exception Branches

Abbreviated diagram:

```text
DataAccessException (RuntimeException)
├── TransientDataAccessException
│   ├── ConcurrencyFailureException
│   │   ├── PessimisticLockingFailureException
│   │   │   └── CannotAcquireLockException
│   │   └── OptimisticLockingFailureException
│   ├── TransientDataAccessResourceException
│   └── QueryTimeoutException
├── NonTransientDataAccessException
│   ├── NonTransientDataAccessResourceException
│   │   └── DataAccessResourceFailureException
│   │       └── CannotGetJdbcConnectionException
│   ├── DataIntegrityViolationException
│   │   └── DuplicateKeyException
│   └── InvalidDataAccessResourceUsageException
├── RecoverableDataAccessException
└── UncategorizedDataAccessException
```

This is an **illustrative tree of relevant branches**, not a complete list of every Spring superclass/subclass. `BadSqlGrammarException` belongs to the invalid SQL/resource usage family (`InvalidDataAccessResourceUsageException`). The two historical classes `DeadlockLoserDataAccessException` and `CannotSerializeTransactionException` also sit under `PessimisticLockingFailureException`, but have been **deprecated since Spring 6.0.3**; new code should handle `PessimisticLockingFailureException` or the appropriate specific branch.

The `transient` classification indicates the error **might** disappear on retry; it **does not prove retrying is business-safe**, does not prove the prior statement failed to commit, and does not replace retry-limit policies.

| Exception / group | Typical meaning | Initial action |
| --- | --- | --- |
| `CannotGetJdbcConnectionException` / `DataAccessResourceFailureException` | Failed to obtain connection, DB unavailable, pool/driver/configuration issue; belongs to Spring's **non-transient** branch | Check infrastructure, config, pool, and cause; consider recovery per dedicated policy |
| `TransientDataAccessResourceException` | Resource failed temporarily | Determine statement/transaction status, then consider bounded retry |
| `RecoverableDataAccessException` | Requires a recovery action (e.g. fresh connection) before retrying | Recover resource and **retry the entire transaction** if business-safe |
| `PessimisticLockingFailureException` / `CannotAcquireLockException` | Failed to acquire lock, deadlock, or lock contention error (depending on translator) | Roll back failed transaction, retry in a new transaction when appropriate |
| `OptimisticLockingFailureException` | Data changed since it was read (version/stale state) | Reload state and **recompute** the operation, or return conflict to the user |
| `QueryTimeoutException` | Query exceeded timeout / stopped by driver | Check query, locks, infrastructure; do not blindly retry writes |
| `DataIntegrityViolationException` / `DuplicateKeyException` | Duplicate key, bad FK, NOT NULL, CHECK... | Fix data or handle business condition; retrying as-is rarely helps |
| `BadSqlGrammarException` | Invalid SQL syntax, wrong table/column, incompatible SQL | Fix SQL/schema; do not retry |
| `PermissionDeniedDataAccessException` | Missing DB resource permissions | Fix permissions/policy; do not blindly retry |
| `UncategorizedDataAccessException` | Translator could not classify | Inspect cause/SQLState/vendor code and transaction state before deciding |

**Common trap:** `CannotGetJdbcConnectionException` **does not** extend `TransientDataAccessException`. It is a subclass of `DataAccessResourceFailureException` under the non-transient branch. Connectivity might return after 5 seconds, yet `catch (TransientDataAccessException e)` will not catch it by default. Conversely, `TransientDataAccessException` does not mean every `INSERT` can be re-run safely either.

## 3. Resource Errors: Distinguishing Missing Connections, Drops, Overload, and Misconfiguration

A "resource" may be a connection, connection pool, session, database endpoint, or query execution resource. Situations to distinguish:

1. **Unable to open a connection before starting a transaction**: DB is down, host unreachable, wrong credentials, wrong TLS, pool exhausted... You may see `CannotGetJdbcConnectionException` or a related error. If caused by a wrong password/URL, retrying 100 times helps nothing; if caused by a brief network glitch, waiting/health checks and sensible load limits are needed.
2. **Connection dropped mid-transaction**: the driver may throw another kind of `SQLException`; the transaction may have been aborted, yet for writes around the time of disconnect, the application must be cautious about uncertain commit outcomes. Relying on the exception class alone is usually insufficient.
3. **Connection pool exhausted**: too many requests hold connections too long, leaks, slow queries, lock waits, pool max-size too small, or insufficient DB capacity. If every request retries immediately, load spikes and the incident worsens.
4. **DB experiencing temporary recoverable issues**: retrying with a fresh connection can be considered, but add timeouts, backoff, jitter, and a circuit breaker/concurrency limit.

Diagnostic direction:

- Check datasource/pool/driver logs and timestamps; verify connection acquisition wait time, active/idle connections, pending pool requests, and DB max connections.
- Verify whether secrets, DNS, firewalls, TLS, database failover, or network policies changed.
- For errors during write transactions, distinguish **command not sent**, **command sent with no response**, and **commit outcome unknown**.
- Record the Spring class, SQLState/vendor code, and request/operation ID; avoid logging sensitive parameters directly.
- Set appropriate application-side timeouts and concurrency limits; retries do not replace fixing connection leaks or misconfigurations.

If write outcomes are **uncertain**, retries must be paired with idempotency, deduplication, or state reconciliation via business keys. See section 8.

## 4. Locking and Concurrent Access: Three Distinct Mechanisms

### 4.1. Pessimistic Locking: Actually Holding Locks in the Database

For example, two transactions both want to modify the row with key `account_id = 10`:

```sql
-- Inside a transaction on a DB supporting the corresponding syntax:
SELECT balance FROM accounts WHERE account_id = 10 FOR UPDATE;
-- Then UPDATE accounts ... and COMMIT.
```

One transaction may have to wait for the other to release its lock. If waiting too long, failing to acquire the lock, or forming a deadlock, the database may reject one transaction. Spring may translate that error into `PessimisticLockingFailureException` or `CannotAcquireLockException`, depending on driver and translator.

`SELECT ... FOR UPDATE` is not strictly portable across all databases. Syntax, lock timeouts, `NOWAIT`/`SKIP LOCKED` modes, isolation levels, and lock release timing depend on the DBMS.

**Deadlocks differ from ordinary lock waits:**

```text
Transaction A: holds lock on record X -> waiting for Y
Transaction B: holds lock on record Y -> waiting for X
                                         ^
                                         |
                             Unresolvable wait cycle
```

The database usually detects the deadlock and chooses one transaction as the "victim" to roll back/abort. In Spring/JDBC environments, do not check only for `DeadlockLoserDataAccessException`, as it is deprecated and mapping results vary by vendor. Handle the `PessimisticLockingFailureException` group when you actually have a lock-failure retry policy.

Reduce contention before thinking of retries: keep transactions short, acquire locks in a consistent order, index update predicates, avoid network I/O or long CPU work inside transactions, and lock only the rows genuinely needed.

### 4.2. Optimistic Locking: Checking Version on Write

Optimistic locking commonly uses a `version` or `row_version` column. Two actors read version 7 concurrently:

```text
T0: A reads version=7, B reads version=7
T1: A UPDATE ... WHERE version=7 -> 1 row, version becomes 8
T2: B UPDATE ... WHERE version=7 -> 0 rows (conflict)
T3: B reloads version=8 and decides whether to recompute or notify the user
```

An SQL pattern:

```sql
UPDATE inventory
SET quantity = ?, row_version = row_version + 1
WHERE sku = ? AND row_version = ?;
```

If the update count returns **0**, the row may have been modified or deleted; the application must check context before proceeding. **`JdbcTemplate.update(...)` only returns the affected row count; it does not automatically throw `OptimisticLockingFailureException` when the result is 0.** You can explicitly detect and throw the exception at the DAO layer. ORMs such as JPA/Hibernate or version-managing frameworks can detect conflicts automatically.

Retrying an optimistic conflict **differs** from retrying a lock timeout: you must not re-run the same `UPDATE ... WHERE version=7` forever. You must read the fresh state and recompute changes according to business rules; sometimes the user must decide when two edits target the same field.

### 4.3. Isolation / Serialization Conflict: Transactions Cannot Coexist Validly

At strong isolation levels like `SERIALIZABLE`, the database may reject a transaction when the concurrent execution schedule cannot be accepted under isolation guarantees. In PostgreSQL, SQLState `40001` typically indicates `serialization_failure`, though the exact Spring exception class depends on version/translator; catch the appropriate group and inspect the cause when needed.

Retrying in this scenario must usually re-run the **entire transaction**, including re-reading rows and making decisions from fresh data; re-running only the final `UPDATE` with stale data can still be wrong.

Isolation, locking, and optimistic versioning are related mechanisms, **not equivalents**. DB locks can block others, optimistic versions detect conflicts conditionally, and isolation governs data-visibility properties within transactions.

## 5. Retry Decision Rules

Before retrying, answer in order:

1. **Is it a potentially transient error?** Lock contention/deadlocks are reasonable candidates; bad SQL, missing schemas, or constraint-violating data normally require fixing the cause.
2. **Has the old transaction finished/rolled back?** Do not re-run SQL inside a transaction already marked rollback-only or in an aborted state. In PostgreSQL, an SQL error can render the current transaction unusable until rollback.
3. **Is the operation safe to re-execute?** A money transfer, event emission, email send, or inventory deduction can cause side effects if it partially or already committed. Idempotency keys, unique constraints, outbox, or deduplication are needed as appropriate.
4. **Does the retry re-read and recompute fresh state?** For optimistic conflicts and serialization failures, initial data may be stale.
5. **Are there strict bounds?** Choose max attempts, overall timeout, backoff with jitter, concurrency caps, and final failure handling.
6. **Does the user/system need to know about the conflict?** Never silently overwrite a user's decision just to force a request to succeed.

Decision matrix:

| Scenario | Retry? | Conditions |
| --- | --- | --- |
| Deadlock / lock acquisition failure | **Possibly** | After rollback, start a new transaction, bounded retry, keep operation safe |
| Serialization failure | **Possibly** | Retry the **entire transaction** with freshly read data |
| Optimistic version conflict | **Conditionally** | Can changes be merged? Reload and recompute; otherwise return conflict |
| Transient resource failure | **Conditionally** | DB health stabilized; commit status known or idempotency in place |
| Recoverable resource exception | **After recovery** | Obtain fresh connection / recover resource per guidance, then retry full transaction |
| Query timeout on write | **Cautiously** | Uncertain whether effect/commit happened; verify or require idempotency before trying |
| Cannot connect due to bad credentials/URL | **No** | Fix configuration/permissions |
| Duplicate unique key | **Do not retry as-is** | May be a business conflict or prior call's success; check by idempotency key |
| Bad SQL/column type/missing permissions | **No** | Fix program or permissions |
| Widespread database outage | **Minimize strictly** | Backoff/circuit breaker, stop adding load, monitor system recovery |

"Retry 3 times" must be clearly defined: **3 attempts total**, consisting of the initial call and at most 2 retries. Do not let an HTTP client retry 3 times, the service layer retry 3 times, and the driver retry 3 times uncoordinated, as total executions can multiply dramatically.

## 6. Retrying at the Right Transaction Boundary

### 6.1. Safe Sequence

```text
Attempt 1:
  BEGIN -> read data -> validate -> write -> lock failure -> ROLLBACK
      |
      v
  Evaluate exception -> backoff / jitter (no transaction held)
      |
      v
Attempt 2:
  New BEGIN -> reload data -> recompute -> write -> COMMIT
      |
      v
  Publish outcome only after successful commit.
```

**Do not catch an error inside a transaction and try to re-run on the same connection/transaction** when the database has aborted or marked the transaction failed. If code catches and swallows the exception, `@Transactional` might think the method succeeded; sometimes the transaction remains rollback-only and throws `UnexpectedRollbackException` at commit time.

Using `@Transactional` via a Spring proxy to place transactions at the service layer is standard practice. When combining retry annotations (`@Retryable`) with `@Transactional`, ensure the retry mechanism wraps **outside** the transaction boundary; advice/proxy ordering affects this. Do not rely on internal same-bean calls (`this.method()`) to trigger annotation proxies. When explicit control is needed, `TransactionTemplate` can put each attempt into an explicit transaction.

### 6.2. Lock-Failure Retry Code Pattern Using `TransactionTemplate`

The following Java 17 snippet illustrates a wrapper **bounded to three attempts**, catching only `PessimisticLockingFailureException`. This method is called when **no transaction is already open in the caller**; `TransactionTemplate` with default `REQUIRED` propagation then creates a new transaction on each invocation.

```java
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.transaction.support.TransactionTemplate;

static <T> T runWithLockRetry(
        TransactionTemplate tx,
        Supplier<T> databaseWork) {

    final int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            // All reads/calculations/writes in this attempt share one transaction.
            return tx.execute(status -> databaseWork.get());
        } catch (PessimisticLockingFailureException lockFailure) {
            // Spring already ended/rolled back the failed transaction before
            // tx.execute(...) threw the exception out.
            if (attempt == maxAttempts) {
                throw lockFailure;
            }

            // 40ms, 80ms + jitter 0..19ms.
            long delayMs = 40L * (1L << (attempt - 1))
                + ThreadLocalRandom.current().nextLong(20L);
            try {
                Thread.sleep(delayMs);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Retry interrupted", interrupted
                );
            }
        }
    }
    throw new IllegalStateException("Unreachable retry state");
}
```

This is a **code fragment to integrate into a Java class that already has `TransactionTemplate` and business logic**, not a standalone program. It does not retry `OptimisticLockingFailureException`, `QueryTimeoutException`, resource failures, `DuplicateKeyException`, or all `DataAccessException`s.

Service-layer call example:

```java
// Assumes tx, jdbc, and orderId are already configured.
// Method must be called outside an active transaction.
runWithLockRetry(tx, () -> {
    int quantity = jdbc.queryForObject(
        "SELECT quantity FROM inventory WHERE id = ?",
        Integer.class, orderId
    );
    // Check business conditions using the freshly read data,
    // then execute required SQL statements within the same transaction.
    return quantity;
});
```

The illustrative call above only reads data to show callback scope; in practice, put **all** related reads, validations, and writes inside `databaseWork`. Do not send emails or call non-rollback-capable APIs directly inside the callback: if retried, external side effects outside the DB may execute multiple times.

Another limitation: `Thread.sleep` blocks the current thread. This snippet is suited for explaining synchronous operations and very short delays, not a mandatory pattern for high-throughput or reactive systems. You can use a retry library such as Spring Retry with explicit exception policies, attempt counts, backoff/jitter, and transaction advice ordering; the key goal is **correct boundaries**, not hand-writing loops in every service.

## 7. Runnable Java 17+ Example: Optimistic Conflict and Reloading Before Retrying

The example below does not spawn two actual threads; it **intentionally lets two "writers" read the same snapshot** to reproduce a conflict deterministically, allowing exact observation of `JdbcTemplate`'s update count. An inventory row starts with `quantity = 10` and `row_version = 0`. Writer A adds 3, while Writer B intends to add 4 but read the stale version.

Structure:

```text
concurrency-demo/
├── build.gradle
└── src/main/java/OptimisticRetryDemo.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'OptimisticRetryDemo'
}
```

Contents of `src/main/java/OptimisticRetryDemo.java`:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class OptimisticRetryDemo {

    record StockSnapshot(int quantity, long version) {}

    static StockSnapshot load(JdbcTemplate jdbc) {
        return jdbc.queryForObject("""
            SELECT quantity, row_version FROM stock WHERE sku = ?
            """, (rs, rowNum) -> new StockSnapshot(
                rs.getInt("quantity"),
                rs.getLong("row_version")
            ), "BOOK");
    }

    static void addStock(JdbcTemplate jdbc,
                         StockSnapshot snapshot,
                         int amount) {
        int updated = jdbc.update("""
            UPDATE stock
            SET quantity = ?, row_version = row_version + 1
            WHERE sku = ? AND row_version = ?
            """,
            snapshot.quantity() + amount,
            "BOOK",
            snapshot.version()
        );

        if (updated != 1) {
            // JdbcTemplate.update returns row count; it does NOT automatically
            // throw OptimisticLockingFailureException when updated == 0.
            throw new OptimisticLockingFailureException(
                "The stock row changed since it was read"
            );
        }
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:concurrency_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute("""
            CREATE TABLE stock (
                sku VARCHAR(20) PRIMARY KEY,
                quantity INT NOT NULL,
                row_version BIGINT NOT NULL
            )
            """);
        jdbc.update(
            "INSERT INTO stock (sku, quantity, row_version) VALUES (?, ?, ?)",
            "BOOK", 10, 0L
        );

        // Both writers observe version=0.
        StockSnapshot writerA = load(jdbc);
        StockSnapshot writerB = load(jdbc);
        System.out.println(
            "Both read version: " + writerA.version()
        );

        addStock(jdbc, writerA, 3);
        System.out.println("Writer A: +3 applied");

        try {
            addStock(jdbc, writerB, 4);
        } catch (OptimisticLockingFailureException conflict) {
            System.out.println("Writer B attempt 1: conflict");
        }

        // Retry only after reloading the new version and quantity.
        StockSnapshot fresh = load(jdbc);
        addStock(jdbc, fresh, 4);
        System.out.println("Writer B attempt 2: +4 applied");

        StockSnapshot result = load(jdbc);
        System.out.println(
            "Final: quantity=" + result.quantity()
            + ", version=" + result.version()
        );
    }
}
```

Run from the `concurrency-demo` directory using an installed Gradle:

```bash
gradle --quiet run
```

If the project has its own Gradle Wrapper, use `./gradlew --quiet run` (Windows: `.\gradlew.bat --quiet run`). With fixed data and in-memory H2, program stdout is:

```text
Both read version: 0
Writer A: +3 applied
Writer B attempt 1: conflict
Writer B attempt 2: +4 applied
Final: quantity=17, version=2
```

**Why is the result 17?** Writer A reads 10/version 0 and updates to 13/version 1. Writer B uses stale snapshot 10/version 0; `WHERE row_version = 0` no longer matches, so `updated = 0` and **no wrong +4 update is written to the database**. B reloads 13/version 1, computes 13+4, and updates to 17/version 2.

Three takeaways from the example:

- The Spring exception class only appears because the **DAO explicitly throws** it after observing `updated != 1`; `JdbcTemplate` has no way of knowing business logic expects `row_version`.
- Contention in this example is simulated with a **stale snapshot**, not a real lock timeout or deadlock. Do not use this result to draw conclusions about locking levels or timing on another database.
- For adding quantities, the addition can be re-applied after a fresh read. If two users edit the same "shipping address", automatically picking a new value to overwrite is usually wrong; return a conflict so the user decides.

In production applications, multi-step operations like reading, checking stock, updating, and writing audit logs need proper transactions. This console example focuses on illustrating **version matching and stale-read handling**; each standalone `UPDATE` is an atomic SQL operation in H2's autocommit mode.

## 8. Retry and Idempotency When Write Outcome Is Uncertain

A dangerous situation:

```text
Client sends order-creation command to DB
  -> DB creates order, possibly already committed
  -> network drops before client receives response
  -> client assumes failure and resends
  -> may create a second order
```

In this case, simply classifying the exception as transient is **not enough**. We must make repeated requests able to determine the outcome.

A common design:

```sql
CREATE TABLE payment_request (
    request_key VARCHAR(100) PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

`request_key` is assigned by the application for **one single logical operation** and reused across retries. The unique/primary-key constraint prevents the DB from storing two rows with the same key. However, **duplicate key does not always mean success**: the application must verify the stored record has the same payload/destination and a valid status before returning the old result. If the same key has a different payload, reject it.

For money transfers:

- Choose a stable request key, unique constraint, transactional DB operations, and status checks.
- If no write response arrives, **query by the request key** to determine whether it was already processed; if querying is not yet possible, follow a controlled recovery workflow.
- If emitting events to a message broker/email after DB writes, consider a transactional outbox or consumer-side deduplication. Do not re-emit events directly inside a retryable callback without deduplication guarantees.
- Return a clear status when the outcome remains uncertain; never pretend the whole transaction definitely rolled back merely because the client timed out.

Idempotency is not just "adding a unique index": it encompasses **operation key, parameter verification, state storage, and how responses are returned** for a repeatedly submitted request.

## 9. Testing Practices for Lock Errors and Retries

Integration tests should use the same driver and database engine as production when measuring real lock behavior. H2 works well for the version example in section 7, but does not guarantee matching PostgreSQL, MySQL, or SQL Server on deadlocks, timeouts, SQLStates, or translation.

| Test scenario | How to set up | What to verify |
| --- | --- | --- |
| Optimistic conflict | Read the same `row_version` on two threads/objects, update sequentially | Second writer updates 0 rows, code detects conflict, no lost update |
| Lock timeout | Connection/transaction A holds lock, B tries to lock with finite timeout | Actual exception type, B rolls back, failed transaction is not retained |
| Deadlock | Two transactions lock two rows in opposite orders | Database aborts one transaction; retry succeeds if starting a new transaction |
| Serialization failure | Transactions at suitable isolation level accessing conflicting rows | Retries read/compute/write of the full transaction, not just the last statement |
| Connection lost before query | Stop DB / cut network or use suitable test harness | Does not retry infinitely, proper error reporting, backoff applied |
| Connection lost around commit | Inject network fault at final transaction step | No duplicate data after retry; idempotency key handles unknown state |
| Bad data (unique/FK/NOT NULL) | Write record violating constraint | Does not retry permanent error; returns business error or fixes input |
| Attempts exhausted | Simulate lock error on every attempt | Exact attempt count, final exception propagated, not swallowed |
| Interrupted during backoff | Interrupt waiting thread | Interrupt flag restored, retry stops |
| External side effects | Callback sends message / calls API | No duplicate emissions; uses outbox or equivalent |

Do not build tests relying on `Thread.sleep(100)` to "hope" two transactions contend. Use deterministic synchronization (e.g., `CountDownLatch`), two genuinely independent connections, timeouts, and final DB state assertions. For deadlocks, lock ordering, isolation, and timeout strategies must reflect the target database.

## 10. Observability and Operations When Errors Recur

Beyond exception handling, production apps need metrics to know whether retries are saving the system or making incidents worse:

- **Attempts per operation**, retry count, total duration, and final outcome; separate "initial calls" from "retry attempts".
- **Causes** by Spring class, SQLState/vendor code, logical operation, and database group; avoid exposing passwords, tokens, personal info, or full sensitive payloads.
- **Pool metrics**: active/idle/pending connections, acquisition timeouts, leak detection, DB max connections.
- **Lock metrics**: transaction duration, lock waits, deadlock count, statement timeouts, and rolled-back transaction count.
- **Bounds**: max attempts, overall deadline, jitter, bounded concurrency/circuit breaker for resource outages.

Final error reporting should include business context and `cause`, without returning stack traces or sensitive SQL directly to clients. Conflicts from concurrent user updates can be represented as HTTP `409 Conflict` when the API contract specifies it; DB unavailability is usually a temporary infrastructure failure requiring appropriate responses while avoiding claims that a command was canceled if commit status is unknown.

## 11. Typical Mistakes

**Mistake 1: retrying every `DataAccessException`.** Invalid SQL, duplicate unique keys, missing permissions, and schema errors do not vanish on their own. Blind retries add load, hide real bugs, and can duplicate side effects.

**Mistake 2: catching only `TransientDataAccessException` and assuming all DB loss errors are handled.** `CannotGetJdbcConnectionException` belongs to the **non-transient** branch. Practical recoverability must be evaluated independently of the class hierarchy.

**Mistake 3: retrying inside the same failed transaction.** The transaction may be rollback-only or the DB may reject further statements. Let the old transaction finish, then start a new transaction for the next attempt.

**Mistake 4: retrying an optimistic conflict without reloading.** The stale version will keep mismatching. For business logic needing conflict reconciliation, reload, recompute, or return a conflict.

**Mistake 5: holding locks while keeping transactions open too long.** Calling external APIs, running heavy jobs, or sleeping for backoff while holding locks increases contention; shorten lock hold times and move delays **outside the transaction**.

**Mistake 6: putting `@Transactional` or `@Retryable` on internal same-bean calls and expecting the proxy to run.** In standard proxy setups, self-invocation bypasses the proxy; verify how AOP advice is applied, or use `TransactionTemplate` for clarity.

**Mistake 7: assuming a timeout guarantees rollback.** The client may have lost connectivity after the DB committed. For non-idempotent requests, verify state or enforce deduplication keys before retrying.

**Mistake 8: treating "deadlock" as an unretryable code bug.** Deadlocks can be transient contention states where the database picks a victim. Bounded retries with new transactions can help, while fixing lock acquisition ordering reduces frequency.

**Mistake 9: failing to prevent retry storms.** During a DB outage, thousands of requests retrying immediately exhaust pools and prolong recovery. Use backoff with jitter, attempt caps, and system health monitoring.

**Mistake 10: assuming all databases map lock errors identically.** SQLState, vendor error codes, driver classes, and Spring translators differ. Write integration tests against the production vendor and record actual exceptions instead of hardcoding guesses.

## 12. Self-Assessment Questions

**Question 1.** `JdbcTemplate.update(...)` returns 0 when updating `WHERE id=? AND row_version=?`. Does it automatically throw `OptimisticLockingFailureException`?

**Answer:** No. JDBC returns the update count; the DAO/ORM layer must know the expectation and detect conflicts. With manual JDBC, you can check `updated == 0` and throw `OptimisticLockingFailureException` or return an appropriate conflict result.

**Question 2.** Does `CannotGetJdbcConnectionException` belong to `TransientDataAccessException`?

**Answer:** No. It belongs to `DataAccessResourceFailureException` under the non-transient branch. That does not claim the real-world outage will last forever; analyze the cause and recovery strategy separately.

**Question 3.** A transaction hits a deadlock after reading a balance, computing a fee, and updating. Should you re-run just the final `UPDATE` or the entire transaction?

**Answer:** Retry the **entire transaction** starting from reading fresh state, after the old transaction rolls back, with attempt limits/backoff. Calculations that depended on stale data must also be re-run.

**Question 4.** A "create payment" request loses connection after sending SQL. Can you call it again immediately assuming the first attempt failed?

**Answer:** No. The commit status may be uncertain. You need an idempotency key, status verification, or appropriate recovery/deduplication mechanism.

**Question 5.** Two users edit the same shipping address. One updates first, making the other's version stale. Should you automatically reload and overwrite with the second address?

**Answer:** Usually no. Return a conflict or show the diff for the user to decide; automatic retry is appropriate only when the transformation and merge rules are genuinely safe.

**Question 6.** Why must backoff be placed outside the transaction?

**Answer:** Because waiting inside a transaction can keep holding connections/locks and prolong contention. Roll back/close the old transaction first, then wait, then open a new transaction.

## 13. Key Takeaways

- `DataAccessException` is the root of Spring's data access exception hierarchy; `JdbcTemplate` translates `SQLException`, though exact mappings depend on driver/translator.
- **Resource errors**, **pessimistic locks**, **optimistic conflicts**, and **permanent data errors** have different causes and handling policies.
- `PessimisticLockingFailureException` is the right branch for catching many locking failures; the two older deadlock/serialization classes were deprecated in Spring 6.0.3.
- `CannotGetJdbcConnectionException` belongs to the **non-transient** branch. An infrastructure failure may recover, but recoverability must not be equated with safe retryability.
- For eligible lock/serialization failures, retry in a **new transaction**, starting from reads and computations, with backoff/jitter and max attempts.
- For optimistic locking, detect update count 0 or ORM exceptions, **reload and reconcile data**; do not silently overwrite user decisions.
- Every retry of a write operation must account for **uncertain rollback/commit status, idempotency, and external side effects**. Retry mechanisms must be bounded and observable.

### References

- Spring Framework — [JDBC Core and `SQLExceptionTranslator`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- Spring Framework 6.2 — [`DataAccessException` and subclasses](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataAccessException.html).
- Spring Framework 6.2 — [`TransientDataAccessException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/TransientDataAccessException.html).
- Spring Framework 6.2 — [`DataAccessResourceFailureException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/DataAccessResourceFailureException.html).
- Spring Framework 6.2 — [`PessimisticLockingFailureException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/PessimisticLockingFailureException.html).
- Spring Framework 6.2 — [`OptimisticLockingFailureException`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/dao/OptimisticLockingFailureException.html).
- Spring Framework — [`@Transactional` and default rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Retry — [Reference Documentation](https://docs.spring.io/spring-retry/reference/).
