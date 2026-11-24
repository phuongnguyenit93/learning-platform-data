# @SqlMergeMode When Combining Class and Method Configurations

Spring TestContext Framework lets you declare SQL scripts using `@Sql` at the test class or test method level. Class-level configuration typically holds shared base data for multiple tests; method-level configuration adds specific data for one scenario. When both levels declare `@Sql`, Spring needs a rule to decide which scripts execute. `@SqlMergeMode` provides that rule.

By default, method-level `@Sql` configuration **overrides** class-level `@Sql` configuration for the corresponding method. If you want to keep the class's shared script and also run the method's own script, use `@SqlMergeMode(MERGE)`. When merging, class-level scripts execute before method-level scripts within the same phase.

## 1. Class-level and method-level @Sql

`@Sql` belongs to the `org.springframework.test.context.jdbc` package. This annotation instructs Spring to execute one or more SQL scripts during the test lifecycle. It can be used on a class to apply shared data across methods, or on a method to prepare scenario-specific data.

`@SqlMergeMode` also belongs to this package and was introduced in Spring Framework 5.2. When `@Sql` is declared at the class level, the class-level script applies to each test method in the class unless a method-level declaration replaces it under the active merge mode.

Class-level declaration example:

~~~java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
class InventoryRepositoryTest {
    // All test methods receive the class-level SQL configuration,
    // unless a method has its own @Sql and the merge rule does not combine them.
}
~~~

Method-level declaration example:

~~~java
@Test
@Sql("/sql/inventory-with-zero-stock.sql")
void rejectsReservationWhenStockIsEmpty() {
    // Test the zero-stock case.
}
~~~

When only one of the two levels declares `@Sql`, Spring runs the scripts at that level. When both class and method declare it, the result depends on the merge mode. Understanding this is essential to avoid accidentally running a test without base data or with unexpected extra data.

`@Sql` can declare `scripts`, `statements`, or both. Example:

~~~java
@Sql(
        scripts = "/sql/clear-inventory.sql",
        statements = "INSERT INTO inventory(sku, available) VALUES ('SKU-01', 8)"
)
~~~

Scripts and statements are executed by `SqlScriptsTestExecutionListener` of the Spring TestContext Framework. The default phase is `BEFORE_TEST_METHOD`, meaning SQL runs before each test method body.

## 2. Default mode: OVERRIDE

If `@SqlMergeMode` is not declared, Spring uses `OVERRIDE` mode. When a test method has its own `@Sql`, class-level `@Sql` declarations are not applied to that method. Methods without their own `@Sql` still use the class-level configuration.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
class InventoryRepositoryTest {
    @Test
    void findsAnExistingItem() {
        // Runs inventory-baseline.sql before the test.
    }

    @Test
    @Sql("/sql/inventory-with-zero-stock.sql")
    void rejectsReservationWhenStockIsEmpty() {
        // Runs inventory-with-zero-stock.sql.
        // Class-level inventory-baseline.sql is overridden for this method.
    }
}
~~~

This rule completely overrides all class-level `@Sql` declarations within the scope of that method. Spring does not automatically treat the method script as an addition to the class script. Therefore, if `inventory-baseline.sql` creates mandatory reference data while the method only declares a script for one specific record, the method may run missing base data.

You can write the default mode explicitly so readers do not have to infer it:

~~~java
import org.springframework.test.context.jdbc.SqlMergeMode;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.OVERRIDE)
class InventoryRepositoryTest {
    // Methods with @Sql will replace the class-level @Sql declaration.
}
~~~

Normally, declaring `OVERRIDE` is unnecessary since it is already the default. Writing it explicitly can be helpful in a test group with varying merge conventions, or when a method deliberately reverts from a class's merge behavior back to override.

## 3. Using MERGE to combine class and method scripts

`@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)` instructs Spring to combine class-level and method-level `@Sql` declarations. Within the same execution phase, class-level scripts run first, followed by method-level scripts.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class InventoryRepositoryMergeTest {
    @Test
    void findsAnExistingItem() {
        // Runs the class-level baseline script.
    }

    @Test
    @Sql("/sql/inventory-with-zero-stock.sql")
    void rejectsReservationWhenStockIsEmpty() {
        // Runs baseline first, then runs the method's zero-stock script.
    }
}
~~~

For the `rejectsReservationWhenStockIsEmpty()` method, the order is:

1. `inventory-baseline.sql` declared at the class level.
2. `inventory-with-zero-stock.sql` declared at the method level.
3. Spring runs the test method.

As a result, the class script can set up shared reference data, while the method script only needs to add or adjust data for the specific scenario.

### Illustration with SQL content

Suppose the application has an `inventory` table and a `warehouse` table. The class-level script sets up the default warehouse and a basic item:

~~~sql
-- /sql/inventory-baseline.sql
DELETE FROM inventory;
DELETE FROM warehouse;

INSERT INTO warehouse(id, name)
VALUES (1, 'Main warehouse');

INSERT INTO inventory(sku, warehouse_id, available)
VALUES ('SKU-01', 1, 8);
~~~

The method-level script adds the out-of-stock scenario:

~~~sql
-- /sql/inventory-with-zero-stock.sql
INSERT INTO inventory(sku, warehouse_id, available)
VALUES ('SKU-EMPTY', 1, 0);
~~~

With `MERGE` mode, the test method can use the default warehouse, item `SKU-01`, and item `SKU-EMPTY`. The method script executes after the class script, so it can rely on data already created by the class script.

In practice, SQL statements must match your database engine and project schema. If tests run multiple times, the class-level script needs a safe data cleanup strategy, such as deleting by test key or using transaction rollback. Avoid assuming an unconditional `DELETE` is safe when multiple tests or processes share the database.

## 4. Placing @SqlMergeMode at the class level

Placing `@SqlMergeMode(MERGE)` on the class is a common pattern when most methods need the class's base data and then add their own data:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CustomerRepositoryTest {
    @Test
    @Sql("/sql/customer-active.sql")
    void findsAnActiveCustomer() {
        // reference-data.sql runs before customer-active.sql.
    }

    @Test
    @Sql("/sql/customer-suspended.sql")
    void findsASuspendedCustomer() {
        // reference-data.sql runs before customer-suspended.sql.
    }

    @Test
    void canReadReferenceData() {
        // Only the class-level script runs since the method declares no @Sql of its own.
    }
}
~~~

When the class uses `MERGE`, methods without `@Sql` still receive the class-level script as normal. Methods with `@Sql` receive both levels. This fits well when the shared script truly represents base data needed by every test in the class.

Do not enable `MERGE` merely because you want all scripts to run. Verify whether class-level data is valid for every method. If a method needs a completely clean/independent database, additionally running base data can make the test harder to understand or cause key collisions.

## 5. Overriding MERGE mode on a single method

A class may use `MERGE` as its default while one method needs an isolated dataset. Place `@SqlMergeMode(OVERRIDE)` on that method to revert it to override behavior.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/customer-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CustomerRepositoryTest {
    @Test
    @Sql("/sql/customer-active.sql")
    void findsActiveCustomer() {
        // Runs reference data, then active customer.
    }

    @Test
    @Sql("/sql/customer-isolated-case.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.OVERRIDE)
    void runsWithAnIsolatedDataset() {
        // Only runs customer-isolated-case.sql.
        // Class-level script is overridden for this method.
    }
}
~~~

The method-level setting takes precedence for that method. This allows the class to maintain a common convention while providing a clear exception for tests that require an independent dataset.

Conversely, if the class omits `@SqlMergeMode` or uses `OVERRIDE`, a single method can opt into `MERGE`:

~~~java
@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/customer-reference-data.sql")
class CustomerRepositoryOverrideByDefaultTest {
    @Test
    @Sql("/sql/customer-active.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
    void mergesClassAndMethodScriptsForThisMethod() {
        // Runs customer-reference-data.sql first,
        // then customer-active.sql.
    }
}
~~~

Thus, `@SqlMergeMode` can be declared at the class level to set the class default, or at the method level to decide how to combine for a specific method. Method-level configuration takes precedence within that method's scope.

## 6. Comparison table: OVERRIDE vs. MERGE

| Scenario | OVERRIDE (default) | MERGE |
|---|---|---|
| Only class has @Sql | Runs class script | Runs class script |
| Only method has @Sql | Runs method script | Runs method script |
| Both class and method have @Sql | Runs method declaration; ignores class declaration for that method | Runs both levels |
| Order in the same phase | Only the selected declaration | Class first, method second |
| Method has @SqlMergeMode(OVERRIDE) | Keeps override | Overrides the class's MERGE mode |
| Method has @SqlMergeMode(MERGE) | Combines both levels | Keeps merge mode |

You can remember the rules like this:

- `OVERRIDE`: a method with its own `@Sql` replaces the class configuration for that method.
- `MERGE`: a method with its own `@Sql` appends to the class configuration for that method.
- Method without its own `@Sql`: the class script still applies, regardless of merge mode.
- Method-level `@SqlMergeMode` determines the handling for that specific method if declared.

## 7. @SqlMergeMode and executionPhase

`@Sql` has an `executionPhase` attribute to specify when the script runs:

- `BEFORE_TEST_METHOD`: before each test method; this is the default value.
- `AFTER_TEST_METHOD`: after each test method.

`@SqlMergeMode` decides whether class-level and method-level declarations are combined. `executionPhase` decides when each declaration executes. These two settings answer two different questions.

For example, the class prepares data before the test, while the method runs a cleanup script after the test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql(
        scripts = "/sql/inventory-baseline.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class InventoryLifecycleTest {
    @Test
    @Sql(
            scripts = "/sql/inventory-after-test.sql",
            executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
    void performsAnInventoryOperation() {
        // Baseline SQL runs before the test method.
        // Cleanup SQL runs after the test method.
    }
}
~~~

Class and method declarations are combined under `MERGE` mode, yet each script still runs in its own phase. `BEFORE_TEST_METHOD` scripts are processed in the pre-method callback; `AFTER_TEST_METHOD` scripts are processed in the post-method callback.

If both class and method declare scripts in the same phase, under `MERGE`, class scripts run before method scripts. If they belong to two different phases, the phase governs execution timing; do not infer that all class scripts always run before all method scripts regardless of phase.

Multiple `@Sql` annotations can be declared at the same level by repeating the annotation:

~~~java
@Sql("/sql/clear-inventory.sql")
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class MultipleSqlScriptsTest {
    @Test
    @Sql("/sql/inventory-special-case.sql")
    void usesSeveralScripts() {
        // Same-level declarations follow @Sql rules
        // and the method-level declaration is merged with the class level.
    }
}
~~~

`@Sql` is a repeatable annotation. Multiple declarations can be used to separate data clearing, creating reference data, and adding scenario data. Splitting scripts should reflect meaningful preparation steps and should not make dependency ordering hard to trace.

## 8. Distinguishing @SqlMergeMode from @SqlConfig

`@SqlMergeMode` controls merging of class-level and method-level `@Sql` declarations. `@SqlConfig` configures how SQL is executed, such as choosing datasource, transaction manager, transaction mode, encoding, comment prefix, or separator.

The two annotations do not replace each other:

| Annotation | Question answered |
|---|---|
| @SqlMergeMode | Are class-level and method-level scripts combined, or does the method override the class? |
| @SqlConfig | Which datasource, transaction, and SQL parsing rules does Spring use to execute the script? |

SQL configuration example:

~~~java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;

@Sql(
        scripts = "/sql/inventory-baseline.sql",
        config = @SqlConfig(
                dataSource = "testDataSource",
                transactionManager = "testTransactionManager",
                encoding = "UTF-8"
        )
)
~~~

Within a test class, `@SqlMergeMode(MERGE)` can be combined with `@SqlConfig`. One annotation determines which set of scripts applies; the other determines how scripts are executed.

If a method needs SQL configuration different from the class, declare `config` on the method's `@Sql` as needed. Do not expect `@SqlMergeMode` to automatically merge or override individual `@SqlConfig` attributes; that is a separate configuration mechanism.

## 9. Interacting with test transactions

SQL scripts typically run within a transaction context managed by Spring TestContext. If a test method has `@Transactional`, Spring typically starts a test-managed transaction before the test runs and rolls back after the method by default. `SqlScriptsTestExecutionListener` executes scripts in the corresponding callbacks, coordinating with the transaction listener in TestContext order.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Transactional
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class TransactionalInventoryTest {
    @Test
    @Sql("/sql/inventory-special-case.sql")
    void readsTheMergedDataset() {
        // Class and method scripts run in the test-managed transaction
        // context under the appropriate default configuration.
    }
}
~~~

Under standard transaction configuration, setup data joins the test transaction and is rolled back when the test completes. However, exact behavior depends on the transaction manager, datasource, and `@SqlConfig`. If a script is configured to run in an independent transaction, or application code opens a separate transaction, data may not reside in the transaction that the test rolls back.

`@SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)` instructs the script to run in a separate transaction and commit it upon completion. This mode can be useful when setup data must exist outside the test-managed transaction, but requires careful consideration because data may remain after the test and affect subsequent runs.

Do not use `ISOLATED` just to avoid understanding rollback mechanics. First determine whether the data should live within the test scope or must exist independently. Using the default transaction for fixtures that should roll back is usually simpler.

## 10. Notes on data preparation and cleanup order

When using `MERGE`, class-level SQL is combined with method-level SQL. However, which script runs first also depends on `executionPhase` and declaration order within the same group. Design scripts in readable steps:

1. Clear or prepare base data within the test's scope.
2. Create reference records needed by the scenario.
3. Add data specific to the test method.
4. Run assertions in the test.
5. Clean up data if cleanup is not handled by transaction rollback.

If a class-level script runs before every method, the data it creates must suit all methods using that configuration. If a method needs a completely empty database, you can use `OVERRIDE` and provide a dedicated script, or organize setup by phase to clarify intent.

Avoid having a class-level script create a record with a fixed key while a method-level script inserts a duplicate key. In `MERGE` mode, both scripts run; key conflicts are a natural consequence if the data is not designed to complement each other.

Strategies to reduce conflicts:

- Use distinct keys for base data and scenario data.
- Use `UPDATE` when the goal is to adjust a base record already created.
- Only use `DELETE` by controlled test key or dataset.
- Use transaction rollback to isolate data when appropriate.
- Choose `OVERRIDE` when a method must replace the entire class-level fixture.

## 11. Combined example: class using MERGE, method with an exception

Suppose a customer repository test has shared reference data, while one method needs to run on an independent dataset to test the duplicate-email case.

Class-level script:

~~~sql
-- /sql/customer-reference-data.sql
DELETE FROM customer;

INSERT INTO customer(id, email, status)
VALUES (1, 'active@example.test', 'ACTIVE');

INSERT INTO customer(id, email, status)
VALUES (2, 'suspended@example.test', 'SUSPENDED');
~~~

Supplementary script for a method:

~~~sql
-- /sql/customer-duplicate-email.sql
INSERT INTO customer(id, email, status)
VALUES (3, 'duplicate@example.test', 'ACTIVE');

INSERT INTO customer(id, email, status)
VALUES (4, 'duplicate@example.test', 'SUSPENDED');
~~~

Isolated script:

~~~sql
-- /sql/customer-isolated-empty-case.sql
DELETE FROM customer;
~~~

Test class:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(CustomerRepositoryTestConfig.class)
@Sql("/sql/customer-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CustomerRepositoryMergeTest {
    @Test
    @Sql("/sql/customer-duplicate-email.sql")
    void findsAllCustomersWithTheSameEmail() {
        // reference data is created first, then two duplicate-email records are added.
    }

    @Test
    void findsTheActiveCustomer() {
        // Uses only class-level reference data.
    }

    @Test
    @Sql("/sql/customer-isolated-empty-case.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.OVERRIDE)
    void returnsNoCustomerForAnEmptyDatabase() {
        // Only runs the method script, skipping reference data.
    }
}
~~~

The first two methods use `MERGE`: the first adds two duplicate-email customers, while the second uses only the reference data. The final method sets `OVERRIDE` to skip the class's base data and only run the script for an empty database.

This example demonstrates placing a shared convention at the class level and declaring an exception directly at the method level. Readers of the test can immediately tell which method inherits fixtures, which adds fixtures, and which completely replaces the shared fixture.

## 12. Common mistakes

### Thinking method-level @Sql always supplements class scripts

This is the most common misconception. The default is `OVERRIDE`, so a method with its own `@Sql` will not run class-level `@Sql` declarations. If combining is needed, declare `@SqlMergeMode(MERGE)`.

### Using MERGE while the method script inserts duplicate keys

In merge mode, both class and method scripts run. If both insert the same primary key or unique value, the database may report a constraint error. Check whether base data and specific data complement each other.

### Setting MERGE but forgetting the test context

`@SqlMergeMode` is a Spring TestContext annotation. The test must integrate with the appropriate Spring TestContext so the listener processes `@Sql` and merge mode. Running plain JUnit tests without Spring Extension/TestContext will not execute these annotations automatically.

### Using the wrong annotation package

`@Sql` and `@SqlMergeMode` belong to `org.springframework.test.context.jdbc`. Check imports when the IDE auto-completes annotations or when the project includes other testing libraries.

### Thinking MERGE changes executionPhase

`MERGE` only controls combining declarations. It does not turn `BEFORE_TEST_METHOD` into `AFTER_TEST_METHOD` or vice versa. Inspect the `executionPhase` of each declaration.

### Thinking @SqlConfig is merged by @SqlMergeMode

`@SqlMergeMode` is not a mechanism for merging SQL configuration attributes. It decides which level's script declarations apply. Datasource, transaction manager, encoding, and transaction mode are still controlled by `@SqlConfig`.

### Using a cleanup script yet data persists

Check transaction mode, test-managed transaction, which phase the cleanup script is in, and whether the script actually ran. If data was committed in an independent transaction, test rollback will not delete that data.

### Using @DirtiesContext to handle SQL data

`@DirtiesContext` evicts the `ApplicationContext` from cache; it is not a command to delete database rows. Use SQL cleanup or transaction rollback for data; only use `@DirtiesContext` when the context itself was mutated and cannot be safely reused.

## 13. Choosing the right mode

| Need | Configuration approach |
|---|---|
| Method needs to completely replace class fixture | Use default OVERRIDE or declare explicitly |
| Every method needs base data plus its own data | Place @SqlMergeMode(MERGE) at class level |
| One method in a MERGE class needs an independent fixture | Place @SqlMergeMode(OVERRIDE) on the method |
| Class defaults to OVERRIDE but one method needs combining | Place @SqlMergeMode(MERGE) on the method |
| Script runs before the test | `executionPhase = BEFORE_TEST_METHOD` or use default |
| Script runs after the test | `executionPhase = AFTER_TEST_METHOD` |
| Need a separate datasource or transaction | Configure @SqlConfig accordingly |

A practical way to choose is to start from the data the test requires:

- If a method needs a single independent dataset, `OVERRIDE` makes clear that the method fixture replaces the class fixture.
- If a class has reference data needed by all methods, `MERGE` lets each method declare only the extra data.
- If only a few methods need merging, keep the class default and enable `MERGE` specifically on those methods.
- If data must be cleaned up after tests, clarify whether transactions can roll it back or whether an `AFTER_TEST_METHOD` script is needed.

## 14. Principles to remember

- The default of `@SqlMergeMode` is `OVERRIDE`.
- With `OVERRIDE`, when a method has `@Sql`, class-level `@Sql` declarations do not apply to that method.
- With `MERGE`, both class and method scripts execute; class scripts run before method scripts within the same phase.
- `@SqlMergeMode` can be placed at the class level to apply to the whole class, or at the method level to override the class's mode.
- Methods without their own `@Sql` still use class-level scripts.
- `executionPhase` decides whether a script runs before or after the test method; `@SqlMergeMode` does not change phase.
- `@SqlConfig` configures how scripts execute, independent of merge rules.
- Check primary keys, unique constraints, and base data when using `MERGE` to avoid script conflicts.
- Understand transaction mode and cleanup to know whether data rolls back or persists after tests.
- Do not use `@DirtiesContext` as a substitute for database data cleanup.

`@SqlMergeMode` helps organize SQL fixtures across two levels while keeping clear control over each test's data. `OVERRIDE` fits when a method needs its own dataset; `MERGE` fits when a method needs to inherit class base data and supplement a specific scenario. Placing the mode at the right scope and understanding script ordering makes database tests readable, low-conflict, and capable of purposefully reusing shared fixtures.

## References

- [Spring Framework Reference — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html)
- [Spring Framework Javadoc — SqlMergeMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlMergeMode.html)
- [Spring Framework Javadoc — Sql](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/Sql.html)
- [Spring Framework Javadoc — SqlConfig](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.html)
