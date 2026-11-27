# Readiness vs. Liveness

## 1. Two signals answer two different questions

In **SPRING_GRPC**, a Spring application can open a gRPC server and serve multiple RPCs defined with Protocol Buffers. When deploying multiple instances, the platform needs to decide when to send traffic to an instance and when to restart the process. Those two decisions require two separate signals:

- **Readiness** answers: should the instance accept new requests right now?
- **Liveness** answers: is the process still functioning well enough to keep running, or does it need to be restarted?

Readiness often changes throughout the application lifecycle: starting up, ready, temporarily paused from receiving traffic, then ready again. Liveness reflects process health; a flapping external dependency is usually not a reason to restart the application.

~~~text
Application starting up
  liveness:   CORRECT (process is running)
  readiness:  REFUSING_TRAFFIC (not accepting requests yet)

Application ready
  liveness:   CORRECT
  readiness:  ACCEPTING_TRAFFIC

Required database temporarily disconnected
  liveness:   CORRECT
  readiness:  REFUSING_TRAFFIC

Process is deadlocked or unable to make progress
  liveness:   BROKEN
  readiness:  REFUSING_TRAFFIC
~~~

If the same health check is used for both decisions, a dependency error can cause Kubernetes to restart the container repeatedly. Meanwhile, all that was needed was to pause sending traffic and wait for the dependency to recover.

## 2. Readiness controls traffic admission

When readiness is `ACCEPTING_TRAFFIC`, the instance is considered eligible to receive new requests. When readiness transitions to `REFUSING_TRAFFIC`, the orchestration system should stop routing new requests to that instance.

Readiness can turn false in situations such as:

- The application has not finished initializing required configuration, caches, or data.
- A dependency required for the service is currently unavailable.
- The instance is draining for a new deployment or shutdown.
- The service is actively rejecting traffic due to overload under an admission control policy.

Readiness does not mean every request is guaranteed to succeed. A `READY` instance can still return `NOT_FOUND`, `INVALID_ARGUMENT`, `PERMISSION_DENIED`, or encounter a request-specific error. Readiness is only a general signal of capacity to accept new work.

In gRPC, readiness can be published via `grpc.health.v1.Health` for probes, client health checking, or proxies to consume. For a specific service, the status typically uses the full name such as `orders.v1.OrdersService`.

## 3. Liveness decides whether to restart the process

Liveness is a signal indicating whether the process is still alive and able to continue operating. If liveness fails consecutively beyond a configured threshold, Kubernetes can restart the container.

Liveness should detect severe internal conditions, for example:

- The process is deadlocked and cannot process work.
- An essential internal component is permanently stuck and cannot recover.
- An event loop or critical worker is no longer making progress.
- The application has entered an unrecoverable error state.

Do not include every external dependency in liveness. If the database temporarily loses connectivity, restarting all replicas at once can create a connection spike just as the database recovers. If DNS or a message broker flaps, mass restarts can turn a brief incident into a wider outage.

Liveness should also not be a deep, slow check depending on many systems. Probes need to respond quickly, consistently, and reflect the health of the process itself.

## 4. Further distinguishing startup probe and connectivity

In addition to readiness and liveness, understand two related concepts:

| Signal | Meaning | Impact |
|---|---|---|
| Startup probe | Has the application completed its startup phase? | Delays liveness/readiness probes until startup succeeds |
| Readiness | Should the instance receive new traffic? | Adds or removes the instance from the traffic pool |
| Liveness | Does the process need a restart? | May restart the container |
| gRPC connectivity `READY` | Channel/subchannel has established transport to send RPCs | Reflects connectivity only, does not prove business readiness |

A gRPC subchannel in the `READY` state only indicates that transport connectivity is ready. The server may be running while `OrdersService` is not yet ready because the database or startup data has not finished initializing.

Startup probes are useful when an application has a long startup time. If only liveness is used with too short a threshold, Kubernetes might restart the container before the application finishes starting up.

## 5. Readiness and liveness lifecycle

A typical lifecycle:

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready: Initialization complete
    Ready --> NotReady: Required dependency fails / drain
    NotReady --> Ready: Dependency recovers / drain ends
    Ready --> Restarting: Liveness fails
    NotReady --> Restarting: Liveness fails
    Restarting --> Starting
~~~

Liveness and readiness can change together, but they should not be rigidly coupled. For example, a database failure can make readiness false while liveness remains true. If the process deadlocks, liveness becomes false; readiness should also stop accepting traffic because the instance can no longer serve.

## 6. Kubernetes uses the two probes in two different ways

Kubernetes handles probe results differently:

- Readiness probe fails: the Pod is marked not ready and is typically removed from Service traffic endpoints. The container keeps running.
- Liveness probe fails consecutively beyond the threshold: kubelet restarts the container according to the restart policy.
- Startup probe has not succeeded yet: liveness and readiness probes are not executed yet; this gives the application time to start up.

Example using Spring Boot Actuator for readiness/liveness over HTTP:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health

---
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8081
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8081
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

These are two illustrative configuration snippets for Spring Boot and Kubernetes; in a real manifest, `readinessProbe` and `livenessProbe` sit under `spec.containers[].`. Ensure the management port and endpoint are exposed on a network reachable by the probe.

If using native gRPC probes, you can check the health service on the gRPC port:

~~~yaml
readinessProbe:
  grpc:
    port: 9090
    service: orders.v1.OrdersService
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
~~~

Native gRPC probes require the health service to be registered and return status for the matching service name. Kubernetes's built-in gRPC probe does not provide the full TLS/authentication options of an application gRPC client. If the endpoint only accepts mTLS or requires custom credentials, use a controlled probe endpoint or an appropriate probing mechanism instead of widening access to business APIs.

## 7. Spring Boot represents these two states

Spring Boot provides two groups of availability states:

- `LivenessState.CORRECT` and `LivenessState.BROKEN`.
- `ReadinessState.ACCEPTING_TRAFFIC` and `ReadinessState.REFUSING_TRAFFIC`.

When Actuator health probes are enabled, the `/actuator/health/liveness` and `/actuator/health/readiness` endpoints reflect these two groups respectively. Spring Boot also publishes availability events so the application can proactively change state:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

public final class TrafficAdmission {
    private final ApplicationContext context;

    public TrafficAdmission(ApplicationContext context) {
        this.context = context;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

For liveness, the application can publish `LivenessState.BROKEN` when it detects an unrecoverable internal condition:

~~~java
AvailabilityChangeEvent.publish(
        context,
        LivenessState.BROKEN);
~~~

Publish `BROKEN` only when a restart is genuinely the appropriate action. A typical database or downstream API error should be handled via readiness/dependency policy, not automatically turned into a liveness failure.

## 8. Do not mechanically put external dependencies into liveness

Spring Boot health indicators can check databases, disk, brokers, or external systems. Adding an indicator to readiness can be useful if that dependency is mandatory for serving traffic. Adding the same indicator to liveness often creates a restart loop risk.

Decision examples:

| Incident | Readiness | Liveness | Reason |
|---|---|---|---|
| Primary database is down and all RPCs need it | Can be `REFUSING_TRAFFIC` | Remains `CORRECT` | Wait for the database to recover without mass restarts |
| Optional cache fails but has a fallback | Can remain accepting | `CORRECT` | The service can still serve |
| Application is warming up | `REFUSING_TRAFFIC` | `CORRECT` | The process is initializing normally |
| Deadlock in an essential component | `REFUSING_TRAFFIC` | `BROKEN` | The process is no longer making progress |
| Performing graceful shutdown | `REFUSING_TRAFFIC` | Remains `CORRECT` during drain | Stop accepting new work, finish in-flight work |

Spring Boot separates liveness and readiness health groups by default. If you add a custom indicator, include it only in the group it actually serves. Do not assume every health indicator is automatically used for both endpoints.

## 9. Mapping Spring readiness to gRPC HealthStatusManager

An application may need both Actuator probes and a gRPC health service. In that case, you can use the same readiness source to update gRPC health status. Example:

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class GrpcReadinessBridge {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health;

    public GrpcReadinessBridge(HealthStatusManager health) {
        this.health = health;
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        ServingStatus status =
                event.getState() == ReadinessState.ACCEPTING_TRAFFIC
                        ? ServingStatus.SERVING
                        : ServingStatus.NOT_SERVING;
        health.setStatus(SERVICE, status);
    }
}
~~~

`HealthStatusManager` must be the same instance registered on the gRPC server. The bridge component only synchronizes service readiness; it does not turn every liveness event into a readiness event. When liveness transitions to `BROKEN`, the application also needs to stop accepting traffic before the process is restarted, though the two states still retain their distinct meanings.

If a server provides multiple services, you can map readiness per service instead of setting all statuses identically. For example, `InventoryService` depends on a broker while `OrdersService` can still serve using the database.

## 10. Graceful shutdown starts with readiness false

During a planned deployment or shutdown, the first goal is to stop sending new requests to the instance:

1. Transition readiness to `REFUSING_TRAFFIC`.
2. Update gRPC health to `NOT_SERVING` and/or deregister from service discovery.
3. Wait within a bounded window for endpoint updates to propagate to load balancers/clients.
4. Drain in-flight RPCs during the grace period.
5. Close the gRPC server, executors, and dependencies.

During draining, liveness can remain `CORRECT`: the process is functioning normally to finish existing RPCs. Do not flip liveness to `BROKEN` just to force Kubernetes to remove the Pod from traffic; that is the job of readiness.

For long-lived server streaming, define how streams end on shutdown and how clients reconnect/resume using a cursor or sequence. Readiness false does not automatically transfer active streams to another backend.

## 11. Common configuration mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using the same database-dependent check for readiness and liveness | Database outage causes continuous container restarts | Let readiness reflect serving ability; let liveness reflect only the process |
| Liveness probe is too sensitive | Restarts during warm-up or brief GC pauses | Use a startup probe, appropriate timeouts, and failure thresholds |
| Readiness always returns healthy as soon as the port opens | Traffic arrives before the service finishes initializing | Transition to accepting traffic after actual readiness |
| Restarting the container on readiness failure | Causes churn even though the process is healthy | Only liveness failures should trigger restarts |
| Putting all dependencies into readiness | An optional dependency knocks out all replicas | Identify mandatory dependencies per service |
| Using gRPC connectivity `READY` as readiness | Transport is good while business logic is not ready | Check health status at the service layer |
| Stopping the server before readiness updates propagate | New requests may get reset | Set readiness false, wait for propagation, then drain |
| Failing to restore readiness after a dependency recovers | Instance stays out of the traffic pool indefinitely | Monitor dependencies and republish `ACCEPTING_TRAFFIC` |

## 12. Testing readiness and liveness

Testing should verify the two decisions independently:

| Scenario | Result to verify |
|---|---|
| Application starting up | Readiness refuses traffic; startup probe allows enough time |
| Initialization complete | Readiness transitions to accepting traffic |
| Mandatory database temporarily fails | Readiness refuses traffic; liveness remains correct |
| Database recovers | Readiness returns to accepting traffic |
| Optional dependency fails | Readiness remains accepting if the service still meets its contract |
| Internal component deadlocks | Liveness transitions to broken; platform restarts after threshold |
| Graceful shutdown | Readiness turns false first; liveness stays correct during drain |
| gRPC health service | Service key reflects readiness, not just transport `READY` |
| Multiple gRPC services | One unhealthy service does not exclude an independent service if policy permits |
| Probe timeout or endpoint error | Failure threshold and recovery behavior match configuration |

Unit tests can verify events and state mapping. Integration tests in Kubernetes or an equivalent environment prove that readiness actually removes the Pod from traffic and liveness actually triggers a restart.

## 13. Observability and diagnostics

Monitor separately:

- Readiness and liveness state per Pod/instance.
- Counts of `ACCEPTING_TRAFFIC` ↔ `REFUSING_TRAFFIC` transitions.
- Liveness probe failure counts and container restarts.
- Startup duration, and time from readiness false until endpoint removal.
- Drain duration and number of open RPCs/streams.
- Dependencies causing readiness false and recovery time.
- Discrepancies between gRPC health, Actuator health, and Kubernetes Pod conditions.

If Pods continuously restart when the database flaps, check whether a database indicator was included in liveness. If a Pod does not restart even when the application is deadlocked, check whether the liveness probe actually detects that internal condition and whether it is configured too leniently.

**Remember:** Readiness controls whether an instance receives new traffic; liveness decides whether the process needs to be restarted. External dependencies generally affect readiness, while liveness should reflect the progress of the process itself. In Spring Boot use `ReadinessState` and `LivenessState`; in Kubernetes use separate readiness/liveness probes, adding a startup probe when needed. With gRPC, map readiness to `HealthStatusManager` so clients/proxies exclude the service from new selection, then drain existing RPCs before shutdown.
