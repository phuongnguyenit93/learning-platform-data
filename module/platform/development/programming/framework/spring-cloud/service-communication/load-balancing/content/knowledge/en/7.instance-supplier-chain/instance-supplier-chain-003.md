# Combining Filters, Caching, and Health Checks

In Spring Cloud LoadBalancer, a selector such as `RoundRobinLoadBalancer` does not perform discovery, caching, or health checks on individual servers itself. It obtains a **list of candidate `ServiceInstance` objects** from `ServiceInstanceListSupplier`, then picks one instance according to a policy. When multiple suppliers are combined, they form a chain: fetching data from discovery, reusing data appropriately, screening instances, and returning the final list to the selector.

This lesson belongs to the **Instance Supplier Chain** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. Its goal is to understand how to combine **instance filtering**, **caching**, and **health checks** so that communication by service ID is more reliable, while recognizing when stale data or overly strict filters eliminate all candidates. This knowledge applies to calls via RestClient, WebClient, and OpenFeign integrated with Spring Cloud LoadBalancer.

## 1. Why Combine Multiple Instance Suppliers?

Suppose `order-service` calls `catalog-service`. The registry reports four instances:

| Instance | Zone | Status at check time | Notes |
|---|---|---|---|
| `catalog-a` | `zone-a` | Healthy | Same zone as caller |
| `catalog-b` | `zone-a` | Unhealthy | Should not receive new traffic |
| `catalog-c` | `zone-b` | Healthy | Available when needed |
| `catalog-d` | `zone-b` | Healthy | Available when needed |

If you only fetch the list from the registry and run Round Robin, `catalog-b` can still be picked when the registry has not yet updated its failure state. If you query the registry on every single request, discovery load and latency increase. If you filter strictly down to `zone-a` without considering health, you may end up with zero candidates at times.

A supplier chain separates each responsibility:

1. **List source**: `DiscoveryClientServiceInstanceListSupplier` or a static source fetches the instances for the service ID.
2. **Cache**: `CachingServiceInstanceListSupplier` reduces query frequency against the backing source when appropriate.
3. **Health check**: `HealthCheckServiceInstanceListSupplier` monitors the responsiveness of supplied instances.
4. **Filtering or preference**: suppliers for zones, hints, metadata, or specific request criteria process the list before selection.
5. **Selector**: `RoundRobinLoadBalancer`, `RandomLoadBalancer`, or another algorithm picks one instance from the resulting list.

Not every system needs all layers. If discovery already reflects health accurately and has suitable caching, adding a separate health check can increase request volume and state management overhead.

## 2. Suppliers Are a Decorator Chain, Not an Independent List of Rules

A `ServiceInstanceListSupplier` can be wrapped by another supplier. The outer supplier calls the inner supplier, receives the list, and transforms or caches that data. Therefore, **wrapping order affects what data is cached, health-checked, and filtered**.

Mental model of a pipeline:

~~~mermaid
flowchart LR
    R["Discovery / static list"] --> C["Cache baseline list, if needed"]
    C --> H["Health check, if needed"]
    H --> F["Filter / prefer by zone, hint, request"]
    F --> L["LoadBalancer selects one ServiceInstance"]
    L --> A["RestClient / WebClient / OpenFeign sends HTTP"]
~~~

This diagram shows the **data stages** reading left to right. The Java implementation using nested decorators invokes methods in the reverse direction: the outermost supplier is called first and pulls data from its inner delegate.

The output of `ServiceInstanceListSupplier` is a stream carrying a **list** of candidates, such as `Flux<List<ServiceInstance>>`. It is not yet a server selection response. Only after receiving the list does the selector return a `Response<ServiceInstance>` containing the chosen instance, or `EmptyResponse` if no candidates remain.

An abstract example:

~~~text
Discovery: [A, B, C, D]
      |
      v
Cache:     [A, B, C, D]  (list snapshot)
      |
      v
Health:    [A, C, D]     (B failed health check)
      |
      v
Zone:      [A]           (prefer zone-a)
      |
      v
Selector:  A
~~~

In practice, some zone-preference or hint-based suppliers **have a mechanism to fall back to the original list if no matching candidates exist**. Thus, you cannot assume from the word "filter" that an empty list is always returned on no match. Check the fallback policy of the actual supplier and the Spring Cloud version in use.

## 3. List Sources: Discovery and Static Instances

The base source is usually one of two types:

- `DiscoveryClientServiceInstanceListSupplier` fetches the list from a Spring Cloud-compatible discovery system.
- `SimpleDiscoveryClient` can supply a statically configured instance list to `DiscoveryClientServiceInstanceListSupplier` in environments without a full service registry; alternatively, the application can build a custom supplier source.

Each `ServiceInstance` holds fields such as `serviceId`, `host`, `port`, `secure`, and `metadata`. Example of a logical instance:

~~~text
serviceId = catalog-service
host      = 192.0.2.21
port      = 8080
secure    = false
metadata  = { zone: "zone-a", version: "v2" }
~~~

`192.0.2.21` is an illustrative address, not a real host. When an HTTP client calls `http://catalog-service/api/items/42`, Spring Cloud LoadBalancer uses `catalog-service` to retrieve the instance list; then the client connects to the selected host/port.

A discovery source does not always reflect instantaneous state. A newly started instance might not appear yet; a recently stopped instance might still remain in the registry. Caching and health checks address different problems arising from this lag.

## 4. Caching: Optimizing Read Cost, Accepting Update Lag

`CachingServiceInstanceListSupplier` stores the instance list received from its inner source so nearby requests can reuse the result. Common benefits include fewer discovery reads, lower instance-selection latency, and avoiding registry load spikes under high HTTP traffic.

For example, while the cache entry remains valid:

~~~mermaid
sequenceDiagram
    participant R as Request
    participant C as Caching supplier
    participant D as Discovery

    R->>C: Call 1: catalog-service
    C->>D: Cache miss: fetch list
    D-->>C: [A, B, C]
    C-->>R: [A, B, C]
    R->>C: Call 2: catalog-service
    C-->>R: Cache hit: [A, B, C]
    Note over C: Cache expires or refreshes
    R->>C: Call 3: catalog-service
    C->>D: Fetch fresh list
    D-->>C: [A, C, D]
    C-->>R: [A, C, D]
~~~

### Time-to-Live and Capacity Limits

The cache has a **TTL (time to live)** and an appropriate capacity limit. A short TTL updates the list faster but increases discovery queries. A long TTL reduces registry load but keeps failed or removed instances around longer.

A reference configuration example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 30s
        capacity: 256
~~~

Property names and defaults may vary by version. If the discovery client already caches data, check whether adding LoadBalancer caching helps or creates **two layers of stale data**. Never pick a very long TTL solely to boost the cache hit ratio.

### Caching Holds Registration Info, Not Proof of Health

A cache entry containing `catalog-b` only indicates that the instance was once in the discovery list. It does not prove that `catalog-b` is currently responding properly. Health checks or actual HTTP client outcomes still matter when deciding whether to send traffic.

Conversely, a successful health check at time T does not guarantee the instance stays healthy at T+1: network errors, overload, or restarts can occur immediately afterward. HTTP timeouts and error handling remain mandatory.

## 5. Health Checks: Filtering Out Unresponsive Candidates

`HealthCheckServiceInstanceListSupplier` checks instances from the underlying source and publishes an updated list based on probe results. The goal is to curb sending new requests to failing instances even when the registry has not yet deregistered them.

General workflow:

1. Obtain the instance list from the delegate.
2. Periodically call each instance's configured HTTP health endpoint.
3. Track results and emit the list of instances considered healthy.
4. Update the published list when the next health-check cycle completes or when the underlying source changes according to configuration.

~~~mermaid
sequenceDiagram
    participant D as Discovery
    participant H as HealthCheck supplier
    participant A as Instance A
    participant B as Instance B
    participant LB as LoadBalancer

    D-->>H: [A, B]
    H->>A: GET /actuator/health
    A-->>H: 200 OK
    H->>B: GET /actuator/health
    B-->>H: Timeout / error
    H-->>LB: Healthy list: [A]
    LB-->>LB: Select A
~~~

The `/actuator/health` path is just a common example. The actual endpoint may differ—such as a dedicated readiness probe—and must be reachable from the caller application. Health checks should not depend on an authenticated endpoint that the client lacks credentials to access.

### Liveness, Readiness, and Traffic Suitability

- **Liveness** answers whether the application process is still running.
- **Readiness** answers whether the application is ready to receive traffic.
- **Dependency health** may require careful consideration: not every dependency failure renders an instance incapable of serving all APIs.

If the endpoint is too trivial, health checks might mark an instance healthy before it is ready. If the endpoint is too strict, a minor dependency outage could eject every instance and cause a total service outage. Define criteria matching the type of requests being routed.

### Health Checks Also Have a Cost

Suppose there are 100 client applications, each probing 20 instances every 10 seconds. The system will generate significant health-check traffic. Balance probe interval, timeout, instance count, and the health endpoint's capacity. Aggressive health checks do not automatically make a system more stable.

In particular, `HealthCheckServiceInstanceListSupplier` already manages retaining and replaying check results over its lifecycle. Therefore, **do not stack `CachingServiceInstanceListSupplier` into the same chain by default**. Check the documentation for your version and keep both only if you know exactly which layer caches what data and why it is needed.

## 6. Filters: Selecting the Right List for the Current Request

Filtering or preference suppliers can use metadata, zones, or request attributes. Examples:

| Mechanism | Decision input | Notes |
|---|---|---|
| Zone preference | Caller's zone and instance metadata | May fall back to other zones depending on the supplier |
| Hint-based | Request hint and metadata | Must define behavior when no matching hint exists |
| Custom metadata | Version, customer tier, hardware capability | Avoids routing to a version missing required APIs |
| Sticky/session preference | Instance that served a prior request | Should not cling to an unhealthy instance |
| Health filtering | Instance probe results | Subject to lag between probe cycles |

Not all filters share the same contract. A **preference** filter may return the full list when no candidates match; a custom **mandatory** filter may return an empty list. Those two behaviors have very different business consequences, especially for tenant isolation or canary deployments.

### Key Ordering Rule: Apply Per-Request Filters After Shared Caching

Suppose request A needs `version=v1` and request B needs `version=v2`. If you cache the list already filtered for request A under a key containing only the service ID, request B could receive the wrong list and find no `v2` instances.

A safer design:

~~~text
Discovery: [A(v1), B(v2), C(v2)]
             |
             v
Cache by service ID: [A, B, C]
             |
             +---- Request A (version=v1) ---> [A]
             |
             +---- Request B (version=v2) ---> [B, C]
~~~

Therefore, let the shared cache layer **see request-independent data**, and apply request-specific filters after retrieving the snapshot from the cache. If you must cache filtered results as well, the cache key must include all conditions affecting the outcome, and you must weigh the risk of key-cardinality explosion.

## 7. Designing the Supplier Chain Based on Needs

Consider the following three patterns as architectural options. They illustrate data flows and do not all need to be applied at once.

### Pattern A: Discovery → Cache → Zone Preference

Suitable when discovery already maintains reliable health status, the registry faces heavy load, and read volume must be reduced. The cache layer stores the registration list; the zone preference layer picks closer candidates if policy allows.

~~~text
Discovery -> CachingServiceInstanceListSupplier
          -> ZonePreferenceServiceInstanceListSupplier
          -> LoadBalancer
~~~

This pattern does not actively probe health endpoints on the client side. If an instance fails while still present in discovery and the cache, requests may fail until the list refreshes or a retry succeeds.

### Pattern B: Discovery → Health Check → Zone Preference

Suitable when the registry does not reflect health status quickly enough and the client needs to verify responsiveness per instance.

~~~text
Discovery -> HealthCheckServiceInstanceListSupplier
          -> ZonePreferenceServiceInstanceListSupplier
          -> LoadBalancer
~~~

The health supplier manages probe cycles and the healthy instance list. Do not add a cache merely out of an assumption that "caching is always good"; first understand how health results are retained and whether discovery already caches.

### Pattern C: Discovery → Cache → Health Check → Per-Request Filter

Consider this when discovery queries are expensive, dedicated health checks are necessary, and per-request filtering has clear rules:

~~~text
Discovery -> Cache discovery data
          -> Scheduled health checks
          -> Per-request filter (zone / hint / policy)
          -> LoadBalancer
~~~

This is a **conditional architecture**, not a universal default across all versions. Ensure the upstream cache does not retain failed lists too long, the health supplier receives discovery updates, and per-request outcomes are never stored in a shared cache. If the health supplier already manages state retention adequately, dropping the extra cache layer is simpler.

## 8. Configuration Example Using `ServiceInstanceListSupplier.builder()`

Spring Cloud LoadBalancer provides a builder to assemble common suppliers within a per-service ID configuration. The example below chooses **Pattern B**, avoiding redundant caching when health checks already manage the resulting list.

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogSupplierConfiguration.class
)
class CatalogLoadBalancerRegistration {
}

// Place outside default component scan scope if registered
// specifically via @LoadBalancerClient.
@Configuration(proxyBeanMethods = false)
class CatalogSupplierConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withHealthChecks()
            .withZonePreference()
            .build(context);
    }
}
~~~

Meaning:

- `withDiscoveryClient()` fetches instances from the discovery mechanism configured in the application.
- `withHealthChecks()` adds health checking before passing candidates to the selector.
- `withZonePreference()` adds zone preference according to the supplier's policy.
- `build(context)` constructs the supplier chain inside the LoadBalancer context.

Builder methods and options should be verified against the Spring Cloud version in use. Service-specific `@LoadBalancerClient` configurations must not accidentally be picked up by component scanning as global configuration for every service ID. You can place this class in a package outside the default component scan path.

Example of a **Pattern A** option replacing health checks with caching:

~~~java
@Bean
ServiceInstanceListSupplier catalogInstanceListSupplier(
        ConfigurableApplicationContext context) {

    return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .build(context);
}
~~~

This is an **alternative** to the bean above, not a duplicate bean declaration in the same context. When building a chain, avoid registering two `ServiceInstanceListSupplier` beans for the same LoadBalancer unintentionally.

### Configuring the Health Endpoint

If the target application exposes a dedicated readiness endpoint, you can configure the path per service ID when your Spring Cloud version supports the corresponding health check properties:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          catalog-service: /actuator/health/readiness
        interval: 15s
~~~

The path and interval above are examples to tune according to topology, startup speed, and real load. Ensure target instances expose this endpoint with appropriate permissions and accurately report readiness to serve traffic. Systems whose discovery layer already removes unhealthy instances may not need client-side polling at all.

### Relationship with HTTP Clients

Once a supplier chain is configured for `catalog-service`, requests from a `RestClient`/`WebClient` built with `@LoadBalanced` or from LoadBalancer-integrated OpenFeign rely on the instance list provided by that chain. Examples:

~~~java
// RestClient with @LoadBalanced RestClient.Builder
catalogRestClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);

// WebClient with @LoadBalanced WebClient.Builder
catalogWebClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class);

// Feign client: @FeignClient(name = "catalog-service")
catalogFeignClient.getItem(itemId);
~~~

These clients differ in threading model and HTTP response handling; **the supplier chain determines the candidate set**, while the LoadBalancer policy determines which instance is selected. Retry and timeout settings still must be configured specifically for the actual HTTP client in use.

## 9. Unintended Interactions Between Filters and Health Checks

### Zone Filtering Before Health Checks

Suppose `catalog-a` is the only instance in `zone-a`, and it is unhealthy, while `catalog-c` in `zone-b` is healthy. If a **mandatory** zone rule removes all instances outside `zone-a` with no fallback, the health-check step ends up with an empty list.

To handle this, clarify the business requirement: is failing over to `zone-b` allowed? If yes, use zone preference with fallback instead of an exclusive filter. If not—due to data residency or latency constraints—returning "no matching instances" is the right outcome and should be handled transparently.

### Caching a List Before an Instance Is Removed

The registry has already removed `catalog-b`, but the cache has not expired yet. Without health checks or proper connection error handling, the client may keep selecting `catalog-b`. Shortening the TTL only narrows the stale-data window; it cannot eliminate the case where an instance dies right after being selected.

Coordinate TTL with discovery propagation lag, health results, timeouts, and bounded retries rather than relying on a single mechanism.

### All Instances Marked Unhealthy by Health Checks

This could indicate a genuine widespread outage, or simply a wrong health path, TLS certificate issue, proxy, firewall, or timeout. Before concluding all instances are dead, probe the health endpoint from the same network environment as the caller and inspect the actual health request/response.

Know whether your supplier falls back when zero healthy instances remain. Never assume the result is always empty across all configurations and versions.

### Caching After a Per-Request Filter

If the cache does not key on hints, zones, or tenant info, placing a filter before the cache can cause later requests to erroneously reuse an earlier request's results. Avoid this design, especially when metadata enforces data boundaries or environment isolation.

## 10. When the Final Candidate List Is Empty

If the final supplier chain emits an empty list, standard selectors like `RoundRobinLoadBalancer` cannot produce a target instance. The selection outcome is typically a no-server response, such as `EmptyResponse` with `hasServer() == false`.

~~~mermaid
flowchart TD
    S["Supplier chain returns list"] --> Q{"Any candidates?"}
    Q -->|Yes| C["Select ServiceInstance by policy"]
    C --> H["HTTP client sends request to instance"]
    Q -->|No| E["No-server response"]
    E --> O["HTTP client reports instance selection failure"]
    O --> R["Application decides retry, fallback, or error response"]
~~~

Distinguish this situation from selecting an instance that then fails to connect, and from a server receiving the request and returning HTTP `503`. Having no instance at selection time means the request was never sent to a target instance. Error messages and metrics should preserve that distinction.

Retries only help if waiting or re-selecting has a chance of producing a different candidate set. If discovery keeps returning an empty list or a filter deliberately excludes all candidates, repeated retries only waste resources. Bound retry attempts, use appropriate backoff, avoid nested retries across client, LoadBalancer, and gateway, and ensure idempotency when requests have side effects.

## 11. Observing the Pipeline Layer by Layer

To investigate root causes accurately, do not merely log "failed to call service." Observe instance counts and status at each stage.

| Metric / Data | Question to answer |
|---|---|
| Service ID | Which service is being routed to? |
| Instance count from discovery | Does the registry know about any instances? |
| Cache hit/miss, entry age | Are we serving a stale list? |
| Healthy instance count | How many instances is the health check keeping or dropping? |
| Instance count after each filter | Which filter changed the candidate count? |
| Selected instance | Where was the request actually sent? |
| Instance selection duration | Is latency coming from discovery, cache, or health checks? |
| Connection errors, timeouts, HTTP status | Did failure occur before or after selection? |
| Retry attempt, previous instance | Did a retry pick the same instance again? |

Combine correlation/trace IDs and instance-selection logs with request metrics. Never log access tokens, cookies, personal data, or sensitive HTTP body contents. For service IDs or hints with high variability, bound metric dimensions to avoid cardinality explosion.

You can use lifecycle hooks like `LoadBalancerLifecycle` for instance selection events, while adding instrumentation at the discovery source and wrappers if you need pre/post-filter counts. Ensure instrumentation does not accidentally create an extra subscription that triggers duplicate discovery or health-check runs.

## 12. Testing Supplier Chain States

Do not test only when every instance is healthy. Your test suite should cover state transitions and cross-layer interactions:

| Scenario | Outcome to verify |
|---|---|
| Discovery returns A, B, C | Final supplier yields the candidate set expected by policy |
| A and C healthy, B unhealthy | B is excluded once health check results update |
| Cache hit | No unnecessary discovery queries while cache remains valid |
| B removed from registry | After refresh, B is no longer a candidate |
| B recovers health | B returns to the candidate set after health updates |
| Zero healthy instances | Error/fallback obeys contract; no requests sent to random hosts |
| Caller in another zone | Zone preference or fallback works as designed |
| Requests A and B have different hints | Shared cache does not leak filtered results across requests |
| Instance dies right after selection | Bounded timeout/retry behaves properly; logs isolate connection error |
| Wrong health endpoint | Metrics/logs expose the misconfiguration |

When testing time-dependent behavior, avoid assuming health checks and caches update instantaneously. Account for refresh intervals, TTL, and emission timing. For asynchronous conditions, wait on updates with a bounded timeout instead of fixed sleeps that cause flaky tests.

## 13. Practical Configuration Guidelines

- If discovery already manages health and caching well, start with a simple pipeline; add suppliers only to solve concrete problems.
- If discovery queries must be throttled, use caching with a TTL aligned to instance churn rate.
- If the registry is slow to mark unhealthy instances, consider a health-check supplier backed by a meaningful readiness endpoint.
- If routing by zone, hint, or metadata is needed, decide explicitly between **preference with fallback** and **mandatory filtering**.
- Place request-dependent filters after the shared list cache to avoid cross-request contamination.
- Observe lists at each layer, instance-selection errors, and HTTP errors, while configuring bounded timeouts and retries.

The `ServiceInstanceListSupplier` chain is where you decide **which instances are eligible for selection**. Caching, health checks, and filtering serve three distinct goals: fetch efficiency, target health, and routing policy. Understanding their relationships and ordering helps Spring Cloud LoadBalancer pick suitable instances while enabling RestClient, WebClient, and OpenFeign to handle empty-list scenarios in an explainable, operable way.
