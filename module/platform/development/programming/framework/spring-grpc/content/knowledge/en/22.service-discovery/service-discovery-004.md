# Service Registration in Discovery Systems

A gRPC service can only be found by clients if the discovery system knows **which service is running, which address to call, and whether the instance is ready**. The process of putting that information into a registry is called service registration. In Spring gRPC, registration is typically tied to the gRPC server lifecycle: registering after the server is ready to accept traffic, maintaining status while running, and removing the instance from discovery when it stops or begins draining.

Registration complements the resolver: the registry stores instance information; the resolver reads that information and provides endpoints to the gRPC channel. This section focuses on registration data, leases/heartbeats, readiness, graceful deregistration, and Spring lifecycle integration.

## 1. What Does Service Registration Solve?

A service may run multiple instances across different machines or Pods. Clients need a stable logical name such as `orders`, while each instance's IP and port can change. The service registry stores instance records so resolvers can find them.

```text
gRPC server instance A ─┐
gRPC server instance B ─┼── register / renew / deregister ──> Service registry
gRPC server instance C ─┘                                      |
                                                               | lookup
                                                               v
                                                        Name resolver
                                                               |
                                                               v
                                                        gRPC client channel
```

Three core operations:

- **Register:** publishes the instance and its endpoint.
- **Renew/heartbeat:** proves the instance is still active and keeps the registration valid.
- **Deregister:** proactively removes the instance from the list eligible to receive requests when it stops or starts draining.

A registry usually stores many instances under the same `serviceName`. Each instance must have its own `instanceId` so one process only updates or deletes its own record.

## 2. Designing a Registration Record

A registration record should contain enough information for clients to connect and apply policies, without containing secrets:

| Field | Example | Meaning |
| --- | --- | --- |
| `serviceName` | `orders` | Logical name that clients look up |
| `instanceId` | `orders-pod-7f9c` | Unique identifier of the instance |
| `host` | `10.20.1.17` or DNS name | Address reachable by clients |
| `port` | `8443` | Listening gRPC port |
| `protocol` | `grpc` | Endpoint type |
| `version` | `2.3.1` | Version for routing/diagnostics if needed |
| `zone` | `ap-southeast-1a` | Location for applying locality policies |
| `health/readiness` | `SERVING` | Whether the instance should receive traffic |
| `leaseTtl` | `30s` | Registration expiration duration if not renewed |
| `metadata` | `team=checkout` | Defined non-sensitive attributes |

`host` must be an address that **clients can actually reach**, not a default bind address such as `0.0.0.0`, `127.0.0.1`, or a hostname that only resolves inside the container. If the service sits behind a gateway, you can register the gateway address; if the resolver connects directly to Pods, publish the Pod endpoint according to network policy.

`instanceId` must be unique within the registry and stable for the lifetime of a process. Do not share one ID across multiple replicas, because one replica deregistering could mistakenly delete another replica's record. Never put tokens, passwords, private keys, or personal data in registration metadata.

Example record in JSON:

```json
{
  "serviceName": "orders",
  "instanceId": "orders-pod-7f9c",
  "host": "10.20.1.17",
  "port": 8443,
  "protocol": "grpc",
  "version": "2.3.1",
  "zone": "ap-southeast-1a",
  "status": "SERVING",
  "leaseTtlSeconds": 30,
  "metadata": {
    "team": "checkout"
  }
}
```

The actual schema depends on Consul, Eureka, Kubernetes, or a custom registry. Agree on which fields are required, which are hints, and how the resolver interprets them.

## 3. Registering at the Right Time: Readiness Before Registration

Do not publish an instance right when the process starts if the gRPC server has not bound its port yet, service dependencies are not ready, or TLS setup is incomplete. If the resolver returns the endpoint too early, clients may send requests to an instance that cannot handle them yet.

A safe startup sequence:

1. Spring initializes configuration, credentials, and required dependencies.
2. The gRPC server binds the port and registers service implementations.
3. Verify readiness: the server is listening, mandatory dependencies are ready, and the instance can handle the required traffic.
4. Register the instance with `SERVING` or the equivalent registry state.
5. Start lease/heartbeat renewal.

If the Spring gRPC starter emits a dedicated server-started/readiness event, use that hook. Spring Boot's `ApplicationReadyEvent` is an option when the gRPC server is already started before the application reports ready. With servers that have an asynchronous lifecycle or starters with custom startup ordering, verify this condition rather than assuming it.

Registration and health checking are related but not identical. The registry can know an instance exists while a health check indicates it is not yet serving. If the registry supports active health checks, configure a safe endpoint/probe and use that status to filter instances. If using heartbeats, a heartbeat only proves the process can still renew its lease; it does not necessarily prove all business dependencies are healthy.

## 4. Leases and Heartbeats

If an instance crashes or loses network connectivity, it cannot send a deregistration request. Therefore, registries typically support a lease/TTL: the record expires if not renewed within the configured interval.

Example with a 30-second TTL and a heartbeat roughly every 10 seconds:

```text
Register ── renew ── renew ── renew ── renew
   |         |        |        |        |
   +---------+--------+--------+--------+----> lease remains valid

Process crash:
Register ── renew ── X
                    |
                    +---- TTL expires ----> registry removes instance
```

The heartbeat interval is usually chosen shorter than the TTL with a safety margin; for example, `TTL / 3` is a starting point, not a strict rule. Account for network latency, JVM pauses, scheduler load, and registry processing time.

When renewal fails:

- Log the registry error category and metrics, without logging credentials.
- Retry with bounded attempts and jittered backoff to avoid request storms.
- Track when the lease might expire.
- If the lease has expired, re-register per policy and verify the instance is still ready.
- Do not continue assuming the instance is discoverable once the registry has evicted the record.

A TTL that is too short causes instances to disappear during pauses or registry slowdowns; a TTL that is too long leaves dead instances in the registry for too long. Choose the TTL based on failure detection SLAs and environment characteristics.

## 5. Integrating Registration with the Spring Lifecycle

You can wrap the registry behind an interface so lifecycle code does not depend directly on the SDK of Consul, Eureka, or a proprietary registry:

```java
import java.time.Duration;

public interface ServiceRegistry {
    void register(ServiceInstance instance);

    void renewLease(
        String serviceName,
        String instanceId,
        Duration ttl);

    void deregister(String serviceName, String instanceId);
}
```

Example record for an instance:

```java
import java.time.Duration;
import java.util.Map;

public record ServiceInstance(
    String serviceName,
    String instanceId,
    String host,
    int port,
    String protocol,
    String version,
    Duration leaseTtl,
    Map<String, String> metadata) {
}
```

A Spring Boot bean can register after the application is ready, renew the lease periodically, and deregister when the context closes:

```java
import java.util.concurrent.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class GrpcServiceRegistration {
    private static final Logger log =
        LoggerFactory.getLogger(GrpcServiceRegistration.class);

    private final ServiceRegistry registry;
    private final ServiceInstance instance;
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor(r -> {
            Thread thread = new Thread(r, "grpc-service-lease");
            thread.setDaemon(true);
            return thread;
        });

    private volatile boolean registered;
    private ScheduledFuture<?> renewalTask;

    public GrpcServiceRegistration(
            ServiceRegistry registry,
            ServiceInstance instance) {
        this.registry = registry;
        this.instance = instance;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void onApplicationReady() {
        if (registered) {
            return;
        }

        // Run only when the gRPC server is ready to accept traffic.
        registry.register(instance);
        registered = true;

        long ttlSeconds = instance.leaseTtl().toSeconds();
        long intervalSeconds = Math.max(1, ttlSeconds / 3);
        renewalTask = scheduler.scheduleAtFixedRate(
            this::renewSafely,
            intervalSeconds,
            intervalSeconds,
            TimeUnit.SECONDS);
    }

    private void renewSafely() {
        if (!registered) {
            return;
        }
        try {
            registry.renewLease(
                instance.serviceName(),
                instance.instanceId(),
                instance.leaseTtl());
        } catch (RuntimeException ex) {
            // Do not log tokens, request headers, or full registry responses.
            log.warn(
                "grpc_service_lease_renewal_failed service={} instance={} error={}",
                instance.serviceName(),
                instance.instanceId(),
                ex.getClass().getSimpleName());
        }
    }

    @EventListener(ContextClosedEvent.class)
    public synchronized void onContextClosed() {
        if (renewalTask != null) {
            renewalTask.cancel(false);
        }
        if (registered) {
            try {
                registry.deregister(
                    instance.serviceName(),
                    instance.instanceId());
            } catch (RuntimeException ex) {
                // TTL serves as a fallback cleanup layer if deregistration fails.
                log.warn(
                    "grpc_service_deregistration_failed service={} instance={} error={}",
                    instance.serviceName(),
                    instance.instanceId(),
                    ex.getClass().getSimpleName());
            } finally {
                registered = false;
            }
        }
        scheduler.shutdownNow();
    }
}
```

This is a general integration example; `ServiceRegistry` and `ServiceInstance` must be provided by appropriate beans. Registry calls must have finite timeouts. If the gRPC starter starts the server after `ApplicationReadyEvent`, replace the event hook with a server-started hook or lifecycle phase that guarantees registration only happens after the listener is open.

When the application shuts down, `ContextClosedEvent` is published before the bean destruction phase; however, the stop order of server components also depends on the starter and lifecycle configuration. Ensure deregistration occurs before the server stops accepting connections. For systems requiring controlled draining, use a lifecycle coordinator to orchestrate explicit ordering.

## 6. Graceful Deregistration and Connection Draining

Deregistering does not automatically close connections that clients have already opened. Some channels may still hold old subchannels or endpoints while the resolver refreshes and the load balancer updates.

The shutdown sequence should be designed as follows:

1. Mark the instance `DRAINING` or not ready so the registry/resolver stops selecting it.
2. Stop accepting new RPCs using the mechanism supported by the server/starter.
3. Allow in-flight RPCs to complete within a grace period.
4. Close the gRPC server and release resources.
5. If deregistration fails, lease TTL lets the registry clean up the record after expiration.

Draining time must be bounded. When the grace period expires, cancel remaining calls according to policy and record the count of interrupted calls. Never leave an instance in `SERVING` state after the server has stopped accepting requests.

For rolling deployments, wait for new instances to become ready and registered before removing old instances if you want to preserve capacity. Readiness configuration, registry propagation, resolver refresh, and termination grace periods must work together.

## 7. Which Registry Is Responsible for Registration?

Not every platform requires the application to call a registry API itself:

| Platform | Typical Registration Approach | Things to Watch |
| --- | --- | --- |
| Consul | Agent/API registers service and health check, optionally with TTL check | Unique ID, TTL renewal, deregistration |
| Eureka | Client integration registers instance and sends heartbeats | Lease/renewal and eviction per configuration |
| Kubernetes | Declare `Service`, `Deployment` labels, and readiness; control plane manages EndpointSlices | Applications usually do not need to self-register each Pod via a registry API |
| Internal registry | Proprietary SDK/API or application adapter | Contract, auth, timeout, retry, and lifecycle must be defined |

In Kubernetes, a `Service` selects Pods by label selector; EndpointSlices are updated by the control plane according to Pod/Service readiness. For gRPC clients using DNS, the Service name is a stable endpoint. If per-Pod client-side discovery is needed, a headless Service can publish Pod addresses as configured. Do not implement an extra registration client to a separate registry when Kubernetes Services already meet your needs, unless the architecture has a clear reason.

With Consul/Eureka starters, prefer the official integration for your version to avoid building a parallel registration mechanism. Only write a manual adapter when you need lifecycle or schema control that the built-in integration cannot provide.

## 8. Security and Correctness of Registration

The registry is a data source that directly affects where clients send traffic. A spoofed record or hijacked endpoint can redirect requests to an untrusted server.

- Authenticate services when writing to the registry; use TLS/mTLS if the platform supports it.
- Restrict permissions: an instance may only register or remove the specific service/instance it owns.
- Validate host, port, protocol, service name, and metadata before publishing.
- Do not publish administrative endpoints or internal ports not meant for clients.
- Do not put credentials, tokens, or private keys in registration metadata.
- Bind certificate SANs/TLS authority to the service name that clients use.
- Use unique instance IDs and idempotent deregister operations.
- Restrict registry read permissions if metadata contains sensitive topology information.

Do not treat a self-reported `SERVING` status as independent proof that the server is healthy. Combine it with active health checks from the registry, the gRPC health service, or platform readiness probes.

## 9. Testing Service Registration

Tests should verify not only that registry APIs are called, but also that endpoints accurately reflect gRPC server state.

| Test Case | Setup | Expected Result |
| --- | --- | --- |
| Successful startup | Server bound and ready | Instance is registered with exact host/port |
| Server not ready | Mandatory dependency not ready | Instance is not published as `SERVING` |
| Two replicas of same service | Different instance IDs | Registry keeps both records |
| Heartbeat succeeds | Lease still valid | TTL is renewed |
| Heartbeat fails | Registry temporarily unavailable | Safe metric/log emitted; bounded retries |
| Lease expires | Process loses ability to renew | Registry evicts instance per TTL |
| Graceful shutdown | Close Spring context | Instance is deregistered before server stops |
| Deregistration fails | Registry unresponsive | Lease expiration acts as fallback cleanup |
| Rolling deployment | New instance ready before old instance drains | No total capacity loss |
| Invalid host/TLS | Register hostname not matching certificate or unreachable address | Validation/tests catch it before production |
| Kubernetes Service | Pod readiness changes | EndpointSlice/DNS reflects state per cluster config |

Unit tests use a fake `ServiceRegistry` to verify register/renew/deregister and idempotency. Integration tests use a test registry or appropriate container, then create a gRPC client through the resolver to call the registered endpoint. Also test crash/TTL behavior and rolling updates in a production-like environment; mock registries do not prove real propagation delays.

## 10. Practice Exercise

`OrderService` runs three instances and registers with an internal registry. The gRPC client resolves the service name `orders`, but after a rollout it sometimes still calls a stopped instance.

**Requirements:**

1. Design a registration record containing service name, instance ID, host, gRPC port, protocol, version, zone, readiness, and lease TTL.
2. Determine the registration timing after the gRPC server is ready; never publish an endpoint that is not listening yet.
3. Design heartbeat/lease renewal with timeouts and backoff; explain how the registry handles an instance crash.
4. Build graceful deregistration, connection draining, and rolling deployment to avoid sending new requests to old instances.
5. Integrate registration with the Spring lifecycle; identify startup and shutdown hooks according to the actual starter.
6. Write tests for multiple replicas, lease expiry, registry outage, deregistration failure, and the resolver receiving new endpoints.
7. If running on Kubernetes, compare using Service/EndpointSlice against self-registering each Pod in a separate registry.

**Self-Check Questions:**

- Which fields does a registration record need for a resolver to build endpoints?
- Why must `serviceName` and `instanceId` be two separate values?
- How does a heartbeat differ from a health check?
- Why should registration happen only after readiness?
- Does deregistering immediately remove every subchannel on the client?
- How does TTL handle the case of a process crash?
- When is a Kubernetes Service sufficient without a custom registration client?
- Why must registry credentials never be placed in instance metadata?

**Key Takeaways:** Service registration publishes where a gRPC instance can be reached and in what state. Register after readiness, use unique instance IDs, renew leases with bounded retries, deregister before the server stops accepting traffic, and let TTL clean up records on process crashes. In Spring gRPC, tie registration to the server lifecycle, secure the registry with authentication, and test startup, renewal, draining, shutdown, and endpoint propagation.
