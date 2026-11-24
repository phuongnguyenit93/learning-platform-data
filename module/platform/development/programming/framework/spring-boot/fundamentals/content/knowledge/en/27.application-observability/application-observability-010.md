# Limitations of Health Checks or Startup Logs in Proving an Application Works Properly

When deploying a Spring Boot application, operators typically look at two signs first:

1. The logs contain a line announcing the application started, such as `Started OrdersApplication in ... seconds`.
2. A health endpoint such as `/actuator/health` returns `{"status":"UP"}` or HTTP 200.

Both are useful signals, yet **neither is sufficient to conclude that all application functionality works properly**. A process can be alive, the application context initialized, and the health endpoint responding cleanly while the order-creation API fails to write to the database, pricing calculations produce wrong results, users cannot log in, or only certain replicas are failing.

This lesson focuses on the limits of each signal, the relationship between **startup, liveness, readiness, health, and functional correctness**, and how to combine Spring Boot Actuator with other verification mechanisms to form a reliable operational picture.

> **Principle:** startup logs and health checks provide *scoped evidence*, not a blanket proof that all business behavior is correct.

## 1. “The Application Works Properly” Is a Multi-Layered Question

Look at these statements:

- The JVM process has not exited.
- The Spring application context refreshed successfully.
- The embedded HTTP server is listening on a port.
- A health endpoint returned a successful result.
- The replica is ready to receive requests.
- An API returned HTTP 200.
- Users can complete the order checkout journey.
- Order results have accurate amounts and consistent data.

These statements are **not equivalent**. They describe different layers in the system.

```text
               Increasing verification coverage

      Process is still running
                |
                v
      Spring Boot starts up
                |
                v
      Application ready for traffic
                |
                v
      Required dependencies respond
                |
                v
      API / workflow operates
                |
                v
      Business outcomes are accurate
                |
                v
      Stable under load and over time
```

This diagram shows **scopes to verify**, not an absolute chain of logical guarantees: some applications have no HTTP server, and an application can serve requests correctly even while a non-essential dependency is failing.

### 1.1. Layer Comparison Table

| Layer | Question | Common Signals | What Remains Unproven |
| --- | --- | --- | --- |
| Process | Is the JVM still alive? | PID, container status | Whether threads can process requests |
| Startup | Did the context initialize? | Startup log, startup events | Whether runners and background work completed |
| Liveness | Is the instance still capable of running? | Liveness probe | Whether database or business logic works |
| Readiness | Should traffic be routed to the instance? | Readiness probe | Whether every request will succeed |
| Dependency health | Does a dependency respond? | `HealthIndicator`, ping | Whether real queries or full transactions work |
| API availability | Does the endpoint return a response? | HTTP test, synthetic check | Whether returned data is business-valid |
| Functional correctness | Are business rules right? | Integration/E2E/contract tests | Stability under sustained load |
| Reliability | Does the system meet goals over time? | Metrics, SLI/SLO, traces | Zero rare edge-case bugs |

A sound observability practice combines multiple signals and states explicitly **what each signal verifies**.

## 2. What Does a Startup Log Actually Prove?

Startup logs are messages emitted as the JVM, Spring Boot, and components pass through initialization steps.

Illustrative example:

```text
INFO  Starting OrdersApplication using Java ...
INFO  The following 1 profile is active: "prod"
INFO  Tomcat initialized with port 8080 (http)
INFO  Started OrdersApplication in 4.823 seconds
```

These logs can indicate:

- Java began running the application.
- Spring Boot read part of the configuration and recorded the profile.
- The embedded server initialized during startup.
- Spring Boot reached the milestone where it logs `Started ...`.

However, **a log line is only information recorded at a point in time**. It does not continuously monitor application state afterward.

### 2.1. `Started ...` Does Not Equal `ApplicationReadyEvent`

In Spring Boot's common startup sequence:

```text
SpringApplication.run(...)
          |
          v
Create and refresh ApplicationContext
          |
          v
Write startup log "Started ...", per common Boot flow
          |
          v
ApplicationStartedEvent
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
ApplicationReadyEvent
          |
          v
ReadinessState.ACCEPTING_TRAFFIC
```

This diagram is conceptual; exact details depend on Spring Boot version and `SpringApplication` customizations.

The crucial point is that **runners usually execute after the started milestone and before ready**. Thus, in a scenario where a runner fails:

```text
INFO  Started OrdersApplication in 4.823 seconds
ERROR Failed to execute ApplicationRunner
ERROR Application run failed
```

the `Started ...` line can still have appeared even though **the final startup did not complete successfully**.

### 2.2. Startup Logs Do Not Prove the Process Is Still Alive

Suppose at 09:00 the application logged:

```text
Started OrdersApplication in 4.823 seconds
```

At 09:05 the process could be killed, run out of memory, or restart. The old log line still remains in the logging system.

During investigation, correlate:

- The log timestamp.
- Whether the current process/container is still running.
- Process start time or container restart count.
- Current health probes.
- Request traffic and error metrics during the window under review.

Never use an old startup log to confirm a new deployment is healthy.

### 2.3. Logs Can Be Missing or Delayed

Log collectors can:

- Receive logs late.
- Drop tail logs when a process exits abruptly.
- Interleave logs from multiple replicas.
- Show logs from a pod that was already replaced.
- Be affected by sampling, buffering, or log-level config.

Therefore, **not seeing a success log** is also not enough to conclude the app definitely failed to start. Check current runtime state and probe results.

## 3. Spring Boot Startup Events and Their Limitations

Spring Boot emits lifecycle events, including:

| Event | General Meaning |
| --- | --- |
| `ApplicationStartingEvent` | Startup has begun; context not yet fully created |
| `ApplicationEnvironmentPreparedEvent` | Environment has been prepared |
| `ApplicationPreparedEvent` | Context prepared yet not yet refreshed |
| `ApplicationStartedEvent` | Context refreshed, runners not yet executed |
| `ApplicationReadyEvent` | Runners completed in a successful startup flow |
| `ApplicationFailedEvent` | Startup failed |

These events report **which milestone** startup passed through; they do not automatically verify all business behavior.

### 3.1. Listener Recording Ready

```java
package com.example.orders.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventsLogger {

    private static final Logger log =
            LoggerFactory.getLogger(StartupEventsLogger.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("event=application.ready");
    }
}
```

Logging `application.ready` is more specific than `application.started` when you need to know runners finished.

Still, inside this listener you **must not assume**:

- All background tasks finished.
- Database connections will remain healthy for the next request.
- Redis, Kafka, or partner APIs are always ready.
- Access permissions on every endpoint are configured correctly.
- Returned data is business-accurate.

### 3.2. A Runner Can Return Before Background Work Completes

```java
@Component
public class WarmupRunner implements ApplicationRunner {

    private final Executor executor;
    private final CatalogService catalog;

    public WarmupRunner(Executor executor, CatalogService catalog) {
        this.executor = executor;
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        executor.execute(catalog::warmUp);
    }
}
```

Assume `Executor` and `CatalogService` are configured. This runner merely **submits a task** and returns immediately. Spring Boot can proceed to `ApplicationReadyEvent` while `warmUp()` is still executing.

If warm-up is mandatory before serving requests, there are two design paths:

1. Wait for work to finish inside a synchronous runner, with explicit timeouts and error handling.
2. If work genuinely runs in the background, make readiness reflect actual completion before allowing traffic.

A log saying “warm-up scheduled” does not at all mean “warm-up completed.”

### 3.3. The Ready Event Is a Milestone, Not a Health Monitor

`ApplicationReadyEvent` normally fires once upon successful startup. It does not re-fire whenever the database disconnects or a queue backs up.

Runtime issues require health signals, metrics, tracing, logging, or specialized checks.

## 4. What Is a Health Check?

A **health check** is a scoped check returning a health assessment against programmed criteria.

A health endpoint may examine:

- Whether the application responds to check requests.
- Whether the JVM and application context are still operating.
- Whether a dependency is reachable.
- Whether a custom readiness condition is satisfied.

With Spring Boot Actuator, the health subsystem aggregates results from multiple `HealthIndicator` or `HealthContributor` beans to produce an overall status.

Illustrative example:

```http
GET /actuator/health
```

Response:

```json
{
  "status": "UP"
}
```

This states that **the health contributors currently included in the result** yielded an aggregate `UP` per the aggregation policy. It does not claim every API and every business journey was tested.

### 4.1. `UP` Is a Result Against Configured Definitions

Suppose the endpoint has only:

```text
PingHealthIndicator -> UP
```

Then health `UP` practically proves only that the health endpoint can handle a request, proving nothing about database queries or payment functionality.

If the health group contains:

```text
readinessState -> ACCEPTING_TRAFFIC
database -> UP
```

the check's scope is broader, yet it still does not prove billing calculation logic or transaction writes are right.

**A measurement cannot convey more meaning than the conditions it actually checks.**

### 4.2. HTTP 200 and JSON `UP` Are Not Two Independent Proofs

In common Actuator configurations, health status maps to HTTP status per health endpoint rules. For example, `UP` typically returns 200, while `DOWN` or `OUT_OF_SERVICE` typically returns 503.

However:

- A reverse proxy might return 200 on behalf of the backend.
- A wrong path might return 200 from a static fallback.
- An HTTP 401/403 might stem from a security policy or ingress, not a dead JVM.
- HTTP status mapping can be customized.

Thus, reliable verification must confirm **the right URL, the right instance/route, the right response contract, and the right moment**, not just look for any 200 response.

## 5. Adding Spring Boot Actuator

In a project with Spring Boot dependency management, add the corresponding starter.

### 5.1. Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

### 5.2. Maven

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

A compatible Spring Boot web app can expose the health endpoint at:

```text
/actuator/health
```

Actual paths can change with `management.endpoints.web.base-path`, management port, or other settings.

### 5.3. Configuring Information Visibility

Example:

```properties
management.endpoint.health.show-details=never
```

Detail visibility modes depend on version, commonly offering `never`, `when-authorized`, and `always`.

In production, avoid exposing connection URLs, topology, or internal details to unauthorized callers. Health endpoints exist to serve operations, not publish full infrastructure state.

### 5.4. Default Health Endpoint Is a Starting Point

Do not assume adding Actuator alone makes the app check every dependency.

Auto-configured health contributors depend on:

- Dependencies on the classpath.
- Enabled beans and auto-configurations.
- Configured drivers/connections.
- Whether the corresponding health indicator is enabled.
- Which health group is being called.

For example, an app with a JDBC datasource can get a database health contributor; an app without a datasource does not automatically get database checks.

## 6. Liveness and Readiness Differ

These two concepts are especially important when deploying with Kubernetes or an orchestrator with health probes.

### 6.1. Liveness: Does the Instance Need a Restart?

**Liveness** aims to answer:

> Is the instance still able to operate by the criteria the system uses to decide whether to restart it?

Sustained liveness failures can cause the orchestrator to restart the container, depending on configuration.

If you put database health into liveness, a database outage can trigger **simultaneous restarts of every instance**. Restarting usually does not cure a database outage and adds recovery load to infrastructure.

Therefore, liveness should focus on conditions where restarting the process **can plausibly help recover**, rather than bundling every external dependency.

### 6.2. Readiness: Should Traffic Be Sent to the Instance?

**Readiness** aims to answer:

> Is the instance currently eligible to receive traffic under the service's operational contract?

When readiness fails, the orchestrator can pull the instance from request-serving endpoints without necessarily restarting the process.

Readiness may depend on:

- Mandatory startup initialization completing.
- Required caches/reference data being loaded.
- Ability to serve core request types.
- A critical dependency, **if** operational policy chooses to refuse traffic when that dependency is unavailable.

### 6.3. Two Different Questions: Do Not Use One Probe for Every Purpose

| Scenario | Liveness | Readiness | Consideration |
| --- | --- | --- | --- |
| Context started, mandatory warm-up running | Likely good | Not ready yet | Do not send traffic early |
| Shared database temporarily disconnected | Process may be fine | Depends on serving policy | Mass restarts can worsen outage |
| Process deadlocked, unable to handle requests | May fail if probe actually detects | Usually fails | Evaluate whether restart recovers |
| Service running yet optional partner API fails | Good | May stay ready | Return degraded behavior if designed |
| Instance undergoing graceful shutdown | May remain alive | Should refuse new traffic | Let in-flight requests finish |

Do not turn readiness into a check that “everything in the outside world is always healthy.” It must reflect **contractual ability to serve traffic**.

## 7. Spring Boot Availability API

Spring Boot provides states:

```java
LivenessState.CORRECT
LivenessState.BROKEN

ReadinessState.ACCEPTING_TRAFFIC
ReadinessState.REFUSING_TRAFFIC
```

You can read them with `ApplicationAvailability`.

```java
package com.example.orders.observability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class ReadinessReporter {

    private final ApplicationAvailability availability;

    public ReadinessReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean acceptsTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
```

### 7.1. When Does Readiness Become `ACCEPTING_TRAFFIC`?

In the typical sequence, Spring Boot emits `ApplicationReadyEvent` after runners finish, then publishes the traffic-accepting state.

This is a **Spring Boot lifecycle signal**, not proof the framework ran every functional test.

### 7.2. Publishing State Changes

An application can publish traffic refusal:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

public void refuseTraffic(ApplicationContext context) {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
    );
}
```

This suits runtime conditions where the instance should stop taking additional requests.

Still, state is only meaningful if the deployment **actually reads the readiness signal**. If a client calls the HTTP port directly without health-aware routing, it can still send requests.

### 7.3. Do Not Use State to Hide Error Causes

If a service switches readiness to refusing, it should also emit:

- A metric recording the reason.
- A safe log event without secrets.
- Diagnostic status or failure codes.
- Rules for restoring readiness when conditions improve.

Mutating readiness without diagnostic visibility makes investigation hard.

## 8. Health Probes in Spring Boot Actuator

In Spring Boot lines supporting availability probes, dedicated health groups can be enabled in appropriate environments.

Example `application.properties`:

```properties
management.endpoint.health.probes.enabled=true
```

Common endpoints:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

In a detected Kubernetes environment, some Spring Boot versions enable probes automatically. Locally, you can enable them explicitly as shown.

### 8.1. Success Case

Example readiness response:

```json
{
  "status": "UP"
}
```

This is the assessment of the **readiness health group**, not a test exercising every controller.

### 8.2. Traffic-Refusing Case

Example response:

```json
{
  "status": "OUT_OF_SERVICE"
}
```

Under standard status mapping, this case can return HTTP 503, signaling the orchestrator that the instance is unready.

### 8.3. Different Health Groups Can Yield Different Results

An instance can show:

```text
Liveness: UP
Readiness: OUT_OF_SERVICE
```

This is not a contradiction. It can express that the JVM is running yet does not want traffic, such as during startup warm-up or graceful shutdown.

### 8.4. Groups Have Configured Scopes

Do not infer:

```text
/actuator/health/readiness = UP
```

means every `HealthIndicator` in the system ran. The readiness group normally relies on readiness state plus contributors you explicitly include—it does not automatically include all health contributors.

## 9. Health Checks Are Only Valid at Observation Time

Suppose a health endpoint runs `SELECT 1` and gets a successful response at 10:00:00.

At 10:00:01:

- The network can drop.
- The connection pool can exhaust.
- Transactions can deadlock.
- The database can fail over primary.
- Another replica can fail.

“UP at 10:00:00” **does not prove UP at every moment afterward**.

### 9.1. Sampling and Blind Spots

A probe running every 10 seconds:

```text
10:00:00  UP
10:00:10  UP
10:00:20  UP
```

If the app fails from 10:00:12 to 10:00:18 and recovers, those probes may **miss the outage completely**.

This is a limitation of periodic checking (*sampling*).

### 9.2. Fast Probes Miss Many Types of Degradation

Example:

```text
Health request duration: 3 ms
Order checkout p99 latency: 9.5 s
```

The health endpoint can stay fast because it does not perform checkout's work. Meanwhile, users experience slowness or timeouts.

Never use `/actuator/health` latency as a substitute for real API latency.

### 9.3. One Success Does Not Prove Reliability

If an API succeeds 1 out of 100 times, a single `UP` health check says nothing trustworthy about the API's success rate.

You need time-series metrics such as request rate, error rate, latency distribution, and periodic synthetic checks.

## 10. Dependency Pings Do Not Prove Business Operations Work

A database health indicator can verify connectivity or execute a simple query. That helps confirm the database **responds**.

However, an order-writing API might need to:

1. Fetch cart info.
2. Check inventory.
3. Apply promotions.
4. Insert order records.
5. Update inventory status or emit events.

The database returning `UP` does not prove those steps succeed.

### 10.1. Scenarios Where Database Is UP Yet Business Logic Fails

- Schema missing a column after a deployment.
- Entity mapping mismatches the table.
- Service account permissions allow reads only, not writes.
- A table is locked or transactions routinely time out.
- Mandatory reference data is missing.
- A migration ran only partially.
- Real queries are too slow even though the simple health query succeeds.
- Business constraints are misconfigured.

These are issues **beyond the scope** of a minimal ping.

### 10.2. Dependencies Can All Be UP While the System Still Fails

Example:

```text
Database: UP
Redis: UP
Kafka: UP
Payment gateway: UP

Checkout response: wrong amount
```

Healthy individual dependencies do not prove aggregate business logic is right.

### 10.3. Do Not Turn Health Indicators Into Dangerous Transactions

The idea “the health check will run a real payment” could catch more bugs, yet causes:

- Business side effects.
- Cost and data contention.
- Extra load under frequent probing.
- Risk of duplicate transactions and cleanup headaches.

Health endpoints serving orchestrators must be **lightweight, fast, safe, and idempotent**. Deep business-flow verification belongs in a different testing/verification layer.

## 11. Writing a Custom `HealthIndicator`

Spring Boot Actuator lets you declare a `HealthIndicator` to represent an application health condition.

For instance, the app needs to finish loading reference data before serving API responses.

### 11.1. Warm-Up State

```java
package com.example.orders.startup;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupState {

    private final AtomicBoolean complete =
            new AtomicBoolean(false);

    public void markComplete() {
        complete.set(true);
    }

    public boolean isComplete() {
        return complete.get();
    }
}
```

`AtomicBoolean` ensures other threads read the updated state safely across memory boundaries.

### 11.2. Runner Performing Mandatory Work

```java
package com.example.orders.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupRunner implements ApplicationRunner {

    private final CatalogService catalog;
    private final CatalogWarmupState state;

    public CatalogWarmupRunner(
            CatalogService catalog,
            CatalogWarmupState state) {
        this.catalog = catalog;
        this.state = state;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalog.loadRequiredReferenceData();
        state.markComplete();
    }
}
```

`CatalogService` is a hypothetical project service with `loadRequiredReferenceData()`. Because the runner waits for that method to return before marking complete, state switches to true **only after synchronous work actually finishes successfully**.

If the method throws an exception, the runner does not mark complete and startup can fail. That is sensible when missing data leaves the instance completely unable to serve requests.

### 11.3. Custom Indicator

```java
package com.example.orders.startup;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupHealthIndicator
        implements HealthIndicator {

    private final CatalogWarmupState state;

    public CatalogWarmupHealthIndicator(CatalogWarmupState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        return state.isComplete()
                ? Health.up().build()
                : Health.down().build();
    }
}
```

Bean name `catalogWarmupHealthIndicator` is typically mapped by Actuator to contributor ID `catalogWarmup` per `HealthIndicator` naming conventions.

### 11.4. Adding the Indicator to the Readiness Group

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalogWarmup
```

Intended meaning:

- `readinessState` reflects Spring Boot's lifecycle readiness.
- `catalogWarmup` reflects reference data preparation.

When both contributors evaluate healthy, the health group can report UP per aggregation policy.

**Remember:** a `HealthIndicator` existing does not automatically place it in the readiness group. Configure the health group appropriately if probes should use its outcome.

### 11.5. Custom Health Indicators Do Not Automatically Validate Data Correctness

In the example, `isComplete()` only states that code marked it done. If `loadRequiredReferenceData()` has a bug, loads incomplete records, yet returns normally, state still flips to true.

An indicator is only as reliable as **the condition you program**. If “complete” does not validate loaded data, health `UP` can still happen with broken business state.

### 11.6. Do Not Let Checks Block Too Long

`health()` may be called repeatedly by orchestrators or monitoring systems. If every call scans an entire database or downloads large files:

- Probes time out easily.
- Connection pools take extra load.
- Infrastructure outages amplify due to health checks.
- Hundreds of replicas simultaneously generate needless queries.

For expensive checks, consider **maintaining periodically measured state** and having `health()` return quickly with a data-age bound and stale-state handling.

## 12. Liveness, Readiness, and Dependency Health Should Not Be Lumped Together

Suppose a system has 20 replicas sharing one database.

If the database drops connectivity for 30 seconds and every replica's liveness depends on database connectivity:

```text
Database outage
      |
      v
20 liveness probes fail
      |
      v
Orchestrator restarts 20 replicas
      |
      v
Connection storms + cold caches
      |
      v
Database recovery becomes harder
```

This illustrates **the harm of putting a shared dependency outage into process restart criteria**.

### 12.1. Should the Database Be Included in Readiness?

There is no universal answer for every system.

**Reasons to include it:**

- Every core request requires the database.
- A replica cannot return anything useful without database connectivity.
- Traffic should avoid instances unable to serve.

**Reasons to weigh carefully:**

- When every replica loses the database, all may go unready at once.
- A system may prefer returning degraded responses or controlled 503s rather than having gateways fail with “no available endpoints.”
- Database pings may not reflect actual queries.
- Too many probes can add load during an outage.

Choose based on **your traffic serving contract and recovery strategy**, not “the more checks the better.”

### 12.2. Non-Essential Dependencies

For instance, an order system has a confirmation email service. If email sending fails while orders can still be saved and emails retried asynchronously, the entire Order API's readiness does not need to go DOWN.

Instead, you can:

- Record metrics on email failures and queue backlog.
- Alert when backlog rises.
- Return business responses per published rules.
- Monitor retry jobs separately.

Readiness should not be held hostage by every auxiliary component.

## 13. Health Endpoints on a Separate Management Port

Spring Boot can expose Actuator on a management port distinct from the application HTTP port.

Example:

```properties
server.port=8080
management.server.port=9090
management.endpoint.health.probes.enabled=true
```

Then health probes on management port 9090 can return UP **even when the traffic-serving path on port 8080 has its own issue**.

Examples:

- Main application connector stops accepting connections.
- Middleware applied only on the application port fails.
- Ingress route to the application port is misconfigured.
- Management port uses a different thread pool or connector.

### 13.1. Checking on the Same Traffic-Receiving Path

In Spring Boot lines supporting it, you can expose additional liveness/readiness paths on the application port:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

When supported and configured properly, additional paths are typically:

```text
/livez
/readyz
```

on the main application port.

Verify exact paths and the Spring Boot version in use. This reduces the risk of separate management-port health checks missing main application connector failures.

### 13.2. Same Port Still Does Not Mean Every Endpoint Is Right

`/readyz` returning UP on port 8080 only proves requests to that path succeed per probe logic.

It still does not run `/api/orders`, special authentication pipelines, or checkout flows.

Thus same-port health checking **improves connectivity coverage**, not proof of business correctness.

## 14. Kubernetes Probes: `startup`, `liveness`, `readiness`

Kubernetes has three common probe types:

| Type | Question | Main Consequence on Consecutive Failures per Config |
| --- | --- | --- |
| `startupProbe` | Has the container passed the required startup phase? | May restart container when failure threshold exceeded |
| `livenessProbe` | Does the container need a restart to recover? | Restarts container if threshold exceeded |
| `readinessProbe` | Should the Pod receive service traffic? | Marks unready, removes from traffic-serving endpoints |

Crucially, when `startupProbe` is declared, Kubernetes **holds off liveness/readiness probes until the startup probe succeeds**. This keeps slow-starting apps from being restarted prematurely by liveness.

### 14.1. Manifest Fragment Example

The following goes under **one container** in a Pod spec:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
```

This assumes those endpoints live on port 8080 with Actuator and probes appropriately enabled.

`periodSeconds`, `timeoutSeconds`, and `failureThreshold` must be chosen according to actual startup times and runtime behavior. Never copy thresholds straight into production without measuring.

### 14.2. Limits of `startupProbe`

If `startupProbe` only calls the liveness endpoint, it can succeed as soon as Spring Boot evaluates liveness healthy—even before a subsequent business warm-up finishes.

Thus, `startupProbe` is an orchestration mechanism **waiting on a defined startup condition**, not proof the business is ready. `readinessProbe` still needs to reflect traffic-serving capability.

### 14.3. Probes Can Miss Brief Outages

Suppose the readiness probe runs every 5 seconds. A 2-second outage falling between two probes may go undetected. This is a sampling-interval limit.

Real-request metrics and traces are needed to catch short-lived errors probes miss.

### 14.4. Probes Failing Due to Network or Config

Probes can fail due to:

- Wrong port/path.
- Wrong HTTP scheme.
- Security filters requiring authentication.
- Network policies or sidecars breaking connections.
- Timeouts set too low.
- Overloaded nodes.

When a probe fails, distinguish **probe unable to reach the endpoint** from **endpoint evaluating the app as unhealthy**. The two causes require different fixes.

## 15. Health Checks Can Report `UP` While Authorization Is Broken

Suppose:

```text
GET /actuator/health   -> 200 UP
GET /api/orders        -> 403 Forbidden
```

One possibility is that Spring Security configuration accidentally blocked a valid user group.

Default health checks often pass through a different route or security policy than business APIs, so they do not detect authorization bugs on real endpoints.

### 15.1. Functional Errors Still Returning HTTP 200

Example API:

```http
GET /api/prices/SKU-100
```

Response:

```json
{
  "sku": "SKU-100",
  "price": 0,
  "currency": "VND"
}
```

It returns HTTP 200, yet a price of 0 may violate business rules.

A synthetic check verifying only status 200 misses the bug. Assert **response contract and expected results**, not HTTP status codes alone.

### 15.2. Health Does Not Check Every Role, Tenant, or Feature Flag

An API might work for admins yet fail for regular customers, work for tenant A yet fail for tenant B, or fail only when a feature flag is active.

Making a lightweight health endpoint traverse this whole condition matrix is unreasonable. Add appropriate tests, synthetic journeys, segmented metrics, and alerts instead.

## 16. Distinguishing “Running” From “Accurate Data”

This is the difference between **availability** and **correctness**.

A program can handle requests smoothly, throw zero exceptions, and return 200 on every call—yet compute the wrong answer:

```java
public BigDecimal total(
        BigDecimal unitPrice,
        int quantity) {
    return unitPrice.add(
            BigDecimal.valueOf(quantity)
    );
}
```

The code adds instead of multiplying. If business rules require `unitPrice × quantity`, the result is wrong without necessarily causing any infrastructure error.

Health checks:

```text
Database: UP
JVM: healthy
HTTP route: reachable
```

cannot detect broken pricing logic.

### 16.1. Business Testing Is Required

Illustrative unit test:

```java
@Test
void calculatesTotalCorrectly() {
    BigDecimal total = calculator.total(
            new BigDecimal("125000"),
            3
    );

    assertThat(total).isEqualByComparingTo("375000");
}
```

This test verifies a specific invariant, unlike liveness/readiness.

### 16.2. Tests Also Have Limits

A passing unit test does not prove production uses the same data, secrets, network policies, or dependency states.

Therefore, combine **pre-deployment testing** with **post-deployment runtime observability**.

### 16.3. Invariants Need a Source of Truth

A good functional check needs to know what constitutes a correct outcome:

- By what rules is the total calculated?
- Is a transaction recorded exactly once?
- How can a paid order transition states?
- What response is valid for each role?

If pass/fail criteria are undefined, neither synthetic tests nor health checks can safeguard quality.

## 17. Summary of “UP Yet Broken” Scenarios

| Sign | Actual Fault | Why Health/Startup Is Insufficient |
| --- | --- | --- |
| `Started ...` appears | Runner failed after started milestone | Startup log precedes runners |
| `/actuator/health` UP | Checkout hits SQL permission error | Health ping does not write orders |
| Readiness UP | Async cache loading incomplete | Runner only submitted task and returned |
| Readiness UP | API returns wrong price | Readiness does not test business rules |
| Database health UP | Migration schema missing column | Connectivity does not guarantee matching schema |
| Health UP | One role wrongly blocked with 403 | Health route uses different security path |
| Health UP | API p99 latency 9 seconds | Lightweight probe does not reflect real load |
| Health UP | Payment provider returns wrong currency | Alive dependency does not mean right data |
| Health UP on management port | Main port refuses requests | Two connectors can be independent |
| Health UP on one pod | Another pod failing | One probe does not represent the entire fleet |
| Ready log has old timestamp | Process crashed/restarted | Logs are historical events |
| Synthetic check returns 200 | Response body violates contract | Checking status alone is insufficient |
| E2E smoke test passes | Bug only triggers under high load | Smoke tests do not measure endurance |

These scenarios illustrate one rule: **every measurement leaves a set of conditions unverified**.

## 18. Testing Real Paths With Synthetic Monitoring

**Synthetic monitoring** proactively sends scheduled simulated requests into the system to verify desired behaviors.

Example synthetic HTTP check for a catalog lookup API:

1. Call an appropriate public endpoint.
2. Verify expected HTTP status.
3. Verify valid response schema.
4. Check key fields.
5. Measure response time.
6. Record results in a separate monitoring system.

### 18.1. Synthetics Go Deeper Than Health Pings

Health check:

```http
GET /actuator/health
```

Functional check:

```http
GET /api/catalog/items/SKU-DEMO
```

For a stable mock product code, synthetics can verify:

```json
{
  "sku": "SKU-DEMO",
  "currency": "VND",
  "available": true
}
```

With clear expected data and assertions, it detects many failure classes outside Actuator health.

### 18.2. Do Not Use Real Transactions for Continuous Testing

For payment flows, design:

- Sandbox payment providers.
- Segregated test accounts or test tenants.
- Dedicated canary data.
- Contracts that do not trigger real money transfers.
- Cleanup/idempotency for generated data.

Never automatically place real orders or run real charges every 10 seconds just to have a synthetic check.

### 18.3. Synthetics Still Do Not Prove Everything

A synthetic running only with a test account can miss bugs affecting real accounts, other locales, other product types, or massive datasets.

Pick a few **critical user journeys**, rather than trying to make one synthetic test replicate every production scenario.

### 18.4. From Where Do Synthetics Observe?

Checking a pod's localhost directly bypasses:

- Public DNS.
- API gateways.
- TLS termination.
- WAF.
- Ingress and routing.
- User network paths.

Conversely, external synthetics cover more components yet can experience Internet noise.

Choose observation vantage points matching your question: **is this instance working?** vs. **can external users complete requests?**

## 19. Integration Tests, Contract Tests, and End-to-End Tests

Health checks serve runtime operations; tests verify defined contracts and behaviors.

### 19.1. Unit Test

Verifies rules within a single component:

```java
@Test
void rejectsNegativeQuantity() {
    assertThatThrownBy(
            () -> calculator.total(
                    new BigDecimal("10"),
                    -1
            )
    ).isInstanceOf(IllegalArgumentException.class);
}
```

This example assumes the calculator enforces validation as required.

### 19.2. Integration Test

Verifies interactions with one or more real components or realistic test environments:

- Repositories against an appropriate test database.
- Transaction boundaries.
- SQL schemas.
- Serialization/deserialization.
- Spring Security filter chains.

### 19.3. Contract Test

Verifies the exchange interface between consumer and provider:

- Request/response schemas.
- Status codes.
- Mandatory fields.
- API version compatibility.

A dependency reporting health `UP` can still break its contract with calling services. Contract testing adds another angle.

### 19.4. End-to-End Test

Tests a journey from start to finish:

```text
Log in
   |
   v
Create cart
   |
   v
Apply pricing / promotions
   |
   v
Place order
   |
   v
Confirm status
```

E2E tests expand interaction coverage yet are costlier and more sensitive to data and environments. They do not replace lightweight, always-available orchestrator health probes.

### 19.5. Assigning Clear Roles

```text
Unit tests ------------> Small rules are right
Integration tests -----> Interactions between components work
Contract tests --------> Interfaces between services match
E2E tests -------------> User journeys work in test environments
Synthetic monitoring --> Key real-style user journeys tested periodically
Metrics/tracing/logs --> Behavior and incidents in live traffic
Liveness/readiness ----> Instance operational decisions
```

No single type is the “final proof” covering every case.

## 20. Metrics Reflect User Experience Better Than a Ping

To know whether users can genuinely use the system, track suitable **Service Level Indicators (SLIs)**.

Common SLIs:

- **Availability / success rate:** proportion of successful requests per service definition.
- **Latency:** response times, commonly focusing on p95/p99 percentiles.
- **Error rate:** failure rates by route and error category.
- **Throughput:** request rate or transaction volume.
- **Queue lag:** queue delay in asynchronous systems.
- **Business outcome:** completed transaction rate, successful payment rate per business definition.

### 20.1. Success Rate

An illustrative SLI:

\[
\text{Success rate}
= \frac{\text{Valid requests completed successfully}}
{\text{Total measured valid requests}}
\times 100\%
\]

Definitions of **valid request** and **success** must be agreed upon. For an authentication API, HTTP 401 when a user types a wrong password may be valid application behavior rather than an availability error.

### 20.2. Percentile Latency

If:

```text
Health endpoint: p99 = 5 ms
Checkout API:    p99 = 8 s
```

checkout users still suffer even though the health endpoint is blazing fast.

Latency must be measured on **actual routes or user journeys**, never using the health endpoint as a proxy for all work.

### 20.3. Error Budgets and SLOs

An **SLO** (Service Level Objective) sets a target such as success rate or latency over a time window.

Example:

```text
Target: 99.9% of eligible checkout requests
complete successfully within a 30-day measurement window
```

This is only an example of how to express an SLO, not a mandatory target for every application.

A deployment with `/health=UP` continuously can still breach its SLO if 2% of checkout requests fail.

### 20.4. Do Not Confuse Process Metrics With Product Metrics

Low CPU, steady JVM heap, and health UP are worthwhile operational metrics, yet they do not prove users finish checkouts or receive accurate data.

When designing dashboards, place **service outcomes** beside **infrastructure signals**.

## 21. Tracing and Logging Aid Investigation; They Do Not Self-Verify Correctness

Distributed tracing records processing steps of a request:

```text
HTTP POST /orders
      |
      +--> validate input
      |
      +--> inventory-service
      |
      +--> database insert
      |
      +--> publish event
```

A trace can show:

- Which step was slow.
- Which service returned an error.
- Whether retries occurred.
- Which spans the request traversed.

However, traces do not prove on their own:

- Price formulas were accurate.
- Access permissions were enforced properly.
- Data written to the database satisfied business invariants.
- A message was processed exactly once by a consumer.

### 21.1. Trace Succeeds While Result Is Wrong

```text
checkout trace status = OK
all spans completed
HTTP = 200
chargedAmount = 0 (expected 300000)
```

If code fails to detect and flag a logic bug, tracing may show a “successful” request.

Therefore, knowing business correctness requires corresponding **assertions, invariants, or business signals**.

### 21.2. Logs Need Meaningful Fields

Useful:

```text
event=checkout.failed
failureCode=INVENTORY_TIMEOUT
route=/api/orders
traceId=<trace-id>
durationMs=713
```

Avoid:

```text
requestBody={...}
authorization=Bearer ...
customerEmail=...
```

Logs should carry metadata sufficient for diagnosis without dumping sensitive data.

## 22. Observing by Replica, Zone, and Version

In a multi-replica deployment:

```text
Load balancer
      |
      +--> pod A: healthy
      |
      +--> pod B: healthy
      |
      +--> pod C: faulty
```

Calling health once through a load balancer might land on pod A or B. Getting 200 fails to detect pod C is broken.

### 22.1. Inspecting Individual Instances

With orchestrators:

- Probes should target the exact instance/container being evaluated.
- Dashboards should distinguish pod, instance, zone, and version.
- Metrics should allow comparing error rates after rollouts.
- Logs/traces should include appropriate instance or deployment metadata.

### 22.2. Bugs Occurring Only on One Version

Rollout example:

```text
version v1: 95% traffic, 0.1% errors
version v2:  5% traffic, 8% errors
```

v2's health endpoint may still be UP. Tracking **error rate and latency by version** catches a bad canary before expanding the rollout.

### 22.3. Zonal Failures

One zone might lose connectivity to cache while another zone runs normally. If dashboards aggregate all replicas together, zonal outages can stay hidden.

Health status should be viewed alongside deployment metadata and meaningfully segmented SLIs.

## 23. Post-Deployment Verification

A deployment pipeline can divide checks into layers:

```text
Build artifact
      |
      v
Start process
      |
      v
Verify startup state
      |
      v
Readiness gate
      |
      v
Smoke / synthetic tests
      |
      v
Gradual traffic rollout
      |
      v
Observe latency, errors, business SLIs
      |
      +--> Satisfactory -> Continue rollout
      |
      +--> Regression --> Stop / rollback according to policy
```

### 23.1. Checking Artifacts and Configuration

Before relying on health:

- Does the artifact match the right version/commit?
- Is the right profile active?
- Have external config resources been loaded?
- Are schema migrations compatible with the new version?
- Are secrets and service account permissions right?

An application that starts cleanly yet connects to the wrong environment or runs with a wrong feature flag can still cause major damage.

### 23.2. Readiness Before Receiving Traffic

If a startup runner loads mandatory data, readiness should refuse traffic until work completes.

Never use startup logs as the sole signal for a load balancer to start sending requests.

### 23.3. Smoke Tests

Select representative endpoints:

- A read-only endpoint.
- A protected endpoint with an appropriate test principal.
- A core business function.
- A critical dependency path.

Smoke tests should run only safe operations with controlled data and clear expectations.

### 23.4. Post-Rollout Monitoring

Check:

- Success/error rate of real traffic.
- p95/p99 latency by route.
- Database/HTTP client error classes.
- Queue backlog if asynchronous.
- Business outcome metrics.
- Comparison against pre-rollout baselines.

If any of these degrade severely, health UP is no excuse to keep rolling out despite warnings.

## 24. When Does a Health Indicator Need a Real Check?

Not every custom indicator should simply return an `AtomicBoolean`. Some runtime conditions require time-aware checks.

Example: a service can only process requests while its business config snapshot remains fresh.

### 24.1. Freshness Check

A state holder:

```java
@Component
public class SnapshotState {

    private final AtomicReference<Instant> lastLoadedAt =
            new AtomicReference<>();

    public void markLoaded(Instant instant) {
        lastLoadedAt.set(instant);
    }

    public boolean isFresh(Duration maxAge, Clock clock) {
        Instant loadedAt = lastLoadedAt.get();
        if (loadedAt == null) {
            return false;
        }
        return !loadedAt.isBefore(
                clock.instant().minus(maxAge)
        );
    }
}
```

The example assumes imports for `Instant`, `Duration`, `Clock`, and `AtomicReference`.

An indicator can use it:

```java
@Component
public class SnapshotFreshnessHealthIndicator
        implements HealthIndicator {

    private final SnapshotState state;
    private final Clock clock;

    public SnapshotFreshnessHealthIndicator(
            SnapshotState state,
            Clock clock) {
        this.state = state;
        this.clock = clock;
    }

    @Override
    public Health health() {
        return state.isFresh(Duration.ofMinutes(10), clock)
                ? Health.up().build()
                : Health.down().build();
    }
}
```

Here a `Clock` bean is required in the context, e.g., configuring `Clock.systemUTC()` via `@Bean`.

### 24.2. Limits of Freshness Checks

A “recently loaded” snapshot does not guarantee valid contents. For example, it might miss records or hold invalid data.

So if the business contract requires valid data, snapshot loading must include validation. Health checks only reflect provided state; they do not replace validation.

### 24.3. Avoid Remote Calls on Every Probe

With 100 replicas each receiving a readiness probe every 5 seconds and each probe calling the database:

```text
100 / 5 = 20 probe-driven DB calls/sec
```

Not counting other monitoring agents. When the database is already slow, probes add even more load.

One solution is updating health state periodically with timeouts and rate limits, while the endpoint returns cached state carrying data-age info.

If cached too long, health reports grow stale. This is a **trade-off between measurement cost and signal freshness**.

## 25. When to Use `Health.up()` vs. `Health.down()`?

A custom indicator should reflect a **published definition of health**, not vague intuition.

Example:

```java
@Override
public Health health() {
    if (!referenceDataAvailable()) {
        return Health.down().build();
    }
    return Health.up().build();
}
```

If `referenceDataAvailable()` checks only `cache != null`, the app might still have an empty or stale cache while health reports UP.

### 25.1. Have Clear, Measurable Criteria

Example criteria:

```text
Catalog snapshot loaded successfully.
Mandatory data validation passed.
Snapshot is no older than 10 minutes.
```

Then `UP` carries much clearer meaning.

### 25.2. Do Not Use One Health Status for Every Situation

If an auxiliary feature fails while the main API serves fine, log metrics and alert on degradation instead of marking the entire service DOWN.

If the system cannot guarantee core correctness, refusing readiness may be the appropriate choice.

This definition must be agreed upon across developers, operations, and service owners.

## 26. Risks of Overly “Clever” Health Checks

A health check executing extensive business operations can become a source of failure itself:

- Reading too many tables and exhausting connection pools.
- Deadlocking with business transactions.
- Triggering side effects in payment systems.
- Generating extra log and trace volume.
- Causing readiness flapping when a dependency has variable latency.
- Creating circular dependencies when service A checks service B and B checks A.

### 26.1. Readiness Flapping

Example:

```text
12:00:00 UP
12:00:05 DOWN
12:00:10 UP
12:00:15 DOWN
```

Load balancers may keep adding and removing instances, making traffic oscillate.

Consider:

- Sensible probe thresholds.
- Bounded timeouts and retries.
- Hysteresis in state evaluation if business logic warrants it.
- Windowed state measurement.

Do not “fix” flapping by always returning UP. That hides outages rather than reducing measurement noise.

### 26.2. Health Endpoints Must Tolerate Missing Dependencies

A health endpoint sharing an exhausted database connection pool can time out. That may be an appropriate readiness signal, yet you still must distinguish:

- App overloaded to the point it cannot handle any request.
- Health check designed too expensively.
- External dependency failing while the app can still serve other flows.

Readiness design must match actual serving capacity.

## 27. Health Endpoints and Information Security

Health endpoints are an HTTP surface that must be managed.

### 27.1. Avoid Leaking Unnecessary Details

An overly detailed health response can reveal:

- Database name or type.
- Internal hostnames.
- Topology information.
- Dependency error messages.
- Infrastructure components in use.

Prefer serving minimal status to probe callers and restricting diagnostic details to protected internal endpoints/systems.

### 27.2. 401/403 Does Not Automatically Mean the App Is Dead

If Kubernetes probes lack credentials while the endpoint demands authentication, probes can fail even though the application works.

Align probe paths and access policies consistently:

- Open enough for orchestrators that must call them.
- Not unnecessarily exposed to the Internet.
- Not leaking sensitive infrastructure state.

### 27.3. Avoid Logging Secrets While Debugging Health

When a health indicator hits a connection error, never log raw connection strings containing passwords, access tokens, or unvetted exception messages.

Log dependency type, failure code, and appropriate correlation info:

```text
event=health.dependency.failed
dependency=database
failureCode=CONNECTION_TIMEOUT
```

Retention and access permissions for these logs must still follow operational policies.

## 28. Complete Example: Startup Log, Readiness, and API With Wrong Results

Suppose the Orders API reports:

```text
Spring Boot startup -> success
Catalog warm-up ------> completed
Readiness probe ------> UP
GET /api/prices ------> 200
```

Yet the pricing code does:

```java
public BigDecimal calculate(
        BigDecimal unitPrice,
        int quantity) {
    return unitPrice.add(
            BigDecimal.valueOf(quantity)
    );
}
```

This bug violates none of the liveness or readiness conditions being checked.

### 28.1. Which Signals Catch It?

| Check | Can Catch Add-Instead-of-Multiply Bug? |
| --- | --- |
| Startup log | No |
| `ApplicationReadyEvent` | No |
| `/actuator/health` | No, unless custom health intentionally checks that invariant |
| Database health | No |
| HTTP status-only check | No if API returns 200 |
| Unit test with expected total | Yes |
| Integration/E2E test with expected total | Yes |
| Synthetic with data and expected result | Yes, if test exercises the buggy logic |
| Business invariant monitor | Possibly, if anomalies are defined and observed |

### 28.2. Do Not Stuff Pricing Unit Tests Into Liveness

Putting all unit tests into liveness is inappropriate:

- Liveness is called frequently.
- Failing liveness can restart the process.
- A pricing bug in code will not be fixed by a restart.
- Code bugs affect all instances, causing restart loops.

The right solution is catching bugs via tests and deployment checks; if detected at runtime, roll back or toggle off the feature per process.

### 28.3. Readiness Should Reflect Only Ability to Serve

If a dependency or config dataset renders an instance **temporarily unable to serve safely**, readiness can refuse traffic.

However, when deployed code has a logic bug across every instance, universal readiness failure is not a complete recovery strategy. Find the root cause and ship a fix or roll back.

## 29. Building a “Suite of Evidence” Instead of One Green Light

On operational dashboards, display signals with distinct scopes:

```text
Deployment: order-api v2.4

Process:
  8/8 instances running

Startup:
  8 instances reached ready event

Probes:
  8/8 liveness passing
  8/8 readiness passing

Service SLIs:
  checkout success rate = 98.1%
  checkout p99 = 6.4s

Functional checks:
  catalog synthetic = passing
  checkout synthetic = failing
```

These numbers are **illustrative only**, not from a real system.

In this situation, the right conclusion is not “the app is healthy because 8/8 health are UP.” Checkout is clearly degrading and needs attention.

### 29.1. Separating Conclusions by Signal

| Signal | Valid Conclusion |
| --- | --- |
| 8/8 processes running | Processes currently exist |
| 8/8 ready events | Startup reached the ready milestone in recorded launches |
| 8/8 readiness UP | Current readiness conditions pass |
| Checkout success 98.1% | By SLI definition, roughly 1.9% are failing |
| Checkout synthetic fails | Specific synthetic journey failed expected criteria |

These conclusions do not contradict each other. They show that different system layers are in different states.

### 29.2. Do Not Show Only Current State

A good dashboard also shows:

- Time-series graphs.
- Comparisons with pre-deployment baselines.
- Grouping by version, zone, or tenant where relevant.
- Rollout timestamp markers.
- Correlation between errors, latency, and dependency incidents.

This reduces the chance a brief outage is masked by an UP status at the moment you open the dashboard.

## 30. How to Investigate When Startup Logs Succeed Yet Users Report Errors

A practical workflow:

### Step 1 — Confirm Scope

- Which endpoint are users hitting?
- Does the error hit all requests or a specific group?
- Does it correlate with a tenant, role, region, or version?
- Is there a timestamp, request ID, or trace ID?

Never ask users for passwords, OTPs, or access tokens.

### Step 2 — Check Runtime State

- Is the process/pod currently running?
- Is it restarting continuously?
- What are liveness/readiness for the exact instance?
- Did the Pod become ready before or after errors began?

### Step 3 — Check SLIs for the Affected Route

- Are 5xx rates or failure codes rising?
- Did p95/p99 latency shift?
- Did traffic volume change?
- Is a dependency timing out or exhausting connection pools?

### Step 4 — Inspect Correlated Traces and Logs

Locate a specific request and check:

- Which services the request traversed.
- Which span failed or took excessive time.
- What failure code was logged.
- Whether retries or circuit breakers triggered.

Avoid dumping raw requests or responses containing personal data.

### Step 5 — Verify Correctness

If HTTP returns 200 with wrong results:

- Compare against business invariants or expected results.
- Inspect data, feature flags, schemas, and versions.
- Create a reproducible test with controlled data.
- Assess blast radius on persisted data.

### Step 6 — Choose Recovery Action

- Restart the instance if the cause is a process state recoverable via restart.
- Temporarily drain traffic if the instance cannot serve.
- Roll back deployment if the bug lives in new code/config.
- Restore dependencies or adjust resources for infrastructure faults.
- Repair data under a dedicated procedure if correctness was impacted.

Never restart by default just because a dashboard shows an error. Actions must fit the root cause.

## 31. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| “`Started ...` appeared so the app is ready.” | Startup log can precede runners and the ready event |
| “Yesterday's startup log proves the app is alive now.” | Logs reflect only the moment they were written |
| “`/health` returning 200 means every API works.” | Health checks only configured contributors |
| “Readiness UP proves payments work.” | Readiness is a traffic-routing decision, not E2E business proof |
| “Database UP guarantees CRUD succeeds.” | Pings do not check permissions, schemas, transactions, or real queries |
| “Liveness should check every dependency to be thorough.” | Can trigger restart storms when shared dependencies fail |
| “Readiness DOWN always requires restarting the process.” | Unready is normally for draining traffic, not restarting |
| “Fast health endpoint means fast APIs.” | Health routes have different workloads than APIs |
| “One passing synthetic means zero bugs.” | Synthetics cover only select inputs and moments |
| “HTTP 200 equals accurate business output.” | Bodies can still violate contracts or business invariants |
| “Management port UP means application port UP.” | Two connectors can fail independently |
| “One healthy pod means the whole deployment is healthy.” | Other replicas/zones/versions can be failing |
| “`ApplicationReadyEvent` waits for all async tasks.” | Runners can submit tasks and exit early |
| “Letting health checks call full real workflows is best.” | Wastes resources and risks side effects |
| “Readiness must always depend on the database.” | Depends on serving, fallback, and recovery strategy |
| “Metrics replace all tests.” | Metrics show observed behavior; tests verify expected invariants |
| “Completed trace means right result.” | Traces may be unaware of business invariants |
| “Health UP is enough to ramp rollout to 100%.” | Monitor SLIs and synthetics for the new version |

## 32. Hands-On Exercises

### Exercise 1 — Classifying Signals

Given these signals:

1. JVM process exists.
2. `Started ...` log appeared.
3. `/actuator/health/liveness` UP.
4. `/actuator/health/readiness` UP.
5. `POST /api/orders` returns 201.
6. A test order has the right total amount.
7. Checkout success rate is 99.9% over 24 hours.

Classify them under process, startup, readiness, API availability, correctness, and reliability. State the limitation of each signal.

### Exercise 2 — Runner Fails After Startup Log

Create an `ApplicationRunner` that throws an unhandled `IllegalStateException`.

Observe logs and lifecycle events in a test project. Explain why you can see the startup log yet no ready event.

### Exercise 3 — Actuator Health

Add Spring Boot Actuator and enable probes locally:

```properties
management.endpoint.health.probes.enabled=true
```

Observe:

```text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
```

Explain why those endpoints can return different results.

### Exercise 4 — Custom Warm-Up Indicator

Create `CatalogWarmupState`, a runner, and `CatalogWarmupHealthIndicator`. Configure the readiness group to include `catalogWarmup`.

Explain the criteria for transitioning from DOWN to UP and what happens if the warm-up task throws an exception.

### Exercise 5 — Async Warm-Up

Modify the runner to submit warm-up to an executor and return immediately.

Predict when `ApplicationReadyEvent` fires and what the custom warm-up indicator's state could be. Design a readiness gate to avoid accepting traffic too early.

### Exercise 6 — Dependency Ping Differs From CRUD

Suppose datasource health is UP yet the order-writing API fails because the database user has only `SELECT` permission.

Determine:

- Which check passed?
- Which check was missing?
- Should a real write statement be added to liveness?
- Which test or synthetic would catch this safely?

### Exercise 7 — Readiness and Database Outage

A deployment has 20 replicas sharing one database. Design a liveness/readiness policy for a 30-second database disconnection.

Analyze restart-storm risk, degraded response options, and error-rate alerting choices.

### Exercise 8 — Separate Management Port

Run Actuator on a management port different from the application port.

Simulate the main app's HTTP path failing while management health remains UP. Propose how to probe on the traffic-serving path based on your Spring Boot version's capabilities.

### Exercise 9 — Kubernetes Probes

Write `startupProbe`, `livenessProbe`, and `readinessProbe` for a service with slow startup.

Explain:

- Why `startupProbe` prevents early liveness restarts.
- Why `readinessProbe` has a distinct role.
- What happens when probes time out or hit a security filter returning 401.

### Exercise 10 — HTTP 200 Yet Wrong Price Calculation

Create a `PriceCalculator` and test with unit price 125000, quantity 3, expected total 375000.

Break the logic from multiply to add and observe the unit test catching the bug. Explain why Actuator health misses it.

### Exercise 11 — Synthetic Monitoring

Design a synthetic check for a catalog endpoint using stable test data:

- Expected HTTP status.
- Response schema.
- Key fields and expected values.
- Latency threshold.
- Side-effect-free contract.

State the limitations of that synthetic and when it fails to represent real users.

### Exercise 12 — Computing Success Rate

In a measurement window, a service receives 10,000 eligible requests, of which 9,850 complete successfully.

Compute the success rate and compare against a hypothetical 99.9% target. Explain why readiness UP during the same window does not contradict the breached SLO.

### Exercise 13 — Canary Rollout

Suppose version A has a 0.2% error rate while newly deployed version B has a 7% error rate, yet both report readiness UP.

Describe a sensible rollout decision, additional signals to check, and stop/rollback conditions per policy.

### Exercise 14 — Multi-Layered Dashboard

Design a dashboard containing:

- Replica count / restart count.
- Liveness/readiness status.
- API request rate / error rate / latency.
- Synthetic test results.
- Business outcome metrics.
- Deployment version and rollout timestamps.

Explain a scenario where the dashboard shows green health yet red business metrics.

### Exercise 15 — Diagnosing User-Reported Errors

A user reports “unable to place order” and provides a request ID.

Lay out the investigation order from runtime, probes, metrics, logs, and traces down to correctness tests. Specify what information should never be requested from the user.

### Exercise 16 — Writing a Readiness Definition

For a hypothetical service, write a short specification covering:

- Mandatory conditions before accepting traffic.
- Essential vs. non-essential dependencies.
- Conditions for transitioning to refusing.
- Rules for restoring accepting state.
- Check intervals and probe load limits.
- How operators identify causes when probes fail.

Do not use “everything works fine” as a readiness definition without measurable criteria.

## 33. Summary

**Startup logs** show the application reached a milestone during boot. **Liveness** helps decide whether an instance needs a restart. **Readiness** indicates whether an instance should enter traffic rotation. **Health checks** evaluate only the conditions and contributors the system defined.

None of those signals alone proves every endpoint, role, dataset, and business rule is right. A database health `UP` does not guarantee write transactions succeed; an HTTP 200 does not guarantee accurate responses; a ready event does not mean async tasks finished; a green probe does not reflect reliability over time.

Use Actuator and Kubernetes probes for operational decisions, tests and synthetic checks for critical behaviors, metrics/SLIs/SLOs to measure user experience and reliability, and tracing/logging to find root causes. Pick each signal for the exact question it answers, and avoid health checks that cause side effects or add load during incidents.

**Key takeaway:** “The application is running” is a statement about state; “the application works properly” requires evidence of behavior, outcomes, and service quality matching the business contract. Only by combining that evidence can a team evaluate a Spring Boot system reliably without equating a startup log line or an `UP` health check with total success.
