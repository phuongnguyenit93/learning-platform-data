# gRPC Health Checking Protocol

**Chapter:** Health and reflection  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and server/client for unary or streaming RPCs. This lesson focuses on the standard gRPC Health Checking Protocol so load balancers, clients, and deployment platforms know whether a service is ready to receive requests.

## 1. What problem does the Health Checking Protocol solve?

A process may have already opened a port and started accepting connections while the service is not yet ready to handle business logic. For example:

- The application is still initializing connection pools or loading configuration.
- Required migrations or warm-up steps have not completed yet.
- An essential dependency has lost connectivity.
- The service is shutting down and needs to stop receiving new requests.

A TCP port check only confirms that a process is accepting connections. It does not confirm that the gRPC service is ready. The Health Checking Protocol provides a standard gRPC service for callers to query status by service name and receive status updates via streaming.

The health protocol helps external components decide whether to send traffic to an instance. It does not replace business testing, authorization, or detailed dependency monitoring.

## 2. Two standard RPCs: Check and Watch

The health service is defined in the `grpc.health.v1` package. The standard contract has two RPCs:

```proto
service Health {
  rpc Check(HealthCheckRequest) returns (HealthCheckResponse);
  rpc Watch(HealthCheckRequest)
      returns (stream HealthCheckResponse);
}

message HealthCheckRequest {
  string service = 1;
}

message HealthCheckResponse {
  enum ServingStatus {
    UNKNOWN = 0;
    SERVING = 1;
    NOT_SERVING = 2;
    SERVICE_UNKNOWN = 3;
  }
  ServingStatus status = 1;
}
```

Meaning:

- **Check** is a unary RPC: the client sends a service name and receives the current status once.
- **Watch** is a server-streaming RPC: the client sends a service name, the server sends the initial status, and then sends subsequent updates whenever the status changes.

Example service name:

```text
orders.v1.OrderService
```

This name is the protobuf package plus the service name. The empty string `""` represents the overall status of the server, not the name of a specific service.

### Meaning of ServingStatus

| Status | Meaning | Common behavior |
| --- | --- | --- |
| `UNKNOWN` | Status not yet determined | Status has not been evaluated or initialized |
| `SERVING` | Service is ready to serve | Can receive requests |
| `NOT_SERVING` | Service is currently not ready | Stop routing new traffic to the service |
| `SERVICE_UNKNOWN` | Server does not know the requested service in Watch | Client needs to handle an incorrect or unregistered service name |

For the `Check` RPC, an unrecognized service name typically results in the gRPC status `NOT_FOUND`. For `Watch`, the server can send `SERVICE_UNKNOWN` to indicate an unknown service name; the stream can still remain open to send status updates if the service is registered later.

Do not confuse the `NOT_SERVING` enum with the gRPC status code `NOT_FOUND`: one is the health status in the response, and the other is the error outcome of the RPC.

## 3. When are Check and Watch used?

**Check** is suitable for periodic probes or tools that only need to know the status at the moment of the call. Each call creates a separate RPC; calling it too frequently can create unnecessary load.

**Watch** is suitable for client-side health checking. The client opens a stream and monitors status continuously. Upon receiving `SERVING`, the client can mark the backend as eligible to receive requests; upon receiving `NOT_SERVING`, the client stops sending new requests to that backend.

Watch avoids continuous polling, but the client must handle reconnects, stream errors, and the initial status. If the stream is disconnected, the client should not assume the backend remains healthy forever; behavior when the health stream is lost depends on the health checker and load balancer policy.

## 4. Implementing the health service in gRPC Java

gRPC Java provides `HealthStatusManager` in the `grpc-services` artifact. This class implements the standard health service and provides an API to update status:

```java
import io.grpc.BindableService;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

public final class GrpcHealth {

    public static final String ORDER_SERVICE =
            "orders.v1.OrderService";

    private final HealthStatusManager manager =
            new HealthStatusManager();

    public GrpcHealth() {
        manager.setStatus("", ServingStatus.NOT_SERVING);
        manager.setStatus(
                ORDER_SERVICE,
                ServingStatus.NOT_SERVING);
    }

    public BindableService healthService() {
        return manager.getHealthService();
    }

    public void markReady() {
        manager.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
        manager.setStatus("", ServingStatus.SERVING);
    }

    public void markUnavailable() {
        manager.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);
        manager.setStatus("", ServingStatus.NOT_SERVING);
    }

    public void stopServing() {
        manager.enterTerminalState();
    }
}
```

The example initializes both the specific service status and the overall status to `NOT_SERVING`, and only transitions to `SERVING` once the application is ready. `HealthStatusManager` provides a `BindableService` to register with the gRPC server.

The required dependency is `io.grpc:grpc-services`; its version should be managed alongside the application's gRPC Java BOM/version to avoid version mismatches between generated health classes and runtime.

In Spring, register the manager as a singleton bean so service registration and lifecycle components update a single source of status:

```java
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GrpcHealthConfiguration {

    @Bean
    public HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }
}
```

### Registering the health service on the server

With a direct gRPC Java server builder:

```java
HealthStatusManager healthStatusManager =
        new HealthStatusManager();

NettyServerBuilder.forPort(port)
        .addService(orderGrpcService)
        .addService(healthStatusManager.getHealthService())
        .build()
        .start();
```

In Spring gRPC, the server is typically managed by the starter and auto-configuration. Register `healthStatusManager.getHealthService()` through the server service registration/customizer mechanism supported by your project's starter. Do not start a separate standalone server just to enable the health service, because probes might check the wrong port or wrong lifecycle.

If the starter already includes built-in health service integration, use the starter's proper extension point and maintain only a single source of status. Avoid registering two implementations with the same service name.

## 5. Managing status with the Spring lifecycle

Health state must reflect the application's actual ability to serve, not just the JVM state. One way to organize this is to create a Spring bean that manages `HealthStatusManager`, and update it at lifecycle milestones:

```java
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class GrpcReadinessLifecycle {

    private static final String ORDER_SERVICE =
            "orders.v1.OrderService";

    private final HealthStatusManager health;

    public GrpcReadinessLifecycle(HealthStatusManager health) {
        this.health = health;
        health.setStatus("", ServingStatus.NOT_SERVING);
        health.setStatus(ORDER_SERVICE, ServingStatus.NOT_SERVING);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void applicationReady() {
        // Call only after required readiness conditions have completed.
        health.setStatus(ORDER_SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    @EventListener(ContextClosedEvent.class)
    public void applicationStopping() {
        health.enterTerminalState();
    }
}
```

This is a minimal lifecycle example. In a real application, `ApplicationReadyEvent` is only a reference milestone; if essential dependencies are checked asynchronously or require separate warm-up steps, wait for the application's readiness gate before calling `markReady`. During shutdown, mark `NOT_SERVING` before the server stops accepting health RPCs and before the traffic draining phase. The exact lifecycle ordering must align with how the starter shuts down the server.

Do not leave the default status as `SERVING` right when the object is constructed. If the application has not yet connected to the database or loaded required configuration, probes could route traffic too early.

## 6. Per-service and server-wide health status

A server can provide multiple gRPC services. Health status should be managed by full service name:

```java
health.setStatus(
        "orders.v1.OrderService",
        ServingStatus.SERVING);

health.setStatus(
        "inventory.v1.InventoryService",
        ServingStatus.NOT_SERVING);
```

Clients watching `orders.v1.OrderService` can continue routing traffic to that service, while `inventory.v1.InventoryService` stops receiving new traffic. The empty string `""` status is the overall status; the application must define a clear aggregation rule.

For example, if both Order and Inventory are required for every request, the overall status is `SERVING` only when both are ready. If they are independent, one failing service does not necessarily have to stop the other from serving. Do not update the overall status arbitrarily; define dependency relationships and how load balancers/probes use service names.

When a dependency changes state, update the affected service:

```java
public void onInventoryDependencyUnavailable() {
    health.setStatus(
            "orders.v1.OrderService",
            ServingStatus.NOT_SERVING);
}

public void onInventoryDependencyRecovered() {
    health.setStatus(
            "orders.v1.OrderService",
            ServingStatus.SERVING);
}
```

Only mark a service `NOT_SERVING` if that dependency is genuinely required to process requests. If the service has a valid fallback or only a secondary feature is affected, you can keep the service serving and report detailed status through separate metrics/monitoring.

## 7. Client-side health checking

Some gRPC clients/load balancers support automatic health checking using `Watch`. Service config can specify the service name to check:

```json
{
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrderService"
  }
}
```

When the feature is enabled and supported by the client implementation, the client opens a health Watch stream. A backend is considered eligible to receive requests only after its health status reports `SERVING`. If the status transitions to `NOT_SERVING`, the client stops routing new requests to that backend according to the load balancer policy.

Not all gRPC clients, languages, or load balancers enable client-side health checking by default. Verify runtime support, whether service config is applied, and whether the health service is exposed on the same endpoint that the client checks.

For custom clients, you can use `HealthGrpc.HealthStub` to call `watch()` and maintain state from the stream. The client needs to handle reconnect/backoff, cancellation when the channel closes, and avoid routing traffic before receiving a reliable serving status.

## 8. Combining with readiness and liveness probes

The Health Checking Protocol is a protocol for reporting the serving status of a gRPC service. It is commonly used to implement readiness probes, but it is not synonymous with all types of health probes:

| Probe | Question | On failure |
| --- | --- | --- |
| Liveness | Is the process still alive according to platform criteria? | The platform may restart the container/process |
| Readiness | Can the instance receive new requests? | The platform/load balancer stops routing traffic |
| Startup | Has the application finished its startup phase? | The platform delays liveness/readiness according to configuration |
| gRPC Health Check | Is the queried service name currently `SERVING`? | The client/probe decides whether to route or mark unhealthy |

Do not mark liveness as failed solely because the database temporarily lost connectivity. If readiness transitions to `NOT_SERVING`, the instance can be removed from traffic to prevent cascading failures; repeated restarts do not necessarily fix a dependency outage.

Some platforms have native gRPC probes that call unary `Check`; other systems use an HTTP health endpoint or client-side `Watch`. Configure the correct service name and port. Do not assume the platform in use supports every probe type.

## 9. Shutdown and graceful draining

When the application shuts down:

1. Transition service health to `NOT_SERVING` or call `enterTerminalState()`.
2. Give load balancers/client-side health checkers time to receive the new status.
3. Stop accepting new requests via the server's graceful shutdown mechanism.
4. Wait for in-flight RPCs to complete within a timeout.
5. Close channels, executors, and dependencies.

If you shut down the server before updating the health state, probes may only see reset connections instead of an intentional `NOT_SERVING` status. If you mark `NOT_SERVING` too late, the load balancer may still send requests while dependencies have already stopped.

Health Watch streams must also be terminated properly with the server lifecycle. Do not allow a background health publisher to continue updating state after the Spring context has closed.

## 10. Security and limiting health information

The health endpoint is usually called by internal probes, but it is still an RPC endpoint that could be accessed if exposed on a wider network. You should:

- Restrict network access or apply authentication/authorization suitable for the probing platform.
- Expose only the service name and necessary serving status.
- Do not include hostnames, connection strings, tokens, SQL, or exception messages in health responses.
- Do not use health responses as a replacement for diagnostic APIs or metrics.
- Ensure the health service cannot be blocked by the very dependency experiencing an outage; if a probe has to query the database on every call, the probe itself may time out when the database is overloaded.

Health status should be updated from a controlled readiness state/health evaluator. Avoid running a suite of synchronous dependency checks on every `Check` call; doing so can amplify incidents when probes are called frequently.

## 11. Testing the Health Checking Protocol

You should test both the current status and the update stream:

| Case | Expectation |
| --- | --- |
| Service started but not yet ready | `Check` returns `NOT_SERVING` |
| Service is ready | `Check` returns `SERVING` |
| Non-existent service name via Check | RPC returns `NOT_FOUND` |
| Unknown service name via Watch | Stream reports `SERVICE_UNKNOWN` per protocol |
| Status changes from serving to not serving | Watch client receives the new update |
| One service stops serving, another keeps running | Each service status reflects state independently |
| Shutdown begins | Status transitions to not serving before server drains |
| Client cancels Watch | Server releases stream/call state |

Example Check test using an in-process server:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.health.v1.HealthCheckRequest;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.health.v1.HealthGrpc;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcHealthCheckTest {

    @Test
    void reportsServiceStatus() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        HealthStatusManager manager = new HealthStatusManager();
        manager.setStatus(
                "orders.v1.OrderService",
                ServingStatus.SERVING);

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(manager.getHealthService())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder
                .forName(serverName)
                .directExecutor()
                .build();

        try {
            var response = HealthGrpc.newBlockingStub(channel)
                    .check(HealthCheckRequest.newBuilder()
                            .setService("orders.v1.OrderService")
                            .build());

            assertEquals(ServingStatus.SERVING, response.getStatus());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

This test verifies that the health service is registered and that the client can call the generated health stub over a gRPC channel. You should add tests for `NOT_SERVING`, unknown services, and Watch streams. For Watch, use a latch/future with a timeout to wait for status updates; do not use `Thread.sleep()` as a synchronization mechanism.

## 12. Self-practice

1. Why does an open TCP port not prove that a gRPC service is ready?
2. Distinguish between unary `Check` and server-streaming `Watch`; when does client-side health checking need Watch?
3. A server has two independent services, and one loses a dependency. Determine the status of each service and the overall status.
4. Why should you not run a synchronous database query on every health Check?
5. Design the sequence of updating `NOT_SERVING` and graceful shutdown so the load balancer stops sending requests before the server closes.

**Remember:** The standard gRPC Health Checking Protocol provides `Check` for one-off status queries and `Watch` for monitoring changes. Use full protobuf service names, manage `SERVING`/`NOT_SERVING` based on actual readiness, register the health service on the right Spring gRPC server, and update status before shutting down. Health responses must be fast, safe, and not disclose internal details.
