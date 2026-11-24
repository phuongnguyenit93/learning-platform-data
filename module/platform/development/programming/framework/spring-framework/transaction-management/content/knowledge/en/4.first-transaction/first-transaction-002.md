# Declaring DataSource with JdbcTransactionManager

> **Scope:** Spring Framework — Transaction Management, **First Transaction** section. This lesson guides you through connecting a relational database using `DataSource`, declaring `JdbcTransactionManager`, and using `JdbcTemplate` in **a local JDBC transaction**. The complete example uses Java 17, Spring Boot 3.5.7 (Spring Framework 6.2), Maven, and H2 so it can run immediately without installing a separate database.

## 1. Objectives and Big Picture

After this lesson, you should understand and be able to:

1. Explain the distinct roles of `DataSource`, `JdbcTransactionManager`, `JdbcTemplate`, and `@Transactional`.
2. Declare Spring beans that use **the same `DataSource`**, ensuring SQL statements in the same transaction use the Spring-managed connection.
3. Observe **commit** when a method finishes normally and **rollback** when an unchecked error (`RuntimeException`) escapes the method.
4. Run a money transfer example between two accounts on H2; verify that an error in a later step rolls back both updates.
5. Distinguish manual Spring configuration from Spring Boot auto-configuration and avoid common pitfalls involving proxies, multiple `DataSource`s, and direct JDBC operations.

Execution flow diagram:

```text
Caller
    |
    v
Spring AOP proxy (@Transactional)
    |
    v
JdbcTransactionManager --------> DataSource --------> JDBC Connection
    |                                                  ^
    | open / commit / rollback                         |
    v                                                  |
BankService ------> JdbcTemplate ------> DataSourceUtils
    |
    +-- UPDATE accounts ...
    +-- UPDATE accounts ...
```

**Key point:** `DataSource` provides connections; `JdbcTransactionManager` determines the transaction boundary and binds the connection to the currently executing thread; `JdbcTemplate` obtains the connection associated with that transaction via Spring's mechanism. Two `UPDATE` statements in a service method can succeed together or be rolled back together.

## 2. Components and Responsibilities

| Component | API / package | Responsibility |
| --- | --- | --- |
| `DataSource` | `javax.sql.DataSource` (Java/JDBC) | Where the application requests a `Connection` to the database; can be a pool, JNDI, or a simple connection source. |
| `DriverManagerDataSource` | `org.springframework.jdbc.datasource` | Simple `DataSource` implementation that creates a new connection on every request; suitable for demos/tests, **does not provide pooling**. |
| `JdbcTransactionManager` | `org.springframework.jdbc.support` | `PlatformTransactionManager` implementation for **one** JDBC `DataSource`, managing begin/commit/rollback and translating SQL errors during commit/rollback when possible. |
| `JdbcTemplate` | `org.springframework.jdbc.core` | Executes SQL, manages statements/result sets, handles connections properly, and translates many `SQLException`s into `DataAccessException`. |
| `@Transactional` | `org.springframework.transaction.annotation` | Declares a transaction boundary around a method call when applied by Spring's AOP transaction mechanism. |
| `@EnableTransactionManagement` | `org.springframework.transaction.annotation` | Enables `@Transactional` processing in plain Spring configuration; in many Boot applications, this infrastructure is auto-configured. |
| `TransactionTemplate` | `org.springframework.transaction.support` | An option for managing transactions via callbacks instead of annotations. |

### How Do `JdbcTransactionManager` and `DataSourceTransactionManager` Differ?

`JdbcTransactionManager` extends `DataSourceTransactionManager`. Both manage JDBC transactions on a single `DataSource`; the notable feature of `JdbcTransactionManager` (since Spring Framework 5.3) is **translating `SQLException` during the commit/rollback phase** using `SQLExceptionTranslator`, in the same spirit as `JdbcTemplate`. For example, a data contention error detected late at commit time can be represented by a class in the `DataAccessException` hierarchy rather than solely as a `TransactionSystemException`.

Therefore, calling code should be prepared to handle both transaction errors and data access errors; never assume every commit error always belongs to a single exception class. This lesson chooses `JdbcTransactionManager` to clearly illustrate how it pairs with `JdbcTemplate`.

### Scope of Guarantees

A standard `JdbcTransactionManager` controls **one JDBC `DataSource`**; by default, it does not control other databases, HTTP requests, message brokers, or external service transactions. Nor does it mean Spring automatically creates a distributed/XA transaction. If the application uses JPA, the appropriate transaction manager may be `JpaTransactionManager`; do not arbitrarily attach a JDBC manager to a JPA business flow without a clear design.

## 3. Preparing the Complete Project

The example uses a Spring Boot application with two accounts. Initially, their balances are **1,000** and **500** units respectively. The first transfer moves 200 and commits, yielding **800 / 700**. The second transfer attempts to move 100 but intentionally throws `IllegalStateException` after both `UPDATE` statements, so the entire second transfer must roll back, leaving balances at **800 / 700**.

Directory structure:

```text
jdbc-transaction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── vn/
                └── example/
                    ├── JdbcTxApplication.java
                    └── BankService.java
```

### 3.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>jdbc-transaction-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-jdbc` provides Spring JDBC and the required components for transaction management. `h2` is the JDBC driver and in-memory database used to run the demo. Maven requires Java 17 or newer; H2 lives only within the example's JVM process.

### 3.2. `src/main/java/vn/example/JdbcTxApplication.java`

```java
package vn.example;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class JdbcTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcTxApplication.class, args);
    }

    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    public JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public CommandLineRunner demo(JdbcTemplate jdbc, BankService service) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE accounts (" +
                "id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO accounts(id, balance) VALUES (1, 1000), (2, 500)"
            );

            service.transfer(1, 2, 200, false);
            System.out.printf("after commit: %d, %d%n",
                balance(jdbc, 1), balance(jdbc, 2));

            try {
                service.transfer(1, 2, 100, true);
            } catch (IllegalStateException expected) {
                // The second transfer was rolled back.
            }
            System.out.printf("after rollback: %d, %d%n",
                balance(jdbc, 1), balance(jdbc, 2));
        };
    }

    private static int balance(JdbcTemplate jdbc, int accountId) {
        return jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?",
            Integer.class,
            accountId
        );
    }
}
```

Meaning of the beans:

- `dataSource()` declares **one** H2 connection source. `jdbc:h2:mem:txdemo` is an in-memory database; `DB_CLOSE_DELAY=-1` keeps the database alive across connection closes within the same JVM to allow multiple demo queries.
- `transactionManager(DataSource dataSource)` receives **that exact `DataSource` bean** injected by Spring and instantiates `JdbcTransactionManager`. Spring uses it to coordinate connections from that data source.
- `jdbcTemplate(DataSource dataSource)` also uses **the same `DataSource` bean**. This is an essential requirement for `JdbcTemplate`'s SQL to participate in transactions controlled by the corresponding manager.
- `@EnableTransactionManagement` enables `@Transactional` processing; in Spring Boot, transaction configuration typically already has auto-configuration infrastructure, but declaring it explicitly in the example helps learners recognize its role.
- `CommandLineRunner` creates the table and sample data **outside the transactional transfer method**, then calls a separate service bean to ensure the call goes through the Spring proxy.

`DriverManagerDataSource` is used **for learning only**. Each connection acquisition may open a new physical connection. For real services, use a pooling `DataSource` such as HikariCP and externalize connection configuration/secrets from source code.

### 3.3. `src/main/java/vn/example/BankService.java`

```java
package vn.example;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BankService {
    private final JdbcTemplate jdbc;

    public BankService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int fromId, int toId, int amount,
                         boolean failAfterUpdates) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts " +
            "SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalArgumentException("Insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Receiver not found");
        }

        if (failAfterUpdates) {
            throw new IllegalStateException("Simulated failure");
        }
    }
}
```

The `transfer` method is declared `public` on a `@Service` Spring bean and called from another bean (the runner). This is important because standard `@Transactional` handling uses a **proxy**. Both update statements go through the same `JdbcTemplate` and thus use the connection currently bound to the transaction.

The `balance >= ?` check in the `UPDATE` statement prevents overdrawing for an individual operation and protects concurrent operations at the row locked/updated by the DB. In real financial applications, you still need detailed design for currency units, rounding, concurrency control, idempotency, and auditing; this example is solely meant to demonstrate JDBC commit/rollback.

### 3.4. Running and Viewing the Results

From the `jdbc-transaction-demo` directory:

```bash
java -version
mvn -version
mvn -q spring-boot:run
```

The two lines intentionally printed by the demo program are:

```text
after commit: 800, 700
after rollback: 800, 700
```

Maven/Spring Boot may print additional startup logs depending on configuration; the two lines above are **deterministic business results**. After the successful transfer: 1,000 − 200 = 800; 500 + 200 = 700. After the failed transfer: both `UPDATE` statements from transferring 100 roll back, so balances remain unchanged.

If you remove `@Transactional` from `BankService.transfer`, the two `UPDATE` statements in the example may run and commit independently under the auto-commit behavior of the acquired connections. When the exception is thrown at the end of the method, **there is no surrounding transaction to roll back both operations**; therefore, you must not assume the result will always be 800/700. Use tests to verify actual configuration instead of relying on whether the program throws an exception.

## 4. Why Do the SQL Statements Share the Same Transaction?

With `@Transactional` active on `BankService.transfer`, the sequence of events is:

1. The caller invokes the **proxy** of `BankService`.
2. `TransactionInterceptor` finds the appropriate transaction manager—here, the `transactionManager` bean of type `JdbcTransactionManager`.
3. The manager obtains a `Connection` from the declared `DataSource`, prepares transaction state (for example, turning off auto-commit as needed), and binds the connection to the current thread's transaction context.
4. `JdbcTemplate` calls the transaction-aware connection access mechanism (`DataSourceUtils`). It receives the connection Spring bound to the transaction for **the same `DataSource`**.
5. Both `UPDATE` statements run on the JDBC resource belonging to the same transaction.
6. If the method completes normally and is not marked rollback-only, the manager **commits**. If an error matching rollback rules escapes, the manager **rolls back**.
7. Spring cleans up the transaction state and releases/closes the connection in the manner appropriate for the `DataSource`.

Never assume that merely declaring a bean named `transactionManager` makes all JDBC code in the application share one transaction. **The connection acquisition mechanism and the `DataSource` instance must be compatible**. `JdbcTemplate` and `DataSourceUtils` handle that; calling `dataSource.getConnection()` directly elsewhere may create a separate connection that does not participate in the active transaction.

### Avoid Acquiring Connections in a Non-Transaction-Aware Way

The following snippet is an **error illustration**, not a standalone program:

```java
try (var connection = dataSource.getConnection()) {
    // This connection may be independent from the connection
    // bound by JdbcTransactionManager to the current transaction.
}
```

Prefer using `JdbcTemplate`. When you truly must perform low-level JDBC operations inside a method with an active Spring transaction, use:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    // Create a PreparedStatement and perform JDBC operations with this connection.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

The snippet above is an **integration pattern**, requiring imports of `java.sql.Connection` and `org.springframework.jdbc.datasource.DataSourceUtils`. `releaseConnection` knows the connection is held by the transaction and will not arbitrarily close it before Spring ends the transaction. Do not manually call `commit()`, `rollback()`, or alter `autoCommit` on a Spring-managed connection unless intentional and you understand the consequences.

## 5. How Does Spring Boot Auto-Configuration Differ from Manual Declaration?

### Plain Spring Framework

In a Spring application without Boot, you typically need to declare:

- `@Bean DataSource`.
- `@Bean JdbcTransactionManager` receiving that exact `DataSource`.
- `@Bean JdbcTemplate` receiving the same `DataSource`.
- `@EnableTransactionManagement` to activate `@Transactional` processing.

The bean method can declare the return type `PlatformTransactionManager` instead of `JdbcTransactionManager` if code only needs the interface:

```java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

In that case, import `org.springframework.transaction.PlatformTransactionManager`; JDBC functionality remains unchanged.

### Spring Boot

With `spring-boot-starter-jdbc` and a valid datasource configuration, Spring Boot normally **auto-configures** `DataSource`, `JdbcTemplate`, and a JDBC transaction manager if no replacement beans exist and the relevant conditions are met. For an external database, familiar properties are `spring.datasource.url`, `spring.datasource.username`, `spring.datasource.password`, and depending on the case, `spring.datasource.driver-class-name`.

The H2 build in section 3 intentionally declares beans manually to clearly learn the wiring flow. **Do not both define a `DataSource` bean manually and expect `spring.datasource.*` properties to always modify that bean**: a custom bean typically causes the corresponding `DataSource` auto-configuration to back off. When choosing Boot auto-configuration, remove your manual `dataSource()` bean and provide standard properties. Do not mix both approaches without understanding auto-configuration conditions.

An **alternative** example, for a Boot project using only H2 and letting Boot create the `DataSource`:

```properties
spring.datasource.url=jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver
```

These lines are the contents of `src/main/resources/application.properties` **in the auto-configuration approach**, and do not need to be added to the project in section 3. When auto-configuring, Boot typically uses HikariCP if the starter brings HikariCP onto the classpath. The actual choice of transaction manager also depends on which beans and persistence stacks are present, so for the first lesson keep things clear with just one JDBC data source and one manager.

In production, put passwords in a secret manager or environment variables, restrict database privileges, configure pool/timeouts, and monitor connections. Do not use `DriverManagerDataSource` as a pool for high load.

## 6. Transaction Boundaries with `@Transactional`

The example uses **declarative transaction management**. Common default attributes of `@Transactional` in Spring include:

| Attribute | Default | Meaning |
| --- | --- | --- |
| `propagation` | `REQUIRED` | Create a new transaction if no suitable one exists; join if one already exists. |
| `isolation` | `DEFAULT` | Let the database decide the default isolation level. |
| `readOnly` | `false` | Transaction allows both reads and writes; `readOnly=true` is usually an optimization hint, not an absolute write block. |
| `timeout` | Per the transaction system, or unlimited if unsupported | Sets a limit via the transaction mechanism; timeout is not a guaranteed cancellation mechanism for all external tasks. |
| Rollback | `RuntimeException` or `Error` | Checked exceptions **do not automatically** trigger rollback under default rules, unless configured otherwise. |

Example making intent explicit:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10
)
public void updateTwoRows() {
    // Perform JdbcTemplate operations using the same DataSource.
}
```

This is an **illustrative snippet**, with `Propagation` and `Isolation` from `org.springframework.transaction.annotation`. Support for isolation levels, timeouts, and lock handling depends on the database/driver; never assume every database behaves identically.

If rollback is also needed for a checked exception:

```java
@Transactional(rollbackFor = IOException.class)
public void processFileAndUpdate() throws IOException {
    // DB part uses JdbcTemplate; IOException must be thrown outward.
}
```

Requires importing `java.io.IOException`. This is also a **snippet**, not a standalone program. Conversely, if you catch an exception inside the method and do not rethrow it or mark rollback-only, Spring may treat the method as having completed normally and commit. Deliberately decide your policy when handling errors.

### When to Use `TransactionTemplate`?

If you need to control transactions around a block of code instead of via annotations, you can create a `TransactionTemplate` from the same manager:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

template.executeWithoutResult(status -> {
    jdbc.update("UPDATE accounts SET balance = balance - 1 WHERE id = 1");
    jdbc.update("UPDATE accounts SET balance = balance + 1 WHERE id = 2");
});
```

This is an **illustrative snippet** assuming `transactionManager` and `jdbc` are already provided in the enclosing method, and requires importing `org.springframework.transaction.support.TransactionTemplate`. If the callback throws a matching exception, Spring rolls back; you can call `status.setRollbackOnly()` to request rollback programmatically. `TransactionTemplate` is useful when explicit transaction boundaries in code are needed, but do not nest it indiscriminately with `@Transactional` without understanding propagation.

## 7. Common Configuration Mistakes

### 7.1. `JdbcTemplate` and the Manager Use Different Data Sources

If the manager is created with `dataSourceA` while the template runs on `dataSourceB`, SQL from B does not automatically participate in A's JDBC transaction. Sometimes two datasources share the same JDBC URL yet are **two distinct beans/connection providers**, leading to subtle bugs. Always verify injection, qualifiers, and connection management.

### 7.2. Using `@Transactional` on an Object Created Manually with `new`

For instance, `new BankService(jdbcTemplate)` bypasses Spring's container/proxy. Annotated methods on this object are not automatically wrapped by Spring's transaction interceptor. Use a Spring-created bean, inject it via constructor, and call through that bean reference.

### 7.3. Calling a Method Within the Same Bean (Self-Invocation)

`this.transfer(...)` from another method of `BankService` normally **does not pass through the proxy** when using Spring AOP proxy mode, so `@Transactional` on `transfer` may have no effect. Place the boundary on a public method called by another bean, or refactor the service. Never treat the presence of the annotation in source code as proof that a transaction is actually running.

### 7.4. Swallowed Exceptions

`JdbcTemplate` can throw `DataAccessException` (unchecked). If a method catches and ignores the error, the manager does not know to roll back, unless the transaction was already marked rollback-only by another mechanism. Avoid logging and returning a fake success; usually you should rethrow the exception or explicitly control rollback per business logic.

### 7.5. Confusing `readOnly` with Database Permissions

`@Transactional(readOnly = true)` is a transaction configuration/hint and may be applied to varying degrees by the driver/database. It **does not replace** a read-only database account, SQL authorization policies, or DB-side enforcement. Do not use it as a security boundary.

### 7.6. Missing Driver, Wrong JDBC URL, or Wrong Secret

Errors such as `Cannot load driver class`, `Failed to obtain JDBC Connection`, or authentication failure are usually caused by a missing driver, wrong URL, database not running, access permissions, or wrong secret. Check dependencies, JDBC driver version, URL, host/port, pool, and network before blaming `@Transactional`.

### 7.7. Holding Transactions Too Long or Switching Threads

Do not place slow queries, long HTTP waits, or large file processing inside a transaction, which holds connections and locks for too long. Imperative JDBC transactions are normally bound to the current thread; running subtasks via `new Thread(...)` or `@Async` **does not automatically inherit the transaction**. If background processing is needed, design a separate transaction where it executes.

### 7.8. Believing Multiple Local Transactions Form One Shared Transaction

`JdbcTransactionManager` does not make updates across two independent databases atomic, and it cannot roll back HTTP/email/broker side effects. If coordination across multiple systems is required, study appropriate patterns such as outbox, idempotency, saga, or distributed transactions when participants genuinely support them. For this introductory lesson, limit yourself to **one JDBC `DataSource`**.

## 8. When an Application Has Multiple `DataSource`s

When there are multiple databases, each `JdbcTransactionManager` must be bound to the right `DataSource`. You can give beans distinct names and specify the manager in `@Transactional`:

```java
@Bean("ordersTransactionManager")
public JdbcTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void updateOrder() {
    // The orders JdbcTemplate must use ordersDataSource.
}
```

These are **extended configuration snippets**, assuming the application already has the `ordersDataSource` bean and corresponding `JdbcTemplate`; they are not standalone code. Import `org.springframework.beans.factory.annotation.Qualifier`. With multiple managers, you must resolve default bean selection/`@Primary` or qualifiers, and do not assume one annotation will manage all datasources. **Two independent `JdbcTransactionManager`s do not turn into XA/2PC.**

If an application uses Spring Data JPA alongside JDBC, you must decide which transaction manager is primary; using `JpaTransactionManager` with the same datasource can coordinate properly managed JDBC operations, but you should not create overlapping configurations or pick managers arbitrarily based only on bean names.

## 9. Verifying Transactions Yourself Instead of Just Looking at Annotations

In the demo, the most important test is:

- Initial state: account 1 has **1000**, account 2 has **500**.
- Call 1: `transfer(1, 2, 200, false)`; no exception; observe **800**, **700**.
- Call 2: `transfer(1, 2, 100, true)`; exception after both `UPDATE`s; observe **still 800**, **700**.
- Verify that the call to `transfer` goes through a **Spring bean** and that `JdbcTemplate` uses the same `DataSource` as the manager.

You can check whether a transaction is active inside a Spring-managed method using this **diagnostic snippet**:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("transaction active = " + active);
```

Requires importing `org.springframework.transaction.support.TransactionSynchronizationManager`. When `transfer` is called through the proxy and a transaction has started, this typically returns `true`. However, this check **does not replace** rollback testing and verifying the actual datasource/connection.

In integration tests, use the target database or one with matching behavior when testing locking/isolation; differences in DDL, autocommit, and isolation between H2 and PostgreSQL/MySQL can cause simple tests not to reflect production. If a test method itself has `@Transactional`, Spring Test may roll back the test at the end; distinguish test rollback from the commit/rollback behavior of the service under test.

### Mini Exercises

1. Change `failAfterUpdates` to `false` on the second call; predict and run to confirm balances become **700 / 800**.
2. Keep `failAfterUpdates=true`, add a `SELECT` inside `transfer` before throwing the error and observe the data **inside the transaction**. After rollback, observe that data **outside the transaction** is unchanged.
3. Change the exception at the end of the method to a custom checked exception and declare `throws`; compare behavior **with** and **without** `rollbackFor`. Be careful because this edit changes source code and requires recompiling.
4. Temporarily point `JdbcTemplate` to a different `DataSource` in a test environment to see why **same DataSource** is an important wiring condition; do not run this experiment on a production database.

## 10. Implementation Checklist for `DataSource` + `JdbcTransactionManager`

- [ ] Spring JDBC, transaction support, and the right JDBC driver dependencies are present.
- [ ] `DataSource` has valid URL/driver/credentials; production uses a pool and externalized secrets outside source code.
- [ ] Only one `DataSource` exists for the transaction demo, or other `DataSource`s are clearly qualified.
- [ ] `JdbcTransactionManager` receives the exact `DataSource` used by `JdbcTemplate`.
- [ ] `@Transactional` infrastructure is enabled, the service is Spring-managed, and callers go through the proxy.
- [ ] Transaction boundaries are placed on service methods encompassing **all** SQL statements that must be atomic.
- [ ] Rollback rules are clear, including checked exceptions when needed.
- [ ] `DataSource.getConnection()` is not used directly in a way that bypasses transaction-aware mechanisms.
- [ ] Both commit and rollback are tested against real data, not just verifying that an exception was thrown.
- [ ] Timeouts, pool limits, logging/metrics, and long-transaction controls fit the operating environment.

**Key takeaway:** `DataSource` is the source of connections; `JdbcTransactionManager` manages transactions on connections from that source; `JdbcTemplate` uses the connection in the right context. Wiring these **three components** properly and calling the service through the Spring proxy is the foundation for getting your first JDBC transaction working as expected.

## References

- Spring Framework — [Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, `DataSourceTransactionManager`, and `JdbcTransactionManager`.
- Spring Framework — [JdbcTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): constructors, commit/rollback error translation capabilities.
- Spring Framework — [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): declarative transaction configuration.
- Spring Framework — [Understanding Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): proxies and interceptors.
- Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`.
- Spring Boot — [SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): datasource properties, pooling, and `JdbcTemplate`.
