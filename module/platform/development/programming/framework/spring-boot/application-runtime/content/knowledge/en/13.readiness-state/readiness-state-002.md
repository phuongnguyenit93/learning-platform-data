# LivenessState.CORRECT and BROKEN: Internal Health of a Spring Boot Application

## 1. What Question Does Liveness Answer?

When operating a Spring Boot application, you must distinguish at least three questions: does the process still exist, is the application **capable of working properly internally**, and is the application **ready to accept requests** yet? A running JVM can still be stuck in an unrecoverable internal state; conversely, a service that is not ready because it is reconnecting to a database does not necessarily need to be restarted.

Spring Boot uses `org.springframework.boot.availability.LivenessState` to express the second question. This enum has only two values:

- `LivenessState.CORRECT`: the application is in an internal state considered valid and can continue operating.
- `LivenessState.BROKEN`: the internal state is broken and **cannot self-recover** under the application's policy; operational infrastructure should consider **restarting the instance**.

Liveness is **a signal for deciding whether to restart an instance**, not an aggregation of every conceivable health check. The `BROKEN` state carries strong meaning; reporting it erroneously can cause Kubernetes to repeatedly restart pods that are still capable of serving.

In Spring Boot 3.3, liveness is part of the `ApplicationAvailability` system. When Actuator is present, these states can be exposed through health groups and Kubernetes HTTP probes. The enum itself is solely **in-memory application state**; HTTP endpoints, kubelet, and restart policies belong to other layers.

This lesson uses **Spring Boot 3.3.x, Java 17+**. It explains when to use `CORRECT`/`BROKEN`, automatic lifecycle milestones, how to read/publish state, testing, Actuator configuration, and how to avoid operational mistakes.

## 2. Exact Meaning of CORRECT and BROKEN

| State | Meaning | Typically Appropriate Response |
| --- | --- | --- |
| `CORRECT` | Essential internal invariants still hold; the application can operate or handle faults normally | Keep the instance running, observe errors and readiness independently |
| `BROKEN` | An internal fault cannot self-heal inside the current instance; continuing to use the instance may be unsafe | Let monitoring/orchestrator detect and restart, or execute a defined recovery strategy |

### 2.1. CORRECT Does Not Mean Every Request Succeeds

For example, a service loses connection to a partner API for 30 seconds, yet still has retry/backoff/circuit breaker mechanisms and can recover when the API returns. **Liveness can still be CORRECT**. A business endpoint depending on the partner may temporarily fail; that **does not turn the internal state into BROKEN**.

Similarly, `CORRECT` does not mean:

- 100% of HTTP requests return 200.
- Database, Redis, Kafka, DNS, or external networks are always available.
- All caches are warm and all batches are done.
- The application has published `ReadinessState.ACCEPTING_TRAFFIC`.
- There are no memory, latency, or CPU warnings.
- The HTTP server on the main port is actually accepting connections.

Liveness and other signals should be observed **together**, rather than replacing one another.

### 2.2. BROKEN Is Not a Generic Label for Any Transient Error

`BROKEN` is appropriate when **the instance can no longer return to a valid operating state on its own**, for example:

- A core coordination component is corrupted and cannot be recreated in-process.
- In-memory-only state data is severely corrupted and the application cannot safely rebuild it.
- A mandatory internal invariant is violated to the point that continued processing could produce wrong results.
- An essential subsystem has died completely with no reliable in-process restart/recreate mechanism.

These are **application-design-dependent examples**, not an automatic rule that every exception, stopped thread, or cache failure must switch to `BROKEN`. If an error can recover safely within the process, there is no basis to request a restart from that error alone.

### 2.3. BROKEN Does Not Make the JVM Exit by Itself

Publishing `LivenessState.BROKEN`:

1. Creates an `AvailabilityChangeEvent`.
2. Updates the state tracked by `ApplicationAvailability` when the event is processed.
3. When probes and Actuator are configured, can cause the liveness health group to report unhealthy.
4. **Does not call `System.exit`, does not restart the JVM, and does not restart a Kubernetes pod by itself.**

Restarting depends on **the infrastructure checking liveness**, probe threshold settings, and restart policy. In a CLI or local JVM without an orchestrator, `BROKEN` may simply exist in memory with no automatic action.

## 3. Liveness Differs from Readiness and General Health

Spring Boot has two primary availability axes:

| Question | API/State | Reaction on Failure |
| --- | --- | --- |
| Is the instance internally corrupted beyond self-recovery? | `LivenessState.CORRECT` / `BROKEN` | Typically **restart instance** |
| Should the instance receive new traffic/work right now? | `ReadinessState.ACCEPTING_TRAFFIC` / `REFUSING_TRAFFIC` | Typically **stop routing traffic**, keep instance alive |
| Is a dependency or subsystem healthy? | `HealthIndicator`/`HealthContributor`, health groups | Depends on group and purpose; may report failure to monitoring |
| Is the JVM process still running? | PID/process monitor | OS/container-level monitoring |
| Is the HTTP endpoint reachable? | HTTP probe and network path | Depends on server, firewall, port, route, and infrastructure policy |

**Example A — temporary database disconnect:** the application can retry and recover. You should not automatically switch liveness to `BROKEN` just because database connections fail. You can handle errors per request, use a circuit breaker, or adjust readiness if serving traffic is genuinely unsafe.

**Example B — startup cache loading:** the container has refreshed, liveness state can be `CORRECT`, yet an `ApplicationRunner` is still executing mandatory work. Readiness typically remains `REFUSING_TRAFFIC`. Do not restart just because it is not ready yet.

**Example C — unrecoverable internal coordinator corruption:** the instance is no longer trustworthy even though database and network are fine. Here, publishing `BROKEN` may be more appropriate than returning `REFUSING_TRAFFIC` forever.

**Example D — temporary maintenance or overload:** the application is still internally sound, but needs to refuse new work. `ReadinessState.REFUSING_TRAFFIC` usually captures the intent better than `LivenessState.BROKEN`.

Key point: **an instance can be live without being ready**. This is normal during startup and at certain operational moments.

## 4. Default State Across the Spring Boot Lifecycle

Spring Boot manages the fundamental availability milestones automatically. For a typical `SpringApplication.run(...)`:

```text
SpringApplication starts
    |
    | LivenessState.BROKEN
    | ReadinessState.REFUSING_TRAFFIC
    | (initial protective state: not yet declaring the app live/ready)
    |
Create ApplicationContext / prepare Environment
    |
context.refresh()
    |
ContextRefreshedEvent
    |
ApplicationStartedEvent
    |
AvailabilityChangeEvent<LivenessState.CORRECT>
    |
    | Liveness = CORRECT
    | Readiness = REFUSING_TRAFFIC
    |
ApplicationRunner and CommandLineRunner
    |
ApplicationReadyEvent
    |
AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>
    |
    | Liveness = CORRECT
    | Readiness = ACCEPTING_TRAFFIC
    |
Running
    |
On normal shutdown: readiness transitions back to REFUSING_TRAFFIC
    |
Close ApplicationContext, stop HTTP server
```

These lines represent the **typical ordering and defaults**, not a guarantee that an HTTP liveness endpoint is reachable right from process start. At startup, the web server may not be open yet, so probes may receive connection refused. Upon context refresh, opening the HTTP server and registering routes still depend on application type and configuration.

### 4.1. Why Is It BROKEN at the Very Start?

In Spring Boot's lifecycle/probe tables, the initial liveness state is described as `BROKEN`. This **does not mean Boot detected an actual critical fault** immediately upon initialization. It is simply the default way of **not yet confirming the instance is live** before startup crosses the required milestone.

Once the context has refreshed and Spring Boot fires `ApplicationStartedEvent`, Boot follows with an `AvailabilityChangeEvent` carrying `LivenessState.CORRECT`. Therefore, **BROKEN during startup** and **BROKEN after the app is running due to an internal error** have different contexts. Do not read the word `BROKEN` without timing/lifecycle context and conclude the application is corrupted.

### 4.2. CORRECT Before Runners Finish

Following the Spring Boot 3.3 sequence:

1. `ApplicationStartedEvent` is published after context refresh and before runners.
2. Spring Boot publishes `LivenessState.CORRECT`.
3. `ApplicationRunner`/`CommandLineRunner` are invoked next.
4. `ApplicationReadyEvent` occurs after runners.
5. Spring Boot publishes `ReadinessState.ACCEPTING_TRAFFIC`.

Consequently, code inside a runner may observe:

```text
liveness = CORRECT
readiness = REFUSING_TRAFFIC
```

The two values **do not contradict each other**. They express that the application is capable of operating on its own, while startup steps prior to accepting traffic have not finished yet.

### 4.3. Do Not Confuse ApplicationReadyEvent with the State-Change Event

A listener receiving `ApplicationReadyEvent` runs **before** the separate event that sets readiness to `ACCEPTING_TRAFFIC`. Therefore, if you need to confirm **that the availability state has actually changed**, listen for `AvailabilityChangeEvent<ReadinessState>` or read the state at the appropriate moment, rather than assuming the readiness snapshot inside every `ApplicationReadyEvent` listener is already accepting.

`ApplicationReadyEvent` remains an important Boot milestone; the point to distinguish is just the ordering between the **application event** and the **availability state event**.

## 5. API: LivenessState, AvailabilityState, and ApplicationAvailability

`LivenessState` is an enum in package:

```java
org.springframework.boot.availability.LivenessState
```

It implements `AvailabilityState` and has two constants: `CORRECT` and `BROKEN`. To **read** the current state, use `ApplicationAvailability`:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;

LivenessState state = availability.getLivenessState();
```

This is a snippet; the `availability` variable is injected via constructor or bean method. The complete application example later will show how to obtain the bean properly.

Related APIs:

| API | Meaning |
| --- | --- |
| `availability.getLivenessState()` | Get the current liveness state |
| `availability.getReadinessState()` | Get the current readiness state |
| `availability.getState(LivenessState.class)` | Get liveness via the generic interface; may return `null` if no state event has occurred yet |
| `availability.getState(LivenessState.class, LivenessState.BROKEN)` | Get state with a caller-defined fallback value |
| `availability.getLastChangeEvent(LivenessState.class)` | Get the last change event if present, to diagnose source/timing |

`ApplicationAvailability` is a **read-only abstraction**; it has no `setLivenessState(...)` method. To change state, Spring Boot is designed around `AvailabilityChangeEvent`.

### 5.1. Reading State Without Re-Running Health Checks

`ApplicationAvailability` keeps track of event-driven availability changes. `getLivenessState()` is not a method that goes out to ping a database or check a new HTTP path on every call.

It is a **snapshot of published state**. If your monitoring logic stopped detecting errors or never emitted a `BROKEN` event, `getLivenessState()` will not automatically detect every failure just because it is called.

If you want to verify a complex subsystem over time, you need a monitor/HealthIndicator with its own contract, and then **decide whether to transition liveness** based on internal recoverability.

### 5.2. Reading Before the First Event

In very early extension points, or unit tests that construct `ApplicationAvailability` in a custom way, state information may not have been published yet. `getState(type)` may return `null`; the overload with a fallback parameter lets you specify an appropriate default.

Do not treat `null` as a third enum constant of `LivenessState`. The enum has only two constants; `null` simply means **no data yet in that specific API call**. When working very early in startup, identify the exact observation point and lifecycle stage rather than inferring from an incomplete snapshot.

## 6. Updating Liveness with AvailabilityChangeEvent

Spring Boot allows application components to publish:

```java
AvailabilityChangeEvent.publish(publisher, this, LivenessState.BROKEN);
```

This snippet sits inside a bean with an `ApplicationEventPublisher publisher` field. `this` is the event **source**; an exception object or component can serve as the source, but avoid putting secrets into logs/metadata.

There is also an overload:

```java
AvailabilityChangeEvent.publish(applicationContext, LivenessState.BROKEN);
```

The snippet above requires a real `ApplicationContext applicationContext` and should only be called when an unrecoverable internal error truly exists.

When the event is published, Spring Boot has a listener managing `ApplicationAvailability`; Actuator's health indicator reads this availability to determine the liveness group result when enabled.

### 6.1. Do Not Treat It as an Arbitrary Boolean Toggle

Dangerous approach:

```java
try {
    remoteApi.call();
} catch (Exception ex) {
    AvailabilityChangeEvent.publish(publisher, ex, LivenessState.BROKEN);
}
```

This is an **anti-pattern example**, assuming `remoteApi` and `publisher` already exist. A brief network error or disconnect from an external service does not prove an unrecoverable internal state. Marking `BROKEN` here can cause all instances to restart even though they are all just waiting on the same API.

The right approach is to evaluate: can the error be retried, handled via readiness, or isolated to one feature? If yes, handle it according to that policy. Only publish `BROKEN` when the error **has no safe recovery path inside the current instance**.

### 6.2. Publishing CORRECT After Recovery?

Spring Boot supports publishing state changes, so at the API level you can emit `LivenessState.CORRECT`. However, if the system marked a fault as **unable to self-recover**, emitting `CORRECT` a few seconds later without proof that invariants were restored defeats the purpose of liveness.

Distinguish between:

- **A falsely emitted BROKEN signal:** fix the monitor condition, re-evaluate state, and handle operationally.
- **A component that can recover in-process:** that design probably should not have used BROKEN in the first place.
- **A genuinely unrecoverable fault:** the instance should be replaced/restarted by infrastructure.

Do not write a timer that re-emits `CORRECT` every minute to "make the probe green" while the underlying fault still exists.

## 7. Complete Java 17+ Example: Observe CORRECT Then Safely Simulate BROKEN

This example uses a **non-web** application. It does not open an HTTP port, does not configure Kubernetes probes, and does not restart a production system. The goal is strictly to **observe Spring Boot's event order and in-memory state**.

**Requirements:** Java 17+, Spring Boot 3.3.x; Gradle project with the Spring Boot plugin, dependency management, and `spring-boot-starter`.

**File:** `src/main/java/com/example/availability/LivenessLessonApplication.java`

```java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LivenessLessonApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LivenessLessonApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            System.out.println("4 AFTER_RUN liveness="
                    + availability.getLivenessState());
            System.out.println("5 AFTER_RUN readiness="
                    + availability.getReadinessState());

            boolean simulate = context.getEnvironment()
                    .getProperty("demo.simulate-broken", Boolean.class, false);

            if (simulate) {
                AvailabilityChangeEvent.publish(
                        context, LivenessState.BROKEN);
                System.out.println("7 AFTER_SIMULATION liveness="
                        + availability.getLivenessState());
            }
        }
    }

    @Bean
    ApplicationListener<AvailabilityChangeEvent<LivenessState>>
            livenessEventLogger() {
        return event -> System.out.println(
                (event.getState() == LivenessState.CORRECT
                        ? "1 EVENT_LIVENESS="
                        : "6 EVENT_LIVENESS=")
                + event.getState());
    }

    @Bean
    ApplicationRunner reportRunnerState(
            ApplicationAvailability availability) {
        return arguments -> {
            System.out.println("2 RUNNER liveness="
                    + availability.getLivenessState());
            System.out.println("3 RUNNER readiness="
                    + availability.getReadinessState());
        };
    }
}
```

This is a **complete Java file**, where `@SpringBootApplication` auto-configures Boot, and `@Bean` registers a type-safe event listener and a runner. The file name matches the public class.

### 7.1. Why Choose a Generic ApplicationListener?

`ApplicationListener<AvailabilityChangeEvent<LivenessState>>` lets Spring distinguish **LivenessState events** from `AvailabilityChangeEvent<ReadinessState>`. Thus, the log in this example tracks only liveness state without printing every readiness transition.

`AvailabilityChangeEvent` provides `ResolvableType` so Spring can inspect the generic event type. With a regular Spring listener bean, the `LivenessState` type parameter selects matching events without manually casting every event to liveness.

### 7.2. Dependencies

In a Gradle project already configured with the Spring Boot 3.3.x plugin and Java 17+, declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This is **part of build.gradle**, not the entire build script. Neither `spring-boot-starter-web` nor Actuator is required for the non-web example.

From the directory containing the Gradle Wrapper, run:

```bash
./gradlew bootRun
```

On Windows CMD it is `gradlew.bat bootRun`; in PowerShell it is `.\gradlew.bat bootRun`.

### 7.3. Output Without Fault Simulation

Ignoring Boot/Gradle banners and INFO logs, in this sample application with one runner and one listener, the lines printed by the lesson code appear in the expected order:

```text
1 EVENT_LIVENESS=CORRECT
2 RUNNER liveness=CORRECT
3 RUNNER readiness=REFUSING_TRAFFIC
4 AFTER_RUN liveness=CORRECT
5 AFTER_RUN readiness=ACCEPTING_TRAFFIC
```

Explanation:

- Line 1 appears after `ApplicationStartedEvent`, when Boot publishes liveness `CORRECT`.
- Lines 2–3 are inside the runner: the app is already considered live, but not yet ready.
- Lines 4–5 are in `main` **after `app.run(...)` returns**, meaning Boot has finished runners and updated readiness.
- Then `try-with-resources` closes the context; closing the context does not produce an extra liveness log in this example.

Do not assume all framework logs always interleave in a fixed order. This is the order of **the lines printed by this specific example** on a normal startup path.

### 7.4. Optional BROKEN Simulation

To test changing state **inside a non-web JVM**, use:

```bash
./gradlew bootRun --args="--demo.simulate-broken=true"
```

`--args` is an option of the `bootRun`/`JavaExec` task for application arguments. On Windows you can also run `gradlew.bat bootRun --args="--demo.simulate-broken=true"`.

In addition to the five lines in section 7.3, the program prints:

```text
6 EVENT_LIVENESS=BROKEN
7 AFTER_SIMULATION liveness=BROKEN
```

This proves:

1. `AvailabilityChangeEvent.publish(context, LivenessState.BROKEN)` emits an event.
2. `ApplicationAvailability` reflects the state change observable in the same context.
3. Because the example is non-web and has no Kubernetes probe, **no container automatically restarts the JVM**. It simply closes the context via `try-with-resources` after printing.

**Do not enable this simulation flag in production applications**; it is purely an illustrative experiment, not a real invariant-checking mechanism.

## 8. Application Example: Emitting BROKEN When an Internal Invariant Truly Cannot Recover

In a real application, a component that understands system correctness should decide when to report `BROKEN`. A complete code pattern for an **error-reporting mechanism**:

**File:** `src/main/java/com/example/availability/LocalInvariantFailureReporter.java`

```java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public final class LocalInvariantFailureReporter {

    private final ApplicationEventPublisher publisher;

    public LocalInvariantFailureReporter(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void reportUnrecoverableState(Throwable cause) {
        if (cause == null) {
            throw new IllegalArgumentException("cause must not be null");
        }

        AvailabilityChangeEvent.publish(
                publisher, cause, LivenessState.BROKEN);
    }
}
```

This class **compiles in a Spring Boot 3.3 project with a starter configured**, but does not cause failures by itself; a component detecting broken invariants must **explicitly call** `reportUnrecoverableState(cause)`. Classifying an error as "unrecoverable" is an **application design responsibility**, not guessed by this class from the `Throwable` type.

Usage example in another component:

```java
try {
    localCoordinator.verifyInvariant();
} catch (IrrecoverableStateException ex) {
    failureReporter.reportUnrecoverableState(ex);
}
```

This is an **illustrative snippet**, not a complete file: `localCoordinator`, `failureReporter`, and `IrrecoverableStateException` must exist in the project. It only makes sense when the fault genuinely has no safe in-process recovery strategy.

### 8.1. Why Not Treat Every Exception as BROKEN?

- I/O failures can be transient.
- Timeouts can stem from an external dependency.
- `ValidationException` can be a data error on a single request.
- A single background task failing does not necessarily break all subsystems of the application.
- `InterruptedException` can be an intentional shutdown signal.
- A rebuildable cache should be recovered according to an appropriate policy.

Assign responsibility for publishing `BROKEN` to a layer that understands **severity and recoverability**, backed by tests and selective logging. Do not put it in a catch-all `catch (Exception)` wrapping every endpoint just to turn liveness red.

## 9. How to Listen to AvailabilityChangeEvent in a Type-Safe Way

For Spring Boot availability events, there are two common approaches:

**Approach 1 — `@EventListener` in a bean:**

```java
@Component
public class LivenessAudit {

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("Liveness changed: " + event.getState());
    }
}
```

This is an **illustrative class** requiring imports for `Component`, `EventListener`, `AvailabilityChangeEvent`, and `LivenessState`. Place the class in a component-scanned package.

**Approach 2 — `ApplicationListener` as in the complete example in section 7:**

```java
@Bean
ApplicationListener<AvailabilityChangeEvent<LivenessState>> listener() {
    return event -> System.out.println(event.getState());
}
```

This is a snippet inside a `@Configuration` or `@SpringBootApplication` class; import `Bean`, `ApplicationListener`, and the availability types. The two approaches are **alternatives** if you only want one log entry per event; do not register both and mistake two log lines for two events.

Note: if you must capture events **before BeanFactory has created listener beans**, register the listener with `SpringApplication` earlier. However, the default `CORRECT` event after started arrives after the context has refreshed, so a properly registered listener bean can receive it.

### 9.1. Be Careful in Multi-ApplicationContext Systems

Events published in a child context can propagate up to listeners in ancestor contexts. When managing a hierarchy, a parent listener might receive a child's `AvailabilityChangeEvent`. If an action applies only to the current context, design an explicit contract filtering by context or event source; **do not** assume `event.getSource()` is always an application context for every `AvailabilityChangeEvent`, because the publish overload accepts arbitrary sources like exceptions or components.

For any state-bearing event, do not look only at `CORRECT`/`BROKEN` while ignoring **which instance published it** and **which availability type the event carries**.

## 10. Liveness and Spring Boot Actuator

Add Actuator to expose availability to monitoring systems:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

The two dependencies above are for **a separate web application** or an alternative configuration to the `NONE` example; **do not simply add starter-web to the section 7 example and expect a server to open**, because that example's `main` forces `WebApplicationType.NONE`. In a real web app, do not force `NONE`.

In `src/main/resources/application.properties`:

```properties
server.port=8080

# Enable liveness/readiness health groups outside Kubernetes as well.
management.endpoint.health.probes.enabled=true

# Expose additional probe paths on the main port:
management.endpoint.health.probes.add-additional-paths=true
```

Note that `spring-boot-starter-actuator` must be on the classpath, and the health endpoint must be enabled/exposed per actual configuration and security policy. In Kubernetes, Spring Boot automatically enables probe health groups upon detecting the environment; setting `enabled=true` above lets you experiment locally.

### 10.1. Which Endpoints Reflect Liveness?

Spring Boot uses `LivenessStateHealthIndicator` for the liveness health group; the default endpoint when enabled is:

```text
GET /actuator/health/liveness
```

With `management.endpoint.health.probes.add-additional-paths=true`, it is also exposed on the **main HTTP server port** at:

```text
GET /livez
```

Similarly, readiness uses `/actuator/health/readiness` and `/readyz`. Additional paths are helpful if Actuator runs on a separate management port: probing on the main port reduces the risk of the management endpoint reporting green while the web server serving real traffic is broken.

Try on a **web application** with probes enabled:

```bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

When the application runs normally with unmodified health mappings, the liveness response is typically:

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

This is a **condensed illustration** of status/body. The exact `Content-Type` header and other headers depend on version and HTTP negotiation. When state is `BROKEN`, the liveness indicator normally flips the group result to `DOWN`; by default, the HTTP status for `DOWN` maps to **503 Service Unavailable**.

Do not treat a request failing because a **TCP connection could not be opened** as proof that the liveness enum is `BROKEN`. The server might not have started yet, might have shut down, the port/path might be wrong, a security policy might be blocking it, or the network might be failing.

### 10.2. Global Health Differs from the Liveness Health Group

`/actuator/health` can aggregate multiple `HealthIndicator`s, including databases and subsystems when relevant libraries are present. You should not point Kubernetes's `livenessProbe` directly at **global health** if global health includes external dependencies.

`/actuator/health/liveness` or `/livez` is designed for **liveness state**, and does not pull every external system indicator in by default. Preserve this distinction when building dashboards and probe configurations.

### 10.3. Liveness State and Actual Probe Differ

`ApplicationAvailability` is in-memory state. An HTTP probe additionally requires:

- An HTTP server created and accepting connections.
- The route/Actuator health group enabled and exposed.
- Correct port, path, scheme, network policy, and security.
- Requests reaching the intended instance.
- Timeout/failure thresholds configured on the orchestrator.

For example, the app may have state `CORRECT` while the web server is so blocked that kubelet cannot hit the endpoint: **the probe can still fail**, and infrastructure may decide to restart even though Spring's memory holds `CORRECT`.

Conversely, if the probe runs on a **separate management port** and the main port is broken, the probe may return 200 while real traffic goes unserved. This is why `/livez` and `/readyz` on the main port are worth considering.

## 11. Kubernetes: Using livenessProbe, readinessProbe, and startupProbe

A container configuration snippet in a Kubernetes Pod/Deployment might look like:

```yaml
containers:
  - name: application
    image: example/my-service:1.0
    ports:
      - containerPort: 8080
    livenessProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
    startupProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
```

This is a **YAML snippet belonging under `spec.containers`**, not a standalone Deployment file. It assumes a web app with an HTTP server on port 8080 and `/livez`/`/readyz` enabled as in section 10. The image is an example of deployment structure; substitute your project's real image if used.

**Purpose of each probe type:**

- `livenessProbe` fails past threshold: kubelet can restart the container according to platform policy.
- `readinessProbe` fails: the container is not considered ready to receive traffic via the Service, but is not immediately restarted for that reason.
- `startupProbe`: when configured, gives the application extra startup time before liveness/readiness probes take effect, avoiding kills during slow startups.

The timing values in YAML are purely **illustrative**; measure actual startup time, GC pauses, CPU load, and system requirements before applying them. Too short a `startupProbe` can still kill a pod before the application finishes refreshing; too lenient a probe can leave an instance stuck for a long time without action.

### 11.1. Why Not Add a Database Check to livenessProbe?

Suppose 20 pods share one database. The database becomes temporarily unavailable:

1. If liveness depends on the DB, all 20 pods are deemed not live at once.
2. Kubelet may restart pods en masse.
3. Each pod restarts, creates pools, and tries to connect to the DB simultaneously.
4. The database suffers even heavier load, easily trapping the system in a crash/restart loop.

That is a **cascading failure**. An external dependency failure is rarely fixed by restarting every instance, so Spring Boot recommends **not using external checks in liveness**.

Readiness may check external dependencies **selectively** if losing the dependency renders the instance unable to handle traffic safely. Yet if that dependency is shared across all pods, including it in readiness can also remove every instance from the Service. Decide based on architecture and actual error-handling strategy.

## 12. When Should Business Logic Publish BROKEN?

A practical decision table:

| Scenario | What Should Liveness Do? | Reason |
| --- | --- | --- |
| An HTTP request returns 400 due to invalid input | Keep `CORRECT` | A bad request does not corrupt the instance |
| Database timeout, with retry and circuit breaker | Usually keep `CORRECT` | External/recoverable fault |
| Lost connection to message broker, but consumer can reconnect | Usually keep `CORRECT` | System has a recovery path |
| Internal queue temporarily full, app still serves other parts | Usually keep `CORRECT`; consider readiness/load shedding | Temporary overload is not corruption |
| Local in-memory state corrupted and cannot be rebuilt | Consider `BROKEN` | Correctness within the instance is no longer guaranteed |
| A critical thread died with no recreation mechanism | Consider `BROKEN` | A restart may be needed to recover |
| A single background job failed but has retries | Keep `CORRECT` | Overall recoverability is not lost |
| Application is running migration/startup runner | Usually still `CORRECT` after started, readiness not accepting | Startup is completing its work |
| Graceful shutdown in progress | Liveness can stay `CORRECT`; readiness switches to refusing | Should not take new traffic, not necessarily an internal fault |
| JVM deadlock prevents serving probes | Probes may fail even without publishing BROKEN | Infrastructure detects via network/timeout |

**Error-classification rule:** ask "If we keep the process running and wait/recover/retry, can the instance return to serving properly?" If the reliable answer is **yes**, usually do not report `BROKEN`. If the answer is **no**, and a restart is genuinely likely to restore a clean state, `BROKEN` is an appropriate signal.

Not every situation is binary: you can use circuit breakers, failover, readiness, bounded retries, or restart an individual component instead of restarting the whole application.

## 13. BROKEN and Restart: Application vs. Platform Responsibilities

When the app publishes `BROKEN`, it **emits a signal** rather than executing a restart. With Kubernetes:

```text
Application publishes AvailabilityChangeEvent(BROKEN)
          |
ApplicationAvailability updates liveness
          |
LivenessStateHealthIndicator -> DOWN
          |
/livez returns HTTP 503 (if endpoint/server is still reachable)
          |
Kubelet calls livenessProbe periodically
          |
Reaches failureThreshold consecutive failures
          |
Kubelet restarts container
          |
New instance restarts from startup lifecycle
```

This is the **typical** flow when probe configuration is valid, not a guarantee that every event publication always causes a restart. Reality can be affected by networking, pod lifecycle, container restart policy, timeout settings, and node status.

### 13.1. Do Not Confuse Readiness and Restart

A readiness failure is advice: **do not send new traffic to this instance**. Kubernetes does not restart automatically merely because readiness is false. By contrast, liveness failures exceeding the threshold are a signal proposing a container restart.

Hence, an issue that can recover within a few seconds should stay out of liveness; use readiness or request-layer error handling where appropriate.

### 13.2. If Liveness Is BROKEN, Does Readiness Automatically Become REFUSING_TRAFFIC?

Do not assume that solely from an `AvailabilityChangeEvent<LivenessState>`. The two states are tracked independently. An application may have published `ReadinessState.ACCEPTING_TRAFFIC` earlier and only later transitioned liveness to `BROKEN`. During the window before kubelet processes the probe, traffic acceptance still depends on the server and current readiness.

If a severe fault also means the instance must stop taking new work, design the system to **switch readiness to REFUSING_TRAFFIC** or use an appropriate mechanism to stop accepting traffic. Do not rely on the liveness enum as an automatic synchronization lock blocking requests. At the same time, do not complicate fatal-failure handling with callbacks that could hang themselves.

## 14. Relationship with ApplicationContext, SmartLifecycle, and Shutdown

`LivenessState` is a **Spring Boot availability** concept, not an alias for:

- `ConfigurableApplicationContext.isActive()`.
- `ConfigurableApplicationContext.isRunning()`.
- A bean's `SmartLifecycle.isRunning()`.
- `ContextRefreshedEvent` or `ContextClosedEvent`.
- JVM PID or container process health.

An active context can coexist with `LivenessState.BROKEN` if the application publishes an unrecoverable internal error **after** startup. Conversely, during very early bootstrap, default liveness is not yet `CORRECT` even though the JVM is running.

### 14.1. During Shutdown

Spring Boot typically switches readiness to `REFUSING_TRAFFIC` during an orderly close. While graceful shutdown is underway, liveness does not necessarily turn `BROKEN` because the application is stopping **intentionally**, not due to an unrecoverable fault.

Once the context has closed and the HTTP server has stopped, the probe endpoint may no longer be reachable; the final in-memory enum value is not what matters once the process has stopped.

### 14.2. Does a SmartLifecycle Bean Stopping Always Mean BROKEN?

No. A `SmartLifecycle` bean may stop per management policy, on shutdown request, or because no more data needs processing. Even a critical component failure might recover by restarting or recreating that component. Only after determining it is an **unrecoverable fault** is there a basis to publish `BROKEN`.

### 14.3. Do Probes Detect Every Deadlock?

No single probe detects every fault. If the HTTP event loop or request thread pool locks up completely, probes on that port may time out even while in-memory state stays `CORRECT`; this can still trigger a restart. Conversely, if the probe runs over a completely separate management server, it may succeed while the main port can no longer process requests. Thus **the probe's path** is also part of reliable liveness design.

## 15. Testing Liveness Mechanics Properly

Three layers of testing should be distinguished.

### 15.1. Unit Testing Unrecoverable Classification Logic

Put the decision "should we report BROKEN?" into a policy class testable by inputs: error type, retry count, invariant state, self-recovery capability. Test that:

- Normal business request errors do not emit BROKEN.
- Retryable external dependency errors do not emit BROKEN.
- Unrecoverable invariant violations emit exactly once as designed.
- No tokens or sensitive data are logged.

You do not need to spin up Kubernetes to test state-selection logic.

### 15.2. Integration Testing ApplicationAvailability

In an integration test with a real Spring Boot context, inject `ApplicationAvailability` and `ApplicationEventPublisher`, publish `AvailabilityChangeEvent` with `LivenessState.BROKEN`, and assert `getLivenessState()` accordingly.

If the test needs HTTP health groups, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and Actuator to hit the real endpoint. Do not let a test that sets BROKEN affect other tests **reusing a cached context** and leak availability state into subsequent tests; isolate the context or intentionally restore state within test scope.

### 15.3. HTTP and Kubernetes Integration Testing

Verify:

1. Health groups are enabled on the right port/path.
2. `/livez` reports UP after started under normal configuration.
3. Health group returns DOWN/503 when an internal fault is simulated in the test environment.
4. `/readyz` is separate and reflects startup/traffic-acceptance conditions.
5. `startupProbe` allows realistic slow application startups.
6. Kubelet restarts on consecutive liveness failures **at the exact threshold**.
7. No restart storm occurs when a shared dependency fails.
8. Readiness false is not mistaken for a liveness failure.
9. Probes on the main port detect when the main port stops accepting requests.
10. After restart, the instance actually recovers; if not, investigate the root cause instead of increasing restart counts.

**Do not test BROKEN in production "to see if the pod restarts"** without a test plan and blast-radius isolation. Use staging or a controlled test environment.

## 16. Common Mistakes and How to Fix Them

| Mistake or Misconception | Problem | Remedy |
| --- | --- | --- |
| "Database loss equals liveness BROKEN" | External dependency outage can restart all pods | Keep liveness strictly for unrecoverable internal errors |
| "CORRECT means every request returns 200" | Liveness does not measure individual request success | Use metrics, health, readiness, and proper error handling |
| "CORRECT means already ready" | Runners may still be running | Read `ReadinessState` and readiness probes |
| "BROKEN makes the JVM exit automatically" | Only updates availability state | Requires orchestrator/probe/restart policy or explicit shutdown by design |
| "Readiness fail causes kubelet restart" | Readiness only removes the instance from traffic | Distinguish the two probe types |
| "Liveness starting as BROKEN at startup is a bug" | Protective state before live is published | Watch the `ApplicationStartedEvent`/`CORRECT` milestone |
| "Just adding Actuator gives you /livez" | Requires additional-paths configuration for /livez | Enable `management.endpoint.health.probes.add-additional-paths=true` |
| "Global health is liveness" | Global health may include database/external checks | Use `/actuator/health/liveness` or `/livez` |
| "200 probe on management port means main port is healthy" | Two ports have separate infrastructure | Consider probing on the main server port |
| "BROKEN and REFUSING_TRAFFIC always sync automatically" | Two distinct state axes | Publish readiness / coordinate traffic stop appropriately |
| "Calling getLivenessState pings every dependency" | API returns current in-memory state | Write properly scoped monitors/indicators |
| "@EventListener receiving any availability event is liveness" | `AvailabilityChangeEvent<ReadinessState>` also exists | Use specific generic types |
| "@PostConstruct is where to publish CORRECT" | Too early; Boot is still starting up | Let Boot manage default states |
| "BROKEN is the fix for all unknown errors" | Restarts can mask bugs and cause loops | Diagnose, classify recoverability, use backoff and logging |
| "If all pods fail, restarting all pods is good" | Can amplify a shared outage | Exclude external dependency checks from liveness |
| "Just increase initialDelaySeconds indefinitely" | Masks startup issues, delays fault detection | Measure startup time and consider startupProbe |
| "A green probe means every internal thread runs properly" | Probe only checks its own state/path | Combine metrics, traces, thread dumps, and subsystem checks |
| "Repeatedly publishing CORRECT fixes the bug" | Only alters the signal | Fix the root cause or restart under proper policy |

## 17. Design Scenarios: Distinguishing Recoverable vs. Fatal Faults

### Scenario A — Partner Network Loss

A REST service calls a partner API via HTTP client. The partner disconnects for 20 seconds. The service has bounded retries and a circuit breaker. Requests depending on the partner may fail, yet the process continues operating properly.

**Decision:** usually keep `LivenessState.CORRECT`; evaluate readiness based on actual impact, and use timeouts/circuit breakers and observability to monitor.

### Scenario B — Corruption of a RAM-Only State Table

An orchestration engine can only operate if an in-memory graph satisfies specific invariants. The engine detects that the structure is corrupted and rebuilding in-process is unsafe; continuing to process would yield wrong decisions.

**Decision:** publishing `BROKEN` may be right because a restart can rebuild clean state. Simultaneously log the cause, prevent new requests from being misprocessed, and verify that restarting actually fixes the issue.

### Scenario C — Temporary Internal Queue Overload

An in-memory queue fills up but can drain within a few seconds, allowing new work to be refused while pending work continues processing.

**Decision:** this is normally **load shedding/readiness**, not `BROKEN`.

### Scenario D — Multi-Minute Startup

A runner loads initial data. Context refresh has completed and Boot publishes `CORRECT`, yet readiness keeps refusing until the runner finishes. Kubelet might probe before the HTTP endpoint is ready.

**Decision:** configure a sensible `startupProbe` if startup is long; do not skip mandatory startup work just to turn liveness green faster.

### Scenario E — Deadlock Blocking Even HTTP Probes

The application has no chance to publish `BROKEN` because core threads are stuck. Kubelet cannot reach the HTTP probe, records timeouts, and restarts once the threshold is exceeded.

**Decision:** this is one reason to monitor the **actual probe**, rather than relying solely on in-memory events. Afterward, find the root cause of the deadlock rather than treating restarts as a root fix.

## 18. Self-Check Questions

**1. How many values does LivenessState have?**

Two: `CORRECT` and `BROKEN`. There is no `STARTING` or `UNKNOWN` enum constant in Spring Boot 3.3's `LivenessState`.

**2. Does BROKEN mean the database is down?**

No. BROKEN expresses an **unrecoverable internal state**, not the check result of an external dependency.

**3. When does Boot publish CORRECT during default startup?**

Immediately after `ApplicationStartedEvent`, meaning after refresh and before `ApplicationRunner`/`CommandLineRunner`.

**4. Why do CORRECT and REFUSING_TRAFFIC appear together?**

Because liveness and readiness are independent: the container is running properly, but startup tasks or traffic-acceptance conditions are not yet complete.

**5. Does publishing AvailabilityChangeEvent(BROKEN) restart the process immediately?**

No. It updates in-memory state; restarting requires appropriate monitoring/orchestration, such as kubelet with a `livenessProbe`.

**6. Should a DB HealthIndicator be added to the liveness group?**

Usually no. A shared DB failure can cause all instances to restart and amplify the outage.

**7. What is the difference between /actuator/health and /actuator/health/liveness?**

Global health can include many indicators; the liveness group is dedicated to evaluating liveness state and does not pull in all dependency checks by default.

**8. Does /livez always exist when Actuator is added?**

No. It is an additional path on the main HTTP port when probes/additional paths are properly configured.

**9. Does Liveness BROKEN automatically set readiness REFUSING_TRAFFIC?**

Do not assume so. The two state axes are tracked separately and may need coordination when handling fatal failures.

**10. Should a user validation error make an instance BROKEN?**

No; a bad data error on a single request does not corrupt the application's internal state.

## 19. Operational Checklist

1. Identify which internal invariants truly make an instance **unable to self-recover**.
2. Clearly define the owner responsible for emitting `BROKEN` and cases where it must not be emitted.
3. Do not arbitrarily put HealthIndicators for databases, external APIs, or external caches into liveness.
4. Read `ApplicationAvailability` as a snapshot, not as an active tool checking the entire system.
5. Observe the exact order `ApplicationStartedEvent → CORRECT → runners → ApplicationReadyEvent → readiness accepting`.
6. Use `ReadinessState`/readinessProbe when traffic needs to be paused temporarily instead of restarting.
7. Design error handling, backoff, and circuit breakers for external faults.
8. If using Actuator, verify health groups and actual endpoint/port/security settings.
9. If the management server uses a separate port, consider `/livez` and `/readyz` on the main port.
10. Configure `livenessProbe` timeout/period/failure threshold according to real load.
11. Consider `startupProbe` if startup is slow to avoid restart loops.
12. Do not enable BROKEN simulation features in production.
13. Test fatal state and probes in staging, verifying that restarts actually help.
14. Monitor restart counts, error logs, and root causes; do not just raise thresholds to hide failures.
15. With multiple `ApplicationContext`s, verify events belong to the right context/instance.
16. Do not treat CORRECT as a guarantee that business APIs work or all dependencies are online.
17. Do not forget graceful shutdown and readiness when handling fatal errors.
18. Keep in mind that reporting BROKEN is a serious operational decision requiring clear criteria and tests.

## 20. Summary to Remember

```text
                APPLICATION AVAILABILITY
                          |
             +------------+------------+
             |                         |
          LIVENESS                  READINESS
             |                         |
      CORRECT / BROKEN      ACCEPTING / REFUSING
             |                         |
    "Should we restart?"    "Should it receive traffic?"
             |                         |
        Liveness Probe          Readiness Probe
             |                         |
       Restart instance      Remove from routing temporarily
```

**Three practical principles:**

- `CORRECT` means the instance's internal state is considered valid; it does **not** mean all dependencies or requests are healthy.
- `BROKEN` is used when internal state **cannot self-recover**, so infrastructure considers a restart; do not tie it to every network or database error.
- Readiness and liveness are **two separate axes**. Check the right health group and HTTP probe path rather than mixing every measurement into a single "healthy" bucket.

## Official Documentation

- [Spring Boot 3.3 — SpringApplication, Application Availability, and Application Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — LivenessState API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html)
- [Spring Boot 3.3 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
- [Spring Boot 3.3 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html)
- [Spring Boot 3.3 — Actuator Endpoints, Kubernetes Probes, External Dependencies, and Availability State](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
