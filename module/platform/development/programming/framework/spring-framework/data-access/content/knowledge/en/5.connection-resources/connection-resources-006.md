# LazyConnectionDataSourceProxy and When Physical Connections Are Acquired

In Spring Framework, an application can start a transaction via `@Transactional` without **needing to run SQL yet**. If every transaction immediately borrows a real JDBC Connection, branches that only check a cache, return existing data, or exit early can still occupy a connection in the pool. **`LazyConnectionDataSourceProxy`** lets you defer borrowing a Connection from the target DataSource until code actually needs to create a JDBC Statement.

This article belongs to the **Connections and Resources** group of the **Spring Framework - data-access** module. The focus is distinguishing a logical Connection from a real Connection, understanding the exact **physical connection acquisition point**, how Spring transactions and JdbcTemplate coordinate with the proxy, configuration across Spring Boot versions, practical measurement, and avoiding common misconceptions.

## 1. Distinguishing Logical Connections from Physical Connections

**Logical Connection / connection handle** is the `java.sql.Connection` object returned by `LazyConnectionDataSourceProxy.getConnection()`. This object is a proxy: it records certain state, accepts JDBC calls, and only reaches for the underlying connection when necessary.

**Target/physical Connection** is the Connection provided by the target DataSource, usually a connection managed by HikariCP. Saying "borrow a physical connection from the pool" **does not necessarily mean opening a new TCP socket**: HikariCP may reissue an already open, idle connection.

~~~text
Spring service / JdbcTemplate / transaction manager
                        |
                        v
             LazyConnectionDataSourceProxy
                        |
               getConnection()
                        |
                        v
              Logical Connection
                        |
            Is a JDBC Statement created?
                  /          \
                No           Yes
                 |             |
                 v             v
       No need to borrow    targetDataSource.getConnection()
       real connection yet         |
                                   v
                              HikariCP pool
                                   |
                                   v
                               Database
~~~

With HikariCP, **Active** reflects connections currently borrowed; **Idle** is connections sitting free in the pool, and **Pending** is calls waiting to borrow. A logical Connection that has not accessed the target **does not automatically increment Active**. Once the proxy must borrow a target connection, the pool still enforces `maximumPoolSize`, `connectionTimeout`, and its own limits.

**Do not confuse the lazy proxy with a pool:** `LazyConnectionDataSourceProxy` only coordinates when the target DataSource is called; it does not create, reuse, limit, or health-check physical connections in place of HikariCP.

## 2. The Key Milestone: Statement Creation Before SQL Execution

According to Spring's Javadoc, `LazyConnectionDataSourceProxy` defers acquiring a real JDBC Connection **until the first JDBC Statement is created**. Common triggering operations include:

- `Connection.createStatement()`
- `Connection.prepareStatement(sql)`
- `Connection.prepareCall(sql)`

The key point is **Statement creation**, without waiting for `executeQuery()`, `executeUpdate()`, or `execute()`. An application can borrow a real connection and yet run no SQL because it created a PreparedStatement and skipped executing it.

| Action | DataSource is HikariCP Directly | DataSource is LazyConnectionDataSourceProxy |
| --- | --- | --- |
| `dataSource.getConnection()` | Borrows from pool immediately | Returns logical handle, usually has not borrowed yet |
| `connection.setAutoCommit(false)` | Sets on borrowed connection | Can be recorded and applied when target is acquired |
| `connection.setReadOnly(true)` | Sets on borrowed connection | Can be recorded and applied later |
| `connection.setTransactionIsolation(...)` | Sets on borrowed connection | Can be recorded and applied later |
| `connection.prepareStatement(sql)` | Uses existing connection | **Borrows target connection if not yet borrowed** |
| `statement.executeQuery()` | Executes on existing connection | Executes on the connection acquired when statement was created |
| `connection.close()` before any Statement is created | Returns borrowed connection | Closes logical handle, possibly never having borrowed target |
| `commit()/rollback()` before any Statement is created | Invoked on real connection | Proxy may skip since no real JDBC transaction exists |

This is the standard rule in Spring JDBC; reading metadata, unwrapping vendor connections, or specialized APIs may force early target access. Do not assume **every** method on `java.sql.Connection` is deferred like `setReadOnly`.

### 2.1. Example of the prepareStatement milestone

~~~java
// This snippet is inside an application that has declared lazyDataSource.
try (Connection connection = lazyDataSource.getConnection()) {
    connection.setReadOnly(true);

    // May borrow the real JDBC Connection RIGHT HERE.
    try (PreparedStatement statement =
            connection.prepareStatement("SELECT 1")) {
        // Not executed yet, yet target DataSource may already have been called.
        try (ResultSet result = statement.executeQuery()) {
            if (result.next()) {
                System.out.println(result.getInt(1));
            }
        }
    }
}
~~~

This Java snippet only illustrates the APIs; `lazyDataSource` must be configured beforehand, and the driver/database must support `SELECT 1`. The query prints `1` on standard H2/PostgreSQL. The most important measurement is not the SQL output, but when `target.getConnection()` gets called.

### 2.2. Why doesn't getConnection() mean physical borrowing?

A logical Connection can exist without a target Connection yet; the proxy retains transaction properties such as auto-commit, isolation, and read-only and applies them once the target is created/acquired. If the handle is closed before creating a Statement, database resources may never have been needed.

**Very important exception regarding first access:** starting in Spring Framework **6.1.2**, `LazyConnectionDataSourceProxy` may acquire a connection on first access to determine default auto-commit and transaction isolation properties. You can call `checkDefaultConnectionProperties()` beforehand to shift this work to the initialization phase. Thus, saying "`getConnection()` never calls the pool" is false; distinguish the **default-property initialization check** from borrowing to execute SQL.

## 3. Timeline When Using @Transactional

A method handled by the Spring transaction interceptor can follow two different branches:

~~~text
00. Interceptor starts @Transactional
01. Transaction manager receives logical Connection from lazy DataSource
02. Records setAutoCommit(false), isolation, and readOnly as needed
03. Business code checks conditions or cached/existing data

BRANCH A: no JDBC access
04A. No Statement created
05A. Spring finishes the logical transaction
06A. Real connection may never be borrowed from the pool

BRANCH B: JDBC access
04B. JdbcTemplate creates the first PreparedStatement
05B. Lazy proxy calls target DataSource -> borrows pool connection
06B. Applies transaction properties, then prepares and executes SQL
07B. Ends transaction: commit/rollback, releases connection
~~~

Three milestones to separate:

1. **Spring transaction starts:** interceptor/transaction manager processes transaction metadata.
2. **Logical Connection obtained:** proxy object may be bound to the transaction without occupying a pool connection yet.
3. **First Statement created:** the real connection is typically acquired; SQL may only run afterward.

Once JDBC has executed inside a transaction, the connection is normally held until the **end of the transaction**, even after `JdbcTemplate` finishes a query. The lazy proxy mainly reduces **the time from transaction start until the first SQL**; it does not automatically return the connection between SQL statements within an open transaction.

### 3.1. Example service with and without database access

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AvailabilityService {
    private final JdbcTemplate jdbc;

    public AvailabilityService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public int check(boolean queryDatabase) {
        if (!queryDatabase) {
            // No JDBC Statement is created on this branch.
            return 0;
        }

        Integer value = jdbc.queryForObject(
            "SELECT 1", Integer.class
        );
        return value == null ? 0 : value;
    }
}
~~~

This is a class in a Spring application that already has `JdbcTemplate`, `DataSource`, a transaction manager, and a driver registered, not a standalone Java `main`. With Spring JDBC consistently wired with the lazy DataSource:

- `check(false)`: Spring can handle the empty transaction without borrowing a target connection, provided no initialization or other intervention occurs.
- `check(true)`: `JdbcTemplate` must create a Statement to run `SELECT 1`, so the proxy borrows a real connection; the result on H2/PostgreSQL is `1`.

`@Transactional` only takes effect when invoked through a **Spring proxy**; calling `check()` from another method on the same instance usually bypasses the interceptor in standard proxy mode. When there is no active transaction, connection return timing differs from inside a transaction: `JdbcTemplate` normally releases resources after each operation.

### 3.2. JdbcTransactionManager and DataSourceTransactionManager

Spring JDBC supports **`DataSourceTransactionManager`** and **`JdbcTransactionManager`**. Both manage transactions for a JDBC DataSource; `JdbcTransactionManager` also translates certain JDBC failures on commit/rollback into appropriate `DataAccessException` subtypes.

For the transaction and DAO to use **the same synchronized connection**, the transaction manager and `JdbcTemplate` must reference **the exact same lazy DataSource bean**. If one side uses the proxy and the other uses the raw pool directly without checking resource identity, JDBC calls may fail to participate in the transaction as expected.

`DataSourceUtils.getConnection(dataSource)` is how Spring synchronizes and reuses the transaction-bound connection. `JdbcTemplate` already uses this mechanism; new code should generally use `JdbcTemplate` instead of manually acquiring/closing connections inside `@Transactional`.

### 3.3. Read-only is not an authorization tool

`@Transactional(readOnly = true)` is Spring metadata. Depending on the transaction manager, JDBC driver, and DBMS, it may only be a **hint**. If `DataSourceTransactionManager.setEnforceReadOnly(true)` is configured, the manager may execute a SQL command such as `SET TRANSACTION READ ONLY` at the start of the transaction. Creating that Statement **forces the proxy to borrow a target connection early**, even if business logic later reads no data.

Do not treat "getting a connection early" in that case as a bug in the lazy proxy: the transaction manager's own configuration requested running SQL right at the start. True data protection requires DB permissions, transaction enforcement, and proper write policies.

## 4. Mechanism for Recording Properties Before Acquiring the Target

`LazyConnectionDataSourceProxy` is the class:

~~~java
org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy
~~~

It extends `DelegatingDataSource` and supplies a Connection proxy. Before acquiring the real connection, the proxy can hold auto-commit, transaction isolation, and read-only settings to apply later. A commit/rollback when no Statement was ever created can be skipped: there is no real JDBC transaction needing commit/rollback on the target.

To return accurate values from `connection.getAutoCommit()` and `connection.getTransactionIsolation()` before a target exists, the proxy needs to know the driver/pool's **default values**. Spring provides:

~~~java
lazy.checkDefaultConnectionProperties();
~~~

This call proactively borrows a target connection to inspect defaults when possible; useful when you want to initialize them before measuring empty transactions. Another option when you have **already verified the real values** of the target:

~~~java
lazy.setDefaultAutoCommit(true);
lazy.setDefaultTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Do not set these values by guesswork just to "ensure laziness": settings that mismatch the target can cause incorrect transaction semantics or read-back values. One initial `getConnection` to establish defaults does not negate the deferral benefit for all subsequent calls.

Do not cast the logical Connection to a vendor connection or Hikari `ProxyConnection`. If you must use a driver-specific API via `unwrap` or `ConnectionProxy.getTargetConnection()`, that operation may trigger immediate target acquisition and affect measurements.

## 5. Configuration in Spring Boot: Version-Specific Notes

### 5.1. Spring Boot 3.x / explicit wiring

Boot 3.x releases do not have Boot 4.1's new lazy JDBC auto-config property. You can configure beans explicitly, for example in an application using **Spring Boot 3.3+, Spring JDBC, HikariCP, PostgreSQL, and Java 17+**.

File `application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/demo
    username: demo
    hikari:
      pool-name: main-pool
      maximum-pool-size: 10
      connection-timeout: 3000
~~~

Provide the password via the **`SPRING_DATASOURCE_PASSWORD`** environment variable or an appropriate secrets mechanism; never put real passwords into lessons. Gradle dependencies in a project using Spring Boot dependency management/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

File `LazyJdbcConfig.java`:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy;
import org.springframework.jdbc.support.JdbcTransactionManager;

@Configuration(proxyBeanMethods = false)
public class LazyJdbcConfig {

    @Bean("physicalDataSource")
    @ConfigurationProperties("spring.datasource.hikari")
    HikariDataSource physicalDataSource(
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("dataSource")
    @Primary
    DataSource dataSource(
            @Qualifier("physicalDataSource") HikariDataSource physical) {
        return new LazyConnectionDataSourceProxy(physical);
    }

    @Bean
    JdbcTransactionManager transactionManager(
            @Qualifier("dataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

This is **configuration inside a Spring Boot project** that already has the JDBC starter, driver, and `DataSourceProperties` registered by Boot; not a standalone Java file compiled with `javac`. The roles:

- `physicalDataSource`: the real `HikariDataSource`, managing pooled connections.
- `dataSource`: `LazyConnectionDataSourceProxy`, marked `@Primary` so DAOs/`JdbcTemplate` prefer it.
- `transactionManager`: uses the same proxy bean as DAOs; empty transactions can avoid borrowing a pool connection.

If the project has multiple DataSources, multiple transaction managers, or JPA, use qualifiers and explicit configuration to ensure the right beans are wired. Do not assume a single-JDBC-resource example fits multi-database systems or distributed transactions.

### 5.2. Spring Boot 4.1+ has the connection-fetch property

Spring Boot **4.1** introduces the ability to wrap an auto-configured pooled DataSource in a lazy proxy via the property:

~~~properties
spring.datasource.connection-fetch=lazy
~~~

Equivalent YAML syntax:

~~~yaml
spring:
  datasource:
    connection-fetch: lazy
~~~

In versions that support it, Spring Boot creates the wrapper automatically via auto-configuration. Do **not** copy this property into Boot 3.3/3.5 and assume it takes effect; always check the documentation for your running version. If auto-wrapping is enabled in Boot 4.1+, avoid wrapping it again with a duplicate lazy proxy.

The outer DataSource bean may be a proxy, so casting directly to `HikariDataSource` will fail. Use proper unwrap/target lookup mechanisms if you need to read physical pool settings or metrics.

## 6. DataSource Proxy Ordering and Transaction Participation

Besides `LazyConnectionDataSourceProxy`, Spring has **`TransactionAwareDataSourceProxy`**. Their roles differ:

| Component | Role |
| --- | --- |
| `HikariDataSource` | Manages real connections and pool limits |
| `LazyConnectionDataSourceProxy` | Defers borrowing a real connection until a Statement is needed |
| `TransactionAwareDataSourceProxy` | Enables raw JDBC code using `DataSource`/`getConnection()` to join Spring-managed transactions |
| `DataSourceUtils`/`JdbcTemplate` | Acquires/returns connections compatibly with Spring transaction synchronization |
| `JdbcTransactionManager` | Opens, commits, rolls back, and releases JDBC transactions |

When **both `LazyConnectionDataSourceProxy` and `TransactionAwareDataSourceProxy`** are needed, Spring documentation requires `TransactionAwareDataSourceProxy` to be **outermost**:

~~~text
Legacy JDBC code
    |
    v
TransactionAwareDataSourceProxy
    |
    v
LazyConnectionDataSourceProxy
    |
    v
HikariDataSource -> Database

JdbcTemplate -> DataSourceUtils -> LazyConnectionDataSourceProxy -> pool
TransactionManager -------------> LazyConnectionDataSourceProxy -> pool
~~~

For new code, prefer `JdbcTemplate` or `DataSourceUtils`; rarely is `TransactionAwareDataSourceProxy` needed. The transaction manager should use the DataSource suitable for transaction synchronization (in this example, the lazy proxy), rather than picking the outermost `TransactionAwareDataSourceProxy` as the managed resource without understanding unwrapping and binding.

Spring synchronizes resources based on DataSource identity/key. Creating multiple separate proxies wrapping the same Hikari pool and giving different keys to DAOs vs. the manager can allocate multiple simultaneous connections and cause code that looks inside a transaction to query on a different connection.

## 7. Lazy Connections Supporting Routing by readOnly/isolation

A system may use a DataSource router to select a write pool (primary) or a read-only pool (replica) based on transaction flags. If the router is invoked **before** Spring binds read-only/isolation metadata, the routing decision can be wrong.

Placing a lazy proxy in front of the router defers pool selection until a Statement is actually created:

~~~text
@Transactional(readOnly = true)
            |
   Spring transaction context
            |
 LazyConnectionDataSourceProxy
            |
 AbstractRoutingDataSource
        /         \
   primary      replica
     pool        pool
~~~

Spring 6.1.2 and later also provide an API to attach a read-only DataSource directly to the lazy proxy:

~~~java
LazyConnectionDataSourceProxy lazy =
        new LazyConnectionDataSourceProxy(primaryDataSource);
lazy.setReadOnlyDataSource(replicaDataSource);
~~~

This snippet is illustrative in an application that has declared `primaryDataSource` and `replicaDataSource`. When a transaction is marked `readOnly` and framework conditions permit, the proxy can select the read-only DataSource when acquiring the target connection. In practice, verify the driver, pool, transaction metadata, and active transaction manager.

Read-only **does not** automatically guarantee every write statement is blocked, and replicas can experience **replication lag**. Read-after-write flows require dedicated consistency design; they may need to read from primary rather than routing arbitrarily to a replica. Also evaluate propagation, nested transactions, self-invocation, and pool selection under real transaction contexts.

## 8. Java 17+ Demo Measuring Target Connection Borrows Accurately

This example uses **Spring JDBC 6.2.14 and H2**, run via Gradle. A `CountingDataSource` wraps `DriverManagerDataSource` (not a Hikari pool) to count how many times `target.getConnection()` is invoked. The example demonstrates **timing**, not pool throughput.

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'example.LazyFetchDemo'
}
~~~

File `src/main/java/example/LazyFetchDemo.java`:

~~~java
package example;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DelegatingDataSource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy;

public class LazyFetchDemo {
    public static void main(String[] args) throws SQLException {
        DataSource raw = new DriverManagerDataSource(
                "jdbc:h2:mem:lazy_demo;DB_CLOSE_DELAY=-1", "sa", ""
        );
        CountingDataSource counting = new CountingDataSource(raw);
        LazyConnectionDataSourceProxy lazy =
                new LazyConnectionDataSourceProxy(counting);

        // Default values known in advance for this H2 test.
        // Do not apply blindly without checking the real target DataSource.
        lazy.setDefaultAutoCommit(true);
        lazy.setDefaultTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED
        );

        try (Connection connection = lazy.getConnection()) {
            System.out.println("after getConnection: "
                    + counting.borrowCount());

            connection.setReadOnly(true);
            System.out.println("after setReadOnly: "
                    + counting.borrowCount());

            try (PreparedStatement statement =
                         connection.prepareStatement("SELECT 1")) {
                System.out.println("after prepareStatement: "
                        + counting.borrowCount());

                try (ResultSet result = statement.executeQuery()) {
                    result.next();
                    System.out.println("SQL value: " + result.getInt(1));
                }
            }
        }

        System.out.println("after close: " + counting.borrowCount());
    }

    static final class CountingDataSource extends DelegatingDataSource {
        private final AtomicInteger count = new AtomicInteger();

        CountingDataSource(DataSource target) {
            super(target);
        }

        @Override
        public Connection getConnection() throws SQLException {
            Connection result = super.getConnection();
            count.incrementAndGet();
            return result;
        }

        int borrowCount() {
            return count.get();
        }
    }
}
~~~

Run when Gradle Wrapper is present in the project:

~~~bash
./gradlew run
~~~

On PowerShell/Windows:

~~~powershell
.\gradlew.bat run
~~~

Ignoring Gradle messages, stdout printed by `main`:

~~~text
after getConnection: 0
after setReadOnly: 0
after prepareStatement: 1
SQL value: 1
after close: 1
~~~

Explanation: returning the logical handle has not incremented `count`; `setReadOnly` is recorded; **`prepareStatement`** requires a target Connection, so `count` increases to 1; executing `SELECT 1` returns 1; `close` does not decrease the **total counted borrows**. If you omit the two default setters or change versions/drivers, the proxy may borrow one connection early to check default auto-commit/isolation; in that case adjust measurements for the initialization pass.

Because the program imports Spring JDBC and the H2 driver, calling `javac/java` directly **without classpath dependencies** will fail with missing packages. Gradle downloads and supplies the necessary jars. For pure Java using only the JDK, `javac/java` can be used directly.

### 8.1. Do not confuse different counter types

- **Borrow count in the demo:** total number of times `target DataSource.getConnection()` was called.
- **HikariCP Active:** number of connections currently borrowed at the observation instant.
- **HikariCP Total:** number of connections currently managed by the pool.
- **New TCP sockets:** can be lower than borrow count because the pool reuses connections.
- **Number of SQL statements:** can be higher than borrow count because multiple Statements share one connection.

You cannot infer "the pool opened more connections" solely from borrow count rising, nor can you prove "no connection was borrowed" merely from the absence of SQL logs.

## 9. Observing Spring Boot Actuator and Verifying Effectiveness

With Actuator/Micrometer properly configured and exposed, HikariCP typically provides metrics such as:

~~~text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.pending
hikaricp.connections.acquire
hikaricp.connections.usage
~~~

Actual metric names depend on version/registry; list the exposed meters. Example in a test environment with metrics enabled:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
~~~

To prove lazy works properly:

1. Verify **which DataSource bean** `JdbcTemplate`/the transaction manager uses.
2. Instrument `target.getConnection()` directly beneath the lazy proxy; separate the default-properties initialization pass.
3. Log timestamps for transaction entry, logical `getConnection`, Statement creation, and SQL execution.
4. Track pool Active/Idle/Pending along with connection acquire/usage times.
5. Account for schema init queries, Flyway/Liquibase, health checks, Hibernate validation, and jobs that may borrow connections outside business logic.
6. Compare identical load before/after enabling lazy; measure latency, throughput, and DB metrics.

`Active=0` at a single instant is **not enough** to claim no queries ran: a connection can be borrowed and returned between two scrapes. Conversely, Active rising during a branch that creates no Statement in your service may be caused by another concurrent component.

### Connection borrowing prediction table

| Scenario | May Borrow Target Connection? |
| --- | --- |
| Open logical connection, `setReadOnly`, close, no Statement | Usually no, after defaults initialization |
| Create `PreparedStatement` and never execute it | **Yes** |
| Run `JdbcTemplate.queryForObject("SELECT 1")` | **Yes** |
| Empty `@Transactional` creating no Statement | Usually no, if no other DB work happens |
| Transaction manager runs `SET TRANSACTION READ ONLY` | **Yes**, because it creates a Statement |
| `ConnectionProxy.getTargetConnection()` or native unwrap | Likely immediately |
| Reading results from JPA/Hibernate cache | Possibly no, depending on provider/transaction handling |
| JDBC already ran SQL in transaction, then calls external HTTP | Connection can stay Active until the end of the transaction |

## 10. Limits of Lazy Benefits and Common Pitfalls

### 10.1. Lazy does not fix slow queries or transactions holding connections too long

The proxy only reduces connection occupancy **before the first JDBC access** and eliminates borrows on empty transactions. Once the first query runs, a long transaction with lock waits, external HTTP calls, or heavy computation still holds the connection until commit/rollback. To reduce Active, you usually need to optimize SQL, shorten transactions, check indexes/locks, and set sensible transaction boundaries.

### 10.2. Does not fix connection leaks automatically

Using raw JDBC without closing connections/statements/result sets properly can still leak. For raw JDBC, use try-with-resources; for Spring, use `JdbcTemplate`/`DataSourceUtils` or the transaction manager. Do not manually close a connection managed by a Spring transaction thinking you need to "return it to the pool early".

### 10.3. Does not guarantee every framework fetches connections lazily

JPA/Hibernate have their own mechanisms for `EntityManager`, flush, caches, and connection handling modes; migrations, health checks, metadata lookups, or driver-specific code can create Statements early. `@Transactional` is not proof that laziness works identically across every stack.

### 10.4. Does not replace pool limits and timeouts

HikariCP's `maximumPoolSize`/`connectionTimeout` still govern physical connection capacity. Once the Statement-creation milestone is reached, the application can wait to borrow and time out normally. Lazy does not increase database capacity, turn JDBC into asynchronous access, or set query timeouts.

### 10.5. Wrong bean identity or proxy order alters transaction behavior

If the manager manages raw Hikari DataSource while a DAO uses a different proxy, Spring may fail to share one thread-bound connection as intended. If `TransactionAwareDataSourceProxy` is used, it must sit outside `LazyConnectionDataSourceProxy`. Verify `@Primary`, `@Qualifier`, bean names, `@Transactional` propagation, and the actual connection via instrumentation.

### 10.6. "Read-only always goes to replica" is a dangerous assumption

Routing configured via `TransactionSynchronizationManager` only works when the read-only flag is already present at pool selection time. Replicas can lag in replication; a read immediately after a write needs consistency design. Write permissions must be enforced at the database and business layer, not solely via `@Transactional(readOnly = true)`.

### Quick diagnostic table

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Empty transaction still borrows a connection | Initializing default auto-commit/isolation; metadata; SQL from transaction manager | Trace the first pass and Statement creation points |
| Creating `PreparedStatement` already increases Hikari Active | **Expected** behavior of the lazy proxy | Distinguish prepare from execute |
| Enabled lazy but Active did not drop | Most requests still hit DB; transactions hold connections long | Empty transaction ratio and usage time |
| `@Transactional` has no effect | Self-invocation, wrong bean, wrong proxy or manager | Spring bean call path and transaction config |
| Read-only routes to the wrong pool | Route chosen before flag takes effect; wrong proxy ordering | Log routing key right at target borrow |
| App reports timeout during `prepareStatement` | Pool could not supply a connection when proxy needed target | Hikari Pending, acquisition latency, DB constraints |
| First `getConnection` count = 1 even with no SQL | Lazy reading default properties | Initialize separately and re-measure; do not set wrong defaults |
| DAO and transaction manager use different connections | Two different DataSource bean/proxy identities | `@Qualifier`/`@Primary` wiring and `DataSourceUtils` |

## 11. Self-Check Exercises

**Exercise 1.** With a lazy proxy whose defaults are already known, the app calls `getConnection()`, `setReadOnly(true)`, `close()` without creating any Statement. Must the pool supply a connection?

**Answer:** No; the logical handle can be created and closed without needing a target connection.

**Exercise 2.** An application calls `prepareStatement("SELECT 1")` and never calls `executeQuery()`. Could it have borrowed a pool connection already?

**Answer:** It may already have borrowed at `prepareStatement()`; "not executing" does not mean "not creating a Statement".

**Exercise 3.** A `@Transactional` service accesses an in-memory cache and returns the result. Can the transaction finish without borrowing a real connection?

**Answer:** Yes, when the lazy proxy is wired properly, no Statement or other operation forces target acquisition, and excluding any default-property initialization pass. That is the main reason to use the proxy.

**Exercise 4.** The transaction manager uses `HikariDataSource` directly, while `JdbcTemplate` uses a `LazyConnectionDataSourceProxy` wrapping that Hikari pool. Should you assume the transaction and DAO definitely share one JDBC connection?

**Answer:** No. Proper resource identity wiring is needed, typically giving both the manager and `JdbcTemplate` **the same lazy DataSource bean**.

**Exercise 5.** Hikari Active stays high after a short query finishes, while the `@Transactional` method also makes a 4-second HTTP call. Does lazy automatically return the connection after the first query?

**Answer:** No. Once borrowed, the connection can stay held until the end of the transaction. Review transaction boundaries and avoid wrapping non-DB work.

**Exercise 6.** Can you enable `spring.datasource.connection-fetch=lazy` on Boot 3.3 and trust the proxy is active?

**Answer:** No. That property was introduced in Boot 4.1; on Boot 3.x use appropriate bean configuration and verify at runtime.

**Exercise 7.** To measure laziness, is calling `ConnectionProxy.getTargetConnection()` right after `getConnection()` appropriate?

**Answer:** Not if the goal is measuring the no-borrow branch: fetching the native target can itself force the proxy to borrow. Instrument the target DataSource instead of forcing real connection acquisition.

**Exercise 8.** How does placing `LazyConnectionDataSourceProxy` in front of `AbstractRoutingDataSource` help?

**Answer:** It defers target pool selection until transaction metadata such as `readOnly`/`isolation` is available, giving the router the right information at Statement creation time; you must still verify consistency, propagation, and actual routing behavior.

## 12. Key Takeaways

- **`getConnection()` on the lazy proxy** returns a logical Connection; **`createStatement()`/`prepareStatement()`/`prepareCall()`** is usually the milestone where a real connection is borrowed.
- **Starting `@Transactional`** differs from **borrowing a pooled connection**; an empty transaction can finish without touching the DB.
- **The first-time probe for default auto-commit/isolation**, metadata/native operations, or transaction-initialization SQL can trigger early connection borrowing.
- **`JdbcTemplate` and the transaction manager** should reference the same lazy DataSource; if `TransactionAwareDataSourceProxy` is used, place it outermost.
- **Read-only routing** can benefit from laziness, but it does not automatically solve authorization or replica consistency.
- **Laziness does not optimize queries** and does not replace Hikari pool/transaction management; once SQL runs, the connection can still be held until the end of the transaction.
- **Spring Boot 4.1+** has `connection-fetch=lazy` when auto-configuring a pooled DataSource; Boot 3.x apps require version-appropriate wiring.

### Official Documentation for Cross-Reference

- Spring Framework 6.1.2, LazyConnectionDataSourceProxy Javadoc: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/jdbc/datasource/LazyConnectionDataSourceProxy.html
- Spring Framework, Controlling Database Connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework, Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Boot 3.5, SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 4.1, SQL Databases / Lazy Connection Proxy: https://docs.spring.io/spring-boot/4.1-SNAPSHOT/reference/data/sql.html
