# @SqlGroup and Multiple Script Sets

Spring Framework Testing lets you load SQL data before or after tests run using the `@Sql` annotation. When a scenario requires multiple scripts, or a test class needs multiple datasets for different purposes, you can declare multiple `@Sql` annotations and group them with `@SqlGroup`.

`@SqlGroup` is a container annotation holding a set of `@Sql` declarations. It helps organize scripts across stages of a test, such as preparing schemas, loading base data, creating data specific to a test method, and cleaning up data after verification. It is important to distinguish grouping annotations from grouping transactions: `@SqlGroup` organizes script declarations, whereas each declaration's transaction is determined by Spring Test configuration.

## 1. What is @Sql used for?

`@Sql` instructs Spring to execute one or more SQL scripts at a point in the test lifecycle. The annotation can be placed on a test class or test method.

Example loading data before a test method:

```java
@SpringBootTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    @Sql("/sql/customer/insert-customer.sql")
    void findsCustomerByEmail() {
        assertTrue(
                customerRepository.findByEmail("lan@example.test").isPresent()
        );
    }
}
```

Spring executes the script before the test method executes. The script can create records that the repository needs to perform queries.

Scripts can be declared explicitly via the `scripts` attribute:

```java
@Sql(scripts = "classpath:/sql/customer/insert-customer.sql")
```

The `value` attribute is an alias for `scripts`, so the following two forms have the same meaning:

```java
@Sql("/sql/customer/insert-customer.sql")
@Sql(scripts = "/sql/customer/insert-customer.sql")
```

A single `@Sql` can accept multiple script paths:

```java
@Sql(scripts = {
        "classpath:/sql/common/insert-country.sql",
        "classpath:/sql/customer/insert-customer.sql",
        "classpath:/sql/customer/insert-address.sql"
})
```

Scripts in the list execute in declared order. This is useful when a later script depends on data or tables created by an earlier script.

## 2. What is @SqlGroup?

`@SqlGroup` is a container annotation used to group multiple `@Sql` declarations on the same class or method.

Example:

```java
@SpringBootTest
class OrderRepositoryTest {

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-customer.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order-line.sql")
    })
    void findsOrderWithLines() {
        // Verify repository
    }
}
```

The three `@Sql` declarations form a group of scripts preparing data. Spring processes each declaration in order, and each declaration can have its own configuration.

In modern Java, `@Sql` is a repeatable annotation, so multiple `@Sql` annotations can be declared directly on the same element. `@SqlGroup` provides an explicit style via a container annotation, useful when you want to clearly express a script group or need compatibility with container-based annotation processing.

The two styles:

```java
@Sql(scripts = "classpath:/sql/common/insert-customer.sql")
@Sql(scripts = "classpath:/sql/common/insert-address.sql")
class CustomerRepositoryTest {
}
```

and:

```java
@SqlGroup({
        @Sql(scripts = "classpath:/sql/common/insert-customer.sql"),
        @Sql(scripts = "classpath:/sql/common/insert-address.sql")
})
class CustomerRepositoryTest {
}
```

both express multiple `@Sql` declarations. Choose one consistent style in your project so readers easily recognize how scripts are organized.

## 3. Grouping multiple scripts by purpose

A group of scripts is usually easier to understand when each file handles a specific piece of data. For example, an order test might need:

| Script | Role |
|---|---|
| `schema.sql` | Create table structures if the test manages the schema itself |
| `reference-data.sql` | Load shared lookup data |
| `insert-customer.sql` | Create the customer for the scenario |
| `insert-order.sql` | Create the order |
| `insert-order-lines.sql` | Create the order line items |
| `cleanup-order.sql` | Delete the scenario's data |

You can group the data-preparation scripts inside an `@SqlGroup`:

```java
@Test
@SqlGroup({
        @Sql(scripts = "classpath:/sql/order/insert-customer.sql"),
        @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
        @Sql(scripts = "classpath:/sql/order/insert-order-lines.sql")
})
void loadsOrderDetails() {
    // ...
}
```

File splitting should reflect data relationships. If `insert-order.sql` references customer, the script creating customer must run first. If order lines have a foreign key to order, the script creating order must run before the script creating lines.

Do not split into too many tiny files if doing so forces readers to trace a long chain just to understand a fixture. Group statements that always belong together, and only split when they are reusable or have distinct lifecycles.

## 4. Placing scripts in easy-to-find locations

Test SQL scripts are usually stored in test resources:

```text
src/test/resources/
└── sql/
    ├── common/
    │   ├── schema.sql
    │   └── reference-data.sql
    ├── customer/
    │   ├── insert-customer.sql
    │   └── insert-address.sql
    └── order/
        ├── insert-order.sql
        ├── insert-order-lines.sql
        └── cleanup-order.sql
```

You can use an explicit classpath path:

```java
@Sql(scripts = "classpath:/sql/order/insert-order.sql")
```

Common resource location styles:

- `classpath:/sql/order/insert-order.sql`: absolute path on the classpath.
- `/sql/order/insert-order.sql`: absolute classpath path.
- `insert-order.sql`: relative path based on the test class's package.
- `file:/path/to/script.sql`: external filesystem file, when permitted by the test environment.

Classpath paths usually fit tests best because scripts are packaged with test resources and run consistently in IDEs and build tools. Avoid depending on absolute paths on a developer's machine.

File names should indicate the action or data they create. Names like `data1.sql`, `setup.sql`, or `script-final.sql` are harder to trace than `insert-active-customer.sql`, `insert-pending-order.sql`, and `delete-order-fixture.sql`.

## 5. Choosing execution timing with executionPhase

By default, `@Sql` runs scripts before each test method. The `executionPhase` attribute lets you choose when scripts execute.

Main phases:

| Phase | Timing |
|---|---|
| `BEFORE_TEST_METHOD` | Before the test method; this is the default |
| `AFTER_TEST_METHOD` | After the test method |
| `BEFORE_TEST_CLASS` | Before the test methods in the class |
| `AFTER_TEST_CLASS` | After the test methods in the class complete |

The two class-level phases `BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` have been supported since Spring Framework 6.1. For earlier versions, use method phases and appropriate preparation/cleanup strategies.

For example, a test class can load base data once before the class, load per-test fixtures before each method, and clean up base data after the class:

```java
@SpringBootTest
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/common/reference-data.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS
        ),
        @Sql(
                scripts = "classpath:/sql/common/cleanup-reference-data.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS
        )
})
class ProductRepositoryTest {

    @Test
    @Sql(scripts = "classpath:/sql/product/insert-product.sql")
    void findsProduct() {
        // ...
    }
}
```

Class-level scripts only fit when data created once can be shared across methods in the class. If test methods modify or delete base data, there must be a way to restore state before the next method.

If one script needs to run before and another after each method, both can be grouped:

```java
@Test
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/order/insert-order.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "classpath:/sql/order/delete-order.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
        )
})
void readsOrder() {
    // ...
}
```

This group organizes two declarations with different phases. The preparation script runs before the method, while the cleanup script is scheduled after the method.

## 6. Class-level @Sql and method-level @Sql

SQL scripts can be declared on a class to apply to its test methods, and extra scripts can be declared on individual methods.

Example:

```java
@SpringBootTest
@Sql(scripts = "classpath:/sql/common/insert-default-customer.sql")
class OrderRepositoryTest {

    @Test
    void findsDefaultCustomer() {
        // ...
    }

    @Test
    @Sql(scripts = "classpath:/sql/order/insert-order.sql")
    void findsOrder() {
        // ...
    }
}
```

By default, when a method declares `@Sql`, method-level SQL declarations override class-level declarations for that method. Therefore, the second test method may run only its own script rather than running the class-level customer script as well.

This is a common point of confusion: placing `@Sql` on a class does not always mean class-level and method-level scripts automatically add together.

## 7. Using @SqlMergeMode when combining class and method scripts

`@SqlMergeMode` controls how Spring combines class-level `@Sql` declarations with method-level declarations.

There are two modes:

| Mode | Behavior |
|---|---|
| `OVERRIDE` | Default; method-level declaration replaces class-level declaration for that method |
| `MERGE` | Combines class-level and method-level declarations |

Example using `MERGE`:

```java
@SpringBootTest
@Sql(scripts = "classpath:/sql/common/insert-default-customer.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class OrderRepositoryTest {

    @Test
    void findsDefaultCustomer() {
        // Receives the class-level script
    }

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order-lines.sql")
    })
    void findsOrderWithLines() {
        // Both class-level script and method-level script group are applied
    }
}
```

With `MERGE`, class-level scripts are combined with method-level scripts. Class-level scripts execute before method-level scripts. This fits when every test needs base data and each method adds its own fixture.

If only a few methods need base data, you can keep the default `OVERRIDE` and declare the full script group on those methods. The choice depends on the meaning of shared data and desired clarity.

`@SqlMergeMode` can be placed on the class to apply to methods in the class, or placed on a method to alter merge behavior for a specific scenario.

## 8. Multiple script sets for multiple scenarios

A test class may verify multiple scenarios with different datasets. Split fixtures by behavior so each method loads only the data it needs.

Example:

```java
@SpringBootTest
class OrderQueryTest {

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-pending-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-pending-order-lines.sql")
    })
    void findsPendingOrder() {
        // Verify PENDING order
    }

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-cancelled-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-cancelled-order-lines.sql")
    })
    void findsCancelledOrder() {
        // Verify CANCELLED order
    }
}
```

Both tests have their own fixtures, and file names reflect business states. Readers can trace directly from a test method to its corresponding script group without reading a huge data file containing unrelated scenarios.

If tests share customer or lookup data, that script set can be placed at the class level using `@SqlMergeMode(MERGE)`. If datasets differ completely, method-level `@SqlGroup` with the default `OVERRIDE` is usually easier to understand.

## 9. Using @SqlConfig to configure how scripts run

`@SqlConfig` lets you adjust how Spring parses and executes SQL scripts. Shared configuration can be declared on the test class, or custom configuration on a single `@Sql`.

Common attributes:

| Attribute | Purpose |
|---|---|
| `dataSource` | Name of the DataSource bean to use |
| `transactionManager` | Name of the PlatformTransactionManager bean |
| `transactionMode` | How the script participates in or creates a transaction |
| `encoding` | Charset used to read script files |
| `separator` | SQL statement separator character |
| `commentPrefix` | Single-line comment prefix |
| `blockCommentStartDelimiter` | Block comment opening delimiter |
| `blockCommentEndDelimiter` | Block comment closing delimiter |
| `errorMode` | How errors are handled during script execution |

Shared configuration example:

```java
@SpringBootTest
@SqlConfig(
        dataSource = "dataSource",
        transactionManager = "transactionManager",
        encoding = "UTF-8",
        separator = ";"
)
class CustomerSqlTest {
    // @Sql annotations in this class use the shared configuration
}
```

Custom configuration can also be placed on a single declaration:

```java
@Sql(
        scripts = "classpath:/sql/customer/insert-customer.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = ";"
        )
)
```

Local configuration is useful when one script has a different separator or encoding rule. If all scripts in the class follow the same conventions, class-level configuration reduces repetition.

When using class-level `@SqlConfig` as global configuration for `@Sql` declarations, keep in mind default values and how Spring merges local configuration with global configuration. Only override attributes that truly need to change to avoid hard-to-trace setups.

## 10. Transaction modes for SQL scripts

SQL scripts can run in the current test transaction, in a separate transaction, or without a Spring transaction depending on configuration and environment.

The `transactionMode` attribute of `@SqlConfig` has these options:

- `DEFAULT`: uses Spring's default policy to infer how to run the script.
- `INFERRED`: infers based on the existing transaction and configured transaction components.
- `ISOLATED`: runs the script in an independent transaction and commits that transaction.

Under standard inferred mode, if a test-managed transaction is active and the script uses the same transaction manager/resource, the script can run in the test's transaction. When the test finishes and rolls back, data prepared by the script is also rolled back.

If no current transaction exists but a suitable transaction manager is present, Spring can create a transaction for the script and commit after the script succeeds. If no transaction manager exists, the script may execute without a Spring transaction.

Example requiring the script to run in an independent transaction:

```java
@Sql(
        scripts = "classpath:/sql/audit/insert-audit-fixture.sql",
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

`ISOLATED` is useful when script data must be committed independently of the test-managed transaction. It also means the test's default rollback cannot automatically undo data committed by this script.

Be cautious when choosing `ISOLATED`: data can persist after the test and requires explicit cleanup. For regular fixtures in tests with `@Transactional`, letting the script join the test transaction usually ensures data rolls back with the test.

## 11. Cleanup with scripts after tests

You can use `executionPhase = AFTER_TEST_METHOD` to run a script after the test method:

```java
@Test
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/customer/insert-customer.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "classpath:/sql/customer/delete-customer.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
        )
})
void readsCustomer() {
    // ...
}
```

Understand the cleanup script's transaction. If the script runs inside the test-managed transaction and the test transaction rolls back, the cleanup operations may also be rolled back. This is not necessarily an issue if all initial fixture data also lives in the same transaction and rollback deletes the fixture too.

However, if data was committed independently, such as via `REQUIRES_NEW` or an `ISOLATED` script, cleanup needs to run in an independent transaction and commit to delete that data:

```java
@Sql(
        scripts = "classpath:/sql/audit/delete-audit-fixture.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

Do not assume every `AFTER_TEST_METHOD` script permanently deletes data. Check which transaction the script runs in and whether that transaction ends in commit or rollback.

## 12. Distinguishing @SqlGroup from @SqlMergeMode

The two annotations solve two different problems:

| Annotation | Question answered |
|---|---|
| `@SqlGroup` | When multiple `@Sql` declarations exist on the same class or method, how should they be organized? |
| `@SqlMergeMode` | Should class-level and method-level SQL declarations be combined, or does the method replace the class? |

Example:

```java
@SpringBootTest
@Sql(scripts = "classpath:/sql/common/insert-tenant.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class TenantOrderTest {

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order-lines.sql")
    })
    void loadsTenantOrder() {
        // ...
    }
}
```

`@SqlGroup` groups the test method's two scripts. `@SqlMergeMode(MERGE)` decides that this script group is combined with the class-level tenant script. Neither annotation replaces the other's functionality.

## 13. Organizing multiple script sets across the lifecycle

For a test class with multiple scenarios, scripts can be divided into layers:

```text
SQL fixtures of test class
    |
    +--> BEFORE_TEST_CLASS
    |       shared schema or base data
    |
    +--> BEFORE_TEST_METHOD
    |       per-test fixture
    |
    +--> AFTER_TEST_METHOD
    |       cleanup per-test data
    |
    +--> AFTER_TEST_CLASS
            cleanup base data or class resources
```

Example directory structure:

```text
src/test/resources/sql/
├── shared/
│   ├── schema.sql
│   ├── reference-data.sql
│   └── cleanup-reference-data.sql
├── customer/
│   ├── insert-customer.sql
│   └── delete-customer.sql
└── order/
    ├── insert-pending-order.sql
    ├── insert-cancelled-order.sql
    ├── insert-order-lines.sql
    └── delete-order-fixture.sql
```

Not every test class needs all four phases. Only use phases that match the data lifecycle. With databases created fresh per test run, schema creation may be handled by migrations or container setup; there is no need to repeat schema scripts in every class.

## 14. Notes on ordering and data dependencies

When multiple scripts exist, execution order is part of the fixture. Clarify dependencies explicitly:

- Create tables before inserting data.
- Create parent records before child records with foreign keys.
- Create lookup entries before business records referencing them.
- Delete child records before parent records if the database enforces foreign key constraints.
- Use fixed or unique identifiers to avoid data collisions across tests.

For example, if `order_line.order_id` references `orders.id`, the preparation order must be:

```text
insert-customer.sql
        |
        v
insert-order.sql
        |
        v
insert-order-lines.sql
```

During cleanup:

```text
delete-order-lines.sql
        |
        v
delete-order.sql
        |
        v
delete-customer.sql
```

If a script depends on state created by another script, keep them in the same group or name and document them clearly so others do not accidentally separate them.

## 15. Common errors when using @SqlGroup

| Symptom | Possible cause | Resolution |
|---|---|---|
| Class-level script does not run on a method with its own @Sql | Method-level overrides class-level by default | Use `@SqlMergeMode(MERGE)` if combining is needed |
| Scripts run in the wrong order | Script list or dependency order is unclear | Order scripts according to foreign key relationships |
| Records remain after test finishes | Script or app code committed an independent transaction | Check transactionMode and propagation; add independent cleanup |
| Cleanup script runs yet data remains | Cleanup joined the test transaction and rolled back | Use an independent transaction for cleanup when commit is needed |
| SQL file not found | Relative or wrong classpath path | Use `classpath:/...` and check test resources |
| Script with Vietnamese characters fails | Incompatible encoding | Declare `@SqlConfig(encoding = "UTF-8")` |
| SQL statements split improperly | Unsuitable separator or comment delimiter | Configure `@SqlConfig` per dialect/script |
| Script continues after unexpected error | Unsuitable error mode | Choose an appropriate error policy, usually failing clearly |
| One test's fixture affects another test | Data committed or shared | Use transaction rollback, unique IDs, and cleanup |
| Using @SqlGroup expecting all scripts in one transaction | Confusing grouping annotation with transaction boundaries | Configure transaction mode and understand each declaration's transaction |

When errors occur, identify which scripts ran, which phases triggered, how class/method merge is configured, and which transaction manages the SQL operations. Seeing `@SqlGroup` on a test class alone is not enough to conclude all scripts run together once or in a single transaction.

## 16. Choosing the right organization strategy

| Need | Usage |
|---|---|
| One simple script for one test | Single `@Sql` |
| Multiple scripts needing sequential order | One `@Sql(scripts = {...})` or `@SqlGroup` |
| Each script needs its own phase or config | `@SqlGroup` with multiple `@Sql` |
| Multiple tests share base data | Class-level `@Sql` |
| Each test needs its own fixture replacing base data | Method-level `@Sql` with default override |
| Each test needs to add data to the shared set | `@SqlMergeMode(MERGE)` |
| Script needs custom encoding/separator or transaction | `@SqlConfig` |
| Script must commit independently of test transaction | `transactionMode = ISOLATED`, with cleanup |
| Need to load/clean up data once for the whole class | Class-level phase if using Spring Framework 6.1 or newer |

`@SqlGroup` helps describe multiple script sets right where tests use them. When combined properly with phases, merge mode, and transaction configuration, data is prepared in an understandable and repeatable sequence. Name files by purpose, keep dependency ordering clear, and identify where cleanup actually commits to avoid leftover data after tests.

