# Testing ApplicationRunner, Readiness, and Application Lifecycle in Spring Boot

## 1. Purpose and Real-World Problem

In Spring Boot, finishing bean initialization does not mean the application is **ready to receive traffic**. An instance may already have an open HTTP port while it is still:

- Loading data or warming up critical caches.
- Validating configurations, locks, schemas, or checkpoints.
- Starting mandatory consumers or background processors.
- Checking a critical dependency before serving traffic.
- Completing startup preparation steps inside `ApplicationRunner`/`CommandLineRunner`.

If a test only asserts that the Spring ApplicationContext loads, it misses startup ordering, readiness state, runner failures, or improper cleanup when the context closes.

This lesson aims to verify all three layers thoroughly:

1. **Runners:** `ApplicationRunner` runs with exact arguments, follows `@Order`, and runs once per `SpringApplication` startup.
2. **Readiness:** after refresh, the application is live yet **not accepting traffic** while runners are executing; only after runners succeed does Boot mark it ready.
3. **Lifecycle/observability:** verify `ApplicationStartedEvent`, `ApplicationReadyEvent`, `ApplicationFailedEvent`, `AvailabilityChangeEvent`, Actuator health probes, and context shutdown cleanup.

In particular, distinguish these four concepts:

~~~text
Spring context refreshed
      != ApplicationStartedEvent itself means ready
      != ApplicationReadyEvent has already changed readiness
      != actual readiness probe is UP
      != external traffic routing by Kubernetes is guaranteed
~~~

### Learning Outcomes

After this lesson, you will be able to:

- Read and write `ApplicationRunner`, `CommandLineRunner`, and `ApplicationArguments`.
- Know the sequence Started → Liveness CORRECT → runners → Ready → Readiness ACCEPTING.
- Explain `ApplicationAvailability`, `ReadinessState`, and `LivenessState`.
- Test `ApplicationRunner` with unit tests and real `SpringApplication` integration tests.
- Test HTTP readiness 200/503 via `/actuator/health/readiness`.
- Test startup failures without crashing the entire `@SpringBootTest` before test methods execute.
- Distinguish graceful shutdown, lifecycle callbacks, and the Spring TestContext cache.
- Avoid fire-and-forget startup tasks, `@BeforeEach` traps, and non-idempotent tasks across multiple replicas.
- Know when to use Actuator startup metrics, `startupProbe`, `readinessProbe`, and `livenessProbe`.

## 2. Spring Boot 3.5 Event Sequence

According to the Spring Boot 3.5 Reference:

~~~text
SpringApplication.run(args)
  |
  +-- ApplicationStartingEvent
  +-- ApplicationEnvironmentPreparedEvent
  +-- ApplicationContextInitializedEvent
  +-- ApplicationPreparedEvent
  +-- Context refresh
  |     +-- ContextRefreshedEvent
  |     +-- WebServerInitializedEvent (if web server present)
  |
  +-- ApplicationStartedEvent
  +-- AvailabilityChangeEvent(LivenessState.CORRECT)
  |
  +-- ApplicationRunner / CommandLineRunner
  |     +-- ordered runners run here
  |
  +-- ApplicationReadyEvent
  +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
  |
  +-- SpringApplication.run returns ApplicationContext
~~~

If an error occurs during startup, Spring Boot can emit `ApplicationFailedEvent` and run failure handling; do not expect the Ready event after a failed startup.

**One crucial detail to verify:** `ApplicationReadyEvent` is emitted **before** the availability event signaling `ReadinessState.ACCEPTING_TRAFFIC`. Inside a listener for `ApplicationReadyEvent` itself, do not assert readiness is already ACCEPTING solely because the event name contains Ready. Check readiness after `SpringApplication.run`, inside the test body after startup, or by listening directly to the readiness accepting event.

### 2.1 Which Events Can Be Observed via @Component?

Very early events like `ApplicationStartingEvent` happen before context/bean listeners are created. A `@EventListener` bean normally **cannot** observe all early events.

To record events prior to bean creation, register listeners on `SpringApplication`:

~~~java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>)
                event -> recorder.record("starting"));
~~~

This is an illustrative snippet requiring real classes and imports. In the runnable project below, `LifecycleTrace` is a bean listening only to events **after the context refreshes**; the dedicated failure test registers listeners directly on `SpringApplication`.

### 2.2 ContextRefreshedEvent Differs from ApplicationStartedEvent

`ContextRefreshedEvent` is Spring Framework's foundational event for a refreshed ApplicationContext. `ApplicationStartedEvent` is Boot's event emitted after refresh, before runners. Projects with parent/child contexts can produce multiple `ContextRefreshedEvent` instances; do not treat them unconditionally as substitutes for Ready events.

## 3. Liveness and Readiness: Two Different Meanings

| State | Meaning | Infrastructure Response |
| --- | --- | --- |
| `LivenessState.CORRECT` | Instance is not internally broken to the point of needing a restart | Usually keep instance running |
| `LivenessState.BROKEN` | Instance cannot recover on its own | May restart when liveness probe fails |
| `ReadinessState.REFUSING_TRAFFIC` | Not ready yet or should not receive new traffic | Temporarily stop routing new requests |
| `ReadinessState.ACCEPTING_TRAFFIC` | Ready to serve | Can receive requests |

During default startup:

| Phase | Liveness | Readiness |
| --- | --- | --- |
| Starting | BROKEN | REFUSING_TRAFFIC |
| Started, before or during runners | CORRECT | REFUSING_TRAFFIC |
| Ready, after final availability state | CORRECT | ACCEPTING_TRAFFIC |

**Never equate liveness with readiness.** An instance can be running healthily while still warming up or overloaded and temporarily refusing traffic.

Similarly, if a shared database goes down, marking every instance BROKEN can trigger Kubernetes mass restarts, worsening the outage. Readiness can depend on truly essential external systems, though you must consider scenarios where all replicas lose the dependency simultaneously.

### 3.1 ApplicationAvailability

Spring Boot provides an injectable `ApplicationAvailability`:

~~~java
ReadinessState readiness =
        availability.getReadinessState();

LivenessState liveness =
        availability.getLivenessState();

AvailabilityChangeEvent<ReadinessState> event =
        availability.getLastChangeEvent(ReadinessState.class);
~~~

This snippet assumes an `availability` field. Inside a runner invoked by `SpringApplication`, the default readiness state is `REFUSING_TRAFFIC`; after startup succeeds and Boot emits the state change, it becomes `ACCEPTING_TRAFFIC`.

Some generic state query methods can return null before any event occurs; convenience methods carry default semantics. When checking pre-start phases, check the exact version/API rather than inferring from null that the app is healthy.

### 3.2 Publishing Readiness Changes

~~~java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC);

// When the instance recovers:
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.ACCEPTING_TRAFFIC);
~~~

This publishes the event to a specific context. Tests must restore the state in a `finally` block if the context is cached and reused.

## 4. ApplicationRunner vs CommandLineRunner

Both interfaces are discovered and invoked by `SpringApplication` after Started and before Ready.

~~~java
@Component
@Order(10)
class PrepareIndexRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments arguments) {
        // Handle startup tasks.
    }
}
~~~

~~~java
@Component
@Order(20)
class VerifySettingsRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Raw command-line arguments.
    }
}
~~~

These two snippets are illustrative only and not part of the mini-project below. Key points:

- `ApplicationRunner` receives `ApplicationArguments`, supporting parsed option and non-option args.
- `CommandLineRunner` receives raw argument strings.
- `@Order`/`Ordered` defines runner execution order; file declaration order or component scan order is not a contract.
- Runners run **each time a new `SpringApplication` context starts**, not once globally across a JVM or cluster.
- If a runner throws an exception, Boot startup does not complete normally.
- Use runners for initialization that genuinely must finish before receiving traffic.

### 4.1 ApplicationArguments

Given args:

~~~text
--demo.mode=qa
note.txt
--feature.flag=a
--feature.flag=b
~~~

Spring Boot's parser provides:

~~~java
args.getOptionValues("demo.mode");   // ["qa"]
args.getOptionValues("feature.flag");// ["a", "b"]
args.getNonOptionArgs();             // ["note.txt"]
~~~

When an option is absent, `getOptionValues` can return null; code should check null/empty. When arguments can contain arbitrary secrets, **do not log raw arguments** to observability; extract only harmless fields such as mode or test inputs.

### 4.2 @Order Does Not Dictate Bean Creation Order

An `@Order(10)` runner may be instantiated after another bean in the Spring context, yet still be invoked **before** an `@Order(20)` runner at startup runner execution. Tests must not infer constructor/`@PostConstruct` ordering from `@Order`.

## 5. Runners and Readiness: Avoid Fire-and-Forget

Runners help because Spring Boot **only emits Ready once runners return**. However, if a runner spawns a background future and returns immediately:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(() -> preloadCriticalData());
    // Runner returns; Boot can immediately mark ready.
}
~~~

this is a bug when preloading is a prerequisite for traffic.

A controlled alternative:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    Future<?> future = executor.submit(this::preloadCriticalData);
    try {
        future.get(20, TimeUnit.SECONDS);
    } catch (TimeoutException timeout) {
        future.cancel(true);
        throw new IllegalStateException(
                "Critical startup timeout", timeout);
    }
}
~~~

Both snippets are standalone illustrations requiring an executor/method/imports. `Future.get(timeout)` bounds the wait, while `cancel(true)` only sends an interrupt request; the worker may still continue if I/O is non-cooperative. Use deadlines and resource-specific timeouts accordingly.

**Subtle trap:** If a runner publishes `REFUSING_TRAFFIC` and **returns immediately** while async warmup is incomplete, Boot publishes `ACCEPTING_TRAFFIC` after Ready and can overwrite the earlier state. Do not treat an early REFUSING event as a permanent sticky lock. Finish critical initialization before the runner returns, or design an explicit readiness coordinator.

## 6. Spring Boot Actuator Probes

Spring Boot provides health groups:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Requires `spring-boot-starter-actuator`. On Kubernetes, probes may auto-enable; outside that environment, configure explicitly:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

In the example, default status mappings apply:

| Availability State | Health Group Status | HTTP |
| --- | --- | --- |
| Readiness ACCEPTING_TRAFFIC | UP | 200 |
| Readiness REFUSING_TRAFFIC | OUT_OF_SERVICE | 503 |
| Liveness CORRECT | UP | 200 |
| Liveness BROKEN | DOWN | 503 |

Mappings can be customized; tests should follow the actual config.

**Do not call generic `/actuator/health` and claim readiness is valid**: global health and the readiness group can contain different sets of indicators.

### 6.1 Probes Do Not Automatically Test All Dependencies

Spring Boot does not automatically include every DB/Redis/external service in readiness/liveness groups. Add only essential health indicators, keeping in mind that a shared dependency outage can pull all instances out of routing.

Liveness **should not** depend on a remote API or shared database: infrastructure could restart every pod while the dependency remains broken.

### 6.2 Main Port vs. Management Port

If Actuator runs on a separate port, probes can report UP even if the main HTTP connector fails. Spring Boot supports:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

to expose `/livez` and `/readyz` on the **main application port**. The runnable lesson keeps Actuator on the same default port.

### 6.3 Kubernetes startupProbe

A startup probe protects services with long startup times from being killed too early by liveness policies. Readiness tells whether to route traffic; liveness tells whether to restart. Do not use a single probe for all purposes.

## 7. Three-Tier Testing Strategy

| Tier | Verifies | Does Not Prove |
| --- | --- | --- |
| Runner unit test with DefaultApplicationArguments | Argument parsing, branching, error handling | SpringApplication calls runner at the right phase |
| `@SpringBootTest(webEnvironment=NONE)` | Runner ordering, lifecycle events, availability state | HTTP/actuator endpoints |
| `@SpringBootTest(RANDOM_PORT)` + Actuator | HTTP readiness/liveness 200/503 | Multi-node Kubernetes ingress routing |
| Isolated SpringApplication test | Runner failure, FailedEvent, context close | All production beans naturally present |
| Kubernetes/staging test | Probe thresholds, routing, rolling updates | Replacing app unit/integration tests |

**Do not treat `ApplicationContextRunner` as proof of the full `SpringApplication` lifecycle.** It is excellent for testing auto-configuration/conditions and bean graphs, yet does not execute the Boot Started → runner → Ready sequence like `SpringApplication.run`.

### 7.1 Spring TestContext Cache

`@SpringBootTest` can cache contexts across test methods/classes with equivalent configurations. `ApplicationRunner` has already run **before JUnit `@BeforeEach`**, and does not re-run when each test method starts.

Therefore, if a test does:

~~~java
@BeforeEach
void resetHistory() {
    lifecycleTrace.clear(); // Wipes startup evidence.
}
~~~

and expects the test body to see startup event/runner records, it causes a false failure. This lesson retains the trace in the bean across the test class without resetting. When each method requires a fresh startup, use targeted `@DirtiesContext` (costly) or create an isolated `SpringApplication` per test.

### 7.2 Fixtures Needed by Runners Must Exist Before Context Startup

Do not seed data needed by a runner inside `@BeforeEach`, because the runner runs before `@BeforeEach`. Seed via database/container initialization prior to context load, auto-configuration/test-specific beans, or extract startup logic into a service and unit-test it separately.

## 8. Java 17+ / Spring Boot 3.5.x Project

The example consists of **5 production classes** and **5 test classes**, totaling **11 JUnit Jupiter methods**, requiring no DB/Docker/remote services.

~~~text
lifecycle-readiness-demo/
  settings.gradle
  build.gradle
  src/main/java/example/lifecycle/
    LifecycleDemoApplication.java
    LifecycleTrace.java
    WarmupStatus.java
    StartupArgumentsRunner.java
    CacheWarmupRunner.java
  src/test/java/example/lifecycle/
    RunnerUnitTest.java
    BootLifecycleTest.java
    ReadinessHttpTest.java
  src/test/java/example/isolated/
    RunnerFailureTest.java
    ShutdownLifecycleTest.java
~~~

**Package note:** isolated tests live in `example.isolated` — outside the base package `example.lifecycle`. The two nested `@SpringBootConfiguration` classes in the negative tests will not be accidentally picked up by the main application's component scan and break all `@SpringBootTest` classes.

### 8.1 settings.gradle

~~~groovy
rootProject.name = 'lifecycle-readiness-demo'
~~~

### 8.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
~~~

Versions are pinned for practice, **not claimed as the latest**. `starter-web` provides the embedded server and Jackson; `actuator` provides health groups; `starter-test` includes JUnit, SpringBootTest, and TestRestTemplate. A Gradle wrapper must be generated or a compatible Gradle installation used.

## 9. LifecycleDemoApplication.java

File `src/main/java/example/lifecycle/LifecycleDemoApplication.java`:

~~~java
package example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }
}
~~~

The lesson places `@SpringBootApplication` in package `example.lifecycle`, so services/runners/listeners in this package are scanned.

## 10. LifecycleTrace.java

File `src/main/java/example/lifecycle/LifecycleTrace.java`:

~~~java
package example.lifecycle;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class LifecycleTrace {

    private final List<String> events =
            new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        record("started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        record("ready:event");
    }

    @EventListener
    public void onAvailability(AvailabilityChangeEvent<?> event) {
        if (event.getState() instanceof LivenessState state) {
            record("liveness:" + state);
        }
        if (event.getState() instanceof ReadinessState state) {
            record("readiness:" + state);
        }
    }
}
~~~

`CopyOnWriteArrayList` is sufficient for the sample trace. It needs no static global state; each Spring ApplicationContext gets its own trace bean.

In production, a custom asynchronous `ApplicationEventMulticaster` can alter listener ordering/execution; this lesson relies on Boot's default synchronous event delivery and the Spring Boot 3.5 timeline.

## 11. WarmupStatus.java

File `src/main/java/example/lifecycle/WarmupStatus.java`:

~~~java
package example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Component;

@Component
public class WarmupStatus {

    private final AtomicBoolean initialized =
            new AtomicBoolean();

    public void markInitialized() {
        initialized.set(true);
    }

    public boolean isInitialized() {
        return initialized.get();
    }
}
~~~

`WarmupStatus` merely simulates the outcome of a critical startup task, with no remote API calls. In a real system, if warmup can fail, propagate exceptions, set deadlines, and record metrics/failure reasons.

## 12. StartupArgumentsRunner.java

File `src/main/java/example/lifecycle/StartupArgumentsRunner.java`:

~~~java
package example.lifecycle;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class StartupArgumentsRunner implements ApplicationRunner {

    private final LifecycleTrace trace;

    public StartupArgumentsRunner(LifecycleTrace trace) {
        this.trace = trace;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> modes = args.getOptionValues("demo.mode");

        String mode = modes == null || modes.isEmpty()
                ? "default"
                : modes.get(0);

        String positional =
                String.join(",", args.getNonOptionArgs());

        trace.record("runner:args:" + mode + ":" + positional);
    }
}
~~~

With args `--demo.mode=qa note.txt`, expected trace:

~~~text
runner:args:qa:note.txt
~~~

Without options, trace:

~~~text
runner:args:default:
~~~

These lines are expected trace strings, not stdout from a build run. `@Order(10)` ensures this runner executes before `@Order(20)` during the same `SpringApplication` startup.

## 13. CacheWarmupRunner.java

File `src/main/java/example/lifecycle/CacheWarmupRunner.java`:

~~~java
package example.lifecycle;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class CacheWarmupRunner implements ApplicationRunner {

    private final LifecycleTrace trace;
    private final WarmupStatus status;
    private final ApplicationAvailability availability;

    public CacheWarmupRunner(
            LifecycleTrace trace,
            WarmupStatus status,
            ApplicationAvailability availability) {
        this.trace = trace;
        this.status = status;
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) {
        trace.record("runner:warmup:"
                + availability.getLivenessState()
                + ":" + availability.getReadinessState());

        // Synchronous warmup finishes before returning.
        status.markInitialized();
    }
}
~~~

In the default lifecycle, at the moment the runner executes:

~~~text
runner:warmup:CORRECT:REFUSING_TRAFFIC
~~~

Meaning the Spring context is live but not yet ready. After the runners, Boot emits `ApplicationReadyEvent` followed by `ReadinessState.ACCEPTING_TRAFFIC`. In production, the method must complete the real critical task before marking initialized.

## 14. RunnerUnitTest.java: 2 Unit Tests

File `src/test/java/example/lifecycle/RunnerUnitTest.java`:

~~~java
package example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RunnerUnitTest {

    @Test
    void parsesOptionsAndPositionalArguments() {
        LifecycleTrace trace = new LifecycleTrace();
        StartupArgumentsRunner runner =
                new StartupArgumentsRunner(trace);

        runner.run(new DefaultApplicationArguments(
                "--demo.mode=unit", "input.csv"));

        assertEquals(
                "runner:args:unit:input.csv",
                trace.snapshot().get(0));
    }

    @Test
    void absentOptionUsesDefault() {
        LifecycleTrace trace = new LifecycleTrace();
        StartupArgumentsRunner runner =
                new StartupArgumentsRunner(trace);

        runner.run(new DefaultApplicationArguments());

        assertEquals(
                "runner:args:default:",
                trace.snapshot().get(0));
    }
}
~~~

Contains **2 JUnit methods**. Does not start `SpringApplication`, so these only check runner argument parsing/defaults. To prove Spring Boot invokes runners at the right time, the integration tests below are needed.

## 15. BootLifecycleTest.java: 4 Tests in a Real Spring Boot Context

File `src/test/java/example/lifecycle/BootLifecycleTest.java`:

~~~java
package example.lifecycle;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    args = {"--demo.mode=qa", "note.txt"})
class BootLifecycleTest {

    @Autowired LifecycleTrace trace;
    @Autowired WarmupStatus warmup;
    @Autowired ApplicationAvailability availability;

    @Test
    void eventSequenceIncludesRunnerBeforeReady() {
        List<String> events = trace.snapshot();

        List<String> ordered = List.of(
                "started",
                "liveness:CORRECT",
                "runner:args:qa:note.txt",
                "runner:warmup:CORRECT:REFUSING_TRAFFIC",
                "ready:event",
                "readiness:ACCEPTING_TRAFFIC");

        int previous = -1;
        for (String expected : ordered) {
            int current = events.indexOf(expected);
            assertTrue(current > previous,
                    () -> "Wrong startup order for "
                            + expected + " in " + events);
            previous = current;
        }
    }

    @Test
    void finalAvailabilityIsLiveAndReady() {
        assertEquals(LivenessState.CORRECT,
                availability.getLivenessState());
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
        assertNotNull(availability.getLastChangeEvent(
                ReadinessState.class));
        assertTrue(warmup.isInitialized());
    }

    @Test
    void bootForwardsArgumentsToApplicationRunner() {
        assertTrue(trace.snapshot().contains(
                "runner:args:qa:note.txt"));
    }

    @Test
    void eachRunnerRunsOnceForThisContext() {
        long argumentRuns = trace.snapshot().stream()
                .filter("runner:args:qa:note.txt"::equals)
                .count();
        long warmupRuns = trace.snapshot().stream()
                .filter(e -> e.startsWith("runner:warmup:"))
                .count();

        assertEquals(1L, argumentRuns);
        assertEquals(1L, warmupRuns);
    }
}
~~~

Contains **4 tests**. Do not reset `trace` in `@BeforeEach` because startup already happened before JUnit test methods run.

### Why Check Order via a Subsequence?

A real application can emit additional listener and lifecycle events beyond those recorded here. The test checks the relative order of **required milestones**, rather than hardcoding every event that frameworks or providers might add.

### What Does @SpringBootTest(args=...) Do?

`args` on `@SpringBootTest` are passed into `SpringApplication` when the test context starts. `ApplicationRunner` receives the corresponding `ApplicationArguments`. That differs from calling the method directly with raw `String[]` in a unit test.

## 16. ReadinessHttpTest.java: 3 HTTP Readiness/Liveness Tests

File `src/test/java/example/lifecycle/ReadinessHttpTest.java`:

~~~java
package example.lifecycle;

import java.util.Objects;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "management.endpoint.health.probes.enabled=true")
class ReadinessHttpTest {

    @LocalServerPort int port;

    @Autowired TestRestTemplate http;
    @Autowired ObjectMapper mapper;
    @Autowired ApplicationContext context;
    @Autowired ApplicationAvailability availability;

    private ResponseEntity<String> probe(String name) {
        return http.getForEntity(
                "http://localhost:" + port
                + "/actuator/health/" + name,
                String.class);
    }

    private String status(ResponseEntity<String> response)
            throws Exception {
        String json = Objects.requireNonNull(response.getBody());
        return mapper.readTree(json).path("status").asText();
    }

    @Test
    void readinessAndLivenessAreUpAfterStartup()
            throws Exception {
        ResponseEntity<String> ready = probe("readiness");
        ResponseEntity<String> live = probe("liveness");

        assertEquals(200, ready.getStatusCode().value());
        assertEquals("UP", status(ready));
        assertEquals(200, live.getStatusCode().value());
        assertEquals("UP", status(live));

        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
        assertEquals(LivenessState.CORRECT,
                availability.getLivenessState());
    }

    @Test
    void refusingTrafficMapsTo503ThenRestore()
            throws Exception {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        try {
            ResponseEntity<String> ready = probe("readiness");

            assertEquals(ReadinessState.REFUSING_TRAFFIC,
                    availability.getReadinessState());
            assertEquals(503, ready.getStatusCode().value());
            assertEquals("OUT_OF_SERVICE", status(ready));
        } finally {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
        }
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
    }

    @Test
    void readinessRefusalDoesNotBreakLiveness()
            throws Exception {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        try {
            ResponseEntity<String> ready = probe("readiness");
            ResponseEntity<String> live = probe("liveness");

            assertEquals(503, ready.getStatusCode().value());
            assertEquals("OUT_OF_SERVICE", status(ready));
            assertEquals(200, live.getStatusCode().value());
            assertEquals("UP", status(live));
            assertEquals(LivenessState.CORRECT,
                    availability.getLivenessState());
        } finally {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

Contains **3 integration tests**. `RANDOM_PORT` avoids hardcoding 8080. `TestRestTemplate` hits real localhost, and `ObjectMapper` parses JSON status. The refusing-traffic tests publish the event to the ApplicationContext and restore it in `finally`.

**Do not enable parallel execution** for tests mutating the same availability bean/context, or two methods could overwrite each other's state. For the same reason, never skip restoring: Spring TestContext may reuse the context across other test classes.

## 17. RunnerFailureTest.java: When a Startup Runner Throws an Exception

If you create a runner that always throws inside a regular `@SpringBootTest`, the TestContext fails to load **before the test body runs**, leaving nowhere clean to assert. Instead, construct a minimal `SpringApplication` inside a dedicated JUnit test.

File `src/test/java/example/isolated/RunnerFailureTest.java`:

~~~java
package example.isolated;

import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RunnerFailureTest {

    @SpringBootConfiguration
    static class BrokenApp {
        @Bean
        ApplicationRunner failingRunner() {
            return args -> {
                throw new IllegalStateException(
                        "critical warmup failed");
            };
        }
    }

    @Test
    void startupFailureEmitsFailedButNotReady() {
        AtomicBoolean started = new AtomicBoolean();
        AtomicBoolean ready = new AtomicBoolean();
        AtomicBoolean failed = new AtomicBoolean();

        SpringApplication app =
                new SpringApplication(BrokenApp.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setLogStartupInfo(false);
        app.addListeners(
            (ApplicationListener<ApplicationStartedEvent>)
                event -> started.set(true),
            (ApplicationListener<ApplicationReadyEvent>)
                event -> ready.set(true),
            (ApplicationListener<ApplicationFailedEvent>)
                event -> failed.set(true));

        RuntimeException exception = assertThrows(
                RuntimeException.class,
                () -> app.run(
                        "--spring.main.banner-mode=off",
                        "--logging.level.root=OFF"));

        assertTrue(started.get());
        assertFalse(ready.get());
        assertTrue(failed.get());
        assertTrue(hasMessage(
                exception, "critical warmup failed"));
    }

    private static boolean hasMessage(
            Throwable error, String expected) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {
            String message = current.getMessage();
            if (message != null && message.contains(expected)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Contains **1 test**. The runner fails after the Started event; no Ready event occurs; Boot publishes the Failed event. The test code does not call `System.exit` and does not break other full-context tests. The nested config sits in `example.isolated`, outside the main demo's scan base package.

**Do not assert HTTP 503 after startup failure**: the embedded server may not exist yet or may have been shut down. Asserting events/exceptions is the accurate lifecycle contract.

## 18. ShutdownLifecycleTest.java: Closing Context Cleans Up Resources

Dedicated test for cleanup:

File `src/test/java/example/isolated/ShutdownLifecycleTest.java`:

~~~java
package example.isolated;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ShutdownLifecycleTest {

    static final class CloseProbe implements AutoCloseable {
        final AtomicInteger closes = new AtomicInteger();

        @Override
        public void close() {
            closes.incrementAndGet();
        }
    }

    @SpringBootConfiguration
    static class CloseOnlyApp {
        @Bean
        CloseProbe closeProbe() {
            return new CloseProbe();
        }
    }

    @Test
    void contextCloseInvokesBeanDestroyMethod() {
        SpringApplication app =
                new SpringApplication(CloseOnlyApp.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setLogStartupInfo(false);

        ConfigurableApplicationContext context =
                app.run(
                    "--spring.main.banner-mode=off",
                    "--logging.level.root=OFF");

        CloseProbe probe = context.getBean(CloseProbe.class);
        try {
            assertEquals(0, probe.closes.get());
        } finally {
            context.close();
        }
        assertEquals(1, probe.closes.get());
    }
}
~~~

Contains **1 test**. Spring `@Bean` provides destroy-method inference for `AutoCloseable.close()`; the test owns the context it creates and properly closes it in `finally`.

Never call `context.close()` on a shared `@SpringBootTest` context and expect subsequent tests to keep working; TestContext may be caching that object. To test context shutdown lifecycles, own a dedicated context or use targeted `@DirtiesContext`.

## 19. Total of 11 Tests and How to Run Them

| Test Class | `@Test` | Goal |
| --- | ---: | --- |
| `RunnerUnitTest` | 2 | `ApplicationArguments`/defaults |
| `BootLifecycleTest` | 4 | Event ordering, runner `@Order`, final availability |
| `ReadinessHttpTest` | 3 | HTTP readiness 200/503, liveness independence |
| `RunnerFailureTest` | 1 | `ApplicationFailedEvent` and no Ready |
| `ShutdownLifecycleTest` | 1 | Bean cleanup on `context.close` |
| **Total** | **11** | Unit + Spring startup + HTTP + isolated failures |

Linux/macOS:

~~~bash
./gradlew test --tests example.lifecycle.RunnerUnitTest --tests example.lifecycle.BootLifecycleTest --tests example.lifecycle.ReadinessHttpTest --tests example.isolated.RunnerFailureTest --tests example.isolated.ShutdownLifecycleTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.lifecycle.RunnerUnitTest --tests example.lifecycle.BootLifecycleTest --tests example.lifecycle.ReadinessHttpTest --tests example.isolated.RunnerFailureTest --tests example.isolated.ShutdownLifecycleTest
~~~

Full suite:

~~~bash
./gradlew clean test
~~~

**Expected outcome** by structure: 11 JUnit Jupiter methods PASS on Java 17+/Spring Boot 3.5.x with the exact files and dependencies above. This is a prediction from static code/API review, **not output from an executed Gradle run**. Random ports and startup logs depend on the environment; never hardcode stdout.

### 19.1 Debugging Failing Tests

1. Are you using the right main `@SpringBootApplication` and package scan?
2. Is another nested `@SpringBootConfiguration` accidentally being scanned into the context?
3. Does `@SpringBootTest(args=...)` declare the right option/non-option args?
4. Is `@Order` placed on runner beans recognized by Spring?
5. Was the listener bean created before `ApplicationStartedEvent`?
6. Is there an async custom `ApplicationEventMulticaster` changing callback order?
7. Did `@BeforeEach` wipe out previously recorded startup traces?
8. Which context and state does `ApplicationAvailability` belong to?
9. Is Actuator in dependencies and `probes.enabled=true` in the test environment?
10. Are there custom status/http mappings or security filters on health endpoints?
11. Did the HTTP test restore readiness state after the 503 case?
12. Does the context failure test use an isolated `SpringApplication` rather than breaking the full test context?
13. Does context cleanup respect ownership without corrupting the TestContext cache?

## 20. Things to Avoid in Production Startup

### 20.1 Long-Running Runners Without Deadlines

A runner calling a remote API with an infinite timeout can stall startup forever. Readiness remains REFUSING, yet infrastructure may enforce startup/liveness timeouts. Set deadlines, bounded retries/backoff, and clear fail-startup or degraded policies. Never use `Thread.sleep` to test startup.

### 20.2 Non-Idempotent Data Initialization in Runners

Restarting a `SpringApplication` re-invokes runners. Kubernetes scaling across multiple replicas can run multiple runners **concurrently**. Do not use runners to send emails, process payments, or migrate DBs without idempotency, locks, or proper migration tools.

### 20.3 Ready Event Triggering Critical Async Warmup

~~~java
@EventListener(ApplicationReadyEvent.class)
public void afterReady() {
    executor.execute(this::loadCriticalData);
}
~~~

If `loadCriticalData` is a prerequisite for traffic, this is an anti-pattern: Boot is about to publish ACCEPTING right after the listener returns. Move critical initialization into a runner, or build a readiness coordinator tested for proper ordering.

### 20.4 Putting Every Dependency Check into Liveness

A shared DB outage can cause all pods to restart and trigger a cascading failure. Liveness checks unrecoverable internal process health; readiness checks traffic-serving capability and can include essential dependencies.

## 21. Graceful Shutdown, Readiness, and Resource Lifecycle

During shutdown:

~~~text
Running:
    liveness CORRECT
    readiness ACCEPTING_TRAFFIC

Graceful shutdown:
    readiness REFUSING_TRAFFIC
    server stops accepting new requests
    in-flight requests may complete within grace period

Shutdown complete:
    ApplicationContext closed
    resources destroyed
~~~

Configurable via:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Depending on embedded server and Boot version, rejection/draining details vary. `ShutdownLifecycleTest` only proves `AutoCloseable.close()` is called by Spring when the context closes; **it does not prove HTTP draining**.

To properly test HTTP graceful shutdown, use a dedicated context/embedded server, an in-flight request held by a `CountDownLatch`, close the context from another thread with a deadline, verify readiness and the in-flight response, release the latch, and await termination. Never guess with `Thread.sleep` or hardcode ports.

### 21.1 Resource Ownership in Tests

| Resource | Owner | How to Clean Up |
| --- | --- | --- |
| `@SpringBootTest` ApplicationContext | Spring TestContext | Do not close arbitrarily in tests |
| Isolated `SpringApplication` context | The test itself | Close in `finally` |
| Runner-created custom executor | Application lifecycle | Shutdown/await on context close |
| DB rows created by runners | Database/fixture | Committed cleanup, not `@Rollback` alone |
| Message subscriptions | Listener/container | Stop/dispose in matching lifecycle |
| Warmup HTTP requests | HTTP client | Timeout, close responses |
| Readiness state published by test | Test owning the mutation | Restore event in `finally` |
| Actuator random-port server | Spring TestContext | Context close/destroy |

### 21.2 Thread-Local Transactions and Runners

Test-managed `@Transactional` on the JUnit thread starts **after startup runners have finished**. Test rollback will not automatically erase DB writes that a runner already created and committed earlier. If runners seed data into a shared DB, use dedicated test schemas/containers and explicit cleanup.

## 22. Startup Metrics and Observability

Keep three distinct signal groups in mind:

1. **Spring Boot events:** Starting/Started/Ready/Failed and availability transitions.
2. **Startup timing/steps:** `ApplicationStartup`, `BufferingApplicationStartup`, startup metrics, and the Actuator startup endpoint if configured.
3. **Health probes:** `/actuator/health/liveness` and `/actuator/health/readiness`.

`ApplicationStartup` can measure bean initialization/configuration steps, yet does not by itself prove business warmup completed. Probe status reports published state, without verifying downstream dependencies unless they are configured in the readiness group.

In production, observe:

| Signal | Purpose |
| --- | --- |
| startup duration | Time from launch to ready |
| runner duration/failure | Identify slow or failing critical steps |
| availability transitions | Count of refusing/accepting/broken transitions |
| Actuator probe 200/503 | Observe application state over HTTP |
| failed startup root cause | Diagnose configuration/dependency issues |
| restart count | Detect crash loops |
| shutdown duration | Monitor drain and cleanup |
| side-effect count | Detect runners firing repeatedly across restarts/scaling |
| application instance ID | Distinguish pods/contexts |

Do not log secrets passed via args/environment or health details. Use labels/tags with reasonable cardinality.

### 22.1 Why Not Assert startup < 100ms?

CI runners, local laptops, JDK warmup, filesystems, networks, and classpaths differ. Lifecycle semantic tests should assert **order and states**; startup performance belongs in benchmarks/metrics with matching SLOs and environments.

## 23. Common Testing Mistakes

**1. Running only unit tests on `runner.run` and claiming Spring calls it automatically.**  
Unit tests do not prove lifecycle wiring; add `@SpringBootTest` or `SpringApplication`.

**2. Confusing `ApplicationStartedEvent` with `ApplicationReadyEvent`.**  
Started runs before runners; Ready runs after runners.

**3. Asserting readiness ACCEPTING inside an `ApplicationReadyEvent` listener.**  
Boot publishes readiness accepting right **after** the Ready event. Wait for the state change or `run` to return.

**4. Treating liveness CORRECT as ready.**  
While runners execute, liveness is CORRECT while readiness is REFUSING.

**5. Runner spawns a background job and returns.**  
Boot marks the app ready even though initialization hasn't finished; await critical tasks or coordinate readiness explicitly.

**6. Runner publishes REFUSING and returns.**  
Boot can publish ACCEPTING afterward, overriding the state; do not treat refusal as a sticky flag.

**7. Putting heavy startup work in `@PostConstruct` without understanding phases.**  
Hard to control `StartupRunner` order and readiness; move it into a proper runner.

**8. Failing to test runner failures.**  
Exceptions might be swallowed and falsely report Ready; check FailedEvent and absence of Ready.

**9. Testing a failing runner directly inside `@SpringBootTest`.**  
The context fails before `@Test` runs; use an isolated `SpringApplication` negative test.

**10. Forgetting `probes.enabled` outside Kubernetes.**  
Probe endpoints may return 404 rather than readiness DOWN.

**11. Calling global `/actuator/health` instead of the readiness group.**  
Contributors can differ; query the exact path.

**12. Inferring from 503 readiness that the TCP port is closed.**  
Readiness is a routing signal; localhost still answers HTTP.

**13. Readiness tests not restoring after `REFUSING_TRAFFIC`.**  
Cached contexts leak state; use `finally`.

**14. Assuming the Spring TestContext cache creates a new context per method.**  
Runners only execute on context load, not per `@Test`.

**15. `@BeforeEach` clearing the lifecycle trace.**  
Wipes out startup events recorded before the test runs.

**16. Adding `@DirtiesContext` unnecessarily on every test.**  
Increases startup cost and forces runners to re-run.

**17. Seeding fixtures in `@BeforeEach` that a runner needs at startup.**  
Fixtures arrive too late; seed before context load or unit-test the logic.

**18. Not distinguishing raw `CommandLineRunner` args from structured `ApplicationArguments`.**  
Test the parser on the exact interface.

**19. Relying on component scan order instead of `@Order`.**  
There is no guarantee; use explicit ordering.

**20. Inferring multi-replica safety from a single `SpringApplication` startup.**  
Every instance runs its own runners; use idempotency/locks.

**21. Placing a shared DB outage into the liveness check.**  
Can cause restart storms; liveness is not a dependency monitor.

**22. Mocking so many startup dependencies that no real path remains.**  
Keep at least one real integration test for Boot lifecycle/runner invocation.

**23. Treating `ApplicationContextRunner` as a full Boot startup.**  
It does not automatically provide complete Started/Ready/runner semantics.

**24. Hardcoding port 8080 in HTTP tests.**  
Parallel CI jobs easily collide; use `RANDOM_PORT`.

**25. Not closing an isolated `SpringApplication` context.**  
Leaks threads/resources; tests that own a context must close it.

**26. Closing a shared `@SpringBootTest` context between tests.**  
Leaves the TestContext cache in an inconsistent state.

**27. Not testing runner deadlines and cancellation.**  
Startup can hang indefinitely; use bounded operations.

**28. Using exact startup time assertions in CI.**  
Flaky; assert ordering/state and monitor performance separately.

## 24. Checklist for Designing Proper Tests

1. Identify all `ApplicationRunner`/`CommandLineRunner` beans and critical startup tasks.
2. Document dependencies/ordering among runners; use `@Order`/`Ordered`.
3. Write unit tests for arguments, branching, and business initialization logic.
4. Keep at least one full-startup `@SpringBootTest` to verify `SpringApplication` invocation.
5. Record events in a context-created bean, and do not clear the trace in `@BeforeEach`.
6. Assert Started → Liveness CORRECT → runners → Ready → Readiness ACCEPTING.
7. Verify liveness/readiness states **inside the runner** and after startup.
8. Test failures via an isolated `SpringApplication` and `ApplicationFailedEvent`.
9. Enable Actuator probes explicitly outside Kubernetes.
10. Verify HTTP readiness UP/200 and REFUSING OUT_OF_SERVICE/503.
11. Verify readiness refusal does not mark liveness broken.
12. Restore readiness state in `finally` and avoid running state-mutating tests in parallel.
13. Never use `Thread.sleep` to guess lifecycle phases.
14. Never treat an open port as proof of readiness.
15. Ensure cleanup/timeouts for critical startup I/O and side effects.
16. Every started `SpringApplication` instance can invoke runners; design them idempotently.
17. Test shutdown callbacks/`context.close` on a dedicated context.
18. Consider Kubernetes `startupProbe`, `readinessProbe`, and `livenessProbe` according to their roles.
19. Separate startup metrics from availability event semantics.
20. Never fabricate stdout/logs; record expected values and framework versions accurately.

### Final Checklist

- [ ] Runner unit tests use proper `ApplicationArguments`.
- [ ] Runner integration test invokes via real `SpringApplication`.
- [ ] `@Order` is accurately verified.
- [ ] Ready event appears after runners and before the accepting event.
- [ ] Startup failure does not emit Ready.
- [ ] Readiness is accepting after startup and refusing when expected.
- [ ] Actuator 200/503 mapping is verified over real HTTP.
- [ ] Liveness is independent of readiness.
- [ ] Tests restore readiness after mutating it.
- [ ] Spring TestContext cache does not leak state.
- [ ] No async fire-and-forget for critical initialization.
- [ ] Startup operations have deadlines, error policies, and idempotency.
- [ ] Context close cleanup is tested.
- [ ] External systems are not unconditionally wired into liveness.

## 25. Conclusion

**Started means the context has refreshed; Ready means Spring Boot finished running runners and is about to switch readiness to accepting.** The core sequence to remember:

~~~text
ApplicationStartedEvent
  -> LivenessState.CORRECT
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
~~~

A strong test suite does more than verify the ApplicationContext loads. It proves runners execute properly, events follow the exact order, readiness health groups return 200/503, failing runners emit no Ready event, and resources are cleaned up when the context closes. When applications involve async warmup, cluster scaling, or dependency latency, readiness policies and idempotency must be tested more deeply to prevent false readiness signals.

### Official References

- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): ApplicationRunner, ApplicationArguments, lifecycle events, and availability.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): readiness/liveness probes, health statuses, Kubernetes lifecycle.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest(args)`, RANDOM_PORT, and TestRestTemplate.
- [Spring Boot 3.5 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html): getReadinessState, getLivenessState, last event.
- [Spring Boot 3.5 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): publish and state.
- [Spring Boot 3.5 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationRunner.html): startup runner contract.
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): `@EventListener`/`ApplicationListener`.
- [Spring Framework — Bean Destroy Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): destroy callbacks, AutoCloseable inference.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): graceful shutdown and lifecycle phase timeout.
