# Roles of ApplicationAvailability, LivenessState, and ReadinessState

A running Java process is not necessarily ready to serve traffic. For instance, an application may have finished creating its beans while still loading a mandatory rules table before handling requests. With only a single "good/bad" signal, the operations system can hardly tell whether to wait for the application to finish its work or to restart it.

Spring Boot represents two separate questions:

- **Liveness — internal application health:** is the current state sound enough for the application to keep running or self-recover?
- **Readiness — traffic acceptance readiness:** should this application instance receive additional requests right now?

This lesson focuses on the state model and Java API of Spring Boot 3.3.x. Actuator is the layer that exposes states externally; full Kubernetes configuration and building all types of health checks belong to a broader scope.

## 1. Three Types Serving Three Roles

| Component | Role | Usage example |
| --- | --- | --- |
| `ApplicationAvailability` | Interface for reading the application's current availability state | Inject the bean and call `getLivenessState()` or `getReadinessState()` |
| `LivenessState` | Enum describing internal operating state | `CORRECT`, `BROKEN` |
| `ReadinessState` | Enum describing the decision on whether it is ready to receive traffic | `ACCEPTING_TRAFFIC`, `REFUSING_TRAFFIC` |
| `AvailabilityChangeEvent<S>` | Event used to publish a state change | Publish an event containing `ReadinessState.REFUSING_TRAFFIC` |

Both enums implement `AvailabilityState`. In a typical auto-configured Boot application, consumers only need to depend on the `ApplicationAvailability` interface; `ApplicationAvailabilityBean` is the implementation class that holds the received event information. Do not instantiate a separate implementation object in each service, because they will not represent the same Spring-managed state.

This interface is for **reading**; it has no `setReadinessState(...)` method. To change the managed state, an application component publishes an `AvailabilityChangeEvent` to the right `ApplicationContext`. This is a Spring Boot core API, so it can be used without exposing an Actuator endpoint. See [Spring Boot 3.3 ApplicationAvailability API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html).

## 2. Understanding Each Enum Correctly

### LivenessState: Does This Application Instance Need Replacement?

- `CORRECT`: internal state is considered sound enough to continue operating.
- `BROKEN`: application internals are considered broken; in an operational environment, this signals infrastructure to consider restarting the application instance.

An appropriate example of broken liveness is foundational in-memory data corrupted to the point where the application has no reliable way to rebuild it itself. An external database losing connectivity for a few seconds is usually not solved by restarting every application instance.

`CORRECT` does not prove that every business transaction will succeed. Nor does it measure response times, queue depth, or the status of every dependent system. Conversely, having the value `BROKEN` does not itself call `System.exit`, shut down the JVM, or perform a restart. Restarting belongs to the supervisor/infrastructure configured to read the signal. See [LivenessState definition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html).

### ReadinessState: Should New Requests Be Sent Here?

- `ACCEPTING_TRAFFIC`: the application instance announces that it is ready to receive traffic.
- `REFUSING_TRAFFIC`: the application instance announces that it is currently not ready to receive new traffic.

A pause in accepting traffic can serve resource preparation, controlled overload handling, or local maintenance. Once the cause clears, the application can publish `ACCEPTING_TRAFFIC` again.

However, **publishing the state is not equivalent to blocking requests directly at the controller**. If the load balancer has not read the probe yet, if there is propagation lag, or if users call the application address directly, requests can still arrive. Local business-level rejection requires a dedicated admission mechanism if the problem demands it. Likewise, readiness does not automatically stop scheduled tasks, background threads, or message consumers.

Both liveness and readiness questions are introduced in the [Application Availability model](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### Why Not Merge the Two States?

| Illustrative scenario | Liveness | Readiness | Operational meaning |
| --- | --- | --- | --- |
| Preparing data after context initialization | `CORRECT` | `REFUSING_TRAFFIC` | Wait for preparation to finish; restarting usually does not help |
| Normal operation | `CORRECT` | `ACCEPTING_TRAFFIC` | Can receive traffic |
| Temporarily pausing new requests for local maintenance | `CORRECT` | `REFUSING_TRAFFIC` | Keep process running, temporarily route traffic elsewhere |
| Unrecoverable internal error detected | `BROKEN` | Per published readiness state | Needs an appropriate error-handling policy and supervisor |

The last row emphasizes that the two values are stored under two separate state types. Publishing `LivenessState.BROKEN` does not automatically also publish `ReadinessState.REFUSING_TRAFFIC`. The application needs coordinated decisions if it wants to express both.

## 3. Relationship to the Spring Boot Lifecycle

Boot proactively publishes availability milestones during application execution:

| Milestone | Typical Liveness | Typical Readiness |
| --- | --- | --- |
| No state-setting event received yet | `BROKEN` per getter default | `REFUSING_TRAFFIC` per getter default |
| Context refreshed; after `ApplicationStartedEvent` | `CORRECT` | `REFUSING_TRAFFIC` |
| Executing `ApplicationRunner` / `CommandLineRunner` | `CORRECT` | `REFUSING_TRAFFIC` |
| Runners finished; after `ApplicationReadyEvent` | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Beginning to close Boot web application context | Usually still `CORRECT` | `REFUSING_TRAFFIC` |

The key sequence is: context refresh → `ApplicationStartedEvent` → liveness `CORRECT` event → run runners → `ApplicationReadyEvent` → readiness `ACCEPTING_TRAFFIC` event. Therefore, a listener handling `ApplicationReadyEvent` itself should not assume the subsequent readiness event has already been processed. See [Spring Boot 3.3 event order](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners).

The default `BROKEN` value before an event is a cautious state when operability has not yet been established; it is not proof that the application has encountered an unrecoverable failure.

If data must be present before serving, a runner can perform that work before returning. If a runner only kicks off an asynchronous task and returns immediately, Boot does not automatically wait for that separate task to complete. Design a readiness mechanism for that case rather than assuming all background threads are finished when Boot turns ready.

In Boot 3.3, to let the web server finish in-flight requests before stopping, configure `server.shutdown=graceful`. Readiness switching to refusing traffic and graceful shutdown are two coordinated parts; changing an enum alone does not produce the full server shutdown sequence. When the HTTP server has not started yet or has already stopped, the state may still be meaningful internally while the probe URL may not yet or no longer be reachable. See [Boot 3.3 graceful shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).

## 4. Reading, Publishing, and Observing Changes

### Reading State

Two dedicated getters return the corresponding enum:

- `getLivenessState()`: current liveness, defaulting to `BROKEN` when no information is available.
- `getReadinessState()`: current readiness, defaulting to `REFUSING_TRAFFIC` when no information is available.

When you need to know whether an event has actually occurred, use `getState(ReadinessState.class)`: the result can be `null` if no event of that type has arrived yet. The `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)` overload lets you specify a fallback value. Do not mistake this fallback value for an actually published event.

`getLastChangeEvent(ReadinessState.class)` returns the last event of that type and can also be `null`. The event provides the state, source, and creation timestamp; it is not a complete log of all changes.

### Publishing Changes

`AvailabilityChangeEvent.publish(context, state)` publishes an event through the context. The `publish(publisher, source, state)` variant fits when you need to specify the component or cause acting as the event source. See [AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).

In Spring's default event configuration, publication is dispatched synchronously. The hands-on example below reads the state right after publishing because it keeps this default configuration. If an application replaces the dispatcher with asynchronous execution, you must re-evaluate when the new state becomes observable; do not carry the example's assumption over to every configuration.

To observe via a listener in a Boot application, you can use `@EventListener` with an `AvailabilityChangeEvent<ReadinessState>` parameter and read `event.getState()`. Listeners should execute quickly and avoid slow network checks on the event-publishing thread.

## 5. Hands-On: Two States Changing Independently

The example uses **JDK 21, Gradle 8.5, and Spring Boot core 3.3.0**. The Java code uses syntax compatible with Java 17+. The goal is to observe the API without setting up an HTTP server, Actuator, or Kubernetes.

This is a standalone program using `GenericApplicationContext`, **not calling `SpringApplication.run(...)`**. It registers a single `ApplicationAvailabilityBean` and publishes events itself. Thus the labels `live`, `ready`, and `paused` are experiment steps, not proof that Boot's lifecycle ran automatically in this context.

Create the structure:

```text
availability-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/AvailabilityDemo.java
```

Contents of `settings.gradle`:

```groovy
rootProject.name = 'availability-demo'
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot:3.3.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'AvailabilityDemo'
}

tasks.register('copyRuntimeLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

Contents of `src/main/java/AvailabilityDemo.java`:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ApplicationAvailabilityBean;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.support.GenericApplicationContext;

public class AvailabilityDemo {
    public static void main(String[] args) {
        try (var context = new GenericApplicationContext()) {
            context.registerBean("applicationAvailability",
                    ApplicationAvailabilityBean.class);
            context.refresh();

            var availability = context.getBean(ApplicationAvailability.class);
            print("initial", availability);

            AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
            print("live", availability);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            print("ready", availability);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            print("paused", availability);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            print("resumed", availability);

            AvailabilityChangeEvent.publish(context, LivenessState.BROKEN);
            print("broken", availability);

            var last = availability.getLastChangeEvent(ReadinessState.class);
            System.out.println("lastReadiness=" + last.getState());
        }
    }

    private static void print(
            String phase, ApplicationAvailability availability) {
        System.out.printf("%s: %s / %s%n", phase,
                availability.getLivenessState(),
                availability.getReadinessState());
    }
}
```

Run in the example directory, with Gradle 8.5 installed:

```shell
gradle -q run --console=plain
```

The first run needs internet access to download libraries. If the example directory already has Gradle Wrapper 8.5, you can replace `gradle` with `./gradlew` on Linux/macOS or `.\gradlew.bat` on Windows.

Program output:

```text
initial: BROKEN / REFUSING_TRAFFIC
live: CORRECT / REFUSING_TRAFFIC
ready: CORRECT / ACCEPTING_TRAFFIC
paused: CORRECT / REFUSING_TRAFFIC
resumed: CORRECT / ACCEPTING_TRAFFIC
broken: BROKEN / ACCEPTING_TRAFFIC
lastReadiness=ACCEPTING_TRAFFIC
```

Three points to verify:

1. `initial` shows both default values because no availability event has been published yet, even though the experiment's context has refreshed.
2. `paused` changes only readiness; liveness stays `CORRECT`. `resumed` shows that pausing traffic acceptance is reversible.
3. `broken` changes liveness while readiness stays `ACCEPTING_TRAFFIC`. The last line confirms the last readiness event is still the one published in the `resumed` step.

You can use `javac`/`java` directly after copying runtime libraries with the declared task:

```shell
gradle -q copyRuntimeLibraries
javac --release 17 -cp "build/runtime-libs/*" -d build/manual src/main/java/AvailabilityDemo.java
```

Run on Windows:

```shell
java -cp "build/manual;build/runtime-libs/*" AvailabilityDemo
```

Run on Linux/macOS:

```shell
java -cp "build/manual:build/runtime-libs/*" AvailabilityDemo
```

Both ways produce the same seven lines of output. The classpath entry separator is `;` on Windows and `:` on Linux/macOS.

## 6. Applying to a Bean in a Real Boot Application

In an application with Boot auto-configuration, inject the state-reading interface and the context managing the application. The example below is **an integrated bean**, not a standalone program with `main`. Place the class within the Boot application's component-scan scope:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class TrafficAdmission {
    private final ApplicationAvailability availability;
    private final ApplicationContext context;

    public TrafficAdmission(
            ApplicationAvailability availability, ApplicationContext context) {
        this.availability = availability;
        this.context = context;
    }

    public boolean isAcceptingTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }

    public void pause() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resume() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

`pause()` and `resume()` only publish the traffic-admission decision; the example does not expose control APIs for them itself. `isAcceptingTraffic()` reads the signal so another component can decide how to proceed. If you use it to gate business admission, you still must implement rejection behavior, concurrency policy, and handling for requests already accepted.

This is an example with **a single controller for readiness**. With multiple simultaneous refusal reasons, do not let each component independently call `ACCEPTING_TRAFFIC` when its own work finishes. For instance, if data preparation finishes while maintenance is still active, the application must still refuse traffic. Have one component aggregate the conditions and publish the unified decision.

In addition, a readiness event published too early during startup may be overwritten by Boot's default ready event published afterward. To preserve a maintenance state across that phase, coordinate with the lifecycle or use a separately aggregated readiness check. The enum pair does not manage a list of active blocking reasons on its own.

## 7. How Does Actuator Connect Java State to Probes?

Conceptual flow:

```text
Boot lifecycle / application decision
              ↓
AvailabilityChangeEvent
              ↓
ApplicationAvailabilityBean
              ↓ read via ApplicationAvailability
LivenessStateHealthIndicator / ReadinessStateHealthIndicator
              ↓
Health group / HTTP probe
              ↓
Monitoring infrastructure reads and enforces policy
```

Per the default mapping of the two indicators in Spring Boot 3.3:

| Value in application | Indicator health status |
| --- | --- |
| `LivenessState.CORRECT` | `UP` |
| `LivenessState.BROKEN` | `DOWN` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` |

This is a translation between Java enums and the health model; enum names are not JSON status names. HTTP status codes are also determined by health mapping and group configuration. A readiness group that includes extra checks can fail even when the readiness enum is still `ACCEPTING_TRAFFIC`; querying a health group does not write the result back into the enum either.

In a web application with `spring-boot-starter-actuator`, you can proactively enable both probe groups outside Kubernetes:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

When using default paths, access `/actuator/health/liveness` and `/actuator/health/readiness`. You also must ensure the health endpoint is enabled, exposed, and accessible to the caller. Do not add the database to liveness just to have more checks. Choices about external dependencies in readiness must be grounded in actual serving capability. See [Kubernetes Probes in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

A key point when diagnosing is that there are three layers: **internal state**, **probe result**, **infrastructure action**. They are related, but they do not occur instantaneously in lockstep.

## 8. Common Mistakes and How to Reason

| Misconception or practice | Problem | Appropriate approach |
| --- | --- | --- |
| "JVM is running so liveness is always correct" | Process may be alive while internal state can no longer self-recover | Define liveness around ability to keep operating properly |
| "Readiness refuses traffic so a restart is needed" | Situation may just be warmup or temporary maintenance | Separate traffic-shifting decisions from restarts |
| Manually calling `new ApplicationAvailabilityBean()` in a service | Reads an object detached from the managed state | Inject the context's `ApplicationAvailability` |
| Calling `getLastChangeEvent(...).getState()` before any event arrives | Can hit `NullPointerException` | Check for `null`; use enum getters when only the current value is needed |
| Assuming changing readiness immediately closes all connections | The enum only expresses availability decision | Configure probes and appropriate admission/shutdown mechanisms |
| Having each task re-enable readiness on its own | One completed task can mask another refusal reason | Aggregate conditions in one place |
| Combining all health checks into liveness | External dependency outages can cause mass restarts | Choose checks matching each signal's operational meaning |

When encountering "the application instance still receives requests despite refusing traffic," check in order: the readiness value in the right context; the readiness group result; the path/port the monitor is reading; infrastructure sync delay; and whether a direct call path bypasses the router. Do not conclude the enum is broken merely because one request still reaches the server.

## 9. Self-Check

1. In the standalone example, omit publishing `LivenessState.CORRECT` while keeping readiness accepting. What can the state pair become?
2. If you add a check to the readiness health group and that check returns an error, must `ApplicationAvailability.getReadinessState()` also change?
3. A startup task is handed off by a runner to a background thread, and the runner returns. Why can Boot's default readiness switch to accepting before that task finishes?
4. Two active reasons are blocking traffic: "maintenance" and "data not loaded." When data finishes loading, what state should the aggregating component publish?

Guiding answers:

1. `BROKEN / ACCEPTING_TRAFFIC`: no new liveness event was published; the two state types are independent.
2. No. The health group result is an aggregated outcome; it does not emit an event to alter the enum.
3. Boot tracks runner completion and has no automatic awareness of when arbitrary background tasks launched by a runner finish.
4. Still `REFUSING_TRAFFIC`, because the maintenance reason remains active.

After this lesson, you should be able to identify whether you are **reading state**, **publishing a new decision**, or **configuring an external system to react to that decision**, and pick the matching component accordingly.
