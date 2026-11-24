# Verifying Post-Commit Behavior Using a Separate Transaction

When testing the data layer, a successful `save()` call is not enough to prove data was durably persisted. An object may still sit inside JPA's persistence context, SQL statements may not have been sent to the database yet, or the transaction may roll back after the test ends. To verify post-commit behavior, let the writing transaction complete, and then read the data back in a new transaction.

This technique is especially useful when testing repositories, `@Transactional` services, data constraints checked at commit, database triggers, or handlers that run only after a transaction commits.

## Why Must You Read in a New Transaction?

JPA manages loaded or modified entities inside a persistence context. If a test saves an entity and immediately reads it back in the same persistence context, Hibernate may return the managed object without reloading committed state from the database. That result proves the application sees changes from the current transaction itself, yet does not prove the transaction committed successfully and another transaction can see the data.

Distinguish three points in time:

| Point in Time | What Happens | What Is Not Yet Proven |
|---|---|---|
| `save()` | Entity is placed into managed state or marked for persistence | SQL may not have executed; transaction has not committed |
| `flush()` | Persistence context synchronizes changes down to the database via SQL | Transaction can still roll back; other transactions typically cannot see changes yet |
| `commit()` | Transaction ends successfully and changes are committed per database semantics | Must read from a new transaction to verify post-commit observability |

`flush()` is no substitute for `commit()`. An `INSERT` that has executed can still be rolled back. Therefore, checking immediately after `flush()` in the same transaction is not post-commit verification.

Spring TestContext also has an important characteristic: tests annotated with `@Transactional` normally run inside a test-managed transaction and roll back by default when the test ends. This isolates test data, yet also means a `save()` in a test does not automatically produce committed data.

## Verification Workflow

A post-commit test should have two independent transaction boundaries:

1. A write transaction that creates or updates data. This transaction must commit successfully before the next step begins.
2. A verification transaction that starts after the write transaction has ended. It queries by primary key or business key and asserts the stored values.

Reading again in a new transaction ensures the test uses a fresh persistence context following JPA's normal transaction lifecycle. If the goal is directly verifying table state while also bypassing the ORM's second-level cache, `JdbcTemplate` can be used to query inside the verification transaction.

## Approach 1: Using `TransactionTemplate`

`TransactionTemplate` lets you define transaction boundaries directly inside the test. Each `execute()` call runs its callback inside a transaction managed by `PlatformTransactionManager`. When the callback returns normally, the template commits the transaction before returning the result to the caller.

The example below uses Spring Boot, Spring Data JPA, and AssertJ. `Order` is an illustrative entity with a `code` field; `OrderRepository` extends `JpaRepository<Order, Long>`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderCommitIntegrationTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void readsOrderInANewTransactionAfterCommit() {
        TransactionTemplate writeTransaction =
                new TransactionTemplate(transactionManager);

        Long orderId = writeTransaction.execute(status -> {
            Order saved = orderRepository.saveAndFlush(
                    new Order("ORD-203")
            );
            return saved.getId();
        });

        assertThat(orderId).isNotNull();

        try {
            // writeTransaction.execute() already committed before reaching here.
            TransactionTemplate verificationTransaction =
                    new TransactionTemplate(transactionManager);
            verificationTransaction.setReadOnly(true);

            String storedCode = verificationTransaction.execute(status ->
                    orderRepository.findById(orderId)
                            .orElseThrow()
                            .getCode()
            );

            assertThat(storedCode).isEqualTo("ORD-203");
        } finally {
            // Data is already committed, so clean it up in a separate transaction.
            new TransactionTemplate(transactionManager)
                    .executeWithoutResult(status ->
                            orderRepository.deleteById(orderId)
                    );
        }
    }
}
```

This test must not place `@Transactional` on the class or method. If an outer test transaction exists, `TransactionTemplate`'s default `REQUIRED` propagation can join the existing transaction. In that case, the write call would not create a commit boundary as the example requires.

`saveAndFlush()` in the example ensures SQL is sent to the database and generally guarantees the ID is generated before the callback returns. The commit itself still occurs after the callback, managed by `TransactionTemplate`. If commit fails, `execute()` throws an exception and the verification step does not run.

## Approach 2: Using `TestTransaction` with `@DataJpaTest`

`@DataJpaTest` normally opens a test-managed transaction automatically and rolls it back when the test finishes. When you want to keep this structure yet still verify post-commit data, Spring Test provides `TestTransaction` to control the test's transaction.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class OrderRepositoryCommitTest {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Test
    void readsCommittedOrderAfterEndingTestTransaction() {
        Order saved = orderRepository.saveAndFlush(
                new Order("ORD-203")
        );
        Long orderId = saved.getId();

        // Mark the current test transaction for commit, then end it.
        TestTransaction.flagForCommit();
        TestTransaction.end();

        // Verification transaction starts after the test transaction has committed.
        TransactionTemplate verificationTransaction =
                new TransactionTemplate(transactionManager);
        verificationTransaction.setReadOnly(true);

        try {
            String storedCode = verificationTransaction.execute(status ->
                    orderRepository.findById(orderId)
                            .orElseThrow()
                            .getCode()
            );

            assertThat(storedCode).isEqualTo("ORD-203");
        } finally {
            // The test transaction committed, so created data must be deleted.
            new TransactionTemplate(transactionManager)
                    .executeWithoutResult(status ->
                            orderRepository.deleteById(orderId)
                    );
        }
    }
}
```

`TestTransaction.flagForCommit()` only flags the decision for ending the transaction; `TestTransaction.end()` is what actually ends and commits it. After `end()`, the `TransactionTemplate` call does not join the ended test transaction and instead opens a fresh verification transaction.

Because the written data committed, `@DataJpaTest`'s default rollback mechanism cannot automatically undo that write. The example explicitly deletes the entity in a separate transaction. In larger test suites, ensure cleanup still runs if an assertion fails, such as moving cleanup into `finally` or using a suitable fixture cleanup mechanism.

Another option is annotating the test with `@Commit` and placing verification reads inside an `@AfterTransaction` method. `@AfterTransaction` callbacks are invoked by Spring after the test-managed transaction has ended. Do not place verification inside the test method body if the transaction only commits automatically after that method returns.

## Using `REQUIRES_NEW` at the Right Moment

`Propagation.REQUIRES_NEW` forces Spring to open an independent transaction, suspending the current transaction if one exists. However, using `REQUIRES_NEW` by itself does not make uncommitted data visible.

For example, if the write transaction is still open and the test calls a read service annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)`, Spring suspends the write transaction and opens the read transaction. The read transaction cannot see the write transaction's uncommitted changes under normal database isolation rules. Only after the read transaction ends does the write transaction resume.

Thus, the right sequence is:

```text
Call write service
    |
    v
Write transaction commits successfully
    |
    v
Call read service / open verification transaction
    |
    v
Read data and assert
```

If no outer transaction exists, default `REQUIRED` propagation is enough for `TransactionTemplate` or a repository method to start a new transaction. Choose `REQUIRES_NEW` only when you must guarantee an independent transaction boundary while a caller transaction may already be active, and ensure the data to be read has already committed beforehand.

## Common Testing Mistakes

| Approach | Problem | Resolution |
|---|---|---|
| Calling `save()` and asserting on the just-saved entity | May only check the state of a managed in-memory object | Re-read by ID in a new transaction |
| Calling `flush()` and assuming data committed | SQL ran, yet the transaction can still roll back | Finish the write transaction successfully before verifying |
| Re-reading inside the same test-managed transaction | Persistence context may return the in-memory entity; other transactions cannot see it yet | Commit or end the test transaction, then start a new transaction |
| Using `REQUIRES_NEW` while the write transaction is still open | Independent read transaction cannot see uncommitted data | Let the write transaction commit before reading |
| Putting `@Transactional` on the test and expecting data to persist afterward | Spring TestContext rolls back test-managed transactions by default | Use `TestTransaction`, `@Commit` with `@AfterTransaction`, or explicit transaction control |
| Omitting committed data from cleanup | Test data can affect subsequent tests | Delete data in a cleanup transaction or use an isolated test database |

## When Direct Database Verification Is Needed

A new transaction normally creates a new persistence context, yet JPA/Hibernate's second-level cache can still participate in reads. If a test requires verifying actual table values, `JdbcTemplate` can be used inside the verification transaction. The following example assumes `jdbcTemplate` is injected and `orderId` is the ID of the newly committed record:

```java
TransactionTemplate verificationTransaction =
        new TransactionTemplate(transactionManager);
verificationTransaction.setReadOnly(true);

String storedCode = verificationTransaction.execute(status ->
        jdbcTemplate.queryForObject(
                "select code from orders where id = ?",
                String.class,
                orderId
        )
);

assertThat(storedCode).isEqualTo("ORD-203");
```

A JDBC query bypasses JPA's persistence context and entity cache. Use the actual table name, column names, and data types from the project schema. The verification transaction must still start after the write transaction commits.

## Verifying Post-Commit Handlers

For listeners using `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, publishing an event inside a transaction does not prove the listener executed. Tests must let the event-publishing transaction commit successfully, then verify the side effect produced by the listener. If the side effect writes to the same database, read it in a new transaction using the approaches above.

If the listener also uses `@Async`, committing only triggers asynchronous processing; the test must wait for completion using a synchronization mechanism or an appropriately bounded wait. Avoid fixed `Thread.sleep()` calls because they do not guarantee the listener has finished and make tests slow and flaky.

## Completion Criteria for the Test

- The write transaction ended with a successful commit before verification began.
- Verification queries execute in a new transaction and read by ID or a stable business key.
- Assertions check values loaded from the data layer, not merely entities sitting in the old persistence context.
- The test has an explicit cleanup strategy for committed data.
- When needing to prove table state, the test uses JDBC queries or an appropriate read mechanism to avoid masking by ORM caches.

Only when these criteria are met does a test verify that changes crossed the commit boundary and are observable from an independent transaction.
