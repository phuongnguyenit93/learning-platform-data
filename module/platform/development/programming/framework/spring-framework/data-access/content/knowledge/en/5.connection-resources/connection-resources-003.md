# DataSourceUtils and Connections Participating in the Current Transaction

> **Topic:** Spring Framework – Data Access  
> **Knowledge Group:** Connections and Resources

## 1. Why Is `DataSourceUtils` Needed?

Suppose a business method performs two operations on the same database: creating an order and writing an audit record. Both must commit or roll back together. In Spring, `@Transactional` or `TransactionTemplate` can define the transaction boundary, yet custom-written JDBC code must still **obtain the exact `Connection` participating in the transaction**. If a DAO acquires a fresh connection from the pool on its own, that operation may auto-commit and fail to roll back with the service's transaction.

`org.springframework.jdbc.datasource.DataSourceUtils` is a Spring JDBC utility for acquiring and releasing a JDBC connection **with awareness of the transaction context**. The basic API pair is:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    // Execute JDBC using connection.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

This pattern lives inside a method that already has `dataSource`; you must still close any `PreparedStatement` and `ResultSet` you create yourself. A runnable Maven example is provided in section 7.

**Key idea:** if Spring has already bound a connection to the current transaction, `getConnection` finds that connection. If the connection still belongs to a transaction, `releaseConnection` does not close it prematurely. When there is no managed transaction or synchronization, the same API still acquires and releases a connection normally.

`DataSourceUtils` helps **participate** in an already managed transaction; it **does not start, commit, or roll back** a business transaction on its own.

## 2. Four Components and Responsibility Boundaries

| Component | Responsible For | Does Not Do Automatically |
| --- | --- | --- |
| `DataSource` | Supplying JDBC `Connection`s; typically backed by a pool | Guaranteeing every `getConnection()` participates in a Spring transaction |
| `DataSourceUtils` | Looking up/releasing connections with awareness of resource binding | Opening, committing, or rolling back business transactions |
| `PlatformTransactionManager`, such as `DataSourceTransactionManager` | Starting/joining JDBC transactions, configuring state, and commit/rollback/cleanup | Fixing JDBC code that acquires a different connection by mistake |
| `TransactionSynchronizationManager` | Holding resources/synchronizations associated with the imperative execution thread | Serving as an API for DAOs to arbitrarily start transactions or bind resources manually |

Example of a `DataSourceTransactionManager` managing a `DataSource` shared with a DAO:

~~~text
@Service / @Transactional or TransactionTemplate
                │
                ▼
       DataSourceTransactionManager
        begin / commit / rollback
                │
                ▼
     TransactionSynchronizationManager
       └─ resource key: DataSource
          value: ConnectionHolder
                ▲
                │ looks up the bound connection
                │
        DataSourceUtils.getConnection(dataSource)
                ▲
                │
             JDBC DAO
                │
                ▼
       PreparedStatement / ResultSet
~~~

In a local JDBC transaction, the manager typically obtains a connection from `DataSource`, prepares auto-commit/isolation/read-only per appropriate configuration, and binds the resource to the thread. A `DataSourceUtils.getConnection` call using that exact `DataSource` can retrieve that connection.

Distinguish **resource management** (acquiring/returning connections) from **transaction management** (choosing the atomic scope and commit/rollback). The same DAO call may need both; neither responsibility replaces the other.

## 3. How `getConnection(DataSource)` Works

API signature:

~~~java
Connection con = DataSourceUtils.getConnection(dataSource);
~~~

Conceptually, Spring performs the following:

1. Checks whether a `ConnectionHolder` resource is already bound to `DataSource` in `TransactionSynchronizationManager` on the current thread.
2. If a matching connection exists, uses that connection.
3. If none exists yet, obtains a connection from `DataSource`. When transaction synchronization is active, Spring may bind it and register cleanup so subsequent calls in the same context participate properly.
4. If no managed transaction synchronization is active, the connection is acquired as in regular JDBC; the caller must release it after use.

Spring supports resource synchronization with `DataSourceTransactionManager` and certain JTA/JPA configurations. Therefore, do not infer that `DataSourceUtils` only works when a method carries `@Transactional`; the API inspects the **execution context**, rather than scanning source code for annotations.

### 3.1. With a Spring-managed JDBC transaction

With a `DataSourceTransactionManager` actively running a transaction on the same `DataSource`:

~~~java
Connection a = DataSourceUtils.getConnection(dataSource);
Connection b = DataSourceUtils.getConnection(dataSource);
try {
    // In a standard JDBC transaction configuration, a and b
    // both refer to the connection Spring has bound.
} finally {
    DataSourceUtils.releaseConnection(b, dataSource);
    DataSourceUtils.releaseConnection(a, dataSource);
}
~~~

This illustrative snippet **only asserts the same connection when the transaction and data source conditions hold**. Outside a transaction, two calls may receive two different connections. In systems with wrappers/proxies, do not use object-identity comparison across all handle types as a substitute for verifying commit/rollback.

### 3.2. Without a transaction

Calling `DataSourceUtils.getConnection` is still valid. The API does not automatically call `begin` and does not turn separate SQL statements into an atomic unit. Depending on driver/connection configuration, JDBC may auto-commit each statement.

For example, calling `jdbcTemplate.update(...)` twice outside a transaction can produce two separately committed changes. Both calls acquiring and releasing connections cleanly **does not guarantee** rolling back together if a failure occurs between the two.

### 3.3. Distinguishing an actual transaction from synchronization

`TransactionSynchronizationManager` tracks state related to both an **actual active transaction** and **transaction synchronization**. `DataSourceUtils` can bind a connection when synchronization is active, even when the JDBC resource is enlisted/acquired lazily in an appropriate JTA or JPA context. Therefore:

- `TransactionSynchronizationManager.isSynchronizationActive()` does not imply that an open local JDBC transaction exists everywhere.
- `DataSourceUtils.isConnectionTransactional(con, dataSource)` checks whether the connection is recognized as a resource bound by Spring for this thread and data source.
- Do not manually call `TransactionSynchronizationManager.bindResource(...)` or `unbindResource(...)` inside a normal DAO to "force" transaction participation; this is infrastructure that must follow a proper lifecycle.

## 4. Important APIs to Know

### 4.1. `getConnection` and `doGetConnection`

~~~java
Connection c = DataSourceUtils.getConnection(dataSource);
~~~

`getConnection` handles connection-acquisition failures as unchecked exceptions, such as `CannotGetJdbcConnectionException` (a type of `DataAccessException`). The `doGetConnection(dataSource)` variant performs the same lookup but can throw the original `SQLException` under a checked-exception contract.

**Exception translation boundary:** `getConnection` translating **connection-acquisition** errors does not mean manual SQL statements throwing `SQLException` are also automatically translated. `JdbcTemplate` provides exception translation for higher-level JDBC operations.

### 4.2. `releaseConnection` and `doReleaseConnection`

~~~java
DataSourceUtils.releaseConnection(c, dataSource);
~~~

If the connection is a resource Spring currently binds to a transaction/synchronization, this call **does not close it**. Closing/returning to the pool is managed at the appropriate time after the transaction.

If the connection is not managed by a thread-bound resource, Spring releases it according to `DataSource` rules. With a pool, `Connection.close()` usually returns the logical connection to the pool; with a demo `DriverManagerDataSource`, the connection is usually physically closed. The `doReleaseConnection` variant allows propagating `SQLException` in certain low-level usage scenarios.

Do not interpret "release" as "commit", "rollback", or "always close socket". These are three distinct concepts.

### 4.3. `isConnectionTransactional`

~~~java
boolean transactional =
        DataSourceUtils.isConnectionTransactional(c, dataSource);
~~~

`true` means Spring recognizes the connection as bound to a transaction resource on the **current thread** for the supplied `DataSource`. `false` does not mean the database cannot run SQL, nor does it prove auto-commit is on; it only indicates Spring does not recognize a corresponding resource binding.

This is a debugging signal, not an API for a DAO to decide to call `commit()` itself upon seeing `false`. Transaction boundaries belong to the service/transaction manager.

### 4.4. `applyTransactionTimeout`

For a manual `PreparedStatement`, Spring lets you apply the remaining transaction timeout (if any):

~~~java
DataSourceUtils.applyTransactionTimeout(preparedStatement, dataSource);
~~~

This API sets the query timeout on the JDBC statement when the context has an applicable timeout. `JdbcTemplate` already supports timeouts per Spring configuration; there is no need to call this redundantly in a DAO using `JdbcTemplate`. Timeouts depend on the driver/database and do not guarantee forcible termination of every external or non-database operation.

## 5. Why Can Calling `DataSource.getConnection()` Directly Bypass a Transaction?

Consider a service where Spring has opened a transaction on `appDataSource`, yet a DAO executes:

~~~java
try (Connection connection = appDataSource.getConnection()) {
    // Perform INSERT via raw JDBC.
}
~~~

If `appDataSource` is a pool or a regular `DataSource`, calling `getConnection()` directly can hand out **a different connection** from the one Spring bound. If the new connection has auto-commit enabled, the INSERT may commit immediately. Later, when the service rolls back, only operations that participated in Spring's connection/transaction are rolled back properly.

Replacement code for Spring integration:

~~~java
Connection connection = DataSourceUtils.getConnection(appDataSource);
try {
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO audit_log(id, description) VALUES (?, ?)")) {
        ps.setLong(1, 101L);
        ps.setString(2, "created");
        DataSourceUtils.applyTransactionTimeout(ps, appDataSource);
        ps.executeUpdate();
    }
} catch (SQLException ex) {
    throw new IllegalStateException("Cannot write audit log", ex);
} finally {
    DataSourceUtils.releaseConnection(connection, appDataSource);
}
~~~

This is an **illustrative snippet inside a method** where `appDataSource` and table `audit_log` already exist. Inside a properly managed transaction, this code participates in the bound connection. Outside a transaction, it still acquires and releases the connection properly.

### 5.1. Do not use `try-with-resources` to close a bound connection

Avoid:

~~~java
// Wrong approach inside a Spring-managed transaction:
try (Connection c = DataSourceUtils.getConnection(dataSource)) {
    // ...
}
~~~

Java will automatically call `c.close()` at the end of the block, bypassing `DataSourceUtils.releaseConnection` rules. That can close a connection the transaction still needs or is preparing to commit/roll back.

**Correct approach:** use `try-with-resources` for `PreparedStatement` and `ResultSet` owned by your code; use `try/finally` and `DataSourceUtils.releaseConnection` for `Connection`. Do not directly call `connection.commit()`, `rollback()`, or change `setAutoCommit(...)` on a connection managed by Spring.

### 5.2. Releasing in a DAO does not end the transaction

~~~text
Service opens transaction
    ├── DAO A: getConnection → INSERT A → releaseConnection
    │         (Connection stays held if bound)
    ├── DAO B: getConnection → INSERT B → releaseConnection
    │         (still participates in the same transaction)
    └── Service finishes:
             transaction manager commits or rolls back
             cleanup, unbind, returns connection to DataSource/pool
~~~

A frequently misunderstood point: **ending the resource access scope** does not mean **ending the business transaction**. Even when `releaseConnection` is called early, the transaction manager still controls the bound connection until the appropriate moment.

## 6. Preferred Approach: `JdbcTemplate`

If the goal is executing standard SQL, `JdbcTemplate` is usually better than managing JDBC connections manually:

~~~java
int rows = jdbcTemplate.update(
        "UPDATE orders SET status = ? WHERE id = ?",
        "DONE", orderId);
~~~

Internally, `JdbcTemplate` acquires/releases connections compatibly with `DataSourceUtils`; it also manages statements/result sets and translates JDBC errors into `DataAccessException`. The DAO focuses on SQL, parameters, and results; the transaction manager handles the transaction.

Use `DataSourceUtils` directly only when writing low-level JDBC adapters, integrating libraries that require a raw `Connection`, or using driver features not covered by the abstraction in use. Avoid mixing `JdbcTemplate` with raw connection handling without understanding the managed data source and transaction.

For example, a service using both a manual JDBC DAO and `JdbcTemplate` can still commit/roll back together **if both use the exact same `DataSource` and the same transaction**.

## 7. Java 17+ Demo: Bound Connection, Commit, and Rollback

The example uses Spring Framework JDBC **6.1.14**, H2 **2.2.224**, Maven, and Java **17+**. `DriverManagerDataSource` has no connection pool, making it suitable for demonstration rather than a default choice for production. `TransactionTemplate` lets us establish explicit transactions without configuring Spring AOP proxies.

Observation goals:

- `isConnectionTransactional` is `false` outside a transaction.
- Inside a transaction, two `getConnection` calls use the same bound connection.
- Manual JDBC and `JdbcTemplate` commit together.
- A subsequent INSERT that throws an error rolls back, even though code already called `releaseConnection`.

### 7.1. Project structure

~~~text
datasource-utils-demo/
├── pom.xml
└── src/main/java/demo/
    └── DataSourceUtilsDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>datasource-utils-demo</artifactId>
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

### 7.3. `src/main/java/demo/DataSourceUtilsDemo.java`

~~~java
package demo;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class DataSourceUtilsDemo {

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:dsutils_demo;DB_CLOSE_DELAY=-1", "sa", "");
        dataSource.setDriverClassName("org.h2.Driver");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE event_log (" +
                "id INT PRIMARY KEY, message VARCHAR(100) NOT NULL)");

        // Outside Spring transaction: connection is not bound by a transaction.
        Connection outside = DataSourceUtils.getConnection(dataSource);
        try {
            System.out.println("Outside Spring transaction: " +
                    DataSourceUtils.isConnectionTransactional(outside, dataSource));
        } finally {
            DataSourceUtils.releaseConnection(outside, dataSource);
        }

        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));

        tx.executeWithoutResult(status -> {
            Connection first = DataSourceUtils.getConnection(dataSource);
            Connection second = DataSourceUtils.getConnection(dataSource);
            try {
                System.out.println("Same transaction connection: " +
                        (first == second));
                System.out.println("Connection is transactional: " +
                        DataSourceUtils.isConnectionTransactional(first, dataSource));

                try (PreparedStatement statement = first.prepareStatement(
                        "INSERT INTO event_log(id, message) VALUES (?, ?)")) {
                    statement.setInt(1, 1);
                    statement.setString(2, "manual JDBC");
                    DataSourceUtils.applyTransactionTimeout(statement, dataSource);
                    statement.executeUpdate();
                }

                // JdbcTemplate joins the same transaction thanks to the same DataSource.
                jdbc.update("INSERT INTO event_log(id, message) VALUES (?, ?)",
                        2, "JdbcTemplate");
            } catch (SQLException ex) {
                throw new IllegalStateException("JDBC failure", ex);
            } finally {
                DataSourceUtils.releaseConnection(second, dataSource);
                DataSourceUtils.releaseConnection(first, dataSource);
            }
        });

        System.out.println("Rows after commit: " +
                jdbc.queryForObject("SELECT COUNT(*) FROM event_log", Integer.class));

        try {
            tx.executeWithoutResult(status -> {
                Connection c = DataSourceUtils.getConnection(dataSource);
                try (PreparedStatement statement = c.prepareStatement(
                        "INSERT INTO event_log(id, message) VALUES (?, ?)")) {
                    statement.setInt(1, 3);
                    statement.setString(2, "must rollback");
                    statement.executeUpdate();
                } catch (SQLException ex) {
                    throw new IllegalStateException("JDBC failure", ex);
                } finally {
                    DataSourceUtils.releaseConnection(c, dataSource);
                }
                throw new IllegalStateException("forced rollback");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Caught: " + expected.getMessage());
        }

        System.out.println("Rows after rollback: " +
                jdbc.queryForObject("SELECT COUNT(*) FROM event_log", Integer.class));
    }
}
~~~

Run inside `datasource-utils-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DataSourceUtilsDemo
~~~

**Lines printed by the application** (excluding Maven logs):

~~~text
Outside Spring transaction: false
Same transaction connection: true
Connection is transactional: true
Rows after commit: 2
Caught: forced rollback
Rows after rollback: 2
~~~

### 7.4. Step-by-step explanation

**Outside transaction.** `getConnection` acquires a connection from `DriverManagerDataSource`. Because the thread has no Spring transaction resource binding yet, `isConnectionTransactional` is `false`. `releaseConnection` closes the connection. The H2 parameter `DB_CLOSE_DELAY=-1` keeps the in-memory database alive across different connections in the same process.

**In the first transaction.** `TransactionTemplate` invokes `DataSourceTransactionManager` to begin a transaction. The manager acquires a connection, configures it for the transaction, and binds the resource. `first` and `second` refer to the same bound connection in the demo. Manual JDBC inserts row 1; `JdbcTemplate` inserts row 2 via the same `DataSource`. `releaseConnection` is called in the callback yet does not close the connection managed by the transaction manager. The callback completes normally, so the manager commits. Counting the table returns 2.

**In the second transaction.** The INSERT for row 3 succeeds at the SQL level, but the callback throws `IllegalStateException`, a runtime exception. `TransactionTemplate` rolls back and propagates the exception outward. The `catch` block prints `forced rollback`. Counting the table still returns 2, proving row 3 was not committed.

**What the example does not prove:** that every `DataSource`/proxy implementation always returns the exact same Java object under `==`; that all databases share identical isolation or timeout behavior; or that two separate databases will automatically roll back together. Always verify transaction boundaries and data after commit/rollback in a real environment.

## 8. Using with `@Transactional` in a Spring Application

A common architecture:

~~~java
@Service
public class CheckoutService {
    private final OrderDao orders;
    private final AuditDao audits;

    public CheckoutService(OrderDao orders, AuditDao audits) {
        this.orders = orders;
        this.audits = audits;
    }

    @Transactional
    public void checkout(long orderId) {
        orders.markCompleted(orderId);
        audits.recordCompleted(orderId);
    }
}
~~~

This is an architectural example, **not a standalone runnable class**: it requires two DAO beans, a transaction manager, and infrastructure processing `@Transactional`. When the call goes through a valid Spring proxy/interceptor, Spring creates or joins a transaction. DAOs using `JdbcTemplate` or `DataSourceUtils` on the same `DataSource` participate in the matching connection.

A few scenarios to understand:

- **Self-invocation:** a method calling `this.checkout(...)` within the same bean may bypass the proxy, so `@Transactional` will not have the desired effect.
- **Rollback:** by default, `RuntimeException` and `Error` cause a `@Transactional` transaction to roll back; checked exceptions may require `rollbackFor`. Catching and swallowing an exception can cause the manager to commit unless marked rollback-only.
- **Propagation:** `REQUIRED` joins an existing transaction or creates a new one; `REQUIRES_NEW` is an independent transaction and may need its own connection. "Same request" does not mean "same transaction".
- **Long transactions:** hold connections and locks for a long time; avoid network calls or waiting on external tasks inside a transaction when unnecessary.

Even with `@Transactional` present, a DAO can still accidentally use the wrong `DataSource` or acquire a connection straight from the pool. Therefore, verify both that **the transaction was activated** and that **the connection actually participates**.

## 9. `TransactionAwareDataSourceProxy` and `LazyConnectionDataSourceProxy`

### 9.1. Transaction-aware proxy for Spring-unaware JDBC code

If integrating legacy code that only calls:

~~~java
try (Connection c = dataSource.getConnection()) {
    // Raw JDBC.
}
~~~

and cannot be changed to `DataSourceUtils`, Spring provides `TransactionAwareDataSourceProxy` wrapping a target `DataSource`. The connection handle returned by the proxy coordinates `getConnection` and `close` according to Spring rules to participate in the appropriate transaction.

This explains why the statement "`dataSource.getConnection` always bypasses transactions" is **false** if the `dataSource` variable actually references a `TransactionAwareDataSourceProxy`. With a standard pool/`DataSource` without such a proxy, a direct call may obtain a connection outside the transaction.

When composing multiple DataSource proxies, configure their order carefully; `TransactionAwareDataSourceProxy` is usually the outermost layer of the proxy chain for legacy consumers. For new code, prefer `JdbcTemplate` or `DataSourceUtils` for readability and fewer wrapper dependencies.

### 9.2. Lazy connection acquisition proxy

`LazyConnectionDataSourceProxy` can defer acquiring a physical JDBC connection until a statement actually needs to execute. This is useful for "empty" transactions that do not end up hitting the database. Because a proxy is present, checking connections via object identity or driver connection IDs may not accurately reflect physical connection acquisition history; checking via Spring APIs and transaction outcomes remains more reliable.

Using a lazy proxy does not alter the core rules: DAOs still need the right data source and transaction manager, and connections must still follow proper lifecycle management.

## 10. Same Thread Does Not Guarantee Same `DataSource` or Same Transaction

`TransactionSynchronizationManager` tracks resources by a key bound to the data source. If the transaction manager manages `appDataSource` yet a DAO calls:

~~~java
Connection c = DataSourceUtils.getConnection(reportingDataSource);
~~~

then the connection from `reportingDataSource` does not automatically belong to `appDataSource`'s transaction. Likewise, creating a fresh `DriverManagerDataSource` with the same JDBC URL inside a DAO does not make Spring treat it as the same bound bean.

**Easy-to-control organization:**

- Inject `DataSource` and `JdbcTemplate` from the same data-source configuration into related DAOs.
- Have the transaction manager manage the exact `DataSource` used by the DAOs.
- With multiple data sources, clarify which manager is selected at each `@Transactional` and which source requires consistency.
- Do not treat a local `DataSourceTransactionManager` as an automatic distributed transaction mechanism across multiple databases.

### JPA and JTA

`DataSourceUtils` supports transaction synchronization in certain contexts using `JpaTransactionManager` or `JtaTransactionManager`. However, whether JDBC actually shares a JPA/JTA transaction depends on declaring the same `DataSource`, the provider, enlisted resources, and the transaction coordinator. Never assume every `EntityManager` and every JDBC `Connection` automatically share one transaction merely by being in the same service method.

In JPA, `EntityManager`/persistence context has its own lifecycle; do not treat it like a raw `Connection`. With reactive R2DBC, use `ConnectionFactory`, the matching transaction manager, and context; `DataSourceUtils` is a utility for imperative JDBC.

## 11. Transaction-Participating Connections Are Usually Thread-Bound

Spring's imperative transactions typically use `ThreadLocal` inside `TransactionSynchronizationManager` to manage the current thread's resources. Practical consequences:

- Do not store a `Connection` in a singleton DAO field or cache for reuse in another request.
- Do not pass a bound connection to another thread and assume it remains in the old transaction.
- `@Async`, `CompletableFuture.supplyAsync`, or a custom executor does not automatically carry the caller thread's imperative JDBC transaction; if async work needs a transaction, design a dedicated transaction inside that task.
- In code running on virtual threads, each thread still has its own context; splitting work across multiple threads does not automatically share one transaction.
- Always return the connection within the proper scope via `finally`; avoid holding it across network API calls or lengthy business steps.

**Do not assume** a Spring-bound connection is safe for multi-threaded use. Many JDBC `Connection` implementations do not guarantee thread safety for concurrent access.

## 12. Troubleshooting Table

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Service rolls back yet an INSERT persists | DAO uses raw `dataSource.getConnection` from a normal pool or a different source | Check how the connection is obtained, same DataSource, transaction manager |
| `isConnectionTransactional` returns `false` in DAO | No matching transaction/synchronization; different DataSource or different thread | Verify transaction is actually active and resource key is correct |
| `Connection is closed` before commit | DAO called `close()` on a bound connection or wrapped it in `try-with-resources` | Switch to `DataSourceUtils.releaseConnection`; close statements/result sets separately |
| Connection pool exhaustion | Missing release outside transactions, long transactions, or code holding connections | `finally` release, inspect active/idle/waiting counts and transaction duration |
| JDBC DAO does not roll back together with JPA | JDBC is not enlisted per JPA/JTA config or uses the wrong data source | Inspect JpaTransactionManager, DataSource, and provider setup |
| SQL error remains checked `SQLException` | Raw JDBC code does not use query exception translation | Prefer `JdbcTemplate` or handle/translate explicitly |
| Transaction timeout does not apply to manual statement | Query timeout was not applied to a DAO-created statement | `applyTransactionTimeout` or use JdbcTemplate |
| Outer transaction does not cover async job | Imperative transaction is thread-bound | Create a dedicated transaction in the async execution thread |
| `releaseConnection` does not close connection right away | Connection still belongs to a transaction; this may be expected behavior | Verify transaction completion and cleanup, do not force early close |

**Effective diagnostic order:** (1) does a real transaction boundary exist, (2) which transaction manager is active, (3) is it the same `DataSource` bean, (4) which API does the DAO use to get connections, (5) how is the connection released, (6) verify data after commit/rollback. When data errors occur, do not merely check whether `@Transactional` exists in source code.

## 13. Pitfalls to Avoid

**Pitfall 1: "`DataSourceUtils` will start a transaction automatically."** No. It acquires/releases connections in a context-aware manner; the service or `TransactionTemplate` must still open an appropriate transaction.

**Pitfall 2: "You can always call `Connection.close()`."** No. A connection bound by Spring must be returned via `releaseConnection` so the transaction manager continues managing it.

**Pitfall 3: "`releaseConnection` will commit."** No. It manages the resource, whereas commit/rollback belongs to the transaction manager.

**Pitfall 4: "Two DAOs sharing the same JDBC URL means they share a transaction."** No. Verify the `DataSource`, transaction manager, resource binding, and resource transaction participation.

**Pitfall 5: "`JdbcTemplate` needs manual `DataSourceUtils` calls before every query."** No. `JdbcTemplate` already integrates this mechanism.

**Pitfall 6: "Since there is a transaction, there is no need to close statements/result sets."** No. Closing statements/result sets promptly is independent of keeping the connection open for the transaction.

**Pitfall 7: "Exceptions from manual JDBC are always `DataAccessException`."** No. `DataSourceUtils` translates connection-level failures; `JdbcTemplate` handles translation for SQL operations it manages.

**Pitfall 8: "`@Transactional` automatically propagates across all threads."** Not in the standard imperative model. Design transactions separately for asynchronous work.

## 14. Self-Check Questions

**1. Is it an error to call `DataSourceUtils.getConnection` when no Spring transaction exists?**  
No. The API still acquires a connection; the calling code must release it and is not automatically guaranteed multi-statement rollback.

**2. In a `DataSourceTransactionManager` JDBC transaction, why can two DAOs using `DataSourceUtils` use the same connection?**  
Because the manager binds a connection holder to the current context keyed by `DataSource`; `DataSourceUtils` looks up that bound resource.

**3. Why shouldn't you write `try (Connection c = DataSourceUtils.getConnection(ds))`?**  
Because Java calls `c.close()` directly on block exit, which can close a connection Spring still needs. Use `try/finally` + `releaseConnection`.

**4. If `releaseConnection` is called before the service finishes, does the transaction commit early?**  
No. For a bound connection, Spring keeps it until the transaction manager commits/rolls back and cleans up.

**5. What must change in code using `JdbcTemplate` for it to participate in a transaction?**  
Ensure operations use the right `DataSource` and transaction manager, and that the transaction boundary is actually active. `JdbcTemplate` uses Spring's connection-acquisition mechanism automatically.

**6. Does `isConnectionTransactional` returning `true` guarantee all SQL statements in the system roll back together?**  
No. It only reflects the binding of a specific connection in the current context/source; SQL on other connections or sources may belong to different transactions.

**7. When is `TransactionAwareDataSourceProxy` useful?**  
When legacy JDBC code that only knows `DataSource.getConnection` and `Connection.close` needs to participate in Spring transactions and is hard to modify. For new code, prefer proper abstractions.

**8. What test proves transaction participation?**  
Write two changes through two different JDBC access paths under one transaction, intentionally throw a runtime exception, and then read the database to verify both changes rolled back.

## 15. Official References

- [Spring Framework: Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html) – `DataSourceUtils`, transaction-aware proxies, transaction managers, and `JdbcTemplate`.
- [Spring Framework: Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html) – mechanism for binding resources to transactions.
- [DataSourceUtils Javadoc (Spring 6.1.14)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html) – contracts for `getConnection`, `releaseConnection`, `isConnectionTransactional`, and timeout.
- [Spring Framework: Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html) – how to use `TransactionTemplate`.

**Takeaway:** `DataSourceUtils` enables JDBC code to use the connection aligned with a Spring-managed transaction and release it at the right time. A successful transaction still requires business boundaries, the right transaction manager, the same `DataSource`, and an appropriate commit/rollback policy.
