# Collecting Events to Verify Ordering and Availability State in Spring Boot

## 1. Goal: testing lifecycle with verifiable traces

A test that merely calls `SpringApplication.run(args)` and checks that no exception is thrown is insufficient to prove the application traversed lifecycle milestones in the right order. Spring Boot can refresh the `ApplicationContext` successfully while `ApplicationRunner` is still executing; `ApplicationStartedEvent` can fire while readiness is still `REFUSING_TRAFFIC`. Conversely, a `ContextClosedEvent` does not prove all executors/consumers have terminated.

This lesson belongs to the **Lifecycle Testing** chapter: **collecting events to verify ordering and availability states**. We record key milestones, use relational ordering assertions, inspect `ApplicationAvailability` directly inside a runner and after Ready, run a controlled startup failure, actively transition readiness, and examine the limits of this technique.

Target outcomes:

- Register an `ApplicationListener` **before** `SpringApplication.run` to capture events before the context exists.
- Record minimal metadata: event label, observed sequence, elapsed time, thread name.
- Verify `ApplicationStartedEvent` → `LivenessState.CORRECT` → runner → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`.
- Verify that inside the runner, liveness is already `CORRECT` while readiness is still `REFUSING_TRAFFIC`.
- Verify that when the runner fails, `ApplicationFailedEvent` is present; Ready and accepting are absent on that startup path.
- Publish `AvailabilityChangeEvent` after startup to verify the refusing → accepting transition.
- Distinguish Spring TestContext's `@RecordApplicationEvents`, ultra-early event recorders, and Actuator HTTP health probes.
- Never treat "closing has started" events as proof that resources have closed.

**Scope:** Java 17+, Spring Boot 3.3.5, JUnit Jupiter, and Gradle. The demo project runs non-web without requiring a database, broker, or Web server. Event capture from Spring is real; log output sequences/timings vary by machine.

## 2. Events involved in a single SpringApplication.run

Spring Boot 3.3 documentation describes the main startup events in order:

```text
ApplicationStartingEvent
       |
ApplicationEnvironmentPreparedEvent
       |
ApplicationContextInitializedEvent
       |
ApplicationPreparedEvent
       |
   context.refresh()
     |-- ContextRefreshedEvent
     +-- WebServerInitializedEvent (if a Web server is present)
       |
ApplicationStartedEvent
       |
AvailabilityChangeEvent(LivenessState.CORRECT)
       |
ApplicationRunner / CommandLineRunner
       |
ApplicationReadyEvent
       |
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
       |
SpringApplication.run() returns successfully
```

This is a **diagram of major milestones**, not an exhaustive list of every event that may interleave. With multiple contexts, Web stacks, parent-child hierarchies, custom publishers, or other event listeners, traces can differ.

| Event | Accurate meaning | Do not infer |
|---|---|---|
| `ApplicationStartingEvent` | Boot begins `run`, before Environment/Context | Beans have been initialized |
| `ApplicationEnvironmentPreparedEvent` | Environment is ready | Context has refreshed |
| `ApplicationContextInitializedEvent` | Context and initializers prepared, bean definitions not loaded yet | All singleton beans exist |
| `ApplicationPreparedEvent` | Bean definitions loaded, before refresh | Application is Ready |
| `ContextRefreshedEvent` | Spring context refresh completed | Runners have finished |
| `ApplicationStartedEvent` | After refresh, before runners | Readiness is accepting |
| `AvailabilityChangeEvent<LivenessState.CORRECT>` | Announces app is live | App has finished runners |
| `ApplicationReadyEvent` | After runners | All readiness listeners have received accepting |
| `AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>` | Announces ready for traffic | All background tasks have finished |
| `ApplicationFailedEvent` | `SpringApplication.run` hit a failure | All success-path events occurred |
| `ContextClosedEvent` | Context is entering the closing phase | All resources have actually stopped |

**Notably:** `ApplicationReadyEvent` is emitted **before** the immediately following `ReadinessState.ACCEPTING_TRAFFIC` event. Therefore, do not design a test expecting an `ApplicationReadyEvent` listener to see the accepting event published beforehand.

**`ApplicationStartedEvent`** sits after refresh and before runners — it is not another name for `ApplicationStartingEvent`. These two events are easily confused because both contain "Started/Starting".

**Runners can be asynchronous:** if `ApplicationRunner.run` merely submits a `CompletableFuture` and returns, Boot can still proceed to Ready while the future keeps processing. To make Ready wait for a critical startup task's completion, await the result with an appropriate deadline or design a mechanism keeping readiness refusing traffic.

## 3. Understanding LivenessState, ReadinessState, and ApplicationAvailability

Spring Boot provides:

```java
org.springframework.boot.availability.ApplicationAvailability
org.springframework.boot.availability.AvailabilityChangeEvent
org.springframework.boot.availability.LivenessState
org.springframework.boot.availability.ReadinessState
```

**Liveness:** internal state indicating whether the app can operate/recover or is broken and needs restarting. `LivenessState` has `CORRECT` and `BROKEN`. Do not set `LivenessState.BROKEN` merely because an external database temporarily loses connectivity; if Kubernetes restarts all replicas, the incident can worsen.

**Readiness:** whether the instance is ready to **accept new traffic**, with `ReadinessState.ACCEPTING_TRAFFIC` and `ReadinessState.REFUSING_TRAFFIC`. Being live yet not ready is completely valid while runners are executing, during warm-up, or while draining before shutdown.

| Stage | Standard Liveness | Standard Readiness |
|---|---|---|
| Initial | Not yet Correct, defaults like `BROKEN` | `REFUSING_TRAFFIC` |
| Started, runners executing | `CORRECT` | `REFUSING_TRAFFIC` |
| Ready | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Graceful shutdown | Usually still `CORRECT` | `REFUSING_TRAFFIC` |

The table describes Boot 3.3's typical lifecycle. Applications can publish changes themselves, and an HTTP probe may not be exposed yet very early on or may have stopped during shutdown.

### 3.1. Checking state directly

`ApplicationAvailability` provides the APIs:

```java
LivenessState live = availability.getLivenessState();
ReadinessState ready = availability.getReadinessState();
AvailabilityChangeEvent<ReadinessState> last =
        availability.getLastChangeEvent(ReadinessState.class);
```

This is an **integration snippet**, requiring an `availability` variable of type `ApplicationAvailability` and appropriate imports.

`getReadinessState()` returns the current state, while `getLastChangeEvent(...)` returns the most recent change event **when one exists**. The last event can be null before Boot publishes an event of that type. A default state of `REFUSING_TRAFFIC` **does not prove** an `AvailabilityChangeEvent(REFUSING_TRAFFIC)` was ever published.

Therefore, tests should verify **state inside the runner** rather than demanding a separate initial refusing event in the trace.

### 3.2. Published availability is not proof of serving HTTP

`ApplicationAvailability.getReadinessState()==ACCEPTING_TRAFFIC` is internal JVM state. It does not prove:

- The Web server is listening on the right port (the non-web demo has no Web server).
- The load balancer updated routing instantaneously.
- Kubernetes probes have already observed the new state.
- All HTTP connections/remote dependencies are healthy.
- An async task outside the runner has completed.

To verify the real HTTP path, a dedicated Web/Actuator integration test is needed.

## 4. Where a listener is registered determines which events it can capture

A listener bean created after the context is built **cannot reliably capture `ApplicationStartingEvent`**:

```java
@Component
class TooLate {
    @EventListener
    void onStarting(ApplicationStartingEvent event) {
        // This event fires before the component bean exists.
    }
}
```

This snippet illustrates a timing mistake and requires appropriate imports. `@EventListener` is very useful for events after beans are registered, yet cannot replace an early listener when testing full bootstrapping.

The right approach:

```java
StartupTrace trace = new StartupTrace();

SpringApplication application =
        new SpringApplication(LifecycleTraceApplication.class);

application.addListeners(trace);  // Register before run().

ConfigurableApplicationContext context = application.run(args);
```

This integration snippet is implemented in full in the demo section.

Other early registration options include `SpringApplicationBuilder.listeners(...)` and `META-INF/spring.factories` under key `org.springframework.context.ApplicationListener`. If you only need to track `AvailabilityChangeEvent` while the app is running, a regular `@EventListener` bean may be more appropriate.

## 5. What should a recorder capture?

Each entry should include:

- **Sequence:** the order processed by the recorder.
- **Label:** standardized name, e.g. `STARTED`, `READY`, `LIVENESS:CORRECT`.
- **Thread:** the thread executing the listener.
- **Elapsed time:** duration since recorder creation via `System.nanoTime()`.
- **Context ID / run ID** when multiple contexts or multiple startups occur.

You do not need to store raw `ApplicationEvent` objects. Many events hold references to the context, Environment, exceptions, or large source objects; keeping them in a `static List` can retain memory across tests longer than intended. Snapshotting strings, enums, and timestamps usually suffices for order verification.

### 5.1. Thread-safe recording does not imply global ordering

With the default synchronous event multicaster, a listener normally runs on the publisher's thread. When designing a recorder, `synchronized` prevents two threads from generating duplicate sequences or corrupting `ArrayList`.

If an async event multicaster is enabled, event A may be published before B while B's listener executes before A's listener due to scheduling. In that case, the recorder only proves **delivery order to the recorder**, not publish order or happens-before relationships between two business tasks. Use event IDs, deadlines, and `CountDownLatch`/`CompletableFuture` to coordinate when genuinely required.

### 5.2. Do not assert the entire sequence with a rigid list

Not recommended:

```java
assertEquals(List.of("STARTING", "STARTED", "READY"),
        trace.labels());
```

This is an example of a brittle test: many valid events are omitted; adding a custom event or Web server alters the list even though the invariant still holds.

Prefer asserting **partial order**:

```text
STARTING < ENV_PREPARED < CONTEXT_INITIALIZED < PREPARED
PREPARED < CONTEXT_REFRESHED < STARTED
STARTED < LIVENESS:CORRECT < RUNNER
RUNNER < READY < READINESS:ACCEPTING_TRAFFIC
```

The less-than sign here denotes "appears earlier in the same trace", not enum comparison. Never assert "must take exactly 120 ms", because JVM speed, CI, CPU/disk, and logging vary.

## 6. How to prove readiness at the exact moment the runner runs

Problem: if you only query `ApplicationAvailability` after `run`, you only know the app ended up accepting. To verify **it is still refusing while the runner executes**, create a custom marker event carrying both states read right inside the runner:

```java
publisher.publishEvent(
        new RunnerObservedEvent(
                this,
                availability.getLivenessState(),
                availability.getReadinessState()));
```

The recorder records:

```text
RUNNER:CORRECT/REFUSING_TRAFFIC
```

Only afterward come `READY` and `READINESS:ACCEPTING_TRAFFIC`. That is stronger evidence than inferring from latency or using `Thread.sleep`.

Do not manually publish accepting inside the runner to force a test to pass; doing so alters the exact behavior you intend to verify.

## 7. Runnable Java 17 + Spring Boot 3.3.5 + JUnit 5 project

The non-web project avoids DB/broker/HTTP to minimize noise, while using real events and `ApplicationAvailability` from Spring Boot.

### 7.1. Structure

```text
lifecycle-event-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/lifecycletrace/
    │   ├── LifecycleTraceApplication.java
    │   └── StartupTrace.java
    └── test/java/com/example/lifecycletrace/
        └── LifecycleOrderTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'lifecycle-event-order-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` suffices for the non-web app; `spring-boot-starter-test` provides JUnit Jupiter. To run `./gradlew` or `.\gradlew.bat`, you need a Gradle Wrapper from Spring Initializr or generated with a compatible Gradle version. Merely adding `build.gradle` does not generate the Wrapper.

### 7.2. StartupTrace.java — recorder capturing early and late events

**`src/main/java/com/example/lifecycletrace/StartupTrace.java`:**

```java
package com.example.lifecycletrace;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;

public final class StartupTrace
        implements ApplicationListener<ApplicationEvent> {

    public record Entry(
            int sequence,
            long elapsedMicros,
            String threadName,
            String label) {
    }

    private final long beginNanos = System.nanoTime();
    private final List<Entry> entries = new ArrayList<>();

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            record("STARTING");
        } else if (event instanceof
                ApplicationEnvironmentPreparedEvent) {
            record("ENV_PREPARED");
        } else if (event instanceof
                ApplicationContextInitializedEvent) {
            record("CONTEXT_INITIALIZED");
        } else if (event instanceof ApplicationPreparedEvent) {
            record("PREPARED");
        } else if (event instanceof ContextRefreshedEvent) {
            record("CONTEXT_REFRESHED");
        } else if (event instanceof ApplicationStartedEvent) {
            record("STARTED");
        } else if (event instanceof AvailabilityChangeEvent<?> change) {
            if (change.getState() instanceof LivenessState) {
                record("LIVENESS:" + change.getState());
            } else if (change.getState() instanceof ReadinessState) {
                record("READINESS:" + change.getState());
            }
        } else if (event instanceof
                LifecycleTraceApplication.RunnerObservedEvent observed) {
            record("RUNNER:"
                    + observed.liveness() + "/"
                    + observed.readiness());
        } else if (event instanceof ApplicationReadyEvent) {
            record("READY");
        } else if (event instanceof ApplicationFailedEvent) {
            record("FAILED");
        } else if (event instanceof ContextClosedEvent) {
            record("CONTEXT_CLOSED");
        }
    }

    private synchronized void record(String label) {
        long micros = TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - beginNanos);

        entries.add(new Entry(
                entries.size() + 1,
                micros,
                Thread.currentThread().getName(),
                label));
    }

    public synchronized List<Entry> snapshot() {
        return List.copyOf(entries);
    }

    public List<String> labels() {
        return snapshot().stream()
                .map(Entry::label)
                .toList();
    }

    public void printAll() {
        for (Entry e : snapshot()) {
            System.out.printf(
                    "%02d +%d us [%s] %s%n",
                    e.sequence(),
                    e.elapsedMicros(),
                    e.threadName(),
                    e.label());
        }
    }
}
```

**Why is the code above on-target?**

1. `ApplicationListener<ApplicationEvent>` receives events across multiple subtypes; we filter with `instanceof`.
2. `record` and `snapshot` use `synchronized` for internal consistency. `Entry` is an immutable Java record.
3. Retains no raw event objects and creates no static list; each test constructs its own recorder.
4. `ApplicationContextInitializedEvent` and `ApplicationEnvironmentPreparedEvent` are captured thanks to early registration, not because the recorder is a bean.
5. `elapsedMicros` is the elapsed time since recorder creation; do not treat it as a fixed startup latency metric.
6. `printAll` runs after the app has run/closed in `main`, avoiding repeated I/O logging inside the listener.
7. For multiple contexts/async listeners, extend the recorder with run/context IDs and choose appropriate ordering semantics.

### 7.3. LifecycleTraceApplication.java — bootstrap and runner marker

**`src/main/java/com/example/lifecycletrace/LifecycleTraceApplication.java`:**

```java
package com.example.lifecycletrace;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LifecycleTraceApplication {

    public static ConfigurableApplicationContext start(
            StartupTrace trace, String... args) {

        SpringApplication app =
                new SpringApplication(LifecycleTraceApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.addListeners(trace); // Register before run(args).
        return app.run(args);
    }

    public static void main(String[] args) {
        StartupTrace trace = new StartupTrace();
        ConfigurableApplicationContext context = null;

        try {
            context = start(trace, args);

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            System.out.println(
                    "AFTER_RUN liveness="
                    + availability.getLivenessState()
                    + " readiness="
                    + availability.getReadinessState());
        } finally {
            try {
                if (context != null) {
                    context.close();
                }
            } finally {
                trace.printAll();
            }
        }
    }

    @Bean
    ApplicationRunner reportRunner(
            ApplicationEventPublisher publisher,
            ApplicationAvailability availability,
            Environment environment) {

        return args -> {
            publisher.publishEvent(new RunnerObservedEvent(
                    this,
                    availability.getLivenessState(),
                    availability.getReadinessState()));

            if (environment.getProperty(
                    "demo.fail-runner", Boolean.class, false)) {
                throw new IllegalStateException(
                        "Controlled failure in ApplicationRunner");
            }
        };
    }

    public static final class RunnerObservedEvent
            extends ApplicationEvent {

        private final LivenessState liveness;
        private final ReadinessState readiness;

        public RunnerObservedEvent(
                Object source,
                LivenessState liveness,
                ReadinessState readiness) {

            super(source);
            this.liveness = liveness;
            this.readiness = readiness;
        }

        public LivenessState liveness() {
            return liveness;
        }

        public ReadinessState readiness() {
            return readiness;
        }
    }
}
```

**Explanation:**

- `start(trace,args)` creates a real `SpringApplication`, adds the listener before startup, and returns the context if successful.
- `WebApplicationType.NONE` prevents the example from opening a Web server while Boot still maintains availability.
- `reportRunner` is an `ApplicationRunner`: it emits an event containing the exact liveness/readiness at execution time.
- The `demo.fail-runner` flag is a demo-defined property, not a built-in setting. When true, the runner intentionally throws after publishing the marker.
- `main` prints state **after `run` returns**, then closes the context so the non-web demo can exit. Do not apply immediate closing to production Web services.
- If `run` throws, `context` may be null; `finally` still prints the trace, and the exception propagates to the Java launcher. The app does not swallow startup errors.
- `RunnerObservedEvent` extends `ApplicationEvent` so Spring's publisher delivers it through the same listener system and the recorder captures it.
- The code does not fake availability states; it reads real `ApplicationAvailability` from Boot.

### 7.4. Successful run

Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Important output:

```text
AFTER_RUN liveness=CORRECT readiness=ACCEPTING_TRAFFIC
```

Key trace labels in a normal startup run, in order:

```text
STARTING
ENV_PREPARED
CONTEXT_INITIALIZED
PREPARED
CONTEXT_REFRESHED
STARTED
LIVENESS:CORRECT
RUNNER:CORRECT/REFUSING_TRAFFIC
READY
READINESS:ACCEPTING_TRAFFIC
CONTEXT_CLOSED
```

**This is an illustrative label subsequence**, not exact full stdout: the program also prints sequence numbers, elapsed micros, thread names, and Boot/Gradle logs. Other availability/shutdown events may appear in the trace when closing the context; therefore tests should not assert an absolute list containing only these exact lines.

### 7.5. Controlled startup failure run

Linux/macOS:

```bash
./gradlew bootRun --args='--demo.fail-runner=true'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.fail-runner=true"
```

The runner publishes marker `RUNNER:CORRECT/REFUSING_TRAFFIC`, then throws `IllegalStateException`. Boot emits `ApplicationFailedEvent` while handling the failure. Neither `ApplicationReadyEvent` nor an accepting readiness event occurs on the **successful startup path**.

Gradle may report `bootRun` failed / nonzero process exit; that is what we expect to observe in the error test scenario, not a sign the recorder broke.

## 8. JUnit Jupiter tests: verifying order, failure, and state

**`src/test/java/com/example/lifecycletrace/LifecycleOrderTest.java`:**

```java
package com.example.lifecycletrace;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LifecycleOrderTest {

    @Test
    void startupOrderAndAvailabilityAreCorrect() {
        StartupTrace trace = new StartupTrace();

        try (ConfigurableApplicationContext context =
                LifecycleTraceApplication.start(trace)) {

            List<String> labels = trace.labels();

            before(labels, "STARTING", "ENV_PREPARED");
            before(labels, "ENV_PREPARED", "CONTEXT_INITIALIZED");
            before(labels, "CONTEXT_INITIALIZED", "PREPARED");
            before(labels, "PREPARED", "CONTEXT_REFRESHED");
            before(labels, "CONTEXT_REFRESHED", "STARTED");
            before(labels, "STARTED", "LIVENESS:CORRECT");
            before(labels, "LIVENESS:CORRECT",
                    "RUNNER:CORRECT/REFUSING_TRAFFIC");
            before(labels, "RUNNER:CORRECT/REFUSING_TRAFFIC",
                    "READY");
            before(labels, "READY",
                    "READINESS:ACCEPTING_TRAFFIC");

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            assertEquals(
                    LivenessState.CORRECT,
                    availability.getLivenessState());
            assertEquals(
                    ReadinessState.ACCEPTING_TRAFFIC,
                    availability.getReadinessState());
        }

        assertTrue(trace.labels().contains("CONTEXT_CLOSED"));
    }

    @Test
    void failingRunnerDoesNotBecomeReady() {
        StartupTrace trace = new StartupTrace();

        assertThrows(RuntimeException.class, () ->
                LifecycleTraceApplication.start(
                        trace, "--demo.fail-runner=true"));

        List<String> labels = trace.labels();

        assertTrue(labels.contains("STARTED"));
        assertTrue(labels.contains("LIVENESS:CORRECT"));
        assertTrue(labels.contains(
                "RUNNER:CORRECT/REFUSING_TRAFFIC"));
        assertTrue(labels.contains("FAILED"));
        assertFalse(labels.contains("READY"));
        assertFalse(labels.contains(
                "READINESS:ACCEPTING_TRAFFIC"));
    }

    @Test
    void explicitReadinessTransitionsAreRecorded() {
        StartupTrace trace = new StartupTrace();

        try (ConfigurableApplicationContext context =
                LifecycleTraceApplication.start(trace)) {

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            assertEquals(
                    ReadinessState.ACCEPTING_TRAFFIC,
                    availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);

            assertEquals(
                    ReadinessState.REFUSING_TRAFFIC,
                    availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);

            assertEquals(
                    ReadinessState.ACCEPTING_TRAFFIC,
                    availability.getReadinessState());

            List<String> labels = trace.labels();
            int firstAccept =
                    labels.indexOf("READINESS:ACCEPTING_TRAFFIC");
            int refuse =
                    labels.indexOf("READINESS:REFUSING_TRAFFIC");
            int lastAccept =
                    labels.lastIndexOf("READINESS:ACCEPTING_TRAFFIC");

            assertTrue(firstAccept >= 0);
            assertTrue(refuse > firstAccept);
            assertTrue(lastAccept > refuse);
        }
    }

    private static void before(
            List<String> labels, String earlier, String later) {

        int a = labels.indexOf(earlier);
        int b = labels.indexOf(later);

        assertTrue(
                a >= 0 && b > a,
                () -> "Expected " + earlier
                        + " before " + later
                        + " in " + labels);
    }
}
```

### 8.1. What the tests prove

**Test 1** calls real `SpringApplication.run` with the pre-registered recorder. It asserts before–after relationships, checks `ApplicationAvailability` after Ready, then closes the context and confirms `ContextClosedEvent` was observed by the recorder.

**Test 2** triggers a controlled runner failure; `assertThrows` ensures startup did not succeed; `FAILED` is present while Ready/accepting are absent. It avoids trying to fetch `ApplicationAvailability` from a context that `run` never returned.

**Test 3** publishes refusing then accepting after startup, comparing both `ApplicationAvailability` and the trace. Using `firstAccept` and `lastAccept` distinguishes **accepting at Boot Ready** from **the newly restored accepting state**.

### 8.2. How to run the tests

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Test code creates a fresh recorder/context per method and explicitly closes it, without relying on a static global event list. All key assertions depend on event/availability logic rather than fixed millisecond values.

### 8.3. Why not Thread.sleep?

Under the standard synchronous dispatcher configuration, when `SpringApplication.run` returns and when `AvailabilityChangeEvent.publish` returns, the corresponding listeners have already executed on the publishing thread. `Thread.sleep(100)` adds no correctness; it only makes tests slow and flaky. With an async multicaster, switch to `CountDownLatch` or futures with deadlines rather than sleeping to guess event arrival.

## 9. @RecordApplicationEvents in Spring TestContext vs. early capture

Spring Framework TestContext provides:

- `@RecordApplicationEvents`: enables event recording inside the test context.
- `ApplicationEvents`: inspects recorded events via `stream()`.
- `ApplicationEventsTestExecutionListener`: supports registering recording per test method lifecycle.

Integration skeleton:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@RecordApplicationEvents
class BusinessEventsTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Test
    void observesEventFromTestMethod(ApplicationEvents events) {
        publisher.publishEvent(new DomainEvent(this));

        assertEquals(
                1L,
                events.stream(DomainEvent.class).count());
    }
}
```

**Not a standalone runnable file:** requires importing annotations/types and defining `DomainEvent`. It illustrates testing **an event emitted from a test method**, without guaranteeing capture of all `ApplicationStartingEvent`s fired before context initialization.

A test method begins after Spring TestContext bootstrap; therefore do not expect `@RecordApplicationEvents` to automatically supply every early event emitted earlier by `SpringApplication`.

| Task | Appropriate tool |
|---|---|
| Capture `ApplicationStartingEvent` | `SpringApplication.addListeners` before `run` |
| Test Started → runner → Ready | Early listener + runner marker |
| Test post-startup state | `ApplicationAvailability` |
| Test custom event published in JUnit method | `@RecordApplicationEvents` |
| Test readiness change | `AvailabilityChangeEvent.publish` + state/assertions |
| Test resource shutdown | `SmartLifecycle` callbacks/termination markers |
| Test HTTP routing/probes | Actuator Web integration test |

## 10. Testing dynamic readiness inside the application

When a queue overloads or a critical condition prevents an instance from accepting traffic yet, the app can publish:

```java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
```

After recovery:

```java
AvailabilityChangeEvent.publish(
        context, ReadinessState.ACCEPTING_TRAFFIC);
```

This is an integration snippet. The overload accepting `ApplicationContext` is provided by Spring Boot; beyond context, there is also an overload accepting `ApplicationEventPublisher`, source, and state.

**Policy note:** if multiple subsystems independently publish accepting/refusing, a new accepting event can overwrite a refusing state from another subsystem. Design a coordinator aggregating conditions that publishes accepting only when all essential conditions hold.

Never use liveness `BROKEN` for every temporary lack of traffic capacity. Also, publishing readiness does not make the load balancer instantly sever all existing connections; probe/routing delays and HTTP/worker draining still apply.

### Example event-publishing service

```java
@Service
class ReadinessCoordinator {

    private final ApplicationEventPublisher publisher;

    ReadinessCoordinator(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void pauseTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    void resumeTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

This is an integration snippet requiring imports. In production, add policies for multiple health sources and concurrency, rather than letting every service freely resume the same shared state.

## 11. Actuator HTTP probes vs. in-JVM state

If you add `spring-boot-starter-actuator` to a **Web** application with proper configuration, you can inspect:

```text
/actuator/health/liveness
/actuator/health/readiness
```

In Kubernetes, probe health groups may be enabled automatically. In other environments, configure:

```properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
```

This configuration **does not create HTTP endpoints for the non-web demo** in section 7. Real Web stack and Actuator are required.

Distinguish:

1. **Internal state:** `ApplicationAvailability` returns liveness/readiness.
2. **Health indicator:** Boot/Actuator maps state to a health response.
3. **HTTP endpoint:** server and management exposure determine whether the URL is served.
4. **Orchestrator:** Kubernetes receives probe results and decides whether the instance receives traffic; updates are not instantaneous.

`REFUSING_TRAFFIC` normally maps to an unavailable health status (e.g. `OUT_OF_SERVICE`) and HTTP 503 in the default mapping; status mapping settings can vary, so HTTP tests must rely on the actual project.

If the management server runs on a **separate port**, probes may report healthy even if the main application port fails. For that use case, check probe exposure guidelines on the main server port and endpoint security; never expose all Actuator endpoints publicly.

## 12. Testing ContextClosedEvent and proper shutdown

During a normal `context.close()`:

```text
ContextClosedEvent
      |
LifecycleProcessor.onClose()
      |
SmartLifecycle.stop(Runnable) by phase
      |
wait for callback or per-phase timeout
      |
destroy singleton beans
  @PreDestroy / DisposableBean / destroy-method
      |
close() returns
```

**`ContextClosedEvent` fires at the start of context closing**, not as an event meaning "all resources have stopped successfully".

If a consumer depends on a writer, use `getPhase()=200` for the consumer and `100` for the writer. On stop, the higher-phase consumer is asked to stop first, and `SmartLifecycle.stop(Runnable)` should invoke its callback only after the consumer finishes draining; only then can Spring proceed to the lower-phase writer. Forgetting the callback causes the lifecycle processor to wait until the phase timeout. Calling the callback early can close the writer while the consumer still uses it.

To test shutdown, collect additional markers from real resources:

```text
CONTEXT_CLOSED
CONSUMER_STOP_BEGIN
CONSUMER_DRAINED
CONSUMER_STOP_CALLBACK
WRITER_STOP_BEGIN
WRITER_STOP_CALLBACK
CONSUMER_DESTROY
WRITER_DESTROY
```

This is an **illustrative timeline**, not an automatic event list emitted by Boot. Destroy order also depends on bean dependency/destruction config; tests must follow real contracts rather than arbitrary expectations.

Furthermore, `context.close()` may return while an app-created non-daemon worker remains alive if you fail to stop it. The Java process can continue running after a direct close; never treat `ContextClosedEvent` as proof the process exited.

## 13. Event hierarchy, async dispatchers, and observed ordering

### 13.1. Parent-child contexts

Spring event propagation lets events from a child context propagate to the parent. One listener may observe multiple events of the same type across multiple contexts. In tests, record `contextId` or compare the event's `ApplicationContext` against the target context instead of asserting count=1 across a complex application.

### 13.2. Asynchronous listeners

If the event multicaster uses an executor, listener processing order can invert relative to publish order. Tests must:

- Distinguish publish order from observed delivery order.
- Use `CountDownLatch`/futures with deadlines to await required events.
- Include correlation IDs to pair events with an operation.
- Never infer happens-before from timestamps across unsynchronized threads.
- Never try to fix races with fixed `Thread.sleep`.

### 13.3. @Order and phase do not replace completion

`@Order` can affect runner/listener order within the applicable scope, yet does not guarantee all JVM bean init, async tasks, or shutdown proceed sequentially per that order. `SmartLifecycle.getPhase()` governs lifecycle start/stop ordering; task completion still requires dedicated futures/latches/callbacks.

### 13.4. Publishing the same state multiple times

Two consecutive `AvailabilityChangeEvent(REFUSING_TRAFFIC)` events can occur. Unless the app has a single-publish contract, tests should check the final state or **required transition order**, rather than assuming each enum state appears only once per run.

### 13.5. Tests failing at different stages

| Where failure occurs | Likely already present | Must not assume present |
|---|---|---|
| Environment preparation | `STARTING` and `FAILED` | `ContextRefreshedEvent` |
| Bean definition loading | Several pre-refresh events, `FAILED` | `STARTED` |
| Singleton construction during refresh | `PREPARED`, `FAILED` | `READY` |
| Runner | `STARTED`, liveness correct, runner marker, `FAILED` | Ready/accepting |
| Ready listener throws | `ApplicationReadyEvent` may already be published | Published readiness accepting |
| Async background job after Ready | App may already be Ready | Startup `ApplicationFailedEvent` |

A startup failure inside a runner differs from a startup failure before the context exists. Tests must select matching invariants. If an error occurs **after Ready** inside `@Async`/schedulers, `ApplicationFailedEvent` is not automatically emitted like a `SpringApplication.run` failure.

## 14. Diagnosing failing tests

| Symptom | Common cause | Action |
|---|---|---|
| Missing `STARTING` | Listener registered after `run` or only as a bean | `addListeners` before `run` |
| Has `STARTED`, missing runner marker | Runner didn't run or wrong event type | Check `@Bean ApplicationRunner` |
| Readiness already accepting in runner | Custom code published accepting too early | Find all `AvailabilityChangeEvent.publish` calls |
| Normal run missing `READY` | Another runner/listener threw an exception | Inspect `ApplicationFailedEvent`/stack |
| Missing accepting event | Recorder filtered state/event wrongly, or startup failed | Check `AvailabilityChangeEvent<?>` |
| State and trace contradict | Different context, concurrent publish, or async listener | Tag context/run ID, pinpoint milestone |
| Count=1 fails in child context | Event propagated or repeated refresh | Filter context identity |
| Event order flaky on CI | Async event processing not awaited | Use completion/latch |
| `CONTEXT_CLOSED` present yet process stays alive | Executor/thread not shut down | Check resource termination |
| Timeout assert fails | Relying on fixed milliseconds | Assert order/semantic state instead of time |
| Later test affected by earlier test | Static recorder or context cache | Fresh recorder per run |
| HTTP probe does not exist | Non-web, Actuator not enabled/exposed | Run appropriate Web integration test |
| Liveness BROKEN when external DB drops | Confusing readiness/liveness | Fix state classification |

Do not fix failures by blindly removing required assertions. Read the timeline and thread names to locate whether the bug is in **event recording**, **publishing**, **state source**, or **expectations**.

## 15. Security and cost of event tracing

Default synchronous listeners can slow startup if every event performs heavy I/O. In the demo, the recorder merely appends a small `Entry` and prints after observation. In production, use bounded/ring buffers or controlled logging so events do not accumulate unboundedly in the heap.

Traces may contain class names, context IDs, thread names, configuration, and error details. Avoid storing secrets or PII payloads. If recording exceptions, sanitize them instead of retaining full `Throwable`/`ApplicationContext` graphs in static collections.

Across multiple replicas, use correlation IDs/process IDs and appropriate timestamps; never compare two `System.nanoTime` values from two JVMs as a shared clock. Actuator health endpoints must have access control; never expose all endpoints publicly just to observe lifecycle.

## 16. Practice exercises

**Exercise 1 — baseline:** run the tests and application, recording the order `STARTING → ENV_PREPARED → CONTEXT_INITIALIZED → PREPARED → CONTEXT_REFRESHED → STARTED → LIVENESS:CORRECT → RUNNER → READY → READINESS:ACCEPTING_TRAFFIC`.

**Exercise 2 — overly late listener:** remove `app.addListeners(trace)`, replace with `@Component @EventListener`, and compare which early events disappear. Explain in terms of context creation timing.

**Exercise 3 — checking state in runner:** compare `LivenessState.CORRECT` and `ReadinessState.REFUSING_TRAFFIC` read directly inside the runner; never manually publish accepting to make the test pass easily.

**Exercise 4 — runner failure:** run `--demo.fail-runner=true`, assert `FAILED`, and assert no Ready or accepting. Then trigger a failure before refresh and adjust expectations.

**Exercise 5 — readiness transitions:** publish refusing then accepting after Ready; compare `ApplicationAvailability.getReadinessState()` and the event trace; inspect `getLastChangeEvent`.

**Exercise 6 — recorder race:** spawn two publisher threads and record sequences with the recorder. Why does recorder order differ from semantic event ordering in an async system?

**Exercise 7 — `@RecordApplicationEvents`:** write a test with `@SpringBootTest` publishing a custom domain event inside a method; prove it does not replace an early listener for `ApplicationStartingEvent`.

**Exercise 8 — Web/Actuator:** create a Web app with Actuator, enable probes, and check `/actuator/health/readiness` responses vs. in-memory state. Distinguish HTTP probes from internal state.

**Exercise 9 — graceful shutdown:** add `SmartLifecycle` consumer and writer beans with different phases, record `STOP_BEGIN` and `STOP_CALLBACK` markers, and assert completion only after the callback.

**Exercise 10 — forgotten callback:** in an isolated test, intentionally omit the callback to observe the phase timeout; restore immediately after observing, and never apply in production.

**Exercise 11 — multiple contexts:** use parent/child contexts and add context IDs to `Entry`; update assertions to filter only events belonging to the target context.

**Exercise 12 — async work:** have the runner submit a `CompletableFuture` without awaiting; confirm Ready can arrive before completion. Then design a valid wait before Ready.

**Exercise 13 — coordinating multiple health sources:** simulate two readiness conditions. Ensure that while one source has not recovered, another cannot publish accepting through the coordinator.

**Exercise 14 — sleep-free test:** for async events, use `CountDownLatch` or a Future to wait instead of `Thread.sleep(100)`; explain happens-before.

**Exercise 15 — write a report:** document Boot/JDK versions, filtered event list, ordering assertions, runner/post-Ready states, failure test results, shutdown completion, and observation limits.

### Self-assessment questions

1. Does `ApplicationStartedEvent` occur before or after runners?
2. Does Boot publish `LivenessState.CORRECT` before or after `ApplicationStartedEvent`?
3. Inside a runner, what is the default readiness?
4. In what order do `ApplicationReadyEvent` and `ReadinessState.ACCEPTING_TRAFFIC` occur?
5. Why can't an `@EventListener` bean reliably catch `ApplicationStartingEvent`?
6. Is `ApplicationAvailability.getReadinessState()` the same as "observed a refusing event"?
7. Is `@RecordApplicationEvents` suited for recording all bootstrap events, or primarily events within a test method?
8. Why is partial-order testing better than asserting a rigid full list?
9. When a runner throws, are Ready/accepting milestones emitted normally?
10. Does `ContextClosedEvent` prove workers have completely stopped?
11. If the event multicaster runs asynchronously, why can observed order differ from publish order?
12. Why does accepting readiness not guarantee the HTTP load balancer immediately routes traffic?

## 17. Completion checklist

- [ ] Use a listener registered before `run` to capture early events.
- [ ] Use a separate recorder per test/run.
- [ ] Record label, sequence, elapsed time, and thread without retaining context objects long-term.
- [ ] Assert Started before runner, runner before Ready.
- [ ] Assert Correct after Started, accepting after Ready.
- [ ] Verify Refusing readiness inside the runner using real state.
- [ ] Do not require a refusing event at startup when the state is merely the default.
- [ ] Test runner failure with `assertThrows` and absence of Ready/accepting.
- [ ] Test publishing readiness and re-reading `ApplicationAvailability`.
- [ ] Test context close and resource completion separately.
- [ ] Do not assert the entire event list for apps with multiple contexts/optional events.
- [ ] Async listeners must use completion signals instead of fixed sleeps.
- [ ] Separate Actuator Web probe tests from in-memory availability tests.
- [ ] Never leak secrets; bound trace storage.

## 18. Conclusion

To test the Spring Boot Application Runtime, combine **event traces** and **availability state**. A successful Boot 3.3 startup has the core sequence `ApplicationStartedEvent` → `LivenessState.CORRECT` → runners → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`. Inside runners, readiness can still be — and normally is — `REFUSING_TRAFFIC`.

`SpringApplication.addListeners` before `run` is a simple way to capture early events. `@RecordApplicationEvents` is useful for events inside test methods, not a substitute for bootstrap listeners. `AvailabilityChangeEvent.publish` allows proactively changing state for testing, yet out-of-JVM HTTP/routing probes need dedicated integration tests. `ContextClosedEvent` signals that closing has started, not that all resources have stopped.

Tests should verify **meaningful milestone ordering and state at the relevant moments**, rather than using verbatim full logs or absolute timings as brittle contracts.

### Official documentation

- Spring Boot 3.3 — Application Events, Listeners, and Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator Probes and Application Lifecycle States: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — ApplicationAvailability API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.3 — AvailabilityChangeEvent API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Framework — Testing Application Events (@RecordApplicationEvents): https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html
- Spring Framework 6.1 — SmartLifecycle API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — ContextClosedEvent API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/ContextClosedEvent.html