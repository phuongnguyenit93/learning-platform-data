# Health-aware load balancing

## 1. Selecting only backends that are actually ready to serve

In **SPRING_GRPC**, a gRPC service can run on multiple instances and the client uses `ManagedChannel`, a name resolver, and a load balancing policy to pick a backend for each new RPC. However, a reachable address does not guarantee the application behind it is healthy. **Health-aware load balancing** incorporates application health signals into backend selection so the client avoids sending new RPCs to an instance that cannot serve.

For example, the `orders` service has three instances:

~~~text
Resolver returns:
  A: 10.60.0.11:9090
  B: 10.60.0.12:9090
  C: 10.60.0.13:9090

Transport state:
  A: READY
  B: READY
  C: READY

Application state:
  A: SERVING
  B: NOT_SERVING (database is not ready)
  C: SERVING

Health-aware picker:
  Choose A or C for new RPCs
  Do not choose B until B returns to SERVING
~~~

If selection relied solely on connection state, A, B, and C would all look ready to accept RPCs. Health-aware load balancing distinguishes **connectable** from **able to serve**.

## 2. READY connectivity is not application health

A gRPC channel tracks subchannel connectivity states such as `IDLE`, `CONNECTING`, `READY`, and `TRANSIENT_FAILURE`. The `READY` state indicates the transport has established a connection to send RPCs; it does not prove the backend's database, message broker, or business dependencies are working properly.

An instance can:

- Open a TCP port and complete a TLS handshake.
- Accept an HTTP/2 connection.
- Answer a health or business RPC with an error because a required dependency is broken.

Therefore, separate these signals:

| Signal | Question it answers | Where it is commonly used |
|---|---|---|
| Connectivity state | Can RPCs be sent over this connection? | gRPC channel/subchannel |
| Liveness | Is the process alive or does it need restarting? | Container orchestrator |
| Readiness | Should this instance receive new traffic? | Kubernetes/service discovery |
| gRPC application health | Is this specific service able to serve? | gRPC health checking |
| Outlier/ejection signal | Is this backend failing abnormally compared to peers? | Service mesh/control plane |

Liveness and readiness are not synonymous either. An application can be alive yet unready while initializing a schema or loading data. If a liveness probe treats every dependency failure as a process failure, the orchestrator may restart containers repeatedly when waiting for the dependency to recover was all that was needed.

## 3. gRPC Health Checking Protocol

gRPC defines the standard service `grpc.health.v1.Health` in package `grpc.health.v1`. The service provides two primary RPCs:

- `Check`: queries the current health status of a service.
- `Watch`: subscribes to status changes over time.

Health responses use statuses such as:

| Status | Meaning |
|---|---|
| `SERVING` | The service can currently serve requests |
| `NOT_SERVING` | The service should not receive new RPCs right now |
| `SERVICE_UNKNOWN` | The health service has no information for the requested service |
| `UNKNOWN` | Status undetermined per health contract |

Client-side health checking typically uses `Watch` to monitor backend status rather than sending a new `Check` before every business RPC. When a service's status is no longer `SERVING`, a health-aware load balancer can stop picking that backend for new RPCs. Exact behavior depends on the gRPC runtime, load balancing policy, and service config supporting health checking.

Service names must match consistently. For a declared service:

~~~proto
package orders.v1;

service OrdersService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderReply);
}
~~~

The full name used in health checks is `orders.v1.OrdersService`, not the Java class name or Spring bean name.

## 4. Exposing the health service in gRPC Java

gRPC Java provides `HealthStatusManager` in the `grpc-services` artifact. The server registers the health service alongside business services and updates status across its lifecycle:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

public final class OrdersGrpcServer {
    private static final String SERVICE =
            "orders.v1.OrdersService";

    private final HealthStatusManager health =
            new HealthStatusManager();

    private Server server;

    public void start(OrdersServiceImpl ordersService)
            throws java.io.IOException {
        server = NettyServerBuilder.forPort(9090)
                .addService(ordersService)
                .addService(health.getHealthService())
                .build()
                .start();

        // Transition to SERVING only after required dependencies
        // and business initialization are ready.
        health.setStatus(SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }
}
~~~

This snippet illustrates a server using the shaded Netty transport; the project must include the `grpc-services` dependency and matching gRPC artifact versions. In Spring, you can manage `HealthStatusManager` as a bean and register `getHealthService()` using the active starter's service registration mechanism.

`setStatus(SERVICE, ...)` updates health for a specific service. An empty service name string is commonly used for the overall server status. If a server hosts multiple gRPC services, do not mark them all `SERVING` just because the process is alive: each service may depend on different components.

Do not mark `SERVING` the instant the socket opens. Wait until dependencies genuinely required for requests, schema/migrations, consumers, or essential caches have completed initialization.

## 5. Configuring client health checking

A gRPC service config can combine a load balancing policy with `healthCheckConfig`. Example:

~~~json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ],
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrdersService"
  }
}
~~~

Meaning:

- `round_robin` distributes new RPCs across eligible subchannels.
- `healthCheckConfig.serviceName` specifies the service the client should monitor via gRPC health checking.
- A backend should only be considered healthy for that service when the health signal meets client-side health checking criteria, typically `SERVING`.

The service config can be supplied by the resolver or set as the channel's default configuration if supported by the runtime. Example default configuration in gRPC Java:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

java.util.Map<String, Object> serviceConfig = java.util.Map.of(
        "loadBalancingConfig", java.util.List.of(
                java.util.Map.of("round_robin", java.util.Map.of())),
        "healthCheckConfig",
                java.util.Map.of("serviceName", "orders.v1.OrdersService")
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultServiceConfig(serviceConfig)
        .useTransportSecurity()
        .build();
~~~

This shows how the configuration is expressed at the gRPC Java layer; actual health checking and policy capabilities must be verified against the gRPC Java version, providers, and resolver in use. Not every starter or custom load balancer enables client-side health checking in the same way. If the runtime does not support it, use health-aware discovery/control plane to remove unhealthy endpoints from the list, or use a policy with built-in health signal integration.

Do not confuse configuring client-side health checking with merely registering a health service on the server. The server must expose and update status; the client must be configured to watch and use that status during backend selection.

## 6. Defining health around business serving capability

Health checks are useful when status accurately reflects request-handling capability. If `GetOrder` requires access to the primary database, the backend should not report `SERVING` during a prolonged database outage. However, if an optional dependency only supports a secondary feature, marking the entire service `NOT_SERVING` may exclude a backend still capable of handling most RPCs.

Therefore:

1. Identify which dependencies are mandatory for each gRPC service.
2. Define conditions for transitioning between `SERVING` and `NOT_SERVING`.
3. Distinguish brief transient glitches from sustained failures.
4. Update health from existing signals (connection state, circuit breaker, dependency monitor) rather than running heavy queries on every health check.
5. If methods have differing requirements, consider per-service or service-group health; a single global status can be too coarse.

Health status is a coarse-grained signal, not a replacement for every business check. A backend can be `SERVING` while a specific request still legitimately returns `NOT_FOUND` or `FAILED_PRECONDITION`.

## 7. When no healthy backends remain

Health-aware load balancing can exclude `NOT_SERVING` backends from new RPC selection. If every backend is unhealthy or health state is not yet confirmed, the client has nowhere safe to send RPCs.

Observed behavior depends on policy and configuration:

- RPCs may fail with a status such as `UNAVAILABLE`.
- RPCs using `withWaitForReady()` may wait for a backend to become healthy again while the deadline remains valid.
- When a backend transitions back to `SERVING`, the health watcher can update status and the eligible backend is restored to the picker.

Example:

~~~java
GetOrderReply reply = stub
        .withWaitForReady()
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

`waitForReady` does not heal a backend and does not wait indefinitely. The deadline remains the hard upper bound. For operations that lose meaning after a brief wait, fail fast instead of queuing for too long.

Do not automatically retry every status continuously when no healthy backend exists. Classify status codes, apply backoff/jitter where appropriate, and bound total retry duration to avoid overloading a recovering cluster.

## 8. Health changes do not migrate in-flight RPCs

Health-aware load balancing primarily affects **new RPCs**. When a backend switches from `SERVING` to `NOT_SERVING`, new calls can be routed to other backends once the health update takes effect. RPCs that have already started typically stay attached to their original backend.

~~~text
Before draining:
  RPC #1 -> A (in progress)
  RPC #2 -> A
  RPC #3 -> B

A transitions to NOT_SERVING:
  New RPCs -> B or C
  RPC #1 is still running on A

A graceful shutdown:
  wait for RPC #1 to complete within grace period
  then shut down server
~~~

For long-lived server streaming, draining may take longer than the allowed instance stop window. Define how streams terminate, send an appropriate status, and let clients reconnect/resume with a cursor if data must be continuous. Health status does not replay responses or migrate the remainder of a stream to another instance.

## 9. Graceful shutdown: report NOT_SERVING before stopping

During planned deployments or shutdowns, sequencing operations reduces new RPCs landing on an instance about to stop:

1. Set service health to `NOT_SERVING`.
2. Wait a bounded time for the health signal to propagate to clients/load balancers or service discovery.
3. Stop accepting new work at the application layer if admission/drain controls exist.
4. Invoke graceful server shutdown so in-flight RPCs have time to finish.
5. After the grace period expires, cancel remaining RPCs and close dependencies.

Example:

~~~java
public void stop() throws InterruptedException {
    health.setStatus(SERVICE, ServingStatus.NOT_SERVING);
    health.setStatus("", ServingStatus.NOT_SERVING);

    if (server != null) {
        server.shutdown();
        if (!server.awaitTermination(20, java.util.concurrent.TimeUnit.SECONDS)) {
            server.shutdownNow();
        }
    }
}
~~~

This is a minimal lifecycle example. In Spring, place corresponding logic in the appropriate lifecycle hook and ensure wait times do not exceed the platform's termination grace period. If health checkers or resolvers have propagation lag, changing status and shutting down immediately may not give clients enough time to stop picking the instance.

## 10. Avoiding health flapping and health-check overload

If health oscillates rapidly between `SERVING` and `NOT_SERVING`, backends can repeatedly enter and leave the picker. This causes unstable load distribution and can trigger large reconnect storms.

Countermeasures:

- Use consecutive-failure thresholds or stabilization intervals before transitioning state.
- Apply hysteresis: the threshold to take a backend out of service can differ from the threshold to restore it.
- Do not execute heavy database queries every time a client calls `Check` or opens a `Watch`.
- Update health from periodic monitors or dependency events, using timeouts and short-lived status caching.
- Bound health watcher counts and ensure `Watch` streams are served efficiently.
- Mark `SERVING` only after dependencies have stabilized.

Health endpoints should return the minimum information needed for serving decisions. Never include internal hostnames, credentials, stack traces, or sensitive dependency details in public health responses.

## 11. Distinguishing gRPC health, Kubernetes readiness, and outlier detection

These layers complement one another:

| Mechanism | Who observes it | Effect |
|---|---|---|
| gRPC health `Watch` | gRPC clients with client-side health checking enabled | Can exclude the backend from new RPC selection on the channel |
| Kubernetes readiness probe | Kubelet/control plane | Pod is excluded from Service traffic endpoints when unready |
| Liveness probe | Kubelet | Can restart the container if the process is no longer alive |
| Outlier detection | Service mesh/proxy/control plane | Temporarily ejects a backend with abnormal error rate/latency |

Multiple mechanisms can run together, provided contradictions are avoided. For example, Kubernetes readiness may report healthy while gRPC health reports `NOT_SERVING`; direct clients may still see the pod, yet the health checker will exclude it. Conversely, once Kubernetes removes an endpoint, clients can no longer resolve the pod even if its internal health status remains `SERVING`.

Outlier detection also differs from active health checks. It can eject a backend based on error statistics from live traffic, even while the backend still reports `SERVING`. Health checks report the state published by the service; outlier detection infers abnormal behavior by observing traffic.

## 12. Testing health-aware load balancing

To verify behavior, you need multiple individually identifiable backends with controllable health statuses:

| Scenario | Expected outcome to verify |
|---|---|
| A and B are both `SERVING` | New RPCs can be distributed across both per policy |
| B transitions to `NOT_SERVING` | New RPCs stop selecting B after the health update is applied |
| B returns to `SERVING` | B can be restored to the picker |
| Health service does not recognize service name | Client handles unknown status per configuration, without assuming healthy by default |
| No backend is `SERVING` | RPCs fail or wait according to `waitForReady` and deadline |
| Business port `READY` but mandatory database is down | Health reflects `NOT_SERVING` per business rules |
| Planned shutdown | `NOT_SERVING` is published prior to graceful shutdown |
| Stream active while backend drains | Active RPC has a deterministic outcome; client resumes if needed |
| Health watcher interrupted | Client/runtime recovers per supported behavior; silence is not treated as proof of health |
| Many clients open health watches | Health checking does not overload the server |

Integration tests should verify that the service config is genuinely applied and that the client runtime supports health checking. A unit test merely calling `HealthStatusManager.setStatus` does not prove the picker excluded the backend. Test through a channel across multiple instances and observe which backend receives RPCs.

## 13. Metrics and diagnostics

Monitor both health signals and actual selection:

- Count of `SERVING`/`NOT_SERVING` backends per service.
- Timestamps and reasons for health status transitions.
- `READY` subchannel count and health-eligible backend count.
- Number of RPCs selected per instance.
- Rates of `UNAVAILABLE`, `DEADLINE_EXCEEDED`, and health watch errors.
- Time from a backend turning `NOT_SERVING` until it stops receiving new RPCs.
- Drain duration and count of open RPCs at shutdown.
- Count of backend flapping events or outlier ejections.

If a `NOT_SERVING` backend still receives new RPCs, check whether client-side health checking is enabled, whether the service name matches completely, whether the health service is registered, whether the service config reached the channel, and whether the load balancing provider supports that feature.

## 14. Common design mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Treating subchannel `READY` as service healthy | RPCs hit a backend with broken dependencies | Use application-layer health signals |
| Exposing health service without client monitoring | Health status has no effect on the picker | Configure client-side health checking or corresponding discovery |
| Health config uses wrong service name | Client watches the wrong service or misses expected status | Use full `package.Service` name |
| Marking `SERVING` immediately when port opens | Backend receives traffic before dependencies are ready | Transition to `SERVING` after initialization |
| Marking every service `NOT_SERVING` when an optional dependency fails | Overly aggressive backend exclusion | Define health by mandatory dependencies per service |
| Health checks running heavy DB queries continuously | Health checking adds load to a struggling dependency | Update status from a monitor with timeouts/cache |
| Stopping server immediately after setting `NOT_SERVING` | Clients have not received health update yet; in-flight RPCs get cut off | Wait for propagation and drain gracefully |
| Assuming health changes migrate active streams | Active RPC remains attached to old backend | Reconnect/resume with cursor at application layer |

**Key takeaway:** Health-aware load balancing combines endpoint lists, connection states, and service health to select backends for new RPCs. The gRPC Health Checking Protocol provides `Check`/`Watch`; servers must publish meaningful status and clients/runtimes must actually apply health signals in the picker. `READY` reflects only transport readiness, whereas `SERVING` reflects application serving capability. When draining, report `NOT_SERVING` first, allow propagation, and shut down gracefully; interrupted in-flight RPCs or streams require separate retry or resume handling.
