# Service Health Status

## 1. Health status indicates whether a service can accept RPCs

In **SPRING_GRPC**, a service is defined using Protocol Buffers, generates Java code, and is registered on a gRPC server managed by the Spring application. When a service runs in a multi-instance environment, clients, load balancers, or deployment platforms need to know which instances can actually serve requests.

**Health status** is an application-layer signal indicating whether a specific service is ready to serve. It helps distinguish between:

- The process is still running.
- The TCP/HTTP/2 connection has been established.
- The business service has finished initializing and can process RPCs.

These three conditions are not synonymous. A gRPC server may accept connections and have subchannels in the `READY` state, yet `OrdersService` still cannot process requests because a required database is not connected or initialization has not finished.

## 2. gRPC Health Checking Protocol

gRPC defines the standard health service `grpc.health.v1.Health` with two RPCs:

- `Check`: queries the current status of a service.
- `Watch`: subscribes to receive the initial status and subsequent status changes.

The request carries the name of the service to check. This name is typically the fully qualified name in protobuf, consisting of package and service, for example `orders.v1.OrdersService`; it is not a Java class name or Spring bean name.

Health responses use the following statuses:

| Status | Meaning |
|---|---|
| `UNKNOWN` | Status has not yet been determined |
| `SERVING` | Service can serve requests |
| `NOT_SERVING` | Service should not currently accept new RPCs |
| `SERVICE_UNKNOWN` | The health service does not know the requested service; this status is used in `Watch` streams |

`Check` is suited for probes that query status at a single point in time. `Watch` is suited for clients that want to monitor changes continuously without constant polling. If the service name is not registered, `Check` can return the `NOT_FOUND` status; `Watch` can emit `SERVICE_UNKNOWN` and continue watching to receive updates if the service appears later.

## 3. Status is managed per service name

A gRPC server can provide multiple services. Health status should reflect each service's serving capability independently:

~~~text
gRPC server
  ├── orders.v1.OrdersService        SERVING
  ├── inventory.v1.InventoryService  NOT_SERVING
  └── payments.v1.PaymentsService    SERVING
~~~

Thus, a dependency failure affecting only `InventoryService` does not necessarily require marking `OrdersService` and `PaymentsService` as `NOT_SERVING`.

The health protocol also allows an empty service name (`""`) to represent the overall status of the server. Overall status is useful for server-level probes, but it does not replace per-service status when services have different dependencies and serving capabilities.

Do not use the Java package name instead of the protobuf service name. If protobuf declares:

~~~proto
package orders.v1;

service OrdersService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderReply);
}
~~~

then the health key is `orders.v1.OrdersService`.

## 4. Exposing the health service with gRPC Java

The `grpc-services` artifact provides `HealthStatusManager`, an implementation that manages statuses and supplies a health service to register on the server:

~~~java
import io.grpc.Server;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;

public final class OrdersGrpcServer {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health =
            new HealthStatusManager();

    private Server server;

    public void start(OrdersServiceImpl ordersService)
            throws java.io.IOException {
        // The server is not ready until dependencies are verified.
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);

        server = NettyServerBuilder.forPort(9090)
                .addService(ordersService)
                .addService(health.getHealthService())
                .build()
                .start();
    }

    public void markReady() {
        health.setStatus(SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    public void markNotReady() {
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
        health.setStatus("", ServingStatus.NOT_SERVING);
    }
}
~~~

`HealthStatusManager` must be shared between the code that updates status and the registered health service. If two different managers are created, the service may continue returning the stale status even though the readiness component updated the other manager.

The snippet uses the Netty shaded transport and illustrates direct registration in gRPC Java. The project needs a `grpc-services` dependency compatible with the rest of the gRPC artifacts.

## 5. Managing health status with the Spring lifecycle

In a Spring application, manage a single `HealthStatusManager` as a bean and inject that same instance into the component tracking lifecycle events:

~~~java
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcHealthConfiguration {

    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }
}
~~~

The lifecycle component can set the initial status, transition to `SERVING` once the application is ready, and switch back to `NOT_SERVING` during shutdown:

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersHealthLifecycle {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health;

    public OrdersHealthLifecycle(HealthStatusManager health) {
        this.health = health;
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        // Use ApplicationReadyEvent only after required dependencies
        // have been checked and the server has registered the health service.
        health.setStatus(SERVICE, ServingStatus.SERVING);
    }

    @EventListener(ContextClosedEvent.class)
    public void onContextClosing() {
        health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    }
}
~~~

The health service must be registered with the gRPC server via the service registration mechanism of the Spring gRPC starter in use. With a starter that manages the server automatically, include `health.getHealthService()` in the list of services the server publishes; do not spin up a second Netty server just to expose health.

`ApplicationReadyEvent` is a convenient lifecycle milestone, but it does not by itself prove that all business dependencies are healthy. If a service has a dedicated readiness step, call `markReady` after that step succeeds and update the status again if a required dependency loses serving capability.

## 6. Health status must reflect business serving capability

A service should report `SERVING` only when it can handle the RPCs it commits to. Identify which dependencies are truly mandatory:

| Dependency | Example decision |
|---|---|
| Primary database required by all RPCs | Losing connectivity can transition the service to `NOT_SERVING` |
| Message broker used only for one specific RPC | May affect only the service/RPC group depending on the broker |
| Cache that can fall back to the database | Does not necessarily stop the service from serving |
| Non-essential analytics service | Failure may only disable a secondary feature |

Do not mark the entire server `NOT_SERVING` just because an optional dependency has an outage. Conversely, do not stay `SERVING` when a mandatory dependency is down and requests definitely cannot succeed.

Health checks should not execute heavy queries against every dependency on each `Check` call. Instead, update status from a readiness coordinator or dependency monitor with timeouts, short result caching, and rate limiting. `Watch` should receive changes from the managed state rather than triggering a fresh suite of checks for every watcher.

## 7. Distinguishing health, readiness, and liveness

These three signals are commonly used together but serve different purposes:

| Signal | Question | Typical action |
|---|---|---|
| Liveness | Is the process still alive or stuck to the point of needing a restart? | Platform restarts the container/process |
| Readiness | Should the instance receive new traffic? | Remove the instance from endpoints/traffic pool |
| gRPC health status | Can the specific gRPC service currently serve? | Probe, client health checking, or load balancer excludes the service from selection |

An application can be alive (good `liveness`) while not yet ready (poor `readiness`) because it is warming up. If liveness depends directly on the database, an intermittent database can cause continuous container restarts even though the process itself is healthy.

With Kubernetes, a gRPC probe can check the health service on the specified port:

~~~yaml
readinessProbe:
  grpc:
    port: 9090
    service: orders.v1.OrdersService
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

This probe is meaningful only when the health service is registered and status is updated properly. Use readiness to stop sending new traffic to an unready service. Liveness should reflect process health; do not configure it so that an optional dependency failure triggers a restart loop.

## 8. Client-side health checking and load balancing

A gRPC client can use health checking to monitor backends via the `Watch` RPC. Service config can specify the service name to check:

~~~json
{
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrdersService"
  }
}
~~~

When the runtime and load balancing policy support client-side health checking, a subchannel is considered eligible to receive new RPCs only when the health signal meets the requirement, typically `SERVING`. When a service transitions to `NOT_SERVING`, the picker can stop selecting that backend for new RPCs; when it returns to `SERVING`, the backend can be put back into selection.

Merely exposing the health service on the server does not automatically enable client-side health checking. The client must receive the service config and the runtime/provider must support this feature. If the system uses a proxy or service mesh, the health policy may be enforced by the proxy rather than the gRPC client.

A health status change does not automatically migrate in-flight RPCs to another instance. An in-progress unary RPC may still complete or fail on the old backend; an open server stream does not automatically transfer its remainder to a new backend. The client needs to retry when the RPC is eligible or reconnect/resume using a cursor if the stream must continue.

## 9. Graceful shutdown: transition to NOT_SERVING first

When deploying a new version or stopping an instance, updating health in the right order reduces new RPCs arriving at a server about to stop:

1. Set the service's health status to `NOT_SERVING`.
2. Mark readiness false or deregister the instance from discovery.
3. Wait within a bounded window for health updates and endpoint changes to propagate to clients/load balancers.
4. Drain in-flight RPCs during the grace period.
5. Close the server and remaining dependencies.

Example of the status update step:

~~~java
health.setStatus(
        "orders.v1.OrdersService",
        ServingStatus.NOT_SERVING);
~~~

Do not stop the server immediately after updating the status if clients need time to receive the `Watch` update or resolvers need time to refresh. For long-lived server streams, define a stream termination policy and client reconnect/resume mechanism. `NOT_SERVING` only prevents new RPC selection by health-aware components; it does not automatically cancel or move already-started RPCs.

## 10. Health status is not an authorization mechanism

The health endpoint is commonly called by probes, load balancers, or monitoring systems. It should return the minimum required signal without disclosing:

- Connection strings or credentials.
- Internal hostnames and sensitive network topology.
- Stack traces or detailed exceptions.
- Customer data or business payloads.

Restrict where the health service can be accessed using network policies, internal listeners, or authentication mechanisms suited to the infrastructure. If platform probes cannot send credentials, design a dedicated endpoint/probe inside a controlled network zone; do not disable authentication for all business APIs for convenience.

Health status also does not prove that a caller has permission to invoke `GetOrder` or `CreateOrder`. Authentication and authorization must still be enforced on business RPCs.

## 11. Testing health status

Testing must verify both the published status and its effects:

| Scenario | What to verify |
|---|---|
| Server just started | Service is `NOT_SERVING` or unknown until readiness completes |
| Mandatory dependencies ready | Status transitions to `SERVING` |
| Mandatory dependency disconnected | Status transitions to `NOT_SERVING` per policy |
| Optional dependency fails | Service stays `SERVING` if it still fulfills its contract |
| `Check` with valid service name | Returns current status |
| `Watch` with valid service name | Receives initial status and subsequent changes |
| Non-existent service name | Handles `NOT_FOUND`/`SERVICE_UNKNOWN` according to RPC and implementation |
| Server provides multiple services | Per-service status is independent; `""` status follows overall policy |
| Shutdown | Status becomes `NOT_SERVING` before server drains |
| Client health checking | A `NOT_SERVING` backend receives no new RPCs after the update is applied |
| Watch disconnected | Client/runtime recovers per policy, without treating silence as proof of health |

Unit tests for `HealthStatusManager` verify status updates. Integration tests over a channel or with actual probes prove that the health service is registered, the service name is right, and clients/load balancers actually use the status.

## 12. Observability and diagnostics

Monitor:

- Number of `SERVING` and `NOT_SERVING` services per instance.
- Timestamps and reasons for status transitions.
- Time from readiness change until probes/clients receive the update.
- Counts of health `Check` and `Watch` calls, watcher errors, and open watchers.
- Number of `READY` subchannels compared to `SERVING` backends.
- New RPCs arriving at a backend after the backend transitioned to `NOT_SERVING`.
- Drain duration and number of open RPCs/streams during shutdown.

If probes report healthy while business RPCs fail, check whether the health policy accurately reflects mandatory dependencies. If the server is already `NOT_SERVING` yet still receives new RPCs, check whether probes are querying the right service name, whether clients/proxies have health checking enabled, and whether endpoint discovery has updated.

## 13. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Checking only the TCP port | Server accepts connections before the service is ready | Expose the gRPC health service |
| Using the wrong service name | Probes/clients cannot find the status to check | Use the full name `package.Service` |
| Registering the health service without updating status | Health responses do not reflect true lifecycle | Manage `HealthStatusManager` with readiness |
| Creating multiple independent `HealthStatusManager` instances | Health service returns a different status from the updater component | Use one shared manager |
| Marking `SERVING` as soon as the server binds the port | Traffic arrives before dependencies are ready | Transition to `SERVING` only after readiness |
| Tying liveness to an optional dependency | Container restarts repeatedly when the dependency flaps | Separate liveness from readiness/business health |
| Stopping the server immediately after `NOT_SERVING` | Clients have not received the update; in-flight RPCs are cut off | Wait for propagation and graceful drain |
| Assuming a health change migrates streams | Existing streams remain bound to the original backend | Reconnect/resume using a cursor |
| Returning dependency details in health responses | Leaks internal information | Return only the minimal status |

**Remember:** Service health status is an application signal keyed by gRPC service name, published via `grpc.health.v1.Health` using `Check` and `Watch`. Use `HealthStatusManager` to manage statuses, share the same instance between the health service and lifecycle components, report `SERVING` only after readiness, and transition to `NOT_SERVING` before draining. Distinguish liveness, readiness, and connectivity; health status helps steer new RPCs but does not automatically recover in-flight RPCs or streams.
