# TransactionAwareDataSourceProxy for JDBC Code That Needs Adaptation

## 1. Real-World Problem and Goal

When bringing a legacy JDBC library or a pure-Java DAO into a Spring Framework application, you may encounter code that knows nothing about Spring:

```java
// Example inside a legacy DAO method; dataSource was passed in.
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
    statement.setInt(1, delta);
    statement.setLong(2, accountId);
    statement.executeUpdate();
}
```

This DAO calls `DataSource.getConnection()` and `Connection.close()` using standard JDBC. Meanwhile, a Spring service wants to group multiple DAO calls into **a single transaction**. If a standard `DataSource` is passed directly into the DAO, `getConnection()` may return a fresh connection, independent of the connection Spring bound to the current transaction. The operation inside the DAO can auto-commit and fail to roll back with the service. The problem does not lie in the `UPDATE` syntax, but in **how the connection is acquired and released**.

`TransactionAwareDataSourceProxy`, in package `org.springframework.jdbc.datasource`, is an adapter class for this situation: it implements the standard JDBC `javax.sql.DataSource` interface, yet causes direct JDBC calls through the proxy to **participate in a Spring-managed transaction** when an appropriate transaction is active.

After this article, you should be able to:

1. Explain when `TransactionAwareDataSourceProxy` is needed and when it is not.
2. Diagram the two paths accurately: the transaction manager uses the **target DataSource**, while JDBC code needing compatibility uses the **transaction-aware proxy**.
3. Understand how the proxy acquires a connection, handles `close()`, and applies timeouts to JDBC `Statement`s.
4. Build a runnable Java 17+ application proving rollback still works even when a DAO calls standard `getConnection()`/`close()`.
5. Recognize the limitations: the proxy does not start transactions on its own, cannot fix a DAO that actively calls `commit()`, and does not automatically propagate transactions to other threads.
6. Distinguish this proxy from `DataSourceUtils`, `JdbcTemplate`, and `LazyConnectionDataSourceProxy`.

**Scope:** integrating JDBC code that needs adaptation into Spring transactions. This article does not replace knowledge of transaction management, connection pools, or SQL isolation, though it uses those concepts to explain the mechanism accurately.

## 2. What Happens Without the Proxy?

In Spring JDBC, `DataSourceTransactionManager` or `JdbcTransactionManager` typically manages a specific `DataSource`. When starting a transaction, Spring acquires a connection from that source, configures the transaction, and binds a `ConnectionHolder` to the current thread's transaction context. APIs such as `JdbcTemplate` and `DataSourceUtils.getConnection(targetDataSource)` know how to look up the thread-bound connection.

Pure JDBC code only using:

```java
Connection connection = targetDataSource.getConnection();
```

does not automatically invoke `DataSourceUtils`. With an implementation that returns a fresh connection every time (such as `DriverManagerDataSource`), this connection can sit outside the active transaction; with a pool, it can borrow a different connection from the pool. If the DAO executes a write and closes the connection, the result may already be committed independently in auto-commit mode.

Balance transfer flow example:

```text
Spring service starts transaction T1
  ├─ Legacy DAO: debit account A via targetDataSource.getConnection()
  │     └─ Connection C2, outside T1, may auto-commit
  ├─ Legacy DAO: credit account B encounters an error
  └─ Spring rolls back T1
       └─ Cannot roll back changes already committed on C2
```

Do not conclude that every `getConnection()` outside Spring always auto-commits: that behavior depends on the `DataSource`, driver, container, and configuration. The key point is that **there is no guarantee of participating in Spring's transaction-bound connection** merely by calling standard JDBC APIs on the target.

## 3. How Does TransactionAwareDataSourceProxy Work?

`TransactionAwareDataSourceProxy` wraps another `DataSource`, called the **target DataSource**. It returns a JDBC `Connection` proxy when code calls `getConnection()`. That connection proxy coordinates with `DataSourceUtils`:

- Inside an active Spring transaction synchronized on the same target, it finds and uses the connection already bound to the transaction.
- When the DAO calls `close()` on the connection proxy, Spring handles releasing via `DataSourceUtils.releaseConnection(...)`. A connection belonging to an active transaction **is not closed physically too early**; the transaction manager completes commit/rollback first and then releases it.
- Outside a transaction, acquiring and releasing the connection falls back to the target's normal JDBC access behavior (physically closing or returning to the pool, depending on implementation).
- JDBC `Statement`, `PreparedStatement`, and `CallableStatement` instances created through the connection proxy can receive **the remaining time of the Spring transaction timeout** via Spring's supported mechanism.
- The returned connection is a **wrapped handle**, not by default the native connection object itself. `Connection.unwrap(...)` or the `ConnectionProxy` interface lets you access the target connection when genuinely necessary, though accessing the native connection directly can bypass the proxy's purpose.

Correct illustration:

```text
                  Spring-managed transaction T1
                               │
                 (transaction manager)
                               │
                               ▼
                    target DataSource ◄─────────────── JdbcTemplate
                               ▲                        (already DataSourceUtils-aware)
                               │
             TransactionAwareDataSourceProxy
                               ▲
                               │ getConnection(), close()
                       LegacyJdbcDao
                               ▲
                               │
                         Spring service
```

Spring transaction synchronization is tied to the corresponding execution context (usually thread-bound in synchronous JDBC transactions). The proxy **does not create transactions**, **does not turn a JDBC driver into XA/JTA**, and **does not guarantee propagating transaction context to `@Async`, `CompletableFuture`, or another thread**. Having multiple independent resources commit atomically requires an appropriate transaction solution; the proxy alone is insufficient.

### Clarity on the two proxy layers

`TransactionAwareDataSourceProxy` is not a connection pool. You can wrap `HikariDataSource` or another implementation with it. Distinguish clearly:

- **DataSource proxy:** shared object in the application context implementing the `DataSource` interface.
- **Connection proxy:** handle returned to legacy JDBC code; it routes operations to the connection appropriate for the transaction context.
- **Physical JDBC connection:** actual socket/session managed by the driver/pool. Closing the handle does not always mean closing the physical connection.

Spring Framework 6.1.2+ includes the option `setLazyTransactionalConnections(boolean)`, defaulting to `true`: calling `getConnection()` on the proxy does not necessarily open a physical connection immediately; it may defer until an actual operation. The `setReobtainTransactionalConnections(boolean)` option defaults to `false` and should only be adjusted when you thoroughly understand the related transaction/container behavior. Do not toggle these flags by guesswork.

## 4. Mandatory Wiring: Target for the Transaction Manager, Proxy for Legacy DAOs

Usually **two beans with distinct roles sharing one target** are needed:

```java
@Configuration
public class JdbcConfiguration {
    @Bean("targetDataSource")
    public DataSource targetDataSource() {
        // Create or acquire the real implementation: pool, JNDI, ...
        return createConfiguredDataSource();
    }

    @Bean("legacyDataSource")
    public DataSource legacyDataSource(
            @Qualifier("targetDataSource") DataSource target) {
        return new TransactionAwareDataSourceProxy(target);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            @Qualifier("targetDataSource") DataSource target) {
        return new DataSourceTransactionManager(target);
    }
}
```

This is an **illustrative snippet**, because `createConfiguredDataSource()` represents an actual factory and must be replaced with a proper implementation; section 6 provides a standalone runnable project.

Dependency graph to maintain:

```text
targetDataSource: Hikari / DriverManager / JNDI DataSource
 ├─► DataSourceTransactionManager(targetDataSource)
 ├─► JdbcTemplate(targetDataSource)
 └─► TransactionAwareDataSourceProxy(targetDataSource)
         └─► LegacyJdbcDao(legacyDataSource)
```

**Important rule:** the transaction manager manages the **target**; do not use the transaction-aware proxy bean as the primary datasource configuration. In some versions, `DataSourceTransactionManager` may automatically unwrap it if it accidentally receives a `TransactionAwareDataSourceProxy`; that is defensive behavior, not a model to rely on. `JdbcTemplate` supports Spring transactions natively, so it should use the target directly, avoiding unnecessary proxy wrapping.

When there are multiple beans of type `DataSource`, inject using `@Qualifier("targetDataSource")` and `@Qualifier("legacyDataSource")`, or name them precisely per configuration. If you inject bare `DataSource`, Spring may not know which bean to pick (or may pick an unintended `@Primary` bean). Bean names, bean types, and the list of transaction managers must be verified at runtime.

### Combining with LazyConnectionDataSourceProxy

If the application uses `LazyConnectionDataSourceProxy`, the wrapper order according to Spring's javadoc is:

```text
Legacy DAO
    ↓
TransactionAwareDataSourceProxy      ← outermost
    ↓
LazyConnectionDataSourceProxy       ← optional
    ↓
Connection pool / real target
    ↓
Database
```

The transaction manager then needs to manage the same **`LazyConnectionDataSourceProxy`** that the transaction-aware proxy wraps, keeping the transaction-bound resource key consistent. Do not have the transaction manager use a different datasource from the target Spring uses to synchronize connections. `LazyConnectionDataSourceProxy` optimizes when a connection is acquired; `TransactionAwareDataSourceProxy` solves compatibility with raw JDBC. They solve two different problems.

## 5. Choosing a Solution for New Code vs. Code Needing Compatibility

| Can you modify the code? | Appropriate Approach | Why? |
| --- | --- | --- |
| New code using Spring JDBC | `JdbcTemplate`, `NamedParameterJdbcTemplate` | Built-in connection, statement, exception management, and transaction participation |
| New JDBC code needing direct `Connection` API | `DataSourceUtils.getConnection(target)` and `releaseConnection(...)` in `finally` | Explicitly uses Spring's transaction synchronization |
| Legacy library/DAO only accepting `javax.sql.DataSource`, calling `getConnection()` and `close()` | Pass `TransactionAwareDataSourceProxy` | No need to change the JDBC contract in legacy code |
| Legacy code manually calling `commit()`, `rollback()`, or changing `autoCommit` uncontrollably | Analyze and fix how transactions are defined in the legacy code | The proxy cannot fix arbitrary manual transaction logic |
| Reactive R2DBC application | Reactive connection factory and reactive transaction manager | Thread-bound JDBC proxies do not replace reactive transactions |

For new code, directly using Spring utilities (a snippet inside a method, not a standalone program):

```java
Connection connection = DataSourceUtils.getConnection(targetDataSource);
try {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT COUNT(*) FROM accounts")) {
        try (ResultSet result = statement.executeQuery()) {
            if (result.next()) {
                System.out.println(result.getInt(1));
            }
        }
    }
} finally {
    DataSourceUtils.releaseConnection(connection, targetDataSource);
}
```

Do not call `connection.close()` directly in code using `DataSourceUtils` on the target while skipping `releaseConnection`: Spring needs to know whether the connection is bound to a transaction. For legacy code receiving the transaction-aware proxy, calling `connection.close()` is right because the proxy handles it for you.

## 6. Runnable Java 17 Example: Legacy DAO Still Rolls Back with Spring

This example uses **Spring Framework 6.2.14**, **H2 2.3.232**, and Java 17+, demonstrating the principle without Spring Boot or an externally installed database. `DriverManagerDataSource` is strictly for demo purposes: it **does not pool**. In production, replace it with a properly lifecycle-managed pool.

### 6.1. Creating the project

```text
transaction-aware-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/TransactionAwareDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'transaction-aware-demo'
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
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.TransactionAwareDemo'
}
```

`src/main/java/demo/TransactionAwareDemo.java`:

```java
package demo;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;
import org.springframework.transaction.support.TransactionTemplate;

public class TransactionAwareDemo {

    @Configuration
    static class Config {
        // Target used by the transaction manager and JdbcTemplate.
        @Bean("targetDataSource")
        DataSource targetDataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:txaware;DB_CLOSE_DELAY=-1", "sa", "");
        }

        // Proxy provided only to raw JDBC DAOs needing compatibility.
        @Bean("legacyDataSource")
        DataSource legacyDataSource(
                @Qualifier("targetDataSource") DataSource target) {
            return new TransactionAwareDataSourceProxy(target);
        }

        @Bean
        JdbcTemplate jdbcTemplate(
                @Qualifier("targetDataSource") DataSource target) {
            return new JdbcTemplate(target);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                @Qualifier("targetDataSource") DataSource target) {
            return new TransactionTemplate(
                    new DataSourceTransactionManager(target));
        }

        @Bean
        LegacyAccountDao legacyAccountDao(
                @Qualifier("legacyDataSource") DataSource legacy) {
            return new LegacyAccountDao(legacy);
        }
    }

    // DAO only knows standard JDBC APIs, without importing Spring libraries.
    static class LegacyAccountDao {
        private final DataSource dataSource;

        LegacyAccountDao(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        void addToBalance(long accountId, int delta) {
            String sql = """
                    UPDATE accounts
                    SET balance = balance + ?
                    WHERE id = ?
                    """;
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement =
                         connection.prepareStatement(sql)) {

                statement.setInt(1, delta);
                statement.setLong(2, accountId);
                int updated = statement.executeUpdate();
                if (updated != 1) {
                    throw new IllegalStateException(
                            "Account not found: " + accountId);
                }
            } catch (SQLException e) {
                throw new IllegalStateException("JDBC failed", e);
            }
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx = context.getBean(TransactionTemplate.class);
            LegacyAccountDao dao = context.getBean(LegacyAccountDao.class);

            jdbc.execute("""
                    CREATE TABLE accounts (
                        id BIGINT PRIMARY KEY,
                        balance INT NOT NULL CHECK (balance >= 0)
                    )
                    """);
            jdbc.update("INSERT INTO accounts VALUES (?, ?)", 1L, 100);
            jdbc.update("INSERT INTO accounts VALUES (?, ?)", 2L, 60);

            // Both DAO getConnection()/close() calls participate in T1.
            tx.executeWithoutResult(status -> {
                dao.addToBalance(1L, -25);
                dao.addToBalance(2L, 25);
            });
            System.out.println("after commit: " + balances(jdbc));

            // Error escapes callback => rolls back the 10 deduction.
            try {
                tx.executeWithoutResult(status -> {
                    dao.addToBalance(1L, -10);
                    throw new IllegalStateException("simulate failure");
                });
            } catch (IllegalStateException expected) {
                // Ignore only the intentionally thrown error demonstrating rollback.
            }
            System.out.println("after rollback: " + balances(jdbc));
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer first = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 1L);
        Integer second = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 2L);
        return first + "," + second;
    }
}
```

In the project directory with Gradle installed, run:

```bash
gradle run
```

If you have Gradle Wrapper: on Linux/macOS use `./gradlew run`, on Windows use `gradlew.bat run`. The two lines **produced by `System.out.println`** are:

```text
after commit: 75,85
after rollback: 75,85
```

Gradle or framework logs may also appear. Explaining the numbers:

- Initially account 1 has 100 and account 2 has 60.
- The first transaction calls the DAO twice: account 1 decreases by 25 to 75, account 2 increases by 25 to 85; when the callback completes, it commits.
- The second transaction decreases account 1 by another 10, then throws an unchecked exception. `TransactionTemplate` rolls back; the result remains 75 and 85.
- The DAO **does not import Spring**, knowing only `DataSource`, `Connection`, `PreparedStatement`, and `SQLException`. `try-with-resources` closes the connection *proxy handle*, while Spring keeps the real connection until the transaction ends.
- If the `targetDataSource` bean is mistakenly passed into a raw JDBC DAO, e.g. with `DriverManagerDataSource`, it may use a different connection outside the transaction; a rollback test will expose the bug.

This program uses **programmatic** transactions (`TransactionTemplate`) to focus on observing the proxy's behavior. In real applications, transactions can also be opened by `@Transactional` via Spring AOP: the underlying JDBC proxy mechanism remains the same.

### 6.2. What changes with @Transactional?

In a Spring-managed service with `@EnableTransactionManagement` or corresponding transaction configuration, you can write:

```java
// Illustrative snippet, not an addition to copy verbatim
// into the standalone program above; requires beans/services and imports.
@Service
public class TransferService {
    private final LegacyAccountDao dao;

    public TransferService(LegacyAccountDao dao) {
        this.dao = dao;
    }

    @Transactional
    public void transfer(long from, long to, int amount) {
        dao.addToBalance(from, -amount);
        dao.addToBalance(to, amount);
    }
}
```

The transaction interceptor must actually execute when invoking the bean, and the transaction manager must be configured with the **target DataSource**. In the commonly used proxy mode, self-invocation (a method calling another `@Transactional` method on the same object) does not go through the proxy and will not receive the expected semantics. Do not assume "annotation present means transaction active" without an integration rollback test through a Spring-managed service.

## 7. Detailed Analysis of getConnection(), close(), and Transaction Timeout

### 7.1. When a Spring transaction is active

1. The transaction manager creates/binds a connection for the target DataSource to the current transaction.
2. The DAO calls `transactionAwareDataSource.getConnection()`; it receives a JDBC connection handle capable of resolving the transactional connection via `DataSourceUtils`.
3. The DAO creates a `PreparedStatement`, binds parameters, and runs SQL. The SQL executes on the transaction-bound connection.
4. The DAO calls `connection.close()`, usually via `try-with-resources`. The proxy releases the handle; the transactional connection remains held by Spring.
5. If the service finishes normally, the manager commits; if an error matches rollback rules, the manager rolls back, then returns/closes the connection.

This explains why **a legacy DAO can close the connection after every method without breaking a multi-step transaction**. Even so, the DAO must avoid calling `commit()`, `rollback()`, or modifying `autoCommit` arbitrarily; such operations can violate the boundaries Spring owns. The proxy does not turn improper legacy transaction management into safe code.

### 7.2. When no Spring transaction is active

The proxy does not automatically call `beginTransaction`, nor does it turn every method into an atomic transaction. It simply delegates acquiring/closing connections according to the target's normal behavior. With a driver defaulting to auto-commit, each statement can commit individually. If multi-step atomicity is desired, create a transaction with `TransactionTemplate`, `@Transactional`, or an appropriate mechanism.

### 7.3. Transaction timeout

When a Spring transaction has a timeout and legacy JDBC code creates a `Statement` or `PreparedStatement` via the connection proxy, Spring can apply the remaining transaction time as the query timeout. For example:

```java
TransactionTemplate tx = new TransactionTemplate(
        new DataSourceTransactionManager(targetDataSource));
tx.setTimeout(5); // seconds; only applies when using this tx instance
tx.executeWithoutResult(status -> legacyDao.runDatabaseOperation());
```

This is an illustrative snippet; `legacyDao.runDatabaseOperation()` represents an actual API. Pool connection wait timeout, socket read timeout, and total transaction timeout **are not the same value**; drivers and databases may enforce timeouts differently. A transaction timeout does not automatically cancel non-JDBC work or undo side effects outside the database.

## 8. Mandatory Limitations to Remember

| Case | Does the Proxy Help? | Real Boundary |
| --- | --- | --- |
| DAO uses standard `dataSource.getConnection()` and `close()` | Yes, given proper proxy, target, and Spring transaction | Routes to the transactional connection |
| DAO needs to join a Spring transaction without importing Spring | Yes | Only the injected DataSource needs changing |
| No active transaction | Does not create a transaction | Follows the target's default behavior |
| DAO manually calls `commit()`/`rollback()` or alters `autoCommit` | Safety is not guaranteed | Must adjust the DAO's transaction logic |
| `@Transactional` on a method hit by self-invocation | Does not solve | The JDBC proxy does not fix Spring AOP invocation |
| Async job on another thread | Does not auto-propagate context | Thread-bound transactions require explicit boundary handoff/isolation |
| Two databases, two independent connection pools | Does not become a distributed transaction | Requires an appropriate transaction architecture |
| New code already using `JdbcTemplate` | Unnecessary | JdbcTemplate already uses DataSourceUtils |
| Reactive R2DBC and reactive transactions | Not applicable | Synchronous JDBC proxy does not replace R2DBC |
| App suffers connection exhaustion, slow SQL, or deadlocks | Does not fix automatically | Observe pool, SQL, locking, and timeouts |

**Do not use the proxy as a cure-all for every transaction bug.** If business design involves two databases not participating in one transaction, or if code touches external APIs or commits manually, wrapping the DataSource only handles JDBC connection acquisition.

## 9. Common Configuration Errors and How to Diagnose Them

### 9.1. Proxy and transaction manager point to the wrong target

**Symptom:** two DAOs run SQL normally yet fail to roll back together.

**Check:** verify which beans Spring injects into the DAO, `JdbcTemplate`, and transaction manager; inspect `DataSource` types/names, `@Qualifier`, pools, and target objects. Creating a separate target/pool per call site breaks consistent connection binding.

### 9.2. Ambiguous DataSource beans

**Symptom:** `NoUniqueBeanDefinitionException` because both target and transaction-aware proxy implement `DataSource`.

**Solution:** name beans clearly and use qualifiers at injection points; do not rely on an accidental `@Primary` picking the right bean. With Spring Boot, inspect both auto-configuration and application-defined beans to avoid conflicts.

### 9.3. DAO receives target instead of proxy

**Symptom:** the DAO still works, yet fails to roll back with the transaction in the demo. This is a dangerous bug because tests that only check the happy path may still PASS.

**Solution:** test a case that intentionally throws an exception *after an UPDATE* and verify the DB is unchanged; assert the exact bean supplied to the DAO.

### 9.4. DAO controls transactions itself

**Symptom:** `commit()` or `setAutoCommit(true)` appears inside the DAO; behavior mismatches service boundaries.

**Solution:** locate and remove or move transaction orchestration up to the service/transaction manager; keep the DAO managing only JDBC resources per agreed contract. Do not expect the transaction-aware proxy to block every `Connection` API call.

### 9.5. Connections held too long

**Symptom:** pool exhaustion, timeouts, or concurrent operations waiting despite having the proxy.

**Solution:** always close handles within scope; do not retain connections/statements in singleton fields or beyond callback lifecycles. Avoid making long HTTP calls inside a transaction when unnecessary; investigate query durations, locks, and connection pool metrics.

### 9.6. Failures occurring after switching threads

**Symptom:** code running via `CompletableFuture` or `@Async` uses a different connection and does not roll back with the initiating transaction.

**Solution:** understand that synchronous JDBC transactions are bound to execution context; establish a new transaction where async work runs when appropriate, or design a distributed workflow. The proxy does not copy `ThreadLocal` to other threads.

### 9.7. Timeouts behaving unexpectedly

**Symptom:** queries still run too long, or the connection pool reports a different timeout from the Spring transaction timeout.

**Solution:** distinguish JDBC statement timeout, transaction timeout, pool acquisition timeout, and network timeout. Inspect driver configuration, transaction manager, and actual SQL; log with context without exposing credentials.

## 10. When to Drop the Adapter and Move to Spring JDBC?

`TransactionAwareDataSourceProxy` fits when **you must preserve the JDBC contract of existing code**; it supports gradual integration without forcing rewrites of legacy libraries/DAOs. However, new code should generally choose:

- `JdbcTemplate`: coordinates connections, statements, mapping, exception translation, and transaction participation without needing a transaction-aware proxy.
- `NamedParameterJdbcTemplate`: SQL with named parameters, useful for many values.
- `DataSourceUtils`: when manual JDBC is still needed, yet you can write Spring-aware code.
- `TransactionTemplate`/`@Transactional`: defines **business** transaction boundaries, rather than letting an individual CRUD method decide.

Purpose comparison example:

```java
// Legacy DAO: needs a DataSource proxy to participate in a Spring transaction.
Connection c = legacyDataSource.getConnection();

// New DAO: JdbcTemplate natively uses Spring's resource coordination.
jdbcTemplate.update("UPDATE accounts SET balance = ? WHERE id = ?",
        newBalance, id);
```

These are **two illustrative snippets in a context where the corresponding beans/variables already exist**; not a standalone Java file. New code does not need a `TransactionAwareDataSourceProxy` merely because `@Transactional` is used.

## 11. Hands-on Exercises and Passing Criteria

**Exercise 1 — Prove the adapter works:** run the project in section 6 and verify the two stdout lines. Change only the bean injected into `LegacyAccountDao` from `legacyDataSource` to `targetDataSource`, then repeat the rollback case. With `DriverManagerDataSource` as in the demo, observe the risk of the DAO's UPDATE committing independently. Then restore the proper injection. This is a learning experiment, **not a production configuration**.

**Exercise 2 — Intentional layering:** add a `JdbcTemplate` repository using the same `targetDataSource` and coordinate one UPDATE from the legacy DAO and one UPDATE from `JdbcTemplate` inside the same `TransactionTemplate`. Intentionally throw an exception and assert both operations roll back. You must explain why the two access paths still share the same transactional connection.

**Exercise 3 — Replace demo H2 with a pool:** use HikariCP or an infrastructure-managed pool instead of `DriverManagerDataSource`. Still keep only one target pool; transaction manager and JdbcTemplate use the target, while the legacy DAO uses the outermost wrapper. Add an integration test verifying rollback and that connections return to the pool.

**Exercise 4 — Test thread boundaries:** from within a transaction, dispatch a task through an executor and use the legacy DAO on the worker thread. Explain why the connection may differ and is not bound to the same transaction by default. Instead of trying to share one JDBC connection across threads, redesign the transaction boundary or work mechanism.

**You pass when you can answer on your own:**

1. Does `TransactionAwareDataSourceProxy` start a transaction on its own? **No.**
2. Should the transaction manager receive the target or the transaction-aware proxy? **Target.**
3. Why can the DAO call `close()` yet the transaction still rolls back? **Because closing the proxy handle coordinates via DataSourceUtils; the underlying transactional connection is retained until the end.**
4. Should you use this proxy for every `JdbcTemplate`? **Unnecessary; JdbcTemplate already supports Spring transactions.**
5. Why might direct JDBC code on the target fail to roll back with Spring? **Because getConnection() does not automatically look up the Spring-bound connection.**
6. Can it wrap `LazyConnectionDataSourceProxy`? **Yes, with TransactionAwareDataSourceProxy outermost and the transaction manager managing the same lazy target.**
7. Why do two different DataSources or two threads not automatically become one transaction? **Because resource synchronization requires the matching object/context and an appropriate transaction type.**

## 12. Official References

- Spring Framework — Controlling Database Connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework 6.2 API — `TransactionAwareDataSourceProxy`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework 6.2 API — `DataSourceUtils`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html

To summarize within the scope of this mechanism: **the transaction manager holds the target DataSource; legacy JDBC code receives the transaction-aware proxy; Spring coordinates the real connection until commit/rollback**. That is the appropriate use of this adapter.