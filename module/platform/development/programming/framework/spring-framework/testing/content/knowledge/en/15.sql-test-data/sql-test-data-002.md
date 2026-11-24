# @Sql for SQL Scripts or Statements

In Spring testing, input data often needs to be prepared directly in the database. A repository test may need an existing customer and several orders; a service test may need data across multiple tables to verify queries, relationships, or transactions. If every test writes its own JDBC setup and cleanup, test code easily becomes verbose, repetitive, and hard to read.

Spring TestContext provides the **@Sql** annotation to execute SQL before or after a test method. You can use external SQL files or declare statements directly inside the annotation. This mechanism ensures test data is prepared according to a clear rule, attached to a test class or test method, and executed via Spring's DataSource.

This lesson covers the two primary ways to use @Sql — scripts and inline SQL statements — along with choosing the execution phase, configuring DataSource and transactions, combining with @Transactional, managing repeatable data, and handling common errors.

## 1. What is @Sql used for?

**@Sql** instructs Spring TestContext to execute one or more SQL scripts or SQL statements during the test lifecycle. The commands are executed via the DataSource configured in the ApplicationContext, so they can operate against a real database or a dedicated test database.

Common purposes:

- Inserting sample data before testing a repository.
- Creating initial state for a business workflow.
- Updating or deleting data before a test case.
- Preparing data across multiple tables without writing many lines of JDBC in Java.
- Cleaning up data after a test when data is not rolled back with the test transaction.
- Sharing a common base dataset across multiple test methods.

Simple example:

~~~java
@SpringBootTest
@Sql("/sql/insert-customers.sql")
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldFindCustomerByEmail() {
        var customer =
                customerRepository.findByEmail("lan@example.test");

        assertTrue(customer.isPresent());
        assertEquals("Lan", customer.get().getName());
    }
}
~~~

When the test method runs, Spring executes the script before the test body according to the default execution phase. The test then queries the data inserted by the script.

@Sql neither creates databases automatically nor defines schemas automatically. The database, DataSource, tables, and SQL execution permissions must be prepared by the application configuration or test environment. The script simply executes on the database to which Spring is connected.

## 2. Two ways to declare SQL: scripts and statements

@Sql supports two ways to provide SQL content:

1. **scripts**: specifies paths to one or more SQL files.
2. **statements**: declares individual SQL statements directly inside the annotation.

You can use the `value` attribute as an alias for `scripts`:

~~~java
@Sql("/sql/seed-customers.sql")
~~~

Equivalent to:

~~~java
@Sql(scripts = "/sql/seed-customers.sql")
~~~

Within a single @Sql declaration, choose either `scripts` or `statements` based on your intent. If you need to execute multiple groups of commands with different configurations or execution phases, declare separate @Sql annotations or use @SqlGroup.

### 2.1. Using scripts when data has multiple statements

Create a file:

~~~text
src/test/resources/sql/seed-customers.sql
~~~

Contents:

~~~sql
DELETE FROM customer;

INSERT INTO customer (id, name, email)
VALUES (101, 'Lan', 'lan@example.test');

INSERT INTO customer (id, name, email)
VALUES (102, 'Minh', 'minh@example.test');
~~~

Declare in the test:

~~~java
@DataJpaTest
@Sql(scripts = "classpath:/sql/seed-customers.sql")
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldLoadSeededCustomers() {
        assertEquals(2, customerRepository.count());
    }
}
~~~

Placing the script in `src/test/resources` ensures the file is included on the test classpath without being packaged into production artifacts. The `classpath:` prefix clarifies that the resource is loaded from the classpath.

Separate scripts are suitable when:

- There are many SQL statements or data spanning multiple tables.
- Multiple tests share the same dataset.
- You want to review test data as a standalone file.
- You want to manage DDL, seed data, and cleanup in separate files.
- The SQL is long or needs explanatory comments.

### 2.2. Using statements for a few short commands

If only a few simple SQL statements are needed, you can declare them directly:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    @Sql(statements = {
            "DELETE FROM customer",
            "INSERT INTO customer (id, name, email) " +
                    "VALUES (101, 'Lan', 'lan@example.test')"
    })
    void shouldFindSeededCustomer() {
        var customer =
                customerRepository.findByEmail("lan@example.test");

        assertTrue(customer.isPresent());
        assertEquals("Lan", customer.get().getName());
    }
}
~~~

Each element in the `statements` array is an SQL statement to execute. You can wrap lines in Java for readability, but ensure the resulting string is valid SQL for the database in use.

Statements are suitable when:

- There are only a few short commands.
- The data serves only a single test method.
- You want to see the setup right next to the test.
- There is no need to reuse an SQL file.

If an annotation contains many long SQL statements, move them to a script file to keep the test class concise.

## 3. Paths to SQL files

Spring's ResourceLoader supports several resource path formats. With @Sql, specify an explicit prefix so readers know where the file comes from.

| Path format | Meaning | Example |
|---|---|---|
| classpath: | Locate resource on the classpath | classpath:/sql/seed.sql |
| file: | Read file from the filesystem | file:./config/test-data.sql |
| Relative path | Resolved according to Spring resource rules | /sql/seed.sql or corresponding resource name |

In Maven or Gradle projects, files in `src/test/resources` are typically copied to the test classpath. Therefore, a common path is:

~~~java
@Sql("classpath:/sql/orders/seed-orders.sql")
~~~

Using an absolute path within the classpath avoids depending on the test class's package. If using a relative path, understand how Spring resolves resources so you do not accidentally point to a different file when moving the test class.

Organize files by feature:

~~~text
src/test/resources/
    sql/
        schema/
            create-customer-tables.sql
        customer/
            seed-customers.sql
            cleanup-customers.sql
        order/
            seed-orders.sql
            cleanup-orders.sql
~~~

File names should reflect the action and related data. When a script is used across multiple test classes, keep it independent of the execution order of other tests.

Avoid placing test data in `src/main/resources` without a clear reason. Data meant for tests generally should not be packaged into the application artifact.

## 4. Executing SQL before or after a test method

The **executionPhase** attribute determines when Spring runs the SQL.

Two commonly used values:

- **BEFORE_TEST_METHOD**: runs before the test method. This is the default.
- **AFTER_TEST_METHOD**: runs after the test method.

### 4.1. Preparing data before the test

~~~java
@Test
@Sql(
        scripts = "classpath:/sql/seed-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
void shouldFindOpenOrders() {
    var orders = orderRepository.findByStatus(OrderStatus.OPEN);

    assertEquals(2, orders.size());
}
~~~

Declaring the phase explicitly tells readers that the script is for setup. In many cases `executionPhase` can be omitted because `BEFORE_TEST_METHOD` is the default.

### 4.2. Cleaning up data after the test

~~~java
@Test
@Sql(
        scripts = "classpath:/sql/seed-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
        scripts = "classpath:/sql/cleanup-orders.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void shouldProcessOrders() {
    // Execute and verify order processing behavior.
}
~~~

A cleanup script can delete data created specifically for the test. Check the transaction mode to know whether the cleanup statements are committed or rolled back with another transaction.

If the test already runs inside a rolled-back transaction, data inserted within the same transaction may disappear automatically when the test ends. In that case, a cleanup script may not be necessary. However, if the test writes data through an HTTP server running on another thread, uses an isolated transaction, or calls an external system, rolling back the test method does not automatically undo those side effects.

### 4.3. Class-level @Sql

@Sql can be placed on a test class so the script applies to the test methods in that class:

~~~java
@DataJpaTest
@Sql("classpath:/sql/seed-reference-data.sql")
class ProductRepositoryTest {

    @Test
    void shouldFindProductByCode() {
        // ...
    }

    @Test
    void shouldFindProductsByCategory() {
        // ...
    }
}
~~~

Class-level declarations generally fit shared base data. Under the default execution phase, the script runs before each test method in the class. Therefore, the script must be repeatable and must not assume it runs only once for the entire class.

If you want a separate dataset for an individual test method, declare @Sql on that method.

## 5. Combining class-level and method-level @Sql

When a test class has base data and each method needs its own data, you need to understand the merge rules.

By default, a method-level @Sql declaration **overrides** the class-level @Sql declaration for that method. If you want both to apply, use **@SqlMergeMode(MERGE)**.

Example:

~~~java
@DataJpaTest
@Sql("classpath:/sql/seed-reference-data.sql")
class ProductRepositoryTest {

    @Test
    void shouldFindActiveProduct() {
        // Uses the class-level base data.
    }

    @Test
    @Sql("classpath:/sql/seed-discontinued-product.sql")
    void shouldFindDiscontinuedProduct() {
        // By default, method declaration replaces class declaration.
    }
}
~~~

If you want a method to use both base data and its own data:

~~~java
@DataJpaTest
@Sql("classpath:/sql/seed-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class ProductRepositoryTest {

    @Test
    @Sql("classpath:/sql/seed-discontinued-product.sql")
    void shouldFindDiscontinuedProduct() {
        // Both class-level script and method-level script are applied.
    }
}
~~~

@SqlMergeMode can be placed at the class level so all methods in the class follow the same rule, or on a method to change it for a single test. When using MERGE, check the ordering and repeatability of the scripts, because both class-level and method-level scripts may affect the same tables.

Do not rely on arbitrary execution order between test methods to produce data. Each method must have a deterministic initial state.

## 6. Using multiple scripts or multiple @Sql declarations

A test may require multiple scripts, such as creating customer data and then creating orders referencing that customer.

~~~java
@Test
@Sql(scripts = {
        "classpath:/sql/customer/seed-customers.sql",
        "classpath:/sql/order/seed-orders.sql"
})
void shouldLoadOrdersForCustomer() {
    // ...
}
~~~

When different phases or configurations are needed for each group of scripts, multiple @Sql annotations can be declared. @Sql is a repeatable annotation; you can also use @SqlGroup to group declarations:

~~~java
@Test
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/seed-orders.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "classpath:/sql/cleanup-orders.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
        )
})
void shouldProcessOrder() {
    // ...
}
~~~

Using multiple declarations helps separate setup and cleanup. Name scripts clearly and do not let cleanup delete base data shared by other test classes.

## 7. Configuring scripts with @SqlConfig

**@SqlConfig** lets you customize how Spring parses and executes SQL scripts. Configuration can be declared directly inside @Sql or placed at the class level as the default configuration for @Sql annotations in the class.

Example:

~~~java
@SpringBootTest
@Sql(
        scripts = "classpath:/sql/seed-orders.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = ";",
                commentPrefix = "--"
        )
)
class OrderRepositoryTest {
}
~~~

Attributes to pay attention to:

| Attribute | Purpose |
|---|---|
| dataSource | Specify the DataSource bean name |
| transactionManager | Specify the PlatformTransactionManager bean name |
| transactionMode | Choose how SQL runs inside a transaction |
| encoding | Encoding of the SQL file |
| separator | Statement separator |
| commentPrefix / commentPrefixes | Single-line comment prefix |
| blockCommentStartDelimiter | Multi-line comment opening delimiter |
| blockCommentEndDelimiter | Multi-line comment closing delimiter |
| errorMode | How to handle errors when an SQL statement fails |

### 7.1. Choosing a DataSource when there are multiple databases

If the application has multiple DataSources, Spring may not be able to infer which database should run the script. In that case, specify the bean explicitly:

~~~java
@Sql(
        scripts = "classpath:/sql/order/seed-orders.sql",
        config = @SqlConfig(dataSource = "ordersDataSource")
)
~~~

If there are multiple transaction managers, specify the corresponding manager:

~~~java
@Sql(
        scripts = "classpath:/sql/order/seed-orders.sql",
        config = @SqlConfig(
                dataSource = "ordersDataSource",
                transactionManager = "ordersTransactionManager"
        )
)
~~~

The DataSource and transaction manager must belong to the same database or the same transaction resource that the script operates on. Choosing the wrong manager can cause the script to run outside the transaction the test expects.

If there is only one suitable DataSource and one suitable transaction manager, Spring can usually infer them from the ApplicationContext.

### 7.2. Encoding and comments

SQL scripts should use a consistent encoding, especially when containing Vietnamese data:

~~~java
@Sql(
        scripts = "classpath:/sql/seed-vietnamese-customers.sql",
        config = @SqlConfig(encoding = "UTF-8")
)
~~~

Example file:

~~~sql
INSERT INTO customer (id, name, email)
VALUES (201, 'Nguyễn Lan', 'lan@example.test');
~~~

Spring supports single-line comments and block comments. If a script uses custom comment conventions, you can configure the corresponding comment prefix or delimiters.

Avoid custom separators if the script does not need them. Keeping the default keeps SQL readable and compatible with common database tools.

### 7.3. Statement separator

By default, the script parser uses a semicolon to identify SQL statement boundaries. Example:

~~~sql
DELETE FROM order_item;
DELETE FROM orders;
~~~

For stored procedures or SQL blocks containing semicolons inside, the default separator may not be suitable. In that case, choose a custom separator:

~~~java
@Sql(
        scripts = "classpath:/sql/create-procedure.sql",
        config = @SqlConfig(separator = "@@")
)
~~~

Corresponding script file:

~~~sql
CREATE PROCEDURE cleanup_orders()
BEGIN
    DELETE FROM order_item;
    DELETE FROM orders;
END
@@
~~~

Procedure syntax is database-dependent. The example above only illustrates using a custom separator; adjust the syntax and delimiter to match the database engine in use.

### 7.4. ErrorMode

By default, SQL errors are handled according to Spring's default mode and errors are not arbitrarily ignored. @SqlConfig lets you choose `errorMode`:

- DEFAULT: uses the default error-handling policy.
- CONTINUE_ON_ERROR: continues executing subsequent statements after a statement encounters an error.
- IGNORE_FAILED_DROPS: ignores errors from matching DROP statements, useful in certain cleanup scripts.

Only continue when errors are anticipated and do not leave data in a half-baked state. For setup scripts creating data required for assertions, the fail-fast default is usually safer: the test stops immediately when data is not prepared properly.

## 8. TransactionMode: which transaction does the SQL run in?

An important question is whether the script participates in the test's transaction. @SqlConfig provides the **transactionMode** attribute with two primary options:

- **INFERRED**: Spring infers the DataSource and transaction manager. If an active transaction exists, the script can participate in it; if a suitable transaction manager exists but no transaction is active, Spring may create a transaction for executing the script. If no suitable transaction manager exists, the script executes without a Spring-managed transaction.
- **ISOLATED**: Spring runs the script in an independent transaction, using propagation equivalent to REQUIRES_NEW, and commits that transaction once the script completes.

INFERRED is the default mode.

### 8.1. Script participating in the test transaction

~~~java
@DataJpaTest
@Transactional
@Sql("classpath:/sql/seed-customers.sql")
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldReadSeededCustomer() {
        assertEquals(2, customerRepository.count());
    }
}
~~~

With a test-managed transaction, a BEFORE_TEST_METHOD script typically runs inside the test's transaction when Spring can properly infer the transaction manager. When the test finishes, the transaction rolls back by default. Data inserted by the script in that transaction is also rolled back.

This approach fits tests that need initial data without leaving records behind after each run.

### 8.2. Script requiring an independent transaction

~~~java
@Sql(
        scripts = "classpath:/sql/seed-reference-data.sql",
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
~~~

ISOLATED creates a separate transaction and commits the script independently. Data may persist after the test's transaction rolls back. This is a deliberate choice when data must be committed before the test or when the script must run separately from the current transaction.

Because the script commits, a clear cleanup plan is required. Otherwise, subsequent runs may hit duplicate keys or stale data that skews results.

### 8.3. Do not confuse test rollback with all side effects

Rolling back a test-managed transaction only undoes operations that participated in that transaction. It does not automatically undo:

- SQL executed in an independent transaction that already committed.
- HTTP requests handled in a server transaction on another thread.
- Writes performed via a different DataSource or transaction manager.
- Files created, messages sent, or external APIs called.
- Effects of a service that does not support a shared transaction.

If using @Sql to prepare data for a test with RANDOM_PORT, check which transaction handles the request. The test thread's transaction does not automatically encompass the HTTP server's transaction.

## 9. Combining @Sql with @Transactional

A common pattern in repository tests is using @DataJpaTest or @SpringBootTest together with @Transactional.

~~~java
@DataJpaTest
@Transactional
@Sql(
        scripts = "classpath:/sql/order/seed-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldFindOrdersForCustomer() {
        var orders =
                orderRepository.findByCustomerId("customer-1");

        assertEquals(2, orders.size());
    }
}
~~~

Spring TestContext integrates @Sql with test transactions via TestExecutionListeners. The transaction listener manages the test transaction; the SQL listener executes scripts at the corresponding phases.

Some notes:

- @DataJpaTest has a transaction per test method by default and rolls back after the test finishes.
- @SpringBootTest does not automatically have a test transaction unless @Transactional or an appropriate transaction mechanism is declared.
- BEFORE_TEST_METHOD scripts can participate in the test transaction depending on transactionMode and DataSource configuration.
- ISOLATED scripts are committed separately, so data is not rolled back with the test transaction.
- If the test uses multiple DataSources, the DataSource and transaction manager must be explicitly specified.
- If the test performs asynchronous operations or HTTP requests against a real server, transactions and cleanup must be managed separately.

Do not rely on rollback to clean up data if the script or application writes through another transaction. Verify transaction boundaries before choosing a cleanup strategy.

## 10. Full example: seeding data via script and testing a repository

Suppose there are two tables:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Data script:

~~~sql
DELETE FROM orders;
DELETE FROM customer;

INSERT INTO customer (id, name, email)
VALUES (101, 'Lan', 'lan@example.test');

INSERT INTO customer (id, name, email)
VALUES (102, 'Minh', 'minh@example.test');

INSERT INTO orders (id, customer_id, status, total_amount)
VALUES (1001, 101, 'PAID', 250000.00);

INSERT INTO orders (id, customer_id, status, total_amount)
VALUES (1002, 101, 'OPEN', 150000.00);
~~~

Test:

~~~java
@DataJpaTest
@Sql(
        scripts = "classpath:/sql/order/seed-customer-orders.sql",
        config = @SqlConfig(encoding = "UTF-8")
)
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldFindOrdersByCustomer() {
        var orders = orderRepository.findByCustomerId(101L);

        assertEquals(2, orders.size());
        assertTrue(orders.stream()
                .anyMatch(order -> order.getStatus() == OrderStatus.PAID));
        assertTrue(orders.stream()
                .anyMatch(order -> order.getStatus() == OrderStatus.OPEN));
    }
}
~~~

This example assumes the schema was created before @Sql runs. With @DataJpaTest, the schema may be generated from entities, schema.sql, or test database configuration depending on the project. If you need to test migrations, use a compatible test database and run migrations before the seed script.

The script deletes data in both tables before inserting. If the database has foreign keys, child tables must be deleted before parent tables. Insert order must also follow foreign key relationships.

In the default test transaction, SQL operations can be rolled back after the test. If the script runs in an isolated transaction, committed data will need separate cleanup.

## 11. Example using statements for a single test method

For a test that only needs one record, `statements` can be concise:

~~~java
@DataJpaTest
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    @Sql(statements = {
            "DELETE FROM account WHERE id = 501",
            "INSERT INTO account (id, owner, balance) " +
                    "VALUES (501, 'Lan', 100000.00)"
    })
    void shouldFindAccountById() {
        var account = accountRepository.findById(501L);

        assertTrue(account.isPresent());
        assertEquals("Lan", account.get().getOwner());
        assertEquals(
                new BigDecimal("100000.00"),
                account.get().getBalance()
        );
    }
}
~~~

Statements keep setup data right next to the test. However, if a statement spans many lines or has multiple records, a script is usually easier to read and reuse.

Avoid inserting data by concatenating untrusted user input into strings. @Sql statements are static SQL tied to the test; if dynamic parameters are needed, use JDBC/JPA or a test data builder with parameter binding rather than arbitrary SQL string concatenation.

## 12. Using @Sql in @DataJpaTest and @JdbcTest

@Sql is not only for @SpringBootTest. It works with Spring TestContext integration tests that have a suitable DataSource.

### With @DataJpaTest

~~~java
@DataJpaTest
@Sql("/sql/seed-products.sql")
class ProductRepositoryTest {
}
~~~

@DataJpaTest loads the JPA slice and typically uses an embedded database if dependencies and configuration allow. The script runs on the slice's DataSource.

If you want to use the exact production engine, combine Testcontainers and DynamicPropertySource to provide the test database URL. @Sql will then execute the script against the DataSource configured from the container.

### With @JdbcTest

~~~java
@JdbcTest
@Sql("/sql/seed-products.sql")
class ProductJdbcRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void shouldCountSeededProducts() {
        var count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM product",
                Integer.class
        );

        assertEquals(3, count);
    }
}
~~~

@JdbcTest focuses on JDBC components. @Sql helps seed data before JdbcTemplate executes queries.

With both slice tests, remember the test's default transaction and rollback. If using scripts in another phase or transaction mode, verify whether data is committed.

## 13. Can SQL scripts contain DDL?

@Sql can be used to execute DDL such as CREATE TABLE, ALTER TABLE, or index creation commands. However, consider rollback behavior and differences across databases.

Example:

~~~java
@Sql(
        scripts = "classpath:/sql/schema/create-test-table.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
~~~

Some database engines auto-commit or have special transaction rules for DDL. Therefore, do not assume every DDL statement rolls back with the test transaction.

For schemas shared across many tests, it is usually better to use schema initialization or a migration tool during environment preparation. @Sql is better suited for test data and schema changes very specific to a group of tests.

If a script creates temporary tables or custom objects, determine how to remove them. Some databases support connection-scoped or transaction-scoped temporary tables; behavior can vary across H2, PostgreSQL, MySQL, and other engines.

## 14. Using @Sql to test migrations and special data

@Sql can help prepare data in states that are difficult to create via API:

- Legacy records missing a new field.
- Data in a pending state.
- Many-to-many relationships with many related records.
- Boundary values for dates, amounts, or statuses.
- Data intended to violate constraints to test error handling.
- Records with fixed timestamps or IDs.

For example, to test code that reads legacy data:

~~~sql
INSERT INTO customer (
    id,
    name,
    email,
    created_at
)
VALUES (
    301,
    'Legacy Customer',
    'legacy@example.test',
    TIMESTAMP '2020-01-01 00:00:00'
);
~~~

The test can verify that the application handles the old record properly. Timestamp literal syntax can vary by database; if multi-engine compatibility is required, use appropriate syntax or a data builder via JDBC.

For migrations, distinguish:
- Migration tests verify schema and data after running migrations.
- Repository tests verify queries on an already prepared schema.
- @Sql seed data creates initial state for each test.

Do not use a seed script to replace migration testing if the goal is to ensure production migrations run properly.

## 15. Managing data so tests can run independently

A good @Sql script should be repeatable and independent of other tests.

Key principles:

**Use deterministic IDs and data**

Choose dedicated IDs, emails, or business codes for the test so assertions are easy to read and collisions with other data are avoided.

**Delete within test scope**

Prefer DELETE by the test's own ID or key. Avoid full-table DELETE if the database might be shared by multiple tests running in parallel.

**Respect foreign keys**

Delete child tables before parent tables; insert parent tables before child tables. This avoids constraint errors and makes scripts predictable.

**Do not depend on test order**

Each test must prepare its own required data. Do not let test B depend on a script that only runs in test A.

**Be careful with parallel execution**

If multiple tests share the same ID or delete data in the same table, they can interfere with each other. Use separate keys per test or dedicated databases/schemas per worker.

**Choose transaction mode intentionally**

INFERRED is usually right when the script should join the test's transaction. ISOLATED should only be used when an independent commit is required along with matching cleanup.

**Do not use real production data**

Seed data should be synthetic, containing no personal information or real secrets. Tests need to reproduce data structure, not copy sensitive data.

## 16. @Sql and application-generated data

Not every test should use SQL to seed data. There are two approaches:

- Use SQL when you need direct control over database state or to create complex data.
- Use repositories/services or test data builders when you want to create data through the application's API.

Direct SQL has the advantage of being concise and exact for database state. However, it can bypass validation, default values, or business logic performed in services.

For example, if you want to test the customer creation workflow, call the customer creation service or API to verify that logic. If you want to test a query finding customers by status, seeding data directly with @Sql is appropriate.

A test can combine both:
- @Sql creates complex background data.
- The service creates the main object under test.
- The repository reads the data back to verify persistence.

Choose the setup method based on the behavior under test. Do not use SQL to create the exact state that the test is supposed to prove the application can create.

## 17. Common errors when using @Sql

| Symptom | Common cause | Resolution |
|---|---|---|
| SQL file not found | Wrong classpath or file name | Place in `src/test/resources` and use `classpath:/...` |
| SQL runs but no data during assertion | Script ran on another DataSource or transaction rolled back | Check DataSource, transaction manager, and phase |
| Duplicate key | Script ran multiple times or stale data remains | Use unique data, proper cleanup, or idempotent scripts |
| Foreign key violation | Wrong table delete/insert order | Delete child before parent, insert parent before child |
| Method-level script does not run with class-level script | Method-level @Sql overrides class-level by default | Use @SqlMergeMode(MERGE) if merging is needed |
| Script fails due to separator | Stored procedure contains semicolons inside | Configure a custom separator in @SqlConfig |
| Vietnamese characters corrupted | Inconsistent encoding | Save as UTF-8 and declare encoding when needed |
| Cleanup statement fails to delete data | Cleanup ran in a rolled-back transaction or used another DataSource | Check phase, transactionMode, and transaction manager |
| Test passes alone but fails in parallel | Shared IDs or full-table DELETE | Isolate keys, schemas, or databases |
| Script continues after a failing SQL statement | ErrorMode allows continuing | Use default/fail-fast mode when setup data is mandatory |
| Transaction manager not found | Context has multiple or lacks a suitable manager | Specify `transactionManager` explicitly in @SqlConfig |

When debugging, verify in order:

1. Is the SQL resource found?
2. Is the script executed at the expected phase?
3. Which DataSource is the script using?
4. Is there an active transaction?
5. Is the transaction mode ISOLATED?
6. Do the statements actually commit?
7. Is the assertion reading from the same database/schema?
8. Was data cleaned up or rolled back before the assertion?

Do not fix issues by disabling all transactions or ignoring all SQL errors without identifying the root cause.

## 18. Example combining setup and cleanup with two phases

A test can use separate scripts for setup and cleanup:

~~~java
@SpringBootTest
class InventoryRepositoryTest {

    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    @Sql(
            scripts = "classpath:/sql/inventory/seed-item.sql",
            executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
    )
    @Sql(
            scripts = "classpath:/sql/inventory/cleanup-item.sql",
            executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
    void shouldFindInventoryItem() {
        var item = inventoryRepository.findBySku("SKU-TEST-1");

        assertTrue(item.isPresent());
        assertEquals(20, item.get().getQuantity());
    }
}
~~~

Setup script:

~~~sql
DELETE FROM inventory WHERE sku = 'SKU-TEST-1';

INSERT INTO inventory (id, sku, quantity)
VALUES (9001, 'SKU-TEST-1', 20);
~~~

Cleanup script:

~~~sql
DELETE FROM inventory WHERE sku = 'SKU-TEST-1';
~~~

This example illustrates data with a dedicated key. In real applications, if the test method is managed in a transaction and the setup script participates in that transaction, rollback may already suffice to clean up data. Cleanup scripts remain useful when data is committed separately or the test has side effects outside the transaction.

If using an independent transaction for cleanup, configure ISOLATED intentionally and verify that it points to the correct database.

## 19. When to use scripts vs. statements?

| Criterion | scripts | statements |
|---|---|---|
| Amount of SQL | Many statements or multiple tables | A few short statements |
| Reusability | High, shared across multiple tests | Usually tied to a single test |
| Ease of reviewing data | Separate file, easy to view as a whole | Viewed directly at the annotation |
| SQL comments and formatting | Flexible | Limited by Java strings |
| Parser configuration | Configurable via @SqlConfig | Rarely needs customization |
| Suitability for DDL or complex seeds | Suitable | Hard to maintain if too long |
| Typical situation | Multi-table seeding, setup/cleanup | Inserting a single simple record |

Practical rules:

- Use `statements` if there are one or two short commands and the data only serves the current method.
- Use `scripts` if the SQL is long, spans multiple tables, is reused, or needs comments.
- Use `@SqlMergeMode` when combining class-level base data with method-level custom data.
- Use `@SqlConfig` when selecting DataSource, transaction manager, encoding, separator, or error mode.
- Use a JDBC/JPA fixture builder when data needs dynamic parameters or must run through application logic.

## 20. Database limitations and caveats

SQL in @Sql is executed on the test's actual database. Therefore, SQL syntax depends on the database engine in use.

A script that runs on H2 may not run on PostgreSQL or MySQL due to differences in:

- Data types.
- Identity/sequence syntax.
- Timestamp literals.
- SQL and JSON functions.
- Constraints and indexes.
- Stored procedure syntax.
- DDL transaction behavior.

If the production application uses PostgreSQL, consider running repository integration tests with PostgreSQL Testcontainers. This ensures test scripts reflect the actual dialect and constraints of the target engine.

Additionally:

- Avoid hard-coding environment-dependent schema or database names.
- Use synthetic test data and dedicated keys.
- Never point test scripts at a production database.
- Do not use broadly destructive commands like DROP DATABASE in test scripts.
- Be careful with sequences after manually inserting IDs; sequences may need to be updated in a database-appropriate way.
- Verify timezone and locale if scripts contain dates/times or environment-dependent data.

## 21. Workflow for adopting @Sql in a project

When adding @Sql to a test, you can follow these steps:

1. Identify the database state required before the test.
2. Choose `scripts` if the data is lengthy or reused; choose `statements` if there are only a few simple statements.
3. Place SQL files in test resources and use explicit classpath paths.
4. Choose the appropriate executionPhase: BEFORE_TEST_METHOD for setup, AFTER_TEST_METHOD for cleanup.
5. If @Sql is present at both class and method levels, decide whether @SqlMergeMode(MERGE) is needed.
6. Verify the selected DataSource and transaction manager.
7. Choose INFERRED or ISOLATED based on the transaction boundary under test.
8. Use dedicated keys and insert/delete ordering matching foreign keys.
9. Run the test individually and as part of the full test suite to catch data dependencies.
10. If using multiple databases or parallel execution, isolate schemas and data between tests.

A good script must be repeatable within the test's data scope and independent of other tests. Treat SQL setup as part of the fixture, with clear responsibilities and proper lifecycle placement.

## 22. Conclusion

@Sql helps Spring TestContext prepare or clean up database data using SQL files or inline statements.

- Use `scripts` for long, multi-table, or reusable SQL.
- Use `statements` for a few short commands tied to a test method.
- BEFORE_TEST_METHOD is the default phase; AFTER_TEST_METHOD suits cleanup.
- Class-level and method-level @Sql follow override rules by default; use @SqlMergeMode(MERGE) when merging is needed.
- @SqlConfig controls DataSource, transaction manager, encoding, separator, and error handling.
- INFERRED is the default and can join the test's transaction; ISOLATED runs the script in an independently committed separate transaction.
- Test rollback does not undo independently committed data or side effects outside the transaction.
- Data needs dedicated keys, SQL ordering aligned with foreign keys, and no dependency on test execution order.

When choosing appropriately between scripts and statements and understanding phases and transaction modes, @Sql gives database tests deterministic, readable, and repeatable input data in CI environments.

