# Dynamic Configuration and Multi-Instance Consistency

## 1. Problem: Changing Quotas When a System Has Multiple Instances

In the **SPRING_INTEGRATION_PATTERN** module, Spring Integration connects Enterprise Integration Patterns (EIP) such as Gateway, Filter, Transformer, Router, Service Activator, Splitter, and Aggregator using message channels. A processing flow may run across multiple pods or multiple JVMs to scale throughput. When calling an external dependency, we typically place a **rate limiter** before the call site to limit how many messages can proceed over a time window, preventing quota overruns or upstream overload.

Suppose the Stock API allows the system to call an average of **120 requests/second**, with a maximum burst of 120 permits. The application runs **three pods**, and every pod receives messages from Gateways or consumers.

If each pod creates a **120 requests/second** rate limiter in RAM, total granted permits can reach **360 requests/second**. Updating the configuration from 120 down to 60 where only two pods receive the update also makes the system-wide limit vary depending on which pod handles the request.

The problem has **two independent requirements**:

1. **Dynamic configuration:** change rates, bursts, tenant quotas, or rejection policies without restarting every pod.
2. **Multi-instance consistency:** pods enforce the same **cluster-wide** limit at the chosen guarantee level, without multiplying quota by pod count.

**Synchronizing config files does not mean synchronizing permit counters.** Every pod can receive the exact same number 120 and still issue 120 permits on its own. To enforce a cluster-wide limit, you need coordinated quota distribution, such as a shared token store with atomic operations or a centralized quota-enforcing gateway.

~~~mermaid
flowchart TD
    A[Policy control plane] -->|Versioned update| B[Policy store]
    B --> C[Pod 1: Spring Integration]
    B --> D[Pod 2: Spring Integration]
    B --> E[Pod 3: Spring Integration]
    C --> F[Shared atomic rate gate]
    D --> F
    E --> F
    F -->|Permit| G[Stock API]
    F -->|Reject| H[429 / fallback / defer]
~~~

This lesson focuses on how to **choose quota scope, manage config versions, execute atomic permits, handle errors, and test across multiple instances** in a Spring Integration flow.

## 2. Clarify First: What Is the Quota Limiting?

A "120 req/s" setting is not enough to implement properly. You must specify **scope**, **algorithm**, **counting unit**, **burst**, and **desired consistency level**.

| Decision | Example | Consequence |
| --- | --- | --- |
| **Scope** | `stock.read` system-wide | All pods share one budget |
| **Tenant scope** | `stock.read:tenant-group-A` | Group A has its own quota |
| **Cost** | Each HTTP call costs 1 permit | Physical retries may cost extra permits |
| **Refill** | 120 tokens per second | Target average rate |
| **Capacity** | Maximum 120 tokens | Allows short bursts |
| **On reject** | Fail fast, retry-after, or defer | Defines caller experience |
| **Consistency** | Exact per key or approximate with bounded error | Determines storage model and latency |

**A token bucket with 120 tokens/second refill and capacity 120 does not mean "never more than 120 requests in any sliding one-second window."** Accumulated tokens can allow a burst while new tokens are added during the following interval. If the upstream contract requires a **hard ceiling in every rolling window**, choose a matching window algorithm instead of misunderstanding token buckets.

You must also determine where the limit applies:

- **Ingress:** limits requests before entering the system, typically tied to clients/APIs.
- **Egress:** limits each call to an external dependency, which may be lower than Gateway traffic.
- **Consumer:** limits consumption speed from a queue or message processing rate.
- **By tenant/operation:** establishes fairness across user groups and task types.

One Gateway request can generate **three** external calls via a Splitter. Then "100 Gateway requests/s" is not "100 HTTP calls/s"; place the limiter according to real cost.

## 3. Control Plane and Data Plane: Never Mix the Two Responsibilities

The **control plane** manages policies; the **data plane** decides whether a message proceeds.

| Component | Function | What must be guaranteed |
| --- | --- | --- |
| Policy admin/API | Changes rate, burst, scope, effective time | Authorization, validation, audit |
| Policy repository | Stores approved snapshots/versions | No lost updates; deterministic rollback |
| Config distribution | Notifies pods of new versions | Retries/reconciliation, tolerant of duplicate or out-of-order events |
| Local policy view | Reads snapshot for logs/UI/non-quota-critical decisions | Replace entire snapshot atomically, never mix fields |
| **Shared rate gate** | Grants or rejects permits | Atomic decision against the same bucket and policy |
| Gateway/error/fallback path | Returns outcome on rejection | No infinite retries or lost messages |

Pushing config via pub/sub can help pods update quickly, yet pub/sub **is not proof that every pod holds the exact same version**. Pods restarting, partitioned, or dropping messages may run stale config. Therefore **periodic reconciliation** is needed to fetch the latest snapshot, and the data plane needs rules for when a local view lags behind the authoritative store.

### Three Consistency Levels to Distinguish

1. **Eventual config consistency:** after some time all pods see the new version; during rollout they may differ.
2. **Exact quota per bucket/key:** every permit grant for a key is serialized at one shared place; total permits do not multiply by pod count.
3. **Linearizable policy transitions per key:** policy updates and permit grants are atomically ordered together, so once an update commits, subsequent permit grants for that key use the new policy.

Level 2 **does not automatically imply** Level 3 if pods pass old policy parameters into the shared gate. And Level 3 **per key** does not guarantee multiple keys update at the exact same instant cluster-wide.

If the business allows only tiny quota error, the design must state the maximum error bound. If a **strict ceiling** is required, never use a mechanism that only guarantees eventual consistency for permit decisions.

## 4. Designing Stable and Bounded Quota Keys

A bucket key should accurately represent the quota, for example:

~~~text
stock.read:GLOBAL
stock.read:TENANT_GROUP_A
pricing.read:REGION_APAC
~~~

Do not use full URLs with query parameters, SKUs, `requestId`, or `correlationId` as keys; turning every request into its own bucket makes the limiter **limit nothing** and bloats memory.

For multi-tenancy:

- Derive tenant context from **authenticated identity**, never trust a self-supplied `tenantId` header.
- Choose buckets according to **provider policy**: global quota uses `GLOBAL`, per-tenant quota partitions by tenant.
- Large tenants may use dedicated buckets; small tenants share `SHARED` buckets if within the same quota domain.
- **Bucket scope does not replace authorization**; data/caches must still be authorized separately.
- Keys and metric labels must not contain emails, tokens, secrets, or very high-cardinality identifiers.

If upstream enforces a **120/s total quota** plus a **50/s per-tenant quota for tenant A**, checking only tenant A's bucket is insufficient. You may need permits from **both the `GLOBAL` bucket and bucket A in one coordinated decision**. Deducting tokens sequentially without rollback/atomicity can misconsume permits or exceed quotas when pods race.

## 5. Comparing Multi-Instance Execution Architectures

| Architecture | Pros | Risks and conditions of use |
| --- | --- | --- |
| **Per-pod local limiter** | Very fast, zero network hops | Valid only for **per-pod** quotas; cluster-wide quota scales by N |
| **Static per-pod quota split** | Simple for fixed pod counts | Skewed load, autoscaling, or pod churn wastes capacity or overruns quota |
| **Shared atomic bucket** | Pods share the same budget per key | Adds network/store latency; needs HA and failure policy |
| **Per-pod token leasing** | Reduces round-trips to shared store | Error from granted-but-unused tokens; needs lease/expiry and over-allocation guards |
| **Centralized quota gateway** | Enforces at one clear choke point | All paths must pass through the gateway; gateway needs HA and no bypasses |
| **Sharding by key** | Spreads load across many independent keys | Hot keys, shard migrations, and key mapping need control |

For example, **3 pods × 120 permits/s** is simply three local limiters, not one cluster-wide limiter. Statically splitting **40 permits/s/pod** is also imperfect: if 90% of traffic hits pod A, pod A rejects even while the other two pods have idle quota. Scaling to four pods changes the total quota unless re-partitioned consistently.

A **shared atomic bucket** is usually the clearest way to enforce exact limits **per key**, provided every request uses the same key and the same atomic execution point.

## 6. How Atomic Must a Shared Token Bucket Be?

A token bucket holds at least:

~~~text
bucketKey        = stock.read:GLOBAL
capacity         = 120 tokens
refillTokens     = 120
refillPeriod     = 1000 milliseconds
tokens           = current available tokens (may be fractional depending on model)
lastRefillAt     = timestamp of last update
policyVersion    = 42
~~~

On each call with **cost = 1**, the backend must execute **read state → refill → check → deduct token → persist result** inside **one atomic operation** on the same bucket.

~~~text
Atomic acquire(bucketKey, cost):

1. Obtain authoritative time from a trusted backend clock.
2. Read active policy and bucket state within the same consistency domain.
3. elapsed = max(0, now - lastRefillAt)
4. tokens = min(capacity,
                oldTokens + elapsed * refillTokens / refillPeriod)
5. If tokens >= cost:
       tokens = tokens - cost
       allowed = true
   Else:
       allowed = false
       compute retryAfter from missing token fraction.
6. Persist tokens, timestamp, and applied policyVersion.
7. Return decision + policyVersion + retryAfter (if rejected).
~~~

This is **algorithmic pseudocode**, not a verbatim runnable Redis script. In real implementations, use an atomic primitive suited to the backend, such as a **Redis Lua script** or transactions/CAS on a store with clear semantics. With Redis Cluster, keys accessed by one script must share **the same hash slot**; never assume a script is atomic across arbitrary keys on different shards.

### 6.1. Race Condition When Non-Atomic

Suppose the bucket has only **1 token** left. Two pods read concurrently:

~~~mermaid
sequenceDiagram
    participant A as Pod A
    participant S as Shared store
    participant B as Pod B
    A->>S: Read tokens = 1
    B->>S: Read tokens = 1
    S-->>A: 1
    S-->>B: 1
    A->>S: Write tokens = 0, ALLOW
    B->>S: Write tokens = 0, ALLOW
    Note over A,B: Two ALLOWs despite only 1 token
~~~

The fix is letting the store **serialize permit grants**, rather than having each pod read and write independently. When executed properly, only **one pod** receives ALLOW and the other receives REJECT.

### 6.2. Whose Clock Is Used?

If each pod uses its local clock to refill, pods can drift apart. Callers could also exploit clock skew to claim tokens early. Use **time managed by the permit-granting backend** or a trusted shared time source, with rules for backward clock jumps and migrations.

Even with server time, understand failover, clock adjustments, and internal math. Calls with varying costs should be decided in one clearly defined unit, avoiding floating-point rounding causing quota overruns.

## 7. Dynamic Configuration Must Have Versioning, Validation, and Audit

A policy snapshot may carry these fields:

~~~yaml
policyId: stock-read-global
version: 42
scope: stock.read:GLOBAL
algorithm: TOKEN_BUCKET
capacity: 120
refillTokens: 120
refillPeriodMillis: 1000
rejectPolicy: FAIL_FAST
effectiveAt: "2026-11-21T10:00:00Z"
updatedBy: rate-admin-service
changeReason: "Align upstream quota"
~~~

This is an **example business schema**, not default Spring Integration or Resilience4j configuration. A real policy must specify effective time, timezone, quota dimensions, and value bounds.

Before accepting a change, validate:

- **capacity > 0**, valid refill tokens and period; avoid division by zero or overflow.
- Declared scope and valid authorization; never create arbitrary keys from request data.
- Monotonically increasing version, with **compare-and-swap** or expected-version preconditions.
- Unambiguous effective window; snapshot carries source, timestamp, approver, and reason.
- When sharply lowering quota, plan for in-flight traffic and remaining tokens.
- When raising burst, check actual limits permitted by upstream.
- When switching **algorithms** (token bucket to rolling window), plan state migration instead of mixing two semantics.

### 7.1. Update Ordering and Preventing Stale Overwrites

Suppose the control plane emits **v42**, followed by **v43**, yet one pod receives the v43 event before v42. If the pod blindly overwrites config on every event, it can **regress to an older version**.

Safety rules:

1. Snapshots carry a monotonic **version/generation**.
2. Pods only install a snapshot newer than their current one.
3. On missed events, periodically fetch the authoritative version to reconcile.
4. Use **atomic replacement** of the whole snapshot, never updating capacity/refill field by field.
5. Expose **`current_policy_version`** and **`config_age`** to spot lagging pods.
6. If the permit-granting backend holds the authoritative policy, pods must not pass stale local policy values to force grants under v42.

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant P as Policy service
    participant S as Shared quota backend
    participant A as Pod A
    participant B as Pod B
    O->>P: Update v42 -> v43
    P->>S: Publish authoritative policy v43
    S-->>P: Confirm commit
    P-->>O: Applied v43
    P-->>A: Notify v43
    P-->>B: Notify v43
    Note over B: Event delayed or lost
    B->>P: Periodic reconciliation
    P-->>B: Snapshot v43
    Note over S: Permits use authoritative policy
~~~

**Note:** "publish authoritative policy" in the diagram must have clear commit semantics with the quota-enforcing backend. If the policy store and limiter state are two systems without a shared transaction, publishing v43 and hoping every permit issuer switches instantaneously is too strong a promise. You need a rollout/versioned-acquire protocol or an explicitly defined eventual-consistency window.

## 8. Changing Capacity and Refill While the Bucket Holds Tokens

Dynamic configuration is not simply changing two numbers on an object. The bucket already holds state from the old policy.

Suppose v42 had **capacity = 120** with **90 tokens** remaining; v43 lowers capacity to **40**.

If only the capacity field changes while keeping `tokens = 90`, the system can immediately grant **90 permits** after the update even though the new policy caps burst at 40. An explicit migration rule is needed:

~~~text
When applying a new policy under the bucket's lock/transaction:

1. Refill old state up to transition time using the old policy.
2. Replace policyVersion and new parameters.
3. Clamp tokens = min(tokens, newCapacity).
4. Persist state and version atomically.
5. Subsequent acquires after commit use the new policy.
~~~

This is **one illustrative transition policy**. Depending on the business contract, you might **reset the bucket to 0** when sharply cutting quotas to prevent bursts, or keep partial credit. There is no single default migration behavior fitting all applications.

| Change | Decision to document explicitly |
| --- | --- |
| Increase capacity | Allow accumulating tokens up to the new cap immediately or gradually? |
| Decrease capacity | Clamp tokens; must all prior credit be cleared? |
| Decrease refill rate | From what exact timestamp does the new rate take effect? |
| Switch rolling-window to token-bucket | How is state converted; is there a dual-run phase? |
| Delete per-tenant quota | When are old buckets and audit data cleaned up? |
| Roll back v43 to v42 values | Create **v44** with old values; do not replay an older version number |

**An update cannot revoke requests already permitted and executing.** If dropping from 120 to 40 req/s, calls that passed the limiter before commit can still finish afterward. If the goal is reducing concurrency immediately, add a separate bulkhead/cancellation mechanism; a rate limiter does not cancel in-flight calls.

## 9. Consistency Level: Strict Exactness or Bounded Error?

A shared atomic store serializes permits for **one bucket**, yet adds a network round-trip per request. At very high load, consider granting per-pod **token leases**.

For example, the backend holds 120 tokens; it atomically allocates 20 tokens to Pod A, 20 to Pod B, and 20 to Pod C. Each pod consumes its leased tokens locally without calling the backend every time. When a lease runs out, the pod requests more.

Pros: lowers latency and backend load. Trade-offs:

- Granted-but-unused tokens tie up budget; other pods may run short of quota.
- When lowering capacity, old leases remain valid; without revocation or blocking, the new threshold can be exceeded.
- Pod crashes strand leased tokens until expiry; an expiry/reclaim policy is required.
- If the backend becomes unreachable, each pod can keep spending valid leased tokens; total limits hold only up to granted budgets and lease semantics.
- Define the **maximum error / transition lag** in terms of outstanding leases and lease TTL.

**Never claim per-pod leases are immediately strongly consistent** while stale tokens remain spendable. When upstream enforces hard quotas whose violation suspends accounts, prefer shared atomic permits or a solution with a proven upper bound.

### Multiple Quota Layers

A provider may simultaneously limit:

- 120 req/s system-wide.
- 40 req/s for tenant A.
- 10 in-flight requests for one operation.

Rate limiters and **bulkhead/concurrency limiters** play different roles. When multiple buckets must be enforced in **a single decision**, prevent races where global and tenant permits are partially deducted; use a backend supporting transactions/atomic scripts within one data domain or a coordinating quota service.

## 10. Java Example: Atomically Updated Config Snapshot

A pod needs to read a stable policy snapshot for display or logging, yet should never use a local snapshot to issue **cluster-wide permits** when the contract demands exact limits.

The example below manages snapshots **only on the control-plane view of a single pod**. Common imports are omitted.

~~~java
public record RatePolicy(
        String scope,
        int capacity,
        int refillTokens,
        Duration refillPeriod
) {}

public record PolicySnapshot(
        long generation,
        Map<String, RatePolicy> policies
) {}

@Component
public final class PolicyView {

    private final AtomicReference<PolicySnapshot> current =
            new AtomicReference<>(
                    new PolicySnapshot(0L, Map.of())
            );

    public boolean install(PolicySnapshot incoming) {
        validate(incoming);
        for (;;) {
            PolicySnapshot previous = current.get();

            // Prevent late events from overwriting a newer snapshot.
            if (incoming.generation() <= previous.generation()) {
                return false;
            }
            if (current.compareAndSet(previous, incoming)) {
                return true;
            }
        }
    }

    public PolicySnapshot snapshot() {
        return current.get();
    }

    private void validate(PolicySnapshot incoming) {
        if (incoming == null || incoming.generation() <= 0
                || incoming.policies() == null) {
            throw new IllegalArgumentException("Invalid policy snapshot");
        }
        for (RatePolicy policy : incoming.policies().values()) {
            if (policy == null || policy.scope() == null
                    || policy.capacity() <= 0
                    || policy.refillTokens() <= 0
                    || policy.refillPeriod() == null
                    || policy.refillPeriod().isZero()
                    || policy.refillPeriod().isNegative()) {
                throw new IllegalArgumentException("Invalid rate policy");
            }
        }
    }
}
~~~

Key points:

1. **`AtomicReference`** swaps **the entire snapshot** in one step, preventing reading a new capacity with an old refill rate.
2. Older versions are ignored, even if notifications arrive out of order.
3. **`PolicyView` is not a distributed limiter**. Two pods with identical `PolicyView` instances will still exceed the total quota if using local buckets.
4. For production data, **immutably copy** the `policies` map before publishing the snapshot and thoroughly validate keys/scopes so external code cannot mutate the Map through a retained mutable reference.
5. Config sources should support fetch/reconcile and authorization checks; `install()` only demonstrates the single-pod mechanism.

A config change is considered applied system-wide only when it satisfies the chosen semantics at the authoritative backend, not merely because one Pod's `install()` returned `true`.

## 11. Spring Integration Java DSL with a Shared Rate Gate

The following example applies rate limiting **at the egress handler**, right before calling the Stock API. `SharedRateGate` is an application abstraction; a real implementation must acquire permits atomically from a shared backend using **the authoritative policy**. The Java snippet shows EIP integration without pretending an in-memory class is a distributed token bucket.

### 11.1. Request and Permit Contracts

~~~java
public record VerifiedStockRequest(
        String tenantGroup,
        String sku,
        String requestId
) {}

public record StockOutcome(
        String requestId,
        String status,
        Integer availableUnits,
        Long retryAfterMillis
) {}

public enum PermitStatus {
    ALLOWED,
    REJECTED,
    STORE_UNAVAILABLE
}

public record PermitDecision(
        PermitStatus status,
        long appliedPolicyVersion,
        long retryAfterMillis
) {}

public interface SharedRateGate {
    // Implementation must read policy + bucket from the same authoritative source.
    PermitDecision acquire(String bucketKey, int cost);
}

public interface StockClient {
    int availableUnits(String tenantGroup, String sku);
}

public class RateGateUnavailableException extends RuntimeException {
    public RateGateUnavailableException(String message) {
        super(message);
    }
}
~~~

`VerifiedStockRequest` should only be constructed after ingress verifies identity, tenant, and operation. Never trust a caller-supplied `tenantGroup`. `requestId` serves tracing/idempotency if needed by business logic, never as a bucket key.

### 11.2. Service Activator Acquiring a Permit Before Calling Upstream

~~~java
@Component
public class RateLimitedStockService {

    private final SharedRateGate rateGate;
    private final StockClient stockClient;

    public RateLimitedStockService(
            SharedRateGate rateGate,
            StockClient stockClient
    ) {
        this.rateGate = rateGate;
        this.stockClient = stockClient;
    }

    public StockOutcome lookup(VerifiedStockRequest request) {
        String bucketKey =
                "stock.read:" + request.tenantGroup();

        // All pods call the same authoritative gate with the same bucketKey.
        PermitDecision decision = rateGate.acquire(bucketKey, 1);

        if (decision.status() == PermitStatus.REJECTED) {
            return new StockOutcome(
                    request.requestId(),
                    "RATE_LIMITED",
                    null,
                    decision.retryAfterMillis()
            );
        }
        if (decision.status() == PermitStatus.STORE_UNAVAILABLE) {
            // Failure policy must be defined explicitly;
            // never default to ALLOW when the backend returns no decision.
            throw new RateGateUnavailableException(
                    "Shared quota backend unavailable"
            );
        }

        int units = stockClient.availableUnits(
                request.tenantGroup(),
                request.sku()
        );

        return new StockOutcome(
                request.requestId(),
                "FRESH",
                units,
                null
        );
    }
}
~~~

Never let a `STORE_UNAVAILABLE` request fall through into `StockClient` simply because an `if` branch checked only `REJECTED`. Outages of the permit store require an explicit **failure policy**.

When the rate gate returns `REJECTED`, `StockClient` must not be called. That is the **most important assertion** in testing. A call that received a permit yet timed out at the Stock API still spent its permit under a "one token per attempt" policy, unless the backend defines an explicit conditional refund mechanism; never auto-refund tokens because a client lost a response.

### 11.3. Wiring with Gateway and IntegrationFlow

~~~java
@MessagingGateway(defaultRequestChannel = "stock.lookup.requests")
public interface StockGateway {
    StockOutcome lookup(VerifiedStockRequest request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockRateFlowConfiguration {

    @Bean
    public IntegrationFlow stockLookupFlow(
            RateLimitedStockService service
    ) {
        return IntegrationFlow.from("stock.lookup.requests")
                .handle(
                        VerifiedStockRequest.class,
                        (request, headers) -> service.lookup(request)
                )
                .get();
    }
}
~~~

The synchronous Gateway receives a `StockOutcome` with status `FRESH` or `RATE_LIMITED`, or a technical exception if the rate gate is unavailable. The REST boundary can map `RATE_LIMITED` to **HTTP 429** with an appropriate `Retry-After`, yet that is an **API-layer contract**, not Spring Integration turning the result into 429 automatically.

In asynchronous flows, rejected messages can route to a **discard/rejected channel** or a durable queue with TTL. Never let a `Filter` return `false` and drop messages without an outcome and audit when business reconciliation is required.

**Invoke `SharedRateGate` only once at the right egress point.** If Gateway, Filter, and Service Activator all deduct from the same bucket for one HTTP attempt, quota gets double-counted. If you genuinely want separate limits for **logical requests** and **physical outbound calls**, use two buckets with distinct names, goals, and metrics.

## 12. Config Updates and Permit Decisions Must Be Unified

A common design bug:

1. Pod A has read **v43 (60 req/s)**.
2. Pod B still holds **v42 (120 req/s)**.
3. Both pods send `acquire` commands to the backend accompanied by capacities they computed locally.
4. The backend blindly accepts whichever parameters arrived last.
5. The system "oscillates" policies backward between 60 and 120.

**Never let pods dictate authoritative policy merely by sending a capacity field along with requests.**

A better protocol:

- **Backend stores `policyVersion`** and active parameters alongside the bucket or within the same valid transaction domain.
- **`acquire(bucketKey, cost)`** reads the authoritative policy itself and returns `appliedPolicyVersion`.
- If the design asks callers to send `expectedVersion`, the backend **refuses to issue permits under stale versions** and returns `CONFIG_STALE` so the caller refreshes (bounded) or evaluates under the new policy.
- Policy changes and bucket state migrations are serialized with `acquire` **on the same key**.
- Local `PolicyView` serves observability or decisions not affecting hard quotas; it never overrides the backend's decision.

A v43 update committed **within the bucket's domain** establishes a clear order: acquires before commit use v42, acquires after commit use v43. **HTTP requests permitted before commit may continue running**, and requests to other buckets may see the new version at different instants unless a multi-key coordination protocol exists.

## 13. Network Failures, Failover, and Choosing Fail-Open / Fail-Closed

If the shared permit store times out, that is **not** a normal `REJECT` response. The caller **does not know** whether a token was deducted when the connection dropped mid-request. Handle ambiguous outcomes explicitly rather than retrying infinitely.

| Policy | Pros | Risks |
| --- | --- | --- |
| **Fail closed** | Never exceeds quota when undecided | Rejects even valid traffic when the store fails |
| **Fail open** | Preserves availability | Can exceed upstream quota, risking contract or security issues |
| **Bounded local fallback** | Serves bounded partial traffic | Must prove worst-case quota error; hard to keep synchronized |
| **Queue/defer** | Avoids losing deferrable work | Increases backlog; needs TTL, backpressure, and DLQ |

No single choice fits every endpoint:

- **APIs whose accounts get suspended on quota overruns:** lean toward fail closed or tightly bounded failover.
- **Non-critical telemetry:** may accept fail open with supplemental quotas/alerts if risk is approved.
- **Asynchronous notifications:** can durably defer instead of blocking workers on the store.
- **Payments or guaranteed data:** never silently turn limiter failures into successes.

### 13.1. Should an Ambiguous Acquire Be Retried?

Suppose the backend deducted a token yet the response to the pod was lost. If the pod retries **the same acquire**, the backend may deduct a token a second time. That causes **under-utilization** and rate-limits callers prematurely, though it does not exceed the quota directly.

If exactness per logical attempt is required, design an **idempotency key** for `acquire` and retain decisions for an appropriate window with a clear deduplication scope. However, this adds state overhead and must distinguish retrying the same permit call from **a fresh HTTP attempt** that ought to consume a fresh permit.

Never assume **exactly-once** merely from calling Redis Lua or using a queue. Atomicity of permit issuance differs from end-to-end flow idempotency.

### 13.2. Redis Failover and Redis Cluster

Redis/Lua can ensure script atomicity within the right node/key scope, yet you must evaluate **persistence, replication, failover, and split-brain** before promising never to exceed quota across all failures. A primary that just granted tokens before replicating to a replica that then promotes during failover can lose updates if the architecture lacks the necessary durability/consistency guarantees.

For **strict quotas with severe consequences**, choose a backend/protocol with matching guarantees, test failovers, and document failure conditions. "Using Redis" does not automatically imply strong consistency across every network partition.

## 14. Retry, Backpressure, Circuit Breaker, and Handling 429

A rate limiter returns `REJECTED` because **budget is exhausted**, whereas a circuit breaker is `OPEN` because **the dependency is failing or slow**. Distinguish them in metrics and responses:

| Component | Decision | Typical response |
| --- | --- | --- |
| **Rate limiter** | No permits remaining | `RATE_LIMITED`, `retry-after` if computable |
| **Circuit breaker** | Calls blocked due to failure state | `BREAKER_REJECTED` / `UNAVAILABLE` |
| **Bulkhead** | No concurrency slots remaining | `BUSY` / `CONCURRENCY_LIMIT` |
| **Retry** | Bounded retry for transient errors | Attempts/backoff within deadline |
| **Fallback** | Degraded result when dependency is unavailable | `STALE_REFERENCE` / `UNAVAILABLE` |

When the rate limiter returns `RATE_LIMITED`:

- **Do not retry immediately in the same handler** just to grab a token; that creates a hot loop.
- For REST callers, return 429 with standardized contract-compliant `Retry-After`.
- For async messages, reschedule via a delayed queue/poller if TTL and attempt budget remain.
- For synchronous Gateways, avoid long sleeps waiting for permits that tie up threads and breach caller deadlines.
- If fallback caching is allowed, label stale data clearly; never return a fake 200 "fresh."
- If a request passed the limiter and the client timed out, retries may require a **new permit** depending on the physical quota unit; align policy before wrapping Retry around the gate.

### 14.1. Ordering Limiter and Retry

~~~mermaid
flowchart LR
    A[Gateway] --> B[Bounded Retry]
    B --> C[Shared rate gate]
    C -->|ALLOW| D[Stock Client]
    C -->|REJECT| E[Do not retry immediately]
~~~

With this layout, every attempt passes through the gate and can consume a permit. Placing the gate outside Retry allows **one permit to cover multiple HTTP attempts**, violating physical-call provider quotas. Pick the order based on **how the provider counts quota** and test actual HTTP attempt counts.

If a request expands via a Splitter into multiple calls, every outbound branch must evaluate its corresponding quota. With an Aggregator, when one branch gets `RATE_LIMITED`, define partial/timeout/error paths so the group does not hang forever, preserving correlation IDs and sequence headers.

## 15. Safe Rollout When Changing Production Policies

A reliable change process:

1. **Define scope and SLO:** is quota per logical request or HTTP attempt; is a hard cap required?
2. **Assess impact:** will lowering quota spike rejections/queues or breach deadlines?
3. **Validate schema + permissions:** which scopes may the updater modify, and are parameters valid?
4. **Prepare:** create a new version; verify bucket migration, capacity/refill, and error policies.
5. **Commit authoritatively:** backend makes the change effective at a well-ordered point.
6. **Distribute & reconcile:** pods receive notifications, install versioned snapshots, and fetch missed updates.
7. **Observe:** policy version state, allowed/rejected, store latency, config lag, upstream 429s, queue age.
8. **Roll back via a new version:** if v43 is faulty, publish v44 with verified values rather than rewinding version numbers.
9. **Audit:** record who made the change, when, reason, scope, before/after values, and rollout outcome.

When updating multiple buckets or regions simultaneously, define what "complete" means: **request accepted**, **policy stored**, **committed on one shard**, or **active on every shard**. Never collapse all those states into a single "SUCCESS" word.

### Rollback Does Not Erase Already-Issued Permits

Lowering quotas or rolling back cannot recall requests already sent. Therefore dashboards should include **`policy_version`** at decision time alongside migration events to separate ALLOWs under v42 from v43 within the same window.

## 16. Testing Dynamic Configuration and Multi-Instance Consistency

### 16.1. Unit Test: Local Snapshot Rejects Out-of-Order Older Versions

~~~java
@Test
void ignoresOutOfOrderPolicySnapshots() {
    PolicyView view = new PolicyView();

    RatePolicy v2Policy = new RatePolicy(
            "stock.read:GLOBAL", 60, 60, Duration.ofSeconds(1)
    );
    RatePolicy v1Policy = new RatePolicy(
            "stock.read:GLOBAL", 120, 120, Duration.ofSeconds(1)
    );

    assertTrue(view.install(new PolicySnapshot(
            2L, Map.of("stock.read:GLOBAL", v2Policy)
    )));
    assertFalse(view.install(new PolicySnapshot(
            1L, Map.of("stock.read:GLOBAL", v1Policy)
    )));

    assertEquals(2L, view.snapshot().generation());
    assertEquals(
            60,
            view.snapshot().policies()
                    .get("stock.read:GLOBAL").capacity()
    );
}
~~~

This test only verifies **atomic local snapshots and monotonic versions**. It **does not test cluster-wide quotas**.

### 16.2. Testing with a Shared Fake Gate

To illustrate **multiple callers sharing one budget**, a synchronized fake can use a shared counter. This test does not replace Redis/SQL backend tests.

~~~java
@Test
void concurrentCallersDoNotExceedSharedPermitBudget()
        throws Exception {
    AtomicInteger remaining = new AtomicInteger(5);
    AtomicInteger allowed = new AtomicInteger();
    ExecutorService workers = Executors.newFixedThreadPool(10);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<?>> jobs = new ArrayList<>();

    try {
        for (int i = 0; i < 20; i++) {
            jobs.add(workers.submit(() -> {
                start.await();

                for (;;) {
                    int before = remaining.get();
                    if (before <= 0) {
                        return null;
                    }
                    if (remaining.compareAndSet(before, before - 1)) {
                        allowed.incrementAndGet();
                        return null;
                    }
                }
            }));
        }
        start.countDown();

        for (Future<?> job : jobs) {
            job.get();
        }
        assertEquals(5, allowed.get());
        assertEquals(0, remaining.get());
    } finally {
        workers.shutdownNow();
    }
}
~~~

`AtomicInteger` here is merely a single-JVM fake, not cross-pod permit sharing. A real integration test must run multiple **processes/client connections** against **the same backend**, using controlled time/refills and verifying the backend never grants more than the bucket's permits.

### 16.3. Required Integration Test Matrix

| Scenario | Result to verify |
| --- | --- |
| 3 pods, same key, bucket holds 120 tokens, no refill during test | Total ALLOWs at most 120, not 360 |
| 3 pods, concurrent requests when 1 token remains | Only one permit is granted |
| Independent quota keys | Bucket A exhausting does not deduct tokens from bucket B |
| GLOBAL + tenant quota | Neither limit exceeded; multi-bucket deduction has proper atomicity |
| Pod receives v43 before v42 | Does not downgrade version |
| One pod misses config notification | Reconciliation pulls the newer version |
| Lower capacity 120 to 40 when bucket holds 90 tokens | State is migrated/clamped per chosen policy |
| Policy update while many acquires run | Acquires on a key are ordered relative to policy commit |
| Gateway receives REJECTED | `StockClient` is not called; outcome carries valid `retryAfter` |
| Shared store timeout | Fail-open/closed/defer matches policy; never treated as ALLOW |
| Acquire response lost | Retry/idempotency avoids unintended double token spend |
| Broker redelivery when rate-limited | No hot loop; backoff, TTL, DLQ present |
| HTTP retry after acquiring a permit | Consumed permits match attempts per contract |
| Splitter has a rejected branch | Aggregator does not hang; correlation preserved |
| Scale from 3 to 6 pods | Total quota does not double |
| Store failover or network partition | Quota guarantees/error bounds remain within commitment |
| Roll back v43 with v44 | Policy version never decreases; new rules take effect |
| Spoofed tenant header | Cannot create/select privileged buckets from unauthenticated data |

**Do not test only inside one JVM.** Test real contention across instances, updates occurring mid-traffic, and backend failure handling. A test with a fake counter proves in-memory logic, not Redis Cluster or database behavior.

## 17. Metrics, Tracing, and Alerts

| Signal | Meaning |
| --- | --- |
| **`allowed` / `rejected` by bucket scope** | Are quotas and partitioning applied accurately? |
| **`applied_policy_version`** | Which policy version governed the acquire decision? |
| **`pod_policy_generation` / `config_lag`** | Which pods are lagging or out of sync? |
| **`shared_gate_latency` p95/p99** | Round-trip cost of the shared mechanism |
| **`quota_backend_error` / `timeout`** | Is the permit-issuing backend failing? |
| **Tokens remaining / utilization** | Do buckets frequently empty or sit mostly unused? |
| **Upstream HTTP 429 / 5xx** | Is the rate limiter preventing provider quota overruns? |
| **Gateway latency / `RATE_LIMITED` outcomes** | User-facing impact |
| **Retry attempts / delayed queue age / DLQ** | Are retry loops or backlogs growing? |
| **Aggregator pending/expired groups** | Are `RATE_LIMITED` branches leaving groups missing replies? |

Distinguish **limiter rejection**, **circuit-breaker rejection**, **bulkhead rejection**, and **upstream-returned HTTP 429**. They have different remediations. Correlation/trace IDs trace one message through Gateway, Router, Splitter, and error channel; never put individual IDs into metric tags.

Suggested alerts:

- Many pods stuck on an old **`policy_generation`** for a prolonged time.
- Total ALLOWs exceed committed quota scope or upstream continually returns 429.
- High **`shared_gate_latency`** pushing Gateway p99 past SLO.
- **`store_unavailable`** rising while the system stays in fail-open for too long.
- **`RATE_LIMITED`** spikes sharply after v43 rollout; oldest queue age exceeds TTL.
- One hot bucket key saturates a backend shard.
- Rejections rise with no version/decision logs to explain why.

Never use raw tenant IDs, SKUs, dynamic URLs, or `requestId` as metric labels when high-cardinality or sensitive. Use **`operation`**, **`tenant_group`**, **`region`**, and normalized bucket names; detailed logs/traces require access control.

## 18. Implementation Checklist

- [ ] Define quota by **logical request**, outbound attempt, tenant, or cluster-wide.
- [ ] Document burst, refill, cost, algorithm, and allowable consistency error.
- [ ] Never multiply a per-pod limiter by pod count and call it a global quota.
- [ ] Separate control-plane policy updates from data-plane atomic permits.
- [ ] Include policy **version/generation**, validation, authorization, audit, and rollback via new version.
- [ ] Config notifications have **reconciliation** and never downgrade to older versions.
- [ ] Bucket state and policy migration are serialized with acquires within each key.
- [ ] Pods use identical stable keys, deriving tenant context from trusted ingress.
- [ ] If using Redis/DB, verify atomicity, cluster hash slots, clocks, failover, and replication.
- [ ] If using leases/local fallback, bound max error, expiry, and outstanding tokens.
- [ ] Choose fail-open, fail-closed, or defer based on business impact, not accidental exception catching.
- [ ] Do not retry immediately on rejection; provide `retryAfter`/backoff, TTL, DLQ, and backpressure as needed.
- [ ] Deduct permits at the exact egress point without confusing rate limiters with bulkheads or circuit breakers.
- [ ] Gateway/error channel and Splitter/Aggregator preserve outcomes/correlation so no message is lost.
- [ ] Test multi-process/pod contention, hot reload, out-of-order config, quota reductions, and store outages.
- [ ] Observe version lag, accepted/rejected, store latency, upstream 429s, queue age, and caller impact.

**Dynamic configuration and multi-instance consistency** require getting two things right at once: **all policies are updated with versions and applied with clear semantics**, while **every cluster-wide permit decision is coordinated at a single authoritative source**. When this boundary is designed cleanly, Spring Integration can scale across pods without multiplying quotas per pod, still explain why any message was allowed or rejected, and maintain controlled processing with Gateway, Router, retry, error channel, and correlation.
