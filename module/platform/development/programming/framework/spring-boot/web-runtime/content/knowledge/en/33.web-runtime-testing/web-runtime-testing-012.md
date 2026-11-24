# Testing Startup Lifecycle, Port Conflicts, and Graceful Shutdown in Spring Boot

**Context:** Spring Boot → web-runtime → **Web runtime testing**.

A web application can return `200 OK` in a controller test yet **fail to start** on the server because the port is occupied; or start up yet report readiness prematurely, accepting traffic before loading critical data; or drop in-flight HTTP requests when deploying a new version. Therefore, web runtime testing must go beyond `@WebMvcTest`/`MockMvc`: verify **startup states and events**, **real socket binding and startup failure handling**, **closing the `ApplicationContext`**, **`SmartLifecycle`**, **graceful HTTP server draining**, **SIGTERM/container orchestration**, and the limits of automation.

This lesson uses **Java 17+, Maven, Spring Boot 3.5.16, Spring MVC + embedded Tomcat, JUnit 5**. Includes a complete compilable project, integration tests running on `RANDOM_PORT`, a test holding a `ServerSocket` to force a port conflict, an intentionally failing `ApplicationRunner` test, a shutdown test blocking an HTTP request with `CountDownLatch`, manual `SIGTERM` testing instructions with `curl`, and a CI/Kubernetes checklist. Illustrative logs/outputs are explicitly noted as **expected from code**, not measured execution results on the reader's machine.

> **Key distinctions:** `ApplicationReadyEvent` means the startup lifecycle reached the ready milestone, whereas readiness state, network acceptance, business dependencies, and load balancers determine whether clients receive useful service. `ApplicationContext.close()` tests teardown inside the JVM, **not** whether shell/Docker/Kubernetes delivered `SIGTERM` properly to Java. `MockMvc` opens no real port and is **never a reliable port-in-use test**.

**Version:** This lesson pins Spring Boot 3.5.16 for API consistency, the final release in the 3.5 line whose OSS support ends in 2026. Production must use a version or support plan receiving security patches and verify matching APIs/settings. Notably, Spring Boot 4.x alters several test starters/module packages.

## 1. Lifecycle Map of a Web Application

When running:

~~~java
SpringApplication.run(RuntimeLabApplication.class, args);
~~~

Spring Boot does more than invoke a controller constructor. It builds the `Environment`, creates the `ApplicationContext`, registers bean definitions, refreshes the context, instantiates singletons, starts `SmartLifecycle` beans, creates/starts the embedded web server, invokes `ApplicationRunner`/`CommandLineRunner`, emits `ApplicationReadyEvent`, and updates readiness state.

### 1.1. Key SpringApplication Event Order

Per Spring Boot 3.5 docs, the main order on **successful** startup:

1. `ApplicationStartingEvent`: run starts, before preparing `Environment`/context.
2. `ApplicationEnvironmentPreparedEvent`: `Environment` is ready, context not created yet.
3. `ApplicationContextInitializedEvent`: context created and initializers ran, bean definitions not loaded yet.
4. `ApplicationPreparedEvent`: bean definitions loaded, right before refresh.
5. During refresh, `ServletWebServerInitializedEvent` and `ContextRefreshedEvent` occur (exact interleaving with internal events depends on context/runtime).
6. `ApplicationStartedEvent`: context refreshed, **runners not called yet**.
7. `AvailabilityChangeEvent<LivenessState>` with `LivenessState.CORRECT`.
8. `ApplicationRunner`/`CommandLineRunner` execute in `@Order`/`Ordered` order.
9. `ApplicationReadyEvent`: runners finished successfully.
10. `AvailabilityChangeEvent<ReadinessState>` with `ReadinessState.ACCEPTING_TRAFFIC`.
11. If startup fails at any applicable stage, `ApplicationFailedEvent` is published instead of reaching ready.

~~~text
process start
  │ ApplicationStartingEvent
  ▼
prepare Environment
  │ ApplicationEnvironmentPreparedEvent
  ▼
create context
  │ ApplicationContextInitializedEvent
  │ ApplicationPreparedEvent
  ▼
refresh ApplicationContext
  ├─ create beans, @PostConstruct
  ├─ SmartLifecycle.start() (ascending phase)
  ├─ embedded web server initialized/started
  └─ ContextRefreshedEvent
  │
  ▼
ApplicationStartedEvent
  │ LivenessState.CORRECT
  ▼
ApplicationRunner / CommandLineRunner
  │ (may read cache, check config, brief warm-up)
  ▼
ApplicationReadyEvent
  │ ReadinessState.ACCEPTING_TRAFFIC
  ▼
running HTTP requests
  │
  │ SIGTERM / context.close()
  ▼
ReadinessState.REFUSING_TRAFFIC; ContextClosedEvent
  │ LifecycleProcessor.onClose() / SmartLifecycle.stop(...)
  ├─ web server graceful drain in-flight requests
  ├─ custom workers stop by phase
  └─ singleton @PreDestroy / destroy callbacks
  ▼
process exit
~~~

The diagram is **conceptual**, not enforcing exact order among every library-created listener/bean. **`ContextClosedEvent` does not mean the server finished draining**, because it is published **before** `LifecycleProcessor.onClose()`.

### 1.2. Events That Cannot Be Caught Reliably by `@EventListener` Beans

`ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`, and certain failures occur **before the `ApplicationContext` or beans exist**. Thus:

~~~java
@Component
class VeryEarlyListener {
    @EventListener
    public void onFailure(ApplicationFailedEvent event) { ... }
}
~~~

is **insufficient** to cover very early startup failures: the listener bean might not exist yet. To catch pre-context events or failures at any stage, register **directly on `SpringApplication` before `run()`**:

~~~java
SpringApplication app = new SpringApplication(RuntimeLabApplication.class);
app.addListeners(event -> {
    if (event instanceof ApplicationFailedEvent failed) {
        System.err.println("Startup failed: "
                + failed.getException().getClass().getSimpleName());
    }
});
app.run(args);
~~~

This is an **illustrative fragment**, not in the main project in section 6. Import `org.springframework.boot.SpringApplication` and `org.springframework.boot.context.event.ApplicationFailedEvent`. If a listener must always apply regardless of how startup is invoked, consider registering via `META-INF/spring.factories` under `org.springframework.context.ApplicationListener`. Avoid long blocking/network operations in event listeners on the startup thread.

### 1.3. “Successful” Startup Does Not Guarantee Business Readiness

A context may finish refreshing, bind the HTTP connector, and accept TCP connections while an `ApplicationRunner` is still preloading data. Spring Boot does not emit `ApplicationReadyEvent`/`ReadinessState.ACCEPTING_TRAFFIC` until runners complete. With Kubernetes, readiness probes prevent premature traffic routing; however, if a load balancer ignores readiness or clients connect directly, the HTTP port **may already be listening before the ready milestone**.

Do not use `@PostConstruct` for multi-minute data migrations: it runs during bean initialization, can fail before startup events/health infrastructure are ready, and complicates diagnosis. Runners suit startup tasks that must finish before ready, yet should avoid infinite loops or secret side effects; long-running jobs belong in background workers with dedicated progress/readiness policies.

## 2. Choosing the Exact Testing Layer

| Goal | Tool | Real Server/Socket? | Limitations |
|---|---|---|---|
| Controller mapping/JSON/validation | `@WebMvcTest` + `MockMvc` | **No** | Does not test port binding or Tomcat shutdown |
| Boot wiring full beans yet fake HTTP | `@SpringBootTest` (`MOCK`) + `@AutoConfigureMockMvc` | **No** | No TCP listener |
| Bootstrap, startup events, readiness, and real HTTP | `@SpringBootTest(RANDOM_PORT)`, `@LocalServerPort` | **Yes** | Test framework manages context/cache |
| Testing bind on a known occupied port | Standalone `SpringApplication.run(server.port=...)`, holding `ServerSocket` | **Yes** and intentionally fails | Must isolate port/JVM and clean up resources |
| Testing startup dependency failure | `ApplicationContextRunner` (bean config) or `SpringApplication.run` (full startup) | ContextRunner: **no**; SpringApplication: depends on web type | ContextRunner does not test embedded connectors |
| Draining an in-flight request | Isolated app context + real HTTP + `CountDownLatch` + `context.close()` | **Yes** | Does not prove OS `SIGTERM` |
| `SIGTERM`, PID 1, and graceful termination | Launch executable JAR as subprocess or manual `kill -TERM` | **Yes** | Needs Linux/container/CI signal support |
| Kubernetes rollout/readiness/preStop | Staging/ephemeral namespace + Service/Ingress | **Yes**, through infrastructure | Cannot be proven by in-JVM unit tests |
| Timeouts/long-lived connections/proxies | Real E2E/stress/protocol tests | **Yes** | Requires production-like environment |

**Quick selection rule:** If the bug depends on **OS sockets, the Servlet container, or OS signals**, `MockMvc` alone is insufficient. If checking bean ordering without networking, a `SmartLifecycle`/`ApplicationContextRunner` test is faster and more stable than booting Tomcat.

### 2.1. `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`

`@SpringBootTest` `webEnvironment` options:

- `MOCK` (default): creates `WebApplicationContext` with Servlet mocks when MVC is on classpath; **does not** open an HTTP port.
- `RANDOM_PORT`: opens a real embedded server on an OS-assigned port (port `0`), injecting the actual port via `@LocalServerPort`. Default choice for ordinary HTTP integration tests.
- `DEFINED_PORT`: uses `server.port` from config or default 8080. Prone to collisions in parallel CI; use only when specifically testing binding a fixed port.
- `NONE`: non-web application; fits testing bean configurations without a Servlet container.

**Never look for a free port by opening a socket, closing it, and booting the server** (time-of-check/time-of-use race). To avoid collisions, use `server.port=0`. When **deliberately inducing a collision**, keep the `ServerSocket` **open throughout `SpringApplication.run`**, as in section 9.

### 2.2. When Does `@WebMvcTest` Turn Green While the App Cannot Start?

For instance, controller tests pass because:
- the service was mocked via `@MockitoBean`, while production lacks a bean/config;
- controller mappings work in the mock dispatcher, yet real `server.port` is occupied by another process;
- the test loads no HTTP connector, custom servlet registrations, or graceful-shutdown lifecycle;
- `@SpringBootTest(MOCK)` never actually starts Tomcat/Jetty;
- the test bypasses `ApplicationRunner` startup paths or uses test profiles skipping startup checks;
- a bean-based `@EventListener(ApplicationFailedEvent)` only initializes after the failure already happened.

These gaps do not make `@WebMvcTest` useless. It validates the **MVC contract**, not **runtime startup**. Supplement the suite with tests at the right layers.

## 3. Verifying Startup Ordering and Readiness

### 3.1. Use an Event Recorder Instead of Random Timestamps

A robust approach uses a bean recording lifecycle milestones into a thread-safe list:
- `SmartLifecycle.start()`;
- `ApplicationStartedEvent`;
- `ApplicationReadyEvent`;
- `ContextClosedEvent`;
- `SmartLifecycle.stop(Runnable)`;
- `@PreDestroy`.

After `SpringApplication.run(...)` returns the context, inspect the event list and `ApplicationAvailability.getReadinessState()`. In a simple context, worker lifecycle start runs **before** `ApplicationStarted`/`Ready`; the close event arrives **before** worker stop, and destroy callbacks run after stop.

**Never assert exact log timestamps or full Boot log lines.** Logger formats, thread names, PIDs, GC pauses, startup optimizations, and auto-config bean counts vary by environment. Assert **partial ordering invariants** guaranteed by Spring's contracts.

### 3.2. `ApplicationStartedEvent` Differs from `ApplicationReadyEvent`

An `ApplicationRunner` failure occurs **after `ApplicationStartedEvent` yet before `ApplicationReadyEvent`**. At that point:
- The server may have already bound its port.
- Boot publishes `ApplicationFailedEvent` and closes the starting context.
- Readiness never reaches `ACCEPTING_TRAFFIC` for that run.
- Never advertise an endpoint as “ready” simply because “Tomcat started” appeared in logs.

You can write a test intentionally throwing `IllegalStateException("intentional runner failure")` inside a runner. The test should assert `SpringApplication.run` fails and a pre-context listener receives `ApplicationFailedEvent`. That verifies the app **never claims readiness** when startup checks fail.

### 3.3. Availability API and Actuator Probes

Spring Boot Actuator supports:
- `ApplicationAvailability`: reads current `LivenessState` and `ReadinessState` inside the JVM.
- `/actuator/health/liveness`, `/actuator/health/readiness` when probe groups are enabled.
- `AvailabilityChangeEvent.publish(...)`: app updates state when stopping traffic or reporting unhealthy.

Example properties:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
~~~

Readiness and liveness differ:
- **Liveness**: can the JVM still self-recover? Do not fail it merely because an external DB is temporarily down—that triggers restart storms.
- **Readiness**: should this instance receive new traffic? Can report not-ready during warm-up or draining.
- Readiness 200 **does not** replace testing feature paths like `GET /ping` or database business contracts.
- During shutdown, the HTTP connector may stop accepting connections, so probes may hit **connection refused** instead of `REFUSING_TRAFFIC` JSON; never hardcode “every shutdown probe returns 503.”

## 4. Port Already in Use: Why Real Bind Tests Are Needed

Port conflicts commonly happen when:
- another JVM/Node/nginx/process holds `0.0.0.0:8080` or `127.0.0.1:8080`;
- two replicas/dev profiles start on the same static port on one host;
- Docker host port mappings collide or Kubernetes `hostPort` conflicts;
- a prior test failed to close its context/HTTP server, leaving a listener behind;
- CI runs multiple `DEFINED_PORT` suites concurrently;
- the application tries binding a non-existent or unpermitted address, distinct from `EADDRINUSE`.

### 4.1. Identifying the Real Error

Symptoms may include:
- `Port 8080 was already in use` in Boot's failure analysis;
- `java.net.BindException: Address already in use` in nested exceptions;
- `ApplicationContextException: Unable to start web server` or a wrapped web-server exception;
- `ApplicationFailedEvent`; the application returns no usable context.

**Do not assume the root exception type/string is always identical** across Tomcat/Jetty/Undertow/Netty/OS. What matters is the behavior: **startup fails, failure listeners receive the event, no extra socket succeeds, and ready is never emitted**. A smart test holds a port, runs real `SpringApplication.run`, and asserts failure without matching full stderr text that varies by version/locale.

### 4.2. Safe and Deterministic Port Conflict Test

~~~java
try (ServerSocket occupied = new ServerSocket(
         0, 50, InetAddress.getByName("127.0.0.1"))) {
    int port = occupied.getLocalPort();
    // Socket stays OPEN throughout SpringApplication.run.
    // Spring Boot will try binding that exact 127.0.0.1:port.
}
~~~

Benefits:
- Never collides with port 8080 used by teammates/CI.
- OS assigns a random port that is genuinely held open.
- Java `try-with-resources` guarantees release after the test.
- `server.address=127.0.0.1` aligns the interface with `ServerSocket`, avoiding IPv4/IPv6 binding mismatches.
- **Never close the occupied socket before `app.run`**, or the test could pass accidentally.
- Verify `ApplicationFailedEvent` via a listener attached to `SpringApplication` before `run`; do not rely on an uncreated bean event listener.

### 4.3. Distinguishing “Bind Failed” from “Port Reachable Yet Unhealthy”

- `connection refused` when a client hits an unlistening port **does not mean** startup failed: it could be wrong address, host firewall, or LB/backend routing.
- A port conflict failure happens **when the server tries to bind** an address/port already in use.
- Two JVMs may bind different addresses on the same port number depending on OS/IPv4/IPv6/socket options; that is why the test explicitly pins `server.address`.
- Docker host port collisions happen at daemon port publishing, **possibly before the JVM even starts**; JVM bind tests do not replicate host-mapping errors identically.
- A Linux socket lingering in `TIME_WAIT` after closure is not necessarily an active listening socket; never diagnose solely from `netstat` grep.

### 4.4. Commands to Inspect Outside the App

~~~bash
# Linux:
ss -ltnp | grep ':8080'
# Or:
lsof -nP -iTCP:8080 -sTCP:LISTEN

# Windows PowerShell:
# Get-NetTCPConnection -LocalPort 8080 -State Listen
# and look up PID via Get-Process -Id <PID>
~~~

Run commands matching your OS, permissions, and namespace. Never kill an arbitrary PID just because a port is listening; identify the owner/process first. On Kubernetes inspect Service/Pod IP/`hostPort` and logs of the exact replica.

## 5. Graceful Shutdown: HTTP Behaviors to Test

Spring Boot 3.5 enables **graceful shutdown by default** across all four embedded servers: **Tomcat, Jetty, Undertow, Reactor Netty**, on both Servlet and reactive stacks. `server.shutdown=graceful` waits for in-flight requests during the stop phase while refusing new requests. `server.shutdown=immediate` disables graceful draining.

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s
~~~

**`timeout-per-shutdown-phase` is not the total process stop budget.** Each `SmartLifecycle` phase gets its own budget; add `ContextClosedEvent`, singleton destruction, JVM shutdown hooks, `preStop`, and log flushing. Multiple phases can exceed 8s total. In Kubernetes, set `terminationGracePeriodSeconds` large enough for **`preStop` + sum of critical phases + destruction + margin**.

### 5.1. How Servers Reject New Requests Differently

| Boot 3.5 Embedded Server | Documented Behavior During Graceful Drain |
| --- | --- |
| **Tomcat** | Stops accepting new requests at the network layer |
| **Jetty** | Stops accepting new requests at the network layer |
| **Reactor Netty** | Stops accepting new requests at the network layer |
| **Undertow** | May still accept connections yet return **503 Service Unavailable** |

Reverse proxies may return 502/503/504 or connection errors depending on timing/hop. Existing keep-alive/HTTP2 connections also have server-specific handling. **Do not hard-assert that new requests during shutdown always return 503**. Instead, test these invariants:
1. A request started **before** shutdown completes successfully within the grace window.
2. Context close does not finish while an in-flight request is still running within timeout.
3. Once close completes, the embedded server stops serving new requests.
4. Resources/lifecycle callbacks stop/destroy in a sensible order.

### 5.2. `SmartLifecycle` and Stop Ordering

Spring Framework manages active components via `Lifecycle` and `SmartLifecycle`:
- `start()` runs in **ascending** phase order.
- `stop(Runnable callback)` runs in **descending** phase order.
- `SmartLifecycle.isAutoStartup()` defaults to `true`.
- `SmartLifecycle.DEFAULT_PHASE` is `Integer.MAX_VALUE`.
- Plain `Lifecycle` does not auto-start like `SmartLifecycle` and is treated as phase 0.
- Bean dependencies can override phases: dependent beans start later and stop before their dependencies.
- `stop(Runnable)` **must invoke `callback.run()` once actually stopped**—never forget it or invoke it prematurely.

Embedded web server graceful shutdown runs in one of the earliest stop phases. A custom bean with a low phase (e.g., 0) normally stops **after** the web server drains, useful when worker resources are still needed by HTTP handlers. A very high-phase bean stops **before** the server; avoid shutting down a DB/HTTP client serving in-flight requests at a high phase.

### 5.3. ContextClosedEvent Arrives Before Bean Destruction

Upon `ConfigurableApplicationContext.close()`:
1. `ContextClosedEvent` is published (listeners may see requests still running on the server).
2. `LifecycleProcessor.onClose()` stops lifecycle beans/web server by phase, waiting up to the per-phase timeout for callbacks.
3. Singletons are destroyed (`@PreDestroy`/`DisposableBean.destroy`/destroy methods).
4. Context is marked closed and internal structures released.

**Never close the `DataSource` on `ContextClosedEvent`** if HTTP handlers still need the DB; that breaks the very requests being gracefully drained. Avoid sleeping inside event listeners as it delays lifecycle stop from starting.

### 5.4. Graceful Is Neither Exactly-Once Nor Immune to SIGKILL

If a POST creates an order, commits the DB transaction, and the connection drops when the pod dies, the client may retry and duplicate it. Graceful shutdown lowers request-truncation risk; it **does not guarantee exactly-once**. That problem requires `Idempotency-Key`, transaction/outbox patterns, durable queues, retry/backoff, and business reconciliation.

`SIGKILL`, JVM crashes, power loss, OOM-kills, or `Runtime.halt` bypass shutdown hooks/`@PreDestroy`. Test `SIGTERM` using `kill -TERM`, never `kill -9`, when checking graceful behavior.

## 6. Complete Spring Boot Project: Events, Ports, In-Flight Requests

The sample project builds **one executable JAR** featuring:
- `EventJournal` recording startup/close milestone order.
- A phase-0 `SmartLifecycle` bean observing start/stop callbacks.
- `ApplicationRunner` with a flag simulating startup failure.
- Fast `GET /ping`.
- `GET /hold` waiting on a **test-controlled `CountDownLatch`** when armed by the test, letting tests verify in-flight requests **without guessing sleep durations**.
- `GET /sleep?ms=7000` for manual `SIGTERM` testing with curl.
- JUnit tests creating **isolated contexts** and closing them in `finally`, leaving Spring's `TestContext` cache intact.

### 6.1. Directory Tree

~~~text
runtime-lifecycle-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/runtimelab/
    │   │   ├── RuntimeLabApplication.java
    │   │   ├── EventJournal.java
    │   │   ├── WorkerLifecycle.java
    │   │   ├── StartupCheckRunner.java
    │   │   ├── HoldGate.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/runtimelab/
            ├── RuntimeHttpTest.java
            ├── StartupFailureTest.java
            ├── PortConflictTest.java
            └── GracefulShutdownTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>runtime-lifecycle-lab</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Dependency versions are managed by Spring Boot's BOM. The demo uses embedded Tomcat from `spring-boot-starter-web`, needing no WebFlux. `spring-boot-starter-actuator` provides health probes without automatically exposing all actuator endpoints.

### 6.3. `src/main/java/com/example/runtimelab/RuntimeLabApplication.java`

~~~java
package com.example.runtimelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeLabApplication.class, args);
    }
}
~~~

`SpringApplication.run` registers a JVM shutdown hook by default. `main` **does not call `context.close()` immediately** after `run`, or the server would shut down immediately. Inside JUnit tests, we spin up controlled isolated contexts and close them explicitly.

### 6.4. `src/main/java/com/example/runtimelab/EventJournal.java`

~~~java
package com.example.runtimelab;

import jakarta.annotation.PreDestroy;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class EventJournal {
    private static final Logger log =
            LoggerFactory.getLogger(EventJournal.class);

    private final List<String> events =
            new CopyOnWriteArrayList<>();
    private final CountDownLatch closeStarted =
            new CountDownLatch(1);

    public void mark(String event) {
        events.add(event);
        log.info("LIFECYCLE {}", event);
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        mark("application-started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        mark("application-ready");
    }

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        mark("context-closed");
        closeStarted.countDown();
    }

    public boolean awaitCloseStarted(long value, TimeUnit unit)
            throws InterruptedException {
        return closeStarted.await(value, unit);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }

    @PreDestroy
    public void destroy() {
        mark("bean-destroy");
    }
}
~~~

`CopyOnWriteArrayList` lets tests safely read recorded milestones from another thread while close runs. This is an **in-RAM lab journal**, not a replacement for logging/metrics backends. `closeStarted` is a test signal indicating the context close event fired, **not** confirming web server draining completed. `@PreDestroy` records bean destruction after lifecycle stop processing.

### 6.5. `src/main/java/com/example/runtimelab/WorkerLifecycle.java`

~~~java
package com.example.runtimelab;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class WorkerLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean();
    private final EventJournal journal;

    public WorkerLifecycle(EventJournal journal) {
        this.journal = journal;
    }

    @Override
    public void start() {
        running.set(true);
        journal.mark("worker-start");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            journal.mark("worker-stop");
        } finally {
            // Spring LifecycleProcessor requires completion callback.
            callback.run();
        }
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        // Lower than the embedded web server's graceful stop phase.
        // Worker stops AFTER the server drains in Boot 3.5.
        return 0;
    }
}
~~~

Notes:
- `SmartLifecycle` auto-starts during context refresh because `isAutoStartup()` defaults to `true`.
- Phase 0 keeps the worker alive past the server's graceful stop phase rather than stopping prematurely.
- Synchronous `stop(Runnable)` in the demo invokes the callback right **after** marking state stopped.
- A production worker processing async tasks must **genuinely finish draining before calling `callback.run()`**; invoking the callback prematurely lets the context destroy beans still in use.
- Never substitute `@Order` on a bean for `getPhase`. Bean dependencies can influence order.

### 6.6. `src/main/java/com/example/runtimelab/StartupCheckRunner.java`

~~~java
package com.example.runtimelab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupCheckRunner implements ApplicationRunner {
    private final boolean fail;

    public StartupCheckRunner(
            @Value("${demo.fail-runner:false}") boolean fail) {
        this.fail = fail;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (fail) {
            throw new IllegalStateException(
                    "intentional runner failure");
        }
    }
}
~~~

This is **lab-only failure injection**. With `--demo.fail-runner=true`:
1. The context refreshed.
2. `ApplicationStartedEvent` may have already fired.
3. The runner throws.
4. `ApplicationReadyEvent` never fires.
5. `ApplicationFailedEvent` is delivered to listeners registered early enough; Boot cleans up the context.

**Never expose an unauthenticated endpoint to toggle `fail-runner` in production.** For real startup checks (certificate config, database schema), decide whether failing fast fits deployment requirements. If a downstream service is briefly unavailable, reporting not-ready and retrying may be better than a restart storm; no single choice fits every system.

### 6.7. `src/main/java/com/example/runtimelab/HoldGate.java`

~~~java
package com.example.runtimelab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class HoldGate {
    private final AtomicBoolean armed = new AtomicBoolean();
    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch released = new CountDownLatch(1);

    public void arm() {
        armed.set(true);
    }

    public boolean awaitEntered(long duration, TimeUnit unit)
            throws InterruptedException {
        return entered.await(duration, unit);
    }

    public void release() {
        released.countDown();
    }

    public void blockIfArmed() throws InterruptedException {
        if (armed.get()) {
            entered.countDown();
            if (!released.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "lab hold request timed out");
            }
        }
    }
}
~~~

`HoldGate` exists to **synchronize tests deterministically without sleep**. The test calls `arm()` before the request; the handler signals `entered` once actually inside, then waits until the test calls `release()`. The 15s cap **protects tests from hanging forever** if cleanup forgets `release()`. Production has no reason to expose such a gate, and the lab app binds localhost only.

**Do not share this gate across multiple parallel test requests**: `CountDownLatch` is one-shot per `ApplicationContext`. Each graceful test spins up its own context; multi-client tests need per-request gates and active counters rather than a global latch.

### 6.8. `src/main/java/com/example/runtimelab/ProbeController.java`

~~~java
package com.example.runtimelab;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    private final HoldGate gate;

    public ProbeController(HoldGate gate) {
        this.gate = gate;
    }

    @GetMapping(path = "/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong\n";
    }

    @GetMapping(path = "/hold",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hold() throws InterruptedException {
        gate.blockIfArmed();
        return "finished\n";
    }

    @GetMapping(path = "/sleep",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> sleep(
            @RequestParam(defaultValue = "5000") long ms)
            throws InterruptedException {
        if (ms < 0 || ms > 15000) {
            return ResponseEntity.badRequest()
                    .body("ms must be 0..15000\n");
        }
        Thread.sleep(ms);
        return ResponseEntity.ok("slept " + ms + "ms\n");
    }
}
~~~

`/ping` serves health/functional smoke checks. `/hold` is used by the automated graceful shutdown test; `/sleep` creates a 7s in-flight request for manual `SIGTERM` trials. `Thread.sleep` only simulates an in-flight request and is **not production design**. In production, slow requests stem from SQL/network/locks and need enforced timeouts and safe retry policies.

### 6.9. `src/main/resources/application.properties`

~~~properties
spring.application.name=runtime-lifecycle-lab

# Do not expose demo endpoints to external networks.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.5 already defaults to graceful; set explicitly for clarity.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health

demo.fail-runner=false
logging.level.com.example.runtimelab=INFO
~~~

Notes:
- `server.address=127.0.0.1` allows loopback access only; when containerizing, override to the Pod bind address and add security/network policies.
- `server.port=8080` is convenient for running the JAR manually. **Integration tests** override to `server.port=0` to avoid conflicts.
- `8s` is **per lifecycle shutdown phase**, not the entire JVM.
- Actuator probes can query `/actuator/health/readiness`, though during close the port may already stop accepting connections so external probes do not always get JSON back.
- Never enable Actuator's `shutdown` endpoint just for testing; if genuinely needed, it requires strict security protection.

## 7. Testing Successful HTTP Startup with RANDOM_PORT

File `src/test/java/com/example/runtimelab/RuntimeHttpTest.java`:

~~~java
package com.example.runtimelab;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RuntimeHttpTest {
    @LocalServerPort
    int port;

    @Autowired
    EventJournal journal;

    @Autowired
    ApplicationAvailability availability;

    @Test
    void realHttpServerIsReadyAfterRunners() {
        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port + "/ping")
                .retrieve()
                .body(String.class);

        assertEquals("pong\n", body);
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                     availability.getReadinessState());

        List<String> events = journal.snapshot();
        int worker = events.indexOf("worker-start");
        int started = events.indexOf("application-started");
        int ready = events.indexOf("application-ready");

        assertTrue(worker >= 0, "SmartLifecycle did not start");
        assertTrue(started > worker,
                   "ApplicationStartedEvent should follow refresh");
        assertTrue(ready > started,
                   "ReadyEvent should follow StartedEvent");
    }
}
~~~

**Value of this test:**
- Uses an OS-assigned port so it never depends on static `8080`.
- `RestClient.create()` is a **real HTTP client**, sending requests over TCP to embedded Tomcat.
- Asserting the body prevents false passes where the server listens yet routes are broken.
- Checks `ApplicationAvailability` after Spring Test's `SpringApplication.run` completes; readiness is `ACCEPTING_TRAFFIC`.
- Event recorder checks partial ordering without fragile exact timestamps.
- `@SpringBootTest` manages context startup/teardown via the test framework; **never call `context.close()` manually in this test** or you break the Spring `TestContext` cache.

If this test fails solely on `availability.getReadinessState()`, check whether custom readiness transitions were published or another context hierarchy altered the state. The lab demo never mutates readiness manually.

## 8. Testing Startup Failure in ApplicationRunner

Some startup failures occur **after the HTTP connector is created**. We want to confirm Boot publishes `ApplicationFailedEvent` and **never publishes `ApplicationReadyEvent`**.

File `src/test/java/com/example/runtimelab/StartupFailureTest.java`:

~~~java
package com.example.runtimelab;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StartupFailureTest {

    @Test
    void runnerFailureIsNotReadyAndEmitsFailedEvent() {
        SpringApplication app =
                new SpringApplication(RuntimeLabApplication.class);

        AtomicBoolean ready = new AtomicBoolean();
        AtomicReference<Throwable> failure =
                new AtomicReference<>();

        // Register BEFORE run so events arrive even when context fails.
        app.addListeners((ApplicationListener<ApplicationEvent>) event -> {
            if (event instanceof ApplicationReadyEvent) {
                ready.set(true);
            }
            if (event instanceof ApplicationFailedEvent failed) {
                failure.set(failed.getException());
            }
        });

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run(
                    "--server.port=0",
                    "--server.address=127.0.0.1",
                    "--demo.fail-runner=true",
                    "--spring.main.banner-mode=off"));

        assertNotNull(thrown);
        assertFalse(ready.get());
        assertNotNull(failure.get());
        assertTrue(containsMessage(failure.get(),
                "intentional runner failure"));
    }

    private static boolean containsMessage(
            Throwable error, String fragment) {
        for (Throwable cursor = error;
             cursor != null; cursor = cursor.getCause()) {
            if (String.valueOf(cursor.getMessage())
                    .contains(fragment)) {
                return true;
            }
        }
        return false;
    }
}
~~~

**Explanation:**
- `--server.port=0` avoids colliding with parallel tests.
- Failure injection comes from `StartupCheckRunner`, needing no real database/network.
- The failure listener is registered **outside the context**, early enough to receive `ApplicationFailedEvent` even when startup aborts.
- Asserts `ApplicationReadyEvent` never arrived because the runner threw before ready.
- `containsMessage` walks the cause chain rather than asserting an exact top-level exception type/message, since the framework may wrap it in `IllegalStateException`/`ApplicationContextException`.
- `SpringApplication` cleans up partial contexts on failure; never call `System.exit` in tests.
- If an unrelated error occurs (e.g., port conflict), the cause chain will lack `"intentional runner failure"` and the test **fails properly**, avoiding false positives where “any startup failure passes.”

**Do not** use `@SpringBootTest` for intentional context-failure tests expecting an `@Autowired` bean to receive `ApplicationFailedEvent`: Spring `TestContext` fails before entering the test method. Creating a dedicated `SpringApplication` inside the JUnit method gives direct control over the expected exception.

## 9. Testing Port Conflicts with a Held ServerSocket

File `src/test/java/com/example/runtimelab/PortConflictTest.java`:

~~~java
package com.example.runtimelab;

import java.net.InetAddress;
import java.net.ServerSocket;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PortConflictTest {

    @Test
    void occupiedLoopbackPortFailsRealServerStartup()
            throws Exception {

        // OS assigns a real IPv4 loopback port and keeps it HELD.
        try (ServerSocket occupied = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"))) {

            int busyPort = occupied.getLocalPort();
            SpringApplication app =
                    new SpringApplication(RuntimeLabApplication.class);

            AtomicReference<Throwable> failure =
                    new AtomicReference<>();

            app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                    failure.set(event.getException()));

            RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run(
                    "--server.address=127.0.0.1",
                    "--server.port=" + busyPort,
                    "--spring.main.banner-mode=off"));

            assertNotNull(thrown);
            assertNotNull(failure.get(),
                "Expected ApplicationFailedEvent");
        }
        // Only AFTER the test does try-with-resources release the occupied port.
    }
}
~~~

**Why does this test add value that MOCK lacks?**
- It attempts to start **real Tomcat** on a genuinely occupied port.
- `ApplicationFailedEvent` is captured via a listener attached before `run()`, independent of initialized context beans.
- `assertThrows(RuntimeException.class, ...)` avoids hardcoding one exact exception class; failure analyzers and nested `BindException` wrapping can differ across embedded servers.
- Never ties up static port 8080, minimizing CI interference.

**Empirical caveat:** OS socket reuse policies vary, yet holding an IPv4 loopback `ServerSocket` on the matching `server.address` works reliably across most Java environments. If the test unexpectedly binds successfully, verify Java/Tomcat share the same network namespace, IPv4 bind address, port, and socket options; never weaken the test to “just log the port,” as that defeats its purpose.

### 9.1. Errors Not to Confuse with Port Occupied

| Error | Example | Proper Test |
| --- | --- | --- |
| **EADDRINUSE** | Another process holds `127.0.0.1:8080` | Hold `ServerSocket` on same IP/port, assert startup fails |
| **EADDRNOTAVAIL** | App binds non-existent host IP | Deliberate bad `server.address` in an isolated test |
| **EACCES/permission** | OS blocks privileged port/host policy | Test in matching container/OS |
| **Docker host port collision** | Two containers publish the same host port | Docker orchestration test; fails before Java |
| **Timeout connecting downstream** | Backend port not listening | Client HTTP connection failure, not own server bind |
| **Port free yet controller fails** | Server returns 200/500 per route | `RANDOM_PORT` HTTP test |

Never run `@SpringBootTest(DEFINED_PORT)` in parallel across a large repo by default: the test suite itself will create port contention. Port conflict testing should be **one deliberate, cleanly isolated test**.

## 10. Automated Graceful Shutdown Test: Real In-Flight Request

**Test goal:** once a request enters the controller and has not finished yet, calling `context.close()` on another thread must not kill the response immediately; the server waits for the in-flight request (within the 8s timeout), and the context finishes closing afterward. A latch ensures the request **has entered the handler** before closing.

**Never** close a `@SpringBootTest(RANDOM_PORT)` context managed by Spring's `TestContext` cache, or subsequent test classes may fail randomly. The test below **omits `@SpringBootTest`**, spinning up a fresh `SpringApplication` and owning its context.

File `src/test/java/com/example/runtimelab/GracefulShutdownTest.java`:

~~~java
package com.example.runtimelab;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GracefulShutdownTest {

    @Test
    void inflightHttpRequestFinishesBeforeContextCloses()
            throws Exception {

        SpringApplication application =
                new SpringApplication(RuntimeLabApplication.class);

        ConfigurableApplicationContext context = application.run(
                "--server.port=0",
                "--server.address=127.0.0.1",
                "--server.shutdown=graceful",
                "--spring.lifecycle.timeout-per-shutdown-phase=8s",
                "--spring.main.banner-mode=off");

        ExecutorService callers =
                Executors.newSingleThreadExecutor();
        HoldGate gate = context.getBean(HoldGate.class);
        EventJournal journal = context.getBean(EventJournal.class);
        AtomicReference<Throwable> closeError =
                new AtomicReference<>();

        try {
            // Each test creates a fresh context so latches are unused.
            gate.arm();
            int port =
                ((ServletWebServerApplicationContext) context)
                    .getWebServer().getPort();

            Future<String> request = callers.submit(
                    () -> RestClient.create().get()
                        .uri("http://127.0.0.1:" + port + "/hold")
                        .retrieve().body(String.class));

            // Close ONLY AFTER the controller genuinely received the request.
            assertTrue(gate.awaitEntered(10, TimeUnit.SECONDS),
                       "HTTP handler did not enter");

            Thread closer = new Thread(() -> {
                try {
                    context.close();
                } catch (Throwable error) {
                    closeError.set(error);
                }
            }, "context-close-test");
            closer.start();

            // ContextClosedEvent occurs before web-server drain.
            assertTrue(journal.awaitCloseStarted(
                    5, TimeUnit.SECONDS));

            // While the gate holds the request, graceful close waits.
            assertFalse(request.isDone());
            assertTrue(closer.isAlive());

            // Let the request finish within the 8s grace window.
            gate.release();
            assertEquals("finished\n",
                         request.get(8, TimeUnit.SECONDS));

            closer.join(10_000L);
            assertFalse(closer.isAlive(),
                        "Context close did not finish");
            assertNull(closeError.get());

            List<String> events = journal.snapshot();
            assertTrue(events.indexOf("context-closed") >= 0);
            assertTrue(events.indexOf("worker-stop") >
                       events.indexOf("context-closed"));
            assertTrue(events.indexOf("bean-destroy") >
                       events.indexOf("worker-stop"));
        } finally {
            // Always release gate before cleanup so test failures do not hang.
            gate.release();
            context.close();
            callers.shutdownNow();
        }
    }
}
~~~

### 10.1. Why Does This Test Avoid Common Race Conditions?

An unstable test often looks like:

~~~java
CompletableFuture.runAsync(() -> callHttp("/sleep?ms=5000"));
Thread.sleep(100);
context.close();
~~~

This is a **counter-example fragment**, not standalone runnable code. After 100 ms, the HTTP request **might not have reached the controller yet** due to slow CI, DNS, thread scheduling, or Tomcat warmup. Closing before the request enters causes false “graceful failed” alarms. With `HoldGate`:
1. The test calls `arm()`.
2. The HTTP client sends the request over a real socket.
3. The controller calls `blockIfArmed()` and `entered.countDown()`.
4. The test waits on `awaitEntered(10s)`; only once the handler is actually executing does it trigger `context.close()`.
5. The test waits for `ContextClosedEvent` to confirm closing started.
6. The gate holds the request, keeping the closer thread alive and future unfinished.
7. The test calls `release()`, the request returns `200 OK`/`finished\n`, and close completes.
8. The test verifies worker stop/destroy ordering via the journal.

**This tests “draining a single request,”** not multi-client load, streaming SSE/WebSocket, or HTTP/2 multiplexing. `CountDownLatch` provides in-JVM JUnit synchronization, not distributed coordination.

### 10.2. Why Are There Multiple Timeout Values?

| Timeout | Lab Value | What It Protects |
| --- | --- | --- |
| Gate `released.await(15s)` | 15 seconds | Prevents request from hanging forever if test forgets `release` |
| Test awaiting HTTP entry | 10 seconds | Gives CI/network time for request to enter controller |
| Test awaiting close event | 5 seconds | Detects context failing to enter shutdown |
| Spring lifecycle phase | 8 seconds | Graceful HTTP in-flight drain deadline |
| HTTP future `get` | 8 seconds | Fails within bounds if request never finishes |
| Close thread `join` | 10 seconds | Prevents JUnit hanging on unfinished teardown |

These are **independent** deadlines, not summed into “56s total.” On very slow CI runners you may need wider margins, never delete timeouts. Tests should **know exactly what they verify** and log delay sources. In apps with multiple `SmartLifecycle` phases, total close time can exceed one phase timeout.

### 10.3. How to Read Expected Outcomes?

When the test succeeds, expected partial ordering relations:

~~~text
worker-start
application-started
application-ready
... HTTP /hold has entered ...
context-closed
... blocked in-flight HTTP /hold completes ...
worker-stop
bean-destroy
~~~

This is an **expected model**, not exact stdout. Spring Boot/Tomcat print many log lines in between. `ContextClosedEvent` occurs **before** phase stops; phase-0 `worker-stop` runs **after** the web-server graceful phase; `bean-destroy` follows lifecycle processing. Logs from shutdown hooks/worker threads may interleave by timing, so the test checks only the relative ordering of milestones it explicitly emitted.

### 10.4. Do Not Hard-Assert New-Request Statuses During Grace

On Tomcat, new connections may be refused, showing `ConnectException`, connection reset, or LB errors. Undertow may return 503. A test doing `assertEquals(503, GET /ping during shutdown)` fails on Tomcat even when graceful shutdown works cleanly. To test new-request rejection:
- prove new requests **do not complete normally** once draining begins;
- accept outcomes matching the contract of the server/hop under test;
- test specifically per server type with tight synchronization and deadlines;
- never mistake an incidental business 503 for proof that web server graceful shutdown worked.

## 11. Building, Running Manually, and Expected Output

Create the files per the directory tree; from `runtime-lifecycle-lab` root:

~~~bash
java -version
mvn clean test
mvn clean package
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar
~~~

**Expected test suite:**
- `RuntimeHttpTest`: real HTTP GET and startup/readiness event order.
- `StartupFailureTest`: runner failure, failure event, no ready.
- `PortConflictTest`: binding an already-held port must fail.
- `GracefulShutdownTest`: an in-flight HTTP request finishes before context closes.

Tests are designed to PASS given complete project files and environment; **never claim these commands already ran on the reader's machine**. If real failures occur, inspect startup logs and cause chains to fix code/config rather than weakening assertions to always pass.

### 11.1. Testing Real Endpoints

~~~bash
curl -i http://127.0.0.1:8080/ping
curl -i "http://127.0.0.1:8080/sleep?ms=100"
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

**Expected:**
- `GET /ping` → 200 and body `pong\n`.
- `GET /sleep?ms=100` → 200 and body `slept 100ms\n` after ~100ms (elapsed time may be longer).
- Readiness endpoint on a ready app normally reports `UP` if health groups are enabled and healthy; exact body/metadata depend on Boot/Actuator config.

If `/actuator/health/readiness` returns 404, check the Actuator starter, `management.endpoint.health.probes.enabled`, and actual management path/port. If another app returns 401/403, check its security chain; this demo omits the security starter.

### 11.2. Triggering Startup Failure from the Command Line

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=0 \
  --demo.fail-runner=true
~~~

**Expected:** logs show `application-started`, the runner throws intentionally, application startup fails without logging `application-ready`, and the process exits with a non-zero exit code per Boot launcher/exception handling. This failure occurs **after context refresh**, distinct from port conflicts during server bind.

**Does not leave a long-running process** when fail is true; the command terminates due to runner failure.

### 11.3. Triggering a Port Conflict Manually

Start the first instance:

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080
~~~

In a second terminal while the first instance stays up, launch a **second instance** on the same port and address:

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080 \
  --server.address=127.0.0.1
~~~

**Expected:** the second instance reports port in use and fails startup; the first instance continues serving `/ping`. Never perform this experiment on a shared production port; use a VM/container/localhost lab. Automated `PortConflictTest` uses an ephemeral port so it never disturbs fixed ports.

### 11.4. Testing SIGTERM with an In-Flight Request

On **Linux/macOS** in terminal 1, launch the executable JAR and note the **real JVM PID**:

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080
~~~

In terminal 2, start a slow request:

~~~bash
curl -i -v "http://127.0.0.1:8080/sleep?ms=7000"
~~~

In terminal 3, **after the request has reached the server**, locate the JVM PID and send:

~~~bash
ps -ef | grep 'runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar'
kill -TERM <JAVA_PID>
~~~

`<JAVA_PID>` is a placeholder to replace with the actual process ID—**do not copy the angle brackets literally**. Never `kill -9`. Confirm the request actually started, e.g., via request-entered logs or coordinated test instrumentation; sending `SIGTERM` too early causes a false negative.

**Expected:** upon `SIGTERM`, the JVM shutdown hook closes the context, HTTP graceful stop waits for the already-accepted request to finish within the 8s budget, and `curl` receives `200` with body `slept 7000ms`. New requests during draining may be refused/reset rather than returning one fixed status. Logs show `context-closed`, `worker-stop`, `bean-destroy` in lifecycle order.

**Important:** Sending `SIGTERM` too late misses testing in-flight drain because the HTTP request already finished; sending too early hits before the handler starts so the server rightly rejects it. That is why automated `GracefulShutdownTest` uses a gate/latch instead of sleeping.

### 11.5. Linux/CI PID Script Guidance

You can test with controlled shell commands:

~~~bash
# Terminal A:
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080 > runtime.log 2>&1 &
app_pid=$!
echo "JVM PID: $app_pid"

# Terminal B: wait until health/ping is genuinely ready.
curl -fsS http://127.0.0.1:8080/ping

# Terminal B: launch a 7-second request in the background.
curl -fsS "http://127.0.0.1:8080/sleep?ms=7000" > response.txt &
req_pid=$!

# After confirming the request entered the handler, send SIGTERM from Terminal A:
kill -TERM $app_pid

# Wait for request and process results:
wait $req_pid
wait $app_pid
~~~

These are **illustrative commands** across two terminals, **not a self-synchronizing complete CI script**. `wait` only tracks child PIDs created by that shell; across separate terminals, run `wait` in the shell owning each child. For CI, build a harness using server-side latches/logs/events to confirm the request entered the handler before `SIGTERM`, plus cleanup/`trap`/timeouts.

## 12. Comparing `context.close()` vs Subprocess SIGTERM

| Criterion | Closing Context Inside JUnit JVM | `SIGTERM` Sent to Executable JAR |
| --- | --- | --- |
| Framework teardown | **Yes**: Spring context/lifecycle | **Yes** if JVM receives signal and hooks run |
| OS signal forwarding | **No** | **Yes** |
| Web server HTTP drain | **Yes** if context starts a real server | **Yes** if graceful is enabled and budget suffices |
| PID 1/entrypoint | Not tested | Testable with container runtime |
| JVM shutdown hooks | Not all hooks necessarily run | Runs cleanly on valid JVM termination |
| Log flush/process exit | Does not test full process exit | Testable |
| K8s preStop/Pod grace | No | Only when tested in real Kubernetes |
| Test speed/determinism | Usually fast/easy to sync | Slower; requires signal handling & cleanup |
| Failure diagnostics | JUnit assertions/exceptions | Process exit code, stderr, stdout, HTTP results |

A solid suite combines:
1. **Many unit/slice tests** for business/API contracts;
2. **A few `SpringApplication`/real HTTP tests** for startup, port conflicts, and graceful close;
3. **A subprocess/Docker `SIGTERM` smoke test** in Linux CI for signal forwarding;
4. **A staging/Kubernetes rollout test** when high availability/zero dropped requests is a key SLO.

## 13. Kubernetes and Docker: Startup/Readiness/Termination Budgets

### 13.1. Probe Endpoints

Spring Boot Actuator can expose:
- `/actuator/health/liveness`;
- `/actuator/health/readiness`.

Kubernetes readiness probes route traffic only once ready. Yet remember:
- readiness flips **after** `ApplicationReadyEvent`;
- readiness only helps if Service/Ingress/load balancers respect it;
- clients hitting pod IPs directly bypass Service routing;
- Kube `EndpointSlice`/Service propagation lags slightly, so new traffic can still arrive right after shutdown begins;
- never tie external DB unavailability to **liveness** or you risk restart storms; align readiness policies with failure modes.

Example Pod/Deployment fragment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: runtime-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: runtime-lab
  template:
    metadata:
      labels:
        app: runtime-lab
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example/runtime-lab:1.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

**Not a ready-to-deploy manifest:** `image: example/runtime-lab:1.0` is a placeholder with no Dockerfile/registry supplied; build an image first. More importantly, the demo's `server.address=127.0.0.1` does not listen on the Pod IP. When containerizing, **override `--server.address=0.0.0.0`** (or equivalent env property) and add `NetworkPolicy`/TLS/auth, otherwise Kubernetes probes to the Pod IP fail even when localhost curl works.

### 13.2. Sizing Termination Grace by Budget

Assuming:
- `preStop` sleep ≈5s;
- web server graceful phase max 8s;
- custom `SmartLifecycle` phases add 5–10s;
- DB pool/metrics destruction 2s;
- at least several seconds safety margin.

`terminationGracePeriodSeconds=45` is an **illustrative** padded example, not a universal standard. Kubernetes **counts `preStop` inside the same termination grace period**, not adding extra free time on top. Once the deadline expires, kubelet sends `SIGKILL`; `@PreDestroy`/callbacks may be cut short.

**Do not equate** `spring.lifecycle.timeout-per-shutdown-phase=8s` with “Pod stops in 8s.” Phases execute sequentially and shutdown hooks/destruction take time too.

### 13.3. Docker PID 1 and Signals

Prefer exec-form container entrypoints:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Shell form `ENTRYPOINT java -jar ...` can make a shell wrapper PID 1 that fails to forward `SIGTERM` as expected. If a shell is required, use `exec java -jar ...` to replace the shell with the JVM, or use a proper init process.

`docker stop` normally sends `SIGTERM` followed by `SIGKILL` after the stop timeout; set a large enough timeout for the app. Default `docker kill` sends `SIGKILL` and does not test graceful shutdown. In Windows IDEs, the Stop button often force-kills rather than matching Linux `SIGTERM`.

## 14. Testing Startup Performance and Advanced Failure Events

### 14.1. Startup Profiling with ApplicationStartup

Spring Boot supports `ApplicationStartup`. You can configure `BufferingApplicationStartup`:

~~~java
SpringApplication app =
        new SpringApplication(RuntimeLabApplication.class);
app.setApplicationStartup(
        new BufferingApplicationStartup(2048));
app.run(args);
~~~

Imports:
- `org.springframework.boot.SpringApplication`;
- `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`.

This is an **illustrative fragment** replacing `main` during profiling, not the runnable project's `main`. Exposing the Actuator `startup` endpoint requires proper security/exposure controls, and the buffer holds a finite number of steps. Spring Framework's `FlightRecorderApplicationStartup` integrates with Java Flight Recorder for measuring allocations/class loading/GC during startup.

**Never take `Started Application in ... seconds` log timestamps as sole proof of readiness**: Boot's started log differs from `ApplicationReadyEvent` after runners. Measure time-to-ready/first successful health check if that is your SLO.

### 14.2. ApplicationContextRunner for Bean/Configuration Errors

`ApplicationContextRunner` (from `spring-boot-test`) excels at testing individual auto-configurations or missing-dependency beans without starting an HTTP server:

~~~java
new ApplicationContextRunner()
    .withBean(String.class, () -> {
        throw new IllegalStateException("missing required config");
    })
    .run(context -> {
        assertThat(context).hasFailed();
    });
~~~

This is an **illustrative fragment** needing imports:
- `org.springframework.boot.test.context.runner.ApplicationContextRunner`;
- static `org.assertj.core.api.Assertions.assertThat`.

It tests **context startup failures** yet **does not** prove socket port conflicts; testing `EADDRINUSE` requires starting a real web server like `PortConflictTest`.

### 14.3. ApplicationFailedEvent and FailureAnalyzer

Spring Boot provides `FailureAnalyzer` and `FailureAnalysisReporter` to emit `Description` / `Action` diagnostics on common startup failures (port in use, missing config...). Tests should prioritize:
- `context.run` throws;
- failure listener received the event;
- cause chain includes the injected exception when testing intentional failures;
- held port causes bind failure;
- process never reaches readiness.

**Never assert verbatim failure-analysis log text**: messages vary by OS/Boot version, log formatting, and code paths. If standardized alerts are needed, emit structured telemetry instead of regex-matching console output.

## 15. Testing Hard Scenarios

### 15.1. Requests Exceeding Shutdown Timeout

With `server.shutdown=graceful` and `timeout-per-shutdown-phase=3s`, a real HTTP request taking 7 seconds **cannot finish within the drain window**. Responses may reset, truncate, or fail on the client depending on server and proxy. Production-like tests should verify retry/idempotency policies rather than hardcoding `503`.

Manual lab test:

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

Then call `/sleep?ms=7000` and send `SIGTERM` once the request has entered. This **intentionally creates a failure window**—never configure 3s for business requests with longer SLAs.

### 15.2. SSE/WebSockets and Long-Lived Connections

An `SseEmitter`, `Flux<ServerSentEvent>`, WebSocket, or streaming download can hold connections open far longer than ordinary APIs. Waiting indefinitely “until the client closes” stalls rolling deploys, exhausts Pod grace, and triggers `SIGKILL`.

Test:
- stop accepting new streams/subscriptions once readiness begins draining;
- emit close/reconnect hints before closing if the protocol supports them;
- close/cancel streams with a bounded deadline;
- clients reconnect with backoff and `Last-Event-ID`/resume if zero data loss is required;
- resources/subscribers/queues clean up properly;
- multi-replica failover works smoothly through ingress.

`MockMvc` helps verify body/event formats yet **does not** simulate real sockets, proxy buffering, or idle timeouts; use real HTTP and staging tests.

### 15.3. Background Workers and SmartLifecycle Phases

A web server waiting for HTTP requests to drain **does not automatically know** about Kafka consumers, schedulers, batch workers, or custom threads. On stop:
1. stop accepting new work;
2. keep DB/client dependencies alive throughout the drain window;
3. stop consumers/executors by phase/dependency;
4. invoke `SmartLifecycle.stop(Runnable)`'s completion callback **only once actually stopped**;
5. close singleton resources during bean destruction.

Verify worker startup/close order via partial-order assertions like `worker-start` before `application-started`, `context-closed` before `worker-stop`, and `worker-stop` before `bean-destroy`. Among multiple beans sharing the same phase, avoid asserting strict ordering not promised by contract.

### 15.4. DB and Transactions in Shutdown Tests

If a request commits a DB transaction and the server closes the connection, the test client may miss the success response even though data persisted. Graceful draining reduces that window without providing exactly-once semantics. Use idempotency keys or transactional outboxes to handle retries.

`@Transactional` on test classes **does not automatically roll back** DB transactions executed by the HTTP server thread in `RANDOM_PORT` tests, because test and server threads have separate transaction scopes. Use explicit fixtures/test DB isolation. Never use an in-memory H2/Testcontainer in a shutdown test that tears down the DB before HTTP finishes draining.

### 15.5. Context Caching and JUnit Parallelism

`@SpringBootTest` uses Spring `TestContext` caching. Calling `context.close()` on a shared cached context causes later tests to fail unpredictably. In the examples:
- `RuntimeHttpTest` uses a Spring Test-managed context and **never** closes it.
- `GracefulShutdownTest` creates its own context via `new SpringApplication(...)` and **safely closes it**.
- `StartupFailureTest`/`PortConflictTest` also create isolated `SpringApplication` instances and fail intentionally.
- Normal tests use `server.port=0` so they can run concurrently with low collision risk.

With JUnit parallel execution, tests touching static/global state or `DEFINED_PORT` must be isolated. A test calling `System.exit`/`Runtime.halt` kills the entire test runner; **never call `System.exit`/`Runtime.halt` inside the JUnit JVM**. Test OS signals via separate subprocesses.

## 16. Symptom – Cause – Fix

| Symptom | Probable Cause | Proper Diagnosis |
| --- | --- | --- |
| MockMvc passes, production fails to bind port | `MOCK` opens no sockets | `RANDOM_PORT` and explicit `PortConflictTest` |
| Boot reports “Port already in use” | Another process holds IP/port | `ss`/`lsof`/PID; bind right address |
| `PortConflictTest` unexpectedly passes | Socket closed early or interface/namespace mismatch | Hold `ServerSocket` open on matching `127.0.0.1`/IPv4 |
| `@SpringBootTest(DEFINED_PORT)` flaky in CI | Parallel tests competing for same port | Use `RANDOM_PORT` for normal tests |
| `ApplicationStartedEvent` fires yet never ready | Runner failed/hung | Check `ApplicationRunner`, `ApplicationFailedEvent` |
| `@EventListener(ApplicationFailedEvent)` never runs | Context/bean uncreated at failure time | Register listener before `SpringApplication.run` |
| Liveness `UP` yet readiness not ready | Warm-up/runners still running | Inspect `ApplicationAvailability`/probes |
| `ApplicationReadyEvent` fires yet requests return 404 | Mapping/business differs from readiness | Real HTTP smoke request |
| `@SpringBootTest(MOCK)` misses TCP timeouts | No network involved | `RANDOM_PORT` or process/staging |
| Server shutdown cuts 7s request | `immediate` mode, 3s grace, `SIGKILL`, LB disconnect | Distinguish lifecycle vs OS/proxy; adjust/design deadlines |
| New request during drain does not return 503 | Tomcat/Netty stops accepting at network layer | Do not hard-assert 503; check server type |
| `context.close` hangs until timeout | `stop(Runnable)` forgot callback, stuck request/worker | Phase logs, thread dumps, deadlines |
| `ContextClosedEvent` logged while DB still active | Event precedes lifecycle/destroy | Expected; keep DB alive until drain finishes |
| `@PreDestroy` skipped after `kill -9` | `SIGKILL` bypasses JVM hooks | Test `SIGTERM`; add durable cleanup |
| IDE Stop fails to reproduce grace | IDE may force-terminate | Run `java -jar` and `kill -TERM` |
| Readiness probe times out during shutdown | Connector stopped accepting connections | Do not always expect JSON; inspect logs/state |
| K8s Pod killed after 30s | `terminationGracePeriodSeconds` expired | Budget `preStop` + phases + destroy |
| `GracefulShutdownTest` fails before server sees request | Arbitrary `sleep` race | Synchronize with `CountDownLatch` `entered` |
| Closing context breaks other tests in suite | Closed shared Spring `TestContext` cached context | Use isolated `SpringApplication` context |
| HTTP finished yet process fails to exit | Worker/phase/`@PreDestroy`/non-daemon thread running | Thread dump, lifecycle callbacks, executor cleanup |
| Docker container ignores `SIGTERM` | Shell wrapper/PID 1 swallows signal | Exec-form `ENTRYPOINT` or init/`exec` |
| Docker `hostPort` error while Java is healthy | Host publish collision | Docker/K8s-level test instead of JVM bind alone |
| Graceful request creates duplicate order on retry | Side effect committed yet caller lost ACK | Idempotency/outbox, not graceful alone |
| Startup failure test catches wrong error | DB/port failure instead of injected runner | Assert cause chain contains intentional marker |

## 17. Verification Runbook from Local Dev to Production

### 17.1. Before Merge

1. Run `mvn clean test`; keep unit/slice tests distinct from real-port tests.
2. Verify `@SpringBootTest(RANDOM_PORT)` hits `GET /ping` with a real client and readiness is `ACCEPTING_TRAFFIC`.
3. Test intentional runner failure: failure event captured, never ready.
4. Test held port: startup fails for the right reason without relying on fixed ports.
5. Test closing context with an in-flight request inside the controller: HTTP response completes before close finishes.
6. Verify `SmartLifecycle` worker stop callback and `@PreDestroy` ordering.
7. Ensure resources clean up in `finally` even on failed assertions; zero leaked sockets/threads.
8. Never disable security/mocks recklessly just for green builds. In real apps, add assertions for AuthN/AuthZ, DB, and retries.

### 17.2. Before Deploy

1. Build the executable JAR and container image ensuring the JVM receives `SIGTERM` cleanly.
2. Test startup in an environment matching production configs/secrets/profiles.
3. Verify readiness/liveness probes, network binding, and Service/Ingress routes.
4. Test `SIGTERM` on the JAR while handling an active request.
5. Test requests exceeding grace and confirm failure/retry contracts.
6. Measure shutdown duration per phase; never guess one total timeout.
7. Set Kubernetes `terminationGracePeriodSeconds` > `preStop` + worst-case drain + destruction + margin.
8. Test multi-replica rollouts, long-lived connections, and proxy idle timers.
9. Ensure no new jobs start after the drain gate while dependencies stay alive long enough.
10. Secure Actuator; never expose shutdown endpoints or lab endpoints publicly.

### 17.3. During Incidents

- Find the **exact last startup event**: Starting? Prepared? WebServerInitialized? Started? Ready? Failed?
- Inspect exit code, exception cause chain, and port/address/socket owner.
- If the app reached ready yet receives no traffic: inspect proxy/ingress/firewall/routing rather than blaming Spring alone.
- If `SIGTERM` produces no `ContextClosedEvent`: check PID 1/shell wrapper, OOM/crash, or hard kill.
- If the event appears yet shutdown stalls: inspect stop phases, callbacks, slow requests, and thread dumps.
- If the process exits promptly yet users see errors: inspect grace window, LB draining, new requests, TCP resets, client retry policies, and committed DB side effects.
- If CI-only failures appear: check parallel test ports, context caching, resource leaks, OS signal behavior, and CPU starvation.

## 18. Self-Check Questions

1. Does `@WebMvcTest` detect that port 8080 is already occupied? Why?
2. How does `@SpringBootTest(MOCK)` differ from `RANDOM_PORT`?
3. Why does `DEFINED_PORT` easily flake when CI runs multiple suites in parallel?
4. Which event occurs after refresh yet before `ApplicationRunner`?
5. Which event occurs after runners complete successfully?
6. Is `ReadinessState.ACCEPTING_TRAFFIC` usually published before or after `ApplicationReadyEvent`?
7. Does a bound port always mean the application is ready?
8. Why can an `@EventListener(ApplicationFailedEvent)` bean miss early startup failures?
9. How do you register a listener before `run`?
10. Why must `ApplicationFailedEvent` be tested outside Spring `TestContext` when startup is forced to fail?
11. Should a port-conflict test keep `ServerSocket` closed or open during `SpringApplication.run`?
12. Why use matching `127.0.0.1`/port in bind tests?
13. Is `PortInUseException` always the top-level exception on startup failure?
14. When should you use `ApplicationContextRunner`, and when a real web server?
15. In principle, how does `server.shutdown=graceful` differ from `immediate`?
16. With Tomcat, must new requests during shutdown return 503?
17. Is `spring.lifecycle.timeout-per-shutdown-phase` total JVM stop time or a per-phase deadline?
18. Do start and stop phases run in the same direction?
19. When must `SmartLifecycle.stop(Runnable)` invoke its callback?
20. Why does `ContextClosedEvent` not mean the database can close immediately?
21. Does `@PreDestroy` run before or after lifecycle stop?
22. Why should a `@SpringBootTest` cached context never be closed manually in a test?
23. Why should graceful tests use `CountDownLatch` instead of `Thread.sleep(100)`?
24. Does a `ctx.close()` test prove a Docker `ENTRYPOINT` forwards `SIGTERM` properly?
25. Why is `kill -9` not a graceful shutdown test?
26. Does Kubernetes `preStop` add extra time on top of `terminationGracePeriodSeconds`?
27. In the real test, what does receiving body `finished\n` before close finishes prove?
28. Why do long-lived SSE/WebSocket connections need dedicated drain/reconnect policies?
29. Does a `@Transactional` test roll back DB changes committed by a `RANDOM_PORT` server thread?
30. Does a Docker host port collision necessarily behave identically to JVM `PortConflictTest`?
31. When `ApplicationRunner` fails, can `ApplicationStartedEvent` appear without `ApplicationReadyEvent`?
32. When a request commits to the DB yet the client loses the ACK, what business solution is needed?
33. Does Liveness `UP` equate to Readiness `ACCEPTING`?
34. Once `context.close` finishes, what should be expected of the HTTP connector?
35. Does startup profiling with `BufferingApplicationStartup` replace health/readiness tests?

**Short answers:** (1) No, opens no socket. (2) Mock HTTP vs real embedded server. (3) Fixed-port contention. (4) `ApplicationStartedEvent`. (5) `ApplicationReadyEvent`. (6) After `ReadyEvent`. (7) No, runners still execute. (8) Bean does not exist yet. (9) `SpringApplication.addListeners` before `run`. (10) `TestContext` fails to finish initializing. (11) Open. (12) Same network binding. (13) No, may be nested/wrapped. (14) Bean config vs real sockets/containers. (15) Drain in-flight vs stop immediately. (16) No, may refuse at network layer. (17) Per phase. (18) No; start ascends, stop descends. (19) Only after actually stopping. (20) Draining HTTP handlers still need DB. (21) After lifecycle stop. (22) `TestContext` cache reuses it. (23) Confirms request actually entered handler. (24) No. (25) Bypasses hooks. (26) No, shares the same budget. (27) Graceful kept the in-flight request alive and context waited. (28) They outlast grace windows. (29) No, separate thread/transaction. (30) No, fails at host mapping. (31) Yes. (32) Idempotency/retries/durable state. (33) No. (34) Stops serving new requests. (35) No, it only profiles startup steps.

## 19. Official Documentation

- **Spring Boot 3.5 — SpringApplication**, event order, Liveness/Readiness, `ApplicationStartup`/`BufferingApplicationStartup`: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- **Spring Boot 3.5 — Testing Spring Boot Applications**, `MOCK`/`RANDOM_PORT`/`DEFINED_PORT`/`NONE`, `@LocalServerPort`, and test context: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Boot 3.5 — Graceful Shutdown**, default embedded servers, graceful phase, and server differences: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- **Spring Boot 3.5 — Actuator Endpoints**, probes/health groups/readiness: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- **Spring Boot 3.5 — Common Application Properties**, `server.shutdown`, `spring.lifecycle.timeout-per-shutdown-phase`, `management.endpoint.health.probes.enabled`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- **Spring Boot 3.5 — ApplicationContextRunner/Test Utilities**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Framework 6.2 — SmartLifecycle and bean lifecycle**, `getPhase`/stop callback/bean destruction: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- **Spring Framework 6.2 — MockMvc vs end-to-end tests**: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/vs-end-to-end-integration-tests.html
- **Kubernetes — Pod Termination and preStop**: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
- **Spring Boot 3.5.16 release**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/