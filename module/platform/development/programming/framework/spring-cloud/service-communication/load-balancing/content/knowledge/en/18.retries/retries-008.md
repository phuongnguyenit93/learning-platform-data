# Retry-Aware Suppliers and Avoiding Recently Failed Instances

When `order-service` calls `inventory-service` through Spring Cloud LoadBalancer, the client may pick a `ServiceInstance` and encounter `connection refused`, a timeout, or an HTTP response that policy deems retryable. If the next attempt goes straight back to the exact same failing replica, retrying may simply add latency and keep piling load onto the broken instance.

Spring Cloud LoadBalancer provides a dedicated component for this situation: **`RetryAwareServiceInstanceListSupplier`**. Rather than performing retries itself, the supplier uses **context from the previous attempt** to prepare the candidate list for the **next selection**, preferring to exclude the previously selected instance when other replicas exist.

This lesson belongs to the **Retries** chapter in the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. We will separate retry policies from instance selection, explain the role of `ServiceInstanceListSupplier#get(Request)`, configure previous-instance avoidance, handle single-replica topologies, and test call paths with RestClient, WebClient, or OpenFeign. The goal is to protect business correctness when using retries/timeouts and observe per-replica errors accurately.

> Key point: **a retry-aware supplier is not a circuit breaker, does not generate extra HTTP requests on its own, and does not maintain a permanent blacklist**. It simply helps shape candidates for a re-selection when the retry integration passes the proper context and eligible alternatives exist.

## 1. The problem: the next attempt lands right back on the failing instance

Suppose `inventory-service` has three replicas:

| Instance | Address | Condition in example |
| --- | --- | --- |
| A | `10.0.1.11:8080` | Stopped accepting connections, yet discovery info is still stale |
| B | `10.0.1.12:8080` | Running |
| C | `10.0.1.13:8080` | Running |

`order-service` calls:

```http
GET /api/stocks/BOOK-001 HTTP/1.1
Host: inventory-service
Accept: application/json
```

Discovery or cache currently returns `[A, B, C]`. On the first attempt, LoadBalancer chooses A:

```text
Attempt 1
  Service ID: inventory-service
  Candidate list: [A, B, C]
  Selected instance: A (10.0.1.11:8080)
  HTTP outcome: Connection refused
```

A retry policy allows retrying this request. If the system simply re-runs selection over the exact same `[A, B, C]` list, **there is no guarantee** the new choice differs from A. An algorithm like Random can easily pick A again; Round Robin maintains its own selection state and should not be treated as a "remember failed instances" mechanism across all calls.

With a retry-aware supplier, the next selection can start from `[B, C]`:

```text
Attempt 2
  Previous ServiceInstance: A
  List from discovery: [A, B, C]
  List after retry-aware filtering: [B, C]
  Selected instance: C (10.0.1.13:8080)
  HTTP outcome: 200 OK
```

Filtering does not fix A, yet it **reduces the chance of immediately reusing the just-failed replica on the next attempt**.

## 2. Separating three decisions: whether to retry, whom to pick, and how to send

To understand `RetryAwareServiceInstanceListSupplier` properly, divide responsibilities into three steps:

1. **Retry policy:** decides whether an error qualifies for retry; enforces attempt limits, backoff, and deadlines.
2. **Instance supplier and LoadBalancer:** builds the candidate list, avoids the replica chosen on the prior attempt when possible, and selects a `ServiceInstance` for the new attempt.
3. **HTTP client/transport:** actually sends the request to the chosen address, waits for a response, enforces connect/read timeouts, and reports failures.

| Component | Primary responsibility | Should not be assigned to it |
| --- | --- | --- |
| Retry engine / `LoadBalancerRetryPolicy` | Decides whether to continue after failure; checks attempt counts and error type | Detecting registry updates or building zone metadata |
| `RetryAwareServiceInstanceListSupplier` | Adjusts the instance list using retry context | Issuing HTTP requests or deciding whether a business operation is safe to resend |
| `RoundRobinLoadBalancer` / other algorithm | Picks one instance from the supplier-provided list | Maintaining a "global bad-instance list" |
| `DiscoveryClient` | Supplies replicas known by discovery | Choosing a replacement instance for a specific attempt |
| RestClient / WebClient / OpenFeign | Executes HTTP via configured integration | Having identical built-in retry/load-balancing behavior across all versions |

**Do not equate "picking a different instance" with "permission to retry."** A side-effecting `POST` request may be unsafe to resend even when the supplier has multiple healthy replicas available.

## 3. High-level flow of a retried call

```mermaid
sequenceDiagram
    participant Caller as order-service
    participant Policy as Retry policy
    participant LB as Spring Cloud LoadBalancer
    participant Supplier as RetryAwareServiceInstanceListSupplier
    participant Discovery as Discovery supplier
    participant A as inventory-service A
    participant C as inventory-service C

    Caller->>Policy: GET /api/stocks/BOOK-001
    Policy->>LB: Select instance (attempt 1)
    LB->>Supplier: get(request with no previous instance)
    Supplier->>Discovery: Fetch candidate list
    Discovery-->>Supplier: [A, B, C]
    Supplier-->>LB: [A, B, C]
    LB-->>Policy: Selected A
    Policy->>A: HTTP request
    A--xPolicy: Connection refused
    Policy->>Policy: Check retry policy + deadline
    Policy->>LB: Select instance (attempt 2; previous=A)
    LB->>Supplier: get(request with retry context)
    Supplier->>Discovery: Fetch candidate list
    Discovery-->>Supplier: [A, B, C]
    Supplier-->>LB: [B, C] if alternatives exist
    LB-->>Policy: Selected C
    Policy->>C: HTTP request
    C-->>Policy: HTTP 200
    Policy-->>Caller: Final result
```

This diagram shows **one illustrative call flow** when the retry integration triggers a new selection and passes the previous instance. Exact callback ordering, HTTP client implementation details, and context storage can vary by Spring Cloud version. When retries are disabled or the failure is ineligible, only the initial attempt occurs.

## 4. At what boundary does RetryAwareServiceInstanceListSupplier operate?

In Spring Cloud LoadBalancer, `ServiceInstanceListSupplier` exposes two retrieval methods:

```java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
```

`get()` returns a list without needing information about the current request. `get(Request)` enables request-aware supplier layers: reading hints, sticky-session info, or **retry context**.

`RetryAwareServiceInstanceListSupplier` is a **decorator-style** supplier: it wraps another supplier, receives the candidate list, and applies logic related to the previously selected instance.

A conceptual stack:

```text
RoundRobinLoadBalancer
  |
  v
RetryAwareServiceInstanceListSupplier
  |
  v
Zone / health / hint suppliers (if configured)
  |
  v
CachingServiceInstanceListSupplier (if needed)
  |
  v
DiscoveryClientServiceInstanceListSupplier
```

Layer order can vary by configuration. For caching or health checks, Spring Cloud documentation recommends placing them near the network-facing discovery supplier, **before request-dependent filters**, to avoid caching request A's filtered output for request B.

During selection, the `Request` passed to the supplier **is not the server's HTTP response**. It is context constructed by the LoadBalancer/retry integration for replica selection—nor is it necessarily the full request body or business DTO.

## 5. What does retry context carry?

On the initial attempt, no instance has been chosen yet, so the retry-aware supplier typically has nothing to exclude.

Once an attempt fails and the retry engine decides to continue, the integration can pass information such as:

```text
serviceId = inventory-service
attemptIndex = 2                 // illustrative label for application logs
previousServiceInstance = A       // ServiceInstance from the prior attempt
```

**The key field is `previousServiceInstance`**, not merely a flag saying "request is retrying." A supplier trying to avoid A needs to know which candidate is A, rather than guessing from an exception disconnected from the previous attempt.

Across Spring Cloud versions, this context is supplied via corresponding request/retry context types. Avoid coupling directly to an internal context class without checking your version; in principle, the retry mechanism must pass enough context into `ServiceInstanceListSupplier#get(Request)`.

Key points to grasp:

- **The supplier does not track which HTTP requests failed on its own.** Errors are observed by the retry engine and HTTP client.
- **The supplier does not by default remember every instance that ever failed throughout a business request.** The standard mechanism primarily avoids the instance from the **immediately preceding selection**, rather than maintaining a multi-attempt failure set.
- **If a decorator drops the request context, retry-aware filtering may never receive the previous instance** and thus fail to work as intended.

## 6. Algorithm for avoiding the previous replica: a simple example

Imagine discovery returns `[A, B, C]` and the previous instance is A. Conceptual algorithm:

```text
function chooseCandidates(instances, previous):
    if previous is absent:
        return instances

    alternatives = instances excluding previous

    if alternatives is not empty:
        return alternatives

    return instances   # fallback when no other option exists
```

Behavior table:

| Pre-filter list | Previous instance | Expected candidate list |
| --- | --- | --- |
| `[A, B, C]` | None yet | `[A, B, C]` |
| `[A, B, C]` | A | `[B, C]` |
| `[A, B, C]` | B | `[A, C]` |
| `[A]` | A | `[A]`, since no other replica exists |
| `[B, C]` | A | `[B, C]`, since A is already gone from the list |
| `[]` | A | `[]`, since no targets exist to select |

**Single-instance fallback** is a crucial detail: if A is the sole replica, removing A yields an empty list. Previous-instance avoidance normally prefers an alternative **when available**, rather than promising never to pick A again.

This table is a learning model. Actual instance identity matching relies on the `ServiceInstance` structure and equality used by the library; when writing custom suppliers, pay close attention to `instanceId`, `host`, `port`, and how equality is defined.

## 7. Single-replica case: avoiding is not forbidding

Suppose staging runs only one replica:

```text
inventory-service -> A (10.0.1.11:8080)
```

Attempt 1 to A times out. If policy allows retrying, the supplier has no B or C to substitute. Two goals can collide:

1. **Resilience:** retry A if the glitch might be momentary.
2. **Load reduction / error containment:** stop hammering A if A is overloaded or persistently failing.

`RetryAwareServiceInstanceListSupplier` focuses on offering an alternative **when the list contains multiple instances**. It does not replace the retry decision itself. If retrying A is pointless, the retry policy, circuit breaker, health check, or deadline is the right place to cap attempts.

Therefore, "avoid-previous is enabled" **does not guarantee every attempt hits a different instance**, especially when zone/health/hint filtering leaves the supplier with only one candidate.

## 8. Difference between previous-instance avoidance and Round Robin

Round Robin cycles sequentially through whatever list it receives. Given a stable `[A, B, C]` list, consecutive selections on one LoadBalancer can produce `A → B → C → A`.

However:

- Round Robin **has no knowledge** of whether the prior request succeeded or failed from the algorithm alone.
- Multiple callers maintain separate load-balancing state; regular requests and retries interleave.
- List ordering can shift whenever registry, cache, zone, or health filtering updates.
- When retries and non-retries share one LoadBalancer, "the next element" is not guaranteed to be "a different replica from the failed attempt of this business request."

Retry-aware filtering injects **previous instance** information into candidate preparation before Round Robin picks from the filtered set. Thus it enforces "avoid A on the next attempt" far more reliably than hoping the algorithm's natural rotation happens to skip A.

## 9. Configuring previous-instance avoidance in Spring Cloud LoadBalancer

The relevant properties are:

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        avoid-previous-instance: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retry-on-all-operations: false
```

Meaning:

| Property | Configuration intent |
| --- | --- |
| `retry.enabled` | Enables LoadBalancer retry capability where integration/dependencies support it |
| `retry.avoid-previous-instance` | Enables wrapping the supplier with `RetryAwareServiceInstanceListSupplier` to prefer avoiding the previous instance when alternatives exist |
| `retry.max-retries-on-same-service-instance` | Retry count on the same instance per integration policy |
| `retry.max-retries-on-next-service-instance` | Retry count involving another instance selection |
| `retry.retry-on-all-operations` | Whether HTTP operations beyond the default safe operations are eligible for retry |

In current Spring Cloud Commons configuration docs, `retry.avoid-previous-instance` **defaults to `true`**. However, **a property's default does not mean every HTTP client always retries**: issuing retried requests also depends on integration, classpath, error policies, and related beans. In particular, across many versions, synchronous retry paths require appropriate Spring Retry components, whereas reactive paths use different activation and conditional retry mechanisms.

The example above sets `avoid-previous-instance: true` explicitly to show intent; do not assume you must manually re-enable a property already defaulted on. Property names use kebab-case; older versions may display camelCase in some documentation examples.

### 9.1. When to disable this behavior?

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        avoid-previous-instance: false
```

Disable it only with clear operational justification, such as a specialized policy requiring same-instance re-selection or a custom integration handling selection itself. **Disabling avoidance does not disable retries**; nor does it guarantee every attempt hits the same instance.

If you want to **disable LoadBalancer retries**, that is a separate decision from disabling previous-instance avoidance; inspect `retry.enabled` and retries at all other application layers.

### 9.2. Per-service configuration

An application may call multiple downstreams with different fault tolerances. Spring Cloud LoadBalancer supports per-client/service-ID configuration via client-scoped properties in supporting versions. Verify the active namespace—such as `spring.cloud.loadbalancer.clients.<clientId>...`—before applying.

Do not apply the exact same retry level across all services simply because `inventory-service` has many replicas. A slow reporting API or a state-mutating `POST` API needs a very different policy from a stock-reading `GET`.

## 10. Auto-configuration and custom suppliers

Spring Cloud LoadBalancer can **automatically wrap** an existing `ServiceInstanceListSupplier` with `RetryAwareServiceInstanceListSupplier` when the corresponding retry path is enabled. Exact conditions depend on blocking/reactive integration, dependencies, and framework version.

Therefore, in most applications:

1. Enable and configure retries properly for your HTTP client/integration.
2. Leave `avoid-previous-instance` enabled.
3. Verify the actual supplier chain includes the retry-aware layer.
4. Observe whether retries receive the previous-instance context.

**Do not manually wrap an extra retry-aware layer into a custom chain when auto-configuration already wraps it**, as this makes the chain confusing and risks creating the impression of two retry engines. Wrapping the supplier does not itself determine attempt counts, yet duplicate decorators complicate debugging and configuration.

### 10.1. Example of building a custom instance list source

If an application needs a custom chain, start from a list-fetching supplier and place filters appropriately. The example below **illustrates only the instance source**, without enabling retries itself:

```java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class InventoryInstancesConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
```

To scope this bean exclusively to service ID `inventory-service`, attach the config class with `@LoadBalancerClient(name = "inventory-service", configuration = InventoryInstancesConfiguration.class)` appropriately, while keeping the dedicated config class outside global component scanning so it is not applied everywhere accidentally.

When the discovery client already caches (such as certain Eureka setups), avoid adding `.withCaching()` unnecessarily; double caching can retain dead replicas longer. Especially, **cache the raw list before request-dependent filters** so attempt A's filtered results are never shared with attempt B.

When using custom configurations, verify **whether auto-configuration still applies the retry-aware decorator**. Do not assume every custom chain automatically receives the same wrappers as the default chain.

## 11. Preserving context across supplier layers

The crucial handoff is the call:

```java
delegate.get(request);
```

A request-agnostic decorator may still need to forward this context so inner layers receive retry information. Proper forwarding example:

```java
@Override
public Flux<List<ServiceInstance>> get(Request request) {
    return delegate.get(request);
}
```

If written mistakenly as:

```java
@Override
public Flux<List<ServiceInstance>> get(Request request) {
    return delegate.get(); // Drops context, potentially losing retry metadata
}
```

then a supplier needing `previousServiceInstance` will never receive it. Dangerously, the returned list still looks valid, yet previous-instance avoidance behaves unexpectedly.

Note: the two snippets above **illustrate decorator method bodies** assuming a `delegate` field, not standalone compilable classes. Source suppliers like cache/discovery do not need request context to run; however, when the chain is expected to pass requests to request-dependent filters, verify ordering and delegation so context is never dropped.

## 12. Do not turn a retry-aware supplier into a global blacklist

Right after A times out, it is tempting to "mark A bad and permanently remove A from the list." That is not `RetryAwareServiceInstanceListSupplier`'s job.

**Previous-instance avoidance** has a narrow scope:

- Tied to a **specific retry turn** and the immediately prior selected instance.
- Does not maintain global failure history by host, port, zone, or service ID.
- Does not perform health-check probes or TCP checks to prove A is dead.
- Does not exclude A from selections of **all other requests** as long as A remains in the instance source.

To curb traffic to failing replicas broadly, combine:

| Mechanism | Purpose |
| --- | --- |
| Discovery deregistration / lease | Updates topology when an instance leaves the system |
| Health-check supplier | Filters unhealthy instances via configured probes |
| Reasonable cache TTL/refresh | Prevents stale topology from lingering too long |
| Circuit breaker | Halts calls to a dependency once policy detects elevated failures |
| Bulkhead / concurrency limit | Contains cascading impact when downstream overloads |
| Retry-aware supplier | Discourages re-selecting the instance from the just-failed attempt |

These mechanisms complement one another; no single mechanism replaces the rest.

## 13. Interaction with zones, sticky sessions, and other filters

Suppose `inventory-service` has:

| Instance | Zone | Status |
| --- | --- | --- |
| A | `zone-a` | Just failed |
| B | `zone-a` | Healthy |
| C | `zone-b` | Healthy |

The caller runs in `zone-a` with `ZonePreferenceServiceInstanceListSupplier` enabled. After zone preference, the list may be `[A, B]`. If the retry-aware filter receives `previous=A`, `[B]` remains.

Now suppose **only A is in `zone-a`** and C is in `zone-b`. If zone preference already narrowed the list to `[A]` before retry-aware filtering ran, the supplier sees only one candidate and falls back to A. To fail over to C, design the supplier chain and zone policy accordingly instead of assuming retry-aware filtering can reach outside whatever list its delegate returns.

Similarly, with **sticky sessions**, the system may prefer the previous instance due to local session state. "Stick to the same instance" and "avoid the just-failed instance" can conflict. Decide layer precedence explicitly: does availability or affinity win, and can the application tolerate moving a session to another replica?

**`RetryAwareServiceInstanceListSupplier` can only choose from the list provided by its delegate.** It cannot resurrect replicas removed by another filter, nor widen zones across regions if configuration forbids it.

## 14. Retrying after multiple failures: not a list of all tried instances

Consider `[A, B, C]`:

```text
Attempt 1: pick A -> timeout
Attempt 2: previous=A -> may pick B -> timeout
Attempt 3: previous=B -> may pick A or C
```

If the mechanism only avoids the **immediate previous instance**, by attempt 3 A can reappear in the candidate pool. **Do not assume the order will be A → B → C** or that every instance is tried exactly once.

If a requirement demands trying distinct replicas without repetition across one business request, that is an advanced custom policy:

- Track the set of already-tried instances in per-request context.
- Forward that context properly on every selection.
- Define behavior once every instance has been tried.
- Enforce attempt caps and deadlines.
- Verify interactions with zone, sticky, health, and selection policies.

By default, Spring Cloud LoadBalancer supports avoiding the previous instance as described; do not assume a built-in blacklist history across the entire retry chain.

## 15. Same instance and next instance: understanding the limits

Two configuration groups must be read together:

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
```

By intent, these settings disable same-instance retries and allow one retry with a newly selected instance on supporting integrations.

However, **"next service instance" is not a fixed distinct address**. Selection still operates over whatever list the supplier returns. When no alternative exists, the algorithm may return the old instance depending on candidates and fallback. Always test actual attempts and selected instances rather than guessing from property names.

Distinguish:

| Aspect | Same-instance retry | Next-instance retry |
| --- | --- | --- |
| New instance selection? | May not be needed | Typically runs a new selection |
| Can move off failing replica? | No, intentionally keeps it | Yes, if supplier/LoadBalancer has another candidate |
| Avoids overloaded server faults? | Can increase load directly on the failing replica | Can spread to another replica, though increases total load |
| Still needs timeouts? | Yes | Yes |
| Still needs write idempotency? | Yes | Yes |

The word "retry" does not prove a request will be resent exactly once. A client combining Spring Cloud LoadBalancer, HTTP transport, and application layers can have distinct retry policies, resulting in **multiplied attempts** if not coordinated.

## 16. Retry only recoverable errors and safe requests

Avoiding A after an error helps only when resending the request **is permitted** and has a chance of succeeding on another replica.

| Prior attempt outcome | Retry eligibility | Reason |
| --- | --- | --- |
| `GET` hits connection refused | Can retry with limits | Replica may have stopped listening; trying another instance helps |
| `GET` receives transient `503` | Can retry with backoff | Downstream may be overloaded; avoid retry storms |
| `GET` receives `429` | Honor `Retry-After` and deadline | Quota may apply service-wide, not per replica |
| `GET` receives `404` for missing SKU | Usually do not retry | Switching instances won't create a missing resource |
| Stock-reserving `POST` hits read timeout | Do not retry blindly | Server may have already executed the operation |
| `POST` with server-enforced idempotency key | Can retry with limits | Server must prevent duplicates across replicas |
| `400` from invalid input data | Do not retry | Switching replicas won't fix the payload |

**The retry policy decides which errors can retry; the retry-aware supplier only shapes the instance list for an already-permitted attempt.** Pair with an overall deadline and jittered exponential backoff, especially when many callers can hit the same incident.

## 17. Application example: WebClient calling by service ID

A `@LoadBalanced` `WebClient.Builder` is a common integration point:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

A client built from this builder can call a logical URL:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class InventoryGateway {

    private final WebClient client;

    InventoryGateway(@LoadBalanced WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    Mono<StockResponse> findStock(String sku) {
        return client.get()
                .uri("/api/stocks/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
```

Here `StockResponse` is an application-defined DTO. **This code alone does not prove retries are active**: it builds a client capable of instance selection once Spring Cloud LoadBalancer and discovery are configured. Retry policies must be enabled appropriately for your version/integration and verified with actual attempts.

To enforce an overall pipeline deadline, apply `.timeout(Duration.ofSeconds(...))` at the appropriate caller boundary. Do not add `retryWhen(...)` while also enabling LoadBalancer retries without recalculating max attempts, as the two retry layers can stack.

## 18. How do RestClient and OpenFeign differ?

With `RestClient`, you typically configure `@LoadBalanced RestClient.Builder` to resolve instances by service ID. Processing is **blocking**; retry support depends on Spring Retry components and the integration in use.

With OpenFeign, `@FeignClient(name = "inventory-service")` can use Spring Cloud LoadBalancer when no physical URL overrides it. However, **OpenFeign's `Retryer` and Spring Cloud LoadBalancer's retry are not the same mechanism**. In many Spring Cloud OpenFeign versions, `Retryer.NEVER_RETRY` is Feign's default; do not assume LoadBalancer configuration automatically creates every Feign retry as expected.

| Client | How service ID is specified | What to verify when retrying |
| --- | --- | --- |
| RestClient | HTTP URL via `@LoadBalanced` builder | Retry integration, Spring Retry if needed, beans/transport, policy |
| WebClient | HTTP URL via `@LoadBalanced` builder | Reactor retry/filter, request context, avoiding double retries |
| OpenFeign | `@FeignClient(name = "...")`, no physical URL | Feign Retryer, LoadBalancer integration, exception/status policy |

When suspecting the retry-aware supplier is not being used, confirm **the HTTP client actually goes through Spring Cloud LoadBalancer**. For instance, a Feign client configured with `url = "http://10.0.1.11:8080"` bypasses service-ID replica selection unlike declaring a name without a fixed URL.

## 19. Observing retry-aware filtering attempt by attempt

To verify configuration works, log with a trace ID and attempt index while distinguishing data sources:

```text
traceId=f31a... serviceId=inventory-service attempt=1
discoveryCandidates=[A,B,C] selected=A
httpResult=CONNECT_REFUSED

traceId=f31a... retryAllowed=true remainingBudgetMs=1450
traceId=f31a... serviceId=inventory-service attempt=2 previous=A
discoveryCandidates=[A,B,C] retryEligibleCandidates=[B,C]
selected=C httpStatus=200
businessOutcome=SUCCESS
```

Log field names in this example are **custom design suggestions**, not a default log format emitted by Spring Cloud. To capture these fields, combine supplier-chain instrumentation, `LoadBalancerLifecycle` callbacks, HTTP client hooks, and tracing.

Key information:

1. **Before filtering:** which replicas did the discovery/source supplier see?
2. **After filtering:** did the retry-aware supplier remove the previous instance?
3. **Selected:** which address did LoadBalancer pick for the current attempt?
4. **Outcome:** what was the exception/HTTP status; was the request actually sent?
5. **Retry:** why was retry permitted, and how many attempts/time remain?
6. **Final outcome:** after how many attempts did the business request succeed, and what was end-to-end latency?

Never log tokens, cookies, request bodies containing sensitive data, or private IDs. When emitting metrics, avoid using instance lists or dynamic URLs as high-cardinality labels; keep service ID, outcome, and attempt count as controlled dimensions.

## 20. Test matrix for a retry-aware supplier

To test, use a fake instance list from `SimpleDiscoveryClient`, spin up small HTTP servers, or use an HTTP mock harness able to make one replica fail.

| Scenario | Expectation to verify |
| --- | --- |
| Initial attempt, no previous | Supplier removes no instances because no previous context exists |
| Previous=A, candidates `[A,B,C]` | When avoid-previous applies, the candidate list for the new selection excludes A |
| Previous=A, candidates `[A]` | Fallback may retain A; do not misdiagnose as a config bug |
| Previous=A, candidates `[B,C]` | List retains B,C; A is already absent from source |
| Empty candidates | No valid target; retries do not invent instances |
| Retries disabled or non-retryable error | No second attempt even if a retry-aware supplier bean exists |
| A decorator drops `Request` context | Detect that previous never reaches filter, risking re-selection of A |
| Zone filter keeps only A | Verify zone + retry-aware interaction; do not assume automatic failover to C |
| Attempt 1=A fails, attempt 2=B fails | Attempt 3 does not automatically remember A; observe all selected instances |
| `POST` times out after server write | Prove server handles idempotency; retries create no second side effect |

Do not test by merely sending two normal requests and counting how often A appears. A new request is **not** a retry of the same business request; tests must exercise the retry path with genuine previous-instance context.

### 20.1. Concrete lab steps

1. Run 3 mock instances returning an `instanceId` field in responses.
2. Register the instances under service ID `inventory-service`.
3. Configure Spring Cloud LoadBalancer and the retry policy matching your client.
4. Make A return connection errors or policy-eligible `503`s.
5. Send a `GET` request from the caller, recording trace ID and attempt index.
6. Verify attempt 1 picks A (you may need deterministic selector control in tests).
7. Verify retry picks B or C when eligible.
8. Switch to A-only and confirm fallback/retry bounds.
9. Disable `avoid-previous-instance` to compare behavior, **without assuming** it always picks A again.
10. Verify total deadline, retry count, and retry-induced load.

Tests should isolate randomness, Round Robin state, concurrent requests, and cache freshness so outcomes never depend on luck.

## 21. Diagnostic workflow when retries keep returning to the failing replica

If logs show attempt 1 picked A and retries keep picking A repeatedly, check in order:

1. **Is it actually a retry?** Two independent requests with different traces can normally both pick A.
2. **Where is the retry happening?** Spring Cloud LoadBalancer, Feign Retryer, Reactor `retryWhen`, gateway, or custom business code?
3. **Is a new selection happening?** Intentional same-instance retries do not re-select; only next-instance retries consult the supplier.
4. **Is the client using LoadBalancer?** Fixed physical URLs or builders missing `@LoadBalanced` bypass selection.
5. **Does the supplier chain include the retry-aware decorator?** Check auto-configuration, dependencies, and `avoid-previous-instance`.
6. **Is context propagated properly?** Is some layer calling `delegate.get()` instead of `delegate.get(request)`?
7. **Are alternative replicas available?** Did zone, health, hint, sticky, or cache filters reduce the list to A alone?
8. **Is instance identity stable?** Could unusual instance IDs/metadata affect equality matching?
9. **Are there double retries?** Multiple policies can mix attempts with different contexts and obscure results.
10. **Are deadlines/idempotency set properly?** Never raise retries merely to mask a replica that should be evicted from topology.

If discovery still lists A after A died, investigate deregistration/leases and cache TTL. If retry-aware filtering works yet all requests still fail, inspect load, connectivity, and health of the remaining replicas. If only one instance exists, a retry-aware supplier cannot turn a single-replica topology into multi-replica.

## 22. Limits to remember and safe operational practices

- **Not a 100% avoidance guarantee:** if only one candidate exists, the previous instance may be retained.
- **Not a full history of all failed instances:** it primarily considers the immediately preceding selection, not all past failed attempts by default.
- **Does not trigger retries by itself:** retrying still depends on retry policy, exception/status, and HTTP method.
- **Does not evict failing replicas from the registry:** suppliers do not replace discovery or health checks.
- **Does not cure stale data:** stale caches and registries can keep feeding A to other requests.
- **Does not make POST retries safe:** write operations require explicit idempotency design.
- **Does not replace backoff/deadlines:** avoiding A while slamming B/C continuously can still cause overload.
- **Behavior is not automatically identical across RestClient, WebClient, and OpenFeign:** verify the exact integration and active policy.
- **Do not confuse selection logs with server receipts:** selecting a `ServiceInstance` does not mean the server received the HTTP request.

### 22.1. Official references

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): describes load-balanced retries and `RetryAwareServiceInstanceListSupplier`.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): `spring.cloud.loadbalancer.retry.*` properties.
- [Spring Cloud Commons – LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): supplier chain, caching, health checks, and filters.

During implementation, cross-check documentation against the **exact Spring Cloud version managed by your BOM**, as auto-configuration and retry activation conditions can change across release trains.

## 23. Self-check questions

1. How does `RetryAwareServiceInstanceListSupplier`'s responsibility differ from a retry policy?
2. Why doesn't Round Robin automatically guarantee retries will avoid the just-failed instance?
3. What crucial piece of prior-attempt data must be forwarded through `ServiceInstanceListSupplier#get(Request)`?
4. When `previous=A` and candidates are `[A,B,C]`, what should the filtered list contain?
5. If only A exists, why can the supplier continue returning A?
6. Does `avoid-previous-instance: false` mean retries are disabled?
7. Why can attempt 3 still see A after A and B fail in turn?
8. Why can caching request-filtered lists break retries or sticky sessions?
9. In the example where the caller is in `zone-a` and only A exists in that zone, why isn't retry-aware filtering guaranteed to pick C in `zone-b`?
10. Why can retrying a read-timed-out `POST` onto a healthy instance still create duplicates?
11. How do you distinguish two separate business requests that both picked A from one business request whose retry picked A again?
12. When debugging retries that fail to switch instances, which layers should you inspect before changing the LoadBalancer algorithm?

**Conclusion:** Spring Cloud LoadBalancer uses `RetryAwareServiceInstanceListSupplier` to **reduce the chance of re-selecting the replica chosen on the previous attempt when alternatives exist**. This works only when the retry integration initiates a new selection, propagates request context, and has eligible substitutes in the candidate list. Pair it with discovery/health checks, timeouts, backoff, deadlines, attempt caps, and idempotency so retries aid recovery rather than amplifying system failures.
