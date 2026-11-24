# Maximum Connections, Borrow Timeout, and Connection Lifetime of a DataSource

A Spring application accesses a database through a **DataSource**. When a DataSource is managed by a **connection pool** (such as HikariCP), the application normally reuses JDBC connections instead of establishing a new physical connection for every query. Three limits that must be distinguished are:

1. **Maximum connections**: how many simultaneous connections to the database the pool is allowed to maintain.
2. **Borrow timeout**: how long a call requesting a connection is allowed to wait before failing.
3. **Lifetime**: how long a physical connection is kept in the pool before being replaced.

This lesson uses **HikariCP with Spring Boot** as a concrete example. This is the typical pool configuration when an application uses spring-boot-starter-jdbc or spring-boot-starter-data-jpa and HikariCP is on the classpath. Limits at the pool layer differ from SQL, transaction, and database infrastructure timeouts.

## 1. Connection Borrow and Return Lifecycle

Imagine a pool containing a number of physical connections to the database:

~~~text
                         DataSource / HikariCP
                  +--------------------------------+
Request A -------> | Idle connection? -> lend it    | ----> Connection A
Request B -------> | Below limit? -> create new     | ----> Connection B
Request C -------> | Full? -> wait for returned     | ----> wait / timeout
                  +--------------------------------+
                         ^                 |
                         |                 v
              Connection.close()      JDBC to DB
                return to pool     (SQL/transaction)
~~~

Logically, the pool tracks:

- **Active (in-use)**: connections currently borrowed by the application.
- **Idle**: connections sitting free and available to be borrowed.
- **Total**: total connections managed by the pool, close to Active + Idle in steady state.
- **Pending / Waiting**: number of calls waiting to be issued a connection; **not** part of Total.

When the application calls **DataSource.getConnection()**, HikariCP picks an available connection, attempts to create a new connection if capacity remains, or waits when all connection-issuing capacity is busy. When the application calls **Connection.close()** on a connection borrowed from the pool, the connection is usually **returned to the pool**, rather than immediately closing the physical socket. A connection is only closed physically when the pool decides to evict it, the connection is broken, or the pool shuts down.

In manually managed JDBC code, try-with-resources must be used to return connections even when an exception occurs. In Spring, **JdbcTemplate** and Spring's transaction components manage acquiring/returning based on context; in particular, do not manually close a connection managed by a Spring transaction just to "release it early".

## 2. maximumPoolSize — Maximum Connection Count

**maximumPoolSize** is the upper bound on physical connections managed by **one pool instance**, counting both Active and Idle. In HikariCP, the typical default is **10** unless configured otherwise; verify the actual library version and Spring Boot configuration before relying on defaults.

Example when **maximumPoolSize = 8**:

| State at a Point in Time | Active | Idle | Total | What Happens |
| --- | ---: | ---: | ---: | --- |
| Room available | 3 | 2 | 5 | A new request can borrow an Idle connection |
| No Idle left, not full yet | 5 | 0 | 5 | The pool can create additional connections up to 8 |
| Saturated | 8 | 0 | 8 | New requests must wait for a returned connection, up to connectionTimeout |
| One connection returned | 7 | 1 | 8 | A waiting request can receive that connection |

The table is an **illustrative model**; connection creation/validation is asynchronous and metric observation timing can have minor skew. The invariant to remember: increasing threads calling the database does not grow the pool indefinitely, and waiting threads **do not turn into** new connections exceeding the limit.

### 2.1. Limit Per Pool, Not System-Wide

If there are three application instances, each with one pool having maximumPoolSize = 8, the application **can** use up to 3 × 8 = **24 database connections** in total. If each instance has two independent DataSources each capped at 8, the theoretical ceiling is 3 × 2 × 8 = **48**. The database also needs connections for migrations, admin, jobs, and other services.

A rough budget check:

~~~text
(number of instances) × (pools per instance) × (maximumPoolSize)
    + (connections from other clients) + (headroom)
    <= (usable connection limit of the database)
~~~

This is a **connection ceiling check**, not a formula to find the optimal pool size. Per-user/database limits, proxies, failover, or cloud-managed databases may have lower limits than the advertised total max_connections. Do not increase maximumPoolSize merely because HTTP request volume is high: only tasks currently **holding a JDBC connection** occupy Active.

### 2.2. Choosing Pool Size by Measurement

Start with a modest configuration and measure under representative operating conditions: throughput, p95/p99 latency, Active/Idle/Pending counts, borrow/hold times, query latency, database CPU/I/O, locks, and connection limits. Increasing pool size can sometimes improve serving capacity, but can also cause the database to run too many concurrent queries, increasing contention and latency and reducing throughput.

Directional relationship from Little's Law:

~~~text
Average Active connections ≈ DB task completion rate per second
                           × average connection hold time per task
~~~

If DB tasks complete **100 times/second**, each holding a connection for **0.04 seconds**, average Active is roughly **4**. This is only a steady-state average, insufficient on its own to decide maximumPoolSize: you must account for bursts, hold-time distribution, long transactions, DB resources, and latency requirements. Pool wait time is not included in connection **hold** time.

## 3. connectionTimeout — Borrow Wait Time

HikariCP's **connectionTimeout** is the maximum time a **getConnection()** call waits to receive an available connection. If the timeout expires before the pool can supply one, the call fails with an **SQLException** (which in the Spring path may be translated into an appropriate DataAccessException). HikariCP's configuration unit is **milliseconds**. Typical HikariCP default: **30,000 ms = 30 seconds**; the minimum according to HikariCP documentation is 250 ms.

Example setting **connectionTimeout = 2,000 ms** and **maximumPoolSize = 8**:

~~~text
t = 0 ms      8 connections are Active; the 9th request calls getConnection()
t = 700 ms    no connection returned yet -> keep waiting
t = 1,200 ms  if a connection becomes available -> the call can succeed
t ≈ 2,000 ms  if still not issued -> the call fails with timeout
~~~

Each call has its own timer. This timeline describes the principle, without guaranteeing scheduling across multiple threads. Connection acquisition time can also include opening/validating a connection when the pool needs to create a new one; therefore, do not interpret that timeouts only occur when Total equals maximumPoolSize.

**connectionTimeout does not limit SQL query duration.** For instance, if getConnection() succeeds in 100 ms and then runs an SQL statement taking 20 seconds, connectionTimeout = 2 seconds will not cancel that query. Nor does it mean an HTTP request will complete within 2 seconds, as there are many steps before/after borrowing.

### 3.1. Distinguishing Timeout Types

| Limit | Measured Where? | What Does It Protect? |
| --- | --- | --- |
| HikariCP connectionTimeout | Waiting inside DataSource.getConnection() | Prevents waiting to borrow a connection forever |
| HikariCP validationTimeout | Checking whether a connection is alive | Bounds connection validation time |
| JDBC Statement.setQueryTimeout() | Statement execution, depending on driver/DBMS | Bounds SQL statement execution time |
| Spring @Transactional(timeout = ...) | Spring transaction scope, depending on transaction manager/integration | Bounds transaction duration per framework semantics |
| Driver connect/socket/network timeout | Network handshake or read/write to DB | Detects connectivity/infrastructure issues |
| HTTP server/client timeout | Application request flow | Bounds duration at the HTTP layer |

Do not lump everything into one "database timeout" number. In particular, a transaction or query timeout does not necessarily release all resources immediately if the driver, DBMS, or query cancellation responds slowly. Always observe the actual behavior of your stack.

### 3.2. Wait Long or Fail Fast?

- **Too short**: legitimate bursts can trigger errors even when connections are about to be returned.
- **Too long**: many requests/threads pile up waiting, raising response times and easily cascading congestion to the HTTP server.
- **Reasonable**: fits within the end-to-end latency budget and is verified by load testing; the application handles connection borrow errors with an appropriate response instead of aggressive retries that congest the pool further.

In practice, increasing connectionTimeout may simply make users **wait longer** if the root cause is slow queries, transactions holding connections too long, or a pool too small for the workload. Investigate before changing timeouts.

## 4. maxLifetime — Physical Connection Lifetime

**maxLifetime** limits the desired maximum age of **each physical connection** in the pool, measured from when it was created. HikariCP typically defaults to **1,800,000 ms = 30 minutes** (depending on version/configuration). It is used to proactively rotate connections before a DB, proxy, firewall, or load balancer terminates sockets under its own policy.

Key rule: **HikariCP does not forcibly close a connection currently borrowed by the application merely for reaching maxLifetime**. When a connection exceeds its age while Idle, the pool can retire it; when Active, retirement usually happens after it is returned. Therefore, maxLifetime is **not** a limit on SQL statement or transaction duration.

~~~text
00:00  Physical connection X is created
12:00  X is borrowed to execute business logic
25:00  X reaches maxLifetime e.g. 25 minutes
25:00  If X is still Active, business work is not interrupted automatically
27:00  X is returned; pool can retire X and create a replacement when needed
~~~

HikariCP applies slight jitter to expiration times across connections to avoid closing/opening all of them simultaneously. Do not assume retirement occurs to the exact millisecond.

### 4.1. Must Account for Database and Infrastructure Lifetime Policies

Suppose a DB proxy sets **maximum lifetime per connection to 30 minutes**. You might choose maxLifetime on the pool side to be **25 minutes**, leaving a buffer before the proxy closes it; these are illustrative numbers, not a universal configuration for all systems. If the proxy limits to **15 minutes**, setting maxLifetime to 25 minutes will not protect against that limit.

Important: **maximum connection age** and DB/proxy **idle timeout** are two different policies. A maxLifetime shorter than the external maximum age enables proactive refresh. However, if infrastructure cuts idle connections very early, you must also examine keepalive/idle policies, driver TCP keepalive, and how the pool checks liveness before reissuing.

## 5. idleTimeout, minimumIdle, and keepaliveTime — Do Not Confuse with maxLifetime

Three supporting parameters explain why Idle connections are kept or retired.

### 5.1. idleTimeout — Idle Duration

**idleTimeout** is how long a connection sits **unused in the pool** before it can be removed as surplus. In HikariCP, this Idle-shrinking mechanism takes effect when **minimumIdle is less than maximumPoolSize**. HikariCP does not remove Idle connections below the maintained minimum due to idleTimeout. HikariCP's typical default for idleTimeout is **600,000 ms = 10 minutes**; actual eviction may occur slightly later due to housekeeping schedules.

**minimumIdle** is the minimum target number of Idle connections the pool tries to maintain. If minimumIdle is not configured, HikariCP typically sets it equal to maximumPoolSize and operates as a fixed-size pool. This setting does not guarantee all connections are opened immediately at startup; the pool still follows its own connection creation and recovery process.

Example with **maximumPoolSize = 8**, **minimumIdle = 2**, **idleTimeout = 10 minutes**:

- Under high load, the pool can grow up to 8 connections.
- When load drops, idle connections beyond the target of 2 can be retired over time after the idle duration.
- The pool still tries to keep 2 Idle when feasible; an Active connection is not closed by idleTimeout because it is **not Idle**.

If minimumIdle is unset and defaults to maximumPoolSize, do not expect idleTimeout to shrink total connections down to 2. HikariCP generally recommends keeping a steady pool (leaving minimumIdle unset) unless there is a specific operational need.

### 5.2. keepaliveTime — Liveness Check for Idle Connections

**keepaliveTime** specifies the interval at which the pool proactively checks whether a connection is alive to prevent infrastructure from dropping it for inactivity. HikariCP performs keepalive only on **Idle connections**: temporarily taking one out, testing it via JDBC Connection.isValid() or a configured test query, and returning it to the pool. Any non-zero value must be less than maxLifetime and meet HikariCP's minimum bound (typically 30 seconds). Default values may vary by version, so check the library version in use.

- keepalive does **not** set a connection age limit.
- keepalive does **not** stop running SQL or protect Active connections from all DB/proxy timeouts.
- Pool-level keepalive and OS/JDBC-driver TCP keepalive are separate mechanisms; depending on infrastructure, both may be needed.

### 5.3. Quick Comparison Table

| Parameter | When Calculated/Applied? | Closes Active Connection Immediately? | Typically Addresses |
| --- | --- | --- | --- |
| maximumPoolSize | Total connections the pool manages | No | Bounding connection load on the database |
| connectionTimeout | Duration a getConnection() call waits | No | Preventing infinite pool waiting |
| maxLifetime | Connection age since creation | No | Rotating connections before infrastructure cutoffs |
| idleTimeout | Unused duration while connection is Idle | No | Reclaiming Idle connections above minimumIdle |
| minimumIdle | Idle level the pool tries to keep | No | Balancing readiness and resources |
| keepaliveTime | Periodically checks Idle connections | No | Reducing chance of receiving a dead connection from idle timeout |

## 6. Configuration in Spring Boot

When Spring Boot auto-configures HikariDataSource, HikariCP parameters are typically placed under **spring.datasource.hikari**. Spring Boot prefers HikariCP when the library is present; if the application creates a DataSource manually or has multiple DataSources, verify the exact bean and prefix the application binds.

An **illustrative** configuration, assuming datasource URL/username/password are configured separately and the DB/proxy allows physical connections to live **longer than 25 minutes**:

File application.yml:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: app-main
      maximum-pool-size: 8
      connection-timeout: 2000     # 2 seconds; borrow wait time
      max-lifetime: 1500000        # 25 minutes; physical connection age
~~~

These three numbers are **learning examples**, not to be copied into production configuration without load testing and checking DB/proxy limits. These numeric values are **milliseconds** for HikariCP timeout properties. With a single datasource, Spring Boot can auto-configure the pool from the JDBC/JPA starter; a matching JDBC driver dependency and valid database connection must be provided.

If you truly need the pool to **scale Idle connections up and down**, you can add:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 8
      minimum-idle: 2
      idle-timeout: 600000        # 10 minutes
      connection-timeout: 2000
      max-lifetime: 1500000
      keepalive-time: 120000     # 2 minutes, checks Idle only
~~~

When applying the second configuration, ensure keepaliveTime < maxLifetime; choose lifetime based on infrastructure policy and measure changes in connection churn. This configuration replaces the first illustrative configuration—it is **not** a YAML file combining two top-level spring blocks.

Equivalent configuration (the three main parameters only) in application.properties:

~~~properties
spring.datasource.hikari.maximum-pool-size=8
spring.datasource.hikari.connection-timeout=2000
spring.datasource.hikari.max-lifetime=1500000
~~~

With a manually declared DataSource, Spring Boot may not auto-bind these properties under the prefix above; you must declare @ConfigurationProperties/binding for that bean. Do not assume editing application.yml always affects the running pool: verify effective configuration at startup, profiles, environment variables, and the number of DataSources.

### 6.1. Acquiring and Returning Connections in Java

The snippet below is **illustrative code inside a Spring Boot application already configured with JdbcTemplate, driver, and database**; not a standalone Java program run with javac. Its goal is to show application code using DataSource through Spring JDBC without manually managing connection sockets:

File DatabaseProbeRepository.java:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DatabaseProbeRepository {
    private final JdbcTemplate jdbcTemplate;

    public DatabaseProbeRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int probe() {
        Integer value = jdbcTemplate.queryForObject(
            "SELECT 1", Integer.class
        );
        if (value == null) {
            throw new IllegalStateException("Database returned NULL");
        }
        return value;
    }
}
~~~

With PostgreSQL, SELECT 1 returns 1. JdbcTemplate borrows and releases connections per Spring rules; when the method runs inside a Spring transaction, the connection may be held until the transaction finishes. When getConnection() actually occurs depends on the access mechanism and transaction manager. Therefore, **method execution duration** does not necessarily equal **connection hold duration**.

When using direct JDBC outside a Spring transaction, close resources with try-with-resources:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class DirectJdbcProbe {
    public static int probe(DataSource dataSource) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement("SELECT 1");
             ResultSet result = statement.executeQuery()) {
            return result.next() ? result.getInt(1) : 0;
        }
    }
}
~~~

This is also a **helper class inside an application with a DataSource**, not a standalone runnable file because it lacks main and database setup. The try-with-resources block returns the connection to the pool even if the statement/query fails. **Do not use raw getConnection()/close() to manage connections yourself inside a @Transactional method when you want Spring to manage the same transaction**; use JdbcTemplate/DataSourceUtils or an appropriate mechanism.

### 6.2. Standalone Java 17+ Example Calculating Connection Budget

This is a limit-calculation exercise, **opening no database connections**. Save as PoolBudget.java:

~~~java
public class PoolBudget {
    public static void main(String[] args) {
        int instances = 3;
        int poolsPerInstance = 1;
        int maximumPoolSize = 8;
        int databaseCapacity = 40;
        int reservedForOthers = 6;

        int applicationCeiling =
                instances * poolsPerInstance * maximumPoolSize;
        int remainingHeadroom =
                databaseCapacity - reservedForOthers - applicationCeiling;

        System.out.println("App connection ceiling: "
                + applicationCeiling);
        System.out.println("Remaining DB headroom: "
                + remainingHeadroom);
    }
}
~~~

Compile/run in the directory containing the file using JDK 17 or newer:

~~~bash
javac -encoding UTF-8 PoolBudget.java
java PoolBudget
~~~

Exact stdout:

~~~text
App connection ceiling: 24
Remaining DB headroom: 10
~~~

If remainingHeadroom is negative, the configured ceilings exceed the assumed DB budget; even when positive, you must still measure performance and real limits. The formula does not guarantee the DB can sustain that many concurrent queries.

## 7. Typical Scenarios and How to Handle Them

### Scenario A: Pool Saturated and Connection Borrows Time Out

Suppose maximumPoolSize = 8, Active = 8, Idle = 0, and Pending rises steadily. After connectionTimeout, some getConnection() calls fail. A sound approach is:

1. Inspect Active, Idle, Pending, timeout counts, and borrow latency.
2. Locate where connections are held long: transactions wrapping external HTTP calls, queries missing indexes, lock waits, heavy loop processing inside transactions, unclosed ResultSet streams.
3. Shorten connection hold time, fix queries/locks, or fix connection leaks.
4. Only then consider increasing the pool if the DB has spare CPU/I/O, connection headroom, and load tests prove a benefit.

**Do not** automatically conclude the pool is too small just because timeouts occur; even a large pool can run dry if connections are not returned or the DB is slow.

### Scenario B: Many Idle Connections

If Total is close to maximumPoolSize while Active is low and Pending = 0, there is not necessarily an error: minimumIdle may default to maximumPoolSize. You can keep it as-is to avoid connection creation overhead during spikes, or try a lower minimumIdle if holding DB connections has significant cost and bursts do not require high readiness.

Switching to a smaller minimumIdle lets **idleTimeout** shrink the pool. However, if load rises rapidly, the pool must establish new connections and borrow latency may rise during scale-up.

### Scenario C: Connections Unexpectedly Closed by Database/Proxy

Symptoms may include I/O errors, connection reset, stale connections, or failed liveness checks. Check database idle timeouts, proxy maximum connection age, NAT/firewall, and driver; choose maxLifetime **smaller than the external age limit** and consider keepalive/TCP keepalive if the environment drops Idle connections.

Do not set maxLifetime extremely low to "cure every network error": doing so can cause heavy connection churn, burning CPU, TLS handshakes, and DB resources without solving the real bug.

### Scenario D: Increasing Pool Size Makes Queries Slower

If the DB has already hit CPU/I/O limits or lock contention, allowing more concurrent queries can increase latency. The fix is usually analyzing execution plans, queries, indexes, transactions, and workload; reducing concurrency can be better than raising maximumPoolSize.

## 8. Observing Metrics and Verifying Changes

When using Spring Boot Actuator/Micrometer with appropriate configuration, DataSource/HikariCP metrics typically include the **jdbc.connections** and **hikaricp** groups. Exact names depend on version and registry; query the list of actually exposed meters before building dashboards/alerts.

For example, if metrics endpoints are enabled and accessible in a test environment:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.idle
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
~~~

**The curl commands only work when the application is running with Actuator and metrics endpoints exposed**; verify host/port and metric names against your actual application. Do not expose sensitive internal endpoints to the Internet just for testing convenience.

Minimum observations:

| Metric | Meaning When Monitored Together |
| --- | --- |
| Active persistently near Max | Pool may be under pressure or connections are held too long |
| Idle = 0, Pending rising | Callers are waiting; pool cannot issue fast enough |
| Rising timeout rate | Borrow calls are failing; investigate root cause |
| High connection usage time | Queries, transactions, or code holding connections too long |
| Database CPU / IO / lock wait | Distinguishes pool shortage from SQL execution bottlenecks |
| Total/max connections on database | Checks total budget across all app instances/pools |

One caution: HikariCP's **leakDetectionThreshold**, when enabled, only logs when a connection is held longer than the threshold—**it does not automatically reclaim leaked connections**. Legitimate long transactions can also trigger false alarms. Therefore, use logs, traces, and hold duration to identify root causes rather than merely raising the threshold or disabling logs.

### Verified Configuration Tuning Process

1. Record a baseline of throughput, p95/p99, Pending, timeouts, DB CPU, and connection limits.
2. Define the goal: prevent borrow timeouts, reduce connection hold cost, or prevent network/DB disconnects.
3. Adjust **one related group of parameters** and check constraints between them; e.g., maxLifetime < external age limit, keepaliveTime < maxLifetime.
4. Run load tests covering normal load, bursts, and database faults; monitor both the application and the DB.
5. Compare results against the baseline, also checking instance count, autoscaling environment, profiles, and which DataSource is actually active.
6. Keep configurations proven beneficial; if the failure merely shifted from borrow timeout to DB overload, investigate and retune.

## 9. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| maximumPoolSize = 20 means the entire system opens only 20 connections | The limit applies **per pool**; multiply by the number of instances/independent sources |
| connectionTimeout = 2 seconds means SQL cannot run longer than 2 seconds | It only bounds **borrowing a connection**; SQL/transactions need separate timeouts |
| maxLifetime = 25 minutes will cut a transaction at minute 25 | HikariCP does not proactively close an Active connection for aging out |
| idleTimeout = 10 minutes always shrinks a fixed pool | Idle eviction depends on **minimumIdle < maximumPoolSize** |
| Raising maximumPoolSize definitely makes the application faster | The database may become overloaded from too many concurrent queries |
| Calling Connection.close() always closes the physical socket | With a pooled DataSource, it typically returns the connection to the pool |
| Pending = 5 means the pool opened 5 extra connections | Pending counts calls currently **waiting**, not Total |
| keepaliveTime replaces maxLifetime | Keepalive tries to keep Idle connections alive; maxLifetime rotates by age |
| maxLifetime fixes all database timeouts | Must distinguish **connection age** timeouts from **idle** timeouts |
| leakDetectionThreshold fixes leaks automatically | It only emits a signal/log for investigation |

## 10. Self-Check with Scenarios

**Question 1.** An instance has maximumPoolSize = 6, currently 6 Active and 0 Idle. A new thread calls getConnection(), connectionTimeout = 1,500 ms. If no connection is returned and no connection-issuing path succeeds, what happens?

**Answer:** the thread waits up to roughly 1,500 ms and then fails because no connection could be issued. It does not automatically expand the pool to 7 connections.

**Question 2.** There are four replicas, each with two pools, each pool with maximumPoolSize = 8. What is the connection ceiling from these pools?

**Answer:** 4 × 2 × 8 = **64**. Budget must also remain for non-application connections, migrations, and admin operations; 64 says nothing about optimal throughput.

**Question 3.** Connection X is created at 10:00 and borrowed at 10:24. maxLifetime = 25 minutes; the transaction returns X at 10:28. Is X forcibly closed by the pool mid-transaction at 10:25?

**Answer:** **No**. A currently borrowed connection is not cut by HikariCP simply for reaching maxLifetime; it may be retired upon return. Independent infrastructure failures can still disconnect the transaction.

**Question 4.** maximumPoolSize = 8, minimumIdle is unset, and idleTimeout = 30 seconds. Should you default to expecting Total to shrink to 1 after 30 seconds?

**Answer:** **No**. When minimumIdle defaults to maximumPoolSize, idleTimeout is not used to shrink the pool to 1. To scale Idle connections, set minimumIdle lower than maximumPoolSize and understand the cost of reopening connections.

**Question 5.** Monitoring shows Active = 8/8, Pending high, DB CPU high, slow p99 queries. Should the first priority be raising maximumPoolSize to 30 immediately?

**Answer:** **Not yet**. Inspect query plans, indexes, lock waits, connection hold duration, and the DB's load capacity. Adding connections can worsen DB congestion.

**Question 6.** A proxy closes the physical socket of every connection after 20 minutes, while pool maxLifetime = 30 minutes. What adjustment should be tested?

**Answer:** choose maxLifetime smaller than **20 minutes**, leaving a safety margin, while also checking network/idle timeout causes and testing in the actual infrastructure. If the proxy enforces an **idle** timeout, you must also consider keepalive and Idle policies, not just maxLifetime.

## 11. Takeaways When Configuring DataSource

- **maximumPoolSize** governs **how many connections can exist simultaneously** in one pool.
- **connectionTimeout** governs **how long callers may wait to borrow a connection**.
- **maxLifetime** governs **the physical age of a connection before retirement**.
- **idleTimeout + minimumIdle** determine **whether excess idle connections are reclaimed**.
- **keepaliveTime** helps verify Idle connections are alive, without limiting queries.
- A good configuration must fit **actual load, database limits, replica count, network, and transaction duration**; measure metrics on both the application and DB sides.

### References for Version Verification

- Official HikariCP: https://github.com/brettwooldridge/HikariCP (Configuration section, properties maximumPoolSize, connectionTimeout, maxLifetime, minimumIdle, idleTimeout, keepaliveTime).
- Spring Boot — SQL Databases / Configure a DataSource: https://docs.spring.io/spring-boot/reference/data/sql.html
- Spring Boot — Actuator Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
