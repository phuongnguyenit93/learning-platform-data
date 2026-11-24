# Measuring and Testing Before Applying Lazy Initialization in Production

**Lazy initialization** in Spring Boot defers creating certain beans until they are requested, rather than creating them right when the `ApplicationContext` is refreshed. It can be enabled globally via:

~~~properties
spring.main.lazy-initialization=true
~~~

This can **shorten startup time**, yet does not eliminate bean initialization cost. The cost can shift to the first request, the first execution of a job, or a rarely used feature branch. Configuration errors previously caught during startup can also be delayed until real users hit that functionality.

This lesson belongs to **Spring Boot Application Runtime**, section **Lazy Initialization**, using Spring Boot **3.3.x / Spring Framework 6.1 / Java 17+** APIs. The goal is establishing controlled experiments and acceptance criteria **before enabling lazy in production**, rather than concluding from a single `Started` log line.

## 1. Understand What Changes

~~~text
EAGER, default:
SpringApplication.run
  -> create bean definitions
  -> create/initialize many non-lazy singletons
  -> ApplicationReadyEvent
  -> first request: typically uses already-initialized beans

GLOBAL LAZY:
SpringApplication.run
  -> create bean definitions
  -> create only beans required to start early
  -> ApplicationReadyEvent
  -> first request: may create additional lazy beans
  -> handle request
~~~

**Important limitations:**

- Default is `spring.main.lazy-initialization=false`.
- Setting `true` does not mean **every** bean is lazy. A lazy bean can still be created early if an eager singleton must inject it, or if framework infrastructure requires it.
- `@Lazy` applies lazy initialization to a single bean/component. `@Lazy(false)` can keep critical beans initializing early when the whole app enables lazy.
- `ApplicationReadyEvent` and readiness reflect Spring Boot lifecycle milestones, **not proof that all lazy beans have been created, verified, and warmed**.
- Cold latency, CPU spikes, post-warm-up RAM growth, and `BeanCreationException` on first use may occur.

| Behavior | Eager | Lazy |
| --- | --- | --- |
| Startup | Pays cost to initialize many beans | Can be faster |
| First HTTP request | Many beans already exist | May have to initialize more beans |
| Bean error detection | Many errors surface at startup | Some errors surface at first use |
| RAM at ready | Potentially higher | Temporarily lower |
| RAM under real load | Workload-dependent | Can climb as beans get created |
| Scale-out | Latency during instance startup | Latency may shift onto new traffic |

Laziness **shifts when the cost is paid**, without optimizing bean creation code, DB queries, connections, or business logic on its own.

## 2. Formulating a Measurement Hypothesis

Example of a sound hypothesis:

> On the same artifact, JDK, and resources, enabling global lazy reduces time to `ApplicationReadyEvent` without causing cold requests, p95/p99, error rates, memory, readiness, or shutdown to breach acceptance criteria.

Before running benchmarks, define:

1. **Target milestone:** are you trying to shorten JVM startup, Spring Boot ready, or time from Pod creation to accepting traffic?
2. **SLOs:** what first-request latency, p95/p99, error rate, and readiness success rate are acceptable?
3. **Critical paths:** login, checkout, main APIs, reports, batch jobs, queue consumers, and which rare features must work?
4. **Resources:** RAM, heap, CPU, GC, container memory limits, and peak load.
5. **Fail-fast policy:** which beans must report configuration errors before the instance accepts traffic?
6. **Rollout/rollback criteria:** when to enable for canary, and when to halt and revert?

There is no universal "standard" startup percentage gain across all services. Base decisions on operational SLOs and real testing.

## 3. Distinguishing Timing Milestones

~~~text
OS/container launches JVM
  |
  v
SpringApplication.run
  |
  +-- refresh ApplicationContext
  |
  +-- ApplicationStartedEvent
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent
  |
  +-- AvailabilityChangeEvent(ACCEPTING_TRAFFIC)
  |
  +-- external readiness probe succeeds
  |
  v
First request calling an un-warmed branch
  |
  +-- lazy bean is created
  |
  v
HTTP response
~~~

| Metric | Meaning |
| --- | --- |
| `T_started` | Time to `ApplicationStartedEvent`, before runners |
| `T_ready` | Time to `ApplicationReadyEvent`, after runners |
| `T_probe_ready` | Time from when infrastructure launches the instance until the probe sees ready state |
| `T_cold_http` | Latency of the first request triggering a still-cold branch |
| `T_warm_http` | Latency after warm-up, measuring p50/p95/p99 distribution |
| `T_scale_out` | From requesting an added instance until it receives useful traffic |

Spring Boot 3.3 offers `ApplicationReadyEvent.getTimeTaken()`, returning a `Duration` **or `null` if unknown**. Listener sample:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationReadyEvent>) event -> {
    Duration taken = event.getTimeTaken();
    System.out.println("READY_MS="
            + (taken == null ? "unknown" : taken.toMillis()));
});
app.run(args);
~~~

This is an illustrative snippet requiring the `MyApplication` configuration class and corresponding imports. Complete code is in Section 7. Event timing **excludes full image pull, scheduling, readiness probes, and network overhead**.

**Do not compare `Started` of build A against `Ready` of build B.** If measurement milestones differ, the comparison is invalid.

## 4. Designing a Fair A/B Test

Two variants differing by a single setting:

- **A — Baseline:** `spring.main.lazy-initialization=false`.
- **B — Candidate:** `spring.main.lazy-initialization=true`.

Variables that must be controlled:

| Variable | Must Keep |
| --- | --- |
| Source code, commit, JAR/image, Spring Boot version | Identical |
| JDK, JVM args, `-Xms`/`-Xmx`, collector | Identical |
| CPU, RAM limit, storage, OS/container image | Identical |
| Profiles and all properties besides the lazy flag | Identical |
| DB, Redis, HTTP dependencies, test data setup | Equivalent |
| Cold/warm cache state, traffic path | Documented, controlled |
| Measurement tools, client location, and network | Fixed |
| Endpoints and warm-up sequence | Identical |

Every **cold run must use a fresh JVM**. Repeat multiple rounds—for example, 10–20 iterations for an initial survey if cost allows—compute median/spread, and increase sample size when variance is noisy. Alternate A/B run order across rounds to reduce time-of-day bias.

Never treat a second request on the same JVM as a "second cold run": singleton beans may already have been created.

## 5. Metrics Table to Collect

| Metric | Eager | Lazy | Decision |
| --- | --- | --- | --- |
| Median `T_ready_ms` | Measured | Measured | Consistent startup gain? |
| `T_probe_ready_ms` | Measured externally | Measured externally | Does the instance take traffic sooner? |
| First HTTP latency per endpoint | Measured | Measured | Does cold penalty breach SLO? |
| Warm p50/p95/p99 | Load test | Load test | Did tail latency and throughput change? |
| Concurrent first requests | Cold load burst | Cold load burst | Do requests wait concurrently on bean init? |
| RSS at ready | OS/container | OS/container | Initial footprint |
| RSS post-warm-up and peak | OS/container | OS/container | Within memory limit? |
| Heap, CPU, GC pauses | JVM/JFR | JVM/JFR | Any object creation/GC spikes? |
| Startup errors | Logs/tests | Logs/tests | Were any errors hidden? |
| Errors hitting rare branches | Smoke/soak | Smoke/soak | Any first-use failures? |
| Readiness/shutdown | Tests | Tests | Safe operations? |

Formula for `T_ready` reduction percentage:

~~~text
100 * (T_ready_eager - T_ready_lazy) / T_ready_eager
~~~

Apply only when baseline exceeds 0 and milestones match. **Never call a single `curl` timing a p99**: p99 is a percentile computed over many request samples.

## 6. Tools for Measuring Startup and First-Use

### `ApplicationReadyEvent`

Use `getTimeTaken()` to measure Spring Boot time to ready; log under a clear key for dashboard aggregation. Do not equate it with when Kubernetes routes traffic.

### `BufferingApplicationStartup` and Actuator

To inspect Spring startup steps, construct the application using:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

This is an illustrative alternative to constructing `SpringApplication`, requiring import `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`.

With `spring-boot-starter-actuator`, enable the endpoint in the measurement environment:

~~~properties
management.endpoints.web.exposure.include=health,info,startup
~~~

Once the endpoint is ready:

~~~bash
curl -sS http://localhost:8080/actuator/startup
~~~

In Spring Boot 3.3, `GET` returns a timeline snapshot; `POST` drains the buffer. Capacity `2048` is just an example and may be too small if the app has many startup steps. Never expose diagnostic startup endpoints publicly in production.

### JFR, Heap, and RSS

Java Flight Recorder helps analyze allocations, GC, and class loading:

~~~bash
java -XX:StartFlightRecording=filename=trial.jfr,duration=60s \
     -jar build/libs/lazy-measure-demo-1.0.0.jar \
     --spring.main.lazy-initialization=true
~~~

Run identical profiling across both variants. Inspect JVM heap info using:

~~~bash
jcmd <PID> GC.heap_info
~~~

Replace `<PID>` with the actual PID. Heap **is not** RSS; use OS/container metrics to monitor total memory. Measure **right at ready, after full warm-up, and under high load** before lowering memory limits.

### HTTP Latency

~~~bash
curl -sS -o /dev/null \
     -w 'HTTP=%{http_code} total=%{time_total}s\n' \
     http://localhost:8080/work
~~~

Use `curl` for single observations, while p95/p99 distributions, concurrency, and throughput require a load-testing tool like k6, Gatling, or JMeter with standardized scenarios.

## 7. Runnable Project: Observing Bean Creation on First Use

This **Spring Boot 3.3.13 / Java 17 / Gradle** example includes a `SlowService` bean simulating ~300 ms initialization cost. The controller injects `ObjectProvider<SlowService>` so the bean is only requested when handling `GET /work`.

`Thread.sleep(300)` here is an **artificial cost for learning purposes**, not a real optimization pattern; production benchmark numbers must come from real services.

### Structure

~~~text
lazy-measure-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/lazymeasure/
│   ├── LazyMeasureApplication.java
│   ├── SlowService.java
│   └── WorkController.java
└── src/test/java/com/example/lazymeasure/
    ├── EagerModeTest.java
    └── LazyModeTest.java
~~~

### `settings.gradle`

~~~groovy
rootProject.name = 'lazy-measure-demo'
~~~

### `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The BOM is declared for both `implementation` and `testImplementation` so dependencies do not need explicit versions. Requires a Gradle version compatible with the Spring Boot 3.3 plugin.

### `LazyMeasureApplication.java`

~~~java
package com.example.lazymeasure;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LazyMeasureApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LazyMeasureApplication.class);

        ApplicationListener<ApplicationReadyEvent> listener = event -> {
            Duration elapsed = event.getTimeTaken();
            System.out.println("MEASURE ready_ms="
                    + (elapsed == null ? "unknown" : elapsed.toMillis()));
        };

        app.addListeners(listener);
        app.run(args);
    }

    @Bean
    SlowService slowService() {
        return new SlowService();
    }
}
~~~

The listener is registered directly before `run`, independent of whether a listener bean is created early.

### `SlowService.java`

~~~java
package com.example.lazymeasure;

public final class SlowService {

    public SlowService() {
        System.out.println("MEASURE slow_service_constructor");
        try {
            Thread.sleep(300);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted during demo init", e);
        }
    }

    public String work() {
        return "OK";
    }
}
~~~

### `WorkController.java`

~~~java
package com.example.lazymeasure;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {

    private final ObjectProvider<SlowService> provider;

    public WorkController(ObjectProvider<SlowService> provider) {
        this.provider = provider;
    }

    @GetMapping("/work")
    public String work() {
        return provider.getObject().work();
    }
}
~~~

`ObjectProvider` only requests `SlowService` when `getObject()` is invoked. Injecting `SlowService` directly into an eager controller can cause the depended-on bean to be created when the controller is created, skewing the scenario under test.

### Build

~~~bash
./gradlew clean test bootJar
~~~

In PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

With the project name and version above, the executable JAR is normally `build/libs/lazy-measure-demo-1.0.0.jar`; check the actual file if customized.

### Running the Eager Baseline

Terminal 1:

~~~bash
java -Xms256m -Xmx512m \
     -jar build/libs/lazy-measure-demo-1.0.0.jar \
     --server.port=8080 \
     --spring.main.lazy-initialization=false
~~~

Once ready, terminal 2:

~~~bash
curl -sS -o /dev/null -w 'A_FIRST=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work

curl -sS -o /dev/null -w 'A_WARM=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work
~~~

In eager mode, the `MEASURE slow_service_constructor` marker typically appears **before** `MEASURE ready_ms=...`.

### Running the Lazy Variant

Stop JVM A completely, then start **a fresh JVM** with the same artifact, JVM args, and port:

~~~bash
java -Xms256m -Xmx512m \
     -jar build/libs/lazy-measure-demo-1.0.0.jar \
     --server.port=8080 \
     --spring.main.lazy-initialization=true
~~~

After ready:

~~~bash
curl -sS -o /dev/null -w 'B_FIRST=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work

curl -sS -o /dev/null -w 'B_WARM=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work
~~~

In lazy mode, the constructor marker typically appears **after** ready, when the first request calls `getObject()`. In both modes, when successful, the endpoint returns HTTP 200 with body:

~~~text
OK
~~~

There are no fixed `ready_ms` or latency numbers: JVM, infrastructure, resources, and overhead affect actual times. Do not treat the 300 ms sleep as a real production benchmark result.

**Windows PowerShell 5.1:** `curl` can be an alias; use `curl.exe`. Avoid mixing shell quoting styles when writing official metric-collection scripts.

## 8. Automated Testing for Both Eager and Lazy

`@SpringBootTest` verifies functional correctness, not cold JAR startup benchmarks. The two tests below use JUnit 5 and `spring-boot-starter-test` already included in the build.

### `EagerModeTest.java`

~~~java
package com.example.lazymeasure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.main.lazy-initialization=false")
class EagerModeTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void firstAndWarmRequestsWork() {
        assertEquals("OK", rest.getForObject("/work", String.class));
        assertEquals("OK", rest.getForObject("/work", String.class));
    }
}
~~~

### `LazyModeTest.java`

~~~java
package com.example.lazymeasure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.main.lazy-initialization=true")
class LazyModeTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void firstAndWarmRequestsWork() {
        assertEquals("OK", rest.getForObject("/work", String.class));
        assertEquals("OK", rest.getForObject("/work", String.class));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

These tests confirm the endpoint returns the right results in both modes. They **do not prove fast startup or SLO-compliant p99**, because test context caching, Gradle/JUnit, and test JVMs differ from running the real JAR. Avoid directly injecting `SlowService` into tests if you want to observe the uninitialized bean before a request, since the test itself can force early creation.

## 9. Configuration Errors May Surface Only on First Use

A critical bean missing a property, dependency, or configuration may fail at startup when eager, yet be deferred when lazy. Conceptual example:

~~~text
Bean required partner API credentials
  Eager: bean created during refresh -> detects missing config -> startup FAIL
  Lazy: context READY -> first request needs bean -> detects missing config -> request FAIL
~~~

Not every error is deferred: errors in `Environment`, initializers, migrations, or mandatory early infrastructure can still fail startup immediately.

### Controlled Failure Scenario

1. In staging, intentionally omit a mandatory property on a bean with a clear access path.
2. Start in eager mode and record when the error appears.
3. Start in lazy mode; if the app reaches ready, explicitly **invoke the exact branch using that bean**.
4. Inspect the exception, HTTP status, whether logs leak secrets, and whether readiness protected traffic.
5. Restore valid configuration and repeat both modes.

If a bean **must be valid before accepting traffic**, consider `@Lazy(false)` on that bean or validating before readiness via an intentional startup step.

Example bean kept eager under global lazy:

~~~java
@Component
@Lazy(false)
public class CriticalConfigValidator {
    public CriticalConfigValidator() {
        // Validate mandatory local configuration.
    }
}
~~~

This is illustrative code requiring `org.springframework.stereotype.Component` and `org.springframework.context.annotation.Lazy` imports. Avoid lengthy I/O in constructors; use a runner or appropriate readiness check if external dependencies must be verified.

## 10. Readiness and Auto-Scaling

Spring Boot emits `ApplicationReadyEvent` after runners, then publishes `ReadinessState.ACCEPTING_TRAFFIC`. Under lazy mode, however, an instance can report ready while several critical beans **have not yet been created or exercised**.

~~~text
Kubernetes/Autoscaler adds instance
  -> app reaches ready quickly
  -> instance receives traffic
  -> multiple initial requests trigger lazy bean
  -> CPU/GC spike, high latency, or init error
  -> subsequent requests become warm
~~~

Test **a fresh instance under realistic load**, not only startup on an idle machine. Measure concurrent cold requests and p95/p99 during scale-out. A lazy singleton is created once, yet multiple requests can wait together on its creation, spiking tail latency.

An Actuator readiness probe, when configured:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

does not initialize all business beans by itself. If using warm-up, run it before traffic arrives and avoid non-idempotent side effects (charging payments, deleting data, sending real emails). Or keep critical paths eager so they are ready before readiness.

## 11. Memory Must Be Measured After Warm-Up

Lazy mode can reduce RAM right at ready because many beans have not been created yet, yet RAM after exercising all paths can climb back near eager levels. Capture three checkpoints:

1. Immediately after ready, before sending business traffic.
2. After traversing all critical branches to warm them up.
3. Under steady load and peak load.

Measure heap used/committed, RSS, allocations, and GC pauses. Heap does not equal total RSS. Never lower `-Xmx` or container memory limits based on a snapshot taken right at ready. When a traffic wave instantiates many lazy beans together, allocation and GC can spike rapidly.

## 12. Pre-Production Testing Checklist

| Layer | Action Needed | Acceptance Criterion |
| --- | --- | --- |
| Unit/integration | Test both modes, dependencies/config/profiles | Functionally correct |
| Startup smoke | Run real JAR/image, measure ready/probes | No errors |
| First-use paths | Invoke rare endpoints, jobs, consumers | No init errors / within cold SLO |
| Failure injection | Missing/invalid config on critical beans | Failure caught appropriately |
| Load/soak | Cold concurrency, p95/p99, memory/GC | Within limits |
| Staging | Same JDK/image/probes as production | Reproducible results |
| Canary | Small instance/traffic share with dedicated labels | Alerts/metrics healthy |
| Rollback drill | Revert to eager, verify outcome | No abnormal disruption |

Commonly missed paths to test: login, persistence/transactions, Redis, HTTP clients, scheduled jobs, queue listeners, serializers, feature flags, report exports, and shutdown. One working endpoint does not prove all lazy beans in the application work.

## 13. Rollout and Rollback Rules

**Accept** when startup improves meaningfully across repeated runs, no config errors are masked, cold/warm latency and resources meet SLOs, and readiness and shutdown hold up in load tests and canary.

**Tune** when startup is good yet certain cold paths are too slow: apply `@Lazy(false)` to critical beans, safe pre-readiness warm-up, or selective laziness, then re-measure.

**Reject or roll back** if first-use errors emerge, p99/5xx rises, memory limits are exceeded, autoscaling bottlenecks occur, or readiness admits traffic while mandatory functionality is broken.

Rollback configuration:

~~~properties
spring.main.lazy-initialization=false
~~~

then deploy/restart the JVM. Changing the property inside a running process **does not revert already-initialized beans to an uncreated state**. Prepare dashboards separating eager vs. lazy canary instances, rollback thresholds, and traffic-draining procedures before launching a canary in production.

## 14. Common Mistakes

- **Measuring startup only once:** CPU/cache/JIT/network/GC noise makes single measurements unstable.
- **Comparing mismatched milestones:** `ApplicationStartedEvent` is not `ApplicationReadyEvent`.
- **Sending a few warm requests and assuming cold was measured:** a fresh JVM is needed for every cold sample.
- **Treating one `curl` as p99:** requires a sample distribution and a load generator.
- **Checking only green health:** lazy business beans may still remain uncreated.
- **Ignoring late bean-creation errors:** startup passes yet the first request fails.
- **Skipping concurrent cold tests:** multiple requests can contend waiting on bean creation.
- **Omitting jobs/queues from tests:** a bean may only be requested hours after startup.
- **Lowering memory limits too early:** RAM grows after warm-up.
- **Assuming all beans are lazy:** dependent eager singletons and infrastructure can force early creation.
- **Using `gradle test` time to compare JAR startup:** test environments differ from production.
- **Having no rollback:** errors discovered after taking traffic become hard to recover from.
- **Exposing startup diagnostic endpoints publicly:** startup data can reveal internal structure.

## 15. Self-Check

1. **What is the default of `spring.main.lazy-initialization`?** `false`.
2. **Does lazy eliminate bean creation cost?** No, it mainly defers it to first request.
3. **Can a bean marked lazy still be created at startup?** Yes, if another eager bean or the framework needs it.
4. **Does `ApplicationReadyEvent` prove all beans are ready?** No.
5. **What else must be measured besides `T_ready`?** Cold/warm latency, p95/p99, errors, memory/GC, readiness, and concurrency.
6. **Why does measuring cold require a fresh JVM?** Singletons may already be created after first use.
7. **Can a single request serve as p99?** No.
8. **If a lazy bean's config error surfaces at first use, how do you guard against it?** Test that branch, warm up before readiness, or keep critical beans eager.
9. **Does low RSS at ready mean enough RAM for production?** No; measure after warm-up and at peak.
10. **What does `/actuator/startup` require?** `BufferingApplicationStartup` and Actuator properly enabled/exposed.
11. **Is lazy always beneficial for autoscaling?** No; cold instances can be slow when admitting traffic.
12. **How do you roll back the lazy flag?** Start fresh processes with `spring.main.lazy-initialization=false`.
13. **Why test scheduled jobs?** A lazy bean may only be created when the first job runs.
14. **Why keep A/B conditions identical?** So differences can be attributed to laziness rather than CPU/JDK/configuration.

**Conclusion:** deciding to enable lazy initialization must rest on **controlled A/B measurements**, **cold requests on fresh JVMs**, **first-use testing of all critical branches**, **post-warm-up RAM**, **readiness under load**, and **a canary with rollback**. Shortening startup only to push errors or tail latency onto users is not a successful operational optimization.

### References

- Spring Boot 3.3 — `SpringApplication` (Lazy Initialization, Application Events, Application Startup tracking): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ApplicationReadyEvent.getTimeTaken()` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3.13 — Actuator startup endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Actuator endpoints/probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Framework 6.1 — `@Lazy` API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework 6.1 — Lazy Beans: https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html
- Spring Boot 3.3 — Gradle managing dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
