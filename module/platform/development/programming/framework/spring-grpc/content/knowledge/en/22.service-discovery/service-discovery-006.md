# Unhealthy Endpoints and Pool Removal

In service discovery, an endpoint may still exist in the registry while no longer being eligible to receive RPCs: the application is not ready yet, a critical dependency is failing, the instance is shutting down, or a health check reports `NOT_SERVING`. If the client keeps picking that endpoint, requests will fail even when other instances are healthy.

In Spring gRPC, three layers must work together: **health/readiness determines whether an endpoint can serve; the resolver publishes membership; the load balancer decides which endpoint is chosen for an RPC**. Removing unhealthy endpoints from the pool requires clear signals, recovery timing, and mechanisms to avoid mis-ejection caused by a transient network blip.

## 1. Distinguishing Commonly Confused States

"Unhealthy endpoint" does not have just one meaning. The following signals represent different aspects:

| Signal | What Does It Indicate? | Should the Endpoint Be Removed from Business Traffic? |
| --- | --- | --- |
| Readiness `NOT_READY` | Instance is not ready yet or no longer wants new requests | Yes; do not publish as a serving endpoint |
| gRPC Health `NOT_SERVING` | Health service reports the queried service is not serving | Yes, if the client/LB uses health checking or discovery consumes this state |
| Transport `TRANSIENT_FAILURE` | Connecting to the endpoint is currently failing | Load balancer usually pauses selecting that subchannel and retries connecting; does not necessarily delete registration |
| Lease/heartbeat expired | Instance failed to renew its registration | Registry evicts the record per TTL; this is a liveness/control-plane signal |
| RPC returns `UNAVAILABLE` | A call could not complete because the service or infrastructure was temporarily unavailable | Do not auto-eject from a single failure; requires policy and thresholds |
| Liveness failure | Process needs to be restarted by the management plane | Usually handled by orchestrator restart; not identical to readiness |

Readiness and liveness serve different purposes. A process that is still alive while a mandatory dependency loses connectivity may need to report `NOT_SERVING`; liveness keeps passing to avoid continuous restarts. Conversely, prolonged liveness failure may require restarting the process.

## 2. Layers That Decide Whether an Endpoint Is Selected

An endpoint can be excluded from the pool at several layers:

1. **Application health:** the service knows the state of its dependencies and its ability to process requests.
2. **Platform readiness:** Kubernetes or the registry marks the instance as no longer ready.
3. **Name resolver:** emits a snapshot containing only endpoints allowed to receive traffic.
4. **Client-side health checking:** gRPC health `Watch` updates the backend's serving state; the load balancer can stop picking that endpoint.
5. **Load balancer connectivity:** subchannels in a connection-error state are not picked for new calls according to policy.

Diagram:

```text
Application / dependency health
             |
             v
   Readiness or gRPC Health
             |
       +-----+------------------+
       |                        |
       v                        v
Kubernetes / Registry     Client health Watch
       |                        |
       v                        v
NameResolver snapshot      LoadBalancer health state
       |                        |
       +-----------+------------+
                   v
           Endpoint pick pool
                   |
          healthy endpoint only
```

Not every system uses all layers. Clearly define which source is the source of truth for readiness, which updates the resolver, and whether clients enable health checking. If the application only sets `NOT_SERVING` internally while the resolver/LB does not read that state, traffic may still be sent to the endpoint.

## 3. Providing the gRPC Health Service

gRPC defines the Health Checking Protocol with the `grpc.health.v1.Health` service. Clients or infrastructure can query the status of a specific service; the `Watch` method allows continuous monitoring of status changes.

Common statuses:

- `SERVING`: the service can currently accept requests.
- `NOT_SERVING`: the service should not receive business requests.
- `UNKNOWN`: status has not been determined.
- `SERVICE_UNKNOWN`: the health server does not know the queried service name.

In Java, grpc-java provides `HealthStatusManager` in the `grpc-services` artifact. Example:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;

public final class OrdersGrpcServer {
    public static void main(String[] args) throws Exception {
        HealthStatusManager health = new HealthStatusManager();

        Server server = ServerBuilder.forPort(8443)
            .addService(new OrdersService())
            .addService(health.getHealthService())
            .build()
            .start();

        // Report SERVING only after the server and required dependencies are ready.
        health.setStatus("orders.v1.OrderService", ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            health.setStatus(
                "orders.v1.OrderService", ServingStatus.NOT_SERVING);
            server.shutdown();
        }));

        server.awaitTermination();
    }
}
```

This is a minimal grpc-java example; in Spring gRPC, register the health service and update statuses through a bean/lifecycle component appropriate for your starter. Do not create a separate health manager per request. Use the same state managed along the server lifecycle.

The health service should return `SERVING` after the gRPC listener has started and mandatory dependencies for the service are ready. If `OrderService` depends on a database and cannot handle any requests when the database disconnects, transition that service to `NOT_SERVING`. You do not necessarily have to mark the entire process unhealthy if only one independent service is affected; health status can be set per service name.

## 4. Client-Side Health Checking and the Load Balancer

The health service only exposes status. For the client to stop picking a `NOT_SERVING` backend, the channel must have supported and properly configured health checking. In gRPC, client-side health checking uses `Health/Watch` for the configured service name; the load balancer uses the result to decide whether a backend is eligible to receive RPCs.

Illustrative service config:

```json
{
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrderService"
  }
}
```

This service config must be supplied to the channel according to your grpc-java mechanism. Health checking availability and how to enable it depend on the grpc-java version, load balancing policy, and channel configuration; verify that the active policy actually supports client-side health checking. Do not assume that merely registering `HealthStatusManager` on the server is enough for every client to stop sending requests automatically.

When health `Watch` reports `NOT_SERVING`, client-side health checking can stop picking that backend for new RPCs. When status returns to `SERVING`, the backend can be returned to the pool according to implementation behavior. Health `Watch` is a separate stream; monitor stream errors, reconnects, and unknown states according to policy.

Distinguish health state from connectivity state:

- `READY`: the subchannel is connected and can accept calls at the transport layer.
- `TRANSIENT_FAILURE`: the connection is currently failing; the channel may attempt to reconnect.
- Health `NOT_SERVING`: the server is reachable but declares the service is not ready.

An endpoint with `READY` transport can still be unhealthy at the application layer. Conversely, an endpoint in `TRANSIENT_FAILURE` may recover after reconnecting without being deleted from the registry.

## 5. Excluding Endpoints via the Registry or Resolver

Another approach is for the discovery source to store readiness/health state and for the resolver to publish only eligible endpoints. For example, a registry snapshot:

```text
orders revision 81:
  orders-1  10.20.1.11:8443  SERVING
  orders-2  10.20.1.12:8443  NOT_SERVING
  orders-3  10.20.1.13:8443  SERVING

resolver result:
  10.20.1.11:8443
  10.20.1.13:8443
```

The resolver must filter by a clear rule, such as publishing only instances whose status is `SERVING` and whose lease is valid. When an instance switches to `NOT_SERVING`, the registry emits a new snapshot and the resolver removes the endpoint from `ResolutionResult`.

Key points:

- Emit a **complete snapshot** after each change; do not send deltas if the resolver API you use expects `ResolutionResult`.
- Use revisions/generations to discard stale lookup results arriving late.
- Do not keep removed endpoints indefinitely just because the registry temporarily errors.
- Distinguish `NOT_SERVING` status from an unreachable registry.
- Do not probe individual endpoints directly on the resolver callback thread; use a health source or an asynchronous worker with timeouts.

Avoid filtering endpoints at too many layers simultaneously without coordination. For example, if the registry deletes an endpoint immediately, client health `Watch` still holds a stream, and the resolver caches an old snapshot, ordering and propagation delays must be defined.

## 6. Kubernetes Readiness and gRPC Health

In Kubernetes, the readiness probe determines whether a Pod is considered ready to receive traffic via a Service. For gRPC, the probe can check the application's health service:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  template:
    spec:
      containers:
        - name: orders
          ports:
            - name: grpc
              containerPort: 8443
          readinessProbe:
            grpc:
              port: 8443
              service: orders.v1.OrderService
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
```

This is an illustrative manifest; adjust it to your cluster configuration and how the server implements the health endpoint. Kubernetes native gRPC probes have their own limitations, such as not configuring TLS credentials or authentication like a typical application gRPC client. If the server only accepts TLS or requires authentication, choose an appropriate probe mechanism (for example, an exec/custom probe or an internal health endpoint protected by network policy).

When readiness fails, Kubernetes updates Service/EndpointSlice endpoint state via the control plane. This does not immediately close existing HTTP/2 connections on clients. Clients may continue holding subchannels to old addresses during propagation or connection draining.

Do not use liveness probes to aggressively check every remote dependency. If the database slows down for a few seconds, mass Pod restarts can worsen the outage. Readiness is usually more appropriate for temporarily pausing traffic; liveness should detect processes that cannot self-recover.

## 7. Passive Ejection and Avoiding False Positives

Some load balancers or service meshes provide passive health checking: observing RPC/connection failures to temporarily eject an endpoint. This is useful when no reliable active health signal exists, but a single error is not enough to conclude an instance is broken.

The policy should consider:

- Consecutive error threshold or error rate within a time window.
- Error types: backend `UNAVAILABLE`, network errors, client-timeout `DEADLINE_EXCEEDED`, or business errors.
- Minimum request volume before computing error rates.
- Maximum ejection duration and cooldown.
- Controlled probing (half-open) before returning the endpoint to service.
- Cap on the percentage of ejected endpoints to avoid exhausting cluster-wide capacity.

Do not eject an endpoint merely because of `INVALID_ARGUMENT`, `PERMISSION_DENIED`, or request-level business errors. Those statuses usually reflect caller input/permissions, not backend health. `UNAVAILABLE` can indicate an infrastructure issue, though its source still needs analysis.

Example state machine:

```text
             consecutive failures / health NOT_SERVING
   SERVING ----------------------------------------------> EJECTED
      ^                                                       |
      |                                                       | cooldown
      | successful health check / probe                       v
   HALF_OPEN <-------------------------------------------- PROBING
      |
      +-- failures --> EJECTED
      |
      +-- enough successes --> SERVING
```

This is a policy model, not a mandatory grpc-java state machine. If your current load balancer does not support outlier detection, that responsibility may sit in a service mesh, proxy, or custom load balancer; do not assume standard `round_robin` automatically ejects backends based on application error rates.

## 8. Returning an Endpoint to the Pool

Removing an endpoint is only half the lifecycle. Without a recovery path, a transient error could leave an instance permanently excluded.

The re-admission process should define:

1. The health source returns to `SERVING` or probes succeed.
2. The instance still holds a valid lease/registration and a reachable address.
3. The resolver emits a new snapshot containing that endpoint.
4. Health checking/LB confirms the backend can accept calls.
5. The endpoint is returned to the pool; if supported by the system, traffic can be ramped up gradually.

For passive ejection, require cooldown plus consecutive successful probes before restoring. For readiness, transition to `READY` only after mandatory dependencies have stabilized. Avoid rapid oscillation between `SERVING` and `NOT_SERVING` with appropriate debouncing/hysteresis.

## 9. Graceful Draining When an Endpoint Must Stop

When rolling out a new version or shutting down an instance, the sequence is typically:

1. Transition health status to `NOT_SERVING` or readiness to `false`.
2. Wait for health `Watch`/registry/EndpointSlice and the resolver to propagate the new state to clients.
3. Stop accepting new RPCs and begin draining.
4. Let in-flight RPCs finish within the grace period.
5. Shut down the server; lease TTL acts as a cleanup fallback if deregistration fails.

Exact ordering depends on the infrastructure. If the registry removes the endpoint before health `Watch` reports `NOT_SERVING`, clients may receive two signals at different times. Set a grace period long enough for propagation yet finite. Do not expect removal from a resolver snapshot to immediately cancel all in-flight RPCs.

## 10. Observing and Testing Endpoint Health

Monitor:

- Number of endpoints in `SERVING`, `NOT_SERVING`, and `UNKNOWN` states.
- Number of `READY` and `TRANSIENT_FAILURE` subchannels.
- Latency from health/readiness change to when the endpoint stops being picked.
- Ejection counts, ejection duration, and re-admission counts.
- RPC error rates by endpoint and status code.
- Open health `Watch` streams, stream errors, and reconnects.
- Drain duration and remaining in-flight RPCs at shutdown.

Do not use instance IDs or IPs as unbounded metric labels; cardinality grows quickly during Pod churn. Controlled logs may include endpoint IDs, but never credentials or full metadata dumps.

| Test Case | Setup | Verification |
| --- | --- | --- |
| Initially ready | Server and dependencies are ready | Health returns `SERVING`; endpoint is published |
| Dependency lost | Simulate mandatory database unavailable | Service transitions to `NOT_SERVING`; endpoint stops being picked per policy |
| Health Watch update | Transition `SERVING` to `NOT_SERVING` | Client health checking receives the change |
| Transient transport failure | Drop connection then recover | Subchannel reconnects; registration is not permanently deleted |
| Registry removes endpoint | New snapshot drops instance | Resolver publishes new snapshot; LB updates subchannel |
| Passive error burst | Generate errors exceeding threshold | Endpoint is ejected per defined cooldown |
| Recovery | Consecutive health/probe successes | Endpoint is returned to the pool |
| False positive | One RPC returns `INVALID_ARGUMENT` | Endpoint is not ejected |
| Graceful drain | Set `NOT_SERVING` then shut down | New RPCs stop choosing it; in-flight RPCs handled per grace period |
| Kubernetes readiness | Probe fails then recovers | EndpointSlice updates and traffic returns after propagation |

Integration tests should have at least two backends: backend A transitions to `NOT_SERVING` while backend B remains `SERVING`. Send RPCs continuously and verify new calls stop going to A after the health/discovery update takes effect, while B continues serving. Then return A to `SERVING` and verify it receives traffic again. Separately test an RPC running while A is removed to verify drain policy.

## 11. Practice Exercise

`OrderService` runs three instances. One instance still has an open TCP/HTTP2 connection, but its database pool is exhausted, causing requests to fail. Clients currently rely only on connection state and therefore keep sending calls to this instance.

**Requirements:**

1. Add the gRPC Health service and update `SERVING`/`NOT_SERVING` based on mandatory dependency readiness.
2. Choose a mechanism for clients to stop picking unhealthy endpoints: client-side health checking or resolver filtering of registry readiness; explain the limitations of the other approach.
3. Distinguish health failures from `TRANSIENT_FAILURE`, lease expiry, and an RPC returning `UNAVAILABLE`.
4. Design thresholds/cooldowns if using passive ejection; do not eject on input errors such as `INVALID_ARGUMENT`.
5. Build a recovery path so the endpoint returns to the pool once dependencies recover.
6. Coordinate readiness, registry updates, health `Watch`, and graceful draining during rollouts.
7. Write an integration test with two backends proving traffic stops going to the `NOT_SERVING` endpoint and resumes when it becomes `SERVING`.

**Self-Check Questions:**

- Why does `READY` transport not imply a `SERVING` service?
- How do heartbeats/leases differ from readiness and gRPC Health `Watch`?
- Does registering a health service automatically make every client drop unhealthy endpoints?
- When should the resolver filter endpoints versus when is client-side health checking a better fit?
- Why is a single `UNAVAILABLE` error insufficient to eject a backend?
- How do readiness and liveness probes differ in purpose?
- When an endpoint is removed from the pool, what happens to in-flight RPCs?
- What conditions are needed to safely re-admit an endpoint to the pool?

**Key Takeaways:** Unhealthy endpoints must be detected via appropriate readiness or health signals and propagated to the resolver/load balancer so they are no longer picked for new RPCs. Distinguish health state from transport connectivity and leases; use thresholds/cooldowns to prevent false ejections; provide a recovery path and graceful draining. In Spring gRPC, test the entire path from application state to endpoint selection, not just whether the health endpoint returns the expected value.
