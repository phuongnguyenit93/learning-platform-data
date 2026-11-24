# Startup Probes, Readiness, Liveness, and Boundaries with Actuator

Slow Spring Boot startups, Pods restarting in loops, or an application returning HTTP 200 on its health endpoint while core APIs fail are very common issues when deploying web services. Three Kubernetes concepts—**startup probe**, **readiness probe**, and **liveness probe**—answer **three different questions**. In Spring Boot, `ApplicationAvailability` and Spring Boot Actuator expose current availability states for kubelet to evaluate.

This lesson belongs to the **Application Deployment** topic of the Spring Boot web-runtime module. Examples use **Spring Boot 3.3.x, Java 17+, Spring MVC, Actuator, and Kubernetes**. It includes runnable Gradle/Java code, HTTP tests before/after warmup, tests transitioning readiness state, a Dockerfile, a Deployment manifest, troubleshooting, and a production checklist.

**Core principle:** **Actuator publishes state; kubelet/Kubernetes enforces restart or routing policies**. An HTTP 200 from a health endpoint does not prove all business transactions, databases, reverse proxies, or external user journeys work.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish startup, readiness, and liveness by purpose, cadence, and failure consequences.
- Explain why `startupProbe` holds off `readinessProbe` and `livenessProbe` until the first startup probe succeeds.
- Recognize **readiness fail → NotReady/remove traffic**, **liveness fail → restart**, **startup fail past threshold → restart**.
- Understand Spring Boot `ApplicationAvailability` and the `LivenessState`/`ReadinessState` enums.
- Distinguish `ApplicationStartedEvent` from `ApplicationReadyEvent`, especially during `ApplicationRunner` warmup.
- Enable the `/actuator/health/liveness` and `/actuator/health/readiness` health groups in Boot 3.3.
- Expose `/livez` and `/readyz` on the **main server port** when using a separate management port.
- Explain why **Actuator `/actuator/startup` is not a Kubernetes `startupProbe`**.
- Author and test a Deployment manifest with sensible failure thresholds, periods, and timeouts.
- Use `@SpringBootTest(RANDOM_PORT)` and `TestRestTemplate` to verify readiness transitions `200→503→200`.
- Set boundaries for DB/cache/broker health checks to avoid cascading restarts.
- Diagnose 404, 401, 503, connection refused, probe timeouts, `CrashLoopBackOff`, and rolling deployments.
- Separate health probes, business monitoring, tracing, SLOs, and graceful shutdown.

## 2. Three Questions and Three Kubernetes Actions

| Probe | Question | When failing enough times | When it runs |
| --- | --- | --- | --- |
| `startupProbe` | Has the container started enough to begin normal health monitoring? | Restarts container per policy | Runs from startup until **first success**, then stops |
| `readinessProbe` | Should this Pod receive new requests right now? | Marks Pod **NotReady**, updates Service endpoints; **does not restart solely for readiness** | Continuously after startup gate |
| `livenessProbe` | Is the process broken enough to warrant restarting? | Restarts container | Continuously after startup gate |

**There is no rule that all three probes must use three distinct URLs.** With Spring Boot, you can use `/livez` for both startup and liveness with different thresholds, and `/readyz` for readiness. When a `startupProbe` is configured, kubelet **does not run readiness/liveness until `startupProbe` succeeds**. Without `startupProbe`, readiness and liveness run on independent schedules without waiting for each other.

### 2.1. Memorable Examples

- JVM is loading classes and warming caches for 60 seconds: **startup** needs a long enough budget to prevent premature restarts.
- App is warming up a model, already accepting HTTP connections, yet not ready to serve user requests: **liveness** can be UP while **readiness** stays DOWN/`OUT_OF_SERVICE`.
- One Pod loses connectivity to a **Pod-local** resource and cannot take traffic: readiness can return 503 without needing a restart.
- Critical application threads hit an unrecoverable deadlock: this is a candidate for liveness failure/restart.
- Shared database goes down briefly: restarting every JVM **does not fix the database**, so do not put standard DB checks into liveness.

### 2.2. Readiness and Service Routing

When readiness fails, Kubernetes stops routing new Service traffic to that container/Pod under normal conditions. EndpointSlice/ingress/proxy updates propagate asynchronously—**not in a single atomic transaction**. Existing connections can stay open, and clients may still see resets or 503s during rollouts. Readiness alone does not guarantee zero-downtime without load balancer draining, client retries, and graceful shutdown.

### 2.3. When All Pods Become NotReady

If every instance turns NotReady due to a shared external dependency, the Service may have zero ready endpoints; clients may receive connection errors or ingresses may return 503 depending on implementation. Thus readiness design must consider cluster-wide impact, not just a single Pod.

## 3. Clear Boundaries Between Actuator, Kubernetes, and Spring Boot

```text
Kubernetes kubelet
   |
   | HTTP GET PodIP:8080/livez or /readyz
   v
Spring Boot main HTTP server
   |
   +-- /livez  --> Actuator liveness health group
   |                   |
   |             LivenessStateHealthIndicator
   |                   |
   +-- /readyz --> Actuator readiness health group
                       |
                 ReadinessStateHealthIndicator
                       |
                ApplicationAvailability
                       |
           Spring lifecycle / app decisions

kubelet receives HTTP status or timeout
   |
   +-- startup failure exceeds threshold  -> restart
   +-- liveness failure exceeds threshold -> restart
   +-- readiness failure                  -> NotReady
```

**Spring Boot `ApplicationAvailability`** is an interface providing availability states inside the JVM. Even without Actuator, Spring Boot manages this state; however, it **does not automatically expose HTTP Actuator health group routes** without Actuator and web support.

**Actuator** wires `HealthIndicator` and `HealthContributor` beans, aggregating them into `HealthEndpoint` and health groups. By default, `UP` maps to HTTP 200 and `DOWN`/`OUT_OF_SERVICE` map to HTTP 503. **Kubelet HTTP probes inspect status codes 200–399**, rather than parsing JSON bodies for `"status":"UP"`.

**Kubernetes** is what restarts containers or updates EndpointSlices/readiness conditions. Actuator does not call the Kubernetes API to delete/restart Pods just because liveness goes down.

### 3.1. What a Health Endpoint Does Not Prove by Itself

An HTTP 200 from `/livez` does not prove:

- Real users can reach the app through TLS/Ingress/CDN from the Internet.
- Controllers process payments with proper authorization and transactions.
- Every API route works.
- The database contains required data.
- A queue consumer is not stalled.
- Redis sessions work across all 5 replicas.
- Latency and error rates meet SLOs.
- In-flight client requests finish before Pod termination.

To verify those contracts, use integration tests, synthetic canary monitoring, metrics/tracing, and **targeted** domain checks—never shove everything into liveness.

## 4. ApplicationAvailability and the Spring Startup Lifecycle

Spring Boot 3.3 provides:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
```

Core states:

- `LivenessState.BROKEN`: the runtime is broken and assumed unable to self-recover; a restart may help.
- `LivenessState.CORRECT`: internal runtime is healthy.
- `ReadinessState.REFUSING_TRAFFIC`: temporarily should not accept new traffic.
- `ReadinessState.ACCEPTING_TRAFFIC`: ready to accept traffic.

### 4.1. Timeline in Spring Boot 3.3

| Stage | Liveness | Readiness | HTTP server |
| --- | --- | --- | --- |
| Starting: context incomplete | `BROKEN` | `REFUSING_TRAFFIC` | Listener may not be open yet |
| Started: context refreshed, before/during runners | `CORRECT` | `REFUSING_TRAFFIC` | May be listening yet should not receive user traffic |
| Ready: after runners, `ApplicationReadyEvent` | `CORRECT` | `ACCEPTING_TRAFFIC` | Ready to accept traffic |
| Graceful shutdown | Usually `CORRECT` | `REFUSING_TRAFFIC` | Rejects new requests, drains in-flight per deadline |
| Process stopped | No health HTTP available | Unavailable | Port closed |

**Do not expect `{"status":"OUT_OF_SERVICE"}` during the very earliest phase.** Before the server binds, kubelet gets connection refused rather than an HTTP response. During graceful shutdown once the listener closes, probes likewise cannot reach the endpoint even though state changed.

### 4.2. ApplicationStartedEvent vs ApplicationReadyEvent

```text
ApplicationContext refreshed
         |
ApplicationStartedEvent
         |
ApplicationRunner/CommandLineRunner
         |
ApplicationReadyEvent
         |
Readiness ACCEPTING_TRAFFIC
```

`ApplicationStartedEvent` fires after context refresh, **before** runners. `ApplicationReadyEvent` arrives only after runners finish. If an `ApplicationRunner` warmup takes 8 seconds, during that window liveness can be `CORRECT` while readiness is `REFUSING_TRAFFIC`. That is valid behavior.

### 4.3. If a Runner Fails

When a runner throws an unhandled exception, Spring Boot startup typically fails, the context closes, and the process exits. It does not necessarily stay up indefinitely returning readiness 503. If degraded mode is desired, design explicit exception handling, retries, circuit breakers, and classify which failures permit continuing.

### 4.4. Application-Driven Readiness Publishing

Inside a bean holding `ApplicationContext context`, you can publish:

```java
AvailabilityChangeEvent.publish(
    context, ReadinessState.REFUSING_TRAFFIC);
```

Once draining or recovery finishes:

```java
AvailabilityChangeEvent.publish(
    context, ReadinessState.ACCEPTING_TRAFFIC);
```

This is a **snippet** requiring imports and a `context` reference, never a public unauthenticated controller endpoint anyone on the network can call. Only publish `LivenessState.BROKEN` when you genuinely want a restart because the runtime cannot recover; never trigger it casually in production.

## 5. HTTP Endpoints Created by Actuator

Add:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

On Kubernetes, Spring Boot automatically enables liveness/readiness probe groups when it detects the platform. Outside Kubernetes, in Spring Boot **3.3**, set explicitly:

```properties
management.endpoint.health.probes.enabled=true
```

Common paths:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

### 5.1. Global Health Differs from Liveness/Readiness

- `/actuator/health`: aggregates configured health contributors, potentially including DB/disk/Redis when dependencies are present.
- `/actuator/health/liveness`: health group for **`livenessState`**.
- `/actuator/health/readiness`: health group for **`readinessState`**.
- `/actuator/startup`: exposes **startup step instrumentation** when configured and exposed—**not** a Kubernetes `startupProbe`.

If a DB check causes `/actuator/health` to return 503, that does not automatically make `/actuator/health/liveness` return 503. Spring Boot does not add external health contributors to liveness/readiness probe groups by default.

### 5.2. Why /actuator/startup Is Not a startupProbe

Actuator's `startup` endpoint exposes bootstrap timing captured by `ApplicationStartup`/`BufferingApplicationStartup` when enabled. It is a diagnostic tool for startup steps, not a liveness signal and not guaranteed available mid-bootstrap. Sharing the word “startup” does not mean kubelet should `GET /actuator/startup`.

A Kubernetes `startupProbe` is **configured in the Pod spec**, for example:

```yaml
startupProbe:
  httpGet:
    path: /livez
    port: http
```

Kubelet checks HTTP status/timeouts. Actuator's `startup` endpoint was not built for that contract.

### 5.3. Status-to-HTTP Mapping

By default, health statuses map `UP` → HTTP 200 and `DOWN`/`OUT_OF_SERVICE` → HTTP 503. `management.endpoint.health.status.http-mapping.*` can customize status mappings. Never map `OUT_OF_SERVICE` to HTTP 200 just to keep dashboards green: kubelet would misinterpret it and send traffic to an unready Pod.

### 5.4. Protecting Health Details

Set:

```properties
management.endpoint.health.show-details=never
management.endpoints.web.exposure.include=health
```

This is a clean baseline for the lab; production still requires network policies and an appropriate security chain. Never unconditionally expose `env`, `heapdump`, `loggers`, `shutdown`, or `configprops` to the Internet. Health details can reveal DB hostnames, error messages, or deployment internals that must stay private.

## 6. Separating the Management Port from the Business Port

Suppose:

```properties
server.port=8080
management.server.port=9090
```

A health probe on `9090` can return 200 even if the business HTTP listener on `8080` is misconfigured or stopped accepting connections. The main server and management server run separate web infrastructures in a separate management context.

For better fidelity, Spring Boot 3.3 supports:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

This adds health group routes on the **main port**:

```text
http://pod-ip:8080/livez
http://pod-ip:8080/readyz
```

With a separate management port, the original Actuator routes also exist:

```text
http://pod-ip:9090/actuator/health/liveness
http://pod-ip:9090/actuator/health/readiness
```

Recommendation for Kubernetes web APIs: probe `/livez`/`/readyz` on **port 8080** so probes at least verify the main listener is handling HTTP. They still do not test DB/payment flows unless explicitly designed.

### 6.1. Do Not Hand-Write an Always-200 Controller

Anti-example:

```java
// Do not use to replace the built-in liveness health group:
@GetMapping("/livez")
public String live() {
    return "OK";
}
```

An endpoint always returning 200 masks `LivenessState.BROKEN`. Once `add-additional-paths=true` is set, no custom controller is needed, and writing one risks mapping collisions.

### 6.2. Context Path and HTTPS

If the project sets `server.servlet.context-path=/api`, probe paths on the main server may be affected by the prefix; verify the exact URL for your version and config. If the web server binds `127.0.0.1` inside the container instead of `0.0.0.0`/Pod IP, kubelet's `HTTP GET PodIP` will fail with connection refused. If TLS-only or a service mesh is active, choose the appropriate `scheme` and mesh probe rewriting.

## 7. Startup Probe Mechanics in Detail

### 7.1. Startup Gate

Kubernetes runs `startupProbe` only until it **succeeds once**. Until then, liveness and readiness probes do not run. Once it succeeds, `startupProbe` stops and liveness/readiness take over on their own schedules. A Pod does not automatically become Ready just because `startupProbe` passed; **readiness must succeed** and other Pod conditions must be met.

### 7.2. Startup Failure

When `startupProbe` fails `failureThreshold` consecutive times, kubelet restarts the container. Repeated failures lead to `CrashLoopBackOff`/backoff restarts. This differs from readiness: readiness failures only mark the Pod NotReady without restarting it.

### 7.3. Should startupProbe Target /livez or /readyz?

**/livez** (commonly recommended by Boot docs): indicates the runtime has booted enough for liveness checks to begin. It can succeed **before** runners/warmup complete while readiness continues holding off traffic. This cleanly separates “process started” from “business ready”.

**/readyz** (when specifically required): only passes startup once ready for traffic. However, if readiness depends on a shared DB, a DB outage causes startup to hit its failure threshold → repeated restarts, even though the JVM is healthy. Choose intentionally rather than picking `/readyz` by reflex.

**A subtle failure mode:** if an `ApplicationRunner` hangs forever after liveness is already `CORRECT`, `startupProbe` on `/livez` turns green while readiness stays red indefinitely. Nothing forces kubelet to restart as long as liveness keeps passing. The proper fix is **bounded warmup timeouts**, controlled startup failure, or an internal progress watchdog—not arbitrarily tying the DB into liveness.

### 7.4. startupProbe Is Not Required for Every App

If an app boots quickly and steady-state liveness tolerances suffice while readiness blocks premature traffic, `startupProbe` may be unnecessary. Use `startupProbe` when startup duration is long/highly variable or steady-state liveness thresholds would kill the app too early.

## 8. Kubernetes Probe Fields: Practical Calculations

Key fields:

| Field | Meaning |
| --- | --- |
| `httpGet.path` | Actual GET path on Pod IP/port |
| `port` | Numeric or named container port |
| `periodSeconds` | Check interval; readiness while NotReady may run more frequently |
| `timeoutSeconds` | Timeout per probe attempt |
| `failureThreshold` | Consecutive failures before taking action |
| `successThreshold` | Consecutive successes; must be **1** for startup/liveness |
| `initialDelaySeconds` | Optional initial delay before probing |
| `terminationGracePeriodSeconds` | Pod shutdown budget; not startup time |

For example, `startupProbe.failureThreshold=24`, `periodSeconds=5` gives roughly a **120-second** budget, not a millisecond-exact hard deadline. Scheduling, probe timeouts, delays, and node load affect exact timing. `livenessProbe.failureThreshold=3`, `periodSeconds=10` gives roughly a few-dozen-second detection window after startup; tune for GC pauses, CPU throttling, and retries.

### 8.1. HTTP Success

Kubelet HTTP probes treat status **200–399** as success. 404/401/403/500/503 or timeouts/connection refused count as failures. Watch out: if Spring Security redirects `/readyz` to a login page with **302**, kubelet may treat it as success. Probe URLs must return health status directly without login redirects.

### 8.2. Timeouts and False Failures Under Load

`timeoutSeconds=1` can be too tight during cold starts, garbage collection, or CPU throttling. False liveness timeouts trigger restarts that drop warm caches and reopen connections, creating an overload loop. Never “fix” this by making health always return 200; measure resource usage, p99 latency, and pick realistic thresholds.

## 9. Deployment YAML with All Three Probes

Example deploying 2 replicas with main HTTP port 8080. Suitable for lab/staging, **not a universal production config**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: probe-lab
spec:
  replicas: 2
  revisionHistoryLimit: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: probe-lab
  template:
    metadata:
      labels:
        app: probe-lab
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: app
          image: registry.example.test/probe-lab:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
            successThreshold: 1
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
            successThreshold: 1
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
          resources:
            requests:
              cpu: 150m
              memory: 256Mi
            limits:
              memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: probe-lab
spec:
  selector:
    app: probe-lab
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
```

**Meaning:**

- Startup gets roughly 120 seconds for JVM cold starts; liveness will not kill it early during that window.
- After startup, readiness checks every 5 seconds whether the instance can accept traffic.
- After startup, liveness checks every 10 seconds whether the process needs restarting.
- `maxUnavailable: 0` keeps old Pods running while new Pods are not yet Ready during rolling updates, though it does not guarantee error-free traffic or sufficient cluster capacity for the surge Pod.
- `terminationGracePeriodSeconds: 40` applies to shutdown, not the startup budget.
- The image name is an example; build and push to a registry the cluster can actually pull from.
- Resource requests/limits are illustrative; benchmark your real app/JVM to avoid `OOMKilled` and CPU throttling.
- Production may also add `securityContext`, service accounts, network policies, HPA, PDB, affinity, and ingress/TLS.

## 10. External Dependencies: Be Extremely Cautious with Liveness

### 10.1. Do Not Put Shared DBs in Liveness

**Dangerous anti-example:**

```properties
management.endpoint.health.group.liveness.include=livenessState,db
```

Suppose the shared database goes down for 30 seconds. If liveness depends on the DB, every Pod may be restarted. Restarting JVMs does not restore the DB; instead it triggers a startup load/connection storm and can drop in-flight work.

Liveness should evaluate only unrecoverable internal runtime state; normally stick to built-in `livenessState` without adding DB/Redis/Kafka/payment APIs.

### 10.2. When Should Readiness Include a Dependency?

If an instance cannot serve **any meaningful request** when a local dependency is unavailable, you may add that check to readiness. Consider first:

1. Is there a fallback, cache, or circuit breaker?
2. Is the dependency shared across all Pods or local to one Pod?
3. Would failing readiness on all Pods leave the Service with zero endpoints?
4. Is the check fast, bounded, and side-effect free?
5. Could probe frequency overload the dependency?
6. Upon recovery, is there hysteresis/debouncing to prevent flapping?

Spring Boot does not add external health contributors to the readiness group automatically. Optional property example **only when a bean named `catalogWarmup` exists**:

```properties
management.endpoint.health.group.readiness.include=readinessState,catalogWarmup
```

If that contributor bean does not exist, do not copy this property into the base app. Match the exact `HealthIndicator` name and scope; missing contributors can make the health group invalid.

### 10.3. Optional Custom HealthIndicator

This class is a **separate extension**, not required for the runnable baseline below:

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("catalogWarmup")
public class CatalogWarmupHealth implements HealthIndicator {

    private final AtomicBoolean prepared =
            new AtomicBoolean(false);

    public void markPrepared() {
        prepared.set(true);
    }

    public void markNotPrepared() {
        prepared.set(false);
    }

    @Override
    public Health health() {
        return prepared.get()
                ? Health.up().build()
                : Health.outOfService().build();
    }
}
```

A warmup service can call `markPrepared()` once local data/models are ready. If the readiness group includes `catalogWarmup`, readiness also reflects this state. **Never run a 2-second remote DB query inside every `health()` call**; probes would generate heavy load themselves.

### 10.4. Readiness Does Not Replace Circuit Breakers

If the DB is down while some endpoints can still serve cached responses, marking the whole Service NotReady can be worse than keeping Pods Ready and serving safe degraded results. Conversely, if every request needs the DB and no fallback exists, shedding traffic may beat returning 500s. Policy depends on the business contract; there is no universal setting.

## 11. Runnable Spring Boot Java 17+ Project

We build a small application with:

- `GET /api/hello`: sample API.
- `GET /demo/state`: returns Java `ApplicationAvailability` (for learning only; never expose publicly).
- `ApplicationRunner` simulating an 8-second warmup.
- Actuator liveness/readiness health groups.
- `/livez` and `/readyz` on the main HTTP port.
- Integration test using `TestRestTemplate` proving readiness flips 200 → 503 while liveness remains 200.

### 11.1. Gradle Project

Generate from [Spring Initializr](https://start.spring.io/), Java 17+, Spring Boot 3.3.x, Gradle/Groovy, selecting **Spring Web** and **Spring Boot Actuator**.

`settings.gradle`:

```groovy
rootProject.name = 'probe-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The project needs the **Gradle Wrapper** generated by Initializr (`gradlew`, `gradlew.bat`, `gradle/wrapper`). Do not run standalone `javac DemoController.java` since it needs Spring dependencies from Gradle. Use Spring Boot dependency management rather than mixing arbitrary Spring Framework/Actuator versions.

Structure:

```text
settings.gradle
build.gradle
gradlew
gradlew.bat
gradle/wrapper/...
src/
  main/
    java/demo/
      ProbeLabApplication.java
      DemoController.java
      WarmupRunner.java
    resources/
      application.properties
  test/
    java/demo/
      ProbeHttpIntegrationTest.java
```

### 11.2. ProbeLabApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProbeLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProbeLabApplication.class, args);
    }
}
```

### 11.3. DemoController.java

```java
package demo;

import java.util.Map;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ApplicationAvailability availability;

    public DemoController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }

    // For local learning only.
    @GetMapping("/demo/state")
    public Map<String, String> state() {
        return Map.of(
                "liveness",
                availability.getLivenessState().name(),
                "readiness",
                availability.getReadinessState().name()
        );
    }
}
```

After successful startup, `/demo/state` body is typically equivalent to:

```json
{
  "liveness": "CORRECT",
  "readiness": "ACCEPTING_TRAFFIC"
}
```

While warmup is still running, you may see `CORRECT`/`REFUSING_TRAFFIC` once the listener is active. Before the server binds/accepts requests, `curl` reports a connection error rather than JSON. `/demo/state` does not replace `/livez`/`/readyz` and should not be exposed in production.

### 11.4. WarmupRunner.java

```java
package demo;

import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class WarmupRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(WarmupRunner.class);

    @Value("${probe.demo.warmup-seconds:8}")
    private int seconds;

    @Override
    public void run(ApplicationArguments arguments)
            throws Exception {

        if (seconds < 0 || seconds > 120) {
            throw new IllegalArgumentException(
                    "warmup-seconds must be 0..120");
        }

        log.info("WARMUP_BEGIN seconds={}", seconds);

        TimeUnit.SECONDS.sleep(seconds);

        log.info("WARMUP_COMPLETE");
    }
}
```

`ApplicationRunner` runs **after `ApplicationStartedEvent` and before `ApplicationReadyEvent`**. The 8-second sleep is strictly for observation, not a production warmup technique. In real apps, startup should have timeout/failure semantics rather than sleeping a thread arbitrarily.

### 11.5. application.properties

```properties
spring.application.name=probe-lab
server.port=8080

# Enable probe groups locally, not only on Kubernetes.
management.endpoint.health.probes.enabled=true

# Expose /livez and /readyz on the application port.
management.endpoint.health.probes.add-additional-paths=true

# Expose only health, not env/heapdump/shutdown...
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never

# Intentionally delay ApplicationReadyEvent.
probe.demo.warmup-seconds=8

# Explicit graceful shutdown for Spring Boot 3.3.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

These properties belong to **Spring Boot 3.3**. On Kubernetes, Boot auto-enables health groups; setting `enabled=true` ensures deterministic behavior locally. If `management.server.port=9090` is set, `/livez`/`/readyz` still expose on the main port when `add-additional-paths=true`.

### 11.6. Run

From the directory containing the Gradle Wrapper:

```bash
./gradlew clean test bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

Package the executable JAR:

```bash
./gradlew bootJar
java -jar build/libs/probe-lab-0.0.1-SNAPSHOT.jar
```

If running via `bootRun` and sending stop signals, remember the Gradle launcher PID may differ from the app JVM PID; run `java -jar` directly in shutdown experiments so signals hit the exact JVM process.

## 12. Observing Warmup with curl

Open **terminal A** to run the JAR. In **terminal B**, start polling before app startup finishes:

```bash
while true; do
  printf "live="
  curl -sS -o /dev/null -w '%{http_code}' \
    http://localhost:8080/livez
  printf " ready="
  curl -sS -o /dev/null -w '%{http_code}' \
    http://localhost:8080/readyz
  printf "\n"
  sleep 1
done
```

On Linux/macOS, before HTTP opens, `curl` prints `000` because **there is no HTTP response**. Once the app is Started, liveness can return 200 while readiness returns 503. After the runner logs `WARMUP_COMPLETE` and Spring publishes `ApplicationReadyEvent`, readiness transitions to 200. Exact timing depends on machine speed, startup order, and scheduling.

Once both are UP:

```bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/state
curl -i http://localhost:8080/api/hello
```

Healthy responses return JSON such as:

```json
{"status":"UP"}
```

HTTP status is normally 200. When readiness is `REFUSING_TRAFFIC`, the response may be:

```json
{"status":"OUT_OF_SERVICE"}
```

with HTTP **503**. This is an illustrative response shape; exact headers/media types from Spring Boot Actuator vary by `Accept` and version. Kubelet evaluates the status code, not raw JSON string equality.

### 12.1. Why Can Early Requests Be Refused Instead of Returning 503?

Before the Servlet connector accepts HTTP requests, no HTTP response exists to return 503. Kubelet sees connection refused/timeout and counts a probe failure. That is normal during the startup window; `startupProbe` handles it via its failure budget rather than expecting the server to emit JSON from millisecond zero.

### 12.2. Do Not Force Every Endpoint to Return 503 Before Ready

Normal business requests are not automatically blocked by Spring MVC merely because `ReadinessState.REFUSING_TRAFFIC` is active. Readiness primarily signals the platform to **stop routing new traffic**. Locally, calling an API port directly while readiness is red can still succeed depending on Boot lifecycle timing. Do not confuse readiness with a security filter blocking all business requests.

## 13. HTTP Integration Test Transitioning Readiness 200→503→200

`@SpringBootTest(webEnvironment=RANDOM_PORT)` starts a real embedded server on a random port. In the test we explicitly publish an event and assert the HTTP outcomes. Create `src/test/java/demo/ProbeHttpIntegrationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "probe.demo.warmup-seconds=0"
)
class ProbeHttpIntegrationTest {

    @Autowired
    TestRestTemplate client;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void appIsLiveAndReadyAfterBoot() {

        ResponseEntity<String> live =
                client.getForEntity("/livez", String.class);

        ResponseEntity<String> ready =
                client.getForEntity("/readyz", String.class);

        assertThat(live.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(ready.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(live.getBody()).contains("UP");
        assertThat(ready.getBody()).contains("UP");
    }

    @Test
    void refusingTrafficOnlyChangesReadiness() {

        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC
        );

        try {
            ResponseEntity<String> ready =
                    client.getForEntity("/readyz", String.class);
            ResponseEntity<String> live =
                    client.getForEntity("/livez", String.class);

            assertThat(ready.getStatusCode())
                    .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
            assertThat(ready.getBody())
                    .contains("OUT_OF_SERVICE");
            assertThat(live.getStatusCode())
                    .isEqualTo(HttpStatus.OK);
        } finally {
            // Prevent state from affecting other tests sharing the context.
            AvailabilityChangeEvent.publish(
                    context,
                    ReadinessState.ACCEPTING_TRAFFIC
            );
        }
    }
}
```

**What this test proves:** the main-port HTTP health group routes exist for real; publishing `REFUSING_TRAFFIC` makes `/readyz` return 503 while `/livez` stays 200. `TestRestTemplate` is designed for integration tests and does not treat 4xx/5xx responses as exceptions.

**What this test does not prove:** kubelet restarts, EndpointSlice routing, Ingress/TLS, distributed DB health, `preStop`, or restarts/evictions. Run those experiments on a staging cluster.

### 13.1. Why Does the Test Set warmup-seconds=0?

`@SpringBootTest` executes test methods only after the context is ready. To observe states **during** startup, run the app as an external process and poll from outside, rather than only using a JUnit method after startup completes.

### 13.2. Do Not Run State-Mutating Tests in Parallel Unconditionally

Availability state lives in the application context. If tests run in parallel sharing one context, a test publishing `REFUSING_TRAFFIC` can interfere with another test. The `finally` block restores state, yet parallel isolation still must be managed. Use separate contexts, disable parallelism, or synchronize if the suite grows.

### 13.3. MockMvc vs RANDOM_PORT

`MockMvc` can test controllers and Actuator mappings via mock Servlet requests without opening a TCP HTTP listener. `RANDOM_PORT` tests the real main listener path. Neither simulates kubelet, Pod IP routing, or network policies.

## 14. Dockerfile and Container Testing

After building `bootJar`, create `Dockerfile`:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY build/libs/probe-lab-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Exec-form `ENTRYPOINT` keeps the JVM as the main process so it receives stop signals cleanly from the container runtime. With shell-form entrypoints, `TERM` may not be forwarded to the JVM properly. To test locally:

```bash
docker build -t probe-lab:local .
docker run --rm -p 8080:8080 probe-lab:local
```

In another terminal, call `/livez`/`/readyz`. To apply the Kubernetes manifest, push the image to a registry or configure the cluster to use local images properly; `registry.example.test/...` in the YAML is illustrative only.

**Distinction:** Docker `HEALTHCHECK` is not the same as Kubernetes `readinessProbe`. Docker tracks a container health state; Kubernetes controllers and Service endpoints rely on Pod Ready conditions driven by kubelet's probes.

## 15. Real Deployment: kubectl and Diagnostics

With a staging Kubernetes cluster and a valid image:

```bash
kubectl apply -f probe-lab.yaml
kubectl rollout status deployment/probe-lab
kubectl get pods -l app=probe-lab -w
kubectl describe pod <POD_NAME>
kubectl logs <POD_NAME> -c app
kubectl logs <POD_NAME> -c app --previous
kubectl get endpointslice \
  -l kubernetes.io/service-name=probe-lab
```

`<POD_NAME>` is a CLI placeholder; replace it with the real Pod name. `--previous` retrieves logs from the previous container run prior to a restart, if still retained.

### 15.1. Meaning of Common Errors

- `connection refused`: container has not bound yet, process died, wrong port/path, or listener bound only to loopback.
- `HTTP 404`: Actuator did not expose the route, missing `add-additional-paths`, or wrong context path.
- `HTTP 401/403`: Spring Security blocked kubelet; permit minimal read-only access for health routes.
- `HTTP 302`: likely a login redirect, which kubelet may treat as success; fix it.
- `HTTP 503`: health group reports `DOWN`/`OUT_OF_SERVICE` or the app is draining.
- `context deadline exceeded`: timeout too short, CPU throttling/GC pauses, network issue, or deadlock.
- `CrashLoopBackOff`: repeated restarts, **not necessarily** caused by probes; the app may be crashing, `OOMKilled`, or failing config.
- `Pod Running, Ready false`: process is alive yet readiness fails, startup has not finished, another container failed, or a readiness gate is unsatisfied.

Inspect `kubectl describe pod` events, container `lastState`, restart count, resource metrics, logs, and EndpointSlices; never rely solely on a single “Unhealthy” line.

### 15.2. Kubelet Probes Bypass Ingress by Default

Kubelet HTTP probes normally target **Pod IP:container port/path**, bypassing Service/Ingress/TLS/CDN. Therefore `curl https://api.example.com/health` returning 200 **does not** prove kubelet's path/port are right; conversely, kubelet `/readyz` passing does not prove the public API works through the gateway.

### 15.3. Security, Redirects, and 3xx

With Spring Security, health probes may need read-only access permitted on `/livez`/`/readyz` for kubelet/internal networks while keeping other Actuator management endpoints protected. Never use `anyRequest().permitAll()` just to make probes pass. Never allow probe endpoints to redirect to login: 3xx can look like success to kubelet without evaluating health.

### 15.4. Localhost Inside Containers

If the app binds `server.address=127.0.0.1` inside a container, kubelet probes targeting the Pod IP will be refused. To listen on the Pod interface for the main port, keep the appropriate default binding (typically all interfaces) and protect it with NetworkPolicies/Ingress/Security. Never set `httpGet.host: localhost` to mask a broken listener configuration.

## 16. Readiness During Rolling Deployments and Shutdown

An ideal rolling update:

1. New Pod is created and the JVM bootstraps.
2. `startupProbe` passes within the startup budget.
3. Liveness monitors steady state.
4. Readiness returns 200 only when the instance can genuinely handle traffic.
5. Service/EndpointSlice updates routes, and the new Pod begins taking load.
6. Old Pod is marked terminating while ingress/proxies withdraw traffic asynchronously.
7. Spring Boot graceful shutdown stops accepting new requests and waits for in-flight requests within budget.
8. Client retries/idempotency handle any interrupted requests.

**Readiness false does not close existing open connections immediately.** Clients using keep-alive/WebSocket/SSE may continue using existing connections during rollout. Depending on the service, instruct clients to reconnect/resubscribe and maintain cursors/replay if event durability matters.

### 16.1. terminationGracePeriodSeconds Differs from Probe Thresholds

`terminationGracePeriodSeconds` defines the Pod shutdown deadline. Example:

```yaml
spec:
  terminationGracePeriodSeconds: 40
  containers:
    - name: app
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
```

This snippet merges into `spec.template.spec` of a Deployment, not a standalone manifest. `preStop` consumes part of the 40 seconds; **it is not added on top of grace**. A 5-second sleep helps only if your cluster/ingress needs propagation buffer and has been measured. Do not copy it blindly into every app.

### 16.2. Graceful Shutdown in Spring Boot 3.3

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

In Boot 3.3, `server.shutdown=graceful` must be enabled explicitly so the embedded web server drains in-flight work; Boot 3.4 changed the default. This mechanism is **separate from Kubernetes probes**. If the graceful phase outlasts remaining Pod grace, kubelet can force-kill the process before it finishes.

### 16.3. Do Not Treat Probes as Transaction Guarantees

An HTTP POST may commit to the DB right before the client sees a connection reset as the Pod stops. Retrying without an idempotency key can execute duplicate transactions. Probes reduce disruption via routing/draining, not exactly-once semantics; handle transactions, retries, and durable state explicitly.

## 17. WebFlux, Management Context, and Other Protocols

In Spring WebFlux, Actuator still exposes liveness/readiness health groups, using Reactor Netty instead of Tomcat. If an application includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot applies rules to choose the web application type; do not assume it switches to reactive just because WebFlux is on the classpath.

If using a separate management port/context, Actuator health requests there can succeed even when the main pipeline is unhealthy. Additional main-port paths are the right mechanism for HTTP web services. For gRPC-only apps, Kubernetes provides a gRPC probe handler following the gRPC Health Checking Protocol; do not expect Actuator's HTTP health group to serve as a gRPC health server.

Kubernetes also supports TCP and exec probes:

- TCP only verifies the socket accepts connections, not that the HTTP app responds properly.
- Exec runs an internal command, but distroless images lack shell/`curl`, and periodic process forks carry overhead.
- HTTP GET inspects actual route status, fitting Actuator liveness/readiness on HTTP web apps.
- gRPC probes have separate semantics and configuration.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Pointing liveness at aggregate `/actuator/health` | Shared DB outage → restart storm | Use `/livez` (`livenessState` group) |
| Using an always-200 URL for readiness | Unwarmed Pod receives traffic | Use `/readyz` backed by `ApplicationAvailability` |
| Omitting `startupProbe` for slow cold starts | Liveness kills app before startup finishes | Set startup budget matching p99 |
| Pointing `startupProbe` at `/actuator/startup` | Endpoint is not a probe, may return 404 | Use `/livez` or a contract-compliant endpoint |
| Assuming startup success = Pod Ready | Readiness has not passed yet | Track readiness and Pod conditions separately |
| Assuming liveness waits for readiness | Without a startup gate, probes run independently | Add `startupProbe` if needed |
| Seeing `/readyz` 503 while `/livez` 200 as a bug | Thinking states are inconsistent | Normal during warmup or graceful drain |
| Thinking management 9090 returning 200 is enough | Business port 8080 may be dead | Enable additional paths on the main port |
| Configuring `/livez` without Actuator | HTTP 404 | Add Actuator starter and probe properties |
| Enabling probe groups only in K8s, getting 404 locally | Platform detection differs | Set `management.endpoint.health.probes.enabled=true` |
| Probe returns 302 to login | Kubelet treats 302 as success | Disable redirects; define explicit security rules |
| Binding probe listener only to `127.0.0.1` | Kubelet requests to Pod IP refused | Bind the proper main interface |
| `timeoutSeconds: 1` during JVM GC pauses | False liveness restarts | Tune thresholds and measure GC/CPU |
| Tying readiness to every external health check | All Pods turn NotReady on shared outage | Evaluate fallbacks, criticality, and scope |
| Running heavy DB queries in probes every second | Health checks overload the DB | Keep checks cheap/bounded and less frequent |
| Blaming every `CrashLoopBackOff` on liveness | Misses OOM, process exit, bad image | Inspect events, `lastState`, and `--previous` logs |
| Testing only localhost URLs, skipping Pod IP | Path/port/network mismatch | Test across K8s networking |
| Skipping rollout tests under load | Active connections drop | Test graceful drain, ingress drain, and retries |
| Treating health 200 as E2E success | Business APIs can still fail | Use synthetic monitors, SLOs, and tracing |

## 19. Self-Check Questions

**1. Will three failed `readinessProbe` checks restart the Pod?**  
**Answer:** Not for readiness alone; the Pod becomes NotReady and routing updates. Restarts come from startup/liveness failures, process exits, or other causes.

**2. What happens when `livenessProbe` exceeds its failure threshold?**  
**Answer:** Kubelet restarts the container per policy. This does not automatically fix broken business data.

**3. Does `startupProbe` passing mean readiness is 200?**  
**Answer:** No. `startupProbe` merely unlocks liveness/readiness checks; readiness must pass on its own.

**4. Does Boot's `ApplicationStartedEvent` fire before or after `ApplicationRunner`?**  
**Answer:** Before the runner. `ApplicationReadyEvent` fires after runners finish.

**5. Are `LivenessState.CORRECT` alongside `ReadinessState.REFUSING_TRAFFIC` valid?**  
**Answer:** Yes. The runtime is alive, yet the app is not ready to accept traffic.

**6. Does `/actuator/startup` serve the same function as a Kubernetes `startupProbe`?**  
**Answer:** No. It provides startup step diagnostics and may not even exist unless `ApplicationStartup` is configured.

**7. Does a kubelet HTTP probe require the body `{"status":"UP"}`?**  
**Answer:** No; HTTP 200–399 counts as success. The body is for humans or external monitors.

**8. Should a shared DB outage fail liveness and restart all Pods?**  
**Answer:** Usually no. Restarting does not fix the DB and risks a cascading failure.

**9. The app uses management port 9090 and main port 8080. Where should you probe?**  
**Answer:** Enable additional paths `/livez`/`/readyz` on port 8080 to verify the main listener, not just the management context.

**10. Do 24 startup retries every 5 seconds equal exactly 120,000 ms?**  
**Answer:** It is roughly a 120-second budget; kubelet scheduling, timeouts, and delays affect actual timing.

**11. Can an HTTP 302 login redirect be treated as success by kubelet?**  
**Answer:** Yes, since 2xx/3xx typically count as success; fix probe paths/security to return health status directly.

**12. Why shouldn't readiness include a shared DB by default for every service?**  
**Answer:** On a cluster-wide DB outage, all Pods could turn NotReady; if the service has fallbacks, that makes matters worse. Decide per business contract.

**13. Can liveness return 200 while a runner hangs forever?**  
**Answer:** Yes. Liveness can be `CORRECT` once context starts while readiness stays `REFUSING` forever. Warmups need timeouts/watchdogs/fail-fast policies.

**14. Does a `RANDOM_PORT` test prove Kubernetes restarts work?**  
**Answer:** No, it only verifies HTTP routes/statuses; testing kubelet requires a staging/live cluster.

**15. Why doesn't a 200 HTTP probe prove Internet clients can reach the app?**  
**Answer:** Kubelet hits Pod IP directly; Ingress/DNS/TLS/CDN and business requests introduce separate failure modes.

## 20. Production Checklist

- [ ] Spring Boot 3.3 has Actuator, health probe groups, and version-appropriate properties.
- [ ] `/livez` and `/readyz` are probed on the main application port.
- [ ] When using a separate management port, `add-additional-paths=true` and the main listener are verified.
- [ ] Liveness does not depend on DB/Redis/Kafka/external APIs by default.
- [ ] Readiness reflects ability to accept new traffic without overusing external checks.
- [ ] `startupProbe` is present when cold starts are long or highly variable.
- [ ] Startup budget, liveness thresholds, and readiness timeouts are backed by real metrics.
- [ ] Warmup enforces timeout/retry/fail semantics so the app cannot stay NotReady forever.
- [ ] Readiness/liveness are not redirected to login or blocked with 401/403 by Security config.
- [ ] Only minimal Actuator endpoints are exposed, with health details hidden.
- [ ] Kubelet targets the exact port, path, and scheme; the app binds the Pod interface.
- [ ] HTTP health checks are fast, bounded, and free of side effects or connection storms.
- [ ] `RANDOM_PORT` integration tests verify readiness transitions 200↔503.
- [ ] Kubernetes staging tests verify Ready status, `restartCount`, EndpointSlices, and rollouts.
- [ ] CPU throttling and GC pauses are addressed to prevent false liveness restarts.
- [ ] Rolling updates pair graceful shutdown with an adequate Pod termination budget.
- [ ] Metrics cover 5xx rates, latency, probe failures, Pod restarts, `OOMKilled`, and startup duration.
- [ ] Business clients enforce retries/idempotency and handle Pod draining cleanly.
- [ ] Health 200 is not equated with E2E business health; synthetic monitors are used where appropriate.
- [ ] Runbooks clearly separate startup, readiness, liveness, process crashes, and proxy failures.

## 21. Official References

1. [Spring Boot 3.3 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
2. [Spring Boot 3.3 — SpringApplication and Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Boot 3.3 — ApplicationAvailability Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
5. [Spring Boot 3.3 — AvailabilityChangeEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html)
6. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
7. [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
8. [Kubernetes — Configure Liveness, Readiness, Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
9. [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
10. [Kubernetes — Service](https://kubernetes.io/docs/concepts/services-networking/service/)
11. [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
12. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)

**Conclusion:** **`startupProbe`** protects startup time, **`readinessProbe`** decides whether to send traffic, and **`livenessProbe`** detects broken processes needing restarts. **Spring Boot `ApplicationAvailability`/Actuator** provide the states and HTTP health groups; **Kubernetes** enforces routing and restarts per the manifest. Separate readiness from liveness, keep shared dependencies out of liveness, place probes on the main port, and verify behavior over real HTTP/Kubernetes to prevent restart storms or routing traffic to unready Pods.