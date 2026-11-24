# Distinguishing Resource Management, Transaction Management, and Data Mapping in Spring Framework Data Access

## 1. Goal and Overall Picture

When a Java application reads or writes a database, three independent questions typically appear within the same call:

1. **Resource management:** Who acquires and returns the connection, closes statements and result sets? How long do resources live?
2. **Transaction management:** Which operations must succeed or fail together? Who decides `commit`, `rollback`, and the transaction boundary?
3. **Data mapping:** How do rows and columns from the database become Java objects, and vice versa?

For example, consider a service transferring 30 units from account A to B. It needs a connection to execute SQL (**resources**), must ensure debiting A and crediting B form a single consistent unit (**transaction**), and converts `account(id, balance)` rows into `Account` objects to return results (**mapping**). The same class may use all three mechanisms, yet none of them replaces the other two.

| Aspect | Resource Management | Transaction Management | Data Mapping |
| --- | --- | --- | --- |
| Core question | *What* is acquired, used, and released, and *when*? | Which operations belong to the same unit of work? | How are SQL values and Java types converted? |
| Typical objects | `DataSource`, JDBC `Connection`, `PreparedStatement`, `ResultSet`, JPA `EntityManager` | `PlatformTransactionManager`, `@Transactional`, `TransactionTemplate` | `RowMapper`, `ResultSetExtractor`, JPA `@Entity`/`@Column`, DTO projection |
| Desired outcome | No leaked connections/cursors; correct connection used in context | Proper `commit` or `rollback` for the entire unit of work | Accurate types, columns, and relationships |
| Typical failures | Connection pool exhaustion, unclosed cursors | Partial writes, missing rollback, locks held too long | Wrong column names, type mismatches, missing or duplicate data |
| Does NOT mean | Automatically guaranteeing atomicity | Automatically closing arbitrary custom resources | Automatically opening a transaction or guaranteeing committed data |

Do not conflate these three concepts just because a single `JdbcTemplate.query(...)` call or JPA repository can hide all three behind one API.

## 2. Resource Management: Lifecycle of Connections and Data Access Objects

### 2.1. Plain JDBC and Resource Closing Responsibility

In JDBC, a typical query obtains a `Connection` from a `DataSource`, creates a `PreparedStatement`, executes it, and reads a `ResultSet`. When writing JDBC manually, use `try-with-resources` for every resource you own:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id, balance FROM account WHERE id = ?")) {
    statement.setLong(1, accountId);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            long id = rows.getLong("id");
            int balance = rows.getInt("balance");
            // Here we are only reading and converting data.
        }
    }
}
~~~

*This illustrative snippet sits inside a method that already has `dataSource` and `accountId`; it is not a standalone Java program.* `try-with-resources` closes `ResultSet`, `PreparedStatement`, and `Connection` even when an exception occurs. With a connection pool, calling `Connection.close()` usually **returns the logical connection to the pool**, rather than necessarily closing the physical socket. Failing to release resources can exhaust the pool even when SQL executes very quickly.

### 2.2. How Spring Reduces Manual Resource Handling

- `JdbcTemplate` creates/closes `Statement` and `ResultSet` and acquires/releases `Connection` via Spring's mechanism, letting developers focus on SQL and results.
- `DataSourceUtils.getConnection(dataSource)` is aware of the connection bound to an active Spring transaction; `DataSourceUtils.releaseConnection(...)` avoids returning a connection still needed by the transaction too early. Do not manually grab a separate connection via `dataSource.getConnection()` and assume it always participates in the active transaction.
- `DataSourceTransactionManager` can bind a `Connection` to the executing thread when a transaction starts; `JdbcTemplate` operations sharing the same `DataSource` participate in that context. After `commit`/`rollback`, the transaction manager cleans up state and releases the connection.
- With JPA, `EntityManager` and the persistence context have their own lifecycle, usually tied to a transaction; the provider may delay acquiring a JDBC connection. Managing an `EntityManager` does not mean a physical `Connection` is always held from start to finish.

`DataSource` is the connection supplier. `DriverManagerDataSource` is suitable for lessons or experiments and **has no pool**; production applications typically use a pool such as HikariCP, monitoring active/idle/waiting counts, wait times, and leaks. Properly closing resources says nothing about whether **two UPDATE statements committed together**.

### 2.3. Resource Scope Does Not Necessarily Equal Method Scope

Without a Spring transaction, two `jdbcTemplate.update(...)` calls can acquire two separate connections and be auto-committed individually by the database according to auto-commit settings. Inside a properly configured JDBC transaction, Spring ensures the statements share the connection associated with the transaction. Having 20 connections in a pool does not mean a single transaction uses all 20 connections.

Conversely, keeping a transaction open too long can hold a connection and locks for an extended duration even if each individual `ResultSet` was closed promptly. Always measure **resource lifecycles** and **transaction durations** as distinct signals.

## 3. Transaction Management: Consistency Boundaries

### 3.1. What Problem Do Transactions Solve?

A transaction groups changes that must satisfy a shared business invariant. For instance, a transfer requires:

1. Checking preconditions and balance using an appropriate concurrency control mechanism.
2. Debiting A.
3. Crediting B.
4. Committing both, or rolling back both if a required step fails.

If each `UPDATE` auto-commits separately, a failure between step 2 and step 3 leaves corrupted data, **even if every connection and statement was closed cleanly**. Transactions solve atomicity; isolation levels and locking/versioning govern how concurrent transactions affect one another. A transaction does not prevent a negative balance if business logic omits checks, nor does it automatically solve every race condition.

### 3.2. Mechanisms in Spring

Spring defines `PlatformTransactionManager` for the imperative transaction model; two common implementations are:

- `DataSourceTransactionManager`: coordinates JDBC transactions over a `DataSource`.
- `JpaTransactionManager`: coordinates JPA transactions via `EntityManagerFactory`; when mixing JPA with JDBC, verify how they participate in the same transaction and configure the corresponding data source properly.

Two common ways to define boundaries:

**Declarative** using `@Transactional` on a service method invoked through a Spring proxy/AOP:

~~~java
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, int amount) {
        jdbc.update(
            "UPDATE account SET balance = balance - ? WHERE id = ?",
            amount, fromId);
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId);
    }
}
~~~

*This snippet requires a Spring application configured with `JdbcTemplate` and a transaction manager; it illustrates the boundary and omits balance/affected-row checks.* The proxy opens or joins a transaction before the method runs, then commits on normal completion or rolls back per rollback rules.

**Programmatic** using `TransactionTemplate`: calling `execute(...)` or `executeWithoutResult(...)`, well suited for small programs or where explicit block-level control is desired. The runnable example in section 5 uses this approach to avoid booting a full Spring container.

### 3.3. Settings You Must Understand Properly

- **Propagation:** `REQUIRED` (default) joins an existing transaction or creates a new one if none exists. `REQUIRES_NEW` creates an independent transaction, typically needing an extra connection, which can put pressure on the pool. `NESTED` uses savepoints when supported by the transaction manager and resource; it is not synonymous with `REQUIRES_NEW`.
- **Isolation:** the database isolation level controls visibility and which concurrency anomalies can occur; choose based on consistency requirements and DB capabilities rather than using it as a substitute for conditional updates.
- **Default rollback:** on a transaction managed by `@Transactional`, `RuntimeException` and `Error` trigger rollback; checked exceptions do not trigger rollback by default unless configured with `rollbackFor`. Never assume every exception rolls back.
- **readOnly:** `@Transactional(readOnly = true)` is a hint to the transaction manager, JDBC driver, or provider depending on the environment; it is not a reliable write-protection barrier.
- **Timeout:** helps bound transaction duration when supported by the system and involved operations; it does not replace query/connection timeouts or retry management.

**Common Spring AOP limitations:** when one method in a bean calls another `@Transactional` method via `this`, the internal call can bypass the proxy, so the expected transaction is not created. Calls via `@Async` or a new thread also do not automatically inherit the imperative transaction bound to the caller's thread. Reactive transactions (R2DBC) have their own context and must not be reasoned about using JDBC's `ThreadLocal` rules.

**Distinguishing rollback from business compensation:** a database transaction does not automatically roll back HTTP calls, emails, or external payment requests. For cross-system effects, design patterns such as outbox, idempotency, or saga depending on the problem.

## 4. Data Mapping: From Rows and Columns to Java Models

### 4.1. Spring JDBC: Explicit Mapping

JDBC returns a `ResultSet` organized by SQL columns and types. `RowMapper<T>` turns **one row** into **one object**; `JdbcTemplate.query(...)` iterates over multiple rows, whereas `queryForObject(...)` expects the exact row count required. Example:

~~~java
record Account(long id, int balance) {}

Account account = jdbcTemplate.queryForObject(
    "SELECT id, balance FROM account WHERE id = ?",
    (rs, rowNum) -> new Account(
        rs.getLong("id"),
        rs.getInt("balance")
    ),
    1L
);
~~~

*This snippet assumes `jdbcTemplate` and an `account` table exist; a complete example appears in section 5.* The `RowMapper` lambda determines exact column names, type conversions, and object construction. It does **not** decide when to open a transaction, commit, roll back, or return a connection to the pool. `ResultSetExtractor` is helpful when aggregating multiple rows into one structure; `BeanPropertyRowMapper` can map by property naming conventions, though you must watch column names, data types, and bean instantiation rules.

Do not confuse mapping with business validation. Converting `balance` from SQL `INTEGER` to Java `int` does not prove the balance is valid. `NULL` values, date/time types, decimals, enums, and timezones all require suitable representations; real monetary data generally requires proper precision types and rounding policies rather than taking `int` from this example as a universal rule.

### 4.2. JPA/ORM: Mapping Objects and Relationships

In JPA, mappings can be declared with `@Entity`, `@Id`, `@Column`, `@ManyToOne`, and relationship annotations. The provider translates entity state ↔ SQL statements, maintaining an identity/persistence context, dirty checking, and flushing. This is a richer mapping and persistence-coordination layer than `RowMapper`, yet it still needs transactions so changes requiring consistency commit together.

Distinguish clearly:

- **Mapping** defines which columns/relationships correspond to which fields/objects.
- **Persistence context** tracks managed entities and their modifications.
- **Flush** synchronizes pending changes into SQL; **flush does not mean commit**.
- **Transaction** decides commit/rollback for the generated SQL.
- **Resource management** manages the `EntityManager`, JDBC connections, and underlying resources.

A `LazyInitializationException` usually indicates lazy data was accessed after the required session/persistence context was no longer active; that is a fetch-boundary and context-lifecycle issue, and increasing the connection pool or sprinkling transactions everywhere will not fix the root cause. Fetch strategies, projections, and N+1 queries also affect performance, yet do not replace transactional consistency.

### 4.3. Spring Data Repositories Hide Details Without Erasing Boundaries

A repository like `JpaRepository` can simultaneously provide read/write APIs, use an `EntityManager`, map entities, and participate in transactions. A simple interface does not mean a single repository is responsible for setting business boundaries across multiple repositories. If an operation must mutate two aggregates/DAOs atomically, the transaction boundary usually belongs on the **service** wrapping the whole operation. Converting an entity to a DTO for an API response is a separate transformation step, not a commit.

## 5. Runnable Example: Three Responsibilities in One Spring JDBC Program

This example uses **JDK 17+**, **Maven 3.9+**, Spring JDBC 6.1.14, and H2 2.2.224. H2 runs in memory so you can observe commit and rollback behavior. Create the structure:

~~~text
spring-data-concerns/
├── pom.xml
└── src/main/java/demo/ConcernsDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-data-concerns</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/ConcernsDemo.java`**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class ConcernsDemo {
    record Account(long id, int balance) {}

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:concerns;DB_CLOSE_DELAY=-1", "sa", "");
        dataSource.setDriverClassName("org.h2.Driver");

        // Resources: JdbcTemplate acquires/returns connections and cleans up statements/result sets.
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE account (id BIGINT PRIMARY KEY, balance INT NOT NULL)");
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1L, 100);
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2L, 50);

        // Transaction: both update statements commit as one unit.
        TransactionTemplate transaction = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));
        transaction.executeWithoutResult(status -> {
            jdbc.update("UPDATE account SET balance = balance - ? WHERE id = ?",
                    30, 1L);
            jdbc.update("UPDATE account SET balance = balance + ? WHERE id = ?",
                    30, 2L);
        });

        printBalances(jdbc, "After commit");

        // Error after first UPDATE => transaction rolls back completely.
        try {
            transaction.executeWithoutResult(status -> {
                jdbc.update("UPDATE account SET balance = balance - ? WHERE id = ?",
                        10, 1L);
                throw new IllegalStateException("Simulated error");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Failed transaction rolled back");
        }

        printBalances(jdbc, "After rollback");
    }

    private static Account find(JdbcTemplate jdbc, long id) {
        // Mapping: one ResultSet row becomes an Account record.
        return jdbc.queryForObject(
                "SELECT id, balance FROM account WHERE id = ?",
                (rs, rowNum) -> new Account(
                        rs.getLong("id"), rs.getInt("balance")),
                id);
    }

    private static void printBalances(JdbcTemplate jdbc, String prefix) {
        System.out.println(prefix + ": A=" + find(jdbc, 1L).balance()
                + ", B=" + find(jdbc, 2L).balance());
    }
}
~~~

In the `spring-data-concerns` directory, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConcernsDemo
~~~

Lines printed by the program:

~~~text
After commit: A=70, B=80
Failed transaction rolled back
After rollback: A=70, B=80
~~~

**Why can you trust this result?**

1. `JdbcTemplate` releases statements, result sets, and connections appropriately for each context (**resource management**). `DriverManagerDataSource` is only for demos; production connection pooling can be swapped in without rewriting mapping code.
2. `TransactionTemplate` invokes `DataSourceTransactionManager`. Inside the callback, `JdbcTemplate` uses the transaction-bound connection for the same `DataSource`; the first two `UPDATE`s commit together. The second run throws `IllegalStateException` (unchecked), so the transaction rolls back and A does not lose another 10 (**transaction management**).
3. `find` uses a `RowMapper` to build an `Account` from two columns; mapping works the same before and after rollback yet **does not decide** commits (**data mapping**).

This example prioritizes showing responsibility boundaries. A real money transfer system needs balance checks, updated-row verification, concurrency control, idempotency, logging, and error handling tailored to business requirements.

## 6. Confusing Scenarios and How to Diagnose Them

| Symptom | What to Check First | Why |
| --- | --- | --- |
| Pool runs out of connections; queries wait long | Unreturned connections/cursors, long-running transactions, active connection count | Primarily resource and transaction lifecycle issues |
| A was debited but B was not credited | Whether one transaction wraps both statements, matching transaction manager/DataSource, and effective rollback | Closing connections properly does not guarantee atomicity |
| Error inside `@Transactional` method yet changes still commit | Whether the method ran through a proxy, whether the exception was swallowed, or if a checked exception lacks rollback config | AOP/rollback rules determine the outcome |
| DTO has null fields or wrong mapping | Column aliases/names, SQL ↔ Java types, record/entity mapping, nullability | Transactions do not fix mapping bugs |
| `LazyInitializationException` | When lazy associations are accessed, fetch plans, persistence context lifecycle | Mapping/fetching depends on context; growing the pool won't fix the root cause |
| Unexpectedly high query count | N+1 queries, fetch strategies, projections, batch fetching | ORM behavior and query design, not necessarily a leak |
| Deadlocks/lost updates under concurrent writes | Isolation, locking, version columns, update ordering, transaction duration | Even with transactions, concurrency policies are still required |

Practical principles:

- Wrap transactions around **a business operation requiring consistency**, typically at the service layer, instead of indiscriminately opening long transactions across every layer. Avoid holding transactions during network calls or unnecessary long work.
- Use SQL parameters (`?` or named parameters) instead of concatenating user data into SQL strings; mapping does not prevent SQL injection.
- Use `JdbcTemplate` when you want explicit control over SQL and mapping; use JPA/ORM when an entity/relationship model and state tracking fit well. Both still need sound resource and transaction policies.
- Distinguish exception translation (e.g., Spring converting `SQLException` into the `DataAccessException` hierarchy) from rollback: exception translation aids consistent handling, while the transaction manager decides rollback.
- Test both the happy path and an exception between two writes; query the database state back after failure to prove atomicity, rather than only asserting an exception was thrown.

## 7. Self-Check Your Understanding

**Question 1.** Two `JdbcTemplate.update(...)` calls succeed sequentially and connections are returned. Are the two statements guaranteed to form one atomic transaction? **No.** A transaction boundary must wrap both; otherwise, each operation may auto-commit separately.

**Question 2.** Does adding `@Transactional` automatically make `RowMapper` map column names correctly? **No.** Mapping still needs accurate configuration/logic. Transactions govern consistency of changes, not how returned data is interpreted.

**Question 3.** Does calling `flush()` in JPA mean data is already committed? **No.** Flush pushes SQL to the database within the transaction; a rollback can still undo those changes.

**Question 4.** Is it right to close a connection early before a Spring transaction finishes? **No.** Use Spring's resource management so the transaction-bound connection is retained and released at the right time.

**Question 5.** If a transaction rolls back after the system already sent a notification email, is the email recalled? **No.** Database transactions do not cover external service side effects; cross-system consistency requires dedicated design.

**Key takeaway:** resource management answers *how connections are acquired and released*; transaction management answers *which changes commit or roll back together*; data mapping answers *how SQL and Java objects represent each other*. Sound data access design needs all three, with clear responsibility boundaries.
