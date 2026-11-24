# ApplicationAvailability and Application State

A Spring Boot application may have already initialized its ApplicationContext while still not being ready to receive traffic. Conversely, an application may still be running normally yet temporarily need to stop accepting new requests for maintenance, load shedding, or preparing to shut down. Therefore, **running** and **ready to serve** are two distinct states.

Spring Boot models these states through `ApplicationAvailability`, `LivenessState`, `ReadinessState`, and `AvailabilityChangeEvent`. These APIs allow an application to publish its current state while providing integration points with Spring Boot Actuator health probes and orchestration systems such as Kubernetes.

## 1. Why Track Application State?

Consider an order-processing service. When the JVM process has just started, Spring Boot still needs to create beans, load configuration, and execute startup tasks. During that time, the service should not receive requests from the load balancer yet.

After starting successfully, the service can accept requests. However, when operators need to take an instance out of rotation to deploy a new version, the service should refuse new traffic before closing the remaining components.

There are also cases where a process gets stuck in an unrecoverable state: it is still alive, yet cannot do useful work. In that situation, the orchestration system may need to restart the instance.

Spring Boot distinguishes two questions:

- **Liveness:** is the application still in a state capable of continuing to operate, or has it broken to the point where it needs to be restarted?
- **Readiness:** is the application currently accepting new traffic or work?

These two independent questions help operations systems take the appropriate action, avoiding restarting an application just because it is temporarily not ready.

## 2. What is ApplicationAvailability?

`ApplicationAvailability` belongs to the `org.springframework.boot.availability` package. It is the interface used to **read the current availability state** recorded by Spring Boot.

A service can receive the interface via constructor injection:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AvailabilityInspector {

    private final ApplicationAvailability availability;

    public AvailabilityInspector(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean isLive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }

    public boolean isReady() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

Spring Boot provides an `ApplicationAvailability` bean so components within the ApplicationContext can look up state without maintaining scattered flag variables themselves.

The interface has commonly used methods:

~~~java
LivenessState liveness = availability.getLivenessState();
ReadinessState readiness = availability.getReadinessState();
~~~

In addition, you can read a state type through `getState(...)` and specify a fallback value if needed:

~~~java
ReadinessState readiness = availability.getState(
        ReadinessState.class,
        ReadinessState.REFUSING_TRAFFIC
);
~~~

`ApplicationAvailability` is an API for observing state. When the application needs to **change** state, publish an `AvailabilityChangeEvent` instead of trying to modify the availability object directly.

## 3. LivenessState: Is the Application Alive or Broken?

`LivenessState` has two values:

| Value | Meaning | Typical operational reaction |
|---|---|---|
| `CORRECT` | The application is in an internal state capable of continuing to operate | Keep the process running |
| `BROKEN` | The application has a severe internal failure and can no longer self-recover as expected | May restart the instance |

Liveness focuses on the operational capability of **the process itself**. It is not a check of whether every external service is ready.

For example, if the database temporarily drops connections but the application has a reconnection mechanism, that incident usually does not mean the JVM needs to be restarted. Marking `BROKEN` just because of a database error can cause all replicas to restart repeatedly without solving the database issue.

By contrast, if a core component enters an unrecoverable error state, the application can publish `LivenessState.BROKEN`. A monitoring system or orchestrator using a liveness probe can then decide to restart the instance.

Note: publishing `BROKEN` **does not automatically call** `System.exit()`, nor does it directly request a JVM restart. The restart action depends on the process manager or external liveness probe configuration.

## 4. ReadinessState: Does the Application Accept New Work?

`ReadinessState` also has two values:

| Value | Meaning | Typical operational reaction |
|---|---|---|
| `ACCEPTING_TRAFFIC` | The instance is ready to accept new traffic | Put the instance into the backend pool eligible to receive requests |
| `REFUSING_TRAFFIC` | The instance is not yet or temporarily not ready to accept new traffic | Temporarily remove the instance from the serving rotation |

Readiness can change multiple times throughout the application lifecycle. Common moments include:

- During startup, while runners or preparation steps are still executing.
- After startup completes, when the instance begins accepting traffic.
- Before shutdown, when the instance needs to be drained from the load balancer.
- When an essential component is temporarily overloaded and the application has a mechanism to proactively shed traffic.

Readiness does not necessarily mean the service has lost the ability to process all requests. An application can switch to `REFUSING_TRAFFIC` to avoid receiving **new requests**, while in-flight requests continue until completion.

Changing the readiness state does not automatically close the HTTP port or reject connections at the network layer. It publishes the state so components such as Actuator health indicators and orchestration systems can act on it.

## 5. How Does State Change When Spring Boot Starts?

Spring Boot automatically publishes availability milestones during the `SpringApplication.run()` lifecycle. The typical flow can be visualized as follows:

~~~text
SpringApplication.run()
        |
        v
Start and prepare ApplicationContext
        |
        |  Liveness:  BROKEN (initial default value)
        |  Readiness: REFUSING_TRAFFIC
        v
ApplicationContext refreshed successfully
        |
        v
ApplicationStartedEvent
        |
        v
LivenessState.CORRECT
        |
        v
Run ApplicationRunner / CommandLineRunner
        |
        |  Readiness still REFUSING_TRAFFIC
        v
ApplicationReadyEvent
        |
        v
ReadinessState.ACCEPTING_TRAFFIC
        |
        v
Application continues serving
~~~

The initial values are designed conservatively: an application that has not yet proven it has started stably should not be considered ready.

After context refresh, Spring Boot publishes `ApplicationStartedEvent` and then publishes liveness `CORRECT`. Next, `ApplicationRunner` and `CommandLineRunner` are invoked. After the runners finish, Boot publishes `ApplicationReadyEvent` and publishes readiness `ACCEPTING_TRAFFIC`.

Therefore, **liveness can already be CORRECT while readiness is still REFUSING_TRAFFIC**. This is a valid state: the container has finished creating the necessary components, but application-level startup steps have not finished yet.

If startup fails, the application may publish `ApplicationFailedEvent` and never reach the ready state. For orchestration systems, readiness and startup/liveness probes should be combined according to deployment policy to avoid routing traffic to an instance that has not finished starting.

## 6. AvailabilityChangeEvent: Changing State via Events

`AvailabilityChangeEvent<S>` belongs to the `org.springframework.boot.availability` package, where `S` is the specific availability state type. When the event is published in the ApplicationContext, Spring Boot's availability mechanism records the new value; listeners can also receive the event for observability updates.

For example, a component needs to temporarily take an instance out of traffic rotation:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class TrafficAdmissionController {

    private final ApplicationEventPublisher publisher;

    public TrafficAdmissionController(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void pauseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void resumeNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

`AvailabilityChangeEvent.publish(...)` emits the event through `ApplicationEventPublisher`. Once the event is processed, `ApplicationAvailability` reflects the published state.

A maintenance workflow can call `pauseNewTraffic()` before starting, wait for the orchestrator to stop routing new requests to the instance, and then handle remaining tasks. Once the service again satisfies the conditions to accept traffic, it can call `resumeNewTraffic()`.

Point to remember: calling `publish(..., REFUSING_TRAFFIC)` **does not guarantee traffic stops immediately**. The load balancer, Kubernetes readiness probe, or another orchestration component must observe the state, update its target list, and may take some time before stopping routing.

### Publishing BROKEN on Unrecoverable Errors

You can publish a liveness change:

~~~java
AvailabilityChangeEvent.publish(
        publisher,
        LivenessState.BROKEN
);
~~~

This should only be done when an error truly renders the instance unable to continue operating safely or self-recovering. Restarting the process depends on external operational mechanisms, and the liveness probe must be configured appropriately.

Do not automatically switch liveness to `BROKEN` every time a request fails or an upstream returns a transient error.

### Distinguishing Application State from Single-Request State

Availability has **instance-wide** meaning. A request missing data, failing authentication, or encountering a business error usually only needs to be handled with the corresponding HTTP status and exception handling.

Do not switch the entire application to `REFUSING_TRAFFIC` or `BROKEN` just because of an ordinary request error. Choose state transitions based on the overall serving capacity of the instance.

## 7. Observing AvailabilityChangeEvent

In addition to reading the current state from `ApplicationAvailability`, an application can listen for state change events using `@EventListener`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityLogger {

    private static final Logger log =
            LoggerFactory.getLogger(AvailabilityLogger.class);

    @EventListener
    public void onAvailabilityChanged(AvailabilityChangeEvent<?> event) {
        if (event.getState() instanceof LivenessState liveness) {
            log.info("Liveness changed to {}", liveness);
        } else if (event.getState()
                instanceof ReadinessState readiness) {
            log.info("Readiness changed to {}", readiness);
        }
    }
}
~~~

The logger above receives events and logs the new value. Reading state via `ApplicationAvailability` gives code the latest recorded state, while a listener lets you react at the moment the change occurs.

In systems with multiple contexts or event publishers, pay attention to context scope and event propagation. Do not treat the event as a cluster-wide state change signal. Each instance has its own availability.

If external systems need to know the state, it is usually best to expose it through health probes or monitoring systems rather than manually emitting notifications from every listener.

## 8. Spring Boot Actuator Provides Liveness and Readiness Probes

When Spring Boot Actuator is added, a web application can expose dedicated health groups for liveness and readiness. These two groups use health indicators based on `ApplicationAvailability`:

- `livenessState`: reflects `LivenessState`.
- `readinessState`: reflects `ReadinessState`.

The commonly used endpoints are:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

In Kubernetes, Spring Boot can automatically enable health probe groups based on the detected environment. When running outside Kubernetes and still wanting to use them, you can enable them explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

With Gradle, the application needs the Actuator dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

These are observation endpoints. Spring Boot maps the availability state to a health group status, and then to an HTTP status according to the health endpoint configuration.

| Availability state | Typical health status | Typical HTTP status |
|---|---|---|
| `LivenessState.CORRECT` | `UP` | 200 |
| `LivenessState.BROKEN` | `DOWN` | 503 |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | 200 |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | 503 |

These codes represent common default health status mapping behavior. An application can customize HTTP status mapping or health groups, so check the actual endpoints if the environment has custom Actuator configuration.

### Kubernetes Probes Example

A Deployment configuration can call the application's health paths:

~~~yaml
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
  failureThreshold: 3
~~~

The example assumes Actuator endpoints are served on application port `8080`. If Actuator uses a separate port, the paths and port in the probes must be configured accordingly.

Kubernetes uses the liveness probe to decide when a container needs to be restarted if the probe fails repeatedly. The readiness probe decides when a Pod is ready to receive traffic from a Service; when the probe fails, the Pod can be removed from the serving endpoints without being restarted.

In slow-starting applications, you can also use a `startupProbe` so Kubernetes does not apply liveness thresholds too early during startup. Do not use arbitrary delays as a substitute for understanding the actual startup process.

### When the Management Server Runs on a Different Port

If `management.server.port` is set to a different port from the main port, probes may only check that the management server is running without accurately reflecting the request path of the main application.

Spring Boot can expose additional health probe paths directly on the application port with:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

With this configuration, the typical additional paths are:

~~~text
GET /livez
GET /readyz
~~~

These additional endpoints on the main port help verify the serving capability of the application's web server itself, avoiding checking only an independent management server.

## 9. Integrating Readiness into the Shutdown Process

Readiness is especially useful during shutdown. During a rolling update deployment, an instance needs to stop accepting new requests while still possibly needing time to finish in-flight work.

A typical operational sequence:

~~~text
Shutdown / instance replacement requested
        |
        v
Readiness = REFUSING_TRAFFIC
        |
        v
Orchestrator stops sending new requests
        |
        v
Complete in-flight requests and tasks
        |
        v
Stop web server, close context and resources
        |
        v
Process terminates
~~~

Spring Boot supports graceful shutdown for supported web servers and integrates with the ApplicationContext lifecycle. It can be configured as:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

`server.shutdown=graceful` instructs the web server to perform a controlled shutdown according to the server's capabilities. `spring.lifecycle.timeout-per-shutdown-phase` sets the time limit for each shutdown phase of the Spring lifecycle.

Availability state and graceful shutdown are two complementary parts:

- Readiness publishes whether the instance should receive new traffic.
- The orchestrator or load balancer decides whether to continue routing traffic.
- Graceful shutdown handles stopping the server and completing ongoing work within the allowed time.

Publishing `REFUSING_TRAFFIC` should not be mistaken for completing graceful shutdown by itself. It does not replace drain duration, load balancer timeouts, Pod termination policies, or closing application resources.

In distributed systems, you must account for readiness update latency and the possibility that a request was already routed before the instance was removed from the pool. That is why the shutdown process needs to coordinate both readiness signals and the ability to finish remaining requests.

## 10. Do Not Put Every Dependency into the Liveness Probe

A common operational mistake is having the liveness probe check a database, message broker, or external API. When a shared dependency experiences an outage, all instances may fail their liveness probes simultaneously and restart repeatedly.

That behavior can create a restart loop and increase load on the failing dependency.

**Liveness should reflect the recoverability of the application itself.** If the database temporarily loses connectivity and the service can recover when the database returns, liveness should usually not be marked `BROKEN`.

Readiness may need to consider certain essential dependencies if the application genuinely cannot serve work when they are unavailable. However, you must weigh the impact of taking the entire system out of the pool:

- If a dependency loses connection, are all replicas unable to serve or is only a subset of tasks affected?
- Is the readiness check too slow or overly sensitive to brief errors?
- When the dependency recovers, does the application automatically flip readiness back?
- Does removing all replicas from the target list leave the system with no path to handle requests or no way to self-recover?

By default, Spring Boot does not automatically include all external health indicators in the readiness group. When needed, an application can customize health groups, but this should be done with an understanding of failure boundaries and orchestrator behavior.

## 11. Checking State While the Application Is Running

Availability can be observed in three complementary ways.

**Read directly via ApplicationAvailability:** a component in the context can call `getLivenessState()` and `getReadinessState()` to get the latest recorded state.

**Listen for AvailabilityChangeEvent:** a listener receives the event when a new state is published, suitable for logging or updating metrics.

**Check health probes:** external systems call `/actuator/health/liveness` and `/actuator/health/readiness` to make orchestration decisions.

Some scenarios worth testing when building an application:

| Scenario | Expected Liveness | Expected Readiness |
|---|---|---|
| Application is starting up | Not yet `CORRECT` until appropriate milestone | `REFUSING_TRAFFIC` |
| Context refreshed, runners executing | `CORRECT` | `REFUSING_TRAFFIC` |
| Startup complete, able to serve | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Proactively pausing incoming traffic | `CORRECT` | `REFUSING_TRAFFIC` |
| Maintenance complete, able to serve again | `CORRECT` | `ACCEPTING_TRAFFIC` |
| Unrecoverable internal error | `BROKEN` | Depends on shutdown and error policy |
| Graceful shutdown in progress | May still be `CORRECT` while draining | `REFUSING_TRAFFIC` |

The table describes target states across the lifecycle and events published by the application. The actual state at a given moment depends on the startup/shutdown stage and the `AvailabilityChangeEvent`s published by the application or framework.

If using Actuator outside Kubernetes, remember to enable health probes if needed. If deploying on Kubernetes, verify the exact endpoints, HTTP statuses, and ports that the probes actually call. When configuring dynamic readiness, observe both the transition from accepting to refusing and the recovery transition.

## 12. Common Misconceptions

### Liveness and readiness are the same thing

Incorrect. Liveness answers whether the process should remain alive; readiness answers whether the instance can accept new work. An instance can be live yet not ready during startup, maintenance, or draining.

### ApplicationReadyEvent means everything stays ready forever after

`ApplicationReadyEvent` is a startup milestone. `ReadinessState` is a state that can be updated multiple times after startup via `AvailabilityChangeEvent`. Having been ready once does not mean the application cannot transition to `REFUSING_TRAFFIC`.

### Publishing REFUSING_TRAFFIC automatically blocks HTTP requests

Incorrect. The state change event is published inside the application. A mechanism such as a Kubernetes readiness probe and Service routing must act on that state. Some in-flight or recently routed requests may still proceed.

### Publishing BROKEN automatically restarts the JVM

Incorrect. `BROKEN` publishes internal health status. Restarting depends on the monitoring system or orchestrator observing the liveness probe and the configured restart policy.

### Check the database in liveness so the application stays healthy

Checking external dependencies in liveness can cause all replicas to restart simultaneously due to a shared outage. Reserve liveness for unrecoverable internal failures; choose readiness or separate health groups for dependencies based on operational requirements.

### Assuming health and availability are the same API

`ApplicationAvailability` manages liveness/readiness states; Actuator health aggregates `HealthIndicator`s to report health. The liveness/readiness health groups can use availability states, but health and availability have different scopes of responsibility.

## 13. How to Choose and Use States Appropriately

When designing state signals for a Spring Boot service:

1. Clearly define when an instance is allowed to accept new traffic.
2. Use `ReadinessState.REFUSING_TRAFFIC` for incomplete startup phases, temporary traffic draining, or preparing to shut down.
3. Transition to `ReadinessState.ACCEPTING_TRAFFIC` when the instance truly meets serving conditions.
4. Only publish `LivenessState.BROKEN` for severe internal errors that cannot recover under the application's policy.
5. Use `ApplicationAvailability` to read the current state and `AvailabilityChangeEvent` to publish changes.
6. Use Actuator health probes so operational systems can observe state, along with appropriate liveness, readiness, and startup probe configurations.
7. Coordinate readiness with graceful shutdown, timeouts, and load balancer draining time.
8. Avoid turning health probes into heavy, unstable dependency-check chains.

`ApplicationAvailability` establishes a clear contract between the Spring Boot lifecycle and operational infrastructure. Liveness indicates when a process can no longer recover; readiness indicates when an instance is ready or temporarily pausing new work. When applied properly, these two signals enable applications to start, serve, pause, and terminate in a more observable and controllable way.
