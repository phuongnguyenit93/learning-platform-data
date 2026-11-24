# Diagnosing Hung Requests, Thread Exhaustion, Blocked Event Loops, and Timeouts

## 1. Objectives of This Knowledge Article

When a Spring Boot API "spins forever," returns 504, stops responding, or suffers a sudden p99 spike, the symptom visible to callers does not immediately reveal the root cause. There may be **no actual thread deadlock**: requests could simply be waiting for a pool connection, waiting on a slow downstream service, queued in Tomcat, or blocked inside the Reactor Netty event loop by synchronous code.

This article belongs to **Spring Boot - web-runtime**, under **Debugging and Upgrades**. After studying it, you will be able to:

1. Distinguish **slow-running requests**, **queue saturation**, **Servlet thread exhaustion**, **deadlock/lock contention**, **event-loop blocking**, **pool acquisition timeouts**, and **client/proxy timeouts**.
2. Determine whether a request reached the server using proxy markers, controller logs, correlation/trace IDs, and HTTP statuses.
3. Capture **metrics, thread dumps, Java Flight Recorder (JFR), CPU/GC, connection pool counters, and traces** while an incident is active.
4. Understand why **`http.server.requests` records timings only upon request completion**, meaning an in-flight hung request has not yet emitted a timer sample.
5. Use **Java 17 + Spring Boot 3.3.5** to reproduce 4 MVC behaviors: held Tomcat workers, Hikari/JDBC pool exhaustion, Java monitor contention, and slow downstream calls.
6. Run a WebFlux lab distinguishing **blocking on `reactor-http-nio-*`** from non-blocking pipelines and offloading to `boundedElastic`.
7. Set timeouts at the proper layer: TCP connect, HTTP response/read, client deadline, Hikari acquisition, SQL query, MVC asynchronous, reverse proxy, and caller timeout.
8. Evaluate upgrade impacts across Spring Boot/JDK/libraries and apply controlled mitigations.

**Guiding principle:** gather evidence first, form a hypothesis, change **one variable**, and re-measure. Blindly bumping `server.tomcat.threads.max`, event-loop threads, Hikari pool max, or timeouts usually just moves the bottleneck elsewhere.

## 2. "Hanging" Can Mean Very Different States

Users see a spinner or HTTP clients time out, yet the underlying state can vary widely:

| Symptom | True nature | Evidence to collect |
| --- | --- | --- |
| Entered handler, hasn't returned | Long business code / I/O / lock | Request START log, spans, thread dump |
| Never entered handler | Connector/worker queue, proxy, or network | Proxy access logs, Tomcat busy/queue, no server START log |
| Worker waiting on pool | Couldn't acquire JDBC/HTTP connection | Pool active/pending/acquire time |
| Worker holds connection, query slow | DB query/lock or remote dependency | SQL time, DB locks, outbound spans |
| True deadlock | Cyclic monitor/lock wait preventing progress | Multiple thread dumps, lock owners, JVM deadlock detection |
| WebFlux event loop blocked | Few event-loop threads executing blocking code | `reactor-http-nio-*` stacks and `/fast` endpoint latency |
| Client/proxy gave up waiting | External deadline expired while server kept working | Status 504/499/client timeout, backend FINISH log later |
| JVM stop-the-world / GC | Many requests pause together | GC/JFR, heap, container CPU quota |
| Upstream out of capacity | 429/503/5xx or read timeout | `http.client.requests`, tracing, dependency metrics |
| Socket or DNS/TLS error | Request never reaches controller or connect fails | Client connect errors, gateway logs, network traces |

**Do not equate:** "no response for 10 seconds" with "thread deadlock" or "high CPU." A thread in `TIMED_WAITING` on `Thread.sleep` can hold a Tomcat worker while burning virtually zero CPU. A `RUNNABLE` thread does not automatically mean it is actively consuming a CPU core.

## 3. Tracing the Full Request Path

### 3.1. Spring MVC / Tomcat

~~~text
Caller
  |
  +-- DNS / TLS / client connection pool
  |
  +-- Load balancer / ingress / proxy timeout
  |
  +-- TCP accept / connector queue (Tomcat)
  |
  +-- Servlet worker thread
         |
         +-- Filter / Spring Security / DispatcherServlet
         |
         +-- Controller + service / CPU / lock
         |
         +-- Hikari JDBC connection acquisition
         |      '-- SQL / DB locks / DB server
         |
         '-- RestClient outbound connection / network
                '-- remote HTTP service / downstream DB
  |
  '-- HTTP response bytes -> caller
~~~

**Synchronous MVC:** one Servlet worker thread is typically occupied throughout blocking execution. If 200 concurrent requests arrive while only 20 workers exist, excess requests queue. Yet even when Tomcat `busy=max`, the real root cause may be a 5-second downstream call holding every worker hostage.

### 3.2. Spring WebFlux / Reactor Netty

~~~text
Caller -> Reactor Netty event loop
                 |
                 +-- Handler publishes Mono/Flux
                 |       |
                 |       +-- non-blocking timers, WebClient, reactive DB
                 |       |
                 |       '-- Thread.sleep / JDBC / .block ?
                 |             blocks event loop -> stalls many sockets
                 |
                 '-- writes response when publisher signals
~~~

The event loop uses very few threads to multiplex many connections. A single `Thread.sleep(700)` inside a reactive pipeline **subscribed on an event-loop thread** stalls unrelated requests sharing that thread. **Returning `Mono` does not automatically make a callable non-blocking.**

### 3.3. Resource Locator Table

| Resource | Role | When overloaded |
| --- | --- | --- |
| Tomcat request worker | Executes Servlet request processing | `busy≈max`, subsequent requests queue |
| Java monitor/lock | Synchronizes shared state access | Threads `BLOCKED` or lock-waiting |
| Hikari JDBC connection | Leases DB connections | Pending acquire rises, connection timeouts |
| Reactor Netty event loop | I/O and reactive callbacks | Blocking code stalls many channels |
| Reactor Netty HTTP client pool | Leases outbound connections | Pending connections rise |
| Remote dependency | External service execution | Outbound latency/errors spike |
| CPU/GC | Compute and memory management | Hot stacks, throttling, pauses |
| Proxy/client | Routing, connections, and deadlines | 502/503/504 or client timeout while app stays alive |

## 4. First 5 Minutes Investigation Workflow

**Step 1 — capture symptoms:** which routes, since when, share of requests affected, p50/p95/p99, 4xx/5xx statuses, timeout messages, RPS, concurrency, recent deploys, one pod vs. entire cluster.

**Step 2 — find the first latency boundary:** did the request reach ingress, reach the server, enter the controller, or stall on an outbound dependency? Compare timestamps and correlation IDs.

**Step 3 — preserve evidence:** per-pod metrics snapshots, at least two or three thread dumps while the failure is active, JFR if permitted, traces, Hikari gauges, CPU/GC, and timestamped logs.

**Step 4 — rank hypotheses:** inbound worker queue, internal lock/CPU/GC, JDBC pool, outbound HTTP client pool, remote dependency, or event loop.

**Step 5 — mitigate impact:** timeout/retry budgets, rollback, concurrency caps, isolate slow dependencies, scale the right layer, or shed load. Never add production load merely to prove a hypothesis.

**Step 6 — verify:** replay comparable load in a lab/staging environment or after controlled mitigation, measuring tail latency, errors, and saturation before and after.

### 4.1. Build a Timeline Instead of Reading Only a Status Code

~~~text
12:00:00.000  client sends GET /orders/123
12:00:00.010  ingress receives
12:00:00.015  backend request START
12:00:00.025  attempts to acquire Hikari connection
12:00:02.025  Hikari acquire timeout
12:00:02.030  backend deliberately returns 503
~~~

Contrast with:

~~~text
12:00:00.000  client sends GET /orders/123
12:00:00.010  ingress receives
12:00:05.010  ingress returns 504 due to upstream deadline
12:00:06.000  backend finally logs START (sat in queue too long)
12:00:06.100  backend completes, no client left waiting
~~~

These are **illustrative timelines**, not real trace captures. The second case shows **the proxy timed out before the controller even processed the request**. Raising backend SQL query timeouts will not fix it.

### 4.2. One Request Involves Multiple Deadlines

- **Caller deadline:** browser, mobile app, gateway, gRPC caller.
- **Proxy upstream timeout:** gateway/ingress waiting on upstream.
- **TCP connect timeout:** client waiting to connect to remote host.
- **HTTP read/response timeout:** client waiting for bytes/response from remote.
- **Connection pool acquire timeout:** client waiting to lease a pool or Hikari connection.
- **DB query/lock timeout:** DB/JDBC query or lock waits.
- **MVC async request timeout:** processing limit for requests handed off to Servlet async.
- **Reactive total deadline:** `Mono.timeout`/app-level timeout on a Publisher.

They are **not identical** and do not automatically inherit from one another. Determine where exceptions/logs originate and which deadline expires first.

## 5. Metrics to Collect in Spring Boot 3.3

With `spring-boot-starter-actuator`, Spring Boot 3.3 uses Micrometer/Observation. These meters are typically helpful when the corresponding component is initialized and instrumented:

| Meter | Signal |
| --- | --- |
| `http.server.requests` | Count/latency of observed HTTP requests, tagged by uri/status/method |
| `http.client.requests` | Client-side latency when using injected Boot-configured `RestClient.Builder`/`WebClient.Builder` |
| `tomcat.threads.busy` | Number of busy Servlet request workers |
| `tomcat.threads.current` | Current number of Tomcat threads |
| `jvm.threads.live` | Total live Java threads, not just workers |
| `jvm.gc.pause` | GC pause events |
| `process.cpu.usage` | Process CPU, compare against CPU quota/cgroup |
| `jdbc.connections.active` | Leased `DataSource` connections |
| `jdbc.connections.max` | Maximum DB pool connections |
| `hikaricp.connections.active` | Hikari leased connections |
| `hikaricp.connections.pending` | Threads waiting for a Hikari connection |
| `hikaricp.connections.timeout` | Hikari timeout counter per instrumentation |
| `reactor.netty.connection.provider.active.connections` | Client HTTP pool active connections when metrics enabled |
| `reactor.netty.connection.provider.pending.connections` | HTTP client pending acquire queue when metrics enabled |

**Missing meter ≠ value of zero.** For example, Tomcat metrics in Boot 3.3 require:

~~~properties
server.tomcat.mbeanregistry.enabled=true
~~~

Without the MBean Registry enabled, Boot **does not register** Tomcat meters. Reactor Netty client connection providers also require metrics enabled (typically `ConnectionProvider.builder(...).metrics(true)`) plus real traffic before gauges appear. Do not confuse Reactor Netty's **client pool** with inbound event-loop threads.

### 5.1. Enable Actuator for the Lab, Never Publicly in Production

~~~properties
management.endpoints.web.exposure.include=health,metrics
server.tomcat.mbeanregistry.enabled=true
~~~

Example local queries:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
~~~

`/actuator/metrics` is a **diagnostic endpoint** requiring explicit exposure and protection via auth/network policy. Never expose `threaddump`, `heapdump`, `env`, `configprops`, or detailed metrics openly on the Internet.

**Sampling caveat:** when all Tomcat workers are occupied, requests to `/actuator/metrics` itself can queue and stall. Production relies on a metrics scraper/agent recording time-series history rather than running `curl` ad-hoc during an outage.

### 5.2. Hung Request Timers May Not Show Up Yet

Micrometer `http.server.requests` is a timer tied to observation lifecycle; a sample for **an unfinished request** has not yet been recorded into completed request counts or durations. Consequently:

- p95 of completed requests can omit requests that are still hung.
- A "very slow" request still executing will not appear in the current histogram until it finishes.
- Pair it with **active requests / in-flight gauges or long-task observations if instrumented**, thread dumps, queue depths, and proxy timeouts.
- When instrumenting custom timers, separate ongoing tasks from completed measurements.

**Never conclude "`http.server.requests` p95 looks fine so nothing is hanging."**

### 5.3. Route-Level and Tag Cardinality

Typical tags include `method`, `outcome`, `status`, and `uri` template. Measure `/orders/{id}` instead of raw `/orders/12345` per customer—raw IDs explode metric cardinality and can leak personal data. Traces can use sampling and correlation IDs, but never log tokens, `Authorization` headers, or sensitive raw request bodies.

## 6. Thread Dumps: Evidence When Workers Are Held or Deadlocked

### 6.1. Capture JVM PID and Multiple Snapshots

On JDK 17, inside the proper host/container namespace with sufficient permissions:

~~~bash
jcmd -l
jcmd <PID> Thread.print -l > thread-1.txt
sleep 2
jcmd <PID> Thread.print -l > thread-2.txt
sleep 2
jcmd <PID> Thread.print -l > thread-3.txt
~~~

`<PID>` is a placeholder for the actual process ID. `jcmd` usually requires a compatible user/group matching the target JVM; container/namespace isolation can prevent `jcmd -l` from seeing processes in other namespaces.

**Take multiple snapshots** because a stack in `SocketInputStream.read` for 20 ms can be normal, whereas the same stack staying frozen for seconds across concurrent requests warrants investigation. There is no reason to capture 100 dumps per second in production.

### 6.2. Common Signatures

| State / stack | Proper interpretation |
| --- | --- |
| `http-nio-8080-exec-*` + `Thread.sleep` | Servlet worker held, usually using minimal CPU |
| `HikariPool.getConnection` / `ConcurrentBag.borrow` | Request waiting on JDBC pool; inspect pending/acquire times |
| `SocketInputStream.read`, JDK HTTP client read | Waiting on network/remote; inspect outbound timeouts and dependencies |
| `java.lang.Object.wait` or `LockSupport.park` | Waiting on condition/lock/pool; check context/owner |
| Java state `BLOCKED` on synchronized monitor | Waiting to enter monitor; find the owning thread |
| `reactor-http-nio-*` + `Thread.sleep`/blocking JDBC | Event-loop blocking hazard |
| Unusual GC/JVM thread activity | Needs GC logs/JFR; do not judge from one thread name |
| `RUNNABLE` | Could be burning CPU or doing native I/O; needs CPU profile |

**Deadlock** is a cyclic wait where threads cannot make progress. **Thread starvation** means too few workers remain because requests are holding/waiting on them. **Lock contention** means many threads wait on a lock whose owner can still finish; never assume lock contention is automatically a deadlock.

### 6.3. Illustrative Stack Snippets

~~~text
"http-nio-8080-exec-2" TIMED_WAITING
  at java.lang.Thread.sleep
  at com.example.mvc.DiagController.worker(...)

"http-nio-8080-exec-3" WAITING
  at ... HikariPool.getConnection(...)
  at com.example.mvc.DiagController.pool(...)

"reactor-http-nio-2" TIMED_WAITING
  at java.lang.Thread.sleep
  at com.example.reactive.LoopController.bad(...)
~~~

These stacks are **abbreviated examples**; exact thread names, Java line numbers, and native frames vary by environment.

## 7. JFR, CPU/GC, and Blocking Diagnostics

### 7.1. Java Flight Recorder (JFR)

On JDK 17:

~~~bash
jcmd <PID> JFR.start name=incident settings=profile duration=30s filename=incident.jfr
~~~

Open `incident.jfr` in Java Mission Control (JMC) or compatible JFR tooling. Look for:

- CPU hotspots / repeated stack samples.
- Monitor/lock contention and thread parking.
- Socket read/write events and file I/O.
- GC pauses / allocation spikes.
- Time correlation between spikes and HTTP p99/errors.

Note that profiling/JFR carries some overhead and captures class names, file paths, and sensitive metadata; bound retention, storage, and access controls. Never leave `settings=profile` running indefinitely without policy.

### 7.2. Low CPU Usage Yet High p99

This is a signal to investigate **waiting**, not "the JVM has no issues." Check:

- Tomcat `busy` near `max`.
- Hikari pending or HTTP client pool pending.
- Thread dumps showing remote socket waits, locks, or sleep.
- Downstream p95, DB slow queries, and lock waits.
- Container CPU throttling (process CPU metrics alone cannot reveal cgroup/quota throttling in every case).

### 7.3. High CPU Yet Flat Throughput

Could be CPU-bound business logic, serialization, regexes, encryption, GC thrashing, or excessive context switching. Use JFR/CPU sampling to isolate hot paths. Raising Tomcat threads or event-loop count will not fix a CPU-bound algorithm and can worsen context-switching overhead.

### 7.4. BlockHound Is Only a Supporting Tool

BlockHound helps detect certain blocking calls on Reactor non-blocking threads during dev/testing, yet it has JDK/instrumentation compatibility requirements and does not catch every blocking call. Never treat "BlockHound didn't alert" as proof zero blocking exists; combine profiling, thread dumps, code review, and comparative load tests.

## 8. Lab A — Spring MVC: Reproducing Worker Exhaustion, Hikari Starvation, Lock Waits, and Slow Downstream

A **Java 17, Spring Boot 3.3.5, Maven** project with embedded Tomcat on port `8080`. Tomcat workers and Hikari pool are intentionally kept tiny for easy reproduction. To avoid affecting other systems, the lab binds `127.0.0.1`; never ship these sleep/lock endpoints in production.

### 8.1. Directory Structure

~~~text
mvc-incident-lab/
├── pom.xml
├── downstream/
│   └── RemoteStub.java
├── tools/
│   └── load.py
└── src/main/
    ├── java/com/example/mvc/
    │   ├── MvcIncidentApplication.java
    │   └── DiagController.java
    └── resources/
        └── application.properties
~~~

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-incident-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
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
~~~

`starter-web` provides Servlet MVC/Tomcat for the lab. `starter-jdbc` brings HikariCP, with H2 solely to simulate acquiring/holding connections. `starter-actuator` exposes metrics for observation.

### 8.3. `application.properties`

~~~properties
server.address=127.0.0.1
server.port=8080

# Intentionally very small limit: for simulation only.
server.tomcat.threads.max=6
server.tomcat.mbeanregistry.enabled=true

spring.datasource.url=jdbc:h2:mem:incident;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=2
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=800

app.remote.base-url=http://127.0.0.1:8091

management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
~~~

**Read the config carefully:** Hikari `connection-timeout=800` is the wait limit for **acquiring a DB connection** (in milliseconds), not a query timeout or JDBC socket timeout. `server.tomcat.threads.max=6` caps request workers, not a 6-second timeout. `server.tomcat.mbeanregistry.enabled=true` is required for Tomcat meters in Boot 3.3.

### 8.4. Main Class

**`src/main/java/com/example/mvc/MvcIncidentApplication.java`:**

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcIncidentApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcIncidentApplication.class, args);
    }
}
~~~

### 8.5. Controller Implementing Four Failure Modes

**`src/main/java/com/example/mvc/DiagController.java`:**

~~~java
package com.example.mvc;

import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@RestController
@RequestMapping("/api")
public class DiagController {

    private final DataSource dataSource;
    private final RestClient remote;
    private final Object oneSharedLock = new Object();

    public DiagController(
            DataSource dataSource,
            RestClient.Builder builder,
            @Value("${app.remote.base-url}") String baseUrl) {
        this.dataSource = dataSource;

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(500));
        factory.setReadTimeout(Duration.ofMillis(1200));
        this.remote = builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @GetMapping("/fast")
    public String fast() {
        return "fast-ok";
    }

    @GetMapping("/worker")
    public ResponseEntity<String> worker(
            @RequestParam(defaultValue = "1500") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("bad ms");
        }
        try {
            Thread.sleep(ms); // DELIBERATELY hold Servlet worker.
            return ResponseEntity.ok("worker:" + ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted");
        }
    }

    @GetMapping("/pool")
    public ResponseEntity<String> pool(
            @RequestParam(defaultValue = "1500") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("bad ms");
        }
        try (Connection c = dataSource.getConnection()) {
            // Holding a Hikari lease while waiting: ANTI-PATTERN.
            Thread.sleep(ms);
            return ResponseEntity.ok("pool:" + ms);
        } catch (SQLException ex) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("db connection unavailable");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted");
        }
    }

    @GetMapping("/lock")
    public ResponseEntity<String> lock(
            @RequestParam(defaultValue = "1500") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("bad ms");
        }
        synchronized (oneSharedLock) {
            try {
                Thread.sleep(ms); // DELIBERATELY hold Java monitor.
                return ResponseEntity.ok("lock:" + ms);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE).body("interrupted");
            }
        }
    }

    @GetMapping("/remote/{kind}")
    public ResponseEntity<String> remote(
            @PathVariable String kind) {
        if (!("fast".equals(kind) ||
                "slow".equals(kind) ||
                "hang".equals(kind))) {
            return ResponseEntity.badRequest().body("bad kind");
        }
        try {
            String body = remote.get()
                    .uri("/remote/{kind}", kind)
                    .retrieve()
                    .body(String.class);
            return ResponseEntity.ok(body == null ? "" : body);
        } catch (RestClientException ex) {
            // Demo: network/read/remote errors mapped to 503.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("remote unavailable");
        }
    }
}
~~~

**Diagnostic notes:**

- `/fast` does no sleeping, JDBC, or remote calls; used as the **control**.
- `/worker` holds a Tomcat worker in `TIMED_WAITING` while CPU stays low.
- `/pool` holds both a Tomcat worker and a Hikari JDBC connection. With `active=2` and extra pending requests, Hikari times out after 800ms; the lab chooses HTTP **503**, though Hikari **does not impose an HTTP status automatically**.
- `/lock` uses a single Java monitor shared across requests. Remaining threads enter `BLOCKED` waiting on the monitor; that is contention, **not necessarily deadlock**.
- `/remote` uses Boot-injected `RestClient.Builder`, enabling `http.client.requests` client observations. `SimpleClientHttpRequestFactory` sets connect/read timeouts, yet is **not an outbound HTTP connection pool with pending gauges**.
- `/fast` has no downstream or `RestClient` dependency; if `/fast` slows down while `/worker` is under load, suspect the shared Tomcat worker pool.
- Never return raw stack traces, hostnames, or internal exception details in lab responses. Production logs should capture correlation IDs/error classes safely.

## 9. Standalone Downstream Stub Using JDK 17

To create a clean remote dependency without another Maven project, use the built-in JDK HTTP server.

**`downstream/RemoteStub.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class RemoteStub {

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8091), 0);
        server.createContext("/remote/", RemoteStub::handle);
        server.setExecutor(Executors.newFixedThreadPool(8));
        server.start();
        System.out.println("RemoteStub started at 127.0.0.1:8091");
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        String path = exchange.getRequestURI().getPath();
        String kind = path.substring("/remote/".length());

        long millis;
        switch (kind) {
            case "fast" -> millis = 0L;
            case "slow" -> millis = 900L;
            case "hang" -> millis = 3000L;
            default -> {
                exchange.sendResponseHeaders(404, -1);
                exchange.close();
                return;
            }
        }

        try {
            Thread.sleep(millis); // Simulate dependency latency.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }

        byte[] bytes = ("remote:" + kind)
                .getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
~~~

Compile and run in terminal A (from project root):

~~~bash
cd downstream
javac --add-modules jdk.httpserver RemoteStub.java
java --add-modules jdk.httpserver RemoteStub
~~~

Run Spring Boot in terminal B:

~~~bash
cd mvc-incident-lab
mvn spring-boot:run
~~~

Note: `cd mvc-incident-lab` above assumes terminal B starts in the **parent directory containing the project**; if already at the project root, simply run `mvn spring-boot:run`.

In terminal C:

~~~bash
curl -i http://127.0.0.1:8080/api/fast
curl -i "http://127.0.0.1:8080/api/worker?ms=1500"
curl -i "http://127.0.0.1:8080/api/pool?ms=1500"
curl -i "http://127.0.0.1:8080/api/lock?ms=1500"
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/remote/slow
curl -i http://127.0.0.1:8080/api/remote/hang
~~~

Single-request outcomes while the remote stub is running:

| Endpoint | Typical expectation |
| --- | --- |
| `/api/fast` | HTTP 200, body `fast-ok` |
| `/api/worker?ms=1500` | HTTP 200, body `worker:1500` after ~1.5s |
| `/api/pool?ms=1500` | HTTP 200 if connection acquired in time |
| `/api/lock?ms=1500` | HTTP 200 if not interrupted |
| `/api/remote/fast` | HTTP 200, body `remote:fast` |
| `/api/remote/slow` | HTTP 200 after ~0.9s, if client does not time out |
| `/api/remote/hang` | Usually **HTTP 503** due to 1.2s client read timeout |

These expectations follow the lab's code and timeouts, not guaranteed fixed wall-clock timings on every machine. If the remote stub is not running, `/remote/fast` also returns 503 due to connection refused/timeout. Never call `/remote/hang` "the controller deadlocked": the root cause is the remote deliberately sleeping past the client deadline.

## 10. Script to Generate Concurrent Load and Collect Latencies/Statuses

**`tools/load.py`**, using Python 3 standard library with no `pip` needed:

~~~python
import concurrent.futures
import math
import sys
import time
import urllib.error
import urllib.request

if len(sys.argv) != 4:
    raise SystemExit("Usage: python3 tools/load.py URL COUNT CONCURRENCY")

url = sys.argv[1]
count = int(sys.argv[2])
concurrency = int(sys.argv[3])

if count < 1 or concurrency < 1 or concurrency > 40:
    raise ValueError("count >= 1 and 1 <= concurrency <= 40")

def one(_):
    begin = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            resp.read()
            status = str(resp.status)
    except urllib.error.HTTPError as ex:
        ex.read()
        status = str(ex.code)
    except Exception:
        status = "ERR"
    ms = (time.perf_counter() - begin) * 1000
    return ms, status

begin = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency) as executor:
    results = list(executor.map(one, range(count)))
elapsed = time.perf_counter() - begin

latencies = sorted(ms for ms, _ in results)

def percentile(p):
    idx = max(0, math.ceil(len(latencies) * p) - 1)
    return round(latencies[idx], 1)

statuses = {}
for _, status in results:
    statuses[status] = statuses.get(status, 0) + 1

print("count=", count, "concurrency=", concurrency)
print("elapsed_s=", round(elapsed, 3))
print("throughput_rps=", round(count / elapsed, 2))
print("p50_ms=", percentile(0.50))
print("p95_ms=", percentile(0.95))
print("p99_ms=", percentile(0.99))
print("status_counts=", statuses)
~~~

This is a **closed-loop load script**: each worker sends its next request after the previous completes. It is useful for spotting trends, though it **does not replace** proper capacity tests with open-loop arrival rates, warm-ups, rate limiting, timeout distributions, and multiple clients. A p99 from a few dozen samples is noisy; never treat one run as an official SLO. Only run against local/staging apps you own.

## 11. Experiment A1: Holding Tomcat Workers Keeps CPU Low

From the MVC project root:

~~~bash
python3 tools/load.py \
  "http://127.0.0.1:8080/api/worker?ms=1500" 24 12
~~~

Tomcat has at most **6 workers**. When 12 concurrent calls arrive, roughly six workers are occupied for 1.5 seconds while the rest wait in the connector/queue. Because those threads sit in `Thread.sleep`, process CPU stays low while p95/p99 climb from worker queueing.

While the batch runs, test `/api/fast` in another terminal:

~~~bash
curl -w "\nTOTAL=%{time_total}s CODE=%{http_code}\n" \
  -o /dev/null \
  http://127.0.0.1:8080/api/fast
~~~

Normally `/api/fast` is instant, yet it can stall when all workers are occupied. This proves **shared-resource contention**, not that `/fast`'s own code is slow.

Poll metrics mid-batch:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.current
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.usage
~~~

When `busy=max`, even the Actuator HTTP call can queue. Collect via a time-series scraper and compare multiple snapshots. Thread dumps will show `http-nio-8080-exec-*` inside `Thread.sleep`.

### 11.1. Does "Raising Tomcat max=500" Fix It?

It can shrink queueing only if the sole bottleneck is worker availability **and** downstream/CPU/heap still have headroom. If workers are held by a 10s remote API, raising max workers drives more concurrency into the remote service, exhausting HTTP client/DB pools, increasing memory, and worsening the collapse.

The right fix addresses why workers are held: set client timeouts and concurrency budgets, trim slow calls, add valid caching, bulkheads, async where appropriate, and scale the right layer. Raise max threads **only after benchmarking**.

## 12. Experiment A2: Hikari Pool Acquisition Timeout

Run:

~~~bash
python3 tools/load.py \
  "http://127.0.0.1:8080/api/pool?ms=1500" 24 12
~~~

Lab Hikari has **`maximum-pool-size=2`** and `connection-timeout=800ms`, while each request holds a connection for 1500ms. Typically:

1. Two requests acquire the two DB connections and hold them.
2. Subsequent requests wait in `dataSource.getConnection()`.
3. Several wait past 800ms and receive `SQLException`, causing the controller to return **503**.
4. CPU remains low while Tomcat workers remain occupied waiting.
5. Once sleep finishes, `try-with-resources` returns connections to Hikari.

Measure:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.active
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.timeout
~~~

**`pending` is an instantaneous gauge.** Reading it after load stops may show 0 even if 10 threads waited earlier. Scrape during peak load or inspect timeout counters and log timestamps.

### 12.1. Why Isn't This a Real "Slow DB Query"?

The lab deliberately holds a JDBC connection and sleeps; H2 runs no slow query. In real systems, pool exhaustion stems from:

- Long-running SQL queries or DB locks.
- Transactions holding connections open while making remote HTTP calls.
- Connection leaks (forgetting to close).
- Pool too small relative to concurrency and DB capacity.
- DB max connections/CPU/IO saturated.
- Too many replicas, each maintaining its own pool.

Measure **acquire wait**, **connection hold duration**, **SQL duration**, and **DB locks**. Seeing `active=max` with `pending=0` and fast acquires is **not enough** to prove pool starvation.

### 12.2. Hikari Timeout Is Not SQL Timeout

`spring.datasource.hikari.connection-timeout` limits **waiting to lease a connection**. It does not cancel an in-flight SQL statement after acquiring a connection. Query timeouts are configured via driver/JDBC `Statement.setQueryTimeout`, transaction timeouts, database server timeouts, or the data-access layer; exact semantics depend on the driver/DB. Never "fix" SQL lock waits by setting acquisition timeout to infinity.

## 13. Experiment A3: Lock Contention Differs from Deadlock

Run:

~~~bash
python3 tools/load.py \
  "http://127.0.0.1:8080/api/lock?ms=1500" 24 12
~~~

Only one thread enters `synchronized (oneSharedLock)` at a time. Other requests wait on the monitor; thread dumps show `BLOCKED` at `DiagController.lock(...)`, while the lock-owning thread sleeps.

This is **lock contention**, not **deadlock**: the owner eventually exits `synchronized` and releases the lock. True deadlock requires a cycle (e.g., thread 1 holds lock A waiting on B; thread 2 holds B waiting on A). Take multiple thread dumps or JFR `MonitorEnter` events and trace lock owners/cycles before concluding.

### 13.1. States to Distinguish

- **`BLOCKED`**: JVM thread waiting to acquire an intrinsic monitor. Can be normal under brief contention.
- **`WAITING`/`TIMED_WAITING`**: `wait`/`park`/`sleep` or pool wait; does not equal deadlock.
- **Deadlock detection**: thread dumps/tooling may flag Java-level deadlocks, though you still need to inspect lock types and context.
- **Starvation**: threads never get served because pool/executors are too small or hogged by other tasks; requires no cycle.

**Mitigation:** shrink critical sections, never hold locks across I/O, minimize shared mutable state, and pick proper concurrency primitives. Never wrap remote HTTP calls or long SQL transactions in `synchronized`.

## 14. Experiment A4: Slow Downstream and Caller Timeouts

Start `RemoteStub` first. Compare:

~~~bash
python3 tools/load.py \
  http://127.0.0.1:8080/api/remote/fast 24 8

python3 tools/load.py \
  http://127.0.0.1:8080/api/remote/slow 24 8

python3 tools/load.py \
  http://127.0.0.1:8080/api/remote/hang 24 8
~~~

The stub responds immediately for `fast`, ~900ms for `slow`, and ~3000ms for `hang`. MVC's `RestClient` has a 1200ms read timeout, so `hang` triggers an exception that the controller maps to 503. **HTTP 503 here is the lab's policy**, not automatic behavior of every `RestClient`.

Fetch:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/http.client.requests
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

Using Boot-injected `RestClient.Builder` lets Spring Boot instrument outbound HTTP with `http.client.requests`. Creating `RestClient.create()` directly bypasses Boot observation customizers, losing client spans and meters.

### 14.1. HTTP 504 at the Gateway

If NGINX/ingress waits 1 second for upstream while the backend takes 3 seconds, the gateway can return **504 Gateway Timeout** to the client. The backend may still log "completed" after the caller left. **Do not assume the Spring Boot controller emitted 504** solely from the client-visible HTTP status.

Conversely, HTTP 503 returned intentionally by the lab controller after a read timeout is **a backend response**, not a proxy 504. Correlate headers, proxy access/error logs, and trace IDs to find the source of the status.

### 14.2. Client Canceled Request, Yet Server Still Wrote to DB?

Yes. In synchronous MVC, client socket disconnection **does not automatically roll back transactions or immediately interrupt the working thread**. If a business side effect commits and the client retries a POST without an idempotency key, duplicate transactions can happen. Enforce timeouts, deadlines, and idempotency in the business contract.

## 15. Lab B — Spring WebFlux: Blocked Event Loop vs. Non-Blocking Reactive

Create a **separate Maven project**—never add `spring-boot-starter-web` to the WebFlux project. The same 700ms delay consumes resources completely differently depending on implementation:

- `/loop/bad`: `Mono.fromCallable` containing `Thread.sleep`, intentionally blocking when subscribed on the event loop.
- `/loop/good`: non-blocking `Mono.delay` timer.
- `/loop/offload`: executes the blocking callable on `Schedulers.boundedElastic()`, keeping the event loop unblocked.
- `/loop/ping`: fast control endpoint with no delay.

### 15.1. Structure

~~~text
webflux-incident-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/loop/
    │   ├── LoopApplication.java
    │   └── LoopController.java
    └── resources/
        └── application.properties
~~~

### 15.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-incident-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

### 15.3. `application.properties`

~~~properties
server.address=127.0.0.1
server.port=8082
management.endpoints.web.exposure.include=health,metrics
~~~

### 15.4. Main Class

**`src/main/java/com/example/loop/LoopApplication.java`:**

~~~java
package com.example.loop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoopApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoopApplication.class, args);
    }
}
~~~

### 15.5. `LoopController.java`

~~~java
package com.example.loop;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/loop")
public class LoopController {

    @GetMapping("/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/bad")
    public Mono<String> bad(
            @RequestParam(defaultValue = "700") int ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid ms"));
        }

        // Anti-pattern: blocking code runs when Publisher is subscribed.
        return Mono.fromCallable(() -> {
            Thread.sleep(ms);
            return "bad:" + Thread.currentThread().getName();
        });
    }

    @GetMapping("/good")
    public Mono<String> good(
            @RequestParam(defaultValue = "700") int ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid ms"));
        }

        // Reactive timer: does not hold the event-loop thread while waiting.
        return Mono.delay(Duration.ofMillis(ms))
                .map(tick -> "good:" + Thread.currentThread().getName());
    }

    @GetMapping("/offload")
    public Mono<String> offload(
            @RequestParam(defaultValue = "700") int ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid ms"));
        }

        return Mono.fromCallable(() -> {
            Thread.sleep(ms);
            return "offload:" + Thread.currentThread().getName();
        }).subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

**Correctness notes:**

1. `Mono.fromCallable` does not spawn its own thread. When WebFlux subscribes directly on the event loop, blocking `Thread.sleep` holds `reactor-http-nio-*`.
2. `Mono.delay` uses Reactor's non-blocking timer scheduler without consuming an event-loop thread during the wait. The thread name inside `map` is not an API contract.
3. `boundedElastic` uses a bounded pool and queue to offload legacy blocking calls—**it does not provide unlimited threads**. Once the pool/queue saturates, it too delays or rejects tasks.
4. In WebFlux, calling `Mono.block()` on a non-blocking event-loop thread can throw an error or block depending on context; never use it to turn reactive pipelines synchronous inside controllers.
5. If you add `spring-boot-starter-web` to the same project, Boot usually picks MVC/Servlet when both exist, so the test no longer measures the Netty event loop as intended.

### 15.6. Running the WebFlux Test

From `webflux-incident-lab`:

~~~bash
mvn clean package
java -jar target/webflux-incident-lab-0.0.1-SNAPSHOT.jar
~~~

In another terminal:

~~~bash
curl -i http://127.0.0.1:8082/loop/ping
curl -i http://127.0.0.1:8082/loop/bad
curl -i http://127.0.0.1:8082/loop/good
curl -i http://127.0.0.1:8082/loop/offload
~~~

All three endpoints with `ms=700` respond after ~700ms for a single call, yet differ dramatically in execution threads and concurrency capacity.

Run the load script from the MVC project (adjust the relative path if your layout differs):

~~~bash
python3 ../mvc-incident-lab/tools/load.py \
  http://127.0.0.1:8082/loop/bad 40 20

python3 ../mvc-incident-lab/tools/load.py \
  http://127.0.0.1:8082/loop/good 40 20

python3 ../mvc-incident-lab/tools/load.py \
  http://127.0.0.1:8082/loop/offload 40 20
~~~

**To lower the event-loop thread count so the lab reproduces contention more sharply**, stop the process and start a **different lab process** with:

~~~bash
java -Dreactor.netty.ioWorkerCount=2 \
  -jar target/webflux-incident-lab-0.0.1-SNAPSHOT.jar
~~~

`reactor.netty.ioWorkerCount` is a Reactor Netty system property; do not treat it as a Spring Boot timeout. Never change production event-loop worker counts arbitrarily. On multi-core machines, results vary with worker count; base conclusions on thread stacks, request latencies, and controls rather than a single p95 run.

### 15.7. Observing `/loop/ping` While `/loop/bad` Runs

While generating load against `/loop/bad`, run:

~~~bash
curl -w "\nCODE=%{http_code} TOTAL=%{time_total}s\n" \
  -o /dev/null \
  http://127.0.0.1:8082/loop/ping
~~~

When event loops are held by blocking calls, even `/loop/ping` stalls despite doing zero sleeping itself. With `/loop/good` and `/loop/offload`, the event loop keeps serving sockets; total latency still depends on `boundedElastic` capacity, CPU, network, and scheduling.

Capture a thread dump under load to see `reactor-http-nio-*` stuck in `Thread.sleep` (bad case), whereas `offload` runs on `boundedElastic-*`. **Thread names are only clues**; verify with stacks, correlation, and time series.

## 16. Outbound HTTP Connection Pools Can Also "Hang" `WebClient`

When WebFlux uses `WebClient` with Reactor Netty HTTP, requests can block waiting to **lease a connection from `ConnectionProvider`** before the remote HTTP call even starts. This differs from **inbound event-loop blocking**.

### 16.1. Conditional Metrics

Reactor Netty `ConnectionProvider` gauges/timers typically include:

~~~text
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.max.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
~~~

They appear only when the **outbound pool is instrumented** and has traffic. Not seeing a pending meter does not prove nothing is waiting, and connection count does not always equal request count (especially with HTTP/2 multiplexing).

### 16.2. Dedicated Client Pool Configuration Example

This class can be added to the **WebFlux lab project**; to generate actual traffic, inject the `backendClient` bean into a controller/service calling downstream:

~~~java
package com.example.loop;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class BackendHttpConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider backendProvider() {
        return ConnectionProvider.builder("backend")
                .maxConnections(2)
                .pendingAcquireMaxCount(4)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient backendClient(
            WebClient.Builder builder,
            ConnectionProvider backendProvider) {
        HttpClient client = HttpClient.create(backendProvider)
                .responseTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("http://127.0.0.1:8091")
                .clientConnector(new ReactorClientHttpConnector(client))
                .build();
    }
}
~~~

**Distinct timeouts and limits:**

- `pendingAcquireTimeout(500ms)`: max wait to lease a connection from the pool per policy.
- `responseTimeout(2s)`: response wait per Reactor Netty semantics on the outbound exchange, not a combined timer for every phase.
- `maxConnections(2)`: caps pooled connections, **not** event-loop threads.
- `pendingAcquireMaxCount(4)`: bounds queued acquisitions to avoid unbounded waiting.
- `metrics(true)`: enables pool meters when Micrometer is present.
- `@Bean(destroyMethod="dispose")`: ensures Spring disposes the provider on context shutdown.
- Auto-configured `WebClient.Builder` preserves Boot observations.

If the remote service is slow or returning 429/503, enlarging the pool rarely helps; it can push even more concurrency into an overloaded dependency. Evaluate pending acquires, remote p95/errors, and per-host budgets before raising `maxConnections`.

### 16.3. Client Total Deadline Using `Mono.timeout`

Inside a **reactive service** holding the configured `WebClient` bean:

~~~java
Mono<String> result = backendClient.get()
        .uri("/remote/slow")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
~~~

This is a **snippet inside a scope where `backendClient` exists**, not a standalone runnable class. `Mono.timeout` sets a deadline on the publisher chain, while connect, response, and pool timeouts must still be set at their respective layers to prevent unbounded waits or ambiguous exceptions.

**`timeout` does not necessarily abort an in-flight blocking JDBC call** on another thread; cancellation is cooperative depending on source/driver. For write side effects, idempotency and transaction semantics remain the application's responsibility.

## 17. Timeout Table — Configuring the Right Layer for the Right Effect

| Timeout / limit | Applies to | Do NOT use to |
| --- | --- | --- |
| `server.tomcat.connection-timeout` | Time Tomcat waits for the request URI line after accepting connection | Cap a 30s synchronous controller |
| `server.tomcat.keep-alive-timeout` | Waiting for next HTTP request on a keep-alive connection | Cap total business execution time |
| `spring.mvc.async.request-timeout` | MVC Servlet **asynchronous request processing** | Interrupt a sync `@GetMapping` calling `Thread.sleep` |
| `spring.datasource.hikari.connection-timeout` | Waiting to **lease a JDBC connection** from Hikari | Bound SQL query duration after acquiring a connection |
| JDBC `Statement.setQueryTimeout` | JDBC statement execution (driver/DB semantics) | TCP connect, Hikari acquire wait |
| `SimpleClientHttpRequestFactory#setConnectTimeout` | `RestClient` connect phase | Wait for entire remote server execution |
| `SimpleClientHttpRequestFactory#setReadTimeout` | Waiting to read HTTP bytes from remote | TCP connect / overall app deadline |
| Reactor Netty `CONNECT_TIMEOUT_MILLIS` | TCP connect | HTTP response/body duration |
| Reactor Netty `responseTimeout(Duration)` | HTTP response wait per client semantics | Pool acquire and total user deadline |
| Reactor Netty `pendingAcquireTimeout` | Waiting to acquire outbound client connection | Remote server compute time |
| Reactor `Mono.timeout` | Deadline on Publisher chain | Guarantee aborting blocking/native side effects |
| Proxy/gateway upstream timeout | Waiting for backend response | Control Java handler/server threads |
| Client `curl --max-time` | Total curl request time per client flag | Alter server policy |
| `spring.lifecycle.timeout-per-shutdown-phase` | Graceful lifecycle shutdown phase | Runtime HTTP request timeout while app is up |

### 17.1. Two Common Spring Boot Traps

**Trap A:** setting `server.tomcat.connection-timeout=10s` expecting a controller doing a 120s DB call to be aborted at 10s. Wrong: that property governs the connector waiting for the request URI line, not execution deadlines.

**Trap B:** setting `spring.mvc.async.request-timeout=10s` while the controller returns `String` synchronously and calls `Thread.sleep(120000)`. That timeout applies primarily to **Servlet async requests** like `Callable`/`DeferredResult`; it does not convert a sync handler into async or kill a sleeping thread.

### 17.2. The Server Does Not Automatically Return HTTP 504 for Every Timeout

If the client receives 504, a gateway/proxy most likely emitted it upon upstream deadline expiration. A Spring Boot app can map `TimeoutException` to 504 via `@ControllerAdvice` or filters, yet that is explicit code/config, **not a universal default for every timeout**.

### 17.3. Budgeting Deadlines Across Layers

Hypothetical example: user SLA 4 seconds, gateway timeout 3.5s, backend calls a remote service.

~~~text
client total deadline          4.0s
proxy upstream deadline       3.5s
backend business deadline     3.0s
remote HTTP timeout           2.0s
pool acquire timeout          0.3s
retry/backoff within budget   bounded
~~~

This is **illustrative**, not a universal template. Remote connect/read/pool timeouts can sum across stages or overlap; ensure total critical-path latency plus retries fits inside the caller deadline. Never configure every dependency timeout to 30s when callers time out at 3s.

## 18. Correlation IDs, Structured Logs, and Tracing

During an incident, the hardest part is stitching logs across client, ingress, app, HTTP client, and DB.

### 18.1. What to Log?

- UTC timestamps with sufficient precision at every hop.
- Request ID / trace ID / span ID when available.
- HTTP method / URI **template**, status, duration.
- Pod/instance ID and app version.
- Downstream logical service name and outcome/timeout class.
- Properly instrumented Hikari / client pool acquire, SQL, and remote durations.
- Start/finish/cancel markers for long work or async lifecycles.

**Never log** raw `Authorization` headers, passwords, session cookies, user PII, full bodies, or access tokens. Avoid user-supplied URL paths as high-cardinality metric labels.

### 18.2. Example Correlation Timeline

~~~text
trace=abc request_id=r-1 ingress_start=12:00:01.000
trace=abc request_id=r-1 mvc_start=12:00:01.020
trace=abc request_id=r-1 hikari_acquire_begin=12:00:01.040
trace=abc request_id=r-1 hikari_acquire_end=12:00:01.540
trace=abc request_id=r-1 db_query_end=12:00:01.600
trace=abc request_id=r-1 downstream_end=12:00:02.900
trace=abc request_id=r-1 mvc_finish=12:00:02.950
~~~

These lines are illustrative. Define span/interval boundaries clearly; never add durations of **nested** or **parallel child spans** thinking they equal total latency. Use the **critical path** for fan-outs.

### 18.3. Tracing Is Not Complete Just Because Actuator Is Present

Spring Boot Actuator provides observations/metrics, whereas **distributed traces** require Micrometer Tracing/OpenTelemetry bridge dependencies/config, exporters, context propagation, and sampling. Outbound HTTP observations usually require injecting Boot's `RestClient.Builder`/`WebClient.Builder` or applying customizers; creating raw clients manually drops instrumentation.

Clocks across machines can drift; prefer trace durations and NTP/clock sync when comparing cross-host timestamps.

## 19. Symptom-Driven Diagnostic Playbook

### 19.1. "Suddenly Every API Is Slow"

1. Check ingress status/response times and traffic spikes.
2. Check CPU quota/throttling, GC pauses, and heap memory.
3. MVC: is Tomcat `busy≈max`? What are worker thread stacks doing?
4. WebFlux: do event-loop threads show blocking stacks? Is `/ping` slow too?
5. Check shared resources: DB pool, HTTP client pool, log appender locks.
6. Check recent rollouts/config changes and downstream health in the same window.

If only one endpoint is slow while `/ping` stays fast, suspect that business route or its specific downstream. If `/ping` slows down too, inspect shared workers, event loops, CPU, or proxies first.

### 19.2. "CPU 10%, 504s Climbing"

Suspect waiting: Tomcat workers stuck in socket reads, pending JDBC pool acquires, downstream latency, proxy routing/caller deadlines. Capture thread dumps + outbound spans + pool gauges; **never bump CPU limits just because you see 504**.

### 19.3. "Hikari Pending Rising, DB CPU Low"

Could be DB locks, long-lived transactions, connection leaks, or the app holding connections while calling remote services. Inspect actual SQL/query plans, connection hold times, transaction boundaries, and total replicas—not just pool max.

### 19.4. "WebFlux p99 Spiked After Integrating a Blocking SDK"

Inspect `reactor-http-nio-*` stack traces. Search for `Thread.sleep`, JDBC, blocking HTTP clients, `Future.get`, file I/O, and `.block()`. Replace with async APIs or bounded offloading; do not raise event-loop counts indefinitely.

### 19.5. "Actuator Metrics Endpoint Is Timing Out Too"

When Tomcat workers are exhausted or the Reactor event loop is blocked, Actuator endpoints **on the same server port** can stall as well. That does not mean Actuator is broken. Rely on external scrape history, JFR, thread dumps, or a separate management port/agent if architecture allows. Using a separate management server port **does not guarantee** the whole process/heap/DB is healthy; it only isolates part of the request path.

### 19.6. "New Failures Appeared Right After an Upgrade"

Check artifact/JDK/library versions, actual web stack, client connection pool defaults and HTTP timeouts, metric names/observations, security filters, virtual-thread settings, and deployment topology. Run a canary under identical traffic mix, comparing p95/p99 and saturation before/after. A single Boot BOM bump can change Reactor Netty, Tomcat, Hikari, and instrumentation versions; never assume tuning derived from an older implementation still holds unchanged.

## 20. Upgrading Spring Boot Without Losing Diagnostic Visibility

This article uses **Boot 3.3.5 + Java 17** for stable imports and config. When upgrading:

- **Boot 2.x → 3.x:** Servlet APIs moved from `javax.servlet.*` to `jakarta.servlet.*`; update imports and versions in filters/interceptors/custom servlets. The lab uses `javax.sql.DataSource` (Java SE), **not `javax.servlet`**, so that import stays valid.
- **Boot 3.3 → 3.4+:** default graceful shutdown shifted from `immediate` to `graceful`; evaluate rollout/termination budgets—unrelated directly to per-request runtime timeouts, yet vital for in-flight traffic during deploys.
- **Reactor Netty upgrades:** connection provider defaults/metrics and event-loop behavior can change across versions/platforms; never copy max pending/connection numbers from "latest" docs into Boot 3.3 without cross-checking.
- **Micrometer/Observation upgrades:** some meters/tags differ or require enabling instrumentation; never assume "missing metric" means utilization=0. Check canonical meter names in `/actuator/metrics` and backend naming normalization.
- **Java 21 virtual threads:** Boot supports virtual threads for Servlet/task execution on compatible versions, yet they **do not turn JDBC/remote services non-blocking** or exempt the WebFlux event loop from blocking. Virtual threads carry trade-offs around pinning, lock contention, and memory.
- **Web stack:** with both `starter-web` and `starter-webflux` on the classpath, Boot usually selects MVC; verify logs and `WebApplicationType` instead of assuming runtime stack from outbound `WebClient`.
- **Timeout configs:** never change a property by name similarity alone; verify versioned docs and test behavior with integration tests.

### 20.1. Post-Upgrade Regression Tests

| Case | What to assert |
| --- | --- |
| 1 fast request | 200 and latency within baseline |
| 20 parallel slow requests | Tail latency and busy workers within bounds |
| Simulated DB pool exhaustion | Fast failure / expected status, no infinite hang |
| Remote timeout | Proper error mapping, no client retry storm |
| WebFlux blocking guard | No known blocking library executing on event loop |
| Graceful shutdown | In-flight handling and deadline match release policy |
| Errors/metrics/tracing | Request IDs, client/server meters, and dashboards remain populated |
| Pod scaling | Aggregate DB connections and downstream rate stay within budget |

**Never deploy the lab stress endpoints to production**: they are deliberate anti-patterns for diagnosis, not production templates.

## 21. Fixing the Right Bottleneck and Preventing Cascading Failures

| Proven root cause | Priority action | Verification data |
| --- | --- | --- |
| Tomcat workers held by downstream | HTTP client deadlines, bulkheads, trim retries, async where suitable | Busy workers, p99, timeouts/errors |
| Lock contention | Shrink critical sections, avoid I/O under lock | `BLOCKED` threads, lock wait time |
| True Java deadlock | Fix lock acquisition order, eliminate cyclic locking | Thread dumps show zero deadlocks |
| Hikari acquire pending | Shorten tx/SQL, cap concurrency, size to DB | Pending/acquire time/DB locks |
| WebFlux event-loop blocking | Reactive I/O or bounded offload | Event-loop responsiveness, JFR, p99 |
| Outbound client pool pending | Reuse `WebClient`/provider, fix remote, bound queue, size pool empirically | Pending time, remote errors |
| Downstream 429/5xx | Rate limits, circuit breakers, jittered retry budget, valid caching | Remote p95/429, drop/retry rate |
| Short proxy timeout | Align deadline budgets or trim backend critical path | Proxy 504 vs. backend completion |
| CPU saturation | Optimize hot paths/serialization, scale CPU properly | CPU profiling, throughput, GC |
| GC pressure | Investigate allocations/heap/GC | JFR GC pauses / heap metrics |

### 21.1. Bulkheads and Backpressure

If a remote service slows down and your app allows unbounded request queueing, every retry amplifies load on the failing dependency. Enforce:

- Per-dependency concurrency limits.
- Bounded queues / pending acquires; explicit overload responses (429/503 per contract).
- Circuit breakers and request deadlines.
- Retries only for transient errors, with exponential backoff + jitter + overall budget.
- Idempotency keys for non-idempotent writes.
- Caching/fallbacks only when business allows stale or partial data.

Never set pool sizes mechanically equal to request workers: DB/server capacity and replica counts dictate useful concurrency.

### 21.2. Re-Measure After Mitigation

Do not compare only average response time; measure p95/p99, error rate, request count, throughput, queue/pending counts, CPU/GC, memory, downstream concurrency, and resource cost. Hold traffic mix, build, quota, and measurement window constant for a fair comparison.

## 22. Common Diagnostic Pitfalls

| Misconception | Why it is wrong |
| --- | --- |
| Low CPU means a healthy server | Threads may be waiting on pools, I/O, or locks |
| Low `http.server.requests` p95 means nothing hangs | In-flight hung requests haven't completed their timer sample |
| Tomcat `threads.busy=max` always means raise max | Workers may be waiting on remote/DB |
| Hikari `active=max` means the DB pool is too small | Check pending, acquire/SQL duration, and DB capacity |
| `server.tomcat.connection-timeout` is a controller timeout | It waits for the request URI line after accept |
| `spring.mvc.async.request-timeout` aborts sync handlers | Applies only to async request processing |
| WebFlux `Mono` is always non-blocking | Callables/JDBC/`Thread.sleep` still block if run on event loop |
| Raising event-loop workers endlessly fixes `.block()` | Doesn't remove blocking code and increases contention |
| `WAITING` in thread dumps means deadlock | Often normal I/O, condition, or connection waits |
| Status 504 definitely came from Spring controller | Often emitted by proxy/gateway |
| Raising Hikari max always boosts throughput | DB can get overwhelmed and suffer lock contention |
| One 30s timeout applies to all layers | Each timeout governs its own phase/boundary |
| Client closing socket rolls back all DB writes | Side effects may already have committed |
| Unresponsive Actuator means Actuator is broken | It may share saturated workers or event loops |
| `@DirtiesContext`/restarts fix hung requests | Only wipes symptoms temporarily; find the root cause |
| One load test and p99 are proof enough | Small samples, client/tool bias, warm-up, and host noise skew results |
| Having `WebClient` means inbound server runs WebFlux | MVC apps can use `WebClient` too |
| Virtual threads eliminate all blocking bottlenecks | DBs, locks, and downstream services still have capacity limits |
| Adding retries when remote is slow helps | Retry storms can worsen outages |

## 23. Scenario Prompts and Self-Check Questions

**Q1.** A Spring MVC backend takes 100 RPS; p99 jumps from 200ms to 8s, CPU is 15%, Tomcat `busy=max`. Give at least three hypotheses and metrics to tell them apart.

**Q2.** Hikari `max=2`, `active=2`, `pending=8`, `connection-timeout=800ms`. Why can the pool time out even with low DB CPU?

**Q3.** Dozens of threads sit in `BLOCKED` waiting on the same lock; is that enough evidence to declare a deadlock?

**Q4.** A thread dump shows `reactor-http-nio-2` in `Thread.sleep` inside `Mono.fromCallable`. Why might unrelated `/ping` requests slow down?

**Q5.** What effect does `spring.mvc.async.request-timeout=3s` have if an MVC controller is synchronous and calls `Thread.sleep(10000)`?

**Q6.** Does `server.tomcat.connection-timeout=3s` terminate a slow SQL query running for 20s?

**Q7.** Why might a client see HTTP 504 while the backend logs `FINISH` successfully?

**Q8.** What metric benefit comes from creating `RestClient` via Boot's injected builder?

**Q9.** Does `reactor.netty.connection.provider.pending.connections` measure inbound Netty event-loop threads or the outbound HTTP pool?

**Q10.** Does `Mono.timeout` guarantee canceling a blocking JDBC statement already sent to the database?

**Q11.** With 8 replicas, each having Hikari `max=20`, what is the aggregate max connections across pools, and why must DB limits be checked?

**Q12.** Why might an unfinished HTTP request not increment the `http.server.requests` sample count yet?

**Q13.** When should thread dumps be captured, and why are multiple snapshots needed?

**Q14.** In Boot 3.3, which property must be enabled to see Tomcat metrics?

**Q15.** Can you enable `spring.threads.virtual.enabled=true` on Java 17 to fix a WebFlux event loop?

**Q16.** After an upgrade, if `tomcat.threads.busy` disappears, what should you check?

**Q17.** When a remote service is returning 429, what can raising the HTTP client connection pool from 20 to 200 cause?

**Q18.** Name four distinct deadlines along an MVC request that queries a DB and calls a remote HTTP service.

**Guided answers:**

1. Workers waiting on downstream/DB, pending Hikari pool, lock contention, or GC; check thread dumps, outbound spans, and Hikari/Tomcat metrics.
2. Connections are leased too long while others wait; low DB CPU does not reveal connection hold times.
3. No; monitor contention can still make progress. Check lock owners/cycles across multiple snapshots.
4. Event loops use few threads across many sockets; blocking hogs the shared event loop.
5. Does not interrupt sync handlers; the property applies to Servlet asynchronous request processing.
6. No; Tomcat `connection-timeout` only governs waiting for the request line after accept.
7. Proxy/caller deadline expired before backend finished; backend kept running after disconnect.
8. Boot observation auto-config/instrumentation populates `http.client.requests` and tracing.
9. Outbound HTTP `ConnectionProvider` pool when metrics are enabled; not inbound event-loop count.
10. No; canceling a blocking/native call does not always abort work in external services.
11. Up to ~160 connections if all replicas hit max; plus DB connections from other clients, jobs, and admins.
12. Timers record completed observations; in-flight requests need dedicated gauges/tracing/dumps.
13. Capture while slowness is happening, spacing a few snapshots seconds apart to distinguish transient waits from long stalls.
14. `server.tomcat.mbeanregistry.enabled=true` plus proper Actuator instrumentation.
15. No; Java 17 lacks standard Java 21 virtual threads, and WebFlux event loops still must not block.
16. Check actual server (Tomcat vs. Netty), MBean Registry, dependencies, and metric names/tags after upgrade.
17. Drives even more concurrent load into a throttling remote service, worsening the outage or retry storm.
18. Hikari acquire timeout, SQL query timeout, HTTP connect/read timeout, and gateway/client total deadline (plus others).

## 24. Production Investigation Checklist

- [ ] Correlation/trace ID links client, ingress, app, DB, and dependencies.
- [ ] Timestamps captured for request arrival, controller START, outbound calls, and FINISH/cancel.
- [ ] Distinguished requests not reaching the app, queued, inside handler, and writing responses.
- [ ] Verified whether the app actually runs MVC/Tomcat or WebFlux/Reactor Netty.
- [ ] Collected p50/p95/p99, RPS, errors, 429/502/503/504, and in-flight counts if available.
- [ ] Collected Tomcat `threads.busy`/current when MBean registry is enabled.
- [ ] Collected Hikari active/pending/acquisition timeouts and SQL/lock evidence.
- [ ] Collected HTTP client metrics and pending acquisitions if using a connection pool.
- [ ] Checked CPU/quota/throttling, GC pauses, heap/threads/FD counts.
- [ ] Captured 2–3 thread dumps / JFR **while the incident is active**, under access controls.
- [ ] Avoided guessing root cause solely from `WAITING`/`BLOCKED`; checked lock owners.
- [ ] Checked for blocking Java/JDBC/HTTP calls on Reactor event-loop threads.
- [ ] Checked proxy/client deadlines before blaming the backend for 504s.
- [ ] Did not confuse Tomcat connector timeouts with sync controller timeouts.
- [ ] Configured Hikari acquire, HTTP connect/read, and reactive deadlines per boundary.
- [ ] Kept retries within deadlines with jitter, bulkheads, rate limits, and idempotency where needed.
- [ ] Did not expose debug/threaddump/heapdump/env endpoints to the Internet.
- [ ] Did not ship lab anti-pattern stress endpoints to production.
- [ ] Re-measured tail latency, errors, queues, pools, and CPU under comparable workload after changes.
- [ ] When upgrading, compared dependencies, web stack, metrics, and config with a canary rollback plan.

## 25. Official Documentation

1. Spring Boot 3.3 — Actuator Metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
2. Spring Boot 3.3 — Common Application Properties (Tomcat connection timeout, MVC async timeout, Hikari): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
4. Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
5. Spring Boot 3.3 — Observability and Tracing: https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html
6. Spring Boot 3.3 — Calling REST Services: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
7. Spring Framework 6.1 — WebClient Configuration and Timeouts: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
8. Reactor Core — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
9. Reactor Core — Wrapping Synchronous Blocking Calls: https://projectreactor.io/docs/core/release/faq.html
10. Reactor Netty 1.1 — HTTP Client, ConnectionProvider Metrics and Pool: https://projectreactor.io/docs/netty/1.1.23/reference/index.html
11. Java 17 — `jcmd` `Thread.print` / `JFR.start` diagnostic command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
12. Micrometer — Timers and percentiles: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
13. OpenTelemetry — Trace context and spans: https://opentelemetry.io/docs/concepts/signals/traces/
14. HikariCP — Connection timeout and pool configuration: https://github.com/brettwooldridge/HikariCP
