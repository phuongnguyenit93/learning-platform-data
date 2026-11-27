# Global Cache Configuration and Verifying Cache Effectiveness

In microservice systems, Spring Cloud LoadBalancer needs the list of **ServiceInstance** entries serving a service ID before picking an instance to send a request to. If every request had to re-query DiscoveryClient or the service registry, the system could incur unnecessary discovery lookups. **CachingServiceInstanceListSupplier** solves this by temporarily retaining the instance list, allowing multiple target selections to share a single snapshot over a configured duration.

This lesson focuses on two tasks: **configuring caching globally** and **proving the cache is actually active**. These two tasks must be verified separately: having cache properties in application.yml does not guarantee the supplier is using the cache; conversely, HTTP requests being distributed across different instances does not prove discovery was re-queried.

In Spring Cloud LoadBalancer, caching applies to the **service instance list**. It is not an HTTP response cache, does not store GET/POST payloads, does not store access tokens, and does not guarantee a cached instance is still healthy at the moment a request is sent.

## 1. Where Does Caching Sit in the LoadBalancer Flow?

A typical call from Order Service to Inventory Service:

~~~mermaid
flowchart TD
    A["RestClient / WebClient / OpenFeign"] --> B["LoadBalancer receives service ID"]
    B --> C["CachingServiceInstanceListSupplier"]
    C --> D{"Cache for service ID"}
    D -->|HIT| E["Return cached list"]
    D -->|MISS / expired| F["DiscoveryClient or ReactiveDiscoveryClient"]
    F --> G["ServiceInstance list"]
    G --> H["Store list in cache"]
    H --> I["Candidate list"]
    E --> I
    I --> J["Zone, hint, weighted, and other filters"]
    J --> K["RoundRobin / Random picks instance"]
    K --> L["Rewrite URI host/port"]
    L --> M["Send HTTP request to instance"]
~~~

The data path has two branches:

1. **Cache hit**: an entry for the service ID already exists and has not expired; the supplier returns the list from the cache.
2. **Cache miss**: no matching entry exists or the entry has expired; the supplier calls its delegate to fetch instances, then writes the result into the cache.

Suppose the service ID is **inventory-service** and the registry returns:

~~~text
inventory-service:
  inventory-a -> 10.20.0.11:8080
  inventory-b -> 10.20.0.12:8080
  inventory-c -> 10.20.0.13:8080
~~~

The first time LoadBalancer needs the list, the cache misses and reads the registry. Subsequent selections can reuse **[a, b, c]**. Round Robin can still pick a, b, c in turn from that same snapshot.

**Distinction:** seeing three HTTP requests go to three different instances while DiscoveryClient was called only once is normal caching behavior. Caching reduces list lookups; **it does not pin LoadBalancer to a single instance**.

## 2. Key Components to Know

| Component | Responsibility | Relation to Caching |
| --- | --- | --- |
| DiscoveryClient / ReactiveDiscoveryClient | Reads instance lists from the discovery source | Data source on a cache miss |
| DiscoveryClientServiceInstanceListSupplier | Adapts discovery results into a Flux of lists | Immediate delegate inside the cache |
| CachingServiceInstanceListSupplier | Looks up, stores, and replays instance lists | Decorator implementing caching in the supplier chain |
| LoadBalancerCacheManager | Manages caches for LoadBalancer | Abstracts cache implementation selection |
| DefaultLoadBalancerCache | Default cache bundled with the LoadBalancer starter | Used when no compatible Caffeine library is present |
| Caffeine-based cache | Cache backed by Caffeine | Selected when the Caffeine dependency is present |
| RoundRobinLoadBalancer / RandomLoadBalancer | Picks one instance from the received list | Does not decide cache hits or misses itself |
| RestClient, WebClient, OpenFeign | Sends HTTP requests to the chosen target | All can benefit from supplier caching |

**ServiceInstanceListSupplier** does not emit individual instances as separate Flux items; its primary API is:

~~~java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

Each Flux element is **a List of ServiceInstance**. CachingServiceInstanceListSupplier caches a list snapshot keyed by service ID, not the outcome of individual Round Robin selections.

### 2.1. Which Layer Should Hold the Cache?

Recommended pipeline:

~~~text
Discovery  ->  Caching  ->  ZonePreference  ->  HintBased  ->  LoadBalancer
                ^
                Caches raw source list, unfiltered by request
~~~

If a service has 3 instances, the same raw list can serve requests carrying different hints or tenants. Each request still needs filtering **after the cache** according to its own policy.

Spring Cloud recommends placing CachingServiceInstanceListSupplier **immediately after the supplier that fetches instances over the network**, before request-dependent filtering suppliers. Putting the cache outside a request-dependent filter can lose the request context or reuse a filtered list inappropriately.

## 3. Global Cache Configuration in application.yml

Commonly used properties live under the **spring.cloud.loadbalancer.cache** prefix:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

These are the **defaults published in the Spring Cloud Commons 5.0.4 documentation**. You can spell them out explicitly as above for clarity, or only declare the properties you want to override.

| Property | Documented Default | Meaning |
| --- | --- | --- |
| spring.cloud.loadbalancer.cache.enabled | true | Enables/disables Spring Cloud LoadBalancer caching globally |
| spring.cloud.loadbalancer.cache.ttl | 35s | Expiration duration after an entry is written |
| spring.cloud.loadbalancer.cache.capacity | 256 | **Initial capacity** of the cache, not a hard cap on entry count |
| spring.cloud.loadbalancer.cache.caffeine.spec | Empty | Uses a custom CaffeineSpec, overriding corresponding general cache settings |

Example shortening TTL for faster instance updates in dynamic environments:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 15s
        capacity: 128
~~~

**TTL is measured from when an entry is written**, not from the last read. A cache hit does not reset the timer back to 15 seconds. Depending on the implementation, expired entries are evicted on the next appropriate access or cache maintenance pass; do not assume a synchronous timer calls the registry at exact 15-second ticks.

### 3.1. What Does Global Configuration Affect?

The **cache.enabled** property belongs to Spring Cloud LoadBalancer's **global** configuration group. Practical interpretation:

- **enabled=true** permits using the cache mechanism and cache manager under auto-configuration conditions.
- **enabled=false** disables LoadBalancer caching globally; do not try to carve out a per-client cached branch while the global flag is off.
- With **enabled=true**, you can **disable caching for a specific service ID** using a custom supplier chain that *omits* CachingServiceInstanceListSupplier.
- With **enabled=true**, a custom supplier built without caching **does not automatically get wrapped in a cache just because this property is set**.

Per current Spring Cloud documentation, default discovery auto-configuration builds the supplier following this pattern:

~~~java
// Illustrates the default chain; does not require declaring a bean manually.
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .build(context);
~~~

The blocking discovery branch uses **withBlockingDiscoveryClient()** instead of **withDiscoveryClient()**. If you replace the supplier with a custom configuration, verify whether that chain still calls **withCaching()**.

## 4. How Do the Default Cache and Caffeine Differ?

Spring Cloud LoadBalancer supports two cache options based on the classpath:

| Criterion | Default Cache | Caffeine Cache |
| --- | --- | --- |
| Condition | No Caffeine on classpath | `com.github.ben-manes.caffeine:caffeine` dependency present |
| Usage | Bundled with LoadBalancer starter | Add Caffeine dependency; Spring Cloud selects the corresponding implementation |
| TTL | Via loadbalancer.cache.ttl | Via general ttl or CaffeineSpec |
| Initial capacity | Via loadbalancer.cache.capacity | Via general capacity or CaffeineSpec |
| Advanced policies | Basic capabilities | Supports maximumSize, expireAfterWrite, eviction, and Caffeine-specific options |
| Verification | Count delegate calls, inspect cache instance | Count delegate calls, use cache stats if enabled and properly instrumented |

To use Caffeine, add the dependency to the application classpath:

~~~groovy
// build.gradle: dependency declaration example, not a command to run.
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("com.github.ben-manes.caffeine:caffeine")
}
~~~

A compatible Spring Boot/Spring Cloud BOM manages the dependency version. Avoid manually picking a Caffeine version incompatible with your project.

### 4.1. Configuring CaffeineSpec

When using Caffeine and wanting explicit rules:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        caffeine:
          spec: initialCapacity=64,maximumSize=512,expireAfterWrite=20s
~~~

Where:

- **initialCapacity=64:** initial cache allocation capacity.
- **maximumSize=512:** approximate cap on entries Caffeine retains under its eviction policy.
- **expireAfterWrite=20s:** expiration duration after entry write.

**Important warning:** when **spring.cloud.loadbalancer.cache.caffeine.spec** is configured, Spring Cloud warns that the spec **overrides** other general LoadBalancer cache settings, including **ttl** and **capacity**. Do not set ttl=15s expecting it to apply when the spec defines expireAfterWrite=20s.

A conflicting configuration to avoid:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 15s
        capacity: 128
        caffeine:
          spec: maximumSize=512,expireAfterWrite=20s
~~~

Here, **20s** from the spec is the effective expiration rule, not **15s** from the general property. Pick **one single configuration method** for TTL/capacity to avoid confusion.

### 4.2. Capacity Is Not maximumSize

A common misreading is assuming **capacity=256** means the cache holds at most 256 service IDs. Per documentation, this is the **initial capacity**; to bound entry count in Caffeine, use **maximumSize** in CaffeineSpec.

Memory cost of instance lists also depends on the **number of service IDs**, **instance count per service**, and per-instance metadata. When an application calls many services, evaluate entry lifetime, eviction, and runtime observability.

## 5. What Does CachingServiceInstanceListSupplier Actually Cache?

In the current implementation, **CachingServiceInstanceListSupplier** uses a cache named:

~~~java
CachingServiceInstanceListSupplier.SERVICE_INSTANCE_CACHE_NAME
~~~

The default cache name derives from the class name and takes the form:

~~~text
CachingServiceInstanceListSupplierCache
~~~

The cache is looked up using the **service ID** provided by the delegate supplier:

~~~java
String cacheKey = delegate.getServiceId();
~~~

On a cache miss, the supplier calls its delegate to get a list snapshot. On a cache hit, it replays the stored list. Therefore:

- The cache key is **not the full URL** of a request.
- The cache key is **not each individual instanceId**.
- The cache key is **not a URI with query strings**.
- The cache does not directly hold Inventory Service's response body.
- The cache does not distinguish tenant/header/hint at the request level.

This is why the cache must sit **before** per-request filters: the same service ID can be invoked by many distinct requests that must not share one request's filtering decision.

### 5.1. Per-Caller-Process Caching

Spring Cloud LoadBalancer's cache lives in the caller application's memory, not in a store shared across JVMs/pods by default:

~~~text
order-service pod A -> A's own cache -> Inventory Service
order-service pod B -> B's own cache -> Inventory Service
order-service pod C -> C's own cache -> Inventory Service
~~~

When pod A just refreshed its list from the registry, pod B may still hold an old snapshot until its own TTL expires. Two pods can select different instances even while calling the same service ID. Never treat logs from pod A as proof that caches across the entire fleet have refreshed.

### 5.2. Empty Lists and Repeated Lookups

One implementation detail in **CachingServiceInstanceListSupplier** is that during cache lookup, if the entry is missing or the retrieved list is **empty**, the code treats it as a **cache miss**. Consequently, when discovery returns **[]** for a service ID that has no instances yet, subsequent calls may keep querying the delegate instead of being served by a negative cache hit.

Testing implications:

- Do not use an unregistered service ID and expect discovery counts to drop to one.
- Use a service with **at least one ServiceInstance** to demonstrate normal cache hits.
- Distinguish empty lists from registry errors: caching does not replace error handling when no instances exist.

This empty-list behavior reflects the referenced implementation; re-verify it when upgrading Spring Cloud versions.

## 6. TTL, Cache Hits, Misses, and Stale Data

Suppose TTL is **15s**. At t=0, the registry has [A, B]. At t=5, B deregisters and the registry updates to [A].

| Time | Registry State | Possible Cache Return | Meaning |
| --- | --- | --- | --- |
| t=0 | [A, B] | [A, B] after miss and write | Entry created |
| t=3 | [A, B] | [A, B] | Valid hit |
| t=5 | [A] | [A, B] | B still remains in cache |
| t=10 | [A] | [A, B] | Valid hit while TTL not expired |
| t=16 | [A] | [A] after miss/refetch call | Old entry has expired |

This is an **illustrative scenario**: exact timing and outcomes depend on the cache backend, registry, when accesses happen, and any active instance filters. There is no guarantee that the cache queries the registry **at the exact moment** TTL expires if no request arrives.

### 6.1. What Do Short TTLs and Long TTLs Trade Off?

| TTL | Advantage | Risk |
| --- | --- | --- |
| Short, e.g., 5s | Observes instance changes faster | Increases discovery calls / cache misses |
| Medium, e.g., 20–35s | Cuts most repeated queries with moderate change lag | Still leaves a stale data window |
| Long, e.g., 120s | Fewer discovery calls | Deleted or relocated instances can linger in cache |

There is no universally optimal TTL for every system. Consider autoscaling speed, deregistration time, heartbeat intervals, fault tolerance, number of service IDs, and client SLOs.

**TTL does not equal system-wide data freshness.** If DiscoveryClient (such as Eureka) caches on its own and syncs periodically, the LoadBalancer cache can read **an already stale snapshot** from discovery. Total update lag therefore spans multiple layers and cannot be inferred from a single TTL property.

## 7. Avoiding Two-Layer Caching with Discovery Providers

Some providers already ship their own local cache/registry:

~~~text
Client request
     |
LoadBalancer cache (TTL 35s)
     |
EurekaDiscoveryClient local cache / refresh
     |
Eureka Registry
~~~

Two layers can lower load yet create confusion right when an instance starts or stops. Spring Cloud warns: if the DiscoveryClient implementation **already caches the instance list**, such as EurekaDiscoveryClient, consider **disabling the LoadBalancer cache** to avoid double caching.

Global disable configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Disabling this cache **does not mean** stripping Eureka's internal cache or forcing a network query per request. DiscoveryClient can still return data from its own cache. Thus, a test that only counts HTTP requests to the registry can be misleading.

### 7.1. When Should You Enable It?

Consider enabling LoadBalancer caching when:

- DiscoveryClient queries an expensive source on every list lookup.
- The replica list changes infrequently or can tolerate update lag within the TTL.
- The system sees far more requests than the number of times the registry genuinely needs to be read.
- You want to offload the discovery provider while keeping suitable health/timeout strategies.

Consider disabling it or lowering TTL when:

- The provider already has strong caching and periodic refresh.
- Pods/instances churn rapidly and the system needs new replicas visible almost immediately.
- Stale-instance errors trigger unwanted timeouts or retries.
- A HealthCheck chain already retains/replays results on its own and is designed to replace standard caching.

**The final decision must be measured**, not based solely on the default property being true.

## 8. Building the Supplier Chain Correctly with Caching

Spring Cloud supplies defaults in many standard setups. When customizing, you can define a dedicated supplier for a service ID.

### 8.1. With Synchronous DiscoveryClient

~~~java
class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Actual transformation order:

~~~text
DiscoveryClient -> Caching -> ZonePreference -> LoadBalancer
~~~

### 8.2. With ReactiveDiscoveryClient

~~~java
class InventoryReactiveLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

**withDiscoveryClient()** in the builder above corresponds to the reactive source. **withBlockingDiscoveryClient()** corresponds to the blocking source. Pick based on your provider implementation and Spring Cloud stack.

### 8.3. Applying Specifically to inventory-service

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
class OrderApplication {
}
~~~

`InventoryLoadBalancerConfiguration` in the example intentionally omits **@Configuration** so component scanning does not turn it into a global configuration. Per Spring Cloud guidance, a `@LoadBalancerClient` configuration class should stay outside component scanning or not be scanned into the main ApplicationContext.

If you only want global cache configuration without customizing zone/health/hint, **you do not need to create this supplier** when auto-configuration already provides a cached chain.

### 8.4. Do Not Place Cache Outside Request Filters

**Correct:**

~~~text
Discovery -> Caching -> ZonePreference -> HintBased -> LoadBalancer
~~~

**Avoid:**

~~~text
Discovery -> HintBased -> Caching -> LoadBalancer
~~~

HintBased may require a Request containing hint headers, whereas caching keyed by service ID does not split entries by header. If caching wraps HintBased, the request context may fail to reach the inner filter or results will no longer reflect individual requests.

Note that **call-get-with-request-on-delegates** added in recent releases lets many decorators forward Request; CachingServiceInstanceListSupplier and HealthCheckServiceInstanceListSupplier are explicit exceptions noted in the documentation. Placing them close to the discovery source remains the safe design.

### 8.5. Do Not Arbitrarily Stack Cache and HealthCheck

**HealthCheckServiceInstanceListSupplier** has its own publisher/scheduler and healthy-list replay mechanism. If both standard caching and HealthCheck retain results, update timing becomes hard to observe or overly stale.

When health checks are needed because the source does not reflect health, typically consider:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHealthChecks()
        .withZonePreference()
        .build(context);
~~~

This is an **alternative** to the standard caching example, not a requirement to add health checks to every registry.

## 9. How Do You Know Caching Is Actually Working?

**Do not use Round Robin distribution to infer cache hits.** To prove the cache is serving instance lists, measure right at the boundary between **CachingServiceInstanceListSupplier** and the **delegate discovery supplier**.

A reliable verification strategy:

1. Pick a service ID with at least one instance, e.g., inventory-service.
2. Ensure cache.enabled=true and the supplier includes CachingServiceInstanceListSupplier.
3. Configure a TTL long enough for the experiment, e.g., 20s.
4. Count how many times the source supplier must fetch the list, not just HTTP calls to backends.
5. Perform two list fetches **sequentially**, completing the first subscription before invoking the second.
6. Compare source read counts after the first and second fetches.
7. Wait for the entry to expire and retry; the source read count should increase.
8. Repeat the same test with caching disabled or a supplier without withCaching() as a **control**.

### 9.1. Expected Results Table

Assuming a single sequential consumer, a non-empty list, and no health/refetch filters:

| Action | Caching enabled and in supplier | Uncached supplier |
| --- | --- | --- |
| First read with no entry | Reads source, writes cache | Reads source |
| Second read immediately after | Reads cache, skips source | Reads source |
| Third read within TTL | Reuses entry | Reads source |
| Read after TTL | Needs to fetch fresh list from source | Reads source as usual |
| Multiple HTTP requests | Can still Round Robin continuously | Can still Round Robin continuously |

Because caches are often initialized **lazily** per service ID, the first load-balanced call to a service includes context creation, bean instantiation, and the initial discovery read. Do not compare the first request's latency to the second and attribute the entire difference to caching.

## 10. Unit Test: Counting Delegate Invocations

This example uses the real **CachingServiceInstanceListSupplier**, a counting source delegate, and Spring's **ConcurrentMapCacheManager** as the test cache. It isolates cache behavior from registries, HTTP clients, DNS, and network timing.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.CachingServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Flux;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LoadBalancerCacheTest {

    static final class CountingSupplier
            implements ServiceInstanceListSupplier {

        private final AtomicInteger calls = new AtomicInteger();

        private final List<ServiceInstance> snapshot = List.of(
                new DefaultServiceInstance(
                        "inventory-1",
                        "inventory-service",
                        "localhost",
                        8081,
                        false),
                new DefaultServiceInstance(
                        "inventory-2",
                        "inventory-service",
                        "localhost",
                        8082,
                        false));

        @Override
        public String getServiceId() {
            return "inventory-service";
        }

        @Override
        public Flux<List<ServiceInstance>> get() {
            return Flux.defer(() -> {
                calls.incrementAndGet();
                return Flux.just(snapshot);
            });
        }

        int calls() {
            return calls.get();
        }
    }

    @Test
    void repeatedReadsReuseCachedInstanceList() {
        CountingSupplier source = new CountingSupplier();
        CacheManager cacheManager = new ConcurrentMapCacheManager(
                CachingServiceInstanceListSupplier.SERVICE_INSTANCE_CACHE_NAME);

        ServiceInstanceListSupplier cached =
                new CachingServiceInstanceListSupplier(source, cacheManager);

        List<ServiceInstance> first =
                cached.get().blockLast(Duration.ofSeconds(2));
        List<ServiceInstance> second =
                cached.get().blockLast(Duration.ofSeconds(2));

        assertEquals(2, first.size());
        assertEquals(first, second);
        assertEquals(1, source.calls());
    }
}
~~~

What the result proves:

- Both **cached.get()** calls are subscribed **sequentially**.
- The first call misses the cache and invokes CountingSupplier.get() once.
- The second call reads the cached list without calling the source a second time.
- Verifies **supplier list reuse** independent of Round Robin or networking.

**Explicit limitation:** ConcurrentMapCacheManager in this example is a test cache that **does not automatically expire on Spring Cloud's 35s TTL**. This unit test **only verifies cache hits**; it does not verify property binding, LoadBalancerCacheManager auto-configuration, or production implementation TTLs. To test end-to-end, an integration test like the next section is needed.

### 10.1. Negative Control Check

Try calling source.get() directly twice with the same snapshot:

~~~java
CountingSupplier source = new CountingSupplier();

source.get().blockLast(Duration.ofSeconds(2));
source.get().blockLast(Duration.ofSeconds(2));

assertEquals(2, source.calls());
~~~

The contrast between **1 source call through Caching** and **2 calls without Caching** is stronger proof than two backends returning identical payloads.

### 10.2. Avoid Misinterpretation Under Concurrent Testing

If 20 requests arrive simultaneously while the cache is empty, multiple concurrent cache misses can occur before one request writes the entry. Do not conclude the cache is broken simply because the source was called more than once during a concurrent cold start. Start with a **sequential test** to verify basic semantics before adding load tests for real-world throughput.

## 11. Integration Test: Verifying Global Configuration Applies

The unit test above proves the decorator works, not that the real application has **loadbalancer.cache.enabled=true**, the right cache manager, or the right TTL. Integration tests must exercise the Spring ApplicationContext and the live call path.

### 11.1. Preparing Two Local Backends

Start two Inventory Service instances with endpoints:

~~~text
http://localhost:8081/whoami -> {"instanceId":"inventory-1"}
http://localhost:8082/whoami -> {"instanceId":"inventory-2"}
~~~

In Order Service, use SimpleDiscoveryClient to avoid needing Eureka:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 128
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

SimpleDiscoveryClient reads a **static** list from configuration; it works well to demonstrate caching and can be measured via a spy/wrapper in tests. Because the list does not auto-update when a backend stops, **do not rely solely on stopping 8081 to prove TTL**.

### 11.2. Integrating a LoadBalanced RestClient

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Call by service ID:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        restClient = builder.build();
    }

    String whoAmI() {
        return restClient.get()
                .uri("http://inventory-service/whoami")
                .retrieve()
                .body(String.class);
    }
}
~~~

If the application uses the default supplier and caching is active, repeated **whoAmI()** calls can still return **inventory-1** and **inventory-2** in Round Robin fashion even though the discovery supplier is read only once within the TTL.

### 11.3. Cache Evidence Inside the Spring Context

Two **independent facts** need verification:

**A. Does the bean/supplier have caching?** For a service ID like inventory-service, Spring Cloud creates a child context via LoadBalancerClientFactory. Inspect the actual ServiceInstanceListSupplier bean inside the child context or enable auto-configuration debug logging to confirm the **Discovery → Caching** chain was constructed.

**B. Is the cache actually being used?** In tests, wrap DiscoveryClient.getInstances("inventory-service") or the discovery supplier right underneath the cache with a spy or counter. Invoke the load-balanced HTTP client sequentially several times, then verify the counter does not increment on every request while the entry remains valid.

Example expectation without extra health/retry/refetch behavior:

~~~text
T=0s:  GET /whoami  -> inventory-1, discovery reads=1
T=1s:  GET /whoami  -> inventory-2, discovery reads=1
T=2s:  GET /whoami  -> inventory-1, discovery reads=1
T=21s: GET /whoami  -> inventory-2, discovery reads=2
~~~

These figures are **expectations for a controlled sequential test environment only**, not guaranteed call counts in production. Requests from adapters using a different supplier, retries, or multiple caller pods will alter the counts.

### 11.4. A/B Comparison with Caching Disabled

Repeat the test in another application launch:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

If the application uses a countable discovery source:

| Criterion | Cache Enabled | Cache Disabled |
| --- | --- | --- |
| Requests reaching backends | Equivalent | Equivalent |
| List fetches from source supplier | Usually substantially lower | Can approach instance selection count |
| Immediate visibility of list changes | Depends on TTL | Depends on discovery provider cache/refresh |
| Round Robin distribution | Still operates | Still operates |

For a fair comparison, keep service ID, instance count, request rate, caller pod count, retries, and discovery provider identical. Change only the **cache mechanism** between runs.

## 12. Verifying Actual TTL Expiration

To test the production implementation's TTL, control when the entry is written rather than only checking whether the instance list changed.

A procedure:

1. Build a test app with **cache.enabled=true**, **ttl=3s**, and a counted discovery source.
2. Initialize the LoadBalancer child context and perform one instance selection to populate the entry.
3. Call again **within 3 seconds**, verifying the source counter does not increment.
4. Wait **more than 3 seconds from when the entry was written**, then perform a new selection.
5. Verify the source read counter increments again if the cache expired as expected.
6. Repeat with CaffeineSpec **expireAfterWrite=3s** and verify the value comes from the spec, not general ttl.

Do not use "how many responses came from instance B" as the primary check. The registry can keep the exact same list before and after expiry, leaving responses unchanged even though the cache just refetched successfully.

### 12.1. Verifying Stale Data After Instance Changes

With a discovery source that can **change its returned list** during the test:

~~~text
T0: source returns [A, B] -> cache miss -> [A, B]
T1: source changes to [A]
T2: read within TTL -> cache hit -> still [A, B]
T3: read after TTL -> cache miss -> [A]
~~~

This verifies both **cache reuse** and **expiry/update**. When using a real registry, remember the registry/discovery provider may also cache. Confirm the source already returns [A] before blaming LoadBalancer's cache.

### 12.2. When Can a TTL Experiment Mislead You?

- The source returns an empty list, triggering special miss handling.
- Concurrent requests overlap cache misses.
- Multiple **caller** instances exist, each with its own cache.
- The test mistakenly reads the ServiceInstanceListSupplier bean from the parent context instead of the service-ID child context.
- Eureka or another provider already caches, so network request counts do not reflect getInstances() calls.
- HealthCheck supplier emits snapshots on a scheduler rather than per request.
- CaffeineSpec is overriding ttl in YAML.
- The test did not wait until the entry was actually written before starting the clock.

That is why combining **supplier unit tests**, **configuration integration tests**, and **production observability** is better than relying on a single form of evidence.

## 13. Observing the Cache in Operations

Signals worth tracking:

| Signal | Question Answered |
| --- | --- |
| DiscoveryClient.getInstances(serviceId) count | Is discovery list-fetching actually decreasing? |
| Cache hits/misses if cache manager is instrumented | Are entries being reused? |
| Service ID count in cache, list sizes | Is cache memory footprint reasonable? |
| Detection delay for new/stopped instances | How much update lag is TTL adding? |
| Failed requests to deregistered instances | How does stale data impact users? |
| Instance selection time and total HTTP latency | Is caching lowering overhead or hiding a bottleneck? |
| Retry, timeout, and 5xx rates | Do errors spike while old instances linger in cache? |

**Do not assume every cache metric is emitted by Spring Cloud out of the box.** With Caffeine, hit/miss statistics typically require enabling stats and wiring Micrometer/Actuator per application configuration. LoadBalancer's instance/request selection metrics are not automatically cache hit/miss metrics.

An easy verification trick in tests is wrapping DiscoveryClient or the source supplier with a counter and emitting call counts via custom logs/metrics. In production, avoid permanently logging full hostnames, metadata, or sensitive instance details at DEBUG level.

### 13.1. Logging at Supplier Boundaries

Illustrative logs:

~~~text
serviceId=inventory-service stage=discovery sourceReads=1
serviceId=inventory-service stage=cache outputSize=3
serviceId=inventory-service stage=zone outputSize=2
serviceId=inventory-service stage=selection chosen=inventory-a
~~~

If 100 requests generate many selection logs but very few discovery source logs, caching is taking effect. However, only rely on log counts if you are sure **every source read is instrumented** and none are dropped by log sampling.

### 13.2. Watch Out for Multi-Service-ID Caches

A caller may invoke inventory-service, pricing-service, and payment-service:

~~~text
inventory-service -> list [I1, I2]
pricing-service   -> list [P1, P2, P3]
payment-service   -> list [M1]
~~~

Lists are managed per service ID. Do not lump discovery counts from three services together to evaluate cache hits for one service. Metric dashboards should include **service ID** or appropriate service groupings, while avoiding excessive cardinality if service names are unbounded.

## 14. Common Troubleshooting Table

| Symptom | Likely Cause | How to Verify |
| --- | --- | --- |
| cache.enabled=true is set, yet source is read every time | Custom supplier lacks withCaching() or cache manager is unused | Inspect the actual supplier chain |
| Initially hits, then calls source again after a few seconds | TTL expired or entry was evicted | Check ttl / CaffeineSpec / maximumSize |
| Set ttl=15s, but actual behavior is near 20s | CaffeineSpec has expireAfterWrite=20s | Check CaffeineSpec first |
| Just-stopped instance is still picked | LoadBalancer cache or registry still holds stale snapshot | Compare cache snapshot and discovery source |
| Requests to Eureka server did not drop as expected | EurekaDiscoveryClient already maintains its own cache | Measure getInstances() and registry cache layer separately |
| Round Robin keeps switching instances with cache on | Normal behavior | Distinguish instance selection from list fetching |
| Test shows no cache hit when source returns [] | Empty lists are treated as misses in current implementation | Test with a non-empty snapshot |
| Many source reads still happen during bursts | Concurrent cache misses or startup warm-up | Test sequentially first, then inspect bursts |
| Hints or sticky sessions break | Cache placed outside Request-based filters | Check decorator order and get(Request) |
| Timeouts rise after increasing TTL | Lists stay stale longer; dead instances still picked | Monitor TTL, health, retries, and deregistration timing |
| Hit/miss metrics missing | Cache stats/Actuator instrumentation disabled or unsupported | Measure via source counter, verify cache manager |
| Only some caller pods see new instances | Each pod has its own cache/refresh cycle | Compare snapshots per pod and service ID |

When debugging, walk from **global config → supplier chain → cache manager → per-service-ID cache entry → discovery delegate → HTTP selection**. If an application runs an uncached supplier chain, tuning TTL does nothing; if the registry already returns stale data, shrinking LoadBalancer's TTL will not guarantee fresh results either.

## 15. Global Cache Rollout Checklist

- [ ] **spring-cloud-starter-loadbalancer** dependency and compatible discovery provider present.
- [ ] Verified **spring.cloud.loadbalancer.cache.enabled** is effective in the runtime environment.
- [ ] Verified the supplier for the service ID actually contains **CachingServiceInstanceListSupplier**.
- [ ] Cache placed **immediately after the discovery source**, before zone/hint/request-based filtering.
- [ ] Confirmed whether the cache uses the default implementation or Caffeine.
- [ ] If using CaffeineSpec, verified no expectation that general ttl/capacity properties still control the cache.
- [ ] Distinguished **capacity=initial capacity** from Caffeine's **maximumSize**.
- [ ] Checked whether DiscoveryClient caches on its own; avoided unintended double caching.
- [ ] Avoided using an empty list as the sole case to prove cache hits.
- [ ] Unit test counting delegate.get() across hits and misses.
- [ ] Integration test comparing cache on/off and verifying TTL.
- [ ] Tested instance stop, registry update, and cache expiration flow.
- [ ] Ensured timeouts/retries and health checks protect the stale-data window.
- [ ] Monitored errors to old instances, discovery read counts, and update lag.
- [ ] Avoided logging sensitive request or instance metadata.

## 16. Summary

Spring Cloud LoadBalancer caching enables **reusing ServiceInstance lists**, reducing discovery source calls when many requests target the same service ID. Global settings include **enabled**, **ttl**, and **capacity**; when Caffeine is present, **caffeine.spec** allows finer control over expiration and eviction.

To prove caching works, confirm **the CachingServiceInstanceListSupplier decorator is actually inside the supplier chain**, then count **how many times the discovery delegate is invoked** with and without caching and before/after TTL expiry. Watching Round Robin distribution or HTTP responses alone is insufficient to prove cache hits. Also account for stale-data lag, double caching with Eureka, placing the cache before request-dependent filters, and independent lifecycles across caller pods.

## 17. References

- [Spring Cloud Commons 5.0.4 – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): caching implementations, TTL, capacity, CaffeineSpec, builder, and supplier ordering.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): default values for spring.cloud.loadbalancer.cache properties.
- [CachingServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/CachingServiceInstanceListSupplier.java): service-ID keying, cache lookup, empty-list handling, and delegate get().
- [LoadBalancerClientConfiguration.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): default suppliers for blocking/reactive discovery.
- [ServiceInstanceListSupplierBuilder.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ServiceInstanceListSupplierBuilder.java): how decorator chains are constructed.
- [Spring Cloud Netflix Eureka – Reference](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): discovery/registry behavior of the Eureka provider.
