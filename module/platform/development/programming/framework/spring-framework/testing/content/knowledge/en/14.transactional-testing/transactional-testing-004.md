# @Commit and @Rollback for Verifying Data Persistence Behavior

Spring Test typically runs each transactional test method inside a test-managed transaction. By default, this transaction is rolled back when the test ends so test data does not affect other tests. That mechanism is very convenient for database tests, yet sometimes we need to verify that data is actually committed or prove that an operation is rolled back.

The two annotations `@Commit` and `@Rollback` allow choosing the final outcome of a test-managed transaction. `@Commit` requests a commit when the test finishes; `@Rollback` requests a rollback and defaults to `true`. They are particularly useful when testing repositories, services with `@Transactional`, transactional events, and persistence rules. To confirm state after commit or rollback, you must observe the database after the test transaction has ended, rather than merely reading the entity back within the same persistence context.

## 1. Spring Test's default transaction

The Spring TestContext Framework supports transactions for tests via `TransactionalTestExecutionListener`. When a test class or test method is annotated with `@Transactional`, Spring starts a test-managed transaction before running the test and ends the transaction after the test method completes.

By default, that transaction is rolled back. This means insert, update, or delete statements executed during the test will not be committed to the database after the test finishes, provided they participate in the same test-managed transaction.

Example with Spring Boot `@DataJpaTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomerDuringTest() {
        Customer customer = customerRepository.save(
                new Customer("lan@example.test")
        );

        // The test can use the saved entity while its transaction is active.
    }
}
```

`@DataJpaTest` opens a transaction for each test method by default and rolls back when the test finishes. Thus, the test can write data to verify the repository without leaving records behind afterward.

With `@SpringBootTest`, transactions are not automatically enabled for every test. If you want a test-managed transaction, annotate the test class or method with `@Transactional`:

```java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTests {
    // Each test method runs in a test-managed transaction.
}
```

When a test does not have a transaction managed by Spring Test, `@Commit` or `@Rollback` has no test transaction whose outcome to decide. Therefore, clearly verify whether the test is actually running in a test-managed transaction.

## 2. @Rollback: keeping the database clean by default

`@Rollback` belongs to the `org.springframework.test.annotation` package:

```java
import org.springframework.test.annotation.Rollback;
```

This annotation indicates whether the test-managed transaction should be rolled back when the test ends. The default value is `true`:

```java
@Test
@Rollback
void doesNotCommitChanges() {
    // Changes made in the test-managed transaction are rolled back.
}
```

Because rollback is already the default behavior of transactional tests, writing `@Rollback` explicitly is usually only needed to clarify test intent or override a class-level commit configuration.

It can be declared at the class level to apply to transactional test methods in the class:

```java
@DataJpaTest
@Rollback
class CustomerRepositoryTests {
    // Transactional test methods roll back by default.
}
```

`@Rollback(false)` means do not roll back, so the test-managed transaction will be committed upon completion:

```java
@Test
@Rollback(false)
void commitsChanges() {
    // The test-managed transaction is committed after the method.
}
```

When wanting to clearly express persisting data, `@Commit` is usually more readable than `@Rollback(false)`.

## 3. @Commit: committing the transaction when the test ends

`@Commit` belongs to the same `org.springframework.test.annotation` package and is equivalent to `@Rollback(false)`:

```java
import org.springframework.test.annotation.Commit;
```

Example:

```java
@Test
@Commit
void commitsCustomer() {
    customerRepository.save(new Customer("lan@example.test"));
}
```

If the test runs inside a test-managed transaction, Spring commits the transaction after the test method finishes. Data that participated in the transaction will be committed according to the governing transaction manager.

`@Commit` can be declared at the method or class level. When declared on a class, transactional test methods in that class will commit according to that configuration. You can use `@Rollback` on a specific method to request rollback for that method; method-level configuration takes precedence over class-level configuration.

Example of a class that commits by default, while one test method still rolls back:

```java
@DataJpaTest
@Commit
class CustomerRepositoryCommitTests {

    @Test
    void commitsCustomer() {
        // This method commits.
    }

    @Test
    @Rollback
    void rollsBackTemporaryCustomer() {
        // This method explicitly rolls back.
    }
}
```

Do not attach `@Commit` to the entire test suite just to test a single persistence case. Committing tests can leave records behind, alter data read by other tests, or cause unique constraint errors on reruns. Limit commits to tests that need to verify commit behavior and manage the data created by the test.

## 4. Distinguishing @Commit, @Rollback, and the default

| Configuration | Outcome of test-managed transaction when test ends |
|---|---|
| `@Transactional` without outcome annotation | Rollback |
| `@Transactional` + `@Rollback` | Rollback |
| `@Transactional` + `@Rollback(true)` | Rollback |
| `@Transactional` + `@Rollback(false)` | Commit |
| `@Transactional` + `@Commit` | Commit |
| No test-managed transaction | No test transaction for the annotation to decide |

`@Commit` and `@Rollback` control the outcome of the test-managed transaction created by Spring Test. They are not replacement annotations for transaction boundaries in application code. For example, `@Transactional` on a service still determines how the service participates in a transaction when called; `@Commit` decides the outcome of the transaction managed by the test framework.

## 5. Verifying data within the same transaction vs. after commit

A common pitfall is that reading an entity immediately after calling `save()` does not prove the transaction committed.

Inside a test-managed transaction, the statement:

```java
Customer saved = customerRepository.save(customer);
```

may place the entity into the persistence context. When calling `findById()` within the same persistence context, JPA can return the managed entity without re-reading from the database. Even if SQL has already been sent to the database, the transaction may still not have committed.

Therefore, distinguish three levels of verification:

1. **Entity is managed in the persistence context:** inspect the object or entity state in memory.
2. **SQL has been flushed to the database:** use `flush()` to force the persistence context to synchronize changes into SQL statements within the current transaction.
3. **Transaction has committed:** observe data after the test transaction ends, for example via `@AfterTransaction` or a new transaction.

### 5.1. Using flush and clear to test a round trip to the database

With JPA, you can use `EntityManager.flush()` and `clear()`:

```java
@DataJpaTest
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customerRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void persistsAndReloadsCustomerInsideTransaction() {
        Customer customer = customerRepository.save(
                new Customer("lan@example.test")
        );

        entityManager.flush();
        entityManager.clear();

        Customer reloaded = customerRepository.findById(customer.getId())
                .orElseThrow();

        assertEquals("lan@example.test", reloaded.getEmail());
    }
}
```

`flush()` forces JPA to send changes to the database in the open transaction. `clear()` evicts entities from the persistence context so the next query must reload the data. This test verifies writing and reading through the database within the same transaction, though the transaction will still roll back by default when the test ends.

`flush()` is not synonymous with commit. If a constraint or SQL statement fails, `flush()` can make the error appear immediately during the test instead of waiting until the transaction ends. This is a useful way to catch persistence errors, though it does not yet prove the data is durably committed.

### 5.2. Verifying state after the transaction ends

To prove commit or rollback, read the database after the test-managed transaction has finished. Spring Test provides `@AfterTransaction` for a callback that runs after the test's transaction.

Example using `@Commit`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@JdbcTest
class CustomerCommitTests {

    private final String email = "commit-" + UUID.randomUUID() + "@example.test";

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    @Commit
    void commitsInsertedCustomer() {
        jdbcTemplate.update(
                "insert into customer(email) values (?)",
                email
        );
    }

    @AfterTransaction
    void verifiesCommittedRow() {
        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );

        assertThat(count).isEqualTo(1);

        jdbcTemplate.update(
                "delete from customer where email = ?",
                email
        );
    }
}
```

This example assumes the schema has a `customer` table and an `email` column. `@JdbcTest` provides a test-managed transaction; `@Commit` requests a commit after the test method; `@AfterTransaction` re-reads the database after that transaction ends. A unique email value helps avoid data collisions across runs. The callback also deletes the committed record so the test does not leave persistent data behind.

In real-world tests, if you need to inspect via a repository instead of direct SQL, you can inject a repository or `JdbcTemplate` to read after the transaction. The key is that the verification read must occur after the test transaction has ended and must not reuse a managed entity from the previous persistence context.

### 5.3. Verifying rollback after a test

For rollback, you can omit `@Rollback` since it is the default, and then use `@AfterTransaction` to verify the record is gone:

```java
@JdbcTest
class CustomerRollbackTests {

    private final String email = "rollback-" + UUID.randomUUID() + "@example.test";

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackInsertedCustomerByDefault() {
        jdbcTemplate.update(
                "insert into customer(email) values (?)",
                email
        );

        Integer countInsideTransaction = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );
        assertThat(countInsideTransaction).isEqualTo(1);
    }

    @AfterTransaction
    void verifiesRowWasRolledBack() {
        Integer countAfterTransaction = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );

        assertThat(countAfterTransaction).isZero();
    }
}
```

Inside the test method, the record can be read because it is still within the current transaction. After the test ends, Spring rolls back the transaction; the `@AfterTransaction` callback checks that the record is no longer in the database.

`@AfterTransaction` is called outside the test-managed transaction. Therefore, JDBC operations in the callback do not join the previously rolled-back or committed transaction. If the system has a special transaction manager or datasource, make sure the post-check read actually observes the updated database.

## 6. Testing services with @Transactional

In an application, services typically manage transactions with `@Transactional`:

```java
@Service
class CustomerService {

    private final CustomerRepository repository;

    CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email) {
        return repository.save(new Customer(email));
    }
}
```

If the test also runs in a test-managed transaction with the default `REQUIRED` propagation, the service's transaction usually joins the transaction already opened by the test. When the `register()` method returns, the transaction has not necessarily committed yet; the outer transaction managed by the test is still active.

Example:

```java
@SpringBootTest
@Transactional
class CustomerServiceTests {

    @Autowired
    private CustomerService customerService;

    @Test
    void registersCustomer() {
        Customer customer = customerService.register("lan@example.test");

        assertNotNull(customer.getId());
    }
}
```

This test confirms that the service performs the operation inside a transaction, yet the test's transaction will roll back upon completion. It does not prove the service committed independently as soon as the method returned.

If you want to verify durable persistence through the test-managed transaction, you can use `@Commit`:

```java
@SpringBootTest
@Transactional
class CustomerServiceCommitTests {

    @Autowired
    private CustomerService customerService;

    @Test
    @Commit
    void commitsCustomerRegisteredByService() {
        customerService.register("lan@example.test");
    }
}
```

To verify that the data actually exists after commit, combine with `@AfterTransaction` as in the earlier example. Checking only the returned ID or that the entity remains in the persistence context is not enough to prove the transaction committed.

## 7. Testing rollback behavior when a service throws an exception

An important goal of transaction testing is confirming that changes are rolled back when an error occurs. Suppose a service saves an order and then performs a business step that can fail:

```java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    OrderService(
            OrderRepository orderRepository,
            InventoryService inventoryService
    ) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public void placeOrder(Order order) {
        orderRepository.save(order);
        inventoryService.reserve(order);
    }
}
```

If `reserve()` throws an unchecked exception and the transaction is managed properly, the transaction can be marked rollback-only. The test can verify that the record does not exist after the transaction ends.

One distinction to make is whether the exception escapes the transaction boundary or is caught and handled inside the service. If the service catches the exception, continues, and does not mark rollback-only, the transaction may commit normally. Rollback rules also depend on the exception type and the transaction manager's rollback configuration.

`@Commit` does not force a transaction to commit if the transaction has already been marked rollback-only. If a transaction is marked rollback-only, requesting a commit at the end of the test may result in a rollback or a commit error depending on the situation. Therefore, inspect the actual transaction state and exception rather than using `@Commit` as a way to bypass the application's rollback rules.

## 8. Using TestTransaction to control transactions inside a test

In some situations, you need to commit or roll back right in the middle of a test method, then continue performing assertions or another testing phase. Spring Test provides `TestTransaction` to control the test-managed transaction programmatically.

Commonly used methods:

| Method | Meaning |
|---|---|
| `TestTransaction.isActive()` | Checks whether a test-managed transaction is currently active |
| `TestTransaction.flagForCommit()` | Marks the current transaction to commit when ended via `end()` |
| `TestTransaction.flagForRollback()` | Marks the current transaction to roll back when ended via `end()` |
| `TestTransaction.isFlaggedForRollback()` | Checks whether the transaction is currently flagged for rollback |
| `TestTransaction.end()` | Ends the current transaction according to the configured commit/rollback flag |
| `TestTransaction.start()` | Starts a new test-managed transaction if permitted by the lifecycle |

Example committing mid-test:

```java
@SpringBootTest
@Transactional
class CustomerTransactionTests {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void commitsThenReadsCommittedData() {
        String email = "commit-now@example.test";
        customerRepository.save(new Customer(email));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );
        assertThat(count).isEqualTo(1);

        TestTransaction.start();
    }
}
```

`flagForCommit()` does not commit immediately; it sets the flag for the next `end()`. After `end()`, the transaction has ended and the test can query the committed data. `start()` opens a new test-managed transaction if the test needs to continue operating inside a transaction; this new transaction still follows the default rollback rule when the test ends unless flagged for commit.

If you only need to commit the entire test at the end of the method, `@Commit` is more concise. Use `TestTransaction` when you need multiple transaction phases within the same test or need to verify data right after commit while continuing other operations.

Do not call `TestTransaction.end()` if no test-managed transaction is active. You can check with `TestTransaction.isActive()` before controlling the transaction.

## 9. @BeforeTransaction and @AfterTransaction callbacks

Spring Test provides two callbacks for running work before and after a test-managed transaction:

- `@BeforeTransaction`: runs before the test's transaction starts.
- `@AfterTransaction`: runs after the test's transaction has ended by commit or rollback.

They differ from JUnit Jupiter's `@BeforeEach` and `@AfterEach`. For transactional tests, JUnit's `@BeforeEach` and `@AfterEach` callbacks normally run inside the test-managed transaction; `@BeforeTransaction` and `@AfterTransaction` are designed for operations outside that transaction.

Example:

```java
@DataJpaTest
class OrderTransactionTests {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeTransaction
    void verifyInitialState() {
        // Runs before the test-managed transaction begins.
    }

    @Test
    @Commit
    void insertsOrder() {
        // Insert data inside the test-managed transaction.
    }

    @AfterTransaction
    void verifyFinalState() {
        // Runs after the test transaction has committed.
    }
}
```

Callback methods must follow Spring Test rules and take no parameters. They are useful when you need to prepare data independent of the test transaction or check database state after the transaction completes.

If using callbacks to clean up committed data, ensure the cleanup operation runs outside the completed transaction and can commit on its own. With multiple transaction managers or databases, check that the callback uses the right datasource and transaction boundary.

## 10. How does transaction propagation affect rollback?

`@Commit` and `@Rollback` only decide the outcome of the test-managed transaction. Independent transactions created by application code can have their own lifecycle.

### 10.1. PROPAGATION_REQUIRED

This is the default propagation of `@Transactional`. If the test has opened a transaction and the service uses `REQUIRED`, the service joins the existing transaction. When the test rolls back, changes in the shared transaction also roll back.

### 10.2. PROPAGATION_REQUIRES_NEW

`REQUIRES_NEW` suspends the current transaction and opens an independent transaction. If the new transaction commits successfully, its data can persist even when the outer test-managed transaction rolls back.

Example:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditEvent(AuditEvent event) {
    auditRepository.save(event);
}
```

If a test invokes this method inside a test transaction and then leaves the default rollback, the separate audit transaction may still have committed. Do not assume the test's rollback will remove all changes created by `REQUIRES_NEW`.

When testing code using this propagation, use an isolated test database, uniquely identified data, and explicit cleanup. You can verify the audit data after the transaction as in the `@AfterTransaction` example.

### 10.3. NOT_SUPPORTED and NEVER

With test-managed transactions, `@Transactional(propagation = Propagation.NOT_SUPPORTED)` requests that the test run without a managed test transaction. `NEVER` requires no transaction; if a transaction exists, execution will be incompatible with that configuration.

When a test has no test-managed transaction, `@Commit` or `@Rollback` has no transaction to complete. Called repository or service methods may open their own transactions according to their configuration. Read the exact transaction boundary of each component before concluding that data will roll back.

### 10.4. Nested transactions and savepoints

`NESTED` can use savepoints if supported by the transaction manager and database. Partial rollback capability depends on the transaction manager; do not infer that all JPA configurations support nested transactions identically. If a test relies on savepoints, confirm the actual transaction manager supports them and verify the outcome against the database.

## 11. After-commit behavior and transactional events

Some logic only runs after a transaction commits, such as `@TransactionalEventListener` with the default `AFTER_COMMIT` phase:

```java
@Component
class OrderEventListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        // Notify another system after the transaction commits.
    }
}
```

If the test-managed transaction rolls back by default, the `AFTER_COMMIT` listener will not be invoked as it would when a transaction actually commits. Thus, a test that simply publishes an event and checks whether the listener sent a notification can fail or fail to test the right flow if the transaction has not committed.

You can use `@Commit` to verify that the listener runs after commit:

```java
@SpringBootTest
@Transactional
class OrderEventListenerTests {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private NotificationGateway notificationGateway;

    @Test
    @Commit
    void sendsNotificationAfterOrderCommit() {
        orderService.createOrder("CUS-1");

        // Verify in a suitable after-commit observation point.
    }
}
```

If you need to verify interactions right after commit, you can use `TestTransaction.flagForCommit()` and `TestTransaction.end()` inside the test, then verify the mock or check state produced by the listener. This makes it clear when the listener is triggered.

Not every event listener runs after commit. Regular `@EventListener` runs when the event is published; `@TransactionalEventListener` runs according to its configured transaction phase. Tests must reflect the actual listener type the application uses.

## 12. Limitations of @Transactional on tests

`@Transactional` on tests is handled by the Spring TestContext Framework and has several differences compared to `@Transactional` on ordinary services.

Important attributes such as the transaction manager can be specified via `value` or `transactionManager`. For test-managed transactions, Spring Test supports only a limited set of attributes; `propagation` only supports `NOT_SUPPORTED` and `NEVER` to control whether a test-managed transaction is used. Attributes such as `isolation`, `timeout`, `readOnly`, `rollbackFor`, and `noRollbackFor` are not used to configure test-managed transactions in the same way as transactions on business methods.

If you need to test a service's rollback rules, let the service's transaction boundary decide and design the test accordingly. Do not put `rollbackFor` on a test method and expect Spring Test to apply that rule to the test transaction.

Another limitation is that test transactions are normally bound to the thread executing the test. Some preemptive timeout assertions can run the test body in another thread. When that happens, database operations on the new thread may not join the test-managed transaction and data may not roll back as expected.

Example requiring caution:

```java
assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
    customerRepository.save(new Customer("lan@example.test"));
});
```

If the test framework runs the lambda on another thread, the transaction bound to the original thread does not automatically propagate to the new thread. With transactional tests, prefer non-preemptive timeouts or explicit transaction management for work running on another thread.

## 13. Common mistakes

**Thinking save() is synonymous with commit.** `save()` may only update the persistence context. Use `flush()` to force SQL execution and use `@AfterTransaction` or a new transaction to confirm post-commit results.

**Thinking @Commit works when there is no test transaction.** The annotation only decides the outcome of a test-managed transaction. Check whether `@Transactional` or a test slice annotation opens a transaction.

**Using @Commit for all repository tests.** Data can persist after tests, affect later tests, and make reruns unstable. Keep default rollback and only commit in tests that need to prove commit behavior.

**Only re-reading the entity in the same persistence context.** JPA may return a managed object without querying the database. Use `flush()` and `clear()` to test a round trip, then check after the transaction to confirm commit.

**Assuming @Rollback will revert REQUIRES_NEW.** An independent transaction can commit separately and survive the rollback of the outer transaction. Check the service's propagation.

**Assuming @Commit overrides rollback-only.** If the transaction has already been marked rollback-only, requesting a commit at the end of the test cannot turn it into a valid transaction to commit.

**Using @Transactional on a test to verify after-commit events without committing.** An `AFTER_COMMIT` listener only runs when the transaction actually commits. Use `@Commit` or `TestTransaction` if the goal is to verify that phase.

**Using @AfterEach to check data after rollback.** `@AfterEach` usually runs inside the test-managed transaction. To check state after the transaction ends, use `@AfterTransaction`.

**Using preemptive timeouts in transactional tests without considering threads.** Test transactions are normally bound to the test runner thread. Work on another thread can escape the transaction and leave data behind.

## 14. Workflow for designing tests that verify commit or rollback

When persistence behavior needs verification, clearly identify what the test aims to prove:

1. **Checking an entity or in-memory result:** direct assertions on the object may suffice.
2. **Checking SQL and mapping:** call `flush()`, then `clear()`, and re-read within the same transaction.
3. **Checking a real commit:** use `@Commit` or `@Rollback(false)`, then read data after the transaction using `@AfterTransaction` or a new transaction.
4. **Checking a real rollback:** keep the default rollback or use `@Rollback`, then confirm the data is gone after the transaction.
5. **Checking after-commit events:** end the transaction by committing before verifying `AFTER_COMMIT` listeners.
6. **Checking independent transactions:** inspect propagation such as `REQUIRES_NEW`, transaction managers, and operations outside the test transaction.
7. **Keeping test data isolated:** use unique IDs/emails, a separate database, or explicit cleanup for committed data.

For example, a typical repository test should use default rollback to avoid leaving data behind. A test specifically verifying commit should use `@Commit` and a post-transaction callback to prove data exists after the transaction. A rollback test should check database state after Spring ends the transaction, not only inside the method prior to rollback.

`@Commit` and `@Rollback` control the outcome of test-managed transactions in Spring Test. Transactional tests roll back by default; `@Commit` or `@Rollback(false)` requests a commit, while `@Rollback` requests a rollback. To confirm whether data has been committed or rolled back, observe the database after the transaction ends using `@AfterTransaction`, or explicitly end the transaction with `TestTransaction`. At the same time, account for `flush()`, the persistence context, propagation such as `REQUIRES_NEW`, after-commit events, and data lifecycle so the test proves the persistence behavior the application needs to safeguard.
