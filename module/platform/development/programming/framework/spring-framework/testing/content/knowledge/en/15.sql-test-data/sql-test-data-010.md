# JdbcTestUtils for Counting, Checking, and Cleaning Up Data

When writing Spring tests that access a database, you often need to verify how many rows a table contains, check the number of rows matching a condition, or clean up data between test cases. Spring Test provides the `JdbcTestUtils` utility class to perform those common operations on a `JdbcTemplate`.

`JdbcTestUtils` is not a repository, does not manage transactions, and does not create databases. It is a collection of utility methods using simple SQL statements to count rows, delete rows, or drop tables. The test still requires a `DataSource`, a `JdbcTemplate`, and a suitable transaction manager if operations should participate in a Spring-managed transaction.

Commonly used methods:

| Method | Task |
|---|---|
| `countRowsInTable(jdbcTemplate, tableName)` | Count all rows in the table. |
| `countRowsInTableWhere(jdbcTemplate, tableName, whereClause)` | Count rows matching a WHERE condition. |
| `deleteFromTableWhere(jdbcTemplate, tableName, whereClause)` | Delete rows matching a WHERE condition. |
| `deleteFromTables(jdbcTemplate, tableNames...)` | Delete all rows in the specified tables. |
| `dropTables(jdbcTemplate, tableNames...)` | Execute DROP TABLE for the specified tables. |

These methods belong to the `org.springframework.test.jdbc` package in the `spring-test` module.

## 1. Dependencies and basic usage

In Spring Boot applications, `spring-boot-starter-test` typically brings Spring Test onto the test classpath. For Spring Framework projects without Boot, declare the `spring-test` module at test scope alongside the JDBC and JUnit modules your project needs.

Gradle example:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-jdbc")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
```

Import the utility class:

```java
import org.springframework.test.jdbc.JdbcTestUtils;
```

The methods on `JdbcTestUtils` are static. You can call them via the class name to make the API source clear:

```java
int total = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");
```

Or use static imports in tests:

```java
import static org.springframework.test.jdbc.JdbcTestUtils.countRowsInTable;
import static org.springframework.test.jdbc.JdbcTestUtils.countRowsInTableWhere;
```

The first argument is always `JdbcTemplate`. `JdbcTestUtils` uses this template to execute SQL and retrieve results. Therefore, counting or deletion operations execute on the exact datasource that the template uses.

## 2. Counting all rows with countRowsInTable

`countRowsInTable(jdbcTemplate, tableName)` returns the current number of rows in the specified table. This is a concise way to verify that data was inserted, deleted, or that fixture state has the expected row count.

Example:

```java
int orderCount = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");

assertThat(orderCount).isEqualTo(3);
```

This method executes the corresponding row-count query against the table. It returns an integer value, not a list of entities or column contents.

A complete test can verify counts before and after calling a repository:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void insertsOneOrder() {
        int before = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");

        orderRepository.save(new Order("ORD-100", "PAID"));

        int after = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");
        assertThat(after).isEqualTo(before + 1);
    }
}
```

Comparing before and after prevents the test from assuming the table starts empty. This is useful when the database has seed data or a test fixture already created multiple rows.

### 2.1. Counting with schema or qualified table names

The `tableName` parameter is the table name interpolated into the SQL statement. If the database uses schemas, you can pass a schema-qualified name in the syntax supported by the database, such as `sales.orders`. For names with uppercase letters, special characters, or SQL keywords, apply identifier quoting appropriate for the database.

`JdbcTestUtils` does not automatically infer schemas or normalize all naming rules across database engines. Use the exact table name recognized by JDBC/the database in SQL statements.

## 3. Counting rows conditionally with countRowsInTableWhere

`countRowsInTableWhere(jdbcTemplate, tableName, whereClause)` counts rows in the table matching a WHERE expression.

Example:

```java
int paidOrders = JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'PAID'"
);

assertThat(paidOrders).isEqualTo(2);
```

The `whereClause` argument contains only the condition expression, without writing the leading `WHERE` keyword. `JdbcTestUtils` appends the condition into the count query automatically.

Multiple conditions can be combined:

```java
int recentPaidOrders = JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'PAID' AND total_amount >= 100"
);
```

The WHERE expression follows the SQL syntax of the database in use. If checking nulls, ranges, dates, or multiple columns, write clear conditions matching the appropriate dialect.

### 3.1. Checking state before and after an operation

Example of a repository transitioning pending orders to paid status:

```java
@Test
void marksPendingOrdersAsPaid() {
    int pendingBefore = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PENDING'"
    );
    int paidBefore = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PAID'"
    );

    orderRepository.markAllPendingAsPaid();

    int pendingAfter = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PENDING'"
    );
    int paidAfter = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PAID'"
    );

    assertThat(pendingAfter).isZero();
    assertThat(paidAfter).isEqualTo(pendingBefore + paidBefore);
}
```

In the example above, `paidBefore` must be captured before the operation if the test wants to compare accurately against the initial count. Saving snapshots before and after helps assertions clearly express the data transition conditions.

### 3.2. Conditions with dynamic values

`countRowsInTableWhere` takes a raw SQL condition string, not a separate list of bind parameters. Do not concatenate untrusted input into `whereClause`. If the condition depends on runtime values, use `JdbcTemplate` with a prepared statement:

```java
int count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE status = ? AND customer_id = ?",
        Integer.class,
        status,
        customerId
);
```

This lets JDBC bind values with proper types and avoids errors when values contain quotes or special characters. `JdbcTestUtils` suits fixed conditions controlled by the test author; parameterized queries suit conditions that vary with data.

## 4. Deleting rows conditionally with deleteFromTableWhere

`deleteFromTableWhere(jdbcTemplate, tableName, whereClause)` deletes rows in the table matching the condition. The method returns the number of affected rows from the JDBC update result.

Example deleting cancelled orders:

```java
int deleted = JdbcTestUtils.deleteFromTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'CANCELLED'"
);

assertThat(deleted).isEqualTo(2);
```

You can verify state after deletion:

```java
int remaining = JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'CANCELLED'"
);

assertThat(remaining).isZero();
```

Counting before or after deletion helps the test verify the exact scope of affected data. If only checking the number of deleted rows, the return value from `deleteFromTableWhere` is usually enough.

### 4.1. Deletion condition must scope the exact rows

The `whereClause` condition is appended to the DELETE statement. If the condition is too broad or blank in a way that produces SQL without a WHERE clause, the test can delete more data than intended. Write specific conditions targeting the exact data.

Example:

```java
int deleted = JdbcTestUtils.deleteFromTableWhere(
        jdbcTemplate,
        "orders",
        "customer_id = 'C-100' AND status = 'CANCELLED'"
);
```

If binding a customer ID from a variable is needed, use a prepared statement instead of concatenating SQL strings:

```java
int deleted = jdbcTemplate.update(
        "DELETE FROM orders WHERE customer_id = ? AND status = ?",
        customerId,
        "CANCELLED"
);
```

## 5. Deleting all data in multiple tables with deleteFromTables

`deleteFromTables(jdbcTemplate, tableNames...)` deletes all rows from each passed table. The method accepts varargs table names and returns the total number of rows deleted across the tables.

Example:

```java
int deletedRows = JdbcTestUtils.deleteFromTables(
        jdbcTemplate,
        "order_items",
        "orders",
        "customers"
);
```

This method corresponds to executing DELETE operations on the listed tables. It does not remove table structures, reset schemas, or automatically substitute TRUNCATE.

### 5.1. Deletion order with foreign keys

If a child table references a parent table via a foreign key, the database may reject deleting parent rows while child rows still exist. In that case, delete child tables before parent tables unless the schema has an appropriate cascade policy.

Relationship example:

```text
customers
    |
    +----< orders
                |
                +----< order_items
```

The appropriate order to pass is typically:

```java
JdbcTestUtils.deleteFromTables(
        jdbcTemplate,
        "order_items",
        "orders",
        "customers"
);
```

The actual order depends on foreign key relationships and schema cascade rules. `JdbcTestUtils` does not inspect metadata to automatically sort dependencies across tables. The test must pass the list in an order permitted by the database.

### 5.2. Verifying cleanup results

After deleting, you can check each table:

```java
JdbcTestUtils.deleteFromTables(
        jdbcTemplate,
        "order_items",
        "orders"
);

assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "order_items")).isZero();
assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders")).isZero();
```

When a table contains seeded base data that must be kept, do not use `deleteFromTables` on the whole table. Delete by specific conditions or use fixtures with test-specific keys.

## 6. Dropping table structures with dropTables

`dropTables(jdbcTemplate, tableNames...)` executes `DROP TABLE` statements for the specified tables. Unlike `deleteFromTables`, this operation removes both the table structure and its data.

Example in a teardown step of a test-owned database/schema:

```java
@AfterAll
static void dropTestTables(@Autowired JdbcTemplate jdbcTemplate) {
    JdbcTestUtils.dropTables(
            jdbcTemplate,
            "order_items",
            "orders",
            "customers"
    );
}
```

The snippet illustrates the schema cleanup idea; injecting parameters into `@AfterAll` must be configured per JUnit Jupiter and the test class's SpringExtension, or teardown can be placed in a dedicated fixture.

`dropTables` is DDL, not a regular data cleanup operation. DDL rollback capability depends on the database engine; some databases auto-commit around DDL or do not roll back schema changes like DML transactions. Only use this method on temporary schemas/databases under the test's control.

If tables have foreign keys, views, or dependent objects, the drop order must also match schema dependencies. `JdbcTestUtils` does not compute dependency order automatically.

## 7. JdbcTestUtils and Spring Test transactions

`JdbcTestUtils` executes SQL through `JdbcTemplate`. The utility class itself does not start or end transactions. If the test has an active test-managed transaction and `JdbcTemplate` uses the same DataSource as the transaction manager, counting/deletion operations join that transaction on the same thread.

Example:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class JdbcCleanupTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void deletesFixtureRowsWithinTestTransaction() {
        int deleted = JdbcTestUtils.deleteFromTableWhere(
                jdbcTemplate,
                "orders",
                "test_batch = 'BATCH-1'"
        );

        assertThat(deleted).isGreaterThanOrEqualTo(0);
    }
}
```

When the test ends, Spring Test rolls back the test-managed transaction by default. If the DELETE operation ran inside that transaction, the deleted data may be restored after rollback. This is useful when a test only needs to verify deletion logic without altering the database after the test completes.

If the test has no enclosing transaction, the DELETE operation typically commits according to connection/autocommit settings or application-managed transactions. In that case, deleted data remains deleted after the test ends.

### 7.1. Cleaning up fixtures in @BeforeEach

When a test needs a table in a known state, you can clean fixtures before each test:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void prepareDatabase() {
        JdbcTestUtils.deleteFromTables(
                jdbcTemplate,
                "order_items",
                "orders"
        );
    }

    @Test
    void startsWithNoOrders() {
        assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders"))
                .isZero();
    }
}
```

With a test-managed transaction, the `@BeforeEach` callback runs inside the test method's transaction. Therefore, cleanup operations and subsequently created fixtures usually roll back together when the test finishes.

If tests run in parallel or share a database, clearing entire tables in `@BeforeEach` can affect other tests. In that case, use separate schemas/databases, data keyed by test ID, or appropriate transaction isolation.

### 7.2. Cleaning up data after a test

You can call `deleteFromTableWhere` in `@AfterEach` to delete data by test ID. However, when the callback still runs inside a test-managed transaction, the DELETE operation will roll back with the transaction. This means initial fixture data may reappear after the transaction ends.

If you need to clean up data committed outside the test transaction, use an independent cleanup mechanism and specify the transaction manager/connection explicitly. Do not assume a DELETE running in `@AfterEach` of a transactional test persists after rollback.

## 8. Complete example: counting, checking, and cleaning up data

Suppose the `orders` table has columns `id`, `customer_id`, `status`, and `total_amount`. The test uses `JdbcTemplate` to insert data, and `JdbcTestUtils` to verify counts and delete conditionally:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class JdbcTestUtilsExampleTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void insertFixtures() {
        jdbcTemplate.update(
                "INSERT INTO orders (id, customer_id, status, total_amount) VALUES (?, ?, ?, ?)",
                1001L, "C-100", "PAID", new BigDecimal("120.00")
        );
        jdbcTemplate.update(
                "INSERT INTO orders (id, customer_id, status, total_amount) VALUES (?, ?, ?, ?)",
                1002L, "C-100", "CANCELLED", new BigDecimal("50.00")
        );
        jdbcTemplate.update(
                "INSERT INTO orders (id, customer_id, status, total_amount) VALUES (?, ?, ?, ?)",
                1003L, "C-200", "PAID", new BigDecimal("200.00")
        );
    }

    @Test
    void countsAllRowsAndRowsMatchingCondition() {
        assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders"))
                .isEqualTo(3);

        assertThat(JdbcTestUtils.countRowsInTableWhere(
                jdbcTemplate, "orders", "status = 'PAID'"
        )).isEqualTo(2);

        assertThat(JdbcTestUtils.countRowsInTableWhere(
                jdbcTemplate, "orders", "customer_id = 'C-100'"
        )).isEqualTo(2);
    }

    @Test
    void deletesOnlyCancelledOrders() {
        int deleted = JdbcTestUtils.deleteFromTableWhere(
                jdbcTemplate,
                "orders",
                "status = 'CANCELLED'"
        );

        assertThat(deleted).isEqualTo(1);
        assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders"))
                .isEqualTo(2);
    }
}
```

Each test runs in its own transaction under Spring Test. Fixtures created in `@BeforeEach` belong to the test transaction, so data changes roll back after the test by default. As a result, the counting test and deletion test do not depend on execution order.

## 9. Distinguishing JdbcTestUtils from JdbcTemplate

`JdbcTestUtils` is a high-level utility class for a few common testing operations. `JdbcTemplate` is the more general JDBC API used to execute queries, updates, batches, map results, and bind parameters.

| Need | Suitable tool |
|---|---|
| Count all rows in a table | `JdbcTestUtils.countRowsInTable` |
| Count rows by a fixed SQL condition | `JdbcTestUtils.countRowsInTableWhere` |
| Delete rows by a fixed SQL condition | `JdbcTestUtils.deleteFromTableWhere` |
| Delete all rows across several tables | `JdbcTestUtils.deleteFromTables` |
| Drop tables in a test schema | `JdbcTestUtils.dropTables` |
| Query with bind parameters | `JdbcTemplate.query` / `queryForObject` |
| Insert/update with bind parameters | `JdbcTemplate.update` |
| Query entities or map DTOs | `JdbcTemplate.query` with `RowMapper` |
| Batch insert/update | `JdbcTemplate.batchUpdate` |
| Execute complex SQL or custom DDL | `JdbcTemplate` or an appropriate migration/schema tool |

For example, if you need to count by a dynamic customer ID, use `JdbcTemplate`:

```java
int count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE customer_id = ?",
        Integer.class,
        customerId
);
```

If you need to delete by a list of IDs, use named parameters or an appropriate SQL query instead of concatenating the list into `whereClause`. Using `JdbcTemplate` directly for dynamic queries ensures proper parameter binding.

## 10. Notes on table names and SQL fragments

`JdbcTestUtils` accepts table names and WHERE conditions as strings. These values are used to construct SQL, not as bind parameters.

Therefore:

- Only pass table/schema names controlled by the test author.
- Do not take table names directly from requests or untrusted input.
- Do not concatenate arbitrary runtime values into `whereClause`.
- For dynamic values, use prepared statements via `JdbcTemplate`.
- Check identifier quoting rules if table names contain uppercase letters, spaces, or SQL keywords.
- Use valid syntax for the running database, especially when conditions involve date/time types, booleans, or engine-specific functions.

Suitable fixed-condition example:

```java
JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'PAID' AND total_amount > 0"
);
```

Dynamic-value example that should use bind parameters:

```java
Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE status = ?",
        Integer.class,
        requestedStatus
);
```

## 11. Common mistakes

### Missing spring-test on the test classpath

If the IDE cannot find `JdbcTestUtils`, check the `spring-test` dependency. Projects using starter test may already include this module; plain Spring Framework projects must declare it directly.

### Using the wrong JdbcTemplate or DataSource

`JdbcTestUtils` executes on the template passed to it. If the template points to a different database/schema than the repository under test, count or delete results will not reflect the data the test cares about. Inject the same datasource or the exact test datasource.

### Adding WHERE to whereClause

The `whereClause` parameter only needs the condition expression, such as `status = 'PAID'`. Do not prepend the `WHERE` keyword since the method builds the SQL statement itself.

### Using bind placeholders in whereClause

`JdbcTestUtils` does not accept an array of bind parameter values for `countRowsInTableWhere` and `deleteFromTableWhere`. If you need `?` placeholders with runtime values, use `JdbcTemplate` with a prepared statement.

### Deleting parent tables before child tables

Foreign keys can prevent deleting rows in a parent table while child rows still reference them. Pass child tables before parent tables or configure cascading aligned with the test's goal.

### Confusing DELETE with TRUNCATE

`deleteFromTables` deletes rows using DELETE operations. It does not automatically truncate tables, does not guarantee resetting identities/sequences, and remains subject to foreign keys, triggers, and database rules.

### Using dropTables for routine data cleanup

`dropTables` removes the table structure. If you only need to empty data, use `deleteFromTables` or `deleteFromTableWhere`. DDL can have database-specific commit rules.

### Thinking cleanup in a transactional test persists after the test

If DELETE runs inside a test-managed transaction, the end-of-test rollback can restore the deleted rows. Understand the active transaction and when cleanup callbacks execute.

### Counting tables while other tests write in parallel

Count results can be affected by other transactions depending on isolation level and database. Avoid letting multiple tests share unisolated data tables; use separate schemas or fixtures with distinct keys.

## 12. Choosing the right method

| Goal | API |
|---|---|
| Know how many rows a table has | `countRowsInTable` |
| Count rows matching a fixed condition | `countRowsInTableWhere` |
| Delete a subset of rows | `deleteFromTableWhere` |
| Empty multiple tables | `deleteFromTables` |
| Remove tables from a test schema | `dropTables` |
| Condition needs dynamic bound values | `JdbcTemplate` with prepared statements |
| Need to inspect individual column contents | `JdbcTemplate`, `RowMapper`, and assertions |

`JdbcTestUtils` helps reduce boilerplate when tests need to count or clean up SQL data. Pass the right `JdbcTemplate`, use test-controlled table names and conditions, order cleanup by foreign keys, and understand the active transaction. For queries with dynamic values or complex data mapping, `JdbcTemplate` remains the better tool.
