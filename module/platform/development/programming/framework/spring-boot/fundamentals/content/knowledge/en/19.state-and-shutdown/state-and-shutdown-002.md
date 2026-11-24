# Liveness, Readiness, and Their Different Purposes

A Spring Boot application may still be running yet not be in a condition to serve requests. For example, the Java process and HTTP server are both active, while initialization data has not finished loading, the system has stopped accepting requests for maintenance, or an essential component is not ready yet. Conversely, an application may enter a severe error state where the most sensible way to recover is to restart the process.

These two questions correspond to two concepts:

- **Liveness:** Is the application process still functioning well enough to keep running, or is it in a broken state to the point where it should be restarted?
- **Readiness:** Is the application instance currently ready to receive new traffic?

Spring Boot represents them via `ApplicationAvailability`, `LivenessState`, and `ReadinessState`; Spring Boot Actuator can expose health probe endpoints for deployment platforms such as Kubernetes.

**Distinguishing their purposes correctly is the most important thing:** liveness typically decides *whether to restart the container*, while readiness typically decides *whether to route new traffic to the instance*. If liveness is used to check every external dependency, a brief database glitch can trigger a wave of unnecessary restarts. If only liveness is checked without readiness, requests can be routed to an instance that has not finished starting up.

This lesson explains availability states in Spring Boot, the startup and shutdown lifecycle, how to enable Actuator endpoints, configuring Kubernetes probes, handling external dependencies, and real-world scenarios when states need to change.

## 1. Two Questions, Two Different Operational Actions

Imagine an e-commerce application with three instances running behind a load balancer:

~~~text
             Client requests
                    |
                    v
              Load balancer
             /      |      \
            v       v       v
        Instance A  B       C
         Ready     Not ready Ready
~~~

Instance B is still running and the JVM is not dead, but it is loading necessary data. There is no need to restart B; it only needs to temporarily avoid receiving new routed requests. This is a **readiness** scenario.

Another scenario: instance C suffers an internal error that cannot recover through ordinary retries—for example, an essential processing thread permanently stops and the application proactively switches to a broken state. Restarting C may be the way to recover. This is a **liveness** scenario.

| Aspect | Liveness | Readiness |
| --- | --- | --- |
| Question | Should the application continue running? | Is the application ready to serve new requests? |
| Goal | Detect broken states requiring recovery via restart | Control traffic reception |
| When check fails in Kubernetes | Kubelet may restart the container per probe configuration | Pod is marked unready; Service stops selecting that endpoint for new traffic |
| Common cases | Deadlock / severe unrecoverable internal error | Starting up, draining, initialization incomplete |
| Should it depend on an external database? | Usually **no** | Only if the database is truly required for the instance to serve traffic |
| Does it replace system-wide health checks? | No | No |

A failing readiness check does not mean the application is "dead". A passing liveness check also does not prove the application can serve business requests.

## 2. Spring Boot's ApplicationAvailability

Spring Boot provides the `ApplicationAvailability` API to query the application's operational state.

Main types:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
~~~

`ApplicationAvailability` manages and provides the current availability state based on state transition events within the application.

### 2.1. The Two Values of LivenessState

`LivenessState` has two basic values:

- `CORRECT`: The application is considered to be in a normal live state.
- `BROKEN`: The application is considered broken and unable to continue functioning properly.

Example:

~~~java
LivenessState state = applicationAvailability.getLivenessState();

if (state == LivenessState.CORRECT) {
    System.out.println("Application is live");
}
~~~

Do not switch to `BROKEN` just because an auxiliary external service temporarily stops responding. Restarting the application usually does not fix an outage of a shared database or external system.

### 2.2. The Two Values of ReadinessState

`ReadinessState` has two basic values:

- `ACCEPTING_TRAFFIC`: The instance is ready to accept traffic.
- `REFUSING_TRAFFIC`: The instance should not accept new traffic at this time.

Example:

~~~java
ReadinessState state = applicationAvailability.getReadinessState();

if (state == ReadinessState.REFUSING_TRAFFIC) {
    System.out.println("Instance is not ready for new requests");
}
~~~

An instance can simultaneously have:

~~~text
LivenessState = CORRECT
ReadinessState = REFUSING_TRAFFIC
~~~

This is a completely valid state. The application is healthy at the process level but temporarily pausing new requests.

### 2.3. Reading State from a Component

Example of a component reading availability:

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityReporter implements ApplicationRunner {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Liveness: " + availability.getLivenessState()
        );
        System.out.println(
                "Readiness: " + availability.getReadinessState()
        );
    }
}
~~~

`ApplicationRunner` runs after the ApplicationContext has refreshed, but before Spring Boot publishes `ApplicationReadyEvent`. Therefore, at the moment the runner executes, liveness is typically already `CORRECT`, while readiness is usually still `REFUSING_TRAFFIC`.

This is not a bug: readiness is waiting for the startup phase—including runners—to finish.

## 3. Startup Lifecycle and Availability State

Spring Boot manages availability states according to lifecycle milestones. In a typical startup sequence:

~~~text
SpringApplication.run()
        |
        v
   Starting up
   Liveness = BROKEN
   Readiness = REFUSING_TRAFFIC
        |
        v
 ApplicationContext refreshed
        |
        v
 ApplicationStartedEvent
   Liveness = CORRECT
   Readiness = REFUSING_TRAFFIC
        |
        v
 ApplicationRunner / CommandLineRunner
        |
        v
 ApplicationReadyEvent
        |
        v
 Readiness = ACCEPTING_TRAFFIC
        |
        v
  Ready to accept traffic
~~~

In the standard lifecycle, Spring Boot's availability milestones can be summarized as follows:

| Phase | Liveness | Readiness | Meaning |
| --- | --- | --- | --- |
| Startup begins | `BROKEN` | `REFUSING_TRAFFIC` | Not started enough yet |
| After context refresh, before runners finish | `CORRECT` | `REFUSING_TRAFFIC` | Process is active but not yet ready |
| After startup completes | `CORRECT` | `ACCEPTING_TRAFFIC` | Can accept traffic |
| Controlled shutdown begins | Usually still `CORRECT` | `REFUSING_TRAFFIC` | Stop accepting new traffic to close application |

Some milestones occur before the HTTP server can serve health endpoints. Thus, startup probes and external check timing configurations remain important.

### 3.1. ApplicationStartedEvent vs. ApplicationReadyEvent

`ApplicationStartedEvent` is published after the ApplicationContext refreshes, **before** runners execute.

`ApplicationReadyEvent` is published once runners have completed, near the end of startup.

Readiness typically transitions to `ACCEPTING_TRAFFIC` after the ready milestone. Therefore, do not assume that handling an `ApplicationReadyEvent` means the readiness indicator necessarily already returns `UP` at the exact moment the listener is executing: you must consider the exact order of event publication and availability updates.

### 3.2. Why Can a Runner Keep an Instance Unready?

Suppose a runner needs to load reference data:

~~~java
@Component
public class ReferenceDataLoader implements ApplicationRunner {

    private final ReferenceDataService referenceDataService;

    public ReferenceDataLoader(
            ReferenceDataService referenceDataService) {
        this.referenceDataService = referenceDataService;
    }

    @Override
    public void run(ApplicationArguments args) {
        referenceDataService.loadRequiredData();
    }
}
~~~

`ReferenceDataService` is an application service that loads mandatory data.

While the runner is still running, Spring Boot has not finished startup and has not announced readiness to accept traffic. If loading the data is a prerequisite for serving requests, a runner can be an appropriate lifecycle hook.

However, do not put every non-essential background task into a runner if they unnecessarily prolong startup. Distinguish between data that *must exist before accepting requests* and work that *can complete after the application is ready*.

## 4. How Does Actuator Expose Liveness and Readiness?

Spring Boot Actuator can translate availability into health indicators and health groups so deployment platforms can query them over HTTP.

Add the dependency to a Maven Spring Boot project:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

When health probes are enabled and the HTTP server/Actuator is configured appropriately, there are typically two endpoints:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

The liveness group includes the `livenessState` contribution. The readiness group includes the `readinessState` contribution.

When liveness is correct, the response can be:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

When readiness refuses traffic, the response can be:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"OUT_OF_SERVICE"}
~~~

The output format and media type may vary by Actuator version and configuration. What matters for an HTTP probe is the **HTTP status code**: typically health groups return 2xx for `UP` and 503 for `DOWN` or `OUT_OF_SERVICE`.

### 4.1. Enabling Probes Outside Kubernetes

Spring Boot can automatically enable probe support when it detects it is running on Kubernetes. If you want to test these endpoints locally, you can enable them explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Or in `application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

After the application starts, test:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

The example assumes the application uses port `8080`, the default context path, Actuator on the same port, and accessible HTTP health endpoints. If the project changes `server.port`, `management.server.port`, base path, or security, the actual URLs may differ.

### 4.2. Do Not Confuse /actuator/health with Individual Probes

The overall endpoint:

~~~text
/actuator/health
~~~

can aggregate many health indicators such as database, disk space, or application components.

The two groups:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

serve dedicated purposes and by default focus on their respective availability states when enabled.

Do not point a Kubernetes liveness probe at the overall health endpoint if the overall endpoint includes database checks. A database outage could cause overall health to fail and trigger restarts even though the application itself is functioning normally.

## 5. Why Should Liveness Not Check External Dependencies?

Suppose an application has 10 instances, all connecting to one database. The database experiences a 30-second network outage.

If each instance's liveness probe also checks the database:

~~~text
Database temporarily unreachable
                 |
                 v
       Overall health reports DOWN
                 |
                 v
    All 10 instances fail liveness
                 |
                 v
       Kubernetes restarts all 10
                 |
                 v
  Database returns, but apps still must
  start up / reconnect / warm up again
~~~

Mass restarts do not fix the database and can prolong the outage. When the database recovers, the instances all reconnect simultaneously, creating extra load.

Therefore, liveness should reflect **internal, non-self-recovering** problems of the application. Some examples to evaluate:

- A core component stops permanently with no recovery mechanism.
- An internal state makes the application unable to continue serving properly regardless of traffic.
- A severe deadlock or process failure where restarting is a reasonable recovery choice.

Not every internal error needs to fail liveness. Many request errors, exceptions, brief congestion, or timeouts can self-recover and should be handled via retries, backpressure, timeouts, or separate coordination mechanisms.

**Design rule:** a failing liveness signal should only be triggered when a restart has a chance of improving the situation. If restarting does not help or makes the outage worse, that signal does not belong in liveness.

## 6. What Should Readiness Check?

Readiness answers whether **the current instance can accept new traffic**.

It typically refuses traffic when:

- The application has not finished starting up.
- An essential data-loading step has not completed.
- The instance is draining for shutdown or maintenance.
- An internal component required to serve requests is temporarily disrupted.
- An essential dependency makes it impossible to serve any critical requests.

However, **do not reflexively put all external dependencies into readiness**.

For example, if the email-sending system fails while product browsing still works, marking the entire instance not-ready can shut down unrelated features. If a shared system goes down for all instances, including that failure in readiness for every instance can leave the entire Service with zero ready endpoints.

Ask:

1. If this dependency fails, can the instance still process useful traffic?
2. Is the error instance-specific or does it affect all instances?
3. If this instance is removed from the load balancer, can another instance handle it better?
4. Does failing readiness reduce user-facing errors, or just leave all traffic with nowhere to go?
5. Is the check fast, stable, and configured with a clear timeout?

Readiness is a decision about **accepting traffic**, not a status report on the entire external ecosystem.

### 6.1. Default Set of Health Indicators

When probe health groups are enabled, Spring Boot typically includes only `livenessState` in the liveness group and `readinessState` in the readiness group.

Other health indicators such as database, Redis, or disk space are not automatically pulled into readiness just because they exist in the context. This is intentional: the application must decide for itself which checks apply to its ability to accept traffic.

### 6.2. Adding a Truly Essential Dependency to Readiness

If the database is strictly required for *all requests to be served*, you can include the `db` health contributor in the readiness group:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,db
~~~

This configuration assumes the application has a datasource and a registered health indicator named `db`. If the `db` contributor does not exist, review the conditions and health group configuration, because Boot may report an error when a group references a non-existent contributor.

Do not add `db` to liveness just to have a "more comprehensive check".

### 6.3. Custom HealthIndicator for Readiness

To check application-specific state, you can create a `HealthIndicator`:

~~~java
@Component("inventoryGateHealthIndicator")
public class InventoryGateHealthIndicator implements HealthIndicator {

    private final InventoryGate inventoryGate;

    public InventoryGateHealthIndicator(InventoryGate inventoryGate) {
        this.inventoryGate = inventoryGate;
    }

    @Override
    public Health health() {
        return inventoryGate.canServeRequests()
                ? Health.up().build()
                : Health.outOfService().build();
    }
}
~~~

Here `InventoryGate` is an application-defined abstraction providing `canServeRequests()`. In a real project, define and register the corresponding bean.

The `inventoryGateHealthIndicator` bean produces a health contributor named `inventoryGate`. It can be included in the readiness group:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,inventoryGate
~~~

When the gate disallows requests, the readiness group can return `OUT_OF_SERVICE`, regardless of whether Boot's `ReadinessState` is already `ACCEPTING_TRAFFIC`.

Make the check fast and safe; if it calls a network service, set a timeout and limit its impact. Probes are called repeatedly on a frequent schedule by the operations platform.

## 7. Configuring Kubernetes livenessProbe and readinessProbe

In Kubernetes, kubelet periodically calls the probes configured in the Deployment or Pod spec. An example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: application
          image: example/catalog-service:1.0.0
          ports:
            - containerPort: 8080
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
~~~

This is an illustrative configuration. Image, port, periods, and thresholds must be adjusted to fit the real system.

### 7.1. When the Liveness Probe Fails

If the liveness probe fails the configured number of times, kubelet can terminate the container and restart it according to the restart policy.

Example:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

Do not assume the container will always restart after exactly 30 seconds in every case: actual timing also depends on probe start time, timeouts, scheduling, Pod state, and other settings. The values above specify check cadence and failure threshold.

### 7.2. When the Readiness Probe Fails

Kubernetes marks the container/Pod unready and stops selecting that Pod as a ready endpoint for normal Service routing.

This is a traffic orchestration behavior. A failing readiness probe **does not directly request a container restart**.

For example, a Pod loading a cache may still be alive while readiness returns an error. Once cache loading finishes, the probe succeeds, and the Pod returns to the ready endpoint list.

Readiness controls new traffic; existing connections, in-flight requests, and proxy/load balancer behavior must be handled separately during graceful shutdown.

### 7.3. HTTP Codes and Health Status

A Kubernetes HTTP probe treats HTTP responses within Kubernetes's success range as passing; error HTTP statuses like `503` count as failures.

With typical Actuator health configuration:

| Spring health status | Typical HTTP response | Probe |
| --- | --- | --- |
| `UP` | `200 OK` | Success |
| `DOWN` | `503 Service Unavailable` | Failure |
| `OUT_OF_SERVICE` | `503 Service Unavailable` | Failure |

If the application customizes status-to-HTTP-code mapping, ensure Kubernetes probes still receive the right signal.

## 8. Startup Probe: Protecting Slow-Starting Applications

A liveness probe that starts too early can restart an application while it is still starting normally. For example, initial startup may need to load classes, initialize connection pools, or build caches, taking longer than the probe allows.

Kubernetes provides **startupProbe** to handle this situation.

~~~yaml
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

In this example, the startup probe gives a relatively generous tolerance window for startup. Until the startup probe succeeds, Kubernetes does not begin executing the liveness and readiness probes.

After the startup probe succeeds, liveness and readiness operate according to their normal configurations.

### 8.1. Why Does startupProbe Often Point to Liveness?

The startup probe only needs to determine that the application has started enough for other probes to begin. For Spring Boot, the liveness endpoint is usually a suitable choice. Readiness may still refuse traffic due to runners or longer initialization steps.

If the startup probe points to readiness, the container could be restarted simply because a data-loading step or external dependency is not ready yet, even while the process is progressing normally. Decide based on the startup workload and operational policy.

### 8.2. StartupProbe Does Not Replace Readiness

A passing startup probe does not mean the application is ready to serve every request. Readiness still needs to confirm whether the application should receive traffic.

The three probes work together:

~~~text
Startup probe: Has it started enough for normal checks?
Liveness:      Does the process need to be restarted?
Readiness:     Should new traffic be sent to the instance?
~~~

Not every application needs a startupProbe, but it is useful when startup can take a long time or vary significantly.

## 9. Separate Management Port and the Risk of Probing the Wrong Port

Spring Boot Actuator can run on the same application port or on a separate management port.

Example:

~~~properties
server.port=8080
management.server.port=9090
management.endpoint.health.probes.enabled=true
~~~

In that case, health endpoints may be served on `9090`, while business requests run on `8080`.

There is a risk: the management port might return healthy even if the application's connector on the main port is having problems. A probe only verifies the port it calls, so if the system needs to check real HTTP serving capability, a probe path on the main port can be more useful.

Spring Boot supports exposing additional probe paths on the main server port:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

When enabled, the default additional paths are typically:

~~~text
GET /livez
GET /readyz
~~~

and they are served on the main server port. With the configuration above:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
~~~

Exact paths depend on base path configuration, version, and the additional-paths mechanism used by the application. Always verify the actual URLs when deploying.

### 9.1. Choosing Paths for Kubernetes

If Actuator and the application run on the same port, you can use:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

If the management port is separate, consider using the additional paths on the application port:

~~~text
/livez
/readyz
~~~

Example Kubernetes configuration:

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

This must be paired with `management.endpoint.health.probes.add-additional-paths=true` and the actual web configuration. Do not treat a URL in documentation as proof that the endpoint exists: call the endpoint in the running environment to verify.

## 10. Changing Readiness via AvailabilityChangeEvent

Spring Boot publishes `AvailabilityChangeEvent` when availability state changes. The application can also publish this event to proactively update state.

For example, when entering a controlled maintenance mode, the instance needs to stop accepting new traffic:

~~~java
package com.example.demo;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class TrafficGate {

    private final ApplicationEventPublisher events;

    public TrafficGate(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
                events,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptNewTraffic() {
        AvailabilityChangeEvent.publish(
                events,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

A maintenance orchestration service can call `refuseNewTraffic()`, wait for traffic routing to stop sending new requests, and then perform the required work. Once the application is truly able to serve again, it can call `acceptNewTraffic()`.

**Do not expose an unauthenticated public endpoint allowing any caller to invoke these two methods.** Changing availability state is an internal operational action; if exposed via an admin API, proper authorization and controls are required.

### 10.1. Do Not Publish ACCEPTING_TRAFFIC Too Early

If the application is still loading data or has not finished initializing essential components, do not manually publish `ACCEPTING_TRAFFIC` just to make the readiness probe green.

Similarly, if the readiness group contains a custom health indicator reporting `DOWN` or `OUT_OF_SERVICE`, publishing `ACCEPTING_TRAFFIC` alone will not necessarily make the entire health group return `UP`.

### 10.2. Do Not Confuse Changing State with Shutting Down the HTTP Server

Publishing `REFUSING_TRAFFIC` updates availability and the corresponding health probe. It **does not automatically close sockets** or force all direct HTTP requests to be rejected.

Kubernetes or the load balancer must use the readiness probe to remove the instance from receiving new traffic. If a client still calls the instance's IP/port directly, the application may continue accepting requests depending on its logic.

Readiness is an **orchestration signal**, not a firewall or automatic request blocker.

### 10.3. Timing of State Updates During Startup

Spring Boot publishes availability states automatically during startup. If the application manually publishes readiness `REFUSING_TRAFFIC` too early, a subsequent `ACCEPTING_TRAFFIC` event published by Boot when ready can overwrite that value.

For work required before ready, let a runner finish it or use a dedicated readiness health contributor. For runtime maintenance, publish state after startup and maintain a clear process for bringing the instance back into service.

## 11. When Should Liveness Be Marked BROKEN?

Spring Boot allows publishing `AvailabilityChangeEvent` with `LivenessState.BROKEN`:

~~~java
AvailabilityChangeEvent.publish(
        applicationEventPublisher,
        LivenessState.BROKEN
);
~~~

This is a strong signal: if the Kubernetes liveness probe observes the broken state for long enough, the container may be restarted.

Use it only when the application hits an internal condition where it can no longer operate properly and restarting is considered a reasonable recovery path. Do not publish `BROKEN` because:

- The database timed out once.
- A request returned HTTP 500.
- An external service is temporarily unresponsive.
- A cache has not warmed up yet.
- A retryable task is failing.
- The application is draining for normal shutdown.

For these situations, consider error handling, retries, circuit breakers, readiness, or appropriate coordination mechanisms.

**Note:** An HTTP liveness probe also checks whether the endpoint responds at all. If the process dies, hangs completely, or the HTTP server fails to serve the probe, kubelet can still detect failure even without the application explicitly publishing a `BROKEN` event.

## 12. Graceful Shutdown: Linking State and Application Termination

When deploying a new release, systems often need to replace one instance with another without cutting off in-flight requests.

A controlled shutdown process typically includes:

1. Receiving a termination request—for example, Kubernetes sends `SIGTERM`.
2. The instance stops being selected for new traffic via readiness or endpoint removal.
3. The server stops accepting new connections and allows a window for in-flight requests to complete.
4. Resources are closed and the process terminates.
5. The deployment system replaces the instance according to the rolling update policy.

In Spring Boot, graceful shutdown can be enabled for supported web servers:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

The `spring.lifecycle.timeout-per-shutdown-phase` property configures the timeout for each shutdown phase. This is an example; choose the timeout based on request characteristics and what the deployment environment allows.

In terms of availability, readiness should transition to `REFUSING_TRAFFIC` during shutdown. Liveness usually does not need to transition to `BROKEN` because a controlled shutdown is not an error requiring a restart.

### 12.1. Kubernetes terminationGracePeriodSeconds

Kubernetes has the property:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
~~~

This value sets the time limit a Pod is allowed to terminate after a termination request. It needs to be enough for any `preStop` hook, traffic routing propagation delay, and the application's graceful shutdown duration.

If Kubernetes's allowed time is too short, the process may be forcefully killed before finishing in-flight requests. If too long, rollouts may drag out unnecessarily. Measure and choose based on actual workload.

### 12.2. Failing Readiness Does Not Immediately Close Open Connections

A Pod becoming not-ready stops the Service from selecting it for new traffic, but established TCP connections, in-flight requests, or proxy routing caches may persist for a period of time.

Therefore, graceful shutdown also requires configuring HTTP server settings, timeouts, connection closure, long-running request management, and possibly infrastructure-level preStop/drain policies.

### 12.3. Why Not Use Liveness to Stop Traffic?

If you deliberately fail liveness during maintenance, Kubernetes may restart the container. That causes unwanted behavior when the real goal is merely to drain the instance from traffic.

Use readiness to stop accepting new traffic and the shutdown mechanism to stop the process.

## 13. Real-World Scenarios: Liveness or Readiness?

| Scenario | Liveness | Readiness | Explanation |
| --- | --- | --- | --- |
| JVM just started, context not done yet | Not yet live | Not ready | Wait for startup or `startupProbe` |
| Context refreshed, runner still loading data | Live | Not ready | Cannot serve requests yet |
| Application running and serving requests normally | Live | Ready | Normal steady state |
| Pod draining prior to shutdown | Live | Not ready | Drain traffic then stop |
| Email provider fails while read endpoints still work | Usually live | May remain ready | Handle failure for that isolated feature |
| Shared database disrupted | Should not self-fail liveness | Depends on traffic-serving requirements | Mass restarts usually do not help |
| One instance unable to serve due to broken local resource | Evaluate self-recovery capability | Can be not ready | Remove from traffic first; restart if needed |
| Internal component permanently broken and restart is the recovery path | Can be broken | Can be not ready | Liveness serves the restart mechanism |
| Auxiliary cache not warmed up yet, direct DB access still works | Live | Depends on SLA | Not strictly necessary to wait for cache |

The deciding factor is **the desired action from the orchestrator**: restart or temporarily withhold traffic. The same type of failure may require different policies depending on architecture.

## 14. Practical Checks and Diagnosing Misbehaving Probes

### 14.1. Check Endpoints on the Right Port

Test against the application environment:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

If using additional paths:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
~~~

Inspect both the response body and the HTTP code. A `404` response may mean the endpoint is not enabled, the path differs, or the management context path changed. `401`/`403` may be due to security configuration. `503` usually reflects health failing under the current mapping.

### 14.2. Checking Pod Status

In Kubernetes:

~~~bash
kubectl get pods
kubectl describe pod <pod-name>
~~~

`kubectl describe` typically displays events related to failed probes and restarts. You can view logs:

~~~bash
kubectl logs <pod-name>
~~~

For multi-container Pods, specify the appropriate container name. For a container that just restarted, you can view the previous run's logs:

~~~bash
kubectl logs <pod-name> --previous
~~~

Replace `<pod-name>` with the actual Pod name; it is a placeholder, not a literal command to run verbatim.

### 14.3. Reasons Probes Fail

- Probe uses the wrong port.
- `management.server.port` differs from the application port.
- Health probe endpoints are not enabled in the tested environment.
- Application changed context path or management base path.
- Endpoint is blocked by Spring Security or a network policy.
- Long startup without an appropriate `startupProbe`.
- Timeout is too short compared to actual latency.
- Health group includes a slow indicator or unstable external dependency.
- Readiness intentionally reports `REFUSING_TRAFFIC` because the app is starting or draining.
- Instance has started, but the main server port is not responding as expected.

Distinguish between an **HTTP probe** failure and **availability** state. A probe can fail with connection timeout or 404 even when `ApplicationAvailability` reports `CORRECT` and `ACCEPTING_TRAFFIC`.

### 14.4. Health Endpoints Do Not Replace Monitoring

A health probe is only a simple signal for the orchestrator. It does not fully explain the root cause of an incident.

For better diagnostics, combine logs, metrics, tracing, JVM/thread diagnostics, connection pool metrics, and dashboards. These help determine why readiness is refused or why the liveness endpoint is unresponsive.

## 15. Common Design Mistakes

### 15.1. Using Overall Health as Liveness

If `/actuator/health` includes database, Redis, and disk indicators, pointing liveness to it can trigger restarts when an external component fails.

**Fix:** use a dedicated liveness health group and include only components whose broken state genuinely requires restarting the application.

### 15.2. Configuring Only Liveness, Omitting Readiness

The application can receive traffic before finishing startup or during draining.

**Fix:** configure a readiness probe alongside liveness.

### 15.3. Using Readiness Failure to Expect a Container Restart

Readiness failure only makes the instance unready for new traffic. It does not tell kubelet to restart the container.

**Fix:** if an unrecoverable internal error occurs and restarting is appropriate, use a dedicated liveness signal.

### 15.4. Adding Every External System to Readiness

If a shared dependency drops connection, all instances may become not-ready together and the Service loses all endpoints.

**Fix:** include a dependency in readiness only when it is genuinely required to serve traffic and removing the instance improves serviceability.

### 15.5. Setting Probe Timeouts Too Low

A health indicator may run longer than the timeout, causing kubelet to treat the probe as failed even while the application is working.

**Fix:** measure actual latency, keep checks lightweight, and choose timeouts/thresholds tolerant of normal variance.

### 15.6. Running Long Initialization Without startupProbe

Repeated liveness failures during startup put the Pod in a restart loop.

**Fix:** add a `startupProbe`, tune thresholds appropriately, and evaluate whether initialization can be optimized or moved to another step.

### 15.7. Thinking Readiness REFUSING_TRAFFIC Blocks All HTTP Requests

Availability only emits a signal. If traffic is sent directly to the port, requests can still reach the application.

**Fix:** ensure the load balancer/Kubernetes uses the readiness probe and has an appropriate connection-draining policy.

### 15.8. Marking BROKEN on a Single Request Error

An HTTP 500 for one request does not necessarily mean the entire instance is unrecoverable.

**Fix:** handle request errors at the proper layer; only switch liveness to broken for truly severe errors with reliable detection mechanisms.

## 16. Combined Spring Boot and Kubernetes Configuration Example

Suppose an application uses Spring Boot Actuator on the same HTTP port `8080` and deploys on Kubernetes.

`application.yml`:

~~~yaml
server:
  port: 8080

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Probe URLs on the main port:

~~~text
http://localhost:8080/livez
http://localhost:8080/readyz
~~~

Deployment excerpt:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-api
  template:
    metadata:
      labels:
        app: inventory-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: inventory-api
          image: example/inventory-api:1.0.0
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
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
            failureThreshold: 2
~~~

At runtime:

1. The startup probe protects the initial startup phase.
2. Once the startup probe succeeds, liveness begins checking whether the process can keep running.
3. Readiness checks the ability to accept new requests.
4. If readiness fails, the Pod is temporarily excluded as a ready endpoint.
5. If liveness fails past the threshold, kubelet can restart the container.
6. When a rollout stops the Pod, timeouts/graceful shutdown and routing policies give in-flight requests time to finish.

This configuration is an illustrative starting point. Production applications should validate against their own timeouts, resource usage, ingress/load balancer behavior, security, and startup/shutdown characteristics.

## 17. Practice Exercises

### Exercise A: Observe Both States During Startup

Create a Spring Boot application with `spring-boot-starter-actuator`. Enable health probes. Write an `ApplicationRunner` that injects `ApplicationAvailability` and prints both states.

Compare the state inside the runner with the result of `/actuator/health/readiness` after startup completes. Explain why readiness can differ between the two points in time.

### Exercise B: Change Readiness at Runtime

Create a `TrafficGate` service as in the example and add a controlled internal trigger. Publish `ReadinessState.REFUSING_TRAFFIC`, then call the readiness endpoint and inspect the HTTP status.

Publish `ReadinessState.ACCEPTING_TRAFFIC` when the application is genuinely ready again and observe the result.

### Exercise C: Experiment with Adding the Database to a Health Group

Take an application with a datasource and the `db` health contributor. Configure:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,db
~~~

Simulate a database connection loss and observe readiness. Explain when this configuration improves the system and when it could leave the entire Service with no ready endpoints.

### Exercise D: Compare startupProbe with livenessProbe

Create a runner that performs a long initialization step (for testing environments only). Configure a liveness probe with a low threshold and observe the restart loop if the application cannot open its endpoint in time. Then add a `startupProbe` and observe the difference.

Do not run failure-simulation exercises in production environments.

### Exercise E: Check a Separate Management Port

Set:

~~~properties
server.port=8080
management.server.port=9090
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Observe Actuator endpoints on the management port and `/livez`, `/readyz` on the main port. Explain why calling probes on the main port can better reflect HTTP serving capability in some cases.

### Exercise F: Design Graceful Shutdown

Suppose an API has requests taking up to 20 seconds. Choose reasonable values for `terminationGracePeriodSeconds` and `spring.lifecycle.timeout-per-shutdown-phase`, then describe how readiness, Service endpoints, and graceful shutdown coordinate to minimize interrupted requests.

Do not simply add two numbers together; consider load balancer traffic-draining latency, hooks, and actual request duration.

## 18. Self-Check Questions

**1. What different questions do liveness and readiness answer?**

Liveness asks whether the application should keep running or needs a restart. Readiness asks whether the instance should receive new traffic.

**2. Does `CORRECT` imply `ACCEPTING_TRAFFIC`?**

No. An application can be live yet not ready during startup or draining.

**3. In Kubernetes, does a failed readiness probe automatically restart the container?**

No. It prevents the Pod from being chosen as a ready endpoint for normal Service routing; liveness is the probe mechanism that can trigger restarts.

**4. Why should a database check not be placed in liveness?**

A database outage is usually not fixed by restarting every application instance; doing so can increase load and prolong the outage.

**5. Why can readiness still be REFUSING_TRAFFIC while an ApplicationRunner is executing?**

Because Boot has not completed the startup phase yet and has not transitioned to accepting traffic.

**6. Which Actuator endpoints are typically used for the two probes?**

`/actuator/health/liveness` and `/actuator/health/readiness` when health probes are enabled and the endpoints are properly exposed.

**7. When do `/livez` and `/readyz` appear?**

When additional paths for health probes are enabled via the corresponding Spring Boot configuration.

**8. What problem does StartupProbe solve?**

It gives the application startup time before Kubernetes begins executing liveness/readiness probes, reducing the risk of restarts during slow startups.

**9. Does `AvailabilityChangeEvent.publish(..., REFUSING_TRAFFIC)` automatically close the HTTP port?**

No. It changes availability state; the orchestrator must use the readiness signal to stop sending new traffic.

**10. During a controlled shutdown, should readiness or liveness fail?**

Typically readiness should refuse traffic. Normal shutdown is not a liveness failure requiring a restart.

## 19. Conclusion

**Liveness** and **readiness** are both Spring Boot state signals, but they serve two distinct operational decisions. Liveness reflects whether the process can continue functioning and may lead to a restart if the orchestrator detects failure. Readiness reflects whether an instance can accept new traffic, helping a load balancer or Kubernetes remove the instance from routing during startup, maintenance, or draining.

Spring Boot provides `ApplicationAvailability`, `LivenessState`, `ReadinessState`, and `AvailabilityChangeEvent` to monitor or update these states. Spring Boot Actuator can expose appropriate health probes; Kubernetes uses `livenessProbe`, `readinessProbe`, and, when needed, `startupProbe` to carry out the corresponding actions.

Keep liveness independent of temporary external system failures, choose readiness based on actual traffic-serving capability, check endpoints on the right port, and combine readiness with graceful shutdown when deploying new versions. Designing probes for their proper purposes prevents mass restarts, reduces request errors during startup/shutdown, and makes the system more resilient during incidents.

## References

- [Spring Boot Reference — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Kubernetes Documentation — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
