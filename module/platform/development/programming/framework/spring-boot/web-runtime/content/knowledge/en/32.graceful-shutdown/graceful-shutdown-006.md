# Handling In-Flight Requests, Async Tasks, and Downstream Service Calls During Spring Boot Shutdown

## 1. Why is “graceful shutdown” harder than calling `System.exit()`?

When a Spring Boot version is replaced during a deploy, there may still be:
- An HTTP request waiting on a DB query or a downstream result.
- A Servlet HTTP request processing via `Callable`, `DeferredResult`, `CompletableFuture`, or returning a stream.
- A WebFlux `Mono`/`Flux` waiting on an HTTP response from `WebClient`.
- An `@Async` or `TaskExecutor` task accepted from a request that is **no longer tied to the HTTP response**.
- A `@Scheduled` task syncing data, or a message queue consumer processing an event.
- A streaming upload/download, a long-lived WebSocket/SSE connection, or a job partway through writing to storage.
- Multiple connection pools and HTTP clients that must stay alive until the tasks using them finish.

If the JVM stops immediately, unanswered requests can lose connections; tasks are left unfinished; downstream services may have committed a transaction even though the caller never got a response. Yet **simply setting `server.shutdown=graceful` does not guarantee all of the above will finish either**.

This lesson belongs to **Graceful Shutdown** in **Spring Boot - web-runtime**. The goals are to understand:
1. Which requests the embedded web server's graceful shutdown waits for, and for how long.
2. Differences among in-flight HTTP, Servlet async, application `@Async`, and WebFlux publishers.
3. How downstream calls are handled while the caller is stopping, especially timeouts/cancellation/retries and lost responses.
4. How to choose deadlines, traffic draining, executor shutdown, Readiness, and Kubernetes termination grace periods.
5. How to test yourself with Java 17+ / Spring Boot 3.3.13, rather than just eyeing a single “graceful shutdown complete” log line.

**Version context:** main guidance/configuration follows **Spring Boot 3.3.13, Spring Framework 6.1, Java 17+**. Boot **3.3 requires explicitly enabling** `server.shutdown=graceful`; newer Boot branches may have different defaults. When deploying to production, use a branch still receiving security support and cross-check APIs against the actual version.

## 2. Defining graceful shutdown accurately once

When the JVM/application closes `ApplicationContext` normally, Spring Boot can instruct the web server to:
- Stop accepting **new requests**.
- Allow **in-flight HTTP requests** to continue until they finish or the grace period expires.
- Then close the web server and continue Spring context shutdown phases.

Per Spring Boot 3.3 documentation, graceful shutdown works with **Tomcat, Jetty, Undertow, Reactor Netty** and both **Servlet/MVC and WebFlux**. It runs when the context closes, at the earliest `SmartLifecycle` stop phase, using `spring.lifecycle.timeout-per-shutdown-phase` as a **per-phase** budget.

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
```

**Do not confuse these 10 seconds with “the JVM is guaranteed to stay alive for exactly 10 seconds”.** If requests finish quickly, the phase can finish early. If there are multiple shutdown phases, total context close time can exceed one phase. If the container/orchestrator sends `SIGKILL` before closing completes, no Java cleanup callback can save it.

**How servers reject new requests differs:** per Boot 3.3 docs, Tomcat/Jetty/Reactor Netty stop accepting at the network layer; Undertow may accept connections and return **503**. Persistent connections, proxies, and load balancers also affect results. Do not write tests demanding “every new request during drain must return HTTP 503”; some clients will see connection refused/reset/EOF.

### 2.1. Timeline

```text
T0: App RUNNING, has accepted Requests A and B
        │
T1: Orchestrator marks pod terminating / drains routing
        │
T2: JVM receives SIGTERM → SpringApplication/ApplicationContext closes
        │
T3: Embedded web server begins graceful shutdown
        ├── Refuses new request C
        ├── Request A running → can finish, HTTP 200
        ├── Request B waiting on downstream → waits within grace budget
        └── Readiness → REFUSING_TRAFFIC per Boot lifecycle
        │
T4: If all in-flight finish → web server phase ends early
    If budget expires → shutdown proceeds, remaining requests may be lost
        │
T5: Other beans/executors/resources stop/close per lifecycle
        │
T6: JVM exits if no remaining threads/conditions keep the process alive
        │
   [If Pod grace expires: SIGKILL; Java cleanup does not run]
```

**Note:** the timeline above is a **logical** model and does not guarantee exact per-bean order when custom `SmartLifecycle`/`@PreDestroy` exist. Do not assume a service's `@PreDestroy` always runs after all HTTP client calls finish. Bean ordering and dependencies must be checked.

## 3. Four scopes of work that must be distinguished

| Work type | Who owns the lifecycle? | Does graceful server wait by default? | What you must do |
|---|---|---|---|
| Synchronous HTTP MVC (`GET` inside controller) | Container request | Yes, within the web server's budget | Bound request time + downstream time |
| Servlet MVC async (`Callable`, `DeferredResult`, `WebAsyncTask`) | Servlet async request + executor/source | Can still be an open request if async hasn't completed | Async timeout, executor bounds, completion/error handling |
| WebFlux HTTP `Mono`/`Flux` | Request's reactive subscription | Yes, within server lifecycle limits | Do not `subscribe()` off-chain; bound streams |
| `@Async`/`TaskExecutor` fire-and-forget after returning 202 | Application executor/job system | **Not guaranteed by web graceful** | Executor shutdown policy + persistence/ACK/retry |
| `@Scheduled` task | Dedicated scheduler | Not an HTTP request by default | Scheduler shutdown policy, leases/locks, idempotency |
| Message consumer | Broker listener container | Listener lifecycle, not web server | Stop polling, finish/ack/rollback, redelivery |
| Long-lived WebSocket/SSE | Connection/subscription | Can stay open very long; server/version-specific | Max age, drain notification, close/reconnect |
| Downstream HTTP call from a request | Client + thread/Publisher + downstream service | Only waited on indirectly while part of in-flight request | Timeouts, cancellation, idempotency, and budget |

**Main point:** `server.shutdown=graceful` protects the **web server's in-flight request handling**, not every task/process/transaction in the JVM.

### 3.1. Why is HTTP 202 dangerous if misunderstood?

`POST /jobs` might:
1. Push a task onto an in-memory executor.
2. Immediately return **202 Accepted**.
3. Client believes the work was accepted.
4. Pod receives SIGTERM before the task finishes.
5. Executor is discarded or JVM is killed → task is lost.

Because the HTTP response **already completed**, the graceful web server **has nothing left to wait on** for that task. Raising `spring.lifecycle.timeout-per-shutdown-phase` may help partially if the task executor is configured to wait, yet it **cannot provide durability when a pod crashes**. For critical work, return 202 only after durably writing the job to a DB/queue, return a job ID, and support retries/idempotency/status endpoints.

## 4. Enabling graceful shutdown and bounding timeouts properly

### 4.1. Core properties in Boot 3.3

```properties
# Must be enabled explicitly in Boot 3.3:
server.shutdown=graceful

# Timeout applied per SmartLifecycle shutdown phase:
spring.lifecycle.timeout-per-shutdown-phase=12s
```

Any in-flight request exceeding the budget can be closed after the phase stops. If there is a 30-second downstream call with 12-second grace, you cannot promise the client will get 200/504: the JVM/server may close before the controller writes a response.

**Do not set infinite grace** to “guarantee no lost requests”. A streaming/WebSocket connection can stay open for hours. A pod must stop within rollout/orchestrator deadlines. Bound:
- Maximum HTTP request duration.
- Duration of each downstream call, retry, and queue wait.
- Remaining time for DB commit/response flush.
- Active task count and queue size.
- Executor shutdown wait time.
- Overall Pod grace with a safety margin.

### 4.2. Containerized applications

On Linux Docker, the Java process needs to receive **SIGTERM**. Good entrypoint example:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/graceful-mvc-demo-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app/app.jar"]
```

The jar filename matches only when the Gradle artifact is configured/packaged as shown. This Dockerfile snippet illustrates the **exec form** principle so Java receives signals, not a complete hardened production image (which needs non-root, resource limits, base image security, proper secrets/CA).

**Pitfall:** `ENTRYPOINT sh -c "java -jar app.jar"` where the shell does not `exec` and does not forward SIGTERM. The orchestrator may signal PID 1 (the shell), Java never receives the signal in time, and graceful shutdown fails to happen as expected.

### 4.3. Do not use Ctrl+C/IDE Stop as your only test

`Ctrl+C` in a terminal usually sends an appropriate signal. An IDE Stop button, Task Manager, or process kill on some platforms can terminate **without running the context-closing lifecycle**. `kill -9` sends SIGKILL and definitely skips graceful Java cleanup. For real testing, send `SIGTERM` directly to the JVM process in Linux/containers and observe clients/network/executors.

## 5. Synchronous request path and downstream calls

Suppose `GET /api/proxy` is running:

```text
HTTP client             Spring Boot A                  Service B
     │                        │                           │
     ├── GET /api/proxy ─────►│                           │
     │                        ├── GET /remote ───────────►│
     │                        │        waiting on B       │
  SIGTERM to A                │                           │
     │                        │ Graceful: waits A in-flight
     │                        │                           │
     │                        │◄────────── HTTP 200 ───────┤
     │◄──── HTTP 200 ─────────┤                           │
     │                        │ request complete          │
```

Here A can return a successful response **if**:
- Service B responds within its timeout and A's context keeps client/connection pools alive.
- The web server graceful budget is long enough.
- Proxies/networks keep the connection open to terminating A.
- No DB/serialization/response-flush error occurs.
- Pod SIGKILL does not hit before completion.

Graceful shutdown on A **does not extend B's timeout**. Blocking `RestClient`/`RestTemplate` calls have the HTTP client's own connection/read timeouts; `WebClient` has response timeouts and the Reactor `timeout` operator. If B does not answer, an A request can still stall even though A stopped admitting new requests.

### 5.1. End-to-end flow timeout budget

Qualitative example:
- Pod termination grace: **30s**.
- preStop/endpoint propagation: **5s**.
- HTTP server graceful phase: **15s**.
- Downstream connect timeout: **1s**.
- Downstream read/response timeout: **4s**.
- Business retry: at most **1 retry** with small backoff and idempotency.
- Total request target: **< 10s** leaving time for serialization/flush and bean shutdown.

This is an **illustrative budget**, not an inequality automatically enforced by Spring. Total shutdown can include multiple phases and executor waits, and Kubernetes starts counting grace **before running preStop**. Measure under load and add margin.

**Do not chain 3 libraries with 20s timeouts each and expect the request to finish in 10s.** In an A→B→C call chain, use a shared deadline or propagate remaining budget and cap retries so every layer does not claim the full time for itself.

## 6. Servlet async: `Callable` and `DeferredResult` are still in-flight HTTP

Spring MVC supports asynchronous request processing based on Servlet async:
- `Callable<T>`: controller returns a Callable; Spring MVC submits it to AsyncTaskExecutor and dispatches the response once ready.
- `WebAsyncTask<T>`: like Callable, with customizable timeout/executor.
- `DeferredResult<T>`: response stays open until another thread/event calls `setResult` or `setErrorResult`.
- `CompletionStage<T>`/`CompletableFuture<T>` or reactive return types are adapted by Spring MVC per contract.
- `ResponseBodyEmitter`/`SseEmitter`: keep an HTTP response streaming for multiple events.

```java
// Illustrative MVC controller snippet:
@GetMapping("/api/async")
Callable<String> async() {
    return () -> {
        Thread.sleep(400);
        return "completed";
    };
}
```

**Seeing the controller method return is not enough to know the request finished.** `Callable` is returned immediately, yet the Servlet async response remains open; the container dispatches the response after the task completes. Consequently, it can still count as an in-flight request in the graceful server.

**Completely different from `@Async void`:**

```java
// Illustrative controller snippet:
@PostMapping("/api/fire-and-forget")
ResponseEntity<Void> start() {
    jobService.runInBackground(); // @Async on another bean.
    return ResponseEntity.accepted().build(); // HTTP 202 already ended.
}
```

With `@Async`, the HTTP request does not automatically wait for the job. If the controller must hold the request until the job returns a result, return `CompletableFuture<T>`/`Callable<T>`/`DeferredResult<T>` appropriately and do not send 202 before guaranteeing durability.

**Do not assume the default MVC async executor suits production load.** Spring Framework docs require configuring a bounded `AsyncTaskExecutor` if using Callable/streaming at scale, along with timeouts/pool/queue bounds. Servlet `asyncTimeout` can also differ from downstream read timeouts. A handler timeout does not automatically cancel a blocking SDK call that ignores interruption.

## 7. Project A: Spring Boot MVC demonstrating three coexisting work types

Standalone runnable project **Java 17+ + Spring Boot 3.3.13 + Gradle**:
- `GET /api/slow?ms=...`: in-flight synchronous MVC request.
- `GET /api/async?ms=...`: Servlet async `Callable`.
- `GET /api/proxy?ms=...`: calls downstream HTTP via `RestClient` with connect/read timeouts.
- `POST /api/jobs?ms=...`: starts an `@Async` task and immediately returns 202; it is **not HTTP in-flight** after the response.
- `GET /api/jobs/completed`: count of finished jobs, for lab observation.
- A mini JDK HTTP server in a separate process simulates downstream; the backend app does not call HTTP back into itself during shutdown.

### 7.1. Structure

```text
graceful-mvc-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/graceful/
    │   │   ├── MvcShutdownApplication.java
    │   │   └── DemoPartnerServer.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/graceful/MvcShutdownIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

// Run the mock downstream in a separate process from the Spring Boot app.
tasks.register('partnerRun', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.graceful.DemoPartnerServer'
}
```

Actuator is added to check readiness/metrics; Spring Security is omitted in the demo to keep the lesson simple. **Do not expose lab endpoints and public metrics in production**; protect management ports/actuator per security policy.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=graceful-mvc-demo

# Spring Boot 3.3: enable explicitly.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s

# HTTP client calls a separate process, not this app itself.
demo.downstream.base-url=http://127.0.0.1:9090

# Servlet async request timeout, independent of downstream read timeout.
spring.mvc.async.request-timeout=5s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info,metrics
```

### 7.2. Application: controller, RestClient, and bounded @Async executor

**`src/main/java/com/example/graceful/MvcShutdownApplication.java`:**

```java
package com.example.graceful;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@SpringBootApplication
@EnableAsync
public class MvcShutdownApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcShutdownApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ClientAndExecutorConfiguration {

    @Bean
    RestClient partnerClient(
            RestClient.Builder builder,
            @Value("${demo.downstream.base-url}") String baseUrl) {

        // Lab only: HTTP URL; production needs HTTPS + auth/TLS policy.
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1000);
        factory.setReadTimeout(3000);

        return builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @Bean("jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("demo-job-");

        // Separate from HTTP graceful: dedicated wait config for background executor.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}

@Component
class WorkSignals {
    final CountDownLatch requestEntered = new CountDownLatch(1);
    final CountDownLatch jobStarted = new CountDownLatch(1);
    final AtomicInteger jobsCompleted = new AtomicInteger();
}

@Service
class AuditJobService {

    private static final Logger log =
            LoggerFactory.getLogger(AuditJobService.class);
    private final WorkSignals signals;

    AuditJobService(WorkSignals signals) {
        this.signals = signals;
    }

    @Async("jobExecutor")
    public CompletableFuture<Void> execute(long ms) {
        signals.jobStarted.countDown();
        try {
            Thread.sleep(Math.max(0, Math.min(ms, 2500)));
            signals.jobsCompleted.incrementAndGet();
            log.info("Background demo job completed");
            return CompletableFuture.completedFuture(null);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(interrupted);
        }
    }
}

@RestController
class WorkController {

    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);

    private final RestClient partner;
    private final AuditJobService jobs;
    private final WorkSignals signals;

    WorkController(RestClient partner, AuditJobService jobs,
            WorkSignals signals) {
        this.partner = partner;
        this.jobs = jobs;
        this.signals = signals;
    }

    @GetMapping("/api/slow")
    Map<String, String> slow(
            @RequestParam(defaultValue = "400") long ms)
            throws InterruptedException {

        signals.requestEntered.countDown();
        Thread.sleep(Math.max(0, Math.min(ms, 2500)));
        return Map.of("result", "slow-done");
    }

    @GetMapping("/api/async")
    Callable<Map<String, String>> async(
            @RequestParam(defaultValue = "400") long ms) {

        return () -> {
            Thread.sleep(Math.max(0, Math.min(ms, 2500)));
            return Map.of("result", "async-done");
        };
    }

    @GetMapping("/api/proxy")
    String proxy(@RequestParam(defaultValue = "400") long ms) {
        long bounded = Math.max(0, Math.min(ms, 2500));

        // Current request stays open; RestClient call is blocking.
        // Web graceful will wait only within the shutdown budget.
        return partner.get()
                .uri("/remote?ms={ms}", bounded)
                .retrieve()
                .body(String.class);
    }

    @PostMapping("/api/jobs")
    ResponseEntity<Void> enqueue(
            @RequestParam(defaultValue = "400") long ms) {

        jobs.execute(Math.max(0, Math.min(ms, 2500)))
                .whenComplete((unused, failure) -> {
                    if (failure != null) {
                        log.warn("Background job failed: {}",
                                failure.toString());
                    }
                });

        // HTTP ends here, even though the task is still running!
        return ResponseEntity.accepted().build();
    }

    @GetMapping("/api/jobs/completed")
    Map<String, Integer> jobsCompleted() {
        return Map.of("completed", signals.jobsCompleted.get());
    }
}
```

**Runnability and scope of the example:**
- A single Java file contains one top-level `public class` named `MvcShutdownApplication`; the other package-private classes in the same package make Boot component scanning and bean definitions valid.
- `@EnableAsync` activates `@Async`; `AuditJobService` is a **different bean from the controller**, so calls pass through the Spring proxy and the annotation takes effect. Self-invocation `this.execute(...)` inside the same service would bypass the proxy and run synchronously.
- `jobExecutor` sets a **bounded** queue (10) and two worker threads. Under overload, the executor can reject; the demo implements no custom mapping for `TaskRejectedException`. Production must enforce admission/quotas and return 202 only after durable acceptance.
- `setWaitForTasksToCompleteOnShutdown(true)` with `setAwaitTerminationSeconds(5)` lets the executor wait for already-accepted jobs when the bean is destroyed, **without turning them into HTTP requests**. Nor does it replace the Kubernetes termination budget.
- `SimpleClientHttpRequestFactory` provides connect/read timeouts per Java 17 transport. Using this factory rather than defaults ensures the demo has timeouts; production must verify proxy/TLS/pool/observability of the client implementation.
- `Thread.sleep(...)` is used solely to simulate blocking work in the lab's MVC/async workers. Do not use it on a Netty event loop in WebFlux.
- `WorkSignals` is an **in-memory** latch/counter **for tests only**. It does not provide durable job status; if the JVM crashes, the count vanishes.
- `/api/jobs` has no auth in the demo, so it is unsuitable for public production.
- The `@Async` method returns `CompletableFuture<Void>` so callers can observe failures via `whenComplete`, unlike `void` async which only reports errors to `AsyncUncaughtExceptionHandler`. However, returning 202 without a durable job record is a **job-loss risk**, illustrated intentionally.

### 7.3. Downstream server running in another process

To avoid calling back into the same shutting-down server, use JDK `com.sun.net.httpserver.HttpServer` as a mock partner. **`src/main/java/com/example/graceful/DemoPartnerServer.java`:**

```java
package com.example.graceful;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpServer;

public final class DemoPartnerServer {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9090), 0);
        ExecutorService threads = Executors.newFixedThreadPool(4);
        server.setExecutor(threads);

        server.createContext("/remote", exchange -> {
            try {
                String query = exchange.getRequestURI().getRawQuery();
                long ms = 400;
                if (query != null && query.startsWith("ms=")) {
                    ms = Long.parseLong(query.substring(3));
                }
                Thread.sleep(Math.max(0, Math.min(ms, 2500)));

                byte[] bytes = "partner-ok".getBytes(
                        StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(bytes);
                }
            } catch (Exception error) {
                exchange.close();
                if (error instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            }
        });

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(0);
            threads.shutdownNow();
        }));

        server.start();
        System.out.println("Partner running on http://127.0.0.1:9090");
    }
}
```

This is a **separate test process**, not a production HTTP backend:
- No auth, no HTTPS, no request logging/metrics.
- Delay input is clamped to 2500ms max; malformed `ms` may close the connection.
- `threads` has at most four workers, not a load generator.
- The Spring Boot app can still stop while downstream is processing a request; the two processes have separate shutdown lifecycles.

### 7.4. How to run the two processes

In terminal 1:

```bash
gradle partnerRun
```

Expected output:

```text
Partner running on http://127.0.0.1:9090
```

In terminal 2:

```bash
gradle bootRun
```

If the project has the Gradle wrapper: `./gradlew partnerRun` and `./gradlew bootRun` on Linux/macOS; PowerShell uses `.\gradlew.bat`. JDK 17+ and a Gradle version compatible with Boot 3.3.13 are required. Boot app runs on `localhost:8080`, partner on `localhost:9090`.

Test:

```bash
curl -i "http://localhost:8080/api/slow?ms=500"
curl -i "http://localhost:8080/api/async?ms=500"
curl -i "http://localhost:8080/api/proxy?ms=500"
curl -i -X POST "http://localhost:8080/api/jobs?ms=500"
curl -i "http://localhost:8080/api/jobs/completed"
```

Expected responses, **not verified live execution stdout**:

| Request | Expected status/body |
|---|---|
| `GET /api/slow` | 200 and `{"result":"slow-done"}` |
| `GET /api/async` | 200 and `{"result":"async-done"}` |
| `GET /api/proxy` | 200 and text `partner-ok` |
| `POST /api/jobs` | 202, usually empty body |
| `GET /api/jobs/completed` | `{"completed":0}` or `{"completed":1}` depending on whether the task finished |

**Do not treat 202 as proof the task finished**, and do not treat `jobCompleted=1` as proof data is durable in a DB; this is only an in-memory lab counter.

## 8. Integration tests for in-flight HTTP and @Async job when context closes

To prove **graceful differs from normal controller execution**, we start a Spring Boot context on a random port, send an HTTP request via JDK `HttpClient.sendAsync`, wait for the handler to actually start using `CountDownLatch`, and then **call `context.close()` while the request is running**. If the budget is sufficient, the request has a chance to return 200 before the context closes.

Do not perform this kind of test on a `@SpringBootTest` context shared across multiple tests, because one test closing the context breaks the other tests. Each test below creates/stops an independent context.

**`src/test/java/com/example/graceful/MvcShutdownIntegrationTest.java`:**

```java
package com.example.graceful;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MvcShutdownIntegrationTest {

    private ConfigurableApplicationContext start() {
        return new SpringApplicationBuilder(MvcShutdownApplication.class)
                .properties(
                        "server.port=0",
                        "server.shutdown=graceful",
                        "spring.lifecycle.timeout-per-shutdown-phase=5s",
                        "demo.downstream.base-url=http://127.0.0.1:9090")
                .run();
    }

    private int port(ConfigurableApplicationContext ctx) {
        return ctx.getBean(
                ServletWebServerApplicationContext.class)
                .getWebServer().getPort();
    }

    private HttpRequest get(int port, String path) {
        return HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();
    }

    @Test
    void runningHttpRequestCanFinishDuringGracefulClose()
            throws Exception {
        ConfigurableApplicationContext context = start();
        try {
            int port = port(context);
            WorkSignals signals = context.getBean(WorkSignals.class);
            HttpClient client = HttpClient.newHttpClient();

            CompletableFuture<HttpResponse<String>> request =
                    client.sendAsync(
                            get(port, "/api/slow?ms=450"),
                            HttpResponse.BodyHandlers.ofString());

            // Ensure the request actually entered the controller before shutdown.
            assertTrue(signals.requestEntered.await(
                    3, TimeUnit.SECONDS));

            context.close(); // Waits for the graceful web phase.

            HttpResponse<String> response = request.get(
                    3, TimeUnit.SECONDS);
            assertEquals(200, response.statusCode());
            assertTrue(response.body().contains("slow-done"));
        } finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }

    @Test
    void acceptedBackgroundJobNeedsItsOwnExecutorDrain()
            throws Exception {
        ConfigurableApplicationContext context = start();
        try {
            int port = port(context);
            WorkSignals signals = context.getBean(WorkSignals.class);
            HttpClient client = HttpClient.newHttpClient();

            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(
                            "http://127.0.0.1:" + port
                                    + "/api/jobs?ms=450"))
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .build();

            HttpResponse<String> response = client.send(
                    post, HttpResponse.BodyHandlers.ofString());

            assertEquals(202, response.statusCode());
            assertTrue(signals.jobStarted.await(
                    3, TimeUnit.SECONDS));

            // HTTP 202 already ended; this waits for jobExecutor.
            context.close();

            assertEquals(1, signals.jobsCompleted.get());
        } finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

Run:

```bash
gradle test
```

**Expectation:** both tests pass with proper config and an unburdened test machine. These are **statically reviewed tests**, **not executed with Gradle here**. The tests are meaningful because:
- Requests go over Tomcat's network layer on a random port rather than calling controller methods directly.
- Latches ensure the request/job **already started before** calling `context.close`, reducing races where a test accidentally checks an unstarted request.
- The HTTP test proves server grace can wait for a short in-flight request.
- The background test proves HTTP 202 already ended yet an executor **configured separately to wait** can still complete the job.
- Neither proves the process will survive beyond the Kubernetes grace budget or that tasks survive `SIGKILL`. Real deployment testing is needed.

**Do not rigidly assert that new requests during draining must return 503.** With Boot 3.3 Tomcat, new connections can be rejected at the network layer, causing JDK `HttpClient` to get `IOException`/`ConnectException` without the request reaching a controller.

### 8.1. Testing downstream calls during shutdown

In a **separate test**, run a mock HTTP partner server on a random port with a latch signaling it received the request, then call `GET /api/proxy` on the Boot app, wait for the partner to receive it, and close the app. When the partner responds within the client timeout and graceful budget, the initial HTTP client can receive `partner-ok`.

A complete test needs to:
1. Start `HttpServer` on port 0 with its own `ExecutorService`.
2. Pass `demo.downstream.base-url=http://127.0.0.1:<actual-port>` to `SpringApplicationBuilder`.
3. Have the mock partner count down the latch **after receiving the request**, sleep ~350ms, and return `partner-ok`.
4. Send HTTP `/api/proxy?ms=350` via `sendAsync`.
5. Wait on the mock partner latch, then call `context.close()`.
6. Assert HTTP 200/body and stop the partner server/executor in `finally`.

Do not place the mock downstream inside **the same shutting-down Boot web server**, because once the app stops accepting new requests, outbound RestClient calls to `localhost:8080` may be rejected immediately even though the outer request is in-flight. A **separate process/server** mock accurately simulates an independent downstream.

## 9. Common mistakes with @Async and executors during shutdown

### 9.1. `@Async` does not mean “job guaranteed to run”

`@Async` actually routes the method call through a proxy and submits a task to an `Executor`. It does not write events/transactions to a broker. Risks:
- In-memory queues vanish on JVM crash.
- A task accepted before shutdown but not started yet may be canceled depending on executor policy.
- Tasks running during shutdown may depend on a DB pool that has already closed.
- Tasks may be interrupted; blocking I/O does not always stop on interrupt.
- Task timeouts do not roll back already-committed transactions.
- Exceptions from `@Async void` usually do not travel back to the HTTP caller.
- Self-invocation within the same bean may bypass the proxy and run synchronously.

An application `@Bean ThreadPoolTaskExecutor` should configure:
- Finite `corePoolSize`, `maxPoolSize`, `queueCapacity`.
- Rejection policy and HTTP response when admission fails.
- `setWaitForTasksToCompleteOnShutdown(true)` **if** you want to wait for already-accepted tasks.
- `setAwaitTerminationSeconds(...)` long enough for short tasks without exceeding the Pod budget.
- No accepting new jobs while draining (application admission flag/queue gating).
- Terminal success/error handling and durable results.

**Spring Framework 6.1 note:** `setWaitForTasksToCompleteOnShutdown(true)` has **late shutdown** executor semantics, letting running/queued tasks proceed while the Spring context is closing. This can conflict if they need DB/client beans being destroyed at the same time. Depending on the case, coordinating early drain via `SmartLifecycle` with explicit phases/dependencies or handing jobs to a durable broker is safer. Do not assume await-termination “fixes all ordering”.

### 9.2. Boot auto-configured task execution properties

For builders/executors auto-configured by Boot 3.3, there are properties:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100

spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=8s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=8s
```

These properties **do not necessarily apply to a `jobExecutor` bean manually declared via `new ThreadPoolTaskExecutor()`** as in the example, because custom beans have their own settings. Do not set `spring.task.execution.shutdown.await-termination=true` and assume every `Executors.newSingleThreadExecutor()` in code is managed by Boot. Bare JDK executors, `CompletableFuture.supplyAsync(...)` using the common pool, SDK timers, or manually spawned threads **fall outside shutdown policies** unless lifecycle-managed.

**Boot 3.3 adds a Java 21 virtual threads option** when `spring.threads.virtual.enabled=true` is enabled; it changes concurrency/executor considerations, though this lesson uses Java 17 and does not rely on virtual threads. Do not treat “virtual threads” as a replacement for timeouts/durability.

### 9.3. If tasks must finish reliably

Prefer this pattern:
1. Request validates input and generates an **idempotency key / job ID**.
2. Writes `PENDING` state to the DB inside a transaction/outbox where appropriate.
3. Returns 202 **only after the durable commit**.
4. A worker claims the job with a lease, executes it, and writes `DONE` or `FAILED_RETRYABLE`.
5. During shutdown, the worker stops claiming new jobs and tries to finish what is running within limits.
6. If killed, the lease expires → another worker retries with idempotent side effects.

Executor waiting alone is just an optimization to reduce retries, not a replacement for durability.

## 10. Downstream calls: timeouts, cancellation, retries, and “processed but response lost”

A downstream timeout has at least two possibilities:
- Server B **has not** processed the request; caller A timed out.
- Server B **committed** the change (e.g., payment), yet the response was lost or A shut down before receiving/writing the response.

Therefore:

```text
A POST /payments ─► B
       │              └── DB COMMIT ✓
       │
  A loses connection/timeout
       │
  Caller retries POST?
       └── Without an idempotency key → may charge twice
```

**Graceful shutdown does not provide exactly-once** across client, A, B, and the database. You need:
- Idempotency keys for all operations with side effects.
- Unique constraints/transactional dedup or outbox/inbox.
- Retry policies with max attempts, backoff, and **remaining deadline**.
- Distinguishing retryable network failures from business 4xx errors.
- Response reconciliation/status queries for “unknown outcomes”.
- Client timeouts smaller than request/grace budgets appropriately.
- Never destroying/closing downstream client pools before in-flight callers finish.

### 10.1. Connect timeout and read/response timeout differ

`RestClient` and `RestTemplate` are blocking APIs. Configure `connect timeout` (establishing connection) and `read timeout` (waiting to read). HTTP client implementations differ in semantics, and total business timeouts may require a separate deadline. `WebClient` is reactive and can configure Reactor Netty `responseTimeout(...)` and/or `Mono.timeout(...)`. Neither mechanism means “the upstream server successfully canceled the request”.

The MVC example used `SimpleClientHttpRequestFactory`:
- Connect timeout 1s.
- Read timeout 3s.
- Graceful server phase 10s.
- Partner demo delay ≤2.5s.

An already-established connection can still take longer overall due to multiple reads, retries, or business orchestration; **do not call a socket timeout an end-to-end SLA**.

### 10.2. Client disconnect and server-side work

When a browser closes a tab while waiting:
- An MVC blocking controller may **only detect disconnect when reading/writing the socket**, rather than immediately interrupting every DB/HTTP call.
- Spring MVC `DeferredResult.onTimeout`, `onError`, and `onCompletion` are useful for cleanup, but do not guarantee interrupting blocking work outside their scope.
- In WebFlux, connection cancellation can propagate to reactive publishers like WebClient, depending on subscription topology/operators/drivers.
- A downstream that already received the request may keep processing even if caller A cancels; **cancellation is best effort**.
- If a command has side effects, you need idempotency/reconciliation—do not treat cancel as rollback.

**Do not call `subscribe()` and discard the result inside a reactive HTTP handler**: doing so detaches work from the request, removing it from graceful/timeout/cancellation management.

## 11. WebFlux: publishers stay alive while requests run

In Spring WebFlux, handlers return `Mono<T>`/`Flux<T>`. The subscription is managed by the WebFlux server, and stream completion/error/cancel governs the HTTP response lifecycle.

```java
// Code snippet in a WebFlux @RestController:
@GetMapping("/api/slow")
Mono<String> slow() {
    return Mono.delay(Duration.ofMillis(500))
            .map(ignored -> "reactive-done");
}
```

This is an **illustrative snippet**; import `Mono`, `Duration`, and WebFlux annotations. Do not use `Thread.sleep(500)` on a Reactor Netty event loop: a single blocking call can stall many requests sharing that event loop.

### 11.1. WebClient attached to the same reactive chain

```java
// Code snippet inside a service with injected WebClient:
Mono<String> reply = client.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3))
        .doFinally(signal ->
                log.debug("Downstream finished: {}", signal));

return reply;
```

`doFinally` can observe `ON_COMPLETE`, `ON_ERROR`, or `CANCEL` at that operator position. **It does not prove the downstream side did not process the request or rolled back.** Spring WebFlux may cancel client I/O/subscriptions, yet downstream may continue depending on its implementation.

### 11.2. The `Mono.when` trap with non-ending streams

If an SSE/WebSocket endpoint returns an infinite `Flux.interval(...)`, “in-flight” can hold the connection for hours. On shutdown, the server **cannot wait forever** when grace has a budget. For long-lived streams:
- Set a max connection/session age or heartbeat/idle timeout.
- Emit an app-level drain/close signal so clients reconnect to a new instance.
- Choose a policy to complete streams/close WebSockets with an appropriate code.
- Prefer letting clients reconnect with jitter and resume via cursor/sequence if business requires.
- Do not allocate an unbounded `Sinks.Many` per client without checking memory.
- Ensure buffers/data resources are released on terminal/cancel.
- For WebSocket and SSE, inspect the exact behavior of your embedded server version instead of assuming every connection finishes before grace.

## 12. Project B: WebFlux reactive slow request and downstream WebClient

Standalone project **Spring Boot 3.3.13, Java 17+**, omitting `spring-boot-starter-web` so the actual server is Reactor Netty. Includes:
- `GET /api/slow?ms=...` using `Mono.delay`, observing subscribe/termination/cancel.
- `GET /api/proxy?ms=...` calling the separate downstream via `WebClient` with a finite timeout.
- Actuator readiness/metrics to check the drain process.

**Structure:**

```text
graceful-webflux-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivegraceful/
    │   │   └── ReactiveShutdownApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivegraceful/
            └── ReactiveShutdownIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
spring.application.name=graceful-webflux-demo
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
demo.downstream.base-url=http://127.0.0.1:9090

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info,metrics
```

**`src/main/java/com/example/reactivegraceful/ReactiveShutdownApplication.java`:**

```java
package com.example.reactivegraceful;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveShutdownApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveShutdownApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ReactiveClientConfiguration {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            @Value("${demo.downstream.base-url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}

@Component
class ReactiveSignals {
    final CountDownLatch requestSubscribed = new CountDownLatch(1);
    final AtomicInteger cancelled = new AtomicInteger();
}

@RestController
class ReactiveWorkController {

    private static final Logger log =
            LoggerFactory.getLogger(ReactiveWorkController.class);

    private final WebClient partner;
    private final ReactiveSignals signals;

    ReactiveWorkController(WebClient partner, ReactiveSignals signals) {
        this.partner = partner;
        this.signals = signals;
    }

    @GetMapping("/api/slow")
    Mono<String> slow(
            @RequestParam(defaultValue = "400") long ms) {
        long bounded = Math.max(0, Math.min(ms, 2500));

        return Mono.delay(Duration.ofMillis(bounded))
                .map(ignored -> "reactive-done")
                .doOnSubscribe(subscription ->
                        signals.requestSubscribed.countDown())
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        signals.cancelled.incrementAndGet();
                    }
                    log.info("Reactive slow finished: {}", signal);
                });
    }

    @GetMapping("/api/proxy")
    Mono<String> proxy(
            @RequestParam(defaultValue = "400") long ms) {
        long bounded = Math.max(0, Math.min(ms, 2500));

        return partner.get()
                .uri("/remote?ms={ms}", bounded)
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(3))
                .doFinally(signal ->
                        log.info("Reactive downstream finished: {}",
                                signal));
    }
}
```

**Key explanations:**
- `Mono.delay` schedules a non-blocking timer rather than holding a Servlet worker thread for 400ms.
- `doOnSubscribe` counts only when the reactive chain is subscribed, convenient for checking true in-flight status.
- `doFinally` can log `ON_COMPLETE`, `ON_ERROR`, `CANCEL`; it is not a transaction log.
- `WebClient` is built via Boot's builder; the HTTP partner runs in a separate process rather than calling back into WebFlux port 8081 during shutdown.
- `timeout(Duration.ofSeconds(3))` is the Publisher's deadline, **not a guarantee the remote server stops processing** once it received the request.
- The demo file has only one top-level `public class`; package-private bean/config classes are scanned by Boot.

### 12.1. Running WebFlux

Start `DemoPartnerServer` from the MVC project in a separate terminal (or an equivalent mock HTTP server on port 9090), then from the WebFlux project directory:

```bash
gradle bootRun
curl -i "http://localhost:8081/api/slow?ms=400"
curl -i "http://localhost:8081/api/proxy?ms=400"
```

Expected: `/api/slow` returns HTTP 200 with body `reactive-done`; `/api/proxy` returns `partner-ok` if the partner is running. All outcomes depend on network/timeouts and **are not live execution output from this environment**.

### 12.2. Testing in-flight WebFlux on context close

**`src/test/java/com/example/reactivegraceful/ReactiveShutdownIntegrationTest.java`:**

```java
package com.example.reactivegraceful;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveShutdownIntegrationTest {

    @Test
    void reactiveRequestCanCompleteDuringGracefulClose()
            throws Exception {
        ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        ReactiveShutdownApplication.class)
                    .properties(
                            "server.port=0",
                            "server.shutdown=graceful",
                            "spring.lifecycle.timeout-per-shutdown-phase=5s",
                            "demo.downstream.base-url=http://127.0.0.1:9090")
                    .run();

        try {
            int port = context.getBean(
                    ReactiveWebServerApplicationContext.class)
                    .getWebServer().getPort();

            ReactiveSignals signals = context.getBean(
                    ReactiveSignals.class);
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create(
                            "http://127.0.0.1:" + port
                                    + "/api/slow?ms=450"))
                    .GET()
                    .build();

            CompletableFuture<HttpResponse<String>> inFlight =
                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString());

            assertTrue(signals.requestSubscribed.await(
                    3, TimeUnit.SECONDS));

            context.close();

            HttpResponse<String> response = inFlight.get(
                    3, TimeUnit.SECONDS);
            assertEquals(200, response.statusCode());
            assertEquals("reactive-done", response.body());
            assertEquals(0, signals.cancelled.get());
        } finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

**Expectation:** the test passes if Reactor Netty/Boot keeps the short running request until completion. It verifies the server can drain a 450ms HTTP request within a 5s budget, not that infinite streams or downstream operations all complete. This code was **statically reviewed, not executed with Gradle**.

**Note on shutdown racing:** sometimes the HTTP client receives the response while the Netty close event arrives in the same window. The test uses a latch to know the subscription started; do not use arbitrary sleep before `context.close`. If flakiness persists in CI, collect logs/network events and tune deadlines/test synchronization instead of changing business code for a single network glitch.

## 13. Cancellation in WebFlux and downstream calls

Suppose a WebFlux controller executes:
```java
return webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .doFinally(signal -> log.info("Signal: {}", signal));
```

If the HTTP client calling Spring Boot closes the connection, the server **may** emit `cancel` into the reactive subscription. Reactor Netty WebClient can stop reading the response or close the connection. However:
- Downstream B might still be processing and unaware the caller no longer wants the result.
- A DB driver might have committed already.
- Running `doOnCancel` does not replace closing files/database transactions.
- An `onErrorResume` might turn a timeout into a fallback response, causing the client to get 200 instead of 504 per policy.
- `retryWhen` might re-send a request with side effects, causing duplicates.
- Synchronous adapters or `Mono.fromCallable(...)` on boundedElastic may not cancel threads/SDKs immediately.
- `WebClient` HTTP response streaming must release `DataBuffer` when manually consumed/relayed; connection close does not replace ownership management outside the pipeline.

**Do not infer from a CANCEL signal that downstream rolled back.** In observability, classify `ON_COMPLETE`, `ON_ERROR`, and `CANCEL` separately, attaching correlation/tracing IDs with allowed log fields.

If you must call B and then write to DB, try to keep the request in **a single reactive chain** with clear timeouts, retries, and transaction boundaries. Do not manually `subscribe()` in the middle and return `Mono.just("accepted")` unless it is genuinely a job workflow with durable handoff.

## 14. Stop background jobs before or after the HTTP listener?

A production workflow typically has two goals:
1. **Accept no new work** once draining starts.
2. **Finish already-accepted work** up to a deadline, then stop safely/save retry state.

Waiting for all jobs before closing the HTTP server is not always right:
- Jobs may keep consuming DB/HTTP client resources.
- If the executor is destroyed **after** the DataSource, running tasks may hit `Connection pool is closed`.
- If the downstream client closes too early, waiting HTTP requests will error.
- If jobs keep being admitted when the service is unready, the queue grows again.
- If `@PreDestroy` blocks forever, deployment gets SIGKILLed.

Good design:
- **Admission gate**: when readiness switches to `REFUSING_TRAFFIC`, reject new job requests/new queue polling.
- **Drain deadline**: record the remaining end time and let tasks that can finish within budget wrap up.
- **Dependency lifetime**: keep DB/client connection pools alive until tasks actually needing them finish.
- **Final state**: unfinished jobs are persisted/requeued/retried rather than silently lost.
- **Lifecycle coordination**: use `SmartLifecycle` with logical phases/dependencies or a dedicated job manager. Do not copy an arbitrary `@PreDestroy` order assuming Spring magically infers task-to-resource dependencies.
- **Force stop** after budget: cancel/interrupt where supported, log/count unfinished work, and let the system recover.

### 14.1. SmartLifecycle: use when special coordination is needed

`SmartLifecycle` has `isRunning()`, `start()`, `stop(Runnable callback)`, `getPhase()`. During shutdown, Spring stops phases **from high to low** (beans in the same phase may stop as a group). You can use a component to stop **job intake** first, wait for short in-flight jobs, and then invoke the callback; phases/bean dependencies must be defined carefully so total shutdown time is not exceeded.

**Illustrative skeleton, not a complete implementation:**

```java
// Inside a class implementing SmartLifecycle:
@Override
public void stop(Runnable callback) {
    acceptingNewJobs.set(false);

    // Must call callback after drain or deadline.
    // Do not hold callback indefinitely if a queue has a hung job.
    stopListeningAndWaitWithinBudget()
            .whenComplete((unused, error) -> callback.run());
}
```

The variables/method `acceptingNewJobs` and `stopListeningAndWaitWithinBudget()` must be implemented. **Do not copy pseudocode as a runnable bean.** Never invoke the callback early while jobs still rely on resources that must stay alive; never omit the callback, which leaves the phase waiting until timeout.

## 15. Kubernetes: readiness, preStop, and SIGTERM must align

Kubernetes Pod termination is an **orchestrator workflow**, not a Spring Boot property:

1. Pod is marked terminating; EndpointSlice updates mark the endpoint not `ready` to gradually pull it from routing.
2. Kubelet runs the `preStop` hook if configured (and termination grace is non-zero).
3. **The grace period has already been counting since termination started**, not after preStop finishes.
4. After preStop, the runtime sends SIGTERM to PID 1 Java.
5. Spring Boot begins graceful shutdown/context close.
6. If `terminationGracePeriodSeconds` is exceeded, the container receives SIGKILL; Java cleanup does not run.

### 15.1. Example configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: graceful-api
  template:
    metadata:
      labels:
        app: graceful-api
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: api
          image: example.registry/graceful-api:1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
```

This is an **example Kubernetes manifest**; the image is an illustrative placeholder and incomplete for production: it still needs namespace, securityContext/non-root, resource requests/limits, liveness/startup probes, secret config, PDB, affinity, actual image, HPA, and network policies per system. `sleep 5` in `preStop` only creates a window for endpoint propagation in some infrastructures; it does not make Spring Boot graceful start earlier because **SIGTERM arrives after preStop**.

**Reading the budget:**
- 40s total Pod grace.
- 5s preStop immediately consumes **5s of the 40s**.
- Spring context close and all web/executor phases must fit within the remaining time, plus operational margin.
- If preStop hangs for 39s, barely 1s remains for Java graceful shutdown; `timeout-per-shutdown-phase=30s` cannot fix that.
- If ingress/LB propagation is slow, new requests may still reach the stopping backend; health checks/routing/drain must be designed and measured.

### 15.2. Spring Boot readiness

With Actuator and probes enabled, Boot manages `ApplicationAvailability` with:
- `ReadinessState.ACCEPTING_TRAFFIC` when the app is ready.
- `ReadinessState.REFUSING_TRAFFIC` during shutdown.
- `LivenessState` to detect a broken process (do not tie every downstream error to liveness).

Commonly used endpoints:
- `/actuator/health/liveness`.
- `/actuator/health/readiness`.

**Do not use a health check to a shared DB as a liveness probe.** A DB outage can make all pods restart in a cascading failure. Readiness depending on business dependencies needs a clear policy, not a rigid checklist.

**Warning:** if the Actuator management port is separate from the application port, readiness probes may pass even while the main server is not accepting requests. Boot docs recommend considering `management.endpoint.health.probes.add-additional-paths=true` to expose `/readyz` and `/livez` on the main server port. Never expose sensitive Actuator endpoints publicly when exposing probes.

## 16. Worker queues and scheduled tasks during shutdown

**Do not lump `@Async` and message listeners into HTTP drain.** For example, a Kafka consumer received a message before SIGTERM and is processing it:
- If offsets auto-commit before processing finishes, the job can be lost.
- If committing after processing and the pod is killed before commit, the message may redeliver.
- If side effects committed yet ACK was not sent, retries can create duplicates.
- If the DataSource closes before the listener, running processing fails.

Broker-dependent solutions:
- Stop polling/receiving new messages when draining.
- Finish in-flight handlers within a bounded deadline.
- ACK/commit only once business work is durable.
- Design **idempotent** handling to survive redelivery.
- Ensure lease/visibility timeouts cover retries, with a dead-letter policy.
- Measure in-flight jobs/consumer lag and unfinished counts.

`spring.task.scheduling.shutdown.await-termination=true` helps Boot-managed schedulers wait for running tasks, yet **says nothing** about Kafka listeners, Rabbit listeners, custom Quartz schedulers, or manually instantiated `ExecutorService`s. Each subsystem needs its own lifecycle policy.

## 17. HTTP request drain does not solve distributed transactions

A single request might simultaneously:
1. Write to database A.
2. Send a command to downstream B.
3. B commits to database B.
4. Caller A loses connection due to shutdown.
5. Client retries.

No Spring graceful property turns three systems into an exactly-once transaction. You must decide on:
- Synchronous idempotent APIs with request IDs.
- Outbox (writing business state and event in the same local transaction).
- Consumer inbox/dedup.
- Saga/compensation if multi-step.
- Status querying by business key after an “unknown outcome”.
- Tolerating duplicate/out-of-order events on retries or reconnects.

### 17.1. Conceptual wrong and right examples

**Wrong:**

```text
client POST /pay
  → A calls B
  → B commits
  → A killed before response
  → client retries same payment without idempotency
  → B commits a 2nd time
```

**Better design direction:**

```text
client POST /pay {idempotencyKey=K}
  → A validates + sends K to B
  → B inserts unique(K) or returns stored result if K exists
  → client times out/retries with same K
  → B returns same business outcome instead of double charging
```

These pseudo-flows illustrate semantics; production requires transactions/unique constraints/correlation/retention policies keeping idempotency records long enough—not just slapping on an arbitrary header and assuming dedup exists.

## 18. Knowing when to stop: auditing and observability

Do not merely log “Application shutdown complete”. Track:

| Group | Metrics/logs |
|---|---|
| HTTP in-flight | Active HTTP requests, request duration, p95/p99 latency, 5xx during drain |
| Web server | Server shutdown start/end, time spent in grace phase, rejected new connections |
| Async executors | Pool active count, queued tasks, rejected submissions, task completion/error/cancel |
| Downstream | Connect/read timeouts, 4xx/5xx, retry counts, in-flight calls, active client pool |
| Reactive | `onComplete` / `onError` / `cancel`, active subscriptions, buffered messages |
| Job durability | Pending/running/retryable jobs, unrenewed leases, duplicate handling |
| Kubernetes | Pod termination reason, SIGTERM→exit duration, termination grace hit/SIGKILL |
| External traffic | LB endpoint deregistration delay, ingress 502/503/resets, client retries |
| Data safety | Orphan temp files, incomplete uploads, unknown transaction outcomes |

Attach trace/correlation IDs to requests and downstream calls per your instrumentation; do not log access tokens, session cookies, raw request bodies, or PII. A reset/EOF request while a pod is terminating is not necessarily a Java bug; separate network drain from real exceptions.

If `http.server.requests` metrics only record completed requests, requests **SIGKILLed before completion** may go unrecorded. Combine client-side/proxy errors and process termination counters; otherwise, server dashboards may look healthy while clients see many errors.

## 19. Pre-production rollout test matrix

| Scenario | What to verify |
|---|---|
| GET 400ms started before SIGTERM, 5s grace | Client gets response, app exits within budget |
| GET 15s, 5s grace | Client may error/cancel; process still stops, does not hang forever |
| Servlet `Callable` running | Async dispatch/response completes when within limit |
| `DeferredResult` never completes | Timeout/cleanup does not push shutdown past grace |
| `@Async` HTTP returns 202 early | Job has durable record or bounded executor drain |
| Executor queue full | Task rejected intentionally; do not return 202 if not accepted |
| Downstream B 400ms, A gets SIGTERM | A waits for B and returns response if budget suffices |
| Downstream B hangs 30s | A has short timeout, does not wait past Pod budget |
| WebFlux `Mono.delay` 450ms | Request can finish during graceful shutdown |
| WebFlux client disconnects mid-downstream call | Cancel/cleanup observed; do not assume B rolled back |
| Infinite SSE/WebSocket/Flux | Close/drain policy exists; does not wait forever |
| Multipart upload streaming | Temp/staging cleanup on cancel, no partial artifact committed |
| Kubernetes preStop 5s + 40s grace | SIGTERM has enough time left, not killed early |
| Rolling update 2 replicas | Readiness/endpoint propagation, no unexpected downtime |
| Pod kill -9 / node crash | Durable job retry + idempotency, not relying on `@PreDestroy` |
| HTTP keep-alive + HTTP/2 multiplex | Request rejection/connection drain per runtime/proxy |
| Request A→B commits then A loses response | Client retry causes no duplicate side effect |
| Slow client upload/download | Bounded queues/timeouts, does not hold drain forever |
| DB pool closes early | Running tasks/jobs do not use already-disposed resources |
| Actuator readiness on separate management port | Probes reflect main server, no false healthy |

Test graceful shutdown with **real HTTP clients** and SIGTERM in containers, not just `MockMvc`. `MockMvc` does not test Servlet container connection draining or PID1/signals. Test WebFlux against a real Reactor Netty server, not just `WebTestClient.bindToController(...)`.

**Verification boundary:** the integration tests in sections 8/12 close the Spring context cleanly, proving Spring lifecycle inside the JVM. They **do not replace** kubelet/preStop/SIGKILL/ingress tests in staging.

## 20. Common failures and diagnostic directions

| Symptom | Possible cause | Resolution |
|---|---|---|
| During deploy, running requests get reset | Graceful not enabled on Boot 3.3, early Pod SIGKILL, misconfigured proxy/LB drain | Check `server.shutdown`, grace period, termination logs |
| 10s shutdown phase yet Pod dies after 5s | Orchestrator grace or preStop exhausted budget | Measure timeline from Pod deletion, raise grace and shrink preStop |
| HTTP 202 returned then job lost | In-memory `@Async` task not durable | Queue/DB job record before ACK, idempotency |
| MVC Callable fails to finish after drain | Async timeout, overloaded executor, blocked task | Configure bounded executor and timeouts |
| `@Async` method does not actually run async | Self-invocation/missing `@EnableAsync` or wrong executor | Call through bean proxy, inspect thread names |
| Custom executor does not wait | Only set `spring.task.execution.shutdown.*` for auto executor | Configure custom bean directly or use dedicated lifecycle |
| Executor waits, yet DB pool already closed | Wrong teardown ordering/dependencies | SmartLifecycle/phases/bean lifetime, durable handoff |
| New jobs still arrive during shutdown | Admission gate not closed or client arrives via stale LB route | Refuse new work, readiness/endpoint propagation |
| Downstream B responds after grace | HTTP client timeout and retry budget exceed grace | Bound connect/read/overall deadlines and test failures |
| A loses response after B commits | Network/Pod termination between commit and response | Idempotency/reconciliation, no blind retries |
| WebFlux blocked during shutdown | `Thread.sleep`/blocking JDBC on Netty event loop | Use async I/O or boundedElastic with quotas |
| `Mono` calls `subscribe()` then response finishes | Task detached from request lifecycle | Return/compose Publisher or durable queue |
| WebSocket/SSE keeps pod alive forever | Infinite stream, missing max-age/drain policy | Close/reconnect, bound streams and grace |
| JVM does not receive SIGTERM | Shell wrapper is PID1 and does not forward signal | Docker exec-form ENTRYPOINT |
| IDE debugging fails to test it | IDE terminates process directly | Test JVM/container SIGTERM |
| Actuator readiness stays 200 during preStop | Spring hasn't received SIGTERM yet, still RUNNING | Endpoint routing drain / preStop admission gate |
| Metrics show few 5xx yet clients see many resets | Requests died before server observation completed | Inspect proxy/client metrics, termination events |
| Scheduled tasks canceled unexpectedly | Scheduler has its own shutdown policy | `spring.task.scheduling.shutdown.*` and durable jobs |
| Retrying HTTP POST causes double effects | Non-idempotent, ambiguous outcome | Keys + dedup/transactions/brokers |
| Jobs wait forever stalling rollout | Unbounded queue/deadline, awaitTermination too long | Bounded concurrency and stop budget |
| App does not exit even after Tomcat shuts down | Non-daemon custom ExecutorService/threads still alive | Register bean lifecycle, shutdown/awaitTermination |
| Cleanup skipped on node crash | SIGKILL/power loss bypasses hooks | Durable leases/reapers/idempotency |

## 21. Graceful shutdown design checklist

- [ ] Explicitly enabled `server.shutdown=graceful` when using Spring Boot 3.3.
- [ ] Set `spring.lifecycle.timeout-per-shutdown-phase` based on p99 request duration and total Pod budget.
- [ ] Identified which lifecycle owns synchronous requests, Servlet async, reactive calls, and background tasks.
- [ ] Avoided equating HTTP 202 with a durably saved/completed job.
- [ ] Used a bounded `TaskExecutor` with explicit admission/rejection and separate await-termination.
- [ ] For critical jobs, persisted ID/state before 202, using leases/retries/idempotency.
- [ ] Downstream calls have connect/read/total deadlines, finite retries, and idempotency.
- [ ] Avoided treating client cancellation as rolling back downstream side effects.
- [ ] MVC `Callable`/`DeferredResult` have proper async timeouts and executors.
- [ ] WebFlux returns/composes Publishers without reckless `subscribe()`/`block()`.
- [ ] Streaming SSE/WebSocket have drain, close/reconnect, and bounded memory.
- [ ] Managed DB/client pool lifecycles so they stay alive until dependent tasks finish.
- [ ] Readiness reduces traffic; verified actual LB/ingress endpoint propagation.
- [ ] Docker Java receives SIGTERM directly; avoided non-forwarding PID1 shells.
- [ ] Kubernetes `terminationGracePeriodSeconds` covers preStop + shutdown + margin.
- [ ] Avoided infinite `@PreDestroy` waits and relying on cleanup callbacks on SIGKILL.
- [ ] Logs/metrics track active requests, jobs, downstream, cancellation, shutdown duration, and rejected traffic.
- [ ] Tested real in-flight HTTP on `context.close`, and tested SIGTERM/kills in staging.
- [ ] Have a recovery plan for crashes between downstream commit and caller response.
- [ ] Have load/chaos tests for long-running requests, idle connections, and concurrent jobs.

## 22. Self-check questions

**1. Is Boot 3.3 graceful shutdown enabled by default?**  
No per Boot 3.3 docs; set `server.shutdown=graceful` explicitly. Newer versions may change the default.

**2. Does Spring Boot automatically wait for all @Async jobs after HTTP 202?**  
No. HTTP 202 has already finished; background executors need separate shutdown policies and job durability if critical.

**3. Does an MVC controller returning Callable mean the request ended immediately?**  
No. It usually transitions to Servlet async processing; the response remains open until the Callable finishes/times out/errors.

**4. Why can a downstream RestClient call cause graceful shutdown to fail?**  
Because request A is waiting on B longer than grace; improperly configured timeouts/connect/retries can let the server close before the response is sent.

**5. If B committed yet A was SIGKILLed before returning a response, is retrying safe?**  
Not necessarily. Idempotency keys, dedup, and outcome reconciliation are required; graceful does not provide exactly-once.

**6. Does `setWaitForTasksToCompleteOnShutdown(true)` replace saving jobs to a database?**  
No. It helps the executor wait during a normal shutdown, not against crashes/power loss/Kubernetes SIGKILL.

**7. In WebFlux, what is needed to keep an HTTP request attached to its downstream call?**  
Return/compose the `WebClient...bodyToMono(...)` Publisher from the handler. Do not call `subscribe()` and drop the reference.

**8. Does `Mono.timeout` guarantee the downstream server canceled the transaction?**  
No. It triggers timeout/cancel on the reactive subscriber side; downstream may have already received/committed it.

**9. When preStop sleeps 5s and Pod grace is 30s, does Java still get a full 30s?**  
No. The countdown starts **before preStop**, leaving about 25s minus other overhead.

**10. Why not assert HTTP 503 for every new request during graceful shutdown?**  
Because Tomcat/Jetty/Reactor Netty may stop accepting at the network layer, giving clients connection refused/reset; Undertow may return 503.

**11. Why might server metrics miss requests lost during SIGKILL?**  
Because observations are usually recorded when requests finish; if the JVM is killed mid-flight, only proxies/clients/already-flushed telemetry have the data.

**12. Should we wait forever for all WebSocket/SSE connections before shutting down?**  
No. Bounded grace, drain/close/reconnect policies, and durable cursors/replay are needed if business requires them.

## 23. References

1. Spring Boot **3.3 Graceful Shutdown** — four embedded servers, `server.shutdown`, `spring.lifecycle.timeout-per-shutdown-phase`, server-specific behavior: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
2. Spring Boot **3.3 Application Properties** — `spring.task.execution.shutdown.await-termination`, scheduling, MVC async request timeout: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Boot **3.3 Actuator Endpoints / Kubernetes Probes** — ApplicationAvailability, Readiness/Liveness, graceful shutdown phases: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
4. Spring Framework — **Asynchronous Requests** (`Callable`, `DeferredResult`, `WebAsyncTask`, Servlet async dispatch): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
5. Spring Framework — **Task Execution and Scheduling**, `@Async`, executor bounds and lifecycle: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
6. Spring Framework — **WebClient retrieve** and response handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
7. Spring Framework — **WebFlux Reactive Core** (publishers, cancellation, non-blocking I/O): https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
8. Kubernetes — **Pod Lifecycle / Termination Flow**, preStop, SIGTERM/SIGKILL, EndpointSlice readiness: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
9. Kubernetes — **Container Lifecycle Hooks**, preStop consumes total grace: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/

**Summary:** Spring Boot graceful shutdown gives **HTTP requests already accepted by the server** time to complete before closing the web runtime, but does not automatically guarantee all `@Async` jobs, schedulers, consumers, or downstream side effects. To stop reliably, you must simultaneously design **traffic draining**, **HTTP grace periods**, **bounded async executors**, **downstream deadlines**, **job durability/idempotency**, **resource lifetimes**, and **Kubernetes termination budgets**. Test with real running requests while the context closes, then test SIGTERM/Pod termination in your deployment environment to confirm actual conditions.
