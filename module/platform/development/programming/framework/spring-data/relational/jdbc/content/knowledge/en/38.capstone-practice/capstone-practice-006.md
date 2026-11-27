# Simulating Two Transactions Updating the Same Order

In a **Spring Data Relational JDBC** application, two requests can read the same order, modify its state in memory, and save nearly simultaneously. If both transactions write without checking the version of the data they read, the later write can overwrite the result of the earlier write. This is a **lost update**.

This lab simulates two independent transactions loading the same `PurchaseOrder` aggregate. Both Transaction A and Transaction B read the current version. A updates and commits first; B proceeds to save its stale snapshot. When the aggregate uses `@Version`, Spring Data JDBC detects that the version no longer matches and throws `OptimisticLockingFailureException`. The test uses two threads, two transactions, and latches to control execution order, then verifies the final state in the database.

## 1. The scenario to simulate

Suppose an order has status `PENDING` and version `0`. Two requests arrive nearly simultaneously:

- Request A confirms the order.
- Request B cancels the order.

Both load the same initial state:

~~~text
Database:
  id = 100
  status = PENDING
  version = 0

Transaction A reads: PENDING, version 0
Transaction B reads: PENDING, version 0
~~~

Without a conflict-detection mechanism, the two transactions can execute:

~~~text
T1: UPDATE purchase_order SET status = 'CONFIRMED' WHERE id = 100
T2: UPDATE purchase_order SET status = 'CANCELLED'  WHERE id = 100
~~~

If T1 commits first and T2 commits second, the final status is `CANCELLED`. T1's `CONFIRMED` change is overwritten without any error. This outcome can violate business rules because an already confirmed order is typically no longer allowed to be cancelled through the normal flow.

## 2. Lost update without optimistic locking

First, consider an entity without a version field:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CANCELLED;
    }
}
~~~

Two service methods can each load the aggregate and save it:

~~~java
@Transactional
public void confirm(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.confirm();
    orders.save(order);
}

@Transactional
public void cancel(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.cancel();
    orders.save(order);
}
~~~

These methods run in separate transactions when invoked through a Spring proxy. However, transaction boundaries alone do not guarantee detection of stale writes. If the update lacks a version-check condition, two transactions can overwrite each other.

### 2.1. Timeline of a lost update

~~~text
Time  Transaction A                 Transaction B                 Database
----  -------------                 -------------                 --------
1     BEGIN                                                        status=PENDING
2     SELECT order ------------------------------------------------> version not used
3                                   BEGIN
4                                   SELECT order ------------------> status=PENDING
5     UPDATE status=CONFIRMED -------------------------------------> status=CONFIRMED
6     COMMIT
7                                   UPDATE status=CANCELLED ------> status=CANCELLED
8                                   COMMIT
~~~

Without a version predicate, the database has no way to know B is writing from a stale snapshot. The update succeeds as long as the row with that ID exists.

## 3. Enabling optimistic locking with @Version

Spring Data JDBC supports optimistic locking through a `@Version` property on the aggregate root:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String orderNumber;
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = OrderStatus.CANCELLED;
    }
}
~~~

For new entities, `version` is initialized according to Spring Data JDBC's mechanism. On update, the framework uses the version that was read to verify the row is still at that version, while incrementing the version when the write succeeds.

Conceptually, the SQL looks like:

~~~sql
UPDATE purchase_order
SET status = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
~~~

If one transaction has already incremented the version from `0` to `1`, another transaction still trying to update with `version = 0` will update zero rows. Spring Data JDBC translates that result into `OptimisticLockingFailureException`.

### 3.1. Timeline with @Version

~~~text
Initial database: id=100, status=PENDING, version=0

T1: BEGIN
T1: SELECT -> status=PENDING, version=0

T2: BEGIN
T2: SELECT -> status=PENDING, version=0

T1: UPDATE ... WHERE id=100 AND version=0
    -> 1 row updated, version becomes 1
T1: COMMIT

T2: UPDATE ... WHERE id=100 AND version=0
    -> 0 rows updated
T2: OptimisticLockingFailureException
T2: ROLLBACK

Final database: status from T1, version=1
~~~

Optimistic locking does not hold locks while a user is editing. It detects conflicts at write time, which is well-suited when conflicts are relatively rare and transactions are short.

## 4. Repository and test fixture

Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

In an integration test, create an initial order and save it with the repository:

~~~java
PurchaseOrder saved = orders.save(
        PurchaseOrder.pending("PO-100", OrderStatus.PENDING)
);

Long orderId = saved.getId();
~~~

Use the object returned by `save`, because the generated ID and version are updated based on persistence results. Depending on entity design, a `pending(...)` factory can accept an order number and initialize the appropriate status and version.

## 5. Why do we need two threads and two transactions?

Spring transactions are typically bound to the current thread. Calling two repository methods sequentially on the same thread inside one transaction does not simulate two independent transactions.

To build a concurrency test:

- Use two separate threads.
- Have each thread call `TransactionTemplate.execute(...)` to create its own transaction.
- Configure a connection pool with at least two concurrent connections.
- Use a `CountDownLatch` to ensure both transactions have read the same version before A writes.
- Signal B to proceed only after transaction A has committed.

Do not annotate the test method with `@Transactional` if you want to observe independent transactions across worker threads. A transaction bound to the test thread does not automatically propagate to worker threads.

## 6. Deterministic testing with TransactionTemplate

The example below uses Spring Boot, JUnit 5, and Testcontainers or an equivalent test database. Entities, repositories, schema migrations, and imports are assumed to exist.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class PurchaseOrderConcurrencyTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Test
    void rejectsSecondWriterWhenItUsesAnOldVersion() throws Exception {
        PurchaseOrder saved = orders.save(
                PurchaseOrder.pending("PO-100", OrderStatus.PENDING)
        );
        Long orderId = saved.getId();

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        CountDownLatch transactionBHasRead = new CountDownLatch(1);
        CountDownLatch transactionAHasCommitted = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> writerB = executor.submit(() ->
                    tx.execute(status -> {
                        PurchaseOrder stale = orders.findById(orderId)
                                .orElseThrow();

                        transactionBHasRead.countDown();
                        await(transactionAHasCommitted);

                        stale.cancel();
                        orders.save(stale);
                        return null;
                    })
            );

            Future<?> writerA = executor.submit(() -> {
                tx.execute(status -> {
                    await(transactionBHasRead);

                    PurchaseOrder current = orders.findById(orderId)
                            .orElseThrow();
                    current.confirm();
                    orders.save(current);
                    return null;
                });

                // execute() returns only after transaction A has committed.
                transactionAHasCommitted.countDown();
            });

            writerA.get(10, TimeUnit.SECONDS);

            assertThatThrownBy(() -> writerB.get(10, TimeUnit.SECONDS))
                    .isInstanceOf(ExecutionException.class)
                    .hasCauseInstanceOf(OptimisticLockingFailureException.class);

            PurchaseOrder finalOrder = orders.findById(orderId)
                    .orElseThrow();

            assertThat(finalOrder.getStatus())
                    .isEqualTo(OrderStatus.CONFIRMED);
            assertThat(finalOrder.getVersion())
                    .isEqualTo(saved.getVersion() + 1);
        } finally {
            executor.shutdownNow();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for transaction");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Concurrency test interrupted", ex);
        }
    }
}
~~~

This is an integration test skeleton. Add the appropriate imports for your entities, repository, and domain exceptions, and ensure the test configuration does not open an enclosing outer transaction.

### 6.1. How is execution order controlled?

1. Thread B opens transaction B, reads the order at its initial version, and counts down `transactionBHasRead`.
2. Thread B waits on `transactionAHasCommitted`; transaction B still holds the snapshot it read.
3. Thread A starts transaction A after B has read.
4. A reads the order, changes status, and calls `save`.
5. A's `TransactionTemplate.execute` completes and commits; then A counts down `transactionAHasCommitted`.
6. B resumes, mutates its stale object, and calls `save`.
7. The version in the database has incremented, so B's update fails to match the old version and throws an optimistic locking exception.
8. Transaction B rolls back.

The test does not rely on scheduler speed or random sleeps. The two latches deterministically mark when each transaction has read and when the winning transaction has committed.

### 6.2. Why is a connection pool with at least two connections needed?

Transaction B holds a connection while waiting for A to commit. If the pool only has one connection, A cannot acquire a connection to run; the test may time out or deadlock at the pool layer.

Ensure the datasource pool has at least two connections available for this test. The database container must also allow two concurrent sessions.

### 6.3. Disabling the outer transaction of @DataJdbcTest

`@DataJdbcTest` by default runs each test method inside a Spring Test-managed transaction. Simply omitting `@Transactional` from the method is not enough to disable this transaction. Because a concurrency test needs two independent worker transactions and a committed fixture, the example places `@Transactional(propagation = Propagation.NOT_SUPPORTED)` on the test class.

Then `orders.save` for creating the fixture executes in a normal repository transaction and completes before the two workers start. Each worker uses `TransactionTemplate` to open its own transaction on its own thread.

If you want tests with automatic rollback, use a separate test class for simple setup/cleanup. For concurrency tests, clean up data after both workers finish or use a dedicated database per test class. If the test-managed transaction is not disabled, worker threads do not inherit the test thread's transaction and may not see the uncommitted fixture.

## 7. Catching and asserting OptimisticLockingFailureException

In the example, `Future.get()` wraps the worker thread's exception in an `ExecutionException`. Thus the test asserts the cause:

~~~java
assertThatThrownBy(() -> writerB.get(10, TimeUnit.SECONDS))
        .isInstanceOf(ExecutionException.class)
        .hasCauseInstanceOf(OptimisticLockingFailureException.class);
~~~

In a regular service, the exception can be caught and translated into a business result:

~~~java
@Transactional
public void cancel(Long orderId) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();
    order.cancel();

    try {
        orders.save(order);
    } catch (OptimisticLockingFailureException ex) {
        throw new OrderChangedByAnotherRequestException(orderId, ex);
    }
}
~~~

Note that the transaction may already be marked rollback-only when a persistence operation fails. Do not catch the exception and continue writing other changes in the same transaction as if nothing went wrong.

## 8. Result when @Version is omitted

To observe a lost update, remove `@Version` from the entity and run the exact same two-transaction scenario:

- B reads `PENDING`.
- A reads `PENDING`.
- A saves `CONFIRMED` and commits.
- B saves `CANCELLED` from its stale snapshot and commits.

If the SQL update relies solely on ID, both updates can succeed. The final outcome depends on which transaction commits last.

A lost-update test should verify that B overwrote A's state to demonstrate the risk. Then add `@Version` and re-run the optimistic locking test to confirm B is rejected.

## 9. Distinguishing optimistic locking from isolation levels

Isolation levels and optimistic locking solve related but distinct problems.

| Mechanism | Role |
| --- | --- |
| READ COMMITTED | A query reads only committed data as of the query start per database semantics |
| REPEATABLE READ | Can keep a more stable snapshot within a transaction, depending on the database |
| SERIALIZABLE | Database aims to ensure outcomes equivalent to a serial execution; may raise serialization failures |
| `@Version` | Verifies the aggregate version that was read when performing an update |
| Pessimistic row lock | Locks rows within a transaction to block concurrent writers per database locking mechanics |

Do not assume choosing a higher isolation level completely replaces version checks. Behavior varies by database and transaction pattern; optimistic locking explicitly expresses the requirement that an aggregate may only be written if its version has not changed.

## 10. If you want to simulate pessimistic locking

An alternative is locking the row upon read, for example via SQL:

~~~sql
SELECT id, status, version
FROM purchase_order
WHERE id = :id
FOR UPDATE;
~~~

The database holds the row lock until the transaction commits or rolls back. Another writer trying to lock or update the same row may have to wait.

This is a database-dependent mechanism and must run inside a transaction. It can be implemented via a custom repository method using `JdbcTemplate`/`NamedParameterJdbcTemplate` to read the row with `FOR UPDATE`, and then perform the update within the same transaction.

Pessimistic locking fits when conflicts are frequent or the business requires serializing operations. It increases lock hold times and the risk of blocking or deadlocks. Optimistic locking is typically simpler when conflicts are infrequent.

## 11. Handling conflicts in business logic

When B receives an optimistic locking failure, it should not automatically overwrite with its stale snapshot. There are several options:

### 11.1. Return conflict to the caller

Appropriate for an order editing screen: notify the user that the data has changed and ask them to reload.

### 11.2. Reload and reapply the command

If the command can be safely applied to the latest state:

1. Roll back the failed transaction.
2. Open a new transaction.
3. Load the latest aggregate.
4. Check invariants.
5. Reapply the command.
6. Save and handle conflict if it occurs again.

Never retry inside a failed or rollback-only transaction. Every retry attempt must have a fresh transaction.

### 11.3. Use idempotent operations

If the command is marking payment received or recording an already-processed event, designing an idempotency key or unique constraint can be more appropriate than overwriting a state with an old snapshot.

### 11.4. Do not retry indefinitely

Set a limit on retry attempts, backoff, and metrics. If conflicts happen constantly, the aggregate may be too hot or transactions too long; revisit the design.

## 12. Common pitfalls when writing concurrency tests

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Running two calls sequentially on one thread | Does not create two concurrent independent transactions | Use two separate threads and transactions |
| Using sleep to guess ordering | Tests flake depending on scheduler | Use `CountDownLatch` or `CyclicBarrier` |
| Both threads share one transaction context | Does not simulate two connections/transactions | Use `TransactionTemplate` inside each thread |
| Test method has an outer transaction | Uncommitted fixture is invisible to workers | Disable outer transaction or commit setup first |
| Connection pool only has one connection | Second transaction cannot run | Provide at least two connections |
| Entity lacks `@Version` | Stale updates can overwrite | Add a version property to the aggregate root |
| Catching exception and continuing same transaction | Transaction may be rollback-only | End the transaction and retry in a new transaction |
| Only asserting the exception | Does not prove final state is valid | Reload aggregate and assert status/version |
| Using H2 while production uses another DB | Locking/isolation differences can invalidate test | Test on production database via Testcontainers |
| Threads hang when test fails | Test suite runs indefinitely | Apply timeouts on latches/futures and shut down executor |

## 13. Extending the simulation to aggregates with children

If `PurchaseOrder` has `OrderLine`s, both transactions may modify both the root and children. With `@Version` on the aggregate root, the root's version serves as the concurrency guard for aggregate updates across the persistence boundary.

Example:

~~~java
@Transactional
public void changeLineQuantity(Long orderId, Long lineId, int quantity) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();
    order.changeLineQuantity(lineId, quantity);
    orders.save(order);
}
~~~

Concurrency tests should verify:

- Both transactions read the same root version.
- The winning transaction saves root/children and increments version.
- The losing transaction cannot save its stale aggregate snapshot.
- The final child state matches the winning transaction.

Do not assert only root status. Reload the child collection to ensure no data was overwritten or lost.

## 14. End-to-end lab workflow

1. Create the `purchase_order` table with ID, status, and version.
2. Declare the aggregate root with `@Id` and `@Version`.
3. Create a repository extending `CrudRepository`.
4. Insert an order in `PENDING` status.
5. Use two threads to open two independent transactions.
6. Have both transactions read the same order version.
7. Have transaction A update and commit.
8. Have transaction B proceed to save its stale snapshot.
9. Verify B receives `OptimisticLockingFailureException`.
10. Reload the order and verify status and version belong to transaction A.
11. Remove `@Version` in a test variant to observe a lost update.
12. Run tests against the same database type as production.

## Key takeaways

Two transactions can read the same aggregate version and make two conflicting decisions. If updates rely only on ID, the later-committing transaction can overwrite the earlier result (lost update). Add `@Version` to the aggregate root so Spring Data JDBC checks the version on save. The first transaction increments the version; the second transaction, holding the stale version, fails to update any row and receives `OptimisticLockingFailureException`.

To simulate this reliably, use two threads, two independent transactions, and at least two database connections. `TransactionTemplate` creates a transaction inside each thread; `CountDownLatch` coordinates execution so both read before the winning transaction commits. Then assert the stale writer's exception and re-read the database to confirm the final status and version. Do not use sleeps to guess ordering, do not keep an outer test transaction active, and do not retry inside a rollback-only transaction. When handling conflicts, reload the aggregate in a new transaction, check invariants, and reapply the command within bounded retries if the business allows.

## References

- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction-bound Events and Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers for Java](https://java.testcontainers.org/)
