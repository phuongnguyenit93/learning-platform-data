# Proactively Publishing Application Availability State Change Events in Spring Boot 3.3

## 1. Objective

Spring Boot includes an **Application Availability** mechanism to represent the state of a running application. Beyond the events Spring Boot itself publishes during startup and shutdown, **an application component can also proactively publish `AvailabilityChangeEvent`** when operating conditions change.

Two common state groups:

- **`ReadinessState`**: whether the application should accept additional traffic or new work.
- **`LivenessState`**: whether the application can still operate/self-recover properly or is broken to a degree requiring a restart.

When a component proactively publishes an event, listeners can receive it, and Spring Boot updates the state reported by the `ApplicationAvailability` bean. When Spring Boot Actuator is present with probes properly configured, this state can also be reflected in health groups for orchestration systems like Kubernetes.

**Practical objectives:**

1. Distinguish the **event** `AvailabilityChangeEvent<S>` from the **state value** `ReadinessState`/`LivenessState` and the **query bean** `ApplicationAvailability`.
2. Publish correctly using both API forms: `AvailabilityChangeEvent.publish(context, state)` and `AvailabilityChangeEvent.publish(publisher, source, state)`.
3. Use constructor injection to publish/receive events and re-query state.
4. Choose `REFUSING_TRAFFIC` when temporarily pulling the application from incoming work, instead of arbitrarily marking liveness `BROKEN`.
5. Understand the interaction between self-published states and Spring Boot's automatic startup/shutdown events.
6. Run a Java 21 + Spring Boot 3.3.13 example, observe state ordering, test with JUnit, and know how to wire Actuator readiness/liveness probes.

**Core principle:** changing availability state is a **signal about serving capability**, not a command that automatically shuts down the JVM, kills the pod, restarts the container, or aborts in-flight requests.

## 2. Three-Component Model

```text
A component detects an abnormal condition
          |
          | AvailabilityChangeEvent.publish(...)
          v
Spring ApplicationEventPublisher
          |
          +--> AvailabilityChangeEvent<ReadinessState>
          |     +--> ApplicationAvailability records new state
          |     +--> Listener observes, writes logs/metrics
          |     +--> Actuator readiness health group (if configured)
          |
          +--> AvailabilityChangeEvent<LivenessState>
                +--> ApplicationAvailability records new state
                +--> Listener observes
                +--> Actuator liveness health group (if configured)
```

Three concepts are easily confused:

| Component | Role | Usage |
| --- | --- | --- |
| `AvailabilityState` | Marker interface for a state type | `ReadinessState`, `LivenessState` are implementing enums |
| `AvailabilityChangeEvent<S extends AvailabilityState>` | An application event announcing a state change | `AvailabilityChangeEvent.publish(...)`, `event.getState()` |
| `ApplicationAvailability` | Reads the latest published state for an availability type | `getReadinessState()`, `getLivenessState()`, `getState(...)` |

**Note:** `ApplicationAvailability` is for **reading**, not an interface with setters like `setReadinessState(...)`. To update state, **publish an `AvailabilityChangeEvent` through the Spring event publisher/context**.

### 2.1. Readiness Values

`org.springframework.boot.availability.ReadinessState` has two main values:

- **`ReadinessState.ACCEPTING_TRAFFIC`**: the application announces it can receive new traffic or tasks.
- **`ReadinessState.REFUSING_TRAFFIC`**: the application announces it should not yet receive more traffic or new tasks.

Good fits for `REFUSING_TRAFFIC`: a service needs to temporarily pull out of a load balancer to shed load, lacks capacity to process safely, is recovering required internal data, or is preparing for controlled maintenance.

Readiness does not say the JVM is dead. An application can still be **live** while it is **not ready**.

### 2.2. Liveness Values

`org.springframework.boot.availability.LivenessState` has two main values:

- **`LivenessState.CORRECT`**: internal state still allows the application to operate properly.
- **`LivenessState.BROKEN`**: the application has fallen into an internal state from which it cannot recover properly without external intervention, typically requiring a restart per operational policy.

**Do not mark `BROKEN` just because an external service (database, remote cache, API, DNS) temporarily fails.** If the liveness probe fails, the orchestration platform may repeatedly restart the pod. When multiple pods share an external dependency, this even triggers a cascading restart disaster. For external incidents where the application can still recover, consider readiness and appropriate recovery/backoff.

### 2.3. Two Independent Axes

| Scenario | Liveness | Readiness | Explanation |
| --- | --- | --- | --- |
| Startup complete, capable of serving | `CORRECT` | `ACCEPTING_TRAFFIC` | Ready for new work |
| Starting up, runners unfinished | May already be `CORRECT` | `REFUSING_TRAFFIC` | Context refreshed, not ready yet |
| Temporary overload, need to reduce traffic | `CORRECT` | `REFUSING_TRAFFIC` | No restart needed; prioritize recovery |
| Unrecoverable internal state | `BROKEN` | Policy-dependent | Liveness probe may trigger a restart |
| Graceful shutdown in progress | Usually still `CORRECT` at start of stop | `REFUSING_TRAFFIC` | Stop new work and finish in-flight work |

Do not try to represent every problem as `LivenessState.BROKEN`. When needed, readiness can toggle back and forth multiple times throughout the application's lifetime.

## 3. When Does Spring Boot Publish AvailabilityChangeEvent Automatically?

During a successful startup:

```text
ApplicationContext.refresh()
   |
   +-- ApplicationStartedEvent
   +-- AvailabilityChangeEvent(LivenessState.CORRECT)
   |
   +-- ApplicationRunner / CommandLineRunner
   |
   +-- ApplicationReadyEvent
   +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
   |
   +-- SpringApplication.run(...) returns
```

Spring Boot considers the application **live** once the context refreshes successfully, and **ready** once runners return normally.

Key points:

- `ApplicationStartedEvent` and `ApplicationReadyEvent` are **not synonymous** with `AvailabilityChangeEvent`.
- Boot publishes `LivenessState.CORRECT` **after** `ApplicationStartedEvent`.
- Boot publishes `ReadinessState.ACCEPTING_TRAFFIC` **after** `ApplicationReadyEvent`.
- While startup is incomplete, readiness normally refuses traffic.
- During shutdown/graceful shutdown, readiness normally transitions to refusing traffic; hooks/lifecycle behavior depend on application type and configuration.
- If a runner throws an exception, the successful startup flow never reaches the normal ready milestone.

**Common trap:** If you publish `ReadinessState.REFUSING_TRAFFIC` right inside an `ApplicationReadyEvent` listener, after that listener returns **Spring Boot still publishes `ReadinessState.ACCEPTING_TRAFFIC`** along the standard startup path. Your earlier self-published value can be overwritten. Do not use a ready listener to "lock readiness forever" without accounting for startup order. If a mandatory condition must be ensured before ready, control the runner's work or lifecycle with explicit timeouts and error handling; only after startup should dynamic state be used to temporarily refuse traffic when conditions change.

## 4. APIs to Proactively Publish Events

### 4.1. Approach 1: With ApplicationContext

Convenience signature in Spring Boot 3.3:

```java
public static <S extends AvailabilityState> void publish(
        ApplicationContext context, S state);
```

This is an **illustrative API signature**, not a method declaration in your application. Usage example after the context is ready:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC);
```

`applicationContext` must be a valid Spring `ApplicationContext`, usually obtained via dependency injection or returned by `SpringApplication.run(...)`. This API publishes an application event to the specified context.

This approach is convenient in application-level coordination code, admin utilities, or demo code already holding a context reference.

### 4.2. Approach 2: With ApplicationEventPublisher and Source

Another convenience signature:

```java
public static <S extends AvailabilityState> void publish(
        ApplicationEventPublisher publisher, Object source, S state);
```

Example:

```java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        ReadinessState.REFUSING_TRAFFIC);
```

This is an **illustrative snippet inside a bean with an `eventPublisher` variable**. Use constructor injection to receive the publisher; `this` is the source indicating which component requested the state change. If the change was triggered by an exception, you can pass the exception as the source for observability, while avoiding logging payloads containing secrets.

**There is no two-parameter overload `(ApplicationEventPublisher, ReadinessState)` in Spring Boot 3.3.13.** If you only have an `ApplicationEventPublisher`, use the three-parameter overload or publish the event object directly.

### 4.3. Approach 3: Publishing the Event Object Directly

Equivalent mechanism:

```java
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this, ReadinessState.REFUSING_TRAFFIC));
```

This is an **illustrative snippet**; import `org.springframework.boot.availability.AvailabilityChangeEvent`, `ReadinessState`, and declare `publisher` of type `ApplicationEventPublisher`.

Although you can use the constructor, prefer the static `publish(...)` method to express intent clearly. **Do not just instantiate `new AvailabilityChangeEvent<>(...)` without passing it to a publisher**: an unpublished object will never reach the `ApplicationAvailability` bean.

### 4.4. Example Transitioning Back to ACCEPTING_TRAFFIC

Once the cause of temporary refusal is resolved and the system can genuinely accept work, proactively publish:

```java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        ReadinessState.ACCEPTING_TRAFFIC);
```

Do not automatically switch back to accepting after a fixed delay if the underlying cause still persists. Verify recovery conditions via a state machine, health checks, or business checks.

### 4.5. Example Reporting an Unrecoverable Internal Fault

```java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        LivenessState.BROKEN);
```

This signal **requires great caution**. It does not directly call `System.exit`, does not guarantee Kubernetes restarts immediately, and does not fix corrupted state by itself. Its effect in deployment depends on whether the platform reads the liveness probe or an equivalent mechanism.

## 5. Reading State After Publishing an Event

Inject `org.springframework.boot.availability.ApplicationAvailability`:

```java
@Component
public class StateReporter {

    private final ApplicationAvailability availability;

    public StateReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public ReadinessState readiness() {
        return availability.getReadinessState();
    }

    public LivenessState liveness() {
        return availability.getLivenessState();
    }
}
```

This is an **illustrative bean template**, requiring imports for `@Component`, `ApplicationAvailability`, `ReadinessState`, and `LivenessState`.

Important APIs:

| API | Meaning |
| --- | --- |
| `getReadinessState()` | Current readiness state |
| `getLivenessState()` | Current liveness state |
| `getState(ReadinessState.class)` | State of a specified state type; may have no prior event yet |
| `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)` | State, or default value if no event has occurred yet |
| `getLastChangeEvent(ReadinessState.class)` | Most recent event for readiness, which may not exist yet |

When using `getLastChangeEvent`, handle the `null` case before any event arrives:

```java
AvailabilityChangeEvent<ReadinessState> last =
        availability.getLastChangeEvent(ReadinessState.class);
if (last != null) {
    System.out.println("Latest readiness: " + last.getState());
}
```

**Do not confuse state with event:** `getReadinessState()` returns an enum, not an event. `getLastChangeEvent(...)` lets you inspect the state along with event metadata (such as source and timestamp) if you need auditing.

Normally, with the default publisher and synchronous listeners in a started context, the `ApplicationAvailability` bean updates while the event is handled. If you customized the global event multicaster to be asynchronous, do not assume every listener finishes immediately when `publish` returns; test your actual configuration.

## 6. Receiving State-Change Events with Listeners

A Spring bean can receive readiness events:

```java
@Component
public class ReadinessObserver {

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.REFUSING_TRAFFIC) {
            System.out.println("Stop taking new work");
        }
        else {
            System.out.println("Ready to accept new work");
        }
    }
}
```

This is an **illustrative sample**, requiring imports for `@Component`, `@EventListener`, `AvailabilityChangeEvent`, and `ReadinessState`.

Because `AvailabilityChangeEvent` carries a generic state type and supports `ResolvableType`, listeners can distinguish:

```java
@EventListener
void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    // readiness only
}

@EventListener
void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
    // liveness only
}
```

The two methods above are **illustrative snippets placed inside a Spring bean**, not a standalone Java file. In real applications, `ApplicationListener` can also be used to receive similar events.

Listeners should be concise and avoid heavy I/O that blocks the publishing thread. If a listener is offloaded to an async executor, handle completion ordering, exceptions, retries, and the absence of transaction/request contexts.

**Important consequence:** A listener can receive events both **automatically emitted by Spring Boot** and **proactively published by the application**. Do not assume an observed event necessarily came from your own `publish(...)` call; inspect the event's source and timing to diagnose.

## 7. Complete Example — Java 21 and Spring Boot 3.3.13

This example uses a **non-web** application with these components:

1. `AvailabilityDemoApplication`: boots Spring Boot and performs state transitions after `run(...)` completes.
2. `ReadinessController`: proactively publishes `REFUSING_TRAFFIC` then `ACCEPTING_TRAFFIC` via `ApplicationEventPublisher`.
3. `AvailabilityObserver`: prints each received readiness/liveness event.
4. `ApplicationAvailability`: reads the actual state after each publication.

### 7.1. Directory Structure

```text
availability-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/availability/
    │       ├── AvailabilityDemoApplication.java
    │       ├── ReadinessController.java
    │       └── AvailabilityObserver.java
    └── test/
        └── java/com/example/availability/
            └── ReadinessControllerTest.java
```

### 7.2. Maven pom.xml

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>availability-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
```

`spring-boot-starter` supplies the components for a CLI app; `spring-boot-starter-test` supplies test tooling. The demo has no Actuator or HTTP server; probe configuration for production is covered in a separate section.

### 7.3. Component Proactively Changing Readiness

File `src/main/java/com/example/availability/ReadinessController.java`:

```java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ReadinessController {

    private final ApplicationEventPublisher publisher;

    public ReadinessController(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void pauseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Each method only emits a signal. It **does not stop** an HTTP server and **does not configure** Kubernetes or a load balancer by itself. In production, external infrastructure must read the readiness probe or suitable service discovery to actually adjust traffic.

### 7.4. Listener Observing Both State Types

File `src/main/java/com/example/availability/AvailabilityObserver.java`:

```java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityObserver {

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("EVENT readiness=" + event.getState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("EVENT liveness=" + event.getState());
    }
}
```

`@EventListener` here receives **both Boot's automatic events** and events published by `ReadinessController`. The events have distinct generic types, so the two methods do not get mixed up.

### 7.5. Main Executing Transitions After App Ready

File `src/main/java/com/example/availability/AvailabilityDemoApplication.java`:

```java
package com.example.availability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class AvailabilityDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(AvailabilityDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);
            ReadinessController controller =
                    context.getBean(ReadinessController.class);

            System.out.println("MAIN initial="
                    + availability.getReadinessState());

            controller.pauseNewTraffic();
            System.out.println("MAIN paused="
                    + availability.getReadinessState());

            controller.resumeNewTraffic();
            System.out.println("MAIN resumed="
                    + availability.getReadinessState());
        }
    }
}
```

**Why change state after `app.run(args)`?** Along the successful startup path, Spring Boot already emitted `ApplicationReadyEvent` and the `ReadinessState.ACCEPTING_TRAFFIC` event before `run` returned. The demo therefore observes an application-initiated change **during runtime after startup**, without being overwritten by Boot's final startup readiness publication.

`try-with-resources` closes `ConfigurableApplicationContext` after the demo finishes printing. While the context closes, Boot's availability/shutdown listeners may publish additional events; they do not invalidate the lines observed **before closing**.

### 7.6. Build and Run

Requires JDK 21, Maven, and dependency download access:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/availability-demo-0.0.1-SNAPSHOT.jar
```

Lines printed by the example code **through `MAIN resumed`**, filtering out Spring Boot banners/logs, must follow this order:

```text
EVENT liveness=CORRECT
EVENT readiness=ACCEPTING_TRAFFIC
MAIN initial=ACCEPTING_TRAFFIC
EVENT readiness=REFUSING_TRAFFIC
MAIN paused=REFUSING_TRAFFIC
EVENT readiness=ACCEPTING_TRAFFIC
MAIN resumed=ACCEPTING_TRAFFIC
```

After code exits the `try` block, Spring closes the context and there may still be logs or shutdown-related availability events. **The block above describes only the part before context close, not the entire stdout.**

Explanation:

- The `CORRECT` event is the liveness event Boot publishes after context refresh.
- The first `ACCEPTING_TRAFFIC` event is the readiness event Boot publishes after runners and the ready event.
- `MAIN initial` reads accepting because `SpringApplication.run` has completed.
- `controller.pauseNewTraffic()` emits refusing; the listener receives it and `ApplicationAvailability` records it.
- `controller.resumeNewTraffic()` emits accepting again.
- Because the default multicaster is synchronous, in this demo state can be read right after `publish` returns; if you change dispatching, adjust tests/synchronization accordingly.

### 7.7. Trying the ApplicationContext Overload Directly

You can replace the controller call in `main` with:

```java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
```

This is an **illustrative snippet inside `try` where `context` exists**; not a standalone program. In this example, after publishing via `context`, the listener still receives `AvailabilityChangeEvent<ReadinessState>` and `ApplicationAvailability` records the new state.

## 8. Testing with Spring Boot Test

To verify the contract for proactively changing readiness, use an integration test that actually creates the context and the `ApplicationAvailability` bean, then publishes and asserts. No web server is needed.

File `src/test/java/com/example/availability/ReadinessControllerTest.java`:

```java
package com.example.availability;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = AvailabilityDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ReadinessControllerTest {

    @Autowired
    private ReadinessController controller;

    @Autowired
    private ApplicationAvailability availability;

    @Test
    void publishesAndTracksReadinessChanges() {
        controller.pauseNewTraffic();
        assertEquals(ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());

        controller.resumeNewTraffic();
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
    }
}
```

The test uses real beans and the default multicaster. `@DirtiesContext` prevents the test context from being reused with state mutated by the test. Checking initial test state is unnecessary because the state after each call is the contract to prove.

If a project customized the multicaster to async, immediate assertions after `publish` may no longer apply; configure the test to match actual dispatching or use synchronization/polling with a timeout.

### 8.1. Why Not Just Instantiate an Event and Assert?

The snippet below does not test Boot's state-updating capability:

```java
new AvailabilityChangeEvent<>(
        this, ReadinessState.REFUSING_TRAFFIC);
```

It only constructs an event object, **without publishing it**. A proper test must use a publisher/context so Boot receives the event.

### 8.2. Why Testing the Controller Directly Is Still Insufficient

A unit test that only mocks `ApplicationEventPublisher` and verifies `publishEvent(...)` confirms the controller emitted an event, yet **does not prove** the `ApplicationAvailability` bean updated. The integration test above verifies both event publication and recorded state.

### 8.3. Avoid Side Effects on Other Tests

If a test only checks one state and finishes, restore the original state in `finally` or mark the context not to be reused. Letting `REFUSING_TRAFFIC` leak into other tests can make test results flaky, especially when the test suite uses context caching.

## 9. Using Actuator to Connect State to Probes

In a **web** application with Spring Boot Actuator, availability states can be exposed via health groups:

- **Liveness probe**: typically at `/actuator/health/liveness`.
- **Readiness probe**: typically at `/actuator/health/readiness`.

**The section 7 demo is non-web and lacks Actuator, so it does not open these two URLs.** To test HTTP probes, change application configuration and dependencies; calling `AvailabilityChangeEvent.publish(...)` alone will not make HTTP endpoints appear.

### 9.1. Additional Dependencies for Web Applications

Use `spring-boot-starter-web` and `spring-boot-starter-actuator` in a Spring Boot web project (this is an **expanded configuration**, not the full POM from section 7):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Remove `app.setWebApplicationType(WebApplicationType.NONE)` so Boot auto-selects a servlet web app. Probes can be enabled with:

```properties
management.endpoint.health.probes.enabled=true
```

When you need health groups on the main port for Kubernetes, look at `management.endpoint.health.probes.add-additional-paths=true` (additional liveness/readiness paths on the main server port; check exposure and security). **Do not indiscriminately expose** all management endpoints. When deploying, confirm the exact port, base path, security, service mesh, proxy, and health groups.

### 9.2. How Probes Change When State Is Published

In a web app with Actuator/probes enabled, the conceptual sequence:

```text
Serving:
    ReadinessState.ACCEPTING_TRAFFIC
    -> /actuator/health/readiness reports UP
    -> platform can route traffic

Temporarily pausing new work:
    AvailabilityChangeEvent.publish(..., REFUSING_TRAFFIC)
    -> ReadinessState.REFUSING_TRAFFIC
    -> readiness health group reports OUT_OF_SERVICE
    -> typically reflected via HTTP 503
    -> platform stops routing to pod once next probe detects it

Recovering:
    publish(..., ACCEPTING_TRAFFIC)
    -> readiness health group reports UP again
    -> platform can route traffic once probe passes
```

This is the behavioral model **when probes and default status mappings apply**, not a promise that the load balancer stops sending requests immediately. Kubernetes probes have periods, failure thresholds, and endpoint update delays. In-flight traffic may continue; if connections must drain, combine appropriate shutdown/routing mechanisms.

### 9.3. Do Not Confuse Readiness Health with Liveness Health

If you only publish `ReadinessState.REFUSING_TRAFFIC`, liveness can stay `CORRECT`. The goal is to **pull out of traffic**, not **request a restart**. Only emit `LivenessState.BROKEN` in a genuinely unrecoverable internal situation.

Likewise, do not tie liveness directly to external services. A shared database outage should not cause every pod to restart endlessly just because the liveness probe checks the database.

### 9.4. `AvailabilityChangeEvent` Does Not Force Request-Handling Code to Reject

The application **announces state**, while reducing traffic requires the orchestration environment to act. Without a load balancer/probe reading state, your service can still receive HTTP requests even when `ApplicationAvailability` reports `REFUSING_TRAFFIC`. When the app itself must reject requests, add appropriate filtering/routing logic; changing availability state alone is not request-blocking middleware.

## 10. Practical Design Pattern: Temporary Load Shedding and Recovery

A task-processing service can sometimes overload due to queues or memory. Using readiness to announce "temporarily not taking more work" can make sense:

```text
RUNNING
  | queue depth exceeds high threshold for a stable window
  v
PAUSED (REFUSING_TRAFFIC)
  | backlog drops below low threshold for a stable window
  v
RUNNING (ACCEPTING_TRAFFIC)
```

**Hysteresis** (distinct high and low thresholds) prevents rapid state oscillation when metrics hover near one threshold. You can add a minimum interval between transitions, essential dependency health checks, and concrete recovery criteria.

### 10.1. Orchestration Pseudo-Code Example

```java
if (queueDepth >= highWatermark && currentlyAccepting) {
    AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.REFUSING_TRAFFIC);
}
else if (queueDepth <= lowWatermark && currentlyRefusing
        && dependenciesHealthy) {
    AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
}
```

**This is Java pseudo-code**, not a standalone compilable file: `queueDepth`, thresholds, check flags, and dependencies must be defined. For production, avoid unsynchronized local flags across threads; use a coordinator/state machine with proper contention protection.

### 10.2. Multiple Components Can Publish Readiness Simultaneously

Dangerous problem: A emits `REFUSING_TRAFFIC` because the database is not ready; B emits `ACCEPTING_TRAFFIC` because the cache finished. If every component publishes the final state itself, **a newer event can overwrite the state from another component** even though A's refusal reason still holds.

Have **one readiness coordinator** aggregate all reasons:

```text
databaseHealthy AND cacheReady AND queueCapacityAvailable
        => ACCEPTING_TRAFFIC
otherwise
        => REFUSING_TRAFFIC
```

Each component updates its own status with the coordinator; only the coordinator proactively publishes availability events from the combined result. This prevents "last writer wins" from causing false readiness.

### 10.3. Avoid Reporting ACCEPTING_TRAFFIC Too Early

If a mandatory cache warm-up job only just started asynchronously, emitting `ACCEPTING_TRAFFIC` is premature. Finish the actual work with deadlines/timeouts, confirm real status, and only then transition to accepting. For startup tasks that must block ready, prefer running/waiting inside `ApplicationRunner` or a lifecycle-aware startup coordinator.

### 10.4. Liveness State Is a Serious Operational Decision

`LivenessState.BROKEN` should be reserved for unrecoverable internal faults: such as irrecoverable corruption of core internal state. Do not use it to report high latency or transient external dependency timeouts. A `BROKEN` event does not close the context by itself; matching infrastructure and operational runbooks are required.

## 11. Common Mistakes

| Mistake or Misconception | Harm | How to Fix |
| --- | --- | --- |
| Calling `availability.setReadinessState(...)` | No such setter exists in the API | Publish `AvailabilityChangeEvent` |
| Calling `AvailabilityChangeEvent.publish(publisher, state)` | Does not match Boot 3.3 overloads | Use `(publisher, source, state)` or `(context, state)` |
| Creating `new AvailabilityChangeEvent` without publishing | Boot's state does not change | `publisher.publishEvent(...)` or static `publish(...)` |
| Emitting refusing in `ApplicationReadyEvent` listener to hold permanently | Boot publishes accepting right after the ready event | Align lifecycle properly; emit after startup for dynamic changes |
| Emitting liveness `BROKEN` when external DB times out | Pods may restart endlessly | Handle with retry/backoff; consider readiness, not liveness for external faults |
| Thinking readiness refusing closes sockets immediately | Probe only reports state; does not close server | Configure orchestrator/routing and draining |
| Having `AvailabilityChangeEvent` yet health URL doesn't exist | App lacks Actuator/web or probes aren't enabled | Add dependencies, configure probes, and check endpoints |
| Forgetting source in publisher overload | Calls wrong method signature | Pass `this`, exception, or meaningful source object |
| Multiple services publishing `ACCEPTING_TRAFFIC` independently | Healthy component overwrites unhealthy component | Single readiness coordinator aggregating conditions |
| Leaving `REFUSING_TRAFFIC` after app recovers | Instance receives no new traffic | Publish `ACCEPTING_TRAFFIC` once real recovery is confirmed |
| Relying on async event then reading state immediately | Action may not have been processed yet | Use synchronous dispatch or test completion with timeout |
| Doing heavy network I/O inside an availability listener | Delays publishing, startup, shutdown, or risks exceptions | Keep listeners lightweight; offload managed background tasks |
| Logging entire event source unchecked | May expose sensitive data | Log needed state/metadata; do not dump secrets |
| Marking readiness healthy instead of business checks | Misleads load balancer, increases request errors | Only publish accepting when serving criteria are verified |

### 11.1. Diagnostic Checklist

When reading state after publishing still shows the old value:

1. Did you publish via the **right** `ApplicationContext` or `ApplicationEventPublisher`?
2. Did you use the right overload `publish(context, state)` or `publish(publisher, source, state)`?
3. Did another listener or Spring Boot startup/shutdown callback publish a different state afterward?
4. Are there multiple contexts (parent/child) causing events to propagate up or an availability bean to inspect a different context?
5. Is a custom async event multicaster, executor, or event handler causing delay or error?
6. Are multiple components overwriting each other's readiness?
7. Did the application finish startup before you manually changed readiness?
8. Is the Actuator health group/probe actually enabled and read by the platform?

Do not conclude from a single `getReadinessState()` returning the desired value that the load balancer has immediately stopped sending traffic.

## 12. Practical Application Scenarios

### 12.1. Rolling Update Deployment

Before shutting down or draining, the application can switch to `REFUSING_TRAFFIC` to signal the platform to stop sending new requests while giving in-flight requests time to finish. Combine lifecycle/draining with readiness probes rather than emitting the event and exiting immediately.

### 12.2. Queue-Processing Worker

When memory or queues overload, a worker can temporarily refuse new work. If it does not serve HTTP, readiness must be wired into the mechanism the orchestrator/consumer actually uses; a local enum will not automatically pause a Kafka/RabbitMQ consumer. You may need to pause the consumer, lower concurrency, or implement explicit backpressure.

### 12.3. Runtime Configuration Recovery

If the application changes configuration or reloads internally and cannot serve safely yet, publish `REFUSING_TRAFFIC`. Once reload is verified successful, publish `ACCEPTING_TRAFFIC` again. Guard against reload failure; do not reopen traffic merely because a fixed timeout elapsed.

### 12.4. Unrecoverable Local Corruption

If an internal processor is in an unfixable state where only a restart can restore it, consider `LivenessState.BROKEN`. Before putting liveness into a runbook, verify that a restart actually fixes the fault to avoid restart loops while the root cause persists.

### 12.5. Telemetry and Auditing

An `@EventListener(AvailabilityChangeEvent<ReadinessState>)` listener can record counters/metrics for temporary refusals and recovery durations. However, the event listener may also receive Boot's automatic events. For auditing, log timestamp, source, reason code (without leaking secrets), and context instance ID.

## 13. Practice Exercises

1. State the difference between `ReadinessState` and `LivenessState`. When is `BROKEN` more dangerous than `REFUSING_TRAFFIC`?
2. Write Spring Boot 3.3's two official `AvailabilityChangeEvent.publish(...)` overloads. When do you use context vs. publisher + source?
3. Explain why `ApplicationAvailability` is not an object with setters to update state.
4. In the demo, why must you wait for `SpringApplication.run(...)` to return before manually testing readiness transitions?
5. Run the demo and identify the origin of the first liveness `CORRECT` and readiness `ACCEPTING_TRAFFIC` events.
6. Explain why `EVENT readiness=REFUSING_TRAFFIC` prints before `MAIN paused=REFUSING_TRAFFIC` with the default synchronous multicaster.
7. Swap the order of `pauseNewTraffic()` and `resumeNewTraffic()` in `main`; predict the final state before closing the context.
8. Replace `AvailabilityChangeEvent.publish(publisher, this, state)` with `publisher.publishEvent(new AvailabilityChangeEvent<>(this, state))`. Explain why both serve the same purpose.
9. Write a listener receiving only `AvailabilityChangeEvent<LivenessState>` and print `BROKEN` when appropriate; do **not** add an endpoint intentionally reporting broken for production.
10. Explain why Spring Boot can emit accepting after a ready listener emitted refusing.
11. Add an integration test checking two readiness transitions without relying on pre-test state.
12. Build a hypothetical coordinator with two conditions `databaseHealthy` and `cacheReady`. Publish `ACCEPTING_TRAFFIC` only when both are true; explain the risk when two components publish independently.
13. If the load balancer still sends requests after readiness is refusing, which platform factors will you check?
14. Propose hysteresis for queue depth: e.g., high threshold 900 for refusing, low threshold 300 for accepting. Why do two distinct thresholds reduce oscillation?
15. In a CLI app without Actuator, what still happens when `AvailabilityChangeEvent` is published, and what **does not appear automatically**?
16. Why must a `BROKEN` event not be treated as equivalent to calling `System.exit(1)`?
17. Extend the app into a web app with Actuator probes. State the minimal configuration and what to verify before Kubernetes deployment.
18. If a listener processes asynchronously and state changes continuously, how will you test ordering, timeouts, and latest state?
19. Distinguish application readiness state from the health of a separate external service. When is a custom health group endpoint needed?
20. Design readiness states for a queue worker, including stopping new work, finishing in-flight work, and recovering, without restarting the process.

**Pass criteria:** explain and use the event API properly; proactively publish `REFUSING_TRAFFIC`/`ACCEPTING_TRAFFIC`; read new state with `ApplicationAvailability`; understand Boot emits automatic events; recognize the limits of liveness, readiness, and platform interaction.

## 14. Official Documentation

- Spring Boot 3.3.13 — `AvailabilityChangeEvent` API (two `publish` overloads): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.3.13 — `ApplicationAvailability` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.3.13 — `ReadinessState` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ReadinessState.html
- Spring Boot 3.3.13 — `LivenessState` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html
- Spring Boot 3.3.13 — Application Availability & Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — Actuator endpoints/probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
