# Simulate database failure, slow HTTP, and resource exhaustion for diagnostic practice

## 1. Goal: move from symptoms to evidence

An API returning an error or running slowly does not by itself reveal where the failure lives. The exact same 503 response can appear when the database stops running or when the database is healthy but the application cannot borrow a connection. Likewise, low CPU does not mean the application still has serving capacity: every worker thread may be blocked waiting on I/O.

In this **Integrated Practice** lab for Spring Boot Actuator, we intentionally inject each failure, observe it, and recover. The destination is being able to explain **which resource is being held, where requests are waiting, and which evidence rules out alternative hypotheses**.

Four concepts to distinguish:

- **Symptom:** HTTP status code, latency, and user-visible error.
- **Health status:** results of checks at the moment the endpoint is called; not a log of every application failure.
- **Operational metrics:** counts, durations, utilization, and queues; must be read alongside timestamps and tags.
- **Execution evidence:** logs and thread dumps, revealing what requests are actually doing while metrics change.

Liveness answers whether the process is still in a valid running state. Readiness answers whether the application is ready to receive traffic under configured policy. A broken database does not automatically turn liveness DOWN; putting a shared dependency into liveness can cause multiple replicas to restart without fixing that dependency.

This lab uses a Servlet application, PostgreSQL, and a separate mock HTTP server. Resource exhaustion scenarios cover **HikariCP connection pool exhaustion** and **Tomcat thread saturation**. These are forms of capacity exhaustion even when memory and CPU are not full.

## 2. Model and lab conditions

Paths of the three request types:

1. `/lab/db` → Tomcat → borrow Hikari connection → PostgreSQL.
2. `/lab/remote` → Tomcat → RestClient → mock HTTP server on port 9090.
3. `/lab/sleep` → Tomcat → hold worker thread for a bounded duration.

Actuator runs on separate management port 8081; APIs run on 8080. Separate ports allow continued evidence gathering while API worker threads are held. Both ports still share the same JVM, CPU, memory, and DataSource; the management port is not an independent monitoring system and cannot rescue a dead JVM.

Prepare JDK 21, Gradle 8.5, Docker Compose, Python 3, and curl. The sample project pins Spring Boot **3.3.0** for a concrete API baseline in the 3.3.x branch; this is a lab pin, not a statement about the latest release. The first build needs access to download plugins and dependencies. All addresses below are loopback and use a lab-dedicated database account.

Create a separate practice directory. Never copy failure-injection endpoints into real services. Run one scenario at a time and fully recover before moving to the next. Stop only the lab database, not Docker machine-wide; never write unbounded memory allocation loops or fill disks.

File structure:

```text
actuator-diagnosis-lab/
├── settings.gradle
├── build.gradle
├── compose.yml
├── SlowUpstream.java
├── load.py
└── src/main/
    ├── java/lab/LabApplication.java
    └── resources/application.yml
```

`curl` commands work in any terminal with curl. On Windows PowerShell, use `curl.exe` to avoid the conflicting alias. `javac`, `java`, and `gradle` commands below must point to the stated toolchain. If Gradle wrapper 8.5 is already present, use `./gradlew` or `.\gradlew.bat` instead of `gradle`.

## 3. Set up the minimal environment

### 3.1. Build and database configuration

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-diagnosis-lab'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'lab'
version = '1.0.0'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

The JDBC starter provides JdbcTemplate, DataSource, and HikariCP. The Actuator starter provides health and metrics; Prometheus is not needed for this lab because we read `/actuator/metrics` directly.

File `compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    ports:
      - "127.0.0.1:15432:5432"
    environment:
      POSTGRES_DB: lab
      POSTGRES_USER: lab
      POSTGRES_PASSWORD: lab
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lab -d lab"]
      interval: 2s
      timeout: 2s
      retries: 20
```

PostgreSQL inside the container listens on port 5432; the host application connects via **15432**. Do not change the application URL to the container port if the application still runs on the host.

### 3.2. Actuator and resource-limit configuration

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  tomcat:
    threads:
      max: 8
      min-spare: 2
    mbeanregistry:
      enabled: true

spring:
  application:
    name: actuator-diagnosis-lab
  threads:
    virtual:
      enabled: false
  datasource:
    url: jdbc:postgresql://127.0.0.1:15432/lab?connectTimeout=2&socketTimeout=3
    username: lab
    password: lab
    hikari:
      pool-name: lab-pool
      maximum-pool-size: 3
      minimum-idle: 1
      connection-timeout: 3000
      validation-timeout: 1000

management:
  server:
    address: 127.0.0.1
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,metrics,threaddump
  endpoint:
    health:
      show-details: always
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Choices governing how results are read:

- Hikari has only **3** connections. `connection-timeout=3000` is the maximum wait to borrow a connection from the pool, not the timeout of an SQL statement.
- PostgreSQL JDBC parameters `connectTimeout` and `socketTimeout` use **seconds** in this URL. They govern different phases than pool borrow wait time.
- API Tomcat has at most **8** worker threads. Virtual threads are disabled so thread-holding experiments behave clearly.
- Readiness includes `readinessState` and `db`; liveness includes only `livenessState`. This is an intentional lab policy. Boot does not put every dependency into readiness by default.
- `mbeanregistry.enabled=true` enables Tomcat metrics via MBeans. When filtering metrics, inspect actual connector tags since there are two ports.
- Expose only `health`, `metrics`, `threaddump`. `show-details=always` and omitting authentication suit only a loopback-restricted lab; never use this configuration verbatim as a public policy.

### 3.3. Complete Spring Boot application

File `src/main/java/lab/LabApplication.java`:

```java
package lab;

import java.net.http.HttpClient;
import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@SpringBootApplication
public class LabApplication {
    private static final Logger LOG = LoggerFactory.getLogger(LabApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(LabApplication.class, args);
    }

    @Bean
    RestClient upstreamClient(RestClient.Builder builder) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(500)).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(client);
        factory.setReadTimeout(Duration.ofMillis(1000));
        return builder.baseUrl("http://127.0.0.1:9090")
                .requestFactory(factory).build();
    }

    @Bean(destroyMethod = "close")
    PoolHolder poolHolder(DataSource dataSource) {
        return new PoolHolder(dataSource);
    }

    static final class PoolHolder implements AutoCloseable {
        private final DataSource dataSource;
        private final List<Connection> held = new ArrayList<>();
        private final ScheduledExecutorService timer =
                Executors.newSingleThreadScheduledExecutor(task -> {
                    Thread thread = new Thread(task, "pool-auto-release");
                    thread.setDaemon(true);
                    return thread;
                });
        private long generation;

        PoolHolder(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        synchronized int hold(int seconds) throws SQLException {
            if (seconds < 1 || seconds > 30) {
                throw new IllegalArgumentException("seconds must be in 1..30");
            }
            if (!held.isEmpty()) {
                throw new IllegalStateException("pool is already held");
            }
            long current = ++generation;
            try {
                for (int i = 0; i < 3; i++) {
                    held.add(dataSource.getConnection());
                }
                timer.schedule(() -> releaseIfCurrent(current), seconds, TimeUnit.SECONDS);
                return held.size();
            } catch (SQLException ex) {
                closeHeld();
                throw ex;
            }
        }

        private synchronized void releaseIfCurrent(long expected) {
            if (generation == expected) {
                release();
            }
        }

        synchronized int release() {
            generation++;
            return closeHeld();
        }

        private int closeHeld() {
            int count = held.size();
            for (Connection connection : held) {
                try {
                    connection.close();
                } catch (SQLException ex) {
                    LOG.warn("Cannot return a held connection", ex);
                }
            }
            held.clear();
            return count;
        }

        @Override
        public void close() {
            timer.shutdownNow();
            release();
        }
    }

    @RestController
    @RequestMapping("/lab")
    static class LabController {
        private final JdbcTemplate jdbc;
        private final RestClient upstream;
        private final PoolHolder holder;

        LabController(JdbcTemplate jdbc, RestClient upstream, PoolHolder holder) {
            this.jdbc = jdbc;
            this.upstream = upstream;
            this.holder = holder;
        }

        @GetMapping("/db")
        String db() {
            Integer result = jdbc.queryForObject("SELECT 1", Integer.class);
            return "db=" + result + "\n";
        }

        @GetMapping("/remote")
        ResponseEntity<String> remote(@RequestParam(name = "delayMs", defaultValue = "0") int delayMs) {
            if (delayMs < 0 || delayMs > 5000) {
                throw new IllegalArgumentException("delayMs must be in 0..5000");
            }
            try {
                String body = upstream.get().uri("/work?delayMs={delay}", delayMs)
                        .retrieve().body(String.class);
                return ResponseEntity.ok(body);
            } catch (ResourceAccessException ex) {
                LOG.warn("Upstream I/O failed", ex);
                return ResponseEntity.status(504).body("remote-io-failed\n");
            } catch (RestClientException ex) {
                LOG.warn("Upstream request failed", ex);
                return ResponseEntity.status(502).body("remote-call-failed\n");
            }
        }

        @PostMapping("/pool/hold")
        String hold(@RequestParam(name = "seconds", defaultValue = "20") int seconds) throws SQLException {
            return "held=" + holder.hold(seconds) + "\n";
        }

        @PostMapping("/pool/release")
        String release() {
            return "released=" + holder.release() + "\n";
        }

        @GetMapping("/sleep")
        String sleep(@RequestParam(name = "ms", defaultValue = "8000") int ms)
                throws InterruptedException {
            if (ms < 0 || ms > 10000) {
                throw new IllegalArgumentException("ms must be in 0..10000");
            }
            Thread.sleep(ms);
            return "sleptMs=" + ms + "\n";
        }

        @ExceptionHandler({DataAccessException.class, SQLException.class})
        ResponseEntity<String> databaseError(Exception ex) {
            LOG.warn("Database request failed", ex);
            return ResponseEntity.status(503).body("db-unavailable\n");
        }

        @ExceptionHandler(IllegalArgumentException.class)
        ResponseEntity<String> badInput(IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(ex.getMessage() + "\n");
        }

        @ExceptionHandler(IllegalStateException.class)
        ResponseEntity<String> conflict(IllegalStateException ex) {
            return ResponseEntity.status(409).body(ex.getMessage() + "\n");
        }
    }
}
```

Key points in the program:

1. `RestClient.Builder` is provided by Spring Boot, so it flows through Boot's observability auto-configuration. Calling `RestClient.create()` directly can bypass that configuration.
2. The HTTP client uses a 500 ms connect timeout and a 1000 ms read timeout. Timing measured outside the app also includes processing, queuing, and scheduling overhead; do not expect the clock to stop at exactly 1.000 second.
3. `PoolHolder` borrows all three connections and **intentionally does not return them immediately**, simulating a resource-retention bug. After at most 30 seconds, the timer returns them; the release endpoint allows early return. The `generation` counter prevents an old timer task from closing connections from a newer hold cycle.
4. Both database failures and pool borrow timeouts map to 503 in the sample API. I/O failures to the mock HTTP server map to 504; other RestClient errors map to 502. This is a lab-code convention, not something every Spring Boot app returns automatically. A real application should classify connection, timeout, and HTTP errors more precisely.
5. Load-generating parameters are all bounded. Holding connections runs no heavy SQL: PostgreSQL can remain completely healthy while the app runs out of connections to hand to new requests.

### 3.4. Standalone mock HTTP server

File `SlowUpstream.java` uses the `jdk.httpserver` module included in the JDK. It runs **outside** the application so dependency latency never mixes with the application's own Tomcat queue.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SlowUpstream {
    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 9090), 0);
        ExecutorService workers = Executors.newFixedThreadPool(8);
        server.setExecutor(workers);
        server.createContext("/work", exchange -> {
            try {
                String query = exchange.getRequestURI().getRawQuery();
                int delay = query == null ? 0 : Integer.parseInt(query.replace("delayMs=", ""));
                if (delay < 0 || delay > 5000) {
                    throw new IllegalArgumentException();
                }
                Thread.sleep(delay);
                reply(exchange, 200, "upstream-ok\n");
            } catch (IllegalArgumentException ex) {
                reply(exchange, 400, "invalid-delay\n");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                reply(exchange, 503, "interrupted\n");
            } finally {
                exchange.close();
            }
        });
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(0);
            workers.shutdownNow();
        }));
        server.start();
        System.out.println("upstream=http://127.0.0.1:9090/work");
    }

    private static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
}
```

The server accepts only the lab's path and parameter. When the client times out first, the server may still finish sleeping and then hit an IOException writing to the closed connection. A client timeout does not guarantee server-side work was cancelled.

### 3.5. Bounded burst load generator

File `load.py` sends the exact chosen number of requests without generating unbounded load. It reads the full response so timing includes receiving the body, and uses a monotonic clock for timing. The cap of 16 concurrent requests prevents accidentally generating heavy load from a typo.

```python
import collections
import concurrent.futures
import sys
import threading
import time
import urllib.error
import urllib.request

route = sys.argv[1] if len(sys.argv) > 1 else "/lab/db"
workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
if not 1 <= workers <= 16:
    raise SystemExit("workers must be in 1..16")
barrier = threading.Barrier(workers)

def call(_):
    barrier.wait()
    start = time.perf_counter()
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080" + route, timeout=25) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except (urllib.error.URLError, TimeoutError):
        status = "transport-error"
    return status, round(time.perf_counter() - start, 3)

with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
    results = list(executor.map(call, range(workers)))
print("statuses:", dict(collections.Counter(status for status, _ in results)))
print("seconds:", sorted(duration for _, duration in results))
```

If output shows `transport-error`, that is a load-generator or connection error, not an HTTP code returned by the server. Inspect both client and server logs before drawing conclusions.

## 4. Start up and capture the baseline

### 4.1. Start the processes

In the directory containing `compose.yml`, start and wait for the database to become ready:

```shell
docker compose up -d --wait db
```

In the first terminal, compile and run the mock HTTP server:

```shell
javac --release 21 --add-modules jdk.httpserver SlowUpstream.java
java --add-modules jdk.httpserver SlowUpstream
```

Stdout of the mock server upon successful startup:

```text
upstream=http://127.0.0.1:9090/work
```

Keep that terminal running. In the second terminal, start the Spring Boot application:

```shell
gradle bootRun
```

Wait for the application to finish starting before calling APIs. If a port is already occupied or the database is not ready yet, fix that cause first; do not treat a broken startup state as the baseline for experiments.

### 4.2. Confirm both branches work normally

```shell
curl -sS http://127.0.0.1:8080/lab/db
curl -sS "http://127.0.0.1:8080/lab/remote?delayMs=0"
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
```

The first two commands print the following exact bodies when all dependencies work:

```text
db=1
upstream-ok
```

Both health groups must return HTTP 200 with a top-level `status` of `UP`. Actual JSON includes components/details; it does not need to match a fixed JSON sample byte-for-byte. Calling `/lab/db` first also initializes the DataSource and registers pool-related metrics.

### 4.3. Capture baseline metrics for comparison

```shell
curl -sS http://127.0.0.1:8081/actuator/metrics
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.max?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.active?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.idle?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.pending?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/http.server.requests?tag=uri:/lab/db"
curl -sS http://127.0.0.1:8081/actuator/metrics/http.client.requests
curl -sS http://127.0.0.1:8081/actuator/metrics/tomcat.threads.busy
```

Inspect `measurements` and `availableTags` in the JSON. For pool `lab-pool`, the cap is 3; when no requests are executing, active and pending should return to 0. Idle may be less than 3 since minimum-idle is only 1. A running health probe can also temporarily borrow a connection.

HTTP metrics appear only after matching activity occurs. If a name returns 404, check the `names` list, trigger the relevant activity, and re-check; 404 does not mean a value of 0. Do not convert to Prometheus underscore names: names read at this endpoint are dotted Micrometer names.

For the `http.server.requests` timer, take the delta of COUNT and TOTAL_TIME between two samples with the same tags. Average duration of newly completed requests is `ΔTOTAL_TIME / ΔCOUNT` when `ΔCOUNT > 0`. Read `baseUnit` to confirm units. Do not infer p95 from average or MAX; this lab configures no percentile/histogram distribution. MAX typically reflects a rolling timer window, not a lifetime maximum since process start.

These timers primarily reflect completed requests. While requests are hanging, check pending, busy threads, and thread dumps instead of waiting for COUNT to rise. Client-measured latency can also include wait time before the servlet begins handling, which server timers may not fully reflect.

For Tomcat metrics, read the actual `name` tag and filter for the 8080 API connector if data separates connectors. Do not sum ports 8080 and 8081 together to claim all 8 API threads are exhausted. Even a metrics request itself can add one busy thread on the management port.

Record timestamps, initial metrics, and HTTP codes in your own observation notes. Counter/timer metrics do not reset to 0 when an incident ends; only gauges such as active/pending can drop back to baseline.

## 5. Scenario A — Database stops running

### 5.1. Inject a real dependency failure

Stop only the lab directory's database service:

```shell
docker compose stop db
curl -sS -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
```

Once the failure is detected, `/lab/db` returns 503 with body:

```text
db-unavailable
```

Readiness transitions to DOWN/503 because the group checks `db`. Liveness remains UP/200 if the process and liveness state have no other issues. Wait time can span phases for broken-connection detection, pool borrowing, and I/O; do not sum timeouts and treat that sum as a fixed duration for every call.

If you just stopped the database and the first read does not reflect the failure yet, confirm the container stopped completely and re-observe within a bounded interval. Do not draw conclusions from a single snapshot taken mid-transition.

### 5.2. Gather and explain evidence

1. Cross-check errors in application logs: locate the JDBC root cause beneath DataAccessException or SQLException, such as connection refused/closed. Exact messages depend on driver and timing.
2. Read the `db` component details in health. `DOWN` tells you the check failed; the cause and logs distinguish losing the database from exhausting the pool.
3. Capture active, idle, pending, and 503 request metrics. Pool values while the database is stopped can fluctuate as Hikari discards broken connections and retries connecting. Do not make a mechanical rule that database down always leaves active at 3.
4. Call `/lab/remote?delayMs=0`. If the HTTP branch still succeeds, the failure is isolated to the database path, even though application-wide readiness is currently DOWN under lab policy.

Readiness is a signal for traffic routers; in this lab there is no orchestrator automatically blocking port 8080. Thus, clients can still call the API directly even while readiness is DOWN.

### 5.3. Recover and verify

```shell
docker compose up -d --wait db
curl -sS -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
```

Wait for Hikari to re-establish connections if needed, then verify the database API returns 200 with `db=1` and readiness returns UP. Bound the wait time per environment, e.g., 60 seconds; if it still has not recovered, read logs and database status instead of immediately restarting the app. Recovering without restarting the application is a key verifiable outcome of this experiment.

## 6. Scenario B — Upstream HTTP dependency responds slowly

Ensure both the database and mock HTTP server are running. Try a slow request that is still within limits:

```shell
curl -sS -i "http://127.0.0.1:8080/lab/remote?delayMs=700"
```

With no other issues, the response is 200 with `upstream-ok` and duration increases with the configured delay. Next, set a delay exceeding the read timeout:

```shell
curl -sS -i "http://127.0.0.1:8080/lab/remote?delayMs=4000"
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
curl -sS http://127.0.0.1:8081/actuator/metrics/http.client.requests
curl -sS "http://127.0.0.1:8081/actuator/metrics/http.server.requests?tag=uri:/lab/remote"
```

Under normal lab conditions, the remote API times out around the 1-second mark plus processing overhead and returns 504 with body:

```text
remote-io-failed
```

Cross-check three layers of evidence:

- The `Upstream I/O failed` log shows the corresponding timeout cause. If the cause is connection refused, the mock server is not running; that is not a slow-response test.
- Both client timer and server timer record the additional call/duration, with error/status tags matching actual outcomes. Do not assume error tag names are always identical across HTTP clients and library versions.
- The database pool still has idle connections; `/lab/db` still succeeds. Thus raising Hikari maximum-pool-size would not fix this HTTP call path.

Both readiness and liveness may still be UP: the readiness group here checks only readiness state and database, not the upstream HTTP dependency. **Health UP does not promise every API succeeds or meets latency targets.** To reflect an HTTP dependency, design an appropriate health indicator and group policy, including dedicated check timeouts; never insert an unbounded slow call into health.

Do not raise timeouts just to eliminate 504s. If wait time jumps from 1 to 10 seconds with unchanged serving capacity, more threads can be held longer and trigger a secondary outage. In real systems, account for end-to-end request time budgets, concurrency limits, and circuit breaking where appropriate. Unbounded retries can amplify load; this lab intentionally does not auto-retry.

Recover with `/lab/remote?delayMs=0` and confirm 200. Wait at least 5 seconds after a 4000 ms call so old mock work finishes before the next experiment; client timeout does not ensure upstream stopped working. Unlike gauges, recorded error counts persist in timers.

## 7. Scenario C — Database healthy but connection pool exhausted

### 7.1. Hold all application connections

Verify `/lab/db` returns 200, then hold all three connections for 20 seconds:

```shell
curl -sS -X POST "http://127.0.0.1:8080/lab/pool/hold?seconds=20"
```

Expected body after holding succeeds:

```text
held=3
```

Immediately afterward, in the load terminal run a burst of eight requests:

```shell
python load.py /lab/db 8
```

While the requests are waiting, use another terminal to capture evidence. Start right away within the 20-second hold window; pending rises only while requests are actively waiting:

```shell
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.active?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.idle?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.pending?tag=pool:lab-pool"
curl -sS http://127.0.0.1:8081/actuator/threaddump
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
```

### 7.2. Signals distinguishing this from a stopped database

While all three connections are held, pool active reaches 3 and idle is 0. Pending is greater than 0 **while** requests are waiting; it may already have dropped to 0 if you sample after they time out. After roughly 3 seconds of pool wait plus processing overhead, requests unable to borrow a connection return 503. If the burst starts and finishes before auto-release, the script's status summary line is:

```text
statuses: {503: 8}
```

The `seconds` line contains actual measured durations; there is no fixed number list to copy. If 200s appear, check when load started relative to auto-release before concluding the fault-injection code failed.

Thread dumps typically show request threads waiting to borrow a connection, with stack frames in HikariPool/ConcurrentBag and JDK wait primitives. Never conclude solely from state names WAITING or TIMED_WAITING: many idle background threads have those states too. Tie stack frames to the endpoint under load.

Check PostgreSQL directly, bypassing the application's Hikari pool:

```shell
docker compose exec -T db psql -U lab -d lab -c "SELECT 1;"
```

If this command succeeds while the API reports pool borrow timeouts, you have evidence that the database is still serving queries over another connection. Connection holding inside the application is the injected cause. PostgreSQL may show the held sessions as idle; **active in Hikari means currently borrowed**, not necessarily that the database is executing queries on all of them.

Readiness may go DOWN/503 even though the database is healthy because the `db` check also borrows a connection from the same DataSource. Liveness remains UP. A failed `db` component alone cannot distinguish a dead database from an exhausted application pool: combine health with metrics, logs, thread dumps, and an independent probe.

### 7.3. Bounded recovery

Wait for auto-release or call:

```shell
curl -sS -X POST http://127.0.0.1:8080/lab/pool/release
curl -sS -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
```

Release returns the number of connections just returned: `released=3` if all three were still held, or `released=0` if the timer already returned them earlier. Once prior requests finish, pending returns to 0, active returns to idle levels, and both API and readiness recover.

The release endpoint still runs on API Tomcat. If all eight threads are waiting on the pool, the release command can end up queued. The timer runs separately so recovery does not depend entirely on this queued rescue endpoint.

In real code, audit unclosed connections, overly long transaction scopes, slow queries, and holding transactions open during HTTP calls. Use try-with-resources when managing Connections directly. Increasing pool size helps only after understanding database limits and hold times; increasing numbers does not cure leaks.

## 8. Scenario D — Worker threads exhausted despite low CPU

Ensure the pool is fully released and both database and HTTP server are healthy. Send 16 requests each sleeping 8 seconds while API Tomcat has only 8 threads:

```shell
python load.py "/lab/sleep?ms=8000" 16
```

In another terminal while the burst is running:

```shell
curl -sS --max-time 2 -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
curl -sS http://127.0.0.1:8081/actuator/metrics/tomcat.threads.busy
curl -sS http://127.0.0.1:8081/actuator/threaddump
```

Half the requests are handled first while the rest wait for threads, so client times usually form two waves around 8 and 16 seconds, plus real overhead. Do not demand the two waves be exact to the millisecond. The curl call to `/lab/db` can hit `--max-time` even though the SQL query is trivial and the database is healthy: the request has not been assigned a thread to reach pool borrowing yet.

Evidence to cross-check:

- Busy threads on the API connector approach the limit of 8 during the load window.
- Thread dumps show request threads inside `LabController.sleep` / `Thread.sleep`.
- The database pool does not show the active=3, idle=0 signature of the pool-hold test; it generally stays idle while threads sleep.
- CPU may stay low because sleeping/waiting takes negligible CPU time. You can also inspect `process.cpu.usage` and `jvm.threads.live` if present in the metrics list; total live JVM threads is not the number of busy Tomcat threads.
- Liveness on the management port may stay UP. Readiness may also stay UP because current policy does not measure API connector saturation. This is an important limitation of health checks on a separate port.

Curl timing out only makes the client stop waiting; it does not ensure queued requests or server work were cancelled. Therefore wait for the entire burst to finish and then verify `/lab/db` is fast again. Bounded sleep requests expire on their own; do not kill the JVM to recover from this scenario.

When applying to environments with real probes, verify whether probe paths actually represent the application port's ability to accept traffic. A responsive management port does not prove the business connector is healthy. Nor should every WAITING thread in a thread dump be called a deadlock or every busy thread be called CPU-bound.

## 9. Comparison table for forming hypotheses

The following indicators are expected outcomes in **this lab's configuration**, read at the same point in time. They do not replace logs and execution evidence.

| Injected fault | API symptom | Expected health | Distinguishing evidence |
| --- | --- | --- | --- |
| PostgreSQL stopped | db branch fails 503 | Readiness DOWN; liveness UP | Dependency unreachable, JDBC errors show connection cause; direct database test fails |
| HTTP server too slow | remote branch fails 504 per sample code | Both groups can remain UP | HTTP client timeout errors; client/server request metrics rise; db branch still works |
| All three connections held | db branch waits then fails 503 | Readiness may be DOWN; liveness UP | active=3, idle=0, pending rises while callers wait; direct database still answers SELECT 1 |
| All API Tomcat threads held | Even trivial APIs wait | Management port may still report UP | API connector threads busy, stack sits in sleep; database pool is not the bottleneck |

A passing direct check at one point in time rules out only hypotheses inconsistent with that check. For instance, SELECT 1 succeeding does not prove all business queries are fast, lock-free, or that enough connections exist system-wide.

## 10. Repeatable diagnostic sequence

1. **Scope the symptom:** which endpoint, which code, how much latency, when did it start, is one branch or multiple branches affected?
2. **Capture simultaneous evidence:** per-component health, properly tagged metrics, logs from the same time window, and thread dumps while waiting. Do not read pending after the incident ended and infer there was never a queue.
3. **Form at least two hypotheses:** database unreachable vs. pool exhausted; slow upstream vs. servlet threads held before calling upstream.
4. **Use isolating checks:** direct SELECT 1, calling upstream directly with the same delay, or comparing a non-database branch. Change one factor at a time.
5. **Restore the injected cause:** start db, clear delay, release pool, or let sleep finish. Re-measure API, readiness, and gauges; do not expect historical counters to reset to 0.
6. **Write a bounded conclusion:** what evidence confirms where requests waited, what evidence rules out alternative hypotheses, and what remains unmeasured. A single metrics snapshot proves neither a resource leak nor causality.

Common practice mistakes:

- Calling the wrong port: `/actuator` is on 8081, lab endpoints on 8080; a 404 from the wrong URL is not a database outage.
- Using curl `-f` and missing error bodies: during diagnostics, use `-i` to see both HTTP code and body as in the examples.
- Holding connections without sending traffic and waiting for pending to rise: pending counts waiting callers, not held connections.
- Seeing readiness DOWN and restarting the entire application: that destroys evidence and does not fix a stopped database.
- Seeing health UP and dismissing user errors: health reflects only configured checks, not a guarantee across every call path.
- Requiring high memory/CPU to call something resource exhaustion: pools or worker threads can run out first.
- Overlapping multiple scenarios: HTTP timeouts hold threads, held threads queue rescue commands, making root cause hard to separate from cascading effects.

## 11. Exercises and completion criteria

Repeat the exercises without looking at the comparison table, injecting only one fault at a time. For each scenario, write a diagnostic note containing: symptom and timestamp; hypothesis; two independent evidence sources; isolating test; recovery action; post-recovery verification.

You complete the lab when you can answer these questions using captured evidence:

- Why does `db` health go DOWN when the pool is exhausted even though the database is still running?
- Why does adding database connections not resolve a slow HTTP upstream?
- Why does a simple SELECT 1 take many seconds during the thread-holding scenario despite low CPU?
- Why is liveness UP on the management port insufficient to prove the API port is accepting requests normally?
- Why does a client-side timeout not guarantee server-side work was cancelled?

Controlled advanced exercise: change `maximum-pool-size` from 3 to 4 **while keeping the code holding only three connections**, restart the lab, and run the pool scenario. Predict beforehand that one connection remains free to serve SELECT 1; latency and pending will depend on load. This tests a capacity hypothesis, not proof that raising pool size fixes connection leaks in production. After testing, revert the setting to 3 before reusing the lab's baseline table.

## 12. Clean up the environment

Wait for all load bursts to finish, release any held connections, stop the application and HTTP server with Ctrl+C in their terminals, then stop the lab stack:

```shell
docker compose down
```

The program closes held connections and its timer when Spring closes beans. The sample Compose file declares no named volumes to preserve; do not run extra volume-delete or system-wide Docker prune commands. When restarting the application for another study session, take a fresh baseline because in-memory metrics have a new lifecycle.
