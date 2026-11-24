# Learning Roadmap and Prerequisite Java & SQL Knowledge for Spring Framework Data Access

> **Orientation:** This lesson helps you identify foundational knowledge, learning sequence, hands-on exercises, and readiness criteria before diving deep into Spring Framework's data access mechanisms. You do not need to memorize every API upfront, but you must understand how data travels from Java to the database, what SQL/JDBC guarantee, and what Spring adds on top.

## 1. Destination and Knowledge Boundaries

After completing this roadmap, you should be able to:

1. Design simple relational tables with primary keys, foreign keys, and constraints; write accurate SQL queries and reason about performance.
2. Use JDBC to understand `Connection`, `PreparedStatement`, `ResultSet`, transactions, and resource management.
3. Explain the roles of `DataSource`, `JdbcTemplate`, `DataAccessException`, transaction managers, and `@Transactional` in Spring Framework.
4. Separate responsibilities across services, repositories/DAOs, and connection configuration; write read/write flows with transaction control.
5. Know when to start with Spring JDBC and when to explore JPA/Hibernate or Spring Data projects; test both success and rollback paths.

**Scope:** Spring Framework Data Access focuses on JDBC, ORM integration, and transaction management. Spring Data JPA, Spring Data JDBC, Spring Boot auto-configuration, relational DBMSs, and JPA/Hibernate are related components with distinct scopes. Do not conflate `Spring Framework`, `Spring Boot`, `Spring Data`, `JPA`, and `Hibernate`: Spring provides data access and transaction infrastructure; Boot streamlines configuration; Spring Data provides repository models; JPA is the specification; Hibernate is a popular ORM implementing JPA.

## 2. The Big Picture Before Learning APIs

```text
HTTP / CLI / batch job
        ↓
Application service       ← business rules, transaction boundaries
        ↓
Repository / DAO          ← SQL statements or entity operations
        ↓
JdbcTemplate / JPA        ← execution support, mapping, error handling
        ↓
DataSource / connection   ← connections, pooling, transaction resources
        ↓
Database                  ← tables, keys, indexes, constraints, transaction locks
```

- **Database** enforces data consistency via constraints and transactions; Java cannot replace `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, or `CHECK`.
- **JDBC** is Java's standard interface for working with relational databases through a driver.
- **Spring JDBC** reduces boilerplate around acquiring/closing connections, statements, result sets, and translating errors. It **does not** design SQL, keys, indexes, or proper transactions for you.
- **Spring transaction abstraction** coordinates the transaction manager and active resources. A transaction must wrap the entire business unit requiring atomicity; annotations take effect only when applied properly by Spring infrastructure.
- **ORM/JPA** maps objects to relational data and manages entity lifecycles; you still need to understand SQL, joins, indexes, transactions, and the queries emitted by the ORM.

A foundational question you should be able to answer: "When transferring 25 currency units from A to B, do the debit and credit need the same transaction, and what happens if the second operation fails?" Answer: both steps must be atomic; if an error occurs before commit, both changes must roll back.

## 3. Prerequisite Java Foundations

| Area | Must Understand | Hands-On Evidence |
| --- | --- | --- |
| Java 17+ and tooling | JDK/JRE, `javac`/`java`, classpath, Gradle/Maven, dependencies, basic logging | Create a project, add a JDBC driver, run a `main` class |
| OOP and design | classes, interfaces, constructors, encapsulation, dependency injection, service vs. DAO responsibilities | Write an `AccountRepository` interface and one implementation |
| Data types | primitives vs. wrappers, `String`, `enum`, `BigDecimal`, `LocalDate`/`Instant`, `null` | Store monetary amounts with `BigDecimal`; define timezone conventions |
| Collections and generics | `List<T>`, `Map<K,V>`, `Optional<T>`, loops, immutable DTOs, `record` | Map multiple rows into a `List<Account>` |
| Lambdas and functional interfaces | lambdas, method references, callback handling | Read and write `RowMapper<T>` and callbacks in `JdbcTemplate` |
| Exceptions and resources | checked/unchecked exceptions, `try-with-resources`, `finally`, error propagation | Close `Connection`/`Statement`/`ResultSet` even when queries fail |
| Basic concurrency | thread safety, shared mutable state, race conditions | Explain why two requests must not arbitrarily share the same `Connection` |
| Testing | JUnit, assertions, unit vs. integration tests | Verify successful updates and rollbacks when errors occur |

**Easy-to-miss details:**

- Use `BigDecimal` for monetary values and explicitly define precision/scale; avoid calculating money with `double` because binary floating point is not exact.
- `java.time` is superior to legacy date/time APIs; distinguish absolute instants (`Instant`) from business dates (`LocalDate`) and local date-times (`LocalDateTime`).
- `Optional` is well suited for expressing possibly-absent results at API boundaries; do not use it to hide mandatory fields or replace every nullable field.
- Java exceptions differ from SQL errors: know how to classify errors, and never swallow exceptions and pretend the business operation succeeded.
- Repositories should hold data access logic; services decide sequencing and business rules. Do not put SQL and transactions directly inside controllers.

**If your Java is still shaky:** practice an in-memory CRUD program first using an interface, implementation, and tests; then swap the implementation for JDBC. This separates Java design challenges from database challenges.

## 4. SQL and Relational Databases: Mandatory Minimum

### 4.1. Data Modeling and Data Types

Understand database/schema/table/row/column; primary keys (`PRIMARY KEY`), foreign keys (`FOREIGN KEY`), candidate keys, and `NOT NULL`, `UNIQUE`, and `CHECK` constraints. Pick appropriate data types: `BIGINT` for numeric identifiers, `VARCHAR` for bounded strings, `DECIMAL(p,s)` for exact values, and DATE/TIMESTAMP types according to your DBMS. Do not assume SQL across PostgreSQL, MySQL, H2, Oracle, and SQL Server is always identical.

Example schema:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL CHECK (total_amount >= 0),
    CONSTRAINT fk_orders_customers
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

INSERT INTO customers (id, full_name)
VALUES (1, 'An'), (2, 'Binh');

INSERT INTO orders (id, customer_id, total_amount)
VALUES (10, 1, 150.00), (11, 1, 50.00);
```

Understand why a nonexistent `orders.customer_id` must be rejected by the foreign key; why `DECIMAL` fits money; and why a `CHECK` constraint does not replace business validation in the service.

### 4.2. Reading, Writing, and Aggregating Data

Learn in sequence:

1. `SELECT`, `FROM`, `WHERE`, `ORDER BY`, `LIMIT`/DBMS pagination syntax.
2. `INSERT`, `UPDATE`, `DELETE`, `WHERE` predicates, and affected row counts.
3. `INNER JOIN`, `LEFT JOIN`, and how missing right-table data appears as `NULL`.
4. `GROUP BY`, `COUNT`, `SUM`, `HAVING`, `DISTINCT`, subqueries, and `EXISTS` when needed.
5. `NULL` and three-valued logic; use `IS NULL` instead of `= NULL`.
6. Indexes, data access order, `EXPLAIN`/execution plans, and the cost of reading many rows.
7. Transactions, ACID, isolation, locking, and concurrent update anomalies.

Example counting orders and total spend, including customers with no orders yet:

```sql
SELECT c.id,
       c.full_name,
       COUNT(o.id) AS order_count,
       COALESCE(SUM(o.total_amount), 0) AS spent
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
GROUP BY c.id, c.full_name
ORDER BY c.id;
```

With the inserted data, An has 2 orders totaling 200.00; Binh has 0 orders and total 0. `COUNT(o.id)` does not count `NULL` rows produced by `LEFT JOIN`. Using `COUNT(*)` could count a customer with zero orders as 1—a very common SQL bug.

### 4.3. Transactions and Concurrency

A transaction is a group of operations whose outcome is **all committed or all rolled back** on transaction-capable databases. Understand atomicity, consistency, isolation, and durability (ACID). Isolation levels such as `READ COMMITTED`, `REPEATABLE READ`, or `SERIALIZABLE` govern observable concurrency phenomena; exact behavior depends on the database.

Learn through three scenarios:
- **Money transfer:** debiting A and crediting B must share a transaction; verify balance and use a strategy to prevent race conditions.
- **Placing an order:** saving the order and line items as one business unit; failure when saving items must not leave a dangling order.
- **Concurrent updates:** two requests reading the same stock level and decrementing it can cause lost updates; learn `UPDATE ... WHERE quantity >= ?` with affected-row checks, pessimistic locking, or optimistic locking.

Keep the boundaries clear: **transactions do not replace constraints**, constraints alone do not solve every race condition, and indexes should be added when real queries need them. Query plans and performance must be measured on the target database with representative data.

## 5. JDBC Is the Essential Bridge Before Spring JDBC

JDBC introduces `Driver`, `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, and `SQLException`. A typical plain JDBC query flow is:

1. Obtain a `Connection` from `DataSource`.
2. Create a `PreparedStatement` with parameterized SQL using `?`.
3. Bind parameters with the right types and call `executeQuery` or `executeUpdate`.
4. Read the `ResultSet` and map each row to Java objects.
5. Close resources with `try-with-resources`; manage commit/rollback if controlling transactions manually.

The illustrative JDBC snippet below is **code inside a method**, assuming `DataSource dataSource` and `long customerId` exist, not a standalone program:

```java
String sql = "SELECT id, full_name FROM customers WHERE id = ?";
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            String fullName = rs.getString("full_name");
            System.out.println(id + ": " + fullName);
        }
    }
}
```

Requires importing `javax.sql.DataSource` and `java.sql.Connection`, `PreparedStatement`, `ResultSet`. Use parameter binding to pass **values** instead of concatenating user input into SQL strings. Placeholders cannot substitute table or column names; dynamic column lists must be validated against an application allowlist.

Understand `autoCommit`: when managing JDBC transactions manually, you typically disable auto-commit, execute the batch of statements, commit on success, roll back on error, and restore state or close the connection properly. When using Spring-managed transactions, **let Spring manage connections, commits, and rollbacks**—never call `connection.commit()` manually inside a DAO.

**JDBC stage gate:** write a read/write function yourself with parameter binding, resource cleanup, single-row mapping, and error handling; explain why repetitive connection management is error-prone.

## 6. Spring Framework Data Access API Map

| Component | Role | What to Practice |
| --- | --- | --- |
| `DataSource` | Supplies JDBC connections; production typically uses a connection pool | Configuring URL, credentials, pool, and lifecycle |
| `JdbcTemplate` | Executes SQL with callbacks, binding, mapping, and resource cleanup | `query`, `queryForObject`, `update`, `RowMapper` |
| `NamedParameterJdbcTemplate` | Named parameters instead of positional `?` | Using `:id`, `:status` for multi-parameter queries |
| `DataAccessException` | Spring's unchecked data access exception hierarchy | Inspecting exception types and root causes without swallowing errors |
| `PlatformTransactionManager` | Transaction coordination interface | Distinguishing transaction managers per technology |
| `DataSourceTransactionManager` | Transaction manager for a JDBC `DataSource` | Using with Spring JDBC in a sample application |
| `TransactionTemplate` | Programmatic callback-based transaction control | Testing commit and rollback programmatically |
| `@Transactional` | Declarative transaction boundaries via Spring infrastructure | Placing on service beans, verifying proxy interception |
| JPA `EntityManager` / Spring ORM | Working with entities and persistence context when choosing ORM | Recognizing mappings, lazy loading, flushing, and N+1 |

`JdbcTemplate` does not automatically start a new transaction per call. When a transaction is active and the same `DataSource` is managed properly, JDBC operations join that transaction. Without an enclosing transaction, commit behavior depends on the connection/driver and database configuration.

Distinguishing the three styles: plain JDBC gives direct control with heavy boilerplate; Spring JDBC still requires writing SQL and mappings with far less ceremony; JPA works primarily via entities and a persistence context, requiring you to understand ORM-generated SQL and query costs. For learning Data Access, master Spring JDBC **before** diving deep into ORM.

## 7. Dependency-Ordered Learning Roadmap

| Stage | Core Knowledge | Verification Exercise | Advancement Criterion |
| --- | --- | --- | --- |
| 0. Core Java | OOP, generics, `BigDecimal`, exceptions, Gradle/Maven, tests | In-memory account model and repository | Run tests and explain service/DAO boundaries |
| 1. Foundational SQL | DDL, DML, constraints, joins, aggregates, NULL | Create customers/orders; query total spend | Query accurately includes customers with zero orders |
| 2. Operational SQL | Indexes, execution plans, ACID, isolation, concurrency | Trigger FK errors, rollbacks, concurrent updates | Explain why data corrupts and how to observe it |
| 3. Plain JDBC | Driver, `DataSource`, prepared statements, result sets, resources | Single-table CRUD using JDBC | No SQL string concatenation from input; resources closed |
| 4. Spring JDBC | DI, `JdbcTemplate`, `RowMapper`, exception translation | Migrate JDBC DAO to JdbcTemplate | Equivalent results with cleaner access code |
| 5. Spring Transactions | `TransactionTemplate`, `@Transactional`, rollback, propagation | Transfer money with failure on step two | Verify data never ends up half-updated |
| 6. Testing & Operations | Integration tests, migrations, pools, logs/metrics, EXPLAIN | Run tests on a production-like engine | Tests cover success, rollback, and invalid inputs |
| 7. Expand as Needed | JPA/Hibernate, Spring Data, batching, locking | Compare SQL vs. ORM on the same use case | Explain N+1, mappings, and trade-offs |

Do not fix a rigid number of days for everyone. Advance when you can complete the exercise and explain errors; memorizing terminology without writing queries and tests creates an illusion of progress.

## 8. Complete Hands-On Lab: Spring JDBC + Transactions (Java 17)

This example uses **Spring Framework 6.2.3** and **H2 2.3.232** to study JDBC/transaction mechanics without starting a server or Spring Boot. Versions are pinned for reproducibility; in real applications, select supported versions and manage dependencies consistently. Requires JDK 17+ and Gradle (or an equivalent Gradle Wrapper).

Create these files:

```text
spring-data-access-roadmap/
├── settings.gradle
├── build.gradle
└── src/main/java/lesson/DataAccessDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-data-access-roadmap'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.3'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'lesson.DataAccessDemo'
}
```

`src/main/java/lesson/DataAccessDemo.java`:

```java
package lesson;

import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class DataAccessDemo {
    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:lesson;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE accounts (
                    id BIGINT PRIMARY KEY,
                    owner VARCHAR(100) NOT NULL,
                    balance DECIMAL(12, 2) NOT NULL CHECK (balance >= 0)
                )
                """);

        jdbc.update("INSERT INTO accounts VALUES (?, ?, ?)",
                1L, "Minh", new BigDecimal("100.00"));
        jdbc.update("INSERT INTO accounts VALUES (?, ?, ?)",
                2L, "Lan", new BigDecimal("40.00"));

        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));

        // Both UPDATEs commit together when the callback succeeds.
        tx.executeWithoutResult(status -> {
            jdbc.update("UPDATE accounts SET balance = balance - ? WHERE id = ?",
                    new BigDecimal("25.00"), 1L);
            jdbc.update("UPDATE accounts SET balance = balance + ? WHERE id = ?",
                    new BigDecimal("25.00"), 2L);
        });

        // The UPDATE below must roll back due to RuntimeException.
        try {
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE accounts SET balance = balance - ? WHERE id = ?",
                        new BigDecimal("10.00"), 1L);
                throw new IllegalStateException("demo rollback");
            });
        } catch (IllegalStateException expected) {
            // Ignore only the intentionally thrown error in this learning example.
        }

        jdbc.query("SELECT id, owner, balance FROM accounts ORDER BY id",
                (RowCallbackHandler) rs -> {
                    System.out.printf("%d | %s | %s%n",
                            rs.getLong("id"),
                            rs.getString("owner"),
                            rs.getBigDecimal("balance").toPlainString());
                });
    }
}
```

In the directory containing `build.gradle`, run `gradle run`; if the project has a Wrapper, use `./gradlew run` on Unix/macOS or `gradlew.bat run` on Windows. The program prints two data lines (excluding Gradle output):

```text
1 | Minh | 75.00
2 | Lan | 65.00
```

**Why is this output right?** The first block reduces Minh from 100.00 to 75.00 and increases Lan from 40.00 to 65.00. The second test block deducts 10.00 from Minh and intentionally throws `IllegalStateException`, so the Spring transaction manager rolls back that deduction. `JdbcTemplate` uses the transaction-bound connection for the same `DataSource`. `DriverManagerDataSource` is for simple demos, **not a production-suitable connection pool**. H2 is a test database; re-test on your target database because dialects, types, locking, and isolation can differ.

**Try variations to deepen understanding:** remove the transaction wrapping the first two statements and throw an exception between them to observe the risk of half-updated data; restore the transaction and confirm final state. Add a case that deducts more than the available balance to see `CHECK (balance >= 0)` protect the data, while also writing clear business validation before issuing SQL.

## 9. From TransactionTemplate to @Transactional

Once you understand callback-based transactions, move to declarative transactions on **public methods of Spring-managed service beans**, giving the transaction interceptor a real opportunity to apply:

```java
// Illustrative code showing business boundaries, not a standalone runnable program:
// AccountRepository and debit/credit methods are defined by the application.
@Service
public class TransferService {
    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        accounts.debit(fromId, amount);
        accounts.credit(toId, amount);
    }
}
```

This snippet needs Spring imports `@Service`, `@Transactional`, `BigDecimal`, plus a valid repository bean and enabled/configured transaction infrastructure; in a corresponding Spring Boot application, auto-configuration prepares many of these pieces. Never assume writing the annotation alone guarantees the transaction is active.

Rules you must know:

- `Propagation.REQUIRED` is the default: join an active transaction or open a new one if none exists. `REQUIRES_NEW` creates an independent transaction when supported by infrastructure; `NESTED` relies on savepoints and transaction manager/database support.
- In the default configuration, `@Transactional` rolls back when a `RuntimeException` or `Error` escapes; checked exceptions do not roll back automatically without declaring rules such as `rollbackFor`. Some newer Spring configurations can change global defaults, so check your specific project.
- Under standard proxy mode, internal calls from one method to another `@Transactional` method **on the same instance** bypass the proxy, so the annotation on the called method may not take effect as expected.
- `readOnly = true` is primarily an optimization hint, not a guarantee that the database will block all write statements.
- Never hold transactions open while waiting on slow HTTP calls or unnecessary non-database work. Database transactions do not automatically roll back external systems (emails, message brokers, HTTP).
- A transaction works properly only when participating DAOs use compatible connections and transaction managers; mixing independent resources demands explicit design.

Verification exercise: invoke the service through a Spring bean, have the `credit` step throw a runtime exception, query the database again, and assert both balances remain unchanged. Add a checked-exception test to confirm your actual rollback rules.

## 10. Next Topics After Spring JDBC

**JPA/Hibernate:** study `@Entity`, `@Id`, one-to-many/many-to-one relationships, persistence context, transient/managed/detached states, dirty checking, flushing, eager/lazy fetching, N+1, and transactions. Inspect the actual SQL emitted by the ORM. Never assume calling `save` always issues an immediate `INSERT`, or that accessing lazy collections after the context closes will succeed.

**Spring Data JDBC / Spring Data JPA:** these are Spring Data projects that help define repository and query abstractions for their respective data models. They are **not synonymous** with Spring JDBC `JdbcTemplate` or JPA/Hibernate; Spring Data JDBC's mapping and lifecycle differ from JPA. Choose them only when the problem fits and once you can read the underlying SQL and transactions.

**Real-world operations:** migrations via Flyway/Liquibase; connection pools and connection limits; transaction timeouts; query timeouts; batch updates; pagination; indexes and execution plans; safely logging sensitive parameters; idempotency for retries; optimistic/pessimistic locking; integration testing on a production-like engine. This is the stage after mastering fundamentals.

## 11. Common Mistakes and How to Spot Them Yourself

| Symptom | Root Cause to Investigate | How to Verify / Improve |
| --- | --- | --- |
| Join results multiply rows | 1-to-many join, wrong join predicate, wrong aggregation | Sketch cardinality, inspect a small dataset, compare `COUNT(*)` vs. `COUNT(column)` |
| Input causes SQL injection | String concatenation of input into SQL | Use parameter binding; allowlist dynamic identifiers |
| Half-finished writes succeed | Missing transaction wrapping the whole use case | Add an integration test throwing an error mid-operation |
| `@Transactional` seems inactive | Non-Spring-managed bean, self-invocation, missing config | Call through bean/proxy; inspect transaction logs |
| Transaction commits despite error | Exception swallowed or checked exception doesn't match rollback rules | Check escaping exceptions and rollback rules |
| Monetary amounts drift slightly | Using `double`, unclear scale/rounding | Use `BigDecimal` and explicit rounding rules |
| Queries slow down as data grows | Missing indexes, N+1 queries, returning too many rows | Inspect real SQL, `EXPLAIN`, pagination, and metrics |
| Connection or resource exhaustion | Unclosed JDBC resources, pool too small, long transactions | `try-with-resources` in plain JDBC; monitor pool and transaction duration |
| Tests pass on H2 but fail in production | Different dialect, constraints, isolation, or data types | Run integration tests on a production-like engine/version |
| Inventory goes negative or updates vanish | Race condition, missing atomic update/locking/constraints | Write concurrency tests; use conditional UPDATE and check affected rows |

Do not catch broad `Exception` and return "success" or a default value. Distinguish expected business errors, data errors, connection failures, and bugs; roll back, log with context, and propagate errors to the appropriate layer.

## 12. Mini Capstone Project to Complete the Roadmap

Build a **Mini Order Service** with `customers`, `products`, `orders`, `order_items`, and `stock`. No REST layer is needed in the first version; running from `main` or tests is enough.

1. **Schema:** define PK/FK/UNIQUE/NOT NULL/CHECK constraints and repeatable migrations for fresh environments.
2. **SQL:** write queries listing orders per customer, total spend, unsold products, and top products; explain why LEFT JOIN and specific indexes are needed.
3. **JDBC:** implement one query and one update using `PreparedStatement` with proper resource cleanup.
4. **Spring JDBC:** create a DAO using `JdbcTemplate` or `NamedParameterJdbcTemplate`; map rows to DTOs/records; check affected row counts.
5. **Transactions:** place an order by creating the order, inserting items, and decrementing stock in one transaction; inject a mid-flight failure to prove rollback.
6. **Concurrency:** have two threads order the last remaining item simultaneously; prevent negative stock or overselling using atomic conditional updates/locking and verify with tests.
7. **Quality:** write integration tests for success, nonexistent customer/product, invalid order quantity, constraint violations, rollbacks, and paginated queries. Inspect SQL logs, timings, and connection usage.

**Definition of Done:** every business operation has a clear transaction boundary; SQL never concatenates input; data is guarded by both constraints and code; tests demonstrate failure scenarios; and you can explain which tool is responsible for each guarantee.

## 13. Self-Assessing Readiness

You are ready to move on to deeper Spring Framework Data Access lessons when you can answer and demonstrate:

- How do `Connection`, `DataSource`, JDBC driver, and connection pool differ?
- Why does `PreparedStatement` protect input values better than SQL string concatenation, and what dynamic input can it *not* handle?
- How does `LEFT JOIN` differ from `INNER JOIN`, and why does `COUNT(o.id)` differ from `COUNT(*)` in the zero-order customer example?
- When should you choose `DECIMAL`/`BigDecimal`, and how should scale and rounding be standardized?
- What does Spring `JdbcTemplate` do on top of plain JDBC, and what does it still leave to you?
- What happens to two UPDATE statements on a mid-operation error with and without a transaction?
- Why does calling `@Transactional` within the same class sometimes have no effect in proxy mode?
- Do checked exceptions trigger rollback by default, and how do you prove it via a test instead of guessing?
- Why are H2 tests insufficient to validate queries, indexes, and locking on PostgreSQL or MySQL?
- When choosing an ORM, how do you detect N+1 queries and reason about transactions and the persistence context?

If any group feels uncertain, return to the corresponding stage and build a small reproducible test. The goal is **observable outcomes and mechanistic understanding**, not memorizing annotations.

## 14. Official Resources to Continue With

- Java JDBC API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/package-summary.html
- Spring Framework 6.2 – JDBC: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc.html
- Spring Framework 6.2 – Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html
- Spring Framework 6.2 – `@Transactional`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- PostgreSQL SQL Tutorial (for practicing relational SQL on a real DB): https://www.postgresql.org/docs/current/tutorial-sql.html

Consult documentation matching the **exact version branch running in your project**, and verify behavior against integration tests and the SQL executed by the database. This provides a solid foundation for learning Spring JDBC, transaction management, and ORM in an effective order.