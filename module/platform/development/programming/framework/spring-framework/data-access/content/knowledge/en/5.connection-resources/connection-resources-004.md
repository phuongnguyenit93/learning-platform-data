# Why Calling DataSource.getConnection() Directly Can Bypass the Transaction-Bound Connection

## 1. The Problem to Understand

Marking a service method with `@Transactional` does not mean **every Connection created inside that method** automatically participates in the same transaction. With Spring JDBC, the transaction manager binds a Connection to the current execution thread's transaction context. Components aware of this mechanism—such as `JdbcTemplate` or `DataSourceUtils.getConnection(dataSource)`—reuse the bound Connection. Conversely, calling `dataSource.getConnection()` directly on a **raw DataSource without a transaction-aware proxy** may request a different Connection from the pool, causing SQL on that Connection to run outside the Spring-managed transaction.

For example: inside `@Transactional`, `JdbcTemplate` writes record A; the developer opens a Connection via `HikariDataSource.getConnection()` and writes record B; then the service throws an exception. Spring rolls back record A, yet record B may persist if the directly acquired Connection has `autoCommit=true`. This bug splits what was intended to be an atomic operation into two independent transactions.

**Goal:** identify the root cause accurately, understand how Spring selects and holds a Connection, distinguish safe methods from calls that can bypass, observe this with a runnable program, and know how to fix it while managing resources properly.

> Important scope: The conclusion "direct calls will bypass" holds for a standard raw DataSource such as `HikariDataSource` used in the example. **It is not strictly true for every DataSource implementation**: if the caller receives a `TransactionAwareDataSourceProxy`, that proxy itself makes `getConnection()` return a Connection aware of Spring's transaction. The recommended approach for Spring JDBC application code remains `JdbcTemplate` or `DataSourceUtils`.

## 2. Two Conceptual Layers: Logical Transaction and Actual Connection

A **logical transaction** is the business boundary Spring marks when a call passes through the `@Transactional` interceptor. An **actual Connection** is the JDBC resource provided by a `DataSource` to execute SQL statements. Every SQL statement intended to commit/roll back together must genuinely participate in the exact same transactional resource.

When using a JDBC transaction manager (`DataSourceTransactionManager` or `JdbcTransactionManager`), the typical flow is:

1. The caller invokes a service method through a Spring proxy, and the interceptor starts the transaction.
2. The transaction manager obtains a Connection from the matching DataSource, configures the transaction (e.g., setting `autoCommit=false` when needed), and binds a `ConnectionHolder` to the thread's resource context.
3. `JdbcTemplate` calls `DataSourceUtils.getConnection(dataSource)`. This utility checks for a Connection already bound to that same DataSource and reuses it.
4. SQL statements execute through the managed Connection; when the service finishes, the transaction manager commits or rolls back.
5. Spring unbinds the resource, restores necessary JDBC state, and returns the Connection to the pool.

Spring stores transactional resources in `TransactionSynchronizationManager`, typically relying on `ThreadLocal` in the synchronous JDBC transaction model. This is why a transaction is normally bound to the current execution thread; spawning a new thread or switching to `@Async` does not automatically carry over the old JDBC transaction.

Visualized:

~~~text
Request-handling thread
│
├── Spring @Transactional proxy
│    └── Transaction manager
│         └── ConnectionHolder bound to primary DataSource
│              └── Connection #A (Spring transaction)
│
├── JdbcTemplate
│    └── DataSourceUtils.getConnection(primary DataSource)
│         └── finds ConnectionHolder → Connection #A
│
└── primary DataSource.getConnection() [if calling pool directly]
     └── pool hands out Connection #B (independent of Connection #A)
~~~

Because both `Connection #A` and `Connection #B` may connect to the same database, they can observe **different** data depending on the isolation level. They can also commit/roll back **independently**.

## 3. Why Does a Direct Call Bypass the Spring-Bound Resource?

The standard JDBC DataSource defines `getConnection()` as the way to **request** a Connection. It does not mandate querying Spring's ThreadLocal or looking up a current ConnectionHolder. For instance, a `HikariDataSource` borrows a connection from the pool; if Connection #A is currently held by the transaction manager, a fresh call can receive Connection #B.

Inside the same logical transaction:

~~~java
@Transactional
public void saveTwoEvents() throws SQLException {
    jdbcTemplate.update(
            "INSERT INTO events(id, description) VALUES (?, ?)",
            1, "through Spring");

    try (Connection raw = dataSource.getConnection()) {
        try (PreparedStatement ps = raw.prepareStatement(
                "INSERT INTO events(id, description) VALUES (?, ?)")) {
            ps.setInt(1, 2);
            ps.setString(2, "direct connection");
            ps.executeUpdate();
        }
    }

    throw new IllegalStateException("Force rollback");
}
~~~

This is **illustrative code inside a service with fields `JdbcTemplate jdbcTemplate` and `DataSource dataSource` declared**, not a standalone Java class. The issue lies in `dataSource.getConnection()`: if `dataSource` is a raw pool, the second INSERT may run on a separate Connection outside the first INSERT's transaction. Under the default `autoCommit=true` on a fresh Connection, the second INSERT has already committed before Spring rolls back the first transaction.

A common point of confusion: the transaction manager **also calls `DataSource.getConnection()` when starting the transaction**, but then **it binds the acquired Connection** so `DataSourceUtils` and templates reuse it. Application code calling `getConnection()` directly one more time does not automatically read that binding.

### What `@Transactional` guarantees — and what it does not

In a typical Spring setup, `@Transactional` works through an interceptor/transaction manager to manage **resources registered to participate** in the transaction. It does not automatically alter arbitrary `Connection` objects opened directly by application code; nor does it turn JDBC SQL executed over an independent Connection into the same commit/rollback unit. Checking `TransactionSynchronizationManager.isActualTransactionActive()` alone is **not enough** to conclude whether SQL on the Connection you are using participates in the transaction.

Even if the direct Connection has `autoCommit=false`, the problem remains: it may simply be a separate JDBC transaction needing its own `commit()`/`rollback()`. The autoCommit flag is not proof of Spring transaction membership.

## 4. Distinguishing Three Ways to Acquire a Connection

| Call | Participates in Transaction-Bound Connection? | Usage |
| --- | --- | --- |
| `jdbcTemplate.query(...)`, `jdbcTemplate.update(...)` | Yes, if using Spring's matching DataSource/transaction manager | Preferred for JDBC data access; Spring handles acquiring/releasing resources and translating exceptions. |
| `DataSourceUtils.getConnection(dataSource)` | Yes, when the same DataSource is bound by the transaction manager and appropriate synchronization is active | When manual JDBC is required; always call `DataSourceUtils.releaseConnection(...)` in finally. |
| `dataSource.getConnection()` on a raw pool | May create a **different** Connection and bypass | Do not mix with `@Transactional` JDBC when a single transaction is intended. |
| `getConnection()` on `TransactionAwareDataSourceProxy` | Proxy supports participating in Spring transactions | Intended for legacy code/libraries that only know DataSource; understand proxy and transaction manager configuration precisely. |

**Essential condition:** The DataSource in `JdbcTemplate`, `DataSourceUtils`, and the transaction manager must correspond to the exact same resource. Using two different pools/datasources, even pointing at the same database URL, does not mean the two share one transaction. Multi-database systems require explicit transaction manager selection; local JDBC transactions do not automatically coordinate commit/rollback across independent databases.

## 5. Runnable Example: One INSERT Rolls Back, One INSERT Remains

The following Spring Boot application is designed to **intentionally reproduce the bug**. It uses Java 21, Spring JDBC, the starter's default HikariCP, and an in-memory H2 database. The pool is configured with at least two Connections, default `READ_COMMITTED` isolation, and direct Connections with autoCommit enabled. The program creates no HTTP endpoints.

### 5.1. Creating the project structure

~~~text
spring-tx-connection-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/tx/
    │   ├── TxConnectionApplication.java
    │   └── TxProbeService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'spring-tx-connection-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:tx_connection_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.auto-commit=true
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE journal (
    id INT PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);
~~~

H2 initializes a fresh table in each run. Inside a Spring JDBC transaction, the transaction manager may switch the managed Connection's state to `autoCommit=false`; the pool's `auto-commit=true` setting describes the default state of a **newly borrowed direct Connection** in the example.

### 5.2. Service containing the intentional bypass

File `src/main/java/example/tx/TxProbeService.java`:

~~~java
package example.tx;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TxProbeService {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;

    public TxProbeService(JdbcTemplate jdbc, DataSource dataSource) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
    }

    @Transactional(rollbackFor = SQLException.class)
    public void demonstrate() throws SQLException {
        jdbc.update(
                "INSERT INTO journal(id, description) VALUES (?, ?)",
                1, "spring-managed");

        int inSpringTransaction = jdbc.queryForObject(
                "SELECT COUNT(*) FROM journal WHERE id = 1",
                Integer.class);
        System.out.println("Spring JDBC sees id=1: "
                + inSpringTransaction);

        // Note: DataSource here is the raw pool, not
        // TransactionAwareDataSourceProxy.
        try (Connection raw = dataSource.getConnection()) {
            System.out.println("Direct Connection autoCommit: "
                    + raw.getAutoCommit());

            try (Statement statement = raw.createStatement();
                 ResultSet rs = statement.executeQuery(
                         "SELECT COUNT(*) FROM journal WHERE id = 1")) {
                rs.next();
                System.out.println("Direct Connection sees id=1: "
                        + rs.getInt(1));
            }

            try (PreparedStatement insert = raw.prepareStatement(
                    "INSERT INTO journal(id, description) VALUES (?, ?)")) {
                insert.setInt(1, 2);
                insert.setString(2, "direct-and-committed");
                insert.executeUpdate();
            }
        }

        throw new IllegalStateException("Intentional rollback");
    }
}
~~~

Because the service uses `@Transactional(rollbackFor = SQLException.class)`, both the unchecked exception thrown at the end and any `SQLException` raised during direct JDBC operations will trigger a rollback **for the Spring-managed transaction**. Declaring `rollbackFor` for checked SQLException avoids confusion with the default rule that only rolls back on RuntimeException/Error.

Even so, rolling back Spring's Connection cannot undo an INSERT already committed by another Connection. In this program, `JdbcTemplate` uses Connection #A, while `dataSource.getConnection()` returns Connection #B.

### 5.3. Runner catching the exception and inspecting the database

File `src/main/java/example/tx/TxConnectionApplication.java`:

~~~java
package example.tx;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TxConnectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxConnectionApplication.class, args);
    }

    @Bean
    CommandLineRunner verify(TxProbeService service, JdbcTemplate jdbc) {
        return args -> {
            try {
                service.demonstrate();
            } catch (IllegalStateException expected) {
                System.out.println("Spring rolled back the transaction");
            }

            int remainingSpring = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM journal WHERE id = 1",
                    Integer.class);
            int remainingDirect = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM journal WHERE id = 2",
                    Integer.class);

            System.out.println("After rollback, id=1: " + remainingSpring);
            System.out.println("After rollback, id=2: " + remainingDirect);
        };
    }
}
~~~

Using JDK 21 with a Gradle version supporting Java 21 (such as Gradle 8.5), run from the project directory:

~~~bash
gradle bootRun
~~~

Lines printed by the program with H2/pool configured as above:

~~~text
Spring JDBC sees id=1: 1
Direct Connection autoCommit: true
Direct Connection sees id=1: 0
Spring rolled back the transaction
After rollback, id=1: 0
After rollback, id=2: 1
~~~

**Line-by-line explanation:**

- `Spring JDBC sees id=1: 1`: the query through `JdbcTemplate` uses Connection #A; that same transaction inserted id=1, so it sees its own uncommitted change.
- `Direct Connection autoCommit: true`: Connection #B has the Hikari pool's default mode in the example.
- `Direct Connection sees id=1: 0`: Connection #B does not see #A's uncommitted INSERT under `READ_COMMITTED`.
- After #B inserts id=2, autoCommit commits that INSERT.
- The service throws an unchecked exception; Spring rolls back Connection #A. Record id=1 disappears, while id=2 remains because it committed independently.

This is a **demo intentionally violating business requirements** to observe the bug. Never open a direct Connection like this for operations that must be atomic. Observed values may vary with a different isolation level, pool, driver, or transaction-aware wrapper. The reliable conclusion is that **two access paths can end up using two different Connections/transactions**, breaking the assumption that one rollback will undo everything.

## 6. Preferred Fix: Use JdbcTemplate for All Work

In practice, the service should only call repositories or JdbcTemplate using the right DataSource. Example fixing the method above (using fields and beans from the same project):

~~~java
@Transactional
public void demonstrateCorrectly() {
    jdbc.update(
            "INSERT INTO journal(id, description) VALUES (?, ?)",
            11, "first");
    jdbc.update(
            "INSERT INTO journal(id, description) VALUES (?, ?)",
            12, "second");

    throw new IllegalStateException("Rollback both INSERTs");
}
~~~

If the caller invokes `demonstrateCorrectly()` through a Spring proxy and the database is in an appropriate state, both INSERTs run on the transaction-bound Connection. When RuntimeException escapes, both id=11 and id=12 are rolled back.

`JdbcTemplate` also handles `PreparedStatement`, `ResultSet`, cleanup, and translating `SQLException` into Spring's `DataAccessException` hierarchy. Therefore, avoid manual JDBC operations unless there is a special need.

**Placing the transaction on the service** is the simplest way to guarantee atomicity across multiple repository calls. Having `@Transactional` on the service alone will not rescue a bypass if a repository opens a raw Connection on its own.

## 7. When a Connection Is Truly Needed: DataSourceUtils

If you need a JDBC API not directly covered by the template, use `DataSourceUtils.getConnection(dataSource)` and `DataSourceUtils.releaseConnection(connection, dataSource)`. These two calls coordinate with the Spring transaction resource bound to the thread. Inside an active transaction, `releaseConnection` does not prematurely close a Connection owned by the transaction manager; Spring holds it until the transaction finishes. Outside a transaction, the utility returns the Connection when no longer needed.

Example of a method placed in a Spring service/repository with a `DataSource dataSource` field and invoked via a bean proxy:

~~~java
@Transactional(readOnly = true)
public int countUsingBoundConnection() {
    Connection connection = DataSourceUtils.getConnection(dataSource);
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT COUNT(*) FROM journal");
         ResultSet rs = statement.executeQuery()) {

        if (!rs.next()) {
            throw new IllegalStateException("COUNT returned empty");
        }
        return rs.getInt(1);
    } catch (SQLException ex) {
        throw new IllegalStateException("Cannot query journal", ex);
    } finally {
        DataSourceUtils.releaseConnection(connection, dataSource);
    }
}
~~~

Required imports for this illustrative method: `java.sql.Connection`, `java.sql.PreparedStatement`, `java.sql.ResultSet`, `java.sql.SQLException`, `org.springframework.jdbc.datasource.DataSourceUtils`, `org.springframework.transaction.annotation.Transactional`; the class holds `javax.sql.DataSource`.

Important notes:

1. **Do not** wrap a Connection obtained from `DataSourceUtils.getConnection` in `try (Connection connection = ...)` to close it directly. Close Statement/ResultSet with try-with-resources, but release the Connection via `DataSourceUtils.releaseConnection` in `finally` so Spring decides whether it should actually be closed yet.
2. Do not manually call `commit()`, `rollback()`, `setAutoCommit(...)`, or change isolation on a Connection controlled by the transaction manager when the goal is letting Spring manage the transaction.
3. `getConnection()` and `releaseConnection()` must receive **the same DataSource matching the transaction manager**; do not mix an incompatible wrapper or two pools.
4. `DataSourceUtils` solves acquiring/releasing a transaction-bound Connection. It does not exempt you from managing Statement, ResultSet, or other database resources.
5. If a `SQLException` occurs in manual code, translate it to `DataAccessException` via the appropriate Spring mechanism when a consistent API is needed; in the short snippet above we wrapped it into `IllegalStateException` to highlight the lifecycle, whereas Spring JDBC normally performs finer-grained error translation.

In most cases, `JdbcTemplate.execute(ConnectionCallback<T>)` is even cleaner than manual get/release:

~~~java
public int countWithJdbcTemplateCallback() {
    return jdbc.execute(connection -> {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT COUNT(*) FROM journal");
             ResultSet rs = statement.executeQuery()) {
            rs.next();
            return rs.getInt(1);
        }
    });
}
~~~

This method assumes `jdbc` is a `JdbcTemplate` field; it works both inside a service transaction and outside a transaction. `JdbcTemplate` supplies a valid Connection to the callback while managing acquisition, release, and `SQLException` translation. Do not retain the Connection obtained inside the callback for use after the callback returns.

## 8. Important Exception: TransactionAwareDataSourceProxy

Spring provides `TransactionAwareDataSourceProxy` to adapt legacy code or external libraries that only know how to call `DataSource.getConnection()`. The proxy wraps a target DataSource; when a caller invokes `getConnection()` on **the proxy**, it supplies a Connection wrapper capable of participating in the target DataSource's Spring transaction (if any) and handling `close` properly.

~~~java
DataSource transactionAware =
        new TransactionAwareDataSourceProxy(targetDataSource);

try (Connection connection = transactionAware.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT COUNT(*) FROM journal");
     ResultSet rs = statement.executeQuery()) {
    rs.next();
    System.out.println(rs.getInt(1));
}
~~~

This is an **illustrative snippet requiring `targetDataSource` and JDBC + `TransactionAwareDataSourceProxy` imports**, not a standalone Java file. To work properly, the transaction manager must manage the corresponding **target DataSource**. Do not arbitrarily instantiate a new proxy in every method and assume it solves multi-DataSource setups.

`TransactionAwareDataSourceProxy` is primarily intended for integrating code unaware of Spring transactions. For code you control, prefer `JdbcTemplate` or `DataSourceUtils` to keep transaction participation and resource ownership explicit. When layering multiple DataSource proxies (`LazyConnectionDataSourceProxy`, routing datasource, transaction-aware proxy), verify the target, wrapper ordering, and the actual DataSource managed by the transaction manager. A wrapper can change the answer to "does this `getConnection()` bypass?"

## 9. Do Not Confuse With Cases That Intentionally Use a Different Connection

### 9.1. Propagation.REQUIRES_NEW

A new transaction with `Propagation.REQUIRES_NEW` may require an independent Connection, yet **Spring still manages that new transaction**. The outer transaction is suspended, the new transaction starts/commits/rolls back per Spring rules, and then the outer transaction resumes. This differs fundamentally from borrowing a raw Connection from the pool without a clear transaction boundary.

Using REQUIRES_NEW requires considering pool size: when many threads hold an outer transaction's Connection and concurrently request a Connection for a new transaction, a small pool can exhaust and wait until timeout. Choose this propagation only for business requirements, never to mask a bypass.

### 9.2. Multiple transaction managers or multiple DataSources

In an application with `ordersDataSource` and `auditDataSource`, `@Transactional` selecting one transaction manager may control only one DataSource. A `JdbcTemplate` pointing to another DataSource will not automatically join the first transaction. Separate transaction managers and an appropriate data consistency strategy may be needed.

Even two DataSources connecting to the same database do not guarantee they share the same Connection. When inspecting, check the `DataSource` bean attached to the transaction manager, the bean injected into `JdbcTemplate`, and any intermediate proxy wrappers.

### 9.3. Self-invocation and thread switching

In a standard Spring proxy configuration, calling a `@Transactional` method **directly from another method of the same object** (self-invocation) normally bypasses the proxy; the transaction may never have started. `TransactionSynchronizationManager.isActualTransactionActive()` may return false in that case. Likewise, Spring's synchronous ThreadLocal-based transaction does not automatically propagate across `new Thread(...)` or `@Async`; separate transaction boundaries must be designed for asynchronous work.

This section only addresses synchronous Spring JDBC transactions. Spring reactive/R2DBC uses a different context and resource management model; do not mechanically apply ThreadLocal/JDBC Connection rules to Reactive Streams.

## 10. How to Diagnose a Suspected Bypass

If a SQL operation "does not roll back even though the service has `@Transactional`", investigate in order:

1. **Confirm a transaction is actually active** at the repository call site: `TransactionSynchronizationManager.isActualTransactionActive()` aids diagnosis, though it is not enough to prove the Connection in use participates in the transaction.
2. **Locate every direct `getConnection()` call** and identify whether the target is a raw pool, `TransactionAwareDataSourceProxy`, or another wrapper. Check which DataSource beans `JdbcTemplate` and the transaction manager use.
3. **Check how the Connection is acquired and released**: `JdbcTemplate`/`DataSourceUtils` or `DataSource.getConnection()`; are there manual `close()`, `commit()`, or `setAutoCommit()` calls?
4. **Prove with post-rollback data** in an integration test against the real database: write record A via Spring template and B via the suspected path, intentionally throw an unchecked exception, and read both back from a fresh connection.
5. **Check the environment**: does the pool have enough Connections to test, isolation level, autoCommit, proxies, transaction manager, and nested transactions. If pool size = 1 while a transaction holds Connection #A, calling `getConnection()` directly may block/time out instead of handing out #B.
6. **Check thread boundaries**: does the operation run synchronously inside the transaction or did it switch to another thread/task?

You can use `DataSourceUtils.isConnectionTransactional(connection, dataSource)` to check whether a Connection **is recognized as bound to a transaction for the given DataSource and current context** in appropriate diagnostic situations. Results are only trustworthy when passing the right DataSource and checking on the right thread/time; do not rely on a `connection == otherConnection` comparison to draw conclusions, since pools and proxies may return different wrappers around the same resource.

### Minimal scenario tests

| Scenario | Symptom | Lesson |
| --- | --- | --- |
| Both INSERTs use the same JdbcTemplate and transaction manager | RuntimeException rolls back both | Spring manages the same connection/resource. |
| INSERT A via JdbcTemplate, INSERT B via raw pool `getConnection()` autoCommit | A rolls back; B remains | B bypassed the Spring transaction. |
| Query via JDBC template in transaction sees uncommitted data; raw Connection READ_COMMITTED does not | Two queries see different views | Two independent Connections/transactions. |
| Raw Connection uses TransactionAwareDataSourceProxy with matching target | Can participate in the current transaction | Distinguish proxies from raw pools. |
| Pool has one Connection held by an active transaction | Second direct call may wait or time out | Bypassing can also add pool pressure/hangs. |
| Service self-invokes `@Transactional` in the same class | Transaction may not be active | Verify proxy behavior before analyzing Connection. |
| Multiple DataSources with wrong manager selected | Some SQL falls outside expected boundary | Ensure configuration uses the matching resource. |

## 11. Thinking Traps to Avoid

- **"Having the annotation puts all SQL in the transaction."** The annotation marks the start/end of a Spring transaction; JDBC calls must use a properly enlisted/bound Connection.
- **"Two Connections with the same JDBC URL form one transaction."** A URL only identifies the database address; a JDBC transaction is tied to a specific Connection/session.
- **"Closing a Connection automatically rolls back with the outer transaction."** Closing a raw Connection back to the pool does not make already-autoCommitted SQL roll back with another Spring transaction.
- **"Wrapping every Connection in `try-with-resources` is always right."** Right for raw Connections owned by your code; for Connections from `DataSourceUtils`, use `releaseConnection` so you do not close a resource still managed by Spring.
- **"`isActualTransactionActive()` returning true proves the current Connection shares the transaction."** That is a thread-context flag, not proof of membership for an arbitrary Connection.
- **"Switch to REQUIRES_NEW so everything rolls back together."** REQUIRES_NEW is an independent Spring-managed transaction; it normally commits/rolls back independently of the outer transaction and does not satisfy shared atomicity.
- **"Even if an exception was caught, the transaction will definitely roll back."** Spring typically decides rollback when an exception crosses the interceptor boundary per rollback rules; if you catch and swallow an error, you must actively trigger rollback or let an appropriate exception escape.
- **"Proxies configured anywhere behave identically."** Pool DataSources, transaction-aware proxies, lazy proxies, and routing proxies have different semantics. Misconfiguring the target can prevent Spring from recognizing the bound Connection.

## 12. Self-Check Questions

1. When a transaction already holds Connection #A, why can a `HikariDataSource.getConnection()` call inside the same method return #B?
2. What mechanism does `JdbcTemplate` use to find the Connection bound to the thread by the transaction manager?
3. For record A just inserted in an uncommitted transaction, why might a SELECT on Connection #B under READ_COMMITTED isolation not see A yet?
4. Why does `DataSourceUtils.releaseConnection` differ from calling `Connection.close()` directly?
5. When does `TransactionAwareDataSourceProxy` make `getConnection()` behave differently from a raw pool?
6. Why can `@Transactional` and two DataSources pointing to the same database still produce two independent transactions?
7. To prove a DAO truly runs inside the same transaction, what must you check beyond the `isActualTransactionActive()` flag?
8. If `@Async` was just added to a database task, which assumption about the transaction context must be re-examined?

**Takeaway:** In Spring JDBC, the transaction manager manages **the Connection bound to the transaction resource/thread**. `JdbcTemplate` and `DataSourceUtils` are built to use that Connection. Calling `getConnection()` directly on a raw pool DataSource can yield a different Connection, leading to independent commits/rollbacks. To guarantee consistency, keep SQL operations of the same business unit on the right Spring transaction infrastructure and verify actual DataSource/proxy configuration.

### References

- Spring Framework — JDBC and Connection management: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Javadoc — DataSourceUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Javadoc — TransactionAwareDataSourceProxy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html
- Spring Javadoc — DataSourceTransactionManager: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
