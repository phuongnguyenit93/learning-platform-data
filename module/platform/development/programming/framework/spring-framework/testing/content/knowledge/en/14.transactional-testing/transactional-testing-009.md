# TestTransaction for ending, starting, and flagging commit

Spring TestContext supports transactions bound to each test method. When a test is annotated with `@Transactional` and has a matching transaction manager, Spring normally starts a test-managed transaction before running the test and rolls back that transaction after the test ends. The default rollback mechanism keeps test data from persisting after each method.

There are cases where you need to verify data after an actual commit, or end the current transaction and open a new transaction right inside the same test method. Spring provides the `TestTransaction` utility class for these operations. Tests can inspect transaction status, flag commit or rollback, end the current transaction, and start a new test-managed transaction.

## Learning objectives

After this lesson, you can:

- Explain test-managed transactions and the role of `TransactionalTestExecutionListener`.
- Understand the methods `isActive`, `isFlaggedForRollback`, `flagForCommit`, `flagForRollback`, `end`, and `start`.
- Distinguish flagging a commit from the moment the commit actually occurs.
- Proactively commit the test's transaction and then open a new transaction to verify data.
- Override the default commit/rollback decision from `@Commit` or `@Rollback`.
- Handle cases where a test has no active transaction.
- Understand limitations of test transactions with HTTP requests running on other threads and independent transactions.
- Clean up data after an explicit commit so other tests remain independent.

## 1. What is a test-managed transaction?

Spring TestContext can manage transactions for tests via `TransactionalTestExecutionListener`. When a test class or test method is annotated with `@Transactional`, the listener starts a transaction before the test method runs and ends the transaction after the method finishes.

Example:

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void savesAnOrderInsideTestTransaction() {
        orderRepository.save(new Order("ORD-1001"));

        assertEquals(1, orderRepository.count());
    }
}
~~~

In a standard configuration, the test's transaction is rolled back after the method. Therefore, records created in the test are not retained after the test finishes, provided the write operations actually participate in that transaction.

Three concepts must be distinguished:

| Concept | Meaning |
|---|---|
| Test-managed transaction | Transaction started and ended around the test by Spring TestContext |
| Application-managed transaction | Transaction managed by application code or a service's transaction boundary |
| External resource transaction | Transaction on a database, message broker, or other system with its own management mechanism |

`TestTransaction` controls the current test-managed transaction. It is not a general-purpose API for committing every running transaction in the application, nor does it replace `TransactionTemplate` or `PlatformTransactionManager` in production code.

Test-managed transactions are normally bound to the test execution thread. While the test method runs inside a transaction, repositories or services participating in the same transaction manager can see the test's uncommitted changes.

## 2. Why control transactions with TestTransaction?

Automatic rollback is a good choice for most integration tests. However, some behaviors only surface after a transaction ends:

- The database only fires certain constraints or triggers on commit.
- Committed data needs to be verified as readable in a new transaction.
- Code behavior needs to be tested once the previous transaction has finished.
- A new transaction needs to be created within the same test method to verify post-commit state.
- Part of the setup data needs to be committed before continuing to test another flow.

For instance, simply calling a repository and asserting in the same transaction may read data from the persistence context or current transaction. That result does not always prove the data was committed and is visible from another transaction.

`TestTransaction` allows ending the current transaction according to the flagged decision. Afterward, the test can start a new transaction to verify the committed data or perform a subsequent portion of work.

~~~mermaid
flowchart TD
    A["Spring starts test-managed transaction"] --> B["Test writes data"]
    B --> C["TestTransaction.flagForCommit()"]
    C --> D["TestTransaction.end()"]
    D --> E["Transaction is committed"]
    E --> F["TestTransaction.start()"]
    F --> G["New transaction starts"]
    G --> H["Reads and verifies committed data"]
    H --> I["Marks for rollback"]
    I --> J["TestTransaction.end()"]
~~~

The key point is that `flagForCommit` only changes the transaction completion decision. The actual commit takes place when the transaction is ended with `end`.

## 3. Methods of TestTransaction

`TestTransaction` resides in the package:

~~~java
import org.springframework.test.context.transaction.TestTransaction;
~~~

All main methods are static:

| Method | Function |
|---|---|
| `TestTransaction.isActive()` | Checks whether a test-managed transaction is currently active |
| `TestTransaction.isFlaggedForRollback()` | Checks whether the current transaction is flagged for rollback |
| `TestTransaction.flagForCommit()` | Marks the current transaction to commit when ended |
| `TestTransaction.flagForRollback()` | Marks the current transaction to roll back when ended |
| `TestTransaction.end()` | Ends the current test-managed transaction per the commit/rollback flag |
| `TestTransaction.start()` | Starts a new test-managed transaction |

These methods are only meaningful in tests integrated with Spring TestContext that have transaction support. If no test-managed transaction is active, operations requiring a current transaction may throw `IllegalStateException`.

Check `isActive()` before acting in tests that have multiple branches or could run with varying transaction configurations.

## 4. Inspecting the current transaction with isActive and isFlaggedForRollback

`isActive()` indicates whether a test-managed transaction is currently active.

~~~java
@Test
@Transactional
void checksTransactionState() {
    assertTrue(TestTransaction.isActive());
}
~~~

In a test annotated with `@Transactional`, the listener has usually already started the transaction before the test method runs. Thus, `isActive()` normally returns `true` in the method body.

`isFlaggedForRollback()` indicates whether the current transaction is marked to roll back or commit upon completion. Under the default behavior of test-managed transactions, the transaction is normally flagged for rollback.

~~~java
@Test
@Transactional
void rollsBackByDefault() {
    assertTrue(TestTransaction.isActive());
    assertTrue(TestTransaction.isFlaggedForRollback());
}
~~~

If the test is annotated with `@Commit` or `@Rollback(false)`, the default decision will be commit. You can use `isFlaggedForRollback()` to confirm the current state before calling `end`.

Do not confuse this state with the transaction having ended. A transaction can still be active while already flagged for commit; data is only committed when the transaction is ended.

## 5. Flagging commit with flagForCommit

`flagForCommit()` tells Spring to commit the test-managed transaction when the transaction is ended.

~~~java
@Test
@Transactional
void commitsTheCurrentTestTransaction() {
    orderRepository.save(new Order("ORD-1001"));

    TestTransaction.flagForCommit();

    assertFalse(TestTransaction.isFlaggedForRollback());

    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

Sequence:

1. Spring starts the transaction before the test method.
2. The test writes data inside the transaction.
3. `flagForCommit()` changes the completion decision from rollback to commit.
4. `end()` closes the transaction and performs the commit.
5. After `end()` completes, there is no longer an active test-managed transaction.

`flagForCommit()` does not commit immediately at the moment it is called. If the test calls this method and then continues writing data, those subsequent changes still belong to the current transaction and will be committed when `end()` is called.

Because committing can leave data in the database after the test ends, use it intentionally. Tests should have a data cleanup strategy or use a dedicated database/schema.

## 6. Flagging rollback with flagForRollback

`flagForRollback()` sets the current transaction to the rollback decision upon completion.

~~~java
@Test
@Transactional
void explicitlyMarksTransactionForRollback() {
    orderRepository.save(new Order("ORD-1002"));

    TestTransaction.flagForRollback();

    assertTrue(TestTransaction.isFlaggedForRollback());

    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

With standard test-managed transactions, rollback is already the default. Calling `flagForRollback()` is useful when:

- The test previously called `flagForCommit()`.
- The test has a `@Commit` or `@Rollback(false)` annotation.
- The test wants to make the rollback decision explicit at a specific point.
- The test starts a new transaction and wants to guarantee that the new transaction rolls back.

`flagForRollback()` likewise only sets the flag. Actual rollback occurs when the transaction is ended via `end`.

## 7. Ending a transaction with end

`end()` finishes the active test-managed transaction. Spring uses the current rollback/commit flag to decide the outcome.

~~~java
@Test
@Transactional
void endsTheCurrentTransaction() {
    orderRepository.save(new Order("ORD-1003"));

    TestTransaction.flagForRollback();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

If the transaction is flagged for rollback, `end()` rolls back. If the transaction is flagged for commit, `end()` commits.

When no transaction is active, a current transaction cannot be ended. Therefore, avoid calling `end()` repeatedly without checking state.

After `end()` completes:

- The current transaction is no longer active.
- The persistence context attached to the ended transaction is no longer a place to continue writing data as before.
- Subsequent repository operations may open their own transactions according to repository configuration.
- The test can call `start()` to open a new test-managed transaction if the method supports transactions.

Do not use `end()` as a way to close the entire `ApplicationContext` or end every transaction in the application. It only controls the current test-managed transaction.

## 8. Starting a new transaction with start

`start()` starts a new test-managed transaction within the same test method.

~~~java
@Test
@Transactional
void endsOneTransactionAndStartsAnother() {
    orderRepository.save(new Order("ORD-1004"));

    TestTransaction.flagForRollback();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());

    TestTransaction.start();

    assertTrue(TestTransaction.isActive());

    orderRepository.save(new Order("ORD-1005"));
}
~~~

In this example, the first transaction is rolled back. Afterward, `start()` begins a new transaction so the test can continue interacting with the repository.

Do not call `start()` while the current test-managed transaction is still active. If you want to start a new transaction, end the current transaction first.

The test method must be configured to run with a test-managed transaction and must have an appropriate transaction manager. If the test lacks `@Transactional` or the transaction listener is not enabled, `TestTransaction.start()` cannot create a complete transactional test context on its own.

If the new transaction is still active when the method ends, Spring TestContext will end it according to its test transaction management mechanism. To express intent clearly and avoid relying on the default flag, explicitly flag commit or rollback before manually ending.



## 9. Complete example: commit and then open a new transaction to verify data

This is the classic scenario for `TestTransaction`. The test creates an order in the first transaction, commits, and then starts a second transaction to read back the committed data.

~~~java
@SpringBootTest
@Transactional
class OrderCommitIntegrationTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void commitsOrderAndReadsItInANewTransaction() {
        Order order = new Order("ORD-2001");

        Order saved = orderRepository.saveAndFlush(order);
        Long orderId = saved.getId();

        assertTrue(TestTransaction.isActive());

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());

        TestTransaction.start();

        try {
            Order reloaded = orderRepository.findById(orderId)
                .orElseThrow();

            assertEquals("ORD-2001", reloaded.getNumber());
        } finally {
            TestTransaction.flagForRollback();
            TestTransaction.end();
        }
    }
}
~~~

This example uses Spring Data JPA for illustration. Property names and constructors of `Order` must match the project's domain model.

Key points:

- `saveAndFlush` pushes changes to the database within the first transaction; it does not commit the transaction by itself.
- `flagForCommit` marks the first transaction to commit.
- `end` performs the commit and finishes that transaction.
- `start` starts a new transaction.
- `findById` re-reads the data from the new transaction, confirming the data was committed.
- The `finally` block flags rollback and ends the second transaction so unintended test state is not retained.

If an assertion in the second transaction fails, the `finally` block still attempts to end the active transaction with rollback. In real tests, ensure cleanup only calls `end()` when the new transaction was started and is still active.

Because the first transaction already committed, rolling back the second transaction cannot undo the saved order. This is why tests that commit need isolated data or explicit cleanup afterward.

## 10. Combining TestTransaction with @Commit and @Rollback

Spring TestContext provides annotations to set the default decision when the test transaction ends:

- `@Rollback` sets the rollback decision by default.
- `@Rollback(false)` sets the commit decision.
- `@Commit` is a clear way to express committing the test's transaction.

Example:

~~~java
@Test
@Transactional
@Commit
void commitsWhenTheTestFinishes() {
    orderRepository.save(new Order("ORD-3001"));
}
~~~

This test lets Spring end the transaction after the method and commit according to the annotation configuration.

You can use `TestTransaction` to change the decision at runtime:

~~~java
@Test
@Transactional
@Commit
void overridesCommitAndRollsBackExplicitly() {
    orderRepository.save(new Order("ORD-3002"));

    TestTransaction.flagForRollback();
    TestTransaction.end();
}
~~~

Here, the test flags rollback before ending the transaction. The decision is set directly for the current transaction.

Conversely, a test with default rollback can still request a commit:

~~~java
@Test
@Transactional
void commitsOnlyAfterExplicitRequest() {
    orderRepository.save(new Order("ORD-3003"));

    TestTransaction.flagForCommit();
    TestTransaction.end();
}
~~~

The point to remember is that annotations set the default policy for the test transaction; `TestTransaction`'s flag methods let the test adjust the current transaction's decision before calling `end()`.

## 11. Starting multiple transactions in the same test method

A test can end one transaction and start another multiple times, provided each transaction is ended before the next begins.

Example:

~~~java
@Test
@Transactional
void runsTwoSeparateTestManagedTransactions() {
    orderRepository.save(new Order("ORD-4001"));

    TestTransaction.flagForCommit();
    TestTransaction.end();

    TestTransaction.start();

    try {
        assertTrue(orderRepository.existsByNumber("ORD-4001"));

        orderRepository.save(new Order("ORD-4002"));

        TestTransaction.flagForRollback();
        TestTransaction.end();
    } finally {
        if (TestTransaction.isActive()) {
            TestTransaction.flagForRollback();
            TestTransaction.end();
        }
    }
}
~~~

This example illustrates two phases:

- The first transaction commits the first order.
- The second transaction reads the committed order and creates the second order.
- The second transaction rolls back so the second order is not retained.

In production tests, adapt repository methods to the real API. The cleanup pattern checking `isActive()` helps avoid leaving the second transaction open if an assertion or operation throws an exception before `end()` is called.

Do not create multiple transactions if the test only verifies a single simple behavior. Each real commit causes data to persist beyond the current transaction and increases cleanup requirements.

## 12. TestTransaction and @BeforeTransaction, @AfterTransaction

Spring TestContext has two helpful callbacks when you need to prepare or verify state outside the test-managed transaction:

- `@BeforeTransaction` runs before the test-managed transaction starts.
- `@AfterTransaction` runs after the test-managed transaction ends.

Example:

~~~java
@SpringBootTest
@Transactional
class TransactionBoundaryTest {

    @Autowired
    OrderRepository orderRepository;

    @BeforeTransaction
    void verifyDatabaseBeforeTransaction() {
        // Runs before the test-managed transaction.
    }

    @Test
    void createsAnOrder() {
        orderRepository.save(new Order("ORD-5001"));
    }

    @AfterTransaction
    void verifyDatabaseAfterTransaction() {
        // Runs after the test-managed transaction has ended.
    }
}
~~~

These callbacks are useful when wanting to inspect data before or after the test's automatic transaction. They are not callbacks invoked every time the test calls `TestTransaction.end()` or `start()` inside the method body. They belong to the transaction lifecycle managed by Spring TestContext around the test method.

If the test manually ends a transaction mid-method and starts a new one, run the corresponding assertions right at that point. Do not rely on `@AfterTransaction` to execute after each call to `end()`.

## 13. Conditions for TestTransaction to work

`TestTransaction` requires Spring TestContext transaction support. Several key conditions:

- The test must be integrated with Spring TestContext, for example with `@SpringBootTest` or `@SpringJUnitConfig`.
- `TransactionalTestExecutionListener` must be registered. This listener is normally included in Spring TestContext's default listener configuration.
- The test method or class must be configured with `@Transactional` to have a test-managed transaction.
- Spring must be able to locate a matching transaction manager, usually a bean implementing `PlatformTransactionManager`.
- Data operations must participate in the right transaction manager if commit/rollback is meant to affect them.

If the application has multiple transaction managers, clearly specify which transaction manager the test uses via appropriate `@Transactional` configuration, such as the `transactionManager` attribute or qualifier depending on the Spring version.

If the test does not run in a transaction, `isActive()` will not report an active test-managed transaction. Operations such as flag or end cannot control a nonexistent transaction.

## 14. TestTransaction only manages test-managed transactions

Do not confuse `TestTransaction` with transactions opened independently in application code.

Example of a service using `TransactionTemplate`:

~~~java
@Service
public class ImportService {

    private final TransactionTemplate transactionTemplate;

    public ImportService(TransactionTemplate transactionTemplate) {
        this.transactionTemplate = transactionTemplate;
    }

    public void importBatch() {
        transactionTemplate.executeWithoutResult(status -> {
            // Write data in a transaction managed by the template.
        });
    }
}
~~~

`TestTransaction.end()` ends the current test-managed transaction. If application code opens an independent transaction via propagation or a separate transaction manager, its outcome follows the application's transaction boundary.

In particular, a transaction with `REQUIRES_NEW` propagation can commit independently of the outer transaction. Rolling back the test transaction does not automatically revert an already-committed independent transaction.

If you need to test a service's transaction behavior, call the service through the Spring proxy so transaction advice is active. Calling the target directly or instantiating the object with `new` can bypass the proxy and prevent the test from verifying the real production transaction boundary.



## 15. Thread-bound transactions and HTTP requests

Test-managed transactions are normally bound to the thread running the test. Consequently, they do not automatically cover work executing on another thread.

An important example:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void postsOrder() {
        // Request is handled by the embedded server on a separate thread.
    }
}
~~~

The test method runs on JUnit's thread and may be inside a test-managed transaction. However, the HTTP request is handled on a server thread, with its own transaction managed by the service or repository. The test method's transaction does not automatically roll back writes performed during the request.

If the endpoint creates data, clean up the data via a repository or cleanup API after the request, use a separate database/schema/container, or apply an appropriate testing strategy.

Similarly, timeouts that run the test body on another thread can prevent code inside the callback from joining the test-managed transaction. Avoid assuming transactions automatically propagate across threads.

## 16. Real commits and data cleanup responsibility

When calling `flagForCommit()` and then `end()`, committed data persists according to the database's policy. Rolling back a new transaction does not delete previously committed data.

You can choose one of the following strategies:

- Use a dedicated test database and reset the schema or data after the suite.
- Create data with unique IDs or codes for precise cleanup.
- Delete committed records in a cleanup transaction.
- Use a separate database container per suite or test class if time and infrastructure allow.
- Use migrations/fixtures to establish a clear initial state.

A cleanup example can use a repository:

~~~java
try {
    // Perform test and commit data to verify.
} finally {
    orderRepository.deleteByNumber("ORD-2001");
}
~~~

If cleanup runs inside a new transaction, verify that transaction is committed appropriately. If cleanup only runs inside a test-managed transaction that rolls back by default, the delete operation can also be rolled back and the committed data will remain.

A cleaner organization is using a dedicated cleanup helper with an explicitly managed transaction, or resetting the database after the test class/suite.

Do not use fixed identifiers if tests can run in parallel against the same database. Generate unique codes or isolate data so one test does not delete another test's data.

## 17. Common mistakes

- **Calling flagForCommit but forgetting end:** the transaction is still active; the commit flag has not yet persisted the data immediately.
- **Calling end when no transaction is active:** there is no test-managed transaction to end; check configuration and state before calling.
- **Calling start while the old transaction is still active:** you must end the current transaction before starting a new one.
- **Thinking start creates a nested transaction:** start opens a new test-managed transaction after the previous one has ended.
- **Thinking rolling back the new transaction deletes previously committed data:** the prior commit was already confirmed by the database and cannot be rolled back retroactively.
- **Using TestTransaction in a test without @Transactional:** no test-managed transaction has been set up to control.
- **Confusing flush with commit:** flush sends changes to the database within the transaction; commit ends the transaction and confirms the changes.
- **Using TestTransaction to control every transaction in the application:** this API only manages test-managed transactions.
- **Overlooking which transaction manager is selected:** multiple transaction managers can cause the test to use the wrong boundary.
- **Assuming HTTP requests use the test method's transaction:** server requests normally run on another thread and have their own transaction.
- **Forgetting cleanup after commit:** data can affect subsequent tests or the next suite run.
- **Calling end multiple times in cleanup without checking active:** errors can occur if the transaction was already ended earlier.

## 18. Workflow for using TestTransaction in tests

When needing to end, start, or commit transactions mid-test method, follow this sequence:

1. Integrate the test with Spring TestContext and configure `@Transactional`.
2. Confirm the right transaction manager is present in the context.
3. Check `TestTransaction.isActive()` before controlling the transaction.
4. Create or update data in the current transaction.
5. Choose `flagForCommit()` or `flagForRollback()` depending on the goal.
6. Call `end()` to actually end the transaction.
7. Verify the transaction has ended using `isActive()`.
8. If needed, call `start()` to open a new test-managed transaction.
9. Run assertions in the new transaction and explicitly decide how to end it.
10. If data was committed, prepare durable, order-independent cleanup.
11. If operations run on another thread or through an HTTP server, identify their separate transaction boundaries.

## Conclusion

`TestTransaction` allows tests to control test-managed transactions while the method is running. `flagForCommit` and `flagForRollback` set the completion decision; `end` executes the commit or rollback; `start` opens a new test transaction; `isActive` and `isFlaggedForRollback` help observe the current state.

The common pattern is writing data in the first transaction, flagging commit, calling `end`, starting a new transaction with `start`, and reading back the committed data. End the new transaction explicitly and clean up committed data so tests remain independent. Remember that TestTransaction only controls transactions managed by Spring TestContext; independent transactions, HTTP requests on other threads, and non-database resources must be handled according to their own boundaries.

