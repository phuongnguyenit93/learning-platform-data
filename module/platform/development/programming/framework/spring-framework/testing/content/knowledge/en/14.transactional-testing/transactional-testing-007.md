# @BeforeEach and @AfterEach within the test transaction scope

In a Spring test with a transaction managed by the TestContext Framework, the order of preparing data, running the test, and cleaning up data determines which state is visible and which changes are rolled back. JUnit Jupiter's two lifecycle methods **@BeforeEach** and **@AfterEach** are commonly used to prepare fixtures and check state after each test. When a test is annotated with **@Transactional**, both of these methods run inside Spring's test-managed transaction.

That means data written in **@BeforeEach**, changes made in the test method, and operations in **@AfterEach** usually all belong to the same transaction. By default, Spring rolls back the transaction after the test method. Consequently, **@AfterEach** can see the changes just performed, while the database state after the transaction ends normally returns to the pre-test state.

Spring also provides two dedicated annotations: **@BeforeTransaction** and **@AfterTransaction**. They allow executing work before the transaction starts and after the transaction has committed or rolled back. Properly distinguishing these four lifecycle hooks helps avoid checking data at the wrong time, performing ineffective cleanup, or accidentally leaving committed data behind.

## 1. What is a test-managed transaction?

The Spring TestContext Framework can open a transaction wrapping each test method. This transaction is called a *test-managed transaction*. It is managed by **TransactionalTestExecutionListener** and is typically activated when the test class or test method has **@Transactional**.

Example:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void savesAnOrder() {
        repository.save(new OrderEntity("order-176", "customer-12"));

        assertTrue(repository.findById("order-176").isPresent());
    }
}
~~~

Spring starts the transaction for the test, runs the test method, and then completes the transaction according to the configured rollback or commit policy. By default, a test-managed transaction is rolled back after each test method.

This allows persistence tests to write data and verify results right within the same transaction without leaving long-lived changes in the database. However, rollback only applies to operations participating in that transaction. Messages sent to a broker, outbound HTTP requests, written files, or independently committed transactions will not be automatically reverted.

### Test-managed transactions differ from application transactions

Two types of transactions must be distinguished:

- **Test-managed transaction** is opened by Spring TestContext around the test method because the test is configured as transactional.
- **Spring-managed transaction** is opened by the application when a method with **@Transactional** is called through Spring's transaction mechanism.

A service with **REQUIRED** propagation normally joins the test's current transaction. If the service uses **REQUIRES_NEW**, Spring suspends the test's transaction and opens an independent transaction. That independent transaction can commit and persist even after the test's transaction rolls back.

Therefore, the statement "the test has @Transactional so all data is rolled back" is only true for changes participating in the test-managed transaction.

## 2. Execution order of @BeforeEach and @AfterEach

When a test is integrated with SpringExtension, Spring TestContext participates in the JUnit Jupiter lifecycle. With a standard test-managed transaction, the general sequence is:

~~~text
JUnit creates the test instance
        |
        v
Spring injects dependencies into the test instance
        |
        v
Spring TestContext: beforeTestMethod
        |
        +--> @BeforeTransaction
        |
        +--> Starts test-managed transaction
        |
        v
JUnit @BeforeEach
        |
        v
JUnit @BeforeTestExecution (if any)
        |
        v
JUnit @Test
        |
        v
JUnit @AfterTestExecution (if any)
        |
        v
JUnit @AfterEach
        |
        v
Spring TestContext: afterTestMethod
        |
        +--> Commits or rolls back test-managed transaction
        |
        +--> @AfterTransaction
        |
        v
Completes the test method
~~~

The diagram illustrates the typical order when SpringExtension and TransactionalTestExecutionListener manage the test. Other extensions may add their own callbacks, yet the key rule remains that the transaction is started by Spring before the **@BeforeEach** lifecycle method and ends after **@AfterEach**.

Therefore:

- **@BeforeEach** can create data belonging to the test's transaction.
- The test method sees the data prepared in **@BeforeEach**.
- **@AfterEach** can read or modify data within the same transaction.
- Only after **@AfterEach** completes does Spring execute rollback or commit.
- **@AfterTransaction** runs after the test-managed transaction has finished.

If the test does not have a test-managed transaction, **@BeforeEach** and **@AfterEach** still run under the normal JUnit lifecycle, without a transaction wrapping them merely because they are lifecycle methods.

## 3. Preparing data with @BeforeEach

**@BeforeEach** runs before each test method. It is the right place to create fixtures, set initial state, or reset collaborators for each test run.

Example:

~~~java
@SpringJUnitConfig(OrderPersistenceTestConfig.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void prepareData() {
        repository.save(
                new OrderEntity("order-176", "customer-12", "PENDING")
        );
    }

    @Test
    void findsPreparedOrder() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        assertEquals("customer-12", order.getCustomerId());
        assertEquals("PENDING", order.getStatus());
    }

    @Test
    void changesOrderStatus() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        order.setStatus("PAID");

        assertEquals(
                "PAID",
                repository.findById("order-176").orElseThrow().getStatus()
        );
    }
}
~~~

Each test method gets its own run of **@BeforeEach**. Data is saved within the test-managed transaction. When the test ends and the transaction rolls back, the record created in that run is also reverted.

Thus, if two tests use the same ID, they can still run independently when each run is wrapped in its own transaction and no operation commits data externally. If tests run in parallel or involve independent transactions, use distinct IDs to avoid conflicts.

### Avoid broad database deletion

Some tests use **@BeforeEach** to call **deleteAll()** before creating data. This approach can work with a test-dedicated database, but its transactional effect must be understood:

- If deleteAll runs inside the test-managed transaction, the delete operation is also rolled back at the end of the test.
- Data that existed prior to the test can reappear after rollback.
- If deleteAll runs in an independent transaction or gets committed, data can be permanently deleted.

Avoid using broad delete operations on a shared database. Creating fixtures with unique IDs or cleaning up only the data scope owned by the test is safer and clearer.

## 4. Inspecting state before rollback with @AfterEach

**@AfterEach** runs after the test method but before Spring finishes the test-managed transaction. Therefore, it still sees data created or modified during the test.

Example:

~~~java
@SpringJUnitConfig(OrderPersistenceTestConfig.class)
@Transactional
class OrderLifecycleTest {

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void prepare() {
        repository.save(
                new OrderEntity("order-176", "customer-12", "PENDING")
        );
    }

    @Test
    void updatesOrder() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        order.setStatus("PAID");
    }

    @AfterEach
    void verifiesStateBeforeRollback() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        assertEquals("PAID", order.getStatus());
    }
}
~~~

In this example, **@AfterEach** reads the PAID status because the transaction has not rolled back yet. This is the right moment to verify the test's final changes before the transaction completes.

If the goal is to verify that data was committed and persists after the transaction finishes, **@AfterEach** is not the right moment. Use **@AfterTransaction** or another test that reads data after the transaction has completed.

### Cleanup in @AfterEach can be rolled back

Suppose **@AfterEach** calls:

~~~java
@AfterEach
void cleanUp() {
    repository.deleteById("order-176");
}
~~~

If the delete operation participates in the same test-managed transaction and the transaction will roll back, the delete operation is also rolled back. The record created in **@BeforeEach** is still removed by the transaction's rollback, yet the cleanup operation is not separately committed.

This is expected behavior in many persistence tests. No extra database cleanup is needed if all data created and modified within the transaction will roll back.

If the test is configured to commit, cleanup in **@AfterEach** may be committed along with the transaction. Clearly determine the test's goal before deciding to clean up data here.

## 5. How do @BeforeTransaction and @AfterTransaction differ?

Spring TestContext provides two annotations for running code outside the test-managed transaction:

- **@BeforeTransaction** runs before the test's transaction starts.
- **@AfterTransaction** runs after the test's transaction has committed or rolled back.

These two annotations belong to the Spring TestContext Framework, not JUnit Jupiter's lifecycle annotations. They are handled by **TransactionalTestExecutionListener**.

Example:

~~~java
@SpringJUnitConfig(OrderPersistenceTestConfig.class)
@Transactional
class OrderTransactionBoundaryTest {

    @Autowired
    private OrderRepository repository;

    @BeforeTransaction
    void verifyStateBeforeTestTransaction() {
        assertFalse(repository.existsById("order-176"));
    }

    @BeforeEach
    void prepareData() {
        repository.save(
                new OrderEntity("order-176", "customer-12", "PENDING")
        );
    }

    @Test
    void seesPreparedOrderInsideTransaction() {
        assertTrue(repository.existsById("order-176"));
    }

    @AfterEach
    void verifyBeforeRollback() {
        assertTrue(repository.existsById("order-176"));
    }

    @AfterTransaction
    void verifyStateAfterRollback() {
        assertFalse(repository.existsById("order-176"));
    }
}
~~~

This example assumes the test database starts without a record with ID order-176 and the test uses an appropriate transaction manager. The observed sequence is:

1. **@BeforeTransaction** checks state before the test-managed transaction.
2. Spring starts the transaction.
3. **@BeforeEach** creates the record.
4. The test method sees the record.
5. **@AfterEach** still sees the record because the transaction has not ended yet.
6. Spring rolls back the transaction by default.
7. **@AfterTransaction** checks that the record is no longer in the database.

If the test uses **@Commit** or **@Rollback(false)**, the post-transaction outcome will differ: data is committed and **@AfterTransaction** can see the record.

### When are these two hooks needed?

Use **@BeforeTransaction** when you need to:

- Verify the committed baseline before the test starts.
- Prepare data that must exist outside the test's transaction.
- Verify data committed from an earlier test or another process.
- Establish state that the test's transaction must read as already-committed data.

Use **@AfterTransaction** when you need to:

- Verify that rollback removed the changes.
- Verify that commit persisted the data.
- Clean up data committed or created outside the transaction.
- Inspect state after the transaction has ended.

These two hooks are only meaningful when a test-managed transaction is actually created. If the test has no transaction, they do not replace **@BeforeEach** and **@AfterEach**.

## 6. Comparing the four lifecycle hooks

| Hook | Timing | Inside the test-managed transaction? | Typical purpose |
|---|---|---|---|
| @BeforeTransaction | Before the transaction starts | No | Check baseline or prepare data outside the transaction |
| @BeforeEach | Before each test method | Yes, if the test has a transaction | Create fixtures for each test |
| @AfterEach | After each test method, before the transaction ends | Yes, if the test has a transaction | Verify state before rollback/commit |
| @AfterTransaction | After the transaction ends | No | Verify commit/rollback outcome or clean up after the transaction |

Another difference is that JUnit Jupiter's **@BeforeAll** and **@AfterAll** run once per test class. They are not part of each individual test method's transaction managed by Spring TestContext. Do not use them to create data that each test method expects to see inside its own transaction, unless you actively manage transactions and shared state.

## 7. Using @Transactional on the class or test method?

You can place **@Transactional** on the test class so all test methods in the class run inside a test-managed transaction:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@Transactional
class AllOrderTests {
}
~~~

Or place it on a specific test method:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class MixedTransactionTests {

    @Test
    @Transactional
    void runsInsideTestTransaction() {
        // Test body
    }

    @Test
    void runsWithoutTestManagedTransaction() {
        // Test body
    }
}
~~~

When a transaction is only needed for some tests, method-level annotations keep the scope clear. When the entire class tests persistence and needs default rollback, a class-level annotation can be cleaner.

Place **@Transactional** on the test class or test method to configure the test-managed transaction. Annotating only an **@BeforeEach** or **@AfterEach** method with **@Transactional** is not a reliable way to ask Spring to create an independent transaction for the lifecycle method. If a separate transaction is needed inside a hook, use **TransactionTemplate** or call a service with a clearly configured transaction boundary.

### Selecting a transaction manager when multiple managers exist

An ApplicationContext can contain multiple **PlatformTransactionManager** beans, such as one manager for the orders database and one manager for the reporting database. If a test uses the wrong manager, the tested data may not belong to the transaction being rolled back.

You can specify the manager using a qualifier in **@Transactional**:

~~~java
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
}
~~~

Or use the **transactionManager** attribute. Make sure the repository and service under test participate in the exact transaction manager used by the test-managed transaction.

## 8. Default rollback and when to commit

Spring TestContext rolls back test-managed transactions by default after each test method. This is a safe policy for persistence tests because tests leave no data behind.

Behavior can be controlled with **@Rollback**:

~~~java
@Test
@Rollback
void rollsBackByDefault() {
    // Changes are rolled back after the test
}
~~~

To request a commit:

~~~java
@Test
@Commit
void commitsChangesAfterTheTest() {
    // Changes are committed after the test
}
~~~

**@Commit** is equivalent to configuring rollback false. You can use **@Rollback(false)** if you prefer expressing the attribute value explicitly.

Only commit when the test needs to verify behavior that depends on committed data, or needs to create durable data for a specially designed integration step. Tests that commit must have a data cleanup strategy, otherwise subsequent runs may hit duplicate keys or mistakenly read stale data.

Do not switch an entire test class to commit just for one test verifying saved data. Set the commit policy on the specific method or use **TestTransaction** to end the transaction intentionally.

### Controlling transactions with TestTransaction

Spring TestContext provides **TestTransaction** to inspect and control the test-managed transaction while the test is running.

Example:

~~~java
@Test
@Transactional
void commitsWhenExplicitlyRequested() {
    repository.save(new OrderEntity("order-commit-1", "customer-1", "PAID"));

    assertTrue(TestTransaction.isActive());

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

**flagForCommit()** marks the current transaction to commit when ended via **end()**. Without flagging for commit, the transaction usually rolls back by default. After ending, a new transaction can be started with **TestTransaction.start()** if the test needs to perform further operations in another transaction.

Do not call **TestTransaction.end()** merely to bypass normal cleanup. It alters the test's transaction lifecycle and can cause subsequent operations to run outside a transaction unless restarted.

## 9. @BeforeEach prepares data in the same transaction as the test

One benefit of using **@BeforeEach** in a transactional test is that prepared data and the behavior under test participate in the same transaction.

Example of a service updating order status:

~~~java
@SpringJUnitConfig(OrderServiceTestConfig.class)
@Transactional
class OrderServiceTransactionTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void createPendingOrder() {
        repository.save(
                new Order("order-176", OrderStatus.PENDING)
        );
    }

    @Test
    void marksOrderAsPaid() {
        orderService.markPaid("order-176");

        assertEquals(
                OrderStatus.PAID,
                repository.findById("order-176").orElseThrow().status()
        );
    }
}
~~~

If **markPaid** uses **REQUIRED** propagation, the service call typically joins the test's open transaction. When the test ends, both the status change and the fixture record roll back.

This approach is well suited for testing persistence logic within the same transaction. However, it does not prove the data has been committed and can be read from another transaction. If the goal is to verify post-commit visibility, end the transaction or use another test observing after the transaction.

## 10. Notes on REQUIRES_NEW propagation

A service method with **Propagation.REQUIRES_NEW** asks Spring to open an independent transaction. The current test transaction is suspended while the new transaction runs.

Example:

~~~java
@Service
class AuditService {

    private final AuditRepository repository;

    AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        repository.save(new AuditEntry(event));
    }
}
~~~

If the test calls **auditService.record(...)**, the audit record may be committed in its own transaction. Afterward, the test's transaction rolls back, yet the audit record remains.

This also affects setup data. If **@BeforeEach** creates a record inside the test transaction while the invoked service uses **REQUIRES_NEW**, the independent transaction may not see that uncommitted record. Databases normally do not allow another transaction to read uncommitted data from the test transaction.

When you need to prepare data for an independent transaction:

- Create committed baseline data before the test transaction starts, potentially using **@BeforeTransaction**.
- Use a separate setup transaction and complete it before calling the service.
- Design the test to verify the service's true commit boundary.
- Clean up data committed by the independent transaction after the test.

Do not assume the test's rollback will retract every change created by services. Check the propagation and transaction manager of each collaborator.

## 11. @BeforeEach and @AfterEach when the test does not use a transaction

If the test class does not have **@Transactional**, the two lifecycle methods still operate, but without a wrapping test-managed transaction.

Example:

~~~java
@SpringJUnitConfig(OrderServiceTestConfig.class)
class NonTransactionalOrderTest {

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void prepare() {
        repository.save(new Order("order-176", OrderStatus.PENDING));
    }

    @Test
    void readsOrder() {
        assertTrue(repository.findById("order-176").isPresent());
    }

    @AfterEach
    void cleanUp() {
        repository.deleteById("order-176");
    }
}
~~~

In this example, each repository method may run its own transaction according to the repository or service configuration. The save statement may already be committed before the test method starts. Therefore, if the test fails before cleanup or cleanup fails to run, data can be left behind.

For non-transactional tests, an explicit cleanup strategy is necessary:

- Use a unique ID per test.
- Clean up the exact records created by the test.
- Use a separate schema or database when multiple tests run in parallel.
- Use containers or fixture lifecycles to reset resources.
- Place cleanup in an appropriate teardown hook and ensure failure cases are handled too.

Do not assume that merely having **@BeforeEach** and **@AfterEach** causes data to roll back automatically. Rollback is behavior of the transaction manager, not of the JUnit lifecycle.

## 12. @AfterEach is not always the place to verify the final result

Two types of assertions are often confused:

- Assertions on state inside the transaction, before rollback or commit.
- Assertions on state already committed or rolled back in the database after the transaction.

**@AfterEach** suits the first type. **@AfterTransaction** suits the second type.

For example, if the test uses default rollback:

~~~java
@AfterEach
void seesUncommittedChange() {
    assertTrue(repository.existsById("order-176"));
}
~~~

This assertion can pass because the record still exists within the current transaction.

After rollback:

~~~java
@AfterTransaction
void doesNotSeeRolledBackChange() {
    assertFalse(repository.existsById("order-176"));
}
~~~

The second assertion verifies state after the transaction has ended.

If using **@Commit**, the post-transaction result may be that the record still exists. Write expectations matching the test's transaction policy. Do not use the exact same assertion for both rollback and commit.

## 13. Impact of @Sql and prepared data

Spring TestContext supports **@Sql** to execute SQL scripts before or after a test method. It is frequently used alongside test transactions to prepare fixtures.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
@Sql(
    scripts = "/sql/order-before-test.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderSqlTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void readsSqlFixture() {
        assertTrue(repository.existsById("order-176"));
    }
}
~~~

With default configuration, the SQL script can join the current transaction when an appropriate transaction exists. In that case, data created by the script also rolls back with the test.

If **@Sql** uses its own transaction mode or the test has no transaction, commit and cleanup behavior can differ. Check **SqlConfig.TransactionMode** configuration and the transaction manager selected for the script.

You can use **@Sql** in the **AFTER_TEST_METHOD** phase to run cleanup scripts. However, if the script runs inside a transaction about to roll back, the cleanup operations may roll back as well. Determine whether data was committed before deciding to use a post-test script.

Do not combine **@BeforeEach**, **@Sql**, and **@AfterEach** to prepare the same fixture without a clear reason. Choosing one primary setup source makes ordering and responsibility easier to understand.

## 14. Thread boundaries can invalidate rollback

Spring's test-managed transaction is bound to the current thread. Transaction context is normally stored in a ThreadLocal via transaction synchronization.

If the tested code runs on another thread, the test's transaction does not automatically propagate to that thread.

Common cases:

- **@Async** running a method on an executor.
- HTTP requests handled by a server thread when using a real server.
- Tasks submitted to an executor or scheduler.
- Tests using a timeout that executes the assertion on a separate thread.
- A message consumer processing data on another thread.

An important example is JUnit Jupiter's **assertTimeoutPreemptively**. This mechanism can run the test snippet in a separate thread so it can interrupt on timeout. If that snippet writes to the database on that thread, it does not join the test-managed transaction bound to the original thread. Changes can commit and fail to roll back as expected.

For transactional tests with database operations, be careful when using preemptive timeouts. Use non-preemptive timeouts or design explicit cleanup for tasks running on separate threads.

If you need to test async behavior, wait for the task to complete, identify the processing thread's transaction boundary, and clean up data after the task finishes. Do not rely on **@Transactional** on the test method to roll back every thread in the application.

## 15. Parallel tests and shared state

JUnit Jupiter can run tests in parallel when configured. Each test-managed transaction is bound to its corresponding thread and transaction manager, yet the database, schema, tables, and singleton beans may still be shared.

If two tests use the same ID, delete the whole table, or modify shared data, they can collide even though each test has its own transaction.

Ways to reduce contention:

- Use unique IDs per test or per test run.
- Avoid **deleteAll()** on tables used by other tests.
- Use separate databases/schemas/containers for test groups needing strong isolation.
- Do not maintain shared mutable fixtures across tests.
- Only enable parallel execution when data and infrastructure have been designed for it.

Rollback reverts changes of individual transactions, yet does not by itself solve all concurrency issues. For instance, two transactions can contend on a unique key or lock rows before one transaction rolls back.

## 16. Choosing hooks by goal

| Goal | Appropriate hook | Reason |
|---|---|---|
| Create fixtures for each test | @BeforeEach | Runs inside the test transaction if one exists |
| Check results right after the test method | @AfterEach | The transaction has not ended yet |
| Check baseline before the transaction | @BeforeTransaction | Runs outside the transaction |
| Check data after rollback/commit | @AfterTransaction | The transaction has ended |
| Create data that must commit before the test transaction | @BeforeTransaction | Data can be committed independently |
| Clean up committed data outside the test transaction | @AfterTransaction | Cleanup occurs after the transaction |
| Prepare once for the whole class | @BeforeAll | Not part of each test method's transaction |
| Clean up resources once after the whole class | @AfterAll | Not part of each test method's transaction |

Start by asking: must the assertion or operation happen before or after the transaction ends? If you need to see uncommitted changes, use **@AfterEach**. If you need to confirm committed or rolled-back state, use **@AfterTransaction**.

## 17. Common mistakes

### Thinking @AfterEach runs after rollback

With Spring TestContext and standard test-managed transactions, **@AfterEach** runs before the transaction is completed. If you need to verify the outcome after rollback, use **@AfterTransaction**.

### Creating fixtures in @BeforeAll

**@BeforeAll** runs once for the class, whereas test transactions are typically created separately per test method. Data created outside a transaction can be committed and shared across tests. If fixtures must be isolated per test, use **@BeforeEach**.

### Deleting data in @AfterEach and expecting permanent deletion

If cleanup participates in the test transaction and the transaction rolls back, the delete operation rolls back too. Use **@AfterTransaction** or a separate cleanup transaction when committed data must be deleted.

### Assuming @Transactional on a lifecycle method opens its own transaction

The transaction listener manages test transactions based on test class or test method configuration. Annotating **@BeforeEach** or **@AfterEach** with **@Transactional** is not a reliable way to create an independent transaction for the hook.

### Forgetting REQUIRES_NEW propagation

Changes committed in an independent transaction are not rolled back with the test transaction. Check service propagation and transaction managers.

### Writing data on another thread

The test's transaction is bound to the current thread. Async tasks, HTTP server threads, or preemptive timeouts can write data outside that transaction.

### Sharing IDs when tests run in parallel

Two tests can concurrently create or delete the same record. Use unique IDs and scoped cleanup.

### Assuming @DirtiesContext replaces rollback

**@DirtiesContext** manages the ApplicationContext cache. It does not automatically revert committed transactions or external side effects.

### Failing to identify the right transaction manager

When the context has multiple managers, the test may roll back a different manager from the one the repository uses. Specify the appropriate qualifier.

## 18. Comprehensive example: verifying before and after the transaction

The following example shows both timing points: **@AfterEach** verifies state inside the transaction and **@AfterTransaction** verifies state after rollback.

~~~java
@SpringJUnitConfig(OrderTransactionTestConfig.class)
@Transactional
class OrderTransactionLifecycleTest {

    private static final String ORDER_ID = "order-lifecycle-176";

    @Autowired
    private OrderRepository repository;

    @Autowired
    private OrderService orderService;

    @BeforeTransaction
    void verifyInitialState() {
        assertFalse(repository.existsById(ORDER_ID));
    }

    @BeforeEach
    void createPendingOrder() {
        repository.save(
                new Order(ORDER_ID, OrderStatus.PENDING)
        );
    }

    @Test
    void confirmsOrderInsideTestTransaction() {
        orderService.confirm(ORDER_ID);

        Order order = repository.findById(ORDER_ID).orElseThrow();

        assertEquals(OrderStatus.CONFIRMED, order.status());
    }

    @AfterEach
    void verifiesStateBeforeTransactionEnds() {
        Order order = repository.findById(ORDER_ID).orElseThrow();

        assertEquals(OrderStatus.CONFIRMED, order.status());
    }

    @AfterTransaction
    void verifiesRollback() {
        assertFalse(repository.existsById(ORDER_ID));
    }
}
~~~

This example assumes the service uses transaction propagation that joins the current transaction, the repository and service use the same transaction manager, and the ID does not exist prior to the test. When the test completes, changes are rolled back; **@AfterTransaction** reads database state after the rollback.

If you switch the class or method to **@Commit**, the final assertion must change to expect the record to exist. If the service uses **REQUIRES_NEW**, redesign the fixtures and assertions because the service may commit outside the test's transaction.

## 19. Workflow for designing the lifecycle of a transactional test

When writing a persistence test, determine:

1. Does the test actually need a test-managed transaction?
2. Is the transaction enabled at the class or method level?
3. Does **@BeforeEach** need to create data inside the transaction, or is pre-committed data required?
4. Which propagation do the test method and service use?
5. Does **@AfterEach** need to verify uncommitted state or clean up changes within the transaction?
6. Are **@BeforeTransaction** or **@AfterTransaction** needed to check outside the transaction?
7. Which transaction manager is being used?
8. Are there independent transactions, other threads, or non-database side effects?
9. Does the test roll back by default or is it marked for commit?
10. Could data collide when tests run in parallel?

A practical rule of thumb is to let **@BeforeEach** prepare data for each test, let the test method execute the behavior under test, and use **@AfterEach** for assertions that need to see state inside the current transaction. When needing to verify results after commit or rollback, move that assertion to **@AfterTransaction**.

## 20. Key principles to remember

- **@BeforeEach** runs before each test method; if the test has a test-managed transaction, it runs inside that transaction.
- **@AfterEach** runs after the test method but before Spring completes the test-managed transaction.
- Spring rolls back test-managed transactions by default after each test method.
- **@BeforeTransaction** runs before the transaction begins.
- **@AfterTransaction** runs after the transaction commits or rolls back.
- **@BeforeAll** and **@AfterAll** do not belong to each test method's individual transaction.
- Cleanup in **@AfterEach** can be rolled back along with the transaction.
- **REQUIRES_NEW**, async threads, and requests handled on server threads can produce changes that survive the test's rollback.
- Use **@Commit**, **@Rollback**, and **TestTransaction** intentionally.
- Isolate data with unique IDs and properly scoped cleanup.

Once you clearly understand when transactions start and end, choosing lifecycle hooks becomes predictable. **@BeforeEach** and **@AfterEach** fit data and assertions inside the transaction; **@BeforeTransaction** and **@AfterTransaction** are meant for work needing to observe state outside the transaction. Separating these timing points lets tests verify both in-transaction state and final outcomes after commit or rollback.

