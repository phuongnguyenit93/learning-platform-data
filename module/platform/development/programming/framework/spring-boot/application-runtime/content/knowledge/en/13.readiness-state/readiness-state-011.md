# Boundary Between Lifecycle State and Actuator Health Groups

## 1. Problem to Solve

Spring Boot supports two related yet non-identical mechanisms:

- **Application Availability State**: in-memory values reflecting startup progress, operational soundness, and traffic-acceptance capability. The two axes are `LivenessState` and `ReadinessState`.
- **Actuator Health Endpoint / Health Groups**: aggregates results from `HealthIndicator`s into a `Status`, then maps it to an HTTP response. Two important health groups are `liveness` and `readiness`.

You cannot conclude for certain that a health endpoint returns 200 solely from `ApplicationAvailability.getReadinessState() == ACCEPTING_TRAFFIC`. For example, if the readiness group is configured to include a custom `HealthIndicator` reporting `DOWN`, `/actuator/health/readiness` can return **503** while the lifecycle state remains `ACCEPTING_TRAFFIC`.

Conversely, global `/actuator/health` reporting `DOWN` does not prove `/actuator/health/readiness` is also `DOWN`, because the two endpoints can check different contributors.

This is a key boundary within the **Readiness State** section of Spring Boot Application Runtime: state is an **internal signal**, whereas a health group is an **evaluation and publication policy** for monitoring systems, load balancers, or Kubernetes.

### Questions You Will Be Able to Answer

1. How do `ApplicationAvailability` and `AvailabilityChangeEvent` differ from `HealthIndicator`?
2. When does Spring Boot publish `LivenessState.CORRECT` and `ReadinessState.ACCEPTING_TRAFFIC`?
3. Why does the readiness health group not automatically include every database, Redis, and external service indicator?
4. Why can state be accepting while the HTTP readiness probe returns 503?
5. When is adding an external dependency to readiness sensible, and when does it cause system-wide traffic loss?
6. How to write a Spring Boot Java 17+ application to verify this distinction yourself.

## 2. Four-Layer Model

~~~text
    SpringApplication events and application decisions
                              |
                   AvailabilityChangeEvent
                              |
                              v
                  ApplicationAvailability
                  /                    \
                 v                      v
           LivenessState            ReadinessState
          CORRECT / BROKEN         ACCEPTING_TRAFFIC /
                                   REFUSING_TRAFFIC
                 |                      |
                 v                      v
       LivenessStateHealthIndicator  ReadinessStateHealthIndicator
                 |                      |
                 v                      v
        Health Group: liveness    Health Group: readiness
           (livenessState)       (readinessState, and optional others)
                                        |
                         +--------------+-------------+
                         |                            |
                    Custom HealthIndicator        StatusAggregator
                    such as demoDependency        + HttpCodeStatusMapper
                         |                            |
                         +----------------------------+
                                        |
                                 HTTP health response
                           /actuator/health/readiness
                                        |
                         Kubelet / load balancer / monitor
~~~

This model has four layers:

| Layer | Responsibility | Example |
| --- | --- | --- |
| **Availability state** | Store internal lifecycle/availability signals | `ReadinessState.ACCEPTING_TRAFFIC` |
| **Availability event** | Broadcast state change information | `AvailabilityChangeEvent<ReadinessState>` |
| **Health contributor** | Check one condition and return `Health/Status` | `Health.down().build()` |
| **Health group + HTTP** | Select contributors, aggregate, map status | `/actuator/health/readiness` → 503 |

One `HealthIndicator` may rely on availability state, while another may check a cache, disk space, or external connectivity. A health group decides **which indicators have authority to influence the group's overall status**. That is exactly where the boundary lies.

### Does Having ApplicationAvailability Imply Actuator HTTP Endpoints?

No. `ApplicationAvailability` is a Spring Boot core feature and can be injected even without Actuator installed. To get Actuator's HTTP endpoints, the project needs the `spring-boot-starter-actuator` dependency, an appropriate web server/transport, and configuration exposing the endpoints.

Adding Actuator also does not make every health endpoint reachable at all times: if the HTTP server is not listening yet, is shutting down, or is blocked by the network, you may hit connection errors rather than receiving a JSON status.

## 3. LivenessState and ReadinessState

### LivenessState: Does the Application Need a Restart?

Spring Boot has two primary values:

- `CORRECT`: internal state is considered still able to operate. A self-recoverable external outage does not necessarily break liveness.
- `BROKEN`: the application is deemed in an unrecoverable state per policy and may need an instance restart.

**Do not put a database or external API check into liveness by default.** If a shared database is disrupted, restarting pods en masse does not fix the database, and can even trigger a connection storm during recovery.

### ReadinessState: Should It Receive New Traffic?

- `ACCEPTING_TRAFFIC`: the application announces it is ready to receive traffic.
- `REFUSING_TRAFFIC`: the application announces it should not receive new traffic yet.

Unlike liveness, readiness can temporarily refuse traffic during startup, warm-up, overload, or preparing for shutdown. Kubelet typically uses a readiness probe to add or remove a pod from Service serving endpoints. **A readiness failure is not a request to restart the pod.**

### The Two Axes Are Independent

A completely valid state is:

~~~text
LivenessState  = CORRECT
ReadinessState = REFUSING_TRAFFIC
~~~

This means the JVM and Spring context are running normally, yet the application does not want new requests yet. This is typically the period after context refresh and before runners finish.

### Access API

Inside a Spring Boot bean:

~~~java
@Component
class AvailabilityView {
    private final ApplicationAvailability availability;

    AvailabilityView(ApplicationAvailability availability) {
        this.availability = availability;
    }

    void show() {
        System.out.println(availability.getLivenessState());
        System.out.println(availability.getReadinessState());
    }
}
~~~

This is an illustrative snippet, **not a standalone Java program**. Import `org.springframework.stereotype.Component` and `org.springframework.boot.availability.ApplicationAvailability`; to run, it must live inside a Spring Boot application.

This state does not measure DB or cache health on its own. It reflects availability events published by Boot and application components.

## 4. Lifecycle Milestones and Default States

Spring Boot 3.5 sequence overview:

~~~text
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  +-- Prepare Environment / ApplicationContext
  +-- ApplicationContext.refresh()
  |
  +-- ApplicationStartedEvent
  +-- AvailabilityChangeEvent: LivenessState.CORRECT
  |
  +-- ApplicationRunner / CommandLineRunner
  |      default readiness is still REFUSING_TRAFFIC
  |
  +-- ApplicationReadyEvent
  +-- AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
  |
  v
run() succeeds
~~~

Before startup completes, Spring Boot treats liveness as `BROKEN` and readiness as `REFUSING_TRAFFIC` in the availability lifecycle. Liveness transitions to `CORRECT` after context refresh, whereas readiness only transitions to `ACCEPTING_TRAFFIC` after runners and the Ready event.

Notably: **`ApplicationReadyEvent` arrives before the availability event switching to accepting**. Therefore, do not assume a listener receiving `ApplicationReadyEvent` itself already sees `getReadinessState() == ACCEPTING_TRAFFIC`.

During shutdown, readiness can revert to `REFUSING_TRAFFIC` to assist stopping new requests. However, once the HTTP server stops accepting connections, probes are not guaranteed to receive a 503 response; they may no longer be able to connect at all.

| Phase | Typical Liveness | Typical Readiness | HTTP Probe |
| --- | --- | --- | --- |
| Starting, server not running yet | `BROKEN` | `REFUSING_TRAFFIC` | Endpoint may not exist to call yet |
| After context refresh, while runners execute | `CORRECT` | `REFUSING_TRAFFIC` | May reflect not ready if HTTP is already serving |
| After Ready and availability event | `CORRECT` | `ACCEPTING_TRAFFIC` | Normally ready if group has no failing indicators |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | May no longer serve new probes |
| Shutdown complete | No active context left | No active context left | Endpoint has stopped |

The gap between in-memory state and actual probes is especially important when analyzing startup timeouts or graceful shutdown on Kubernetes.

## 5. HealthIndicator and Actuator Status

### HealthIndicator Is Not the Same as AvailabilityState

In Spring Boot 3.5, `org.springframework.boot.actuate.health.HealthIndicator` has the `Health health()` method. A `HealthIndicator` checks a specific condition when invoked and returns a `Health`.

Example:

~~~java
@Bean("demoDependency")
HealthIndicator demoDependency(DemoDependencyState state) {
    return () -> state.isUp()
            ? Health.up().build()
            : Health.down().build();
}
~~~

The snippet above is **illustrative**, requiring `@Bean`, `Health`, `HealthIndicator`, and a `DemoDependencyState` class. A complete runnable program is in section 8.

If the dependency flips from UP to DOWN, the indicator reports `Status.DOWN`. That change **does not automatically publish** `AvailabilityChangeEvent<ReadinessState>` and does not necessarily alter `ApplicationAvailability`.

Conversely, when the application publishes `ReadinessState.REFUSING_TRAFFIC`, other indicators such as disk space or `demoDependency` can remain `UP`.

### Status and HTTP Code

Actuator health typically uses:

| `Status` | Meaning | Typical Default HTTP |
| --- | --- | --- |
| `UP` | Component/group satisfies healthy criteria | 200 |
| `DOWN` | Component/group has failed | 503 |
| `OUT_OF_SERVICE` | Component/group should not be used | 503 |
| `UNKNOWN` | Cannot be determined | 200 under default mapping |

These are default rules, not fixed codes across every project. Spring Boot allows customizing `StatusAggregator` and `HttpCodeStatusMapper`, including at the health-group level. Distinguish:

1. **Aggregation:** choosing a representative status from contributors in the group.
2. **Mapping:** translating the representative status into an HTTP status code.

With the default converters:

- `LivenessState.CORRECT` is typically represented by `LivenessStateHealthIndicator` as `UP`.
- `LivenessState.BROKEN` as `DOWN`.
- `ReadinessState.ACCEPTING_TRAFFIC` as `UP`.
- `ReadinessState.REFUSING_TRAFFIC` as `OUT_OF_SERVICE`.

This is a **state-to-health translation**, not an enum identity.

### Global Health and Health Groups Can Differ

Actuator has the global `/actuator/health` endpoint, which typically checks many enabled contributors. Meanwhile, `/actuator/health/readiness` only checks contributors belonging to the `readiness` group. Thus you can observe:

~~~text
ApplicationAvailability.readiness = ACCEPTING_TRAFFIC
/actuator/health/readiness       = UP   (HTTP 200)
/actuator/health                 = DOWN (HTTP 503)
~~~

A database indicator being DOWN in global health while excluded from the readiness group is a classic example. This is behavior driven by **group membership policy**, not a system bug.

## 6. The Liveness and Readiness Health Groups

### Enabling Probes Locally

Spring Boot enables liveness/readiness health groups automatically in recognized Kubernetes environments. To enable them explicitly in all environments:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

With Actuator and a web application, you can access:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
~~~

Normally only the `health` endpoint is exposed over HTTP by default; you do not need to expose every management endpoint.

### Default Members of the Two Groups

~~~text
liveness Health Group:
  livenessState

readiness Health Group:
  readinessState
~~~

Spring Boot **does not automatically place all indicators such as database, Redis, or external APIs into the readiness or liveness group**. This prevents the system from losing all replicas at once when a shared dependency fails.

### Extending the Readiness Group

When business requirements truly call for adding a custom check `demoDependency`:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,demoDependency
~~~

Then:

~~~text
readinessState    -> UP
demoDependency    -> DOWN
          |
          v
StatusAggregator  -> DOWN
          |
          v
HttpCodeStatusMapper -> HTTP 503
~~~

Even though `ApplicationAvailability.getReadinessState()` is still `ACCEPTING_TRAFFIC`, **the readiness group is failing**. That is the core lesson.

Do not blindly copy `include=*` or dump every external health check into readiness. Identify which indicators relate **directly to the ability to serve essential traffic**.

If a contributor is configured in a group yet does not exist, Spring Boot by default can fail startup during membership validation. Use exact contributor IDs rather than disabling validation just to mask misconfiguration.

### When Should External Dependencies Go Into Readiness?

You must answer:

- If the dependency fails, are all requests unservable, or is there a fallback?
- Is the dependency shared across all pods?
- Can some features that do not use that dependency still serve?
- Is the health check lightweight with an appropriate timeout?
- If every pod is pulled from the load balancer, do users get a better experience?

**Liveness** should avoid relying on external services because a shared service outage can trigger a restart storm. **Readiness** may include an external check if lacking it renders the instance unable to serve, yet that is an architectural decision, not Boot's default.

## 7. Matrix of Easily Confused Scenarios

Assume the readiness group is extended to include `readinessState` and `demoDependency`, while the liveness group contains only `livenessState`; default mappings are kept.

| Liveness State | Readiness State | Demo Dependency | Health Liveness | Health Readiness |
| --- | --- | --- | --- | --- |
| `CORRECT` | `ACCEPTING_TRAFFIC` | `UP` | UP / 200 | UP / 200 |
| `CORRECT` | `ACCEPTING_TRAFFIC` | `DOWN` | UP / 200 | DOWN / 503 |
| `CORRECT` | `REFUSING_TRAFFIC` | `UP` | UP / 200 | OUT_OF_SERVICE / 503 |
| `CORRECT` | `REFUSING_TRAFFIC` | `DOWN` | UP / 200 | Unhealthy status / 503 |
| `BROKEN` | `ACCEPTING_TRAFFIC` | `UP` | DOWN / 503 | UP / 200 |

The last row illustrates the two independent axes, not a recommendation to set liveness `BROKEN` while readiness is accepting. Infrastructure can restart the instance due to the failing liveness probe even though the readiness group stays UP.

The table only applies **while the HTTP server is serving endpoints**. If the process dies, the port is blocked, or shutdown finishes, there is no guarantee an HTTP response will be returned.

## 8. Runnable Java 17+ Example with Spring Boot 3.5.16

We will build a Spring MVC + Actuator application with a custom `HealthIndicator`. Demo endpoints let us toggle independently:

- Health of `demoDependency`: UP ↔ DOWN.
- Spring Boot's `ReadinessState`: ACCEPTING_TRAFFIC ↔ REFUSING_TRAFFIC.

This lets us directly observe that the readiness group is not merely the output of `ApplicationAvailability`.

**Use state-changing endpoints strictly in local/practice environments. Do not expose them in production or on public networks.**

### 8.1. Project Structure

~~~text
health-boundary-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/healthboundary/
    │   └── HealthBoundaryApplication.java
    └── resources/
        └── application.properties
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>health-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

File `src/main/java/com/example/healthboundary/HealthBoundaryApplication.java`:

~~~java
package com.example.healthboundary;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HealthBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthBoundaryApplication.class, args);
    }

    @Bean
    DemoDependencyState demoDependencyState() {
        return new DemoDependencyState();
    }

    // Bean name is the health contributor ID: demoDependency.
    @Bean("demoDependency")
    HealthIndicator demoDependencyIndicator(DemoDependencyState state) {
        return () -> state.isUp()
                ? Health.up().build()
                : Health.down().build();
    }

    @Bean
    DemoController demoController(
            DemoDependencyState state,
            ApplicationAvailability availability,
            ApplicationEventPublisher publisher) {
        return new DemoController(state, availability, publisher);
    }

    @Bean
    ApplicationRunner startupTrace(ApplicationAvailability availability) {
        return args -> System.out.println(
                "RUNNER_READINESS=" + availability.getReadinessState());
    }

    static final class DemoDependencyState {
        private final AtomicBoolean up = new AtomicBoolean(true);

        boolean isUp() {
            return up.get();
        }

        void setUp(boolean value) {
            up.set(value);
        }
    }

    @RestController
    static final class DemoController {
        private final DemoDependencyState dependency;
        private final ApplicationAvailability availability;
        private final ApplicationEventPublisher publisher;

        DemoController(DemoDependencyState dependency,
                       ApplicationAvailability availability,
                       ApplicationEventPublisher publisher) {
            this.dependency = dependency;
            this.availability = availability;
            this.publisher = publisher;
        }

        @GetMapping(value = "/demo/state",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> state() {
            return Map.of(
                    "livenessState",
                    availability.getLivenessState().name(),
                    "readinessState",
                    availability.getReadinessState().name(),
                    "dependency",
                    dependency.isUp() ? "UP" : "DOWN");
        }

        @PostMapping("/demo/dependency/down")
        public String dependencyDown() {
            dependency.setUp(false);
            return "DEPENDENCY_DOWN";
        }

        @PostMapping("/demo/dependency/up")
        public String dependencyUp() {
            dependency.setUp(true);
            return "DEPENDENCY_UP";
        }

        @PostMapping("/demo/readiness/refuse")
        public String refuseTraffic() {
            AvailabilityChangeEvent.publish(
                    publisher, this, ReadinessState.REFUSING_TRAFFIC);
            return "READINESS_REFUSING_TRAFFIC";
        }

        @PostMapping("/demo/readiness/accept")
        public String acceptTraffic() {
            AvailabilityChangeEvent.publish(
                    publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
            return "READINESS_ACCEPTING_TRAFFIC";
        }
    }
}
~~~

This is a complete Java file for the Maven project above. The controller is a bean registered via a `@Bean` method and discovered via `@RestController`. The `HealthIndicator` bean is named `demoDependency`, matching the ID referenced in the group configuration.

`DemoDependencyState` uses `AtomicBoolean` so the simulated state updates safely across requests. It does not represent a real connection; the example strictly demonstrates the boundary.

### 8.2. application.properties

File `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Enable liveness/readiness health groups even on local machine.
management.endpoint.health.probes.enabled=true

# Combine Boot's state with a custom HealthIndicator.
management.endpoint.health.group.readiness.include=readinessState,demoDependency

# Add /livez and /readyz on the main web port.
management.endpoint.health.probes.add-additional-paths=true

# Do not expose unnecessary health details.
management.endpoint.health.show-details=never
~~~

No separate `management.server.port` is set, so the web app and Actuator share port 8080. The `health` endpoint is exposed by default in standard Actuator configurations.

### 8.3. Run the Program

From the directory containing `pom.xml`:

~~~bash
mvn package
java -jar target/health-boundary-demo-0.0.1-SNAPSHOT.jar
~~~

Or:

~~~bash
mvn spring-boot:run
~~~

In the startup logs, one line printed by the demo code itself:

~~~text
RUNNER_READINESS=REFUSING_TRAFFIC
~~~

This is the runner milestone, after context refresh yet before `ApplicationReadyEvent` and the availability event switching readiness to accepting. Maven and framework logs may interleave. Once startup finishes along the normal path, liveness is `CORRECT` and readiness is `ACCEPTING_TRAFFIC`.

### 8.4. Normal Case

After the application finishes starting, run in another terminal:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/demo/state
~~~

Expected results in the demo:

- Liveness group: `UP`, HTTP 200.
- Readiness group: `UP`, HTTP 200.
- Global health: `UP`, HTTP 200.
- State in `/demo/state`: `livenessState=CORRECT`, `readinessState=ACCEPTING_TRAFFIC`, `dependency=UP`.

With details hidden, a health response looks like:

~~~json
{"status":"UP"}
~~~

A state response looks like the following; JSON key order is not guaranteed:

~~~json
{
  "livenessState": "CORRECT",
  "readinessState": "ACCEPTING_TRAFFIC",
  "dependency": "UP"
}
~~~

### 8.5. Health Group Goes DOWN While Readiness State Is Still ACCEPTING

Call:

~~~bash
curl -X POST http://localhost:8080/demo/dependency/down
curl -s http://localhost:8080/demo/state
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health
~~~

Expected results:

| Check | Result |
| --- | --- |
| `ApplicationAvailability.getReadinessState()` | Still `ACCEPTING_TRAFFIC` |
| Custom `HealthIndicator` | `DOWN` |
| Readiness health group | `DOWN`, HTTP 503 |
| Liveness health group | `UP`, HTTP 200 |
| Global health | `DOWN`, HTTP 503 in the demo |

No availability event is emitted automatically when `dependency.setUp(false)` runs. **Only the health indicator's result changed**, and the readiness group aggregates both contributors, returning 503.

Restore:

~~~bash
curl -X POST http://localhost:8080/demo/dependency/up
curl -i http://localhost:8080/actuator/health/readiness
~~~

The readiness group returns to `UP`/200 provided all remaining contributors are healthy.

### 8.6. ReadinessState Switches to REFUSING Even Though Dependency Is UP

Ensure the dependency is UP, then call:

~~~bash
curl -X POST http://localhost:8080/demo/readiness/refuse
curl -s http://localhost:8080/demo/state
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
~~~

Expected:

- `/demo/state`: `readinessState=REFUSING_TRAFFIC`, `dependency=UP`.
- `ReadinessStateHealthIndicator`: `OUT_OF_SERVICE`.
- `/actuator/health/readiness`: 503 per default mapping.
- `/actuator/health/liveness`: still 200 since liveness did not change.

Restore readiness:

~~~bash
curl -X POST http://localhost:8080/demo/readiness/accept
curl -i http://localhost:8080/actuator/health/readiness
~~~

Note: in real applications, only publish `ACCEPTING_TRAFFIC` when business criteria justify it; never use this state to mask a failing health indicator.

### 8.7. Changing Group Membership Changes the Result Without Changing State

Remove this configuration line:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,demoDependency
~~~

Restart the application. When you call `/demo/dependency/down`, global health can go `DOWN`, yet the default readiness group only checks `readinessState`, so it remains `UP` as long as state is `ACCEPTING_TRAFFIC`.

This proves the HTTP outcome depends on **group membership**. Changing a group changes which checks run, not the enum state in `ApplicationAvailability`.

## 9. Kubernetes: Liveness, Readiness, and Startup Probes

Kubelet uses each probe type for different decisions:

| Probe | Operational Meaning | Typical Reaction |
| --- | --- | --- |
| Liveness | Does the process need a restart because it cannot self-recover? | Restart container after consecutive failures |
| Readiness | Should the pod be included in traffic-receiving endpoints? | Remove or add pod to traffic |
| Startup | Does it need longer before liveness/readiness take effect? | Delay impact of the other probes during startup |

Illustrative YAML snippet for the app above:

~~~yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  failureThreshold: 2

startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 30
~~~

This is a probe snippet inside a container spec, **not a complete Kubernetes manifest**. Use only after verifying the real image, port, startup time, and resources.

`/livez` and `/readyz` exist thanks to `management.endpoint.health.probes.add-additional-paths=true`. Without additional paths enabled, use `/actuator/health/liveness` and `/actuator/health/readiness` on the actual port.

### Separate Management Port

When Actuator runs on a `management.server.port` different from the business port, the health endpoint on the management port can return 200 while the main web server fails to accept requests. Consider placing additional probe paths on the **main server port**; that tests closer to the real business traffic path.

However, even a probe on the main port only checks the group's conditions. No probe automatically guarantees all endpoints and all upstreams work unless they are checked.

### Why Not Put the Database into Liveness?

When multiple instances share one DB and the DB fails temporarily, if the liveness group includes the DB indicator, kubelet may restart every instance. Restarting does not fix the DB, and adds load during recovery. Only use liveness to detect unrecoverable internal faults.

### Should the DB Be Put into Readiness?

Depends on requirements:
- If every request strictly requires the DB with no fallback, putting the DB in readiness can make sense.
- If the system has a cache/circuit breaker that can still serve during DB errors, putting the DB in readiness can cause unnecessary traffic loss.
- If the DB is shared by all replicas, putting the DB in readiness means one DB outage can make **all replicas unready**. Accept and explicitly design for that consequence.

Do not run heavy DB checks on every HTTP probe; use sensible timeouts and intervals.

## 10. Shutdown and Moments When HTTP Cannot Reflect State

Spring Boot can transition readiness to `REFUSING_TRAFFIC` when preparing to stop. Yet once the HTTP server stops accepting connections, probes are no longer guaranteed to receive a 503 response. There is a difference between:

~~~text
ApplicationAvailability.readiness = REFUSING_TRAFFIC
~~~

and:

~~~text
curl /actuator/health/readiness always receives HTTP 503
~~~

The second statement is not true in every phase. When the JVM crashes, receives `SIGKILL`, loses power, or network drops, there is no HTTP path left to return a status.

Reference configuration for graceful shutdown on supported web servers:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Coordinate with termination grace periods and load balancer/Kubernetes draining. Health endpoints are a signal, not a complete replacement for mechanisms that stop accepting new requests.

## 11. Common Deployment Mistakes

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Have `ApplicationAvailability` yet `/readiness` 404 | Missing Actuator, probes not enabled outside Kubernetes, wrong port/path, or endpoint not exposed | Check dependencies, `management.endpoint.health.probes.enabled`, and web server |
| `ReadinessState` is `ACCEPTING_TRAFFIC` yet `/readiness` 503 | Added a DOWN health indicator to the group, or custom mapping | Check membership and each contributor's status |
| Global health 503 yet readiness 200 | Global and readiness groups select different members | Compare `/actuator/health` against group includes |
| Liveness 503 just because DB failed | Put external check in liveness | Remove external checks from liveness to avoid restart storms |
| Startup fails after adding group include | Misspelled contributor ID or bean not created | Verify bean names and group membership |
| `/readyz` 404 | Additional paths not enabled, wrong port | Check property and main server port |
| Probe 200 yet API still fails | Probe criteria omit critical business preconditions | Design health around real serving capability |
| Probe flapping 503/200 | Slow indicator, flaky dependency, overly sensitive timeout | Reduce check cost, tune thresholds and retries |
| Readiness refusing yet requests still arrive | LB/kubelet hasn't updated, in-flight requests, Service bypassed | Check routing and propagation |
| Actuator management port UP yet app main port unreachable | Two ports use separate HTTP paths | Consider additional paths on the main port |
| Shutdown does not return a final 503 response | HTTP server is closing or killed | Do not assume an HTTP response exists in every phase |
| Health details leak internal info | `show-details` configured too broadly | Hide details, restrict permissions and endpoint exposure |

### Ordered Debugging Procedure

1. Identify the **exact replica, timestamp, URL, and port**. Do not compare pod A's state with pod B's probe.
2. Check `ApplicationAvailability.getReadinessState()` and `getLivenessState()` on the instance being diagnosed.
3. Check group membership in configuration and identify each `HealthContributor` in readiness/liveness.
4. Determine whether the actual HTTP response came from Actuator or from an Ingress/Proxy. 404, 401, connection refused, and 503 are different error classes.
5. Check startup/shutdown phase: have runners finished? Has the Ready event fired? Is graceful shutdown in progress?
6. Inspect `StatusAggregator` and HTTP mappings if customized; do not assume every non-UP status maps to 503.
7. Audit timeouts, probe frequencies, and shared dependencies to avoid restart storms or traffic flapping.
8. Fix the readiness policy or dependency issue properly rather than forcing state to `ACCEPTING_TRAFFIC` to hide a DOWN contributor.

## 12. Self-Check Questions

**Q1:** If `ApplicationAvailability.getReadinessState()` is ACCEPTING, is the readiness health group guaranteed to be UP?

**A:** No. The group may include another contributor that is DOWN, making the overall status DOWN and HTTP 503.

**Q2:** If `/actuator/health` is DOWN, is the default readiness group necessarily DOWN?

**A:** No. Global health can include DB/disk checks, whereas default readiness focuses on `readinessState`.

**Q3:** Does changing a `HealthIndicator`'s result automatically publish an `AvailabilityChangeEvent`?

**A:** No. A standalone health contributor only changes its result when queried; availability events are a separate mechanism.

**Q4:** When does Boot typically publish `LivenessState.CORRECT` and `ReadinessState.ACCEPTING_TRAFFIC`?

**A:** After `ApplicationStartedEvent` comes liveness `CORRECT`; after runners and `ApplicationReadyEvent` comes readiness `ACCEPTING_TRAFFIC`.

**Q5:** Does a readiness failure restart the pod automatically?

**A:** No. Readiness mainly removes the pod from traffic; liveness failures are what cause kubelet to restart containers per probe config.

**Q6:** Why shouldn't `/actuator/health` be used as liveness for every application?

**A:** Global health may include external dependencies; a shared dependency failure would fail liveness, triggering mass restarts even though apps are internally healthy.

**Q7:** Can you always get HTTP 503 when readiness is `REFUSING_TRAFFIC`?

**A:** No. If the HTTP server is not running yet or has stopped, there is no response. While the endpoint is serving, `readinessState` mapping normally returns `OUT_OF_SERVICE`/503.

**Q8:** Can a health group choose which contributors participate?

**A:** Yes, through include/exclude configuration and the contributor registry. This is where probe policies beyond lifecycle state are configured.

**Q9:** Why can a slow health indicator make probes unstable?

**A:** HTTP responses must wait for the check; slow network I/O and timeouts can cause probe failures or resource exhaustion. Design lightweight checks with timeouts that reflect meaningful state.

**Q10:** How do you observe state and health group independently in the demo?

**A:** Use `/demo/state` to inspect `ApplicationAvailability` and `demoDependency`; use `/actuator/health/readiness` to inspect the health group. Turn off the dependency without publishing `AvailabilityChangeEvent` to see the difference.

## 13. Practice Exercises

**Exercise A — Separate the two state sources:** Run the section 8 demo. Record `/demo/state`, liveness HTTP, and readiness HTTP before/after `POST /demo/dependency/down`. Explain why availability did not change while the readiness group failed.

**Exercise B — Change readiness state:** Restore the dependency to UP, then `POST /demo/readiness/refuse`. Compare liveness and readiness health. Restore with `POST /demo/readiness/accept`.

**Exercise C — Remove the custom indicator from the group:** Remove `readiness.include`, restart, and repeat Exercise A. Compare global health against readiness. Describe the role of membership.

**Exercise D — Three-replica scenario:** Suppose three pods access one shared database. Compare outcomes when putting the DB in liveness, readiness, and global health only. Analyze restart storms, losing all endpoints, and having a cache fallback.

**Exercise E — Main port and management port:** Try setting `management.server.port=8081` and enabling additional paths. Verify `/readyz` on the main application port and `/actuator/health/readiness` on the management port. Explain why each check path has distinct value.

**Exercise F — Long-running runner:** Add a runner simulating a time-bounded startup task. Observe that while the runner executes, readiness stays refusing and only becomes accepting after Ready. Do not use simulated `sleep` as production logic.

## 14. Official Documentation and Key Takeaways

Spring Boot 3.5 documentation for contract verification:

- [Spring Boot 3.5 — Application Availability and Application Events](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html).
- [Spring Boot 3.5 — Actuator Health Groups and Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).
- [Spring Boot 3.5 — ApplicationAvailability Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html).
- [Spring Boot 3.5 — AvailabilityChangeEvent Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).
- [Spring Boot 3.5 — HealthIndicator Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).
- [Spring Boot 3.5 — Status Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/Status.html).

**Key Takeaways:**

1. `ApplicationAvailability` holds in-memory lifecycle signals, not the HTTP health endpoints themselves.
2. `AvailabilityChangeEvent` updates state; `HealthIndicator` can check separate conditions.
3. Liveness and readiness health groups select contributors strictly by configuration and do not include every external dependency by default.
4. Health groups aggregate `Status` and map to HTTP; `ACCEPTING_TRAFFIC` can coexist with a `DOWN`/503 readiness group if a custom indicator is `DOWN`.
5. Global health `DOWN` does not automatically imply readiness group `DOWN`, and vice versa.
6. A readiness failure signals not to receive traffic; a liveness failure normally signals a potential need for restart. Do not arbitrarily make liveness depend on DBs or external systems.
7. Before the web server starts or during shutdown, HTTP probes are not guaranteed to respond; internal state and endpoint availability are separate concerns.
8. Test group membership, HTTP mappers, shutdown, management/main ports, and Kubernetes timing before finalizing a readiness policy.
