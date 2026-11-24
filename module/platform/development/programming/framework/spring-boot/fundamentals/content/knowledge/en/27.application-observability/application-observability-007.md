# Health Status Differs From Liveness or Readiness

When monitoring a Spring Boot application, you may encounter three questions that sound very similar:

1. **Is the application healthy?** — An aggregate health report can state the condition of the components currently being checked.
2. **Is the process still operating properly to keep running?** — This is the **liveness** perspective.
3. **Is this instance ready to receive new traffic?** — This is the **readiness** perspective.

These three questions are not synonymous. An application can be **alive yet not ready to receive requests** while warming up; an external dependency error can make aggregate health report `DOWN` even though the application process is still functioning and should not be restarted; an instance undergoing graceful shutdown may still be alive yet must stop accepting new requests.

Spring Boot Actuator provides the health endpoint and, when enabled appropriately, health groups for liveness and readiness. To operate reliably, you must distinguish **Health status** aggregated from health indicators from **availability state** managed by the application lifecycle, and understand what Kubernetes or a load balancer will do with each signal.

## 1. Concepts: Health, Liveness, Readiness

### Health Status

**Health status** is the evaluation result for one or more components: database, disk space, message broker, integrated services, or custom application indicators.

Example:

~~~json
{
  "status": "UP"
}
~~~

Or when detail visibility is enabled for authorized callers:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "DOWN"
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
~~~

This report reflects **the indicators that the endpoint/group actually includes**, not a promise that all business logic in the application is correct.

### Liveness

**Liveness** answers: *Is the current process in a valid operational state, or has it entered a situation that requires a restart to recover?*

With Kubernetes, consecutive liveness probe failures per policy cause kubelet to **restart the container**. This is a drastic action, so do not tie liveness to external dependency errors that a restart cannot fix.

### Readiness

**Readiness** answers: *Should the instance receive new requests at this moment?*

With Kubernetes, a failing readiness probe marks the Pod as not ready and normally removes it from the list of endpoints used by a Service to route traffic. **Readiness failure by itself does not require restarting the container.**

Readiness fits periods of warm-up, incomplete initialization, draining during shutdown, or a temporary condition making it unsafe for the instance to handle new requests.

### Quick Comparison

| Signal | Question | Typical Kubernetes Action |
|---|---|---|
| Aggregate health | Are checked components functioning? | No fixed restart/routing meaning unless configured as a probe |
| Liveness | Does the container need to be restarted? | Restart if probe failures exceed threshold |
| Readiness | May the Pod receive new traffic? | Remove from routing when not ready |
| Startup probe | Has the application passed initial startup? | Delays liveness/readiness; restarts if startup fails past threshold |

**Rule:** Do not use the exact same check for every question without considering what the operations system will do when the check fails.

## 2. Enabling Spring Boot Actuator

In Gradle Groovy DSL, for a project already using the Spring Boot plugin and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

A minimal Spring Boot application:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

When Actuator is properly configured, the HTTP health endpoint normally has the path:

~~~text
GET /actuator/health
~~~

Example:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Typical response:

~~~http
HTTP/1.1 200
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Actual media type and body depend on version, state, and display configuration. The example above only illustrates `UP`.

There is no need to expose all Actuator endpoints. In the default HTTP configuration of many modern Spring Boot lines, the health endpoint is reachable; changing the management base path, port, security, or exposure settings can alter the path and access permissions.

## 3. How Do `HealthIndicator` and Health Status Work?

Each `HealthIndicator` contributes a `Health` object:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class InventoryHealthIndicator implements HealthIndicator {

    @Override
    public Health health() {
        boolean available = checkInventoryLocally();

        if (available) {
            return Health.up().build();
        }
        return Health.down().build();
    }

    private boolean checkInventoryLocally() {
        // Illustrative. In practice use an appropriate, lightweight check with timeout.
        return true;
    }
}
~~~

In a Spring Boot application with a database and Actuator, contributors might include:

- `db`: reflects database status per the auto-configured health indicator.
- `diskSpace`: checks disk space against a threshold.
- `ping`: simple indicator confirming the endpoint can handle requests.
- Custom indicators declared by the application or libraries.

The `/actuator/health` endpoint aggregates contributors using a `StatusAggregator`.

### Common Statuses

| Status | Typical Interpretation |
|---|---|
| `UP` | Checked component functions per indicator criteria |
| `DOWN` | Component fails to meet health check criteria |
| `OUT_OF_SERVICE` | Component/instance should not currently participate in serving |
| `UNKNOWN` | Status could not be determined by the current check |

Beyond default statuses, an application can define custom statuses. In that case, understand how aggregation and mapping to HTTP status work appropriately.

### Aggregation Does Not Mean “Everything Works”

Example response:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {"status": "DOWN"},
    "diskSpace": {"status": "UP"}
  }
}
~~~

It only reports results for `db` and `diskSpace` in the current group. A business flow calling an external payment service might be failing while health remains `UP` if no indicator checks that capability.

Conversely, health reporting `DOWN` due to a database used for background jobs does not by itself prove all remaining APIs must stop accepting requests.

## 4. HTTP Status Differs From the `"status"` Field in JSON

Actuator health can return body:

~~~json
{"status":"UP"}
~~~

and HTTP 200. For unhealthy statuses such as `DOWN` or `OUT_OF_SERVICE`, Spring Boot defaults to mapping them to HTTP 503 (Service Unavailable). `UNKNOWN` typically still maps to HTTP 200 by default.

An example:

| Health status | Common Default HTTP Code |
|---|---|
| `UP` | 200 |
| `DOWN` | 503 |
| `OUT_OF_SERVICE` | 503 |
| `UNKNOWN` | 200 |

You can configure `management.endpoint.health.status.http-mapping.*` to change mappings in supported versions, as well as configure precedence order for custom statuses. However, when using Kubernetes HTTP probes, the **HTTP response status code** is the primary signal; kubelet does not parse the `status` string inside JSON to infer state.

### Example Custom HTTP Mapping

~~~properties
management.endpoint.health.status.http-mapping.fatal=503
~~~

This example is only meaningful if the application defines a custom `Status("FATAL")` and configures matching status aggregation. When overriding mappings, consult docs for your version because declaring custom mappings can affect default mappings of `DOWN` and `OUT_OF_SERVICE`; declare them explicitly if needed.

Do not map `DOWN` to HTTP 200 just to prevent probes from failing: that hides real failures from the orchestrator.

## 5. The Biggest Problem: Aggregate Health Does Not Equal Liveness

Suppose an application has three replicas and a shared database:

~~~text
                   Kubernetes Service
                         |
              +----------+----------+
              |          |          |
              v          v          v
           Pod A       Pod B       Pod C
              \          |          /
               \         |         /
                +--------+--------+
                         |
                         v
                    Shared DB
~~~

If the database fails temporarily, the `db` health indicator across all three Pods can return `DOWN`.

If you use `/actuator/health` as the **liveness probe**, Kubernetes may continuously restart all three Pods. Restarting the application **cannot fix an external database outage**. Instead, it can cause:

- Unnecessary loss of connections and transient state.
- Connection creation spikes as the database recovers.
- Slower overall recovery.
- Restart loops across all replicas.
- Masking of the original error signal as logs get cut off repeatedly between startup and shutdown.

This is why Spring Boot recommends **excluding external-system health checks from liveness**.

A living instance can temporarily fail to reach the database. Liveness should only fail when the instance itself enters a state where **restarting is a reasonable recovery action**.

## 6. Readiness Should Not Copy Aggregate Health Blindly Either

A common reaction is: “Then let's move all health checks to readiness.” That approach still needs thought.

If the shared database loses connectivity and every Pod's readiness returns 503, Kubernetes may have zero ready endpoints left to route traffic. From the caller's perspective, the entire Service stops accepting requests—even endpoints **that do not need the database**.

For some systems that decision is right: if every critical request requires database access, continuing to accept traffic only produces mass failures.

Yet other systems have cache reads, health info, or independent APIs that can still serve when the database is temporarily unavailable. In those cases, marking every Pod unready can widen the incident.

**Readiness is a decision about an instance's ability to serve traffic, not just a logical AND of every dependency.**

Questions to answer:

1. Does the failing dependency truly prevent this instance from serving the traffic the load balancer sends?
2. Can other Pods take over, or do all of them share that dependency?
3. When removing the Pod from routing, do users get a better experience or just an immediate 503 at the gateway?
4. Is the dependency failure transient such that the app can retry or circuit-break?
5. Is the health check fast, stable, and lightweight enough to be called repeatedly?

## 7. `ApplicationAvailability`: The Liveness and Readiness State Model

Spring Boot provides the `ApplicationAvailability` abstraction to track an application's availability state.

Two key enums are:

~~~java
org.springframework.boot.availability.LivenessState
org.springframework.boot.availability.ReadinessState
~~~

Common values:

**LivenessState**

- `CORRECT`: the process is considered to be operating normally.
- `BROKEN`: the process is no longer operating properly and a restart may be required.

**ReadinessState**

- `ACCEPTING_TRAFFIC`: the instance can receive traffic.
- `REFUSING_TRAFFIC`: the instance is not yet ready or should no longer receive new traffic.

These are **lifecycle-driven availability states**, not results of automatically scanning all external dependencies.

### Lifecycle Diagram

~~~text
Application starting up
  Liveness: BROKEN
  Readiness: REFUSING_TRAFFIC
            |
            v
Application context refreshed
  Liveness: CORRECT
  Readiness: REFUSING_TRAFFIC
            |
            v
ApplicationRunner / CommandLineRunner complete
            |
            v
Application ready
  Liveness: CORRECT
  Readiness: ACCEPTING_TRAFFIC
            |
            v
Graceful shutdown begins
  Readiness: REFUSING_TRAFFIC
  Liveness: may remain CORRECT while stopping
~~~

Exact transition points depend on lifecycle/version, yet the crucial meaning is that **liveness can become good before readiness becomes good**.

An application may have just finished creating its context and operate normally as a process, yet still be executing runners or preparation work and therefore not ready for new requests.

## 8. Reading `ApplicationAvailability` in Code

Spring Boot can inject `ApplicationAvailability` into application beans:

~~~java
package com.example.orders.monitoring;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class AvailabilitySnapshot {

    private final ApplicationAvailability availability;

    public AvailabilitySnapshot(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean isAlive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }

    public boolean isReady() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

This shows how to read state at runtime. Do not replace normal controller business decisions by calling `isReady()` on every request if the load balancer already uses readiness for routing. Handling incoming requests during state transitions also depends on graceful shutdown policy.

### Reading When the Application Is Ready

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ReadyDiagnostics {

    private final ApplicationAvailability availability;

    ReadyDiagnostics(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @EventListener(ApplicationReadyEvent.class)
    void onReady() {
        System.out.println(
                "Readiness at ready event: "
                + availability.getReadinessState()
        );
    }
}
~~~

This listener is created as a bean and runs once the context is prepared. It is not a mechanism for receiving startup events emitted before the context exists.

Do not use logged availability state as the sole proof of external system health; it only reflects state managed by the application lifecycle and events.

## 9. `LivenessStateHealthIndicator` and `ReadinessStateHealthIndicator`

Spring Boot Actuator integrates availability with health via corresponding indicators:

- `LivenessStateHealthIndicator` based on `LivenessState`.
- `ReadinessStateHealthIndicator` based on `ReadinessState`.

They convert `ApplicationAvailability` states into health statuses exposable through HTTP health groups.

Representative meaning:

| Availability state | Typical Health Status | Default HTTP Result |
|---|---|---|
| `LivenessState.CORRECT` | `UP` | 200 |
| `LivenessState.BROKEN` | `DOWN` | 503 |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | 200 |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | 503 |

When probes are enabled, Actuator provides dedicated groups, normally at URLs:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

These are **health groups**, not two separate processes, two Spring contexts, or two web servers.

## 10. Enabling Liveness/Readiness Probes Outside Kubernetes

In Kubernetes environments detected by Spring Boot, probe support is typically activated automatically when Actuator and matching conditions are present.

When running locally, in a VM, or in environments not recognized as Kubernetes, enable them explicitly:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Or YAML:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Once enabled, test:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Illustrative response for a ready instance:

~~~json
{"status":"UP"}
~~~

If readiness is refusing traffic:

~~~http
HTTP/1.1 503 Service Unavailable

{"status":"OUT_OF_SERVICE"}
~~~

These paths assume the Actuator web base path is `/actuator`, the management port matches the application port, and endpoints/groups are not altered by security or exposure settings.

### Version Note

Health groups for Kubernetes probes evolved in modern Spring Boot lines, notably from Boot 2.3 onward. Auxiliary properties and behavior can vary across versions. For projects on older Boot 2.x releases, do not copy Boot 3 configuration verbatim without checking documentation for the running version.

## 11. Aggregate Health and Groups Have Different Indicator Sets

A very common source of confusion:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

**do not necessarily** evaluate the same set of contributors.

Example:

~~~text
Health root:
  db
  diskSpace
  ping
  other enabled health contributors

Liveness group:
  livenessState

Readiness group:
  readinessState
~~~

In Spring Boot's common default Kubernetes probe configuration, liveness/readiness groups are built from the corresponding availability-state indicators. External health indicators like `db` are usually **not automatically included in liveness/readiness groups**.

Therefore, it is completely possible to observe:

| Endpoint | Result | Explanation |
|---|---|---|
| `/actuator/health` | `DOWN` | A contributor such as the database is failing |
| `/actuator/health/liveness` | `UP` | Process is still alive and needs no restart |
| `/actuator/health/readiness` | `UP` | `ApplicationAvailability` still allows traffic |

This is not necessarily a contradiction or a bug. The endpoints answer **different questions**.

If you want readiness to include an additional dependency check, explicitly configure the group—only after evaluating the impact on routing.

## 12. Kubernetes `livenessProbe`: Fail Only When Restarting Helps

Example container configuration in a Kubernetes Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: app
          image: example/orders-service:1.0
          ports:
            - name: http
              containerPort: 8080
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

This example assumes the container listens on port 8080 and Actuator/probe endpoints are reachable from kubelet.

A Kubernetes liveness HTTP probe checks the HTTP response. If liveness fails consecutively `failureThreshold` times, kubelet considers the container unhealthy and restarts it according to the container/Pod restart policy.

### Cases Where Liveness Should Reflect `BROKEN`

- An internal state corruption unrecoverable via retry or continued execution.
- A core process control component is severely stuck and needs a restart.
- The application detects an unrecoverable internal invariant violation and explicitly publishes the matching readiness/liveness state.

### Cases That Should Not Make Liveness `DOWN`

- Database temporarily unreachable.
- External payment provider returning 503.
- A message broker shared by all replicas loses connection.
- A downstream API times out.
- External cache disconnects while the process can still run/retry.

Liveness is the decision “is restarting the container reasonable?”, not “are all dependent services UP?”.

## 13. Kubernetes `readinessProbe`: Traffic-Receiving Decision

In the same Deployment above, `readinessProbe` uses:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

When the readiness endpoint stops succeeding, Kubernetes marks the Pod NotReady. Services relying on readiness endpoints normally stop routing new requests to that Pod.

However:

- The container **does not automatically restart solely because readiness failed**.
- A Pod can keep running background work.
- Once readiness recovers, the Pod can rejoin traffic rotation without a restart.
- Changing readiness state does not automatically close all open connections or guarantee in-flight requests stop instantly.

Readiness is useful for:

1. Application not yet ready after bootstrap.
2. Instance warming up essential internal data.
3. Replica not yet synchronized with required state.
4. Instance entering drain mode for maintenance.
5. Instance undergoing graceful shutdown, needing to stop accepting new requests.

### Do Not Turn Readiness Into an Overly Heavy Health Check

Kubelet may invoke readiness many times per minute on every replica. If each readiness request runs a complex SQL query or calls a slow upstream, probing itself can generate substantial load.

For external dependencies, consider using periodically updated state with timeouts/circuit breakers monitored separately, rather than making long network calls inside every health request.

## 14. Startup Probe: Solving Slow Startup

An application may need time to load caches, initialize connection pools, apply initialization, or run legitimate bootstrap steps.

If `livenessProbe` starts checking too early, it can restart the container before the application finishes starting. Kubernetes provides **`startupProbe`** to handle this phase.

Example:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30
~~~

With this illustrative configuration, the startup probe has a failure budget of roughly 30 checks spaced 5 seconds apart before Kubernetes deems startup unsuccessful. This is a budget of check counts/intervals, not an exact total wall-clock guarantee because timeouts, scheduling, and runtime factors also affect timing.

When `startupProbe` is configured, Kubernetes **delays executing liveness and readiness probes** until `startupProbe` succeeds. Afterward, liveness and readiness run under their own configurations.

Diagram:

~~~text
Container started
       |
       v
startupProbe
       |
  +----+----+
  |         |
Fail      Success
  |         |
Retry       v
  |    Start liveness/readiness checks
  v
Over threshold
  |
  v
Restart container
~~~

A startup probe can normally target the same liveness endpoint suitable for the application. It is **not** a new Actuator status; it is a Kubernetes mechanism.

### When Should `startupProbe` Be Used?

- Boot time can be long or vary significantly.
- Kubelet checks liveness before the HTTP server starts listening.
- The application needs warm-up yet you do not want to loosen liveness thresholds for the entire runtime lifetime.

If the application starts fast and predictably, `startupProbe` may be unnecessary. For real-world systems with complex initialization, it is usually cleaner than setting a huge `initialDelaySeconds` on liveness and accepting slow deadlock detection for the rest of the lifecycle.

## 15. Liveness/Readiness Also Connect to Graceful Shutdown

A shutting-down application does not necessarily “die” instantaneously. It may need to stop accepting new requests, finish in-flight requests, and release resources.

Spring Boot supports embedded web server graceful shutdown on supported versions/platforms. Example:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

When the application enters shutdown, readiness can become `REFUSING_TRAFFIC` to signal that no new requests should arrive, while the process remains alive long enough to clean up resources.

Elements to coordinate:

- Readiness state switches to refusing when stopping.
- Kubernetes removes the Pod from EndpointSlices/routing paths per readiness.
- Load balancers and proxies need time to propagate state updates.
- In-flight requests need time to complete.
- Kubernetes `terminationGracePeriodSeconds` must align with graceful shutdown policy.
- The application must handle stop signals properly rather than being killed immediately.

Do not force liveness to `BROKEN` merely to stop a Pod from receiving traffic. Liveness failure can trigger a restart when what you actually need is an orderly drain and shutdown.

## 16. When the Management Port Differs From the Application Port

Spring Boot Actuator can run on a separate management port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
~~~

Then:

~~~text
Main application server: 8080
Management HTTP server: 8081
~~~

An important operational issue: **a passing probe on the management port does not necessarily prove the application port is accepting connections**.

For example, the management context/server may still return HTTP 200 while the main server listener encounters its own failure. Kubernetes might keep treating the container as ready even though real requests to the app port cannot be served.

### 16.1. Additional Paths on the Main Application Port

In Spring Boot lines supporting it, you can enable additional probe endpoints on the main server port:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Typical additional paths on the **main application port**:

~~~text
GET /livez
GET /readyz
~~~

When this configuration is active, Kubernetes can check the application port directly:

~~~yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
~~~

Remember that a simple HTTP endpoint returning 200 still does not prove every business route works. However, checking on the main server port avoids an obvious discrepancy between the management server and application server.

### 16.2. Separate Port Does Not Mean Always Wrong

Some systems intentionally separate the management port to protect endpoints, restrict access, or isolate monitoring traffic. That can make sense.

Still, for liveness/readiness of a web workload, decide clearly whether probes should test:

- Process availability state only?
- Or also the main application server's ability to accept HTTP requests?

For Kubernetes HTTP workloads, endpoints on the main server port generally give a signal closer to real serving capability.

## 17. Creating a Custom `HealthIndicator` for a Critical Dependency

Suppose an application depends on a search backend. You want a dedicated health indicator to observe it.

Example service storing lightweight state updated by a periodic check mechanism:

~~~java
package com.example.orders.monitoring;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class SearchBackendState {

    private final AtomicBoolean available = new AtomicBoolean(true);

    public boolean isAvailable() {
        return available.get();
    }

    public void setAvailable(boolean value) {
        available.set(value);
    }
}
~~~

A health indicator:

~~~java
package com.example.orders.monitoring;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("searchBackendHealthIndicator")
public class SearchBackendHealthIndicator implements HealthIndicator {

    private final SearchBackendState state;

    public SearchBackendHealthIndicator(SearchBackendState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isAvailable()) {
            return Health.up().build();
        }
        return Health.down().build();
    }
}
~~~

This example only illustrates reporting a state. `AtomicBoolean(true)` is not a production way to test a real search backend; state must come from a meaningful monitoring mechanism, avoiding staying permanently true/false after real changes.

At the Spring Boot Actuator level, a bean with the `HealthIndicator` suffix normally contributes a health contributor named `searchBackend`.

### 17.1. Add That Dependency to Readiness Only Intentionally

One configuration option:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,searchBackend
~~~

Then the readiness group evaluates both the application's state and the `searchBackend` indicator.

**Impact to consider:** If a search backend shared across all Pods fails, readiness for every Pod can turn into 503. Confirm this is truly the desired behavior.

Do not add `searchBackend` to liveness just to “monitor thoroughly.” An external dependency is not necessarily tied to restarting the process.

### 17.2. If You Want to Observe a Dependency Without Making Pods Unready

You can still leave `searchBackend` in root health or create a dedicated monitoring group, while readiness reflects only availability state.

Architectural meaning:

~~~text
/actuator/health
   -> aggregate monitoring of components

/actuator/health/liveness
   -> decide whether to restart the instance

/actuator/health/readiness
   -> decide whether the instance receives new traffic
~~~

Separating these goals lets monitoring alerts spot dependency failures without accidentally triggering mass orchestration actions unnecessarily.

## 18. Creating a Custom Health Group for a Subsystem

Spring Boot Actuator can group health contributors by check objective. Example configuring a group for an auxiliary backend:

~~~yaml
management:
  endpoint:
    health:
      group:
        search:
          include: searchBackend
          show-details: never
~~~

When the group is declared and the endpoint is exposed appropriately:

~~~text
GET /actuator/health/search
~~~

A dedicated group helps backend monitoring track search health without forcing Kubernetes to treat that result as liveness or readiness.

### Groups Are Not Automatic Kubernetes Probes

Creating a `search` group **does not make Kubernetes aware of it automatically**. Kubernetes only uses the URLs configured in Deployment/Pod `livenessProbe`, `readinessProbe`, or `startupProbe`.

Similarly, a health group with status `DOWN` does not restart containers by itself if no orchestrator uses it as a liveness probe.

### Check Scope Shapes Result Meaning

A group can select different contributors, so name it after its purpose. For example, a `dependencies` group checking downstream services should not be presented to operators as an answer to “does the pod need a restart?”.

## 19. Intentionally Changing `ReadinessState` Inside the Application

In some scenarios, an application has a warm-up phase or needs to refuse traffic during state transitions. You can publish an `AvailabilityChangeEvent` to change the availability state.

Example service toggling readiness for maintenance:

~~~java
package com.example.orders.monitoring;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class TrafficControlService {

    private final ApplicationEventPublisher publisher;

    public TrafficControlService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

When the readiness group includes the `readinessState` indicator, changing the state causes the endpoint to reflect the new state.

### Explicit Transition Conditions Are Required

Do not publish `ACCEPTING_TRAFFIC` at the start of a constructor or `@PostConstruct` without proving the application is ready. Spring Boot manages normal lifecycle milestones automatically; manual publication should be reserved for cases where the application has genuine extra conditions.

If multiple components emit readiness change events, design clear state ownership and coordination. One component publishing `ACCEPTING_TRAFFIC` must not inadvertently override another critical maintenance process's decision to refuse traffic.

### Marking `LivenessState.BROKEN`

An application can also publish `LivenessState.BROKEN` for an unrecoverable internal failure. However, exercise extreme caution: doing so can cause continuous restarts, especially if the root cause is a failing external dependency.

Choose `BROKEN` only when the process is in a state where **restarting is the right recovery action**, never as a substitute for logging or alerting.

## 20. A Health Check Can Impact the Application

Health indicators are code running inside the application. If a check is too heavy, lacks a timeout, or throws unhandled exceptions, monitoring can actively degrade or take down the service.

Risks include:

- Every probe executes a complex database query.
- Every probe makes HTTP calls to multiple downstream services.
- Health checks exhaust thread pools or connection pools.
- Many Pods probe a shared dependency in lockstep, creating load spikes.
- Probe timeout too short causes false negatives under brief slowness.
- Probe timeout too long delays incident detection.
- Health checks contain side effects that mutate data instead of merely observing state.

### Designing a Safer `HealthIndicator`

An indicator should:

1. Check the exact condition operators need to observe.
2. Have short execution time, a timeout, and resource bounds.
3. Never mutate business state.
4. Return a clear status rather than silently swallowing exceptions.
5. Minimize sensitive info in details.
6. Never turn a downstream outage into an unnecessary restart loop.

You can use **cached state** updated by a separate monitoring mechanism for expensive dependency checks. Even then, cached state must have a TTL or clear staleness marker; a permanently stale “UP” value is untrustworthy.

## 21. Liveness Failure and Readiness Failure Have Different Consequences

Suppose there are three Pods A, B, and C.

### Scenario A: Pod A Hits an Internal Deadlock

~~~text
Pod A: Liveness DOWN, Readiness may be unresponsive
Pod B: Liveness UP, Readiness UP
Pod C: Liveness UP, Readiness UP
~~~

Kubernetes can restart Pod A's container. B and C continue serving traffic. If the deadlock affects only one instance and a restart resolves it, liveness failure is helpful.

### Scenario B: Pod A Is Warming Up a Cache

~~~text
Pod A: Liveness UP, Readiness OUT_OF_SERVICE
Pod B: Liveness UP, Readiness UP
Pod C: Liveness UP, Readiness UP
~~~

Pod A stays alive and finishes warm-up; Kubernetes does not route new requests to A until it is ready. Restarting A now would destroy warm-up progress.

### Scenario C: Shared Database Fails

~~~text
Shared database DOWN
          |
     +----+----+
     |    |    |
    Pod A Pod B Pod C
~~~

Aggregate health may go `DOWN` across all three Pods. Do not automatically conclude all three processes must restart. Whether readiness should go `OUT_OF_SERVICE` depends on the business serving capability of each Pod and the whole system.

### Scenario D: Rolling Deployment

A new Pod was just created and is not yet ready. Old Pods still serve traffic.

Readiness tells Kubernetes **when the new instance can join routing**. If readiness reports `UP` too early before the application is actually usable, rolling deployments can route traffic to an unready instance and cause intermittent errors.

This is why readiness is more than checking whether a process “returns HTTP 200.”

## 22. Defining Probes and Thresholds in Kubernetes

A fuller configuration:

~~~yaml
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
  successThreshold: 1

startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30
~~~

This example uses main-port aliases `/livez` and `/readyz`, so the application must enable `management.endpoint.health.probes.add-additional-paths=true` (or supported equivalent) before deployment.

Meaning of key parameters:

| Parameter | Purpose |
|---|---|
| `periodSeconds` | Interval between probe runs |
| `timeoutSeconds` | Wait time limit per check |
| `failureThreshold` | Consecutive failures before the probe is considered failed per policy |
| `successThreshold` | Consecutive successes needed to be considered passing where supported |
| `initialDelaySeconds` | Wait time before starting probes, interacting with other probes per Kubernetes rules |

Do not pick `timeout`/`failureThreshold` by intuition. An application with GC pauses, slow startup, or distinct latency traits needs sensible thresholds; overly sensitive settings can trigger restarts or traffic flapping even when the application is not truly broken.

## 23. An HTTP Endpoint Returning 200 Is Not Enough to Prove Business Functionality

Even when `/actuator/health/liveness` and `/readiness` both return 200, these can still happen:

- A business endpoint throws exceptions.
- Critical database queries fail.
- A payment gateway cannot process transactions.
- Cache data is stale.
- A background queue consumer stopped.
- The app returns HTTP 200 yet computes wrong business data.

Therefore, **health probes do not replace all of observability**.

Complementary signals:

- Metrics: error rate, latency, saturation, queue lag.
- Logs: exceptions and structured info, without secrets.
- Distributed tracing: request flow across services.
- Business-level monitoring: metrics reflecting real business work.
- Synthetic checks: testing critical business journeys.
- Alerting: based on SLOs and user impact, not a single health endpoint.

The health endpoint is a useful interface for orchestration, not quality certification for the whole application.

## 24. Security and Access Permissions for Health Endpoints

Actuator endpoints can return status and, if configured, details such as database, disk space, or custom contributors. This data helps operators yet can also reveal infrastructure layout.

Example property:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
~~~

Detail visibility values can include `never`, `when_authorized`, and `always` depending on version. Health groups can have individual settings.

Principles:

- Do not expose all Actuator endpoints to the Internet just so kubelet can call health probes.
- Use appropriate network policies, authentication, and authorization.
- Never put connection strings with passwords, tokens, or secrets into `Health.withDetail(...)`.
- Consider exposing health on the main port with minimal output for probes, keeping deep diagnostics inside better-protected monitoring systems.
- If using a separate `management.server.port`, manage both network access and whether probes accurately reflect the main server.

A health check can return minimal external data while internal monitoring still has detailed metrics and alerts separately.

## 25. Testing Health and Availability at the Right Scope

A unit test for a custom `HealthIndicator` can test its logic:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;

class SearchBackendHealthIndicatorTest {

    @Test
    void returnsDownWhenSearchBackendUnavailable() {
        SearchBackendState state = new SearchBackendState();
        state.setAvailable(false);

        SearchBackendHealthIndicator indicator =
                new SearchBackendHealthIndicator(state);

        assertThat(indicator.health().getStatus())
                .isEqualTo(Status.DOWN);
    }
}
~~~

This test proves indicator logic; it **does not prove** the readiness group was configured to include that indicator.

### 25.1. Testing Endpoints After Application Startup

You can create an integration test with Actuator endpoints enabled:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "management.endpoint.health.probes.enabled=true"
)
class HealthProbesIntegrationTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void livenessEndpointRespondsAfterStartup() {
        ResponseEntity<String> response = rest.getForEntity(
                "/actuator/health/liveness",
                String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody()).contains("UP");
    }
}
~~~

This example assumes the application context started cleanly, Actuator health endpoints are exposed on the same port, and no security rule blocks the test client. If the project uses a separate management port, authentication, or a custom base path, adjust the test accordingly.

### 25.2. Testing Readiness When Refusing Traffic

If the application explicitly publishes `AvailabilityChangeEvent` with `ReadinessState.REFUSING_TRAFFIC`, you can test that the readiness indicator/group returns the matching status, then restore `ACCEPTING_TRAFFIC` afterward.

Avoid sharing an application context with mutated readiness state across multiple tests without resetting it. Otherwise subsequent tests may fail due to leftover state.

### 25.3. Verify From Kubernetes, Not Just Spring Tests

An endpoint returning the expected status in tests does not guarantee Kubernetes manifests point to the right URL/port.

When deploying, verify:

- Pod spec defines `livenessProbe`, `readinessProbe`, and `startupProbe` if needed.
- Probe paths match the Actuator base path or aliases.
- Probe port matches the main application port or management port as designed.
- Kubelet can connect to that port.
- A `readiness` failure actually transitions the Pod to NotReady.
- A `liveness` failure triggers the desired restart policy.
- Thresholds suit application startup and latency.

This is integration verification between the application and orchestrator, which unit tests cannot fully replace.

## 26. Diagnosing Common Failures

| Symptom | Possible Cause | How to Address |
|---|---|---|
| `/actuator/health` UP while readiness returns 503 | `AvailabilityState` is `REFUSING_TRAFFIC` | Check lifecycle, runners, warm-up, or readiness change events |
| `/actuator/health` DOWN while liveness is UP | Health root has a failing contributor; liveness reflects process state only | This may be intentional design; distinguish health from restart need |
| `/actuator/health/liveness` returns 404 | Probe groups disabled or different path/base path | Enable `management.endpoint.health.probes.enabled`, check Actuator config |
| Kubernetes restarts continuously during DB outage | Using `/actuator/health` as liveness or putting DB in liveness | Use `livenessState` only; keep external dependencies out of liveness |
| All Pods NotReady when shared backend fails | Readiness depends on shared backend | Evaluate whether interrupting the whole Service is truly intended |
| Pod alive yet receives no traffic | Readiness failing or Service selector/endpoints mismatch | Check readiness endpoint, Pod conditions, Service/EndpointSlice |
| Health on management port UP while API port fails | Probes run only on management context/server | Consider main-port `/livez`, `/readyz` |
| New Pod restarts before startup completes | Liveness timeout/threshold too short, missing startupProbe | Add `startupProbe` and tune bootstrap budget |
| Slow probes consume heavy resources | Indicator runs heavy DB/upstream queries on every call | Use lightweight checks or cached state with TTL and timeout |
| Readiness stays 503 after app is ready | Event/app logic continuously holds `REFUSING_TRAFFIC` | Check ownership and ordering of `AvailabilityChangeEvent` |
| Custom indicator missing from group | Wrong contributor ID or group include config | Check bean name and include configuration |
| Actuator endpoint returns 401/403 | Security blocks probe access | Permit needed probe paths per policy without opening all of Actuator |
| Pod reports Ready yet real requests fail | Probes do not cover sufficient serving conditions | Check main port, metrics/error rate, and readiness semantics |

An effective investigation workflow:

~~~text
1. Read HTTP status + body from the configured endpoint
            |
            v
2. Check whether the endpoint is health root, liveness, or readiness
            |
            v
3. Identify which indicators/groups contribute to the status
            |
            v
4. Inspect ApplicationAvailability and lifecycle state
            |
            v
5. Verify Kubernetes probe path, port, and thresholds
            |
            v
6. Determine whether the fault is local to the instance or a shared dependency
            |
            v
7. Choose restart, drain, retry, alert, or backend remediation
~~~

## 27. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| “Health is UP so the app can definitely serve every request.” | Health covers only the configured set of indicators. |
| “Health DOWN means the process must be restarted.” | Health DOWN can stem from an external dependency that restarting cannot fix. |
| “Liveness and readiness are the same endpoint under different names.” | They reflect two different operational decisions. |
| “When readiness fails, Kubernetes restarts the container.” | Readiness failure affects routing; it does not by itself request a restart. |
| “When liveness fails, Kubernetes just stops sending traffic.” | Liveness failures past threshold make kubelet restart the container. |
| “Startup probe is a special Spring Boot `HealthIndicator`.” | Startup probe is a Kubernetes mechanism; it can call existing Boot endpoints. |
| “Every `HealthIndicator` is automatically part of readiness.” | By default the group usually includes only `readinessState`; adding contributors requires configuration. |
| “If the DB flickers, liveness must go DOWN.” | Restarting processes can worsen outages; use monitoring/retry/readiness as needed. |
| “Actuator on a separate port returns UP so the main port is definitely fine.” | The management server may keep running while the main server fails to accept requests. |
| “Readiness UP alone removes the need for metrics, logs, or traces.” | Availability probes do not replace observability and SLO monitoring. |

## 28. Design Principles for Health and Probes

1. **Separate measurement goals:** aggregate health for diagnostics, liveness for restart decisions, readiness for routing decisions.
2. **Liveness should reflect only local faults that restarting helps recover.** Do not mechanically put shared databases, brokers, or upstream APIs in liveness.
3. **Readiness reflects an instance's capacity to serve traffic.** Weigh the impact when every Pod shares one backend.
4. **Startup probes protect long boot phases.** Do not use overly sensitive liveness thresholds that restart the app before initialization finishes.
5. **Leverage Boot's availability states.** `LivenessState` and `ReadinessState` express lifecycle, while health groups expose those states over HTTP.
6. **Control health group membership.** Add a contributor only when you know which operational decision its outcome should steer.
7. **Keep checks lightweight and safe.** Enforce timeouts, avoid side effects, and avoid heavy network/DB calls every cycle.
8. **Check on the main port when appropriate.** If using a separate management port, evaluate the risk of probes passing while the app server fails to accept requests.
9. **Never expose sensitive details publicly.** Restrict Actuator endpoints and access permissions.
10. **Test end-to-end from app to Kubernetes.** Verify status codes, groups, URLs/ports, Pod conditions, thresholds, and actual behavior.
11. **Never use probes as a replacement for metrics, tracing, or business monitoring.** They complement each other.
12. **Account for graceful shutdown.** Readiness must support orderly traffic draining rather than turning drain into a restart loop.

## 29. Summary

In Spring Boot Actuator, **health status** is the evaluation result of `HealthIndicator`/`HealthContributor` beans within a group. **Liveness** is the process state indicating whether a restart is needed when broken; **readiness** is the instance state indicating whether it should receive new traffic.

Spring Boot exposes `ApplicationAvailability`, `LivenessState`, and `ReadinessState` through health groups so Kubernetes can call `/actuator/health/liveness` and `/actuator/health/readiness`. Kubernetes uses liveness to decide container restarts, readiness to decide Pod routing, and startup probes to give the application adequate time to boot.

**Key takeaway:** Never use an aggregate health endpoint as liveness merely because it is named “health.” Design every check around **the action the operations system will take when that check fails**. Properly distinguishing health, liveness, and readiness prevents needless fleet-wide restarts, prevents routing traffic to unready instances, and improves Spring Boot application stability in production.
