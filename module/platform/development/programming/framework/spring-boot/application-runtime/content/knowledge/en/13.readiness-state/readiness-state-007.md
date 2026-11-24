# Relationship Between Runners and the Readiness Milestone in Spring Boot

## 1. The Problem: "Application Running" Does Not Equal "Ready to Accept Work"

When a Spring Boot application starts, there are at least three milestones to distinguish:

1. **ApplicationContext refreshed**: foundational components, regular beans, and web infrastructure may already be built. Spring Boot publishes **ApplicationStartedEvent**.
2. **Mandatory startup work completed**: SpringApplication invokes **ApplicationRunner** and **CommandLineRunner** beans. Runners can warm up caches, verify data, initialize required state, and reject startup if conditions are unmet.
3. **Application ready to serve**: once runners complete normally, Spring Boot fires **ApplicationReadyEvent**, then publishes **ReadinessState.ACCEPTING_TRAFFIC**.

This is why Spring Boot documentation describes runners as a mechanism for work executed after the context starts yet **before the application begins receiving traffic** under the readiness contract.

However, we must state this accurately: **readiness is a state/capability announced to orchestrators**, not a JVM lock that automatically blocks every request, message, scheduler, or thread. The web server may already bind its port before runners finish; components that do not coordinate with readiness can still process work early. Therefore, you must distinguish **when Boot declares ready** from **the actual mechanisms that gate or allow each work source**.

Lesson objectives:

- Understand where runners sit in the event sequence and **ApplicationAvailability** states.
- Use runners as a **startup barrier** for conditions mandatory before ready.
- Distinguish **liveness**, **readiness**, **HTTP probes**, and **actual ability to process work**.
- Recognize cases where **async tasks**, **listener containers**, **schedulers**, or direct calls break the expectation "not ready means no work yet".
- Design error handling, timeouts, runner ordering, readiness probes, and proper tests.
- Practice with Java 17+, Spring Boot 3.x, web endpoints, Actuator, and the startup failure branch.

## 2. Exact Lifecycle: Runners Sit Between Started and Ready

During a successful **SpringApplication.run(args)**, the main milestone sequence is:

| Order | Spring Boot Milestone | What Has Happened / Is Happening |
| --- | --- | --- |
| 1 | Prepare Environment and ApplicationContext | Read configuration, prepare application sources |
| 2 | Refresh ApplicationContext | Instantiate non-lazy beans, initialize infrastructure and appropriate web server |
| 3 | **ApplicationStartedEvent** | Context refreshed successfully; runners have not been called by SpringApplication yet |
| 4 | **AvailabilityChangeEvent(LivenessState.CORRECT)** | Spring Boot publishes that the application is in a live state |
| 5 | **ApplicationRunner/CommandLineRunner** | Startup tasks execute in their applicable order |
| 6 | **ApplicationReadyEvent** | All runners returned normally; successful startup branch advances to ready |
| 7 | **AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)** | Spring Boot announces the instance is ready to accept traffic |
| 8 | SpringApplication.run(...) returns | Caller receives context; typical web applications continue running |

Concise diagram:

~~~text
SPRINGAPPLICATION.RUN
         |
    Create/Refresh
    ApplicationContext
         |
   ApplicationStartedEvent
         |
    LivenessState.CORRECT
         |
         v
   +------------------------+
   | ApplicationRunner      |
   | CommandLineRunner      |  <- Startup barrier
   | (may throw exception)  |
   +------------------------+
         |
         | All runners returned successfully
         v
   ApplicationReadyEvent
         |
   ReadinessState.ACCEPTING_TRAFFIC
         |
   SpringApplication.run returns
~~~

**The keyword is "returned successfully".** Spring Boot does not check whether a Future completed or a background thread finished warming up if a runner merely spawns an async task and returns immediately. A runner is a **synchronous barrier scoped to the run(...) method**; it only guards work that the method actually waits for or verifies.

**Started differs from Ready:** seeing `ApplicationStartedEvent`, the `"Started ..."` log, an open TCP port, or a passing liveness health check **does not mean startup runners have finished**.

## 3. Liveness and Readiness Reflect Two Different Questions

**LivenessState** roughly answers: is the process still in a healthy enough internal state to keep operating or self-recover? Spring Boot typically publishes **LivenessState.CORRECT** after context refresh.

**ReadinessState** answers: can the instance accept traffic/work under the readiness contract yet? While runners execute, the default state is still **ReadinessState.REFUSING_TRAFFIC**. Once startup succeeds past the runners, Boot publishes **ReadinessState.ACCEPTING_TRAFFIC**.

| Phase | Liveness | Readiness | Operational Meaning |
| --- | --- | --- | --- |
| Early bootstrap | Not yet live / BROKEN in app lifecycle | REFUSING_TRAFFIC | Context incomplete; HTTP probes may be unreachable |
| Refresh done, runners executing | CORRECT | REFUSING_TRAFFIC | JVM/context running; startup conditions incomplete |
| After runners and Ready | CORRECT | ACCEPTING_TRAFFIC | Instance declares it can serve traffic |
| Application proactively throttling service | Can stay CORRECT | Can be REFUSING_TRAFFIC | Stop new traffic without needing an immediate restart |
| Graceful shutdown in progress | Often still CORRECT initially | REFUSING_TRAFFIC | Stop new traffic, finish in-flight tasks per policy |

Do not put every external system dependency into **liveness**. For example, if a shared database has an outage, marking every Pod `BROKEN` can trigger mass restart loops and worsen the incident. Depending on business requirements, consider readiness, circuit breakers, or an appropriate degradation policy.

**Nor is readiness a promise that every business operation will always succeed:** once ready, a request can still fail due to invalid input, quota exhaustion, timeouts, or a temporarily unavailable dependency. Readiness is a service-capacity routing signal, not a per-transaction guarantee.

## 4. A Runner Is a Startup Barrier, Not a "Server On-Switch"

Because the web server is created during refresh, the HTTP port can be bound **before runners finish**. Therefore:

- Direct connections to the instance may reach the web server early; whether the app serves or rejects requests depends on the web stack, readiness state, and handler code.
- Orchestrators such as Kubernetes should read the **readiness probe** to include an instance in the traffic-receiving pool only once it is ready.
- A client bypassing the load balancer, calling the Pod IP directly, or hitting an endpoint that ignores readiness can still generate work before the ready milestone.
- A Kafka/RabbitMQ consumer or scheduler may begin work on its **own lifecycle**; an HTTP readiness probe does not automatically stop them.

Thus, configuring runners is only part of the design. **You must ensure each work source respects the required startup boundary.**

For example: a service must preload a pricing rules table. A runner loads the cache and checks success. If it throws an exception, the instance never reaches ready on the success path. Readiness-driven HTTP ingress will not route to that instance. Yet if a message listener container auto-starts during context refresh, it can receive messages **before the runner finishes loading the cache**. For consumers, you must use explicit start/stop mechanics or gating.

## 5. When to Choose ApplicationRunner or CommandLineRunner?

Spring Boot provides two interfaces:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

These are **abbreviated signatures for study**, not runnable source files since packages and auxiliary declarations are omitted. Both run in **the same phase after ApplicationStartedEvent and before ApplicationReadyEvent**; they differ mainly in their arguments:

- **ApplicationRunner** receives **ApplicationArguments** to inspect **containsOption()**, **getOptionValues()**, and **getNonOptionArgs()**.
- **CommandLineRunner** receives raw `String[]` arguments.
- Both are registered as Spring beans via `@Component` or `@Bean`.
- With multiple runners, use **@Order/Ordered** to specify ordering within **the same ApplicationContext**.

**Use runners for:**

1. Cache warm-up that **must finish before the service receives traffic**.
2. Validating mandatory configuration or application data relying on multiple initialized beans.
3. Confirming readiness of critical dependencies, with timeouts and a fail-fast policy.
4. Lightweight, idempotent, properly coordinated data initialization before ready.
5. CLI/batch work invoked during startup that is meant to finish before `run` returns.

**Do not use runners to:**

- Run periodic tasks for the lifetime of the app; use a scheduler/job framework.
- Hold an infinite message-polling loop, causing `run(...)` to never return and the instance to never become ready.
- Manually manage long-lived threads or sockets without stop/shutdown; pick an appropriate lifecycle bean or consumer container.
- Replace schema migrations managed by Flyway/Liquibase.
- Execute a task **exactly once cluster-wide** merely by placing it in a runner: each replica/restart runs its own runner, requiring unique keys, transactions, idempotency, or a shared job orchestrator.

## 6. Runner Work Must Wait for Real Results

A common mistake:

~~~java
@Component
class WrongRunner implements ApplicationRunner {
    private final WarmupService service;

    WrongRunner(WarmupService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        service.startWarmupAsync();
        // Method returns immediately: startup may progress to Ready.
    }
}
~~~

This is an **illustrative snippet**; `WarmupService` and imports must be defined in real use. The runner **invoked** the method, yet does not know whether warm-up finished or failed. `SpringApplication` only sees **`run(...)` returning normally**; hence it may emit `ApplicationReadyEvent` and `ACCEPTING_TRAFFIC` while data is still unprepared.

For async tasks that genuinely must complete before readiness, wait with a bounded timeout and propagate failures to startup:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    CompletableFuture<Void> completion = service.startWarmupAsync();
    completion.get(10, TimeUnit.SECONDS);
}
~~~

This is an **illustrative snippet inside a runner**, not a standalone program. The service is assumed to return `CompletableFuture<Void>`; import **java.util.concurrent.CompletableFuture** and **TimeUnit**. **`get(...)`** applies a timeout and throws an exception if incomplete. Design task cancellation, cleanup, bounded retries, and proper root-cause exception handling. If using **@Async**, ensure an executor is configured and calls go through a Spring proxy; self-invocation inside the same bean bypasses `@Async`.

**Do not use unbounded `Thread.sleep` loops** to "wait for readiness": wait on real completion state, timeouts, and meaningful logging. The short sleep in the hands-on example below is solely to create an observation window.

## 7. Spring Boot 3.x / Java 17+ Example: Runner Driving Readiness

The following example demonstrates:

- `ApplicationStartedEvent` has occurred, yet runners have not finished.
- A runner observes **REFUSING_TRAFFIC** during warm-up.
- A work-accepting endpoint checks **ApplicationAvailability** and cache condition, rejecting with **HTTP 503** if preconditions are unmet.
- Once all runners complete, the app emits `ApplicationReadyEvent` and then **ReadinessState.ACCEPTING_TRAFFIC**.
- Actuator provides the readiness health probe as a signal for orchestrators.
- If a runner throws an exception, the app does not traverse the successful ready path.

### 7.1. Project Structure

~~~text
runner-readiness-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          ReadinessRunnerDemo.java
      resources/
        application.properties
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'runner-readiness-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
}
~~~

Requires **JDK 17+**, compatible Gradle, and dependencies downloadable from the repository or already cached. Version 3.3.13 is pinned so the example is reproducible on Spring Boot 3.3.x; for other versions, verify the matching APIs.

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=runner-readiness-demo
server.port=8080

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

**management.endpoint.health.probes.enabled=true** enables **liveness/readiness** health probe groups for local testing environments as well. On Kubernetes, Spring Boot can auto-detect and enable probes with matching config; here it is set explicitly for easy local testing.

### 7.2. Complete Java Source

Create **src/main/java/demo/ReadinessRunnerDemo.java**:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessRunnerDemo {
    public static void main(String[] args) {
        SpringApplication.run(ReadinessRunnerDemo.class, args);
        System.out.println("MAIN_AFTER_RUN");
    }
}

@Component
class StartupCache {
    private final AtomicBoolean warmed = new AtomicBoolean(false);

    void markWarmed() {
        warmed.set(true);
    }

    boolean isWarmed() {
        return warmed.get();
    }
}

@Component
class StartupEvents {

    @EventListener(ApplicationStartedEvent.class)
    public void started() {
        System.out.println("EVENT_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void ready() {
        System.out.println("EVENT_READY");
    }

    @EventListener
    public void readinessChanged(
            AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("READINESS_ACCEPTING");
        }
    }
}

@Component
@Order(10)
class WarmupRunner implements ApplicationRunner {
    private final ApplicationAvailability availability;
    private final StartupCache cache;

    WarmupRunner(ApplicationAvailability availability, StartupCache cache) {
        this.availability = availability;
        this.cache = cache;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RUNNER_WARMUP_START");
        System.out.println(
                "RUNNER_READINESS_" + availability.getReadinessState());

        if (args.containsOption("fail-warmup")) {
            throw new IllegalStateException("Demo warmup failed");
        }

        try {
            Thread.sleep(2500); // Only for observing the startup barrier.
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Warmup interrupted", exception);
        }

        cache.markWarmed();
        System.out.println("RUNNER_WARMUP_DONE");
    }
}

@Component
@Order(20)
class VerifyRunner implements CommandLineRunner {
    private final StartupCache cache;

    VerifyRunner(StartupCache cache) {
        this.cache = cache;
    }

    @Override
    public void run(String... args) {
        if (!cache.isWarmed()) {
            throw new IllegalStateException("Cache has not been warmed");
        }
        System.out.println("RUNNER_VERIFIED");
    }
}

@RestController
class WorkEndpoint {
    private final ApplicationAvailability availability;
    private final StartupCache cache;

    WorkEndpoint(ApplicationAvailability availability, StartupCache cache) {
        this.availability = availability;
        this.cache = cache;
    }

    @PostMapping("/work")
    ResponseEntity<String> acceptWork() {
        if (availability.getReadinessState()
                != ReadinessState.ACCEPTING_TRAFFIC
                || !cache.isWarmed()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("NOT_READY");
        }
        return ResponseEntity.ok("WORK_ACCEPTED");
    }
}
~~~

**Detailed explanation:**

1. **StartupCache** uses `AtomicBoolean` to illustrate an initialized condition. It does not replace business data storage or distributed readiness across multiple replicas.
2. **WarmupRunner** is invoked after `ApplicationStartedEvent`; it prints the current readiness state and simulates warm-up with `Thread.sleep(2500)`. In production code, replace this with concrete preparation logic with timeouts, error handling, and safe retryability.
3. **VerifyRunner** uses `@Order(20)` to run after `WarmupRunner` `@Order(10)`; if the cache is not marked valid, it throws an exception to reject startup.
4. **StartupEvents** listens for Started/Ready and prints **READINESS_ACCEPTING** only upon seeing an `AvailabilityChangeEvent` carrying `ReadinessState.ACCEPTING_TRAFFIC`.
5. **WorkEndpoint** checks both readiness state and cache state; **POST /work** accepts work when ready and returns **503** when not ready. The demo uses a simple endpoint for illustration; production code needs authentication, authorization, input validation, idempotency, and dedicated work management.
6. **ApplicationAvailability** is Spring Boot's internal API for accessing current state; it is not a distributed locking mechanism or durable queue.

### 7.3. Running the Project

If the project already has a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Without a wrapper, if a compatible Gradle is installed, you can use **gradle bootRun**.

During a normal run, **the order of lines printed by the example code itself** is:

~~~text
EVENT_STARTED
RUNNER_WARMUP_START
RUNNER_READINESS_REFUSING_TRAFFIC
RUNNER_WARMUP_DONE
RUNNER_VERIFIED
EVENT_READY
READINESS_ACCEPTING
MAIN_AFTER_RUN
~~~

Logs from Spring Boot, Tomcat, Actuator, and Gradle may interleave; this is **not the entire stdout**. Exact timing depends on context initialization and scheduling, yet the milestone ordering is the startup contract of the example.

**Note:** `READINESS_ACCEPTING` is printed from a synchronous listener receiving **AvailabilityChangeEvent**; it appears after `EVENT_READY` because Boot publishes readiness after `ApplicationReadyEvent`. If you change the listener config to async or publish custom availability states elsewhere, do not rely on this log line to infer when an async task finished.

### 7.4. Checking State with curl

After the application starts successfully:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i -X POST http://localhost:8080/work
~~~

With health probes enabled, the readiness endpoint in traffic-accepting state normally returns **HTTP 200**, with `"status":"UP"` in the body. The demo endpoint **POST /work** returns **HTTP 200** with body **WORK_ACCEPTED**.

During the warm-up window, if the HTTP server can already respond to requests, the readiness probe may report **HTTP 503/OUT_OF_SERVICE**, while the demo endpoint **POST /work** returns **503 NOT_READY** per code. If tested too early before the web server opens its port, you may encounter **connection refused**: an HTTP probe cannot be forced to respond before the server begins listening.

With the runner sleeping 2.5 seconds, you can test sending curl during that window from another terminal. Exact timing is not strictly identical across machines; rely on reported states and matching logs rather than depending on manual timing to "catch" an exact moment.

### 7.5. Testing the Startup Failure Branch

~~~bash
./gradlew bootRun --args="--fail-warmup"
~~~

Lines printed by the example code before the error is thrown:

~~~text
EVENT_STARTED
RUNNER_WARMUP_START
RUNNER_READINESS_REFUSING_TRAFFIC
~~~

Then the runner throws **IllegalStateException("Demo warmup failed")**. **RUNNER_WARMUP_DONE**, **RUNNER_VERIFIED**, **EVENT_READY**, **READINESS_ACCEPTING**, and **MAIN_AFTER_RUN** do not appear along the successful startup branch. Spring Boot handles the failure and closes the context as appropriate; Gradle may report the task failed and print a stack trace.

Because process startup failed, **do not expect the readiness endpoint to stay alive returning 503 forever**. The HTTP port may close when the context shuts down. Orchestrators must handle both probe signals and process/container exit.

## 8. Relationship with Actuator and Kubernetes Readiness Probes

Spring Boot Actuator can publish health groups:

- **/actuator/health/liveness**: reflects the instance's liveness state.
- **/actuator/health/readiness**: reflects the instance's readiness state.

With valid probe configuration, the default readiness group relies on **readinessState**. When `REFUSING_TRAFFIC`, the readiness indicator can be **OUT_OF_SERVICE** and the HTTP status is usually **503**; when `ACCEPTING_TRAFFIC`, status is usually **UP/200**. Actual HTTP responses depend on whether the server has opened, health group configuration, security, and HTTP status mapping.

In Kubernetes, an example `readinessProbe`:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

This is an **illustrative YAML snippet inside a container spec**, not a complete standalone runnable Deployment. Parameters must be tuned for the application, startup latency, port, Spring Security, and deployment infrastructure. If the application uses a different management port, select the proper probe path; probing a separate management port **does not automatically prove** the main application port is serving requests. Spring Boot also supports additional probe paths on the main server port when properly configured.

**The role of `readinessProbe`** is so Kubernetes **does not select an unready instance as a traffic-receiving endpoint**. This works for HTTP ingress/Service traffic routed by Kubernetes. It **does not prevent** a client from hitting the Pod IP directly, does not block self-created threads, and does not stop message listeners just because readiness is still `REFUSING_TRAFFIC`.

### Startup Probe and Liveness Probe Do Not Replace Readiness Probe

- **Startup probe** (if present) lets an application start more slowly before other liveness/readiness checks take effect on kubelet's schedule.
- **Liveness probe** decides whether to restart the container when the application can no longer self-recover.
- **Readiness probe** decides whether to include the instance in the traffic-serving pool.

If a runner must load a critical resource taking tens of seconds, consider a sensible startup probe/budget and `readinessProbe`; **do not mark liveness BROKEN just because a cache is preloading**. If the runner cannot finish due to a broken mandatory dependency, set reasonable timeouts/fail-fast so the orchestrator sees the true startup failure.

## 9. Cases Where HTTP Readiness Cannot Control Message Consumption

This is an easily missed detail in event-driven applications.

**SmartLifecycle** and many listener containers can auto-start during `ApplicationContext` refresh. For example, a consumer with **autoStartup=true** can begin polling messages before Spring Boot invokes `ApplicationRunner`s. A scheduler can also start running tasks on its own lifecycle once the scheduler portion of the context is ready. Exact timing depends on the framework and configuration.

Therefore:

~~~text
Context refresh
   |
   +-- Kafka/RabbitMQ listener container may start
   +-- Scheduler may be triggered
   |
ApplicationStartedEvent
   |
Runner preloads cache
   |
ApplicationReadyEvent
   |
ReadinessState.ACCEPTING_TRAFFIC
~~~

**An HTTP readiness probe is not a consumer-group controller.** If a consumer could receive messages before caches are ready, you need a dedicated strategy:

1. **Do not auto-start the consumer** during refresh: configure `autoStartup=false` on the appropriate container/listener.
2. Start the consumer after warm-up completes, using dedicated lifecycle APIs from a controlled coordinator component.
3. If starting on `ApplicationReadyEvent`, remember this event fires **immediately before** `ACCEPTING_TRAFFIC`; if exact state synchronization is required, listen for **AvailabilityChangeEvent<ReadinessState>** or use a gate backed by `ApplicationAvailability`.
4. If a message has already been received before processing is possible, apply pause/resume, nack/requeue, or backpressure per broker semantics. Do not simply drop received messages.
5. Set timeouts and a shutdown path; ensure startup threads are not blocked by an infinite polling loop.

Illustrative snippet for a standalone readiness gate:

~~~java
@Component
class ReadinessGate {
    private final AtomicBoolean accepting = new AtomicBoolean(false);

    @EventListener
    public void onAvailability(AvailabilityChangeEvent<ReadinessState> event) {
        accepting.set(event.getState() == ReadinessState.ACCEPTING_TRAFFIC);
    }

    public boolean canProcess() {
        return accepting.get();
    }
}
~~~

This is an **illustrative code snippet**, not standalone runnable: import `Component`, `AtomicBoolean`, `EventListener`, `AvailabilityChangeEvent`, and `ReadinessState`. In a real consumer, wire the gate into **the proper message fetch/ack/nack/pause mechanism**, rather than checking and silently dropping. If duplicating state is unnecessary, the consumer can also inject **ApplicationAvailability** to read current readiness directly.

**Key point on message processing:** "Ready for HTTP requests" and "ready to consume messages" are sometimes two different conditions. An application may intentionally expose no HTTP ingress yet still consume messages, or vice versa. In such cases, define readiness **per workstream** and control the corresponding consumers; do not rely on a single boolean if different workstreams have different initialization points.

## 10. Failures After Runners or Async Tasks Still Running

### 10.1. A Runner Finishing Does Not Mean the Whole System Finished Processing

A runner might call:

~~~java
backgroundExecutor.submit(() -> preloadBigCache());
return;
~~~

This is **Java pseudocode inside a method**, as `backgroundExecutor` and `preloadBigCache` are undeclared. When the method returns, `SpringApplication` can proceed to the next runner and `ApplicationReadyEvent`. If the background task fails later, the error does not automatically fail `SpringApplication.run(...)`, unless you wait and propagate the failure back to the startup path.

Pick one of two explicit contracts:

- **Mandatory before ready:** wait for task completion with a timeout, propagate errors, or run synchronously in the runner.
- **Allowed to finish after ready:** separate into a background task with its own health/metrics; only enable dependent features once their dependency is ready.

Never use "submitted the task" to report "completed the task".

### 10.2. Runner Succeeds While Mandatory Work Errors Were Swallowed

Bad example:

~~~java
try {
    validateCriticalDependency();
} catch (Exception error) {
    logger.warn("Startup check failed", error);
}
// run(...) returns successfully => Boot may proceed to ready
~~~

This is **pseudocode** since `validateCriticalDependency` and `logger` must be defined by the application. If this dependency is mandatory, catching and only logging lets the app declare itself ready while incapable of serving. Rethrow an exception with a proper cause, or transition explicitly to degraded mode with readiness reflecting the actual work types.

### 10.3. What Does a Failing Runner Do to the Ready Milestone?

If a runner throws an exception before returning:

- **ApplicationReadyEvent** is not fired on the successful startup path.
- **ReadinessState.ACCEPTING_TRAFFIC** is not published by Spring Boot along that success path.
- **ApplicationFailedEvent** is typically fired during `SpringApplication`'s failure handling.
- The created `ApplicationContext` may be closed; container-scoped bean destroy callbacks run per lifecycle rules.
- Side effects outside transactions (sending emails, writing files, HTTP APIs) **are not automatically rolled back** when the context closes.

Because orchestration may restart the instance after a failure, runners must be safe to **invoke again**. For data writes or message sends, ensure idempotency keys, transaction boundaries, and reconciliation.

## 11. Ordering Multiple Runners and Impact on Readiness

Spring Boot permits multiple runners in the same `ApplicationContext`. If tasks have dependencies, use **@Order/Ordered** to express order:

~~~java
@Component
@Order(10)
class LoadCacheRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Load cache.
    }
}

@Component
@Order(20)
class VerifyCacheRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Verify cache.
    }
}
~~~

This is **illustrative code**, requiring Spring Boot/Spring imports and real logic. If two runners share the same order, do not rely on classpath scanning order or class names as a business contract.

Along the success path:

~~~text
ApplicationStartedEvent
      |
LoadCacheRunner  (order 10)
      |
VerifyCacheRunner (order 20)
      |
ApplicationReadyEvent
      |
ReadinessState.ACCEPTING_TRAFFIC
~~~

If `VerifyCacheRunner` throws an exception, ready is not reached. If `LoadCacheRunner` spawns async work and returns, `VerifyCacheRunner` may still run before the cache finishes. **@Order controls the order of `run(...)` invocations, not a barrier for all background tasks.**

If many steps are tightly coupled, a single runner coordinating services in explicit order is easier to maintain than a long chain of hard-to-trace order-dependent runners.

## 12. Why @PostConstruct and ApplicationStartedEvent Do Not Replace Runners

**@PostConstruct** is an initialization callback of **a single bean**. It typically runs while the context is refreshing, when other beans may not yet be fully initialized. Heavy work in `@PostConstruct` can slow bean creation or cause circular dependencies. It fits local config validation and small per-bean state initialization.

**ApplicationStartedEvent** occurs after refresh and before runners, fitting logging/metrics or lightweight work needing to know the context refreshed. Listeners run **synchronously on the publisher thread** by default, so a long Started listener delays runners and readiness. Do not use it to execute full warm-up when the goal is a clearly coordinated mandatory startup step.

**ApplicationReadyEvent** occurs after runners and before `ACCEPTING_TRAFFIC`. A long synchronous Ready listener can delay the readiness transition. If a Ready listener is marked `@Async`, Boot may publish `ACCEPTING_TRAFFIC` **before the async listener actually finishes**, violating reader expectations if that work is mandatory.

| Hook | Main Milestone | Good For | Risk When Misused |
| --- | --- | --- | --- |
| `@PostConstruct`/initMethod | When bean initializes | Local invariants | Unfinished sibling beans, slow initialization |
| `ApplicationStartedEvent` | After refresh, before runners | Logs, traces, lightweight metrics | Long listener blocks startup; async listener acts as no barrier |
| `ApplicationRunner`/`CommandLineRunner` | After Started, before Ready | Mandatory startup tasks | Long runtime, unpropagated errors, async returning early |
| `ApplicationReadyEvent` | After runners, before readiness publication | Startup completion signal, telemetry | Heavy work delays/lags behind readiness |
| `SmartLifecycle` | Bean lifecycle start/stop | Consumers, long-running background services | Can begin accepting work before runners finish |
| `@Scheduled` | On schedule once scheduler is active | Periodic jobs | Must not assume scheduler waits for runners |

## 13. Self-Managing Readiness After Successful Startup

Readiness does not have to change only once. After the app is ready, if a critical component can no longer take work or becomes overloaded, the application can proactively publish **ReadinessState.REFUSING_TRAFFIC**.

Spring Boot supports **AvailabilityChangeEvent.publish(...)**:

~~~java
AvailabilityChangeEvent.publish(
        applicationEventPublisher,
        this,
        ReadinessState.REFUSING_TRAFFIC);
~~~

This is an **illustrative snippet inside a Spring bean** with `ApplicationEventPublisher` injected. Once recovered and the app is genuinely ready, it can publish **ACCEPTING_TRAFFIC** per policy. Ensure the state machine is transparent and does not flip back to ready on a single overly optimistic check.

**Consider these points:**

- Refusing traffic is a signal to orchestrators; **it does not cancel in-flight requests** and does not pause Kafka/RabbitMQ listeners automatically.
- If only one feature is unavailable, refusing all traffic may be undesirable. Define feature contracts and degraded mode.
- For shared external dependency outages, every Pod can become unready. This prevents bad serving yet can cause total service outage; establish fallback and recovery policies.
- During shutdown, Spring Boot may switch readiness to `REFUSING_TRAFFIC` to stop receiving new traffic; graceful shutdown still needs explicit configuration where appropriate.
- Do not use liveness to restart containers en masse just because an external dependency drops temporarily.

## 14. Readiness Probes Do Not Necessarily Include Every Dependency

When the Actuator readiness probe is enabled, default status reflects serving capability via Spring Boot's **readinessState**. Do not assume it checks databases, brokers, remote APIs, or business cache quality.

If a dependency is **mandatory for accepting traffic**, you can:

1. Check it in a runner before `SpringApplication` is ready, with a bounded timeout.
2. Build a health indicator for the appropriate readiness group and define when to return `OUT_OF_SERVICE`.
3. Proactively publish `ReadinessState.REFUSING_TRAFFIC` when the application detects insufficient serving capacity.
4. Guard specific endpoints/consumers so they do not accept work beyond actual state.

Do not mechanically add every shared dependency's health check into readiness; when that dependency fails, all instances can go unready together, leaving orchestrators with zero endpoints. Base the decision on whether **the service can perform useful work in degraded mode**.

## 15. From "Ready for Traffic" to "Ready for Every Kind of Work"

Systems often have multiple entry points:

| Work Source | Automatically Respects HTTP Readiness Probe? | Proper Coordination |
| --- | --- | --- |
| HTTP via probe-configured Kubernetes Service/Ingress | Normally yes, via platform routing/endpoints | Appropriate readiness probe and timeouts |
| Direct HTTP call to instance | Not guaranteed | Gate at endpoint/middleware if needed |
| Kafka listener | Not automatically via HTTP probe | `autoStartup`, pause/resume, lifecycle API, ack control |
| RabbitMQ consumer | Not automatically via HTTP probe | Listener container lifecycle and controlled requeue/nack |
| `@Scheduled` scheduler | Not automatically | State guards, toggling scheduler, or job coordination |
| `@Async` tasks | Not automatically | Await results or manage readiness per task |
| Custom threads, external cron | Not automatically | State protocol, leases/queues, gate at ingestion point |
| `ApplicationRunner` | Is itself part of the startup barrier | Wait for mandatory work to finish, propagate errors |

Sometimes an app only needs HTTP readiness, while batch consumers have different readiness criteria. In that case, **design readiness per workstream** or separate services/jobs so operational contracts remain consistent. Do not rely on one shared boolean if different work types initialize at different times.

## 16. Timeouts, Retries, and Non-Blocking Startup Design

A runner waiting indefinitely on a dependency prevents the instance from ever reaching `ApplicationReadyEvent`. For multi-replica services, this prolongs rollouts, reduces serving capacity, and puts pressure on the dependency.

Practical designs should:

- Set **timeouts** on I/O, JDBC, HTTP, file/object storage, and every awaited `Future`.
- Use retries with **max attempts, backoff, and jitter** when errors may be transient.
- Avoid retrying forever inside a runner if platform restarts handle recovery better.
- Throw errors with accurate causes so logs/metrics pinpoint unresponsive dependencies.
- When startup tasks produce DB/broker side effects, ensure **transactions/idempotency/compensation** for safe Pod restarts.
- Measure per-runner duration with timers/traces; **`ApplicationStartedEvent.getTimeTaken()`** excludes runners, whereas time-to-ready reflects the later milestone.
- If work takes minutes and does not need to complete before each Pod serves, consider separating it into a dedicated Job/migration/workflow rather than blocking startup.
- With multiple replicas, avoid having every runner execute an uncoordinated global migration/job concurrently.

**The goal is not to make runners as short as possible by silently pushing work to the background**, but to uphold the exact contract: *ready means mandatory preconditions are satisfied*.

## 17. Real-World Diagnostic Scenarios

### Scenario A — Port 8080 Is Open, Yet App Receives No Traffic

Likely cause: the web server initialized during refresh, while a cache-preloading runner has not finished yet. Check `EVENT_STARTED` logs, runner milestones, the readiness group, and how Kubernetes selects endpoints. Do not equate "TCP port open" with "startup ready".

### Scenario B — ApplicationReadyEvent Appears, Yet Cache Is Still Empty

Check whether a runner **only submitted an async task and returned**, caught an exception without rethrowing, or whether data is only loaded in a lazy bean/consumer after ready. Fix by awaiting mandatory work inside the runner with a timeout and propagating errors.

### Scenario C — HTTP Is Ready, Yet Kafka Consumer Fails Right at Startup

The consumer container may auto-start during refresh, before runners. Configure deferred startup or a message-consumption gate, and check ack/nack/backpressure and listener container responsibilities. HTTP readiness does not enforce ordering on consumers.

### Scenario D — Runner Throws, Pod Restarts Repeatedly

Find the root exception, timeouts/dependencies, idempotency of partially executed work, `startupProbe`, and workload restart policy. Do not fix by swallowing the error and reporting ready if the precondition is truly mandatory.

### Scenario E — Readiness Endpoint Unreachable in the First Few Seconds

Not necessarily a readiness state failure. The HTTP server/Actuator may not have initialized or bound the port yet. Distinguish **connection refused**, **503 OUT_OF_SERVICE**, and **200 UP**; these signals belong to different stages.

### Scenario F — An ApplicationReadyEvent Listener Runs for 40 Seconds

Default listeners are synchronous, so it can delay event completion and the subsequent readiness state. If it is mandatory work, move it to a runner. If optional, use background tasks/queues with observability, ensuring unfinished background work does not masquerade as ready.

## 18. Verification and QA Strategy

### Lifecycle Order Testing

With section 7 code, verify:

1. `EVENT_STARTED` appears before `RUNNER_WARMUP_START`.
2. `RUNNER_READINESS_REFUSING_TRAFFIC` appears while the runner executes.
3. `RUNNER_WARMUP_DONE` and `RUNNER_VERIFIED` appear before `EVENT_READY`.
4. `READINESS_ACCEPTING` appears after `EVENT_READY`.
5. `MAIN_AFTER_RUN` appears after `SpringApplication.run(...)` returns.

Do not assert the entire stdout because framework logs and timing vary; compare only messages explicitly printed by the example.

### Startup Failure Testing

With `--fail-warmup`, verify the runner throws an exception, and `ApplicationReadyEvent` and `READINESS_ACCEPTING` do not appear on the success path; the process fails/closes the context per Spring's handling. If the runner writes data, verify transaction rollback and restart idempotency.

### HTTP Readiness Testing

- Hit **/actuator/health/readiness** after the app is ready: expect `UP`/200 if no additional failing indicator is in the group.
- If you catch the warm-up window while the server is listening, verify 503/`OUT_OF_SERVICE`; if the port is not open yet, connection refused is expected.
- Try **POST /work** before ready: the gate code returns `503 NOT_READY`.
- After ready, **POST /work** returns `200 WORK_ACCEPTED` per the demo.

### Background Consumer Testing

Trigger a message while runners are still warming up and verify the consumer does not execute business logic before dependencies are ready; without gating, this test catches bugs even when HTTP readiness works fine.

### Async Testing

Have a runner submit a `CompletableFuture` with a longer processing time; if the runner does not wait, demonstrate that `ApplicationReadyEvent` can occur before completion. Then update the runner to await `completion.get(timeout)` and verify ready only appears after completion or startup fails on timeout.

### Load and Shutdown Testing

Test rolling updates, scale-out, shutdown with in-flight requests/messages, health probes, readiness refusal, in-flight handling, retries, and resource limits. Readiness is only a signal; verify the **actual behavior of each consumer/endpoint**.

## 19. Common Misconceptions

**"ApplicationStartedEvent means ready to accept requests."** False. It arrives before runners; readiness may still be `REFUSING_TRAFFIC`.

**"Once runners finish, all background tasks are done."** False if a runner merely kicked off async work and returned.

**"Spring Boot automatically blocks all HTTP requests when not ready."** Do not assume so. Platform and endpoints must respect readiness; direct access can behave differently.

**"Readiness probe also pauses Kafka consumers automatically."** False. Consumers have separate lifecycles, polling, and acks.

**"Liveness UP means caches are warm."** No. Liveness and readiness serve different purposes.

**"@Order(1) on a runner makes it run before ApplicationStartedEvent."** False. `@Order` only orders runners relative to one another, not SpringApplication's event sequence.

**"If one runner fails, Boot still publishes ACCEPTING_TRAFFIC."** Not on the normal successful startup path. A runner failure prevents `ApplicationReadyEvent` and is handled as a startup failure.

**"A long ApplicationReadyEvent listener is always safe because the app is already ready."** The event arrives immediately before `ACCEPTING_TRAFFIC`; a long synchronous listener can delay that transition.

**"No timeouts are needed because Kubernetes will restart slow runners."** Insufficient. Startup/probe budgets, graceful shutdown, exceptions, cancellation, and load limits must be designed proactively.

**"A runner executes strictly once for the entire cluster."** False. A runner is a per-`SpringApplication`-startup hook; multiple Pods and restarts re-run it.

**"Readiness always includes every health indicator and dependency."** No. The default health group and custom indicators must be configured explicitly per contract.

**"Returning 503 when unready is the whole solution."** Insufficient for gRPC, messaging, scheduled jobs, direct callers, background threads, or un-gated HTTP paths.

## 20. Self-Check Questions

**Q1.** Does Spring Boot invoke `ApplicationRunner` before or after `ApplicationStartedEvent`?  
**A:** After `ApplicationStartedEvent` and after `LivenessState.CORRECT` in the default sequence.

**Q2.** Is `ReadinessState.ACCEPTING_TRAFFIC` published before or after runners?  
**A:** After all runners complete successfully and after `ApplicationReadyEvent`.

**Q3.** Why is liveness `CORRECT` insufficient to prove a service is ready for traffic?  
**A:** The context may have refreshed while runners are still warming up and readiness is still `REFUSING_TRAFFIC`.

**Q4.** If a runner calls `asyncService.start()` and returns immediately, does `SpringApplication` know when the task finishes?  
**A:** No. You must await/track real completion state if the task is a precondition for ready.

**Q5.** What should be used for mandatory cache preloading before traffic?  
**A:** `ApplicationRunner`/`CommandLineRunner` with timeouts, fail-fast, and result verification; not just logging "started loading".

**Q6.** Does an HTTP readiness probe automatically stop a `KafkaListener` from receiving messages?  
**A:** No. Separate listener container/lifecycle/gate configuration is needed.

**Q7.** If a runner throws an exception, does `ApplicationReadyEvent` fire on the success branch?  
**A:** No.

**Q8.** `curl` gets connection refused right as the app starts; is that a 503 readiness response?  
**A:** No. Connection refused means no server is responding at that address/port yet, unlike an HTTP 503 returned by a probe.

**Q9.** Since the web port opens before runners, can the system receive direct requests?  
**A:** Depending on the web stack and how it is accessed, yes. Orchestrators must follow readiness; critical endpoints may need explicit gates.

**Q10.** What can an `ApplicationReadyEvent` listener calling `Thread.sleep(5000)` cause?  
**A:** If running synchronously, it can delay when Spring Boot publishes `ACCEPTING_TRAFFIC`.

**Q11.** Should remote database health always be placed into liveness?  
**A:** Not mechanically; a shared dependency failure can make every instance restart simultaneously. Weigh readiness and degradation policies.

**Q12.** After ready, if a critical cache breaks, do runners re-run automatically?  
**A:** No. Runners are a startup step; runtime health, repair, readiness updates, or policy-driven restarts are needed.

**Conclusion:** **ApplicationRunner/CommandLineRunner is the execution boundary for mandatory startup work before readiness**, not a master switch controlling all work ingestion paths. Spring Boot publishes **ApplicationStartedEvent → runners → ApplicationReadyEvent → ReadinessState.ACCEPTING_TRAFFIC**. To ensure "ready means able to process work properly", wait for mandatory work to actually finish in runners, report errors honestly, configure readiness probes, and separately govern direct HTTP calls, consumers, schedulers, and async tasks per their contracts.

### References

- [Spring Boot — SpringApplication: Application Events, Runners, Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Actuator Endpoints: Kubernetes Probes and Application Lifecycle](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
- [Spring Boot 3.3 — ReadinessState API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ReadinessState.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
