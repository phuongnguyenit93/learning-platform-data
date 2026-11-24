# Requirements for PlatformTransactionManager and @Transactional

The Spring TestContext Framework supports running tests within a transaction managed by the framework. This mechanism is useful when testing repositories, services, or business flows that write data: the test performs operations just like the real application, reads back the results within the transaction, and then Spring automatically rolls back after the test finishes.

For a standard transactional test to work, the test context needs an appropriate **PlatformTransactionManager** bean and the test must be annotated with **@Transactional**. Spring Test uses **TransactionalTestExecutionListener** to detect the annotation, look up the transaction manager, start the transaction before the test method, and complete the transaction after the test.

These two requirements serve two distinct roles:

- **PlatformTransactionManager** provides the capability to start, commit, and roll back transactions for a specific resource type, such as JDBC or JPA.
- **@Transactional** requests that the test run inside a transaction managed by Spring Test.

Merely having a transaction manager in the context does not mean every test automatically runs in a transaction. Conversely, a test annotated with @Transactional that cannot find an appropriate transaction manager will fail to initialize a test-managed transaction.

## 1. What is PlatformTransactionManager?

PlatformTransactionManager is Spring's imperative transaction interface. It defines the core operations for managing transactions:

- getTransaction(...): retrieves the current transaction or starts a new one according to the requested attributes.
- commit(...): commits the transaction.
- rollback(...): rolls back the transaction.

Implementations connect Spring's transaction abstraction to a specific persistence technology or transaction coordinator.

| Transaction manager | Resource typically managed | When commonly used |
|---|---|---|
| DataSourceTransactionManager | A JDBC DataSource | Applications using JDBC directly |
| JdbcTransactionManager | A JDBC DataSource | JDBC transactions with Spring exception translation support |
| JpaTransactionManager | A JPA EntityManagerFactory | Applications using JPA/Hibernate |
| JtaTransactionManager | Distributed transactions managed by JTA | Multiple resources participating in a single distributed transaction |

Choose the manager that matches the resource your test is using. For example, if the repository uses JPA, JpaTransactionManager is usually the right choice. If the application uses plain JDBC with a single DataSource, DataSourceTransactionManager or JdbcTransactionManager can handle it.

A test context can contain multiple transaction managers, such as one manager for the orders database and one manager for the reporting database. In that case, the test should explicitly specify which manager to use instead of leaving Spring to guess.

## 2. Requirements for Spring Test to manage transactions

For imperative transactional tests, the following components are needed:

1. The test runs with the Spring TestContext Framework, typically via @SpringJUnitConfig, @SpringBootTest, or a test slice.
2. TransactionalTestExecutionListener must be registered in the test's listener list.
3. The ApplicationContext must provide a PlatformTransactionManager that Spring can discover.
4. The test class or test method is annotated with @Transactional.
5. The resource under test must participate in the transaction managed by that manager.

Spring TestContext registers default listeners, including TransactionalTestExecutionListener. Therefore, when using standard test configurations, you usually do not need to register this listener manually.

Example with Spring Framework:

~~~java
@SpringJUnitConfig(TestDatabaseConfiguration.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomer() {
        // The test runs in a transaction managed by Spring Test.
    }
}
~~~

TestDatabaseConfiguration must provide both the repository under test and an appropriate transaction manager. If the configuration only creates the repository without providing a PlatformTransactionManager, Spring cannot start a test-managed transaction.

With Spring Boot, a transaction manager can be auto-configured when the classpath and application configuration meet the conditions. However, do not assume every test slice or custom configuration includes a manager. When a test context is narrowed down, verify which beans are actually loaded.

## 3. Declaring a transaction manager in test configuration

With JDBC, a simple configuration can register a DataSource and a DataSourceTransactionManager:

~~~java
@Configuration
class JdbcTestConfiguration {

    @Bean
    DataSource dataSource() {
        return new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .build();
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

A test can use this manager:

~~~java
@SpringJUnitConfig({
    JdbcTestConfiguration.class,
    CustomerRepositoryConfiguration.class
})
@Transactional
class JdbcCustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void storesAndReadsCustomer() {
        Customer saved = customerRepository.save(
            new Customer("customer-01", "Ada")
        );

        Customer loaded = customerRepository.findById(saved.id())
            .orElseThrow();

        assertEquals("Ada", loaded.name());
    }
}
~~~

This example illustrates the configuration structure; the repository and schema must be implemented according to the project's model. The transaction manager is created from the exact DataSource that the repository uses. If the repository and the manager point to two different datasources, the test's transaction may not cover the write operations the test is verifying.

With JPA, the configuration typically uses JpaTransactionManager:

~~~java
@Bean
PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
~~~

In Spring Boot, the manager bean is typically auto-configured alongside the DataSource or EntityManagerFactory. If you already have a custom transaction manager configuration, ensure that bean is included in the right test context.

## 4. Role of @Transactional on test classes and test methods

Spring Test allows placing @Transactional at the class level or method level.

### 4.1. Placing on a test class

When placed on the class, the test methods in that class run inside a test-managed transaction according to that configuration:

~~~java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        // ...
    }

    @Test
    void rejectsInvalidOrder() {
        // ...
    }
}
~~~

This is a convenient option when most test methods in the class need a transaction. Each method receives its own test transaction according to the Spring Test lifecycle.

### 4.2. Placing on a test method

If only some tests need a transaction, place the annotation on the method:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    @Transactional
    void createsOrderWithinTestTransaction() {
        // ...
    }

    @Test
    void checksApplicationHealthWithoutTransaction() {
        // ...
    }
}
~~~

A method without @Transactional that does not inherit transaction configuration from the class will not be automatically wrapped in a test-managed transaction by Spring Test.

### 4.3. Method-level and class-level configuration

When both the class and the method have the annotation, the method-level configuration is used for that method according to Spring Test's annotation lookup rules. This is useful when one method needs a different transaction manager or a specific transaction policy.

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {

    @Test
    void usesOrdersDatabase() {
        // Uses ordersTransactionManager.
    }

    @Test
    @Transactional(transactionManager = "auditTransactionManager")
    void usesAuditDatabase() {
        // Selects the manager dedicated to audit.
    }
}
~~~

In this example, both managers must exist in the test context. The method-level annotation determines the manager for that test. If there is only one manager, specifying the name is unnecessary.

## 5. How does Spring look up PlatformTransactionManager?

When a test has @Transactional, Spring Test must locate an appropriate manager in the ApplicationContext. Common rules:

- If the annotation specifies a name or qualifier via transactionManager (or its alias value), Spring looks up the corresponding manager.
- If unspecified, Spring prioritizes a bean with the default name transactionManager.
- If there is no bean with the default name, but only a single matching PlatformTransactionManager exists, Spring can use that unique manager.
- If multiple managers exist and a suitable manager cannot be determined, transaction preparation fails.

Example specifying the name explicitly:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
    // ...
}
~~~

Or using the value alias:

~~~java
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
    // ...
}
~~~

The name in the annotation must match a bean name or qualifier that Spring can resolve. If the project has multiple databases, give managers meaningful names based on the resource and use those names consistently in both tests and services.

If you encounter an error where the transaction manager cannot be found, check:

- Is the manager bean registered in the current context?
- Does the bean implement the PlatformTransactionManager type?
- Are there multiple managers of the same type?
- Does the default manager have the name transactionManager?
- Does transactionManager in the annotation point to the right bean?
- Does the manager govern the exact DataSource or EntityManagerFactory used by the repository?

## 6. What does TransactionalTestExecutionListener do?

TransactionalTestExecutionListener is the component of the Spring TestContext Framework responsible for integrating @Transactional with the test lifecycle.

At a high level, the listener performs the following steps:

1. Reads @Transactional metadata on the test class or test method.
2. Resolves the appropriate transaction manager in the ApplicationContext.
3. Starts the test-managed transaction before the test method executes.
4. Binds transaction information to the test context so related callbacks can access it.
5. After the test method, determines whether the transaction must roll back or commit.
6. Completes the transaction and executes post-transaction callbacks when appropriate.

Because the listener participates in the test lifecycle, the transaction is not created by an ordinary @Transactional proxy wrapping the test method. Spring Test proactively starts and completes the transaction so it can apply the default rollback policy.

If a project customizes @TestExecutionListeners and replaces the default listener list, ensure TransactionalTestExecutionListener remains registered. You can use the merge mode with default listeners when you want to add custom listeners while keeping standard Spring Test features.

## 7. Test-managed transactions and application transactions

These two types of transactions are related, though they originate from different sources:

- **Test-managed transaction:** started by Spring TestContext before the test method and ended after the test method.
- **Spring-managed transaction:** started by Spring's transaction interceptor when the application invokes a method annotated with @Transactional.
- **Application-managed transaction:** started and completed by application code or a library via the corresponding transaction API.

Service example:

~~~java
@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        return repository.save(Order.from(command));
    }
}
~~~

Test:

~~~java
@SpringBootTest
@Transactional
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.create(validCommand());

        assertTrue(order.getId() != null);
    }
}
~~~

If a test-managed transaction is active with the default REQUIRED propagation, the service call typically joins the current transaction. When the test ends and Spring rolls back, changes in that transaction are also rolled back.

To test the service's transaction without a surrounding transaction from the test, remove @Transactional from the test method or class. Then the service proxy starts and completes its own transaction according to its configuration. This is how you verify commits or rollbacks decided by the service itself.

Do not always put @Transactional on every integration test without considering the goal. A test with an outer transaction can mask the service's actual commit behavior.

## 8. Default rollback and how to request a commit

By default, a test-managed transaction is rolled back after the test method. This prevents test data from persisting into other tests:

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void insertsCustomer() {
        repository.save(new Customer("customer-02", "Lin"));
        repository.flush();

        assertEquals(1, repository.count());
    }
}
~~~

After the test ends, Spring rolls back the transaction. Other tests do not see this record if they use the same database and appropriate transaction isolation.

If you need to commit the test's transaction, you can use @Commit:

~~~java
@Test
@Transactional
@Commit
void persistsFixtureForFollowingVerification() {
    repository.save(new Customer("customer-03", "Mina"));
}
~~~

Or use @Rollback(false):

~~~java
@Test
@Transactional
@Rollback(false)
void commitsTestTransaction() {
    repository.save(new Customer("customer-04", "Noah"));
}
~~~

@Commit expresses the commit intent clearly; @Rollback(false) disables the default rollback behavior. Only use commit when the test genuinely needs data to persist beyond the transaction. If committing into a shared database, you must have an isolated data strategy and cleanup to avoid affecting subsequent runs.

## 9. Controlling transactions with TestTransaction

In some tests, you need to end a transaction mid-method, verify committed data, and then continue in another transaction. Spring Test provides TestTransaction to control test-managed transactions:

- isActive() checks whether a test transaction is currently active.
- flagForRollback() requests a rollback when the transaction ends.
- flagForCommit() requests a commit when the transaction ends.
- end() ends the current transaction according to the commit/rollback flag.
- start() starts a new test-managed transaction if supported by the lifecycle.

Example:

~~~java
@SpringBootTest
@Transactional
class CommittedOrderTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void commitsThenStartsAnotherTestTransaction() {
        Order order = orderRepository.save(validOrder());
        orderRepository.flush();

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());

        TestTransaction.start();
        Order stored = orderRepository.findById(order.getId())
            .orElseThrow();
        assertEquals(order.getId(), stored.getId());
    }
}
~~~

The example illustrates transaction control; if a test commits data, the committed data must be cleaned up after verification. TestTransaction only controls transactions managed by Spring Test, and is not a general-purpose API for controlling arbitrary transactions created by the application.

## 10. @BeforeEach, @AfterEach, and callbacks outside the transaction

When a test method runs inside a test-managed transaction, regular JUnit @BeforeEach and @AfterEach callbacks also run inside that transaction:

~~~java
@SpringBootTest
@Transactional
class InventoryRepositoryTest {

    @BeforeEach
    void prepareData() {
        // Repository operations in this callback participate in the test transaction.
    }

    @Test
    void updatesStock() {
        // ...
    }

    @AfterEach
    void inspectStateBeforeRollback() {
        // Still inside the test method's transaction.
    }
}
~~~

If you need to run logic before or after the test transaction, Spring Test provides:

- @BeforeTransaction: runs before the test-managed transaction starts.
- @AfterTransaction: runs after the test-managed transaction ends.

~~~java
@SpringBootTest
@Transactional
class TransactionBoundaryTest {

    @BeforeTransaction
    void beforeTransaction() {
        // Verify database state before the test transaction.
    }

    @Test
    void performsDatabaseWork() {
        // Runs inside the test-managed transaction.
    }

    @AfterTransaction
    void afterTransaction() {
        // Verify state after the transaction has rolled back/committed.
    }
}
~~~

These callbacks are useful when you want to verify that data does not exist before the test or has been properly committed/rolled back after the test. They must be placed in a test class with appropriate transaction management; if the test does not run in a test-managed transaction, there is no corresponding transaction boundary for the callbacks to attach to.

## 11. @Transactional attributes to watch out for in tests

Spring's @Transactional has many attributes, but test-managed transactions do not apply all of them in the same way as production method transactions.

Points to keep in mind:

- value and transactionManager: used to select the transaction manager for the test.
- propagation: the test framework has its own rules for propagation; NOT_SUPPORTED and NEVER can be used to request that the test not run in a test-managed transaction. Other propagation modes must be considered in light of Spring TestContext limitations and the test's goal.
- isolation, timeout, and readOnly: are not used as a full way to configure a test transaction identically to an ordinary business method.
- rollbackFor and noRollbackFor: are not the recommended mechanism for controlling test rollback; use @Rollback, @Commit, or TestTransaction to express the test transaction's completion policy.

If you need to test the isolation level, timeout, or rollback rules of a production service, write a test that calls the service through its proxy in a service-managed transaction and observe behavior at the appropriate boundary. Do not assume an annotation on a test method thoroughly tests all transaction attributes of a service.

## 12. Transaction managers and multiple datasources

An application can have multiple datasources and multiple transaction managers. For example, orders and reporting may be stored in two separate databases:

~~~java
@Configuration
class MultiDatabaseConfiguration {

    @Bean
    @Primary
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Test for the orders repository:

~~~java
@SpringJUnitConfig(MultiDatabaseConfiguration.class)
@Transactional("ordersTransactionManager")
class OrdersRepositoryTest {
    // ...
}
~~~

Test for the audit repository:

~~~java
@SpringJUnitConfig(MultiDatabaseConfiguration.class)
@Transactional("auditTransactionManager")
class AuditRepositoryTest {
    // ...
}
~~~

@Primary helps Spring choose a default manager in situations that require a preferred candidate. However, if a test intends to use a specific database, declaring the manager name directly clearly expresses the resource being managed.

A typical transaction manager only manages the resource it is configured to govern. Two independent datasources with two local transaction managers do not automatically form a single unified distributed transaction. If a test writes to both databases, rolling back the first manager does not guarantee rolling back changes already committed by the second manager.

## 13. Conditions for a transaction to actually cover database operations

Having a PlatformTransactionManager and @Transactional is not enough if the data operations do not participate in that transaction.

### 13.1. The repository must use the right resource

If the test transaction manager manages DataSource A while the repository writes to DataSource B, the write operation may occur outside the test transaction. In that case, the test rollback does not remove the data written to B.

Verify that the repository, EntityManagerFactory, and transaction manager are wired consistently.

### 13.2. Transaction propagation can create a separate transaction

A production method using Propagation.REQUIRES_NEW can suspend the current test transaction and run in a new transaction. The new transaction can commit independently; rolling back the outer test transaction cannot revert that committed data.

For methods using REQUIRES_NEW, design separate cleanup or verify across the appropriate transaction boundary.

### 13.3. Other threads do not automatically join the test transaction

Standard JDBC/JPA transactions are bound to the current thread. If a test invokes asynchronous code running on an executor or another thread, those operations typically do not participate in the test transaction of the thread running JUnit.

An async task can commit data even when the outer test transaction rolls back. Wait for the task to finish and clean up data outside the test transaction if needed.

### 13.4. Preemptive timeouts can lose transaction context

Some preemptive timeout assertions execute the test block on a separate thread. Because test transactions are normally bound to the test execution thread, code running on a new thread may not join that transaction. Database writes on the new thread can persist after the test rolls back.

With transactional tests, be cautious when using preemptive timeouts such as assertTimeoutPreemptively. If a time limit is needed, consider a timeout mechanism that does not shift execution to another thread or use controls suited to the application's transactions.

## 14. Flushing to observe persistence errors at the right time

JPA can defer SQL statements until flush or commit. Because a test-managed transaction typically rolls back after the method, some constraint errors may not surface if the test has not flushed.

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void rejectsDuplicateEmail() {
        repository.save(new Customer("a@example.test"));
        repository.flush();

        repository.save(new Customer("a@example.test"));

        assertThrows(
            DataIntegrityViolationException.class,
            repository::flush
        );
    }
}
~~~

This example assumes the database has a unique constraint on email and the repository supports flush. Calling flush causes SQL to be sent to the database within the current transaction so the constraint error appears right where the test checks for it.

Flushing is not synonymous with committing. The data remains inside the transaction and can still be rolled back after the test. This enables testing constraints without leaving data behind in the database.

## 15. When should a test not use @Transactional?

Not every integration test is a good fit for wrapping the test method in a transaction.

Consider omitting @Transactional when the goal is to:

- Verify that a service commits or rolls back its own transaction.
- Verify that data actually persists after the service ends its transaction.
- Test transaction propagation behavior such as REQUIRES_NEW.
- Test asynchronous work writing data on another thread.
- Test transaction boundaries across multiple datasources.
- Test callbacks or events published only after commit.

For example, wanting to verify that a service commits data:

~~~java
@SpringBootTest
class OrderCommitIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void serviceCommitsOrder() {
        Order created = orderService.createAndCommit(validCommand());

        Order loaded = orderRepository.findById(created.getId())
            .orElseThrow();

        assertEquals(created.getId(), loaded.getId());
    }
}
~~~

This example assumes the service manages its own transaction and completes the commit before returning. The test needs isolated data or cleanup to avoid leaving records across runs.

## 16. Common errors when PlatformTransactionManager or @Transactional is missing

### 16.1. @Transactional is present, but no PlatformTransactionManager exists

Spring Test cannot start a test-managed transaction. Check whether the context has an appropriate manager bean and whether the manager's configuration is imported into the test.

### 16.2. A transaction manager exists, but the test does not run in a transaction

The manager only provides transaction management capability. The test method needs @Transactional or an equivalent transaction mechanism for Spring Test to start a transaction.

### 16.3. Multiple managers exist, and none can be selected

If the context has multiple PlatformTransactionManager beans, specify transactionManager explicitly in @Transactional, or organize the default bean with an appropriate transactionManager name / @Primary.

### 16.4. The manager uses the wrong DataSource

Rollback succeeds, yet data still remains because the repository writes to a different datasource. Check the wiring of the repository and manager, especially when the application has multiple databases.

### 16.5. Thinking @Transactional on a test tests the service's transaction

A test-managed transaction can cause the service to join the transaction already started by the test. That is useful for data testing, but it does not prove the service creates and commits a transaction in a standalone call.

### 16.6. Using REQUIRES_NEW and expecting the outer rollback to delete the data

The separate transaction can commit independently. Verify the propagation and provide cleanup for data committed inside the new transaction.

### 16.7. Writing data on another thread

The test transaction does not automatically propagate to asynchronous threads. Wait for the work to finish and clean up data according to the actual transaction boundary.

### 16.8. Failing to flush before asserting constraints

JPA may defer SQL. Call flush at the point where the database error should be verified so the test does not miss a constraint violation.

### 16.9. Disabling default listeners

If you customize the @TestExecutionListeners list without keeping TransactionalTestExecutionListener, @Transactional may not be processed as expected. Merge with the default listeners or register the required listener.

## 17. Workflow for setting up a transactional test

When creating a test that uses transactions, you can follow this sequence:

1. Identify the resource under test: JDBC, JPA, or another transaction system.
2. Ensure the test context registers the right PlatformTransactionManager.
3. If there are multiple managers, specify the manager name in @Transactional.
4. Place @Transactional at the class level when most test methods need a transaction, or at the method level when only some tests need it.
5. Verify that the repository and manager use the same datasource or persistence unit.
6. Use the default rollback for ordinary data tests; use @Commit, @Rollback(false), or TestTransaction when an intentional commit is needed.
7. Call flush when SQL or constraint errors must be detected directly at an assertion.
8. Check boundaries such as REQUIRES_NEW, asynchronous threads, and multiple datasources.
9. Run the test individually and as part of the suite to confirm data does not leak between runs.

Minimal template:

~~~java
@SpringBootTest
@Transactional
class RepositoryIntegrationTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private CustomerRepository repository;

    @Test
    void usesSpringManagedTestTransaction() {
        assertNotNull(transactionManager);

        Customer customer = repository.save(
            new Customer("customer-10", "Kai")
        );
        repository.flush();

        assertTrue(repository.findById(customer.id()).isPresent());
    }
}
~~~

In this example, injecting the manager makes the test's dependency on the transaction infrastructure explicit; it is @Transactional and TransactionalTestExecutionListener that actually create the test-managed transaction. If the repository uses JPA, the injected manager must be the manager governing that repository's persistence unit.

## Conclusion

Standard Spring transactional tests require a PlatformTransactionManager in the ApplicationContext and @Transactional on the test class or method. Spring TestContext uses TransactionalTestExecutionListener to start the transaction before the test and roll back by default after the test. When multiple managers exist, select the right bean; when testing commits, propagation, multiple datasources, or asynchronous work, identify the true transaction boundary and choose the appropriate verification approach.
