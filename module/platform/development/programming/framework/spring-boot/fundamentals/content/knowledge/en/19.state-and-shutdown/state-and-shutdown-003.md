# AvailabilityChangeEvent and When State Transitions Happen

A Spring Boot application may have already created its beans and opened its HTTP port yet still not be ready to serve requests. Conversely, an application may be running normally yet temporarily should not receive traffic because it is preparing for maintenance, draining from a cluster, or missing an essential business condition. When beginning to shut down, it also needs to notify the orchestrator to stop sending new requests before resources are closed.

Spring Boot provides **ApplicationAvailability** to describe process availability state and **AvailabilityChangeEvent** to publish changes to that state. Two aspects are tracked:

- **Liveness**: is the application still capable of functioning properly, or has it entered a severely broken state and needs to be restarted?
- **Readiness**: should the application receive new traffic at this moment?

This state is especially meaningful when deploying applications on Kubernetes, systems with load balancers, or any platform that monitors health/readiness. Even more important than the API names is **timing**—when state changes occur: before the context completes, after startup runners execute, while serving requests, and during shutdown.

## 1. Why Distinguish Liveness and Readiness?

Consider an order-processing application. When the process first starts:

1. Spring reads configuration and creates beans.
2. ApplicationContext is refreshed.
3. ApplicationRunners perform mandatory preparation steps.
4. Only then can the application serve requests reliably.

Between step 1 and step 4, the Java process is running, but letting traffic in too early can cause APIs to access unprepared data.

At another time, the application is serving normally yet needs to enter maintenance for a few minutes. The process is still alive and capable of recovering; restarting it is not the right solution. Instead, the load balancer should stop sending new requests.

Two questions must be answered independently:

| Question | Related state | Typical platform action |
|---|---|---|
| Is the process operating properly, or broken beyond self-recovery? | **Liveness** | Consider restarting when liveness fails. |
| Can this instance receive new requests right now? | **Readiness** | Add to or remove from the traffic-receiving endpoint pool. |

An application can be **live yet not ready**. This is a completely valid state during startup, maintenance, and graceful shutdown.

## 2. States Provided by Spring Boot

The main types reside in the package:

~~~java
org.springframework.boot.availability
~~~

The key APIs include:

- **ApplicationAvailability**: reads the current availability state.
- **AvailabilityState**: common interface for an availability state type.
- **LivenessState**: liveness state enum.
- **ReadinessState**: readiness state enum.
- **AvailabilityChangeEvent**: event publishing a state change.

### 2.1. LivenessState

Spring Boot has two basic liveness values:

| Value | Meaning |
|---|---|
| **LivenessState.CORRECT** | The application is considered to be functioning properly with respect to liveness. |
| **LivenessState.BROKEN** | The application is considered severely broken; restarting may be the appropriate recovery action. |

Do not interpret CORRECT as guaranteeing that all features, databases, and external services are working. It only reflects the liveness assessment of the process.

### 2.2. ReadinessState

Spring Boot has two basic readiness values:

| Value | Meaning |
|---|---|
| **ReadinessState.ACCEPTING_TRAFFIC** | The instance is considered ready to receive traffic. |
| **ReadinessState.REFUSING_TRAFFIC** | The instance should not receive new traffic yet. |

REFUSING_TRAFFIC can be a normal state while the app is starting up or shutting down; it does not by itself mean the process encountered a severe error.

### 2.3. Scenario Matrix

| Liveness | Readiness | Typical interpretation |
|---|---|---|
| CORRECT | ACCEPTING_TRAFFIC | The instance is active and ready to accept requests. |
| CORRECT | REFUSING_TRAFFIC | The process is healthy but not yet ready, under maintenance, or preparing to shut down. |
| BROKEN | REFUSING_TRAFFIC | The process has a serious issue or has not yet reached the milestone to be considered live. |
| BROKEN | ACCEPTING_TRAFFIC | An abnormal state or inconsistent updates; do not design systems around this combination. |

In typical designs, liveness and readiness change at separate stages; do not use a single boolean flag to represent both.

## 3. ApplicationAvailability: Reading Current State

Spring Boot provides **ApplicationAvailability** as a bean so application components can read the published state.

Example:

~~~java
package com.example.availability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityInspector {

    private final ApplicationAvailability availability;

    public AvailabilityInspector(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean canReceiveTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }

    public boolean isLive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }
}
~~~

This interface also provides a generic API:

~~~java
ReadinessState readiness = availability.getState(
        ReadinessState.class,
        ReadinessState.REFUSING_TRAFFIC);
~~~

The second argument is a fallback value if no state has been published yet for that type. Use this approach when you want to explicitly express a safe default state in code.

### 3.1. ApplicationAvailability Reflects Published State

When an AvailabilityChangeEvent is processed, Spring Boot's availability bean updates the latest state by type. Other parts of the code can query it via ApplicationAvailability.

~~~text
AvailabilityChangeEvent
        │
        ▼
ApplicationAvailability updates state
        │
        ├── getLivenessState()
        │
        └── getReadinessState()
~~~

This is state **within a single application process**. It is not a durable store or shared cluster-wide state. Each replica has its own ApplicationAvailability.

### 3.2. Reading State Does Not Replace Functional Checks

For example, readiness may be ACCEPTING_TRAFFIC while a business endpoint still fails because an external service is temporarily unresponsive. Availability state is only meaningful when necessary conditions are properly monitored and reflected.

Therefore, do not conclude that an HTTP API will succeed merely from the result of getReadinessState().

## 4. AvailabilityChangeEvent: Publishing Changes

**AvailabilityChangeEvent** is a Spring application event carrying an AvailabilityState value. When the event is published in the ApplicationContext, matching listeners can handle it; Spring Boot also uses this mechanism to track the current state.

Common way to publish state:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

public class ReadinessController {

    private final ApplicationEventPublisher events;

    public ReadinessController(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

In real code, this class needs to be registered as a bean, and invoking its methods must happen inside a controlled operational workflow. The example only illustrates how to publish; do not expose an open public endpoint allowing outsiders to toggle application state.

### 4.1. What Information Does the Event Contain?

An AvailabilityChangeEvent contains:

- **State**: the specific value such as ReadinessState.REFUSING_TRAFFIC.
- **Source**: the source object associated with the event.
- Publish context: the application event is dispatched to matching listeners via Spring's event mechanism.

Example listener:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessLogListener {

    @EventListener
    public void onReadinessChanged(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("Readiness changed to " + event.getState());
    }
}
~~~

In production logging systems, use SLF4J instead of System.out, and include timestamp, instance ID, and the transition reason recorded by the business component.

### 4.2. Publishing Does Not Mean Stopping the HTTP Server

When publishing REFUSING_TRAFFIC, Spring Boot updates the readiness state, but **that does not mean all HTTP sockets are immediately closed or all clients are blocked at that exact instant**.

In a system with a readiness probe, the orchestrator must:

1. Call the probe.
2. Receive the result that the instance is not ready.
3. Update the list of eligible traffic-receiving endpoints.
4. Shift new traffic to other instances.

These steps take time. Existing connections or in-flight requests may still continue. To stop accepting requests in a controlled manner, coordinate readiness, traffic draining, and graceful shutdown.

## 5. Startup Milestones Related to Availability

When Spring Boot publishes states can be visualized as follows:

~~~text
SpringApplication.run(...)
          │
          ▼
Prepare Environment / ApplicationContext
          │
          ▼
ApplicationContext.refresh()
          │
          ├── Create eager singletons
          └── Bean callbacks
          │
          ▼
ApplicationStartedEvent
          │
          ▼
AvailabilityChangeEvent(LivenessState.CORRECT)
          │
          ▼
ApplicationRunner / CommandLineRunner
          │
          ▼
ApplicationReadyEvent
          │
          ▼
AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
          │
          ▼
Application in normal ready state
~~~

This is Spring Boot's normal successful startup sequence. It represents **observation milestones**, not a promise that all external services are always healthy or that all application-initiated tasks have finished.

### 5.1. Before ApplicationContext Refresh Finishes

While beans are being created and callbacks like @PostConstruct are running, the application has not reached the complete startup milestone yet.

Therefore, do not treat:

- A constructor completing.
- A @PostConstruct completing.
- The web server beginning initialization.
- An ApplicationContext bean already existing.

as proof that the application is ready to receive requests.

During the phase before live/ready milestones, the fallback values Spring Boot applies typically express **BROKEN** for liveness and **REFUSING_TRAFFIC** for readiness. However, external probes may not even be able to connect yet because the HTTP server is not open. Do not build business logic depending on probes being reachable from the very first second.

### 5.2. After ApplicationStartedEvent

Spring Boot publishes ApplicationStartedEvent after context refresh finishes, before calling startup runners.

Next in the normal startup flow, Boot publishes:

~~~java
LivenessState.CORRECT
~~~

This indicates the application has reached the milestone to be considered live. It does not prove runners have finished, so readiness typically remains REFUSING_TRAFFIC.

### 5.3. During ApplicationRunner and CommandLineRunner

Spring Boot invokes runners after the started milestone and before the ready milestone. This is where mandatory preparation steps can be performed:

- Validate required business configuration.
- Load reference data.
- Prepare caches that must exist before serving requests.
- Verify resources required to serve APIs.

While a synchronous runner is still running, the application has not reached ApplicationReadyEvent. If a runner throws an unhandled exception, startup can fail and never complete the normal ready path.

### 5.4. After ApplicationReadyEvent

Spring Boot publishes ApplicationReadyEvent after startup runners complete. Following this event, Boot publishes:

~~~java
ReadinessState.ACCEPTING_TRAFFIC
~~~

This is the transition milestone to ready in a successful startup flow. The subtle point is that **ApplicationReadyEvent and AvailabilityChangeEvent with ACCEPTING_TRAFFIC are two consecutive events, not the same event**.

If a listener handling ApplicationReadyEvent reads ApplicationAvailability immediately at that moment, it should not assume ReadinessState is already ACCEPTING_TRAFFIC; Boot publishes readiness after the ready event.

## 6. Why Not Publish Readiness Arbitrarily During Startup?

Suppose an application needs to warm up a cache asynchronously and wants to block traffic until the cache is ready.

An error-prone way to write it:

~~~java
@Component
public class CacheStartupListener {
    private final ApplicationEventPublisher publisher;

    public CacheStartupListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        AvailabilityChangeEvent.publish(
                publisher, ReadinessState.REFUSING_TRAFFIC);

        // Start background warm-up task here.
    }
}
~~~

The issue is that this listener runs **while ApplicationReadyEvent is being dispatched**. After synchronous listeners of the ready event finish, Spring Boot proceeds to publish ACCEPTING_TRAFFIC. Thus, REFUSING_TRAFFIC published inside the listener can quickly be overwritten by the default startup event.

The background warm-up task may still be unfinished even though the final state has switched to ACCEPTING_TRAFFIC.

### 6.1. Appropriate Approach if the Task Must Finish Before Ready

Run synchronously in ApplicationRunner:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class RequiredWarmupRunner implements ApplicationRunner {

    private final CacheWarmupService warmupService;

    public RequiredWarmupRunner(CacheWarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmupService.loadRequiredData();
    }
}
~~~

If loadRequiredData() returns only when mandatory data is ready, Boot only then proceeds to ApplicationReadyEvent and readiness ACCEPTING_TRAFFIC. If it cannot complete, an exception should reflect startup failure instead of silently pretending to be ready.

### 6.2. Appropriate Approach if Mandatory Warm-Up Runs in the Background

When a task genuinely must run in the background while still blocking traffic, you can create a **health contributor** for readiness that returns OUT_OF_SERVICE until warm-up finishes. The actual readiness probe must include this contributor.

Model:

~~~text
ApplicationReadyEvent
          │
          ├── Boot publishes ACCEPTING_TRAFFIC
          │
          └── Warm-up runs in background
                    │
                    ▼
Readiness health group checks warm-up
          │
          ├── Not done → OUT_OF_SERVICE
          │
          └── Done → UP
~~~

This separates the availability state managed by Boot from application-specific business conditions that the readiness endpoint must evaluate. A health contributor example is shown below.

## 7. Publishing Readiness While the Application Is Running

After the application passes startup, a component can proactively publish AvailabilityChangeEvent to pause or resume traffic.

Example:

~~~java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceService {

    private final ApplicationEventPublisher events;

    public MaintenanceService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void beginMaintenance() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
    }

    public void finishMaintenance() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

When the application begins maintenance, beginMaintenance() marks the instance as not yet ready for traffic. Once normal operating conditions are confirmed, finishMaintenance() publishes the accepting traffic state.

### 7.1. Do Not Rush to Restore Readiness

Before publishing ACCEPTING_TRAFFIC, ensure the condition that caused the instance to refuse traffic has genuinely been resolved:

- Have required resources recovered?
- Has maintenance work completed?
- Is the application already in the middle of shutting down?
- Can core features serve requests properly?

If multiple components can independently publish readiness, they can overwrite each other's state. For instance, service A reports unready due to maintenance while service B publishes accepting because the database just recovered.

With multiple independent conditions, use a coordinator that aggregates state or a readiness health group containing the necessary contributors, instead of letting every component freely emit ACCEPTING_TRAFFIC events.

### 7.2. Liveness Can Be Published Manually, but with Caution

The API allows publishing:

~~~java
AvailabilityChangeEvent.publish(
        events, LivenessState.BROKEN);
~~~

This is a severe signal: the orchestrator may treat the process as needing a restart. Do not publish BROKEN merely because an HTTP call failed, the database briefly lost connectivity, or a background retry task has not succeeded yet.

External dependency errors are usually better reflected through readiness or a health contributor. Liveness should be reserved for situations where the process cannot continue functioning properly and restarting is a sensible recovery path.

## 8. When Readiness Changes During Shutdown

When an instance needs to stop, stopping new requests should generally happen **before request-serving resources are closed**.

Target sequence:

~~~text
Receive shutdown signal
          │
          ▼
Readiness → REFUSING_TRAFFIC
          │
          ▼
Load balancer / orchestrator stops sending new requests
          │
          ▼
In-flight requests are processed or waited on within limit
          │
          ▼
Spring context and resources are stopped
          │
          ▼
Process terminates
~~~

Spring Boot has lifecycle and graceful shutdown mechanisms to support this flow. In a properly managed shutdown flow, readiness is transitioned to REFUSING_TRAFFIC to indicate the instance should not receive new traffic.

### 8.1. Readiness Alone Does Not Guarantee Graceful Shutdown

Publishing REFUSING_TRAFFIC is a signal about traffic eligibility. It does not replace:

- The web server's mechanism to stop accepting new connections.
- Waiting time for in-flight requests.
- Load balancer or ingress draining mechanisms.
- Closing connection pools, executors, and message consumers.
- Container/orchestrator shutdown deadlines.

Because probes are called periodically, there can be a delay before external systems notice the instance is unready. Requests already dispatched beforehand can still arrive.

### 8.2. Configuring Graceful Shutdown

An illustrative configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

When graceful shutdown is supported by the web server in use, Spring Boot coordinates to give in-flight requests a chance to finish within the shutdown timeout. Depending on the web server and deployment setup, how new connections are handled during this phase may differ.

This is the shutdown mechanism, whereas AvailabilityChangeEvent is the way state is communicated. Both mechanisms must be configured and observed together.

### 8.3. Do Not Rely on Callbacks on Sudden Kill

When a process crashes, is forcefully killed, or loses its host machine, shutdown callbacks may not run. In those cases, there is no guarantee AvailabilityChangeEvent or @PreDestroy will be emitted or completed.

The deployment platform must use probes, timeouts, and disconnect detection to remove dead instances from the endpoint pool. Do not design availability as a protocol guaranteeing every process can send a "goodbye event".

## 9. Relationship Between ApplicationReadyEvent and AvailabilityChangeEvent

The two events serve different functions:

| Event | Meaning |
|---|---|
| **ApplicationStartedEvent** | Context refreshed, runners not yet called. |
| **AvailabilityChangeEvent(LivenessState.CORRECT)** | Spring Boot publishes that the application reached the normal live milestone. |
| **ApplicationReadyEvent** | Runners have been called and successful startup reached the ready milestone. |
| **AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)** | Spring Boot publishes the ready state to accept traffic. |
| **AvailabilityChangeEvent(ReadinessState.REFUSING_TRAFFIC)** | The instance should not accept traffic yet or is leaving the ready state. |

### 9.1. Why Does Event Ordering Matter?

Suppose a listener is registered:

~~~java
@EventListener(ApplicationReadyEvent.class)
void onReady() {
    // Here ApplicationReadyEvent is currently being processed.
}
~~~

If you want to know the exact moment **ReadinessState switches to ACCEPTING_TRAFFIC**, a listener for ApplicationReadyEvent is not the most direct signal. Listen to AvailabilityChangeEvent for readiness instead.

~~~java
@EventListener
void onReadinessChange(
        AvailabilityChangeEvent<ReadinessState> event) {

    if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
        // Readiness is being published as accepting traffic.
    }
}
~~~

If the application publishes readiness multiple times itself, this listener may be invoked each time the state is published. Do not assume it runs strictly once per application lifecycle.

## 10. Observing Both Liveness and Readiness

You can write a shared listener:

~~~java
package com.example.availability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityAuditListener {

    private static final Logger log =
            LoggerFactory.getLogger(AvailabilityAuditListener.class);

    @EventListener
    public void onAvailabilityChange(AvailabilityChangeEvent<?> event) {
        Object state = event.getState();

        if (state instanceof ReadinessState) {
            log.info("Readiness changed: {}", state);
        } else if (state instanceof LivenessState) {
            log.info("Liveness changed: {}", state);
        }
    }
}
~~~

This is an observation-only listener. Avoid emitting another event solely in response to receiving the current event unless clear state transition rules exist, as that can cause loops or unintended state changes.

### 10.1. Events and Current State Are Not Identical

- An **Event** indicates a change was published, with a specific moment and state.
- **ApplicationAvailability** returns the current state tracked in the process.

A listener created after an event was already published does not automatically replay all historical events. If you need the current state, read ApplicationAvailability; if you need to react when changes occur, listen to events.

### 10.2. Watch Out for Asynchronous Dispatch

Spring application events are normally processed synchronously under the default event multicaster configuration. However, an application can customize the multicaster or configure asynchronous listeners.

When event dispatch is asynchronous, do not assume that right after publishing, all listeners and observers have immediately updated. If a strong synchronous contract is required, clearly define the event dispatch mechanism and state confirmation point in the architecture.

## 11. AvailabilityChangeEvent and Spring Boot Actuator

Spring Boot Actuator can reflect availability through health contributors for liveness/readiness. When properly configured, two familiar endpoints are:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

When the application is detected running on Kubernetes, Spring Boot can automatically enable probe health groups per the integration mechanism of the version in use. In other environments, enable them explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

### 11.1. Readiness State and HTTP Health Response

Under common default health status mappings:

| Availability state | Corresponding health status | Typical HTTP status |
|---|---|---|
| CORRECT (liveness) | UP | 200 |
| BROKEN (liveness) | DOWN | 503 |
| ACCEPTING_TRAFFIC (readiness) | UP | 200 |
| REFUSING_TRAFFIC (readiness) | OUT_OF_SERVICE | 503 |

This is the typical mapping of availability health indicators. An application can customize status mapping, health groups, and contributors; always verify the actual response of the deployed endpoints.

### 11.2. Probes Read Endpoints, Not Java Events Directly

Kubernetes, ingress controllers, or load balancers do not directly receive AvailabilityChangeEvent inside the JVM. They read the result of health endpoints or another health check mechanism.

Interaction flow:

~~~text
AvailabilityChangeEvent
         │
         ▼
ApplicationAvailability
         │
         ▼
Actuator availability health indicator
         │
         ▼
HTTP readiness/liveness endpoint
         │
         ▼
Kubernetes probe / load balancer health check
         │
         ▼
Orchestrate restarts or traffic routing
~~~

Without probes or an orchestrator acting on probe results, events still update state inside the process but will not automatically cause external traffic to reroute.

### 11.3. A Separate Management Port Can Mask Application Port Issues

If Actuator runs on a separate management port, probes may return 200 even while the main port serving APIs is experiencing issues. In certain setups, consider exposing additional health probe paths on the main application port:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

When supported, this configuration can provide paths such as **/livez** and **/readyz** on the main server port. Verify endpoints, security, and routing according to the Boot version and web stack in use.

## 12. Choosing What to Include in the Readiness Probe

Readiness should reflect whether the instance **can serve requests properly**. Not every external dependency belongs in readiness.

For example:

- If every request strictly requires calling the database with no fallback, an unavailable database may make the instance unready.
- If the email-sending system fails while core functionality can still serve, do not automatically pull the entire instance out of traffic just because email failed.
- If a cache is an optimization with a fallback, incomplete cache warm-up may not need to block readiness.
- If a mandatory background data-loading step has not completed, readiness should reflect that state.

An overly strict readiness gate can knock all replicas out of routing simultaneously when a shared dependency disconnects. That can amplify an outage. Choose contributors based on the request-serving contract and the application's fallback model.

### 12.1. Health Contributor Example for Warm-Up

Suppose the application must finish a preparation process before endpoints can return accurate results. We create a state holder:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class WarmupState {
    private final AtomicBoolean ready = new AtomicBoolean(false);

    public void markReady() {
        ready.set(true);
    }

    public boolean isReady() {
        return ready.get();
    }
}
~~~

HealthIndicator reading the state:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("warmup")
public class WarmupHealthIndicator implements HealthIndicator {

    private final WarmupState warmup;

    public WarmupHealthIndicator(WarmupState warmup) {
        this.warmup = warmup;
    }

    @Override
    public Health health() {
        return warmup.isReady()
                ? Health.up().build()
                : Health.outOfService().build();
    }
}
~~~

Then add this contributor to the readiness health group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,warmup
~~~

While warmup is not ready, the readiness endpoint can return OUT_OF_SERVICE even though ApplicationAvailability already received ACCEPTING_TRAFFIC from the default startup flow. Once WarmupState becomes true, the readiness group can return UP if other contributors are also ready.

Key takeaway: **ReadinessState and health groups are not the same variable**. A health group can aggregate additional conditions that the application needs to verify.

## 13. Distinguishing Readiness Events from Business State

AvailabilityChangeEvent is suitable for publishing a high-level availability state. It does not store details such as:

- Why is the instance not ready?
- Which task is blocking?
- What percentage of warm-up is complete?
- How many retries have failed?
- Which dependency is degraded?

If those details are needed, the application should maintain dedicated observability mechanisms such as metrics, logs, health details, or a specific business status.

For example, a system with three conditions:

~~~text
Composite readiness
        │
        ├── Dataset initialized?
        ├── Search index usable?
        └── Local worker initialized?
~~~

Instead of letting three components publish ACCEPTING_TRAFFIC independently, health contributors or a coordinator can compute the composite condition:

~~~text
Ready = datasetReady AND searchReady AND workerReady
~~~

Only when all mandatory conditions are met should the instance report ready. This prevents race conditions where components overwrite each other's state.

## 14. Testing Runtime State Transitions

In a Spring Boot application with Actuator and probes enabled, you can create a state management service like the MaintenanceService example and invoke it through an internal operational workflow.

Observation procedure:

1. Start the application and wait for startup runners to complete.
2. Query the readiness endpoint; under normal conditions, the result is typically UP.
3. Trigger MaintenanceService.beginMaintenance().
4. Query the readiness endpoint after the event is processed; availability readiness typically switches to OUT_OF_SERVICE.
5. Complete the maintenance work and verify the application can serve again.
6. Call finishMaintenance().
7. Query the readiness endpoint; status typically returns to UP if no other contributor is failing.

If the response does not change, check:

- Was the event published via the ApplicationEventPublisher of the right context?
- Was ApplicationAvailability updated?
- Are probe endpoints and health groups properly enabled?
- Is another health contributor still reporting DOWN or OUT_OF_SERVICE?
- Is a custom event multicaster causing listeners to process asynchronously?
- Does the probe or load balancer cache state or have polling latency?

Changing Java state is one step; external routing outcomes also depend on infrastructure configuration.

## 15. Testing Events and State in a Spring Context

You can spin up a minimal context to test how AvailabilityChangeEvent is published and observed. The example below focuses on state events without needing a web server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ApplicationAvailabilityBean;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class AvailabilityChangeEventTests {

    @Test
    void updatesReadinessWhenEventIsPublished() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(ApplicationAvailabilityBean.class);
            context.refresh();

            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);

            assertThat(availability.getReadinessState())
                    .isEqualTo(ReadinessState.REFUSING_TRAFFIC);

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);

            assertThat(availability.getReadinessState())
                    .isEqualTo(ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

This example demonstrates events updating state inside a context with ApplicationAvailabilityBean and default synchronous event dispatch.

For integration tests of a real application, you can use @SpringBootTest and read ApplicationAvailability after the context starts. When a test modifies readiness on a shared context, isolate or restore the state so it does not affect other tests.

### 15.1. Testing Startup Order by Behavior

For a mandatory startup runner, tests should verify:

- If preparation succeeds, the application reaches the ready milestone.
- If the runner throws an error, startup is not considered successful.
- If work runs asynchronously, the readiness endpoint still reflects the required business condition accurately.

Do not merely assert that AvailabilityChangeEvent was emitted; test the actual outcome callers rely on—such as the readiness probe reporting unready while required data is missing.

## 16. Common Timing Mistakes

### 16.1. Assuming @PostConstruct Equals Application Ready

**Symptom:** a bean logs "ready" inside @PostConstruct, yet runners have not executed or data is not ready yet.

**Explanation:** bean callbacks occur during bean initialization, before the full startup flow completes.

**Fix:** use a synchronous runner or appropriate ready milestone; let Boot reflect liveness/readiness according to lifecycle.

### 16.2. Publishing REFUSING_TRAFFIC in ApplicationReadyEvent and Getting Overwritten

**Symptom:** a listener published refusing, yet readiness quickly flips back to accepting while warm-up is still running.

**Explanation:** Spring Boot publishes ACCEPTING_TRAFFIC after ApplicationReadyEvent during a successful startup flow.

**Fix:** run mandatory tasks synchronously before ready or put warm-up status into the readiness health group. Avoid relying on publishing refusing inside a ready listener to keep the gate closed.

### 16.3. Marking BROKEN When an External Dependency Temporarily Fails

**Symptom:** Kubernetes restarts replicas en masse when a shared database briefly loses connection.

**Explanation:** liveness failure is usually interpreted as needing a process restart. An external system failure may not be fixed by restarting.

**Fix:** design readiness, retries, and fallbacks according to business requirements; reserve BROKEN for situations where the process cannot operate properly.

### 16.4. Publishing Readiness Yet Traffic Keeps Arriving

**Symptom:** after state becomes REFUSING_TRAFFIC, new requests still arrive.

**Explanation:** events do not close sockets automatically; there is probe latency, load balancer delay, and existing connections.

**Fix:** inspect readiness probes, load balancer routing, polling intervals, and the graceful shutdown procedure.

### 16.5. ApplicationAvailability Is Accepting Yet Readiness Health Returns 503

**Symptom:** getReadinessState() returns ACCEPTING_TRAFFIC while the readiness endpoint returns OUT_OF_SERVICE.

**Explanation:** the health group may aggregate additional contributors that are failing, such as warmup or mandatory dependencies.

**Fix:** inspect each health contributor and specific business conditions.

### 16.6. Readiness Flapping Back and Forth

**Symptom:** the readiness endpoint oscillates between UP and OUT_OF_SERVICE multiple times in a short span.

**Explanation:** could be caused by an unstable dependency, two components both publishing state, or missing hysteresis in health checks.

**Fix:** identify the source of state transitions, centralize conditions into a coordinator, and apply appropriate thresholds and recovery policies instead of letting events race.

### 16.7. Using Readiness as a Process Termination Mechanism

**Symptom:** the application was told to stop, yet it only published REFUSING_TRAFFIC and the process keeps running.

**Explanation:** readiness only says "do not send traffic"; it does not call SpringApplication.exit or close the context.

**Fix:** when actual termination is needed, use the appropriate shutdown lifecycle mechanism; readiness is one part of draining.

### 16.8. Expecting Events to Persist Across Restarts

**Symptom:** after restarting an instance, the maintenance state published by the old process is gone.

**Explanation:** ApplicationAvailability is in-memory process state; events are not durable data.

**Fix:** for maintenance modes that must survive restarts, store the maintenance intent in a durable configuration/orchestration system and reapply it according to the appropriate lifecycle.

## 17. Common Misconceptions

**"Opening the HTTP port means the app is ready."**  
No. Spring Boot may open the port before startup runners complete. Readiness is published at a separate milestone.

**"ApplicationStartedEvent and ApplicationReadyEvent are the same."**  
No. Started occurs before runners; Ready occurs after runners.

**"ApplicationReadyEvent means readiness has already been published as ACCEPTING_TRAFFIC."**  
Do not assume this while executing a ready listener. Spring Boot publishes accepting traffic after ApplicationReadyEvent in the normal flow.

**"AvailabilityChangeEvent is only emitted by Spring Boot itself."**  
No. Applications can proactively publish availability events via ApplicationEventPublisher.

**"Publishing REFUSING_TRAFFIC will immediately block every request."**  
No. It updates availability state; traffic routing depends on probes, load balancers, and infrastructure latency.

**"CORRECT guarantees the database and all external services are working."**  
No. CORRECT is liveness, not verification of every dependency.

**"Readiness must go down whenever any dependency fails."**  
No. It should only reflect dependencies that genuinely affect the ability to serve requests under the service contract.

**"BROKEN is the right state for all temporary errors."**  
No. BROKEN can trigger restarts; temporary external errors usually do not warrant restarting the process.

**"ApplicationAvailability is cluster-wide state."**  
No. Each instance tracks its own state within its process.

**"AvailabilityChangeEvent is stored and replayed for new listeners."**  
No. It is an application event. To read current state, use ApplicationAvailability; for history, record logs/metrics or store separately.

**"Starting an @Async task from ApplicationReadyEvent makes Boot wait until it finishes."**  
No. Background tasks can continue after Boot publishes readiness; use a readiness gate or run synchronously before ready if the work is mandatory.

**"Graceful shutdown is guaranteed by a single availability event alone."**  
No. You must coordinate web server shutdown, request draining, timeouts, and deployment platform behavior.

## 18. Principles for Choosing When to Change State

1. **Let Spring Boot manage standard startup milestones**: liveness after started and readiness after ready are the foundational lifecycle signals.
2. **Use synchronous ApplicationRunner for mandatory preparation**: startup does not advance to ready until runners complete.
3. **Use a readiness health contributor for asynchronous conditions**: when multiple independent conditions or background tasks exist, the health group should accurately reflect serving capability.
4. **Publish REFUSING_TRAFFIC when removing an instance from routing**: such as maintenance or coordinating drain after startup.
5. **Do not publish ACCEPTING_TRAFFIC just because a single condition recovered**: confirm other mandatory conditions are also satisfied.
6. **Reserve BROKEN for truly severe process errors**: restarting must be a meaningful recovery strategy.
7. **Ensure probes are actually configured and used**: an in-JVM event does not control a load balancer by itself.
8. **Coordinate readiness with shutdown**: announce refusing, allow traffic draining, then close resources under clear deadlines.
9. **Observe and explain every state transition**: log the source, timestamp, and reason for easier diagnosis.
10. **Treat availability as per-replica state**: if state must persist across restarts or synchronize across a cluster, use an external management mechanism.

## Key Takeaways

**AvailabilityChangeEvent** is Spring Boot's mechanism for publishing **LivenessState** and **ReadinessState** changes; **ApplicationAvailability** lets you read the current state. In a successful startup flow, Boot publishes liveness CORRECT after ApplicationStartedEvent, executes ApplicationRunner/CommandLineRunner, emits ApplicationReadyEvent, and then publishes readiness ACCEPTING_TRAFFIC. When preparing to shut down or when an instance temporarily cannot take traffic, readiness can switch back to REFUSING_TRAFFIC.

Publish timing determines real-world behavior. Emitting REFUSING_TRAFFIC inside ApplicationReadyEvent can be overwritten by the subsequent startup event; mandatory work should complete synchronously before ready, while background work needs an appropriate readiness health gate if it must block requests. Availability events are state signals inside the JVM; to affect routing and shutdown, they must work in concert with Actuator probes, the orchestration platform, and graceful shutdown mechanisms.
