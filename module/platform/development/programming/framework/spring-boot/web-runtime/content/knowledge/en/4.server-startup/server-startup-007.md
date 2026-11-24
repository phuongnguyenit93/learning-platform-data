# ApplicationRunner, CommandLineRunner, and Their Impact on Readiness Time

In a Spring Boot application, the fact that the web server has started **does not mean** the application is ready to accept business traffic. After Spring creates and refreshes the `ApplicationContext`, `ApplicationRunner` and `CommandLineRunner` beans can still run tasks before Spring Boot publishes `ReadinessState.ACCEPTING_TRAFFIC`. Therefore, a task running inside a runner can extend the time from process start until the instance is eligible to receive requests from a load balancer or Kubernetes.

This lesson focuses on **where runners sit in the server startup process**, how to use both interfaces properly, their effect on readiness, error handling, measurement, and organizing safe initialization tasks.

## 1. Learning Objectives

After this lesson, you will be able to:

- Write and run an `ApplicationRunner` or `CommandLineRunner` in Spring Boot.
- Distinguish `String... args` from `ApplicationArguments`, and understand ordering with `@Order`.
- Identify the sequence `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`.
- Explain why a "Started ..." log or an open HTTP port is not enough to prove the app is **ready**.
- Evaluate which tasks should block readiness, which should run in the background, and how to handle timeouts, errors, and retries.
- Observe the impact using Actuator readiness probes and the two metrics `application.started.time` and `application.ready.time`.
- Avoid running cluster-wide one-time tasks on **every replica**.

## 2. What Are Runners and How Do They Differ?

Spring Boot provides two functional interfaces for executing logic after the application context has been initialized:

```java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}

@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

These are **abbreviated interface signatures for learning**; when writing an application, import both existing interfaces from `org.springframework.boot` rather than redefining them.

| Criterion | `CommandLineRunner` | `ApplicationRunner` |
| --- | --- | --- |
| Input arguments | `String... args`, raw arguments | `ApplicationArguments`, already parsed by Spring Boot |
| Reading `--mode=demo` | Parse the string array manually | `getOptionValues("mode")` |
| Reading `--dry-run` flag | Search the array manually | `containsOption("dry-run")` |
| Reading non-`--` arguments | Filter manually | `getNonOptionArgs()` |
| Execution timing | After `ApplicationStartedEvent`, before `ApplicationReadyEvent` | Same as `CommandLineRunner` |
| Readiness impact | While `run` has not finished, Boot has not switched to ready | Same |
| Ordering among beans | Can use `@Order` or `Ordered` | Can use `@Order` or `Ordered` |

Example when starting the program with:

```bash
java -jar app.jar --mode=demo input.csv
```

- `CommandLineRunner` receives the array `["--mode=demo", "input.csv"]`.
- `ApplicationRunner` returns `["demo"]` from `getOptionValues("mode")` and `["input.csv"]` from `getNonOptionArgs()`.
- `containsOption("mode")` returns `true`. Check for `null`/empty lists when calling `getOptionValues` if an option might be omitted or have no value.

**Practical choice:** prefer `ApplicationRunner` when a task needs named CLI options; use `CommandLineRunner` when raw argument strings are needed or a library supplies its own parser. The two interfaces do not produce two different readiness levels.

An application can have multiple runner beans. Their execution order can be controlled via `@Order` or `Ordered`. Never rely on accidental class name ordering, bean declaration order, or assume that *all* `ApplicationRunner` beans always run before *all* `CommandLineRunner` beans.

## 3. Where Do Runners Sit in the Spring Boot Lifecycle?

### 3.1. Typical Startup Sequence

In Spring Boot 3.x, the main flow of a `SpringApplication.run(...)` call includes these key milestones:

```text
main()
  |
  +-- Prepare Environment and ApplicationContext
  |
  +-- Initialize beans, dependency injection, refresh context
  |       |
  |       +-- Embedded web server initialized / begins listening
  |       +-- ContextRefreshedEvent and WebServerInitializedEvent
  |
  +-- ApplicationStartedEvent
  |
  +-- LivenessState.CORRECT
  |
  +-- Invoke ApplicationRunner / CommandLineRunner beans in order
  |       |
  |       +-- first run(): synchronous, waits to finish
  |       +-- second run(): synchronous, waits to finish
  |       +-- ...
  |
  +-- ApplicationReadyEvent
  |
  +-- ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- SpringApplication.run(...) returns
```

This is a diagram of major milestones, not an exhaustive list of every internal Spring callback.

**Key point:** `ApplicationStartedEvent` arrives before runners, whereas `ApplicationReadyEvent` arrives after runners complete. The readiness transition to `ACCEPTING_TRAFFIC` is published **after** `ApplicationReadyEvent`. Event listeners run synchronously on the publishing thread by default, so a slow listener can also affect startup.

### 3.2. "Started", "Live", "Ready", and "Port Open" Are Four Distinct Concepts

| Milestone / Signal | Accurate Meaning | Sufficient to Accept Traffic? |
| --- | --- | --- |
| Log `Started DemoApplication in ...` | Context has started; startup logs can appear before runners finish | **Not enough** |
| Web server bound port `8080` | Socket/HTTP server is present | **Not enough** |
| `LivenessState.CORRECT` | Internal state indicates the process can run | **Not enough** |
| `ReadinessState.REFUSING_TRAFFIC` | Instance is not ready to receive traffic | **No**; infrastructure should stop routing to the instance |
| `ApplicationReadyEvent` | Runners have finished executing; Boot is completing startup | Nearly ready, but not yet the readiness-change event |
| `ReadinessState.ACCEPTING_TRAFFIC` | Spring Boot publishes the ready state | **Yes per readiness contract**, provided infrastructure actually honors this signal |

Distinguish **Spring's readiness state** from **actual HTTP blocking**. Boot publishes the state; Kubernetes, ingress, service mesh, or the load balancer must be configured to check readiness to stop sending requests to an unready instance. If a user calls the listening address and port directly, do not assume Spring automatically rejects all business endpoints solely because readiness is `REFUSING_TRAFFIC`.

### 3.3. How Does Runner Duration Affect Startup?

Suppose (illustrative timings):

- Process start to context-started: 2.0 seconds.
- `ApplicationRunner` loads a mandatory cache: 4.0 seconds.
- `CommandLineRunner` validates configuration: 0.5 seconds.
- Final startup events complete: 0.1 seconds.

Then time to `started` is around **2.0 seconds**, but time to `ready` is around **6.6 seconds**. If a service scales from 3 to 20 pods, each pod runs its own runners. A slow runner can slow down rollouts/scale-outs or cause probes to fail before initialization completes.

Measure context startup time, individual runner durations, and time to readiness separately. These sample numbers only illustrate how to reason, not Spring Boot's default performance.

## 4. Java 17+ Example: Observing Exact Runner and Readiness Order

The example below is a **Spring Boot 3.x** application using Spring MVC, Actuator, and Java 17+. Generate a project with Spring Initializr including **Spring Web** and **Spring Boot Actuator**, then place the entire file below at:

`src/main/java/demo/RunnerReadinessDemo.java`

```java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerReadinessDemo {

    public static void main(String[] args) {
        SpringApplication.run(RunnerReadinessDemo.class, args);
        System.out.println("5 SpringApplication.run returned");
    }
}

@Component
@Order(1)
class PrepareRunner implements ApplicationRunner {

    private final ApplicationAvailability availability;

    PrepareRunner(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> values = args.getOptionValues("mode");
        String mode = (values == null || values.isEmpty())
                ? "default" : values.get(0);

        System.out.println("1 ApplicationRunner: mode=" + mode
                + ", files=" + args.getNonOptionArgs()
                + ", readiness=" + availability.getReadinessState());

        if (args.containsOption("fail")) {
            throw new IllegalStateException("Required preparation failed");
        }

        // Only for observing readiness; do not use sleep in real deployments.
        TimeUnit.SECONDS.sleep(6);
    }
}

@Component
@Order(2)
class PrintArgsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("2 CommandLineRunner: raw="
                + Arrays.toString(args));
    }
}

@Component
class StartupEvents {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("3 ApplicationReadyEvent");
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("4 readiness=ACCEPTING_TRAFFIC");
        }
    }
}
```

This is a **complete single Java file**: only `RunnerReadinessDemo` is public; the remaining classes belong to the same `demo` package and are picked up by component scanning. `@Order(1)` and `@Order(2)` guarantee the order of the two runners. Event publishing and logging in this example rely on the default synchronous application event multicaster.

Configuration `src/main/resources/application.properties`:

```properties
server.port=8080

# Allow readiness/liveness probes even outside Kubernetes
management.endpoint.health.probes.enabled=true

# Expose /readyz and /livez on the main web port
management.endpoint.health.probes.add-additional-paths=true

# Only for observing metrics in a learning environment
management.endpoints.web.exposure.include=health,info,metrics
```

If the project uses the Gradle Wrapper, run from the project root:

```bash
./gradlew bootRun --args='--mode=demo input.csv'
```

On Windows PowerShell, use:

```powershell
.\gradlew.bat bootRun --args='--mode=demo input.csv'
```

Ignoring the banner and Spring's automatic log lines, **the lines printed by the sample code** will follow this order:

```text
1 ApplicationRunner: mode=demo, files=[input.csv], readiness=REFUSING_TRAFFIC
2 CommandLineRunner: raw=[--mode=demo, input.csv]
3 ApplicationReadyEvent
4 readiness=ACCEPTING_TRAFFIC
5 SpringApplication.run returned
```

Note: Tomcat and Spring logs may interleave between these lines. `TimeUnit.SECONDS.sleep(6)` is only an intentional delay to test readiness, not a real-world initialization pattern. Use Ctrl+C to stop the program.

### 4.1. Observing Readiness While the Runner Is Running

Open a second terminal as soon as Spring starts the web server while runner 1 is still waiting:

```bash
curl -i http://localhost:8080/readyz
```

When the endpoint is reachable before the runner finishes, the response typically has HTTP status **503 Service Unavailable** with health status:

```json
{"status":"OUT_OF_SERVICE"}
```

Once both runners finish and Boot switches to `ACCEPTING_TRAFFIC`, calling it again returns HTTP **200 OK**, typically with body:

```json
{"status":"UP"}
```

The example uses the default HTTP response of the Actuator health group without customizing status mappers or details. If called too early, you may get a connection error because the port is not open yet; if called too late, you will only see `UP` because the runner already finished. Neither case changes the lifecycle order.

### 4.2. Testing a Failing Runner

Run again with the `--fail` flag:

```bash
./gradlew bootRun --args='--mode=demo --fail'
```

`PrepareRunner` throws `IllegalStateException("Required preparation failed")`. Normal startup fails and does not complete readiness. The lines `2 CommandLineRunner`, `3 ApplicationReadyEvent`, `4 readiness=ACCEPTING_TRAFFIC`, and `5 SpringApplication.run returned` **do not appear** in this failed run because the exception happens in the first runner. Spring Boot publishes the failure event (`ApplicationFailedEvent`) and closes the context when startup fails.

Do not ship a failure-simulation flag in production; this example demonstrates that **a failing runner is never treated as a successful startup**.

### 4.3. When CLI Arguments Are Not Needed

For fixed tasks, you can write a runner as a concise bean:

```java
@Bean
ApplicationRunner auditOnBoot() {
    return args -> auditService.verifyConfiguration();
}
```

This is a **snippet** inside an `@Configuration` or `@SpringBootApplication` class; it assumes an `auditService` bean already exists and is not a standalone program. If this task needs transactions, timeouts, or configurable retries, place the logic in a dedicated service and have the runner simply call that service.

## 5. Should Runners Be Used to Seed Data or Check Dependencies?

The answer depends on one condition: **Without finishing this task, can the instance serve requests correctly and safely?**

| Task | Appropriate Approach | Acceptable Readiness Impact |
| --- | --- | --- |
| Validate mandatory config vars, local certs/configs | Runner or startup validation | Fail startup on error; should be very fast |
| Load small local dataset required by every request | Synchronous `ApplicationRunner` with a deadline | Not ready until loaded |
| Verify reachability of an essential dependency | Short preflight with timeout; combine with runtime health/readiness | May block readiness; avoid infinite retries |
| Warm optional cache to speed up first requests | Background execution with bounded executor or lazy-load | Do not delay ready if cold cache still serves correctly |
| Seed sample data in local/dev environments | Runner gated by specific profile/flag, idempotent | Do not run by default in production |
| Database schema migration | Prefer Flyway/Liquibase or a dedicated migration Job | Ensure ordering before data access; do not reimplement ad hoc in a runner |
| Task that must run once **cluster-wide** | Kubernetes Job, scheduler with lock/leader election | Do not run in a runner on every pod unless safe to repeat |
| Send bulk emails, full-system sync, multi-minute data imports | Separate batch/queue/background worker | Do not hold a web service unready for minutes for auxiliary work |
| Periodic jobs | `@Scheduled`/coordinated job scheduler | Use runner only to initialize scheduling if truly needed |

**Decision rule:** a step required for data correctness should finish **before** readiness; an optimization or background task can be decoupled as long as requests still behave properly while it is incomplete. Do not mark `ACCEPTING_TRAFFIC` when critical resources are not ready.

## 6. Synchronous Runners, Background Work, and Common Misconceptions

### 6.1. Synchronous Runners Block Startup Completion

By default, Spring Boot calls `run(...)` methods sequentially and waits for them to return. If the first runner takes 30 seconds, the next runner does not start during that time and `ApplicationReadyEvent` is not published yet. If the wait involves I/O to a database or HTTP server, startup duration depends on the external system's latency and availability.

Mistake:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    while (!externalSystemAvailable()) {
        Thread.sleep(1000); // Unbounded duration and retry count
    }
}
```

This is an **anti-pattern snippet**, where `externalSystemAvailable()` is an illustrative method. If the dependency never recovers, the pod can remain unready indefinitely; the orchestrator may continuously restart it based on startup/liveness probe deadlines.

Better design: enforce an **overall deadline**, per-request timeouts, bounded retry count, backoff with jitter if needed, clear error messages, and an explicit fail-fast policy when a mandatory dependency is unavailable.

### 6.2. Spawning a Future or @Async Can Flip Readiness Too Early

Consider this snippet:

```java
@Override
public void run(ApplicationArguments args) {
    CompletableFuture.runAsync(() -> warmRequiredCache());
}
```

The `run` method returns immediately after scheduling the background task. Spring Boot **does not wait** for the `CompletableFuture` to finish; it proceeds to the remaining runners and can transition to ready while the mandatory cache is still empty. The same risk occurs when using `@Async` without proper coordination. In the snippet, `warmRequiredCache()` is a hypothetical task and the code needs `import java.util.concurrent.CompletableFuture`.

If the cache is **mandatory** for serving requests accurately, wait with a bounded timeout inside the runner and return only once validation completes; if the cache is **optional**, allow cold-cache behavior, bound the queue, and do not equate readiness with background completion.

### 6.3. Can Readiness Be Delayed After the Ready Event?

Boot publishes `ApplicationReadyEvent` and then publishes `ReadinessState.ACCEPTING_TRAFFIC`. If an `ApplicationReadyEvent` listener publishes `REFUSING_TRAFFIC` right then, Boot's subsequent `ACCEPTING_TRAFFIC` event can overwrite it. Do not build readiness-delay logic by "setting REFUSING once inside the Ready listener."

If a **mandatory** preparation phase is required, the simplest and least error-prone solution is to finish it synchronously inside a runner before `ApplicationReadyEvent`. If a long mandatory warm-up must run asynchronously, design a dedicated readiness mechanism (such as a custom `HealthIndicator` in the readiness group reflecting actual business readiness) and test every state transition for success, failure, and shutdown.

### 6.4. Why Not Put Everything in @PostConstruct?

`@PostConstruct` runs during bean initialization, when other beans, connectivity, or the full context may not be in the state you need. It also hides initialization duration inside constructors or bean lifecycles.

Use `@PostConstruct` for **local, short preparation depending only on bean state**; use a runner for **application-wide** initialization that requires Spring beans to be ready and must complete before receiving traffic. Not every task belongs in a runner either: the longer or more side-effect-heavy a task is, the more it warrants a dedicated orchestration flow.

## 7. Designing Fault-Tolerant Runners and Safe Restarts

### 7.1. Distinguish Mandatory vs. Optional

Define two branches explicitly:

- **Mandatory:** missing data or connectivity would cause wrong results or data leaks. The runner checks, executes with a timeout, and **throws an exception** on failure so startup aborts. Readiness must never turn on after a critical failure.
- **Optional:** the application can still serve requests properly while the secondary feature is unavailable. Log warnings/metrics, retry outside the startup path, and provide fallbacks. If catching an error to ignore it, verify that ignoring it is genuinely **safe**, not just to "make the app go green."

For transactional operations, call a `@Transactional` service from the runner rather than cramming transaction boundaries, I/O, and retries directly into `run`. Distinguish **transient** errors (timeouts, 503) from **unrecoverable** errors (missing config, incompatible schema). Bound retries because every replica may be retrying concurrently.

### 7.2. Once Per Instance Startup Does Not Mean Once Cluster-Wide

`ApplicationRunner` and `CommandLineRunner` are called **every time `SpringApplication` starts an instance**. If you run 10 pods, each pod runs its own runners; restarts, rolling updates, and scale-outs re-run the same logic. Therefore:

- Data seeding/upserting must be idempotent: re-running must not create duplicate records or send duplicate emails.
- If multiple instances write to a shared resource, use explicit locks or coordination.
- Use dedicated migration tools for schema changes and a Job/leader election if a task may execute only once cluster-wide.
- Do not assume `@Order` between runners across **different instances** provides synchronization.

Failure example: a runner checks `COUNT(*)=0` and inserts a default record across multiple replicas at once. Both see an empty table and insert simultaneously. Use unique constraints + proper upsert/transactions or move seeding to a coordinated Job.

### 7.3. Timeouts, Cancellation, and Consistency

For HTTP/DB calls inside a runner, configure timeouts on the **client/driver**, not just `Thread.sleep` or a loop counter. Account for connection establishment, response reads, and the overall business deadline. If a runner fails after performing partial side effects, compensation, transactions, or idempotency keys may be needed so subsequent restarts do not corrupt data.

Log the task name, start/end timestamps, duration, outcome, and error code; never log tokens, passwords, or sensitive data during startup. Messages should be clear enough for operations to tell **which startup step failed**.

## 8. Configuring Readiness and Liveness Probes in Deployment

To let Kubernetes route traffic based on readiness, add Spring Boot Actuator and enable probes. With the properties in the example, `/readyz` and `/livez` reside on the **main HTTP port**. Sample Kubernetes configuration:

```yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 3
  failureThreshold: 2

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
```

This is a **snippet inside a Kubernetes container spec**, not a standalone Deployment manifest. Values are illustrative only: choose them based on actual startup duration distribution, probe intervals, resources, and deployment requirements.

- **Startup probe:** provides an initialization window; while the startup probe has not succeeded, Kubernetes delays regular liveness/readiness probes. Choose a timeout budget matching the longest acceptable startup.
- **Readiness probe:** when failing, Kubernetes excludes the pod from ready Service endpoints. This is the primary signal ensuring mandatory runners complete before traffic arrives.
- **Liveness probe:** indicates whether the process is still healthy or needs restarting; **do not** include external network/DB checks that turn a shared dependency outage into a cluster-wide pod restart storm.

If you do not enable `management.endpoint.health.probes.add-additional-paths=true`, you can use `/actuator/health/readiness` and `/actuator/health/liveness` when Actuator health probes are enabled. If Actuator serves on a separate `management.server.port`, prefer probing on the main application port to verify the HTTP stack used by real users. Secure management endpoints according to your network and security policies.

**Important note:** Spring Boot may already start the HTTP connector while runners are executing. A platform without readiness probes or with a misconfigured load balancer can still forward requests to the pod prematurely. Therefore, rollout tests must verify that **infrastructure actually excludes unready pods**, not just inspect endpoint JSON.

## 9. Measuring Readiness Time and Finding Slow Runners

Spring Boot Actuator/Micrometer exposes two startup metrics:

- `application.started.time`: time taken for the application to reach the started milestone.
- `application.ready.time`: time taken for the application to reach the ready milestone.

These two metrics reflect different milestones. When a synchronous runner performs lengthy work, ready time rises relative to started time. However, **the difference between metrics is not an exact profiler solely for runners**, as callbacks, listeners, and final-stage processing also contribute. Measure each runner individually with `System.nanoTime()` or a Micrometer timer to isolate the cause.

If `metrics` is exposed in a safe environment:

```bash
curl -s http://localhost:8080/actuator/metrics/application.started.time
curl -s http://localhost:8080/actuator/metrics/application.ready.time
```

Once the app is ready, the metric endpoints can return the corresponding timing data. Actual output depends on the exporter, Actuator configuration, version, and meter registry; do not attempt to query these metrics while the app is not ready yet.

### 9.1. Logging Duration for Mandatory Tasks

Example snippet inside a runner's `run` method, assuming `warmupService` is injected:

```java
long start = System.nanoTime();
try {
    warmupService.prepare(); // Has deadline/timeout inside service
} finally {
    long elapsedMs =
            TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);
    logger.info("startup.warmup.elapsed_ms={}", elapsedMs);
}
```

This is a **snippet**, not a standalone class; it requires a `logger` (such as SLF4J), `warmupService`, and `import java.util.concurrent.TimeUnit`. When multiple runners exist, use stable names for each task (such as `startup.cache`, `startup.config`) instead of relying on the total "Started" log to guess which runner took time.

### 9.2. Measuring Real Startup in Deployment Environments

Measure across at least three scenarios:

1. **Cold start:** un-warmed image/container/JVM, cold caches, dependency connections not yet established.
2. **Rolling update:** multiple new replicas running runners simultaneously, potentially spiking DB/API load.
3. **Degraded dependency:** slow DB, slow DNS, HTTP 503, or unavailable cache.

Record time from container start to readiness success, p95/p99 across multiple startups, pod restart counts, probe failures, concurrent connections opened, and impact on in-flight requests. If adding a runner pushes p99 ready time past your rollout budget, break down the work, bound I/O, choose an appropriate background pattern, or move the task out of the web service.

## 10. Scenario-Based Testing and Troubleshooting

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| `Started` log appears, yet `/readyz` returns 503 | Runners or state transition not yet complete | Read task logs, measure each runner, check timeouts |
| HTTP 8080 responds, yet Kubernetes does not route traffic | Pod not ready yet; probe is reflecting the lifecycle accurately | Check readiness group and Service endpoints; this may be intended behavior |
| Probe never turns UP | Runner stuck, infinite retry loop, exception, or failing readiness check | Bound deadlines, inspect logs and downstream dependency errors |
| `ApplicationReadyEvent` fires while warm-up is incomplete | Runner spawned an async task and returned immediately | Wait with a bound if mandatory; design fallback and mark clearly if optional |
| Two runners execute in reverse of expected order | Missing `@Order` / `Ordered` or identical order values | Assign explicit order; group dependent steps into one coordinating service |
| Every scale-out produces duplicate data | Runner executes on every replica | Idempotency/upsert, unique constraints, coordinated Job |
| Increasing startupProbe still leaves app stuck | Root issue is slow/hung task or dependency | Fix logic, timeouts, and verify; raise probe thresholds only with justification |
| Liveness fails during DB outage | Liveness includes external dependency checks | Keep liveness focused on process health; move needed checks to readiness or recovery logic |
| Readiness probe green yet real requests fail | Probe hits separate management port, missing required dependency, or background task incomplete | Check main HTTP listener, readiness group, and real app behavior |

### 10.1. Minimum Verification Tests

- Normal startup: verify runner order, ready event, readiness accepting, and `SpringApplication.run` returning.
- Add a runner with an intentional bounded wait: before it finishes, readiness reports not ready; afterward it returns UP.
- Force a runner to throw an exception: no `ApplicationReadyEvent`/`ACCEPTING_TRAFFIC`, and startup fails clearly.
- Start two independent instances: observe runner logic executing on both, verifying safe repeatability.
- Simulate slow or unresponsive dependencies: confirm deadlines and startup duration stay within budget.
- On Kubernetes, test a real rollout: new pods receive no traffic until readiness succeeds; old pods continue serving according to the rollout strategy.

## 11. Common Design Mistakes

1. **Using a runner for multi-minute work that requests do not need.** Result: slow rollouts and auto-scaling; move to a batch/background worker.
2. **Treating `ApplicationStartedEvent` as application ready.** That milestone is before runners. Use `ApplicationReadyEvent` and readiness probes properly.
3. **Calling `CompletableFuture.runAsync(...)` for mandatory data and returning.** Spring Boot does not wait for the Future; readiness can enable prematurely.
4. **Catching every exception and logging a WARNING.** If the error breaks requests, the instance dangerously becomes ready; fail startup instead.
5. **Retrying forever without a deadline.** Can keep the pod unready indefinitely; configure explicit timeouts and retry strategies.
6. **Using a runner as a cluster-wide once-only job.** It runs again on every instance; coordination or idempotency is required.
7. **Assuming an open port means Kubernetes will route requests.** Infrastructure relies on readiness, not just an open port.
8. **Relying on arbitrary bean ordering.** Dependent runners need `@Order`/`Ordered` and clear design.
9. **Cramming schema migrations or complex transactions into runners.** Use migration tools and services with clear transaction boundaries.
10. **Using an `ApplicationReadyEvent` listener to synchronously run very long work.** Listeners are synchronous by default and further delay completing readiness; prefer runners or coordinated background processing.
11. **Putting external dependencies in liveness probes.** When a shared dependency fails, the whole cluster can enter a cascading restart loop.
12. **Forgetting to measure p95/p99 startup.** A few fast local runs do not reflect rolling deployments across many concurrent pods.

## 12. Practice Exercises

**Exercise 1 — Identifying order:** Three runners are annotated with `@Order(10)`, `@Order(1)`, and `@Order(5)`. What is the execution order and when is `ApplicationReadyEvent` published?  
**Answer:** order 1 → 5 → 10 (assuming no higher-precedence order such as `Ordered.HIGHEST_PRECEDENCE`); `ApplicationReadyEvent` arrives only after all three finish successfully. Interface type (`ApplicationRunner`/`CommandLineRunner`) does not determine order by itself.

**Exercise 2 — 90-second startup:** An instance takes 3 seconds to build its context and 87 seconds to load an optional image cache. Clients can still receive images via a cold disk cache. Should the full cache load stay inside the runner?  
**Hint:** Do not block readiness for an optional optimization. Move cache warming to the background, bound concurrency, and ensure requests remain correct on a cold cache.

**Exercise 3 — Loading a mandatory catalog:** Pricing requests compute wrong prices without the current exchange-rate table. Can `run` trigger an async load and return immediately?  
**Answer:** No. Either verify completion before readiness or use a readiness indicator reflecting real state; if loading fails, fail fast / refuse traffic per design rather than merely logging a warning.

**Exercise 4 — Multiple replicas:** A Deployment runs 8 pods. A runner runs `INSERT` for default data after checking the table is empty. What is the risk?  
**Answer:** All 8 pods can execute concurrently; check-then-insert causes races, duplicate data, or startup errors. Use migrations/coordinated Jobs and unique constraints + idempotent operations.

**Exercise 5 — Checking readiness signals:** Logs already show `Started MyApp` and `curl localhost:8080/api` returns data, yet `/readyz` returns 503. Can you conclude this is a Spring Boot bug?  
**Answer:** No. This can be valid while a runner is still executing and the HTTP connector is listening; only orchestrator routing based on readiness prevents sending traffic prematurely.

## 13. Checklist Before Adding a Runner to a Web Application

- [ ] Determined whether the task is mandatory before readiness or only an optimization.
- [ ] Selected `ApplicationRunner` or `CommandLineRunner` based on argument needs, not performance expectations.
- [ ] Assigned explicit ordering or a coordinating service if multiple runners depend on each other.
- [ ] Every network/DB call has timeouts; retries are bounded and failure policy is clear.
- [ ] Startup work is idempotent and safe when multiple replicas run concurrently.
- [ ] Long, periodic, or cluster-wide once-only tasks are moved to appropriate tools.
- [ ] Readiness probe covers essential conditions; liveness does not depend on external systems.
- [ ] Tested exception, delay, restart, and real rolling-update scenarios.
- [ ] Measured `application.started.time`, `application.ready.time`, and individual runner durations.
- [ ] Not using the "Started" log or open port as the sole criterion for marking ready.

## Official Documentation

- [Spring Boot 3.3 — SpringApplication: Application Events, Application Availability, Runners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Actuator Endpoints, Kubernetes liveness/readiness probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot API — ApplicationRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot API — CommandLineRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/CommandLineRunner.html)
- [Spring Boot API — ApplicationAvailability](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ApplicationAvailability.html)

In summary, runners are the execution point **after the context starts up but before Spring Boot announces readiness**. Use that spot to satisfy conditions genuinely required to serve requests, keep startup time-bounded, and let readiness probes govern traffic delivery.