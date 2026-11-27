# Updating the Endpoint List

In service discovery, a gRPC service's endpoint list changes throughout instance lifecycles: new Pods appear, old instances drain, IP addresses change, or the registry marks an endpoint as no longer serving. Clients must receive those updates without recreating the channel on every change.

In grpc-java, the **`NameResolver` publishes a new endpoint snapshot to the channel** using `ResolutionResult`. The load balancer receives the snapshot, updates subchannels, and decides which endpoint is used for subsequent RPCs. The resolver is responsible for watching the discovery source and emitting new data; it does not manage connections itself or distribute individual requests.

## 1. The Endpoint List Is a Snapshot of Discovery State

An endpoint typically consists of a host/port address and optionally attributes such as zone or non-sensitive routing metadata. The resolver converts them into `EquivalentAddressGroup` objects and places them in a `ResolutionResult`.

Example registry output:

```text
Snapshot revision 41:
  orders-1 -> 10.20.1.11:8443
  orders-2 -> 10.20.1.12:8443

Snapshot revision 42:
  orders-2 -> 10.20.1.12:8443
  orders-3 -> 10.20.1.13:8443
```

In revision 42, endpoint `orders-1` was removed and `orders-3` was added. `orders-2` remains. The resolver should emit the **entire current snapshot**, rather than sending only diffs, so the channel can compute the latest endpoint state consistently.

| Change in Registry | Resolver Action |
| --- | --- |
| Instance added | Include the new endpoint in the snapshot |
| Instance removed | Omit the endpoint from the next snapshot |
| Host/port changed | Replace the old endpoint with the new address |
| Attributes changed | Emit a snapshot with the new attributes |
| Endpoint no longer ready | Remove from traffic-eligible endpoints or mark per policy |
| No valid endpoints left | Report no-endpoint discovery state per policy; do not retain stale list indefinitely |

An endpoint needs a stable identifier, such as `instanceId`, to distinguish one instance from another when addresses change. Do not rely solely on list index because DNS/registry ordering can change between reads.

## 2. Who Receives and Applies Endpoint Updates?

The update flow has three parts:

```text
Service registry / DNS watch
          |
          | snapshot revision 42
          v
Custom NameResolver
          |
          | listener.onResult(ResolutionResult)
          v
gRPC ManagedChannel
          |
          v
LoadBalancer
    |             |
    v             v
Subchannel A    Subchannel B
    |             |
    +---- RPC pick / connection lifecycle
```

- The registry or DNS is the source of endpoint data.
- The resolver emits new resolution results to the channel.
- The load balancer compares the new result against current state, creates or removes subchannels, and picks connections according to policy.

The resolver should not open sockets to each endpoint itself, round-robin RPCs itself, or close load balancer subchannels. Those operations belong to the channel/load balancer.

## 3. Publishing a New Snapshot with NameResolver.Listener2

When the resolver receives a new endpoint list, it converts the data into `EquivalentAddressGroup` instances and calls `listener.onResult(...)`. Each call carries a complete snapshot:

```java
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;

void publishSnapshot(
        NameResolver.Listener2 listener,
        List<InetSocketAddress> endpoints) {

    List<EquivalentAddressGroup> groups = new ArrayList<>();
    for (InetSocketAddress endpoint : endpoints) {
        groups.add(new EquivalentAddressGroup(endpoint));
    }

    NameResolver.ResolutionResult result =
        NameResolver.ResolutionResult.newBuilder()
            .setAddresses(groups)
            .build();

    listener.onResult(result);
}
```

This snippet illustrates the conversion step. A real resolver must validate host/port before constructing `InetSocketAddress`, deduplicate endpoints by identity, preserve required attributes, and ensure the callback executes on gRPC's `SynchronizationContext`.

Do not send deltas like "add endpoint X" or "remove endpoint Y" as if the listener were an event bus. `onResult(...)` replaces the current resolution result with a new one; therefore, the snapshot must contain all still-valid endpoints.

## 4. Watching for Changes: Watch or Polling

There are two common ways to learn about registry changes:

| Approach | Mechanism | Advantages | Things to Manage |
| --- | --- | --- | --- |
| Watch/subscribe | Registry pushes events or streams changes | Low update latency, less polling | Reconnects, event ordering, resync after disconnect |
| Polling | Resolver queries snapshots periodically | Simple, easily recovers on next read | Query frequency, detection delay, jitter, and registry load |

With watches, do not keep applying individual events forever. After a disconnect or a detected revision gap, the resolver should reload a full snapshot to resynchronize. With polling, include timeouts, backoff on failure, and jitter so many clients do not query the registry at the exact same moment.

A hybrid strategy uses watches for fast updates and periodic full-snapshot resyncs to correct drift. Limit the number of watchers per channel/service and close subscriptions when the resolver shuts down.

## 5. Atomic Updates and Discarding Stale Results

Asynchronous lookups can complete out of order. For instance, reading revision 42 may finish slower than reading revision 43; if the resolver emits revision 42 after revision 43, the channel could revert to old endpoints.

Attach a monotonically increasing revision or sequence number to each snapshot:

```java
import java.util.concurrent.atomic.AtomicLong;
import io.grpc.SynchronizationContext;

final class EndpointUpdateGate {
    private final AtomicLong latestRevision = new AtomicLong(-1);
    private final SynchronizationContext syncContext;

    EndpointUpdateGate(SynchronizationContext syncContext) {
        this.syncContext = syncContext;
    }

    void accept(long revision, Runnable publish) {
        syncContext.execute(() -> {
            long current = latestRevision.get();
            if (revision <= current) {
                return; // Ignore stale or duplicate snapshot.
            }
            latestRevision.set(revision);
            publish.run();
        });
    }
}
```

This is an illustrative skeleton; in a real resolver, `publish` must emit a validated snapshot through the listener on the same synchronization context. If the registry lacks a revision number, a local generation counter can discard stale lookups initiated by the resolver itself. A generation counter only orders client-initiated requests; it does not replace an authoritative registry revision when multiple writers exist concurrently.

Do not mutate a shared collection by clearing it and adding endpoints one by one while another callback might read it. Build a new immutable snapshot, validate it completely, and publish it once. The channel will see either the state before or after the update, never a half-populated list.

## 6. Handling Adds, Removes, and Address Changes

The resolver can compare the new snapshot with the previous snapshot to measure churn, log counts, or emit metrics:

| Endpoint | Old Snapshot | New Snapshot | Interpretation |
| --- | --- | --- | --- |
| `orders-1` | `10.20.1.11:8443` | Absent | Removed from discovery |
| `orders-2` | `10.20.1.12:8443` | `10.20.1.12:8443` | Unchanged |
| `orders-3` | Absent | `10.20.1.13:8443` | New endpoint |
| `orders-4` | `10.20.1.14:8443` | `10.20.1.24:8443` | Address changed |

Identity should rely on `instanceId` or a key supplied by the registry. When a host/port changes, the resolver emits the new endpoint for the same identity; the load balancer may need to create a new subchannel and drop the old one.

Do not keep an endpoint that the registry has revoked just because it worked previously. If stale caching is needed to tolerate registry outages, define an explicit age limit, rationale, and policy. Stale endpoints can route requests to dead instances or hosts reassigned to another workload.

## 7. Empty Results and Discovery Errors

Having no valid endpoints is a state that must be handled intentionally:

- If the registry returns a valid empty snapshot, the resolver can emit an empty result if the version's load balancer/policy supports it and the application wants the channel to enter a no-endpoint state; or report `UNAVAILABLE` per the discovery contract.
- If a registry request fails temporarily, call `listener.onError(Status.UNAVAILABLE...)` and perform retry/backoff per policy.
- If the target is malformed or the service key is invalid, fail configuration early; do not retry endlessly.
- If a new snapshot is invalid, do not publish a partial snapshot. Retain the previous valid state only within a defined grace period, or report an error per policy.

There is no single choice for every registry. What matters is distinguishing "no instances available," "registry unreachable," and "misconfigured target." Metrics and logs must reflect the proper category without recording credentials or full registry responses.

## 8. How Does the Load Balancer Update Subchannels?

Upon receiving a new `ResolutionResult`, the load balancer uses the list of `EquivalentAddressGroup` instances to update subchannels:

- New endpoints can trigger new subchannels and connection attempts.
- Endpoints absent from the snapshot can be excluded from selection for new RPCs.
- Remaining endpoints can keep their existing subchannels if identity/addresses match.
- Endpoints whose addresses changed may require new subchannels.

Removing an endpoint from a snapshot does not mean every in-flight RPC on that connection is immediately canceled. In-flight RPCs can complete according to the connection lifecycle; the server can continue draining. Retries or failover to another endpoint depend on retry policy, status, and RPC idempotency.

This is why discovery updates must coordinate with graceful deregistration:

1. The instance transitions to `DRAINING` or is no longer published as ready.
2. The registry emits a snapshot removing the instance from the endpoint list.
3. The resolver delivers the new snapshot to the channel.
4. The load balancer stops selecting that endpoint for new RPCs and updates subchannels.
5. The server waits for in-flight RPCs to finish within the grace period and then shuts down.

The resolver only publishes membership and attributes. It does not guarantee that every client stops sending traffic to the instance instantaneously; there are propagation delays, caches, and open connections.

## 9. Integrating Endpoint Updates in Spring gRPC

In Spring, a channel is typically a long-lived bean shared across many stubs/calls. When the resolver emits a new snapshot, the channel updates automatically via grpc-java's mechanisms; the application should not recreate the channel whenever the registry changes endpoints.

Example channel configuration with a custom target:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forTarget("catalog:///orders")
            .useTransportSecurity()
            .build();
    }
}
```

The provider for the `catalog` scheme and the resolver watching the registry must be registered before the channel resolves the target. If a Spring gRPC starter manages channels, configure the target and resolver through the starter version's extension point; keep a single long-lived channel and let the resolver push updates.

Do not swap the target URI with a new IP on every event. Doing so forces the application to manage creating/closing channels, stubs, and in-flight calls itself, risking resource leaks or request disruptions.

## 10. Observing and Testing Endpoint Updates

Track metrics that show whether the resolver is updating accurately and promptly:

- Number of endpoints in the current snapshot.
- Time from registry revision/event to resolver publication.
- Count of endpoint adds/removes/changes.
- Count of refreshes, lookup failures, and watch reconnects.
- Age of the current snapshot and timestamp of the last successful update.
- Number of connected or errored subchannels if the load balancer exposes telemetry.

Do not use individual endpoint IPs, instance IDs, or hostnames as unbounded metric labels; cardinality can grow rapidly as instances churn. You can log necessary IDs under controlled logging, while avoiding credentials and sensitive data.

| Test Case | Scenario | Verification |
| --- | --- | --- |
| Initial snapshot | Registry returns two endpoints | Resolver publishes both endpoints |
| Add endpoint | Registry adds a third instance | New snapshot contains all three |
| Remove endpoint | Registry removes a drained instance | New snapshot no longer includes that instance |
| Address change | An instance's host/port changes | New snapshot contains the new address |
| Out-of-order result | Revision 43 arrives before revision 42 | Revision 42 is ignored |
| Duplicate event | Same revision emitted twice | Does not cause update churn |
| Watch reconnect | Connection drops and reconnects | Resolver reloads a full snapshot |
| Empty result | No ready endpoints remain | Channel enters state per defined policy |
| Registry unavailable | Lookup times out or fails | Error reported; bounded retry/backoff |
| Resolver shutdown | Channel closes while watch is active | Subscription/executor stopped; late callbacks ignored |
| In-flight RPC | Endpoint removed while a call is running | Drain/cancel matches policy; do not assume all calls auto-retry |

Unit tests use a fake registry to emit snapshots with controlled revisions. Integration tests can start two gRPC servers on dynamic ports, have the resolver return the first endpoint, then update the snapshot to the second endpoint and verify new RPCs reach the new endpoint. Add a test for an in-flight RPC during an update to confirm draining behavior.

In-process tests are useful for resolver logic, but do not exercise real TCP/TLS connections. When verifying TLS authority, proxies, DNS caching, or connection draining, run tests against real transport and infrastructure.

## 11. Practice Exercise

`OrderService` runs multiple instances. The custom resolver currently reads the registry only once at channel initialization, so new Pods are never used by clients and old Pods sometimes still receive requests after starting shutdown.

**Requirements:**

1. Design a snapshot with revisions and stable endpoint identities.
2. Add watch or polling support to receive changes from the registry.
3. Emit a complete new `ResolutionResult` after validation; do not send deltas or mutate a shared collection piecemeal.
4. Discard late stale snapshots, handle duplicate events, and resync after reconnects.
5. Coordinate endpoint removal with `DRAINING`, load balancer subchannel updates, and server graceful shutdown.
6. Write tests for add/remove/address change, empty results, registry outages, out-of-order revisions, and in-flight RPCs.

**Self-Check Questions:**

- Why must `onResult(...)` receive a complete snapshot?
- How do the resolver and load balancer divide responsibility for endpoint updates?
- Why do revisions prevent stale lookup results from overwriting newer state?
- When an endpoint is removed, what happens to in-flight RPCs?
- Why must a watch resync the snapshot after reconnecting?
- When should `UNAVAILABLE` be reported versus handling an empty result per policy?
- Why should Spring gRPC keep a long-lived channel rather than recreating the channel whenever endpoints change?

**Key Takeaways:** Updating the endpoint list is the process of publishing new discovery snapshots to a gRPC channel. The resolver watches the registry, validates, and publishes a complete `ResolutionResult`; the load balancer updates subchannels and selects endpoints for new RPCs. Use revisions to drop stale results, update snapshots atomically, handle empty/error states by policy, and coordinate deregistration with graceful draining. In Spring gRPC, keep channels stable and test both endpoint updates and in-flight RPCs.
