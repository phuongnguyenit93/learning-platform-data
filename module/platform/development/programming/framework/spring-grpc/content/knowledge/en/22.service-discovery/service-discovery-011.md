# Fallback When Discovery Is Unavailable

Service discovery can become temporarily unreachable due to DNS failures, registry overload, control-plane disconnects, or interrupted watch streams. When that happens, a gRPC client needs an explicit policy to keep using known endpoints, switch to a backup discovery source, or fail safely.

In Spring gRPC, fallback must live at the exact layer experiencing the failure. **The resolver handles finding endpoints; the load balancer chooses connections; the retry policy handles failed RPC calls.** A DNS failure is not the same as a TCP connection failure, and both differ from server business errors. This section focuses on discovery fallback, bounding stale data, and ensuring fallback never causes a client to call the wrong service.

## 1. Identifying Discovery Unavailability

Discovery unavailability is the state where a client cannot fetch or refresh an endpoint list from the discovery source within the required time. Common causes include:

- DNS resolver timeouts, SERVFAIL, or unreachable DNS servers.
- Service registry temporarily unavailable or returning 5xx errors.
- Watch/subscribe stream disconnected and unable to reconnect yet.
- Network policy, proxy, or firewall blocking the path to the registry.
- Expired registry authentication or revoked access permissions.
- Malformed target URI, nonexistent service name, or misconfiguration.

Not every error should trigger the same fallback:

| Error | Classification | Recommended Handling |
| --- | --- | --- |
| Registry timeout, connection reset, 5xx | Potentially transient | Bounded retries; use last-known-good if still valid |
| DNS SERVFAIL or timeout | Potentially transient | Retry with backoff; use configured backup source |
| DNS NXDOMAIN | Possibly wrong name or unpublished record | Verify target; use fallback only if this is an anticipated scenario |
| Malformed target URI | Configuration error | Fail fast; do not try arbitrary endpoints |
| Registry 401/403 | Authentication/authorization error | Fail closed and fix credentials/permissions; do not mask with fallback |
| TLS certificate/hostname mismatch | Security or configuration error | Stop connecting; do not switch to plaintext or skip verification |
| Endpoint connection refused | Transport error to backend | Load balancer reconnects or discovery updates endpoints; do not assume it is a registry error |
| RPC returns `UNAVAILABLE` | Call-, transport-, or server-level error | Analyze status and origin; apply RPC retry if safe |

Proper error classification prevents a misconfiguration from being masked for days by an endpoint cache.

## 2. Fallback Strategies

No single strategy fits every system. Choose based on SLAs, data sensitivity, and reliability of backup sources:

| Strategy | How It Works | Risks / Caveats |
| --- | --- | --- |
| Last-known-good snapshot | Uses the most recent successfully resolved endpoint snapshot within a maximum age | Old endpoints may be dead, retired, or have reassigned IPs |
| Static/bootstrap endpoint | Uses explicitly configured fallback addresses | Can create a single point of failure or target the wrong environment |
| Alternate discovery source | Switches from primary registry to backup DNS/registry | Two sources may differ in data, revisions, or readiness state |
| Stable gateway/proxy | Connects to one stable endpoint; gateway resolves backends | Gateway becomes a critical dependency and needs HA |
| Fail closed | Without valid discovery data, sends no RPCs | Reduces availability, but prevents calling wrong endpoints or violating policy |

You can chain strategies in order, such as primary registry → fresh last-known-good snapshot → backup gateway. Ordering and switch conditions must be explicitly configured, never inferred from exception messages.

## 3. Age-Bounded Last-Known-Good Snapshot

The resolver can retain the last successfully resolved snapshot. When a new lookup fails, that snapshot is used only if it is still within the `maxStale` age limit.

Example:

```text
T=00s  Registry returns revision 120: A, B, C
       Resolver stores last-known-good snapshot

T=10s  Registry times out
       Snapshot age = 10s; maxStale = 60s
       -> Can continue using A, B, C

T=70s  Registry still unavailable
       Snapshot age > maxStale
       -> Stop using stale snapshot; report discovery unavailable
```

A snapshot should store at least:

- Validated endpoint list.
- Registry revision/version if provided by the source.
- Timestamp of the successful lookup.
- Service identity and environment the snapshot belongs to.
- Attributes required for load balancing, if any.

Never share snapshots across different service names, tenants, regions, or environments merely because they share a port. A snapshot for `orders` in staging must never serve as a fallback for `orders` in production.

`maxStale` is a policy bound, not the registry's TTL. It must be shorter than the window in which old endpoints might be reassigned or become unsafe. If the registry returns lease expiry or endpoint validity, do not retain endpoints past that deadline.

## 4. Example Storing and Checking Last-Known-Good

A small store can hold an immutable snapshot in process memory:

```java
import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

record EndpointSnapshot(
    String serviceName,
    String environment,
    long revision,
    List<InetSocketAddress> addresses,
    Instant fetchedAt) {

    EndpointSnapshot {
        addresses = List.copyOf(addresses);
    }
}

final class LastKnownGoodStore {
    private final AtomicReference<EndpointSnapshot> current =
        new AtomicReference<>();

    void update(EndpointSnapshot snapshot) {
        current.set(snapshot);
    }

    Optional<EndpointSnapshot> getUsable(
            String serviceName,
            String environment,
            Instant now,
            Duration maxStale) {
        EndpointSnapshot snapshot = current.get();
        if (snapshot == null
                || !snapshot.serviceName().equals(serviceName)
                || !snapshot.environment().equals(environment)
                || snapshot.addresses().isEmpty()) {
            return Optional.empty();
        }

        Duration age = Duration.between(snapshot.fetchedAt(), now);
        if (age.isNegative() || age.compareTo(maxStale) > 0) {
            return Optional.empty();
        }
        return Optional.of(snapshot);
    }
}
```

This is an illustrative component, not a complete resolver. When updating real snapshots, validate every host/port, enforce non-regressing revisions, verify service/environment identity, and publish snapshots atomically. Use `Instant` to record observation timestamps; if accurate elapsed-time measurement within the same process is needed, use a monotonic clock for internal counters.

In-memory snapshots are lost on process restart. Persisting snapshots to disk should only be done with a clear need; persisted data must include version, service/environment identity, expiration, integrity protection, and re-validation before use. Never load a cache from another deployment or environment.

## 5. Integrating Fallback in NameResolver

When a lookup succeeds, the resolver saves the snapshot and emits `ResolutionResult`. When a lookup fails, the resolver attempts to retrieve a fresh-enough snapshot; if none is valid, it reports an error through the listener.

Overview flow:

```text
NameResolver refresh
       |
       v
Primary discovery lookup
       |
   +---+--------------------+
   | success                | failure
   v                        v
Validate full snapshot   Classify error
   |                        |
   v                        v
Save last-known-good    Is fallback allowed?
   |                        |
   v                   +----+-----+
Publish result         | yes      | no
                       v          v
                Snapshot fresh?  listener.onError
                       |
                 +-----+------+
                 | yes        | no
                 v            v
          Publish fallback   Try alternate source
                              or fail closed
```

Example result handling:

```java
void onLookupFailure(
        Throwable cause,
        NameResolver.Listener2 listener,
        LastKnownGoodStore store,
        String serviceName,
        String environment,
        Duration maxStale) {

    Optional<EndpointSnapshot> fallback =
        store.getUsable(
            serviceName, environment, Instant.now(), maxStale);

    if (fallback.isPresent()) {
        EndpointSnapshot snapshot = fallback.get();
        publishSnapshot(listener, snapshot.addresses());
        recordFallbackUse(snapshot.revision(), cause);
        return;
    }

    listener.onError(
        io.grpc.Status.UNAVAILABLE
            .withDescription("Service discovery is unavailable")
            .withCause(cause));
}
```

Here `publishSnapshot(...)` converts addresses into `EquivalentAddressGroup` objects and calls `listener.onResult(...)` just like in a normal resolver. Callbacks must run on gRPC's `SynchronizationContext`. The example omits the registry client implementation, revision gate, metrics, and backoff to focus on the fallback decision.

Do not call `listener.onError(...)` and simultaneously emit a fallback snapshot for the same resolution attempt without explicit ordering/policy. Pick one outcome per decision: publish a valid snapshot or report a resolution error. If using an alternate source, publish only after that source returns a validated snapshot.

## 6. Static Endpoints and Alternate Discovery

Static endpoints fit local environments, bootstrapping, or a stable gateway. Example configuration:

```yaml
clients:
  orders:
    discovery:
      primary-target: catalog:///orders
      fallback:
        mode: last-known-good
        max-stale: 45s
        static-target: ""
```

In this configuration, `static-target` is empty because the mode is `last-known-good`. If choosing static fallback, addresses must be declared explicitly per environment and must use matching TLS/authority. Never fall back automatically to `localhost`, `127.0.0.1`, or an uncontrolled hardcoded IP.

An alternate discovery source is useful when two independent control planes exist. For example, a primary registry inside the cluster and backup DNS/gateway in another region. Before switching sources, verify:

- Same service identity and API contract.
- Endpoints belong to the right environment, tenant, and region.
- Same TLS/authentication requirements.
- Compatible health/readiness and version.
- Safeguards against split-brain or snapshot revisions older than the primary source.

Two discovery sources sharing the same DNS, network, credentials, or control plane can fail together. Fallback only improves availability when the backup source's failure domain is genuinely independent.

## 7. When Must You Fail Closed?

Fallback is not always safe. Fail closed when you cannot verify endpoints still belong to the right service or security policies are no longer satisfied:

- Malformed target or mismatched service identity.
- Registry returns 401/403 due to invalid credentials or permissions.
- Expired certificate, mismatched SAN, or invalid trust chain.
- Stale snapshot exceeds `maxStale` or lease has expired.
- Endpoints belong to a different environment/tenant/region.
- Fallback would bypass residency, authorization, or routing requirements.

Never switch to plaintext, disable certificate verification, or call a similarly named service to "rescue" requests. For systems handling sensitive data or write operations, failing closed can be the right choice even though it reduces availability.

## 8. Discovery Fallback vs. RPC Retry and Failover

These three mechanisms solve three different problems:

| Mechanism | Triggered When | Where Handled |
| --- | --- | --- |
| Discovery fallback | Cannot obtain a new endpoint list from DNS/registry | Resolver / configuration |
| Load balancing failover | A subchannel cannot connect or is no longer eligible for picking | Load balancer |
| RPC retry | A call fails with a retryable status and has remaining deadline/budget | gRPC retry policy or application |

Discovery fallback does not automatically replay failed RPCs. The load balancer switching to another subchannel does not mean an already-sent RPC is re-executed. RPC retries must consider:

- Remaining deadline and retry budget.
- Retryable status codes.
- Whether the operation is idempotent.
- Whether the server may already have executed the request before the response was lost.
- Backoff and maximum retry attempts.

Do not retry endlessly when the registry or all backends are unavailable; doing so can amplify the outage.

## 9. Spring Configuration by Environment

Fallback mode should be explicitly declared and observable:

```yaml
# application-local.yml
clients:
  orders:
    discovery:
      primary-target: dns:///localhost:9090
      fallback:
        mode: none

---
# application-prod.yml
clients:
  orders:
    discovery:
      primary-target: dns:///orders.default.svc.cluster.local:8443
      fallback:
        mode: last-known-good
        max-stale: 45s
```

Local setups usually do not need discovery fallback because endpoints are fixed and errors should surface immediately. Production can use age-bounded `last-known-good` if SLAs allow. These values are examples; pick `max-stale` based on leases, rollout times, endpoint reuse, and real SLAs.

If a Spring gRPC starter manages channels, configure the target and resolver via the starter version's extension point. If creating `ManagedChannel` manually, keep the channel long-lived, inject it into stubs, and close it when the Spring context shuts down. Do not create a new channel for every fallback; the resolver can emit new snapshots on the active channel.

## 10. Observing Fallback and Avoiding Masked Outages

Fallback keeps the system serving, but can hide a broken registry. Measure and alert on:

- Discovery lookup failure counts by cause.
- Usage counts of last-known-good, static, or alternate sources.
- Snapshot age at the time of fallback.
- Endpoint count and revision of the snapshot in use.
- Duration spent in fallback mode and consecutive lookup failures.
- Counts of snapshots exceeding `maxStale` and failing closed.
- RPC statuses/latency during fallback compared to normal discovery.

Logs should include service name, environment, fallback mode, snapshot revision/age, and error category. Do not log tokens, credentials, or full registry responses. Do not put unbounded IPs/instance IDs in metric labels.

Alert when fallback activates, snapshots approach expiration, or alternate sources are used. A system running in fallback long-term without alerts can turn a temporary outage into a lingering misconfiguration.

## 11. Testing Fallback

Tests must verify both fallback selection decisions and safeguards against bad data:

| Test Case | Setup | Expected Result |
| --- | --- | --- |
| Primary discovery succeeds | Registry returns new snapshot | Resolver stores and publishes primary snapshot |
| Registry timeout, cache fresh | Last-known-good age less than `maxStale` | Resolver publishes cached snapshot and records fallback |
| Cache just expired | Age equals/exceeds policy limit | Stale snapshot is not used |
| No snapshot yet | Discovery fails on first lookup | Fails closed or uses configured bootstrap |
| Wrong service/environment | Cache belongs to another service or profile | Rejects fallback |
| Regressing revision | Backup source returns older snapshot | Does not overwrite newer snapshot unless policy permits |
| Registry 401/403 | Invalid credentials | Reports security error; does not mask with disallowed fallback |
| TLS SAN mismatch | Certificate does not match target | Connection fails; does not fall back to plaintext |
| Alternate source unavailable | Both sources fail | Fails closed after retry budget |
| Discovery recovers | Primary registry returns new snapshot | Resolver switches back to primary and replaces fallback snapshot |
| Channel shutdown | Watch/retries running | Tasks stop and late callbacks are ignored |
| Non-idempotent RPC | Call fails after server may have processed it | Does not blindly retry and cause duplicate execution |

Integration tests should run a test gRPC server at an endpoint in the snapshot. After making the primary registry unavailable, verify the client can still call the server within `maxStale`; once the limit is exceeded, verify the resolver stops using the stale endpoint. Restore the registry and verify the resolver switches back to the primary snapshot.

## 12. Practice Exercise

A Spring gRPC client uses the custom target `catalog:///orders`. The primary registry occasionally times out during rollouts; some clients have a recent endpoint snapshot, while newly started clients have no snapshot yet.

**Requirements:**

1. Classify registry timeout, invalid target, 401/403, and TLS mismatch errors; identify which errors permit fallback.
2. Design a last-known-good snapshot with service identity, environment, revision, endpoint list, and fetch timestamp.
3. Choose `maxStale` based on lease/endpoint lifecycle and define behavior when the cache expires.
4. Define bootstrap/static or an alternate source for newly started clients lacking a snapshot, or choose fail closed if no safe source exists.
5. Integrate fallback inside `NameResolver`, emit complete snapshots, and execute callbacks on `SynchronizationContext`.
6. Distinguish discovery fallback from load balancer failover and RPC retries; set deadlines, retry budgets, and idempotency rules.
7. Write tests for registry outages, cache expiration, wrong environment, TLS mismatch, recovery, and channel shutdown.

**Self-Check Questions:**

- How does discovery unavailability differ from an endpoint transport failure?
- What metadata does a last-known-good snapshot need to avoid calling the wrong service?
- Why must stale snapshots have a `maxStale` limit?
- When is a static endpoint a reasonable fallback?
- Why must 401/403 or TLS mismatches typically fail closed?
- Does discovery fallback automatically retry failed RPCs?
- Why does a fallback source need an independent failure domain?
- How do you know the system is currently serving from a stale snapshot?

**Key Takeaways:** Fallback when discovery is unavailable requires clear backup sources, trigger conditions, and age limits. Last-known-good must only be used for the exact service/environment and within `maxStale`; static or alternate sources must preserve contracts, TLS, and routing policies. Configuration/security errors must fail closed. In Spring gRPC, handle fallback at the resolver, distinguish it from load balancer failover and RPC retries, and measure fallback duration and frequency.
