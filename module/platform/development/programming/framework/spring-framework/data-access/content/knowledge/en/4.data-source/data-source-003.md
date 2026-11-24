# Distinguishing DriverManagerDataSource from a Pooled Connection Source

In Spring Data Access, `DataSource` is the entry point for obtaining JDBC connections. Two objects both implementing `javax.sql.DataSource` can be passed to **the same `JdbcTemplate`**, yet their cost, concurrency capability, and behavior when calling `Connection.close()` differ significantly:

- Spring's `DriverManagerDataSource` **has no connection pool**. Every time `getConnection()` actually needs a new connection, it opens a physical JDBC connection via the driver; closing the connection typically terminates that physical connection.
- A `DataSource` with a **connection pool** (such as HikariCP's `HikariDataSource`) manages a set of reusable physical connections. `getConnection()` borrows a logical connection; `close()` typically returns the connection to the pool for the next caller to use.

A distinction to make right away: **having the same API does not mean having the same usage cost**. And **a pool is not synonymous with a transaction**: managing connection lifecycle, limiting connection count, and controlling transactions are three related but distinct responsibilities.

## 1. DataSource Is a Shared Contract, Not One Kind of Pool

`javax.sql.DataSource` is the standard JDBC interface. The application asks `DataSource.getConnection()` for a `java.sql.Connection`, uses JDBC to run queries, and then releases it with `close()`. The interface does not promise that each call creates a new physical connection, reuses an old connection, or enforces concurrency limits.

In Spring, `JdbcTemplate` takes a `DataSource`; it manages acquiring and releasing `Connection` instances according to Spring's transaction-support mechanism. Consequently, switching the connection source configuration from direct to pooled usually **requires no changes to SQL statements or DAO code**.

```text
            Spring service / DAO
                     |
                     v
                JdbcTemplate
                     |
                     v
             DataSource (JDBC API)
                  /        \
                 /          \
DriverManagerDataSource     HikariDataSource
     no pool                   pooled
         |                       |
   creates new conn      borrows / returns conn
         |                       |
         +----------> Database <-+
```

### 1.1. How Does DriverManagerDataSource Work?

`DriverManagerDataSource` resides in `org.springframework.jdbc.datasource`. Each time application code actually requests a new connection, it uses the JDBC URL, username/password, and driver to open a physical connection. It does not maintain a list of idle connections to lend out later.

Basic lifecycle when **not inside a transaction actively managing the connection**:

1. `getConnection()` → driver establishes a physical session/connection to the DB.
2. Application executes the statement.
3. `close()` → closes the physical connection; the next `getConnection()` call opens a new one.

Creating a physical connection may require socket setup, authentication, TLS, session initialization, and DB-side resource allocation. These steps increase latency and load when many short query tasks run in sequence. You should not infer that every **SQL statement** always creates a new connection: if a Spring transaction is active and code uses `JdbcTemplate`/`DataSourceUtils` properly, operations within the transaction can share a single connection bound to that transaction.

### 1.2. How Does a Pooled DataSource Work?

`HikariDataSource` is a popular pooling implementation. It manages physical connections and hands the application a logical `Connection` (usually a proxy). The pool distinguishes:

- **Idle:** physical connections available to be borrowed.
- **Active / in use:** connections currently held by the application.
- **Pending / waiting:** calls waiting because no connection is available yet.
- **Total:** total physical connections currently managed, comprising active and idle.

Basic lifecycle:

1. `getConnection()` → pool provides an idle connection, or creates an additional one if below the limit and needed.
2. Application executes statements with the borrowed connection.
3. `close()` on the logical connection → pool reclaims it, resets pool-managed state, and returns the physical connection to a reusable state if still valid.
4. Another request can borrow that physical connection again.

The pool may validate, evict, or replace broken/expired connections. Therefore, **not every `close()` guarantees returning that exact physical connection to idle**; however, the usage rule remains that the logical connection must be closed at the right time.

## 2. Comparing by Practical Criteria

| Criterion | `DriverManagerDataSource` | `HikariDataSource` or Another JDBC Pool |
| --- | --- | --- |
| Physical connection creation | Opens a new one whenever a fresh `getConnection()` is needed. | Borrows an available connection; may open more within pool limits. |
| `Connection.close()` | Normally closes the physical connection. | Normally returns the logical connection to the pool; the physical connection can be reused. |
| Cost for many short queries | Repeats connection setup overhead. | Saves overhead through reuse. |
| Connection limit on the DataSource itself | Does not enforce `maximumPoolSize`. | Configurable limit on physical connections per pool. |
| Under high concurrent requests | Each borrow usually tries to open a new connection; DB may reject when exceeding limits. | When no free connections remain and the pool is at limit, requests wait and may time out. |
| Idle connection management | Keeps no idle pool. | Has minimum idle, idle timeout, and max lifetime policies. |
| Operational observability | Few pool metrics; must observe driver/DB. | Can observe active, idle, pending, total; integrates with metrics. |
| Configuration/lifecycle cost | Simple, no pool to shut down. | Requires sensible configuration and closing `HikariDataSource` on app shutdown. |
| Suitable for | Simple tests, small examples, cases with very infrequent access. | Real services with repeated requests, concurrency, and stable latency requirements. |

Spring Framework recommends `DriverManagerDataSource` and `SimpleDriverDataSource` primarily for **testing purposes**; when connection demand is high, pooling should be used. That does not mean tests must use direct connections: integration tests under load or simulating production behavior should also test with a pool.

## 3. Why Does Connection Pooling Matter Under Load?

Suppose a service receives many database read requests:

**Without a pool** (if each request needs and closes its own connection):
- Each request may have to wait for a physical connection to open.
- Concurrent requests increase connection creation rate and concurrent connections on the DB.
- The DB may hit its connection limit or burn resources on session setup/teardown, even if each SQL query is very fast.

**With a pool** (e.g., `maximumPoolSize = 3`):
- At any given moment, **each pool** manages at most 3 physical connections to the database according to its policy.
- If all 3 are in use, the fourth request must wait for a connection to be returned; if waiting exceeds `connectionTimeout`, it fails with a connection acquisition error.
- When a short request completes, a connection is reused without establishing a new session each turn.

Example of 5 tasks simultaneously trying to borrow a connection from a pool capped at 3:

```text
Task A ---> Connection #1 (active)
Task B ---> Connection #2 (active)
Task C ---> Connection #3 (active)
Task D ---> waits for free connection -----+
Task E ---> waits for free connection -----+
                                           |
                    A closes logically ----+--> D can borrow #1 again
```

The pool limit does **not** mean the entire system has only 3 connections: if 4 application instances run, each with a pool max of 3, total capacity reaches 12 connections (not counting other apps, migrations, admin, and ops tools). Hence sizing must be based on the database's connection budget and maximum instance count, not just HTTP thread counts.

### 3.1. A Pool Does Not Make Inherently Slow SQL Fast

Pooling mainly reduces connection **setup** overhead and manages concurrency; it does not alter query plans, indexes, locks, or SQL speed. Holding transactions too long quickly exhausts active pool connections. Raising `maximumPoolSize` indefinitely often increases DB contention and can worsen performance.

Overall latency can be broken down for diagnosis:

```text
DB-related request duration
≈ time waiting to acquire a connection
+ time executing SQL / waiting on locks / transferring data
+ time processing results and holding the connection
```

This is an approximate analytical model, not an exact measurement formula. When the pool is exhausted, investigate **why connections are held so long**, rather than just raising the cap.

## 4. Spring Framework Configuration with Two Ways of Providing DataSource

The examples below use **Java 17+, Spring JDBC, HikariCP, and H2** to show the difference. The two configurations are **two alternatives**: activate exactly one profile, `direct` or `pooled`. `H2` is used as the test DB; the URL `jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1` keeps the in-memory database alive after the last connection closes within the process, fitting `DriverManagerDataSource` opening/closing multiple connections. This URL configuration is for the demo, not a production deployment recommendation.

### 4.1. Direct configuration: DriverManagerDataSource

File `DirectDataSourceConfig.java`:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration(proxyBeanMethods = false)
@Profile("direct")
public class DirectDataSourceConfig {

    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }
}
```

The configuration specifies the driver, URL, username/password, and creates a plain `DataSource` bean. Whenever a new connection must be acquired, `DriverManagerDataSource` has no idle connection store to reuse. In real applications, do not write production credentials directly in source code; the example uses a test H2 account.

### 4.2. Pooled configuration: HikariDataSource

File `PooledDataSourceConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

@Configuration(proxyBeanMethods = false)
@Profile("pooled")
public class PooledDataSourceConfig {

    @Bean(destroyMethod = "close")
    public HikariDataSource dataSource() {
        HikariConfig cfg = new HikariConfig();
        cfg.setDriverClassName("org.h2.Driver");
        cfg.setJdbcUrl("jdbc:h2:mem:datasource_demo;DB_CLOSE_DELAY=-1");
        cfg.setUsername("sa");
        cfg.setPassword("");

        cfg.setPoolName("datasource-demo");
        cfg.setMaximumPoolSize(3);
        cfg.setMinimumIdle(1);
        cfg.setConnectionTimeout(2_000); // max 2 seconds wait to borrow
        return new HikariDataSource(cfg);
    }
}
```

Same bean name `dataSource` and same H2 connection, but a different connection provisioning mechanism. `destroyMethod = "close"` ensures Spring closes the pool when the ApplicationContext shuts down normally. Activate only one profile to avoid two competing beans.

In a Spring Boot project with `spring-boot-starter-jdbc` and the H2 driver, you can place the two classes above in a Spring-scanned package and run:

```bash
./gradlew bootRun --args='--spring.profiles.active=direct'
./gradlew bootRun --args='--spring.profiles.active=pooled'
```

The two commands are **two independent runs**; do not run them simultaneously on the same application just to compare. The corresponding dependencies section in a Gradle-based Spring Boot project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

When using the Spring Boot JDBC starter, HikariCP is normally already available through dependencies. If configuring Spring Framework manually without the starter, you must explicitly declare `spring-jdbc`, `HikariCP`, and the JDBC driver with compatible versions. The two Java examples above are **configuration classes inside a Spring application**, not standalone programs that can be compiled with `javac` without libraries.

### 4.3. Query Code Does Not Need to Change by DataSource Type

File `ProbeRepository.java`, reusable with both profiles:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProbeRepository {
    private final JdbcTemplate jdbc;

    public ProbeRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int pingDatabase() {
        Integer result = jdbc.queryForObject("SELECT 1", Integer.class);
        if (result == null) {
            throw new IllegalStateException("Database did not return 1");
        }
        return result;
    }
}
```

In both profiles, with H2, `pingDatabase()` returns **1**. That only proves the same query contract executes; **it does not prove the two sources have equivalent performance**. Proving pooling requires observing connection creation, active/idle/pending counts, or concurrency tests, not just checking returned data.

## 5. Common Spring Boot Configuration in Real Applications

In a Spring Boot application using `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa`, HikariCP is usually present and preferred by Spring Boot auto-configuration when no custom `DataSource` bean is defined. You can then configure the pool via `application.yml` instead of creating `HikariDataSource` manually in Java.

PostgreSQL configuration example with values supplied via environment variables:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/learning
    username: learning_user
    password: change-at-deployment
    hikari:
      pool-name: learning-db
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      max-lifetime: 1800000
```

**Explanation:** This is a configuration-format example, not credentials to use verbatim. In real systems, read URL/user/password from external configuration or a secret manager; do not commit real passwords. Hikari's `connection-timeout` and `max-lifetime` use **milliseconds**, while `maximum-pool-size` is a number of connections, not requests.

Some important properties:

| Hikari Property | Effect | Risk When Chosen Poorly |
| --- | --- | --- |
| `maximumPoolSize` | Maximum physical connections managed by the pool (idle + active). | Too low causes waiting; too high overloads the DB, especially across multiple instances. |
| `minimumIdle` | Number of idle connections the pool tries to maintain. | Setting too high can hold many unused DB sessions. |
| `connectionTimeout` | Maximum time to wait when borrowing a connection if none is available. | Too long piles up requests; too short triggers timeouts under load spikes. |
| `maxLifetime` | Expected maximum lifetime of a connection in the pool. | Should be smaller than infrastructure/DB limits that may drop connections; in-use connections are not cut mid-operation solely for reaching this threshold. |
| `idleTimeout` | Idle duration before excess connections may be removed. | Applies when `minimumIdle < maximumPoolSize`; should not be treated as millisecond-exact. |
| `leakDetectionThreshold` | Logs a warning when a connection is held too long. | It is a suspicion warning mechanism; **it does not automatically return or reclaim** leaked connections. |

These are **parameters to understand**, not a fixed optimal preset. With HikariCP, if `minimumIdle` is unset, it normally defaults to `maximumPoolSize`; configuring an essentially fixed-size pool. Only configure a lower `minimumIdle` when there is an operational reason and you have verified scale-up/scale-down connection behavior.

**Spring Boot pitfall:** If the application declares its own `DataSource` bean (like `DriverManagerDataSource` above), the default `DataSource` auto-configuration usually backs off. Adding `spring.datasource.hikari.maximum-pool-size` to YAML **does not automatically turn** a `DriverManagerDataSource` bean you created into a pooled source; Hikari properties only take effect if Hikari is actually running (or you bind configuration to the corresponding bean yourself).

## 6. Spring Transactions and Connection Lifecycle

A common misconception is "the pool always grabs a new connection for every SQL statement" or "having `@Transactional` removes the need for pooling". Both are false.

### 6.1. Outside a Transaction

With `JdbcTemplate` and a single standalone query operation, Spring acquires a connection and releases it when the operation finishes:

- Direct DataSource: typically creates and closes a physical connection for each non-transactional acquire/release.
- Pooled DataSource: borrows a logical connection, then returns it to the pool; the next call can reuse the physical connection.

### 6.2. Inside a Transaction

With a JDBC transaction managed by `DataSourceTransactionManager` or `JdbcTransactionManager`:

1. Spring starts the transaction and binds a `Connection` resource to the execution thread per transaction management rules.
2. `JdbcTemplate` operations within the same transaction obtain the connection via `DataSourceUtils` and typically share that bound connection.
3. After commit/rollback, Spring releases the connection back to the DataSource; direct closes it physically, while pooled returns it to the pool if valid.

Therefore, the number of physical connections created also depends on **transaction boundaries** and how long transactions are held. A long-running transaction both holds DB resources and occupies an active pool slot. `@Transactional` controls consistency/commit/rollback, whereas the pool controls allocation and reuse of connections across many transactions.

### 6.3. Closing Connections with the Right API

When using plain JDBC outside a Spring-managed transaction, use `try-with-resources`:

```java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class PlainJdbcProbe {
    public static int readOne(DataSource ds) throws SQLException {
        try (Connection con = ds.getConnection();
             Statement statement = con.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {
            if (!result.next()) {
                throw new SQLException("No row returned");
            }
            return result.getInt(1);
        }
    }
}
```

The method above returns **1** when SQL `SELECT 1` returns a row containing 1 (e.g., H2/PostgreSQL). `try-with-resources` calls `close()` even when an exception occurs. With direct, the physical connection terminates; with Hikari, the handle is typically returned to the pool.

Inside a Spring-managed transaction, avoid calling `dataSource.getConnection()` and `close()` arbitrarily yourself because doing so can bypass the transaction context. Prefer `JdbcTemplate`. If you need to use a JDBC `Connection` directly while still participating in Spring's transaction, use the API pair:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.datasource.DataSourceUtils;

public final class SpringAwareProbe {
    public static void run(DataSource ds) throws SQLException {
        Connection con = DataSourceUtils.getConnection(ds);
        try {
            try (var statement = con.createStatement();
                 var result = statement.executeQuery("SELECT 1")) {
                result.next();
                int value = result.getInt(1);
                if (value != 1) {
                    throw new SQLException("Unexpected result");
                }
            }
        } finally {
            DataSourceUtils.releaseConnection(con, ds);
        }
    }
}
```

`DataSourceUtils.releaseConnection` only closes/releases when appropriate for the transaction boundary. Do not hold a connection beyond the needed duration; a single connection must not be shared arbitrarily across multiple threads. Even when using a pool, all `ResultSet`, `Statement`, and `Connection` objects must still be released properly.

## 7. Directly Verifying the Difference

A useful experiment is requesting **two connections simultaneously** when the pool allows only one connection. The following example is complete Java 17 code at the class level `ConnectionPoolExperiment.java`, runnable in a project with `spring-jdbc`, `HikariCP`, H2, and suitable runtime logging.

```java
import java.sql.Connection;
import java.sql.SQLTransientConnectionException;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class ConnectionPoolExperiment {
    private static final String URL =
        "jdbc:h2:mem:pool_experiment;DB_CLOSE_DELAY=-1";

    public static void main(String[] args) throws Exception {
        DriverManagerDataSource direct = new DriverManagerDataSource();
        direct.setDriverClassName("org.h2.Driver");
        direct.setUrl(URL);
        direct.setUsername("sa");
        direct.setPassword("");

        try (Connection first = direct.getConnection();
             Connection second = direct.getConnection()) {
            System.out.println("Direct: obtained two connections");
        }

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(URL);
        config.setUsername("sa");
        config.setPassword("");
        config.setMaximumPoolSize(1);
        config.setMinimumIdle(1);
        config.setConnectionTimeout(1_000);

        try (HikariDataSource pool = new HikariDataSource(config);
             Connection held = pool.getConnection()) {
            try (Connection second = pool.getConnection()) {
                System.out.println("Unexpected second connection");
            } catch (SQLTransientConnectionException expected) {
                System.out.println("Pool: second checkout timed out");
            }
        }
    }
}
```

**Expected lines printed to `System.out` when H2 is working and the pool is configured as above:**

```text
Direct: obtained two connections
Pool: second checkout timed out
```

HikariCP and logging libraries may print additional messages to **stderr**, which are not counted in the stdout lines above. The experiment shows:

- Direct created 2 concurrent connections because it **has no pool limit** itself (the DB may still have its own limit).
- The `maximumPoolSize=1` pool holds one active connection, so the second call waits up to about 1 second and then fails when nobody returns a connection.
- **This is a concurrency limit example**, not a speed benchmark. Nor does it prove Hikari creates strictly one connection in every state: on error/expiration, it may replace the physical connection per pool policy.

Do not use `Connection.equals()`, `hashCode()`, or compare `first == second` to conclude whether physical connections are reused: a pooled DataSource may return different wrapper objects for the same physical connection.

### 7.1. Observing the Pool Directly Instead of Guessing

With an initialized `HikariDataSource`, you can inspect the pool MXBean:

```java
HikariDataSource pool = /* DataSource created in the pooled example */;
var mx = pool.getHikariPoolMXBean();

int total = mx.getTotalConnections();
int active = mx.getActiveConnections();
int idle = mx.getIdleConnections();
int pending = mx.getThreadsAwaitingConnection();
```

This is an **illustrative snippet placed inside code that already has a `pool` variable**, not a standalone Java program. Counter values change continuously under load; do not assert a fixed value at arbitrary moments. With Spring Boot Actuator + Micrometer, you can track the corresponding Hikari metrics when configuration supports it. Correlate application metrics with DB session counts, timeout errors, query time, and transaction duration to identify bottlenecks.

## 8. Choosing Configuration and Handling Common Errors

### When to Use DriverManagerDataSource

- Very small tests, demo scripts performing a few JDBC operations, or environments needing minimal setup to learn connection mechanics.
- When the goal is to clearly observe a single physical connection being opened/closed; no repeated request volume needed.
- Avoid putting a direct DataSource into an environment handling frequent requests just because it takes fewer lines of configuration.

### When to Use a Pooled DataSource

- Web/API applications, batch jobs, workers, or real systems querying the DB repeatedly.
- When concurrency requires limits, waiting mechanisms, timeouts, monitoring, and connection reuse policies.
- When you need to control total connections to the DB across instances and resource budgets.

Do not set `maximumPoolSize` as large as possible just because you have a pool. Measure: peak active connections, borrow wait time, timeout rate, SQL latency, lock contention, instance count, and DB connection limits.

### Diagnostic Scenarios

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Every request incurs heavy connection setup cost | Using non-pooled `DriverManagerDataSource` | Confirm actual runtime `DataSource` bean class; consider pooled DataSource. |
| Hikari reports borrow timeouts | Pool exhausted by long-held connections, leaks, slow SQL, or too small a limit | Check active/pending, transaction duration, connection release paths, DB locks. |
| DB reports too many connections | Sum of pools across multiple instances/apps exceeds DB capacity | Sum `maximumPoolSize` across instances; adjust budget. |
| Raising pool size does not speed up requests | DB/SQL/locks are the bottleneck | Use query plans, slow query logs, metrics, and inspect transactions. |
| Connections occasionally fail after idle | DB/network drops connections, infra timeout, mismatched validation/lifetime | Compare DB, proxy, load balancer timeouts with `maxLifetime`/keepalive. |
| Suspected leak warnings logged | Connection held long or unreleased; could be a valid long query | Inspect stack traces, transaction boundaries, and actual duration; leak detection only warns. |
| Changing `spring.datasource.hikari.*` has no effect | App created its own `DriverManagerDataSource` or another bean type | Confirm bean class, auto-configuration conditions, and active config source. |

### Pitfalls Around Closing Connections

**Wrong:** thinking a pooled connection does not need `close()` because "the pool will take it back automatically". Forgetting `close()` leaves the connection marked active; eventually the pool can run dry. **Right:** always release the logical connection via `close()` or Spring's management API.

**Wrong:** thinking Hikari `close()` always destroys the physical connection. **Right:** it usually returns it for reuse; the pool may evict a connection that is no longer eligible.

**Wrong:** using `try (Connection c = dataSource.getConnection())` inside a Spring-managed transaction and assuming that connection surely participates in the current transaction. **Right:** use `JdbcTemplate` or `DataSourceUtils` to stay compatible with transaction-bound resources.

**Wrong:** sharing a single singleton `Connection` across multiple requests instead of a pool. **Right:** share **`DataSource`** as a bean, and have each task flow borrow and return `Connection` following its proper lifecycle.

## 9. Self-Check Questions

**1.** Does `DriverManagerDataSource` implement the `DataSource` interface, and does it pool by itself?  
**Answer:** It implements `DataSource` but does not pool; each time a new connection must be created, it opens a physical connection.

**2.** With a Hikari pool capped at 2 connections and both busy, what happens when a third request calls `getConnection()`?  
**Answer:** It waits for a connection to be returned, up to `connectionTimeout`; if the wait times out, a connection acquisition error is thrown. It does not exceed the limit just to serve that request.

**3.** Does calling `close()` on a connection borrowed from a pool always close the socket to the DB?  
**Answer:** No. It usually returns the handle to the pool; the physical connection can be reused if still valid.

**4.** Do two DAOs both using `JdbcTemplate` inside one `@Transactional` method typically need two physical connections?  
**Answer:** Not necessarily. With the same DataSource and properly managed transactions, operations can share one connection bound to the transaction. This holds whether the source is direct or pooled.

**5.** If `maximumPoolSize=10` and there are 6 application instances, does the DB always use at most 10 connections?  
**Answer:** False. The six pools alone can total up to 60 physical connections, besides other connections.

**6.** Can pooling be verified by checking whether two Java `Connection` references are `==`?  
**Answer:** No. The objects may be wrappers/proxies, which do not directly reflect the identity of the underlying physical connection.

## 10. Pre-Production Checklist

1. Verify the **actual `DataSource` type** registered as a runtime bean, not just dependencies or YAML.
2. Use a pooled DataSource for repeated workloads; clearly separate pool management from transactions and SQL.
3. Size the connection budget by **DB limit × instance count**, choosing `maximumPoolSize` by measurement rather than estimating from thread count alone.
4. Set `connectionTimeout` sensibly against SLAs; measure both borrow wait time and connection hold time.
5. Acquire/close connections with the right lifecycle; use `JdbcTemplate`/`DataSourceUtils` with Spring transactions.
6. Monitor active, idle, pending, timeouts, query latency, transaction duration, and DB errors.
7. Validate `maxLifetime`, idle, and keepalive policies against DB/network timeouts.
8. Ensure the pool closes on application shutdown; protect credentials via proper configuration mechanisms.
9. For integration/performance tests, use a production-representative pool configuration when verifying concurrency.

## Official References

- [Spring Framework – Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): sections on `DataSource`, `DriverManagerDataSource`, `DataSourceUtils`, and transactions.
- [Spring Boot – SQL Databases / DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html): pool selection and `spring.datasource.hikari.*` under auto-configuration.
- [HikariCP – Configuration README](https://github.com/brettwooldridge/HikariCP): `maximumPoolSize`, `connectionTimeout`, `minimumIdle`, `maxLifetime`, leak detection.

**Remember:** `DriverManagerDataSource` creates a new physical connection whenever a fresh connection is needed; a pooled `DataSource` supplies logical connections from a managed set of physical connections. Both provide the `DataSource` interface to `JdbcTemplate`; the difference determines performance under repeated load, concurrency limits, and connection return responsibilities.
