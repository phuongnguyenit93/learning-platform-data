# Test-managed transactions vs. application-managed transactions

In Spring testing, a transaction can be started either by the test infrastructure or by application logic. Both cases can use the same PlatformTransactionManager and the same database, but the party responsible for starting, ending, and deciding commit/rollback differs.

A **Test-managed transaction** is a transaction whose lifecycle is controlled by the Spring TestContext Framework for a test method. An **Application-managed transaction** is a transaction started by application code, typically through @Transactional on a service or TransactionTemplate. Understanding this boundary helps explain why a test rolls back data by default, why a service can join the test's transaction, and why a REQUIRES_NEW operation or a request running on another thread can still commit data.

## 1. Where do the two transaction types differ?

| Aspect | Test-managed transaction | Application-managed transaction |
|---|---|---|
| Who starts it? | Spring TestContext Framework, through TransactionalTestExecutionListener. | Application logic, such as a service invoked through an @Transactional proxy or code using TransactionTemplate. |
| Goal | Isolate data and state within a single test run. | Ensure an application unit of work has an appropriate transaction boundary. |
| When it ends | Spring Test ends the transaction after the test method and rolls back by default. | The transaction interceptor or transaction management code commits/rolls back based on the application's processing result. |
| Commit/rollback decision | Typically controlled via @Rollback, @Commit, or TestTransaction. | Based on the processing outcome, exceptions, and the application's transaction rules. |
| Typical scope | A test method running on the test thread. | A service method or a unit of work defined by the application. |

These two types are not two separate transaction managers. Spring Test typically requests a PlatformTransactionManager from the context and uses that manager to start the test transaction. When a service is invoked on the same thread and with the same transaction manager, the transaction requested by the application can join the existing transaction.

## 2. How is a test-managed transaction created?

The Spring TestContext Framework provides TransactionalTestExecutionListener to support transactions for tests. This listener is registered by default when using the standard Spring TestContext mechanism.

When a test class or test method is annotated with @Transactional, the listener starts a transaction before executing the test method. After the test finishes, the listener rolls back the transaction by default so data does not leak into other tests.

```text
JUnit Jupiter runs the test
        |
        v
Spring TestContext prepares the test
        |
        v
TransactionalTestExecutionListener
        | starts test-managed transaction
        v
@BeforeEach
        |
        v
Test method
        |
        v
@AfterEach
        |
        v
Spring Test ends the transaction
        |
        +-- rolls back by default (or commits as configured)
```

Example:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAnAccount() {
        Account account = new Account("ACC-100");

        accountRepository.save(account);

        assertThat(accountRepository.findByCode("ACC-100")).isPresent();
    }
}
```

In this example, the test can read back the newly written data within the same transaction. After the test, Spring Test rolls back the transaction by default. Therefore, data written in the test transaction usually does not exist after the test method completes.

### 2.1. A transaction manager is required

For a test-managed transaction to work, the Spring context must provide an appropriate transaction manager. With JDBC, this can be DataSourceTransactionManager; with JPA, it is typically JpaTransactionManager.

```java
@Configuration
class PersistenceTestConfiguration {

    @Bean
    DataSource dataSource() {
        // Create a DataSource dedicated to testing.
        return createTestDataSource();
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

This is an illustrative JDBC configuration example; the createTestDataSource() method represents how the project provides a real datasource for tests. If the context has multiple transaction managers, specify the appropriate manager on the test using the transactionManager attribute of @Transactional:

```java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
}
```

You can use the corresponding bean name or qualifier according to your configuration. If Spring cannot find a unique transaction manager or selects the wrong manager, the test may not run within the transaction you expect.

## 3. Default rollback and how to request a commit

Test-managed transactions are rolled back by default. This mechanism allows a test to prepare data, perform write operations, and run assertions within a single transaction without having to manually clean up every row after each run.

### 3.1. @Rollback

@Rollback controls whether the test's transaction is rolled back after completion:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
@Rollback
class AccountRepositoryTest {

    @Test
    void rollsBackAfterTest() {
        // Data written in the test transaction will roll back after the test.
    }
}
```

Passing no value or setting @Rollback(true) means rollback. You can set @Rollback(false) to commit the test transaction:

```java
@Test
@Rollback(false)
void commitsTestTransaction() {
    // Data is committed when the test finishes.
}
```

### 3.2. @Commit

@Commit is a clear way to express that a test-managed transaction should commit:

```java
@Test
@Commit
void persistsFixtureForLaterVerification() {
    // The test transaction is committed after the test completes.
}
```

@Commit is equivalent in intent to @Rollback(false). These annotations can be placed at the class or method level as needed. An annotation on a method can override the default configuration applied from the class.

Use commit in tests when you need to confirm that data persists across a transaction boundary or when there is an independent verification step running afterward. Because committed data remains in the database, the test must have a data cleanup strategy so it does not affect subsequent runs.

## 4. Application-managed transactions started by application code

In an application, transactions are typically declared on service methods:

```java
@Service
public class TransferService {

    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        Account source = accountRepository.getReferenceById(fromId);
        Account target = accountRepository.getReferenceById(toId);

        source.withdraw(amount);
        target.deposit(amount);
    }
}
```

When the application calls transfer() through a Spring proxy, the transaction interceptor starts a transaction if no suitable transaction exists yet, invokes the method, and decides to commit or roll back based on the execution outcome. This is an application-managed transaction because the business boundary is defined by the annotation on the service.

Code can also manage transactions explicitly using TransactionTemplate:

```java
public class TransferService {

    private final TransactionTemplate transactionTemplate;
    private final AccountRepository accountRepository;

    public TransferService(
            TransactionTemplate transactionTemplate,
            AccountRepository accountRepository) {
        this.transactionTemplate = transactionTemplate;
        this.accountRepository = accountRepository;
    }

    public void transfer(long fromId, long toId, BigDecimal amount) {
        transactionTemplate.executeWithoutResult(status -> {
            Account source = accountRepository.getReferenceById(fromId);
            Account target = accountRepository.getReferenceById(toId);
            source.withdraw(amount);
            target.deposit(amount);
        });
    }
}
```

TransactionTemplate uses the configured transaction manager and ends the transaction based on the callback's outcome. This approach is suitable when an explicit transaction boundary is needed in code without relying on proxy annotations.

## 5. Application transactions joining a test-managed transaction

A test can open a test-managed transaction and then call a service annotated with @Transactional. The outcome depends on the service's propagation.

With the default REQUIRED propagation, the service joins the existing transaction on the same thread and the same transaction manager. The service does not create an independent transaction; when the test finishes and rolls back, changes made by the service are also rolled back.

```text
Test method
    |
    +-- Spring Test starts transaction T1
    |
    +-- calls OrderService.create()
             |
             +-- @Transactional(REQUIRED)
                       |
                       +-- joins transaction T1

Test finishes
    |
    +-- Spring Test rolls back T1
             +-- changes from the service also roll back
```

Example:

```java
@SpringJUnitConfig(classes = OrderApplicationTestConfiguration.class)
@Transactional
class OrderServiceTransactionTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void serviceWriteIsRolledBackWithTheTest() {
        Order order = orderService.create(new CreateOrderCommand("SKU-1", 2));

        assertThat(orderRepository.findById(order.getId())).isPresent();
    }
}
```

The assertion can read the order because it is running within the same transaction and sees the uncommitted changes of that very transaction. After the test ends, the test's rollback reverts the changes.

This is useful for integration tests because you can test multiple beans participating in a business flow while keeping the database clean after the test.

## 6. Propagation determines the boundary between the two transactions

Propagation describes how a business call behaves when the current thread already has a transaction. When a service is called inside a test-managed transaction, the service's propagation determines whether it joins, suspends, or requires a different transaction.

| Propagation | When a test-managed transaction exists | Effect on test rollback |
|---|---|---|
| REQUIRED | Joins the current transaction. | Changes belong to the test transaction and are rolled back with the test. |
| REQUIRES_NEW | Suspends the test transaction and starts an independent transaction. | The new transaction can commit independently; the test rollback does not revert what was committed. |
| NESTED | Uses a nested transaction/savepoint if the transaction manager and resource support it. | Changes remain inside the outer transaction; the test rollback still reverts the outer transaction. |
| SUPPORTS | Joins the transaction if one exists; otherwise runs without a transaction. | Inside a test-managed transaction, typically joins the test transaction. |
| MANDATORY | Requires an existing transaction to be present. | Succeeds when called inside a test-managed transaction; fails if there is no transaction. |
| NOT_SUPPORTED | Suspends the current transaction and runs non-transactionally. | Operations are outside the test rollback; how writes behave depends on the resource and its own management mechanism. |
| NEVER | Requires that no current transaction exists. | Throws an error if called while a test-managed transaction is active. |

### 6.1. REQUIRES_NEW can commit outside the test transaction

Suppose a service records audits using REQUIRES_NEW propagation:

```java
@Service
class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        // Record audit in an independent transaction.
    }
}
```

When the test is in transaction T1, the audit call suspends T1 and opens T2. If T2 commits successfully, Spring restores T1 afterward. At the end of the test, rolling back T1 cannot undo the already-committed T2.

This is why a test annotated with @Transactional can still leave data behind after running. When encountering this case, you need to clean up the committed audit data or design the test to verify it using a separate fixture.

### 6.2. NOT_SUPPORTED runs outside the test transaction

A NOT_SUPPORTED method suspends the active transaction during its execution. If the method performs write operations using an auto-commit mechanism or an independent transaction, those changes are not part of the test transaction and are not rolled back with the test.

Do not use NOT_SUPPORTED merely to avoid rollback issues without understanding which transaction mechanism the code inside is using. Clearly determine whether the operation under test is meant to commit independently.

### 6.3. NESTED depends on savepoint support

NESTED is typically implemented using a savepoint within the current transaction. It is not the same as REQUIRES_NEW: a nested transaction does not necessarily create an independent physical transaction. Support depends on the transaction manager, driver, and resource configuration. Without savepoint support, the call may fail or lack the semantics the test expects.

## 7. Tests without a test-managed transaction still test application transactions

Not every test needs @Transactional at the test level. If the goal is to verify that a service opens and commits its own transaction according to application behavior, call the service in a test without a surrounding transaction:

```java
@SpringJUnitConfig(classes = OrderApplicationTestConfiguration.class)
class OrderServiceCommitTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void serviceTransactionCommitsAfterMethodReturns() {
        Order order = orderService.create(new CreateOrderCommand("SKU-1", 2));

        // Query after the service transaction has ended.
        assertThat(orderRepository.findById(order.getId())).isPresent();
    }
}
```

In this example, if OrderService.create() is invoked through a Spring proxy and has @Transactional, the service starts and commits the transaction according to application rules. The assertion after the call verifies that the data has been committed.

This test needs to clean up data after running, such as deleting the order by id in @AfterEach or using a dedicated database for tests. If you want to verify rollback when the service throws an exception, create a separate test confirming that the data is not persisted according to the service's rollback rules.

## 8. Controlling test-managed transactions with TestTransaction

The @Commit and @Rollback annotations are sufficient for many cases. When you need to end a transaction mid-method, start a new transaction, or decide to commit based on runtime logic, Spring Test provides TestTransaction.

Main operations:

| API | Meaning |
|---|---|
| TestTransaction.isActive() | Checks whether a test-managed transaction is currently active. |
| TestTransaction.flagForCommit() | Marks the current transaction to commit when it ends. |
| TestTransaction.flagForRollback() | Marks the current transaction to roll back when it ends. |
| TestTransaction.end() | Ends the current transaction according to the flagged commit/rollback decision. |
| TestTransaction.start() | Starts a new test-managed transaction. |

Example of committing one phase and then continuing assertions in a new transaction:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountTransactionTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void commitsFirstPhaseAndRunsSecondPhaseInNewTransaction() {
        accountRepository.save(new Account("ACC-200"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(accountRepository.findByCode("ACC-200")).isPresent();

        TestTransaction.start();
        accountRepository.save(new Account("ACC-201"));
        // The new transaction will roll back by default when the test finishes.
    }
}
```

After end(), the first test transaction has finished. The post-commit query assertion confirms the data exists. start() opens a new test transaction; unless flagged for commit, the new transaction will roll back when the test completes.

Do not call TestTransaction in a test that does not have a test-managed transaction. This API controls transactions managed by Spring Test, not a general-purpose tool to commit arbitrary application transactions.

## 9. Callbacks running inside and outside a test-managed transaction

When a callback runs affects whether fixture data belongs to the test transaction.

| Callback | Relationship to the test-managed transaction |
|---|---|
| @BeforeTransaction | Runs before the test transaction starts. |
| @BeforeEach | Runs inside the test transaction if the test is configured as transactional. |
| Test method | Runs inside the test transaction if the test is configured as transactional. |
| @AfterEach | Runs before the test transaction ends, and therefore still inside the test transaction. |
| @AfterTransaction | Runs after the test transaction has ended. |
| @BeforeAll / @AfterAll | Runs outside each test method's transaction. |

Example:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountLifecycleTest {

    @BeforeTransaction
    void verifyDatabaseBeforeTransaction() {
        // Verify committed state before the test transaction starts.
    }

    @BeforeEach
    void prepareInsideTransaction() {
        // Fixtures created here belong to the test transaction.
    }

    @AfterEach
    void inspectBeforeRollback() {
        // Can still read uncommitted changes in the test transaction.
    }

    @AfterTransaction
    void verifyAfterTransaction() {
        // Runs after commit/rollback of the test transaction.
    }
}
```

The @BeforeTransaction and @AfterTransaction callbacks are Spring TestContext callbacks, not JUnit lifecycle annotations. They require SpringExtension/TestContext to be configured and are only invoked when an appropriate test-managed transaction is present.

## 10. Thread-bound transactions and rollback limitations

With common imperative transaction managers, a transaction is bound to the current thread through a thread-local mechanism. Spring binds transaction resources such as a JDBC connection to the thread running the test.

This leads to an important limitation: code running on another thread does not automatically join the test transaction. Example:

```java
@Test
@Transactional
void writesFromAnotherThread() {
    executorService.submit(() -> orderService.create(command)).join();
}
```

If the executor runs the work on another thread, the test thread's test transaction does not automatically propagate to that thread. The service may open and commit its own transaction. When the test finishes, rolling back the test transaction cannot revert this separate transaction.

Similarly, tests using preemptive timeouts such as JUnit Jupiter's assertTimeoutPreemptively() may run the executable on a different thread. If database operations occur on that thread, they may fall outside the test-managed transaction even though the test method is annotated with @Transactional.

A request sent to a real server is also typically processed on a server thread:

```text
Test thread
  +-- test-managed transaction T1
        +-- sends HTTP request
              |
              v
        Server request thread
          +-- application transaction T2

Rolling back T1 does not roll back T2 if T2 is independent.
```

Therefore, when using @SpringBootTest(webEnvironment = RANDOM_PORT) or DEFINED_PORT, do not assume the test's transaction wraps the transaction handling the HTTP request. Clean up committed data through an appropriate API or repository, use an isolated database/container, or design a clear test data strategy.

## 11. Test transactions and @Transactional on services

When the same service is invoked inside and outside a test-managed transaction, the outcome can differ:

| Invocation | Transaction boundary |
|---|---|
| Test without `@Transactional` calls `@Transactional(REQUIRED)` service | The service opens and closes its own transaction. |
| Test with `@Transactional` calls `@Transactional(REQUIRED)` service on same thread | The service joins the test transaction; the test decides the final rollback/commit. |
| Test with `@Transactional` calls `@Transactional(REQUIRES_NEW)` service | The service opens an independent transaction; that transaction can commit before the test rolls back. |
| Test with `@Transactional` calls `@Transactional(NOT_SUPPORTED)` service | The test transaction is suspended during the call; operations inside run outside that transaction. |
| Test with `@Transactional` calls service via another thread | The test thread's transaction does not automatically propagate to the new thread. |

This explains why a test with @Transactional might not accurately reproduce the service's commit behavior when running in the application. If the goal is to verify the service's transaction boundary, have at least one test that calls the service without a surrounding test transaction and checks the state after the service returns.

## 12. Rollback rules when exceptions occur

For application-managed transactions created by @Transactional, rollback rules are typically based on exception type: by default Spring rolls back on unchecked exceptions and Errors, whereas checked exceptions do not automatically trigger rollback unless an appropriate rollback rule is configured.

Test-managed transactions have Spring Test's own commit/rollback decision mechanism. By default, a test transaction rolls back after the test completes, even if the test fails. Do not infer that the test's rollback proves the service's rollback rule works properly; the test may simply be rolling back the entire transaction after the service has already completed.

If you want to test a service's rollback rule, call the service through its proxy in a test without a test-managed transaction, let the service transaction finish, and then query the data state in another transaction or through an appropriate repository.

Conceptual example:

```java
@Service
class RegistrationService {

    private final RegistrationRepository repository;

    RegistrationService(RegistrationRepository repository) {
        this.repository = repository;
    }

    @Transactional(rollbackFor = IOException.class)
    public void registerThenFail() throws IOException {
        repository.save(new Registration("user-1"));
        throw new IOException("External registration failed");
    }
}
```

Without declaring rollbackFor, a checked exception like IOException does not roll back the application transaction by default. With the configuration in the example, the service's transaction is rolled back when that exception exits the method through the proxy.

## 13. Certain @Transactional attributes on tests must be used within their proper scope

@Transactional on a test method/class is used by Spring Test to control the test-managed transaction. The interpretation of the annotation here is not completely identical to when it is placed on a service method.

Keep in mind:

- Use @Commit and @Rollback to express how the test transaction should end.
- Select the right transaction manager when the context has multiple managers.
- Special propagation modes such as NOT_SUPPORTED or NEVER can cause the test not to run in a transaction as expected.
- Do not assume every attribute of @Transactional on a service is supported or has the same meaning when placed on a test class/method. Consult the documentation for the exact Spring version you are using.
- If you need a transaction with specific isolation, timeout, or rollback rules for business logic, configure it on the application service/transaction template and verify it with an appropriate test.

A test annotated with @Transactional does not by itself prove that the service was invoked through a Spring proxy. If the test instantiates the service with new or calls an internal method via self-invocation, annotations on the service may not be applied as they are in the application.

## 14. Common pitfalls

### Assuming all database operations roll back because the test has @Transactional

Rollback only affects the transaction the test is managing. REQUIRES_NEW transactions, transactions on another thread, real server requests, or operations not participating in that transaction may have committed independently.

### Reading data after the transaction has rolled back

If an assertion runs after @AfterTransaction, data that only existed in the rolled-back test transaction will no longer be present. To inspect data before rollback, the assertion must run inside the test transaction; to verify after commit, use @Commit or TestTransaction.

### Service opens its own transaction, but the test does not use the Spring proxy

Creating a service with new does not activate the transaction interceptor. To test an application-managed transaction, obtain the service bean from the context and invoke it through the Spring proxy.

### Using @Transactional on a test to verify the service's rollback rule

The test transaction can roll back all data after the service finishes, making the test pass even if the service's rollback rule does not work as expected. Test the service's transaction with a test that has no surrounding transaction.

### Using preemptive timeouts with write operations

Test code may run on a different thread from the one holding the transaction. Data written on the auxiliary thread can commit independently. Use non-preemptive timeouts or a clear data cleanup strategy when testing database operations.

### Running tests through an HTTP server and expecting rollback from the test thread

Requests are processed on a server thread with its own transaction. The test transaction does not automatically span the request. Clean up data after the request or use an isolated database environment.

### Forgetting that @BeforeEach and @AfterEach run inside the test transaction

Fixtures created in @BeforeEach typically belong to the test transaction and are rolled back with the test. If you need data committed before the test transaction starts, use the @BeforeTransaction callback or an independent data preparation mechanism.

### Confusing @Commit with the service committing

@Commit requests committing the test-managed transaction when the test completes. It does not change the propagation or rollback rules of an application service.

## 15. Choosing a testing approach based on your goal

| Goal | Appropriate testing approach |
|---|---|
| Test a repository/service and automatically clean up data after the test | Use a test-managed transaction with `@Transactional` and default rollback. |
| Verify that a service joins an existing transaction | Open a test-managed transaction and call the REQUIRED service on the same thread. |
| Verify that a service commits on its own when run independently | Do not annotate the test with `@Transactional`; call the service bean through the Spring proxy and verify data after the call. |
| Verify that REQUIRES_NEW commits independently | Call the service inside a test transaction, then verify the independent transaction persists after the test rolls back and clean up the data. |
| Verify a service's rollback rule | Call the service through its proxy without a surrounding test transaction, then check the committed state. |
| Test requests through a real server | Use a separate data cleanup strategy; do not rely on the test thread's transaction. |
| Need to commit one phase and then continue the test | Use `TestTransaction.flagForCommit()`, `end()`, and `start()` while a test-managed transaction is active. |

A test-managed transaction is a tool for isolating data according to the test lifecycle. An application-managed transaction represents the business boundary of code running in the application. When the two transaction types meet, propagation, the transaction manager, and the executing thread determine which operations roll back with the test and which can commit independently.
