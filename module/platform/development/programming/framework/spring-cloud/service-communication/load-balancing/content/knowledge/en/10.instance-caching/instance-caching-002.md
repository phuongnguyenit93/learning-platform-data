# LoadBalancer Cache and Discovery Client Cache

In a microservice architecture, the number of `ServiceInstance` entries for a service can change continuously: new replicas are deployed, old replicas stop running, or a replica is marked unavailable. Client-side load balancing must maintain a sufficiently fresh instance list to choose targets accurately, while avoiding remote registry queries on every request if doing so increases latency and load on the discovery infrastructure.

Because of this, a Spring Cloud application can have **multiple cache layers related to the instance list**. The two most easily confused layers are the **Spring Cloud LoadBalancer cache** and the **service discovery client cache**. Both can reduce queries, yet they operate at different boundaries and have their own refresh cycles.

This lesson belongs to the **Instance Caching** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The module focuses on client-side load balancing: selecting a `ServiceInstance` by service ID, discovery, health checks, and routing policies; communicating via `RestClient`, `WebClient`, and OpenFeign; configuring retries/timeouts; and observing errors. The goal here is to understand each cache layer in order to choose the right design, avoid **double caching**, and investigate situations where requests are still routed to old instances.

## 1. What Problem Does Instance List Caching Solve?

Suppose `order-service` calls `inventory-service` via its logical hostname:

~~~http
GET http://inventory-service/internal/instance
~~~

The registry knows about three replicas of `inventory-service`:

~~~text
inventory-service
  ├─ inv-1: http://10.1.0.11:8080
  ├─ inv-2: http://10.1.0.12:8080
  └─ inv-3: http://10.1.0.13:8080
~~~

When `RestClient`, `WebClient`, or OpenFeign is integrated with Spring Cloud LoadBalancer, the client does not send requests directly to this logical name as a physical address. LoadBalancer receives the service ID, obtains the `ServiceInstance` list from `ServiceInstanceListSupplier`, picks an instance, and executes the HTTP call to the chosen host/port.

If the instance list can be read quickly from memory, target selection can cut down registry lookups. However, caching accepts a trade-off: **lower lookup cost in exchange for the risk of seeing stale data**.

A cached snapshot can run into these situations:

- A new replica has registered but does not yet appear in the caller's list.
- A replica has been removed from the registry but is still selected because the caller uses an old snapshot.
- An instance's `zone`, `weight`, or `version` metadata changed, but the client has not received the update yet.
- The registry is unavailable; the cache may temporarily let the caller use prior information, without guaranteeing the instances in the snapshot are still healthy.

The cache stores information about **known instances**, not proof that an instance will definitely handle a request successfully.

## 2. Where Are the Two Cache Layers Located?

You need to distinguish the **registry** (source of truth), the **discovery client** (library fetching registry data), and **Spring Cloud LoadBalancer** (selecting an instance to call).

~~~mermaid
flowchart LR
    subgraph Registry["Discovery infrastructure"]
        R["Registry / registration list"]
    end
    subgraph Caller["Caller application"]
        D["Discovery client"]
        DC["Discovery client cache or snapshot"]
        LBC["Spring Cloud LoadBalancer cache"]
        S["ServiceInstanceListSupplier"]
        LB["LoadBalancer selects instance"]
        H["HTTP client"]
    end
    R --> D
    D --> DC
    DC --> S
    S --> LBC
    LBC --> LB
    LB --> H
~~~

The diagram shows **possible cache locations**; it does not claim every discovery implementation maintains two separate layers in the exact same way. In some libraries, the cache is an internal structure of the discovery client with no synchronous network call on every instance lookup. In other applications, the discovery client queries on demand and only LoadBalancer caches.

### Quick Comparison

| Criterion | LoadBalancer cache | Discovery client cache |
|---|---|---|
| Belongs to | Spring Cloud LoadBalancer | Discovery library: Eureka, other adapters |
| Primary data | List of `ServiceInstance` provided by the supplier, per service ID | Registry/instance snapshot or data managed by the discovery client |
| Read point | Before LoadBalancer picks an instance | When the application or supplier queries the discovery client |
| Refresh mechanism | TTL/eviction and re-reading the delegate | Poll, watch, refresh, or implementation-specific mechanism |
| Configuration | `spring.cloud.loadbalancer.cache.*` and supplier chain | Discovery client's own property group |
| Risk | Caches an additional snapshot on top of discovery | Client-side snapshot lags behind registry updates |
| Question to check | Has LoadBalancer's TTL expired and re-queried the source? | Does the discovery client know about the registry change yet? |

**Do not equate** LoadBalancer-side caching with HTTP response caching, DNS caching, or connection pooling. They solve different problems. In this lesson, "cache" focuses solely on the **instance list used for target selection**.

## 3. How Does the LoadBalancer Cache Work?

In Spring Cloud LoadBalancer, `ServiceInstanceListSupplier` provides the candidate list. A caching supplier, commonly known via `CachingServiceInstanceListSupplier`, can wrap a source supplier to reuse the retrieved list.

Simplified flow:

~~~text
LoadBalancer needs the list for inventory-service
   |
   v
CachingServiceInstanceListSupplier
   |
   +--> Cache hit: returns the still-valid list
   |
   +--> Cache miss/expired:
           delegate.get()
              |
              v
        Discovery-backed supplier
              |
              v
        New ServiceInstance list
              |
              v
        Store in cache and return result
~~~

The cache is generally organized by service ID; however, **what list gets stored** depends on where the decorator is placed in the supplier chain.

For example:

~~~text
Discovery source -> LoadBalancer cache -> Zone filter -> LoadBalancer
~~~

With this ordering, the cache holds the list from discovery. The zone filter uses the cached data to choose instances matching the zone.

If reversed to:

~~~text
Discovery source -> Request-dependent filter -> LoadBalancer cache -> LoadBalancer
~~~

then the cache risks holding the filtered result from a previous request and misapplying it to subsequent requests if the cache key does not fully capture the filter context.

**Rule of thumb:** Place the cache close to the discovery-fetching supplier, before request-specific filtering steps, unless you have verified the cache-key mechanism for that specific case.

## 4. Configuring the LoadBalancer Cache

Spring Cloud LoadBalancer provides cache properties under `spring.cloud.loadbalancer.cache`. Example customizing TTL and capacity:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 256
~~~

Meaning:

- `enabled: true`: enables the LoadBalancer caching mechanism when the corresponding supplier and auto-configuration use it.
- `ttl: 20s`: sets the lifetime of a cache entry according to the policy supported by the implementation.
- `capacity: 256`: limits cache capacity; this is **not** the maximum number of replicas a service can have.

TTL is a trade-off parameter. A short TTL triggers more frequent re-reads from the source at higher lookup cost. A long TTL reduces source reads but can extend the window where callers use stale information.

Do not treat TTL as a strict deadline between a registry change and every request reaching the right target. Entry creation time, eviction behavior, discovery client refresh intervals, and health marking all affect actual update timing.

### Choosing a Cache Implementation

Spring Cloud LoadBalancer can use a default cache implementation; when Caffeine is on the classpath and properly configured, Caffeine can be used for the LoadBalancer cache. Example Caffeine configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        caffeine:
          spec: maximumSize=500,expireAfterWrite=20s
~~~

With a Caffeine `spec`, policies like size and expiration live inside the spec string itself. Do not set both `ttl`/`capacity` and `caffeine.spec` assuming both groups apply identically: **the explicit spec may override default TTL/capacity settings**. When switching cache providers, check the documentation for your exact Spring Cloud and Caffeine versions.

A system with few service IDs but many instances per service does not necessarily require a huge capacity: the cache stores lists per service, rather than always assigning one separate entry per replica.

## 5. Building a Caching Supplier Chain

When you need to customize the supplier for a service whose discovery has no cache of its own, you can configure the builder:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Attach the configuration to the service ID:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class CallerApplication {
}
~~~

Design notes:

1. `withDiscoveryClient()` serves as the source producing the `ServiceInstance` list.
2. `withCaching()` adds a caching layer for data from the source.
3. `@LoadBalancerClient(name = "inventory-service", ...)` scopes the configuration to that specific service ID.
4. Place `InventoryLoadBalancerConfiguration` **outside normal component scan scope** of the application, or exclude it from scanning, so this bean does not accidentally become a global configuration.
5. Do not declare two competing supplier beans in the same LoadBalancer context. This configuration is **a replacement**, not something to append onto an already-registered default chain.

This example illustrates the structure only and depends on compatible Spring Boot/Spring Cloud versions. If the discovery source already caches, reconsider calling `withCaching()` instead of leaving both layers enabled by default.

## 6. Discovery Client Cache: The Eureka Example

Not all discovery clients behave the same way. **Eureka is a classic example with client-side caching.**

The Eureka client typically fetches and maintains a snapshot of instance information from the Eureka Server periodically. When the application calls discovery APIs such as `DiscoveryClient.getInstances("inventory-service")`, the library can return data from its local snapshot instead of making a synchronous network query on that call.

Overview model:

~~~mermaid
sequenceDiagram
    participant I as Inventory replica
    participant ES as Eureka Server
    participant EC as Caller's Eureka client
    participant S as InstanceListSupplier
    participant LB as Spring Cloud LoadBalancer
    I->>ES: Register / heartbeat / status update
    EC->>ES: Periodically refresh registry
    ES-->>EC: Registry snapshot or delta
    LB->>S: Request instance list
    S->>EC: getInstances("inventory-service")
    EC-->>S: List from local data
    S-->>LB: ServiceInstance list
~~~

An illustrative Eureka client configuration:

~~~yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
~~~

The `registry-fetch-interval-seconds` property controls how often the Eureka client fetches the registry. It is part of the discovery-side snapshot update process, **not the LoadBalancer cache TTL**.

Beyond client-side polling, the Eureka Server also has heartbeat intervals, lease evaluation, instance status transitions, and potentially a server response cache layer. Consequently, a replica's state change may not appear immediately in the registry snapshot used by the caller.

For other discovery clients:

- **Consul:** lookup, refresh, and caching behavior depend on the discovery client type, Consul configuration, and how it queries catalog/health. Do not assume the Consul client has a local cache like Eureka.
- **Kubernetes:** endpoint information may come through API/watch or another adapter. Sync latency depends on the implementation; do not apply Eureka cache settings to Kubernetes.
- **SimpleDiscoveryClient:** data is declared statically in configuration. It does not automatically remove addresses just because a process stopped; this is not a dynamic registry cache.

Regardless of the implementation, what you must verify is **which list the caller currently sees from the discovery client** and which mechanism updates that list.

## 7. Double Caching: When Two Caches Hold Snapshots

Suppose an application uses Eureka with two data layers:

~~~text
Eureka Server
    |
    v
Eureka client snapshot (periodically refreshed)
    |
    v
LoadBalancer cache (separate TTL)
    |
    v
RoundRobinLoadBalancer
    |
    v
HTTP request to replica
~~~

If a replica is removed from the registry, two delays can occur:

1. **Discovery client has not refreshed yet:** Eureka Server already knows the replica was removed, but the caller's snapshot still contains it.
2. **LoadBalancer cache TTL has not expired yet:** the discovery client already knows the replica was removed, but LoadBalancer keeps serving the old list it cached earlier.

This is **double caching**. Both delays do not always occur in full, but it makes reasoning about when changes become visible harder because each layer has its own update policy.

### Illustrative Timeline

~~~text
t0     Registry and caller both know A, B, C
t1     C stops operating
t2     Registry detects C is no longer valid
t3     Discovery client refreshes; list now has A, B
t4     LoadBalancer cache TTL expires; re-reads A, B
t5     New requests only choose between A and B
~~~

These timestamps are explanatory examples, **not SLAs or fixed timings**. Depending on when the cache was populated, order and delay can vary. If you only disable the LoadBalancer cache while the Eureka client has not updated, the caller can still choose C; conversely, if the Eureka client has updated while the LoadBalancer cache has not expired, the caller can also keep choosing C.

Spring Cloud LoadBalancer recommends **not layering an extra LoadBalancer cache** on top of a discovery client that already caches adequately, with Eureka being the prime example.

## 8. Configuration to Avoid Double Caching with Eureka

When using a Eureka client that already maintains a local registry, a sensible approach is to let Eureka manage the snapshot and **disable the Spring Cloud LoadBalancer cache**:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false

eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
~~~

At this point, the caller can read the list from the discovery-backed supplier and use the Eureka client's snapshot without needing a second LoadBalancer TTL.

If you explicitly declared a supplier chain with the builder, **also remove `withCaching()`** from your custom configuration:

~~~java
@Bean
ServiceInstanceListSupplier serviceInstanceListSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .build(context);
}
~~~

Do not intentionally disable the LoadBalancer cache via properties while manually constructing a caching decorator, because cache manager initialization and usage also depend on the library version's auto-configuration conditions.

Choosing a shorter Eureka registry fetch interval can reduce update latency at the cost of more exchanges with the server. Weigh the number of callers, instance churn frequency, and deployment characteristics instead of dropping every interval to an extreme minimum.

**Disabling one cache layer does not replace health checks.** Even a fresh registry snapshot does not guarantee an instance is healthy at the exact moment an HTTP request is sent.

## 9. For Discovery Without Its Own Cache: Consider LoadBalancer Cache

If the discovery client performs a network query for each list fetch and lacks effective caching, the LoadBalancer cache can help reduce network cost. A possible configuration is:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 15s
        capacity: 256
~~~

In that case, the supplier chain can use `withDiscoveryClient().withCaching()` as shown earlier.

However, before deciding, answer these questions:

- Does the discovery client already have a local cache or watch-based snapshot?
- How many instance-list lookups actually produce network requests?
- How frequently does the list change during scaling or deployments?
- How severe is the impact of sending a request to a stale instance?
- Are there health or zone filters that need fresh data immediately?
- Are many callers querying the same registry and causing significant load?

There is no universally "best" TTL for every system. The `15s` example is only a starting point to test, measure in practice, and tune based on discovery latency, error rates, and deployment patterns.

## 10. Comparing Two Common Deployment Patterns

| Scenario | Starting Choice | Reason |
|---|---|---|
| Eureka client maintaining local registry snapshot | Prefer disabling LoadBalancer cache | Avoid storing the same list across two TTL/refresh cycles |
| Discovery client without cache querying the source frequently | Consider enabling LoadBalancer cache | Reduce registry query volume from callers |
| SimpleDiscoveryClient with a static list | Caching usually does not solve freshness | The source itself does not automatically remove dead instances |
| Watch/snapshot-based discovery | Check built-in cache before adding a new layer | Data may already be maintained locally and updated by watches |
| Only a few services are very sensitive to replica changes | Consider per-service config or tuning discovery | Avoid forcing one ill-fitting cache policy onto all services |
| Supplier has request-dependent filters | Cache near discovery source, never unconditionally cache filtered results | Prevent returning one request's candidate list to another request |

When unsure whether the discovery client caches, check the documentation and behavior of your specific version. Never assume "using service discovery" automatically means "an appropriate cache already exists."

## 11. Impact of Caching on Health Checks and Retries

A cache only reflects previously read data, so you must distinguish **registered**, **considered healthy**, and **actually completing an HTTP request**.

### Health Checks

A `HealthCheckServiceInstanceListSupplier` or registry health mechanism can filter out unhealthy instances, yet these systems have different check intervals and health criteria. If the cache sits at an unsuitable position in the supplier chain, it can retain a list that health or other filters have not updated yet.

Health checks should use an endpoint that reflects readiness to serve, not merely an endpoint that always returns `200 OK`. They must also account for timeouts, check intervals, and the policy when all instances are filtered out.

### Retries

When a client sends a request to a stopped instance, retries may try again on the same or another instance depending on configuration. Retrying does not make the cache fresher and does not guarantee choosing a healthy target. In particular, retrying non-idempotent requests such as a resource-creating `POST` must be designed carefully to avoid duplicate side effects.

Relationship between mechanisms:

~~~mermaid
flowchart TD
    A["List from discovery/cache"] --> B["Health/zone/metadata filter if enabled"]
    B --> C["LoadBalancer picks ServiceInstance"]
    C --> D["HTTP request"]
    D --> E{"Success?"}
    E -- Yes --> F["Return response"]
    E -- No --> G["Timeout/retry policy"]
    G --> H{"Retry allowed?"}
    H -- Yes --> C
    H -- No --> I["Return error / business fallback"]
~~~

This diagram is conceptual. Some retry configurations ask the supplier to select an instance again and may include policies to avoid the just-failed instance; not all retries follow the exact same path. Measure HTTP attempt counts separately from logical request counts.

## 12. Hands-On: Observing List Update Latency

The objective of this exercise is to identify which layer holds a stale list, not merely to check whether round robin distributes requests evenly.

### Setup

Use one caller `order-service`, two `inventory-service` replicas, and a chosen discovery implementation. Each replica exposes the endpoint:

~~~http
GET /internal/instance
~~~

Example response:

~~~json
{
  "serviceId": "inventory-service",
  "instanceId": "inv-1"
}
~~~

The caller uses `RestClient`, `WebClient`, or OpenFeign with LoadBalancer integration to send multiple requests using the logical hostname `inventory-service`.

### Test Procedure

1. Start `inv-1` and `inv-2`, ensuring discovery sees both.
2. Call through LoadBalancer and confirm responses include two distinct `instanceId` values.
3. Record the instance list from the discovery client **on the caller** and the final list returned by `ServiceInstanceListSupplier`, if the application has observability instrumentation.
4. Stop `inv-2` and note the stop timestamp.
5. Track when the registry updates, when the caller's discovery client no longer contains `inv-2`, and when the final supplier stops returning `inv-2`.
6. Record connection error or timeout rates during the transition window.
7. Vary the LoadBalancer cache TTL in a test environment and compare the timestamps again.

Do not use static `SimpleDiscoveryClient` expecting step 5 to happen automatically. When the list is hardcoded in YAML, stopping a process does not update the discovery source on its own. Use a dynamic registry or a mock source whose data can change to test freshness.

### Observation Table

| Point in Time | Registry | Caller's Discovery Client | Final Supplier | HTTP Outcome |
|---|---|---|---|---|
| Before stopping | `inv-1, inv-2` | `inv-1, inv-2` | `inv-1, inv-2` | Both handle requests |
| Registry updated | `inv-1` | May still contain `inv-2` | May still contain `inv-2` | Some requests may fail |
| Discovery refreshed | `inv-1` | `inv-1` | May still contain `inv-2` if LB cache has not expired | Errors may still occur |
| Both layers updated | `inv-1` | `inv-1` | `inv-1` | Only `inv-1` selected |

This table is a **theoretical scenario**, not actual run output. In a setup with only discovery caching, the final supplier column typically reads updated discovery data without waiting for an extra LoadBalancer TTL.

## 13. Diagnosing When Clients Still Select Removed Instances

If the client keeps calling `inv-2` even though it is no longer expected, trace in order from source to LoadBalancer:

~~~mermaid
flowchart TD
    A["Caller still picks old instance"] --> B{"Instance still in registry?"}
    B -- Yes --> C["Check deregistration, heartbeat, lease, health"]
    B -- No --> D{"Instance still in caller's discovery client?"}
    D -- Yes --> E["Check discovery polling/watch/refresh"]
    D -- No --> F{"Instance still in final supplier?"}
    F -- Yes --> G["Check LB cache TTL, cache placement, filters"]
    F -- No --> H["Check target selection logs, HTTP connections, proxy, retries"]
~~~

Common signs:

- **Registry does not know the replica died:** heartbeat/lease/health has not updated or deregistration failed.
- **Registry is right, caller is wrong:** discovery client snapshot has not refreshed or has connection errors reaching the registry.
- **Discovery client is right, supplier is wrong:** likely a LoadBalancer cache or custom supplier holding stale data.
- **Supplier is right but HTTP still fails:** another instance may also be failing; the fault may lie in DNS, TLS, connection pool, timeout, or the target service.
- **Weights or zones do not change:** updated metadata has not propagated across layers, or the filter/weighted supplier is not enabled in that service's context.

A useful technique is controlled timestamped logging of three items: **service ID**, **candidate count/IDs at each layer**, and **selected instance**. Do not log tokens, personal data, or sensitive metadata payloads. For metrics, avoid unbounded-cardinality labels, especially request IDs or ephemeral instance identities.

## 14. When Should You Tune TTL and Discovery Intervals?

Do not optimize caching based solely on a single average latency measurement. Consider at least four variables:

| Variable | TTL too long / slow refresh | TTL too short / overly fast refresh |
|---|---|---|
| Registry read frequency | Lower | Higher |
| Speed of seeing new replicas | Slower | Potentially faster |
| Window where removed replicas can be selected | Potentially longer | Potentially shorter |
| Load on discovery and callers | Typically lower | Can increase significantly |

Operational notes:

- **Measure actual cost** of discovery lookups before adding a cache layer.
- **Check registry resilience**, especially when many callers refresh simultaneously.
- **Tune to your scale/deploy cadence:** systems with frequent instance churn are more sensitive to stale snapshots.
- **Set sensible failure bounds:** connect timeouts, read timeouts, and controlled retries limit the blast radius when a broken instance is picked.
- **Keep policies consistent:** if callers use different TTLs and refresh intervals, routing outcomes across callers can diverge at the same point in time.
- **Do not shrink TTL to tiny values** and treat it as instant health checking. Cache freshness, heartbeats, and HTTP transport are separate mechanisms.

When using Eureka, changing `registry-fetch-interval-seconds` affects Eureka client polling. Changing `spring.cloud.loadbalancer.cache.ttl` only matters if the LoadBalancer cache layer is active. The two properties do not substitute for one another.

## 15. Misconceptions to Avoid

**"LoadBalancer cache and Eureka cache are the same thing."** False. They belong to two different layers, can both cache the instance list, and have separate update lifecycles.

**"Lowering LoadBalancer TTL to 1 second makes every removed replica disappear in 1 second."** False. If the discovery snapshot has not updated or the registry has not detected the dead instance, LoadBalancer still reads stale data from the source.

**"Enabling `withCaching()` always improves stability."** Not necessarily. It can cut discovery queries, but with a discovery client that already caches well, adding another cache layer can sometimes worsen staleness.

**"A low cache TTL is enough; health checks or timeouts are unnecessary."** False. An instance can fail right after being selected. Timeouts, health checks, and retries address different aspects.

**"Static `SimpleDiscoveryClient` automatically drops dead instances after TTL expires."** False. TTL only makes the caller re-read the source; if the static source still lists the dead host, the result remains unchanged.

**"Cache capacity equals the number of replicas."** Conceptually false. The LoadBalancer cache stores list collections keyed by service ID; entry counting depends on the implementation, not simply one entry per replica.

## 16. Production Checklist for Cache Configuration

| Item | Verification Question |
|---|---|
| Discovery implementation | Are you using Eureka, Consul, a Kubernetes adapter, or a static source? |
| Discovery-side cache | Does that library keep a local snapshot/cache? How does it refresh? |
| LoadBalancer cache | Is it enabled? Is `withCaching()` in a custom supplier chain? |
| Double caching | Are two active cache layers genuinely necessary? |
| TTL/capacity | Do you have operational rationale and metrics backing those values? |
| Caffeine | Is the dependency present? Does `caffeine.spec` override other properties? |
| Scope | Are the supplier and cache policy applied to the intended service IDs? |
| Health and retry | Have dead-instance eviction, timeouts, retries, and idempotency been addressed? |
| Freshness test | Have you measured the delay from replica loss until callers stop selecting it? |
| Observability | Can you compare the registry, discovery snapshot, and final supplier? |

## 17. Summary

- **LoadBalancer cache** holds the list provided by the supplier to reduce the cost of re-fetching candidates; it has TTL and capacity and can be configured via `spring.cloud.loadbalancer.cache.*`.
- **Discovery client cache** sits closer to the registry source; for example, the Eureka client typically maintains a local snapshot and refreshes periodically.
- **Double caching** can cause callers to keep selecting stale instances even after one layer updates; therefore, Spring Cloud LoadBalancer generally recommends avoiding an extra cache if the discovery client already caches appropriately.
- With Eureka, a common option is `spring.cloud.loadbalancer.cache.enabled=false` and omitting `withCaching()` from custom supplier chains.
- For discovery without effective caching, the LoadBalancer cache can be helpful, though TTL must reflect the trade-off between freshness and lookup cost.
- Never treat caching as health checks, retries, circuit breaking, or HTTP response caching.
- When investigating misrouted requests, inspect in order: **registry → discovery client snapshot → supplier/LoadBalancer cache → selected instance → HTTP transport**.

Understanding the boundaries between cache layers helps you configure Spring Cloud LoadBalancer cleanly, reduce requests to unavailable instances, and explain accurately why traffic distribution across replicas changes over time.
