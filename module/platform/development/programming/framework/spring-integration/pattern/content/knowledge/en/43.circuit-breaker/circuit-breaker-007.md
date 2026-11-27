# Circuit breaker per endpoint or tenant

## 1. Why does circuit breaker scope matter?

In **SPRING_INTEGRATION_PATTERN**, a system may receive messages through a Gateway, filter them with a Filter, transform them via a Transformer, select branches with a Router, and then invoke external services via Service Activators. Spring Integration channels help build flows following Enterprise Integration Patterns (EIP) with low coupling, yet an outage at one dependency can still spill over to other messages if protection boundaries are drawn poorly.

Suppose an e-commerce system has two APIs:

- **Stock API** to look up inventory.
- **Pricing API** to fetch prices.

If both share **one circuit breaker**, when Stock API repeatedly times out, the OPEN breaker can reject price lookup requests even though Pricing API is healthy. Another example: a multi-tenant provider enforces separate quotas per tenant. Tenant A keeps receiving HTTP 429 while Tenant B is still being served. If one shared breaker covers all tenants, Tenant A's errors can end up blocking Tenant B too.

A **circuit breaker per endpoint or tenant** means scoping the circuit breaker to match the **failure domain**: calls that share a common failure cause or shared limit policy generally belong together; groups that can fail independently may need independent breaker states.

Partitioning must have bounds. Creating a breaker for every URL, SKU, user ID, or request ID grows instance count without bound, leaves each breaker with sparse statistics, and makes the system hard to operate. The goal is to **isolate failures in the right place with a manageable number of breakers**.

## 2. Breaker scope: one key per failure domain

Each breaker instance maintains its own **CLOSED / OPEN / HALF_OPEN** state and statistical history. We choose a stable **breaker key** to determine which calls share an instance.

~~~mermaid
flowchart TD
    A[Gateway] --> B[Filter / Transformer]
    B --> C{Business Router}
    C -->|Lookup stock| D[Breaker: stock.read]
    C -->|Reserve stock| E[Breaker: stock.reserve]
    C -->|Lookup pricing| F[Breaker: pricing.read]
    D --> G[Stock read endpoint]
    E --> H[Stock reserve endpoint]
    F --> I[Pricing endpoint]
~~~

For instance, the three breakers above can be independent if the operations are deployed and fail independently. Conversely, if all three endpoints traverse **the same downed dependency cluster**, splitting breakers per operation does not eliminate the shared failure; each breaker may still send extra traffic to the cluster before opening.

### 2.1. Common ways to choose keys

| Scope | Example key | When to use | Limitations |
| --- | --- | --- | --- |
| Per service | **stock-service** | Multiple calls share one failure domain | One failing endpoint can impact healthy endpoints |
| Per operation / logical endpoint | **stock.read**, **stock.reserve** | Read/write have independent policies or infrastructure | Too many tiny endpoints fragment sample counts |
| Per deployment region | **stock.read:ap-southeast**, **stock.read:eu-west** | Each region has separate backends and failure modes | Misused if traffic hits the same upstream |
| Per tenant | **stock.read:tenant-A** | Tenants have separate quotas, instances, or connections | High cardinality; low-traffic tenants lack samples |
| Per tenant group | **stock.read:shared**, **stock.read:enterprise-A** | A few large tenants need isolation while others share | Tenants in the shared group still affect each other |

**Endpoint here means a stable operation**, not a literal URL containing parameters. For example, **/stock/SKU-1** and **/stock/SKU-2** both belong to the **stock.read** operation. Using the SKU in the breaker key gives every item its own state and prevents the breaker from accumulating enough failures to recognize that the inventory API is down.

Likewise, never use request IDs, correlation IDs, paths with query parameters, or unverified tenant strings as keys.

### 2.2. Questions about failure domains before splitting breakers

1. Do two calls share the **same upstream instance, connection pool, or quota**?
2. Can one endpoint/tenant fail **while the remaining groups stay healthy**?
3. Are there enough requests in each group to conclude a breaker should OPEN?
4. Are there **SLA, contractual, or security isolation** requirements between tenants?
5. Is the number of keys bounded and small enough to monitor, test, and clean up?

Practical scopes are sometimes a combination of **service + operation + region + tenant group**, but do not add dimensions unless there is evidence they represent independent failure domains.

## 3. Isolating by endpoint: the most intuitive design

An application may call two endpoints on the same backend, yet their usage patterns and failure requirements differ.

| Call site | Business role | Example policy |
| --- | --- | --- |
| **stock.read** | Read inventory for display | Can fall back to reference cache |
| **stock.reserve** | Reserve items for an order | Usually requires fresh confirmation, fail fast on error |
| **pricing.read** | Look up price | May have its own timeout and SLO |
| **shipping.quote** | Calculate shipping fee | Can try a backup provider if permitted |

A separate breaker for **stock.reserve** keeps erratic read traffic from directly locking out reservation operations, provided failure domains are sufficiently independent. However, if both operations depend on the same disconnected database, both breakers can still open; monitor overall system health as well.

In Spring Integration, the Router forwards messages to the appropriate channel; each Service Activator uses its own advice/breaker:

~~~mermaid
flowchart LR
    A[Order Gateway] --> B[Validate]
    B --> C{Router}
    C -->|read| D[Channel stock.read]
    C -->|reserve| E[Channel stock.reserve]
    D --> F[Breaker read]
    E --> G[Breaker reserve]
    F --> H[Stock read client]
    G --> I[Stock reserve client]
~~~

**Attach the breaker right next to the dependency call operation.** Filters must not trip the circuit on negative quantities; Transformer parse errors must not count against Stock API health. If the same endpoint is called by multiple flows, share the same breaker instance for that endpoint when they share the same failure domain and policy.

## 4. Isolating by tenant: when is it actually needed?

In a multi-tenant service, each request carries an authenticated tenant context. If the provider enforces **per-tenant quotas**, **dedicated data stores**, **separate connections**, or **distinct SLAs**, one tenant can fail independently of others.

~~~mermaid
flowchart TD
    A[Gateway + authenticated tenant context] --> B[Resolve bounded breaker scope]
    B --> C{Scope}
    C -->|Tenant A with dedicated circuit| D[stock.read:DEDICATED_A]
    C -->|Tenant B with dedicated circuit| E[stock.read:DEDICATED_B]
    C -->|Standard tenants| F[stock.read:SHARED]
    D --> G[Stock client, tenant A]
    E --> H[Stock client, tenant B]
    F --> I[Stock client, tenant from verified request]
~~~

In this example, if Tenant A fails enough for A's circuit to OPEN, Tenant B can still make calls through B's breaker. Tenants in the SHARED group share statistics: if one tenant fails continuously, the shared group can also be affected. This is an intentional trade-off when tenant count is large or per-tenant traffic is low.

### When should you use a per-tenant breaker?

- Upstream enforces **per-tenant rate limits/quotas**, e.g., Tenant A exhausts quota while B still has quota.
- Each tenant routes to a separate **database schema/cluster/provider** or credentials, so failures can be independent.
- Certain tenants have **high SLAs** and need isolation from other tenants' traffic.
- There is enough sample volume/traffic for per-tenant breaker state to reflect real failures rather than constantly falling short of minimum calls.

### When should you avoid it?

- All tenants hit **the exact same shared endpoint** and most incidents are full-upstream outages. Over-splitting forces thousands of breakers to independently "learn" the backend is down.
- There are tens of thousands of tenants with very low traffic; each breaker holds fragmented statistics and fails to detect incidents promptly.
- The tenant key comes directly from untrusted input. A client could generate arbitrary keys to inflate breaker count or intentionally skew state.

**Do not confuse breakers with quota enforcement.** A breaker detects failing/slow call conditions; a quota/rate limiter proactively restricts request rates, while a bulkhead bounds concurrent resources. In multi-tenant setups, you often need **breaker + per-tenant rate limit/bulkhead** depending on fairness requirements.

## 5. Scope selection matrix

| Situation | Scope to consider | Reason |
| --- | --- | --- |
| Stock and Pricing are two independent systems | One breaker per dependency | Stock outage does not automatically block Pricing |
| Stock read and reserve run on independent clusters | Per operation/endpoint | Can fail independently |
| Stock read/reserve share a cluster that fails together | Per service or service-level protection | Avoids multiple breakers sending traffic into a broken backend |
| Tenant A/B have independent quotas/providers | Per tenant or dedicated tenant group | A's failures do not block B |
| Many small tenants on one endpoint | Shared breaker | Enough samples and fewer instances |
| A few large tenants need isolation | Shared + dedicated breakers | Balances isolation and cardinality |
| Multi-region traffic to regional backends | Add region to scope | Outage in one region does not block others |
| Each request has a unique SKU/request ID | **Never use as key** | Not a failure domain; unbounded key growth |

There is no single fixed diagram for every system. Scope must derive from how dependencies are deployed and actually fail, then be validated against traffic and outage scenarios.

## 6. Simple implementation with native advice per endpoint

Spring Integration's **RequestHandlerCircuitBreakerAdvice** attaches to a request handler and keeps breaker state on the advice instance. When you have two independent dependencies, declare **two independent advice instances**.

Illustrative configuration example (imports omitted):

~~~java
@Configuration
@EnableIntegration
public class EndpointBreakerConfig {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockReadAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();
        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000);
        return advice;
    }

    @Bean
    public RequestHandlerCircuitBreakerAdvice pricingReadAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();
        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000);
        return advice;
    }

    @Bean
    public IntegrationFlow stockReadFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockReadAdvice
    ) {
        return IntegrationFlow.from("stock.read.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> stockClient.lookup(query),
                        endpoint -> endpoint.advice(stockReadAdvice)
                )
                .get();
    }

    @Bean
    public IntegrationFlow pricingReadFlow(
            PricingClient pricingClient,
            RequestHandlerCircuitBreakerAdvice pricingReadAdvice
    ) {
        return IntegrationFlow.from("pricing.read.requests")
                .handle(
                        PriceQuery.class,
                        (query, headers) -> pricingClient.lookup(query),
                        endpoint -> endpoint.advice(pricingReadAdvice)
                )
                .get();
    }
}
~~~

In this example, **StockClient**, **PricingClient**, **StockQuery**, and **PriceQuery** are application-defined types. Each advice observes exceptions from its corresponding handler. Do not accidentally pass **the same advice instance** to both endpoints if you want two independent breakers.

Native advice is convenient when endpoints are few and you only need a consecutive-failure threshold plus a wait duration. If you need breakers allocated dynamically across tenants, managing many handlers/advices becomes cumbersome, so choosing a library with a **named instance registry** is easier to control.

## 7. Spring Integration + Resilience4j with a partitioned registry

Resilience4j supports creating multiple circuit breaker instances by **name** via **CircuitBreakerRegistry**. Calls using the same name within a registry receive the same breaker; different names keep separate states.

An easily controlled design uses a **finite set of scopes** for endpoints and tenant groups. For instance, only allow select special tenants to have dedicated breakers; remaining tenants use a shared breaker.

### 7.1. Message contract and authenticated scope

~~~java
public record StockQuery(String sku) {}

public record StockResult(String sku, int availableUnits) {}

public interface StockClient {
    StockResult lookup(String tenantId, String sku);
}

public enum TenantCircuitGroup {
    SHARED,
    DEDICATED_A,
    DEDICATED_B
}

public record VerifiedTenantContext(
        String tenantId,
        TenantCircuitGroup group
) {}

public interface VerifiedTenantResolver {
    VerifiedTenantContext resolveFromTrustedContext(
            Map<String, Object> headers);
}
~~~

**VerifiedTenantResolver** is an interface the application must implement at the security boundary. It must extract the tenant from an **authenticated identity** or context attached by a trusted service, check permissions, and map the tenant to one of the three groups. Never simply read a client-supplied **tenantId** header and assume it is a valid tenant.

**TenantCircuitGroup** is the breaker scope, while **tenantId** remains the data identifier passed when StockClient executes. Multiple tenants sharing a group **does not mean** they are allowed to share caches, credentials, or returned data.

### 7.2. Registry configured with minimum sample count

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockBreakerConfiguration {

    @Bean
    public CircuitBreakerRegistry stockCircuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreakerRegistry.of(config);
    }

    @Bean
    public IntegrationFlow stockReadFlow(PartitionedStockCaller caller) {
        return IntegrationFlow.from("stock.read.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> caller.lookup(query, headers)
                )
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "stock.read.requests")
public interface StockGateway {
    StockResult lookup(StockQuery query);
}
~~~

This illustrative config uses **minimumNumberOfCalls(10)** to avoid opening the circuit based on just a couple of requests. Real numbers must fit traffic. For a dedicated tenant with very few requests, such a threshold may prevent the breaker from gathering enough samples to open in the desired timeframe; carefully weigh scope and window size.

### 7.3. Selecting the scoped breaker before the client call

~~~java
@Component
public class PartitionedStockCaller {

    private final CircuitBreakerRegistry registry;
    private final VerifiedTenantResolver tenantResolver;
    private final StockClient stockClient;

    public PartitionedStockCaller(
            CircuitBreakerRegistry registry,
            VerifiedTenantResolver tenantResolver,
            StockClient stockClient
    ) {
        this.registry = registry;
        this.tenantResolver = tenantResolver;
        this.stockClient = stockClient;
    }

    public StockResult lookup(
            StockQuery query,
            Map<String, Object> headers
    ) {
        VerifiedTenantContext tenant =
                tenantResolver.resolveFromTrustedContext(headers);

        // Key set is bounded by a controlled enum.
        String breakerName =
                "stock.read:" + tenant.group().name();

        CircuitBreaker breaker =
                registry.circuitBreaker(breakerName);

        return breaker.executeSupplier(
                () -> stockClient.lookup(tenant.tenantId(), query.sku())
        );
    }
}
~~~

In this snippet:

1. The Gateway forwards the message to the **stock.read.requests** channel.
2. The resolver obtains the **authenticated tenant** and selects the group from internal policy configuration.
3. The registry looks up or creates the breaker for a stable name like **stock.read:DEDICATED_A**.
4. The supplier wraps only **StockClient.lookup**, so dependency exceptions are accurately recorded by the breaker.
5. When the breaker is OPEN, the supplier does not run; the not-permitted error can propagate to the Gateway for fail-fast or outer fallback handling.

Choosing three groups illustrates **bounded cardinality**. It does not implement the real resolver or StockClient: those are application-supplied adapters. If **each tenant requires an independent breaker**, the mapping must ensure **each individual tenant gets its own group/key**, accompanied by limits on breaker count, lifecycle, and observability. You cannot call the three groups above "per-tenant breakers" for every tenant in the system.

### 7.4. Adding endpoint to the key without cardinality explosion

If the same registry manages multiple logical endpoints, keys can be built from two controlled value sets:

~~~java
public enum DependencyOperation {
    STOCK_READ,
    STOCK_RESERVE,
    PRICING_READ
}

public record CircuitScope(
        DependencyOperation operation,
        TenantCircuitGroup group
) {
    public String breakerName() {
        return operation.name() + ":" + group.name();
    }
}
~~~

At most 3 operations × 3 groups = **9 logical scopes** in the example. An endpoint that does not need tenant partitioning can always use **SHARED**, reducing actual instances further.

Endpoints with different SLOs can register **different CircuitBreakerConfig** definitions when creating instances. One shared/global config does not necessarily fit both a 100 ms read latency and a 3-second reserve latency; choosing timeouts, error thresholds, and wait durations must reflect the actual dependency/operation.

## 8. Managing breaker count: avoiding unbounded cardinality

The isolation benefit can turn into heavy overhead if breakers are created arbitrarily per dynamic tenant.

For example, with **20 endpoints × 50,000 tenants**, a full endpoint-tenant matrix could create up to **1,000,000 keys**. Registries, event listeners, metrics, stats objects, and references can consume large amounts of memory. Too many keys also bloat metric time series and degrade monitoring effectiveness.

Measures to consider:

- **Group by real failure domain:** grant dedicated breakers only to tenants with genuinely independent quotas, providers, or infrastructure.
- **Whitelist / scope policy:** determine dedicated tenants from authenticated, controlled configuration rather than arbitrary request strings.
- **Cap instance count:** if supporting dynamic tenants, enforce a breaker budget and clear expiration/cleanup policies for inactive tenants.
- **Safe eviction mechanism:** clean up only when no calls are actively using the breaker, without abruptly destroying state or leaking listener/metric resources.
- **Metric aggregation:** avoid using tenant ID, SKU, request ID, or correlation ID as high-cardinality tags. Use buckets, endpoints, and outcomes; tenant IDs needed for investigation can live in controlled logs/traces.
- **Tier by priority:** key tenants receive dedicated breakers; the smaller majority shares a common breaker alongside per-tenant rate limiters to enforce fairness.

Do not assume a registry automatically deletes instances after a tenant stops sending requests. Lifecycle, metric/registry cleanup, and config updates must be verified against your library version and application architecture.

### Avoid keys containing sensitive data

Breaker names often appear in metrics, logs, or dashboards. Constructing names from emails, sensitive customer IDs, or internal tenant values can leak data through observability channels. Use neutral group names or technical identifiers approved to appear in monitoring systems.

## 9. Failure count when multiple tenants share a breaker

Suppose breaker **stock.read:SHARED** has a threshold of three consecutive failures and is shared by tenants T1, T2, and T3:

| Request | Tenant | Outcome | Consecutive failures of SHARED breaker |
| --- | --- | --- | ---: |
| 1 | T1 | Timeout | 1 |
| 2 | T2 | Timeout | 2 |
| 3 | T3 | Timeout | 3, circuit OPEN |
| 4 | T1 | Rejected | Client not called |
| 5 | T2 | Rejected | Client not called |

All tenants in the shared group experience the same state. That is a direct consequence of sharing an instance, not a breaker bug.

When split into dedicated tenant breakers:

~~~mermaid
flowchart LR
    A[Tenant A] --> B[Breaker A: OPEN]
    C[Tenant B] --> D[Breaker B: CLOSED]
    B -.-> E[Block A calls]
    D --> F[Allow B to call upstream]
~~~

Tenant B can continue, **if B's upstream is actually healthy and has independent resources**. If the shared upstream is broken, A and B will independently record failures in their own windows; B may spend several calls before Breaker B opens.

**Low-traffic problem:** a tenant calling only twice per hour, while the breaker requires at least ten calls to evaluate failure rate, can take a very long time to reach minimum number of calls. You can use count-based consecutive failures with a smaller threshold, group tenants together, or adjust SLO policies. However, too small a threshold triggers false trips from noise.

## 10. Interaction with retry, timeout, bulkhead, and rate limiter

A circuit breaker can only infer failure conditions from **the outcomes it observes**. If each tenant has a separate breaker yet all share one HTTP connection pool, Tenant A's outage can still exhaust the pool and slow down Tenant B.

Therefore, breaker scope must coordinate with resource limits:

| Mechanism | Problem solved | Scope that may be needed |
| --- | --- | --- |
| **Timeout** | Bounds duration of an in-flight call | Per endpoint/dependency and SLA |
| **Circuit breaker** | Cuts off new calls after failure streak/rate | Per endpoint/tenant failure domain |
| **Bulkhead** | Limits concurrent calls or resources | Per dependency or tenant group |
| **Rate limiter** | Limits access rate/quota | Possibly per tenant |
| **Retry** | Retries transient errors | Based on operation idempotency |

### Retry alters statistics within each scope

If the breaker wraps retry, a logical request with multiple attempts may produce **one final outcome** for the breaker. If retry wraps the breaker, each attempt can be tracked within the breaker's scope. Whether scoped per tenant or per endpoint, define the counting unit clearly so retries do not trip a tenant's circuit prematurely.

Never retry indefinitely when a breaker is OPEN. In Resilience4j, rejected calls can throw **CallNotPermittedException**; do not treat that exception as a new dependency failure to keep retrying.

### Write operations must have idempotency

For operations like **stock.reserve**, a timeout does not prove upstream never processed the command. When retrying or replaying from a queue, require a distinct **idempotency key** per business request, scoped by tenant, to avoid duplicate orders or double reservations.

### Per-breaker OPEN → HALF_OPEN

Each scope has its own wait duration and HALF_OPEN phase. If many breakers open simultaneously during a region-wide outage, they can all allow probes at once when their wait durations expire. Cap probe counts, concurrency, and total recovery traffic at the dependency level, especially when upstream may overload right as it recovers.

## 11. Fallback must match the tenant and endpoint type

When a breaker is OPEN, Spring Integration does not decide the business outcome on its own. Branches need explicit, safe fallbacks.

| Scope | When OPEN | Appropriate strategy |
| --- | --- | --- |
| **stock.read** on catalog screen | Cannot fetch fresh data | Reference cache within TTL, labeled stale |
| **stock.reserve** at order confirmation | Cannot confirm reservation | Fail fast/UNAVAILABLE; never mark order complete |
| **pricing.read** where stale prices are acceptable | API slow or failing | Cache with explicit origin and expiration |
| Asynchronous **notification.send** | Provider not yet recovered | Durable queue/outbox with bounded replay |

In multi-tenant setups, **fallback data must be partitioned by tenant**, even when tenants share a breaker group. For example, never use a cache key containing only **SKU** if stock differs per tenant/warehouse. Keys must include the authenticated tenant identifier and key business dimensions, and enforce authorization before reading the cache.

Represent outcomes explicitly:

~~~java
public enum LookupStatus {
    FRESH,
    STALE_REFERENCE,
    UNAVAILABLE
}

public record StockLookupReply(
        String tenantId,
        String sku,
        LookupStatus status,
        Integer availableUnits,
        Instant sourceTime,
        String correlationId,
        String reasonCode
) {}
~~~

**UNAVAILABLE** means "no reliable data available", not "out of stock". When fallback sits **outside the breaker execution zone**, the breaker still records StockClient failures before returning cached data or the appropriate error.

Never treat `tenantId` inside an outcome as proof of authentication; it is merely correlation metadata. Which tenant a caller may access is decided at ingress / the trusted Resolver.

## 12. Error channel, Router, Splitter, Aggregator, and correlation

### Router

The Router can select operations such as `stock.read`, `stock.reserve`, or `pricing.read`. The breaker key is an infrastructure decision based on operation and failure domain; the Router must continue respecting the message's business meaning. If one branch is OPEN, do not automatically route a stock reservation request to a cached-read branch as if the two were equivalent.

### Synchronous Gateway

With a Gateway calling over **DirectChannel**, exceptions from the handler or Resilience4j can propagate straight to the caller. The API layer must map errors by scope: e.g., **Stock for tenant A is temporarily unavailable**. Never leak other tenants' structure or breaker state to unauthorized users.

### Asynchronous error channel

When a handler runs via an ExecutorChannel/poller/asynchronous adapter, failures can produce an **ErrorMessage** through the corresponding error channel mechanism. The error flow needs enough context to decide retry/defer:

- Authenticated tenant.
- Logical endpoint/operation and selected breaker scope.
- Correlation/trace ID and idempotency key if present.
- Root exception or reason code, specifically distinguishing **dependency failure** from **breaker rejected**.

An error channel does not automatically guarantee every synchronous error from a Gateway enters it. Verify actual execution boundaries.

### Splitter and Aggregator

When a Splitter generates multiple sub-requests from one order, they may pass through different breakers by operation, region, or tenant. If one branch is OPEN and emits no reply, the Aggregator can hang waiting for missing messages.

Preserve **correlation ID**, **sequence metadata**, and **authenticated tenant context** on every branch. Clearly define partial results, fallback outcomes, group timeout, expiration, and discard/error paths. Never merge messages from different tenants simply because they share a client-provided correlation ID; include a group key or context-validation step sufficient to isolate each tenant's requests.

## 13. Testing isolation between two breakers

Tests must prove that Scope A's breaker opening **does not automatically open Scope B's breaker**, while blocked requests never reach the dependency. You can use Resilience4j and fake clients with separate counters.

~~~java
@Test
void outageInOneTenantScopeDoesNotOpenAnotherScope() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreakerRegistry registry = CircuitBreakerRegistry.of(config);
    CircuitBreaker tenantA = registry.circuitBreaker(
            "stock.read:DEDICATED_A");
    CircuitBreaker tenantB = registry.circuitBreaker(
            "stock.read:DEDICATED_B");

    AtomicInteger callsA = new AtomicInteger();
    AtomicInteger callsB = new AtomicInteger();

    Supplier<String> failingA = () -> {
        callsA.incrementAndGet();
        throw new IllegalStateException("tenant A upstream unavailable");
    };
    Supplier<String> healthyB = () -> {
        callsB.incrementAndGet();
        return "OK";
    };

    assertThrows(
            IllegalStateException.class,
            () -> tenantA.executeSupplier(failingA));
    assertThrows(
            IllegalStateException.class,
            () -> tenantA.executeSupplier(failingA));

    assertEquals(CircuitBreaker.State.OPEN, tenantA.getState());
    assertThrows(
            CallNotPermittedException.class,
            () -> tenantA.executeSupplier(failingA));
    assertEquals(2, callsA.get());

    assertEquals("OK", tenantB.executeSupplier(healthyB));
    assertEquals(CircuitBreaker.State.CLOSED, tenantB.getState());
    assertEquals(1, callsB.get());
}
~~~

Common imports are omitted. This tests **separate breaker state**, not whether two tenants truly have independent backends. Integration tests should use a fake provider returning errors specifically for Tenant A and successes for Tenant B, while running messages through the real Gateway and route resolver.

### Required test matrix

| Scenario | Expected verification |
| --- | --- |
| Stock.read fails, Pricing.read healthy | Stock breaker OPEN does not block Pricing |
| Read fails, Reserve healthy on independent infra | Read operation breaker does not open Reserve breaker |
| Tenant A fails, B healthy, separate keys | A OPEN; B still permitted to call |
| Tenant A/B both in SHARED | Enough failures can OPEN the circuit for the whole group |
| Unauthenticated tenant | Rejected before creating a breaker or calling dependency |
| Unknown tenant ID / request with spoofed key | Does not create a new breaker from arbitrary input |
| Many low-traffic tenants | Minimum calls and windows do not cause undesired reactions |
| Same breaker name in registry | Calls share state as designed |
| Different breaker names | States and counters are isolated |
| Breaker OPEN | Call counter for the respective client does not increase |
| Multiple scopes in HALF_OPEN | Permit limits and total recovery load bounded |
| A's cache fallback | Never reads/returns Tenant B's data |
| Multi-branch Splitter/Aggregator | Correlation and tenant never mixed; group completes per policy |
| Multiple instances/pods | Do not assume one global breaker state |

Timeout/retry tests must use fakes with controllable exceptions, latencies, and attempt counts; do not merely assert that the Gateway errored. For failing write operations, add idempotency and replay tests to verify no duplicate side effects occur.

## 14. Observing and operating scoped breakers

A system with many breakers becomes hard to maintain without a scope map, naming convention, and consistent metrics.

| Signal | What to monitor? |
| --- | --- |
| **breaker name / scope** | Which operation or tenant group is OPEN? |
| **state transition** | When each scope opens, probes, and closes |
| **failure / slow call rate** | Which group has abnormal errors or latency? |
| **not-permitted calls** | Which scope is rejecting many messages? |
| **request rate and minimum calls** | Does the breaker have enough samples to open? |
| **Gateway latency / channel queue depth** | Is the flow congested despite the breaker being OPEN? |
| **fallback rate / cache age** | Which tenant is using degraded results and is it still safe? |
| **bulkhead saturation / rate-limit rejection** | Is one tenant exhausting shared resources? |
| **Aggregator group timeout** | Are OPEN branches causing missing replies? |

With Resilience4j, integrate Micrometer and event publishers. Use bounded-cardinality metric tags such as **operation**, **normalized region**, **tenant group**, and **outcome**. When you genuinely need to investigate a specific tenant, use access-controlled logs/traces with tenant ID and correlation ID; never create a metric time series per request or unboundedly per tenant.

**State usually lives in-process.** Pods may open/close breakers at different times due to different traffic. If you need system-wide traffic limiting, add a rate limiter or appropriate coordination mechanism; do not assume Resilience4j shares breaker state across pods automatically.

### Signs of poor scope selection

- **One endpoint outage drags another branch down:** shared breaker is too broad or shared resources lack isolation.
- **Clear upstream errors yet no breaker OPENS:** scope is too narrow, lacks minimum calls, or errors are not recorded.
- **Breaker count keeps growing:** keys come from dynamic request data; registry/lifecycle is unbounded.
- **Metrics have too many series:** tenant ID/SKU/request ID attached as tags; dashboards consume excessive resources.
- **Tenant B stays slow while Breaker A is OPEN:** shared pool/concurrency/quota requires bulkhead/rate limiter beyond the breaker.
- **One tenant receives another tenant's cache:** data partitioning bug; fix at the cache/identity boundary; breaker scope never replaces authorization.

## 15. Implementation checklist

- [ ] Identify real **failure domains** before choosing per-service, per-endpoint, per-region, or per-tenant breakers.
- [ ] Keys use **stable operation/region/tenant group**, never dynamic URLs, SKUs, or request IDs.
- [ ] Tenant context is authenticated at ingress and preserved across message headers/correlation.
- [ ] Use separate breakers for independent dependencies; native advice instances are not unintentionally shared.
- [ ] If using a Registry, bound key count, lifecycle strategy, and metrics/listeners cleanup policy.
- [ ] Choose minimum calls, windows, timeouts, retries, and HALF_OPEN probes per scope with sufficient traffic.
- [ ] Pair with rate limiter/bulkhead when multiple tenants share underlying resources.
- [ ] Fallbacks and caches enforce authorization, TTL, and tenant-scoped keys; never confuse UNAVAILABLE with a business result.
- [ ] Gateway/error channel, Router, Splitter, and Aggregator preserve correlation and tenant context accurately.
- [ ] Test A failing/B healthy, shared groups, rejected calls, spoofed-tenant cases, and cache isolation.
- [ ] Monitor metrics with bounded-cardinality scope tags; use controlled logs/traces for detailed IDs.

**Circuit breaker per endpoint or tenant** cuts off failures at the right boundary instead of letting one unhealthy dependency or tenant drag down the whole system. In Spring Integration, breaker scope must work alongside Router, Gateway, error channel, correlation, resource limits, and data partitioning. Choosing a manageable number of breakers, placing them close to dependency calls, and testing real isolation keeps flows loosely coupled and able to recover under control.
