# Default rollback after a test method

When testing a persistence layer or a service that writes data, we usually want each test to start from a deterministic database state and prevent data from an earlier test from affecting subsequent tests. Spring TestContext supports **test-managed transactions**: if a test method or test class is annotated with `@Transactional`, Spring can open a transaction before the test runs and roll back that transaction after the method finishes.

With test-managed transactions, **rollback is the default behavior**. A test still rolls back when assertions succeed; rollback does not happen only when a test fails. As a result, a test can insert, update, or delete data within the transaction and inspect the results right inside the test without leaving the changes made in that transaction persisted after the test completes.

It is important to understand the exact scope of this transaction. It governs operations that participate in the same transaction manager and test transaction context. It does not automatically revert every external side effect, such as requests processed on another server thread, `REQUIRES_NEW` transactions, sent messages, written files, or changes in external systems.

## 1. What is a test-managed transaction?

The Spring TestContext Framework integrates transactions via `TransactionalTestExecutionListener`. This listener reads `@Transactional` metadata on the test class or test method, locates the appropriate transaction manager, and manages the transaction lifecycle for the test.

A test-managed transaction typically follows this sequence:

```text
Spring TestContext prepares the test
              |
              v
Opens transaction for the test method
              |
              v
JUnit @BeforeEach
              |
              v
Test method
              |
              v
JUnit @AfterEach
              |
              v
Commit or rollback according to test configuration
              |
              v
Spring @AfterTransaction
```

Under the default policy, the final step is a rollback. Spring's `@BeforeTransaction` and `@AfterTransaction` callbacks are designed to run outside the test-managed transaction; they are useful when you need to prepare or verify data before/after the transaction. Meanwhile, JUnit callbacks such as `@BeforeEach` and `@AfterEach` are executed inside the test's transaction once the transaction has already been opened.

A test-managed transaction differs from a transaction created by application code in that Spring TestContext starts and ends the transaction wrapping the test method. When a service invokes an `@Transactional` method with the default `REQUIRED` propagation on the same transaction manager and thread, the operation typically joins the test's transaction.

## 2. Enabling transactions for tests

To have Spring manage a transaction for a test, annotate the class or method with `@Transactional`. An appropriate transaction manager must exist in the ApplicationContext.

Example with JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(TestDatabaseConfiguration.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void insertsAccountInsideTestTransaction() {
        jdbcTemplate.update(
                "insert into account(email) values (?)",
                "rollback@example.test");

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from account where email = ?",
                Integer.class,
                "rollback@example.test");

        assertEquals(1, count);
    }
}
```

This example assumes `TestDatabaseConfiguration` configures a datasource, a `JdbcTemplate`, and a `PlatformTransactionManager` using the same datasource. In the test, the record can be read immediately within the transaction and the assertion confirms the insert took effect for the current transaction. After the method finishes, Spring rolls back the transaction by default, so the record is not committed to the database.

Without `@Transactional` on the class or method, Spring TestContext does not automatically open a transaction merely because the test uses Spring. An ordinary test is not automatically rolled back; write operations may commit according to the application's transaction or the datasource's auto-commit mechanism.

### 2.1. @Transactional at the class level

Place `@Transactional` on the class so that test methods in the class participate in a test-managed transaction by default:

```java
@SpringJUnitConfig(TestConfiguration.class)
@Transactional
class OrderRepositoryTests {

    @Test
    void savesOrder() {
        // A transaction is opened for this method.
    }

    @Test
    void updatesOrder() {
        // Separate transaction for this method.
    }
}
```

Each test method gets its own transaction. Spring does not open a single transaction for the entire class and keep it open across all methods.

### 2.2. @Transactional at the method level

If only some tests need a transaction, you can place the annotation directly on the method:

```java
@SpringJUnitConfig(TestConfiguration.class)
class AccountServiceTests {

    @Test
    @Transactional
    void createsAccountAndRollsBackAfterTest() {
        // Test runs in a test-managed transaction.
    }

    @Test
    void checksPureCalculationWithoutTransaction() {
        // No test-managed transaction.
    }
}
```

A method-level annotation can be used to define the transaction behavior for that method. If the class already has `@Transactional`, a method can use its own metadata to override the configuration appropriately.

### 2.3. Selecting a transaction manager

If the context has only one matching `PlatformTransactionManager`, Spring can find that transaction manager using default rules. If the application has multiple transaction managers, explicitly specify the bean to use:

```java
@Transactional(transactionManager = "ordersTransactionManager")
@Test
void updatesOrderDatabase() {
    // Operations join the ordersTransactionManager transaction.
}
```

The `value` attribute is an alias for `transactionManager`, so you can write the shorthand `@Transactional("ordersTransactionManager")`. Selecting the right transaction manager is critical: rolling back the transaction manager for database A does not automatically roll back operations performed through the transaction manager for database B.

## 3. Why is rollback the default?

Tests often create temporary data to verify behavior. If every test committed, data could accumulate, cause duplicate key errors, alter query results, or make tests depend on execution order.

Default rollback provides several benefits:

- **Data isolation:** changes within one test's transaction do not become committed data for subsequent tests.
- **Repeatability:** the same test can run multiple times without manually deleting every record it created.
- **Reduced order dependency:** tests do not need to assume whether earlier tests created or did not create data.
- **Simplified cleanup:** the database automatically reverts changes belonging to the transaction instead of requiring delete statements for every case.
- **Inspecting intermediate state:** a test can write data and query it back within the same transaction before rollback.

Rollback does not mean the test cannot write data. The test can still perform full insert, update, and delete operations inside the transaction; those changes are simply not committed when the test finishes under the default policy.

## 4. @Rollback and @Commit

Spring TestContext provides two annotations to control the outcome of a test-managed transaction:

- `@Rollback`: specifies whether the transaction should roll back when finished.
- `@Commit`: requests committing the transaction when the test completes.

`@Rollback` has a default value of `true`. Therefore, `@Rollback` without an argument still indicates rollback. This is also the default behavior of a test-managed transaction when the test has `@Transactional`.

### 4.1. Explicitly specifying rollback

```java
@Test
@Transactional
@Rollback(true)
void createsTemporaryAccount() {
    // Data is written in the transaction and rolled back after the test.
}
```

This declaration is equivalent to the default behavior. It can be used when you want to document the test's intent or override a class-level configuration that requests a commit.

### 4.2. Committing with @Commit

```java
@Test
@Transactional
@Commit
void storesReferenceDataForLaterTests() {
    // Changes are committed when the test method completes.
}
```

`@Commit` is an explicit way to express commit intent, equivalent in purpose to `@Rollback(false)`. Use it only when the test genuinely needs data to persist after the method finishes, such as a dedicated test creating a long-lived fixture for a controlled integration workflow.

### 4.3. Using @Rollback(false)

```java
@Test
@Transactional
@Rollback(false)
void commitsAccount() {
    // Transaction is committed when the test finishes.
}
```

`@Rollback(false)` causes the transaction to commit instead of rolling back. `@Commit` is usually easier to read because it expresses the intent directly.

### 4.4. Declaring at the class level and overriding on a method

You can set a policy for the entire class and then change it on a single method:

```java
@SpringJUnitConfig(TestConfiguration.class)
@Transactional
@Rollback(false)
class AccountPersistenceTests {

    @Test
    void commitsReferenceAccount() {
        // Commits per class-level configuration.
    }

    @Test
    @Rollback
    void rollsBackTemporaryAccount() {
        // Rollback is explicitly requested for this method.
    }
}
```

In this example, the class-level `@Rollback(false)` requests commits by default for transactional test methods. The second method uses `@Rollback` (defaulting to `true`) to override and roll back individually. Avoid creating tests that depend on data committed by another method; with such dependencies, the suite becomes hard to run in isolation and hard to run in parallel.

## 5. When to verify data before and after rollback

Inside a test-managed transaction, the test method can see its own changes. To verify that rollback actually happened after the method ends, you can use `@AfterTransaction`, a Spring callback that runs after the transaction has ended.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(TestDatabaseConfiguration.class)
@Transactional
class RollbackAfterMethodTest {

    private static final String EMAIL = "rollback-check@example.test";

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void rowExistsInsideTestTransaction() {
        jdbcTemplate.update(
                "insert into account(email) values (?)", EMAIL);

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from account where email = ?",
                Integer.class,
                EMAIL);

        assertEquals(1, count);
    }

    @AfterTransaction
    void rowDoesNotExistAfterRollback() {
        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from account where email = ?",
                Integer.class,
                EMAIL);

        assertEquals(0, count);
    }
}
```

This example assumes the `account` table exists, the test email does not already exist before running, and `JdbcTemplate` uses the same datasource/transaction manager as the test. `@AfterTransaction` runs after Spring has rolled back the transaction, so the query verifies state outside the test transaction. In a test suite sharing data, generate unique identifiers or prepare/clean up fixtures to avoid colliding with other tests.

`@BeforeTransaction` can similarly be used to inspect or prepare state before the transaction begins:

```java
@BeforeTransaction
void verifyInitialState() {
    // Runs before Spring opens the test-managed transaction.
}
```

These callbacks are only invoked for tests that have a test-managed transaction. They do not replace `@BeforeEach`/`@AfterEach`; the two groups of callbacks serve different points in the test lifecycle.

## 6. Transaction lifecycle and JUnit callbacks

With JUnit Jupiter and `SpringExtension`, JUnit method callbacks such as `@BeforeEach` and `@AfterEach` run within the scope of the test-managed transaction once the transaction has opened. `@BeforeAll` and `@AfterAll` run outside each test method's transaction.

| Callback | Position relative to test-managed transaction | Purpose |
|---|---|---|
| `@BeforeTransaction` | Before opening the transaction | Inspect or prepare data outside the transaction |
| `@BeforeEach` | After the transaction starts | Prepare fixtures belonging to the test transaction |
| `@Test` | Inside the transaction | Execute behavior and assertions |
| `@AfterEach` | Before the transaction ends | Assertions/cleanup inside the transaction |
| Rollback/commit | Ends the transaction | Apply the completion policy |
| `@AfterTransaction` | After the transaction ends | Verify committed/rolled-back state |

This matters when choosing where to place cleanup. If you delete data in `@AfterEach` and that delete operation also runs inside the transaction about to roll back, the delete statement may not be committed. Usually there is no need to delete test data created in the same transaction because rollback already handles it. If cleanup outside the transaction is needed, use an appropriate callback and consider `REQUIRES_NEW` or a dedicated intentional mechanism.

## 7. Controlling transactions with TestTransaction

`TestTransaction` is a Spring TestContext API that lets tests inspect and control the test-managed transaction while the test is running.

Main operations:

- `isActive()`: checks whether a test-managed transaction is currently active.
- `flagForRollback()`: marks the current transaction to roll back when ended.
- `flagForCommit()`: marks the current transaction to commit when ended.
- `end()`: ends the current transaction according to the configured commit/rollback flag.
- `start()`: starts a new test-managed transaction if the test is configured to support it.

Example:

```java
@Test
@Transactional
void commitsFirstTransactionAndStartsAnother() {
    jdbcTemplate.update(
            "insert into account(email) values (?)",
            "committed@example.test");

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());

    TestTransaction.start();
    jdbcTemplate.update(
            "insert into account(email) values (?)",
            "temporary@example.test");
}
```

The first transaction is committed when `end()` is called. The second transaction is reopened and, unless its completion flag is changed, will roll back under the default policy when the test method completes. The example assumes `jdbcTemplate` is injected and uses the test's transaction manager.

`TestTransaction` is useful when you need to verify post-commit state or create multiple transaction phases within a single test. For typical tests, letting Spring automatically roll back after the method is usually simpler and clearer.

## 8. Flushing the persistence context before assertions

Rollback only occurs when the transaction ends; it does not guarantee that every write operation has already been sent to the database at the moment the repository is called. With JPA/Hibernate, entities may remain in the persistence context with SQL deferred until flush or commit.

This can cause a test to assume a save succeeded when the database has not yet checked constraints or executed the SQL statement.

Example with Spring Data JPA:

```java
@Test
@Transactional
void persistsEntityAndChecksDatabaseConstraint() {
    accountRepository.save(new Account("user@example.test"));

    entityManager.flush();

    assertEquals(1, accountRepository.countByEmail("user@example.test"));
}
```

`flush()` forces the persistence context to synchronize pending changes with the database within the current transaction. It does not commit the transaction. After the test, Spring still rolls back by default.

If you want to prove that data is actually read from the database rather than only from the first-level cache, you can flush and then clear the persistence context before querying again:

```java
accountRepository.save(account);
entityManager.flush();
entityManager.clear();

Account reloaded = accountRepository.findById(account.getId()).orElseThrow();
assertEquals("user@example.test", reloaded.getEmail());
```

`flush()` and `clear()` do not replace rollback. They serve to test the interaction between the persistence context and the database before the transaction ends.

## 9. Rollback scope: what is reverted and what is not

Default rollback only applies to operations participating in the exact transaction managed by Spring. It should not be thought of as a snapshot mechanism for the entire system.

| Operation | Rolled back with the test transaction? | Conditions/explanation |
|---|---|---|
| JDBC insert/update/delete | Yes | Uses the same datasource and transaction manager, on the current transaction context |
| JPA/Hibernate write | Yes | EntityManager participates in the same transaction; flush is not commit |
| Service `@Transactional(REQUIRED)` | Usually yes | Joins the current transaction if on the same transaction manager and thread |
| Service `REQUIRES_NEW` | Not necessarily | Creates an independent transaction; may commit before the test rolls back |
| Another database with another transaction manager | Not automatically | Each transaction manager manages its own resource |
| HTTP request to an embedded server | No | Server handles the request on a separate thread and transaction |
| `@Async` or task running on another thread | Not automatically | Thread-bound transactions do not automatically propagate to a new thread |
| Sending email/message to an external system | No | Side effects outside the database are not reverted by a JDBC/JPA transaction |
| Writing files or calling external APIs | No | Requires separate cleanup or test doubles |
| Database sequences/identities | Database-dependent | Some generators do not revert to pre-rollback values |
| DDL or database administration operations | Database-dependent | Some DDL statements auto-commit or do not participate in transactions like regular DML |

If a test needs to verify changes across multiple resources, an appropriate transaction coordination mechanism or dedicated cleanup design is required. A single JDBC transaction does not guarantee rolling back a sent email or an HTTP request already processed on another server thread.

### 9.1. REQUIRES_NEW

A service method using `Propagation.REQUIRES_NEW` requests an independent transaction. The test's current transaction may be suspended while the new transaction runs. If the new transaction commits, rolling back the outer transaction does not automatically revert those committed changes.

Therefore, when testing a service with `REQUIRES_NEW`, clearly define the goal: whether to verify that the independent transaction commits properly, or whether the data needs cleanup after the test. Do not assume the test's rollback will delete every record the service creates.

### 9.2. HTTP requests via an embedded server

In a `@SpringBootTest(webEnvironment = RANDOM_PORT)` test, HTTP requests are handled by the server on a separate thread. The test method's transaction does not automatically wrap the server request's transaction.

For example, a test method with `@Transactional` sends `POST /orders` via `TestRestTemplate`. The server may create and commit the order in its own transaction. When the test method finishes, the test-side transaction rolls back, but the order created by the server still remains.

For server integration tests, use test data with unique identifiers and clean up via repository/API or reset the database/schema according to the project's strategy. Do not rely on `@Transactional` on the test method to automatically roll back remotely processed requests.

## 10. Notes on timeouts running on another thread

Spring TestContext normally binds the transaction to the thread executing the test. Some timeout APIs run the test body on another thread so it can be interrupted when time expires. In that case, database operations on the auxiliary thread may not join the test's transaction.

Dangerous example:

```java
assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
    accountRepository.save(account);
});
```

JUnit Jupiter's `assertTimeoutPreemptively` executes the callback in a separate thread. The transaction bound by Spring to the original test thread does not automatically propagate to that thread. If the repository opens an independent transaction or the datasource operates outside the test transaction, changes can commit and persist after the test.

When a test needs to guarantee rollback, avoid placing database operations inside a preemptive timeout callback. You can use non-preemptive `assertTimeout` where appropriate, or design the test and transaction clearly so all operations requiring rollback execute on the transaction-managing thread. If another thread must be used, separate cleanup is required.

## 11. When should tests not use @Transactional?

Not every test needs a transaction:

- Unit tests checking pure logic do not need a database.
- Real HTTP server tests need to observe data committed in the server transaction.
- Tests verifying a service's commit/rollback need to control transactions explicitly.
- Tests checking transaction propagation behavior may need multiple transactions or state verification outside the transaction.
- Tests using resources that do not participate in database transactions need separate cleanup.

If you need to inspect data after commit, you can use `@Commit`, `TestTransaction.flagForCommit()`, or an integration test that does not wrap the entire method in a test-managed transaction, depending on the goal. Avoid adding `@Transactional` out of habit if it causes the test to mask the application's actual commit behavior.

## 12. Some @Transactional attributes in tests

`@Transactional` in Spring TestContext uses a transaction manager to manage the test's transaction. Not every attribute of `@Transactional` has the exact same meaning as when placed on a service method.

Some points to keep in mind:

- `transactionManager` or `value` helps select the transaction manager.
- `propagation = NOT_SUPPORTED` or `NEVER` can be used to request that the test not run inside a test-managed transaction.
- Other attributes should be checked against the Spring TestContext documentation for the version in use; do not assume every propagation, timeout, or isolation setting of a service method is applied identically to an application flow.
- `@Transactional` on a test class/method is handled by the TestContext listener, whereas the annotation on a service method is handled by the application's transaction infrastructure.

If the goal is to test the isolation level, timeout, or propagation of a service, test the behavior through the actual service and transaction manager rather than inferring it from test-method configuration. A test-managed transaction can alter the transaction context the service receives.

## 13. Common mistakes

**Assuming every test automatically rolls back.** Only tests with a test-managed transaction receive Spring TestContext's rollback policy. Without `@Transactional`, there is no automatic test transaction.

**Assuming a test only rolls back on failure.** By default, the transaction rolls back after the method even when the test passes. Only `@Commit` or `@Rollback(false)` requests a commit.

**Using the wrong transaction manager.** The repository and the test may use different transaction managers. Explicitly specify `transactionManager` when multiple managers exist and ensure they govern the same resource that needs rollback.

**Assuming rollback deletes data created by a server thread.** HTTP requests to an embedded server have an independent transaction. The test needs to clean up data written by the server.

**Overlooking `REQUIRES_NEW`.** An independent transaction can commit even if the outer test transaction rolls back.

**Using preemptive timeouts around database operations.** Callbacks running on another thread may not join the test's transaction and may leave committed data behind.

**Failing to flush the persistence context.** JPA can defer SQL until the end of the transaction. Flush when you need to verify SQL statements or database constraints before the test finishes.

**Using `@AfterEach` to delete data inside a transaction about to roll back.** That cleanup operation can also be rolled back. Use the default rollback or an out-of-transaction callback according to your goal.

**Committing shared data between tests.** Later tests may depend on data from earlier tests, making the suite hard to run in isolation and hard to parallelize. Prefer independent fixtures.

**Assuming rollback reverts every side effect.** Emails, messages, files, HTTP calls, and database sequences may not be reverted. Test doubles, transaction coordination, or separate cleanup are needed.

## 14. Workflow for designing tests with rollback

When writing a persistence or service test that needs transactions, determine:

1. Does the test truly need a Spring-managed transaction?
2. Which transaction manager governs the datasource or resource being tested?
3. Should `@Transactional` be placed on the class or method?
4. Does the test need the default rollback, or must it commit to verify post-commit behavior?
5. Do `@BeforeEach`/`@AfterEach` methods manipulate data within the same transaction?
6. Does any service use `REQUIRES_NEW`, `NOT_SUPPORTED`, or run on another thread?
7. Are there HTTP requests to an embedded server, `@Async`, preemptive timeouts, or asynchronous callbacks?
8. With JPA, are `flush()`/`clear()` needed so assertions reflect database state?
9. How are side effects outside the transaction cleaned up or isolated?
10. Does the test run independently, repeatably, and without order dependencies?

For a typical persistence test, `@Transactional` at the class or method level with default rollback is usually sufficient. Use `@Commit` or `@Rollback(false)` only when changes must persist after the method. When mid-method control is needed, use `TestTransaction`; when post-transaction state needs verification, use `@AfterTransaction`. Always remember that rollback only reverts operations that actually participate in the test transaction.

## 15. References

- [Spring Framework Reference — Transaction Management in TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): describes test-managed transactions, default rollback, `@Commit`, `@Rollback`, callbacks, and test transaction limitations.
- [Spring Framework Javadoc — @Transactional](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Transactional.html): describes the transaction annotation and its attributes.
- [Spring Framework Javadoc — TestTransaction](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): API for controlling transactions in tests.

Default rollback is the mechanism by which Spring TestContext keeps persistence tests independent and repeatable. When a test method has `@Transactional`, Spring opens a transaction for the method and rolls it back after the method completes unless the test requests a commit. To rely on this mechanism safely, ensure the operations that need reverting participate in the same transaction, while managing any side effects that run outside that transaction separately.
