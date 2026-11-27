# Differences When Replacing MySQL with H2 or Mock Databases

H2 and mock databases enable fast testing, but they do not fully reproduce MySQL behavior. H2 is a different database management system with only partial syntax compatibility; mock repositories or JDBC mocks only simulate calls in Java code and do not execute SQL. As a result, a test that passes on H2 or a mock can still fail on MySQL due to differences in data types, collations, SQL modes, locks, transactions, the optimizer, or DDL.

This lesson belongs to the **Testing** chapter of the **DATABASE_MYSQL** module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backup, and operations—testing must verify behavior on the exact database the application will use. This article distinguishes the scope of mocks, H2, and real MySQL, and guides you on choosing the right tool for the risk being tested.

## 1. Three Non-Equivalent Test Environments

| Environment | Executes SQL? | What it tests well | What it cannot prove |
|---|---|---|---|
| Mock with Mockito or fake repository | No | Service logic, branching, responses to simulated results/errors | Valid SQL, JPA mappings, constraints, transactions, locks, and MySQL behavior |
| H2 in-memory | Yes, via the H2 engine | Simple repositories, basic mappings, portable SQL queries, fast tests | Full MySQL compatibility, collations, SQL mode, optimizer, DDL, and InnoDB concurrency |
| Real MySQL or MySQL Testcontainers | Yes, via MySQL Server | SQL, schemas, migrations, data types, constraints, transactions, locks, driver, and server behavior | Automatically proving production safety if configuration, data, and load differ from production |

Choose the environment based on what the test is asking:

- If you need to verify which arguments a service passes to a repository, a mock may suffice.
- If you need to test a simple JPA mapping or a quick portable query, H2 can be useful.
- If you need to confirm that MySQL accepts DDL/SQL, applies a collation, enforces foreign keys, assigns `AUTO_INCREMENT`, handles transactions, or selects an expected plan, run against real MySQL.

A single test does not need to verify everything at once. Layer your tests to keep feedback fast while maintaining proof of MySQL compatibility at critical boundaries.

## 2. A Mock Database Is Not a Database

A mock is a fake object replacing a dependency in Java code. For example, a service calls `CustomerRepository.findByEmail()`; the test can configure the mock to return a customer or throw an exception.

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {
    @Mock
    private CustomerRepository customerRepository;

    @InjectMocks
    private CustomerService customerService;

    @Test
    void returnsCustomerWhenEmailExists() {
        Customer customer = new Customer();
        customer.setEmail("linh@example.com");

        when(customerRepository.findByEmail("linh@example.com"))
            .thenReturn(Optional.of(customer));

        Customer result =
            customerService.findByEmail("linh@example.com");

        assertEquals("linh@example.com", result.getEmail());
        verify(customerRepository).findByEmail("linh@example.com");
    }
}
~~~

This test checks service logic and the repository invocation contract. It runs no SQL, does not initialize Hibernate, does not verify column names, does not enforce unique keys, and does not prove the repository method can actually query MySQL.

If the mock repository returns the expected result, the test still passes even when:

- JPQL references the wrong property name or native SQL uses the wrong column name.
- An entity maps `BIGINT UNSIGNED`, `DECIMAL`, `JSON`, or timestamp types incorrectly.
- Migrations have not created the required indexes or constraints.
- The actual query violates MySQL's SQL mode or syntax.
- A foreign key rejects the insert.
- Transaction rollback or deadlock behavior differs from the service's assumptions.

Do not use mocks to test database semantics. Use them for application logic above the repository layer, where the goal is to verify how the service reacts to results and errors a dependency might return.

### Fake Repositories Also Have Limits

A fake repository can store objects in a `Map` or `List` to test services without a mocking framework. This can make tests easier to read, yet a fake only simulates behavior defined by its author. Even if the fake checks uniqueness or relationships in Java logic, it still does not prove MySQL enforces constraints the same way.

Keep fakes simple and only simulate the required contract. Do not build a "mini MySQL" in test code by rewriting an optimizer, transaction manager, or constraint engine.

## 3. H2 MySQL Compatibility Mode Is Only Partially Compatible

H2 has a MySQL compatibility mode, typically enabled via the JDBC URL:

~~~text
jdbc:h2:mem:testdb;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1
~~~

- `MODE=MySQL` instructs H2 to emulate some MySQL behaviors and syntax.
- `DATABASE_TO_LOWER=TRUE` controls how H2 stores unquoted identifiers; this option can help avoid certain letter-case discrepancies in tests.
- `DB_CLOSE_DELAY=-1` keeps the in-memory database alive after the last connection closes, until the JVM exits or the database is explicitly closed.

These options only adjust H2's behavior. They do not install MySQL Server, do not use InnoDB, do not swap H2's optimizer for MySQL's optimizer, and do not make all MySQL syntax or data types equivalent.

H2 may accept some MySQL syntax yet still differ in:

- String comparison rules and collations.
- Unsigned numeric types, `JSON`, `ENUM`, `SET`, and extended types.
- `AUTO_INCREMENT`/identity behavior and ID assignment.
- Built-in functions, operators, upsert syntax, and DDL.
- Transaction isolation, locks, and deadlocks.
- Metadata in `information_schema`.
- Indexes, execution plans, and optimizer statistics.
- SQL mode, implicit conversions, and warnings.

Compatibility mode is a helper for running simple SQL applications on H2. Do not treat it as proof that the application is compatible with MySQL.

## 4. Differences in Data Types and Conversions

Data types are one of the most common sources of bugs when replacing MySQL with H2.

| MySQL capability | Risk when testing with H2 |
|---|---|
| `BIGINT UNSIGNED` | Value ranges may differ; Java `long` also cannot represent the full 64-bit unsigned range |
| `DECIMAL(p,s)` | Conversion, rounding, and casting rules must be verified on MySQL |
| `JSON` and JSON functions | H2 does not share MySQL's storage format or full JSON function set |
| `ENUM`, `SET` | Types and value-validation rules may not be equivalent |
| `TIMESTAMP`, `DATETIME` | Time zone conversions and fractional-second precision may differ |
| Generated columns | Syntax, expressions, and indexing depend on MySQL |
| Spatial types | Functions and indexes are not necessarily equivalent |
| Character set/collation | Comparisons, uniqueness, and sort order may differ |

MySQL example using unsigned and JSON types:

~~~sql
CREATE TABLE api_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  payload JSON NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id)
) ENGINE=InnoDB;
~~~

An H2 test might need altered schemas or column types just to run. When that happens, the test is verifying a different schema from production. This is especially dangerous if the test is still treated as evidence for migrations or JPA mappings.

For `DECIMAL`, check both precision and scale. For example, a `DECIMAL(12,2)` column stores monetary values with two decimal places; tests should verify values are written and read accurately without being converted to floating point or rounded outside business rules.

For `BIGINT UNSIGNED`, verify the actual value range the system uses. If data can exceed `Long.MAX_VALUE`, Java `long` is insufficient; you need a representation such as `BigInteger` and must test conversions with Connector/J.

## 5. Collation, Charset, and String Comparison Rules

MySQL frequently uses case-insensitive collations for many schemas. For instance, a collation ending in `_ci` may treat `Linh@example.com` and `linh@example.com` as equal. A collation ending in `_ai` may ignore accent differences in comparisons.

This directly affects:

- `WHERE email = ?` results.
- `ORDER BY` and `GROUP BY`.
- Unique indexes and duplicate keys.
- Joins on string columns.
- Pagination ordered by string values.

MySQL example:

~~~sql
CREATE TABLE accounts (
  email VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL,
  PRIMARY KEY (email)
) ENGINE=InnoDB;
~~~

With that collation, two emails differing only in case collide on the primary key. If an H2 test uses different comparison rules, the test may allow both rows to be inserted and pass, whereas MySQL rejects the second row.

Testing uniqueness on MySQL:

~~~sql
INSERT INTO accounts (email)
VALUES ('Linh@example.com');

-- Expect duplicate key under the chosen collation
INSERT INTO accounts (email)
VALUES ('linh@example.com');
~~~

Do not assume emails must always be case-insensitive; that is a business rule to decide. The key point is that tests must use the exact charset/collation of the target schema.

Table names can also behave differently depending on the OS and `lower_case_table_names` setting. On some Linux systems, table names are case-sensitive; in other environments, they may not be. H2 has its own identifier normalization rules. Use consistent casing for table and column names in entities, native queries, and migrations, and test on MySQL with production-like configuration.

## 6. SQL Mode and MySQL-Specific Syntax

SQL mode controls how MySQL handles out-of-range values, invalid dates, `GROUP BY`, and similar cases. H2 does not fully replicate MySQL's SQL modes.

For example, MySQL with `ONLY_FULL_GROUP_BY` rejects a query selecting a column that is neither in `GROUP BY` nor functionally dependent on the grouping columns. An H2 test might accept the query or handle it differently, so that test does not prove the query is valid under production's SQL mode.

MySQL-specific syntax and functions that should run on MySQL include:

- `INSERT ... ON DUPLICATE KEY UPDATE`.
- `INSERT IGNORE` and `REPLACE`.
- `LAST_INSERT_ID()`.
- `GROUP_CONCAT()`.
- MySQL JSON functions.
- `LOAD DATA [LOCAL] INFILE`.
- MySQL-specific index, generated column, partition, and DDL syntax.

Upsert example:

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-001', 10)
ON DUPLICATE KEY UPDATE
  quantity = quantity + VALUES(quantity);
~~~

Syntax and deprecation warnings for expressions can depend on the MySQL version. Test against the exact target server version and use syntax supported by that version. H2 MySQL mode is not an oracle for MySQL upsert behavior.

During tests, record `@@SESSION.sql_mode` and related settings. If production enables strict mode, MySQL tests should run with the corresponding mode; if the test container uses different defaults, results can still diverge.

## 7. Constraints and Locking Behavior

MySQL InnoDB enforces `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `NOT NULL`, and `CHECK` constraints depending on the version. A fake repository enforces no database constraints unless the fake author reimplements them. H2 has its own constraint engine and can differ in syntax, validation timing, or execution details.

For example, if an entity has an `Order.customer` relationship, a mock test can save an `Order` referencing a nonexistent `Customer` ID. MySQL with a foreign key will reject the `INSERT`:

~~~sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (id),
  KEY idx_orders_customer_id (customer_id),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;
~~~

Foreign keys must be tested on real MySQL if the application relies on InnoDB-enforced integrity. Do not check only the Java object graph, because data may also be written via native SQL, batch jobs, or other applications.

MySQL InnoDB also uses row locks, gap locks, and next-key locks depending on isolation level, indexes, and queries. H2 does not accurately reproduce InnoDB's locking mechanisms. An H2 test running two transactions without deadlocking does not prove MySQL will not deadlock.

## 8. Transactions, Isolation, and Concurrency

MySQL InnoDB defaults to `REPEATABLE READ` in many common configurations. H2 has a different default isolation level and different lock implementations. When testing transactions, be clear about what you are verifying:

- Does rollback undo DML?
- Does a second transaction see uncommitted data?
- How do two transactions updating the same row behave?
- Does a deadlock or lock wait timeout occur?
- When do unique or foreign key violations trigger?
- Does the connection pool return connections with ended transactions?

Do not use H2 to verify exact InnoDB lock behavior. For concurrency tests, use real MySQL, two independent connections, and synchronize execution timing with latches/barriers rather than relying on `Thread.sleep()`.

Two-transaction test principle example:

~~~text
Thread A                         Thread B
   |                                |
   | BEGIN                          | BEGIN
   | UPDATE account id=1            |
   |                                | UPDATE account id=1
   | holds row lock                 | waits for lock
   | COMMIT                         |
   |                                | proceeds or times out
   v                                v
Compare results, wait times, and MySQL errors
~~~

Use two physical connections so the two threads truly act as two separate MySQL sessions. If the test framework opens a transaction on the test thread and repositories use the same transaction-bound connection, two calls may not produce real concurrency.

In Spring, tests annotated with `@Transactional` typically roll back at completion. That helps isolate data, but it cannot automatically test all post-commit behaviors, transaction synchronizations, or interactions across multiple transactions. Tests that require real commits should control transactions explicitly via `TransactionTemplate`, a transaction manager, or separate connections, followed by controlled cleanup.

## 9. Indexes and Execution Plans Cannot Be Inferred from H2

The same SQL statement and index can produce different plans on H2 versus MySQL. The two engines have different optimizers, statistics, cost models, and storage layouts.

Example:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);

EXPLAIN
SELECT id, total_amount
FROM orders
WHERE customer_id = 1001
ORDER BY created_at DESC
LIMIT 20;
~~~

An H2 plan does not prove MySQL will use that index. To inspect on MySQL:

~~~sql
EXPLAIN FORMAT=JSON
SELECT id, total_amount
FROM orders
WHERE customer_id = 1001
ORDER BY created_at DESC
LIMIT 20;
~~~

On MySQL 8.0.18 and later, you can use `EXPLAIN ANALYZE` on safe read queries to view actual timing and row counts at each iterator. Evaluate plans on data with production-like distribution; a table with a few rows does not represent a table with millions of records.

Factors that change plans include:

- Table size and data distribution.
- Index cardinality and histograms.
- Column order in composite indexes.
- Collation and data types in join conditions.
- `LIMIT`, `ORDER BY`, `GROUP BY`, and subqueries.
- Optimizer statistics and MySQL version.

Use H2 to test portable query result logic; use MySQL to test MySQL execution plans and performance.

## 10. DDL, Migrations, and Stored Programs

A migration can succeed on H2 yet fail on MySQL due to syntax or semantic differences:

- `JSON`, `ENUM`, `UNSIGNED` types, or generated columns.
- Index and foreign key syntax.
- `AUTO_INCREMENT` and default expressions.
- Stored procedures, functions, triggers, and events.
- `DEFINER`, `SQL SECURITY`, and privileges.
- Partitioning, tablespaces, and online DDL.
- Implicit commits and metadata locks.

MySQL has implicit commit rules for many DDL statements. H2 has its own transaction/DDL behavior. A migration runner may execute scripts differently across the two engines; an H2 test does not confirm that a migration will run properly on MySQL.

If the application uses Flyway or Liquibase, run migrations on MySQL in CI. Verify both a fresh path from an empty database and an upgrade path from an earlier schema version. Do not use H2 as the sole check for production DDL.

Example post-migration schema verification:

~~~sql
SHOW CREATE TABLE orders;
SHOW INDEX FROM orders;
SELECT
  TABLE_NAME,
  CONSTRAINT_NAME,
  CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE();
~~~

Metadata queries should run on the target MySQL because schemas and columns in `information_schema` can differ by engine.

## 11. Testing Repositories with MySQL Testcontainers

Testcontainers launches MySQL Server inside a container for tests. Tests send SQL through real Connector/J and can exercise migrations, Hibernate, constraints, transactions, and queries just as on MySQL.

The example below uses Spring Boot 3.1+ with `@ServiceConnection`:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class CustomerRepositoryMySqlTest {

    @Container
    @ServiceConnection
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4.4")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void enforcesUniqueEmailUsingMySqlCollation() {
        customerRepository.saveAndFlush(
            new Customer("Linh@example.com")
        );

        assertThrows(
            DataIntegrityViolationException.class,
            () -> customerRepository.saveAndFlush(
                new Customer("linh@example.com")
            )
        );
    }
}
~~~

Key imports in the example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertThrows;
~~~

For the collation check in this example to be meaningful, the migration creating the email column must declare a case-insensitive collation, such as an appropriate collation for MySQL 8.4. If the column uses a case-sensitive collation, adjust the expected outcome to match the actual schema.

Annotations and dependencies:

- `@Testcontainers` enables Testcontainers lifecycle integration for the test.
- `@Container` manages the container lifecycle.
- `@ServiceConnection` (Spring Boot 3.1+) supplies container connection details to auto-configuration.
- `@AutoConfigureTestDatabase(replace = NONE)` prevents `@DataJpaTest` from replacing the MySQL `DataSource` with an embedded database.
- `MySQLContainer` provides MySQL Server and a dynamic JDBC URL.

Add the corresponding test dependencies managed by Spring Boot:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-testcontainers</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>mysql</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>junit-jupiter</artifactId>
  <scope>test</scope>
</dependency>
~~~

A working Docker runtime is required on the test machine or CI runner. On older Spring Boot versions without `@ServiceConnection`, register the URL, username, and password with `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void datasourceProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", mysql::getJdbcUrl);
    registry.add("spring.datasource.username", mysql::getUsername);
    registry.add("spring.datasource.password", mysql::getPassword);
}
~~~

Whichever approach you use, verify the test actually connects to MySQL by checking `SELECT VERSION()` or JDBC metadata. Do not rely solely on the container class name.

## 12. Choosing a Container Version and Configuration Matching Production

Testing on MySQL 8.4 does not automatically prove the application is compatible with all MySQL 8.0.x releases or a managed database service with different settings. The container example uses patch tag `8.4.4` to illustrate version pinning; replace it with the patch version or image digest matching production or your target upgrade version.

Compare:

- MySQL server version and patch release.
- Connector/J version and JDBC URL properties.
- SQL mode.
- Database/table/column character sets and collations.
- Server and session time zones.
- Authentication plugin and TLS if testing connectivity.
- Storage engine, isolation level, and related settings.
- Migration version and schema.
- Variables such as `lower_case_table_names` and `auto_increment_increment` if the application depends on them.

Do not use floating container tags like `latest` in compatibility tests. A tag can point to a newer version on the next pipeline run and alter results. Pin a patch version or image digest for reproducibility; update the pin deliberately when testing upgrades.

If production uses custom settings, launch the container with a matching test config file or explicit server flags. Avoid copying production secrets or personal data into test containers.

## 13. Tests That Should Run on Real MySQL

Use MySQL integration tests for server-dependent behaviors:

| Category | Test examples |
|---|---|
| Schema and migrations | Flyway/Liquibase from an empty database and upgrading old schemas |
| Data types | `JSON`, unsigned, decimal precision, timestamp precision, generated columns |
| Constraints | Collation-aware unique constraints, foreign keys, `CHECK`, `NOT NULL` |
| Specific SQL | Upsert, `LAST_INSERT_ID`, JSON functions, `GROUP_CONCAT` |
| Transactions | Commit/rollback, isolation, read visibility |
| Concurrency | Row locks, deadlocks, lock wait timeouts, unique races |
| Indexes/plans | `EXPLAIN`, `EXPLAIN ANALYZE`, index selection on representative data |
| Stored programs | Procedures, functions, triggers, events, `DEFINER`, and privileges |
| Driver | Generated keys, batch rewrite, time zones, reconnect |
| Connection security | Accounts, `GRANT`, roles, TLS, and authentication plugins |

You do not need to run every slow test after every minor edit. You can organize your pipeline as:

- Fast unit tests with mocks on every commit.
- Fast repository/JPA tests on a MySQL container in CI.
- Migration, concurrency, performance, and compatibility suites on important pull requests or nightly schedules.
- Smoke tests on staging after deploying a new version.

Testcontainers remains integration testing; it does not replace production-like benchmarks or failover testing on real topologies.

## 14. Common Mistakes

| Mistake | Why it is dangerous | How to address |
|---|---|---|
| Mocking a repository and concluding SQL is valid | No SQL is executed at all | Run repository tests on MySQL |
| Enabling only `MODE=MySQL` in H2 | Emulates only a subset of behavior | Use H2 for portable SQL; verify MySQL-specific behavior on a real server |
| Changing `JSON` to `VARCHAR` in tests | Test schema no longer matches production | Use a MySQL container for mappings and JSON functions |
| Using H2 to test collations | Comparison rules may differ | Create schemas with real collations on MySQL |
| Using H2 to test deadlocks | Lock engine differs from InnoDB | Use two independent MySQL sessions and transactions |
| Using H2 as the sole Flyway check | DDL and implicit commits can differ | Run migrations on target MySQL |
| `@DataJpaTest` accidentally replacing `DataSource` | Tests run on an embedded DB despite MySQL config | Use `replace = NONE` and verify server version |
| Using the `latest` image | Test results are non-reproducible | Pin a version or digest |
| Testing only on an empty database | Misses cardinality and legacy data issues | Seed representative data with duplicates and edge cases |
| Running concurrency inside one test transaction | Does not create independent sessions | Use a separate connection/transaction for each actor |

## 15. Risk-Based Test Design Workflow

A practical workflow:

1. **Identify the contract to verify:** service logic, JPA mapping, SQL, constraints, transactions, or performance.
2. **Choose the environment:** mocks for logic, H2 for portable parts, MySQL container for MySQL semantics.
3. **Keep schemas consistent:** use real migrations instead of creating a simplified H2 schema that diverges from production.
4. **Use meaningful data:** include normal rows, boundaries, `NULL`s, duplicates, foreign keys, and key data distributions.
5. **Test with the right driver:** Connector/J version and properties must match the application environment.
6. **Verify the engine:** check server version, SQL mode, collation, time zone, and storage engine.
7. **Cross-check outcomes:** inspect both data persisted in the DB and application behavior.
8. **Keep tests reproducible:** pin images, seed data, migration versions, and configuration.
9. **Tier pipeline speed:** fast unit tests, MySQL integration tests in CI, performance/upgrade suites scheduled or pre-release.
10. **Document limitations:** note which MySQL behaviors H2 tests cannot prove, and that container tests do not replace production-like topology testing.

## 16. Checklist

**When using mocks**

- [ ] Use only to test service logic and dependency interactions.
- [ ] Do not treat mocks as proof of valid SQL, JPA mappings, or constraints.
- [ ] Maintain corresponding integration tests for critical repository behaviors.

**When using H2**

- [ ] Determine whether the queries and schemas under test are truly portable.
- [ ] If using MySQL mode, clearly document that it is only a compatibility subset.
- [ ] Do not use H2 results to draw conclusions about collations, locks, the optimizer, or MySQL DDL.
- [ ] Never silently alter production schemas just to fit H2.

**When using real MySQL**

- [ ] Run a MySQL container matching or close to the production version.
- [ ] Use real Connector/J and real migrations.
- [ ] Set the right SQL mode, charset/collation, and time zone.
- [ ] Verify constraints, transactions, and generated keys.
- [ ] Use independent connections for concurrency tests.
- [ ] Pin images and seed data so tests remain reproducible.

## 17. Key Takeaways

- Mocks test dependency-call logic; they execute no SQL and do not simulate InnoDB.
- H2 MySQL mode is only partially compatible, not MySQL Server.
- Differences in data types, collations, SQL modes, time zones, `AUTO_INCREMENT`, and syntax can let H2 tests pass while MySQL fails.
- Transaction isolation, row/gap locks, and deadlocks must be tested on InnoDB.
- H2's optimizer and execution plans do not predict MySQL plans.
- DDL and migrations must run against the target MySQL version.
- Use Testcontainers to test Spring Data JPA, Connector/J, migrations, and constraints against real MySQL.
- With Spring Boot `@DataJpaTest`, prevent embedded database replacement when targeting a MySQL container.
- Pin MySQL version, configuration, and data so test results stay reproducible.
- Pick tools according to risk: do not force every test to boot a database, but never skip MySQL testing at critical boundaries.

A reliable test suite uses mocks for application logic, H2 for genuinely portable SQL, and real MySQL for MySQL-dependent behavior. When schema, driver, configuration, and test data closely match the deployment environment, test results provide trustworthy evidence for releasing.

## References

- [H2 Database Engine: Features and Compatibility Modes](https://www.h2database.com/html/features.html#compatibility)
- [Spring Boot Reference: Testing and Auto-configured Data JPA Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot Reference: Testcontainers Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers for Java: MySQL Module](https://java.testcontainers.org/modules/databases/mysql/)
- [MySQL 8.4 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual: Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
