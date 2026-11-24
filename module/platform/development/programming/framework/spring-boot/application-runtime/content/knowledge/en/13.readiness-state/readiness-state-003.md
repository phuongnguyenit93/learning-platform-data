# ReadinessState.ACCEPTING_TRAFFIC and REFUSING_TRAFFIC in Spring Boot

## 1. What Question Does Readiness Answer?

When operating a Spring Boot application, **whether the process is still alive** and **whether the process is ready to receive new requests** are two different properties.

For example, a service has initialized its Spring ApplicationContext yet is still loading mandatory lookup data, warming caches, or running startup runners. The JVM may be working properly, but if the load balancer sends business requests too early, those requests may fail. Conversely, when an instance is overloaded or preparing to shut down, the service may need to temporarily stop accepting new traffic even though internal processes are still running normally.

Spring Boot represents this decision using **ReadinessState** (package **org.springframework.boot.availability**). The enum has two values:

- **ReadinessState.ACCEPTING_TRAFFIC:** the application reports that it is **ready and willing to accept traffic**.
- **ReadinessState.REFUSING_TRAFFIC:** the application reports that it is **not yet ready or is actively refusing new traffic**.

This signal is useful for **container orchestrators**, **Kubernetes readinessProbe**, **load balancers**, and traffic-routing infrastructure. It does not guarantee business correctness on its own, does not replace comprehensive health checks, and **does not automatically sever HTTP connections** when switching to REFUSING_TRAFFIC.

**Core rule:** readiness is a declaration of **whether new requests should be routed to this instance right now**, not a command to terminate the process.

## 2. How Readiness Differs from Liveness

Spring Boot has two semantically independent availability groups:

| Property | Readiness | Liveness |
| --- | --- | --- |
| API | **ReadinessState** | **LivenessState** |
| Question | Should the instance receive new traffic? | Is the instance still in a state where it can keep operating/recover? |
| Values | **ACCEPTING_TRAFFIC**, **REFUSING_TRAFFIC** | **CORRECT**, **BROKEN** |
| When check fails in Kubernetes | Removes instance from ready endpoints for traffic routing | Kubelet may restart container after failure threshold is reached |
| Typical scenarios | Startup incomplete, temporary overload, preparing for shutdown | Deadlock/unrecoverable internal condition |
| When external DB temporarily fails | May lower readiness if DB is a mandatory dependency | Usually **do not** mark BROKEN solely because external DB failed |
| Goal | Keep service alive while preventing new work when unsuitable | Recover a process that can no longer operate properly |

An instance can simultaneously have **LivenessState.CORRECT** and **ReadinessState.REFUSING_TRAFFIC**. That is a valid state: the process is healthy, yet traffic should not be routed to it yet.

If a shared database failure is turned into a liveness failure across all replicas, Kubernetes may restart pods en masse, making the system more unstable. Including external dependencies in readiness must also be weighed carefully: when all replicas share one failing DB, the entire service could be pulled from routing; some applications can instead serve in degraded mode with a fallback.

## 3. Readiness Ordering in the Spring Boot Lifecycle

According to Spring Boot 3.5, on a successful startup, readiness transitions from not ready to accepting traffic **after startup runners finish**.

~~~text
SpringApplication.run(args)
        |
        v
Prepare Environment and ApplicationContext
        |
        v
Create beans, refresh context
        |
        +--> ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
        |
        +--> LivenessState.CORRECT
        |
        v
ApplicationRunner / CommandLineRunner
        |      Seed data, check configuration,
        |      mandatory warm-up...
        |      Readiness is still REFUSING_TRAFFIC
        |
        v
ApplicationReadyEvent
        |
        +--> AvailabilityChangeEvent(
        |      ReadinessState.ACCEPTING_TRAFFIC)
        |
        v
SpringApplication.run(...) returns
        |
        v
Application continues running
~~~

Key milestones:

1. **During starting:** readiness defaults to **REFUSING_TRAFFIC**. ApplicationContext and web server may not be ready yet.
2. **After ApplicationStartedEvent, while runners execute:** liveness is usually already **CORRECT**, yet readiness remains **REFUSING_TRAFFIC**.
3. **After all ApplicationRunner/CommandLineRunner finish normally:** Boot emits **ApplicationReadyEvent**.
4. **Immediately after ApplicationReadyEvent:** Boot publishes an availability event with **ReadinessState.ACCEPTING_TRAFFIC**.
5. **If a runner throws an unhandled exception:** startup fails; Boot does not complete the normal Ready sequence.
6. **During shutdown/graceful shutdown:** Spring Boot switches readiness to **REFUSING_TRAFFIC** while stopping new work, if configured and supported by the runtime for the corresponding shutdown steps.

**ApplicationReadyEvent** and publishing **ReadinessState.ACCEPTING_TRAFFIC** are not the same instruction: Spring Boot fires the availability event **immediately after** the ready event. Inside a listener handling ApplicationReadyEvent, do not assume the new availability state has already been published.

**Do not use @PostConstruct to conclude the app is ready.** @PostConstruct is only a single bean's initialization callback; many other beans or runners may still be unfinished.

## 4. What Effects Do the Two Readiness States Have?

### ACCEPTING_TRAFFIC

This state means the instance **wants to be considered ready to receive requests**. In the standard Kubernetes model, a passing readiness probe allows the instance to be added to the Service's ready endpoints per Kubernetes update mechanics.

This **does not guarantee**:

- Every external dependency is healthy.
- Every cache key already exists.
- All new traffic will arrive immediately.
- The system actually distributes requests evenly across every instance.
- Every request returns HTTP 200.

It is a signal for routing, not a business quality certification.

### REFUSING_TRAFFIC

This state means the instance **does not want to receive new traffic**. When the readiness probe reflects this state as unhealthy, infrastructure such as Kubernetes removes the instance from the ready endpoints group once the state is observed and processed.

Understand the limits clearly:

- **The HTTP listener usually stays open.** If called directly via the instance's IP/port, business requests may still be served depending on the application.
- **Does not kill or restart the JVM** just because readiness is false. That is not readiness semantics.
- **Does not close in-flight connections** via the state command; graceful shutdown has separate mechanisms for handling in-flight requests.
- Does not guarantee routing stops instantaneously; probe period, thresholds, controller/load balancer propagation, and connection reuse introduce lag.
- Without an orchestrator or readiness-aware proxy, changing the state may only alter internal state and the Actuator probe.

Therefore, the statement **"with REFUSING_TRAFFIC, every direct HTTP request returns 503" is false**. The 503 status in the example below comes from the **Actuator readiness endpoint** via health-status mapping, not middleware automatically blocking every business URL.

## 5. Commonly Used APIs

Spring Boot provides three main components:

| API | Role |
| --- | --- |
| **ReadinessState** | Enum describing the two traffic-accepting/refusing states |
| **ApplicationAvailability** | Reads current liveness/readiness from a Spring bean |
| **AvailabilityChangeEvent** | Event publishing an availability state change |

In an initialized Spring bean, you can inject:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;

public final class StateReader {
    private final ApplicationAvailability availability;

    public StateReader(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public ReadinessState currentReadiness() {
        return availability.getReadinessState();
    }
}
~~~

This is an **illustrative Java class**; create/inject it via Spring to run as a bean, not as a program with `main`. Calling **getReadinessState()** returns the state currently recorded by the availability component.

For code running very early before Spring Boot emits the first readiness event, the generic API **getState(ReadinessState.class)** can return **null** if no event has arrived yet; when a fallback value is needed, use:

~~~java
ReadinessState state = availability.getState(
        ReadinessState.class, ReadinessState.REFUSING_TRAFFIC);
~~~

This is a snippet placed in a method that has the **availability** variable. Do not treat `null` as implying the instance is already ready.

### Publishing a New State

Spring Boot 3.5 JavaDoc explicitly supports two overloads:

~~~java
// When ApplicationContext is available:
AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.REFUSING_TRAFFIC);

// When only ApplicationEventPublisher is available:
AvailabilityChangeEvent.publish(
        eventPublisher, this, ReadinessState.ACCEPTING_TRAFFIC);
~~~

These two snippets only illustrate method calls, not a complete program; `applicationContext` and `eventPublisher` must be injected/defined. **The second overload requires three parameters: publisher, source, state.** Do not mistakenly write `publish(eventPublisher, state)`.

With the default synchronous event multicaster, the availability-managing component receives the event and updates the state so the Actuator readiness indicator reflects it. If the application customizes asynchronous publish/listener mechanics, immediate state observation on the same thread must be re-tested.

## 6. Runnable Java 17+ Example: Changing Readiness and Inspecting the HTTP Probe

The example below creates a Spring Boot HTTP service with:

- **GET /demo/readiness:** view `ReadinessState` in `ApplicationAvailability`.
- **POST /demo/readiness/refuse:** publish `AvailabilityChangeEvent` with `REFUSING_TRAFFIC`.
- **POST /demo/readiness/accept:** publish `AvailabilityChangeEvent` with `ACCEPTING_TRAFFIC`.
- **GET /actuator/health/readiness:** real Actuator probe returning HTTP status based on readiness state.

The example uses **Spring Boot 3.5.x and Java 17+**. The POST endpoints are solely for testing on a development machine. **Do not deploy public readiness-control endpoints in production**; authentication/authorization and clear control logic are required.

### 6.1. Create the Project

Create a Maven project with Spring Initializr, group **com.example**, artifact **readiness-demo**, package **com.example.demo**, Java 17+, Spring Boot 3.5.x. Select:

- **Spring Web**
- **Spring Boot Actuator**

Core dependencies section in the POM generated by Initializr:

~~~xml
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
~~~

This is only the **dependencies section** of a complete POM, not a standalone `pom.xml`. Use the Spring Boot parent/BOM provided by Initializr to manage dependency versions.

### 6.2. Complete Java File

Create **src/main/java/com/example/demo/ReadinessDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessDemoApplication.class, args);
    }

    @RestController
    static class ReadinessController {
        private final ApplicationAvailability availability;
        private final ApplicationContext applicationContext;

        ReadinessController(
                ApplicationAvailability availability,
                ApplicationContext applicationContext) {
            this.availability = availability;
            this.applicationContext = applicationContext;
        }

        @GetMapping("/demo/readiness")
        public Map<String, String> getReadiness() {
            return Map.of(
                    "readiness",
                    availability.getReadinessState().name());
        }

        @PostMapping("/demo/readiness/refuse")
        public ResponseEntity<Void> refuseTraffic() {
            AvailabilityChangeEvent.publish(
                    applicationContext, ReadinessState.REFUSING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }

        @PostMapping("/demo/readiness/accept")
        public ResponseEntity<Void> acceptTraffic() {
            AvailabilityChangeEvent.publish(
                    applicationContext, ReadinessState.ACCEPTING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Why is this code appropriate?**

- **ApplicationAvailability** is a Boot-provided bean for reading the current availability state.
- **ApplicationContext** supports Boot 3.5's **AvailabilityChangeEvent.publish(ApplicationContext, state)** overload; this is the exact overload per JavaDoc.
- **ReadinessController** is a nested static class with **@RestController**, discovered by the application's component scan.
- The two POST endpoints only publish an **availability event**; they do not stop the HTTP server or change liveness state.
- **ResponseEntity.noContent().build()** returns HTTP 204 for the state-publishing action; do not try to interpret HTTP 204 as readiness status. The probe must be queried separately.

The code above is a **complete Java file** inside a project with matching dependencies. It cannot be compiled directly with `javac` without putting Spring Boot/Framework libraries on the classpath; Maven Wrapper handles this.

### 6.3. Enable the Actuator Readiness Probe

Create **src/main/resources/application.properties**:

~~~properties
server.port=8080

# Enable health probes even when running locally, outside Kubernetes.
management.endpoint.health.probes.enabled=true

# The health endpoint is the exposed HTTP endpoint.
management.endpoints.web.exposure.include=health

# Do not expose detailed health check info publicly.
management.endpoint.health.show-details=never
~~~

With this configuration and Spring Boot 3.5, Actuator provides health groups:

- **/actuator/health/liveness**
- **/actuator/health/readiness**

**management.endpoint.health.probes.enabled=true** is the key point so the demo has probes in a local environment. When Spring Boot detects a Kubernetes environment, probes are normally enabled automatically. There is no need to separate the management port for the demo; the endpoint runs on port **8080** alongside the application.

### 6.4. Run and Observe ACCEPTING_TRAFFIC

In the project root directory:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell or CMD:
# .\mvnw.cmd spring-boot:run
~~~

After the application starts successfully and the log reports ready, open a second terminal:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/demo/readiness
~~~

Expected results under the default configuration:

~~~text
GET /actuator/health/readiness
HTTP/1.1 200
{"status":"UP"}

GET /demo/readiness
HTTP/1.1 200
{"readiness":"ACCEPTING_TRAFFIC"}
~~~

This shows **condensed status and body** to focus on the content; actual curl output may show a specific HTTP version, additional headers, and different JSON formatting. What to check is **200/UP** on Actuator and **ACCEPTING_TRAFFIC** on the demo endpoint.

On Windows PowerShell, invoke **curl.exe** rather than Windows PowerShell's legacy **curl** alias; the commands above follow curl CLI syntax.

### 6.5. Switch to REFUSING_TRAFFIC

Send a POST request to the demo endpoint:

~~~bash
curl -i -X POST http://localhost:8080/demo/readiness/refuse
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/demo/readiness
~~~

With Spring Boot's default listener and default health-status mapping:

~~~text
POST /demo/readiness/refuse
HTTP/1.1 204

GET /actuator/health/readiness
HTTP/1.1 503
{"status":"OUT_OF_SERVICE"}

GET /demo/readiness
HTTP/1.1 200
{"readiness":"REFUSING_TRAFFIC"}
~~~

**Key learning points:**

- The readiness health group switches to **OUT_OF_SERVICE** and Actuator returns **HTTP 503** by default, signaling probe failure.
- **/demo/readiness** can still be called directly and returns HTTP 200. Readiness state **does not automatically block all controller endpoints**.
- Liveness can still be `CORRECT`; calling **GET /actuator/health/liveness** normally yields HTTP 200/UP while the app remains healthy.
- If a Kubernetes `readinessProbe` is present, kubelet observes the probe and updates the Pod Ready condition on its check schedule, not instantaneously just because a client called POST.

### 6.6. Switch Back to ACCEPTING_TRAFFIC

~~~bash
curl -i -X POST http://localhost:8080/demo/readiness/accept
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/demo/readiness
~~~

Expected output:

~~~text
POST /demo/readiness/accept
HTTP/1.1 204

GET /actuator/health/readiness
HTTP/1.1 200
{"status":"UP"}

GET /demo/readiness
HTTP/1.1 200
{"readiness":"ACCEPTING_TRAFFIC"}
~~~

Publishing `ACCEPTING_TRAFFIC` must be based on **business conditions and dependencies truly being ready**. In the demo, the control button is invoked via HTTP strictly for observation; production must never let an arbitrary request force an instance to report ready.

### 6.7. Limitations and Security Notes

- The POST endpoints are for **local demo** only; in real deployments, apply **authentication, authorization**, audit controls, rate limiting, and anti-flapping policies.
- On systems with Spring Security, endpoint behavior may differ; the curl illustrations assume **Spring Security is not installed**.
- Do not assume an exact order of HTTP headers, protocol version names, or logging.
- The Actuator health endpoint should expose only necessary data; **do not enable show-details=always** on public networks if it risks leaking infrastructure details.
- If the project uses a different management context/port, URLs and probe settings must be adjusted.

## 7. How Does Actuator Translate Readiness State into Health Status?

Spring Boot Actuator supports **ReadinessStateHealthIndicator** and the **readiness** health group. This group reads the readiness value from **ApplicationAvailability**.

Mapping under the default configuration:

| ReadinessState | Readiness Health Status | Readiness Probe HTTP Status |
| --- | --- | --- |
| **ACCEPTING_TRAFFIC** | **UP** | **200** |
| **REFUSING_TRAFFIC** | **OUT_OF_SERVICE** | **503** |

The HTTP column describes **Spring Boot's Actuator readiness probe with defaults**. Configuring custom status mappings or adding health indicators can alter the result. It does **not** say every URL in the application will return those same statuses.

### Health Root and Readiness Group Differ

**/actuator/health** is the overall health endpoint. **/actuator/health/readiness** is a health group. In a project with JDBC, messaging, or other HealthIndicators, root health may be DOWN due to one dependency, while the readiness group **does not necessarily include that dependency by default**.

If a custom indicator needs to be added:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,customCheck
~~~

This syntax is **illustrative**. For the configuration to work, a HealthIndicator with id **customCheck** must exist, matching your dependencies and Spring Boot version. Do not copy this property into the demo without creating `customCheck`; the readiness endpoint could encounter configuration errors or unexpected results.

When changing readiness logic, there are two options with distinct meanings:

- **Publish AvailabilityChangeEvent:** proactively change the application-managed willingness-to-accept-traffic state.
- **Add a custom HealthIndicator to the readiness group:** add a condition checked when the probe is called (for example, an essential internal dependency).

Do not add every health indicator to the readiness group just because it exists. A system can still serve usefully when an optional dependency is failing.

## 8. Kubernetes readinessProbe: Using Both States Properly

An example container configuration inside a Pod template:

~~~yaml
containers:
  - name: readiness-demo
    image: example/readiness-demo:1.0.0
    ports:
      - containerPort: 8080
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
~~~

The YAML snippet is a **PodSpec fragment**, not a complete Kubernetes manifest. Image, port, and thresholds must be tuned to the deployment environment. It assumes the application exposes Actuator health probes on main port 8080 and no security rules block kubelet.

**How Kubernetes handles it:**

1. Kubelet calls **/actuator/health/readiness** periodically.
2. When the probe passes sufficiently, the Pod gets the Ready status and can be selected as a serving endpoint for the Service.
3. When the probe fails, the Pod is deemed unready for new traffic routing after the failure threshold/observation window.
4. The container **is not restarted solely because the readiness probe fails**; liveness or other failure mechanisms normally govern restarts.
5. Once it transitions back to ACCEPTING_TRAFFIC and the probe passes, the Pod can be added back to the endpoints set.

**An important nuance:** if all replicas are REFUSING_TRAFFIC, the Service has no ready endpoints left. Clients may see connection errors, ingress errors, or 503 depending on how the load balancer/proxy is implemented. **Do not promise every client is guaranteed to receive 503** in this scenario.

### When the Management Port Differs from the Main Server Port

If Actuator runs on a separate port, the health probe can return UP even while the **main HTTP connector** is broken and not accepting requests. Spring Boot has an option:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

It exposes additional paths **/livez** and **/readyz** on the main server port by default, letting probes test HTTP infrastructure closer to the real request path. Exact behavior also depends on network policy, management endpoints, and Spring Boot version.

### Slow-Starting Applications

When loading large datasets or running long migrations, consider **startupProbe** if `livenessProbe` risks killing the container before the application reaches a valid startup milestone. `startupProbe` grants the process sufficient startup time under its own policy; readiness still controls routing.

Do not extend startup indefinitely just to reach ready. Set deadlines, error handling, and observe actual startup durations.

## 9. Proactively Switching to REFUSING_TRAFFIC on Runtime Degradation

Spring Boot manages state automatically during startup/shutdown. At runtime, the application can proactively emit a readiness event to refuse new traffic when an essential condition is not met.

An example method in a Spring-managed service:

~~~java
public void onRequiredCacheUnavailable() {
    AvailabilityChangeEvent.publish(
            applicationContext, ReadinessState.REFUSING_TRAFFIC);
}
~~~

This is an **illustrative code snippet**, assuming the service has `ApplicationContext` injected. Once the cache is repaired and consistency is verified, the service can publish `ACCEPTING_TRAFFIC` again.

However, real-world logic needs:

- **Condition to switch to refusing:** e.g., essential data cannot be read, an internal queue is overloaded, or the instance needs to drain.
- **Recovery condition:** re-verify dependency functionality and internal state stability.
- **Hysteresis/debounce:** avoid rapidly flipping between accepting and refusing on brief blips.
- **Backoff and retry:** controlled recovery without triggering a query storm against dependencies.
- **Observability:** metrics, structured logs, and tracing to investigate why state changed.
- **Multi-instance safety:** avoid having all replicas simultaneously set themselves to REFUSING if the system can still serve degraded.
- **Security:** only a trusted controller is permitted to alter state.

**ReadinessState is not persisted across restarts.** It is in-memory state of the running instance. On each startup, Spring Boot traverses a fresh sequence of availability states per its lifecycle.

## 10. Why Should You Not Control Readiness Too Early in ApplicationRunner?

A common pitfall:

~~~java
@Bean
ApplicationRunner launchWarmup(
        ApplicationContext context, Executor executor) {
    return args -> {
        executor.execute(this::warmUpSlowly);
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
    };
}
~~~

This is only an **illustrative pseudocode/Java snippet** (`warmUpSlowly` and the `Executor` bean are not declared). The runner spawns an async task and **returns immediately**. After all runners return, Spring Boot still executes its default sequence: **ApplicationReadyEvent**, followed by **ReadinessState.ACCEPTING_TRAFFIC**. Thus, the `REFUSING_TRAFFIC` state the runner just emitted can be **overwritten by the default startup event**, while warm-up is still unfinished!

**The right approach if warm-up is mandatory before ready:**

- Run warm-up synchronously in the runner, or **wait for CompletableFuture/Future completion with a timeout** before the runner returns.
- If warm-up fails and the application must not serve, throw an appropriate exception from the runner so startup fails clearly; do not force ACCEPTING.
- If async startup is mandatory yet must still control readiness, design a custom HealthIndicator/readiness gate reflecting progress or a post-ready mechanism to manage state, and test for races between events.
- If warm-up is purely a speed optimization, treat it as **best effort**, start accepting traffic, and use a fallback for cache misses.

A **finished ApplicationRunner** only proves that its `run` method returned, not that self-spawned async tasks have completed.

## 11. Readiness During Graceful Shutdown

Spring Boot supports graceful shutdown for supported web servers when enabled:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

This is a Spring Boot 3.5 configuration option; 30 seconds is an example and must match infrastructure policy. When the process receives a shutdown signal and begins closing the context:

1. Boot signals that the instance is entering a state refusing new traffic.
2. Kubernetes or a load balancer can pull the instance from routing based on readiness/probes.
3. Graceful shutdown finishes in-flight requests within server and configured timeout limits.
4. The context and HTTP connector are closed in order, and resources are released.

Externally observed ordering can differ because readiness probes run periodically and the HTTP server may close during shutdown. **Do not expect to always be able to query /actuator/health/readiness and see REFUSING_TRAFFIC during shutdown**.

State is not a fixed-duration request delay mechanism. If draining must be guaranteed, combine graceful shutdown, `terminationGracePeriodSeconds`, a `preStop` hook (when needed), application logic, and load balancer infrastructure.

## 12. Common Mistakes and Fixes

| Misconception / Mistake | Correct Explanation |
| --- | --- |
| **REFUSING_TRAFFIC will kill the application** | False; it expresses unwillingness to receive traffic, not liveness/restart |
| **Changing readiness closes socket 8080** | False; this is state for routing/probes |
| **ACCEPTING_TRAFFIC means every DB/API is healthy** | False; it only reflects readiness under current policy |
| **ApplicationStartedEvent means ready** | False; runners have not executed yet |
| **ApplicationReadyEvent and availability ACCEPTING are one event** | False; Boot publishes the readiness event right after the ready event |
| **Liveness DOWN on DB error is safe** | Can cause mass restarts; evaluate readiness/dependencies properly |
| **Actuator readiness includes every HealthIndicator by default** | No; the readiness group is tied to readiness state by default, depending on config |
| **Direct GET to a business endpoint must return 503 when refusing** | False; the Actuator readiness probe reflects the status; controllers may still run |
| **Publishing refusing in an async runner is enough** | No; the default ready event can overwrite state if the runner returns early |
| **Kubernetes pulls traffic instantaneously** | Probes, thresholds, endpoint updates, and proxy routing take time |
| **Publishing ACCEPTING yourself fixes startup errors** | No; state is just a signal; real dependencies still have to work |
| **Actuator always provides /actuator/health/readiness** | Requires Actuator dependency, health probes enabled, and matching path/port |
| **Using GET to change readiness** | Easily triggered by crawlers/caches/probes; state-changing actions should use POST and be secured |
| **Readiness and liveness have two states with the same meaning** | Both have two enum constants, yet their goals and infrastructure effects differ |

## 13. Real-World Scenarios for Deciding State

### Case A — Synchronous Startup Runner Executing

An instance is loading mandatory catalog data. Spring Boot has not fired `ApplicationReadyEvent` yet, and **REFUSING_TRAFFIC** remains appropriate. Do not manually publish ACCEPTING when the runner is only halfway done.

### Case B — Mandatory DB Connection Lost at Runtime

If every critical request requires the DB with no fallback, readiness may transition to `REFUSING_TRAFFIC` while the DB is unavailable. Yet if the DB is shared and every replica goes unready together, the entire service could be pulled from traffic; weigh this against returning controlled errors or degraded mode. Do not flip liveness to `BROKEN` solely for a temporary external DB outage.

### Case C — External Email System Failing, Main API Still Working

If email is secondary and already has queueing/retries, readiness can stay `ACCEPTING_TRAFFIC`. Marking an instance unready over a non-essential dependency outage can cause unnecessary disruption.

### Case D — Temporary Overload

An instance may temporarily set `REFUSING_TRAFFIC` to be pulled from routing, provided there are load thresholds, debounce, and self-recovery. Under heavy traffic, load shedding, concurrency limits, and circuit breakers may also be needed because readiness probes do not react instantaneously.

### Case E — Rolling Deployment and Graceful Shutdown

Old instances prepare to stop and announce they are refusing new work; new instances must pass readiness before receiving routed traffic. Combining a rolling update strategy with sufficient available replicas reduces downtime, though readiness alone does not guarantee zero downtime if all replicas are pulled or long-lived connections remain unhandled.

## 14. Self-Check Exercises

**Exercise 1.** An instance has **LivenessState.CORRECT** and **ReadinessState.REFUSING_TRAFFIC**. Is this a contradictory state?

**Exercise 2.** After `ApplicationStartedEvent`, a runner takes 20 seconds to seed the DB. What is the default readiness during that time? When the runner succeeds, which event occurs right before Boot reports accepting?

**Exercise 3.** While `REFUSING_TRAFFIC`, calling **GET /demo/readiness** directly in the example still returns HTTP 200. Why doesn't this contradict the HTTP 503 from **/actuator/health/readiness**?

**Exercise 4.** An application publishes `REFUSING_TRAFFIC` expecting Kubernetes to restart the pod. Is that expectation correct?

**Exercise 5.** Why shouldn't every external database check be put into `livenessProbe`?

**Exercise 6.** Inside a Runner, code submits a `Future` and returns immediately after publishing `REFUSING_TRAFFIC`. After the Runner, what can Boot do that prevents that state from staying intact?

**Exercise 7.** When you need to check readiness on the main port even though Actuator runs on a separate management port, which configuration can you use?

**Exercise 8.** If all replicas are `REFUSING_TRAFFIC`, is the client guaranteed to receive HTTP 503 from the application?

**Suggested Answers:**

1. No: the process is alive, just not accepting work yet.
2. `REFUSING_TRAFFIC`; **ApplicationReadyEvent** arrives after the runner, followed by availability `ACCEPTING_TRAFFIC`.
3. State does not block controllers automatically; the Actuator health group maps readiness to `OUT_OF_SERVICE`/503.
4. No: readiness controls routing; liveness is what typically triggers restarts.
5. Because a shared dependency outage easily triggers mass restarts and cascading failures.
6. Boot fires `ApplicationReadyEvent` and then `ACCEPTING_TRAFFIC`, which can overwrite the earlier refusing state.
7. **management.endpoint.health.probes.add-additional-paths=true**, then use `/readyz` on the main port under the default configuration.
8. No; the actual error may come from Service/Ingress/load balancer or even a failed connection.

## 15. Readiness Operational Checklist

- [ ] Clearly defined conditions for **accepting new traffic**.
- [ ] Distinguished **readiness** (routing) from **liveness** (restarting).
- [ ] Do runners finish mandatory work before ready instead of just submitting async tasks and returning?
- [ ] Enabled and verified the Actuator readiness probe appropriate for the environment?
- [ ] Is the probe hitting the right port/path and not blocked by security?
- [ ] No unauthenticated readiness-control endpoints exposed?
- [ ] Evaluated which external dependencies must genuinely fail readiness?
- [ ] Have retries, timeouts, hysteresis, and metrics to prevent state flapping?
- [ ] Not treating `REFUSING_TRAFFIC` as a command to close sockets or stop the JVM?
- [ ] Tested rollouts, restarts, dependency outages, and graceful shutdown in staging?
- [ ] Balanced probe period, failure thresholds, and connection-draining delay?
- [ ] Not tying readiness to every external service when the app can use fallbacks?

## 16. Summary and References

**ReadinessState.ACCEPTING_TRAFFIC** means the instance signals it can accept new requests. **ReadinessState.REFUSING_TRAFFIC** means the instance signals new requests should not be routed to it right now. Both states are managed by Spring Boot across its lifecycle and can be updated by the application via **AvailabilityChangeEvent**.

Quick-reference sequence:

~~~text
Startup / runner unfinished  -> REFUSING_TRAFFIC
ApplicationReadyEvent      -> Boot publishes ACCEPTING_TRAFFIC
Runtime temporarily unready-> REFUSING_TRAFFIC (when app changes proactively)
Runtime recovered          -> ACCEPTING_TRAFFIC (once verified)
Graceful shutdown          -> REFUSING_TRAFFIC
~~~

**Readiness is a coordination signal, not an automatic HTTP request blocker.** Use Actuator probes and an orchestrator/load balancer to enforce routing effects.

Official documentation aligned with Spring Boot 3.5:

1. Spring Boot — SpringApplication / Application Availability / startup events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot API — ReadinessState enum: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html
3. Spring Boot API — AvailabilityChangeEvent.publish overloads: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
4. Spring Boot API — ApplicationAvailability: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
5. Spring Boot Actuator — Endpoints / Kubernetes Probes / Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html

Examples use **Spring Boot 3.5.x, Spring Framework 6.x, and Java 17+**. If using Spring Boot 4.x or custom web management/security configuration, check the exact version's JavaDoc and application properties to avoid mismatched APIs, URLs, or HTTP status mappings.