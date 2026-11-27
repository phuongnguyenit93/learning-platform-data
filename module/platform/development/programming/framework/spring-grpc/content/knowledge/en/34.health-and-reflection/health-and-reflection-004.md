# Changing Health When Dependencies Fail

A service's health does not only reflect whether the process is still running. It also indicates whether the instance can accept and handle the types of requests the system is routing to it. With **Spring gRPC**, when a database, authentication service, or critical downstream experiences an outage, the application needs to update its health state so readiness probes, load balancers, and gRPC health clients make the right decisions.

You should not mark the entire process unhealthy just because a single downstream request failed. You need to determine which dependencies are mandatory, whether errors are sustained enough to count as an incident rather than an isolated failure, and which RPCs are actually affected. Health should change based on an evaluated state, with thresholds and recovery mechanisms to avoid rapid UP/DOWN flapping when a dependency is unstable.

## 1. Distinguishing liveness, readiness, and individual RPC service status

These three concepts serve different purposes:

| Health type | Question to answer | When a dependency fails |
| --- | --- | --- |
| **Liveness** | Is the process still alive and able to keep running? | Usually stays healthy; external dependency errors are not a reason to restart the process |
| **Readiness** | Should the instance accept new traffic? | Transitions to not ready if an essential dependency makes most functionality unservable |
| **gRPC service health** | Can a specific service/method group currently serve? | Can set NOT_SERVING for only the affected service while keeping other services SERVING |

For example, an application has OrderService and CatalogService. If the orders database goes down but the catalog can still read from cache, it is not necessary to mark the entire server out of service. You can set OrderService's health to NOT_SERVING while keeping CatalogService SERVING.

With Kubernetes, failing readiness usually removes the pod from traffic endpoints; failing liveness can cause the container to restart. Do not mechanically include dependency readiness in liveness, because a prolonged database outage can trigger a restart loop without fixing the database.

## 2. Classifying dependencies by impact

Before changing health, classify your dependencies:

- **Critical for the entire application:** if it fails, nearly all RPCs cannot complete—for example, a primary data store when every method needs to read/write it.
- **Critical for a service or method group:** only part of the API is affected—for example, PaymentService requires the payment ledger while ProfileService continues operating.
- **Optional or has a fallback:** failure may degrade features, but the application can still serve—for example, a recommendation service when a baseline result can be returned.
- **Dependency recoverable via cache/queue:** temporary failures do not necessarily fail readiness if the system can still accept and process requests per contract.

Health must reflect actual serving capability. An optional dependency should not cause the pod to be removed from the load balancer if core RPCs still work. Conversely, if a critical dependency causes all write requests to fail, keeping readiness UP can keep sending traffic to an instance unable to process it.

## 3. Do not change health on a single isolated error

An RPC error can be caused by an invalid request, permissions, too short a caller deadline, or a transient network glitch. Not every error indicates a broken dependency.

Classification examples:

| Downstream result | Should dependency health be updated? | Reason |
| --- | --- | --- |
| Repeated UNAVAILABLE | Possibly | May indicate the service or connection is unavailable |
| Repeated DEADLINE_EXCEEDED with reasonable internal timeout | Possibly | May reflect a slow or overloaded downstream |
| RESOURCE_EXHAUSTED | Depends on cause | May be throttling/quota or exhausted capacity |
| INVALID_ARGUMENT | No | Caller data/request error |
| PERMISSION_DENIED | No | Permission or policy error, not availability |
| CANCELLED from caller | No | Caller cancelled; does not prove dependency failure |
| Business NOT_FOUND | No | Valid outcome based on data state |

Only record errors attributable to the dependency. For example, DEADLINE_EXCEEDED from a client is not enough to mark the database down if the caller supplied too short a deadline. Distinguish downstream call timeouts from the overall deadline of the incoming request.

## 4. Using a circuit breaker or state monitor

A common approach is using a circuit breaker or dependency monitor as the source of state. A circuit breaker typically has three states:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: errors exceed threshold
    OPEN --> HALF_OPEN: wait duration elapsed
    HALF_OPEN --> CLOSED: enough probes succeed
    HALF_OPEN --> OPEN: probe fails
~~~

- **CLOSED:** requests are allowed through to the dependency; errors are tracked.
- **OPEN:** temporarily stops calling the dependency or fails fast to avoid adding load.
- **HALF_OPEN:** allows a limited number of requests/probes to test recovery.

The application can map this state to health. For a critical dependency, OPEN typically transitions the dependent service's readiness to OUT_OF_SERVICE or gRPC NOT_SERVING. Transition back to SERVING only after evidence of recovery, such as enough successful probes in HALF_OPEN.

To avoid health flapping, use error thresholds, statistical windows, cooldowns, and consecutive successes before recovering. Do not flip to SERVING just because a single random request succeeds immediately after a burst of failures.

## 5. Updating Spring Boot Actuator readiness

Spring Boot Actuator lets you write a HealthIndicator to publish dependency state. The indicator should read state already updated by the circuit breaker or monitor, rather than making a new blocking network call each time the health endpoint is queried.

Example state abstraction:

~~~java
public interface DependencyAvailability {
    boolean isCriticalDependencyReady();
    String state();
}
~~~

Health indicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("ordersDependency")
public final class OrdersDependencyHealthIndicator
        implements HealthIndicator {

    private final DependencyAvailability availability;

    public OrdersDependencyHealthIndicator(
            DependencyAvailability availability) {
        this.availability = availability;
    }

    @Override
    public Health health() {
        if (!availability.isCriticalDependencyReady()) {
            return Health.outOfService()
                .withDetail("dependency", "orders-database")
                .withDetail("state", availability.state())
                .build();
        }

        return Health.up()
            .withDetail("dependency", "orders-database")
            .withDetail("state", availability.state())
            .build();
    }
}
~~~

DependencyAvailability is an application abstraction updated from circuit breaker or monitor events. Avoid letting health() call the database or downstream directly with long timeouts: health probes can hang, adding load right when the dependency is overloaded.

You can configure separate health groups:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ordersDependency
        liveness:
          include: livenessState
~~~

The contributor name in include must match the registered health indicator ID. Include only dependencies critical to the pod's ability to accept traffic in the readiness group. Optional dependencies should show degraded details/metrics without necessarily failing readiness.

## 6. Updating the gRPC Health Checking Protocol

gRPC defines a standard health service with two primary RPCs:

- Check: the client queries the current status of a service.
- Watch: the client subscribes to a stream to receive status changes when health changes.

With gRPC Java, HealthStatusManager in the grpc-services library manages status and provides the service implementation. The project needs the grpc-services dependency at a version compatible with the gRPC Java artifacts in use:

~~~java
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

HealthStatusManager healthStatusManager =
    new HealthStatusManager();

healthStatusManager.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(9090)
    .addService(orderService)
    .addService(healthStatusManager.getHealthService())
    .build()
    .start();

// Transition to SERVING only after critical dependencies are ready.
healthStatusManager.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.SERVING);
~~~

This example illustrates a plain gRPC Java server. When a Spring gRPC starter manages the server automatically, register healthStatusManager.getHealthService() via the service registration or server builder customizer mechanism supported by the starter in use; do not create a second server just to add the health service.

The service name in the health protocol must match the full service name in the gRPC method path, such as acme.orders.v1.OrderService. The empty string "" represents the overall server status. Only set the overall status to NOT_SERVING when the entire server truly cannot accept traffic; if only one service fails, update its corresponding service name.

## 7. Pushing dependency state to the gRPC health service

When the monitor or circuit breaker detects a dependency state change, a publisher updates the health manager. Publish only when the status actually changes to avoid emitting duplicate events:

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public final class OrdersGrpcHealthPublisher {

    private static final String SERVICE =
        "acme.orders.v1.OrderService";

    private final HealthStatusManager healthManager;
    private final AtomicReference<ServingStatus> current =
        new AtomicReference<>(ServingStatus.NOT_SERVING);

    public OrdersGrpcHealthPublisher(
            HealthStatusManager healthManager) {
        this.healthManager = healthManager;
        healthManager.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }

    public void dependencyUnavailable() {
        publish(ServingStatus.NOT_SERVING);
    }

    public void dependencyRecovered() {
        publish(ServingStatus.SERVING);
    }

    private void publish(ServingStatus next) {
        ServingStatus previous = current.getAndSet(next);
        if (previous != next) {
            healthManager.setStatus(SERVICE, next);
        }
    }
}
~~~

The dependencyUnavailable() and dependencyRecovered() methods should be invoked from threshold-crossed circuit breaker/monitor events, not called directly for every per-request exception. The publisher initializes at NOT_SERVING; only after critical dependencies are checked and application initialization completes does the application call dependencyRecovered() to transition to SERVING.

When setStatus changes, clients using Watch can receive the new status. This lets load balancers or health-aware clients stop selecting a service that can no longer serve and continue watching for when it recovers.

## 8. Dependency fails but only part of the API is affected

Not every dependency is shared across all RPCs. Health can be maintained per service:

| Failing dependency | Affected service | How to publish |
| --- | --- | --- |
| Orders database | OrderService | OrderService = NOT_SERVING; other services keep their own status |
| Payment ledger | PaymentService | Only payment service transitions to NOT_SERVING |
| Optional recommendation service | Does not break core functionality | Keep SERVING, add degraded detail/metric |
| Shared identity provider critical for all RPCs | Multiple services or entire server | Update dependent services; change overall status only if the whole server cannot serve |

Pod HTTP readiness is an instance-scoped decision. If one service is not ready while other services remain useful, consider using service-level gRPC health and method-level routing instead of removing the whole pod from all traffic. Service-based routing capability depends on the load balancer; if infrastructure only supports pod-level readiness, choose an overall policy suited to the most critical API.

## 9. Health recovery and avoiding flapping

When a dependency starts working again, do not flip health back immediately after a single probe. A recovery cycle should include:

1. Waiting for a cooldown after the circuit opens.
2. Transitioning to HALF_OPEN and limiting the number of probes.
3. Requiring a number of consecutive successful probes or a success rate meeting a threshold.
4. Verifying the dependency can handle real load, not just a successful TCP connect.
5. Transitioning health back to SERVING and ramping traffic gradually if infrastructure supports it.
6. If errors recur, returning to NOT_SERVING according to the configured threshold.

Active health checks should use short timeouts, bounded frequency, and a dedicated executor. Do not let thousands of pods probe a recovering database simultaneously. You can apply jitter to probe schedules and cap total concurrency.

## 10. Startup and shutdown

At startup, the server may open a socket before all dependencies are ready. If health defaults to SERVING, the load balancer may send traffic too early. Initialize the status to NOT_SERVING, finish configuration, connect or warm up critical dependencies, and only then transition to SERVING.

At shutdown:

- Transition service health to NOT_SERVING before stopping traffic acceptance.
- Give the load balancer time to remove the instance from the pool if the deployment workflow requires it.
- Gracefully stop the gRPC server and let in-flight calls finish within bounds.
- Close monitors, schedulers, and dependency clients according to lifecycle.

Do not let the health service keep reporting SERVING while the server is intentionally shutting down.

## 11. Testing health changes on dependency failures

Tests should verify both status and routing behavior:

| Scenario | What to verify |
| --- | --- |
| Critical dependency healthy | Actuator readiness UP, gRPC service SERVING |
| Dependency exceeds error threshold | Readiness OUT_OF_SERVICE, service health NOT_SERVING |
| One service's dependency fails | Other services stay SERVING if independent |
| Optional dependency fails | Health still matches serving capability; details/metrics reflect degraded state |
| Single request with invalid input | Does not cause dependency health to go down |
| Circuit HALF_OPEN with a successful probe | Does not recover prematurely; waits for threshold |
| Dependency recovers steadily | Actuator and gRPC health return to UP/SERVING |
| Connected Watch client | Receives notification when status changes |
| Application shutdown | Health transitions to NOT_SERVING before server stops |

With Spring, test the readiness group endpoint using integration tests. With gRPC, use a health client to call Check and open Watch to verify status updates. Use fake dependencies or circuit breaker test events to drive failures rather than breaking a real database.

## 12. Observability and securing health information

Monitor:

- Circuit breaker state and transition timestamps.
- Consecutive error counts, error rates, and recovery probe counts.
- Readiness status and per-service gRPC SERVING/NOT_SERVING.
- Time from dependency failure until health is updated.
- Requests rejected or rerouted when the service is not ready.
- Dependency recovery duration and number of health flaps.

Health endpoints should provide sufficient operational information without exposing connection strings, internal hostnames, tokens, stack traces, or customer data. Restrict access to detailed endpoints; for external clients, return only the minimum necessary status.

## 13. Takeaways and self-check

When a dependency fails, update health based on **criticality, threshold-crossed failure state, and scope of affected RPCs**. Use Spring Actuator HealthIndicator for readiness, gRPC HealthStatusManager for Check/Watch, and a circuit breaker or monitor as the state source. Keep liveness independent of external dependencies, recover through controlled HALF_OPEN, and update to NOT_SERVING before shutdown.

Self-check:

1. Why should a dependency outage usually affect readiness rather than liveness?
2. When should only one gRPC service transition to NOT_SERVING instead of the entire server?
3. Why should you not invoke a blocking dependency directly each time the Actuator health endpoint is queried?
4. How are circuit breaker OPEN and HALF_OPEN states mapped to health?
5. Why are recovery thresholds and cooldowns needed to prevent health flapping?
6. What should you test to prove that a Watch client receives status changes?

Properly designed dynamic health enables Spring gRPC to stop accepting traffic where it truly cannot serve, keep independent services running, and bring instances back into the pool once dependencies recover steadily.
