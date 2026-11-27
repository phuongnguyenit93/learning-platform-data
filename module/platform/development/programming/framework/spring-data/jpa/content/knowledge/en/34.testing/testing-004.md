# Rollback in Tests and Bugs Masked by Test Transactions

An integration test can run through a service, repository, and database and still fail to catch errors that only occur at commit time. A common cause is that Spring TestContext opens a transaction wrapping the test method and rolls it back by default when the test ends. Services using `REQUIRED` propagation join the test's transaction, so when the service returns, the transaction has not actually committed yet.

This can mask constraints checked on commit, errors that only appear when the transaction completes, `UnexpectedRollbackException`, and listeners requiring `AFTER_COMMIT`. To test transaction boundaries accurately, you must distinguish test-managed transactions from application-managed transactions, flush proactively when SQL errors need early detection, and perform real commits when verifying post-commit behavior.

## 1. Two Types of Transactions in Spring Tests

### Test-Managed Transaction

Spring TestContext provides transaction support for tests via `TransactionalTestExecutionListener`. When a test class or test method is annotated with `@Transactional` and an appropriate transaction manager exists, the framework starts a test-managed transaction before the test method runs.

Common characteristics:

- The transaction opens before the test method.
- `@BeforeEach`, the test method, and standard `@AfterEach` run inside that transaction.
- By default, the transaction is rolled back when the test finishes.
- The transaction outcome can be changed using `@Commit`, `@Rollback`, or the `TestTransaction` API.
- `@BeforeTransaction` and `@AfterTransaction` callbacks run outside the test-managed transaction, before the transaction begins and after it ends, respectively.

`@DataJpaTest` is configured as transactional by default and rolls back after each test. `@SpringBootTest` does not automatically make every test method transactional; a test only gets a test-managed transaction when appropriately configured, such as with `@Transactional` on the class or method.

### Application-Managed Transaction

This is a transaction opened by application code via the Spring transaction interceptor, typically using `@Transactional` on a service method.

```java
@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        // Validate business rules and save aggregate.
        orders.save(Order.create(command));
    }
}
```

If the test has no surrounding transaction, calling `createOrder()` through the Spring proxy opens a transaction, performs the work, and commits before the method returns successfully. Errors occurring during commit can be thrown straight to the caller, so the test can use `assertThrows` around the service call.

If the test already opened a transaction and the service uses the default `REQUIRED` propagation, the service joins the existing transaction. When the service returns, it does not commit the physical transaction because the test-owned transaction is still active.

## 2. Why Can Default Rollback Mask Bugs?

Consider a repository-style test:

```java
@DataJpaTest
class UserRepositoryTest {

    @Autowired
    private UserRepository users;

    @Test
    void duplicateEmailShouldFail() {
        users.save(new User("same@example.com"));
        users.save(new User("same@example.com"));

        // Test ends; Spring rolls back the test transaction by default.
    }
}
```

If the database only checks unique constraints when SQL is sent or at commit time, the test above may fail to detect the error. JPA can hold changes in the persistence context and defer SQL until flush or commit. Because the test transaction rolls back by default, the framework can terminate the transaction with a rollback rather than a commit; errors that only surface on commit will not be observed as the test intends.

Another scenario is a service with nested transactions using `REQUIRED` propagation:

1. The test opens a transaction.
2. The test calls a `@Transactional` service; the service joins the test transaction.
3. The service calls a `REQUIRED` child service.
4. The child service fails; the interceptor marks the shared transaction as rollback-only.
5. The parent service catches the exception and returns normally.
6. Test assertions may still execute without a commit at the service boundary.
7. When the test finishes, the framework rolls back the test transaction. There is no outermost service commit to throw `UnexpectedRollbackException` where the test is observing.

This is why a test can pass even though the exact same service call in production throws an exception when the service's transaction tries to commit.

## 3. Distinguishing flush and commit

`flush()` and `commit()` represent two different moments.

| Operation | What Happens? | Ends Transaction? |
|---|---|---|
| `EntityManager.flush()` | Synchronizes pending changes into SQL within the current transaction | No |
| `EntityTransaction.commit()` / transaction manager commit | Completes the transaction; the provider synchronizes remaining changes before database commit | Yes |
| Rollback | Discards changes belonging to the transaction per database semantics | Yes |

### Flush Helps Catch Many Errors Early

In JPA tests, calling `flush` after persist/update operations causes SQL to execute immediately, exposing errors such as:

- Unique constraint violations.
- NOT NULL or foreign key constraint violations.
- SQL or data type errors.
- Optimistic locking failures when update statements execute.

Example with `TestEntityManager`:

```java
@DataJpaTest
class UserRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private UserRepository users;

    @Test
    void duplicateEmailViolatesUniqueConstraint() {
        users.save(new User("same@example.com"));
        users.save(new User("same@example.com"));

        assertThrows(
            RuntimeException.class,
            () -> entityManager.flush()
        );
    }
}
```

This example illustrates where to check for the error. In real tests, expect the specific exception returned by your database/provider and the application's exception translation layer, such as the appropriate constraint violation exception. Do not keep `RuntimeException` as the final expected type if the exact exception can be determined.

The test still rolls back after completion. Flush only causes SQL to run early so errors are detected inside the test method; it does not check conditions that are only verified at commit.

### Flush Does Not Catch Every Commit-Time Error

Some errors are only checked by the database at commit, such as constraints declared as deferred. Other behaviors also only occur when the transaction completes:

- The transaction manager detects the transaction was marked rollback-only and throws `UnexpectedRollbackException`.
- `@TransactionalEventListener(phase = AFTER_COMMIT)` only runs after a successful commit.
- Transaction synchronization callbacks at the completion phase.
- Errors or responses from the database commit operation itself.

Therefore, if the goal is to verify a real commit, a transaction must actually commit.

## 4. Approach 1: Let the Service Manage Its Own Transaction

The clearest way to test errors at the service boundary is not to open a test-managed transaction. Call a `@Transactional` service method from a non-transactional test.

```java
@SpringBootTest
class OrderServiceTransactionTest {

    @Autowired
    private OrderService orderService;

    @Test
    void shouldExposeCommitFailureAtServiceBoundary() {
        assertThrows(
            UnexpectedRollbackException.class,
            () -> orderService.processOrder()
        );
    }
}
```

In this example, the test method does not have `@Transactional`. When `processOrder()` finishes, the service's transaction interceptor performs a commit. If the transaction is already rollback-only, `UnexpectedRollbackException` can be thrown straight at the proxy call and caught by `assertThrows`.

This approach is suitable for testing:

- Service transaction boundaries.
- Errors during transaction commit.
- Rollback rules and propagation between services.
- Listeners running after commit.
- Actual behavior observed by callers of the service.

If using `@DataJpaTest`, the test slice usually has a default transaction. You can move service transaction tests to `@SpringBootTest` without `@Transactional`, or configure the test method not to join a test-managed transaction using a propagation supported by Spring Test, such as `NOT_SUPPORTED`. Ensure the service is invoked through its Spring proxy.

## 5. Approach 2: Explicitly End the Test Transaction With TestTransaction

When you need to keep the test-managed transaction for setup or repository checks, Spring provides `TestTransaction` in package `org.springframework.test.context.transaction`.

Commonly used API methods:

- `TestTransaction.isActive()`: checks whether a test-managed transaction is currently active.
- `TestTransaction.flagForCommit()`: marks the current transaction to commit when ended.
- `TestTransaction.flagForRollback()`: marks the current transaction to roll back when ended.
- `TestTransaction.end()`: ends the current transaction according to the set flag.
- `TestTransaction.start()`: starts a new test-managed transaction if the test configuration supports it.

Example testing a listener that only runs after commit:

```java
@SpringBootTest
@Transactional
class OrderAfterCommitTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderEventProbe eventProbe;

    @Test
    void listenerRunsAfterExplicitCommit() {
        orderService.createAndConfirm();

        assertFalse(eventProbe.wasCalled());

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertTrue(eventProbe.wasCalled());
    }
}
```

In the example, `orderService` joins the test-managed transaction via `REQUIRED`. The listener is configured with `@TransactionalEventListener(AFTER_COMMIT)`, so it has not run before the test ends the transaction. `TestTransaction.end()` commits according to the flag; after the commit succeeds, the listener is invoked.

If you need to verify an exception thrown during commit, place the assertion around `TestTransaction.end()`:

```java
@Test
@Transactional
void commitFailureIsVisibleWhenEndingTestTransaction() {
    service.performOperationThatMarksTransactionRollbackOnly();

    TestTransaction.flagForCommit();

    assertThrows(
        UnexpectedRollbackException.class,
        TestTransaction::end
    );
}
```

Adjust the specific exception according to the actual failure and transaction manager. Once commit fails, the test transaction has been requested to end; do not assume it remains active for further persistence operations. Check transaction status and clean up data in a separate transaction if needed.

## 6. Approach 3: Using @Commit or @Rollback(false)

Spring TestContext rolls back test-managed transactions by default. You can request a commit when the test finishes:

```java
@SpringBootTest
@Transactional
@Commit
class CommitTest {
    // Test transaction is committed when finished.
}
```

`@Rollback(false)` also requests a commit instead of a rollback:

```java
@Test
@Transactional
@Rollback(false)
void persistsData() {
    repository.save(new User("commit@example.com"));
}
```

These annotations are useful when confirming data actually committed or using data after the test. However, commit occurs during the teardown phase after the test method has returned. Therefore, if committing raises an exception, the test method usually cannot wrap `assertThrows` directly around that commit moment.

When you need to catch and verify a commit exception inside the test body, use `TestTransaction.flagForCommit()` and `TestTransaction.end()` to end the transaction right where assertions can be made.

Do not use `@Commit` indiscriminately because data can remain after the test and affect other tests. Use a dedicated test database, unique keys, or explicit cleanup mechanisms.

## 7. Testing @TransactionalEventListener and Callbacks

A test transaction that rolls back by default does not trigger an `AFTER_COMMIT` listener. This is correct behavior: if the transaction does not commit, the listener must not run.

Example listener:

```java
@Component
public class OrderListener {

    private final NotificationService notifications;

    public OrderListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmed event) {
        notifications.send(event.orderId());
    }
}
```

Separate tests can be written:

| Scenario | Expectation |
|---|---|
| Test transaction ends with rollback | `AFTER_COMMIT` listener does not run |
| Test transaction is committed | `AFTER_COMMIT` listener runs |
| Listener uses `BEFORE_COMMIT` | Runs before commit inside the transaction |
| Listener uses `AFTER_ROLLBACK` | Runs when the transaction rolls back |
| Listener uses `AFTER_COMPLETION` | Runs after the transaction ends in either outcome |

If testing a post-commit listener inside a test-managed transaction, end the transaction explicitly using `TestTransaction.end()` after calling `flagForCommit()`.

Note: a standard `@EventListener` does not wait for commit. It is called as soon as the event is published. Therefore, a test transaction that eventually rolls back may already have executed a standard listener and caused side effects. If a side effect is only allowed upon commit, use `@TransactionalEventListener(AFTER_COMMIT)`.

## 8. Default @Rollback and Related Annotations

| Annotation/API | Meaning |
|---|---|
| `@Transactional` on test | Asks Spring TestContext to manage a transaction for the test |
| `@Rollback` | Chooses rollback or commit when the test transaction ends; defaults to `true` |
| `@Commit` | Equivalent to requesting `@Rollback(false)` |
| `@BeforeTransaction` | Runs before the test-managed transaction begins |
| `@AfterTransaction` | Runs after the test-managed transaction finishes |
| `TestTransaction` | Controls the test's transaction directly inside the test method |

Standard `@BeforeEach` and `@AfterEach` run inside the test-managed transaction when one is opened. If setup/cleanup must happen outside the transaction, use transaction-specific callbacks like `@BeforeTransaction` and `@AfterTransaction`.

Not every attribute of `@Transactional` is applied by Spring TestContext the same way as application transactions. Attributes such as isolation, timeout, and readOnly are not fully supported for test-managed transactions; consult the documentation for your Spring version when special configuration is needed. `NOT_SUPPORTED` or `NEVER` propagation can be used to request that a test not run inside a test-managed transaction.

## 9. Propagation and UnexpectedRollbackException in Tests

The default propagation of `@Transactional` is `REQUIRED`. If the test already opened a transaction, services and repositories usually join that transaction.

Suppose a child service throws an unchecked exception and the transaction interceptor marks the shared transaction as rollback-only. The parent service catches the exception and continues. In production, if the parent service owns the transaction, when it completes Spring attempts to commit and can throw `UnexpectedRollbackException`.

But in a test with an outer transaction:

- The parent service joins the test's transaction.
- When the parent service returns, the physical transaction still belongs to the test.
- The test transaction rolls back by default in teardown.
- The commit-boundary exception may not appear during the service call.

To test this failure properly, use a non-transactional test calling the service via its proxy:

```java
@SpringBootTest
class UnexpectedRollbackIntegrationTest {

    @Autowired
    private ParentService parentService;

    @Test
    void exposesUnexpectedRollbackAtServiceCommit() {
        assertThrows(
            UnexpectedRollbackException.class,
            parentService::execute
        );
    }
}
```

Ensure the test has no `@Transactional` on the class or method. If using a test slice with a default transaction, reconfigure the test's transaction or use `TestTransaction` to end the transaction explicitly.

### Caution With REQUIRES_NEW

A child service using `Propagation.REQUIRES_NEW` creates its own transaction. The child transaction can commit even if the outer test transaction ultimately rolls back. Therefore, default test rollback does not guarantee cleanup of data written by an independent transaction.

If a test involves `REQUIRES_NEW`, control data using an isolated database, unique IDs, and dedicated cleanup. Do not assume test rollback will roll back every transaction opened during the test.

## 10. Testing Database Constraints and Commit-Only Failures

When a test needs to verify constraints:

1. Persist or update entities.
2. Call `flush()` to force SQL to be sent to the database.
3. Assert the exception at flush if the constraint is checked during SQL execution.
4. If the constraint is checked deferred at commit, perform a real commit and catch the error at the commit boundary.
5. Inspect database state after the failed transaction using a new transaction/context if needed.

Example checking a unique constraint at flush time:

```java
@DataJpaTest
class UserConstraintTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void duplicateEmailFailsWhenFlushed() {
        entityManager.persist(new User("duplicate@example.com"));
        entityManager.persist(new User("duplicate@example.com"));

        assertThrows(
            RuntimeException.class,
            () -> entityManager.flush()
        );
    }
}
```

This is an illustrative skeleton. In real projects, replace `RuntimeException` with the specific exception returned by your provider and exception translation layer. The test transaction will be rolled back after the test.

If you want to verify an error that only occurs at commit, `flush` cannot substitute for `commit`. Use a test without an outer transaction so the service commits on its own, or use `TestTransaction.end()` after `flagForCommit()`.

## 11. Cleanup and Isolation Between Tests

Default rollback keeps test data clean without deleting rows one by one, but it only works for data belonging to the test transaction itself.

Some operations are not rolled back with the test transaction:

- Independent transactions from `REQUIRES_NEW`.
- Transactions executed on another thread.
- Sending emails, making HTTP calls, writing files, or other side effects outside the database.
- Data written by other systems during the test.

For tests that actually commit or have side effects:

- Use a dedicated database or per-suite schema/container.
- Generate data with unique identifiers to avoid colliding with other tests.
- Clean up data in a separate transaction or reset the database after the test.
- Use fakes/mocks for external systems if the test target is purely application logic.
- Do not depend on test execution order.

`@Sql` can be used to run setup/cleanup scripts; choose the appropriate execution phase and transaction mode so cleanup executes outside a rolled-back or committed transaction.

## 12. Checklist for Choosing a Testing Approach

| Testing Goal | Appropriate Approach |
|---|---|
| Testing basic repository persist/query | `@DataJpaTest` with default rollback |
| Catching SQL constraints checked at flush | Call `TestEntityManager.flush()` or `EntityManager.flush()` |
| Catching errors at service commit | Test without outer `@Transactional`, calling service proxy |
| Testing `AFTER_COMMIT` listeners | Commit test transaction with `TestTransaction` or call service from non-transactional test |
| Verifying listener does not run on rollback | Keep default rollback and verify listener receives no event |
| Testing a rollback-only transaction | Call service at real transaction boundary and assert `UnexpectedRollbackException` |
| Tests involving `REQUIRES_NEW` | Use an isolated database and separate cleanup |
| Testing deferred constraints | Commit a real transaction, not just flush |

## 13. Process for Investigating Tests That Pass Locally but Fail in Production

When tests pass but production encounters errors at commit:

1. Check whether the test class/method has `@Transactional`, or uses a test slice with default transactions like `@DataJpaTest`.
2. Determine whether the service uses `REQUIRED` propagation and is joining the test's transaction.
3. Look for operations only synchronized on flush/commit, such as unique constraints, foreign keys, optimistic locking, or transaction synchronization.
4. Try flushing explicitly to surface SQL errors earlier.
5. If the failure still occurs only at commit, run the test without an outer transaction or end the test transaction with `TestTransaction`.
6. Check whether a listener is using `@EventListener` when business logic requires `AFTER_COMMIT`.
7. Inspect independent transactions and non-database side effects; default rollback does not clean them up automatically.

## Conclusion

Spring TestContext's test-managed transactions roll back by default after a test. When a service uses `REQUIRED`, it may merely join the test's transaction and never actually commit at the service boundary. As a result, commit-time failures, `UnexpectedRollbackException`, and `AFTER_COMMIT` listeners can be masked.

Use `flush` to catch SQL errors early during statement execution; use non-transactional tests or `TestTransaction` to verify real commits. Choose `@Commit` when you want teardown to commit and remember to clean up data. Always design tests to match the exact transaction boundaries the application runs with in production.