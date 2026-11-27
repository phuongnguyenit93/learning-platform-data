# Testing Locking, Concurrency Conflicts, and Rollback

## 1. Objectives

When multiple requests concurrently read and update an Entity, data can be overwritten or changed between the check and the write. Spring Data JPA relies on JPA/Hibernate locking mechanisms and database transactions to control these situations.

This lesson shows how to test:
- Optimistic locking using `@Version`, detecting two transactions updating the same version of data.
- Pessimistic locking using `@Lock(LockModeType.PESSIMISTIC_WRITE)`, holding a lock while a transaction processes.
- Concurrent conflicts using two independent transactions and two independent persistence contexts.
- Rollback when business logic throws an exception or fails validation.
- Verifying data after commit/rollback using a fresh transaction.
- Distinguishing tests running inside `@DataJpaTest`'s transaction from real transactions managed by a Service.

After this lesson, you will be able to write integration tests proving a competing update is rejected, a write lock makes another transaction wait, and a failed operation leaves no committed changes behind.

## 2. Why Test Concurrency?

Suppose inventory holds 10 items. Two requests simultaneously read quantity 10 and each orders 1 item. If both write the new quantity 9 without protection, one decrement is lost. The wrong result is 9 even though two orders were confirmed.

This is a lost update. Related bugs commonly arise when:

- Two transactions read the same Entity version.
- One transaction modifies data after another transaction has already read it.
- Application code checks state in Java and then writes without re-verifying the condition at the database.
- A transaction writes across multiple tables and fails partway through.

Standard unit tests run sequentially and typically share one persistence context, making these bugs hard to spot. You need integration tests that create independent transactions, coordinate read/write timing, and inspect state after transactions finish.

## 3. Optimistic Locking With @Version

Optimistic locking fits scenarios where conflicts are infrequent. The Entity has a version attribute annotated with `@Version`. When JPA updates a managed Entity, the provider includes the current version in the `WHERE` clause and increments the version.

Hibernate-generated SQL typically looks like:

```sql
update stock_items
set available = ?, version = ?
where id = ? and version = ?;
```

If another transaction already updated the same row, the database version no longer matches. The second UPDATE affects 0 rows and the provider reports an optimistic locking conflict, typically via `OptimisticLockException` or a Spring-translated `OptimisticLockingFailureException`.

### 3.1. Entity With Version

`src/main/java/com/example/stock/StockItem.java`:

```java
package com.example.stock;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "stock_items")
public class StockItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int available;

    @Version
    @Column(nullable = false)
    private long version;

    protected StockItem() {
        // JPA requires a no-arg constructor.
    }

    public StockItem(int available) {
        if (available < 0) {
            throw new IllegalArgumentException("Available quantity cannot be negative");
        }
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }
        available -= quantity;
    }

    public Long getId() { return id; }
    public int getAvailable() { return available; }
    public long getVersion() { return version; }
}
```

JPA manages the version when the Entity is updated via dirty checking or merge. Never assign version manually in domain methods; the provider is responsible for incrementing it.

### 3.2. Repository and Service

`src/main/java/com/example/stock/StockItemRepository.java`:

```java
package com.example.stock;

import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface StockItemRepository extends JpaRepository<StockItem, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from StockItem s where s.id = :id")
    Optional<StockItem> findByIdForUpdate(@Param("id") Long id);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           update StockItem s
           set s.available = :newAvailable,
               s.version = s.version + 1
           where s.id = :id
             and s.version = :expectedVersion
           """)
    int updateIfVersionMatches(
            @Param("id") Long id,
            @Param("expectedVersion") long expectedVersion,
            @Param("newAvailable") int newAvailable);
}
```

`src/main/java/com/example/stock/StockService.java`:

```java
package com.example.stock;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockService {
    private final StockItemRepository repository;

    public StockService(StockItemRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserveOptimistically(Long id, int quantity) {
        StockItem item = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Stock item not found"));
        item.reserve(quantity);
    }

    @Transactional
    public void reservePessimistically(Long id, int quantity) {
        StockItem item = repository.findByIdForUpdate(id)
                .orElseThrow(() -> new IllegalArgumentException("Stock item not found"));
        item.reserve(quantity);
    }

    @Transactional
    public void reserveThenFail(Long id, int quantity) {
        StockItem item = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Stock item not found"));
        item.reserve(quantity);
        repository.flush();
        throw new IllegalStateException("Simulated downstream failure");
    }

    @Transactional
    public void saveDetached(StockItem staleItem) {
        repository.saveAndFlush(staleItem);
    }

    @Transactional
    public void setAvailableIfVersionMatches(Long id, long expectedVersion, int newAvailable) {
        int affected = repository.updateIfVersionMatches(id, expectedVersion, newAvailable);
        if (affected != 1) {
            throw new IllegalStateException("Stock changed or no longer exists");
        }
    }
}
```

`reserveOptimistically` uses an Entity with `@Version`; if another transaction already updated the same version, flushing/committing fails. `reservePessimistically` loads the row with a write lock and holds the lock until the transaction commits or rolls back. `reserveThenFail` intentionally throws an unchecked exception after flushing to verify rollback.

## 4. Pessimistic Locking With @Lock

Pessimistic locking asks the database to lock a row while the transaction is processing. Spring Data JPA lets you attach `@Lock` to a Repository query method:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select s from StockItem s where s.id = :id")
Optional<StockItem> findByIdForUpdate(@Param("id") Long id);
```

`PESSIMISTIC_WRITE` is commonly implemented using SQL equivalent to `SELECT ... FOR UPDATE`. Another transaction requesting a conflicting lock on the same row must wait, or receives a lock timeout/deadlock exception depending on database and settings.

Common lock modes:

| Lock Mode | General Meaning |
| --- | --- |
| `PESSIMISTIC_READ` | Requests a shared read lock preventing other transactions from modifying data per database/provider semantics. |
| `PESSIMISTIC_WRITE` | Requests an exclusive write lock, commonly used for read-then-update flows. |
| `PESSIMISTIC_FORCE_INCREMENT` | Acquires a pessimistic lock and forces incrementing the version of a versioned Entity. |

Pessimistic locks must be acquired inside an active transaction. Never call a Repository to acquire a lock and end the transaction before performing the update; once the transaction ends, the lock is released.

Do not hold locks while calling external services, waiting on user input, or doing long-running work. Longer transactions increase lock contention and deadlock risk.

### 4.1. Configuring Timeouts

JPA allows requesting a lock timeout via query hints, though support and interpretation depend on provider/database:

```java
import jakarta.persistence.QueryHint;
import jakarta.persistence.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(@QueryHint(name = "jakarta.persistence.lock.timeout", value = "3000"))
@Query("select s from StockItem s where s.id = :id")
Optional<StockItem> findByIdForUpdate(@Param("id") Long id);
```

The example uses the Jakarta Persistence hint with a millisecond value. Do not assume every database enforces the exact same timeout; check Hibernate and target database documentation, then write tests for lock timeout/deadlock if it is part of the application contract.

## 5. Configuring the Integration Test

Examples use Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate, and H2. `@DataJpaTest` configures the Repository, `EntityManager`, and transaction manager for the test slice.

`src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:stock-lock-db;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
```

Concurrency tests require multiple independent transactions. `@DataJpaTest` runs each test inside a framework-managed transaction by default; therefore, the example disables the outer test transaction with `@Transactional(propagation = NOT_SUPPORTED)` and opens explicit transactions with `TransactionTemplate`.

This gives each thread its own persistence context and ensures transactions actually commit/roll back before tests read results.

## 6. Testing Optimistic Conflict With Two Concurrent Transactions

The next test uses two threads. Both transactions read the same version before either is allowed to update. Then both decrement stock by one unit.

Because both read the same version, only one transaction can commit. The other must receive an optimistic locking conflict. The final stock count is 9, not 8; the failed operation must be retried if business rules require applying both requests.

`src/test/java/com/example/stock/StockConcurrencyTest.java`:

```java
package com.example.stock;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import jakarta.persistence.OptimisticLockException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@DataJpaTest
@Import(StockService.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class StockConcurrencyTest {
    @Autowired
    private StockItemRepository repository;

    @Autowired
    private StockService service;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private TransactionTemplate transactions;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        transactions.executeWithoutResult(status -> repository.deleteAllInBatch());
    }

    private Long createStock(int available) {
        return transactions.execute(status ->
                repository.saveAndFlush(new StockItem(available)).getId());
    }

    private int readAvailable(Long id) {
        return transactions.execute(status -> repository.findById(id)
                .orElseThrow().getAvailable());
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for concurrent test");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Concurrent test interrupted", ex);
        }
    }

    private static boolean hasCause(Throwable error, Class<? extends Throwable> type) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
        }
        return false;
    }

    @Test
    void onlyOneConcurrentOptimisticUpdateCanCommitFromTheSameVersion() throws Exception {
        Long id = createStock(10);
        CountDownLatch bothLoaded = new CountDownLatch(2);
        CountDownLatch allowUpdates = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        java.util.concurrent.Callable<String> update = () -> {
            try {
                transactions.execute(status -> {
                    StockItem item = repository.findById(id).orElseThrow();
                    bothLoaded.countDown();
                    await(allowUpdates);
                    item.reserve(1);
                    repository.flush();
                    return null;
                });
                return "COMMITTED";
            } catch (RuntimeException ex) {
                if (hasCause(ex, OptimisticLockingFailureException.class)
                        || hasCause(ex, OptimisticLockException.class)) {
                    return "CONFLICT";
                }
                throw ex;
            }
        };

        List<String> outcomes;
        try {
            Future<String> first = pool.submit(update);
            Future<String> second = pool.submit(update);
            assertThat(bothLoaded.await(10, TimeUnit.SECONDS)).isTrue();
            allowUpdates.countDown();
            outcomes = List.of(first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS));
        } finally {
            allowUpdates.countDown();
            pool.shutdownNow();
        }

        assertThat(outcomes).containsExactlyInAnyOrder("COMMITTED", "CONFLICT");
        assertThat(readAvailable(id)).isEqualTo(9);
    }

    @Test
    void staleDetachedEntityCannotOverwriteANewerVersion() {
        Long id = createStock(10);
        StockItem stale = transactions.execute(status -> repository.findById(id).orElseThrow());

        service.reserveOptimistically(id, 2);

        assertThatThrownBy(() -> service.saveDetached(stale))
                .satisfies(error -> assertThat(
                        hasCause(error, OptimisticLockingFailureException.class)
                                || hasCause(error, OptimisticLockException.class)).isTrue());

        assertThat(readAvailable(id)).isEqualTo(8);
    }

    @Test
    void runtimeExceptionRollsBackTheStockChange() {
        Long id = createStock(10);

        assertThatThrownBy(() -> service.reserveThenFail(id, 3))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Simulated downstream failure");

        assertThat(readAvailable(id)).isEqualTo(10);
    }
}
```

The first test uses barriers to ensure both transactions read the same version before updating. `flush()` surfaces the optimistic locking failure directly inside the callback upon conflict; commit is still managed by `TransactionTemplate`. The second test keeps a detached Entity holding a stale version, updates the database in another transaction, and then attempts to merge the stale snapshot. The rollback test reads the quantity back in a fresh transaction to prove the change was discarded.

Run tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is `BUILD SUCCESS`. The tests verify one transaction wins and one conflicts, a stale Entity cannot overwrite a newer version, and a runtime exception rolls back changes. This is the expected output for the example; no live build log was recorded here.

## 7. Testing a Pessimistic Lock

With `PESSIMISTIC_WRITE`, the first transaction holds a lock on a row. The second transaction requests a lock on the same row and must wait until the first transaction completes.

Add the following test to `StockConcurrencyTest`:

```java
@Test
void pessimisticWriteLockMakesAnotherTransactionWait() throws Exception {
    Long id = createStock(10);
    CountDownLatch firstHasLock = new CountDownLatch(1);
    CountDownLatch releaseFirst = new CountDownLatch(1);
    CountDownLatch secondIsStarting = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    try {
        Future<?> first = pool.submit(() -> transactions.executeWithoutResult(status -> {
            StockItem item = repository.findByIdForUpdate(id).orElseThrow();
            firstHasLock.countDown();
            await(releaseFirst);
            item.reserve(1);
        }));

        assertThat(firstHasLock.await(10, TimeUnit.SECONDS)).isTrue();

        Future<?> second = pool.submit(() -> transactions.executeWithoutResult(status -> {
            secondIsStarting.countDown();
            StockItem item = repository.findByIdForUpdate(id).orElseThrow();
            item.reserve(1);
        }));

        assertThat(secondIsStarting.await(10, TimeUnit.SECONDS)).isTrue();
        assertThatThrownBy(() -> second.get(250, TimeUnit.MILLISECONDS))
                .isInstanceOf(java.util.concurrent.TimeoutException.class);

        releaseFirst.countDown();
        first.get(10, TimeUnit.SECONDS);
        second.get(10, TimeUnit.SECONDS);
    } finally {
        releaseFirst.countDown();
        pool.shutdownNow();
    }

    assertThat(readAvailable(id)).isEqualTo(8);
}
```

The test verifies the second transaction has not completed while the first holds the lock. Once the lock is released, both transactions decrement stock sequentially and the final result is 8.

The 250 ms timeout is purely an observation window in this test to confirm the second transaction is waiting, not an application lock-timeout setting. Lock timing varies by database, driver, and CI environment. For production systems using PostgreSQL, MySQL, or SQL Server, run the same test on that engine via Testcontainers and pick appropriate timeouts.

## 8. Rollback on Business Failure

Spring transactions roll back by default when a transactional method throws a `RuntimeException` or `Error`. Checked exceptions do not trigger automatic rollback by default; if required, declare `rollbackFor`.

In `reserveThenFail` above, the service:

1. Reads `StockItem` inside the transaction.
2. Decrements quantity via a domain method.
3. Flushes to send the UPDATE to the database.
4. Throws `IllegalStateException` before the transaction commits.

Tests must invoke the Service through the Spring proxy so the interceptor applies `@Transactional`. Once the exception exits the method, the transaction must roll back.

### 8.1. Rollback With Checked Exceptions

If a method throws a checked exception and business logic still requires rollback, declare it explicitly:

```java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void reserveAndCharge(Long id, int quantity) throws PaymentRejectedException {
    StockItem item = repository.findById(id).orElseThrow();
    item.reserve(quantity);
    paymentGateway.charge(quantity);
}
```

The snippet assumes `PaymentRejectedException` is a checked exception. Without configuring `rollbackFor`, Spring can commit changes by default when a checked exception escapes the method. Also watch out for catching exceptions without rethrowing: the transaction interceptor never sees the exception unless code explicitly marks rollback-only.

### 8.2. Rollback When Affected Row Count Is Wrong

For bulk updates, a Service can inspect the affected row count and throw a runtime exception if the count fails expectations:

```java
@Transactional
public void setAvailableExactly(Long id, long expectedVersion, int newAvailable) {
    int affected = repository.updateIfVersionMatches(id, expectedVersion, newAvailable);
    if (affected != 1) {
        throw new IllegalStateException("Unexpected affected row count: " + affected);
    }
}
```

Place the update and the count check inside the same transaction. When the exception exits the Service, the transaction rolls back under Spring's rollback rules. Never catch the exception and continue committing if business rules demand all-or-nothing atomicity.

## 9. Why Do Transaction Tests Need Dedicated Setup?

`@DataJpaTest` opens a transaction for each test method and rolls back on completion by default. This is convenient for simple Repository tests, yet can mask how Services manage transactions or cause multiple operations in a test to share one persistence context.

For concurrency/rollback tests:

- Use `@Transactional(propagation = NOT_SUPPORTED)` to turn off the outer transaction created by the test framework.
- Use `TransactionTemplate` to open distinct transactions per operation.
- Run competing transactions on separate threads so they use independent `EntityManager`/persistence contexts.
- Wait for both transactions to read data before allowing writes so conflicts reproduce deterministically.
- Read results in a fresh transaction after competing transactions finish.

Never share a single `EntityManager` or managed Entity instance across threads. `EntityManager` is not thread-safe; each transaction/thread requires its own persistence context.

## 10. Testing Deadlocks and Lock Timeouts

Deadlocks occur when transactions acquire locks in different orders and wait on each other's resources. For example:

- Transaction A locks row 1 and waits for row 2.
- Transaction B locks row 2 and waits for row 1.

The database detects the wait cycle and aborts one transaction. The application should handle the resulting exception appropriately and may retry the entire transaction if the operation is idempotent.

When testing deadlocks/timeouts:

1. Create at least two independent transactions.
2. Use latches/barriers to coordinate lock acquisition order.
3. Configure a short lock timeout in the test environment if supported by the database.
4. Assert one transaction fails with the expected provider/database exception.
5. Verify the aborted transaction leaves no partial writes behind.
6. Run tests on the production database or Testcontainers; H2 does not reproduce every engine identically.

Deadlock tests are not mandatory for every Repository. Add them only when the application actually acquires multiple pessimistic locks or risks conflicting lock orders.

## 11. Comparing Optimistic and Pessimistic Locking

| Criterion | Optimistic (`@Version`) | Pessimistic (`@Lock`) |
| --- | --- | --- |
| Protection mechanism | Checks version on update/delete. | Acquires a database lock before or during read to block conflicting updates. |
| Best fit | Low contention, short transactions, retryable operations. | High contention or operations requiring serialized row access. |
| Impact on contention | One transaction fails on flush/commit. | Other transactions wait, time out, or deadlock. |
| Resource holding | Does not hold write locks during ordinary reads. | Holds locks until commit/rollback. |
| How to test | Two transactions read the same version then write; verify one conflicts. | Transaction A holds lock, transaction B requests the same lock and waits. |

Neither strategy is universally best. Optimistic locking is usually a solid starting point for low-contention data; pessimistic locking suits strict concurrency control when lock duration stays brief.

## 12. Note on Bulk Updates and @Version

JPQL bulk UPDATE/DELETE statements execute directly on the database, bypassing Entity dirty checking and automatic optimistic locking. If a bulk query modifies a `@Version`ed Entity, increment the version explicitly and include the expected version in `WHERE` when compare-and-set semantics are required.

For example, the Repository method shown earlier uses:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
       update StockItem s
       set s.available = :newAvailable,
           s.version = s.version + 1
       where s.id = :id
         and s.version = :expectedVersion
       """)
int updateIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") long expectedVersion,
        @Param("newAvailable") int newAvailable);
```

If the count is 0, either the version mismatched or the row no longer exists. Bulk queries do not automatically throw an optimistic locking exception on version mismatch; the Service must check affected counts and handle conflicts.

## 13. Testing on the Production Database

H2 is helpful for basic JPA tests, but locking, isolation, deadlocks, timeouts, generated SQL, and data types can differ from production databases.

If the application runs PostgreSQL, MySQL, or SQL Server, maintain a suite of integration tests running on the matching engine via Testcontainers:

```java
@Testcontainers
@SpringBootTest
class StockDatabaseConcurrencyIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Configure datasource from container and run the same transaction scenarios.
}
```

This snippet only illustrates container setup; dynamic datasource configuration, Testcontainers dependencies, and migrations must be wired per your project build. Do not treat H2 tests as full proof of PostgreSQL/MySQL locking behavior.

## 14. Common Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Two concurrent requests update with no conflict | Entity lacks `@Version` or update bypassed versioned Entity. | Add `@Version` and test with two independent transactions. |
| Optimistic exception appears only at commit | Provider defers SQL until flush/commit. | Call `flush()` in tests when observing failure at a specific point; still verify rollback. |
| Concurrency test shares one persistence context | Test runs in a single transaction or shares an `EntityManager`. | Disable outer test transaction and open independent transactions per thread. |
| Pessimistic lock not held until update | Transaction ended before write finished. | Place locking read and update inside the same `@Transactional` method. |
| Lock tests flake in CI | Used fixed delays without coordinating transaction order. | Use `CountDownLatch`/barriers, bounded timeouts, and test on target DB. |
| Rollback test still sees stale value in object | Reading stale managed object in persistence context. | Clear/refresh or reload in a fresh transaction. |
| Runtime exception does not roll back | Exception was caught and swallowed, or method bypassed Spring transaction proxy. | Let the exception exit the transactional method or mark rollback-only. |
| Checked exception still commits | Spring rolls back runtime exceptions and Errors by default, not all checked exceptions. | Declare `rollbackFor` if business rules require it. |
| Deadlock test fails to reproduce on H2 | Locking/isolation differs from production database. | Run test on the exact engine using Testcontainers. |
| Conflicting transaction still alters data | Test did not inspect state after transaction completed or caught exception inside transaction. | Verify rollback and reload data in a fresh transaction. |

## 15. Process for Writing Reliable Concurrency Tests

1. Seed baseline data in a separate transaction and commit before starting the scenario.
2. Create independent transactions/persistence contexts per concurrent actor.
3. Use latches or barriers to control read, lock acquisition, and update timing.
4. Flush when needed to force the provider to emit SQL and expose conflicts mid-test.
5. Collect each transaction's outcome: commit, optimistic conflict, lock timeout, or deadlock.
6. Wait for all transactions to finish before inspecting database state.
7. Read database state in a fresh transaction rather than relying on old Entity objects.
8. Verify both business outcomes and database version/quantity values.
9. Confirm rollback left no committed changes behind.
10. Re-run locking scenarios on the production database via Testcontainers when engine-specific behavior affects business rules.

## 16. Completion Checklist

- [ ] Can explain lost updates and why concurrency testing is needed.
- [ ] Declared `@Version` on the Entity.
- [ ] Used two independent transactions to test optimistic locking.
- [ ] Verified only one transaction sharing a version can commit.
- [ ] Declared `@Lock(LockModeType.PESSIMISTIC_WRITE)` on the Repository.
- [ ] Verified a second transaction waits while the first holds the lock.
- [ ] Understand that locks are held until commit/rollback.
- [ ] Used `@Transactional` and runtime exceptions to test rollback.
- [ ] Used `rollbackFor` when checked exceptions must trigger rollback.
- [ ] Reloaded data in a fresh transaction after commit/rollback.
- [ ] Disabled `@DataJpaTest`'s outer transaction when controlling independent transactions.
- [ ] Distinguished H2 behavior from production databases and added Testcontainers when needed.

With this in place, you can prove through integration tests that optimistic locking catches competing updates, pessimistic locking serializes access on a row, and transaction rollbacks preserve data consistency when business operations fail.