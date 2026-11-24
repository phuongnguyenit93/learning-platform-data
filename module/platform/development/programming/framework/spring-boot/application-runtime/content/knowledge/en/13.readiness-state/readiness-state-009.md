# Why External Service Failures Should Not Fail Liveness by Default

A Spring Boot application can **continue operating properly as a process** even when a database, cache, message broker, or HTTP API it calls experiences an outage. In that situation, the application can return controlled errors, retry, trip a circuit breaker, keep serving unaffected features, or wait for the dependency to recover. If every dependency failure caused the **liveness probe** to fail, Kubernetes could repeatedly restart containers that are not actually broken. The result is usually more disruption, not better self-healing.

Design principle:

> **Liveness answers: "Is this process broken to the point that it needs a restart to recover?" Readiness answers: "Should this instance receive new traffic right now?" The state of an external dependency does not automatically answer either question.**

This lesson focuses on Spring Boot Application Runtime, `ApplicationAvailability`, Spring Boot Actuator, and Kubernetes probes. Examples use **Java 17+ and Spring Boot 3.3.x**; the same liveness/readiness selection principles apply to similar container platforms.

## 1. Three Probe Types Serve Different Purposes

Kubernetes typically uses three probe types:

| Probe | Core Question | What Kubernetes Usually Does When Failures Reach Threshold |
|---|---|---|
| **Liveness** | Is this container still capable of working or self-recovering? | **Restarts the container** according to the Pod's policy. |
| **Readiness** | Is this instance currently eligible to receive new requests? | Marks the Pod **NotReady**, removing it from traffic-serving endpoints of the corresponding Service; does not restart solely for readiness failure. |
| **Startup** | Has the application finished starting up enough for regular checks to begin? | Grants startup a dedicated window; if consecutive failures exceed the threshold, the container is restarted. While the startup probe has not succeeded yet, Kubernetes does not run liveness/readiness probes. |

Do not treat all three probes as meaning "every dependency must be UP". Kubernetes's operational responses **differ**; therefore, an ill-suited check can turn a transient error into a restart loop.

Two contrasting examples:

- **Liveness failure may be warranted:** a severe deadlock prevents the process from making progress and it cannot self-recover. A restart can resolve that internal condition.
- **Liveness should not fail by default:** the database times out for 30 seconds while the JVM still accepts requests, returns controlled errors, updates metrics, and will reconnect automatically once the database recovers.

Liveness should be **cheap, fast, and reflect internal state**, not an integration test continuously calling multiple network services.

## 2. Consequences of Tying Liveness to an External Database or API

Suppose three Spring Boot Pods share one database:

~~~text
                Kubernetes Service
                  /     |     \
                Pod A  Pod B  Pod C
                  \     |     /
                  Database (shared)
~~~

If every liveness probe opens a connection to the database and reports failure when the database errors, the chain reaction can look like this:

~~~mermaid
flowchart TD
    A["Shared database experiences a brief outage"] --> B["Probes on Pods A/B/C all fail"]
    B --> C["Kubernetes restarts multiple containers"]
    C --> D["Healthy serving instances are stopped"]
    D --> E["Rebuild caches, create connection pools, run initialization"]
    E --> F["Traffic and connections surge onto the dependency"]
    F --> G["Risk of cascading failure / restart loop"]
~~~

The fundamental issue is that **restarting the application does not fix an external database**. Even once the database recovers, having a whole fleet of Pods simultaneously build connection pools, run startup queries, and warm caches can put fresh pressure on the dependency.

Common impacts:

1. **Loss of capacity:** Pods that were still returning valid responses for endpoints not needing the database also get restarted.
2. **Request disruption:** connections and in-flight requests may be cut off, depending on graceful shutdown and timeouts.
3. **Increased dependency pressure:** multiple instances simultaneously reconnect, refresh tokens, rebuild caches, or re-subscribe to brokers.
4. **Loss of retry/fallback benefits:** resilience logic inside the app gets no time to work.
5. **Harder diagnostics:** climbing restart counts obscure the real root cause in the external database/API.
6. **Blast radius spreads:** while some Pods are restarting, load piles onto the remaining Pods.

This is a form of **cascading failure** or "thundering herd". That is why Spring Boot recommends not putting external system checks into the liveness group by default.

## 3. How Does Spring Boot Represent Liveness and Readiness?

Spring Boot provides the `ApplicationAvailability` abstraction, with two key state groups:

| State | Typical Values | Meaning |
|---|---|---|
| `LivenessState` | `CORRECT`, `BROKEN` | Whether internal state is sound enough for the process to keep running/self-recover. |
| `ReadinessState` | `ACCEPTING_TRAFFIC`, `REFUSING_TRAFFIC` | Whether the instance is ready to accept new traffic. |

Spring Boot manages availability transitions across startup and shutdown. A simplified view:

~~~text
Initial startup:
    liveness  = BROKEN
    readiness = REFUSING_TRAFFIC
Once context has initialized sufficiently:
    liveness  = CORRECT
    readiness = REFUSING_TRAFFIC (runners may still be executing)
After startup completes normally:
    liveness  = CORRECT
    readiness = ACCEPTING_TRAFFIC
When controlled shutdown begins:
    readiness = REFUSING_TRAFFIC
~~~

These milestones describe internal state; **HTTP endpoints may not exist yet** during certain startup phases or may already be stopped during shutdown. Do not assume an endpoint is always reachable simply because state is set in memory.

With `spring-boot-starter-actuator`, Actuator can expose these states via:

- `LivenessStateHealthIndicator` in the `liveness` health group.
- `ReadinessStateHealthIndicator` in the `readiness` health group.

Typical paths:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

When running inside Kubernetes, Spring Boot enables probe health groups automatically upon detecting the environment. When running **locally outside Kubernetes**, you can enable them explicitly with:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

**Key point:** By default, Spring Boot **does not automatically add** `db`, `redis`, `diskSpace`, or other health contributors to the liveness/readiness groups merely because they appear on the general health endpoint.

Therefore:

- `/actuator/health` may report `DOWN` due to a failing database health indicator.
- `/actuator/health/liveness` can still be `UP` because internal state remains `CORRECT`.
- `/actuator/health/readiness` can still be `UP` if the app remains `ACCEPTING_TRAFFIC` and no dependency check was added to readiness.

Those three results **do not contradict one another**; they answer different questions.

## 4. When a Dependency Fails, Which State Should Transition?

There is no universal "dependency DOWN = readiness DOWN" rule for every service. Distinguish **essential dependencies** from **gracefully degradable dependencies**.

| Scenario | Liveness | What Readiness Should Consider | Application Handling |
|---|---|---|---|
| Email-sending API fails, main APIs still work | Keep passing | Usually keep ready | Queue/retry emails, emit metrics/alerts. |
| Redis cache fails, app can fall back to database | Keep passing | Can stay ready if still handling load well | Circuit breaker, rate limit, fallback, and monitor. |
| Critical database unreachable, yet only one feature group needs it | Keep passing | Depends on traffic, routing, and partial serving capability | Return controlled errors for affected features without necessarily pulling the whole Pod. |
| A dependency is unusable **only on Pod A** due to local credentials or config | Keep passing if process can recover | May mark Pod A NotReady | Isolate faulty instance, keep other Pods serving. |
| All instances cannot reach a shared database | Keep passing | **Weigh carefully**: pulling all Pods can leave the Service with zero endpoints | Retries, circuit breaker, fallback; decide per API contract and orchestration. |
| Unrecoverable internal deadlock, app stops making progress | May fail if reliably detected | Usually unready as well | Restart can help when the fault belongs to the instance. |

For a shared dependency checked by **every Pod** in readiness: if all report NotReady, the Service may have **zero endpoints left to accept connections**. The application then loses the chance to serve independent operations or return controlled business errors, and gateway/ingress/load balancer behavior can become unpredictable.

So ask:

1. Does the dependency failure break **every request** or only one feature?
2. Does the error affect **one instance** or **all instances**?
3. Are there fallbacks, caches, retries, queues, circuit breakers, or a degraded mode?
4. When removing an instance from traffic, are there other instances actually better able to serve?
5. Does restarting the instance positively address the root cause or just add load?

A good choice may be to **keep both liveness and readiness passing**, while affected business endpoints return appropriate errors and monitoring raises alerts independently.

## 5. Runnable Spring Boot Example: Upstream Fails, Liveness Stays UP

The following example demonstrates **the difference between the two states** without calling an external database. We build a REST endpoint enabled only under the `demo` profile to **simulate** an essential dependency failure: transitioning readiness to `REFUSING_TRAFFIC`, while **not** changing liveness.

Setup uses **Spring Boot 3.3.5, Java 17, Spring Web, and Actuator**.

### Project Structure

~~~text
probe-demo/
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── com/example/probe/
        │       └── DependencyProbeApplication.java
        └── resources/
            └── application.properties
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

springBoot {
    mainClass = 'com.example.probe.DependencyProbeApplication'
}
~~~

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=dependency-probe-demo
server.port=8080

management.endpoints.web.exposure.include=health
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
management.endpoint.health.show-details=never
~~~

Here:

- `probes.enabled=true` ensures liveness/readiness groups are enabled even when running locally outside Kubernetes.
- `add-additional-paths=true` exposes `/livez` and `/readyz` on the **main application port**, alongside the Actuator paths.
- We intentionally **do not** add external service health checks to the liveness group.
- `show-details=never` avoids publicly exposing internal health indicator details.

Create the complete Java file `src/main/java/com/example/probe/DependencyProbeApplication.java`:

~~~java
package com.example.probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DependencyProbeApplication {

    public static void main(String[] args) {
        SpringApplication.run(DependencyProbeApplication.class, args);
    }

    // For demo use only; do not expose readiness-changing APIs in production.
    @Profile("demo")
    @RestController
    public static class SimulationController {

        private final ApplicationEventPublisher events;

        public SimulationController(ApplicationEventPublisher events) {
            this.events = events;
        }

        @PostMapping("/demo/upstream/down")
        public String simulateUpstreamDown() {
            AvailabilityChangeEvent.publish(
                    events, ReadinessState.REFUSING_TRAFFIC);
            return "readiness=REFUSING_TRAFFIC";
        }

        @PostMapping("/demo/upstream/up")
        public String simulateUpstreamRecovered() {
            AvailabilityChangeEvent.publish(
                    events, ReadinessState.ACCEPTING_TRAFFIC);
            return "readiness=ACCEPTING_TRAFFIC";
        }
    }
}
~~~

Reason for choosing `ApplicationEventPublisher` and `AvailabilityChangeEvent.publish(...)`: Spring Boot listens for availability change events and updates the state that health indicators use to answer probes. We **only** publish `ReadinessState`; the application is not flagged `LivenessState.BROKEN`.

Run from the project directory containing the Gradle wrapper, after generating a wrapper compatible with the plugin:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=demo'
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=demo"
~~~

Without a Gradle wrapper, install Gradle or generate the wrapper in the project first. This Java code depends on Spring Boot, so it **cannot** be compiled with a standalone `javac` command lacking the classpath.

### Verifying via HTTP

Wait for the application to finish starting, then call:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Under a successful startup with no other customization, both normally return:

~~~text
HTTP 200
{"status":"UP"}
~~~

Next, simulate an unavailable upstream:

~~~bash
curl -i -X POST http://localhost:8080/demo/upstream/down
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
~~~

Expected observations:

| Request | Expected HTTP Status | Main Body |
|---|---|---|
| `POST /demo/upstream/down` | `200` | `readiness=REFUSING_TRAFFIC` |
| `GET /actuator/health/readiness` | **`503`** | `{"status":"OUT_OF_SERVICE"}` |
| `GET /actuator/health/liveness` | **`200`** | `{"status":"UP"}` |

These numbers are the **expected program results under the given configuration**; exact HTTP headers, timestamps, and field ordering are not fixed here. By default, Spring Boot maps health status `OUT_OF_SERVICE` to HTTP 503 and `UP` to HTTP 200.

Let the upstream "recover":

~~~bash
curl -i -X POST http://localhost:8080/demo/upstream/up
curl -i http://localhost:8080/actuator/health/readiness
~~~

Readiness returns to `UP`, HTTP 200. **No JVM restart occurred** during this simulation.

To observe on the main application port instead of the Actuator path, you can also call:

~~~text
GET /livez
GET /readyz
~~~

These two paths are created by `management.endpoint.health.probes.add-additional-paths=true`.

**Important demo limitation:** `/demo/upstream/down` only **publishes a simulated event**; it does not check a network or real database. Do not expose a public endpoint allowing arbitrary clients to alter production availability. In real systems, state-tracking logic must live in a protected internal component with debounce/hysteresis and a proper recovery strategy.

## 6. When to Add External Checks to the Readiness Group?

Spring Boot Actuator allows configuring health groups. If a dependency genuinely determines **which instances can serve traffic**, you can add that health contributor to **readiness**, for example:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,db
~~~

This configuration is valid **only when** the application actually has a health contributor with ID `db`, such as when Spring Boot activates `DataSourceHealthIndicator` for an appropriate datasource. Without a `db` contributor, referencing a nonexistent name can make the health group configuration invalid. Do not copy this setting into the section 5 demo, because the demo declares no database.

Do not add the same thing to liveness:

~~~properties
# Should not be done as a general default:
management.endpoint.health.group.liveness.include=livenessState,db
~~~

The line above illustrates **a choice to avoid** for external dependencies. A database failure will affect the liveness health group and can lead Kubernetes to restart containers that are completely capable of self-recovering.

### Choosing Readiness by Dependency Nature

A health contributor can be:

- **Per-instance:** configuration keys, credentials, local connections, or critical local cache data on one Pod. Including it in readiness can make sense so a faulty Pod is pulled from traffic while other Pods remain healthy.
- **Shared across all instances:** a shared database or API. Including it in readiness can make **every** Pod NotReady simultaneously, leaving the Service with no endpoints. Weigh this carefully against keeping Pods alive and handling errors in the app/caller layer.
- **Optional:** analytics, email, or a cache with fallback. Including it in readiness usually causes broader disruption than the real business impact warrants.

If you write a custom `HealthIndicator` representing a dependency, avoid making slow or expensive remote calls on **every probe**. Kubelet calls readiness frequently; good checks should use short timeouts, evaluate sensible local/cached state, and avoid clogging request handling when the dependency is overloaded.

Health contributors **outside** liveness/readiness can still be used on the general health endpoint or dedicated monitoring health groups. Separate **dependency incident alerting** from the decision to **restart a container**.

## 7. Sensible Kubernetes Probe Configuration Example

The following YAML snippet is **a container configuration section inside a Pod/Deployment**, not a complete Deployment manifest:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 30

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
~~~

Explanation:

- `startupProbe` targeting the liveness endpoint grants the process a dedicated startup window before Kubernetes begins using liveness/readiness. For example, `failureThreshold=30` and `periodSeconds=10` provide tolerance measured in probe intervals; exact restart timing also depends on timeouts and kubelet scheduling.
- `livenessProbe` reflects only internal state; external failures should not be a default reason to fail.
- `readinessProbe` indicates whether the Pod should accept new traffic. On failure, Kubernetes keeps the Pod running, keeps probing, and can automatically return the Pod to the Service once probes pass.
- Both use `/livez` and `/readyz` on the **main HTTP server** port instead of a separate management port.

These thresholds are **starting examples**, not optimal values for every service. Measure actual startup duration, request processing latency, application timeouts, and load capacity to tune them. Overly sensitive probes can mark failures due to GC pauses, CPU contention, or brief traffic spikes.

### Why Be Cautious with a Separate Management Port?

If `management.server.port` differs from the application port, Actuator may use separate web infrastructure. A probe on the management port can keep returning success **even while the main server is not accepting connections**. Spring Boot provides `management.endpoint.health.probes.add-additional-paths=true` to expose `/livez` and `/readyz` on the main application port.

Running probes via the main port does not mean liveness should call the database. It simply verifies the application's HTTP path can answer probes without entangling external system dependencies.

## 8. Distinguishing Unrecoverable Faults from Transient Errors

A key engineering question is: **does restarting the instance stand a chance of improving the situation?**

| Fault | Does Restart Usually Fix the Root Cause? | Appropriate Response to Consider |
|---|---|---|
| Shared database loses network | No | Retries with backoff, circuit breaker, controlled business errors, alerts. |
| External payment API returns transient 503 | No | Timeouts, bounded retries, queue/degraded mode, alerts. |
| Redis cache fails while app has fallback | Unnecessary | Fallback, rate limiting, and protecting the backing database. |
| Permanently misconfigured credentials | Restarting does not fix bad config | Error/NotReady as appropriate; fix secret/config and perform a controlled rollout. |
| Real JVM/application deadlock with no recovery path | Possibly | Liveness fail/restart if reliably detected; simultaneously find and fix the bug. |
| Severe memory leak, instance can no longer operate | Restart may temporarily relieve symptoms | Policy-driven restart; mandatory leak and capacity investigation. |
| Short-term instance overload | Restart may make things worse | Backpressure, autoscaling, concurrency limits, readiness when needed. |

Do not conclude "DB failed so the Pod is dead" just because a business route returns HTTP 500 or 503. Statuses from **business endpoints** differ from the status of the **liveness endpoint**. Even the aggregate health endpoint reporting `DOWN` does not mean the liveness group should report `DOWN`.

## 9. Circuit Breakers, Retries, and Degraded Mode

The goal of resilience is to let the application **survive and recover** when a dependency fails, rather than being restarted repeatedly.

Commonly combined techniques:

1. **Explicit timeouts:** upstream requests must finish within a bounded time, never tying up threads indefinitely.
2. **Controlled retries:** only retry safe/idempotent operations or use deduplication; apply backoff and jitter so Pods do not retry in lockstep.
3. **Circuit breaker:** when an upstream fails repeatedly, temporarily stop sending more requests to protect the system and return a fast fallback/error.
4. **Bulkheads and concurrency limits:** one failing upstream must not exhaust the entire application's thread pool.
5. **Fallback/degraded mode:** serve cached data, queue work, or disable secondary features; do not necessarily mark the whole Pod NotReady.
6. **Metrics, tracing, and alerts:** surface upstream error rates to operators without triggering erroneous restarts.

For instance, an email-sending endpoint can enqueue messages when the email provider is failing. The system can still accept requests successfully if the business contract allows async processing. Wiring the email provider into liveness turns a transient fault into unnecessary service downtime.

Conversely, if an application's sole responsibility is executing direct database transactions and it cannot serve any request while disconnected, readiness may need to reflect that state. **Even then, liveness should still not fail solely because the database failed.**

## 10. Failing Readiness Is Not Always the Right Answer Either

Readiness is normally less destructive than liveness because **it does not restart**, yet you should not unconditionally mark NotReady for every external error.

One example: 10 Pods read from the same database. When the database suffers a global outage and every readiness health group directly depends on `db`, all 10 Pods can turn NotReady. The Kubernetes Service ends up with zero ready endpoints, even if the application could still serve caches, return clear error messages, or handle requests that do not touch the database.

There are two design directions, depending on needs:

- **Include the dependency in readiness:** appropriate when pulling a faulty instance steers traffic to **another instance that is genuinely healthier**, or when every request to that instance strictly requires the dependency.
- **Do not include shared dependencies in readiness:** appropriate when every instance suffers the same outage, when fallback/degraded mode exists, or when keeping the service reachable to return controlled errors is better.

If you need to distinguish multiple availability levels, use **dedicated health groups for monitoring** and per-feature metrics instead of collapsing every error into a single liveness/readiness boolean.

Test actual gateway, load balancer, and Service behavior: when every endpoint is NotReady, clients may encounter connection failures instead of receiving a JSON 503 from the app. Exact results depend on network topology and ingress controllers.

## 11. Startup Probes Are Not for Checking External Services Forever

A startup probe exists to **allow slow application startup** without being killed prematurely by the liveness probe. For example, an app needs to load a model, build an internal cache, or warm up within a measurable window.

If the startup probe depends on an external database that is down, it can still cause repeated restarts. When designing:

- The startup probe should reflect **initialization milestones of the process itself**, avoiding locking startup to a non-mandatory external service.
- Readiness can stay `REFUSING_TRAFFIC` until the application can truly accept requests.
- Only after the startup probe passes does Kubernetes start regular liveness and readiness probes.

Do not use startup probes to turn prolonged external outages into restart triggers unless there is a clear technical contract proving restarting the instance helps recovery.

## 12. What Should a Liveness Endpoint Check?

Appropriate criteria:

- The process and minimal HTTP handling still respond within a reasonable threshold.
- `ApplicationAvailability.getLivenessState()` is `CORRECT`.
- A reliably detected and proven **unrecoverable internal fault** may transition `LivenessState.BROKEN`.

Things that **should not belong to liveness by default**:

- Opening new database connections.
- Calling an upstream's HTTP health endpoint.
- Querying a message broker/Redis to verify every dependency is online.
- Testing a specific business feature spanning multiple services.
- Requiring caches to be fully warm or background jobs to finish.

If a custom liveness handler runs a blocking network call and the upstream hangs, the handler can time out; Kubernetes will assume the JVM is broken and restart it. Therefore, **liveness logic should have as few external dependencies and be as lightweight as possible**.

When you truly need to flag an unrecoverable internal fault in the application itself, you can proactively publish `AvailabilityChangeEvent` for `LivenessState.BROKEN` via Spring Boot's mechanism. Yet this is a **serious decision**: verify that the signal truly warrants a Kubernetes restart. Do not use `BROKEN` as a catch-all label for every exception.

## 13. Observability Must Be Separated from Restart Decisions

Probes have a relatively narrow orchestration duty, whereas observing system health requires multiple signals:

| Signal | Example | Purpose |
|---|---|---|
| Upstream metrics | Timeout rate, connection errors, circuit breaker state, latency | Detect dependency outages. |
| Dedicated health groups | Database, cache, broker, external API | Investigate/monitor dependencies. |
| Liveness | Internal state of the process | Decide restarts when necessary. |
| Readiness | Instance's ability to accept new requests | Coordinate traffic routing. |
| Logs and traces | Root cause, request correlation | Debugging and fault analysis. |
| Kubernetes events | Probe failures, restart count, NotReady | Assess platform behavior. |

A system might report:

~~~text
Liveness: UP
Readiness: UP
Payment API error rate: 100%
Circuit breaker: OPEN
~~~

This can be the **right model** if other features still serve normally and payment is not a mandatory dependency for every request. Monitoring must still alert on payment errors; there is no need to force liveness DOWN just to generate an alert.

You might also see:

~~~text
Liveness: UP
Readiness: OUT_OF_SERVICE
External dependency: DOWN
~~~

This can be the **right model** when the instance should not take new requests yet can still self-recover. Kubernetes should temporarily pull traffic without restarting it.

## 14. Common Design Mistakes

**Mistake 1 — Pointing `livenessProbe` at general `/actuator/health`.**

General health can include datasource, Redis, disk space, and other contributors. If one dependency fails and drags general health down, kubelet may restart a healthy container. Use **`/actuator/health/liveness`** or `/livez` for its intended purpose.

**Mistake 2 — Adding `db` to the liveness group.**

A database error gets interpreted as "the application should restart". That is not a database recovery mechanism. If a dependency affects serving ability, consider readiness based on real need instead of automatically tying it to liveness.

**Mistake 3 — Calling `System.exit(...)` upon seeing readiness DOWN.**

This defeats the distinction between readiness and liveness. NotReady lets a running Pod recover and return to traffic. `System.exit(...)` terminates the process, potentially causing unnecessary restarts.

**Mistake 4 — Making every upstream error mark the whole Pod NotReady.**

This can wipe out all endpoints during a shared outage or block features that still work. Assess fault scope, fallbacks, and routing.

**Mistake 5 — Health checks calling upstreams continuously without timeouts.**

Probes themselves can add load and trigger timeout loops right when the system is degraded. Consider local state, cached check results, short timeouts, and circuit breakers.

**Mistake 6 — Liveness and readiness hitting the same endpoint that returns DB status.**

Two probes with different consequences sharing one check condition. The result can be mass restarts instead of merely pausing traffic. Separate their semantics and paths.

**Mistake 7 — Forgetting startup probes for slow-starting applications.**

If liveness starts too early, the process can be restarted before HTTP endpoints exist. Use a startup probe when startup is genuinely long or highly variable.

**Mistake 8 — Assuming probing a separate management port suffices to check the main server.**

Not necessarily: the management HTTP stack can stay alive while the main port stops accepting connections. Spring Boot supports adding `/livez` and `/readyz` on the main port.

**Mistake 9 — Using probes as the sole alerting system.**

Probes serve lifecycle/traffic orchestration; broken dependencies need dedicated metrics, logs, traces, and alerts. Do not force liveness DOWN just so operators get notified.

**Mistake 10 — Exposing readiness-changing endpoints to external users.**

In the demo, the `demo` profile allows proactively toggling state for learning. Production must never publicly expose such APIs, as they could be abused to pull Pods out of traffic.

## 15. Pre-Deployment Verification Checklist

1. **Confirm purpose:** does liveness truly measure hard-to-recover internal faults; does readiness measure traffic-serving capability?
2. **Separate endpoints:** configure kubelet to use `/livez` and `/readyz` or matching Actuator health groups, not general health without evaluating contributors.
3. **Audit health contributors:** which dependencies were manually added to liveness/readiness? Why?
4. **Classify dependencies:** essential, optional, per-instance, or shared across all Pods?
5. **Controlled fault testing:** when disconnecting the database in staging, measure restart count, Ready state, business responses, retries, and connection pools.
6. **Observe recovery:** when the database recovers, do Pods automatically resume serving without restarting?
7. **Control probe cost:** measure probe latency, timeouts, frequency, thread usage, and dependency pressure.
8. **Assess all-Pods-NotReady state:** what do clients and gateways experience when the Service has zero endpoints?
9. **Ensure graceful shutdown:** when a restart or rollout is genuinely needed, the app must have time to drain traffic and finish in-flight requests.
10. **Set independent alerts:** DB/API outages must be observable via metrics/logs without forcing liveness to fail.

### Official Documentation

- Spring Boot — Actuator endpoints, *Kubernetes Probes* and *Checking External State With Kubernetes Probes*: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Application Availability and liveness/readiness state: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Kubernetes — *Liveness, Readiness, and Startup Probes*: https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Kubernetes — *Configure Liveness, Readiness and Startup Probes*: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

**Summary:** Failures in an external database, cache, broker, or API **do not mean the JVM/Spring Boot instance is broken**. Tying external failures to liveness causes Kubernetes to restart applications that could still self-recover, risking cascading outages. Reserve **liveness for unrecoverable internal faults**, use **readiness selectively** to coordinate traffic, and rely on **resilience + observability** to handle dependency failures within their true blast radius.
