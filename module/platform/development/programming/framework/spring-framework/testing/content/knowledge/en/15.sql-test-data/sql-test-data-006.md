# Selecting DataSource and Transaction Manager for Scripts

Spring TestContext Framework supports running SQL scripts before or after test methods via **@Sql**. This mechanism is commonly used to create initial data, prepare state for repository tests, or clean up data after testing. For a script to run against the right database and within the right transaction boundary, Spring needs to know which **DataSource** provides the JDBC connection and which **PlatformTransactionManager** manages the transaction for the script.

In a simple application with only one database, Spring can usually infer these two beans automatically. However, when the ApplicationContext has multiple DataSources or multiple transaction managers, inference can become ambiguous or select the wrong database. In that situation, **@SqlConfig** lets you explicitly specify the beans to use.

This lesson explains the roles of DataSource and transaction manager, how to configure them for **@Sql**, how to handle multiple databases, the difference between **INFERRED** and **ISOLATED** transaction modes, and how to choose appropriately for setup and cleanup scripts.

## 1. Which DataSource does @Sql use to execute scripts?

**@Sql** instructs Spring TestContext to execute one or more SQL statements for a test class or test method. Example:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Sql("/sql/orders-before-test.sql")
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsPreparedOrder() {
        assertTrue(repository.existsById("order-188"));
    }
}
~~~

When processing the annotation, Spring must execute the script over JDBC. **DataSource** is the component providing database connections. The script executes using a connection obtained from the selected DataSource in the ApplicationContext.

Example file `orders-before-test.sql`:

~~~sql
INSERT INTO customers (id, name)
VALUES ('customer-test-18', 'Test Customer');

INSERT INTO orders (id, customer_id, status)
VALUES ('order-test-188', 'customer-test-18', 'PENDING');
~~~

The DataSource determines which database those statements affect. If an application has an orders database and a billing database, picking the wrong DataSource can cause the script to fail due to missing tables or write data to a database outside the test scenario.

Therefore, when multiple DataSources exist, specify the bean name instead of relying on automatic inference.

## 2. What is the transaction manager responsible for?

**PlatformTransactionManager** manages transactions for a resource or a group of resources. For JDBC, the common implementation is **DataSourceTransactionManager**. For JPA, **JpaTransactionManager** is commonly used.

DataSource and transaction manager have distinct roles:

- DataSource provides JDBC connections for running SQL.
- Transaction manager starts, commits, rolls back, or joins transactions.
- @SqlConfig links the script to the appropriate DataSource and transaction manager.
- @Transactional on the test class or method selects the transaction manager for the test-managed transaction.

JDBC configuration example:

~~~java
@Configuration
class OrderDatabaseTestConfig {

    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl("jdbc:postgresql://localhost:5432/orders_test");
        dataSource.setUsername("orders_test_user");
        dataSource.setPassword("test-only-password");
        return dataSource;
    }

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

This example illustrates wiring. In real projects, connection details should be placed in appropriate property sources; real credentials should not be hard-coded in test configuration or committed to the repository.

With JPA, the transaction manager is typically tied to the corresponding EntityManagerFactory:

~~~java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Do not pair a DataSource of one database with a transaction manager of another database. If a script runs on DataSource A while the transaction manager manages DataSource B, the script may fail to join the transaction that the test rolls back. As a result, data may be committed or left behind unexpectedly.

## 3. Specifying DataSource with @SqlConfig

**@SqlConfig** has a **dataSource** attribute to select the DataSource bean by name in the ApplicationContext.

Example:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(dataSource = "ordersDataSource")
)
class OrderRepositoryTest {
}
~~~

In this example, Spring uses the bean named `ordersDataSource` to obtain a connection and run the script.

Multiple scripts can be configured in a single annotation:

~~~java
@Sql(
    scripts = {
        "/sql/orders-schema.sql",
        "/sql/orders-before-test.sql"
    },
    config = @SqlConfig(dataSource = "ordersDataSource")
)
~~~

The order of resources in the list is preserved during execution. This is useful when the first script creates schemas or tables and the next script inserts fixture data.

### When there is only one DataSource

If the context has only one suitable DataSource bean, Spring can usually infer that DataSource when `dataSource` is omitted. Still, explicit declaration is beneficial when test configuration is shared with other modules or may evolve into a multi-database context.

When multiple candidates exist, use the bean name in @SqlConfig. Do not rely on bean declaration order or assume the first-created bean will always be chosen.

## 4. Specifying transaction manager with @SqlConfig

The **transactionManager** attribute of **@SqlConfig** selects the PlatformTransactionManager bean used to manage transactions when running scripts.

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
class OrderRepositoryTest {
}
~~~

Specifying both beans clarifies that the script uses the orders database's DataSource and the transaction manager managing that database.

If the test class is also annotated with @Transactional, select the same transaction manager:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Transactional("ordersTransactionManager")
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
class OrderRepositoryTransactionalTest {
}
~~~

This declaration ensures the test-managed transaction and the SQL script use the same transaction manager. When transaction mode is INFERRED, the script can join the active transaction and fixture data rolls back with the test.

In modern Spring Framework, you can use the `transactionManager` attribute of @Transactional; the shorthand string value form above is commonly used to specify the bean name. If the application has multiple managers, do not skip checking which manager manages the repository under test.

## 5. DataSource and transaction manager inference mechanism

When `dataSource` or `transactionManager` is not declared, Spring TestContext attempts to locate suitable beans in the ApplicationContext. Inference is convenient for simple configurations, but can become ambiguous when an application has multiple databases.

Selection rules may consider bean name, bean type, qualifiers, and primary status via Spring TestContext's dependency lookup mechanism. Therefore:

- A single DataSource is usually inferred easily.
- A single transaction manager is usually inferred easily.
- If multiple beans of the same type exist, Spring needs an unambiguous candidate or identifying information.
- If no suitable bean can be determined, script execution may fail with a dependency resolution error or SQL execution initialization error.

Default bean names such as `dataSource` or `transactionManager` frequently appear in Spring applications, but do not rely on that convention when the context has multiple candidates.

**Practical rule:** if a test has more than one DataSource or transaction manager, specify bean names in @SqlConfig. Explicit configuration shows readers which database the script touches and which transaction protects it.

## 6. Applications with multiple DataSources

An application may split data by module or business domain, for example:

- ordersDataSource: orders and customers.
- billingDataSource: invoices and payments.
- reportingDataSource: reporting data.

Each DataSource can have its own transaction manager. When a test needs to prepare data for one database, specify the exact pair of beans.

Two-database configuration example:

~~~java
@Configuration
class MultiDatabaseTestConfig {

    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        return createTestDataSource("jdbc:postgresql://localhost:5432/orders_test");
    }

    @Bean("billingDataSource")
    DataSource billingDataSource() {
        return createTestDataSource("jdbc:postgresql://localhost:5432/billing_test");
    }

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("billingTransactionManager")
    PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    private DataSource createTestDataSource(String url) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(url);
        dataSource.setUsername("test_user");
        dataSource.setPassword("test_password");
        return dataSource;
    }
}
~~~

The example uses the same helper to keep configuration concise; URLs and credentials are for illustration only. In real projects, load them from separate properties or secret sources.

Script for the orders database:

~~~java
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
~~~

Script for the billing database:

~~~java
@Sql(
    scripts = "/sql/billing-before-test.sql",
    config = @SqlConfig(
        dataSource = "billingDataSource",
        transactionManager = "billingTransactionManager"
    )
)
~~~

If a test method needs to run scripts on both databases, multiple @Sql annotations or @SqlGroup can be declared. Each annotation must specify the corresponding DataSource and transaction manager.

Note that two local transaction managers do not automatically form a distributed transaction. If a test requires atomicity across multiple databases, an appropriate transaction architecture is needed, such as JTA/XA or an application-level consistency mechanism. Running two scripts with two separate managers does not guarantee that both databases commit or roll back together.

## 7. Running scripts on multiple DataSources in the same test

Spring allows declaring multiple @Sql annotations on the same class or method. Each script can use its own configuration:

~~~java
@SpringJUnitConfig(MultiDatabaseTestConfig.class)
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
@Sql(
    scripts = "/sql/billing-before-test.sql",
    config = @SqlConfig(
        dataSource = "billingDataSource",
        transactionManager = "billingTransactionManager"
    )
)
class OrderBillingIntegrationTest {
}
~~~

When using multiple @Sql annotations, remember that each script executes under its own transaction mode and transaction manager. If the first script succeeds but the second script fails, changes in the first database may already be committed depending on the transaction configuration.

If a consistent initial state across multiple databases is required, design setup and cleanup to be safely repeatable, or use an integration-suite-level test data management strategy. Do not assume Spring automatically creates a shared transaction across multiple DataSources simply because scripts are placed on the same test class.

## 8. What is transactionMode INFERRED?

**INFERRED** is the default transaction mode of @SqlConfig. Spring infers how to execute the script based on the current transaction and available transaction managers.

In principle:

- If a test-managed transaction is active and the script uses the same transaction manager, the script can join that transaction.
- If no transaction is active but a suitable transaction manager exists, Spring can create a transaction for executing the script.
- If no suitable transaction manager exists, the script can run directly against the DataSource without a Spring-managed transaction.

Therefore, INFERRED usually fits setup scripts running inside a transactional test. The script runs inside the test's transaction, and fixture data rolls back with the test by default.

Example:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Transactional("ordersTransactionManager")
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.INFERRED
    )
)
class OrderRepositoryTest {
}
~~~

Here, the script uses the same transaction manager as the test. Data inserted before the test method is visible within the transaction and rolled back after the test finishes.

The `transactionMode` attribute can be omitted because INFERRED is the default. Writing it explicitly helps document intent or contrast with another script using ISOLATED.

## 9. What is transactionMode ISOLATED?

**ISOLATED** tells Spring to run the script in an independent transaction, separate from the current transaction. The independent transaction commits immediately after the script completes successfully.

~~~java
@Sql(
    scripts = "/sql/orders-baseline.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
~~~

This mode requires a suitable transaction manager. Spring suspends the current transaction if one exists, opens an independent transaction to run the script, and then commits that transaction.

Suitable situations:

- Creating baseline data that must exist outside the test-managed transaction.
- Preparing committed data so another transaction can read it.
- Running cleanup that must commit even when the test's transaction rolls back.
- Creating initial state for a processing flow running on another thread or transaction.

### Impact of ISOLATED on default rollback

Suppose the test method has @Transactional and the setup script uses ISOLATED:

~~~text
@BeforeTestMethod
    |
    v
Test transaction begins
    |
    v
@Sql with ISOLATED
    |
    +--> Suspend test transaction
    |
    +--> Open separate transaction
    |
    +--> Run script and commit
    |
    v
Resume test transaction
    |
    v
@Test and @AfterEach
    |
    v
Test transaction rolls back
~~~

Data created by the ISOLATED script has already committed in its own transaction, so rolling back the test transaction does not delete that data. The test must clean up this baseline data using a clearly scoped cleanup script or cleanup mechanism.

Do not pick ISOLATED simply because you want the script to "definitely run." If the goal is a fixture that exists only during the test and rolls back with the test, INFERRED is usually more appropriate.

## 10. Comparing INFERRED and ISOLATED

| Criterion | INFERRED | ISOLATED |
|---|---|---|
| Role | Infers transaction from context | Always requires a separate transaction |
| Joins active test transaction | Possible, if using the same manager | No |
| Requires transaction manager | Possibly not, if script runs non-transactionally | Yes |
| Outcome when script succeeds | Follows the joined or inferred transaction | Separate transaction commits immediately |
| Does data roll back with test? | Yes, if script joins test transaction | No, because it committed independently |
| Common use case | Fixture tied to test lifecycle | Baseline that must exist outside test transaction |

Choose the mode based on data lifecycle:

- Data serving only one test and expected to disappear after rollback: use INFERRED with the appropriate test transaction.
- Data that must remain after the test transaction rolls back: use ISOLATED and plan cleanup.
- Script needing to run when no test transaction exists yet still needing its own transaction: consider ISOLATED.
- Script not needing a transaction or database not supporting transactions for that operation: understand the limitations before using the default mode.

## 11. Class-level default configuration with @SqlConfig

If multiple scripts in a test class use the same DataSource and transaction manager, you can declare @SqlConfig at the class level to set defaults:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@SqlConfig(
    dataSource = "ordersDataSource",
    transactionManager = "ordersTransactionManager",
    transactionMode = SqlConfig.TransactionMode.INFERRED
)
class OrderRepositoryTest {

    @Test
    @Sql("/sql/orders-before-test.sql")
    void findsOrder() {
        // Test body
    }

    @Test
    @Sql("/sql/orders-with-lines.sql")
    void findsOrderWithLines() {
        // Test body
    }
}
~~~

Class-level @SqlConfig provides default configuration for @Sql declarations within the class. If a script needs a different DataSource or transaction manager, configure it individually on the corresponding @Sql annotation:

~~~java
@Test
@Sql(
    scripts = "/sql/billing-before-test.sql",
    config = @SqlConfig(
        dataSource = "billingDataSource",
        transactionManager = "billingTransactionManager"
    )
)
void loadsBillingData() {
}
~~~

This organization reduces repetition while still letting a test method choose its own database. Keep class-level configuration suitable for the majority of scripts; if every method has to override it, shared configuration may no longer help.

## 12. Using @Sql in setup and cleanup phases

@Sql has an `executionPhase` attribute to specify when the script runs:

- **BEFORE_TEST_METHOD**: before each test method; this is the default.
- **AFTER_TEST_METHOD**: after each test method.

Setup example:

~~~java
@Test
@Sql(
    scripts = "/sql/orders-before-test.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD,
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager"
    )
)
void findsOrder() {
}
~~~

Cleanup example with an independent transaction:

~~~java
@Test
@Sql(
    scripts = "/sql/orders-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
void cleansCommittedFixture() {
}
~~~

Cleanup scripts use ISOLATED when cleanup operations need to commit independently of the test's transaction. If cleanup runs inside the test transaction and the test rolls back, the delete operation can also roll back. Choose the mode according to the desired post-test data state.

Another approach is using an ISOLATED setup script and an ISOLATED cleanup script to manage committed fixtures. Both must accurately limit the IDs or namespace owned by the test.

## 13. @SqlGroup and multiple scripts with different configurations

When multiple @Sql declarations with different configurations are needed, you can repeat the annotation in modern Java or use @SqlGroup to group them:

~~~java
@SpringJUnitConfig(MultiDatabaseTestConfig.class)
@SqlGroup({
    @Sql(
        scripts = "/sql/orders-before-test.sql",
        config = @SqlConfig(
            dataSource = "ordersDataSource",
            transactionManager = "ordersTransactionManager"
        )
    ),
    @Sql(
        scripts = "/sql/billing-before-test.sql",
        config = @SqlConfig(
            dataSource = "billingDataSource",
            transactionManager = "billingTransactionManager"
        )
    )
})
class CrossDatabaseTest {
}
~~~

**@SqlGroup** is useful when expressing a group of setup or cleanup scripts. Each @Sql can still have its own config. Grouping annotations does not merge transaction managers or create a distributed transaction.

If scripts have ordering dependencies, declare order explicitly and name resources to reflect their roles. Avoid having scripts in multiple places modify the same table without knowing execution order.

## 14. Configuring the script parser and execution errors

The main focus of this lesson is choosing DataSource and transaction manager, yet @SqlConfig also has attributes controlling how Spring parses and executes scripts:

| Attribute | Role |
|---|---|
| encoding | Charset of the SQL file |
| separator | Statement separator |
| commentPrefix | Line comment prefix |
| blockCommentStartDelimiter | Block comment start delimiter |
| blockCommentEndDelimiter | Block comment end delimiter |
| errorMode | How errors are handled when executing statements |
| dataSource | DataSource bean used to run the script |
| transactionManager | Transaction manager bean used for the script |
| transactionMode | How transactions are managed when running the script |

Example:

~~~java
@Sql(
    scripts = "/sql/orders-seed.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        encoding = "UTF-8",
        separator = ";",
        commentPrefix = "--",
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR
    )
)
~~~

FAIL_ON_ERROR fails the test when an SQL statement encounters an error. This is usually the clear choice for fixtures that must be created completely. If choosing a mode that ignores errors, understand that the test may continue with missing data and fail at a harder-to-diagnose assertion elsewhere.

The separator and comment prefix should match the script format. For stored procedures or scripts with semicolons inside blocks, configuring a parser-appropriate separator may be necessary. Do not change parser settings if simple scripts already run cleanly with defaults.

## 15. Interacting with @Transactional on tests

When a test class or method is annotated with @Transactional, Spring TestContext typically opens a transaction before running the test method. `@Sql` scripts in the BEFORE_TEST_METHOD phase are processed in the test lifecycle; with INFERRED mode and the matching transaction manager, the script can join the active transaction.

Example:

~~~java
@SpringJUnitConfig(OrderDatabaseTestConfig.class)
@Transactional("ordersTransactionManager")
@Sql(
    scripts = "/sql/orders-before-test.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.INFERRED
    )
)
class TransactionalOrderTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void seesScriptData() {
        assertTrue(repository.existsById("order-188"));
    }
}
~~~

If the test transaction rolls back by default, fixture scripts joining the transaction also roll back. Other tests can reuse the same IDs because the data disappears once the transaction ends.

If the script uses ISOLATED, the fixture commits independently and can persist after the test rolls back. Use dedicated IDs or cleanup scripts to avoid stale data affecting subsequent runs.

### Script and transaction manager must belong to the same database

A common mistake is the test using `ordersTransactionManager` while the script uses a DataSource or manager of a different database. In that case, data created by the script may not reside inside the transaction the test expects to roll back.

Align three components:

1. Which database does the repository under test use?
2. Which transaction manager does the test's @Transactional use?
3. Which DataSource and transaction manager does @SqlConfig use?

If the three answers do not share the same resource boundary, explain clearly why the test requires that and how data is cleaned up.

## 16. Interacting with JPA and the persistence context

When an SQL script inserts data directly into the database, an open JPA persistence context may not automatically know about the change. This is especially important when the same transaction already loaded entities before the script ran, or when the script ran in an independent transaction.

Some principles:

- SQL scripts operate directly on the database via JDBC.
- JPA EntityManager manages entities in its own persistence context.
- Already-loaded entities may retain stale state in the first-level cache.
- ISOLATED scripts commit in a separate transaction; the test's persistence context may need refreshing or clearing before reading again.
- If the test writes via JPA and then an SQL script reads data, flushing may be required to push pending changes to the database.

Example:

~~~java
@Autowired
private EntityManager entityManager;

@Test
void reloadsEntityAfterDirectSqlChange() {
    OrderEntity order = entityManager.find(OrderEntity.class, "order-188");

    // A SQL script or JDBC operation updates the row.

    entityManager.refresh(order);
    assertEquals("PAID", order.getStatus());
}
~~~

The example only illustrates refreshing an entity after a JDBC change. In real tests, ensure the script runs on the correct DataSource and transaction manager; if the script uses an independent transaction, changes have already committed before refreshing. If changes are in another uncommitted transaction, the current transaction may not see them depending on isolation level.

Do not call `EntityManager.clear()` or `refresh()` mechanically. It is only needed when a test directly mixes JDBC scripts with managed entities and needs state synchronization.

## 17. Common mistakes when selecting DataSource and transaction manager

### Not specifying beans when multiple DataSources exist

Spring may fail to infer a DataSource or pick an unintended candidate. Declare `dataSource` by bean name in @SqlConfig.

### Choosing a DataSource and transaction manager from different databases

The script may run outside the expected transaction or data may not roll back. Pair each DataSource with the manager that manages it.

### Using a JPA transaction manager for the wrong persistence unit

An application with multiple EntityManagerFactory instances may have multiple JpaTransactionManagers. Pick the manager bound to the persistence unit containing the tables the script operates on.

### Assuming INFERRED always rolls back the script

INFERRED depends on the current transaction and inferred manager. If there is no test transaction, the script may run in its own transaction and commit according to execution mechanics. Check transaction state and manager rather than relying solely on the mode name.

### Using ISOLATED without cleanup

Independent transactions commit immediately after the script. Test rollback does not remove that data. Use dedicated IDs and scoped cleanup scripts.

### Expecting ISOLATED to work with no transaction manager

ISOLATED requires a suitable transaction manager. Register a manager or choose a mode compatible with your infrastructure.

### Using @Transactional while the repository uses another manager

The test transaction may not wrap the repository's operations. Specify the right manager on the test and inspect repository configuration.

### Cleanup script running in a transaction about to roll back

If a cleanup script joins the test transaction and the transaction rolls back, the delete operation also rolls back. When persistent cleanup is needed, use an independent transaction and scope data precisely.

### Using multiple databases and expecting one atomic transaction

Two independent transaction managers do not automatically coordinate commit/rollback. If cross-database atomicity is required, use a distributed transaction solution or another consistency design.

### Script failing while the test continues

If configuration ignores errors, tests can run on incomplete fixtures. For critical scripts, let SQL errors fail the test and surface the offending statement/resource.

## 18. Workflow for selecting DataSource and transaction manager

When a test needs to execute an SQL script, decide in order:

1. **Identify target database**: which DataSource owns the tables the script reads or writes?
2. **Identify DataSource bean**: obtain the exact bean name in the ApplicationContext.
3. **Identify transaction manager**: which manager manages that same DataSource or persistence unit?
4. **Align with test transaction**: if the test has @Transactional, select the same manager when the script should join the test's transaction.
5. **Choose transaction mode**: use INFERRED for fixtures belonging to the test transaction; use ISOLATED when an immediately committed separate transaction is needed.
6. **Choose phase**: BEFORE_TEST_METHOD for setup, AFTER_TEST_METHOD for cleanup.
7. **Scope data**: use dedicated IDs or namespaces, avoiding deleting shared data.
8. **Check multi-database setups**: each script has its own config; do not assume multiple managers create one atomic distributed transaction.
9. **Handle persistence context**: flush, refresh, or clear when combining JDBC scripts with managed JPA entities.
10. **Keep script errors visible**: pick an appropriate error mode, typically failing when fixtures cannot be created.

## 19. Combined example: setup and cleanup scripts with the orders database

Database configuration:

~~~java
@Configuration
class OrderSqlTestConfig {

    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl("jdbc:postgresql://localhost:5432/orders_test");
        dataSource.setUsername("orders_test_user");
        dataSource.setPassword("test-only-password");
        return dataSource;
    }

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    OrderRepository orderRepository(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcOrderRepository(dataSource);
    }
}
~~~

Test class:

~~~java
@SpringJUnitConfig(OrderSqlTestConfig.class)
@Transactional("ordersTransactionManager")
class OrderSqlFixtureTest {

    @Autowired
    private OrderRepository repository;

    @Test
    @Sql(
        scripts = "/sql/order-188-before.sql",
        config = @SqlConfig(
            dataSource = "ordersDataSource",
            transactionManager = "ordersTransactionManager",
            transactionMode = SqlConfig.TransactionMode.INFERRED
        )
    )
    void readsOrderCreatedByScript() {
        assertTrue(repository.existsById("order-188"));
    }
}
~~~

In this example, the setup script and repository share the orders database. The script runs in the test-managed transaction in INFERRED mode and data is rolled back after the test.

If you want to test independently committed data:

~~~java
@Test
@Sql(
    scripts = "/sql/order-188-before.sql",
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
@Sql(
    scripts = "/sql/order-188-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
void readsCommittedBaseline() {
    assertTrue(repository.existsById("order-188"));
}
~~~

The setup script commits data in an independent transaction. The cleanup script also runs in an independent transaction after the test to delete the exact committed fixture. In real projects, resource cleanup must only delete IDs owned by the test and must run even when test assertions fail.

## 20. Principles to remember

- DataSource determines which database the script connects to.
- PlatformTransactionManager determines which transaction manages the script.
- Use `dataSource` in @SqlConfig when explicit DataSource selection is needed.
- Use `transactionManager` in @SqlConfig to select the matching transaction manager.
- When multiple databases exist, specify the exact bean pair for each script.
- INFERRED uses the current transaction context and suitable manager to determine execution.
- ISOLATED runs the script in an independent transaction and commits upon script success.
- ISOLATED scripts do not roll back with the test transaction; separate cleanup is required.
- The test's @Transactional and @SqlConfig should share the same manager when fixtures need to join the test transaction.
- Multiple transaction managers do not create atomic cross-database transactions automatically.
- When mixing JDBC scripts and JPA, pay attention to persistence context, flush, and refresh.
- Choose clear setup/cleanup phases and data scopes so tests can run repeatedly.

Selecting the right DataSource ensures scripts operate on the intended database; selecting the right transaction manager ensures data commits or rolls back at the boundary the test expects. For simple contexts, Spring can infer suitable beans. For applications with multiple databases or multiple transaction managers, declare bean names explicitly in **@SqlConfig**, align with **@Transactional**, and choose between **INFERRED** and **ISOLATED** based on the fixture's lifecycle. That makes SQL scripts reproducible, easy to diagnose, and free of unintended leftover data.

