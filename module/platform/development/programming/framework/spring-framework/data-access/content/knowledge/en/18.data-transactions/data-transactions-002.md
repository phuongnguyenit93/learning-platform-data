# `DataSourceTransactionManager` and `JdbcTransactionManager` in Spring JDBC

## 1. Purpose of the Two Transaction Managers

A business operation often runs **multiple SQL statements that must succeed or fail together**. For example, transferring 100 units from account A to account B requires debiting A and crediting B within a single transaction. If the statement crediting B fails after debiting A has already committed, the data becomes corrupted.

In Spring Framework, `PlatformTransactionManager` is the abstraction that controls the transaction lifecycle: begin, commit, rollback, and applying propagation, isolation, read-only, and timeout rules. For **synchronous JDBC** accessing a single `DataSource`, the two directly relevant implementations are:

- `org.springframework.jdbc.datasource.DataSourceTransactionManager`: manages **local JDBC transactions** on connections obtained from a single `DataSource`.
- `org.springframework.jdbc.support.JdbcTransactionManager`: **extends `DataSourceTransactionManager`**, keeping the connection/transaction management mechanism and adding **exception translation for `SQLException` thrown during commit or rollback** via the same `SQLExceptionTranslator` infrastructure used by `JdbcTemplate`.

`JdbcTransactionManager` has been available since **Spring Framework 5.3**. The word "Jdbc" in its name does not mean it uses a different transaction model or can coordinate multiple databases. Both still work with a single JDBC resource through a single `DataSource`.

### When a Transaction Is Needed

```text
BEGIN TRANSACTION
    UPDATE account SET balance = balance - 100 WHERE id = 1;
    UPDATE account SET balance = balance + 100 WHERE id = 2;
COMMIT                        -- both changes take effect

BEGIN TRANSACTION
    UPDATE account SET balance = balance - 100 WHERE id = 1;
    UPDATE account SET balance = balance + 100 WHERE id = 2;
    -- application detects an error
ROLLBACK                      -- both changes are canceled
```

This is a **conceptual diagram**, not a cross-DBMS SQL script to copy verbatim. The syntax for starting a transaction and rollback capability depend on the DBMS and SQL object types. In Java/Spring, service code should declare **transaction boundaries**; the transaction manager and driver handle the appropriate JDBC operations.

## 2. Exact Comparison of the Two Classes

| Criterion | `DataSourceTransactionManager` | `JdbcTransactionManager` |
| --- | --- | --- |
| Package | `org.springframework.jdbc.datasource` | `org.springframework.jdbc.support` |
| Inheritance | Extends `AbstractPlatformTransactionManager` | Directly extends `DataSourceTransactionManager` |
| Managed resource | A single JDBC `DataSource` | A single JDBC `DataSource` |
| Thread-bound connection | Yes, via Spring transaction synchronization | Yes, **inherited** |
| `@Transactional`, `TransactionTemplate` | Supported | Supported |
| `REQUIRED`, `REQUIRES_NEW`, `NESTED` | Supported per JDBC capabilities | Same mechanism |
| Isolation, timeout, read-only | Per JDBC/driver and configuration | Same mechanism |
| `SQLException` in **SQL statements** run via `JdbcTemplate` | `JdbcTemplate` translates to `DataAccessException` | **Identical** at the `JdbcTemplate` layer |
| `SQLException` at **commit/rollback** | Wraps as `TransactionSystemException` by default | Attempts translation into an appropriate `DataAccessException`; falls back to `TransactionSystemException` |
| When typically chosen | Need traditional manager exception behavior, compatibility with existing flows | JDBC apps wanting commit/rollback error handling more consistent with `JdbcTemplate` |

**The deciding factor is when the error occurs.** An `INSERT` failing due to a duplicate key is already translated by `JdbcTemplate` into `DuplicateKeyException` under both configurations. The extension point of `JdbcTransactionManager` applies to errors raised **late at commit or rollback**, such as certain high-isolation transaction conflicts reported by the DBMS at commit time.

Do not assume **every** commit error will become a specific subclass of `DataAccessException`: the translator depends on the `SQLException` type, SQLState, JDBC driver, and configuration. If untranslatable, the manager can still throw `TransactionSystemException`. Business code needs to understand both exception families.

## 3. Connection Management Under a Transaction

### 3.1. One Connection Used Across Statements

With `DataSourceTransactionManager` or `JdbcTransactionManager`, when an actual transaction begins, Spring obtains a connection from the `DataSource` and binds the related resource to the execution thread via `TransactionSynchronizationManager`. The manager configures the necessary JDBC state, typically setting `autoCommit = false` if needed, then commits/rolls back and cleans up after the transaction ends.

`JdbcTemplate` automatically uses `DataSourceUtils.getConnection(dataSource)`, enabling two SQL statements executed inside the same `@Transactional` to use **the same connection participating in the transaction**. When the transaction completes, Spring restores the connection state and returns the connection to the appropriate `DataSource`/pool.

```text
External call: transferService.transfer(...)
             |
             v
Spring @Transactional proxy
             |
             v
PlatformTransactionManager.getTransaction(...)
             |
             v
DataSource -> JDBC Connection X, bound to current thread
             |
             +--> JdbcTemplate.update("debit")  -- Connection X
             |
             +--> JdbcTemplate.update("credit") -- Connection X
             |
             v
 commit() or rollback() on Connection X
             |
             v
 cleanup / unbind / release Connection X
```

The example depicts an **imperative** flow running on the same thread. Do not assume the same transaction will automatically follow onto a thread created with `new Thread(...)`, an `@Async` task, or a reactive pipeline.

### 3.2. Why Both the Manager and DAO Need the Same DataSource

The core requirement is **the same connection factory/resource recognized by Spring**. If you configure the transaction manager with `dataSourceA` while `JdbcTemplate` uses `dataSourceB`, SQL statements may execute outside the transaction you think is protecting them.

```java
// Configuration fragment inside a @Configuration class.
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}

@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

Both methods use **the same `DataSource` bean** injected by Spring. You can replace the body of `transactionManager` with `new DataSourceTransactionManager(dataSource)` without modifying services or repositories that use `JdbcTemplate`.

If you invoke low-level JDBC directly, obtain the connection via `DataSourceUtils.getConnection(dataSource)` and release it via `DataSourceUtils.releaseConnection(connection, dataSource)`. Calling `dataSource.getConnection()` directly on a standard pool and closing it yourself can yield **a different connection** and bypass Spring's transaction synchronization. When integrating legacy code that must call `getConnection()` directly, Spring provides `TransactionAwareDataSourceProxy`; place the proxy properly according to the documentation.

### 3.3. Limitations of Local JDBC Transactions

Both managers are suitable when an operation uses **a single `DataSource` with independent connections**. They do not create an atomic distributed transaction across two databases, JDBC plus JMS, or JDBC plus HTTP requests. If you genuinely need XA/multi-resource coordination, use an appropriate technology such as JTA when supported by the environment; for distributed systems, you must also consider outbox, saga, idempotency, or appropriate protocols.

The mere presence of `@Transactional` does not automatically make network calls, file writes, or sending emails rollbackable.

## 4. Runnable Java 17 + Spring JDBC Example

Goal: create two accounts in **in-memory H2**; run one successful transfer transaction and one transaction that throws an error after both updates. The result proves actual rollback, and swapping the transaction manager from `JdbcTransactionManager` to `DataSourceTransactionManager` shows that **basic commit/rollback rules do not change**.

The example uses **Spring Framework 6.2.x**, Java 17+, Maven, and H2. No separate database server is required. Run in a new project directory or test environment; the classes are kept in a single Java file for readability.

### 4.1. `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jdbc-transaction-managers</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the container and annotation configuration; `spring-jdbc` provides `JdbcTemplate` and the transaction managers; H2 is the JDBC driver/DB used solely for the demo. In a Spring Boot project, let Boot's BOM manage compatible dependency versions; this code uses **plain Spring Framework**, without Boot.

### 4.2. `src/main/java/TxManagerDemo.java` File

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class TxManagerDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
            // Try the other variant by changing the line above to:
            // return new DataSourceTransactionManager(ds);
        }

        @Bean
        public TransferService transferService(JdbcTemplate jdbc) {
            return new TransferService(jdbc);
        }
    }

    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transfer(long fromId, long toId,
                             int amount, boolean failAfterUpdates) {
            if (amount <= 0 || fromId == toId) {
                throw new IllegalArgumentException("Invalid transfer");
            }

            int debited = jdbc.update(
                    "UPDATE account SET balance = balance - ? "
                    + "WHERE id = ? AND balance >= ?",
                    amount, fromId, amount);
            if (debited != 1) {
                throw new IllegalArgumentException("Cannot debit");
            }

            int credited = jdbc.update(
                    "UPDATE account SET balance = balance + ? WHERE id = ?",
                    amount, toId);
            if (credited != 1) {
                throw new IllegalArgumentException("Cannot credit");
            }

            if (failAfterUpdates) {
                throw new IllegalStateException("Simulated failure");
            }
        }
    }

    private static int balance(JdbcTemplate jdbc, long id) {
        Integer result = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?",
                Integer.class, id);
        if (result == null) {
            throw new IllegalStateException("Missing balance for " + id);
        }
        return result;
    }

    private static void printBalances(String label, JdbcTemplate jdbc) {
        System.out.printf("%s: A=%d, B=%d%n",
                label, balance(jdbc, 1L), balance(jdbc, 2L));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransferService service = context.getBean(TransferService.class);

            jdbc.execute("CREATE TABLE account ("
                    + "id BIGINT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)",
                    1L, 1000);
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)",
                    2L, 500);

            printBalances("Initial", jdbc);

            service.transfer(1L, 2L, 100, false);
            printBalances("After commit", jdbc);

            try {
                service.transfer(1L, 2L, 100, true);
                throw new AssertionError("Expected failure was not thrown");
            } catch (IllegalStateException expected) {
                if (!"Simulated failure".equals(expected.getMessage())) {
                    throw expected;
                }
            }
            printBalances("After rollback", jdbc);
        }
    }
}
```

**Explanation of potentially confusing points:**

- `Config` is a real Spring configuration; `@EnableTransactionManagement` activates the proxy mechanism for `@Transactional`. Placing the annotation on a normal method without Spring transaction infrastructure has no effect.
- `context.getBean(TransferService.class)` returns the Spring-managed bean (and proxied when configured properly). Calling `service.transfer(...)` from `main` is a call **through the proxy**.
- Both `JdbcTemplate` and `JdbcTransactionManager` receive the same `DataSource`. Inside a transaction, both `update` calls in the service participate in Spring's connection mechanism.
- `IllegalStateException` is an unchecked exception. Under `@Transactional` default rules, this exception rolls back **both UPDATE statements** executed earlier.
- Checking the updated row count and the `balance >= amount` condition are additional business checks, not specific traits of one transaction manager.
- `DriverManagerDataSource` has no connection pool; it is suitable for short demos/tests, and should not be used in production web applications under load.

### 4.3. Run Command and Output

From the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=TxManagerDemo
```

**Expected stdout** from the program (excluding Maven logs):

```text
Initial: A=1000, B=500
After commit: A=900, B=600
After rollback: A=900, B=600
```

After the successful transfer, A has 900 and B becomes 600. On the second run, even though both updates execute before `IllegalStateException` is thrown, Spring rolls back so the balances remain 900 and 600. If you change the `transactionManager` bean to `new DataSourceTransactionManager(ds)`, the three output lines remain identical: the difference between the two managers **does not appear** in this normal business rollback case.

The example verifies **the business result** rather than triggering a `SQLException` at the moment of commit/rollback; hence it does not demonstrate the translated exception type for a concurrency failure at commit. That scenario requires a dedicated test with a real driver and an appropriate DBMS.

## 5. Core Difference: Translating Commit and Rollback Errors

### 5.1. Two Points Where SQL Errors Occur

Suppose a transaction executes SQL statements and then commits:

```text
    JdbcTemplate.update(...)
          |
          +-- SQL exception as soon as the statement executes:
          |      JdbcTemplate uses SQLExceptionTranslator
          |      -> DataAccessException (with both managers)
          |
          v
    PlatformTransactionManager.commit(...)
          |
          +-- SQLException occurs inside JDBC Connection.commit():
                 DataSourceTransactionManager
                    -> usually TransactionSystemException

                 JdbcTransactionManager
                    -> tries SQLExceptionTranslator:
                       corresponding DataAccessException
                       or fallback TransactionSystemException
```

Notable example: PostgreSQL under `SERIALIZABLE` isolation may detect certain transaction conflicts late at commit time. When the `SQLException` matches translator rules, `JdbcTransactionManager` can return `ConcurrencyFailureException` or a specific subclass instead of only a generic `TransactionSystemException`. **Do not hardcode exact error codes, subclasses, or error timing across all drivers.**

### 5.2. Common Exceptions

| Timing | Source | Notable Behavior |
| --- | --- | --- |
| Executing `JdbcTemplate.update/query` | `SQLException` from JDBC statement | `JdbcTemplate` normally translates to `DataAccessException` for both managers |
| At `Connection.commit()` | `SQLException` during commit | `JdbcTransactionManager` tries translation; `DataSourceTransactionManager` uses `TransactionSystemException` by default |
| At `Connection.rollback()` | `SQLException` during rollback | `JdbcTransactionManager` also tries translation; falls back when unrecognized |
| Business exception from service | `IllegalStateException`, etc. | Follows `@Transactional` rollback rules; identical mechanism |

**Avoid this misconception:** switching the manager to `JdbcTransactionManager` **is not** how you "enable JDBC error translation" for `JdbcTemplate`: `JdbcTemplate` already has its own exception translation. The change matters primarily at **commit/rollback**.

### 5.3. Configuring a Translator When Truly Needed

`JdbcTransactionManager` can accept a custom `SQLExceptionTranslator`. The example below is a configuration fragment, not a standalone runnable class:

```java
// Fragment inside a @Bean method, with related classes imported.
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
    manager.setExceptionTranslator(
            new org.springframework.jdbc.support.SQLExceptionSubclassTranslator());
    return manager;
}
```

Spring Framework 6.x already provides a suitable default translator for many cases via SQL exception subclasses and SQLState; override it only when there is a clear requirement (such as a specialized driver or custom SQLState/vendor code mapping). When a custom translator does not recognize an error, your code must still handle the general exception or let it propagate to an appropriate boundary. Do not rely on the exception class name alone to conclude a transaction rolled back cleanly in every commit failure: evaluate transaction status, safe retries, and idempotency.

## 6. How Are `@Transactional` and `TransactionTemplate` Related?

The **transaction manager** is the component executing the transaction mechanism. `@Transactional` is metadata for **declarative** transaction management; `TransactionTemplate` is the API for **programmatic** transaction management. Both use the configured `PlatformTransactionManager`.

### 6.1. Declarative: `@Transactional`

```java
// Fragment in a Spring-managed service, called via a Spring proxy.
@Transactional
public void placeOrder(long orderId) {
    jdbc.update("UPDATE orders SET state = 'CONFIRMED' WHERE id = ?",
            orderId);
    jdbc.update("INSERT INTO order_audit(order_id, action) VALUES (?, ?)",
            orderId, "CONFIRM");
}
```

If an error in one update throws an unchecked exception and it is not swallowed inside the method, the manager marks rollback according to default rules.

Crucial condition: the method must be called **through a Spring proxy**, for example from another bean. A method calling another method **on the same object** (self-invocation) bypasses the proxy in default proxy mode, so the annotation on the inner method may have no effect. Starting transactions from a public service method called externally is a clear choice.

### 6.2. Programmatic: `TransactionTemplate`

You can run an explicit transaction with the same manager using a template; the fragment below assumes `PlatformTransactionManager txManager` and `JdbcTemplate jdbc` are already injected:

```java
TransactionTemplate template = new TransactionTemplate(txManager);

template.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET balance = balance - ? WHERE id = ?",
            100, 1L);
    jdbc.update("UPDATE account SET balance = balance + ? WHERE id = ?",
            100, 2L);

    boolean validationFailed = true; // Assume business validation fails.
    if (validationFailed) {
        status.setRollbackOnly();
    }
});
```

`status.setRollbackOnly()` requests a rollback when the callback finishes; it does not necessarily throw an exception. This fragment only illustrates the API; it does not replace the full example in section 4. If the callback throws an unchecked exception, `TransactionTemplate` also rolls back according to Spring's mechanism and rethrows the error. There is no need to layer `@Transactional` and `TransactionTemplate` over the same boundary without an explicit propagation intent.

## 7. Propagation, Savepoints, Isolation, Timeout, and Read-Only

Because `JdbcTransactionManager` **extends** `DataSourceTransactionManager`, these transaction management features are fundamentally identical.

### Propagation

| Setting | Meaning in a Spring Call |
| --- | --- |
| `REQUIRED` (default) | Join an existing transaction; if none exists, create a new transaction |
| `REQUIRES_NEW` | Suspend the outer transaction and create a new physical transaction |
| `NESTED` | When a transaction exists, create a nested scope using a JDBC savepoint if supported by the driver; if no outer transaction exists, start a new transaction |
| `SUPPORTS` | Join if a transaction exists; execute without a real transaction otherwise |
| `MANDATORY` | Require an existing transaction; throw an error otherwise |
| `NOT_SUPPORTED` | Execute without a real transaction, suspending any existing transaction |
| `NEVER` | Throw an error if called while a transaction exists |

**`NESTED` vs `REQUIRES_NEW`:** a nested scope can roll back to a **savepoint within the same physical transaction**, whereas `REQUIRES_NEW` uses a different physical transaction with its own connection when needed. Savepoints must be supported by the JDBC driver and DBMS; `DataSourceTransactionManager`'s `nestedTransactionAllowed` flag defaults to `true`, though that does not force every driver to support savepoints.

`REQUIRES_NEW` may need to borrow an additional connection from the pool while the outer transaction still holds the old connection. If the pool is too small, concurrent tasks can wait for connections and cause resource starvation. Use `REQUIRES_NEW` only when genuinely independent commit/rollback is needed.

### Isolation

`@Transactional(isolation = Isolation.READ_COMMITTED)` requests the corresponding isolation on a new transaction, depending on the driver/DBMS. The default `Isolation.DEFAULT` defers to the database. Isolation is not "higher is always better": stronger levels can increase conflicts, locking, and retries; choose based on business consistency needs and measure on a real database.

### Timeout

`@Transactional(timeout = 5)` requests a 5-second transaction timeout, though actual enforcement depends on the manager, driver, and JDBC statements. `JdbcTemplate` and `DataSourceUtils.applyTransactionTimeout(...)` have mechanisms to apply the timeout to statements. If you create raw `Statement` objects bypassing Spring helpers, do not assume every query will obey the declared timeout.

### Read-Only

`@Transactional(readOnly = true)` is a signal to the transaction infrastructure/driver; by default many environments treat it only as a **hint**. `DataSourceTransactionManager.setEnforceReadOnly(true)` enables attempting to issue a real read-only transaction command on supported DBMSs, for example via `SET TRANSACTION READ ONLY`. Both managers have this setting through inheritance; test on the real DBMS before treating it as a hard barrier against writes.

### Annotation Example with Attributes

```java
// Fragment on a method in a Spring-managed service.
@Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 5,
        rollbackFor = java.io.IOException.class
)
public void updateAndAudit() throws java.io.IOException {
    // SQL statements using the same DataSource/JdbcTemplate.
}
```

This fragment requires importing `org.springframework.transaction.annotation.Propagation` and `org.springframework.transaction.annotation.Isolation`. The rollback condition for `IOException` is **explicitly specified**. By default `@Transactional` rolls back on `RuntimeException` or `Error`; ordinary checked exceptions do not trigger rollback without a matching rule. If you catch an exception inside the method without rethrowing or marking rollback-only, the transaction may proceed to commit.

## 8. When to Choose Which Manager?

### Choose `JdbcTransactionManager` When

- The application uses Spring JDBC (especially `JdbcTemplate`/`NamedParameterJdbcTemplate`) against **a single `DataSource`**.
- You want `SQLException` errors during commit/rollback categorized using the same `DataAccessException` hierarchy already used for SQL operations.
- You handle concurrency errors that occasionally surface at **commit** (especially under high-isolation transactions) and want to leverage the translator when the driver supplies sufficient info.
- You have verified that upstream callers tolerate `commit()/rollback()` throwing `DataAccessException` alongside `TransactionException`.

### Keep `DataSourceTransactionManager` When

- Legacy applications already have handlers/monitoring expecting `TransactionSystemException` specifically on commit/rollback.
- You need to preserve historical exception behavior during an upgrade or already have custom transaction-level error reporting.
- There is no practical benefit from translating commit/rollback errors further, and changing it would introduce compatibility adjustments.

Do not choose based on false criteria such as "`JdbcTransactionManager` has real transactions while `DataSourceTransactionManager` does not," "the old manager does not support `@Transactional`," or "the new manager fixes self-invocation." All of those claims are false.

### When **Not** to Use Either

- Using JPA with `EntityManager` as the primary resource: typically use `JpaTransactionManager` per JPA architecture to manage persistence context lifecycle and flushing.
- Needing multiple homogeneous XA resources: consider an appropriate JTA solution (only when genuinely supported by the environment).
- Using Spring R2DBC/reactive: use `R2dbcTransactionManager` and the reactive transaction context, not a thread-bound JDBC manager.

Multi-technology systems may require multiple distinct transaction managers; in that case, explicitly specify the target manager via the `@Transactional(transactionManager = "...")` qualifier to avoid selecting the wrong one.

## 9. Real-World Pitfalls and Diagnostics

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| First statement commits even though later statement throws | Method does not run via proxy, manager/DAO use different DataSources, exception swallowed | Check bean proxy, Spring config, and shared DataSource; test rollback with real data |
| Error occurs at commit without specific `DataAccessException` | Using `DataSourceTransactionManager` or translator does not recognize `SQLException` | Inspect exception chain, manager type, and SQLState; do not force every error into one subclass |
| `@Transactional` present yet checked exception does not roll back | Default rollback rules | Add `rollbackFor` or configure an appropriate policy |
| `NESTED` does not work | Driver/DBMS does not support savepoints or no real transaction exists as expected | Check savepoint support and actual propagation |
| `REQUIRES_NEW` blocks waiting for a connection | Outer transaction holds a connection, pool lacks capacity | Size pool with evidence, reduce nesting, or redesign flow |
| Query ignores timeout | Raw JDBC Statement bypasses Spring timeout helper | Use `JdbcTemplate` or `DataSourceUtils.applyTransactionTimeout` |
| `readOnly = true` still allows writes | Read-only is usually a hint, DBMS does not enforce it | Choose DBMS-supported enforcement and test |
| Results lost across threads | Transaction context in imperative flow is thread-bound | Design transaction boundaries per thread; avoid assuming automatic propagation to `@Async` |
| JDBC block rolls back yet email is still sent | Sending email is outside the JDBC resource | Use an outbox or proper orchestration |

### Pre-Production Testing Checklist

1. Verify which `PlatformTransactionManager` is actually injected; verify the manager's `DataSource` bean and all `JdbcTemplate` beans share the same connection source.
2. Test **successful commit** and **rollback on unchecked exception**; inspect database state after the transaction, not just logs.
3. Test checked exceptions with and without `rollbackFor` if business logic can throw them.
4. If needed, test `NESTED`/savepoints and `REQUIRES_NEW` with a real pool; pay attention to connection counts and transaction isolation.
5. Enable Spring transaction diagnostic logging when investigating (e.g., `org.springframework.transaction` and `org.springframework.jdbc.datasource` at DEBUG in an appropriate environment), while avoiding leaking sensitive info and not leaving verbose logging on for long in production.
6. Test SQL errors at **statement** execution separately from errors at **commit/rollback**. Commit errors can be hard to reproduce; they require a real DBMS/driver and controlled concurrency scenarios. Do not infer exception types from the H2 business demo in section 4.
7. For applications with retries, ensure retries happen at **a new transaction boundary**, include idempotency, and only retry genuinely recoverable errors; do not unconditionally retry every `DataAccessException`.
8. Upgrading Spring or JDBC drivers requires retesting `SQLExceptionTranslator` mappings and exception-catching logic; this is where the two managers can produce observable differences.

## 10. Knowledge Summary

- `DataSourceTransactionManager` manages connections and local JDBC transactions for **a single `DataSource`**, working with `JdbcTemplate`, `@Transactional`, and `TransactionTemplate`.
- `JdbcTransactionManager` is a **subclass** with the same transaction mechanism, adding `SQLExceptionTranslator` at **commit/rollback** to report errors more consistently with Spring JDBC's `DataAccessException` hierarchy.
- Both share the same connection sharing, propagation, isolation, savepoints, and basic rollback mechanics; switching managers **does not automatically fix** proxy misconfigurations, mismatched DataSources, missing pools, or faulty transaction scopes.
- Choose the manager based on resource type, desired exception behavior, and how the application handles commit/rollback failures. Always verify with business tests and a real DBMS when evaluating concurrency errors.

### Official Documentation

1. [Spring Framework – Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, `DataSourceTransactionManager`, and `JdbcTransactionManager` mechanics, connection sharing, and lazy connection optimization.
2. [DataSourceTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): local JDBC, savepoints, timeout, read-only, lifecycle.
3. [JdbcTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): subclass since 5.3, `SQLException` translation at commit/rollback, translator fallback.
4. [Spring Framework – Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy, propagation, and rollback rules.
5. [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): differences between `REQUIRED`, `REQUIRES_NEW`, and `NESTED`.
6. [Spring Framework – Using `SQLExceptionTranslator`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): standardizing JDBC exceptions into `DataAccessException`.
