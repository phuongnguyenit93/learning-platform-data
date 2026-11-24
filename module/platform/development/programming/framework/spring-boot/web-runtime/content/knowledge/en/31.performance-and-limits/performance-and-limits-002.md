# Finding Bottlenecks in Request Threads, Event Loops, Connection Pools, or Downstream Services

## 1. Lesson Objectives and Investigation Principles

A Spring Boot API is responding slowly. The root cause could lie in **request processing threads**, the **Reactor Netty event loop**, a **connection pool** for an HTTP client or database, or a **downstream dependency**. Increasing `server.tomcat.threads.max`, Hikari pool size, or HTTP connection counts without measuring first can make the system even slower.

A **bottleneck** is the resource or stage that limits throughput or drives up wait time as load rises. This lesson belongs to the **Performance and Limits** group of Spring Boot web-runtime. After this lesson, you will be able to:

1. Break an API call down into stages: request accept queue, controller execution, DB pool wait, HTTP client pool wait, remote service time, and response write.
2. Distinguish **CPU saturation**, **Servlet worker thread starvation**, **event-loop blocking**, **pool exhaustion**, and **downstream latency** through measurable signals.
3. Use Spring Boot 3.3 Actuator/Micrometer, `jcmd` thread dumps, Java Flight Recorder, distributed tracing, and load tests to gather evidence.
4. Run two **Java 17 + Spring Boot 3.3.5** labs: MVC with bounded Tomcat workers/Hikari/downstream; WebFlux comparing blocking vs non-blocking endpoints.
5. Identify bottlenecks via controlled A/B experiments checking queue time, throughput, p95/p99, error rate, and saturation.
6. Choose the right remediation: optimize code/queries, reduce blocking, bounded offloading, size pools to backend capacity, limit concurrency, timeouts, circuit breakers, caching, or improve downstreams.
7. Avoid confusing "increased latency" with "broken server", "WAITING" with CPU load, "more connections" with higher throughput, or "WebFlux" with automatically non-blocking.

**Standard procedure:** identify symptoms → measure each stage → form a hypothesis → run a **single-variable** experiment → confirm with metrics/traces → re-test under equivalent load. Never diagnose from a single CPU figure or a single thread dump snapshot.

## 2. Where Does a Request Travel?

### 2.1. Spring MVC, Calling JDBC and Downstream HTTP

~~~text
HTTP client / browser
        |
        v
Network / load balancer / reverse proxy
        |
        v
Tomcat listening socket + accept/request queue
        |
        v
Servlet worker thread
        |
        +--> Controller / service / validation / JSON
        |
        +--> JDBC DataSource / Hikari pool
        |         |
        |         +--> wait to acquire connection
        |         '--> SQL query / DB locks / database CPU
        |
        +--> RestClient / outbound HTTP connection pool
                  |
                  +--> wait for pool lease
                  +--> DNS / TCP connect / TLS
                  '--> downstream network + server + DB
        |
        v
Serialize HTTP response -> browser
~~~

The controller executes Java code, yet total request latency also includes **resource wait time** and **time spent in external systems**. A Tomcat worker waiting on JDBC may consume negligible CPU while latency climbs. Conversely, a CPU-bound endpoint can saturate CPU without waiting on any pool.

### 2.2. Spring WebFlux, Reactor Netty

~~~text
Incoming socket
      |
      v
Reactor Netty event-loop thread
      |
      v
WebFlux reactive handler
      |
      +--> non-blocking operators / async I/O
      |
      +--> WebClient with event-loop / connection provider
      |        |
      |        +--> pending acquire / DNS / TLS / downstream
      |        '--> response signal
      |
      +--> blocking library?  <-- RISK if executed directly on the event loop
      |
      v
Publisher emits -> write response
~~~

An event loop typically has **far fewer threads** than concurrent requests: one thread multiplexes many sockets via non-blocking I/O. If code calls `Thread.sleep()`, `Future.get()`, blocking JDBC, `RestClient.retrieve().body()`, or `Mono.block()` on the event loop, other connections cannot be served in time, causing **head-of-line blocking**.

**Key takeaway:** blocking MVC is not automatically a bug; reactive WebFlux does not automatically eliminate all blocking. What matters is matching the execution model and concurrency limits to the workload.

## 3. Start From Symptoms Instead of Tweaking Config

| Symptom | Hypothesis Worth Testing | Distinguishing Evidence |
| --- | --- | --- |
| p95/p99 rises while CPU stays low | Blocked threads, pending DB/HTTP pool, slow downstream | Thread states, queue metrics, wait spans, connection acquisition time |
| CPU near quota, throughput flat | CPU-bound service, JSON, crypto, GC, or excessive context switching | Per-process/thread CPU, JFR CPU profile, GC |
| Tomcat busy workers ≈ max and requests queue | Worker thread exhaustion / synchronous blocking | `tomcat.threads.busy`, thread dumps, active requests, queue/latency |
| WebFlux slow across the board even when downstream is fast | Blocking Reactor event loop | Thread names `reactor-http-nio-*`, BlockHound/JFR/thread dump, baseline comparison |
| Hikari active=max, pending rising | Waiting for JDBC connections | `hikaricp.connections.active` and `.pending`, acquisition timeouts, slow SQL |
| Reactor Netty client active=max, pending connections rising | Outbound HTTP pool saturation | Reactor Netty connection-provider gauges and pending acquire timer |
| HTTP client latency rises before server latency | Remote dependency slowed down | Client span, dependency RPS/p95, remote metrics |
| Gateway returns 503/504 while main service stays up | Connect/read timeout, DNS, TLS, pool wait, or remote down | Outbound errors, traces, dependency health |
| Throughput flat despite adding threads/connections | Bottleneck at DB/CPU/downstream or contention | Capacity curve and per-resource metrics |
| Latency climbs over time, GC pauses grow | Memory pressure, allocations, heap/GC, or leak | `jvm.gc.pause`, heap occupancy, JFR allocations |
| Only one endpoint is slow | Specific query, lock, serialization, or dependency | Route-level metrics and traces, query plans |
| All endpoints including `/fast` slow down | Shared resource such as event loop, CPU, request queue, or proxy | Compare `/fast` vs `/slow`, process and infrastructure metrics |

**One metric is never conclusive.** For example, Hikari `active=max` can be healthy if queries are very fast and nobody is pending; only when acquisition wait, errors, or latency climb do you have grounds to treat the pool as the bottleneck.

## 4. Minimum Measurements to Collect

### 4.1. Latency, Throughput, Errors, and Saturation

Following the practical **RED/USE** model:

- **Rate:** requests/s or transactions/s per route and client dependency.
- **Errors:** 4xx/5xx, timeouts, failed pool acquires, connection resets, rejected tasks, 429s.
- **Duration:** p50, p95, p99, maximum over a meaningful window; measure server and outbound calls separately.
- **Utilization:** CPU, heap, busy threads, active pool connections.
- **Saturation:** queue depth/pending acquires, queue delay, blocked requests, executor rejections.
- **Resource errors:** OOM, socket/file descriptor exhaustion, TLS/handshake failures, GC pauses.

### 4.2. Total Time Does Not Equal CPU Time

Practical breakdown:

\[
T_{\text{end-to-end}}
 = T_{\text{proxy/queue}}
 + T_{\text{controller}}
 + T_{\text{pool-wait}}
 + T_{\text{remote}}
 + T_{\text{response}}
\]

This is a practical component sketch, **not an unconditional additive formula** for every system. When parallel fan-out or overlapping asynchronous work occurs, use the **critical path** rather than summing every span duration. Network time, retries, pool acquisition, and instrumentation overhead can also nest inside different spans; avoid double-counting.

For instance, in an 800 ms request where DB acquisition takes 500 ms, the query takes 20 ms, and serialization takes 3 ms: optimizing 3 ms of Java code will not solve the main wait. Conversely, if a CPU profile shows 80% of samples in JSON transformation, enlarging the Hikari pool will hardly help.

### 4.3. Comparing Baseline vs High Load

Record explicitly:

| Case | Concurrency | Rate | p95 | Errors | Saturation |
| --- | --- | --- | --- | --- | --- |
| Unloaded baseline | Low | Low | Measure actually | Measure | Measure |
| Moderate load | Controlled step-up | Measure | Measure | Measure | Measure |
| Near threshold | Step up further | Measure | Measure | Measure | Measure |
| After a single change | Keep same workload | Compare vs before | Compare | Compare | Compare |

Do not fill in "nice" numbers into a table; collect **real measured results** from the same build, machine/quota, request mix, upstream health, warm-up duration, and network conditions. Production load tests require authorization, rate limits, and a rollback plan; run labs locally.

## 5. Actuator and Micrometer in Spring Boot 3.3

Spring Boot Actuator 3.3 exposes metrics via Micrometer when the right starters are present. Common meter names include:

| Meter / Endpoint Name | Meaning | Important Condition |
| --- | --- | --- |
| `http.server.requests` | Latency/count of HTTP requests handled by MVC/WebFlux | Server observation/instrumentation |
| `http.client.requests` | Outbound calls from RestClient/RestTemplate/WebClient | **Use Boot's auto-configured builder** or customizer |
| `tomcat.threads.busy` | Busy Tomcat request threads | `server.tomcat.mbeanregistry.enabled=true` |
| `tomcat.threads.current` | Current Tomcat threads | Tomcat MBean registry enabled |
| `jdbc.connections.active` | Active JDBC connections in use | DataSource instrumentation/pool metadata |
| `jdbc.connections.max` | Maximum JDBC connections | DataSource pool instrumentation |
| `hikaricp.connections.active` | Hikari active connections | HikariCP in use and instrumented |
| `hikaricp.connections.pending` | Threads waiting on the Hikari pool | Traffic must currently be waiting; reading after load stops may show 0 |
| `jvm.threads.live` | Live Java thread count | JVM metrics active |
| `jvm.gc.pause` | GC pause duration | Micrometer JVM instrumentation |
| `process.cpu.usage` | Process CPU ratio | Depends on runtime and exporter |
| `system.cpu.usage` | System CPU usage | May differ from container CPU quota |
| `reactor.netty.connection.provider.pending.connections` | Requests waiting for an outbound Reactor Netty connection | **Metrics must be enabled** on the connection provider |
| `reactor.netty.connection.provider.active.connections` | Active connections in the HTTP client pool | Requires proper provider/metrics configuration |

**It is normal for metrics not to appear if a component is absent or instrumentation is disabled.** Spring Boot 3.3 documentation notes that Tomcat instrumentation is only auto-enabled when the **MBean Registry** is enabled; it is disabled by default. Reactor Netty pool gauges require pool metrics to be enabled and a pool actually handling traffic. Never assume an absent meter means a value of 0.

### 5.1. Actuator Endpoints Used in the Lab

Add dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Configuration **for lab environments only**:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics
server.tomcat.mbeanregistry.enabled=true
~~~

Try:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
~~~

`/actuator/metrics` lists meter names **already registered in the process**. Some names only appear **after a request creates a sample** or a component/pool is initialized. The HTTP metrics response is JSON containing `measurements` and `availableTags`; do not infer p95 directly from a timer's single `TOTAL_TIME` snapshot.

**Security:** exposing metrics endpoints can leak topology/traffic details; keep the lab bound to `127.0.0.1`. In production, place management endpoints behind security/network policies and expose only what is necessary. `health` can also leak details if `show-details=always` is left public.

### 5.2. Histograms and p95 in Prometheus

When using the Micrometer Prometheus registry, enable histograms for the server timer:

~~~properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
~~~

Example PromQL against bucket metrics once the exporter/histogram is enabled:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Exact metric and tag names depend on the registry and version; Prometheus typically converts dots to underscores and timers to seconds. Distribution-statistic histograms **do not appear automatically** unless enabled with a supporting registry. Use **URI templates** instead of full user-controlled URLs to avoid blowing up metric cardinality.

## 6. Lab A — Spring MVC: Workers, Hikari Pool, and Downstream

We build a Spring Boot 3.3.5 / Java 17 app with three intentionally slow endpoints:

- `GET /api/worker?ms=1200`: holds a Tomcat worker using `Thread.sleep` to simulate a blocking call.
- `GET /api/db?ms=1200`: acquires a Hikari JDBC connection and holds it while sleeping, simulating a slow query/transaction occupying the pool.
- `GET /api/remote/{kind}`: uses `RestClient` to call a separate dependency server running on port 8091 (fast, slow, or hang).

**These sleep behaviors are deliberately bad so you can learn to identify bottlenecks**—never use them as production business code patterns. To prevent misuse, the app binds only to localhost, sleep durations are bounded, and the lab has no public network exposure.

### 6.1. Project Structure

~~~text
mvc-bottleneck-lab/
├── pom.xml
├── downstream/
│   └── RemoteStub.java
├── tools/
│   └── load.py
└── src/main/
    ├── java/com/example/perf/
    │   ├── PerfMvcApplication.java
    │   └── ProbeController.java
    └── resources/
        └── application.properties
~~~

The Maven project contains only the Spring Boot app. `RemoteStub` is a standalone JDK 17 Java HTTP server that can be started/stopped separately to observe downstream faults; `load.py` uses standard Python 3 to generate concurrent requests with zero external packages.

### 6.2. pom.xml

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
    <artifactId>mvc-bottleneck-lab</artifactId>
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

**Note:** `spring-boot-starter-jdbc` uses HikariCP by default under standard conditions; H2 is an embedded SQL database for the demo. `starter-actuator` provides meter visibility. The WebFlux starter is not needed in this MVC project.

### 6.3. application.properties

**File `src/main/resources/application.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

# Low worker cap to make queueing symptoms easy to observe.
server.tomcat.threads.max=8
server.tomcat.mbeanregistry.enabled=true

# H2 in-memory DB and tiny Hikari pool for experiments.
spring.datasource.url=jdbc:h2:mem:perfdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=2
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=700

# Downstream service running in a separate terminal.
app.remote.base-url=http://127.0.0.1:8091

management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=never
~~~

- Tomcat `max=8` is **not** a production recommendation; it makes local load queueing visible.
- Hikari `max=2` and connection timeout 700 ms exist to observe **pending acquire**/timeouts, not as optimal settings for every database.
- `spring.datasource.hikari.connection-timeout` is **the timeout waiting to borrow a connection** from Hikari; it differs from an SQL query timeout.
- `server.tomcat.mbeanregistry.enabled=true` enables Tomcat metrics in Actuator per Boot 3.3.
- Do not expose Actuator on a public network. Some metrics appear only after traffic or connections occur.

### 6.4. Main Class

**File `src/main/java/com/example/perf/PerfMvcApplication.java`:**

~~~java
package com.example.perf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PerfMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(PerfMvcApplication.class, args);
    }
}
~~~

### 6.5. Controller Creating Three Types of Slowness

**File `src/main/java/com/example/perf/ProbeController.java`:**

~~~java
package com.example.perf;

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
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping("/api")
public class ProbeController {

    private final DataSource dataSource;
    private final RestClient client;

    public ProbeController(
            DataSource dataSource,
            RestClient.Builder builder,
            @Value("${app.remote.base-url}") String baseUrl) {
        this.dataSource = dataSource;

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(500));
        factory.setReadTimeout(Duration.ofMillis(1500));

        this.client = builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @GetMapping("/fast")
    public String fast() {
        return "fast-ok";
    }

    @GetMapping("/worker")
    public ResponseEntity<String> worker(
            @RequestParam(defaultValue = "1200") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("invalid ms");
        }

        try {
            Thread.sleep(ms); // INTENTIONALLY blocking for illustration.
            return ResponseEntity.ok("worker:" + ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("worker interrupted");
        }
    }

    @GetMapping("/db")
    public ResponseEntity<String> db(
            @RequestParam(defaultValue = "1200") int ms) {
        if (ms < 0 || ms > 3000) {
            return ResponseEntity.badRequest().body("invalid ms");
        }

        try (Connection connection = dataSource.getConnection()) {
            // HOLDING the JDBC connection: intentionally simulating a slow query.
            Thread.sleep(ms);
            return ResponseEntity.ok("db:" + ms);
        } catch (SQLException ex) {
            // Demo groups SQL/pool errors; production should classify specifically.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("db connection unavailable");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("db request interrupted");
        }
    }

    @GetMapping("/remote/{kind}")
    public ResponseEntity<String> remote(@PathVariable String kind) {
        if (!("fast".equals(kind) ||
              "slow".equals(kind) ||
              "hang".equals(kind))) {
            return ResponseEntity.badRequest().body("invalid kind");
        }

        try {
            String body = client.get()
                    .uri("/remote/{kind}", kind)
                    .retrieve()
                    .body(String.class);
            return ResponseEntity.ok(body == null ? "" : body);

        } catch (ResourceAccessException ex) {
            // Connect/read timeout or network errors.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("remote unavailable");
        } catch (RestClientResponseException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body("remote HTTP error");
        } catch (RestClientException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body("remote response error");
        }
    }
}
~~~

Key points:

1. `/fast` has no `sleep`, `DB`, or downstream HTTP call; it serves as the **control group**.
2. `/worker` intentionally holds a **Tomcat request thread**. CPU usage can stay low because the thread is in `TIMED_WAITING`, while Tomcat busy workers stay high.
3. `/db` holds a Hikari JDBC connection while waiting. Once both connections are active, subsequent requests **wait on the pool**; waiting past 700 ms can throw `SQLException` (typically `SQLTransientConnectionException` from Hikari). The controller maps this to 503 in the lab; that is **not** an automatic status for every Hikari timeout.
4. `/remote/{kind}` makes an **outbound HTTP call** through `RestClient`, using Boot's injected builder to preserve client observations. `SimpleClientHttpRequestFactory` provides explicit timeouts, though it **does not create a separate Apache/Netty connection pool with pending metrics**.
5. `readTimeout=1500ms` is not an overall request deadline. In the lab, `hang` from downstream normally times out, while `slow` (~900 ms) normally succeeds.
6. Responses return plain text for simplicity; timers measure both Tomcat and the HTTP client, not only the sleep time.
7. `Thread.sleep` inside a transaction or while holding a connection is an **intentional anti-pattern**. Never put it in production business code.
8. HTTP statuses and exception handling are standardized so the test client can count errors without exposing raw stack traces or internal hosts.

## 7. Stub Service to Isolate Downstream Faults

**File `downstream/RemoteStub.java`:**

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
        System.out.println("RemoteStub listening on 127.0.0.1:8091");
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        String kind = exchange.getRequestURI().getPath()
                .substring("/remote/".length());
        long waitMs;

        if ("fast".equals(kind)) {
            waitMs = 0;
        } else if ("slow".equals(kind)) {
            waitMs = 900;
        } else if ("hang".equals(kind)) {
            waitMs = 3000;
        } else {
            waitMs = 0;
        }

        System.out.println("DOWNSTREAM kind=" + kind);
        try {
            Thread.sleep(waitMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }

        String response = "remote:" + kind;
        byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
~~~

This is a real downstream server running in a **separate process** on port `8091`, outside the Maven project. In reality, a remote service can slow down due to DB, I/O, queues, GC, or network issues; `Thread.sleep` merely simulates repeatable slowness. When the gateway times out and closes the socket first, the stub may encounter an error while writing its response; that is a consequence of the client giving up.

Compile/run with JDK 17 in terminal A (from the project directory):

~~~bash
cd downstream
javac --add-modules jdk.httpserver RemoteStub.java
java --add-modules jdk.httpserver RemoteStub
~~~

Run the gateway in terminal B, from `mvc-bottleneck-lab`:

~~~bash
mvn spring-boot:run
~~~

If you are still inside `downstream`, return to the project root before running Maven. Do not launch multiple instances on the same port.

Verify from terminal C:

~~~bash
curl -i http://127.0.0.1:8080/api/fast
curl -i http://127.0.0.1:8080/api/worker?ms=1200
curl -i http://127.0.0.1:8080/api/db?ms=1200
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/remote/slow
curl -i http://127.0.0.1:8080/api/remote/hang
~~~

Expected behavior:

| Endpoint | Result for a Single Request Under Normal Conditions |
| --- | --- |
| `/api/fast` | HTTP 200, `fast-ok` |
| `/api/worker?ms=1200` | HTTP 200, `worker:1200`, roughly 1.2 s + overhead |
| `/api/db?ms=1200` | HTTP 200, `db:1200` if a connection is acquired in time |
| `/api/remote/fast` | HTTP 200, `remote:fast` if stub is running |
| `/api/remote/slow` | HTTP 200, `remote:slow`, roughly 0.9 s + overhead |
| `/api/remote/hang` | In the lab, typically 503 `remote unavailable` due to 1.5 s read timeout |

Timing is not deterministic output: thread scheduling, JIT, container overhead, loopback networking, cold start, and pool initialization all contribute. Only the body/status rules are determined by the code under those conditions.

## 8. Generating Repeatable Controlled Load

Use a Python 3 standard-library script to measure per-endpoint latency, statuses, and throughput without relying on external benchmark tools.

**File `tools/load.py`:**

~~~python
import concurrent.futures
import math
import sys
import time
import urllib.error
import urllib.request

if len(sys.argv) != 4:
    print("Usage: python3 tools/load.py URL REQUESTS CONCURRENCY")
    sys.exit(2)

url = sys.argv[1]
requests = int(sys.argv[2])
concurrency = int(sys.argv[3])
if requests < 1 or concurrency < 1 or concurrency > 64:
    raise ValueError("requests>=1 and 1<=concurrency<=64 required")

def once(_):
    begin = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            response.read()
            status = str(response.status)
    except urllib.error.HTTPError as exc:
        exc.read()
        status = str(exc.code)
    except Exception:
        status = "ERR"
    latency_ms = 1000 * (time.perf_counter() - begin)
    return latency_ms, status

begin = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency) as pool:
    results = list(pool.map(once, range(requests)))
elapsed = time.perf_counter() - begin

values = sorted(latency for latency, _ in results)
def percentile(fraction):
    index = max(0, math.ceil(fraction * len(values)) - 1)
    return round(values[index], 1)

by_status = {}
for _, status in results:
    by_status[status] = by_status.get(status, 0) + 1

print("requests=", requests, "concurrency=", concurrency)
print("total_seconds=", round(elapsed, 3))
print("throughput_rps=", round(requests / elapsed, 2))
print("p50_ms=", percentile(0.5), "p95_ms=", percentile(0.95),
      "p99_ms=", percentile(0.99))
print("status_counts=", by_status)
~~~

**Measurement caveats:** `ThreadPoolExecutor` runs a finite number of requests; `throughput_rps` is batch-observed throughput including client warm-up and scheduling. This is **not** a fixed-arrival-rate open-loop load generator, does not measure server queue depth directly, and does not replace k6/Gatling/wrk for formal capacity testing. With tiny sample sizes, percentiles have low statistical confidence; increase sample counts and repeat runs for production conclusions.

Commands from the project root:

~~~bash
python3 tools/load.py http://127.0.0.1:8080/api/fast 50 8
python3 tools/load.py "http://127.0.0.1:8080/api/worker?ms=1200" 24 16
python3 tools/load.py "http://127.0.0.1:8080/api/db?ms=1200" 24 12
python3 tools/load.py http://127.0.0.1:8080/api/remote/slow 24 8
~~~

On Windows, if `python3` is unavailable, use `py tools/load.py ...`. Never fire load at production URLs or systems you do not own/control.

**Never assert a specific p95 figure before actually running it.** Results depend on CPU, OS, JIT, other background activity, and library versions.

## 9. Experiment 1 — Finding Tomcat Request Worker Saturation

### 9.1. Running 16 Concurrent Calls with Tomcat Max 8

~~~bash
python3 tools/load.py "http://127.0.0.1:8080/api/worker?ms=1200" 24 16
~~~

Each request holds a Tomcat worker for ~1.2 s while the configuration allows at most 8 workers. With 16 concurrent requests and 24 total requests:

- One batch of requests holds workers and sleeps.
- Requests without a worker must wait in connector/queue/socket layers; exact behavior depends on Tomcat and the OS.
- p95/p99 can rise in "waves" of waiting even while CPU remains low.
- `/api/fast` can also slow down if called **at the exact moment** workers are tied up by `/api/worker`: this is a sign of a shared inbound resource.

### 9.2. Measuring While Load Is Running

In another terminal:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.current
curl -s http://127.0.0.1:8080/actuator/metrics/process.cpu.usage
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

**When Tomcat is completely busy**, the request fetching Actuator metrics also needs a worker, so it may queue and **respond late**. Therefore production monitoring should use proper time-series scraping and out-of-band agents where appropriate; never treat a slow metrics endpoint as proof that the metrics themselves are inaccurate.

### 9.3. What Will a Thread Dump Show?

Find the JVM PID:

~~~bash
jcmd -l
~~~

Capture the dump:

~~~bash
jcmd <PID> Thread.print
~~~

`<PID>` is a placeholder to replace with the real PID. Stack frames typically look like:

~~~text
java.lang.Thread.sleep
com.example.perf.ProbeController.worker
... http-nio-8080-exec-...
~~~

While a thread is sleeping, its state is typically `TIMED_WAITING`. **This thread occupies a worker without necessarily consuming CPU.** Never diagnose a "deadlock" simply because threads are in `WAITING` or `TIMED_WAITING`.

### 9.4. Proper Remediation

- Identify **why workers are occupied**: remote calls, JDBC, locks, file I/O, or business CPU.
- In blocking MVC, configure timeouts and concurrency budgets; when upstream slows down, avoid holding workers indefinitely.
- Under high concurrency needs, consider async request handling, virtual threads on supported JDK/Boot/stacks, or a reactive design when genuinely warranted.
- Increase max worker threads **only when** CPU/heap/downstream have headroom and load tests prove worker availability is the bottleneck; unlimited increases can crash Hikari/HTTP pools/DBs.
- Apply rate limiting, queue/bulkhead limits, and explicit overload responses.

## 10. Experiment 2 — Hikari Connection Pool Exhaustion

### 10.1. Why Is It Different from Tomcat Thread Starvation?

In `/api/db`, the code:

~~~java
try (Connection connection = dataSource.getConnection()) {
    Thread.sleep(ms);
}
~~~

borrows a connection from Hikari and **holds it** for the entire sleep. The pool has only `maximum-pool-size=2`. When 12 requests arrive concurrently, typically:

- Two requests hold the two connections.
- Remaining requests wait inside `getConnection()` against `connection-timeout=700ms`.
- Some requests throw a timeout `SQLException` and return 503.
- Their Tomcat threads remain occupied while **waiting on the pool**, even though the H2 database and CPU are not overloaded.
- Once the first requests finish, `try-with-resources` returns connections to the pool.

### 10.2. Running the Test

~~~bash
python3 tools/load.py "http://127.0.0.1:8080/api/db?ms=1200" 24 12
~~~

While load is running, inspect:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.active
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.pending
curl -s http://127.0.0.1:8080/actuator/metrics/hikaricp.connections.max
curl -s http://127.0.0.1:8080/actuator/metrics/jdbc.connections.active
~~~

`hikaricp.connections.pending` may read 0 **after the batch finishes**; scrape during peak load or watch a time-series dashboard. Because metrics can carry `pool` or `name` tags, inspect `availableTags` if multiple Hikari pools exist.

### 10.3. Signals in a Thread Dump

Waiting thread stacks may show:

~~~text
com.zaxxer.hikari.pool.HikariPool.getConnection
com.zaxxer.hikari.HikariDataSource.getConnection
com.example.perf.ProbeController.db
~~~

Meanwhile, the threads holding connections and sleeping have a different stack (inside `Thread.sleep`). Distinguish:

- **Hikari active/max**: connections currently leased.
- **Pending**: threads waiting for a lease.
- **Acquire time**: wait time to obtain a lease.
- **Usage time**: how long a lease is held.
- **SQL/DB time**: time spent executing the query on the DB server.

Do not label `hikaricp.connections.active=max` as pool starvation if pending is ~0, acquisition latency is low, and throughput meets target.

### 10.4. Why Raising `maximum-pool-size` May Be Wrong

Suppose a DB handles ~10 parallel queries well; raising Hikari max from 10 to 100 can unleash excessive concurrent SQL, lock contention, and CPU/IO pressure, making queries even slower. Size the pool according to **DB capacity, transaction duration, concurrency, and app replica count**, not Tomcat thread count. More importantly:

- Shorten connection hold time; never sleep or call remote HTTP APIs inside a transaction.
- Optimize SQL plans, indexes, and lock durations.
- Ensure `Connection.close()` / `try-with-resources` returns connections to the pool.
- Set acquisition timeouts and leak detection where appropriate instead of waiting forever.
- Monitor aggregate connections across **all replicas**, since each pod maintains its own pool.

## 11. Experiment 3 — Slow Downstream, Not Slow Controller Code

### 11.1. Comparing Fast, Slow, and Hang

~~~bash
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/remote/slow
curl -i http://127.0.0.1:8080/api/remote/hang
~~~

The stub uses `fast=0ms`, `slow=900ms`, and `hang=3000ms`. The MVC `RestClient` has `readTimeout=1500ms`, so typically:

- `fast` succeeds quickly.
- `slow` succeeds, holding a gateway worker for ~0.9 s.
- `hang` triggers a timeout, which the gateway maps to 503, while the downstream may still be sleeping/processing.

Fetch metrics:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics/http.client.requests
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

When using Boot's injected `RestClient.Builder`, Spring Boot Actuator can instrument the HTTP client with `http.client.requests`. If you call `RestClient.create()` directly without applying Boot customizers, do not assume HTTP client meters will be present. With multiple dependencies, use tags/traces identifying remote host/URI template rather than looking only at total time across all HTTP client calls.

### 11.2. Stopping the Downstream Server

Stop the `RemoteStub` terminal with `Ctrl+C` while keeping the Spring Boot gateway running. Call:

~~~bash
curl -i http://127.0.0.1:8080/api/remote/fast
curl -i http://127.0.0.1:8080/api/fast
~~~

What to observe:

- `/api/remote/fast` typically returns 503 due to connection refused or timeout.
- `/api/fast` still returns 200 because it needs no downstream.
- If many remote requests arrive concurrently, workers stay occupied and `/api/fast` may suffer indirectly once the worker pool fills.

**Correct conclusion:** the gateway HTTP server is alive, while an outbound dependency is failing. Checking readiness or HTTP 200 on `/api/fast` alone does not prove all business capabilities are healthy.

### 11.3. Evidence from Distributed Tracing

Illustrative trace (not auto-generated by the lab):

~~~text
SERVER GET /api/remote/slow    944 ms
  |
  '-- CLIENT GET /remote/slow  915 ms
       |
       '-- REMOTE server work 900 ms
~~~

If most time sits in the client span, investigate the remote service, network, or client pool. If the client span is short while the server span is long, investigate code before/after the call, thread queueing, or serialization. For parallel calls, examine the **critical path** and pool wait times rather than summing all child spans to explain wall-clock latency.

## 12. Lab B — WebFlux and Event-Loop Blocking

This lab is a **separate Spring Boot project**—do not add these classes into the MVC project. It compares:

- `GET /loop/bad`: **intentionally** calls `Thread.sleep(700)` inside a reactive pipeline **without offloading**, potentially blocking the event-loop subscriber thread.
- `GET /loop/good`: uses `Mono.delay`, avoiding thread blocking for the 700 ms wait.
- `GET /loop/offload`: offloads the blocking task onto `Schedulers.boundedElastic()` to illustrate a transitional workaround when a blocking library cannot yet be replaced.

### 12.1. Project and pom.xml

~~~text
webflux-loop-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/loop/
    │   ├── LoopApplication.java
    │   └── LoopController.java
    └── resources/
        └── application.properties
~~~

**File `pom.xml`:**

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
    <artifactId>webflux-loop-lab</artifactId>
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

Do not add `spring-boot-starter-web`: when both starters are present, Spring Boot 3.3 normally chooses Servlet MVC, changing the event-loop experiment.

### 12.2. Configuration and Main

**`src/main/resources/application.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8082
management.endpoints.web.exposure.include=health,metrics
~~~

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

### 12.3. Controller Comparing Three Wait Approaches

**`src/main/java/com/example/loop/LoopController.java`:**

~~~java
package com.example.loop;

import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/loop")
public class LoopController {

    @GetMapping("/bad")
    public Mono<String> bad() {
        // INTENTIONALLY WRONG: blocks when the publisher is subscribed.
        return Mono.fromCallable(() -> {
            Thread.sleep(700);
            return "bad:" + Thread.currentThread().getName();
        });
    }

    @GetMapping("/good")
    public Mono<String> good() {
        // Does not occupy a thread while waiting 700ms.
        return Mono.delay(Duration.ofMillis(700))
                .map(tick ->
                        "good:" + Thread.currentThread().getName());
    }

    @GetMapping("/offload")
    public Mono<String> offload() {
        // Needed for blocking code that cannot yet be replaced.
        return Mono.fromCallable(() -> {
                    Thread.sleep(700);
                    return "offload:" +
                            Thread.currentThread().getName();
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Key distinctions:

1. `bad()` returns a `Mono`, yet `fromCallable` still executes **blocking code upon subscription**. On a typical WebFlux/Reactor Netty path without a scheduler boundary, subscription can run on an event-loop thread; sleeping ties up the event loop and delays other sockets.
2. `good()` uses the `Mono.delay` timer, avoiding tying up an event-loop thread for 700 ms. The result callback may run on another Reactor scheduler thread; never treat thread names as an API contract.
3. `offload()` moves blocking work onto `boundedElastic`, which has bounded threads and queues. This is a transitional measure; if overloaded with blocking tasks, `boundedElastic` can also **saturate**, introducing queueing and latency.
4. All three return text with the thread name to aid observation. Names like `reactor-http-nio-2` or `boundedElastic-1` depend on runtime and concurrency; do not hardcode expected names.
5. The experiment intentionally omits WebClient/DB calls to **isolate** event-loop blocking from network/downstream latency.

### 12.4. Running the Experiment

In `webflux-loop-lab`:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://127.0.0.1:8082/loop/bad
curl -i http://127.0.0.1:8082/loop/good
curl -i http://127.0.0.1:8082/loop/offload
~~~

Expect around 700 ms for all three endpoints, yet **different resources are held while waiting**. Run `tools/load.py` from the MVC project (or copy it into the WebFlux directory if preferred):

~~~bash
python3 ../mvc-bottleneck-lab/tools/load.py \
  http://127.0.0.1:8082/loop/bad 40 20

python3 ../mvc-bottleneck-lab/tools/load.py \
  http://127.0.0.1:8082/loop/good 40 20

python3 ../mvc-bottleneck-lab/tools/load.py \
  http://127.0.0.1:8082/loop/offload 40 20
~~~

**Do not force conclusions from a single run.** Event-loop worker count depends on CPU count and runtime; on many-core machines, 20 requests schedule differently than on few-core hosts. To confirm blocking, combine sampling/JFR, thread names, latency of a non-blocking control endpoint, and busy event-loop threads. You can test `-Dreactor.netty.ioWorkerCount=2` in a **separate lab process** to reproduce contention, but changing event-loop thread counts is an experimental variable, not a production tuning trick.

### 12.5. Why Must `.block()` Never Be Called on the Event Loop?

~~~java
// ANTI-PATTERN in a WebFlux reactive handler:
String result = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

Illustrative snippet (**not a standalone runnable Java class**). `block()` waits synchronously for a result and can stall the event loop; Reactor also includes safeguards that detect blocking on certain non-blocking schedulers. Never "fix" this by increasing event-loop threads indefinitely.

Instead, keep the pipeline reactive:

~~~java
// In a reactive service that already has WebClient:
Mono<String> result = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2));
~~~

If a third-party library only offers blocking JDBC/IO, offload with `Schedulers.boundedElastic()` within sensible bounds, or consider MVC/virtual threads. **Do not equate `boundedElastic` with an unlimited thread pool.**

## 13. Outbound HTTP Connection Pools: Distinct from DB Pools and Tomcat Workers

A WebFlux request using `WebClient` may need to **lease an outbound HTTP connection** from Reactor Netty's `ConnectionProvider`:

~~~text
WebFlux event loop
      |
      v
WebClient request
      |
      v
ConnectionProvider (HTTP client pool)
      |    active / idle / total
      |    pending acquire queue
      v
Remote host:port
      |
      v
HTTP response
~~~

When active pool connections hit the limit and pending acquisitions grow, requests wait for a lease or time out. **This can happen even when CPU and event-loop threads are idle.**

### 13.1. Signals with Reactor Netty

Gauges/timers when pool metrics are enabled:

~~~text
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.total.connections
reactor.netty.connection.provider.max.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
~~~

These are **Reactor Netty connection provider metrics**, not Tomcat or Hikari metrics. If the backend uses HTTP/2, there are also active/pending **streams** concepts in applicable versions; never infer concurrent request count purely from TCP connection count.

### 13.2. Example Bounded WebClient Pool Configuration

The standalone class snippet below is for a **WebFlux project with Reactor Netty + Micrometer**. Place it in a scanned package and replace the base URL with your actual service:

~~~java
package com.example.loop;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class WebClientPoolConfig {

    @Bean
    ConnectionProvider dependencyConnections() {
        return ConnectionProvider.builder("dependency")
                .maxConnections(10)
                .pendingAcquireMaxCount(20)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient dependencyWebClient(
            WebClient.Builder builder,
            ConnectionProvider dependencyConnections) {
        HttpClient httpClient = HttpClient.create(dependencyConnections)
                .responseTimeout(Duration.ofSeconds(2));
        return builder
                .baseUrl("http://127.0.0.1:8091")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

**Do not copy this into the MVC lab expecting it to configure a Tomcat pool.** It configures an **outbound Reactor Netty HTTP client** in a WebFlux project, not the inbound Netty event-loop worker pool.

- `maxConnections(10)`: maximum active connections in the provider according to the actual pooling/remote-address model.
- `pendingAcquireMaxCount(20)`: bounds waiting acquisitions to avoid unbounded queues.
- `pendingAcquireTimeout(1s)`: waiting past the limit fails acquisition.
- `metrics(true)`: enables pool gauges when Micrometer is present.
- `responseTimeout(2s)`: client-level HTTP response timeout, distinct from pool wait and overall business deadline.
- Boot's injected `WebClient.Builder` preserves `http.client.requests` observations where applicable.
- A custom `ConnectionProvider` requires lifecycle management; dispose of custom resources on application shutdown if not framework-managed. You can configure `@Bean(destroyMethod="dispose")` or manage via a Reactor Netty resource factory depending on design to avoid resource leaks.
- One HTTP/2 connection can multiplex multiple streams; interpret client/provider metrics per protocol rather than equating every active connection to a single request.

**Do not blindly apply defaults from "latest" docs to Boot 3.3 without checking versions:** Reactor Netty `maxConnections`/pending defaults can vary by version, CPU count, and resource config. Always check actual max meter values during diagnosis.

### 13.3. Actions When Pending Connections Rise

1. Identify which pool, which remote address, and how long acquisition waits take.
2. Check remote latency: if the service is slow, enlarging the pool may simply **push more load onto an already struggling service**.
3. Keep connections alive/reused; avoid creating `WebClient`/providers per request.
4. Configure sensible queue sizes/timeouts, concurrency limits, and circuit breakers.
5. Consider raising pool size in a controlled way if downstream and network have capacity, then re-verify throughput/p95/errors.
6. For DB pools, investigate queries/locks; for HTTP client pools, investigate per-host connections, HTTP/2 multiplexing, and remote rate limits—**do not conflate the two pools**.

## 14. Distinguishing Workers, Event Loops, JDBC Pools, and Client Pools

| Resource | Belongs To | What Happens When Exhausted | Observation |
| --- | --- | --- | --- |
| Tomcat request worker | Inbound MVC | New requests wait for workers, latency rises | `tomcat.threads.busy`, thread dumps |
| Reactor Netty event loop | Inbound/async I/O WebFlux | Many sockets stall when blocking tasks run | Event-loop thread stack/CPU, `/fast` latency, JFR |
| Hikari JDBC connection | Database outbound | Threads wait in `getConnection()`, acquire timeouts | Hikari active/pending/timeout, slow queries |
| Reactor Netty HTTP client connection | Remote HTTP outbound | Requests queue on pending lease, acquire timeouts | ConnectionProvider active/pending |
| DB server worker/lock | Downstream database | Query latency/lock wait rises even if Hikari still has connections | DB dashboard, query plans/lock stats |
| Remote HTTP service worker | Dependency | HTTP client latency/p95 rises, 429/5xx | Client spans and remote metrics |
| CPU cores / cgroup quota | Host/container | Runnable CPU threads queue | CPU usage/throttling, profiler |
| Heap/GC | JVM | Pauses, allocation pressure, latency spikes | `jvm.gc.pause`, heap, JFR |

**A system can saturate multiple layers simultaneously:** slow downstream → long HTTP client pool leases → MVC workers block → Tomcat queue grows → frontend times out. Here, "Tomcat busy" is a **secondary symptom**; the root cause may be the dependency. Find the *first bottleneck* in the critical path, not just wherever the first alert fired.

## 15. Little’s Law and Concurrency Limits

In steady state:

\[
L = \lambda W
\]

- `L`: items currently inside the system/measured stage.
- `λ`: arrival/throughput rate (items per second) at the same boundary.
- `W`: average time an item spends inside that boundary.

Hypothetical example: outbound call rate `100 requests/s`, average call duration `0.2s` → roughly `20` concurrent calls in flight on average. If the dependency slows to `0.8s` at the same throughput, average concurrency grows to roughly `80`.

**This is an illustrative calculation**, not a recommendation to set pool=20 or 80. Consider queues, tail latency, HTTP/2 multiplexing, replica counts, and downstream capacity. In systems with feedback/backpressure, throughput may also drop upon saturation, so `λ` cannot be held arbitrarily constant.

### 15.1. Queueing and the Knee

As a resource approaches 100% utilization, wait times can grow **nonlinearly**, especially with uneven arrivals. Therefore:

- Hikari `active=max` **with rising pending** is far more dangerous than `active=max` alone.
- Tomcat `busy=max` **with growing request queues/degrading p95** signals worker saturation.
- CPU≈100% **with growing run queues** indicates compute pressure.
- Rising HTTP client pool pending accompanied by rising remote latency: pool pressure may be a downstream consequence.

Never target "100% steady-state pool utilization". Systems need headroom for bursts, GC, reconnects, and retries.

## 16. How to Use Thread Dumps, JFR, and Profilers

### 16.1. Thread Dump — A Snapshot, Not a Final Verdict

First find the Java PID:

~~~bash
jcmd -l
~~~

Then:

~~~bash
jcmd <PID> Thread.print
~~~

Capture **several snapshots during slowdowns**, spaced a few seconds apart, to separate transient waits from sustained stalls. Look for:

- Tomcat `http-nio-...-exec-*` threads and controller/service call stacks.
- Reactor Netty `reactor-http-nio-*` threads: check for `Thread.sleep`, JDBC, or `block()`.
- `HikariPool.getConnection`: requests waiting on pool acquisition.
- Socket read/HTTP client stacks: waiting on network I/O, not necessarily a code bug.
- `BLOCKED` on monitors/locks: contention; identify the lock owner.
- CPU-hot threads: requires CPU sampling, never infer CPU usage from one stack line.

`WAITING`, `TIMED_WAITING`, and `RUNNABLE` are JVM thread states that **do not map 1:1 to CPU consumption**; OS scheduling and native I/O still factor in.

### 16.2. Java Flight Recorder (JFR)

JDK 17 supports Flight Recorder; capture a short recording **in an authorized environment**:

~~~bash
jcmd <PID> JFR.start name=perf settings=profile duration=30s filename=perf.jfr
~~~

Once finished, inspect in JDK Mission Control or a compatible tool. Useful signals:

- CPU method sampling / hot stacks.
- Lock contention and thread parking.
- Socket read/write events and file I/O.
- Allocation pressure and GC pauses.
- Thread scheduling and latency-spike timestamps.

**JFR/profiling carries some overhead.** Choose appropriate sampling periods, durations, data sensitivity controls, and load; do not blindly run verbose profiling forever in production. To observe container CPU quota/throttling, pull host/cgroup metrics outside the JVM.

### 16.3. BlockHound for Reactive Blocking

BlockHound helps detect certain blocking calls on Reactor non-blocking threads in tests/labs, but it is an extra dependency/tool with JDK/runtime compatibility requirements. **Never treat the absence of BlockHound warnings as proof of zero blocking.** Combine code review, thread dumps, tracing, and event-loop latency measurements.

### 16.4. Database-Specific Evidence

When suspecting Hikari exhaustion, ask:

1. How many connections are active/pending?
2. How long is each connection held?
3. Which queries is the DB running—are there lock waits, full scans, missing indexes, or overly long transactions?
4. Is there a connection leak? Are `Connection`/`ResultSet` closed and returned to the pool?
5. What pool size does each replica use? Does the sum exceed DB `max_connections`?

`hikaricp.connections.pending` alone cannot distinguish "pool too small" from "queries too slow"; inspect SQL durations and query plans too.

## 17. Tracing Across Hops: Finding the Critical Path

A trace may look like:

~~~text
Browser request total: 1400ms
  |
  +-- inbound controller / authentication: 20ms
  |
  +-- DB connection acquire: 500ms
  +-- DB query: 30ms
  |
  +-- outbound HTTP client: 800ms
  |     '-- remote service processing: 760ms
  |
  '-- encode response: 10ms
~~~

These numbers are **illustrative only**; do not sum nested spans or parallel calls. In real traces, distinguish **server spans**, **client spans**, custom pool/SQL spans, and end-to-end wall time.

Distributed tracing requires configuring the Micrometer Tracing/OpenTelemetry bridge, exporter, context propagation, sampling, and instrumentation. Basic Spring Boot Actuator **does not automatically export end-to-end spans to a tracing backend** without the required dependencies and config.

**Questions to find root cause:**

- Long server span, short client/DB spans? Check queueing, CPU, serialization, or uninstrumented blocking.
- Long client span, short remote server span? Check connect/queue/network, proxies, TLS, retries, or instrumentation gaps.
- Remote server span also long? Investigate resources/DB inside the remote service.
- Multiple endpoints slow due to the same dependency? Break down by dependency tag and per-route metrics.

Never log raw tokens, cookies, PII, or sensitive query parameters; use URI templates and sampling.

## 18. Fix the Actual Bottleneck Instead of Blindly Scaling Resources

| Confirmed Root Cause | Priority Remediation | What to Verify Afterward |
| --- | --- | --- |
| MVC worker waiting too long on I/O | Timeouts, concurrency limits, async handling, or suitable stack | Busy workers, p95, remote errors |
| Blocking WebFlux event loop | Use non-blocking APIs, bounded offload of blocking work | Event-loop latency, `boundedElastic` queue, p99 |
| Slow DB query | SQL/indexes/query plan, shorter transactions, DB capacity | Query time, locks, Hikari usage |
| Hikari acquisition pending | Shorten connection hold time, size pool to DB, limit load | Pending acquires, DB CPU, total connections |
| HTTP client pool pending | Reuse client, optimize remote, cap queue, adjust pool carefully | Pending acquires, remote latency, error rate |
| Downstream slow / 429 | Cache where valid, bulkheads, timeouts, rate limits, circuit breakers | Remote p95/429, fallback rate, user SLA |
| CPU saturation | Optimize hot paths, allocations, serialization, caching, scale out | CPU p95, GC, throughput |
| GC pressure | Reduce allocations/buffers, tune heap/GC based on JFR | GC pause time, memory retention |
| Proxy/network | Tune TLS, DNS, routing, keep-alive, idle timeouts | Client connect time, resets, latency |
| Load burst / queue overload | Admission control, bounded queues, fast rejection | Tail latency, drop/reject rate, recovery |

**Adding threads or enlarging pools is not the default fix.** For instance, increasing Hikari max increases concurrent queries hitting the DB; if the DB is already saturated, latency worsens. Adding HTTP connections when a remote service is already returning 429/503 makes matters worse too.

### 18.1. Retries, Timeouts, and Circuit Breakers

- Retry only transient failures, with bounded attempts, exponential backoff/jitter, and an overall deadline.
- Never retry payment/order-creating POSTs without idempotency keys and duplicate protection.
- Circuit breakers prevent piling requests onto a failing dependency; they do not fix the remote service by themselves.
- Bulkheads isolate resources/concurrency per dependency so failures do not cascade across the whole gateway.
- Rate limiting / load shedding fail fast once capacity is exceeded instead of queueing indefinitely and timing out en masse.
- Caching/fallbacks apply only when stale/partial data is allowed by the business contract.

### 18.2. When Should You Scale Out?

Scale application replicas when the **app's own** CPU/threads are bottlenecked and DB/downstreams still have headroom. If the bottleneck is the DB or a dependency, adding app replicas can **multiply** Hikari connections and outbound RPS, worsening the outage. Size across the whole system, not a single pod.

## 19. 10-Step Incident Investigation Workflow

1. **Define scope:** all routes or one endpoint, sudden or gradual; what deploy/config changed recently?
2. **Client metrics:** p95/p99, errors, deadlines, traffic mix, concurrency, geography; proxy/CDN involved?
3. **Server metrics:** `http.server.requests` by URI template/status; CPU, GC, threads.
4. **MVC vs WebFlux:** verify the actual runtime (Tomcat/Servlet or Reactor Netty WebFlux), do not guess from a `WebClient` dependency.
5. **Pools:** Tomcat busy workers, Hikari active/pending, HTTP client provider active/pending, executor queues.
6. **Downstreams:** `http.client.requests`, remote p95/errors, remote CPU/DB saturation, TCP/TLS/DNS failures.
7. **Capture evidence:** thread dumps/JFR/traces while slowness is happening; avoid capturing only after recovery.
8. **Rank hypotheses:** pick the earliest layer creating queue/latency growth, separating root cause from secondary symptoms.
9. **Change one variable:** optimize a query, remove blocking, cap concurrency temporarily, fix a timeout, or roll back a release under comparable load.
10. **Validate & document:** compare baseline, p99, errors, throughput, saturation, cost, and regressions; update runbooks/alerts.

During a production incident, prioritize mitigating user impact (shedding load, rolling back, rate limiting) alongside collecting evidence; never deliberately inject heavy load or flip many settings at once just to test hypotheses.

## 20. Scenario Drill: Gather Evidence Before Fixing

### Scenario A: MVC API p99 5 Seconds, CPU 15%

- Tomcat busy workers at max.
- Thread dumps show many `SocketInputStream.read` frames in outbound HTTP calls.
- Client span to inventory rose from 100 ms to 4 s.

**Priority hypothesis:** slow inventory/network calls are holding Tomcat threads; worker saturation is a consequence. Check timeouts, inventory health, retries, and bulkheads before raising Tomcat max.

### Scenario B: Hikari Pending 40, SQL p95 2 Seconds

- Pool max=20, active=20.
- Queries show lock waits / slow SQL.
- Raising pool to 50 would likely worsen lock contention.

**Priority:** fix queries, transactions, and DB locks, and shorten connection hold times—do not raise pool size as step one.

### Scenario C: WebFlux App Low CPU, Yet `/fast` Also Slow

- Reactor Netty thread dump shows `Thread.sleep` and blocking JDBC.
- All sockets share a handful of event-loop threads.

**Priority:** remove blocking from the event loop, switch to a reactive driver or bounded offload, then re-test under load.

### Scenario D: Reactor Netty Active Connections=Max and Pending Rising

- Remote HTTP p95 is 1.8 s, continuous pool acquisition timeouts.
- Remote returns 429 due to quota.

**Priority:** reduce concurrency/rate and retries, check remote capacity/quota. Raise pool size only if the remote has headroom and measurements confirm it.

### Scenario E: CPU 100% with Rising p95, Pools Mostly Empty

- JFR samples concentrate in JSON serialization and a large table-building algorithm.

**Priority:** optimize hot paths, response size, caching, pagination, and inspect heap/GC. Enlarging the DB pool will not fix CPU-bound serialization.

### Scenario F: One Pod Slow, Remaining Pods Normal

- The slow pod shows high GC pauses and heap occupancy.
- No difference in Hikari pending or client latency.

**Priority:** memory pressure, allocation hotspots, cgroup/quota, GC, traffic skew, or connection imbalance; avoid letting cluster-wide averages hide an outlier pod.

## 21. Common Analysis Mistakes

| Misconception | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| Low CPU means the server is not bottlenecked | Threads may be waiting on I/O or pools | Measure queues, pending counts, and client latency |
| High CPU means bad Java code | Could be GC, serialization, legitimate load, or container throttling | CPU profile, quotas, GC metrics |
| Hikari `active=max` means the pool is too small | Ignores pending count and acquisition latency | Combine pending, SQL duration, DB capacity |
| Tomcat `busy=max` means add more threads | Workers may be waiting on a remote service | Thread dumps and downstream spans |
| WebFlux guarantees non-blocking execution | Blocking code can still run on the event loop | Audit blocking APIs and schedulers |
| More event-loop threads is always faster | More threads do not fix blocking/library latency | Remove/offload blocking and benchmark |
| Huge HTTP client pool is always faster | Remote can overload and return 429/5xx | Size to remote budget and load test |
| `http.server.requests` suffices for root cause | Only gives end-to-end request timing | Add client/DB spans, pool metrics, profiler |
| Absent metric meter means value is 0 | Instrumentation may be off or no samples exist yet | Verify Actuator names, dependencies, and config |
| Run one request and measure p95 | Single-sample percentiles are meaningless | Warm up, gather many samples, test concurrency |
| Calling `sleep()` inside a DB transaction is harmless | Holds connections/locks, starving the pool | Keep transactions short, no remote calls inside |
| Retrying more reduces timeouts | Usually amplifies load and queues during outages | Retry budgets, backoff, idempotency |
| Raise pools independently across all replicas | Total DB connections multiply by replica count | Calculate aggregate capacity and quotas |
| `/actuator/metrics` not responding means Actuator broke | Tomcat workers may all be busy | Observe via external scraper/agent and thread dumps |
| App uses `WebClient` so it must be WebFlux | MVC can use `WebClient` too | Verify actual server runtime/classpath |
| Child span latencies sum to parent latency | Spans can be nested or parallel | Trace critical path, avoid double-counting |

## 22. Self-Check Exercises

**Question 1.** An endpoint's p99 spikes 10x while process CPU stays at 10%. Name at least four places to inspect before raising thread counts.

**Question 2.** Why can two requests holding Hikari connections cause 10 other requests to time out even when Tomcat still has workers and the DB uses little CPU?

**Question 3.** In the MVC lab, both `/api/worker` and `/api/db` call `Thread.sleep`. Why do these two endpoints cause different bottlenecks?

**Question 4.** In the WebFlux lab, does `Mono.fromCallable(Thread.sleep)` guarantee non-blocking execution just because it returns a `Mono`?

**Question 5.** When using WebFlux `WebClient` on Reactor Netty, which resource does `reactor.netty.connection.provider.pending.connections` track? Is it the Hikari pool?

**Question 6.** Why might creating `RestClient.create()` directly miss `http.client.requests` instrumentation compared to Boot's injected builder?

**Question 7.** Why can `hikaricp.connections.pending` read 0 after load stops even though pool exhaustion just occurred?

**Question 8.** What setting does Spring Boot 3.3 require to register Tomcat-specific metrics automatically?

**Question 9.** Client span to remote is slow while remote server span is fast. What intermediate stages should be inspected?

**Question 10.** Why can increasing Hikari max per pod slow down the DB when scaling replicas?

**Question 11.** Can Little's Law `L=λW` finalize `maxConnections` without measuring p95, queueing, and remote capacity?

**Question 12.** Why are fire-and-forget load tests or a single request insufficient to claim capacity?

**Question 13.** When a thread dump shows `WAITING`, does that mean the thread is consuming CPU?

**Question 14.** If a slow downstream causes MVC worker exhaustion, where should you investigate the direct cause first?

**Suggested Answers:**

1. Tomcat workers/queues, Hikari pending, outbound HTTP pool pending, downstream latency, locks, network, or GC.
2. Two connections are leased, so other requests wait to acquire a connection and hit acquisition timeouts despite idle CPU.
3. `/worker` holds a Tomcat request thread; `/db` also holds a Hikari JDBC connection, causing pool starvation before threads hit max.
4. No. When subscribed on the event loop, the blocking callable still blocks that thread.
5. Waiting to lease outbound Reactor Netty HTTP connections—not the JDBC/Hikari pool.
6. Boot instrumentation is attached via auto-configured `RestClient.Builder`/customizers; manually instantiated clients bypass them.
7. Pending is an instantaneous state; scrape during active load or check time-series/exception counters.
8. `server.tomcat.mbeanregistry.enabled=true`, along with Actuator and Tomcat.
9. HTTP client pool acquisition, DNS, TCP connect, TLS, proxies, network, retries, and observation gaps.
10. Per-pod pools multiply, potentially exceeding DB connection limits or causing excessive concurrent SQL and lock contention.
11. No, it only relates averages at a steady boundary; you must test queues, tail latency, and capacity.
12. They fail to measure concurrency, queues, or tail latency accurately and do not reproduce production workload mixes.
13. No. `WAITING`/`TIMED_WAITING` can indicate sleep, park, or I/O wait; inspect CPU samples and stacks.
14. Remote service latency and outbound HTTP client timeouts/retries/connection pool; Tomcat busy threads are a secondary symptom.

## 23. Production Diagnostic Checklist

- [ ] Recorded baseline request rate, p50/p95/p99, errors, traffic mix, and CPU/GC.
- [ ] Confirmed whether the app actually runs MVC/Tomcat or WebFlux/Reactor Netty.
- [ ] Enabled `http.server.requests` by route template and `http.client.requests` by dependency.
- [ ] Enabled Tomcat MBean registry when Tomcat metrics are needed.
- [ ] Tracked Hikari/JDBC active, max, pending, acquire time, and slow SQL evidence.
- [ ] Tracked HTTP client connection pool metrics and pending acquire time when pooling is used.
- [ ] Captured thread dumps/JFR **during slowness**, not only afterward.
- [ ] Identified where blocking code runs, especially on event loops.
- [ ] Collected downstream traces/latencies/errors to separate root cause from symptoms.
- [ ] Determined the critical path in fan-outs without double-counting nested spans.
- [ ] Bounded timeouts, connection acquires, and retry budgets within overall deadlines.
- [ ] Sized DB and HTTP pool maximums to aggregate downstream capacity and replica counts.
- [ ] Configured rate limits, bulkheads, and circuit breakers to prevent cascading failures.
- [ ] Avoided raising thread counts or pool sizes blindly before controlled A/B comparison tests.
- [ ] Secured metrics endpoints and bounded load-test impact.
- [ ] Re-measured p95/p99, errors, throughput, and saturation after fixes, and documented runbooks.

## 24. References

- Spring Boot 3.3 — Actuator Metrics, JVM/System/MVC/WebFlux/HTTP-client/Tomcat/DataSource/Hikari: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Actuator Endpoints: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Observability / HTTP client instrumentation: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
- Spring Boot 3.3 — Calling REST Services: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — Embedded web servers / Tomcat thread and connector config: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Reactor Netty — HTTP Client Reference, ConnectionProvider metrics: https://projectreactor.io/docs/netty/1.1.23/reference/index.html
- Reactor Netty — Current HTTP Client Reference, configuration and pool metrics (cross-check versions): https://projectreactor.io/docs/netty/release/reference/http-client.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- HikariCP — Configuration and `connectionTimeout`: https://github.com/brettwooldridge/HikariCP
- Java 17 — `jcmd` diagnostic command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Java 17 — Java Flight Recorder runtime guide: https://docs.oracle.com/en/java/javase/17/jfapi/
- Micrometer — Meter concepts, timers, and distributions: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- OpenTelemetry — Traces and spans / critical path observations: https://opentelemetry.io/docs/concepts/signals/traces/