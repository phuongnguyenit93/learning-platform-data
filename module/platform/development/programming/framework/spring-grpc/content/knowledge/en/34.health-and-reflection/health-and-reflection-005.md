# Health Checks Through a Load Balancer

Health checks help a load balancer select instances capable of serving RPCs at the current moment. With **Spring gRPC**, the server must publish its health status using the standard gRPC protocol; client-side load balancers, proxies, or orchestration infrastructure must be configured to read that status and stop sending requests to backends that can no longer serve.

An open TCP port does not mean the service is ready. The process may be running while the database is not yet connected, the service is still starting up, or a group of RPCs has been disabled due to a failing dependency. Therefore, you must distinguish TCP probes, the gRPC Health Checking Protocol, and deployment platform readiness probes.

## 1. Three common types of health checks

| Mechanism | What is checked | Limitation |
| --- | --- | --- |
| TCP connect probe | Whether a connection can be opened to the port | Does not verify HTTP/2, gRPC services, or dependencies |
| gRPC Health Check | The SERVING/NOT_SERVING status of a service | Requires the server to implement the health protocol and the LB to support gRPC health |
| Platform readiness probe | Whether the instance should receive new traffic | Usually a pod/instance-level decision that may not distinguish individual gRPC services |

TCP probes are useful for detecting processes not listening on a port, but can mark a server healthy even when the service is not ready. Conversely, a server hosting multiple independent services may only need to remove one service from the pool; gRPC health lets you publish status by service name.

Liveness answers whether the process needs to be restarted. Readiness answers whether the instance should receive traffic. Load balancer health checks typically serve readiness; do not treat external dependency failures as liveness failures if restarting the process cannot restore the dependency.

## 2. The gRPC Health Checking protocol

gRPC defines a standard service with the full name grpc.health.v1.Health, featuring two RPCs:

- **Check**: the client sends a service name and receives the current status.
- **Watch**: the client opens a server-streaming RPC to receive the initial status and subsequent changes.

Primary serving statuses:

| Status | Meaning to the load balancer |
| --- | --- |
| SERVING | Backend can accept RPCs for the queried service |
| NOT_SERVING | Backend should not receive new RPCs for that service |
| UNKNOWN | Serving capability cannot be determined yet |

Client-side gRPC load balancers typically use Watch to monitor each backend over time. When a backend transitions to NOT_SERVING, the LB can stop selecting that backend for the corresponding service. When status returns to SERVING, the backend can be put back into the pool according to the LB policy.

The service name must exactly match the full name of the Protobuf service, such as acme.orders.v1.OrderService. The empty string represents overall server health. If only OrderService is affected, update that service's status rather than marking all services NOT_SERVING.

## 3. Registering HealthStatusManager on a Spring gRPC server

gRPC Java provides HealthStatusManager in the grpc-services artifact. It implements the standard health service and manages per-service status:

~~~java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;

HealthStatusManager healthManager = new HealthStatusManager();
String orderServiceName = "acme.orders.v1.OrderService";

healthManager.setStatus(
    orderServiceName,
    ServingStatus.NOT_SERVING);

Server server = ServerBuilder.forPort(9090)
    .addService(orderService)
    .addService(healthManager.getHealthService())
    .build()
    .start();

// After critical dependencies and application initialization are ready:
healthManager.setStatus(
    orderServiceName,
    ServingStatus.SERVING);
~~~

This example illustrates a gRPC Java server. In a Spring application, manage HealthStatusManager as a bean and register the health service via the service registration mechanism or ServerBuilder customizer of the starter in use. Do not create a second server if the starter already owns the server lifecycle.

Initializing at NOT_SERVING avoids a window where the server has opened its port while critical dependencies are not yet ready. Transition to SERVING only after startup completes. If there are multiple services, set individual statuses for each service and update the overall status only when the entire server truly cannot accept traffic.

## 4. Client-side load balancing with healthCheckConfig

In client-side load balancing, the gRPC application connects to a resolver that returns a list of backends. The load balancing policy picks a subchannel to send RPCs. You can configure service config with healthCheckConfig so the client performs health checking on backends:

~~~json
{
  "healthCheckConfig": {
    "serviceName": "acme.orders.v1.OrderService"
  },
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

healthCheckConfig specifies the service name the client should monitor via gRPC Health Watch. When a backend reports NOT_SERVING, the client-side LB can exclude that subchannel from the eligible endpoint set for that service's RPCs. round_robin is an example policy distributing requests across eligible backends.

Service config must be supplied to the channel via a name resolver or default configuration supported by gRPC Java. Example of direct channel configuration:

~~~java
Map<String, ?> serviceConfig = Map.of(
    "healthCheckConfig",
    Map.of("serviceName", "acme.orders.v1.OrderService"),
    "loadBalancingConfig",
    List.of(Map.of("round_robin", Map.of())));

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.internal:9090")
    .defaultServiceConfig(serviceConfig)
    .build();
~~~

This is an example for a gRPC Java client with a corresponding resolver and LB policy. Verify that the policy is supported in your runtime version and actual resolver configuration. If the resolver returns its own service config, unify the configuration source; do not assume defaultServiceConfig always overrides service config from the resolver.

Health checking must be supported by the load balancing policy/client runtime. Simply declaring a service name in a Spring YAML file does not automatically make every channel or proxy perform health checks.

## 5. Infrastructure proxies and load balancers

Not every load balancer uses the same mechanism:

- **TCP/L4 load balancers** usually only check port connectivity or transport-layer health probes. They do not inherently understand individual gRPC service statuses.
- **gRPC-aware L7 proxies/service meshes** can call gRPC Health Check or Watch to decide which backends are eligible.
- **Kubernetes readiness** determines whether a pod is in the EndpointSlice/Service endpoints; probes can use HTTP, TCP, or gRPC depending on configuration and version.
- **Client-side gRPC LB** uses a resolver and policy inside the client process to monitor each backend, typically via Health Watch when service config enables health checking.

With an L7 proxy, active health check configuration must specify the gRPC protocol and the exact service name. If the proxy only uses an HTTP path or TCP connect, it can verify the process but not the gRPC service status. Check product documentation for HTTP/2 support, gRPC Check/Watch, TLS, and status interpretation.

A deployment can have multiple layers of health checks: Kubernetes readiness removes pods from Service endpoints; Envoy checks cluster endpoints; client-side LB continues monitoring backends. These layers should share the same readiness criteria or have clear reasons when they differ; otherwise a backend might be considered healthy by one layer while being excluded by another.

## 6. Per-service health and routing

Suppose a server provides OrderService and CatalogService. The orders database might fail while catalog still serves from cache:

~~~java
healthManager.setStatus(
    "acme.orders.v1.OrderService",
    ServingStatus.NOT_SERVING);

healthManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.SERVING);
~~~

Clients configured with health checks for OrderService will not select a backend reporting NOT_SERVING for that service. Another client watching CatalogService can still use the same backend. This works only if the LB supports per-service health and appropriate routing; an HTTP load balancer with only pod-level readiness may remove the entire pod.

If a shared dependency affects all RPCs, update the affected services or the overall status per policy. Never report SERVING for a service whose requests are guaranteed to fail just to keep backends in the pool.

## 7. Status during startup, dependency failure, and shutdown

A sensible health lifecycle:

1. **Starting**: initialize the health manager with NOT_SERVING.
2. **Dependency validation**: verify database, credential providers, and critical dependencies with short timeouts.
3. **Ready**: transition relevant services to SERVING.
4. **Degraded**: when a circuit breaker/monitor confirms a dependency is unavailable beyond threshold, transition affected services to NOT_SERVING.
5. **Recovery**: transition back to SERVING only after consistent successful probes or circuit breaker closure.
6. **Draining**: before graceful shutdown, transition to NOT_SERVING so the LB stops selecting the backend for new work; then wait for in-flight requests to finish within the grace period.

Do not update health on a single isolated exception. Distinguish caller errors such as INVALID_ARGUMENT/CANCELLED from dependency availability errors such as repeated UNAVAILABLE. Use cooldowns, statistical windows, and limited probes to avoid health flapping.

When transitioning to NOT_SERVING, Watch clients need time to receive updates and the LB needs time to apply them. Therefore, graceful shutdown still needs a grace period; do not close sockets immediately after changing status.

## 8. Timeouts, security, and health check load

Health checks are traffic too and can create load if run too frequently. You should:

- Use Watch for client-side LB when supported, instead of continuous Check polling from every client.
- If using active Check, set reasonable intervals, timeouts, and failure thresholds.
- Do not let the health handler execute long blocking queries on every check.
- Use state already updated by a monitor/circuit breaker, or lightweight bounded probes.
- Protect health endpoints along trust boundaries; do not let detailed endpoints expose topology or sensitive information.
- If the gRPC server uses TLS/mTLS, configure probes/clients consistently with certificates, hostnames, and credentials.

Health checks do not replace deadlines on business RPCs. An endpoint reporting SERVING only indicates the service is considered capable of accepting requests; each RPC still needs its own deadline, retry, and error handling.

## 9. Testing load balancer removal of failing backends

Tests need at least two backends to verify the LB actually fails over:

| Scenario | What to verify |
| --- | --- |
| Both backends SERVING | Requests are distributed according to policy |
| Backend A transitions to NOT_SERVING | Client/proxy stops sending new RPCs to A after receiving the health update |
| Backend B remains SERVING | Requests continue succeeding via B |
| A recovers to SERVING | A is returned to the pool per policy |
| Service A fails while service B stays healthy | Per-service health does not mistakenly exclude an independent service |
| Backend does not implement Health Watch | LB behaves according to configured policy without assuming the backend is healthy |
| Health endpoint times out or TLS fails | Backend is treated as unhealthy per failure threshold |
| Graceful shutdown | Backend is drained before the server closes connections |

Use a gRPC health client calling Check and Watch to verify server status. Then run integration tests through the exact resolver, LB policy, or proxy used in production; tests calling a single server directly do not prove traffic distribution behavior.

## 10. Observing health-aware load balancing

Monitor by service name and backend identity:

- Counts of SERVING, NOT_SERVING, and UNKNOWN backends.
- Time from server status change until the LB removes or adds the backend.
- Health Watch disconnects/reconnects and Check failures.
- Number of RPCs sent to each backend and error rate after failover.
- Duration a backend remains in draining state.
- Health flapping frequency and causes of status transitions.
- Probe latency, timeouts, and load generated by health checks.

When requests still go to a NOT_SERVING backend, check whether the service name matches, whether the LB supports gRPC health, whether service config is applied, and whether health updates have reached the subchannel. If all backends are excluded, check readiness thresholds and recovery logic; avoid letting the LB aggressively retry endpoints that cannot serve.

## 11. Takeaways and self-check

**Health checks through a load balancer** require a health signal that the LB understands and a routing policy that consumes that signal. TCP probes only check ports; gRPC Health Check/Watch publishes status per service; platform readiness typically decides at the instance level. Register HealthStatusManager, initialize at NOT_SERVING, switch to SERVING when ready, and drain with NOT_SERVING before shutdown. Enable healthCheckConfig on client-side LB or configure gRPC-aware probes in proxies/infrastructure.

Self-check:

1. Why does a successful TCP connect not prove a gRPC service is ready?
2. How do Check and Watch differ?
3. What value in Protobuf must healthCheckConfig.serviceName match?
4. Why might a backend be SERVING for CatalogService yet NOT_SERVING for OrderService?
5. How do client-side LB, L7 proxies, and Kubernetes readiness differ in health scope?
6. Why is a grace period needed after switching a backend to NOT_SERVING?

Health-aware load balancing helps Spring gRPC avoid sending new requests to backends unable to serve, shifts load to healthy instances, and brings backends back into the pool once dependencies recover steadily.
