# Supported @Transactional attributes in test-managed transactions

The Spring TestContext Framework can open a transaction wrapping each test method so that data changes are reverted after the test ends. This mechanism is called a **test-managed transaction** and is typically enabled by the **@Transactional** annotation on a test class or test method.

However, **@Transactional** in tests does not apply the full semantics that it does when placed on an application service. Spring Test supports only a specific subset of attributes to control test-managed transactions. Several familiar attributes such as **isolation**, **timeout**, **readOnly**, and **rollbackFor**/**noRollbackFor** rules are not applied in the usual way in this context.

Understanding exactly which attributes take effect prevents writing a test that assumes it ran at a desired isolation level or timeout, or assumes a transaction will commit/roll back based on exception type when Spring Test does not use those rules.

## 1. What is a test-managed transaction?

The Spring TestContext Framework uses **TransactionalTestExecutionListener** to manage transactions for tests. This listener is registered by default in standard TestContext configurations, even when the test class does not declare **@TestExecutionListeners** itself.

To enable a test transaction, two conditions must be met:

1. The test's ApplicationContext has a bean implementing **PlatformTransactionManager**.
2. The test class or test method is annotated with **org.springframework.transaction.annotation.Transactional**.

Example:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void savesCustomer() {
        repository.save(new Customer("CUS-01", "Lan"));

        assertTrue(repository.findById("CUS-01").isPresent());
    }
}
~~~

Spring starts the transaction before the test method runs. By default, the transaction is rolled back when the test finishes, even when the test passes. As a result, data created by the test is no longer in the database after the transaction ends.

Three types of transactions must be distinguished:

| Type | Who manages it? | Example |
|---|---|---|
| Test-managed transaction | Spring TestContext via TransactionalTestExecutionListener or TestTransaction | Transaction wrapping a test method |
| Spring-managed transaction | Spring transaction infrastructure in the ApplicationContext | @Transactional on a service/repository |
| Application-managed transaction | Application code managing transactions via transaction APIs | Code calling TransactionTemplate or transaction APIs directly |

Transactions created by a service typically join the test-managed transaction if propagation is compatible, most commonly **REQUIRED** or **SUPPORTS**. Be careful with other propagation modes because they can create an independent transaction or suspend the test's transaction.

## 2. Table of supported @Transactional attributes

The Spring TestContext Framework documents a specific scope of support for test-managed transactions:

| @Transactional attribute | Supported in test-managed transactions | How to interpret |
|---|---|---|
| value and transactionManager | Yes | Selects the transaction manager by qualifier or bean name |
| propagation | Only recognizes NOT_SUPPORTED and NEVER | These two values request that the test run without a transaction |
| isolation | No | Not used to set the isolation level for the test transaction |
| timeout | No | Not used to set a timeout for the test transaction |
| readOnly | No | Not used to configure the test transaction in read-only mode |
| rollbackFor and rollbackForClassName | No | Use TestTransaction.flagForRollback() when programmatic rollback control is needed |
| noRollbackFor and noRollbackForClassName | No | Use TestTransaction.flagForCommit() when programmatic commit control is needed |

This table refers to the **@Transactional** annotation on a test class or test method—that is, transactions managed by Spring Test. It does not mean those attributes lose effect in transactions managed by the application's services.

For instance, **@Transactional(readOnly = true)** on a service still carries meaning for the application's transaction infrastructure. However, placing **readOnly = true** on a test method to request a read-only test-managed transaction is not supported by Spring Test.

## 3. value and transactionManager: selecting the transaction manager

The two attributes **value** and **transactionManager** are aliases of each other in **@Transactional**. They let you specify which transaction manager to use for the test.

If the ApplicationContext has only one matching **PlatformTransactionManager** bean, Spring Test can usually locate and use that bean according to default rules.

If there are multiple transaction managers, explicitly specify the bean:

~~~java
@SpringJUnitConfig(MultiDatabaseTestConfiguration.class)
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
    // The test uses the transaction manager for the orders database.
}
~~~

Or write explicitly:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
}
~~~

The name passed in is the qualifier or bean name Spring uses to find the matching transaction manager. This declaration is helpful when the application has multiple databases, for example:

- ordersTransactionManager manages the orders database.
- billingTransactionManager manages the billing database.
- auditTransactionManager manages the audit database.

Whichever database the test needs to roll back data on must use the exact transaction manager governing that resource. Selecting the wrong manager can prevent the test from rolling back on the database the repository actually uses.

### Selecting a transaction manager via shared configuration

If the application has multiple PlatformTransactionManager beans and wants to designate a default manager, a configuration can implement TransactionManagementConfigurer:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionConfiguration
        implements TransactionManagementConfigurer {

    private final PlatformTransactionManager transactionManager;

    TransactionConfiguration(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager transactionManager
    ) {
        this.transactionManager = transactionManager;
    }

    @Override
    public PlatformTransactionManager annotationDrivenTransactionManager() {
        return transactionManager;
    }
}
~~~

This is a general configuration mechanism for transaction annotations. For tests that need a manager other than the default, declaring **@Transactional(transactionManager = "...")** directly on the test is usually clearer.

## 4. propagation: the two special supported values

In test-managed transactions, Spring Test supports only two propagation values to indicate that the test runs without a transaction:

- **Propagation.NOT_SUPPORTED**
- **Propagation.NEVER**

These two values mean the test must not execute inside a test-managed transaction.

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
class TransactionBoundaryTest {

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void runsWithoutTestManagedTransaction() {
        assertFalse(TestTransaction.isActive());
    }

    @Test
    @Transactional(propagation = Propagation.NEVER)
    void alsoRunsWithoutTestManagedTransaction() {
        assertFalse(TestTransaction.isActive());
    }
}
~~~

These modes can be used when a test needs to observe behavior occurring outside a transaction, or verify data already committed from another transaction.

Other propagation modes are not ways to configure test-managed transactions. Do not use **REQUIRES_NEW**, **MANDATORY**, **NESTED**, or **SUPPORTS** on a test annotation expecting Spring Test to open a test transaction with those semantics.

Distinguish this from propagation on application services. A service using **@Transactional(propagation = REQUIRED)** usually joins the test's transaction. If the service uses **REQUIRES_NEW**, it can suspend the test transaction, run an independent transaction, and commit its own data. Data committed in the independent transaction can still persist after the test transaction rolls back.

## 5. isolation, timeout, and readOnly do not apply to test-managed transactions

This group of attributes easily causes confusion because they are valid attributes of **@Transactional** in applications.

### isolation

In a service transaction, the isolation level describes the degree of isolation between concurrent transactions. Example:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void updateInventory() {
    // Logic to update inventory.
}
~~~

When placed on a service, the transaction manager can use the corresponding isolation level when creating a new transaction, depending on the data platform's capabilities and configuration.

However, on a test method:

~~~java
@Test
@Transactional(isolation = Isolation.SERIALIZABLE)
void checksInventory() {
    // Cannot rely on this annotation to make the
    // test-managed transaction use SERIALIZABLE.
}
~~~

Spring Test does not support **isolation** for test-managed transactions. If you need to test isolation, design a dedicated transaction test using **TransactionTemplate** or real service transactions, create independent transactions, and verify concurrency behavior on an appropriate database.

### timeout

**timeout** on an application transaction is the time limit the transaction manager can apply to the transaction. However, this attribute is not supported in test-managed transactions.

~~~java
@Test
@Transactional(timeout = 5)
void checksDatabaseOperation() {
    // Do not assume the test transaction will have a 5-second timeout.
}
~~~

If you need to limit test execution time, use the test framework's timeout appropriately. Note that preemptive timeouts can run the test method on a different thread and lose association with the test-managed transaction; this issue is explained in a later section.

### readOnly

**readOnly** can be a hint or configuration for the transaction manager when running an application transaction:

~~~java
@Transactional(readOnly = true)
public List<Customer> findCustomers() {
    return repository.findAll();
}
~~~

However, **readOnly = true** on a test method does not turn the test-managed transaction into a read-only transaction.

~~~java
@Test
@Transactional(readOnly = true)
void readsCustomers() {
    // Do not rely on readOnly on the test annotation to block data writes.
}
~~~

If a test must ensure code does not write data, verify the behavior using database permissions, appropriate transaction configuration, or assertions on data state. The annotation on the test provides no read-only guarantee in a test-managed transaction.

## 6. rollbackFor and noRollbackFor are not supported

In application transactions, rollback rule attributes determine which exceptions cause the transaction to roll back or still commit.

Example on a service:

~~~java
@Transactional(rollbackFor = BusinessException.class)
public void processPayment() throws BusinessException {
    // ...
}
~~~

Or:

~~~java
@Transactional(noRollbackFor = NotificationException.class)
public void completeOrder() {
    // ...
}
~~~

These rules belong to application-managed transactions. When placed on a test method to control a test-managed transaction, Spring Test does not support them:

~~~java
@Test
@Transactional(rollbackFor = IllegalArgumentException.class)
void testRollbackRule() {
    // rollbackFor on a test annotation does not control
    // the completion outcome of the test-managed transaction.
}
~~~

To control the outcome of a test-managed transaction, there are two primary options:

- **@Rollback** or **@Commit** to declare completion behavior.
- **TestTransaction.flagForRollback()** or **TestTransaction.flagForCommit()** to decide programmatically.

### Using @Rollback

By default, test-managed transactions roll back. This can be declared explicitly:

~~~java
@Test
@Transactional
@Rollback
void rollsBackChanges() {
    repository.save(new Customer("CUS-02", "Minh"));
}
~~~

**@Rollback** also accepts a boolean:

~~~java
@Test
@Transactional
@Rollback(false)
void commitsChanges() {
    repository.save(new Customer("CUS-03", "An"));
}
~~~

**@Rollback(false)** requests a commit when the test finishes normally according to the transaction lifecycle.

### Using @Commit

**@Commit** is an explicit way to express commit intent:

~~~java
@Test
@Transactional
@Commit
void commitsCustomer() {
    repository.save(new Customer("CUS-04", "Hoa"));
}
~~~

You can place **@Rollback** or **@Commit** at the class level as the default for test methods. Method-level annotations can override the class-level choice.

Only commit in tests when data needs to persist after the test, such as a test that needs to confirm committed state in a later phase. Tests that commit data must have their own cleanup strategy so they do not affect other tests or shared environments.

## 7. Using TestTransaction to control transactions programmatically

**TestTransaction** provides a static API to interact with the test-managed transaction. This API is available when **TransactionalTestExecutionListener** is enabled.

Commonly used operations:

| Method | Meaning |
|---|---|
| isActive() | Checks whether a test-managed transaction is currently active |
| flagForRollback() | Marks the current transaction to roll back when ended |
| flagForCommit() | Marks the current transaction to commit when ended |
| end() | Ends the current transaction according to the commit/rollback flag |
| start() | Starts a new test-managed transaction |
| isFlaggedForRollback() | Checks whether the current transaction is flagged for rollback |

Example ending the first transaction with a commit and then starting a new transaction:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerTransactionTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void commitsOnePhaseAndRollsBackTheNext() {
        repository.save(new Customer("CUS-10", "Mai"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertTrue(repository.findById("CUS-10").isPresent());

        TestTransaction.start();

        repository.save(new Customer("CUS-11", "Nam"));

        // The new transaction will roll back by default
        // when the test completes unless the flag is changed.
    }
}
~~~

**TestTransaction.end()** completes the current transaction. After it ends, you can verify committed state with an appropriate query and then call **start()** to open a new transaction for the remainder of the test.

Ensure the query verifying committed state actually observes the database post-commit, rather than merely reading an entity still in the old persistence context. With JPA, you may need to flush/clear or use a new read connection/transaction depending on the goal.

### When to use TestTransaction instead of @Commit?

Use **@Commit** when the entire test needs to commit upon completion. Use **TestTransaction** when a test needs multiple phases, for example:

1. Create data in the first transaction.
2. Commit the first transaction so the data becomes durable.
3. Start the second transaction.
4. Test subsequent behavior.
5. Roll back the second transaction when the test ends.

This approach is useful when testing logic that depends on already-committed data or another process that only sees data after commit.

## 8. Selecting the right transaction manager when there are multiple databases

An ApplicationContext can contain multiple **PlatformTransactionManager** beans. For example, an application has an orders database and a reports database.

~~~java
@Configuration
class MultiDatabaseConfiguration {

    @Bean
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource
    ) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    PlatformTransactionManager reportsTransactionManager(
            @Qualifier("reportsDataSource") DataSource dataSource
    ) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Tests for the orders repository must select the right manager:

~~~java
@SpringJUnitConfig(MultiDatabaseConfiguration.class)
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
    // Changes to the orders database belong to the test transaction.
}
~~~

If the test selects **reportsTransactionManager** while the repository uses **ordersDataSource**, changes to the orders database are not part of the transaction managed by the test. Rolling back the reports manager cannot revert data in the orders database.

When multiple managers coexist, clearly identify:

- Which DataSource the repository uses.
- Which transaction manager governs that DataSource.
- Which manager the test declares.
- Whether any service opens an independent transaction on another manager.

A test using multiple databases does not by default have a global transaction spanning all resources. Unless the application uses distributed transactions, rolling back one manager only controls resources belonging to that manager.

## 9. Which lifecycle methods run inside the transaction?

For a transactionally managed test method, when the transaction starts and ends affects setup and cleanup.

| Callback | Inside the test-managed transaction? |
|---|---|
| @BeforeTransaction | No, runs before the transaction starts |
| JUnit Jupiter @BeforeEach | Yes |
| Test method with @Transactional | Yes |
| JUnit Jupiter @AfterEach | Yes |
| @AfterTransaction | No, runs after the transaction ends |
| JUnit Jupiter @BeforeAll | No |
| JUnit Jupiter @AfterAll | No |

**@Transactional** is not supported on lifecycle methods such as **@BeforeAll**, **@BeforeEach**, **@AfterEach**, or **@AfterAll**. Place the annotation at the test class or test method level for Spring Test to manage the transaction.

### @BeforeEach and @AfterEach

**@BeforeEach** and **@AfterEach** methods run inside the corresponding test method's test-managed transaction.

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @BeforeEach
    void prepare() {
        repository.save(new Customer("CUS-20", "Test"));
    }

    @Test
    void findsPreparedCustomer() {
        assertTrue(repository.findById("CUS-20").isPresent());
    }

    @AfterEach
    void verifyBeforeRollback() {
        assertEquals(1, repository.count());
    }
}
~~~

Data created in setup and checked in the test both belong to the test transaction. After the test completes, the transaction rolls back by default.

### @BeforeTransaction and @AfterTransaction

If you need to inspect database state before the transaction starts or after it finishes, use these two annotations:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerCommitTest {

    @Autowired
    private CustomerRepository repository;

    @BeforeTransaction
    void verifyInitialState() {
        assertFalse(repository.existsById("CUS-30"));
    }

    @Test
    @Commit
    void commitsCustomer() {
        repository.save(new Customer("CUS-30", "Linh"));
    }

    @AfterTransaction
    void verifyCommittedState() {
        assertTrue(repository.existsById("CUS-30"));
    }
}
~~~

**@BeforeTransaction** and **@AfterTransaction** only run for test methods that have a test-managed transaction. They are the right place to verify state outside the test transaction.

With JUnit Jupiter and SpringExtension, these methods can accept parameters supplied by a JUnit ParameterResolver, such as **@Autowired** beans. In simple examples, injected fields can be used.

### @BeforeAll and @AfterAll

Class-level lifecycle methods run outside test-managed transactions. If transactional operations are needed in these methods, you can inject **PlatformTransactionManager** and use **TransactionTemplate**:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
class DatabaseSuiteSetup {

    @Autowired
    private PlatformTransactionManager transactionManager;

    void performTransactionalSetup() {
        new TransactionTemplate(transactionManager)
                .executeWithoutResult(status -> {
                    // Perform data operations inside a separate transaction.
                });
    }
}
~~~

If using static **@BeforeAll**, the method cannot directly access instance fields under the default lifecycle. You can use JUnit's PER_CLASS lifecycle or an appropriate configuration approach. The key point is that class-level transactions must be managed explicitly with an API like **TransactionTemplate**.

## 10. Why can preemptive timeouts cause data not to roll back?

Spring Test binds test-managed transaction state to the current thread using **ThreadLocal**. Consequently, all database operations in a test method must run on the thread holding that transaction.

Some timeout APIs may run the tested code on a different thread, such as JUnit Jupiter's:

~~~java
assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> service.updateCustomer(customer)
);
~~~

If the callback executes on a new thread, that thread lacks the transaction context Spring Test bound to the original test thread. A database transaction may be opened and committed independently under standard configuration. Afterward, Spring rolls back the transaction bound to the original thread, yet data written by the new thread persists.

Cases requiring caution include:

- JUnit Jupiter assertTimeoutPreemptively(...).
- JUnit 4 @Test(timeout = ...) and the TimeOut rule.
- TestNG @Test(timeOut = ...).

When a test relies on automatic rollback, use non-preemptive timeouts where suitable for the framework, or explicitly verify and clean up data. Do not assume Spring Test's rollback can revert operations executed on another thread.

## 11. ORM may not have sent SQL even after the test called save

When using JPA or Hibernate, a save operation may only modify the in-memory persistence context. Actual SQL may be sent upon flush or transaction commit.

Because test-managed transactions typically roll back at the end of a test, some errors that only surface at flush time may go undetected if the test simply calls save and finishes.

Example:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void detectsConstraintViolationDuringFlush() {
        repository.save(new Customer("CUS-40", "Lan"));
        repository.save(new Customer("CUS-40", "Duplicate"));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> entityManager.flush()
        );
    }
}
~~~

This example illustrates flushing so the constraint error appears while the test is running. The actual exception type depends on the JPA provider, database, and Spring's exception translation layer.

You can use **entityManager.flush()** or **sessionFactory.getCurrentSession().flush()** to force the ORM to send SQL. If you need to verify reading back from the database instead of the persistence context, call **entityManager.clear()** after flushing and then re-query.

Flushing is not committing. Data remains inside the current transaction and can roll back when the test finishes.

For entity lifecycle callbacks, flushing is also important. Certain callbacks such as **@PostPersist**, **@PreUpdate**, or **@PostUpdate** are only invoked when the persistence context is flushed. If you need to verify a callback re-reads data, sometimes you must clear the persistence context to avoid retrieving an already-managed entity from memory.

## 12. Service transactions can escape the test transaction

By default, a service transaction with **REQUIRED** propagation typically joins the current test transaction. When the test finishes and rolls back, changes in the shared transaction also roll back.

However, if the service uses a propagation that creates a separate transaction, behavior differs.

Example:

~~~java
@Service
class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String action) {
        // Record audit in an independent transaction.
    }
}
~~~

If a test calls record() while a test-managed transaction is active, Spring can suspend the test transaction, open a new transaction for AuditService, and commit that transaction when the method completes. Then the test transaction resumes. When the test rolls back, the audit record committed in the independent transaction may still persist.

This is not a bug in rollback. It is the result of distinct transaction boundaries.

Similarly, an HTTP call to a server running in another process/thread or a message published to a broker is not automatically rolled back along with the test's database transaction.

When testing these behaviors, clearly identify which transaction governs each resource and which side effects require cleanup. You can use a separate test database, a separate namespace, or delete created data after the test.

## 13. Comprehensive example: selecting a manager, committing, and verifying outside the transaction

The following example illustrates several commonly used attributes and callbacks:

~~~java
@SpringJUnitConfig(PersistenceTestConfiguration.class)
@Transactional(transactionManager = "ordersTransactionManager")
@Commit
class OrderTransactionTest {

    @Autowired
    private OrderRepository repository;

    @BeforeTransaction
    void verifyInitialState() {
        assertFalse(repository.existsById("ORD-50"));
    }

    @BeforeEach
    void prepare() {
        // This setup runs inside the test-managed transaction.
    }

    @Test
    @Rollback
    void rollsBackThisTestDespiteClassLevelCommit() {
        repository.save(new Order("ORD-50"));
        assertTrue(repository.existsById("ORD-50"));
    }

    @Test
    void commitsByClassDefault() {
        repository.save(new Order("ORD-51"));
    }

    @AfterEach
    void verifyWithinTransaction() {
        // Can read data within the current transaction.
    }

    @AfterTransaction
    void verifyAfterCompletion() {
        assertTrue(repository.existsById("ORD-51"));
        assertFalse(repository.existsById("ORD-50"));
    }
}
~~~

Class-level **@Commit** sets commit as the default for test methods. The first method uses **@Rollback** to override and roll back. The second method uses the class-level default and commits. **@BeforeTransaction** runs before the transaction; **@AfterTransaction** runs after the transaction completes.

In practice, if two tests both write data to one database, ensure they are independent of execution order. This example focuses on annotation semantics; real test suites should use unique IDs or isolated fixtures to avoid data contention.

## 14. Common misconceptions

### Thinking all @Transactional attributes take effect on tests

Test-managed transactions only support the subset of attributes documented by Spring Test. **isolation**, **timeout**, **readOnly**, and rollback rules are not applied in the usual way. Use the right API for the target behavior you want to test.

### Using rollbackFor to decide the test transaction outcome

**rollbackFor** and **noRollbackFor** do not control test-managed transactions. Use **@Rollback**, **@Commit**, or **TestTransaction.flagForRollback()**/**flagForCommit()**.

### Putting @Transactional on @BeforeEach

Spring Test does not support **@Transactional** on lifecycle methods. Place the annotation at the class or test method level. **@BeforeEach** and **@AfterEach** will run inside the already-managed transaction of the test method.

### Selecting the wrong transaction manager

When multiple managers exist, rollback only applies to resources governed by the selected manager. Verify the repository, DataSource, and corresponding manager; use **@Transactional("beanName")** when needed.

### Thinking rollback will also revert REQUIRES_NEW transactions

Independent transactions can commit on their own. Rolling back the test transaction does not automatically revert independently committed transactions.

### Thinking every operation inside a test method is inside the transaction

Test transactions are bound to the current thread. Code running on another thread, such as a preemptive timeout callback or a request processed on a server thread, may fall outside that transaction.

### Failing to flush when testing JPA/Hibernate

The ORM may hold changes in the persistence context. Without flushing, tests may miss SQL or constraint errors that only arise when statements are sent to the database.

### Using @Commit without cleaning up data

Committing causes data to persist after the test. If tests rerun or run in parallel, leftover data can alter results. Use unique data and explicit cleanup.

## 15. Choosing attributes and APIs by testing goal

| Goal | How to implement |
|---|---|
| Use default transaction manager | @Transactional |
| Select one of multiple transaction managers | @Transactional(transactionManager = "...") |
| Test does not need a test-managed transaction | propagation = NOT_SUPPORTED or NEVER |
| Use a specific isolation level | Test application transactions or use TransactionTemplate |
| Set timeout for application transaction | Configure on the service transaction; do not rely on test-managed timeout |
| Require read-only on a service | Set readOnly on the application transaction and verify with an appropriate mechanism |
| Default rollback | @Transactional without @Commit or @Rollback(false) |
| Commit test | @Commit or @Rollback(false) |
| Decide commit/rollback mid-test | TestTransaction.flagForCommit() or flagForRollback() |
| Start/end transaction mid-test | TestTransaction.end() and TestTransaction.start() |
| Verify state before/after transaction | @BeforeTransaction and @AfterTransaction |
| Run transaction in @BeforeAll/@AfterAll | TransactionTemplate with injected manager |
| Force ORM to send SQL before assertion | EntityManager.flush() or Hibernate Session flush |

When using **@Transactional** in Spring Framework Testing, first determine whether the test needs a transaction, which transaction manager governs the data, and whether the final outcome should be rollback or commit. Then rely only on the attributes Spring Test actually supports. For isolation, timeout, read-only, and rollback rules of application transactions, test at the appropriate transaction boundary. For test-managed transactions, use **@Commit**, **@Rollback**, or **TestTransaction** to control the outcome; place out-of-transaction checks in **@BeforeTransaction** and **@AfterTransaction**; and pay attention to thread-bound context, independent transactions, and ORM flush timing.

## References

- [Spring Framework Reference — Transaction Management in the TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [TransactionalTestExecutionListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TransactionalTestExecutionListener.html)

