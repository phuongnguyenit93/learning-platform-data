# Monitoring DataSource and HikariCP Connection Pools

## 1. Why Look at the Connection Pool?

A slow HTTP request is not necessarily running a slow SQL statement. It might not yet have obtained a connection to send SQL to the database. Conversely, the application might still hold a connection while waiting on another service, even though the database is barely doing any work.

A connection pool holds and reuses physical connections to the database. Instead of creating a new connection for every operation, application code borrows a connection, uses it, and returns it. Monitoring the pool helps answer three distinct questions:

- How many connections are currently borrowed, and how many are ready for immediate use?
- How many threads are waiting to borrow, and how long do they wait?
- Are creating, borrowing, or holding connections causing errors or slowing the application down?

In Spring Boot, `DataSource` is the interface supplying JDBC connections. HikariCP is a pool implementation commonly chosen by Spring Boot when present on the classpath. The two names are not synonymous: a `DataSource` may use HikariCP, another pool, a wrapper, or a routing mechanism.

This lesson uses Spring Boot 3.3.13, Boot-managed Micrometer, and HikariCP 5.1.0. The example runs on Java 21 with source targeting Java 17. Notes about metric names and registration lifecycle apply to this version combination; when using another version, inspect the actual metric list.

## 2. The Model From Borrowing to Returning

`DataSource.getConnection()` is where the application requests a connection. If an idle connection exists, the pool can hand it to the calling thread. If none is idle, the pool can create one within configured bounds or force the caller to wait. If one cannot be granted before the borrow timeout, the borrow fails.

A typical usage cycle:

```java
try (Connection connection = dataSource.getConnection()) {
    // Perform JDBC work requiring the connection.
}
```

This is an illustrative snippet, not a standalone program. On connections handed out by HikariCP, calling `close()` on the connection object normally returns it to the pool for reuse. It does not mean every close immediately destroys the physical connection. The pool can still evict a connection when it breaks or reaches retirement.

In applications using `JdbcTemplate`, JPA, or Spring-managed transactions, the framework handles borrow/return lifecycles according to the corresponding scope. Direct JDBC examples here help visualize pool mechanics; in business logic, keep connection management consistent with your tooling and transactions.

The flow can be pictured as follows:

```text
Application thread
    -> requests to borrow a connection
    -> waits for the pool to supply a connection, if needed
    -> receives the connection
    -> holds the connection to run SQL or perform other work
    -> closes the borrowed connection
    -> pool reclaims or discards the connection
```

Concepts to separate clearly:

| Concept | Meaning | What Cannot Be Inferred Directly |
| --- | --- | --- |
| `active` | Connections checked out of the pool and not yet returned | Not the number of SQL statements currently running |
| `idle` | Connections sitting idle in the pool | Does not prove every subsequent query will succeed |
| `pending` | Threads waiting for the pool to grant a connection | Not the number of queries waiting on database locks |
| `total` | Total connections currently in the pool | Not necessarily equal to the configured maximum |
| `max` | Pool connection limit | Not the measured capacity of the database |
| `min` | Target minimum idle connections | Not the idle count guaranteed available at every instant |

For instance, a thread holding a connection while calling an external API still raises `active`, even with no SQL running. A thread waiting on `getConnection()` raises `pending` before it can even send SQL. A query already inside the database waiting on a lock usually keeps holding its connection, so it can push `active` up and indirectly make later threads wait.

In steady state, total connections generally correspond to active plus idle. However, Gauges are read independently while the pool changes concurrently; do not treat numbers gathered across separate reads as an atomic snapshot or use transient mismatches as proof of a bug.

## 3. Two Metric Groups: Generic JDBC and HikariCP

### 3.1. The `jdbc.connections.*` Group

Spring Boot Actuator provides pool measurement via `DataSourcePoolMetadataProvider`. When matching metadata is available and produces values, generic JDBC Gauges include:

| Micrometer Metric | Meaning |
| --- | --- |
| `jdbc.connections.active` | Number of connections currently borrowed |
| `jdbc.connections.idle` | Number of idle connections |
| `jdbc.connections.max` | Maximum reported by the pool |
| `jdbc.connections.min` | Minimum reported by the pool |

This is a generic observation layer for supported `DataSource`s, not exclusive to HikariCP. Having a `DataSource` bean does not guarantee all four Gauges always exist: it also depends on metadata availability and registration timing.

The identifying tag at this layer is `name`, derived from the `DataSource` bean name. With the default `dataSource` bean in the example, the tag is `name=dataSource`. Do not infer every bean's tag by copying the bean name verbatim: Spring Boot's naming rule can strip a `DataSource` suffix from longer names. Inspect the actual tags.

### 3.2. The `hikaricp.*` Group

HikariCP has its own Micrometer integration. With Spring Boot, you generally do not write custom counters around `getConnection()` calls.

The identifying tag is `pool`. Example setting an explicit name:

```properties
spring.datasource.hikari.pool-name=lessonPool
```

Hikari metrics for this pool then carry `pool=lessonPool`. This is the pool name, neither the JDBC `name` tag nor the database name.

Gauges in HikariCP 5.1.0:

| Micrometer Metric | Observed Value |
| --- | --- |
| `hikaricp.connections` | Current total connections |
| `hikaricp.connections.active` | Number of currently borrowed connections |
| `hikaricp.connections.idle` | Number of idle connections |
| `hikaricp.connections.pending` | Number of threads waiting for a connection |
| `hikaricp.connections.max` | Maximum limit |
| `hikaricp.connections.min` | Minimum idle target |

In HikariCP 5.1.0, the pool statistics backing these Gauges use a cache updated roughly every second. Holding a connection and immediately reading Gauges within a tiny timeframe can therefore still show stale values. The lab example below uses bounded waits to observe state transitions rather than assuming every Gauge read fetches fresh counts.

### 3.3. Three Timers and One Counter

| Metric | Type | What Does It Measure? |
| --- | --- | --- |
| `hikaricp.connections.acquire` | Timer | Wait time to borrow a connection |
| `hikaricp.connections.usage` | Timer | Duration a connection is held after borrowing, recorded upon return |
| `hikaricp.connections.creation` | Timer | Time to create a physical connection |
| `hikaricp.connections.timeout` | Counter | Number of connection borrow timeouts |

A Timer has sample count and total time; depending on the registry, it also has windowed max and configured distribution stats. A Timer is not a single duration figure. When checking Actuator, read both `statistic` and `baseUnit`; when querying from Java directly, request units using `TimeUnit`.

Three very common interpretation mistakes:

1. High `acquire` does not prove SQL is slow. It says obtaining a connection took time; investigate further why the pool could not supply one promptly.
2. High `usage` does not prove all that time was spent executing SQL. Hold duration can also include Java processing, lock waits, external service calls, or overly broad transaction scopes.
3. `creation` does not measure every borrow. Reusing an idle connection does not create a physical connection.

In HikariCP 5.1.0, the borrow-timeout path also records an `acquire` sample. Therefore do not call `acquire.count()` "number of successful borrows" without verifying the implementation. Conversely, a failed attempt that never obtained a connection does not produce a `usage` duration for that caller.

`usage` is recorded when the connection is returned. If a connection is held for a very long time and not yet returned, its accumulating duration has not yet become a completed sample in the Timer. Hence, a normal-looking usage chart is not enough to rule out an abnormally held connection.

## 4. Conditions for Seeing Metrics

In a Spring Boot application using JDBC, you need a pool, Actuator, and an active `MeterRegistry`. Spring Boot can create a `SimpleMeterRegistry` when no other metrics backend is configured; the standalone example below uses this in-memory registry.

Distinguish three actions:

- Registering metrics in `MeterRegistry`.
- Allowing HTTP endpoint access to view metrics.
- Exporting metrics to a time-series storage system.

A metric can already exist in the registry even if the HTTP endpoint is not exposed. Conversely, exposing the endpoint does not create a `DataSource`, start an unused pool, or provide long-term history on its own.

In a web app with Actuator, diagnostic endpoint access can be enabled with:

```properties
management.endpoints.web.exposure.include=health,metrics
```

This property controls which endpoints are exposed; authentication and authorization still follow the application's security configuration. Modify it only within environments needing observation.

You do not need `spring.datasource.hikari.register-mbeans=true` for Micrometer to instrument HikariCP. MBeans are a separate management/observation mechanism. Nor should you manually attach a Hikari metrics tracker when Spring Boot already attaches one: mixing manual setup can drop expected metrics or create confusing duplicates.

If you define multiple `DataSource` beans manually, `spring.datasource.*` properties intended for default auto-configuration do not automatically configure every bean you construct. Verify each pool's actual configuration, actual trackers, and emitted tags.

## 5. Reading Metrics via Actuator in a Web App

This section applies to a web app running on `localhost:8080` using default Actuator paths. The Java example in Section 6 intentionally runs without a web server, so do not run these HTTP commands against that process.

First discover the list of names:

```bash
curl -s http://localhost:8080/actuator/metrics
```

Inspect a metric before filtering tags:

```bash
curl -s http://localhost:8080/actuator/metrics/hikaricp.connections.active
```

Read `availableTags`, then filter by the exact pool name:

```bash
curl -s --get \
  --data-urlencode "tag=pool:lessonPool" \
  http://localhost:8080/actuator/metrics/hikaricp.connections.active

curl -s --get \
  --data-urlencode "tag=pool:lessonPool" \
  http://localhost:8080/actuator/metrics/hikaricp.connections.pending

curl -s --get \
  --data-urlencode "tag=pool:lessonPool" \
  http://localhost:8080/actuator/metrics/hikaricp.connections.acquire

curl -s --get \
  --data-urlencode "tag=name:dataSource" \
  http://localhost:8080/actuator/metrics/jdbc.connections.max
```

These commands are for shells supporting `\` line continuations. In PowerShell, use `curl.exe` and keep each command on one line. If management port or base path was changed, adjust the URL to match the app.

Read results by metric type:

- For Gauges, find the measurement with `statistic=VALUE`.
- For Timers, distinguish `COUNT`, `TOTAL_TIME`, and `MAX` if provided by the registry; check the returned unit.
- For the timeout Counter, observe counts and changes over time rather than interpreting a cumulative count as a current rate.

Do not cite a fixed sample JSON to claim connection counts across every machine. Tag lists and values depend on the pool, registry, timing, and running workload. The commands above show how to query, not predetermined outputs.

When multiple pools exist, an unfiltered endpoint query can aggregate same-named meters. A combined value does not describe a read pool or write pool individually. To diagnose connection starvation, retain dimensions such as application instance, pool name, and connection role in your monitoring system.

## 6. Practice: Producing a Real Borrow Wait and Observing Recovery

### 6.1. Experiment Goal

The following standalone program creates a HikariCP pool with at most one connection to an in-memory H2 database:

1. Borrow and return once to initialize the pool.
2. Main thread holds the single connection.
3. Another thread requests a connection and has to wait.
4. That thread times out after the configured `connection-timeout`.
5. Main thread returns the connection.
6. Borrow again and execute `SELECT 1` successfully.

This is a pool test, not a database load test or a slow-SQL simulation. Holding the connection is intentional; there is no need for sleep SQL statements or an external database.

### 6.2. Files to Create

Create a dedicated directory with this layout:

```text
pool-metrics-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/PoolMetricsApplication.java
        └── resources/application.properties
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>pool-metrics-lab</artifactId>
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
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
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

Spring Boot manages JDBC, HikariCP, and H2 versions; no need to copy a separate Hikari version into the POM. With parent 3.3.13, this experiment uses HikariCP 5.1.0.

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:pool_metrics;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.pool-name=lessonPool
spring.datasource.hikari.maximum-pool-size=1
spring.datasource.hikari.minimum-idle=1
spring.datasource.hikari.connection-timeout=5000
spring.datasource.hikari.validation-timeout=1000
spring.sql.init.mode=never
```

Configuration explanation:

- `maximum-pool-size=1` creates a strict limit so the second borrow must wait.
- `minimum-idle=1` sets the goal of keeping one idle connection when no borrower holds it. It does not prevent idle count from dropping to 0 while in use.
- `connection-timeout=5000` permits waiting up to about five seconds per Hikari's mechanism. Do not use it to claim external timings will equal 5000 ms exactly.
- `validation-timeout=1000` bounds connection validation, separate from the borrow wait timeout.
- `spring.sql.init.mode=never` skips Spring Boot's SQL initialization script step in this test. The program opens connections itself during the lab.
- `web-application-type=none` allows running and exiting like a regular Java application. No HTTP port is needed, and there is no HTTP Actuator endpoint in this process.

`src/main/java/demo/PoolMetricsApplication.java`:

```java
package demo;

import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLTransientConnectionException;
import java.sql.Statement;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

@SpringBootApplication
public class PoolMetricsApplication {
    private static final String POOL = "lessonPool";
    private static final String DATA_SOURCE = "dataSource";

    public static void main(String[] args) throws Exception {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(PoolMetricsApplication.class, args)) {
            HikariDataSource source = context.getBean(HikariDataSource.class);
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            demonstrate(source, registry);
        }
    }

    private static void demonstrate(
            HikariDataSource source, MeterRegistry registry) throws Exception {
        try (Connection warm = source.getConnection()) {
            if (!selectOne(warm)) {
                throw new IllegalStateException("Warm-up query failed");
            }
        }

        Timer acquire = registry.get("hikaricp.connections.acquire")
                .tag("pool", POOL).timer();
        Timer usage = registry.get("hikaricp.connections.usage")
                .tag("pool", POOL).timer();
        Counter timeouts = registry.get("hikaricp.connections.timeout")
                .tag("pool", POOL).counter();
        long acquireBefore = acquire.count();
        long usageBefore = usage.count();
        double timeoutsBefore = timeouts.count();

        System.out.println("CHECK jdbc.name=" + registry.get("jdbc.connections.max")
                .tag("name", DATA_SOURCE).gauge().getId().getTag("name"));
        System.out.println("CHECK hikari.pool=" + acquire.getId().getTag("pool"));
        System.out.println("CHECK jdbc.active.present=" + (registry.find("jdbc.connections.active")
                .tag("name", DATA_SOURCE).gauge() != null));
        await(() -> hasState(registry, 0, 1, 0), "ready");
        snapshot("ready", registry);

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            try (Connection held = source.getConnection()) {
                await(() -> hasState(registry, 1, 0, 0), "held");
                snapshot("held", registry);

                Future<String> waiting = executor.submit(() -> {
                    try (Connection unexpected = source.getConnection()) {
                        return "unexpected-success";
                    } catch (SQLTransientConnectionException expected) {
                        return expected.getClass().getSimpleName();
                    }
                });

                await(() -> hasState(registry, 1, 0, 1), "waiting");
                snapshot("waiting", registry);
                String result = waiting.get(8, TimeUnit.SECONDS);
                if (!result.equals("SQLTransientConnectionException")) {
                    throw new IllegalStateException("Expected pool acquisition timeout");
                }
                System.out.println("CHECK wait.result=" + result);
                System.out.printf(Locale.ROOT, "CHECK timeout.delta=%.0f%n",
                        timeouts.count() - timeoutsBefore);
                System.out.println("CHECK usage.closed.whileHeld="
                        + (usage.count() - usageBefore));
            }

            await(() -> hasState(registry, 0, 1, 0), "returned");
            snapshot("returned", registry);
            try (Connection recovered = source.getConnection()) {
                System.out.println("CHECK reborrow.query.ok=" + selectOne(recovered));
            }
            System.out.println("CHECK acquire.count.delta="
                    + (acquire.count() - acquireBefore));
            System.out.println("CHECK usage.count.delta="
                    + (usage.count() - usageBefore));
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not terminate");
            }
        }
    }

    private static boolean selectOne(Connection connection) throws Exception {
        try (Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {
            return result.next() && result.getInt(1) == 1;
        }
    }

    private static boolean hasState(
            MeterRegistry registry, int active, int idle, int pending) {
        return hikari(registry, "active") == active
                && hikari(registry, "idle") == idle
                && hikari(registry, "pending") == pending
                && hikari(registry, "") == 1;
    }

    private static void snapshot(String phase, MeterRegistry registry) {
        Gauge jdbcMax = registry.get("jdbc.connections.max")
                .tag("name", DATA_SOURCE).gauge();
        System.out.printf(Locale.ROOT,
                "CHECK %s jdbcMax=%.0f hikariActive=%.0f idle=%.0f pending=%.0f total=%.0f%n",
                phase, jdbcMax.value(), hikari(registry, "active"),
                hikari(registry, "idle"), hikari(registry, "pending"),
                hikari(registry, ""));
    }

    private static double hikari(MeterRegistry registry, String suffix) {
        String name = "hikaricp.connections" + (suffix.isEmpty() ? "" : "." + suffix);
        return registry.get(name).tag("pool", POOL).gauge().value();
    }

    private static void await(BooleanSupplier condition, String phase)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (System.nanoTime() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(20);
        }
        throw new IllegalStateException("Pool state not observed: " + phase);
    }
}
```

### 6.3. Running the Program

JDK 17 or higher and Maven are required. The first build downloads dependencies from Maven repositories. From the directory containing `pom.xml`, run:

```bash
mvn -q -DskipTests package
java -jar target/pool-metrics-lab-1.0.0.jar
```

Because this application uses Spring Boot and external dependencies, you cannot simply run `javac PoolMetricsApplication.java` on the loose Java file. Maven compiles and packages the full required classpath.

Alongside startup and shutdown logs, the lines printed by the program in the verified Java 21 run are:

```text
CHECK jdbc.name=dataSource
CHECK hikari.pool=lessonPool
CHECK jdbc.active.present=false
CHECK ready jdbcMax=1 hikariActive=0 idle=1 pending=0 total=1
CHECK held jdbcMax=1 hikariActive=1 idle=0 pending=0 total=1
CHECK waiting jdbcMax=1 hikariActive=1 idle=0 pending=1 total=1
CHECK wait.result=SQLTransientConnectionException
CHECK timeout.delta=1
CHECK usage.closed.whileHeld=0
CHECK returned jdbcMax=1 hikariActive=0 idle=1 pending=0 total=1
CHECK reborrow.query.ok=true
CHECK acquire.count.delta=3
CHECK usage.count.delta=2
```

Do not hardcode exact execution durations or PID-bearing log lines as fixed outputs, since those values vary across machines.

### 6.4. Explaining Each State

`ready`: the pool has one idle connection. `active=0`, `idle=1`, `pending=0`. The JDBC `max` Gauge reports the limit of 1, not connections in use.

`held`: the main thread has borrowed the connection. `active=1`, `idle=0`. No slow SQL is running at this point. The experiment directly demonstrates that "active" means currently borrowed.

`waiting`: the second thread called `getConnection()` while the sole connection had not been returned. `pending=1`. It cannot run a query yet.

`wait.result=SQLTransientConnectionException`: Hikari could not grant a connection within the timeout. `timeout.delta=1` confirms one borrow timeout was recorded.

`usage.closed.whileHeld=0`: the usage Timer has no new completed sample yet, even though the main connection is being held. This line illustrates why you must inspect both the active Gauge and completed usage durations.

`returned`: the main connection was returned to the pool. One connection is idle again, and no thread is waiting. `reborrow.query.ok=true` verifies that subsequent borrowing and a simple query still work.

In this experiment's HikariCP 5.1.0 combination, `acquire` sample count increases by 3: borrowing to hold, the failed wait, and the recovery borrow. `usage` sample count increases by 2: returning the held connection and returning the recovery connection. The warm-up borrow completed before baseline snapshots were captured, so it is excluded from these deltas.

The program uses `try-with-resources` to return connections, closes the context to shut down the pool, and stops the executor. Observation waits are bounded. If a desired state is not observed, the program fails rather than printing fabricated results.

### 6.5. Why Is `jdbc.active.present=false`?

This is observed behavior for the exact configuration and version above, not a rule claiming Hikari always lacks JDBC Gauges.

In the experiment, `HikariDataSource` initializes its pool on the first `getConnection()` call, after the context has finished starting. When generic JDBC meters are bound earlier, `min/max` configuration can be read, while live pool `active/idle` statistics do not exist yet.

In Spring Boot 3.3.13, `DataSourcePoolMetrics` only registers a Gauge when that Gauge's value supplier returns non-`null` at binding time. `HikariDataSourcePoolMetadata` can return `null` for active/idle before the pool is initialized. Opening a connection later does not automatically re-register those skipped Gauges.

Hikari was attached with `MicrometerMetricsTrackerFactory` by Spring Boot, so `hikaricp.*` metrics appear once the pool starts. That is why the example uses `jdbc.connections.max` to illustrate the `name` tag and uses Hikari Gauges to observe state. Do not replace a missing metric with 0.

When encountering a similar situation:

- Inspect the list of actually registered meters rather than querying an endpoint solely by an assumed name.
- Check whether the pool has started, whether the bean is wrapped/routed, and whether the metadata provider supports it.
- Verify the exact version combination and binder attachment timing.
- Only initialize early or bind meters explicitly when lifecycle is deliberately designed, avoiding duplicate binding alongside auto-configuration.

If another application initializes its pool earlier, it may have both `jdbc.connections.active` and `jdbc.connections.idle`. Do not alter system-wide expectations just to force every app to resemble a small lab.

## 7. Distinguishing Related Timeouts

These names all contain "timeout," yet they guard different phases:

| Setting or Mechanism | Primary Phase | Misconception to Avoid |
| --- | --- | --- |
| Hikari `connectionTimeout` | Waiting for the pool to hand a connection to a borrower | Not a SQL execution timeout |
| Hikari `validationTimeout` | Checking whether a connection is still valid | Does not replace query timeout |
| JDBC/driver query timeout | Executing a statement per driver capability | Does not guarantee the whole transaction ends cleanly |
| Transaction timeout | Transaction scope, depending on manager and resources | Not identical to a single pool wait |
| Hikari `idleTimeout` | Retiring idle connections per pool rules | Never reclaims a currently borrowed connection |
| Hikari `maxLifetime` | Physical connection lifecycle | Never forcibly severs a borrowed connection right at the limit |

In Spring Boot properties, Hikari settings use kebab-case, such as `spring.datasource.hikari.connection-timeout`. For `long` values accepted by Hikari here, the unit is milliseconds; setting 5000 means 5000 ms.

For ordinary finite settings, Hikari 5.1.0 requires a minimum `connectionTimeout` of 250 ms; `validationTimeout` should be smaller than `connectionTimeout`. These are configuration constraints, not advice for every system to use minimum values.

`idleTimeout` shrinks excess idle connections when `minimumIdle` is smaller than `maximumPoolSize`. If you set min equal to max as in the example, do not expect the pool to shrink to fewer connections simply because idle time elapses.

`maxLifetime` retires physical connections over their lifecycle, yet a borrowed connection is not revoked mid-flight just because it crosses this threshold. Setting a short value will not fix code that forgets to return connections.

`leakDetectionThreshold` can log when a connection is held past a threshold. It is a suspected-long-hold warning, not automatic proof that code leaked, nor a mechanism that closes suspected connections. A legitimate but very long transaction can still trigger the warning.

Separating timeouts helps pick the right remedy: increasing borrow timeout can make users wait longer without adding processing capacity; a query timeout will not fix an external service call holding a connection.

## 8. Reading Signals Together to Find Root Causes

### 8.1. `active` Near `max`, `pending` Rising

This indicates the pool is struggling to supply connections fast enough for demand. Check how long the condition lasts and whether acquire duration rises with it.

Possible investigation directions include:

- Slow queries or queries waiting on database locks.
- Transactions spanning too much work.
- Code holding connections while calling external services or processing large payloads.
- Connections not returned when exceptions occur.
- Traffic rising beyond serving capacity or pool limits too small for measured load.

These metrics pinpoint where contention sits; they do not pre-select one cause. Cross-check error logs, request durations, execution traces, and database metrics before changing configuration.

### 8.2. `active` High While `pending` Is 0

The pool may simply be serving current load well. High utilization is not automatically an incident if borrow wait times stay low and errors are absent.

Conversely, a periodically scraped Gauge can miss very brief waits. Therefore do not use a single `pending=0` reading to deny timeouts or waits that happened between scrapes.

### 8.3. `timeout` Rising While `total` Is Still Below `max`

Simply raising `max` may not help. The pool might be unable to create new connections due to authentication errors, database connection limits, network failures, or slow connection handshakes.

Check Hikari/driver logs, test connectivity appropriately, and verify database state. The `creation` Timer helps observe recorded creation times but does not replace full connection error details. Do not infer from normal creation durations that every creation attempt succeeded.

### 8.4. `usage` Rising While `acquire` Stays Low

The application may be holding connections longer without yet forcing subsequent callers to wait. This is a cue to inspect connection-holding and transaction scopes, not a reason to rewrite every SQL statement immediately.

Also remember the usage Timer's delay: long holds complete only upon return. Combine active counts, transaction logs, and execution traces to understand what is happening.

### 8.5. Idle Connections Exist Yet the Application Still Fails

Idle connections do not prove credentials for every data source are right, every table exists, or every query is fast. Pool metrics reflect connection management, whereas SQL and business correctness sit at another layer.

Health endpoints and pool metrics also answer different questions. A single passing connection check does not prove the pool can handle concurrent load; a lightly used pool snapshot does not guarantee the next request will succeed.

## 9. Multiple Pools, Multiple Instances, and Setting Limits

An application may use a read pool, write pool, background-job pool, or multi-tenant pools. Each application replica also has its own pools.

When reading charts:

- Keep tags identifying pool and instance so different limits are not mixed.
- Distinguish JDBC Gauges tagged with `name` from Hikari metrics tagged with `pool`.
- Do not sum JDBC and Hikari groups as two independent connection sets if both observe the same pool.
- Aggregate only after clarifying whether you want to answer for one pool, one instance, or the whole system.

With multiple pools, a low total `active` can still hide a small saturated pool. For example, a write pool capped at 5 using all 5 connections, alongside a read pool capped at 50 sitting idle. A combined 5/55 hides the fact that threads needing the write pool are waiting.

When sizing `maximumPoolSize`, calculate the total connection budget toward the same database:

```text
Potentially needed connection budget
    = sum of limits across pools pointing to the database on all instances
      + connections from other applications/tools
      + headroom for operations and failover
```

This is capacity limit planning, not a prediction that every pool always opens its maximum connections. Scaling up instance count also raises potential connection demand even when each pool's setting stays unchanged.

Adding more connections does not make the database process faster on its own. Excessive concurrency can worsen CPU, I/O, or lock contention and lengthen connection hold times. Use controlled load testing and database metrics to find the right operating point.

You can roughly estimate held connections by multiplying the rate of work actually borrowing connections by average hold duration, provided the system is relatively stable. Do not multiply raw HTTP RPS blindly when many requests never touch the database, and do not treat an average as sufficient for traffic spikes or long transactions.

## 10. From Point-in-Time Inspection to Continuous Monitoring

`/actuator/metrics` is convenient for checking names, tags, and current state. To see trends, you need an export registry and a suitable collection/storage system. Backend names may be transformed according to backend rules; do not copy dotted endpoint names into a query without checking exported names.

A useful chart set usually pairs together:

- Borrowed, idle, total, and max connections per pool.
- Waiting thread count and borrow wait duration.
- Borrow timeouts per time interval.
- Completed connection hold duration.
- Application request latency/errors alongside corresponding database signals.

For a Timer, the mean over an interval must be computed as delta total time divided by delta sample count over the same interval and tag set when count is positive. Do not divide cumulative total time by overall application RPS. Percentiles or histograms exist only when configured and supported; do not infer p95 from a mean.

Cumulative timeout counters can reset on process restarts; step-exporting registries also have specific aggregation rules. Use your backend's rate/increase functions, preserve instance boundaries, and handle counter resets properly. A raw count of "10" alone does not mean 10 errors happened in the last minute.

Alerts should be tied to sustained duration and impact: for example, new timeouts occurring, or rising borrow wait times alongside pending threads and request latency. No single active percentage threshold fits every pool. The single-connection pool in the lab hits 100% the instant anyone borrows it; that alone is not an incident.

## 11. Common Mistakes and What to Check

| Symptom or Practice | What to Check | Next Step |
| --- | --- | --- |
| Missing `jdbc.connections.active` | Has the pool started, did metadata return a value at bind time? | Inspect real meters and registration lifecycle; do not turn missing data into 0 |
| Missing `hikaricp.*` | Is Hikari actually running and wired to Micrometer? | Check actual bean, versions, tracker setup, and registry |
| Metrics exist, but HTTP query sees nothing | Is the endpoint exposed, URL/tags right, and access authorized? | Separate HTTP access issues from meter registration issues |
| Calling `active` "running SQL count" | Are threads holding connections without running SQL? | Interpret as connections currently checked out |
| Treating `acquire` as SQL runtime | Does the timer measure pool wait time instead? | Measure and compare SQL/transactions with suitable instrumentation |
| Checking only `usage` to find a held connection | Has the suspected connection been returned yet? | Inspect active, transaction scopes, and hold diagnostics |
| Increasing pool size whenever timeouts happen | Does the database have capacity and connection budget? | Find root cause, re-measure after each change |
| Setting a huge borrow timeout to stop errors | Are requests just waiting longer or actually succeeding better? | Compare latency, pending threads, and serving capacity |
| Enabling leak detection and treating every log as a leak | Are there legitimate long transactions? | Inspect stack/logs and connection return paths |
| Summing JDBC and Hikari figures | Are both observing the same pool? | Pick one layer for consistent aggregation |

Do not create a custom "active" Counter around every query: in-use count rises and falls as state, and the pool already exposes a proper Gauge. A custom repository-layer counter can also miss borrows outside that layer or connections held by transactions.

## 12. Self-Check Exercises

1. In the standalone example, change `maximum-pool-size` to 2 and deduce what changes. The second thread can borrow immediately instead of waiting until timeout. The current program has checks tailored for a single-connection pool; update the scenario and expectations accordingly rather than treating assertion failures as a Hikari bug.
2. Keep a single-connection pool, yet close the main connection before the wait times out. The waiting thread can succeed and must return its connection. Then do not keep expecting `timeout.delta=1`.
3. In an existing web app, discover actual tags for each pool and query `active`, `pending`, `acquire`, and `timeout` separately. State which are point-in-time values, which are duration samples, and which are counts.
4. Pick a transactional operation and identify which parts actually need a connection held. If there are network calls unrelated to data consistency, analyze shortening the transaction scope before changing pool limits.

Comprehension check questions:

- Why might an active connection not be running SQL yet? Because it has been borrowed, while what happens during the hold depends on application code.
- Why does a missing metric differ from a metric equal to 0? Missing means no corresponding measurement exists; 0 is a value from an existing measurement.
- Why does a borrow timeout differ from a SQL timeout? The former occurs before obtaining a connection, while the latter occurs during statement execution.
- Why did `acquire` sample count increase by 3 while `usage` increased by only 2 in the experiment? The timed-out wait recorded an acquire duration, yet had no borrowed connection to return.
- Why does running multiple instances change decisions about increasing pool size? Each instance enforces its own limit, while together they share the connection budget of one database.

## 13. Reference Documentation

- [Spring Boot 3.3 — DataSource metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.jdbc): generic JDBC group and HikariCP.
- [Spring Boot 3.3.13 — DataSourcePoolMetricsAutoConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/jdbc/DataSourcePoolMetricsAutoConfiguration.java): how trackers are wired and tagged.
- [HikariCP 5.1.0 — MicrometerMetricsTracker](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/metrics/micrometer/MicrometerMetricsTracker.java): metric names and measurement types.
- [HikariCP 5.1.0 — HikariPool](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/pool/HikariPool.java): pool statistics and borrow timeout paths.
- [HikariCP 5.1.0 — PoolBase](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/pool/PoolBase.java): how borrow and usage durations are recorded.
- [HikariCP 5.1.0 — HikariConfig](https://github.com/brettwooldridge/HikariCP/blob/HikariCP-5.1.0/src/main/java/com/zaxxer/hikari/HikariConfig.java): configuration value constraints.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): sample counts, total time, and unit handling.
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): point-in-time observation and sampling limits.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): meaning of pool properties; cross-check with your running version.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): relationship between connection counts, concurrency, and database capacity.
