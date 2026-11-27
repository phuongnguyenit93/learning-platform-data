# Service Record TTL

In service discovery, a service record typically represents an instance and the address clients can call. If a process crashes, loses network connectivity, or cannot actively deregister, the record may remain in the registry and cause the resolver to return a dead endpoint. **Time To Live (TTL)** limits how long a record is considered valid without renewal.

In Spring gRPC, TTL must be coordinated with registration, heartbeat/lease renewal, readiness, and graceful shutdown. TTL is a cleanup mechanism for abandoned records; it does not replace health checking and does not guarantee clients immediately stop using an endpoint when the record expires.

## 1. What Does TTL Represent?

TTL is the duration a registry allows a registration to remain valid since the most recent valid register or renew operation. If no renewal is received before expiration, the registry marks the record expired and removes it from discovery results according to the registry's semantics.

Example of a record with a 30-second TTL:

```text
T=0s       Register(instance-A, TTL=30s)
T=10s      Renew(instance-A)  -> expiry pushed forward
T=20s      Renew(instance-A)  -> expiry pushed forward
T=30s      No new renew       -> record remains valid if the most recent
                                 renew pushed expiry past this point

Process crash after last renew:
            No more heartbeats
            |
            v
            TTL expires -> registry removes record
```

TTL is usually managed according to the registry server's clock, not by a client deleting its own record when a local clock hits a timestamp. The client sends a renew request; the registry confirms and updates the expiration time per its implementation rules.

Do not confuse TTL with an RPC deadline, a connection timeout, or a DNS cache duration. It is the validity window of a registration/health lease in the discovery system.

## 2. TTL, Heartbeat, and Health Are Different Concepts

| Mechanism | Question Answered | When Does State Change? |
| --- | --- | --- |
| TTL/lease | Does the registry still consider the registration valid? | Expires if not renewed in time |
| Heartbeat/renewal | Can the instance still contact the registry to renew? | On each renew success or failure |
| Readiness | Can the instance accept business requests right now? | When the application/dependencies change state |
| gRPC Health `Watch` | Does the service report `SERVING` or `NOT_SERVING`? | When health status is updated |
| Transport connectivity | Can the client connect to the endpoint? | When subchannels connect, disconnect, or reconnect |

A successful heartbeat only proves the process can renew its record; it does not prove the database, queue, or business logic is healthy. Conversely, a service may still handle requests fine while temporarily unable to reach the registry. When the lease expires, discovery may remove the instance even though the application is still running.

The design should define the source of truth for each state. For example, readiness controls whether traffic is accepted; TTL handles instances that can no longer renew registrations; gRPC Health lets clients or infrastructure monitor serving status.

## 3. Choosing TTL and Renewal Cadence

Suppose TTL is 30 seconds; an initial setup might renew roughly every 10 seconds. The `TTL / 3` rule is a common starting point to leave headroom for a few failures, not a mandatory value.

When choosing TTL and heartbeat intervals, account for:

- Network latency to the registry and request timeouts.
- JVM pauses, GC pauses, CPU starvation, and scheduler delays.
- Registry load when many instances renew concurrently.
- How many retries can occur before TTL expires.
- Dead-instance detection SLA and acceptable stale-endpoint exposure.
- Propagation delay from registry through resolver to clients.

| TTL | Illustrative Renewal Interval | Characteristics |
| --- | --- | --- |
| 15 seconds | 5 seconds | Faster heartbeat-loss detection but sensitive to pauses/slow networks |
| 30 seconds | 10 seconds | Balanced starting point for many systems |
| 60 seconds | 20 seconds | More headroom, but dead records can persist longer |

These are examples for comparison, not rigid recommendations for every registry. A TTL that is too short causes healthy instances to be evicted during pauses or registry overload. A TTL that is too long leaves dead process records around longer, extending the window in which clients may receive stale endpoints.

Do not set the renewal interval right up against the TTL. Leave a safety margin large enough for timeouts and retries to finish before expiry. With multiple instances, add jitter to prevent all heartbeats from bunching up at the same instant after a rollout.

## 4. Renewal Must Have Timeouts and Bounded Retries

Each renew attempt must finish within a finite deadline. If calls to the registry hang indefinitely, the scheduler can stall renewals and other instances may also be affected if they share an executor.

A practical renewal policy should:

1. Send renewals ahead of expiry with a safety margin.
2. Set request timeouts shorter than the remaining lease duration.
3. On transient errors, retry with exponential backoff and jitter.
4. Cap retry attempts to avoid request storms.
5. Track the last successful renewal time and estimated remaining lease time.
6. If lease validity cannot be confirmed before a safety threshold, mark the instance not ready and stop accepting new traffic per policy.

Not all renew errors mean the same thing:

| Outcome | Interpretation | Action |
| --- | --- | --- |
| Success | Registry confirms lease extended | Update last successful renewal timestamp |
| Timeout/network error | Unknown whether registry received the renewal | Bounded retries; check lease state if API supports it |
| Unauthorized/forbidden | Problem with credentials or registration permissions | Report config/security error; do not retry aggressively |
| Lease/instance missing | Record already expired or ID no longer owns lease | Re-register via a workflow that checks readiness |
| Registry unavailable | Control plane temporarily unreachable | Back off, alert, and protect traffic as lease nears expiry |

A timeout does not always mean the renewal failed: the request may have reached the registry while the response was lost. Registry APIs should support idempotent renewals by lease/instance identity or provide a way to confirm state so clients can handle ambiguous outcomes.

## 5. Tying TTL to Registration in Spring

The application should keep service name, instance ID, and lease identity separate. A registry adapter hides the specific API of Consul, Eureka, or an internal system:

```java
import java.time.Duration;

public record ServiceInstance(
    String serviceName,
    String instanceId,
    String host,
    int port,
    Duration leaseTtl) {}

public interface ServiceLeaseRegistry {
    Lease register(ServiceInstance instance, Duration ttl);

    Lease renew(Lease lease, Duration ttl);

    void deregister(Lease lease);

    record Lease(
        String serviceName,
        String instanceId,
        String leaseId) {}
}
```

The lifecycle coordinator example below illustrates registering after readiness, renewing periodically, and deregistering on shutdown. The registry client must set finite timeouts on every call:

```java
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class GrpcLeaseLifecycle {
    private static final Logger log =
        LoggerFactory.getLogger(GrpcLeaseLifecycle.class);

    private final ServiceLeaseRegistry registry;
    private final ServiceInstance instance;
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();
    private final AtomicBoolean stopping = new AtomicBoolean();

    private volatile ServiceLeaseRegistry.Lease lease;
    private ScheduledFuture<?> renewal;

    public GrpcLeaseLifecycle(
            ServiceLeaseRegistry registry,
            ServiceInstance instance) {
        this.registry = registry;
        this.instance = instance;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void startAfterReadiness() {
        if (lease != null || stopping.get()) {
            return;
        }

        Duration ttl = instance.leaseTtl();
        lease = registry.register(instance, ttl);

        long intervalSeconds = Math.max(1, ttl.toSeconds() / 3);
        renewal = scheduler.scheduleWithFixedDelay(
            this::renewSafely,
            intervalSeconds,
            intervalSeconds,
            TimeUnit.SECONDS);
    }

    private synchronized void renewSafely() {
        ServiceLeaseRegistry.Lease current = lease;
        if (current == null || stopping.get()) {
            return;
        }

        try {
            lease = registry.renew(current, instance.leaseTtl());
        } catch (RuntimeException ex) {
            log.warn(
                "service_lease_renew_failed service={} instance={} error={}",
                instance.serviceName(),
                instance.instanceId(),
                ex.getClass().getSimpleName());
            // Production code needs to track safety margins,
            // retry/backoff, and update readiness when the lease is no longer certain.
        }
    }

    @EventListener(ContextClosedEvent.class)
    public synchronized void stopAndDeregister() {
        if (!stopping.compareAndSet(false, true)) {
            return;
        }
        if (renewal != null) {
            renewal.cancel(false);
        }
        ServiceLeaseRegistry.Lease current = lease;
        if (current != null) {
            try {
                registry.deregister(current);
            } catch (RuntimeException ex) {
                // TTL serves as a fallback cleanup layer if deregistration fails.
                log.warn(
                    "service_lease_deregister_failed service={} instance={} error={}",
                    instance.serviceName(),
                    instance.instanceId(),
                    ex.getClass().getSimpleName());
            }
        }
        scheduler.shutdownNow();
    }
}
```

This is a general integration skeleton, not a complete adapter for a specific registry. In production, add timeouts, jittered backoff, expired-lease handling, readiness updates when renewal becomes uncertain, and guaranteed shutdown ordering. If `ApplicationReadyEvent` fires before the gRPC server is actually ready in your starter, replace it with the appropriate server-started/readiness hook.

Do not run unbounded registry tasks on RPC processing threads. Use a dedicated scheduler for lease renewals or an application-managed scheduler with clear resource limits. Do not create a new scheduler for each heartbeat.

## 6. What Happens When TTL Expires?

When a lease expires, the registry can remove the record from lookup/watch results. The resolver receives the new snapshot and publishes a new endpoint list; the load balancer updates subchannels. However, this process has latency:

1. The registry determines the record has expired.
2. The registry updates discovery data or emits an event.
3. The resolver receives the change or performs the next lookup.
4. The resolver emits a new `ResolutionResult`.
5. The load balancer updates the pool and stops choosing the removed endpoint for new RPCs.
6. Existing connections and in-flight RPCs are handled according to connection lifecycle/graceful draining.

TTL expiration does not immediately close TCP/HTTP2 connections on all clients. Clients may retain old subchannels for a period, especially when resolver refreshes are slow or proxies/caches introduce propagation delay.

Therefore, measure **the time from the last renewal until the endpoint stops being picked**, rather than only measuring when the registry deletes the record.

## 7. How TTL Differs Across Discovery Systems

Not every registry exposes TTL through the same API:

| System | Common Management Approach | Notes |
| --- | --- | --- |
| Consul | Service registration can attach a TTL check; agent/client must update check status before expiry | A TTL check is a time-bounded health check; understand agent ownership and expiration behavior |
| Eureka | Client sends periodic heartbeats; server uses lease/renewal and eviction policies | Renewal/eviction thresholds have specific semantics, not necessarily equivalent to an arbitrary per-record TTL |
| Kubernetes | Services/EndpointSlices are updated by the control plane based on Pods, readiness, and endpoint lifecycle | Typically no application-managed TTL heartbeat per Service record |
| Internal registry | Lease/TTL per platform-defined contract | Must define expiry, renewal, ownership, idempotency, and stale behavior |

If using an official Consul/Eureka starter or integration, prefer configuration and lifecycle managed by that integration. Avoid adding a parallel manual heartbeat that makes two registration mechanisms conflict.

In Kubernetes, readiness and EndpointSlices are usually the primary mechanism for managing endpoints. Do not add custom TTL registration merely because service discovery has a TTL concept; only do so if the architecture uses a separate registry with a clear contract.

## 8. TTL, Stale Records, and Graceful Shutdown

TTL primarily handles cases where an instance disappears without deregistering, such as a process crash or node network loss. During normal shutdown, deregister proactively:

1. Transition readiness or gRPC Health to `NOT_SERVING`/`DRAINING`.
2. Stop accepting new RPCs via the server/lifecycle mechanism.
3. Deregister or update the record so resolvers stop selecting the instance.
4. Allow in-flight RPCs to complete within the grace period.
5. Shut down the server and resources.

If deregistration fails, TTL cleans up the record after expiration. TTL does not replace draining because the record remains valid while waiting for expiry.

When renewal loses connectivity for an extended period, the application should enforce a safety threshold: if lease validity cannot be confirmed, transition readiness to not-serving or stop publishing `SERVING`. When the registry recovers, re-registration must verify the instance is still ready and use a new identity/lease if the old lease expired.

## 9. Observing TTL and Alerting

Useful metrics:

- Active registrations per service.
- Counts of register, renew, renew failure, and deregister operations.
- Renewal latency and timeout rate.
- Time since the last successful renewal.
- Leases close to expiry or already expired.
- Re-registrations after lease loss.
- Propagation time from expiry to resolver/LB endpoint update.
- Stale endpoints still picked by clients if telemetry is available.

Logs should include service name, controlled instance ID, operation, outcome, and error category. Do not log registry tokens, credentials, or full responses containing sensitive data. Avoid using instance IDs as unbounded metric labels if Pod counts churn continuously.

Set alerts on prolonged renewal failures, rising counts of near-expiry leases, high registry latency, or simultaneous lease losses across many instances. Simultaneous lease losses may indicate a registry/network outage rather than every application instance dying at once.

## 10. Testing TTL and Lease Lifecycle

Do not wait tens of real seconds for TTLs in every unit test. Use a fake clock or a test registry with controllable time; integration tests verify real registry semantics:

| Test Case | Setup | Verification |
| --- | --- | --- |
| Initial register | Instance ready, register with TTL | Registry returns a lease/record with expiry |
| Renew succeeds | Renew before expiry | Lease is extended |
| No renewal | Stop heartbeats | Record expires and is removed from discovery |
| Renew timeout | Simulate slow/lost response | Bounded retries; ambiguous outcome handled safely |
| Registry unavailable | Block registry connectivity | Metrics/alerts emitted; readiness handled per safety margin |
| Lost lease | Renew with an invalid lease ID | Re-register per policy, without assuming old lease is alive |
| Heartbeat jitter | Multiple instances start together | Renewal requests do not spike simultaneously |
| Graceful shutdown | Close Spring context | Stop renewals and deregister the exact instance |
| Deregister fails | Registry unresponsive at shutdown | TTL eventually cleans up the record |
| Stale endpoint | Resolver sees expired record | New snapshot drops endpoint; new RPCs stop picking it after propagation |
| Rolling deployment | New instance ready before old instance drains | Capacity maintained during rollout |

Unit tests use a fake `ServiceLeaseRegistry` to verify register/renew/deregister and retry policies. Integration tests use a real or test-container registry to verify actual expiry, then call through the resolver/channel and confirm the endpoint is no longer chosen. Tests must measure both registry expiry and when the client pool updates, because those two moments are not identical.

## 11. Practice Exercise

`OrderService` registers three instances in an internal registry with a 30-second TTL. When a Pod is killed abruptly, its record still appears and some clients keep receiving `UNAVAILABLE`.

**Requirements:**

1. Explain why the record still exists after a process crash and how TTL solves that situation.
2. Choose a renewal interval, timeout, retry/backoff, and jitter suitable for a 30-second TTL; state the safety margin.
3. Design lease identity using `serviceName` and `instanceId`, preventing one replica from deleting another replica's registration.
4. Handle ambiguous renewal timeouts and expired-lease cases.
5. Coordinate readiness, gRPC Health, deregistration, and graceful draining on normal shutdown.
6. Write tests for expiry, registry outages, synchronized heartbeats, stale endpoints, and resolver propagation.
7. Compare the TTL semantics of your registry with Kubernetes EndpointSlice/readiness.

**Self-Check Questions:**

- Which component's confirmation starts or extends a TTL?
- Why does a successful heartbeat not prove the business service is healthy?
- Why should the renewal interval not be close to expiry?
- Does a timeout during renewal always mean the registry never received the request?
- When a lease expires, why might clients still hold old subchannels?
- How does TTL differ from readiness and gRPC Health `Watch`?
- Why is graceful deregistration still necessary even when the registry has TTL?
- When should you re-register instead of continuing to renew an old lease?

**Key Takeaways:** TTL limits how long a service record remains valid if an instance stops renewing its lease. Choose TTL and renewal cadence with safety margins, timeouts, retry/backoff, and jitter; track lease loss so you do not keep serving when registration is uncertain. TTL cleans up abandoned records, while readiness/health and graceful deregistration control serving availability. In Spring gRPC, tie lease renewal to the server lifecycle and test both registry expiry and when the resolver/load balancer stops picking the endpoint.
