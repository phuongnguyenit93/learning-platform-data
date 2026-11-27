# Lock Timeouts, Deadlocks, and Database-Specific Differences

## 1. Objectives

When multiple transactions access the same row concurrently, the database may force one transaction to wait for a lock. If transactions wait on each other in a cycle, the database detects a deadlock and aborts one transaction to free resources. Wait times, rollback scopes, and error reporting differ across PostgreSQL, MySQL/InnoDB, SQL Server, Oracle, and H2.

This lesson shows you how to:
- Distinguish lock wait timeout, transaction timeout, query timeout, and connection pool timeout.
- Use `@Lock(PESSIMISTIC_WRITE)` to lock a row within a transaction.
- Configure lock timeouts using a JPA hint or database-specific settings.
- Reproduce a lock wait using two independent transactions.
- Create a controlled deadlock with two transactions locking two rows in opposite orders.
- Identify errors by Spring exception, SQLState, and vendor error code.
- Choose a safe retry strategy after a deadlock or serialization failure.
- Understand important database differences and why testing on the production engine is necessary.

## 2. Distinguishing timeout types and deadlocks

These failures can all appear as slow-running requests, yet their causes and handling differ:

| Concept | What is it waiting for? | Example |
| --- | --- | --- |
| Lock wait timeout | Waiting for another transaction to release a lock on a row or resource. | Transaction A holds `SELECT ... FOR UPDATE`, transaction B wants to lock the same row. |
| Transaction timeout | Limit on how long a transaction is allowed to remain active per transaction manager/provider settings. | A service transaction exceeds its allowed duration. |
| Query/statement timeout | Limit on the execution time of an SQL/JPA query. | A SELECT runs too long or is blocked by a lock. |
| Connection pool timeout | Waiting for an idle connection from the application's pool. | HikariCP has no available connections left. |
| Deadlock | Transactions wait in a cycle for resources held by one another. | A holds row 1 and waits for row 2; B holds row 2 and waits for row 1. |

A lock wait timeout occurs when a single wait exceeds its limit. A deadlock is a wait cycle; the database typically detects it and picks a victim transaction without waiting for the lock timeout to expire.

`@Transactional(timeout = 5)` is not guaranteed to mean database `lock_timeout = 5 seconds`. Transaction timeout, query timeout, and lock timeout may pass through different layers; the provider or database may not apply them identically.

Connection pool timeout happens before any SQL is sent to the database. If the application fails to obtain a connection, no lock request is ever created. Read the exception and connection pool metrics to distinguish this case.

## 3. Pessimistic locking in Spring Data JPA

JPA provides lock modes to ask the database to protect data inside a transaction. For read-then-update operations, `PESSIMISTIC_WRITE` is commonly used to lock the row before making changes.

Repository:

```java
package com.example.inventory;

import java.util.Optional;
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository extends JpaRepository<Inventory, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdate(@Param("id") Long id);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints(@QueryHint(
            name = "jakarta.persistence.lock.timeout",
            value = "2000"))
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdateWithHint(@Param("id") Long id);
}
```

`@Lock` is in `org.springframework.data.jpa.repository.Lock`; Spring Data JPA's `@QueryHints` accepts `jakarta.persistence.QueryHint` entries. The `jakarta.persistence.lock.timeout` hint uses milliseconds per JPA. The provider/database may ignore or map the hint in its own way, so you must verify it with integration tests against the actual database.

JPA locks require an active transaction. Calling a lock-acquiring method outside a transaction can lead to `TransactionRequiredException` or inappropriate behavior. Keep lock acquisition, reading, and updating within the same transaction.

## 4. Example Entity and Service

The examples use Java 17+, Spring Boot 3.x, Spring Data JPA, and Hibernate managed by Spring Boot. The `Inventory` entity tracks available stock and has a domain method validating quantity before deducting.

`src/main/java/com/example/inventory/Inventory.java`:

```java
package com.example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory")
public class Inventory {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int available;

    protected Inventory() {
        // JPA requires a no-arg constructor.
    }

    public Inventory(int available) {
        if (available < 0) {
            throw new IllegalArgumentException("Available cannot be negative");
        }
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("Insufficient inventory");
        }
        available -= quantity;
    }

    public Long getId() { return id; }
    public int getAvailable() { return available; }
}
```

The service places the transaction boundary around locking and updating:

`src/main/java/com/example/inventory/InventoryService.java`:

```java
package com.example.inventory;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional(timeout = 10)
    public void reserve(Long id, int quantity) {
        Inventory item = repository.findForUpdate(id)
                .orElseThrow(() -> new IllegalArgumentException("Inventory not found"));
        item.reserve(quantity);
    }
}
```

`@Transactional(timeout = 10)` is a transaction timeout in seconds via Spring's transaction abstraction. It does not replace the database's own lock wait timeout configuration. This example service holds the lock until the transaction commits or rolls back; do not call HTTP APIs, send emails, or wait for user input during that time.

## 5. Configuring lock timeout with a JPA hint

JPA defines the hint:

```text
jakarta.persistence.lock.timeout
```

The example above sets the value `2000`, corresponding to a 2,000-millisecond timeout request. You can apply the hint to queries annotated with `@Lock` using Spring Data `@QueryHints`.

Distinguish the following scenarios:

- The provider supports the hint and the database can enforce it: the locking statement is emitted with the corresponding timeout.
- The provider does not support it or the database has no equivalent mapping: the hint may be ignored.
- The database enforces a session/transaction-level timeout limit: vendor configuration may dictate the final outcome.

Do not conclude that the timeout works just because the annotation compiles. Hold a lock on a row in one transaction, issue the query from a second transaction, and verify that the second query fails with a timeout error within the expected interval.

## 6. Database-specific timeout configuration

There is no single SQL timeout syntax that works across every engine. The following examples are common settings; exact syntax, required privileges, and scope also depend on the database version and configuration.

| Database | Lock wait timeout / how to request | Deadlock typically identified by |
| --- | --- | --- |
| PostgreSQL | `SET LOCAL lock_timeout = '2s'`; `NOWAIT` or `SKIP LOCKED` on locking SELECTs. | SQLState `40P01`. |
| MySQL InnoDB | `innodb_lock_wait_timeout` in seconds; locking reads support `NOWAIT`/`SKIP LOCKED` on supported versions. | Error 1213, SQLState usually `40001`. |
| SQL Server | `SET LOCK_TIMEOUT 2000` in milliseconds; has specific lock hints. | Error 1205 is deadlock victim; error 1222 is lock request timeout. |
| Oracle | `SELECT ... FOR UPDATE WAIT n`, `NOWAIT`, or `SKIP LOCKED`. | `ORA-00060`; resource busy is usually `ORA-00054`. |
| H2 | Has `LOCK_TIMEOUT` in milliseconds and H2-specific locking syntax. | H2 behavior and error codes; does not fully represent production engines. |

### 6.1. PostgreSQL

Inside a PostgreSQL transaction, you can set a lock wait limit for the current transaction:

```sql
SET LOCAL lock_timeout = '2s';
```

`SET LOCAL` expires when the transaction ends. PostgreSQL also has `statement_timeout`, which limits overall statement execution time. `lock_timeout` applies only to waiting for locks; if `statement_timeout` is shorter, the statement may be canceled earlier.

A locking read can use:

```sql
SELECT id, available
FROM inventory
WHERE id = 10
FOR UPDATE NOWAIT;
```

`NOWAIT` errors immediately if the lock cannot be acquired. `SKIP LOCKED` skips rows that are currently locked, which is often useful for workers polling jobs from a queue. It is unsuitable if the caller needs a complete and consistent read result.

PostgreSQL uses SQLState `55P03` for lock not available, covering certain `NOWAIT`/lock timeout cases; deadlocks have SQLState `40P01`. A statement error puts a PostgreSQL transaction into an aborted state until it is rolled back or rolled back to a savepoint.

### 6.2. MySQL with InnoDB

InnoDB uses `innodb_lock_wait_timeout` to limit record lock waiting. The value is usually in seconds and can be configured at server or session level depending on privileges/version:

```sql
SET SESSION innodb_lock_wait_timeout = 2;
```

Locking read:

```sql
SELECT id, available
FROM inventory
WHERE id = 10
FOR UPDATE NOWAIT;
```

MySQL 8.0 supports `NOWAIT` and `SKIP LOCKED` for locking reads on InnoDB. Verify the exact version and storage engine in use.

InnoDB deadlocks typically return error 1213 with SQLState `40001`; lock wait timeouts typically return error 1205. By default, a deadlock causes InnoDB to roll back the entire victim transaction. A lock wait timeout usually rolls back only the timed-out statement; `innodb_rollback_on_timeout` can change transaction rollback behavior. After a timeout error, the application should decide to roll back the current transaction and not continue using transaction state unless certain it remains valid.

InnoDB may use record locks, gap locks, and next-key locks depending on isolation level, indexes, and query predicates. Missing appropriate indexes can cause queries to scan/lock more records or ranges than expected.

### 6.3. SQL Server

SQL Server allows setting lock wait timeout per session:

```sql
SET LOCK_TIMEOUT 2000;
```

The value is in milliseconds. `-1` typically indicates waiting indefinitely and `0` means no wait. Session settings can persist when a connection returns to a pool; if modified via SQL, reset properly or manage via connection pool configuration so subsequent requests are unaffected.

SQL Server has lock hints such as `UPDLOCK`, `ROWLOCK`, and `READPAST`, but they carry specific semantics and should not be added arbitrarily. `ROWLOCK` is a hint; the engine can still choose a different lock granularity or perform lock escalation.

Error 1205 indicates the transaction was chosen as a deadlock victim. Error 1222 indicates a lock request timeout. Distinguish these two errors to choose appropriate retry or business responses.

### 6.4. Oracle

Oracle lets you specify wait time directly in a locking SELECT:

```sql
SELECT id, available
FROM inventory
WHERE id = 10
FOR UPDATE WAIT 2;
```

`WAIT 2` requests waiting at most 2 seconds; `NOWAIT` errors immediately; `SKIP LOCKED` skips currently locked rows, commonly used in queue processing. `ORA-00054` typically indicates resource busy / unable to acquire lock as requested; `ORA-00060` reports a deadlock.

Whether JPA lock hints map to these options depends on the Hibernate dialect and driver. When Oracle-specific syntax is required, you can use native queries or JDBC in a dedicated repository, but test on Oracle.

### 6.5. H2

H2 supports configuring `LOCK_TIMEOUT` in the test URL:

```properties
spring.datasource.url=jdbc:h2:mem:lockdb;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=2000
```

This is convenient for lightweight tests. H2 does not fully replicate the lock granularity, deadlock detector, isolation, error codes, or timeouts of PostgreSQL/MySQL/SQL Server/Oracle. Passing H2 tests does not prove the production database will behave identically.

## 7. How does a deadlock form?

A deadlock requires a wait cycle. Example of two transactions updating two rows:

```text
Transaction A                 Transaction B
-------------                 -------------
LOCK inventory 1              LOCK inventory 2
WAIT inventory 2              WAIT inventory 1
       |                              |
       +---------- DEADLOCK -----------+
```

A holds row 1 and waits for row 2. B holds row 2 and waits for row 1. Neither transaction can proceed unless one transaction is aborted.

The database monitors the lock graph and chooses one transaction as the victim. Victim selection depends on the engine, rollback cost, priority, and system state; do not rely on assuming the transaction that started later is always aborted.

Deadlock differs from lock timeout: the deadlock detector identifies a wait cycle; a lock timeout simply terminates a wait that exceeded its threshold. A transaction can be aborted due to deadlock before the lock timeout expires.

## 8. Why does lock ordering matter?

Suppose every money-transfer flow locks accounts in ascending ID order. When two transfer requests operate between the same two accounts in opposite directions, both still acquire locks in the same order.

```java
List<Long> ids = Stream.of(sourceId, targetId)
        .sorted()
        .toList();

List<Account> accounts = repository.findAllForUpdate(ids);
```

A stable lock-ordering rule reduces the chance of creating a wait cycle. The repository may need a query with `IN` and `ORDER BY id`; verify that the database actually locks in the desired order via SQL and execution plans. Do not assume the order in a Java collection dictates database lock order.

Measures to reduce deadlocks:

- Lock multiple rows in the same order across all code paths.
- Keep transactions short and avoid network operations while holding locks.
- Add indexes for filter conditions to reduce the number of records scanned/locked.
- Lock only the rows that are needed.
- Avoid raising isolation levels unnecessarily if the business logic does not require it.
- Never hold locks while waiting for user input or another job.
- Retry deadlocked transactions when the operation is safe to re-run.

## 9. Testing lock wait timeout on PostgreSQL

The test below uses two independent transactions:

1. Transaction A locks an Inventory row and holds the lock.
2. Transaction B sets a short `lock_timeout` within its own transaction.
3. B requests a lock on the same row and receives SQLState `55P03`.
4. A releases the lock and commits.
5. The test re-reads the data in a new transaction.

The example requires `spring-boot-starter-data-jpa`, the PostgreSQL JDBC driver, `spring-boot-starter-test`, `org.testcontainers:junit-jupiter`, and `org.testcontainers:postgresql` in test scope.

`src/test/java/com/example/inventory/PostgreSqlLockTimeoutTest.java`:

```java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.SQLException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.open-in-view=false"
})
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class PostgreSqlLockTimeoutTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name", postgres::getDriverClassName);
    }

    @Autowired
    private InventoryRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private TransactionTemplate transactions;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        transactions.executeWithoutResult(status -> repository.deleteAllInBatch());
    }

    private Long createInventory() {
        return transactions.execute(status ->
                repository.saveAndFlush(new Inventory(10)).getId());
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for test coordination");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Test interrupted", ex);
        }
    }

    private static boolean hasSqlState(Throwable error, String expected) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            if (current instanceof SQLException sql
                    && expected.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }

    @Test
    void secondTransactionTimesOutWhileFirstHoldsTheRowLock() throws Exception {
        Long id = createInventory();
        CountDownLatch firstHasLock = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> holder = pool.submit(() -> transactions.executeWithoutResult(status -> {
                repository.findForUpdate(id).orElseThrow();
                firstHasLock.countDown();
                await(releaseFirst);
            }));

            assertThat(firstHasLock.await(10, TimeUnit.SECONDS)).isTrue();

            Future<Throwable> contender = pool.submit(() -> {
                try {
                    transactions.executeWithoutResult(status -> {
                        jdbcTemplate.execute("SET LOCAL lock_timeout = '300ms'");
                        repository.findForUpdate(id).orElseThrow();
                    });
                    return null;
                } catch (RuntimeException ex) {
                    return ex;
                }
            });

            Throwable failure = contender.get(5, TimeUnit.SECONDS);
            assertThat(failure).isNotNull();
            assertThat(hasSqlState(failure, "55P03")).isTrue();

            releaseFirst.countDown();
            holder.get(10, TimeUnit.SECONDS);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }

        int available = transactions.execute(status ->
                repository.findById(id).orElseThrow().getAvailable());
        assertThat(available).isEqualTo(10);
    }
}
```

`SET LOCAL` and the JPA Repository must participate in the same transaction and share the same DataSource to use the same connection. Spring-managed `JdbcTemplate` joins the current transaction when it uses the same DataSource as `JpaTransactionManager`.

The test does not catch the exception inside the transaction callback; the exception propagates outside `TransactionTemplate`, causing transaction B to roll back. Afterward, the test checks the error's SQLState and re-reads the data in a new transaction.

Run the test:

```bash
mvn test
```

The expected outcome is that Maven finishes with `BUILD SUCCESS` and the test verifies transaction B times out while A holds the lock. This is the expected result of the example, not a build log already executed in an actual environment.

## 10. Testing deadlock with two transactions

To create a controlled deadlock, you need two rows and two independent transactions:

- Transaction A locks row 1, then waits for row 2.
- Transaction B locks row 2, then waits for row 1.
- Latches ensure both hold their first lock before either requests the second lock.

Helper example for integration testing on PostgreSQL:

```java
private String lockTwoRowsInOppositeOrder(
        Long firstId, Long secondId,
        CountDownLatch bothHoldFirst, CountDownLatch continueToSecond) {
    try {
        transactions.executeWithoutResult(status -> {
            repository.findForUpdate(firstId).orElseThrow().reserve(1);
            repository.flush();
            bothHoldFirst.countDown();
            await(continueToSecond);
            repository.findForUpdate(secondId).orElseThrow().reserve(1);
            repository.flush();
        });
        return "COMMITTED";
    } catch (RuntimeException ex) {
        if (hasSqlState(ex, "40P01")) {
            return "DEADLOCK";
        }
        throw ex;
    }
}
```

In the test method, create two Inventory rows with available equal to 10, then run two calls in opposite orders:

```java
CountDownLatch bothHoldFirst = new CountDownLatch(2);
CountDownLatch continueToSecond = new CountDownLatch(1);
ExecutorService pool = Executors.newFixedThreadPool(2);

try {
    Future<String> first = pool.submit(() -> lockTwoRowsInOppositeOrder(
            firstId, secondId, bothHoldFirst, continueToSecond));
    Future<String> second = pool.submit(() -> lockTwoRowsInOppositeOrder(
            secondId, firstId, bothHoldFirst, continueToSecond));

    assertThat(bothHoldFirst.await(10, TimeUnit.SECONDS)).isTrue();
    continueToSecond.countDown();

    assertThat(List.of(first.get(10, TimeUnit.SECONDS),
            second.get(10, TimeUnit.SECONDS)))
            .containsExactlyInAnyOrder("COMMITTED", "DEADLOCK");
} finally {
    continueToSecond.countDown();
    pool.shutdownNow();
}
```

The database detects the wait cycle and aborts one transaction. The other transaction proceeds, acquires the lock, and commits. Because each transaction decremented one row before requesting the second lock, the total quantity after the test must be 19 rather than 20: only the committed transaction's changes are kept. Re-read both rows in a new transaction to verify the victim transaction rolled back.

This deadlock example depends on the engine and deadlock detector. On PostgreSQL, check SQLState `40P01`; with MySQL InnoDB, check error 1213/SQLState `40001`. Adjust the error code for the database under test. When running on CI, use generous timeouts and always release latches in `finally` so threads do not hang when an assertion fails.

## 11. Retrying after deadlock or serialization failure

Deadlocks are usually transient errors that can be retried. However, a retry must re-execute the entire transaction because the transaction chosen as the database victim has already rolled back or no longer has valid state.

Safety rules:

1. Retry only errors identified as transient, such as deadlocks or serialization failures by SQLState/vendor code.
2. End the failed transaction before retrying; each attempt must get a new transaction.
3. Limit the number of attempts, e.g., at most 2–3 times, with exponential backoff and jitter.
4. Ensure operations are idempotent or use an idempotency key so duplicate side effects are not created.
5. Do not retry validation errors, missing data, business constraint violations, or permission errors.
6. Record metrics/logs for retry counts and final errors to spot persistent contention.

Do not re-execute repository statements inside a transaction already marked rollback-only. A clean approach is placing the retry in a facade bean outside the `@Transactional` bean, so each call to the worker creates a new transaction. Verify AOP ordering between the retry aspect and the transaction interceptor.

Example structure:

```java
@Service
public class InventoryRetryFacade {
    private final InventoryTransactionalWorker worker;

    public InventoryRetryFacade(InventoryTransactionalWorker worker) {
        this.worker = worker;
    }

    public void reserveWithRetry(Long id, int quantity) {
        int maxAttempts = 3;
        for (int attempt = 1; ; attempt++) {
            try {
                worker.reserveInNewTransaction(id, quantity);
                return;
            } catch (PessimisticLockingFailureException ex) {
                if (attempt >= maxAttempts) {
                    throw ex;
                }
                backoff(attempt);
            }
        }
    }

    private void backoff(int attempt) {
        long baseMillis = 50L * (1L << (attempt - 1));
        long jitter = java.util.concurrent.ThreadLocalRandom.current()
                .nextLong(25L);
        try {
            Thread.sleep(baseMillis + jitter);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Retry interrupted", ex);
        }
    }
}

@Service
class InventoryTransactionalWorker {
    private final InventoryRepository repository;

    InventoryTransactionalWorker(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void reserveInNewTransaction(Long id, int quantity) {
        Inventory item = repository.findForUpdate(id).orElseThrow();
        item.reserve(quantity);
    }
}
```

This is an illustrative skeleton. In real applications, retry only exceptions classified as deadlock/transient; `PessimisticLockingFailureException` can cover several kinds of locking errors. If the operation sends emails, calls a payment provider, or publishes messages, use an outbox/idempotency so side effects do not repeat when a transaction retries.

## 12. Factors that prolong lock waits

Long lock waits are often caused by more than just high request volume. Check the following factors:

- Transactions hold locks too long because they perform extensive work after reading.
- Queries lack indexes and scan many rows before acquiring locks.
- Two code paths lock multiple rows in different orders.
- Transactions span multiple unnecessary Repository calls or services.
- A batch update/delete holds locks across many rows.
- Isolation levels or gap/next-key locking widen the lock scope beyond expectations.
- Connection pool exhaustion forces other requests to wait for a connection before even reaching the database.
- A transaction hangs or a client disconnects while the connection/transaction is not yet released.

SQL logs show which query is running; database lock monitoring shows which session is blocking which. When investigating production incidents, collect queries, transaction ages, lock wait events, blocking sessions, and connection pool metrics together.

## 13. Differences in rollback scope

Do not assume every database rolls back the same scope on timeout:

| Engine | Lock timeout / deadlock | Rollback scope to watch out for |
| --- | --- | --- |
| PostgreSQL | Lock timeout typically fails the statement; deadlock detector aborts one transaction. | After an SQL error, the transaction usually enters an aborted state and must roll back completely or to a savepoint. |
| MySQL InnoDB | Lock wait timeout and deadlock have distinct error codes. | Deadlock rolls back the victim transaction; lock wait timeout by default usually rolls back only the statement, unless `innodb_rollback_on_timeout` changes the behavior. |
| SQL Server | Lock timeout and deadlock victim have distinct error codes. | Deadlock victim transaction is rolled back; lock timeout usually cancels the statement, while remaining transaction state depends on configuration and context. |
| Oracle | Supports `WAIT`, `NOWAIT`, `SKIP LOCKED`; deadlock reports `ORA-00060`. | Deadlock typically rolls back the statement causing the deadlock; the application must handle transaction state according to the actual error. |
| H2 | Has a simple lock timeout for tests. | Use for basic testing; do not extrapolate rollback semantics to other engines. |

Across all engines, after a lock error let the transaction boundary handle rollback cleanly. Do not catch the exception and continue operating in the same transaction without understanding the transaction and provider state.

## 14. NOWAIT and SKIP LOCKED

`NOWAIT` and `SKIP LOCKED` serve two different purposes:

| Option | Behavior | Use case |
| --- | --- | --- |
| `NOWAIT` | Do not wait if the row is locked; error immediately. | APIs needing fast failure when a resource is busy. |
| `SKIP LOCKED` | Skip locked rows and continue fetching other rows. | Multiple worker instances pulling jobs from a queue. |

PostgreSQL-style SQL example:

```sql
SELECT id, status
FROM job
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 20;
```

Multiple workers can claim different groups of jobs without waiting on each other. However, `SKIP LOCKED` produces an incomplete view at query time because locked rows are skipped. Do not use it for search screens or reports requiring a complete result set.

Whether `NOWAIT`/`SKIP LOCKED` can be expressed via JPA lock timeout or Hibernate hints depends on the dialect. If exact SQL must be guaranteed, use a controlled native query and integration tests on the target database.

## 15. Testing on a real database

H2 is suitable for fast Repository tests, but is insufficient to verify:

- Deadlock detector and victim selection.
- Lock timeout error codes/SQLState.
- Gap/next-key locks, lock escalation, and row/page locks.
- `NOWAIT`, `SKIP LOCKED`, and vendor syntax.
- Rollback scope after a lock wait timeout.
- Impact of indexes and isolation levels on the lock graph.

If the application runs on PostgreSQL, MySQL, SQL Server, or Oracle, add integration tests with Testcontainers or a corresponding dedicated database environment. Use a version close to production and the same schema/indexes/migrations so results are meaningful.

Do not assert only a generic exception class. When needing to distinguish timeouts and deadlocks, inspect SQLState or vendor error codes in the cause chain, and check the data after the transaction ends.

## 16. Common mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `@Transactional(timeout=...)` does not limit lock wait time as expected | Transaction timeout is not equivalent to database lock timeout. | Use a JPA lock hint or vendor configuration and test on the target engine. |
| Lock timeout query hint has no effect | Provider/dialect/database ignores or maps the hint differently. | Inspect SQL, check Hibernate version, and use supported database configuration. |
| Request waits a long time before SQL runs | Connection pool is out of connections. | Check pool acquisition timeout and metrics; distinguish from database lock wait. |
| Deadlocks appear only under load | Code paths lock multiple rows in different orders. | Standardize lock order, reduce transaction duration, and test two competing transactions. |
| Retry fails immediately | Retry runs inside the old rollback-only transaction. | Place retry outside the transactional worker; each attempt uses a new transaction. |
| Retry creates duplicate orders or side effects | Operation is not idempotent or calls external systems before commit. | Use an idempotency key/outbox and bounded retries. |
| MySQL timeout does not roll back entire transaction | InnoDB by default may roll back only the statement on lock wait timeout. | Explicitly roll back the transaction in the application or configure `innodb_rollback_on_timeout` per policy. |
| SQL Server session retains old lock timeout | `SET LOCK_TIMEOUT` persists on pooled connections. | Reset session settings or manage connection configuration carefully. |
| `SKIP LOCKED` misses rows | Query intentionally skips locked rows. | Use only for queues/workers; do not use when a full list is required. |
| H2 tests pass but production deadlocks | Lock manager and isolation differ across engines. | Run tests using the production database via Testcontainers. |

## 17. Procedure for investigating lock waits and deadlocks

1. Determine whether requests are waiting on the connection pool or already executing SQL waiting on the database.
2. Collect the running SQL, transaction age, and request stack traces.
3. On the database, inspect blocking sessions, blocked sessions, lock types, and involved rows/tables/indexes.
4. For deadlocks, read the deadlock graph/logs to see which resources each transaction holds and waits on.
5. Inspect query plans and indexes to determine the range of locked records.
6. Compare lock acquisition orders across code paths that can update those rows concurrently.
7. Check isolation levels, batch sizes, and transaction hold times.
8. Choose a lock timeout suited to the latency budget and API response design.
9. Retry only deadlock/transient errors with a new transaction, bounded attempts, and idempotent operations.
10. Add an integration test reproducing the exact scenario on the target database.

## 18. Design principles

1. Use `PESSIMISTIC_WRITE` when row locking is needed in read-then-update flows; always run inside a transaction.
2. Distinguish lock timeout, transaction timeout, query timeout, and connection pool timeout.
3. Treat `jakarta.persistence.lock.timeout` as a provider request and verify the database actually enforces it.
4. Choose timeouts according to SLAs and acceptable business wait times; avoid waiting indefinitely.
5. Keep transactions short and do not call external services while holding database locks.
6. Lock multiple rows in a consistent order across every code path.
7. Create indexes for filter predicates and inspect execution plans to minimize lock scope.
8. Handle deadlocks by rolling back and retrying the entire operation in a new transaction if safe.
9. Do not retry business or validation errors; cap retries and add backoff/jitter.
10. Use `NOWAIT` when fast failure is desired; use `SKIP LOCKED` for queues where skipping busy rows is acceptable.
11. Test timeouts, deadlocks, and rollbacks on the actual production database/driver.
12. Verify SQLState/vendor codes together with post-commit/rollback data; do not assert exception messages alone.

## 19. Completion checklist

- [ ] Distinguish lock wait timeout, transaction timeout, query timeout, and connection pool timeout.
- [ ] Use `@Lock(PESSIMISTIC_WRITE)` inside a transaction.
- [ ] Configure and verify `jakarta.persistence.lock.timeout`.
- [ ] Explain the deadlock cycle between two transactions.
- [ ] Write a test with two transactions acquiring locks in opposite orders.
- [ ] Verify lock timeout using two independent transactions.
- [ ] Identify deadlocks and timeouts via SQLState/vendor code.
- [ ] Know timeout rollback differences among PostgreSQL, MySQL, SQL Server, and Oracle.
- [ ] Understand the effects of indexes, isolation levels, and lock order.
- [ ] Use NOWAIT/SKIP LOCKED for the right purposes.
- [ ] Retry the entire operation in a new transaction with bounds and idempotency.
- [ ] Run integration tests on the production database engine.

Once completed, you can set appropriate lock wait timeouts, reproduce deadlocks in integration tests, and handle database-specific differences to protect transactions in Spring Data JPA.