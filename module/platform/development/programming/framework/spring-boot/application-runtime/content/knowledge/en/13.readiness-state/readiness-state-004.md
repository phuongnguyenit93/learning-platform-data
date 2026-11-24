# Reading Current State via ApplicationAvailability in Spring Boot

## 1. Lesson Goal and Meaning of "Current State"

Spring Boot provides an **application availability** mechanism so the application and operations infrastructure understand two separate questions:

1. **Liveness:** is the process and internal state still sound enough to keep running or self-recover?
2. **Readiness:** at the current moment, is the instance **ready to receive new traffic**?

This mechanism lives in `org.springframework.boot.availability`. When you want to **read a snapshot of the state currently known to Spring Boot**, inject the `ApplicationAvailability` interface and call `getLivenessState()`, `getReadinessState()`, or the generic `getState(...)` methods.

What to distinguish right from the start:

- `ApplicationAvailability` returns **the state published by the latest availability events** and sensible fallback values; it does not run a database check or an HTTP health check on every call.
- `AvailabilityChangeEvent<S>` is the **state change** event; a component that wants to change readiness/liveness must publish an event, not call a setter, because the `ApplicationAvailability` interface has no setters.
- `ApplicationAvailabilityBean` is Boot's built-in implementation, receiving `AvailabilityChangeEvent` to retain the latest state. In business code, **inject the interface** rather than depending directly on the implementation.
- Spring Boot uses the availability mechanism in web, command-line, and batch applications alike. To let external platforms observe via HTTP, you need an appropriate health/probe layer, usually Spring Boot Actuator.

~~~mermaid
flowchart LR
    E["Spring Boot lifecycle and application code"] -->|"publish"| EV["AvailabilityChangeEvent"]
    EV -->|"listener stores state"| A["ApplicationAvailabilityBean"]
    A -->|"implements"| API["ApplicationAvailability"]
    API -->|"getLivenessState / getReadinessState"| S["Business beans, runners, exporters"]
    A -->|"health indicator when Actuator is present"| P["Health probes for platform"]
~~~

This is a data-flow diagram, not a detailed description of synchronous/asynchronous listener ordering across every configuration.

## 2. Two Non-Interchangeable State Types

| Group | State | Meaning | Common Platform Decision |
| --- | --- | --- | --- |
| `LivenessState` | `CORRECT` | Internal state is assessed as working properly or able to self-recover | Keep the instance running |
| `LivenessState` | `BROKEN` | Internal state is broken and cannot reliably self-recover | May restart process/container when liveness probe fails |
| `ReadinessState` | `ACCEPTING_TRAFFIC` | Instance is ready to receive routed new traffic | Include in the serving endpoints set |
| `ReadinessState` | `REFUSING_TRAFFIC` | Instance should temporarily not receive new traffic | Temporarily remove from traffic routing, not necessarily restart |

**Liveness differs from readiness.** An instance can be `CORRECT` for liveness while still `REFUSING_TRAFFIC` for readiness, typically when an `ApplicationRunner` is initializing data after context refresh. Conversely, when a component genuinely fails beyond recovery, reporting liveness `BROKEN` has a stronger consequence: the orchestrator may restart the container.

Do not switch liveness to `BROKEN` just because a database, cache, or external API is temporarily unresponsive: restarting every replica usually does not fix a shared dependency, and can even cause a cascading failure. For readiness, you can check additional conditions truly required for serving, while still weighing the risk of all instances being removed from the load balancer simultaneously.

### What the API Can and Cannot Conclude

If:

~~~java
ReadinessState readiness = availability.getReadinessState();
~~~

yields `ACCEPTING_TRAFFIC`, we know the state **managed by application availability** is currently accepting. That does not automatically prove DNS, ingress, inter-node connectivity, security filters, or databases are all healthy. Conversely, readiness `REFUSING_TRAFFIC` does not close TCP ports by itself; the platform must use probes or another integration for routing.

Reading state captures the observed state **at the moment of the call**. After it returns, another thread/event can still publish a new state; do not treat a single read as an immutable lock for an entire long-running workflow.

## 3. Most Important APIs of ApplicationAvailability

The `ApplicationAvailability` interface has the following methods in Spring Boot 3.5.x:

| Method | Return Type | Semantics |
| --- | --- | --- |
| `getLivenessState()` | `LivenessState` | Get the latest liveness or fallback `BROKEN` if no event of this type has occurred |
| `getReadinessState()` | `ReadinessState` | Get the latest readiness or fallback `REFUSING_TRAFFIC` if no event of this type has occurred |
| `getState(LivenessState.class)` | `LivenessState` or `null` | State **published by an event**; `null` when no event of this type has occurred |
| `getState(ReadinessState.class)` | `ReadinessState` or `null` | Same for readiness, without applying a fallback |
| `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)` | `ReadinessState` | Overload with a caller-supplied fallback, required non-null |
| `getLastChangeEvent(ReadinessState.class)` | `AvailabilityChangeEvent<ReadinessState>` or `null` | Most recent readiness event **received by the implementation** |
| `getLastChangeEvent(LivenessState.class)` | `AvailabilityChangeEvent<LivenessState>` or `null` | Most recent liveness event received |

### 3.1 Concise Reading via the Two Convenience Methods

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

boolean live = availability.getLivenessState()
        == LivenessState.CORRECT;

boolean ready = availability.getReadinessState()
        == ReadinessState.ACCEPTING_TRAFFIC;
~~~

The snippet above goes inside a method of a class with `availability` injected. These are the two preferred ways to read when you only need a live/ready check under default policy.

### 3.2 Understand Fallback Values to Avoid Misinterpretation

According to the interface source, the equivalent logic is:

~~~java
default LivenessState getLivenessState() {
    return getState(LivenessState.class, LivenessState.BROKEN);
}

default ReadinessState getReadinessState() {
    return getState(
            ReadinessState.class,
            ReadinessState.REFUSING_TRAFFIC);
}
~~~

**Consequence:** when no availability event has ever been emitted for that type, the two convenience methods still return a **safe** state. They do not need to fabricate a "synthetic event" to provide a fallback.

Conversely, `getState(ReadinessState.class)` can be `null` before any readiness event. Therefore:

~~~java
ReadinessState raw = availability.getState(ReadinessState.class);

// May be true at startup even though the convenience method returns REFUSING_TRAFFIC.
boolean notYetPublished = raw == null;

ReadinessState safe = availability.getState(
        ReadinessState.class,
        ReadinessState.REFUSING_TRAFFIC);
~~~

**Do not conclude** that `getReadinessState() == REFUSING_TRAFFIC` proves a `REFUSING_TRAFFIC` event was published. That value may simply be the fallback.

### 3.3 Why Is getState(Class, defaultState) Useful?

The generic overload allows an `AvailabilityState` to be read with a caller-supplied fallback, provided the fallback is **non-null** and matches `stateType`. For example:

~~~java
LivenessState liveState = availability.getState(
        LivenessState.class,
        LivenessState.BROKEN);
~~~

This is the explicit form of how the convenience method chooses its default. For a custom state type provided by an extension, this overload is also useful for defining policy before any event arrives. However, typical applications only need the two standard enums; there is no need to invent new availability state types.

### 3.4 getLastChangeEvent: When You Need the Latest Event

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;

AvailabilityChangeEvent<ReadinessState> latest =
        availability.getLastChangeEvent(ReadinessState.class);

if (latest == null) {
    System.out.println("No readiness event has been received");
} else {
    System.out.println("Last readiness event state=" + latest.getState());
}
~~~

Besides `getState()`, `AvailabilityChangeEvent` inherits `getSource()` and `getTimestamp()` from Spring application events. They can be helpful for diagnostics, yet are **not** a complete history, carry no continuity guarantees like a durable event log, and an event's timestamp is not by itself the "time until ready".

Limits to remember:
- Returns **the latest event of a state type**, not every event since process start.
- Can be `null` when no event of that type has been received.
- An app or library can publish state-change events itself; not every event originates from Boot's startup milestones.
- "Latest" reflects the order in which events were **received** by the implementation, not necessarily real-world chronological order across multiple publishers in complex async designs.

## 4. State Storage Mechanism and Relationship with AvailabilityChangeEvent

Spring Boot provides `ApplicationAvailabilityBean`, which both implements `ApplicationAvailability` and acts as a listener for `AvailabilityChangeEvent<?>`. When it receives a state event, it records that event so reads via `getState(...)` and `getLastChangeEvent(...)` reflect the new information.

To **change state**, the application must publish `AvailabilityChangeEvent` through Spring's event infrastructure:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
class TrafficAdmission {
    private final ApplicationEventPublisher publisher;

    TrafficAdmission(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void pause() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    void resume() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

This class illustrates a runtime policy: `pause()` is used when the instance must temporarily pull out of routing; `resume()` is only called once serving preconditions are verified. It does **not** run automatically at startup, is not a cure-all for database errors, and does not directly close sockets or restart pods.

With default synchronous event publishing, `ApplicationAvailabilityBean` typically updates state while the event is being handled. If the project customizes the multicaster/executor, do not rely on assuming every listener finishes updating instantaneously. In real code needing synchronization, re-read after publishing and design the processing chain explicitly.

### Why Not Mutate ApplicationAvailabilityBean Directly?

`ApplicationAvailability` is a **read-oriented** interface. Reaching into the implementation to call `onApplicationEvent(...)` directly bypasses the event multicaster and other listeners, or even targets a standalone instance unrelated to the running context. To have the system observe the new state consistently, **publish the event** via `ApplicationContext` or `ApplicationEventPublisher`.

### Listening for Changes Instead of Polling Continuously

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ReadinessAudit {
    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS_CHANGED=" + event.getState());
    }
}
~~~

If you need to act **every time readiness changes**, a listener is better than polling every few milliseconds. If you only need a **snapshot right when a request/job begins**, inject `ApplicationAvailability` and read directly.

## 5. How Does State Change During Startup?

A critical part of reading state is understanding **at which milestone you are reading**.

~~~mermaid
flowchart TD
    A["SpringApplication.run(args)"] --> B["Prepare Environment/Context"]
    B --> C["refresh ApplicationContext"]
    C --> D["ApplicationStartedEvent"]
    D --> E["AvailabilityChangeEvent: LivenessState.CORRECT"]
    E --> F["ApplicationRunner / CommandLineRunner"]
    F --> G["ApplicationReadyEvent"]
    G --> H["AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC"]
~~~

Table for a standard successful startup:

| Phase | `getLivenessState()` | `getReadinessState()` | Reason |
| --- | --- | --- | --- |
| Before any liveness event | `BROKEN` (fallback) | `REFUSING_TRAFFIC` (fallback) | Not yet declared live/ready |
| Inside `ApplicationStartedEvent` listener | Usually still `BROKEN` if no liveness event yet | `REFUSING_TRAFFIC` | Boot emits the liveness event **after** started |
| Inside a normal `ApplicationRunner` | `CORRECT` | `REFUSING_TRAFFIC` | Started/liveness completed; runner not finished yet |
| Inside `ApplicationReadyEvent` listener | `CORRECT` | Usually still `REFUSING_TRAFFIC` | Boot emits the readiness accepting event **after** ready |
| After `AvailabilityChangeEvent<ReadinessState>` with accepting | `CORRECT` | `ACCEPTING_TRAFFIC` | Boot marks the instance ready |

The table assumes **no custom listener or component publishes other states itself**. In a real application, readiness may change between milestones, for instance if the system temporarily drains traffic.

### Reading Inside ApplicationStartedEvent

`ApplicationStartedEvent` occurs after the context has refreshed, **before** Boot publishes `LivenessState.CORRECT`. If a callback reads `getLivenessState()` and sees `BROKEN`, that does not necessarily mean the application hit a fault: it may be the fallback before the liveness event. Distinguish state actually published by an event from fallback values, and avoid making wrong operational conclusions from an overly early read.

### Reading Inside ApplicationRunner

Runners execute after liveness `CORRECT` and before readiness `ACCEPTING_TRAFFIC`. This is a useful place to demonstrate snapshots:

~~~java
@Bean
ApplicationRunner inspect(ApplicationAvailability availability) {
    return args -> {
        System.out.println(availability.getLivenessState());
        System.out.println(availability.getReadinessState());
    };
}
~~~

Place this method in a `@Configuration` or `@SpringBootApplication` class with appropriate imports. During startup without custom availability events, the two lines printed by the runner are typically:

~~~text
CORRECT
REFUSING_TRAFFIC
~~~

This is not a readiness error; the runner is part of the work that must finish **before** the ready milestone.

### Reading Inside ApplicationReadyEvent

`ApplicationReadyEvent` is published after runners, and **immediately after this event**, Boot publishes `AvailabilityChangeEvent<ReadinessState>` with `ACCEPTING_TRAFFIC`. Therefore, in a synchronous `@EventListener(ApplicationReadyEvent)`, readiness may still be `REFUSING_TRAFFIC`. To capture the exact transition, listen for the typed event `AvailabilityChangeEvent<ReadinessState>`.

### Shutdown and Post-Ready States

During graceful shutdown, Boot may transition readiness back to `REFUSING_TRAFFIC` so the platform stops routing new requests. Liveness can remain `CORRECT` during a valid drain period. After the context closes, do not rely on an availability bean that is no longer in an active lifecycle for external queries.

CLI/batch applications also have availability states and events even without an HTTP server. Thus `ACCEPTING_TRAFFIC` in a CLI app denotes Boot's availability milestone, not that the app opened an HTTP socket.

## 6. Complete Example: Java 17+, Maven, and Spring Boot 3.5.x

The goal is to **read actual state at different times**, observe `getLastChangeEvent(...)`, distinguish events from snapshots, and clearly see the gap between started and ready.

Create the following Maven project. It uses neither the web starter nor Actuator, demonstrating that availability is a core Spring Boot feature.

~~~text
availability-reader/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/availability/
    │       ├── AvailabilityReaderApplication.java
    │       └── StartupAvailabilityObserver.java
    └── test/
        └── java/com/example/availability/
            └── ApplicationAvailabilityBeanTest.java
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
    <artifactId>availability-reader</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
~~~

### File src/main/java/com/example/availability/AvailabilityReaderApplication.java

~~~java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AvailabilityReaderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AvailabilityReaderApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectState(ApplicationAvailability availability) {
        return args -> {
            System.out.println("03.RUNNER_LIVENESS="
                    + availability.getLivenessState());
            System.out.println("04.RUNNER_READINESS="
                    + availability.getReadinessState());

            AvailabilityChangeEvent<LivenessState> event =
                    availability.getLastChangeEvent(LivenessState.class);

            System.out.println("05.LAST_LIVENESS_EVENT="
                    + (event == null ? "none" : event.getState()));
        };
    }
}
~~~

### File src/main/java/com/example/availability/StartupAvailabilityObserver.java

~~~java
package com.example.availability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupAvailabilityObserver {

    private final ApplicationAvailability availability;

    public StartupAvailabilityObserver(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01.STARTED_SNAPSHOT="
                + availability.getLivenessState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        if (event.getState() == LivenessState.CORRECT) {
            System.out.println("02.LIVENESS_EVENT=CORRECT");
        }
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("06.READY_SNAPSHOT="
                + availability.getReadinessState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("07.READINESS_EVENT=ACCEPTING_TRAFFIC");
        }
    }
}
~~~

Note: in `onLiveness` and `onReadiness`, we print **the event's payload** instead of re-reading `ApplicationAvailability` immediately inside the callback for the same event. This avoids implicitly relying on execution order between the state-recording listener and the custom listener. In the runner and the next milestone's listener, reading the snapshot occurs at a clearer lifecycle point.

### Running the Application

From the directory containing `pom.xml`, with Maven and Java 17+:

~~~bash
mvn -q test
mvn -q -DskipTests package
java -jar target/availability-reader-0.0.1-SNAPSHOT.jar
~~~

Lines **explicitly printed by the example code** during a default startup:

~~~text
01.STARTED_SNAPSHOT=BROKEN
02.LIVENESS_EVENT=CORRECT
03.RUNNER_LIVENESS=CORRECT
04.RUNNER_READINESS=REFUSING_TRAFFIC
05.LAST_LIVENESS_EVENT=CORRECT
06.READY_SNAPSHOT=REFUSING_TRAFFIC
07.READINESS_EVENT=ACCEPTING_TRAFFIC
~~~

Spring Boot may interleave banners and other logs; this block lists only the lines prefixed with `01.` through `07.`. The output above assumes standard synchronous startup with no extra custom publishers/listeners modifying state.

Explanation:
1. `01`: during `ApplicationStartedEvent`, Boot has not yet published the standard liveness `CORRECT` event, so the convenience method returns fallback `BROKEN`.
2. `02`: the listener receives the liveness `CORRECT` event emitted by Boot after started.
3. `03`: the runner reads the latest liveness and gets `CORRECT`.
4. `04`: readiness is still `REFUSING_TRAFFIC` because the runner has not finished yet.
5. `05`: the latest liveness event has been stored with state `CORRECT`.
6. `06`: while the `ApplicationReadyEvent` callback executes, the standard readiness `ACCEPTING_TRAFFIC` availability event has not yet been published; the snapshot is still refusing.
7. `07`: the listener receives the readiness `ACCEPTING_TRAFFIC` event itself.

**Do not infer from a CLI run** that the application has web endpoints: this example has no web server, so the process may exit quickly after startup callbacks complete. State and events still carry meaning inside the Boot lifecycle.

### What Happens If a Runner Fails?

If you add a runner that throws an exception before ready, Spring Boot may already have emitted liveness `CORRECT`, yet the startup path never reaches normal ready/readiness accepting. The run may transition to `ApplicationFailedEvent`. This illustrates the difference between "context refreshed" and "full startup succeeded".

## 7. Unit Test: Distinguishing Default, Null, and Real Events

To test the implementation's behavior without creating a context or web server, you can instantiate `ApplicationAvailabilityBean` directly and feed events to it **as a unit test for that class**. Calling `onApplicationEvent` directly is strictly for testing; in production applications, publish through Spring's event infrastructure as in section 4.

### File src/test/java/com/example/availability/ApplicationAvailabilityBeanTest.java

~~~java
package com.example.availability;

import org.junit.jupiter.api.Test;
import org.springframework.boot.availability.ApplicationAvailabilityBean;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

import static org.junit.jupiter.api.Assertions.*;

class ApplicationAvailabilityBeanTest {

    @Test
    void defaultsExistBeforeAnyEvent() {
        ApplicationAvailabilityBean availability =
                new ApplicationAvailabilityBean();

        assertEquals(
                LivenessState.BROKEN,
                availability.getLivenessState());
        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());

        // Non-fallback version is still null.
        assertNull(availability.getState(LivenessState.class));
        assertNull(availability.getState(ReadinessState.class));
        assertNull(
                availability.getLastChangeEvent(ReadinessState.class));

        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getState(
                        ReadinessState.class,
                        ReadinessState.REFUSING_TRAFFIC));
    }

    @Test
    void lastEventAndCurrentStateAdvanceTogether() {
        ApplicationAvailabilityBean availability =
                new ApplicationAvailabilityBean();

        AvailabilityChangeEvent<ReadinessState> accepting =
                new AvailabilityChangeEvent<>(
                        "unit-test", ReadinessState.ACCEPTING_TRAFFIC);

        availability.onApplicationEvent(accepting);

        assertEquals(
                ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
        assertSame(
                accepting,
                availability.getLastChangeEvent(ReadinessState.class));
        assertEquals(
                "unit-test",
                availability.getLastChangeEvent(ReadinessState.class)
                        .getSource());

        AvailabilityChangeEvent<ReadinessState> refusing =
                new AvailabilityChangeEvent<>(
                        "maintenance", ReadinessState.REFUSING_TRAFFIC);

        availability.onApplicationEvent(refusing);

        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());
        assertSame(
                refusing,
                availability.getLastChangeEvent(ReadinessState.class));

        // No liveness event yet: the two state types are independent.
        assertNull(availability.getState(LivenessState.class));
        assertEquals(
                LivenessState.BROKEN,
                availability.getLivenessState());
    }

    @Test
    void livenessEventDoesNotOverwriteReadiness() {
        ApplicationAvailabilityBean availability =
                new ApplicationAvailabilityBean();

        availability.onApplicationEvent(
                new AvailabilityChangeEvent<>(
                        this, LivenessState.CORRECT));

        assertEquals(
                LivenessState.CORRECT,
                availability.getLivenessState());
        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());
        assertNull(
                availability.getLastChangeEvent(ReadinessState.class));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Three purposeful tests:
- Test 1 shows `getReadinessState()` can return `REFUSING_TRAFFIC` even when `getState(ReadinessState.class)` and `getLastChangeEvent(ReadinessState.class)` are `null`.
- Test 2 shows the latest event of the **same type** replaces the previous event in the snapshot and preserves the source.
- Test 3 shows liveness and readiness are **two independent state types**, not a single enum or shared boolean flag.

Do not use this implementation unit test to infer that every Spring Boot integration startup shares the exact same execution order. To verify `ApplicationStartedEvent`/`ApplicationReadyEvent` milestones, run the full example app in section 6 or write an integration test for `SpringApplication.run(...)`.

## 8. Reading State in Business Services

A service can inject `ApplicationAvailability` like a normal collaborator:

~~~java
package com.example.availability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AdmissionPolicy {
    private final ApplicationAvailability availability;

    public AdmissionPolicy(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean canAcceptNewWork() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

Place this class in a component-scanned package. `canAcceptNewWork()` reads the current state snapshot; if a high-priority job-enqueuing workflow needs strict guarantees, you still need separate synchronization/idempotency to prevent races if readiness changes right after the read.

### Using One Snapshot for One Short Decision

~~~java
ReadinessState state = availability.getReadinessState();

if (state == ReadinessState.ACCEPTING_TRAFFIC) {
    // Can consider accepting a new unit of work.
} else {
    // Temporarily refuse or enqueue according to policy.
}
~~~

This snippet is just a method skeleton, not a complete admission control system. If the service sits behind a load balancer that already has a readiness probe, you may not need to check on every request. Conversely, for a consumer reading from a queue, HTTP route readiness state does not automatically pause queue polling; you need the consumer's own controller or corresponding pause/resume mechanism.

### Avoid Checking Availability in Constructors or @PostConstruct

Constructors and `@PostConstruct` run while the container creates beans, **before** started/ready milestones occur. Reading state there very normally returns fallback `BROKEN`/`REFUSING_TRAFFIC`. Do not throw a startup exception just because a newly created bean reads `getReadinessState() != ACCEPTING_TRAFFIC`; it cannot be accepting until startup finishes.

If you need to run a check after context refresh and before ready, use an `ApplicationRunner` and handle the result as required. If you need a callback when readiness transitions from refusing to accepting, use `@EventListener` for `AvailabilityChangeEvent<ReadinessState>`.

## 9. Reading Events and Snapshots Are Not the Same Operation

Operational question determines the API:

| Need to Know | How to Do It |
| --- | --- |
| "Is it ready right now?" | `getReadinessState() == ACCEPTING_TRAFFIC` |
| "Is it live right now?" | `getLivenessState() == CORRECT` |
| "Has any readiness event been received yet?" | `getLastChangeEvent(ReadinessState.class) != null` |
| "What value was actually published by the last event?" | `getState(ReadinessState.class)`, noting it may be null |
| "Read with an explicit fallback?" | `getState(ReadinessState.class, REFUSING_TRAFFIC)` |
| "Handle immediately whenever readiness changes?" | `@EventListener` with `AvailabilityChangeEvent<ReadinessState>` |
| "Who/what was the source of the latest event?" | `getLastChangeEvent(...).getSource()` after a null check |
| "Need full change history?" | Set up separate logging/metrics/event storage; the API only keeps the latest event |

**Snapshots do not generate events:** calling `getReadinessState()` a thousand times does not emit a thousand `AvailabilityChangeEvent`s.

**Events do not equal health probes:** reading `event.getState()` inside an application event listener does not mean Kubernetes already knows the new state; kubelet observes probe results on its polling interval and configured parameters.

### Do Not Use Timestamps as Durations

`ApplicationEvent.getTimestamp()` can tell when the event object was created. Yet from the timestamp alone you cannot deduce the lag between the service receiving the event and the platform starting to route traffic, nor infer database warm-up completion time. To measure duration, you need proper start/end timestamps with dedicated clocks and metrics.

## 10. Relationship with Actuator Liveness/Readiness Probes

When an application uses Spring Boot Actuator and a web runtime, availability states can be represented via health indicators/groups for infrastructure observation. Common paths:

- `/actuator/health/liveness` corresponds to `LivenessState`.
- `/actuator/health/readiness` corresponds to `ReadinessState`.

If enabling health probes in an environment that does not enable them automatically:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

This configuration is **only relevant when Actuator and appropriate web endpoints are present**. It does not start a web server in an app that only has `spring-boot-starter` like in section 6.

### Read State in Java or Call the Endpoint Over HTTP?

- **In the same process:** inject `ApplicationAvailability`; fast, no HTTP request needed, independent of management port.
- **From an orchestrator or external host:** use the health probe over Actuator/HTTP or another probe; external systems cannot inject a bean inside the running JVM process.
- **When end-to-end checks are needed:** use dedicated endpoints/health checks matching that goal, rather than expecting pure liveness/readiness to reflect every upstream system.

### What HTTP Codes Can Probes Produce?

In a typical Actuator setup, liveness `CORRECT` maps to health `UP` and `BROKEN` maps to `DOWN`; readiness `ACCEPTING_TRAFFIC` maps to `UP` and `REFUSING_TRAFFIC` maps to `OUT_OF_SERVICE`. Health statuses have default HTTP mappings that can be reconfigured; do not write business clients requiring a single hardcoded HTTP code without checking app policy.

Example observation commands if endpoints are enabled:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

These commands **do not apply** to the CLI app in section 6 because that project does not start a web server. For production apps, confirm the base path, management port, Spring Security, network policy, ingress, and probe access permissions.

### If the Management Port Differs from the Business Port

A probe hitting only the management port might be healthy while the business connector has issues. Spring Boot supports adding probe aliases to the main application port when conditions match:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Default aliases are typically `/livez` and `/readyz` on the main server port; verify the actual active paths before configuring Kubernetes.

### How Does Kubernetes Typically Use State?

A liveness failure can cause kubelet to restart the container. A readiness failure typically removes the pod from the Service's traffic-receiving endpoints. Publishing `ReadinessState.REFUSING_TRAFFIC` in the app **does not** modify Kubernetes objects directly; Actuator/probe endpoints must reflect the state, and kubelet needs properly configured probes to observe it.

For long startups, `startupProbe` may be needed so the container is not restarted before context refresh and liveness is marked `CORRECT`. Base probe settings on measured startup times, avoiding overly aggressive settings that trigger restart loops.

## 11. Operational Scenarios: Reading State for the Right Purpose

### A. Warm-Up After Context Refresh

A runner needs to load a local lookup table. Inside the runner, state is usually `CORRECT` / `REFUSING_TRAFFIC`. That is expected: do not fail just because readiness is refusing before the runner itself finishes. Only after the runner completes does Boot publish the ready milestone.

### B. Pausing Traffic Without Restarting the Process

The application needs maintenance or a role change. It publishes `ReadinessState.REFUSING_TRAFFIC`, keeping liveness `CORRECT`. Components can check `getReadinessState()` before taking new jobs. Kubelet will observe the readiness probe and stop routing traffic on its polling cycle.

### C. Internal Cache Loses Self-Recovery Capability

If a component truly breaks beyond recovery, the application can publish `LivenessState.BROKEN`. Do not do this for an isolated external timeout. After publishing, whether a restart occurs still depends on the platform, probe settings, and restart policy.

### D. No Events Yet in a Manually Instantiated Implementation

A unit test calling `new ApplicationAvailabilityBean()` without feeding any events gets fallbacks `BROKEN`/`REFUSING_TRAFFIC`, while `getState(...)` returns null. Do not treat that as a "Spring Boot hasn't started" bug: a manually created test object is not a bean registered in the application lifecycle.

### E. After Graceful Shutdown

When the app begins shutting down, readiness can revert to `REFUSING_TRAFFIC` to accept fewer new requests while liveness stays `CORRECT` as in-flight requests drain. Once the context closes, do not keep a reference to the availability bean for out-of-process health checks.

## 12. Common Errors and Diagnostics

### "getReadinessState() is always REFUSING_TRAFFIC in @PostConstruct"

`@PostConstruct` runs during bean initialization, before `ApplicationReadyEvent`. This is normally a valid fallback, not proof that the server will never become ready. Read in a runner/after-ready or listen for the readiness accepting event.

### "getState(ReadinessState.class) is null while getReadinessState() is non-null"

That matches the **exact API contract**. The non-fallback variant returns null when no event exists. The convenience method uses `REFUSING_TRAFFIC` as a fallback. If you need to know whether an event actually arrived, check `getLastChangeEvent(ReadinessState.class)`.

### "Inside ApplicationReadyEvent, readiness is still refusing"

Boot publishes `ApplicationReadyEvent` and only then publishes `AvailabilityChangeEvent` for readiness accepting. Wait for the typed event or read state after that milestone. Do not equate the name "ReadyEvent" with the availability state already having been recorded.

### "I reassigned the enum in a local variable, yet real state didn't change"

`ReadinessState state = availability.getReadinessState()` only reads a value. Assigning `state = ACCEPTING_TRAFFIC` does not mutate state inside `ApplicationAvailabilityBean`. You must publish `AvailabilityChangeEvent` via Spring's event infrastructure.

### "Published an event, yet ApplicationAvailability still returns the old state"

Check whether you published through the **active** context/publisher, which listeners received the event, whether there is a context hierarchy, a custom multicaster, an async executor, or another source publishing state afterward. Avoid instantiating a separate `ApplicationAvailabilityBean` and comparing it against the context bean.

### "Readiness is accepting, yet requests still don't arrive"

Internal readiness does not replace probes, load balancers, networking, security, port binding, or dependency health. Check health group/probe configuration, kubelet polling schedule, EndpointSlice/Service, and ingress. Do not try to fix it by repeatedly publishing accepting state.

### "Readiness refusing removes every replica"

If readiness is tied to a shared external service and that service goes down, all pods may become unready together. Weigh business fail-open/fail-closed behavior, retries/fallbacks, and routing goals before adding a dependency check to the readiness group.

### "Liveness is BROKEN, yet kubelet does not restart"

There may be no `livenessProbe`, wrong path/port, health endpoint not reflecting state, or failure threshold not yet met. `ApplicationAvailability` only stores the internal signal; restarting belongs to platform orchestration.

### "Test expects an exact number of events and fails"

Boot and extensions can publish additional availability changes; test by **state type** and target state, or unit-test an isolated `ApplicationAvailabilityBean`. Do not write an integration test assuming there are only two events in the application's entire lifetime.

### "Two consecutive state reads do not match"

This can be a valid update between the two reads. If logic requires a consistent decision, read one snapshot into a local variable at the decision point and design extra coordination when multiple threads are involved; the API does not provide transactions across business workflows.

## 13. Checklist for Using ApplicationAvailability Properly

1. Inject `ApplicationAvailability` from the context rather than calling `new ApplicationAvailabilityBean()` in production services.
2. Distinguish **liveness** (internal ability to operate) from **readiness** (permission to receive new traffic).
3. Use `getLivenessState()` / `getReadinessState()` for checks with fallbacks.
4. Use `getState(Class)` when you need to know **which state was actually published**, and handle possible `null`.
5. Use `getLastChangeEvent(Class)` when you need the latest event or metadata, remembering to handle `null`.
6. Do not call `getReadinessState()` too early and treat `REFUSING_TRAFFIC` as a startup failure.
7. To **change state**, publish `AvailabilityChangeEvent`; do not reassign local variable references.
8. To react on each state transition, listen to `AvailabilityChangeEvent<S>` with the right generic type.
9. Do not use availability state as a substitute for other necessary technical health checks.
10. Do not attach every external dependency to the liveness probe.
11. With Kubernetes, verify the actual Actuator path, management/main port, security, and probe thresholds.
12. For tests, separate `ApplicationAvailabilityBean` unit tests from `SpringApplication` lifecycle integration tests.

## 14. Self-Check Questions

**1. Does `ApplicationAvailability` return the current state without making an HTTP call?**  
Yes. It is an interface injected within the same application that reads in-memory managed state.

**2. What does `getLivenessState()` return before any liveness event?**  
`LivenessState.BROKEN` as the standard fallback.

**3. What does `getReadinessState()` return before any readiness event?**  
`ReadinessState.REFUSING_TRAFFIC` as the standard fallback.

**4. Is `getState(ReadinessState.class)` guaranteed to be non-null?**  
No; it can return `null` when no readiness event has occurred yet.

**5. How does `getState(ReadinessState.class, REFUSING_TRAFFIC)` differ?**  
It provides a caller-chosen non-null fallback if no event has arrived yet.

**6. Which API should you use to get the most recent readiness event?**  
`getLastChangeEvent(ReadinessState.class)`, remembering to handle `null`.

**7. Does `ApplicationAvailabilityBean` retain the full event history?**  
No; this API provides the latest state and event per type, not a durable event log.

**8. What does reading readiness inside an `ApplicationRunner` usually show?**  
`REFUSING_TRAFFIC`, because runners execute before Boot emits readiness accepting.

**9. Why can `ApplicationReadyEvent` still see refusing?**  
Because the accepting readiness availability event is published immediately after `ApplicationReadyEvent`.

**10. To pause receiving traffic, should you publish `LivenessState.BROKEN`?**  
Usually no. Use `ReadinessState.REFUSING_TRAFFIC` if the process is still live and can recover.

**11. If an external database is down, should liveness always switch to BROKEN?**  
No; a shared dependency failure does not mean restarting every instance will help.

**12. Does `getReadinessState()==ACCEPTING_TRAFFIC` automatically guarantee Kubernetes is routing traffic?**  
No; the platform also depends on probe polling, Service/ingress/networking, and orchestration rules.

**13. Can `ApplicationAvailability` be used in a batch app with no HTTP?**  
Yes. Availability is a Spring Boot core mechanism and does not require a web server.

**14. Does publishing an availability event automatically create an Actuator endpoint?**  
No. You need the Actuator dependency/configuration and appropriate web exposure.

**15. Should you read state or listen for events?**  
Read state for point-in-time decisions; listen for events when you need to execute an action on every state transition.

## 15. Official Documentation and Version Reference

- [Spring Boot 3.5 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html): defines `getState`, `getLastChangeEvent`, `getLivenessState`, and `getReadinessState`.
- [Spring Boot 3.5 — ApplicationAvailabilityBean API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailabilityBean.html): implementation that updates state from events.
- [Spring Boot 3.5 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): generic event, `getState`, and `publish`.
- [Spring Boot 3.5 — SpringApplication / Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): meaning of liveness, readiness, how to read them, and event ordering.
- [Spring Boot 3.5 — Actuator Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): startup/shutdown phases, health probes, endpoints, and integration mechanics.
- [Spring Boot 3.5 — LivenessState](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/LivenessState.html) and [ReadinessState](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html): enum values and semantics.

This lesson uses Java 17+ and Spring Boot 3.5.16 for examples. When deploying on another version, verify the exact Spring Boot and Spring Framework versions in your project's dependency tree, especially when using custom application event multicasters or health probe extensions.