# Selecting a transaction manager when there are multiple data sources

A Spring application can work with multiple databases or multiple data sources: a business database, an audit database, a reporting store, a legacy system, or a read-only datasource. When each data source has its own transaction boundary, the application typically has multiple `PlatformTransactionManager` beans. In that case, an `@Transactional` annotation without an explicit manager may select the wrong manager or fail because Spring cannot determine the appropriate manager.

In integration testing, selecting the right transaction manager also determines which data gets rolled back after the test. A test-managed transaction only governs resources belonging to the selected manager. If the test writes to a second datasource through another transaction manager, that data may still commit even though the test's transaction rolled back. Therefore, tests must explicitly specify the manager when there are multiple data sources and understand each source's transaction boundary.

## 1. `PlatformTransactionManager` and multiple datasources

Spring manages transactions through the `PlatformTransactionManager` abstraction. Each transaction manager coordinates transactions for a specific resource type or group of resources.

Common implementations:

| Transaction manager | Resource managed | Use case |
|---|---|---|
| `DataSourceTransactionManager` | A JDBC `DataSource` | Applications using JDBC or Spring JDBC |
| `JdbcTransactionManager` | A JDBC `DataSource` | JDBC transaction manager variant with more consistent exception translation in modern Spring Framework |
| `JpaTransactionManager` | A JPA `EntityManagerFactory` | Applications using Spring Data JPA/Hibernate |
| `JtaTransactionManager` | Transactions coordinated by JTA | When distributed transactions across appropriately configured XA resources are needed |

An application with two independent datasources typically declares two corresponding transaction managers:

```text
OrdersRepository  ---> ordersDataSource  ---> ordersTransactionManager

AuditRepository   ---> auditDataSource   ---> auditTransactionManager
```

Each manager knows how to start, commit, and roll back transactions for the resource it manages. Having multiple managers does not automatically create a single shared transaction spanning all datasources.

### 1.1. Why select the manager explicitly?

When there is only one `PlatformTransactionManager` bean, Spring can usually use that single manager as the default. When multiple managers exist, a decision must be made about which manager will handle an `@Transactional` method that does not specify a name.

For example, a service has two methods:

```java
@Service
class OrderService {
    @Transactional
    public void placeOrder(CreateOrderCommand command) {
        // Write the order to the business database.
    }
}

@Service
class AuditService {
    @Transactional
    public void recordOrderCreated(String orderId) {
        // Write the audit entry to a separate database.
    }
}
```

If the context has two transaction managers and no clear default convention, an unqualified annotation may fail to resolve as desired. Even if Spring can pick a default manager, `AuditService` still needs the manager tied to the audit datasource. The clearest approach is to specify the manager on methods that have distinct transaction boundaries.

## 2. Declaring multiple transaction managers

With JDBC, each transaction manager must receive its own datasource. Use bean names and `@Qualifier` to avoid injecting the wrong bean when multiple beans share the same type.

```java
@Configuration
class MultiDataSourceConfiguration {
    @Bean
    @ConfigurationProperties("app.datasource.orders")
    DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.orders.hikari")
    HikariDataSource ordersDataSource(
            @Qualifier("ordersDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.audit")
    DataSourceProperties auditDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.audit.hikari")
    HikariDataSource auditDataSource(
            @Qualifier("auditDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean(name = {"transactionManager", "ordersTransactionManager"})
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("auditTransactionManager")
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

The example names the orders manager both `transactionManager` and `ordersTransactionManager`. Both names are aliases for the same bean, so the application has a default manager with the conventional name while still having a specific name for annotations. The audit manager has its own distinct name.

Properties can be configured in the application configuration file:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: app
      password: secret
      driver-class-name: org.postgresql.Driver
    audit:
      url: jdbc:postgresql://localhost:5432/audit
      username: app
      password: secret
      driver-class-name: org.postgresql.Driver
```

This is an illustrative configuration example. In a real project, datasources can be created from `DataSourceBuilder`, `DataSourceProperties`, custom Hikari configurations, or Spring Boot's mechanisms. The key point is that each transaction manager must receive the right datasource, and beans needing a datasource injected must use explicit qualifiers.

### 2.1. Naming managers consistently

Bean names are part of the configuration contract. Choose names that reflect the resource or bounded context:

- `ordersTransactionManager` for transactions on the orders database.
- `auditTransactionManager` for transactions on the audit database.
- `reportingTransactionManager` for the reporting database.

Avoid generic names such as `manager1` or `secondaryTx`. Clear names help readers immediately know which data source `@Transactional` governs and help tests specify the right manager.

If you want one manager to act as the default where no qualifier is specified, you can name that bean `transactionManager`, mark it `@Primary` when needed to resolve injection by type, or configure the default manager via `TransactionManagementConfigurer`. Even with a default manager, services belonging to other datasources should still specify their manager explicitly.

## 3. Selecting a transaction manager with `@Transactional`

Spring's `@Transactional` has a `transactionManager` attribute to select the bean managing the transaction. The `value` attribute is an alias for `transactionManager`, so the following two forms are equivalent:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder() {
    // Transaction on the orders database.
}
```

```java
@Transactional("ordersTransactionManager")
public void placeOrder() {
    // Transaction on the orders database.
}
```

If a bean is declared with `@Bean("ordersTransactionManager")`, that name can be used as the qualifier. This applies to service transactions and is also how you select the manager for a test-managed transaction.

### 3.1. Specifying the manager at the method level

When a service has operations across multiple datasources, placing the manager directly on the method expresses the transaction boundary:

```java
@Service
class OrderService {
    private final OrderRepository orders;

    OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Order create(CreateOrderCommand command) {
        return orders.save(new Order(command.customerId()));
    }
}

@Service
class AuditService {
    private final AuditRepository audits;

    AuditService(AuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public void record(String orderId) {
        audits.save(new AuditEntry(orderId, "ORDER_CREATED"));
    }
}
```

Explicitly specifying the manager makes each service's intent easier to read and avoids relying on the context's default manager.

### 3.2. Manager at the class level and overriding at the method level

You can place a shared manager on the class:

```java
@Service
@Transactional(transactionManager = "ordersTransactionManager")
class OrderService {
    public void create() {
        // Uses ordersTransactionManager.
    }

    public void cancel() {
        // Also uses ordersTransactionManager.
    }
}
```

If a method needs a different manager, you can declare the annotation on that method:

```java
@Transactional(transactionManager = "auditTransactionManager")
public void recordAudit() {
    // Uses auditTransactionManager.
}
```

Method-level transaction metadata overrides class-level configuration for that method. Avoid mixing multiple datasources inside the same service if doing so makes transaction boundaries hard to follow; splitting services by resource usually keeps ownership clearer.

## 4. Selecting a default manager for annotation-driven transactions

If an application has multiple managers yet many services still use unqualified `@Transactional`, a clear default manager must be configured.

### 4.1. A bean named `transactionManager`

A common convention is naming the default manager `transactionManager`. Annotations that do not specify a manager can use the bean by this conventional name in Spring's transaction mechanism.

In the multi-datasource example above, `ordersTransactionManager` is declared with two names:

```java
@Bean(name = {"transactionManager", "ordersTransactionManager"})
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

Places that need the default manager can continue using `@Transactional`, while the audit service uses its specific name.

### 4.2. Using `@Primary`

`@Primary` marks the preferred bean when Spring must resolve a dependency by type and multiple candidates exist. Example:

```java
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
```

`@Primary` is useful for dependency injection by type and can help unqualified manager resolution pick a preferred candidate. However, the default bean name and the application's transaction configuration mechanism must be clearly understood. When multiple managers exist, using qualifiers on important transaction boundaries remains the most readable and least ambiguous approach.

### 4.3. Using `TransactionManagementConfigurer`

If you want to explicitly specify the default manager for annotation-driven transactions, you can implement `TransactionManagementConfigurer`:

```java
@Configuration
@EnableTransactionManagement
class DefaultTransactionConfiguration
        implements TransactionManagementConfigurer {

    private final PlatformTransactionManager defaultManager;

    DefaultTransactionConfiguration(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager defaultManager) {
        this.defaultManager = defaultManager;
    }

    @Override
    public PlatformTransactionManager annotationDrivenTransactionManager() {
        return defaultManager;
    }
}
```

Here, `ordersTransactionManager` is chosen as the default manager for annotation-driven transactions. Methods requiring the audit manager still specify its qualifier in `@Transactional`.

`TransactionManagementConfigurer` belongs to Spring's transaction configuration mechanism. When using Spring Boot, auto-configuration may already enable transaction management; place this configuration appropriately and avoid registering competing default configurations.

## 5. Multiple JPA datasources require multiple `EntityManagerFactory` beans

If an application uses JPA with two independent datasources, it typically needs an `EntityManagerFactory` and a `JpaTransactionManager` for each datasource. Simply creating two `DataSource` beans and two `JpaTransactionManager` beans is not enough if repository packages are not bound to the right factory and manager.

Example configuring two repository groups:

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.orders.repository",
        entityManagerFactoryRef = "ordersEntityManagerFactory",
        transactionManagerRef = "ordersTransactionManager")
class OrdersJpaConfiguration {
    @Bean
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return builder
                .dataSource(dataSource)
                .packages(Order.class)
                .persistenceUnit("orders")
                .build();
    }

    @Bean
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

The audit repository has a corresponding configuration:

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.audit.repository",
        entityManagerFactoryRef = "auditEntityManagerFactory",
        transactionManagerRef = "auditTransactionManager")
class AuditJpaConfiguration {
    @Bean
    LocalContainerEntityManagerFactoryBean auditEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("auditDataSource") DataSource dataSource) {
        return builder
                .dataSource(dataSource)
                .packages(AuditEntry.class)
                .persistenceUnit("audit")
                .build();
    }

    @Bean
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Package names, entities, and builder configuration depend on the application. The crux is that each `@EnableJpaRepositories` points to the right `entityManagerFactoryRef` and `transactionManagerRef`. If a repository package is scanned by both configurations or wired to the wrong manager, tests may hit the wrong database or fail during context initialization.

### 5.1. `@Primary` for JPA infrastructure

If the application has multiple `DataSource`, `EntityManagerFactory`, or `PlatformTransactionManager` beans, some auto-configurations or injection points need to know the default bean. You can use `@Primary` for the main group, while still putting explicit qualifiers on the secondary configurations.

Do not mark every bean as primary. Each type should have at most one default choice when genuinely needed. For repositories belonging to a secondary datasource, `entityManagerFactoryRef` and `transactionManagerRef` must explicitly reference the corresponding secondary beans.

## 6. Transaction managers in test-managed transactions

The Spring TestContext Framework includes `TransactionalTestExecutionListener` to manage transactions for test methods or test classes annotated with `@Transactional`. A test transaction typically starts before the test method runs and rolls back after the test completes by default.

When multiple managers exist, select the manager for a test using the `transactionManager` attribute or `value` alias of `@Transactional`:

```java
@SpringBootTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryIntegrationTest {
    @Autowired
    private OrderRepository orders;

    @Test
    void createsOrderInsideOrdersTransaction() {
        orders.save(new Order("customer-42"));

        assertThat(orders.count()).isEqualTo(1);
    }
}
```

The test transaction is opened using `ordersTransactionManager`. When the test ends, Spring rolls back this transaction by default, so the test's data is reverted if the operations participate in the same transaction.

For the audit datasource:

```java
@SpringBootTest
@Transactional("auditTransactionManager")
class AuditRepositoryIntegrationTest {
    @Autowired
    private AuditRepository audits;

    @Test
    void storesAuditEntryInsideAuditTransaction() {
        audits.save(new AuditEntry("order-42", "CREATED"));

        assertThat(audits.count()).isEqualTo(1);
    }
}
```

Here, the test transaction is managed by the audit manager. If a test fails to specify a manager in a context with multiple managers and Spring cannot pick a default, the test may fail when starting the transaction.

### 6.1. Class-level and method-level annotations

You can place `@Transactional` at the class level so all test methods use the same manager:

```java
@SpringBootTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrderServiceIntegrationTest {
    @Test
    void createsOrder() {
    }

    @Test
    void cancelsOrder() {
    }
}
```

A method can override the class metadata if it needs a different manager or transaction attribute:

```java
@Test
@Transactional(transactionManager = "auditTransactionManager")
void recordsAuditEntry() {
    // Test-managed transaction uses the audit manager.
}
```

Avoid placing a shared class-level manager if multiple methods in the class test independent datasources. In that case, method-level annotations or splitting test classes by datasource keeps rollback boundaries clearer.

## 7. Test transactions only roll back resources of the selected manager

This is the most critical point when testing multiple datasources. A test transaction using `ordersTransactionManager` only manages transactions on the orders datasource. If, within the same test, code writes to the audit datasource through `auditTransactionManager`, the audit transaction is a different transaction.

Example:

```java
@Service
class OrderWorkflowService {
    private final OrderRepository orders;
    private final AuditService auditService;

    OrderWorkflowService(OrderRepository orders, AuditService auditService) {
        this.orders = orders;
        this.auditService = auditService;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Order createOrder(String customerId) {
        Order order = orders.save(new Order(customerId));
        auditService.record(order.id());
        return order;
    }
}

@Service
class AuditService {
    private final AuditRepository audits;

    AuditService(AuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public void record(String orderId) {
        audits.save(new AuditEntry(orderId, "ORDER_CREATED"));
    }
}
```

If the test is annotated with `@Transactional("ordersTransactionManager")`, creating the order can join the orders test transaction. The call to `AuditService.record()` uses a different manager, so it opens its own audit transaction and can commit independently. When the orders test transaction rolls back, the audit record may still remain.

This is not a bug in Spring. Two local transaction managers do not automatically coordinate commit/rollback like a distributed transaction. Tests must accurately anticipate which data will be rolled back and clean up data committed to other sources.

### 7.1. Do not assume test `@Transactional` covers every datasource

An annotation on a test method does not automatically cover every manager in the context. It selects one manager. Repositories belonging to other datasources may use separate transactions, or run without a corresponding transaction depending on configuration.

When testing a multi-datasource workflow, clearly identify:

- Which writes use the orders manager?
- Which writes use the audit manager?
- Does the service's transaction join the test transaction or open a separate transaction?
- Which data rolls back with the test and which data commits independently?
- How should the secondary datasource be cleaned up?

If you need a single atomic transaction spanning multiple XA datasources, you must configure a JTA transaction manager and appropriate XA-capable resources. Two independent `DataSourceTransactionManager` or `JpaTransactionManager` instances do not provide atomic commits across datasources.

## 8. Propagation when a test calls a service with a different manager

Propagation decides how a transactional method joins or creates a transaction. `REQUIRED` is the default: the method joins an existing transaction of the same transaction manager or creates a new one if none exists.

The key point is that the existing transaction must belong to the manager the method is using. An orders transaction does not automatically become an existing transaction for the audit manager.

| Test transaction | Service transaction | Typical behavior |
|---|---|---|
| `ordersTransactionManager` | `ordersTransactionManager`, `REQUIRED` | Service joins the test transaction |
| `ordersTransactionManager` | `auditTransactionManager`, `REQUIRED` | Audit manager opens a separate transaction if needed |
| `auditTransactionManager` | `auditTransactionManager`, `REQUIRED` | Audit service joins the test transaction |
| No test transaction | `ordersTransactionManager`, `REQUIRED` | Service opens its own orders transaction |
| `ordersTransactionManager` | `ordersTransactionManager`, `REQUIRES_NEW` | Service suspends the test transaction and opens a new orders transaction |

`REQUIRES_NEW` on the same manager can commit independently of the outer test transaction. That data can remain after the test transaction rolls back. When using this propagation, the test must clean up or intentionally verify commit behavior.

`NESTED`, `SUPPORTS`, `NOT_SUPPORTED`, `MANDATORY`, and `NEVER` also have their own semantics. Do not use propagation to fix manager selection errors; ensure the right manager is specified first.

## 9. Verifying rollback and commit in tests

By default, a test-managed transaction rolls back after the test. This can be controlled with `@Rollback` or `@Commit`:

```java
@Test
@Transactional("ordersTransactionManager")
@Rollback
void rollsBackOrderAfterTest() {
    orders.save(new Order("customer-42"));
}
```

`@Rollback` defaults to `true`. You can use `@Commit` or `@Rollback(false)` to commit the test transaction when commit behavior needs to be verified:

```java
@Test
@Transactional("ordersTransactionManager")
@Commit
void commitsOrderAfterTest() {
    orders.save(new Order("customer-42"));
}
```

Tests that commit leave data in the database. Use uniquely identified data and explicit cleanup so test runs do not interfere with each other.

### 9.1. Inspecting data after the transaction ends

`@BeforeTransaction` and `@AfterTransaction` let you run callbacks before the test transaction starts or after it finishes. They are useful when you need to inspect committed or rolled-back state from outside the test transaction:

```java
@SpringBootTest
@Transactional("ordersTransactionManager")
class OrderRollbackTest {
    @Autowired
    private OrderRepository orders;

    private String orderId;

    @Test
    void rollsBackCreatedOrder() {
        Order order = orders.save(new Order("customer-42"));
        orderId = order.id();

        assertThat(orders.findById(orderId)).isPresent();
    }

    @AfterTransaction
    void verifiesOrderWasRolledBack() {
        assertThat(orders.findById(orderId)).isEmpty();
    }
}
```

This example assumes the repository reads data through a new transaction or appropriate mechanism after the test transaction has rolled back. If the repository method opens its own read-only transaction, the callback can read the committed state from the database. With JPA, pay attention to the persistence context and cache; do not use a managed entity from an ended transaction as proof of rolled-back data.

`@BeforeTransaction` can create baseline data before the test transaction begins. `@AfterTransaction` is suitable for verifying data after commit/rollback or cleaning up data committed by another manager.

### 9.2. `TestTransaction`

Spring Test provides `TestTransaction` to control the test-managed transaction while the test is running:

```java
@Test
@Transactional("ordersTransactionManager")
void commitsCurrentTestTransactionExplicitly() {
    orders.save(new Order("customer-42"));

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertThat(TestTransaction.isActive()).isFalse();
}
```

`TestTransaction` operates on the current test-managed transaction, meaning the transaction selected via the test's annotation. It does not accept a manager name on each call. If a test needs a different transaction, use `TransactionTemplate` or transaction APIs with the corresponding manager.

After `TestTransaction.end()`, a new test transaction can be started via `TestTransaction.start()` if the test configuration permits and you need to continue testing in a new transaction. Clearly distinguish an ended transaction from a persistence context or entity reference still held in a test field.

## 10. Using `TransactionTemplate` when explicit manager control is needed

When a test needs to create transactions for multiple managers or control commit/rollback per resource, `TransactionTemplate` is an explicit choice:

```java
@SpringBootTest
class MultiDatabaseTransactionTest {
    @Autowired
    @Qualifier("ordersTransactionManager")
    private PlatformTransactionManager ordersManager;

    @Autowired
    @Qualifier("auditTransactionManager")
    private PlatformTransactionManager auditManager;

    @Autowired
    private OrderRepository orders;

    @Autowired
    private AuditRepository audits;

    @Test
    void controlsEachLocalTransactionSeparately() {
        TransactionTemplate ordersTx = new TransactionTemplate(ordersManager);
        TransactionTemplate auditTx = new TransactionTemplate(auditManager);

        ordersTx.executeWithoutResult(status -> {
            orders.save(new Order("customer-42"));
            status.setRollbackOnly();
        });

        auditTx.executeWithoutResult(status -> {
            audits.save(new AuditEntry("order-42", "TEST_EVENT"));
            status.setRollbackOnly();
        });

        // Each template rolled back the transaction belonging to its respective manager.
    }
}
```

This example creates two local transactions and marks them rollback-only independently. This is not a shared atomic transaction; if one transaction commits while the other fails, data may end up in an inconsistent state. `TransactionTemplate` is suited for tests controlling individual managers, not as a replacement for JTA when distributed transactions are needed.

If you only want to verify that a test-managed transaction picks the right manager, using `@Transactional("...TransactionManager")` is simpler. Only switch to `TransactionTemplate` when the test needs to control multiple transaction boundaries or proactively commit/roll back.

## 11. `@DataJpaTest` with multiple datasources

`@DataJpaTest` focuses on a single persistence setup by default and usually auto-configures test transactions. When an application has multiple `EntityManagerFactory` beans and transaction managers, the test slice needs to know which repository package is bound to which manager.

You can use `@Import` to load additional JPA configuration and specify the manager on the test:

```java
@DataJpaTest
@Import(MultiJpaTestConfiguration.class)
@Transactional("auditTransactionManager")
class AuditRepositoryTest {
    @Autowired
    private AuditRepository audits;
}
```

Depending on Spring Boot configuration and how datasources are declared, the test slice may need `@AutoConfigureTestDatabase(replace = Replace.NONE)` to keep configured datasources instead of replacing them with an embedded database. With multiple datasources, identify which datasource is primary and configure repositories/EntityManagerFactory separately for the remaining datasource.

Do not assume `@DataJpaTest` automatically creates test transactions for every `JpaTransactionManager`. Select the specific manager via the test annotation and verify the repository uses the right `EntityManagerFactory`.

If the goal is to test multi-datasource configuration, multiple entity managers, and full wiring, `@SpringBootTest` may be more appropriate than a slice test. If testing only repositories belonging to a single persistence unit, keep the test context narrow with specific imported configuration.

## 12. Testing transactions with JDBC and `JdbcTemplate`

When using multiple JDBC datasources, each `JdbcTemplate` must be created from the right datasource:

```java
@Configuration
class JdbcTemplateConfiguration {
    @Bean
    JdbcTemplate ordersJdbcTemplate(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    JdbcTemplate auditJdbcTemplate(
            @Qualifier("auditDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

When a test uses `@Transactional("ordersTransactionManager")`, JDBC operations through `ordersJdbcTemplate` can join the test transaction if they use the same datasource and Spring's transaction-aware connection lookup. Operations through `auditJdbcTemplate` do not automatically join the orders transaction.

To verify which datasource a manager is actually bound to, perform an insert using the corresponding template and read back after rollback in another transaction. Do not rely solely on bean names or manager counts; persistence and rollback behavior on the target database is more direct proof.

## 13. Transactions across multiple datasources and JTA

Two independent local transaction managers do not provide cross-datasource atomicity. For example, a service commits an order to database A and then writes an audit to database B. If database B fails after A has already committed, the system may have the order without the audit record.

If business requirements genuinely demand a single atomic transaction across multiple XA resources, a JTA transaction coordinator and XA-capable datasources/drivers are required. `JtaTransactionManager` participates in coordinating distributed transactions; each resource must be registered with the appropriate coordinator.

Not every application needs XA. Many systems use the outbox pattern, sagas, or eventual consistency to coordinate data between a database and a message broker. When testing, verify the application's actual mechanism:

- With XA/JTA: test global commit and rollback using an XA-capable environment.
- With outbox: verify the business record and outbox record commit in the same transaction of the respective database, then test the publisher processing the outbox.
- With saga: test successful steps and compensation when a later step fails.
- With two independent local transactions: explicitly verify that partial outcomes can exist and clean up test data per source.

A test transaction on a single manager does not prove atomicity of a multi-datasource workflow. Tests must run through the transaction coordinator or coordination mechanism used in production.

## 14. Diagnosing transaction manager selection errors

### 14.1. `NoUniqueBeanDefinitionException`

This error usually occurs when Spring needs a `PlatformTransactionManager` but multiple beans of the same type exist without a clear default choice.

How to resolve:

- Specify `@Transactional(transactionManager = "...TransactionManager")` on the service or test.
- Name the default bean `transactionManager` if there is a primary manager.
- Use `@Primary` for the default choice when appropriate for injection by type.
- Use `TransactionManagementConfigurer` when wanting to configure a default manager for annotation-driven transactions.

Do not add `@Primary` arbitrarily if services belonging to other datasources need their own managers. Qualifiers on transaction boundaries usually express intent more accurately.

### 14.2. Bean not found by qualifier

If the error states that a manager with the specified name or qualifier cannot be found, check bean names in `@Bean`, `@Component`, or auto-configuration. The name in `@Transactional` must match a registered bean name or qualifier.

For example, `@Transactional("auditTxManager")` will not automatically match a bean named `auditTransactionManager` without a corresponding alias or qualifier.

### 14.3. Repository uses the wrong datasource

If the test transaction rolls back yet data still persists, the repository may be using a different manager or writes may be running in a separate transaction. Check `entityManagerFactoryRef`, `transactionManagerRef`, datasource qualifiers, and the manager on the service.

With JPA, check that repository packages are bound to the right persistence unit. With JDBC, check which datasource each `JdbcTemplate` is created from.

### 14.4. Test rolls back one database while the other still has data

This is usually the expected behavior when two sources use independent managers. Identify the manager of each operation and clean up the source that committed. Do not increase rollback levels or add `@DirtiesContext` expecting it to revert another manager's transaction.

### 14.5. Service does not join the test transaction

Check whether the service is invoked through a Spring proxy. Self-invocation within the same bean can bypass the transactional proxy. Check the manager on the method, propagation, and whether the test is using the same manager.

### 14.6. Test context fails to initialize due to multi-source JPA configuration

Check that each `@EnableJpaRepositories` has the right packages, `entityManagerFactoryRef`, and `transactionManagerRef`. Check for non-conflicting bean names, sensible `@Primary` usage, and that each factory uses the right datasource/entity packages.

## 15. Workflow for selecting a manager in an integration test

When a test involves multiple datasources, determine step by step:

1. Which repository or `JdbcTemplate` is the test reading from / writing to?
2. Which datasource and `EntityManagerFactory` is that repository bound to?
3. Which transaction manager coordinates that resource?
4. Does the test need transaction rollback or commit to verify post-commit behavior?
5. Do invoked services use a manager with the same name or open transactions on a different manager?
6. Are there any side effects committed outside the test transaction?
7. How should data in secondary datasources or external resources be cleaned up?
8. If the workflow requires atomicity across multiple datasources, does production use JTA/XA, outbox, or saga?

Then explicitly declare the manager on the test's `@Transactional`:

```java
@SpringBootTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrderWorkflowIntegrationTest {
    // The test transaction is managed by the orders manager.
}
```

If a test needs a different manager, use a separate test class or method-level annotation to make the boundary clear. Avoid grouping scenarios requiring different managers into one class and relying on a default manager.

## 16. Comprehensive example: verifying rollback on the right data source

Suppose an application has two repositories: `OrderRepository` using the orders database and `AuditRepository` using the audit database. Each repository has its own transaction manager.

```java
@SpringBootTest
class MultiDatabaseIntegrationTest {
    @Autowired
    private OrderRepository orders;

    @Autowired
    private AuditRepository audits;

    @Test
    @Transactional("ordersTransactionManager")
    void rollsBackOrdersDatabaseTransaction() {
        Order order = orders.save(new Order("customer-42"));

        assertThat(orders.findById(order.id())).isPresent();
    }

    @Test
    @Transactional("auditTransactionManager")
    void rollsBackAuditDatabaseTransaction() {
        AuditEntry entry = audits.save(
                new AuditEntry("order-42", "TEST_EVENT"));

        assertThat(audits.findById(entry.id())).isPresent();
    }
}
```

Each method selects the corresponding manager. Spring rolls back that manager's transaction after the test. If the test needs to confirm data vanished after rollback, it can use `@AfterTransaction` or a new transaction to re-read the data.

For workflows writing to both datasources, write dedicated tests to prove the real boundary. If the audit manager commits independently, the test must delete the audit record after checking. If production uses outbox or JTA, tests must run through that mechanism and verify final state according to the contract.

## 17. Key principles to remember

- Each `PlatformTransactionManager` manages transactions for the resource or group of resources configured with it.
- Name managers clearly and use `@Qualifier` when injecting datasources or managers of the same type.
- `@Transactional` can select a manager via `transactionManager` or its alias `value`.
- When multiple managers exist, define the default manager using bean name `transactionManager`, an appropriate `@Primary`, or `TransactionManagementConfigurer`.
- With multiple JPA datasources, bind the right `EntityManagerFactory` and `transactionManager` to each repository package.
- Test-managed transactions use the manager selected on the test's `@Transactional` and roll back after the method by default.
- Rolling back one manager only applies to transactions/resources governed by that manager; other datasources may have committed independently.
- `REQUIRED` only joins an existing transaction of the same manager; transactions of other managers are not automatically shared.
- Use `TransactionTemplate` when needing separate control over multiple transaction managers; use JTA/XA if business logic requires distributed atomic transactions and infrastructure supports it.
- Verify data after the transaction using callbacks or a new transaction, and separately clean up sources that committed.

When there are multiple data sources, selecting the transaction manager is part of the testing contract. Explicitly specifying the manager on tests and services clarifies exactly which resource is committed or rolled back, prevents test data from leaking across runs, and makes the consistency limits of multi-database workflows explicit.
