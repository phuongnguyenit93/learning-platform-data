# Startup State in Spring Boot

When a Spring Boot instance starts up, the process may have already opened a port, yet the application may not be ready to serve requests. Beans may still be initializing, caches may not be warmed, schema checks may not have completed, or connections to essential dependencies may not yet be verified. If a load balancer sends traffic too early, users may receive errors even though the container is in the running state. **Startup state** describes the phase during which an application transitions from initialization to being ready to accept traffic, helping Spring Boot, Actuator, and the orchestrator coordinate at the right moment.

In the **SPRING_BOOT_OBSERVABILITY** module, startup state belongs to the **Health and readiness** chapter, connecting health endpoints, liveness/readiness, metrics, logs, and tracing. This lesson focuses on Spring Boot's application availability state: lifecycle events, `ApplicationAvailability`, `LivenessState` and `ReadinessState`, readiness transitions, warm-up/initialization, asynchronous startup, Kubernetes probes, graceful shutdown, testing, and troubleshooting.

## Learning objectives

1. Describe the startup phases of a Spring Boot application.
2. Distinguish a running process from a ready application.
3. Use `ApplicationAvailability` to read liveness/readiness state.
4. Understand `AvailabilityChangeEvent` and `LivenessState`/`ReadinessState`.
5. Control readiness during warm-up and startup tasks.
6. Integrate Kubernetes startup/readiness probes.
7. Avoid blocking startup or receiving traffic before essential dependencies are ready.
8. Combine readiness with graceful shutdown and traffic draining.
9. Test startup transitions and startup failure scenarios.

## 1. What is startup state?

Startup state is the operational state of an application as it transitions from a newly started process to an instance capable of receiving traffic. In Spring Boot, application availability is represented via states such as liveness and readiness. These states allow external components to ask the right questions:

- Is the process/application still functioning or has it entered a state requiring a restart?
- Is the instance ready to receive requests?
- Is the instance warming up, refusing traffic, or shutting down?

An open port or an existing JVM does not mean the application is ready. Similarly, a health endpoint returning UP at one point in time does not replace the application's readiness policy.

### 1.1. Common startup phases

~~~mermaid
flowchart TD
    Start["JVM process starts"] --> Context["Spring ApplicationContext refresh"]
    Context --> Beans["Create beans and infrastructure"]
    Beans --> Started["ApplicationStartedEvent"]
    Started --> Runners["ApplicationRunner / CommandLineRunner"]
    Runners --> Ready["ApplicationReadyEvent"]
    Ready --> Accept["Readiness: ACCEPTING_TRAFFIC"]
    Accept --> Serve["Serve requests"]
    Serve --> Stop["Shutdown begins"]
    Stop --> Refuse["Readiness: REFUSING_TRAFFIC"]
    Refuse --> Drain["Drain in-flight requests"]
    Drain --> Exit["Process exits"]
~~~

This is a high-level diagram. Lifecycle events have specific ordering and semantics in Spring Boot; the application must distinguish context refresh, runner completion, and readiness transitions.

### 1.2. Process state, liveness, and readiness

| Concept | Question | Typical action |
| --- | --- | --- |
| Process running | Is the JVM/container still running? | Runtime/container status |
| Liveness | Can the application continue operating? | Restart if probe fails |
| Readiness | Should the instance receive traffic? | Add/remove from service endpoints |
| Startup probe | Has the application passed the startup phase? | Defer liveness/readiness checks |

Do not use a single signal to represent every state. Kubernetes can see a running process while readiness remains false.

## 2. ApplicationAvailability in Spring Boot

Spring Boot provides `ApplicationAvailability` to read the application's current availability state. Key states:

- `LivenessState`: `CORRECT` or `BROKEN`.
- `ReadinessState`: `ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC`.

Example reading state:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityReporter {
    private final ApplicationAvailability availability;

    public AvailabilityReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public void report() {
        LivenessState liveness = availability.getLivenessState();
        ReadinessState readiness = availability.getReadinessState();

        // Send these states to an internal diagnostic logger if needed.
    }
}
~~~

`ApplicationAvailability` reflects the state published in the application context. It does not actively ping every dependency and does not decide business readiness on its own.

### 2.1. LivenessState

`CORRECT` indicates the application has not reported a broken state. `BROKEN` indicates the application is in a state where it cannot continue normally and may require a restart.

Do not switch liveness to `BROKEN` simply because a database or remote API is temporarily unavailable. If all replicas restart together due to a shared dependency, the outage can worsen.

### 2.2. ReadinessState

`REFUSING_TRAFFIC` indicates the instance should not receive traffic yet. `ACCEPTING_TRAFFIC` indicates the instance can receive traffic according to the readiness policy.

During startup, Spring Boot manages readiness transitions according to its lifecycle. Applications can publish `AvailabilityChangeEvent` to transition states when custom initialization steps must complete or when shutdown begins.

## 3. Lifecycle events and readiness timing

Common Spring Boot events:

| Event | Timing | Used for |
| --- | --- | --- |
| ApplicationStartingEvent | Very early in startup | Listeners before ApplicationContext |
| ApplicationEnvironmentPreparedEvent | Environment prepared | Environment-level setup |
| ApplicationContextInitializedEvent | Context initialized before refresh | Context initializers/listeners |
| ApplicationPreparedEvent | Context about to refresh | Setup before bean creation |
| ApplicationStartedEvent | Context refresh complete | Startup work before runners |
| ApplicationReadyEvent | Runners completed | Application ready per lifecycle |
| ApplicationFailedEvent | Startup failed | Recording startup failure |

Readiness state typically transitions to `ACCEPTING_TRAFFIC` after `ApplicationReadyEvent` is processed. Do not conflate `ApplicationStartedEvent` with `ApplicationReadyEvent`: runners may still execute after the started event.

### 3.1. ApplicationRunner and CommandLineRunner

Runners are suited for work that must finish within the startup sequence, such as validating startup configuration or loading small mandatory reference data:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StartupValidationConfiguration {
    @Bean
    ApplicationRunner startupValidation() {
        return args -> {
            // Validate required configuration and local invariants.
        };
    }
}
~~~

Synchronous runners lengthen startup. Only place work here that truly must finish before the application is considered ready. Do not load millions of records or run uncontrolled long migrations inside a runner if better deployment approaches exist.

### 3.2. ApplicationReadyEvent

You can listen for `ApplicationReadyEvent` to perform actions after the startup lifecycle:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Emit a startup-completed log or trigger non-blocking work.
    }
}
~~~

The listener runs once the application reaches the ready event. If this work is a mandatory prerequisite before traffic, do not make it a fire-and-forget background task and assume readiness will wait automatically. Design explicit readiness transitions.

## 4. Controlling ReadinessState with AvailabilityChangeEvent

An application can publish `AvailabilityChangeEvent` to announce state changes. For example, a startup coordinator places the instance in a traffic-refusing state during warm-up:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class StartupReadinessCoordinator {
    private final ApplicationEventPublisher events;

    public StartupReadinessCoordinator(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void beginWarmup() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void completeWarmup() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

This is the state control API; it must be called at appropriate lifecycle boundaries. If `completeWarmup` is called too early, the instance may receive traffic before truly ready. If you forget to transition back to `ACCEPTING_TRAFFIC`, the pod will remain not ready even though the application is healthy.

### 4.1. Readiness only or liveness as well?

Normal warm-up should affect readiness, not liveness. The application is still alive while caches load or indexes warm up. If warm-up fails permanently and the process cannot recover, policy may switch liveness to `BROKEN`, but conditions must be clearly defined and avoid reacting to transient dependency failures.

### 4.2. State must have an owner

A single coordinator or lifecycle component should own state transitions. Avoid having multiple independent beans publish readiness events based on different conditions, causing state to flip back and forth. If multiple steps are required, use a startup coordinator that aggregates results.

## 5. Startup warm-up and initialization strategy

Startup work usually falls into one of these groups:

| Work | Appropriate strategy |
| --- | --- |
| Validate config/schema compatibility | Complete before ready if mandatory |
| Load small reference data | Runner or initialization component |
| Warm critical cache | Readiness remains refusing until finished |
| Preload large dataset | Background warm-up with readiness policy |
| Optional analytics connection | Does not necessarily block readiness |
| External service discovery | Bounded timeout/retry, degraded mode if available |

### 5.1. Synchronous warm-up

Synchronous warm-up fits when the work is short, mandatory, and bounded by a timeout. It increases startup time; the Kubernetes `startupProbe` must have a matching budget.

### 5.2. Asynchronous warm-up

If warm-up runs in the background, the application must keep readiness at `REFUSING_TRAFFIC` until completion. Example:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class CacheWarmup {
    private final ThreadPoolTaskExecutor executor;
    private final StartupReadinessCoordinator readiness;

    public CacheWarmup(
            ThreadPoolTaskExecutor executor,
            StartupReadinessCoordinator readiness
    ) {
        this.executor = executor;
        this.readiness = readiness;
    }

    @EventListener
    public void startWarmup(ApplicationReadyEvent event) {
        readiness.beginWarmup();
        CompletableFuture.runAsync(this::loadCriticalCache, executor)
                .whenComplete((ignored, error) -> {
                    if (error == null) {
                        readiness.completeWarmup();
                    }
                    // On failure, remain refusing traffic and report the failure.
                });
    }

    private void loadCriticalCache() {
        // Load only the data required before serving traffic.
    }
}
~~~

This example illustrates the flow, but you must verify listener and readiness state lifecycle timing in your Spring Boot version. If readiness already transitioned to `ACCEPTING_TRAFFIC` automatically before the listener ran, there is a brief window where the instance could accept traffic. For mandatory warm-up, control state earlier in the startup lifecycle or use appropriate startup orchestration, and test the race condition via integration tests.

Do not swallow exceptions in `whenComplete`. Log errors, emit alerts, or transition state according to policy. If warm-up uses retries, bound both time and attempt count.

### 5.3. Retries and timeouts

Dependency startup checks require explicit timeouts. Retries must use backoff and limits; never retry infinitely such that startup never concludes. Distinguish mandatory dependencies from optional ones to choose fail-fast, remain-not-ready, or degraded mode.

## 6. Kubernetes startup, liveness, and readiness probes

Kubernetes provides three probe types:

- `startupProbe`: determines whether the container has completed startup;
- `livenessProbe`: determines whether the container needs to be restarted;
- `readinessProbe`: determines whether the pod receives traffic.

Manifest example:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

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

This is an illustrative configuration. Adjust port, initial delays, period, timeout, and failure threshold according to startup duration, traffic, and failure detection budget. A startup probe allows the application to take longer starting up without being restarted by the liveness probe.

### 6.1. Separate management port

If Actuator runs on a separate management port, Kubernetes probes must point to that port. Verify service/container networking and security rules. Do not use a correct path on a port unreachable from kubelet.

### 6.2. Probe semantics

Readiness failures typically remove the pod from Service endpoints without restarting the container. Liveness failures can restart the container. Startup failures beyond the budget can cause the container to restart. Pick the right endpoint/group for each type so readiness failures do not trigger restarts or external dependencies do not cause liveness failures.

## 7. Graceful shutdown and traffic draining

Startup state has a reverse direction when the application stops. Before the process exits, the instance must stop receiving new requests, let in-flight requests complete within a limit, and close resources.

Spring Boot supports graceful shutdown for embedded web servers via configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

When shutdown begins, readiness can transition to `REFUSING_TRAFFIC` so the instance is drained from routing. Coordinate Kubernetes's termination grace period with the Spring lifecycle timeout and the load balancer's drain time.

### 7.1. Shutdown sequence

~~~mermaid
sequenceDiagram
    participant K8s as Kubernetes
    participant App as Spring Boot
    participant LB as Load balancer
    participant Requests
    K8s->>App: SIGTERM
    App->>App: Begin graceful shutdown
    App->>LB: Readiness becomes REFUSING_TRAFFIC
    LB->>LB: Remove instance from new routing
    Requests->>App: In-flight requests complete
    App->>App: Close beans and resources
    App-->>K8s: Process exits
~~~

Propagation time for readiness changes and load balancer endpoint updates is non-zero. A platform-appropriate `preStop`/drain strategy may be needed. Avoid arbitrary fixed sleeps without understanding the termination sequence and grace period.

### 7.2. Background tasks during shutdown

In-memory task queues can lose tasks when the process terminates. Use durable messaging/job storage if tasks require delivery guarantees. Executors must stop accepting new tasks, process running tasks within timeout, and record canceled/rejected tasks.

## 8. Observability for startup state

Startup state also needs to be observed, not just used as a probe.

Useful signals:

| Signal | Purpose |
| --- | --- |
| Application startup duration | Detect slow startups |
| Warm-up duration | Measure cache/index preparation time |
| Readiness transition timestamp | Know how long an instance takes before receiving traffic |
| Startup failure count | Track startup failures |
| Probe status | Track liveness/readiness over time |
| Lifecycle event logs | Investigate startup/shutdown steps |
| Traces for startup tasks | Analyze dependency calls during warm-up |

### 8.1. Startup metrics

Spring Boot can record application startup steps when using an appropriate startup tracking mechanism. Startup information can be viewed through the Actuator startup endpoint if configured/exposed, but do not expose this endpoint publicly unless necessary.

Custom warm-ups should have an `Observation` with a stable operation name like `startup.cache-warmup` and low-cardinality tags such as `cache.name` or `outcome`. Do not attach dynamic host/user/data IDs to metric tags.

### 8.2. Logging state transitions

Log when warm-up starts, finishes, fails, when readiness transitions, and when shutdown begins. Logs need service identity and timestamps; if startup tasks carry trace context, correlation fields help link dependency calls. Do not log credentials or full configuration dumps.

## 9. Protecting and designing dependency policies

Readiness can affect cluster-wide traffic. Determine which dependencies are truly mandatory:

- database mandatory for all primary requests;
- cache can fall back;
- analytics can buffer;
- optional API can run degraded;
- broker may be needed for one subset of use cases but not all.

Do not turn every dependency failure into a global readiness failure. If the instance can still serve partial traffic, consider degraded mode and routing policies. If readiness is a single bit across diverse endpoints, supplement it with metrics/dependency health groups so operations has sufficient visibility.

### 9.1. Avoiding readiness flapping

If an indicator fluctuates, pods repeatedly toggle ready/not-ready, causing traffic oscillation. Use appropriate timeouts, hysteresis, or consecutive probe thresholds in the orchestrator; cache health results where appropriate; avoid overly sensitive dependency checks or retry storms.

### 9.2. Do not use liveness to restart on dependency outages

Liveness should focus on the process's ability to self-heal. External dependency outages generally call for retries/circuit breakers/degraded mode, not mass restarts of application instances.

## 10. Testing startup state

Test state transitions, event ordering, readiness endpoints, and graceful shutdown behavior.

### 10.1. Testing ApplicationAvailability

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class StartupAvailabilityTest {
    @Autowired
    ApplicationAvailability availability;

    @Test
    void applicationBecomesReadyAfterContextStartup() {
        assertThat(availability.getReadinessState())
                .isEqualTo(ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

This test assumes no startup coordinator intentionally holds readiness at `REFUSING_TRAFFIC`. If the application performs warm-up, the test must wait for/trigger completion per contract instead of assuming readiness immediately after context startup.

### 10.2. Testing AvailabilityChangeEvent

Use `ApplicationEventPublisher` to publish `REFUSING_TRAFFIC`/`ACCEPTING_TRAFFIC` and verify `ApplicationAvailability` reflects the new state. Check event sources and ordering to prevent multiple coordinators from overwriting one another's state.

### 10.3. Testing the readiness endpoint

Call the readiness health group before, during, and after warm-up. Verify status/HTTP responses reflect the expected state. Tests should run with Actuator health probes enabled and group configurations matching production.

### 10.4. Testing warm-up failures and timeouts

Simulate a slow or failing dependency. Verify:
- readiness stays refusing while mandatory work is incomplete;
- timeouts/retries are not infinite;
- failures are logged/metered;
- the process does not automatically switch liveness to `BROKEN` unless policy demands it;
- after recovery, readiness transitions to accepting under the proper conditions.

### 10.5. Testing graceful shutdown

Use an embedded server or lifecycle test to verify readiness transitions to refusing when shutdown begins, in-flight requests have time to complete, and the process closes within bounds. Do not assert overly tight absolute timings because CI environments have jitter.

## 11. Troubleshooting startup state

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Pod receives traffic before warm-up | Readiness transitions to accepting too early | Control state from an earlier lifecycle boundary |
| Pod stays NOT READY forever | `ACCEPTING_TRAFFIC` never published or warm-up stuck | Inspect coordinator, timeouts, and logs |
| Startup probe fails | Budget too low or slow app startup | Measure startup duration and increase budget reasonably |
| Liveness restart loop | Liveness depends on external dependency | Separate liveness from readiness |
| `ApplicationReadyEvent` fired while warm-up unfinished | Warm-up runs async fire-and-forget | Keep readiness refusing until completion |
| Startup task blocks too long | Synchronous runner or long dependency timeout | Bound timeouts and move work appropriately |
| Readiness flapping | Flaky dependency check | Timeouts, caching, thresholds, and degraded mode |
| Readiness unchanged after event | Event published to wrong context or overwritten | Check `ApplicationEventPublisher` and event ordering |
| Shutdown drops requests | Traffic not drained or short grace period | Coordinate readiness, LB drain, and termination grace |
| Background tasks lost on restart | Queue stored only in memory | Use durable queue/job store |
| Missing startup metrics | Startup tracking not enabled/exposed | Check Actuator startup support |
| Health endpoint works yet probe fails | Wrong port/path/security/network | Check kubelet reachability and HTTP mapping |

### 11.1. Investigation workflow

1. Inspect application logs from process start through `ApplicationReadyEvent`.
2. Read `ApplicationAvailability` liveness/readiness state.
3. Check the readiness group and HTTP status.
4. Inspect startup/warm-up `Observation` and duration.
5. Verify dependency timeouts/retries and failure policies.
6. Check Kubernetes startup/liveness/readiness probe paths, ports, and thresholds.
7. If a pod restarts, identify which probe failed.
8. For shutdown, correlate SIGTERM, readiness transitions, load balancer drain, and grace period.

## 12. Production checklist

| Criterion | Required evidence |
| --- | --- |
| Startup lifecycle well understood | Event ordering documented |
| Process and readiness separated | Pod running does not imply ready |
| `ApplicationAvailability` verified | Liveness/Readiness states observable |
| Warm-up has an owner | Single coordinator manages transitions |
| Readiness stays refusing until ready | Integration tests verify |
| Clear dependency policy | Mandatory/optional classified |
| Startup probe has budget | Based on actual startup duration |
| Liveness independent of external dependencies | No restart storms |
| Readiness endpoint properly exposed | Matching path/port/security |
| Warm-up has bounded timeouts/retries | No infinite startup |
| Graceful shutdown | Readiness refusing and traffic draining |
| Background tasks have durability | No critical tasks lost |
| Useful startup telemetry | Duration, transitions, errors, and logs |
| Full lifecycle tests | Ready, failure, timeout, shutdown |

## 13. Practice: keeping an instance unready during warm-up

**Context:** `order-service` runs on Kubernetes. When the process starts, the application needs to load reference data and warm caches before receiving traffic. Currently, the pod turns Ready right after the Spring context refreshes, causing initial requests to be slow or fail.

**Tasks:**

1. Enable Actuator health probes and verify readiness/liveness paths.
2. Read `ApplicationAvailability` in the startup lifecycle.
3. Identify mandatory vs. optional warm-up steps.
4. Design a `StartupReadinessCoordinator` that owns state transitions.
5. Keep `ReadinessState` at `REFUSING_TRAFFIC` during warm-up.
6. Transition to `ACCEPTING_TRAFFIC` only after critical warm-up finishes.
7. Set bounded timeouts/retries and record warm-up failures.
8. Keep `LivenessState` `CORRECT` when a dependency temporarily fails while the process can still recover.
9. Configure Kubernetes `startupProbe`/`readinessProbe`/`livenessProbe` using real ports/paths.
10. Verify readiness transitions and traffic routing via integration tests.
11. Verify graceful shutdown transitions back to `REFUSING_TRAFFIC` and drains requests.
12. Build a dashboard/log view for startup duration, warm-up duration, and readiness transitions.

**Expected outcome:** clear startup state transitions, readiness does not open prematurely, aligned probes, bounded warm-up timeouts, graceful shutdown, and lifecycle tests.

## 14. Key takeaways

Startup state describes an application's transition from a newly running process to an instance ready to accept traffic. Spring Boot provides `ApplicationAvailability` along with `LivenessState` and `ReadinessState` to represent this status. `ApplicationStartedEvent` and `ApplicationReadyEvent` mark distinct lifecycle milestones; synchronous runners can prolong startup, while asynchronous warm-up requires a dedicated readiness policy.

Keep readiness at `REFUSING_TRAFFIC` until mandatory work completes; use liveness for whether the process can continue running. Kubernetes `startupProbe` protects the startup phase, `readinessProbe` controls traffic, and `livenessProbe` decides restarts. During shutdown, transition to refusing traffic and coordinate draining/grace periods. Observe startup duration, warm-up, state transitions, and failures with metrics/logs/traces; test startup failures, timeouts, readiness, and shutdown.

**References:**
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Kubernetes — Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
