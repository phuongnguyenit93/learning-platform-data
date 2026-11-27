# Health Endpoints and Actuator for Spring Integration Adapters

When a Spring Boot application starts up cleanly, the HTTP server responding **does not guarantee** the entire integration system is working. An inbound File adapter may have stopped polling, SFTP sessions may be failing authentication repeatedly, an HTTP outbound gateway may be timing out continuously, a Kafka listener may have no assigned partitions, or a JDBC poller may be unable to fetch rows. Conversely, a brief SFTP partner outage is **not necessarily** a reason to restart every application container: doing so can worsen queues and backlogs.

**Spring Boot Actuator** provides management endpoints to observe a running application, with `/actuator/health` serving as a key entry point. To design health checks for **Spring Integration Adapters**, we must answer three distinct questions:

1. **Liveness:** Is the process alive and able to recover without a restart?
2. **Readiness:** Is this instance ready to accept additional work from the orchestrator?
3. **Integration dependency health:** Are adapters, pollers, connections, and business pipelines operating per contract?

This lesson belongs to the **Spring Boot** chapter of the `SPRING_INTEGRATION_ADAPTERS` module. The module explores connecting external systems via **inbound/outbound adapters, gateways, pollers, and `MessageChannel`** across File, SFTP, HTTP, JMS, AMQP, Kafka, and databases, along with message contracts, error handling, and connection lifecycles. This content designs health/observability specifically for those integration flows, not merely a conventional REST API.

> **Principle:** "The application is running" does not mean "data is flowing properly"; nor does "an external partner is down" automatically mean "this instance must be restarted". Health must reflect **the purpose of the signal and the action that signal triggers**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish Actuator health, liveness/readiness, startup probes, metrics, traces, logs, and business-level checks.
2. Explain `HealthIndicator`, `HealthContributor`, `CompositeHealthContributor`, status aggregation, and HTTP status mapping.
3. Configure `spring-boot-starter-actuator`, `management.endpoints.web.exposure.include`, and `management.endpoint.health.*`.
4. Design health groups by instance role and dependency risk.
5. Use Kubernetes liveness/readiness/startup probes without causing restart loops when a partner fails.
6. Build a passive `HealthIndicator` for a poller, distinguishing **successful empty polls** from **a stopped poller**.
7. Monitor File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC, separating connectivity, backlog, processing, and business outcomes.
8. Avoid health checks that are expensive, cause side effects, or leak sensitive data.
9. Test health/HTTP status responses, pre/post-startup states, outages, and recovery.
10. Write runbooks, test matrices, SLOs, and checklists for operating integration services.

## 2. What Is Actuator and What Does the Health Endpoint Solve?

Actuator is Spring Boot's toolkit for **managing and observing running applications**. Depending on dependencies, version, and configuration, Actuator can expose health, info, metrics, loggers, mappings, environment, beans, thread/heap diagnostics, and specialized endpoints. **This does not mean every endpoint is enabled or public over HTTP.**

`/actuator/health` returns **an aggregated status** derived from registered health contributors. It serves both human operators and orchestrators, though it is not a full business-verification API. Example:

~~~json
{
  "status": "UP"
}
~~~

This states only that the contributors in the **queried health group** aggregated to `UP`. Never assume from this that:

- Every external system was probed;
- Kafka consumer lag is zero;
- All SFTP files were ingested;
- Zero error messages sit in the DLQ;
- HTTP outbound completed all transactions;
- Zero orders are awaiting reconciliation.

### 2.1. Signals That Must Not Be Conflated

| Signal | Question answered | Appropriate action |
|---|---|---|
| **Liveness** | Should the process be restarted due to unrecoverable corruption? | Kubelet/agent restarts the instance only on truly fatal states. |
| **Readiness** | Should this instance receive new traffic/work? | Route traffic into or out of the instance. |
| **Dependency health** | Is the DB/broker/partner sufficiently available? | Investigate, retry/backoff, fail over, trip circuit breaker. |
| **Poller/consumer state** | Is the endpoint running and still polling/consuming? | Controlled endpoint restart; fix scheduling/connections. |
| **Data-flow metrics** | What are throughput, backlog, latency, errors, and duplicates? | Scale, tune, investigate business errors. |
| **Business verification** | Was the final side effect actually confirmed? | Reconcile, redrive, business support. |

Health answers a **qualitative question paired with an action**; metrics and traces answer **why** and **how severe the impact is**.

## 3. Liveness, Readiness, and Startup: Do Not Equate Them

### 3.1. Liveness

Liveness detects instances that are stuck or broken to the point where **a restart is likely to restore health**. Do not put every upstream HTTP, SFTP, or Kafka dependency into liveness merely because they are important. A partner outage affects every instance; Kubernetes repeatedly restarting healthy instances adds load and discards in-memory state.

Liveness can rely on Spring Boot's managed `livenessState`, plus only a tiny set of truly fatal internal conditions by design. If a failure can self-heal via reconnect/backoff, **do not turn it into liveness `DOWN`**.

### 3.2. Readiness

Readiness indicates whether an instance is ready to accept workload. An instance starting up or gracefully shutting down can report `REFUSING_TRAFFIC` while the process remains alive.

Depending on architecture, a mandatory DB may belong in readiness. Still, placing a **shared dependency** into every instance's readiness requires caution: if every instance drops out of service at once, the service may have nowhere left to return helpful error responses or recover.

### 3.3. Startup Probe

Kubernetes `startupProbe` grants slow-starting apps extra startup time before liveness probes restart them prematurely. It does not replace readiness and is not a mandatory Spring Boot `HealthIndicator` type.

### 3.4. Scenario Comparison

| Situation | Liveness | Readiness | Dependency/business alert |
|---|---|---|---|
| App is bootstrapping | Usually unassessed yet or process alive | Not ready | Monitor startup. |
| Kafka broker briefly unavailable, consumer auto-reconnects | Alive | Depends on instance role | Broker outage, lag, retries. |
| Partner HTTP returns 503 | Alive | Usually do not pull all API instances | Partner failure / circuit breaker. |
| SFTP inbound poller stopped unexpectedly | Process may still be alive | Depends on whether service is ingestion-only | Alert endpoint stopped + backlog. |
| Mandatory DB disconnected | Alive | May refuse traffic per policy | DB outage, queue/inbox safety. |
| Worker deadlocked unable to progress | May fail liveness if reliably detected | Not ready | Thread/lock diagnostics. |
| Graceful shutdown | Alive while draining | Not accepting new traffic | Track in-flight work. |

**No single liveness/readiness table fits every topology.** An app that only runs a file poller without serving HTTP clients handles readiness differently from an API gateway. Check whether Kubernetes readiness actually governs that workload's dispatch.

## 4. Health Building Blocks in Spring Boot

| API/concept | Role |
|---|---|
| `HealthIndicator` | Contributor whose `health()` method returns `Health`. |
| `ReactiveHealthIndicator` | Reactive variant for reactive stacks. |
| `HealthContributor` | Common abstraction for health contributors. |
| `CompositeHealthContributor` | Groups nested contributors. |
| `Health` | Holds `Status` and detail entries (when exposed). |
| `Status` | States such as `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN`. |
| `HealthEndpoint` | Actuator endpoint aggregating health. |
| **Health group** | Subset of contributors with dedicated visibility and status rules per purpose. |
| **Status aggregator** | Computes the combined status from individual contributors. |
| **HTTP status mapper** | Maps `Status` to HTTP codes understood by probes/monitors. |

### 4.1. Meaning of Common Statuses

| Status | Suggested meaning | Common default HTTP code |
|---|---|---|
| `UP` | Checked conditions passed. | 200 |
| `DOWN` | A required condition failed. | 503 |
| `OUT_OF_SERVICE` | Intentionally removed from service. | 503 |
| `UNKNOWN` | Insufficient evidence to decide. | Often 200 unless custom-mapped. |

**Note:** Custom statuses and health groups can have custom aggregation and HTTP mappings. Whenever configuring mappings, test the actual HTTP response; **never assume every unfamiliar status automatically maps to 503**. Kubernetes probes consume the HTTP status code, so `UNKNOWN` in JSON returning HTTP 200 will not gate readiness as you might assume.

### 4.2. Aggregated Health Does Not Mean "Everything Was Truly Checked"

~~~mermaid
flowchart TD
    HTTP["GET /actuator/health"] --> AGG["Health aggregation"]
    AGG --> DB["db HealthIndicator"]
    AGG --> DISK["diskSpace HealthIndicator"]
    AGG --> CUSTOM["custom poller/partner indicator"]
    AGG --> STATUS["UP / DOWN / OUT_OF_SERVICE / UNKNOWN"]
    STATUS --> RESP["JSON + HTTP status"]
~~~

Which contributors appear depends on **auto-configuration, context beans, health groups, and enable/disable properties**. Not every Spring Integration transport comes with a deep built-in health indicator; specifically, never assume "having Kafka client / SFTP adapter" means `/health` checks them end-to-end.

## 5. Maven and Gradle: Adding Actuator

In a project already using the Spring Boot BOM or matching dependency management, minimal dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.integration:spring-integration-test")
}
~~~

For real transports, add the matching adapter dependencies (File, SFTP, JMS, AMQP, Kafka, JDBC, HTTP) and connectors/drivers. For Prometheus, also add the matching registry such as a compatible `micrometer-registry-prometheus`; Actuator alone does not guarantee `/actuator/prometheus` works.

**Versioning:** Examples follow common APIs of modern Spring Boot and Spring Integration, especially releases supporting health groups and availability states. Endpoint names, YAML keys, and API signatures can vary across versions; verify against your exact dependency versions before deploying. Never mix incompatible versions simultaneously.

## 6. Minimal Safe Actuator Configuration

~~~yaml
spring:
  application:
    name: shipment-integration

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
~~~

With this configuration, the goal is exposing a basic health endpoint and enabling health probes on supporting Boot versions.

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Sample response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

This is a **sample**, not output from running on the learner's project. The exact content type depends on version and content negotiation. When probes aren't enabled or contributors don't exist, a URL may be unavailable; inspect real responses rather than treating samples as evidence.

### 6.1. Health Details Are Not for the Public Internet

`show-details: never` reduces operational information leakage in responses. When component details are needed, use `when_authorized` with appropriate roles and Spring Security. Never set `always` on a public endpoint lacking network/authentication controls.

### 6.2. Do Not Expose Every Endpoint for Debugging Convenience

Avoid:

~~~yaml
# NOT recommended for internet-facing apps without strict controls.
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Configuration, environment, logging, and diagnostic endpoints can expose system metadata or allow mutating operations. Expose only strictly needed endpoints behind network policies and proper authorization. Health endpoints for kubelets/load balancers should use **internal network paths**, not be exposed publicly to the internet.

## 7. Health Groups: One Application, Multiple Questions

An application can define groups:

- `liveness`: whether the instance needs restarting;
- `readiness`: whether it should receive more traffic;
- `integrations`: status of operational dependencies/adapters;
- `criticalDependencies`: only dependencies strictly mandatory to serve workload.

### 7.1. Creating a Dedicated Group for Integrations

~~~yaml
management:
  endpoint:
    health:
      group:
        integrations:
          include: partnerSftp,partnerHttp,db
          show-details: when_authorized
          roles: OPS
~~~

This example **assumes** the context has contributor IDs `partnerSftp`, `partnerHttp`, and `db`; for a custom bean named `partnerSftpHealthIndicator`, Spring Boot normally strips the `HealthIndicator` suffix to produce contributor ID `partnerSftp`. If using another bean name, the group must reference the actual ID. Where strict group-member validation is enabled, referencing a nonexistent ID can fail startup; verify with context tests.

Querying:

~~~bash
curl -i http://localhost:8080/actuator/health/integrations
~~~

You do not necessarily include the entire `integrations` group inside readiness; avoid letting a single partner outage pull all instances out of traffic when the app can still serve other work.

### 7.2. Readiness Includes Only Strictly Mandatory Components

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
~~~

This is **an architectural choice** when the database is mandatory for the workload. It is not a universal "best practice for every app". Spring Boot's default readiness/liveness groups focus on availability states and **do not automatically include external systems**. If you extend them, do so intentionally and test the blast radius of a shared dependency outage.

### 7.3. When One App Plays Multiple Roles

If one process serves an HTTP API and also runs an SFTP poller, HTTP traffic readiness **may not** be the right lever to control SFTP ingestion. Clarify:

1. Which endpoints/flows truly depend on that component.
2. Which workload controller reads readiness.
3. When the probe goes `DOWN`, whether fallback routes or other workers handle traffic.
4. Whether a widespread dependency outage removes every instance.
5. Whether API and ingestion workers should be deployed separately for independent orchestration.

## 8. Kubernetes Probes and Management Ports

Sample deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shipment-integration
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shipment-integration
  template:
    metadata:
      labels:
        app: shipment-integration
    spec:
      containers:
        - name: app
          image: example/shipment-integration:1.0
          ports:
            - containerPort: 8080
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
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
~~~

**This is an illustrative manifest**, not universal SLO values. Tune `failureThreshold`, `periodSeconds`, `timeoutSeconds`, startup window, graceful termination, and endpoint paths to your application's characteristics. Image, namespace, service account, and policies in this snippet are incomplete for production.

### 8.1. Separate Management Ports Can Mask Main Server Failures

If `management.server.port` differs from the main server port, Actuator may keep responding even if the main HTTP listener breaks. When probes must reflect the main web server, supported Spring Boot versions provide:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

On supporting versions, liveness/readiness also expose at **`/livez` and `/readyz` on the main server port**. Verify actual endpoints via integration tests; never assume every release supports the property or uses identical default mappings. If using a separate management port, never point kubelet at main-port paths unless verified.

### 8.2. Readiness Does Not Automatically Control Queue Consumers

A Kafka consumer container or inbound File poller runs independently of an HTTP load balancer. Kubernetes readiness going `DOWN` **does not automatically stop pollers, halt Kafka consumption, or pause JMS listeners**. To stop accepting broker work, implement explicit pause/stop/container lifecycle controls and test ACK/offset and backlog impacts.

## 9. Custom `HealthIndicator`: Choosing the Right Kind of Evidence

A custom `HealthIndicator` must answer **what was actually verified**, not merely return `UP` because the bean initialized.

| Strategy | Strengths | Risks |
|---|---|---|
| **Active check** | Issues a `ping`/query to verify live connectivity. | Adds load, timeouts, auth side effects, probe amplification. |
| **Passive state** | Reads state recorded by real I/O and polls. | Can go stale; absence of traffic is not a failure. |
| **Cached active check** | Bounds call frequency to external sources. | Must define TTL and stale/unknown semantics. |
| **Poller heartbeat** | Proves the scheduler still invokes the source even when idle. | Does not prove downstream target processing. |
| **Lifecycle state** | Checks bean/endpoint `isRunning()`. | Running does not guarantee messages are flowing. |
| **Backlog/lag check** | Measures processing health and delay. | Metrics often fit better than binary UP/DOWN flags. |
| **Canary/synthetic transaction** | Closest to real business outcome. | Has side effects/cost; needs dedicated accounts/fixtures. |

### 9.1. Four Easily Confused Poller States

1. **Poller running, source empty:** `receive()` normally returns `null`.
2. **Poller not invoked:** scheduler stopped, endpoint stopped, or thread pool starved.
3. **Poller invoked, source throws:** connection, permission, or schema failure.
4. **Poll succeeded, downstream failed:** message received yet failed processing.

A counter incremented only when **a message arrives** cannot distinguish case 1 from case 2. To measure heartbeat, **record every successful source poll even when it returns `null`**.

## 10. Designing a Passive Indicator Around Passive Signals

Let's build a thread-safe `PollMonitor` that records successful source polls, failed polls, and timestamps. The `HealthIndicator` merely **reads a snapshot**, never opening an SFTP connection on every Actuator scrape.

~~~mermaid
flowchart LR
    SCHED["Poller scheduler"] --> SRC["Observed MessageSource"]
    SRC --> REAL["Real File/SFTP/JDBC source"]
    SRC --> MON["PollMonitor<br/>last success/failure"]
    HEALTH["GET /actuator/health/integrations"] --> IND["PollHealthIndicator"]
    IND --> MON
    IND --> JSON["UP / DOWN / UNKNOWN"]
    REAL --> CH["MessageChannel"]
    CH --> HANDLER["Business handler"]
~~~

### 10.1. Defining an Immutable Snapshot

~~~java
package example.integration.health;

import java.time.Instant;

public record PollSnapshot(
        Instant lastSuccessfulPoll,
        Instant lastFailedPoll,
        long consecutiveFailures) {
}
~~~

### 10.2. Testable Monitor Using `Clock`

~~~java
package example.integration.health;

import java.time.Clock;
import java.util.concurrent.atomic.AtomicReference;

public final class PollMonitor {
    private final Clock clock;
    private final AtomicReference<PollSnapshot> current =
            new AtomicReference<>(
                    new PollSnapshot(null, null, 0));

    public PollMonitor(Clock clock) {
        this.clock = clock;
    }

    public void successfulPoll() {
        current.updateAndGet(old -> new PollSnapshot(
                clock.instant(),
                old.lastFailedPoll(),
                0));
    }

    public void failedPoll() {
        current.updateAndGet(old -> new PollSnapshot(
                old.lastSuccessfulPoll(),
                clock.instant(),
                old.consecutiveFailures() + 1));
    }

    public PollSnapshot snapshot() {
        return current.get();
    }
}
~~~

This monitor is **passive**: it knows nothing about SFTP credentials, calls no external APIs, and queries no DB. `AtomicReference` holds an immutable snapshot so Actuator reads a consistent set of fields while the scheduler updates them.

**Intentional limitation:** `consecutiveFailures` reflects failures receiving from the instrumented source, not downstream handler failures; it is neither Kafka lag nor a business-error count.

## 11. `HealthIndicator` Reads `PollMonitor` Without Triggering Side Effects

~~~java
package example.integration.health;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class PollHealthIndicator implements HealthIndicator {
    private final PollMonitor monitor;
    private final Clock clock;
    private final Duration maxSilence;

    public PollHealthIndicator(
            PollMonitor monitor,
            Clock clock,
            Duration maxSilence) {
        this.monitor = monitor;
        this.clock = clock;
        this.maxSilence = maxSilence;
    }

    @Override
    public Health health() {
        PollSnapshot state = monitor.snapshot();
        Instant lastSuccess = state.lastSuccessfulPoll();

        if (lastSuccess == null) {
            return Health.unknown()
                    .withDetail("reason", "NO_SUCCESSFUL_POLL_YET")
                    .build();
        }

        if (clock.instant().isAfter(lastSuccess.plus(maxSilence))) {
            return Health.down()
                    .withDetail("reason", "POLL_HEARTBEAT_STALE")
                    .withDetail("consecutiveFailures",
                            state.consecutiveFailures())
                    .build();
        }

        return Health.up()
                .withDetail("reason", "RECENT_SUCCESSFUL_POLL")
                .withDetail("consecutiveFailures",
                        state.consecutiveFailures())
                .build();
    }
}
~~~

### 11.1. Why Return `UNKNOWN` Before Any Poll?

Before the first poll, the app **lacks enough evidence** to declare the inbound source healthy. Yet if a poller runs **once every 24 hours**, "no poll yet" right after startup does not mean the instance is broken. Returning `UNKNOWN` expresses that evidence boundary.

**Critical warning:** If this indicator is placed into Kubernetes readiness to block traffic, `UNKNOWN` may still map to HTTP 200 by default; **never use it as a readiness gate** without verifying status aggregation and HTTP mapping. If business rules require blocking until the first poll, define explicit startup grace/requirements and a status with an unambiguous HTTP code rather than relying on surprising defaults.

### 11.2. When Is the Heartbeat Stale?

`maxSilence` must reflect **the polling schedule and acceptable jitter**. For a 30-second poller, a 3-minute threshold may make sense in one system; for a daily cron job, a 3-minute threshold would constantly report `DOWN` even when healthy. Without a baseline, this is just an example, not a default SLO.

### 11.3. `UP` Does Not Prove Business Outcomes

In this code, `UP` proves only that **at least one recent poll completed normally**. It does not prove:

- The source held new messages.
- Files had valid bytes or schemas.
- HTTP outbound succeeded.
- Kafka offsets committed.
- Final DB side effects were confirmed.

Those questions require dedicated health indicators, metrics, or reconciliation.

## 12. Observing `MessageSource`: An Empty Poll Is Still a Poll

To update `PollMonitor` accurately, wrap `MessageSource<T>` in a decorator. The decorator delegates to the real source, records the poll outcome, and **never alters** payloads/headers or swallows exceptions.

~~~java
package example.integration.health;

import java.util.Objects;

import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

public final class ObservedMessageSource<T>
        implements MessageSource<T> {

    private final MessageSource<T> delegate;
    private final PollMonitor monitor;

    public ObservedMessageSource(
            MessageSource<T> delegate,
            PollMonitor monitor) {
        this.delegate = Objects.requireNonNull(delegate);
        this.monitor = Objects.requireNonNull(monitor);
    }

    @Override
    public Message<T> receive() {
        try {
            Message<T> message = delegate.receive();
            monitor.successfulPoll(); // Even when message == null.
            return message;
        } catch (RuntimeException ex) {
            monitor.failedPoll();
            throw ex; // Preserve retry/error semantics.
        }
    }
}
~~~

### 12.1. Why Must Exceptions Be Rethrown?

If a health wrapper catches an SFTP/JDBC error and returns `null`, the poller thinks the source is empty when the adapter may actually be disconnected. As a result:

- Error channels and retry advice never see the real error.
- Health may stay `UP` if the wrapper mistakenly calls `successfulPoll()`.
- Operations cannot tell "no data" from "unable to fetch data".
- Backlogs grow silently without alerts.

The wrapper only **observes**; it must never change `MessageSource.receive()` semantics.

### 12.2. Exceptions to the Decorator Pattern

Catching `RuntimeException` suits most synchronous `receive()` APIs, though it does not cover every failure mode. If a source/framework **catches exceptions internally and returns `null`**, the wrapper sees no failure; attach observation to error handlers or transport metrics at the right layer.

For reactive/asynchronous `MessageSource`s or streaming connections, tailor observation to their lifecycle rather than applying this decorator mechanically to every inbound adapter.

### 12.3. Do Not Block the Scheduler with Health Checks

This decorator updates an `AtomicReference`, adding virtually zero network overhead. If every poll also called `sftpSessionFactory.getSession()` just to "check health", the health check itself could add load and alter failure modes; avoid doing so.

## 13. Registering Beans and Health Contributor IDs

Illustrative configuration for an SFTP source created by the integration module:

~~~java
package example.integration.health;

import java.io.File;
import java.time.Clock;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.core.MessageSource;

@Configuration
public class PollHealthConfiguration {

    @Bean
    Clock healthClock() {
        return Clock.systemUTC();
    }

    @Bean
    PollMonitor sftpPollMonitor(Clock healthClock) {
        return new PollMonitor(healthClock);
    }

    @Bean(name = "partnerSftpHealthIndicator")
    PollHealthIndicator partnerSftpHealthIndicator(
            PollMonitor sftpPollMonitor,
            Clock healthClock) {
        return new PollHealthIndicator(
                sftpPollMonitor,
                healthClock,
                Duration.ofMinutes(3));
    }

    @Bean(name = "observedSftpFileSource")
    MessageSource<File> observedSftpFileSource(
            @Qualifier("sftpFileSource")
            MessageSource<File> actualSource,
            PollMonitor sftpPollMonitor) {
        return new ObservedMessageSource<>(
                actualSource, sftpPollMonitor);
    }
}
~~~

**Prerequisite of this example:** `sftpFileSource` is the **real source bean provided by another SFTP inbound config**. Without that bean, the application context will fail to start; this snippet illustrates wiring only and does not build an SFTP connection or credentials itself.

### 13.1. Using the Observed Source in an `IntegrationFlow`

~~~java
// Example fragment inside @Configuration:
@Bean
IntegrationFlow sftpInboundFlow(
        @Qualifier("observedSftpFileSource")
        MessageSource<File> observedSftpFileSource) {
    return IntegrationFlow
            .from(observedSftpFileSource,
                    endpoint -> endpoint
                            .id("sftpInboundEndpoint")
                            .poller(Pollers
                                    .fixedDelay(Duration.ofSeconds(30))
                                    .maxMessagesPerPoll(1)))
            .channel("importedFiles")
            .get();
}
~~~

Add imports for `IntegrationFlow`, `Pollers`, `File`, `Duration`, `MessageSource`, and `@Qualifier` in real code. This is a design fragment; `importedFiles` must be registered with a consumer. Never create two pollers reading the same source just for health.

### 13.2. Global `/health` and Groups Can Both Be Affected

When `partnerSftpHealthIndicator` is registered, it may contribute to **global `/actuator/health`**, not only the `integrations` group. If it goes `DOWN` during a partner outage, global status may turn `DOWN`. Therefore:

- Kubernetes liveness must call `/actuator/health/liveness`, **never global `/health` just because the URL is shorter**.
- Readiness groups must be defined deliberately.
- Monitors/operators checking integrations should query `/health/integrations` or dedicated metrics/alerts.
- If a custom diagnostic indicator negatively affects global status, consider contributor structure, aggregation policies, or custom management endpoints/metrics rather than turning every `HealthIndicator` into a fatal dependency.

Adding an indicator often causes unintended aggregation side effects; test **global, liveness, readiness, and diagnostic groups** together.

## 14. Difference Between Adapter Running and Message Processing Succeeding

On a Spring Integration endpoint, lifecycle interfaces like `SmartLifecycle` report `isRunning()`. However:

~~~text
Endpoint isRunning() == true
    != scheduler polled recently
    != external source is reachable
    != messages were processed
    != downstream side effects were confirmed
~~~

Health checks relying solely on `isRunning()` produce false positives when:

- The scheduler thread pool is starved.
- The source keeps returning `null` due to a broken filter.
- A Kafka listener lacks partition assignments.
- Handlers throw exceptions while the endpoint stays running.
- Workers are hours behind in backlog.

### 14.1. A Four-Layer Observability Model

~~~mermaid
flowchart LR
    LIFE["Lifecycle<br/>endpoint running"] --> P["Poll/Consume<br/>attempts"]
    P --> MSG["Message processing<br/>success/error"]
    MSG --> BIZ["Business confirmation<br/>target readback"]
~~~

| Layer | Signal | What it proves |
|---|---|---|
| Lifecycle | `isRunning()`, assignment, subscription | Endpoint/consumer is started/assigned in its own layer. |
| Source activity | Latest poll/receive, connect failures | Scheduler/source is active. |
| Processing | Handler throughput, errors, retries, DLQ | Messages entered and traversed processing steps. |
| Business outcome | DB state, outbound ACK + reconciliation | Final results were verified. |

You do not need four separate health indicators all returning `DOWN`; several of these belong in **metrics and dashboards**.

## 15. File Inbound Adapter: Health of a Local Source

File polling usually needs no network connection; filesystem access and file readiness dominate.

### 15.1. What to Monitor

- Does the input directory exist, is it a directory, and does it have proper permissions?
- Is the poller firing on schedule, even when no files exist?
- Are there `AccessDeniedException`, disk-full, or path-mismatch errors?
- Are `*.ready` files waiting beyond threshold?
- Are `*.tmp` files lingering too long, suggesting a stalled producer?
- Does the metadata filter persist and reload cleanly across restarts?

**Never scan/read directories of millions of files on every `/health` scrape.** Update file counts/backlog ages via bounded scheduled monitors or collected metrics.

### 15.2. Designing by Signal Meaning

| Signal | Should it drive liveness? | Where to observe it? |
|---|---|---|
| Missing directory | Usually no | Integration diagnostics; readiness if ingestion is mandatory. |
| Poller stopped unexpectedly | Not by default | Endpoint metric/alert; possibly worker readiness. |
| No new files today | No, if partner sent none | Business schedule/SLO metrics. |
| Ready files pending past SLA | No | Backlog / oldest-pending alert. |
| Disk full blocks temp writes | Do not decide blindly | Disk health, integration alerts; separate readiness policy. |

### 15.3. Checking File Directory Readiness

An active check can inspect `Files.isDirectory(path)` and `Files.isReadable(path)`, yet **never write dummy test files into a production directory on every `/health` call**. Writing files can trigger the inbound adapter itself, inject fake data, or cause permission contention.

## 16. SFTP Inbound/Outbound: Don't Turn Health into a File-Downloader

SFTP has many failure modes: DNS, TCP, SSH handshake, host keys, authentication, session pools, remote permissions, directories, rate limits, and partial transfers.

| Health signal | Proper measurement | Risk |
|---|---|---|
| Session connection | Cached active check or passive from real I/O | Opening session storms on frequent probes. |
| Host key/authentication | Error category from real connections | Never retry bad credentials infinitely. |
| Poll success | `MessageSource.receive()` success even on `null` | Does not prove new files exist. |
| Download success | Transfer counts/bytes and completion | Does not prove CSV business validity. |
| Remote backlog | Bounded listing / cached scan | Large directories overload SFTP. |
| Partial files | File-readiness / rename policies | Failures might not stop the endpoint. |
| Output upload confirmation | Remote readback/file metadata if required | Needs idempotency against duplicate uploads. |

**Never make "SFTP remote directory has at least one file" part of liveness.** Partners may send zero files on a given day while connectivity is completely healthy. Track **poll attempt success** separately from **data arrival SLOs**.

### 16.1. When to Use `UNKNOWN`?

If a poller runs on a daily cron and the first run hasn't happened yet, source status may be `UNKNOWN`. Clarify:

1. Is separate startup validation needed?
2. How long ago was the last connection?
3. Must the instance be immediately ready to ingest files?
4. During partner maintenance windows, should status show degraded or outage?

Never apply the same 2-minute heartbeat threshold to every SFTP partner regardless of polling schedule.

## 17. HTTP Outbound Gateway: Timeout Does Not Mean Partner Failed

An HTTP outbound gateway in Spring Integration can call an API synchronously, await the response, and emit a reply message. Partner HTTP health can be observed via:

- Request count, success/error status codes, and response latency;
- Connect/read timeouts and retry counts;
- Circuit breaker state;
- Last successful request and `429` rate limits;
- Count of requests with unknown outcomes;
- Backlog / pending gateway calls.

### 17.1. Active Probes Must Be Safe

An HTTP health indicator **must never send a real order-creation `POST`** just to see if the server is alive. If the partner exposes a contract-guaranteed **read-only, side-effect-free** `GET /health` or `HEAD /ping`, an active check can use it with timeouts, caching, and rate limits. Still:

- Partner's health endpoint may report `UP` even while the business API fails.
- The check needs its own credentials, and tokens must never be logged.
- A `200` on a health URL does not prove business requests succeed.
- HTTP `401`/`403` on a health URL may reflect policy/credentials rather than a dead server.

### 17.2. Unknown Outcomes After `POST`

If a `POST` reaches the server and the client hits a read timeout, the server may have committed data while the response was lost. Even if the health indicator records timeouts, **never automatically retry side-effecting operations** without idempotency keys or readback verification.

For operations:

- Health reflects connectivity/readiness per policy.
- Metrics track unknown outcomes.
- Reconciliation checks actual state at the target.
- Gateway retries remain bounded and follow safety contracts.

## 18. JDBC/Database: Connection Health vs. Batch Processing Health

Spring Boot can auto-configure a `db` health contributor when a `DataSource` is present, depending on configuration. Such contributors typically verify DB reachability at the connection/validation-query level, which **does not mean all business SQL or data consistency is healthy**.

### 18.1. Distinct Questions

| Question | Check type |
|---|---|
| Can a DB connection be established? | DB health / connection validation. |
| Does the DB user have read/write rights on inbox/outbox tables? | Dedicated integration/permission tests. |
| Can the poller query `READY` records? | Source execution metrics/health. |
| Are rows locked too long? | DB contention metrics/alerts. |
| Are outbox events stale? | Backlog / oldest-pending SLO. |
| Can business transactions commit? | Integration transaction tests + monitoring. |
| Was a row processed twice? | Idempotency / reconciliation metrics. |

### 18.2. Never Run Heavy Queries on Every `/health`

Avoid:

~~~sql
-- Do not execute on every probe request:
SELECT COUNT(*)
FROM massive_inbox_table
WHERE status = 'PENDING';
~~~

Without an index or on large tables, health checks add DB load and worsen outages. Use **periodically updated metrics, bounded/cached queries**, or lightweight connection checks matching the goal.

### 18.3. Readiness When the Database Is Mandatory

An app may require the DB to serve requests, making `db` in readiness reasonable. Yet during a broad DB outage, every instance can be pulled out of traffic. Verify how load balancers, ingress, and consumers handle **zero ready endpoints**, valid `503` responses, and failover runbooks. Never replace architectural decisions by blindly adding `db` to every readiness group.

## 19. JMS Listeners and AMQP Consumers

With JMS/AMQP, a broker connection/channel can stay open while consumers fail to process messages; conversely, brief broker outages can be handled by container auto-reconnect.

### 19.1. JMS

Observe:

- Listener container state (started/stopped/failed per API version);
- Connection/session error counts;
- Consume and acknowledgment/transaction outcomes;
- Redelivery attempts / poison messages;
- Pending queue depth or oldest message age where broker metrics exist;
- DLQ backlogs and recovery failures.

If an app primarily serves HTTP requests independent of JMS, a broker outage need not mark HTTP readiness `DOWN`. If the app is strictly a JMS worker, define controller/worker semantics explicitly rather than expecting HTTP readiness to pause listeners automatically.

### 19.2. AMQP

For RabbitMQ or compatible brokers:

- RabbitMQ management/connection health can serve as one signal;
- Consumer ACK/NACK/requeue differs from publisher confirms;
- Queue backlogs and DLX/DLQ need dedicated metrics;
- A `RabbitHealthIndicator` (if auto-configured in your stack) does not prove messages reached consumers or side effects persisted.

### 19.3. Testing Failure Modes

| Fault | Expected indicator/metric |
|---|---|
| Broker restart | Connection error/recovery; app avoids pointless restart loops. |
| Listener stopped | Lifecycle alarm, even if global `/health` stays `UP`. |
| Infinite NACK-requeue | Poison-message/retry alert, not just connection health. |
| DLQ growing | Business processing alert; do not assume the instance died. |
| Quarantine publisher unavailable | High-priority recovery-failure alert. |

## 20. Kafka: Connection Health Does Not Replace Lag, Assignment, or Offset

A Kafka consumer is message-driven with polling and offset commits, which **is not identical** to Spring Integration `PollerMetadata` on a `MessageSource`. Having data in a topic and a running broker does not guarantee the application processed it.

| Layer | Observation point | Meaning |
|---|---|---|
| Broker connectivity | Kafka client/broker request failures | Are technical connections/operations failing? |
| Consumer lifecycle | Listener container running/paused | Is the container ready to receive data per config? |
| Partition assignment | Assigned partition count | Which partitions is this instance responsible for? |
| Consumer lag | Log-end offsets vs. committed/position offsets | Is backlog or consumption delay growing? |
| Processing failures | Handler exceptions/retry counts | Was data received yet failed processing? |
| DLT | DLT records/publish outcomes/oldest age | Are poison messages awaiting intervention? |
| Business confirmation | DB/outbox/target evidence | Were final side effects confirmed? |

### 20.1. Zero Assignments Is Not Always an Error

When replicas outnumber partitions, some consumers legitimately receive **zero assigned partitions**. Treating `assignedPartitions == 0` as liveness `DOWN` causes needless restart loops. Health thresholds must account for group membership, partition count, scaling, and policy.

### 20.2. Lag Is a Metric and Alert, Not Always `Health.DOWN`

Short-lived lag spikes during traffic bursts can be normal. Evaluate consumer lag, oldest-event age, processing latency, and backlog SLOs. Severe lag threatening core SLAs may justify a diagnostic degraded state, provided you define **who acts on it and whether readiness/liveness helps or hurts**.

### 20.3. Offset Commit Is Not Business Completion

A consumer may commit offsets after routing a message to a DLT per policy. That does not mean the business transaction succeeded. Health and reporting should distinguish `PROCESSED`, `RECOVERED_TO_DLT`, `UNKNOWN_OUTCOME`, and `FAILED_WITHOUT_DURABLE_RECOVERY`.

## 21. `MessageChannel` and the Spring Integration Graph

Spring Integration can combine:

- `DirectChannel`: synchronous handler on the sender thread;
- `ExecutorChannel`: asynchronous dispatch via an executor;
- `QueueChannel`: queued for consumer polling;
- publish-subscribe, routing, bridges, aggregators, filters, and gateways.

### 21.1. Don't Just Count "Send Success"

`MessageChannel.send() == true` means only that the channel accepted the message per its semantics; with async executors or queues, downstream can fail later.

A pipeline needs metrics for:

~~~mermaid
flowchart LR
    SRC["Inbound Source"] --> CH["MessageChannel"]
    CH --> H["Handler / Transformer"]
    H --> OUT["Outbound Adapter"]
    OUT --> TARGET["External Target"]
    CH --> Q["Queue/Executor<br/>pending + rejection"]
    H --> ERR["ErrorChannel / Retry"]
    OUT --> RECON["Target readback / reconciliation"]
~~~

### 21.2. Actuator Integration Graph and Management Instrumentation

Depending on version and configuration, Spring Integration integrates with Actuator/Micrometer to expose graphs, metrics, or management endpoints (such as `integrationgraph`). **Do not assume that endpoint exists and is exposed just because Actuator is present.** Verify:

1. Which integration endpoints your Spring Integration and Spring Boot versions support.
2. Whether dependencies and management settings enable them.
3. Whether the endpoint is actually exposed over web/JMX.
4. Whether security policy permits reading topology (graphs can reveal system/channel names).
5. Whether metrics are instrumented at the sources/handlers/channels you need to observe.

Topology graphs help debug wiring and lifecycles, yet they **neither replace health nor guarantee business flows succeed**.

## 22. Health, Metrics, Logs, Traces, and Audit: Use the Right Tool

| Tool | Question | Example |
|---|---|---|
| **Health** | Which operational conditions pass or fail? | Poll heartbeat stale, readiness refusing. |
| **Metrics** | Frequency, rate, errors, backlog, ratios? | Poll count, P95 latency, DLQ oldest age. |
| **Structured logs** | Which event occurred, and what failed? | `eventId`, `endpointId`, error category. |
| **Distributed tracing** | Where did a request/event travel and spend time? | HTTP gateway → handler → DB. |
| **Audit/evidence** | Why was it processed/revoked/redriven, who decided, where is proof? | Quarantine resolution, target readback. |

### 22.1. Incident Example: Health `UP` While Business Fails

~~~text
SFTP poll every 30s: SUCCESS (no exception)
MessageSource returns one file: SUCCESS
CSV parser rejects: UNKNOWN_STATUS
File quarantined: SUCCESS
Business updates applied: 0

Poll health = UP (source is working)
Contract error count rising
Quarantine oldest age rising
Business integration SLO at risk of breach
~~~

The health indicator is not broken: it measures **source polling**, not **business translation**. The mistake is operators treating `UP` as "zero business errors".

## 23. Securing Actuator: Restricting Exposure, Details, and Access

Actuator is a **management plane**, not a public dashboard. End users need business APIs; operators need health status, metrics, and diagnostics under access controls.

### 23.1. Common Risks

| Risk | What to prevent |
|---|---|
| Public `/actuator/env` or `/beans` | Exposing structure/configuration, even if some values are sanitized. |
| Public health details | Exposing DB names, broker addresses, remote hosts, exception messages. |
| State-mutating endpoints | Outsiders altering loggers, config, or management state. |
| Health checks leaking secrets | Logs or responses containing passwords, tokens, or certificate paths. |
| Metrics tagged with personal IDs | Exposing business identifiers and exploding cardinality. |
| Exposing the entire management port | Bypassing application network segmentation/firewalls. |
| Sharing one API key for all probes | Hard to rotate and scope permissions. |

### 23.2. Conditional Details

~~~yaml
management:
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS
~~~

This property **does not provide authentication by itself**. For `when_authorized` to work as intended, configure Spring Security/authorization on management endpoints and roles, and test that unauthorized callers see only permitted status info.

### 23.3. Network Security Before the HTTP Response

- Internal Kubernetes probes must reach health endpoints, which does not mean internet users may access them.
- When using a separate management port, enforce network policies, security groups, and proper ingress rules.
- Restrict `management.endpoints.web.exposure.include` by least privilege.
- If exposing metrics/Prometheus, restrict who can scrape; Prometheus output can reveal service names, brokers, and topology.
- Never put personal data, credentials, or raw event payloads into `Health.withDetail(...)`.

### 23.4. Authentication Can Break Kubelet Probes

When Spring Security protects every actuator endpoint, kubelets calling without tokens may get HTTP `401`/`403` and mark instances unhealthy. Design **internal, narrowly scoped** probe access matching your architecture, and test both unauthorized users and kubelet probes. Never solve this by making all of Actuator public.

## 24. Health Checks Must Have a Resource Budget

Kubernetes calls probes multiple times per minute, Prometheus scrapes periodically, and monitoring tools may also hit `/health`. A health group packed with expensive active checks can amplify load right when upstreams are struggling.

### 24.1. Estimating Load

Example with two replicas, each probed every 5 seconds:

~~~text
Health requests per instance ≈ 12 requests/min
Two replicas ≈ 24 requests/min

If each request opens 3 SFTP sessions and 2 DB connections:
  → up to 72 SFTP opens/min, 48 DB validations/min
  (excluding extra readiness/liveness/monitoring scrapes)
~~~

This back-of-the-envelope calculation shows **cost multiplying by replicas and probe frequency**. Real load depends on requests/endpoints/replicas, caching, and intervals.

### 24.2. Performance Principles

1. **Prefer passive state** for I/O sources already exercised by regular pollers or listeners.
2. **Use active checks sparingly** with strict timeouts, connection pools, and rate limits.
3. **Cache results with a TTL** and document stale semantics clearly.
4. **Never share business flow executors** with heavy health jobs that could starve business work.
5. **Never trigger side effects** such as creating bookings, publishing real events, or deleting files.
6. **Never scan huge backlogs per request**; rely on periodically updated metrics.
7. **Never let one dependency exhaust the time budget** of the entire health group.
8. **Measure health-check latency itself** to catch when probes become a load source.

### 24.3. A Hanging Health Endpoint Is Also a Signal

If a synchronous health indicator waits 60 seconds for an SFTP timeout, kubelet times out externally while Actuator worker threads pile up. Bound every check and define timeout behavior. Run slow checks off the request thread and let `/health` read cached state.

## 25. `DEGRADED`, `UNKNOWN`, and `OUT_OF_SERVICE` States

Spring Boot includes built-in statuses `UP`/`DOWN`/`OUT_OF_SERVICE`/`UNKNOWN`; developers can also define custom `Status` values and aggregation rules. However:

- A custom `DEGRADED` has no built-in standard HTTP status meaning.
- Aggregation order must be defined if it should influence global health.
- HTTP status mappings must be defined per group for custom statuses.
- Kubernetes readiness understands only **success/failure HTTP status codes**, not business semantics inside JSON.

### 25.1. Choosing Status Based on Action

| Observation | Suggested health state | Accompanying action |
|---|---|---|
| No first poll yet on a daily poller | `UNKNOWN` for diagnostics | Wait for schedule / check startup plan. |
| Poller dead and unable to recover | `DOWN` in diagnostics | Restart endpoint or inspect scheduler. |
| App draining intentionally for deploy | `OUT_OF_SERVICE` / readiness refusing | Stop sending new traffic. |
| Partner API slow yet fallback exists | Custom degraded metric/alert | Fail over / rate-limit / retry; do not restart all pods. |
| Mandatory DB unreachable | `DOWN` in dependency/readiness per policy | Isolate traffic, investigate DB. |
| Source healthy while DLQ exceeds SLA | Technical health may stay `UP` | Business alert, redrive/reconciliation. |

### 25.2. Flapping and Hysteresis

If one timeout flips readiness `DOWN` and one success flips it `UP`, health will **flap continuously** on flaky networks. Consider:

- $N$ consecutive failures threshold;
- Time windows;
- Minimum $M$ successful checks before recovery;
- Startup grace periods;
- Error categories and maintenance windows.

Hysteresis is a **risk-based policy** and does not happen automatically when a `HealthIndicator` returns a status. Tests must verify both degradation and recovery so states never get stuck `DOWN` forever.

## 26. Availability Events and Spring Boot Lifecycle

Spring Boot tracks application liveness and readiness via availability APIs (such as `ApplicationAvailability`, `LivenessState`, and `ReadinessState`). A component can publish readiness changes when a workload genuinely needs to stop accepting work:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

final class TrafficDrainCoordinator {
    private final ApplicationEventPublisher events;

    TrafficDrainCoordinator(ApplicationEventPublisher events) {
        this.events = events;
    }

    void stopAcceptingWork() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
    }

    void resumeAcceptingWork() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

**Never publish `REFUSING_TRAFFIC` on a single SFTP partner `503` without a clear policy.** This is an instance/service-level decision. Once controllers remove a pod from traffic, verify:

1. How are in-flight requests drained?
2. Are pollers or broker listeners paused/stopped too?
3. Are pending messages durable?
4. Who or what condition restores `ACCEPTING_TRAFFIC`?
5. Could all instances withdraw from service simultaneously?

### 26.1. Graceful Shutdown

A clean shutdown typically follows:

~~~mermaid
sequenceDiagram
    participant Deploy as Deployment controller
    participant App as ApplicationAvailability
    participant LB as Load balancer
    participant Flow as Spring Integration flows
    participant Source as Source/Broker
    Deploy->>App: Initiate shutdown
    App-->>LB: Readiness REFUSING_TRAFFIC
    Deploy->>Flow: Graceful stop / drain
    Flow->>Source: ACK/commit strictly by outcome
    Flow-->>Deploy: In-flight settled / timed out
    Deploy->>App: Process shutdown
~~~

This sequence is the **target model**; actual behavior depends on `terminationGracePeriodSeconds`, lifecycle phases, listener containers, transactions, and each adapter. Never treat readiness `DOWN` as proof that pending work has finished draining.

## 27. Metrics with Micrometer: Complementing Health

With a Micrometer registry available, instrument poll attempts and failures without altering retry logic:

~~~java
package example.integration.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class PollMetrics {
    private final Counter attempts;
    private final Counter failures;

    public PollMetrics(MeterRegistry registry) {
        this.attempts = Counter.builder("integration.poll.attempts")
                .tag("source", "partner-sftp")
                .register(registry);
        this.failures = Counter.builder("integration.poll.failures")
                .tag("source", "partner-sftp")
                .register(registry);
    }

    public void attempted() {
        attempts.increment();
    }

    public void failed() {
        failures.increment();
    }
}
~~~

Place instrumentation carefully: call `attempts.increment()` **exactly once when starting a source receive**, even when empty. Increment `failures` only when the operation is confirmed failed. With multiple retry layers, separate **source poll attempts, handler retry attempts, and broker redeliveries**.

### 27.1. Recommended Metrics for Integration Pipelines

| Suggested metric | Definition | Usage |
|---|---|---|
| `integration.poll.attempts` | Number of source polls | Confirms poller is still running. |
| `integration.poll.failures` | Number of failed polls | Detects source/connection failures. |
| `integration.messages.received` | Business messages ingested | Distinct from poll attempts. |
| `integration.messages.processed` | Messages handled per contract | Does not guarantee target confirmation. |
| `integration.messages.recovered` | Messages durably sent to quarantine/DLT | Distinguishes from business success. |
| `integration.backlog.oldest.age` | Age of oldest pending event | Detects stuck data. |
| `integration.retry.attempts` | In-process retries | Detects retry storms. |
| `integration.target.confirmations` | Verified final outcomes | Business success rate. |

These names are **illustrative conventions**, not metrics automatically emitted everywhere. Check built-in metrics provided by your framework and Micrometer version to avoid double-counting.

### 27.2. Never Use Request IDs as Metric Tags

`eventId`/`traceId` have near-infinite cardinality and must never become time-series metric tags. Keep tags low-cardinality such as `sourceType`, `endpointId`, `result`, and `errorCategory`; put detailed correlation in authorized traces and logs.

### 27.3. Prometheus Endpoint Is Not Public by Default

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Enable this only in environments **with a Prometheus registry and access/network controls**. Without the matching registry, `/actuator/prometheus` will not exist. Other monitoring backends can collect metrics without exposing Prometheus over HTTP.

## 28. Unit Testing Custom `HealthIndicator` with a Controllable `Clock`

Never write `Thread.sleep(180_000)` in a unit test to wait for a heartbeat to expire. Inject `Clock` as designed above and advance time in tests.

### 28.1. A Step-Advanceable Fake Clock

~~~java
package example.integration.health;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

final class MutableClock extends Clock {
    private final AtomicReference<Instant> now;
    private final ZoneId zone;

    MutableClock(Instant initial) {
        this(initial, ZoneOffset.UTC);
    }

    private MutableClock(Instant initial, ZoneId zone) {
        this.now = new AtomicReference<>(initial);
        this.zone = zone;
    }

    void advance(Duration duration) {
        now.updateAndGet(old -> old.plus(duration));
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId requestedZone) {
        return new MutableClock(now.get(), requestedZone);
    }

    @Override
    public Instant instant() {
        return now.get();
    }
}
~~~

Here `withZone(...)` returns a **snapshot copy** for simple tests; if tests need two clocks sharing the same mutable time across `withZone`, share the `AtomicReference` explicitly. The goal is eliminating wall-clock/CI flakiness.

### 28.2. Testing No-Poll, Empty-Poll, Stale, and Recovery

~~~java
package example.integration.health;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;
import org.springframework.integration.core.MessageSource;

class PollHealthIndicatorTest {

    @Test
    void emptyPollIsStillSuccessfulButStalePollIsDown() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-23T09:00:00Z"));
        PollMonitor monitor = new PollMonitor(clock);
        PollHealthIndicator indicator =
                new PollHealthIndicator(
                        monitor, clock, Duration.ofMinutes(3));

        assertEquals(Status.UNKNOWN,
                indicator.health().getStatus());

        MessageSource<String> empty = () -> null;
        ObservedMessageSource<String> source =
                new ObservedMessageSource<>(empty, monitor);

        assertNull(source.receive()); // Empty source, poll succeeded.
        assertEquals(Status.UP,
                indicator.health().getStatus());

        clock.advance(Duration.ofMinutes(4));
        assertEquals(Status.DOWN,
                indicator.health().getStatus());

        assertNull(source.receive()); // Subsequent poll succeeds.
        assertEquals(Status.UP,
                indicator.health().getStatus());
    }

    @Test
    void sourceExceptionIsNotSwallowed() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-23T09:00:00Z"));
        PollMonitor monitor = new PollMonitor(clock);
        MessageSource<String> failing = () -> {
            throw new IllegalStateException("test failure");
        };

        ObservedMessageSource<String> source =
                new ObservedMessageSource<>(failing, monitor);

        assertThrows(IllegalStateException.class, source::receive);
        assertEquals(1,
                monitor.snapshot().consecutiveFailures());
        assertNull(monitor.snapshot().lastSuccessfulPoll());
    }
}
~~~

**What this test proves:** the decorator/indicator health logic works against a controlled clock. **It does not prove** a real SFTP server or scheduler is running. This is a unit test, not network integration.

### 28.3. Failure After a Successful Poll

If `successfulPoll` occurs at 09:00 and a failure occurs at 09:01, the indicator can remain `UP` until `maxSilence` elapses. That is the **chosen rule** (stale heartbeat), not necessarily a bug. If the app requires going `DOWN` immediately after $N$ consecutive failures, add that threshold, test that policy, and guard against unnecessary flapping.

## 29. Spring Boot Test: Verifying the HTTP Health Endpoint Returns Properly

Seeing `HealthIndicator.health()` return `DOWN` in a unit test does not prove the probe returns HTTP 503, because health groups may be configured differently or omit the indicator. Thus **HTTP-level Actuator tests** are essential.

### 29.1. `MockMvc` Pattern for Spring MVC Applications

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoint.health.probes.enabled=true",
        "management.endpoints.web.exposure.include=health"
})
@AutoConfigureMockMvc
class ActuatorHealthHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void exposesLivenessAndReadinessStatus() throws Exception {
        mvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));

        mvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

This test assumes the application context started cleanly and availability states are `CORRECT`/`ACCEPTING_TRAFFIC`. **If the app uses security filters, custom health groups, a non-default servlet path, or failing readiness dependencies**, adjust fixtures/authorization per contract. Never set `@AutoConfigureMockMvc(addFilters = false)` to disable security in tests meant to verify security.

### 29.2. Testing Readiness `REFUSING_TRAFFIC`

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.web.servlet.MockMvc;

class ReadinessBehaviorSnippet {

    @Autowired MockMvc mvc;
    @Autowired ApplicationEventPublisher events;

    @Test
    void refusingTrafficProducesUnavailableReadiness() throws Exception {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
        try {
            mvc.perform(get("/actuator/health/readiness"))
                    .andExpect(status().isServiceUnavailable())
                    .andExpect(jsonPath("$.status")
                            .value("OUT_OF_SERVICE"));
        } finally {
            AvailabilityChangeEvent.publish(
                    events, ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

This is a **test fragment**: to execute it, place it inside a class annotated with `@SpringBootTest` and `@AutoConfigureMockMvc` with proper configuration. Restore availability in `finally` so Spring Test context caching does not pollute subsequent tests. Isolate tests if multiple availability-mutating tests run in parallel on the same context.

### 29.3. Testing Global `/health` vs. Groups

Register a custom health indicator returning `DOWN` and compare:

- `GET /actuator/health`: aggregated status across contributors.
- `GET /actuator/health/liveness`: liveness group only per config.
- `GET /actuator/health/readiness`: readiness group per config.
- `GET /actuator/health/integrations`: integration group containing that indicator.

Tests should assert **both JSON status and HTTP status**, never just one. Especially for `UNKNOWN` or custom statuses, assert the actual mapping rather than guessing.

## 30. Testing Auth and Data Disclosure on Management Endpoints

Suppose an app requires:

- Internal kubelet: reads `/health/liveness` and `/health/readiness`.
- `OPS` operator: reads `/health/integrations` with needed details.
- Unauthorized users: **cannot** view sensitive config or topology.

### 30.1. Security Test Cases

| Caller | Endpoint | Expected |
|---|---|---|
| Permitted internal probe | `/actuator/health/liveness` | HTTP success when state is `UP`. |
| Internal probe | `/actuator/health/readiness` | Exact HTTP mapping for `UP`/`OUT_OF_SERVICE`. |
| Anonymous from public interface | `/actuator/env` | Access denied. |
| Anonymous | `/actuator/health/integrations` | Public status only or blocked per policy. |
| `OPS` operator | Diagnostic health group | Views policy-redacted details. |
| Non-`OPS` user | Diagnostic health group | Cannot view internal details. |
| Any caller | Any health response | **Zero** tokens, passwords, or connection strings. |

Do not treat HTTP 200 for anonymous health checks as a security flaw if the contract intentionally allows **minimal status** on an internal endpoint. The risk lies in **external exposure and returned details**, not status code alone.

### 30.2. `MockMvc` Does Not Test Network Policy

`MockMvc` verifies Spring Security filters and HTTP mappings inside the JVM; it does not test Kubernetes `NetworkPolicy`, Ingress, firewalls, mTLS proxies, or real management-port routing. Verify the deployment/network layer as well for production.

## 31. Testing Outage and Recovery by Adapter

Run fault tests in **isolated environments**, never by disconnecting production:

| Fault injection | What to measure | What must NOT happen |
|---|---|---|
| SFTP server offline | Last poll success/failure, reconnect | Health checks opening session storms. |
| HTTP partner returns `503` | Failure rate, latency, circuit breaker | All pods flipping liveness `DOWN` needlessly. |
| DB briefly unavailable | DB contributor, readiness policy, recovery | ACKing inbound data before transactions commit. |
| Kafka broker restart | Consumer reconnect/lag, retries | Pod restart loop while broker is recovering. |
| JMS consumer stopped | Lifecycle state, backlog | `/health UP` mistaken for active message processing. |
| AMQP poison message | DLQ, redelivery attempts | Silent infinite NACK-requeue loop without alerts. |
| File permission denied | Poll failures, error channel | Returning `null` and logging fake poll success. |
| Endpoint stop/start | Lifecycle state, heartbeat reset | Stale state falsely staying `UP` forever. |
| Graceful shutdown | Readiness transition, in-flight drain | New traffic continuing to arrive. |
| Disk full | Disk health and File processing | Health check writing test files and worsening disk full. |

### 31.1. Specify Test Tiers Explicitly

- **Unit:** test monitor/indicator logic with a fake clock.
- **Flow integration:** test pollers, channels, and error paths inside Spring context.
- **Transport integration:** use test SFTP server / HTTP stub / broker / DB.
- **Deployment:** test real pods, management ports, networks, and probes.
- **Business E2E:** verify final data, offsets, ACKs, and reconciliation where needed.

A health group returning `DOWN` in a unit test does not prove Kubernetes **actually** pulled the instance from traffic. That proof belongs to deployment/cluster testing.

## 32. Health Endpoint and Actuator Test Matrix

| # | Scenario | Layer | Required evidence |
|---:|---|---|---|
| 1 | Actuator starter present | Spring context | Health endpoint registered properly. |
| 2 | Minimal health exposure | HTTP/security | Only permitted endpoints are reachable. |
| 3 | Default health `UP` | HTTP | Matching JSON and HTTP code. |
| 4 | Global contributor `DOWN` | HTTP | Global aggregation reflects it accurately. |
| 5 | Custom `UNKNOWN` status | HTTP | HTTP mapping verified, not misassumed. |
| 6 | Liveness group | HTTP | Independent of integration diagnostics if designed so. |
| 7 | Readiness `ACCEPTING_TRAFFIC` | HTTP | Probe succeeds per policy. |
| 8 | Readiness `REFUSING_TRAFFIC` | HTTP | `OUT_OF_SERVICE`, `503` per mapping. |
| 9 | Readiness does not auto-include all deps | Context/HTTP | Only explicitly included contributors appear. |
| 10 | Readiness includes mandatory `db` | Context/HTTP | Policy and aggregation verified. |
| 11 | `integrations` group has valid members | Context | Startup and endpoint succeed with no missing IDs. |
| 12 | Indicator before first poll | Unit | `UNKNOWN` per contract. |
| 13 | First poll empty | Unit | Recorded as a successful poll. |
| 14 | Poll returns one message | Unit/flow | Health heartbeat updates without altering payload. |
| 15 | Poll source throws | Unit | Exception propagates; failure state increments. |
| 16 | Poll heartbeat stale | Clock unit | Status turns `DOWN` per threshold. |
| 17 | Poll succeeds after stale | Clock unit | Health recovers to `UP`. |
| 18 | $N$ consecutive failures | Unit | Threshold/hysteresis matches design. |
| 19 | Poller stopped | Flow | Lifecycle/alert differs from empty poll. |
| 20 | Poller running yet handler fails | Flow | Never reports false business success. |
| 21 | File directory loses permissions | File integration | Clear error and recovery behavior. |
| 22 | SFTP no new files | SFTP integration | Not treated as a remote outage. |
| 23 | SFTP remote unreachable | SFTP integration | Error category, backoff, and health policy match. |
| 24 | SFTP wrong host key | Security/integration | Never disables verification. |
| 25 | HTTP health check read-only | HTTP transport | Creates zero business side effects. |
| 26 | HTTP `503` from partner | HTTP integration | Diagnostic error without restart storms. |
| 27 | HTTP `POST` timeout | E2E | Unknown outcome tracked; idempotency/readback verified. |
| 28 | DB connection failure | DB integration | DB contributor / readiness policy verified. |
| 29 | JDBC inbox backlog | DB/metrics | Pending age metric used; no heavy probe queries. |
| 30 | JMS broker restart | JMS integration | Listener recovers per policy. |
| 31 | JMS queue poison message | JMS integration | DLQ/backlog triggers alert. |
| 32 | AMQP requeue loop | AMQP integration | Retry storm bounded and alerted. |
| 33 | Kafka consumer assignment = 0 valid | Kafka integration | Does not falsely fail liveness. |
| 34 | Kafka lag exceeds SLO | Metrics/operations | Alert and owner triggered, not just health status. |
| 35 | Kafka DLT publish failed | Broker integration | Recovery failure detected. |
| 36 | Separate main/management ports | Deployment | Probes hit intended port/path. |
| 37 | `/livez`/`/readyz` extra paths | Deployment | Actual paths reachable if supported. |
| 38 | Kubelet access policy | Security/deployment | Probes succeed; public details blocked. |
| 39 | Slow health indicator | Load test | Bounded timeout; avoids unbounded resource hold. |
| 40 | Aggressive health scraping | Load test | Causes zero SFTP session storms. |
| 41 | Startup probe during cold start | Deployment | No premature restart within startup budget. |
| 42 | Readiness during graceful shutdown | Deployment | Stops new traffic; drains in-flight work. |
| 43 | Spring Integration graph | Context/security | Exposed only if supported and authorized. |
| 44 | Micrometer counters | Unit/metrics | Attempts distinct from messages; bounded tags. |
| 45 | Error detail with secret | Security | Passwords/tokens absent from responses/logs. |
| 46 | Shared outage across replicas | Deployment | Replicas avoid synchronized pointless restarts. |
| 47 | Spring Test context caching | Spring Test | Health/availability states never leak across tests. |
| 48 | Quarantine backlog rising | E2E/metrics | Alerts fire even when source health is `UP`. |
| 49 | Custom `DEGRADED` probe status | HTTP | Code mapping and aggregation tested. |
| 50 | Recovery after error and restart | Recovery/E2E | Data, ACKs, and target evidence verified accurate. |

Each test must record **initial state, action, data source, threshold, expected status and HTTP code, timeout, and teardown**. Writing merely "Actuator returned 200" is insufficient to prove operational health.

## 33. Case Study: SFTP → DB → Kafka App Running on Kubernetes

### 33.1. Context and Goals

A Spring Boot app runs two replicas:

1. Polls SFTP every 30 seconds for ready partner files.
2. Parses files and updates inbox/orders tables in PostgreSQL.
3. After commit, writes an outbox event.
4. Publisher sends events to Kafka and updates outbox status.
5. Dashboards monitor data latency, pending/failed files, and Kafka backlog.

Risks: SFTP undergoes maintenance, the database occasionally slows down, and Kafka brokers rebalance; we do not want to restart the entire application merely because an external system blips.

~~~mermaid
flowchart TD
    PARTNER["Partner SFTP<br/>ready files"] --> POLL["SFTP inbound poller"]
    POLL --> PARSE["Parse + validate"]
    PARSE --> DB["PostgreSQL inbox/orders"]
    DB --> OUTBOX["Outbox publisher"]
    OUTBOX --> KAFKA["Kafka topic"]

    POLL --> PH["Passive poll heartbeat"]
    DB --> DH["DB connectivity"]
    OUTBOX --> METRIC["Pending/confirmations metrics"]
    KAFKA --> METRIC
    PH --> ACT["Actuator integration health"]
    DH --> ACT
    ACT --> OPS["Operator diagnostics"]
    METRIC --> ALERT["SLO alerts"]

    READY["Readiness state<br/>+ selected mandatory deps"] --> KUBE["Kubernetes readiness"]
    LIVE["Liveness state"] --> KUBE
~~~

### 33.2. Define Both Sides of "Healthy" Clearly

**Technical availability:** service/process, Spring context, mandatory DB connectivity, inbound poller lifecycle, SFTP sessions within thresholds.

**Business throughput:** backlogged ready files, unprocessed rows, target confirmations, oldest pending item, Kafka outbox lag, and reconciliation.

Health cannot replace business throughput SLOs; display them side by side.

### 33.3. Recommended Health Policy

| Component | Health/metric | Drives liveness `DOWN`? | Drives readiness `DOWN`? |
|---|---|---|---|
| Spring Boot `livenessState` | Liveness group | Per availability | Not applied directly. |
| Spring Boot `readinessState` | Readiness group | No | Per availability. |
| PostgreSQL | DB contributor + connection failures | Not by default | Possibly yes if every workload requires DB. |
| SFTP poller | Passive heartbeat + outage duration | No | Not by default; consider if ingestion-only. |
| File backlog | Oldest file age, pending count | No | Usually metric/alert instead of readiness. |
| Kafka outbox | Oldest pending, publisher failures | No | Depends on pipeline; usually ops alert. |
| DLQ/quarantine | Count / oldest age | No | Not by default; assign owner. |

This is **one proposal**, not universal truth. If a service performs ingestion only with no REST traffic, readiness probes may not govern Kafka/SFTP intake automatically; coordinate consumer/poller lifecycles explicitly.

### 33.4. Scenario A — 15-Minute SFTP Outage

**Observed:**

~~~text
12:00  SFTP poll OK, receive() returns null
12:01  DNS/TCP timeouts begin
12:02  consecutiveFailures rises
12:04  lastSuccessfulPoll exceeds heartbeat threshold
12:05  /health/integrations shows partnerSftp DOWN
12:15  SFTP recovers
12:16  poll succeeds, health returns to UP
~~~

**Expected:**

- Do not mistake `receive() == null` for failure.
- Diagnostic health goes `DOWN` only per agreed policy.
- Liveness stays `UP` as long as the app can self-recover.
- Metrics/alerts report SFTP unavailable, backlog, and oldest age.
- Global HTTP 503 does not trigger a pod restart loop if Kube liveness queries the right group.
- Upon recovery, backlogged files process with filters/idempotency without duplicating DB records.

### 33.5. Scenario B — PostgreSQL Outage

If the service cannot commit domain transactions:

1. Check connection pool / DB health and readiness policy.
2. Stop accepting new work or apply backpressure if needed.
3. Never ACK/checkpoint inbound messages prior to durable persistence per contract.
4. Reconnect with retry/backoff rather than spawning thousands of concurrent attempts.
5. Read back targets and outbox/inbox after recovery to verify zero data loss.

Never treat `db Health UP` as proof that business commits succeed; a DB user/role may pass connection checks yet lack write permissions on tables.

### 33.6. Scenario C — Kafka Broker Outage

If DB commits succeed while outbox events remain unpublished:

- App HTTP liveness/readiness may remain unchanged depending on workload.
- Outbox pending age and publisher failures rise.
- SLO alerts fire instead of "restarting pods hoping Kafka fixes itself".
- Once brokers recover, the publisher replays outbox rows using designed idempotency and producer semantics.
- Final completion is measured by Kafka publish confirmations and eventual consumer processing per business needs.

### 33.7. Scenario D — CSV Schema Changes

SFTP polls, downloads, and DB may all stay healthy while the parser hits an unexpected field on every file:

- `/health/integrations` may stay `UP`.
- `contract_errors_total` and quarantine backlog climb.
- Alerts must classify contract errors (avoiding pointless network retries).
- After updating the translator, redrive files/events with clear ownership and audit trails.

This is the clearest illustration of **technical health's** boundaries.

## 34. Operational Runbook When `/actuator/health` Is `DOWN`

A health alert is useful only when operators know **what to do next**.

### 34.1. Diagnostic Workflow

~~~mermaid
flowchart TD
    A["Probe DOWN / unhealthy"] --> TYPE{"Which endpoint?"}
    TYPE -- "Liveness" --> L["Check fatal process state,<br/>threads, OOM, startup/shutdown"]
    TYPE -- "Readiness" --> R["Check availability state,<br/>required dependencies"]
    TYPE -- "Integrations" --> I["Check adapter/partner<br/>poll heartbeat + errors"]
    L --> ACTION["Pick action per runbook"]
    R --> ACTION
    I --> ACTION
    ACTION --> VERIFY["Verify recovery and backlog"]
~~~

### 34.2. Step-by-Step Procedure

1. **Identify the endpoint:** global `/health`, `/health/liveness`, `/health/readiness`, or a custom group?
2. **Check HTTP code and JSON status:** don't rely solely on a red UI badge; check the mapping.
3. **Identify the contributor:** DB, disk, passive poller, `readinessState`, or custom indicator.
4. **Cross-check metrics:** source attempts, failures, last success, backlog, DLQ, latencies.
5. **Read correlated logs/traces:** keep tenant/source/version context; never expose secrets.
6. **Check endpoint state:** poller/listener running, stop phase, partition assignment, connection recovery.
7. **Classify failure:** fatal instance issue, dependency outage, contract violation, expected idle period, unknown outcome.
8. **Choose the right action:** restart instances only when appropriate; usually reconnect, fix config, pause/resume, redrive, or escalate vendor incident.
9. **Reconcile data:** never close an incident merely because health returned `UP` while aged backlog remains.
10. **Update SLOs/runbooks:** if the alert was a false positive from a long cron or `UNKNOWN` state, tune the policy with tests.

### 34.3. When Should You NOT Restart?

Do not mass-restart pods when:

- An HTTP/SFTP partner has a broad outage;
- A Kafka cluster is recovering or performing normal rebalances;
- Backlog spikes during a burst while workers are actively draining;
- Scheduled DB maintenance triggers expected retry/backoff;
- Health checks failed due to an overly tight probe timeout or heavy active checks;
- A new message contract hasn't been supported in the translator yet.

Restarts flush caches, interrupt in-flight work, and can create extra duplicates. Reserve liveness for failures where **a restart is genuinely a useful recovery mechanism**.

### 34.4. Closing Incidents with Evidence

Close an incident only when:

- Relevant health/groups return to expected states and hold steady for an observation window.
- Pollers/consumers actually resumed work, not just bean running flags.
- Pending counts, backlog, and oldest ages trend back within acceptable bounds.
- Error/quarantined items are resolved or have explicit owners, SLAs, and tracking states.
- Final side effects are read back or verified per business contract.
- Root cause and preventive actions are documented for severe incidents.

## 35. Common Anti-Patterns

| Anti-pattern | Why it is dangerous | Fix |
|---|---|---|
| Kubernetes liveness hitting global `/health` | External SFTP/DB outages restart all pods. | Call `/health/liveness` with fatal-only checks. |
| Readiness including every partner | Shared outages take down the entire service. | Include only mandatory dependencies per traffic/role. |
| Treating `isRunning() == true` as healthy flow | Stuck schedulers still report running. | Monitor poll heartbeats, throughput, and lag. |
| Counting only arrived messages for heartbeat | Legitimately idle sources look `DOWN`. | Count successful empty polls returning `null`. |
| Catching poller exceptions and returning `null` | Masks connection failures as "no data". | Rethrow; handle via error channels. |
| Health endpoint opening SFTP sessions per call | Probe storms overload servers. | Use passive/cached/timeout-bounded checks. |
| Probe writing test files into input dir | Creates fake messages or triggers ingestion. | Keep checks safe and side-effect-free. |
| Health calling order-creating HTTP `POST` | Causes unwanted business side effects. | Use read-only endpoints or passive metrics. |
| Health running `COUNT(*)` on massive tables | Hammers DB during outages. | Use bounded/cached queries or separate metrics. |
| Assuming `UNKNOWN` always fails probes | HTTP code may still be `200`. | Test status-to-HTTP mappings explicitly. |
| Unconfigured custom `DEGRADED` status | Probes may treat it as OK. | Define explicit aggregation and status mappings. |
| Exposing all management endpoints publicly | Leaks topology/config; risks mutations. | Allowlist exposure with auth/network controls. |
| `show-details: always` on the internet | Leaks hostnames, exceptions, and secrets. | Minimal public info; authorized diagnostics only. |
| Kubelet getting `401` reported as app `DOWN` | Broken probe/security setup. | Design internal probe access and test auth. |
| Separate management port yet probes hit main port | Routes wrongly or hides main server failures. | Verify ports/paths or additional probe paths. |
| Treating health HTTP `200` as business success | DLQ/backlogs can still pile up. | Add target verification and business alerts. |
| Disabling probes to "fix" false positives | Blinds operations. | Fix the signal, threshold, or action instead. |
| Unit-testing indicator method without HTTP test | HTTP code / group mapping may be wrong. | Add `MockMvc`/HTTP integration tests. |
| Using `Thread.sleep` to test stale heartbeats | Flaky and slow CI. | Inject `Clock` / fake time. |
| Tagging metrics with `eventId` | High cardinality explodes cost. | Keep tags bounded; put IDs in traces/logs. |
| Not resetting readiness state between tests | Pollutes cached Spring test contexts. | Restore in `finally` or isolate contexts. |
| Contract quarantine errors turning technical health `DOWN` | Mixes technical and business concerns. | Separate technical health from cause-specific metrics/alerts. |

## 36. Hands-On Exercises

### Exercise 1 — Enable Actuator and Identify Health Groups

Create a Spring Boot app using `spring-boot-starter-actuator`.

Requirements:

1. Expose only `health` and `info` over internal HTTP.
2. Enable `liveness`/`readiness` for your Boot version.
3. Query all three health endpoints and record HTTP codes and JSON bodies.
4. Distinguish `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`.
5. Verify an unexposed endpoint cannot be accessed improperly.

### Exercise 2 — Custom `PollHealthIndicator`

Implement `PollMonitor`, `ObservedMessageSource<T>`, and `PollHealthIndicator` per the examples.

Requirements:

1. `receive()` returning `null` still advances the success heartbeat.
2. Exceptions increment failure counts and propagate cleanly.
3. Before the first poll, health returns `UNKNOWN`.
4. Past the stale threshold, health returns `DOWN`.
5. After another successful poll, health returns `UP`.
6. Use a fake `Clock` instead of `Thread.sleep`.

### Exercise 3 — Health Group Isolated from Liveness

Create a `partnerSftpHealthIndicator` controllable to `DOWN` via a test fixture.

Requirements:

1. Custom `integrations` group includes the indicator.
2. Verify global `/health` and the integration group reflect `DOWN` per config.
3. `/health/liveness` remains `UP` while the process is healthy.
4. `/health/readiness` follows your chosen policy.
5. Assert both **JSON status and HTTP code**.

### Exercise 4 — File/SFTP Polling and Backlog

Build a File inbound adapter reading `@TempDir` or a test SFTP server.

Requirements:

1. Poll an empty directory without false errors.
2. Create a `*.ready` file and verify message ingestion.
3. Disconnect SFTP or revoke directory permissions and inspect failure metrics/health.
4. Route a schema-invalid file to quarantine and explain why poll health can stay `UP`.
5. Measure oldest pending age and design a dedicated alert.
6. Restart the poller and verify filters/checkpoints/idempotency.

### Exercise 5 — HTTP and JDBC Dependencies

Build an HTTP outbound gateway to a stub server and a JDBC inbox on a test DB.

Requirements:

1. Stub `200`, `429`, `503`, and timeouts; observe transport metrics.
2. Prove active health checks are read-only and create no test orders.
3. Stop the DB and inspect the `db` contributor when a `DataSource` is configured.
4. Evaluate adding `db` to readiness and measure what happens when all instances turn unready.
5. Verify `db` connection `UP` does not guarantee business rows committed.

### Exercise 6 — JMS/AMQP/Kafka Consumer Observability

Pick an isolated broker:

1. Start the consumer, receive, and process a message.
2. Restart the broker and verify listener/container recovery.
3. Inject a failing message and verify redelivery/DLQ/DLT.
4. Compare connection health, consumer running state, lag/queue depth, and business confirmation.
5. Explain why ACK/offset alone cannot prove business outcomes.
6. Design alerts for poison-message loops and oldest pending items.

### Exercise 7 — Kubernetes Deployment Probes

Design a manifest for a slow-starting app where the management port may differ from the main port.

Requirements:

1. Startup probe covers warmup; liveness covers fatal states only.
2. Readiness aligns with the intended traffic/workload.
3. Verify the actual `/actuator/health/readiness` or `/readyz` path and port.
4. Simulate an SFTP outage and prove zero pod restart loops occur.
5. Simulate graceful shutdown with in-flight processing.
6. Justify thresholds and timeouts from baselines instead of copying arbitrary numbers.

### Exercise 8 — Runbook and SLO

An SFTP partner delivers files every 15 minutes; results must appear on Kafka within an agreed business SLA.

Requirements:

1. Define an SLO for **`availableAt → confirmedAt`**.
2. Choose health indicators for poll/source and metrics for backlog/lag.
3. Propose a stale-heartbeat threshold aligned with the poll schedule.
4. Design alerts for when health is `UP` yet business outcomes lag.
5. Write a runbook covering triage, rollback, redrive, reconciliation, and incident closure.
6. Assign ownership and specify logging/display boundaries.

## 37. Health/Actuator Acceptance Checklist for Integration Services

- [ ] **Clear definitions** exist for liveness, readiness, and integration dependency health.
- [ ] **Actuator starter is present**, aligned with Boot/Integration versions.
- [ ] **Management endpoints use minimal exposure**, avoiding unintended public diagnostics.
- [ ] **Health details are governed** by security and network policies.
- [ ] **`UP`/`DOWN`/`OUT_OF_SERVICE`/`UNKNOWN` meanings are clear.**
- [ ] **HTTP status mapping is tested**, including custom statuses.
- [ ] **Health groups are intentional**, keeping external dependencies out of liveness.
- [ ] **Kubernetes probes hit the right endpoint/port/path**, including with separate management ports.
- [ ] **Startup probes and graceful shutdown** are accounted for.
- [ ] **Readiness governs the intended workload**, never confused with auto-pausing Kafka/SFTP.
- [ ] **Custom `HealthIndicator`s cause zero side effects.**
- [ ] **Active checks have bounded timeouts, caching, and cost.**
- [ ] **Poll heartbeats distinguish empty sources from stopped pollers.**
- [ ] **Source exceptions are never swallowed as `null`.**
- [ ] **SFTP/HTTP/File/JDBC/JMS/AMQP/Kafka have protocol-specific signals**, not just bean running flags.
- [ ] **DB health is never treated as proof of business commits.**
- [ ] **Broker ACKs/offsets are kept distinct from business confirmations.**
- [ ] **Lag, backlog, and DLQ/quarantine have dedicated metrics/alerts.**
- [ ] **Metric tags have bounded cardinality and zero secrets/PII.**
- [ ] **Unit tests use a fake `Clock`**, never `sleep` for stale durations.
- [ ] **HTTP tests cover global, liveness, readiness, and diagnostic groups.**
- [ ] **Tests cover startup, outage, recovery, stop/restart, and auth.**
- [ ] **Transport integration/deployment tests exist where SLAs require**, beyond mocks.
- [ ] **Every `DOWN` state has a defined action and owner**, preventing restart storms.
- [ ] **Runbooks require business reconciliation before closing incidents.**
- [ ] **Fixtures and endpoint states are cleaned up after tests**, avoiding context-cache leaks.

## 38. Summary

Spring Boot **Actuator Health endpoints** are essential for operating **Spring Integration Adapters**, yet they are trustworthy only when every signal has a **clear meaning, scope, and paired action**. `/actuator/health` aggregates contributors; `liveness`/`readiness` orchestrate instance lifecycles; **health groups** separate integration diagnostics from traffic-acceptance gates.

In applications integrating **File, SFTP, HTTP, JDBC, JMS, AMQP, and Kafka**, never equate "endpoint running", "HTTP 200", "empty poll", "broker ACK", or "DB connection UP" with end-to-end business completion. A passive `HealthIndicator` wrapping `MessageSource` tracks poll health without opening external connections on every probe, while **throughput, lag, pending age, duplicates, DLQs, and target confirmations** require dedicated metrics, tracing, auditing, and reconciliation.

On Kubernetes, keep **liveness** focused on failures that truly require a restart, tie **readiness** to capacity to accept workload, and keep **integration diagnostics** for deep operations. Test **indicator logic, HTTP mappings, security, transport outages, and deployment probes** so a partner outage never triggers a restart loop — and so an `UP` badge never hides stuck data.

When looking at a dashboard, the question is never just "is the app alive?", but **should it accept more work, which adapter stopped making progress, which messages remain unconfirmed at targets, who owns remediation, and what evidence proves recovery**.
