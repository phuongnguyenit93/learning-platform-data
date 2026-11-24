# Observing Changes via `AvailabilityChangeEvent`

In Spring Boot, the fact that an application **has finished creating its beans** does not mean the application **is ready to accept traffic**. A service may still be starting up, running data-preparation tasks, temporarily pausing request acceptance for maintenance, or shutting down. To observe these milestones consistently, Spring Boot provides **Application Availability** and **`AvailabilityChangeEvent`** events.

This lesson belongs to the **Readiness State** section of the **Spring Boot Application Runtime** module, focusing on **how to listen to, read, publish, and verify liveness/readiness changes via events**. The APIs and examples are based on **Spring Boot 3.3.x / Spring Framework 6.1, Java 17+**.

Learning objectives:

- Distinguish **liveness** (is the application still in a healthy/self-recoverable state?) from **readiness** (should it accept traffic right now?).
- Understand `AvailabilityChangeEvent<S extends AvailabilityState>`, `ApplicationAvailability`, and their corresponding states.
- Write listeners with `@EventListener` or `ApplicationListener` to observe changes.
- Proactively publish `ReadinessState.REFUSING_TRAFFIC` / `ACCEPTING_TRAFFIC` when a component needs to adjust traffic acceptance.
- Verify event ordering across the `SpringApplication.run(...)` lifecycle, without confusing startup logs or `ApplicationReadyEvent` with current readiness.
- Know when internal state is reflected in Spring Boot Actuator and Kubernetes HTTP probes.

## 1. Why Observe Readiness State?

A multi-replica deployment can encounter scenarios such as:

1. **Startup:** Spring has refreshed the context, yet an `ApplicationRunner` is still loading initial data. The application is running at the container level, but should not receive traffic yet.
2. **Normal operation:** Startup tasks complete; the application can serve requests.
3. **Temporary pause:** An internal queue exceeds a threshold or the system performs brief maintenance; the application is still alive, yet should stop accepting **new traffic**.
4. **Recovery:** The cause of the pause is resolved, and the application can accept traffic again.
5. **Shutdown:** The container is about to close; a graceful shutdown mechanism avoids taking new requests and tries to finish in-flight work.

Relying solely on an open TCP port or a `Started ...` log makes it hard to distinguish these states. Spring Boot therefore lets you represent **liveness** and **readiness** at the application level, and uses events to announce state changes.

You must distinguish **published state** from **external observability**. Setting readiness to `REFUSING_TRAFFIC` does not make every reverse proxy or client stop sending requests immediately. Infrastructure (such as Kubernetes) must configure and poll a readiness probe, then update routing; there is a lag between the internal event and its effect on network traffic.

## 2. The Two Dimensions of Application Availability

### Liveness: `LivenessState`

`org.springframework.boot.availability.LivenessState` has two values:

| Value | Meaning | Typical Desired Operational Outcome |
| --- | --- | --- |
| `CORRECT` | Internal state allows the application to keep operating properly or self-recover | Liveness probe should succeed |
| `BROKEN` | The application is broken internally and cannot self-recover | Infrastructure may need to restart the process |

**Do not treat every connection error to a database, Redis, or external API as a reason to switch liveness to `BROKEN`.** A shared dependency failing across many instances can cause infrastructure to repeatedly restart every instance and amplify the outage. Liveness is for severe conditions **of the process itself**.

### Readiness: `ReadinessState`

`org.springframework.boot.availability.ReadinessState` has two values:

| Value | Meaning | Typical Desired Operational Outcome |
| --- | --- | --- |
| `ACCEPTING_TRAFFIC` | The application confirms it can serve new traffic | Readiness probe may allow traffic routing |
| `REFUSING_TRAFFIC` | Temporarily no new traffic should be routed to the application | Readiness probe should report unready |

Readiness can change multiple times within **the same process**: from `REFUSING_TRAFFIC` to `ACCEPTING_TRAFFIC` after startup, back to `REFUSING_TRAFFIC` during maintenance, and recovering to `ACCEPTING_TRAFFIC` without a restart.

### Liveness Is Not Readiness

~~~text
Application is alive but not ready yet:
Liveness = CORRECT
Readiness = REFUSING_TRAFFIC

Application is serving normally:
Liveness = CORRECT
Readiness = ACCEPTING_TRAFFIC
~~~

These two dimensions are semantically independent. **An instance that is alive yet refusing traffic is a completely valid state**, especially during startup or a controlled pause.

## 3. What Is `AvailabilityChangeEvent`?

`AvailabilityChangeEvent<S extends AvailabilityState>` belongs to package:

~~~java
org.springframework.boot.availability
~~~

It is an `ApplicationEvent` carrying a state `S`, where `S` implements the `AvailabilityState` interface. In Spring Boot 3.3, this class extends `PayloadApplicationEvent<S>`.

Notable operations:

| API | Role |
| --- | --- |
| `event.getState()` | Read the liveness/readiness value carried by the event |
| `event.getSource()` | Source of the event, depending on how it was created/published |
| `AvailabilityChangeEvent.publish(context, state)` | Publish an event via an `ApplicationContext` |
| `AvailabilityChangeEvent.publish(publisher, source, state)` | Publish via an `ApplicationEventPublisher` with a caller-specified source |

Conceptual example:

~~~java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
~~~

This snippet requires `context` to be an active `ApplicationContext` and appropriate Spring Boot imports; it is not a standalone runnable program.

**Distinguish between an event and current state:**

- An event is a **point-in-time message**: "Someone just published the value `REFUSING_TRAFFIC`."
- Current state is the **retained value queried** via `ApplicationAvailability`.
- If you miss an event because a listener was registered late, you do **not** automatically receive the full event history. When you only need the latest state, query `ApplicationAvailability`.
- The name "change event" does not mean the framework refuses to publish two consecutive events with the same value. Code emitting events must handle deduplication and idempotency itself if listener actions have side effects.

Events are an **in-application** state-propagation mechanism, not a distributed message broker, and they do not replace infrastructure signals/probes.

## 4. How Does `ApplicationAvailability` Store the Latest State?

`ApplicationAvailability` is an interface you can inject into beans to query current state. Spring Boot provides `ApplicationAvailabilityBean` as the implementation that listens for change events and stores the latest value per state type.

Core APIs:

~~~java
LivenessState liveness = availability.getLivenessState();
ReadinessState readiness = availability.getReadinessState();

ReadinessState state = availability.getState(ReadinessState.class);
AvailabilityChangeEvent<ReadinessState> lastEvent =
        availability.getLastChangeEvent(ReadinessState.class);
~~~

Here `availability` is an injected variable of type `ApplicationAvailability`. The snippet is an **API usage example inside a method**, not a standalone Java file.

- `getLivenessState()` / `getReadinessState()`: read state along the two standard dimensions.
- `getState(ReadinessState.class)`: may return `null` if this state type has never been published via an event, per the API contract.
- `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)`: supply a **fallback** if no event of that type has occurred yet.
- `getLastChangeEvent(ReadinessState.class)`: read the **most recent event** for the state type, which may be absent if the app has not published a corresponding event yet.

Note: default/fallback behavior differs from an event actually having occurred. When an application just starts, `getLastChangeEvent(...)` may still have no value even though a state-reading method returns a sensible default. **Do not infer that every default value was emitted via an `AvailabilityChangeEvent`.**

### Do Not Mutate the Storage Implementation Directly

To report a new state, Spring Boot instructs you to **publish an `AvailabilityChangeEvent`**, rather than trying to mutate internal fields of `ApplicationAvailabilityBean`. Publishing an event gives other listeners and state-tracking components a chance to learn of the change.

~~~java
AvailabilityChangeEvent.publish(
        eventPublisher, this, ReadinessState.REFUSING_TRAFFIC);
~~~

Here `eventPublisher` is an injected `ApplicationEventPublisher`. Many parties may listen to events; only publish when there is a clear business/operational reason.

## 5. Availability Event Order During Spring Boot Startup

Per Spring Boot 3.3 documentation, the success flow directly related to liveness/readiness is:

~~~text
main()
 |
 v
SpringApplication.run(args)
 |
 +-- Prepare Environment and ApplicationContext
 |
 +-- Refresh ApplicationContext
 |
 +-- ApplicationStartedEvent
 |
 +-- AvailabilityChangeEvent<LivenessState>
 |      state = CORRECT
 |
 +-- ApplicationRunner and CommandLineRunner
 |
 +-- ApplicationReadyEvent
 |
 +-- AvailabilityChangeEvent<ReadinessState>
 |      state = ACCEPTING_TRAFFIC
 |
 v
run(args) returns ApplicationContext
~~~

This is a **milestone order** for observation, not an exhaustive list of every event, bean callback, or web server initialization step.

Typical state table:

| Phase | Liveness | Readiness | Condition |
| --- | --- | --- | --- |
| Starting | `BROKEN` | `REFUSING_TRAFFIC` | Context not yet refreshed |
| Context refreshed, running runners | `CORRECT` | `REFUSING_TRAFFIC` | Passed started milestone, not yet past ready |
| Startup completed successfully | `CORRECT` | `ACCEPTING_TRAFFIC` | Runners finished; Spring Boot published ready |

**Three common pitfalls:**

1. **`ApplicationStartedEvent` is not synonymous with `ApplicationReadyEvent`.** The started event occurs before runners, so readiness is normally still `REFUSING_TRAFFIC`.
2. **`ApplicationReadyEvent` is not identical to the readiness event.** Spring Boot emits `AvailabilityChangeEvent<ReadinessState>` with `ACCEPTING_TRAFFIC` **after** `ApplicationReadyEvent`. Inside a handler running *right at* `ApplicationReadyEvent`, do not assume the subsequent readiness event has already been emitted.
3. **`run` may fail**. If startup or a runner throws an exception, the success path never reaches readiness `ACCEPTING_TRAFFIC`; the application may emit `ApplicationFailedEvent`.

A listener for `AvailabilityChangeEvent<ReadinessState>` defined inside the context can still observe the default startup event **because this event happens after context refresh**. You do not need to register via `spring.factories` just to catch normal readiness events.

## 6. Observing Events with `@EventListener`

In most applications, writing a standard bean is sufficient:

~~~java
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
        System.out.println("READINESS changed-to=" + event.getState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("LIVENESS changed-to=" + event.getState());
    }
}
~~~

This is a complete class **when compiled in a Spring Boot 3.3 project with appropriate dependencies**. Both methods have concrete generic types, allowing Spring's listener mechanism to dispatch the matching events.

- `onReadiness(...)` receives events with a `ReadinessState` payload.
- `onLiveness(...)` receives events with a `LivenessState` payload.
- `getState()` gives the **value published by the current event**.
- `@Component` lets Spring register the class in `ApplicationContext` via component scanning.

**Do not use a readiness listener to infer liveness state**, nor rely on the class name of `getSource()` since the publisher may vary by case.

### Writing with `ApplicationListener`

You can use the interface instead of the annotation:

~~~java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessOnlyListener
        implements ApplicationListener<AvailabilityChangeEvent<ReadinessState>> {

    @Override
    public void onApplicationEvent(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS changed-to=" + event.getState());
    }
}
~~~

This is an **alternative** to the previous readiness listener; do not register both if you only want one log line per event.

An `ApplicationListener<AvailabilityChangeEvent<ReadinessState>>` can be registered as a bean because key availability events during startup occur once the context already exists. Only if a library needs to listen for a milestone **before beans are created** must it register early via `SpringApplication.addListeners(...)`, builder, or `spring.factories` depending on that event.

## 7. Publishing Events to Temporarily Pause Traffic

Suppose the service is running, yet needs to temporarily stop taking new requests while recovering a critical cache. Instead of marking the process unlive, the application can **switch readiness to `REFUSING_TRAFFIC`**:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

public class TrafficGate {

    private final ApplicationEventPublisher publisher;

    public TrafficGate(ApplicationEventPublisher publisher) {
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
~~~

Structurally this is a complete Java class (when run in a project with Spring Boot dependencies); for Spring to manage/inject it, register it with `@Component` or `@Bean`. It properly demonstrates calling the overload accepting `ApplicationEventPublisher`, a `source` object, and the state.

Operational flow:

~~~text
Application is accepting traffic
    |
    | publish REFUSING_TRAFFIC
    v
ApplicationAvailability changes readiness
    |
    v
Listener records new state
    |
    v
Probe/readiness endpoint (if configured) reflects state
    |
    v
Infrastructure updates routing after probes
    |
    | pause reason resolved
    | publish ACCEPTING_TRAFFIC
    v
Readiness allows receiving traffic again
~~~

**There is no instantaneous guarantee**: between publishing the event and Kubernetes removing the instance from its endpoints list, there can be lag from probe intervals and orchestration components. If a maintenance operation strictly requires zero new requests, design additional blocking/coordination mechanisms rather than relying solely on the event.

### When Should You Not Switch Liveness to BROKEN?

If an external API is slow yet the application can still fall back or retry on its own, this is usually not a liveness fault. Evaluate whether readiness should pause temporarily and consider a circuit breaker. Switching liveness to `BROKEN` causes orchestration to potentially restart the instance, which does not necessarily solve an external dependency outage.

## 8. Complete Practical Example: Observing Startup and Manually Toggling Readiness

This lab uses **Java 17 + Spring Boot 3.3.13 + Gradle**, running as a **console application**. Neither an HTTP server nor Spring Boot Actuator is needed, because the goal is to verify event publishing/listening and `ApplicationAvailability` **directly inside the JVM**.

### 8.1. Project Structure

~~~text
availability-events-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/availability/
    └── AvailabilityEventsDemo.java
~~~

### 8.2. Gradle Configuration with Proper Dependency Versions

`settings.gradle`:

~~~groovy
rootProject.name = 'availability-events-demo'
~~~

`build.gradle`:

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
    // Gradle native BOM manages Spring Boot module versions.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

The BOM is an essential part of the example: if you only apply the `org.springframework.boot` plugin and declare a versionless dependency **without a dependency management mechanism**, the build may fail to resolve the starter. With the BOM above, `spring-boot-starter` gets the version compatible with Spring Boot 3.3.13.

Use a Gradle version compatible with Spring Boot 3.3 and JDK 17+. The sample project includes only the base starter, so it neither opens an HTTP port nor exposes Actuator endpoints.

### 8.3. Application Class

Create `src/main/java/com/example/availability/AvailabilityEventsDemo.java`:

~~~java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class AvailabilityEventsDemo {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(AvailabilityEventsDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            System.out.println(
                    "MAIN after-run readiness=" + availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            System.out.println(
                    "MAIN paused readiness=" + availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            System.out.println(
                    "MAIN resumed readiness=" + availability.getReadinessState());
        }

        System.out.println("MAIN context closed");
    }

    @Bean
    ApplicationRunner inspectDuringStartup(ApplicationAvailability availability) {
        return args -> System.out.println(
                "RUNNER liveness=" + availability.getLivenessState()
                        + " readiness=" + availability.getReadinessState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("EVENT liveness=" + event.getState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("EVENT readiness=" + event.getState());
    }
}
~~~

Code explanation:

1. `WebApplicationType.NONE` turns the demo into a console app; **Tomcat is not needed** to emit availability events.
2. `@EventListener` on the `@SpringBootApplication` class registers listeners via the context bean after it is created.
3. Spring Boot automatically emits `AvailabilityChangeEvent<LivenessState>` with `CORRECT` after `ApplicationStartedEvent` and before runners.
4. `ApplicationRunner` prints the two current states **before `ApplicationReadyEvent` and the `ACCEPTING_TRAFFIC` readiness event are emitted**.
5. When `run(args)` returns successfully, Spring Boot has already published readiness as `ACCEPTING_TRAFFIC`.
6. Code in `main` explicitly publishes `REFUSING_TRAFFIC` and then `ACCEPTING_TRAFFIC`, showing **a live instance can change readiness multiple times**.
7. `try-with-resources` calls `context.close()` at the end, releasing Spring resources per the context-closing contract.

### 8.4. Run

With Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper yet but a compatible Gradle is installed:

~~~bash
gradle bootRun
~~~

During a successful run with the demo configuration, **the main lines produced by `System.out.println` in the code above**, in order, include:

~~~text
EVENT liveness=CORRECT
RUNNER liveness=CORRECT readiness=REFUSING_TRAFFIC
EVENT readiness=ACCEPTING_TRAFFIC
MAIN after-run readiness=ACCEPTING_TRAFFIC
EVENT readiness=REFUSING_TRAFFIC
MAIN paused readiness=REFUSING_TRAFFIC
EVENT readiness=ACCEPTING_TRAFFIC
MAIN resumed readiness=ACCEPTING_TRAFFIC
~~~

This is a **milestone sequence for reference**, not a promise of strictly eight stdout lines. During context closing, Spring Boot may emit an **additional** `REFUSING_TRAFFIC` readiness event, so the listener may print one more line before `MAIN context closed`. There may also be logs from Spring Framework or Gradle. Output can differ if you add listeners, runners, or configurations customizing availability handling.

Two conclusions from the demo:

- **Liveness does not change** when the application manually switches readiness from accepting to refusing traffic and back.
- **`AvailabilityChangeEvent` is not only for startup.** Business components can publish it while the application is running to drive readiness signals.

### 8.5. Observe-Only Variant Without Changes

If the goal is purely **observation**, remove the two `AvailabilityChangeEvent.publish(...)` calls in `main`. Keep the `onReadiness` and `onLiveness` listeners along with the `ApplicationAvailability` read. The application will still emit normal lifecycle events; you simply will not trigger extra readiness transitions.

To keep application code running long-term in the JVM, use a web server or an appropriate process-management mechanism. The console demo intentionally closes the context to exit cleanly for observation; **do not use the console app exiting on its own to infer real web-application behavior**.

## 9. Reading State Inside a Listener: A Note on Event Ordering

When receiving `AvailabilityChangeEvent<ReadinessState>`:

~~~java
@EventListener
public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    ReadinessState announced = event.getState();
    System.out.println("Event state = " + announced);
}
~~~

`event.getState()` is the **exact value being announced**, so this is the clearest way to log state transitions.

Do not carelessly replace it with:

~~~java
@EventListener
public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    System.out.println(availability.getReadinessState());
}
~~~

and assume that result always matches the just-received event in all circumstances. Because `ApplicationAvailabilityBean` also receives the event and updates the snapshot, **listener execution order can affect the snapshot value seen inside a callback**, especially with a custom multicaster. If you need the state of **the event currently being handled**, use `event.getState()`; if you need the **current value for acting after events have been dispatched**, query `ApplicationAvailability` at the appropriate time.

In the default setup, Spring's event multicaster dispatches synchronously, and `publish(...)` returns after synchronous listeners finish. Yet with an async executor/multicaster, ordering and immediacy must be verified separately. Do not bake the assumption "every listener runs synchronously" into business logic.

## 10. Recording Only Actual Transitions to Avoid Repeated Side Effects

Events may be published repeatedly with the same state. To prevent a listener from executing expensive side effects multiple times, keep the most recently processed state.

Illustrative example:

~~~java
@Component
public class ReadinessChangeLogger {

    private final AtomicReference<ReadinessState> last =
            new AtomicReference<>();

    @EventListener
    public void observe(AvailabilityChangeEvent<ReadinessState> event) {
        ReadinessState next = event.getState();
        ReadinessState previous = last.getAndSet(next);
        if (previous != next) {
            System.out.println("Readiness " + previous + " -> " + next);
        }
    }
}
~~~

This is an **illustrative class snippet**, requiring imports for `java.util.concurrent.atomic.AtomicReference`, `ReadinessState`, `AvailabilityChangeEvent`, `@Component`, and `@EventListener` to compile in a Spring Boot project. `AtomicReference` prevents simple unsynchronized read/write issues if events are emitted from multiple threads. It does **not** turn event sequences into distributed transactions or guarantee global ordering when multiple publishers operate concurrently.

Although deduplication is useful, consider:

- When the listener is newly created, `previous` can be `null`; a log "`null → ACCEPTING_TRAFFIC`" simply means **the first time this listener observed it**, not necessarily that the application previously lacked readiness.
- In systems with multiple contexts or multiple application instances, each listener has its own local state.
- If handling an event fails, storing `last` and ignoring repeated events could miss retries. Critical side effects need their own retry/recording mechanism.
- If a listener is only for logging, deduplication logic may be unnecessary; sometimes logging every publication helps diagnostics.

## 11. Connecting to Spring Boot Actuator and Readiness Probes

`AvailabilityChangeEvent` is an **internal** Spring Boot event. To let external infrastructure see the state over HTTP, a web application needs **Spring Boot Actuator** configured with appropriate health groups enabled.

In a Spring Boot 3.3 project with web starter and Actuator, example dependencies:

~~~groovy
dependencies {
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

This is a **replacement/adjusted configuration snippet** in a valid Gradle Spring Boot project; do not add web starter to the console demo above if you only want to follow stdout.

Spring Boot Actuator can expose two health groups:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

In Kubernetes, Spring Boot can enable these probe groups automatically when it detects a Kubernetes environment. When testing **outside Kubernetes**, enable them manually:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

If you need probes on the **same main HTTP port** rather than only a separate management port, Spring Boot also supports:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

When this option is enabled, you can check:

~~~text
GET /livez
GET /readyz
~~~

on the main application port, depending on the system's web/management configuration.

### Internal State Does Not Equal HTTP Results at Every Moment

- `ApplicationAvailability` stores the current state in the JVM.
- Actuator turns the state into the health result of the readiness/liveness group when the endpoint is available and configured.
- Infrastructure performs HTTP probes and acts on results for routing/restarts.
- While the application has not opened its port yet or is shutting down, probes **may not be reachable**, even though internal state already exists.

For example, when readiness is `REFUSING_TRAFFIC`, the readiness health group typically fails and may yield HTTP 503 per status mapping. Yet **not every system calling the probe is guaranteed to receive an HTTP 503**: if the app has not opened the port yet or the load balancer already removed the instance, connections may be refused or handled at the infrastructure layer.

### Sample Kubernetes Configuration

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

This is an **excerpt of `containers[]` in a Pod/Deployment**, not a complete Kubernetes manifest; port `8080` assumes the application actually exposes Actuator health on that port. If using a separate management port or different `management.endpoints.web.base-path`, adjust the probe accordingly.

**Do not make liveness strictly depend on an external service.** If a shared Redis failure causes all liveness probes to fail, Kubernetes may repeatedly restart every replica. Readiness may need to consider certain mandatory dependencies, yet pulling a shared dependency into readiness can cause **all instances to be removed from traffic** at once. Decide based on fallback capability and business requirements.

## 12. Operational Limits of Readiness Events

An `AvailabilityChangeEvent` **does not automatically** perform any of the following:

| Desired Behavior | Does the Event Do It Alone? | What Else Is Needed |
| --- | --- | --- |
| Change internal readiness/liveness value | Yes, via Spring Boot's event/availability system | Event published in the appropriate context |
| Log every readiness change | Yes, if a listener exists | Listener writing logs/metrics |
| Change Actuator readiness probe result | Yes, when Actuator tracks state | Depends on Actuator, health group, and active endpoint |
| Remove instance from Kubernetes Service instantaneously | **No** | Kubelet probes, EndpointSlice, and routing infrastructure |
| Block all requests already arrived or in flight | **No** | Server middleware, graceful shutdown, or dedicated request gating |
| Close the entire `ApplicationContext` automatically | **No** | Context close call or valid shutdown |
| Restart the process automatically when `BROKEN` | **No** | Monitoring system and restart policy |
| Check every application dependency automatically | **No** | Health indicators, business checks, circuit breakers |
| Persist state history across restarts | **No** | External logging, metrics, or storage systems |

Thus, events are an **application-level observation and coordination hook**, not a complete solution for traffic management.

## 13. When Multiple Event Sources Exist

A real-world application may have multiple readiness publishers:

- Spring Boot itself emits `ACCEPTING_TRAFFIC` after successful startup.
- A maintenance coordinator emits `REFUSING_TRAFFIC` to pause.
- An overload controller emits `REFUSING_TRAFFIC` when limits are exceeded.
- A cache-recovery handler emits `ACCEPTING_TRAFFIC` when the system recovers.
- Shutdown processing emits `REFUSING_TRAFFIC` when the app is about to stop.

If these components publish independently, they can **overwrite each other's valid states**. For example, the app is overloaded; maintenance just finished and publishes `ACCEPTING_TRAFFIC` even though overload persists.

A better solution is to **centralize readiness decisions**:

~~~text
Maintenance requested?  ----yes----\
Overload active?         ----yes-----+--> REFUSING_TRAFFIC
Required local setup ok? ----no-----/
                                   
All conditions satisfied -----------> ACCEPTING_TRAFFIC
~~~

A dedicated service can maintain the set of "not ready" reasons and only publish `ACCEPTING_TRAFFIC` when **no blocking reasons remain**. Each component updates its own condition rather than unilaterally publishing ACCEPTING.

Similarly, consider **race conditions** when multiple threads emit events. The default event system is synchronous per publish call, yet does not provide an atomic transaction spanning all publishers and external side effects. If readiness affects critical traffic, design synchronization, idempotency, and monitoring of published state.

## 14. Observing When the Application Prepares to Shut Down

Upon receiving a normal shutdown signal, Spring Boot can transition readiness to `REFUSING_TRAFFIC` and execute graceful shutdown per configuration. Therefore, readiness listeners can continue receiving events **after the application has been running for a while**, not only during startup.

Example graceful shutdown configuration in a web application:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Explanation:

- `server.shutdown=graceful` asks the server to support stopping new requests and waiting for in-flight requests under the integration contract.
- `spring.lifecycle.timeout-per-shutdown-phase` specifies the wait timeout per phase for components stopped by `LifecycleProcessor`.
- Coordinate with container/OS termination deadlines; if killed forcibly, listeners and shutdown hooks may not finish running.
- Do not treat a `ContextClosedEvent` as proof that all HTTP requests have finished. Stopping/cleanup may continue after the event.

**Be cautious inside shutdown listeners:** trying to invoke an already-destroyed bean, spawning new threads, or performing long I/O inside an event callback can delay or break shutdown. For work that must finish before stopping, design an explicit shutdown mechanism rather than relying on availability event logs.

## 15. Common Pitfalls When Observing `AvailabilityChangeEvent`

| Symptom | Possible Cause | How to Diagnose |
| --- | --- | --- |
| Only see `ACCEPTING_TRAFFIC` readiness event, not `REFUSING_TRAFFIC` at startup start | `REFUSING_TRAFFIC` may be the default state before any event is emitted; listener beans do not exist very early | Distinguish default state from actual events; read `ApplicationAvailability` |
| `@EventListener` listener does not run | Class is not a bean, outside component scan, or generic event mismatch | Check `@Component`/`@Bean` and `AvailabilityChangeEvent<ReadinessState>` type |
| `ApplicationStartedEvent` ran, yet readiness is still `REFUSING_TRAFFIC` | Runners/`ApplicationReadyEvent` have not completed yet | This is normal ordering, not a bug |
| `ApplicationReadyEvent` fired, yet `ACCEPTING_TRAFFIC` event not seen inside that handler | Readiness event is emitted **after** `ApplicationReadyEvent` | Observe `AvailabilityChangeEvent<ReadinessState>` directly |
| Log caught readiness, yet HTTP query still differs | Probes not enabled, cached, infrastructure lag, different endpoint/port | Check Actuator health groups and exposed ports |
| Set readiness `REFUSING_TRAFFIC`, yet requests still arrive | Infrastructure has not probed/updated yet, old requests in flight, or no probe | Inspect kubelet settings, interval, paths, and extra blocking mechanisms |
| Set liveness `BROKEN` on external database outage and Pods restart endlessly | Confused external dependency outage with unrecoverable internal fault | Use readiness/circuit breakers instead |
| Listener logs duplicates | Two registrations for same logic, multiple instances, or repeated event publishing | Check registration points, event types, and idempotent design |
| `getLastChangeEvent(...)` returns `null` | No corresponding event has occurred yet | Check startup/registration timing and use explicit fallbacks |
| Listener depends on an unready bean | Registered too early and accessed container before refresh | Choose an appropriate event milestone or use a bean listener after refresh |
| One component reports ACCEPTING too early | Multiple uncoordinated publishers | Centralize readiness policy; transition only when all conditions are met |
| No events seen when JVM is forcibly killed | Shutdown hooks and Spring close did not execute fully | Rely on process management infrastructure and data recovery mechanisms |

### Case of an Overly Broad Generic Listener

~~~java
@EventListener
public void onAnyAvailability(AvailabilityChangeEvent<?> event) {
    System.out.println(event.getState());
}
~~~

This snippet illustrates a listener observing **every AvailabilityState**, not only readiness. To log the two types separately, check `event.getState() instanceof ReadinessState` or use two handlers with specific generic types. Do not cast the payload to readiness without checking the type.

## 16. Testing and Verification

### Simple Verification via the Example Code

In the console demo, verify:

1. Liveness `CORRECT` event occurs before the runner.
2. The runner sees `CORRECT` + `REFUSING_TRAFFIC`.
3. After the runner, the readiness `ACCEPTING_TRAFFIC` event occurs.
4. After `run`, `ApplicationAvailability.getReadinessState()` is `ACCEPTING_TRAFFIC`.
5. When `REFUSING_TRAFFIC` is published, the listener prints the new value; reading the snapshot again confirms it.
6. When `ACCEPTING_TRAFFIC` is published, the listener and snapshot reflect recovery.
7. If you add a shutdown listener/log, you can observe a readiness transition event when the context closes.

### Testing with a Web App + Actuator

If the web app exposes Actuator, run in a test environment:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

Repeat before and after a controlled component publishes `REFUSING_TRAFFIC`, and then `ACCEPTING_TRAFFIC`. When readiness is healthy, the health group normally returns a success code; when refusing, the health group may return a service-unavailable error per status mapping. **Do not hardcode that the result is always strictly 200 or 503 in every environment**, because security, port, base path, health groups, and HTTP proxies can alter the response.

When writing automated tests, avoid relying on arbitrary sleep durations to "wait for events". In the default synchronous case, you can publish and check `ApplicationAvailability`, or use a listener/test probe with explicit synchronization. If configured with an async multicaster, use an event-waiting mechanism with a reasonable timeout.

## 17. Knowledge Self-Check

1. **What data does `AvailabilityChangeEvent` carry?** An `AvailabilityState`, such as `LivenessState.CORRECT` or `ReadinessState.REFUSING_TRAFFIC`.
2. **To get the newly published readiness value inside a listener, what do you use?** `event.getState()`.
3. **To read current readiness from any bean, what do you use?** Inject `ApplicationAvailability` and call `getReadinessState()`.
4. **How do `ApplicationStartedEvent` and `LivenessState.CORRECT` relate?** Spring Boot publishes liveness `CORRECT` immediately after the started event on the success path.
5. **How do `ApplicationReadyEvent` and `ReadinessState.ACCEPTING_TRAFFIC` relate?** The readiness `ACCEPTING_TRAFFIC` event is published immediately after `ApplicationReadyEvent`.
6. **Can an app be `CORRECT` yet `REFUSING_TRAFFIC`?** Yes, this is a valid state while running runners, undergoing maintenance, or overloaded.
7. **To pause traffic temporarily, should you publish `LivenessState.BROKEN` first?** No, unless the process is genuinely broken and cannot self-recover; normally use readiness.
8. **Is `spring.factories` required to receive readiness events in a `@Component` bean?** No, a bean listener after refresh is normally sufficient.
9. **Is `getLastChangeEvent(ReadinessState.class)` always non-null when an app starts?** No; there may not be an event of that type yet.
10. **Does publishing readiness `REFUSING_TRAFFIC` guarantee Kubernetes immediately stops all requests?** No; probes, routing updates, and in-flight requests still apply.
11. **Why shouldn't an external DB check be used as a liveness probe?** A shared outage can cause all instances to restart, creating cascading failures.
12. **If two services decide readiness independently, what is the risk?** One service may publish `ACCEPTING_TRAFFIC` while another service's refusal reason still holds; policy coordination is required.
13. **Is Spring's readiness state automatically an HTTP endpoint?** No. For HTTP probes, you need Actuator/relevant configuration and an HTTP application.
14. **Does `ApplicationReadyEvent` mean external components are permanently healthy?** No; it is a lifecycle milestone, and state can change afterward.
15. **Why is `event.getState()` preferred over re-reading the snapshot inside an event handler?** Because it is the exact value published by that event, independent of snapshot-update ordering across listeners.

**Summary:** `AvailabilityChangeEvent` bridges **state-change events** with **observing, reacting to, or publishing liveness/readiness** in Spring Boot. `ApplicationAvailability` serves current-state queries; `@EventListener` observes individual events; `AvailabilityChangeEvent.publish(...)` publishes state transitions. Combined with Actuator/Kubernetes probes, these signals aid traffic orchestration, though they do not replace shutdown design, business checks, and infrastructure handling.

### References

- Spring Boot 3.3.13 — **SpringApplication: Application Availability**, liveness/readiness, and publishing events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — **AvailabilityChangeEvent API** (`getState`, `publish`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.3.13 — **ApplicationAvailability API** (`getReadinessState`, `getLastChangeEvent`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.3.13 — **Actuator Endpoints: Kubernetes Probes**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — **Gradle Plugin: Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Kubernetes — **Liveness, Readiness, and Startup Probes**: https://kubernetes.io/docs/concepts/workloads/pods/probes/
