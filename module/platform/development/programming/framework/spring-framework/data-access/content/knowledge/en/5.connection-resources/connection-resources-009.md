# Limits of try-with-resources When Working with Spring-Managed Resources

In Java, `try-with-resources` is an excellent way to close a `Connection`, `PreparedStatement`, `ResultSet`, stream, or other `AutoCloseable` objects. However, in a Spring application, **not every object with a `close()` method belongs to the calling code to close**. A connection may be held by the transaction manager until commit/rollback; an injected `EntityManager` may be a proxy tied to a persistence context; a `DataSource` may be a bean living for the entire application lifecycle.

Therefore, the key limitation of `try-with-resources` is: **it knows the lexical scope of the `try` block, yet it does not know the owner or lifecycle end time established by Spring**. To clean up resources properly, distinguish resources created/borrowed by your code from resources supplied, shared, and released by Spring per transaction or container.

This article explains Java's mechanism, right and wrong cases in Spring JDBC and JPA, stream and exception handling, and illustrates with a Java 17+ example using Spring JDBC.

## 1. What Does `try-with-resources` Actually Guarantee?

Java syntax:

```java
// Illustrative example; resourceA/resourceB implement AutoCloseable.
try (Resource resourceA = openA();
     Resource resourceB = openB()) {
    use(resourceA, resourceB);
}
```

This is illustrative pseudocode, not a standalone runnable Java file; `Resource`, `openA`, `openB`, and `use` stand in for real APIs.

Java guarantees:

1. Closing every resource **successfully initialized** in the header when exiting the `try` block, including via `return`, `break`, or exception.
2. Closing in **reverse order of declaration**: `resourceB.close()` first, `resourceA.close()` second.
3. If the `try` body throws an exception and `close()` also fails, the exception from the `try` body is normally preserved as the primary exception, while the error in `close()` appears in `getSuppressed()`.
4. Calling `close()` according to that Java object's contract; **Java does not understand Spring transactions, connection pools, transaction propagation, commit/rollback boundaries, or container-managed sessions**.

From (4) follow two symmetric risks:

- **Closing too early:** using `try-with-resources` on a resource the transaction manager still needs after the block exits.
- **Closing at the wrong layer:** calling `close()` on an object your code only **borrowed for use** while Spring manages its lifecycle, or closing a proxy that is not equivalent to releasing the underlying resource.

Conversely, omitting `try-with-resources` for resources opened by your code itself (such as an independent `ResultSet` or `InputStream`) can cause leaks. The goal is not to avoid `try-with-resources`, but to **apply it at the right ownership boundary**.

## 2. Three Distinct Scopes: Lexical Scope, Resource Ownership, Transaction Scope

```text
@Transactional method starts
│
├─ Transaction manager acquires/binds JDBC Connection (when needed)
│   │
│   ├─ Repository enters a try-with-resources block
│   │   ├─ creates PreparedStatement
│   │   ├─ executes SQL / reads ResultSet
│   │   └─ closes PreparedStatement/ResultSet  ← right scope
│   │
│   ├─ Another repository continues using the same transaction's connection
│   │
│   └─ commit or rollback decided by transaction manager
│
└─ Spring unbinds/releases Connection back to DataSource/pool
Transactional method finishes
```

In the example above, the `try` block wraps only one statement. A transaction can span **multiple repositories** and outlive the `try` block. Closing the transaction-bound connection at the end of the block can cause subsequent operations or commit to fail.

| Question | Who Answers It? | Meaning |
| --- | --- | --- |
| When will `close()` be called? | `try-with-resources` syntax, at the end of lexical scope. | Simply the closing schedule decided by Java. |
| Which objects does this code have the right to call `close()` on? | API contract and **resource ownership**. | Resources borrowed from the container may need to be released by the container. |
| When does the transaction commit/roll back? | Transaction manager and transaction rules. | Can happen after several `try` blocks have already finished. |
| Does it close a physical connection or return to the pool? | `DataSource`, proxy/pool, and connection state. | `Connection.close()` on a pool handle usually returns the handle, not necessarily dropping the socket. |

There is no "one `try` block equals one transaction" rule. One transaction can contain many `try` blocks; a `try` block may also participate in no Spring transaction at all.

## 3. Quick Decision Table by Resource Type

| Resource Source | Should You Use `try-with-resources` Directly? | Proper Release Method |
| --- | --- | --- |
| `DriverManager.getConnection(...)` called by your code | **Yes**, if your code owns the connection. | `Connection.close()` at end of scope; manual commit/rollback when auto-commit is off. |
| `dataSource.getConnection()` from a pool **outside** a Spring transaction, borrowed by your code | **Usually yes**. | Close handle to return to pool; still finish any manually managed transaction. |
| `DataSourceUtils.getConnection(dataSource)` | **Do not put the connection in the `try` header** when Spring transaction compatibility is needed. | Use `DataSourceUtils.releaseConnection(con, dataSource)` in `finally`. |
| `Connection` passed into `JdbcTemplate.execute(ConnectionCallback)` | **Do not close the connection the callback receives**. | Spring/`JdbcTemplate` is responsible; only close child resources you create yourself when needed. |
| `Connection` from `TransactionAwareDataSourceProxy` | **Can be yes**, because the proxy handles `close()` transaction-aware when configured properly. | Use per proxy contract; transaction manager still manages the target DataSource. |
| `PreparedStatement` / `ResultSet` created by your code | **Yes**, even when using a Spring-managed connection. | Close statement/result set at end of operation, leaving connection to its owner. |
| `EntityManager` injected via `@PersistenceContext` | **Do not use `try-with-resources` to manage lifecycle**. | Spring/container manages persistence context, transactions, and cleanup. |
| `EntityManagerFactory.createEntityManager()` created by your code | **Can be used** with Jakarta Persistence supporting `AutoCloseable`. | The creator of the EntityManager must close it; handle transactions per appropriate configuration. |
| `Stream<T>` returned by `JdbcTemplate.queryForStream(...)` | **Yes, should wrap** around the **stream**. | `Stream.close()` releases cursor/statement; consume before the required transaction ends. |
| `InputStream` obtained via `Resource.getInputStream()` | **Yes** for the opened stream owned by your code. | Close the stream; do not infer you must also close the `Resource` bean. |
| `HikariDataSource` managed by Spring as a bean | **Do not close inside requests/services**. | Spring closes the pool with the application context or bean owner lifecycle. |

This table applies to standard synchronous Spring JDBC/JPA. In reactive R2DBC flows, ownership models attach to publishers and subscribers; a `try-with-resources` wrapping a call returning `Mono`/`Flux` typically exits before I/O is even subscribed/executed.

## 4. First Mistake: Opening a Raw Connection Inside `@Transactional`

Consider the service below. Assume `dataSource` points directly to a normal pool or driver `DataSource`, **not a `TransactionAwareDataSourceProxy`**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WrongPaymentService {
    private final DataSource dataSource;

    public WrongPaymentService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Transactional
    public void pay(long invoiceId) throws SQLException {
        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(
                 "UPDATE invoice SET paid = TRUE WHERE id = ?")) {
            ps.setLong(1, invoiceId);
            ps.executeUpdate();
        }

        // If this operation throws an error, the UPDATE above
        // may already have committed independently when auto-commit = true.
        throw new IllegalStateException("Downstream failure");
    }
}
```

This code **illustrates an incorrect scenario**, needing a Spring app with a `DataSource`, `invoice` table, and transaction management; it is not a standalone program.

The problem is not the `try` syntax. `dataSource.getConnection()` on a raw DataSource can hand out **a new connection separate from the connection bound to the Spring transaction**. If that connection has auto-commit enabled, `UPDATE` can commit immediately, despite `@Transactional` on the service later rolling back the Spring-owned transaction. Calling `close()` only returns that handle to the pool; it does not bring already-committed SQL into another transaction.

Even if the raw connection sets `autoCommit(false)`, it remains a **self-managed, independent** JDBC transaction, not automatically merged into the Spring transaction. When you want Spring to manage business boundaries, keep all related operations on the matching transaction manager/DataSource.

The standard approach is `JdbcTemplate`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void pay(long invoiceId) {
        int changed = jdbc.update(
            "UPDATE invoice SET paid = TRUE WHERE id = ?",
            invoiceId
        );
        if (changed != 1) {
            throw new IllegalStateException("Invoice not found");
        }

        // A RuntimeException in the next step
        // causes the Spring transaction to roll back by default.
        performBusinessChecks();
    }

    private void performBusinessChecks() {
        // Real business logic is implemented here.
    }
}
```

The second snippet is a **Spring integration** example, without a complete schema/database to run standalone. `JdbcTemplate` uses the `DataSourceUtils` mechanism to acquire a connection compatible with the bound transaction. Do not manually close connections or call commit/rollback inside repositories when Spring manages the transaction.

Applicable conditions: an appropriate transaction manager, Spring beans, and active `@Transactional` interception; self-invocation on the same bean in proxy mode typically does not trigger a new interceptor.

## 5. Second Mistake: Closing a Connection Provided by `DataSourceUtils`

Spring provides `DataSourceUtils.getConnection(dataSource)` to participate in JDBC transactions bound to the current thread. When a connection is already bound for the same DataSource, this call returns that connection; when no transaction exists, it can acquire a new connection from the DataSource.

The following code is **dangerous inside a Spring transaction**:

```java
// WRONG when the connection is already bound to a Spring transaction.
try (Connection con = DataSourceUtils.getConnection(dataSource)) {
    doSomething(con);
}
// Java calls con.close() directly, which can close a connection
// the transaction manager still needs to continue / commit.
```

Here, `DataSourceUtils.getConnection` does not turn `Connection.close()` into a transaction-aware operation. When code calls `close()` directly on a bound connection, it can close the physical connection or return the handle to the pool **too early**. The transaction manager still treats that connection as belonging to the transaction, so the next SQL statement or commit can hit a "connection closed"/invalid state error. Exact behavior depends on driver, proxy, and pool.

The right approach is using Spring's matching API pair:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;

public final class SpringJdbcAccess {
    private final DataSource dataSource;

    public SpringJdbcAccess(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int markProcessed(long jobId) {
        Connection con = DataSourceUtils.getConnection(dataSource);
        try (PreparedStatement ps = con.prepareStatement(
                "UPDATE job SET processed = TRUE WHERE id = ?")) {
            ps.setLong(1, jobId);
            return ps.executeUpdate();
        } catch (SQLException ex) {
            throw new IllegalStateException("JDBC write failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(con, dataSource);
        }
    }
}
```

This is a class compilable with Spring JDBC, needing a real DataSource and `job` table to run.

Mechanism to understand:

1. `getConnection` obtains a connection aligned with the current transaction.
2. `PreparedStatement` **is created by the method**, so `try-with-resources` is allowed to close it.
3. `releaseConnection(con, dataSource)` checks whether the connection is bound to an active Spring transaction.
4. If bound to a transaction, Spring avoids closing the connection early; the transaction manager releases it when the transaction ends. If no matching transaction exists, Spring can call close to return the connection to the pool/driver.
5. Calling `releaseConnection` must pass the exact DataSource corresponding to the acquired connection. Do not swap DataSource/proxy objects between the two calls.

Do not call `con.commit()`, `con.rollback()`, or change auto-commit inside a scope owned by the Spring transaction manager. When programmatic transaction control is wanted, use `TransactionTemplate` or Spring's transaction APIs.

## 6. An Intentional Exception: `TransactionAwareDataSourceProxy`

Spring provides `TransactionAwareDataSourceProxy` for **raw JDBC code unaware of `DataSourceUtils`** that still needs to participate in Spring transactions.

```java
// Configuration illustration; targetDataSource is the real DataSource.
DataSource aware = new TransactionAwareDataSourceProxy(targetDataSource);

// Raw JDBC code using "aware":
try (Connection con = aware.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "SELECT name FROM item WHERE id = ?")) {
    ps.setLong(1, itemId);
    try (ResultSet rs = ps.executeQuery()) {
        // Consume results here.
    }
}
```

The snippet above is **integration code**; it requires JDBC/Spring imports, `targetDataSource`, `itemId`, and a real schema. `TransactionAwareDataSourceProxy` returns a connection proxy that handles `close()` and coordinates with `DataSourceUtils`. If the connection is held by Spring for a transaction, calling `close()` on **the proxy** is handled without closing the underlying connection prematurely; outside a transaction, normal release rules apply.

Important constraints:

- The transaction manager must work with the **underlying target DataSource**, not using this awareness proxy as the main coordination source.
- The proxy must be wired and ordered properly with other DataSource proxies; Spring requires `TransactionAwareDataSourceProxy` to be the outermost layer in a proxy/adapter chain.
- Merely having type `DataSource` does not make an object transaction-aware. Do not copy this example directly onto `HikariDataSource`/`DriverManagerDataSource` and expect `close()` to be intercepted.
- If you can modify the code, prefer `JdbcTemplate` or `DataSourceUtils`; the proxy is mainly helpful for legacy JDBC APIs.

This is why we cannot state a mechanical rule like "`Connection.close()` is always wrong with Spring" or "`try-with-resources` is always safe with `Connection`". **What decides it is the contract of the handed object and who owns its lifecycle.**

## 7. `JdbcTemplate` and Callbacks: Framework Closes Connection, Code Closes What It Creates

`JdbcTemplate` already manages acquiring/releasing connections, closing statements/result sets for standard operations, and translating many `SQLException`s into `DataAccessException`. Therefore, business code only needs to invoke template methods:

```java
// Integration example; jdbc is a configured JdbcTemplate.
int updated = jdbc.update(
    "UPDATE job SET processed = TRUE WHERE id = ?",
    jobId
);
```

If lower-level JDBC API access is required, you can use `ConnectionCallback`:

```java
import java.sql.PreparedStatement;
import org.springframework.jdbc.core.ConnectionCallback;

// Illustrative snippet in an app with jdbc and jobId.
Integer updated = jdbc.execute((ConnectionCallback<Integer>) con -> {
    try (PreparedStatement ps = con.prepareStatement(
            "UPDATE job SET processed = TRUE WHERE id = ?")) {
        ps.setLong(1, jobId);
        return ps.executeUpdate();
    }
});
```

Inside the callback, `con` is supplied by `JdbcTemplate` for the work; **do not place `con` in a `try` header and do not close it manually**. Because `PreparedStatement` is created by the callback itself, it should be closed with `try-with-resources`. Once the callback finishes, `JdbcTemplate` handles releasing per the Spring transaction context.

Similarly, when using `RowMapper` or `ResultSetExtractor`, the framework owns closing `ResultSet` and the corresponding statement; callbacks should only read data while being invoked. Never return a live `ResultSet` out of a callback to use after the template has cleaned up resources.

## 8. Spring-Managed `EntityManager` and Persistence Context

With Spring JPA, an injected field:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class ArticleRepository {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void rename(long id, String newTitle) {
        Article article = entityManager.find(Article.class, id);
        if (article == null) {
            throw new IllegalArgumentException("Article not found");
        }
        article.setTitle(newTitle);
    }
}
```

This is an integration snippet needing the `Article` entity and JPA provider/configuration, not a standalone runnable file.

An `EntityManager` via `@PersistenceContext` is typically a **shared proxy** pointing to the EntityManager aligned with the current transaction. Spring manages when the persistence context is created, joins the transaction, flushes, and closes. Do not write:

```java
// WRONG ownership for an injected EntityManager.
try (EntityManager em = entityManager) {
    em.persist(new Article());
}
```

Although `EntityManager` in modern Jakarta Persistence implements `AutoCloseable`, that **does not transfer ownership of the persistence context to the calling method**. With some Spring `@PersistenceContext` proxies, `close()` may even be suppressed; that further demonstrates a `try` block is not the lifecycle coordinator here. With an unwrapped native EntityManager, closing at the wrong time can break subsequent operations.

An EntityManager **created by the application itself** via `entityManagerFactory.createEntityManager()` carries a different responsibility: the creating code must close it when work finishes and manage transactions according to the configured strategy. With Jakarta Persistence 3.1+, EntityManager is `AutoCloseable`, so an application-owned EntityManager can be placed in `try-with-resources`. However, it does not automatically join a Spring transaction merely by being created inside a `@Transactional` method.

Similarly in Hibernate: a `Session` opened manually via `openSession()` must usually be closed per its contract; whereas `getCurrentSession()` is bound to the transaction context and should not be closed like a self-created session. Always check how the resource was obtained before choosing `close()`.

**Further distinction:** JPA's `flush()` may synchronize SQL down to the DB, yet does not mean `commit`. `try-with-resources` does not turn flush into commit and does not guarantee rollback if code closes a persistence context it does not own.

## 9. Streams from Spring: One Place `try-with-resources` Is Truly Needed

Some APIs return a `Stream<T>` **still attached to a cursor/statement**. For example, `JdbcTemplate.queryForStream(...)` returns a stream that must be closed after consumption, because a terminal operation such as `count()` or `toList()` **does not automatically call `Stream.close()`**.

Example using `try-with-resources` properly on the **stream**, without manually closing connections:

```java
import java.util.List;
import java.util.stream.Stream;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskReportService {
    private final JdbcTemplate jdbc;

    public TaskReportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public List<Long> loadIds() {
        try (Stream<Long> ids = jdbc.queryForStream(
                "SELECT id FROM task ORDER BY id",
                (rs, rowNum) -> rs.getLong(1))) {
            return ids.toList();
        }
    }
}
```

This is an integration service needing the `task` table and a matching transaction manager. The stream is **opened, consumed, and closed within the same method/transaction scope**. When the stream closes, Spring can clean up the cursor/statement and release the connection per ownership rules; while the transaction remains active, the connection is not necessarily returned to the pool until the transaction ends.

Counterexample:

```java
// Illustration of what NOT to do for a stream holding a live cursor.
@Transactional(readOnly = true)
public Stream<Long> loadIds() {
    return jdbc.queryForStream(
        "SELECT id FROM task ORDER BY id",
        (rs, rowNum) -> rs.getLong(1));
}
// Caller may consume the stream after the transaction has already ended.
```

If the caller uses the stream after the service returns, the transaction may already be closed; cursors/JDBC resources or lazy loading may no longer be valid. Callers also risk forgetting to close the stream. The common safe approach is to **consume and close the stream inside the transaction**, returning a DTO or materialized list of data. With streams from JPA repositories, transaction limits and cleanup must also be evaluated per provider and query method.

For `InputStream`/`Reader` obtained by calling `Resource.getInputStream()` or file APIs, you can use `try-with-resources` to close the opened stream. Do not also close the `Resource` bean or the entire `ApplicationContext`: bean lifecycles belong to the container.

## 10. `try-with-resources` Does Not Replace Rollback Policies

Consider the following method:

```java
// Illustrative snippet, not a standalone program.
@Transactional
public void importData() throws java.io.IOException {
    jdbc.update("INSERT INTO audit_event(id) VALUES (1)");

    try (java.io.InputStream input = openInput()) {
        consume(input); // May throw IOException.
    }
}
```

`try-with-resources` only guarantees `input.close()` is called. It **does not decide** whether the `INSERT` will roll back. Under Spring's default `@Transactional` configuration, an escaping `RuntimeException`/`Error` normally triggers rollback; a checked exception like `IOException` **does not automatically** trigger rollback unless a rollback rule is configured or the transaction is marked rollback-only.

If failing to read the file must abort the transaction, you can specify:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importData() throws java.io.IOException {
    // Data operations and file reading belong to the same business unit.
}
```

Both snippets in this section are **illustrative**, lacking concrete `openInput`/`consume` to run standalone. The `rollbackFor` setting applies to exceptions escaping the matching interception boundary. If the exception is caught and the method returns normally, Spring may commit unless the transaction was already marked rollback-only for another reason.

In particular, if the `try` body succeeds yet `close()` throws an exception, the rollback decision still depends on the exception type and transaction policy. If both the `try` body and `close()` throw, inspect `Throwable.getSuppressed()` so cleanup causes are not missed.

**Do not use `try-with-resources` to imagine a nested child transaction.** `@Transactional` with `REQUIRED`, `REQUIRES_NEW`, `NESTED`, or `TransactionTemplate` is where joining, splitting, or creating savepoints for transactions is decided per transaction manager capabilities.

## 11. Standalone Runnable Java 17+ Example: Holding Connection for Spring Until Commit

The example below uses **Spring JDBC 6.1.14 and H2 2.2.224**. H2's `JdbcDataSource` is used to keep the project small; it is **not a connection pool**. The goal is verifying a connection can be owned by the Spring transaction manager, `PreparedStatement` is closed in a short scope, and the connection is only released by Spring after the transaction.

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>spring-resource-ownership-demo</artifactId>
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
```

Create `src/main/java/ResourceOwnershipDemo.java`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.transaction.support.TransactionTemplate;

public class ResourceOwnershipDemo {
    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:owner_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
        TransactionTemplate transaction = new TransactionTemplate(manager);

        jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, amount INT NOT NULL)");

        transaction.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO ledger(id, amount) VALUES (?, ?)",
                    1, 100);

            // getConnection joins the active Spring transaction.
            Connection con = DataSourceUtils.getConnection(dataSource);
            try (PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO ledger(id, amount) VALUES (?, ?)")) {
                ps.setInt(1, 2);
                ps.setInt(2, 200);
                ps.executeUpdate();

                System.out.println("Bound to transaction: " +
                        DataSourceUtils.isConnectionTransactional(
                                con, dataSource));
            } catch (SQLException ex) {
                throw new IllegalStateException("JDBC operation failed", ex);
            } finally {
                // Do not call con.close() directly:
                // the transaction manager still needs con to commit.
                DataSourceUtils.releaseConnection(con, dataSource);
            }
        });

        Integer afterCommit = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ledger", Integer.class);
        System.out.println("Rows after commit: " + afterCommit);

        try {
            transaction.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO ledger(id, amount) VALUES (?, ?)",
                        3, 300);
                throw new IllegalStateException("Business failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Rollback triggered");
        }

        Integer afterRollback = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ledger", Integer.class);
        System.out.println("Rows after rollback: " + afterRollback);
    }
}
```

Run with **JDK 17+ and Maven** installed:

```bash
mvn -q compile exec:java -Dexec.mainClass=ResourceOwnershipDemo
```

Lines produced by `System.out.println`:

```text
Bound to transaction: true
Rows after commit: 2
Rollback triggered
Rows after rollback: 2
```

If the build environment/logger prints its own messages, those are separate from the application stdout lines listed above.

**Step-by-step analysis:**

1. `TransactionTemplate` starts a transaction via `DataSourceTransactionManager` and binds the connection to the appropriate execution context.
2. `JdbcTemplate` runs the first `INSERT` using the transaction-participating connection.
3. `DataSourceUtils.getConnection(dataSource)` retrieves the connection managed by the transaction. `isConnectionTransactional` evaluates to `true`.
4. `PreparedStatement` is created in the inner block; `try-with-resources` closes it immediately on completion. `DataSourceUtils.releaseConnection` does not close the transaction-bound connection.
5. The transaction callback finishes normally, and the transaction manager commits; both rows exist together.
6. The second callback inserts a third row and throws `IllegalStateException`. `TransactionTemplate` rolls back, so the row count after rollback remains 2.

What the example proves is **proper ownership when combining manual JDBC with Spring**. It does not prove a pool is automatically present, nor does it mean connections to multiple databases share one transaction.

## 12. Diagnosing Failures from Closing Mistakes or Omitted Closes

When encountering "connection is closed", connection-borrow timeouts, or lazy-loading errors after a method returns, identify **where the resource was created, who owns it, who is responsible for releasing it, and where the transaction boundary lies** before changing timeouts.

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| `Connection is closed` on the second SQL or at commit | Spring-bound connection was closed directly by code calling `close()`. | Find `try (Connection con = DataSourceUtils.getConnection(...))` and replace with `releaseConnection`. |
| SQL committed even though `@Transactional` threw an error | SQL ran on a different connection acquired straight from a raw DataSource with auto-commit on. | Switch to `JdbcTemplate`/`DataSourceUtils`; verify transaction manager and DataSource. |
| `getConnection()` timeout, active never drops | Connection borrowed manually by the app lacks `close()` on an error path. | Use `try-with-resources`/`finally` for connections **owned by your code**. |
| `ResultSet` unusable after callback | Live cursor returned outside the scope closed by `JdbcTemplate`. | Map data into DTOs/lists inside the callback. |
| JDBC stream / lazy JPA errors after method returns | Stream needs cursor or persistence context whose transaction already ended. | Consume and close the stream inside the proper transaction scope. |
| DB transaction does not roll back on IOException/checked exception | `try-with-resources` closed the stream, yet default rollback rules exclude checked exceptions. | Configure `rollbackFor` appropriately and ensure the exception crosses the interceptor. |
| Connection/persistence context closed at the wrong time | Code closed an injected bean, `EntityManager`, or transaction-bound `Session` manually. | Let Spring manage container/transaction lifecycles. |
| Method has `@Transactional` yet connection is not bound | Call bypassed proxy, mismatched transaction manager/DataSource, or wrong thread. | Verify interceptor path, resource binding, and propagation. |
| Cleanup failure masks primary error | `close()` also threw an exception. | Inspect `getSuppressed()` and log error context; never swallow exceptions. |

For Spring JDBC, observe active/idle connection counts in the pool, transaction duration, and database messages. `DataSourceUtils.isConnectionTransactional(con, dataSource)` is useful as a contextual check in diagnostic code, yet should not be used to write business logic depending on a connection's physical identity.

## 13. Decision Checklist Before Writing `try (...)`

1. **Where does this resource come from?** Newly created by code calling a constructor/factory, borrowed from a pool, or injected/bound by Spring?
2. **Who owns the close call?** Does the API documentation say the caller must close, or will the framework release it at the end of a callback/transaction/context?
3. **Will the resource still be used after the try block?** If so, `try-with-resources` may close it too early.
4. **Is a Spring transaction active?** Does raw `DataSource.getConnection()` join the right transaction or create an independent connection?
5. **Are you trying to close a child resource or the parent resource?** Closing a `Statement`/`ResultSet` you created is usually right; closing a transaction-bound `Connection` is usually wrong.
6. **Is there a lazy stream/cursor?** The stream itself needs `close()` and must be consumed before the connection/transaction ends.
7. **How will exceptions affect the transaction?** Distinguish checked/unchecked, suppressed exceptions, catching inside the method, `rollbackFor`, and rollback-only state.
8. **If there is no transaction, will the resource still be released?** `DataSourceUtils.releaseConnection` handles both bound connections and self-borrowed cases outside transactions.

### Key Takeaways

- `try-with-resources` solves **closing `AutoCloseable` objects by lexical scope**; it does not determine resource ownership and does not replace the transaction manager.
- For self-managed JDBC, `try (Connection con = dataSource.getConnection())` is usually right **when your code truly owns the connection**. For connections obtained via `DataSourceUtils` in Spring, use **`DataSourceUtils.releaseConnection`**.
- With `JdbcTemplate`, Spring manages the connection; callbacks may use `try-with-resources` for `PreparedStatement`/`ResultSet` created by the callback itself.
- With `@PersistenceContext EntityManager`, Spring manages the persistence context; do not manually close an injected entity manager even though the API implements `AutoCloseable`.
- With `JdbcTemplate.queryForStream` or streams holding cursors, close the **stream** using `try-with-resources` and consume it within the appropriate transaction scope.
- **Commit/rollback**, **closing a handle**, and **closing a bean/pool** are three distinct responsibilities; performing only one cannot substitute for the others.

### References

- Java 17 — `try-with-resources` and exception suppression: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
- Spring Framework — Controlling JDBC connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring — `DataSourceUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring — `TransactionAwareDataSourceProxy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html
- Spring — rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring — `JdbcTemplate.queryForStream`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Jakarta Persistence — `EntityManager`: https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html
