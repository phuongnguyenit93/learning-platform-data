# Conditions for Using Caffeine and the Default Cache Mechanism

In **Spring Cloud LoadBalancer**, choosing a `ServiceInstance` typically starts by fetching the instance list for a **service ID** via `ServiceInstanceListSupplier`. If every request had to re-read discovery, the application could increase latency and load on the registry. The **instance cache** retains a recent list so subsequent selections can reuse it, at the cost of managing data freshness.

This lesson belongs to the **Instance Caching** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. Its goal is to understand **when LoadBalancer uses Caffeine, when it uses the default cache, how to configure TTL/capacity**, and how to evaluate correctness when discovery, health checks, or routing policies change. This knowledge applies to service-to-service communication over **RestClient**, **WebClient**, and **OpenFeign** integrated with Spring Cloud LoadBalancer; the HTTP client type itself does not decide the instance cache implementation.

> In this lesson, a "replica" means an instance providing the same service. LoadBalancer's cache stores **instance lists**, not HTTP responses, business data, cookies, or network connections.

## 1. Where Does Caching Sit in the LoadBalancer Architecture?

A typical call flow:

~~~mermaid
flowchart LR
    A["Caller: order-service"] --> B["RestClient / WebClient / OpenFeign"]
    B --> C["LoadBalancer by service ID"]
    C --> S["ServiceInstanceListSupplier"]
    S --> K{"Valid cache entry?"}
    K -->|Cache hit| L["Cached instance list"]
    K -->|Cache miss / TTL expired| D["DiscoveryClient fetches list"]
    D --> L
    L --> F["Appropriate filters / preferences"]
    F --> R["Select ServiceInstance"]
    R --> H["HTTP request to host:port"]
~~~

`CachingServiceInstanceListSupplier` wraps a discovery-backed supplier and reuses the instance list across selections. The caching mechanism runs **before the target selection step**. Round Robin, Random, or another algorithm still chooses an instance from the supplied list.

If the cache holds `[catalog-a, catalog-b]`, and `catalog-b` later stops while the cache has not refreshed, the algorithm can still select `catalog-b`. Conversely, a new instance `catalog-c` will not be selected until the list refreshes.

**Caching lowers list lookup cost; it does not check instance health or guarantee HTTP requests succeed.**

## 2. Conditions for Using Caffeine vs. the Default Cache

Spring Cloud Commons provides two cache implementations for LoadBalancer. When caching is enabled and the LoadBalancer cache component is used, the default choice depends on the **runtime classpath**:

| Condition | Selected Implementation | Meaning |
|---|---|---|
| `com.github.ben-manes.caffeine:caffeine` dependency on classpath | **Caffeine**-backed cache | Uses the Caffeine caching engine for instance lists |
| No Caffeine dependency | `DefaultLoadBalancerCache` bundled with `spring-cloud-starter-loadbalancer` | Still caches; avoids querying discovery every time |
| `spring.cloud.loadbalancer.cache.enabled=false` | Disables LoadBalancer cache via supported configuration | Supplier does not use this cache layer; discovery may still cache separately |
| Custom supplier config omits cache from the chain | No `CachingServiceInstanceListSupplier` in that chain | Behavior depends on the specific supplier, even with Caffeine on the classpath |

This marks an important distinction between **choosing the cache backend** and **deciding whether to cache the instance list**.

- Having Caffeine on the classpath is the condition for Spring Cloud LoadBalancer to use the **Caffeine-backed implementation** under appropriate cache configuration.
- Missing Caffeine does **not** mean caching is disabled: Spring Cloud ships a default cache implementation.
- Simply adding the Caffeine dependency does **not** automatically add a cache layer to a custom supplier that does not include caching.
- `spring.cloud.loadbalancer.cache.enabled` is the LoadBalancer-level cache flag; custom supplier configurations must also be checked when evaluating runtime behavior.

### Why Say "Runtime Classpath"?

A project might declare Caffeine in source yet have the dependency excluded by build configuration, or scoped only to `testImplementation`. When the application actually runs, selection depends on the classes present on the runtime classpath, not on what appears in documentation.

Therefore, when diagnosing which cache an application uses, inspect the **dependency tree / runtime classpath** and the actual Spring context configuration.

## 3. Adding the Caffeine Dependency

With compatible Spring Boot/Spring Cloud versions and proper dependency version management, Caffeine can be added as follows.

**Gradle (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

**Maven:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>com.github.ben-manes.caffeine</groupId>
        <artifactId>caffeine</artifactId>
    </dependency>
</dependencies>
~~~

This example assumes the project already uses the Spring Cloud BOM and compatible dependency management. If your build does not manage the Caffeine version, specify a compatible version for your setup.

There is no need to create a separate `@Cacheable` bean for LoadBalancer to recognize Caffeine under standard auto-configuration. Instance list caching is a **Spring Cloud LoadBalancer** mechanism, even when using Caffeine as the backend. Do not confuse it with caching method return values using Spring Cache.

### When Should You Choose Caffeine?

Caffeine is useful when the application handles high service-call volume, needs an efficient in-process cache, and wants explicit control over eviction policies or entry limits. Especially when a single caller instance invokes many service IDs, capping size and expiration via a Caffeine spec can be convenient.

However, **you do not need Caffeine just to enable caching**, since LoadBalancer already includes `DefaultLoadBalancerCache`. Actual benefits should be measured: discovery lookup count, selection latency, memory usage, cache hits/misses, and delay before instance changes appear.

## 4. Default Cache When Caffeine Is Absent

When `spring-cloud-starter-loadbalancer` is present and Caffeine is absent from the runtime classpath, Spring Cloud uses `DefaultLoadBalancerCache` for LoadBalancer caching. This is a built-in cache implementation, distinct from invoking a base supplier that calls discovery on every selection.

According to current Spring Cloud Commons documentation, the default general cache settings are:

| Property | Default Value | Meaning |
|---|---:|---|
| `spring.cloud.loadbalancer.cache.enabled` | `true` | Caching is enabled in default configuration |
| `spring.cloud.loadbalancer.cache.ttl` | `35s` | Time to live measured from cache write |
| `spring.cloud.loadbalancer.cache.capacity` | `256` | **Initial capacity**, initial allocation capacity |

Note: **`capacity=256` is the documented initial capacity; it must not be interpreted as a hard cap of 256 instances or 256 requests.** If you need an explicit bound on cache entries in Caffeine, use a policy such as `maximumSize` in the Caffeine specification.

The `35s` and `256` defaults are published in the current Spring Cloud Commons documentation; if your project pins a different release train, check that version's configuration properties reference.

### Cache Miss, Hit, and Expiration

~~~mermaid
sequenceDiagram
    participant App as Request caller
    participant Cache as Instance cache
    participant Discovery as DiscoveryClient
    participant LB as LoadBalancer

    App->>Cache: Call 1: look up catalog-service
    Cache->>Discovery: Cache miss: fetch instance list
    Discovery-->>Cache: [A, B]
    Cache-->>LB: [A, B]
    App->>Cache: Call 2: same service ID
    Cache-->>LB: Cache hit: [A, B]
    Note over Cache: Entry expires after TTL
    App->>Cache: Call 3: same service ID
    Cache->>Discovery: Read fresh list
    Discovery-->>Cache: [A, C]
    Cache-->>LB: [A, C]
~~~

This sequence is illustrative and does not mean every cache miss generates a network call: the discovery client itself may hold a list in memory. TTL is the **expiration period measured from write time**, not an active push schedule from the registry to every cache instance.

## 5. Configuring General TTL and Capacity

Both parameters can be adjusted in `application.yml`:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 128
~~~

Meaning:

- `enabled: true` enables caching under the general configuration.
- `ttl: 20s` expires entries 20 seconds after write.
- `capacity: 128` configures the LoadBalancer cache initial capacity via the general property.

`ttl` binds as a Spring Boot `Duration`. Choosing a TTL should consider registry update speed, how often instances are created/terminated, and application sensitivity to stale addresses.

For example, an environment with frequent autoscaling or rolling deployments may need a shorter TTL than a mostly static system. Yet a short TTL increases discovery reads; if discovery is overloaded, that can backfire.

**Do not treat TTL as a guarantee that every client detects dead instances within that window.** Data may be cached in the discovery client itself, health results follow their own update cycle, and an instance can fail immediately after being selected.

## 6. Using Caffeine Specification: Explicit Config Overrides General Config

When Caffeine is available, you can use the property:

`spring.cloud.loadbalancer.cache.caffeine.spec`

Example of **an alternative configuration** replacing the general block above:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        caffeine:
          spec: "initialCapacity=64,maximumSize=500,expireAfterWrite=20s"
~~~

Spec components:

| Caffeine Component | Effect |
|---|---|
| `initialCapacity=64` | Hint for initial capacity |
| `maximumSize=500` | Caps entry count via Caffeine's eviction policy |
| `expireAfterWrite=20s` | Expires entries based on write timestamp |

**Important rule:** when `spring.cloud.loadbalancer.cache.caffeine.spec` is supplied, Spring Cloud LoadBalancer uses that spec to build the cache and **overrides general cache settings**, including `ttl` and `capacity`. If you configure both simultaneously:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 10s
        capacity: 256
        caffeine:
          spec: "maximumSize=500,expireAfterWrite=40s"
~~~

then do not expect `ttl: 10s` and `capacity: 256` to still apply to the Caffeine cache; the relevant policies follow the Caffeine spec. Keep **one intentional source of configuration** to avoid conflicting values that mislead operators.

If you write a custom Caffeine spec and omit an expiration policy, entry retention can behave differently from LoadBalancer's default TTL. Explicitly declare `expireAfterWrite` when instance data needs automatic expiration, and consider `maximumSize` when bounding entry count.

Caffeine specs allow many other options, though you should only use options verified against your actual Caffeine version. **An entry limit is not an instance-count limit per entry**: a single service ID can map to a list containing many `ServiceInstance` entries.

## 7. Position of CachingServiceInstanceListSupplier in the Chain

When building a custom supplier chain, the position of `CachingServiceInstanceListSupplier` matters just as much as picking the cache backend. Per Spring Cloud guidance, place caching **right after the supplier that fetches instances over the network**, before other filters.

Example:

~~~text
DiscoveryClientServiceInstanceListSupplier
               |
               v
CachingServiceInstanceListSupplier
               |
               v
ZonePreferenceServiceInstanceListSupplier
               |
               v
RoundRobinLoadBalancer selects instance
~~~

Reason: the cache should hold the baseline list per service ID, not results transformed for a specific request.

Suppose request A needs metadata `version=v1`, while request B needs `version=v2`. Caching the list already filtered for A when the cache key only distinguishes service ID would hand B the wrong list.

~~~text
Discovery returns: [A(v1), B(v2), C(v2)]
                     |
                     v
            Cache [A, B, C]
              /          \
       request v1       request v2
           [A]            [B, C]
~~~

This pattern prevents a shared cache from mixing data across different requests. In systems enforcing tenant/zone/version isolation rules, misplacing the cache not only affects performance—it can violate routing policies.

### Custom Supplier Example

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogLoadBalancerConfiguration.class
)
class LoadBalancerClientRegistration {
}

// Place this class outside the default component scan scope
// if it is loaded specifically via @LoadBalancerClient.
class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogInstanceSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .withZonePreference()
            .build(context);
    }
}
~~~

`withDiscoveryClient()` retrieves instances from the configured discovery mechanism. `withCaching()` adds the caching step; `withZonePreference()` applies zone preference afterward. `build(context)` builds the supplier chain for the corresponding LoadBalancer context.

This example illustrates a custom configuration option and **does not force every application to register custom beans** if defaults suffice. Avoid accidentally pulling `catalog-service`'s dedicated configuration class into shared component scanning for other services.

## 8. Already Caching at the Discovery Layer: Avoid Stacked Caching

Some discovery implementations, such as `EurekaDiscoveryClient`, already maintain their own instance list mechanism. Adding a LoadBalancer cache layer on top means data can pass through two update cycles:

~~~mermaid
flowchart LR
    A["Registry updates instance"] --> B["Discovery client cache"]
    B --> C["LoadBalancer cache"]
    C --> D["Selector"]
    D --> E["HTTP client"]
~~~

Suppose the registry removes B at time T, yet the discovery client refreshes only after an interval. LoadBalancer keeps reading the old list from discovery and may also hold its own cached entry. **LoadBalancer's TTL is not the sole upper bound on convergence latency**, because the discovery layer is also involved.

Per Spring Cloud documentation, when `DiscoveryClient` already caches instances, consider **disabling the LoadBalancer cache** to avoid two cache layers causing unnecessary stale data.

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Disabling `spring.cloud.loadbalancer.cache.enabled` does not disable all of discovery or internal caches in other registries/clients. With custom supplier chains, also check whether `withCaching()` is added manually.

Do not blindly disable caching just because someone says a registry "has a cache": verify whether it actually serves cached data, what its update timing looks like, how many discovery queries happen without LoadBalancer caching, and the latency impact. The goal is minimizing **data staleness and overhead**, not maximizing cache layer count.

## 9. Relationship with Health Checks

Caching and health checks solve two different problems:

- **Cache**: reduces instance-list lookup cost at the expense of some update delay.
- **Health check**: observes a signal about each instance's responsiveness.
- **LoadBalancer**: picks one instance from the final candidate list.

`HealthCheckServiceInstanceListSupplier` can maintain and emit updated healthy lists on its own schedule. Spring Cloud's custom supplier documentation recommends using **either `CachingServiceInstanceListSupplier` or `HealthCheckServiceInstanceListSupplier`** in that chain pattern, placing the chosen supplier right after the network-fetching component and before filters.

Accordingly, **do not naively combine `withCaching()` and `withHealthChecks()` in the same custom example** assuming lifetimes and health status interact as desired. When a system genuinely needs both, understand the framework version, delegate ordering, and emission behavior of each supplier, and verify with tests.

Even when health checks report healthy, an instance can crash right after selection. The HTTP client still needs timeouts, connection error handling, and bounded retries.

## 10. Stale Instances, Cache Misses, and Real-World Failure Scenarios

Consider three instances: `catalog-a`, `catalog-b`, `catalog-c`:

| Point in Time | Actual Discovery | Caller's Cache | Risk |
|---|---|---|---|
| T0 | [A, B] | [A, B] | Normal operation |
| T1: B stops | [A] | [A, B] | May pick B and fail to connect |
| T2: C registers | [A, C] | [A, B] | No traffic routed to C yet |
| T3: cache refreshes | [A, C] | [A, C] | B removed, C eligible for selection |

This table assumes the cache has not expired between T1 and T2. In practice, discovery may also return stale data or filters may exclude additional instances.

Common incidents:

1. **Cache holds a dead instance**: requests hit connection refused, timeouts, or TLS errors; lowering TTL narrows the stale window but cannot completely eliminate race conditions.
2. **Cache lacks a new instance**: startup, rollout, or scale-out is not utilized by LoadBalancer right away; load may stay concentrated on old instances.
3. **Empty list on cache miss**: if discovery currently has no candidates, LoadBalancer cannot pick an instance; distinguish this from HTTP 503s returned by servers.
4. **Cache placed after a per-request filter**: cached list may be invalid for the next request; place request-specific filters after the baseline cache layer.
5. **TTL too long during continuous autoscaling**: lists and metadata lag behind new topology, increasing errors or skewing distribution.
6. **TTL too short**: registry faces higher load, and the first request after each expiration absorbs the cost of fetching a fresh list.

Do not use caching as a substitute for service discovery, health checks, circuit breakers, or routing policies. Caching optimizes **reading the instance list**.

## 11. Caffeine Does Not Cache HTTP Responses from RestClient, WebClient, or OpenFeign

A common misconception is that adding Caffeine to LoadBalancer makes responses from `GET /api/items/42` return directly from memory. That is not how Spring Cloud LoadBalancer's instance cache works.

~~~mermaid
sequenceDiagram
    participant Caller as order-service
    participant LC as Instance cache
    participant LB as LoadBalancer
    participant Catalog as catalog-service

    Caller->>LC: Fetch list for catalog-service
    LC-->>Caller: [A, B] (cache hit)
    Caller->>LB: Select instance
    LB-->>Caller: A
    Caller->>Catalog: GET /api/items/42
    Catalog-->>Caller: HTTP 200, JSON
    Note over Caller,Catalog: Response is not stored by instance cache
~~~

Example with RestClient:

~~~java
// Built from @LoadBalanced RestClient.Builder
ItemDto item = restClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);
~~~

Even when the instance list comes from cache, the HTTP client still sends the request to the selected instance. With WebClient, the request executes through the reactive pipeline; with OpenFeign, the request goes through the declarative interface; both likewise benefit only from lower instance-list lookup cost.

If an application wants to cache DTOs or HTTP responses, that is a separate business/API cache design requiring distinct keys, TTLs, invalidation, authorization, and data consistency rules.

## 12. Observing and Verifying Cache Configuration

When evaluating whether caching helps or causes stale data, measure:

| Metric or Signal | Question |
|---|---|
| Cache hit/miss per service ID | How often must we go back to the list source? |
| Discovery read count | Does caching reduce load on discovery? |
| Instance list fetch duration | Do cache misses raise selection latency? |
| Cache entry count and age | How old is the cached data? |
| Instance count before/after filters | Is the cache holding the right baseline list? |
| Connection error rate per instance | Are dead instances still getting picked? |
| Rollout/scale-out detection lag | How long before new instances take traffic? |
| Failed instance selection count | Is the cache holding or receiving empty lists? |
| Retries and timeouts | Are stale instances inflating attempt counts? |

Do not assume Spring Cloud emits every metric above under the same name out of the box; extra instrumentation or logging may be needed. When logging, avoid printing bodies, cookies, tokens, and sensitive data. Never put request IDs into metric labels because cardinality will explode.

### Meaningful Test Scenarios

1. **No Caffeine on classpath**: caching still works under supported configuration using the default implementation.
2. **Caffeine on classpath**: verify the Caffeine backend is selected and `spec` settings take effect.
3. **TTL expiration**: after the discovery source changes, the next access receives the updated list per configured behavior.
4. **Spec overrides general TTL**: if `expireAfterWrite` in `spec` differs from `cache.ttl`, verify the spec value actually governs expiry.
5. **LoadBalancer cache disabled**: verify `DiscoveryClient` is invoked under the new behavior; if discovery caches internally, recognize that cache layer still exists.
6. **Instance removed while cache is still valid**: ensure timeouts/retries do not stretch past business deadlines.
7. **Instance added during scale-out**: measure how long until the new instance starts receiving requests.
8. **Per-request zone/hint filter**: ensure the shared cache does not contain results filtered for a prior request.
9. **Discovery temporarily has no instances**: application reports an instance-selection failure clearly, distinct from an HTTP 503 returned by a server.
10. **Multiple caller replicas**: remember each process's cache has its own independent lifecycle and freshness.

Avoid testing merely by repeatedly calling a single unchanged instance: modify the upstream list, trigger cache misses, and compare before/after across timestamps. Refresh behavior also depends on underlying discovery caching, so verify the list emitted by the final supplier directly.

## 13. Choosing Between Caffeine, Default Cache, or Disabling Cache

| Context | Option to Consider | Verification Criterion |
|---|---|---|
| LoadBalancer needs caching, app lacks Caffeine | Use `DefaultLoadBalancerCache` | TTL, latency, and discovery query counts meet requirements |
| Caffeine present and explicit eviction control desired | Use Caffeine-backed cache | Spec is applied; size/TTL are appropriate |
| Discovery already has effective caching such as Eureka | Consider disabling LoadBalancer cache | Reduces double caching without overloading registry |
| Many requests filter by hint/version | Cache baseline list, filter after cache | Never reuse a list filtered for the wrong request |
| Instances change frequently | Evaluate shorter TTL or refresh mechanism | Rollouts/scale-out appear fast enough |
| Dedicated health check in use | Avoid arbitrarily stacking caching and health suppliers | Update flow and recovery behavior are correct |
| Errors mainly due to slow dependencies | Measure saturation, connection pool, timeouts | Instance list caching will not hide root cause |

Before changing configuration, verify the **running Spring Cloud Commons version, runtime classpath, `ServiceInstanceListSupplier` chain, internal `DiscoveryClient` caching behavior, and error observability**. Changing TTL may have no effect if the root cause of stale data sits in the discovery layer.

## 14. References and Key Principles to Remember

Default values, backend selection, and supplier ordering in this lesson match the official documentation:

- [Spring Cloud Commons – Spring Cloud LoadBalancer, Caching section](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)

**Cache selection principles:** Caffeine is used when the dependency is present and LoadBalancer caching is appropriately configured; without Caffeine, Spring Cloud still provides `DefaultLoadBalancerCache`. General configuration uses `ttl` and `capacity`, while `caffeine.spec` overrides the corresponding general settings. Place caching immediately after the instance-fetching source, avoid caching request-filtered results, and evaluate double caching at the discovery layer. Caching makes instance selection faster with fewer lookups, while timeouts, retries, health checks, and stale-instance observability still determine stability when RestClient, WebClient, or OpenFeign call services via Spring Cloud LoadBalancer.
