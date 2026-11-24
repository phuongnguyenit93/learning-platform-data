# Distinguishing Publishing Readiness from Automatically Blocking Requests in Spring Boot

**Scope:** Spring Boot Application Runtime → Readiness State. This article explains the difference between **publishing readiness state**, **exposing readiness via health probes**, **infrastructure traffic-routing decisions**, and **rejecting an HTTP request inside the application itself**. The goal is to avoid the misconception that merely emitting `AvailabilityChangeEvent<ReadinessState.REFUSING_TRAFFIC>` causes every controller, socket, or direct request to automatically return 503.

Hands-on examples use **Java 17+**, **Spring Boot 3.5.x**, **Spring MVC**, and **Spring Boot Actuator**. APIs, probe settings, and connector behavior must be checked against the exact version's documentation when applied to another Spring Boot version. Test tasks run strictly on localhost and make no real business changes.

## 1. Foundational Conclusion

**Publishing readiness is a state signal, not an HTTP filter applied across every endpoint.**

When an application is running and code explicitly calls:

~~~java
AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.REFUSING_TRAFFIC);
~~~

Spring Boot updates `ApplicationAvailability`; the readiness health indicator is used by Actuator to reflect this state. With default HTTP mapping, `/actuator/health/readiness` switches to `OUT_OF_SERVICE` and typically returns **503**.

However, if a client **directly calls** a business endpoint still served by the web server and the application has no filter/gateway blocking requests, that controller **can still process the request and return 200**. In other words:

- **Readiness state**: the application says "I should not receive more traffic".
- **Readiness probe**: an operational endpoint reporting that condition to monitoring or orchestrators.
- **Router/load balancer/Kubernetes Service**: infrastructure **may** stop sending new requests to the instance after observing a failing probe.
- **Application-level gate**: a filter/interceptor or custom logic configured by the developer can **proactively reject requests** right inside the JVM.
- **Web server shutdown**: an actual graceful shutdown can close/transition the HTTP connector and handle requests per stop policy; that is **different** from merely publishing a readiness event while the server is running normally.

The last two behaviors do not materialize automatically just because a piece of code published `REFUSING_TRAFFIC` mid-runtime. Distinguishing them helps you design readiness, Kubernetes operations, and overload behavior accurately.

## 2. Four Layers to Understand Independently

~~~text
                 Spring Boot process (JVM)
                 +--------------------------------------+
                 | Business controller /lab/process     |
                 |                                      |
                 | ApplicationAvailability              |
                 |   ReadinessState                     |
                 |    ACCEPTING_TRAFFIC / REFUSING ...  |
                 |                |                     |
                 |     ReadinessStateHealthIndicator     |
                 |                |                     |
                 | /actuator/health/readiness            |
                 +----------------|---------------------+
                                  |
                           kubelet/LB probes
                                  |
                            routing decision
                                  |
                    normal client -> Service / LB
                                  |
                       selected application pod

Direct client -> pod IP:port -> controller
   (may still get through if network, web connector, and application permit)
~~~

**Layer 1 — State inside the JVM:** `ApplicationAvailability.getReadinessState()` reports the current readiness snapshot Spring Boot is tracking. It is not a socket firewall.

**Layer 2 — Probe:** `/actuator/health/readiness` exposes state via the health group; the body is typically `{"status":"UP"}` for `ACCEPTING_TRAFFIC` and `{"status":"OUT_OF_SERVICE"}` for `REFUSING_TRAFFIC`. HTTP 200/503 is the **health endpoint's** mapping, not an automatic mapping for every controller.

**Layer 3 — Infrastructure:** kubelet or a load balancer polls probes periodically and updates routing conditions. This incurs lag and depends on networking, service mesh, endpoints, and connection reuse. A client hitting a Pod IP or server port directly can bypass the Service/LB and still succeed.

**Layer 4 — Application-level rejection:** for the application to return 503 on a specific request, you must **explicitly check readiness and set the HTTP status** in a Servlet Filter, WebFlux WebFilter, gateway, or route handler design. The filter must have clear policies for exempted endpoints, in-flight requests, races between state transitions and incoming requests, and the risk of accidentally blocking health/control endpoints.

## 3. ReadinessState, AvailabilityChangeEvent, and ApplicationAvailability

### 3.1. Two Readiness States

Spring Boot provides `org.springframework.boot.availability.ReadinessState` with two values:

| ReadinessState | Meaning | Used to Decide |
|---|---|---|
| `ACCEPTING_TRAFFIC` | Application is ready to receive traffic | Infrastructure may select the instance for routing |
| `REFUSING_TRAFFIC` | Application currently does not want more traffic | Infrastructure should temporarily stop routing new requests |

`REFUSING_TRAFFIC` does not mean the JVM is dead, the web connector is closed, or every HTTP request must return 503. Nor does it mean the app needs a restart. It is a signal that can change as the application exits overload, warm-up, or maintenance.

### 3.2. Publishing Events

To request a state transition:

~~~java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
~~~

and to switch back:

~~~java
AvailabilityChangeEvent.publish(
        context, ReadinessState.ACCEPTING_TRAFFIC);
~~~

Both are **snippets** placed inside a Spring-managed component that already holds `ApplicationContext context`; not standalone Java programs. `AvailabilityChangeEvent.publish(...)` dispatches the event to listeners. The default `ApplicationAvailability` implementation observes the event and lets code read the latest state.

With the default event multicaster (synchronous for most regular listeners), the state callback runs on the publishing thread. If a project customizes async multicasting or special listeners, do not treat immediate read-after-publish visibility as a system-wide guarantee without testing.

### 3.3. Reading State

~~~java
ReadinessState state = availability.getReadinessState();
boolean ready = state == ReadinessState.ACCEPTING_TRAFFIC;
~~~

This snippet assumes the bean has `ApplicationAvailability availability` injected. There is no need—and you should not—reach into internal fields of `ApplicationAvailabilityBean` to mutate state; use events.

**Readiness differs from liveness:**

- `LivenessState.CORRECT`: the process can keep operating/recovering under the internal liveness definition.
- `LivenessState.BROKEN`: internal state has a problem that cannot recover normally; infrastructure may restart it.
- `ReadinessState.REFUSING_TRAFFIC` and `LivenessState.CORRECT` **can coexist**. For instance, an instance is alive yet temporarily pausing new traffic.

Do not mechanically wire shared database or upstream API health into liveness; a shared outage causes multiple replicas to restart together and trigger a cascading failure.

## 4. When Boot Automatically Changes Readiness in Startup/Shutdown

In Spring Boot 3.5's successful startup flow:

~~~text
SpringApplication.run(...)
    |
    +-- refresh ApplicationContext
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT published
    +-- ApplicationRunner / CommandLineRunner complete
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC published
    |
    v
application is ready per Boot lifecycle
~~~

Boot starts in an unready state (`REFUSING_TRAFFIC`) until the milestone where traffic can be accepted. When stopping the application, readiness can also revert to `REFUSING_TRAFFIC`, and the HTTP connector is governed by the **actual shutdown lifecycle**, not merely the availability event.

**Distinguish two critical contexts:**

1. **Startup/shutdown lifecycle:** Spring Boot documentation describes HTTP server states corresponding to each phase; during startup runners or graceful shutdown, the server may not yet accept requests or may reject new ones due to the connector/lifecycle.
2. **Running normally, self-publishing `REFUSING_TRAFFIC`:** The context and embedded server remain active. Publishing state **does not automatically ask the servlet container to stop/close ports, nor insert a `Filter` into the request chain**. Hence you need probes/routing or a separate filter if you want to block requests.

Do not use examples of the server stopping new connections **during actual shutdown** to infer that a standalone `AvailabilityChangeEvent` also closes the web server. This is the exact boundary of this topic.

## 5. Behavior Matrix While the Application Is Running

Assume startup finished, the server listens on port 8080, there is no blocking filter, Actuator health probes are enabled, and default HTTP status mappings apply:

| Scenario | `ApplicationAvailability` | `GET /actuator/health/readiness` | Direct `POST /lab/process` |
|---|---|---|---|
| Just became ready | `ACCEPTING_TRAFFIC` | HTTP 200, `UP` | HTTP 200 |
| Publish `REFUSING_TRAFFIC` | `REFUSING_TRAFFIC` | HTTP 503, `OUT_OF_SERVICE` | **Can still return HTTP 200** |
| Re-publish `ACCEPTING_TRAFFIC` | `ACCEPTING_TRAFFIC` | HTTP 200, `UP` | HTTP 200 |
| Refusing + custom gate filter | `REFUSING_TRAFFIC` | HTTP 503 | **HTTP 503 from filter** |
| Web server actually stopping | Typically refuses traffic | May be 503 or unreachable | May be 503/unreachable; depends on server and timing |

The table reflects **expected lab results**, not a promise that external cluster networks or all embedded servers behave identically during shutdown. If health groups/status mappings are customized, probe HTTP codes may differ; if business endpoints have authentication/authorization or custom error logic, responses can also differ from 200.

A 503 readiness probe **does not** force business controllers to return 503. A 200 HTTP controller **does not** prove the instance is ready to be placed into Service traffic routing.

## 6. Sample Application: Seeing Readiness 503 While Business Logic Still Executes

### 6.1. Prepare the Project

Create a Maven project in **Spring Initializr**:

- Group: `com.example`
- Artifact: `readiness-gate-lab`
- Package: `com.example.readinessgate`
- Java: **17**
- Spring Boot: **3.5.x**
- Dependencies: **Spring Web**, **Spring Boot Actuator**
- Packaging: **Jar**.

Keep `pom.xml`, `mvnw`, and plugin versions from Initializr. Create the structure:

~~~text
readiness-gate-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/readinessgate/
    ReadinessGateApplication.java
    LabController.java
    ReadinessTrace.java
    OptionalReadinessGateFilter.java
  src/main/resources/
    application.properties
~~~

Place each class in a separate file matching its public class name. All this code compiles inside a Maven project with Spring Web/Actuator; do not run `javac` on individual files without Spring on the classpath.

### 6.2. Main: Print Ready Milestone

File `src/main/java/com/example/readinessgate/ReadinessGateApplication.java`:

~~~java
package com.example.readinessgate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ReadinessGateApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessGateApplication.class, args);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady(ApplicationReadyEvent event) {
        ApplicationAvailability availability =
                event.getApplicationContext()
                        .getBean(ApplicationAvailability.class);

        System.out.println(
                "LAB_APPLICATION_READY_EVENT readiness="
                        + availability.getReadinessState());
    }
}
~~~

In the normal Boot lifecycle, `ApplicationReadyEvent` is emitted **before** the event transitioning to `ACCEPTING_TRAFFIC`. Without another custom publisher, when the ready listener executes, the value may still be `REFUSING_TRAFFIC`; do not infer from the event name "Ready" that the readiness field flipped immediately when the callback began.

### 6.3. Controller: Business Endpoint, Reading State, Changing State

File `src/main/java/com/example/readinessgate/LabController.java`:

~~~java
package com.example.readinessgate;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {

    private final ApplicationAvailability availability;
    private final ApplicationContext context;
    private final AtomicLong processed = new AtomicLong();

    public LabController(
            ApplicationAvailability availability,
            ApplicationContext context) {
        this.availability = availability;
        this.context = context;
    }

    @GetMapping("/lab/status")
    public Status status() {
        return new Status(
                availability.getReadinessState().name(),
                availability.getLivenessState().name(),
                processed.get());
    }

    @PostMapping("/lab/process")
    public ProcessResult process() {
        long number = processed.incrementAndGet();
        System.out.println("LAB_PROCESS_ACCEPTED count=" + number);

        return new ProcessResult("processed", number);
    }

    @PostMapping("/lab/control/refuse")
    public Status refuse() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        return status();
    }

    @PostMapping("/lab/control/accept")
    public Status accept() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
        return status();
    }

    public record Status(
            String readiness, String liveness, long processed) {
    }

    public record ProcessResult(String outcome, long processed) {
    }
}
~~~

**Illustrative design:**

- `GET /lab/status` **reads** readiness/liveness and processed count; GET itself does not update the counter.
- `POST /lab/process` represents a business request and **increments an in-memory counter**. Without a filter, this method **never checks readiness**, so it can still execute while state is refusing.
- `POST /lab/control/refuse` and `/accept` publish `AvailabilityChangeEvent` with the desired state; these endpoints are strictly for lab testing.
- `AtomicLong` is an observation counter, not a real transaction or business data.
- Control endpoints must be **removed or strongly secured** in production—for example bound to localhost—to prevent external callers from arbitrarily altering readiness.

### 6.4. Listener Receiving Readiness Events

File `src/main/java/com/example/readinessgate/ReadinessTrace.java`:

~~~java
package com.example.readinessgate;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessTrace {

    @EventListener
    public void onState(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("LAB_READINESS_CHANGED=" + event.getState());
    }
}
~~~

The log `LAB_READINESS_CHANGED=REFUSING_TRAFFIC` confirms the state event was received, **not** that a request-blocking filter was activated. We will compare it against the response from `POST /lab/process`.

### 6.5. Optional Filter: Enabled Only in the Control Scenario

File `src/main/java/com/example/readinessgate/OptionalReadinessGateFilter.java`:

~~~java
package com.example.readinessgate;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@ConditionalOnProperty(
        name = "lab.gate.enabled",
        havingValue = "true")
public class OptionalReadinessGateFilter extends OncePerRequestFilter {

    private final ApplicationAvailability availability;

    public OptionalReadinessGateFilter(
            ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();

        return path.startsWith("/actuator/")
                || path.equals("/lab/status")
                || path.startsWith("/lab/control/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        if (availability.getReadinessState()
                != ReadinessState.ACCEPTING_TRAFFIC) {
            response.setStatus(HttpServletResponse.SC_SERVICE_UNAVAILABLE);
            response.setContentType("application/json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write(
                    "{\"error\":\"not_ready\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

**Verifiable mechanism:** by default `lab.gate.enabled=false`, so Spring does not instantiate this filter. When run with `--lab.gate.enabled=true`, the filter bean is registered in the servlet filter chain. It explicitly **reads readiness state** and returns 503 for requests not in the exemption list. That is **logic we wrote ourselves**, not an automatic effect of `AvailabilityChangeEvent`.

`/actuator/` and `/lab/control/` are exempted so probes can still be queried and state can be flipped back; `/lab/status` is exempted so the counter remains observable during tests. In real applications, the exemption list must be reviewed carefully: it may need health, metrics, auth, admin, or other draining-related APIs. This is a simple learning filter, not a complete security, DDoS protection, admission control, or maintenance policy solution.

**Technical limitation:** the filter checks the snapshot when the request passes through; a request that already passed the filter before a refusing event occurs is **not automatically canceled**. Concurrent requests may observe different states across the transition boundary. For streaming, async requests, WebFlux, and service meshes, implementation differs; do not use servlet-stack `OncePerRequestFilter` for pure WebFlux.

### 6.6. Application Configuration

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=readiness-gate-lab
server.address=127.0.0.1
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
lab.gate.enabled=false
~~~

`management.endpoint.health.probes.enabled=true` ensures readiness/liveness health groups are created even outside Kubernetes. `health` is exposed over HTTP; liveness and readiness are health groups under the health endpoint. `server.address=127.0.0.1` is strictly for safe local labbing on a personal machine; if deploying in containers where kubelet must probe over the network, do not keep a loopback bind address without checking network architecture.

Spring Security is not added to the sample project, so local curl examples require no token. In production, define explicit authentication/authorization for control endpoints and admin functions.

## 7. Experiment A — Readiness Refusing Yet Business Endpoint Still Returns 200

### 7.1. Run the Application

On Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

If port 8080 is already used by another service, stop that service or change `server.port` and use the new port. In the example, the relevant markers are:

~~~text
LAB_APPLICATION_READY_EVENT readiness=REFUSING_TRAFFIC
LAB_READINESS_CHANGED=ACCEPTING_TRAFFIC
~~~

This illustrates the default startup ordering **with no other custom publishers**. Framework logs may interleave; Spring Boot-managed liveness/readiness may emit extra markers on shutdown.

In a second terminal, check initial state:

~~~bash
curl -i http://127.0.0.1:8080/lab/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

Expected after startup:

~~~json
{"readiness":"ACCEPTING_TRAFFIC","liveness":"CORRECT","processed":0}
~~~

Both probes normally return HTTP 200 and body `{"status":"UP"}` while the lab app is healthy. If groups, auth, or HTTP mappings differ, results may vary; the lab relies on the configuration above.

### 7.2. Call Business Endpoint While State Is Accepting

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/process
~~~

Expect HTTP 200 with JSON:

~~~json
{"outcome":"processed","processed":1}
~~~

The controller prints `LAB_PROCESS_ACCEPTED count=1`. This reflects a freshly started JVM with no prior process calls.

### 7.3. Publish Readiness Refusing

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/control/refuse
curl -i http://127.0.0.1:8080/lab/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

Expected:

- Listener prints `LAB_READINESS_CHANGED=REFUSING_TRAFFIC`.
- `/lab/status` returns `"readiness":"REFUSING_TRAFFIC"` while liveness remains `CORRECT`.
- `/actuator/health/readiness` returns HTTP 503 and body equivalent to `{"status":"OUT_OF_SERVICE"}` under default config/mapping.

Now **do not enable the gate filter**. Call the business endpoint directly:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/process
curl -i http://127.0.0.1:8080/lab/status
~~~

Expected result for the second POST:

~~~json
{"outcome":"processed","processed":2}
~~~

`/lab/status` confirms the counter reached 2 even though readiness is still `REFUSING_TRAFFIC`. This is **direct, decisive proof**: publishing a readiness event only updates availability/probes in the lab, and **does not automatically block business requests** arriving directly at an active servlet server.

**Technical note:** If a client goes through a Kubernetes Service that already removed the Pod from endpoints, requests may not reach the Pod. Yet that is due to infrastructure routing, not because Spring's default controllers/Filters return 503 for every endpoint.

### 7.4. Restore State

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/control/accept
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

The marker returns to `LAB_READINESS_CHANGED=ACCEPTING_TRAFFIC`, and the probe normally returns 200 `UP`. There is no need to restart the app, re-run `SpringApplication.run()`, and no new `ApplicationReadyEvent` fires merely because we changed state after startup.

## 8. Experiment B — Proactively Adding an HTTP Gate to Block Requests

Stop run A. Package with Maven:

~~~bash
./mvnw clean package
java -jar target/readiness-gate-lab-0.0.1-SNAPSHOT.jar --lab.gate.enabled=true
~~~

On Windows PowerShell use `./mvnw.cmd clean package`. The JAR name is an example matching Initializr artifact/version `readiness-gate-lab` / `0.0.1-SNAPSHOT`; if different, use the actual JAR in `target/`.

Wait until ready, then call:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/process
~~~

While readiness is accepting, the filter calls `chain.doFilter(...)`, so the response is still 200. Next:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/control/refuse
curl -i http://127.0.0.1:8080/lab/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i -X POST http://127.0.0.1:8080/lab/process
~~~

The final `POST /lab/process` call gets **HTTP 503 proactively returned by `OptionalReadinessGateFilter`** with body:

~~~json
{"error":"not_ready"}
~~~

The console **does not increment** the `LAB_PROCESS_ACCEPTED` marker for the blocked request; `/lab/status` remains reachable to compare the counter. The health probe continues reporting `OUT_OF_SERVICE`/503 due to the refusing state, even though the filter exempts Actuator endpoints. This isolates the cause:

| Result | Without Gate | With Gate |
|---|---|---|
| Publishing `REFUSING_TRAFFIC` updates availability | Yes | Yes |
| Readiness probe returns 503 | Yes | Yes |
| Direct `POST /lab/process` call | Still 200 | **503 from custom filter** |
| Did controller `process()` execute on blocked request? | Yes | No |
| Needed web server replacement or context refresh to change state? | No | No |

Calling `POST /lab/control/accept` flips state back and allows new process requests through the filter. When the filter acts, that is application-installed policy. Do not confuse it with how kubelet removes a Pod from routing.

## 9. Why Not Automatically Block Every Request Whenever State Is Refusing?

Application-level self-blocking sounds simple, yet carries trade-offs:

1. **Health and management paths:** if a filter accidentally blocks `/actuator/health/readiness`, infrastructure still sees 503, yet diagnosing the cause becomes harder. Blocking `/actuator/health/liveness` can cause the Pod to restart even though the JVM is completely healthy.
2. **Admin/repair:** an endpoint to disable the gate or fix conditions becomes unreachable if it also sits behind the gate; you need a protected, recoverable control path.
3. **In-flight requests:** refusing state does not mean mid-flight transactions/requests should be severed. Graceful draining aims to curb new requests while letting existing ones finish within a deadline.
4. **Different health groups:** an app may have public and internal endpoints; not every request shares the same policy.
5. **Authentication and security:** health/routing does not replace authentication/authorization; bypassing the gate must not bypass security.
6. **Race condition:** readiness is a snapshot that can change between check and processing. A filter does not provide an absolute "zero new requests after an exact nanosecond" guarantee.
7. **WebFlux vs. Servlet:** reactive web filters differ from Servlet Filters; use the matching stack.
8. **Multi-instance:** a gate in one replica does not guarantee other replicas share the same synchronized state.
9. **Self-inflicted outage risk:** choosing the wrong health dependency or an overly aggressive gate can stop the entire cluster from serving requests even when fallbacks could work.

In most Kubernetes deployments, readiness probes to **manage routing** are the primary mechanism; a custom gate should only be added when a business contract requires **the instance itself to refuse certain requests even on direct access**, with recovery paths thoroughly tested.

## 10. Kubernetes readinessProbe Governs Routing, Not Controllers

Example configuration snippet **inside the container spec** of a Pod/Deployment (not a full YAML manifest):

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

Kubelet uses readiness results to update Pod status and Service endpoint eligibility. This steers routing **through the Service** away from unready Pods once updates propagate. However:

- Routing does not necessarily shift at the exact instant the JVM publishes the event.
- Existing keep-alive connections, ingress, service mesh, or direct-PodIP clients may behave differently.
- `readinessProbe` failure does **not** kill the container by default; that contrasts with `livenessProbe`, which can trigger restarts.
- When all replicas are unready, the Service may have zero healthy endpoints to serve; design dependency/readiness policies carefully.
- `startupProbe` protects slow-starting applications from premature liveness restarts; it is not an in-JVM business gate.

**Deployment note:** The lab binds `server.address=127.0.0.1` solely for local use. In Kubernetes, the servlet server must bind an interface reachable by kubelet, usually by omitting this property or binding `0.0.0.0`. Leaving loopback bound inside a container can cause HTTP probes over the Pod network to fail even while the app runs fine.

### 10.1. Probing on a Separate Management Port

If an app sets `management.server.port` to a different port from the service port, health probes only test the management connector. The management server can remain healthy while the main application port fails. Spring Boot supports adding `/livez` and `/readyz` on the **main server port** with:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

If used, verify the actual URLs and security/routing before changing manifests; do not assume the main port is reachable from kubelet without testing.

## 11. Readiness and External Dependencies: What Are the Limits of Publishing State?

At the startup ready milestone, Spring Boot publishes `ACCEPTING_TRAFFIC` based on the application lifecycle; **it does not by default prove all external dependencies are always healthy**. By design, the default readiness health group focuses on `readinessState`; if you add a database/cache/broker to the readiness group, evaluate the impact on routing across all replicas yourself.

For example, when an application has a `HealthIndicator` with ID `ordersBackend`, you can configure a combined readiness group:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,ordersBackend
~~~

This is an **illustrative configuration**—the lab project has no `ordersBackend`, so do not copy it into the lab unless you provide that indicator. Health group aggregation returns a combined status; it does not mean the framework publishes a new `AvailabilityChangeEvent<ReadinessState>` every time an indicator check fails.

If a dependency fails temporarily yet the app has a fallback, removing every replica from the Service can cause a worse outage. Do not mechanically put external dependencies into liveness. A sound policy specifies which requests require the dependency, error budgets, fallbacks, retries, and which states truly warrant refusing.

## 12. Distinguishing Clearly from Graceful Shutdown

When a process receives a normal shutdown signal, Boot can publish `REFUSING_TRAFFIC` and coordinate closing the embedded web server. With graceful shutdown supported, the server stops accepting new requests per its mechanism, continues processing in-flight requests within the allowed time, and then stops.

Typical configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Key understanding:** `server.shutdown=graceful` is a policy for **stopping the web server during context close**. It does not turn every runtime `REFUSING_TRAFFIC` publication into a `close()` call, and an event from a controller does not invoke graceful shutdown by itself. Conversely, an actual shutdown may terminate the HTTP connector, making probes unreachable: do not demand always seeing a final 503 via curl.

Kubernetes needs coordination across readiness changes, endpoint propagation, and `terminationGracePeriodSeconds`. A Pod may still receive requests over pre-existing connections or un-updated routes. If business rules forbid accepting commands after a specific shutdown point, application-level controls and idempotency must enforce that.

Do not test shutdown using `kill -9` to draw conclusions about graceful behavior; SIGKILL prevents the JVM from running shutdown hooks and cleanup callbacks.

## 13. Troubleshooting Table

| Symptom | Possible Explanation | What to Verify |
|---|---|---|
| Readiness probe 503 yet `/lab/process` returns 200 | State is just a signal; controller does not check automatically | Test direct localhost and check if a custom filter exists |
| Readiness 503 yet Pod still gets requests via PodIP | Client bypasses Service/LB | Check client path, PodIP, network policies, and ingress |
| App published refusing yet Service still sends requests for seconds | Probe/endpoint cycle, caching/connection reuse | Check publish timestamp, kubelet probes, endpoints, and LB |
| Readiness refusing yet liveness still UP | Process is alive but refusing traffic | Inspect both health groups and policy |
| Filter enabled yet process endpoint still returns 200 | Property ineffective, filter not registered, path bypassed | Check bean condition, startup arguments, servlet path |
| Enabling filter causes health/liveness to return 503 when app is healthy | Filter also blocks management endpoints | Inspect `shouldNotFilter(...)`, logs, and probe status |
| After refusal, cannot call accept | Filter also blocks control/admin path | Design a protected recovery path exempted from the gate |
| HTTP 503 from `/lab/process` yet readiness is accepting | Other controller/security/gateway error, not necessarily the gate | Check response body, access logs, and status endpoint |
| Probe 404 | Actuator missing, probes disabled, wrong path/custom config | Check dependencies and `management.endpoint.health.probes.enabled` |
| K8s readiness always fails, local curl works | Bound to loopback in container or wrong port/path | Check `server.address`, manifest, connectivity from Pod network |
| Management probe UP yet main port dead | Health runs on separate management connector | Test probe on main port or additional paths |
| Published accept yet probe stays 503 | Another indicator in readiness group failed, custom mapping, or event unprocessed | Inspect health group aggregation and listeners |
| Controller sees state just flipped yet earlier request still finishes | Filter checks at request entry time | Distinguish in-flight requests from new requests |
| Shutdown probe cannot connect | Embedded server already stopped | Rely on shutdown logs too; do not assume state didn't change |
| All replicas pulled when shared DB has outage | Readiness tied too tightly to shared DB | Evaluate fallbacks, retries, and external indicator policies |

When investigating, record **timestamp**, **state event**, **probe status**, **controller status**, **client path**, and **request count entering the controller**. A single `REFUSING_TRAFFIC` log alone is insufficient to conclude that infrastructure or all HTTP endpoints are rejecting requests.

## 14. Choosing a Solution by Goal

| Goal | Primary Mechanism | What to Avoid |
|---|---|---|
| Tell platform instance is temporarily unready | Publish `AvailabilityChangeEvent<ReadinessState>` | Expecting controllers to return 503 automatically |
| Expose readiness state over HTTP | Actuator readiness health group | Using an ambiguous business endpoint as a probe |
| Stop routing through Kubernetes Service | `readinessProbe` and Service endpoints | Assuming direct PodIP is also blocked |
| Reject requests **inside the JVM** by policy | Filter/WebFilter/interceptor/gateway or handler guard | Accidentally blocking health/admin/recovery and in-flight requests |
| Stop web server and drain requests | Graceful shutdown + termination policy | Only publishing state without closing context |
| Protect business commands on client retries | Idempotency keys, transactions, deduplication | Relying on readiness to guarantee exactly-once |
| Delay traffic during startup until warm-up completes | Runners/readiness state and probes | Relying solely on `"Started"` log or `"Ready"` listener |

**Design advice:** define clearly whether "not ready" means **stop routing new requests from infrastructure**, or **forbid executing new commands inside the process**. Both requirements carry different scope and cost. Readiness state is a great language for communicating with platforms; it does not replace business authorization, throttling, admission control, or transaction semantics.

## 15. Practice Exercises and Acceptance Criteria

### Exercise A — Prove State Does Not Gate Requests Automatically

1. Run the lab with `lab.gate.enabled=false`.
2. Record `/lab/status`, `/actuator/health/readiness`, and `/actuator/health/liveness` after startup.
3. POST `/lab/process`: verify HTTP 200, processed=1.
4. POST `/lab/control/refuse`: check log `LAB_READINESS_CHANGED=REFUSING_TRAFFIC`.
5. GET readiness probe: HTTP 503/`OUT_OF_SERVICE`.
6. POST `/lab/process` again: **still HTTP 200**, processed=2.
7. Explain why two endpoints in the same process return different HTTP statuses without contradiction.

### Exercise B — Prove a Filter Creates the Difference

1. Restart the lab with `--lab.gate.enabled=true`.
2. When accepting, `/lab/process` returns 200.
3. Publish refusing, verify readiness probe 503.
4. POST process: HTTP **503** with `{"error":"not_ready"}`.
5. GET `/lab/status`: counter did not increment because the request was blocked by the filter.
6. Publish accepting; POST process returns 200 again.
7. Point to the `response.setStatus(...)` line in the filter as where requests are actually blocked.

### Exercise C — Readiness and Client Paths

Draw two paths: Client → Kubernetes Service → Pod and Client → PodIP → port. Explain why failing readiness removes an instance from the Service without closing the Pod's HTTP port. Name factors affecting when results are observed: probe period, failure threshold, EndpointSlice updates, kube-proxy/mesh, and existing connections.

### Exercise D — Readiness Differs from Liveness

Keep `REFUSING_TRAFFIC` with liveness `CORRECT`; compare `/actuator/health/readiness` and `/actuator/health/liveness`. Explain why Kubernetes can stop routing without restarting the Pod. Propose a readiness policy for a shared dependency, distinguishing when a fallback suffices to keep receiving traffic.

### Exercise E — Graceful Shutdown

In the lab JAR, add graceful shutdown configuration. Stop the process with Ctrl+C or a valid SIGTERM, and observe new-request behavior and shutdown logs. Do not confuse a stopped connector with merely publishing refusing while the app is still running.

### Acceptance Checklist

- [ ] Name the 4 layers: readiness state, readiness probe, infrastructure routing, and application-level gate.
- [ ] Explain why `ReadinessState.REFUSING_TRAFFIC` does not make every controller return 503 automatically.
- [ ] Build and run Spring Boot 3.5.x/Java 17 with Web + Actuator successfully.
- [ ] Publish refusing/accepting events and read `ApplicationAvailability`.
- [ ] Call readiness/liveness endpoints and distinguish 200/503 under lab defaults.
- [ ] Prove `/lab/process` still returns 200 when readiness is refusing without the filter enabled.
- [ ] Prove the custom filter produces 503 for business requests when refusing.
- [ ] Know why health/control endpoints must be bypassed when building the lab filter.
- [ ] Distinguish readiness gating from graceful shutdown.
- [ ] Explain why Service-level routing does not block direct PodIP access.
- [ ] Understand the relationship between startup runners/ready events and accepting state.
- [ ] Do not use readiness as a substitute for authorization, business validation, or idempotency.

## 16. Official Documentation

- Spring Boot 3.5 — Application Availability and readiness/liveness: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Actuator endpoints, Kubernetes probes, lifecycle, and health groups: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5 — `ApplicationAvailability` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.5 — `AvailabilityChangeEvent` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.5 — `ReadinessState` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html
- Spring Framework — Servlet Filters and Spring Web `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html

**Conclusion:** `REFUSING_TRAFFIC` answers "the instance **should not be routed new requests**", not "every direct HTTP request **has already been blocked by Spring automatically**". To verify, always measure **both the readiness probe and the business endpoint** under configurations with and without a gate. To block requests, add a mechanism with clear ownership in infrastructure or the application; to stop the server, use an actual shutdown mechanism.