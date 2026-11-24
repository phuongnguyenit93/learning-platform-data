# AvailabilityChangeEvent Transitioning Readiness State After ApplicationReadyEvent

**Module:** Spring Boot Application Runtime. **Group:** Application Events. This lesson focuses on the event sequence when an application transitions from startup to being ready to accept traffic: Spring Boot emits `ApplicationReadyEvent` once startup—including runners—has completed successfully; **afterward**, Boot publishes `AvailabilityChangeEvent<ReadinessState>` with value `ReadinessState.ACCEPTING_TRAFFIC`. The content uses **Java 17+ and Spring Boot 3.5.x** with Spring MVC, Actuator, and a reproducible example; detailed behavior should be verified against your target Spring Boot line.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the differences among `ApplicationReadyEvent`, `AvailabilityChangeEvent`, `ApplicationAvailability`, `ReadinessState`, and `LivenessState`.
2. Identify the exact order: **context refresh → started event → runners → ready event → readiness accepting traffic published** during normal startup.
3. Understand the meaning of the two readiness states `REFUSING_TRAFFIC` and `ACCEPTING_TRAFFIC`; distinguish readiness from liveness.
4. Read state via the `ApplicationAvailability.getReadinessState()` API and receive events via `@EventListener`.
5. Inspect `/actuator/health/readiness` / `/actuator/health/liveness`, interpreting `200 UP` and `503 OUT_OF_SERVICE` under default mapping.
6. Publish a controlled readiness event in a lab environment, then confirm values change both inside the JVM and on HTTP probes.
7. Design traffic acceptance properly in containers/orchestrators: health probes, startup probes, grace periods, shutdown, and the limits of relying only on logs.

**Key message:** `ApplicationReadyEvent` is a **startup event milestone**, whereas `ReadinessState.ACCEPTING_TRAFFIC` is the **readiness state published after that milestone**. Neither guarantees that every business request will succeed, all external connections are healthy, or Kubernetes has immediately started routing traffic.

## 2. Concepts to Distinguish

### 2.1. ApplicationReadyEvent

`org.springframework.boot.context.event.ApplicationReadyEvent` is emitted when `SpringApplication` finishes startup and `ApplicationRunner`/`CommandLineRunner` beans have completed. This event arrives late in startup. If a runner throws an exception, the application normally **does not** reach the ready milestone. Applications with multiple contexts or async listeners may show different details, yet the core contract remains that the ready event follows runners in a normal Boot flow.

A listener can be written as:

~~~java
@EventListener(ApplicationReadyEvent.class)
public void onReady() {
    System.out.println("LAB_APPLICATION_READY_EVENT");
}
~~~

This is a method snippet inside a Spring-managed bean, **not a standalone Java program**.

### 2.2. AvailabilityChangeEvent

`org.springframework.boot.availability.AvailabilityChangeEvent<S extends AvailabilityState>` is a Spring application event notifying that an availability state has changed. `getState()` returns the published state. Spring Boot uses this event to update `ApplicationAvailability` and let observers react.

For example, an event whose state type is `ReadinessState`. The event carries a **state value**, unlike a listener reading a property from a configuration file. The framework or application can publish a new event when conditions change; the new state becomes current through the event-handling mechanism.

### 2.3. ReadinessState

`org.springframework.boot.availability.ReadinessState` has two standard values:

| ReadinessState | Meaning | Recommended infrastructure action |
|---|---|---|
| `REFUSING_TRAFFIC` | The instance is not ready to accept additional traffic | Temporarily stop routing new requests to the instance |
| `ACCEPTING_TRAFFIC` | The instance signals it is ready to accept traffic | The instance may be included in traffic routing |

`REFUSING_TRAFFIC` does not mean the JVM is dead, does not mean the process must restart, and does not guarantee every endpoint on the HTTP port automatically returns 503. It is a **signal of ability to accept traffic**, typically translated into HTTP probe responses by Spring Boot Actuator.

### 2.4. LivenessState

`LivenessState.CORRECT` means the application is in a normal live state per internal signals; `BROKEN` is an unrecoverable state under liveness semantics. Crucial distinction:

- **Readiness fails:** pause routing traffic to the instance and wait for recovery or handling.
- **Liveness fails:** the orchestrator may restart the instance; therefore **do not** tie liveness to a shared database experiencing an outage, lest all replicas restart in a loop.
- `LivenessState.CORRECT` can coexist with `ReadinessState.REFUSING_TRAFFIC` — for example, while runners are still working or the app temporarily pauses traffic.

### 2.5. ApplicationAvailability

`ApplicationAvailability` is the interface for code to read an availability snapshot. Two convenient methods:

~~~java
ReadinessState readiness = availability.getReadinessState();
LivenessState liveness = availability.getLivenessState();
~~~

Applications should use events to **change** state rather than trying to mutate the implementation's internal state directly. `ApplicationAvailabilityBean` is Spring Boot's default implementation and tracks state-change events.

## 3. Exact Sequence of Startup and the Readiness Milestone

~~~text
main()
   |
   v
SpringApplication.run(args)
   |
   +-- Environment, ApplicationContext, bean definitions
   +-- ApplicationContext.refresh() completes
   |     +-- ContextRefreshedEvent
   |
   +-- ApplicationStartedEvent
   +-- AvailabilityChangeEvent<LivenessState.CORRECT>
   |
   +-- ApplicationRunner / CommandLineRunner executes
   |     +-- if still busy: readiness remains REFUSING_TRAFFIC
   |     +-- if failed: does not reach normal ready
   |
   +-- ApplicationReadyEvent
   |     +-- listeners receive ready milestone
   |
   +-- AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>
   |     +-- ApplicationAvailability updates
   |     +-- readiness health indicator returns UP
   |
   v
Instance ready to accept traffic
~~~

The diagram depicts the **successful startup flow** of Spring Boot 3.5. Listener execution order can depend on multicaster setup, yet the `ACCEPTING_TRAFFIC` readiness event emitted by Boot under the default lifecycle happens **after** `ApplicationReadyEvent`. Do not check readiness by assuming the value is already `ACCEPTING_TRAFFIC` **inside the `ApplicationReadyEvent` listener itself**: at that moment the default readiness-change event has not been published yet, so the snapshot may still be `REFUSING_TRAFFIC`.

Therefore:

- `ContextRefreshedEvent`: context refreshed; **not** the readiness milestone.
- `ApplicationStartedEvent`: refresh done, runners remain.
- `ApplicationReadyEvent`: runners finished; Boot emitted the ready milestone.
- `AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>`: post-ready readiness signal.
- Infrastructure probes/orchestrators: poll state with their own caches/intervals and may observe the change later than the JVM event.

## 4. Availability, HTTP Health Probes, and Traffic Routing Are Three Layers

**Layer 1 — JVM:** `ApplicationAvailability.getReadinessState()` is the process's state snapshot.

**Layer 2 — Spring Boot Actuator:** `ReadinessStateHealthIndicator` translates that state into a health status. Under typical config, `ACCEPTING_TRAFFIC` → `UP`, `REFUSING_TRAFFIC` → `OUT_OF_SERVICE`. Under default HTTP mapping, `UP` returns HTTP 200 and `OUT_OF_SERVICE` returns HTTP 503. Changing health groups or HTTP status mappings can change the result.

**Layer 3 — Infrastructure:** Kubernetes or a load balancer polls probes periodically and decides whether to route requests to the instance. There is **no** instantaneous synchronous link "event printed to log → load balancer routes traffic immediately."

Specifically, before the embedded web server opens its port, probes may **fail to connect**; an unready phase does not always return an HTTP 503. Once the web server is open yet readiness is not met, probes can return 503. During/after shutdown, the HTTP server may become unreachable even though a shutdown state was published earlier.

Table under the default flow:

| Phase | Liveness | Readiness | Assessment |
|---|---|---|---|
| Just starting | May not be live per probe yet | `REFUSING_TRAFFIC` | Do not use live traffic to test the app before startup |
| Context refreshed, runners unfinished | `CORRECT` | `REFUSING_TRAFFIC` | Process is alive yet should not accept traffic |
| After ready + readiness change | `CORRECT` | `ACCEPTING_TRAFFIC` | Instance has signaled readiness |
| Proactively shedding load | Usually `CORRECT` | `REFUSING_TRAFFIC` | Temporarily remove instance from routing |
| Graceful shutdown | May still be `CORRECT` | `REFUSING_TRAFFIC` | Stop sending new traffic, drain in-flight requests |
| Process exited | Gone | Gone | Probes can no longer connect |

## 5. Building a Java 17 / Spring Boot 3.5 Sample Application

### 5.1. Create the Project

Use Spring Initializr to create a Maven project:

- Group: `com.example`
- Artifact: `readiness-lab`
- Package: `com.example.readinesslab`
- Java: **17**
- Spring Boot: **3.5.x**
- Dependencies: **Spring Web**, **Spring Boot Actuator**
- Packaging: JAR.

Keep the `pom.xml` and Maven Wrapper generated by Initializr. Create this structure:

~~~text
readiness-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/readinesslab/
    ReadinessLabApplication.java
    ReadinessEventLogger.java
    ReadinessController.java
  src/main/resources/
    application.properties
~~~

The Java files below form a complete program **when placed together in the project with the Maven classpath**. Do not run `javac ReadinessLabApplication.java` standalone without Spring dependencies.

### 5.2. Main, Runner, and ApplicationReadyEvent Marker

File `src/main/java/com/example/readinesslab/ReadinessLabApplication.java`:

~~~java
package com.example.readinesslab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ReadinessLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessLabApplication.class, args);
    }

    @Bean
    ApplicationRunner startupRunner(
            @Value("${lab.runner.delay-ms:0}") long delayMillis) {
        return args -> {
            System.out.println("LAB_RUNNER_BEGIN");
            if (delayMillis > 0) {
                Thread.sleep(delayMillis);
            }
            System.out.println("LAB_RUNNER_DONE");
        };
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady(
            ApplicationReadyEvent event) {
        ApplicationAvailability availability =
                event.getApplicationContext()
                        .getBean(ApplicationAvailability.class);
        System.out.println("LAB_APPLICATION_READY_EVENT"
                + " currentReadiness="
                + availability.getReadinessState());
    }
}
~~~

**Explanation:** `ApplicationRunner` executes after refresh and before ready. `lab.runner.delay-ms` lets you intentionally slow down the runner in the lab without modifying code. `Thread.sleep(...)` here is solely for **observing startup phases**; production code should not arbitrarily block runners with sleep. If the runner throws an exception or stops, the app does not reach the normal ready milestone.

The `ApplicationReadyEvent` listener reads `ApplicationAvailability` to demonstrate that receiving the ready event and having state `ACCEPTING_TRAFFIC` are adjacent yet **distinct** points in time. Without custom publishers interfering, the value printed here is normally still `REFUSING_TRAFFIC`; immediately afterward Boot emits the accepting event.

### 5.3. Listener Receiving AvailabilityChangeEvent<ReadinessState>

File `src/main/java/com/example/readinesslab/ReadinessEventLogger.java`:

~~~java
package com.example.readinesslab;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessEventLogger {

    @EventListener
    public void onReadinessChanged(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println(
                "LAB_READINESS_EVENT=" + event.getState());
    }
}
~~~

Here, the `ReadinessState` type parameter narrows the listener to readiness events. Spring may emit other availability events for liveness; they are not targeted by this listener. When running, `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC` appears after `LAB_APPLICATION_READY_EVENT` under the default flow.

Do not use this marker as a guarantee that all lazy beans or external dependencies are healthy; it only confirms that the availability change was published.

### 5.4. Controller Reading and Publishing State Under Control

File `src/main/java/com/example/readinesslab/ReadinessController.java`:

~~~java
package com.example.readinesslab;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReadinessController {

    private final ApplicationAvailability availability;
    private final ApplicationContext context;

    public ReadinessController(
            ApplicationAvailability availability,
            ApplicationContext context) {
        this.availability = availability;
        this.context = context;
    }

    @GetMapping("/demo/status")
    public ReadinessStatus status() {
        return new ReadinessStatus(
                availability.getReadinessState().name(),
                availability.getLivenessState().name());
    }

    @PostMapping("/demo/refuse")
    public ReadinessStatus refuse() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        return status();
    }

    @PostMapping("/demo/accept")
    public ReadinessStatus accept() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
        return status();
    }

    public record ReadinessStatus(
            String readiness, String liveness) {
    }
}
~~~

This is an **illustrative lab**. `AvailabilityChangeEvent.publish(ApplicationContext, state)` is the official API for publishing the event. Under the default synchronous multicaster, `ApplicationAvailability`'s implementation updates from the event before the method returns a response; if an application switches event handling to async, re-verify immediacy when reading.

**Security:** the two POST endpoints that alter readiness must **exist only in learning/lab environments**, never deployed publicly without authentication/authorization. Anyone able to call them could affect instance routing. Never use an HTTP GET to mutate readiness, as GET should have read semantics.

### 5.5. application.properties and Health Probes

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=readiness-lab
server.address=127.0.0.1
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`management.endpoint.health.probes.enabled=true` enables liveness/readiness health groups even when not running inside Kubernetes. `health` is exposed over HTTP; `readiness` and `liveness` are groups of the health endpoint. `server.address=127.0.0.1` restricts listening to localhost so lab endpoints are not exposed to external networks in the sample config. In a real Kubernetes container, adjust binding for network reachability rather than copying the lab's loopback restriction.

## 6. Running and Verifying Results

### 6.1. Running the Application

On Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

In Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Keep the terminal running the application. The **relative** markers during a default startup:

~~~text
LAB_RUNNER_BEGIN
LAB_RUNNER_DONE
LAB_APPLICATION_READY_EVENT currentReadiness=REFUSING_TRAFFIC
LAB_READINESS_EVENT=ACCEPTING_TRAFFIC
~~~

Framework logs, PIDs, timestamps, and markers from other listeners may appear in between. The `currentReadiness=REFUSING_TRAFFIC` line belongs to default startup without an early custom publisher; it can differ if a library or other code publishes availability state itself.

**Why order matters:** Boot transitions standard state to `ACCEPTING_TRAFFIC` only after emitting `ApplicationReadyEvent`. Seeing the ready event while ignoring the readiness marker does not tell you the current state snapshot on its own.

### 6.2. Testing HTTP After Startup Completes

In a second terminal:

~~~bash
curl -i http://127.0.0.1:8080/demo/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

With a successful app and default probe mapping:

~~~json
{"readiness":"ACCEPTING_TRAFFIC","liveness":"CORRECT"}
~~~

The readiness probe returns a body equivalent to:

~~~json
{"status":"UP"}
~~~

The liveness probe also returns `{"status":"UP"}` in the normal lab; both are normally HTTP 200. Do not assert exact byte-for-byte response bodies because Spring/Jackson may add fields if health `show-details` or group settings change.

### 6.3. Proactively Switching to REFUSING_TRAFFIC

Call the test API:

~~~bash
curl -i -X POST http://127.0.0.1:8080/demo/refuse
curl -i http://127.0.0.1:8080/demo/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

Expected:

- Console prints `LAB_READINESS_EVENT=REFUSING_TRAFFIC`.
- `GET /demo/status` returns readiness `REFUSING_TRAFFIC` while liveness stays `CORRECT`.
- `GET /actuator/health/readiness` reports `{"status":"OUT_OF_SERVICE"}` and HTTP **503** under default mapping.
- `GET /actuator/health/liveness` still returns HTTP **200** with `{"status":"UP"}`.
- The HTTP endpoint `/demo/status` can still return **200** while readiness is `REFUSING_TRAFFIC`, because the state does not automatically install middleware blocking all requests. That is why infrastructure must read the readiness probe to avoid routing.

If endpoints are governed by security configs or custom health groups, status codes and accessibility may differ. The sample project omits Spring Security, so local paths work directly as above.

### 6.4. Switching Back to ACCEPTING_TRAFFIC

~~~bash
curl -i -X POST http://127.0.0.1:8080/demo/accept
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

Console prints `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC`; the readiness probe returns to HTTP 200 with `UP`. This is a **readiness event published after startup by user code**, not a new `ApplicationReadyEvent`. Boot does not need to refresh the context again to change readiness.

## 7. Observing the Window While Runners Have Not Finished

To clearly distinguish started from ready, build the JAR:

~~~bash
./mvnw clean package
java -jar target/readiness-lab-0.0.1-SNAPSHOT.jar --lab.runner.delay-ms=12000
~~~

The JAR name assumes version `0.0.1-SNAPSHOT`; use the actual file name in `target` if the version differs. On Windows use `./mvnw.cmd clean package`. Stop the previous app first so ports do not collide.

When you see `LAB_RUNNER_BEGIN` before `LAB_RUNNER_DONE`, call from another terminal:

~~~bash
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

During the window when the web server is already listening yet the runner is still running, readiness can be **`REFUSING_TRAFFIC`** with `OUT_OF_SERVICE`/503 while liveness is **`CORRECT`**/200. If you send requests too early, you may get "connection refused"; that is the difference between **port not open yet** and **readiness not achieved yet**, not a bug in the event.

After the runner finishes, wait for `LAB_APPLICATION_READY_EVENT` and then `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC` and re-check the readiness probe to see 200. Do not rely on a hardcoded `sleep 1` to assume an event fired; always observe the real markers and probes.

### 7.1. What If the Runner Fails?

In a separate test lab copy, replace the runner body with exception-throwing logic:

~~~java
@Bean
ApplicationRunner startupRunner() {
    return args -> {
        System.out.println("LAB_RUNNER_FAIL");
        throw new IllegalStateException("LAB_INTENTIONAL_FAILURE");
    };
}
~~~

**This is a method replacement snippet for the main class**, not a standalone Java file. When the runner throws an error, the default `ApplicationReadyEvent` and `ACCEPTING_TRAFFIC` readiness for that run usually **do not** occur. Boot reports a startup failure; analyze the `Caused by` chain in the stack trace rather than concluding the app is ready just because context refresh or a server log mentioned "started."

## 8. Readiness Is Not a Health Check of Every Dependency

Misconceptions to avoid:

1. `ACCEPTING_TRAFFIC` does not prove the database, Redis, broker, or upstream APIs are responding well. The state reflects the application's lifecycle/decision via event publishing.
2. By default, Spring Boot **does not automatically include all external health indicators** in the readiness probe; designers must choose which dependencies are strictly needed to serve requests.
3. A temporarily failing cache with a solid fallback should probably **not** be included in readiness, because pulling every replica out of routing can cause a wider outage.
4. A shared dependency like a database can mark every replica unready simultaneously; weigh circuit breakers, fallbacks, and readiness policies rather than pulling all instances blindly.
5. External dependencies should not go into **liveness**, because an external outage does not make the JVM unrecoverable; mass restarts often trigger cascades.

If readiness should reflect business health, you can add a `HealthIndicator` to the readiness health group or publish availability states from a state machine with a single clear owner. Avoid two independent components continuously publishing readiness and overwriting each other without a priority policy.

**Illustrative** config example once you have registered a `HealthIndicator` with ID `customCheck`:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,customCheck
~~~

Use this only when `customCheck` actually exists; it is not required for this lab. This property modifies the aggregated health group result and does not make other beans automatically emit `AvailabilityChangeEvent`.

## 9. Kubernetes readinessProbe, livenessProbe, and startupProbe

In Kubernetes, kubelet probes Pods using `readinessProbe` and `livenessProbe`. YAML **container config snippet**, not a full Deployment manifest:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24
~~~

Timeout/threshold numbers are illustrative and must be tuned from real measurements. `startupProbe` creates a protective window for slow-starting containers: while the startup probe has not succeeded, Kubernetes does not begin standard liveness/readiness evaluations, avoiding premature restarts when an app needs time. When readiness fails, Kubernetes removes the Pod from Service endpoints under normal routing rules; the JVM itself is not killed merely because readiness is false.

**Important:** the lab's `application.properties` sets `server.address=127.0.0.1` to keep demo APIs off the network. In real Kubernetes, containers must listen on an interface reachable by kubelet (usually omitting `server.address` or setting `0.0.0.0` per network architecture). Never ship unprotected POST endpoints that mutate readiness to production.

When using a separate management server port, readiness probes hitting only the management context might miss failures on the main port; Spring Boot supports exposing `/readyz` and `/livez` on the **main server port** via:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

When enabled, point probe paths to the right target. Do not guess which ports/paths work without verifying with `curl` inside a real container.

## 10. Shutdown: Returning to REFUSING_TRAFFIC

Spring Boot also updates availability when the application stops. With graceful shutdown, the goal is to signal **stop accepting new traffic**, allow in-flight requests time to finish, and then close the server/context. During that window:

- `ReadinessState.REFUSING_TRAFFIC` helps the orchestrator stop sending new requests to the instance.
- HTTP probes may become unreachable while the connector is shutting down; you will not always observe a clean 503.
- `server.shutdown=graceful` controls the web server's shutdown policy, whereas the readiness event conveys ability to accept traffic.
- `spring.lifecycle.timeout-per-shutdown-phase` governs the timeout of lifecycle shutdown phases; it does not replace Kubernetes's termination grace period.
- A forcibly killed JVM (e.g., `SIGKILL`) is not guaranteed to run callbacks or publish availability events.

Do not use `Runtime.getRuntime().halt(...)` or `kill -9` to "test graceful shutdown"; those bypass normal cleanup. In Kubernetes, coordinate `terminationGracePeriodSeconds` and endpoint propagation delays so new requests do not arrive at the Pod right after shutdown starts.

## 11. Common Errors and How to Diagnose Them

| Symptom | Cause to inspect | Verification step |
|---|---|---|
| `ApplicationReadyEvent` fired, yet listener sees old readiness | Boot emits accepting **after** ready | Print a separate `AvailabilityChangeEvent<ReadinessState>` marker |
| `GET /actuator/health/readiness` returns 404 | Missing Actuator, probes disabled, altered path/base-path, security | Check dependencies, `management.endpoint.health.probes.enabled`, exposure, routes |
| Probe returns 503, yet controller still returns 200 | Readiness does not automatically block requests | Check `/demo/status` and health readiness; configure router |
| Liveness 200, readiness 503 | Process is alive yet refusing traffic | Inspect runners, dependencies, latest events |
| Readiness stays REFUSING after startup | Runner unfinished, custom publisher set refuse, startup failed, or shutting down | Check ready/change markers, stack trace, poll state |
| Readiness switches to ACCEPTING before ready in logs | Other code/library published state or async logging | Check publishers, listener ordering, and version |
| Probe before ready gets "connection refused" | Web server not listening yet | Distinguish connectivity from HTTP status |
| K8s does not add Pod to endpoints even though JVM is accepting | Kubelet period, network path, wrong readinessProbe, security | Run `kubectl describe pod`, check events, curl probe URL from Pod |
| K8s restarts when shared DB fails | External health wired into liveness | Restrict liveness to internal recoverability |
| Probe is green yet business API fails | Health group does not cover business prerequisites | Run an end-to-end request, add intentional health indicators |
| Custom publisher overridden by another state | Multiple components publishing events | Identify readiness state-machine owner, log event sources |
| Testing web port separately from management port | Probe not checking the main listener port | Inspect `/readyz` and `/livez` on the main port |
| Lab POST did not change state as expected | Async event bus or another process serving that port | Check PID, markers, `getState` after event processing |

In logs, prefer facts you can cross-check: event names, states, PIDs, timestamps, ports, and probe HTTP statuses. Do not draw conclusions from the word "Started" alone, because Boot may still have runners, readiness events, or network conditions unconfirmed.

## 12. Experiment Matrix and Checklist

### Suggested Experiment Matrix

| Step | Command/trigger | Expected marker | Probe/response | Valid conclusion |
|---|---|---|---|---|
| Normal startup | `./mvnw spring-boot:run` | Ready event then readiness accepting | readiness UP/200 | State transitions after the ready milestone |
| Slow runner | `--lab.runner.delay-ms=12000` | Runner begin, not done yet | readiness refused/503 once server is open | Started does not mean ready |
| Proactive refuse | `POST /demo/refuse` | readiness refusing | readiness OUT_OF_SERVICE/503 | Readiness can change post-startup |
| Liveness preserved | After refuse | Liveness unchanged by readiness alone | liveness UP/200 | The two states are independent |
| Proactive accept | `POST /demo/accept` | readiness accepting | readiness UP/200 | No context refresh needed |
| Runner failure | Exception branch in test lab copy | No normal ready/accept | Probe may be unavailable | Startup failure differs from false readiness |
| Graceful stop | Valid Ctrl+C/SIGTERM | Shutdown logs/events depending on timing | Probe transitions fail/unavailable | Infrastructure stops routing during shutdown |

### Verification Checklist

- [ ] Distinguish `ApplicationReadyEvent` and `AvailabilityChangeEvent` as two distinct events.
- [ ] Explain the exact sequence `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`.
- [ ] State the meanings of `REFUSING_TRAFFIC` and `ACCEPTING_TRAFFIC`.
- [ ] Build the Java 17 and Spring Boot 3.5.x project with Spring Web + Actuator.
- [ ] Observe `LAB_APPLICATION_READY_EVENT` before `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC`.
- [ ] Use `ApplicationAvailability` to read readiness/liveness and receive availability events via a listener.
- [ ] Call `/actuator/health/readiness`, observing HTTP 200 and 503 across state transitions.
- [ ] Prove `REFUSING_TRAFFIC` does not mean the JVM died or HTTP controllers block requests themselves.
- [ ] Test a slow runner and distinguish an unopened port from readiness 503.
- [ ] Understand Kubernetes routing policies, startup/liveness/readiness probes, and main-port paths.
- [ ] Explain why a failing runner produces no ready event.
- [ ] Keep unprotected readiness-mutating endpoints out of production.

## 13. Official Documentation

- Spring Boot 3.5 — Application Events and Listeners: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Actuator endpoints, Kubernetes probes and Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5 — `AvailabilityChangeEvent` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.5 — `ApplicationAvailability` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.5 — `ReadinessState` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html

**Conclusion:** To confirm an app has completed the standard readiness milestone, observe both `ApplicationReadyEvent` **and** the subsequent `AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>`. To confirm the system is receiving traffic properly, also verify live probes, infrastructure routing policies, and business requests.