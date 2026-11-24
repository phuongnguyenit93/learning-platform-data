# AvailabilityChangeEvent Transitioning Liveness State After Started in Spring Boot

## 1. Exact Meaning of the Event After ApplicationStartedEvent

During Spring Boot startup, **finishing ApplicationContext initialization** and **being ready to receive traffic** are two distinct milestones. After the context refreshes successfully, Spring Boot emits `ApplicationStartedEvent`. **Right after this event, Boot emits `AvailabilityChangeEvent<LivenessState>` with state `LivenessState.CORRECT`**. Only then are `ApplicationRunner` and `CommandLineRunner` invoked. Once the runners complete successfully, Boot emits `ApplicationReadyEvent` and then emits `AvailabilityChangeEvent<ReadinessState>` with `ReadinessState.ACCEPTING_TRAFFIC`.

This is an important rule when writing listeners, inspecting health probes, and orchestrating deployments. You must not assume the name `ApplicationStartedEvent` means the application is ready to serve users, or that `LivenessState.CORRECT` proves every external dependency is healthy.

Three conceptual layers must be kept separate:

| Concept | Representation | Meaning |
| --- | --- | --- |
| Lifecycle events | `ApplicationStartedEvent`, `ApplicationReadyEvent` | Notify that Spring Boot has reached a specific startup milestone |
| Availability change event | `AvailabilityChangeEvent<S>` | Notifies that an `AvailabilityState` just changed; `S` is typically `LivenessState` or `ReadinessState` |
| Stored state | `ApplicationAvailability` | API for reading the latest liveness/readiness state known to the application |
| Health probes | Actuator health groups, Kubernetes liveness/readiness probes | Mechanism for external systems to observe state and make orchestration decisions |

`AvailabilityChangeEvent` is an in-process **Spring application event**. On its own, it does not open an HTTP endpoint, configure Kubernetes, or guarantee requests are rejected. When Spring Boot Actuator is present and configured appropriately, the new state can be reflected on health endpoints for infrastructure platforms to inspect.

## 2. Startup Sequence: From Context Refreshed to Liveness CORRECT and Readiness ACCEPTING_TRAFFIC

Spring Boot documents the order of key milestones as follows:

~~~mermaid
flowchart TD
  A["SpringApplication.run(args)"] --> B["ApplicationStartingEvent"]
  B --> C["ApplicationEnvironmentPreparedEvent"]
  C --> D["ApplicationContextInitializedEvent"]
  D --> E["ApplicationPreparedEvent"]
  E --> F["refresh ApplicationContext"]
  F --> G["ApplicationStartedEvent"]
  G --> H["AvailabilityChangeEvent: LivenessState.CORRECT"]
  H --> I["ApplicationRunner / CommandLineRunner"]
  I --> J["ApplicationReadyEvent"]
  J --> K["AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC"]
~~~

This is the **primary event sequence**, omitting many details such as config loading, bean definitions, context lifecycles, web server events, and bean post-processors. In practice, a startup failure can cut the sequence short and make Boot emit `ApplicationFailedEvent`; do not assume every event in the diagram will occur if startup fails.

Conceptual state table during normal startup:

| Timing | LivenessState | ReadinessState | Operational meaning |
| --- | --- | --- | --- |
| Starting up, refresh not finished | `BROKEN` | `REFUSING_TRAFFIC` | Process should not yet be considered capable of handling requests |
| After `ApplicationStartedEvent` and liveness event | `CORRECT` | `REFUSING_TRAFFIC` | Context refreshed; runners may still have startup work |
| After runners, `ApplicationReadyEvent` and readiness event | `CORRECT` | `ACCEPTING_TRAFFIC` | Boot marks the application as able to serve traffic |

The values in the table reflect **Boot's availability model**, not a guarantee that the HTTP server in every environment will return a specific HTTP code at every instant. Before the web connector is actually active, probes may be unreachable; if no platform uses readiness, an HTTP request hitting the port directly might still be handled by the server during startup. It is platforms like Kubernetes that use readiness probes to avoid routing traffic to an unready instance.

### ApplicationStartedEvent Milestone

`ApplicationStartedEvent` is emitted **after** `ApplicationContext.refresh()` and **before** `ApplicationRunner` / `CommandLineRunner`. Because the context has refreshed, Spring Boot infers that core internal infrastructure is working well enough to continue startup. This is the point where liveness is marked `CORRECT`.

Even so, runners may still have work such as loading local data, checking serving preconditions, or warming caches. That unfinished work explains why readiness remains `REFUSING_TRAFFIC` at this stage.

### AvailabilityChangeEvent with CORRECT

Right after started, Boot emits an event whose payload/state is `LivenessState.CORRECT`. Listeners specialized for `AvailabilityChangeEvent<LivenessState>` can receive it. The `ApplicationAvailability` implementation updates the last received state, allowing other components to inspect it.

**Common confusion:** `ApplicationStartedEvent` is not the same object/event as `AvailabilityChangeEvent`. The liveness event is emitted **after** the started event; a listener handling `ApplicationStartedEvent` should not assume the liveness event was already published before that listener ran.

### ApplicationReadyEvent and Readiness

After Boot finishes calling runners without errors, it emits `ApplicationReadyEvent`, followed by `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC`. These two events are also distinct. Inside an `ApplicationReadyEvent` callback, reading readiness immediately will not necessarily return `ACCEPTING_TRAFFIC`, because the standard readiness event is published **right after** the ready event.

Depending on version and custom listeners, state can also be actively changed by the application. A sound model relies on the availability event being handled or reads the latest state from `ApplicationAvailability` at the right moment.

## 3. Liveness: How Does CORRECT Differ from BROKEN?

`LivenessState` represents whether **the process can still function properly or self-recover**. It helps the platform decide whether restarting the instance would help.

Two core values:

- `LivenessState.CORRECT`: the application is considered live, with internal state fit for work. After context refresh, Spring Boot defaults to this state.
- `LivenessState.BROKEN`: the application is in an internal state considered unable to recover cleanly; the platform may need to restart the instance to restore service.

Liveness **does not mean** every API, database, message broker, or remote dependency is healthy. If an external database goes down temporarily and liveness flips to `BROKEN`, Kubernetes can restart all instances at once; repeated restarts usually do not fix the database and can worsen the outage. Therefore, **do not mechanically wire external system checks into liveness**.

A reasonable example for considering `BROKEN` is a core internal component entering an unrecoverable corrupted state, such as critical in-memory state invariants being broken. Deciding to publish `BROKEN` must be based on genuine recoverability; do not emit it simply because one request returned HTTP 500, a DB query timed out, or a remote cache is briefly unavailable.

### Marking Liveness CORRECT Is a Startup Assumption

By default Spring Boot relies heavily on `ApplicationContext` as a proxy for internal health. When refresh succeeds, Boot emits `CORRECT` per the standard lifecycle. However, `CORRECT` is not the result of an end-to-end test of every business endpoint. It is an **internal state signal**, meant to be used alongside logging, metrics, tracing, and other health checks for diagnostics.

A startup error **before** context refresh may prevent `ApplicationStartedEvent` from ever appearing, and thus no `CORRECT` liveness from the standard flow. If an exception happens **inside a runner**, `CORRECT` liveness may have been emitted, while `ApplicationReadyEvent` and `ACCEPTING_TRAFFIC` readiness will not occur on that failed startup branch.

## 4. Readiness: Why Started Yet Still REFUSING_TRAFFIC?

Readiness signals whether the application **should accept new traffic right now**. Standard states:

- `ReadinessState.REFUSING_TRAFFIC`: the platform should temporarily stop forwarding requests to the instance.
- `ReadinessState.ACCEPTING_TRAFFIC`: Boot/the application marks the instance ready to accept traffic.

Readiness is mainly useful in load-balanced/orchestrated environments. Below are situations where liveness can be `CORRECT` while readiness is `REFUSING_TRAFFIC`:

1. The context has refreshed, yet an `ApplicationRunner` is running a long initialization step.
2. The application was ready, yet needs to pause accepting new traffic for an operational reason.
3. The instance is preparing for graceful shutdown and must be removed from the active endpoint pool.
4. An instance-specific required dependency went down and the app stops traffic while still able to recover.

Do not rely on readiness to conclude a process needs restarting. Platforms like Kubernetes normally **remove the pod from traffic-serving endpoints** when readiness fails, whereas liveness failure can trigger a container restart.

### Startup with Long Runners

If an `ApplicationRunner` warms up data, the gap between `CORRECT` and `ACCEPTING_TRAFFIC` grows longer. This is by design: the application is live enough to run startup tasks, yet not ready to serve requests. If the runner throws an exception, startup fails; there is no guarantee Boot will publish accepting readiness.

### Non-Web Applications

A Spring Boot CLI/batch app still has lifecycle events and `ApplicationAvailability` even without an embedded web server. In that case `ReadinessState.ACCEPTING_TRAFFIC` marks startup completion under Boot's model, though there is no HTTP traffic to route. Do not assume the event creates an HTTP listener on its own.

## 5. ApplicationAvailability and AvailabilityChangeEvent APIs

The main types live in `org.springframework.boot.availability`:

| Type | Role |
| --- | --- |
| `ApplicationAvailability` | Service for reading state; exposes `getLivenessState()`, `getReadinessState()`, `getState(Class<S>)`, `getLastChangeEvent(Class<S>)` |
| `AvailabilityState` | Marker interface for availability state types |
| `LivenessState` | Enum with `CORRECT` and `BROKEN` |
| `ReadinessState` | Enum with `ACCEPTING_TRAFFIC` and `REFUSING_TRAFFIC` |
| `AvailabilityChangeEvent<S extends AvailabilityState>` | Application event with `getState()`; emitted when state changes |
| `AvailabilityChangeEvent.publish(...)` | Helper to publish state-change events via `ApplicationContext` or `ApplicationEventPublisher` |

To read state inside a bean:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

class AvailabilitySnapshot {
    private final ApplicationAvailability availability;

    AvailabilitySnapshot(ApplicationAvailability availability) {
        this.availability = availability;
    }

    boolean isLive() {
        return availability.getLivenessState() == LivenessState.CORRECT;
    }

    boolean isReady() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

This is a **Java snippet** illustrating state reading, not a complete bean since it lacks `@Component` and is not inside a full project. In a larger example, constructor injection of `ApplicationAvailability` is provided by Spring Boot at runtime.

An application can publish events to change readiness proactively:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
class TrafficGate {
    private final ApplicationEventPublisher publisher;

    TrafficGate(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void pauseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    void resumeNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

**Explanation:** publishing the event via `ApplicationEventPublisher` notifies availability listeners, including Boot's state service. It does **not** directly control sockets, stop the server, or guarantee load balancers re-route instantaneously. Proper health probes, routing policies, polling intervals, and orchestration are required.

For liveness, publish `LivenessState.BROKEN` only when you have verified reasons that the instance is internally broken and cannot self-recover; it carries heavier operational consequences than marking unready.

## 6. Listening to Events: Distinguishing Event Type, State, and Generic Parameter

Spring Framework supports `@EventListener` for receiving application events. You can define two handlers with specific generic parameters:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class AvailabilityAudit {
    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("LIVENESS=" + event.getState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS=" + event.getState());
    }
}
~~~

Spring Boot supplies generic type information when publishing `AvailabilityChangeEvent<S>`, allowing listeners to be declared per state type. Do not replace `<LivenessState>` with an arbitrary type and perform unchecked casts; a readiness event is also an `AvailabilityChangeEvent` yet carries a **different state type**.

`@EventListener` is convenient for beans already in the context. Ultra-early events such as `ApplicationStartingEvent` happen before context creation, so a regular `@Component` cannot be relied upon to catch them. By contrast, `AvailabilityChangeEvent` marking `CORRECT` occurs after refresh, so container-managed listeners can observe it.

**Avoid logic that relies on arbitrary listener ordering.** By default, event listeners run synchronously; if you configure an async event multicaster or async listeners, log timing and exception handling can differ. When you need an exact conclusion about state, inspect the `event.getState()` payload and `ApplicationAvailability` API rather than inferring from a single log line.

## 7. Complete Java 17+ Example: Proving Exact Event Order

The example below runs on Spring Boot 3.5.x, Java 17+, and Maven. It intentionally omits the web starter and Actuator to show that `AvailabilityChangeEvent` comes from **Spring Boot startup** without depending on HTTP endpoints.

File structure:

~~~text
availability-demo/
├── pom.xml
└── src/main/java/com/example/availability/
    ├── AvailabilityDemoApplication.java
    └── LifecycleObserver.java
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>availability-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
~~~

### File src/main/java/com/example/availability/AvailabilityDemoApplication.java

~~~java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AvailabilityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AvailabilityDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner startupTask(ApplicationAvailability availability) {
        return args -> System.out.println(
                "03.RUNNER=" + availability.getLivenessState()
                + "/" + availability.getReadinessState());
    }
}
~~~

### File src/main/java/com/example/availability/LifecycleObserver.java

~~~java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class LifecycleObserver {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01.STARTED");
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        if (event.getState() == LivenessState.CORRECT) {
            System.out.println("02.LIVENESS=CORRECT");
        }
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("04.READY");
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("05.READINESS=ACCEPTING_TRAFFIC");
        }
    }
}
~~~

**Run** inside `availability-demo`:

~~~bash
mvn -q -DskipTests package
java -jar target/availability-demo-0.0.1-SNAPSHOT.jar
~~~

With default Spring Boot startup, no unusual listeners, and no runner exceptions, the lines **explicitly printed by the sample program** follow this order:

~~~text
01.STARTED
02.LIVENESS=CORRECT
03.RUNNER=CORRECT/REFUSING_TRAFFIC
04.READY
05.READINESS=ACCEPTING_TRAFFIC
~~~

Spring Boot may print additional framework logs; the block above lists only the `01.` through `05.` prefixed lines, not total stdout.

**Event analysis:**

1. `ApplicationStartedEvent` is the first milestone recorded by the observer in the example, after context refresh.
2. Boot then publishes the `CORRECT` liveness event, and the observer prints line `02`.
3. `ApplicationRunner` is invoked; at this point liveness is already `CORRECT`, while readiness is still `REFUSING_TRAFFIC`, matching line `03`.
4. Once the runner finishes, Boot publishes `ApplicationReadyEvent`, and the observer prints line `04`.
5. Next, Boot publishes the `ACCEPTING_TRAFFIC` readiness event; line `05` marks readiness to receive traffic.

The logical order `ApplicationStartedEvent` → liveness → runner → `ApplicationReadyEvent` → readiness is confirmed by official Spring Boot documentation. However, if the app publishes other states itself, switches event handling to async, or the runner throws an exception, output can differ. This demo intentionally uses only standard synchronous in-context listeners without a custom event multicaster.

**Note on CLI programs:** because there is no web server or other long-running non-daemon thread, the Java process may exit once startup finishes; that does not negate that the startup events were emitted before exiting.

## 8. Exposing State in Actuator and Kubernetes Probes

In web applications, `spring-boot-starter-actuator` uses `ApplicationAvailability` to surface liveness/readiness through health indicators. When health probe groups are enabled, the common URLs are:

- `/actuator/health/liveness`: translates `LivenessState` into a health status per probe rules.
- `/actuator/health/readiness`: translates `ReadinessState`.
- `/actuator/health`: overall health, which may include other indicators; **not synonymous** with liveness alone.

A web runtime and Actuator are needed for these HTTP endpoints to actually exist. In Kubernetes environments detected by Spring Boot, probe groups may be enabled automatically; in other environments they can be enabled explicitly:

~~~yaml
# src/main/resources/application.yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

This configuration assumes the project already has Spring Web/Actuator; it does not create a web server without a web starter and does not bypass Spring Security or network policies.

Kubernetes probes example:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 2
  periodSeconds: 5
~~~

These are two **container spec configuration snippets**, meant for `spec.containers[]` in a Pod/Deployment manifest with seconds, ports, and thresholds tuned to the application. They are not Spring Boot YAML config. When liveness fails past its threshold, kubelet can restart the container; when readiness fails, that endpoint is removed from the Service's traffic-serving pool per Kubernetes mechanics.

### Liveness CORRECT Does Not Guarantee the Database Is Connected

Liveness probes should reflect genuinely unrecoverable internal state. Do not add DB/remote cache checks to liveness without evaluating the consequence of restarting all replicas simultaneously. For readiness, you can consider health checks for components strictly needed to serve traffic; yet a **shared dependency across all instances** failing can mark the entire service unready. Evaluate architecture, circuit breakers, fallbacks, and load-balancing impact before adding indicators.

### Health Probe Endpoints and Real HTTP Infrastructure

If Actuator runs on a `management.server.port` different from the application port, probes on the management port can still succeed even when the business port has issues. Spring Boot supports exposing health probes on the main application port:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

With this configuration and an appropriate web runtime, the additional paths on the main port are `/livez` and `/readyz`. This reduces the risk of probing only the management server while missing main-port failures. You must still verify security, ingress, and routing config in the deployment environment.

### Slow Startup: When Is startupProbe Needed?

During startup, liveness is considered `BROKEN` before the context finishes refreshing. If startup takes longer than the liveness probe allows, kubelet may restart the container before it gets a chance to become live. Kubernetes `startupProbe` protects the startup window: while the startup probe has not succeeded yet, kubelet holds off normal periodic liveness/readiness probes. Design thresholds based on measured startup times rather than blindly adding it to every app.

## 9. Proactively Switching State After Startup

A module may need to stop accepting new traffic without killing the process—for example, during leader handoff, temporarily pausing new jobs, or graceful draining. In that case publishing `ReadinessState.REFUSING_TRAFFIC` is usually more appropriate than `LivenessState.BROKEN`.

Reusing `TrafficGate` from Section 5:

~~~java
// Once you decide to temporarily pause traffic:
trafficGate.pauseNewTraffic();

// Once serving conditions are restored:
trafficGate.resumeNewTraffic();
~~~

These are **illustrative calls inside application code**, not a standalone program. Avoid calling `resumeNewTraffic()` unconditionally after a fixed delay if serving conditions have not been verified.

For an unrecoverable internal state failure, broken liveness can be published via the helper:

~~~java
AvailabilityChangeEvent.publish(
        eventPublisher, this, LivenessState.BROKEN);
~~~

This snippet belongs inside a bean with an `eventPublisher` of type `ApplicationEventPublisher`; it only illustrates syntax. Distinguish **emitting a signal** from **fixing the error**: the event does not automatically roll back state, recreate beans, restart the process, or replace incident handling.

Additionally, Spring Boot publishes shutdown-related states, typically transitioning readiness to `REFUSING_TRAFFIC` when graceful shutdown starts. You do not need to manually mark liveness `BROKEN` on every intentional application shutdown.

## 10. Common Errors When Reading Logs or Writing Listeners

### Confusing Started with Ready

**Symptom:** code in `ApplicationStartedEvent` starts serving business logic or reports ready externally while an `ApplicationRunner` is still preparing data. **Fix:** treat started as context refreshed; report readiness only upon `ACCEPTING_TRAFFIC` or `ApplicationAvailability` state after runners.

### Calling getReadinessState Inside ApplicationReadyEvent and Seeing REFUSING_TRAFFIC

`ApplicationReadyEvent` is emitted before the standard readiness availability event. This can be normal startup behavior, not a bug. If you want to handle the **exact moment** readiness changes, listen for `AvailabilityChangeEvent<ReadinessState>` and check `event.getState()`.

### Enabling Health URLs Yet the Endpoint Returns 404

Verify Spring Web/Actuator starters, base paths, management port, enabled health probe settings, and Spring Security/access rules. The existence of `AvailabilityChangeEvent` and `ApplicationAvailability` in Boot startup does not mean HTTP endpoints are registered.

### Liveness Turning BROKEN When the DB Is Down

This is typically a dangerous probe setup if the DB is shared: endless container restarts rarely heal the DB and often amplify the incident. Separate liveness from external dependency checks; use readiness or business-level retries/circuit breakers where appropriate.

### App Has CORRECT Yet Readiness Never Reaches ACCEPTING_TRAFFIC

Check whether `ApplicationRunner`/`CommandLineRunner` completed; if a runner hangs, throws, or stops the process, Boot does not emit ready/accepting readiness along the success path. Also check whether a custom listener explicitly published `REFUSING_TRAFFIC` afterward.

### Tests Asserting an Exact Number of Events

Libraries, processors, or application code may emit additional availability events—for example, when readiness changes during runtime. Tests should filter by **state type and value** and assert the order of meaningful events rather than assuming strictly two events exist over a process's lifetime.

### Manually Publishing CORRECT in ApplicationStartingEvent

That defeats the purpose of liveness: reporting live before the context has even refreshed. Let Boot's lifecycle mark `CORRECT` after started; if you genuinely write custom infrastructure, respect the event contract and when the container can create listeners.

### Mistaking Probes Returning HTTP 503 for All Users Receiving HTTP 503

Probes can return unhealthy status on the **probe endpoint**; Kubernetes normally stops routing to an unready instance, so users may not receive 503 from that instance directly. Ingress/load balancer responses also depend on the platform and available ready replicas.

### Emitting a State Event Without Seeing Kubernetes React

Check whether Boot Actuator reflects the state, whether probes are enabled, whether path/port match, readiness/liveness policies, and probe polling intervals. Events are internal app signals; without probes and a platform consuming them, deployment infrastructure cannot know about them automatically.

## 11. Quick Decision Table

| Situation | State/event to observe or adjust | Why |
| --- | --- | --- |
| Context refresh succeeded | After `ApplicationStartedEvent` → `LivenessState.CORRECT` | Boot marks the process live |
| Runner still preparing data | `CORRECT` + `REFUSING_TRAFFIC` | Live, yet not ready |
| Runners finished, startup succeeded | `ApplicationReadyEvent` → `ACCEPTING_TRAFFIC` | Begin accepting traffic per platform policy |
| Local cache corrupted unrecoverably | Consider `LivenessState.BROKEN` | Instance restart may be needed |
| External DB briefly timed out | Do not automatically emit BROKEN | Restarting the app may not fix external failures |
| Instance needs to drain new requests briefly | `ReadinessState.REFUSING_TRAFFIC` | Stop routing new traffic while keeping the process alive |
| Graceful shutdown begins | Observe refusing readiness | Allow time to finish in-flight requests per config |
| Batch/CLI app without HTTP | Still emits availability events | Events do not create an HTTP server on their own |
| Choosing restart vs. load-balancer removal | Liveness vs. readiness probes | The two probe types trigger different orchestration actions |

## 12. Self-Check Questions

**1.** Does `ApplicationStartedEvent` fire before or after context refresh?  
**Answer:** After refresh, before runners.

**2.** Right after `ApplicationStartedEvent`, which event does Spring Boot emit to mark liveness?  
**Answer:** `AvailabilityChangeEvent` with `LivenessState.CORRECT`.

**3.** While `ApplicationRunner` is executing, what are liveness and readiness typically?  
**Answer:** `CORRECT` and `REFUSING_TRAFFIC`.

**4.** Can you assert the app is ready immediately upon receiving `ApplicationStartedEvent`?  
**Answer:** No; runners and the readiness event still lie ahead.

**5.** Are `ApplicationReadyEvent` and the readiness accepting event the same event?  
**Answer:** No; `AvailabilityChangeEvent<ReadinessState>` with `ACCEPTING_TRAFFIC` is published right after `ApplicationReadyEvent`.

**6.** Should you automatically publish `LivenessState.BROKEN` when an external DB goes down?  
**Answer:** Usually no, because liveness should be based on internal recoverability to avoid mass instance restarts due to a shared dependency.

**7.** Which interface do you inject into a bean to read the latest availability state?  
**Answer:** `ApplicationAvailability`.

**8.** Which event type should a handler accept to listen specifically for liveness changes?  
**Answer:** `AvailabilityChangeEvent<LivenessState>` and inspect `getState()`.

**9.** Without Actuator, does the `LivenessState.CORRECT` event still occur during startup?  
**Answer:** Yes, because the event belongs to Spring Boot's startup mechanism; without Actuator/web, HTTP probes are simply absent.

**10.** Do a failed liveness probe and a failed readiness probe have the same consequence in Kubernetes?  
**Answer:** No; liveness can trigger a restart, whereas readiness removes the pod from new traffic routing.

**11.** If an ApplicationReadyEvent listener reads readiness and sees refusing, is that necessarily a bug?  
**Answer:** No, because the standard event transitioning to accepting is published right after the ready event.

**12.** Does publishing `REFUSING_TRAFFIC` once automatically sever HTTP connections or restart the pod?  
**Answer:** No, it changes internal state; orchestration behavior depends on probes and external platforms.

## 13. Official Spring Boot Documentation for Reference

- [Spring Boot — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): sequence of started, liveness, runners, ready, readiness.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability): meaning of liveness and readiness, how to read and publish state.
- [Spring Boot — Actuator Endpoints: Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): health groups, readiness/liveness probes, and startup/shutdown states.
- [Spring Boot — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): generic state type, `getState()`, and `publish(...)`.
- [Spring Boot — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html): reading the latest state.

For every real project, check the active Spring Boot version, web context initialization, custom listeners, Actuator configuration, and platform probe behavior before relying on these states to route traffic.