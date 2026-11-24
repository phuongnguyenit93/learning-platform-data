# Script Transaction Modes and Rollback Scope

Spring TestContext Framework lets you run SQL scripts to prepare data before tests or clean up data after tests using **@Sql**. An important question is which transaction the statements in the script belong to. If a script joins the test's transaction, its changes can be rolled back along with the test. If a script runs in an independent transaction and commits immediately, data can persist after the test ends.

The **@SqlConfig** annotation provides the **transactionMode** attribute to control how a script participates in transactions. Two commonly used modes are:

- **INFERRED:** Spring infers how to run the script from the DataSource, PlatformTransactionManager, and active transaction. If a test transaction exists, the script typically joins that transaction.
- **ISOLATED:** the script runs in an independent transaction and that transaction commits immediately once the script completes successfully.

Transaction mode determines the rollback scope. This is essential to understand when using seed scripts, cleanup scripts, tests with @Transactional, or when verifying data after commit. A script running successfully does not automatically mean its data will be rolled back when the test finishes.

## 1. What is @Sql used for?

@Sql is a Spring TestContext Framework annotation for declaring SQL scripts to execute during testing. Scripts usually contain INSERT, UPDATE, or DELETE statements to prepare database state.

Example:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Sql("/db/test-data.sql")
class CustomerRepositoryTests {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void finds_customer_created_by_script() {
        assertThat(customerRepository.findById("C-100"))
            .isPresent();
    }
}
~~~

The `/db/test-data.sql` script is typically placed in **src/test/resources/db/test-data.sql** so it can be located on the classpath.

@Sql can be placed at:

- Test class level: applies to test methods in the class according to the chosen execution phase.
- Test method level: applies to a specific method.
- Together with @SqlGroup or repeated declarations to run multiple groups of scripts.

The default execution phase of @Sql is **BEFORE_TEST_METHOD**. **AFTER_TEST_METHOD** can be used to run a script after the method:

~~~java
@Sql(
    scripts = "/db/cleanup-customer.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
~~~

@Sql only specifies the script and execution timing. How the script participates in transactions is configured separately via @SqlConfig.

## 2. @SqlConfig and transactionMode

@SqlConfig lets you configure how Spring executes SQL scripts, including:

| Attribute | Meaning |
| --- | --- |
| dataSource | Name of the DataSource bean used to execute the script |
| transactionManager | Name of the PlatformTransactionManager bean used to manage transactions |
| transactionMode | How the script participates in or creates a transaction |
| encoding | Encoding of the SQL file |
| separator | SQL statement separator character |
| commentPrefix | Line comment prefix |
| blockCommentStartDelimiter | Block comment opening delimiter |
| blockCommentEndDelimiter | Block comment closing delimiter |
| errorMode | How errors are handled during script execution |

The most important attribute in this lesson is `transactionMode`.

~~~java
@Sql(
    scripts = "/db/seed-customers.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
~~~

`SqlConfig.TransactionMode` has three values:

| Value | Meaning |
| --- | --- |
| DEFAULT | Uses the globally configured default mode; if no other global config exists, defaults to INFERRED |
| INFERRED | Infers the transaction from configuration and current transaction state |
| ISOLATED | Runs the script in an independent transaction and commits that transaction immediately upon successful completion |

DEFAULT is useful when a test class has a shared @SqlConfig. An individual @Sql declaration can use DEFAULT to continue applying the shared configuration. If no global configuration exists, the ultimate default mode is INFERRED.

## 3. INFERRED: letting Spring infer the transaction

INFERRED is the default mode of @SqlConfig if no global configuration alters it. Spring inspects the DataSource, transaction manager, and existing transaction to choose how to execute the script.

General rules:

1. If a suitable transaction manager and DataSource exist, Spring executes the script within a transaction managed by the transaction manager.
2. If an active transaction already exists, the script joins the current transaction.
3. If no active transaction exists, Spring may create a transaction for the script and commit it when the script completes.
4. If only a DataSource exists without a transaction manager, the script executes directly against the DataSource without a Spring-managed transaction.
5. If a DataSource cannot be determined for running the script, execution fails.

Therefore, INFERRED does not mean always roll back, nor does it mean always commit. The outcome depends on whether the script joins an existing transaction or has to run in its own transaction.

### 3.1. Script joining the test's transaction

This is the common situation when a test class or test method has @Transactional.

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
@Sql("/db/seed-customers.sql")
class CustomerRepositoryTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void reads_seeded_customer() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = ?",
            Integer.class,
            "C-100"
        );

        assertThat(count).isEqualTo(1);
    }
}
~~~

With standard configuration, TransactionalTestExecutionListener starts a test-managed transaction before the test method runs. A `@Sql` script in the BEFORE_TEST_METHOD phase executes inside the active transaction when `transactionMode` is INFERRED. The seed statements thus participate in the test's transaction.

After the test method finishes, Spring rolls back the transaction by default. Both the data created in the script and changes made by the test method are rolled back, provided they actually participated in the same transaction and the database supports rollback for those statements.

Overview flow:

~~~text
Spring starts test-managed transaction
                 |
                 v
       @Sql seed (INFERRED)
       joins test transaction
                 |
                 v
             @BeforeEach
                 |
                 v
             @Test method
                 |
                 v
       @AfterEach / after-test @Sql
       (if same transaction)
                 |
                 v
       Spring rolls back transaction
                 |
                 v
      Data in transaction disappears
~~~

This is a convenient option when script data only needs to exist within the test scope and should be cleaned up automatically via rollback.

### 3.2. INFERRED when no transaction is active

If the test has no test-managed transaction, yet Spring can determine a transaction manager and DataSource, the script can run in a new transaction and commit when the script completes.

Example:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
class NonTransactionalSqlTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql("/db/seed-customer.sql")
    void reads_data_seeded_without_test_transaction() {
        assertThat(jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = 'C-200'",
            Integer.class
        )).isEqualTo(1);
    }
}
~~~

In this situation, there is no test-managed transaction for the script to join. With a successfully inferred transaction manager and DataSource, the script runs in its own transaction and commits after successful execution. Data may remain after the test.

If the test suite uses a shared database, cleanup or distinct data identification is required. Do not assume that merely lacking @Transactional on a test will make script data disappear on its own.

### 3.3. INFERRED when only a DataSource exists

If Spring can locate a DataSource but no suitable transaction manager exists, the script may execute directly via the DataSource without a Spring-managed transaction.

In that case, rollback capability depends on how the JDBC connection is provided and database semantics. If the connection is in auto-commit mode, each statement may commit individually. Do not rely on test rollback to clean up scripts in this configuration.

If controlled rollback is needed, configure a suitable transaction manager or use an explicit database cleanup strategy.

## 4. ISOLATED: running the script in an independent transaction

ISOLATED requires the script to run in a new transaction, independent of the current transaction, and commits that transaction immediately when the script completes successfully.

Example:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class IsolatedSqlTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql(
        scripts = "/db/seed-customer.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    void can_read_data_seeded_in_isolated_transaction() {
        // Script already ran in its own transaction and committed.
        assertThat(jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = 'C-300'",
            Integer.class
        )).isEqualTo(1);
    }
}
~~~

When a test-managed transaction is active, Spring suspends that transaction to run the script in an independent transaction. Once the script finishes successfully, the separate transaction commits and the test's transaction resumes.

When the test method ends, rolling back the test-managed transaction cannot undo data committed in the ISOLATED transaction. This is the most important difference between ISOLATED and INFERRED when a test transaction exists.

### 4.1. ISOLATED requires both DataSource and transaction manager

To run an independent transaction, Spring needs:

- A DataSource to execute SQL.
- A PlatformTransactionManager managing transactions for that DataSource.

If these two matching components cannot be determined, the script cannot run in ISOLATED mode and the test will fail when preparing or executing the script.

When the application has multiple DataSources or multiple transaction managers, declare them explicitly:

~~~java
@Sql(
    scripts = "/db/seed-audit.sql",
    config = @SqlConfig(
        dataSource = "auditDataSource",
        transactionManager = "auditTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
~~~

The DataSource and transaction manager must manage the same database or the same transactional resource. Picking the wrong transaction manager can cause the script to run on a connection not managed by that transaction, making rollback/commit scope differ from expectations.

### 4.2. ISOLATED does not roll back with the test transaction

Suppose:

1. The test transaction begins.
2. An ISOLATED script inserts a customer and commits.
3. The test method updates the customer inside the test's transaction.
4. Spring rolls back the test transaction.

Result:

- The customer inserted by the ISOLATED script still exists.
- The update made in the test transaction is rolled back.

This is the exact behavior dictated by transaction boundaries. If the test must not leave seeded data behind after running, a separate cleanup script or equivalent cleanup mechanism is required.

## 5. Comparing INFERRED and ISOLATED by rollback scope

| Context | INFERRED | ISOLATED |
| --- | --- | --- |
| Test has an active transaction | Script joins the current transaction | Script runs in a new, independent transaction |
| Test transaction rolls back | Script joining the same transaction also rolls back | Committed script data persists |
| Test transaction commits | Script joining the same transaction commits with the test | Script already committed independently beforehand |
| No active transaction, transaction manager and DataSource present | Script runs in its own transaction and commits on completion | Script runs in an independent transaction and commits |
| Only DataSource present | Runs directly without a Spring-managed transaction | Does not meet requirements to run an isolated transaction |
| Need seed that only exists inside test transaction | Usually suitable | Unsuitable without cleanup |
| Need seed that persists outside test transaction | May be unsuitable if script joins test transaction | Suitable |

Choose based on the desired lifetime of the data:

- Fixture data that should roll back with the test: usually choose INFERRED in a test with @Transactional.
- Data that needs to commit independently for observation outside/after transactions: choose ISOLATED.
- Script data created when no test transaction exists: check the transaction manager and INFERRED commit semantics before assuming data will be cleaned up.

## 6. Combining seed and cleanup scripts

A useful pattern is seeding data in an independent transaction and running cleanup in an independent transaction after the test:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class CustomerSqlLifecycleTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql(
        scripts = "/db/seed-customer-c400.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    @Sql(
        scripts = "/db/cleanup-customer-c400.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    void reads_customer_seeded_outside_test_transaction() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from customers where customer_id = ?",
            Integer.class,
            "C-400"
        );

        assertThat(count).isEqualTo(1);
    }
}
~~~

`seed-customer-c400.sql`:

~~~sql
insert into customers(customer_id, customer_name)
values ('C-400', 'SQL test customer');
~~~

`cleanup-customer-c400.sql`:

~~~sql
delete from customers
where customer_id = 'C-400';
~~~

The seed script runs in its own transaction and commits. The cleanup script is invoked at AFTER_TEST_METHOD and also runs in its own transaction. Thus, cleanup commits independently of the test transaction.

This example assumes ID C-400 is dedicated to the test. In suites running in parallel, use unique IDs or a namespace mechanism so tests do not delete other tests' data or shared data.

### 6.1. Why does cleanup also need ISOLATED?

If a cleanup script joins the test's transaction and that transaction rolls back after the test ends, the DELETE statement can also be rolled back. In that case, the independently committed seed data remains.

Putting cleanup in ISOLATED ensures the DELETE statement commits in its own transaction. However, only do this when the test genuinely needs seed data to exist outside the transaction. For INFERRED seeds joining the test transaction, rollback usually cleans up both seed and test changes; separate isolated cleanup is unnecessary.

### 6.2. Cleanup must be safe when assertions fail

If an assertion in a test method fails, Spring still executes the transaction termination lifecycle and AFTER_TEST_METHOD callbacks per listener configuration. Cleanup scripts can help clear independently committed data.

Nevertheless, cleanup scripts can still fail due to database errors, foreign keys, or modified data. Write idempotent cleanup when possible, such as DELETE by unique key, and ensure it does not affect data outside the test's scope.

## 7. Global and local @SqlConfig configuration

@SqlConfig can be placed at the class level as shared configuration for @Sql declarations. An @SqlConfig placed in the `config` attribute of @Sql can customize a specific script.

Example:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@SqlConfig(
    dataSource = "testDataSource",
    transactionManager = "testTransactionManager",
    transactionMode = SqlConfig.TransactionMode.INFERRED
)
class SharedSqlConfigurationTests {

    @Test
    @Sql("/db/seed-default.sql")
    void uses_global_inferred_mode() {
        // ...
    }

    @Test
    @Sql(
        scripts = "/db/seed-independent.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
    )
    void overrides_transaction_mode_for_this_script() {
        // ...
    }
}
~~~

In the example, class-level @SqlConfig provides the DataSource, transaction manager, and shared mode. The first script uses the shared configuration. The second script requires ISOLATED for its specific case.

The DEFAULT value in local configuration allows falling back to the global default. If no global configuration exists, DEFAULT ultimately corresponds to the default INFERRED mode.

### 7.1. When there are multiple DataSources

If the application has multiple databases, do not rely on Spring inferring a single DataSource or transaction manager. Declare bean names explicitly:

~~~java
@SqlConfig(
    dataSource = "reportingDataSource",
    transactionManager = "reportingTransactionManager",
    transactionMode = SqlConfig.TransactionMode.ISOLATED
)
~~~

This ensures the script runs on the right database and transaction manager. Verify that both beans manage the same resource. An incompatible DataSource and transaction manager can prevent the script from running in the transaction the test author thinks it is using.

### 7.2. When using multiple scripts with different modes

Multiple @Sql annotations can be declared with separate configs:

~~~java
@Test
@Sql(
    scripts = "/db/seed-reference-data.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
@Sql(
    scripts = "/db/seed-temporary-data.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.INFERRED
    )
)
void combines_independent_and_test_scoped_fixtures() {
    // ...
}
~~~

The reference data script commits independently, while temporary data can join the test transaction and roll back with the test. Only use this combination when the data lifecycles of the two groups genuinely differ.

## 8. Does the script run before or after the test method?

Execution phase affects when the script is invoked; `transactionMode` determines how the script participates in transactions at that point.

| Execution phase | Timing | Common purpose |
| --- | --- | --- |
| BEFORE_TEST_METHOD | Before each test method | Seed fixtures |
| AFTER_TEST_METHOD | After each test method | Cleanup or script-based state verification |
| BEFORE_TEST_CLASS | Before the class's test methods | Prepare shared data for the class |
| AFTER_TEST_CLASS | After the class's test methods | Clean up class-level shared data |

BEFORE_TEST_CLASS and AFTER_TEST_CLASS are supported in newer Spring Framework versions starting from Spring Framework 6.1. For projects on older versions, check the `ExecutionPhase` enum in the Javadoc for that exact version; the two class-level phases may not be available.

Regardless of which phase a script runs in, do not infer rollback scope solely from the phase name. Identify which transaction is active, which transaction manager is used, and what `transactionMode` is configured.

### 8.1. AFTER_TEST_METHOD scripts do not automatically run outside the transaction

A common misconception is thinking a cleanup script after a test method is always outside the test transaction. Spring TestExecutionListeners have their own callback ordering. An AFTER_TEST_METHOD script may execute while the test-managed transaction is still active, depending on listener ordering and test configuration.

If cleanup must commit independently, declare `transactionMode = ISOLATED` instead of relying on the AFTER_TEST_METHOD phase.

### 8.2. BEFORE_TEST_CLASS scripts and transactions

Scripts running before methods may have no per-method test-managed transaction to join. Under INFERRED with a suitable transaction manager/DataSource, the script can run in its own transaction and commit. If data should persist across test methods, define an explicit class-level cleanup policy.

## 9. Rollback scope: what gets undone?

Rollback only undoes changes belonging to the rolled-back transaction that are supported for rollback by the database/resource. Do not treat rollback as a full-system restore operation.

### 9.1. Changes in the same transaction

If an INFERRED script joins a test-managed transaction, the script's DML statements and the test's operations share the same transaction. When Spring rolls back, those changes are usually undone together.

### 9.2. Changes in an ISOLATED transaction

An ISOLATED script runs in its own transaction and commits. Rolling back the test transaction does not affect committed changes. To remove that data, separate cleanup or a database recreated per test lifecycle is required.

### 9.3. Side effects outside the database

JDBC/JPA transactions do not automatically roll back:

- Emails sent.
- HTTP requests sent to external systems.
- Messages published to a broker if the broker does not participate in the same transaction.
- Files written to the filesystem.
- Distributed caches updated.
- Payment transactions confirmed by a provider.

These effects require test doubles, proper transaction coordination, the outbox pattern, or separate cleanup. Do not use `@Sql` `transactionMode` to reason about side effects outside the database managed by the transaction manager.

### 9.4. DDL and database-specific behavior

Some databases have specific rules for DDL such as CREATE TABLE, ALTER TABLE, or TRUNCATE. Some engines auto-commit certain statements or do not roll them back the same way as DML.

Therefore, even when a script runs inside a transaction, you cannot assume every DDL statement will roll back. Check the semantics of the database in use and separate schema setup from data fixtures when appropriate.

### 9.5. Sequences, identities, and auto-increment values

Some databases do not revert sequence or identity allocation when a transaction rolls back. The record may disappear while the allocated sequence number does not rewind. Tests must not assume the next ID will be contiguous or equal to a fixed value unless the database and configuration guarantee it.

## 10. @Sql and test-managed transactions

When a test class or test method has @Transactional, Spring TestContext typically starts a transaction before the test method runs and rolls back after the method. @Sql integrates through SqlScriptsTestExecutionListener.

A common configuration:

~~~java
@SpringJUnitConfig(JpaTestConfig.class)
@Transactional
class ProductRepositorySqlTests {

    @Autowired
    ProductRepository repository;

    @Test
    @Sql(
        scripts = "/db/products.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.INFERRED
        )
    )
    void loads_product_seeded_by_sql() {
        assertThat(repository.findBySku("SKU-1"))
            .isPresent();
    }
}
~~~

The script runs inside the test transaction and data rolls back after the test by default. This is usually the simplest way to seed data for repository tests.

If the test uses @Commit:

~~~java
@Test
@Commit
@Sql("/db/products.sql")
void commits_test_transaction() {
    // ...
}
~~~

An INFERRED script joins the test transaction and commits along with that transaction. If the script is ISOLATED, it commits independently as soon as the script completes, without waiting for @Commit.

## 11. Combining with @Rollback, @Commit, and @AfterTransaction

@Sql controls scripts. @Transactional, @Rollback, and @Commit control the test-managed transaction. @AfterTransaction lets you verify state after the test transaction ends.

The three mechanisms can work together:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class SqlRollbackTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Sql("/db/seed-in-transaction.sql")
    void sees_seed_data_inside_test_transaction() {
        assertThat(countRows("TEST-1")).isEqualTo(1);
    }

    @AfterTransaction
    void verifies_seed_data_was_rolled_back() {
        assertThat(countRows("TEST-1")).isZero();
    }

    private int countRows(String id) {
        return jdbcTemplate.queryForObject(
            "select count(*) from sample_data where id = ?",
            Integer.class,
            id
        );
    }
}
~~~

In the example, the INFERRED script joins the test transaction. After rollback, @AfterTransaction confirms the data is gone.

If you switch the script to ISOLATED, the post-transaction assertion must change because the seed data was committed separately. If data must not remain after the test, add ISOLATED cleanup or another cleanup mechanism.

### 11.1. Do not use @AfterTransaction as an automatic cleanup mechanism for all scripts

@AfterTransaction is a Java callback. It does not automatically delete data created by @Sql. You can use the callback to call a repository or JdbcTemplate cleanup, but ensure the cleanup operation commits outside the test transaction.

If you want to use SQL scripts for cleanup, declare @Sql with executionPhase AFTER_TEST_METHOD and the appropriate transactionMode.

## 12. Common mistakes

### Thinking INFERRED always rolls back

INFERRED joins an active transaction if present. If there is no test transaction, Spring may create a separate transaction and commit the script. Check actual transaction state before predicting whether data remains after the test.

### Thinking ISOLATED still rolls back with the test

ISOLATED commits its own transaction. Rolling back the test transaction cannot undo independently committed data. Separate cleanup is required if data must not persist after the test.

### Using ISOLATED without a transaction manager

ISOLATED needs a suitable DataSource and transaction manager. If missing, the script cannot run in the requested mode.

### Selecting the wrong DataSource or transaction manager

When an application has multiple databases, a script can run on one DataSource while the transaction manager manages another DataSource. Declare the corresponding bean names in @SqlConfig.

### Assuming AFTER_TEST_METHOD is always outside the transaction

Phase only determines when the script is called. If the script joins the test transaction, cleanup can be rolled back. To commit cleanup independently, use ISOLATED.

### Cleaning up shared data

An unconditional DELETE script can wipe another test's data or environment data. Use per-test keys, namespaces, or dedicated databases/schemas.

### Relying on rollback for DDL

DDL and sequences have database-specific semantics. Check your database engine's documentation and separate schema lifecycle from DML fixtures when needed.

### Ignoring side effects outside the database

Database rollback does not retract emails, HTTP requests, messages, or files. Verify and clean up those effects with appropriate mechanisms.

## 13. Workflow for choosing transactionMode

**Step 1 – Identify the script's purpose.** Is the script for seeding fixtures, creating baseline state, checking data, or cleanup?

**Step 2 – Check whether the test has a test-managed transaction.** Inspect @Transactional on the class/method and propagation settings.

**Step 3 – Determine whether data should roll back with the test.** If yes, INFERRED is usually suitable when the script runs inside the test transaction.

**Step 4 – Determine whether data must commit independently.** If yes, choose ISOLATED and ensure both DataSource and transaction manager exist.

**Step 5 – Choose the right database resources.** When multiple DataSources or transaction managers exist, declare names explicitly in @SqlConfig.

**Step 6 – Choose the execution phase.** Use BEFORE_TEST_METHOD to seed before the method, AFTER_TEST_METHOD to clean up after the method, or class-level phases when supported by your Spring version and aligned with data lifecycle.

**Step 7 – Plan cleanup.** If seeds commit independently, plan independent cleanup. Use dedicated data keys for safe cleanup.

**Step 8 – Consider database semantics.** Check DDL, sequences, identities, and statements that may auto-commit.

**Step 9 – Verify after the transaction.** Use @AfterTransaction or a fresh query to confirm whether data persists or rolled back as expected.

**Step 10 – Run tests in isolation and in the suite.** Ensure scripts do not depend on order, do not delete out-of-scope data, and do not leave unintended committed fixtures behind.

## 14. Quick decision table

| Question | Usually suitable choice |
| --- | --- |
| Should the script roll back with the test-managed transaction? | INFERRED |
| Should the script persist after the test transaction rolls back? | ISOLATED |
| Should the cleanup script commit independently after the test? | AFTER_TEST_METHOD combined with ISOLATED |
| Test has no transaction, but transaction manager and DataSource exist? | INFERRED can create a separate transaction and commit the script |
| Only DataSource exists, no transaction manager? | INFERRED runs without a Spring-managed transaction; do not rely on rollback |
| Application has multiple databases? | Declare `dataSource` and `transactionManager` explicitly |
| Only want to use the shared @SqlConfig configuration? | DEFAULT in local declaration or omit local `config` |
| Script contains DDL or sequences? | Verify the specific semantics of the database |

## 15. Practical principles

- Always identify which transaction is active when @Sql runs.
- Use INFERRED when you want the script to join the test transaction and roll back with the test.
- Use ISOLATED when the script needs its own transaction committed immediately.
- Remember ISOLATED requires a matching DataSource and transaction manager.
- Distinguish `executionPhase` from `transactionMode`: one selects timing, the other selects transaction scope.
- If seeding ISOLATED, consider ISOLATED cleanup.
- Use global @SqlConfig to share settings and local config for intentional exceptions.
- When multiple DataSources exist, choose the matching DataSource and transaction manager.
- Do not assume database rollback retracts side effects outside the database.
- Verify DDL, sequence, and identity semantics for the actual database engine.
- Use dedicated data keys so parallel tests run safely.

## Conclusion

`@SqlConfig`'s `transactionMode` decides whether an SQL script joins an existing transaction or runs in an independent transaction. INFERRED lets Spring infer: if a suitable test-managed transaction exists, the script usually joins and rolls back with the test; if no active transaction exists but a transaction manager and DataSource are present, the script can run in its own transaction and commit. ISOLATED always requires an independent transaction that commits immediately upon successful completion of the script.

Keep script execution timing separate from rollback scope. BEFORE_TEST_METHOD or AFTER_TEST_METHOD does not by itself determine whether data persists after the test. That depends on `transactionMode`, the transaction manager, the DataSource, and database semantics. Choosing the right mode keeps seeding and cleanup clearly controlled, prevents tests from leaving unintended data behind, and ensures assertions accurately reflect post-commit or post-rollback state.
