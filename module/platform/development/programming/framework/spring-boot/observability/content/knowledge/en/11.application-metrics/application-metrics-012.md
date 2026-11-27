# Cache Metrics in Spring Boot: Measuring Hits, Misses, Evictions, and Cache Effectiveness

A Spring Boot application can use a cache to reduce database queries or external service calls. However, simply adding `@Cacheable` is not enough to conclude the cache is effective: the cache hit ratio might be low, entries might be evicted too frequently, or stale data might cause users to see wrong results. **Cache metrics** reveal these phenomena with data instead of guesswork.

Within the **Application metrics** chapter of the **SPRING_BOOT_OBSERVABILITY** module, this lesson focuses on collecting and interpreting cache metrics in Spring Boot through Micrometer and Actuator, then correlating results with **Micrometer Observation, metrics, logs, and distributed tracing** to investigate errors, latency, and application behavior. Topics such as tags/cardinality, exporters, sampling, and propagation also directly affect how you validate findings in production.

## Learning objectives

After this lesson, you will be able to:

1. Explain cache hits, misses, puts, evictions, size, and the limits of interpreting each metric.
2. Enable cache metrics in Spring Boot with a concrete provider such as **Caffeine**.
3. Verify metrics via `/actuator/metrics` and `/actuator/prometheus`.
4. Write PromQL queries to calculate hit ratio, miss ratio, eviction rate, and monitor cache size.
5. Distinguish cache metrics from business processing time, HTTP errors, and tracing telemetry.
6. Control cache names, labels/cardinality, sensitive data, and cache consistency.
7. Design tests and an investigation workflow when cache metrics look abnormal or fail to export.

## 1. What problem does caching solve?

Suppose an endpoint `GET /products/{sku}` fetches product details. If every request queries the database or calls `catalog-service`, the system wastes time and resources even when many users request the same product.

A cache stores a result temporarily:

~~~mermaid
flowchart TD
    Request["GET /products/{sku}"] --> Lookup{"Valid entry in cache?"}
    Lookup -- "Hit" --> Cached["Return result from cache"]
    Lookup -- "Miss" --> Backend["Read DB / catalog-service"]
    Backend --> Store["Store in cache if policy allows"]
    Store --> Result["Return result"]
    Cached --> Result
    Lookup -. "Hit/miss metrics" .-> Meter["Micrometer cache.gets"]
    Backend -. "Observe dependency" .-> Observe["Observation / trace / logs"]
~~~

A **cache hit** is a lookup that finds a usable value in the cache. A **cache miss** is a lookup without usable cached data, forcing the system to fetch or compute from the source. Exact hit/miss definitions depend on the provider and lookup API: calling `put` directly does not necessarily count as a miss, and concurrent requests may behave differently when loading values.

Caching always involves trade-offs:

- **Performance:** saves origin read latency, at the cost of memory, lookup, and management overhead.
- **Data freshness:** caches can return stale data if TTL and invalidation are wrong.
- **Resources:** overly large caches increase heap/GC pressure or external cache service costs.
- **Reliability:** massive cache misses can overload the database or downstream services.

Therefore, use metrics to **measure both effectiveness and cost**, rather than watching a single hit percentage.

## 2. Core cache metrics

Micrometer standardizes several meter names for supported providers. Common names include `cache.gets`, `cache.puts`, `cache.evictions`, and `cache.size`. Which metrics are available depends on the cache library, statistics configuration, and integration version.

| Meter / concept | Data type | Question answered | Things to watch |
| --- | --- | --- | --- |
| `cache.gets` with `result=hit` | Counter / total hit lookups | How many reads did the cache serve? | Cumulative count, not current rate |
| `cache.gets` with `result=miss` | Counter / total miss lookups | How many reads fell back to the origin? | Does not equal exact DB query count across all providers |
| `cache.puts` | Counter if provider supports it | How many cache writes occurred? | Put semantics vary by provider |
| `cache.evictions` | Counter if provider supports it | How many entries were removed by eviction? | Does not automatically include all manual invalidations |
| `cache.size` | Gauge if provider supports it | Roughly how many entries exist right now? | May be an estimate/point-in-time snapshot, not total accesses |
| Hit ratio | Derived from hits and misses | Fraction of lookups served from cache? | Must use matching time window and scope |
| Miss ratio | Derived metric | Fraction of lookups missing the cache? | Must read alongside traffic, cache, and instance |

### 2.1. Hit ratio and miss ratio

In a measurement window, let hits be `H` and misses be `M`, with `H + M > 0`:

\[
\text{Hit ratio} = \frac{H}{H + M}
\qquad
\text{Miss ratio} = \frac{M}{H + M}
\]

Example over 5 minutes:

| Outcome | Count |
| --- | ---: |
| Hit | 900 |
| Miss | 100 |
| Total lookups | 1,000 |
| Hit ratio | 90% |
| Miss ratio | 10% |

In this example, **90% is the ratio of cache lookups that found data**, not the HTTP request success rate. One request may perform multiple cache lookups or none at all; a cache hit also does not guarantee a business-valid response.

### 2.2. Eviction vs. explicit invalidation

**Eviction** generally refers to entries removed due to capacity limits, expiration policies, or provider-specific management rules. **Invalidation** is removing/updating entries because the application knows data changed, such as `@CacheEvict` after updating a product.

Do not assume every `@CacheEvict` increments `cache.evictions`. Providers may distinguish capacity-based eviction from removals triggered by explicit delete APIs, replacements, or expiry. Verify your provider's exact semantics before writing eviction alerts.

### 2.3. Cache size is not memory bytes

`cache.size` is typically an **entry count**, not heap size in bytes. In Caffeine, size may be reported as an estimate. A cache with 10,000 tiny entries and one with 10,000 large object entries have vastly different memory footprints.

If concerned about heap and GC, pair cache size with `jvm.memory.used`, `jvm.gc.pause`, cache limits, and appropriate profiling data.

## 3. How does Spring Boot collect cache metrics?

Spring Boot Actuator integrates Micrometer and can automatically instrument eligible caches from `CacheManager` when the provider is supported. For a given cache, the flow generally includes:

1. The application initializes `CacheManager` and declared caches.
2. Spring Boot metrics auto-configuration detects supported caches.
3. An appropriate binder/provider registers cache meters into `MeterRegistry`.
4. The cache provider updates statistics as the application runs.
5. The registry exposes meters via Actuator endpoints or exports them to a metrics backend.

~~~mermaid
flowchart LR
    App["@Cacheable / CacheManager"] --> Provider["Caffeine, JCache, ..."]
    Provider --> Stats["Provider statistics"]
    Stats --> Binder["Cache meter binder"]
    Binder --> Registry["MeterRegistry"]
    Registry --> Actuator["/actuator/metrics"]
    Registry --> Prom["/actuator/prometheus"]
    Prom --> Backend["Prometheus / Grafana"]
    App --> Observation["Micrometer Observation"]
    Observation --> Trace["Tracing / logs correlation"]
~~~

**Provider-dependent:** not every `Cache` implementation provides identical hit/miss/eviction stats. Some require enabling statistics, some support only a subset of meters, and distributed caches can report local stats differently from cluster-wide stats. Do not just add Actuator and assume every figure exists.

### 3.1. Caches created after startup

Spring Boot normally auto-binds caches **already present at startup**. Caches created dynamically later (e.g., cache names generated at runtime) may **not receive metrics automatically**. To observe dynamic caches, check Spring Boot's `CacheMetricsRegistrar` or the provider's binder API for your exact project version.

Better yet, **declare a stable set of cache names up front** during domain design. Creating a separate cache per tenant, user, or request causes meter/label explosion and management headaches.

### 3.2. Associated labels

Cache metrics can carry labels like cache name and `CacheManager` name. Tags related to `cache`, `cacheManager`, and `result` (hit/miss) are common. These labels pinpoint which cache has an issue, though **exact tag names and backend transformations depend on version and registry**.

For example, if `catalogBySku` and `permissionsByRole` share one `CacheManager`, aggregating all hits/misses into a single combined ratio can hide an issue in one cache. Always filter by **cache and cache manager** first when investigating.

## 4. Spring Boot example with Caffeine

Caffeine is an in-process cache provider commonly paired with Spring's Cache abstraction. In this example, the application defines a cache named `catalogBySku` storing product data by SKU, with a 10-minute TTL and a 10,000-entry cap.

### 4.1. Dependencies

Gradle example with Spring Boot 3.x and compatible dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'com.github.ben-manes.caffeine:caffeine'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-cache` provides the cache abstraction and support for annotations like `@Cacheable`; Caffeine is the cache provider. Actuator with Micrometer collects metrics, and the Prometheus registry makes them scrapeable.

### 4.2. Declaring the cache with `recordStats()`

In `CacheConfiguration.java`:

~~~java
package com.example.catalog;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("catalogBySku");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(10))
                .recordStats());
        return manager;
    }
}
~~~

**The key detail is `recordStats()`.** With Caffeine, statistics recording must be enabled for hit/miss counters to be populated. Without `recordStats()`, the cache still works and returns entries, yet statistics will not update as expected.

`new CaffeineCacheManager("catalogBySku")` declares the cache name up front so it is initialized and eligible for Actuator binding at startup. `maximumSize` caps entry count; `expireAfterWrite` sets expiry from write time, which **does not automatically keep business data consistent** when origin data changes.

### 4.3. Using `@Cacheable` in a service

In `CatalogService.java`:

~~~java
package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CatalogBackend backend;

    public CatalogService(CatalogBackend backend) {
        this.backend = backend;
    }

    @Cacheable(cacheNames = "catalogBySku", key = "#p0")
    public ProductView findProduct(String sku) {
        return backend.fetch(sku);
    }
}

interface CatalogBackend {
    ProductView fetch(String sku);
}

record ProductView(String sku, String name) {}
~~~

`CatalogBackend` is an application adapter reading from a database or `catalog-service`; `ProductView` is an illustrative record. `#p0` references the first method parameter without depending on parameter name retention in bytecode.

The first call to `findProduct("SKU-1")` normally reads from the backend (**miss**) and populates the cache; subsequent calls with the same key while valid are served from the cache (**hit**).

**Proxy caveat:** Spring caching annotations typically run via AOP proxies. If a method inside the same object calls `this.findProduct(...)` directly, it can **bypass the proxy** and skip `@Cacheable`. That causes tests or metrics to miss expectations even with the annotation present.

### 4.4. Invalidation and stale data

When product info changes, explicit invalidation may be needed:

~~~java
import org.springframework.cache.annotation.CacheEvict;

@CacheEvict(cacheNames = "catalogBySku", key = "#p0")
public void invalidateProduct(String sku) {
    // When invoked through the Spring proxy, the cache entry for sku is removed.
}
~~~

This illustrates a method inside an appropriate Spring bean; do not copy this annotated snippet standalone outside a class. A real design must decide **when** invalidation occurs, especially when updating data inside transactions or across services. A high cache hit ratio serving stale data is a **correctness failure**, not a success.

## 5. Enabling and inspecting cache metrics in Actuator

In `application.yml`, configure endpoints for a test environment:

~~~yaml
spring:
  application:
    name: catalog-service

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
  metrics:
    tags:
      application: catalog-service
~~~

Start the application, trigger hit/miss lookups, and inspect:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/cache.gets
curl -s http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics/cache.gets` presents meter details in Actuator format, including meter name, measurements, and available tags. On `/actuator/prometheus`, metric names convert to snake_case and counters gain a `_total` suffix.

Example **hypothetical, simplified output** after traffic:

~~~text
cache_gets_total{application="catalog-service",cache="catalogBySku",result="hit"} 900
cache_gets_total{application="catalog-service",cache="catalogBySku",result="miss"} 100
cache_puts_total{application="catalog-service",cache="catalogBySku"} 100
cache_evictions_total{application="catalog-service",cache="catalogBySku"} 5
cache_size{application="catalog-service",cache="catalogBySku"} 95
~~~

**Do not treat these lines as mandatory names/labels across every version.** A registry may include `cacheManager`, transform names, or omit meters unsupported by the provider. Always inspect real output before writing queries and alerts.

### 5.1. Why might meters exist with value 0?

- The cache has received no lookups or hits/misses as counted by the provider.
- `recordStats()` was not enabled.
- `@Cacheable` calls suffered self-invocation, caching wasn't enabled, or the wrong bean was used.
- A different cache than the one you filtered on is being used.
- Entries were populated directly with `put` without any `get` calls yet.
- The runtime config or provider does not support that specific statistic.

A zero reading is a prompt to investigate, **not enough to conclude the cache does nothing** before verifying the execution path.

### 5.2. Securing endpoints

Metrics can expose cache names, service names, entry counts, environment tags, and application structure. In production, restrict Actuator endpoint access via management networks, authentication/authorization, or secure scraping setup. Never expose `/actuator/prometheus` publicly just for easy debugging.

## 6. Analyzing caches with PromQL

The examples below assume Prometheus receives **classic counter/gauge series** named `cache_gets_total`, `cache_evictions_total`, and `cache_size`, with labels `cache="catalogBySku"` and `application="catalog-service"`. Adjust queries to match your actual series.

**Important:** because `cache.gets` is a cumulative counter, use `rate(...[5m])` or `increase(...[5m])` to compute ratios over a window instead of dividing two cumulative values from process startup when checking recent effectiveness.

### 6.1. 5-minute hit ratio

~~~promql
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result="hit"
}[5m]))
/
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result=~"hit|miss"
}[5m]))
~~~

A result of `0.90` means roughly 90% of **observed cache lookups** during that window were hits. If total lookups are zero or near zero, division yields no value or lacks statistical significance. Dashboards should show **lookup rate** alongside hit ratio to prevent misinterpretation.

Never merge completely different caches and declare "the system has a 90% hit ratio." One cache with 10 million hits can hide a critical cache experiencing 100% misses.

### 6.2. Miss ratio and lookup rate

~~~promql
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result="miss"
}[5m]))
/
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result=~"hit|miss"
}[5m]))
~~~

Lookup rate:

~~~promql
sum(rate(cache_gets_total{
  application="catalog-service",
  cache="catalogBySku",
  result=~"hit|miss"
}[5m]))
~~~

A high miss ratio during **cold cache warmup** can be normal; a sudden miss-ratio jump after hours of stability can point to expiration, eviction, invalidation, or a shift in key distribution.

### 6.3. Eviction rate

~~~promql
sum(rate(cache_evictions_total{
  application="catalog-service",
  cache="catalogBySku"
}[5m]))
~~~

This is average eviction events per second as counted by the provider. If it spikes suddenly, cross-check `cache.size`, hits/misses, and `maximumSize`; do not assume insufficient memory if evictions can also reflect expiry or overwrites depending on the provider.

### 6.4. Cache size per instance

~~~promql
cache_size{
  application="catalog-service",
  cache="catalogBySku"
}
~~~

With in-process Caffeine, each JVM holds its own cache, so `cache_size` per `instance` shows each replica's size. You can sum across instances to estimate total entries *stored across all replicas*, yet **that is not the unique key count system-wide** because one SKU can be cached on multiple JVMs.

If multiple instances report on **one shared distributed cache**, summing sizes can double-count; understand the provider's metric scope before aggregating.

### 6.5. Viewing hit ratio per cache

When multiple caches share the `cache` label in one application, group by cache:

~~~promql
sum by (cache) (
  rate(cache_gets_total{
    application="catalog-service", result="hit"
  }[5m])
)
/
sum by (cache) (
  rate(cache_gets_total{
    application="catalog-service", result=~"hit|miss"
  }[5m])
)
~~~

If multiple `CacheManager`s might define identically named caches, keep the cache manager label in `sum by (...)` to avoid mixing them. Do not assume a `cacheManager` label exists in every backend: inspect actual series first.

## 7. A high hit ratio does not guarantee a good cache

Hit ratio is a useful indicator, **not a comprehensive SLO**. Easily misinterpreted cases:

| Situation | How metrics may look | Real problem |
| --- | --- | --- |
| Cache returns stale data | Very high hit ratio | Incorrect consistency or invalidation |
| Cache hits yet deserialization is slow | High hit ratio, HTTP p95 still rises | App processing cost or huge payload |
| Infrequently reused data across many keys | Low hit ratio | Workload may not fit caching |
| Many pods restarting | Sudden miss ratio spike | Cold cache |
| TTL too short | Rising misses/puts | Entries expire before reuse |
| `maximumSize` too small | Both evictions and misses climb | Capacity insufficient for working set |
| Distributed cache slow or network errors | Hits may stay high, latency still poor | Network/serialization/cache backend |
| Cache stampede when hot key expires | Many simultaneous misses and DB load spikes | Needs load coalescing or proper refresh policy |

When evaluating a cache, inspect **traffic, hits/misses, evictions, size, request latency, origin latency, and error rates**. For caches with freshness requirements, add business-layer freshness or correctness checks rather than inferring them from hit ratios.

### 7.1. How much load can cache hits save?

Suppose in 5 minutes there are 10,000 lookups: 9,000 hits and 1,000 misses. Without a cache, every lookup might hit the origin; with a cache, origin reads can drop dramatically.

However, **never claim you saved exactly 9,000 DB queries** purely from hits/misses. Some requests check multiple caches; concurrent misses may coalesce into a single load via synchronization; prefetch/refresh or batching may occur; and not every cache lookup corresponds 1-to-1 to a DB query.

To prove actual load reduction, measure **DB query rate / downstream request rate / connection pool usage** and compare before/after under equivalent traffic.

## 8. How metrics and Micrometer Observation complement each other

**Cache metrics** describe aggregate cache behavior, whereas **Micrometer Observation** tracks the duration of a business operation, emitting metrics and spans when instrumented. The two serve different purposes.

~~~mermaid
sequenceDiagram
    participant Client
    participant Catalog as CatalogService
    participant Cache as Caffeine cache
    participant Backend as CatalogBackend
    participant Metrics as Metrics backend
    participant Trace as Trace backend
    Client->>Catalog: GET /products/SKU-1
    Catalog->>Cache: lookup SKU-1
    alt Cache hit
        Cache-->>Catalog: ProductView
    else Cache miss
        Cache->>Backend: fetch SKU-1
        Backend-->>Cache: ProductView
        Cache-->>Catalog: ProductView
    end
    Catalog-->>Client: HTTP response
    Cache-->>Metrics: hit/miss/size/eviction metrics
    Catalog-->>Trace: Observed HTTP/backend spans if configured
~~~

In a typical Spring Boot app:

- **Cache provider metrics:** analyze cache effectiveness by cache name and instance.
- **HTTP server metrics:** show request rate, 4xx/5xx errors, processing duration, and p95/p99.
- **Downstream metrics:** show DB/HTTP call counts, connection wait times, and timeouts if instrumented.
- **Distributed tracing:** shows a concrete path, e.g., a request missed cache and then spent 800 ms in the database.
- **Logs:** provide error events or notable invalidations, linkable via trace ID/span ID.

**Do not assume** every cache lookup will appear as a trace span merely because cache hit/miss metrics exist. Provider binders mainly emit metrics; tracing individual lookups requires dedicated instrumentation and must weigh the high span cost of tracing every tiny lookup.

### 8.1. Tags and cardinality: a cache key is not a metric label

An internal cache naturally uses thousands of SKUs as keys. That **does not mean** SKU belongs in `cache.gets` labels. Dynamic keys are domain data; metric labels need small value sets like `cache=catalogBySku` or `result=hit|miss`.

Avoid labels such as `sku`, `userId`, `sessionId`, `orderId`, `traceId`, or raw URLs. Every new value spawns new time series, increasing memory, cost, and data exposure risk. To investigate a single request, rely on trace IDs with safe logs rather than putting request IDs into metrics.

### 8.2. Context propagation and sampling

When a cache miss triggers an outbound HTTP call to `catalog-service`, Spring Boot needs HTTP client/tracing instrumentation and context propagation (e.g., W3C `traceparent`) so spans from both services join the same trace. Across `@Async` or executors, matching context propagation is required.

Sampling may drop most traces, yet **it does not make cache counters disappear**: cache metrics keep accumulating independently. If a trace is not retained, you cannot conclude the request skipped the cache or that the cache isn't working.

### 8.3. Metrics exporters vs. tracing exporters

`/actuator/prometheus` serves Prometheus metrics via scraping. A separate OTLP tracing pipeline may push spans to a Collector and trace backend. If metrics export fine while traces are missing, separate sampling/propagation/tracing-exporter issues from cache binder issues.

For caches in Redis or other distributed systems, **server metrics** may differ from **client/cache-abstraction stats**. Clearly define where each metric is measured and use server-side telemetry when evaluating backend capacity or cluster-wide state.

## 9. Testing cache metrics

A helpful test suite proves three independent things:

1. **Cache behavior:** a second call with the same key skips the backend while the entry is valid.
2. **Provider statistics:** hits/misses update on lookups.
3. **Micrometer/Spring Boot integration:** metrics are actually bound and exposed by the active registry.

### 9.1. Unit testing Caffeine statistics

You can verify the provider itself without booting the application:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CaffeineStatisticsTest {
    @Test
    void countsOneMissAndOneHit() {
        Cache<String, String> cache = Caffeine.newBuilder()
                .recordStats()
                .build();

        String first = cache.get("SKU-1", key -> "Product A"); // Miss + load.
        String second = cache.getIfPresent("SKU-1");          // Hit.

        assertEquals("Product A", first);
        assertEquals("Product A", second);
        assertEquals(1L, cache.stats().missCount());
        assertEquals(1L, cache.stats().hitCount());
    }
}
~~~

This test **only verifies Caffeine statistics**; it does not prove Spring Boot created the named cache or Micrometer bound meters. Keep provider unit tests distinct from Actuator integration tests.

### 9.2. Unit testing the binder with `SimpleMeterRegistry`

To verify the bridge from Caffeine to Micrometer, use `CaffeineCacheMetrics` on a native cache:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.binder.cache.CaffeineCacheMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CaffeineMeterBindingTest {
    @Test
    void bindsCacheGetMetrics() {
        Cache<String, String> cache = Caffeine.newBuilder()
                .recordStats()
                .build();

        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            CaffeineCacheMetrics.monitor(registry, cache, "catalogBySku");

            cache.get("SKU-1", key -> "Product A");
            cache.getIfPresent("SKU-1");

            assertThat(registry.find("cache.gets")
                    .tag("cache", "catalogBySku")
                    .tag("result", "hit")
                    .meters()).isNotEmpty();
            assertThat(registry.find("cache.gets")
                    .tag("cache", "catalogBySku")
                    .tag("result", "miss")
                    .meters()).isNotEmpty();
        }
    }
}
~~~

The main point is verifying **meters are registered with expected tags**. When asserting count values, read the specific Micrometer meter (e.g., function counter from the provider binder) using the API for your version. Do not assert that `SimpleMeterRegistry` contains Prometheus-renamed `cache_gets_total`.

### 9.3. Spring Boot integration test

With `@SpringBootTest` or an appropriate test context:

1. Ensure `@EnableCaching` and the `CaffeineCacheManager` bean are present.
2. Call the **Spring bean** `CatalogService` through its proxy—never instantiate it with `new`.
3. Call `findProduct("SKU-1")` twice and verify the backend is called only once while cached.
4. Check that the injected `MeterRegistry` holds `cache.gets` with the expected cache tag, and observe hits/misses under traffic.
5. If using the Prometheus registry, inspect `/actuator/prometheus` output and exact series names.
6. Test invalidation, TTL, or eviction per cache policy; never assume every `@CacheEvict` increments `cache.evictions`.

Isolate cache state between tests so earlier runs do not turn expected misses into surprise hits. Use fixed small key sets and avoid assertions relying on test execution order.

## 10. Investigating cache incidents in production

### 10.1. Hit ratio drops sharply after deployment

For example, `catalogBySku` hit ratio drops from 92% to 35% after a rollout, while HTTP p95 climbs from 180 ms to 700 ms.

Suggested workflow:

1. **Confirm scope:** which cache, service, instance, release, and time window changed.
2. **Check traffic:** did request rate and lookup rate change? Was there a burst of new keys?
3. **Check cache warm-up:** did a rollout, pod restart, replica scale-out, or routing change leave in-process caches cold?
4. **Compare evictions and size:** is the cache hitting capacity limits? Was TTL shortened? Were entries bulk-invalidated?
5. **Check the backend:** did database/downstream load increase in line with misses?
6. **Use tracing and logs:** open sampled slow requests, inspect backend or connection pool wait times, and check timeout logs.
7. **Verify root cause:** adjust TTL/capacity/key logic or roll back cleanly, then re-measure hit ratio, backend load, and p95.

One **slow trace** shows what happened inside a single request; metrics show how many requests were affected. You need both kinds of evidence rather than generalizing from one trace.

### 10.2. Very high hit ratio while users see stale data

This is likely a **cache invalidation or freshness** bug, not a hit-ratio problem. Check:

- Does TTL match how fast underlying data changes?
- Is `@CacheEvict` or refresh logic running properly after updates?
- Did origin updates succeed while invalidation events were lost?
- Are there multiple in-process cache replicas where only one instance was evicted?
- Do consistency requirements make the current caching strategy unsuitable?

The fix is repairing data consistency contracts and testing updates/deletes, not trying to raise hit ratio.

### 10.3. Evictions rise alongside JVM GC pauses

If `catalogBySku` approaches `maximumSize` and evictions climb, inspect working set size, entry size, TTL, and memory pressure. Still, rising evictions alone do not prove GC pauses come from the cache: cross-check heap, allocation rate, CPU, and profiling if needed.

### 10.4. Cache metrics missing even though `@Cacheable` works

Check sequentially:

| Question | What to inspect |
| --- | --- |
| Is caching enabled? | `@EnableCaching`, right bean/proxy, and calls going through the proxy? |
| Is the provider supported? | Does Caffeine, JCache, or your provider have a matching binder? |
| Are stats enabled? | With Caffeine, is `recordStats()` enabled? |
| Did the cache exist at startup? | If created dynamically, explicit binding is needed |
| Is the cache name right? | Check `cacheNames` and tags in Actuator |
| Does Actuator list the meter? | Inspect `/actuator/metrics/cache.gets` |
| Is the Prometheus registry ready? | Dependency, exposure, path, network |
| Is the backend scraping? | Check Prometheus target, actual series, and timestamps |
| Is a `MeterFilter` blocking it? | Check meter deny/rename policies |

Never tweak the tracing exporter to fix unbound cache metrics; they are separate telemetry pipelines.

## 11. Cardinality, cost, and security

For cache metrics, the **cache name** is part of the observability contract. Some systems mistakenly embed user IDs into cache names:

~~~text
Avoid:
  cache=products-for-user-123
  cache=products-for-user-124
  cache=products-for-user-125

Recommended:
  cache=catalogBySku
  cache=permissionsByRole
~~~

Keep cache names bounded and domain-meaningful, using cache keys inside the provider to distinguish items. **Never put cache keys into metric tags**, especially emails, user IDs, large SKU sets, or raw URLs.

Suppose you have 10 cache names, 4 cache managers, 3 regions, and 30 instances. If all combinations appear, one meter can reach **10 × 4 × 3 × 30 = 3,600** series before multiplying by `result=hit|miss` and other labels. Creating a new cache name per request loses cardinality control fast.

With hit/miss stats, cost stems not only from series counts but also scrape frequency, retention, and backend count. Protect metrics endpoints and keep secrets or personal data out of tags, logs, and span attributes.

### 11.1. Changing metric schemas safely

Renaming `catalogBySku` or changing the `cache` tag can break existing dashboards and alerts even while the app keeps running. Before changing:

1. Locate queries, dashboards, and alerts referencing the cache name/label.
2. Plan dual support or migration during transition if possible.
3. Update documentation and contract tests.
4. Roll out and compare counts/rates across instances.
5. Agree on when to retire old queries once historical data is no longer needed.

## 12. Designing cache dashboards and alerts

A cache dashboard should answer not only "what is the hit ratio?" but also "**are users impacted?**".

| Panel group | Values to observe | Action hint when anomalous |
| --- | --- | --- |
| Lookup throughput | Hit, miss, and total lookup rates | Check whether workload shifted |
| Hit ratio | 5–30 min % hits per cache | Inspect warm-up, TTL, keys, and capacity |
| Eviction rate | Evictions/sec | Check memory budget and `maximumSize` |
| Cache size | Entry count per instance/manager | Spot skewed instances or flat cache growth |
| User latency | HTTP p95/p99 of product-read endpoints | Verify user impact |
| Downstream load | DB query/HTTP dependency rate, timeouts | See whether misses overload origins |
| JVM health | Heap, GC pauses, CPU | Balance cache memory cost against performance |
| Errors | HTTP and backend error rates | Separate cache misses from origin outages |

A naive hit-ratio alert like "below 70% for 10 minutes" triggers false positives during low traffic or cold caches. Combine **minimum lookup rate**, sustained duration across windows, and impact on downstream latency/error rates.

Moreover, caching is a performance optimization. In systems with formal SLOs, **user-facing latency and error rate** usually serve better as primary targets, while cache metrics act as diagnostic and tuning signals.

## 13. Hands-on exercise: measuring catalog cache effectiveness

**Context:** a Spring Boot application handles `GET /products/{sku}`. Product lookups spike after a marketing campaign. You need to prove the cache reduces `catalog-service` calls and detect when caching becomes ineffective.

**Tasks:**

1. Add `spring-boot-starter-cache`, Caffeine, Actuator, and the Prometheus registry.
2. Declare the `catalogBySku` cache with `maximumSize(10_000)`, 10-minute TTL, and `recordStats()`.
3. Create `CatalogService.findProduct(sku)` using `@Cacheable` calling a mock backend with a fetch counter.
4. Execute four lookups in order: `SKU-1`, `SKU-1`, `SKU-2`, `SKU-1`. Compute hits/misses on paper, then compare against provider statistics. Assuming an initially empty cache with no expiration: **2 misses, 2 hits, 50% hit ratio**.
5. Inspect `cache.gets`, `cache.puts`, `cache.size`, and the exact series exported by the Prometheus registry.
6. Write PromQL queries for 5-minute hit ratio, miss rate, and eviction rate; display lookup rate alongside to prevent misinterpretation at low traffic.
7. Lower `maximumSize` in a test environment and send many distinct keys; observe how evictions/misses and backend latency change.
8. Simulate updating a product: verify stale data remains without invalidation, then design and test `@CacheEvict` properly.
9. When miss rate climbs, open a sampled slow HTTP trace, and inspect backend spans and logs by trace ID if present.
10. Draft an alert proposal linking hit ratio with backend latency/5xx and a rule forbidding cache keys or personal data in metric tags.

**Expected deliverables:** working Caffeine config, unit/integration tests for caching and meter binding, a dashboard covering hits/misses/evictions/size, explanations of each metric's limitations, and a brief investigation report backed by metrics, logs, and traces.

## 14. Key takeaways

**Cache metrics** expose hits/misses, puts, evictions, and size for supported caches. In Spring Boot, Actuator/Micrometer can auto-bind initialized caches when the provider supports stats; for **Caffeine**, `recordStats()` is critical for tracking hits/misses.

A high hit ratio alone does not prove cached data is accurate or requests are fast; a high miss rate alone does not prove the system is broken. Read metrics by **cache, traffic, instance, time, and provider semantics**, then cross-check HTTP latency, downstream load, logs, and distributed traces. Safe tag/cardinality design, reliable exporters, and understanding sampling/context propagation are essential for evidence-based incident investigation.

**References:**

- [Spring Boot — Metrics and Cache Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Micrometer — Cache Metrics](https://docs.micrometer.io/micrometer/reference/reference/cache.html)
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Caffeine — Statistics](https://github.com/ben-manes/caffeine/wiki/Statistics)
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
