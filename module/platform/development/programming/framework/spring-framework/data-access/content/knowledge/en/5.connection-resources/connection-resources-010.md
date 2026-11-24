# Reading Errors and Metrics to Detect Connection Leaks

When a Java/Spring application uses JDBC, Hibernate/JPA, or Spring JDBC, many data access operations must borrow a `Connection` from a `DataSource`. With a connection pool, this resource must be **returned to the pool** after use. If connections are held too long or never returned, the application can experience timeout errors even while the database remains healthy.

To diagnose incidents, do not look only at a single log line or a single `active` metric. Read **error messages, stack traces, pool metrics over time, connection hold duration, application load, and database state** together along the same timeline. This article uses Spring JDBC and HikariCP as examples, yet the diagnostic reasoning applies to other pools as well when mapped to their corresponding metric names and mechanisms.

## 1. Learning Objectives

After this article, you will be able to:

- Distinguish a **connection leak**, long-held connections, pool exhaustion from high load, slow queries/transactions, and the database refusing connections.
- Read accurately what `active`, `idle`, `total`, `max`, `pending`, timeout counters, and acquire/usage timers mean.
- Understand what HikariCP's `leakDetectionThreshold` warns about, where the stack trace points, and when a message indicates the connection was later returned.
- Use logs, Spring Boot Actuator/Micrometer, or Hikari JMX to form hypotheses and verify them against metric time series.
- Trace suspicious stack traces/call sites back to Java/Spring source checks, fixing JDBC lifecycles with `try-with-resources`, `JdbcTemplate`, and proper transaction boundaries.
- Evaluate fixes through load testing, comparing before/after and avoiding "workarounds" that merely mask symptoms.

## 2. From Borrowing a Connection to Returning a Connection

With a typical JDBC pool:

~~~text
Request / scheduled job
        |
        v
Service / Repository
        |
        v
DataSource.getConnection()
        |
        +--> Pool has an idle connection? ---- Yes --> borrow
        |                                       |
        +--> Can create another connection? -- Yes --> create + borrow
        |
        +--> No slots left and none idle --> wait (pending)
                                                |
                      connection returned ------+
                          |                     |
                          v                     +--> exceeds connectionTimeout
                      SQL usage                       --> exception
                          |
                      close() / release
                          |
                          v
                   return to pool (idle)
~~~

A `Connection` **active in the pool** is usually a connection that has been borrowed and not yet returned—it **does not necessarily mean** the database is executing SQL. It could be reading a `ResultSet`, waiting on I/O, holding a transaction, running Java logic, or simply forgotten. When using a pool, `Connection.close()` on a pool-issued handle typically returns the logical resource to the pool; the pool decides when to close the physical connection.

A **connection leak** within this article's scope is when code borrows a connection and fails to return it per lifecycle due to forgetting close/release, exception paths skipping cleanup, or retaining the resource indefinitely. A connection returned after 40 seconds in a valid transaction is not necessarily leaked, even though it can exhaust the pool. Conversely, a leak does not always cause immediate errors; remaining idle pool connections can mask the issue until enough accumulate.

Distinguish three time layers:

1. **Acquire/wait time:** how long calling `getConnection()` had to wait for a usable connection.
2. **Usage/borrow time:** from successfully borrowing a connection until returning it to the pool; this duration can exceed SQL execution time.
3. **SQL execution / transaction duration:** how long the database executes statements or the transaction stays active. These intervals can overlap yet are **not equal**.

For example: a request spends 100 ms executing SQL, then calls an external API taking 15 seconds inside the same transaction, only releasing the connection afterward. The usage metric can be near 15 seconds even though the database was busy for only 100 ms. That is holding a connection long due to transaction boundaries, different in root cause from forgetting `close` altogether.

## 3. Recognizing Four Symptom Groups

| Phenomenon | What Appears in the Pool | Questions to Check |
| --- | --- | --- |
| **True leak:** connection never returned | Active accumulates and does not return to baseline after load drops; idle drops, potentially leading to pending/timeouts | Is code missing cleanup? Which thread or bean holds the handle? |
| **Holding connections too long:** long transactions, slow stream reads, waiting on other services | Active tracks request/transaction duration; may eventually return after a long time | Is SQL actually slow, or is code holding transactions across I/O? |
| **Legitimate demand exceeds pool capacity** | Active nears max as QPS/concurrency rises; pending rises; recovers when load drops | Are pool/DB sized for current capacity and query duration? |
| **DB/driver/network cannot create connections** | Total may stay below max, pending/timeouts rise, usually with a connection root cause | Is DB reachable; what about session limits, TLS, credentials, or driver? |

These are **patterns**, not automatic decision rules. A system can suffer both a leak and slow queries simultaneously; a saturated pool alone does not pinpoint the cause.

### Two foundational questions

- **How long is the connection borrowed?** If returned after the transaction ends, examine transaction duration and execution flow. If never returned, inspect where it is borrowed and cleanup branches.
- **When load drops, does active drop too?** Examine multiple samples after requests/jobs finish. A single snapshot is insufficient for conclusions.

## 4. Reading Error Logs by Layer, Avoiding Guesses from Exception Names

### 4.1. HikariCP reports failing to obtain a connection

Illustrative log (numbers invented for this article, not collected from a live system):

~~~text
java.sql.SQLTransientConnectionException:
  LearningPool - Connection is not available, request timed out after 5002ms
  (total=8, active=8, idle=0, waiting=6)
~~~

Interpretation:

- `Connection is not available`: the caller could not be granted a connection before the borrow wait timed out.
- `request timed out after 5002ms`: wait time for borrowing is roughly `connectionTimeout`, **not a SQL query timeout**.
- `total=8`: the pool currently holds eight connections; `active=8`: all eight are borrowed; `idle=0`: none are available; `waiting=6`: six threads were waiting when logged.
- This log proves **pool exhaustion at that instant**; it does not yet prove who leaked connections.

If `total < maximumPoolSize` and timeouts still occur, check whether the pool is trying to create connections, whether the database rejects them, whether the driver has auth/TLS errors, or whether connection setup takes too long. Hikari can wrap root causes in the exception chain; read the full `Caused by`, `SQLException.getNextException()`, and driver/database logs.

### 4.2. HikariCP detects potential leaks by hold duration

When `leakDetectionThreshold` is enabled, Hikari schedules a warning if a connection stays borrowed past the threshold. Illustrative log with stack abbreviated:

~~~text
WARN  com.zaxxer.hikari.pool.ProxyLeakTask -
  Connection leak detection triggered for ... on thread http-nio-8080-exec-4,
  stack trace follows
java.lang.Exception: Apparent connection leak detected
    at com.zaxxer.hikari.HikariDataSource.getConnection(...)
    at com.example.data.ReportRepository.loadReport(ReportRepository.java:42)
    at com.example.service.ReportService.generate(ReportService.java:28)
~~~

Read **the stack trace meaning accurately**:

- The stack typically captures **the call path when the connection was borrowed** (checkout/acquisition site), not necessarily where it is currently sitting when the warning fires.
- `ReportRepository.java:42` is the starting clue for finding the acquisition path. Follow every `return`, `throw`, `catch`, and `finally` branch after that line.
- An *apparent leak* warning is a **suspicion due to exceeding the hold threshold**, not proof of a permanent leak. A 30-second report job may still release cleanly upon completion.

If the connection is returned after Hikari logged the warning, an INFO log may appear such as:

~~~text
Previously reported leaked connection ... was returned to the pool (unleaked)
~~~

This message proves the connection **was returned** and the earlier warning may have been a long hold rather than a permanently lost handle at return time. It does not prove long holds are acceptable. Conversely, not seeing an "unleaked" log **does not automatically** confirm a leak: logs may be filtered, the app may have stopped before returning, or the connection may still be held when observation ended.

### 4.3. Errors easily confused with leaks

| Error Line / Symptom | What It Directly Tells You | What Else to Check |
| --- | --- | --- |
| `SQLTransientConnectionException` during getConnection | Could not acquire a connection in time | Active/pending/total, load, connection creation errors |
| `SQLTimeoutException` from driver/SQL statement | A time-limited JDBC operation exceeded its limit, depending on driver | SQL, locks, network, query timeout; do not jump to pool leak |
| `Connection reset`, `Broken pipe`, SQLState class `08` | Communication/driver failure on connection | DB/network, server-side connection drops, pool validation |
| Database `too many connections` | Database connection limit reached | Total connections across **all** instances/pools and other processes |
| DB lock/deadlock/lock timeout | Transaction/lock contention | Open transactions, queries, and lock history |
| Spring `CannotGetJdbcConnectionException` | Spring could not obtain a JDBC connection | Pool/driver root cause; Spring may wrap underlying exceptions |

Distinguish **errors during connection acquisition**, **errors during SQL execution**, and **errors during connection return/close**. The top Spring stack frame may be a wrapper; the root cause sits deeper.

## 5. Pool Metrics That Must Be Read Together

In Spring Boot with Actuator and Micrometer, supported DataSources typically expose meters prefixed `jdbc.connections.*`; HikariCP also exposes `hikaricp.connections.*`. In Spring Framework apps without Boot, corresponding monitoring must be configured manually. Meter names and presence depend on version, registry, pool implementation, and whether the DataSource is instrumented.

| Typical Meter Name (Actuator) | Type | Meaning | Interpretation Hint |
| --- | --- | --- | --- |
| `jdbc.connections.active` / `hikaricp.connections.active` | Gauge | Connections currently borrowed | Does it drop after demand ends? |
| `jdbc.connections.idle` / `hikaricp.connections.idle` | Gauge | Idle connections in the pool | Idle at 0 under high load does not by itself mean a leak |
| `hikaricp.connections` | Gauge | Current total connections in the Hikari pool | Not a cumulative count of all ever created |
| `jdbc.connections.max` / `hikaricp.connections.max` | Gauge | Max connections the pool is allowed to keep | Pool limit, not the database's global limit |
| `jdbc.connections.min` / `hikaricp.connections.min` | Gauge | Minimum idle/pool maintenance target | Useful for understanding idle baseline |
| `hikaricp.connections.pending` | Gauge | Threads waiting to borrow a connection | Rising pending signals contention pressure |
| `hikaricp.connections.timeout` | Counter | Cumulative borrow timeouts | Watch rate of increase; counters only go up |
| `hikaricp.connections.acquire` | Timer | Time to grant a connection to caller | Rises with contention or slow connection creation |
| `hikaricp.connections.usage` | Timer | How long a connection is held before return | Helps spot transactions/requests holding resources long |
| `hikaricp.connections.creation` | Timer | Time to establish a new physical connection | Rises when DB/driver/network setup is slow |

A **Gauge** is a state snapshot at sampling time; a **Counter** is an accumulated total incremented on events (resetting on process restart); a **Timer** aggregates durations and counts. Do not read `timeout=50` as "50 threads currently waiting": it is the cumulative count of past timeouts, not current state.

### Relationship among active, idle, total, max

Typically in a stable snapshot, `active + idle ≈ total` and `total ≤ max`. The `≈` is intentional: metrics are often sampled slightly apart without a shared atomic snapshot while the pool continuously borrows, returns, creates, and retires connections. Sums can skew slightly during rapid changes.

**Active is not QPS:** high QPS/requests-per-second with queries taking a few milliseconds can keep active low. Conversely, just a few long-running transactions can occupy the entire pool. Active counts borrowed connections even if no query is executing on them.

**Pending is not all waiting requests:** pending only counts callers actively waiting on this pool for a connection. Requests queued in a thread pool, queue, HTTP server, or upstream before calling `getConnection()` are not included in that number.

**Usage timer has evidence lag:** duration is recorded when a connection is returned. A connection held indefinitely may not yet have contributed a completed usage sample. Hence, a low usage timer **does not rule out an ongoing leak**. Read it alongside active, pending, and leak-detection logs.

### Tags and multiple pools

An application can have multiple `DataSource`s: primary, reporting, read-only, batch, tenant-specific. Aggregating metrics across all pools can hide one exhausted pool. In Spring Boot, `jdbc.connections.*` usually tags by DataSource bean name; Hikari-specific metrics tag by pool name. Always filter by the exact **service, instance, pool, and environment**. If pods/instances share the same pool name, add instance labels in your monitoring system.

## 6. Inspecting Metrics with Spring Boot Actuator

Example configuration **for a controlled diagnostic environment** in Spring Boot using HikariCP:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: LearningPool
      maximum-pool-size: 8
      connection-timeout: 5000
      leak-detection-threshold: 20000

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
~~~

- `maximum-pool-size: 8` caps pool connections; this is **only an example number**, not a production recommendation.
- `connection-timeout: 5000` (milliseconds) limits waiting for a connection from the pool.
- `leak-detection-threshold: 20000` (milliseconds) makes Hikari log a warning if a connection is borrowed for more than ~20 seconds.
- `management.endpoints.web.exposure.include` exposes the metrics endpoint over HTTP; access must be restricted via security and network controls in real apps.

Per HikariCP, a leak-detection threshold of `0` disables it (default); the lowest accepted value to enable it is `2000` ms. The threshold **does not close connections**, it only warns. Choose a threshold based on valid hold times in your system (e.g., higher than normal transactions yet low enough to catch incidents), rather than using 2000 ms for every app. Setting it too low floods logs with false positives from valid long transactions.

If the app has `spring-boot-starter-actuator` and proper metric binders, test within an admin network:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.pending
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.timeout
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.usage
curl -s http://localhost:8080/actuator/metrics/jdbc.connections.active
~~~

These URLs are **query examples**, not a guarantee every application exposes all meters. Inspect the actual list in `/actuator/metrics` first; some meters will not appear depending on pool/provider or instrumentation settings. The metrics endpoint uses Micrometer meter names; when exported to Prometheus, names may be normalized (e.g., dots to underscores and suffixes on counters), so do not mechanically copy HTTP endpoint names into PromQL.

If the endpoint covers multiple pools, filter by tag after checking `availableTags` in the response. Example tag query:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/hikaricp.connections.active?tag=pool:LearningPool"
~~~

The `pool` tag name is what Hikari/Micrometer commonly uses; verify actual tags in your environment instead of guessing.

### Example reading a metrics response

An output **illustrating structure**, with non-production values:

~~~json
{
  "name": "hikaricp.connections.active",
  "measurements": [
    {"statistic": "VALUE", "value": 8.0}
  ],
  "availableTags": [
    {"tag": "pool", "values": ["LearningPool"]}
  ]
}
~~~

What can be concluded with certainty: at the moment of measurement, the pool matching the tag has about eight active connections. To determine whether a leak exists, you must still correlate `max`, `pending`, load, and prior/subsequent snapshots. If a meter aggregates multiple pools/instances, filter by tags before comparing against a single pool's `maximumPoolSize`.

### Collect metrics over time

Actuator `/metrics` returns point-in-time state. To spot accumulating leaks, collect time series with a registry/monitoring system such as Prometheus, Grafana, Datadog, or equivalent; monitor at least:

- `active` and `idle` over time, alongside the `max` line of **the exact pool**.
- `pending` and the rate of increase of the `timeout` counter.
- Acquire/usage duration percentiles (p95/p99 if distribution stats are enabled) and total usage counts.
- QPS, in-flight requests, HTTP durations, transaction durations, and concurrent jobs.
- CPU, thread pools, DB locks/waits/query durations, DB session counts, network/connection creation errors.

There is no universal "active ≥ 80% = leak" threshold for every system. Observe **persistence**, **baseline under low load**, and **correlation/divergence** with request traffic. A pool intentionally sized close to utilization can run at high active and still be healthy if pending and timeouts do not climb.

## 7. Analyzing Trends: One Snapshot, Multiple Possible Conclusions

Assume each scenario uses a pool with `max=8`. The numbers below **are learning scenarios**, not real production logs/metrics.

### Scenario A: Load spikes then recovers

| Time | In-flight requests | Active | Idle | Pending | Timeout counter | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 09:00 | 1 | 1 | 7 | 0 | 0 | Baseline |
| 09:05 | 15 | 8 | 0 | 5 | 0 | High load, pool hits max |
| 09:10 | 4 | 4 | 4 | 0 | 2 | Timeouts occurred during saturation |
| 09:15 | 0 | 0 | 8 | 0 | 2 | Active returns to 0 |

Reasonable conclusion: **pool saturation occurred during the peak**, with no strong signal of connections held after work ended. The timeout counter stays at 2 because it is cumulative. Continue reviewing load capacity, SQL/transaction durations, and pool sizing.

### Scenario B: Load drops while active stays flat

| Time | In-flight requests | Active | Idle | Pending | Timeout counter | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 10:00 | 1 | 1 | 7 | 0 | 0 | Baseline |
| 10:05 | 12 | 8 | 0 | 4 | 0 | Pool hits max |
| 10:10 | 0 | 8 | 0 | 0 | 2 | Observed load stopped, active has not dropped |
| 10:15 | 0 | 8 | 0 | 0 | 2 | Active remains held |

This is a **signal worth investigating**: why are eight connections still active when observed requests are 0? Check scheduled jobs, async workers, in-flight event consumers, long transactions, and borrower stacks. Never conclude a leak solely from HTTP requests: background tasks excluded from HTTP in-flight counts can legitimately use connections.

Once all load sources are accounted for and you wait longer than normal transaction durations, if active still fails to return to baseline, the leak hypothesis strengthens. If checkout logs point to the same call site with no return evidence, finding the root cause is much more likely.

### Scenario C: Total below max yet timeouts still occur

For example, `max=16, total=3, active=3, idle=0, pending=12`. This is **not the same** as eight connections being held in a pool of max eight. The pool lacks connections, potentially because it **cannot create more** (DB limits, network, TLS, authentication, driver) or connection establishment is too slow. Read connection-creation logs, `SQLException` root causes, and database state before editing cleanup code.

## 8. Standalone Runnable Java 17+ Example: Reading Metric Timelines

The following example **connects to no database**; it simulates four snapshots to practice spotting *suspicious signals*. Save as `PoolSignalDemo.java`:

~~~java
import java.util.List;

public class PoolSignalDemo {
    record Snapshot(
            String time,
            int inFlight,
            int active,
            int idle,
            int max,
            int pending,
            long timeouts
    ) {}

    public static void main(String[] args) {
        List<Snapshot> samples = List.of(
                new Snapshot("10:00", 1, 1, 7, 8, 0, 0),
                new Snapshot("10:05", 12, 8, 0, 8, 4, 0),
                new Snapshot("10:10", 0, 8, 0, 8, 0, 2),
                new Snapshot("10:15", 0, 8, 0, 8, 0, 2)
        );

        for (Snapshot s : samples) {
            System.out.printf(
                    "%s inFlight=%d active=%d/%d idle=%d pending=%d timeouts=%d%n",
                    s.time(), s.inFlight(), s.active(), s.max(),
                    s.idle(), s.pending(), s.timeouts()
            );
        }

        Snapshot a = samples.get(2);
        Snapshot b = samples.get(3);
        boolean suspicious =
                a.inFlight() == 0 && b.inFlight() == 0
                && a.active() == a.max()
                && b.active() == b.max();

        System.out.println(suspicious
                ? "SUSPECT: inspect borrowers and long transactions"
                : "INCONCLUSIVE: continue observing");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 PoolSignalDemo.java
java PoolSignalDemo
~~~

Exact stdout:

~~~text
10:00 inFlight=1 active=1/8 idle=7 pending=0 timeouts=0
10:05 inFlight=12 active=8/8 idle=0 pending=4 timeouts=0
10:10 inFlight=0 active=8/8 idle=0 pending=0 timeouts=2
10:15 inFlight=0 active=8/8 idle=0 pending=0 timeouts=2
SUSPECT: inspect borrowers and long transactions
~~~

This is merely a **learning heuristic**. The program lacks information on background jobs, thread owners, or transaction durations, so it prints `SUSPECT` to prompt investigation. Production tooling needs real-time data and additional signals; never automatically restart servers or close connections from a naive expression like this.

## 9. Using Leak Detection Properly with HikariCP

`leakDetectionThreshold` emits a warning after a connection stays checked out beyond a threshold duration. Example in Spring Boot:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: LearningPool
      leak-detection-threshold: 20000
~~~

In a non-Spring Boot environment, a `HikariConfig` can be configured directly:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:h2:mem:training");
config.setUsername("sa");
config.setPassword("");
config.setPoolName("LearningPool");
config.setLeakDetectionThreshold(20_000L);
HikariDataSource dataSource = new HikariDataSource(config);
~~~

This snippet is an **integration illustration** requiring HikariCP and H2 JDBC driver dependencies; `HikariDataSource` must be closed when the application owns the pool lifecycle. It is not a standalone Java file. If the environment already provides a pooled `DataSource` (e.g., JNDI), do not create a second Hikari pool just to turn on leak detection; use the container-managed pool's diagnostics instead.

The **20-second threshold** is only an example. Choose based on the distribution of valid borrow/transaction durations:

1. Observe normal usage under real load and find p95/p99 or an appropriate tail percentile.
2. Pick a threshold above common valid cases yet low enough to catch risky long holds.
3. Enable during diagnostic windows, monitoring warning frequency and log impact.
4. Classify each stack, cross-check `unleaked` logs and metrics; modify code only after identifying the hold path.
5. Adjust or keep config per operational policy once done; avoid setting thresholds too low and causing floods of false alarms.

**Distinguish clearly:** `connectionTimeout` limits *waiting to borrow* a connection; `leakDetectionThreshold` checks *already borrowed and not yet returned* duration. `maxLifetime`/`idleTimeout` govern pool connection lifecycle under specific conditions—they are **not mechanisms to immediately reclaim a connection held by the application**. Raising `maxLifetime` or lowering `idleTimeout` generally does not fix code that forgot to close.

### Reading checkout stacks responsibly

A stack trace may point into `JdbcTemplate` or framework wrappers before reaching an application class. Look for the **first frame belonging to your business package** and trace callbacks, streams, transactions, and exception branches. If multiple warnings share the same call site, it is a priority investigation target, though not guaranteed that all warnings share one root cause. Correlate with trace/span/request IDs and timestamps, avoiding logging secrets or full sensitive query details.

## 10. Verifying via JMX When Not Using Actuator

HikariCP can expose MBeans when configured with `registerMbeans=true`. Pool MXBean attributes typically include:

- `ActiveConnections`: borrowed connections.
- `IdleConnections`: idle connections.
- `TotalConnections`: total connections currently held by the pool.
- `ThreadsAwaitingConnection`: threads waiting to borrow.

Example configuration for an app owning the Hikari pool:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: LearningPool
      register-mbeans: true
~~~

In JMX tools like JConsole/JMC, locate the MBean by pool name. Values are read at slightly different instants so sums may not match exactly during rapid pool changes. JMX also exposes pool management operations; restrict access and avoid running connection-intervention operations during investigation unless following an explicit operational plan.

If reading from Java (illustrative snippet in an app that already has a `HikariDataSource` bean):

~~~java
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

HikariPoolMXBean pool = hikariDataSource.getHikariPoolMXBean();
if (pool != null) {
    System.out.println("active=" + pool.getActiveConnections());
    System.out.println("idle=" + pool.getIdleConnections());
    System.out.println("waiting=" + pool.getThreadsAwaitingConnection());
}
~~~

This code depends on HikariCP and an injected `hikariDataSource` variable; it is not a standalone Java program. Periodic sampling correlated with requests/transactions is required for meaningful diagnostics. MBeans help **observe**, yet do not tell you which Java object holds each individual connection.

## 11. Tracing from Symptoms Back to Source Code

When logs point to a connection borrow site, inspect all control-flow paths, especially:

- Inside `try`, is there an early `return` or thrown exception before `close()`?
- Were `ResultSet`, `PreparedStatement`, `CallableStatement`, or `Connection` opened outside the expected lifecycle?
- Does an object, iterator, or stream keep a `ResultSet` alive after the method returns?
- Is an async callback, scheduled job, event listener, or thread local holding a connection/transaction?
- Are HTTP calls, file I/O, sleeps, or long CPU computations running inside a transaction after acquiring a connection?
- Does read/write logic use Spring transaction-aware access or acquire connections through a separate path?

### 11.1. Incorrect pattern: raw JDBC opens a connection and forgets to close

This is an **anti-example**; do not use it:

~~~java
// Anti-example: if query or mapping fails, the connection can remain held.
Connection connection = dataSource.getConnection();
PreparedStatement statement =
        connection.prepareStatement("SELECT name FROM customer WHERE id = ?");
statement.setLong(1, customerId);
ResultSet rs = statement.executeQuery();
if (!rs.next()) {
    return null; // Early return: does not close result set, statement, connection.
}
return rs.getString("name"); // Also fails to close resources.
~~~

Each request hitting this code can leave behind a borrowed connection. Once accumulated requests reach `maximumPoolSize`, new requests must wait and may time out. Code throwing `SQLException` before cleanup makes the bug even harder to notice if only the happy path is tested.

### 11.2. Correct pattern: try-with-resources for all three resources

This method can live in a Java class with a `DataSource dataSource` field; it requires a matching JDBC driver/database to run:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class CustomerReader {
    private final DataSource dataSource;

    public CustomerReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findName(long customerId) throws SQLException {
        String sql = "SELECT name FROM customer WHERE id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);
            try (ResultSet rs = statement.executeQuery()) {
                return rs.next() ? rs.getString("name") : null;
            }
        }
    }
}
~~~

`try-with-resources` closes in reverse creation order: `ResultSet` → `PreparedStatement` → `Connection`; even with `return` or exceptions, all `close()` calls run. With a pooled DataSource, `close()` on the handle is precisely the **return to pool** operation. This is the leak-prevention rule for direct JDBC. If a connection participates in a Spring-managed transaction, use the appropriate acquire/release path (see below) rather than arbitrarily closing a resource owned by the transaction manager.

**Do not use `finally { connection.close(); }` while ignoring secondary failures when `connection` might not even be assigned; `try-with-resources` expresses ownership far more clearly.** Java preserves the primary exception and attaches close failures as *suppressed exceptions*, helpful for investigation.

### 11.3. With Spring JDBC, let JdbcTemplate manage resources

Repository pattern inside a Spring application context that already has a `JdbcTemplate` bean:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerCountRepository {
    private final JdbcTemplate jdbc;

    public CustomerCountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int countCustomers() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer", Integer.class
        );
        return count == null ? 0 : count;
    }
}
~~~

`JdbcTemplate` manages acquiring and returning JDBC resources through Spring infrastructure. Inside an active transaction, it uses `DataSourceUtils` to reuse the transaction-bound connection and lets the transaction manager decide the final return timing. Therefore, **active does not drop immediately after every JdbcTemplate call finishes** while the service still holds an open transaction.

If using raw JDBC inside a Spring-managed transaction, consider `DataSourceUtils.getConnection(dataSource)` and `DataSourceUtils.releaseConnection(connection, dataSource)`, or `TransactionAwareDataSourceProxy` when integrating legacy code; never mix direct `dataSource.getConnection()` with transaction-bound connections and assume all calls share one transaction. Prefer Spring abstractions whenever possible.

### 11.4. Result streams must be closed

`JdbcTemplate.queryForStream(...)` returns a `Stream<T>` backed by JDBC resources. Reading all data **does not replace** closing the stream. Example in a class with `JdbcTemplate jdbc`:

~~~java
import java.util.stream.Stream;

public long countPositiveIds() {
    try (Stream<Long> ids = jdbc.queryForStream(
            "SELECT id FROM customer",
            (rs, rowNum) -> rs.getLong("id"))) {
        return ids.filter(id -> id > 0).count();
    }
}
~~~

Even though the `count()` consumer completes, `try-with-resources` is still required to invoke `Stream.close()` and release the JDBC resources owned by the stream. Never return a live stream to a controller and forget to close it after serialization. JPA/Hibernate stream APIs also carry lifecycle requirements; check the provider's documentation and real transaction context.

### 11.5. Holding a transaction too wide

Example of what a service is doing:

~~~text
@Transactional
  query database (50 ms)
  call external HTTP API (15 s)
  write database (50 ms)
  commit / release
~~~

In many configurations, the connection is borrowed at the first operation and held until the transaction ends. Leak detection can log a warning after 10 seconds even though the code eventually returns the connection. To reduce pool occupancy, evaluate whether **network I/O can be separated from the transaction** safely in terms of business logic and data consistency. Never move transaction boundaries arbitrarily if business atomicity rules require the writes in the same transaction.

With Spring AOP, `@Transactional` also depends on proxy mechanisms, self-invocation within the same bean, the transaction manager, propagation, and async execution paths; verify the transaction is actually active rather than inferring solely from the annotation.

## 12. Using Database-Side Data to Rule Out Causes

Pool metrics describe connections on the **application** side; the database side shows active sessions, transactions, and running SQL. They complement each other without a perfect one-to-one mapping: a driver/pool may open physical connections on its own schedule, and the database also receives connections from other applications.

With PostgreSQL, inspect sessions per granted permissions:

~~~sql
SELECT pid, usename, application_name, state,
       now() - xact_start AS transaction_age,
       now() - query_start AS query_age,
       wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

When reading:

- `state='active'` in `pg_stat_activity` means PostgreSQL is actively executing a query for that backend. It is **not synonymous** with Hikari `active` (borrowed on the application side).
- `idle in transaction` in PostgreSQL can indicate a transaction left open without running SQL, requiring finding whoever holds the transaction; it can cause locks/bloat and consume resources.
- `transaction_age` is the transaction age when `xact_start` is non-NULL; `query_age` is the age since `query_start` was recorded, which cannot blindly be assumed to mean active query duration across all states.
- `wait_event_type` and `wait_event` help distinguish lock waits from I/O waits, if provided by the PostgreSQL version and permitted for the user.

Database privilege restrictions may hide session/query details of other users. Never run bulk session-termination commands just because many sessions appear; identify the owner and transaction impact first. For MySQL, SQL Server, Oracle, or other databases, use equivalent monitoring views per that DBMS's documentation.

Also check **the sum of pools across instances**: 10 pods, each with `max=20`, can configure up to ~200 connections, not counting other workers/services. A database "too many connections" error does not imply individual pools are leaking.

## 13. End-to-End Incident Investigation Process

### Step 1 — Scope and preserve evidence

Record the time window, environment, service/instance/pool, deployment version, affected requests/jobs, and metrics before and after errors began. Collect full exceptions, pool logs, root causes, and trace IDs if available. With multiple datasources, identify **which pool** ran out of connections.

### Step 2 — Identify which phase failed

If errors occur at `getConnection()`, examine active/idle/total/pending and connection creation causes. If a connection was acquired yet queries time out, focus on SQL execution, locks, and transactions. If no errors appear yet active never returns to baseline, investigate long-held connections/leaks.

### Step 3 — Compare baseline, peak, and recovery

On **the same instance/pool**, plot active, pending, timeout counters alongside request rate/in-flight and processing times. Observe at least long enough for legitimate transactions to finish; avoid applying one fixed duration rule to every system.

If active rises with load and then drops: lean toward capacity or latency. If active climbs across multiple load cycles and never returns to baseline: lean toward leaks or non-terminating background tasks/transactions.

### Step 4 — Match leak logs with borrower stacks

If leak detection is enabled, collect checkout-time stacks and filter by application classes and time range. Find where the connection opened, where it should have closed, return/exception branches, and callbacks/streams. Check whether "unleaked" logs appear. If many warnings point to the same code path, clarify whether it is one very slow request or many connections genuinely unreturned.

### Step 5 — Verify DB and threads

Inspect sessions, transaction ages, lock waits, and slow queries on the database; correlate with requests/traces and JVM thread dumps when appropriate. A thread dump shows where threads stood at capture time; it does not always identify connection ownership. Add transaction/service span/time logging and connection checkout logs if needed.

### Step 6 — Fix the smallest root cause

Examples:

- Wrap JDBC Connection/Statement/ResultSet in `try-with-resources`.
- Use `JdbcTemplate` to reduce manual resource management code.
- Ensure JDBC-backed streams/cursors/iterators are closed after reading.
- Shrink transactions that do not need to span network calls; bound query/transaction durations and check cancellation handling.
- Fix slow queries, lock contention, or DB limits if the cause is not a leak.
- With multiple `DataSource`s, verify the exact transaction manager and pool in use.

### Step 7 — Test after fixing

Replay the reproducing load with the same inputs, concurrency, and pool size, observing long enough. Compare:

1. Does active return to baseline after all tasks finish?
2. Does pending clear, and does the timeout counter stop rising outside overload spikes?
3. Do borrow/usage times return to expected ranges?
4. Do leak warnings at the old call site stop appearing, or do "unleaked" logs clarify long-hold warnings?
5. Are any abnormal lingering transactions/sessions left on the DB?
6. Did the fix introduce any business bugs or alter transaction semantics?

Never treat "no exceptions for 30 seconds" as sufficient QA if an accumulating leak takes hundreds of requests to surface.

## 14. Controlled Test to Observe the Difference

A useful exercise in an isolated test environment: configure a small Hikari pool (e.g., 2 connections), create JDBC operations with and without `try-with-resources`, invoke them sequentially, and watch active/idle/pending. **Only run the intentional unclosed-connection case in an isolated test environment**, as it exhausts the pool and breaks other tasks.

Run two separate passes, creating a fresh pool for each so no state carries over from the broken example:

- **Pass A (intentional bug):** Borrow a connection and do not return it. After two successes, the next borrow may wait and time out depending on pool and test setup. Active does not return to baseline.
- **Pass B (correct):** Every borrow sits inside `try-with-resources`; after the method exits, active returns to the expected level when no other transactions exist.
- Read timeout counters and event logs; figures can vary with sampling timing. Even with in-memory H2, the pool still needs a JDBC driver and matching test schema.

Never use `System.gc()` or rely on `finalize()` to fix leaks; resource lifecycles must be managed explicitly. Connection pools may reclaim some resources on errors, yet that does not guarantee connections retained by application code will return on time.

## 15. Practical Alerting and Dashboard Design

An investigation dashboard should align charts on the same timeline:

| Group | Recommended Charts | Reason |
| --- | --- | --- |
| Pool availability | active, idle, total, max | Shows pool saturation and recovery |
| Contention | pending, acquire latency | Shows threads waiting to borrow |
| Failure | timeout counter rate, `getConnection()` error count | Shows user-request impact |
| Duration | usage time, transaction time, query time | Distinguishes held connections from slow SQL |
| Traffic | request rate, concurrency, batch throughput | Correlates with actual demand |
| DB | sessions, connection errors, lock waits, slow queries | Identifies DB-side bottlenecks |

Several **alert signals worth configuring against baselines/SLOs**:

- Pending stays above 0 across multiple scrape intervals while acquire latency rises.
- Timeout counter rate rises above 0 and requests begin failing.
- Active stays near max long **after all related workload sources have finished**.
- Tail usage duration rises noticeably after a deployment, especially on a specific endpoint/job.
- Repeated leak-detection warnings from the same code path, with or without connection return events.

Do not page solely on "idle=0" for 1 second or "active=8" when `max=8`: those can reflect a normal traffic spike. Use time windows, combined conditions, environment separation, and avoid alert storms.

With Prometheus, treat gauges as point-in-time values and use rate/increase on timeout counters after checking the actual exported metric names (which often differ from Actuator names). Never subtract counters across a restart without accounting for counter resets.

## 16. Common Misconceptions When Concluding

1. **"High active = leak."** Insufficient: it can be workload, long transactions, or slow queries. Compare against workload and recovery.
2. **"Timeouts appeared = code forgot to close."** Timeouts mean borrowing didn't succeed in time; the DB failing to create connections causes this too.
3. **"A leak warning definitely means a leak."** The threshold checks hold duration; an unleaked return log may follow later.
4. **"Increasing maximumPoolSize fixes the root cause."** If connections aren't returned, a bigger pool only delays exhaustion and can overload the DB.
5. **"connectionTimeout is the SELECT query timeout."** No: it is the pool borrow wait time; query/statement timeouts are configured at a different layer.
6. **"Connection.close() closes the socket every time."** With a pool, it usually returns the handle for reuse; calling close is still mandatory.
7. **"Usage timer is low so there is no leak."** An unreturned connection may not have produced a completed usage sample yet.
8. **"With @Transactional, connections cannot be held long."** Long transactions are often the exact reason for long borrows; inspect scope, queries, and I/O.
9. **"Calling dataSource.getConnection() in raw JDBC automatically joins Spring transactions."** Spring JDBC recommends `DataSourceUtils`/`JdbcTemplate` when a transaction-bound connection is needed.
10. **"Pool metrics match DB sessions 1:1."** Systems have multiple pools/instances/other connections, plus idle handling, reconnects, and instrumentation differences.
11. **"Closing ResultSet guarantees the Connection was returned."** Close each resource per ownership; ResultSet does not replace closing Connection.
12. **"No warnings means no leaks."** Leak detection may be disabled, threshold too high, filtered by log level, or the issue may differ from that model.

## 17. Self-Check Questions

**Question 1.** Pool shows `max=10, active=10, idle=0, pending=3`. Is there enough evidence to conclude a leak?  
**Answer:** Not yet. It only proves the pool is saturated at that sample. Compare over time with load, transactions/SQL, checkout logs, and connection creation capacity.

**Question 2.** The timeout counter rises from 4 to 9 within the same process. How many new timeouts occurred in that interval?  
**Answer:** 5, assuming no counter reset and no change in collection.

**Question 3.** A leak warning appears at second 20, and at second 27 "returned to the pool (unleaked)" appears. What is proven?  
**Answer:** The connection was returned after exceeding the threshold. You cannot call it a permanent leak; investigate why it was held for 27 seconds and its impact on the pool.

**Question 4.** `active` stays equal to `max` after HTTP requests drop to 0. Why can't you declare a leak with certainty yet?  
**Answer:** There may still be scheduled jobs, async consumers, transactions waiting on I/O, background requests, or load metrics missing some borrowers.

**Question 5.** Does raising `maximumPoolSize` from 10 to 50 fix code that forgot to call `close()`?  
**Answer:** No. It only delays when the pool runs dry and may increase database pressure. You must fix the resource release path.

**Question 6.** With `JdbcTemplate.queryForStream(...)`, why is `try-with-resources` needed around the Stream?  
**Answer:** The stream is backed by ResultSet/Statement/Connection and requires calling close to release JDBC resources, even after consumption finishes.

**Question 7.** Database logs "too many connections" while each Hikari pool has `active=5` and `max=10`. What should you check?  
**Answer:** Pod/instance/pool counts, total connections from all other apps, DB sessions, and connection creation failures. Never reason from a single pool alone.

**Question 8.** Hikari `hikaricp.connections.usage` increases while SQL p95 is nearly unchanged. What hypothesis makes sense?  
**Answer:** Connections are being held outside SQL time—such as transactions containing HTTP calls, data processing, or application logic waits; correlate transaction spans and borrower logs.

## 18. Summary

**Connection leaks are a lifecycle issue of borrowed resources.** Timeout logs only tell you when the pool could not meet demand; leak-detection warnings provide the borrow site and hold duration past threshold; active/idle/pending/usage/timeout metrics describe pool health over time. Reliable conclusions combine all three with request, transaction, and database state, then verify with before/after testing of the fix.

Keeping connections as short-lived as business logic allows, returning ownership properly via `try-with-resources` or Spring mechanisms, closing streams/cursors cleanly, and observing metrics per pool distinguishes true leaks from performance bottlenecks.

### References

- [HikariCP README — configuration (connectionTimeout, maximumPoolSize, leakDetectionThreshold)](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): meaning of borrow timeout, pool cap, and leak warning threshold.
- [HikariCP — ProxyLeakTask](https://github.com/brettwooldridge/HikariCP/blob/dev/src/main/java/com/zaxxer/hikari/pool/ProxyLeakTask.java): mechanism logging borrower stacks and "unleaked" connection return logs.
- [HikariCP — JMX Monitoring and Management](https://github.com/brettwooldridge/HikariCP/wiki/MBean-%28JMX%29-Monitoring-and-Management): active/idle/total/waiting metrics and snapshot notes.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `jdbc.connections.*` meters, Hikari metrics, Actuator queries.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, `JdbcTemplate`, transaction-aware connections.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JDBC resources and `JdbcTemplate`.
- [Spring Framework — JdbcTemplate.queryForStream JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): streams must be closed after use.