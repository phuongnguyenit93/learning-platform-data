# ExecutionPhase for Running Before or After Tests

In Spring integration testing, initial data is often prepared with SQL: creating sample records, setting the state to verify, or building a fixed dataset. After the test finishes, you may need to clean up data or verify persisted state. Spring Test provides `@Sql` to execute SQL scripts and `ExecutionPhase` to select when they run in the test lifecycle.

`ExecutionPhase` has four values: `BEFORE_TEST_METHOD`, `AFTER_TEST_METHOD`, `BEFORE_TEST_CLASS`, and `AFTER_TEST_CLASS`. The two method-level phases allow preparing or cleaning up data around each test method. The two class-level phases allow setting up once before the entire test class and cleaning up once after all test methods finish. Choosing the right phase avoids redundant SQL execution and clarifies the lifecycle of test data.

## 1. @Sql and ExecutionPhase

`@Sql` belongs to the `org.springframework.test.context.jdbc` package:

```java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;
```

The annotation can be declared on a test method or test class. It tells Spring Test which scripts to run and in which phase. Simple example:

```java
@Test
@Sql(
        scripts = "/sql/insert-customer.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_METHOD
)
void findsCustomer() {
    // Test runs after the SQL fixture has been applied.
}
```

If `executionPhase` is omitted, the default value is `BEFORE_TEST_METHOD`. Thus, `@Sql(scripts = "/sql/insert-customer.sql")` on a method runs the script before that method.

`@Sql` is executed by `SqlScriptsTestExecutionListener` in the Spring TestContext Framework. This listener reads scripts from the test classpath, selects the appropriate `DataSource` and transaction manager, and executes the SQL as configured. `ExecutionPhase` controls when the listener runs the script; it does not create data by itself nor determine all transaction semantics. Transaction behavior is further controlled by `@SqlConfig` and the test's transaction context.

## 2. The four ExecutionPhase values

| Phase | Timing | Typical frequency | Typical purpose |
|---|---|---|---|
| `BEFORE_TEST_METHOD` | Before each test method | Every method that declares or inherits the configuration | Load per-test fixtures |
| `AFTER_TEST_METHOD` | After each test method | After each method | Clean up data or run post-test SQL checks |
| `BEFORE_TEST_CLASS` | Before the class's test methods | Once per test class | Create schema or load shared data |
| `AFTER_TEST_CLASS` | After the class's test methods complete | Once per test class | Drop schema or clean up shared data |

`BEFORE_TEST_METHOD` and `AFTER_TEST_METHOD` existed in earlier Spring Test versions. `BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` were added in Spring Framework 6.1. The two class-level phases are only used on class-level `@Sql` declarations; do not place them on individual methods.

The two class-level phases do not mean SQL runs once for the entire test suite. If multiple test classes declare class-level scripts, each script runs according to its own class lifecycle. `ApplicationContext` caching across test classes does not turn `BEFORE_TEST_CLASS` into a once-per-context phase.

## 3. BEFORE_TEST_METHOD: preparing data before each test

This is the default and most commonly used phase. Each test method can receive a deterministic dataset before execution.

For example, file `src/test/resources/sql/insert-customer.sql`:

```sql
INSERT INTO customer (id, email, status)
VALUES (101, 'lan@example.test', 'ACTIVE');
```

Repository test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.test.context.jdbc.Sql;

import static org.assertj.core.api.Assertions.assertThat;

@JdbcTest
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    @Sql("/sql/insert-customer.sql")
    void findsCustomerByEmail() {
        var customer = customerRepository.findByEmail("lan@example.test");

        assertThat(customer).isPresent();
        assertThat(customer.orElseThrow().getStatus()).isEqualTo("ACTIVE");
    }
}
```

Because no phase is declared, Spring runs `insert-customer.sql` before `findsCustomerByEmail()`. `@JdbcTest` creates a JDBC test slice and runs tests inside a transaction rolled back after each method by default, so fixtures created in the test transaction typically do not persist after the test ends.

This phase fits when each test needs an independent dataset. If a class has multiple methods with different data, declaring `@Sql` on each method lets readers see clearly which data serves which test.

## 4. AFTER_TEST_METHOD: running SQL after each test method

`AFTER_TEST_METHOD` runs after the test method completes. This phase is commonly used to clean up data created outside the test transaction or to perform post-test SQL actions.

Example:

```java
@Test
@Sql(scripts = "/sql/insert-customer.sql")
@Sql(
        scripts = "/sql/delete-test-customer.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD
)
void findsCustomerByEmail() {
    // Exercise the repository using the inserted customer.
}
```

File `delete-test-customer.sql`:

```sql
DELETE FROM customer
WHERE email = 'lan@example.test';
```

This declaration makes the intent of preparing and cleaning up the fixture around the method clear. However, check the test's transaction before concluding that the `DELETE` statement will commit. For transactional tests, scripts in `AFTER_TEST_METHOD` typically run while the test-managed transaction is still active. If the cleanup SQL joins that transaction, it may be rolled back along with the transaction when Spring finishes the test.

This is not necessarily a problem. If the fixture was inserted inside the same test transaction and the transaction rolls back, the record disappears on its own; separate cleanup may be unnecessary. However, if data was committed independently before the test or created via `REQUIRES_NEW`, cleanup needs to run in an independent transaction so the changes are persisted.

## 5. BEFORE_TEST_CLASS: preparing once for the entire class

Since Spring Framework 6.1, you can place `@Sql` at the class level with `BEFORE_TEST_CLASS` to run scripts once before the test methods in the class.

Example creating a schema or shared reference data:

```java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@SpringBootTest
@Sql(
        scripts = {
                "/sql/create-test-schema.sql",
                "/sql/insert-reference-data.sql"
        },
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
class OrderIntegrationTests {

    @Test
    void createsOrderForExistingCustomer() {
        // Uses schema and reference data prepared once for this class.
    }

    @Test
    void listsOrdersForExistingCustomer() {
        // Uses the same class-level setup.
    }
}
```

Scripts in the `scripts` array execute in declared order, so you can place schema creation before scripts that load data depending on that schema.

`BEFORE_TEST_CLASS` fits shared base data, such as lookup tables, sample configurations, or schemas required before any method runs. Do not place per-test mutable data in this phase if methods might modify the data and affect each other.

The class-level phase runs outside any individual method's test-managed transaction, because the method's transaction has not started yet. Therefore, if the script needs a transaction, `SqlScriptsTestExecutionListener` handles it according to `@SqlConfig` and the selected transaction manager. With default configuration and a suitable transaction manager, the script can run in its own transaction and commit before methods start.

## 6. AFTER_TEST_CLASS: cleaning up data after the entire class

`AFTER_TEST_CLASS` runs once after all test methods in the class have completed. This is the appropriate place to delete shared data or remove schemas created in `BEFORE_TEST_CLASS`.

Example:

```java
@SpringBootTest
@Sql(
        scripts = "/sql/create-test-schema.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
@Sql(
        scripts = "/sql/drop-test-schema.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_CLASS,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
class OrderIntegrationTests {
    // All test methods use the schema created before the class.
}
```

File `drop-test-schema.sql` might contain:

```sql
DROP SCHEMA IF EXISTS order_test CASCADE;
```

The example assumes the test has privileges to create and drop its own schema. In real projects, ensure the script only affects schemas/databases dedicated to tests. Do not run drop scripts on a shared database containing data outside the test's scope.

`AFTER_TEST_CLASS` is useful when cleaning up class-level SQL resources. However, it does not replace managing the lifecycle of external containers or servers. If a test uses Testcontainers, let Testcontainers manage the container and use SQL phases for data/schema inside the database.

## 7. Declaration scope: method-level vs. class-level

`@Sql` can be declared at the class level or method level. Distinguish declaration scope from execution phase:

- Class-level `@Sql` with the default `BEFORE_TEST_METHOD` phase applies the script before each test method in the class.
- Class-level `@Sql` with `BEFORE_TEST_CLASS` runs only once before the class's methods.
- Method-level `@Sql` runs before that method by default.
- Method-level `@Sql` can choose `AFTER_TEST_METHOD` to run after the method.

Example of a class-level fixture executed before each method:

```java
@SpringBootTest
@Sql("/sql/common-reference-data.sql")
class CatalogIntegrationTests {

    @Test
    void findsCategory() {
    }

    @Test
    void listsCategories() {
    }
}
```

Because the default phase is `BEFORE_TEST_METHOD`, `common-reference-data.sql` runs before each method, not just once for the class. If the data only needs to be loaded once, specify `BEFORE_TEST_CLASS`.

### 7.1. Coexisting class-level and method-level declarations

Spring Test provides `@SqlMergeMode` to decide how class-level and method-level `@Sql` declarations combine. By default, method-level `@Sql` uses `OVERRIDE` mode, meaning a method-level declaration replaces the class-level declaration according to Spring Test's merge rules.

If you want the method-level script to supplement the class-level script, you can use:

```java
import org.springframework.test.context.jdbc.SqlMergeMode;

@SpringBootTest
@Sql("/sql/common-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CatalogIntegrationTests {

    @Test
    @Sql("/sql/insert-special-category.sql")
    void findsSpecialCategory() {
    }
}
```

In `MERGE` mode, class-level and method-level SQL configurations are combined according to Spring Test's rules. This is useful when each method needs its own data while still needing a shared fixture. Specify phases explicitly if scripts need to run at different times.

When using `BEFORE_TEST_CLASS` or `AFTER_TEST_CLASS` alongside method-level SQL, inspect the metadata and phase of each declaration to determine accurately which scripts run once and which run around each method. If a test depends on complex setup/cleanup ordering, separate scripts and write phases explicitly instead of relying on defaults.

## 8. Multiple scripts in one @Sql and execution order

The `scripts` attribute takes an array of resources. Multiple scripts can be declared in one annotation:

```java
@Sql(
        scripts = {
                "/sql/01-create-schema.sql",
                "/sql/02-insert-users.sql",
                "/sql/03-insert-orders.sql"
        },
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
class OrderRepositoryTests {
}
```

This style clarifies dependency ordering: create the schema first, load users, and then load orders. If a later script references data created by an earlier script, the order is part of the fixture and must be stated explicitly.

`@Sql` is a repeatable annotation, so it can be declared multiple times on the same class or method. `@SqlGroup` can also be used to group multiple declarations, especially when a clear annotation structure is desired or for compatibility with nested annotation declarations.

Example with `@SqlGroup`:

```java
@SqlGroup({
        @Sql(
                scripts = "/sql/insert-customer.sql",
                executionPhase = ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "/sql/delete-customer.sql",
                executionPhase = ExecutionPhase.AFTER_TEST_METHOD
        )
})
class CustomerSqlTests {
}
```

With modern Java, you can use multiple `@Sql` annotations directly because the annotation is repeatable. Choose the style that lets readers see the order and phase most clearly.

## 9. Using statements instead of script files

In addition to `scripts`, `@Sql` has a `statements` attribute to declare short SQL directly in the annotation:

```java
@Test
@Sql(
        statements = {
                "INSERT INTO customer(id, email) VALUES (201, 'minh@example.test')"
        },
        executionPhase = ExecutionPhase.BEFORE_TEST_METHOD
)
void findsCustomer() {
}
```

You can use `statements` in a later phase to delete a record:

```java
@Sql(
        statements = "DELETE FROM customer WHERE id = 201",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD
)
```

`statements` suits short SQL that rarely changes. For long fixtures, many statements, reused data, or scripts with comments and complex structure, `.sql` files are usually easier to read and maintain.

Do not put sensitive data or environment-dependent values in shared test scripts. Use synthetic data, clear IDs, and dedicated test databases to avoid affecting real data.

## 10. SQL script transactions and @SqlConfig

Execution phase determines when a script runs; transaction mode determines how the script participates in or creates a transaction. `@SqlConfig` lets you configure `DataSource`, transaction manager, encoding, comment prefix, separator, and transaction mode.

The two transaction modes to understand are:

- `INFERRED`: Spring infers how to run based on the current transaction and transaction manager. If an active transaction exists, the script can join that transaction; otherwise, Spring uses a suitable transaction manager to run the script in its own transaction when available.
- `ISOLATED`: the script runs in an independent transaction with `REQUIRES_NEW` propagation and commits that transaction upon completion.

Unless configured otherwise, Spring Test uses the default transaction behavior corresponding to `INFERRED`. You can configure it individually for a script:

```java
@Sql(
        scripts = "/sql/insert-reference-data.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
class OrderIntegrationTests {
}
```

Here, the script runs in an independent transaction and commits before the test methods start. The test methods can use the committed reference data.

### 10.1. Fixture joining the test transaction

For a test method with `@Transactional`, a `BEFORE_TEST_METHOD` script using `INFERRED` transaction mode typically joins the active test-managed transaction. If the test ends with a rollback, the fixture rolls back as well.

This is usually a good choice for data specific to a single method:

```java
@DataJpaTest
class CustomerRepositoryTests {

    @Test
    @Sql("/sql/insert-customer.sql")
    void readsCustomer() {
        // Setup and test participate in the test-managed transaction.
    }
}
```

There is no need to add a cleanup script just to delete data created inside the same transaction if all operations participate in that transaction and the test rolls back as expected.

### 10.2. When is ISOLATED needed?

Use `ISOLATED` when data must be committed independently of the test's transaction, or when cleanup must persist after the test transaction rolls back. For instance, a class-level script creating reference data that must be committed before methods run; or a test invoking code that uses `REQUIRES_NEW`, creating data that must be cleaned up by an independent transaction.

Example of independent cleanup:

```java
@Sql(
        scripts = "/sql/delete-committed-fixture.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

The cleanup script runs in its own transaction and commits. Use this when the record to delete has already been committed and is visible from an independent transaction. If the record only exists inside an uncommitted test transaction, another independent transaction cannot see it; rolling back the test transaction will remove that record itself.

### 10.3. Specifying DataSource and transaction manager

If the context has multiple `DataSource`s or multiple transaction managers, Spring may not be able to infer which component to use. Specify them in `@SqlConfig`:

```java
@Sql(
        scripts = "/sql/seed-reporting-data.sql",
        config = @SqlConfig(
                dataSource = "reportingDataSource",
                transactionManager = "reportingTransactionManager",
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

Bean names must match the configuration in the application context. Using the wrong datasource or transaction manager can cause the script to run against a different database than the one the repository reads from.

## 11. Combining phases with @Transactional

To understand outcomes, look at the ordering between test-managed transactions and the SQL listener.

For a standard transactional test, Spring Test starts a transaction for the method and runs `BEFORE_TEST_METHOD` scripts according to the configured transaction mode. After the test method, `AFTER_TEST_METHOD` scripts are processed during the method-end lifecycle; with `INFERRED`, they can join the still-active test transaction. The transactional listener then completes the transaction according to the test's commit/rollback policy.

General diagram:

```text
BEFORE_TEST_METHOD
       |
       v
Test-managed transaction active (if @Transactional)
       |
       v
@Sql BEFORE_TEST_METHOD
       |
       v
JUnit test method and test callbacks
       |
       v
@Sql AFTER_TEST_METHOD
       |
       v
Commit or rollback test-managed transaction
```

The diagram shows the typical flow when SQL scripts use `INFERRED` transaction mode and the test has a Spring-managed transaction. When using `ISOLATED`, the script runs in an independent transaction; it does not roll back with the test transaction.

Class-level `BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` run at the class lifecycle level, outside any individual method's test transaction. Therefore, data created in a class phase can persist across methods if the script commits. Corresponding cleanup in the class phase or another data cleanup mechanism is required.

Do not assume `AFTER_TEST_METHOD` always runs after rollback. An `AFTER_TEST_METHOD` script is part of the Spring Test lifecycle; the transaction listener determines when the test-managed transaction ends. If the goal is to verify data after commit/rollback, use the `@AfterTransaction` callback or a suitable new transaction instead of relying solely on the SQL after-method phase.

## 12. Choosing a phase by testing goal

| Goal | Suitable phase | Reason |
|---|---|---|
| Load records specific to a method | `BEFORE_TEST_METHOD` | Each method receives its fixture before running |
| Delete committed data created by a method | `AFTER_TEST_METHOD` | Immediate cleanup after each method |
| Create shared schema or tables in a class | `BEFORE_TEST_CLASS` | Runs once instead of repeating before each method |
| Load shared immutable lookup data | `BEFORE_TEST_CLASS` | Methods share a single base dataset |
| Drop schema or base data after the class | `AFTER_TEST_CLASS` | Cleans up once after the class finishes |
| Verify state right after test transaction commit/rollback | `@AfterTransaction` callback or a new transaction | After-method SQL may still participate in the test transaction |

For example, a repository test usually only needs `BEFORE_TEST_METHOD` to insert fixtures with default rollback. An integration test suite needing its own schema for the entire class can use `BEFORE_TEST_CLASS` to create the schema, then `AFTER_TEST_CLASS` to drop it. A test verifying data committed by `REQUIRES_NEW` may need `AFTER_TEST_METHOD` with `ISOLATED` for cleanup.

## 13. Common mistakes when choosing ExecutionPhase

### 13.1. Thinking class-level @Sql always runs once

Class-level `@Sql` still defaults to `BEFORE_TEST_METHOD`, so the script may run before every method. If you only want it to run once, set `executionPhase = BEFORE_TEST_CLASS`.

### 13.2. Using class-level phases on method-level annotations

`BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` are meant for class-level `@Sql` declarations. Placing them on a method is an invalid configuration. Move the annotation to the class or use a method-level phase.

### 13.3. Using AFTER_TEST_METHOD to inspect after rollback

An `AFTER_TEST_METHOD` script does not automatically run after the test transaction has rolled back. With `INFERRED`, the script can join the active transaction and roll back along with the test. Use `@AfterTransaction` or an independent transaction if you need to verify post-rollback state.

### 13.4. Cleanup getting rolled back with the test

If cleanup SQL joins the test transaction, delete statements can be rolled back. This does not affect fixtures in the same transaction, but it fails to clean up independently committed data. Consider `ISOLATED` when cleanup must commit.

### 13.5. Using ISOLATED for every script

Every isolated transaction script can commit independently and leave data behind even when a test fails. This increases cleanup overhead and can cause cross-test interference. Only use `ISOLATED` when a separate transaction is required.

### 13.6. Loading shared data before every method

If a class-level script inserts a record with a fixed key and runs before each method, the second method may hit a duplicate key if the first method committed or data is not in the same transaction. Decide clearly whether that data should be created once in a class phase or rolled back individually per method.

### 13.7. Selecting the wrong DataSource

Multi-datasource applications can cause SQL scripts to run on a different database than the repository. Use `@SqlConfig(dataSource = ...)` and `transactionManager = ...` when explicit selection is needed.

### 13.8. Incorrect resource paths

Scripts are loaded from the classpath or specified location. For resources in `src/test/resources/sql`, `/sql/file-name.sql` is commonly used. Check the file name, casing, and test runtime classpath if Spring reports the script cannot be found.

### 13.9. Confusing class phase with context caching

Spring may cache the `ApplicationContext`, but `BEFORE_TEST_CLASS` remains a per-test-class phase. Do not treat context caching as a guarantee that a script runs only once for the entire suite.

## 14. SQL fixture design workflow

When designing scripts for a test class, determine the data lifecycle first:

1. **Is the data needed for one method or the whole class?** If only for one method, use `BEFORE_TEST_METHOD`; if shared, consider `BEFORE_TEST_CLASS`.
2. **Does the data need an independent commit?** If the fixture must exist outside the test transaction, consider `ISOLATED`; otherwise, leave `INFERRED` to join the current transaction.
3. **Does the test have a transaction?** Check `@Transactional` or test slice annotations such as `@JdbcTest`/`@DataJpaTest`.
4. **Is explicit cleanup required?** Data in the same transaction is usually rolled back; committed data or data created outside the transaction needs separate cleanup.
5. **Where does cleanup run?** Use `AFTER_TEST_METHOD` for per-method data, `AFTER_TEST_CLASS` for class-level shared data. Use `ISOLATED` if cleanup must commit independently.
6. **Are there multiple datasources?** Specify the datasource and transaction manager via `@SqlConfig` when Spring cannot infer accurately.
7. **Do both class and method have multiple SQL declarations?** Check `@SqlMergeMode` to see whether method declarations override or merge with the class.
8. **Verify state at the right time.** If checking after commit/rollback is needed, use callbacks or a new transaction; do not check solely inside the test method itself.

A stable test suite typically uses method-level fixtures inside test transactions with default rollback. Only promote data to a class phase when there is genuinely shared data or schema preparation is needed. Cleanup scripts should reflect where data was created and whether the transaction committed.

## 15. Combined example: class-level schema and method-level fixtures

A test class can combine class-level setup with method-specific data:

```java
@SpringBootTest
@Sql(
        scripts = "/sql/create-order-test-schema.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
@Sql(
        scripts = "/sql/drop-order-test-schema.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_CLASS,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
class OrderRepositoryIntegrationTests {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    @Sql("/sql/insert-pending-order.sql")
    void findsPendingOrder() {
        assertThat(orderRepository.findByStatus("PENDING")).isNotEmpty();
    }

    @Test
    @Sql("/sql/insert-completed-order.sql")
    void findsCompletedOrder() {
        assertThat(orderRepository.findByStatus("COMPLETED")).isNotEmpty();
    }
}
```

The example illustrates splitting phases: the schema is created once before the class; each method loads its own fixture before running; the schema is cleaned up after the class. In real projects, adjust transaction mode, schema name, and datasource creation according to the test database in use. If methods use test-managed transaction rollback, method-level fixtures can roll back automatically. If the schema is created in a separate transaction and must be dropped at the end, class-level cleanup must run in an appropriate transaction.

`ExecutionPhase` helps place SQL fixtures at the exact point in the test lifecycle. Use `BEFORE_TEST_METHOD` and `AFTER_TEST_METHOD` for per-method data; use `BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` to prepare or clean up shared SQL resources within a class. Combine phases with `@SqlConfig` and understand `INFERRED`/`ISOLATED` transaction modes to know whether data is rolled back or committed. When you need to verify state after the test transaction ends, use `@AfterTransaction` or a new transaction instead of assuming after-method SQL always runs after rollback.
