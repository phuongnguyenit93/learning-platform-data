# Context Startup Completion Does Not Mean Preparation Tasks Are Finished

In Spring Boot, having the **ApplicationContext initialized and refreshed successfully** does not mean all application preparation tasks have finished. Spring may already have created the required beans, started the web server, and emitted context-related events, while the application is still running an `ApplicationRunner`, `CommandLineRunner`, or an asynchronous task such as loading caches, fetching reference data, connecting to external systems, or warming up resources.

This distinction is crucial when deploying web applications, workers, or systems with health checks. Treating "context started" as "ready to serve" can cause the application to receive requests before essential data is loaded, return transient errors, or produce inconsistent state.

This lesson belongs to the **State and Shutdown** topic in **Spring Boot Fundamentals**. The focus is separating three different questions:

1. **Has the container been built?** — to what extent have beans and core infrastructure been prepared?
2. **Has Spring Boot's startup process finished?** — have the relevant runners and callbacks completed?
3. **Does the application truly meet business conditions to serve traffic?** — are essential data, resources, and preparation tasks ready?

These three questions can have three different answers at the exact same moment.

## 1. What Does Context Startup Completion Mean?

`ApplicationContext` is the container managing Spring beans, configuration, and many foundational services. During `refresh()`, Spring executes steps such as processing bean definitions, instantiating non-lazy singletons, setting up lifecycle components, and completing context initialization.

In a typical Spring Boot application, the sequence can be visualized as follows:

~~~text
main()
  |
  v
SpringApplication.run(args)
  |
  +-- Prepare Environment and configuration
  |
  +-- Create ApplicationContext
  |
  +-- Refresh ApplicationContext
  |     +-- Create eager beans
  |     +-- Run init callbacks / @PostConstruct on those beans
  |     +-- Start some SmartLifecycle components
  |     +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  |
  +-- Invoke ApplicationRunner and CommandLineRunner
  |
  +-- ApplicationReadyEvent
  |
  +-- ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- SpringApplication.run(...) completes
~~~

The diagram illustrates a typical startup flow; Spring Boot also includes additional callbacks, events, and mechanisms depending on application type, configuration, and version.

**Successful context refresh** is usually a necessary condition for an application to run, but not a sufficient condition to declare that all preparation work is complete.

For example: service beans have already been created, yet a runner is still syncing the product catalog from a data store. Or a bean submitted a data-loading task to an executor and returned immediately, leaving a background thread to continue running afterward.

### Even an Existing Context May Not Be Finished Refreshing

Very early in startup, `SpringApplication` may have created the context object without completing refresh yet. Therefore:

- **Context created** does not mean context refreshed.
- **Context refreshed** does not mean all runners have finished.
- **Runners finished** does not mean all background tasks launched by runners have finished.
- **Application reporting ready** in Spring Boot's lifecycle does not by itself prove that all business conditions outside Spring are satisfied.

In simple systems, these milestones may occur very close together. In systems with multiple preparation steps, the gap may be a few seconds, several minutes, or indefinite if a task hangs.

## 2. Distinguishing Lifecycle Milestones

Three key Spring Boot events:

| Event | Main meaning | What cannot be concluded yet |
|---|---|---|
| `ContextRefreshedEvent` | The Spring context completed a refresh | Boot runners have finished, or the app is business-ready |
| `ApplicationStartedEvent` | Spring Boot refreshed the context, before calling runners | `ApplicationRunner` and `CommandLineRunner` have completed |
| `ApplicationReadyEvent` | Spring Boot finished calling runners and reached the ready phase | All async tasks or external systems are ready |

`ContextRefreshedEvent` is a Spring Framework event. It may appear multiple times when an application uses multiple contexts or performs special refresh operations; do not assume it fires strictly once in every architecture.

`ApplicationStartedEvent` and `ApplicationReadyEvent` are Spring Boot lifecycle events. In a normal successful startup path, `ApplicationReadyEvent` occurs after runners. Spring Boot then publishes readiness accepting traffic through the availability mechanism.

### Example of Timing Differences

Suppose startup has three tasks:

~~~text
0.0s   Application starts running
1.2s   ApplicationContext refresh finishes
1.3s   ApplicationStartedEvent
1.3s   ApplicationRunner starts loading data (synchronously)
5.0s   ApplicationRunner finishes
5.0s   ApplicationReadyEvent
5.0s   Spring Boot publishes readiness ACCEPTING_TRAFFIC
~~~

Between 1.2 seconds and 5 seconds, the context may already have all its beans, yet the application **has not finished its synchronous preparation step**.

If that work is replaced with a background task:

~~~text
0.0s   Application starts running
1.2s   ApplicationContext refresh finishes
1.3s   ApplicationRunner submits cache-loading task to executor
1.3s   ApplicationRunner returns immediately
1.3s   ApplicationReadyEvent
1.3s   Boot publishes readiness ACCEPTING_TRAFFIC
5.0s   Background task finishes loading cache
~~~

In the second example, Spring Boot's ready milestone arrives **before the cache finishes loading**. This scenario is very easy to overlook.

Timestamps are illustrative only, not default Spring Boot timings.

## 3. Why Can the Web Server Run Before the Application Is Truly Ready?

For web applications using an embedded server, server startup is tied to creating and refreshing the web application context. The HTTP port can already be open before runners finish.

This creates two distinct concepts:

- **Port listening:** a TCP connection can be accepted and an HTTP request can be processed.
- **Application eligible to receive serving traffic:** all startup conditions and critical business conditions have been met.

Do not use the test "can reach `http://localhost:8080`" to conclude startup is complete. A simple endpoint may respond with 200 while another endpoint requiring a cache or reference data still fails.

Example:

~~~text
Load balancer
    |
    |  If readiness is ignored:
    v
Spring Boot HTTP server (already listening)
    |
    +-- GET /ping        -> 200
    |
    +-- GET /products    -> error because cache is not loaded yet
~~~

A safer deployment approach is requiring the ingress or orchestrator to **route traffic only after the readiness probe passes**, while also adding application-layer protection for call paths that might bypass orchestration.

A readiness probe is only meaningful if the conditions it checks actually cover the resources needed to handle the corresponding traffic.

## 4. ApplicationRunner and CommandLineRunner Are Synchronous Startup Steps

`ApplicationRunner` and `CommandLineRunner` are hooks that run after the context has refreshed. Spring Boot invokes registered runners in order and waits for each call to return.

Example:

~~~java
package com.example.bootstrap;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class RequiredPreparationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Starting mandatory data check...");

        boolean requiredDataAvailable = checkRequiredData();

        if (!requiredDataAvailable) {
            throw new IllegalStateException(
                    "Mandatory data is not ready");
        }

        System.out.println("Mandatory preparation completed.");
    }

    private boolean checkRequiredData() {
        // Simulate check; replace with actual application validation.
        return true;
    }
}
~~~

In this example, `run(...)` only returns when the synchronous check finishes. If it throws an exception, Spring Boot treats startup as failed rather than emitting a successful ready milestone.

`@Order(10)` can coordinate the ordering of multiple runners when dependencies exist between preparation steps. Remember that **ordering does not govern background tasks**: a runner invoked first that submits work to a thread pool and returns immediately does not guarantee that work finishes before the next runner.

### When Is Synchronous Execution Appropriate?

Consider synchronous startup when:

- Missing data or configuration makes every business request wrong.
- The work completes relatively quickly and predictably.
- Failure should cause application startup to fail immediately.
- The task can be safely re-run on every deployment or restart.

Reasonable examples include minimal schema checks, validating mandatory configuration, or loading a small indispensable lookup table.

### When Should Startup Not Be Blocked for Too Long?

An operation taking tens of minutes, depending on an unstable service, or requiring long retries can trap the application in startup. In such cases, consider an asynchronous processing model **combined with a readiness gate**, or move the work to a separate job and let the application track its outcome.

The choice should come from business requirements and operational strategy, not simply from which code is more convenient to write.

## 5. "Runner Finished" Differs from "Work Launched by Runner Finished"

Consider two snippets.

**Approach A — wait until completion:**

~~~java
@Override
public void run(ApplicationArguments args) {
    catalogService.loadAllSynchronously();
}
~~~

Assume `loadAllSynchronously()` only returns when data loading finishes or throws an error. Spring Boot must wait for it to finish before continuing.

**Approach B — hand off to a background thread and return:**

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(catalogService::loadAllSynchronously);
}
~~~

With approach B, `executor.execute(...)` usually returns as soon as the task is accepted. Spring Boot does not automatically track that thread to know whether the cache is done. It only knows the `run(...)` call returned.

In the snippets, `catalogService` and `executor` are hypothetical dependencies configured by the application.

Several variants behave similarly:

- Calling an `@Async` method through a Spring proxy.
- Launching `CompletableFuture.runAsync(...)` without awaiting the result.
- Creating a `Thread` and calling `start()`.
- Scheduling work on a scheduler or queue.
- Triggering a cache-loading job with background refresh.

**What must be managed is not whether a runner or event ran, but the actual completion of the preparation condition.**

## 6. @PostConstruct and SmartLifecycle Also Do Not Always Mean "Everything Is Ready"

`@PostConstruct` is invoked during bean initialization. If a `@PostConstruct` method works synchronously and throws no errors, that work finishes before the bean is considered initialized.

However, if it only starts a thread or submits work to an executor and returns, background work continues running:

~~~java
@PostConstruct
public void init() {
    backgroundExecutor.execute(this::rebuildIndex);
}
~~~

The snippet above only illustrates asynchronous behavior. `@PostConstruct` is not an ideal place to integrate a long-running business workflow because bean initialization becomes vulnerable to task duration and failures.

Similarly, a bean implementing `SmartLifecycle` can start a consumer or connection during context refresh. `start()` finishing may only mean "asked the worker to start", not that the consumer has received partition assignments, loaded a snapshot, or fully synchronized state.

With `@Scheduled`, the first execution depends on schedule, delay, and scheduler configuration. You cannot deduce that a scheduled task has run just because the context refreshed.

Comparison table:

| Mechanism | What Spring typically waits for | Risk when async work starts inside |
|---|---|---|
| `@PostConstruct` | Initialization method returns | Spawned thread keeps running in background |
| `SmartLifecycle.start()` | `start()` method finishes | Consumer/service may not be connected or synced yet |
| `ApplicationRunner.run()` | `run()` method returns | Submitted future or task has not completed yet |
| `@EventListener(ApplicationReadyEvent.class)` | Synchronous listener returns | Background task started by listener is still unfinished |
| `@Scheduled` | Not a startup barrier | First run may happen after the ready milestone |

These mechanisms have different purposes. Do not pick a hook based on the assumption that Spring automatically waits for all work initiated inside it.

## 7. Readiness, Liveness, and Business Readiness State

Spring Boot has the **Application Availability** mechanism to represent key lifecycle signals. Common states:

- `LivenessState.CORRECT`: the process can run, not necessarily qualified to serve business requests yet.
- `ReadinessState.ACCEPTING_TRAFFIC`: per Spring Boot's lifecycle, the app has reached the stage to accept traffic.
- `ReadinessState.REFUSING_TRAFFIC`: the application is not yet or no longer willing to accept traffic.

Distinguish clearly:

**Liveness answers:** is this process still in an operable state?

**Readiness answers:** should new requests be routed to this process right now?

In orchestration systems such as Kubernetes, readiness is typically used to remove a pod from traffic-serving endpoints without necessarily restarting the pod. Liveness is typically used to decide when to act on a malfunctioning process, such as restarting it.

### Spring Boot State and Business Conditions Do Not Sync Automatically

Spring Boot can publish `ReadinessState.ACCEPTING_TRAFFIC` after `ApplicationReadyEvent` even while an asynchronous data-loading task is still running.

Therefore, if system readiness genuinely depends on that task, you need to **add a dedicated readiness condition** instead of trusting a single lifecycle milestone.

For example, we can consider the application ready only when:

~~~text
Spring Boot has reached ready state
                  AND
Business preparation data has completed
                  AND
Mandatory dependencies are usable
                  |
                  v
Readiness probe -> UP
~~~

Not every external dependency must be checked with a network call on every health probe. Health check design must avoid generating heavy load or turning a brief glitch unrelated to core requests into an outage across all pods.

## 8. A Common Bug: Marking ACCEPTING_TRAFFIC Too Early

Suppose this listener runs on `ApplicationReadyEvent`:

~~~java
@EventListener(ApplicationReadyEvent.class)
public void onReady() {
    preparationService.startAsync();
}
~~~

If `startAsync()` only submits a task and returns, Spring Boot may proceed to publish readiness accepting traffic right after the listener. The preparation task might not even have started executing yet.

Another subtle bug is publishing `ReadinessState.REFUSING_TRAFFIC` too early and assuming it will stick. Spring Boot can publish `ACCEPTING_TRAFFIC` afterward during normal startup and overwrite the earlier intent.

Therefore, a clean strategy for asynchronous preparation is **adding a HealthIndicator that checks preparation status to the readiness health group**. That way, composite readiness can still report failing even if Boot's lifecycle state has transitioned to ACCEPTING_TRAFFIC.

## 9. Complete Example: Loading Resources Asynchronously Without Opening Readiness Yet

We will build a Spring Boot 3.x example consisting of:

1. A `PreparationHealthIndicator` holding `PREPARING`, `READY`, or `FAILED` state.
2. A service executing preparation work asynchronously.
3. A listener using `ApplicationReadyEvent` to trigger the work.
4. Spring Boot Actuator configuration adding the `preparation` condition to the readiness group.

The example uses a multi-second wait to simulate data loading. This is a **technical simulation**, not a recommendation to use `Thread.sleep` in production.

### 9.1. Declaring the Dependency

If the project already has the web starter, add Actuator to expose health endpoints. With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

If using Gradle (Groovy DSL):

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
~~~

Spring Boot and the project's dependency management should manage starter versions instead of picking arbitrary versions per starter.

### 9.2. Creating a Dedicated Indicator for Preparation Work

File `PreparationHealthIndicator.java`:

~~~java
package com.example.preparation;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("preparationHealthIndicator")
public class PreparationHealthIndicator implements HealthIndicator {

    private enum Phase {
        PREPARING, READY, FAILED
    }

    private final AtomicReference<Phase> phase =
            new AtomicReference<>(Phase.PREPARING);

    public void markReady() {
        phase.set(Phase.READY);
    }

    public void markFailed() {
        phase.set(Phase.FAILED);
    }

    @Override
    public Health health() {
        Phase current = phase.get();

        if (current == Phase.READY) {
            return Health.up()
                    .withDetail("phase", current.name())
                    .build();
        }

        return Health.down()
                .withDetail("phase", current.name())
                .build();
    }
}
~~~

A few key points:

- The initial value is `PREPARING`, so the application has not met business readiness as soon as the indicator is created.
- `AtomicReference` allows the task thread and health-check thread to observe updated state safely.
- Both `PREPARING` and `FAILED` return `DOWN` because serving traffic is not yet permitted under this condition.
- Bean name `preparationHealthIndicator` is recognized by Actuator as health contributor `preparation`. That name will be used in the readiness group configuration.

In real systems, you can include preparation start time, completion time, or sanitized error codes. Do not put secrets or raw exceptions containing sensitive details into public health responses.

### 9.3. Declaring a Spring-Managed Executor

File `PreparationAsyncConfiguration.java`:

~~~java
package com.example.preparation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class PreparationAsyncConfiguration {

    @Bean("preparationExecutor")
    public ThreadPoolTaskExecutor preparationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("prepare-");
        executor.initialize();
        return executor;
    }
}
~~~

`@EnableAsync` enables processing `@Async`-annotated methods via Spring proxies. An explicit executor name avoids carelessly sharing thread pools meant for other work.

Do not assume calling an `@Async` method from another method on the **same instance** will switch to a background thread, because self-invocation can bypass the proxy. In the next example, another bean calls the async service.

### 9.4. Creating the Service That Performs Preparation Work

File `PreparationService.java`:

~~~java
package com.example.preparation;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PreparationService {

    private static final Logger log =
            LoggerFactory.getLogger(PreparationService.class);

    private final PreparationHealthIndicator indicator;

    public PreparationService(PreparationHealthIndicator indicator) {
        this.indicator = indicator;
    }

    @Async("preparationExecutor")
    public void prepare() {
        log.info("Starting background data preparation");

        try {
            // Simulate cache loading or resource initialization.
            // Replace with actual application work.
            Thread.sleep(3_000);

            indicator.markReady();
            log.info("Data preparation completed");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            indicator.markFailed();
            log.warn("Preparation task was interrupted", exception);
        } catch (Exception exception) {
            indicator.markFailed();
            log.error("Preparation task failed", exception);
        }
    }
}
~~~

`@Async("preparationExecutor")` executes the work on the executor when called through the Spring proxy. The `prepare()` method returns to the caller before `Thread.sleep(...)` or real work finishes.

If an error occurs, the indicator remains `DOWN` and the logger records the cause. This pattern intentionally does not auto-retry; in production, define retry, timeout, or fail-fast policies.

### 9.5. Triggering from ApplicationReadyEvent

File `PreparationStarter.java`:

~~~java
package com.example.preparation;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PreparationStarter {

    private final PreparationService preparationService;

    public PreparationStarter(PreparationService preparationService) {
        this.preparationService = preparationService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        preparationService.prepare();
    }
}
~~~

`PreparationStarter` calls `prepare()` on **another bean**, so the call passes through the `@Async` proxy. The listener can return right after the executor accepts the task.

Using `ApplicationReadyEvent` here is not meant to prove the work is finished; rather, it simply serves as the **trigger point** for the work after Boot's synchronous startup steps.

### 9.6. Configuring the Readiness Group

In `src/main/resources/application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,preparation
~~~

Meaning:

- `management.endpoint.health.probes.enabled=true` enables liveness and readiness health groups even in environments where probes are not auto-enabled.
- `readinessState` is the health contributor reflecting Spring Boot's lifecycle readiness state.
- `preparation` is the health contributor provided by `PreparationHealthIndicator`.

When any contributor in the readiness group reports `DOWN`, the aggregated health group normally also reports failing.

If you want to expose probe endpoints on the main web port in a setup with a separate management port, Spring Boot also supports:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Depending on configuration, additional probe paths such as `/readyz` and `/livez` will be served on the main server port. Verify network topology and deployment configuration to ensure probes traverse the intended port.

### 9.7. Observing the Result

For a web application with Actuator, call:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

Initially, the business indicator is still `PREPARING`, so the readiness group may return:

~~~text
HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"DOWN"}
~~~

After the task completes, the indicator returns `UP`:

~~~text
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

These are illustrative responses. Detailed contents may be hidden by Actuator configuration and status codes can be customized.

Boot's state at `ApplicationAvailability.getReadinessState()` may already be `ACCEPTING_TRAFFIC` while the **readiness health group** is still `DOWN` because of `preparation`. This is precisely why you must understand the difference between lifecycle state and aggregated readiness state.

## 10. When to Keep Work Synchronous vs. Using a Readiness Gate?

Two main strategies:

| Criterion | Synchronous prep before ready | Async prep with readiness gate |
|---|---|---|
| Structure | Runner or startup callback waits for work to finish | Task runs in background; indicator reflects completion |
| `ApplicationReadyEvent` milestone | Arrives after synchronous runners end | May arrive before background task completes |
| Business state signal | Can use runner failure to block startup | Needs dedicated readiness control |
| Preparation error | Exception can fail startup | Needs retry policy, DOWN status, or proactive app shutdown |
| Pros | Easy to reason about ordering and prerequisites | Does not block startup thread on long tasks |
| Risks | Prolonged startup, easy deploy timeout | May report ready early if gate is forgotten |

### Choose Synchronous When the Condition Is Mandatory and Fail-Fast Is Needed

If missing the condition makes the application useless and preparation finishes quickly, a synchronous runner is usually clear:

~~~java
@Bean
ApplicationRunner warmUpRequiredData(RequiredCatalogLoader loader) {
    return args -> loader.loadAndWait();
}
~~~

`RequiredCatalogLoader` and `loadAndWait()` are illustrative application-defined classes/methods.

If `loadAndWait()` throws an exception, Spring Boot handles startup failure instead of reaching ready. If it succeeds, we know this synchronous task completed before the ready milestone.

### Choose Async + Readiness When Infrastructure Must Start First

For example, a worker needs to initialize connections and then sync a large data snapshot. Starting the application context may be quick, while syncing takes much longer. Using a readiness indicator for the snapshot lets the system clearly report "process running, not yet serving".

However, do not equate "created the background task" with "successfully loaded". Only flip the indicator to ready after verification steps pass.

## 11. What Happens If the Preparation Task Fails?

There are three common policies; choose one explicitly.

### A. Failure Means the Application Cannot Run

If a mandatory condition fails and the application has no recovery path within the current process, a synchronous runner can throw an exception so startup fails.

Benefit: clear failure state, avoiding keeping an unserviceable process running.

Drawback: if an external dependency is flaky, there is a risk of continuous restart loops; align with the deployment platform's backoff and retry policies.

### B. The Application Can Self-Recover in the Background

If preparation is a retryable task, keep readiness `DOWN`, log, and retry in a controlled manner. Only switch to `UP` upon success.

Consider:

- Timeout for each attempt.
- Exponential backoff and retry rate limits.
- Cancellation condition if the application is shutting down.
- Distinguishing unrecoverable configuration errors from transient network errors.
- Metrics for preparation duration, attempt count, and final status.
- Alerts if readiness stays `DOWN` too long.

Do not retry indefinitely at high frequency or keep threads busy without cancellation support.

### C. The Application Serves in Degraded Mode

Some features can still work even while an auxiliary cache is not ready. In that case, you do not necessarily mark the entire pod `DOWN`. You can guard individual business endpoints per feature, or publish separate availability per module.

Do not put every optional task into the readiness group: an analytics counter failing to update usually should not pull the entire API out of traffic.

## 12. Cases of "Looking UP Yet Still Not Ready"

A system can exhibit misconceptions such as:

**Health endpoint returns 200 yet services needing the database cannot work.** The endpoint may only check liveness, or the health group omits mandatory service conditions.

**HTTP server opens port yet cannot serve useful requests.** The web server may start listening during refresh while runners are still processing data.

**`ApplicationReadyEvent` fired yet cache is still loading.** A listener or runner submitted an async task; Spring Boot does not automatically wait for it.

**`ReadinessState.ACCEPTING_TRAFFIC` yet readiness group is `DOWN`.** An indicator added to the health group is still failing. The two values belong to different layers of interpretation.

**A `SmartLifecycle` bean reports running yet the consumer has not received data.** Bean state may only reflect that the run loop started, not that business sync finished.

**An external dependency just became unavailable.** Ready at startup does not guarantee ready forever; readiness must reflect critical operational conditions if application policy requires it.

In every situation, identify **who publishes the state**, **what the state describes**, and **what conditions requests truly need**.

## 13. Checking Readiness in Kubernetes and Load Balancers

In Kubernetes, a readiness probe typically checks an endpoint like:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

This snippet illustrates a container listening on port 8080 using the Actuator readiness endpoint.

A readiness probe does not necessarily block all direct requests. It primarily helps traffic orchestration **avoid sending requests via routes that honor readiness**.

If an application needs very long startup, consider `startupProbe` to grant sufficient startup time before the liveness probe starts triggering restarts. `startupProbe` differs from readiness: it supports slow-starting apps, rather than replacing business conditions for serving requests.

Also distinguish:

- **Liveness DOWN:** may lead to a restart per orchestrator configuration.
- **Readiness DOWN:** typically removes the instance from new-traffic routing.
- **Shutdown:** the system must stop accepting new requests, finish in-flight requests, and release resources.

Each signal has a distinct operational effect; do not use readiness DOWN as a default way to ask the orchestrator to restart an application.

## 14. Relation to Shutdown: Not Just Opening the Port, Also Closing at the Right Time

The relationship between startup and shutdown is symmetrical:

~~~text
STARTUP
  Create context
      |
      v
  Complete preparation conditions
      |
      v
  Accept traffic

SHUTDOWN
  Begin refusing new traffic
      |
      v
  Complete / cancel running work per policy
      |
      v
  Close resources, context, and process
~~~

Related configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

For servers supporting graceful shutdown, Spring Boot attempts to stop accepting new requests and allow time for in-flight requests within configured limits. This **does not automatically guarantee** that all running background tasks, consumers, or preparation jobs will finish before the JVM exits.

If the application has background workers, manage their lifecycles explicitly, such as:

- Recording the shutdown signal so no new work starts.
- Allowing safe cancellation or interruption of stoppable work.
- Waiting for critical in-flight tasks within a bounded timeout.
- Using `SmartLifecycle.stop(...)`, bean destruction callbacks, or proper executor shutdown.
- Not reporting readiness `UP` when the system no longer accepts new work.

In Spring Boot, readiness state typically switches to refusing traffic when entering a managed shutdown flow. Still, verify actual connection draining in the deployment environment, especially when load balancers or proxies take time to update instance lists.

**Context closing** also does not automatically mean all background tasks have terminated cleanly. Startup and shutdown management require the same work ownership model.

## 15. Measuring and Observing Preparation State

To distinguish "context alive" from "data ready", collect minimum signals:

| Signal | Meaning |
|---|---|
| Startup start timestamp | Baseline for total preparation time |
| Context refresh completion time | Spring infrastructure built |
| Runners completion time | Boot completed synchronous startup step |
| Business preparation completion time | Required data or resources actually usable |
| Preparation duration | Identify slowness in startup vs. background worker |
| `PREPARING`, `READY`, `FAILED` states | Used for readiness and alerting |
| Sanitized failure reason | Aids debugging without leaking sensitive data |

A simple log format might be designed as:

~~~text
INFO  Application context refreshed
INFO  Starting mandatory runners
INFO  Spring Boot ready event observed
INFO  Beginning asynchronous catalog preparation
INFO  Preparation completed: 3270 ms
INFO  Readiness health contributor preparation=UP
~~~

These are example application-written logs, not mandatory default Spring Boot log lines.

If an instance stays stuck in `PREPARING`, operators need to know what it is waiting for, how many attempts it made, and what condition will transition it to `READY` or `FAILED`.

## 16. Lab Exercise: Observing the Gap Between Context and Business Readiness

You can run this exercise directly on the sample app from section 9.

### Experiment 1 — Controlled Slow Preparation

Keep `Thread.sleep(3_000)` in `PreparationService`, run the app, and repeatedly call:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

Observe an initial period returning `DOWN`, followed by switching to `UP` when the background task calls `markReady()`.

Key milestone to verify: `ApplicationReadyEvent` may have already fired before `preparation` returns `UP`.

### Experiment 2 — Failing Preparation

Replace the simulated body in `prepare()` with:

~~~java
throw new IllegalStateException("Simulated data is invalid");
~~~

Place this inside the example's `try` block so the `catch (Exception exception)` branch logs the error and calls `markFailed()`.

Expected: the process may remain alive, while the readiness group continues returning `DOWN`. If the system requires fail-fast, add a policy to proactively shut down the application or make the task a synchronous runner.

### Experiment 3 — Comparing with a Synchronous Runner

Move the simulated preparation into a synchronous `ApplicationRunner`. Restart and observe:

- `ApplicationStartedEvent` arrives before the runner begins.
- `ApplicationReadyEvent` arrives after the runner returns.
- If the runner throws an exception, the application enters startup failure handling rather than succeeding to ready.

### Experiment 4 — Using readinessState Only

Temporarily change the readiness group to:

~~~properties
management.endpoint.health.group.readiness.include=readinessState
~~~

Now the health group no longer relies on `preparation`. Boot's readiness milestone can flip `UP` while simulated preparation is still running. This demonstrates that **a single default startup state cannot stand in for all business conditions**.

Restore the original configuration after testing.

## 17. Misconceptions to Avoid

**"Context refreshed means the system is ready."** False. Runners and async tasks may not have finished yet.

**"Once the server opens its port, ingress can send traffic."** Not necessarily. A proper readiness probe and traffic path respecting its result are needed.

**"ApplicationStartedEvent means ready."** No. Spring Boot still executes runners after the started milestone.

**"ApplicationReadyEvent guarantees all background work is done."** No. It reflects completion of the synchronous startup path managed by Boot, not every task submitted to an executor.

**"Calling @Async inside a runner makes Boot wait for that method."** No. When called through a proxy, the async method returns control to the runner before the actual work finishes.

**"ReadinessState.ACCEPTING_TRAFFIC always means business readiness is met."** No. Boot's state only reflects the lifecycle perspective; add business conditions if your system requires them.

**"Every external dependency must be checked live on every health request."** No. Checking too many dependencies can make the health endpoint slow, create heavy load, or take the app out of service due to an optional dependency.

**"Readiness DOWN means the process must restart."** No. Readiness and liveness have different purposes.

**"Graceful shutdown automatically handles all background tasks."** No. Background work needs managed stopping or completion mechanisms.

## 18. Design Principles to Remember

When an application has custom preparation steps, clearly define:

1. **Which conditions are mandatory to receive traffic?** Do not mechanically pull optional tasks into readiness.
2. **Who owns the preparation task?** A runner, service, scheduler, background worker, or separate job?
3. **Who knows when the task finishes?** Synchronous wait, managed future, atomically published state, or verified data.
4. **Are failures recoverable?** Decide between fail-fast, retry, or degraded mode.
5. **Which signals compose readiness?** Verify the endpoint accurately reports during preparation and failure.
6. **How will shutdown cancel or wait for tasks?** Never leave background threads unowned.
7. **Are duration and causes observable?** Logs, metrics, and alerts should answer "what is it waiting for?".

For a service capable of serving early while preparing optional resources, you can allow traffic to some features and guard unready parts individually. For systems requiring strict consistency, the readiness gate should enforce stronger conditions.

## Conclusion

**Successful ApplicationContext refresh is an infrastructure milestone, not a guarantee that all preparation work has ended.** Spring Boot continues running `ApplicationRunner` and `CommandLineRunner` after context refresh; furthermore, asynchronously launched tasks can persist even after `ApplicationReadyEvent`.

When work is mandatory and short, let a runner execute it **synchronously**, so Spring Boot reaches ready only after completion. When work is **asynchronous**, track a separate `PREPARING/READY/FAILED` state and include required conditions in the readiness health group to avoid taking traffic too early.

Across the entire **State and Shutdown** lifecycle, keep **context created**, **Boot startup finished**, **application business-ready**, and **application shutting down** clearly separated. Distinguishing these milestones accurately makes deployments safer, reduces startup errors, and keeps traffic handling consistent.
