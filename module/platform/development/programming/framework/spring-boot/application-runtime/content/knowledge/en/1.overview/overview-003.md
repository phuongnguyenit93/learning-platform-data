# Spring Boot Lifecycle Map: Startup, Readiness, Running, and Shutdown

## 1. Understand the map before learning individual events

A Spring Boot application does not jump straight from "not running" to "able to serve requests" the moment the JVM starts. It must build the configuration environment, create and refresh the `ApplicationContext`, initialize beans and web infrastructure (if present), run startup tasks, and only then announce that it is ready. When stopping, the application also needs to stop accepting new work and release the resources it has used.

Picture a restaurant: **opening the building doors** (the process is running) is not the same as **the kitchen being fully prepped** (the application is ready to receive guests). At closing time, the restaurant stops seating new guests, finishes serving orders already in progress, and only then shuts off the equipment. That mental model helps prevent confusing "the JVM is alive", "the Spring context is created", and "the application is already receiving traffic".

This lesson uses the semantics of **Spring Boot 3.3.x and Java 17+**. For applications without an HTTP server (batch, CLI, consumer), "receiving traffic" can be understood correspondingly as "ready to accept work"; the context-building and runner milestones still apply.

```text
JVM process starts
        |
        v
SpringApplication.run(...)
        |
        v
Load Environment -> build ApplicationContext -> refresh context
        |
        v
ApplicationStartedEvent -> LivenessState.CORRECT
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent -> ReadinessState.ACCEPTING_TRAFFIC
        |
        v
RUNNING: HTTP requests, jobs, scheduled tasks, message processing...
        |
        v
Shutdown requested -> ReadinessState.REFUSING_TRAFFIC
        |
        v
Close ApplicationContext -> stop infrastructure/beans -> release resources
        |
        v
Application terminates; JVM process exits according to its own lifecycle
```

This is a **mental map**, not a guarantee that every component starts or stops sequentially on a single thread. For instance, the web server may already have opened its port before `ApplicationReadyEvent`, and background tasks may continue running after that event.

## 2. Four phases from an operator's perspective

| Phase | What is happening | What operators need to know |
| --- | --- | --- |
| **Starting** | JVM runs `main`; Boot prepares `Environment`, context, beans, web server. | Having a PID or a listening port **does not prove** readiness. |
| **Ready** | Context is refreshed, startup runners complete; Boot publishes `ApplicationReadyEvent`, then switches readiness to `ACCEPTING_TRAFFIC`. | The orchestrator can begin routing traffic to the instance. |
| **Running** | Receives and processes requests/jobs, uses threads, connection pools, schedulers, caches... | Readiness can switch back to `REFUSING_TRAFFIC` while the JVM and context remain alive. |
| **Stopping/stopped** | Stops accepting new work, allows in-flight work to finish per policy, closes context, and releases resources. | Whether shutdown is graceful depends on the stop signal, configuration, and time budget. |

**Key boundaries:** "started" and "ready" are two distinct milestones; "live" and "ready" are two distinct questions; "Spring context closed" and "JVM process terminated" are not the same event either.

## 3. Deep dive into the startup phase

### 3.1. From `main` to `Environment`

`SpringApplication.run(...)` is the common entry point. `SpringApplication` publishes `ApplicationStartingEvent` very early, then prepares the `Environment` (configuration properties, profiles, environment variables, command-line arguments, etc.) and publishes `ApplicationEnvironmentPreparedEvent`.

At those points, the context and regular beans are **not yet ready**. Therefore, listeners for very early events cannot implicitly obtain beans via dependency injection. If you genuinely need to catch those events, register the listener directly on `SpringApplication` or use an early registration mechanism supported by Boot.

### 3.2. Building and refreshing the `ApplicationContext`

Boot creates the appropriate `ApplicationContext` type, loads bean definitions, applies auto-configuration, wires dependency injection, and then calls `refresh()`. During this process, non-lazy singletons are instantiated; callbacks such as `@PostConstruct` occur in **each individual bean's lifecycle**, not as a milestone that the entire application is ready.

Several useful milestones:

- `ApplicationContextInitializedEvent`: the context has been prepared and initializers have run, but bean definitions have not yet been loaded.
- `ApplicationPreparedEvent`: bean definitions have been loaded, right before refresh begins.
- `ContextRefreshedEvent`: published by Spring Framework when context refresh completes.
- `WebServerInitializedEvent`: the web server has been initialized (if it is a web application).
- `ApplicationStartedEvent`: Boot has refreshed the context, but has **not yet called** `ApplicationRunner` and `CommandLineRunner`.

Do not treat `WebServerInitializedEvent` or the log line "Tomcat started on port 8080" as a readiness test. A runner that is still loading data or validating initial state can mean the application is not yet ready to accept traffic even though the port is open.

### 3.3. Work after the context has been built

Boot invokes `ApplicationRunner` and `CommandLineRunner` beans after `ApplicationStartedEvent`. This is the appropriate place for work that must complete **before** the system announces readiness, such as preparing essential startup data. If multiple runners exist, `@Order` or `Ordered` can be used to define their relative order.

Once the runners finish, Boot publishes `ApplicationReadyEvent`. Afterward, Boot publishes `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC`. The "ready" event marks the **end of the Boot-managed startup sequence**; it does not prove that every external connection will always succeed in the future.

If a runner throws an uncaught exception, the startup process may fail: `ApplicationReadyEvent` is not reached, and Boot publishes `ApplicationFailedEvent`.

## 4. Event table by exact milestone

| Event | Meaning | Can regular beans be used yet? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Boot has just begun the run process. | No. |
| `ApplicationEnvironmentPreparedEvent` | `Environment` is prepared; context not yet created. | No. |
| `ApplicationContextInitializedEvent` | Context has been created/preliminarily initialized. | Do not assume application beans exist. |
| `ApplicationPreparedEvent` | Bean definitions loaded; about to refresh. | Do not assume beans have finished initializing. |
| `ContextRefreshedEvent` / `WebServerInitializedEvent` | Context refreshed / web server initialized. | Typically beans can be used; not necessarily ready. |
| `ApplicationStartedEvent` | Refresh complete, runners not yet executed. | Yes; still not the ready milestone. |
| `AvailabilityChangeEvent(LivenessState.CORRECT)` | Boot announces the application is live. | Yes. |
| `ApplicationReadyEvent` | Runners have finished executing. | Yes. |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | Boot announces readiness to accept traffic. | Yes. |
| `ApplicationFailedEvent` | An exception occurred causing startup to fail. | Depends on failure timing; context may not exist yet. |
| `ContextClosedEvent` | Context begins closing. | Should not initiate new work. |

The table describes the milestones of a typical `SpringApplication`. Event listeners run synchronously on the event-publishing thread by default; avoid placing long-running operations that can block startup inside a listener. With a parent/child context hierarchy, a listener may receive events from multiple contexts: distinguish which context published the event.

## 5. How is Live different from Ready?

Spring Boot uses `ApplicationAvailability` to represent two state axes:

- **Liveness**: is the application still in an internal state that allows it to operate and recover properly? `CORRECT` is normal; `BROKEN` suggests the instance needs to be restarted.
- **Readiness**: should the application receive traffic/work **right now**? `ACCEPTING_TRAFFIC` allows routing; `REFUSING_TRAFFIC` requests temporarily withholding routing.

| Situation | Liveness | Readiness | Interpretation |
| --- | --- | --- | --- |
| Starting up | `BROKEN` (initial state) | `REFUSING_TRAFFIC` | Not serving yet; HTTP probes may not even be reachable. |
| Context refreshed; runners still executing | `CORRECT` | `REFUSING_TRAFFIC` | Application is live but not yet ready. |
| Ready, operating normally | `CORRECT` | `ACCEPTING_TRAFFIC` | Can accept new work. |
| Graceful shutdown in progress | Usually still `CORRECT` | `REFUSING_TRAFFIC` | Stop accepting new work; finish remaining work. |
| Shutdown complete | No application state left to query | Gone | Context/web server has closed. |

**Why not merge the two probes?** A slow shared data store may mean an instance should not receive new requests, yet restarting every instance does not fix that data store and can even worsen cascading failures. Therefore, **do not arbitrarily include external dependencies in liveness**. If a dependency must be included in readiness, verify that it is genuinely a prerequisite for accepting traffic and check whether the application has a fallback mechanism.

When `spring-boot-starter-actuator` is added, Spring Boot can expose two health groups:

- `GET /actuator/health/liveness`
- `GET /actuator/health/readiness`

In Kubernetes, these probe groups are enabled automatically when Boot detects the environment. In other environments, enable `management.endpoint.health.probes.enabled=true`. Without Actuator or with probes disabled, do not assume those two URLs exist. The internal state inside `ApplicationAvailability` is also distinct from **being able to send a successful HTTP request**; if the web server has not opened or has already closed, the probe has no normal response to read.

You can query internal state via `ApplicationAvailability.getLivenessState()` and `getReadinessState()`. When you genuinely need to pause accepting traffic while the application keeps running, the application can publish `AvailabilityChangeEvent` with `ReadinessState.REFUSING_TRAFFIC`, and then publish `ACCEPTING_TRAFFIC` upon recovery. Changing readiness **does not automatically stop running threads, HTTP listeners, or jobs**; the orchestrator must use that signal to make routing decisions.

## 6. Shutdown phase: requesting a stop vs. killing immediately

Common stop paths include the `SIGTERM` signal in containers/Linux, intentionally closing the `ApplicationContext`, and stop actions from the deployment environment. Spring Boot normally registers a JVM shutdown hook to close the context when the JVM terminates normally. Do not treat `SIGKILL`, power loss, JVM crashes, or calls to `Runtime.halt()` as graceful shutdown: those cases can bypass cleanup callbacks.

For a Spring Boot **3.3.x** web application, explicit configuration:

```properties
# src/main/resources/application.properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

When closing the context, the embedded web server's graceful shutdown mechanism gives in-flight requests a window of time to complete and stops accepting new requests in the way supported by that server. Spring Boot 3.3.x supports Tomcat, Jetty, Reactor Netty, and Undertow; rejection behavior for new requests may vary by server (for example, Undertow returns 503). `spring.lifecycle.timeout-per-shutdown-phase` sets a time limit **per lifecycle shutdown phase**, not a guarantee that all work will finish regardless of how long it takes.

During the context closing process, the relevant milestones/mechanisms include:

1. Announcing unavailability (`ReadinessState.REFUSING_TRAFFIC`) so the routing system removes the instance from the traffic-receiving pool.
2. The context publishes `ContextClosedEvent`; beans implementing `SmartLifecycle` are asked to stop in phases (including web server graceful shutdown).
3. Spring destroys singletons, invoking corresponding cleanup callbacks such as `@PreDestroy`, `DisposableBean.destroy()`, or a declared destroy method.
4. Application resources (pools, schedulers, connection clients, etc.) are released according to their registered lifecycle. When the JVM process actually exits still depends on non-daemon threads and whatever manages it.

The steps above describe **responsibilities and logical sequence**; do not assume an absolute ordering across every listener/bean when multiple phases or custom implementations are involved.

For Kubernetes, allow enough time for unrouting and cleanup: align `terminationGracePeriodSeconds` with shutdown duration, `SmartLifecycle` phases, and the cost of completing in-flight requests. If the platform's deadline expires, the process may be forcefully terminated even while the application is performing graceful shutdown.

**You must decide your own policy for background work**: a scheduled job, Kafka consumer, or self-created thread is not automatically guaranteed to "drain" merely by enabling `server.shutdown=graceful`. Manage stopping intake of new jobs, completing/canceling in-progress jobs, and closing resources with an appropriate lifecycle mechanism. `@PreDestroy` callbacks should be fast, bounded, and safe to invoke even during an error shutdown.

## 7. Java example to observe the lifecycle

Create a Spring Boot 3.3.x, Java 17+ application with the `Spring Web` and `Spring Boot Actuator` dependencies (you can generate the project using Spring Initializr). The class below is a complete file at `src/main/java/com/example/lifecycle/RuntimeLifecycleApplication.java`, in package `com.example.lifecycle`.

```java
package com.example.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RuntimeLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeLifecycleApplication.class, args);
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("[STARTED] Context refreshed; runners not yet executed");
    }

    @Bean
    ApplicationRunner prepareApplication() {
        return args -> {
            // Illustrates only a brief initialization step; does not simulate real I/O.
            System.out.println("[RUNNER] Startup tasks completed");
        };
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("[READY] ApplicationReadyEvent");
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("[READINESS] " + event.getState());
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("[CLOSING] ContextClosedEvent");
    }

    @PreDestroy
    public void releaseResources() {
        System.out.println("[DESTROY] @PreDestroy");
    }
}
```

Add configuration for the example:

```properties
spring.application.name=lifecycle-demo
server.port=8080
management.endpoint.health.probes.enabled=true
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Run the Gradle project in a terminal (on Windows use `gradlew.bat bootRun`):

```bash
./gradlew bootRun
```

During a successful startup, the lines printed by the example itself have the following conceptual order; Spring Boot logs will be interleaved:

```text
[STARTED] Context refreshed; runners not yet executed
[RUNNER] Startup tasks completed
[READY] ApplicationReadyEvent
[READINESS] ACCEPTING_TRAFFIC
```

In another terminal, after the application is ready:

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

When both health groups are available and healthy, HTTP typically returns 200 with a body containing `"status":"UP"`. If startup is still in progress, do not deduce that HTTP 503 will always be returned: the server may not yet be ready to accept connections. When sending a stop signal handled normally by the JVM, observe the `[CLOSING]`, `[DESTROY]`, and readiness state logs; the interleaved ordering of listeners during shutdown should not be relied upon as a business contract.

**Do not use log output timing to route requests**. Use the deployment environment's readiness probe, combined with latency metrics, error rates, and background job tracking.

## 8. Three scenarios to self-test your understanding

**Scenario A — "Port 8080 is already open, but requests should not arrive yet."** An `ApplicationRunner` takes 8 seconds to load essential data. During that interval, the context has already refreshed and the web server may already exist, yet `ApplicationReadyEvent` has not appeared; the readiness state remains `REFUSING_TRAFFIC`. The orchestrator must wait for readiness rather than checking only the TCP port.

**Scenario B — "The application is still alive, but temporarily overloaded."** The JVM is still running and internal state remains valid, yet the instance needs to pause accepting traffic. This is usually a readiness problem: transition to `REFUSING_TRAFFIC`, rather than defaulting to marking liveness `BROKEN` to force a restart.

**Scenario C — "Deploying a new version; the old instance must drain."** Upon receiving a stop request, the instance must avoid new requests, allow in-flight requests to complete within the allowed budget, stop consumers/schedulers, and close resources. Enable graceful shutdown for the web server and ensure the platform grants enough time. `SIGKILL` bypasses this cleanup window.

## 9. Common misunderstandings and how to diagnose them

| Misconception / symptom | Correct understanding / what to check |
| --- | --- |
| "Seeing `Started ... in ... seconds` means it is ready." | The log can appear before runners; check `ApplicationReadyEvent` and readiness. |
| "Liveness returning UP means it can accept requests." | Reflects only one aspect of state; check readiness, web server, and real request path. |
| "Having `@PostConstruct` means the application has finished starting." | A **single bean's** callback occurring during context construction, possibly before runners and ready. |
| "Opening the HTTP port means it is safe to serve." | The server may bind before startup tasks complete. |
| "Changing readiness will close sockets." | Readiness is a signal; the orchestrator decides to stop routing. |
| "Enabling graceful shutdown ensures all background jobs finish." | Requires dedicated stop/await logic for jobs and an appropriate timeout. |
| "Any database error must mark liveness `BROKEN`." | External dependency failures usually do not mean the internal instance needs restarting; consider readiness/fallback. |
| "An `ApplicationFailedEvent` listener declared as a regular bean always catches every error." | Errors can happen before beans are created; listeners for early events must be registered early. |
| "`ContextClosedEvent` proves the JVM has exited." | It indicates the context is closing; the JVM/process may still hold other threads or resources. |

When encountering startup failures, inspect the **root exception**, the `APPLICATION FAILED TO START` log, profiles/configuration, bean creation, and port conflicts. When encountering slow shutdown, inspect in-flight requests, `SmartLifecycle`, shutdown timeouts, non-daemon threads, connection pools, consumers, and orchestrator deadlines.

## 10. Knowledge retention checklist

1. Trace the flow `SpringApplication.run -> refresh context -> ApplicationStartedEvent -> runners -> ApplicationReadyEvent -> ACCEPTING_TRAFFIC`.
2. Explain why `@PostConstruct`, an open HTTP port, and `ApplicationStartedEvent` are not yet "ready".
3. Distinguish liveness (does it need a restart?) from readiness (should it receive traffic right now?).
4. Describe the shutdown path from the shutdown signal to `ContextClosedEvent`, `SmartLifecycle`, and bean destruction; state the conditions for graceful shutdown.
5. In operations, measure startup time, monitor health probes, ensure shutdown timeouts are configured, and control background work.

## Official reference documentation (Spring Boot 3.3)

- [SpringApplication: application events, runners, and availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Actuator endpoints, Kubernetes probes, and lifecycle state table](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
