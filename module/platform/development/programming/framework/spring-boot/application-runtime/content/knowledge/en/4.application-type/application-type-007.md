# Distinguishing Server Startup Success from Full Application Readiness in Spring Boot

## 1. Two Easily Confused Milestones

In a Spring Boot application with an HTTP server, a message such as `Tomcat started on port 8080` indicates that **the embedded web server has started**. It **does not automatically prove that the entire application has finished starting up and is ready to receive business traffic**. After the server begins listening on the port, Spring Boot may still have to execute startup tasks, such as `ApplicationRunner` and `CommandLineRunner`, before declaring the application ready.

At least three questions must be distinguished:

1. **Has the server started?** Has the web server been initialized and started accepting connections on the expected port? This is the state of the HTTP transport component.
2. **Has the Spring ApplicationContext finished initializing?** Have the required configurations and beans for the context been loaded, processed, and refreshed successfully? This is a milestone in the Spring lifecycle.
3. **Is the application ready to receive business requests?** Have pre-serving initialization steps completed, and does the readiness check allow routing traffic? This is the operational state of the whole application.

The three questions are related yet not identical. An HTTP port responding does not prove reference data has finished loading, a background task is ready, or all external dependencies are working. Conversely, a `WebApplicationType.NONE` program can complete startup and be ready to perform work **without any HTTP server existing**.

> Practical rule: **"server started" is a signal that transport infrastructure is up; "application ready" is a signal that the application has passed the startup sequence per Spring Boot's contract**. True business readiness also depends on custom conditions the application has incorporated into its readiness mechanism.

## 2. Startup Progression: Order Matters

For a typical Servlet or Reactive Spring Boot application, the condensed sequence is:

~~~text
JVM calls main()
  |
  v
SpringApplication.run(...)
  |
  +-- Prepare Environment, profiles, configuration
  |
  +-- Create and refresh ApplicationContext
  |     |
  |     +-- Load beans, dependency injection, auto-configuration
  |     +-- Create embedded web server (if web application)
  |     +-- Web server started during refresh lifecycle
  |     +-- May publish WebServerInitializedEvent
  |
  +-- Log application "Started" (typically)
  +-- ApplicationStartedEvent
  +-- LivenessState = CORRECT
  |
  +-- Run ApplicationRunner / CommandLineRunner
  |     |
  |     +-- May still load cache, check resources,
  |         register initial data, or perform warm-up
  |
  +-- ApplicationReadyEvent
  +-- ReadinessState = ACCEPTING_TRAFFIC
  |
  v
Application completes startup sequence successfully
~~~

This is a high-level diagram: exact server initialization, logs, and callbacks may vary by version and application type. The core point is that **`ApplicationStartedEvent` occurs after the context has refreshed yet before runners**, whereas **`ApplicationReadyEvent` occurs after runners have been invoked and succeeded**. Spring Boot transitions readiness to `ACCEPTING_TRAFFIC` after `ApplicationReadyEvent`.

### 2.1. Signals That Cannot Substitute for Each Other

| Signal | What Does It Tell You? | What Does It Not Prove? |
| --- | --- | --- |
| Log `Tomcat started on port ...` or equivalent message | The web server is up for that specific implementation | Runners completed, readiness is open, or external networking routes properly |
| `WebServerInitializedEvent` | The web server attached to the Spring context has initialized and exposes info such as actual port | The entire application startup process has finished |
| Log `Started MyApplication in ... seconds` | Spring Boot reached the logging milestone after context refresh | Runners or post-refresh tasks have finished |
| `ApplicationStartedEvent` | Context refreshed successfully, before runners | The application is ready to receive traffic |
| `LivenessState.CORRECT` | Per internal liveness signal, the app is running and not considered unrecoverably broken | Readiness is open or downstream dependencies are healthy |
| `ApplicationReadyEvent` | Runners executed successfully; Boot is completing the startup phase | All business dependencies or asynchronous tasks are actually ready |
| `ReadinessState.ACCEPTING_TRAFFIC` | Spring Boot published the state indicating it can accept traffic | Any given HTTP request will succeed; external systems are routing correctly |

For example, if a `CommandLineRunner` runs for 10 seconds, the web server may already be listening on port 8080 during that window, while readiness remains `REFUSING_TRAFFIC`. Only after the runner succeeds does Boot complete the application ready milestone. If the runner throws an exception, startup fails even though the server may have opened its port earlier.

### 2.2. How Does "Listening on Port" Differ from "Ready"?

An application can be in the following states:

- **No server yet:** connecting to the port fails; may be starting up, startup failed, or the app is not a web app.
- **Server up, readiness not open yet:** endpoints may answer, yet the app should not receive business traffic from a load balancer; this is typically the window waiting for runners to finish.
- **Readiness open:** the readiness system permits receiving traffic, assuming that signal reflects all required serving conditions.
- **Application shutting down:** the server or context may not have stopped completely yet, while readiness should switch to refusing traffic so routers stop sending new requests.

**You cannot infer readiness solely from a TCP connect check** or by spotting one log line. An HTTP 200 from a custom endpoint also does not guarantee a properly designed readiness probe.

## 3. Liveness, Readiness, and Startup Probes

Spring Boot provides `ApplicationAvailability` to represent the application's availability state:

- **`LivenessState`**: `BROKEN` or `CORRECT`. Represents whether the process is still healthy enough to stay alive. In an orchestrator, the liveness probe typically determines whether to restart the container.
- **`ReadinessState`**: `REFUSING_TRAFFIC` or `ACCEPTING_TRAFFIC`. Indicates whether new traffic should be routed to the instance. An instance can be alive yet temporarily unready.
- **Startup probe**: this is a Kubernetes mechanism giving a process time to finish a long startup phase before applying liveness/readiness probes as configured. It is **not a third state of `ApplicationAvailability`**.

### Why Not Collapse Everything into One Probe?

Suppose an external database temporarily loses connectivity. The application may still be alive and able to recover when the database returns, while temporarily unable to handle database-dependent requests. Putting database failures into **liveness** can make Kubernetes repeatedly restart the entire pod and worsen the outage. That case usually belongs in **readiness**, if the application genuinely cannot serve without the database.

Conversely, if the application process itself enters a severe unrecoverable broken state, an unhealthy liveness probe can signal the orchestrator to restart it. Probe design must reflect actual recovery behavior, avoiding mechanical checks of external dependencies.

**Spring Boot Actuator** can expose endpoints for Kubernetes:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

To use these paths, the application needs the Actuator dependency and probe support enabled in environments where it is not auto-enabled (such as outside Kubernetes). For example in `application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

When probes are active, the default readiness indicator reflects `ReadinessState`. Refusing traffic is typically represented as `OUT_OF_SERVICE` (HTTP 503 under default mapping), while ready is `UP` (HTTP 200), **assuming no additional health indicator alters the aggregate status**. A healthy liveness probe can still return HTTP 200 while readiness returns HTTP 503.

Paths, endpoint accessibility, status aggregation, and HTTP codes depend on Actuator configuration, security config, and version. Do not confuse `/actuator/health` in general with `/actuator/health/readiness`: a general health endpoint returning 200 does not necessarily mean readiness.

### Is Default Readiness Enough for Business Requirements?

Not necessarily. The default state transition reflects **the startup lifecycle managed by Spring Boot**, especially runners. It **does not automatically know** whether a Kafka consumer has finished subscribing, an asynchronously populated cache is loaded, a token from an external service has been fetched, or a job must finish before traffic is routed.

If business logic needs special conditions, design initialization so mandatory steps complete before the app is considered ready, or add a reliable status check to the readiness health group. Do not put every external service into the health group reflexively: a non-essential dependency failing should not necessarily take the entire instance out of service.

## 4. Java 17+ Example: Server Up First, Application Ready Later

The following example **intentionally holds `ApplicationRunner` for 10 seconds** to observe state transitions. This is a runnable Spring Boot program for a matching Java 17+ project, not a startup-time optimization pattern for production.

Create a Maven project via [Spring Initializr](https://start.spring.io/) with group `com.example`, artifact `readiness-demo`, package `com.example.readinessdemo`, JDK 17 or newer compatible with Spring Boot, and two dependencies: **Spring Web** and **Spring Boot Actuator**. Use the included Maven Wrapper and create the structure:

~~~text
readiness-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/readinessdemo/
   │  ├─ ReadinessDemoApplication.java
   │  └─ DiagnosticController.java
   └─ resources/
      └─ application.properties
~~~

**File `src/main/java/com/example/readinessdemo/ReadinessDemoApplication.java`:**

~~~java
package com.example.readinessdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReadinessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner simulateCriticalInitialization(
            ApplicationAvailability availability) {

        return args -> {
            System.out.println("RUNNER_BEGIN=" + availability.getReadinessState());
            Thread.sleep(10_000L);
            System.out.println("RUNNER_END");
        };
    }
}
~~~

**File `src/main/java/com/example/readinessdemo/DiagnosticController.java`:**

~~~java
package com.example.readinessdemo;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    private final ApplicationAvailability availability;

    public DiagnosticController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/internal/readiness-state")
    public String readinessState() {
        return availability.getReadinessState().name();
    }
}
~~~

**File `src/main/resources/application.properties`:**

~~~properties
server.port=8080
management.endpoint.health.probes.enabled=true
~~~

In the project root directory, run the appropriate command:

~~~bash
# Linux / macOS
./mvnw spring-boot:run
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd spring-boot:run
~~~

During startup, the application prints two lines **produced by the runner itself** (aside from Spring Boot and web server logs):

~~~text
RUNNER_BEGIN=REFUSING_TRAFFIC
RUNNER_END
~~~

The first line prints after the context has refreshed yet before Boot publishes readiness. The second line appears when the simulated task finishes; right after that, Boot proceeds through `ApplicationReadyEvent` and updates readiness. Server logs may appear before those two lines; do not rely on the ordering of arbitrary log lines from different libraries to deduce a general ordering beyond defined lifecycle milestones.

**Test in another terminal while the application is inside the 10-second wait**:

~~~bash
curl -i http://localhost:8080/internal/readiness-state
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
~~~

On Windows, replace `curl` with `curl.exe` if needed to avoid PowerShell aliases depending on the environment.

Expected results **while the runner is executing**, if called before the wait finishes:

| URL | Typical Status | Meaning |
| --- | --- | --- |
| `/internal/readiness-state` | HTTP 200; body `REFUSING_TRAFFIC` | Endpoint only observes the enum value |
| `/actuator/health/readiness` | HTTP 503; JSON has `"status":"OUT_OF_SERVICE"` | Probe recommends not sending new traffic |
| `/actuator/health/liveness` | HTTP 200; JSON has `"status":"UP"` | Application can be alive even before ready |

**After the runner completes and Boot is ready**, test again:

~~~bash
curl -i http://localhost:8080/internal/readiness-state
curl -i http://localhost:8080/actuator/health/readiness
~~~

At that point the diagnostic endpoint typically returns `ACCEPTING_TRAFFIC`, while the readiness health endpoint returns HTTP 200 with `"status":"UP"`. Exact results depend on health group configuration and whether additional indicators exist. If you miss the intermediate state because your commands ran too slowly, increase `Thread.sleep` **only during experimentation**, then rerun; no change to Spring Boot's lifecycle is needed.

**Important note:** `/internal/readiness-state` in the example *always returns HTTP 200* because the controller simply returns a string. **Do not use that diagnostic endpoint as a Kubernetes readiness probe**. Use the Actuator endpoint that returns the proper HTTP status code matching health status, or build another operational endpoint with proper status logic.

### Why Does This Example Prove Two Distinct Milestones?

Once Spring refreshes the web context, the server can accept connections. The runner still sleeps for 10 seconds, so `ApplicationAvailability` continues returning `REFUSING_TRAFFIC`. Only after the runner succeeds does Spring Boot emit the application ready milestone and publish `ACCEPTING_TRAFFIC`. Thus, **the HTTP server can answer probe requests while the application is telling routers not to send business traffic yet**.

This test illustrates timing; it does not guarantee every HTTP request to the server succeeds before application ready: applications with filters, security, dependencies, or specialized workers may behave differently.

## 5. Distinguishing by Application Type

Spring Boot can infer or be configured with different application types. How you observe "server started" must be placed in that context.

| `WebApplicationType` | Typical Infrastructure | Is "Server started" Meaningful? | Is "Application ready" Meaningful? |
| --- | --- | --- | --- |
| `SERVLET` | Embedded Servlet container such as Tomcat or Jetty | Yes, if the app actually runs an HTTP server | Yes; after context refresh and runners |
| `REACTIVE` | Reactive web server such as Reactor Netty | Yes, even without a Tomcat log line | Yes; after context refresh and runners |
| `NONE` | CLI, batch, or app creating no web context | No default web server to observe | Yes, per Spring Boot lifecycle; process may exit once work finishes |

Application type selection relies on the classpath and/or explicit configuration, so **do not treat a missing Tomcat log as an error** in every scenario. Reactive apps typically do not use Tomcat; `NONE` apps do not need to open an HTTP port. On the other hand, a `SERVLET` app may have logged server started while readiness still refuses traffic until runners complete.

You can set the application type explicitly when genuinely needed:

~~~java
SpringApplication app = new SpringApplication(ReadinessDemoApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

The snippet above **only illustrates alternative configuration inside `main()`** (requiring `import org.springframework.boot.WebApplicationType;`); do not run it alongside `SpringApplication.run(...)` in the full example. When switching to `NONE`, the HTTP endpoints and `curl` tests above no longer apply.

## 6. Does ApplicationReadyEvent Mean All Background Work Is Done?

No. `ApplicationReadyEvent` means **synchronous runners have finished executing** and Boot has completed the startup phase. It does not wait indefinitely for every thread, future, or asynchronous task launched by the application itself.

Example design that creates a "false ready":

~~~java
@Bean
ApplicationRunner badInitialization() {
    return args -> {
        new Thread(() -> loadCriticalCache()).start();
        // Runner returns immediately, while the cache may not have finished loading.
    };
}
~~~

This is a **conceptual illustration snippet, not standalone compilable code**: `loadCriticalCache()` represents an undeclared business operation. It illustrates the problem: the runner returns immediately, so Boot can publish `ACCEPTING_TRAFFIC` even though mandatory data is still unready.

Better approaches depending on requirements:

1. If an initialization step is truly mandatory before any request, make the runner **wait until it completes** or fail in a controlled manner, and define an appropriate retry/fail-start policy.
2. If initialization must be asynchronous, create a dedicated readiness state tracked consistently and integrated into the readiness health group, so the probe does not report healthy until critical work finishes.
3. If only a subset of features needs that resource, consider readiness aligned with actual serving capability instead of unconditionally blocking the whole instance. Put that decision in the system contract rather than hiding it behind a "Started" log.

Spring Boot allows intentionally publishing state transitions via `AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC)` and `AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC)` when needed. However, **event ordering is critical**: Boot automatically publishes `ACCEPTING_TRAFFIC` after `ApplicationReadyEvent`, so publishing `REFUSING_TRAFFIC` too early during startup can be overwritten by the automatic transition. Do not tweak readiness just to make indicator lights look good; set it only when you have a mechanism that accurately determines traffic-handling conditions and flips state back once conditions change.

## 7. Applying in Containers, Kubernetes, and Load Balancers

In multi-instance environments, if a load balancer sends requests to a pod as soon as the HTTP port opens, requests can hit a window where the application is not ready yet. Orchestrators must rely on **readiness**, not on a "server started" log.

Kubernetes example (illustrating container probe config, to be placed in a valid Pod/Deployment):

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 0
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

The intervals above are **example values** and must be tuned to actual startup duration, resources, and operational needs. If startup is often very slow, consider a `startupProbe` so the liveness probe does not restart the process while it is still validly initializing. Probe configuration only works when the application exposes the endpoints, enables Actuator probes, and allows Kubernetes access.

Also understand the limits of probing mechanisms:

- **Kubernetes readiness:** a failing probe normally removes the pod from Service endpoints eligible for traffic; it does not by itself kill the process.
- **Kubernetes liveness:** failing probes beyond the threshold can trigger a container restart; poor conditions can cause a restart loop.
- **Graceful shutdown:** before or during termination, the system must stop routing new requests and let in-flight requests finish per policy. Readiness signals assist orchestration, while route propagation and connection draining also depend on infrastructure.
- **Separate management port:** if Actuator runs on a different management port from the application port, health endpoints might respond while the main HTTP server has issues. With Kubernetes, consider exposing probes on the main serving port; Spring Boot supports additional probe paths when configured appropriately.
- **Ingress and external networking:** even when Spring reports `ACCEPTING_TRAFFIC`, DNS, firewalls, TLS, ingress, service discovery, and networking can still block requests from reaching the app. Application readiness is one piece of end-to-end availability.

## 8. Observing and Diagnosing When the System Fails to Serve

When you see a "server started" log yet users receive errors, ask questions in a logical order:

| Symptom | Interpretation to Check | Verification Action |
| --- | --- | --- |
| Web server started log appears, yet readiness returns 503 | App may be running a runner, refusing traffic, or a health group indicator failed | Check runners, `ReadinessState`, health details, and post-startup logs |
| `Started ...` log appears, yet ready not reached | Context refresh milestone reached, yet runners haven't finished | Track `ApplicationReadyEvent` and `ApplicationRunner`/`CommandLineRunner` |
| Liveness 200, readiness 503 | Process is considered alive yet cannot receive requests yet | Inspect readiness conditions; avoid reflexive restarts |
| Readiness 200, yet API still returns 500 | Readiness doesn't measure that endpoint/dependency error, or failure happened after ready | Check request traces, error logs, business indicators, and specific dependencies |
| `curl localhost` works, yet external clients cannot connect | Difference in network bind, port mapping, proxy, ingress, TLS, or security | Test from outside the container, check routing and exposed ports |
| App with `WebApplicationType.NONE` opens no port | May be completely expected for CLI/batch | Check application type, exit code, runners, and logs |
| Port still appears to listen during shutdown | Graceful shutdown and traffic routing take time to converge | Verify readiness drops first, drain duration is adequate, and shutdown config |

**Key takeaway:** logs, TCP connect, HTTP 200, Spring availability, and business operation outcomes are different measurements. To confirm the system is ready to serve, define **which business conditions must hold**, then build probes reflecting those conditions. Readiness is not magic that infers every network or dependency failure.

### Observing via Lifecycle Events

When you need to measure precisely when Boot completes startup, use `ApplicationReadyEvent` or readiness health state instead of parsing a server log string. An example listener inside a Spring configuration class:

~~~java
@Bean
ApplicationListener<ApplicationReadyEvent> readyLogListener() {
    return event -> System.out.println("APPLICATION_READY_EVENT");
}
~~~

This is an **illustrative snippet requiring imports** for `org.springframework.context.ApplicationListener`, `org.springframework.boot.context.event.ApplicationReadyEvent`, and `org.springframework.context.annotation.Bean`. The listener is invoked when `ApplicationReadyEvent` is published; `ReadinessState.ACCEPTING_TRAFFIC` is published by Boot **after that event**, so avoid assuming this listener already observes readiness as ACCEPTING the moment it runs.

For startup timing or production observability, use metrics, tracing, health probes, and framework-defined events; do not depend on the relative positions of console log lines emitted by different libraries.

## 9. Common Misconceptions

1. **"Tomcat started = application ready."** False while runners or critical initialization conditions are still incomplete.
2. **"Started log = ApplicationReadyEvent."** False; the log milestone typically precedes runner completion.
3. **"Liveness UP = safe to send traffic."** False; the process may be alive while readiness is `REFUSING_TRAFFIC`.
4. **"HTTP 200 from any endpoint means readiness."** False; that endpoint may always return 200 even while business resources are unready.
5. **"Default readiness checks all databases, caches, and brokers."** False; you must understand each indicator, its conditions, and health group config.
6. **"An app without a Tomcat log failed to start."** False for Reactive or `NONE`.
7. **"Once a runner spawns a thread, initialization is done."** False if the thread continues running asynchronously.
8. **"Readiness 200 guarantees the entire Internet path succeeds."** False; the application and routing infrastructure have separate conditions.
9. **"Put temporarily disconnected dependencies into liveness to self-heal via restart."** Can trigger restart loops; analyze recoverability carefully before deciding.
10. **"Writing an ApplicationReadyEvent listener puts you in full control of readiness."** Insufficient; Boot automatically publishes readiness accepting right after the event and can overwrite signals emitted too early.

## 10. Review Questions and Exercises

**Question 1.** The HTTP server bound port 8080. An `ApplicationRunner` is still processing for 10 seconds. Should the application be considered ready?

**Answer:** Not yet under Spring Boot's default lifecycle readiness. The server can accept connections, yet `ReadinessState` remains `REFUSING_TRAFFIC` until runners succeed and Boot completes the ready step.

**Question 2.** At the same moment, `/actuator/health/liveness` returns 200 and `/actuator/health/readiness` returns 503. Is there a contradiction?

**Answer:** No. Liveness and readiness measure two different aspects: the application is alive yet not accepting traffic yet.

**Question 3.** Startup creates no web server, yet `ApplicationReadyEvent` still fires. Is that abnormal?

**Answer:** No. `WebApplicationType.NONE` still has a Spring Boot lifecycle and ready phase, even without an HTTP server.

**Question 4.** After ApplicationReadyEvent, a critical cache is still loading in the background; readiness returns 200. Where should this be fixed?

**Answer:** Determine whether the cache is mandatory for all requests. If mandatory, make initialization synchronous or integrate cache state into readiness; review state transition order and failure conditions. Merely renaming logs or checking the HTTP port further will not solve it.

**Hands-on exercise:** Run the example in section 4, observe health/readiness while the runner is executing, then measure again after the runner completes. Next, replace the sleep duration with a controlled data-preparation task; analyze what happens when the task fails. Discuss why an `ApplicationRunner` that spawns a background thread and returns immediately can cause the system to advertise readiness too early.

## 11. Takeaways to Apply

- **Server started:** milestone when the web server can open its port; not enough to speak for the entire application.
- **Application started:** context refreshed, Boot publishes `ApplicationStartedEvent`, before runners.
- **Application ready:** runners completed, Boot publishes `ApplicationReadyEvent`, then transitions `ReadinessState` to `ACCEPTING_TRAFFIC`.
- **Liveness:** whether the process is alive and recoverable. **Readiness:** whether new traffic should be routed to the instance.
- For Servlet/Reactive, use proper readiness probes rather than inferring from server logs. For `NONE`, do not apply HTTP server criteria to the application.
- For asynchronous business initialization, manage readiness state according to actual serving conditions.