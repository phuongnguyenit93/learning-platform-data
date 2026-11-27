# Simulating Two Concurrent Inventory Transactions and Handling Conflicts

## Objectives

When two requests purchase the same item concurrently, both can read the same available stock and both decide enough stock remains. If each transaction writes a new value based on stale data without checking for conflicts, the system can confirm more orders than actual inventory. This is a form of lost update that causes overbooking.

This lab creates two independent transactions, forces both to read the same inventory version before writing, and observes how JPA detects the conflict via optimistic locking. We also examine retrying in a new transaction, pessimistic locking, conditional `UPDATE` statements, idempotency, and running tests against a real database.

After this lesson, you will be able to:

- Explain the race condition when multiple requests reserve the same item concurrently.
- Define inventory invariants and protect them at both the domain and database levels.
- Use `@Version` to detect updates based on stale versions.
- Write an integration test with two threads, two transactions, and a deterministic synchronization barrier.
- Verify that one transaction commits while the other receives an optimistic locking conflict.
- Retry safely using a new transaction and reloaded data.
- Compare optimistic locking, pessimistic locking, and atomic conditional `UPDATE`.
- Handle deadlocks, timeouts, rollbacks, and duplicate requests.
- Verify concurrency behavior using Testcontainers.

## 1. Scenario and Invariants to Protect

Suppose an item currently has 10 sellable units. Two independent requests both attempt to reserve 7 units:

| Step | Transaction T1 | Transaction T2 | Available in DB |
|---|---|---|---:|
| 1 | Reads `available = 10` | | 10 |
| 2 | | Reads `available = 10` | 10 |
| 3 | Computes `10 - 7 = 3` | | 10 |
| 4 | | Computes `10 - 7 = 3` | 10 |
| 5 | Writes `available = 3` | | 3 |
| 6 | | Writes `available = 3` | 3 |

If both writes succeed based on stale reads, the system has promised 14 units when only 10 existed. The final database value might be 3, yet both orders were confirmed. Checking `available` only in Java cannot prevent this because both transactions can read the same stale snapshot.

Minimum invariants:

- `available` is always greater than or equal to 0.
- A reservation succeeds only when `available` is sufficiently large.
- The same business request must never deduct stock multiple times.
- If a transaction fails, its changes must roll back.

The precondition check and mutation must be guarded at write time using a version column, row lock, or conditional `UPDATE` statement.

## 2. Creating an Entity with Optimistic Locking

Entity representing sellable inventory:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_item")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private int available;

    protected InventoryItem() {
    }

    public InventoryItem(int available) {
        if (available < 0) {
            throw new IllegalArgumentException(
                "Available quantity cannot be negative");
        }
        this.available = available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        if (available < quantity) {
            throw new InsufficientStockException(
                "Not enough stock: available=" + available
                    + ", requested=" + quantity);
        }

        available -= quantity;
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }

    public long getVersion() {
        return version;
    }
}
~~~

Business exception:

~~~java
public class InsufficientStockException extends RuntimeException {

    public InsufficientStockException(String message) {
        super(message);
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {
}
~~~

The `@Version` field is managed by the JPA provider. The application does not increment this field manually in normal entity update flows. When loading the entity, each transaction receives both `available` and the current `version`. On flush or commit, the provider generates a conditional `UPDATE` equivalent to:

~~~sql
UPDATE inventory_item
   SET available = ?, version = ?
 WHERE id = ? AND version = ?;
~~~

Suppose T1 and T2 both load `version = 0`. The transaction that writes first updates the row where `version = 0` and increments the version. The other transaction's `UPDATE` no longer matches the old version, so the provider sees 0 updated rows and throws an optimistic locking exception.

The exact SQL depends on the provider, dialect, and mapping. The crucial semantics are that the `UPDATE` checks the version that was read, not just the ID.

## 3. Service Reserving Inventory Inside a Transaction

The service loads the entity, calls the domain behavior, and relies on dirty checking to write changes:

~~~java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryReservationService {

    private final InventoryRepository inventoryRepository;

    public InventoryReservationService(
            InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(Long itemId, int quantity) {
        InventoryItem item = inventoryRepository.findById(itemId)
            .orElseThrow(() ->
                new EntityNotFoundException("Inventory item not found"));

        item.reserve(quantity);
    }
}
~~~

The entity is loaded inside the transaction and is therefore managed. When `reserve()` decreases `available`, JPA tracks the mutation. SQL might only be emitted at flush or commit time. Thus, reaching the final line of the service method does not guarantee the transaction has committed; callers only treat the operation as successful once the call through the Spring proxy finishes without a commit error.

Do not catch an optimistic locking exception inside the transaction and keep using the old entity. The transaction may already be rolled back or marked rollback-only. Let the error escape the transaction boundary, then reload fresh data in a new transaction.

## 4. Simulating Two Transactions Reading the Same Version

To reliably reproduce the race condition in a test, ensure both transactions read the entity before either transaction writes. If you merely spawn two threads and hope their timing overlaps, the test can become flaky.

We use:

- Two independent threads.
- A separate transaction for each thread.
- `CyclicBarrier` to wait until both have finished reading.
- `flush()` to force the `UPDATE` to run and detect conflicts inside the callback.
- A new transaction to verify the final database state.

Integration test example using `@DataJpaTest` and `TransactionTemplate`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManager;
import jakarta.persistence.OptimisticLockException;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@DataJpaTest
class InventoryConcurrencyTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void onlyOneTransactionCanReserveFromTheSameVersion()
            throws Exception {

        TransactionTemplate transactions =
            new TransactionTemplate(transactionManager);
        transactions.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        Long itemId = transactions.execute(status -> {
            InventoryItem item = new InventoryItem(10);
            entityManager.persist(item);
            entityManager.flush();
            return item.getId();
        });

        CyclicBarrier bothTransactionsRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<String> first = pool.submit(() ->
                reserveInOwnTransaction(
                    transactions, itemId, 7, bothTransactionsRead));

            Future<String> second = pool.submit(() ->
                reserveInOwnTransaction(
                    transactions, itemId, 7, bothTransactionsRead));

            String firstResult = first.get(15, TimeUnit.SECONDS);
            String secondResult = second.get(15, TimeUnit.SECONDS);

            assertThat(List.of(firstResult, secondResult))
                .containsExactlyInAnyOrder(
                    "COMMITTED", "OPTIMISTIC_CONFLICT");

            Integer remaining = transactions.execute(status -> {
                entityManager.clear();
                return entityManager.find(InventoryItem.class, itemId)
                    .getAvailable();
            });

            assertThat(remaining).isEqualTo(3);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(15, TimeUnit.SECONDS);

            transactions.executeWithoutResult(status -> {
                InventoryItem item =
                    entityManager.find(InventoryItem.class, itemId);
                if (item != null) {
                    entityManager.remove(item);
                }
            });
        }
    }

    private String reserveInOwnTransaction(
            TransactionTemplate transactions,
            Long itemId,
            int quantity,
            CyclicBarrier bothTransactionsRead) {

        try {
            transactions.executeWithoutResult(status -> {
                InventoryItem item =
                    entityManager.find(InventoryItem.class, itemId);

                awaitBothReads(bothTransactionsRead);

                item.reserve(quantity);
                entityManager.flush();
            });

            return "COMMITTED";
        } catch (RuntimeException ex) {
            if (hasCause(ex, OptimisticLockException.class)
                    || hasCause(
                        ex, OptimisticLockingFailureException.class)) {
                return "OPTIMISTIC_CONFLICT";
            }
            throw ex;
        }
    }

    private void awaitBothReads(CyclicBarrier barrier) {
        try {
            barrier.await(10, TimeUnit.SECONDS);
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Both transactions did not reach the read barrier", ex);
        }
    }

    private boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType) {

        Throwable current = error;
        while (current != null) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

The test method uses `Propagation.NOT_SUPPORTED` so there is no outer test transaction wrapping everything. The fixture is created and committed via `TransactionTemplate` before the two threads start. Each worker calls `executeWithoutResult()` with `REQUIRES_NEW`, giving each thread its own transaction and persistence context.

The injected `EntityManager` is Spring's shared proxy, which routes to the `EntityManager` bound to the current thread's transaction. Never share a single raw `EntityManager` instance across threads because persistence contexts are not thread-safe.

Both workers read `available = 10` and the same version before the barrier opens. Then each deducts 7 and flushes. One `UPDATE` succeeds; the other no longer matches the version and rolls back. The expected outcome is exactly one `COMMITTED`, one `OPTIMISTIC_CONFLICT`, and a final `available` of 3.

Which transaction wins depends on thread scheduling. Tests should never assert that T1 always wins or T2 always wins. The barrier uses a timeout so the test fails cleanly if a worker never reaches the synchronization point. The fixture is removed in a separate transaction inside `finally` so the test leaves no leftover data.

## 5. Why Flush and Re-read in a New Transaction?

Calling `save()` or modifying fields on a managed entity does not necessarily emit SQL immediately. Without `flush()`, the optimistic locking error might only occur at commit time, making it harder to pinpoint where the error arose in the test.

`flush()` synchronizes the persistence context with the database without committing the transaction. When flush detects a conflict, the current transaction must roll back. Even if the error were raised only at commit time, `TransactionTemplate.execute()` still throws the exception after the callback completes and before returning to the caller.

After both workers finish, the test starts a new transaction and calls `clear()` before reloading the entity. This avoids reading stale state from an old persistence context. The final result must be verified from the database: `available = 3`, `version` incremented once, and no second reservation occurred.

Do not use a single transaction for both workers. Nor should you simply call two methods sequentially in the same transaction, as that fails to simulate two transactions holding the same stale version.

## 6. Retrying Conflicts in a New Transaction

An optimistic locking conflict means the data changed after the current transaction read it. Retrying requires loading a fresh entity and re-running the business rules from scratch. Never reuse a stale entity or continue inside a rolled-back transaction.

An explicit retry coordinator using `TransactionTemplate`:

~~~java
import jakarta.persistence.EntityNotFoundException;
import jakarta.persistence.OptimisticLockException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public class InventoryRetryCoordinator {

    private final InventoryRepository inventoryRepository;
    private final PlatformTransactionManager transactionManager;

    public InventoryRetryCoordinator(
            InventoryRepository inventoryRepository,
            PlatformTransactionManager transactionManager) {
        this.inventoryRepository = inventoryRepository;
        this.transactionManager = transactionManager;
    }

    public void reserveWithRetry(Long itemId, int quantity) {
        TransactionTemplate attemptTransaction =
            new TransactionTemplate(transactionManager);
        attemptTransaction.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                attemptTransaction.executeWithoutResult(status -> {
                    InventoryItem item =
                        inventoryRepository.findById(itemId)
                            .orElseThrow(() ->
                                new EntityNotFoundException(
                                    "Inventory item not found"));

                    item.reserve(quantity);
                });
                return;
            } catch (RuntimeException ex) {
                boolean conflict =
                    hasOptimisticConflict(ex);

                if (!conflict || attempt == maxAttempts) {
                    throw ex;
                }

                pauseBeforeRetry(attempt);
            }
        }
    }

    private boolean hasOptimisticConflict(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof OptimisticLockException
                    || current instanceof OptimisticLockingFailureException) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
            current = current.getCause();
        }
        return false;
    }

    private void pauseBeforeRetry(int attempt) {
        try {
            Thread.sleep(50L * attempt);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Retry was interrupted", ex);
        }
    }
}
~~~

Each iteration calls `executeWithoutResult()` with `REQUIRES_NEW`, so the previous transaction has already ended before the next attempt begins. The entity is reloaded from the database on each attempt. The example uses linear backoff for readability; production should use bounded backoff with jitter.

In the scenario where two requests both reserve 7 out of 10, the winning request commits and leaves `available = 3`. The losing request hits a conflict, retries, reloads `available = 3`, and throws `InsufficientStockException`. That is the right business outcome. Out-of-stock is not a transient error to keep retrying.

The coordinator must sit outside any enclosing transaction. If an outer transaction is active and the worker uses `REQUIRED`, retries would join that same transaction, defeating independent retry attempts. `REQUIRES_NEW` suspends any active outer transaction.

## 7. Distinguishing Conflicts, Out-of-Stock, and Infrastructure Failures

Do not lump every exception into a single retry loop:

| Scenario | Meaning | Handling Strategy |
|---|---|---|
| Optimistic locking conflict | Another transaction updated the version | Reload and perform bounded retries |
| `InsufficientStockException` | Fresh data does not have enough stock | Reject the request; do not retry |
| `EntityNotFoundException` | Item does not exist | Return appropriate business error |
| Deadlock | Database aborted one transaction to break a wait cycle | Retry the entire operation in a new transaction if safe |
| Lock timeout | Failed to acquire lock within timeout | Bounded retry or return transient error |
| Constraint violation | Data violates a database rule | Inspect cause; do not retry by default |
| Connection failure | Commit outcome may be unknown to the caller | Look up via idempotency key before re-submitting |

When a connection failure happens right at commit time, the caller might not know whether the transaction committed. Never assume a timeout means the database did not write the data. Use a stable request ID to verify whether the outcome was already applied before retrying.

## 8. Alternative: Pessimistic Locking

Optimistic locking lets transactions read concurrently and detects conflicts at write time. If an item experiences frequent contention, you can use a pessimistic write lock to serialize operations on that row.

Repository:

~~~java
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select i
          from InventoryItem i
         where i.id = :id
        """)
    Optional<InventoryItem> findForUpdate(@Param("id") Long id);
}
~~~

Service:

~~~java
@Transactional
public void reserveWithPessimisticLock(Long itemId, int quantity) {
    InventoryItem item = inventoryRepository.findForUpdate(itemId)
        .orElseThrow(() ->
            new EntityNotFoundException("Inventory item not found"));

    item.reserve(quantity);
}
~~~

The first transaction acquires a write lock on the inventory row. A second transaction requesting the lock must wait or fail according to the provider/database lock timeout. Once the first transaction commits, the second proceeds and inspects the updated quantity. If only 3 remain, the request for 7 is rejected.

Pessimistic locking fits when write contention is high and transactions are short. Never make HTTP calls, send emails, or wait on users while holding a lock. If a transaction must lock multiple items, lock them in a deterministic ID order to minimize deadlock risk. Specific lock timeouts and hints depend on the provider; verify behavior on your target database.

## 9. Alternative: Conditional UPDATE

If the business rule only needs to decrement quantity while checking availability, the database can evaluate the condition and perform the subtraction in a single statement:

~~~java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update InventoryItem i
           set i.available = i.available - :quantity
         where i.id = :itemId
           and i.available >= :quantity
        """)
    int reserveIfAvailable(
        @Param("itemId") Long itemId,
        @Param("quantity") int quantity
    );
}
~~~

Validate `quantity > 0` in the service before calling the query. Result:

- `1`: one row updated; reservation succeeded.
- `0`: no matching row; either the item does not exist or stock is insufficient.

The condition `available >= quantity` and the subtraction execute atomically in the database. Two requests cannot both read a stale value in Java and overwrite each other with precomputed results.

This is a JPQL bulk update. It bypasses dirty checking, entity callbacks, and does not automatically synchronize the persistence context. `flushAutomatically` flushes pending changes before the query; `clearAutomatically` clears the persistence context afterward. If the entity was loaded earlier, do not treat that old reference as the latest state.

Bulk updates also do not perform optimistic version checks automatically like regular entity updates. If the same table is also updated through entities carrying `@Version`, design consistent version/audit/event handling and test both write paths. Use a conditional `UPDATE` when the rule fits cleanly in one statement; use aggregate methods and locking when multiple invariants must be checked.

## 10. Deadlocks, Lock Timeouts, and Lock Ordering

Deadlocks arise when two transactions hold different locks and each waits for a lock held by the other. For instance, T1 locks item A and waits for B, while T2 locks B and waits for A.

Risk mitigation measures:

- Lock multiple rows in a consistent order, such as ascending by ID.
- Keep transactions short and load only necessary rows.
- Never call external services while holding database locks.
- Configure suitable lock timeouts and transaction timeouts.
- Retry the entire operation in a new transaction when the database reports a retryable error.
- Cap retry counts and apply backoff with jitter.
- Record metrics for deadlocks, lock waits, timeouts, and retry counts.

When the database aborts a transaction due to a deadlock, that transaction must roll back. Never catch the error and continue using the failed persistence context or transaction. Retries must reload fresh data and re-execute all business rules.

## 11. Idempotency So Retried Requests Do Not Deduct Stock Twice

`@Version` prevents two transactions from writing based on the same version, but it does not automatically prevent the same business request from being retried after the first attempt already committed. For instance, the server commits a reservation of 2 units, the response is lost, and the client times out and retries. If the retry is treated as a brand-new request, stock could be deducted by another 2.

Use a stable idempotency key generated by the caller or assigned by the system prior to the first attempt. Store the key alongside the business result and protect it with a unique constraint:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "stock_reservation",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_stock_reservation_request",
        columnNames = "request_id"
    )
)
public class StockReservation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_id", nullable = false, updatable = false)
    private String requestId;

    @Column(name = "item_id", nullable = false, updatable = false)
    private Long itemId;

    @Column(nullable = false, updatable = false)
    private int quantity;

    protected StockReservation() {
    }

    public StockReservation(
            String requestId,
            Long itemId,
            int quantity) {
        this.requestId = requestId;
        this.itemId = itemId;
        this.quantity = quantity;
    }
}
~~~

Within the same transaction, the service should:

1. Persist the reservation by `requestId` and flush to trigger the unique constraint check.
2. Load `InventoryItem` and call `reserve(quantity)`.
3. Commit both the reservation and the `available` update together.

If stock reservation fails, the transaction rolls back the reservation record too. If the same `requestId` is submitted again, the unique constraint blocks creating a second reservation. The caller handles duplicates after transaction failure: load the committed reservation in a new transaction, verify `itemId` and `quantity` match the original payload, and return the previous outcome. If the same key arrives with a different payload, return a conflict error instead of treating it as a valid duplicate.

Do not rely solely on `findByRequestId()` followed by `save()` for deduplication. Two concurrent transactions can both observe that the key does not yet exist. A database unique constraint is the final safeguard under concurrent arrivals.

## 12. Rollback and Transaction Boundaries

Spring rolls back transactions by default when a transactional method throws a `RuntimeException` or `Error`. Because `InsufficientStockException` in the example extends `RuntimeException`, prior changes within the same transaction roll back.

For checked exceptions, Spring does not roll back by default in all cases. If business rules require a rollback, declare `rollbackFor` explicitly:

~~~java
@Transactional(rollbackFor = ReservationRejectedException.class)
public void reserveForOrder(Long itemId, int quantity)
        throws ReservationRejectedException {
    // load item, validate and update
}
~~~

Do not catch an exception and return normally within the same transaction if the transaction has been marked rollback-only. When error handling and retries are needed, let the exception escape the transactional worker, then catch it in a coordinator without an enclosing transaction.

For a use case that reserves stock and creates an order in the same database, explicitly decide whether both operations must be atomic or proceed via a `PENDING` state confirmed later. If they share a single local transaction, a stock reservation failure must roll back order creation as required. If split across services/databases, use outbox/Saga patterns and idempotency rather than assuming local `@Transactional` covers distributed systems.

## 13. Testing Against a Real Database with Testcontainers

H2 is useful for fast tests, but locking behavior, isolation levels, deadlocks, timeouts, and generated SQL can differ from production databases. For critical concurrency tests, run against the same database engine used in deployment.

Example PostgreSQL Testcontainers setup:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class InventoryConcurrencyIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void testRunsAgainstPostgres() {
        // Reuse the two-transaction test from the previous section.
    }
}
~~~

This is the container configuration; place the concurrency test from the earlier section inside this test class or a shared base class. If the project uses Flyway or Liquibase, let migrations create the schema just like production instead of relying on Hibernate DDL generation.

Testcontainers does not make a concurrency test correct on its own. You still need two independent transactions, a barrier synchronizing reads, flush/commit to trigger conflict detection, and a fresh transaction to verify final state.

## 14. Required Test Scenarios

Beyond two requests both reserving 7 out of 10, test:

1. Single successful request: `available = 10`, reserve 4, remaining is 6.
2. Insufficient stock: `available = 3`, request 7, business exception thrown and database remains 3.
3. Two transactions on the same version: both read 10, both reserve 7; exactly one commits and one hits a conflict.
4. Retry after conflict: new transaction reads `available = 3` and rejects the request for 7.
5. Pessimistic lock: second transaction waits, then reads the updated quantity and rejects if insufficient.
6. Conditional `UPDATE`: two concurrent requests; total updated units never exceed available stock.
7. Deadlock/timeout: simulate lock error; transaction aborts and bounded retry runs.
8. Duplicate request with the same idempotency key: creates only one reservation and deducts stock once.
9. Same key, different payload: second request is rejected.
10. Rollback: an error after creating the reservation but before commit rolls back both the reservation and the stock change.
11. Post-commit read: verify state using a new transaction, not just an entity sitting in an old persistence context.

Never assert that T1 always wins. Only assert that the outcome set contains one success and one conflict. Tests must set timeouts on barriers and `Future`s so synchronization bugs do not hang the suite indefinitely.

## 15. Common Pitfalls

- Using one transaction or one `EntityManager` across both threads, failing to simulate true concurrency.
- Not synchronizing read timing so the two transactions never observe the same version.
- Calling `save()` without flushing or waiting for commit, causing errors to surface outside the expected test assertion block.
- Catching optimistic locking exceptions inside a transaction and continuing to use stale entities.
- Retrying with the old entity instead of reloading in a new transaction.
- Treating a conflict as out-of-stock; only after reloading can you know whether enough stock remains.
- Retrying `InsufficientStockException` or constraint violations as if they were transient errors.
- Checking only the entity in the persistence context without re-reading the database in a fresh transaction.
- Using `@Version` while another bulk/native update path bypasses version checks.
- Holding pessimistic locks too long or locking multiple rows in inconsistent orders.
- Missing idempotency keys, allowing a timed-out post-commit retry to deduct stock a second time.
- Drawing production locking conclusions solely from H2 without testing on the real database.

## 16. Implementation Checklist

- Define invariants: `available` is non-negative and reservations never exceed sellable stock.
- Choose `@Version` when conflicts are infrequent and retries are acceptable.
- Use `PESSIMISTIC_WRITE` when operations must be serialized and transactions can stay short.
- Use conditional `UPDATE` when the rule fits cleanly in a single atomic statement.
- Ensure all write paths follow the same version, audit, and event rules.
- Bound retries for conflicts/deadlocks in a fresh transaction, with backoff and jitter.
- Never retry out-of-stock business errors or permanent data errors.
- Use idempotency keys and unique constraints to guard against duplicate requests.
- Test rollbacks and re-read committed outcomes.
- Run integration tests with a production-equivalent database via Testcontainers.
- Monitor conflict rate, retry count, lock waits, deadlocks, timeouts, and out-of-stock rejections.

The expected outcome of the simulation is that only one of the two requests reserves 7 units from an available stock of 10. The other transaction detects that the version changed; when it retries against fresh data, it sees only 3 remaining and rejects the request. Combining transaction boundaries, concurrency control, and idempotency enables Spring Data JPA to protect inventory even under concurrent traffic or client retries.